"""LLM client seam.

`LLMClient` is the Protocol the graph nodes depend on; tests inject a scripted
fake. `LiteLLMClient` is the real implementation against the OpenAI-compatible
LiteLLM gateway. `litellm` is imported lazily inside `complete` so importing this
module (and constructing the client) never touches the network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from db_agent.config import Settings


@runtime_checkable
class LLMClient(Protocol):
    async def complete(self, model: str, messages: list[dict[str, str]]) -> str: ...


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.litellm_base_url
        self._api_key = settings.litellm_api_key
        self._timeout = settings.llm_timeout_s
        # Qwen3 thinking mode is toggled via the chat template; on a vLLM
        # OpenAI-compatible gateway it rides in extra_body. Off by default so the
        # model emits the answer directly instead of long reasoning (which otherwise
        # 504s the gateway). See Settings.llm_enable_thinking.
        self._extra_body = {
            "chat_template_kwargs": {"enable_thinking": settings.llm_enable_thinking}
        }

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        import litellm

        # Async stream + accumulate. acompletion(stream=True) yields an async
        # iterator of chunks; streaming keeps the gateway connection alive during
        # long generations (e.g. SQL gen) so it never sits idle long enough to trip
        # the upstream timeout (the chronic "504"), and being async means the I/O
        # never blocks the event loop. Still returns the full joined string —
        # callers just await. See https://docs.litellm.ai/stream
        stream = await litellm.acompletion(
            model=f"openai/{model}",
            api_base=self._base_url,
            api_key=self._api_key,
            messages=messages,
            extra_body=self._extra_body,
            timeout=self._timeout,
            stream=True,
        )
        parts: list[str] = []
        async for chunk in stream:
            piece = chunk.choices[0].delta.content
            if piece:  # role-only / finish chunks carry delta.content = None
                parts.append(piece)
        return "".join(parts)
