# Add modeling_panel_data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `modeling_panel_data` into the access-controlled `modeling` domain at the any-visible `(model_uuid, model_no)` grain — a `semantic_layer.yaml`-only change (the permission injector is already key-count generic).

**Architecture:** Add one table block to `semantic_layer.yaml` with `join_to_hub: [model_uuid, model_no]`. The injector emits a 2-key `EXISTS` semi-join to `modeling_attr_info` automatically. Update the two existing tests that asserted panel was excluded / that all modeling detail tables use 3 keys; add panel coverage.

**Tech Stack:** YAML, pytest, ruff, uv. No source changes.

**Reference spec:** `docs/superpowers/specs/2026-06-23-modeling-panel-data-design.md`

---

## Task 1: Add modeling_panel_data + update/extend tests

**Files:**
- Modify: `semantic_layer.yaml`
- Modify: `tests/test_semantic_domains.py`, `tests/test_permission.py`

- [ ] **Step 1: Update the failing/affected tests first**

In `tests/test_semantic_domains.py`, replace `test_modeling_detail_tables_join_to_hub`
and `test_modeling_panel_excluded` with:

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
        "modeling_panel_data",
    }
    for t in details:
        assert t.access_via == "modeling_attr_info"
        if t.name == "modeling_panel_data":
            assert t.join_to_hub == ("model_uuid", "model_no")  # no group_id
        else:
            assert t.join_to_hub == ("model_uuid", "model_no", "group_id")


def test_modeling_panel_included_two_key_grain():
    t = LAYER.get_table("modeling_panel_data")
    assert t is not None
    assert t.access_via == "modeling_attr_info"
    assert t.join_to_hub == ("model_uuid", "model_no")
```

In `tests/test_permission.py`, in `test_injection_config_for_modeling_built_from_layer`
(after the existing `detail_join_keys` assertions), add:

```python
    assert cfg.detail_join_keys["modeling_panel_data"] == ("model_uuid", "model_no")
```

- [ ] **Step 2: Add a permission-injection test for panel**

Append to `tests/test_permission.py`:

```python
def test_modeling_panel_data_gets_two_key_exists():
    from db_agent.semantic import load_semantic_layer
    from db_agent.sql.secure import secure_query
    from db_agent.config import Settings

    layer = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)
    secured = secure_query(
        "SELECT panel, detection_item FROM modeling_panel_data", layer, "modeling"
    )
    sql = secured.sql.lower()
    assert "exists" in sql
    assert "modeling_attr_info" in sql
    assert "for_bd" in sql
    assert "model_no" in sql
    assert "group_id" not in sql  # panel has no group_id -> 2-key semi-join only
```

(If `secure_query`'s signature differs, mirror the call used by the other modeling
permission tests in this file.)

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_semantic_domains.py tests/test_permission.py -q`
Expected: the new/updated tests FAIL (panel not yet in the YAML).

- [ ] **Step 4: Add the YAML block**

In `semantic_layer.yaml`, insert after the `modeling_pathology_data` block (before
`gene_info:`):

```yaml
  modeling_panel_data:
    domain: modeling
    desc: 建模-panel检测(模型级，无实验分组)
    access_via: modeling_attr_info
    join_to_hub: [model_uuid, model_no]
    columns:
      model_uuid:     {type: varchar, desc: 模型spine键}
      model_no:       {type: varchar, desc: 建模编号(枢纽连接键)}
      panel:          {type: varchar, desc: 检测panel}
      detection_item: {type: varchar, desc: 检测项}
      update_date:    {type: date, desc: 更新日期}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_semantic_domains.py tests/test_permission.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add semantic_layer.yaml tests/test_semantic_domains.py tests/test_permission.py
git commit -m "feat: add modeling_panel_data (any-visible 2-key permission grain)"
```

---

## Task 2: assemble_context coverage + full suite + ruff + security + docs

**Files:** Modify `tests/test_graph_nodes.py`, `CLAUDE.md`

- [ ] **Step 1: Assert panel shows in the modeling context**

In `tests/test_graph_nodes.py`, extend `test_assemble_context_modeling_has_permission_note`
(or add a focused test) with an assertion that the panel table is now in context:

```python
def test_assemble_context_modeling_includes_panel():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "modeling"
    ctx = assemble_context_node(s, deps)["context"]
    assert "modeling_panel_data" in ctx
    assert "do not" in ctx.lower()  # still access-controlled
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: pass (panel rendered in the modeling schema context).

- [ ] **Step 3: Full offline suite + ruff**

Run: `uv run pytest -q`
Expected: all pass, 9 deselected.

Run: `uv run ruff check src tests && uv run ruff format src tests`
Expected: clean (only test files touched; commit any reformat).

- [ ] **Step 4: Security review**

Dispatch `sql-security-reviewer` focused on the `semantic_layer.yaml` access-rule
change: confirm `modeling_panel_data` is filtered by a 2-key `(model_uuid, model_no)`
EXISTS to `modeling_attr_info` with `for_bd='yes'`, that it cannot be scanned
unfiltered, and that the any-visible grain is the intended (documented) decision.
Address any high-confidence finding.

- [ ] **Step 5: Update CLAUDE.md**

In the modeling bullet, change the `modeling_panel_data` exclusion note to: now
included at the any-visible `(model_uuid, model_no)` 2-key grain (model-level data, no
group_id); remove it from the "deferred" list.

- [ ] **Step 6: Commit + push**

```bash
git add tests/test_graph_nodes.py CLAUDE.md
git commit -m "modeling_panel_data: context test + docs"
git push origin main
```

- [ ] **Step 7: Live (best-effort)**

Through `run_agent` with real deps, ask a panel question (e.g. "modeling 的 panel 和检测项有哪些")
and confirm the secured SQL carries the 2-key `for_bd` EXISTS over
`modeling_attr_info`. Report the SQL + answer. Gateway-flaky → note it; the
deterministic securing is already proven offline.

---

## Notes for the implementer

- **No source changes.** `injection_config_for_domain` + `_exists_via_hub` already
  build the EXISTS from `join_to_hub` generically, so a 2-key entry works as-is.
- The any-visible grain is deliberate (panel is model-level, no group_id) — see the
  spec; do not switch to NOT EXISTS.
- `secure_query` is the one-call bridge in `db_agent.sql.secure`; match the existing
  modeling permission tests' call style if the signature differs from the snippet.
