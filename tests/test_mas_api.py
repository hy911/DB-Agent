from __future__ import annotations

import json

from fastapi.testclient import TestClient
from tests._rec_helpers import FULL_CRITERIA, FULL_GENE_MAP, RecReplica, rec_resolver

from db_agent.api.app import create_app
from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.state import Deps
from db_agent.semantic import load_semantic_layer
from db_agent.vdr.model import FactCard

SETTINGS = Settings(_env_file=None)
SETTINGS_MAS = Settings(_env_file=None, mas_enabled=True)
_VDR_CARDS = [FactCard("CT26", "CT26 (Colorectal Carcinoma, CDX)", "平均潜伏期约 8 天。")]
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


def _sse_events(resp):
    events = []
    for frame in resp.text.split("\n\n"):
        line = frame.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


class _LLM:
    """Content-aware fake serving intent + domain route + SQL + answer."""

    def __init__(self, *, intent: str, domain: str = "efficacy", answer: str = "ok.") -> None:
        self.intent = intent
        self.domain = domain
        self.answer = answer
        self.sqls = ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"]

    async def complete(self, model, messages):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_fast:
            if "classify a user's request" in text:
                return self.intent
            if "domain router" in text:
                return self.domain
            return "NONE"
        if model == SETTINGS.model_sql:
            return self.sqls.pop(0)
        if "extract structured selection criteria" in text:
            return FULL_CRITERIA
        if "scientific consultant recommending" in text:
            return "推荐 m1。"
        if "due-diligence questions" in text:
            return "潜伏期约 8 天 [CT26]。"
        return self.answer

    async def complete_stream(self, model, messages):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_route:
            yield "潜伏期约 8 天 [CT26]。" if "due-diligence questions" in text else self.answer
        else:
            yield await self.complete(model, messages)


class _Replica(RecReplica):
    """RecReplica (recommender fetch) + execute for the explore engine."""

    def __init__(self, script):
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


def _client(llm, replica, settings, cards=()):
    deps = Deps(
        llm=llm,
        replica=replica,
        layer=LAYER,
        settings=settings,
        resolve_gene=rec_resolver(FULL_GENE_MAP),
        retrieve_cards=lambda q: list(cards),
    )
    return TestClient(create_app(deps=deps))


def test_mas_enabled_routes_through_supervisor():
    # intent=recommend → the supervisor runs the real recommender pipeline
    with _client(_LLM(intent="recommend"), _Replica([]), SETTINGS_MAS) as client:
        resp = client.post("/query/stream", json={"question": "推荐合适的模型"})
        events = _sse_events(resp)
    assert resp.status_code == 200
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert tokens == "推荐 m1。"  # the recommender summary streamed
    final = events[-1]
    assert final["type"] == "final" and final["payload"]["status"] == "answered"
    assert final["payload"]["rows"]["rows"][0]["model_id"] == "A1"


def test_mas_disabled_uses_engine():
    # default settings: the supervisor is bypassed, the engine answers directly
    with _client(_LLM(intent="recommend"), _Replica([_qr()]), SETTINGS) as client:
        resp = client.post("/query/stream", json={"question": "查药效"})
        events = _sse_events(resp)
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert tokens == "ok."


def test_mas_routes_vdr_by_intent():
    # purely semantic auto-routing (no agent field): intent=vdr + a matching card
    with _client(_LLM(intent="vdr"), _Replica([]), SETTINGS_MAS, _VDR_CARDS) as client:
        resp = client.post("/query/stream", json={"question": "CT26 潜伏期"})
        events = _sse_events(resp)
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert "[CT26]" in tokens
