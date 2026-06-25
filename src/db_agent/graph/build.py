"""Build and run the agent graph.

`build_graph(deps)` wires the nodes (deps bound via functools.partial) into a
StateGraph with conditional edges for clarification and the self-correction loop.
`run_agent` is the public entry point: build, invoke, map to AgentResult.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from functools import partial

from langgraph.graph import END, START, StateGraph

from db_agent.config import Settings
from db_agent.db import GeneResolution, ReadReplica
from db_agent.db.result import QueryResult
from db_agent.examples.retriever import Retriever
from db_agent.graph import nodes
from db_agent.graph.state import (
    AgentResult,
    AgentState,
    Deps,
    DomainResult,
    initial_state,
    to_result,
)
from db_agent.llm import answer_multi as llm_answer_multi
from db_agent.llm import answer_multi_stream as llm_answer_multi_stream
from db_agent.llm import route as llm_route
from db_agent.llm.client import LLMClient
from db_agent.observability.observer import Observer
from db_agent.observability.record import RunRecord
from db_agent.sandbox.stats import StatResult
from db_agent.semantic.model import SemanticLayer

# Shown when a multi-domain fan-out found no data in any category.
_NO_DATA_FALLBACK = "未在相关数据类别中找到匹配的数据。"


def build_graph(deps: Deps):
    g = StateGraph(AgentState)
    g.add_node("route", partial(nodes.route_node, deps=deps))
    g.add_node("extract_genes", partial(nodes.extract_genes_node, deps=deps))
    g.add_node("resolve_genes", partial(nodes.resolve_genes_node, deps=deps))
    g.add_node("assemble_context", partial(nodes.assemble_context_node, deps=deps))
    g.add_node("retrieve_examples", partial(nodes.retrieve_examples_node, deps=deps))
    g.add_node("generate_sql", partial(nodes.generate_sql_node, deps=deps))
    g.add_node("guard", partial(nodes.guard_node, deps=deps))
    g.add_node("execute", partial(nodes.execute_node, deps=deps))
    g.add_node("analyze", partial(nodes.analyze_node, deps=deps))
    g.add_node("stats", partial(nodes.stats_node, deps=deps))
    g.add_node("answer", partial(nodes.answer_node, deps=deps))

    g.add_edge(START, "route")
    g.add_conditional_edges(
        "route",
        partial(nodes.after_route, deps=deps),
        ["extract_genes", "assemble_context", END],
    )
    g.add_edge("extract_genes", "resolve_genes")
    g.add_conditional_edges("resolve_genes", nodes.after_resolve, ["assemble_context", END])
    g.add_edge("assemble_context", "retrieve_examples")
    g.add_edge("retrieve_examples", "generate_sql")
    g.add_edge("generate_sql", "guard")
    g.add_conditional_edges("guard", nodes.after_guard, ["execute", "generate_sql", END])
    g.add_conditional_edges("execute", nodes.after_execute, ["analyze", "generate_sql", END])
    g.add_edge("analyze", "stats")
    g.add_edge("stats", "answer")
    g.add_edge("answer", END)
    return g.compile()


def build_domain_graph(deps: Deps, *, with_answer: bool):
    """The post-route, single-domain pipeline as its own graph (domain preset in
    the initial state, no route node).

    `with_answer=True` runs analyze→stats→answer — the single-domain path, behaving
    exactly like the legacy graph after routing. `with_answer=False` stops at a good
    `execute` (data-only), used per domain in the multi-domain fan-out so we don't
    pay for N heavy NL answers.
    """
    g = StateGraph(AgentState)
    g.add_node("extract_genes", partial(nodes.extract_genes_node, deps=deps))
    g.add_node("resolve_genes", partial(nodes.resolve_genes_node, deps=deps))
    g.add_node("assemble_context", partial(nodes.assemble_context_node, deps=deps))
    g.add_node("retrieve_examples", partial(nodes.retrieve_examples_node, deps=deps))
    g.add_node("generate_sql", partial(nodes.generate_sql_node, deps=deps))
    g.add_node("guard", partial(nodes.guard_node, deps=deps))
    g.add_node("execute", partial(nodes.execute_node, deps=deps))

    g.add_conditional_edges(
        START, partial(nodes.domain_entry, deps=deps), ["extract_genes", "assemble_context"]
    )
    g.add_edge("extract_genes", "resolve_genes")
    g.add_conditional_edges("resolve_genes", nodes.after_resolve, ["assemble_context", END])
    g.add_edge("assemble_context", "retrieve_examples")
    g.add_edge("retrieve_examples", "generate_sql")
    g.add_edge("generate_sql", "guard")
    g.add_conditional_edges("guard", nodes.after_guard, ["execute", "generate_sql", END])

    if with_answer:
        g.add_node("analyze", partial(nodes.analyze_node, deps=deps))
        g.add_node("stats", partial(nodes.stats_node, deps=deps))
        g.add_node("answer", partial(nodes.answer_node, deps=deps))
        g.add_conditional_edges("execute", nodes.after_execute, ["analyze", "generate_sql", END])
        g.add_edge("analyze", "stats")
        g.add_edge("stats", "answer")
        g.add_edge("answer", END)
    else:
        g.add_conditional_edges("execute", nodes.after_execute_data_only, ["generate_sql", END])
    return g.compile()


def _domain_state(question: str, domain: str) -> AgentState:
    st = initial_state(question)
    st["domain"] = domain
    return st


def _domain_section(deps: Deps, domain: str, state: AgentState) -> DomainResult:
    """Reduce one per-domain subgraph's final state to a DomainResult section."""
    dom = deps.layer.get_domain(domain)
    label = dom.label if dom is not None else domain
    result = state.get("result")
    if result is not None:
        return DomainResult(domain=domain, label=label, sql=state.get("secured_sql"), result=result)
    if state.get("status") == "clarify":
        return DomainResult(domain=domain, label=label, clarification=state.get("clarification"))
    return DomainResult(domain=domain, label=label, error=state.get("error") or "no result")


