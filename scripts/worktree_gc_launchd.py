#!/usr/bin/env python3
"""Launchd wrapper for the fleet worktree GC — plumbing only, policy never.

WHY A WRAPPER EXISTS AT ALL (2026-08-13). The canonical plist used to invoke
``__REPO_ROOT__/scripts/worktree_gc.py`` with the primary checkout's own config.
Two facts broke that quietly:

  * NOTHING UPDATES THE PRIMARY. It is routinely occupied, dirty, or parked on
    an old commit (house law: sessions must never touch its git state). So the
    operator's arming ratification — a config change merged to MAIN — would
    never reach the launchd job: it would sweep report-only forever, silently,
    while the roots regrew. The first install attempt failed on exactly this
    class of assumption (a repo path that did not exist at the referenced
    vintage).
  * DRIFT IS INVISIBLE. A stale script copy at least fails loudly; a stale
    CONFIG simply makes conservative decisions with no signal that policy and
    practice have diverged.

So this wrapper re-extracts BOTH the tool and the config from ``origin/main``
on every run. The primary checkout serves only as the GIT VANTAGE POINT — the
place worktrees are registered and refs are fetched — which is the one role it
cannot be stale at. All drift directions in the extracted pair are conservative
(worktree_gc.py is fail-closed at every gate: locked, dirty, unpushed, open-PR,
live-process, young, outside-roots), and a host that cannot READ origin/main
refuses outright: for a deleter, blind means stop.

INSTALLED TO A HOST PATH (~/Library/Application Support/macro-worktree-gc/) by
scripts/install_worktree_gc_launchd.sh, not run from a checkout — the wrapper
itself is the only file that has to be somewhere stable, and it carries no
policy: policy lives on origin/main, which is re-read live.

macOS TCC NOTE. The repo lives under ~/Documents, which macOS shields from
background processes. Launchd jobs get no consent prompt — they just get
``Operation not permitted``. One-time grant required (System Settings →
Privacy & Security → Full Disk Access → add ``/usr/bin/python3``); until it is
granted, every run fail-closes with the message below and deletes nothing.

Stdlib-only, like the tool it launches — no venv, no repo imports.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
GIT_TIMEOUT_S = 120
RUN_TIMEOUT_S = 3000   # the sweep walks ~200 trees with per-tree git reads


def _git(*args: str) -> "subprocess.CompletedProcess[bytes]":
    return subprocess.run(("git", "-C", str(REPO), *args),
                          capture_output=True, timeout=GIT_TIMEOUT_S)


def main() -> int:
    print(f"== worktree-gc {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} ==",
          flush=True)
    probe = _git("rev-parse", "--git-dir")
    if probe.returncode != 0:
        detail = probe.stderr.decode(errors="replace").strip()
        print(f"cannot read the primary checkout ({detail!r}).", flush=True)
        if "not permitted" in detail.lower():
            print("This is the macOS TCC wall: grant Full Disk Access to "
                  "/usr/bin/python3 (System Settings → Privacy & Security), "
                  "then `launchctl kickstart` this job to verify.", flush=True)
        return 1

    fetched = _git("fetch", "origin", "main", "--quiet")
    if fetched.returncode != 0:
        print("(fetch failed — proceeding on last-known origin/main)", flush=True)

    with tempfile.TemporaryDirectory(prefix="worktree-gc-") as work:
        tool = Path(work) / "worktree_gc.py"
        cfg = Path(work) / "config.json"
        for target, path in ((tool, "scripts/worktree_gc.py"),
                             (cfg, "config/worktree_gc.json")):
            shown = _git("show", f"origin/main:{path}")
            if shown.returncode != 0 or not shown.stdout:
                print(f"cannot read {path} from origin/main — refusing "
                      "(fail-closed: policy truth unavailable)", flush=True)
                return 1
            target.write_bytes(shown.stdout)

        run = subprocess.run(
            (sys.executable, str(tool), "--apply",
             "--repo-root", str(REPO), "--config", str(cfg),
             "--json-out",
             str(Path.home() / "Library/Logs/macro_worktree_gc/last_run.json")),
            timeout=RUN_TIMEOUT_S,
        )
    print(f"== worktree-gc done rc={run.returncode} ==", flush=True)
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
