"""Pydantic request/response models for the query endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class ResultRows(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool


class QueryResponse(BaseModel):
    status: str  # answered | clarify | error
    answer: str | None = None
    sql: str | None = None
    clarification: str | None = None
    error: str | None = None
    rows: ResultRows | None = None
