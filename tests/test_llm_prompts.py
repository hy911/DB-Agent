from __future__ import annotations

from db_agent.config import Settings
from db_agent.llm.prompts import answer_messages, route_messages, sql_messages
from db_agent.semantic import load_semantic_layer

DOMAINS = load_semantic_layer(Settings(_env_file=None).semantic_layer_path).routable_domains()


def test_route_messages_lists_domains_and_clarify():
    msgs = route_messages("how many models?", DOMAINS)
    assert msgs[0]["role"] == "system"
    text = " ".join(m["content"] for m in msgs).lower()
    assert "efficacy" in text and "expression" in text
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


def test_extract_genes_messages_include_question():
    from db_agent.llm.prompts import extract_genes_messages

    msgs = extract_genes_messages("expression of p53?")
    assert msgs[0]["role"] == "system"
    assert "gene" in " ".join(m["content"] for m in msgs).lower()
    assert "expression of p53?" in msgs[-1]["content"]


def test_sql_system_prompt_is_domain_neutral():
    msgs = sql_messages("q", "ctx")
    system = msgs[0]["content"].lower()
    assert "efficacy domain" not in system
    assert "select" in system  # still instructs a read-only SELECT


def test_sql_system_prompt_states_failure_avoidance_rules():
    system = sql_messages("q", "ctx")[0]["content"].lower()
    assert "alias" in system  # qualify columns to avoid ambiguity
    assert "true/false" in system or "boolean" in system  # varchar-not-boolean rule
    assert "ilike" in system  # fuzzy match for off-vocabulary categories
    assert "group by" in system  # all non-aggregated columns must be grouped


def test_answer_system_prompt_forbids_long_enumeration():
    from db_agent.llm.prompts import answer_messages

    system = answer_messages("q", "s", "(0 rows)")[0]["content"].lower()
    assert "enumerate" in system or "list" in system
    assert "table" in system  # points the user to the table for the full result


def test_extract_genes_prompt_excludes_model_names():
    from db_agent.llm.prompts import extract_genes_messages

    system = extract_genes_messages("EGFR in MDA-MB-468?")[0]["content"]
    low = system.lower()
    assert "pbmc" in low  # explicitly names model-identifier patterns to skip
    assert "not genes" in low or "not a gene" in low


def test_analysis_messages_include_columns_and_question():
    from db_agent.llm.prompts import analysis_messages

    msgs = analysis_messages("avg per group?", ["group_id", "tv"], "group_id, tv\nA, 1")
    joined = " ".join(m["content"] for m in msgs)
    assert "result" in joined.lower()
    assert "group_id" in joined
    assert "avg per group?" in joined


def test_sql_system_steers_inferential_stats_to_system():
    msgs = sql_messages("q", "ctx")
    system = msgs[0]["content"].lower()
    # must forbid computing test statistics / p-values in SQL ...
    assert "p-value" in system or "p value" in system
    assert "raw" in system  # ... and ask for the raw rows instead
    # ... while still allowing plain descriptive aggregation
    assert "group by" in system or "aggregation" in system


def test_analysis_messages_defer_inferential_stats():
    from db_agent.llm.prompts import analysis_messages

    msgs = analysis_messages(
        "is the difference significant?", ["group_id", "tv"], "group_id, tv\nA, 1"
    )
    system = msgs[0]["content"].lower()
    assert "p-value" in system or "p value" in system  # names what NOT to compute here
    assert "none" in system  # tells it to defer (reply NONE) for a statistical test


def test_sql_messages_include_examples_block():
    from db_agent.examples.model import Example
    from db_agent.llm.prompts import sql_messages

    examples = [Example("how many models?", "SELECT count(*) FROM model_efficacy_info", "efficacy")]
    msgs = sql_messages("list drugs", "ctx", examples=examples)
    joined = " ".join(m["content"] for m in msgs)
    assert "how many models?" in joined
    assert "SELECT count(*) FROM model_efficacy_info" in joined


def test_sql_messages_no_examples_block_when_empty():
    from db_agent.llm.prompts import sql_messages

    msgs = sql_messages("list drugs", "ctx", examples=[])
    joined = " ".join(m["content"] for m in msgs)
    assert "similar past questions" not in joined.lower()
