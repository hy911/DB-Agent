"""Guard rail for sandbox analysis SQL (DuckDB dialect).

Defense in depth over the engine's locked-down connection: the analysis SQL must
be a single read-only SELECT referencing only the in-memory ``result`` table, with
no file/network/attach constructs. Fail closed (raise GuardError) on anything else.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from db_agent.sql.errors import GuardError

_ALLOWED_TABLE = "result"
_BANNED_FUNCS = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "parquet_scan",
        "read_json",
        "read_json_auto",
        "read_json_objects",
        "read_ndjson",
        "read_ndjson_auto",
        "read_text",
        "read_blob",
        "glob",
        "sniff_csv",
        "current_setting",
        "set_config",
    }
)

# Some file-reader functions are promoted to dedicated sqlglot nodes in the duckdb
# dialect (e.g. read_csv -> exp.ReadCSV), so their .name is "" and the name-based
# check below would miss them — match those node classes directly. Guarded with
# getattr so a sqlglot version lacking a class simply drops it from the tuple.
_BANNED_NODE_TYPES = tuple(
    t for t in (getattr(exp, n, None) for n in ("ReadCSV", "ReadParquet")) if t is not None
)


def validate_analysis_sql(sql: str) -> exp.Expression:
    try:
        statements = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
    except Exception as e:  # sqlglot ParseError and friends
        raise GuardError("analysis_parse_error", str(e).strip(), retryable=False) from e

    if len(statements) != 1:
        raise GuardError(
            "analysis_multi_statement", "exactly one statement is allowed", retryable=False
        )
    ast = statements[0]
    if not isinstance(ast, exp.Select):
        raise GuardError("analysis_not_select", "only a single SELECT is allowed", retryable=False)

    for table in ast.find_all(exp.Table):
        if table.name != _ALLOWED_TABLE:
            raise GuardError(
                "analysis_forbidden_table",
                f"only the 'result' table may be queried, got {table.name!r}",
                retryable=False,
            )

    for fn in ast.find_all(exp.Anonymous):
        name = (fn.name or "").lower()
        if name in _BANNED_FUNCS:
            raise GuardError(
                "analysis_banned_function", f"function {name!r} is not allowed", retryable=False
            )

    if _BANNED_NODE_TYPES:
        for _ in ast.find_all(*_BANNED_NODE_TYPES):
            raise GuardError(
                "analysis_banned_function",
                "file-reader function is not allowed",
                retryable=False,
            )

    return ast
