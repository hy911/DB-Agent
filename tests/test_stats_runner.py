from __future__ import annotations

import json

import pytest

from db_agent.sandbox.stats.runner import run_stat
from db_agent.sql.errors import GuardError


def _rows():
    return [{"g": "ctrl", "v": x} for x in (10.0, 11.0, 12.0, 9.0)] + [
        {"g": "drug", "v": x} for x in (2.0, 3.0, 1.0, 4.0)
    ]


def test_run_stat_end_to_end_welch():
    req = json.dumps({"function": "welch_t_test", "params": {"value": "v", "group": "g"}})
    out = run_stat(["g", "v"], _rows(), req)
    assert out.test == "welch_t_test"
    assert out.stats["p_value"] < 0.05


def test_run_stat_rejects_bad_json():
    with pytest.raises(GuardError):
        run_stat(["g", "v"], _rows(), "not json {")


def test_run_stat_rejects_unknown_function():
    req = json.dumps({"function": "ranksum", "params": {"value": "v", "group": "g"}})
    with pytest.raises(GuardError):
        run_stat(["g", "v"], _rows(), req)


def test_run_stat_rejects_column_not_in_table():
    req = json.dumps({"function": "welch_t_test", "params": {"value": "v", "group": "missing"}})
    with pytest.raises(GuardError):
        run_stat(["g", "v"], _rows(), req)


def test_run_stat_rejects_too_many_rows():
    from db_agent.sandbox.stats.runner import _MAX_ROWS

    rows = [{"g": "a", "v": 1.0}] * (_MAX_ROWS + 1)
    req = json.dumps({"function": "welch_t_test", "params": {"value": "v", "group": "g"}})
    with pytest.raises(GuardError):
        run_stat(["g", "v"], rows, req)
