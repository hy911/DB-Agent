# Stats Registry Additions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four vetted tests — Mann-Whitney U, Tukey HSD, two-way ANOVA, Cox PH — to the `sandbox/stats/` registry, plus a `columns` (list) validator role and the statsmodels dependency.

**Architecture:** Pure additions to the frozen stats registry. New functions in `functions.py`, new entries in `registry.py`, one new `columns` param role in `validator.py` + `catalog_text`. Dispatch/runner/node unchanged. The LLM still emits only `{function, params}` data; everything stays fail-soft.

**Tech Stack:** Python, scipy, statsmodels (new), lifelines, pandas, pytest, ruff, uv.

**Reference spec:** `docs/superpowers/specs/2026-06-23-stats-registry-additions-design.md`

---

## File Structure

**Modify:**
- `pyproject.toml` — add `statsmodels`.
- `src/db_agent/sandbox/stats/validator.py` — `columns` role.
- `src/db_agent/sandbox/stats/registry.py` — 4 new entries + `catalog_text` role label.
- `src/db_agent/sandbox/stats/functions.py` — 4 new functions + a `median` import.
- `tests/test_stats_validator.py`, `tests/test_stats_functions.py` — new tests.
- `CLAUDE.md` — note the added tests.

---

## Task 1: statsmodels dependency + smoke

