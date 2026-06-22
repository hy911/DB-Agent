# Modeling Detail Tables (batch 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 5 more modeling detail tables (facs / avg_radiance / total_flux /
elisa / pathology) to the existing access-controlled `modeling` domain — pure
`semantic_layer.yaml` + tests, **zero Python source changes**.

**Architecture:** Each table joins the hub `modeling_attr_info` via
`access_via` + `join_to_hub: [model_uuid, model_no, group_id]`; the generic
permission injector (already shipped + security-reviewed for the modeling
pattern) filters them automatically. `modeling_panel_data` is excluded (no
group_id).

**Tech Stack:** Python 3.14 (uv `.venv`), sqlglot, pytest. Spec:
`docs/superpowers/specs/2026-06-18-modeling-detail-tables-design.md`.

**Conventions:** Run with `uv run`. Columns pinned to the live DB. `sql/` must NOT
change. Commit + push after each task.

## File Structure

- Modify: `semantic_layer.yaml` — add 5 detail-table blocks under `tables:`.
- Modify: `tests/test_semantic_domains.py` — assert all 8 modeling detail tables
  are wired to the hub with the 3 join keys.
- Modify: `tests/test_sql_secure.py` — assert one new table gets the correct
  `EXISTS` semi-join from `secure_query`.

---

### Task 1: Add the 5 detail tables to `semantic_layer.yaml` + tests

**Files:**
- Modify: `semantic_layer.yaml`
- Test: `tests/test_semantic_domains.py`, `tests/test_sql_secure.py`

- [ ] **Step 1: Update the failing semantic test**

In `tests/test_semantic_domains.py`, replace `test_modeling_detail_tables_join_to_hub`
with the 8-table version:

```python
def test_modeling_detail_tables_join_to_hub():
    details = LAYER.detail_tables_of("modeling_attr_info")
    names = {t.name for t in details}
    assert names == {
        "modeling_tumor_volume_growth_curve_data",
        "modeling_body_weight_growth_curve_data",
        "modeling_survival_data",
        "modeling_facs_growth_curve_data",
        "modeling_avg_radiance_data",
        "modeling_total_flux_data",
        "modeling_elisa_data",
        "modeling_pathology_data",
    }
    for t in details:
        assert t.access_via == "modeling_attr_info"
        assert t.join_to_hub == ("model_uuid", "model_no", "group_id")


def test_modeling_panel_excluded():
    # panel lacks group_id; deliberately not added (would coarsen permission grain)
    assert LAYER.get_table("modeling_panel_data") is None
```

- [ ] **Step 2: Add the secure_query test for a new table**

In `tests/test_sql_secure.py`, append:

```python
def test_secure_modeling_facs_injects_exists_semijoin():
    out = secure_query(
        "SELECT val FROM modeling_facs_growth_curve_data", LAYER, "modeling"
    )
    s = out.sql
    assert "EXISTS" in s.upper()
    assert "modeling_attr_info AS _perm" in s
    assert "_perm.model_uuid = modeling_facs_growth_curve_data.model_uuid" in s
    assert "_perm.model_no = modeling_facs_growth_curve_data.model_no" in s
    assert "_perm.group_id = modeling_facs_growth_curve_data.group_id" in s
    assert "_perm.for_bd = 'yes'" in s
    assert "modeling_facs_growth_curve_data.for_bd" not in s
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_semantic_domains.py tests/test_sql_secure.py -q`
Expected: FAIL — the 5 tables are not in the YAML yet (`detail_tables_of` returns
only 3; `secure_query` on the facs table raises a fatal out-of-scope GuardError).

- [ ] **Step 4: Add the 5 tables to `semantic_layer.yaml`**

Under `tables:`, add these blocks after the `modeling_survival_data` block
(before `gene_info`). Columns are the live DB columns:

