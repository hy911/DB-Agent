# graph/ Layer Implementation Plan (Plan B of the agent chain)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `semantic/` + `sql/` + `db/` + `llm/` into one LangGraph chain — `run_agent(question, ...) -> AgentResult` — that routes/clarifies, generates SQL, secures it, executes it on the replica, self-corrects (≤3), and answers in natural language.

**Architecture:** A `StateGraph` over a `AgentState` TypedDict. Nodes are plain functions `node(state, deps)` bound with `functools.partial(node, deps=deps)` at build time, so each node is unit-testable in isolation and all external dependencies (LLM, replica, layer, settings) are injected. The self-correction loop and clarification are conditional edges keyed on a transient `outcome` field. A new pure `sql/secure.py` bridges the `sql/` guard pieces into one call.

**Tech Stack:** Python 3.14 (uv `.venv`), `langgraph` (already in deps), pytest. Spec: `docs/superpowers/specs/2026-06-16-langgraph-agent-chain-design.md`. Builds on the shipped `db/` and `llm/` layers.

**Conventions:** `from __future__ import annotations` at the top of every module. Run with `uv run`. Offline tests inject `FakeLLM` + `FakeReplica` — no real LLM or DB. Commit + push after each task.

**Heads-up:** Task 1 adds a file under `src/db_agent/sql/`, so the repo's Stop hook will ask for an `sql-security-reviewer` pass at end of turn — that is expected; run the reviewer (or note the change is additive orchestration) and continue.

---

### Task 1: `sql/secure.py` — one-call guard bridge

**Files:**
- Create: `src/db_agent/sql/secure.py`
- Test: `tests/test_sql_secure.py`

`secure_query` runs parse → validate → inject → enforce-limit and returns the
secured SQL string plus the flags `db/` needs (`needs_explain`, `big_tables`,
`limit`). Pure (no I/O).

- [ ] **Step 1: Write the failing test**

Create `tests/test_sql_secure.py`:

```python
from __future__ import annotations

import pytest

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError
from db_agent.sql.secure import SecuredQuery, secure_query

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_secure_injects_permission_and_limit():
    out = secure_query("SELECT drug_name FROM model_efficacy_info", LAYER, "efficacy")
    assert isinstance(out, SecuredQuery)
    low = out.sql.lower()
    assert "for_bd" in low and "'yes'" in low      # permission injected
    assert "limit" in low                           # limit enforced
    assert out.needs_explain is False               # not the big table
    assert out.limit is not None and out.limit > 0


def test_secure_rejects_out_of_scope_table():
    with pytest.raises(GuardError) as exc:
        secure_query("SELECT * FROM django_session", LAYER, "efficacy")
    assert exc.value.retryable is False


def test_secure_rejects_non_select():
    with pytest.raises(GuardError):
        secure_query("UPDATE model_efficacy_info SET for_bd='no'", LAYER, "efficacy")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sql_secure.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.sql.secure'`.

- [ ] **Step 3: Write the implementation**

Create `src/db_agent/sql/secure.py`:

```python
"""One-call bridge over the sql/ guard rails (pure, no I/O).

Runs parse -> validate -> inject permissions -> enforce LIMIT on a generated SQL
string and returns the secured SQL plus the flags db/ needs to execute it
safely. Raises GuardError (with its retryable flag) if the query cannot be
secured — the graph's self-correction loop decides what to do with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from db_agent.semantic.model import SemanticLayer
from db_agent.sql.permission import inject_permissions, injection_config_for_domain
from db_agent.sql.validator import (
    enforce_limit,
    parse_single_statement,
    requires_explain_guard,
    validate_structure,
    validation_config_for_domain,
)


@dataclass(frozen=True)
class SecuredQuery:
    sql: str
    needs_explain: bool
    big_tables: frozenset[str]
    limit: int | None


def secure_query(sql: str, layer: SemanticLayer, domain: str) -> SecuredQuery:
    ast = parse_single_statement(sql)
    vcfg = validation_config_for_domain(layer, domain)
    validate_structure(ast, vcfg)

    icfg = injection_config_for_domain(layer, domain)
    if icfg is not None:
        ast = inject_permissions(ast, icfg)

    ast = enforce_limit(ast, vcfg)
    needs_explain = requires_explain_guard(ast, vcfg)
    return SecuredQuery(
        sql=ast.sql(dialect="postgres"),
        needs_explain=needs_explain,
        big_tables=vcfg.big_tables,
        limit=_limit_value(ast),
    )


def _limit_value(ast: exp.Expression) -> int | None:
    limit = ast.args.get("limit")
    if limit is None:
        return None
    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int:
        return int(value.name)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sql_secure.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/sql/secure.py tests/test_sql_secure.py
git commit -F - <<'EOF'
Add sql/secure.py: one-call guard bridge for the graph

secure_query runs parse -> validate -> inject -> enforce-limit and returns the
secured SQL plus needs_explain/big_tables/limit. Pure; raises GuardError on an
unsecurable query.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: `graph/state.py` — state, result, deps

**Files:**
- Create: `src/db_agent/graph/__init__.py` (empty marker for now)
- Create: `src/db_agent/graph/state.py`
- Test: `tests/test_graph_state.py`

- [ ] **Step 1: Create the empty package marker**

Create `src/db_agent/graph/__init__.py`:

```python
from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_graph_state.py`:

```python
from __future__ import annotations

