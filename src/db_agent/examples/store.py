"""Local vector index of few-shot examples. Pure cosine search over in-memory arrays.

The index file is a .npz produced by build.save_index: a float32 `vectors` matrix
plus parallel object arrays `questions` / `sqls` / `domains`, and (newer indexes)
`skeletons` + a `skeleton_vectors` matrix for structure-aware recall. A
missing/unset path or a corrupt file yields an empty store whose search returns []
(fail-soft); an old index without skeleton vectors simply falls back to
question-only recall.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from db_agent.examples.model import Example


class ExampleStore:
    def __init__(self, path: Path | None) -> None:
        self._vectors: np.ndarray | None = None
        self._skeleton_vectors: np.ndarray | None = None
        self._examples: list[Example] = []
        if path is None or not Path(path).exists():
            return
        try:
            data = np.load(path, allow_pickle=True)
            vectors = np.asarray(data["vectors"], dtype=np.float32)
            questions = list(data["questions"])
            sqls = list(data["sqls"])
            domains = list(data["domains"])
        except Exception:
            return  # corrupt/unreadable -> empty store (fail-soft)
        if len(vectors) == len(questions) == len(sqls) == len(domains) and len(vectors) > 0:
            self._vectors = vectors
            skeletons = list(data["skeletons"]) if "skeletons" in data else [""] * len(sqls)
            self._examples = [
                Example(q, s, d, k)
                for q, s, d, k in zip(questions, sqls, domains, skeletons, strict=True)
            ]
            if "skeleton_vectors" in data:
                skvec = np.asarray(data["skeleton_vectors"], dtype=np.float32)
                if len(skvec) == len(vectors):
                    self._skeleton_vectors = skvec

    @property
    def has_skeletons(self) -> bool:
        return self._skeleton_vectors is not None

    def search(self, query_vec: list[float], domain: str, k: int) -> list[Example]:
        if self._vectors is None or k <= 0:
            return []
        idx = [i for i, ex in enumerate(self._examples) if ex.domain == domain]
        if not idx:
            return []
        sims = _cosine(self._vectors[idx], np.asarray(query_vec, dtype=np.float32))
        order = np.argsort(-sims)[:k]
        return [self._examples[idx[i]] for i in order]

    def search_dual(
        self, query_vec: list[float], skeleton_vec: list[float], domain: str, k: int
    ) -> list[Example]:
        """Two-channel recall (DAIL-SQL): fuse the question-similarity ranking and
        the SQL-skeleton-similarity ranking via Reciprocal Rank Fusion. Falls back
        to question-only `search` when the index carries no skeleton vectors."""
        if self._vectors is None or self._skeleton_vectors is None or k <= 0:
            return self.search(query_vec, domain, k)
        idx = [i for i, ex in enumerate(self._examples) if ex.domain == domain]
        if not idx:
            return []
        q_order = np.argsort(-_cosine(self._vectors[idx], np.asarray(query_vec, dtype=np.float32)))
        s_order = np.argsort(
            -_cosine(self._skeleton_vectors[idx], np.asarray(skeleton_vec, dtype=np.float32))
        )
        fused = _rrf([q_order, s_order])[:k]
        return [self._examples[idx[i]] for i in fused]


def _rrf(orders: list[np.ndarray], c: int = 60) -> list[int]:
    """Reciprocal Rank Fusion of several local-index rankings (arrays of positions
    into the per-domain subset). Returns fused local positions, best first."""
    scores: dict[int, float] = {}
    for order in orders:
        for rank, pos in enumerate(order):
            scores[int(pos)] = scores.get(int(pos), 0.0) + 1.0 / (c + rank + 1)
    return sorted(scores, key=lambda p: -scores[p])


def _cosine(mat: np.ndarray, q: np.ndarray) -> np.ndarray:
    mnorm = np.linalg.norm(mat, axis=1)
    qnorm = np.linalg.norm(q)
    denom = mnorm * qnorm
    denom[denom == 0] = 1e-12
    return (mat @ q) / denom
