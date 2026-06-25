"""The retrieved few-shot example: a past question and the raw SQL that answered it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    question: str
    sql: str
    domain: str
    skeleton: str = ""  # de-parameterized SQL template, for structure-aware recall
