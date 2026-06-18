# Modeling Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the access-controlled `modeling` domain (hub `modeling_attr_info` +
3 detail tables) so modeling questions route to it and get row-level permissions
(`for_bd='yes'` on the hub, an `EXISTS` semi-join on detail tables) injected
deterministically — with **zero Python source changes**.

**Architecture:** A pure `semantic_layer.yaml` addition of 4 tables. The permission
injector (`sql/permission.py`) is already generic and data-driven: it reads the
hub, detail tables (`access_via`), and join keys (`join_to_hub`) from the layer,
and the hardcoded `for_bd`/`yes` happen to be exactly modeling's permission rule.
This is the first access-controlled domain added via config, so it exercises the
real injection path.

**Tech Stack:** Python 3.14 (uv `.venv`), LangGraph, sqlglot, pytest. Spec:
`docs/superpowers/specs/2026-06-18-modeling-domain-design.md`.

**Conventions:** Run with `uv run`. Offline tests inject a FakeLLM (no DB, no LLM).
Columns are pinned to the live DB (not `models.py`). `sql/permission.py` must NOT
change — if it appears to need to, STOP (security-relevant). Commit + push after
each task.

## File Structure

- Modify: `semantic_layer.yaml` — add the hub `modeling_attr_info` + 3 detail
  tables + one relationship line. (`modeling` is already declared under
  `domains:` with `access_controlled: true, hub: modeling_attr_info`.)
- Modify: `tests/test_semantic_domains.py` — routable set now includes modeling;
  modeling is access-controlled, not gene-bearing; detail tables wired to the hub.
- Modify: `tests/test_permission.py` — `injection_config_for_domain` builds the
  modeling config correctly from the YAML.
- Modify: `tests/test_sql_secure.py` — `secure_query` injects `for_bd='yes'` on
  the hub and an `EXISTS` semi-join (on model_uuid/model_no/group_id) on a detail
  table.
- Modify: `tests/test_graph_nodes.py` + `tests/test_graph_chain.py` — modeling
  routes straight to assemble_context (not gene-bearing), context shows the
  permission note, and the full chain injects `for_bd`.

---

### Task 1: Add the 4 tables to `semantic_layer.yaml` + semantic tests

**Files:**
- Modify: `semantic_layer.yaml`
- Test: `tests/test_semantic_domains.py`

- [ ] **Step 1: Write/update the failing tests**

In `tests/test_semantic_domains.py`:

(a) Replace the existing `test_routable_domains_are_efficacy_expression_mutation`
with the 4-domain version:

```python
def test_routable_domains_are_all_four():
    names = {d.name for d in LAYER.routable_domains()}
    assert names == {"efficacy", "expression", "mutation", "modeling"}
```

(b) In `test_routable_excludes_reference_and_undefined_domains`, remove the now-
false `assert "modeling" not in names` line, leaving:

```python
def test_routable_excludes_reference_and_undefined_domains():
    names = {d.name for d in LAYER.routable_domains()}
    assert "reference" not in names  # dictionary domain, never routed
```

(c) Append these new tests:

