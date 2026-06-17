"""High-level LLM tasks for the agent graph: route, generate_sql, answer.

Each takes an injected LLMClient and the Settings (for model-alias selection), so
the graph nodes stay thin and the functions are trivially testable with a fake
client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.llm import prompts
from db_agent.llm.client import LLMClient

if TYPE_CHECKING:
    from db_agent.semantic.model import Domain

_CLARIFY_FALLBACK = "Could you clarify or rephrase your question?"


@dataclass(frozen=True)
class RouteResult:
    domain: str | None = None
    clarification: str | None = None


def route(
    client: LLMClient, settings: Settings, question: str, domains: list[Domain]
) -> RouteResult:
    valid = {d.name for d in domains}
    text = client.complete(settings.model_fast, prompts.route_messages(question, domains)).strip()
    low = text.lower()
    if low.startswith("clarify"):
        q = text.split(":", 1)[1].strip() if ":" in text else _CLARIFY_FALLBACK
        return RouteResult(clarification=q or _CLARIFY_FALLBACK)
    for name in valid:
        if low.startswith(name.lower()):
            return RouteResult(domain=name)
    # Unexpected output or an out-of-scope domain name: never guess — ask.
    return RouteResult(clarification=_CLARIFY_FALLBACK)


def generate_sql(
    client: LLMClient,
    settings: Settings,
    question: str,
    context: str,
    prior_error: str | None = None,
) -> str:
    text = client.complete(settings.model_sql, prompts.sql_messages(question, context, prior_error))
    return _strip_fences(text).strip()


def answer(
    client: LLMClient,
    settings: Settings,
    question: str,
    sql: str,
    result: QueryResult,
) -> str:
    preview = _rows_preview(result)
    return client.complete(
        settings.model_route, prompts.answer_messages(question, sql, preview)
    ).strip()


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


def _rows_preview(result: QueryResult, limit: int = 20) -> str:
    if result.rowcount == 0:
        return "(0 rows)"
    lines = [", ".join(result.columns)]
    for row in result.rows[:limit]:
        lines.append(", ".join(str(row.get(c)) for c in result.columns))
    if result.rowcount > limit:
        lines.append(f"... ({result.rowcount} rows total)")
    return "\n".join(lines)
