# Stats Sandbox Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add controlled statistical inference (Welch t-test / one-way ANOVA /
Kaplan-Meier + log-rank) over an already-fetched, permission-filtered result set via
a vetted function registry, run as a `stats` graph node after the Phase 1 `analyze`
(DuckDB reshape) node.

**Architecture:** A new pure subpackage `src/db_agent/sandbox/stats/` holds a frozen
registry of vetted statistical functions, a deterministic validator, and a `run_stat`
entry point. The LLM emits only a structured `{function, params}` JSON request
(data, never code); the validator checks it against the registry and the table's
columns, then a hand-written impl calls scipy/lifelines. A new `stats_node` wires it
into the graph between `analyze` and `answer`, fail-soft (any error degrades to the
descriptive answer). Mirrors the Phase 1 DuckDB sandbox boundary and DI pattern.

**Tech Stack:** Python 3.12+ (runs on 3.14), scipy, lifelines, sqlglot (unchanged),
LangGraph, pytest, ruff, uv.

**Reference spec:** `docs/superpowers/specs/2026-06-22-stats-sandbox-phase2-design.md`

---

## File Structure

**Create:**
- `src/db_agent/sandbox/stats/__init__.py` — package exports.
- `src/db_agent/sandbox/stats/spec.py` — `ParamSpec`, `StatTest`, `StatResult`,
  `ValidatedStatRequest` dataclasses (no library imports; pure types).
- `src/db_agent/sandbox/stats/functions.py` — the three vetted impls
  (`welch_t_test`, `one_way_anova`, `kaplan_meier`) + private numeric helpers.
  scipy/lifelines imported lazily inside each function.
- `src/db_agent/sandbox/stats/registry.py` — `REGISTRY` dict + `catalog_text()`.
- `src/db_agent/sandbox/stats/validator.py` — `validate_stat_request`.
- `src/db_agent/sandbox/stats/runner.py` — `run_stat(columns, rows, request_str)`.
- `tests/test_stats_spec_import.py` — Task 1 dependency/import smoke test.
- `tests/test_stats_validator.py` — Task 2.
- `tests/test_stats_functions.py` — Task 3.
- `tests/test_stats_runner.py` — Task 3.
- `tests/test_llm_stats.py` — Task 4.

**Modify:**
- `pyproject.toml` — add `scipy`, `lifelines` runtime deps (Task 1).
- `src/db_agent/llm/prompts.py` — add `stat_messages`, `stat_answer_messages` (Task 4).
- `src/db_agent/llm/agent_llm.py` — add `request_stat`, `answer_stat`, `_format_stat` (Task 4).
- `src/db_agent/llm/__init__.py` — export `request_stat`, `answer_stat` (Task 4).
- `src/db_agent/graph/state.py` — state fields, `Deps.run_stat`, `AgentResult`,
  `initial_state`, `to_result` (Task 5).
- `src/db_agent/graph/nodes.py` — `stats_node`, `answer_node` update (Task 5).
- `src/db_agent/graph/build.py` — wire `stats` node, `run_agent(run_stat=...)` (Task 5).
- `src/db_agent/observability/record.py` — add `stat_request` (Task 6).
- `tests/test_graph_nodes.py` — stats node tests + answer-node stats test (Task 5).
- `tests/test_graph_chain.py` — append a `stats` NONE to answered-path scripts +
  a new stats chain test (Task 5).
- `tests/test_observability_integration.py` — append stats NONE; assert stat_request (Task 6).
- `tests/test_api_endpoint.py` — append stats NONE to answered-path scripts (Task 6).

---

## Task 1: Dependencies + import/compute smoke proof

