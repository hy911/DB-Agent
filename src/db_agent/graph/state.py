"""Graph state, the public result object, and the injected dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from db_agent.config import Settings
from db_agent.db import GeneResolution, QueryResult, ReadReplica
from db_agent.db import resolve_gene as _default_resolve_gene
from db_agent.llm.client import LLMClient
from db_agent.semantic.model import SemanticLayer


class AgentState(TypedDict):
    question: str
    domain: str | None
    context: str | None
    extracted_genes: list[str]
    resolved_genes: dict[str, str]
    sql: str | None
    secured_sql: str | None
    needs_explain: bool
    big_tables: frozenset[str]
    limit: int | None
    attempts: int
    last_error: str | None
    outcome: str  # "" | "ok" | "retry" | "fatal"
    result: QueryResult | None
    answer: str | None
    clarification: str | None
    status: str  # running | answered | clarify | error
    error: str | None


def initial_state(question: str) -> AgentState:
    return AgentState(
        question=question,
        domain=None,
        context=None,
        extracted_genes=[],
        resolved_genes={},
        sql=None,
        secured_sql=None,
        needs_explain=False,
        big_tables=frozenset(),
        limit=None,
        attempts=0,
        last_error=None,
        outcome="",
        result=None,
        answer=None,
        clarification=None,
        status="running",
        error=None,
    )


@dataclass(frozen=True)
class AgentResult:
    status: str
    answer: str | None
    sql: str | None
    clarification: str | None
    error: str | None
    result: QueryResult | None


def to_result(state: AgentState) -> AgentResult:
    return AgentResult(
        status=state["status"],
        answer=state.get("answer"),
        sql=state.get("secured_sql"),
        clarification=state.get("clarification"),
        error=state.get("error"),
        result=state.get("result"),
    )


@dataclass(frozen=True)
class Deps:
    llm: LLMClient
    replica: ReadReplica
    layer: SemanticLayer
    settings: Settings
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] = _default_resolve_gene
