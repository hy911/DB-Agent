"""Data Explorer worker — the existing full agent, adopted unchanged.

This is the MAS `explore` worker: ad-hoc natural-language query + analysis +
visualization for researchers. It simply delegates to `run_agent` /
`run_agent_stream` (which still do domain routing, SQL gen, guard, execute,
critic, analyze, stats, answer). Keeping it a thin delegate means there is ONE
query pipeline; the supervisor just chooses who calls it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from db_agent.graph import AgentResult, run_agent, run_agent_stream
from db_agent.graph.state import Deps
from db_agent.observability.observer import Observer


def _kwargs(deps: Deps, observer: Observer | None) -> dict:
    return {
        "llm": deps.llm,
        "replica": deps.replica,
        "layer": deps.layer,
        "settings": deps.settings,
        "observer": observer,
        "resolve_gene": deps.resolve_gene,
        "align_values": deps.align_values,
        "run_sandbox": deps.run_sandbox,
        "run_stat": deps.run_stat,
        "retrieve_examples": deps.retrieve_examples,
    }


async def explore_worker(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AgentResult:
    return await run_agent(question, **_kwargs(deps, observer))


async def explore_worker_stream(
    question: str, *, deps: Deps, observer: Observer | None = None
) -> AsyncIterator[dict]:
    async for event in run_agent_stream(question, **_kwargs(deps, observer)):
        yield event
