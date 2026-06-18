"""Graph nodes and routers.

Each node is `node(state, deps) -> dict-of-updates`; `build_graph` binds `deps`
with functools.partial so LangGraph calls them with just `state`. Guard/execute
nodes catch GuardError and write a transient `outcome` the routers dispatch on.
"""

from __future__ import annotations

from langgraph.graph import END

from db_agent.graph.state import AgentState, Deps
from db_agent.llm import answer as llm_answer
from db_agent.llm import extract_genes as llm_extract_genes
from db_agent.llm import generate_sql as llm_generate_sql
from db_agent.llm import route as llm_route
from db_agent.sql.errors import GuardError
from db_agent.sql.secure import secure_query


def route_node(state: AgentState, deps: Deps) -> dict:
    res = llm_route(deps.llm, deps.settings, state["question"], deps.layer.routable_domains())
    if res.domain is not None:
        return {"domain": res.domain}
    return {"clarification": res.clarification, "status": "clarify"}


def after_route(state: AgentState, deps: Deps) -> str:
    if state["status"] == "clarify":
        return END
    if deps.layer.is_gene_bearing(state["domain"]):
        return "extract_genes"
    return "assemble_context"


def extract_genes_node(state: AgentState, deps: Deps) -> dict:
    return {"extracted_genes": llm_extract_genes(deps.llm, deps.settings, state["question"])}


def resolve_genes_node(state: AgentState, deps: Deps) -> dict:
    resolved: dict[str, str] = {}
    for name in state["extracted_genes"]:
        res = deps.resolve_gene(deps.replica, name)
        if res.status == "resolved":
            resolved[name] = res.symbol
        elif res.status == "ambiguous":
            cands = ", ".join(sorted({m.symbol for m in res.candidates})[:5])
            return {
                "clarification": f"The gene '{name}' is ambiguous — did you mean one of: {cands}?",
                "status": "clarify",
            }
        else:  # unknown
            return {
                "clarification": (
                    f"I couldn't find a gene matching '{name}'. Please check the name."
                ),
                "status": "clarify",
            }
    return {"resolved_genes": resolved}


def after_resolve(state: AgentState) -> str:
    return END if state["status"] == "clarify" else "assemble_context"


def assemble_context_node(state: AgentState, deps: Deps) -> dict:
    return {"context": _render_context(deps, state["domain"], state["resolved_genes"])}


def generate_sql_node(state: AgentState, deps: Deps) -> dict:
    sql = llm_generate_sql(
        deps.llm, deps.settings, state["question"], state["context"], state["last_error"]
    )
    return {"sql": sql, "attempts": state["attempts"] + 1}


def guard_node(state: AgentState, deps: Deps) -> dict:
    try:
        secured = secure_query(state["sql"], deps.layer, state["domain"])
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


def _render_context(deps: Deps, domain: str, resolved_genes: dict[str, str]) -> str:
    """Render the domain's schema for sql-gen: columns with descriptions, plus —
    only for an access-controlled domain — a note that the permission columns are
    filtered automatically (so the model never filters or guesses them)."""
    tables = deps.layer.tables_in_domain(domain) + deps.layer.reference_tables()
    lines = []
    for t in tables:
        cols = ", ".join(f"{c.name} ({c.desc})" if c.desc else c.name for c in t.columns.values())
        header = f"{t.name}: {cols}" if t.desc is None else f"{t.name} — {t.desc}: {cols}"
        lines.append(header)
    dom = deps.layer.get_domain(domain)
    if dom is not None and dom.access_controlled:
        perm = ", ".join(deps.layer.access_control.fields)
        lines.append(
            f"\nRow-level permissions are already enforced automatically on these "
            f"columns: {perm}. Do NOT add WHERE conditions on them — the system "
            f"applies the correct filter for you."
        )
    if resolved_genes:
        mapping = ", ".join(f"{name} -> {symbol}" for name, symbol in resolved_genes.items())
        lines.append(f"\nResolved gene names (use these canonical symbols): {mapping}")
    return "\n".join(lines)
