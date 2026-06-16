# db/ Layer (Read-Only Execution Boundary) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `src/db_agent/db/`, the single I/O boundary that runs secured SQL against the read replica with DB-level read-only enforcement, `statement_timeout`, a node-type EXPLAIN gate, and SQLSTATE-based error mapping.

**Architecture:** Pure decision logic (`result.py`, `mapping.py`, `explain.py`) is split from psycopg I/O (`replica.py`) so the security-relevant pieces are unit-tested offline (no DB), while `replica.py` stays thin and is exercised later via integration tests.

**Tech Stack:** Python 3.14 (uv-managed `.venv`), psycopg3 + `psycopg_pool` (already in deps), pytest, ruff. Reference spec: `docs/superpowers/specs/2026-06-16-db-layer-readonly-execution-design.md`.

**Conventions:** Every module starts with `from __future__ import annotations`. Frozen dataclasses for data. Guards fail closed. Run everything with `uv run`. Commit after each task (commit + push is the project default).

---

### Task 1: `QueryResult` data object

**Files:**
- Create: `src/db_agent/db/__init__.py` (empty package marker for now)
- Create: `src/db_agent/db/result.py`
- Test: `tests/test_db_result.py`

- [ ] **Step 1: Create the empty package marker**

Create `src/db_agent/db/__init__.py` with a single line:

```python
from __future__ import annotations
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_db_result.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from db_agent.db.result import QueryResult


def test_query_result_holds_fields():
    r = QueryResult(
        columns=["a", "b"],
        rows=[{"a": 1, "b": 2}],
        rowcount=1,
        truncated=False,
        sql="SELECT 1",
        elapsed_ms=1.5,
    )
    assert r.columns == ["a", "b"]
    assert r.rows == [{"a": 1, "b": 2}]
    assert r.rowcount == 1
    assert r.truncated is False
    assert r.sql == "SELECT 1"
    assert r.elapsed_ms == 1.5


def test_query_result_is_frozen():
    r = QueryResult(columns=[], rows=[], rowcount=0, truncated=False, sql="", elapsed_ms=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.rowcount = 5  # type: ignore[misc]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_db_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.db.result'`

- [ ] **Step 4: Write minimal implementation**

Create `src/db_agent/db/result.py`:

```python
"""The value object returned by a successful read-replica execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool       # rowcount >= the `limit` passed to execute() (else False)
    sql: str
    elapsed_ms: float
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_db_result.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/db_agent/db/__init__.py src/db_agent/db/result.py tests/test_db_result.py
git commit -F - <<'EOF'
Add QueryResult value object for db/ layer

Frozen dataclass carrying columns/rows/rowcount/truncated/sql/elapsed_ms,
returned by ReadReplica.execute.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: SQLSTATE error mapping

**Files:**
- Create: `src/db_agent/db/mapping.py`
- Test: `tests/test_db_mapping.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_mapping.py`:

```python
from __future__ import annotations

import pytest

from db_agent.db.mapping import classify_db_error


@pytest.mark.parametrize(
    "sqlstate, expected",
    [
        ("42703", ("bad_column", True)),
        ("42883", ("bad_function", True)),
        ("42804", ("bad_type", True)),
        ("42P01", ("bad_table", True)),
        ("42601", ("bad_syntax", True)),
        ("57014", ("timeout", False)),
        ("42501", ("forbidden", False)),
        ("08006", ("connection", False)),   # class 08 -> connection
        ("08003", ("connection", False)),
        ("99999", ("db_error", False)),     # unknown -> fatal
        (None, ("db_error", False)),        # missing -> fatal
    ],
)
def test_classify_db_error(sqlstate, expected):
    assert classify_db_error(sqlstate) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_mapping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.db.mapping'`

- [ ] **Step 3: Write minimal implementation**

Create `src/db_agent/db/mapping.py`:

