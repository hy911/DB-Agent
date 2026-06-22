# Modeling Detail Tables (batch 2) Design

**Date:** 2026-06-18
**Status:** Approved (design + panel decision), pending spec review
**Extends:** `2026-06-18-modeling-domain-design.md` — the modeling domain (hub
`modeling_attr_info` + 3 detail tables) is already live. This adds 5 more detail
tables under the same access-controlled pattern.

## Goal

Add 5 more `modeling` detail tables so FACS / imaging / ELISA / pathology
characterization data is queryable, with the same deterministic permission
injection (hub `for_bd='yes'` + correlated `EXISTS` semi-join on
`(model_uuid, model_no, group_id)`) — **zero Python source changes**.

## Tables in scope (5)

All five carry the three join keys `(model_uuid, model_no, group_id)` (verified
live) and have no permission column of their own, so each gets
`access_via: modeling_attr_info`, `join_to_hub: [model_uuid, model_no, group_id]`.
Columns pinned to the live DB `information_schema` (2026-06-18):

- `modeling_facs_growth_curve_data` (~3.8K) — FACS: `animal_id, detection_item,
  tissue_type, date, val`.
- `modeling_avg_radiance_data` (~3.3K) — imaging (longitudinal): `animal_id,
  days, date, avg_radiance`.
- `modeling_total_flux_data` (~2K) — imaging (longitudinal): `animal_id, days,
  date, total_flux`.
- `modeling_elisa_data` (~122) — ELISA: `animal_id, detection_item, tissue_type,
  date, val`.
- `modeling_pathology_data` (~12) — pathology (cross-sectional): `animal_id,
  detection_item, val`.

None is a big table; no EXPLAIN gate applies. The permission injector already
handles all of them generically once they are in the YAML (proven by the first
modeling batch + the SQL-security review).

## Explicitly excluded: `modeling_panel_data`

`modeling_panel_data` lacks a `group_id` column (it has only `model_no`,
`panel`, `detection_item`). The standard 3-key semi-join cannot apply. Filtering
it on `(model_uuid, model_no)` only would make its permission grain **coarser**
than every other modeling table (model-level, not group-level) — a permission-
policy change, not a mechanical add. **Decision (user-confirmed): exclude
`modeling_panel_data` from this batch.** Revisit separately if panel data is ever
needed, with an explicit grain decision.

## Architecture / data flow

No change. modeling routing, the permission note in context, and the injector are
all already in place. These 5 tables join the existing `modeling` domain; they
appear in modeling context and get the same hub `for_bd='yes'` + detail `EXISTS`
treatment automatically.

## Testing

- **Offline:** `detail_tables_of("modeling_attr_info")` now returns all 8 detail
  tables (3 existing + 5 new), each with `join_to_hub == (model_uuid, model_no,
  group_id)`; `secure_query` on one new table (e.g. `modeling_facs_growth_curve_data`)
  injects the correct `EXISTS` semi-join and no bare `for_bd` on the detail.
- **Full offline suite + ruff** stay green.
- **Live (real DB):** secure + execute one new detail query (e.g. FACS for a
  `for_bd='yes'` model) and confirm the injected `EXISTS` runs and returns rows.
- **SQL security review:** the injection path is unchanged and was already
  audited SOUND for the modeling pattern; a fresh full review is not required for
  same-pattern table additions, but the offline `secure_query` assertion + the
  live execute confirm correctness. (If the reviewer hook fires on the
  `semantic_layer.yaml` access-rule change, run it.)

## Risks

- **Column drift:** columns pinned to the live DB on 2026-06-18; re-pin if it
  changes.
- **Panel grain:** addressed by exclusion above — do not silently add panel with
  a 2-key filter.
