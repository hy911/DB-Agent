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


def test_mann_whitney_detects_shift():
    from db_agent.sandbox.stats.functions import mann_whitney_u

    rows = [{"g": "a", "v": x} for x in (1.0, 2.0, 3.0, 4.0)] + [
        {"g": "b", "v": x} for x in (10.0, 11.0, 12.0, 13.0)
    ]
    out = mann_whitney_u(rows, {"value": "v", "group": "g"})
    assert out.test == "mann_whitney_u"
    assert out.stats["p_value"] < 0.05
    assert {g["label"] for g in out.groups} == {"a", "b"}
    assert all("median" in g for g in out.groups)


def test_mann_whitney_requires_two_groups():
    from db_agent.sandbox.stats.functions import mann_whitney_u

    rows = [{"g": "a", "v": 1.0}, {"g": "a", "v": 2.0}]
    with pytest.raises(GuardError):
        mann_whitney_u(rows, {"value": "v", "group": "g"})


def test_tukey_pairwise_keys_and_best_pair():
    from db_agent.sandbox.stats.functions import tukey_hsd

    rows = (
        [{"g": "a", "v": x} for x in (1.0, 2.0, 3.0)]
        + [{"g": "b", "v": x} for x in (1.5, 2.5, 3.5)]
        + [{"g": "c", "v": x} for x in (50.0, 51.0, 52.0)]
    )
    out = tukey_hsd(rows, {"value": "v", "group": "g"})
    assert out.test == "tukey_hsd"
    assert "a vs b p" in out.stats and "a vs c p" in out.stats and "b vs c p" in out.stats
    # a vs c is far apart -> smaller p than a vs b
    assert out.stats["a vs c p"] < out.stats["a vs b p"]


def test_tukey_needs_two_groups():
    from db_agent.sandbox.stats.functions import tukey_hsd

    rows = [{"g": "a", "v": 1.0}, {"g": "a", "v": 2.0}]
    with pytest.raises(GuardError):
        tukey_hsd(rows, {"value": "v", "group": "g"})


def test_two_way_anova_detects_main_effect():
    from db_agent.sandbox.stats.functions import two_way_anova

    # factor a drives y (x~low, y~high); factor b does not
    rows = []
    for b in ("p", "q"):
        rows += [{"a": "x", "b": b, "v": v} for v in (1.0, 2.0, 1.5)]
        rows += [{"a": "y", "b": b, "v": v} for v in (9.0, 8.0, 8.5)]
    out = two_way_anova(rows, {"value": "v", "factor1": "a", "factor2": "b"})
    assert out.test == "two_way_anova"
    assert out.stats["factor1_p"] < 0.05
    assert "factor2_p" in out.stats and "interaction_p" in out.stats
    assert len(out.groups) == 4  # 2x2 cells


def test_two_way_anova_needs_two_levels():
    from db_agent.sandbox.stats.functions import two_way_anova

    rows = [{"a": "x", "b": "p", "v": float(i)} for i in range(6)]  # one level each
    with pytest.raises(GuardError):
        two_way_anova(rows, {"value": "v", "factor1": "a", "factor2": "b"})


def test_cox_ph_detects_covariate_effect():
    from db_agent.sandbox.stats.functions import cox_ph

    # higher dose -> shorter survival (events all observed)
    rows = []
    for i in range(12):
        dose = float(i % 4)
        rows.append({"t": 20.0 - 3.0 * dose + (i % 2), "e": 1, "dose": dose})
    out = cox_ph(rows, {"duration": "t", "event": "e", "covariates": ["dose"]})
    assert out.test == "cox_ph"
    assert "dose hazard_ratio" in out.stats and "dose p" in out.stats
    assert out.groups[0]["n"] == 12


def test_cox_ph_insufficient_events():
    from db_agent.sandbox.stats.functions import cox_ph

    rows = [{"t": 5.0, "e": 0, "dose": 1.0}, {"t": 6.0, "e": 0, "dose": 2.0}]
    with pytest.raises(GuardError):
        cox_ph(rows, {"duration": "t", "event": "e", "covariates": ["dose"]})
