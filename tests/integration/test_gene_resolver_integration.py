from __future__ import annotations

import pytest

from db_agent.config import get_settings
from db_agent.db import ReadReplica
from db_agent.db.gene_resolver import resolve_gene

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def replica():
    r = ReadReplica(get_settings())
    r.open()
    yield r
    r.close()


def test_fetch_is_parameterized(replica):
    rows = replica.fetch('SELECT "Symbol" AS s FROM gene_info WHERE "Symbol" = %s', ("EGFR",))
    assert rows and rows[0]["s"] == "EGFR"


def test_resolve_exact_human(replica):
    res = resolve_gene(replica, "EGFR")
    assert res.status == "resolved"
    assert res.symbol == "EGFR"


def test_resolve_lowercase_falls_to_fuzzy_ambiguous(replica):
    res = resolve_gene(replica, "egfr")  # no case-exact match
    assert res.status == "ambiguous"
    assert any(m.symbol == "EGFR" for m in res.candidates)


def test_resolve_unknown(replica):
    res = resolve_gene(replica, "zzzznotagene")
    assert res.status == "unknown"
    assert res.candidates == []
