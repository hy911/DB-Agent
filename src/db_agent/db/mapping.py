"""Map a PostgreSQL SQLSTATE to a GuardError (category, retryable) decision.

retryable=True means the model's SQL was wrong in a way regeneration could fix
(bad column/function/type/table/syntax). Everything else is fatal — timeouts,
privilege errors, connection failures, and anything unrecognized fail closed and
are never fed back to the self-correction loop.
"""

from __future__ import annotations

# 42xxx-class mistakes in the generated SQL — safe to feed back for a retry.
_RETRYABLE: dict[str, str] = {
    "42703": "bad_column",
    "42883": "bad_function",
    "42804": "bad_type",
    "42P01": "bad_table",
    "42601": "bad_syntax",
}

# Known-fatal states.
_FATAL: dict[str, str] = {
    "57014": "timeout",  # query canceled (statement_timeout)
    "42501": "forbidden",  # insufficient privilege
    "25006": "read_only",  # write attempted in a read-only transaction
}


def classify_db_error(sqlstate: str | None) -> tuple[str, bool]:
    """Return (category, retryable) for a SQLSTATE. Fail closed on the unknown."""
    if sqlstate is None:
        return ("db_error", False)
    if sqlstate in _RETRYABLE:
        return (_RETRYABLE[sqlstate], True)
    if sqlstate in _FATAL:
        return (_FATAL[sqlstate], False)
    if sqlstate.startswith("08"):
        return ("connection", False)
    return ("db_error", False)
