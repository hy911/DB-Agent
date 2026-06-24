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

`complete_stream() -> Iterator[str]` on the Protocol/client; `POST /query/stream`
SSE endpoint streaming only the answer node; frontend fetch-stream consumption.
