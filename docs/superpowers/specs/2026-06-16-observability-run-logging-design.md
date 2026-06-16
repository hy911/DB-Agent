# Design: observability run logging (observability/)

Date: 2026-06-16
Status: Approved (brainstorming) — ready for implementation plan
Scope: Phase 1. Implement CLAUDE.md item #8 — log every run's
(question, retrieved context, generated SQL, result, feedback) tuple as
structured seed data for a future example store.

## Goal

Append one JSON line per `run_agent` call to a configurable JSONL file,
capturing the question, the assembled context, the generated and secured SQL, a
**summary** of the result (not the raw rows), and the outcome. Logging is
optional and fully decoupled — when no log path is configured, nothing is
written and behavior is unchanged.

## Confirmed decisions (brainstorming, 2026-06-16)

- **Sink = JSONL file append** at a config-controlled path; `None` disables it.
- **Result is summarized** (`rowcount` / `columns` / `truncated`) — raw rows are
  never written (size + sensitive-data avoidance).
- **Decoupled, optional integration:** `run_agent` gains an `observer=None`
  parameter; graph nodes and `Deps` are untouched.
- **`feedback` is a null placeholder** — Phase 1 has no feedback mechanism.

## Module layout

```
src/db_agent/observability/
  __init__.py
  record.py     # RunRecord dataclass + from_state() + to_dict()
  observer.py   # Observer protocol, JsonlObserver, NullObserver
```

`observability/` is a leaf module: it depends on `graph.state.AgentState` (to
read the final state) but nothing depends on it except `run_agent`'s optional
hook and the API wiring.

## RunRecord (`record.py`)

```python
@dataclass(frozen=True)
class RunRecord:
    ts: str                       # ISO-8601 UTC timestamp
    question: str
    domain: str | None
    context: str | None           # the assembled schema context (item #8)
    raw_sql: str | None           # the SQL the model generated
    sql: str | None               # the secured SQL that actually ran
    status: str                   # answered | clarify | error
    attempts: int
    rowcount: int | None          # result summary (None when no result)
    columns: list[str] | None
    truncated: bool | None
    answer: str | None
    clarification: str | None
    error: str | None
    feedback: str | None = None   # placeholder for a future feedback signal (always None in Phase 1)

    @classmethod
    def from_state(cls, state: AgentState) -> RunRecord: ...
    def to_dict(self) -> dict: ...
```

`from_state` reads the final `AgentState`:
- `result` (a `QueryResult | None`) maps to `rowcount` / `columns` / `truncated`
  (all `None` when `result` is `None`).
- `sql` ← `state["secured_sql"]`, `raw_sql` ← `state["sql"]`.
- `ts` is generated at record build time (`datetime.now(UTC).isoformat()`).

`to_dict` returns a plain JSON-serializable dict (frozen dataclass → `asdict`).

## Observer (`observer.py`)

```python
@runtime_checkable
class Observer(Protocol):
    def __call__(self, record: RunRecord) -> None: ...

class NullObserver:
    def __call__(self, record: RunRecord) -> None:  # no-op
        ...

class JsonlObserver:
    def __init__(self, path: str | Path) -> None: ...
    def __call__(self, record: RunRecord) -> None:
        # ensure parent dir exists; append json.dumps(record.to_dict(),
        # ensure_ascii=False) + "\n" (open/write/close per call)
        ...
```

`JsonlObserver` opens the file in append mode per write (simple and safe at low
volume), creating the parent directory if needed, and writes UTF-8 without
escaping non-ASCII (`ensure_ascii=False`) so Chinese questions stay readable.

## Integration

- `db_agent/graph/build.py`:
  `run_agent(question, *, llm, replica, layer, settings, observer=None) -> AgentResult`.
  After `final = graph.invoke(...)`, if `observer is not None`, call
  `observer(RunRecord.from_state(final))` — wrapped so a logging failure never
  breaks the request (a broken log sink must not fail a good answer). Then return
  `to_result(final)` as before. Graph nodes and `Deps` are unchanged.
- `db_agent/config.py`: add `observability_log_path: Path | None = None`
  (env `DBAGENT_OBSERVABILITY_LOG_PATH`).
- `db_agent/api/app.py`: in the real-deps lifespan branch, build
  `app.state.observer = JsonlObserver(s.observability_log_path)` when the path is
  set, else `NullObserver()`; the `/query` handler passes
  `observer=request.app.state.observer` to `run_agent`. The injected-deps (test)
  branch sets `app.state.observer = NullObserver()`.

## Error handling

Observability is best-effort and must never break a query: the `run_agent` hook
catches any exception from the observer and ignores it (the answer is already
computed). The 502/200 contract of the endpoint is unaffected.

## Testing (offline — no DB, no LLM, no real files beyond tmp)

1. `RunRecord.from_state` for each status:
   - answered (with a `QueryResult`) → `rowcount`/`columns`/`truncated` set,
     `sql`/`raw_sql` set, `feedback is None`.
   - clarify → `clarification` set, `rowcount is None`.
   - error → `error` set.
2. `JsonlObserver(tmp_path)` writes one line; read it back, `json.loads` it,
   assert the question/status/sql round-trip and that a second call appends a
   second line.
3. `NullObserver` does nothing (no file created).
4. `run_agent(..., observer=collector)` with the graph fakes (FakeLLM +
   FakeReplica): the collector (a list-appending callable) receives exactly one
   `RunRecord` with the expected `status`; no file is written.
5. A `run_agent` observer that raises does **not** propagate (the result is still
   returned).

## Out of scope (deferred)

The feedback signal itself, log rotation, async/batched writes, a DB/columnar
sink, and the pgvector example store that will consume this seed data.

## Open questions

None. All decisions are resolved above.
