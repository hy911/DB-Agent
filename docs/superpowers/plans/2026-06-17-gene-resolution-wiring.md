# Gene-Resolution Wiring Implementation Plan (Plan B of gene resolution)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `resolve_gene` into the question flow so a gene-bearing-domain question (expression) has its gene mentions extracted by the LLM, resolved deterministically to canonical symbols, and either injected into the SQL-gen context or clarified.

**Architecture:** Two new graph nodes (`extract_genes` LLM, `resolve_genes` deterministic) run only for gene-bearing domains, gated by `SemanticLayer.is_gene_bearing`. The resolver is injected via `Deps.resolve_gene` (default = the real `resolve_gene`) so the full graph is offline-testable with a fake resolver. The LLM only spots candidate gene strings; resolution stays deterministic (fixed decision #5).

**Tech Stack:** Python 3.14 (uv `.venv`), LangGraph, pytest. Spec: `docs/superpowers/specs/2026-06-17-gene-resolution-design.md`. Builds on Plan A (`db.resolve_gene`).

**Conventions:** `from __future__ import annotations` at the top of every module. Run with `uv run`. Offline tests inject FakeLLM + a fake resolver (no DB, no LLM). Commit + push after each task.

---

### Task 1: `SemanticLayer.is_gene_bearing`

**Files:**
- Modify: `src/db_agent/semantic/model.py`
- Test: `tests/test_semantic_domains.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_semantic_domains.py`, add:

```python
def test_is_gene_bearing():
    assert LAYER.is_gene_bearing("expression") is True  # has a gene_symbol column
    assert LAYER.is_gene_bearing("efficacy") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_semantic_domains.py::test_is_gene_bearing -q`
Expected: FAIL with `AttributeError: 'SemanticLayer' object has no attribute 'is_gene_bearing'`.

- [ ] **Step 3: Add the method**

In `src/db_agent/semantic/model.py`, add to the `SemanticLayer` class (after
`routable_domains`):

```python
    def is_gene_bearing(self, domain: str) -> bool:
        """True if any table in the domain has the gene_key (gene_symbol) column."""
        return any(t.has_column(self.gene_key) for t in self.tables_in_domain(domain))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/semantic/model.py tests/test_semantic_domains.py
git commit -F - <<'EOF'
Add SemanticLayer.is_gene_bearing

True for domains whose tables include the gene_key column (gene_symbol) —
currently expression. Drives whether the graph runs gene resolution.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Gene-extraction prompt + LLM task

**Files:**
- Modify: `src/db_agent/llm/prompts.py`
- Modify: `src/db_agent/llm/agent_llm.py`
- Modify: `src/db_agent/llm/__init__.py`
- Test: `tests/test_llm_prompts.py`, `tests/test_llm_agent.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_llm_prompts.py`, add:

```python
def test_extract_genes_messages_include_question():
    from db_agent.llm.prompts import extract_genes_messages

    msgs = extract_genes_messages("expression of p53?")
    assert msgs[0]["role"] == "system"
    assert "gene" in " ".join(m["content"] for m in msgs).lower()
    assert "expression of p53?" in msgs[-1]["content"]
```

In `tests/test_llm_agent.py`, add:

```python
def test_extract_genes_parses_comma_list():
    from db_agent.llm.agent_llm import extract_genes

    c = _ScriptedClient("p53, EGFR")
    assert extract_genes(c, SETTINGS, "p53 and EGFR?") == ["p53", "EGFR"]
    assert c.last_model == "qwen-fast"


def test_extract_genes_none_returns_empty():
    from db_agent.llm.agent_llm import extract_genes

    assert extract_genes(_ScriptedClient("NONE"), SETTINGS, "how many models?") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: FAIL — `extract_genes_messages` / `extract_genes` are not defined.

- [ ] **Step 3: Add the prompt builder**

In `src/db_agent/llm/prompts.py`, add:

```python
def extract_genes_messages(question: str) -> list[dict[str, str]]:
    system = (
        "You extract gene names or symbols mentioned in the user's question for a "
        "gene-expression database. List each gene mention exactly as the user "
        "wrote it, comma-separated. If no gene is mentioned, reply with the single "
        "word NONE. Reply with nothing else."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
```

- [ ] **Step 4: Add the LLM task**

In `src/db_agent/llm/agent_llm.py`, add:

```python
def extract_genes(client: LLMClient, settings: Settings, question: str) -> list[str]:
    text = client.complete(settings.model_fast, prompts.extract_genes_messages(question)).strip()
    if not text or text.strip().upper() == "NONE":
        return []
    return [g.strip() for g in text.split(",") if g.strip()]
```

- [ ] **Step 5: Export it**

In `src/db_agent/llm/__init__.py`, add `extract_genes` to the import from
`agent_llm` and to `__all__` (keeping it sorted):

```python
from db_agent.llm.agent_llm import RouteResult, answer, extract_genes, generate_sql, route
```

and add `"extract_genes"` to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: PASS (all green).

- [ ] **Step 7: Commit**

```bash
git add src/db_agent/llm/prompts.py src/db_agent/llm/agent_llm.py src/db_agent/llm/__init__.py tests/test_llm_prompts.py tests/test_llm_agent.py
git commit -F - <<'EOF'
Add gene-mention extraction (prompt + extract_genes)

The LLM lists gene mentions verbatim (comma-separated, or NONE). It only spots
candidate strings; canonical resolution stays deterministic in resolve_gene.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: State fields + injected resolver on Deps

**Files:**
- Modify: `src/db_agent/graph/state.py`
- Test: `tests/test_graph_state.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_graph_state.py`, add:

```python
def test_initial_state_has_gene_fields():
    s = initial_state("q")
    assert s["extracted_genes"] == []
    assert s["resolved_genes"] == {}


def test_deps_default_resolve_gene_is_callable():
    from db_agent.config import Settings
    from db_agent.graph.state import Deps

    deps = Deps(llm=object(), replica=object(), layer=object(), settings=Settings(_env_file=None))
    assert callable(deps.resolve_gene)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_state.py -q`
Expected: FAIL — `AgentState` has no `extracted_genes`/`resolved_genes` and `Deps`
has no `resolve_gene`.

- [ ] **Step 3: Update state.py**

In `src/db_agent/graph/state.py`:

Change the `db` import line to also bring in the resolver and types:

```python
from db_agent.db import GeneResolution, QueryResult, ReadReplica
from db_agent.db import resolve_gene as _default_resolve_gene
```

Add `Callable` import after `from __future__ import annotations`:

```python
from collections.abc import Callable
```

In the `AgentState` TypedDict, add these two fields (after `context`):

```python
    extracted_genes: list[str]
    resolved_genes: dict[str, str]
```

In `initial_state(...)`, add these two entries (after `context=None,`):

```python
        extracted_genes=[],
        resolved_genes={},
```

In the `Deps` dataclass, add the resolver field (after `settings: Settings`):

```python
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] = _default_resolve_gene
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph_state.py -q`
Expected: PASS (the new 2 plus the existing state tests).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/state.py tests/test_graph_state.py
git commit -F - <<'EOF'
Add gene state fields and an injected resolver on Deps

AgentState gains extracted_genes/resolved_genes; Deps gains resolve_gene
(default = the real db.resolve_gene) so the graph is offline-testable with a fake
resolver.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: Gene nodes + context injection

**Files:**
- Modify: `src/db_agent/graph/nodes.py`
- Test: `tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_graph_nodes.py`:

Change the `_deps` helper to accept a resolver:

```python
def _deps(llm=None, replica=None, resolve_gene=None):
    kwargs = dict(llm=llm, replica=replica, layer=LAYER, settings=SETTINGS)
    if resolve_gene is not None:
        kwargs["resolve_gene"] = resolve_gene
    return Deps(**kwargs)
