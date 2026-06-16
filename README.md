# DB-Agent

Natural-language query & analysis agent for the mouse tumor model PostgreSQL
database. Users ask in plain language; the agent routes to a domain, assembles
schema context from the semantic layer, generates SQL (qwen-code), **validates
and injects row-level permissions deterministically**, runs against a read-only
replica, self-corrects on error, and answers in natural language while showing
the SQL it ran.

## Status — Phase 1 MVP (efficacy domain) — complete

The end-to-end chain is built, fully unit-tested offline, and verified against a
live LiteLLM gateway + read replica (HTTP layer included):

```
intent route / clarify → context assembly (yaml) → SQL gen (qwen-code)
  → sqlglot validate + permission inject → read-replica exec → self-correct (≤3)
  → NL answer + generated SQL          (exposed via POST /query)
```

### Modules

| Module | Path | What it does |
| --- | --- | --- |
| Semantic layer | `src/db_agent/semantic/` | Loads & validates `semantic_layer.yaml` into typed, frozen dataclasses (the agent's only map). |
| SQL guards | `src/db_agent/sql/` | `validator.py` (single-statement, read-only, table allow-list, banned functions, LIMIT enforce/clamp, big-table EXPLAIN gate), `permission.py` (deterministic row-level injection), `secure.py` (one-call bridge → secured SQL + flags). |
| Read replica | `src/db_agent/db/` | Sync psycopg pool to the read-only replica: per-connection `read_only` + `statement_timeout`, node-type EXPLAIN gate, SQLSTATE → `GuardError` mapping. |
| LLM | `src/db_agent/llm/` | `LLMClient` protocol + `LiteLLMClient` (gateway), pure prompt builders, and the route / generate-SQL / answer tasks. |
| Graph | `src/db_agent/graph/` | LangGraph `StateGraph` wiring the chain; `run_agent(...)`; self-correction & clarification as conditional edges. |
| API | `src/db_agent/api/` | FastAPI `POST /query` + `GET /health` over `run_agent`. |
| Observability | `src/db_agent/observability/` | Optional per-run JSONL logging of the (question, context, SQL, result-summary, outcome) tuple. |

### Permission policy (Phase 1)

A single constant rule, never decided by the LLM: efficacy queries only see rows
where `model_efficacy_info.for_bd = 'yes'`. The injector only ever **AND**s this
predicate on (it can narrow, never widen). Detail tables (growth curve / TGI /
survival) carry no permission column, so they are filtered with an `EXISTS`
semi-join back to the hub on `(model_uuid, efficacy_num, group_id)` — a semi-join
(not a real JOIN) so detail rows are never multiplied. No per-user concept yet.

### Deferred to Phase 2/3

Stats sandbox, pgvector example retrieval (this logging feeds it), the
modeling/expression/mutation domains, DuckDB, real `resolve_gene`, streaming/auth,
multi-turn clarification, and gateway retry/backoff.

## Develop

The project uses a **uv-managed `.venv` on Python 3.14** (`requires-python >=3.12`;
modules keep `from __future__ import annotations` so they stay importable on 3.11).

```bash
uv sync --extra dev                          # deps incl. pytest + ruff
uv run pytest                                # offline suite (no DB, no LLM)
uv run ruff check src tests && uv run ruff format src tests
```

### Tests

The default suite is **strictly offline** — no database, no LLM (LLM/DB are
injected as fakes). Live integration tests are opt-in:

```bash
uv run pytest                  # offline only (integration auto-deselected)
uv run pytest -m integration   # live DB tests (needs DBAGENT_REPLICA_DSN)
```

## Run the API

```bash
uv run uvicorn db_agent.api.app:app --host 127.0.0.1 --port 8000

curl -s localhost:8000/health
curl -s localhost:8000/query \
  -H 'content-type: application/json' \
  -d '{"question": "How many efficacy models are marked for BD?"}'
```

Response: `{status, answer, sql, clarification, error, rows}`. Agent outcomes
(`answered` / `clarify` / `error`) are HTTP 200 with a `status` field; an
infrastructure failure (gateway/DB unreachable) is HTTP 502.

## Configuration

Copy `.env.example` to `.env` (gitignored). Settings accept both the
`DBAGENT_`-prefixed names and the deployed gateway's names.

| What | Env var(s) | Notes |
| --- | --- | --- |
| Read replica DSN | `DBAGENT_REPLICA_DSN` | A restricted **read-only** role on the replica. URL or `host=... user=... password=...` form. |
| Statement timeout | `DBAGENT_STATEMENT_TIMEOUT_MS` | Default 15000. |
| Guard limits | `DBAGENT_DEFAULT_LIMIT`, `DBAGENT_MAX_LIMIT` | Default 1000 / 10000. |
| Self-correction budget | `DBAGENT_MAX_SQL_RETRIES` | Default 3. |
| LiteLLM gateway | `LITELLM_BASE_URL`, `LITELLM_MASTER_KEY` | (or `DBAGENT_LITELLM_BASE_URL` / `DBAGENT_LITELLM_API_KEY`). |
| Model aliases | `MODEL_MAIN`, `MODEL_FAST`, `MODEL_CODE` | qwen-main / qwen-fast / qwen-code (or `DBAGENT_MODEL_ROUTE` / `_FAST` / `_SQL`). |
| Run logging (optional) | `DBAGENT_OBSERVABILITY_LOG_PATH` | e.g. `logs/runs.jsonl`. Unset = disabled. |

## Layout

```
src/db_agent/
  config.py        semantic/        sql/        db/
  llm/             graph/           api/        observability/
tests/             tests/integration/   (live-DB, -m integration)
docs/superpowers/  specs/ + plans/  (design specs & implementation plans)
```

See `CLAUDE.md` for the fixed architectural decisions and conventions.
