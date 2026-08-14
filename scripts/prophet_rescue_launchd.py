#!/usr/bin/env python3
"""Launchd wrapper for the Prophet US rescue lane — plumbing only, policy never.

WHY A HOST LANE AT ALL.  ``.github/workflows/prophet-rescue.yml`` is GitHub-hosted,
so it survives the Mac Studio dying.  It does NOT survive GitHub's scheduler dying,
and cron on Actions is best-effort by contract.  This is the other half: a lane that
survives GitHub, watches the same artifact, and adds the one check only a host can
make — free space on the volume the self-hosted runners fill.  That check is not
hypothetical: actions-runner-2 hit "No space left on device" at 14:29Z on
2026-08-13 and took two jobs of the recovery bake with it, reported as unrelated
failures.

WHY A WRAPPER, RATHER THAN THE PLIST CALLING THE TOOL DIRECTLY.  Same lesson the
worktree-GC agent learned on 2026-08-13 (scripts/worktree_gc_launchd.py):

  * NOTHING UPDATES THE PRIMARY CHECKOUT.  It is routinely occupied, dirty, or
    parked on an old commit — house law forbids sessions from touching its git
    state — so a plist pointing at ``<primary>/scripts/prophet_rescue.py`` would
    run whatever vintage the primary happened to be stuck on, possibly a commit
    where the file does not exist at all.
  * DRIFT IS INVISIBLE.  A stale script does not announce itself; it just makes
    quietly wrong decisions, which for a lane that can DISPATCH is worse than for
    one that only reports.

So this re-extracts the tool and its one dependency from ``origin/main`` on every
run.  The primary checkout serves only as the GIT VANTAGE POINT — the one role it
cannot be stale at.  A host that cannot read origin/main refuses outright: for a
responder, blind means stop.

macOS TCC NOTE.  The repo lives under ~/Documents, which macOS shields from
background processes.  Launchd jobs get no consent prompt, just ``Operation not
permitted``.  One-time grant required (System Settings -> Privacy & Security ->
Full Disk Access -> add ``/usr/bin/python3``); until then every run fail-closes
with the message below.

Stdlib-only, like the tool it launches — no venv, no repo imports.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")

#: Operator-created, chmod 600, KEY=VALUE per line.  Secrets never live in the
#: plist (which is world-readable and, worse, would be a repo artifact): the
#: installer creates the directory and prints what to put here.  Recognised keys
#: are the ones heartbeat.yml already passes to scripts/healthcheck.py, plus a
#: token: GH_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL,
#: DISCORD_WEBHOOK_WATCHLIST.
ENV_FILE = Path.home() / "Library/Application Support/macro-prophet-rescue/env"

#: The files the tool needs, and where they must land relative to the tempdir so
#: ``REPO_ROOT = Path(__file__).resolve().parents[1]`` resolves and
#: ``from lib.nyse_calendar import …`` works.
EXTRACT = (
    ("scripts/prophet_rescue.py", "scripts/prophet_rescue.py"),
    ("lib/nyse_calendar.py", "lib/nyse_calendar.py"),
    ("lib/__init__.py", "lib/__init__.py"),
)

GIT_TIMEOUT_S = 120
RUN_TIMEOUT_S = 300      # five network reads with 15 s timeouts, plus slack


def _git(*args: str) -> "subprocess.CompletedProcess[bytes]":
    return subprocess.run(("git", "-C", str(REPO), *args),
                          capture_output=True, timeout=GIT_TIMEOUT_S)


def _load_env() -> dict[str, str]:
    """Host secrets, if the operator has provisioned any.  Absence is not fatal:
    the tool degrades to anonymous reads and says so in its own output."""
    env = dict(os.environ)
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    if "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env:
        # The fleet's own gh login is already on this host; borrowing it beats
        # asking the operator to mint a second credential.
        try:
            got = subprocess.run(("gh", "auth", "token"), capture_output=True,
                                 timeout=30)
            if got.returncode == 0 and got.stdout.strip():
                env["GH_TOKEN"] = got.stdout.decode().strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return env


def main() -> int:
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print(f"== prophet-rescue {stamp} ==", flush=True)

    probe = _git("rev-parse", "--git-dir")
    if probe.returncode != 0:
        detail = probe.stderr.decode(errors="replace").strip()
        print(f"cannot read the primary checkout ({detail!r}).", flush=True)
        if "not permitted" in detail.lower():
            print("This is the macOS TCC wall: grant Full Disk Access to "
                  "/usr/bin/python3 (System Settings -> Privacy & Security), "
                  "then `launchctl kickstart` this job to verify.", flush=True)
        return 1

    if _git("fetch", "origin", "main", "--quiet").returncode != 0:
        print("(fetch failed - proceeding on last-known origin/main)", flush=True)

    with tempfile.TemporaryDirectory(prefix="prophet-rescue-") as work:
        root = Path(work)
        for repo_path, local_path in EXTRACT:
            shown = _git("show", f"origin/main:{repo_path}")
            if shown.returncode != 0:
                print(f"cannot read {repo_path} from origin/main - refusing "
                      "(fail-closed: the tool's truth is unavailable)", flush=True)
                return 1
            target = root / local_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(shown.stdout)

        run = subprocess.run(
            (sys.executable, str(root / "scripts/prophet_rescue.py"),
             "--lane", "launchd",
             # The tool runs from a tempdir, so it must be TOLD which volume to
             # measure or it would report headroom on /var/folders.
             "--disk-path", str(REPO)),
            env=_load_env(), timeout=RUN_TIMEOUT_S,
        )
    print(f"== prophet-rescue done rc={run.returncode} ==", flush=True)
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
