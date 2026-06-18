# Design: deterministic gene resolution + in-flow wiring (resolve_gene)

Date: 2026-06-17
Status: Approved (brainstorming) — ready for implementation plans
Scope: Phase 2, sub-project 2. Build the deterministic `resolve_gene` lookup tool
and wire it into the gene-bearing question flow so users can ask by gene synonym /
alias / near-miss spelling, with the canonical symbol resolved deterministically
(never guessed by the LLM — fixed decision #5).

## Goal

Let a question like "p53 expression in model X" resolve `p53` to the canonical
gene symbol deterministically before SQL is generated. The LLM only **spots
candidate gene mentions**; a deterministic DB-backed tool maps each to the
official `gene_info."Symbol"`. Unique → injected into the SQL-gen context;
ambiguous/unknown → the chain clarifies.

## Environment (verified 2026-06-17, live)

- DB is now **PostgreSQL 16.3** (`db_dev`); `.env` updated. **`pg_trgm` is
  installed** and `similarity()` works, so fuzzy matching is available.
- `gene_info` (137,642 rows): the canonical column is **`"Symbol"`** (capital S —
  the `semantic_layer.yaml` declaration `gene_info.symbol` is wrong and is
  corrected here). `gene_synonyms` (287,028 rows): columns `synonym`,
  `gene_symbol`, `species`.
- Both gene tables carry a `species` column, and **letter case encodes species**:
  human symbols are upper (`EGFR`, `TP53`), mouse are title-case (`Egfr`, `Trp53`);
  synonyms follow the same convention (`P53 → TP53` human, `p53 → Trp53` mouse).
  Matching is therefore **case-sensitive** — a case-insensitive match would
  collapse `EGFR`/`Egfr` and make nearly everything ambiguous (verified against
  the live data).
- `model_ccle_expression_data` is ~36M rows (the big table); the EXPLAIN gate
  already protects it.

## Confirmed decisions (brainstorming, 2026-06-17)

- **Fuzzy never auto-resolves** — a `similarity()` match is only ever a candidate
  for clarification, never silently chosen (honors "never guess").
- **Cross-species / multiple exact matches → ambiguous** → clarify, listing the
  candidates with their species. Filtering candidates to those actually present
  in the queried table is a deferred optimization (not built now).
- **Gene-bearing domain** is detected data-drivenly: a domain whose tables include
  the `gene_key` column (`gene_symbol`). Currently only `expression`; `mutation`
  qualifies automatically once its tables are added.
- Two implementation plans: **Plan A** (the `resolve_gene` tool), **Plan B** (the
  graph wiring).

---

## Plan A — the `resolve_gene` tool

### Data types (`db/gene_resolver.py`)

```python
@dataclass(frozen=True)
class GeneMatch:
    symbol: str            # canonical gene_info."Symbol"
    species: str | None
    via: str               # "symbol_exact" | "synonym_exact" | "fuzzy"
    score: float           # 1.0 for exact; similarity() for fuzzy

@dataclass(frozen=True)
class GeneResolution:
    query: str             # the input name
    status: str            # "resolved" | "ambiguous" | "unknown"
    symbol: str | None     # set only when status == "resolved"
    candidates: list[GeneMatch]
```

### Decision rule (pure, offline-testable)

`_decide(exact: list[GeneMatch], fuzzy: list[GeneMatch]) -> GeneResolution`:

1. If `exact` resolves to **exactly one** distinct canonical `symbol` →
   `resolved` (symbol set).
2. If `exact` has **more than one** distinct symbol (e.g. cross-species) →
   `ambiguous` with those candidates.
3. Else if `fuzzy` is non-empty → `ambiguous` with the fuzzy candidates (sorted by
   score desc). **Fuzzy is never auto-resolved.**
4. Else → `unknown` (no candidates).

### I/O (`resolve_gene`)

`resolve_gene(replica, name, *, fuzzy_threshold=0.4, limit=5) -> GeneResolution`:
- Runs **parameterized** read-only queries (the gene name is always a bound
  parameter, never interpolated):
  - exact symbol (case-sensitive): `SELECT "Symbol", species FROM gene_info WHERE "Symbol" = %s`
  - exact synonym (case-sensitive): `SELECT gs.gene_symbol AS symbol, gs.species FROM gene_synonyms gs WHERE gs.synonym = %s`
  - fuzzy (only if no exact): `SELECT "Symbol", species, similarity("Symbol", %s) AS sim FROM gene_info WHERE similarity("Symbol", %s) > %s ORDER BY sim DESC LIMIT %s`
    (uses the `similarity()` function, not the `%` operator, to avoid psycopg
    placeholder clashes).
- Maps rows into `GeneMatch` and calls `_decide`.

### New `ReadReplica` helper

`resolve_gene` needs parameterized trusted queries. Add
`ReadReplica.fetch(sql, params=()) -> list[dict]` — a read-only, parameterized
fetch for **trusted internal** queries (distinct from `execute`, which secures and
runs LLM-generated SQL). It uses the same pool/read-only connection. No EXPLAIN
gate, no securing — the SQL is hand-written and the value is bound.

### Semantic-layer correction

Fix `gene_info`'s column in `semantic_layer.yaml`: `symbol` → `Symbol` (matching
the real DB), and update the `relationships` / `lookup_tools` references
accordingly. This is a data fix in the YAML; the loader is unchanged.

