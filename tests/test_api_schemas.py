from __future__ import annotations

import pytest
from pydantic import ValidationError

from db_agent.api.schemas import QueryRequest, QueryResponse, ResultRows


def test_query_request_requires_question():
    assert QueryRequest(question="hi").question == "hi"
    with pytest.raises(ValidationError):
        QueryRequest()


def test_query_response_defaults_are_none():
    r = QueryResponse(status="error")
    assert r.status == "error"
    assert r.answer is None
    assert r.rows is None


def test_query_response_carries_rows():
    rows = ResultRows(columns=["a"], rows=[{"a": 1}], rowcount=1, truncated=False)
    r = QueryResponse(status="answered", answer="ok", sql="SELECT 1", rows=rows)
    dumped = r.model_dump()
    assert dumped["rows"]["columns"] == ["a"]
    assert dumped["status"] == "answered"