```python
"""Map a PostgreSQL SQLSTATE to a GuardError (category, retryable) decision.

retryable=True means the model's SQL was wrong in a way regeneration could fix
(bad column/function/type/table/syntax). Everything else is fatal — timeouts,
privilege errors, connection failures, and anything unrecognized fail closed and
are never fed back to the self-correction loop.
"""

from __future__ import annotations

# 42xxx-class mistakes in the generated SQL — safe to feed back for a retry.
_RETRYABLE: dict[str, str] = {
    "42703": "bad_column",
    "42883": "bad_function",
    "42804": "bad_type",
    "42P01": "bad_table",
    "42601": "bad_syntax",
}

# Known-fatal states.
_FATAL: dict[str, str] = {
    "57014": "timeout",        # query canceled (statement_timeout)
    "42501": "forbidden",      # insufficient privilege
}


def classify_db_error(sqlstate: str | None) -> tuple[str, bool]:
    """Return (category, retryable) for a SQLSTATE. Fail closed on the unknown."""
    if sqlstate is None:
        return ("db_error", False)
    if sqlstate in _RETRYABLE:
        return (_RETRYABLE[sqlstate], True)
    if sqlstate in _FATAL:
        return (_FATAL[sqlstate], False)
    if sqlstate.startswith("08"):
        return ("connection", False)
    return ("db_error", False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db_mapping.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/mapping.py tests/test_db_mapping.py
git commit -F - <<'EOF'
Add SQLSTATE -> GuardError classification for db/ layer

42xxx generation mistakes are retryable; timeout/privilege/connection and
unknown states fail closed (fatal).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: EXPLAIN plan analysis (the big-table gate)

**Files:**
- Create: `src/db_agent/db/explain.py`
- Test: `tests/test_db_explain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_explain.py`:

```python
from __future__ import annotations

import pytest

from db_agent.db.explain import evaluate_explain, seq_scanned_big_tables
from db_agent.sql.errors import GuardError

BIG = frozenset({"model_ccle_expression_data"})


def _plan(node: dict) -> list[dict]:
    """Wrap a plan node the way EXPLAIN (FORMAT JSON) returns it."""
    return [{"Plan": node}]


def test_seq_scan_on_big_table_is_rejected():
    plan = _plan({"Node Type": "Seq Scan", "Relation Name": "model_ccle_expression_data"})
    with pytest.raises(GuardError) as exc:
        evaluate_explain(plan, BIG)
    assert exc.value.retryable is False
    assert exc.value.category == "big_table_scan"


def test_index_scan_on_big_table_passes():
    plan = _plan({"Node Type": "Index Scan", "Relation Name": "model_ccle_expression_data"})
    assert evaluate_explain(plan, BIG) is None


def test_seq_scan_on_non_big_table_passes():
    plan = _plan({"Node Type": "Seq Scan", "Relation Name": "model_efficacy_info"})
    assert evaluate_explain(plan, BIG) is None


def test_nested_seq_scan_under_gather_is_caught():
    plan = _plan(
        {
            "Node Type": "Gather",
            "Plans": [
                {
                    "Node Type": "Nested Loop",
                    "Plans": [
                        {"Node Type": "Index Scan", "Relation Name": "model_efficacy_info"},
                        {"Node Type": "Seq Scan", "Relation Name": "model_ccle_expression_data"},
                    ],
                }
            ],
        }
    )
    hits = seq_scanned_big_tables(plan, BIG)
    assert hits == ["model_ccle_expression_data"]
    with pytest.raises(GuardError):
        evaluate_explain(plan, BIG)


def test_empty_plan_passes():
    assert evaluate_explain([], BIG) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_explain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.db.explain'`

- [ ] **Step 3: Write minimal implementation**

Create `src/db_agent/db/explain.py`:

