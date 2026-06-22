from __future__ import annotations

import pytest

from db_agent.sandbox.stats.spec import ParamSpec, StatResult, StatTest
from db_agent.sandbox.stats.validator import validate_stat_request
from db_agent.sql.errors import GuardError


def _dummy_run(rows, params):
    return StatResult(test="dummy", stats={}, groups=[], caveats=[])


REG = {
    "two_group": StatTest(
        "two_group",
        "compare two groups",
        {
            "value": ParamSpec("column"),
            "group": ParamSpec("column"),
            "alpha": ParamSpec("scalar", required=False, py_type=float, bounds=(0.0, 1.0)),
        },
        _dummy_run,
    )
}

COLS = ["value", "group", "other"]


def test_accepts_valid_request():
    v = validate_stat_request(
        {"function": "two_group", "params": {"value": "value", "group": "group"}}, COLS, REG
    )
    assert v.test.name == "two_group"
    assert v.params == {"value": "value", "group": "group"}


def test_accepts_optional_scalar_in_bounds():
    v = validate_stat_request(
        {"function": "two_group", "params": {"value": "value", "group": "group", "alpha": 0.01}},
        COLS,
        REG,
    )
    assert v.params["alpha"] == 0.01


def test_rejects_unknown_function():
    with pytest.raises(GuardError):
        validate_stat_request({"function": "nope", "params": {}}, COLS, REG)


def test_rejects_missing_required_param():
    with pytest.raises(GuardError):
        validate_stat_request({"function": "two_group", "params": {"value": "value"}}, COLS, REG)


def test_rejects_unknown_param():
    with pytest.raises(GuardError):
        validate_stat_request(
            {"function": "two_group", "params": {"value": "value", "group": "group", "x": 1}},
            COLS,
            REG,
        )


def test_rejects_column_not_in_table():
    with pytest.raises(GuardError):
        validate_stat_request(
            {"function": "two_group", "params": {"value": "value", "group": "missing"}}, COLS, REG
        )


def test_rejects_scalar_out_of_range():
    with pytest.raises(GuardError):
        validate_stat_request(
            {"function": "two_group", "params": {"value": "value", "group": "group", "alpha": 9.0}},
            COLS,
            REG,
        )


def test_rejects_scalar_wrong_type():
    with pytest.raises(GuardError):
        validate_stat_request(
            {
                "function": "two_group",
                "params": {"value": "value", "group": "group", "alpha": "high"},
            },
            COLS,
            REG,
        )


def test_rejects_non_object_request():
    with pytest.raises(GuardError):
        validate_stat_request("SELECT 1", COLS, REG)


def test_rejects_typeless_scalar():
    reg = {
        "bad": StatTest(
            "bad",
            "typeless scalar",
            {"x": ParamSpec("scalar", required=False, py_type=None)},
            _dummy_run,
        )
    }
    with pytest.raises(GuardError):
        validate_stat_request({"function": "bad", "params": {"x": 1}}, COLS, reg)
