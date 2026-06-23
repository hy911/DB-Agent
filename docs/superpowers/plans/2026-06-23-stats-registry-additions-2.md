# Stats Registry Additions Batch 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six scipy tests — Kruskal-Wallis, chi-square, Spearman, Pearson, Wilcoxon (paired), Shapiro — to the `sandbox/stats/` registry.

**Architecture:** Pure additions to `functions.py` + `registry.py` (+ two helpers). All params use the existing single-`column` role, so no validator change and no new dependency. Dispatch/runner/graph/prompts unchanged; fail-soft preserved.

**Tech Stack:** scipy, pandas (already present), pytest, ruff, uv.

**Reference spec:** `docs/superpowers/specs/2026-06-23-stats-registry-additions-2-design.md`

---

## Task 1: Helpers + Kruskal-Wallis + correlations (group & paired-numeric shapes)

**Files:** Modify `src/db_agent/sandbox/stats/functions.py`, `registry.py`; Test `tests/test_stats_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_stats_functions.py`:

```python
def test_kruskal_detects_difference():
    from db_agent.sandbox.stats.functions import kruskal_wallis

    rows = (
        [{"g": "a", "v": x} for x in (1.0, 2.0, 3.0)]
        + [{"g": "b", "v": x} for x in (4.0, 5.0, 6.0)]
        + [{"g": "c", "v": x} for x in (40.0, 50.0, 60.0)]
    )
    out = kruskal_wallis(rows, {"value": "v", "group": "g"})
    assert out.test == "kruskal_wallis"
    assert out.stats["p_value"] < 0.05
    assert len(out.groups) == 3 and all("median" in g for g in out.groups)


def test_kruskal_needs_two_groups():
    from db_agent.sandbox.stats.functions import kruskal_wallis

    rows = [{"g": "a", "v": 1.0}, {"g": "a", "v": 2.0}]
    with pytest.raises(GuardError):
        kruskal_wallis(rows, {"value": "v", "group": "g"})


def test_spearman_monotonic():
    from db_agent.sandbox.stats.functions import spearman_correlation

    rows = [{"x": float(i), "y": float(i * i)} for i in range(1, 8)]  # monotonic
    out = spearman_correlation(rows, {"x": "x", "y": "y"})
    assert out.test == "spearman_correlation"
    assert out.stats["rho"] > 0.99
    assert out.stats["p_value"] < 0.05
    assert out.stats["n"] == 7.0


def test_pearson_linear():
    from db_agent.sandbox.stats.functions import pearson_correlation

    rows = [{"x": float(i), "y": 2.0 * i + 1.0} for i in range(1, 8)]  # perfectly linear
    out = pearson_correlation(rows, {"x": "x", "y": "y"})
    assert out.test == "pearson_correlation"
    assert out.stats["r"] > 0.99
    assert out.stats["n"] == 7.0


def test_correlation_needs_three_points():
    from db_agent.sandbox.stats.functions import pearson_correlation, spearman_correlation

    rows = [{"x": 1.0, "y": 2.0}, {"x": 2.0, "y": 4.0}]
    with pytest.raises(GuardError):
        spearman_correlation(rows, {"x": "x", "y": "y"})
    with pytest.raises(GuardError):
        pearson_correlation(rows, {"x": "x", "y": "y"})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: new tests FAIL (functions missing).

- [ ] **Step 3: Add helpers + functions to `functions.py`**

Append:

```python
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
```

- [ ] **Step 4: Register the three in `registry.py`**

Extend the import:

```python
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
```

Add to the `REGISTRY` tuple (after `cox_ph`):

```python
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
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/sandbox/stats/functions.py src/db_agent/sandbox/stats/registry.py tests/test_stats_functions.py
git commit -m "stats batch 2 T1: Kruskal-Wallis + Spearman + Pearson"
```

---

## Task 2: Wilcoxon + Shapiro + chi-square

**Files:** Modify `src/db_agent/sandbox/stats/functions.py`, `registry.py`; Test `tests/test_stats_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_stats_functions.py`:

```python
def test_wilcoxon_paired_shift():
    from db_agent.sandbox.stats.functions import wilcoxon

    # y consistently above x by a few units -> significant signed-rank
    rows = [{"x": float(i), "y": float(i) + 3.0} for i in range(1, 9)]
    out = wilcoxon(rows, {"x": "x", "y": "y"})
    assert out.test == "wilcoxon"
    assert out.stats["p_value"] < 0.05
    assert out.stats["n_pairs"] == 8.0


def test_wilcoxon_needs_enough_pairs():
    from db_agent.sandbox.stats.functions import wilcoxon

    rows = [{"x": float(i), "y": float(i) + 1.0} for i in range(3)]
    with pytest.raises(GuardError):
        wilcoxon(rows, {"x": "x", "y": "y"})