```

Add these imports near the top (with the other node imports):

```python
from db_agent.db.gene_resolver import GeneMatch, GeneResolution
from db_agent.graph.nodes import (
    after_resolve,
    extract_genes_node,
    resolve_genes_node,
)
```

Add these tests:

```python
def test_extract_genes_node():
    deps = _deps(llm=_LLM({"qwen-fast": ["p53, EGFR"]}))
    out = extract_genes_node(initial_state("p53 and EGFR?"), deps)
    assert out["extracted_genes"] == ["p53", "EGFR"]


def test_resolve_genes_node_all_resolved_injects_map():
    def fake_resolver(replica, name):
        return GeneResolution(name, "resolved", "TP53", [GeneMatch("TP53", "human", "symbol_exact", 1.0)])

    deps = _deps(resolve_gene=fake_resolver)
    s = initial_state("q")
    s["extracted_genes"] = ["p53"]
    out = resolve_genes_node(s, deps)
    assert out["resolved_genes"] == {"p53": "TP53"}
    assert "status" not in out  # continues, no clarify


def test_resolve_genes_node_ambiguous_clarifies():
    def fake_resolver(replica, name):
        return GeneResolution(
            name, "ambiguous", None,
            [GeneMatch("TP53", "human", "symbol_exact", 1.0),
             GeneMatch("Trp53", "mouse", "symbol_exact", 1.0)],
        )

    deps = _deps(resolve_gene=fake_resolver)
    s = initial_state("q")
    s["extracted_genes"] = ["p53"]
    out = resolve_genes_node(s, deps)
    assert out["status"] == "clarify"
    assert "TP53" in out["clarification"] and "Trp53" in out["clarification"]


