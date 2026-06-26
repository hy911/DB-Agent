"""Parameterized candidate-discovery queries for the Model Recommender.

These are TRUSTED, hand-written, parameterized reads (the `ReadReplica.fetch`
pattern, like gene_resolver / value_resolver) — NOT LLM SQL. Every user-derived
value (gene symbol, cancer type, model type, uuid) is bound as a parameter; table
and column identifiers are constants from this module. Determinism over the LLM
path is deliberate: the same brief yields the same candidate set every run.

Big-table note: the expression (~36M) and mutation (~5.5M) tables are always
filtered by the indexed `gene_symbol` and hard-capped with LIMIT, so these never
seq-scan the whole table; the role's statement_timeout is the backstop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db_agent.db.replica import ReadReplica

# Single source of truth for the per-criterion candidate cap.
DEFAULT_CANDIDATE_LIMIT = 500
DEFAULT_EVIDENCE_LIMIT = 50


def models_with_mutation(
    replica: ReadReplica, symbol: str, limit: int = DEFAULT_CANDIDATE_LIMIT
) -> list[str]:
    """model_uuids carrying any somatic mutation in `symbol` (canonical gene symbol)."""
    rows = replica.fetch(
        "SELECT DISTINCT model_uuid FROM model_ccle_mutation_data "
        "WHERE gene_symbol = %s AND model_uuid IS NOT NULL LIMIT %s",
        (symbol, limit),
    )
    return [str(r["model_uuid"]) for r in rows]


def models_with_expression(
    replica: ReadReplica, symbol: str, direction: str, limit: int = DEFAULT_CANDIDATE_LIMIT
) -> list[tuple[str, float]]:
    """The top-`limit` models by `symbol` expression in `direction` ('high'|'low').

    Returns (model_uuid, log2tpm) so the scorer can use the value as a tiebreak. No
    magic cutoff: direction just orders the candidates; membership in the top-K of
    the requested tail is the 'match' signal.
    """
    order = "DESC" if direction == "high" else "ASC"
    rows = replica.fetch(
        "SELECT model_uuid, log2tpm FROM model_ccle_expression_data "
        "WHERE gene_symbol = %s AND model_uuid IS NOT NULL AND log2tpm IS NOT NULL "
        f"ORDER BY log2tpm {order} LIMIT %s",
        (symbol, limit),
    )
    return [(str(r["model_uuid"]), float(r["log2tpm"])) for r in rows]


def models_with_attributes(
    replica: ReadReplica,
    cancer_type: str | None,
    model_type: str | None,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[str]:
    """model_uuids matching the given attribute filters (used to seed an
    attribute-only brief). At least one of cancer_type/model_type must be set."""
    clauses = []
    params: list[object] = []
    if cancer_type:
        clauses.append("cancer_type = %s")
        params.append(cancer_type)
    if model_type:
        clauses.append("model_type = %s")
        params.append(model_type)
    if not clauses:
        return []
    params.append(limit)
    rows = replica.fetch(
        "SELECT model_uuid FROM model_desc_info "
        "WHERE " + " AND ".join(clauses) + " AND model_uuid IS NOT NULL LIMIT %s",
        params,
    )
    return [str(r["model_uuid"]) for r in rows]


def model_details(replica: ReadReplica, uuids: list[str]) -> dict[str, dict[str, object]]:
    """Map each model_uuid → its descriptive attributes (id/name/type/cancer_type)."""
    if not uuids:
        return {}
    rows = replica.fetch(
        "SELECT model_uuid, model_id, model_name, model_type, cancer_type "
        "FROM model_desc_info WHERE model_uuid = ANY(%s)",
        (list(uuids),),
    )
    return {str(r["model_uuid"]): r for r in rows}


def efficacy_evidence(
    replica: ReadReplica, uuid: str, limit: int = DEFAULT_EVIDENCE_LIMIT
) -> list[dict[str, object]]:
    """Permission-filtered efficacy records for one model (the single constant rule:
    for_bd = 'yes'). Used as persuasive evidence in the recommendation."""
    return replica.fetch(
        "SELECT drug_name, tgi_tv FROM model_efficacy_info "
        "WHERE model_uuid = %s AND for_bd = 'yes' AND drug_name IS NOT NULL "
        "ORDER BY tgi_tv DESC NULLS LAST LIMIT %s",
        (uuid, limit),
    )
