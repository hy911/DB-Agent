"""In-process DuckDB sandbox: the only module that touches DuckDB.

Runs ONE validated, locked-down SELECT over an in-memory ``result`` table built
from an already-permission-filtered query result.
"""

from __future__ import annotations

from db_agent.sandbox.engine import DuckDBSandbox
from db_agent.sandbox.validator import validate_analysis_sql

__all__ = ["DuckDBSandbox", "validate_analysis_sql"]
