from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.db.gene_resolver import GeneMatch, GeneResolution
from db_agent.graph.build import run_agent, run_agent_stream
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


class _LLM:
    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}

    async def complete(self, model, messages):
        return self.by_model[model].pop(0)

    async def complete_stream(self, model, messages):
        yield self.by_model[model].pop(0)


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

    def fetch(self, sql, params=()):
        # Used by the critic's value aligner (pg_trgm). Default: no near match.
        return getattr(self, "_fetch_rows", [])


def _resolver(mapping):
    def resolve(replica, name):
        sym = mapping.get(name)
        if sym is None:
            return GeneResolution(name, "unknown", None, [])
        return GeneResolution(name, "resolved", sym, [GeneMatch(sym, "human", "symbol_exact", 1.0)])

    return resolve


async def _run(
    llm, replica, question="how many models for BD?", resolve_gene=None, run_sandbox=None
):
    return await run_agent(
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


async def test_happy_path():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    replica = _Replica([_qr()])
    res = await _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "Found 1 drug."
    assert "for_bd" in res.sql.lower()  # permission injected into the SQL that ran


async def test_self_correction_then_success():
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
    res = await _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "Recovered."
    assert replica.calls == 2


def _qr_empty(cols=("model_name",)):
    return QueryResult(
        columns=list(cols), rows=[], rowcount=0, truncated=False, sql="SELECT ...", elapsed_ms=1.0
    )


async def test_critic_revises_empty_enum_mismatch():
    # SQL runs clean but returns 0 rows because is_cancer_model='T' is outside the
    # closed value set {cancer, no_cancer}; the critic diagnoses it and forces a
    # regenerate, the second SQL returns rows.
    llm = _LLM(
        {
            "qwen-fast": ["model"],
            "qwen-code": [
                "SELECT model_name FROM model_desc_info WHERE is_cancer_model = 'T'",
                "SELECT model_name FROM model_desc_info WHERE is_cancer_model = 'cancer'",
                "NONE",  # analyze (second result is non-empty)
                "NONE",  # stats
            ],
            "qwen-main": ["Revised answer."],
        }
    )
    replica = _Replica([_qr_empty(), _qr()])
    res = await _run(llm, replica, question="哪些是癌症模型")
    assert res.status == "answered"
    assert res.answer == "Revised answer."
    assert replica.calls == 2  # the critic forced a second execution


async def test_value_alignment_revises_empty_then_succeeds():
    # 0 rows on a drug_name typo; the critic's value aligner finds the real stored
    # value via pg_trgm (faked) and forces a regenerate that returns rows.
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT drug_name FROM model_efficacy_info WHERE drug_name ILIKE '%吉非ti尼%'",
                "SELECT drug_name FROM model_efficacy_info WHERE drug_name ILIKE '%吉非替尼%'",
                "NONE",  # analyze
                "NONE",  # stats
            ],
            "qwen-main": ["Found it after alignment."],
        }
    )
    replica = _Replica([_qr_empty(cols=("drug_name",)), _qr()])
    replica._fetch_rows = [{"v": "吉非替尼", "s": 0.55}]  # nearest real value
    res = await _run(llm, replica, question="哪些模型用了吉非ti尼")
    assert res.status == "answered"
    assert res.answer == "Found it after alignment."
    assert replica.calls == 2  # aligner forced a second execution


async def test_critic_accepts_genuinely_empty():
    # 0 rows with no closed-vocabulary signal (an ILIKE on the open drug_name) is a
    # real empty result — the critic must accept it and not loop.
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT drug_name FROM model_efficacy_info WHERE drug_name ILIKE '%zzz%'"
            ],
            "qwen-main": ["No matching data."],
        }
    )
    replica = _Replica([_qr_empty(cols=("drug_name",))])
    res = await _run(llm, replica)
    assert res.status == "answered"
    assert res.answer == "No matching data."
    assert replica.calls == 1  # critic accepted; no second execution


