#!/usr/bin/env python3
"""The evening close pass's PRIMARY clock — host-native, launchd-fired (PR-B).

WHY A HOST CLOCK AT ALL. ``.github/workflows/close-pass.yml`` was the product
clock until 2026-08-15 and cannot be one. Measured Friday 2026-08-14: the
20:25 UTC cron line's run was CREATED at 20:52 — 27 minutes of pure scheduler
drift before a runner was even asked for — and its DST sibling at 21:47 then sat
95 minutes in the queue on the two-host `macstudio` pool. The board published
~19:20 ET against a 16:15 ET product target. That is not a slow job; it is a
clock that does not tick when it says it will, and the estate has measured the
same thing at larger scale: GitHub cron gaps of 90 min to 3 h 12 m
(``agentos/decisions/DEC-LER-LIVE-LANE-VPS-5MIN-REST.md``), which is why Live
Entry Radar's live lane runs off a VPS timer rather than Actions.

So the roles swap. This runner is the primary: ``launchd`` on the Mac Studio
fires it at 13:00 local (PT) Monday-Friday, which is 16:00 ET in both DST
regimes because both zones flip together. The workflow stays armed as a BOUNDED
BACKSTOP — it fast-exits when this lane already landed the session's board, and
announces loudly when it had to publish, so a silently-dead primary is visible
in the Actions log rather than only in a missing artifact.

WHAT THIS FILE IS, AND IS NOT. It is PLUMBING: locking, a fresh checkout, a
venv, an env file, a bounded wait, one subprocess, one discard, one receipt. It
computes nothing about the market and decides nothing about the board. Every
POLICY question — is today a session, is this session already published, which
names are admitted, what gets written where — belongs to
``scripts.close_pass_publish`` running out of a checkout this runner resets to
``origin/main`` immediately beforehand. That split is deliberate and it is the
same one ``scripts/prophet_rescue_launchd.py`` makes: the wrapper is frozen at
install time, the policy it launches is always current.

TWO COPIES OF THIS FILE RUN, WITH DIFFERENT JOBS — by design, not by accident:

  * ``$SUPPORT_DIR/close_pass_host_runner.py`` — installed by
    ``scripts/install_closepass_launchd.sh`` and executed by launchd with the
    system ``/usr/bin/python3``. It lives OUTSIDE ``~/Documents`` because launchd
    jobs cannot exec from there (the same wall ``ops/launchd/com.macro.chainheat.plist``
    documents). It is frozen at install time; re-run the installer after editing
    this file. MERGING A FIX TO THIS FILE DEPLOYS NOTHING (measured 2026-08-18,
    PR #5862). Every receipt therefore carries a ``bootstrap`` block naming the
    executing snapshot, and every run GRADES it against origin/main out loud.
  * ``<lane>/scripts/close_pass_host_runner.py --probe-close`` — the SAME file
    at ``origin/main`` vintage, run by the lane's venv python inside the lane
    checkout. Only this copy imports repo code, which is why the outer runner
    never has to import pandas to ask whether the closes have settled.

Stdlib only, no repo imports, no third-party package: the outer half must run on
a bare system python3 under launchd.

Usage:
  python3 scripts/close_pass_host_runner.py              # one pass
  python3 scripts/close_pass_host_runner.py --dry-run    # compute, publish nothing
  python3 scripts/close_pass_host_runner.py --now 2026-08-14T20:00:00Z
  python3 -m scripts.close_pass_host_runner --probe-close --session 2026-08-14
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional
from zoneinfo import ZoneInfo

# The repo-root pin (house guard: test_check_script_import_pinning). Not a
# formality here: ``--probe-close`` imports ``engine.close_pass`` IN-PROCESS,
# and without the pin a direct ``python scripts/close_pass_host_runner.py``
# from any other CWD would report the module "unavailable" for the wrong
# reason — an import-path artifact wearing the absence contract's clothes.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TAG = "close-pass-host"
ET = ZoneInfo("America/New_York")

#: The git VANTAGE POINT. Never the source of code that runs: the primary is
#: routinely parked, dirty or occupied, and house law forbids sessions from
#: touching its git state. It owns the object store, the remote, and the ``.env``.
PRIMARY_DEFAULT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")

#: The lane's own checkout, DELIBERATELY inside the primary's worktree root: a
#: git worktree must live with its repository, and a fleet root is where the
#: worktree GC already knows to look. It is created with ``--lock`` so that GC
#: (``research/WORKTREE_GC_POLICY.md``) keeps its hands off a production lane.
#:
#: NOTE ON SPARSENESS, because this is the one checkout in the estate that must
#: NOT be sparse: session worktrees are minted by ``.claude/hooks/worktree_create_sparse.py``
#: and omit ``data/`` (87 % of the tree). This one is created by RAW GIT, so the
#: hook never sees it and it is a FULL checkout — which is the point. The pass
#: computes off the committed price store, and a lane whose ``data/`` was omitted
#: would publish a board with no prices at all.
LANE_REL = Path(".claude/worktrees/closepass-host-lane")
LANE_LOCK_REASON = "closepass host lane (com.macro.closepass launchd primary)"

SUPPORT_DEFAULT = Path.home() / "Library" / "Application Support" / "macro-closepass"
LOG_DIR_DEFAULT = Path.home() / "Library" / "Logs" / "macro_closepass"
VENV_DEFAULT = Path.home() / ".cache" / "mm-venv-closepass"
#: The same interpreter close-pass.yml's venv step uses, so the lane and the
#: backstop resolve the same wheels.
PY312 = Path("/opt/homebrew/bin/python3.12")

# ── budgets ──────────────────────────────────────────────────────────────────
GIT_TIMEOUT_S = 180
#: The lane-prep PROBE (`rev-parse --git-dir`) is a metadata read that answers in
#: milliseconds on an idle box, so GIT_TIMEOUT_S was 180x more patience than it can
#: ever need — and patience is exactly the wrong currency here. 2026-08-17 W-ACCEPT
#: day 1: the probe blocked past 180s while the Studio ran the CN asia job plus a
#: render, `_sh` returned rc=124 with EMPTY output, and prepare_lane rendered it as
#: `primary checkout unreadable: ''` — indistinguishable from a corrupt repo. The
#: run refused at rc=1/lane_unprepared after 240s and the session lost its board.
#: A short timeout with retries survives a contention spike AND stays inside the
#: 16:12 ET wait deadline (3 x 30s + backoff << one 180s stall).
GIT_PROBE_TIMEOUT_S = 30
GIT_PROBE_ATTEMPTS = 3
GIT_PROBE_BACKOFF_S = (2.0, 5.0)
VENV_TIMEOUT_S = 300
PIP_TIMEOUT_S = 1800          # cold install is minutes; warm is skipped outright
PROBE_TIMEOUT_S = 120
HEAL_TIMEOUT_S = 480
PUBLISH_TIMEOUT_S = 1200
#: The hard wall-clock alarm, and it starts AFTER the close wait rather than at
#: process start. The wait is separately bounded by its own ET deadline (≤12 min
#: by construction), so charging it against the work budget would let a normal
#: wait shorten the publish. Worst case end-to-end is therefore ~12 + 25 = 37
#: minutes from 16:00 ET — done by ~16:37 ET, against a measured 19:20 ET.
HARD_ALARM_S = 25 * 60

# ── the close wait ───────────────────────────────────────────────────────────
#: Not 16:00:00. The close prints at 16:00 ET and no vendor has a grouped daily
#: bar in the same second; ten seconds costs nothing and keeps the first probe
#: from being a guaranteed miss.
WAIT_START_ET = dt.time(16, 0, 10)
#: Proceed regardless at 16:12 ET. The publisher SKIPS AND COUNTS any name
#: without today's bar (``skipped.no_todays_bar``), so waiting longer buys
#: coverage, never truth — and truth is already safe without the wait.
WAIT_DEADLINE_ET = dt.time(16, 12, 0)
#: How early the runner is willing to HOLD for the window. A launchd firing
#: lands ~10 s before it; a manual replay at 10:00 ET must not sleep six hours,
#: so anything further out than this skips the wait entirely.
WAIT_ARM_LEAD_S = 15 * 60
POLL_SPACING_S = 25
#: Consecutive probe errors that end the wait. A probe that cannot read (no key,
#: vendor 500) will not start reading within twelve minutes, and burning the
#: window on it delays the board for nothing.
PROBE_ERROR_BUDGET = 3

#: Every outcome below means PROCEED. The string is the receipt's record of WHY,
#: which is the only thing that distinguishes "we waited and the closes settled"
#: from "we never waited at all" three weeks later.
WAIT_OUTCOMES = (
    "grouped_final",     # the vendor reported a finalized grouped read
    "stable_snapshot",   # two consecutive identical snapshot reads
    "deadline",          # 16:12 ET — proceed degraded, the publisher counts skips
    "past_deadline",     # fired after the window (a late launchd, a replay)
    "outside_window",    # fired far outside it (a manual kickstart)
    "module_absent",     # engine.close_pass.massive_close is not in this checkout
    "probe_error",       # the probe kept failing
    "probe_unreadable",  # the probe answered something this runner does not know
    "skipped_dry_run",
)

_PROBE_STATUSES = ("final", "snapshot", "unavailable", "error")


# ─────────────────────────────────────────────────────────────────────────────
# Annotations — bare print, first thing on the line, flushed.
# ─────────────────────────────────────────────────────────────────────────────
def _notice(msg: str) -> None:
    """A GitHub annotation must START the line, so it is printed bare.

    This lane runs under launchd rather than in an Actions step, but the form is
    the house form (``tests/test_gh_annotation_line_start.py``) and the receipts
    read the same in both logs. ``flush`` is load-bearing: launchd's
    StandardOutPath is a pipe, so stdout is block-buffered and an unflushed line
    can be lost with the process.
    """
    print(f"::notice title={_TAG}::{msg}", flush=True)


def _warn(msg: str) -> None:
    print(f"::warning title={_TAG}::{msg}", flush=True)


def _error(msg: str) -> None:
    print(f"::error title={_TAG}::{msg}", flush=True)


def _log(msg: str) -> None:
    print(f"{_TAG} {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Paths — every one env-overridable, so a test never touches the real host state
# ─────────────────────────────────────────────────────────────────────────────
def primary_root() -> Path:
    return Path(os.environ.get("CLOSE_PASS_HOST_PRIMARY") or PRIMARY_DEFAULT)


def support_dir() -> Path:
    return Path(os.environ.get("CLOSE_PASS_HOST_SUPPORT") or SUPPORT_DEFAULT)


def venv_dir() -> Path:
    return Path(os.environ.get("CLOSE_PASS_HOST_VENV") or VENV_DEFAULT)


def log_dir() -> Path:
    return Path(os.environ.get("CLOSE_PASS_HOST_LOGS") or LOG_DIR_DEFAULT)


def lane_path() -> Path:
    override = os.environ.get("CLOSE_PASS_HOST_LANE")
    return Path(override) if override else primary_root() / LANE_REL


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess — ONE seam. Everything that leaves this process goes through _sh,
# so a test can record the whole conversation without a real git or a real venv.
# ─────────────────────────────────────────────────────────────────────────────
class ShResult(NamedTuple):
    rc: int
    out: str
    timed_out: bool


def _kill_group(proc: "subprocess.Popen[Any]") -> None:
    """SIGTERM then SIGKILL the child's whole process GROUP.

    ``subprocess.run(timeout=…)`` kills only the direct child, which for
    ``python -m scripts.close_pass_publish`` would leave any downloader it
    spawned holding the network and the price store. The children are started
    with ``start_new_session=True`` precisely so there is a group to signal.
    """
    for sig, grace in ((signal.SIGTERM, 10.0), (signal.SIGKILL, 5.0)):
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            continue


def _sh(argv, *, cwd=None, env=None, timeout=None, capture=True) -> ShResult:
    """Run a command. Never raises on a non-zero exit or a timeout.

    ``capture=False`` streams the child's output straight into the launchd log,
    which is what a twenty-minute publish needs — captured output would arrive
    only after the job finished, and only if it finished.
    """
    argv = [str(a) for a in argv]
    try:
        proc = subprocess.Popen(
            argv, cwd=(str(cwd) if cwd else None), env=env,
            stdout=(subprocess.PIPE if capture else None),
            stderr=(subprocess.STDOUT if capture else None),
            text=True, start_new_session=True,
        )
    except OSError as exc:
        return ShResult(127, f"{type(exc).__name__}: {exc}", False)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return ShResult(proc.returncode, out or "", False)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            out, _ = proc.communicate(timeout=15)
        except Exception:            # noqa: BLE001 — a wedged pipe must not win
            out = ""
        return ShResult(124, out or "", True)


# ─────────────────────────────────────────────────────────────────────────────
# Single instance
# ─────────────────────────────────────────────────────────────────────────────
def acquire_lock(path: Path):
    """``flock`` the runner's lock file, or return None if another run holds it.

    A second invocation is NOT an error: launchd will happily fire a job that is
    still running from a manual kickstart, and the honest response is to say so
    and exit clean. Refusing loudly would red a lane that is working perfectly.

    The file is opened ``a+`` and truncated only after the lock is won, so a
    losing invocation cannot erase the winner's pid stamp on its way out.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")     # noqa: SIM115 — held for the run
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()} {dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        fh.flush()
    except OSError:
        pass
    return fh


def release_lock(fh) -> None:
    if fh is None:
        return
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


# ─────────────────────────────────────────────────────────────────────────────
# The lane checkout
# ─────────────────────────────────────────────────────────────────────────────
def lane_ready(lane: Path) -> bool:
    """A worktree checkout has a ``.git`` FILE (a gitdir pointer), not a dir."""
    return (lane / ".git").exists() and (lane / "scripts").is_dir()


def _sh_detail(res: ShResult, timeout: float) -> str:
    """A human-actionable reason, which a bare `repr(out)` is not when out is ''.

    `_sh` reports a timeout as rc=124 with empty captured output (the group is
    killed, the pipe yields nothing), so every `f"...: {out!r}"` message
    degrades to `''` exactly when the box is too busy to answer — the one case
    where the operator most needs to be told what happened.
    """
    if res.timed_out:
        return f"timed out after {timeout:g}s (host contention, not corruption)"
    return repr((res.out or "").strip())


def _git_probe(sh: Callable[..., ShResult], argv, *,
               attempts: int = GIT_PROBE_ATTEMPTS,
               timeout: float = GIT_PROBE_TIMEOUT_S,
               sleep: Optional[Callable[[float], None]] = None) -> ShResult:
    """Run a cheap git metadata command, retrying a TIMEOUT (never an error).

    Only `timed_out` is retried: a real failure (corrupt repo, missing path, TCC
    denial) is deterministic and re-running it just burns the wait window.
    """
    # Resolved at CALL time, not bound as a default: a default of ``time.sleep``
    # captures the function object at import, so monkeypatching ``time.sleep``
    # in a test silently does nothing and the suite pays real backoff seconds.
    _sleep = sleep or time.sleep
    res = sh(argv, timeout=timeout)
    for i in range(attempts - 1):
        if not res.timed_out:
            return res
        delay = GIT_PROBE_BACKOFF_S[min(i, len(GIT_PROBE_BACKOFF_S) - 1)]
        _warn(f"git probe {' '.join(str(a) for a in argv[-2:])!r} timed out after "
              f"{timeout:g}s (attempt {i + 1}/{attempts}) — retrying in {delay:g}s")
        _sleep(delay)
        res = sh(argv, timeout=timeout)
    return res


def prepare_lane(primary: Path, lane: Path, *, sh: Callable[..., ShResult] = _sh) -> dict:
    """Create-if-absent, fetch, hard-reset the lane to ``origin/main``.

    Returns ``{"ok", "code_sha", "code_stale", "detail"}``.

    THE TWO FAILURES ARE NOT THE SAME FAILURE, and the asymmetry is the whole
    point of the ``code_stale`` flag:

      * ``fetch`` fails (network, GitHub down) → PROCEED on the previous
        ``origin/main``. The board matters more than the vintage, and the
        vintage is a day old at worst. But it is DISCLOSED in the receipt, so a
        week of quietly stale runs cannot hide behind a green log.
      * ``reset`` fails → REFUSE. Then the working tree is in an unknown state
        and "which code ran" has no answer at all, which is exactly the thing
        the receipt exists to be able to answer.
    """
    out = {"ok": False, "code_sha": "", "code_stale": False, "detail": ""}

    probe = _git_probe(sh, ["git", "-C", primary, "rev-parse", "--git-dir"])
    if probe.rc != 0:
        detail = (probe.out or "").strip()
        out["detail"] = f"primary checkout unreadable: {_sh_detail(probe, GIT_PROBE_TIMEOUT_S)}"
        if "not permitted" in detail.lower():
            out["detail"] += (" — this is the macOS TCC wall: grant Full Disk Access"
                              " to /usr/bin/python3, then kickstart the job again")
        return out

    if not lane_ready(lane):
        add = sh(["git", "-C", primary, "worktree", "add", "--detach",
                  "--lock", "--reason", LANE_LOCK_REASON, lane, "origin/main"],
                 timeout=GIT_TIMEOUT_S)
        if add.rc != 0 and "already registered" in (add.out or "").lower():
            # The directory was removed under a live registration (an operator
            # tidy-up, a failed disk). Prune the corpse and try once more —
            # otherwise the lane is dead forever and nothing says why.
            sh(["git", "-C", primary, "worktree", "prune"], timeout=GIT_TIMEOUT_S)
            add = sh(["git", "-C", primary, "worktree", "add", "--detach",
                      "--lock", "--reason", LANE_LOCK_REASON, lane, "origin/main"],
                     timeout=GIT_TIMEOUT_S)
        if add.rc != 0:
            out["detail"] = f"worktree add failed: {_sh_detail(add, GIT_TIMEOUT_S)}"
            return out
        _log(f"created the lane checkout at {lane} (locked, FULL — data/ included)")

    fetch = sh(["git", "-C", lane, "fetch", "origin", "main", "--quiet"],
               timeout=GIT_TIMEOUT_S)
    if fetch.rc != 0:
        out["code_stale"] = True
        _warn("fetch origin/main failed — proceeding on the previous HEAD; the "
              "receipt records code_stale=true")

    reset = sh(["git", "-C", lane, "reset", "--hard", "origin/main", "--quiet"],
               timeout=GIT_TIMEOUT_S)
    if reset.rc != 0:
        out["detail"] = f"reset --hard origin/main failed: {_sh_detail(reset, GIT_TIMEOUT_S)}"
        return out

    # ``-e /data`` keeps the committed price store's untracked neighbours out of
    # the sweep: ``reset --hard`` already restores every TRACKED byte under
    # data/, and blowing away the rest would make each run re-download a store
    # this lane exists to read fast. The pass's OWN data/ writes are discarded
    # after the publish (discard_data), which is the narrow, timed version of
    # the same contract close-pass.yml carries.
    sh(["git", "-C", lane, "clean", "-fdq", "-e", "/data"], timeout=GIT_TIMEOUT_S)

    head = sh(["git", "-C", lane, "rev-parse", "HEAD"], timeout=GIT_TIMEOUT_S)
    out["code_sha"] = (head.out or "").strip() if head.rc == 0 else ""
    out["ok"] = True
    return out


def discard_data(lane: Path, *, sh: Callable[..., ShResult] = _sh) -> None:
    """The pass's data/ writes, undone — the workflow's discard step, host-side.

    The ``--heal`` prefetch refreshes ``data/yahoo/*.parquet``; the nightly is
    the sole writer of record for everything under data/, so those writes are
    scratch by contract (G0.2, DNR:KILL-INTRADAY-CHRONICLE). Best-effort on
    purpose: a failed discard must not fail a published board, and the next
    run's ``reset --hard`` restores every tracked byte anyway.
    """
    for argv in (["git", "-C", lane, "checkout", "--", "data/"],
                 ["git", "-C", lane, "clean", "-fdq", "data/"]):
        res = sh(argv, timeout=GIT_TIMEOUT_S)
        if res.rc != 0:
            _warn(f"discard step {' '.join(argv[-2:])!r} returned {res.rc} — the "
                  "next run's reset --hard restores the tracked store regardless")


# ─────────────────────────────────────────────────────────────────────────────
# Is today a session? — asked of the CHECKOUT, answered by lib.nyse_calendar
# ─────────────────────────────────────────────────────────────────────────────
_SESSION_SNIPPET = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from datetime import date\n"
    "from lib.nyse_calendar import is_session\n"
    "d = date.fromisoformat(sys.argv[2])\n"
    "print(json.dumps({'session': d.isoformat() if is_session(d) else None}))\n"
)


