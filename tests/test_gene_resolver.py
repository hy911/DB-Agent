from __future__ import annotations

from db_agent.db.gene_resolver import GeneMatch, GeneResolution, _decide


def _gm(symbol, *, via="symbol_exact", score=1.0, species="human"):
    return GeneMatch(symbol=symbol, species=species, via=via, score=score)


def test_unique_exact_is_resolved():
    res = _decide("EGFR", [_gm("EGFR")], [])
    assert isinstance(res, GeneResolution)
    assert res.status == "resolved"
    assert res.symbol == "EGFR"
    assert res.query == "EGFR"


def test_multiple_distinct_exact_is_ambiguous():
    res = _decide("x", [_gm("TP53"), _gm("Trp53", species="mouse")], [])
    assert res.status == "ambiguous"
    assert res.symbol is None
    assert {m.symbol for m in res.candidates} == {"TP53", "Trp53"}


def test_shared_synonym_disambiguated_by_query_casing():
    # 'HER2' maps to human ERBB2 + mouse Erbb2; uppercase query → human.
    human = _gm("ERBB2", via="synonym_exact", species="human")
    mouse = _gm("Erbb2", via="synonym_exact", species="mouse")
    up = _decide("HER2", [human, mouse], [])
    assert up.status == "resolved" and up.symbol == "ERBB2"
    # title-case query → mouse.
    title = _decide("Her2", [human, mouse], [])
    assert title.status == "resolved" and title.symbol == "Erbb2"
    # mixed-case / no signal → stay ambiguous (safe).
    amb = _decide("hEr2", [human, mouse], [])
    assert amb.status == "ambiguous"


def test_same_symbol_twice_still_resolved():
    # symbol-exact and synonym-exact both pointing at one symbol
    res = _decide("EGFR", [_gm("EGFR"), _gm("EGFR", via="synonym_exact")], [])
    assert res.status == "resolved"
    assert res.symbol == "EGFR"


def test_fuzzy_only_is_ambiguous_sorted_desc():
    res = _decide(
        "egfr",
        [],
        [_gm("Egfr", via="fuzzy", score=0.5), _gm("EGFR", via="fuzzy", score=0.8)],
    )
    assert res.status == "ambiguous"
    assert res.symbol is None
    assert [m.symbol for m in res.candidates] == ["EGFR", "Egfr"]


def test_no_match_is_unknown():
    res = _decide("zzz", [], [])
    assert res.status == "unknown"
    assert res.symbol is None
    assert res.candidates == []


def test_noisy_synonym_resolves_obvious_target():
    # gene_synonyms maps 'PD1' to {PDCD1, SNCA, SPATA2}; PDCD1 is the obvious
    # target (the query is a subsequence of it) and should win over trigram junk.
    res = _decide(
        "PD1",
        [
            _gm("PDCD1", via="synonym_exact"),
            _gm("SNCA", via="synonym_exact"),
            _gm("SPATA2", via="synonym_exact"),
        ],
        [],
    )
    assert res.status == "resolved"
    assert res.symbol == "PDCD1"


def test_ambiguous_synonyms_are_ranked_when_no_clear_winner():
    # two equally-unrelated symbols → still ambiguous, but ordered deterministically
    res = _decide(
        "X",
        [_gm("AAAA", via="synonym_exact"), _gm("BBBB", via="synonym_exact")],
        [],
    )
    assert res.status == "ambiguous"
    assert [m.symbol for m in res.candidates] == ["AAAA", "BBBB"]


def test_species_casing_still_wins_over_ranking():
    # HER2 (all-caps → human) must still resolve to human ERBB2, not rank-guess
    res = _decide(
        "HER2",
        [
            _gm("ERBB2", species="human", via="synonym_exact"),
            _gm("Erbb2", species="mouse", via="synonym_exact"),
        ],
        [],
    )
    assert res.status == "resolved"
    assert res.symbol == "ERBB2"
