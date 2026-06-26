"""Virtual Data Room QA worker (Phase C): hybrid RAG + live fallback.

Retrieves de-sensitized fact cards for the question. If any clear the similarity
threshold, it answers from them with citations (grounded, never touching raw data).
If none do — a structured fact the cards don't cover, or no index yet — it falls
back to the live explore engine (same `for_bd='yes'` constant rule). Either way the
run is tagged `vdr` by the supervisor's observer wrapper.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

from db_agent.db.result import QueryResult
from db_agent.graph import AgentResult
from db_agent.graph.state import Deps, DomainResult, initial_state
from db_agent.llm import vdr_answer, vdr_answer_stream
from db_agent.mas.workers.explore import explore_worker, explore_worker_stream
from db_agent.observability.observer import Observer
from db_agent.observability.record import RunRecord
from db_agent.vdr.model import FactCard

_LABEL = "尽调资料"
_COLUMNS = ["model_id", "title", "fact"]


def _render(cards: list[FactCard]) -> list[str]:
    return [f"[{c.model_id}] {c.title}: {c.text}" for c in cards]


def _cards_result(cards: list[FactCard]) -> QueryResult:
    rows = [{"model_id": c.model_id, "title": c.title, "fact": c.text} for c in cards]
    return QueryResult(
        columns=_COLUMNS, rows=rows, rowcount=len(rows), truncated=False, sql="", elapsed_ms=0.0
    )


def _agent_result(answer: str, cards: list[FactCard], run_id: str) -> AgentResult:
    qr = _cards_result(cards)
    return AgentResult(
        status="answered",
        answer=answer,
        sql=None,
        analysis_sql=None,
        stat_request=None,
        clarification=None,
        error=None,
        result=qr,
        run_id=run_id,
        results=(DomainResult(domain="vdr", label=_LABEL, result=qr),),
    )


def _emit(
    observer: Observer | None,
    question: str,
    answer: str,
    cards: list[FactCard],
    run_id: str,
    latency_ms: float,
) -> None:
    if observer is None:
        return
    st = initial_state(question)
    st["status"] = "answered"
    st["domain"] = "vdr"
    st["answer"] = answer
    st["result"] = _cards_result(cards)
    try:
        observer(RunRecord.from_state(st, run_id=run_id, latency_ms=latency_ms))
    except Exception:
        pass  # best-effort observability


async def vdr_worker(question: str, *, deps: Deps, observer: Observer | None = None) -> AgentResult:
    cards = await asyncio.to_thread(deps.retrieve_cards, question)
    if not cards:
        return await explore_worker(question, deps=deps, observer=observer)
    run_id = uuid.uuid4().hex
    start = time.perf_counter()
    answer = await vdr_answer(deps.llm, deps.settings, question, _render(cards))
    _emit(observer, question, answer, cards, run_id, (time.perf_counter() - start) * 1000.0)
    return _agent_result(answer, cards, run_id)


async def vdr_worker_stream(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AsyncIterator[dict]:
    cards = await asyncio.to_thread(deps.retrieve_cards, question)
    if not cards:
        async for event in explore_worker_stream(question, deps=deps, observer=observer):
            yield event
        return
    run_id = uuid.uuid4().hex
    start = time.perf_counter()
    pieces: list[str] = []
    async for piece in vdr_answer_stream(deps.llm, deps.settings, question, _render(cards)):
        pieces.append(piece)
        yield {"type": "token", "text": piece}
    answer = "".join(pieces).strip()
    _emit(observer, question, answer, cards, run_id, (time.perf_counter() - start) * 1000.0)
    yield {"type": "final", "result": _agent_result(answer, cards, run_id)}
