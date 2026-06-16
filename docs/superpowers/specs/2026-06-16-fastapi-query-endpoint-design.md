# Design: FastAPI query endpoint (api/)

Date: 2026-06-16
Status: Approved (brainstorming) — ready for implementation plan
Scope: Phase 1 MVP. Expose the agent chain (`run_agent`) over HTTP as one
synchronous JSON endpoint.

## Goal

A FastAPI service that turns a POSTed natural-language question into a JSON
response carrying the agent's answer, the SQL it ran, and the result rows —
wrapping the existing `db_agent.graph.run_agent` without changing it.

## Confirmed decisions (brainstorming, 2026-06-16)

- **Single JSON response** (no streaming). `run_agent` is synchronous and
  one-shot; FastAPI runs the sync handler in its threadpool.
- **Response includes result rows** (columns/rows/rowcount/truncated) so a UI or
  management dashboard can render a table.
- **Injection seam is the app factory** `create_app(deps=None)` — not
  `dependency_overrides`. Tests pass fake `Deps`; production builds real ones in
  the lifespan.
- **HTTP semantics:** agent outcomes (`answered` / `clarify` / `error`) are all
  HTTP 200 with a `status` field; only an *exception* escaping `run_agent`
  (infrastructure failure) maps to HTTP 502.

## Module layout

```
src/db_agent/api/
  __init__.py
  schemas.py   # Pydantic request/response models
  app.py       # create_app() factory, lifespan, routes; module-level `app`
```

`api/` is the thin HTTP boundary. It contains no business logic — it adapts HTTP
to `run_agent` and back.

## Schemas (`schemas.py`)

```python
class QueryRequest(BaseModel):
    question: str

class ResultRows(BaseModel):
    columns: list[str]
    rows: list[dict[str, object]]
    rowcount: int
    truncated: bool

class QueryResponse(BaseModel):
    status: str                       # answered | clarify | error
    answer: str | None = None
    sql: str | None = None
    clarification: str | None = None
    error: str | None = None
    rows: ResultRows | None = None
```

`AgentResult.result` (a `QueryResult` or `None`) maps to `rows` (a `ResultRows`
or `None`).

## App factory, lifespan, dependency seam (`app.py`)

```python
def create_app(deps: Deps | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if deps is None:
            s = get_settings()
            replica = ReadReplica(s)
            replica.open()
            app.state.deps = Deps(
                llm=LiteLLMClient(s),
                replica=replica,
                layer=load_semantic_layer(s.semantic_layer_path),
                settings=s,
            )
            try:
                yield
            finally:
                replica.close()
        else:
            app.state.deps = deps          # tests: no real pool, no external I/O
            yield

    app = FastAPI(title="DB-Agent", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()   # for `uvicorn db_agent.api.app:app`
```

- The `deps=None` branch builds and owns the real `ReadReplica` pool for the
  process lifetime; the `deps=<fake>` branch stores the injected bundle and does
  no I/O. `TestClient(create_app(deps=fake))` therefore runs fully offline.
- Module-level `app = create_app()` does **not** build deps at import time — the
  lifespan runs only when the server (or TestClient) starts.

## Routes

```python
@router.get("/health")
def health() -> dict:
    return {"status": "ok"}

@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request) -> QueryResponse:
    deps: Deps = request.app.state.deps
    try:
        result = run_agent(
            req.question,
            llm=deps.llm, replica=deps.replica, layer=deps.layer, settings=deps.settings,
        )
    except Exception as exc:  # infrastructure failure (gateway down, pool timeout)
        raise HTTPException(status_code=502, detail="agent backend error") from exc
    return _to_response(result)
```

`_to_response(AgentResult) -> QueryResponse` copies the scalar fields and maps
`result` to `ResultRows` when present.

## Error handling

| Situation | HTTP | Body |
|---|---|---|
| Agent answered | 200 | `status=answered`, `answer`, `sql`, `rows` |
| Needs clarification | 200 | `status=clarify`, `clarification` |
| Agent error (guard/budget) | 200 | `status=error`, `error` |
| Exception out of `run_agent` | 502 | `{"detail": "agent backend error"}` |
| Malformed body (no `question`) | 422 | FastAPI's default validation error |

The 502 message is deliberately generic — internal exception detail is not
leaked to the client (it is still available in server logs / the chained
exception).

## Testing (offline — no LLM, no DB)

`TestClient(create_app(deps=Deps(FakeLLM(...), FakeReplica(...), layer, settings)))`:

1. `GET /health` → 200, `{"status": "ok"}`.
2. `POST /query` happy path → 200; `status=answered`; `answer` set; `sql`
   contains `for_bd`; `rows` populated (columns/rowcount).
3. `POST /query` clarify → 200; `status=clarify`; `clarification` set; `rows`
   is null.
4. `POST /query` fatal guard error → 200; `status=error`.
5. `POST /query` when the LLM raises → 502.
6. `POST /query` with an empty body → 422.

Fakes are the same scripted `FakeLLM` / `FakeReplica` used by the graph tests;
the semantic layer is loaded from `semantic_layer.yaml` (offline). No real
gateway or database is contacted.

## Out of scope (deferred)

Streaming/SSE, auth, rate limiting, request logging/observability (item #8),
multi-turn sessions, and a live end-to-end smoke (the graph layer already has
one; a manual `uvicorn` + curl check can be done later but is not required by
this spec).

## Open questions

None. All decisions are resolved above.
