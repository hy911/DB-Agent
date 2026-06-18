# Mutation Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `mutation` domain (somatic mutation data) so mutation questions
route to it, resolve gene names, generate big-table-guarded SQL, and answer —
with **zero Python source changes** to the domain logic (YAML + tests only).

**Architecture:** A pure `semantic_layer.yaml` addition of two tables
(`model_ccle_mutation_data` main + `oncokb` annotation), both `domain: mutation`,
not access-controlled. Routing, gene resolution, the big-table EXPLAIN gate, and
the no-op permission path are all already data-driven and proven by the
`expression` domain. The only optional code touch is a cosmetic prompt reword
(last task, droppable).

**Tech Stack:** Python 3.14 (uv `.venv`), LangGraph, sqlglot, pytest. Spec:
`docs/superpowers/specs/2026-06-18-mutation-domain-design.md`.

**Conventions:** Run with `uv run`. Offline tests inject FakeLLM + a fake resolver
(no DB, no LLM). Columns are pinned to the live DB (not `models.py`). Commit +
push after each task.

## File Structure

- Modify: `semantic_layer.yaml` — add the `mutation` domain's two tables and two
  relationship declarations. (The `mutation` domain entry already exists under
  `domains:` as a forward declaration — no change there.)
- Modify: `tests/test_semantic_domains.py` — assert mutation is routable,
  gene-bearing, and the main table is a flagged big table.
- Modify: `tests/test_sql_secure.py` — assert the main table triggers / skips
  the big-table EXPLAIN gate based on the filter key.
- Modify: `tests/test_graph_nodes.py` — assert mutation context renders both
  tables, no permission note, with gene injection.
- Modify: `tests/test_graph_chain.py` — mutation end-to-end with a fake resolver.
- (Optional, last) Modify: `src/db_agent/llm/prompts.py` + `tests/test_llm_prompts.py`
  — reword the hardcoded "efficacy domain" string to be domain-neutral.

---

### Task 1: Add the two tables to `semantic_layer.yaml` + semantic tests

**Files:**
- Modify: `semantic_layer.yaml`
- Test: `tests/test_semantic_domains.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_semantic_domains.py`, add at the end:

```python
def test_mutation_is_routable():
    names = {d.name for d in LAYER.routable_domains()}
    assert names == {"efficacy", "expression", "mutation"}


def test_mutation_is_gene_bearing():
    assert LAYER.is_gene_bearing("mutation") is True


def test_mutation_main_table_is_big_and_in_domain():
    t = LAYER.get_table("model_ccle_mutation_data")
    assert t is not None
    assert t.domain == "mutation"
    assert t.big_table is True
    assert t.has_column("gene_symbol")
    assert t.has_column("model_uuid")
    assert t.join_to_hub == ("model_uuid",)


def test_oncokb_in_mutation_domain_not_access_controlled():
    t = LAYER.get_table("oncokb")
    assert t is not None
    assert t.domain == "mutation"
    assert t.access_controlled is False
    assert t.has_column("gene")
    assert t.has_column("mutant")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: FAIL — `model_ccle_mutation_data` / `oncokb` are not yet defined
(`get_table` returns `None`), and `routable_domains` excludes `mutation`.

- [ ] **Step 3: Add the two tables to `semantic_layer.yaml`**

In `semantic_layer.yaml`, under `tables:`, add these two blocks (place them after
the `model_ccle_expression_data` block, before `gene_info`). Columns are the live
DB columns:

```yaml
  model_ccle_mutation_data:
    domain: mutation
    desc: 模型体细胞突变(默认表，含外部CCLE数据)。长表：(模型,基因,突变)一行
    big_table: true                   # 约547万行，必须带 model_uuid/gene_symbol 过滤，禁全表扫描
    join_to_hub: [model_uuid]
    columns:
      model_uuid:   {type: varchar, desc: 关联 model_desc_info}
      model_id:     {type: varchar, desc: 模型业务编号}
      gene_symbol:  {type: varchar, desc: 关联 gene_info.Symbol}
      species:      {type: varchar, desc: 物种(大小写编码人/鼠)}
      mutation_id:  {type: text, desc: 突变标识(如 EGFR:L858R)}
      variant_classification: {type: text, desc: 变异分类(如 Missense_Mutation)}
      hgvsc:        {type: text, desc: HGVS 编码序列变化}
      hgvsp_short:  {type: text, desc: HGVS 蛋白变化简写(如 p.L858R)}
      dbsnp_rs:     {type: text, desc: dbSNP rs 编号}
      sift:         {type: text, desc: SIFT 有害性预测}
      polyphen:     {type: text, desc: PolyPhen 有害性预测}
      hotspot_mutation: {type: text, desc: 是否热点突变}
      data_source:  {type: varchar, desc: 数据来源}

  oncokb:
    domain: mutation
    desc: OncoKB 临床注释(基因+突变 -> 致癌性/可用药等级)，按 gene/mutant 关联
    columns:
      gene:            {type: varchar, desc: 基因符号(关联 gene_info.Symbol)}
      mutant:          {type: varchar, desc: 突变(氨基酸改变，如 L858R)}
      oncogenic:       {type: varchar, desc: 致癌性判定}
      mutation_effect: {type: varchar, desc: 突变功能效应}
      level:           {type: varchar, desc: 临床证据等级}
      level_associated_cancer_types: {type: varchar, desc: 等级关联癌种}
      citations:       {type: integer, desc: 文献引用数}
