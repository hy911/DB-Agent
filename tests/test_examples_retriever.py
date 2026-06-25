from __future__ import annotations

from db_agent.config import Settings
from db_agent.examples.model import Example
from db_agent.examples.retriever import _no_examples, default_retriever, make_retriever


class _Store:
    def __init__(self, hits):
        self._hits = hits
        self.seen = None

    def search(self, vec, domain, k):
        self.seen = (vec, domain, k)
        return self._hits


class _Embed:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def test_no_examples_returns_empty():
    assert _no_examples("efficacy", "q") == []


def test_make_retriever_embeds_and_searches():
    hit = Example("past q", "SELECT 1", "efficacy")
    store = _Store([hit])
    retrieve = make_retriever(store, _Embed(), k=3)
    out = retrieve("efficacy", "current q")
    assert out == [hit]
    assert store.seen == ([1.0, 0.0], "efficacy", 3)


def test_make_retriever_fail_soft_on_embed_error():
    class _Boom:
        def embed(self, texts):
            raise RuntimeError("gateway down")

    retrieve = make_retriever(_Store([Example("x", "y", "efficacy")]), _Boom(), k=3)
    assert retrieve("efficacy", "q") == []  # degrades to no examples


def test_default_retriever_no_index_is_noop():
    # no example_index_path -> the no-op retriever
    assert default_retriever(Settings(_env_file=None)) is _no_examples


class _RecordingStore:
    """Returns k distinct examples; records the n it was asked for."""

    def __init__(self, n_available):
        self._all = [Example(f"q{i}", f"SELECT {i}", "efficacy") for i in range(n_available)]
        self.asked = None

    def search(self, vec, domain, k):
        self.asked = k
        return self._all[:k]


class _Rerank:
    def __init__(self, order):
        self._order = order
        self.seen = None

    def rerank(self, query, documents, top_n):
        self.seen = (query, documents, top_n)
        return self._order[:top_n]


def test_rerank_reorders_candidates_to_top_k():
    store = _RecordingStore(10)
    rr = _Rerank(order=[2, 0, 1])  # reranker prefers candidate index 2, then 0
    retrieve = make_retriever(store, _Embed(), k=2, rerank=rr, candidates=5)
    out = retrieve("efficacy", "q")
    assert store.asked == 5  # fetched the candidate pool, not just k
    assert [e.question for e in out] == ["q2", "q0"]  # reranked order, truncated to k
    assert rr.seen[2] == 2  # top_n passed to reranker == k


def test_rerank_fail_soft_falls_back_to_cosine():
    class _Boom:
        def rerank(self, query, documents, top_n):
            raise RuntimeError("rerank route 500")

    store = _RecordingStore(10)
    retrieve = make_retriever(store, _Embed(), k=2, rerank=_Boom(), candidates=5)
    out = retrieve("efficacy", "q")
    assert [e.question for e in out] == ["q0", "q1"]  # cosine order preserved


def test_no_rerank_is_plain_cosine_top_k():
    store = _RecordingStore(10)
    retrieve = make_retriever(store, _Embed(), k=3)
    out = retrieve("efficacy", "q")
    assert store.asked == 3  # only k fetched when no rerank
    assert [e.question for e in out] == ["q0", "q1", "q2"]


def test_default_retriever_rerank_enabled_builds_client(monkeypatch, tmp_path):
    # an index file must exist for default_retriever to build a real retriever
    import numpy as np

    from db_agent.examples.build import save_index

    save_index(
        tmp_path / "idx.npz",
        np.array([[1.0, 0.0]], dtype=np.float32),
        [Example("q", "SELECT 1", "efficacy")],
    )
    s = Settings(
        _env_file=None,
        example_index_path=tmp_path / "idx.npz",
        example_rerank=True,
    )
    retrieve = default_retriever(s)
    assert retrieve is not _no_examples  # a real retriever was built


def test_make_retriever_uses_dual_channel_with_draft_skeleton():
    hit = Example("past q", "SELECT 1", "efficacy", "SELECT ?")

    class _DualStore:
        has_skeletons = True

        def __init__(self):
            self.dual_args = None

        def search(self, vec, domain, k):  # pragma: no cover - should not be hit
            raise AssertionError("expected search_dual, not search")

        def search_dual(self, qvec, svec, domain, k):
            self.dual_args = (qvec, svec, domain, k)
            return [hit]

    class _Embed2:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]  # one vector per input text

    store = _DualStore()
    retrieve = make_retriever(store, _Embed2(), k=3)
    out = retrieve("efficacy", "current q", "SELECT ?")
    assert out == [hit]
    assert store.dual_args is not None and store.dual_args[2] == "efficacy"


def test_make_retriever_single_channel_when_no_draft():
    hit = Example("past q", "SELECT 1", "efficacy")
    store = _Store([hit])  # only has .search
    retrieve = make_retriever(store, _Embed(), k=3)
    assert retrieve("efficacy", "q", None) == [hit]  # draft None → single channel
