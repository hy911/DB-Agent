"""FastAPI app: POST /query (wraps run_agent) and GET /health.

create_app(deps=None) is the injection seam: with deps=None the lifespan builds
the real ReadReplica pool + LiteLLMClient + semantic layer; with deps provided
(tests) it stores them and does no I/O. The endpoint reads request.app.state.deps
and maps AgentResult -> QueryResponse. Agent outcomes are 200 (with a status
field); an exception out of run_agent is 502.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request

from db_agent.api.schemas import QueryRequest, QueryResponse, ResultRows
from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.graph import run_agent
from db_agent.graph.state import AgentResult, Deps
from db_agent.llm import LiteLLMClient
from db_agent.semantic import load_semantic_layer

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, request: Request) -> QueryResponse:
    deps: Deps = request.app.state.deps
    try:
        result = run_agent(
            req.question,
            llm=deps.llm,
            replica=deps.replica,
            layer=deps.layer,
            settings=deps.settings,
        )
    except Exception as exc:  # infrastructure failure (gateway down, pool timeout)
        raise HTTPException(status_code=502, detail="agent backend error") from exc
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
        answer=result.answer,
        sql=result.sql,
        clarification=result.clarification,
        error=result.error,
        rows=rows,
    )


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
            app.state.deps = deps
            yield

    app = FastAPI(title="DB-Agent", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
