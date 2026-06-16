"""Permission injector tests — the security-critical surface.

Covers: hub direct filter, detail EXISTS, existing-WHERE preservation,
subquery/CTE scopes, idempotency, no-op on uncontrolled tables, and that we
never multiply rows (EXISTS, not JOIN).
"""

import sqlglot
from sqlglot import exp

from db_agent.sql.permission import InjectionConfig, inject_permissions

CFG = InjectionConfig(
    hub_table="model_efficacy_info",
    access_field="for_bd",
    access_value="yes",
    detail_join_keys={
        "model_efficacy_tgi_tv_data": ("model_uuid", "efficacy_num", "group_id"),
        "model_efficacy_tumor_volume_growth_curve_data": (
            "model_uuid",
            "efficacy_num",
            "group_id",
        ),
        "model_efficacy_survival_data": ("model_uuid", "efficacy_num", "group_id"),
    },
    controlled_tables=frozenset(
        {
            "model_efficacy_info",
            "model_efficacy_tgi_tv_data",
            "model_efficacy_tumor_volume_growth_curve_data",
            "model_efficacy_survival_data",
        }
    ),
)


def _inject(sql: str) -> str:
    ast = sqlglot.parse_one(sql, dialect="postgres")
    return inject_permissions(ast, CFG).sql(dialect="postgres")


def test_hub_direct_filter_added():
    out = _inject("SELECT efficacy_num FROM model_efficacy_info")
    assert "for_bd = 'yes'" in out


def test_hub_filter_respects_alias():
    out = _inject("SELECT e.efficacy_num FROM model_efficacy_info AS e")
    assert "e.for_bd = 'yes'" in out


def test_detail_table_gets_exists():
    out = _inject(
        "SELECT tgi FROM model_efficacy_tgi_tv_data WHERE days > 0"
    )
    assert "EXISTS" in out
    assert "model_efficacy_info AS _perm" in out
    # joins on all three keys + the access filter
    assert "_perm.model_uuid = model_efficacy_tgi_tv_data.model_uuid" in out
    assert "_perm.efficacy_num = model_efficacy_tgi_tv_data.efficacy_num" in out
    assert "_perm.group_id = model_efficacy_tgi_tv_data.group_id" in out
    assert "_perm.for_bd = 'yes'" in out


def test_existing_where_is_preserved_and_anded():
    out = _inject("SELECT tgi FROM model_efficacy_tgi_tv_data WHERE days > 0")
    assert "days > 0" in out
    assert " AND " in out


def test_or_condition_is_parenthesized():
    out = _inject(
        "SELECT tgi FROM model_efficacy_tgi_tv_data WHERE days = 1 OR days = 2"
    )
    # original OR must be wrapped so AND-ing our predicate doesn't change meaning
    assert "(days = 1 OR days = 2)" in out


def test_uncontrolled_table_untouched():
    out = _inject("SELECT model_id FROM model_desc_info")
    assert "for_bd" not in out
    assert "EXISTS" not in out


def test_detail_in_subquery_is_filtered():
    sql = (
        "SELECT * FROM ("
        "  SELECT tgi FROM model_efficacy_tgi_tv_data"
        ") sub"
    )
    out = _inject(sql)
    assert "EXISTS" in out
    assert "_perm.for_bd = 'yes'" in out


def test_detail_in_cte_is_filtered():
    sql = (
        "WITH t AS (SELECT tgi FROM model_efficacy_tgi_tv_data) "
        "SELECT * FROM t"
    )
    out = _inject(sql)
    assert "EXISTS" in out


def test_idempotent():
    ast = sqlglot.parse_one(
        "SELECT tgi FROM model_efficacy_tgi_tv_data", dialect="postgres"
    )
    once = inject_permissions(ast, CFG)
    once_sql = once.sql(dialect="postgres")
    twice_sql = inject_permissions(once, CFG).sql(dialect="postgres")
    assert once_sql == twice_sql
    assert once_sql.count("_perm.for_bd = 'yes'") == 1


def test_no_extra_join_added_for_detail():
    """EXISTS semi-join must not add a real JOIN (which would multiply rows)."""
    ast = sqlglot.parse_one(
        "SELECT tgi FROM model_efficacy_tgi_tv_data", dialect="postgres"
    )
    inject_permissions(ast, CFG)
    # the only JOINs/scopes added live inside the EXISTS subquery; the outer
    # SELECT must still have exactly one source table and no joins.
    outer = ast
    assert not outer.args.get("joins")


def test_hub_and_detail_both_present():
    sql = (
        "SELECT d.tgi FROM model_efficacy_tgi_tv_data d "
        "JOIN model_efficacy_info e "
        "ON e.efficacy_num = d.efficacy_num AND e.group_id = d.group_id"
    )
    out = _inject(sql)
    assert "e.for_bd = 'yes'" in out   # hub filtered directly
    assert "EXISTS" in out             # detail still semi-joined (redundant but safe)