def test_shapiro_flags_non_normal():
    from db_agent.sandbox.stats.functions import shapiro

    # a heavily skewed sample -> reject normality
    rows = [{"v": float(v)} for v in [1, 1, 1, 1, 1, 1, 1, 2, 3, 100]]
    out = shapiro(rows, {"value": "v"})
    assert out.test == "shapiro"
    assert out.stats["p_value"] < 0.05
    assert out.stats["n"] == 10.0


def test_shapiro_needs_three():
    from db_agent.sandbox.stats.functions import shapiro

    with pytest.raises(GuardError):
        shapiro([{"v": 1.0}, {"v": 2.0}], {"value": "v"})


def test_chi_square_association():
    from db_agent.sandbox.stats.functions import chi_square

    # strong association: a=p mostly with b=x; a=q mostly with b=y
    rows = (
        [{"a": "p", "b": "x"} for _ in range(20)]
        + [{"a": "p", "b": "y"} for _ in range(2)]
        + [{"a": "q", "b": "x"} for _ in range(2)]
        + [{"a": "q", "b": "y"} for _ in range(20)]
    )
    out = chi_square(rows, {"col1": "a", "col2": "b"})
    assert out.test == "chi_square"
    assert out.stats["p_value"] < 0.05
    assert "dof" in out.stats


def test_chi_square_needs_two_categories():
    from db_agent.sandbox.stats.functions import chi_square

    rows = [{"a": "p", "b": "x"} for _ in range(5)]  # one category each
    with pytest.raises(GuardError):
        chi_square(rows, {"col1": "a", "col2": "b"})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: new tests FAIL.

- [ ] **Step 3: Append the three functions to `functions.py`**

```python
def wilcoxon(rows, params) -> StatResult:
    from scipy import stats as _stats

    xs, ys = _paired_values(rows, params["x"], params["y"])
    if len(xs) < 6:
        raise GuardError(
            "stat_insufficient_n", "Wilcoxon needs at least 6 paired observations", retryable=False
        )
    try:
        res = _stats.wilcoxon(xs, ys)
    except ValueError as e:  # e.g. all differences zero
        raise GuardError("stat_fit_error", str(e).strip()[:200], retryable=False) from e
    p = float(res.pvalue)
    caveats = [
        "Wilcoxon signed-rank (paired, non-parametric); tests the median of paired differences.",
        _significance(p, 0.05),
    ]
    return StatResult(
        test="wilcoxon",
        stats={"w": float(res.statistic), "p_value": p, "n_pairs": float(len(xs))},
        groups=[],
        caveats=caveats,
    )


def shapiro(rows, params) -> StatResult:
    from scipy import stats as _stats

    vals = _column_values(rows, params["value"])
    if len(vals) < 3:
        raise GuardError("stat_insufficient_n", "Shapiro needs at least 3 values", retryable=False)
    caveats = ["Shapiro-Wilk normality test.", "Over-sensitive on very large samples."]
    used = vals
    if len(vals) > 5000:
        used = vals[:5000]
        caveats.append("n>5000: tested the first 5000 values (Shapiro p is unreliable above 5000).")
    res = _stats.shapiro(used)
    p = float(res.pvalue)
    caveats.append(
        "p < 0.05 suggests the data is not normally distributed."
        if p < 0.05
        else "No strong evidence against normality."
    )
    return StatResult(
        test="shapiro",
        stats={"w": float(res.statistic), "p_value": p, "n": float(len(used))},
        groups=[],
        caveats=caveats,
    )


def chi_square(rows, params) -> StatResult:
    import pandas as pd
    from scipy import stats as _stats

    c1, c2 = params["col1"], params["col2"]
    a: list[str] = []
    b: list[str] = []
    for r in rows:
        x, y = r.get(c1), r.get(c2)
        if x is None or y is None:
            continue
        a.append(str(x))
        b.append(str(y))
    if not a:
        raise GuardError("stat_insufficient_n", "no rows with both categories", retryable=False)
    table = pd.crosstab(pd.Series(a), pd.Series(b))
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise GuardError(
            "stat_group_count", "each variable needs at least 2 categories", retryable=False
        )
    if table.shape[0] > _MAX_GROUPS or table.shape[1] > _MAX_GROUPS:
        raise GuardError(
            "stat_group_count", f"too many categories (> {_MAX_GROUPS})", retryable=False
        )
    chi2, p, dof, _expected = _stats.chi2_contingency(table.values)
    caveats = [
        "Chi-square test of independence between two categorical variables.",
        "Validity assumes expected cell counts >= 5.",
        _significance(float(p), 0.05),
    ]
    return StatResult(
        test="chi_square",
        stats={"chi2": float(chi2), "p_value": float(p), "dof": float(dof)},
        groups=[],
        caveats=caveats,
    )
```

