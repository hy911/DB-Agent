"""Request-time card retrieval: embed the question, cosine-search the card store,
keep only cards clearing a similarity threshold. Off (no-op) until a card index is
configured, so the VDR worker simply uses the live engine until cards exist.
"""

from __future__ import annotations

from collections.abc import Callable

from db_agent.config import Settings
from db_agent.llm.embedding import EmbeddingClient
from db_agent.vdr.model import FactCard
from db_agent.vdr.store import CardStore

CardRetriever = Callable[[str], list[FactCard]]


def _no_cards(question: str) -> list[FactCard]:
    return []


def make_card_retriever(
    store: CardStore, embed: EmbeddingClient, k: int, threshold: float
) -> CardRetriever:
    def retrieve(question: str) -> list[FactCard]:
        try:
            vec = embed.embed([question])[0]
            hits = store.search(vec, k)
        except Exception:
            return []  # fail-soft: retrieval is additive; the worker falls back to live
        return [card for card, score in hits if score >= threshold]

    return retrieve


def default_card_retriever(settings: Settings) -> CardRetriever:
    if settings.vdr_index_path is None:
        return _no_cards
    from db_agent.llm.embedding import LiteLLMEmbeddingClient

    store = CardStore(settings.vdr_index_path)
    if not store.has_cards:
        return _no_cards
    return make_card_retriever(
        store, LiteLLMEmbeddingClient(settings), settings.vdr_top_k, settings.vdr_score_threshold
    )
