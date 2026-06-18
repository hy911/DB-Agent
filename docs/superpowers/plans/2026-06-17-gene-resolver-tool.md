# resolve_gene Tool Implementation Plan (Plan A of gene resolution)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic `resolve_gene` lookup tool — given a gene name, resolve it to the canonical `gene_info."Symbol"` via case-sensitive exact match (symbol + synonym) with a pg_trgm fuzzy fallback offered only as clarification candidates.

**Architecture:** A pure decision function (`_decide`) is offline-TDD'd; the I/O (`resolve_gene` + a new `ReadReplica.fetch` for trusted parameterized queries) is integration-tested against the live DB. Case is significant — it encodes species (human `EGFR` vs mouse `Egfr`), so matching is case-sensitive. The semantic layer's wrong `gene_info` column name is corrected.

**Tech Stack:** Python 3.14 (uv `.venv`), psycopg3, pytest. Spec: `docs/superpowers/specs/2026-06-17-gene-resolution-design.md`. Live DB: PG16 `db_dev`, pg_trgm installed.

**Conventions:** `from __future__ import annotations` at the top of every module. Run with `uv run`. Offline suite stays DB-free; the resolver's real queries are `-m integration`. Commit + push after each task.

---

### Task 1: Correct the gene_info column name in the semantic layer

**Files:**
- Modify: `semantic_layer.yaml`
- Test: `tests/test_semantic_domains.py`

The real `gene_info` column is `"Symbol"` (capital S); the YAML says `symbol`.

- [ ] **Step 1: Add the failing test**

In `tests/test_semantic_domains.py`, add:

```python
def test_gene_info_symbol_column_matches_db_casing():
    t = LAYER.get_table("gene_info")
    assert t.has_column("Symbol")  # matches the real DB column
    assert not t.has_column("symbol")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_semantic_domains.py::test_gene_info_symbol_column_matches_db_casing -q`
Expected: FAIL — the loaded `gene_info` has `symbol`, not `Symbol`.

- [ ] **Step 3: Fix the YAML**

In `semantic_layer.yaml`, under `gene_info:` → `columns:`, change the key
`symbol:` to `Symbol:`:

```yaml
      Symbol:       {type: text, desc: 基因官方符号(连接键), unique: true}
```

Then update the two `relationships` lines and the `lookup_tools.resolve_gene`
references that point at `gene_info.symbol` to `gene_info.Symbol`:

```yaml
  - {from: model_ccle_expression_data.gene_symbol, to: gene_info.Symbol, type: many_to_one}
  - {from: gene_synonyms.gene_symbol, to: gene_info.Symbol, type: many_to_one}
```

```yaml
  resolve_gene: {source: [gene_synonyms.synonym, gene_info.Symbol], output: gene_info.Symbol, method: 精确(大小写敏感)+pg_trgm模糊}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_semantic_domains.py -q`
Expected: PASS (3 passed — the 2 existing domain tests plus the new casing test).

- [ ] **Step 5: Commit**

```bash
git add semantic_layer.yaml tests/test_semantic_domains.py
git commit -F - <<'EOF'
Fix gene_info column casing in semantic layer (symbol -> Symbol)

The real DB column is "Symbol" (capital S); the YAML declared symbol. Corrected
the column and the relationships/lookup_tools references.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Resolver data types + the pure `_decide` rule

**Files:**
- Create: `src/db_agent/db/gene_resolver.py`
- Test: `tests/test_gene_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gene_resolver.py`:

```python
from __future__ import annotations

from db_agent.db.gene_resolver import GeneMatch, GeneResolution, _decide


def _gm(symbol, *, via="symbol_exact", score=1.0, species="human"):
    return GeneMatch(symbol=symbol, species=species, via=via, score=score)


def test_unique_exact_is_resolved():
    res = _decide("EGFR", [_gm("EGFR")], [])
    assert isinstance(res, GeneResolution)
    assert res.status == "resolved"
    assert res.symbol == "EGFR"
    assert res.query == "EGFR"


def test_multiple_distinct_exact_is_ambiguous():
    res = _decide("x", [_gm("TP53"), _gm("Trp53", species="mouse")], [])
    assert res.status == "ambiguous"
    assert res.symbol is None
    assert {m.symbol for m in res.candidates} == {"TP53", "Trp53"}


def test_same_symbol_twice_still_resolved():
    # symbol-exact and synonym-exact both pointing at one symbol
    res = _decide("EGFR", [_gm("EGFR"), _gm("EGFR", via="synonym_exact")], [])
    assert res.status == "resolved"
    assert res.symbol == "EGFR"


def test_fuzzy_only_is_ambiguous_sorted_desc():
    res = _decide("egfr", [], [_gm("Egfr", via="fuzzy", score=0.5),
                               _gm("EGFR", via="fuzzy", score=0.8)])
    assert res.status == "ambiguous"
    assert res.symbol is None
    assert [m.symbol for m in res.candidates] == ["EGFR", "Egfr"]