from db_agent.graph.state import AgentResult, initial_state, to_result


def test_initial_state_defaults():
    s = initial_state("how many?")
    assert s["question"] == "how many?"
    assert s["attempts"] == 0
    assert s["status"] == "running"
    assert s["big_tables"] == frozenset()


def test_to_result_maps_fields():
    s = initial_state("q")
    s["status"] = "answered"
    s["answer"] = "42"
    s["secured_sql"] = "SELECT 1 LIMIT 1000"
    r = to_result(s)
    assert isinstance(r, AgentResult)
    assert r.status == "answered"
    assert r.answer == "42"
    assert r.sql == "SELECT 1 LIMIT 1000"
    assert r.clarification is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_state.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.graph.state'`.

- [ ] **Step 4: Write the implementation**

Create `src/db_agent/graph/state.py`:

```python
"""Graph state, the public result object, and the injected dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from typing_extensions import NotRequired

from db_agent.config import Settings
from db_agent.db import QueryResult, ReadReplica
from db_agent.llm.client import LLMClient
from db_agent.semantic.model import SemanticLayer


class AgentState(TypedDict):
    question: str
    domain: str | None
    context: str | None
    sql: str | None
    secured_sql: str | None
    needs_explain: bool
    big_tables: frozenset[str]
    limit: int | None
    attempts: int
    last_error: str | None
    outcome: str  # "" | "ok" | "retry" | "fatal"
    result: NotRequired[QueryResult | None]
    answer: str | None
    clarification: str | None
    status: str  # running | answered | clarify | error
    error: str | None


def initial_state(question: str) -> AgentState:
    return AgentState(
        question=question,
        domain=None,
        context=None,
        sql=None,
        secured_sql=None,
        needs_explain=False,
        big_tables=frozenset(),
        limit=None,
        attempts=0,
        last_error=None,
        outcome="",
        result=None,
        answer=None,
        clarification=None,
        status="running",
        error=None,
    )


@dataclass(frozen=True)
class AgentResult:
    status: str
    answer: str | None
    sql: str | None
    clarification: str | None
    error: str | None
    result: QueryResult | None


def to_result(state: AgentState) -> AgentResult:
    return AgentResult(
        status=state["status"],
        answer=state.get("answer"),
        sql=state.get("secured_sql"),
        clarification=state.get("clarification"),
        error=state.get("error"),
        result=state.get("result"),
    )


@dataclass(frozen=True)
class Deps:
    llm: LLMClient
    replica: ReadReplica
    layer: SemanticLayer
    settings: Settings
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_state.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/graph/__init__.py src/db_agent/graph/state.py tests/test_graph_state.py
git commit -F - <<'EOF'
Add graph state, AgentResult, and Deps

AgentState TypedDict threaded through the graph; initial_state/to_result helpers;
frozen Deps bundling the injected llm/replica/layer/settings.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: `graph/nodes.py` — node functions + routers

**Files:**
- Create: `src/db_agent/graph/nodes.py`
- Test: `tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_nodes.py`:

```python
from __future__ import annotations

import pytest

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.nodes import (
    after_execute,
    after_guard,
    after_route,
    answer_node,
    execute_node,
    generate_sql_node,
    guard_node,
    route_node,
)
from db_agent.graph.state import Deps, initial_state
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError
from langgraph.graph import END

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
        self.calls = 0

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, GuardError):
            raise item
        return item


