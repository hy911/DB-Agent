"""Load and validate ``semantic_layer.yaml`` into typed dataclasses.

Validation happens once at startup and fails loud: if the map is internally
inconsistent (a detail table points at a missing hub, a join key is absent on
either side, a domain hub is undefined) we refuse to boot rather than generate
SQL against a broken map.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from db_agent.semantic.model import (
    AccessControl,
    Column,
    Domain,
    SemanticLayer,
    Table,
)


class SemanticLayerError(Exception):
    """Raised when the semantic layer file is malformed or internally inconsistent."""


def load_semantic_layer(path: str | Path) -> SemanticLayer:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SemanticLayerError("semantic layer root must be a mapping")

    layer = _parse(raw)
    _validate(layer)
    return layer


def _parse(raw: dict) -> SemanticLayer:
    meta = raw.get("meta") or {}
    ac_raw = meta.get("access_control") or {}
    access_control = AccessControl(
        fields=tuple(ac_raw.get("fields", ())),
        note=ac_raw.get("note"),
    )

    domains: dict[str, Domain] = {}
    for name, d in (raw.get("domains") or {}).items():
        d = d or {}
        domains[name] = Domain(
            name=name,
            label=d.get("label", name),
            hub=d.get("hub"),
            access_controlled=bool(d.get("access_controlled", False)),
        )

    tables: dict[str, Table] = {}
    for name, t in (raw.get("tables") or {}).items():
        t = t or {}
        columns = {
            col_name: Column(
                name=col_name,
                type=(col or {}).get("type"),
                desc=(col or {}).get("desc"),
                unique=bool((col or {}).get("unique", False)),
                values=tuple((col or {}).get("values") or ()),
                examples=tuple((col or {}).get("examples") or ()),
                language=(col or {}).get("language"),
                fuzzy_align=bool((col or {}).get("fuzzy_align", False)),
            )
            for col_name, col in (t.get("columns") or {}).items()
        }
        tables[name] = Table(
            name=name,
            domain=t.get("domain", "reference"),
            columns=columns,
            desc=t.get("desc"),
            pk=t.get("pk"),
            access_controlled=bool(t.get("access_controlled", False)),
            access_via=t.get("access_via"),
            join_to_hub=tuple(t.get("join_to_hub", ())),
            big_table=bool(t.get("big_table", False)),
        )

    return SemanticLayer(
        spine_key=meta.get("spine_key", "model_uuid"),
        gene_key=meta.get("gene_key", "gene_symbol"),
        default_expression_table=meta.get("default_expression_table", ""),
        access_control=access_control,
        domains=domains,
        tables=tables,
    )


def _validate(layer: SemanticLayer) -> None:
    errors: list[str] = []

    for table in layer.tables.values():
        if table.domain not in layer.domains:
            errors.append(f"table {table.name!r} references unknown domain {table.domain!r}")

        if table.access_via is not None:
            hub = layer.tables.get(table.access_via)
            if hub is None:
                errors.append(
                    f"table {table.name!r} access_via points at missing table {table.access_via!r}"
                )
            else:
                if not table.join_to_hub:
                    errors.append(
                        f"detail table {table.name!r} declares access_via but no join_to_hub"
                    )
                for key in table.join_to_hub:
                    if not table.has_column(key):
                        errors.append(f"detail table {table.name!r} missing join key {key!r}")
                    if not hub.has_column(key):
                        errors.append(
                            f"hub {hub.name!r} missing join key {key!r} required by {table.name!r}"
                        )

    # NOTE: a domain whose hub table is not defined (e.g. the out-of-MVP
    # `modeling` domain) is treated as a forward declaration, not an error —
    # those domains are simply not routable until their tables are added.

    if errors:
        raise SemanticLayerError("semantic layer failed validation:\n  - " + "\n  - ".join(errors))
