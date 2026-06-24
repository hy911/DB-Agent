"""Typed representation of ``semantic_layer.yaml``.

The semantic layer is the *only* source of schema context for the agent. These
dataclasses are deliberately read-only (frozen) so that, once loaded and
validated at startup, the map cannot drift at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    type: str | None = None
    desc: str | None = None
    unique: bool = False
    values: tuple[str, ...] = ()  # closed enum of stored values, if known
    examples: tuple[str, ...] = ()  # sample values for an open vocabulary
    language: str | None = None  # english | chinese | mixed — language of stored values


@dataclass(frozen=True)
class Table:
    name: str
    domain: str
    columns: dict[str, Column]
    desc: str | None = None
    pk: str | None = None
    access_controlled: bool = False
    access_via: str | None = None  # hub table name, set on permissionless detail tables
    join_to_hub: tuple[str, ...] = ()  # join keys back to the hub (or spine)
    big_table: bool = False

    @property
    def is_detail(self) -> bool:
        """True when the table carries no access fields and must be filtered via its hub."""
        return self.access_via is not None

    def has_column(self, name: str) -> bool:
        return name in self.columns


@dataclass(frozen=True)
class Domain:
    name: str
    label: str
    hub: str | None = None
    access_controlled: bool = False


@dataclass(frozen=True)
class AccessControl:
    fields: tuple[str, ...]
    note: str | None = None


@dataclass(frozen=True)
class SemanticLayer:
    spine_key: str
    gene_key: str
    default_expression_table: str
    access_control: AccessControl
    domains: dict[str, Domain]
    tables: dict[str, Table]

    def get_table(self, name: str) -> Table | None:
        return self.tables.get(name)

    def get_domain(self, name: str) -> Domain | None:
        return self.domains.get(name)

    def tables_in_domain(self, domain: str) -> list[Table]:
        return [t for t in self.tables.values() if t.domain == domain]

    def reference_tables(self) -> list[Table]:
        return self.tables_in_domain("reference")

    def detail_tables_of(self, hub: str) -> list[Table]:
        """Detail tables whose ``access_via`` points at ``hub``."""
        return [t for t in self.tables.values() if t.access_via == hub]

    def routable_domains(self) -> list[Domain]:
        """Domains the router may pick: non-reference with at least one defined table.

        Forward-declared domains (a hub named but no tables yet) are excluded, so
        adding their tables to the YAML later makes them routable with no code change.
        """
        return [
            d
            for d in self.domains.values()
            if d.name != "reference" and self.tables_in_domain(d.name)
        ]

    def is_gene_bearing(self, domain: str) -> bool:
        """True if any table in the domain has the gene_key (gene_symbol) column."""
        return any(t.has_column(self.gene_key) for t in self.tables_in_domain(domain))
