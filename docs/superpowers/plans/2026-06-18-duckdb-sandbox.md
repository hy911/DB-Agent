# DuckDB Result Post-Processing Sandbox (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional second step that runs ONE locked-down DuckDB `SELECT`
over a query's already-permission-filtered result set (in-process, in-memory) for
post-processing (descriptive stats / reshaping / correlations), then answers from
it — failing soft to the raw result if anything goes wrong.

**Architecture:** New `src/db_agent/sandbox/` package = the only DuckDB boundary
(validator + engine). A new `analyze` graph node sits between `execute` and
`answer`: the LLM decides + emits DuckDB SQL, the sandbox validates and runs it in
a locked-down in-memory DuckDB (`enable_external_access=false`), and the answer
uses the analysis when present. Injected via `Deps.run_sandbox` for offline tests.

**Tech Stack:** Python 3.14 (uv `.venv`), DuckDB, sqlglot, LangGraph, pytest.
Spec: `docs/superpowers/specs/2026-06-18-duckdb-sandbox-design.md`.

**Conventions:** `from __future__ import annotations` atop each module. Run with
`uv run`. Offline tests fake the LLM; the sandbox engine is real DuckDB (offline,
no network). Fail-soft: analysis errors degrade to the raw-result answer. Commit +
push after each task.

## File Structure

- Modify: `pyproject.toml` — add `duckdb` runtime dependency.
- Create: `src/db_agent/sandbox/__init__.py` — exports `DuckDBSandbox`,
  `validate_analysis_sql`.
- Create: `src/db_agent/sandbox/validator.py` — pure DuckDB-SQL guard
  (`validate_analysis_sql`).
- Create: `src/db_agent/sandbox/engine.py` — `DuckDBSandbox.run(...)` (locked-down
  in-memory execution).
- Modify: `src/db_agent/llm/prompts.py` — `analysis_messages`.
- Modify: `src/db_agent/llm/agent_llm.py` — `analyze_sql`.
- Modify: `src/db_agent/llm/__init__.py` — export `analyze_sql`.
- Modify: `src/db_agent/graph/state.py` — `analysis`/`analysis_sql` state +
  `AgentResult.analysis_sql` + `Deps.run_sandbox`.
- Modify: `src/db_agent/graph/nodes.py` — `analyze_node`, `after_execute`,
  `answer_node`.
- Modify: `src/db_agent/graph/build.py` — wire `analyze`; `run_agent(run_sandbox=)`.
- Modify: `src/db_agent/observability/record.py` — log `analysis_sql`.
- Tests: `tests/test_sandbox_validator.py`, `tests/test_sandbox_engine.py`,
  `tests/test_llm_prompts.py`, `tests/test_llm_agent.py`, `tests/test_graph_nodes.py`,
  `tests/test_graph_chain.py`, `tests/test_graph_state.py`.

---

### Task 1: Add the `duckdb` dependency and PROVE the lockdown

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_sandbox_engine.py` (new)

This is the hard gate: before building anything, prove `enable_external_access=false`
blocks file access. If it does not, STOP and redesign the lockdown.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `"duckdb>=1.0"` to the `[project] dependencies` list
(after `"sqlglot>=25",`).

- [ ] **Step 2: Install**

Run: `uv sync --extra dev`
Expected: resolves and installs `duckdb`. If it fails, STOP and report.

- [ ] **Step 3: Write the lockdown proof test**

Create `tests/test_sandbox_engine.py`:

```python
from __future__ import annotations

import duckdb


def test_external_access_disabled_blocks_file_read():
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        import pytest

        with pytest.raises(duckdb.Error):
            con.execute("SELECT * FROM read_csv_auto('pyproject.toml')").fetchall()
    finally:
        con.close()


def test_locked_connection_still_runs_in_memory_sql():
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE result AS SELECT * FROM (VALUES (1), (2), (3)) t(x)")
        assert con.execute("SELECT avg(x) FROM result").fetchone()[0] == 2.0
    finally:
        con.close()
```

- [ ] **Step 4: Run the proof**

Run: `uv run pytest tests/test_sandbox_engine.py -q`
Expected: PASS — file read raises, in-memory SQL works. **If
`test_external_access_disabled_blocks_file_read` FAILS (file read NOT blocked),
STOP — the lockdown is unsound; do not proceed.**

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_sandbox_engine.py
git commit -F - <<'EOF'
Add duckdb dep and prove the sandbox lockdown blocks file access

enable_external_access=false rejects read_csv_auto on a real file while still
running in-memory SQL — the precondition for the result post-processing sandbox.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 2: Sandbox SQL validator (pure)

**Files:**
- Create: `src/db_agent/sandbox/__init__.py`
- Create: `src/db_agent/sandbox/validator.py`
- Test: `tests/test_sandbox_validator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sandbox_validator.py`:

```python
from __future__ import annotations

