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

1. **Domain routing first.** Routing (in `run_agent`, NOT a graph node) picks
   every applicable domain. One domain → full pipeline; ≥2 (ambiguous) → fan out,
   querying each and returning labeled sections rather than asking which to use.
   Only that/those domains' tables + the `model_desc_info` spine feed SQL-gen
   context. Clarify is reserved for greetings/meta/out-of-scope. No naive schema RAG.
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

## Status (2026-06-25)

**Phase 1 MVP complete and live-verified** end-to-end through the FastAPI
endpoint. **Phase 2 complete + live-verified** — DuckDB post-processing, 13-test
stats inference, few-shot example retrieval, and two-stage rerank. The chronic
gateway 504 was root-caused + fixed (Qwen3 thinking mode), so the full chain is now
live-verified end-to-end. The chain (all layers built):

(Note: "Phase 1/2 MVP" above = the original build-out. A SEPARATE **optimization-
blueprint** track — referenced as "(Phase 1/2)" in the capability bullets below —
added the critic / value-alignment / JOIN-edge / EA-eval / structural-recall work;
its Phase 3 (Plan-and-Solve, multi-candidate) is deferred.)

```
domain route / clarify → context assembly (yaml + JOIN-edge graph) → SQL gen (qwen-code)
  → sqlglot validate + permission inject (sql/secure.py) → read-replica exec
  → self-correct on error (≤3) → critic (data-aware empty-result revision)
  → DuckDB analyze → vetted stats → NL answer + SQL
  (SSE-streamed token-by-token via POST /query/stream)
```

The whole chain is **async end-to-end**: `run_agent` / `run_agent_stream` are
coroutines, LLM calls await `acompletion` (streamed), DB stays sync via
`to_thread`. The answer **streams over SSE** (`POST /query/stream`).

Current capabilities (history/forensics live in git + `docs/superpowers/specs/` and
the subdir `CLAUDE.md` files — do not reproduce it here):

- **All layers built**: semantic / sql / db / llm / graph / api / observability.
- **5 routable domains**, data-driven via `routable_domains()`: `efficacy` + `modeling`
  (access-controlled), `expression` + `mutation` (not), and `model` (the spine itself).
  New domains/tables are pure `semantic_layer.yaml` additions — **zero source changes**
  (proven repeatedly). `expression`/`mutation` are gene-bearing big tables (EXPLAIN gate on
  `model_ccle_expression_data` ~36M and `model_ccle_mutation_data` ~5.5M).
- **model** domain: `model_desc_info` (the spine) + `model_rnaseq_mapping`. It owns
  *pure model-attribute/identifier* questions (model count, type PDX/CDX, cancer_type,
  name/ID, `rnaseq_id`) that no measurement domain covers — without it they fell to
  out-of-scope clarify. `model_desc_info` is also the **spine**: `spine_tables()` (pk ==
  `spine_key`) is injected into every domain's sql-gen context AND validator scope, so a
  measurement query can still JOIN/filter model attributes even though the spine is no
  longer in the `reference` domain.
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
- **data-aware self-correction (`critic` node)** — after a clean `execute`, the graph
  routes through `critic` (in both `build_graph` and `build_domain_graph`). On a
  **0-row** result it runs `sql/critic.py:diagnose_empty_result` (pure): if a filter
  compares a column with a closed `values` enum to a value outside that set (e.g.
  `is_cancer_model='T'`, a lung subtype string), it feeds a revision hint back to
  `generate_sql` **at most once** (`critic_used` flag + `max_sql_retries` budget). No
  signal → accept the empty result as real, so a legitimately-empty query (e.g. 吉非替尼
  filtered out by `for_bd`) never loops. Deterministic-only by default; `critic_llm_enabled`
  (default False) reserves an optional LLM critic. Toggle: `critic_enabled` (default True).
  **Value alignment (Phase 2):** if the enum check finds nothing, the critic calls
  `db/value_resolver.py:align_values` (DB-backed, injected via `Deps.align_values`) — for
  filters on `fuzzy_align`-flagged open-text columns (`drug_name`, `model_name`) it runs
  pg_trgm `similarity()` on the replica and, when the nearest *real* stored value DIFFERS
  from the user's term (typo/variant: "Docetaxe"→"Docetaxel"), revises. Returns None when the
  term already matches a stored value, so 吉非替尼 (a real drug filtered by `for_bd`) stays a
  correct 0-row answer. Toggle: `value_align_enabled` (default True); reuses `critic_used`.
