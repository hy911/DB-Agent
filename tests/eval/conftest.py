"""Eval-suite support: a live ReadReplica fixture + a DSN gate.

Mirrors tests/integration/conftest.py. The execution-accuracy benchmark needs
BOTH a live replica (to run the gold SQL) and the LLM gateway (to run the agent),
so when DBAGENT_REPLICA_DSN is unset every `eval`-marked test is skipped. The
offline suite never reaches here (it deselects `eval`).
"""

from __future__ import annotations

import pytest

from db_agent.config import get_settings
from db_agent.db import ReadReplica

_DEFAULT_DSN = "postgresql://readonly@localhost:5432/tumordb"


def _dsn_configured() -> bool:
    return get_settings().replica_dsn != _DEFAULT_DSN


def pytest_collection_modifyitems(config, items):
    if _dsn_configured():
        return
    skip = pytest.mark.skip(reason="DBAGENT_REPLICA_DSN not set; eval tests skipped")
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def replica():
    r = ReadReplica(get_settings())
    r.open()
    yield r
    r.close()
