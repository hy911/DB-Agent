"""One-call bridge over the sql/ guard rails (pure, no I/O).

Runs parse -> validate -> inject permissions -> enforce LIMIT on a generated SQL
string and returns the secured SQL plus the flags db/ needs to execute it
safely. Raises GuardError (with its retryable flag) if the query cannot be
secured — the graph's self-correction loop decides what to do with it.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from db_agent.semantic.model import SemanticLayer
from db_agent.sql.permission import inject_permissions, injection_config_for_domain
from db_agent.sql.validator import (
    enforce_limit,
    parse_single_statement,
    requires_explain_guard,
    validate_structure,
    validation_config_for_domain,
)


@dataclass(frozen=True)
class SecuredQuery:
    sql: str
    needs_explain: bool
    big_tables: frozenset[str]
    limit: int | None


def secure_query(sql: str, layer: SemanticLayer, domain: str) -> SecuredQuery:
    ast = parse_single_statement(sql)
    vcfg = validation_config_for_domain(layer, domain)
    validate_structure(ast, vcfg)

    icfg = injection_config_for_domain(layer, domain)
    if icfg is not None:
        ast = inject_permissions(ast, icfg)

    ast = enforce_limit(ast, vcfg)
    needs_explain = requires_explain_guard(ast, vcfg)
    return SecuredQuery(
        sql=ast.sql(dialect="postgres"),
        needs_explain=needs_explain,
        big_tables=vcfg.big_tables,
        limit=_limit_value(ast),
    )


def _limit_value(ast: exp.Expression) -> int | None:
    limit = ast.args.get("limit")
    if limit is None:
        return None
    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int:
        return int(value.name)
    return None
