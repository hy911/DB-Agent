# Few-Shot Example Retrieval (Local Vector Index) — Design

**Date:** 2026-06-22
**Status:** Approved (design), pending spec review
**Scope:** Retrieve similar past (question → SQL) pairs from the observability log and
inject them as few-shot examples into the SQL-generation prompt, to improve SQL
quality. Local self-contained vector index (no writable Postgres); embeddings via the
gateway's `qwen-embedding`. Two stages: an offline index builder and an online
retrieval node.

## Context / constraints

- The agent's DB access is a **strictly read-only replica** (`conn.read_only = True`),
  so the example store **cannot** live in the database — it is a local file built
  from the observability log.
- The observability log is already local JSONL (`RunRecord`): each record has
  `question`, `raw_sql`, `sql` (secured), `domain`, `status`.
- The gateway exposes `qwen-embedding` (and `qwen-reranker`, deferred).
- **Examples use `raw_sql` (the model's own output), NOT `sql` (secured).** Secured
  SQL carries deterministic permission injection (`for_bd` EXISTS semi-joins, etc.);
  teaching the model from secured SQL would wrongly teach it to write permission
  filters, which must stay deterministic and never be the model's job.

## Architecture

Two stages sharing a small `examples/` package (pure logic separated from I/O):

### Offline index builder (not on the request path)

A CLI (`python -m db_agent.examples.build`) that:
1. reads the obs JSONL log,
2. keeps records with `status == "answered"` and non-empty `question` + `raw_sql`,
3. dedups on `(domain, raw_sql)`,
4. batch-embeds the `question` text via `qwen-embedding`,
5. writes a local index file (vectors + parallel metadata) to `example_index_path`.

### Online retrieval (request path)

A new node `retrieve_examples`, placed `assemble_context → retrieve_examples →
generate_sql`:
1. embeds the current `question` (one gateway call),
2. cosine top-k over the **same-domain** subset of the index,
3. writes `state["examples"]`,
4. `sql_messages` appends a "similar past questions and their SQL" block.

## Components

New package `src/db_agent/examples/`:

- `model.py` — `Example` (frozen: `question`, `sql`, `domain`).
- `store.py` — `ExampleStore`: loads the index file once; `search(query_vec,
  domain, k) -> list[Example]` is **pure cosine** over the in-memory arrays, filtered
  to `domain`. Missing/corrupt file → empty store (search returns `[]`).
- `build.py` — `build_index(records, embed_fn, out_path)`: pure-ish ingest
  (filter/dedup/embed via injected `embed_fn`, write file) + a `__main__` CLI wrapper
  that wires the real JSONL reader + `LiteLLMEmbeddingClient`.
- index file format: a `.npz` with a float32 matrix `vectors` (n × d) plus a JSON
  sidecar (or `np.savez` with object arrays) holding the parallel `question` / `sql`
  / `domain` lists. (Plan pins the exact format.)

Embedding seam (kept separate from `LLMClient` so existing fakes are untouched):

- `EmbeddingClient` Protocol — `embed(texts: list[str]) -> list[list[float]]`.
- `LiteLLMEmbeddingClient` — wraps `litellm.embedding(model="openai/<alias>", ...)`,
  lazy import, returns vectors.

## State / DI / config

- `Deps`: add `retrieve_examples: Callable[[str, str], list[Example]]` (args: domain,
  question) with a default that embeds + searches the loaded store; when no index is
  configured/loaded the default returns `[]`. Mirrors the `resolve_gene` /
  `run_sandbox` / `run_stat` injection pattern.
- `AgentState`: add `examples: list[Example]` (default `[]` in `initial_state`).
- `run_agent(..., retrieve_examples=None)` override for offline tests.
- `graph/build.py`: insert the `retrieve_examples` node between `assemble_context`
  and `generate_sql` (`assemble_context → retrieve_examples → generate_sql`).
- `generate_sql_node` passes `state["examples"]` into `llm_generate_sql`, which
  forwards to `prompts.sql_messages(..., examples=...)`.
- `Settings`: `example_index_path: Path | None = None` (None → retrieval disabled),
  `example_top_k: int = 3`, `model_embed: str = "qwen-embedding"` (with the deployed
  alias via `AliasChoices`, matching the other model fields).

## Prompt change

`sql_messages` gains an optional `examples: list[Example] | None = None`. When
present and non-empty, prepend a block to the user message:

```
Here are similar past questions and the SQL that answered them (for reference, adapt
to the current question and schema):
Q: <question>
SQL: <raw_sql>
... (k of them)
```

The system instruction is unchanged; examples are reference, not rules.

## Error handling — fail-soft throughout

Retrieval is **additive**; it must never break a good run:
- No `example_index_path` / file missing / corrupt → store is empty → node injects no
  examples → SQL-gen behaves exactly as today.
- The embedding gateway call is wrapped; any exception → the node returns `{}` (no
  examples), generation proceeds normally.
- Empty same-domain subset → no examples.

## Testing

- **store (offline, pure):** known unit vectors → correct cosine top-k; domain filter
  excludes other domains; missing file → empty, `search` returns `[]`.
- **build (offline, fake `embed_fn`):** JSONL with mixed statuses → only `answered`
  with non-empty question+raw_sql are kept; dedup on `(domain, raw_sql)`; round-trips
  to a file the store can load.
- **EmbeddingClient (offline):** monkeypatch `litellm.embedding` to assert the model
  alias + that vectors are returned (mirrors `test_llm_client`).
- **node (fake retriever):** injects examples into state; empty/raising retriever →
  passthrough (`{}`), no crash.
- **sql_messages:** with examples → the block + each Q/SQL present; without → unchanged
  (existing tests still pass).
- **chain:** `assemble → retrieve → generate` offline end-to-end (one with examples,
  one with an empty retriever); existing chains still pass (default retriever returns
  `[]` when no index).
- **full offline suite + ruff** stay green.
- **live (best-effort):** build a small index from a sample JSONL, run a query, and
  confirm real `qwen-embedding` retrieval injects a relevant past example into the SQL
  prompt. Report the retrieved examples + generated SQL.

## Out of scope (deferred)

- `qwen-reranker` second-stage rerank (cosine-only first; reranker leaves a clean
  follow-up).
- Automatic / incremental index rebuild and any online write-back (the builder is run
  manually).
- Human vetting of example quality (first cut uses all `answered` runs).

## Risks

- **Index staleness:** the index is a snapshot; new good runs aren't searchable until
  the builder is re-run. Acceptable for a manual offline builder; documented.
- **Embedding latency per query:** one extra gateway call on the request path. Gated
  by `example_index_path` (off by default), so zero cost until enabled.
- **Cold start:** an empty/small obs log yields few or no examples — handled by
  fail-soft (no examples → today's behavior).
- **Few-shot bias:** a wrong past SQL could mislead generation. Mitigated by using
  only `answered` runs and presenting examples as adaptable reference, not rules;
  reranker / vetting (deferred) would tighten this further.