import pytest

from db_agent.sandbox.validator import validate_analysis_sql
from db_agent.sql.errors import GuardError


def test_accepts_select_over_result():
    ast = validate_analysis_sql("SELECT avg(tumor_volume) AS m FROM result")
    assert ast is not None


def test_accepts_group_by_and_quantile():
    validate_analysis_sql(
        "SELECT group_id, quantile_cont(val, 0.5) AS med FROM result GROUP BY group_id"
    )


def test_rejects_non_select():
    with pytest.raises(GuardError):
        validate_analysis_sql("CREATE TABLE x AS SELECT 1")


def test_rejects_multi_statement():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT 1 FROM result; SELECT 2 FROM result")


def test_rejects_other_table():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT * FROM model_efficacy_info")


def test_rejects_file_function():
    with pytest.raises(GuardError):
        validate_analysis_sql("SELECT * FROM read_csv_auto('x.csv')")


def test_rejects_attach():
    with pytest.raises(GuardError):
        validate_analysis_sql("ATTACH 'evil.db'")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_sandbox_validator.py -q`
Expected: FAIL — module not present.

- [ ] **Step 3: Implement the validator**

Create `src/db_agent/sandbox/validator.py`:

```python
"""Guard rail for sandbox analysis SQL (DuckDB dialect).

Defense in depth over the engine's locked-down connection: the analysis SQL must
be a single read-only SELECT referencing only the in-memory ``result`` table, with
no file/network/attach constructs. Fail closed (raise GuardError) on anything else.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from db_agent.sql.errors import GuardError

_ALLOWED_TABLE = "result"
_BANNED_FUNCS = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "parquet_scan",
        "read_json",
        "read_json_auto",
        "read_json_objects",
        "read_ndjson",
        "read_ndjson_auto",
        "read_text",
        "read_blob",
        "glob",
        "sniff_csv",
    }
)


def validate_analysis_sql(sql: str) -> exp.Expression:
    try:
        statements = [s for s in sqlglot.parse(sql, dialect="duckdb") if s is not None]
    except Exception as e:  # sqlglot ParseError and friends
        raise GuardError("analysis_parse_error", str(e).strip(), retryable=False) from e

    if len(statements) != 1:
        raise GuardError(
            "analysis_multi_statement", "exactly one statement is allowed", retryable=False
        )
    ast = statements[0]
    if not isinstance(ast, exp.Select):
        raise GuardError(
            "analysis_not_select", "only a single SELECT is allowed", retryable=False
        )

    for table in ast.find_all(exp.Table):
        if table.name != _ALLOWED_TABLE:
            raise GuardError(
                "analysis_forbidden_table",
                f"only the 'result' table may be queried, got {table.name!r}",
                retryable=False,
            )

    for fn in ast.find_all(exp.Anonymous):
        name = (fn.name or "").lower()
        if name in _BANNED_FUNCS:
            raise GuardError(
                "analysis_banned_function", f"function {name!r} is not allowed", retryable=False
            )

    return ast
```

Create `src/db_agent/sandbox/__init__.py`:

```python
"""In-process DuckDB sandbox: the only module that touches DuckDB.

