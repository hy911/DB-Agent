from __future__ import annotations

from db_agent.mas.recommender.scoring import rank_models


def test_score_counts_matched_signals():
    signals = [("KRAS 突变", frozenset({"m1", "m2"})), ("HER2 低表达", frozenset({"m1"}))]
    details = {"m1": {"model_id": "A"}, "m2": {"model_id": "B"}}
    ranked = rank_models(signals, details, top_n=3)
    assert ranked[0].model_uuid == "m1" and ranked[0].score == 2
    assert ranked[0].matched == ("KRAS 突变", "HER2 低表达")
    assert ranked[1].model_uuid == "m2" and ranked[1].score == 1


def test_tiebreak_by_expression_value():
    signals = [("HER2 高表达", frozenset({"m1", "m2"}))]
    details = {"m1": {}, "m2": {}}
    ranked = rank_models(signals, details, tiebreak={"m1": 0.2, "m2": 0.9}, top_n=2)
    assert [m.model_uuid for m in ranked] == ["m2", "m1"]  # stronger expresser first


def test_top_n_caps_results():
    signals = [("x", frozenset({"a", "b", "c", "d"}))]
    details = {k: {} for k in "abcd"}
    assert len(rank_models(signals, details, top_n=2)) == 2


def test_stable_order_by_model_id_when_tied():
    signals = [("x", frozenset({"m1", "m2"}))]
    details = {"m1": {"model_id": "Z"}, "m2": {"model_id": "A"}}
    ranked = rank_models(signals, details, top_n=2)
    assert [m.model_id for m in ranked] == ["A", "Z"]


def test_empty_signals_yields_no_models():
    assert rank_models([], {}, top_n=3) == []
