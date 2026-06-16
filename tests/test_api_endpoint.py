from __future__ import annotations

from fastapi.testclient import TestClient

from db_agent.api.app import create_app
from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.state import Deps
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


class _LLM:
    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}

    def complete(self, model, messages):
        return self.by_model[model].pop(0)


class _RaisingLLM:
    def complete(self, model, messages):
        raise RuntimeError("gateway down")


class _Replica:
    def __init__(self, script):
        self.script = list(script)

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        item = self.script.pop(0)
        if isinstance(item, GuardError):
            raise item
        return item


def _client(llm, replica):
    deps = Deps(llm=llm, replica=replica, layer=LAYER, settings=SETTINGS)
    return TestClient(create_app(deps=deps))


def _qr():
    return QueryResult(
        columns=["drug_name"],
        rows=[{"drug_name": "X"}],
        rowcount=1,
        truncated=False,
        sql="SELECT drug_name",
        elapsed_ms=1.0,
    )


def test_health():
    with _client(_LLM({}), _Replica([])) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_query_answered_includes_rows():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    with _client(llm, _Replica([_qr()])) as client:
        resp = client.post("/query", json={"question": "how many?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "answered"
    assert body["answer"] == "Found 1 drug."
    assert "for_bd" in body["sql"].lower()
    assert body["rows"]["rowcount"] == 1
    assert body["rows"]["columns"] == ["drug_name"]


def test_query_clarify_has_no_rows():
    llm = _LLM({"qwen-fast": ["clarify: which drug?"]})
    with _client(llm, _Replica([])) as client:
        resp = client.post("/query", json={"question": "how is it?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "clarify"
    assert "which drug?" in body["clarification"]
    assert body["rows"] is None


def test_query_fatal_guard_error_is_200_error():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        }
    )
    replica = _Replica([GuardError("big_table_scan", "seq scan", retryable=False)])
    with _client(llm, replica) as client:
        resp = client.post("/query", json={"question": "scan it"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_query_llm_exception_is_502():
    with _client(_RaisingLLM(), _Replica([])) as client:
        resp = client.post("/query", json={"question": "boom"})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "agent backend error"


def test_query_missing_question_is_422():
    with _client(_LLM({}), _Replica([])) as client:
        resp = client.post("/query", json={})
    assert resp.status_code == 422
