from __future__ import annotations

import json

from db_agent.graph.state import initial_state
from db_agent.observability.observer import JsonlObserver, NullObserver, Observer
from db_agent.observability.record import RunRecord


def _rec(status="answered"):
    s = initial_state("q?")
    s["status"] = status
    return RunRecord.from_state(s)


def test_observers_satisfy_protocol(tmp_path):
    assert isinstance(NullObserver(), Observer)
    assert isinstance(JsonlObserver(tmp_path / "x.jsonl"), Observer)


def test_null_observer_writes_nothing(tmp_path):
    NullObserver()(_rec())
    assert list(tmp_path.iterdir()) == []


def test_jsonl_observer_appends_lines(tmp_path):
    p = tmp_path / "logs" / "runs.jsonl"  # parent dir does not exist yet
    obs = JsonlObserver(p)
    obs(_rec("answered"))
    obs(_rec("error"))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "answered"
    assert json.loads(lines[1])["status"] == "error"
