"""The read-replica I/O boundary.

Owns a psycopg connection pool to the restricted read-only replica role. Each
connection is configured read-only with a statement_timeout (belt-and-suspenders
over the role). ``execute`` runs an already-secured SQL string, optionally
EXPLAIN-gating a flagged big-table scan first, and maps any database error to a
GuardError that drives the self-correction loop.

This module is the only place that touches the database. It stays thin and
delegates every decision to the pure modules (explain, mapping).
"""

from __future__ import annotations

import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from db_agent.config import Settings
from db_agent.db.explain import evaluate_explain
from db_agent.db.mapping import classify_db_error
from db_agent.db.result import QueryResult
from db_agent.sql.errors import GuardError


class ReadReplica:
    def __init__(self, settings: Settings) -> None:
        self._timeout_ms = settings.statement_timeout_ms
        self.pool = ConnectionPool(
            conninfo=settings.replica_dsn,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            kwargs={"autocommit": False, "row_factory": dict_row},
            configure=self._configure,
            open=False,
        )

    def _configure(self, conn: psycopg.Connection) -> None:
        # read_only must be set before any transaction begins.
        conn.read_only = True
        # SET does not accept query parameters ($1); set_config() does and keeps
        # the value parameterized (no string interpolation).
        conn.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            (str(self._timeout_ms),),
        )
        conn.commit()

    def open(self) -> None:
        self.pool.open()

    def close(self) -> None:
        self.pool.close()

    def execute(
        self,
        sql: str,
        *,
        needs_explain: bool,
        big_tables: frozenset[str],
        limit: int | None = None,
    ) -> QueryResult:
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                if needs_explain:
                    cur.execute("EXPLAIN (FORMAT JSON) " + sql)
                    evaluate_explain(_plan_payload(cur.fetchone()), big_tables)
                start = time.perf_counter()
                cur.execute(sql)
                rows = cur.fetchall()
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                columns = [d.name for d in (cur.description or [])]
        except GuardError:
            raise  # EXPLAIN gate already produced a fatal GuardError
        except PoolTimeout as e:
            raise GuardError("pool_timeout", str(e).strip(), retryable=False) from e
        except psycopg.Error as e:
            category, retryable = classify_db_error(e.sqlstate)
            raise GuardError(category, str(e).strip(), retryable=retryable) from e

        truncated = limit is not None and len(rows) >= limit
        return QueryResult(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
            truncated=truncated,
            sql=sql,
            elapsed_ms=elapsed_ms,
        )


def _plan_payload(row: dict[str, object] | None) -> object:
    """Pull the JSON plan out of an EXPLAIN (FORMAT JSON) dict_row result.

    The single column is named "QUERY PLAN"; its value is the plan list.
    """
    if not row:
        return []
    return next(iter(row.values()))
