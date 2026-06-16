from __future__ import annotations

import json

from db_agent.db import QueryResult
from db_agent.graph.state import initial_state
from db_agent.observability.record import RunRecord


def _final(**over):
    s = initial_state("q?")
    s.update(over)
    return s


def test_from_state_answered_has_result_summary():
    qr = QueryResult(
        columns=["n"], rows=[{"n": 1}], rowcount=1, truncated=False,
        sql="SELECT 1", elapsed_ms=1.0,
    )
    s = _final(
        status="answered", domain="efficacy", context="ctx",
        sql="SELECT 1", secured_sql="SELECT 1 LIMIT 1000", attempts=1,
        result=qr, answer="one",
    )
    r = RunRecord.from_state(s)
    assert r.status == "answered"
    assert r.rowcount == 1 and r.columns == ["n"] and r.truncated is False
    assert r.sql == "SELECT 1 LIMIT 1000" and r.raw_sql == "SELECT 1"
    assert r.domain == "efficacy" and r.context == "ctx" and r.answer == "one"
    assert r.feedback is None
    assert "T" in r.ts  # ISO-8601 timestamp


def test_from_state_clarify_has_no_result():
    s = _final(status="clarify", clarification="which drug?")
    r = RunRecord.from_state(s)
    assert r.status == "clarify"
    assert r.clarification == "which drug?"
    assert r.rowcount is None and r.columns is None and r.truncated is None


def test_to_dict_is_json_serializable():
    s = _final(status="error", error="boom")
    d = RunRecord.from_state(s).to_dict()
    json.dumps(d)  # must not raise
    assert d["status"] == "error" and d["error"] == "boom"
