"""Pydantic request/response models for the query endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    # Optional MAS worker override: explore | recommend | vdr. None/"auto" lets the
    # supervisor's intent router decide. Ignored unless Settings.mas_enabled.
    agent: str | None = None


class ResultRows(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool


class DomainResultModel(BaseModel):
    """One domain's data section. A single-domain answer has one; a multi-domain
    fan-out has several. `error`/`clarification` flag a domain that returned no data."""

    domain: str
    label: str | None = None
    sql: str | None = None
    rows: ResultRows | None = None
    error: str | None = None
    clarification: str | None = None


class QueryResponse(BaseModel):
    status: str  # answered | clarify | error
    run_id: str | None = None
    answer: str | None = None
    sql: str | None = None  # top-level mirror of results[0] (back-compat; single-domain)
    clarification: str | None = None
    error: str | None = None
    rows: ResultRows | None = None  # top-level mirror of results[0] (back-compat)
    results: list[DomainResultModel] = []  # per-domain sections (1 or N); [] for clarify/error
