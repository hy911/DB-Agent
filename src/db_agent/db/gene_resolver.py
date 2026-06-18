"""Deterministic gene-name resolution (CLAUDE.md fixed decision #5).

Case is significant — it encodes species in this DB (human EGFR vs mouse Egfr) —
so exact matching is case-sensitive. A pg_trgm fuzzy match is only ever offered as
a clarification candidate, never auto-resolved. `_decide` is pure; `resolve_gene`
runs the parameterized queries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_agent.db.replica import ReadReplica


@dataclass(frozen=True)
class GeneMatch:
    symbol: str  # canonical gene_info."Symbol"
    species: str | None
    via: str  # "symbol_exact" | "synonym_exact" | "fuzzy"
    score: float  # 1.0 for exact; similarity() for fuzzy


@dataclass(frozen=True)
class GeneResolution:
    query: str
    status: str  # "resolved" | "ambiguous" | "unknown"
    symbol: str | None
    candidates: list[GeneMatch]


def _decide(query: str, exact: list[GeneMatch], fuzzy: list[GeneMatch]) -> GeneResolution:
    distinct = {m.symbol for m in exact}
    if len(distinct) == 1:
        return GeneResolution(query, "resolved", next(iter(distinct)), list(exact))
    if len(distinct) > 1:
        return GeneResolution(query, "ambiguous", None, list(exact))
    if fuzzy:
        ranked = sorted(fuzzy, key=lambda m: m.score, reverse=True)
        return GeneResolution(query, "ambiguous", None, ranked)
    return GeneResolution(query, "unknown", None, [])
