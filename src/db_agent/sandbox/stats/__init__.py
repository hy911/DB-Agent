"""Vetted statistical-inference registry over an in-memory result set.

The LLM emits only a structured {function, params} request (data, never code);
``validate_stat_request`` checks it against the frozen ``REGISTRY`` and the table's
columns; ``run_stat`` dispatches to a hand-written impl that calls scipy/lifelines.
"""

from __future__ import annotations

from db_agent.sandbox.stats.registry import REGISTRY, catalog_text
from db_agent.sandbox.stats.runner import run_stat
from db_agent.sandbox.stats.spec import (
    ParamSpec,
    StatResult,
    StatTest,
    ValidatedStatRequest,
)
from db_agent.sandbox.stats.validator import validate_stat_request

__all__ = [
    "REGISTRY",
    "ParamSpec",
    "StatResult",
    "StatTest",
    "ValidatedStatRequest",
    "catalog_text",
    "run_stat",
    "validate_stat_request",
]