```python
def test_modeling_access_controlled_with_hub():
    dom = LAYER.get_domain("modeling")
    assert dom is not None
    assert dom.access_controlled is True
    assert dom.hub == "modeling_attr_info"


def test_modeling_not_gene_bearing():
    assert LAYER.is_gene_bearing("modeling") is False


def test_modeling_detail_tables_join_to_hub():
    details = LAYER.detail_tables_of("modeling_attr_info")
    names = {t.name for t in details}
    assert names == {
        "modeling_tumor_volume_growth_curve_data",
        "modeling_body_weight_growth_curve_data",
        "modeling_survival_data",
    }
    for t in details:
        assert t.access_via == "modeling_attr_info"
        assert t.join_to_hub == ("model_uuid", "model_no", "group_id")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: FAIL — modeling has no tables yet (`detail_tables_of` empty,
`get_domain("modeling").hub` is set but no tables → not routable).

- [ ] **Step 3: Add the 4 tables to `semantic_layer.yaml`**

Under `tables:`, add these blocks (place after the `oncokb` block, before
`gene_info`). Columns are the live DB columns:

```yaml
  modeling_attr_info:
    domain: modeling
    desc: 建模实验枢纽（一个建模分组=一行），含建模属性与权限字段
    access_controlled: true
    columns:
      model_uuid:   {type: varchar, desc: 关联 model_desc_info}
      model_no:     {type: varchar, desc: 建模编号(明细表连接键，相当于 efficacy 的 efficacy_num)}
      group_id:     {type: varchar, desc: 实验分组(明细表连接键)}
      amount:       {type: varchar, desc: 接种量}
      route:        {type: varchar, desc: 接种途径}
      strain:       {type: varchar, desc: 鼠品系}
      sex:          {type: varchar, desc: 性别}
      vendor:       {type: varchar, desc: 供应商}
      passage:      {type: varchar, desc: 代次}
      days_when_tumor_volume_100mm3:  {type: integer, desc: 瘤体积达 100mm³ 的天数}
      days_when_tumor_volume_500mm3:  {type: integer, desc: 瘤体积达 500mm³ 的天数}
      days_when_tumor_volume_1000mm3: {type: float, desc: 瘤体积达 1000mm³ 的天数}
      quality:      {type: varchar, desc: 数据质量}
      for_bd:       {type: varchar, desc: 权限：是否对 BD 可见}
      for_control:  {type: varchar, desc: 权限：是否对照}
      for_model:    {type: boolean, desc: 权限：是否用于建模}

  modeling_tumor_volume_growth_curve_data:
    domain: modeling
    desc: 建模-肿瘤体积生长曲线(纵向时序，按动物/天)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:   {type: varchar}
      model_no:     {type: varchar}
      group_id:     {type: varchar}
      days:         {type: integer, desc: 建模后天数}
      date:         {type: timestamp, desc: 测量日期}
      body_part:    {type: varchar, desc: 部位}
      tumor_volume: {type: float, desc: 单只动物瘤体积}
      avg:          {type: float, desc: 组内均值}
      sd:           {type: float, desc: 组内标准差}

  modeling_body_weight_growth_curve_data:
    domain: modeling
    desc: 建模-体重生长曲线(纵向时序，按动物/天)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:   {type: varchar}
      model_no:     {type: varchar}
      group_id:     {type: varchar}
      days:         {type: integer, desc: 建模后天数}
      date:         {type: timestamp, desc: 测量日期}
      body_weight:  {type: float, desc: 单只动物体重}
      avg:          {type: float, desc: 组内均值}
      sd:           {type: float, desc: 组内标准差}

  modeling_survival_data:
    domain: modeling
    desc: 建模-生存数据(按动物)，用于生存/KM 分析
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:   {type: varchar}
      model_no:     {type: varchar}
      group_id:     {type: varchar}
      animal_id:    {type: text, desc: 动物编号(库内为字符串)}
      survival:     {type: text, desc: 生存时间(库内为字符串)}
```

Then, under `relationships:`, add this line (after the existing
`model_efficacy_*` relationship line):

```yaml
  - {from: "modeling_*.{model_uuid,model_no,group_id}", to: modeling_attr_info, desc: 建模明细->枢纽}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: PASS (the loader `_validate` accepts the detail tables because each
`join_to_hub` key exists on both the detail table and the hub).

- [ ] **Step 5: Commit**

```bash
git add semantic_layer.yaml tests/test_semantic_domains.py
git commit -F - <<'EOF'
Add modeling domain tables to the semantic layer

Hub modeling_attr_info (access-controlled, for_bd) + 3 detail tables
(tumor_volume / body_weight / survival) joined back via [model_uuid, model_no,
group_id]. routable_domains now yields all four domains; permission injection is
auto-driven from the YAML.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Permission-injection tests for modeling (the security core)

**Files:**
- Test: `tests/test_permission.py`, `tests/test_sql_secure.py`

This proves the generic injector produces correct, fail-closed SQL for modeling
purely from the YAML — no `sql/permission.py` change.

- [ ] **Step 1: Write the config test**

In `tests/test_permission.py`, append (the file currently imports only
`InjectionConfig, inject_permissions`; import the rest inside the test):

```python
def test_injection_config_for_modeling_built_from_layer():
    from db_agent.config import Settings
    from db_agent.semantic import load_semantic_layer
    from db_agent.sql.permission import injection_config_for_domain

    layer = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)
    cfg = injection_config_for_domain(layer, "modeling")
    assert cfg is not None
    assert cfg.hub_table == "modeling_attr_info"
    assert cfg.access_field == "for_bd"
    assert cfg.access_value == "yes"
    keys = ("model_uuid", "model_no", "group_id")
    assert cfg.detail_join_keys["modeling_tumor_volume_growth_curve_data"] == keys
    assert cfg.detail_join_keys["modeling_body_weight_growth_curve_data"] == keys
    assert cfg.detail_join_keys["modeling_survival_data"] == keys
    assert "modeling_attr_info" in cfg.controlled_tables
