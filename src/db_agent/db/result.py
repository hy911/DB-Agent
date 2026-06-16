"""The value object returned by a successful read-replica execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool  # rowcount >= the `limit` passed to execute() (else False)
    sql: str
    elapsed_ms: float
