"""Runtime configuration, loaded from environment / ``.env``.

Only what Phase 1 needs: the read-replica DSN (a *restricted read-only role*),
a statement timeout, query guard limits, the path to the semantic layer, and
the LiteLLM gateway with its model aliases.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DBAGENT_", env_file=".env", extra="ignore")

    # --- semantic layer ---
    semantic_layer_path: Path = _REPO_ROOT / "semantic_layer.yaml"

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
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = "sk-noauth"
    model_route: str = Field(default="qwen-main")  # general reasoning / clarify / summarize
    model_fast: str = Field(default="qwen-fast")  # domain routing
    model_sql: str = Field(default="qwen-code")  # SQL generation


@lru_cache
def get_settings() -> Settings:
    return Settings()
