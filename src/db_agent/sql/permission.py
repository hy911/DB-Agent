"""Permission injector (guard rail #2) — the security-critical module.

Policy (Phase 1, deliberately simple and *not* the model's decision): every
query against the efficacy domain may only see rows where the hub
``model_efficacy_info.for_bd = 'yes'``. There is no per-user concept yet; the
rule is a constant.

How it is enforced, deterministically, on the sqlglot AST:

* **Hub table** (``model_efficacy_info``) is filtered directly:
  ``AND <hub_alias>.for_bd = 'yes'``.
* **Detail tables** (growth curve / TGI / survival) carry no permission column,
  so we filter them with a correlated ``EXISTS`` back to the hub on
  ``(model_uuid, efficacy_num, group_id)``::

      AND EXISTS (
        SELECT 1 FROM model_efficacy_info AS _perm
        WHERE _perm.model_uuid = <d>.model_uuid
          AND _perm.efficacy_num = <d>.efficacy_num
          AND _perm.group_id = <d>.group_id
          AND _perm.for_bd = 'yes'
      )

  ``EXISTS`` (a semi-join) is used instead of a real JOIN so we never multiply
  detail rows — which would corrupt AVG/COUNT — and never collide on the
  ``model_uuid`` column both tables share.

Safety properties:

* We only ever ``AND`` our predicate onto each scope's WHERE, wrapping any
  existing condition in parentheses. ANDing can only *narrow* the result set,
  so even if the model wrote its own (wrong) filter, ours remains authoritative
  and can never be widened.
* Every SELECT scope is handled — subqueries and CTE bodies included — so a
  controlled table cannot hide inside a nested query.
* Fail-closed: if injection cannot be applied safely, the caller raises a fatal
  GuardError rather than execute an unsecured query.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp

from db_agent.semantic.model import SemanticLayer

# Marker placed on every predicate we inject, so a second pass is idempotent.
_PERM_MARK = "_perm_injected"
_PERM_ALIAS = "_perm"


@dataclass(frozen=True)
class InjectionConfig:
    hub_table: str                       # model_efficacy_info
    access_field: str                    # for_bd
    access_value: str                    # "yes"
    detail_join_keys: dict[str, tuple[str, ...]]  # detail table -> join keys to hub
    controlled_tables: frozenset[str]    # hub + detail tables


def injection_config_for_domain(layer: SemanticLayer, domain: str) -> InjectionConfig | None:
    """Build the injector config for an access-controlled domain, or None.

    Returns None for domains without a hub / access control (nothing to inject).
    """
    dom = layer.get_domain(domain)
    if dom is None or not dom.access_controlled or dom.hub is None:
        return None

    hub = dom.hub
    details = {t.name: t.join_to_hub for t in layer.detail_tables_of(hub)}
    controlled = frozenset({hub, *details})
    return InjectionConfig(
        hub_table=hub,
        access_field="for_bd",
        access_value="yes",
        detail_join_keys=details,
        controlled_tables=controlled,
    )


def inject_permissions(ast: exp.Expression, cfg: InjectionConfig) -> exp.Expression:
    """Return ``ast`` with the access policy ANDed into every relevant scope."""
    # Snapshot the SELECT scopes *before* mutating, so the inner SELECTs we add
    # for EXISTS are not themselves treated as targets.
    scopes = list(ast.find_all(exp.Select))
    for select in scopes:
        if select.meta.get(_PERM_MARK) or _already_injected(select):
            continue
        predicates = [
            pred
            for table in _direct_tables(select)
            if (pred := _predicate_for(table, cfg)) is not None
        ]
        for predicate in predicates:
            _and_into_where(select, predicate)
    return ast


def _direct_tables(select: exp.Select) -> list[exp.Table]:
    """Tables in this SELECT's own FROM/JOIN (not those of nested subqueries)."""
    sources: list[exp.Expression] = []
    # sqlglot stores the FROM under "from" or "from_" depending on version.
    from_ = select.args.get("from") or select.args.get("from_")
    if from_ is not None:
        sources.append(from_.this)
    for join in select.args.get("joins") or []:
        sources.append(join.this)
    return [s for s in sources if isinstance(s, exp.Table)]


def _predicate_for(table: exp.Table, cfg: InjectionConfig) -> exp.Expression | None:
    name = table.name
    if name not in cfg.controlled_tables:
        return None
    alias = table.alias_or_name
    if name == cfg.hub_table:
        pred = _access_eq(alias, cfg)
    else:
        pred = _exists_via_hub(alias, cfg.detail_join_keys[name], cfg)
    pred.meta[_PERM_MARK] = True
    return pred


def _access_eq(table_alias: str, cfg: InjectionConfig) -> exp.Expression:
    """``<alias>.for_bd = 'yes'``"""
    return exp.EQ(
        this=exp.column(cfg.access_field, table=table_alias),
        expression=exp.Literal.string(cfg.access_value),
    )


def _exists_via_hub(
    detail_alias: str, join_keys: tuple[str, ...], cfg: InjectionConfig
) -> exp.Expression:
    """Correlated EXISTS semi-join from a detail table back to the hub."""
    conditions = [
        exp.EQ(
            this=exp.column(key, table=_PERM_ALIAS),
            expression=exp.column(key, table=detail_alias),
        )
        for key in join_keys
    ]
    conditions.append(
        exp.EQ(
            this=exp.column(cfg.access_field, table=_PERM_ALIAS),
            expression=exp.Literal.string(cfg.access_value),
        )
    )
    where = conditions[0]
    for cond in conditions[1:]:
        where = exp.And(this=where, expression=cond)

    inner = (
        exp.Select()
        .select(exp.Literal.number(1))
        .from_(exp.alias_(exp.to_table(cfg.hub_table), _PERM_ALIAS, table=True))
        .where(where)
    )
    # Tag our generated scope so re-running the injector never re-enters it.
    inner.meta[_PERM_MARK] = True
    return exp.Exists(this=inner)


def _and_into_where(select: exp.Select, predicate: exp.Expression) -> None:
    existing = select.args.get("where")
    if existing is None:
        select.set("where", exp.Where(this=predicate))
        return
    combined = exp.And(this=exp.paren(existing.this), expression=predicate)
    select.set("where", exp.Where(this=combined))


def _already_injected(select: exp.Select) -> bool:
    where = select.args.get("where")
    if where is None:
        return False
    return any(node.meta.get(_PERM_MARK) for node in where.walk())