async def _fan_out_data(
    deps: Deps, question: str, domains: tuple[str, ...]
) -> tuple[list[DomainResult], list[tuple[str, int]]]:
    """Run each domain's data-only subgraph concurrently; return the per-domain
    sections plus the (label, rowcount) inputs for the intro sentence."""
    graph = build_domain_graph(deps, with_answer=False)
    states = await asyncio.gather(*(graph.ainvoke(_domain_state(question, d)) for d in domains))
    sections = [_domain_section(deps, d, st) for d, st in zip(domains, states, strict=True)]
    intro_inputs = [
        (s.label or s.domain, s.result.rowcount) for s in sections if s.result is not None
    ]
    return sections, intro_inputs


def _log_state(
    question: str,
    *,
    status: str,
    domain: str | None = None,
    answer: str | None = None,
    secured_sql: str | None = None,
    clarification: str | None = None,
    error: str | None = None,
) -> AgentState:
    """A minimal state for RunRecord.from_state when there is no single graph state
    to log (the clarify branch, or the multi-domain fan-out)."""
    st = initial_state(question)
    st["status"] = status
    st["domain"] = domain
    st["answer"] = answer
    st["secured_sql"] = secured_sql
    st["clarification"] = clarification
    st["error"] = error
    return st


def _multi_log_state(question: str, domains: tuple[str, ...], answer: str, sections) -> AgentState:
    joined_sql = "\n".join(f"-- {s.domain}\n{s.sql}" for s in sections if s.sql) or None
    return _log_state(
        question,
        status="answered",
        domain=", ".join(domains),
        answer=answer,
        secured_sql=joined_sql,
    )


def _build_deps(
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] | None,
    run_sandbox: Callable[[list[str], list[dict[str, object]], str], QueryResult] | None,
    run_stat: Callable[[list[str], list[dict[str, object]], str], StatResult] | None,
    retrieve_examples: Retriever | None,
) -> Deps:
    deps_kwargs = {"llm": llm, "replica": replica, "layer": layer, "settings": settings}
    if resolve_gene is not None:
        deps_kwargs["resolve_gene"] = resolve_gene
    if run_sandbox is not None:
        deps_kwargs["run_sandbox"] = run_sandbox
    if run_stat is not None:
        deps_kwargs["run_stat"] = run_stat
    if retrieve_examples is not None:
        deps_kwargs["retrieve_examples"] = retrieve_examples
    return Deps(**deps_kwargs)


def _emit_record(
    observer: Observer | None,
    final: AgentState,
    *,
    run_id: str,
    latency_ms: float,
    settings: Settings,
) -> None:
    if observer is None:
        return
    try:
        observer(
            RunRecord.from_state(
                final,
                run_id=run_id,
                latency_ms=latency_ms,
                result_sample_rows=settings.audit_result_sample_rows,
            )
        )
    except Exception:
        pass  # observability is best-effort; never break a good answer


