from __future__ import annotations

from db_agent.db.audit import _COLUMNS
from db_agent.graph.state import initial_state
from db_agent.observability.postgres import PostgresObserver
from db_agent.observability.record import RunRecord


def _rec(**over):
    s = initial_state("q?")
    s.update({"status": "answered"})
    s.update(over)
    return RunRecord.from_state(s, run_id="abc123", latency_ms=12.5)


def test_record_has_run_id_and_latency():
    r = _rec()
    assert r.run_id == "abc123"
    assert r.latency_ms == 12.5
    d = r.to_dict()
    assert d["run_id"] == "abc123" and d["latency_ms"] == 12.5


def test_from_state_generates_run_id_when_absent():
    s = initial_state("q?")
    s["status"] = "answered"
    r = RunRecord.from_state(s)  # legacy call site, no run_id
    assert r.run_id  # non-empty generated hex
    assert r.latency_ms is None


def test_audit_columns_match_record_keys():
    # Guards drift: the audit table columns must mirror RunRecord exactly.
    assert set(_COLUMNS) == set(_rec().to_dict().keys())


class _FakeAudit:
    def __init__(self):
        self.inserted: list[RunRecord] = []

    def insert(self, record):
        self.inserted.append(record)


def test_postgres_observer_inserts_record():
    audit = _FakeAudit()
    obs = PostgresObserver(audit)
    rec = _rec()
    obs(rec)
    assert audit.inserted == [rec]
