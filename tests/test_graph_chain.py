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


def _run(llm, replica, question="how many models for BD?", resolve_gene=None):
    return run_agent(
        question,
        llm=llm,
        replica=replica,
        layer=LAYER,
        settings=SETTINGS,
        resolve_gene=resolve_gene,
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
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
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
                "WHERE gene_symbol = 'TP53' AND model_uuid = 'm1'"
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
