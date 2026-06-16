# Observability Run Logging Implementation Plan (observability/)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement CLAUDE.md item #8 — append one JSONL record per `run_agent` call (question, context, generated + secured SQL, result summary, outcome) as seed data for a future example store.

**Architecture:** A leaf `observability/` module with a `RunRecord` dataclass built from the final `AgentState` and an `Observer` seam (`JsonlObserver` / `NullObserver`). `run_agent` gains an optional `observer=None` param; logging is best-effort (a sink failure never breaks a query). The API lifespan builds the real `JsonlObserver` from a config path and passes it per request. Graph nodes and `Deps` are untouched.

**Tech Stack:** Python 3.14 (uv `.venv`), stdlib `json`/`dataclasses`/`datetime`, pytest (`tmp_path`). Spec: `docs/superpowers/specs/2026-06-16-observability-run-logging-design.md`.

**Conventions:** `from __future__ import annotations` at the top of every module. Run with `uv run`. Offline tests use `tmp_path` + list-collector observers — no real log files, no DB, no LLM. Commit + push after each task.

---

### Task 1: `RunRecord` (record.py)

**Files:**
- Create: `src/db_agent/observability/__init__.py` (empty marker for now)
- Create: `src/db_agent/observability/record.py`
- Test: `tests/test_observability_record.py`

- [ ] **Step 1: Create the empty package marker**

Create `src/db_agent/observability/__init__.py`:

```python
from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_observability_record.py`:

```python
from __future__ import annotations

import json

from db_agent.db import QueryResult
from db_agent.graph.state import initial_state
from db_agent.observability.record import RunRecord


def _final(**over):
    s = initial_state("q?")
    s.update(over)
    return s


def test_from_state_answered_has_result_summary():
    qr = QueryResult(columns=["n"], rows=[{"n": 1}], rowcount=1, truncated=False,
                     sql="SELECT 1", elapsed_ms=1.0)
    s = _final(status="answered", domain="efficacy", context="ctx",
               sql="SELECT 1", secured_sql="SELECT 1 LIMIT 1000", attempts=1,
               result=qr, answer="one")
    r = RunRecord.from_state(s)
    assert r.status == "answered"
    assert r.rowcount == 1 and r.columns == ["n"] and r.truncated is False
    assert r.sql == "SELECT 1 LIMIT 1000" and r.raw_sql == "SELECT 1"
    assert r.domain == "efficacy" and r.context == "ctx" and r.answer == "one"
    assert r.feedback is None
    assert "T" in r.ts  # ISO-8601 timestamp


def test_from_state_clarify_has_no_result():
    s = _final(status="clarify", clarification="which drug?")
    r = RunRecord.from_state(s)
    assert r.status == "clarify"
    assert r.clarification == "which drug?"
    assert r.rowcount is None and r.columns is None and r.truncated is None


def test_to_dict_is_json_serializable():
    s = _final(status="error", error="boom")
    d = RunRecord.from_state(s).to_dict()
    json.dumps(d)  # must not raise
    assert d["status"] == "error" and d["error"] == "boom"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_observability_record.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.observability.record'`.

- [ ] **Step 4: Write the implementation**

Create `src/db_agent/observability/record.py`:

