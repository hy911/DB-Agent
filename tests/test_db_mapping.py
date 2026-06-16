from __future__ import annotations

import pytest

from db_agent.db.mapping import classify_db_error


@pytest.mark.parametrize(
    "sqlstate, expected",
    [
        ("42703", ("bad_column", True)),
        ("42883", ("bad_function", True)),
        ("42804", ("bad_type", True)),
        ("42P01", ("bad_table", True)),
        ("42601", ("bad_syntax", True)),
        ("57014", ("timeout", False)),
        ("42501", ("forbidden", False)),
        ("08006", ("connection", False)),  # class 08 -> connection
        ("08003", ("connection", False)),
        ("99999", ("db_error", False)),  # unknown -> fatal
        (None, ("db_error", False)),  # missing -> fatal
    ],
)
def test_classify_db_error(sqlstate, expected):
    assert classify_db_error(sqlstate) == expected
