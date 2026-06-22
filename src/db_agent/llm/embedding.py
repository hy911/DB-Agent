"""Embedding client seam, separate from LLMClient so existing fakes are untouched.

`LiteLLMEmbeddingClient` calls the gateway's embedding endpoint; litellm is imported
lazily so importing this module never touches the network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from db_agent.config import Settings


@runtime_checkable
class EmbeddingClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LiteLLMEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.litellm_base_url
        self._api_key = settings.litellm_api_key
        self._model = settings.model_embed

    def embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        resp = litellm.embedding(
            model=f"openai/{self._model}",
            api_base=self._base_url,
            api_key=self._api_key,
            input=texts,
        )
        return [list(item["embedding"]) for item in resp.data]
