from __future__ import annotations

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_routable_domains_include_model_spine():
    names = {d.name for d in LAYER.routable_domains()}
    # the four measurement domains plus the model-attribute/identifier domain
    assert names == {"efficacy", "expression", "mutation", "modeling", "model"}


def test_model_domain_holds_spine_and_not_gene_bearing():
    assert LAYER.get_table("model_desc_info").domain == "model"
    assert LAYER.get_table("model_rnaseq_mapping").domain == "model"
    assert [t.name for t in LAYER.spine_tables()] == ["model_desc_info"]
    assert LAYER.is_gene_bearing("model") is False


def test_routable_excludes_reference_and_undefined_domains():
    names = {d.name for d in LAYER.routable_domains()}
    assert "reference" not in names  # dictionary domain, never routed


def test_gene_info_symbol_column_matches_db_casing():
    t = LAYER.get_table("gene_info")
    assert t.has_column("Symbol")  # matches the real DB column
    assert not t.has_column("symbol")


def test_is_gene_bearing():
    assert LAYER.is_gene_bearing("expression") is True  # has a gene_symbol column
    assert LAYER.is_gene_bearing("efficacy") is False


def test_mutation_is_gene_bearing():
    assert LAYER.is_gene_bearing("mutation") is True


def test_mutation_main_table_is_big_and_in_domain():
    t = LAYER.get_table("model_ccle_mutation_data")
    assert t is not None
    assert t.domain == "mutation"
    assert t.big_table is True
    assert t.has_column("gene_symbol")
    assert t.has_column("model_uuid")
    assert t.join_to_hub == ("model_uuid",)


def test_oncokb_in_mutation_domain_not_access_controlled():
    t = LAYER.get_table("oncokb")
    assert t is not None
    assert t.domain == "mutation"
    assert t.access_controlled is False
    assert t.has_column("gene")
    assert t.has_column("mutant")


def test_modeling_access_controlled_with_hub():
    dom = LAYER.get_domain("modeling")
    assert dom is not None
    assert dom.access_controlled is True
    assert dom.hub == "modeling_attr_info"


def test_modeling_not_gene_bearing():
    assert LAYER.is_gene_bearing("modeling") is False


def test_modeling_detail_tables_join_to_hub():
    details = LAYER.detail_tables_of("modeling_attr_info")
    names = {t.name for t in details}
    assert names == {
        "modeling_tumor_volume_growth_curve_data",
        "modeling_body_weight_growth_curve_data",
        "modeling_survival_data",
        "modeling_facs_growth_curve_data",
        "modeling_avg_radiance_data",
        "modeling_total_flux_data",
        "modeling_elisa_data",
        "modeling_pathology_data",
        "modeling_panel_data",
    }
    for t in details:
        assert t.access_via == "modeling_attr_info"
        if t.name == "modeling_panel_data":
            assert t.join_to_hub == ("model_uuid", "model_no")  # no group_id
        else:
            assert t.join_to_hub == ("model_uuid", "model_no", "group_id")


def test_modeling_panel_included_two_key_grain():
    t = LAYER.get_table("modeling_panel_data")
    assert t is not None
    assert t.access_via == "modeling_attr_info"
    assert t.join_to_hub == ("model_uuid", "model_no")
