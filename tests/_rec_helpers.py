"""Shared fakes for Model Recommender tests (pipeline / worker / API).

A content-aware fake LLM (serves criteria JSON + summary by prompt content) and a
fake replica whose `fetch` answers each candidate query by SQL substring. The
recommender is deterministic, so these reproduce a fixed ranked outcome.
"""

from __future__ import annotations

from db_agent.db.gene_resolver import GeneResolution

# Default candidate fixture: m1 matches everything, m3 most, m2 least.
_DETAILS = [
    {
        "model_uuid": "m1",
        "model_id": "A1",
        "model_name": "N1",
        "model_type": "PDX",
        "cancer_type": "Lung Carcinoma",
    },
    {
        "model_uuid": "m2",
        "model_id": "A2",
        "model_name": "N2",
        "model_type": "CDX",
        "cancer_type": "Breast Carcinoma",
    },
    {
        "model_uuid": "m3",
        "model_id": "A3",
        "model_name": "N3",
        "model_type": "PDX",
        "cancer_type": "Lung Carcinoma",
    },
]


class RecLLM:
    """Serves the recommender's two model_route calls (criteria, summary)."""

    def __init__(self, criteria_json: str, summary: str = "推荐 m1。") -> None:
        self.criteria_json = criteria_json
        self.summary = summary

    async def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        text = " ".join(m["content"] for m in messages)
        if "extract structured selection criteria" in text:
            return self.criteria_json
        if "scientific consultant recommending" in text:
            return self.summary
        return ""

    async def complete_stream(self, model: str, messages: list[dict[str, str]]):
        yield await self.complete(model, messages)


class RecReplica:
    def fetch(self, sql: str, params=()):
        if "model_ccle_mutation_data" in sql:
            return [{"model_uuid": "m1"}, {"model_uuid": "m2"}]
        if "model_ccle_expression_data" in sql:
            return [{"model_uuid": "m1", "log2tpm": 3.0}, {"model_uuid": "m3", "log2tpm": 2.0}]
        if "ANY(%s)" in sql:  # model_details
            return list(_DETAILS)
        if "model_desc_info" in sql:  # attribute seed
            return [{"model_uuid": "m1"}, {"model_uuid": "m3"}]
        if "model_efficacy_info" in sql:
            return [{"drug_name": "DrugX", "tgi_tv": 85}]
        return []


def rec_resolver(mapping: dict[str, str]):
    def resolve(replica, name: str) -> GeneResolution:
        sym = mapping.get(name)
        if sym is None:
            return GeneResolution(name, "unknown", None, [])
        return GeneResolution(name, "resolved", sym, [])

    return resolve


# A criteria JSON covering all four signal kinds (KRAS mutation, HER2-high
# expression, Lung Carcinoma, PDX) → m1 scores 4, m3 scores 3, m2 scores 1.
FULL_CRITERIA = (
    '{"mutated_genes": ["KRAS"], "expression": [{"gene": "HER2", "direction": "high"}], '
    '"cancer_type": "Lung Carcinoma", "model_type": "PDX"}'
)
FULL_GENE_MAP = {"KRAS": "KRAS", "HER2": "ERBB2"}
