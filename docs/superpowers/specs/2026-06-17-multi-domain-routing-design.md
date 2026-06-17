# Design: multi-domain support (data-driven routing + expression domain)

Date: 2026-06-17
Status: Approved (brainstorming) — ready for implementation plan
Scope: Phase 2, first sub-project. Generalize the agent's domain routing from a
hardcoded `efficacy` to whatever domains the semantic layer defines, and bring
the **expression** domain online.

## Goal

Make the chain route over **all in-scope domains the semantic layer defines**,
not just `efficacy`. Today that yields `{efficacy, expression}`; when the
`modeling` / `mutation` tables are later added to `semantic_layer.yaml`, they
become routable with **no code change**.

## Context (confirmed during brainstorming, 2026-06-17)

- `semantic_layer.yaml` declares domains `efficacy`, `modeling`, `expression`,
  `mutation`, `reference`. Only **efficacy** (built) and **expression** (hub
  `model_desc_info`, table `model_ccle_expression_data`) have defined tables.
  `modeling` (`modeling_attr_info`) and `mutation` have **no tables** — they are
  forward declarations awaiting their `models.py`-derived definitions, so they
  are out of scope here.
- `sql/` is already domain-generic: `validation_config_for_domain(layer, domain)`
  and `injection_config_for_domain(layer, domain)` take a domain, and the latter
  returns `None` for non-access-controlled domains (no permission injection). No
  `sql/` changes are needed.
- `expression` is **not** access-controlled → no `for_bd` injection; the
  big-table EXPLAIN guard for `model_ccle_expression_data` already exists.
- **Deferred (not in this sub-project):** real `resolve_gene` (gene-name
  resolution stays a Phase 1 placeholder, so expression is most reliable for
  questions giving an explicit `gene_symbol` / `model_uuid`); the
  `modeling` / `mutation` domains; per-domain access-field generalization (only
  needed once an access-controlled domain other than efficacy is buildable).

## Routable-domains rule (data-driven)

Add a pure method to `SemanticLayer`:

```python
def routable_domains(self) -> list[Domain]:
    """Domains the router may pick: non-reference with at least one defined table."""
    return [
        d for d in self.domains.values()
        if d.name != "reference" and self.tables_in_domain(d.name)
    ]
```

This excludes `reference` (a dictionary domain, never routed) and any
forward-declared domain that has no tables yet (`modeling`, `mutation`). Adding
their tables later flips them into the routable set automatically.

## Routing generalization (`llm/`)

- `prompts.route_messages(question, domains)` — `domains` is the routable
  `list[Domain]`. The system prompt lists each domain's `name (label)` and
  instructs the model to reply with **exactly one domain name** if the question
  fits it, otherwise `clarify: <short question>`.
- `agent_llm.route(client, settings, question, domains)` — passes `domains` to
  the prompt, then maps the model output to a `RouteResult`:
  - the model's reply is matched (case-insensitive, leading token) against the
    set of valid domain names; a match → `RouteResult(domain=<name>)`.
  - `clarify: ...` → `RouteResult(clarification=...)`.
  - anything else, **including a domain name not in the routable set** (e.g. the
    model says `modeling`) → `RouteResult(clarification=<fallback>)`. Never route
    to a domain that isn't in scope.

`RouteResult` is unchanged (`domain` / `clarification`); `domain` may now be any
routable domain name, not just `efficacy`.

## Node generalization (`graph/`)

- Drop the module-level `_DOMAIN = "efficacy"` constant.
- `route_node(state, deps)`: call `route(deps.llm, deps.settings, state["question"],
  deps.layer.routable_domains())`; on a domain → `{"domain": <name>}`, on clarify
  → `{"clarification": ..., "status": "clarify"}`.
- `assemble_context_node`: `{"context": _render_context(deps, state["domain"])}`.
- `guard_node`: `secure_query(state["sql"], deps.layer, state["domain"])`.
- `_render_context(deps, domain)`:
  - render `tables_in_domain(domain)` + the reference tables, each as
    `name(col (desc), ...)` (unchanged format).
  - append the "permission columns are auto-filtered; do not filter them" note
    **only when** `deps.layer.get_domain(domain).access_controlled` is true. For a
    non-access-controlled domain (expression) the note is omitted (those columns
    don't exist there).

`run_agent` and the API are **unchanged** — the domain is decided inside the
graph.

## What stays unchanged

`sql/` (validator / permission / secure), `db/`, `observability/`, `api/`,
`run_agent`'s signature, and the `AgentState` shape (it already carries
`domain`). The efficacy path keeps injecting `for_bd = 'yes'` exactly as before.

## Testing (offline — no DB, no LLM)

1. `SemanticLayer.routable_domains()` → exactly `{efficacy, expression}` (a set
   of names); excludes `reference`, `modeling`, `mutation`.
2. `prompts.route_messages(q, domains)` includes each routable domain's name and
   label, and the question.
3. `agent_llm.route` with a fake client:
   - reply `expression` → `RouteResult(domain="expression")`.
   - reply `efficacy` → `RouteResult(domain="efficacy")`.
   - reply `modeling` (not routable) → clarification (never a domain).
   - reply `clarify: which gene?` → clarification with the text.
   - unexpected reply → clarification fallback.
4. `graph.nodes`:
   - `route_node` sets `domain` from the model's choice.
   - `_render_context` for `expression` lists `model_ccle_expression_data` and
     **omits** the permission note; for `efficacy` it **includes** the note.
   - `guard_node` on an expression query (`SELECT ... FROM
     model_ccle_expression_data WHERE gene_symbol = '...' AND model_uuid = '...'`)
     returns `outcome == "ok"` with **no** `for_bd` in the secured SQL.
5. Full-graph (`run_agent` with fakes):
   - **expression end-to-end**: route → expression, generate a filtered
     `model_ccle_expression_data` query, execute (fake `QueryResult`), answer →
     `status == "answered"`, no `for_bd` in `res.sql`.
   - **efficacy regression**: the existing happy path still routes to efficacy
     and injects `for_bd = 'yes'`.
6. Existing `route` / `route_messages` / node / chain tests are updated for the
   new `domains` parameter.

## Out of scope (deferred)

`modeling` / `mutation` domains (await table definitions), real `resolve_gene`,
per-domain access-field generalization, and pgvector example retrieval.

## Open questions

None. All decisions are resolved above.
