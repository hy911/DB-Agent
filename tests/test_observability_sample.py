from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from db_agent.db import QueryResult
from db_agent.graph.state import initial_state
from db_agent.observability.observer import JsonlObserver
from db_agent.observability.record import RunRecord
from db_agent.observability.source import read_jsonl


def _state_with_rows(rows):
    qr = QueryResult(
        columns=list(rows[0].keys()) if rows else [],
        rows=rows,
        rowcount=len(rows),
        truncated=False,
        sql="SELECT ...",
        elapsed_ms=1.0,
    )
    s = initial_state("q?")
    s.update({"status": "answered", "result": qr, "answer": "ok"})
    return s


def test_result_sample_caps_rows():
    rows = [{"n": i} for i in range(5)]
    r = RunRecord.from_state(_state_with_rows(rows), result_sample_rows=2)
    assert r.result_sample == [{"n": 0}, {"n": 1}]
    assert r.rowcount == 5  # full count preserved


def test_result_sample_zero_disables():
    r = RunRecord.from_state(_state_with_rows([{"n": 1}]), result_sample_rows=0)
    assert r.result_sample is None


def test_jsonl_handles_decimal_and_datetime(tmp_path):
    rows = [{"val": Decimal("1.5"), "ts": datetime(2026, 6, 23, 12), "d": date(2026, 6, 23)}]
    rec = RunRecord.from_state(_state_with_rows(rows), run_id="r1", result_sample_rows=10)
    p = tmp_path / "runs.jsonl"
    JsonlObserver(p)(rec)  # must not raise despite non-JSON-native types
    back = read_jsonl(p)
    assert len(back) == 1
    sample = back[0]["result_sample"][0]
    assert sample["val"] == "1.5"  # Decimal coerced via default=str
    assert sample["ts"].startswith("2026-06-23")


def test_read_jsonl_missing_file_is_empty(tmp_path):
    assert read_jsonl(tmp_path / "nope.jsonl") == []


def test_to_dict_with_sample_is_json_serializable():
    rec = RunRecord.from_state(_state_with_rows([{"n": 1}]), result_sample_rows=10)
    json.dumps(rec.to_dict())  # primitive rows serialize with no default needed