Runs ONE validated, locked-down SELECT over an in-memory ``result`` table built
from an already-permission-filtered query result. Pure compute on data already in
memory — no external I/O.
"""

from __future__ import annotations

from db_agent.sandbox.engine import DuckDBSandbox
from db_agent.sandbox.validator import validate_analysis_sql

__all__ = ["DuckDBSandbox", "validate_analysis_sql"]
```

(Note: `__init__.py` imports `engine`, written in Task 3. Run this task's tests
with a direct import of the validator module to avoid the not-yet-written engine;
the test imports `db_agent.sandbox.validator` directly, so `__init__` is not
executed for it. If collection imports `__init__`, complete Task 3 first then run.
To keep Task 2 self-contained, temporarily make `__init__.py` import only the
validator, and add the engine export in Task 3 Step 3.)

Replace the `__init__.py` body for Task 2 with just:

```python
"""In-process DuckDB sandbox (the only module that touches DuckDB)."""

from __future__ import annotations

from db_agent.sandbox.validator import validate_analysis_sql

__all__ = ["validate_analysis_sql"]
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_sandbox_validator.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/sandbox/__init__.py src/db_agent/sandbox/validator.py tests/test_sandbox_validator.py
git commit -F - <<'EOF'
Add sandbox analysis-SQL validator (single SELECT over `result`)

Rejects non-SELECT, multi-statement, any table other than `result`, and DuckDB
file/network functions — defense in depth over the locked-down connection.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 3: Sandbox engine (locked-down DuckDB execution)

**Files:**
- Create: `src/db_agent/sandbox/engine.py`
- Modify: `src/db_agent/sandbox/__init__.py`
- Test: `tests/test_sandbox_engine.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sandbox_engine.py`:

```python
from decimal import Decimal

from db_agent.db.result import QueryResult
from db_agent.sandbox.engine import DuckDBSandbox
from db_agent.sql.errors import GuardError


def _rows():
    return [
        {"group_id": "A", "tv": Decimal("100.0")},
        {"group_id": "A", "tv": Decimal("200.0")},
        {"group_id": "B", "tv": Decimal("50.0")},
    ]


def test_engine_runs_aggregation():
    out = DuckDBSandbox().run(
        ["group_id", "tv"],
        _rows(),
        "SELECT group_id, avg(tv) AS m FROM result GROUP BY group_id ORDER BY group_id",
    )
    assert isinstance(out, QueryResult)
    assert out.columns == ["group_id", "m"]
    assert out.rows == [{"group_id": "A", "m": 150.0}, {"group_id": "B", "m": 50.0}]


def test_engine_rejects_unsafe_sql_before_running():
    with pytest.raises(GuardError):
        DuckDBSandbox().run(["x"], [{"x": 1}], "SELECT * FROM read_csv_auto('x')")


def test_engine_handles_empty_rows():
    out = DuckDBSandbox().run(["x"], [], "SELECT count(*) AS n FROM result")
    assert out.rows == [{"n": 0}]
```

(`pytest` is already imported at the top of the file from Task 1.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_sandbox_engine.py -q`
Expected: FAIL — `engine` module not present.

- [ ] **Step 3: Implement the engine**

Create `src/db_agent/sandbox/engine.py`:

```python
"""Locked-down in-memory DuckDB execution for result post-processing.

Opens a fresh in-memory DuckDB with external access disabled, builds a single
``result`` table from the (already-permission-filtered) rows, validates the SQL,
runs it, and returns a QueryResult. duckdb is imported lazily so importing the
graph does not require duckdb at module-import time.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal

from db_agent.db.result import QueryResult
from db_agent.sandbox.validator import validate_analysis_sql
from db_agent.sql.errors import GuardError

# Python type -> DuckDB column type. bool before int (bool is an int subclass).
_TYPE_MAP: tuple[tuple[type, str], ...] = (
    (bool, "BOOLEAN"),
    (int, "BIGINT"),
    (float, "DOUBLE"),
    (Decimal, "DOUBLE"),
    (datetime.datetime, "TIMESTAMP"),
    (datetime.date, "DATE"),
)


def _column_type(values: Sequence[object]) -> str:
    for v in values:
        if v is None:
            continue
        for py, sql in _TYPE_MAP:
            if isinstance(v, py):
                return sql
        return "VARCHAR"
    return "VARCHAR"


def _coerce(v: object) -> object:
    return float(v) if isinstance(v, Decimal) else v


class DuckDBSandbox:
    def run(
        self, columns: list[str], rows: list[dict[str, object]], sql: str
    ) -> QueryResult:
        validate_analysis_sql(sql)  # raises GuardError if unsafe
        import duckdb

        con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
        try:
            coldefs = ", ".join(
                f'"{c}" {_column_type([r.get(c) for r in rows])}' for c in columns
            )
            con.execute(f"CREATE TABLE result ({coldefs})")
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                con.executemany(
                    f"INSERT INTO result VALUES ({placeholders})",
                    [[_coerce(r.get(c)) for c in columns] for r in rows],
                )
            cur = con.execute(sql)
            out_columns = [d[0] for d in cur.description]
            out_rows = [dict(zip(out_columns, row, strict=False)) for row in cur.fetchall()]
        except duckdb.Error as e:
            raise GuardError("duckdb_error", str(e).strip(), retryable=False) from e
        finally:
            con.close()

        return QueryResult(
            columns=out_columns,
            rows=out_rows,
            rowcount=len(out_rows),
            truncated=False,
            sql=sql,
            elapsed_ms=0.0,
        )
```

Update `src/db_agent/sandbox/__init__.py` to also export the engine:

```python
"""In-process DuckDB sandbox: the only module that touches DuckDB.

Runs ONE validated, locked-down SELECT over an in-memory ``result`` table built
from an already-permission-filtered query result.
"""

