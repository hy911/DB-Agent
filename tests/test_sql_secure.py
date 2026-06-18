from __future__ import annotations

import pytest

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer
from db_agent.sql.errors import GuardError
from db_agent.sql.secure import SecuredQuery, secure_query

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_secure_injects_permission_and_limit():
    out = secure_query("SELECT drug_name FROM model_efficacy_info", LAYER, "efficacy")
    assert isinstance(out, SecuredQuery)
    low = out.sql.lower()
    assert "for_bd" in low and "'yes'" in low  # permission injected
    assert "limit" in low  # limit enforced
    assert out.needs_explain is False  # not the big table
    assert out.limit is not None and out.limit > 0


def test_secure_rejects_out_of_scope_table():
    with pytest.raises(GuardError) as exc:
        secure_query("SELECT * FROM django_session", LAYER, "efficacy")
    assert exc.value.retryable is False


def test_secure_rejects_non_select():
    with pytest.raises(GuardError):
        secure_query("UPDATE model_efficacy_info SET for_bd='no'", LAYER, "efficacy")


def test_mutation_big_table_scan_without_filter_needs_explain():
    secured = secure_query(
        "SELECT count(*) FROM model_ccle_mutation_data", LAYER, "mutation"
    )
    assert secured.needs_explain is True
    assert "model_ccle_mutation_data" in secured.big_tables


def test_mutation_big_table_with_gene_filter_skips_explain():
    secured = secure_query(
        "SELECT mutation_id FROM model_ccle_mutation_data WHERE gene_symbol = 'TP53'",
        LAYER,
        "mutation",
    )
    assert secured.needs_explain is False
