"""Runtime configuration, loaded from environment / ``.env``.

Only what Phase 1 needs: the read-replica DSN (a *restricted read-only role*),
a statement timeout, query guard limits, the path to the semantic layer, and
the LiteLLM gateway with its model aliases.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DBAGENT_", env_file=".env", extra="ignore")

    # --- semantic layer ---
    semantic_layer_path: Path = _REPO_ROOT / "semantic_layer.yaml"

    # --- observability ---
    # JSONL fallback sink. When no audit DB is configured, runs are still logged
    # here (default-on recording) so nothing is lost before the audit DB exists.
    observability_log_path: Path | None = None
    default_log_path: Path = _REPO_ROOT / "logs" / "agent_runs.jsonl"

    # --- audit log (separate WRITABLE Postgres role/db, never the read replica) ---
    # When set, per-run records are written to `audit_table` for SQL analysis.
    audit_db_dsn: str | None = None
    audit_table: str = "agent_query_log"
    # Per-run we store the first N result rows (dev-stage: see what data came back,
    # not just the rowcount). truncated/rowcount still reflect the full result.
    audit_result_sample_rows: int = 50

    # --- read replica (restricted read-only role) ---
    replica_dsn: str = "postgresql://readonly@localhost:5432/tumordb"
    statement_timeout_ms: int = 15_000
    pool_min_size: int = 1
    pool_max_size: int = 8

    # --- query guard rails ---
    default_limit: int = 1000
    max_limit: int = 10_000

    # --- self-correction loop ---
    max_sql_retries: int = 3

    # --- LiteLLM gateway / model aliases ---
    # Accept both the DBAGENT_-prefixed names and the deployed gateway's names.
    litellm_base_url: str = Field(
        default="http://localhost:4000",
        validation_alias=AliasChoices("DBAGENT_LITELLM_BASE_URL", "LITELLM_BASE_URL"),
    )
    litellm_api_key: str = Field(
        default="sk-noauth",
        validation_alias=AliasChoices("DBAGENT_LITELLM_API_KEY", "LITELLM_MASTER_KEY"),
    )
    model_route: str = Field(  # general reasoning / clarify / answer (qwen-main)
        default="qwen-main",
        validation_alias=AliasChoices("DBAGENT_MODEL_ROUTE", "MODEL_MAIN"),
    )
    model_fast: str = Field(  # domain routing (qwen-fast)
        default="qwen-fast",
        validation_alias=AliasChoices("DBAGENT_MODEL_FAST", "MODEL_FAST"),
    )
    model_sql: str = Field(  # SQL generation (qwen-code)
        default="qwen-code",
        validation_alias=AliasChoices("DBAGENT_MODEL_SQL", "MODEL_CODE"),
    )
    model_embed: str = Field(  # question embedding for example retrieval
        default="qwen-embedding",
        validation_alias=AliasChoices("DBAGENT_MODEL_EMBED", "MODEL_EMBED"),
    )
    model_rerank: str = Field(  # second-stage rerank for example retrieval
        default="qwen-reranker",
        validation_alias=AliasChoices("DBAGENT_MODEL_RERANK", "MODEL_RERANK"),
    )

    # --- few-shot example retrieval (off until an index path is set) ---
    example_index_path: Path | None = None
    example_top_k: int = 3
    # Optional second-stage rerank (off by default; needs a working gateway /v1/rerank).
    example_rerank: bool = False
    example_rerank_candidates: int = 10
    # Qwen3 models default to "thinking" mode and emit long reasoning before the
    # answer — for routing / SQL-gen / answer that just burns latency and makes the
    # gateway 504 on the upstream timeout. Disable it by default (these are
    # deterministic, non-CoT tasks); flip to True only if a thinking path is wanted.
    llm_enable_thinking: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
