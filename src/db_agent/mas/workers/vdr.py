"""Virtual Data Room QA worker (Phase A stub).

Target (Phase C): hybrid — structured facts via the live query engine, narrative /
pre-computed conclusions (take rate, latency summaries) via a de-sensitized RAG
card index. For now it delegates to explore with a note.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from db_agent.graph import AgentResult
from db_agent.graph.state import Deps
from db_agent.mas.workers._stub import stub_worker, stub_worker_stream
from db_agent.observability.observer import Observer

_NOTE = "（尽调问答 Agent 正在建设中，先用通用数据查询为您应答。）\n\n"


async def vdr_worker(question: str, *, deps: Deps, observer: Observer | None = None) -> AgentResult:
    return await stub_worker(question, note=_NOTE, deps=deps, observer=observer)


async def vdr_worker_stream(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AsyncIterator[dict]:
    async for event in stub_worker_stream(question, note=_NOTE, deps=deps, observer=observer):
        yield event
