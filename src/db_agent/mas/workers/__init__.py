"""MAS worker implementations. Each is `(question, *, deps, observer) -> AgentResult`
plus a streaming twin yielding {"type": "token"/"final"} events."""

from __future__ import annotations

from db_agent.mas.workers.explore import explore_worker, explore_worker_stream
from db_agent.mas.workers.recommend import recommend_worker, recommend_worker_stream
from db_agent.mas.workers.vdr import vdr_worker, vdr_worker_stream

__all__ = [
    "explore_worker",
    "explore_worker_stream",
    "recommend_worker",
    "recommend_worker_stream",
    "vdr_worker",
    "vdr_worker_stream",
]
