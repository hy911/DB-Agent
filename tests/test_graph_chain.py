from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.db.gene_resolver import GeneMatch, GeneResolution
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


def _resolver(mapping):
    def resolve(replica, name):
        sym = mapping.get(name)
        if sym is None:
            return GeneResolution(name, "unknown", None, [])
        return GeneResolution(name, "resolved", sym, [GeneMatch(sym, "human", "symbol_exact", 1.0)])

    return resolve


def _run(llm, replica, question="how many models for BD?", resolve_gene=None, run_sandbox=None):
    return run_agent(
        question,
        llm=llm,
        replica=replica,
        layer=LAYER,
        settings=SETTINGS,
        resolve_gene=resolve_gene,
        run_sandbox=run_sandbox,
    )


def _qr():
    return QueryResult(
        columns=["drug_name"],
        rows=[{"drug_name": "X"}],
        rowcount=1,
        truncated=False,
        sql="SELECT drug_name",
        elapsed_ms=1.0,
    )


def test_happy_path():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    replica = _Replica([_qr()])
    res = _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "Found 1 drug."
    assert "for_bd" in res.sql.lower()  # permission injected into the SQL that ran


def test_self_correction_then_success():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT bad_col FROM model_efficacy_info",
                "SELECT drug_name FROM model_efficacy_info",
                "NONE",
                "NONE",
            ],
            "qwen-main": ["Recovered."],
        }
    )
    replica = _Replica([GuardError("bad_column", "no col", retryable=True), _qr()])
    res = _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "Recovered."
    assert replica.calls == 2


def test_retry_budget_exhausted():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"] * 3,
        }
    )
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
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        }
    )
    replica = _Replica([GuardError("big_table_scan", "seq scan", retryable=False)])
    res = _run(llm, replica)
    assert res.status == "error"
    assert replica.calls == 1


def test_expression_end_to_end_resolves_gene_and_injects():
    llm = _LLM(
        {
            "qwen-fast": ["expression", "p53"],  # route, then extract_genes
            "qwen-code": [
                "SELECT log2tpm FROM model_ccle_expression_data "
                "WHERE gene_symbol = 'TP53' AND model_uuid = 'm1'",
                "NONE",
                "NONE",
            ],
            "qwen-main": ["log2tpm for TP53 in m1 is 5.2."],
        }
    )
    qr = QueryResult(
        columns=["log2tpm"],
        rows=[{"log2tpm": 5.2}],
        rowcount=1,
        truncated=False,
        sql="SELECT log2tpm",
        elapsed_ms=1.0,
    )
    res = _run(
        llm,
        _Replica([qr]),
        question="p53 expression in m1?",
        resolve_gene=_resolver({"p53": "TP53"}),
    )
    assert res.status == "answered"
    assert res.answer == "log2tpm for TP53 in m1 is 5.2."
    assert "for_bd" not in (res.sql or "").lower()


def test_expression_unknown_gene_clarifies():
    llm = _LLM({"qwen-fast": ["expression", "notagene"]})
    res = _run(
        llm,
        _Replica([]),
        question="notagene expression?",
        resolve_gene=_resolver({}),  # resolves nothing -> unknown
    )
    assert res.status == "clarify"
    assert "notagene" in res.clarification


def test_mutation_end_to_end_resolves_gene():
    llm = _LLM(
        {
            "qwen-fast": ["mutation", "p53"],  # route, then extract_genes
            "qwen-code": [
                "SELECT model_uuid, mutation_id FROM model_ccle_mutation_data "
                "WHERE gene_symbol = 'TP53'",
                "NONE",
                "NONE",
            ],
            "qwen-main": ["3 models carry a TP53 mutation."],
        }
    )
    qr = QueryResult(
        columns=["model_uuid", "mutation_id"],
        rows=[{"model_uuid": "m1", "mutation_id": "TP53:R175H"}],
        rowcount=1,
        truncated=False,
        sql="SELECT model_uuid, mutation_id",
        elapsed_ms=1.0,
    )
    res = _run(
        llm,
        _Replica([qr]),
        question="which models have a p53 mutation?",
        resolve_gene=_resolver({"p53": "TP53"}),
    )
    assert res.status == "answered"
    assert res.answer == "3 models carry a TP53 mutation."
    assert "for_bd" not in (res.sql or "").lower()  # mutation: not access-controlled
    assert "model_ccle_mutation_data" in res.sql.lower()


