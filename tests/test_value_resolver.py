from __future__ import annotations

from db_agent.config import Settings
from db_agent.db.value_resolver import align_values
from db_agent.semantic import load_semantic_layer

LAYER = load_semantic_layer(Settings(_env_file=None).semantic_layer_path)


class _FakeReplica:
    """Returns a fixed nearest value (or none) and records fetch calls."""

    def __init__(self, nearest: str | None):
        self.nearest = nearest
        self.calls = 0

    def fetch(self, sql, params=()):
        self.calls += 1
        if self.nearest is None:
            return []
        return [{"v": self.nearest, "s": 0.6}]


def test_typo_drug_name_returns_alignment_hint():
    r = _FakeReplica("吉非替尼")
    hint = align_values(
        r,
        LAYER,
        "SELECT * FROM model_efficacy_info e WHERE e.drug_name ILIKE '%吉非ti尼%'",
        "efficacy",
    )
    assert hint is not None
    assert "吉非替尼" in hint
    assert r.calls == 1


def test_exact_real_value_returns_none():
    # the nearest value equals what the user wrote → no hint (e.g. a real drug that
    # is simply filtered out by permission → legitimately empty, must be accepted)
    r = _FakeReplica("吉非替尼")
    hint = align_values(
        r, LAYER, "SELECT * FROM model_efficacy_info e WHERE e.drug_name = '吉非替尼'", "efficacy"
    )
    assert hint is None


def test_non_fuzzy_column_skipped_without_db_call():
    r = _FakeReplica("x")
    hint = align_values(
        r, LAYER, "SELECT * FROM model_efficacy_info e WHERE e.tgi_tv = '5'", "efficacy"
    )
    assert hint is None
    assert r.calls == 0  # never touches the DB for a non-alignable column


def test_no_near_match_returns_none():
    r = _FakeReplica(None)
    hint = align_values(
        r, LAYER, "SELECT model_name FROM model_desc_info WHERE model_name = 'zzzzz'", "model"
    )
    assert hint is None


def test_model_name_alignment_on_spine():
    r = _FakeReplica("CT26")
    hint = align_values(
        r, LAYER, "SELECT * FROM model_desc_info WHERE model_name = 'CT-26'", "model"
    )
    assert hint is not None
    assert "CT26" in hint


def test_unparseable_sql_returns_none():
    assert align_values(_FakeReplica("x"), LAYER, "NOT SQL ((", "model") is None
