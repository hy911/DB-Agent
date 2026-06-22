"""The per-run record (CLAUDE.md item #8 tuple), built from the final state.

Summary only: the result is reduced to rowcount/columns/truncated — raw rows are
never captured.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Import only for type hints (annotations are strings via __future__): importing
    # db_agent.graph at runtime would create a cycle (graph -> observability -> graph).
    from db_agent.graph.state import AgentState


@dataclass(frozen=True)
class RunRecord:
    ts: str
    question: str
    domain: str | None
    context: str | None
    raw_sql: str | None
    sql: str | None
    analysis_sql: str | None
    status: str
    attempts: int
    rowcount: int | None
    columns: list[str] | None
    truncated: bool | None
    answer: str | None
    clarification: str | None
    error: str | None
    feedback: str | None = None  # placeholder; always None in Phase 1

    @classmethod
    def from_state(cls, state: AgentState) -> RunRecord:
        result = state.get("result")
        if result is not None:
            rowcount, columns, truncated = result.rowcount, result.columns, result.truncated
        else:
            rowcount, columns, truncated = None, None, None
        return cls(
            ts=datetime.now(UTC).isoformat(),
            question=state["question"],
            domain=state.get("domain"),
            context=state.get("context"),
            raw_sql=state.get("sql"),
            sql=state.get("secured_sql"),
            analysis_sql=state.get("analysis_sql"),
            status=state["status"],
            attempts=state["attempts"],
            rowcount=rowcount,
            columns=columns,
            truncated=truncated,
            answer=state.get("answer"),
            clarification=state.get("clarification"),
            error=state.get("error"),
        )

    def to_dict(self) -> dict:
        return asdict(self)