def test_no_match_is_unknown():
    res = _decide("zzz", [], [])
    assert res.status == "unknown"
    assert res.symbol is None
    assert res.candidates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gene_resolver.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.db.gene_resolver'`.

- [ ] **Step 3: Write the types and `_decide`**

Create `src/db_agent/db/gene_resolver.py`:

```python
"""Deterministic gene-name resolution (CLAUDE.md fixed decision #5).

Case is significant — it encodes species in this DB (human EGFR vs mouse Egfr) —
so exact matching is case-sensitive. A pg_trgm fuzzy match is only ever offered as
a clarification candidate, never auto-resolved. `_decide` is pure; `resolve_gene`
runs the parameterized queries (Task 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_agent.db.replica import ReadReplica


@dataclass(frozen=True)
class GeneMatch:
    symbol: str  # canonical gene_info."Symbol"
    species: str | None
    via: str  # "symbol_exact" | "synonym_exact" | "fuzzy"
    score: float  # 1.0 for exact; similarity() for fuzzy


@dataclass(frozen=True)
class GeneResolution:
    query: str
    status: str  # "resolved" | "ambiguous" | "unknown"
    symbol: str | None
    candidates: list[GeneMatch]


def _decide(query: str, exact: list[GeneMatch], fuzzy: list[GeneMatch]) -> GeneResolution:
    distinct = {m.symbol for m in exact}
    if len(distinct) == 1:
        return GeneResolution(query, "resolved", next(iter(distinct)), list(exact))
    if len(distinct) > 1:
        return GeneResolution(query, "ambiguous", None, list(exact))
    if fuzzy:
        ranked = sorted(fuzzy, key=lambda m: m.score, reverse=True)
        return GeneResolution(query, "ambiguous", None, ranked)
    return GeneResolution(query, "unknown", None, [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_gene_resolver.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/gene_resolver.py tests/test_gene_resolver.py
git commit -F - <<'EOF'
Add gene-resolver types and the pure _decide rule

GeneMatch/GeneResolution and _decide: unique case-sensitive exact -> resolved;
multiple distinct -> ambiguous; fuzzy-only -> ambiguous (sorted); none -> unknown.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: `ReadReplica.fetch` + `resolve_gene` (I/O) + integration tests

**Files:**
- Modify: `src/db_agent/db/replica.py`
- Modify: `src/db_agent/db/gene_resolver.py`
- Test: `tests/integration/test_gene_resolver_integration.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_gene_resolver_integration.py`:

```python
from __future__ import annotations

import pytest

from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.db.gene_resolver import resolve_gene

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def replica():
    r = ReadReplica(get_settings())
    r.open()
    yield r
    r.close()


def test_fetch_is_parameterized(replica):
    rows = replica.fetch('SELECT "Symbol" AS s FROM gene_info WHERE "Symbol" = %s', ("EGFR",))
    assert rows and rows[0]["s"] == "EGFR"


def test_resolve_exact_human(replica):
    res = resolve_gene(replica, "EGFR")
    assert res.status == "resolved"
    assert res.symbol == "EGFR"


def test_resolve_lowercase_falls_to_fuzzy_ambiguous(replica):
    res = resolve_gene(replica, "egfr")  # no case-exact match
    assert res.status == "ambiguous"
    assert any(m.symbol == "EGFR" for m in res.candidates)


