from __future__ import annotations

import sys
import types

from db_agent.config import Settings
from db_agent.llm.embedding import EmbeddingClient, LiteLLMEmbeddingClient


def _install_fake_litellm(monkeypatch, capture):
    fake = types.ModuleType("litellm")

    def embedding(**kwargs):
        capture.update(kwargs)
        data = [{"embedding": [0.1, 0.2, 0.3]} for _ in kwargs["input"]]
        return types.SimpleNamespace(data=data)

    fake.embedding = embedding
    monkeypatch.setitem(sys.modules, "litellm", fake)


def test_embedding_client_satisfies_protocol():
    assert isinstance(LiteLLMEmbeddingClient(Settings(_env_file=None)), EmbeddingClient)


def test_embed_passes_model_and_returns_vectors(monkeypatch):
    capture: dict = {}
    _install_fake_litellm(monkeypatch, capture)
    client = LiteLLMEmbeddingClient(Settings(_env_file=None))
    out = client.embed(["a", "b"])
    assert out == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert capture["model"] == "openai/qwen-embedding"
    assert capture["input"] == ["a", "b"]
