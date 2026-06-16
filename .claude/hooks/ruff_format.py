"""PostToolUse hook: auto-format and lint-fix edited Python files with ruff.

The project's conventions are mechanical and easy to drift on — `from __future__
import annotations` at the top of every module, type hints everywhere, frozen
dataclasses, import ordering. Nothing enforced them before. This hook runs
`ruff check --fix` then `ruff format` on each Python file Claude edits, so
adherence is automatic instead of reviewer-dependent.

Fail open: if ruff is not installed, or anything goes wrong, the hook exits 0
without complaint — formatting is a convenience, never a blocker.

Wired up in `.claude/settings.json` under PostToolUse with matcher `Edit|Write`.
Install ruff via the dev extras: `pip install -e '.[dev]'`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(args: list[str], target: str) -> None:
    try:
        subprocess.run([*args, target], check=False, capture_output=True)
    except FileNotFoundError:
        # ruff not installed — nothing to do.
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0

    p = Path(file_path)
    if p.suffix != ".py" or not p.exists():
        return 0

    target = str(p)
    _run(["ruff", "check", "--fix", "--quiet"], target)
    _run(["ruff", "format", "--quiet"], target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