```

Then, under `relationships:`, add these two lines (after the existing
`model_ccle_expression_data.gene_symbol` line):

```yaml
  - {from: model_ccle_mutation_data.gene_symbol, to: gene_info.Symbol, type: many_to_one}
  - {from: oncokb.gene, to: gene_info.Symbol, type: many_to_one}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: PASS (the 4 new tests plus the existing ones).

- [ ] **Step 5: Commit**

```bash
git add semantic_layer.yaml tests/test_semantic_domains.py
git commit -F - <<'EOF'
Add mutation domain tables to the semantic layer

model_ccle_mutation_data (big table, gene-bearing, joins the model_uuid spine)
and oncokb (clinical annotation, domain=mutation so it is fed only for mutation
questions). Not access-controlled. routable_domains now yields {efficacy,
expression, mutation}; gene resolution and the big-table gate are auto-driven.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Big-table gate test for the mutation main table

**Files:**
- Test: `tests/test_sql_secure.py`

This proves the big-table EXPLAIN gate is wired for `model_ccle_mutation_data`
purely from the YAML flag — no source change. The file already has a module-level
`LAYER = load_semantic_layer(...)` and `from db_agent.sql.secure import
SecuredQuery, secure_query` — reuse them.

- [ ] **Step 1: Write the tests**

Add to `tests/test_sql_secure.py`:

```python
def test_mutation_big_table_scan_without_filter_needs_explain():
    secured = secure_query(
        "SELECT count(*) FROM model_ccle_mutation_data", LAYER, "mutation"
    )
    assert secured.needs_explain is True
    assert "model_ccle_mutation_data" in secured.big_tables


def test_mutation_big_table_with_gene_filter_skips_explain():
    secured = secure_query(
        "SELECT mutation_id FROM model_ccle_mutation_data WHERE gene_symbol = 'TP53'",
        LAYER,
        "mutation",
    )
    assert secured.needs_explain is False
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_sql_secure.py -q`
Expected: PASS. (These pass immediately once Task 1's YAML is in — the mechanism
is data-driven. If `test_..._needs_explain` FAILS, the big_table flag is not
reaching the validator and you must STOP and investigate rather than patch around
it — see the spec's "key architectural claim".)

- [ ] **Step 3: Commit**

```bash
git add tests/test_sql_secure.py
git commit -F - <<'EOF'
Test the big-table EXPLAIN gate covers model_ccle_mutation_data

A no-filter scan flags needs_explain; a gene_symbol-filtered query skips it —
driven entirely by the YAML big_table flag, no validator change.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Graph node + chain tests for mutation

**Files:**
- Test: `tests/test_graph_nodes.py`, `tests/test_graph_chain.py`

- [ ] **Step 1: Write the failing node tests**

In `tests/test_graph_nodes.py`, add:

```python
def test_route_mutation_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["mutation"]}))
    out = route_node(initial_state("which models have a TP53 mutation?"), deps)
    assert out["domain"] == "mutation"


def test_after_route_mutation_goes_to_extract():
    s = initial_state("q")
    s["domain"] = "mutation"
    assert after_route(s, _deps()) == "extract_genes"


def test_assemble_context_mutation_omits_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "mutation"
    s["resolved_genes"] = {"p53": "TP53"}
    ctx = assemble_context_node(s, deps)["context"]
    assert "model_ccle_mutation_data" in ctx
    assert "oncokb" in ctx
    assert "do not" not in ctx.lower()           # not access-controlled
    assert "p53 -> TP53" in ctx or "p53 → TP53" in ctx
```