```yaml
  modeling_facs_growth_curve_data:
    domain: modeling
    desc: 建模-FACS 检测(按检测项/组织/动物)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:     {type: varchar}
      model_no:       {type: varchar}
      group_id:       {type: varchar}
      animal_id:      {type: integer, desc: 动物编号}
      detection_item: {type: varchar, desc: 检测项}
      tissue_type:    {type: varchar, desc: 组织类型}
      date:           {type: timestamp, desc: 测量日期}
      val:            {type: float, desc: 检测值}

  modeling_avg_radiance_data:
    domain: modeling
    desc: 建模-平均辐射强度(活体成像，纵向时序)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:   {type: varchar}
      model_no:     {type: varchar}
      group_id:     {type: varchar}
      animal_id:    {type: varchar, desc: 动物编号}
      days:         {type: integer, desc: 建模后天数}
      date:         {type: date, desc: 测量日期}
      avg_radiance: {type: float, desc: 平均辐射强度}

  modeling_total_flux_data:
    domain: modeling
    desc: 建模-总光通量(活体成像，纵向时序)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid: {type: varchar}
      model_no:   {type: varchar}
      group_id:   {type: varchar}
      animal_id:  {type: varchar, desc: 动物编号}
      days:       {type: integer, desc: 建模后天数}
      date:       {type: date, desc: 测量日期}
      total_flux: {type: float, desc: 总光通量}

  modeling_elisa_data:
    domain: modeling
    desc: 建模-ELISA 检测(按检测项/组织/动物)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:     {type: varchar}
      model_no:       {type: varchar}
      group_id:       {type: varchar}
      animal_id:      {type: integer, desc: 动物编号}
      detection_item: {type: varchar, desc: 检测项}
      tissue_type:    {type: varchar, desc: 组织类型}
      date:           {type: date, desc: 测量日期}
      val:            {type: float, desc: 检测值}

  modeling_pathology_data:
    domain: modeling
    desc: 建模-病理检测(横截面，按检测项/动物)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no, group_id]
    columns:
      model_uuid:     {type: varchar}
      model_no:       {type: varchar}
      group_id:       {type: varchar}
      animal_id:      {type: varchar, desc: 动物编号}
      detection_item: {type: varchar, desc: 检测项}
      val:            {type: float, desc: 检测值}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_semantic_domains.py tests/test_sql_secure.py -q`
Expected: PASS (loader `_validate` accepts each detail table because all three
join keys exist on both the table and the hub).

- [ ] **Step 6: Commit**

```bash
git add semantic_layer.yaml tests/test_semantic_domains.py tests/test_sql_secure.py
git commit -F - <<'EOF'
Add 5 more modeling detail tables (facs/imaging/elisa/pathology)

facs, avg_radiance, total_flux, elisa, pathology join the modeling hub via
[model_uuid, model_no, group_id] and get the same for_bd EXISTS semi-join from
the generic injector. modeling_panel_data excluded (no group_id). Zero source.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Full suite + ruff + live execute check

**Files:** none (verification).

- [ ] **Step 1: Full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `9 deselected`. All green.

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If format
differs, run `uv run ruff format src tests` and re-check.)

- [ ] **Step 3: Live execute one new detail query (real DB, no LLM)**

This confirms the injected `EXISTS` for a new table runs on the real DB. It uses
`secure_query` + `replica.execute` directly (no answer-node LLM call, so no
gateway dependency).

Run:

```bash
uv run python - <<'PY'
from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.semantic import load_semantic_layer
from db_agent.sql.secure import secure_query

s = get_settings(); r = ReadReplica(s); r.open()
layer = load_semantic_layer(s.semantic_layer_path)
try:
    uuid_rows = r.fetch(
        "SELECT model_uuid FROM modeling_attr_info WHERE for_bd = 'yes' "
        "AND model_uuid IS NOT NULL LIMIT 1"
    )
    uuid = uuid_rows[0]["model_uuid"] if uuid_rows else None
    print("uuid:", uuid)
    raw = (
        "SELECT detection_item, val FROM modeling_facs_growth_curve_data "
        f"WHERE model_uuid = '{uuid}' LIMIT 5"
    )
    sec = secure_query(raw, layer, "modeling")
    print("SECURED:", sec.sql)
    res = r.execute(sec.sql, needs_explain=sec.needs_explain, big_tables=sec.big_tables, limit=sec.limit)
    print("rows:", res.rowcount)
    for row in res.rows[:5]:
        print("  ", row)
finally:
    r.close()
PY
```

Expected: the SECURED SQL contains the `EXISTS ... modeling_attr_info AS _perm
... _perm.for_bd = 'yes'` semi-join on all three keys; the query executes without
error. Row count may be 0 if that particular model has no FACS rows — that is
fine; the point is the injected SQL runs. Report the printed output. No commit
(no code change).

---

## Self-Review

**Spec coverage:**
- 5 detail tables added with `access_via` + 3-key `join_to_hub`, live-DB columns →
  Task 1 Step 4. ✅
- `detail_tables_of` returns all 8; panel excluded → Task 1 Steps 1. ✅
- `secure_query` injects correct EXSTS for a new table → Task 1 Step 2 + live
  Task 2 Step 3. ✅
- Full suite + ruff green → Task 2 Steps 1-2. ✅
- Live execute of an injected new-table query → Task 2 Step 3. ✅
- panel exclusion asserted → `test_modeling_panel_excluded`. ✅

**Placeholder scan:** No TBD/TODO; all code/commands concrete. Reused helpers
(`LAYER`, `detail_tables_of`, `secure_query`, `ReadReplica.fetch/execute`)
confirmed present.

**Type consistency:** `detail_tables_of(hub) -> list[Table]` with `.access_via`,
`.join_to_hub: tuple[str,...]`; `secure_query(sql, layer, domain) -> SecuredQuery`
(`.sql`, `.needs_explain`, `.big_tables`, `.limit`); `ReadReplica.execute(sql, *,
needs_explain, big_tables, limit)` / `.fetch(sql, params)` — all match shipped
code.
