# DuckDB Result Post-Processing Sandbox (Phase 1) Design

**Date:** 2026-06-18
**Status:** Approved (architecture + security model), pending spec review
**Scope:** Phase 1 only — DuckDB post-processing of a query's result set. Phase 2
(controlled statistical inference: t-test / ANOVA / KM via a vetted function set)
is a **separate** future spec, not built here.

## Goal

After the agent fetches a permission-filtered result set from the read replica,
optionally run **one locked-down DuckDB SELECT** over those rows (in-process,
in-memory) to do post-processing that plain answer-formatting can't — descriptive
stats, pivots/reshaping, correlations, quantiles, multi-step aggregation — then
answer from that. Triggered automatically as a second step (no new routing path).

## Architecture

A new package `src/db_agent/sandbox/` is the **only place that touches DuckDB**
(mirrors `db/` as the only Postgres boundary). It is pure compute on data already
in memory — no external I/O.

- `sandbox/validator.py` (pure) — `validate_analysis_sql(sql) -> exp.Expression`
  or raise `GuardError`. Parses with sqlglot `dialect="duckdb"`; asserts a single
  read-only `SELECT` that references only the table `result`, with no banned
  constructs/functions. Reuses `db_agent.sql.errors.GuardError`.
- `sandbox/engine.py` — `DuckDBSandbox.run(columns, rows, sql) -> QueryResult`:
  opens a fresh locked-down in-memory DuckDB, registers the rows as table
  `result`, runs the (already-validated) SELECT, returns a `QueryResult` (reusing
  `db_agent.db.result.QueryResult`).

`graph/` stays thin: a new `analyze_node` calls the LLM (decide + generate DuckDB
SQL) and the sandbox; logic lives in `sandbox/` + `llm/`. The sandbox runner is
injected via `Deps.run_sandbox` (default = the real `DuckDBSandbox.run`) so the
graph is offline-testable with a fake.

## Security model (non-negotiable — the core of "sandbox")

DuckDB by default can read local files (`read_csv`/`read_parquet`/`glob`), `ATTACH`
databases, `INSTALL`/`LOAD` extensions, and (with httpfs) reach the network. All of
it is disabled, with defense in depth:

1. **Locked-down connection:** in-memory (`:memory:`), created fresh per analysis,
   with `enable_external_access = false` (disables filesystem access, remote
   access, and extension autoload in one setting). No file-backed DB is ever used.