Prove scipy + lifelines install and compute correct known values **before** building
on them (mirrors the Phase 1 lockdown-proof-first task).

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_stats_spec_import.py`

- [ ] **Step 1: Add the runtime dependencies**

In `pyproject.toml`, find the `dependencies = [` array (the runtime deps, not the
`[dependency-groups]`/dev extras) and add two entries:

```toml
    "scipy>=1.13",
    "lifelines>=0.29",
```

- [ ] **Step 2: Install**

Run: `uv sync --extra dev`
Expected: resolves and installs scipy + lifelines (and their transitive deps incl.
numpy, pandas, matplotlib); updates `uv.lock`. Exit 0.

- [ ] **Step 3: Write the smoke test**

```python
# tests/test_stats_spec_import.py
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
```

- [ ] **Step 4: Run the smoke test**

Run: `uv run pytest tests/test_stats_spec_import.py -v`
Expected: 3 passed. If scipy/lifelines fail to import or compute, STOP — the rest of
the plan depends on these libraries being available and correct.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_stats_spec_import.py
git commit -m "stats Phase 2 T1: add scipy+lifelines deps + compute smoke proof"
```

---

## Task 2: Spec dataclasses + registry skeleton + validator

Build the pure validation surface first (no scipy/lifelines needed). The key design
choice that keeps this task independently testable: `validate_stat_request` takes the
**registry as a parameter** rather than importing the global one. So Task 2 ships
`spec.py` + `validator.py` and tests the validator against a small **test-local**
registry; Task 3 then adds the real `functions.py` + `registry.py` and the `runner.py`
that passes the global `REGISTRY` in. No forward reference, no stubs.

**Files:**
- Create: `src/db_agent/sandbox/stats/__init__.py`
- Create: `src/db_agent/sandbox/stats/spec.py`
- Create: `src/db_agent/sandbox/stats/validator.py`
- Test: `tests/test_stats_validator.py`

- [ ] **Step 1: Write `spec.py`**

```python
# src/db_agent/sandbox/stats/spec.py
"""Pure types for the vetted statistical-test registry. No library imports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    role: str  # "column" | "scalar"
    required: bool = True
    py_type: type | None = None  # scalar only: int | float | bool
    bounds: tuple[float, float] | None = None  # scalar numeric: exclusive (lo, hi)
    choices: tuple[object, ...] | None = None  # scalar enum


@dataclass(frozen=True)
class StatResult:
    test: str
    stats: dict[str, float]
    groups: list[dict[str, object]]
    caveats: list[str]


@dataclass(frozen=True)
class StatTest:
    name: str
    description: str
    params: dict[str, ParamSpec]
    run: Callable[[list[dict[str, object]], dict[str, object]], StatResult]


@dataclass(frozen=True)
class ValidatedStatRequest:
    test: StatTest
    params: dict[str, object]
```

- [ ] **Step 2: Write `__init__.py` (exports grow as later tasks land)**

```python
# src/db_agent/sandbox/stats/__init__.py
"""Vetted statistical-inference registry over an in-memory result set.

The LLM emits only a structured {function, params} request (data, never code);
``validate_stat_request`` checks it against the frozen ``REGISTRY`` and the table's
columns; ``run_stat`` dispatches to a hand-written impl that calls scipy/lifelines.
"""

from __future__ import annotations

from db_agent.sandbox.stats.spec import (
    ParamSpec,
    StatResult,
    StatTest,
    ValidatedStatRequest,
)
from db_agent.sandbox.stats.validator import validate_stat_request

__all__ = [
    "ParamSpec",
    "StatResult",
    "StatTest",
    "ValidatedStatRequest",
    "validate_stat_request",
]
```

- [ ] **Step 3: Write `validator.py`**

```python
# src/db_agent/sandbox/stats/validator.py
"""Deterministic guard for a stat request: function in registry, params conform,
column refs exist, scalars in bounds. Fail closed (raise GuardError)."""

from __future__ import annotations

from collections.abc import Sequence

from db_agent.sandbox.stats.spec import StatTest, ValidatedStatRequest
from db_agent.sql.errors import GuardError


def validate_stat_request(
    request: object, available_columns: Sequence[str], registry: dict[str, StatTest]
) -> ValidatedStatRequest:
    if not isinstance(request, dict):
        raise GuardError("stat_bad_request", "request must be a JSON object", retryable=False)

    name = request.get("function")
    test = registry.get(name) if isinstance(name, str) else None
    if test is None:
        raise GuardError("stat_unknown_function", f"unknown function {name!r}", retryable=False)

    params = request.get("params", {})
    if not isinstance(params, dict):
        raise GuardError("stat_bad_request", "params must be a JSON object", retryable=False)

    unknown = set(params) - set(test.params)
    if unknown:
        raise GuardError("stat_unknown_param", f"unknown params {sorted(unknown)}", retryable=False)

    cols = set(available_columns)
    clean: dict[str, object] = {}
    for pname, spec in test.params.items():
        if pname not in params:
            if spec.required:
                raise GuardError(
                    "stat_missing_param", f"missing required param {pname!r}", retryable=False
                )
            continue
        val = params[pname]
        if spec.role == "column":
            if not isinstance(val, str) or val not in cols:
                raise GuardError(
                    "stat_bad_column",
                    f"param {pname!r}={val!r} is not a column of the result table",
                    retryable=False,
                )
        else:  # scalar
            _check_scalar(pname, val, spec)
        clean[pname] = val

    return ValidatedStatRequest(test=test, params=clean)


def _check_scalar(pname, val, spec) -> None:
    if spec.py_type is bool:
        if not isinstance(val, bool):
            raise GuardError("stat_bad_scalar", f"param {pname!r} must be a boolean", retryable=False)
    elif spec.py_type in (int, float):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise GuardError("stat_bad_scalar", f"param {pname!r} must be numeric", retryable=False)
        if spec.bounds is not None:
            lo, hi = spec.bounds
            if not (lo < float(val) < hi):
                raise GuardError(
                    "stat_bad_scalar",
                    f"param {pname!r}={val} out of range ({lo}, {hi})",
                    retryable=False,
                )
    if spec.choices is not None and val not in spec.choices:
        raise GuardError(
            "stat_bad_scalar", f"param {pname!r}={val!r} not in {spec.choices}", retryable=False
        )
```

- [ ] **Step 4: Write the failing tests**

```python
# tests/test_stats_validator.py
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_stats_validator.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/sandbox/stats/__init__.py src/db_agent/sandbox/stats/spec.py src/db_agent/sandbox/stats/validator.py tests/test_stats_validator.py
git commit -m "stats Phase 2 T2: spec types + deterministic request validator"
```

---

## Task 3: Vetted functions + registry + runner

**Files:**
- Create: `src/db_agent/sandbox/stats/functions.py`
- Create: `src/db_agent/sandbox/stats/registry.py`
- Create: `src/db_agent/sandbox/stats/runner.py`
- Modify: `src/db_agent/sandbox/stats/__init__.py`
- Test: `tests/test_stats_functions.py`, `tests/test_stats_runner.py`

- [ ] **Step 1: Write `functions.py`**

```python
# src/db_agent/sandbox/stats/functions.py
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
        raise GuardError("stat_insufficient_n", "each group needs at least 2 values", retryable=False)
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
                "stat_bad_value", f"event column {event_c!r} must be 0 or 1, got {e!r}", retryable=False
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
        caveats.append("Log-rank test is reported only for exactly 2 groups; medians shown for all.")
    return StatResult(test="kaplan_meier", stats=stats, groups=out_groups, caveats=caveats)
```

- [ ] **Step 2: Write `registry.py`**

```python
# src/db_agent/sandbox/stats/registry.py
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
```

- [ ] **Step 3: Write `runner.py`**

```python
# src/db_agent/sandbox/stats/runner.py
"""Public entry: parse the LLM's JSON request, validate it, dispatch to the impl.
Mirrors DuckDBSandbox.run — validation happens inside; the caller catches GuardError."""

from __future__ import annotations

import json

from db_agent.sandbox.stats.registry import REGISTRY
from db_agent.sandbox.stats.spec import StatResult
from db_agent.sandbox.stats.validator import validate_stat_request
from db_agent.sql.errors import GuardError


def run_stat(columns: list[str], rows: list[dict[str, object]], request_str: str) -> StatResult:
    try:
        request = json.loads(request_str)
    except (json.JSONDecodeError, TypeError) as e:
        raise GuardError("stat_parse_error", str(e).strip(), retryable=False) from e
    validated = validate_stat_request(request, columns, REGISTRY)
    return validated.test.run(rows, validated.params)
```

- [ ] **Step 4: Update `__init__.py` to export the runner + registry**

Replace the import/`__all__` block in `src/db_agent/sandbox/stats/__init__.py` with:

```python
from db_agent.sandbox.stats.registry import REGISTRY, catalog_text
from db_agent.sandbox.stats.runner import run_stat
from db_agent.sandbox.stats.spec import (
    ParamSpec,
    StatResult,
    StatTest,
    ValidatedStatRequest,
)
from db_agent.sandbox.stats.validator import validate_stat_request

__all__ = [
    "REGISTRY",
    "ParamSpec",
    "StatResult",
    "StatTest",
    "ValidatedStatRequest",
    "catalog_text",
    "run_stat",
    "validate_stat_request",
]
```

- [ ] **Step 5: Write the failing function tests**

```python
# tests/test_stats_functions.py
from __future__ import annotations

import pytest

from db_agent.sandbox.stats.functions import kaplan_meier, one_way_anova, welch_t_test
from db_agent.sql.errors import GuardError


def _tv_rows():
    return (
        [{"g": "ctrl", "v": x} for x in (10.0, 11.0, 12.0, 9.0)]
        + [{"g": "drug", "v": x} for x in (2.0, 3.0, 1.0, 4.0)]
    )


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
    rows = (
        [{"grp": "ctrl", "t": t, "e": 1} for t in (2.0, 3.0, 4.0)]
        + [{"grp": "drug", "t": t, "e": 1} for t in (8.0, 9.0, 10.0)]
    )
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
```

- [ ] **Step 6: Write the failing runner tests**

```python
# tests/test_stats_runner.py
from __future__ import annotations

import json

import pytest

from db_agent.sandbox.stats.runner import run_stat
from db_agent.sql.errors import GuardError


def _rows():
    return (
        [{"g": "ctrl", "v": x} for x in (10.0, 11.0, 12.0, 9.0)]
        + [{"g": "drug", "v": x} for x in (2.0, 3.0, 1.0, 4.0)]
    )


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
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_stats_functions.py tests/test_stats_runner.py -v`
Expected: 12 passed.

- [ ] **Step 8: Commit**

```bash
git add src/db_agent/sandbox/stats/functions.py src/db_agent/sandbox/stats/registry.py src/db_agent/sandbox/stats/runner.py src/db_agent/sandbox/stats/__init__.py tests/test_stats_functions.py tests/test_stats_runner.py
git commit -m "stats Phase 2 T3: vetted t-test/ANOVA/KM functions + registry + runner"
```

---

## Task 4: LLM tasks (request_stat / answer_stat) + prompts

**Files:**
- Modify: `src/db_agent/llm/prompts.py`
- Modify: `src/db_agent/llm/agent_llm.py`
- Modify: `src/db_agent/llm/__init__.py`
- Test: `tests/test_llm_stats.py`

- [ ] **Step 1: Add prompt builders to `prompts.py`**

Append to `src/db_agent/llm/prompts.py` (after `analysis_messages`):

```python
def stat_messages(
    question: str, columns: list[str], rows_preview: str, catalog: str
) -> list[dict[str, str]]:
    system = (
        "You decide whether answering the question needs a statistical test over an "
        "already-fetched result table named `result`. If so, pick ONE test from the "
        "catalog and map its parameters to the table's columns. Available tests:\n"
        f"{catalog}\n\n"
        "If a test is appropriate, reply with exactly one JSON object: "
        '{"function": <name>, "params": {<param>: <column-name-or-scalar>, ...}}. '
        "Map column-typed params to column names from the table; use only those "
        "columns. If no statistical test is needed, reply with the single word NONE. "
        "Reply with the JSON object or NONE and nothing else."
    )
    user = (
        f"Question: {question}\n\n"
        f"result columns: {', '.join(columns)}\n\n"
        f"Sample rows:\n{rows_preview}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def stat_answer_messages(
    question: str, sql: str, analysis_sql: str | None, stat_summary: str
) -> list[dict[str, str]]:
    system = (
        "You answer the user's question in natural language using a statistical test "
        "result. State the test used, the key statistic and p-value, the per-group "
        "figures, and clearly convey the caveats about assumptions. Be concise and "
        "factual; do not overstate significance."
    )
    reshape = f"\n\nReshape SQL:\n{analysis_sql}" if analysis_sql else ""
    user = (
        f"Question: {question}\n\nSQL run:\n{sql}{reshape}\n\n"
        f"Statistical test result:\n{stat_summary}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
```

- [ ] **Step 2: Add the LLM tasks to `agent_llm.py`**

In `src/db_agent/llm/agent_llm.py`, add an import near the top (after the existing
`from db_agent.llm import prompts`):

```python
from db_agent.sandbox.stats.spec import StatResult
```

Then append these functions (after `analyze_sql`):

```python
def request_stat(
    client: LLMClient,
    settings: Settings,
    question: str,
    columns: list[str],
    rows_preview: str,
    catalog: str,
) -> str:
    msgs = prompts.stat_messages(question, columns, rows_preview, catalog)
    return _strip_fences(client.complete(settings.model_sql, msgs)).strip()


def answer_stat(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    analysis_sql: str | None,
    stat: StatResult,
) -> str:
    summary = _format_stat(stat)
    return client.complete(
        settings.model_route, prompts.stat_answer_messages(question, sql, analysis_sql, summary)
    ).strip()


def _format_stat(stat: StatResult) -> str:
    lines = [f"Test: {stat.test}"]
    if stat.stats:
        lines.append("Statistics: " + ", ".join(f"{k}={v:.4g}" for k, v in stat.stats.items()))
    for g in stat.groups:
        lines.append("Group: " + ", ".join(f"{k}={v}" for k, v in g.items()))
    if stat.caveats:
        lines.append("Caveats: " + " ".join(stat.caveats))
    return "\n".join(lines)
```

Note: `request_stat` takes `rows_preview` (a string) and `catalog` (a string) rather
than the `QueryResult`, so the LLM layer keeps no dependency on the sandbox runtime
beyond the `StatResult` type. The node (Task 5) builds the preview via the existing
`_rows_preview` helper and passes `catalog_text()`.

- [ ] **Step 3: Export from `__init__.py`**

In `src/db_agent/llm/__init__.py`, add `answer_stat` and `request_stat` to both the
import block and `__all__` (keep alphabetical order within the existing list):

```python
from db_agent.llm.agent_llm import (
    RouteResult,
    analyze_sql,
    answer,
    answer_stat,
    extract_genes,
    generate_sql,
    request_stat,
    route,
)
```

and in `__all__` add `"answer_stat",` and `"request_stat",`.

- [ ] **Step 4: Write the failing tests**

```python
# tests/test_llm_stats.py
from __future__ import annotations

from db_agent.config import Settings
from db_agent.llm.agent_llm import answer_stat, request_stat
from db_agent.sandbox.stats.registry import catalog_text
from db_agent.sandbox.stats.spec import StatResult

SETTINGS = Settings(_env_file=None)


class _LLM:
    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}
        self.seen = []

    def complete(self, model, messages):
        self.seen.append((model, messages))
        return self.by_model[model].pop(0)


def test_request_stat_returns_json_string():
    llm = _LLM({"qwen-code": ['{"function": "welch_t_test", "params": {"value": "v", "group": "g"}}']})
    out = request_stat(llm, SETTINGS, "is it significant?", ["g", "v"], "g, v\nctrl, 1", catalog_text())
    assert "welch_t_test" in out
    assert llm.seen[0][0] == "qwen-code"


def test_request_stat_strips_fences():
    llm = _LLM({"qwen-code": ['```json\n{"function": "one_way_anova"}\n```']})
    out = request_stat(llm, SETTINGS, "q", ["g", "v"], "preview", catalog_text())
    assert out.startswith("{")
    assert "```" not in out


def test_request_stat_none():
    llm = _LLM({"qwen-code": ["NONE"]})
    assert request_stat(llm, SETTINGS, "q", ["g"], "p", catalog_text()) == "NONE"


def test_answer_stat_formats_and_routes():
    stat = StatResult(
        test="welch_t_test",
        stats={"t": -3.5, "p_value": 0.01, "mean_difference": -7.0},
        groups=[{"label": "ctrl", "n": 4, "mean": 10.5}, {"label": "drug", "n": 4, "mean": 2.5}],
        caveats=["Welch's t-test.", "Result is significant at alpha=0.05 (p=0.01)."],
    )
    llm = _LLM({"qwen-main": ["The difference is significant (p=0.01)."]})
    out = answer_stat(llm, SETTINGS, "significant?", "SELECT ...", "SELECT ... FROM result", stat)
    assert out == "The difference is significant (p=0.01)."
    assert llm.seen[0][0] == "qwen-main"
    # the prompt carried the formatted summary
    user_msg = llm.seen[0][1][1]["content"]
    assert "welch_t_test" in user_msg
    assert "p_value" in user_msg
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_llm_stats.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/llm/prompts.py src/db_agent/llm/agent_llm.py src/db_agent/llm/__init__.py tests/test_llm_stats.py
git commit -m "stats Phase 2 T4: request_stat/answer_stat LLM tasks + prompts"
```

---

## Task 5: Graph wiring — state, stats_node, answer_node, build

**Files:**
- Modify: `src/db_agent/graph/state.py`
- Modify: `src/db_agent/graph/nodes.py`
- Modify: `src/db_agent/graph/build.py`
- Test: `tests/test_graph_nodes.py`, `tests/test_graph_chain.py`

- [ ] **Step 1: Extend `state.py`**

In `src/db_agent/graph/state.py`:

Add the default-runner import + binding near the existing sandbox import (after
`from db_agent.sandbox.engine import DuckDBSandbox`):

```python
from db_agent.sandbox.stats import StatResult, run_stat as _default_run_stat
```

and after `_default_run_sandbox = DuckDBSandbox().run` add nothing (run_stat is
already a function, used directly as the default).

In `AgentState` (after `analysis_sql: str | None`):

```python
    stat_result: StatResult | None
    stat_request: str | None
```

In `initial_state` (after `analysis_sql=None,`):

```python
        stat_result=None,
        stat_request=None,
```

In `AgentResult` (after `analysis_sql: str | None`):

```python
    stat_request: str | None
```

In `to_result` (after `analysis_sql=state.get("analysis_sql"),`):

```python
        stat_request=state.get("stat_request"),
```

In `Deps` (after the `run_sandbox` field):

```python
    run_stat: Callable[[list[str], list[dict[str, object]], str], StatResult] = _default_run_stat
```

- [ ] **Step 2: Add `stats_node` and update `answer_node` in `nodes.py`**

In `src/db_agent/graph/nodes.py`, add imports (after the existing `from db_agent.llm`
imports):

```python
from db_agent.llm import answer_stat as llm_answer_stat
from db_agent.llm import request_stat as llm_request_stat
from db_agent.llm.agent_llm import _rows_preview
from db_agent.sandbox.stats import catalog_text
```

Add the new node (after `analyze_node`):

```python
def stats_node(state: AgentState, deps: Deps) -> dict:
    table = state.get("analysis")
    if table is None:
        table = state.get("result")
    if table is None or table.rowcount == 0:
        return {}
    req = llm_request_stat(
        deps.llm, deps.settings, state["question"], table.columns, _rows_preview(table), catalog_text()
    )
    if not req or req.strip().upper() == "NONE":
        return {}
    try:
        stat = deps.run_stat(table.columns, table.rows, req)
    except GuardError:
        return {}  # fail-soft: stats are additive; degrade to the descriptive answer
    return {"stat_result": stat, "stat_request": req}
```

Replace `answer_node` with the stats-aware version:

```python
def answer_node(state: AgentState, deps: Deps) -> dict:
    stat = state.get("stat_result")
    if stat is not None:
        text = llm_answer_stat(
            deps.llm,
            deps.settings,
            state["question"],
            state["secured_sql"],
            state.get("analysis_sql"),
            stat,
        )
        return {"answer": text, "status": "answered"}
    analysis = state.get("analysis")
    if analysis is not None:
        text = llm_answer(
            deps.llm, deps.settings, state["question"], state["analysis_sql"], analysis
        )
    else:
        text = llm_answer(
            deps.llm, deps.settings, state["question"], state["secured_sql"], state["result"]
        )
    return {"answer": text, "status": "answered"}
```

- [ ] **Step 3: Wire the node in `build.py`**

In `src/db_agent/graph/build.py`:

Add the import (after `from db_agent.db.result import QueryResult`):

```python
from db_agent.sandbox.stats import StatResult
```

Register the node (after the `analyze` node line):

```python
    g.add_node("stats", partial(nodes.stats_node, deps=deps))
```

Replace `g.add_edge("analyze", "answer")` with:

```python
    g.add_edge("analyze", "stats")
    g.add_edge("stats", "answer")
```

Add the `run_stat` override to `run_agent`'s signature (after the `run_sandbox`
param):

```python
    run_stat: Callable[[list[str], list[dict[str, object]], str], StatResult] | None = None,
```

and thread it into `deps_kwargs` (after the `run_sandbox` block):

```python
    if run_stat is not None:
        deps_kwargs["run_stat"] = run_stat
```

- [ ] **Step 4: Write the failing node tests**

Append to `tests/test_graph_nodes.py`. First add the imports at the top (extend the
existing `from db_agent.graph.nodes import (...)` block) with `stats_node`. Then add:

```python
def test_stats_node_runs_when_request_returned():
    from db_agent.sandbox.stats.spec import StatResult

    stat = StatResult(test="welch_t_test", stats={"p_value": 0.01}, groups=[], caveats=[])

    def fake_run_stat(columns, rows, req):
        assert columns == ["group_id", "tv"]
        assert "welch_t_test" in req
        return stat

    deps = _deps(
        llm=_LLM({"qwen-code": ['{"function": "welch_t_test", "params": {"value": "tv", "group": "group_id"}}']})
    )
    object.__setattr__(deps, "run_stat", fake_run_stat)
    s = initial_state("is tv different by group?")
    s["result"] = _qr_rows()
    out = stats_node(s, deps)
    assert out["stat_result"] is stat
    assert "welch_t_test" in out["stat_request"]


def test_stats_node_prefers_analysis_table():
    from db_agent.sandbox.stats.spec import StatResult

    analysis = QueryResult(
        columns=["grp", "val"],
        rows=[{"grp": "A", "val": 1.0}],
        rowcount=1,
        truncated=False,
        sql="SELECT grp, val FROM result",
        elapsed_ms=0.0,
    )
    seen = {}

    def fake_run_stat(columns, rows, req):
        seen["columns"] = columns
        return StatResult(test="t", stats={}, groups=[], caveats=[])

    deps = _deps(llm=_LLM({"qwen-code": ['{"function": "welch_t_test", "params": {}}']}))
    object.__setattr__(deps, "run_stat", fake_run_stat)
    s = initial_state("q")
    s["result"] = _qr_rows()
    s["analysis"] = analysis
    stats_node(s, deps)
    assert seen["columns"] == ["grp", "val"]  # used the analysis table, not raw result


def test_stats_node_none_passes_through():
    deps = _deps(llm=_LLM({"qwen-code": ["NONE"]}))
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert stats_node(s, deps) == {}


def test_stats_node_empty_table_skips_llm():
    empty = QueryResult(columns=["x"], rows=[], rowcount=0, truncated=False, sql="s", elapsed_ms=0.0)
    deps = _deps(llm=_LLM({}))  # no scripted response -> must not be called
    s = initial_state("q")
    s["result"] = empty
    assert stats_node(s, deps) == {}


def test_stats_node_guard_error_degrades():
    def boom(columns, rows, req):
        raise GuardError("stat_unknown_function", "nope", retryable=False)

    deps = _deps(llm=_LLM({"qwen-code": ['{"function": "nope"}']}))
    object.__setattr__(deps, "run_stat", boom)
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert stats_node(s, deps) == {}


def test_answer_node_uses_stat_result_when_present():
    from db_agent.sandbox.stats.spec import StatResult

    stat = StatResult(
        test="welch_t_test",
        stats={"p_value": 0.01},
        groups=[{"label": "A", "n": 4, "mean": 1.0}],
        caveats=["Welch's t-test."],
    )
    deps = _deps(llm=_LLM({"qwen-main": ["Significant difference (p=0.01)."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT group_id, tv FROM t"
    s["analysis_sql"] = "SELECT group_id, tv FROM result"
    s["result"] = _qr_rows()
    s["stat_result"] = stat
    out = answer_node(s, deps)
    assert out["answer"] == "Significant difference (p=0.01)."
    assert out["status"] == "answered"
```

- [ ] **Step 5: Run the node tests**

Run: `uv run pytest tests/test_graph_nodes.py -v`
Expected: all pass (existing + 6 new). If `test_after_guard_and_execute_dispatch`
fails, it should not — `after_execute` still returns `"analyze"`, unchanged.

- [ ] **Step 6: Fix the chain tests (new `stats` pass-through) + add a stats chain test**

In `tests/test_graph_chain.py`, every **answered** path now runs `analyze` AND
`stats`, both calling the model on `qwen-code`. The existing scripts already end each
`qwen-code` list with one `"NONE"` (the analyze pass-through). Append a **second**
`"NONE"` (the stats pass-through) to each of these tests' `qwen-code` lists:
`test_happy_path`, `test_self_correction_then_success`,
`test_expression_end_to_end_resolves_gene_and_injects`,
`test_mutation_end_to_end_resolves_gene`, `test_modeling_end_to_end_injects_permission`.

Example — `test_happy_path` becomes:

```python
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
```

For `test_self_correction_then_success` the list becomes:

```python
            "qwen-code": [
                "SELECT bad_col FROM model_efficacy_info",
                "SELECT drug_name FROM model_efficacy_info",
                "NONE",
                "NONE",
            ],
```

For `test_analysis_end_to_end_runs_sandbox`, the analyze step returns SQL (not NONE),
so append a single `"NONE"` for the stats step:

```python
            "qwen-code": [
                "SELECT drug_name, tgi_tv FROM model_efficacy_info",  # generate_sql
                "SELECT drug_name, avg(tgi_tv) AS m FROM result GROUP BY drug_name",  # analyze
                "NONE",  # stats: no test
            ],
```

(`test_retry_budget_exhausted`, `test_clarification_short_circuits`,
`test_fatal_guarderror_no_retry`, `test_expression_unknown_gene_clarifies` never
reach `stats` — leave them unchanged.)

Then add a new end-to-end stats test:

```python
def test_stats_end_to_end_runs_test():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT group_id, tgi_tv FROM model_efficacy_info",  # generate_sql
                "NONE",  # analyze: no reshape
                '{"function": "welch_t_test", "params": {"value": "tgi_tv", "group": "group_id"}}',
            ],
            "qwen-main": ["The two groups differ significantly (p<0.05)."],
        }
    )
    raw = QueryResult(
        columns=["group_id", "tgi_tv"],
        rows=[{"group_id": "A", "tgi_tv": v} for v in (10.0, 11.0, 12.0, 9.0)]
        + [{"group_id": "B", "tgi_tv": v} for v in (2.0, 3.0, 1.0, 4.0)],
        rowcount=8,
        truncated=False,
        sql="SELECT group_id, tgi_tv",
        elapsed_ms=1.0,
    )
    res = _run(llm, _Replica([raw]), question="is the TGI difference between groups significant?")
    assert res.status == "answered"
    assert res.answer == "The two groups differ significantly (p<0.05)."
    assert res.stat_request is not None and "welch_t_test" in res.stat_request
```

This test uses the **real** `run_stat` (no `run_stat` override), exercising scipy via
the registry end-to-end through the graph.

- [ ] **Step 7: Run the chain tests**

Run: `uv run pytest tests/test_graph_chain.py -v`
Expected: all pass (existing updated + 1 new).

- [ ] **Step 8: Commit**

```bash
git add src/db_agent/graph/state.py src/db_agent/graph/nodes.py src/db_agent/graph/build.py tests/test_graph_nodes.py tests/test_graph_chain.py
git commit -m "stats Phase 2 T5: stats_node wired between analyze and answer"
```

---

## Task 6: Observability + full suite + ruff + live e2e + security review

**Files:**
- Modify: `src/db_agent/observability/record.py`
- Modify: `tests/test_observability_integration.py`
- Modify: `tests/test_api_endpoint.py`

- [ ] **Step 1: Add `stat_request` to `RunRecord`**

In `src/db_agent/observability/record.py`:

In the `RunRecord` dataclass, after `analysis_sql: str | None`:

```python
    stat_request: str | None
```

In `from_state`, after `analysis_sql=state.get("analysis_sql"),`:

```python
            stat_request=state.get("stat_request"),
```

- [ ] **Step 2: Fix observability + api answered-path scripts**

In `tests/test_observability_integration.py`, update `_happy_llm`'s `qwen-code` list
to append a second `"NONE"` (analyze + stats pass-through):

```python
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
```

In `tests/test_api_endpoint.py`, do the same for the answered-path tests
`test_query_answered_includes_rows` and `test_query_invokes_observer` (append a
second `"NONE"`):

```python
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
```

(`test_query_fatal_guard_error_is_200_error` fails at `execute` before reaching
`analyze`/`stats`, so its script is never fully consumed — leave it as is.)

- [ ] **Step 3: Add an observability assertion for stat_request**

Append to `tests/test_observability_integration.py`:

```python
def test_record_captures_stat_request():
    records: list[RunRecord] = []
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT group_id, tgi_tv FROM model_efficacy_info",
                "NONE",  # analyze
                '{"function": "one_way_anova", "params": {"value": "tgi_tv", "group": "group_id"}}',
            ],
            "qwen-main": ["Groups differ."],
        }
    )
    raw = QueryResult(
        columns=["group_id", "tgi_tv"],
        rows=[{"group_id": g, "tgi_tv": v} for g, v in
              [("A", 1.0), ("A", 2.0), ("B", 5.0), ("B", 6.0), ("C", 9.0), ("C", 10.0)]],
        rowcount=6,
        truncated=False,
        sql="SELECT group_id, tgi_tv",
        elapsed_ms=1.0,
    )
    run_agent(
        "do groups differ?",
        llm=llm,
        replica=_Replica([raw]),
        layer=LAYER,
        settings=SETTINGS,
        observer=records.append,
    )
    assert len(records) == 1
    assert records[0].stat_request is not None
    assert "one_way_anova" in records[0].stat_request
