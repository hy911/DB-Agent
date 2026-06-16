---
name: run-tests
description: Run the DB-Agent offline test suite the correct way. Use when asked to run tests, check tests pass, or verify a change. Encodes the no-DB / no-LLM contract and the Python 3.12 vs 3.11 invocation paths.
---

# Running DB-Agent tests

The suite is **strictly offline**: tests never touch a database and never call an
LLM. Everything under `tests/` exercises the pure `sql/` and `semantic/` layers
(AST in, secured AST out). If a test you are about to write would need a live
Postgres connection or a LiteLLM call, that is a sign it belongs behind the
`db/` I/O boundary (and should be deferred / mocked), not in this suite.

## Preferred invocation (Python 3.12+, editable install present)

```bash
pytest
```

`pyproject.toml` already sets `pythonpath = ["src"]` and `testpaths = ["tests"]`,
so a bare `pytest` from the repo root is enough.

If the editable install hasn't been done yet:

```bash
pip install -e '.[dev]'   # needs Python 3.12+; also installs ruff
pytest
```

## Fallback invocation (Python 3.11, no editable install)

Modules keep `from __future__ import annotations` at the top specifically so they
import on 3.11. When you can't do the 3.12 editable install:

```bash
pip install sqlglot pytest pyyaml
PYTHONPATH=src pytest -q
```

On Windows PowerShell, set the path inline:

```powershell
$env:PYTHONPATH = "src"; pytest -q
```

## What "passing" must mean

- All tests green **without** any `DATABASE_URL` / replica DSN set and **without**
  any LiteLLM credentials — if a test only passes with those present, it has
  leaked an I/O dependency into the offline suite. Reject that.
- The three guard-rail test files are the ones that matter most:
  `tests/test_validator.py`, `tests/test_permission.py`,
  `tests/test_semantic_loader.py`.

## Focused runs

```bash
pytest tests/test_permission.py -q          # just the injector
pytest -k "exists or idempoten" -q          # by keyword
pytest -q -x                                 # stop on first failure
```

After changes to `src/db_agent/sql/`, also consider invoking the
**sql-security-reviewer** subagent — the test suite proves the cases you thought
of; the reviewer hunts the ones you didn't.
