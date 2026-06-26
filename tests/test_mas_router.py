from __future__ import annotations

from db_agent.config import Settings
from db_agent.mas.router import DEFAULT_KIND, classify_intent

SETTINGS = Settings(_env_file=None)


class _C:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.model: str | None = None

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        self.model = model
        return self.reply


async def test_classify_recommend():
    assert await classify_intent(_C("recommend"), SETTINGS, "推荐适合的模型") == "recommend"


async def test_classify_vdr():
    assert await classify_intent(_C("vdr"), SETTINGS, "CT26 成瘤率多少") == "vdr"


async def test_classify_explore():
    assert await classify_intent(_C("explore"), SETTINGS, "查 EGFR 表达") == "explore"


async def test_classify_uses_fast_model():
    c = _C("explore")
    await classify_intent(c, SETTINGS, "q")
    assert c.model == SETTINGS.model_fast


async def test_classify_unexpected_falls_open_to_explore():
    assert await classify_intent(_C("banana"), SETTINGS, "q") == DEFAULT_KIND


async def test_classify_tolerates_wordy_reply():
    # a non-leading mention still routes to the named worker
    assert await classify_intent(_C("this is a recommend request"), SETTINGS, "q") == "recommend"