def test_after_resolve_branches():
    s = initial_state("q")
    assert after_resolve(s) == "assemble_context"
    s["status"] = "clarify"
    assert after_resolve(s) == END


def test_after_route_gene_bearing_goes_to_extract():
    s = initial_state("q")
    s["domain"] = "expression"
    assert after_route(s, _deps()) == "extract_genes"
    s2 = initial_state("q")
    s2["domain"] = "efficacy"
    assert after_route(s2, _deps()) == "assemble_context"


def test_assemble_context_injects_resolved_genes():
    deps = _deps()
    s = initial_state("q")
    s["domain"] = "expression"
    s["resolved_genes"] = {"p53": "TP53"}
    ctx = assemble_context_node(s, deps)["context"]
    assert "p53 -> TP53" in ctx or "p53 → TP53" in ctx
```

Also update `test_after_route_branches` (the existing one) — `after_route` now
takes `deps`. Replace it with:

```python
def test_after_route_branches():
    deps = _deps()
    s = initial_state("q")
    assert after_route(s, deps) == "assemble_context"
    s["status"] = "clarify"
    assert after_route(s, deps) == END
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: FAIL — the new nodes/`after_resolve` don't exist and `after_route` does
not accept `deps`.

- [ ] **Step 3: Update nodes.py**

In `src/db_agent/graph/nodes.py`:

Add to the LLM imports:

```python
from db_agent.llm import extract_genes as llm_extract_genes
```

Replace `after_route` with the gene-aware version:

```python
def after_route(state: AgentState, deps: Deps) -> str:
    if state["status"] == "clarify":
        return END
    if deps.layer.is_gene_bearing(state["domain"]):
        return "extract_genes"
    return "assemble_context"
```

Add the two new nodes and the resolve router (place them after `route_node`):

```python
def extract_genes_node(state: AgentState, deps: Deps) -> dict:
    return {"extracted_genes": llm_extract_genes(deps.llm, deps.settings, state["question"])}


def resolve_genes_node(state: AgentState, deps: Deps) -> dict:
    resolved: dict[str, str] = {}
    for name in state["extracted_genes"]:
        res = deps.resolve_gene(deps.replica, name)
        if res.status == "resolved":
            resolved[name] = res.symbol
        elif res.status == "ambiguous":
            cands = ", ".join(sorted({m.symbol for m in res.candidates})[:5])
            return {
                "clarification": f"The gene '{name}' is ambiguous — did you mean one of: {cands}?",
                "status": "clarify",
            }
        else:  # unknown
            return {
                "clarification": f"I couldn't find a gene matching '{name}'. Please check the name.",
                "status": "clarify",
            }
    return {"resolved_genes": resolved}


def after_resolve(state: AgentState) -> str:
    return END if state["status"] == "clarify" else "assemble_context"
```

Change `assemble_context_node` to pass `resolved_genes`:

```python
def assemble_context_node(state: AgentState, deps: Deps) -> dict:
    return {"context": _render_context(deps, state["domain"], state["resolved_genes"])}
```

Change `_render_context`'s signature and append the resolved-gene line. Replace the
function header and add the injection before the final `return`:

