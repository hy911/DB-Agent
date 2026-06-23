from __future__ import annotations

from db_agent.observability.report import _percentile, format_report, summarize


def _row(status, attempts, domain, error, latency_ms):
    return {
        "status": status,
        "attempts": attempts,
        "domain": domain,
        "error": error,
        "latency_ms": latency_ms,
    }


def _rows():
    return [
        _row("answered", 1, "efficacy", None, 100.0),
        _row("answered", 2, "efficacy", None, 200.0),
        _row("error", 3, "modeling", "boom", 300.0),
        _row("clarify", 0, None, None, None),
        _row("error", 3, "modeling", "boom", 400.0),
    ]


def test_summarize_counts_and_failure_rate():
    s = summarize(_rows())
    assert s["total"] == 5
    assert s["status"] == {"answered": 2, "error": 2, "clarify": 1}
    assert s["failure_rate"] == 2 / 5
    assert s["by_domain"] == {"modeling": 2, "efficacy": 2}
    assert s["attempts"] == {0: 1, 1: 1, 2: 1, 3: 2}


def test_summarize_top_errors_and_latency():
    s = summarize(_rows())
    assert s["top_errors"] == [("boom", 2)]
    assert s["latency_ms"]["count"] == 4
    assert s["latency_ms"]["p50"] == 200.0
    assert s["latency_ms"]["p95"] == 400.0


def test_summarize_empty():
    s = summarize([])
    assert s["total"] == 0 and s["failure_rate"] == 0.0
    assert s["latency_ms"]["p50"] is None


def test_percentile_basic():
    assert _percentile([], 50) is None
    assert _percentile([10.0], 50) == 10.0
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0


def test_format_report_is_text():
    out = format_report(summarize(_rows()))
    assert "total runs: 5" in out
    assert "failure rate: 40.0%" in out
    assert "boom" in out