### Plan A testing

- Offline (`_decide`): unique exact → resolved; two exact symbols → ambiguous;
  no exact + fuzzy → ambiguous (sorted); nothing → unknown.
- Integration (`-m integration`, real DB): `resolve_gene` for `EGFR` (case-exact
  → resolved, symbol `EGFR`), `egfr` (no case-exact → fuzzy candidates →
  ambiguous), and `zzzznotagene` (unknown). Also a `ReadReplica.fetch`
  parameterized smoke. (Verified against live data: `EGFR`→`EGFR`, `Egfr`→`Egfr`,
  `p53`→`Trp53`, `P53`→`TP53` all resolve case-sensitively.)

---

## Plan B — wire resolution into the question flow

### Gene-bearing domain detection

Add `SemanticLayer.is_gene_bearing(domain) -> bool`: true if any table in the
domain has a column named `self.gene_key` (`gene_symbol`). Pure, data-driven.

### New state fields (`AgentState`)

- `extracted_genes: list[str]` — gene mentions the LLM spotted.
- `resolved_genes: dict[str, str]` — `{input_name: canonical_symbol}` for the
  resolved ones (injected into context).

### New LLM task + prompt

- `prompts.extract_genes_messages(question)` and
  `agent_llm.extract_genes(client, settings, question) -> list[str]` — the model
  lists gene mentions (comma-separated, or empty). Uses `model_fast`. The model
  only spots strings; it does **not** decide canonical names.

### New nodes (`graph/nodes.py`)

- `extract_genes_node`: `{"extracted_genes": extract_genes(...)}`.
- `resolve_genes_node`: for each extracted name, call the injected resolver
  `deps.resolve_gene(deps.replica, name)` (see the dependency note below). If
  **all** are `resolved` (or none were extracted) → store
  `resolved_genes` and continue. If **any** is `ambiguous`/`unknown` → set
  `status="clarify"` with a clarification listing the candidates (or "unknown
  gene"), short-circuiting like the route clarify.

### Wiring (`graph/build.py`)

After `route`, a conditional edge on the chosen domain:
- gene-bearing domain → `extract_genes → resolve_genes → (clarify END | assemble_context)`.
- otherwise → `assemble_context` (efficacy path unchanged).

`_render_context(deps, domain, resolved_genes)` appends, when `resolved_genes` is
non-empty, a line like `Resolved gene names: p53 -> TP53, ...` so the model uses
the canonical symbols.

### Dependency note

`resolve_genes_node` calls `resolve_gene(deps.replica, ...)`. In offline tests the
`replica` fake must therefore also answer the resolver's `fetch` calls — so the
graph fakes gain a tiny `fetch` method returning scripted rows (or the node takes
an injected resolver function for clean offline testing). The plan uses an
**injected resolver** on `Deps` (`Deps.resolve_gene`, defaulting to the real
`resolve_gene`) so graph tests inject a fake resolver and never hit a DB.

### Plan B testing

- Offline: `is_gene_bearing` (expression true, efficacy false); `extract_genes`
  parsing; `resolve_genes_node` (all-resolved → context injection & continue; any
  ambiguous → clarify); full-graph expression run where `p53` resolves to a
  canonical symbol and the secured SQL uses it; an ambiguous-gene run that ends in
  `clarify`; efficacy regression (skips the gene nodes entirely).
- Integration: an end-to-end expression question by synonym against the real DB.

---

## Out of scope (deferred)

Filtering gene candidates to those present in the target table; the `mutation`
domain tables; per-species preference; trigram GIN-index tuning; multi-gene
disambiguation UX beyond a single clarify.

## Open questions

None. All decisions are resolved above.
