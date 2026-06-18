"""Read-replica execution boundary — the only module that touches the database.

Pure decision logic (explain, mapping, result) is importable without a DB; the
psycopg I/O lives in ReadReplica.
"""

from __future__ import annotations

from db_agent.db.explain import evaluate_explain, seq_scanned_big_tables
from db_agent.db.gene_resolver import GeneMatch, GeneResolution, resolve_gene
from db_agent.db.mapping import classify_db_error
from db_agent.db.replica import ReadReplica
from db_agent.db.result import QueryResult

__all__ = [
    "GeneMatch",
    "GeneResolution",
    "QueryResult",
    "ReadReplica",
    "classify_db_error",
    "evaluate_explain",
    "resolve_gene",
    "seq_scanned_big_tables",
]
