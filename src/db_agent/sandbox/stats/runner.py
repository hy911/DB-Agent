"""Public entry: parse the LLM's JSON request, validate it, dispatch to the impl.
Mirrors DuckDBSandbox.run — validation happens inside; the caller catches GuardError."""

from __future__ import annotations

import json

from db_agent.sandbox.stats.registry import REGISTRY
from db_agent.sandbox.stats.spec import StatResult
from db_agent.sandbox.stats.validator import validate_stat_request
from db_agent.sql.errors import GuardError


def run_stat(columns: list[str], rows: list[dict[str, object]], request_str: str) -> StatResult:
    try:
        request = json.loads(request_str)
    except (json.JSONDecodeError, TypeError) as e:
        raise GuardError("stat_parse_error", str(e).strip(), retryable=False) from e
    validated = validate_stat_request(request, columns, REGISTRY)
    return validated.test.run(rows, validated.params)
