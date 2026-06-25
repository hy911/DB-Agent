from __future__ import annotations

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer
from db_agent.sql.critic import diagnose_empty_result

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_closed_enum_value_out_of_set_returns_hint():
    hint = diagnose_empty_result(
        "SELECT model_name FROM model_desc_info m WHERE m.is_cancer_model = 'T'", LAYER, "model"
    )
    assert hint is not None
    assert "is_cancer_model" in hint
    assert "cancer" in hint  # names the allowed values


def test_finer_subtype_outside_cancer_type_set_returns_hint():
    hint = diagnose_empty_result(
        "SELECT model_name FROM model_desc_info WHERE cancer_type = 'NSCLC'", LAYER, "model"
    )
    assert hint is not None
    assert "cancer_type" in hint


def test_in_list_with_bad_member_returns_hint():
    hint = diagnose_empty_result(
        "SELECT model_name FROM model_desc_info WHERE cancer_type IN ('Lung Carcinoma', 'NSCLC')",
        LAYER,
        "model",
    )
    assert hint is not None
    assert "NSCLC" in hint


def test_valid_enum_value_returns_none():
    assert (
        diagnose_empty_result(
            "SELECT model_name FROM model_desc_info WHERE is_cancer_model = 'cancer'",
            LAYER,
            "model",
        )
        is None
    )


def test_open_vocabulary_ilike_never_fires():
    # drug_name has examples but no closed `values` — a 0-row ILIKE there is a real
    # empty result (e.g. permission-filtered), the critic must NOT flag it.
    assert (
        diagnose_empty_result(
            "SELECT drug_name FROM model_efficacy_info WHERE drug_name ILIKE '%gefitinib%'",
            LAYER,
            "efficacy",
        )
        is None
    )


def test_non_enum_equality_returns_none():
    assert (
        diagnose_empty_result(
            "SELECT model_name FROM model_desc_info WHERE model_name = 'CT26'", LAYER, "model"
        )
        is None
    )


def test_unparseable_sql_returns_none():
    assert diagnose_empty_result("NOT SQL AT ALL ((", LAYER, "model") is None
