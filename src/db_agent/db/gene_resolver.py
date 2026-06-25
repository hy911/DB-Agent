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


def _species_from_casing(query: str) -> str | None:
    """Infer the intended species from the query's own casing.

    This DB encodes species in symbol casing (human upper EGFR, mouse title-case
    Egfr). A shared synonym like 'HER2' maps to BOTH species, so case-sensitive
    matching alone can't split them — but the *query's* casing carries the same
    signal: all-uppercase → human, title-case → mouse. Anything else → no signal.
    """
    letters = [c for c in query if c.isalpha()]
    if not letters:
        return None
    if all(c.isupper() for c in letters):
        return "human"
    if letters[0].isupper() and all(c.islower() for c in letters[1:]):
        return "mouse"
    return None


def _norm(s: str) -> str:
    """Casefold + drop non-alphanumerics so 'PD-1', 'pd1', 'PD1' compare equal."""
    return "".join(ch for ch in s if ch.isalnum()).upper()


def _is_subseq(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def _match_rank(query: str, symbol: str) -> int:
    """How closely a candidate symbol resembles the raw query (lower = closer).

    The noisy synonym table maps a common alias like 'PD1' to several symbols
    ({PDCD1, SNCA, SPATA2}); rank by string resemblance so the obvious target
    (PDCD1 — query is a subsequence of it) beats the trigram-junk ones.
    """
    q, s = _norm(query), _norm(symbol)
    if q == s:
        return 0
    if s.startswith(q):
        return 1
    if _is_subseq(q, s):
        return 2
    return 3


def _rank(query: str, matches: list[GeneMatch]) -> list[GeneMatch]:
    """Sort by resemblance, then shorter symbol, then name; dedup by symbol."""
    ordered = sorted(matches, key=lambda m: (_match_rank(query, m.symbol), len(m.symbol), m.symbol))
    seen: set[str] = set()
    return [m for m in ordered if not (m.symbol in seen or seen.add(m.symbol))]


def _decide(query: str, exact: list[GeneMatch], fuzzy: list[GeneMatch]) -> GeneResolution:
    distinct = {m.symbol for m in exact}
    if len(distinct) == 1:
        return GeneResolution(query, "resolved", next(iter(distinct)), list(exact))
    if len(distinct) > 1:
        # A synonym shared across species (e.g. 'HER2' → human ERBB2 + mouse Erbb2):
        # disambiguate by the query's casing before falling back to a clarify.
        species = _species_from_casing(query)
        if species is not None:
            narrowed = [m for m in exact if m.species == species]
            if len({m.symbol for m in narrowed}) == 1:
                return GeneResolution(query, "resolved", narrowed[0].symbol, narrowed)
        # Otherwise rank candidates by resemblance to the query: if one clearly
        # wins (strictly closer than the runner-up, and itself a real match), take
        # it; else clarify, but with the candidates ordered most-relevant first.
        ranked = _rank(query, exact)
        best_rank = _match_rank(query, ranked[0].symbol)
        runner_rank = _match_rank(query, ranked[1].symbol) if len(ranked) > 1 else 99
        if best_rank <= 2 and best_rank < runner_rank:
            return GeneResolution(query, "resolved", ranked[0].symbol, ranked)
        return GeneResolution(query, "ambiguous", None, ranked)
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
