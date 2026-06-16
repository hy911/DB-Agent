"""Integration-test support: a live-DB ReadReplica fixture and a DSN gate.

When DBAGENT_REPLICA_DSN is not configured (still the default), every
integration-marked test is skipped so `-m integration` degrades gracefully with
no database. The offline suite never reaches here (it deselects `integration`).
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
    skip = pytest.mark.skip(reason="DBAGENT_REPLICA_DSN not set; integration tests skipped")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def replica():
    r = ReadReplica(get_settings())
    r.open()
    yield r
    r.close()
