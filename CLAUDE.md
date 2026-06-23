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

## Status (2026-06-23)

**Phase 1 MVP complete and live-verified** end-to-end through the FastAPI
endpoint. **Phase 2 complete + live-verified** — DuckDB post-processing, 13-test
stats inference, few-shot example retrieval, and two-stage rerank. The chronic
gateway 504 was root-caused + fixed (Qwen3 thinking mode), so the full chain is now
live-verified end-to-end. The chain (all layers built):

```
domain route / clarify → context assembly (yaml) → SQL gen (qwen-code)
  → sqlglot validate + permission inject (sql/secure.py) → read-replica exec
  → self-correct (≤3) → DuckDB analyze → vetted stats → NL answer + SQL (POST /query)
```

Current capabilities (history/forensics live in git + `docs/superpowers/specs/` and
the subdir `CLAUDE.md` files — do not reproduce it here):

- **All layers built**: semantic / sql / db / llm / graph / api / observability.
- **4 routable domains**, data-driven via `routable_domains()`: `efficacy` + `modeling`
  (access-controlled) and `expression` + `mutation` (not). New domains/tables are pure
  `semantic_layer.yaml` additions — **zero source changes** (proven repeatedly).
  `expression`/`mutation` are gene-bearing big tables (EXPLAIN gate on
  `model_ccle_expression_data` ~36M and `model_ccle_mutation_data` ~5.5M).
- **modeling** (access-controlled): hub `modeling_attr_info` (`for_bd='yes'`) + 9 detail
  tables filtered by correlated **`EXISTS`** semi-join. Most join on
  `(model_uuid, model_no, group_id)`; `modeling_panel_data` is model-level → **2-key**
  `(model_uuid, model_no)` "any-visible" grain (the injector is key-count generic).
- **resolve_gene** wired into gene-bearing domains: `route → extract_genes →
  resolve_genes → clarify | assemble`; deterministic (case-sensitive exact + pg_trgm
  fuzzy as clarify-only), injected via `Deps.resolve_gene`, offline-testable.
- **DuckDB post-processing sandbox** (`analyze` node, the only DuckDB boundary) — see
  the `sandbox/` Gotchas + `Deps.run_sandbox`.
- **stats inference** — 13 vetted tests via the `stats` node. **See
  `src/db_agent/sandbox/stats/CLAUDE.md`.**
- **few-shot example retrieval + optional two-stage rerank** (off by default). **See
  `src/db_agent/examples/CLAUDE.md`** (incl. the reranker `hosted_vllm` gateway-config
  requirement).
- **observability**: optional per-run JSONL (`DBAGENT_OBSERVABILITY_LOG_PATH`).

**LLM/gateway gotcha (important, cross-cutting):** Qwen3 models default to *thinking
mode* (long reasoning before the answer → heavy prompts blow past the gateway timeout;
this was the chronic "504" root cause). `LiteLLMClient` sends
`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` (toggle
`Settings.llm_enable_thinking`, default False) — request `extra_body` overrides the
gateway's per-model config. The gateway also has `num_retries: 2`.

Still deferred (do not build until asked): **LLM gateway client-side retry/backoff**
(gateway already has `num_retries: 2`), and more stats tests (Fisher exact, Levene,
mixed/repeated-measures) — pure `sandbox/stats/registry.py` additions once asked.

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
                   #   answer_stat); embedding.py (LiteLLMEmbeddingClient);
                   #   rerank.py (LiteLLMRerankClient, optional 2nd-stage rerank)
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
