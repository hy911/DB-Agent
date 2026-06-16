# Design: `db/` layer — read-only execution boundary

Date: 2026-06-16
Status: Approved (brainstorming) — ready for implementation plan
Scope: Phase 1 MVP, efficacy domain. The single I/O boundary of the agent.

## Goal

Build `src/db_agent/db/`, the only module that talks to PostgreSQL. It takes a
**already-secured SQL string** (produced by `sql/`: structure-validated +
permission-injected + LIMIT-enforced) and runs it against the **read replica**
under a restricted read-only role, with three guarantees layered on top:

1. **Read-only at the DB level** — belt-and-suspenders over the restricted role.
2. **`statement_timeout`** — every connection is capped.
3. **EXPLAIN gate** — when `sql/` flagged a big-table scan, run `EXPLAIN` first
   and refuse to execute a plan that sequentially scans the big table.

Out of scope (deferred, per project phasing): observability logging (item #8 in
CLAUDE.md), the LangGraph wiring, the FastAPI endpoint, and the other domains.
The `db/` layer only exposes a clean interface for those to call later.

## Fixed decisions (confirmed during brainstorming, 2026-06-16)

- **Synchronous** implementation: psycopg3 `ConnectionPool`, plain `def`
  execute. FastAPI runs sync endpoints in a threadpool; LangGraph nodes call it
  directly. Chosen for simplicity and offline testability over async, which is
  over-engineered for internal low-concurrency load.
- **EXPLAIN gate rule = node-type**: reject if the plan contains a
  `Seq Scan` / parallel `Seq Scan` node on a big table. Deterministic, no tunable
  cost threshold.
- **Error mapping**: column/function/type/table/syntax errors (42xxx class) are
  `retryable=True` (fed back to the self-correction loop); statement timeout
  (57014), insufficient privilege (42501), connection/infrastructure (08xxx) and
  pool timeout are **fatal** (`retryable=False`). Unknown errors fail closed
  (fatal).

## Architecture — module decomposition

The defining constraint: `sql/` is pure and unit-tested offline; `db/` is the
I/O boundary. To keep the security-relevant logic offline-testable, split the
**pure decision logic** from the **psycopg I/O**.

| File | Responsibility | Offline-testable |
|---|---|---|
| `db/explain.py` | **Pure.** Parse an `EXPLAIN (FORMAT JSON)` plan tree; detect a `Seq Scan` node whose `Relation Name` is a big table. Raise `GuardError` on hit. | Yes (sample JSON) |
| `db/mapping.py` | **Pure.** `classify_db_error(sqlstate) -> (category, retryable)` by SQLSTATE. | Yes (sample sqlstate) |
| `db/result.py` | `QueryResult` frozen dataclass. | Yes |
| `db/replica.py` | **I/O.** `ReadReplica`: psycopg `ConnectionPool` + execution orchestration. Thin — delegates to the three pure modules. | No (needs a real DB) |
| `db/__init__.py` | Public exports. | — |

Rejected alternative: everything in one `replica.py`. That binds EXPLAIN-plan
analysis and error classification to a psycopg import, making them impossible to
unit-test under the no-DB rule. Not acceptable.

## Public interface

```python
class ReadReplica:
    def __init__(self, settings: Settings) -> None: ...
    def execute(
        self,
        sql: str,
        *,
        needs_explain: bool,
        big_tables: frozenset[str],
        limit: int | None = None,
    ) -> QueryResult: ...
    def close(self) -> None: ...
```

- `sql` — the secured SQL string from `sql/` (validate + permission inject +
  LIMIT already applied). `db/` does not re-derive any `sql/` decision.
- `needs_explain` — the boolean from `validator.requires_explain_guard()`.
- `big_tables` — `ValidationConfig.big_tables`, passed through so `explain.py`
  knows which relations to refuse a seq scan on.
- `limit` — the effective LIMIT value `sql/` enforced (the caller already holds
  it). Only used to compute `QueryResult.truncated`; `db/` never re-parses the
  SQL for it. When `None`, `truncated` is always `False`.

```python
@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool      # rowcount >= the `limit` passed to execute() (else False)
    sql: str
    elapsed_ms: float
```

