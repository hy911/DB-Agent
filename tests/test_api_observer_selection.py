from __future__ import annotations

from db_agent.api.app import _select_observer
from db_agent.config import Settings
from db_agent.observability.observer import JsonlObserver


def test_default_jsonl_when_nothing_configured(tmp_path):
    default = tmp_path / "runs.jsonl"
    s = Settings(_env_file=None, default_log_path=default)
    obs, audit = _select_observer(s)
    assert isinstance(obs, JsonlObserver)
    assert audit is None
    assert obs._path == default


def test_explicit_log_path_overrides_default(tmp_path):
    explicit = tmp_path / "explicit.jsonl"
    s = Settings(
        _env_file=None,
        observability_log_path=explicit,
        default_log_path=tmp_path / "d.jsonl",
    )
    obs, audit = _select_observer(s)
    assert isinstance(obs, JsonlObserver)
    assert obs._path == explicit
    assert audit is None
