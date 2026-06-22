# Stats Sandbox (Phase 2) Design — Controlled Statistical Inference

**Date:** 2026-06-22
**Status:** Approved (architecture + security model), pending spec review
**Scope:** Phase 2 — real statistical inference (t-test / one-way ANOVA / Kaplan-Meier
survival + log-rank) over an already-fetched, permission-filtered result set, via a
**vetted function registry**. Builds on the Phase 1 DuckDB post-processing sandbox
(`2026-06-18-duckdb-sandbox-design.md`), which it leaves unchanged.

## Goal

After Phase 1's optional DuckDB reshape, optionally run **one vetted statistical
test** over the (reshaped) rows — Welch t-test, one-way ANOVA, or Kaplan-Meier +
log-rank — and fold the result (statistic, p-value, effect, per-group n, caveats)
into the natural-language answer. Triggered automatically as a step after `analyze`;
no new routing path.

The hard problem Phase 1 deliberately deferred: t-test / ANOVA / KM cannot be
expressed in DuckDB SQL, so they need a Python statistics library. The security
question is therefore **"how does the LLM request a test without ever supplying
code?"** — answered by a declarative function registry.

## Core decision — declarative function registry (code-as-data)

The LLM never writes Python or SQL for the statistics. It emits a small structured
request naming a registered function and mapping the table's columns to that
function's parameters, e.g.:

```json
{"function": "welch_t_test", "params": {"value": "tumor_volume", "group": "group_id"}}
```

The LLM's output is **data** (a selection + column names + scalar params), not code.
A deterministic validator checks the request against a frozen registry; the hand-
written, audited implementation then pulls those columns from the in-memory table
and calls a pinned library function. This mirrors Phase 1's contract exactly: the
LLM proposes, the deterministic layer enforces.

**Rejected alternatives:**
- *LLM writes restricted Python against a whitelisted API* — executing LLM-authored
  Python is a far larger attack surface (AST sandbox, import/builtins stripping,
  fragile). Violates "safety is never the LLM's job".
- *Stats via DuckDB UDFs/macros* — DuckDB has no t-test/ANOVA/KM aggregate, KM is
  not expressible as an aggregate, and registering Python UDFs would pollute the
  Phase 1 SQL boundary.

## Architecture

New subpackage `src/db_agent/sandbox/stats/` (inside the existing sandbox boundary,
but a distinct, independently testable unit — pure compute on data already in
memory, no external I/O):

- `registry.py` — frozen `StatTest` descriptors. Each carries: `name`; a parameter
  schema (column roles with required/optional + expected dtype; scalar params with
  type + range/enum); and a `run(table, params) -> StatResult` callable. Dispatch is
  **only** through this dict — never a string-keyed dynamic `import`.
- `validator.py` (pure) — `validate_stat_request(request, available_columns) ->
  ValidatedStatRequest`, fail-closed `GuardError`. Reuses `db_agent.sql.errors.GuardError`.
- `runner.py` — `run_stat(table, validated) -> StatResult`: extracts the referenced
  columns into arrays, drops `None`/`NaN`, dispatches to the registered impl.
- vetted implementations (one module each or grouped):
  - `welch_t_test` — `scipy.stats.ttest_ind(..., equal_var=False)` (Welch default).
  - `one_way_anova` — `scipy.stats.f_oneway(*groups)`.
  - `kaplan_meier` — `lifelines.KaplanMeierFitter` (per-group median survival) +
    `lifelines.statistics.logrank_test` (group comparison).

`graph/` stays thin: a new `stats_node` calls the LLM (decide + select test) and the
runner; logic lives in `sandbox/stats/` + `llm/`. The runner is injected via
`Deps.run_stat` (default = the real `run_stat`) so the graph is offline-testable
with a fake.

### Data types

- `StatResult` (frozen dataclass): `test` (str), `stats` (dict[str, float] —
  statistic, p_value, effect estimate, etc.), `groups` (list of per-group summary:
  label, n, mean or median), `caveats` (list[str] — normality / equal-variance /
  sample-size assumptions stated in plain language).
- `ValidatedStatRequest` (frozen dataclass): the resolved function descriptor + the
  validated params (column refs + coerced scalars).

## Flow

Phase 1's `analyze` (DuckDB reshape) is **unchanged**. A new `stats_node` runs after
it:

```
execute → analyze (DuckDB reshape) → stats (vetted test) → answer
                                        │
                                        ├─ table empty/absent → passthrough (no LLM call)
                                        ├─ LLM says NONE       → passthrough
                                        └─ LLM emits request   → validate → run_stat
                                              ├─ ok                       → state["stat_result"]
                                              └─ Guard/stat error         → passthrough (degrade)
```

- `stats_node` reads the **current table**: `state["analysis"]` if Phase 1 produced
  one, else `state["result"]`. So the LLM sees the **reshaped** columns — exactly
  what "reshape first, then test" requires.
- Fail-soft: empty table, `NONE`, any `GuardError`, or a statistical failure
  (single group, insufficient n, all-NaN) → skip and answer from the descriptive
  result. Analysis is additive; it never turns a good answer into an error.

## Rigor — named test + caveats (no auto-switching)

Each vetted function runs one explicit test and reports assumptions as caveats
rather than silently switching tests:

- **welch_t_test**: Welch's t (does not assume equal variance) by default. Returns
  t statistic, p-value, mean difference, per-group n + mean. Caveats: normality
  assumption; small-n warning when any group n is below a threshold.
- **one_way_anova**: F statistic, p-value, per-group n + mean. Caveats: normality +
  equal-variance assumptions; requires ≥2 groups (else fail-soft). No post-hoc.