```python
def _render_context(deps: Deps, domain: str, resolved_genes: dict[str, str]) -> str:
```

and immediately before `return "\n".join(lines)` add:

```python
    if resolved_genes:
        mapping = ", ".join(f"{name} -> {symbol}" for name, symbol in resolved_genes.items())
        lines.append(f"\nResolved gene names (use these canonical symbols): {mapping}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph_nodes.py -q`
Expected: PASS (all node tests green).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/nodes.py tests/test_graph_nodes.py
git commit -F - <<'EOF'
Add gene extract/resolve nodes and context injection

extract_genes_node (LLM) + resolve_genes_node (deterministic, via deps.resolve_gene):
all resolved -> inject canonical-symbol map into context; any ambiguous/unknown ->
clarify. after_route now sends gene-bearing domains through the gene nodes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: Wire the graph + run_agent resolver param + chain tests

**Files:**
- Modify: `src/db_agent/graph/build.py`
- Test: `tests/test_graph_chain.py`

- [ ] **Step 1: Update the chain tests**

In `tests/test_graph_chain.py`:

Add a resolver import and a helper near the top (after the existing imports):

```python
from db_agent.db.gene_resolver import GeneMatch, GeneResolution


def _resolver(mapping):
    def resolve(replica, name):
        sym = mapping.get(name)
        if sym is None:
            return GeneResolution(name, "unknown", None, [])
        return GeneResolution(name, "resolved", sym, [GeneMatch(sym, "human", "symbol_exact", 1.0)])

    return resolve
```

Change `_run` to thread an optional resolver:

```python
def _run(llm, replica, question="how many models for BD?", resolve_gene=None):
    return run_agent(
        question, llm=llm, replica=replica, layer=LAYER, settings=SETTINGS,
        resolve_gene=resolve_gene,
    )
```

Replace `test_expression_end_to_end_no_permission_injection` with (it now also
feeds the gene-extraction model_fast call and a fake resolver):

```python
def test_expression_end_to_end_resolves_gene_and_injects():
    llm = _LLM(
        {
            "qwen-fast": ["expression", "p53"],  # route, then extract_genes
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
    res = _run(llm, _Replica([qr]), question="p53 expression in m1?",
               resolve_gene=_resolver({"p53": "TP53"}))
    assert res.status == "answered"
    assert res.answer == "log2tpm for TP53 in m1 is 5.2."
    assert "for_bd" not in (res.sql or "").lower()


def test_expression_unknown_gene_clarifies():
    llm = _LLM({"qwen-fast": ["expression", "notagene"]})
    res = _run(llm, _Replica([]), question="notagene expression?",
               resolve_gene=_resolver({}))  # resolves nothing -> unknown
    assert res.status == "clarify"
    assert "notagene" in res.clarification
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: FAIL — `run_agent` does not accept `resolve_gene`, and the graph has no
gene nodes wired.

- [ ] **Step 3: Wire the graph + run_agent**

In `src/db_agent/graph/build.py`:

Add these imports (with the existing ones):

```python
from collections.abc import Callable

from db_agent.db import GeneResolution
```

Register the two new nodes and rewire the edges. In `build_graph`, after the
`g.add_node("route", ...)` line add:

```python
    g.add_node("extract_genes", partial(nodes.extract_genes_node, deps=deps))
    g.add_node("resolve_genes", partial(nodes.resolve_genes_node, deps=deps))
```

Replace the `route` conditional edge and add the gene edges. Change:

```python
    g.add_conditional_edges("route", nodes.after_route, ["assemble_context", END])
```

to:

```python
    g.add_conditional_edges(
        "route",
        partial(nodes.after_route, deps=deps),
        ["extract_genes", "assemble_context", END],
    )
    g.add_edge("extract_genes", "resolve_genes")
    g.add_conditional_edges(
        "resolve_genes", nodes.after_resolve, ["assemble_context", END]
    )