- [ ] **Step 2: Run node tests to verify they fail**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: FAIL — routing to `mutation` and the mutation context assertions fail
until Task 1's YAML is in place. (If Task 1 is already merged, the route/context
tests will pass once added; the point of this step is they are *new* assertions —
run them and confirm green. If any fail, fix before moving on.)

- [ ] **Step 3: Write the failing chain test**

In `tests/test_graph_chain.py`, add (the `_LLM`, `_Replica`, `_resolver`, `_run`,
and `QueryResult` helpers already exist from the gene-wiring work):

```python
def test_mutation_end_to_end_resolves_gene():
    llm = _LLM(
        {
            "qwen-fast": ["mutation", "p53"],  # route, then extract_genes
            "qwen-code": [
                "SELECT model_uuid, mutation_id FROM model_ccle_mutation_data "
                "WHERE gene_symbol = 'TP53'"
            ],
            "qwen-main": ["3 models carry a TP53 mutation."],
        }
    )
    qr = QueryResult(
        columns=["model_uuid", "mutation_id"],
        rows=[{"model_uuid": "m1", "mutation_id": "TP53:R175H"}],
        rowcount=1,
        truncated=False,
        sql="SELECT model_uuid, mutation_id",
        elapsed_ms=1.0,
    )
    res = _run(
        llm,
        _Replica([qr]),
        question="which models have a p53 mutation?",
        resolve_gene=_resolver({"p53": "TP53"}),
    )
    assert res.status == "answered"
    assert res.answer == "3 models carry a TP53 mutation."
    assert "for_bd" not in (res.sql or "").lower()  # mutation: not access-controlled
    assert "model_ccle_mutation_data" in res.sql.lower()
```

- [ ] **Step 4: Run chain test to verify it passes**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: PASS. (The `_Replica` fake returns the scripted `QueryResult` without
running EXPLAIN, so the gate is not exercised here — that is covered offline in
Task 2 and live in Task 4.)

- [ ] **Step 5: Run both files to confirm green**

Run: `uv run pytest tests/test_graph_nodes.py tests/test_graph_chain.py -q`
Expected: PASS (all node + chain tests green).

- [ ] **Step 6: Commit**

```bash
git add tests/test_graph_nodes.py tests/test_graph_chain.py
git commit -F - <<'EOF'
Add mutation routing + context + end-to-end offline tests

Mutation routes through the gene nodes (gene-bearing), its context renders both
tables with the resolved-gene map and no permission note, and the full chain
answers with no for_bd injection.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: Full offline suite + ruff + live end-to-end

**Files:** none (verification).

- [ ] **Step 1: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `9 deselected` (integration). All offline tests green
including the new mutation tests; efficacy and expression regressions intact.

- [ ] **Step 2: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff
check` reports fixable issues, run `uv run ruff check --fix src tests && uv run
ruff format src tests` and re-run.)

- [ ] **Step 3: Live end-to-end (real LLM + DB)**

> Prerequisite: `.env` DSN authenticates and the LiteLLM gateway is reachable. If
> either fails, STOP and report — do not loosen anything.

Run:

```bash
uv run python - <<'PY'
from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.graph import run_agent
from db_agent.llm import LiteLLMClient
from db_agent.semantic import load_semantic_layer

s = get_settings()
replica = ReadReplica(s); replica.open()
layer = load_semantic_layer(s.semantic_layer_path)
llm = LiteLLMClient(s)
try:
    # 1) gene-filtered: "which models carry a TP53 mutation?"
    r1 = run_agent(
        "Which models carry a TP53 mutation? List a few model_uuid.",
        llm=llm, replica=replica, layer=layer, settings=s,
    )
    print("Q1 status :", r1.status)
    print("Q1 answer :", r1.answer)
    print("Q1 sql    :", r1.sql)

    # 2) model_uuid-filtered: discover a uuid that has mutations, then ask
    uuid_rows = replica.fetch(
        "SELECT model_uuid FROM model_ccle_mutation_data "
        "WHERE model_uuid IS NOT NULL LIMIT 1"
    )
    uuid = uuid_rows[0]["model_uuid"] if uuid_rows else None
    print("discovered uuid:", uuid)
    if uuid:
        r2 = run_agent(
            f"What mutations does model {uuid} have? Give gene_symbol and mutation_id.",
            llm=llm, replica=replica, layer=layer, settings=s,
        )
        print("Q2 status :", r2.status)
        print("Q2 answer :", r2.answer)
        print("Q2 sql    :", r2.sql)
finally:
    replica.close()
PY
```