async def test_retry_budget_exhausted():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"] * 3,
        }
    )
    replica = _Replica([GuardError("bad_column", "no col", retryable=True)] * 3)
    res = await _run(llm, replica)
    assert res.status == "error"
    assert replica.calls == 3


async def test_clarification_short_circuits():
    llm = _LLM({"qwen-fast": ["clarify: which drug do you mean?"]})
    replica = _Replica([])
    res = await _run(llm, replica)
    assert res.status == "clarify"
    assert "which drug" in res.clarification
    assert replica.calls == 0  # DB never touched


async def test_fatal_guarderror_no_retry():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info"],
        }
    )
    replica = _Replica([GuardError("big_table_scan", "seq scan", retryable=False)])
    res = await _run(llm, replica)
    assert res.status == "error"
    assert replica.calls == 1


async def test_expression_end_to_end_resolves_gene_and_injects():
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
    res = await _run(
        llm,
        _Replica([qr]),
        question="p53 expression in m1?",
        resolve_gene=_resolver({"p53": "TP53"}),
    )
    assert res.status == "answered"
    assert res.answer == "log2tpm for TP53 in m1 is 5.2."
    assert "for_bd" not in (res.sql or "").lower()


async def test_expression_unknown_gene_clarifies():
    llm = _LLM({"qwen-fast": ["expression", "notagene"]})
    res = await _run(
        llm,
        _Replica([]),
        question="notagene expression?",
        resolve_gene=_resolver({}),  # resolves nothing -> unknown
    )
    assert res.status == "clarify"
    assert "notagene" in res.clarification


async def test_mutation_end_to_end_resolves_gene():
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
    res = await _run(
        llm,
        _Replica([qr]),
        question="which models have a p53 mutation?",
        resolve_gene=_resolver({"p53": "TP53"}),
    )
    assert res.status == "answered"
    assert res.answer == "3 models carry a TP53 mutation."
    assert "for_bd" not in (res.sql or "").lower()  # mutation: not access-controlled
    assert "model_ccle_mutation_data" in res.sql.lower()


async def test_modeling_end_to_end_injects_permission():
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
    res = await _run(llm, _Replica([qr]), question="how many modeling groups for BD?")
    assert res.status == "answered"
    assert res.answer == "3 modeling groups are visible to BD."
    assert "for_bd" in (res.sql or "").lower()  # permission injected into the SQL that ran


async def test_analysis_end_to_end_runs_sandbox():
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

    res = await _run(
        llm, _Replica([raw]), question="average TGI per drug?", run_sandbox=fake_sandbox
    )
    assert res.status == "answered"
    assert res.answer == "Average TGI per drug computed."
    assert "result" in captured["sql"].lower()  # sandbox ran the analysis SQL
    assert res.analysis_sql is not None and "avg" in res.analysis_sql.lower()


async def test_examples_injected_end_to_end():
    from db_agent.examples.model import Example

    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    hit = Example("how many?", "SELECT count(*) FROM model_efficacy_info", "efficacy")
    res = await run_agent(
        "list drugs for BD",
        llm=llm,
        replica=_Replica([_qr()]),
        layer=LAYER,
        settings=SETTINGS,
        retrieve_examples=lambda domain, q, draft=None: [hit],
    )
    assert res.status == "answered"


async def test_stats_end_to_end_runs_test():
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
    res = await _run(
        llm, _Replica([raw]), question="is the TGI difference between groups significant?"
    )
    assert res.status == "answered"
    assert res.answer == "The two groups differ significantly (p<0.05)."
    assert res.stat_request is not None and "welch_t_test" in res.stat_request


class _StreamLLM:
    """Like _LLM but the answer model streams its reply in several pieces."""

    def __init__(self, by_model, answer_pieces):
        self.by_model = {k: list(v) for k, v in by_model.items()}
        self.answer_pieces = list(answer_pieces)

    async def complete(self, model, messages):
        return self.by_model[model].pop(0)

    async def complete_stream(self, model, messages):
        if model == SETTINGS.model_route:  # the answer step streams piecewise
            for p in self.answer_pieces:
                yield p
        else:
            yield self.by_model[model].pop(0)


