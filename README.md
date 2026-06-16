# DB-Agent

Natural-language query & analysis agent for the mouse tumor model PostgreSQL
database. Users ask in plain language; the agent routes to a domain, assembles
schema context from the semantic layer, generates SQL (qwen-code), **validates
and injects row-level permissions deterministically**, runs against a read-only
replica, self-corrects on error, and answers in natural language while showing
the SQL it ran.

## Status — Phase 1 MVP (efficacy domain)

End-to-end chain being built:

```
intent route / clarify → context assembly (yaml) → SQL gen (qwen-code)
  → sqlglot validate + permission inject → read-replica exec → self-correct (≤3)
  → NL answer + generated SQL
```

### Landed so far

| Module | Path | What it does |
| --- | --- | --- |
| Semantic layer | `src/db_agent/semantic/` | Loads & validates `semantic_layer.yaml` into typed, frozen dataclasses (the agent's map). |
| SQL validator | `src/db_agent/sql/validator.py` | Single-statement, read-only, table allow-list, banned functions, LIMIT enforce/clamp, big-table EXPLAIN gate. |
| Permission injector | `src/db_agent/sql/permission.py` | Deterministically ANDs `for_bd = 'yes'` onto the efficacy hub; filters detail tables via correlated `EXISTS` back to `model_efficacy_info`. |
| Config | `src/db_agent/config.py` | Read-replica DSN, guard limits, LiteLLM aliases. |

### Permission policy (Phase 1)

A single constant rule, never decided by the LLM: efficacy queries only see rows
where `model_efficacy_info.for_bd = 'yes'`. Detail tables (growth curve / TGI /
survival) carry no permission column, so they are filtered with an `EXISTS`
semi-join back to the hub on `(model_uuid, efficacy_num, group_id)` — a semi-join
(not a real JOIN) so detail rows are never multiplied. No per-user concept yet.

### Still to build (this phase)

`db/replica.py` (read-only pool + `statement_timeout` + EXPLAIN), `llm/`
(LiteLLM aliases + prompts), `graph/` (LangGraph nodes + wiring), `api/`
(FastAPI `POST /query`), `observability/trace.py`.

Out of scope until Phase 2/3: stats sandbox, pgvector example retrieval, the
modeling/expression/mutation domains, DuckDB, real `resolve_gene`.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'        # requires Python 3.12+
pytest
```

> The code is written to also run under 3.11 (uses `from __future__ import
> annotations`), so the guard modules can be tested without a 3.12 toolchain.