from __future__ import annotations

from db_agent.sandbox.engine import DuckDBSandbox
from db_agent.sandbox.validator import validate_analysis_sql

__all__ = ["DuckDBSandbox", "validate_analysis_sql"]
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_sandbox_engine.py -q`
Expected: PASS (the Task 1 lockdown tests plus the 3 engine tests).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/sandbox/engine.py src/db_agent/sandbox/__init__.py tests/test_sandbox_engine.py
git commit -F - <<'EOF'
Add DuckDBSandbox engine (locked-down in-memory result post-processing)

Builds a typed `result` table from the permission-filtered rows, runs one
validated SELECT in an in-memory DuckDB with enable_external_access=false, returns
a QueryResult. Decimal -> float; duckdb imported lazily.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 4: LLM analyze task + prompt

**Files:**
- Modify: `src/db_agent/llm/prompts.py`
- Modify: `src/db_agent/llm/agent_llm.py`
- Modify: `src/db_agent/llm/__init__.py`
- Test: `tests/test_llm_prompts.py`, `tests/test_llm_agent.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_llm_prompts.py`, append:

```python
def test_analysis_messages_include_columns_and_question():
    from db_agent.llm.prompts import analysis_messages

    msgs = analysis_messages("avg per group?", ["group_id", "tv"], "group_id, tv\nA, 1")
    joined = " ".join(m["content"] for m in msgs)
    assert "result" in joined.lower()
    assert "group_id" in joined
    assert "avg per group?" in joined
```

In `tests/test_llm_agent.py`, append (`_ScriptedClient`, `SETTINGS`, `QueryResult`
are already imported in that file):

```python
def test_analyze_sql_returns_sql():
    from db_agent.llm.agent_llm import analyze_sql

    c = _ScriptedClient("SELECT group_id, avg(tv) FROM result GROUP BY group_id")
    qr = QueryResult(
        columns=["group_id", "tv"], rows=[{"group_id": "A", "tv": 1.0}],
        rowcount=1, truncated=False, sql="SELECT ...", elapsed_ms=1.0,
    )
    out = analyze_sql(c, SETTINGS, "avg per group?", qr)
    assert out.lower().startswith("select")
    assert c.last_model == "qwen-code"


def test_analyze_sql_none_passthrough():
    from db_agent.llm.agent_llm import analyze_sql

    qr = QueryResult(
        columns=["x"], rows=[{"x": 1}], rowcount=1, truncated=False,
        sql="s", elapsed_ms=1.0,
    )
    assert analyze_sql(_ScriptedClient("NONE"), SETTINGS, "q", qr) == "NONE"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: FAIL — `analysis_messages` / `analyze_sql` not defined.

- [ ] **Step 3: Add the prompt builder**

In `src/db_agent/llm/prompts.py`, add:

```python
def analysis_messages(
    question: str, columns: list[str], rows_preview: str
) -> list[dict[str, str]]:
    system = (
        "You decide whether answering the user's question needs post-processing of "
        "an already-fetched result set, and if so write ONE DuckDB SQL SELECT to do "
        "it. The result set is a single in-memory table named `result` with the "
        "given columns. If the rows already answer the question as-is, reply with "
        "the single word NONE. Otherwise reply with exactly one SELECT over `result` "
        "(aggregation / descriptive stats / pivot / correlation / quantiles), using "
        "only the `result` table and no file or external functions. Reply with the "
        "SQL or NONE and nothing else."
    )
    user = (
        f"Question: {question}\n\n"
        f"result columns: {', '.join(columns)}\n\n"
        f"Sample rows:\n{rows_preview}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
```

- [ ] **Step 4: Add the LLM task**

In `src/db_agent/llm/agent_llm.py`, add (reusing the module-private
`_rows_preview` and `_strip_fences`):

```python
def analyze_sql(
    client: LLMClient, settings: Settings, question: str, result: QueryResult
) -> str:
    msgs = prompts.analysis_messages(question, result.columns, _rows_preview(result))
    return _strip_fences(client.complete(settings.model_sql, msgs)).strip()
```

- [ ] **Step 5: Export it**

In `src/db_agent/llm/__init__.py`, add `analyze_sql` to the import from
`agent_llm` and to `__all__` (keep sorted):

```python
from db_agent.llm.agent_llm import RouteResult, analyze_sql, answer, extract_genes, generate_sql, route
```

