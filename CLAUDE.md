# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

A natural-language query & analysis agent over the company's **mouse tumor model
PostgreSQL database**. Users (both domain scientists and non-technical
management) ask in plain language; the agent routes to a domain, assembles
schema context, generates SQL, **validates and injects row-level permissions
deterministically**, runs it on a read-only replica, self-corrects on error,
**optionally post-processes the result set in a locked-down in-memory DuckDB**,
and answers in natural language while showing the SQL it ran.

When intent is ambiguous, the agent **clarifies rather than guesses**.

## Fixed decisions — do NOT relitigate

Tech stack is settled: **LangGraph** (orchestration), **LiteLLM** gateway with
aliases `qwen-main` / `qwen-fast` / `qwen-code` (SQL generation routes to
`qwen-code`), backed by **Qwen3.6-27B** on vLLM (internal), **PostgreSQL**
(always via read-only replica + restricted read-only role + `statement_timeout`),
**sqlglot** for SQL parse/validate, **FastAPI** service layer. Python 3.12+,
type hints + dataclasses, keep it simple — no over-engineering.

Architecture (already agreed, build to these):

1. **Domain routing first.** A light node decides the domain
   (efficacy / modeling / expression / mutation / reference), then only that
   domain's tables + the `model_desc_info` spine are fed into SQL-gen context.
   No naive schema RAG.
2. **Spine key** `model_uuid` joins everything to `model_desc_info`; omics side
   joins on `gene_symbol` to `gene_info."Symbol"` (capital S — case-sensitive,
   see Gotchas).
3. **Permission injection is deterministic, never the LLM's job.** After SQL
   generation, parse the AST with sqlglot and splice WHERE conditions based on
   policy. Detail tables carry no permission column — filter them via the hub.
4. **Big-table guard** for `model_ccle_expression_data` (tens of millions of
   rows): SELECT-only, force LIMIT, and `EXPLAIN`-gate any scan lacking a
   `model_uuid` / `gene_symbol` filter.
5. **Gene-name resolution** is deterministic (lookup tool), never guessed by the
   model.
6. Default expression table is `model_ccle_expression_data`.
7. **Self-correction loop**: on execution error, feed the error back and
   regenerate, **max 3 times**.
8. **Observability**: log every (question, retrieved context, generated SQL,
   result, feedback) tuple as seed data for a future example store.

## Source-of-truth inputs

- `semantic_layer.yaml` — the agent's map: in-scope tables, column meanings,
  domains, relationships, access rules, lookup tools. **The only context source.**
- `models.py` (Django, from inspectdb — *not* in this repo, provided as task
  input) — authoritative table structure. The DB has **no real foreign keys**
  (`db_constraint=False`); relationships come from `semantic_layer.yaml`. Ignore
  django/auth/rbac system tables, `m_`-prefixed mirror tables, and `*_stats`
  deprecated tables.

## Status (2026-06-22)

**Phase 1 MVP complete and live-verified** end-to-end through the FastAPI
endpoint. **Phase 2: DuckDB post-processing + stats inference built** (offline-
complete + security-reviewed; live e2e gated by the known gateway 504). The full
chain (all layers built):

```
domain route / clarify → context assembly (yaml) → SQL gen (qwen-code)
  → sqlglot validate + permission inject (sql/secure.py) → read-replica exec
  → self-correct (≤3) → DuckDB analyze → vetted stats → NL answer + SQL (POST /query)
```

Done:
- **All layers built**: semantic / sql / db / llm / graph / api / observability.
- **Multi-domain routing is data-driven** (`SemanticLayer.routable_domains()`):
  routes all four domains `{efficacy, expression, mutation, modeling}`.
- **expression** domain (gene expression; NOT access-controlled → no permission
  injection; the big-table EXPLAIN gate applies to `model_ccle_expression_data`).
- **mutation** domain (somatic mutations; NOT access-controlled; added
  2026-06-18, live-verified). `model_ccle_mutation_data` (big table, ~5.5M rows,
  gene-bearing) + `oncokb` clinical annotation (domain=mutation → fed only for
  mutation questions). Added as a **pure `semantic_layer.yaml` change** (zero
  source changes) — proof the data-driven extension path works.
