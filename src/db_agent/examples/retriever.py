"""Build the request-time retriever closure: embed the question, cosine-search the
store, fail-soft to no examples. `default_retriever` returns a no-op unless an index
path is configured, keeping retrieval off by default."""

from __future__ import annotations

from collections.abc import Callable

from db_agent.config import Settings
from db_agent.examples.model import Example
from db_agent.examples.store import ExampleStore
from db_agent.llm.embedding import EmbeddingClient

Retriever = Callable[[str, str], list[Example]]


def _no_examples(domain: str, question: str) -> list[Example]:
    return []


def make_retriever(store: ExampleStore, embed: EmbeddingClient, k: int) -> Retriever:
    def retrieve(domain: str, question: str) -> list[Example]:
        try:
            vec = embed.embed([question])[0]
            return store.search(vec, domain, k)
        except Exception:
            return []  # fail-soft: retrieval is additive, never break a good run

    return retrieve


def default_retriever(settings: Settings) -> Retriever:
    if settings.example_index_path is None:
        return _no_examples
    from db_agent.llm.embedding import LiteLLMEmbeddingClient

    store = ExampleStore(settings.example_index_path)
    return make_retriever(store, LiteLLMEmbeddingClient(settings), settings.example_top_k)
