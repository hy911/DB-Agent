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


class RecommendRequest(BaseModel):
    question: str  # the customer's model-selection brief
    top_n: int = 3
    format: str | None = None  # "pdf" → return application/pdf instead of JSON


class RecommendResponse(BaseModel):
    # models[] are plain dicts (their keys start with `model_`, which pydantic
    # reserves as a protected field namespace — dicts sidestep that cleanly).
    question: str
    summary: str
    models: list[dict[str, object]] = []
    notes: list[str] = []
    report_html: str
