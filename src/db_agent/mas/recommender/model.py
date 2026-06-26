"""Data model for the Model Recommender: extracted criteria + ranked output.

All dataclasses are frozen value objects. `Criteria.from_json` tolerantly parses
the LLM's structured extraction (it must never raise on a malformed reply — an
empty Criteria simply yields no recommendation, handled upstream).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

_DIRECTIONS = {"high", "low"}


@dataclass(frozen=True)
class ExpressionCriterion:
    gene: str  # raw gene token as written; resolved to a canonical symbol later
    direction: str  # "high" | "low"


@dataclass(frozen=True)
class Criteria:
    """What the customer wants in a model, parsed from their natural-language brief."""

    mutated_genes: tuple[str, ...] = ()
    expression: tuple[ExpressionCriterion, ...] = ()
    cancer_type: str | None = None
    model_type: str | None = None

    def is_empty(self) -> bool:
        return not (self.mutated_genes or self.expression or self.cancer_type or self.model_type)

    @classmethod
    def from_json(cls, raw: str) -> Criteria:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        genes = tuple(str(g).strip() for g in _as_list(data.get("mutated_genes")) if str(g).strip())
        expr: list[ExpressionCriterion] = []
        for item in _as_list(data.get("expression")):
            if isinstance(item, dict):
                gene = str(item.get("gene", "")).strip()
                direction = str(item.get("direction", "")).strip().lower()
                if gene and direction in _DIRECTIONS:
                    expr.append(ExpressionCriterion(gene, direction))
        cancer = _clean_str(data.get("cancer_type"))
        model_type = _clean_str(data.get("model_type"))
        return cls(
            mutated_genes=genes, expression=tuple(expr), cancer_type=cancer, model_type=model_type
        )


@dataclass(frozen=True)
class RankedModel:
    model_uuid: str
    model_id: str | None
    model_name: str | None
    model_type: str | None
    cancer_type: str | None
    score: int
    matched: tuple[str, ...]  # human-readable matched-criterion labels
    evidence: tuple[dict[str, object], ...] = ()  # efficacy rows (drug_name, tgi_tv)


@dataclass(frozen=True)
class Recommendation:
    question: str
    criteria: Criteria
    models: tuple[RankedModel, ...]
    summary: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)  # e.g. unresolved genes


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