- [ ] **Step 4: Register the three in `registry.py`**

Extend the import to also include `chi_square`, `shapiro`, `wilcoxon` (keep alphabetical):

```python
from db_agent.sandbox.stats.functions import (
    chi_square,
    cox_ph,
    kaplan_meier,
    kruskal_wallis,
    mann_whitney_u,
    one_way_anova,
    pearson_correlation,
    shapiro,
    spearman_correlation,
    tukey_hsd,
    two_way_anova,
    welch_t_test,
    wilcoxon,
)
```

Add to the `REGISTRY` tuple (after `pearson_correlation`):

```python
        StatTest(
            "wilcoxon",
            "Wilcoxon signed-rank test: paired non-parametric comparison of two numeric "
            "columns (e.g. before vs after on the same subject).",
            {"x": ParamSpec("column"), "y": ParamSpec("column")},
            wilcoxon,
        ),
        StatTest(
            "shapiro",
            "Shapiro-Wilk normality test for a single numeric column.",
            {"value": ParamSpec("column")},
            shapiro,
        ),
        StatTest(
            "chi_square",
            "Chi-square test of independence between two categorical columns.",
            {"col1": ParamSpec("column"), "col2": ParamSpec("column")},
            chi_square,
        ),
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_stats_functions.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/sandbox/stats/functions.py src/db_agent/sandbox/stats/registry.py tests/test_stats_functions.py
git commit -m "stats batch 2 T2: Wilcoxon + Shapiro + chi-square"
```

---

## Task 3: Registry count test + full suite + ruff + security + docs

**Files:** Modify `tests/test_stats_functions.py`, `CLAUDE.md`

- [ ] **Step 1: Update the registry-count test**

Replace `test_registry_lists_all_seven_tests` in `tests/test_stats_functions.py` with:

```python
def test_registry_lists_all_thirteen_tests():
    from db_agent.sandbox.stats.registry import REGISTRY, catalog_text

    assert set(REGISTRY) == {
        "welch_t_test",
        "one_way_anova",
        "kaplan_meier",
        "mann_whitney_u",
        "tukey_hsd",
        "two_way_anova",
        "cox_ph",
        "kruskal_wallis",
        "spearman_correlation",
        "pearson_correlation",
        "wilcoxon",
        "shapiro",
        "chi_square",
    }
    cat = catalog_text()
    assert "kruskal_wallis" in cat and "chi_square" in cat
```

- [ ] **Step 2: Full offline suite**

Run: `uv run pytest -q`
Expected: all pass, 9 deselected.

- [ ] **Step 3: Lint + format**

Run: `uv run ruff check src tests && uv run ruff format src tests`
Expected: clean; commit any reformatting.

- [ ] **Step 4: Security review**

Dispatch `sql-security-reviewer` over the new `functions.py` additions (the six
functions + `_paired_values` / `_column_values`). Confirm: no I/O (pure scipy/pandas);
column params only ever used as dict keys against the passed-in rows (no formula/SQL/
shell); chi-square crosstab is built from row values, not code; all GuardErrors are
`retryable=False`; fail-soft preserved. Address any high-confidence finding.

- [ ] **Step 5: Update CLAUDE.md**

In the stats Phase 2 bullet, change "Seven vetted tests" to "Thirteen vetted tests"
and add the six new ones (Kruskal-Wallis, Spearman, Pearson, Wilcoxon, Shapiro,
chi-square). In the deferred line, drop chi-square (now built); leave Fisher exact /
Levene / mixed models as the remaining examples.

- [ ] **Step 6: Commit + push**

```bash
git add tests/test_stats_functions.py CLAUDE.md
git commit -m "stats batch 2 T3: registry test + docs + suite green"
git push origin main
```

- [ ] **Step 7: Live (best-effort)**

Through `run_agent` with real deps, ask a Kruskal-Wallis question (e.g. "不同 group_id
的 tgi_tv 分布是否有差异,用非参数检验,取原始 group_id 和 tgi_tv,统计交给系统") and a
Spearman/correlation question; confirm the stats node fires the new test and the answer
reports it. Report SQL + stat request + answer. Gateway-flaky → note it; the functions
are already proven offline.

---

## Notes for the implementer

- No validator change (all params are single `column`), no new dependency.
- `_significance` / `median` / `_group_values` / `_to_float` / `_MAX_GROUPS` already
  exist in `functions.py` from earlier batches — reuse them.
- scipy `spearmanr` / `pearsonr` / `wilcoxon` / `shapiro` return result objects with
  `.statistic` / `.pvalue` (scipy ≥1.9; the project is on 1.18).
- `from __future__ import annotations` stays at the top; ruff stays `py311`.
- Do not touch the graph, prompts, runner, or validator.
