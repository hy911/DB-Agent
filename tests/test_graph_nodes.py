from __future__ import annotations

from langgraph.graph import END

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
    qr = QueryResult(
        columns=["n"], rows=[{"n": 1}], rowcount=1, truncated=False,
        sql="SELECT 1", elapsed_ms=1.0,
    )
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
    qr = QueryResult(
        columns=["n"], rows=[{"n": 1}], rowcount=1, truncated=False,
        sql="SELECT 1", elapsed_ms=1.0,
    )
    deps = _deps(llm=_LLM({"qwen-main": ["One row."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT 1"
    s["result"] = qr
    out = answer_node(s, deps)
    assert out["answer"] == "One row."
    assert out["status"] == "answered"
