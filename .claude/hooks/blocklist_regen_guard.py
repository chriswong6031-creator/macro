#!/usr/bin/env python3
"""PostToolUse guard: auto-regen compiled blocklists on DO_NOT_REBUILD.md edits.

House law (CLAUDE.md §house-laws): a research/DO_NOT_REBUILD.md row append must
land in the same PR as the regenerated config/compiled_kill_registry.yml +
config/signal_foundry_blocklist.yml (CI: capability-broker /
scripts/check_blocklist_drift.py).  Lanes kept forgetting the regen (twice on
2026-07-12 alone; each miss reddens every open PR until a heal PR lands), so
this hook runs it mechanically the moment the registry file is edited, in the
editing session's own working tree.

Fail OPEN on anything ambiguous or on internal error — a hook that bricks
editing is worse than a missed regen (the CI guard still catches those).
Exit 2 (feedback to the model) only when the checker reports a state --fix
cannot heal: a row outside sections 1-4, or a compiler error.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ARTIFACTS = (
    os.path.join("config", "compiled_kill_registry.yml"),
    os.path.join("config", "signal_foundry_blocklist.yml"),
)


def allow():
    sys.exit(0)


def _read(path: Path):
    try:
        return path.read_bytes()
    except OSError:
        return None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        allow()
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        allow()
    fp = ti.get("file_path")
    if not fp:
        allow()

    try:
        path = Path(fp)
        if not path.is_absolute():
            path = Path(payload.get("cwd") or os.getcwd()) / path
        path = path.resolve()
    except Exception:
        allow()

    if path.name != "DO_NOT_REBUILD.md" or path.parent.name != "research":
        allow()

    repo_root = path.parent.parent
    checker = repo_root / "scripts" / "check_blocklist_drift.py"
    if not checker.exists():
        allow()  # not this repo's layout — nothing to regen

    before = {a: _read(repo_root / a) for a in ARTIFACTS}
    try:
        proc = subprocess.run(
            [sys.executable, str(checker), "--repo-root", str(repo_root), "--fix"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception:
        allow()
    changed = [a for a in ARTIFACTS if _read(repo_root / a) != before[a]]

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        print(
            "blocklist_regen_guard: your research/DO_NOT_REBUILD.md edit leaves the "
            "compiled blocklists in a state --fix cannot heal (usually a row outside "
            "sections 1-4, or a compiler error). Fix the registry edit, then run "
            "python3 scripts/check_blocklist_drift.py --fix and commit the regenerated "
            "config files in the same PR.\n--- checker output ---\n" + tail,
            file=sys.stderr,
        )
        sys.exit(2)

    if changed:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": (
                    "blocklist_regen_guard: regenerated " + ", ".join(changed)
                    + " from your research/DO_NOT_REBUILD.md edit (house law: the regen "
                    "lands in the same PR as the row; CI guard check_blocklist_drift "
                    "reddens every open PR if it reaches main stale). Commit these "
                    "regenerated files together with the registry edit."
                ),
            }
        }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail open
