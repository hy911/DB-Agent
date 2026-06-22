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


def test_initial_state_has_gene_fields():
    s = initial_state("q")
    assert s["extracted_genes"] == []
    assert s["resolved_genes"] == {}


def test_deps_default_resolve_gene_is_callable():
    from db_agent.config import Settings
    from db_agent.graph.state import Deps

    deps = Deps(llm=object(), replica=object(), layer=object(), settings=Settings(_env_file=None))
    assert callable(deps.resolve_gene)


def test_initial_state_has_analysis_fields():
    s = initial_state("q")
    assert s["analysis"] is None
    assert s["analysis_sql"] is None


def test_deps_default_run_sandbox_is_callable():
    from db_agent.config import Settings
    from db_agent.graph.state import Deps

    deps = Deps(llm=object(), replica=object(), layer=object(), settings=Settings(_env_file=None))
    assert callable(deps.run_sandbox)
