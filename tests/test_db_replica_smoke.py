from __future__ import annotations

from db_agent.config import Settings
from db_agent.db.replica import ReadReplica


def test_readreplica_constructs_without_connecting():
    # Default Settings() needs no env; pool is created with open=False so no
    # network access happens here.
    replica = ReadReplica(Settings(pool_min_size=1, pool_max_size=4))
    try:
        assert replica.pool.min_size == 1
        assert replica.pool.max_size == 4
    finally:
        replica.close()