```

- [ ] **Step 2: Write the secure_query tests**

In `tests/test_sql_secure.py`, append (the file already has module-level `LAYER`
and `from db_agent.sql.secure import SecuredQuery, secure_query`):

```python
def test_secure_modeling_hub_injects_for_bd():
    out = secure_query("SELECT model_no FROM modeling_attr_info", LAYER, "modeling")
    low = out.sql.lower()
    assert "for_bd = 'yes'" in low
    assert out.needs_explain is False  # not a big table


def test_secure_modeling_detail_injects_exists_semijoin():
    out = secure_query(
        "SELECT tumor_volume FROM modeling_tumor_volume_growth_curve_data",
        LAYER,
        "modeling",
    )
    s = out.sql
    assert "EXISTS" in s.upper()
    assert "modeling_attr_info AS _perm" in s
    assert "_perm.model_uuid = modeling_tumor_volume_growth_curve_data.model_uuid" in s
    assert "_perm.model_no = modeling_tumor_volume_growth_curve_data.model_no" in s
    assert "_perm.group_id = modeling_tumor_volume_growth_curve_data.group_id" in s
    assert "_perm.for_bd = 'yes'" in s
    # the detail table must NOT get a bare for_bd filter on itself
    assert "modeling_tumor_volume_growth_curve_data.for_bd" not in s
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/test_permission.py tests/test_sql_secure.py -q`
Expected: PASS immediately (mechanism is data-driven from Task 1). If
`test_secure_modeling_detail_injects_exists_semijoin` FAILS, the injector is not
picking up the modeling config from the YAML — STOP and report (do NOT edit
`sql/permission.py`; that contradicts the design and is security-relevant).

- [ ] **Step 4: Commit**

```bash
git add tests/test_permission.py tests/test_sql_secure.py
git commit -F - <<'EOF'
Test modeling permission injection (hub for_bd + detail EXISTS)

injection_config_for_domain builds the modeling config from the YAML; secure_query
filters the hub on for_bd='yes' and semi-joins each detail table back to the hub on
(model_uuid, model_no, group_id) — generic injector, no source change.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Graph node + chain tests for modeling

**Files:**
- Test: `tests/test_graph_nodes.py`, `tests/test_graph_chain.py`

- [ ] **Step 1: Write the node tests**

In `tests/test_graph_nodes.py`, append (helpers `_deps`, `_LLM`, `route_node`,
`after_route`, `assemble_context_node`, `initial_state` already exist):

```python
def test_route_modeling_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["modeling"]}))
    out = route_node(initial_state("modeling tumor volume for model X?"), deps)
    assert out["domain"] == "modeling"


def test_after_route_modeling_skips_gene_nodes():
    # modeling is not gene-bearing, so it goes straight to assemble_context.
    s = initial_state("q")
    s["domain"] = "modeling"
    assert after_route(s, _deps()) == "assemble_context"


def test_assemble_context_modeling_has_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "modeling"
    ctx = assemble_context_node(s, deps)["context"]
    assert "modeling_attr_info" in ctx
    assert "modeling_tumor_volume_growth_curve_data" in ctx
    assert "for_bd" in ctx
    assert "do not" in ctx.lower()  # permission note present (access-controlled)
```