and add `"analyze_sql",` to `__all__`.

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/test_llm_prompts.py tests/test_llm_agent.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/db_agent/llm/prompts.py src/db_agent/llm/agent_llm.py src/db_agent/llm/__init__.py tests/test_llm_prompts.py tests/test_llm_agent.py
git commit -F - <<'EOF'
Add analyze_sql LLM task (decide + emit one DuckDB SELECT over `result`)

The model proposes post-processing SQL (or NONE); safety is enforced
deterministically by the sandbox validator + locked connection.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 5: State / Deps / AgentResult fields + analyze_node + answer_node

**Files:**
- Modify: `src/db_agent/graph/state.py`
- Modify: `src/db_agent/graph/nodes.py`
- Modify: `src/db_agent/observability/record.py`
- Test: `tests/test_graph_state.py`, `tests/test_graph_nodes.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_graph_state.py`, append:

```python
def test_initial_state_has_analysis_fields():
    s = initial_state("q")
    assert s["analysis"] is None
    assert s["analysis_sql"] is None


def test_deps_default_run_sandbox_is_callable():
    from db_agent.config import Settings
    from db_agent.graph.state import Deps

    deps = Deps(llm=object(), replica=object(), layer=object(), settings=Settings(_env_file=None))
    assert callable(deps.run_sandbox)
```

In `tests/test_graph_nodes.py`, append (helpers `_deps`, `_LLM`, `initial_state`,
`QueryResult` already present; add `analyze_node`, `after_execute` already
imported — confirm `analyze_node` is added to the import list):

```python
def _qr_rows():
    return QueryResult(
        columns=["group_id", "tv"],
        rows=[{"group_id": "A", "tv": 1.0}, {"group_id": "B", "tv": 2.0}],
        rowcount=2,
        truncated=False,
        sql="SELECT group_id, tv",
        elapsed_ms=1.0,
    )


def test_analyze_node_runs_sandbox_when_sql_returned():
    analysis = QueryResult(
        columns=["m"], rows=[{"m": 1.5}], rowcount=1, truncated=False,
        sql="SELECT avg(tv) AS m FROM result", elapsed_ms=0.0,
    )

    def fake_sandbox(columns, rows, sql):
        assert columns == ["group_id", "tv"]
        return analysis

    deps = _deps(llm=_LLM({"qwen-code": ["SELECT avg(tv) AS m FROM result"]}))
    object.__setattr__(deps, "run_sandbox", fake_sandbox)
    s = initial_state("avg tv?")
    s["result"] = _qr_rows()
    out = analyze_node(s, deps)
    assert out["analysis"] is analysis
    assert "result" in out["analysis_sql"].lower()


def test_analyze_node_none_passes_through():
    deps = _deps(llm=_LLM({"qwen-code": ["NONE"]}))
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert analyze_node(s, deps) == {}


def test_analyze_node_empty_result_skips_llm():
    empty = QueryResult(columns=["x"], rows=[], rowcount=0, truncated=False, sql="s", elapsed_ms=0.0)
    deps = _deps(llm=_LLM({}))  # no scripted response -> must not be called
    s = initial_state("q")
    s["result"] = empty
    assert analyze_node(s, deps) == {}


def test_analyze_node_guard_error_degrades():
    def boom(columns, rows, sql):
        from db_agent.sql.errors import GuardError

        raise GuardError("duckdb_error", "bad", retryable=False)

    deps = _deps(llm=_LLM({"qwen-code": ["SELECT * FROM result"]}))
    object.__setattr__(deps, "run_sandbox", boom)
    s = initial_state("q")
    s["result"] = _qr_rows()
    assert analyze_node(s, deps) == {}


def test_answer_node_uses_analysis_when_present():
    analysis = QueryResult(
        columns=["m"], rows=[{"m": 1.5}], rowcount=1, truncated=False,
        sql="SELECT avg(tv) AS m FROM result", elapsed_ms=0.0,
    )
    deps = _deps(llm=_LLM({"qwen-main": ["Average is 1.5."]}))
    s = initial_state("q")
    s["secured_sql"] = "SELECT group_id, tv FROM t"
    s["result"] = _qr_rows()
    s["analysis"] = analysis
    s["analysis_sql"] = "SELECT avg(tv) AS m FROM result"
    out = answer_node(s, deps)
    assert out["answer"] == "Average is 1.5."
    assert out["status"] == "answered"
```

Also update the existing `test_after_guard_and_execute_dispatch` in
`tests/test_graph_nodes.py` — the `ok` branch of `after_execute` now goes to
`analyze`:

