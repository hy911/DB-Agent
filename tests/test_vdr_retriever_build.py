from __future__ import annotations

from decimal import Decimal

from db_agent.config import Settings
from db_agent.vdr.build import _card_text, build_cards
from db_agent.vdr.model import FactCard
from db_agent.vdr.retriever import _no_cards, default_card_retriever, make_card_retriever

SETTINGS = Settings(_env_file=None)


class _Embed:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class _Store:
    def __init__(self, hits):
        self._hits = hits

    def search(self, vec, k):
        return self._hits[:k]


def test_retriever_keeps_cards_above_threshold():
    card_hi = FactCard("CT26", "t", "x")
    card_lo = FactCard("MC38", "t", "x")
    store = _Store([(card_hi, 0.8), (card_lo, 0.1)])
    retrieve = make_card_retriever(store, _Embed(), k=3, threshold=0.3)
    cards = retrieve("CT26 的潜伏期？")
    assert [c.model_id for c in cards] == ["CT26"]  # the low-score card dropped


def test_retriever_failsoft_on_embed_error():
    class _Boom:
        def embed(self, texts):
            raise RuntimeError("gateway down")

    retrieve = make_card_retriever(_Store([]), _Boom(), k=3, threshold=0.3)
    assert retrieve("q") == []  # never raises → worker falls back to live engine


def test_default_retriever_is_noop_without_index():
    assert default_card_retriever(SETTINGS) is _no_cards


class _Replica:
    """Serves the three card-build queries by SQL substring."""

    def fetch(self, sql, params=()):
        if "FROM model_desc_info" in sql:
            return [
                {
                    "model_uuid": "u1",
                    "model_id": "CT26",
                    "model_type": "CDX",
                    "cancer_type": "Colorectal Carcinoma",
                    "msi_status": "MSS",
                }
            ]
        if "modeling_attr_info" in sql:
            return [{"model_uuid": "u1", "latency": 8.0}]
        if "model_efficacy_info" in sql:
            return [{"model_uuid": "u1", "n_drugs": 12, "best_tgi": 95.0}]
        return []


def test_build_cards_assembles_desensitized_fact_text():
    cards = build_cards(_Replica())
    assert len(cards) == 1
    c = cards[0]
    assert c.model_id == "CT26"  # public id, never the uuid
    assert "u1" not in c.text  # internal uuid never leaks into the card
    assert "Colorectal Carcinoma" in c.title
    assert "潜伏期约 8.0 天" in c.text and "12 个药物" in c.text and "TGI 95.0%" in c.text


def test_card_text_formats_decimal_metrics_to_one_dp():
    # DB AVG/MAX return Decimal — must not render as 11.0000000000000000
    text = _card_text(
        {"cancer_type": "Myeloma", "model_type": "HISCDX"},
        Decimal("11.0000000000000000"),
        5,
        Decimal("63.814"),
    )
    assert "11.0 天" in text and "TGI 63.8%" in text
    assert "0000" not in text