- **modeling** domain (PDX/CDX 建模 characterization; **access-controlled**; added
  2026-06-18, live-verified + SQL-security-reviewed). Hub `modeling_attr_info`
  (`for_bd='yes'`) + **8 detail tables** (tumor_volume / body_weight / survival,
  then facs / avg_radiance / total_flux / elisa / pathology added 2026-06-18 batch
  2) filtered by `EXISTS` semi-join on `(model_uuid, model_no, group_id)`. Added as
  a **pure `semantic_layer.yaml` change** (zero source changes) — the **first
  access-controlled domain added via config**, exercising the real permission-
  injection path (not the no-op). `modeling_panel_data` is intentionally excluded
  (no `group_id` → can't use the 3-key semi-join without coarsening the permission
  grain; revisit only with an explicit grain decision).
- **resolve_gene** tool (`db/gene_resolver.py`): deterministic gene-name →
  canonical symbol (case-sensitive exact + pg_trgm fuzzy as clarify-only
  candidates).
- **observability**: optional per-run JSONL log (`DBAGENT_OBSERVABILITY_LOG_PATH`).
- **DuckDB result-post-processing sandbox** (Phase 1; added 2026-06-18,
  live-verified + SQL-security-reviewed). `sandbox/` is the only DuckDB boundary;
  the graph runs `execute → analyze → answer`, where `analyze` lets the LLM
  optionally emit ONE DuckDB `SELECT` over the result set (table `result`) for
  descriptive stats / reshaping / correlations. **Locked down**: in-memory +
  `enable_external_access=false` + a sqlglot SELECT-only validator (only `result`,
  no file/network/attach funcs incl. the dedicated `read_csv`/`read_parquet`
  nodes) + the sandbox only ever sees already-permission-filtered rows + **fail-
  soft** (any GuardError → degrade to the raw-result answer). Injected via
  `Deps.run_sandbox`.
- **stats sandbox Phase 2** (real statistical inference; added 2026-06-22,
  offline-complete + SQL-security-reviewed SOUND; live e2e blocked only by the
  known gateway 504 gap). New pure subpackage `sandbox/stats/` (spec / validator /
  registry / functions / runner). A new `stats` node runs AFTER `analyze`:
  `execute → analyze (DuckDB reshape) → stats (vetted test) → answer`. The LLM
  emits ONLY a structured `{function, params}` JSON request (data, never code);
  `validate_stat_request` checks it against the frozen `REGISTRY` allowlist + the
  current table's columns + scalar bounds, then a hand-written impl calls
  scipy/lifelines. Three vetted tests: **Welch t-test**, **one-way ANOVA**,
  **Kaplan-Meier + log-rank** (named test + caveats, no auto-switching). Dispatch
  is only ever through the registry dict (no dynamic import); pure in-memory compute
  (no file/network/DB); **fail-soft** (any GuardError → degrade to the descriptive
  answer); independent row cap + typeless-scalar reject as defense in depth. Reads
  the post-DuckDB table if present, else the raw result. Injected via `Deps.run_stat`.

`resolve_gene` is now **wired into the question flow** (Plan B, executed
2026-06-18, live-verified): a gene-bearing domain (`is_gene_bearing`) routes
`route → extract_genes (LLM lists mentions) → resolve_genes (deterministic) →
clarify | assemble_context`. All-resolved injects a canonical-symbol map into the
sql-gen context; any ambiguous/unknown short-circuits to clarify. The resolver is
injected via `Deps.resolve_gene` (default = real `db.resolve_gene`) so the graph
stays offline-testable. Design specs + plans live under `docs/superpowers/`.

**Gateway 504 root cause FOUND + FIXED (2026-06-22):** the chronic "transient" 504s
were NOT a flaky gateway — the Qwen3 models default to **thinking mode**, emitting
long reasoning before the answer, which on heavier prompts (SQL-gen) blows past the
gateway's upstream timeout. `LiteLLMClient` now sends
`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` (toggle via
`Settings.llm_enable_thinking`, default False). qwen-code SQL-gen dropped from
504-timeout to ~2.6s; **full stats Phase 2 chain live-verified end-to-end** (Welch
t-test fired through the stats node: t=-19.84, p=1.75e-53, per-group n/means + normality
caveat, on for_bd-filtered rows).