def _deps(llm=None, replica=None):
    return Deps(llm=llm, replica=replica, layer=LAYER, settings=SETTINGS)


def test_route_efficacy_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["efficacy"]}))
    out = route_node(initial_state("how many models?"), deps)
    assert out["domain"] == "efficacy"
    assert out.get("status") != "clarify"


def test_route_clarify_sets_status():
    deps = _deps(llm=_LLM({"qwen-fast": ["clarify: which drug?"]}))
    out = route_node(initial_state("how is it?"), deps)
    assert out["status"] == "clarify"
    assert "which drug?" in out["clarification"]


def test_after_route_branches():
    s = initial_state("q")
    assert after_route(s) == "assemble_context"
    s["status"] = "clarify"
    assert after_route(s) == END


def test_generate_sql_increments_attempts():
    deps = _deps(llm=_LLM({"qwen-code": ["SELECT 1"]}))
    s = initial_state("q")
    s["context"] = "ctx"
    out = generate_sql_node(s, deps)
    assert out["sql"] == "SELECT 1"
    assert out["attempts"] == 1


def test_guard_ok_sets_secured_sql():
    deps = _deps()
    s = initial_state("q")
    s["sql"] = "SELECT drug_name FROM model_efficacy_info"
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "ok"
    assert "for_bd" in out["secured_sql"].lower()


def test_guard_retryable_under_budget():
    deps = _deps()
    s = initial_state("q")
    s["sql"] = "SELECT (("  # parse error -> retryable GuardError
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "retry"
    assert out["last_error"]


def test_guard_retryable_at_budget_is_fatal():
    deps = _deps()
    s = initial_state("q")
    s["sql"] = "SELECT (("
    s["attempts"] = 3  # == max_sql_retries
    out = guard_node(s, deps)
    assert out["outcome"] == "fatal"
    assert out["status"] == "error"


def test_execute_ok_sets_result():
    qr = QueryResult(columns=["n"], rows=[{"n": 1}], rowcount=1, truncated=False,
                     sql="SELECT 1", elapsed_ms=1.0)
    deps = _deps(replica=_Replica([qr]))
    s = initial_state("q")
    s["secured_sql"] = "SELECT 1 LIMIT 1000"
    s["attempts"] = 1
    out = execute_node(s, deps)
    assert out["outcome"] == "ok"
    assert out["result"] is qr


def test_execute_fatal_guarderror_no_retry():
    deps = _deps(replica=_Replica([GuardError("big_table_scan", "x", retryable=False)]))
    s = initial_state("q")
    s["secured_sql"] = "SELECT 1"
    s["attempts"] = 1
    out = execute_node(s, deps)
    assert out["outcome"] == "fatal"
    assert out["status"] == "error"


def test_after_guard_and_execute_dispatch():
    s = initial_state("q")
    s["outcome"] = "ok"
    assert after_guard(s) == "execute"
    assert after_execute(s) == "answer"
    s["outcome"] = "retry"
    assert after_guard(s) == "generate_sql"
    assert after_execute(s) == "generate_sql"
    s["outcome"] = "fatal"
    assert after_guard(s) == END
    assert after_execute(s) == END


