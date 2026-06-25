from __future__ import annotations

import numpy as np

from db_agent.examples.build import save_index
from db_agent.examples.model import Example
from db_agent.examples.store import ExampleStore


def _make_index(tmp_path):
    examples = [
        Example("how many models for BD?", "SELECT count(*) FROM model_efficacy_info", "efficacy"),
        Example("list drugs", "SELECT drug_name FROM model_efficacy_info", "efficacy"),
        Example("TP53 expression?", "SELECT log2tpm FROM model_ccle_expression_data", "expression"),
    ]
    vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)
    path = tmp_path / "idx.npz"
    save_index(path, vectors, examples)
    return path


def test_search_returns_nearest_in_domain(tmp_path):
    store = ExampleStore(_make_index(tmp_path))
    hits = store.search([1.0, 0.0], domain="efficacy", k=2)
    assert [h.question for h in hits] == [
        "how many models for BD?",
        "list drugs",
    ]
    assert all(h.domain == "efficacy" for h in hits)


def test_search_filters_by_domain(tmp_path):
    store = ExampleStore(_make_index(tmp_path))
    hits = store.search([0.0, 1.0], domain="expression", k=5)
    assert len(hits) == 1
    assert hits[0].domain == "expression"


def test_missing_file_is_empty_store(tmp_path):
    store = ExampleStore(tmp_path / "nope.npz")
    assert store.search([1.0, 0.0], domain="efficacy", k=3) == []


def test_none_path_is_empty_store():
    store = ExampleStore(None)
    assert store.search([1.0, 0.0], domain="efficacy", k=3) == []


def _dual_index(tmp_path):
    # two efficacy examples; question vectors favor #0, skeleton vectors favor #1
    examples = [
        Example("q-zero", "SELECT a FROM t", "efficacy", "SELECT a FROM t"),
        Example("q-one", "SELECT b FROM t", "efficacy", "SELECT b FROM t"),
    ]
    qvecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    svecs = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float32)
    path = tmp_path / "dual.npz"
    save_index(path, qvecs, examples, svecs)
    return path


def test_search_dual_fuses_both_channels(tmp_path):
    store = ExampleStore(_dual_index(tmp_path))
    assert store.has_skeletons
    # question vec favors #0, skeleton vec favors #1 → RRF surfaces both, k=2
    hits = store.search_dual([1.0, 0.0], [1.0, 0.0], domain="efficacy", k=2)
    assert {h.question for h in hits} == {"q-zero", "q-one"}


def test_search_dual_falls_back_without_skeleton_vectors(tmp_path):
    # an index built WITHOUT skeleton vectors → dual search degrades to question-only
    store = ExampleStore(_make_index(tmp_path))
    assert not store.has_skeletons
    hits = store.search_dual([1.0, 0.0], [0.0, 1.0], domain="efficacy", k=2)
    assert [h.question for h in hits] == ["how many models for BD?", "list drugs"]