**Few-shot example retrieval built (2026-06-22, off by default).** New `examples/`
package: an offline CLI (`python -m db_agent.examples.build <obs.jsonl> <out.npz>`)
ingests the observability log, keeps `status=="answered"` runs, dedups, embeds each
`question` via `qwen-embedding`, and writes a local `.npz` vector index (NOT in the
read-only replica). A new `retrieve_examples` node (`assemble_context →
retrieve_examples → generate_sql`) embeds the incoming question, does cosine top-k
over the **same-domain** examples, and injects the `(question → raw_sql)` pairs into
`sql_messages` as few-shot reference. **Uses `raw_sql`, never the secured SQL** — so
examples never teach the model to write permission filters (those stay deterministic).
**Off until `Settings.example_index_path` is set** (default None → no-op retriever,
zero extra calls); **fail-soft** (missing/corrupt index or embed failure → no
examples, generation proceeds as before). Embedding seam is `llm/embedding.py`
(`LiteLLMEmbeddingClient`), injected via `Deps.retrieve_examples`. `qwen-reranker`
two-stage rerank is the deferred follow-up.

Still deferred (do not build until asked): `modeling_panel_data` (needs a
permission-grain decision, see above), **LLM gateway retry/backoff** (nice-to-have now
that the 504 root cause is fixed — still worth adding for genuine transient blips),
`qwen-reranker` rerank stage for example retrieval, and more stats tests (two-way
ANOVA, post-hoc, Cox regression) — pure `sandbox/stats/registry.py` additions once
asked.

### Permission policy (Phase 1, confirmed with the user)

A single **constant** rule — no per-user concept yet, everyone has the same
access:

- Always filter `model_efficacy_info.for_bd = 'yes'`.
- **No** `drug_classification` allow-listing, **no** `for_model`, **no**
  `RuleModel` (that Django code exists but was never actually used).
- Detail tables (`model_efficacy_tumor_volume_growth_curve_data`,
  `model_efficacy_tgi_tv_data`, `model_efficacy_survival_data`) have no
  permission column, so filter them with a correlated **`EXISTS`** back to the
  hub on `(model_uuid, efficacy_num, group_id)` — a semi-join (confirmed over a
  real JOIN) so detail rows are never multiplied.

## Layout

```
src/db_agent/
  config.py        # Settings (replica DSN, guard limits, LiteLLM aliases via
                   #   AliasChoices for deployed env names, observability_log_path)
  semantic/        # frozen dataclasses from semantic_layer.yaml; routable_domains(),
                   #   is_gene_bearing(), tables_in_domain()
  sql/             # PURE guard rails (AST in, secured AST out): validator.py,
                   #   permission.py, secure.py (one-call bridge), errors.py
  db/              # the ONLY I/O boundary: replica.py (pool + execute + fetch),
                   #   explain.py, mapping.py, result.py, gene_resolver.py
  llm/             # LiteLLM client + prompts + tasks (route / generate_sql /
                   #   answer / extract_genes / analyze_sql / request_stat /
                   #   answer_stat); embedding.py (LiteLLMEmbeddingClient)
  examples/        # few-shot example retrieval: model.py (Example), store.py (local
                   #   .npz cosine index), build.py (offline builder + CLI),
                   #   retriever.py (request-time embed+search; off by default)
  sandbox/         # the ONLY DuckDB boundary: validator.py (analysis-SQL guard),
                   #   engine.py (locked-down in-memory DuckDBSandbox.run);
                   #   stats/ (Phase 2: vetted t-test/ANOVA/KM registry + validator
                   #   + runner, LLM emits {function,params} data, never code)
  graph/           # LangGraph: state.py (AgentState, Deps), nodes.py, build.py.
                   #   Flow: route → [extract→resolve] → assemble → retrieve_examples
                   #   → generate_sql → guard → execute → analyze → stats → answer
  api/             # FastAPI: app.py (create_app, POST /query, GET /health)
  observability/   # RunRecord + JsonlObserver (optional per-run logging)
tests/             # offline default (no DB/LLM); tests/integration/ is -m integration
```