```python
def test_after_guard_and_execute_dispatch():
    s = initial_state("q")
    s["outcome"] = "ok"
    assert after_guard(s) == "execute"
    assert after_execute(s) == "analyze"
    s["outcome"] = "retry"
    assert after_guard(s) == "generate_sql"
    assert after_execute(s) == "generate_sql"
    s["outcome"] = "fatal"
    assert after_guard(s) == END
    assert after_execute(s) == END
```

And add `analyze_node` to the `from db_agent.graph.nodes import (...)` block at the
top of `tests/test_graph_nodes.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_graph_state.py tests/test_graph_nodes.py -q`
Expected: FAIL — `analysis` state fields / `Deps.run_sandbox` / `analyze_node` not
present; `after_execute` still returns `"answer"`.

- [ ] **Step 3: Update `state.py`**

In `src/db_agent/graph/state.py`:

Add to the imports (after the existing `from db_agent.db import ...` lines):

```python
from db_agent.sandbox.engine import DuckDBSandbox
```

Add the `QueryResult`-typed analysis fields to `AgentState` (after `result`):

```python
    analysis: QueryResult | None
    analysis_sql: str | None
```

Add to `initial_state(...)` (after `result=None,`):

```python
        analysis=None,
        analysis_sql=None,
```

Add `analysis_sql` to `AgentResult` (after `sql`):

```python
    analysis_sql: str | None
```

Map it in `to_result(...)` (after `sql=state.get("secured_sql"),`):

```python
        analysis_sql=state.get("analysis_sql"),
```

Add the sandbox runner default + `Deps` field. After the existing
`_default_resolve_gene` import area, add:

```python
_default_run_sandbox = DuckDBSandbox().run
```

In `Deps` (after the `resolve_gene` field):

```python
    run_sandbox: Callable[[list[str], list[dict[str, object]], str], QueryResult] = (
        _default_run_sandbox
    )
```

- [ ] **Step 4: Update `nodes.py`**

In `src/db_agent/graph/nodes.py`:

Add to the LLM imports:

```python
from db_agent.llm import analyze_sql as llm_analyze_sql
```

Change `after_execute` so `ok` routes to `analyze`:

```python
def after_execute(state: AgentState) -> str:
    return {"ok": "analyze", "retry": "generate_sql", "fatal": END}[state["outcome"]]
```

Add the `analyze_node` (place it after `execute_node`):

```python
def analyze_node(state: AgentState, deps: Deps) -> dict:
    result = state.get("result")
    if result is None or result.rowcount == 0:
        return {}
    sql = llm_analyze_sql(deps.llm, deps.settings, state["question"], result)
    if not sql or sql.strip().upper() == "NONE":
        return {}
    try:
        analysis = deps.run_sandbox(result.columns, result.rows, sql)
    except GuardError:
        return {}  # fail-soft: analysis is additive; degrade to the raw-result answer
    return {"analysis": analysis, "analysis_sql": sql}
```

Change `answer_node` to prefer the analysis output:

```python
def answer_node(state: AgentState, deps: Deps) -> dict:
    analysis = state.get("analysis")
    if analysis is not None:
        text = llm_answer(
            deps.llm, deps.settings, state["question"], state["analysis_sql"], analysis
        )
    else:
        text = llm_answer(
            deps.llm, deps.settings, state["question"], state["secured_sql"], state["result"]
        )
    return {"answer": text, "status": "answered"}
```

- [ ] **Step 5: Update `observability/record.py`**

Add `analysis_sql` to `RunRecord` (after `sql`):

```python
    analysis_sql: str | None
```

and in `from_state(...)` (after `sql=state.get("secured_sql"),`):

```python
            analysis_sql=state.get("analysis_sql"),
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest tests/test_graph_state.py tests/test_graph_nodes.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/db_agent/graph/state.py src/db_agent/graph/nodes.py src/db_agent/observability/record.py tests/test_graph_state.py tests/test_graph_nodes.py
git commit -F - <<'EOF'
Add analyze_node + analysis state/Deps and answer-from-analysis

execute -> analyze (LLM decides + sandbox runs one DuckDB SELECT) -> answer.
Fail-soft: empty result or NONE or GuardError passes through to the raw-result
answer. Deps.run_sandbox is injected (default = DuckDBSandbox); analysis_sql is
logged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 6: Wire the graph + run_agent param + chain tests

**Files:**
- Modify: `src/db_agent/graph/build.py`
- Test: `tests/test_graph_chain.py`

- [ ] **Step 1: Update the chain tests**

In `tests/test_graph_chain.py`:

Add a sandbox helper near the top (after the `_resolver` helper):

```python
def _passthrough_sandbox(columns, rows, sql):  # not used when LLM says NONE
    raise AssertionError("sandbox should not run when analyze returns NONE")
