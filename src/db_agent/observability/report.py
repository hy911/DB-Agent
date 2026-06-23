"""Offline analysis report over the audit log.

`python -m db_agent.observability.report` reads `agent_query_log` from the audit
DB (`Settings.audit_db_dsn`) and prints aggregate health metrics: status mix and
failure rate, retry/attempt distribution, top error messages, per-domain counts,
and latency percentiles. The aggregation is a pure function (`summarize`) over a
list of row dicts so it is unit-testable without a database.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (pct in [0, 100]). None for an empty input."""
    if not values:
        return None
    ordered = sorted(values)
    k = max(1, min(len(ordered), round(pct / 100.0 * len(ordered))))
    return ordered[k - 1]


def summarize(rows: list[dict[str, Any]], *, top_errors: int = 5) -> dict[str, Any]:
    total = len(rows)
    status_counts = Counter(r.get("status") for r in rows)
    attempts = Counter(r.get("attempts") for r in rows)
    domains = Counter(r.get("domain") for r in rows if r.get("domain"))
    error_msgs = Counter(r.get("error") for r in rows if r.get("error"))
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    return {
        "total": total,
        "status": dict(status_counts),
        "failure_rate": (status_counts.get("error", 0) / total) if total else 0.0,
        "attempts": dict(sorted(attempts.items(), key=lambda kv: (kv[0] is None, kv[0]))),
        "by_domain": dict(domains.most_common()),
        "top_errors": error_msgs.most_common(top_errors),
        "latency_ms": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "count": len(latencies),
        },
    }


def format_report(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"total runs: {summary['total']}")
    lines.append(f"failure rate: {summary['failure_rate']:.1%}")
    lines.append("status:")
    for status, n in summary["status"].items():
        lines.append(f"  {status}: {n}")
    lines.append("attempts:")
    for attempts, n in summary["attempts"].items():
        lines.append(f"  {attempts}: {n}")
    lines.append("by domain:")
    for domain, n in summary["by_domain"].items():
        lines.append(f"  {domain}: {n}")
    lat = summary["latency_ms"]
    lines.append(f"latency ms (n={lat['count']}): p50={lat['p50']}, p95={lat['p95']}")
    lines.append("top errors:")
    for msg, n in summary["top_errors"]:
        lines.append(f"  [{n}] {msg}")
    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    import argparse

    from db_agent.config import get_settings
    from db_agent.db.audit import AuditLog

    parser = argparse.ArgumentParser(description="Analyze the agent audit log.")
    parser.add_argument("--top-errors", type=int, default=5)
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.audit_db_dsn is None:
        parser.error("DBAGENT_AUDIT_DB_DSN is not set; nothing to analyze")
    audit = AuditLog(settings)
    audit.open()
    try:
        rows = audit.fetch_records()
    finally:
        audit.close()
    print(format_report(summarize(rows, top_errors=args.top_errors)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
