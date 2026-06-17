# Multi-Domain Routing Implementation Plan (Phase 2, sub-project 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the agent's domain routing from a hardcoded `efficacy` to whatever in-scope domains the semantic layer defines, and bring the `expression` domain online.

**Architecture:** `SemanticLayer.routable_domains()` (non-reference domains with ≥1 defined table) drives the router. `route`/`route_messages` take that list and only accept in-scope domain names; the graph threads `state["domain"]` through context-assembly and guarding. `sql/`, `db/`, `api/`, and `run_agent` are unchanged — `expression` is not access-controlled, so `injection_config_for_domain` already returns `None` (no `for_bd` injection).

**Tech Stack:** Python 3.14 (uv `.venv`), pytest. Spec: `docs/superpowers/specs/2026-06-17-multi-domain-routing-design.md`. Builds on the shipped `semantic/`, `sql/`, `llm/`, `graph/`.

**Conventions:** `from __future__ import annotations` at the top of every module. Run with `uv run`. Offline only (FakeLLM + FakeReplica). Commit + push after each task.

---

### Task 1: `SemanticLayer.routable_domains()`

**Files:**
- Modify: `src/db_agent/semantic/model.py`
- Test: `tests/test_semantic_domains.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_semantic_domains.py`:

```python
from __future__ import annotations

from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


def test_routable_domains_are_efficacy_and_expression():
    names = {d.name for d in LAYER.routable_domains()}
    assert names == {"efficacy", "expression"}


def test_routable_excludes_reference_and_undefined_domains():
    names = {d.name for d in LAYER.routable_domains()}
    assert "reference" not in names      # dictionary domain, never routed
    assert "modeling" not in names       # forward-declared, no tables
    assert "mutation" not in names       # forward-declared, no tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: FAIL with `AttributeError: 'SemanticLayer' object has no attribute 'routable_domains'`.

- [ ] **Step 3: Add the method**

In `src/db_agent/semantic/model.py`, add this method to the `SemanticLayer` class (after `detail_tables_of`):

```python
    def routable_domains(self) -> list[Domain]:
        """Domains the router may pick: non-reference with at least one defined table.

        Forward-declared domains (a hub named but no tables yet) are excluded, so
        adding their tables to the YAML later makes them routable with no code change.
        """
        return [
            d
            for d in self.domains.values()
            if d.name != "reference" and self.tables_in_domain(d.name)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/semantic/model.py tests/test_semantic_domains.py
git commit -F - <<'EOF'
Add SemanticLayer.routable_domains()

Non-reference domains with >=1 defined table -> currently {efficacy, expression}.
Forward-declared modeling/mutation (no tables) are excluded until their tables
are added.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Generalize routing (`prompts.route_messages` + `agent_llm.route`)

**Files:**
- Modify: `src/db_agent/llm/prompts.py`
- Modify: `src/db_agent/llm/agent_llm.py`
- Test: `tests/test_llm_prompts.py`, `tests/test_llm_agent.py`

- [ ] **Step 1: Update the prompt test**

In `tests/test_llm_prompts.py`, add this import at the top:

```python
from db_agent.config import Settings
from db_agent.semantic import load_semantic_layer

DOMAINS = load_semantic_layer(Settings(_env_file=None).semantic_layer_path).routable_domains()
```

Replace the function `test_route_messages_mention_efficacy_and_clarify` with:

```python
def test_route_messages_lists_domains_and_clarify():
    msgs = route_messages("how many models?", DOMAINS)
    assert msgs[0]["role"] == "system"
    text = " ".join(m["content"] for m in msgs).lower()
    assert "efficacy" in text and "expression" in text
    assert "clarify" in text
    assert "how many models?" in msgs[-1]["content"]
```

- [ ] **Step 2: Update the route tests**

In `tests/test_llm_agent.py`, add after the existing imports:

```python
from db_agent.semantic import load_semantic_layer

DOMAINS = load_semantic_layer(SETTINGS.semantic_layer_path).routable_domains()
```

Replace `test_route_efficacy`, `test_route_clarify_extracts_question`, and
`test_route_unexpected_output_falls_back_to_clarify` with:

```python
def test_route_efficacy():
    c = _ScriptedClient("efficacy")
    assert route(c, SETTINGS, "how many models?", DOMAINS) == RouteResult(domain="efficacy")
    assert c.last_model == "qwen-fast"


def test_route_expression():
    c = _ScriptedClient("expression")
    assert route(c, SETTINGS, "TP53 expression?", DOMAINS) == RouteResult(domain="expression")


def test_route_unroutable_domain_is_clarify():
    c = _ScriptedClient("modeling")  # not in the routable set
    res = route(c, SETTINGS, "modeling stuff", DOMAINS)
    assert res.domain is None
    assert res.clarification


def test_route_clarify_extracts_question():
    c = _ScriptedClient("clarify: which drug do you mean?")
    res = route(c, SETTINGS, "how is it?", DOMAINS)
    assert res.domain is None
    assert res.clarification == "which drug do you mean?"


def test_route_unexpected_output_falls_back_to_clarify():
    c = _ScriptedClient("the answer is 42")
    res = route(c, SETTINGS, "what?", DOMAINS)
    assert res.domain is None
    assert res.clarification  # non-empty fallback question
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: FAIL — `route_messages()` / `route()` do not accept the `domains` argument yet.

- [ ] **Step 4: Generalize `route_messages`**

In `src/db_agent/llm/prompts.py`, add the typing import block after `from __future__ import annotations`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_agent.semantic.model import Domain
```

Delete the `_ROUTE_SYSTEM` constant and replace the `route_messages` function with:

```python
def route_messages(question: str, domains: list[Domain]) -> list[dict[str, str]]:
    listing = "\n".join(f"- {d.name}: {d.label}" for d in domains)
    system = (
        "You are a domain router for a mouse tumor-model database agent. The "
        "in-scope domains are:\n"
        f"{listing}\n\n"
        "If the question is answerable from exactly one of these domains, reply "
        "with that domain's name verbatim (e.g. 'efficacy'). Otherwise reply "
        "'clarify: <one short question asking the user to clarify, or stating it "
        "is out of scope>'. Reply with nothing else."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
```

- [ ] **Step 5: Generalize `route`**

In `src/db_agent/llm/agent_llm.py`, add the typing import block after `from __future__ import annotations`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_agent.semantic.model import Domain
```

Replace the `route` function with:

```python
def route(
    client: LLMClient, settings: Settings, question: str, domains: list[Domain]
) -> RouteResult:
    valid = {d.name for d in domains}
    text = client.complete(settings.model_fast, prompts.route_messages(question, domains)).strip()
    low = text.lower()
    if low.startswith("clarify"):
        q = text.split(":", 1)[1].strip() if ":" in text else _CLARIFY_FALLBACK
        return RouteResult(clarification=q or _CLARIFY_FALLBACK)
    for name in valid:
        if low.startswith(name.lower()):
            return RouteResult(domain=name)
    # Unexpected output or an out-of-scope domain name: never guess — ask.
    return RouteResult(clarification=_CLARIFY_FALLBACK)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: PASS (5 prompt + 7 agent = all green).

- [ ] **Step 7: Commit**

```bash
git add src/db_agent/llm/prompts.py src/db_agent/llm/agent_llm.py tests/test_llm_prompts.py tests/test_llm_agent.py
git commit -F - <<'EOF'
Generalize routing over the semantic layer's domains

route_messages/route take the routable domain list, list each domain to the
model, and accept only an in-scope domain name (an out-of-scope name like
'modeling' falls back to clarify). RouteResult.domain may now be any routable
domain.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Thread the domain through the graph nodes

**Files:**
- Modify: `src/db_agent/graph/nodes.py`
- Test: `tests/test_graph_nodes.py`

- [ ] **Step 1: Update / add node tests**

In `tests/test_graph_nodes.py`:

Replace `test_assemble_context_has_descriptions_and_permission_note` with these two tests:

```python
def test_assemble_context_efficacy_has_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "efficacy"
    ctx = assemble_context_node(s, deps)["context"]
    assert "model_efficacy_info" in ctx
    assert "药物名称" in ctx  # column description rendered
    assert "for_bd" in ctx
    assert "do not" in ctx.lower()  # permission note present (access-controlled)


def test_assemble_context_expression_omits_permission_note():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "expression"
    ctx = assemble_context_node(s, deps)["context"]
    assert "model_ccle_expression_data" in ctx
    assert "do not" not in ctx.lower()  # expression is not access-controlled
```

Add a new route test next to the existing route node tests:

```python
def test_route_expression_sets_domain():
    deps = _deps(llm=_LLM({"qwen-fast": ["expression"]}))
    out = route_node(initial_state("TP53 expression?"), deps)
    assert out["domain"] == "expression"
```

Replace `test_guard_ok_sets_secured_sql` with these two tests:

```python
def test_guard_ok_efficacy_injects_permission():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "efficacy"
    s["sql"] = "SELECT drug_name FROM model_efficacy_info"
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "ok"
    assert "for_bd" in out["secured_sql"].lower()


def test_guard_ok_expression_no_permission():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "expression"
    s["sql"] = (
        "SELECT log2tpm FROM model_ccle_expression_data "
        "WHERE gene_symbol = 'TP53' AND model_uuid = 'm1'"
    )
    s["attempts"] = 1
    out = guard_node(s, deps)
    assert out["outcome"] == "ok"
    assert "for_bd" not in out["secured_sql"].lower()
```

In `test_guard_retryable_under_budget` and `test_guard_retryable_at_budget_is_fatal`,
add `s["domain"] = "efficacy"` immediately after the `s = initial_state("q")` line
(so the node has a domain to secure against).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: FAIL — `assemble_context_node`/`guard_node` still use the hardcoded
`_DOMAIN`, so the expression cases don't behave per-domain and route lacks the
expression mapping.

- [ ] **Step 3: Generalize the nodes**

In `src/db_agent/graph/nodes.py`, delete the line `_DOMAIN = "efficacy"`.

Replace `route_node`:

```python
def route_node(state: AgentState, deps: Deps) -> dict:
    res = llm_route(deps.llm, deps.settings, state["question"], deps.layer.routable_domains())
    if res.domain is not None:
        return {"domain": res.domain}
    return {"clarification": res.clarification, "status": "clarify"}
```

Replace `assemble_context_node`:

```python
def assemble_context_node(state: AgentState, deps: Deps) -> dict:
    return {"context": _render_context(deps, state["domain"])}
```

In `guard_node`, change the `secure_query` call from `secure_query(state["sql"],
deps.layer, _DOMAIN)` to:

```python
        secured = secure_query(state["sql"], deps.layer, state["domain"])
```

Replace `_render_context`:

```python
def _render_context(deps: Deps, domain: str) -> str:
    """Render the domain's schema for sql-gen: columns with descriptions, plus —
    only for an access-controlled domain — a note that the permission columns are
    filtered automatically (so the model never filters or guesses them)."""
    tables = deps.layer.tables_in_domain(domain) + deps.layer.reference_tables()
    lines = []
    for t in tables:
        cols = ", ".join(f"{c.name} ({c.desc})" if c.desc else c.name for c in t.columns.values())
        header = f"{t.name}: {cols}" if t.desc is None else f"{t.name} — {t.desc}: {cols}"
        lines.append(header)
    dom = deps.layer.get_domain(domain)
    if dom is not None and dom.access_controlled:
        perm = ", ".join(deps.layer.access_control.fields)
        lines.append(
            f"\nRow-level permissions are already enforced automatically on these "
            f"columns: {perm}. Do NOT add WHERE conditions on them — the system "
            f"applies the correct filter for you."
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: PASS (all node tests green, including the new expression cases).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/nodes.py tests/test_graph_nodes.py
git commit -F - <<'EOF'
Thread state["domain"] through the graph nodes

route_node picks from routable_domains; assemble_context/guard use the chosen
domain; _render_context renders that domain's tables and adds the permission note
only for an access-controlled domain. Drops the hardcoded efficacy constant.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: Expression end-to-end + efficacy regression (full graph)

**Files:**
- Test: `tests/test_graph_chain.py`

- [ ] **Step 1: Add the expression end-to-end test**

In `tests/test_graph_chain.py`, add:

```python
def test_expression_end_to_end_no_permission_injection():
    llm = _LLM(
        {
            "qwen-fast": ["expression"],
            "qwen-code": [
                "SELECT log2tpm FROM model_ccle_expression_data "
                "WHERE gene_symbol = 'TP53' AND model_uuid = 'm1'"
            ],
            "qwen-main": ["log2tpm for TP53 in m1 is 5.2."],
        }
    )
    qr = QueryResult(
        columns=["log2tpm"], rows=[{"log2tpm": 5.2}], rowcount=1,
        truncated=False, sql="SELECT log2tpm", elapsed_ms=1.0,
    )
    res = _run(llm, _Replica([qr]), question="TP53 expression in m1?")
    assert res.status == "answered"
    assert res.answer == "log2tpm for TP53 in m1 is 5.2."
    assert "for_bd" not in (res.sql or "").lower()  # expression: not access-controlled
    assert "model_ccle_expression_data" in res.sql.lower()
```

(The existing `test_happy_path` already covers the efficacy regression — it routes
to `efficacy` and asserts `for_bd` is injected.)

- [ ] **Step 2: Run the chain tests**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: PASS (the 5 existing cases plus the new expression case).

- [ ] **Step 3: Commit**

```bash
git add tests/test_graph_chain.py
git commit -F - <<'EOF'
Add expression end-to-end test; efficacy regression stays green

Full-graph run routing to expression, querying model_ccle_expression_data with a
gene_symbol/model_uuid filter, and confirming no for_bd injection (expression is
not access-controlled). The existing efficacy happy path is the regression.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: Full offline suite + ruff

**Files:** none (verification + docs).

- [ ] **Step 1: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `5 deselected` (integration). All offline tests green,
including the new domain/routing/expression tests and the unchanged efficacy ones.

- [ ] **Step 2: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff check`
reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff
format src tests` and re-run.)

- [ ] **Step 3: Update the README domain note**

In `README.md`, change the efficacy-only framing of the status line to mention
multi-domain. Replace the heading line:

```markdown
## Status — Phase 1 MVP (efficacy domain) — complete
```

with:

```markdown
## Status — Phase 1 MVP complete; Phase 2 in progress (multi-domain routing)
```

And in the chain description, change `route / clarify` context to note routing now
covers the semantic layer's in-scope domains (currently efficacy + expression) by
replacing the line:

```
intent route / clarify → context assembly (yaml) → SQL gen (qwen-code)
```

with:

```
domain route / clarify (efficacy | expression) → context assembly (yaml) → SQL gen (qwen-code)
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -F - <<'EOF'
Note multi-domain routing in README (efficacy + expression)

Routing is now data-driven over the semantic layer's in-scope domains. Full
offline suite green; ruff clean.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

## Self-Review

**Spec coverage:**
- `routable_domains()` data-driven rule (non-reference + has tables) → Task 1. ✅
- `route_messages(question, domains)` lists domains → Task 2. ✅
- `route(..., domains)` accepts only in-scope names, out-of-scope → clarify → Task 2. ✅
- Node domain threading (route_node, assemble_context, guard) + drop `_DOMAIN` → Task 3. ✅
- `_render_context` permission note only for access-controlled domains → Task 3. ✅
- `sql/`, `db/`, `run_agent`, API unchanged → confirmed (no tasks touch them). ✅
- Tests: routable_domains, route_messages, route (incl. modeling→clarify), node render (efficacy note / expression none), guard (efficacy for_bd / expression none), expression end-to-end, efficacy regression → Tasks 1–4. ✅

**Placeholder scan:** No TBD/TODO; every code/test/command/edit step is complete. Task 5 Step 1 uses the deterministic check. ✅

**Type consistency:** `routable_domains() -> list[Domain]`; `route_messages(question, domains: list[Domain])`; `route(client, settings, question, domains) -> RouteResult`; `RouteResult(domain, clarification)`; `route_node`/`assemble_context_node`/`guard_node(state, deps) -> dict`; `_render_context(deps, domain)`; `secure_query(sql, layer, domain)`; `Domain.name`/`.label`/`.access_controlled` — all consistent across tasks and with the shipped `semantic/`, `sql/`, `llm/`, `graph/` code. ✅

**Note:** No dependency changes. `prompts.py`/`agent_llm.py` import `Domain` only under `TYPE_CHECKING` (annotations are strings via `__future__`), so no new import-time coupling. No files under `sql/` change, so the Stop hook does not trigger; the PostToolUse ruff hook runs on each edit. modeling/mutation remain out of scope until their tables are defined; real `resolve_gene` is a separate Phase 2 item.
