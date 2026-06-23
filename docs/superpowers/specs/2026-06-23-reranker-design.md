# qwen-reranker Two-Stage Rerank for Example Retrieval — Design

**Date:** 2026-06-23
**Status:** Approved (build against the standard rerank contract; live-verify deferred
to the gateway fix).
**Scope:** Add an optional second-stage rerank to few-shot example retrieval: fetch a
larger cosine top-N from the local index, then reorder to top-k with `qwen-reranker`.
Off by default, fail-soft.

## Context / known blocker

Probed 2026-06-22: the gateway exposes `qwen-reranker` but its `/v1/rerank` route is
misconfigured (registered under the `openai` provider, which LiteLLM's rerank route
rejects → 500 `Unsupported provider: openai`; not a chat model either → 404). So this
**cannot be live-verified now**. We build against the **standard rerank contract**
(Cohere/Jina-style: `POST /v1/rerank {model, query, documents, top_n}` →
`{results: [{index, relevance_score}, ...]}`), off by default + fail-soft, so the code
lands now and works the moment the gateway re-registers the model under a
rerank-capable provider. Offline tests pin the contract with a fake.

## Architecture

A new client seam + a small change to the retriever closure. No graph change.

- `llm/rerank.py` — `RerankClient` Protocol (`rerank(query, documents, top_n) ->
  list[int]`, returning document indices best-first) + `LiteLLMRerankClient`
  (direct `httpx.post` to `{base}/v1/rerank`, parses `results` sorted by
  `relevance_score`). httpx is imported lazily; declared as a direct dep.
- `examples/retriever.py` — `make_retriever(store, embed, k, rerank=None,
  candidates=None)`: when `rerank` is set, fetch `candidates` cosine hits then reorder
  to `k` via the reranker; fail-soft to cosine top-k on any rerank error. When
  `rerank` is None, behaves exactly as today (cosine top-k).
- `default_retriever(settings)`: builds the rerank client only when
  `settings.example_rerank` is True (and an index path is set).

## Config

- `model_rerank: str = "qwen-reranker"` (with `AliasChoices` like the other models).
- `example_rerank: bool = False` (off by default).
- `example_rerank_candidates: int = 10` (cosine top-N fetched before rerank).

## Data flow

```
embed question → store.search(vec, domain, N=candidates) → cosine top-N
  → rerank(question, [hit.question...], top_n=k) → reorder → top-k → inject
```

Reranker scores the **example questions** (the same text embedded), matching the
question-similarity intent. On any rerank failure → cosine top-k (the current behavior).

## Error handling — fail-soft (unchanged philosophy)

- `example_rerank=False` or no rerank client → cosine top-k, zero extra calls.
- rerank HTTP error / 500 (current gateway state) / malformed response / bad indices
  → fall back to cosine top-k. Never breaks a run.
- All wrapped inside the retriever's existing outer try (embed/search failure → `[]`).

## Testing

- **RerankClient (offline):** monkeypatch `httpx.post` to return a fake
  `{results:[{index, relevance_score}]}`; assert it POSTs `model`/`query`/`documents`/
  `top_n` and returns indices sorted by score; `raise_for_status` error path surfaces.
- **retriever with rerank (offline):** fake rerank reorders candidates → top-k in
  reranked order; rerank raising → cosine top-k (fail-soft); `rerank=None` → cosine
  top-k unchanged; `candidates` controls how many hits are fetched before rerank.
- **default_retriever:** `example_rerank=False` → no rerank client (cosine only);
  `example_rerank=True` + index path → a retriever that calls rerank.
- **full offline suite + ruff** green; existing retrieval tests unchanged (rerank off
  by default).
- **live:** deferred — blocked on the gateway rerank route fix (documented). When
  fixed: set `example_rerank=true`, confirm `/v1/rerank` reorders candidates.

## Out of scope

- Fixing the gateway config (infra, not this repo).
- Reranking on anything other than the example question text.