```

Add a `resolve_gene` parameter to `run_agent` and thread it into `Deps`. Replace
the `run_agent` signature and `Deps(...)` construction:

```python
def run_agent(
    question: str,
    *,
    llm: LLMClient,
    replica: ReadReplica,
    layer: SemanticLayer,
    settings: Settings,
    observer: Observer | None = None,
    resolve_gene: Callable[[ReadReplica, str], GeneResolution] | None = None,
) -> AgentResult:
    deps_kwargs = {"llm": llm, "replica": replica, "layer": layer, "settings": settings}
    if resolve_gene is not None:
        deps_kwargs["resolve_gene"] = resolve_gene
    deps = Deps(**deps_kwargs)
    graph = build_graph(deps)
    final = graph.invoke(initial_state(question))
    if observer is not None:
        try:
            observer(RunRecord.from_state(final))
        except Exception:
            pass  # observability is best-effort; never break a good answer
    return to_result(final)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: PASS (the efficacy cases unchanged, the two expression cases green).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/build.py tests/test_graph_chain.py
git commit -F - <<'EOF'
Wire gene extract/resolve nodes into the graph + run_agent resolver param

Gene-bearing domains route route -> extract_genes -> resolve_genes ->
(clarify | assemble_context); efficacy is unchanged. run_agent gains an optional
resolve_gene override for offline testing (default = the real resolver).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 6: Full offline suite + ruff + live end-to-end

**Files:** none (verification).

- [ ] **Step 1: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `9 deselected` (integration). All offline tests green
including the new gene-wiring tests; efficacy and expression regressions intact.

- [ ] **Step 2: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff check`
reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff
format src tests` and re-run.)

- [ ] **Step 3: Live end-to-end by synonym (real LLM + DB)**

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
try:
    res = run_agent(
        "What is the EGFR expression (log2tpm) in model 23c5b76a3abd4da38e979881650bc443?",
        llm=LiteLLMClient(s), replica=replica,
        layer=load_semantic_layer(s.semantic_layer_path), settings=s,
    )
    print("status :", res.status)
    print("answer :", res.answer)
    print("clarify:", res.clarification)
    print("sql    :", res.sql)
finally:
    replica.close()
PY
```

Expected: `status` is `answered` (the SQL filters on `gene_symbol = 'EGFR'` and the
model_uuid), or `clarify` if the model extracted an ambiguous gene. Report the
printed result. Do not commit anything (no code change).

---

## Self-Review

**Spec coverage (Plan B portions):**
- `SemanticLayer.is_gene_bearing` (data-driven gene-bearing detection) → Task 1. ✅
- `extract_genes_messages` + `extract_genes` (LLM spots mentions only) → Task 2. ✅
- AgentState `extracted_genes`/`resolved_genes`; injected `Deps.resolve_gene` → Task 3. ✅
- `extract_genes_node`, `resolve_genes_node` (all-resolved inject / any non-unique clarify), `after_route` gene branch, `after_resolve`, context injection → Task 4. ✅
- Graph wiring (route → gene nodes → clarify|assemble) + `run_agent` resolver param → Task 5. ✅
- Offline tests (is_gene_bearing, extract, resolve node resolved/ambiguous, after_route/after_resolve, context injection, expression-by-synonym end-to-end, unknown-gene clarify, efficacy regression) → Tasks 1–5. ✅
- Live end-to-end by synonym → Task 6. ✅

**Placeholder scan:** No TBD/TODO; every code/test/command/edit step is complete. Task 6 Step 1 uses the deterministic check. ✅

**Type consistency:** `is_gene_bearing(domain) -> bool`; `extract_genes(client, settings, question) -> list[str]`; `Deps.resolve_gene: Callable[[ReadReplica, str], GeneResolution]`; `resolve_genes_node`/`extract_genes_node(state, deps) -> dict`; `after_route(state, deps) -> str`; `after_resolve(state) -> str`; `_render_context(deps, domain, resolved_genes)`; `run_agent(..., resolve_gene=None)`; `GeneResolution(query, status, symbol, candidates)` / `GeneMatch(symbol, species, via, score)` — consistent across tasks and with Plan A's shipped `db.resolve_gene`. ✅

**Note:** `after_route` becomes a `partial(..., deps=deps)` conditional-edge function (like the nodes), so it can consult `deps.layer.is_gene_bearing`. The efficacy path is unchanged (not gene-bearing → straight to `assemble_context`). No files under `sql/` change, so the Stop hook does not trigger; the PostToolUse ruff hook runs on each edit. modeling/mutation auto-qualify for gene resolution once they gain a `gene_symbol` column.
