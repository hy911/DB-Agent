"""Guard error type shared by the validator and the permission injector.

``retryable`` decides what the LangGraph self-correction loop does with a
failure:

* ``retryable=False`` — a security / policy violation (not read-only, unknown
  table, banned function, big-table scan, or a query we cannot safely secure).
  These are hard rejections: we never feed them back to the model to "try
  again", because doing so would invite the model to talk its way past a guard.
* ``retryable=True`` — a recoverable mistake in the *model's* SQL (parse error,
  later a bad column/type from the database). These are fed back into the
  generate step, up to the retry budget.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GuardError(Exception):
    category: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:  # pragma: no cover - trivial
        kind = "retryable" if self.retryable else "fatal"
        return f"[{self.category}/{kind}] {self.message}"
