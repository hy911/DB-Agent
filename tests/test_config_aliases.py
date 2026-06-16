from __future__ import annotations

from db_agent.config import Settings

_ALL = [
    "DBAGENT_LITELLM_BASE_URL",
    "DBAGENT_LITELLM_API_KEY",
    "DBAGENT_MODEL_ROUTE",
    "DBAGENT_MODEL_FAST",
    "DBAGENT_MODEL_SQL",
    "LITELLM_BASE_URL",
    "LITELLM_MASTER_KEY",
    "MODEL_MAIN",
    "MODEL_FAST",
    "MODEL_CODE",
]


def _clear(monkeypatch):
    for k in _ALL:
        monkeypatch.delenv(k, raising=False)


def test_accepts_deployed_names(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LITELLM_BASE_URL", "https://llm-dev.example/v1")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("MODEL_MAIN", "qwen-main")
    monkeypatch.setenv("MODEL_FAST", "qwen-fast")
    monkeypatch.setenv("MODEL_CODE", "qwen-code")
    s = Settings(_env_file=None)
    assert s.litellm_base_url == "https://llm-dev.example/v1"
    assert s.litellm_api_key == "sk-test"
    assert s.model_route == "qwen-main"
    assert s.model_fast == "qwen-fast"
    assert s.model_sql == "qwen-code"


def test_dbagent_names_still_work(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DBAGENT_LITELLM_BASE_URL", "http://x/v1")
    monkeypatch.setenv("DBAGENT_MODEL_SQL", "qwen-code-x")
    s = Settings(_env_file=None)
    assert s.litellm_base_url == "http://x/v1"
    assert s.model_sql == "qwen-code-x"