- [ ] **Step 2: Run node tests to verify they pass**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: PASS (modeling now routes and renders since Task 1's YAML is in).

- [ ] **Step 3: Write the chain test**

In `tests/test_graph_chain.py`, append (helpers `_LLM`, `_Replica`, `_run`,
`QueryResult` already exist):

```python
def test_modeling_end_to_end_injects_permission():
    llm = _LLM(
        {
            "qwen-fast": ["modeling"],  # not gene-bearing -> no extract_genes call
            "qwen-code": ["SELECT model_no FROM modeling_attr_info"],
            "qwen-main": ["3 modeling groups are visible to BD."],
        }
    )
    qr = QueryResult(
        columns=["model_no"],
        rows=[{"model_no": "M1"}],
        rowcount=1,
        truncated=False,
        sql="SELECT model_no",
        elapsed_ms=1.0,
    )
    res = _run(llm, _Replica([qr]), question="how many modeling groups for BD?")
    assert res.status == "answered"
    assert res.answer == "3 modeling groups are visible to BD."
    assert "for_bd" in (res.sql or "").lower()  # permission injected into the SQL that ran
```

- [ ] **Step 4: Run chain test to verify it passes**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: PASS.

- [ ] **Step 5: Run both files to confirm green**

Run: `uv run pytest tests/test_graph_nodes.py tests/test_graph_chain.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_graph_nodes.py tests/test_graph_chain.py
git commit -F - <<'EOF'
Add modeling routing + context + end-to-end offline tests

modeling routes straight to assemble_context (not gene-bearing), its context
carries the permission note, and the full chain injects for_bd into the executed
SQL.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: Full suite + ruff + live e2e + SQL security review

**Files:** none (verification).

- [ ] **Step 1: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `9 deselected` (integration). All offline tests green
including the new modeling tests; efficacy/expression/mutation regressions intact.

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
    # 1) hub count, exercises the for_bd='yes' filter directly
    r1 = run_agent(
        "How many modeling groups are visible to BD? Give a single count.",
        llm=llm, replica=replica, layer=layer, settings=s,
    )
    print("Q1 status :", r1.status)
    print("Q1 answer :", r1.answer)
    print("Q1 sql    :", r1.sql)

    # 2) detail growth curve for a model_uuid that has a for_bd='yes' modeling group
    uuid_rows = replica.fetch(
        "SELECT model_uuid FROM modeling_attr_info WHERE for_bd = 'yes' "
        "AND model_uuid IS NOT NULL LIMIT 1"
    )
    uuid = uuid_rows[0]["model_uuid"] if uuid_rows else None
    print("discovered uuid:", uuid)
    if uuid:
        r2 = run_agent(
            f"Show the modeling tumor-volume growth curve (days and tumor_volume) "
            f"for model {uuid}.",
            llm=llm, replica=replica, layer=layer, settings=s,
        )
        print("Q2 status :", r2.status)
        print("Q2 answer :", r2.answer)
        print("Q2 sql    :", r2.sql)
finally:
    replica.close()
PY
```

Expected: Q1 `status == answered`, SQL filters `for_bd = 'yes'` on
`modeling_attr_info`. Q2 `status == answered`, SQL either carries the `EXISTS`
semi-join (if it queried the detail table alone) or a hub `for_bd` filter (if it
joined the hub). Report both printed results verbatim. A transient gateway 504 on
the answer node is an ops issue (known deferred retry/backoff gap), not a domain
bug — if it happens, report it and note the SQL/secured pipeline still worked.

- [ ] **Step 4: SQL security review (mandatory for an access-controlled domain)**

This change adds an access-controlled domain via `semantic_layer.yaml`. Dispatch
the `sql-security-reviewer` subagent (Agent tool, `subagent_type='sql-security-reviewer'`)
to audit the injected SQL against the fixed guard-rail decisions. Point it at the
diff `git diff c2b9713 HEAD` (or the actual base SHA before Task 1) and the two
live SQLs from Step 3. It must confirm: the hub is filtered `for_bd='yes'`; every
detail table is semi-joined on all three keys + `for_bd='yes'`; no detail-row
multiplication (EXISTS, not JOIN); idempotent; `sql/permission.py` unchanged.
Address any Critical/High findings before finishing. (No code commit in this task
unless the review surfaces a required fix.)

---

## Self-Review

**Spec coverage:**
- 4 tables added to YAML (hub access-controlled + 3 detail with `access_via` /
  `join_to_hub`, live-DB columns) → Task 1. ✅
- Routing auto-includes modeling; not gene-bearing (skips gene nodes) → Tasks 1
  (semantic) + 3 (node). ✅
- Permission injection via the generic injector (hub `for_bd='yes'`, detail
  `EXISTS` on model_uuid/model_no/group_id, no bare detail filter) → Task 2
  (config + secure_query) + Task 3 (chain `for_bd` assertion). ✅
- Context renders the permission note → Task 3 node test. ✅
- Live verification of hub + detail question shapes → Task 4 Step 3. ✅
- Mandatory SQL security review → Task 4 Step 4. ✅
- Out-of-scope detail tables / clinical_attr_info / m_-mirror / *_stats excluded
  → not added. ✅

**Placeholder scan:** No TBD/TODO; every code/test/command step has concrete
content. Every reused helper (`LAYER`, `_deps`, `_LLM`, `_Replica`, `_run`,
`secure_query`, `injection_config_for_domain`, `QueryResult`,
`detail_tables_of`) was confirmed present in the codebase before referencing.

**Type consistency:** `secure_query(sql, layer, domain) -> SecuredQuery(.sql,
.needs_explain, .big_tables, .limit)`; `injection_config_for_domain(layer, domain)
-> InjectionConfig(.hub_table, .access_field, .access_value, .detail_join_keys,
.controlled_tables)`; `detail_tables_of(hub) -> list[Table]` with `.access_via`,
`.join_to_hub: tuple[str, ...]`; `after_route(state, deps) -> str`;
`assemble_context_node(state, deps) -> dict`; `route_node(state, deps) -> dict`;
`_deps(llm=, replica=, resolve_gene=)`; `_run(llm, replica, question=,
resolve_gene=None)`; `QueryResult(columns, rows, rowcount, truncated, sql,
elapsed_ms)` — all consistent with the shipped code and the efficacy/mutation
tests.
