"""Locked-down in-memory DuckDB execution for result post-processing.

Opens a fresh in-memory DuckDB with external access disabled, builds a single
``result`` table from the (already-permission-filtered) rows, validates the SQL,
runs it, and returns a QueryResult. duckdb is imported lazily so importing the
graph does not require duckdb at module-import time.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal

from db_agent.db.result import QueryResult
from db_agent.sandbox.validator import validate_analysis_sql
from db_agent.sql.errors import GuardError

# Python type -> DuckDB column type. bool before int (bool is an int subclass).
_TYPE_MAP: tuple[tuple[type, str], ...] = (
    (bool, "BOOLEAN"),
    (int, "BIGINT"),
    (float, "DOUBLE"),
    (Decimal, "DOUBLE"),
    (datetime.datetime, "TIMESTAMP"),
    (datetime.date, "DATE"),
)


def _column_type(values: Sequence[object]) -> str:
    for v in values:
        if v is None:
            continue
        for py, sql in _TYPE_MAP:
            if isinstance(v, py):
                return sql
        return "VARCHAR"
    return "VARCHAR"


def _coerce(v: object) -> object:
    return float(v) if isinstance(v, Decimal) else v


class DuckDBSandbox:
    def run(self, columns: list[str], rows: list[dict[str, object]], sql: str) -> QueryResult:
        validate_analysis_sql(sql)  # raises GuardError if unsafe
        import duckdb

        con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
        try:
            coldefs = ", ".join(
                f'"{c}" {_column_type([r.get(c) for r in rows])}' for c in columns
            )
            con.execute(f"CREATE TABLE result ({coldefs})")
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                con.executemany(
                    f"INSERT INTO result VALUES ({placeholders})",
                    [[_coerce(r.get(c)) for c in columns] for r in rows],
                )
            cur = con.execute(sql)
            out_columns = [d[0] for d in cur.description]
            out_rows = [dict(zip(out_columns, row, strict=False)) for row in cur.fetchall()]
        except duckdb.Error as e:
            raise GuardError("duckdb_error", str(e).strip(), retryable=False) from e
        finally:
            con.close()

        return QueryResult(
            columns=out_columns,
            rows=out_rows,
            rowcount=len(out_rows),
            truncated=False,
            sql=sql,
            elapsed_ms=0.0,
        )
