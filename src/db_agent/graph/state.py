"""Graph state, the public result object, and the injected dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from db_agent.config import Settings
from db_agent.db import GeneResolution, QueryResult, ReadReplica
from db_agent.db import resolve_gene as _default_resolve_gene
from db_agent.db.value_resolver import align_values as _default_align_values
from db_agent.examples.model import Example
from db_agent.examples.retriever import Retriever, _no_examples
from db_agent.llm.client import LLMClient
from db_agent.sandbox.engine import DuckDBSandbox
from db_agent.sandbox.stats import StatResult
from db_agent.sandbox.stats import run_stat as _default_run_stat
from db_agent.semantic.model import SemanticLayer

_default_run_sandbox = DuckDBSandbox().run


class AgentState(TypedDict):
    question: str
    domain: str | None
    context: str | None
    extracted_genes: list[str]
    resolved_genes: dict[str, str]
    examples: list[Example]
    sql: str | None
    secured_sql: str | None
    needs_explain: bool
    big_tables: frozenset[str]
    limit: int | None
    attempts: int
    last_error: str | None
    critic_used: bool  # data-aware empty-result revision fired (bounds it to once)
    outcome: str  # "" | "ok" | "retry" | "fatal"
    result: QueryResult | None
    analysis: QueryResult | None
    analysis_sql: str | None
    stat_result: StatResult | None
    stat_request: str | None
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
        examples=[],
        sql=None,
        secured_sql=None,
        needs_explain=False,
        big_tables=frozenset(),
        limit=None,
        attempts=0,
        last_error=None,
        critic_used=False,
        outcome="",
        result=None,
        analysis=None,
        analysis_sql=None,
        stat_result=None,
        stat_request=None,
        answer=None,
        clarification=None,
        status="running",
        error=None,
    )


@dataclass(frozen=True)
class DomainResult:
    """One domain's data section in a (possibly multi-domain) answer."""

    domain: str  # domain name, e.g. "expression"
    label: str | None = None  # human display label, e.g. "基因表达"
    sql: str | None = None
    result: QueryResult | None = None
    error: str | None = None
    clarification: str | None = None


@dataclass(frozen=True)
class AgentResult:
    status: str
    answer: str | None
    sql: str | None
    analysis_sql: str | None
    stat_request: str | None
    clarification: str | None
    error: str | None
    result: QueryResult | None
    run_id: str | None = None
    # Per-domain sections: one item for a single-domain answer, N for a fan-out.
    # Empty for clarify/error. Top-level sql/result mirror results[0] for back-compat.
    results: tuple[DomainResult, ...] = ()


def to_result(state: AgentState, *, run_id: str | None = None) -> AgentResult:
    result = state.get("result")
    sql = state.get("secured_sql")
    sections: tuple[DomainResult, ...] = ()
    if state["status"] == "answered" and result is not None:
        sections = (DomainResult(domain=state.get("domain") or "", sql=sql, result=result),)
    return AgentResult(
        run_id=run_id,
        status=state["status"],
        answer=state.get("answer"),
        sql=sql,
        analysis_sql=state.get("analysis_sql"),
        stat_request=state.get("stat_request"),
        clarification=state.get("clarification"),
        error=state.get("error"),
        result=result,
        results=sections,
    )


@dataclass(frozen=True)
class Deps:
    llm: LLMClient
    replica: ReadReplica
    layer: SemanticLayer
    settings: Settings
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] = _default_resolve_gene
    # Data-aware value alignment (DB-backed, used by the critic on 0-row results).
    align_values: Callable[[ReadReplica, SemanticLayer, str, str | None], str | None] = (
        _default_align_values
    )
    run_sandbox: Callable[[list[str], list[dict[str, object]], str], QueryResult] = (
        _default_run_sandbox
    )
    run_stat: Callable[[list[str], list[dict[str, object]], str], StatResult] = _default_run_stat
    retrieve_examples: Retriever = _no_examples
