"""High-level LLM tasks for the agent graph: route, generate_sql, answer.

Each takes an injected LLMClient and the Settings (for model-alias selection), so
the graph nodes stay thin and the functions are trivially testable with a fake
client.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.llm import prompts
from db_agent.llm.client import LLMClient
from db_agent.sandbox.stats.spec import StatResult

if TYPE_CHECKING:
    from db_agent.examples.model import Example
    from db_agent.semantic.model import Domain

_CLARIFY_FALLBACK = "Could you clarify or rephrase your question?"


@dataclass(frozen=True)
class RouteResult:
    domain: str | None = None
    clarification: str | None = None


async def route(
    client: LLMClient, settings: Settings, question: str, domains: list[Domain]
) -> RouteResult:
    valid = {d.name for d in domains}
    raw = await client.complete(settings.model_fast, prompts.route_messages(question, domains))
    text = raw.strip()
    low = text.lower()
    if low.startswith("clarify"):
        q = text.split(":", 1)[1].strip() if ":" in text else _CLARIFY_FALLBACK
        return RouteResult(clarification=q or _CLARIFY_FALLBACK)
    for name in valid:
        if low.startswith(name.lower()):
            return RouteResult(domain=name)
    # Unexpected output or an out-of-scope domain name: never guess — ask.
    return RouteResult(clarification=_CLARIFY_FALLBACK)


async def extract_genes(client: LLMClient, settings: Settings, question: str) -> list[str]:
    raw = await client.complete(settings.model_fast, prompts.extract_genes_messages(question))
    text = raw.strip()
    if not text or text.strip().upper() == "NONE":
        return []
    return [g.strip() for g in text.split(",") if g.strip()]


async def generate_sql(
    client: LLMClient,
    settings: Settings,
    question: str,
    context: str,
    prior_error: str | None = None,
    examples: list[Example] | None = None,
) -> str:
    text = await client.complete(
        settings.model_sql, prompts.sql_messages(question, context, prior_error, examples)
    )
    return _strip_fences(text).strip()


async def analyze_sql(
    client: LLMClient, settings: Settings, question: str, result: QueryResult
) -> str:
    msgs = prompts.analysis_messages(question, result.columns, _rows_preview(result))
    text = await client.complete(settings.model_sql, msgs)
    return _strip_fences(text).strip()


async def request_stat(
    client: LLMClient,
    settings: Settings,
    question: str,
    columns: list[str],
    rows_preview: str,
    catalog: str,
) -> str:
    msgs = prompts.stat_messages(question, columns, rows_preview, catalog)
    text = await client.complete(settings.model_sql, msgs)
    return _strip_fences(text).strip()


async def answer_stat(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    analysis_sql: str | None,
    stat: StatResult,
) -> str:
    summary = _format_stat(stat)
    text = await client.complete(
        settings.model_route, prompts.stat_answer_messages(question, sql, analysis_sql, summary)
    )
    return text.strip()


def _format_stat(stat: StatResult) -> str:
    lines = [f"Test: {stat.test}"]
    if stat.stats:
        lines.append("Statistics: " + ", ".join(f"{k}={v:.4g}" for k, v in stat.stats.items()))
    for g in stat.groups:
        lines.append("Group: " + ", ".join(f"{k}={v}" for k, v in g.items()))
    if stat.caveats:
        lines.append("Caveats: " + " ".join(stat.caveats))
    return "\n".join(lines)


async def answer(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    result: QueryResult,
) -> str:
    preview = _rows_preview(result)
    text = await client.complete(
        settings.model_route, prompts.answer_messages(question, sql, preview)
    )
    return text.strip()


async def answer_stream(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    result: QueryResult,
) -> AsyncIterator[str]:
    """Token-yielding twin of `answer` — same prompt/model, streamed for live display."""
    preview = _rows_preview(result)
    async for piece in client.complete_stream(
        settings.model_route, prompts.answer_messages(question, sql, preview)
    ):
        yield piece


async def answer_stat_stream(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    analysis_sql: str | None,
    stat: StatResult,
) -> AsyncIterator[str]:
    """Token-yielding twin of `answer_stat`."""
    summary = _format_stat(stat)
    async for piece in client.complete_stream(
        settings.model_route, prompts.stat_answer_messages(question, sql, analysis_sql, summary)
    ):
        yield piece


def _strip_fences(text: str) -> str:
    """Remove a leading ```sql / ``` fence and trailing ``` if the model added them."""
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[: -len("```")]
    return t


def _rows_preview(
    result: QueryResult,
    limit: int = 20,
    *,
    max_cell: int = 200,
    max_chars: int = 2000,
) -> str:
    """Compact preview of a result for an LLM prompt.

    Bounded three ways so a wide single row (e.g. ARRAY_AGG of 1000+ names) can't
    blow up the prompt and time out the answer step: each cell is clipped to
    ``max_cell`` chars, and rows are added only while under the ``max_chars``
    budget (on top of the ``limit`` row cap).
    """
    if result.rowcount == 0:
        return "(0 rows)"

    def cell(value: object) -> str:
        s = str(value)
        return s if len(s) <= max_cell else s[:max_cell] + "…"

    lines = [", ".join(result.columns)]
    used = len(lines[0])
    shown = 0
    for row in result.rows[:limit]:
        line = ", ".join(cell(row.get(c)) for c in result.columns)
        if shown and used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
        shown += 1
    if shown < result.rowcount:
        lines.append(f"... ({result.rowcount} rows total)")
    return "\n".join(lines)
