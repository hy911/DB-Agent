"""Observability sinks. Observer is the seam run_agent calls; tests inject a
list-appending callable, production injects a JsonlObserver.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from db_agent.observability.record import RunRecord


@runtime_checkable
class Observer(Protocol):
    def __call__(self, record: RunRecord) -> None: ...


class NullObserver:
    def __call__(self, record: RunRecord) -> None:
        return None


class JsonlObserver:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def __call__(self, record: RunRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # default=str: result_sample rows may hold Decimal/datetime/date from
        # Postgres, which json can't encode natively — coerce them to strings
        # rather than lose the whole record.
        line = json.dumps(record.to_dict(), ensure_ascii=False, default=str)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
