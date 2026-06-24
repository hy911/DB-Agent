from __future__ import annotations

import sys
import types

from db_agent.config import Settings
from db_agent.llm.client import LiteLLMClient, LLMClient


class _FakeClient:
    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        return "ok"


def test_fake_satisfies_protocol():
    assert isinstance(_FakeClient(), LLMClient)


def test_litellm_client_satisfies_protocol_without_calling():
    # Constructing must not hit the network (litellm is imported lazily in
    # .complete, not at module import or construction).
    client = LiteLLMClient(Settings(_env_file=None))
    assert isinstance(client, LLMClient)


def _chunk(content):
    delta = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])


async def _aiter(chunks):
    for c in chunks:
        yield c


def _install_fake_litellm(monkeypatch, capture):
    fake = types.ModuleType("litellm")

    async def acompletion(**kwargs):
        capture.update(kwargs)
        # Streaming: yield "SELECT 1" in pieces, then a content=None chunk
        # (role-only / finish) to exercise the accumulator's guard.
        return _aiter([_chunk("SEL"), _chunk("ECT"), _chunk(" 1"), _chunk(None)])

    fake.acompletion = acompletion
    monkeypatch.setitem(sys.modules, "litellm", fake)


async def test_client_disables_thinking_by_default(monkeypatch):
    capture: dict = {}
    _install_fake_litellm(monkeypatch, capture)
    client = LiteLLMClient(Settings(_env_file=None))
    out = await client.complete("qwen-code", [{"role": "user", "content": "hi"}])
    assert out == "SELECT 1"
    assert capture["stream"] is True
    assert capture["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert capture["model"] == "openai/qwen-code"


async def test_client_thinking_can_be_enabled(monkeypatch):
    capture: dict = {}
    _install_fake_litellm(monkeypatch, capture)
    client = LiteLLMClient(Settings(_env_file=None, llm_enable_thinking=True))
    await client.complete("qwen-main", [{"role": "user", "content": "hi"}])
    assert capture["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
