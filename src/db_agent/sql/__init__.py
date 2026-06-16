"""SQL guard rails: read-only validation, big-table guard, and permission injection.

These modules are pure (no I/O): they take a SQL string / sqlglot AST and the
semantic layer, and return a secured AST or raise :class:`GuardError`. All
database access lives in :mod:`db_agent.db`.
"""

from __future__ import annotations

from db_agent.sql.errors import GuardError
from db_agent.sql.permission import (
    InjectionConfig,
    inject_permissions,
    injection_config_for_domain,
)
from db_agent.sql.validator import (
    ValidationConfig,
    parse_single_statement,
    validate_structure,
    validation_config_for_domain,
)

__all__ = [
    "GuardError",
    "InjectionConfig",
    "ValidationConfig",
    "inject_permissions",
    "injection_config_for_domain",
    "parse_single_statement",
    "validate_structure",
    "validation_config_for_domain",
]
