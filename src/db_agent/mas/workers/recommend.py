"""Model Recommender worker (Phase A stub).

Target (Phase B): a plan-execute orchestration — extract target/indication
criteria, query mutation/expression/model domains for candidates, rank, gather
efficacy evidence, render a PDF report. For now it delegates to explore with a
note, so a recommendation request still returns relevant data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from db_agent.graph import AgentResult
from db_agent.graph.state import Deps
from db_agent.mas.workers._stub import stub_worker, stub_worker_stream
from db_agent.observability.observer import Observer

_NOTE = "（模型推荐 Agent 正在建设中，先用通用数据查询为您应答。）\n\n"


async def recommend_worker(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AgentResult:
    return await stub_worker(question, note=_NOTE, deps=deps, observer=observer)


async def recommend_worker_stream(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AsyncIterator[dict]:
    async for event in stub_worker_stream(question, note=_NOTE, deps=deps, observer=observer):
        yield event
