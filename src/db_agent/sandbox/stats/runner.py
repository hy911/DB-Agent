"""Public entry: parse the LLM's JSON request, validate it, dispatch to the impl.
Mirrors DuckDBSandbox.run — validation happens inside; the caller catches GuardError."""

from __future__ import annotations

import json

from db_agent.sandbox.stats.registry import REGISTRY
from db_agent.sandbox.stats.spec import StatResult
from db_agent.sandbox.stats.validator import validate_stat_request
from db_agent.sql.errors import GuardError

# Independent row-count floor: the result set is already LIMIT-bounded upstream, but
# the stats layer caps it itself so a future caller can't feed an unbounded set into
# scipy/lifelines (CPU sink). Defense in depth, mirrors functions._MAX_GROUPS.
_MAX_ROWS = 100_000


def run_stat(columns: list[str], rows: list[dict[str, object]], request_str: str) -> StatResult:
    if len(rows) > _MAX_ROWS:
        raise GuardError(
            "stat_too_many_rows", f"{len(rows)} rows exceeds the {_MAX_ROWS} cap", retryable=False
        )
    try:
        request = json.loads(request_str)
    except (json.JSONDecodeError, TypeError) as e:
        raise GuardError("stat_parse_error", str(e).strip(), retryable=False) from e
    validated = validate_stat_request(request, columns, REGISTRY)
    return validated.test.run(rows, validated.params)
