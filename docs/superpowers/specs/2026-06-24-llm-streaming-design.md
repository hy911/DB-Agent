# LLM Streaming — Design

Date: 2026-06-24
Status: Phase 1 approved for implementation; Phase 2 deferred.

## Motivation

`LiteLLMClient.complete` issues a single non-streaming `litellm.completion` call.
For heavy prompts (notably `generate_sql`) the gateway connection sits idle while
the model generates, which historically tripped the upstream timeout (the chronic
"504"). Streaming keeps chunks flowing over the connection, so it stays alive for
the full generation. Reference: https://docs.litellm.ai/stream

The agent chain has six LLM call sites (route / extract_genes / generate_sql /
analyze_sql / request_stat) which are internal structured outputs, plus answer /
answer_stat which are the user-facing NL. All of them flow through the single
`LiteLLMClient.complete` seam.

## Decision

Two phases. **Phase 1 (this work): internal accumulating stream.** Phase 2
(deferred): end-to-end SSE to the frontend.

No config toggle — `complete` always streams (decided with the user).

## Phase 1 — Internal accumulating stream

`LiteLLMClient.complete` switches to `litellm.completion(..., stream=True)`,
iterates the chunk stream accumulating `chunk.choices[0].delta.content`
(guarding the `None` content on role-only / finish chunks), and returns the
joined string.

The method **signature and return type are unchanged** (`complete(model,
messages) -> str`). Therefore:

- `LLMClient` Protocol is unchanged.
- `llm/agent_llm.py` tasks, `graph/` nodes, `api/app.py`, and the frontend are
  untouched.
- The five fake-LLM tests that implement the Protocol directly are untouched.

`extra_body` (thinking toggle), `timeout`, `api_base`, `api_key` are preserved.
No usage tracking (no `stream_options`), no new dependency, no settings change.

### Files

- `src/db_agent/llm/client.py` — `complete` body: add `stream=True`, iterate +
  accumulate, return `"".join(parts)`.
- `tests/test_llm_client.py` — fake `completion` returns a chunk iterator (each
  with `.choices[0].delta.content`), including a trailing `content=None` chunk to
  exercise the guard. Add `assert capture["stream"] is True`. Existing assertions
  (`extra_body`, `model`, output `== "SELECT 1"`) still hold.

### Out of scope (Phase 2, not built)

`POST /query/stream` SSE endpoint streaming only the answer node; frontend
fetch-stream consumption.

## Phase 1b — Full-chain async (follow-up, approved)

Phase 1 streamed synchronously. Follow-up: make the whole call chain async so the
streaming LLM I/O is truly non-blocking (`litellm.acompletion(stream=True)` +
`async for`). This also lays the groundwork for the Phase 2 SSE endpoint.

### Key mechanism

Under `await graph.ainvoke(state)`, LangGraph runs **sync** node functions in a
threadpool (non-blocking) and **awaits** async node functions. So only nodes that
do LLM I/O become `async`; pure/DB nodes stay sync and run in the executor.

### Changes

- `client.py`: `LLMClient.complete` Protocol and `LiteLLMClient.complete` become
  `async def`, using `await litellm.acompletion(..., stream=True)` + `async for`.
- `agent_llm.py`: the 7 LLM task functions (`route`, `extract_genes`,
  `generate_sql`, `analyze_sql`, `request_stat`, `answer`, `answer_stat`) become
  `async def` and `await client.complete(...)`. Pure helpers unchanged.
- `nodes.py`: LLM-calling nodes (`route_node`, `extract_genes_node`,
  `generate_sql_node`, `analyze_node`, `stats_node`, `answer_node`) become
  `async def`. The sync `run_sandbox`/`run_stat` calls inside `analyze_node`/
  `stats_node` are wrapped in `await asyncio.to_thread(...)`. DB-only/pure nodes
  (`resolve_genes_node`, `assemble_context_node`, `retrieve_examples_node`,
  `guard_node`, `execute_node`) and all routers stay sync.
- `build.py`: `run_agent` becomes `async def` using `await graph.ainvoke(...)`.
  No sync wrapper — the chain is async end to end. Observer call stays sync
  (best-effort).
- `app.py`: `query` endpoint becomes `async def` awaiting `run_agent(...)`.

### Decision: no sync wrapper

`run_agent` is `async def` outright. A sync wrapper would not save test churn,
because the async chain must `await` the fake clients, so every fake `complete`
becomes `async def` regardless.

### Tests

- Dev dep `pytest-asyncio` added; `asyncio_mode = "auto"` in pytest config.
- All fake `complete` methods become `async def`.
- Tests that call task functions or `run_agent` directly become `async def test_*`
  and `await`. `test_api_endpoint.py` goes through the FastAPI TestClient (which
  drives the async endpoint), so only its fake changes.