Layering intent: `sql/` and `sandbox/` are pure guard rails (no external I/O) so
they stay unit-testable; `db/` is the only Postgres boundary, `sandbox/` the only
DuckDB boundary; `graph/` nodes stay thin and push logic into `sql/`/`db/`/`llm/`/
`sandbox/`. **Dependency injection:** external deps live in `graph.state.Deps`;
nodes are bound with `functools.partial(node, deps=deps)`; `run_agent` takes
`observer=` / `resolve_gene=` / `run_sandbox=` overrides so the whole graph is
offline-testable with fakes.

## Conventions

- Type hints everywhere; `from __future__ import annotations` at the top of each
  module (keeps modules importable on 3.11 for local testing even though the
  project targets 3.12+).
- Dataclasses for data; **frozen** for anything loaded once and read many
  (semantic layer, configs).
- Guard modules **fail closed**: if a query can't be safely secured, raise a
  fatal `GuardError`, never execute.
- `GuardError.retryable` drives the self-correction loop:
  - `retryable=False` (fatal, no retry): not read-only, multi-statement,
    out-of-scope table, banned function, big-table scan, injection failure.
  - `retryable=True`: parse errors and (later) bad-column/type DB errors — fed
    back to regeneration, up to 3 times.

## Commands

```bash
# Project env is a uv-managed .venv on Python 3.14 (already created). Use it for
# all dev / debug / test. requires-python is >=3.12; runtime is 3.14.
uv sync --extra dev     # install/refresh deps incl. pytest + ruff, updates uv.lock
uv run pytest
uv run ruff check src tests && uv run ruff format src tests

# Equivalent without uv (the venv python directly):
.venv/Scripts/python.exe -m pytest        # Windows
```

Note: modules still keep `from __future__ import annotations` and ruff stays on
`target-version = "py311"` so the code remains importable on 3.11 — keep this
unless 3.11 support is explicitly dropped.

## Gotchas

- **sqlglot 30.x stores `FROM` under the `from_` arg key** (older versions used
  `from`). When walking a SELECT's direct sources, check both keys.
- A domain may be declared under `domains:` with no tables yet — a forward
  declaration, not an error; `routable_domains()` excludes it until it gains
  tables (this is the zero-code extension path). All four business domains
  (efficacy / expression / mutation / modeling) are now defined and routable; none
  is currently pending.
- The permission injector must snapshot SELECT scopes **before** mutating, and
  tag its generated `EXISTS` sub-select, so a second pass doesn't re-enter and
  double-filter (idempotency).
- **DB is PostgreSQL 16 (`db_dev`); `pg_trgm` is installed.** Use the
  `similarity()` *function* for fuzzy match, NOT the `%` operator (it clashes with
  psycopg's parameter placeholders).
- **Gene symbol casing encodes species**: human is upper (`EGFR`, `TP53`), mouse
  is title-case (`Egfr`, `Trp53`). `gene_info`'s column is `"Symbol"` (capital S
  → must double-quote in SQL). Gene matching is therefore **case-sensitive** — a
  case-insensitive match collapses `EGFR`/`Egfr` and makes nearly everything
  ambiguous.
- **`ReadReplica.execute`** secures + runs LLM SQL (EXPLAIN gate, LIMIT);
  **`ReadReplica.fetch(sql, params)`** is for trusted hand-written parameterized
  queries (e.g. gene resolution) — value always bound, never interpolated.
- **Tests:** `uv run pytest` is offline (DB/LLM faked, `integration` deselected);
  `uv run pytest -m integration` runs live-DB tests (needs `.env` DSN).
- `model_ccle_expression_data` is ~36M rows — the big-table EXPLAIN gate is real
  and live-verified (it rejects a `SELECT AVG(...) FROM` with no filter).
- **`.claude/` automations** (committed): PreToolUse confirm on edits to
  `sql/permission.py`/`validator.py`; PostToolUse ruff; a Stop hook that asks for
  the `sql-security-reviewer` subagent when `sql/` changed.

## Git

Develop directly on `main`. Commit with clear messages; push with
`git push -u origin main`. Do not open a PR unless explicitly asked.
