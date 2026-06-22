"""Deterministic guard for a stat request: function in registry, params conform,
column refs exist, scalars in bounds. Fail closed (raise GuardError)."""

from __future__ import annotations

from collections.abc import Sequence

from db_agent.sandbox.stats.spec import ParamSpec, StatTest, ValidatedStatRequest
from db_agent.sql.errors import GuardError


def validate_stat_request(
    request: object, available_columns: Sequence[str], registry: dict[str, StatTest]
) -> ValidatedStatRequest:
    if not isinstance(request, dict):
        raise GuardError("stat_bad_request", "request must be a JSON object", retryable=False)

    name = request.get("function")
    test = registry.get(name) if isinstance(name, str) else None
    if test is None:
        raise GuardError("stat_unknown_function", f"unknown function {name!r}", retryable=False)

    params = request.get("params", {})
    if not isinstance(params, dict):
        raise GuardError("stat_bad_request", "params must be a JSON object", retryable=False)

    unknown = set(params) - set(test.params)
    if unknown:
        raise GuardError("stat_unknown_param", f"unknown params {sorted(unknown)}", retryable=False)

    cols = set(available_columns)
    clean: dict[str, object] = {}
    for pname, spec in test.params.items():
        if pname not in params:
            if spec.required:
                raise GuardError(
                    "stat_missing_param", f"missing required param {pname!r}", retryable=False
                )
            continue
        val = params[pname]
        if spec.role == "column":
            if not isinstance(val, str) or val not in cols:
                raise GuardError(
                    "stat_bad_column",
                    f"param {pname!r}={val!r} is not a column of the result table",
                    retryable=False,
                )
        else:  # scalar
            _check_scalar(pname, val, spec)
        clean[pname] = val

    return ValidatedStatRequest(test=test, params=clean)


def _check_scalar(pname: str, val: object, spec: ParamSpec) -> None:
    if spec.py_type is None:
        # A typeless scalar would skip all type/bounds checks below — reject it so a
        # future registry entry can never silently accept an unchecked value.
        raise GuardError(
            "stat_bad_scalar", f"scalar param {pname!r} has no declared type", retryable=False
        )
    if spec.py_type is bool:
        if not isinstance(val, bool):
            raise GuardError(
                "stat_bad_scalar", f"param {pname!r} must be a boolean", retryable=False
            )
    elif spec.py_type in (int, float):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise GuardError("stat_bad_scalar", f"param {pname!r} must be numeric", retryable=False)
        if spec.bounds is not None:
            lo, hi = spec.bounds
            if not (lo < float(val) < hi):
                raise GuardError(
                    "stat_bad_scalar",
                    f"param {pname!r}={val} out of range ({lo}, {hi})",
                    retryable=False,
                )
    if spec.choices is not None and val not in spec.choices:
        raise GuardError(
            "stat_bad_scalar", f"param {pname!r}={val!r} not in {spec.choices}", retryable=False
        )
