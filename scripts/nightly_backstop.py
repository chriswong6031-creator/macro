#!/usr/bin/env python3
"""Re-fire the US nightly when the night produced nothing — the CN lane's idiom.

WHY THE US LANE NEEDED THIS AND THE CN LANE DID NOT.  The operator's observation
on 2026-08-13 was exact: "China side perfectly refreshes nightly and we've been
having a week of problems on US side."  The asymmetry is structural, not luck:

    asia-close.yml  (CN/HK)   71,284 bytes   FIVE cron slots — 06:00, 06:40,
                                             07:20, 08:30, 09:30 UTC, commented
                                             in-file as "early bird" x3, "the
                                             original on-time slot", "backstop"
    daily.yml       (US)     465,841 bytes   ONE effective fire: a DST PAIR at
                                             22:30Z/23:30Z of which et_gate keeps
                                             exactly one

CN can lose a fire — to a runner outage, a cancellation, a transient collector
failure — and the next slot picks the night up.  The US lane gets one shot, so
any single loss costs a whole session of ledger that only the next night or a
force-majeure backfill can recover.  On 2026-08-11/12 it lost two in a row: the
#5362 workflow-size strand killed the cron outright, and every manual recovery
dispatch was force-cancelled.

WHY THIS IS A SEPARATE FILE AND NOT MORE CRONS IN daily.yml.  Adding the CN shape
literally would mean editing a workflow that already sits at 91% of GitHub's
512,000-byte processing cliff — the exact file whose growth caused this outage —
and entangling et_gate's DST regime matching, which is what guarantees the
nightly runs exactly once.  A separate small lane buys the same redundancy while
touching neither.

THE DISPATCH RULE.  Fire ONLY into a night that has produced nothing:

    any run queued or in progress   -> SKIP.  Never dispatch over a live run.
                                       This is the 2026-08-09 ci.yml livelock,
                                       where main-ref dispatches shared one
                                       cancel-in-progress group and each new
                                       dispatch killed the proof the whole fleet
                                       was waiting on — the escape hatch WAS the
                                       lock.  A long job inside its timeout is
                                       not evidence that it is wedged; tonight's
                                       bake ran 2h+ in `collect` and was healthy.
    any run concluded success       -> SKIP.  The night landed.
    >= MAX_DISPATCHES already fired -> SKIP and say so.  A systematically broken
                                       night must not become a dispatch storm on
                                       a 3-slot self-hosted pool; the liveness
                                       guard alarms at 08:00Z instead.
    cannot tell (API error)         -> SKIP.  Dispatching blind is how the
                                       livelock above happened.  Fail SAFE here,
                                       which for an ACTION means doing nothing —
                                       note that this is the opposite polarity
                                       from check_nightly_liveness.py, where
                                       blindness must not raise an alarm.
    otherwise                       -> DISPATCH.

et_gate lets a dispatch through unconditionally (`verdict = "true" if (event !=
"schedule" or fired == intended)`), so a backstop run executes the full pipeline
rather than being skipped as an off-regime firing.

Usage:
    python3 scripts/nightly_backstop.py              # decide and act
    python3 scripts/nightly_backstop.py --dry-run    # decide, print, never fire
    python3 scripts/nightly_backstop.py --selftest   # synthetic assertions

Exit codes:
    0  a decision was reached (dispatched, or correctly skipped)
    1  a dispatch was attempted and failed
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, time, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.nyse_calendar import expected_last_session  # noqa: E402

WORKFLOW_FILE = "daily.yml"
DEFAULT_REPO = (
    os.environ.get("GITHUB_REPOSITORY") or "mastermindx-market-intelligence/macro"
)

#: Same safe-earliest boundary check_nightly_liveness.py uses: any run created at
#: or after session D 22:00Z is D's bake, which covers both DST cron slots and the
#: dispatch lag that pushes real starts past 00:00Z.
FIRE_BOUNDARY_UTC = time(22, 0)

#: Backstop dispatches allowed per session. CN effectively gets four retries; two
#: is deliberately tighter because a US bake holds the 3-slot macstudio pool for
#: hours. Past this the liveness guard's 08:00Z alarm is the right escalation —
#: a night failing three times is not a transient and wants a human.
MAX_DISPATCHES = 2

PROBE_TIMEOUT_S = 30

LIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}


def fire_boundary(now: datetime) -> "tuple[str, datetime]":
    session = expected_last_session(now)
    return session.isoformat(), datetime.combine(
        session, FIRE_BOUNDARY_UTC, tzinfo=timezone.utc)


def _parse_dt(value: object) -> "datetime | None":
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def decide(runs: "list[dict] | None", now: datetime) -> dict:
    """Pure decision. ``{"dispatch": bool, "reason": str, "session": str}``."""
    session, boundary = fire_boundary(now)
    base = {"dispatch": False, "session": session,
            "boundary": boundary.isoformat()}

    if runs is None:
        return {**base, "reason": (
            "BLIND: could not list runs. Dispatching on an unknown state is the "
            "2026-08-09 livelock; doing nothing is the safe action for an actor.")}

    tonight = [r for r in runs
               if (dt := _parse_dt(r.get("created_at"))) is not None
               and dt >= boundary]

    live = [r for r in tonight if (r.get("status") or "") in LIVE_STATUSES]
    if live:
        return {**base, "reason": (
            f"LIVE: {len(live)} run(s) for session {session} still going. A long "
            "job inside its timeout is not wedged — never dispatch over it.")}

    if any((r.get("conclusion") or "") == "success" for r in tonight):
        return {**base, "reason": f"LANDED: session {session} already baked green."}

    fired = [r for r in tonight
             if (r.get("event") or "") == "workflow_dispatch"]
    if len(fired) >= MAX_DISPATCHES:
        return {**base, "reason": (
            f"CAPPED: {len(fired)} backstop dispatch(es) already fired for session "
            f"{session} (limit {MAX_DISPATCHES}). Escalating to the liveness alarm "
            "instead of storming a 3-slot pool.")}

    if not tonight:
        why = (f"NO RUN for session {session} since {boundary.isoformat()} — the "
               "cron did not fire at all (workflow-file strand, disabled workflow, "
               "or a dropped schedule).")
    else:
        states = ", ".join(f"{r.get('status')}/{r.get('conclusion') or '-'}"
                           for r in tonight)
        why = (f"ALL FAILED for session {session}: [{states}]. Nothing is alive and "
               "nothing landed.")
    return {**base, "dispatch": True, "reason": why}


def fetch_runs(repo: str) -> "list[dict] | None":
    try:
        proc = subprocess.run(
            ["gh", "run", "list", "--workflow", WORKFLOW_FILE, "--limit", "30",
             "--json", "databaseId,status,conclusion,createdAt,event",
             "--repo", repo],
            capture_output=True, timeout=PROBE_TIMEOUT_S)
    except Exception as exc:
        print(f"::warning title=backstop-blind::run list failed: "
              f"{exc.__class__.__name__}", flush=True)
        return None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[:200]
        print(f"::warning title=backstop-blind::gh exit {proc.returncode}: {detail}",
              flush=True)
        return None
    try:
        rows = json.loads(proc.stdout or b"[]")
    except ValueError:
        return None
    if not isinstance(rows, list):
        return None
    # gh's JSON uses camelCase; normalise to the REST spelling `decide` reads.
    return [{"created_at": r.get("createdAt"), "status": r.get("status"),
             "conclusion": r.get("conclusion"), "event": r.get("event")}
            for r in rows]


def dispatch(repo: str) -> bool:
    try:
        proc = subprocess.run(
            ["gh", "workflow", "run", WORKFLOW_FILE, "--ref", "main", "--repo", repo],
            capture_output=True, timeout=PROBE_TIMEOUT_S)
    except Exception as exc:
        print(f"::error title=backstop::dispatch raised {exc.__class__.__name__}",
              flush=True)
        return False
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[:300]
        print(f"::error title=backstop::dispatch failed (exit {proc.returncode}): "
              f"{detail}", flush=True)
        return False
    return True


def _selftest() -> int:
    """Fixture dates are constants — a guard whose fixtures age is a scheduled red."""
    ok = True
    now = datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc)   # 01:00Z backstop slot

    def _c(label: str, got: bool, want: bool) -> None:
        nonlocal ok
        if got is not want:
            print(f"::error title=selftest::{label}: dispatch={got}, want {want}",
                  flush=True)
            ok = False

    live = {"created_at": "2026-08-11T22:30:00Z", "status": "in_progress",
            "conclusion": None, "event": "schedule"}
    good = {"created_at": "2026-08-11T22:30:00Z", "status": "completed",
            "conclusion": "success", "event": "schedule"}
    dead = {"created_at": "2026-08-11T22:30:00Z", "status": "completed",
            "conclusion": "cancelled", "event": "schedule"}
    old = {"created_at": "2026-08-11T00:00:55Z", "status": "completed",
           "conclusion": "success", "event": "schedule"}
    fired = {"created_at": "2026-08-11T23:00:00Z", "status": "completed",
             "conclusion": "failure", "event": "workflow_dispatch"}

    _c("strand -> dispatch", decide([old], now)["dispatch"], True)
    _c("all-cancelled -> dispatch", decide([dead], now)["dispatch"], True)
    _c("live -> skip", decide([live], now)["dispatch"], False)
    _c("live beside dead -> skip", decide([dead, live], now)["dispatch"], False)
    _c("landed -> skip", decide([good], now)["dispatch"], False)
    _c("blind -> skip", decide(None, now)["dispatch"], False)
    _c("capped -> skip", decide([fired, fired], now)["dispatch"], False)
    _c("one prior dispatch -> still allowed", decide([fired], now)["dispatch"], True)
    # A weekend slot resolves to Friday's bake, which landed.
    sat = datetime(2026, 8, 15, 1, 0, tzinfo=timezone.utc)
    _c("weekend -> skip", decide(
        [{"created_at": "2026-08-14T22:30:00Z", "status": "completed",
          "conclusion": "success", "event": "schedule"}], sat)["dispatch"], False)

    print("nightly-backstop selftest: " + ("PASS" if ok else "FAIL"), flush=True)
    return 0 if ok else 1


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="decide and print, never fire")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--runs-json", type=Path, help="offline: read runs from a file")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.runs_json:
        try:
            runs = json.loads(args.runs_json.read_text())
        except (OSError, ValueError):
            runs = None
        if not isinstance(runs, list):
            runs = None
    else:
        runs = fetch_runs(args.repo)

    verdict = decide(runs, datetime.now(timezone.utc))
    print(f"nightly backstop | session={verdict['session']} "
          f"dispatch={verdict['dispatch']} :: {verdict['reason']}", flush=True)

    if not verdict["dispatch"]:
        return 0
    if args.dry_run:
        print("::notice title=backstop::DRY RUN — would dispatch daily.yml",
              flush=True)
        return 0
    print(f"::warning title=backstop::re-firing {WORKFLOW_FILE} for session "
          f"{verdict['session']}: {verdict['reason']}", flush=True)
    return 0 if dispatch(args.repo) else 1


if __name__ == "__main__":
    raise SystemExit(main())
