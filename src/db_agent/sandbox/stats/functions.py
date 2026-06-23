"""Hand-written, audited statistical tests. Each takes the result rows + validated
params and returns a StatResult. scipy/lifelines are imported lazily so importing
this module (e.g. via the registry at graph build time) stays cheap and offline."""

from __future__ import annotations

import math
from statistics import fmean, median

from db_agent.sandbox.stats.spec import StatResult
from db_agent.sql.errors import GuardError

_MAX_GROUPS = 20


def _to_float(col: str, value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as e:
        raise GuardError(
            "stat_bad_value", f"column {col!r} has non-numeric value {value!r}", retryable=False
        ) from e


def _group_values(rows, value_col: str, group_col: str) -> dict[str, list[float]]:
    groups: dict[str, list[float]] = {}
    for r in rows:
        g = r.get(group_col)
        v = r.get(value_col)
        if g is None or v is None:
            continue
        f = _to_float(value_col, v)
        if math.isnan(f):
            continue
        groups.setdefault(str(g), []).append(f)
    return groups


def _significance(p: float, alpha: float) -> str:
    return (
        f"Result is significant at alpha={alpha} (p={p:.4g})."
        if p < alpha
        else f"Result is not significant at alpha={alpha} (p={p:.4g})."
    )


def welch_t_test(rows, params) -> StatResult:
    from scipy import stats as _stats

    groups = _group_values(rows, params["value"], params["group"])
    if len(groups) != 2:
        raise GuardError(
            "stat_group_count", f"t-test needs exactly 2 groups, got {len(groups)}", retryable=False
        )
    (l1, v1), (l2, v2) = sorted(groups.items())
    if len(v1) < 2 or len(v2) < 2:
        raise GuardError(
            "stat_insufficient_n", "each group needs at least 2 values", retryable=False
        )
    alpha = float(params.get("alpha", 0.05))
    t, p = _stats.ttest_ind(v1, v2, equal_var=False)
    m1, m2 = fmean(v1), fmean(v2)
    caveats = [
        "Welch's t-test (does not assume equal variances).",
        "Assumes approximately normal group distributions.",
    ]
    if min(len(v1), len(v2)) < 5:
        caveats.append("Small sample size (a group has n<5); interpret with caution.")
    caveats.append(_significance(float(p), alpha))
    return StatResult(
        test="welch_t_test",
        stats={"t": float(t), "p_value": float(p), "mean_difference": m1 - m2},
        groups=[
            {"label": l1, "n": len(v1), "mean": m1},
            {"label": l2, "n": len(v2), "mean": m2},
        ],
        caveats=caveats,
    )


def one_way_anova(rows, params) -> StatResult:
    from scipy import stats as _stats

    groups = _group_values(rows, params["value"], params["group"])
    if len(groups) < 2:
        raise GuardError(
            "stat_group_count", f"ANOVA needs at least 2 groups, got {len(groups)}", retryable=False
        )
    if len(groups) > _MAX_GROUPS:
        raise GuardError(
            "stat_group_count", f"too many groups ({len(groups)} > {_MAX_GROUPS})", retryable=False
        )
    for label, vals in groups.items():
        if len(vals) < 2:
            raise GuardError(
                "stat_insufficient_n", f"group {label!r} needs at least 2 values", retryable=False
            )
    alpha = float(params.get("alpha", 0.05))
    f, p = _stats.f_oneway(*groups.values())
    caveats = [
        "One-way ANOVA.",
        "Assumes normality and equal variances across groups.",
        _significance(float(p), alpha),
    ]
    return StatResult(
        test="one_way_anova",
        stats={"f": float(f), "p_value": float(p)},
        groups=[{"label": lab, "n": len(v), "mean": fmean(v)} for lab, v in sorted(groups.items())],
        caveats=caveats,
    )


def kaplan_meier(rows, params) -> StatResult:
    from lifelines import KaplanMeierFitter
    from lifelines.statistics import logrank_test

    duration_c, event_c = params["duration"], params["event"]
    group_c = params.get("group")
    buckets: dict[str, tuple[list[float], list[int]]] = {}
    for r in rows:
        d, e = r.get(duration_c), r.get(event_c)
        if d is None or e is None:
            continue
        df = _to_float(duration_c, d)
        if math.isnan(df) or df < 0:
            continue
        ef = _to_float(event_c, e)
        ei = int(ef)
        if ei not in (0, 1):
            raise GuardError(
                "stat_bad_value",
                f"event column {event_c!r} must be 0 or 1, got {e!r}",
                retryable=False,
            )
        key = str(r.get(group_c)) if group_c else "all"
        ds, es = buckets.setdefault(key, ([], []))
        ds.append(df)
        es.append(ei)

    if not buckets or all(len(ds) < 2 for ds, _ in buckets.values()):
        raise GuardError("stat_insufficient_n", "not enough survival observations", retryable=False)
    if len(buckets) > _MAX_GROUPS:
        raise GuardError(
            "stat_group_count", f"too many groups ({len(buckets)} > {_MAX_GROUPS})", retryable=False
        )

    kmf = KaplanMeierFitter()
    out_groups: list[dict[str, object]] = []
    for label, (ds, es) in sorted(buckets.items()):
        kmf.fit(ds, event_observed=es)
        med = kmf.median_survival_time_
        out_groups.append(
            {
                "label": label,
                "n": len(ds),
                "median_survival": None if med is None or math.isinf(med) else float(med),
            }
        )

    stats: dict[str, float] = {}
    caveats = ["Kaplan-Meier survival; event=1 means observed, event=0 means censored."]
    if group_c and len(buckets) == 2:
        (_, (d1, e1)), (_, (d2, e2)) = sorted(buckets.items())
        lr = logrank_test(d1, d2, event_observed_A=e1, event_observed_B=e2)
        stats["logrank_statistic"] = float(lr.test_statistic)
        stats["p_value"] = float(lr.p_value)
    elif group_c and len(buckets) > 2:
        caveats.append(
            "Log-rank test is reported only for exactly 2 groups; medians shown for all."
        )
    return StatResult(test="kaplan_meier", stats=stats, groups=out_groups, caveats=caveats)


def mann_whitney_u(rows, params) -> StatResult:
    from scipy import stats as _stats

    groups = _group_values(rows, params["value"], params["group"])
    if len(groups) != 2:
        raise GuardError(
            "stat_group_count",
            f"Mann-Whitney needs exactly 2 groups, got {len(groups)}",
            retryable=False,
        )
    (l1, v1), (l2, v2) = sorted(groups.items())
    if len(v1) < 2 or len(v2) < 2:
        raise GuardError(
            "stat_insufficient_n", "each group needs at least 2 values", retryable=False
        )
    alpha = float(params.get("alpha", 0.05))
    u, p = _stats.mannwhitneyu(v1, v2, alternative="two-sided")
    caveats = [
        "Mann-Whitney U (non-parametric); makes no normality assumption.",
        "Tests whether one group's values are stochastically shifted vs the other.",
        _significance(float(p), alpha),
    ]
    return StatResult(
        test="mann_whitney_u",
        stats={"u": float(u), "p_value": float(p)},
        groups=[
            {"label": l1, "n": len(v1), "median": median(v1)},
            {"label": l2, "n": len(v2), "median": median(v2)},
        ],
        caveats=caveats,
    )


def tukey_hsd(rows, params) -> StatResult:
    from scipy import stats as _stats

    groups = _group_values(rows, params["value"], params["group"])
    if len(groups) < 2:
        raise GuardError(
            "stat_group_count", f"Tukey needs at least 2 groups, got {len(groups)}", retryable=False
        )
    if len(groups) > _MAX_GROUPS:
        raise GuardError(
            "stat_group_count", f"too many groups ({len(groups)} > {_MAX_GROUPS})", retryable=False
        )
    for label, vals in groups.items():
        if len(vals) < 2:
            raise GuardError(
                "stat_insufficient_n", f"group {label!r} needs at least 2 values", retryable=False
            )
    labels = sorted(groups)
    res = _stats.tukey_hsd(*[groups[lbl] for lbl in labels])
    stats: dict[str, float] = {}
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            stats[f"{labels[i]} vs {labels[j]} p"] = float(res.pvalue[i, j])
    caveats = [
        "Tukey HSD post-hoc pairwise comparison; family-wise error rate controlled.",
        "Intended after a significant one-way ANOVA.",
    ]
    return StatResult(
        test="tukey_hsd",
        stats=stats,
        groups=[
            {"label": lbl, "n": len(groups[lbl]), "mean": fmean(groups[lbl])} for lbl in labels
        ],
        caveats=caveats,
    )


def _paired_values(rows, x_col: str, y_col: str) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        xv, yv = r.get(x_col), r.get(y_col)
        if xv is None or yv is None:
            continue
        fx, fy = _to_float(x_col, xv), _to_float(y_col, yv)
        if math.isnan(fx) or math.isnan(fy):
            continue
        xs.append(fx)
        ys.append(fy)
    return xs, ys


def _column_values(rows, col: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        v = r.get(col)
        if v is None:
            continue
        f = _to_float(col, v)
        if math.isnan(f):
            continue
        out.append(f)
    return out


def kruskal_wallis(rows, params) -> StatResult:
    from scipy import stats as _stats

    groups = _group_values(rows, params["value"], params["group"])
    if len(groups) < 2:
        raise GuardError(
            "stat_group_count",
            f"Kruskal-Wallis needs at least 2 groups, got {len(groups)}",
            retryable=False,
        )
    for label, vals in groups.items():
        if len(vals) < 2:
            raise GuardError(
                "stat_insufficient_n", f"group {label!r} needs at least 2 values", retryable=False
            )
    h, p = _stats.kruskal(*groups.values())
    caveats = [
        "Kruskal-Wallis (non-parametric one-way ANOVA); rank-based, no normality assumption.",
        _significance(float(p), 0.05),
    ]
    return StatResult(
        test="kruskal_wallis",
        stats={"h": float(h), "p_value": float(p)},
        groups=[
            {"label": lbl, "n": len(groups[lbl]), "median": median(groups[lbl])}
            for lbl in sorted(groups)
        ],
        caveats=caveats,
    )


def spearman_correlation(rows, params) -> StatResult:
    from scipy import stats as _stats

    xs, ys = _paired_values(rows, params["x"], params["y"])
    if len(xs) < 3:
        raise GuardError("stat_insufficient_n", "need at least 3 paired points", retryable=False)
    res = _stats.spearmanr(xs, ys)
    p = float(res.pvalue)
    caveats = [
        "Spearman rank correlation (monotonic association).",
        _significance(p, 0.05),
    ]
    return StatResult(
        test="spearman_correlation",
        stats={"rho": float(res.statistic), "p_value": p, "n": float(len(xs))},
        groups=[],
        caveats=caveats,
    )


def pearson_correlation(rows, params) -> StatResult:
    from scipy import stats as _stats

    xs, ys = _paired_values(rows, params["x"], params["y"])
    if len(xs) < 3:
        raise GuardError("stat_insufficient_n", "need at least 3 paired points", retryable=False)
    res = _stats.pearsonr(xs, ys)
    p = float(res.pvalue)
    caveats = [
        "Pearson linear correlation; sensitive to outliers; assumes roughly bivariate-normal.",
        _significance(p, 0.05),
    ]
    return StatResult(
        test="pearson_correlation",
        stats={"r": float(res.statistic), "p_value": p, "n": float(len(xs))},
        groups=[],
        caveats=caveats,
    )


def two_way_anova(rows, params) -> StatResult:
    import pandas as pd
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm

    v, f1, f2 = params["value"], params["factor1"], params["factor2"]
    recs = []
    for r in rows:
        val, a, b = r.get(v), r.get(f1), r.get(f2)
        if val is None or a is None or b is None:
            continue
        fv = _to_float(v, val)
        if math.isnan(fv):
            continue
        recs.append({"y": fv, "a": str(a), "b": str(b)})
    if len(recs) < 4:
        raise GuardError("stat_insufficient_n", "two-way ANOVA needs more rows", retryable=False)
    df = pd.DataFrame(recs)
    if df["a"].nunique() < 2 or df["b"].nunique() < 2:
        raise GuardError("stat_group_count", "each factor needs at least 2 levels", retryable=False)
    ncells = df.groupby(["a", "b"], observed=True).ngroups
    if ncells > _MAX_GROUPS:
        raise GuardError("stat_group_count", f"too many cells ({ncells})", retryable=False)
    try:
        model = smf.ols("y ~ C(a) + C(b) + C(a):C(b)", data=df).fit()
        table = anova_lm(model, typ=2)
    except Exception as e:  # singular design / unfittable
        raise GuardError("stat_fit_error", str(e).strip()[:200], retryable=False) from e

    def _fp(name: str) -> tuple[float, float]:
        return float(table.loc[name, "F"]), float(table.loc[name, "PR(>F)"])

    f1_F, f1_p = _fp("C(a)")
    f2_F, f2_p = _fp("C(b)")
    i_F, i_p = _fp("C(a):C(b)")
    groups = [
        {"factor1": a, "factor2": b, "n": int(len(g)), "mean": float(g["y"].mean())}
        for (a, b), g in df.groupby(["a", "b"], observed=True)
    ]
    caveats = [
        "Two-way ANOVA (type II sums of squares).",
        "Assumes normal residuals and homogeneous variances across cells.",
    ]
    return StatResult(
        test="two_way_anova",
        stats={
            "factor1_F": f1_F,
            "factor1_p": f1_p,
            "factor2_F": f2_F,
            "factor2_p": f2_p,
            "interaction_F": i_F,
            "interaction_p": i_p,
        },
        groups=groups,
        caveats=caveats,
    )


def cox_ph(rows, params) -> StatResult:
    import pandas as pd
    from lifelines import CoxPHFitter

    dur, ev = params["duration"], params["event"]
    covariates = params["covariates"]
    recs = []
    for r in rows:
        d, e = r.get(dur), r.get(ev)
        if d is None or e is None:
            continue
        df_dur = _to_float(dur, d)
        if math.isnan(df_dur) or df_dur < 0:
            continue
        ei = int(_to_float(ev, e))
        if ei not in (0, 1):
            raise GuardError(
                "stat_bad_value", f"event column {ev!r} must be 0 or 1, got {e!r}", retryable=False
            )
        rec = {"_duration": df_dur, "_event": ei}
        ok = True
        for c in covariates:
            cv = r.get(c)
            if cv is None:
                ok = False
                break
            fcv = _to_float(c, cv)
            if math.isnan(fcv):
                ok = False
                break
            rec[c] = fcv
        if ok:
            recs.append(rec)
    n_events = sum(r["_event"] for r in recs)
    if len(recs) < 3 or n_events < 2:
        raise GuardError(
            "stat_insufficient_n",
            "not enough survival observations/events for Cox",
            retryable=False,
        )
    df = pd.DataFrame(recs)
    try:
        cph = CoxPHFitter()
        cph.fit(df, duration_col="_duration", event_col="_event")
    except Exception as e:  # singular / non-converging fit
        raise GuardError("stat_fit_error", str(e).strip()[:200], retryable=False) from e
    stats: dict[str, float] = {}
    for c in covariates:
        stats[f"{c} hazard_ratio"] = float(cph.hazard_ratios_[c])
        stats[f"{c} p"] = float(cph.summary.loc[c, "p"])
    caveats = [
        "Cox proportional-hazards regression; event=1 observed, event=0 censored.",
        "Assumes proportional hazards; needs enough events per covariate (rule of thumb >=10).",
    ]
    return StatResult(
        test="cox_ph",
        stats=stats,
        groups=[{"label": "all", "n": len(df)}],
        caveats=caveats,
    )
