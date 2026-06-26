from __future__ import annotations

import numpy as np

from db_agent.vdr.build import save_index
from db_agent.vdr.model import FactCard
from db_agent.vdr.store import CardStore


def _build(tmp_path):
    cards = [
        FactCard("CT26", "CT26 (Colorectal Carcinoma, CDX)", "潜伏期约 8 天。"),
        FactCard("MC38", "MC38 (Colorectal Carcinoma, CDX)", "潜伏期约 10 天。"),
    ]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    path = tmp_path / "cards.npz"
    save_index(path, vectors, cards)
    return CardStore(path)


def test_search_returns_nearest_card_with_score(tmp_path):
    store = _build(tmp_path)
    assert store.has_cards
    hits = store.search([1.0, 0.0], 2)
    assert hits[0][0].model_id == "CT26"
    assert hits[0][1] > 0.99  # cosine ~1 for the aligned vector
    assert hits[1][0].model_id == "MC38"


def test_missing_path_is_empty_store():
    store = CardStore(None)
    assert not store.has_cards
    assert store.search([1.0, 0.0], 3) == []


def test_search_k_zero_returns_empty(tmp_path):
    assert _build(tmp_path).search([1.0, 0.0], 0) == []