```python
"""The per-run record (CLAUDE.md item #8 tuple), built from the final state.

Summary only: the result is reduced to rowcount/columns/truncated — raw rows are
never captured.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from db_agent.graph.state import AgentState


@dataclass(frozen=True)
class RunRecord:
    ts: str
    question: str
    domain: str | None
    context: str | None
    raw_sql: str | None
    sql: str | None
    status: str
    attempts: int
    rowcount: int | None
    columns: list[str] | None
    truncated: bool | None
    answer: str | None
    clarification: str | None
    error: str | None
    feedback: str | None = None  # placeholder; always None in Phase 1

    @classmethod
    def from_state(cls, state: AgentState) -> RunRecord:
        result = state.get("result")
        if result is not None:
            rowcount, columns, truncated = result.rowcount, result.columns, result.truncated
        else:
            rowcount, columns, truncated = None, None, None
        return cls(
            ts=datetime.now(timezone.utc).isoformat(),
            question=state["question"],
            domain=state.get("domain"),
            context=state.get("context"),
            raw_sql=state.get("sql"),
            sql=state.get("secured_sql"),
            status=state["status"],
            attempts=state["attempts"],
            rowcount=rowcount,
            columns=columns,
            truncated=truncated,
            answer=state.get("answer"),
            clarification=state.get("clarification"),
            error=state.get("error"),
        )

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_observability_record.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/observability/__init__.py src/db_agent/observability/record.py tests/test_observability_record.py
git commit -F - <<'EOF'
Add RunRecord: the per-run observability tuple

Built from the final AgentState; result is summarized to
rowcount/columns/truncated (no raw rows). feedback is a null placeholder.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Observers (observer.py)

**Files:**
- Create: `src/db_agent/observability/observer.py`
- Test: `tests/test_observability_observer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_observability_observer.py`:

```python
from __future__ import annotations

import json

from db_agent.graph.state import initial_state
from db_agent.observability.observer import JsonlObserver, NullObserver, Observer
from db_agent.observability.record import RunRecord


def _rec(status="answered"):
    s = initial_state("q?")
    s["status"] = status
    return RunRecord.from_state(s)


def test_observers_satisfy_protocol(tmp_path):
    assert isinstance(NullObserver(), Observer)
    assert isinstance(JsonlObserver(tmp_path / "x.jsonl"), Observer)


def test_null_observer_writes_nothing(tmp_path):
    NullObserver()(_rec())
    assert list(tmp_path.iterdir()) == []


def test_jsonl_observer_appends_lines(tmp_path):
    p = tmp_path / "logs" / "runs.jsonl"  # parent dir does not exist yet
    obs = JsonlObserver(p)
    obs(_rec("answered"))
    obs(_rec("error"))
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["status"] == "answered"
    assert json.loads(lines[1])["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability_observer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.observability.observer'`.

- [ ] **Step 3: Write the implementation**

Create `src/db_agent/observability/observer.py`:

```python
"""Observability sinks. Observer is the seam run_agent calls; tests inject a
list-appending callable, production injects a JsonlObserver.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from db_agent.observability.record import RunRecord


@runtime_checkable
class Observer(Protocol):
    def __call__(self, record: RunRecord) -> None: ...


class NullObserver:
    def __call__(self, record: RunRecord) -> None:
        return None


class JsonlObserver:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def __call__(self, record: RunRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_observability_observer.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/observability/observer.py tests/test_observability_observer.py
git commit -F - <<'EOF'
Add Observer protocol, NullObserver, and JsonlObserver

JsonlObserver appends one UTF-8 JSON line per record (ensure_ascii=False),
creating the parent dir as needed.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Config path + run_agent integration

**Files:**
- Modify: `src/db_agent/config.py`
- Modify: `src/db_agent/graph/build.py`
- Test: `tests/test_observability_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_observability_integration.py`:

```python
from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.build import run_agent
from db_agent.observability.record import RunRecord
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


class _LLM:
    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}

    def complete(self, model, messages):
        return self.by_model[model].pop(0)


class _Replica:
    def __init__(self, script):
        self.script = list(script)

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        item = self.script.pop(0)
        if isinstance(item, GuardError):
            raise item
        return item


def _qr():
    return QueryResult(columns=["drug_name"], rows=[{"drug_name": "X"}], rowcount=1,
                       truncated=False, sql="SELECT drug_name", elapsed_ms=1.0)


def _happy_llm():
    return _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        "qwen-main": ["Found 1 drug."],
    })


def test_settings_log_path_defaults_none():
    assert SETTINGS.observability_log_path is None