```

- [ ] **Step 4: Run the full offline suite**

Run: `uv run pytest`
Expected: all pass, integration deselected. No failures from the new `stats` step.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check src tests && uv run ruff format src tests`
Expected: no errors; formatting clean (commit any reformatting).

- [ ] **Step 6: Commit the offline-complete state**

```bash
git add src/db_agent/observability/record.py tests/test_observability_integration.py tests/test_api_endpoint.py
git commit -m "stats Phase 2 T6: observability stat_request + suite/ruff green"
```

- [ ] **Step 7: Security review (the mandatory gate — allowed subagent exception)**

Dispatch the `sql-security-reviewer` subagent over the new stats surface
(`src/db_agent/sandbox/stats/`) and the LLM stat prompt, with this framing: verify
(1) the LLM never supplies executable code — only a `{function, params}` request
parsed as data; (2) dispatch is solely through `REGISTRY` (no string-keyed dynamic
import); (3) `validate_stat_request` fail-closes on unknown function, missing/extra
params, column-not-in-table, and out-of-bounds scalars; (4) the stats step sees only
already-permission-filtered rows and holds no DSN/credentials; (5) fail-soft —
`stats_node` degrades on any `GuardError`. Address any high-confidence findings, then
re-run `uv run pytest` and re-commit if changed.

