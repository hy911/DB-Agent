"""Stop hook: require an sql-security-reviewer pass when sql/ has changed.

The guard rails in `src/db_agent/sql/` are the security boundary. When this
turn touched them, finishing without a security review is exactly the moment a
weakened guard slips through. This hook checks the working tree on Stop and, if
any `db_agent/sql/` file is modified relative to the last commit, blocks the
stop (exit 2) and instructs the agent to invoke the `sql-security-reviewer`
subagent before finishing.

Loop safety: when Claude is already continuing *because of* this hook
(`stop_hook_active` is true), we exit 0 so the review runs and the turn can
then end normally — one nudge per turn, never an infinite loop.

Wired up in `.claude/settings.json` under the Stop event.
"""

from __future__ import annotations

import json
import subprocess
import sys

# Path fragment that marks the security-critical guard-rail layer.
_SQL_DIR = "db_agent/sql/"


def _changed_sql_files() -> list[str]:
    """Modified/added sql/ files in the working tree (staged, unstaged, untracked)."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError:
        return []
    files = []
    for line in out.splitlines():
        # porcelain format: "XY <path>"; path starts at column 3.
        path = line[3:].strip().strip('"')
        if _SQL_DIR in path.replace("\\", "/") and path.endswith(".py"):
            files.append(path)
    return files


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    # Already continuing because of this hook → let the turn finish.
    if payload.get("stop_hook_active"):
        return 0

    changed = _changed_sql_files()
    if not changed:
        return 0

    files = ", ".join(sorted(changed))
    sys.stderr.write(
        "Security boundary touched this turn: "
        f"{files}.\n"
        "Before finishing, invoke the `sql-security-reviewer` subagent (Agent "
        "tool, subagent_type='sql-security-reviewer') to audit these changes "
        "against the fixed guard-rail decisions, then address any Critical/High "
        "findings. If a review has already been completed this turn, you may stop.\n"
    )
    return 2  # block stop; stderr is fed back to the agent


if __name__ == "__main__":
    sys.exit(main())