**Files:** Modify `pyproject.toml`; Create `tests/test_statsmodels_smoke.py`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` `dependencies = [` add:

```toml
    "statsmodels>=0.14",
```

- [ ] **Step 2: Install**

Run: `uv sync --extra dev`
Expected: installs statsmodels (+ patsy); exit 0.

- [ ] **Step 3: Smoke test**

```python
# tests/test_statsmodels_smoke.py
from __future__ import annotations


def test_statsmodels_two_way_anova_runs():
    import pandas as pd
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm

    df = pd.DataFrame(
        {
            "y": [1.0, 2.0, 1.5, 8.0, 9.0, 8.5, 2.0, 1.0, 9.5, 8.0, 1.0, 2.5],
            "a": ["x", "x", "x", "y", "y", "y", "x", "x", "y", "y", "x", "x"],
            "b": ["p", "p", "q", "p", "p", "q", "q", "p", "q", "p", "p", "q"],
        }
    )
    model = smf.ols("y ~ C(a) + C(b) + C(a):C(b)", data=df).fit()
    table = anova_lm(model, typ=2)
    assert "C(a)" in table.index
    assert float(table.loc["C(a)", "PR(>F)"]) < 0.05  # factor a clearly separates y
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/test_statsmodels_smoke.py -v`
Expected: 1 passed. If statsmodels import/compute fails, STOP.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_statsmodels_smoke.py
git commit -m "stats additions T1: statsmodels dep + smoke"
```

---

## Task 2: validator `columns` role + catalog rendering

**Files:** Modify `src/db_agent/sandbox/stats/validator.py`, `src/db_agent/sandbox/stats/registry.py`; Test `tests/test_stats_validator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_stats_validator.py`:

```python
def test_accepts_columns_role():
    reg = {
        "cov": StatTest(
            "cov",
            "covariates test",
            {"covariates": ParamSpec("columns")},
            _dummy_run,
        )
    }
    v = validate_stat_request(
        {"function": "cov", "params": {"covariates": ["value", "other"]}}, COLS, reg
    )
    assert v.params["covariates"] == ["value", "other"]


def test_rejects_columns_not_a_list():
    reg = {"cov": StatTest("cov", "c", {"covariates": ParamSpec("columns")}, _dummy_run)}
    with pytest.raises(GuardError):
        validate_stat_request({"function": "cov", "params": {"covariates": "value"}}, COLS, reg)


def test_rejects_empty_columns_list():
    reg = {"cov": StatTest("cov", "c", {"covariates": ParamSpec("columns")}, _dummy_run)}
    with pytest.raises(GuardError):
        validate_stat_request({"function": "cov", "params": {"covariates": []}}, COLS, reg)


def test_rejects_columns_with_unknown_column():
    reg = {"cov": StatTest("cov", "c", {"covariates": ParamSpec("columns")}, _dummy_run)}
    with pytest.raises(GuardError):
        validate_stat_request(
            {"function": "cov", "params": {"covariates": ["value", "nope"]}}, COLS, reg
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stats_validator.py -q`
Expected: the 4 new tests FAIL (columns role not handled).

- [ ] **Step 3: Add the `columns` branch in `validator.py`**

In `validate_stat_request`, replace the role dispatch block:

```python
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
```

with:

```python
        if spec.role == "column":
            if not isinstance(val, str) or val not in cols:
                raise GuardError(
                    "stat_bad_column",
                    f"param {pname!r}={val!r} is not a column of the result table",
                    retryable=False,
                )
        elif spec.role == "columns":
            if (
                not isinstance(val, list)
                or not val
                or not all(isinstance(c, str) and c in cols for c in val)
            ):
                raise GuardError(
                    "stat_bad_column",
                    f"param {pname!r} must be a non-empty list of result columns",
                    retryable=False,
                )
        else:  # scalar
            _check_scalar(pname, val, spec)
        clean[pname] = val
```

- [ ] **Step 4: Make `catalog_text` role-aware in `registry.py`**

Replace the `catalog_text` function with:

```python
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
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_stats_validator.py -q`
Expected: all pass (existing + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/sandbox/stats/validator.py src/db_agent/sandbox/stats/registry.py tests/test_stats_validator.py
git commit -m "stats additions T2: columns validator role + catalog rendering"
```

---

## Task 3: Mann-Whitney U + Tukey HSD

**Files:** Modify `src/db_agent/sandbox/stats/functions.py`, `registry.py`; Test `tests/test_stats_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_stats_functions.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: new tests FAIL (functions missing).

- [ ] **Step 3: Add a `median` import to `functions.py`**

Change the statistics import line:

```python
from statistics import fmean
```

to:

```python
from statistics import fmean, median
```

- [ ] **Step 4: Append the two functions to `functions.py`**

```python
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
        groups=[{"label": lbl, "n": len(groups[lbl]), "mean": fmean(groups[lbl])} for lbl in labels],
        caveats=caveats,
    )
```

- [ ] **Step 5: Register both in `registry.py`**

Add these two `StatTest` entries inside the `REGISTRY` tuple (after `kaplan_meier`):

```python
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
```

and extend the import at the top of `registry.py`:

```python
from db_agent.sandbox.stats.functions import (
    kaplan_meier,
    mann_whitney_u,
    one_way_anova,
    tukey_hsd,
    welch_t_test,
)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/db_agent/sandbox/stats/functions.py src/db_agent/sandbox/stats/registry.py tests/test_stats_functions.py
git commit -m "stats additions T3: Mann-Whitney U + Tukey HSD"
```

---

## Task 4: Two-way ANOVA + Cox PH

**Files:** Modify `src/db_agent/sandbox/stats/functions.py`, `registry.py`; Test `tests/test_stats_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_stats_functions.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: the 4 new tests FAIL.

- [ ] **Step 3: Append the two functions to `functions.py`**

```python
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
            "stat_insufficient_n", "not enough survival observations/events for Cox", retryable=False
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
```

- [ ] **Step 4: Register both in `registry.py`**

Add to the `REGISTRY` tuple (after `tukey_hsd`):

```python
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
            "survival. duration=time-to-event, event=1 observed/0 censored, covariates="
            "numeric columns.",
            {
                "duration": ParamSpec("column"),
                "event": ParamSpec("column"),
                "covariates": ParamSpec("columns"),
            },
            cox_ph,
        ),
```

and extend the `registry.py` import:

```python
from db_agent.sandbox.stats.functions import (
    cox_ph,
    kaplan_meier,
    mann_whitney_u,
    one_way_anova,
    tukey_hsd,
    two_way_anova,
    welch_t_test,
)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/sandbox/stats/functions.py src/db_agent/sandbox/stats/registry.py tests/test_stats_functions.py
git commit -m "stats additions T4: two-way ANOVA + Cox PH"
```

---

## Task 5: Registry catalog test + full suite + ruff + security + docs

**Files:** Test `tests/test_stats_functions.py` (or a small registry test); Modify `CLAUDE.md`

- [ ] **Step 1: Registry/catalog presence test**

Append to `tests/test_stats_functions.py`:

```python
def test_registry_lists_all_seven_tests():
    from db_agent.sandbox.stats.registry import REGISTRY, catalog_text

    assert set(REGISTRY) == {
        "welch_t_test",
        "one_way_anova",
        "kaplan_meier",
        "mann_whitney_u",
        "tukey_hsd",
        "two_way_anova",
        "cox_ph",
    }
    cat = catalog_text()
    assert "cox_ph" in cat
    assert "covariates (columns)" in cat  # the columns role renders
```

- [ ] **Step 2: Full offline suite**

Run: `uv run pytest -q`
Expected: all pass, 9 deselected.

- [ ] **Step 3: Lint + format**

Run: `uv run ruff check src tests && uv run ruff format src tests`
Expected: clean; commit any reformatting.

- [ ] **Step 4: Security review**

Dispatch `sql-security-reviewer` over `src/db_agent/sandbox/stats/validator.py` (the new
`columns` role) and `functions.py` (the four new functions). Confirm: the `columns`
role only resolves to columns present in the supplied table; no dynamic dispatch added
(registry dict only); the new functions open no files/sockets/DB (pure
scipy/statsmodels/lifelines); all GuardErrors are `retryable=False`; fail-soft is
preserved. Address any high-confidence finding.

- [ ] **Step 5: Update CLAUDE.md**

In the stats Phase 2 paragraph, update the test list from "three vetted tests" to seven
(add Mann-Whitney U, Tukey HSD, two-way ANOVA, Cox PH), note the `columns` param role
and the statsmodels dependency. Remove two-way ANOVA / post-hoc / Cox from the
"deferred stats tests" line.

- [ ] **Step 6: Commit + push**

```bash
git add -A
git commit -m "stats additions T5: registry test + docs + suite green"
git push origin main
```

- [ ] **Step 7: Live (best-effort)**

Through `run_agent` with real deps, ask a Mann-Whitney question (e.g. "G1 和 G2 两组的
tgi_tv 分布是否有显著差异,用非参数检验") and a Tukey question; confirm the stats node
fires the new test and the answer reports it. Two-way ANOVA / Cox depend on suitable
real data; report what the data supports. If the gateway is flaky, note it — the
deterministic functions are already proven offline.

---

## Notes for the implementer

- Registry is additive; the dispatch path (`runner.run_stat` → validate → `test.run`)
  is unchanged, so existing stats tests and the graph stay green.
- `from __future__ import annotations` on touched modules; ruff stays `py311`.
- Cox uses `_duration`/`_event` as internal DataFrame columns to avoid clashing with a
  covariate's own name; covariate column names come straight from the result table.
- Do not touch the graph, prompts, or `runner.py` — these are pure registry/validator
  additions.
