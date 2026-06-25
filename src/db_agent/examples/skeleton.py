"""De-parameterize a SQL string into a structural skeleton (pure).

The skeleton drops literal values (keeping table/column structure and the
SELECT/JOIN/WHERE/GROUP BY shape) so two queries that differ only in their
filter values — "lung EGFR expression" vs "gastric TP53 expression" — collapse
to the same template. Used as the second recall channel for DAIL-SQL-style
structure-aware few-shot retrieval. A parse failure falls back to the raw SQL.
"""

from __future__ import annotations

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


def skeletonize(sql: str) -> str:
    try:
        ast = parse_one(sql, dialect="postgres")
    except ParseError:
        return sql
    if ast is None:
        return sql

    def _strip(node: exp.Expression) -> exp.Expression:
        return exp.Placeholder() if isinstance(node, exp.Literal) else node

    try:
        return ast.transform(_strip).sql(dialect="postgres")
    except Exception:
        return sql
