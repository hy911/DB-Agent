import pytest

from db_agent.sql.errors import GuardError
from db_agent.sql.validator import (
    ValidationConfig,
    enforce_limit,
    parse_single_statement,
    requires_explain_guard,
    validate_structure,
)

EFFICACY_TABLES = frozenset(
    {
        "model_efficacy_info",
        "model_efficacy_tgi_tv_data",
        "model_efficacy_tumor_volume_growth_curve_data",
        "model_efficacy_survival_data",
        "model_desc_info",
        "gene_info",
    }
)
CFG = ValidationConfig(allowed_tables=EFFICACY_TABLES)


def _checked(sql: str) -> None:
    validate_structure(parse_single_statement(sql), CFG)


def test_allows_plain_select():
    _checked("SELECT efficacy_num, tgi_tv FROM model_efficacy_info WHERE drug_name = 'x'")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE model_efficacy_info SET for_bd = 'yes'",
        "DELETE FROM model_efficacy_info",
        "INSERT INTO model_efficacy_info (efficacy_num) VALUES ('1')",
        "DROP TABLE model_efficacy_info",
        "ALTER TABLE model_efficacy_info ADD COLUMN x int",
        "TRUNCATE model_efficacy_info",
    ],
)
def test_rejects_non_read_only(sql):
    with pytest.raises(GuardError) as ei:
        _checked(sql)
    assert ei.value.retryable is False


def test_rejects_multi_statement():
    with pytest.raises(GuardError) as ei:
        parse_single_statement("SELECT 1 FROM model_efficacy_info; DROP TABLE x")
    assert ei.value.category == "multi_statement"
    assert ei.value.retryable is False


def test_rejects_out_of_scope_table():
    with pytest.raises(GuardError) as ei:
        _checked("SELECT * FROM m_model_efficacy_info")
    assert ei.value.category == "forbidden_table"


def test_rejects_system_schema():
    with pytest.raises(GuardError) as ei:
        _checked("SELECT * FROM pg_catalog.pg_tables")
    assert ei.value.category == "forbidden_table"


def test_rejects_banned_function():
    with pytest.raises(GuardError) as ei:
        _checked("SELECT pg_sleep(10) FROM model_efficacy_info")
    assert ei.value.category == "forbidden_function"


def test_parse_error_is_retryable():
    with pytest.raises(GuardError) as ei:
        parse_single_statement("SELECT FROM WHERE")
    assert ei.value.retryable is True


def test_cte_name_not_treated_as_physical_table():
    sql = (
        "WITH eff AS (SELECT efficacy_num FROM model_efficacy_info) "
        "SELECT * FROM eff"
    )
    _checked(sql)  # must not raise: 'eff' is a CTE, not an out-of-scope table


def test_enforce_limit_injects_default():
    ast = parse_single_statement("SELECT 1 FROM model_efficacy_info")
    ast = enforce_limit(ast, CFG)
    assert ast.args["limit"].expression.name == str(CFG.default_limit)


def test_enforce_limit_clamps_excessive():
    ast = parse_single_statement("SELECT 1 FROM model_efficacy_info LIMIT 999999")
    ast = enforce_limit(ast, CFG)
    assert ast.args["limit"].expression.name == str(CFG.max_limit)


def test_big_table_without_filter_needs_explain():
    cfg = ValidationConfig(
        allowed_tables=EFFICACY_TABLES | {"model_ccle_expression_data"},
        big_tables=frozenset({"model_ccle_expression_data"}),
    )
    ast = parse_single_statement("SELECT log2tpm FROM model_ccle_expression_data")
    assert requires_explain_guard(ast, cfg) is True


def test_big_table_with_filter_ok():
    cfg = ValidationConfig(
        allowed_tables=EFFICACY_TABLES | {"model_ccle_expression_data"},
        big_tables=frozenset({"model_ccle_expression_data"}),
    )
    ast = parse_single_statement(
        "SELECT log2tpm FROM model_ccle_expression_data WHERE gene_symbol = 'TP53'"
    )
    assert requires_explain_guard(ast, cfg) is False