async def test_run_agent_stream_emits_tokens_then_final():
    llm = _StreamLLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
        },
        answer_pieces=["Found ", "1 ", "drug."],
    )
    events = [
        e
        async for e in run_agent_stream(
            "how many?", llm=llm, replica=_Replica([_qr()]), layer=LAYER, settings=SETTINGS
        )
    ]
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens == ["Found ", "1 ", "drug."]
    final = events[-1]
    assert final["type"] == "final"
    assert final["result"].status == "answered"
    assert final["result"].answer == "Found 1 drug."
    assert "for_bd" in final["result"].sql.lower()


async def test_run_agent_stream_clarify_has_no_tokens():
    llm = _StreamLLM({"qwen-fast": ["clarify: which drug?"]}, answer_pieces=[])
    events = [
        e
        async for e in run_agent_stream(
            "how is it?", llm=llm, replica=_Replica([]), layer=LAYER, settings=SETTINGS
        )
    ]
    assert not [e for e in events if e["type"] == "token"]
    assert events[-1]["result"].status == "clarify"


async def test_single_domain_answer_has_one_result_section():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )
    res = await _run(llm, _Replica([_qr()]))
    assert res.status == "answered"
    assert len(res.results) == 1  # single domain still produces one labeled section
    assert res.results[0].result is not None and res.results[0].sql


class _MultiLLM:
    """Content-aware fake: routes to two domains, then answers per the schema/role.

    The fan-out runs the per-domain subgraphs concurrently (asyncio.gather), so a
    pop-order fake is unsafe — decide replies by model + message content instead.
    """

    def __init__(self, intro="为该问题找到 2 类相关数据。"):
        self.intro = intro
        self.answer_calls = 0

    async def complete(self, model, messages):
        text = " ".join(m["content"] for m in messages)
        if model == SETTINGS.model_fast:  # route or extract_genes
            return "mutation, expression" if "domain router" in text else "NONE"
        if model == SETTINGS.model_sql:  # generate_sql — pick the domain's table
            if "model_ccle_expression_data" in text:
                return "SELECT model_uuid, log2tpm FROM model_ccle_expression_data "
            return "SELECT model_uuid, mutation_id FROM model_ccle_mutation_data "
        self.answer_calls += 1  # model_route: only the multi-domain intro
        return self.intro

    async def complete_stream(self, model, messages):
        self.answer_calls += 1
        yield self.intro


class _MultiReplica:
    """Thread-safe (no shared mutable list): returns a domain-shaped result by SQL."""

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        if "expression" in sql:
            return QueryResult(
                columns=["log2tpm"],
                rows=[{"log2tpm": 5.2}],
                rowcount=1,
                truncated=False,
                sql=sql,
                elapsed_ms=1.0,
            )
        return QueryResult(
            columns=["mutation_id"],
            rows=[{"mutation_id": "R175H"}],
            rowcount=1,
            truncated=False,
            sql=sql,
            elapsed_ms=1.0,
        )


async def test_multi_domain_fans_out_into_sections():
    llm = _MultiLLM()
    res = await _run(llm, _MultiReplica(), question="Trp53 相关数据")
    assert res.status == "answered"
    assert res.answer == llm.intro
    assert res.sql is None and res.result is None  # multi: no single top-level result
    assert {s.domain for s in res.results} == {"mutation", "expression"}
    assert all(s.result is not None and s.sql for s in res.results)
    assert llm.answer_calls == 1  # one combined intro, NOT one heavy answer per domain


async def test_multi_domain_stream_emits_intro_then_final():
    llm = _MultiLLM(intro="找到 2 类相关数据，请选择查看。")
    events = [
        e
        async for e in run_agent_stream(
            "CT26 的数据", llm=llm, replica=_MultiReplica(), layer=LAYER, settings=SETTINGS
        )
    ]
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == llm.intro  # intro streamed as tokens
    final = events[-1]["result"]
    assert final.status == "answered"
    assert len(final.results) == 2
