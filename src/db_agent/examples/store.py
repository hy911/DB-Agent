"""Local vector index of few-shot examples. Pure cosine search over in-memory arrays.

The index file is a .npz produced by build.save_index: a float32 `vectors` matrix
plus parallel object arrays `questions` / `sqls` / `domains`. A missing/unset path or
a corrupt file yields an empty store whose search returns [] (fail-soft).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from db_agent.examples.model import Example


class ExampleStore:
    def __init__(self, path: Path | None) -> None:
        self._vectors: np.ndarray | None = None
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
            self._examples = [
                Example(q, s, d) for q, s, d in zip(questions, sqls, domains, strict=True)
            ]

    def search(self, query_vec: list[float], domain: str, k: int) -> list[Example]:
        if self._vectors is None or k <= 0:
            return []
        idx = [i for i, ex in enumerate(self._examples) if ex.domain == domain]
        if not idx:
            return []
        mat = self._vectors[idx]
        q = np.asarray(query_vec, dtype=np.float32)
        sims = _cosine(mat, q)
        order = np.argsort(-sims)[:k]
        return [self._examples[idx[i]] for i in order]


def _cosine(mat: np.ndarray, q: np.ndarray) -> np.ndarray:
    mnorm = np.linalg.norm(mat, axis=1)
    qnorm = np.linalg.norm(q)
    denom = mnorm * qnorm
    denom[denom == 0] = 1e-12
    return (mat @ q) / denom