def session_probe(lane: Path, python: Path, *, now: dt.datetime,
                  sh: Callable[..., ShResult] = _sh) -> dict:
    """``{"ok": bool, "session": str|None}`` for the ET date of ``now``.

    Asked of the checkout rather than reimplemented here: "when is the market
    open" already has exactly one definition in this lane
    (``lib.nyse_calendar``), and a second one in the runner is a second thing to
    keep in step with the holiday list.

    FAIL-OPEN, deliberately. This probe is an OPTIMISATION — it saves a fetch, a
    venv and a twenty-minute publish on the ~9 full-day closures a year. The
    AUTHORITY is ``close_pass_publish.session_date``, which runs from fresh code
    a minute later and no-ops on a non-session day all by itself. So an
    unreadable probe proceeds; only a confident "not a session" stops the run.
    """
    et_date = now.astimezone(ET).date().isoformat()
    res = sh([python, "-c", _SESSION_SNIPPET, lane, et_date], cwd=lane, timeout=60)
    if res.rc != 0:
        return {"ok": False, "session": None}
    payload = _last_json(res.out)
    if not isinstance(payload, dict) or "session" not in payload:
        return {"ok": False, "session": None}
    return {"ok": True, "session": payload["session"]}


def _last_json(text: str) -> Any:
    """The last line of ``text`` that parses as JSON, or None.

    The probes run inside a checkout whose imports may print warnings, so the
    payload is read off the END rather than assumed to be the whole output.
    """
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The venv — reused across runs, reinstalled only when requirements.txt moves
# ─────────────────────────────────────────────────────────────────────────────
def venv_python(venv: Optional[Path] = None) -> Path:
    return (venv or venv_dir()) / "bin" / "python"