```python
"""Big-table EXPLAIN gate (pure).

When sql/ flagged a big-table scan, db/ runs ``EXPLAIN (FORMAT JSON)`` (no
ANALYZE, so the query never executes) and passes the plan here. We refuse a plan
that *sequentially* scans a big table. A parallel sequential scan still reports
``Node Type == "Seq Scan"`` (parallelism is expressed by an enclosing ``Gather``),
so the single node-type check covers it.
"""

from __future__ import annotations

from collections.abc import Iterator

from db_agent.sql.errors import GuardError


def _root(plan: object) -> dict | None:
    """Normalize an EXPLAIN (FORMAT JSON) payload to its root plan node."""
    if isinstance(plan, list):
        return _root(plan[0]) if plan else None
    if isinstance(plan, dict):
        if "Plan" in plan:
            return plan["Plan"]
        if "Node Type" in plan:
            return plan
    return None


def _walk(node: dict) -> Iterator[dict]:
    yield node
    for child in node.get("Plans", []) or []:
        yield from _walk(child)


def seq_scanned_big_tables(plan: object, big_tables: frozenset[str]) -> list[str]:
    """Return big-table relation names reached by a Seq Scan in this plan."""
    root = _root(plan)
    if root is None:
        return []
    return [
        node["Relation Name"]
        for node in _walk(root)
        if node.get("Node Type") == "Seq Scan"
        and node.get("Relation Name") in big_tables
    ]


def evaluate_explain(plan: object, big_tables: frozenset[str]) -> None:
    """Raise a fatal GuardError if the plan sequentially scans a big table."""
    hits = seq_scanned_big_tables(plan, big_tables)
    if hits:
        names = ", ".join(sorted(set(hits)))
        raise GuardError(
            "big_table_scan",
            f"sequential scan on big table(s) {names} is not allowed; "
            "add a model_uuid/gene_symbol filter",
            retryable=False,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db_explain.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/explain.py tests/test_db_explain.py
git commit -F - <<'EOF'
Add node-type EXPLAIN gate for db/ layer

Pure plan-tree walk rejecting a Seq Scan on a big table (parallel seq scan
included). Fatal, non-retryable.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: `ReadReplica` — the psycopg I/O orchestration

**Files:**
- Create: `src/db_agent/db/replica.py`
- Test: `tests/test_db_replica_smoke.py`

> **Note:** `replica.py` is the I/O boundary and is NOT exercised against a real DB in the offline suite (per the spec). The smoke test only confirms it imports and constructs a pool **without opening it** (no network). Real execution is integration-tested later.

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_replica_smoke.py`:

```python
from __future__ import annotations

from db_agent.config import Settings
from db_agent.db.replica import ReadReplica


def test_readreplica_constructs_without_connecting():
    # Default Settings() needs no env; pool is created with open=False so no
    # network access happens here.
    replica = ReadReplica(Settings(pool_min_size=1, pool_max_size=4))
    try:
        assert replica.pool.min_size == 1
        assert replica.pool.max_size == 4
    finally:
        replica.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_replica_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db_agent.db.replica'`

- [ ] **Step 3: Write minimal implementation**

Create `src/db_agent/db/replica.py`:

```python
"""The read-replica I/O boundary.

Owns a psycopg connection pool to the restricted read-only replica role. Each
connection is configured read-only with a statement_timeout (belt-and-suspenders
over the role). ``execute`` runs an already-secured SQL string, optionally
EXPLAIN-gating a flagged big-table scan first, and maps any database error to a
GuardError that drives the self-correction loop.

This module is the only place that touches the database. It stays thin and
delegates every decision to the pure modules (explain, mapping).
"""

from __future__ import annotations

import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from db_agent.config import Settings
from db_agent.db.explain import evaluate_explain
from db_agent.db.mapping import classify_db_error
from db_agent.db.result import QueryResult
from db_agent.sql.errors import GuardError


class ReadReplica:
    def __init__(self, settings: Settings) -> None:
        self._timeout_ms = settings.statement_timeout_ms
        self.pool = ConnectionPool(
            conninfo=settings.replica_dsn,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            kwargs={"autocommit": False, "row_factory": dict_row},
            configure=self._configure,
            open=False,
        )

    def _configure(self, conn: psycopg.Connection) -> None:
        # read_only must be set before any transaction begins.
        conn.read_only = True
        conn.execute("SET statement_timeout = %s", (self._timeout_ms,))
        conn.commit()

    def open(self) -> None:
        self.pool.open()

    def close(self) -> None:
        self.pool.close()

    def execute(
        self,
        sql: str,
        *,
        needs_explain: bool,
        big_tables: frozenset[str],
        limit: int | None = None,
    ) -> QueryResult:
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                if needs_explain:
                    cur.execute("EXPLAIN (FORMAT JSON) " + sql)
                    evaluate_explain(_plan_payload(cur.fetchone()), big_tables)
                start = time.perf_counter()
                cur.execute(sql)
                rows = cur.fetchall()
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                columns = [d.name for d in (cur.description or [])]
        except GuardError:
            raise  # EXPLAIN gate already produced a fatal GuardError
        except PoolTimeout as e:
            raise GuardError("pool_timeout", str(e).strip(), retryable=False) from e
        except psycopg.Error as e:
            category, retryable = classify_db_error(e.sqlstate)
            raise GuardError(category, str(e).strip(), retryable=retryable) from e

        truncated = limit is not None and len(rows) >= limit
        return QueryResult(
            columns=columns,
            rows=rows,
            rowcount=len(rows),
            truncated=truncated,
            sql=sql,
            elapsed_ms=elapsed_ms,
        )


def _plan_payload(row: dict[str, object] | None) -> object:
    """Pull the JSON plan out of an EXPLAIN (FORMAT JSON) dict_row result.

    The single column is named "QUERY PLAN"; its value is the plan list.
    """
    if not row:
        return []
    return next(iter(row.values()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db_replica_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/replica.py tests/test_db_replica_smoke.py
git commit -F - <<'EOF'
Add ReadReplica I/O boundary for db/ layer

Sync psycopg ConnectionPool to the read-only replica: per-connection read_only
+ statement_timeout, EXPLAIN gate before a flagged big-table scan, and
SQLSTATE/pool-timeout error mapping to GuardError. Thin orchestration over the
pure explain/mapping modules.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: Public exports + full-suite green

**Files:**
- Modify: `src/db_agent/db/__init__.py`

- [ ] **Step 1: Write the package exports**

Replace `src/db_agent/db/__init__.py` with:

```python
"""Read-replica execution boundary — the only module that touches the database.

Pure decision logic (explain, mapping, result) is importable without a DB; the
psycopg I/O lives in ReadReplica.
"""

