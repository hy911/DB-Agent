from __future__ import annotations

import pytest

from db_agent.sandbox.validator import validate_analysis_sql
from db_agent.sql.errors import GuardError


def test_accepts_select_over_result():
    ast = validate_analysis_sql("SELECT avg(tumor_volume) AS m FROM result")
    assert ast is not None


def test_accepts_group_by_and_quantile():
    validate_analysis_sql(
        "SELECT group_id, quantile_cont(val, 0.5) AS med FROM result GROUP BY group_id"
    )


def test_rejects_non_select():
    with pytest.raises(GuardError):
        validate_analysis_sql("CREATE TABLE x AS SELECT 1")


def test_rejects_multi_statement():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT 1 FROM result; SELECT 2 FROM result")


def test_rejects_other_table():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT * FROM model_efficacy_info")


def test_rejects_file_function():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT * FROM read_csv_auto('x.csv')")


def test_rejects_attach():
    with pytest.raises(GuardError):
        validate_analysis_sql("ATTACH 'evil.db'")


def test_rejects_file_reader_in_scalar_position():
    # read_csv/read_parquet parse to dedicated sqlglot nodes (name == ""); the
    # node-class check must still reject them even with no FROM-clause table.
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT read_csv('pyproject.toml')")
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT read_parquet('x.parquet')")


def test_rejects_current_setting():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT current_setting('home_directory') FROM result")