async def run_agent(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
    observer: Observer | None = None,
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] | None = None,
    run_sandbox: Callable[[list[str], list[dict[str, object]], str], QueryResult] | None = None,
    run_stat: Callable[[list[str], list[dict[str, object]], str], StatResult] | None = None,
    retrieve_examples: Retriever | None = None,
) -> AgentResult:
    deps = _build_deps(
        llm=llm,
        replica=replica,
        layer=layer,
        settings=settings,
        resolve_gene=resolve_gene,
        run_sandbox=run_sandbox,
        run_stat=run_stat,
        retrieve_examples=retrieve_examples,
    )
    run_id = uuid.uuid4().hex
    start = time.perf_counter()

    route_res = await llm_route(deps.llm, deps.settings, question, deps.layer.routable_domains())

    if not route_res.domains:  # greeting / meta / out-of-scope → still clarify
        result = _clarify_result(route_res.clarification, run_id)
        log: AgentState = _log_state(
            question, status="clarify", clarification=route_res.clarification
        )
    elif len(route_res.domains) == 1:  # confident single domain → full pipeline (unchanged)
        graph = build_domain_graph(deps, with_answer=True)
        log = await graph.ainvoke(_domain_state(question, route_res.domains[0]))
        result = to_result(log, run_id=run_id)
    else:  # ambiguous data question → fan out across all relevant domains
        sections, intro_inputs = await _fan_out_data(deps, question, route_res.domains)
        intro = (
            await llm_answer_multi(deps.llm, deps.settings, question, intro_inputs)
            if intro_inputs
            else _NO_DATA_FALLBACK
        )
        result = _multi_result(intro, sections, run_id)
        log = _multi_log_state(question, route_res.domains, intro, sections)

    latency_ms = (time.perf_counter() - start) * 1000.0
    _emit_record(observer, log, run_id=run_id, latency_ms=latency_ms, settings=settings)
    return result


def _clarify_result(clarification: str | None, run_id: str) -> AgentResult:
    return AgentResult(
        status="clarify",
        answer=None,
        sql=None,
        analysis_sql=None,
        stat_request=None,
        clarification=clarification,
        error=None,
        result=None,
        run_id=run_id,
    )


def _multi_result(answer: str, sections: list[DomainResult], run_id: str) -> AgentResult:
    return AgentResult(
        status="answered",
        answer=answer,
        sql=None,
        analysis_sql=None,
        stat_request=None,
        clarification=None,
        error=None,
        result=None,
        run_id=run_id,
        results=tuple(sections),
    )


async def run_agent_stream(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
    observer: Observer | None = None,
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] | None = None,
    run_sandbox: Callable[[list[str], list[dict[str, object]], str], QueryResult] | None = None,
    run_stat: Callable[[list[str], list[dict[str, object]], str], StatResult] | None = None,
    retrieve_examples: Retriever | None = None,
) -> AsyncIterator[dict]:
    """Streaming twin of `run_agent`: yields `{"type":"token", ...}` events as the
    answer is generated, then a single `{"type":"final","result": AgentResult}`
    once the run completes (and the RunRecord has been logged). Clarify/error
    branches emit no tokens — just the final event."""
    deps = _build_deps(
        llm=llm,
        replica=replica,
        layer=layer,
        settings=settings,
        resolve_gene=resolve_gene,
        run_sandbox=run_sandbox,
        run_stat=run_stat,
        retrieve_examples=retrieve_examples,
    )
    run_id = uuid.uuid4().hex
    start = time.perf_counter()

    route_res = await llm_route(deps.llm, deps.settings, question, deps.layer.routable_domains())

    if not route_res.domains:  # clarify — no tokens, just the final event
        result = _clarify_result(route_res.clarification, run_id)
        log: AgentState = _log_state(
            question, status="clarify", clarification=route_res.clarification
        )
    elif len(route_res.domains) == 1:  # single domain → stream the full pipeline's answer
        graph = build_domain_graph(deps, with_answer=True)
        final: AgentState | None = None
        async for mode, chunk in graph.astream(
            _domain_state(question, route_res.domains[0]), stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield {"type": "token", "text": chunk["token"]}
            else:  # "values": full state after each step; the last one is final
                final = chunk
        assert final is not None
        log = final
        result = to_result(final, run_id=run_id)
    else:  # fan out: run the data subgraphs, then stream the one-line intro
        sections, intro_inputs = await _fan_out_data(deps, question, route_res.domains)
        parts: list[str] = []
        if intro_inputs:
            async for piece in llm_answer_multi_stream(
                deps.llm, deps.settings, question, intro_inputs
            ):
                parts.append(piece)
                yield {"type": "token", "text": piece}
        intro = "".join(parts).strip() or _NO_DATA_FALLBACK
        result = _multi_result(intro, sections, run_id)
        log = _multi_log_state(question, route_res.domains, intro, sections)

    latency_ms = (time.perf_counter() - start) * 1000.0
    _emit_record(observer, log, run_id=run_id, latency_ms=latency_ms, settings=settings)
    yield {"type": "final", "result": result}
