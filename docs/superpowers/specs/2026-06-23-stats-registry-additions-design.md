# Stats Registry Additions (Mann-Whitney / Tukey / Two-way ANOVA / Cox) — Design

**Date:** 2026-06-23
**Status:** Approved (design), pending spec review
**Scope:** Add four vetted tests to the existing `sandbox/stats/` registry —
Mann-Whitney U, Tukey HSD post-hoc, two-way ANOVA, Cox proportional-hazards. Pure
additions following the frozen registry pattern, plus one validator extension (a
`columns` list param role) and one new dependency (statsmodels).

## Context

The stats sandbox (Phase 2) already has a frozen registry (`registry.py`), a
deterministic validator (`validator.py`), hand-written functions (`functions.py`),
and a runner (`runner.py`). The LLM emits only `{function, params}` data; dispatch is
allowlist-only; everything is fail-soft and pure in-memory. These four tests extend
that surface without changing the contract, the graph, or the prompts.

## Dependencies

Add **`statsmodels`** (two-way ANOVA via `ols` + `anova_lm`). pandas is already
present (transitively via lifelines); scipy and lifelines are already direct deps.

## Validator extension — `columns` (list) param role

`ParamSpec.role` currently supports `"column"` (one column) and `"scalar"`. Add
**`"columns"`**: the value must be a non-empty `list` of strings, each present in the
table's columns. Used by Cox covariates. Validation fails closed (GuardError) on:
not a list, empty list, a non-string element, or any element not in
`available_columns`. The validated value (the clean list) flows through
`ValidatedStatRequest.params` like the other roles. `catalog_text()` renders a
`columns` param as e.g. `covariates (columns)`.

## Functions (input → StatResult mapping)

All return the existing `StatResult(test, stats, groups, caveats)`. Per-test
pairwise / per-covariate numbers ride in `stats` as composite-keyed floats so the
existing `dict[str, float]` shape is unchanged.

1. **`mann_whitney_u`** (`scipy.stats.mannwhitneyu`) — params `value` (column),
   `group` (column), optional `alpha` (scalar, 0–1). Requires exactly 2 groups, each
   n≥2 (else GuardError). `stats = {u, p_value}`; `groups = [{label, n, median}]`;
   caveats: non-parametric (no normality assumption), two-sided, tests distribution /
   median shift; significance vs alpha.

2. **`tukey_hsd`** (`scipy.stats.tukey_hsd`) — params `value` (column), `group`
   (column), optional `alpha`. Requires ≥2 groups (≥3 meaningful), each n≥2.
   `stats` holds each pairwise p-value keyed `"<a> vs <b> p"` (groups sorted, pairs
   in sorted order); `groups = [{label, n, mean}]`; caveats: post-hoc pairwise,
   family-wise error rate controlled, run after a significant ANOVA.

3. **`two_way_anova`** (`statsmodels.formula.api.ols` + `statsmodels.stats.anova.anova_lm`,
   type II) — params `value` (column), `factor1` (column), `factor2` (column). Builds
   a pandas DataFrame from the three columns (drop rows with any None/NaN), fits
   `value ~ C(factor1) + C(factor2) + C(factor1):C(factor2)`. `stats = {factor1_F,
   factor1_p, factor2_F, factor2_p, interaction_F, interaction_p}`; `groups` = per-cell
   `{factor1, factor2, n, mean}` (capped at the existing `_MAX_GROUPS`); caveats:
   assumes normal residuals + homogeneous variance; needs ≥2 levels per factor and
   data in the cells (else GuardError). Requires ≥ a minimum row count to fit (else
   GuardError, fail-soft).

4. **`cox_ph`** (`lifelines.CoxPHFitter`) — params `duration` (column), `event`
   (column, 0/1), `covariates` (**columns** list). Builds a DataFrame of
   duration+event+covariates (drop None/NaN; validate event ∈ {0,1}); fits Cox.
   `stats` holds per-covariate `"<cov> hazard_ratio"` (= exp(coef)) and `"<cov> p"`;
   `groups = [{label: "all", n}]`; caveats: proportional-hazards assumption, needs
   enough events relative to covariates (rule of thumb ≥10 events per covariate),
   censoring interpretation (event=1 observed). Degenerate fits (singular, too few
   events) → GuardError → fail-soft.

## Registry / catalog / dispatch

Append the four `StatTest` entries to `REGISTRY`; `catalog_text()` picks them up
automatically (it already iterates the registry and renders param roles — extended to
print `columns`). `runner.run_stat` and the `stats_node` are unchanged: same
`{function, params}` → validate → dispatch → `StatResult` flow, same fail-soft, same
row cap, same typeless-scalar reject.

## Security

Unchanged model: the LLM supplies a structured request (data, never code); dispatch
is allowlist-only via the registry dict; the new `columns` role only ever resolves to
column names already present in the (permission-filtered) table — no new injection
surface, no file/network/DB access (pure scipy/statsmodels/lifelines compute). The
validator change is the one safety-relevant edit, so it gets a `sql-security-reviewer`
pass during execution.

## Testing

- **validator `columns` role:** accepts a valid list of present columns; rejects a
  non-list, an empty list, a non-string element, and an element not in the table.
- **each function (offline, real libs on fixtures):**
  - mann_whitney_u: clearly separated groups → small p; exactly-2-group + n≥2
    enforcement (GuardError otherwise).
  - tukey_hsd: 3 groups → pairwise keys present; the clearly-different pair has the
    smaller p.
  - two_way_anova: a constructed 2×2 design with a real main effect → that factor's p
    is small; the F/p keys all present; <2 levels → GuardError.
  - cox_ph: a covariate that drives the hazard → hazard_ratio away from 1 and small p;
    too-few-events / single covariate-value → GuardError.
- **registry/catalog:** `REGISTRY` contains the four new names; `catalog_text()`
  includes them and renders the `columns` role.
- **full offline suite + ruff** stay green; existing tests unchanged (registry is
  additive; dispatch path identical).
- **security review:** `sql-security-reviewer` over `validator.py` (the `columns`
  role) + the new functions.
- **live (best-effort):** a Mann-Whitney question (e.g. "G1 vs G2 的 tgi_tv 分布是否
  有差异,用非参数检验") and a Tukey question route through the stats node and return
  the new tests; two-way ANOVA / Cox depend on suitable real data shapes — report
  whatever the live data supports.

## Out of scope (deferred)

Further tests (chi-square, mixed models, repeated-measures), automatic test selection,
and any graph/prompt change. New tests remain pure `registry.py` + `functions.py`
additions.

## Risks

- **statsmodels weight:** a new dependency (pulls patsy); accepted for two-way ANOVA.
  If install size matters later, two-way ANOVA could be hand-rolled, but YAGNI now.
- **Cox / two-way ANOVA need richer data** than the toy efficacy rows; live
  verification may only exercise Mann-Whitney/Tukey. Offline fixtures cover all four.
- **Pairwise/covariate keys are dynamic** (depend on group/covariate names); the
  `stats` dict tolerates this. Answer rendering already iterates `stats.items()`.