- [ ] **Step 8: Live end-to-end (real LLM + scipy/lifelines)**

Run a live query through `POST /query` (needs `.env` DSN + gateway), e.g.:
"is the day-21 tumor volume difference between the treated and control efficacy
groups for model X statistically significant?"
Expected: the replica fetches for_bd-filtered rows, the answer reports the test name,
t/p, per-group means + n, and the assumption caveats. Record the replica SQL +
analysis SQL (if any) + stat request + answer. If the gateway returns transient 504s
(the known deferred retry/backoff gap), note it; the deterministic stats path
(validator + registry + runner) is already proven by the offline suite.

- [ ] **Step 9: Final commit (if the live run surfaced any doc/code tweaks)**

```bash
git add -A
git commit -m "stats Phase 2 T6: live e2e verified + security review addressed"
git push -u origin main
```

---

## Notes for the implementer

- **DI / offline-test contract:** `run_agent(..., run_stat=fake)` overrides the real
  runner exactly like `run_sandbox=` / `resolve_gene=`. Default = real `run_stat`,
  which lazily imports scipy/lifelines only when a function actually runs — so
  importing the graph stays cheap and most offline tests never touch the libraries.
- **Idempotency / fail-soft:** the `stats` step is additive. Empty table, `NONE`, or
  any `GuardError` degrades to the descriptive answer; it never turns a good answer
  into an error.
- **`from __future__ import annotations`** at the top of every new module; ruff stays
  on `target-version = "py311"`.
- **Do not** modify `sql/permission.py` or `sql/validator.py` — Phase 2 adds a new
  guard surface under `sandbox/stats/`, it does not touch the SQL guard rails.
```
