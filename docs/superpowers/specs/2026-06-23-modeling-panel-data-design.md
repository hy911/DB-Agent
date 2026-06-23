# Add modeling_panel_data to the modeling Domain — Design

**Date:** 2026-06-23
**Status:** Approved (design + permission-grain decision), pending spec review
**Scope:** Bring `modeling_panel_data` into the access-controlled `modeling` domain.
Pure `semantic_layer.yaml` change — no source changes (the permission injector is
already generic over the number of join keys).

## Permission-grain decision (the blocker, now resolved)

`modeling_panel_data` is **model-level** data (panel / detection items per model
build) with columns `model_uuid, model_no, panel, detection_item, update_date,
push_id` — it has **no `group_id`**, so it cannot use the standard 3-key
`(model_uuid, model_no, group_id)` semi-join the other modeling detail tables use.

The hub `modeling_attr_info` carries `for_bd` at the
`(model_uuid, model_no, group_id)` grain. The only keys panel shares with the hub are
`(model_uuid, model_no)`. **Decision (user, 2026-06-23): any-visible grain** — a panel
row is visible if **any** group under its `(model_uuid, model_no)` is `for_bd='yes'`.
Rationale: panel data is model-level (no group dimension), so model-grain visibility
is its natural grain; and it reuses the existing `EXISTS` semi-join semantics exactly
(just two keys instead of three), keeping the permission model uniform.

## Change

Add one table block to `semantic_layer.yaml` under `tables:`:

```yaml
  modeling_panel_data:
    domain: modeling
    access_via: modeling_attr_info     # no own permission column; filter via the hub
    join_to_hub: [model_uuid, model_no]
    columns:
      model_uuid:     {type: varchar, desc: 模型spine键}
      model_no:       {type: varchar, desc: 建模编号(枢纽连接键)}
      panel:          {type: varchar, desc: 检测panel}
      detection_item: {type: varchar, desc: 检测项}
      update_date:    {type: date,    desc: 更新日期}
```

(`id` and `push_id` are omitted, matching how the other modeling detail tables drop
surrogate/bookkeeping columns.)

## How it works (no code change)

`injection_config_for_domain` reads `access_via` + `join_to_hub` from the YAML; the
detail map becomes `{..., "modeling_panel_data": ("model_uuid", "model_no")}`.
`_exists_via_hub` loops over the join keys, so it emits a **2-key** correlated EXISTS
back to `modeling_attr_info` with `for_bd = 'yes'` — a semi-join (no row
multiplication), tagged for idempotency like the others. A `SELECT … FROM
modeling_panel_data …` is secured to:

```sql
SELECT … FROM modeling_panel_data
WHERE … AND EXISTS (
  SELECT 1 FROM modeling_attr_info <tag>
  WHERE <tag>.model_uuid = modeling_panel_data.model_uuid
    AND <tag>.model_no  = modeling_panel_data.model_no
    AND <tag>.for_bd = 'yes')
```

The big-table EXPLAIN gate does not apply (panel is not flagged `big_table`).

## Testing

- **semantic:** the `modeling` domain's `tables_in_domain` now includes
  `modeling_panel_data`; it is a detail table of `modeling_attr_info` with join keys
  `(model_uuid, model_no)`.
- **permission injection (pure, offline):** a `SELECT … FROM modeling_panel_data`
  gets a 2-key `EXISTS … modeling_attr_info … for_bd = 'yes'`; idempotent (a second
  secure pass does not double-inject); a join key count of 2 (not 3) is asserted.
- **assemble_context:** modeling context now lists `modeling_panel_data` and still
  carries the access-controlled permission note.
- **full offline suite + ruff** stay green (existing modeling chain unchanged).
- **security review:** `sql-security-reviewer` over the `semantic_layer.yaml` access
  rule change — confirm the 2-key EXISTS filters panel correctly and there is no path
  for an unfiltered panel scan.
- **live (best-effort):** a panel question (e.g. "列出 model_no 为 X 的 panel 和检测项")
  → the secured SQL carries the 2-key `for_bd` EXISTS; report it + the answer.

## Out of scope

- No change to the permission injector (already key-count generic).
- No change to the graph or prompts.
- The stricter "all-visible" (NOT EXISTS) grain was considered and not chosen.
