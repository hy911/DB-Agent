"""The de-sensitized fact card — the unit of the VDR knowledge base.

A card is built offline from the DB and holds only externally-shareable facts about
one model (public `model_id`, not the internal `model_uuid`; coarse attributes;
pre-computed metrics like latency and an efficacy summary). De-sensitization is a
build-time projection: only safe fields ever enter a card, so retrieval/answering
need no extra permission logic (the single constant rule still governs the live
fallback path).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactCard:
    model_id: str  # public business identifier (never the internal model_uuid)
    title: str  # short header, e.g. "CT26 (Colorectal Carcinoma, CDX)"
    text: str  # the de-sensitized fact body used both for embedding and grounding
