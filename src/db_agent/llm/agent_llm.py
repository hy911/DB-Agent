"""High-level LLM tasks for the agent graph: route, generate_sql, answer.

Each takes an injected LLMClient and the Settings (for model-alias selection), so
the graph nodes stay thin and the functions are trivially testable with a fake
client.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
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
    domain: str | None = None  # set when exactly one domain matched (convenience)
    clarification: str | None = None
    domains: tuple[str, ...] = field(default_factory=tuple)  # all matched domains, in order


async def route(
    client: LLMClient, settings: Settings, question: str, domains: list[Domain]
) -> RouteResult:
    """Route a question to one OR MORE domains.

    A data question now yields every applicable domain (the model replies with a
    comma-separated list); the agent fans out across them instead of asking the
    user which one. Only greetings/meta/out-of-scope still clarify.
    """
    valid = {d.name for d in domains}
    raw = await client.complete(settings.model_fast, prompts.route_messages(question, domains))
    text = raw.strip()
    low = text.lower()
    if low.startswith("clarify"):
        q = text.split(":", 1)[1].strip() if ":" in text else _CLARIFY_FALLBACK
        return RouteResult(clarification=q or _CLARIFY_FALLBACK)
    matched: list[str] = []
    for tok in re.split(r"[,\s]+", low):
        tok = tok.strip(".;:!?。，、 ")
        if not tok:
            continue
        for name in valid:
            if name.lower() == tok and name not in matched:
                matched.append(name)
    if matched:
        return RouteResult(
            domain=matched[0] if len(matched) == 1 else None,
            domains=tuple(matched),
        )
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


def _record_count_prefix(question: str, result: QueryResult) -> str:
    """A deterministic, language-aware "N records" lead for a multi-row result.

    The answer LLM reliably undercounts a multi-row data listing (it reports the
    number of distinct drugs, or the treatment rows it sees in the preview, instead
    of the true row count — e.g. "CT26的阳性药数据" → 11 instead of 48). So the
    system states the authoritative count itself. Skipped for single-row results
    (an aggregate value like "380 PDX models" — "1 record" would be nonsense)."""
    if result.rowcount <= 1:
        return ""
    zh = any("一" <= c <= "鿿" for c in question)
    n = result.rowcount
    if result.truncated:
        return f"共查询到至少 {n} 条记录。\n\n" if zh else f"Found at least {n} records.\n\n"
    return f"共查询到 {n} 条记录。\n\n" if zh else f"Found {n} records.\n\n"


async def answer(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    result: QueryResult,
    *,
    prefix_count: bool = False,
) -> str:
    preview = _rows_preview(result)
    prefix = _record_count_prefix(question, result) if prefix_count else ""
    text = await client.complete(
        settings.model_route,
        prompts.answer_messages(
            question, sql, preview, result.rowcount, result.truncated, count_prefixed=bool(prefix)
        ),
    )
    return (prefix + text).strip()


async def answer_stream(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    result: QueryResult,
    *,
    prefix_count: bool = False,
) -> AsyncIterator[str]:
    """Token-yielding twin of `answer` — same prompt/model, streamed for live display.

    When `prefix_count` is set, an authoritative "N records" line is yielded first
    (deterministic, matches the result table) and the LLM is told not to restate a
    total — see `_record_count_prefix` and `answer_messages(count_prefixed=...)`."""
    preview = _rows_preview(result)
    prefix = _record_count_prefix(question, result) if prefix_count else ""
    if prefix:
        yield prefix
    async for piece in client.complete_stream(
        settings.model_route,
        prompts.answer_messages(
            question, sql, preview, result.rowcount, result.truncated, count_prefixed=bool(prefix)
        ),
    ):
        yield piece


async def answer_multi(
    client: LLMClient,
    settings: Settings,
    question: str,
    sections: list[tuple[str, int]],
) -> str:
    """One-sentence intro for a multi-domain fan-out (non-streaming)."""
    text = await client.complete(
        settings.model_route, prompts.multi_intro_messages(question, sections)
    )
    return text.strip()


async def answer_multi_stream(
    client: LLMClient,
    settings: Settings,
    question: str,
    sections: list[tuple[str, int]],
) -> AsyncIterator[str]:
    """Streamed twin of `answer_multi`."""
    async for piece in client.complete_stream(
        settings.model_route, prompts.multi_intro_messages(question, sections)
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
