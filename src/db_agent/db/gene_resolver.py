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


def resolve_gene(
    replica: ReadReplica, name: str, *, fuzzy_threshold: float = 0.4, limit: int = 5
) -> GeneResolution:
    exact: list[GeneMatch] = []
    for row in replica.fetch(
        'SELECT "Symbol" AS symbol, species FROM gene_info WHERE "Symbol" = %s', (name,)
    ):
        exact.append(
            GeneMatch(
                symbol=row["symbol"], species=row.get("species"), via="symbol_exact", score=1.0
            )
        )
    for row in replica.fetch(
        "SELECT gene_symbol AS symbol, species FROM gene_synonyms WHERE synonym = %s", (name,)
    ):
        exact.append(
            GeneMatch(
                symbol=row["symbol"], species=row.get("species"), via="synonym_exact", score=1.0
            )
        )

    fuzzy: list[GeneMatch] = []
    if not exact:
        rows = replica.fetch(
            'SELECT "Symbol" AS symbol, species, similarity("Symbol", %s) AS sim '
            'FROM gene_info WHERE similarity("Symbol", %s) > %s ORDER BY sim DESC LIMIT %s',
            (name, name, fuzzy_threshold, limit),
        )
        fuzzy = [
            GeneMatch(
                symbol=r["symbol"], species=r.get("species"), via="fuzzy", score=float(r["sim"])
            )
            for r in rows
        ]

    return _decide(name, exact, fuzzy)
