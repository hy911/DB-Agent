"""Build the request-time retriever closure: embed the question, cosine-search the
store, fail-soft to no examples. `default_retriever` returns a no-op unless an index
path is configured, keeping retrieval off by default."""

from __future__ import annotations

from collections.abc import Callable

from db_agent.config import Settings
from db_agent.examples.model import Example
from db_agent.examples.store import ExampleStore
from db_agent.llm.embedding import EmbeddingClient
from db_agent.llm.rerank import RerankClient

Retriever = Callable[..., list[Example]]


def _no_examples(domain: str, question: str, draft_skeleton: str | None = None) -> list[Example]:
    return []


def make_retriever(
    store: ExampleStore,
    embed: EmbeddingClient,
    k: int,
    rerank: RerankClient | None = None,
    candidates: int | None = None,
) -> Retriever:
    cand_n = (candidates or k) if rerank is not None else k

    def retrieve(domain: str, question: str, draft_skeleton: str | None = None) -> list[Example]:
        try:
            # Structure-aware dual recall when a draft SQL skeleton is supplied and
            # the index carries skeleton vectors; one batched embed call for both.
            if draft_skeleton is not None and store.has_skeletons:
                qvec, svec = embed.embed([question, draft_skeleton])
                hits = store.search_dual(qvec, svec, domain, cand_n)
            else:
                vec = embed.embed([question])[0]
                hits = store.search(vec, domain, cand_n)
        except Exception:
            return []  # fail-soft: retrieval is additive, never break a good run
        if rerank is not None and len(hits) > 1:
            try:
                order = rerank.rerank(question, [h.question for h in hits], k)
                return [hits[i] for i in order if 0 <= i < len(hits)][:k]
            except Exception:
                pass  # fail-soft: rerank unavailable/failed -> cosine top-k
        return hits[:k]

    return retrieve


def default_retriever(settings: Settings) -> Retriever:
    if settings.example_index_path is None:
        return _no_examples
    from db_agent.llm.embedding import LiteLLMEmbeddingClient

    store = ExampleStore(settings.example_index_path)
    embed = LiteLLMEmbeddingClient(settings)
    if settings.example_rerank:
        from db_agent.llm.rerank import LiteLLMRerankClient

        return make_retriever(
            store,
            embed,
            settings.example_top_k,
            rerank=LiteLLMRerankClient(settings),
            candidates=settings.example_rerank_candidates,
        )
    return make_retriever(store, embed, settings.example_top_k)
