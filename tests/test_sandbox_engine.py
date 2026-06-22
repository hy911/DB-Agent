from __future__ import annotations

import duckdb
import pytest


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
