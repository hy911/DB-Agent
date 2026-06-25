"""Graph nodes and routers.

Each node is `node(state, deps) -> dict-of-updates`; `build_graph` binds `deps`
with functools.partial so LangGraph calls them with just `state`. Guard/execute
nodes catch GuardError and write a transient `outcome` the routers dispatch on.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.config import get_stream_writer
from langgraph.graph import END

from db_agent.examples.skeleton import skeletonize
from db_agent.graph.state import AgentState, Deps
from db_agent.llm import analyze_sql as llm_analyze_sql
from db_agent.llm import answer_stat_stream as llm_answer_stat_stream
from db_agent.llm import answer_stream as llm_answer_stream
from db_agent.llm import extract_genes as llm_extract_genes
from db_agent.llm import generate_sql as llm_generate_sql
from db_agent.llm import request_stat as llm_request_stat
from db_agent.llm import route as llm_route
from db_agent.llm.agent_llm import _rows_preview
from db_agent.sandbox.stats import catalog_text
from db_agent.sql.critic import diagnose_empty_result
from db_agent.sql.errors import GuardError
from db_agent.sql.secure import secure_query

logger = logging.getLogger("db_agent.graph")

# Shown when the SQL ran fine but the final NL-answer LLM call failed (e.g. gateway
# 504). The data + SQL are already on the result, so degrade instead of 502-ing.
_ANSWER_FALLBACK = "（自动摘要生成超时，已返回查询到的数据与所用 SQL，请直接查看下方结果。）"


async def route_node(state: AgentState, deps: Deps) -> dict:
    res = await llm_route(deps.llm, deps.settings, state["question"], deps.layer.routable_domains())
    if res.domains:
        # Legacy single-domain graph: take the first match. The multi-domain
        # fan-out is orchestrated in build.run_agent, not through this node.
        return {"domain": res.domains[0]}
    return {"clarification": res.clarification, "status": "clarify"}


def after_route(state: AgentState, deps: Deps) -> str:
    if state["status"] == "clarify":
        return END
    return domain_entry(state, deps)


def domain_entry(state: AgentState, deps: Deps) -> str:
    """Entry router for a per-domain subgraph (domain already set): gene-bearing
    domains resolve genes first, others go straight to context assembly."""
    return "extract_genes" if deps.layer.is_gene_bearing(state["domain"]) else "assemble_context"


def after_execute_to_critic(state: AgentState) -> str:
    """A clean execute goes to the critic (data-aware review); error/fatal as before."""
    return {"ok": "critic", "retry": "generate_sql", "fatal": END}[state["outcome"]]


def critic_node(state: AgentState, deps: Deps) -> dict:
    """Data-aware self-correction: a SELECT that ran clean but returned 0 rows may
    be a fixable mistake (a closed-vocabulary filter value outside its allowed
    set). Deterministically diagnose ONCE; on a high-precision signal, feed a
    revision hint back to generate_sql. No signal → accept the empty result as
    real (so a legitimately-empty query, e.g. a permission-filtered drug, never
    loops)."""
    result = state.get("result")
    if (
        not deps.settings.critic_enabled
        or result is None
        or result.rowcount != 0
        or state.get("critic_used")
        or state["attempts"] >= deps.settings.max_sql_retries
    ):
        return {"outcome": "ok"}
    sql_text = state.get("secured_sql") or state.get("sql") or ""
    hint = diagnose_empty_result(sql_text, deps.layer, state["domain"])
    if hint is None and deps.settings.value_align_enabled:
        # Open-vocab value alignment (drug_name/model_name): the nearest real value
        # via pg_trgm. Returns None when the filter already matches a stored value,
        # so a legitimately-empty (e.g. permission-filtered) query is accepted.
        hint = deps.align_values(deps.replica, deps.layer, sql_text, state["domain"])
    if hint is None:
        # The optional LLM critic (settings.critic_llm_enabled) would go here; it
        # stays off by default, so with no deterministic signal we accept the result.
        return {"outcome": "ok"}
    return {"outcome": "retry", "last_error": hint, "critic_used": True}


def after_critic(state: AgentState) -> str:
    """Full pipeline: accepted result proceeds to analyze; a revision re-generates."""
    return {"ok": "analyze", "retry": "generate_sql"}[state["outcome"]]


def after_critic_data_only(state: AgentState) -> str:
    """Data-only fan-out subgraph: accepted result ends; a revision re-generates."""
    return {"ok": END, "retry": "generate_sql"}[state["outcome"]]


async def extract_genes_node(state: AgentState, deps: Deps) -> dict:
    genes = await llm_extract_genes(deps.llm, deps.settings, state["question"])
    return {"extracted_genes": genes}


def resolve_genes_node(state: AgentState, deps: Deps) -> dict:
    resolved: dict[str, str] = {}
    unknown: list[str] = []
    for name in state["extracted_genes"]:
        res = deps.resolve_gene(deps.replica, name)
        if res.status == "resolved":
            resolved[name] = res.symbol
        elif res.status == "ambiguous":
            # A genuine gene typo fuzzy-matching several real genes — worth asking.
            cands = ", ".join(sorted({m.symbol for m in res.candidates})[:5])
            return {
                "clarification": f"The gene '{name}' is ambiguous — did you mean one of: {cands}?",
                "status": "clarify",
            }
        else:  # unknown
            unknown.append(name)
    # A model/cell-line name mis-extracted as a gene (e.g. 'MDA-MB-468') resolves to
    # nothing. Don't derail a query that named a real gene too — drop the stray term
    # and let SQL use it as an ordinary filter. Only clarify when *no* gene resolved.
    if unknown and not resolved:
        names = ", ".join(f"'{n}'" for n in unknown)
        return {
            "clarification": f"I couldn't find a gene matching {names}. Please check the name.",
            "status": "clarify",
        }
    return {"resolved_genes": resolved}


def after_resolve(state: AgentState) -> str:
    return END if state["status"] == "clarify" else "assemble_context"


def assemble_context_node(state: AgentState, deps: Deps) -> dict:
    return {"context": _render_context(deps, state["domain"], state["resolved_genes"])}


async def retrieve_examples_node(state: AgentState, deps: Deps) -> dict:
    draft_skeleton: str | None = None
    if deps.settings.example_structural:
        # DAIL-SQL second channel: a cheap draft SQL (no examples) → de-parameterized
        # skeleton → structure-aware recall. Fail-soft: degrade to question-only.
        try:
            draft = await llm_generate_sql(
                deps.llm, deps.settings, state["question"], state["context"]
            )
            draft_skeleton = skeletonize(draft)
        except Exception:
            draft_skeleton = None
    return {"examples": deps.retrieve_examples(state["domain"], state["question"], draft_skeleton)}


async def generate_sql_node(state: AgentState, deps: Deps) -> dict:
    sql = await llm_generate_sql(
        deps.llm,
        deps.settings,
        state["question"],
        state["context"],
        state["last_error"],
        state["examples"],
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
    return {"ok": "analyze", "retry": "generate_sql", "fatal": END}[state["outcome"]]


async def analyze_node(state: AgentState, deps: Deps) -> dict:
    result = state.get("result")
    if result is None or result.rowcount == 0:
        return {}
    sql = await llm_analyze_sql(deps.llm, deps.settings, state["question"], result)
    if not sql or sql.strip().upper() == "NONE":
        return {}
    try:
        analysis = await asyncio.to_thread(deps.run_sandbox, result.columns, result.rows, sql)
    except GuardError:
        return {}  # fail-soft: analysis is additive; degrade to the raw-result answer
    return {"analysis": analysis, "analysis_sql": sql}


async def stats_node(state: AgentState, deps: Deps) -> dict:
    table = state.get("analysis")
    if table is None:
        table = state.get("result")
    if table is None or table.rowcount == 0:
        return {}
    req = await llm_request_stat(
        deps.llm,
        deps.settings,
        state["question"],
        table.columns,
        _rows_preview(table),
        catalog_text(),
    )
    if not req or req.strip().upper() == "NONE":
        return {}
    try:
        stat = await asyncio.to_thread(deps.run_stat, table.columns, table.rows, req)
    except GuardError:
        return {}  # fail-soft: stats are additive; degrade to the descriptive answer
    return {"stat_result": stat, "stat_request": req}


async def answer_node(state: AgentState, deps: Deps) -> dict:
    # The SQL has already run and the result/SQL are on the state — they are returned
    # regardless of this step. So if the final NL-answer LLM call fails (commonly a
    # gateway 504 under load), degrade to a fallback note instead of failing the whole
    # query with a 502 and losing the data the user already paid to compute.
    #
    # Token pieces are pushed to the LangGraph stream writer for live display. Under
    # `invoke` (the non-streaming run_agent) the writer drops them; under
    # `astream(stream_mode="custom")` (run_agent_stream) they reach the client.
    # Outside a graph run (direct unit-test call) get_stream_writer raises — degrade
    # to a no-op so the node stays callable in isolation.
    try:
        writer = get_stream_writer()
    except RuntimeError:
        writer = lambda _piece: None  # noqa: E731
    try:
        stat = state.get("stat_result")
        if stat is not None:
            gen = llm_answer_stat_stream(
                deps.llm,
                deps.settings,
                state["question"],
                state["secured_sql"],
                state.get("analysis_sql"),
                stat,
            )
        elif state.get("analysis") is not None:
            gen = llm_answer_stream(
                deps.llm, deps.settings, state["question"], state["analysis_sql"], state["analysis"]
            )
        else:
            gen = llm_answer_stream(
                deps.llm, deps.settings, state["question"], state["secured_sql"], state["result"]
            )
        parts: list[str] = []
        async for piece in gen:
            parts.append(piece)
            writer({"token": piece})
        return {"answer": "".join(parts).strip(), "status": "answered"}
    except Exception:
        logger.exception("answer generation failed; degrading to data+SQL only")
        return {"answer": _ANSWER_FALLBACK, "status": "answered"}


def _on_guard_error(state: AgentState, deps: Deps, e: GuardError) -> dict:
    msg = f"{e.category}: {e.message}"
    if not e.retryable or state["attempts"] >= deps.settings.max_sql_retries:
        return {"outcome": "fatal", "status": "error", "error": msg}
    return {"outcome": "retry", "last_error": msg}


def _render_column(c) -> str:  # noqa: ANN001 - semantic.model.Column, kept loose to avoid import cycle churn
    """One column line for sql-gen context: name (desc) + value hints when known.

    Value hints turn 0-row guesses into hits: a closed `values` enum (e.g.
    is_cancer_model: cancer|no_cancer), an open `examples` vocabulary (e.g. the
    cancer_type histology names), and the stored-value `language` so the model
    maps a Chinese question term to the English value actually stored.
    """
    base = f"{c.name} ({c.desc})" if c.desc else c.name
    hints: list[str] = []
    if c.values:
        hints.append("one of: " + "|".join(c.values))
    if c.examples:
        hints.append("e.g. " + ", ".join(c.examples))
    if c.language:
        hints.append(f"stored in {c.language}")
    return f"{base} [{'; '.join(hints)}]" if hints else base


def _render_context(deps: Deps, domain: str, resolved_genes: dict[str, str]) -> str:
    """Render the domain's schema for sql-gen: columns with descriptions, plus —
    only for an access-controlled domain — a note that the permission columns are
    filtered automatically (so the model never filters or guesses them)."""
    # Spine (model_desc_info) is always included so model attributes are joinable
    # in every domain; dedup by name since the `model` domain already lists it.
    candidates = (
        deps.layer.tables_in_domain(domain)
        + deps.layer.spine_tables()
        + deps.layer.reference_tables()
    )
    seen: set[str] = set()
    tables = [t for t in candidates if not (t.name in seen or seen.add(t.name))]
    lines = []
    for t in tables:
        cols = ", ".join(_render_column(c) for c in t.columns.values())
        header = f"{t.name}: {cols}" if t.desc is None else f"{t.name} — {t.desc}: {cols}"
        lines.append(header)
    edges = deps.layer.join_edges(domain)
    if edges:
        joins = "\n".join(f"  - {e}" for e in edges)
        lines.append(
            f"\nJoin keys (use these exact equalities to JOIN, no real FKs exist):\n{joins}"
        )
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
        lines.append(
            f"\nResolved gene names (use these canonical symbols): {mapping}. Filter the "
            f"omics table directly, e.g. gene_symbol = '{next(iter(resolved_genes.values()))}'"
            f' — do NOT JOIN gene_info (its column is "Symbol" with a capital S and a bare '
            f"g.Symbol errors)."
        )
    return "\n".join(lines)
