from __future__ import annotations

from decimal import Decimal

import duckdb
import pytest

from db_agent.db.result import QueryResult
from db_agent.sandbox.engine import DuckDBSandbox
from db_agent.sql.errors import GuardError


def test_external_access_disabled_blocks_file_read():
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        with pytest.raises(duckdb.Error):
            con.execute("SELECT * FROM read_csv_auto('pyproject.toml')").fetchall()
    finally:
        con.close()


def test_locked_connection_still_runs_in_memory_sql():
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE result AS SELECT * FROM (VALUES (1), (2), (3)) t(x)")
        assert con.execute("SELECT avg(x) FROM result").fetchone()[0] == 2.0
    finally:
        con.close()


def _rows():
    return [
        {"group_id": "A", "tv": Decimal("100.0")},
        {"group_id": "A", "tv": Decimal("200.0")},
        {"group_id": "B", "tv": Decimal("50.0")},
    ]


def test_engine_runs_aggregation():
    out = DuckDBSandbox().run(
        ["group_id", "tv"],
        _rows(),
        "SELECT group_id, avg(tv) AS m FROM result GROUP BY group_id ORDER BY group_id",
    )
    assert isinstance(out, QueryResult)
    assert out.columns == ["group_id", "m"]
    assert out.rows == [{"group_id": "A", "m": 150.0}, {"group_id": "B", "m": 50.0}]


def test_engine_rejects_unsafe_sql_before_running():
    with pytest.raises(GuardError):
        DuckDBSandbox().run(["x"], [{"x": 1}], "SELECT * FROM read_csv_auto('x')")


def test_engine_handles_empty_rows():
    out = DuckDBSandbox().run(["x"], [], "SELECT count(*) AS n FROM result")
    assert out.rows == [{"n": 0}]
