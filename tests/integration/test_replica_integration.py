"""Live-PostgreSQL integration tests for ReadReplica.

Run with: uv run pytest -m integration   (requires .env DBAGENT_REPLICA_DSN)
Every test is read-only against the database: the write case is rejected by the
read-only transaction, the big-table query is stopped by the EXPLAIN gate before
execution, and pg_sleep is bounded by a 500 ms statement_timeout.
"""

from __future__ import annotations

import pytest

from db_agent.config import Settings
from db_agent.db import ReadReplica
from db_agent.sql.errors import GuardError

pytestmark = pytest.mark.integration

NO_BIG: frozenset[str] = frozenset()
BIG: frozenset[str] = frozenset({"model_ccle_expression_data"})


def test_real_select_returns_shape(replica):
    res = replica.execute(
        "SELECT model_uuid, drug_name, for_bd FROM model_efficacy_info "
        "WHERE for_bd = 'yes' LIMIT 5",
        needs_explain=False,
        big_tables=NO_BIG,
        limit=5,
    )
    assert res.columns == ["model_uuid", "drug_name", "for_bd"]
    assert res.rowcount == len(res.rows)
    assert res.rowcount >= 0
    assert res.elapsed_ms > 0


def test_readonly_transaction_blocks_write(replica):
    # WHERE false: the read-only transaction rejects the UPDATE with 25006, and
    # even if the guard ever failed, zero rows would match — no mutation.
    with pytest.raises(GuardError) as exc:
        replica.execute(
            "UPDATE model_efficacy_info SET for_bd = for_bd WHERE false",
            needs_explain=False,
            big_tables=NO_BIG,
        )
    assert exc.value.category == "read_only"
    assert exc.value.retryable is False


def test_statement_timeout_is_enforced():
    # A dedicated short-timeout replica (same DSN from .env) so the sleep resolves
    # in well under a second.
    replica = ReadReplica(Settings(statement_timeout_ms=500))
    replica.open()
    try:
        with pytest.raises(GuardError) as exc:
            replica.execute("SELECT pg_sleep(2)", needs_explain=False, big_tables=NO_BIG)
        assert exc.value.category == "timeout"
        assert exc.value.retryable is False
    finally:
        replica.close()


def test_big_table_seq_scan_is_gated(replica):
    with pytest.raises(GuardError) as exc:
        replica.execute(
            "SELECT gene_symbol, log2tpm FROM model_ccle_expression_data LIMIT 100",
            needs_explain=True,
            big_tables=BIG,
        )
    assert exc.value.category == "big_table_scan"
    assert exc.value.retryable is False


def test_bad_column_is_retryable(replica):
    with pytest.raises(GuardError) as exc:
        replica.execute(
            "SELECT no_such_col FROM model_efficacy_info LIMIT 1",
            needs_explain=False,
            big_tables=NO_BIG,
        )
    assert exc.value.category == "bad_column"
    assert exc.value.retryable is True
