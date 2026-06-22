from __future__ import annotations

import pytest

from db_agent.sandbox.stats.functions import kaplan_meier, one_way_anova, welch_t_test
from db_agent.sql.errors import GuardError


def _tv_rows():
    return [{"g": "ctrl", "v": x} for x in (10.0, 11.0, 12.0, 9.0)] + [
        {"g": "drug", "v": x} for x in (2.0, 3.0, 1.0, 4.0)
    ]


def test_welch_t_test_detects_difference():
    out = welch_t_test(_tv_rows(), {"value": "v", "group": "g"})
    assert out.test == "welch_t_test"
    assert out.stats["p_value"] < 0.05
    assert out.stats["mean_difference"] > 0  # ctrl > drug (ctrl sorts first)
    assert {g["label"] for g in out.groups} == {"ctrl", "drug"}
    assert any("Welch" in c for c in out.caveats)


def test_welch_requires_exactly_two_groups():
    rows = _tv_rows() + [{"g": "third", "v": 5.0}, {"g": "third", "v": 6.0}]
    with pytest.raises(GuardError):
        welch_t_test(rows, {"value": "v", "group": "g"})


def test_welch_insufficient_n():
    rows = [{"g": "a", "v": 1.0}, {"g": "b", "v": 2.0}]
    with pytest.raises(GuardError):
        welch_t_test(rows, {"value": "v", "group": "g"})


def test_anova_three_groups():
    rows = (
        [{"g": "a", "v": x} for x in (1.0, 2.0, 3.0)]
        + [{"g": "b", "v": x} for x in (4.0, 5.0, 6.0)]
        + [{"g": "c", "v": x} for x in (7.0, 8.0, 9.0)]
    )
    out = one_way_anova(rows, {"value": "v", "group": "g"})
    assert out.test == "one_way_anova"
    assert out.stats["p_value"] < 0.05
    assert len(out.groups) == 3


def test_anova_needs_two_groups():
    rows = [{"g": "a", "v": 1.0}, {"g": "a", "v": 2.0}]
    with pytest.raises(GuardError):
        one_way_anova(rows, {"value": "v", "group": "g"})


def test_kaplan_meier_two_groups_has_logrank():
    rows = [{"grp": "ctrl", "t": t, "e": 1} for t in (2.0, 3.0, 4.0)] + [
        {"grp": "drug", "t": t, "e": 1} for t in (8.0, 9.0, 10.0)
    ]
    out = kaplan_meier(rows, {"duration": "t", "event": "e", "group": "grp"})
    assert out.test == "kaplan_meier"
    assert "logrank_statistic" in out.stats
    assert "p_value" in out.stats
    assert len(out.groups) == 2
    assert all("median_survival" in g for g in out.groups)


def test_kaplan_meier_no_group_single_curve():
    rows = [{"t": t, "e": 1} for t in (2.0, 4.0, 6.0, 8.0)]
    out = kaplan_meier(rows, {"duration": "t", "event": "e"})
    assert len(out.groups) == 1
    assert "logrank_statistic" not in out.stats


def test_kaplan_meier_rejects_bad_event_code():
    rows = [{"t": 1.0, "e": 2}, {"t": 2.0, "e": 0}]
    with pytest.raises(GuardError):
        kaplan_meier(rows, {"duration": "t", "event": "e"})
