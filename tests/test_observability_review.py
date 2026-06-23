from __future__ import annotations

from db_agent.observability.review import format_runs


def _runs():
    return [
        {
            "run_id": "bbbbbbbb1111",
            "ts": "2026-06-23T10:00:00",
            "status": "answered",
            "latency_ms": 142.0,
            "question": "how many BD drugs?",
            "domain": "efficacy",
            "sql": "SELECT count(*) FROM model_efficacy_info WHERE for_bd = 'yes'",
            "rowcount": 1,
            "columns": ["n"],
            "truncated": False,
            "result_sample": [{"n": 42}],
            "answer": "There are 42.",
        },
        {
            "run_id": "aaaaaaaa0000",
            "ts": "2026-06-23T09:00:00",
            "status": "error",
            "latency_ms": 12.0,
            "question": "broken one",
            "error": "boom",
        },
    ]


def test_format_runs_is_chronological_and_readable():
    out = format_runs(_runs(), last=20)
    # older (09:00) appears before newer (10:00)
    assert out.index("broken one") < out.index("how many BD drugs?")
    assert "domain: efficacy" in out
    assert '{"n": 42}' in out
    assert "answer: There are 42." in out
    assert "error: boom" in out


def test_format_runs_last_n_limits():
    out = format_runs(_runs(), last=1)
    # only the most recent (10:00) survives
    assert "how many BD drugs?" in out
    assert "broken one" not in out


def test_format_runs_empty():
    assert format_runs([]) == ""


def test_format_runs_sample_rows_cap():
    rows = [
        {
            "run_id": "c",
            "ts": "t",
            "status": "answered",
            "question": "q",
            "rowcount": 3,
            "columns": ["n"],
            "truncated": False,
            "result_sample": [{"n": 1}, {"n": 2}, {"n": 3}],
        }
    ]
    out = format_runs(rows, sample_rows=1)
    assert '{"n": 1}' in out
    assert '{"n": 2}' not in out
