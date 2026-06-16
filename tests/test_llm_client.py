from __future__ import annotations

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
