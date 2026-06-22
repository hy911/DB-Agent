from __future__ import annotations

import sys
import types

from db_agent.config import Settings
from db_agent.llm.client import LiteLLMClient, LLMClient


class _FakeClient:
    def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        return "ok"


def test_fake_satisfies_protocol():
    assert isinstance(_FakeClient(), LLMClient)


def test_litellm_client_satisfies_protocol_without_calling():
    # Constructing must not hit the network (litellm is imported lazily in
    # .complete, not at module import or construction).
    client = LiteLLMClient(Settings(_env_file=None))
    assert isinstance(client, LLMClient)


def _install_fake_litellm(monkeypatch, capture):
    fake = types.ModuleType("litellm")

    def completion(**kwargs):
        capture.update(kwargs)
        msg = types.SimpleNamespace(content="SELECT 1")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    fake.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", fake)


def test_client_disables_thinking_by_default(monkeypatch):
    capture: dict = {}
    _install_fake_litellm(monkeypatch, capture)
    client = LiteLLMClient(Settings(_env_file=None))
    out = client.complete("qwen-code", [{"role": "user", "content": "hi"}])
    assert out == "SELECT 1"
    assert capture["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert capture["model"] == "openai/qwen-code"


def test_client_thinking_can_be_enabled(monkeypatch):
    capture: dict = {}
    _install_fake_litellm(monkeypatch, capture)
    client = LiteLLMClient(Settings(_env_file=None, llm_enable_thinking=True))
    client.complete("qwen-main", [{"role": "user", "content": "hi"}])
    assert capture["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
