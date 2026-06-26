from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.state import Deps
from db_agent.mas.supervisor import run_mas, run_mas_stream
from db_agent.semantic import load_semantic_layer

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


class _LLM:
    """Content-aware fake: serves intent classification, domain routing, SQL gen and
    the answer off the same client (the supervisor adds an intent call ABOVE the
    existing domain route, so a pop-order fake on model_fast is unsafe)."""

    def __init__(self, *, intent: str, domain: str = "efficacy", answer: str = "ok.") -> None:
        self.intent = intent
        self.domain = domain
        self.answer = answer
        self.sqls = ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"]

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_fast:
            if "classify a user's request" in text:  # intent_messages
                return self.intent
            if "domain router" in text:  # route_messages
                return self.domain
            return "NONE"  # extract_genes
        if model == SETTINGS.model_sql:
            return self.sqls.pop(0)
        return self.answer  # model_route

    async def complete_stream(self, model: str, messages: list[dict[str, str]]):
        if model == SETTINGS.model_route:
            yield self.answer
        else:
            yield await self.complete(model, messages)


class _Replica:
    def __init__(self, script) -> None:
        self.script = list(script)

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        return self.script.pop(0)

    def fetch(self, sql, params=()):
        return []


def _qr():
    return QueryResult(
        columns=["drug_name"],
        rows=[{"drug_name": "X"}],
        rowcount=1,
        truncated=False,
        sql="SELECT drug_name",
        elapsed_ms=1.0,
    )


def _deps(llm, replica):
    return Deps(llm=llm, replica=replica, layer=LAYER, settings=SETTINGS)


async def test_supervisor_routes_explore_unchanged():
    res = await run_mas("查药效数据", deps=_deps(_LLM(intent="explore"), _Replica([_qr()])))
    assert res.status == "answered"
    assert res.answer == "ok."  # explore worker = the plain engine, no note prepended


async def test_supervisor_recommend_stub_prepends_note_and_falls_back():
    res = await run_mas("推荐合适的模型", deps=_deps(_LLM(intent="recommend"), _Replica([_qr()])))
    assert res.status == "answered"
    assert res.answer.startswith("（模型推荐 Agent")  # stub note
    assert res.answer.endswith("ok.")  # then the explore fallback answer


async def test_supervisor_vdr_stub_prepends_its_note():
    res = await run_mas("成瘤率多少", deps=_deps(_LLM(intent="vdr"), _Replica([_qr()])))
    assert res.answer.startswith("（尽调问答 Agent")


async def test_supervisor_tags_worker_in_observer():
    recs = []
    await run_mas(
        "推荐模型", deps=_deps(_LLM(intent="recommend"), _Replica([_qr()])), observer=recs.append
    )
    assert recs and recs[-1].worker == "recommend"


async def test_supervisor_agent_override_skips_router():
    # explicit agent='vdr' overrides the (here explore-returning) classifier
    res = await run_mas("q", deps=_deps(_LLM(intent="explore"), _Replica([_qr()])), agent="vdr")
    assert res.answer.startswith("（尽调问答 Agent")


async def test_supervisor_stream_emits_note_then_tokens_then_final():
    events = [
        e
        async for e in run_mas_stream(
            "推荐模型", deps=_deps(_LLM(intent="recommend"), _Replica([_qr()]))
        )
    ]
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens[0].startswith("（模型推荐 Agent")  # note streamed first
    assert "".join(tokens).endswith("ok.")  # explore answer streamed after
    assert events[-1]["type"] == "final" and events[-1]["result"].status == "answered"
