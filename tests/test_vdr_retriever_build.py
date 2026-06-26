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
    def __init__(self, hits, cards=()):
        self._hits = hits
        self._cards = list(cards)

    @property
    def cards(self):
        return self._cards

    def search(self, vec, k):
        return self._hits[:k]


def test_retriever_keeps_cards_above_threshold():
    card_hi = FactCard("CT26", "t", "x")
    card_lo = FactCard("MC38", "t", "x")
    store = _Store([(card_hi, 0.8), (card_lo, 0.1)])
    retrieve = make_card_retriever(store, _Embed(), k=3, threshold=0.3)
    cards = retrieve("潜伏期怎么样？")  # no exact id mention
    assert [c.model_id for c in cards] == ["CT26"]  # the low-score card dropped


def test_retriever_surfaces_exact_model_id_even_if_semantic_misses():
    # the named model's card must be returned even when cosine ranks neighbours higher
    target = FactCard("YK-CRC-032", "t", "x")
    neighbour = FactCard("YK-CRC-031", "t", "x")
    store = _Store([(neighbour, 0.9)], cards=[target, neighbour])
    retrieve = make_card_retriever(store, _Embed(), k=3, threshold=0.5)
    ids = [c.model_id for c in retrieve("YK-CRC-032 的潜伏期？")]
    assert ids[0] == "YK-CRC-032"  # exact match first
    assert "YK-CRC-031" in ids  # semantic neighbour still included


def test_retriever_failsoft_on_embed_error_keeps_exact():
    class _Boom:
        def embed(self, texts):
            raise RuntimeError("gateway down")

    target = FactCard("CT26", "t", "x")
    retrieve = make_card_retriever(_Store([], cards=[target]), _Boom(), k=3, threshold=0.3)
    assert retrieve("无关问题") == []  # no exact hit + embed down → live fallback
    assert [c.model_id for c in retrieve("CT26 怎么样")] == ["CT26"]  # exact survives embed failure


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


def test_embed_batched_chunks_calls():
    from db_agent.vdr.build import _embed_batched

    calls = []

    def embed(texts):
        calls.append(len(texts))
        return [[1.0] for _ in texts]

    vecs = _embed_batched(embed, [f"t{i}" for i in range(150)], batch=64)
    assert len(vecs) == 150  # all embedded, order preserved
    assert calls == [64, 64, 22]  # chunked, not one giant request


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
