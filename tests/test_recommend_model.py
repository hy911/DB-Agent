from __future__ import annotations

from db_agent.mas.recommender.model import Criteria, ExpressionCriterion


def test_from_json_full():
    c = Criteria.from_json(
        '{"mutated_genes": ["KRAS"], "expression": [{"gene": "HER2", "direction": "low"}], '
        '"cancer_type": "Lung Carcinoma", "model_type": "PDX"}'
    )
    assert c.mutated_genes == ("KRAS",)
    assert c.expression == (ExpressionCriterion("HER2", "low"),)
    assert c.cancer_type == "Lung Carcinoma" and c.model_type == "PDX"
    assert not c.is_empty()


def test_from_json_malformed_returns_empty():
    assert Criteria.from_json("not json at all").is_empty()
    assert Criteria.from_json("[1,2,3]").is_empty()  # not an object


def test_from_json_partial_defaults_the_rest():
    c = Criteria.from_json('{"mutated_genes": ["TP53"]}')
    assert c.mutated_genes == ("TP53",)
    assert c.expression == () and c.cancer_type is None and c.model_type is None


def test_from_json_drops_bad_expression_direction():
    c = Criteria.from_json('{"expression": [{"gene": "X", "direction": "medium"}]}')
    assert c.expression == ()  # only high/low are accepted


def test_empty_criteria_is_empty():
    assert Criteria().is_empty()
