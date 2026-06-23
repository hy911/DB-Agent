# sandbox/stats/ — vetted statistical inference (Phase 2)

The `stats` graph node runs AFTER `analyze`: `execute → analyze (DuckDB reshape) →
stats → answer`. It reads the post-DuckDB table if present, else the raw result.
Injected via `Deps.run_stat`.

**Contract (the core of the security model):** the LLM emits ONLY a structured
`{function, params}` JSON request — **data, never code**. `validate_stat_request`
(`validator.py`) checks it against the frozen `REGISTRY` allowlist + the current
table's columns + scalar bounds; a hand-written impl in `functions.py` then calls
scipy / statsmodels / lifelines.

**Robustness / security:** dispatch is only ever through the registry dict (no dynamic
import); pure in-memory compute (no file/network/DB); **fail-soft** — any `GuardError`
makes `stats_node` return `{}` and the answer degrades to the descriptive result. All
`GuardError`s here are `retryable=False`. Defense-in-depth: independent row cap
(`runner._MAX_ROWS`) + typeless-scalar reject.

**13 vetted tests** (named test + caveats, no auto-switching): `welch_t_test`,
`mann_whitney_u`, `one_way_anova`, `kruskal_wallis`, `tukey_hsd`, `two_way_anova`
(statsmodels), `kaplan_meier` (+ log-rank), `cox_ph` (covariates via the `columns`
role), `spearman_correlation`, `pearson_correlation`, `wilcoxon` (paired), `shapiro`,
`chi_square`.

**Param roles (`spec.py` / `validator.py`):** `column` (one column), `columns`
(non-empty list of columns, e.g. Cox covariates — fails closed on non-list / empty /
unknown column), `scalar` (typed + range/enum bounded; a typeless scalar is rejected).
LLM-supplied names are only ever used as dict keys against the rows — never
interpolated into SQL/shell/paths/formulas (the statsmodels formula is a constant;
factor names are data).

**Adding a test** = append a function in `functions.py` + a `StatTest` entry in
`registry.py` (+ tests). `catalog_text()` and the LLM `stat_messages` prompt pick it up
automatically — **no graph or prompt change needed**. Any change here is security-
sensitive: run the `sql-security-reviewer` subagent.

**Deps:** statsmodels (two-way ANOVA), scipy (most), lifelines (KM / Cox).
