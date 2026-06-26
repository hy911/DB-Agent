from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient
from tests._rec_helpers import FULL_CRITERIA, FULL_GENE_MAP, RecLLM, RecReplica, rec_resolver

from db_agent.api.app import create_app
from db_agent.config import Settings
from db_agent.graph.state import Deps
from db_agent.semantic import load_semantic_layer

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


def _client():
    deps = Deps(
        llm=RecLLM(FULL_CRITERIA),
        replica=RecReplica(),
        layer=LAYER,
        settings=SETTINGS,
        resolve_gene=rec_resolver(FULL_GENE_MAP),
    )
    return TestClient(create_app(deps=deps))


def test_recommend_returns_models_summary_and_report():
    with _client() as client:
        resp = client.post("/recommend", json={"question": "推荐 KRAS 突变的 PDX 肺癌模型"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "推荐 m1。"
    assert [m["model_id"] for m in data["models"]] == ["A1", "A3", "A2"]
    assert data["models"][0]["evidence"][0]["drug_name"] == "DrugX"
    assert "A1" in data["report_html"] and "<table" in data["report_html"]


def test_recommend_pdf_unavailable_returns_501():
    if importlib.util.find_spec("weasyprint") is not None:
        pytest.skip("weasyprint installed; PDF path returns 200 here")
    with _client() as client:
        resp = client.post("/recommend", json={"question": "推荐肺癌模型", "format": "pdf"})
    assert resp.status_code == 501
    assert "weasyprint" in resp.json()["detail"].lower()
