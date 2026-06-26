from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.state import Deps
from db_agent.llm.prompts import vdr_answer_messages
from db_agent.mas.workers.vdr import vdr_worker, vdr_worker_stream
from db_agent.semantic import load_semantic_layer
from db_agent.vdr.model import FactCard

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)

CARDS = [FactCard("CT26", "CT26 (Colorectal Carcinoma, CDX)", "平均潜伏期约 8 天。")]


class _LLM:
    def __init__(self, *, vdr="CT26 的平均潜伏期约 8 天 [CT26]。", answer="ok.") -> None:
        self.vdr = vdr
        self.answer = answer
        self.sqls = ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"]

    async def complete(self, model, messages):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_fast:
            return "efficacy" if "domain router" in text else "NONE"
        if model == SETTINGS.model_sql:
            return self.sqls.pop(0)
        if "due-diligence questions" in text:  # vdr_answer
            return self.vdr
        return self.answer  # explore answer

    async def complete_stream(self, model, messages):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_route:
            yield self.vdr if "due-diligence questions" in text else self.answer
        else:
            yield await self.complete(model, messages)


class _Replica:
    def __init__(self, script):
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


def _deps(llm, replica, cards):
    return Deps(
        llm=llm,
        replica=replica,
        layer=LAYER,
        settings=SETTINGS,
        retrieve_cards=lambda q: list(cards),
    )


def test_vdr_answer_prompt_grounds_and_cites():
    msgs = vdr_answer_messages("CT26 潜伏期？", ["[CT26] CT26: 潜伏期 8 天。"])
    joined = " ".join(m["content"] for m in msgs)
    assert "[CT26]" in joined  # the card is supplied
    assert "ONLY the provided" in joined and "Cite" in joined  # grounding + citation rule


async def test_vdr_rag_answer_when_cards_match():
    res = await vdr_worker("CT26 平均潜伏期多久", deps=_deps(_LLM(), _Replica([]), CARDS))
    assert res.status == "answered"
    assert "[CT26]" in res.answer  # grounded, with citation
    assert res.result.rows[0]["model_id"] == "CT26"
    assert res.results[0].domain == "vdr"


async def test_vdr_falls_back_to_explore_without_cards():
    res = await vdr_worker("随便问点别的", deps=_deps(_LLM(), _Replica([_qr()]), []))
    assert res.answer == "ok."  # the live explore engine answered
    assert res.results[0].domain == "efficacy"  # not a vdr section


async def test_vdr_emits_record_tagged_vdr_domain():
    recs = []
    await vdr_worker("CT26 潜伏期", deps=_deps(_LLM(), _Replica([]), CARDS), observer=recs.append)
    assert recs and recs[0].domain == "vdr"


async def test_vdr_stream_emits_grounded_tokens_then_final():
    events = [
        e async for e in vdr_worker_stream("CT26 潜伏期", deps=_deps(_LLM(), _Replica([]), CARDS))
    ]
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert "[CT26]" in tokens
    final = events[-1]
    assert final["type"] == "final" and final["result"].results[0].domain == "vdr"