Expected: Q1 `status == answered` with SQL filtering `gene_symbol = 'TP53'`; Q2
`status == answered` with SQL filtering `model_uuid = '<uuid>'`. Report both
printed results. If either is `clarify`, report the clarification (e.g. the model
extracted an ambiguous gene) — that is a valid outcome to surface, not a failure
to patch. Do not commit anything (no code change).

> If Q1/Q2 come back as a fatal big-table rejection, that means
> `model_ccle_mutation_data` is being sequentially scanned even with the filter
> (likely a missing index on `gene_symbol`/`model_uuid`). Report it as an
> ops/index finding — do NOT remove or weaken the big-table guard.

---

### Task 5 (optional, droppable): Domain-neutral SQL prompt wording

**Files:**
- Modify: `src/db_agent/llm/prompts.py`
- Test: `tests/test_llm_prompts.py`

The `_SQL_SYSTEM` string hardcodes "for the efficacy domain". Harmless (the real
schema is supplied via context, proven by expression + mutation working), but
reword now that three domains exist. If this causes churn beyond the trivial
assertion below, drop the task.

- [ ] **Step 1: Write the failing test**

In `tests/test_llm_prompts.py`, add:

```python
def test_sql_system_prompt_is_domain_neutral():
    msgs = sql_messages("q", "ctx")
    system = msgs[0]["content"].lower()
    assert "efficacy domain" not in system
    assert "select" in system  # still instructs a read-only SELECT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_prompts.py::test_sql_system_prompt_is_domain_neutral -q`
Expected: FAIL — the current string contains "efficacy domain".

- [ ] **Step 3: Reword the prompt**

In `src/db_agent/llm/prompts.py`, change the first sentence of `_SQL_SYSTEM`:

```python
_SQL_SYSTEM = (
    "You write exactly one read-only PostgreSQL SELECT for a mouse tumor-model "
    "database. "
    "Use only the tables and columns in the provided schema context. Do not write "
    "INSERT/UPDATE/DELETE/DDL. Return only the SQL, with no prose and no code "
    "fences."
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_prompts.py -q`
Expected: PASS (the new test plus the existing prompt tests).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/llm/prompts.py tests/test_llm_prompts.py
git commit -F - <<'EOF'
Reword SQL system prompt to be domain-neutral

The agent now serves efficacy/expression/mutation; drop the stale "efficacy
domain" wording (the real schema is always supplied via context).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

## Self-Review

**Spec coverage:**
- Two tables added to YAML (main `big_table`, `oncokb` domain=mutation, columns
  pinned to live DB, not access-controlled) → Task 1. ✅
- Routing auto-includes mutation; gene resolution auto-runs (gene-bearing) →
  Tasks 1 (semantic) + 3 (node/chain). ✅
- Big-table EXPLAIN gate on the main table → Task 2 (offline) + Task 4 (live). ✅
- No permission injection (not access-controlled) → Task 3 context test + chain
  `for_bd` assertion. ✅
- oncokb fed only for mutation (domain=mutation, not reference) → Task 3 context
  renders oncokb for the mutation domain; existing efficacy/expression context
  tests already assert their own tables, so oncokb does not leak. ✅
- Live verification of both question shapes → Task 4. ✅
- Optional prompt reword → Task 5. ✅
- Out-of-scope (`model_mutation_feature`, raw `model_mutation_data`,
  `ccl_mutation_data`, `modeling`) → not added; deferred per spec. ✅

**Placeholder scan:** No TBD/TODO; every code step has concrete code, and every
test file's existing helpers (`LAYER`, `_LLM`, `_Replica`, `_resolver`, `_run`,
`secure_query`) were confirmed present before referencing them.

**Type consistency:** `secure_query(sql, layer, domain) -> SecuredQuery` with
`.needs_explain: bool` and `.big_tables: frozenset[str]` (matches
`sql/secure.py`); `after_route(state, deps)`, `assemble_context_node(state, deps)`,
`route_node(state, deps)`, `_deps(llm=, replica=, resolve_gene=)`,
`_run(llm, replica, question=, resolve_gene=)`, `_resolver(mapping)`,
`QueryResult(columns, rows, rowcount, truncated, sql, elapsed_ms)`,
`run_agent(question, *, llm, replica, layer, settings)` — all consistent with the
shipped code and the gene-wiring tests. ✅