2. **sqlglot guard rail (suspenders over the connection's belt):** the analysis
   SQL must be a single statement, a read-only `SELECT`, referencing only the
   `result` table; reject any DDL/DML (`INSERT`/`UPDATE`/`DELETE`/`CREATE`/…),
   `ATTACH`/`COPY`/`PRAGMA`/`SET`/`INSTALL`/`LOAD`, and any file/network function
   (`read_csv`, `read_csv_auto`, `read_parquet`, `parquet_scan`, `read_json`,
   `read_json_auto`, `glob`, `read_text`, `read_blob`). Fail closed (raise
   `GuardError`) on anything else.
3. **Data isolation:** the sandbox only ever sees the **already-permission-filtered
   result rows** (`state["result"].rows`, already constrained by for_bd / the
   big-table EXPLAIN gate / LIMIT). It never has the replica DSN, credentials, or
   any connection to the real database. A sandbox escape can expose only data the
   user already received.
4. **Fail-soft degrade:** analysis is *additive*. If the LLM declines, or the
   generated SQL can't be validated, or the sandbox raises, the `analyze_node`
   **skips analysis and the answer falls back to the raw result** — it never turns
   a good answer into an error. (Contrast with the replica path, which fails
   closed: there, an unsecured query must not run; here, the data is already safe,
   so the safe degrade is "answer from the raw rows".)

## Flow

```
route → … → guard → execute → analyze → answer
                                  │
                                  ├─ result empty/absent → passthrough (no analysis)
                                  ├─ LLM says NONE       → passthrough
                                  └─ LLM emits DuckDB SQL → validate → sandbox.run
                                        ├─ ok    → state["analysis"] = QueryResult
                                        └─ Guard/DuckDB error → passthrough (degrade)
```

- `execute` already returns the full (LIMIT-bounded) rows in `QueryResult.rows`, so
  no change to fetching — `analyze` reuses what's in `state["result"]`.
- `answer_node`: if `state["analysis"]` is set, answer from the analysis output and
  show both the replica SQL and the DuckDB analysis SQL; otherwise unchanged.

## LLM task

`llm/agent_llm.py` gains `analyze_sql(client, settings, question, columns, preview)
-> str`: a prompt (routed to `qwen-code`) that is given the question and the result
table's columns + a small row preview, and returns either the single word `NONE`
(no post-processing needed) or one DuckDB `SELECT ... FROM result …`. Prompt lives
in `llm/prompts.py` (`analysis_messages`). The model only proposes SQL; the
sandbox validator + locked connection enforce safety deterministically.

## State / DI changes

- `AgentState`: add `analysis: QueryResult | None` and `analysis_sql: str | None`
  (both default None in `initial_state`).
- `Deps`: add `run_sandbox: Callable[[list[str], list[dict], str], QueryResult]`
  with default `DuckDBSandbox().run`.
- `run_agent(...)`: add `run_sandbox=None` override (threaded into `Deps`) for
  offline tests, matching the existing `resolve_gene=` pattern.
- `graph/build.py`: insert `analyze` node between `execute` and `answer`
  (`after_execute`'s `"answer"` branch now points at `analyze`; `analyze → answer`).
  The retry/fatal branches of `after_execute` are unchanged.
- Observability: `RunRecord` gains `analysis_sql` (best-effort, like the other
  fields) so the analysis step is logged too.

## Dependencies

Add `duckdb` to `pyproject.toml` (runtime dep). `uv sync` installs it.

## Testing

- **Sandbox validator (offline, pure):** accepts `SELECT avg(tumor_volume) FROM
  result`; rejects `read_csv_auto('x')`, `ATTACH 'y'`, `COPY …`, `PRAGMA …`, a
  non-SELECT, a multi-statement string, and a query referencing any table other
  than `result`.
- **Sandbox engine (offline, real duckdb):** register rows → `SELECT count(*)`,
  `avg`, `quantile`, `corr` return correct values; `enable_external_access=false`
  makes `read_csv_auto('<any path>')` fail (proves file access is blocked even if
  the validator were bypassed).
- **analyze_node (fake LLM + fake/real sandbox):** `NONE` → passthrough (no
  `analysis`); valid SQL → `state["analysis"]` populated; a `GuardError` from
  validation → passthrough (degrade, no error); empty result → passthrough without
  calling the LLM.
- **answer_node:** uses `analysis` when present, else the raw result.
- **chain:** `execute → analyze → answer` end-to-end with fakes (one case with
  analysis, one NONE passthrough); existing efficacy/expression/mutation/modeling
  chains still pass (analyze is a transparent passthrough when NONE).
- **Full offline suite + ruff** stay green.
- **Live (real LLM + DuckDB):** a question like "average tumor_volume per group on
  day 21 for model X's modeling groups" → the replica fetches the rows (for_bd
  filtered), DuckDB computes the per-group average, the answer reflects it. Report
  the replica SQL + the analysis SQL + the answer.

## Out of scope (Phase 2, separate spec)

Statistical inference needing a real stats library (t-test, ANOVA, regression,
Kaplan-Meier survival) — that requires a vetted Python function surface and its
own security design. Not built here.

## Risks

- **Lockdown must be proven, not assumed.** `duckdb` is not yet installed, so the
  plan's first task installs it and *demonstrates* `enable_external_access=false`
  blocks a file read before anything else is built. If that setting does not block
  file access in the installed version, STOP and redesign the lockdown (e.g.
  per-statement function denylist + a restricted DuckDB build) before proceeding.
- **Row volume:** the result set is already LIMIT-bounded (≤ the guard's max, ~1000
  rows), so in-memory DuckDB load is cheap; no streaming needed.
- **Column typing:** rows are psycopg `dict_row` dicts; register them via DuckDB's
  Python value binding (e.g. build the `result` table from the list of dicts).
  Mixed/None values are handled by DuckDB's type inference; the plan pins how the
  table is created from the rows.
