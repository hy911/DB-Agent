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
