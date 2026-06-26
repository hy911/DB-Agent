"""Multi-Agent System (MAS) layer.

A supervisor sits above the existing query engine and routes each request to one
worker — `explore` (the adopted full agent), `recommend` (model recommender), or
`vdr` (due-diligence QA) — all sharing the same deterministic tool layer via Deps.
Off by default; enable with `Settings.mas_enabled`.
"""

from __future__ import annotations

from db_agent.mas.router import WORKER_KINDS, classify_intent
from db_agent.mas.supervisor import run_mas, run_mas_stream

__all__ = [
    "WORKER_KINDS",
    "classify_intent",
    "run_mas",
    "run_mas_stream",
]
