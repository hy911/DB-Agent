from __future__ import annotations

import json

from fastapi.testclient import TestClient

from db_agent.api.app import create_app
from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.state import Deps
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


def _sse_events(resp):
    """Parse `data: {json}` SSE frames from a buffered TestClient response body."""
    events = []
    for frame in resp.text.split("\n\n"):
        line = frame.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def _ask(client, question):
    resp = client.post("/query/stream", json={"question": question})
    return resp, _sse_events(resp)


class _LLM:
    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}

    async def complete(self, model, messages):
        return self.by_model[model].pop(0)

    async def complete_stream(self, model, messages):
        yield self.by_model[model].pop(0)


class _RaisingLLM:
    async def complete(self, model, messages):
        raise RuntimeError("gateway down")

    async def complete_stream(self, model, messages):
        raise RuntimeError("gateway down")
        yield  # pragma: no cover  (makes this an async generator)


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


def test_index_serves_ui():
    with _client(_LLM({}), _Replica([])) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "DB" in resp.text and "/query" in resp.text


def test_query_streams_tokens_then_final_with_rows():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    with _client(llm, _Replica([_qr()])) as client:
        resp, events = _ask(client, "how many?")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    # the answer streamed at least one token
    tokens = [e for e in events if e["type"] == "token"]
    assert tokens and "".join(t["text"] for t in tokens) == "Found 1 drug."
    final = events[-1]
    assert final["type"] == "final"
    payload = final["payload"]
    assert payload["status"] == "answered"
    assert payload["answer"] == "Found 1 drug."
    assert "for_bd" in payload["sql"].lower()
    assert payload["rows"]["rowcount"] == 1
    assert payload["rows"]["columns"] == ["drug_name"]
    # single domain also exposes one labeled section in results[]
    assert len(payload["results"]) == 1
    assert payload["results"][0]["domain"] == "efficacy"
    assert payload["results"][0]["rows"]["rowcount"] == 1


class _MultiLLM:
    """Content-aware fake routing to two domains (fan-out runs concurrently)."""

    def __init__(self, intro="找到 2 类相关数据。"):
        self.intro = intro

    async def complete(self, model, messages):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_fast:
            return "mutation, expression" if "domain router" in text else "NONE"
        if model == SETTINGS.model_sql:
            if "model_ccle_expression_data" in text:
                return "SELECT model_uuid, log2tpm FROM model_ccle_expression_data "
            return "SELECT model_uuid, mutation_id FROM model_ccle_mutation_data "
        return self.intro

    async def complete_stream(self, model, messages):
        yield self.intro


class _MultiReplica:
    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        col = "log2tpm" if "expression" in sql else "mutation_id"
        return QueryResult(
            columns=[col], rows=[{col: 1}], rowcount=1, truncated=False, sql=sql, elapsed_ms=1.0
        )


def test_query_multi_domain_returns_labeled_sections():
    with _client(_MultiLLM(), _MultiReplica()) as client:
        _, events = _ask(client, "Trp53 相关数据")
    final = events[-1]
    assert final["type"] == "final"
    payload = final["payload"]
    assert payload["status"] == "answered"
    assert payload["sql"] is None and payload["rows"] is None  # multi: no single top-level
    domains = {s["domain"] for s in payload["results"]}
    assert domains == {"mutation", "expression"}
    assert all(s["rows"]["rowcount"] == 1 and s["sql"] for s in payload["results"])


def test_query_clarify_emits_no_tokens():
    llm = _LLM({"qwen-fast": ["clarify: which drug?"]})
    with _client(llm, _Replica([])) as client:
        _, events = _ask(client, "how is it?")
    assert not [e for e in events if e["type"] == "token"]  # never reaches answer
    final = events[-1]
    assert final["type"] == "final"
    assert final["payload"]["status"] == "clarify"
    assert "which drug?" in final["payload"]["clarification"]
    assert final["payload"]["rows"] is None


def test_query_fatal_guard_error_final_is_error():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE"],
        }
    )
    replica = _Replica([GuardError("big_table_scan", "seq scan", retryable=False)])
    with _client(llm, replica) as client:
        _, events = _ask(client, "scan it")
    assert events[-1]["type"] == "final"
    assert events[-1]["payload"]["status"] == "error"


def test_query_llm_exception_emits_error_event():
    with _client(_RaisingLLM(), _Replica([])) as client:
        resp, events = _ask(client, "boom")
    # the stream already started (200); the failure surfaces as a terminal error event
    assert resp.status_code == 200
    assert events[-1]["type"] == "error"
    assert events[-1]["detail"].startswith("agent backend error")


def test_query_missing_question_is_422():
    with _client(_LLM({}), _Replica([])) as client:
        resp = client.post("/query/stream", json={})
    assert resp.status_code == 422


def test_query_invokes_observer():
    records = []
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    deps = Deps(llm=llm, replica=_Replica([_qr()]), layer=LAYER, settings=SETTINGS)
    app = create_app(deps=deps, observer=records.append)
    with TestClient(app) as client:
        resp, events = _ask(client, "how many?")
    assert resp.status_code == 200
    assert events[-1]["payload"]["status"] == "answered"
    assert len(records) == 1
    assert records[0].status == "answered"
