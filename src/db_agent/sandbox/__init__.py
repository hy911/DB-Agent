"""In-process DuckDB sandbox (the only module that touches DuckDB)."""

from __future__ import annotations

from db_agent.sandbox.validator import validate_analysis_sql

__all__ = ["validate_analysis_sql"]