def ensure_venv(lane: Path, *, venv: Optional[Path] = None,
                support: Optional[Path] = None,
                sh: Callable[..., ShResult] = _sh) -> Optional[Path]:
    """Return the lane's interpreter, creating/updating it only when needed.

    ``pip install -r requirements.txt`` is minutes cold and pointless warm, and
    this lane has a twelve-minute window it would rather spend waiting for the
    closes. So the requirements file's SHA-256 is cached beside the lock: same
    hash, no pip at all. The stamp is written only AFTER a successful install,
    so a failed one retries next run instead of latching a lie.
    """
    venv = venv or venv_dir()
    support = support or support_dir()
    python = venv_python(venv)

    if not python.exists():
        base = PY312 if PY312.exists() else None
        if base is None:
            for candidate in ("python3.12", "python3"):
                found = _which(candidate)
                if found:
                    base = found
                    break
        if base is None:
            _error("no python3.12 on this host — cannot build the lane venv")
            return None
        made = sh([base, "-m", "venv", venv], timeout=VENV_TIMEOUT_S)
        if made.rc != 0 or not python.exists():
            _error(f"venv creation failed ({made.rc}): {(made.out or '').strip()!r}")
            return None
        sh([python, "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
           timeout=PIP_TIMEOUT_S)

    requirements = lane / "requirements.txt"
    try:
        digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    except OSError:
        _warn("requirements.txt unreadable in the lane — leaving the venv as it is")
        return python
    stamp = support / "requirements.sha256"
    try:
        current = stamp.read_text(encoding="utf-8").strip()
    except OSError:
        current = ""
    if current == digest:
        return python

    _log("requirements.txt changed since the last install — running pip")
    installed = sh([python, "-m", "pip", "install", "--quiet", "-r", requirements],
                   cwd=lane, timeout=PIP_TIMEOUT_S)
    if installed.rc != 0:
        _warn(f"pip install returned {installed.rc} — proceeding on the venv as it "
              "stands; the publish will report anything genuinely missing")
        return python
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(digest + "\n", encoding="utf-8")
    return python


def _which(name: str) -> Optional[Path]:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The environment handed to the pass
# ─────────────────────────────────────────────────────────────────────────────
#: The keys the publish genuinely cannot work without. Named so an absent one is
#: a NAMED warning rather than a boto3 traceback twenty minutes later.
R2_KEYS = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


def load_env_file(path: Path) -> dict:
    """Parse a ``KEY=VALUE`` env file. Values are NEVER logged, anywhere."""
    parsed: dict = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return parsed
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        parsed[key] = value.strip().strip('"').strip("'")
    return parsed


def build_env(primary: Path, *, base: Optional[dict] = None) -> dict:
    """The subprocess environment: the host ``.env``, then the lane's overrides.

    The overrides are not preferences, they are the lane's contract:

      * ``CLOSE_PASS_SERVED_PATH=""`` — R2 only. The VPS owns the served copy and
        mirrors R2 every five minutes through 23:00 UTC
        (``app/deploy/macro-live-closepass.timer``); a second writer of
        ``/var/lib/macro-live/...`` on a machine that is not the VPS would be
        writing into a directory that does not exist there anyway.
      * ``RENDER_NO_DRIP=1`` — the closing-bell idiom, job-wide in the workflow.
      * ``COLLECT_LANE`` UNSET — every engine ledger writer self-gates on it, and
        unset is how a non-ledger lane says so. Popped LAST so a stray value in
        the host ``.env`` cannot reintroduce it.
    """
    env = dict(os.environ if base is None else base)
    parsed = load_env_file(primary / ".env")
    env.update(parsed)
    env["CLOSE_PASS_SERVED_PATH"] = ""
    env["RENDER_NO_DRIP"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("COLLECT_LANE", None)

    _log(f"env: {len(parsed)} key(s) read from the primary .env (values never logged)")
    missing = [k for k in R2_KEYS if not env.get(k)]
    if missing:
        _warn(f"{', '.join(missing)} absent — the R2 PUT will fail and the VPS "
              "mirror will not see this pass")
    return env


# ─────────────────────────────────────────────────────────────────────────────
# The close wait
# ─────────────────────────────────────────────────────────────────────────────
def probe_close(lane: Path, python: Path, env: dict, session: str, *,
                sh: Callable[..., ShResult] = _sh) -> dict:
    """Ask the LANE whether the session's closes have settled.

    Run as a subprocess inside the lane so this file never imports pandas: the
    outer runner is executed by ``/usr/bin/python3`` under launchd and has no
    third-party packages at all.
    """
    res = sh([python, "-m", "scripts.close_pass_host_runner",
              "--probe-close", "--session", session],
             cwd=lane, env=env, timeout=PROBE_TIMEOUT_S)
    payload = _last_json(res.out)
    if isinstance(payload, dict) and payload.get("status") in _PROBE_STATUSES:
        return payload
    detail = (res.out or "").strip().splitlines()[-1:] or [""]
    return {"status": "error", "detail": f"rc={res.rc} {detail[0][:200]!r}"}


def wait_for_close(*, probe: Callable[[], dict],
                   now_fn: Callable[[], dt.datetime],
                   sleep_fn: Callable[[float], None]) -> tuple:
    """Hold until the closes settle, or until 16:12 ET. Returns (outcome, polls).

    EVERY branch proceeds — this function chooses WHEN to publish, never
    WHETHER. That is what makes it safe to be wrong: the publisher skips and
    counts any name without today's bar, so an early publish degrades coverage
    visibly and never carries a stale price as a fresh one.

    The decision table, in the order it is evaluated:

      finalized grouped read      → grouped_final    publish now
      identical snapshot twice    → stable_snapshot  publish now
      module absent (PR-A unmerged) → module_absent  publish now, no wait at all
      3 consecutive probe errors  → probe_error      publish now
      16:12 ET                    → deadline         publish now, degraded
      fired outside the window    → past_deadline / outside_window
    """
    et_now = now_fn().astimezone(ET)
    start = dt.datetime.combine(et_now.date(), WAIT_START_ET, tzinfo=ET)
    deadline = dt.datetime.combine(et_now.date(), WAIT_DEADLINE_ET, tzinfo=ET)

    if et_now >= deadline:
        return "past_deadline", 0
    if (start - et_now).total_seconds() > WAIT_ARM_LEAD_S:
        return "outside_window", 0
    if et_now < start:
        sleep_fn((start - et_now).total_seconds())

    errors = 0
    last_digest = None
    polls = 0
    while True:
        if now_fn().astimezone(ET) >= deadline:
            return "deadline", polls
        state = probe()
        polls += 1
        status = state.get("status")
        if status == "unavailable":
            # PR-A (engine/close_pass/massive_close.py) is not in this checkout.
            # There is nothing to wait ON, so waiting would be twelve minutes of
            # sleeping for no information.
            return "module_absent", polls
        if status == "final":
            return "grouped_final", polls
        if status == "error":
            errors += 1
            last_digest = None
            if errors >= PROBE_ERROR_BUDGET:
                return "probe_error", polls
        elif status == "snapshot":
            errors = 0
            digest = state.get("digest")
            # TWO consecutive identical reads, and only on a digest the probe
            # actually produced: `None == None` would call an empty vendor
            # response "stable" and publish into a hole.
            if digest is not None and digest == last_digest:
                return "stable_snapshot", polls
            last_digest = digest
        else:
            return "probe_unreadable", polls
        # Never sleep PAST the deadline. A flat 25 s nap overshoots it by up to
        # a poll, which turns "proceed at 16:12" into "proceed at 16:12 and a
        # bit" — small, but the deadline is the one number this function
        # promises and it should mean what it says.
        remaining = (deadline - now_fn().astimezone(ET)).total_seconds()
        if remaining <= 0:
            return "deadline", polls
        sleep_fn(min(float(POLL_SPACING_S), remaining))


# ── the probe half: runs INSIDE the lane, with the lane's interpreter ─────────
def _probe_payload(module: Any, session: str) -> dict:
    """Duck-typed adapter over PR-A's close reader.

    PR-A (``engine/close_pass/massive_close.py``) is IN FLIGHT and its exact
    surface is not settled, so this reads whichever of a small set of shapes it
    turns out to have and reports ``unavailable`` when it recognises none. That
    is the fail-safe direction by construction: an unrecognised module skips the
    wait and publishes immediately, which is exactly today's behaviour. It never
    blocks, never guesses a close, and never touches the board.
    """
    for name in ("close_probe", "session_close_state"):
        hook = getattr(module, name, None)
        if callable(hook):
            state = hook(session)
            if isinstance(state, dict) and state.get("status") in _PROBE_STATUSES:
                return dict(state)

    fetch = getattr(module, "fetch_session_closes", None)
    if not callable(fetch):
        return {"status": "unavailable",
                "detail": "massive_close exposes no recognised close reader"}

    closes, final = _split_close_result(fetch(session))
    if closes is None:
        return {"status": "unavailable",
                "detail": "fetch_session_closes returned an unreadable shape"}
    return {"status": "final" if final else "snapshot",
            "n": len(closes), "digest": _digest(closes)}


def _split_close_result(got: Any) -> tuple:
    """``(closes_mapping, finalized_bool_or_None)`` out of whatever PR-A returns."""
    final = None
    if isinstance(got, tuple) and len(got) == 2:
        got, final = got
    for attr in ("finalized", "is_final", "final", "complete"):
        if isinstance(got, dict) and attr in got:
            final = bool(got.get(attr))
        elif hasattr(got, attr):
            final = bool(getattr(got, attr))
    for attr in ("closes", "prices", "rows"):
        if isinstance(got, dict) and isinstance(got.get(attr), dict):
            return got[attr], final
        inner = getattr(got, attr, None)
        if isinstance(inner, dict):
            return inner, final
    if isinstance(got, dict) and all(isinstance(k, str) for k in got):
        return got, final
    return None, final


def _digest(closes: dict) -> str:
    """A stable fingerprint of a close set — the "did anything move" comparand."""
    body = "\n".join(f"{k}={closes[k]!r}" for k in sorted(closes, key=str))
    return hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()[:16]


def probe_close_main(session: str) -> int:
    """``--probe-close``: print ONE json line, always exit 0.

    Exit code is not the channel — the JSON is. A non-zero exit here would be
    indistinguishable from "the interpreter is broken", and the caller already
    treats an unparseable answer as an error.
    """
    try:
        from engine.close_pass import massive_close as module  # noqa: PLC0415
    except Exception as exc:          # noqa: BLE001 — ANY import failure degrades
        print(json.dumps({"status": "unavailable",
                          "detail": f"{type(exc).__name__}: {exc}"[:200]}), flush=True)
        return 0
    try:
        payload = _probe_payload(module, session)
    except Exception as exc:          # noqa: BLE001
        payload = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"[:200]}
    print(json.dumps(payload), flush=True)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# The receipt — LOCAL TELEMETRY. Never data/, never git, never a ledger.
# ─────────────────────────────────────────────────────────────────────────────
#: v2 replaced the bare ``runner_sha`` hex with the namespaced ``bootstrap``
#: block below — a rename ON PURPOSE, so a receipt that predates the drift
#: check is distinguishable from one whose check found nothing wrong.
RECEIPT_SCHEMA = "close_pass.host_run/v2"
RECEIPT_KEEP = 90


def write_receipt(support: Path, receipt: dict) -> Optional[Path]:
    """One JSON file per session under ``<support>/runs/``, written atomically.

    This is the answer to "did the primary fire, and what did it see" three
    weeks later, and it is the ONLY thing that distinguishes a lane that waited
    and published from a lane that never woke up — a killed or missing run and a
    run that never existed leave the same trace, which is nothing.
    """
    runs = support / "runs"
    try:
        runs.mkdir(parents=True, exist_ok=True)
        path = runs / f"{receipt.get('session') or 'no-session'}.json"
        tmp = runs / f".{path.name}.tmp"
        tmp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        _warn(f"run receipt not written ({exc})")
        return None
    _prune_receipts(runs)
    return path


def _prune_receipts(runs: Path, keep: int = RECEIPT_KEEP) -> None:
    try:
        files = sorted(p for p in runs.glob("*.json"))
    except OSError:
        return
    for stale in files[:-keep] if len(files) > keep else []:
        try:
            stale.unlink()
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# The BOOTSTRAP's identity — a DIFFERENT question from ``code_sha``
# ─────────────────────────────────────────────────────────────────────────────
# TWO VINTAGES RUN EVERY EVENING AND ONLY ONE MOVES WHEN A PR MERGES:
#
#   * the LANE's ``code_sha`` — a 40-hex GIT COMMIT, hard-reset to origin/main on
#     every run. It reports today's main even when the code computing it is weeks
#     old, which is the direction that makes it dangerous.
#   * this BOOTSTRAP — the snapshot launchd execs out of Application Support,
#     whose only vintage is the BYTES ON DISK. ``install_closepass_launchd.sh``
#     copies it at install time ON PURPOSE (a mid-day push to main must not change
#     what the clock executes), so a merged fix to this file sits inert until an
#     operator re-runs the installer.
#
# MEASURED 2026-08-18: PR #5862 fixed prepare_lane's timeout blindness and merged
# as af416e4a1066; the installed snapshot stayed byte-identical to the PRE-fix
# main, dated Aug 15 19:54, with ``grep -c _git_probe`` returning 0 on it. That
# evening's receipt looked perfect — ``code_sha`` was af416e4a — and the one
# bootstrap field it carried, ``runner_sha``, was compared to nothing at all.
#
# So the block is NAMESPACED and every digest key says what it hashed:
# ``receipt["code_sha"]`` is a git commit, ``receipt["bootstrap"]["file_sha256"]``
# is a content digest of a file. The two 12-hex prefixes they replaced were
# indistinguishable side by side in a real receipt; these cannot be.
RUNNER_BASENAME = "close_pass_host_runner.py"
#: This file's path inside a checkout — the origin/main REFERENCE a run grades
#: the executing bootstrap against. The lane is already reset to origin/main by
#: ``prepare_lane``, so the reference costs one file read and no network.
RUNNER_REPO_REL = f"scripts/{RUNNER_BASENAME}"
#: Bounded and short: the vintage walk is diagnosis, never the pass. Both calls
#: are metadata-only and are paid ONLY after a mismatch is already proven.
BOOTSTRAP_GIT_TIMEOUT_S = 30
#: How far back the vintage walk looks. This file has tens of commits, not
#: thousands; past the window the honest answer is "older than N", not a number.
BOOTSTRAP_LOG_SCAN = 50


def _file_sha256(path: Path) -> str:
    """Full 64 hex, never truncated. A 12-hex prefix reads exactly like the short
    form of a git commit, which is the confusion this whole block exists to end."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _file_mtime_utc(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return ""
    return dt.datetime.fromtimestamp(
        stamp, dt.timezone.utc).isoformat(timespec="seconds")


def bootstrap_identity() -> dict:
    """WHO IS EXECUTING — answerable with no git, no lane and no network.

    Filled in at receipt construction, before anything can fail, so a run that
    refuses at ``lane_unprepared`` still says which plumbing refused. Not
    hypothetical: the 2026-08-17 refusal that cost W-ACCEPT day 1 left a receipt
    naming a lane it never prepared and a bootstrap it never identified.

    ``installed_*`` is recorded even when it IS this file, because the equality
    is the interesting fact: under launchd they are the same path, and a run
    where they are not is a session exercising something launchd will not.
    """
    executing = Path(__file__).resolve()
    installed = (support_dir() / RUNNER_BASENAME).resolve()
    return {
        "path": str(executing),
        "file_sha256": _file_sha256(executing),
        "mtime": _file_mtime_utc(executing),
        "is_installed_copy": executing == installed,
        "installed_path": str(installed),
        "installed_file_sha256": _file_sha256(installed),
        "main_file_sha256": "",
        "matches_main": None,
        "commits_behind": None,
        "detail": "not compared — no origin/main checkout was prepared this run",
    }


def _bootstrap_commits_behind(lane: Path, path: str, *,
                              sh: Callable[..., ShResult] = _sh) -> Optional[int]:
    """Commits that touched THIS FILE between the executing vintage and origin/main.

    Deliberately NOT "commits behind main": the wire lanes push ~24 times a night,
    so that number would be weather. The number an operator can act on is how many
    times the thing they are running was changed without being redeployed.

    ``hash-object`` for the executing file's blob id, then ONE ``log --raw`` whose
    every entry carries the resulting blob for the path. Anything unexpected
    answers None — an unknown distance must never render as zero.
    """
    blob = sh(["git", "-C", lane, "hash-object", path],
              timeout=BOOTSTRAP_GIT_TIMEOUT_S)
    lines = [ln.strip() for ln in (blob.out or "").splitlines() if ln.strip()]
    want = lines[-1] if lines else ""
    if blob.rc != 0 or len(want) != 40:
        return None
    log = sh(["git", "-C", lane, "log", f"-n{BOOTSTRAP_LOG_SCAN}", "--format=%H",
              "--raw", "--no-abbrev", "origin/main", "--", RUNNER_REPO_REL],
             timeout=BOOTSTRAP_GIT_TIMEOUT_S)
    if log.rc != 0:
        return None
    behind = 0
    for line in (log.out or "").splitlines():
        # :<oldmode> <newmode> <oldblob> <newblob> <status>\t<path>
        if not line.startswith(":"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[3] == want:
            return behind
        behind += 1
    return None


def compare_bootstrap_to_main(lane: Path, identity: dict, *, stale: bool,
                              sh: Callable[..., ShResult] = _sh) -> dict:
    """Grade the executing bootstrap against origin/main's copy. Never raises.

    THE ASYMMETRY IS DELIBERATE and it is the same one ``prepare_lane`` already
    makes about ``code_stale``:

      * bytes DIFFER from the reference → ``matches_main = False``, and that is
        certain even against a stale origin/main: a file that does not match an
        older main cannot match a newer main descended from it.
      * bytes MATCH a STALE reference → ``None``, never True. The fetch failed,
        so "identical to what main was yesterday" is not "identical to main", and
        a drift detector that certifies against a reference it could not refresh
        is the blind kind.

    A clean verdict therefore requires an AFFIRMATIVE match against a refreshed
    reference. Absence of evidence never renders as ``ok``.
    """
    out = dict(identity)
    reference = lane / "scripts" / RUNNER_BASENAME
    out["main_file_sha256"] = _file_sha256(reference)
    if not out["main_file_sha256"]:
        out["detail"] = (f"not compared — origin/main's {RUNNER_REPO_REL} is not "
                         f"readable at {reference}")
        return out
    if not out["file_sha256"]:
        out["detail"] = (f"not compared — the executing bootstrap at {out['path']} "
                         f"is not readable")
        return out

    if out["file_sha256"] != out["main_file_sha256"]:
        out["matches_main"] = False
        out["commits_behind"] = _bootstrap_commits_behind(lane, out["path"], sh=sh)
        behind = out["commits_behind"]
        out["detail"] = (
            f"the executing bootstrap is NOT origin/main's {RUNNER_REPO_REL} — "
            + (f"{behind} commit(s) to that file are not deployed"
               if isinstance(behind, int) else
               f"its vintage is not among the last {BOOTSTRAP_LOG_SCAN} commits "
               f"that touched the file")
            + "; re-run scripts/install_closepass_launchd.sh")
        return out

    if stale:
        out["detail"] = (
            "byte-identical to the lane's origin/main, but this run's fetch failed "
            "(code_stale) so the reference may itself be behind — reported as "
            "unverified rather than clean")
        return out

    out["matches_main"] = True
    out["commits_behind"] = 0
    out["detail"] = f"byte-identical to origin/main's {RUNNER_REPO_REL}"
    return out


def announce_bootstrap(identity: dict) -> None:
    """Say it OUT LOUD, and never heal it.

    Self-updating would defeat the freeze the installer exists to provide — a
    mid-day push to main must not change what the clock executes — so the entire
    remedy this lane owns is DISCLOSURE with the exact command attached. The run
    continues on whatever snapshot started it; a drifted bootstrap that still
    publishes a board is a reporting failure, not a reason to lose the session.
    """
    running = (identity.get("file_sha256") or "")[:12] or "unknown"
    verdict = identity.get("matches_main")
    if verdict is True:
        _log(f"bootstrap file_sha256 {running} (mtime {identity.get('mtime') or '?'}) "
             f"is origin/main's {RUNNER_REPO_REL} — no drift")
    elif verdict is False:
        behind = identity.get("commits_behind")
        gap = (f"{behind} commit(s) behind" if isinstance(behind, int)
               else "an unknown distance behind")
        _error(
            f"BOOTSTRAP DRIFT — launchd is executing {identity.get('path')}, which is "
            f"{gap} origin/main's {RUNNER_REPO_REL} (running file_sha256 {running}, "
            f"origin/main {(identity.get('main_file_sha256') or '')[:12]}, snapshot "
            f"mtime {identity.get('mtime') or '?'}). MERGING DOES NOT DEPLOY THIS "
            f"FILE — run: bash scripts/install_closepass_launchd.sh. This run "
            f"continues on the snapshot it started with: disclosed, never self-healed")
    else:
        _warn(f"bootstrap vintage UNVERIFIED — {identity.get('detail')}. A snapshot "
              f"weeks behind origin/main writes a receipt that looks exactly like "
              f"this one, so this is a gap in the evidence, not a clean bill")

    # A session running the repo copy grades ITSELF above; the file launchd will
    # actually exec tonight is a different question and gets its own answer.
    if not identity.get("is_installed_copy"):
        installed = identity.get("installed_file_sha256") or ""
        main = identity.get("main_file_sha256") or ""
        _notice(f"this is not the installed snapshot — launchd execs "
                f"{identity.get('installed_path')}")
        if installed and main and installed != main:
            _error(
                f"BOOTSTRAP DRIFT (installed) — the snapshot launchd execs, "
                f"{identity.get('installed_path')} (file_sha256 {installed[:12]}), is "
                f"not origin/main's {RUNNER_REPO_REL} ({main[:12]}); this run "
                f"exercised a different file. Run: bash scripts/install_closepass_launchd.sh")


# ─────────────────────────────────────────────────────────────────────────────
# The pass
# ─────────────────────────────────────────────────────────────────────────────
def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def run(*, now: dt.datetime, dry_run: bool = False,
        sh: Callable[..., ShResult] = _sh,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now_fn: Callable[[], dt.datetime] = _utc_now) -> int:
    """One host-native close pass. 0 on any outcome that is not a lane fault.

    ``now`` is the SESSION clock and honours ``--now`` for replays; ``now_fn`` is
    the WALL clock the close wait runs on and does not. Replaying an old session
    must not convince the runner it is 16:00 ET and make it hold for twelve
    minutes; it lands on ``past_deadline`` and publishes, which is right.
    """
    primary, lane, support = primary_root(), lane_path(), support_dir()
    started = clock()
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "session": None,
        "fired_at": now.astimezone(dt.timezone.utc).isoformat(),
        "close_wait_outcome": None,
        "close_wait_polls": 0,
        "publish_rc": None,
        "heal_rc": None,
        "code_sha": "",
        "code_stale": False,
        "duration_sec": 0.0,
        "log_tail": str(log_dir() / "launchd.out.log"),
        "lane": str(lane),
        "dry_run": bool(dry_run),
        # WHO IS RUNNING, filled before anything can fail — see bootstrap_identity.
        "bootstrap": bootstrap_identity(),
        "outcome": "started",
    }

    def _finish(code: int, outcome: str) -> int:
        receipt["outcome"] = outcome
        receipt["duration_sec"] = round(clock() - started, 1)
        write_receipt(support, receipt)
        _log(f"done rc={code} outcome={outcome} "
             f"duration={receipt['duration_sec']}s")
        return code

    # (1) The cheapest possible holiday exit: if a lane checkout is already on
    #     disk, ask it before spending a single network call. A steady-state
    #     holiday costs one interpreter start.
    python_hint = venv_python()
    if not python_hint.exists():
        python_hint = Path(sys.executable)
    if lane_ready(lane):
        early = session_probe(lane, python_hint, now=now, sh=sh)
        if early["ok"] and early["session"] is None:
            _notice("not a NYSE session day — no evening board (no fetch, no venv, "
                    "no publish; this is not a fault)")
            return _finish(0, "not_a_session")

    # (2) Fresh code. Everything after this point runs origin/main, or refuses.
    state = prepare_lane(primary, lane, sh=sh)
    receipt["code_sha"] = state["code_sha"]
    receipt["code_stale"] = state["code_stale"]
    # The lane is now origin/main, which makes THIS file's own origin/main copy a
    # free local reference. Graded before the refusal below on purpose: "which
    # bootstrap refused" is exactly the question the 2026-08-17 receipt could not
    # answer, and a stale snapshot is a live candidate cause of a refusal.
    if state["ok"]:
        receipt["bootstrap"] = compare_bootstrap_to_main(
            lane, receipt["bootstrap"], stale=state["code_stale"], sh=sh)
    announce_bootstrap(receipt["bootstrap"])
    if not state["ok"]:
        _error(f"lane checkout not prepared — refusing to run stale or unknown "
               f"code ({state['detail']})")
        return _finish(1, "lane_unprepared")

    # (3) Ask again on the fresh checkout: the answer that counts is the one the
    #     publisher's own guard will give a minute from now.
    probed = session_probe(lane, python_hint, now=now, sh=sh)
    if probed["ok"] and probed["session"] is None:
        _notice("not a NYSE session day — no evening board (this is not a fault)")
        return _finish(0, "not_a_session")
    session = probed["session"] or now.astimezone(ET).date().isoformat()
    receipt["session"] = session
    _log(f"session {session} · code {state['code_sha'][:12] or '(unknown)'}"
         f"{' STALE' if state['code_stale'] else ''}")

    # (4) The interpreter, and pip only if requirements moved.
    python = ensure_venv(lane, support=support, sh=sh)
    if python is None:
        return _finish(1, "no_interpreter")
    env = build_env(primary)

    # (5) Hold for the closes, bounded by 16:12 ET.
    if dry_run:
        outcome, polls = "skipped_dry_run", 0
    else:
        outcome, polls = wait_for_close(
            probe=lambda: probe_close(lane, python, env, session, sh=sh),
            now_fn=now_fn, sleep_fn=sleep_fn)
    receipt["close_wait_outcome"] = outcome
    receipt["close_wait_polls"] = polls
    _log(f"close wait: {outcome} after {polls} poll(s)")

    # (6) The work budget starts HERE — see HARD_ALARM_S.
    alarm_at = clock() + HARD_ALARM_S

    def _budget(cap: float) -> float:
        return max(1.0, min(cap, alarm_at - clock()))

    # The price-store prefetch, exactly as close-pass.yml runs it and for the
    # same reason: at 16:00 ET the committed store has no bar for today, and a
    # board computed without one skips every name. Best-effort and non-fatal
    # (the workflow's `continue-on-error: true`): a partial heal degrades
    # coverage, never truth, because the pass requires TODAY's bar per name.
    heal = sh([python, "-m", "scripts.check_price_store_freshness", "--heal"],
              cwd=lane, env=env, timeout=_budget(HEAL_TIMEOUT_S), capture=False)
    receipt["heal_rc"] = heal.rc
    if heal.rc != 0:
        _warn(f"price-store prefetch returned {heal.rc} — continuing; names without "
              "today's bar are skipped and counted by the pass itself")

    # (7) The pass.
    argv = [python, "-m", "scripts.close_pass_publish"]
    if dry_run:
        argv.append("--dry-run")
    if _now_was_overridden():
        argv += ["--now", os.environ["CLOSE_PASS_HOST_NOW"]]
    published = sh(argv, cwd=lane, env=env, timeout=_budget(PUBLISH_TIMEOUT_S),
                   capture=False)
    receipt["publish_rc"] = published.rc

    # (8) Undo the prefetch's writes whatever happened above — a failed publish
    #     leaves the same dirt a successful one does.
    discard_data(lane, sh=sh)

    if published.timed_out:
        _error("the pass exceeded its wall-clock budget and was killed — no board "
               "was published by this run; the GitHub backstop still covers the "
               "session")
        return _finish(1, "publish_timeout")
    if published.rc != 0:
        _error(f"the pass exited {published.rc} — the GitHub backstop still covers "
               "the session")
        return _finish(1, "publish_failed")
    return _finish(0, "published")


def _now_was_overridden() -> bool:
    return bool(os.environ.get("CLOSE_PASS_HOST_NOW"))


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Host-native primary clock for the evening close pass")
    ap.add_argument("--now", default=None,
                    help="ISO clock override (naive = UTC); propagated to the pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="run the whole lane; the pass publishes nothing")
    ap.add_argument("--probe-close", action="store_true",
                    help="internal: report the session's close state as one JSON "
                         "line (runs INSIDE the lane checkout)")
    ap.add_argument("--session", default=None, help="internal: --probe-close's session")
    args = ap.parse_args(argv)

    if args.probe_close:
        return probe_close_main(args.session or "")

    if args.now:
        parsed = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00"))
        # Naive stamps are UTC BY CONTRACT (the repo-wide #2463 convention).
        now = (parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None
               else parsed.astimezone(dt.timezone.utc))
        # Carried in the environment rather than through run()'s signature: the
        # value has to reach the PASS's own --now, and threading a CLI string
        # through every helper for a replay-only flag earns nothing.
        os.environ["CLOSE_PASS_HOST_NOW"] = args.now
    else:
        now = dt.datetime.now(dt.timezone.utc)
        os.environ.pop("CLOSE_PASS_HOST_NOW", None)

    stamp = now.isoformat(timespec="seconds")
    print(f"== close-pass host runner {stamp} ==", flush=True)

    lock = acquire_lock(support_dir() / "runner.lock")
    if lock is None:
        _notice("another close-pass host run holds the lock — exiting clean "
                "(this is not a fault)")
        return 0
    try:
        return run(now=now, dry_run=args.dry_run)
    finally:
        release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
