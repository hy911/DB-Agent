# Steer Inferential Statistics to the Vetted Stats Node — Design

**Date:** 2026-06-22
**Status:** Approved (design), pending spec review
**Scope:** Prompt-only change to route inferential statistics through the vetted
`stats` node instead of letting the model hand-roll them in `generate_sql` or the
DuckDB `analyze` step. No graph/structural change, no deterministic guard.

## Problem

Live e2e of stats Phase 2 (2026-06-22) showed a capable model **bypassing the vetted
stats node**: in one run the DuckDB `analyze` step hand-computed an ANOVA F statistic;
in another, `generate_sql` used window functions to compute ANOVA components in SQL.
Both produced correct-looking answers, but they sidestep the audited statistical
implementations (scipy/lifelines) and their assumption caveats — defeating the point
of the `stats/` registry. The `stats` node then sees the work already done and
returns `NONE`.

This is purely a routing/behavior issue, not a correctness or security bug: the
stats output is already validated + sandboxed, and the SQL/DuckDB paths are guarded.
The fix is to steer *which path does inferential statistics*.

## Goal

Inferential statistics — t-test, ANOVA, χ², regression, Kaplan-Meier / log-rank,
any p-value or test statistic — should flow to the `stats` node. Descriptive work
(counts, means, GROUP BY, pivots, correlations, quantiles) stays where it is.

## Changes (3 prompt builders in `src/db_agent/llm/prompts.py`)

1. **`_SQL_SYSTEM` (generate_sql).** Add guidance: fetch the **raw rows** needed; do
   NOT compute inferential test statistics (t / F / χ² / p-values) or implement
   statistical tests in SQL. Plain descriptive aggregation (COUNT / AVG / GROUP BY)
   for descriptive questions remains allowed. When the question asks whether a
   difference is significant, for a p-value, or for a named test (t-test / ANOVA /
   survival), return the raw per-row data needed for that test (e.g. group + value,
   or duration + event + group) and let the system run the test.

2. **`analysis_messages` (analyze / DuckDB).** Add guidance: this step is for
   descriptive reshaping / aggregation / pivot / correlation / quantiles ONLY. Do
   NOT compute inferential statistics or test statistics (t / F / χ² / p-values,
   ANOVA, regression, survival) here. If the question needs a statistical test, reply
   `NONE` and let the dedicated stats step handle it.

3. **`stat_messages` (request_stat).** Light reinforcement: when the question is
   about significance / a p-value / a named test AND the table has the needed
   columns, emit the request rather than defaulting to `NONE`. (Live probing already
   shows it emits correctly on clean grouped data; this just reduces over-conservative
   NONEs.)

No other source changes. `agent_llm.py`, the nodes, and the graph are untouched.

## Non-goals

- No graph or structural change (no reordering, no new node).
- No deterministic guard that inspects DuckDB/SQL for statistics — prompt-only. The
  stats output is already validated + sandboxed, so correctness/security are not at
  risk; a guard would risk false-positives on legitimate descriptive aggregation.
- Descriptive aggregation stays allowed in both `generate_sql` and `analyze`.

## Testing

- **Prompt builders are pure → unit tests** in `tests/test_llm_prompts.py`: assert the
  new guidance phrases are present in the `_SQL_SYSTEM` system message, the
  `analysis_messages` system message, and the `stat_messages` system message (e.g.
  the SQL prompt mentions not computing p-values / test statistics; the analysis
  prompt mentions returning NONE for statistical tests).
- **Full offline suite stays green** — the chain/observability/api tests script LLM
  output directly (NONE / fixed strings), so they do not depend on prompt wording.
- **Live re-verification (best-effort, gateway now healthy):** the ANOVA-style
  question that previously hand-rolled F in SQL/DuckDB should now fetch raw rows,
  `analyze` returns NONE, and the `stats` node fires the vetted test. Report the
  replica SQL + stat request + answer.

## Risks

- **Prompt steering is probabilistic, not a guarantee.** A model may still
  occasionally compute statistics in SQL. That is acceptable: the answer remains
  correct and guarded; this change shifts the default, it does not enforce it. (A
  deterministic guard is a deliberately deferred follow-up if steering proves
  insufficient.)
- **Over-steering `generate_sql`** could make it avoid legitimate descriptive
  aggregation. Mitigated by explicitly preserving descriptive COUNT/AVG/GROUP BY in
  the wording.
