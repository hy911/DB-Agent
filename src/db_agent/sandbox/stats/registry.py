"""The frozen allowlist of vetted tests. Dispatch is only ever through this dict."""

from __future__ import annotations

from db_agent.sandbox.stats.functions import (
    cox_ph,
    kaplan_meier,
    kruskal_wallis,
    mann_whitney_u,
    one_way_anova,
    pearson_correlation,
    spearman_correlation,
    tukey_hsd,
    two_way_anova,
    welch_t_test,
)
from db_agent.sandbox.stats.spec import ParamSpec, StatTest

REGISTRY: dict[str, StatTest] = {
    t.name: t
    for t in (
        StatTest(
            "welch_t_test",
            "Compare the mean of a numeric value between exactly two groups (Welch's t-test).",
            {
                "value": ParamSpec("column"),
                "group": ParamSpec("column"),
                "alpha": ParamSpec("scalar", required=False, py_type=float, bounds=(0.0, 1.0)),
            },
            welch_t_test,
        ),
        StatTest(
            "one_way_anova",
            "Compare the mean of a numeric value across two or more groups (one-way ANOVA).",
            {
                "value": ParamSpec("column"),
                "group": ParamSpec("column"),
                "alpha": ParamSpec("scalar", required=False, py_type=float, bounds=(0.0, 1.0)),
            },
            one_way_anova,
        ),
        StatTest(
            "kaplan_meier",
            (
                "Kaplan-Meier survival: per-group median survival and, for exactly two "
                "groups, a log-rank test. duration=time-to-event, event=1 observed/0 censored."
            ),
            {
                "duration": ParamSpec("column"),
                "event": ParamSpec("column"),
                "group": ParamSpec("column", required=False),
            },
            kaplan_meier,
        ),
        StatTest(
            "mann_whitney_u",
            "Non-parametric comparison of a numeric value between exactly two groups "
            "(Mann-Whitney U); use when normality is doubtful.",
            {
                "value": ParamSpec("column"),
                "group": ParamSpec("column"),
                "alpha": ParamSpec("scalar", required=False, py_type=float, bounds=(0.0, 1.0)),
            },
            mann_whitney_u,
        ),
        StatTest(
            "tukey_hsd",
            "Tukey HSD post-hoc pairwise comparison of a numeric value across groups, "
            "run after a significant one-way ANOVA.",
            {
                "value": ParamSpec("column"),
                "group": ParamSpec("column"),
            },
            tukey_hsd,
        ),
        StatTest(
            "two_way_anova",
            "Two-way ANOVA of a numeric value across two categorical factors and their "
            "interaction.",
            {
                "value": ParamSpec("column"),
                "factor1": ParamSpec("column"),
                "factor2": ParamSpec("column"),
            },
            two_way_anova,
        ),
        StatTest(
            "cox_ph",
            "Cox proportional-hazards regression: effect of one or more covariates on "
            "survival. duration=time-to-event, event=1 observed/0 censored, "
            "covariates=numeric columns.",
            {
                "duration": ParamSpec("column"),
                "event": ParamSpec("column"),
                "covariates": ParamSpec("columns"),
            },
            cox_ph,
        ),
        StatTest(
            "kruskal_wallis",
            "Non-parametric one-way ANOVA: compare a numeric value across two or more "
            "groups (Kruskal-Wallis); use when normality is doubtful.",
            {"value": ParamSpec("column"), "group": ParamSpec("column")},
            kruskal_wallis,
        ),
        StatTest(
            "spearman_correlation",
            "Spearman rank correlation (monotonic association) between two numeric columns.",
            {"x": ParamSpec("column"), "y": ParamSpec("column")},
            spearman_correlation,
        ),
        StatTest(
            "pearson_correlation",
            "Pearson linear correlation between two numeric columns.",
            {"x": ParamSpec("column"), "y": ParamSpec("column")},
            pearson_correlation,
        ),
    )
}


def _role_label(spec: ParamSpec) -> str:
    if spec.role == "column":
        return "column"
    if spec.role == "columns":
        return "columns"
    return spec.py_type.__name__ if spec.py_type is not None else "scalar"


def catalog_text() -> str:
    lines = []
    for t in REGISTRY.values():
        ps = ", ".join(
            f"{n} ({_role_label(s)}{'' if s.required else ', optional'})"
            for n, s in t.params.items()
        )
        lines.append(f"- {t.name}: {t.description} Params: {ps}")
    return "\n".join(lines)
