"""Human-readable replay of recent runs.

`python -m db_agent.observability.review --last 20` prints the most recent runs as
a readable Q&A stream (question → domain → SQL → result sample → answer/status),
reading from whichever sink is configured. Built for eyeballing what colleagues
asked and what the agent answered — and for handing the log to an assistant to
iterate on the agent. `format_runs` is a pure function over row dicts (testable).
"""

from __future__ import annotations

import json
from typing import Any


def _fmt_value(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _format_run(rec: dict[str, Any], *, sample_rows: int) -> str:
    run_id = str(rec.get("run_id") or "")[:8]
    ts = str(rec.get("ts") or "")
    status = rec.get("status") or "?"
    latency = rec.get("latency_ms")
    lat = f"{latency:.0f}ms" if isinstance(latency, (int, float)) else "?"
    lines = [f"══ run {run_id} │ {ts} │ {status} │ {lat} ══"]
    lines.append(f"Q: {rec.get('question', '')}")
    if rec.get("domain"):
        lines.append(f"domain: {rec['domain']}")
    sql = rec.get("sql") or rec.get("raw_sql")
    if sql:
        lines.append("SQL:")
        lines.append(f"  {sql}")
    if rec.get("rowcount") is not None:
        cols = rec.get("columns") or []
        trunc = " (truncated)" if rec.get("truncated") else ""
        lines.append(f"result: {rec['rowcount']} row(s){trunc}, cols={cols}")
        for row in (rec.get("result_sample") or [])[:sample_rows]:
            lines.append(f"  {_fmt_value(row)}")
    if rec.get("answer"):
        lines.append(f"answer: {rec['answer']}")
    if rec.get("clarification"):
        lines.append(f"clarify: {rec['clarification']}")
    if rec.get("error"):
        lines.append(f"error: {rec['error']}")
    return "\n".join(lines)


def format_runs(rows: list[dict[str, Any]], *, last: int = 20, sample_rows: int = 10) -> str:
    ordered = sorted(rows, key=lambda r: str(r.get("ts") or ""))
    recent = ordered[-last:] if last else ordered
    return "\n\n".join(_format_run(r, sample_rows=sample_rows) for r in recent)


def _main(argv: list[str] | None = None) -> int:
    import argparse

    from db_agent.config import get_settings
    from db_agent.observability.source import read_records

    parser = argparse.ArgumentParser(description="Replay recent agent runs as readable Q&A.")
    parser.add_argument("--last", type=int, default=20, help="show the most recent N runs (0=all)")
    parser.add_argument("--sample-rows", type=int, default=10, help="result rows to show per run")
    args = parser.parse_args(argv)

    rows = read_records(get_settings())
    out = format_runs(rows, last=args.last, sample_rows=args.sample_rows)
    print(out if out else "(no runs logged yet)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