def test_run_agent_emits_one_record():
    records: list[RunRecord] = []
    res = run_agent("how many?", llm=_happy_llm(), replica=_Replica([_qr()]),
                    layer=LAYER, settings=SETTINGS, observer=records.append)
    assert res.status == "answered"
    assert len(records) == 1
    assert records[0].status == "answered"
    assert "for_bd" in records[0].sql.lower()


def test_run_agent_without_observer_is_unchanged():
    res = run_agent("how many?", llm=_happy_llm(), replica=_Replica([_qr()]),
                    layer=LAYER, settings=SETTINGS)
    assert res.status == "answered"


def test_observer_failure_does_not_break_the_run():
    def boom(record):
        raise RuntimeError("sink down")

    res = run_agent("how many?", llm=_happy_llm(), replica=_Replica([_qr()]),
                    layer=LAYER, settings=SETTINGS, observer=boom)
    assert res.status == "answered"
    assert res.answer == "Found 1 drug."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability_integration.py -q`
Expected: FAIL — `Settings` has no `observability_log_path`, and `run_agent` has no `observer` parameter.

- [ ] **Step 3: Add the config field**

In `src/db_agent/config.py`, add this field inside `Settings` immediately after the `semantic_layer_path` field:

```python
    # --- observability ---
    observability_log_path: Path | None = None
```

- [ ] **Step 4: Wire the observer into run_agent**

In `src/db_agent/graph/build.py`, add these imports after the existing `from db_agent.graph.state import ...` line:

```python
from db_agent.observability.observer import Observer
from db_agent.observability.record import RunRecord
```

Replace the `run_agent` function with:

```python
def run_agent(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
    observer: Observer | None = None,
) -> AgentResult:
    deps = Deps(llm=llm, replica=replica, layer=layer, settings=settings)
    graph = build_graph(deps)
    final = graph.invoke(initial_state(question))
    if observer is not None:
        try:
            observer(RunRecord.from_state(final))
        except Exception:
            pass  # observability is best-effort; never break a good answer
    return to_result(final)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_observability_integration.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/config.py src/db_agent/graph/build.py tests/test_observability_integration.py
git commit -F - <<'EOF'
Wire observability into run_agent + add config log path

run_agent gains an optional observer= param; after invoke it emits a RunRecord
(best-effort — a sink exception never breaks the run). Settings gains
observability_log_path (default None = disabled). Graph nodes and Deps unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: API wiring (observer per request)

**Files:**
- Modify: `src/db_agent/api/app.py`
- Test: `tests/test_api_endpoint.py` (add one case)

- [ ] **Step 1: Write the failing test**

Add this test to the end of `tests/test_api_endpoint.py` (the `_LLM`, `_Replica`, `_qr`, `Deps`, `create_app`, `TestClient` imports already exist in that file):

```python
def test_query_invokes_observer():
    records = []
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        "qwen-main": ["Found 1 drug."],
    })
    deps = Deps(llm=llm, replica=_Replica([_qr()]), layer=LAYER, settings=SETTINGS)
    app = create_app(deps=deps, observer=records.append)
    with TestClient(app) as client:
        resp = client.post("/query", json={"question": "how many?"})
    assert resp.status_code == 200
    assert len(records) == 1
    assert records[0].status == "answered"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api_endpoint.py::test_query_invokes_observer -q`
Expected: FAIL — `create_app()` does not accept an `observer` argument yet.

- [ ] **Step 3: Wire the observer into the app**

In `src/db_agent/api/app.py`, add this import after the existing `from db_agent.llm import LiteLLMClient` line:

```python
from db_agent.observability.observer import JsonlObserver, NullObserver, Observer
```

Change the `/query` handler so it passes the observer — replace the `run_agent(...)` call inside `query` with:

```python
        result = run_agent(
            req.question,
            llm=deps.llm,
            replica=deps.replica,
            layer=deps.layer,
            settings=deps.settings,
            observer=request.app.state.observer,
        )
```

Replace the `create_app` signature and both lifespan branches:

