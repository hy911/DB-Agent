"""Hand-written, audited statistical tests. Each takes the result rows + validated
params and returns a StatResult. scipy/lifelines are imported lazily so importing
this module (e.g. via the registry at graph build time) stays cheap and offline."""

from __future__ import annotations

import math
from statistics import fmean

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
        groups=[{"label": l, "n": len(v), "mean": fmean(v)} for l, v in sorted(groups.items())],
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
