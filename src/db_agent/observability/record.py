"""The per-run record (CLAUDE.md item #8 tuple), built from the final state.

The result is reduced to rowcount/columns/truncated PLUS a capped sample of the
first N rows (`result_sample`) so reviewers can see what data actually came back,
not just how many rows. `truncated`/`rowcount` always reflect the full result.
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
    result_sample: list[dict[str, object]] | None = None
    feedback: str | None = None  # placeholder; reserved for future user feedback
    # Which MAS worker handled the run (explore | recommend | vdr). None for a
    # direct (non-MAS) run_agent call; set by the supervisor's tagged observer.
    worker: str | None = None

    @classmethod
    def from_state(
        cls,
        state: AgentState,
        *,
        run_id: str | None = None,
        latency_ms: float | None = None,
        result_sample_rows: int = 50,
    ) -> RunRecord:
        result = state.get("result")
        if result is not None:
            rowcount, columns, truncated = result.rowcount, result.columns, result.truncated
            result_sample = list(result.rows[:result_sample_rows]) if result_sample_rows else None
        else:
            rowcount, columns, truncated, result_sample = None, None, None, None
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
            result_sample=result_sample,
        )

    def to_dict(self) -> dict:
        return asdict(self)
