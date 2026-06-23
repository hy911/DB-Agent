# Stats Registry Additions Batch 2 (Kruskal / chi-square / Spearman / Pearson / Wilcoxon / Shapiro) — Design

**Date:** 2026-06-23
**Status:** Approved (design), pending spec review
**Scope:** Add six more vetted tests to the `sandbox/stats/` registry. All scipy, no
new dependencies, no validator change (every param uses the existing single-`column`
role). Pure `functions.py` + `registry.py` additions following the frozen pattern.

## Context

The stats registry currently holds seven tests. This batch adds the common
non-parametric / association / assumption tests, completing the parametric ↔
non-parametric pairings (one-way ANOVA ↔ Kruskal-Wallis, mirroring Welch ↔
Mann-Whitney) and adding categorical association, correlation, paired comparison, and
a normality check. The LLM still emits only `{function, params}` data; dispatch stays
allowlist-only; everything is fail-soft and pure in-memory.

## Two new helpers (in `functions.py`)

- `_paired_values(rows, x_col, y_col) -> tuple[list[float], list[float]]`: collect
  row-aligned numeric pairs; drop a row if either value is None / NaN / non-numeric
  (via `_to_float`). Used by Spearman / Pearson / Wilcoxon.
- `_column_values(rows, col) -> list[float]`: collect one numeric column, dropping
  None/NaN. Used by Shapiro.

## Functions (input → StatResult)

All return `StatResult(test, stats, groups, caveats)`; `stats` is `dict[str, float]`.

1. **`kruskal_wallis`** (`scipy.stats.kruskal`) — `value` (column), `group` (column).
   Reuses `_group_values`; needs ≥2 groups, each n≥2 (else GuardError). `stats =
   {h, p_value}`; `groups = [{label, n, median}]`; caveats: non-parametric one-way
   ANOVA (rank-based), tests distribution shift across groups; significance vs 0.05.

2. **`chi_square`** (`scipy.stats.chi2_contingency`) — `col1` (column), `col2`
   (column), treated as categorical. Build a contingency table of co-occurrence
   counts (pandas `crosstab`); reject if either variable has <2 categories or the
   table exceeds `_MAX_GROUPS` rows/cols (GuardError). `stats = {chi2, p_value, dof}`;
   `groups = []`; caveats: tests independence of two categoricals; expected cell
   counts ≥5 recommended for validity.

3. **`spearman_correlation`** (`scipy.stats.spearmanr`) — `x` (column), `y` (column),
   numeric, paired via `_paired_values`; needs n≥3 (else GuardError). `stats =
   {rho, p_value, n}`; `groups = []`; caveats: monotonic (rank-based) association.

4. **`pearson_correlation`** (`scipy.stats.pearsonr`) — `x`, `y` numeric paired,
   n≥3. `stats = {r, p_value, n}`; `groups = []`; caveats: linear association,
   sensitive to outliers, assumes roughly bivariate-normal.

5. **`wilcoxon`** (`scipy.stats.wilcoxon`, paired) — `x`, `y` numeric paired, n≥6
   pairs (scipy's small-sample floor; else GuardError). Wrap scipy in try/except so an
   all-zero-difference input → GuardError (fail-soft). `stats = {w, p_value,
   n_pairs}`; `groups = []`; caveats: paired non-parametric test of the median of
   differences.

6. **`shapiro`** (`scipy.stats.shapiro`) — `value` (column), numeric, 3≤n; if n>5000
   use the first 5000 values (scipy's p-value is unreliable above that) and note it in
   caveats. `stats = {w, p_value, n}`; `groups = []`; caveats: tests normality;
   over-sensitive on very large n.

## Registry / dispatch / security

Append six `StatTest` entries to `REGISTRY`; `catalog_text()` renders them
automatically (all `column` roles). `runner.run_stat`, `validator.py`, the graph, and
the prompts are unchanged. The LLM supplies a structured request (data, never code);
dispatch is registry-dict only; the new functions open no files/sockets/DB (pure
scipy/pandas compute) and reference only the validated column params. The validator is
**not** touched (no new role), but the new function surface still gets a
`sql-security-reviewer` pass during execution.

## Testing

- **each function (offline, real scipy on fixtures):**
  - kruskal_wallis: clearly separated groups → small p; <2 groups / n<2 → GuardError.
  - chi_square: a contingency with strong association → small p; <2 categories →
    GuardError.
  - spearman/pearson: a monotonic/linear relation → |coef| high, small p; n<3 →
    GuardError.
  - wilcoxon: paired shift → small p; too-few pairs / all-zero diff → GuardError.
  - shapiro: clearly non-normal sample → small p; normal-ish → larger p; n<3 →
    GuardError.
- **registry:** `REGISTRY` now has 13 names; `catalog_text()` includes the six new.
- **full offline suite + ruff** stay green (additive; dispatch path unchanged).
- **security review:** `sql-security-reviewer` over the new `functions.py` additions.
- **live (best-effort):** a Kruskal-Wallis question and a Spearman question route
  through the stats node and return the new tests; report SQL + stat request + answer.

## Out of scope

Further tests (Fisher exact, Levene, mixed/repeated-measures, multiple-comparison
corrections) — pure later additions. No validator/graph/prompt change.

## Risks

- **chi_square category explosion:** capped at `_MAX_GROUPS` per axis (GuardError
  otherwise); the upstream row cap also bounds input.
- **paired alignment:** `_paired_values` pairs by row (each row carries both columns);
  it does not attempt cross-row matching — correct for this row-oriented result model.
- **scipy small-sample/large-sample edges** (Wilcoxon n<6, Shapiro n>5000) handled
  explicitly (GuardError / truncate-with-caveat).
