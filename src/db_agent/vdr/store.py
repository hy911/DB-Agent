"""Local vector index of de-sensitized fact cards. Pure cosine search.

Mirrors examples/store.py: a .npz produced by build.save_index holds a float32
`vectors` matrix plus parallel object arrays `model_ids` / `titles` / `texts`. A
missing/unset path or a corrupt file yields an empty store whose search returns []
(fail-soft), so the VDR worker simply falls back to the live engine.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from db_agent.vdr.model import FactCard


class CardStore:
    def __init__(self, path: Path | None) -> None:
        self._vectors: np.ndarray | None = None
        self._cards: list[FactCard] = []
        if path is None or not Path(path).exists():
            return
        try:
            data = np.load(path, allow_pickle=True)
            vectors = np.asarray(data["vectors"], dtype=np.float32)
            model_ids = list(data["model_ids"])
            titles = list(data["titles"])
            texts = list(data["texts"])
        except Exception:
            return  # corrupt/unreadable -> empty store (fail-soft)
        if len(vectors) == len(model_ids) == len(titles) == len(texts) and len(vectors) > 0:
            self._vectors = vectors
            self._cards = [
                FactCard(mid, t, x) for mid, t, x in zip(model_ids, titles, texts, strict=True)
            ]

    @property
    def has_cards(self) -> bool:
        return self._vectors is not None

    @property
    def cards(self) -> list[FactCard]:
        return list(self._cards)

    def search(self, query_vec: list[float], k: int) -> list[tuple[FactCard, float]]:
        """Top-k cards by cosine similarity, each with its score (best first)."""
        if self._vectors is None or k <= 0:
            return []
        sims = _cosine(self._vectors, np.asarray(query_vec, dtype=np.float32))
        order = np.argsort(-sims)[:k]
        return [(self._cards[i], float(sims[i])) for i in order]


def _cosine(mat: np.ndarray, q: np.ndarray) -> np.ndarray:
    mnorm = np.linalg.norm(mat, axis=1)
    qnorm = np.linalg.norm(q)
    denom = mnorm * qnorm
    denom[denom == 0] = 1e-12
    return (mat @ q) / denom
