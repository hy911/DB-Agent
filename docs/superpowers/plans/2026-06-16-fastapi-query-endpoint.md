# FastAPI Query Endpoint Implementation Plan (api/)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `db_agent.graph.run_agent` over HTTP as one synchronous JSON endpoint (`POST /query`) plus a `GET /health`, wrapping the agent without changing it.

**Architecture:** `create_app(deps=None)` is the injection seam: production builds the real `ReadReplica` pool + `LiteLLMClient` + semantic layer in the FastAPI lifespan; tests pass fake `Deps` so `TestClient` runs fully offline. The endpoint reads `request.app.state.deps`, calls `run_agent`, and maps `AgentResult` → `QueryResponse`. Agent outcomes are HTTP 200 with a `status` field; an exception escaping `run_agent` is HTTP 502.

**Tech Stack:** Python 3.14 (uv `.venv`), FastAPI + Starlette `TestClient` (httpx already installed), Pydantic v2, pytest. Spec: `docs/superpowers/specs/2026-06-16-fastapi-query-endpoint-design.md`. Builds on the shipped `graph/`, `db/`, `llm/`, `semantic/` layers.

**Conventions:** `from __future__ import annotations` at the top of every module. Run with `uv run`. Offline tests inject `FakeLLM` + `FakeReplica` — no real LLM or DB. Commit + push after each task.

---

### Task 1: Request/response schemas

**Files:**
- Create: `src/db_agent/api/__init__.py` (empty marker for now)
- Create: `src/db_agent/api/schemas.py`
- Test: `tests/test_api_schemas.py`

- [ ] **Step 1: Create the empty package marker**

Create `src/db_agent/api/__init__.py`:

```python
from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_api_schemas.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from db_agent.api.schemas import QueryRequest, QueryResponse, ResultRows


def test_query_request_requires_question():
    assert QueryRequest(question="hi").question == "hi"
    with pytest.raises(ValidationError):
        QueryRequest()


def test_query_response_defaults_are_none():
    r = QueryResponse(status="error")
    assert r.status == "error"
    assert r.answer is None
    assert r.rows is None


def test_query_response_carries_rows():
    rows = ResultRows(columns=["a"], rows=[{"a": 1}], rowcount=1, truncated=False)
    r = QueryResponse(status="answered", answer="ok", sql="SELECT 1", rows=rows)
    dumped = r.model_dump()
    assert dumped["rows"]["columns"] == ["a"]
    assert dumped["status"] == "answered"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_api_schemas.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.api.schemas'`.

- [ ] **Step 4: Write the implementation**

Create `src/db_agent/api/schemas.py`:

```python
"""Pydantic request/response models for the query endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class ResultRows(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool


class QueryResponse(BaseModel):
    status: str  # answered | clarify | error
    answer: str | None = None
    sql: str | None = None
    clarification: str | None = None
    error: str | None = None
    rows: ResultRows | None = None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api_schemas.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/api/__init__.py src/db_agent/api/schemas.py tests/test_api_schemas.py
git commit -F - <<'EOF'
Add API request/response schemas

QueryRequest{question}, QueryResponse{status,answer,sql,clarification,error,rows}
and ResultRows for the JSON query endpoint.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: App factory, routes, and endpoint tests

**Files:**
- Create: `src/db_agent/api/app.py`
- Test: `tests/test_api_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_endpoint.py`:

```python
from __future__ import annotations

import pytest
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
    return QueryResult(columns=["drug_name"], rows=[{"drug_name": "X"}], rowcount=1,
                       truncated=False, sql="SELECT drug_name", elapsed_ms=1.0)


def test_health():
    with _client(_LLM({}), _Replica([])) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_query_answered_includes_rows():
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        "qwen-main": ["Found 1 drug."],
    })
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
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
    })
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_endpoint.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.api.app'`.

- [ ] **Step 3: Write the implementation**

Create `src/db_agent/api/app.py`:

