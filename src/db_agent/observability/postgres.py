"""Postgres observability sink: writes each RunRecord to the audit table.

A thin Observer over `db.audit.AuditLog` — observability stays the sink-selection
layer; all Postgres I/O lives in db/. Best-effort by contract: run_agent wraps the
observer call in try/except, so a sink failure never breaks a good answer.
"""

from __future__ import annotations

from db_agent.db.audit import AuditLog
from db_agent.observability.record import RunRecord


class PostgresObserver:
    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit

    def __call__(self, record: RunRecord) -> None:
        self._audit.insert(record)
