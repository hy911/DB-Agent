from __future__ import annotations

from db_agent.llm.prompts import answer_messages, route_messages, sql_messages


def test_route_messages_mention_efficacy_and_clarify():
    msgs = route_messages("how many models?")
    assert msgs[0]["role"] == "system"
    text = " ".join(m["content"] for m in msgs).lower()
    assert "efficacy" in text
    assert "clarify" in text
    assert "how many models?" in msgs[-1]["content"]


def test_sql_messages_include_context_and_question():
    msgs = sql_messages("list drugs", "TABLE model_efficacy_info(...)")
    joined = " ".join(m["content"] for m in msgs)
    assert "TABLE model_efficacy_info(...)" in joined
    assert "list drugs" in joined


def test_sql_messages_include_prior_error_on_retry():
    msgs = sql_messages("list drugs", "ctx", prior_error="column foo does not exist")
    joined = " ".join(m["content"] for m in msgs)
    assert "column foo does not exist" in joined


def test_sql_messages_omit_error_marker_when_none():
    msgs = sql_messages("list drugs", "ctx")
    joined = " ".join(m["content"] for m in msgs)
    assert "Previous attempt failed" not in joined


def test_answer_messages_include_sql_and_preview():
    msgs = answer_messages("how many?", "SELECT 1", "(0 rows)")
    joined = " ".join(m["content"] for m in msgs)
    assert "SELECT 1" in joined
    assert "(0 rows)" in joined
