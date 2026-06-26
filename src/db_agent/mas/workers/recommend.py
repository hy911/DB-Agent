"""Model Recommender worker (Phase B): the real plan-execute recommendation.

Runs the recommender pipeline and adapts its `Recommendation` to the shared
AgentResult / SSE contract: the persuasive summary becomes the streamed answer, and
the ranked models become a labeled result table the existing chat UI renders. Emits
a RunRecord (tagged `recommend` by the supervisor's observer wrapper).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from db_agent.db.result import QueryResult
from db_agent.graph import AgentResult
from db_agent.graph.state import Deps, DomainResult, initial_state
from db_agent.mas.recommender.model import Recommendation
from db_agent.mas.recommender.pipeline import run_recommendation
from db_agent.observability.observer import Observer
from db_agent.observability.record import RunRecord

_COLUMNS = [
    "model_id",
    "model_name",
    "model_type",
    "cancer_type",
    "score",
    "matched",
    "evidence_count",
]
_LABEL = "模型推荐"


def _to_query_result(rec: Recommendation) -> QueryResult:
    rows = [
        {
            "model_id": m.model_id,
            "model_name": m.model_name,
            "model_type": m.model_type,
            "cancer_type": m.cancer_type,
            "score": m.score,
            "matched": "; ".join(m.matched),
            "evidence_count": len(m.evidence),
        }
        for m in rec.models
    ]
    return QueryResult(
        columns=_COLUMNS, rows=rows, rowcount=len(rows), truncated=False, sql="", elapsed_ms=0.0
    )


def _to_agent_result(rec: Recommendation, run_id: str) -> AgentResult:
    qr = _to_query_result(rec) if rec.models else None
    sections = (DomainResult(domain="recommend", label=_LABEL, result=qr),) if qr else ()
    return AgentResult(
        status="answered",
        answer=rec.summary,
        sql=None,
        analysis_sql=None,
        stat_request=None,
        clarification=None,
        error=None,
        result=qr,
        run_id=run_id,
        results=sections,
    )


def _emit(observer: Observer | None, rec: Recommendation, run_id: str, latency_ms: float) -> None:
    if observer is None:
        return
    st = initial_state(rec.question)
    st["status"] = "answered"
    st["domain"] = "recommend"
    st["answer"] = rec.summary
    st["result"] = _to_query_result(rec) if rec.models else None
    try:
        observer(RunRecord.from_state(st, run_id=run_id, latency_ms=latency_ms))
    except Exception:
        pass  # observability is best-effort; never break a good recommendation


async def _run(question: str, deps: Deps) -> tuple[Recommendation, str, float]:
    run_id = uuid.uuid4().hex
    start = time.perf_counter()
    rec = await run_recommendation(question, deps=deps)
    return rec, run_id, (time.perf_counter() - start) * 1000.0


async def recommend_worker(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AgentResult:
    rec, run_id, latency = await _run(question, deps)
    _emit(observer, rec, run_id, latency)
    return _to_agent_result(rec, run_id)


async def recommend_worker_stream(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AsyncIterator[dict]:
    rec, run_id, latency = await _run(question, deps)
    _emit(observer, rec, run_id, latency)
    if rec.summary:
        yield {"type": "token", "text": rec.summary}
    yield {"type": "final", "result": _to_agent_result(rec, run_id)}
