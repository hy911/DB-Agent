"""Build and run the agent graph.

`build_graph(deps)` wires the nodes (deps bound via functools.partial) into a
StateGraph with conditional edges for clarification and the self-correction loop.
`run_agent` is the public entry point: build, invoke, map to AgentResult.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from langgraph.graph import END, START, StateGraph

from db_agent.config import Settings
from db_agent.db import GeneResolution, ReadReplica
from db_agent.graph import nodes
from db_agent.graph.state import AgentResult, AgentState, Deps, initial_state, to_result
from db_agent.llm.client import LLMClient
from db_agent.observability.observer import Observer
from db_agent.observability.record import RunRecord
from db_agent.semantic.model import SemanticLayer


def build_graph(deps: Deps):
    g = StateGraph(AgentState)
    g.add_node("route", partial(nodes.route_node, deps=deps))
    g.add_node("extract_genes", partial(nodes.extract_genes_node, deps=deps))
    g.add_node("resolve_genes", partial(nodes.resolve_genes_node, deps=deps))
    g.add_node("assemble_context", partial(nodes.assemble_context_node, deps=deps))
    g.add_node("generate_sql", partial(nodes.generate_sql_node, deps=deps))
    g.add_node("guard", partial(nodes.guard_node, deps=deps))
    g.add_node("execute", partial(nodes.execute_node, deps=deps))
    g.add_node("answer", partial(nodes.answer_node, deps=deps))

    g.add_edge(START, "route")
    g.add_conditional_edges(
        "route",
        partial(nodes.after_route, deps=deps),
        ["extract_genes", "assemble_context", END],
    )
    g.add_edge("extract_genes", "resolve_genes")
    g.add_conditional_edges(
        "resolve_genes", nodes.after_resolve, ["assemble_context", END]
    )
    g.add_edge("assemble_context", "generate_sql")
    g.add_edge("generate_sql", "guard")
    g.add_conditional_edges("guard", nodes.after_guard, ["execute", "generate_sql", END])
    g.add_conditional_edges("execute", nodes.after_execute, ["answer", "generate_sql", END])
    g.add_edge("answer", END)
    return g.compile()


def run_agent(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
    observer: Observer | None = None,
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] | None = None,
) -> AgentResult:
    deps_kwargs = {"llm": llm, "replica": replica, "layer": layer, "settings": settings}
    if resolve_gene is not None:
        deps_kwargs["resolve_gene"] = resolve_gene
    deps = Deps(**deps_kwargs)
    graph = build_graph(deps)
    final = graph.invoke(initial_state(question))
    if observer is not None:
        try:
            observer(RunRecord.from_state(final))
        except Exception:
            pass  # observability is best-effort; never break a good answer
    return to_result(final)
