from __future__ import annotations

from langgraph.graph import END

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.db.gene_resolver import GeneMatch, GeneResolution
from db_agent.graph.nodes import (
    after_execute,
    after_guard,
    after_resolve,
    after_route,
    analyze_node,
    answer_node,
    assemble_context_node,
    execute_node,
    extract_genes_node,
    generate_sql_node,
    guard_node,
    resolve_genes_node,
    route_node,
    stats_node,
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


def _deps(llm=None, replica=None, resolve_gene=None):
    kwargs = dict(llm=llm, replica=replica, layer=LAYER, settings=SETTINGS)
    if resolve_gene is not None:
        kwargs["resolve_gene"] = resolve_gene
    return Deps(**kwargs)


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
    deps = _deps()
    s = initial_state("q")
    assert after_route(s, deps) == "assemble_context"
    s["status"] = "clarify"
    assert after_route(s, deps) == END


def test_extract_genes_node():
    deps = _deps(llm=_LLM({"qwen-fast": ["p53, EGFR"]}))
    out = extract_genes_node(initial_state("p53 and EGFR?"), deps)
    assert out["extracted_genes"] == ["p53", "EGFR"]


def test_resolve_genes_node_all_resolved_injects_map():
    def fake_resolver(replica, name):
        return GeneResolution(
            name, "resolved", "TP53", [GeneMatch("TP53", "human", "symbol_exact", 1.0)]
        )

    deps = _deps(resolve_gene=fake_resolver)
    s = initial_state("q")
    s["extracted_genes"] = ["p53"]
    out = resolve_genes_node(s, deps)
    assert out["resolved_genes"] == {"p53": "TP53"}
    assert "status" not in out  # continues, no clarify


def test_resolve_genes_node_ambiguous_clarifies():
    def fake_resolver(replica, name):
        return GeneResolution(
            name,
            "ambiguous",
            None,
            [
                GeneMatch("TP53", "human", "symbol_exact", 1.0),
                GeneMatch("Trp53", "mouse", "symbol_exact", 1.0),
            ],
        )

    deps = _deps(resolve_gene=fake_resolver)
    s = initial_state("q")
    s["extracted_genes"] = ["p53"]
    out = resolve_genes_node(s, deps)
    assert out["status"] == "clarify"
    assert "TP53" in out["clarification"] and "Trp53" in out["clarification"]


def test_after_resolve_branches():
    s = initial_state("q")
    assert after_resolve(s) == "assemble_context"
    s["status"] = "clarify"
    assert after_resolve(s) == END


def test_after_route_gene_bearing_goes_to_extract():
    s = initial_state("q")
    s["domain"] = "expression"
    assert after_route(s, _deps()) == "extract_genes"
    s2 = initial_state("q")
    s2["domain"] = "efficacy"
    assert after_route(s2, _deps()) == "assemble_context"


def test_assemble_context_injects_resolved_genes():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "expression"
    s["resolved_genes"] = {"p53": "TP53"}
    ctx = assemble_context_node(s, deps)["context"]
    assert "p53 -> TP53" in ctx or "p53 → TP53" in ctx


def test_assemble_context_efficacy_has_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "efficacy"
    ctx = assemble_context_node(s, deps)["context"]
    assert "model_efficacy_info" in ctx
    assert "药物名称" in ctx  # column description rendered
    assert "for_bd" in ctx
    assert "do not" in ctx.lower()  # permission note present (access-controlled)


def test_assemble_context_expression_omits_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "expression"
    ctx = assemble_context_node(s, deps)["context"]
    assert "model_ccle_expression_data" in ctx
    assert "do not" not in ctx.lower()  # expression is not access-controlled


def test_route_expression_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["expression"]}))
    out = route_node(initial_state("TP53 expression?"), deps)
    assert out["domain"] == "expression"


def test_generate_sql_increments_attempts():
    deps = _deps(llm=_LLM({"qwen-code": ["SELECT 1"]}))
    s = initial_state("q")
    s["context"] = "ctx"
    out = generate_sql_node(s, deps)
    assert out["sql"] == "SELECT 1"
    assert out["attempts"] == 1


def test_guard_ok_efficacy_injects_permission():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "efficacy"
    s["sql"] = "SELECT drug_name FROM model_efficacy_info"
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "ok"
    assert "for_bd" in out["secured_sql"].lower()


def test_guard_ok_expression_no_permission():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "expression"
    s["sql"] = (
        "SELECT log2tpm FROM model_ccle_expression_data "
        "WHERE gene_symbol = 'TP53' AND model_uuid = 'm1'"
    )
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "ok"
    assert "for_bd" not in out["secured_sql"].lower()


