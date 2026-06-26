from __future__ import annotations

from tests._rec_helpers import FULL_CRITERIA, FULL_GENE_MAP, RecReplica, rec_resolver

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.state import Deps
from db_agent.mas.supervisor import run_mas, run_mas_stream
from db_agent.semantic import load_semantic_layer
from db_agent.vdr.model import FactCard

_VDR_CARDS = [FactCard("CT26", "CT26 (Colorectal Carcinoma, CDX)", "平均潜伏期约 8 天。")]

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


class _LLM:
    """Content-aware fake serving every call the supervisor's workers make: intent
    classification, domain routing, SQL gen, the explore answer, AND the recommender's
    criteria + summary (the supervisor adds an intent call ABOVE the domain route, and
    recommend now runs the real pipeline — so a pop-order fake on a model is unsafe)."""

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
        # model_route: recommender criteria/summary, vdr grounded answer, else explore
        if "extract structured selection criteria" in text:
            return FULL_CRITERIA
        if "scientific consultant recommending" in text:
            return "推荐 m1。"
        if "due-diligence questions" in text:
            return "潜伏期约 8 天 [CT26]。"
        return self.answer

    async def complete_stream(self, model: str, messages: list[dict[str, str]]):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_route:
            yield "潜伏期约 8 天 [CT26]。" if "due-diligence questions" in text else self.answer
        else:
            yield await self.complete(model, messages)


class _Replica(RecReplica):
    """RecReplica (fetch for the recommender) plus execute for the explore engine."""

    def __init__(self, script) -> None:
        self.script = list(script)

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        return self.script.pop(0)


def _qr():
    return QueryResult(
        columns=["drug_name"],
        rows=[{"drug_name": "X"}],
        rowcount=1,
        truncated=False,
        sql="SELECT drug_name",
        elapsed_ms=1.0,
    )


def _deps(llm, replica, cards=()):
    return Deps(
        llm=llm,
        replica=replica,
        layer=LAYER,
        settings=SETTINGS,
        resolve_gene=rec_resolver(FULL_GENE_MAP),
        retrieve_cards=lambda q: list(cards),
    )


async def test_supervisor_routes_explore_unchanged():
    res = await run_mas("查药效数据", deps=_deps(_LLM(intent="explore"), _Replica([_qr()])))
    assert res.status == "answered"
    assert res.answer == "ok."  # explore worker = the plain engine, unchanged


async def test_supervisor_routes_to_recommend_pipeline():
    res = await run_mas("推荐合适的模型", deps=_deps(_LLM(intent="recommend"), _Replica([])))
    assert res.status == "answered"
    assert res.answer == "推荐 m1。"  # the recommender's summary, not the explore answer
    assert res.result is not None and res.result.rows[0]["model_id"] == "A1"
    assert res.results and res.results[0].domain == "recommend"


async def test_supervisor_vdr_grounds_from_cards():
    res = await run_mas("CT26 潜伏期多久", deps=_deps(_LLM(intent="vdr"), _Replica([]), _VDR_CARDS))
    assert res.status == "answered"
    assert "[CT26]" in res.answer  # grounded card answer with citation
    assert res.results[0].domain == "vdr"


async def test_supervisor_vdr_falls_back_to_explore_without_cards():
    # no matching cards → the vdr worker uses the live engine (still tagged vdr)
    res = await run_mas("成瘤率多少", deps=_deps(_LLM(intent="vdr"), _Replica([_qr()])))
    assert res.answer == "ok."
    assert res.results[0].domain == "efficacy"


async def test_supervisor_tags_worker_in_observer():
    recs = []
    await run_mas(
        "推荐模型", deps=_deps(_LLM(intent="recommend"), _Replica([])), observer=recs.append
    )
    assert recs and recs[-1].worker == "recommend"


async def test_supervisor_agent_override_skips_router():
    # explicit agent='vdr' overrides the (here explore-returning) classifier; with a
    # matching card the vdr worker answers (proving the override took effect)
    res = await run_mas(
        "CT26 潜伏期", deps=_deps(_LLM(intent="explore"), _Replica([]), _VDR_CARDS), agent="vdr"
    )
    assert "[CT26]" in res.answer and res.results[0].domain == "vdr"


async def test_supervisor_stream_recommend_emits_summary_then_final():
    events = [
        e
        async for e in run_mas_stream(
            "推荐模型", deps=_deps(_LLM(intent="recommend"), _Replica([]))
        )
    ]
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "推荐 m1。"  # the summary streamed as a token
    final = events[-1]
    assert final["type"] == "final" and final["result"].status == "answered"
    assert final["result"].result.rows[0]["model_id"] == "A1"
