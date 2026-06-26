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
        # Exact model_id mentions resolve deterministically — an embedding barely
        # separates YK-CRC-032 from YK-CRC-031, so a named model must never be lost
        # to semantic neighbours. These are always surfaced first.
        ql = question.lower()
        exact = [c for c in store.cards if c.model_id.lower() in ql]
        try:
            hits = store.search(embed.embed([question])[0], k)
        except Exception:
            return exact  # fail-soft: still return any exact hits; else live fallback
        semantic = [card for card, score in hits if score >= threshold]
        seen: set[str] = set()
        merged: list[FactCard] = []
        for card in [*exact, *semantic]:
            if card.model_id not in seen:
                seen.add(card.model_id)
                merged.append(card)
        return merged[: max(k, len(exact))]

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