def test_answer_node_sets_answer():
    qr = QueryResult(columns=["n"], rows=[{"n": 1}], rowcount=1, truncated=False,
                     sql="SELECT 1", elapsed_ms=1.0)
    deps = _deps(llm=_LLM({"qwen-main": ["One row."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT 1"
    s["result"] = qr
    out = answer_node(s, deps)
    assert out["answer"] == "One row."
    assert out["status"] == "answered"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.graph.nodes'`.

- [ ] **Step 3: Write the implementation**

Create `src/db_agent/graph/nodes.py`:

```python
"""Graph nodes and routers.

Each node is `node(state, deps) -> dict-of-updates`; `build_graph` binds `deps`
with functools.partial so LangGraph calls them with just `state`. Guard/execute
nodes catch GuardError and write a transient `outcome` the routers dispatch on.
"""

from __future__ import annotations

from langgraph.graph import END

from db_agent.graph.state import AgentState, Deps
from db_agent.llm import answer as llm_answer
from db_agent.llm import generate_sql as llm_generate_sql
from db_agent.llm import route as llm_route
from db_agent.sql.errors import GuardError
from db_agent.sql.secure import secure_query

_DOMAIN = "efficacy"


def route_node(state: AgentState, deps: Deps) -> dict:
    res = llm_route(deps.llm, deps.settings, state["question"])
    if res.domain == _DOMAIN:
        return {"domain": _DOMAIN}
    return {"clarification": res.clarification, "status": "clarify"}


def after_route(state: AgentState) -> str:
    return END if state["status"] == "clarify" else "assemble_context"


def assemble_context_node(state: AgentState, deps: Deps) -> dict:
    return {"context": _render_context(deps)}


def generate_sql_node(state: AgentState, deps: Deps) -> dict:
    sql = llm_generate_sql(
        deps.llm, deps.settings, state["question"], state["context"], state["last_error"]
    )
    return {"sql": sql, "attempts": state["attempts"] + 1}


def guard_node(state: AgentState, deps: Deps) -> dict:
    try:
        secured = secure_query(state["sql"], deps.layer, _DOMAIN)
    except GuardError as e:
        return _on_guard_error(state, deps, e)
    return {
        "secured_sql": secured.sql,
        "needs_explain": secured.needs_explain,
        "big_tables": secured.big_tables,
        "limit": secured.limit,
        "outcome": "ok",
        "last_error": None,
    }


def execute_node(state: AgentState, deps: Deps) -> dict:
    try:
        result = deps.replica.execute(
            state["secured_sql"],
            needs_explain=state["needs_explain"],
            big_tables=state["big_tables"],
            limit=state["limit"],
        )
    except GuardError as e:
        return _on_guard_error(state, deps, e)
    return {"result": result, "outcome": "ok"}


def after_guard(state: AgentState) -> str:
    return {"ok": "execute", "retry": "generate_sql", "fatal": END}[state["outcome"]]


def after_execute(state: AgentState) -> str:
    return {"ok": "answer", "retry": "generate_sql", "fatal": END}[state["outcome"]]


def answer_node(state: AgentState, deps: Deps) -> dict:
    text = llm_answer(
        deps.llm, deps.settings, state["question"], state["secured_sql"], state["result"]
    )
    return {"answer": text, "status": "answered"}


def _on_guard_error(state: AgentState, deps: Deps, e: GuardError) -> dict:
    msg = f"{e.category}: {e.message}"
    if not e.retryable or state["attempts"] >= deps.settings.max_sql_retries:
        return {"outcome": "fatal", "status": "error", "error": msg}
    return {"outcome": "retry", "last_error": msg}


def _render_context(deps: Deps) -> str:
    tables = deps.layer.tables_in_domain(_DOMAIN) + deps.layer.reference_tables()
    return "\n".join(f"{t.name}({', '.join(t.columns)})" for t in tables)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/nodes.py tests/test_graph_nodes.py
git commit -F - <<'EOF'
Add graph nodes and routers

route/assemble_context/generate_sql/guard/execute/answer node functions plus
after_route/after_guard/after_execute routers. Guard and execute catch GuardError
and set a transient outcome (ok/retry/fatal) with the retry budget enforced.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: `graph/build.py` — wiring + run_agent (full-graph tests)

**Files:**
- Create: `src/db_agent/graph/build.py`
- Test: `tests/test_graph_chain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_graph_chain.py`:

```python
from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.build import run_agent
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
        self.calls = 0

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, GuardError):
            raise item
        return item


def _run(llm, replica, question="how many models for BD?"):
    return run_agent(question, llm=llm, replica=replica, layer=LAYER, settings=SETTINGS)


def _qr():
    return QueryResult(columns=["drug_name"], rows=[{"drug_name": "X"}], rowcount=1,
                       truncated=False, sql="SELECT drug_name", elapsed_ms=1.0)


def test_happy_path():
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        "qwen-main": ["Found 1 drug."],
    })
    replica = _Replica([_qr()])
    res = _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "Found 1 drug."
    assert "for_bd" in res.sql.lower()  # permission injected into the SQL that ran


def test_self_correction_then_success():
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": [
            "SELECT bad_col FROM model_efficacy_info",
            "SELECT drug_name FROM model_efficacy_info",
        ],
        "qwen-main": ["Recovered."],
    })
    replica = _Replica([GuardError("bad_column", "no col", retryable=True), _qr()])
    res = _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "Recovered."
    assert replica.calls == 2


