"""FastAPI app: POST /query (wraps run_agent) and GET /health.

create_app(deps=None) is the injection seam: with deps=None the lifespan builds
the real ReadReplica pool + LiteLLMClient + semantic layer; with deps provided
(tests) it stores them and does no I/O. The endpoint reads request.app.state.deps
and maps AgentResult -> QueryResponse. Agent outcomes are 200 (with a status
field); an exception out of run_agent is 502.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from db_agent.api.schemas import QueryRequest, QueryResponse, ResultRows
from db_agent.config import Settings, get_settings
from db_agent.db import ReadReplica
from db_agent.db.audit import AuditLog
from db_agent.examples.retriever import default_retriever
from db_agent.graph import run_agent
from db_agent.graph.state import AgentResult, Deps
from db_agent.llm import LiteLLMClient
from db_agent.observability.observer import JsonlObserver, NullObserver, Observer
from db_agent.observability.postgres import PostgresObserver
from db_agent.semantic import load_semantic_layer

logger = logging.getLogger("db_agent.api")

router = APIRouter()

_INDEX_HTML = Path(__file__).resolve().parent.parent / "web" / "index.html"


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-file chat UI; the page calls POST /query itself."""
    return FileResponse(_INDEX_HTML, media_type="text/html")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request) -> QueryResponse:
    deps: Deps = request.app.state.deps
    try:
        result = await run_agent(
            req.question,
            llm=deps.llm,
            replica=deps.replica,
            layer=deps.layer,
            settings=deps.settings,
            observer=request.app.state.observer,
        )
    except Exception as exc:  # infrastructure failure (gateway down/timeout, pool timeout)
        # Log the full traceback server-side, and surface the cause in the response
        # so a pending->502 can be diagnosed (dev stage, internal). The real culprit
        # is usually an LLM gateway timeout.
        logger.exception("run_agent failed (question=%r)", req.question)
        detail = f"agent backend error: {type(exc).__name__}: {exc}"
        raise HTTPException(status_code=502, detail=detail) from exc
    return _to_response(result)


def _to_response(result: AgentResult) -> QueryResponse:
    rows = None
    if result.result is not None:
        qr = result.result
        rows = ResultRows(
            columns=qr.columns,
            rows=qr.rows,
            rowcount=qr.rowcount,
            truncated=qr.truncated,
        )
    return QueryResponse(
        status=result.status,
        run_id=result.run_id,
        answer=result.answer,
        sql=result.sql,
        clarification=result.clarification,
        error=result.error,
        rows=rows,
    )


def _select_observer(s: Settings) -> tuple[Observer, AuditLog | None]:
    """Pick the recording sink. Recording is on by default: a writable audit DB
    wins; else an explicit JSONL path; else a default local JSONL file so nothing
    is lost before the audit DB exists. Returns the AuditLog to close on shutdown.
    """
    if s.audit_db_dsn is not None:
        try:
            audit = AuditLog(s)
            audit.open()  # connect + ensure_schema; bounded by connect_timeout
            return PostgresObserver(audit), audit
        except Exception:
            # A down/misconfigured log DB must never block startup — fall back to
            # the file sink so queries still serve (and still get logged).
            logger.exception("audit DB unavailable; falling back to JSONL sink")
    path = s.observability_log_path or s.default_log_path
    return JsonlObserver(path), None


def create_app(deps: Deps | None = None, observer: Observer | None = None) -> FastAPI:
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
                retrieve_examples=default_retriever(s),
            )
            obs, audit = _select_observer(s)
            app.state.observer = obs
            try:
                yield
            finally:
                if audit is not None:
                    audit.close()
                replica.close()
        else:
            app.state.deps = deps
            app.state.observer = observer if observer is not None else NullObserver()
            yield

    app = FastAPI(title="DB-Agent", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