- **kaplan_meier**: per-group median survival + log-rank statistic and p-value.
  Caveats: censoring interpretation (event=1 observed, 0 censored); small-n warning.

## Security model (independent design — the core of "sandbox")

1. **No code execution.** The LLM output is parsed into a fixed schema; a parse
   failure, unknown function name, or non-conforming params raise `GuardError`. No
   `eval`/`exec`, no LLM-supplied code path of any kind.
2. **Closed allowlist registry.** Only registry functions are callable; each is a
   hand-written, audited Python impl calling a pinned set of library functions.
   Dispatch is solely via the registry dict — no dynamic import by string.
3. **Column-ref validation.** Requests may reference only columns present in the
   (already permission-filtered) current table. Everything runs as pure in-memory
   numpy/pandas — no filesystem, network, or DB access.
4. **Parameter bounds.** Scalar params are constrained by the schema (type +
   range/enum); group cardinality is bounded (ANOVA ≥2 groups, with a sane upper
   cap to avoid pathological compute); row volume is already LIMIT-bounded upstream.
5. **Fail-soft degrade.** Any `GuardError` or statistical failure degrades to the
   descriptive answer (Phase 1 result, else raw rows). Additive, never fatal.
6. **Data isolation (inherited from Phase 1).** The stats step only ever sees
   already-permission-filtered rows; it holds no replica DSN, credentials, or DB
   connection. A sandbox escape can expose only data the user already received.

## State / DI / Observability changes

- `AgentState`: add `stat_result: StatResult | None` and `stat_request: str | None`
  (both default `None` in `initial_state`).
- `AgentResult`: add `stat_request` (best-effort, like `analysis_sql`).
- `Deps`: add `run_stat: Callable[[Table, ValidatedStatRequest], StatResult]` with
  the real `run_stat` as default.
- `run_agent(...)`: add `run_stat=None` override, threaded into `Deps`, matching the
  existing `resolve_gene=` / `run_sandbox=` pattern.
- `graph/build.py`: insert `stats` node between `analyze` and `answer`
  (`analyze → stats → answer`); `analyze`'s edge to `answer` is repointed to
  `stats`. The retry/fatal branches are unchanged.
- `answer_node`: when `stat_result` is set, fold the test name, statistic, p-value,
  effect, per-group n, and caveats into the answer, and show the DuckDB SQL + the
  stat request (function + params) for transparency. Otherwise unchanged.
- Observability: `RunRecord` gains `stat_request` so the stats step is logged.

## LLM task

`llm/agent_llm.py` gains `request_stat(client, settings, question, columns, preview,
catalog) -> str`: a prompt (routed to `qwen-code`) given the question, the current
table's columns + a small row preview, and the catalog of available tests with their
parameter schemas. It returns either the single word `NONE` (no test needed) or one
JSON request. Prompt lives in `llm/prompts.py` (`stat_messages`). The model only
selects a test and maps columns; the registry + validator enforce safety
deterministically.

## Dependencies

Add `scipy` and `lifelines` to `pyproject.toml` (runtime deps). `uv sync` installs
them. `lifelines` is the vetted standard for KM/log-rank; it pulls `matplotlib` as a
transitive dependency, which we do not use (no plotting) — accepted as the cost of a
vetted implementation over a hand-rolled KM/log-rank. (Confirmed with the user.)

## Testing

- **registry / validator (offline, pure):** a valid request is accepted; reject an
  unknown function, a missing required param, an extra/unknown param, a column not
  in the table, and an out-of-range/wrong-type scalar.
- **each vetted function (offline, real scipy/lifelines on tiny fixtures):** known
  input → expected statistic/p-value (compared to hand-computed values); single
  group / insufficient n → handled (GuardError or documented degrade).
- **stats_node (fake LLM + fake/real runner):** `NONE` → passthrough (no
  `stat_result`); valid request → `state["stat_result"]` populated; a `GuardError`
  → passthrough (degrade); empty table → passthrough **without** calling the LLM.
- **answer_node:** includes the stats when present; unchanged when absent.
- **chain:** `execute → analyze → stats → answer` end-to-end with fakes (one case
  with a test, one `NONE` passthrough); existing efficacy/expression/mutation/
  modeling/Phase-1 chains still pass (stats is a transparent passthrough on `NONE`).
- **full offline suite + ruff** stay green.
- **live (real LLM + scipy/lifelines):** e.g. "is the day-21 tumor volume
  difference between the treated and control modeling groups significant for model
  X" → replica fetches the for_bd-filtered rows, DuckDB reshapes to (group, value),
  Welch t-test runs, the answer reports t, p, group means/n, and caveats. Report the
  replica SQL + DuckDB SQL + the stat request + the answer.
- **security review:** run `sql-security-reviewer` over the new stats validator /
  registry surface during execution (the mandatory security gate — the one allowed
  subagent exception to inline execution).

## Out of scope (deferred, not built here)

Multi-factor / two-way ANOVA, post-hoc tests (Tukey), regression, Cox proportional-
hazards, confidence-interval plotting, and any test not in the three-function
registry. New tests are pure registry additions once the framework lands.

## Risks

- **Library trust.** scipy and lifelines are the vetted implementations; we call
  pinned functions only and never expose them to LLM-chosen arguments beyond the
  validated column refs + bounded scalars.
- **matplotlib weight.** lifelines drags in matplotlib transitively; unused but
  installed. Accepted (see Dependencies). If install size becomes a problem, a
  follow-up can replace KM/log-rank with a hand-rolled numpy implementation behind
  the same registry interface — no caller change.
- **NaN / mixed-type columns.** rows are psycopg `dict_row` dicts; the runner
  coerces (Decimal→float, drops None/NaN per the test's input columns) before
  handing arrays to the library, and fail-softs on degenerate inputs.