- **structure-aware few-shot recall (DAIL-SQL, Phase 2, default off)** — `example_structural`
  adds a second recall channel: `retrieve_examples_node` drafts a cheap SQL (no examples),
  `examples/skeleton.py:skeletonize` de-parameterizes it (literals → `?`), and
  `ExampleStore.search_dual` fuses question-cosine + skeleton-cosine via RRF. The index
  (`build.py`) now stores `skeletons` + `skeleton_vectors`; an old index without them falls
  back to question-only recall. Costs one extra SQL-gen call when on. **See `examples/CLAUDE.md`.**
- **JOIN-edge graph injection** — `SemanticLayer.join_edges(domain)` synthesizes concrete
  `A.col = B.col` edges from structured metadata (`spine_key`/`access_via`/`join_to_hub`),
  NOT the YAML `relationships:` glob block; `_render_context` injects them as a "Join keys"
  list (gene_info excluded — never JOINed).
- **Execution-Accuracy eval** — `tests/eval/` (marker `eval`, deselected by default, needs
  replica DSN + gateway, mirrors the `integration` gate). `golden.yaml` holds verified
  `question → gold_sql`; the harness runs the agent and compares the **result set** (not SQL
  string) to the gold SQL's via order-insensitive value-multiset (`harness.rows_match`), then
  asserts an aggregate EA floor (0.7). Run: `uv run pytest -m eval -s`. EA <100% is expected
  (LLM nondeterminism); it's a regression gate, not a correctness proof.
- **observability**: per-run audit logging, **on by default**. Each run carries a
  `run_id` (also returned in the API response) + total `latency_ms`. Sink selection
  (`api/app.py` `_select_observer`): writable Postgres audit table
  (`DBAGENT_AUDIT_DB_DSN` → `db/audit.py` `AuditLog`, **separate writable role, never
  the read replica**) > explicit JSONL (`DBAGENT_OBSERVABILITY_LOG_PATH`) > default
  local JSONL (`logs/agent_runs.jsonl`). Each run stores the full `RunRecord`
  including `answer` text and a **capped sample of result rows** (`result_sample`,
  first `audit_result_sample_rows`=50; rowcount/truncated still reflect the full
  result) — dev-stage choice so reviewers see the actual data, not just counts.
  JSONL/Jsonb serialize with `default=str` (result rows may carry Decimal/datetime).
  Read it back via `observability/source.py` `read_records` (same precedence as the
  writer): `python -m db_agent.observability.report` (status mix / failure rate /
  retry dist / top errors / per-domain / latency p50-p95) and
  `python -m db_agent.observability.review --last N` (readable Q→SQL→result→answer
  stream, for eyeballing or feeding the log to an assistant to iterate). The
  `RunRecord.feedback` column is reserved (no UI feedback loop yet).
- **frontend**: a self-contained chat UI at `GET /` (`src/db_agent/web/index.html`,
  zero deps). Three status branches (answered/clarify/error); collapsible SQL +
  result table; auto-charting (bar / single & grouped multi-series line, inferred
  from columns). Streams the answer token-by-token over SSE; the final answer is rendered
  as a **GFM-subset markdown** (tables/bold/lists/code, zero deps). Preview offline via
  `.claude/launch.json` (`web-static`); end-to-end needs the running app
  (`uv run uvicorn db_agent.api.app:app`).

**LLM/gateway gotcha (important, cross-cutting):** Qwen3 models default to *thinking
mode* (long reasoning before the answer → heavy prompts blow past the gateway timeout;
this was the chronic "504" root cause). `LiteLLMClient` sends
`extra_body={"chat_template_kwargs": {"enable_thinking": False}}` (toggle
`Settings.llm_enable_thinking`, default False) — request `extra_body` overrides the
gateway's per-model config. The gateway also has `num_retries: 2`.

