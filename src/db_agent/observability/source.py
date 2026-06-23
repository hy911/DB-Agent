"""Read logged runs back, from whichever sink is configured.

Mirrors `_select_observer`'s precedence so analysis reads the same place the API
writes: the audit DB if `audit_db_dsn` is set, else the JSONL file (explicit path
or the default). Returns plain dicts; both the report and review CLIs build on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from db_agent.config import Settings


def read_records(settings: Settings) -> list[dict[str, Any]]:
    if settings.audit_db_dsn is not None:
        # Imported lazily so the JSONL path needs no psycopg / DB at all.
        from db_agent.db.audit import AuditLog

        audit = AuditLog(settings)
        audit.open()
        try:
            return audit.fetch_records()
        finally:
            audit.close()
    path = settings.observability_log_path or settings.default_log_path
    return read_jsonl(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
