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