```python
"""FastAPI app: POST /query (wraps run_agent) and GET /health.

create_app(deps=None) is the injection seam: with deps=None the lifespan builds
the real ReadReplica pool + LiteLLMClient + semantic layer; with deps provided
(tests) it stores them and does no I/O. The endpoint reads request.app.state.deps
and maps AgentResult -> QueryResponse. Agent outcomes are 200 (with a status
field); an exception out of run_agent is 502.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request

from db_agent.api.schemas import QueryRequest, QueryResponse, ResultRows
from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.graph import run_agent
from db_agent.graph.state import AgentResult, Deps
from db_agent.llm import LiteLLMClient
from db_agent.semantic import load_semantic_layer

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request) -> QueryResponse:
    deps: Deps = request.app.state.deps
    try:
        result = run_agent(
            req.question,
            llm=deps.llm,
            replica=deps.replica,
            layer=deps.layer,
            settings=deps.settings,
        )
    except Exception as exc:  # infrastructure failure (gateway down, pool timeout)
        raise HTTPException(status_code=502, detail="agent backend error") from exc
    return _to_response(result)


def _to_response(result: AgentResult) -> QueryResponse:
    rows = None
    if result.result is not None:
        qr = result.result
        rows = ResultRows(
            columns=qr.columns,
            rows=qr.rows,
            rowcount=qr.rowcount,
            truncated=qr.truncated,
        )
    return QueryResponse(
        status=result.status,
        answer=result.answer,
        sql=result.sql,
        clarification=result.clarification,
        error=result.error,
        rows=rows,
    )


def create_app(deps: Deps | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if deps is None:
            s = get_settings()
            replica = ReadReplica(s)
            replica.open()
            app.state.deps = Deps(
                llm=LiteLLMClient(s),
                replica=replica,
                layer=load_semantic_layer(s.semantic_layer_path),
                settings=s,
            )
            try:
                yield
            finally:
                replica.close()
        else:
            app.state.deps = deps
            yield

    app = FastAPI(title="DB-Agent", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_endpoint.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/api/app.py tests/test_api_endpoint.py
git commit -F - <<'EOF'
Add FastAPI app: POST /query + GET /health

create_app(deps=None) builds the real pool/clients in the lifespan or stores
injected fakes for offline tests. /query wraps run_agent and maps AgentResult to
QueryResponse: agent outcomes are 200+status, an exception out of run_agent is
502. Six TestClient cases cover answered/clarify/error/502/422/health.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Public exports + full offline suite + ruff

**Files:**
- Modify: `src/db_agent/api/__init__.py`

- [ ] **Step 1: Write the package exports**

Replace `src/db_agent/api/__init__.py` with:

```python
"""HTTP boundary: the FastAPI query endpoint over the agent chain."""

from __future__ import annotations

from db_agent.api.app import app, create_app
from db_agent.api.schemas import QueryRequest, QueryResponse, ResultRows

__all__ = ["QueryRequest", "QueryResponse", "ResultRows", "app", "create_app"]
```

- [ ] **Step 2: Verify the package imports**

Run: `uv run python -c "from db_agent.api import create_app, app, QueryResponse; print('imports OK')"`
Expected: prints `imports OK`.

- [ ] **Step 3: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `5 deselected` (integration). All offline tests green, including the new api schema + endpoint tests.

- [ ] **Step 4: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff check` reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff format src tests` and re-run.)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/api/__init__.py
git commit -F - <<'EOF'
Export api/ public API and finalize the endpoint

create_app/app plus the request/response schemas. Full offline suite green; ruff
clean. Serve with: uv run uvicorn db_agent.api.app:app

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

## Self-Review

**Spec coverage:**
- `schemas.py` (QueryRequest/ResultRows/QueryResponse) → Task 1. ✅
- `create_app(deps=None)` injection seam + lifespan (real vs injected) → Task 2. ✅
- Routes `POST /query`, `GET /health`; `_to_response` mapping incl. rows → Task 2. ✅
- HTTP semantics (200 for answered/clarify/error; 502 for exception; 422 for bad body) → Task 2 tests. ✅
- Module-level `app = create_app()` for uvicorn → Task 2. ✅
- Offline testability with fakes via TestClient → Task 2 (uses `with TestClient(app)` so the lifespan runs and sets `app.state.deps`). ✅
- Out of scope (streaming, auth, observability, live smoke) → not built. ✅

**Placeholder scan:** No TBD/TODO; every code/test/command step is complete. Task 3 Step 3 uses the deterministic check ("green + 5 deselected"). ✅

**Type consistency:** `create_app(deps: Deps | None) -> FastAPI`; `Deps(llm, replica, layer, settings)`; `run_agent(question, *, llm, replica, layer, settings) -> AgentResult`; `AgentResult.result : QueryResult | None`; `QueryResult(columns, rows, rowcount, truncated, sql, elapsed_ms)`; `QueryResponse(status, answer, sql, clarification, error, rows)`; `ResultRows(columns, rows, rowcount, truncated)` — all used identically across tasks and consistent with the shipped `graph/`, `db/` code. ✅

**Note:** No dependency changes (`fastapi`, `uvicorn`, and `httpx` are already available). New files live under `api/` and `tests/`, so the `sql/` PreToolUse guard and Stop hook do not trigger; the PostToolUse ruff hook runs on each edit. Tests must use `with TestClient(app) as client:` so the lifespan runs and `app.state.deps` is populated before requests.
