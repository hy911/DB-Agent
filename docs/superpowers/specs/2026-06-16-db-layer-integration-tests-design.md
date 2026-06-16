# Design: db/ layer integration tests (against a live PostgreSQL)

Date: 2026-06-16
Status: Approved (brainstorming) — ready for implementation plan
Scope: Real-database integration tests for `src/db_agent/db/ReadReplica`. The
offline unit suite already covers the pure pieces; this adds the I/O paths that
could not be exercised without a DB.

## Goal

Exercise `ReadReplica.execute` end-to-end against a **live PostgreSQL** so the
parts `replica.py` could not unit-test offline are verified for real: the
connection pool, DB-level read-only enforcement, `statement_timeout`, the EXPLAIN
gate on a real plan, and SQLSTATE error mapping.

## Environment (confirmed with the user)

- The target is a **full development database with a writable role** (not the
  production read-only replica). This is actually a stronger test of the
  belt-and-suspenders: even on a writable role, our per-connection
  `conn.read_only = True` must still reject writes.
- The database contains the **real efficacy schema and data**
  (`model_efficacy_info`, the detail tables, and the big table
  `model_ccle_expression_data`), so real SELECTs and the big-table EXPLAIN gate
  are meaningful.
- Connection string is supplied by the user in `.env` as
  `DBAGENT_REPLICA_DSN=...`. `.env` is gitignored — **credentials never enter
  chat or git**. Tests read it via `get_settings()`.

## Isolation from the offline suite (the critical constraint)

CLAUDE.md requires the default `pytest` run to be **offline — no DB, no LLM**.
Integration tests are isolated three ways:

1. **Marker** — every integration test is decorated `@pytest.mark.integration`,
   registered in `pyproject.toml`.
2. **Default deselect** — `addopts = ["-m", "not integration"]` so a bare
   `pytest` / `uv run pytest` runs only the offline suite. A command-line
   `-m integration` overrides addopts to run only integration tests.
3. **No-DSN skip** — a `conftest.py` under `tests/integration/` skips the whole
   directory when `DBAGENT_REPLICA_DSN` is unset, so even `-m integration`
   degrades gracefully with no configured database.

Run modes:

```bash
uv run pytest                 # offline only (integration auto-deselected)
uv run pytest -m integration  # live DB (requires .env DBAGENT_REPLICA_DSN)
```

## File layout

```
tests/integration/
  __init__.py
  conftest.py                     # DSN-gate + `replica` fixture
  test_replica_integration.py     # the 5 cases
```

- `conftest.py`:
  - Module/collection guard: if `get_settings().replica_dsn` is unset/default,
    `pytest.skip(..., allow_module_level=True)` — no connection attempted.
  - `replica` fixture (session-scoped): build `ReadReplica(get_settings())`,
    call `.open()`, `yield`, then `.close()`.

## Test cases (all marked `integration`)

All SQL targets the real schema from `semantic_layer.yaml`.

| # | Verifies | SQL (run through `ReadReplica.execute`) | Expectation |
|---|---|---|---|
| 1 | Real SELECT + result shape | `SELECT model_uuid, drug_name, for_bd FROM model_efficacy_info WHERE for_bd = 'yes' LIMIT 5` | Returns `QueryResult`; `columns == ["model_uuid","drug_name","for_bd"]`; `rowcount >= 0`; `elapsed_ms > 0` |
| 2 | Read-only belt-and-suspenders (writable role still blocked) | `CREATE TEMP TABLE _ro_probe (x int)` | Raises `GuardError` (read-only transaction, SQLSTATE 25006); nothing mutated |
| 3 | `statement_timeout` enforced | On a dedicated `ReadReplica(Settings(statement_timeout_ms=500))`: `SELECT pg_sleep(2)` | Raises `GuardError` with `category == "timeout"`, `retryable is False`; returns within ~1s |
| 4 | EXPLAIN gate on a real plan | `SELECT gene_symbol, log2tpm FROM model_ccle_expression_data LIMIT 100` with `needs_explain=True`, `big_tables={"model_ccle_expression_data"}` | Raises `GuardError` with `category == "big_table_scan"`; the query **never executes** (EXPLAIN-gated) |
| 5 | Error mapping on a real SQLSTATE | `SELECT no_such_col FROM model_efficacy_info LIMIT 1` | Raises `GuardError` with `retryable is True`, `category == "bad_column"` (42703) |

Notes:
- Case 2 and 5 feed raw SQL straight to `execute` (bypassing the `sql/`
  validator) on purpose — the point is to prove the DB-level guard and the real
  SQLSTATE mapping, not the validator (already unit-tested).
- Case 3 constructs its own short-timeout `ReadReplica` rather than using the
  shared `replica` fixture, so the sleep resolves in well under a second.
- Tests assert structure, not specific row counts (`rowcount >= 0`), so they stay
  green regardless of how much data the dev DB holds.

## Supporting change (pure, offline)

Add an explicit mapping for SQLSTATE **`25006` (read_only_sql_transaction)** to
`db/mapping.py`: `("read_only", False)`. Without it, case 2 would fall through to
the `("db_error", False)` catch-all; the explicit category makes the read-only
assertion precise and self-documenting. Add a matching parametrized case to the
offline `tests/test_db_mapping.py`.

## Safety properties

Every test is effectively read-only against the live DB:
- Case 2's write is rejected by the read-only transaction — no object is created.
- Case 4's big-table query is stopped by the EXPLAIN gate **before execution**, so
  the multi-million-row table is never scanned.
- Case 3's `pg_sleep` is bounded by a 500 ms `statement_timeout`.
- No test issues a destructive statement directly; writes only go through
  `ReadReplica`, which forces `read_only`.

## Pre-implementation verification (once `.env` is set)

Before/while implementing, with the DSN configured, run read-only checks to
confirm the live schema matches `semantic_layer.yaml` (table and column names for
`model_efficacy_info` and `model_ccle_expression_data`, that `for_bd` carries
`'yes'` values, and that `pg_sleep` is available). Adjust the test SQL only if the
live schema diverges from the semantic layer.

## Open questions

None. All decisions are resolved above.