from __future__ import annotations

from db_agent.db.explain import evaluate_explain, seq_scanned_big_tables
from db_agent.db.mapping import classify_db_error
from db_agent.db.replica import ReadReplica
from db_agent.db.result import QueryResult

__all__ = [
    "QueryResult",
    "ReadReplica",
    "classify_db_error",
    "evaluate_explain",
    "seq_scanned_big_tables",
]
```

- [ ] **Step 2: Verify the package imports**

Run: `uv run python -c "from db_agent.db import ReadReplica, QueryResult, evaluate_explain, classify_db_error; print('imports OK')"`
Expected: prints `imports OK`

- [ ] **Step 3: Run the full offline suite**

Run: `uv run pytest -q`
Expected: PASS — all prior tests plus the new db/ tests (32 existing + 19 new = 51 passed). No DB or LLM accessed.

- [ ] **Step 4: Lint and format clean**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`

(If `ruff check` reports fixable issues, run `uv run ruff check --fix src tests && uv run ruff format src tests` and re-run.)

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/__init__.py
git commit -F - <<'EOF'
Export db/ public API and finalize the layer

ReadReplica, QueryResult, and the pure explain/mapping helpers. Full offline
suite green; ruff clean.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

## Self-Review

**Spec coverage:**
- Module decomposition (explain/mapping/result/replica/__init__) → Tasks 1–5. ✅
- Sync psycopg `ConnectionPool` + per-connection `read_only` + `statement_timeout` → Task 4 `_configure`. ✅
- Public interface `execute(sql, *, needs_explain, big_tables, limit=None)` + `close()` → Task 4. ✅ (`open()` added for explicit pool lifecycle, matching the spec's "open the pool explicitly".)
- `QueryResult` shape → Task 1. ✅
- Node-type EXPLAIN gate, parallel-scan coverage, never-execute-on-hit → Task 3 + Task 4 (EXPLAIN before execute, GuardError short-circuits). ✅
- SQLSTATE error mapping table → Task 2. ✅
- Offline testing for explain + mapping; replica not in DB suite → Tasks 2–4. ✅

**Placeholder scan:** No TBD/TODO; every code and test step shows complete content. ✅

**Type consistency:** `evaluate_explain(plan, big_tables) -> None`, `seq_scanned_big_tables(...) -> list[str]`, `classify_db_error(sqlstate) -> tuple[str, bool]`, `QueryResult(columns, rows, rowcount, truncated, sql, elapsed_ms)`, and `ReadReplica.execute(sql, *, needs_explain, big_tables, limit=None)` are referenced identically across the plan, the `__init__` exports, and the smoke test (`replica.pool`). ✅

**Notes:** No dependency changes — `psycopg[binary,pool]>=3.2` is already in `pyproject.toml`. The new files live under `db/`, so the `sql/` PreToolUse guard and Stop-hook review do not trigger; the PostToolUse ruff hook runs on each edit.
