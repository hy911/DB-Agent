from __future__ import annotations

import pytest

from db_agent.db.explain import evaluate_explain, seq_scanned_big_tables
from db_agent.sql.errors import GuardError

BIG = frozenset({"model_ccle_expression_data"})


def _plan(node: dict) -> list[dict]:
    """Wrap a plan node the way EXPLAIN (FORMAT JSON) returns it."""
    return [{"Plan": node}]


def test_seq_scan_on_big_table_is_rejected():
    plan = _plan({"Node Type": "Seq Scan", "Relation Name": "model_ccle_expression_data"})
    with pytest.raises(GuardError) as exc:
        evaluate_explain(plan, BIG)
    assert exc.value.retryable is False
    assert exc.value.category == "big_table_scan"


def test_index_scan_on_big_table_passes():
    plan = _plan({"Node Type": "Index Scan", "Relation Name": "model_ccle_expression_data"})
    assert evaluate_explain(plan, BIG) is None


def test_seq_scan_on_non_big_table_passes():
    plan = _plan({"Node Type": "Seq Scan", "Relation Name": "model_efficacy_info"})
    assert evaluate_explain(plan, BIG) is None


def test_nested_seq_scan_under_gather_is_caught():
    plan = _plan(
        {
            "Node Type": "Gather",
            "Plans": [
                {
                    "Node Type": "Nested Loop",
                    "Plans": [
                        {"Node Type": "Index Scan", "Relation Name": "model_efficacy_info"},
                        {"Node Type": "Seq Scan", "Relation Name": "model_ccle_expression_data"},
                    ],
                }
            ],
        }
    )
    hits = seq_scanned_big_tables(plan, BIG)
    assert hits == ["model_ccle_expression_data"]
    with pytest.raises(GuardError):
        evaluate_explain(plan, BIG)


def test_empty_plan_passes():
    assert evaluate_explain([], BIG) is None