Still deferred (do not build until asked): **LLM gateway client-side retry/backoff**
(gateway already has `num_retries: 2`), and more stats tests (Fisher exact, Levene,
mixed/repeated-measures) — pure `sandbox/stats/registry.py` additions once asked. Also
**optimization Phase 3** (Plan-and-Solve decomposed generation + multi-candidate /
self-consistency voting) — deferred pending more EA golden data to justify the cost.

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
                   #   permission.py, secure.py (one-call bridge), errors.py,
                   #   critic.py (data-aware empty-result diagnosis, pure)
  db/              # Postgres boundary: replica.py (read-only pool + execute + fetch),
                   #   explain.py, mapping.py, result.py, gene_resolver.py,
                   #   value_resolver.py (pg_trgm value alignment for the critic);
                   #   audit.py (SEPARATE writable AuditLog for the run-log table)
  llm/             # LiteLLM client + prompts + tasks (route / generate_sql /
                   #   answer / extract_genes / analyze_sql / request_stat /
                   #   answer_stat); embedding.py (LiteLLMEmbeddingClient);
                   #   rerank.py (LiteLLMRerankClient, optional 2nd-stage rerank)
  examples/        # few-shot example retrieval: model.py (Example), store.py (local
                   #   .npz cosine index + search_dual RRF), build.py (offline builder + CLI),
                   #   retriever.py (request-time embed+search; off by default),
                   #   skeleton.py (SQL de-parameterization for structure-aware recall)
  sandbox/         # the ONLY DuckDB boundary: validator.py (analysis-SQL guard),
                   #   engine.py (locked-down in-memory DuckDBSandbox.run);
                   #   stats/ (Phase 2: vetted t-test/ANOVA/KM registry + validator
                   #   + runner, LLM emits {function,params} data, never code)
  graph/           # LangGraph: state.py (AgentState, Deps), nodes.py, build.py.
                   #   run_agent routes (1+ domains) then runs build_domain_graph per
                   #   domain: [extract→resolve]→assemble→retrieve_examples→generate_sql
                   #   →guard→execute→critic(→analyze→stats→answer if with_answer). ≥2 domains
                   #   fan out via asyncio.gather → AgentResult.results (labeled sections).
                   #   build_graph is the legacy single-domain graph (route node inside).
  mas/             # Multi-Agent System supervisor over the query engine (off unless
                   #   Settings.mas_enabled). router.classify_intent (qwen-fast, fails open to
                   #   'explore') → supervisor.run_mas[_stream] dispatch → workers/: explore
                   #   (delegates to run_agent[_stream], the adopted full agent), recommend
                   #   (Phase B: real recommender), vdr (Phase A stub: note + fall back to
                   #   explore). Same AgentResult/SSE contract; tags audit RunRecord.worker.
                   # recommender/ (Phase B): model.py (Criteria/RankedModel/Recommendation),
                   #   scoring.py (pure additive rank), pipeline.run_recommendation (extract
                   #   criteria → resolve genes → per-criterion candidate fetch (db/
                   #   recommend_queries.py, parameterized) → rank → efficacy evidence →
                   #   summary), report.py (jinja2 HTML; lazy-optional WeasyPrint PDF).
  api/             # FastAPI: app.py (create_app, POST /query/stream [SSE], POST /recommend,
                   #   GET /health, GET /); SSE emits token/final/error, final carries
                   #   QueryResponse. mas_enabled → run_mas_stream (req.agent override); else
                   #   run_agent_stream. /recommend → RecommendResponse (+report_html; ?format=pdf)
  web/             # single-file chat UI (index.html, inline CSS+JS, zero deps);
                   #   served at GET / via FileResponse; auto-charts numeric results
  observability/   # RunRecord (+result_sample) + sinks (Jsonl/Postgres/Null) +
                   #   source.read_records + report.py / review.py analysis CLIs
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

