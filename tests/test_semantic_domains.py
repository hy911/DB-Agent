from __future__ import annotations

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_routable_domains_are_efficacy_and_expression():
    names = {d.name for d in LAYER.routable_domains()}
    assert names == {"efficacy", "expression"}


def test_routable_excludes_reference_and_undefined_domains():
    names = {d.name for d in LAYER.routable_domains()}
    assert "reference" not in names  # dictionary domain, never routed
    assert "modeling" not in names  # forward-declared, no tables
    assert "mutation" not in names  # forward-declared, no tables


def test_gene_info_symbol_column_matches_db_casing():
    t = LAYER.get_table("gene_info")
    assert t.has_column("Symbol")  # matches the real DB column
    assert not t.has_column("symbol")


def test_is_gene_bearing():
    assert LAYER.is_gene_bearing("expression") is True  # has a gene_symbol column
    assert LAYER.is_gene_bearing("efficacy") is False