def test_modeling_end_to_end_injects_permission():
    llm = _LLM(
        {
            "qwen-fast": ["modeling"],  # not gene-bearing -> no extract_genes call
            "qwen-code": ["SELECT model_no FROM modeling_attr_info", "NONE", "NONE"],
            "qwen-main": ["3 modeling groups are visible to BD."],
        }
    )
    qr = QueryResult(
        columns=["model_no"],
        rows=[{"model_no": "M1"}],
        rowcount=1,
        truncated=False,
        sql="SELECT model_no",
        elapsed_ms=1.0,
    )
    res = _run(llm, _Replica([qr]), question="how many modeling groups for BD?")
    assert res.status == "answered"
    assert res.answer == "3 modeling groups are visible to BD."
    assert "for_bd" in (res.sql or "").lower()  # permission injected into the SQL that ran


def test_analysis_end_to_end_runs_sandbox():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT drug_name, tgi_tv FROM model_efficacy_info",  # generate_sql
                "SELECT drug_name, avg(tgi_tv) AS m FROM result GROUP BY drug_name",  # analyze
                "NONE",  # stats: no test
            ],
            "qwen-main": ["Average TGI per drug computed."],
        }
    )
    raw = QueryResult(
        columns=["drug_name", "tgi_tv"],
        rows=[{"drug_name": "X", "tgi_tv": 80.0}, {"drug_name": "X", "tgi_tv": 90.0}],
        rowcount=2,
        truncated=False,
        sql="SELECT drug_name, tgi_tv",
        elapsed_ms=1.0,
    )
    captured = {}

    def fake_sandbox(columns, rows, sql):
        captured["sql"] = sql
        return QueryResult(
            columns=["drug_name", "m"],
            rows=[{"drug_name": "X", "m": 85.0}],
            rowcount=1,
            truncated=False,
            sql=sql,
            elapsed_ms=0.0,
        )

    res = _run(llm, _Replica([raw]), question="average TGI per drug?", run_sandbox=fake_sandbox)
    assert res.status == "answered"
    assert res.answer == "Average TGI per drug computed."
    assert "result" in captured["sql"].lower()  # sandbox ran the analysis SQL
    assert res.analysis_sql is not None and "avg" in res.analysis_sql.lower()


def test_examples_injected_end_to_end():
    from db_agent.examples.model import Example

    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    hit = Example("how many?", "SELECT count(*) FROM model_efficacy_info", "efficacy")
    res = run_agent(
        "list drugs for BD",
        llm=llm,
        replica=_Replica([_qr()]),
        layer=LAYER,
        settings=SETTINGS,
        retrieve_examples=lambda domain, q: [hit],
    )
    assert res.status == "answered"


def test_stats_end_to_end_runs_test():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT group_id, tgi_tv FROM model_efficacy_info",  # generate_sql
                "NONE",  # analyze: no reshape
                '{"function": "welch_t_test", "params": {"value": "tgi_tv", "group": "group_id"}}',
            ],
            "qwen-main": ["The two groups differ significantly (p<0.05)."],
        }
    )
    raw = QueryResult(
        columns=["group_id", "tgi_tv"],
        rows=[{"group_id": "A", "tgi_tv": v} for v in (10.0, 11.0, 12.0, 9.0)]
        + [{"group_id": "B", "tgi_tv": v} for v in (2.0, 3.0, 1.0, 4.0)],
        rowcount=8,
        truncated=False,
        sql="SELECT group_id, tgi_tv",
        elapsed_ms=1.0,
    )
    res = _run(llm, _Replica([raw]), question="is the TGI difference between groups significant?")
    assert res.status == "answered"
    assert res.answer == "The two groups differ significantly (p<0.05)."
    assert res.stat_request is not None and "welch_t_test" in res.stat_request