```python
def create_app(deps: Deps | None = None, observer: Observer | None = None) -> FastAPI:
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
            app.state.observer = (
                JsonlObserver(s.observability_log_path)
                if s.observability_log_path is not None
                else NullObserver()
            )
            try:
                yield
            finally:
                replica.close()
        else:
            app.state.deps = deps
            app.state.observer = observer if observer is not None else NullObserver()
            yield

    app = FastAPI(title="DB-Agent", lifespan=lifespan)
    app.include_router(router)
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api_endpoint.py -q`
Expected: PASS (7 passed — the 6 existing cases plus the new observer case).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/api/app.py tests/test_api_endpoint.py
git commit -F - <<'EOF'
Wire observability into the API

The lifespan builds a JsonlObserver from observability_log_path (or NullObserver),
stores it on app.state, and /query passes it to run_agent. create_app accepts an
observer override for tests.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: Public exports + full offline suite + ruff

**Files:**
- Modify: `src/db_agent/observability/__init__.py`

- [ ] **Step 1: Write the package exports**

Replace `src/db_agent/observability/__init__.py` with:

```python
"""Observability: per-run JSONL logging of the item-#8 tuple."""

from __future__ import annotations

from db_agent.observability.observer import JsonlObserver, NullObserver, Observer
from db_agent.observability.record import RunRecord

__all__ = ["JsonlObserver", "NullObserver", "Observer", "RunRecord"]
```

- [ ] **Step 2: Verify the package imports**

Run: `uv run python -c "from db_agent.observability import RunRecord, Observer, JsonlObserver, NullObserver; print('imports OK')"`
Expected: prints `imports OK`.

- [ ] **Step 3: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `5 deselected` (integration). All offline tests green, including the new observability record/observer/integration tests and the new API observer case.

- [ ] **Step 4: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff check` reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff format src tests` and re-run.)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/observability/__init__.py
git commit -F - <<'EOF'
Export observability public API and finalize the module

RunRecord + Observer/NullObserver/JsonlObserver. Full offline suite green; ruff
clean. Enable by setting DBAGENT_OBSERVABILITY_LOG_PATH.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

## Self-Review

**Spec coverage:**
- `record.py` RunRecord + from_state + to_dict (summary-only result) → Task 1. ✅
- `observer.py` Observer protocol + NullObserver + JsonlObserver (append, ensure_ascii=False, mkdir) → Task 2. ✅
- `run_agent` optional `observer=` hook, best-effort (catches sink errors) → Task 3. ✅
- `config.observability_log_path` (None disables) → Task 3. ✅
- API lifespan builds JsonlObserver/NullObserver, `/query` passes it; `create_app(observer=)` test seam → Task 4. ✅
- Offline tests (from_state per status, Jsonl append, Null no-op, run_agent collector, observer-raises-no-break) → Tasks 1–4. ✅
- feedback null placeholder → Task 1 (`feedback: str | None = None`). ✅
- Out of scope (feedback signal, rotation, async, pgvector) → not built. ✅

**Placeholder scan:** No TBD/TODO; every code/test/command step is complete. Task 5 Step 3 uses the deterministic check ("green + 5 deselected"). ✅

**Type consistency:** `RunRecord.from_state(state) -> RunRecord` / `.to_dict() -> dict`; `Observer.__call__(record: RunRecord) -> None`; `JsonlObserver(path)`; `run_agent(question, *, llm, replica, layer, settings, observer=None)`; `create_app(deps=None, observer=None)`; `AgentState` fields (`secured_sql`, `sql`, `result`, `attempts`, ...) and `QueryResult(columns, rowcount, truncated, ...)` — all used identically across tasks and consistent with the shipped `graph/`, `db/`, `api/` code. ✅

**Note:** No dependency changes (stdlib only). Task 3 modifies `graph/build.py` (not under `sql/`), so the Stop hook does not trigger; the PostToolUse ruff hook runs on each edit. The API change keeps the existing 6 endpoint tests valid (the injected branch defaults `app.state.observer` to `NullObserver()`).
