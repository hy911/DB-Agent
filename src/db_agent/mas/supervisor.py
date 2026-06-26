"""MAS supervisor: classify intent, dispatch to a worker, tag observability.

`run_mas` / `run_mas_stream` mirror `graph.build.run_agent` / `run_agent_stream`
(same `AgentResult` / SSE event contract) so the API and frontend are unchanged.
The only new behavior is a top-level intent route and a `worker` tag on the audit
record (via a thin observer wrapper) so logs show which agent handled each run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace

from db_agent.graph import AgentResult
from db_agent.graph.state import Deps
from db_agent.mas.router import WORKER_KINDS, classify_intent
from db_agent.mas.workers import (
    explore_worker,
    explore_worker_stream,
    recommend_worker,
    recommend_worker_stream,
    vdr_worker,
    vdr_worker_stream,
)
from db_agent.observability.observer import Observer
from db_agent.observability.record import RunRecord

_WORKERS: dict[str, Callable[..., Awaitable[AgentResult]]] = {
    "explore": explore_worker,
    "recommend": recommend_worker,
    "vdr": vdr_worker,
}
_STREAM_WORKERS: dict[str, Callable[..., AsyncIterator[dict]]] = {
    "explore": explore_worker_stream,
    "recommend": recommend_worker_stream,
    "vdr": vdr_worker_stream,
}


def _tagged_observer(observer: Observer | None, worker: str) -> Observer | None:
    """Wrap the sink so each emitted RunRecord carries the handling worker."""
    if observer is None:
        return None

    def wrapped(record: RunRecord) -> None:
        observer(replace(record, worker=worker))

    return wrapped


async def _resolve_kind(deps: Deps, question: str, agent: str | None) -> str:
    """An explicit, valid `agent` overrides the router; else classify (→ explore)."""
    if agent in WORKER_KINDS:
        return agent  # type: ignore[return-value]
    return await classify_intent(deps.llm, deps.settings, question)


async def run_mas(
    question: str, *, deps: Deps, observer: Observer | None = None, agent: str | None = None
) -> AgentResult:
    kind = await _resolve_kind(deps, question, agent)
    return await _WORKERS[kind](question, deps=deps, observer=_tagged_observer(observer, kind))


async def run_mas_stream(
    question: str, *, deps: Deps, observer: Observer | None = None, agent: str | None = None
) -> AsyncIterator[dict]:
    kind = await _resolve_kind(deps, question, agent)
    async for event in _STREAM_WORKERS[kind](
        question, deps=deps, observer=_tagged_observer(observer, kind)
    ):
        yield event
