from __future__ import annotations

import json

from db_agent.examples.build import build_index, load_examples_from_jsonl
from db_agent.examples.store import ExampleStore


def _write_log(path):
    rows = [
        {"status": "answered", "domain": "efficacy", "question": "q1", "raw_sql": "SELECT 1"},
        {"status": "answered", "domain": "efficacy", "question": "q1", "raw_sql": "SELECT 1"},  # dup
        {"status": "error", "domain": "efficacy", "question": "qbad", "raw_sql": "SELECT x"},
        {"status": "answered", "domain": "expression", "question": "q2", "raw_sql": None},  # no sql
        {"status": "answered", "domain": "mutation", "question": "q3", "raw_sql": "SELECT 3"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_load_examples_filters_and_dedups(tmp_path):
    log = tmp_path / "obs.jsonl"
    _write_log(log)
    examples = load_examples_from_jsonl(log)
    # only answered + non-empty question/raw_sql, deduped on (domain, raw_sql)
    assert [(e.domain, e.question) for e in examples] == [
        ("efficacy", "q1"),
        ("mutation", "q3"),
    ]


def test_build_index_roundtrips_through_store(tmp_path):
    log = tmp_path / "obs.jsonl"
    _write_log(log)
    out = tmp_path / "idx.npz"

    def fake_embed(texts):
        # 2-d vector: deterministic per text
        return [[float(len(t)), 1.0] for t in texts]

    n = build_index(log, fake_embed, out)
    assert n == 2  # two examples embedded
    store = ExampleStore(out)
    hits = store.search([3.0, 1.0], domain="mutation", k=1)
    assert hits[0].question == "q3"


def test_build_index_empty_log_writes_nothing(tmp_path):
    log = tmp_path / "empty.jsonl"
    log.write_text("", encoding="utf-8")
    out = tmp_path / "idx.npz"

    n = build_index(log, lambda texts: [[0.0] for _ in texts], out)
    assert n == 0
    assert not out.exists()  # nothing to index -> no file
    assert ExampleStore(out).search([0.0], domain="efficacy", k=1) == []
