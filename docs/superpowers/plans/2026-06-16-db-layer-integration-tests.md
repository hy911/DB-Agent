# db/ Layer Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live-PostgreSQL integration tests for `ReadReplica`, isolated from the offline suite, covering the I/O paths (pool, DB-level read-only, statement_timeout, EXPLAIN gate, SQLSTATE mapping) that could not be unit-tested without a DB.

**Architecture:** Integration tests live in `tests/integration/`, are marked `@pytest.mark.integration`, and are deselected by default (`addopts = -m "not integration"`) so a bare `uv run pytest` stays offline. A `conftest.py` provides a `replica` fixture and skips the integration tests when `DBAGENT_REPLICA_DSN` is unset. Tasks 1–4 are fully offline/deterministic; Task 5 is the only one that touches the live DB.

**Tech Stack:** Python 3.14 (uv `.venv`), pytest, psycopg3, the existing `db_agent.db` package. Spec: `docs/superpowers/specs/2026-06-16-db-layer-integration-tests-design.md`.

**Conventions:** `from __future__ import annotations` at the top of every module. Run everything with `uv run`. Credentials live only in the gitignored `.env` — never printed, never committed. Commit + push after each task (project default).

---

### Task 1: Add the read-only (25006) SQLSTATE mapping

**Files:**
- Modify: `src/db_agent/db/mapping.py`
- Test: `tests/test_db_mapping.py` (add one parametrized case)

- [ ] **Step 1: Add the failing test case**

In `tests/test_db_mapping.py`, add this row to the `@pytest.mark.parametrize` list (after the `("42501", ("forbidden", False)),` line):

```python
        ("25006", ("read_only", False)),    # write in a read-only transaction
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db_mapping.py -q`
Expected: FAIL — the `25006` case returns `("db_error", False)` instead of `("read_only", False)`.

- [ ] **Step 3: Add the mapping**

In `src/db_agent/db/mapping.py`, add the `25006` entry to the `_FATAL` dict:

```python
# Known-fatal states.
_FATAL: dict[str, str] = {
    "57014": "timeout",  # query canceled (statement_timeout)
    "42501": "forbidden",  # insufficient privilege
    "25006": "read_only",  # write attempted in a read-only transaction
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db_mapping.py -q`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/db/mapping.py tests/test_db_mapping.py
git commit -F - <<'EOF'
Map SQLSTATE 25006 (read-only transaction) to a fatal read_only GuardError

Makes the read-only write-rejection precise instead of falling through to the
db_error catch-all; used by the db/ integration test for write rejection.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Register the `integration` marker and deselect it by default

**Files:**
- Modify: `pyproject.toml` (the `[tool.pytest.ini_options]` table)

- [ ] **Step 1: Edit the pytest config**

Replace the existing `[tool.pytest.ini_options]` table in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

with:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = ["-m", "not integration"]
markers = [
    "integration: requires a live PostgreSQL (DBAGENT_REPLICA_DSN); deselected by default",
]
```

- [ ] **Step 2: Verify the offline suite is unchanged**

Run: `uv run pytest -q`
Expected: PASS (52 passed) — no integration tests exist yet, so the deselect is a no-op; this just confirms the config parses.

- [ ] **Step 3: Verify the marker is registered (no unknown-mark warning)**

Run: `uv run pytest -q -W error::pytest.PytestUnknownMarkWarning`
Expected: PASS (52 passed) — registering the marker means using it later won't warn.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -F - <<'EOF'
Register integration pytest marker and deselect it by default

A bare `uv run pytest` now runs only the offline suite; `-m integration` opts
into the live-DB tests.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Integration test scaffolding (fixture + DSN gate)

**Files:**
- Create: `tests/integration/conftest.py`

> No `__init__.py` — the test filename is unique, matching the flat `tests/` layout; a subdirectory `conftest.py` is picked up automatically.

- [ ] **Step 1: Write the conftest**

Create `tests/integration/conftest.py`:

```python
"""Integration-test support: a live-DB ReadReplica fixture and a DSN gate.

When DBAGENT_REPLICA_DSN is not configured (still the default), every
integration-marked test is skipped so `-m integration` degrades gracefully with
no database. The offline suite never reaches here (it deselects `integration`).
"""

from __future__ import annotations

import pytest

from db_agent.config import get_settings
from db_agent.db import ReadReplica

_DEFAULT_DSN = "postgresql://readonly@localhost:5432/tumordb"


