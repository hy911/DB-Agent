"""LLM layer: gateway client, prompt builders, and the route/sql/answer tasks."""

from __future__ import annotations

import os

# litellm fetches a remote model-cost map from GitHub raw on first import (for
# token/cost accounting). On a restricted/internal network that SSL handshake
# times out and logs a WARNING before falling back to its bundled local copy.
# Force the local copy so the network call never happens. Must be set BEFORE
# litellm is first imported — this package __init__ runs before any submodule
# body (client.py / embedding.py import litellm lazily). setdefault so an
# explicit env override still wins.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from db_agent.llm.agent_llm import (  # noqa: E402
    RouteResult,
    analyze_sql,
    answer,
    answer_stat,
    answer_stat_stream,
    answer_stream,
    extract_genes,
    generate_sql,
    request_stat,
    route,
)
from db_agent.llm.client import LiteLLMClient, LLMClient  # noqa: E402

__all__ = [
    "LLMClient",
    "LiteLLMClient",
    "RouteResult",
    "analyze_sql",
    "answer",
    "answer_stat",
    "answer_stat_stream",
    "answer_stream",
    "extract_genes",
    "generate_sql",
    "request_stat",
    "route",
]
