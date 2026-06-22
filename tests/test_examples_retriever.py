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
