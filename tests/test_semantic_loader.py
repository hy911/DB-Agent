from __future__ import annotations

from pathlib import Path

import pytest

from db_agent.semantic import SemanticLayerError, load_semantic_layer

YAML_PATH = Path(__file__).resolve().parents[1] / "semantic_layer.yaml"


def test_loads_repo_semantic_layer():
    layer = load_semantic_layer(YAML_PATH)
    assert layer.spine_key == "model_uuid"
    assert "model_efficacy_info" in layer.tables
    assert layer.get_domain("efficacy").hub == "model_efficacy_info"


def test_detail_tables_resolve_to_hub():
    layer = load_semantic_layer(YAML_PATH)
    details = {t.name for t in layer.detail_tables_of("model_efficacy_info")}
    assert details == {
        "model_efficacy_tumor_volume_growth_curve_data",
        "model_efficacy_tgi_tv_data",
        "model_efficacy_survival_data",
    }
    for t in layer.detail_tables_of("model_efficacy_info"):
        assert t.join_to_hub == ("model_uuid", "efficacy_num", "group_id")
        assert t.is_detail


def test_efficacy_info_is_access_controlled_hub():
    layer = load_semantic_layer(YAML_PATH)
    hub = layer.get_table("model_efficacy_info")
    assert hub.access_controlled
    assert hub.has_column("for_bd")


def test_column_value_hints_parse():
    layer = load_semantic_layer(YAML_PATH)
    desc = layer.get_table("model_desc_info")
    assert desc.columns["is_cancer_model"].values == ("cancer", "no_cancer")
    assert "PDX" in desc.columns["model_type"].values
    assert desc.columns["cancer_type"].language == "english"
    assert "Lung Carcinoma" in desc.columns["cancer_type"].values  # closed vocabulary
    assert layer.get_table("model_efficacy_info").columns["drug_name"].language == "english"


def test_validation_rejects_missing_join_key(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
meta:
  spine_key: model_uuid
domains:
  efficacy: {label: x, hub: hub_t, access_controlled: true}
tables:
  hub_t:
    domain: efficacy
    columns:
      model_uuid: {type: varchar}
  detail_t:
    domain: efficacy
    access_via: hub_t
    join_to_hub: [model_uuid, efficacy_num]
    columns:
      model_uuid: {type: varchar}
""",
        encoding="utf-8",
    )
    with pytest.raises(SemanticLayerError) as ei:
        load_semantic_layer(bad)
    assert "efficacy_num" in str(ei.value)
