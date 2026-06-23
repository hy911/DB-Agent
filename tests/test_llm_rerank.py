from __future__ import annotations

import sys
import types

import pytest

from db_agent.config import Settings
from db_agent.llm.rerank import LiteLLMRerankClient, RerankClient


def _install_fake_httpx(monkeypatch, capture, *, results, status=200):
    fake = types.ModuleType("httpx")

    class _Resp:
        status_code = status

        def __init__(self):
            self._json = {"results": results}

        def raise_for_status(self):
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")

        def json(self):
            return self._json

    def post(url, **kwargs):
        capture["url"] = url
        capture["json"] = kwargs.get("json")
        capture["headers"] = kwargs.get("headers")
        return _Resp()

    fake.post = post
    monkeypatch.setitem(sys.modules, "httpx", fake)


def test_rerank_client_satisfies_protocol():
    assert isinstance(LiteLLMRerankClient(Settings(_env_file=None)), RerankClient)


def test_rerank_returns_indices_sorted_by_score(monkeypatch):
    capture: dict = {}
    # deliberately unsorted scores; index 2 best, then 0, then 1
    results = [
        {"index": 0, "relevance_score": 0.5},
        {"index": 1, "relevance_score": 0.1},
        {"index": 2, "relevance_score": 0.9},
    ]
    _install_fake_httpx(monkeypatch, capture, results=results)
    client = LiteLLMRerankClient(Settings(_env_file=None))
    order = client.rerank("q", ["a", "b", "c"], top_n=2)
    assert order == [2, 0]
    assert capture["url"].endswith("/v1/rerank")
    assert capture["json"]["model"] == "qwen-reranker"
    assert capture["json"]["query"] == "q"
    assert capture["json"]["documents"] == ["a", "b", "c"]
    assert capture["json"]["top_n"] == 2


def test_rerank_raises_on_http_error(monkeypatch):
    _install_fake_httpx(monkeypatch, {}, results=[], status=500)
    client = LiteLLMRerankClient(Settings(_env_file=None))
    with pytest.raises(RuntimeError):
        client.rerank("q", ["a"], top_n=1)
