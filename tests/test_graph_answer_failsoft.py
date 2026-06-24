from __future__ import annotations

from db_agent.config import Settings
from db_agent.db import QueryResult
from db_agent.graph.build import run_agent
from db_agent.semantic import load_semantic_layer

SETTINGS = Settings(_env_file=None)
LAYER = load_semantic_layer(SETTINGS.semantic_layer_path)


class _LLM:
    """Scripted, but the final answer step (qwen-main) raises like a gateway 504."""

    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}

    def complete(self, model, messages):
        if model == SETTINGS.model_route:  # the answer step
            raise RuntimeError("gateway 504")
        return self.by_model[model].pop(0)


class _Replica:
    def __init__(self, script):
        self.script = list(script)

    def execute(self, sql, *, needs_explain, big_tables, limit=None):
        return self.script.pop(0)


def _qr():
    return QueryResult(
        columns=["drug_name"],
        rows=[{"drug_name": "X"}],
        rowcount=1,
        truncated=False,
        sql="SELECT drug_name",
        elapsed_ms=1.0,
    )


def test_answer_failsoft_returns_data_when_answer_llm_fails():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE", "NONE"],
        }
    )
    res = run_agent("how many?", llm=llm, replica=_Replica([_qr()]), layer=LAYER, settings=SETTINGS)
    # SQL ran fine; the answer LLM 504'd — we degrade instead of raising (-> 502).
    assert res.status == "answered"
    assert res.result is not None and res.result.rowcount == 1
    assert res.sql is not None and "for_bd" in res.sql.lower()
    assert "超时" in (res.answer or "")  # the fallback note