def test_retry_budget_exhausted():
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"] * 3,
    })
    replica = _Replica([GuardError("bad_column", "no col", retryable=True)] * 3)
    res = _run(llm, replica)
    assert res.status == "error"
    assert replica.calls == 3


def test_clarification_short_circuits():
    llm = _LLM({"qwen-fast": ["clarify: which drug do you mean?"]})
    replica = _Replica([])
    res = _run(llm, replica)
    assert res.status == "clarify"
    assert "which drug" in res.clarification
    assert replica.calls == 0  # DB never touched


def test_fatal_guarderror_no_retry():
    llm = _LLM({
        "qwen-fast": ["efficacy"],
        "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
    })
    replica = _Replica([GuardError("big_table_scan", "seq scan", retryable=False)])
    res = _run(llm, replica)
    assert res.status == "error"
    assert replica.calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.graph.build'`.

- [ ] **Step 3: Write the implementation**

Create `src/db_agent/graph/build.py`:

```python
"""Build and run the agent graph.

`build_graph(deps)` wires the nodes (deps bound via functools.partial) into a
StateGraph with conditional edges for clarification and the self-correction loop.
`run_agent` is the public entry point: build, invoke, map to AgentResult.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from db_agent.config import Settings
from db_agent.db import ReadReplica
from db_agent.graph import nodes
from db_agent.graph.state import AgentResult, AgentState, Deps, initial_state, to_result
from db_agent.llm.client import LLMClient
from db_agent.semantic.model import SemanticLayer


def build_graph(deps: Deps):
    g = StateGraph(AgentState)
    g.add_node("route", partial(nodes.route_node, deps=deps))
    g.add_node("assemble_context", partial(nodes.assemble_context_node, deps=deps))
    g.add_node("generate_sql", partial(nodes.generate_sql_node, deps=deps))
    g.add_node("guard", partial(nodes.guard_node, deps=deps))
    g.add_node("execute", partial(nodes.execute_node, deps=deps))
    g.add_node("answer", partial(nodes.answer_node, deps=deps))

    g.add_edge(START, "route")
    g.add_conditional_edges("route", nodes.after_route, ["assemble_context", END])
    g.add_edge("assemble_context", "generate_sql")
    g.add_edge("generate_sql", "guard")
    g.add_conditional_edges("guard", nodes.after_guard, ["execute", "generate_sql", END])
    g.add_conditional_edges("execute", nodes.after_execute, ["answer", "generate_sql", END])
    g.add_edge("answer", END)
    return g.compile()


def run_agent(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
) -> AgentResult:
    deps = Deps(llm=llm, replica=replica, layer=layer, settings=settings)
    graph = build_graph(deps)
    final = graph.invoke(initial_state(question))
    return to_result(final)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/build.py tests/test_graph_chain.py
git commit -F - <<'EOF'
Wire the agent graph and add run_agent (full-graph tests)

StateGraph with clarification short-circuit and the self-correction loop as
conditional edges. Five end-to-end tests with FakeLLM + FakeReplica: happy path,
self-correct-then-succeed, retry budget exhausted, clarify, fatal-no-retry.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: Public exports + full offline suite + ruff

**Files:**
- Modify: `src/db_agent/graph/__init__.py`

- [ ] **Step 1: Write the package exports**

Replace `src/db_agent/graph/__init__.py` with:

```python
"""Agent graph: the end-to-end chain wiring semantic/sql/db/llm together."""

from __future__ import annotations

from db_agent.graph.build import build_graph, run_agent
from db_agent.graph.state import AgentResult, AgentState

