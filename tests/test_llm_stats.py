from __future__ import annotations

from db_agent.config import Settings
from db_agent.llm.agent_llm import answer_stat, request_stat
from db_agent.sandbox.stats.registry import catalog_text
from db_agent.sandbox.stats.spec import StatResult

SETTINGS = Settings(_env_file=None)


class _LLM:
    def __init__(self, by_model):
        self.by_model = {k: list(v) for k, v in by_model.items()}
        self.seen = []

    async def complete(self, model, messages):
        self.seen.append((model, messages))
        return self.by_model[model].pop(0)


async def test_request_stat_returns_json_string():
    llm = _LLM(
        {"qwen-code": ['{"function": "welch_t_test", "params": {"value": "v", "group": "g"}}']}
    )
    out = await request_stat(
        llm, SETTINGS, "is it significant?", ["g", "v"], "g, v\nctrl, 1", catalog_text()
    )
    assert "welch_t_test" in out
    assert llm.seen[0][0] == "qwen-code"


async def test_request_stat_strips_fences():
    llm = _LLM({"qwen-code": ['```json\n{"function": "one_way_anova"}\n```']})
    out = await request_stat(llm, SETTINGS, "q", ["g", "v"], "preview", catalog_text())
    assert out.startswith("{")
    assert "```" not in out


async def test_request_stat_none():
    llm = _LLM({"qwen-code": ["NONE"]})
    assert await request_stat(llm, SETTINGS, "q", ["g"], "p", catalog_text()) == "NONE"


def test_stat_messages_encourage_emitting_when_significance_asked():
    from db_agent.llm.prompts import stat_messages

    msgs = stat_messages(
        "is A vs B significant?", ["group_id", "tv"], "group_id, tv\nA, 1", catalog_text()
    )
    system = msgs[0]["content"].lower()
    assert "significan" in system  # nudges emitting a test when significance is asked
    assert "p-value" in system or "p value" in system


async def test_answer_stat_formats_and_routes():
    stat = StatResult(
        test="welch_t_test",
        stats={"t": -3.5, "p_value": 0.01, "mean_difference": -7.0},
        groups=[{"label": "ctrl", "n": 4, "mean": 10.5}, {"label": "drug", "n": 4, "mean": 2.5}],
        caveats=["Welch's t-test.", "Result is significant at alpha=0.05 (p=0.01)."],
    )
    llm = _LLM({"qwen-main": ["The difference is significant (p=0.01)."]})
    out = await answer_stat(
        llm, SETTINGS, "significant?", "SELECT ...", "SELECT ... FROM result", stat
    )
    assert out == "The difference is significant (p=0.01)."
    assert llm.seen[0][0] == "qwen-main"
    # the prompt carried the formatted summary
    user_msg = llm.seen[0][1][1]["content"]
    assert "welch_t_test" in user_msg
    assert "p_value" in user_msg
