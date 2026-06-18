from __future__ import annotations

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_routable_domains_are_efficacy_expression_mutation():
    names = {d.name for d in LAYER.routable_domains()}
    assert names == {"efficacy", "expression", "mutation"}


def test_routable_excludes_reference_and_undefined_domains():
    names = {d.name for d in LAYER.routable_domains()}
    assert "reference" not in names  # dictionary domain, never routed
    assert "modeling" not in names  # forward-declared, no tables yet


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
