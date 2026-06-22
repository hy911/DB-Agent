# Steer Inferential Statistics to the Stats Node — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Steer the LLM (via three prompt builders) so inferential statistics flow to the vetted `stats` node instead of being hand-rolled in `generate_sql` or the DuckDB `analyze` step.

**Architecture:** Prompt-only edits to `src/db_agent/llm/prompts.py` — `_SQL_SYSTEM`, `analysis_messages`, `stat_messages`. No graph/structural change, no deterministic guard. Verified by string-presence unit tests + the existing offline suite + a best-effort live re-run.

**Tech Stack:** Python, pytest, ruff, uv.

**Reference spec:** `docs/superpowers/specs/2026-06-22-stats-routing-prompts-design.md`

---

## Task 1: Steer the three prompts away from hand-rolled inferential statistics

**Files:**
- Modify: `src/db_agent/llm/prompts.py` (`_SQL_SYSTEM` constant; `analysis_messages`; `stat_messages`)
- Test: `tests/test_llm_prompts.py`, `tests/test_llm_stats.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_llm_prompts.py`:

```python
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

    msgs = analysis_messages("is the difference significant?", ["group_id", "tv"], "group_id, tv\nA, 1")
    system = msgs[0]["content"].lower()
    assert "p-value" in system or "p value" in system  # names what NOT to compute here
    assert "none" in system  # tells it to defer (reply NONE) for a statistical test
```

Append to `tests/test_llm_stats.py`:

```python
def test_stat_messages_encourage_emitting_when_significance_asked():
    from db_agent.llm.prompts import stat_messages

    msgs = stat_messages("is A vs B significant?", ["group_id", "tv"], "group_id, tv\nA, 1", catalog_text())
    system = msgs[0]["content"].lower()
    assert "significan" in system  # nudges emitting a test when significance is asked
    assert "p-value" in system or "p value" in system
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_stats.py -q`
Expected: the 3 new tests FAIL (phrases not yet present); existing tests pass.

- [ ] **Step 3: Edit `_SQL_SYSTEM`**

In `src/db_agent/llm/prompts.py`, replace the `_SQL_SYSTEM` constant:

```python
_SQL_SYSTEM = (
    "You write exactly one read-only PostgreSQL SELECT for a mouse tumor-model "
    "database. "
    "Use only the tables and columns in the provided schema context. Do not write "
    "INSERT/UPDATE/DELETE/DDL. "
    "Plain descriptive aggregation (COUNT/AVG/SUM/GROUP BY) is fine for descriptive "
    "questions. But do NOT compute inferential statistics or test statistics "
    "(t / F / chi-square / p-values) or implement a statistical test in SQL. When the "
    "question asks whether a difference is significant, for a p-value, or for a named "
    "test (t-test / ANOVA / survival), instead return the raw per-row data that test "
    "needs (e.g. the group column and the value column, or duration + event + group) "
    "and let the system run the test. "
    "Return only the SQL, with no prose and no code fences."
)
```

- [ ] **Step 4: Edit `analysis_messages`**

In `src/db_agent/llm/prompts.py`, in `analysis_messages`, replace the `system` string:

```python
    system = (
        "You decide whether answering the user's question needs post-processing of "
        "an already-fetched result set, and if so write ONE DuckDB SQL SELECT to do "
        "it. The result set is a single in-memory table named `result` with the "
        "given columns. This step is for DESCRIPTIVE post-processing only — "
        "aggregation / reshaping / pivot / correlation / quantiles. Do NOT compute "
        "inferential statistics or test statistics here (t / F / chi-square / "
        "p-values, ANOVA, regression, survival): if the question needs a statistical "
        "test, reply with the single word NONE and let the dedicated stats step run "
        "it. If the rows already answer the question as-is, also reply NONE. "
        "Otherwise reply with exactly one SELECT over `result` (descriptive "
        "aggregation / pivot / correlation / quantiles), using only the `result` "
        "table and no file or external functions. Reply with the SQL or NONE and "
        "nothing else."
    )
```

- [ ] **Step 5: Edit `stat_messages`**

In `src/db_agent/llm/prompts.py`, in `stat_messages`, replace the `system` string:

```python
    system = (
        "You decide whether answering the question needs a statistical test over an "
        "already-fetched result table named `result`. If so, pick ONE test from the "
        "catalog and map its parameters to the table's columns. Available tests:\n"
        f"{catalog}\n\n"
        "If the question asks whether a difference is significant, for a p-value, or "
        "for a named test, AND the table has the columns that test needs, you SHOULD "
        "emit the request rather than declining. Reply with exactly one JSON object: "
        '{"function": <name>, "params": {<param>: <column-name-or-scalar>, ...}}. '
        "Map column-typed params to column names from the table; use only those "
        "columns. If no statistical test is needed, reply with the single word NONE. "
        "Reply with the JSON object or NONE and nothing else."
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_stats.py -q`
Expected: all pass (existing + 3 new).

- [ ] **Step 7: Full offline suite + ruff**

Run: `uv run pytest -q`
Expected: all pass, 9 deselected (chain/api/observability tests script LLM output, so unaffected by wording).

Run: `uv run ruff check src tests && uv run ruff format src tests`
Expected: clean; commit any reformatting.

- [ ] **Step 8: Commit**

```bash
git add src/db_agent/llm/prompts.py tests/test_llm_prompts.py tests/test_llm_stats.py
git commit -m "steer inferential stats to the vetted stats node (prompts)"
```

- [ ] **Step 9: Best-effort live re-verification (gateway healthy)**

Run a live query that previously hand-rolled stats, e.g. "对每个药物比较其各实验分组的 tgi_tv 是否有显著差异(用方差分析)" through `run_agent` with real deps (`.env`). Expected now: `generate_sql` fetches raw rows, `analysis_sql` is None (analyze defers), and `stat_request` is a vetted test (or, if the grouping is genuinely single-group, a clear NONE with an honest answer — not a hand-rolled F). Report replica SQL + analysis_sql + stat_request + answer. If the gateway 504s transiently, retry a few times; this step is best-effort and does not block the commit.

---

## Notes for the implementer

- Prompt strings are the only source change. Keep `from __future__ import annotations` headers intact; ruff stays on `py311`.
- The string-presence tests are intentionally loose (substring checks) so minor wording tweaks don't break them — they assert the *intent* (forbid p-values in SQL/analyze, nudge the stats node) is present, not exact phrasing.
- Do not add a deterministic guard or change the graph — that is an explicitly deferred follow-up per the spec.
