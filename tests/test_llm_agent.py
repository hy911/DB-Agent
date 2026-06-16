from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.llm.agent_llm import RouteResult, answer, generate_sql, route

SETTINGS = Settings(_env_file=None)


class _ScriptedClient:
    """Returns a fixed string regardless of inputs; records the model used."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_model: str | None = None

    def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        self.last_model = model
        return self.reply


def test_route_efficacy():
    c = _ScriptedClient("efficacy")
    assert route(c, SETTINGS, "how many models?") == RouteResult(domain="efficacy")
    assert c.last_model == "qwen-fast"


def test_route_clarify_extracts_question():
    c = _ScriptedClient("clarify: which drug do you mean?")
    res = route(c, SETTINGS, "how is it?")
    assert res.domain is None
    assert res.clarification == "which drug do you mean?"


def test_route_unexpected_output_falls_back_to_clarify():
    c = _ScriptedClient("the answer is 42")
    res = route(c, SETTINGS, "what?")
    assert res.domain is None
    assert res.clarification  # non-empty fallback question


def test_generate_sql_strips_code_fences():
    c = _ScriptedClient("```sql\nSELECT 1\n```")
    sql = generate_sql(c, SETTINGS, "q", "ctx")
    assert sql == "SELECT 1"
    assert c.last_model == "qwen-code"


def test_answer_uses_model_route_and_passes_through():
    c = _ScriptedClient("There are 3 models.")
    res = QueryResult(
        columns=["n"],
        rows=[{"n": 3}],
        rowcount=1,
        truncated=False,
        sql="SELECT count(*) AS n",
        elapsed_ms=1.0,
    )
    out = answer(c, SETTINGS, "how many?", "SELECT count(*) AS n", res)
    assert out == "There are 3 models."
    assert c.last_model == "qwen-main"
