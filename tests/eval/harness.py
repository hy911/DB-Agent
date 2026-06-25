"""Execution-Accuracy comparison helpers (pure).

EA compares the *result set* of the agent's SQL against a gold SQL's result set,
not the SQL strings. We normalize each result to an order-insensitive multiset of
rows, where each row is the sorted tuple of its stringified cell values — so
column aliasing and column/row ordering don't cause false mismatches (a count
aliased `pdx_count` still equals the gold's `n`).
"""

from __future__ import annotations

from collections.abc import Sequence


def normalize_rows(rows: Sequence[dict]) -> list[tuple[str, ...]]:
    return sorted(tuple(sorted(str(v) for v in r.values())) for r in rows)


def rows_match(gold_rows: Sequence[dict], pred_rows: Sequence[dict]) -> bool:
    return normalize_rows(gold_rows) == normalize_rows(pred_rows)
