"""Pure ranking logic for the recommender (no I/O — trivially unit-testable).

Scoring is deliberately simple and explainable: every criterion is a soft signal
worth one point, so a model that matches 2 of 3 criteria still surfaces (the whole
point of a recommender is the best *partial* matches, not just perfect ones). Ties
break on an expression-strength tiebreak, then on a stable identifier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from db_agent.mas.recommender.model import RankedModel

Signal = tuple[str, frozenset[str]]  # (human label, set of matching model_uuids)


def rank_models(
    signals: Sequence[Signal],
    details: Mapping[str, Mapping[str, object]],
    *,
    tiebreak: Mapping[str, float] | None = None,
    top_n: int = 3,
) -> list[RankedModel]:
    """Union the per-signal candidate sets, score by #signals matched, return top-N."""
    tb = tiebreak or {}
    pool: set[str] = set()
    for _, uuids in signals:
        pool |= uuids

    ranked: list[RankedModel] = []
    for uuid in pool:
        matched = tuple(label for label, uuids in signals if uuid in uuids)
        d = details.get(uuid, {})
        ranked.append(
            RankedModel(
                model_uuid=uuid,
                model_id=_opt(d.get("model_id")),
                model_name=_opt(d.get("model_name")),
                model_type=_opt(d.get("model_type")),
                cancer_type=_opt(d.get("cancer_type")),
                score=len(matched),
                matched=matched,
            )
        )

    ranked.sort(key=lambda m: (-m.score, -tb.get(m.model_uuid, 0.0), m.model_id or m.model_uuid))
    return ranked[:top_n]


def _opt(value: object) -> str | None:
    return None if value is None else str(value)
