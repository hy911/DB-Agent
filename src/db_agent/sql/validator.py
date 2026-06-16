"""SQL validator (guard rail #1).

Responsibilities — *structure and safety only, never row-level permissions*:

1. Parse exactly one statement (reject ``;``-chained payloads).
2. Enforce read-only: the statement and every node in it must be SELECT-shaped.
3. Table allow-list: every physical table referenced must be in scope for the
   routed domain. This is what keeps ``m_*`` mirror tables, ``*_stats`` and the
   django/auth/rbac system tables out of reach.
4. Ban dangerous functions and system-catalog access.
5. Enforce / clamp ``LIMIT`` on the top-level query.
6. Big-table guard: flag queries over the multi-million-row expression table
   that lack a ``model_uuid`` / ``gene_symbol`` filter so the caller can run an
   ``EXPLAIN`` gate before execution. (Not triggered in the efficacy MVP, but
   the rule is implemented generically.)

The validator works on a sqlglot AST and mutates it in place where noted
(LIMIT). It does not touch the database; the EXPLAIN gate lives in
:mod:`db_agent.db.replica` and is driven by the ``needs_explain`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from db_agent.semantic.model import SemanticLayer
from db_agent.sql.errors import GuardError

# Statement node types that must never appear anywhere in a read-only query.
# Built dynamically so we stay compatible across sqlglot versions that may not
# define every name (e.g. Grant / TruncateTable).
_FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "TruncateTable",
    "Grant",
    "Set",
    "SetItem",
    "Command",
)
_FORBIDDEN_NODES = tuple(getattr(exp, name) for name in _FORBIDDEN_NODE_NAMES if hasattr(exp, name))

_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# Functions that can read the filesystem, sleep the connection, reach other
# databases, or otherwise escape a read-only SELECT.
_BANNED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_exec",
        "query_to_xml",
        "copy",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "set_config",
        "current_setting",
    }
)

_BANNED_SCHEMAS = frozenset({"pg_catalog", "information_schema"})


@dataclass(frozen=True)
class ValidationConfig:
    allowed_tables: frozenset[str]
    default_limit: int = 1000
    max_limit: int = 10000
    big_tables: frozenset[str] = frozenset({"model_ccle_expression_data"})
    big_table_filter_keys: frozenset[str] = frozenset({"model_uuid", "gene_symbol"})


def validation_config_for_domain(
    layer: SemanticLayer,
    domain: str,
    *,
    default_limit: int = 1000,
    max_limit: int = 10000,
) -> ValidationConfig:
    """Allow only the routed domain's tables plus reference tables and the hub.

    Reference tables (model_desc_info, gene_info, ...) are always allowed because
    nearly every business query joins the spine.
    """
    allowed = {t.name for t in layer.tables_in_domain(domain)}
    allowed |= {t.name for t in layer.reference_tables()}
    dom = layer.get_domain(domain)
    if dom and dom.hub:
        allowed.add(dom.hub)
    big = frozenset(t.name for t in layer.tables.values() if t.big_table)
    return ValidationConfig(
        allowed_tables=frozenset(allowed),
        default_limit=default_limit,
        max_limit=max_limit,
        big_tables=big or frozenset({"model_ccle_expression_data"}),
    )


def parse_single_statement(sql: str) -> exp.Expression:
    """Parse one statement. Multiple statements or a parse error are rejected.

    A parse error is *retryable* (the model wrote bad SQL); a multi-statement
    payload is *fatal* (an injection attempt, never a legitimate generation).
    """
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except ParseError as e:
        raise GuardError("parse", f"could not parse SQL: {e}", retryable=True) from e

    statements = [s for s in statements if s is not None]
    if not statements:
        raise GuardError("parse", "empty SQL", retryable=True)
    if len(statements) > 1:
        raise GuardError(
            "multi_statement",
            "multiple statements are not allowed",
            retryable=False,
        )
    return statements[0]


def validate_structure(ast: exp.Expression, cfg: ValidationConfig) -> None:
    """Run all structural / safety checks. Raises GuardError on the first failure."""
    _check_read_only(ast)
    _check_tables(ast, cfg)
    _check_functions(ast)


def _check_read_only(ast: exp.Expression) -> None:
    if not isinstance(ast, _ALLOWED_ROOTS):
        raise GuardError(
            "not_read_only",
            f"only SELECT queries are allowed, got {type(ast).__name__}",
            retryable=False,
        )
    for node in ast.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise GuardError(
                "not_read_only",
                f"forbidden statement element: {type(node).__name__}",
                retryable=False,
            )


def _physical_tables(ast: exp.Expression) -> list[exp.Table]:
    """All physical table references, excluding names that are CTE aliases."""
    cte_names = {cte.alias_or_name for cte in ast.find_all(exp.CTE)}
    return [t for t in ast.find_all(exp.Table) if t.name not in cte_names]


def _check_tables(ast: exp.Expression, cfg: ValidationConfig) -> None:
    for table in _physical_tables(ast):
        schema = (table.db or "").lower()
        if schema in _BANNED_SCHEMAS:
            raise GuardError(
                "forbidden_table",
                f"access to system schema {schema!r} is not allowed",
                retryable=False,
            )
        if table.name not in cfg.allowed_tables:
            raise GuardError(
                "forbidden_table",
                f"table {table.name!r} is out of scope for this query",
                retryable=False,
            )


def _check_functions(ast: exp.Expression) -> None:
    for func in ast.find_all(exp.Anonymous):
        name = (func.name or "").lower()
        if name in _BANNED_FUNCTIONS:
            raise GuardError(
                "forbidden_function",
                f"function {name!r} is not allowed",
                retryable=False,
            )
    # sqlglot models some of these as dedicated nodes rather than Anonymous.
    for func in ast.find_all(exp.Func):
        name = (func.sql_name() or "").lower()
        if name in _BANNED_FUNCTIONS:
            raise GuardError(
                "forbidden_function",
                f"function {name!r} is not allowed",
                retryable=False,
            )


def enforce_limit(ast: exp.Expression, cfg: ValidationConfig) -> exp.Expression:
    """Ensure the top-level query has a LIMIT no larger than ``max_limit``."""
    limit = ast.args.get("limit")
    if limit is None:
        return ast.limit(cfg.default_limit)

    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int:
        if int(value.name) > cfg.max_limit:
            limit.set("expression", exp.Literal.number(cfg.max_limit))
    return ast


def requires_explain_guard(ast: exp.Expression, cfg: ValidationConfig) -> bool:
    """True when a big table is queried without a required filter key.

    The caller should then run ``EXPLAIN`` on the read replica and reject a plan
    that sequentially scans the big table.
    """
    referenced = {t.name for t in _physical_tables(ast)}
    big_used = referenced & cfg.big_tables
    if not big_used:
        return False
    return not _has_filter_key(ast, cfg.big_table_filter_keys)


def _has_filter_key(ast: exp.Expression, keys: frozenset[str]) -> bool:
    """Heuristic: any equality / IN predicate on one of the filter-key columns."""
    for pred in ast.find_all(exp.EQ, exp.In):
        for col in pred.find_all(exp.Column):
            if col.name in keys:
                return True
    return False
