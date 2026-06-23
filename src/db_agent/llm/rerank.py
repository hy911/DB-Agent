"""Rerank client seam for the example-retrieval second stage.

`LiteLLMRerankClient` targets the standard rerank contract
(POST /v1/rerank {model, query, documents, top_n} -> {results:[{index,
relevance_score}]}). httpx is imported lazily so importing this module never touches
the network. NOTE: the gateway's rerank route is currently misconfigured (qwen-reranker
registered under the openai provider, which LiteLLM's rerank route rejects) — until
that is fixed, calls 500 and the retriever fails soft to cosine top-k.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from db_agent.config import Settings


@runtime_checkable
class RerankClient(Protocol):
    def rerank(self, query: str, documents: list[str], top_n: int) -> list[int]: ...


class LiteLLMRerankClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.litellm_base_url.rstrip("/") + "/v1/rerank"
        self._api_key = settings.litellm_api_key
        self._model = settings.model_rerank

    def rerank(self, query: str, documents: list[str], top_n: int) -> list[int]:
        import httpx

        resp = httpx.post(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = list(resp.json()["results"])
        results.sort(key=lambda r: r["relevance_score"], reverse=True)
        return [int(r["index"]) for r in results[:top_n]]
