# Mutation Domain Design

**Date:** 2026-06-18
**Status:** Approved (architecture section), pending spec review
**Builds on:** the data-driven multi-domain routing + gene-resolution wiring already
shipped for the `expression` domain.

## Goal

Add the `mutation` domain — somatic mutation data for mouse tumor models — to the
agent, so questions like "which models carry a TP53 mutation?", "what mutations
does model X have?", and "is the EGFR L858R mutation oncogenic?" route to it,
resolve gene names deterministically, generate guarded SQL, and answer.

## Key architectural claim

The domain itself is expected to be a **pure `semantic_layer.yaml` addition +
tests + live verification, with zero Python source changes** (the one optional
prompt reword in "Minor cleanup" is cosmetic and separable). Every mechanism the
domain needs is already data-driven and was proven by the `expression` domain:

- **Routing** — `SemanticLayer.routable_domains()` returns every non-reference
  domain with ≥1 defined table. Adding mutation's tables makes it auto-routable
  (`{efficacy, expression, mutation}`); the router prompt lists it automatically.
- **Gene resolution** — `is_gene_bearing("mutation")` is `True` because the main
  table has a `gene_symbol` column, so `route → extract_genes → resolve_genes`
  runs automatically and injects canonical symbols into the SQL-gen context.
- **Big-table guard** — flagging the main table `big_table: true` makes the
  validator's EXPLAIN gate reject any scan lacking a `model_uuid`/`gene_symbol`
  filter, exactly as for `model_ccle_expression_data`.
- **Permissions** — mutation is **not** `access_controlled` (matches the existing
  YAML forward-declaration and CLAUDE.md's policy: only efficacy filters
  `for_bd`). The permission injector is a no-op for non-controlled domains, as
  already true for expression.
- **Context assembly** — `_render_context` renders `tables_in_domain(domain)` +
  reference tables, so tagging `oncokb` with `domain: mutation` feeds it only for
  mutation questions.

If any of these turns out to need a code change during implementation, that is a
signal to stop and re-examine — the design assumes none are needed.

## Tables in scope

Columns are taken from the **live DB `information_schema`**, NOT `models.py`,
because the two have drifted (e.g. `model_mutation_feature.exon_rank` and `id`
exist in `models.py` but not in the real table). `models.py` is authoritative for
*which* tables exist; the live DB is authoritative for *columns*.

### `model_ccle_mutation_data` — main table (in `mutation`)

- `big_table: true` (~5.47M rows, live-estimated via `pg_class.reltuples`).
- `join_to_hub: [model_uuid]` (joins the spine `model_desc_info`).
- gene-bearing (`gene_symbol` joins `gene_info."Symbol"`).
- Columns to expose (with Chinese descriptions, matching existing YAML style):
  `model_uuid, model_id, gene_symbol, species, mutation_id, variant_classification,
  hgvsc, hgvsp_short, dbsnp_rs, sift, polyphen, hotspot_mutation, data_source`.
  (`model_name` exists in the DB but is redundant with `model_desc_info.model_name`;
  omit to keep context lean.)

### `oncokb` — clinical annotation (in `mutation`)

- Small (~24.6K rows); no big-table guard.
- Not keyed by `model_uuid` — it is a gene/mutation-level annotation table. It is
  tagged `domain: mutation` (NOT `reference`) so it is fed only for mutation
  questions, never to efficacy/expression.
- Columns to expose: `gene, mutant, oncogenic, mutation_effect, level,
  level_associated_cancer_types, citations`. Omit the `alterations`/`drugs` jsonb
  columns to avoid bloating context.
- Relationship (declared, no real FK): `oncokb.gene` → `gene_info."Symbol"`; the
  LLM joins `oncokb` to the main table on `gene` + the amino-acid change when a
  question needs actionability. We only supply the schema; SQL is the model's job.

## Data flow (all reused, no new nodes)

```
route → mutation
  → extract_genes (LLM lists gene mentions)
  → resolve_genes (deterministic, case-sensitive; ambiguous/unknown → clarify)
  → assemble_context (inject canonical symbol map + the two tables' schema)
  → generate_sql (qwen-code)
  → guard (sqlglot validate; big-table EXPLAIN gate; no permission injection)
  → execute (read replica)
  → answer
```

Covered question shapes:
1. "which models carry a TP53 mutation?" → filter `gene_symbol = 'TP53'`
   (gene resolved first); gate satisfied by the gene_symbol filter.
2. "what mutations does model X have?" → filter `model_uuid = '...'`; gate
   satisfied by the model_uuid filter.
3. "is the EGFR L858R mutation oncogenic?" → join `oncokb` on gene + mutation.

## Out of scope (deferred, not built)

- `model_mutation_feature` — `mutation_id → aa_mutation` reference; the main table
  already carries `hgvsp_short`/`variant_classification`, so it is redundant for
  the target questions. Add later only if a real query needs canonical
  amino-acid names.
- `model_mutation_data` (~5.1M rows, rnaseq-keyed raw VEP dump) and
  `ccl_mutation_data` (cell-line, not model-keyed) — neither hangs off the
  `model_uuid` spine cleanly; excluded.
- The `modeling` domain — the other forward-declared domain, deferred to its own
  spec/plan (it is access-controlled with a large efficacy-parallel detail-table
  set and is a bigger piece of work).

## Testing

- **Offline (faked LLM + resolver, no DB):**
  - `routable_domains()` now yields `{efficacy, expression, mutation}`.
  - `is_gene_bearing("mutation") is True`.
  - Routing a mutation question sets `domain == "mutation"`.
  - `assemble_context` for mutation renders both tables, injects the resolved-gene
    map, and emits **no** permission note (not access-controlled).
  - End-to-end (fake LLM streams route→extract→sql→answer, fake resolver maps
    p53→TP53): resolves the gene, runs, answers; generated SQL contains no
    `for_bd`.
  - The main table is recognised as a guarded big table (validator flags
    `needs_explain`).
- **Live (real LLM + DB, `-m integration` style one-off script):**
  - "Which models carry a TP53 mutation?" → `answered`, SQL filters
    `gene_symbol = 'TP53'`, EXPLAIN gate passes.
  - "What mutations does model `<uuid>` have?" → `answered`, SQL filters
    `model_uuid`.

## Minor cleanup (bundled, optional)

`llm/prompts.py` `_SQL_SYSTEM` hardcodes "for the efficacy domain". It is harmless
(the real schema is supplied via context, proven by the working expression
domain), but since we are adding a third domain, reword it to be domain-neutral
(e.g. "for a mouse tumor-model database"). Tiny, low-risk; include as the last
task. If it causes any test churn beyond a trivial string assertion, drop it.

## Risks

- **EXPLAIN gate vs. indexes:** the gate passes a query only if the plan avoids a
  big seq scan given a `model_uuid`/`gene_symbol` filter. If `model_ccle_mutation_data`
  lacks an index on those columns, even a filtered query could seq-scan and be
  rejected. Verify during live testing; if so, that is an ops/index finding to
  report (not a code change here).
- **Drift:** columns were pinned to the live DB on 2026-06-18; if the DB changes,
  re-pin.
