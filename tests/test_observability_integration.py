from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.build import run_agent
from db_agent.observability.record import RunRecord
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

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        item = self.script.pop(0)
        if isinstance(item, GuardError):
            raise item
        return item


def _qr():
    return QueryResult(
        columns=["drug_name"],
        rows=[{"drug_name": "X"}],
        rowcount=1,
        truncated=False,
        sql="SELECT drug_name",
        elapsed_ms=1.0,
    )


def _happy_llm():
    return _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
            "qwen-main": ["Found 1 drug."],
        }
    )


def test_settings_log_path_defaults_none():
    assert SETTINGS.observability_log_path is None


def test_run_agent_emits_one_record():
    records: list[RunRecord] = []
    res = run_agent(
        "how many?",
        llm=_happy_llm(),
        replica=_Replica([_qr()]),
        layer=LAYER,
        settings=SETTINGS,
        observer=records.append,
    )
    assert res.status == "answered"
    assert len(records) == 1
    assert records[0].status == "answered"
    assert "for_bd" in records[0].sql.lower()


def test_run_agent_without_observer_is_unchanged():
    res = run_agent(
        "how many?", llm=_happy_llm(), replica=_Replica([_qr()]), layer=LAYER, settings=SETTINGS
    )
    assert res.status == "answered"


def test_observer_failure_does_not_break_the_run():
    def boom(record):
        raise RuntimeError("sink down")

    res = run_agent(
        "how many?",
        llm=_happy_llm(),
        replica=_Replica([_qr()]),
        layer=LAYER,
        settings=SETTINGS,
        observer=boom,
    )
    assert res.status == "answered"
    assert res.answer == "Found 1 drug."


def test_record_captures_stat_request():
    records: list[RunRecord] = []
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT group_id, tgi_tv FROM model_efficacy_info",
                "NONE",  # analyze
                '{"function": "one_way_anova", "params": {"value": "tgi_tv", "group": "group_id"}}',
            ],
            "qwen-main": ["Groups differ."],
        }
    )
    raw = QueryResult(
        columns=["group_id", "tgi_tv"],
        rows=[
            {"group_id": g, "tgi_tv": v}
            for g, v in [
                ("A", 1.0),
                ("A", 2.0),
                ("B", 5.0),
                ("B", 6.0),
                ("C", 9.0),
                ("C", 10.0),
            ]
        ],
        rowcount=6,
        truncated=False,
        sql="SELECT group_id, tgi_tv",
        elapsed_ms=1.0,
    )
    run_agent(
        "do groups differ?",
        llm=llm,
        replica=_Replica([raw]),
        layer=LAYER,
        settings=SETTINGS,
        observer=records.append,
    )
    assert len(records) == 1
    assert records[0].stat_request is not None
    assert "one_way_anova" in records[0].stat_request