```

Change `_run` to thread an optional sandbox:

```python
def _run(llm, replica, question="how many models for BD?", resolve_gene=None, run_sandbox=None):
    return run_agent(
        question,
        llm=llm,
        replica=replica,
        layer=LAYER,
        settings=SETTINGS,
        resolve_gene=resolve_gene,
        run_sandbox=run_sandbox,
    )
```

Append `"NONE"` to the `qwen-code` script of every test that reaches the answer
(so the new analyze step gets its decision). Specifically, change these five
tests' `qwen-code` lists to end with `"NONE"`:

- `test_happy_path`: `"qwen-code": ["SELECT drug_name FROM model_efficacy_info", "NONE"]`
- `test_self_correction_then_success`: `"qwen-code": ["SELECT bad_col FROM model_efficacy_info", "SELECT drug_name FROM model_efficacy_info", "NONE"]`
- `test_expression_end_to_end_resolves_gene_and_injects`: append `"NONE"` to its `qwen-code` list
- `test_mutation_end_to_end_resolves_gene`: append `"NONE"` to its `qwen-code` list
- `test_modeling_end_to_end_injects_permission`: `"qwen-code": ["SELECT model_no FROM modeling_attr_info", "NONE"]`

Then add a new end-to-end test exercising the sandbox:

```python
def test_analysis_end_to_end_runs_sandbox():
    llm = _LLM(
        {
            "qwen-fast": ["efficacy"],
            "qwen-code": [
                "SELECT drug_name, tgi_tv FROM model_efficacy_info",  # generate_sql
                "SELECT drug_name, avg(tgi_tv) AS m FROM result GROUP BY drug_name",  # analyze
            ],
            "qwen-main": ["Average TGI per drug computed."],
        }
    )
    raw = QueryResult(
        columns=["drug_name", "tgi_tv"],
        rows=[{"drug_name": "X", "tgi_tv": 80.0}, {"drug_name": "X", "tgi_tv": 90.0}],
        rowcount=2,
        truncated=False,
        sql="SELECT drug_name, tgi_tv",
        elapsed_ms=1.0,
    )
    captured = {}

    def fake_sandbox(columns, rows, sql):
        captured["sql"] = sql
        return QueryResult(
            columns=["drug_name", "m"], rows=[{"drug_name": "X", "m": 85.0}],
            rowcount=1, truncated=False, sql=sql, elapsed_ms=0.0,
        )

    res = _run(llm, _Replica([raw]), question="average TGI per drug?", run_sandbox=fake_sandbox)
    assert res.status == "answered"
    assert res.answer == "Average TGI per drug computed."
    assert "result" in captured["sql"].lower()  # sandbox ran the analysis SQL
    assert res.analysis_sql is not None and "avg" in res.analysis_sql.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: FAIL — `run_agent` does not accept `run_sandbox`, and `analyze` is not
wired (`after_execute` returns `"analyze"` but there is no such node).

- [ ] **Step 3: Wire the graph + run_agent**

In `src/db_agent/graph/build.py`:

Add the import (with the existing imports):

```python
from db_agent.db.result import QueryResult
```

Register the node and rewire the execute edge. After the
`g.add_node("execute", ...)` line, add:

```python
    g.add_node("analyze", partial(nodes.analyze_node, deps=deps))
```

Change the `execute` conditional edge from:

```python
    g.add_conditional_edges("execute", nodes.after_execute, ["answer", "generate_sql", END])
```

to:

```python
    g.add_conditional_edges("execute", nodes.after_execute, ["analyze", "generate_sql", END])
    g.add_edge("analyze", "answer")
```

Add the `run_sandbox` parameter to `run_agent` and thread it into `Deps`. Update
the signature (after `resolve_gene=...`):

```python
    run_sandbox: Callable[[list[str], list[dict[str, object]], str], QueryResult] | None = None,
```

and where `deps_kwargs` is built, add:

```python
    if run_sandbox is not None:
        deps_kwargs["run_sandbox"] = run_sandbox
```

(`Callable` is already imported in build.py from the gene-wiring work; if not, add
`from collections.abc import Callable`.)

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_graph_chain.py -q`
Expected: PASS (the five updated tests + the new sandbox e2e + unchanged
clarify/error tests).

- [ ] **Step 5: Commit**

```bash
git add src/db_agent/graph/build.py tests/test_graph_chain.py
git commit -F - <<'EOF'
Wire the analyze node into the graph + run_agent run_sandbox param