def test_resolve_unknown(replica):
    res = resolve_gene(replica, "zzzznotagene")
    assert res.status == "unknown"
    assert res.candidates == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -m integration tests/integration/test_gene_resolver_integration.py -q`
Expected: FAIL — `ReadReplica` has no `fetch`, and `resolve_gene` is not defined.

- [ ] **Step 3: Add `ReadReplica.fetch`**

In `src/db_agent/db/replica.py`, add the import at the top (after
`from __future__ import annotations`):

```python
from collections.abc import Sequence
```

Add this method to the `ReadReplica` class (after `execute`):

```python
    def fetch(self, sql: str, params: Sequence[object] = ()) -> list[dict[str, object]]:
        """Run a trusted, parameterized read-only query and return rows as dicts.

        For hand-written internal queries (e.g. gene resolution) — NOT for
        LLM-generated SQL, which must go through `execute`'s securing/EXPLAIN path.
        The value is always bound as a parameter, never interpolated.
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
```

- [ ] **Step 4: Add `resolve_gene`**

In `src/db_agent/db/gene_resolver.py`, append:

```python
def resolve_gene(
    replica: ReadReplica, name: str, *, fuzzy_threshold: float = 0.4, limit: int = 5
) -> GeneResolution:
    exact: list[GeneMatch] = []
    for row in replica.fetch(
        'SELECT "Symbol" AS symbol, species FROM gene_info WHERE "Symbol" = %s', (name,)
    ):
        exact.append(
            GeneMatch(symbol=row["symbol"], species=row.get("species"), via="symbol_exact", score=1.0)
        )
    for row in replica.fetch(
        "SELECT gene_symbol AS symbol, species FROM gene_synonyms WHERE synonym = %s", (name,)
    ):
        exact.append(
            GeneMatch(symbol=row["symbol"], species=row.get("species"), via="synonym_exact", score=1.0)
        )

    fuzzy: list[GeneMatch] = []
    if not exact:
        rows = replica.fetch(
            'SELECT "Symbol" AS symbol, species, similarity("Symbol", %s) AS sim '
            'FROM gene_info WHERE similarity("Symbol", %s) > %s ORDER BY sim DESC LIMIT %s',
            (name, name, fuzzy_threshold, limit),
        )
        fuzzy = [
            GeneMatch(symbol=r["symbol"], species=r.get("species"), via="fuzzy", score=float(r["sim"]))
            for r in rows
        ]

    return _decide(name, exact, fuzzy)
```

- [ ] **Step 5: Run the integration tests (live DB)**

Run: `uv run pytest -m integration tests/integration/test_gene_resolver_integration.py -q`
Expected: PASS (4 passed). If the DB is unreachable, STOP and report — do not
loosen the assertions.

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/db/replica.py src/db_agent/db/gene_resolver.py tests/integration/test_gene_resolver_integration.py
git commit -F - <<'EOF'
Add ReadReplica.fetch and resolve_gene (case-sensitive exact + pg_trgm fuzzy)

fetch runs trusted parameterized read-only queries (gene name always bound).
resolve_gene does case-sensitive symbol/synonym exact match, then a similarity()
fuzzy fallback offered only as candidates. Integration-verified live: EGFR
resolves, egfr -> fuzzy candidates, gibberish -> unknown.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: Public exports + full offline suite + ruff

**Files:**
- Modify: `src/db_agent/db/__init__.py`

- [ ] **Step 1: Add exports**

In `src/db_agent/db/__init__.py`, add the gene-resolver exports. Add this import
with the existing ones:

```python
from db_agent.db.gene_resolver import GeneMatch, GeneResolution, resolve_gene
```

and add `"GeneMatch"`, `"GeneResolution"`, `"resolve_gene"` to `__all__` (keeping
it alphabetically sorted).

- [ ] **Step 2: Verify the package imports**

Run: `uv run python -c "from db_agent.db import resolve_gene, GeneResolution, GeneMatch; print('imports OK')"`
Expected: prints `imports OK`.

- [ ] **Step 3: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS — the `_decide` + semantic tests are green and the new gene
integration tests are deselected (now `9 deselected`: 5 prior + 4 new).

- [ ] **Step 4: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If `ruff check`
reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff
format src tests` and re-run.)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/__init__.py
git commit -F - <<'EOF'
Export resolve_gene / GeneResolution / GeneMatch from db/

Full offline suite green; gene integration tests deselected by default; ruff
clean.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

## Self-Review

**Spec coverage (Plan A portions):**
- Semantic-layer `gene_info."Symbol"` correction → Task 1. ✅
- `GeneMatch` / `GeneResolution` + pure `_decide` rule (resolved/ambiguous/unknown; fuzzy-only ambiguous; fuzzy never auto-resolved) → Task 2. ✅
- `ReadReplica.fetch` parameterized trusted query → Task 3. ✅
- `resolve_gene` case-sensitive exact (symbol+synonym) + pg_trgm `similarity()` fuzzy fallback → Task 3. ✅
- Offline `_decide` tests + integration resolve tests (EGFR resolved, egfr fuzzy-ambiguous, gibberish unknown, fetch smoke) → Tasks 2 & 3. ✅
- Plan B (graph wiring, is_gene_bearing, extract/resolve nodes) → **out of scope here**; separate plan. ✅

**Placeholder scan:** No TBD/TODO; every code/test/command step is complete. Task 4 Step 3 uses the deterministic check. ✅

**Type consistency:** `GeneMatch(symbol, species, via, score)`; `GeneResolution(query, status, symbol, candidates)`; `_decide(query, exact, fuzzy) -> GeneResolution`; `resolve_gene(replica, name, *, fuzzy_threshold=0.4, limit=5) -> GeneResolution`; `ReadReplica.fetch(sql, params=()) -> list[dict]` — used identically across tasks. The fuzzy SQL uses `similarity()` (function, not the `%` operator) to avoid psycopg placeholder clashes. ✅

**Note:** `gene_resolver.py` imports `ReadReplica` only under `TYPE_CHECKING` (annotations are strings via `__future__`) to avoid coupling; the resolver is duck-typed on `.fetch`. Task 3 touches `db/` (not `sql/`), so the Stop hook does not trigger. Integration tests are gated by the existing `tests/integration/conftest.py` DSN check and the `integration` marker.