## Connection pool & per-connection setup

- `ReadReplica.__init__` builds a psycopg `ConnectionPool` from
  `settings.replica_dsn`, `pool_min_size`, `pool_max_size`. (Open the pool
  explicitly rather than implicitly in the constructor.)
- A `configure` callback runs once per new connection and sets, before any
  transaction:
  - `conn.read_only = True` — every transaction on this connection is read-only
    (double protection over the restricted role).
  - `SET statement_timeout = <settings.statement_timeout_ms>`.
- `close()` closes the pool. Lifecycle (one pool per process) is owned by the
  caller that constructs `ReadReplica`.

## `execute` flow

1. Acquire a connection from the pool (already read-only + timed out via
   `configure`).
2. If `needs_explain`:
   - Run `EXPLAIN (FORMAT JSON) <sql>` — **no `ANALYZE`, so the query does not
     execute**.
   - Pass the plan JSON + `big_tables` to `explain.py`. If a `Seq Scan` node on a
     big table is found, raise `GuardError("big_table_scan",
     "big-table sequential scan rejected", retryable=False)`. **The query is
     never executed.**
3. Execute `<sql>`; fetch rows; assemble `QueryResult` (`columns` from the
   cursor description, `rows` as list of dicts, `elapsed_ms` timed around
   execution, `truncated` true when row count reached the enforced LIMIT).
4. On `psycopg.Error`: read `e.sqlstate`, call `mapping.classify_db_error`, and
   raise the corresponding `GuardError`. Pool-acquire timeout maps to a fatal
   `GuardError` too.

`EXPLAIN` is allowed under the read-only transaction; planning is cheap and also
bounded by `statement_timeout`.

## EXPLAIN plan analysis (`explain.py`)

- Input: the Python object psycopg returns for `EXPLAIN (FORMAT JSON)` — a list
  like `[{"Plan": {...}}]`.
- Walk the plan tree recursively (`Plan` → nested `Plans`). For each node, check
  `node["Node Type"] == "Seq Scan"` and `node.get("Relation Name") in
  big_tables`. A parallel sequential scan still reports `Node Type == "Seq Scan"`
  (parallelism is expressed by an enclosing `Gather` + `Parallel Aware`), so this
  single check covers it.
- Function shape: a pure entry point, e.g.
  `evaluate_explain(plan: object, big_tables: frozenset[str]) -> None` that
  raises `GuardError` on a hit and returns `None` otherwise. A helper that
  yields/finds offending relation names keeps it testable.

## Error mapping (`mapping.py`)

`classify_db_error(sqlstate: str | None) -> tuple[str, bool]` returning
`(category, retryable)`:

| SQLSTATE | Meaning | category | retryable |
|---|---|---|---|
| `42703` | undefined column | `bad_column` | True |
| `42883` | undefined function | `bad_function` | True |
| `42804` | datatype mismatch | `bad_type` | True |
| `42P01` | undefined table | `bad_table` | True |
| `42601` | syntax error | `bad_syntax` | True |
| `57014` | query canceled (statement_timeout) | `timeout` | False |
| `42501` | insufficient privilege | `forbidden` | False |
| `08***` (class 08) | connection exception | `connection` | False |
| anything else / `None` | unknown | `db_error` | False |

Fail closed: unrecognized states are fatal, never retryable.

## Testing strategy (offline — no DB, no LLM)

- `tests/test_db_explain.py`:
  - A plan with a `Seq Scan` on a big table → `evaluate_explain` raises
    `GuardError(retryable=False)`.
  - A plan with an `Index Scan` / filtered scan on the big table → passes.
  - A nested plan (seq scan buried under joins / `Gather`) → still caught.
  - A seq scan on a *non*-big table → passes (only big tables are gated).
- `tests/test_db_mapping.py`: each SQLSTATE in the table → expected
  `(category, retryable)`; unknown/`None` → fatal.
- `db/replica.py` (pool + real execution) is intentionally **not** in the
  offline suite — it is the I/O boundary. It is exercised later via integration
  testing against a real replica, out of scope here.

## Open questions

None. All design decisions are resolved above.