execute -> analyze -> answer; run_agent gains an optional run_sandbox override for
offline tests (default = the real DuckDBSandbox). Existing answered-path chain
tests now script the analyze NONE decision.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
git push
```

---

### Task 7: Full suite + ruff + live e2e + SQL security review

**Files:** none (verification).

- [ ] **Step 1: Full offline suite**

Run: `uv run pytest -q`
Expected: PASS with `9 deselected`. All green including the new sandbox tests and
the updated chain tests.

- [ ] **Step 2: Lint and format**

Run: `uv run ruff check src tests && uv run ruff format --check src tests`
Expected: `All checks passed!` and `... files already formatted`. (If format
differs, run `uv run ruff format src tests` and re-check; if `ruff check` has
fixable issues, `uv run ruff check --fix src tests` then re-run.)

- [ ] **Step 3: Live end-to-end (real LLM + DuckDB + DB)**

> Prerequisite: `.env` DSN authenticates and the LiteLLM gateway is reachable.

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
layer = load_semantic_layer(s.semantic_layer_path)
llm = LiteLLMClient(s)
try:
    res = run_agent(
        "For BD-visible efficacy experiments, what is the average tgi_tv per drug? "
        "Return the top few.",
        llm=llm, replica=replica, layer=layer, settings=s,
    )
    print("status       :", res.status)
    print("replica sql  :", res.sql)
    print("analysis sql :", res.analysis_sql)
    print("answer       :", res.answer)
finally:
    replica.close()
PY
```

Expected: `status == answered`. If the model chose to post-process,
`analysis sql` is a `SELECT ... FROM result …` and the answer reflects the DuckDB
aggregation; if it answered directly, `analysis sql` is `None` (valid — analysis is
optional). Report the printed output. A transient gateway 504 on the answer node is
the known deferred retry/backoff gap, not a sandbox bug. No commit.

- [ ] **Step 4: SQL security review (mandatory — new code-execution surface)**

Dispatch the `sql-security-reviewer` subagent (Agent tool,
`subagent_type='sql-security-reviewer'`) to audit the sandbox. Point it at
`git diff 28a58ea HEAD` (or the actual base SHA before Task 1) and have it verify:
the DuckDB connection is in-memory with `enable_external_access=false`; the
validator rejects non-SELECT / multi-statement / non-`result` tables / file &
network functions; the sandbox never receives DB credentials or a replica
connection (only in-memory rows); failures degrade soft (no unfiltered data path
opens); and `sql/permission.py` / `sql/validator.py` are unchanged. Address any
Critical/High findings before finishing.

---

## Self-Review

**Spec coverage:**
- `sandbox/` module = only DuckDB boundary (validator + engine) → Tasks 2-3. ✅
- Lockdown proven (`enable_external_access=false` blocks file read) → Task 1. ✅
- sqlglot SELECT-only over `result`, banned file/network funcs, single statement →
  Task 2. ✅
- Data isolation (rows only, no DSN) + Decimal handling → Task 3. ✅
- Two-step automatic trigger (execute → analyze → answer) → Tasks 5-6. ✅
- LLM decide + emit DuckDB SQL (NONE passthrough) → Task 4 + analyze_node. ✅
- Fail-soft degrade (empty / NONE / GuardError → raw-result answer) → Task 5
  analyze_node + tests. ✅
- State/Deps/AgentResult/RunRecord fields + run_agent override → Tasks 5-6. ✅
- Full suite + ruff + live + security review → Task 7. ✅
- Phase 2 (stats inference) excluded → not in any task. ✅

**Placeholder scan:** No TBD/TODO. Task 2's `__init__.py` two-stage note (validator-
only, then engine added in Task 3) is explicit, not a placeholder. Every reused
helper (`_rows_preview`, `_strip_fences`, `QueryResult`, `GuardError`, `_deps`,
`_LLM`, `_Replica`, `_run`, `initial_state`, `after_execute`) was confirmed present.

**Type consistency:** `validate_analysis_sql(sql) -> exp.Expression`;
`DuckDBSandbox.run(columns: list[str], rows: list[dict], sql: str) -> QueryResult`;
`Deps.run_sandbox: Callable[[list[str], list[dict[str,object]], str], QueryResult]`;
`analyze_sql(client, settings, question, result: QueryResult) -> str`;
`analysis_messages(question, columns, rows_preview) -> list[dict]`;
`analyze_node(state, deps) -> dict`; `after_execute(state) -> str` ("ok"→"analyze");
`AgentResult.analysis_sql`; `run_agent(..., run_sandbox=None)` — consistent across
tasks and with the shipped `QueryResult`/`GuardError`/`Deps` types.