# Inspect real column values (read-only) when the LLM keeps guessing wrong:
#   ReadReplica(Settings()).fetch("SELECT DISTINCT col, count(*) ... GROUP BY 1")
# via .venv/Scripts/python.exe. NOTE: fetch() is parameterized, so a literal % in
# an ILIKE must be escaped as %% (psycopg placeholder gotcha).
#
# Live end-to-end replay of a question (hits the gateway):
#   await run_agent(q, llm=LiteLLMClient(s), replica=ReadReplica(s),
#       layer=load_semantic_layer(s.semantic_layer_path), settings=s)
# AgentResult fields: status / sql / result / answer / clarification / error /
# analysis_sql / stat_request / run_id / results (there is no `.domain`).
# Guard with asyncio.wait_for.
```

Note: modules still keep `from __future__ import annotations` and ruff stays on
`target-version = "py311"` so the code remains importable on 3.11 — keep this
unless 3.11 support is explicitly dropped.

## Gotchas

- **Column value semantics live in `semantic_layer.yaml`** via per-column
  `values:` (closed enum) / `examples:` (open vocab) / `language:` (en/zh). The
  loader parses them; `graph/nodes.py:_render_column` renders them into sql-gen
  context as `[one of: …]` / `[e.g. …]` / `[stored in …]`. When the LLM guesses a
  wrong stored value (→ 0 rows), document it HERE, not in the prompt. Known real
  values: `is_cancer_model` ∈ {cancer, no_cancer} (NOT T/true); `cancer_type` is
  coarse English histology (`Lung Carcinoma`, no NSCLC/SCLC — subtype is in
  `cancer_subtype_short_names` as short codes like `LUC`). `model_type` is the
  clean coarse enum (PDX/CDX/CDA/HISCDX/HISPDX/IMID/FB); `second_model_type`
  refines it with variant suffixes (CDX-IVIS/-ORT/PBMCCDX…) AND trailing spaces,
  so "CDX models" via `second_model_type LIKE 'CDX%'` returns MORE than
  `model_type='CDX'` (a real cause of differing result counts).
- **The NL answer's count comes from `result.rowcount`, not the model.** The
  answer LLM only sees a *truncated* row preview, so it must never recount or
  de-duplicate. Prompting alone was NOT enough — for a multi-row list the model
  reliably under-counts (e.g. "CT26的阳性药数据" → 11 distinct drugs instead of 48
  rows). So `answer_node` **deterministically prepends** an authoritative, language-
  aware "共查询到 N 条记录。 / Found N records." line (`agent_llm._record_count_prefix`,
  raw-result branch only, skipped for single-row aggregates) and tells the LLM via
  `answer_messages(count_prefixed=True)` to describe only, not restate a total.
- **LLM calls are greedy (`temperature=0`, `Settings.llm_temperature`).** A non-zero
  default made the *same* question return different SQL and different answer counts
  run-to-run (the "为什么每次结果都不一样" bug); greedy decoding makes generation
  near-deterministic and also lifted the EA benchmark to 100%.
- **The DuckDB `analyze` step may aggregate/reshape, never just filter rows.**
  `sandbox/validator.py` rejects a filter-only analysis (a WHERE/HAVING with no
  aggregate and no GROUP BY, e.g. `SELECT * FROM result WHERE drug_name NOT IN
  ('vehicle',…)`); such a reshape silently dropped rows so the answer described
  fewer than the result table (the 48→11 root cause). Row filtering belongs in the
  main SQL; on rejection `analyze_node` fail-soft returns `{}` and answers from the
  raw result.
- **Debugging a wrong/inconsistent answer count: check `AgentResult.analysis_sql`
  first.** If non-None, the answer describes the *reshaped* DuckDB result, while
  `.result` (the table) holds the raw rows — they can diverge. Three escalating
  answer-prompt rewrites failed to stop the undercount; the deterministic count
  prefix + the analyze filter-only guard fixed it. Lesson: for count/row-set
  correctness, prefer a deterministic guard or system-injected value over trying to
  prompt the model into compliance.
- **The multi-domain fan-out runs per-domain subgraphs concurrently**
  (`asyncio.gather` in `build.run_agent`). Offline fakes must be **content-aware**
  (decide replies by model + message text, e.g. the table name in the SQL context),
  NOT pop-order — and replicas must be thread-safe (no shared mutable list; DB
  `execute` runs in `to_thread`). See `_MultiLLM`/`_MultiReplica` in tests.
- **The model echoes `<angle-bracket>` placeholders literally** (Qwen once replied
  "out-of-scope note"). In prompts, give a filled example, not a bare placeholder.
- **Growth-curve `avg`/`sd` columns are 100% NULL** (both the efficacy and
  modeling variants). Aggregate `tumor_volume` and compute the mean yourself;
  never `MAX(avg)`.
- **Domain routing keys on the *measurement* the question needs** (expression /
  mutation / efficacy / modeling), NOT on model attributes — `model_type`,
  `cancer_type`, `model_name` sit on the shared `model_desc_info` spine and are
  available in every domain (so "HER2-high CDX models" is expression, not
  modeling). `modeling_panel_data.detection_item` is a flow-cytometry/immune
  panel, not gene expression.
- **sqlglot 30.x stores `FROM` under the `from_` arg key** (older versions used
  `from`). When walking a SELECT's direct sources, check both keys.
- A domain may be declared under `domains:` with no tables yet — a forward
  declaration, not an error; `routable_domains()` excludes it until it gains
  tables (this is the zero-code extension path). All five domains (efficacy /
  expression / mutation / modeling / model) are now defined and routable; none is
  currently pending.
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
  ambiguous. **SQL-gen never JOINs `gene_info`** — the gene is already resolved to a
  canonical symbol and injected, so it filters `gene_symbol = '<symbol>'` directly (a
  bare `g.Symbol` join was the #1 live error: PG folds it to `g.symbol` → "column does
  not exist", burning all 3 retries).
- **`gene_synonyms` is noisy & many-to-many** (~287K rows): a common alias like `PD1`
  maps to `{PDCD1, SNCA, SPATA2}`. `gene_resolver._decide` ranks multi-symbol matches by
  resemblance to the query (equality > prefix > subsequence > none) and auto-resolves the
  clear winner (`PD1` → `PDCD1`); only genuinely close ties still clarify. Species-casing
  disambiguation (`HER2` → human `ERBB2`) runs first and is preserved.
- **`drug_name` is mixed-language, NOT english** (`吉非替尼`, `Herceptin+Perjeta`,
  `Opdivo`): `language: mixed` so the model keeps the user's original term for ILIKE and
  does NOT translate (`吉非替尼`→`gefitinib` returned 0). Note a `吉非替尼` hit can still be
  0 rows *after* the `for_bd='yes'` permission filter — that's correct, not a bug. A column
  marked `fuzzy_align: true` in the yaml (currently `drug_name`, `model_name`) gets pg_trgm
  **value alignment** in the critic on a 0-row result (`db/value_resolver.py`); it only revises
  when the nearest real value differs from the user's term, so it never loops on a correct
  permission-empty result. `value_resolver` interpolates the table/column identifiers (trusted,
  from the validated layer) but ALWAYS binds the user value as a parameter.
- **`ReadReplica.execute`** secures + runs LLM SQL (EXPLAIN gate, LIMIT);
  **`ReadReplica.fetch(sql, params)`** is for trusted hand-written parameterized
  queries (e.g. gene resolution) — value always bound, never interpolated.
- **Tests:** `uv run pytest` is offline (DB/LLM faked, `integration` deselected);
  `uv run pytest -m integration` runs live-DB tests (needs `.env` DSN); `uv run pytest
  -m eval -s` runs the Execution-Accuracy benchmark (needs gateway + replica). The LLM client
  is **async** — offline fakes must make `complete` / `acompletion` coroutines, else
  the chain `await`s a plain value and breaks.
- `model_ccle_expression_data` is ~36M rows — the big-table EXPLAIN gate is real
  and live-verified (it rejects a `SELECT AVG(...) FROM` with no filter).
- **`.claude/` automations** (committed): PreToolUse confirm on edits to
  `sql/permission.py`/`validator.py`; PostToolUse ruff; a Stop hook that asks for
  the `sql-security-reviewer` subagent when `sql/` changed.

## Git

Develop directly on `main`. Commit with clear messages; push with
`git push -u origin main`. Do not open a PR unless explicitly asked.
