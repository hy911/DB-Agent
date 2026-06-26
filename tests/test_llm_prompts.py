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


def test_route_messages_asks_for_all_applicable_domains():
    system = route_messages("Trp53 相关数据", DOMAINS)[0]["content"].lower()
    assert "comma-separated" in system  # list every applicable domain
    # clarify is reserved for greeting/meta/out-of-scope, NOT "which data type?"
    assert "never to ask which data type" in system


def test_multi_intro_messages_carries_counts_and_language():
    from db_agent.llm.prompts import multi_intro_messages

    msgs = multi_intro_messages("Trp53 相关数据", [("基因突变", 13), ("基因表达", 1)])
    joined = " ".join(m["content"] for m in msgs)
    assert "13" in joined and "基因突变" in joined
    assert "same language" in joined.lower()  # answer in the question's language


def test_route_messages_has_model_spine_domain_and_same_language():
    system = route_messages("q", DOMAINS)[0]["content"].lower()
    assert "model" in system and "rnaseq_id" in system  # spine domain described
    assert "same language" in system  # clarify must match the question's language


def test_sql_system_steers_genes_without_gene_info_join():
    system = sql_messages("q", "ctx")[0]["content"]
    low = system.lower()
    assert "do not join gene_info" in low or "not join gene_info" in low
    assert '"symbol"' in low  # double-quote rule for the capital-S column
    assert "rnaseq_data" in low  # warns against inventing this table


def test_route_messages_routes_by_measurement_not_model_attrs():
    system = route_messages("q", DOMAINS)[0]["content"].lower()
    assert "expression" in system and "mutation" in system
    # model attributes (CDX/cancer type) must not drive routing
    assert "cdx" in system or "model type" in system
    assert "never route on them" in system or "available in every domain" in system


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


def test_answer_messages_states_authoritative_count():
    msgs = answer_messages("list models", "SELECT ...", "a\nb", rowcount=95, truncated=False)
    joined = " ".join(m["content"] for m in msgs)
    assert "95" in joined
    assert "authoritative" in joined.lower()


def test_answer_messages_count_phrasing_when_truncated():
    msgs = answer_messages("list models", "SELECT ...", "a\nb", rowcount=1000, truncated=True)
    joined = " ".join(m["content"] for m in msgs)
    assert "at least 1000" in joined


def test_answer_system_uses_given_count_and_matches_language():
    system = answer_messages("q", "s", "(0 rows)")[0]["content"].lower()
    assert "authoritative" in system  # must use the given count, not its own
    assert "same language" in system  # answer in the question's language


def test_answer_system_forbids_excluding_rows_from_count():
    # the headline total must equal the row count even for control/vehicle rows
    # (the cause of "阳性药数据" returning 35/29/0 instead of the real 48)
    system = answer_messages("q", "s", "(0 rows)")[0]["content"].lower()
    assert "exclude" in system or "subset" in system
    assert "control" in system or "vehicle" in system


def test_answer_messages_count_line_forbids_exclusion():
    msgs = answer_messages("list", "SELECT ...", "a\nb", rowcount=48, truncated=False)
    joined = " ".join(m["content"] for m in msgs).lower()
    assert "48" in joined
    assert "exclude" in joined  # control/vehicle rows still count


def test_answer_messages_count_prefixed_tells_llm_not_to_restate_total():
    # when the system already prepended the count, the LLM must not state its own total
    msgs = answer_messages("list", "SELECT ...", "a\nb", rowcount=48, count_prefixed=True)
    joined = " ".join(m["content"] for m in msgs).lower()
    assert "already been shown" in joined
    assert "do not state any record count" in joined


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
    # closed-vocabulary adherence: map to the closest listed value, don't invent
    assert "closest" in system and "never invent" in system


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
