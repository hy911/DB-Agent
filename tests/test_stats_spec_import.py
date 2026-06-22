from __future__ import annotations


def test_scipy_welch_matches_known_value():
    from scipy import stats

    # Two clearly different groups: Welch t is large, p is small.
    t, p = stats.ttest_ind([1.0, 2.0, 3.0], [10.0, 11.0, 12.0], equal_var=False)
    assert t < 0  # first group has the smaller mean
    assert p < 0.001


def test_scipy_anova_runs():
    from scipy import stats

    f, p = stats.f_oneway([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0])
    assert f > 0
    assert p < 0.05


def test_lifelines_km_and_logrank_run():
    from lifelines import KaplanMeierFitter
    from lifelines.statistics import logrank_test

    kmf = KaplanMeierFitter()
    kmf.fit([5, 6, 6, 2, 4], event_observed=[1, 0, 1, 1, 1])
    assert kmf.median_survival_time_ > 0

    res = logrank_test([5, 6, 6], [2, 3, 4], event_observed_A=[1, 1, 1], event_observed_B=[1, 1, 1])
    assert res.p_value >= 0.0