def _dsn_configured() -> bool:
    return get_settings().replica_dsn != _DEFAULT_DSN


def pytest_collection_modifyitems(config, items):
    if _dsn_configured():
        return
    skip = pytest.mark.skip(reason="DBAGENT_REPLICA_DSN not set; integration tests skipped")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def replica():
    r = ReadReplica(get_settings())
    r.open()
    yield r
    r.close()
```

- [ ] **Step 2: Verify the offline suite still ignores this directory**

Run: `uv run pytest -q`
Expected: PASS (52 passed) — `conftest.py` holds no tests; the offline run is unchanged.

- [ ] **Step 3: Verify the conftest imports cleanly under integration collection**

Run: `uv run pytest -m integration --collect-only -q tests/integration`
Expected: exits cleanly collecting 0 items (no test files yet, no import errors). No DB connection is attempted during collection.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/conftest.py
git commit -F - <<'EOF'
Add integration-test conftest: live-DB replica fixture + DSN skip gate

Session-scoped ReadReplica fixture; integration tests are skipped when
DBAGENT_REPLICA_DSN is unset so the suite degrades gracefully.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: The five integration test cases

**Files:**
- Create: `tests/integration/test_replica_integration.py`

> These tests are written now but only run live in Task 5. Their Task-4 verification is that the **offline** suite still deselects them (no DB is touched here).

- [ ] **Step 1: Write the integration tests**

Create `tests/integration/test_replica_integration.py`:

```python
"""Live-PostgreSQL integration tests for ReadReplica.

Run with: uv run pytest -m integration   (requires .env DBAGENT_REPLICA_DSN)
Every test is read-only against the database: the write case is rejected by the
read-only transaction, the big-table query is stopped by the EXPLAIN gate before
execution, and pg_sleep is bounded by a 500 ms statement_timeout.
"""

from __future__ import annotations

import pytest

from db_agent.config import Settings
from db_agent.db import ReadReplica
from db_agent.sql.errors import GuardError

pytestmark = pytest.mark.integration

NO_BIG: frozenset[str] = frozenset()
BIG: frozenset[str] = frozenset({"model_ccle_expression_data"})


def test_real_select_returns_shape(replica):
    res = replica.execute(
        "SELECT model_uuid, drug_name, for_bd FROM model_efficacy_info "
        "WHERE for_bd = 'yes' LIMIT 5",
        needs_explain=False,
        big_tables=NO_BIG,
        limit=5,
    )
    assert res.columns == ["model_uuid", "drug_name", "for_bd"]
    assert res.rowcount == len(res.rows)
    assert res.rowcount >= 0
    assert res.elapsed_ms > 0


def test_readonly_transaction_blocks_write(replica):
    # WHERE false: the read-only transaction rejects the UPDATE with 25006, and
    # even if the guard ever failed, zero rows would match — no mutation.
    with pytest.raises(GuardError) as exc:
        replica.execute(
            "UPDATE model_efficacy_info SET for_bd = for_bd WHERE false",
            needs_explain=False,
            big_tables=NO_BIG,
        )
    assert exc.value.category == "read_only"
    assert exc.value.retryable is False


def test_statement_timeout_is_enforced():
    # A dedicated short-timeout replica (same DSN from .env) so the sleep resolves
    # in well under a second.
    replica = ReadReplica(Settings(statement_timeout_ms=500))
    replica.open()
    try:
        with pytest.raises(GuardError) as exc:
            replica.execute("SELECT pg_sleep(2)", needs_explain=False, big_tables=NO_BIG)
        assert exc.value.category == "timeout"
        assert exc.value.retryable is False
    finally:
        replica.close()


def test_big_table_seq_scan_is_gated(replica):
    with pytest.raises(GuardError) as exc:
        replica.execute(
            "SELECT gene_symbol, log2tpm FROM model_ccle_expression_data LIMIT 100",
            needs_explain=True,
            big_tables=BIG,
        )
    assert exc.value.category == "big_table_scan"
    assert exc.value.retryable is False


def test_bad_column_is_retryable(replica):
    with pytest.raises(GuardError) as exc:
        replica.execute(
            "SELECT no_such_col FROM model_efficacy_info LIMIT 1",
            needs_explain=False,
            big_tables=NO_BIG,
        )
    assert exc.value.category == "bad_column"
    assert exc.value.retryable is True
