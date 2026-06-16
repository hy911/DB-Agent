"""Big-table EXPLAIN gate (pure).

When sql/ flagged a big-table scan, db/ runs ``EXPLAIN (FORMAT JSON)`` (no
ANALYZE, so the query never executes) and passes the plan here. We refuse a plan
that *sequentially* scans a big table. A parallel sequential scan still reports
``Node Type == "Seq Scan"`` (parallelism is expressed by an enclosing ``Gather``),
so the single node-type check covers it.
"""

from __future__ import annotations

from collections.abc import Iterator

from db_agent.sql.errors import GuardError


def _root(plan: object) -> dict | None:
    """Normalize an EXPLAIN (FORMAT JSON) payload to its root plan node."""
    if isinstance(plan, list):
        return _root(plan[0]) if plan else None
    if isinstance(plan, dict):
        if "Plan" in plan:
            return plan["Plan"]
        if "Node Type" in plan:
            return plan
    return None


def _walk(node: dict) -> Iterator[dict]:
    yield node
    for child in node.get("Plans", []) or []:
        yield from _walk(child)


def seq_scanned_big_tables(plan: object, big_tables: frozenset[str]) -> list[str]:
    """Return big-table relation names reached by a Seq Scan in this plan."""
    root = _root(plan)
    if root is None:
        return []
    return [
        node["Relation Name"]
        for node in _walk(root)
        if node.get("Node Type") == "Seq Scan" and node.get("Relation Name") in big_tables
    ]


def evaluate_explain(plan: object, big_tables: frozenset[str]) -> None:
    """Raise a fatal GuardError if the plan sequentially scans a big table."""
    hits = seq_scanned_big_tables(plan, big_tables)
    if hits:
        names = ", ".join(sorted(set(hits)))
        raise GuardError(
            "big_table_scan",
            f"sequential scan on big table(s) {names} is not allowed; "
            "add a model_uuid/gene_symbol filter",
            retryable=False,
        )
