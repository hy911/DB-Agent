"""PreToolUse guard for the security-critical SQL modules.

The deterministic guard rails — `sql/validator.py` (read-only / allow-list /
limit / big-table gate) and `sql/permission.py` (row-level `for_bd = 'yes'`
injection) — are the security boundary of this agent. A careless edit that
weakens them is a data-leak-class bug, so any edit to them must be a *deliberate*
act, not a silent one.

This hook reads the PreToolUse payload from stdin and, when the target is one of
those two files, returns `permissionDecision: "ask"`, forcing an explicit
confirmation prompt before the edit is allowed. Every other file passes through
untouched (exit 0, no output).

Wired up in `.claude/settings.json` under PreToolUse with matcher `Edit|Write`.
"""

from __future__ import annotations

import json
import sys
from pathlib import PurePath

# (parent-dir-name, file-name) pairs that require a deliberate pause.
_GUARDED = {
    ("sql", "permission.py"),
    ("sql", "validator.py"),
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # If we cannot read the payload, fail open: never block normal editing.
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0

    p = PurePath(file_path)
    if (p.parent.name, p.name) not in _GUARDED:
        return 0

    reason = (
        f"{p.name} is a fail-closed SQL security guard rail. Edits here can "
        "silently weaken read-only enforcement or row-level permission "
        "injection (for_bd = 'yes'). Confirm the change preserves: fail-closed "
        "behaviour, idempotent injection, EXISTS semi-join (never a JOIN), and "
        "correct GuardError.retryable classification."
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