__all__ = ["AgentResult", "AgentState", "build_graph", "run_agent"]
```

- [ ] **Step 2: Verify the package imports**

Run: `uv run python -c "from db_agent.graph import run_agent, build_graph, AgentResult; print('imports OK')"`
Expected: prints `imports OK`.

- [ ] **Step 3: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `5 deselected` (integration). All offline tests green, including the new sql/secure, graph state/nodes/chain tests.

- [ ] **Step 4: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff check` reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff format src tests` and re-run.)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/__init__.py
git commit -F - <<'EOF'
Export graph/ public API and finalize the agent chain

run_agent/build_graph/AgentResult/AgentState. Full offline suite green; ruff
clean.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 6: Live end-to-end smoke (real LLM + real DB)

> **Prerequisite:** `.env` must have a working `DBAGENT_REPLICA_DSN` (authenticates) and the LiteLLM gateway (`LITELLM_BASE_URL` + `LITELLM_MASTER_KEY`) reachable. If the LLM call or DB connection fails, STOP and report the error — do not guess credentials or loop.

**Files:** none (manual verification script).

- [ ] **Step 1: Run the chain end-to-end against real services**

Run:

```bash
uv run python - <<'PY'
from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.graph import run_agent
from db_agent.llm import LiteLLMClient
from db_agent.semantic import load_semantic_layer

s = get_settings()
replica = ReadReplica(s)
replica.open()
try:
    res = run_agent(
        "How many efficacy models are marked for BD?",
        llm=LiteLLMClient(s),
        replica=replica,
        layer=load_semantic_layer(s.semantic_layer_path),
        settings=s,
    )
    print("status     :", res.status)
    print("answer     :", res.answer)
    print("clarify    :", res.clarification)
    print("error      :", res.error)
    print("sql        :", res.sql)
finally:
    replica.close()
PY
```

Expected: `status` is `answered` (with a natural-language `answer` and a `sql`
that contains `for_bd = 'yes'`), or `clarify` (with a question). If `status` is
`error`, read `error` and report it — a model that writes invalid SQL three times
is a real (reportable) outcome, not a test to silence.

- [ ] **Step 2: Confirm the offline suite is still clean**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: green offline suite (`... deselected`) and `All checks passed!`.

- [ ] **Step 3: Record the result**

No code change. Report the printed `status` / `answer` / `sql` to the user as the
end-to-end confirmation. If a schema or prompt tweak proves necessary, raise it
before changing anything (the offline tests pin the contract).

---

## Self-Review

**Spec coverage:**
- `sql/secure.py` bridge (parse→validate→inject→limit, returns needs_explain) → Task 1. ✅
- `graph/state.py` AgentState + AgentResult + Deps → Task 2. ✅
- `graph/nodes.py` route/assemble_context/generate_sql/guard/execute/answer + routers → Task 3. ✅
- `graph/build.py` build_graph + run_agent, conditional edges for clarify + self-correction → Task 4. ✅
- Self-correction loop back to generate_sql, ≤3 via `max_sql_retries`, fatal on exhaustion/non-retryable → Tasks 3 (`_on_guard_error`) + 4 tests. ✅
- Stateless clarification terminal → Tasks 3 (`after_route`) + 4 test. ✅
- LLM {efficacy, clarify} routing → Task 3 `route_node`. ✅
- Dependency injection + offline fakes (no real LLM/DB) → Tasks 3 & 4. ✅
- `answer` handles zero rows → covered by `llm.agent_llm._rows_preview` (Plan A) + the answer prompt; the node passes the preview through. ✅
- Live end-to-end verification → Task 6. ✅
- Out of scope (FastAPI, observability, other domains) → not built. ✅

**Spec deviation (intentional):** `AgentState` is a `TypedDict` (LangGraph's idiom for partial-update nodes) rather than the spec's dataclass sketch; `AgentResult`/`Deps` remain frozen dataclasses. Behavior is unchanged.

**Placeholder scan:** No TBD/TODO; every code/test/command step is complete. Task 5 Step 3 gives the deterministic check ("green + deselected") rather than a brittle exact count. ✅

**Type consistency:** `secure_query(sql, layer, domain) -> SecuredQuery(sql, needs_explain, big_tables, limit)`; `Deps(llm, replica, layer, settings)`; node signature `node(state, deps) -> dict`; routers return node-name strings / `END`; `run_agent(question, *, llm, replica, layer, settings) -> AgentResult`; `ReadReplica.execute(sql, *, needs_explain, big_tables, limit)`; `QueryResult(columns, rows, rowcount, truncated, sql, elapsed_ms)`; `RouteResult(domain, clarification)` — all used identically across tasks and consistent with the shipped `sql/`, `db/`, and `llm/` code. ✅

**Note:** `langgraph` and `typing_extensions` (via pydantic/langgraph) are already available; no dependency changes. Task 1 adds a file under `sql/`, so the Stop hook will request an `sql-security-reviewer` pass that turn — expected.
