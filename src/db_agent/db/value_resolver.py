"""Deterministic value alignment for open-vocabulary filters (DB-backed).

When a SELECT returns zero rows because a free-text filter used a value that's
*close to* but not equal to a real stored value (a typo, a brand/generic
variant, wrong casing), `align_values` finds the nearest real value via pg_trgm
`similarity()` and returns a revision hint. It only inspects columns flagged
`fuzzy_align: true` in the semantic layer (e.g. drug_name, model_name), and only
hints when the nearest real value DIFFERS from what the user wrote — so a filter
that already matches a real value (a legitimately-empty permission-filtered
query like 吉非替尼) produces no hint and the empty result is accepted.

Mirrors `gene_resolver`'s pg_trgm approach; runs on the read replica via
`fetch` (parameterized — the user value is always bound, never interpolated).
The table/column identifiers come from the validated semantic layer, not user
input, so they are safe to interpolate into the query text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from db_agent.sql.critic import _alias_map, _scope_table_names

if TYPE_CHECKING:
    from db_agent.db.replica import ReadReplica
    from db_agent.semantic.model import SemanticLayer


def _term_from_predicate(pred: exp.Expression) -> tuple[exp.Column | None, str | None]:
    """(column, search term) from an `=` or `ILIKE` predicate, else (None, None).
    ILIKE patterns are stripped of leading/trailing % so '%吉非替尼%' -> '吉非替尼'."""
    if isinstance(pred, exp.EQ):
        left, right = pred.left, pred.right
        if isinstance(left, exp.Column) and isinstance(right, exp.Literal) and right.is_string:
            return left, right.this
        if isinstance(right, exp.Column) and isinstance(left, exp.Literal) and left.is_string:
            return right, left.this
        return None, None
    if isinstance(pred, exp.ILike) or isinstance(pred, exp.Like):
        this, patt = pred.this, pred.expression
        if isinstance(this, exp.Column) and isinstance(patt, exp.Literal) and patt.is_string:
            return this, patt.this.strip("%")
        return None, None
    return None, None


def _resolve_table(layer: SemanticLayer, amap: dict[str, str], scope: set[str], col: exp.Column):
    """The Table a fuzzy_align column belongs to (alias-qualified or unambiguous), else None."""
    name = col.name
    qualifier = col.table
    if qualifier:
        tbl = layer.get_table(amap.get(qualifier, qualifier))
        if tbl is not None and name in tbl.columns and tbl.columns[name].fuzzy_align:
            return tbl
        return None
    matches = [
        tbl
        for tn in scope
        if (tbl := layer.get_table(tn)) is not None
        and name in tbl.columns
        and tbl.columns[name].fuzzy_align
    ]
    return matches[0] if len(matches) == 1 else None


def align_values(
    replica: ReadReplica,
    layer: SemanticLayer,
    sql: str,
    domain: str | None,
    *,
    threshold: float = 0.3,
) -> str | None:
    """A revision hint when a fuzzy_align filter's value has a closer real value,
    else None. Runs pg_trgm similarity on the replica."""
    try:
        ast = parse_one(sql, dialect="postgres")
    except ParseError:
        return None
    if ast is None:
        return None

    amap = _alias_map(ast)
    scope = _scope_table_names(layer, domain)
    hints: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for pred in ast.find_all(exp.EQ, exp.ILike, exp.Like):
        col, term = _term_from_predicate(pred)
        if col is None or not term:
            continue
        tbl = _resolve_table(layer, amap, scope, col)
        if tbl is None:
            continue
        key = (tbl.name, col.name, term)
        if key in seen:
            continue
        seen.add(key)
        best = _nearest_value(replica, tbl.name, col.name, term, threshold)
        if best is not None and best != term:
            hints.append(
                f"column `{col.name}` has no value '{term}'; the closest stored value is '{best}'"
            )

    if not hints:
        return None
    return (
        "The query ran but returned 0 rows; a free-text filter does not match any "
        "stored value: " + "; ".join(hints) + ". Rewrite the SQL using the stored value(s)."
    )


def _nearest_value(
    replica: ReadReplica, table: str, column: str, term: str, threshold: float
) -> str | None:
    # table/column come from the validated semantic layer (not user input); the
    # user `term` is always bound as a parameter.
    rows = replica.fetch(
        f"SELECT {column} AS v, similarity({column}, %s) AS s FROM {table} "
        f"WHERE similarity({column}, %s) > %s AND {column} IS NOT NULL "
        f"ORDER BY s DESC LIMIT 1",
        (term, term, threshold),
    )
    if not rows:
        return None
    v = rows[0].get("v")
    return str(v) if v is not None else None
