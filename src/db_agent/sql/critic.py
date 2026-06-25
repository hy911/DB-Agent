"""Data-aware self-correction diagnosis (pure, no I/O).

When a SELECT runs cleanly but returns ZERO rows, the result may be genuinely
empty (correct) OR the symptom of a fixable mistake — most commonly a filter on
a closed-vocabulary column that used a value outside the allowed set (e.g.
``is_cancer_model = 'T'`` instead of ``'cancer'``, a lung subtype string instead
of ``'Lung Carcinoma'``).

`diagnose_empty_result` inspects the secured SQL's AST and returns a concrete
revision hint ONLY when it finds such a high-precision signal; otherwise it
returns ``None`` so the agent accepts the empty result as real (never looping on
a legitimately-empty query — e.g. a drug that exists but is filtered out by the
``for_bd`` permission). It deliberately checks only equality / ``IN`` predicates
against columns carrying a closed ``values`` enum — never open ``examples`` /
``ILIKE`` columns like ``drug_name`` — so it cannot misfire on those.
"""

from __future__ import annotations

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from db_agent.semantic.model import SemanticLayer


def _alias_map(ast: exp.Expression) -> dict[str, str]:
    """alias-or-bare-name -> real table name, for every table reference."""
    return {t.alias_or_name: t.name for t in ast.find_all(exp.Table)}


def _scope_table_names(layer: SemanticLayer, domain: str | None) -> set[str]:
    tables = []
    if domain is not None:
        tables += layer.tables_in_domain(domain)
    tables += layer.spine_tables() + layer.reference_tables()
    return {t.name for t in tables}


def _enum_for_column(
    layer: SemanticLayer,
    amap: dict[str, str],
    scope: set[str],
    col: exp.Column,
) -> tuple[str, ...] | None:
    """The closed `values` enum for `col`, or None if the column has none / can't
    be resolved unambiguously."""
    name = col.name
    qualifier = col.table  # alias or table name, "" if unqualified
    if qualifier:
        real = amap.get(qualifier, qualifier)
        tbl = layer.get_table(real)
        if tbl is not None and name in tbl.columns and tbl.columns[name].values:
            return tbl.columns[name].values
        return None
    # Unqualified: only trust it if exactly one in-scope table has this enum column.
    matches = [
        tbl.columns[name].values
        for tn in scope
        if (tbl := layer.get_table(tn)) is not None
        and name in tbl.columns
        and tbl.columns[name].values
    ]
    return matches[0] if len(matches) == 1 else None


def _col_and_literals(pred: exp.Expression) -> tuple[exp.Column | None, list[str]]:
    """Extract (column, [string-literal values]) from an `=` or `IN` predicate."""
    if isinstance(pred, exp.EQ):
        left, right = pred.left, pred.right
        if isinstance(left, exp.Column) and isinstance(right, exp.Literal) and right.is_string:
            return left, [right.this]
        if isinstance(right, exp.Column) and isinstance(left, exp.Literal) and left.is_string:
            return right, [left.this]
        return None, []
    if isinstance(pred, exp.In):
        this = pred.this
        if isinstance(this, exp.Column):
            lits = [e.this for e in pred.expressions if isinstance(e, exp.Literal) and e.is_string]
            return this, lits
        return None, []
    return None, []


def diagnose_empty_result(sql: str, layer: SemanticLayer, domain: str | None) -> str | None:
    """A revision hint when an empty result looks fixable, else None.

    Only fires on a filter that compares a closed-vocabulary column to a value
    outside its allowed set — a high-precision "you wrote the wrong stored value"
    signal. Returns None (accept the empty result) for everything else.
    """
    try:
        ast = parse_one(sql, dialect="postgres")
    except ParseError:
        return None
    if ast is None:
        return None

    amap = _alias_map(ast)
    scope = _scope_table_names(layer, domain)
    problems: list[str] = []
    for pred in ast.find_all(exp.EQ, exp.In):
        col, literals = _col_and_literals(pred)
        if col is None or not literals:
            continue
        enum = _enum_for_column(layer, amap, scope, col)
        if enum is None:
            continue
        allowed = set(enum)
        bad = [v for v in literals if v not in allowed]
        if bad:
            allowed_str = ", ".join(f"'{v}'" for v in enum)
            bad_str = ", ".join(f"'{v}'" for v in bad)
            problems.append(
                f"column `{col.name}` only accepts one of [{allowed_str}], "
                f"but the filter used {bad_str}"
            )

    if not problems:
        return None
    return (
        "The query ran but returned 0 rows, and the filter uses values outside a "
        "column's closed value set: "
        + "; ".join(problems)
        + ". Rewrite the SQL using the closest allowed value(s) from that set."
    )
