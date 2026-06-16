from __future__ import annotations

import dataclasses

import pytest

from db_agent.db.result import QueryResult


def test_query_result_holds_fields():
    r = QueryResult(
        columns=["a", "b"],
        rows=[{"a": 1, "b": 2}],
        rowcount=1,
        truncated=False,
        sql="SELECT 1",
        elapsed_ms=1.5,
    )
    assert r.columns == ["a", "b"]
    assert r.rows == [{"a": 1, "b": 2}]
    assert r.rowcount == 1
    assert r.truncated is False
    assert r.sql == "SELECT 1"
    assert r.elapsed_ms == 1.5


def test_query_result_is_frozen():
    r = QueryResult(columns=[], rows=[], rowcount=0, truncated=False, sql="", elapsed_ms=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.rowcount = 5  # type: ignore[misc]