def test_guard_retryable_under_budget():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "efficacy"
    s["sql"] = "SELECT (("  # parse error -> retryable GuardError
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "retry"
    assert out["last_error"]


def test_guard_retryable_at_budget_is_fatal():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "efficacy"
    s["sql"] = "SELECT (("
    s["attempts"] = 3  # == max_sql_retries
    out = guard_node(s, deps)
    assert out["outcome"] == "fatal"
    assert out["status"] == "error"


def test_execute_ok_sets_result():
    qr = QueryResult(
        columns=["n"],
        rows=[{"n": 1}],
        rowcount=1,
        truncated=False,
        sql="SELECT 1",
        elapsed_ms=1.0,
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
    assert after_execute(s) == "analyze"
    s["outcome"] = "retry"
    assert after_guard(s) == "generate_sql"
    assert after_execute(s) == "generate_sql"
    s["outcome"] = "fatal"
    assert after_guard(s) == END
    assert after_execute(s) == END


def _qr_rows():
    return QueryResult(
        columns=["group_id", "tv"],
        rows=[{"group_id": "A", "tv": 1.0}, {"group_id": "B", "tv": 2.0}],
        rowcount=2,
        truncated=False,
        sql="SELECT group_id, tv",
        elapsed_ms=1.0,
    )


def test_analyze_node_runs_sandbox_when_sql_returned():
    analysis = QueryResult(
        columns=["m"],
        rows=[{"m": 1.5}],
        rowcount=1,
        truncated=False,
        sql="SELECT avg(tv) AS m FROM result",
        elapsed_ms=0.0,
    )

    def fake_sandbox(columns, rows, sql):
        assert columns == ["group_id", "tv"]
        return analysis

    deps = _deps(llm=_LLM({"qwen-code": ["SELECT avg(tv) AS m FROM result"]}))
    object.__setattr__(deps, "run_sandbox", fake_sandbox)
    s = initial_state("avg tv?")
    s["result"] = _qr_rows()
    out = analyze_node(s, deps)
    assert out["analysis"] is analysis
    assert "result" in out["analysis_sql"].lower()


def test_analyze_node_none_passes_through():
    deps = _deps(llm=_LLM({"qwen-code": ["NONE"]}))
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert analyze_node(s, deps) == {}


def test_analyze_node_empty_result_skips_llm():
    empty = QueryResult(
        columns=["x"], rows=[], rowcount=0, truncated=False, sql="s", elapsed_ms=0.0
    )
    deps = _deps(llm=_LLM({}))  # no scripted response -> must not be called
    s = initial_state("q")
    s["result"] = empty
    assert analyze_node(s, deps) == {}


def test_analyze_node_guard_error_degrades():
    def boom(columns, rows, sql):
        raise GuardError("duckdb_error", "bad", retryable=False)

    deps = _deps(llm=_LLM({"qwen-code": ["SELECT * FROM result"]}))
    object.__setattr__(deps, "run_sandbox", boom)
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert analyze_node(s, deps) == {}


def test_answer_node_uses_analysis_when_present():
    analysis = QueryResult(
        columns=["m"],
        rows=[{"m": 1.5}],
        rowcount=1,
        truncated=False,
        sql="SELECT avg(tv) AS m FROM result",
        elapsed_ms=0.0,
    )
    deps = _deps(llm=_LLM({"qwen-main": ["Average is 1.5."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT group_id, tv FROM t"
    s["result"] = _qr_rows()
    s["analysis"] = analysis
    s["analysis_sql"] = "SELECT avg(tv) AS m FROM result"
    out = answer_node(s, deps)
    assert out["answer"] == "Average is 1.5."
    assert out["status"] == "answered"


def test_answer_node_sets_answer():
    qr = QueryResult(
        columns=["n"],
        rows=[{"n": 1}],
        rowcount=1,
        truncated=False,
        sql="SELECT 1",
        elapsed_ms=1.0,
    )
    deps = _deps(llm=_LLM({"qwen-main": ["One row."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT 1"
    s["result"] = qr
    out = answer_node(s, deps)
    assert out["answer"] == "One row."
    assert out["status"] == "answered"


def test_route_mutation_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["mutation"]}))
    out = route_node(initial_state("which models have a TP53 mutation?"), deps)
    assert out["domain"] == "mutation"


def test_after_route_mutation_goes_to_extract():
    s = initial_state("q")
    s["domain"] = "mutation"
    assert after_route(s, _deps()) == "extract_genes"


def test_assemble_context_mutation_omits_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "mutation"
    s["resolved_genes"] = {"p53": "TP53"}
    ctx = assemble_context_node(s, deps)["context"]
    assert "model_ccle_mutation_data" in ctx
    assert "oncokb" in ctx
    assert "do not" not in ctx.lower()  # not access-controlled
    assert "p53 -> TP53" in ctx or "p53 → TP53" in ctx


def test_oncokb_only_fed_for_mutation_not_other_domains():
    # oncokb is domain=mutation, so it must not leak into efficacy/expression context.
    deps = _deps()
    for domain in ("efficacy", "expression"):
        s = initial_state("q")
        s["domain"] = domain
        ctx = assemble_context_node(s, deps)["context"]
        assert "oncokb" not in ctx


def test_route_modeling_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["modeling"]}))
    out = route_node(initial_state("modeling tumor volume for model X?"), deps)
    assert out["domain"] == "modeling"


def test_after_route_modeling_skips_gene_nodes():
    # modeling is not gene-bearing, so it goes straight to assemble_context.
    s = initial_state("q")
    s["domain"] = "modeling"
    assert after_route(s, _deps()) == "assemble_context"


def test_assemble_context_modeling_has_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "modeling"
    ctx = assemble_context_node(s, deps)["context"]
    assert "modeling_attr_info" in ctx
    assert "modeling_tumor_volume_growth_curve_data" in ctx
    assert "for_bd" in ctx
    assert "do not" in ctx.lower()  # permission note present (access-controlled)


def test_stats_node_runs_when_request_returned():
    from db_agent.sandbox.stats.spec import StatResult

    stat = StatResult(test="welch_t_test", stats={"p_value": 0.01}, groups=[], caveats=[])

    def fake_run_stat(columns, rows, req):
        assert columns == ["group_id", "tv"]
        assert "welch_t_test" in req
        return stat

    deps = _deps(
        llm=_LLM(
            {
                "qwen-code": [
                    '{"function": "welch_t_test", "params": {"value": "tv", "group": "group_id"}}'
                ]
            }
        )
    )
    object.__setattr__(deps, "run_stat", fake_run_stat)
    s = initial_state("is tv different by group?")
    s["result"] = _qr_rows()
    out = stats_node(s, deps)
    assert out["stat_result"] is stat
    assert "welch_t_test" in out["stat_request"]


def test_stats_node_prefers_analysis_table():
    from db_agent.sandbox.stats.spec import StatResult

    analysis = QueryResult(
        columns=["grp", "val"],
        rows=[{"grp": "A", "val": 1.0}],
        rowcount=1,
        truncated=False,
        sql="SELECT grp, val FROM result",
        elapsed_ms=0.0,
    )
    seen = {}

    def fake_run_stat(columns, rows, req):
        seen["columns"] = columns
        return StatResult(test="t", stats={}, groups=[], caveats=[])

    deps = _deps(llm=_LLM({"qwen-code": ['{"function": "welch_t_test", "params": {}}']}))
    object.__setattr__(deps, "run_stat", fake_run_stat)
    s = initial_state("q")
    s["result"] = _qr_rows()
    s["analysis"] = analysis
    stats_node(s, deps)
    assert seen["columns"] == ["grp", "val"]  # used the analysis table, not raw result


def test_stats_node_none_passes_through():
    deps = _deps(llm=_LLM({"qwen-code": ["NONE"]}))
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert stats_node(s, deps) == {}


def test_stats_node_empty_table_skips_llm():
    empty = QueryResult(
        columns=["x"], rows=[], rowcount=0, truncated=False, sql="s", elapsed_ms=0.0
    )
    deps = _deps(llm=_LLM({}))  # no scripted response -> must not be called
    s = initial_state("q")
    s["result"] = empty
    assert stats_node(s, deps) == {}


def test_stats_node_guard_error_degrades():
    def boom(columns, rows, req):
        raise GuardError("stat_unknown_function", "nope", retryable=False)

    deps = _deps(llm=_LLM({"qwen-code": ['{"function": "nope"}']}))
    object.__setattr__(deps, "run_stat", boom)
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert stats_node(s, deps) == {}


def test_answer_node_uses_stat_result_when_present():
    from db_agent.sandbox.stats.spec import StatResult

    stat = StatResult(
        test="welch_t_test",
        stats={"p_value": 0.01},
        groups=[{"label": "A", "n": 4, "mean": 1.0}],
        caveats=["Welch's t-test."],
    )
    deps = _deps(llm=_LLM({"qwen-main": ["Significant difference (p=0.01)."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT group_id, tv FROM t"
    s["analysis_sql"] = "SELECT group_id, tv FROM result"
    s["result"] = _qr_rows()
    s["stat_result"] = stat
    out = answer_node(s, deps)
    assert out["answer"] == "Significant difference (p=0.01)."
    assert out["status"] == "answered"
