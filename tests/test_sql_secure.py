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
    secured = secure_query("SELECT count(*) FROM model_ccle_mutation_data", LAYER, "mutation")
    assert secured.needs_explain is True
    assert "model_ccle_mutation_data" in secured.big_tables


def test_mutation_big_table_with_gene_filter_skips_explain():
    secured = secure_query(
        "SELECT mutation_id FROM model_ccle_mutation_data WHERE gene_symbol = 'TP53'",
        LAYER,
        "mutation",
    )
    assert secured.needs_explain is False


def test_secure_modeling_hub_injects_for_bd():
    out = secure_query("SELECT model_no FROM modeling_attr_info", LAYER, "modeling")
    low = out.sql.lower()
    assert "for_bd = 'yes'" in low
    assert out.needs_explain is False  # not a big table


def test_secure_modeling_detail_injects_exists_semijoin():
    out = secure_query(
        "SELECT tumor_volume FROM modeling_tumor_volume_growth_curve_data",
        LAYER,
        "modeling",
    )
    s = out.sql
    assert "EXISTS" in s.upper()
    assert "modeling_attr_info AS _perm" in s
    assert "_perm.model_uuid = modeling_tumor_volume_growth_curve_data.model_uuid" in s
    assert "_perm.model_no = modeling_tumor_volume_growth_curve_data.model_no" in s
    assert "_perm.group_id = modeling_tumor_volume_growth_curve_data.group_id" in s
    assert "_perm.for_bd = 'yes'" in s
    # the detail table must NOT get a bare for_bd filter on itself
    assert "modeling_tumor_volume_growth_curve_data.for_bd" not in s
