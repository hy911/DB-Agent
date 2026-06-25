from __future__ import annotations

from db_agent.examples.skeleton import skeletonize


def test_literals_are_stripped_to_placeholders():
    sk = skeletonize("SELECT model_name FROM model_desc_info WHERE model_type = 'PDX'")
    assert "'PDX'" not in sk
    assert "model_type" in sk and "model_desc_info" in sk  # structure preserved


def test_value_only_difference_collapses_to_same_skeleton():
    a = skeletonize("SELECT n FROM t WHERE c = 'Lung Carcinoma' AND g = 'EGFR'")
    b = skeletonize("SELECT n FROM t WHERE c = 'Gastric Carcinoma' AND g = 'TP53'")
    assert a == b  # differ only in filter values → identical template


def test_structure_difference_is_preserved():
    grouped = skeletonize("SELECT g, AVG(x) FROM t WHERE g = 'A' GROUP BY g")
    flat = skeletonize("SELECT x FROM t WHERE g = 'A'")
    assert grouped != flat


def test_unparseable_sql_falls_back_to_raw():
    assert skeletonize("not valid sql (((") == "not valid sql ((("
