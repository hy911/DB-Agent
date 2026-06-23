# examples/ — few-shot example retrieval + optional rerank (off by default)

Improves SQL generation by injecting similar past `(question → raw_sql)` pairs as
few-shot reference. **Off until `Settings.example_index_path` is set** (default None →
no-op retriever, zero extra gateway calls). **fail-soft** throughout (missing/corrupt
index, embed failure, or rerank failure → degrade; generation proceeds as before).

**Offline build:** `python -m db_agent.examples.build <obs.jsonl> <out.npz>` — ingests
the observability log, keeps `status=="answered"`, dedups on `(domain, raw_sql)`,
embeds each `question` via `qwen-embedding`, and writes a local `.npz` vector index
(NOT in the read-only replica). **Uses `raw_sql`, never the secured SQL** — examples
must never teach the model to write permission filters (those stay deterministic).

**Request-time:** the `retrieve_examples` node (`assemble_context → retrieve_examples →
generate_sql`) embeds the question, cosine top-k over **same-domain** examples, injects
the pairs into `sql_messages`. Embedding seam: `llm/embedding.py`
(`LiteLLMEmbeddingClient`); injected via `Deps.retrieve_examples` (default no-op unless
an index path is set).

**Optional two-stage rerank** (`Settings.example_rerank=True`): fetch a larger cosine
top-N (`example_rerank_candidates`, default 10) then reorder to `example_top_k` via
`qwen-reranker` (`llm/rerank.py`, standard `POST /v1/rerank` contract); fail-soft →
cosine top-k. Enable with `DBAGENT_EXAMPLE_RERANK=true` (+ `DBAGENT_EXAMPLE_INDEX_PATH`).

**Gateway config for the reranker (important):** register `qwen-reranker` under the
**`hosted_vllm`** provider, NOT `infinity`. litellm's `infinity` rerank transform
mishandles vLLM's object-form `document` (`{text, multi_modal}`) and 500s
(`RerankResponse … results.N.document.text`); `return_documents:false` does not help.
`model: hosted_vllm/qwen3-reranker-8b` (api_base `…:8002/v1`, `mode: rerank`) parses it
cleanly — live-verified 2026-06-23. (Our client only reads `index` + `relevance_score`,
so a direct call to the infinity endpoint also works if the gateway can't be changed.)
