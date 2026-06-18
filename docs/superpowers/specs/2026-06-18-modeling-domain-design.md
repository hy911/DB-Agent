# Modeling Domain Design

**Date:** 2026-06-18
**Status:** Approved (architecture section), pending spec review
**Builds on:** the data-driven domain machinery proven by `expression` and
`mutation`, and the permission injector already shipped for `efficacy`.

## Goal

Add the `modeling` domain — PDX/CDX model-establishment (建模) characterization
data — so questions like "show the tumor-volume growth curve for model X's
modeling group" or "how many modeling groups are visible to BD?" route to it,
get **row-level permissions injected deterministically**, generate SQL, and
answer. modeling is the last forward-declared domain.

## Key architectural claim

This is expected to be a **pure `semantic_layer.yaml` addition + tests + live
verification, with zero Python source changes** — and it is the **first
access-controlled domain added purely through configuration**, so unlike
expression/mutation (which exercised the no-op permission path) it exercises the
real permission-injection path end-to-end. That is a stronger proof of the
data-driven design.

Why no code change is needed:

- **Routing** — `routable_domains()` returns every non-reference domain with ≥1
  table; adding modeling's tables makes it auto-routable
  (`{efficacy, expression, mutation, modeling}`).
- **Permission injection** — `injection_config_for_domain(layer, "modeling")`
  already reads `dom.access_controlled` + `dom.hub` from the domain, derives
  detail tables via `layer.detail_tables_of(hub)` (tables whose
  `access_via == hub`), and reads each detail table's `join_to_hub` keys — all
  from YAML. The hub filter and the correlated `EXISTS` semi-join are built
  generically in `sql/permission.py`. The only hardcoded values are
  `access_field="for_bd"` / `access_value="yes"`, and `modeling_attr_info`
  **uses exactly that column and value** (verified live: 578 rows with
  `for_bd='yes'`). So no injector change is required.
- **No gene resolution** — modeling has no `gene_symbol` column, so
  `is_gene_bearing("modeling")` is `False`; the gene nodes are skipped.
- **No big-table gate** — none of the modeling tables are flagged `big_table`
  (largest is ~71K rows); the EXPLAIN gate does not apply.

If any of these needs a code change during implementation, STOP and re-examine —
the design assumes none are needed. (`sql/permission.py` in particular must NOT
change; if it appears to need to, that is a security-relevant finding to surface.)

## Tables in scope

Columns are pinned to the **live DB `information_schema`** (2026-06-18), NOT
`models.py`, which has drifted (e.g. `modeling_survival_data.survival` is `text`
in the DB, not the decimal `models.py` implies; dates are `timestamp`).

### `modeling_attr_info` — hub (domain `modeling`, `access_controlled: true`)

Joins the spine on `model_uuid`. Detail join keys to it: `model_no`, `group_id`
(modeling's `model_no` is the analogue of efficacy's `efficacy_num`).

Columns to expose: `model_uuid, model_no, group_id, amount, route, strain, sex,
vendor, passage, days_when_tumor_volume_100mm3, days_when_tumor_volume_500mm3,
days_when_tumor_volume_1000mm3, quality, for_bd, for_control, for_model`.

### Three detail tables (domain `modeling`, `access_via: modeling_attr_info`, `join_to_hub: [model_uuid, model_no, group_id]`)

Each has no permission column and is filtered via the correlated `EXISTS` back to
the hub. All three carry `model_uuid, model_no, group_id` (verified live).

- `modeling_tumor_volume_growth_curve_data`: `model_uuid, model_no, group_id,
  days, date, body_part, tumor_volume, avg, sd` (~71K rows).
- `modeling_body_weight_growth_curve_data`: `model_uuid, model_no, group_id,
  days, date, body_weight, avg, sd` (~50K rows).
- `modeling_survival_data`: `model_uuid, model_no, group_id, animal_id, survival`
  (~362 rows; `animal_id` and `survival` are `text` in the DB).

## Permission injection (automatic, from YAML)

For any query touching modeling tables, `secure_query(sql, layer, "modeling")`
injects:

