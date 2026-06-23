"""The per-run record (CLAUDE.md item #8 tuple), built from the final state.

Summary only: the result is reduced to rowcount/columns/truncated — raw rows are
never captured.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Import only for type hints (annotations are strings via __future__): importing
    # db_agent.graph at runtime would create a cycle (graph -> observability -> graph).
    from db_agent.graph.state import AgentState


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    ts: str
    question: str
    domain: str | None
    context: str | None
    raw_sql: str | None
    sql: str | None
    analysis_sql: str | None
    stat_request: str | None
    status: str
    attempts: int
    rowcount: int | None
    columns: list[str] | None
    truncated: bool | None
    answer: str | None
    clarification: str | None
    error: str | None
    latency_ms: float | None = None
    feedback: str | None = None  # placeholder; reserved for future user feedback

    @classmethod
    def from_state(
        cls,
        state: AgentState,
        *,
        run_id: str | None = None,
        latency_ms: float | None = None,
    ) -> RunRecord:
        result = state.get("result")
        if result is not None:
            rowcount, columns, truncated = result.rowcount, result.columns, result.truncated
        else:
            rowcount, columns, truncated = None, None, None
        return cls(
            run_id=run_id or uuid.uuid4().hex,
            ts=datetime.now(UTC).isoformat(),
            question=state["question"],
            domain=state.get("domain"),
            context=state.get("context"),
            raw_sql=state.get("sql"),
            sql=state.get("secured_sql"),
            analysis_sql=state.get("analysis_sql"),
            stat_request=state.get("stat_request"),
            status=state["status"],
            attempts=state["attempts"],
            rowcount=rowcount,
            columns=columns,
            truncated=truncated,
            answer=state.get("answer"),
            clarification=state.get("clarification"),
            error=state.get("error"),
            latency_ms=latency_ms,
        )

    def to_dict(self) -> dict:
        return asdict(self)
