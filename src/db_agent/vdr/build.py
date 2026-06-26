"""Build the VDR fact-card index from the database (offline, not on the request path).

Assembles one de-sensitized card per model from public attributes + pre-computed
metrics the live schema does NOT expose as ready columns (average latency from the
modeling table, an efficacy summary). The embed function is injected so card
assembly is unit-testable without the gateway. Trusted parameterized reads only
(the ReadReplica.fetch pattern); never LLM SQL.

De-sensitization is by construction: only the fields selected here enter a card —
the internal `model_uuid`, raw per-animal data, and non-`for_bd` efficacy rows never do.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from db_agent.vdr.model import FactCard

if TYPE_CHECKING:
    from db_agent.db.replica import ReadReplica

_MODEL_LIMIT = 5000


def _fmt(value: object, suffix: str = "") -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _card_text(attrs: dict[str, object], latency: object, n_drugs: object, best_tgi: object) -> str:
    """Assemble the de-sensitized fact body for one model (Chinese, BD-facing)."""
    parts: list[str] = []
    coarse = "、".join(str(attrs[k]) for k in ("cancer_type", "model_type") if attrs.get(k))
    if coarse:
        parts.append(f"瘤种/类型：{coarse}")
    if attrs.get("msi_status"):
        parts.append(f"MSI 状态：{attrs['msi_status']}")
    lat = _fmt(latency, " 天")
    if lat:
        parts.append(f"平均潜伏期约 {lat}（瘤体积达 100mm³）")
    if n_drugs:
        tgi = _fmt(best_tgi, "%")
        ev = f"累计 {n_drugs} 个药物的药效数据"
        if tgi:
            ev += f"，最佳 TGI {tgi}"
        parts.append(ev)
    return "；".join(parts) + "。" if parts else "暂无可对外披露的汇总数据。"


def build_cards(replica: ReadReplica, limit: int = _MODEL_LIMIT) -> list[FactCard]:
    models = replica.fetch(
        "SELECT model_uuid, model_id, model_type, cancer_type, msi_status "
        "FROM model_desc_info WHERE model_id IS NOT NULL LIMIT %s",
        (limit,),
    )
    latency = {
        str(r["model_uuid"]): r["latency"]
        for r in replica.fetch(
            "SELECT model_uuid, AVG(days_when_tumor_volume_100mm3) AS latency "
            "FROM modeling_attr_info WHERE days_when_tumor_volume_100mm3 IS NOT NULL "
            "GROUP BY model_uuid"
        )
    }
    efficacy = {
        str(r["model_uuid"]): r
        for r in replica.fetch(
            "SELECT model_uuid, COUNT(DISTINCT drug_name) AS n_drugs, MAX(tgi_tv) AS best_tgi "
            "FROM model_efficacy_info WHERE for_bd = 'yes' GROUP BY model_uuid"
        )
    }

    cards: list[FactCard] = []
    for m in models:
        uuid = str(m["model_uuid"])
        eff = efficacy.get(uuid, {})
        text = _card_text(m, latency.get(uuid), eff.get("n_drugs"), eff.get("best_tgi"))
        coarse = ", ".join(str(m[k]) for k in ("cancer_type", "model_type") if m.get(k))
        title = f"{m['model_id']} ({coarse})" if coarse else str(m["model_id"])
        cards.append(FactCard(model_id=str(m["model_id"]), title=title, text=text))
    return cards


def save_index(path: Path, vectors: np.ndarray, cards: list[FactCard]) -> None:
    np.savez(
        path,
        vectors=np.asarray(vectors, dtype=np.float32),
        model_ids=np.array([c.model_id for c in cards], dtype=object),
        titles=np.array([c.title for c in cards], dtype=object),
        texts=np.array([c.text for c in cards], dtype=object),
    )


def build_index(
    replica: ReadReplica,
    embed: Callable[[list[str]], list[list[float]]],
    out_path: Path,
) -> int:
    cards = build_cards(replica)
    if not cards:
        return 0
    # Embed "title: text" so both the model identity and its facts steer retrieval.
    vectors = np.asarray(embed([f"{c.title}: {c.text}" for c in cards]), dtype=np.float32)
    save_index(out_path, vectors, cards)
    return len(cards)


def _main(argv: list[str] | None = None) -> int:  # pragma: no cover
    import argparse

    from db_agent.config import get_settings
    from db_agent.db.replica import ReadReplica
    from db_agent.llm.embedding import LiteLLMEmbeddingClient

    parser = argparse.ArgumentParser(description="Build the VDR fact-card index.")
    parser.add_argument("out", type=Path, help="output .npz index path")
    args = parser.parse_args(argv)

    settings = get_settings()
    replica = ReadReplica(settings)
    replica.open()
    try:
        n = build_index(replica, LiteLLMEmbeddingClient(settings).embed, args.out)
    finally:
        replica.close()
    print(f"indexed {n} fact cards -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
