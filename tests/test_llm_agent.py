from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.llm.agent_llm import RouteResult, answer, generate_sql, route
from db_agent.semantic import load_semantic_layer

SETTINGS = Settings(_env_file=None)
DOMAINS = load_semantic_layer(SETTINGS.semantic_layer_path).routable_domains()


class _ScriptedClient:
    """Returns a fixed string regardless of inputs; records the model used."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_model: str | None = None

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        self.last_model = model
        return self.reply


async def test_route_efficacy():
    c = _ScriptedClient("efficacy")
    res = await route(c, SETTINGS, "how many models?", DOMAINS)
    assert res == RouteResult(domain="efficacy", domains=("efficacy",))
    assert c.last_model == "qwen-fast"


async def test_route_expression():
    c = _ScriptedClient("expression")
    res = await route(c, SETTINGS, "TP53 expression?", DOMAINS)
    assert res.domain == "expression"
    assert res.domains == ("expression",)
    assert res.clarification is None


async def test_route_multiple_domains_fans_out():
    c = _ScriptedClient("mutation, expression")
    res = await route(c, SETTINGS, "Trp53 相关数据", DOMAINS)
    assert res.domains == ("mutation", "expression")
    assert res.domain is None  # ambiguous → no single domain
    assert res.clarification is None


async def test_route_unroutable_domain_is_clarify():
    c = _ScriptedClient("reference")  # a real domain, but deliberately not routable
    res = await route(c, SETTINGS, "dictionary stuff", DOMAINS)
    assert res.domain is None
    assert res.clarification


async def test_route_clarify_extracts_question():
    c = _ScriptedClient("clarify: which drug do you mean?")
    res = await route(c, SETTINGS, "how is it?", DOMAINS)
    assert res.domain is None
    assert res.clarification == "which drug do you mean?"


async def test_route_unexpected_output_falls_back_to_clarify():
    c = _ScriptedClient("the answer is 42")
    res = await route(c, SETTINGS, "what?", DOMAINS)
    assert res.domain is None
    assert res.clarification  # non-empty fallback question


async def test_generate_sql_strips_code_fences():
    c = _ScriptedClient("```sql\nSELECT 1\n```")
    sql = await generate_sql(c, SETTINGS, "q", "ctx")
    assert sql == "SELECT 1"
    assert c.last_model == "qwen-code"


async def test_extract_genes_parses_comma_list():
    from db_agent.llm.agent_llm import extract_genes

    c = _ScriptedClient("p53, EGFR")
    assert await extract_genes(c, SETTINGS, "p53 and EGFR?") == ["p53", "EGFR"]
    assert c.last_model == "qwen-fast"


async def test_extract_genes_none_returns_empty():
    from db_agent.llm.agent_llm import extract_genes

    assert await extract_genes(_ScriptedClient("NONE"), SETTINGS, "how many models?") == []


async def test_analyze_sql_returns_sql():
    from db_agent.llm.agent_llm import analyze_sql

    c = _ScriptedClient("SELECT group_id, avg(tv) FROM result GROUP BY group_id")
    qr = QueryResult(
        columns=["group_id", "tv"],
        rows=[{"group_id": "A", "tv": 1.0}],
        rowcount=1,
        truncated=False,
        sql="SELECT ...",
        elapsed_ms=1.0,
    )
    out = await analyze_sql(c, SETTINGS, "avg per group?", qr)
    assert out.lower().startswith("select")
    assert c.last_model == "qwen-code"


async def test_analyze_sql_none_passthrough():
    from db_agent.llm.agent_llm import analyze_sql

    qr = QueryResult(
        columns=["x"],
        rows=[{"x": 1}],
        rowcount=1,
        truncated=False,
        sql="s",
        elapsed_ms=1.0,
    )
    assert await analyze_sql(_ScriptedClient("NONE"), SETTINGS, "q", qr) == "NONE"


def test_rows_preview_clips_wide_cell_and_budget():
    from db_agent.llm.agent_llm import _rows_preview

    big_list = ", ".join(f"model{i}" for i in range(2000))  # one huge ARRAY_AGG-style cell
    qr = QueryResult(
        columns=["names"],
        rows=[{"names": big_list}],
        rowcount=1,
        truncated=False,
        sql="s",
        elapsed_ms=1.0,
    )
    out = _rows_preview(qr)
    assert "…" in out  # the wide cell was clipped
    assert len(out) < 500  # nowhere near the raw ~13k-char cell


def test_rows_preview_caps_rows_by_char_budget():
    from db_agent.llm.agent_llm import _rows_preview

    rows = [{"v": "x" * 150} for _ in range(50)]
    qr = QueryResult(
        columns=["v"], rows=rows, rowcount=50, truncated=False, sql="s", elapsed_ms=1.0
    )
    out = _rows_preview(qr, max_chars=600)
    assert "rows total" in out  # stopped early and reported the true total
    assert out.count("\n") < 50  # fewer than all 50 rows rendered


async def test_answer_uses_model_route_and_passes_through():
    c = _ScriptedClient("There are 3 models.")
    res = QueryResult(
        columns=["n"],
        rows=[{"n": 3}],
        rowcount=1,
        truncated=False,
        sql="SELECT count(*) AS n",
        elapsed_ms=1.0,
    )
    out = await answer(c, SETTINGS, "how many?", "SELECT count(*) AS n", res)
    assert out == "There are 3 models."
    assert c.last_model == "qwen-main"
