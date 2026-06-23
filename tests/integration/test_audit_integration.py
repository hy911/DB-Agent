"""Live-PostgreSQL integration tests for the writable AuditLog.

Run with: uv run pytest -m integration   (requires DBAGENT_AUDIT_DB_DSN, a WRITABLE
role/db — never the read replica). Skipped when no audit DSN is configured.
"""

from __future__ import annotations

import pytest

from db_agent.config import get_settings
from db_agent.db.audit import AuditLog
from db_agent.graph.state import initial_state
from db_agent.observability.record import RunRecord

pytestmark = pytest.mark.integration

_audit_configured = get_settings().audit_db_dsn is not None
needs_audit = pytest.mark.skipif(not _audit_configured, reason="DBAGENT_AUDIT_DB_DSN not set")


@needs_audit
def test_ensure_schema_is_idempotent_and_insert_roundtrips():
    audit = AuditLog(get_settings())
    audit.open()  # ensure_schema runs here
    audit.ensure_schema()  # second call must not error (CREATE ... IF NOT EXISTS)
    try:
        s = initial_state("integration question?")
        s.update({"status": "answered", "domain": "efficacy", "answer": "ok"})
        rec = RunRecord.from_state(s, run_id=None, latency_ms=42.0)
        audit.insert(rec)
        rows = audit.fetch_records()
        match = [r for r in rows if r["run_id"].hex == rec.run_id or str(r["run_id"]) == rec.run_id]
        assert match, "inserted run_id not found"
        got = match[0]
        assert got["question"] == "integration question?"
        assert got["status"] == "answered"
        assert got["latency_ms"] == 42.0
    finally:
        audit.close()
