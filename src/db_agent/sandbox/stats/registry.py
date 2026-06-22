"""The frozen allowlist of vetted tests. Dispatch is only ever through this dict."""

from __future__ import annotations

from db_agent.sandbox.stats.functions import kaplan_meier, one_way_anova, welch_t_test
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
    )
}


def catalog_text() -> str:
    lines = []
    for t in REGISTRY.values():
        ps = ", ".join(
            f"{n} ({'column' if s.role == 'column' else s.py_type.__name__}"
            f"{'' if s.required else ', optional'})"
            for n, s in t.params.items()
        )
        lines.append(f"- {t.name}: {t.description} Params: {ps}")
    return "\n".join(lines)