- Hub: `AND modeling_attr_info.for_bd = 'yes'`.
- Each detail table `d`:

  ```sql
  AND EXISTS (
    SELECT 1 FROM modeling_attr_info AS _perm
    WHERE _perm.model_uuid = d.model_uuid
      AND _perm.model_no   = d.model_no
      AND _perm.group_id   = d.group_id
      AND _perm.for_bd     = 'yes'
  )
  ```

`EXISTS` (a semi-join) is used so detail rows are never multiplied (which would
corrupt AVG/COUNT) — identical to the efficacy treatment, only the middle join
key differs (`model_no` vs `efficacy_num`).

## Data flow (all reused, no new nodes)

```
route → modeling
  → assemble_context (renders hub + 3 detail tables + the permission note)
  → generate_sql (qwen-code)
  → guard (sqlglot validate; permission injection: hub for_bd + EXISTS on detail)
  → execute (read replica)
  → answer
```

modeling is NOT gene-bearing, so `after_route` sends it straight to
`assemble_context` (skipping extract/resolve), exactly like efficacy.

## Out of scope (deferred, not built)

- The other modeling detail tables — `modeling_facs_growth_curve_data`,
  `modeling_tumor_weight_data`, `modeling_avg_radiance_data`,
  `modeling_total_flux_data`, `modeling_elisa_data`, `modeling_panel_data`,
  `modeling_pathology_data`. Same pattern, addable later with zero code.
- `clinical_attr_info`, `modeling_tm_info`, `model_info_group*` — adjacent but
  not part of the core characterization flow.
- All `m_`-prefixed mirror tables and `*_stats` tables (per CLAUDE.md: ignore).

## Testing

- **Offline (faked LLM, no DB):**
  - `routable_domains()` now yields `{efficacy, expression, mutation, modeling}`.
  - `is_gene_bearing("modeling") is False`; `after_route` for modeling →
    `assemble_context` (not `extract_genes`).
  - `injection_config_for_domain(layer, "modeling")` returns a config with
    `hub_table == "modeling_attr_info"` and the 3 detail tables mapped to
    `("model_uuid", "model_no", "group_id")`.
  - `secure_query` on a hub query injects `modeling_attr_info.for_bd = 'yes'`.
  - `secure_query` on a detail-table query injects an `EXISTS` semi-join
    referencing `modeling_attr_info` and `_perm.for_bd = 'yes'`, and does NOT
    inject a bare `for_bd` on the detail table.
  - `assemble_context` for modeling renders the hub + 3 detail tables AND the
    permission note ("do not add WHERE conditions on them …"), like efficacy.
  - End-to-end (fake LLM streams route→sql→answer): a modeling query answers and
    the SQL that ran contains `for_bd`.
- **Live (real LLM + DB):**
  - A modeling characterization query (e.g. "tumor-volume growth curve for the
    modeling groups of model `<uuid>`") → `answered`, the executed SQL filters
    `for_bd = 'yes'` (hub) or carries the `EXISTS` (detail), and rows come back.
  - Confirm the loader still boots (the `_validate` pass checks every detail
    table's `access_via` hub exists and each `join_to_hub` key is present on both
    the detail and the hub — all verified present live).

## Security review

modeling is the project's **second access-controlled domain** and the first added
via config. After implementation, invoke the `sql-security-reviewer` subagent to
audit that the injected SQL is correct and fail-closed: hub filtered, every detail
table semi-joined on all three keys + `for_bd='yes'`, no detail-row multiplication,
idempotent. `sql/permission.py` must be unchanged.

## Risks

- **`for_bd` values:** live data has `for_bd` in {`yes`, `false`, `no`}; only
  `'yes'` is visible. Verified the hub has 578 `'yes'` rows, so live e2e will
  return data. (If a chosen model_uuid happens to have no `'yes'` group, the
  query correctly returns 0 rows — pick a uuid known to have visible groups, or
  let the e2e discover one.)
- **Column drift:** columns pinned to the live DB on 2026-06-18; re-pin if the DB
  changes.
- **Join-key correctness:** the EXISTS correlates on `(model_uuid, model_no,
  group_id)`; an offline test asserts the injected SQL names all three, so a
  wrong/short key list fails the suite rather than silently under-filtering.
