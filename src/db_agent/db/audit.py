"""The audit-log I/O boundary — a *writable* Postgres connection.

Separate from `replica.py` on purpose: the read replica uses a restricted
read-only role and must never be written to. The audit log lives in its own
writable database/role (`Settings.audit_db_dsn`) and stores one row per agent
run for offline analysis. Result rows are never stored — only the `RunRecord`
summary (rowcount/columns/truncated), matching the privacy design.

This module owns all SQL for the audit table; values are always bound as
parameters and the table name is composed via `psycopg.sql.Identifier`.
"""

from __future__ import annotations

import functools
import json
from datetime import datetime
from typing import TYPE_CHECKING

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from db_agent.config import Settings

if TYPE_CHECKING:
    # Type-only import keeps db/ free of a runtime dependency on observability.
    from db_agent.observability.record import RunRecord

# default=str: sampled result rows may hold Decimal/datetime/date that json can't
# encode natively — coerce to strings rather than fail the insert.
_dumps = functools.partial(json.dumps, default=str)
_JSONB_COLUMNS = frozenset({"columns", "result_sample"})

# Column order is the single source of truth for both DDL and INSERT.
_COLUMNS: tuple[str, ...] = (
    "run_id",
    "ts",
    "question",
    "domain",
    "context",
    "raw_sql",
    "sql",
    "analysis_sql",
    "stat_request",
    "status",
    "attempts",
    "rowcount",
    "columns",
    "truncated",
    "answer",
    "clarification",
    "error",
    "latency_ms",
    "result_sample",
    "feedback",
    "worker",
)

_DDL = """CREATE TABLE IF NOT EXISTS {tbl} (
    run_id uuid PRIMARY KEY,
    ts timestamptz NOT NULL,
    question text,
    domain text,
    context text,
    raw_sql text,
    sql text,
    analysis_sql text,
    stat_request text,
    status text,
    attempts integer,
    rowcount integer,
    columns jsonb,
    truncated boolean,
    answer text,
    clarification text,
    error text,
    latency_ms double precision,
    result_sample jsonb,
    feedback text,
    worker text
)"""


class AuditLog:
    def __init__(self, settings: Settings) -> None:
        if settings.audit_db_dsn is None:
            raise ValueError("AuditLog requires Settings.audit_db_dsn")
        self._table = settings.audit_table
        # autocommit: each run is a single best-effort INSERT, no transaction needed.
        # Short timeouts so a slow/unreachable LOG db never stalls a real query:
        # connect_timeout bounds the TCP connect (libpq default is infinite); the
        # pool `timeout` bounds waiting for a free connection. Logging is best-effort
        # (run_agent swallows failures), so failing fast here is the right trade.
        self.pool = ConnectionPool(
            conninfo=settings.audit_db_dsn,
            min_size=1,
            max_size=settings.pool_max_size,
            kwargs={"autocommit": True, "connect_timeout": 5},
            timeout=5.0,
            open=False,
        )

    def open(self) -> None:
        self.pool.open()
        self.ensure_schema()

    def close(self) -> None:
        self.pool.close()

    def ensure_schema(self) -> None:
        tbl = sql.Identifier(self._table)
        ddl = sql.SQL(_DDL).format(tbl=tbl)
        indexes = [
            sql.SQL("CREATE INDEX IF NOT EXISTS {name} ON {tbl} ({col})").format(
                name=sql.Identifier(f"{self._table}_{col}_idx"),
                tbl=tbl,
                col=sql.Identifier(col),
            )
            for col in ("ts", "status", "domain")
        ]
        # Columns added after a table was first created (e.g. `worker`): bring an
        # existing table up to date. ADD COLUMN IF NOT EXISTS is a no-op otherwise.
        alters = [
            sql.SQL("ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} text").format(
                tbl=tbl, col=sql.Identifier("worker")
            )
        ]
        with self.pool.connection() as conn:
            conn.execute(ddl)
            for alter in alters:
                conn.execute(alter)
            for idx in indexes:
                conn.execute(idx)

    def insert(self, record: RunRecord) -> None:
        d = record.to_dict()
        values = []
        for col in _COLUMNS:
            v = d[col]
            if col == "ts" and v is not None:
                v = datetime.fromisoformat(v)
            elif col in _JSONB_COLUMNS and v is not None:
                v = Jsonb(v, dumps=_dumps)
            values.append(v)
        stmt = sql.SQL("INSERT INTO {tbl} ({cols}) VALUES ({ph})").format(
            tbl=sql.Identifier(self._table),
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in _COLUMNS),
            ph=sql.SQL(", ").join(sql.Placeholder() for _ in _COLUMNS),
        )
        with self.pool.connection() as conn:
            conn.execute(stmt, values)

    def fetch_records(self) -> list[dict[str, object]]:
        """Read all audit rows as dicts (for the analysis report). Trusted, no params."""
        stmt = sql.SQL("SELECT {cols} FROM {tbl}").format(
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in _COLUMNS),
            tbl=sql.Identifier(self._table),
        )
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(stmt)
            return cur.fetchall()
