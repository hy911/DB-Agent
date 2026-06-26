"""Phase-A stub workers: prepend a 'building this' note, then fall back to the
explore pipeline so the request is still answered with generic data.

Each future worker (recommend, vdr) replaces its stub with real orchestration; the
supervisor wiring and the observability `worker` tag stay the same.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace

from db_agent.graph import AgentResult
from db_agent.graph.state import Deps
from db_agent.mas.workers.explore import explore_worker, explore_worker_stream
from db_agent.observability.observer import Observer


async def stub_worker(
    question: str, *, note: str, deps: Deps, observer: Observer | None = None
) -> AgentResult:
    result = await explore_worker(question, deps=deps, observer=observer)
    if result.answer is not None:
        return replace(result, answer=note + result.answer)
    return result


async def stub_worker_stream(
    question: str, *, note: str, deps: Deps, observer: Observer | None = None
) -> AsyncIterator[dict]:
    yield {"type": "token", "text": note}
    async for event in explore_worker_stream(question, deps=deps, observer=observer):
        yield event
