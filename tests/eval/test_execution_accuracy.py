"""Execution-Accuracy benchmark (marker: eval, deselected by default).

Runs the full agent over the golden set against the live gateway + replica,
compares each answer's result set to the gold SQL's, prints a per-case report,
and asserts an aggregate EA floor as a regression gate. Run with:

    uv run pytest -m eval -s
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from harness import rows_match

from db_agent.config import get_settings
from db_agent.graph import run_agent
from db_agent.llm import LiteLLMClient
from db_agent.semantic import load_semantic_layer

pytestmark = pytest.mark.eval

_GOLDEN = yaml.safe_load(
    (pathlib.Path(__file__).parent / "golden.yaml").read_text(encoding="utf-8")
)
_EA_FLOOR = 0.7


def _pred_rows(res) -> list[dict]:
    """Rows the agent actually returned (single-domain → result; fan-out → the
    first populated section)."""
    if res.result is not None:
        return res.result.rows
    for section in res.results:
        if section.result is not None:
            return section.result.rows
    return []


async def test_execution_accuracy(replica):
    settings = get_settings()
    llm = LiteLLMClient(settings)
    layer = load_semantic_layer(settings.semantic_layer_path)

    report: list[tuple[bool, str]] = []
    for case in _GOLDEN:
        res = await run_agent(
            case["question"], llm=llm, replica=replica, layer=layer, settings=settings
        )
        gold = replica.fetch(case["gold_sql"])
        ok = res.status == "answered" and rows_match(gold, _pred_rows(res))
        report.append((ok, case["question"]))

    passed = sum(1 for ok, _ in report if ok)
    total = len(report)
    print("\n=== Execution Accuracy ===")
    for ok, q in report:
        print(f"  [{'PASS' if ok else 'FAIL'}] {q}")
    ea = passed / total if total else 0.0
    print(f"  -> {passed}/{total} = {ea:.1%}")

    assert ea >= _EA_FLOOR, f"Execution Accuracy {ea:.1%} below floor {_EA_FLOOR:.0%}"