```

- [ ] **Step 2: Verify the offline suite still deselects them (no DB touched)**

Run: `uv run pytest -q`
Expected: PASS (52 passed, 5 deselected). The "5 deselected" line confirms the integration tests are collected but excluded from the offline run — and critically, no connection was attempted.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_replica_integration.py
git commit -F - <<'EOF'
Add live-DB integration tests for ReadReplica (5 cases)

Real SELECT shape, read-only write rejection (25006), statement_timeout (57014),
big-table EXPLAIN gate, and bad-column mapping (42703). Marked integration;
deselected from the offline suite.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: Live run against the real database

> **Prerequisite:** `DBAGENT_REPLICA_DSN` in `.env` must authenticate. If the connection fails (e.g. `fe_sendauth: no password supplied`), STOP and report the auth error — do not retry in a loop or guess credentials.

**Files:** none created; may *adjust* `tests/integration/test_replica_integration.py` only if the live schema diverges from `semantic_layer.yaml`.

- [ ] **Step 1: Read-only schema verification**

Run (prints schema facts only — no credentials):

```bash
uv run python - <<'PY'
from db_agent.config import get_settings
from db_agent.db import ReadReplica

NO_BIG = frozenset()
r = ReadReplica(get_settings())
r.open()
try:
    res = r.execute(
        "SELECT current_user AS usr, current_setting('transaction_read_only') AS ro",
        needs_explain=False, big_tables=NO_BIG)
    print("connect/read_only:", res.rows)
    res = r.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_name IN ('model_efficacy_info','model_ccle_expression_data') "
        "ORDER BY table_name, ordinal_position",
        needs_explain=False, big_tables=NO_BIG)
    cols = {}
    for row in res.rows:
        cols.setdefault(row["table_name"], []).append(row["column_name"])
    for t, cs in cols.items():
        print(t, "->", cs)
PY
```

Expected: `read_only` reports `on`; both tables list columns including `model_uuid`, `drug_name`, `for_bd` (efficacy) and `gene_symbol`, `log2tpm` (expression). If a column name differs, update the matching SELECT in `test_replica_integration.py` to the real name and note it.

- [ ] **Step 2: Run the integration suite live**

Run: `uv run pytest -m integration -q`
Expected: PASS (5 passed). No `deselected`/`skipped` lines (DSN is configured).

- [ ] **Step 3: Confirm the offline suite is still clean and green**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: `52 passed, 5 deselected` and `All checks passed!`.

- [ ] **Step 4: Commit any schema adjustments (only if Step 1 required changes)**

```bash
git add tests/integration/test_replica_integration.py
git commit -F - <<'EOF'
Align db/ integration test SQL with the live schema

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

If no adjustment was needed, skip this step — the suite already passed live in Step 2.

---

## Self-Review

**Spec coverage:**
- Isolation: marker + default deselect + no-DSN skip → Tasks 2 & 3. ✅
- Run modes (`uv run pytest`, `uv run pytest -m integration`) → Tasks 2, 4, 5. ✅
- File layout `tests/integration/{conftest,test_replica_integration}.py` → Tasks 3 & 4 (dropped the optional `__init__.py`; filename is unique). ✅
- 5 cases (SELECT shape, read-only write reject, timeout, EXPLAIN gate, bad-column) → Task 4. ✅
- Supporting pure change: 25006 → `("read_only", False)` + offline test → Task 1. ✅
- Pre-implementation schema verification → Task 5 Step 1. ✅
- Safety (read-only/EXPLAIN/timeout bounded; no destructive statements) → Task 4 SQL choices + Task 5 prerequisite. ✅

**Spec deviation (intentional):** Case 2 uses `UPDATE ... WHERE false` instead of the spec's original `CREATE TEMP TABLE` — PostgreSQL *permits* temp-table DDL inside a read-only transaction, so that would not be rejected. The spec was corrected to match before this plan was written.

**Placeholder scan:** No TBD/TODO; every code and command step is complete. ✅

**Type consistency:** `ReadReplica.execute(sql, *, needs_explain, big_tables, limit=None)`, `QueryResult.columns/rows/rowcount/elapsed_ms`, `GuardError.category/retryable`, and `classify_db_error -> (category, retryable)` are referenced identically across tasks and match the shipped `db/` code. The `read_only` category string is defined in Task 1 and asserted in Task 4. ✅

**Note:** No dependency changes. New files live under `tests/`, so the `sql/` PreToolUse guard and Stop-hook review do not trigger; the PostToolUse ruff hook runs on each edit.
