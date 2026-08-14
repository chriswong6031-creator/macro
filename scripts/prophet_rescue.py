#!/usr/bin/env python3
"""Prophet US availability RESCUE lane — bounded self-heal, alerting, edge coverage.

DIVISION OF LABOUR (read this before adding anything here).

  scripts/check_nightly_liveness.py  DETECTS.  It is a red-check dead-man switch over
      daily.yml: run created (A), run concluded (B), source_asof advanced (C), with
      blind -> INDETERMINATE discipline.  It has NO side effects: its product is a
      failing check and a push notification.
  scripts/prophet_rescue.py (this)   RESPONDS.  It re-arms the nightly within bounds,
      opens/updates one public issue per stranded session with a receipt per wake,
      pushes to the ops channel, and additionally covers two failure shapes the
      detector does not model: a SERVE SPLIT (main fresh, the public R2 mirror or the
      VPS pull loop stale) and the ZERO-ORIGINATION WEDGE (source_asof fresh, plans
      for the expected session absent while intake says candidates were eligible).

The overlap in staleness arithmetic between the two is DELIBERATE.  A responder that
imports its detector shares its fate; on 2026-08-11 the thing that broke was a single
file crossing a size cap, and two organs wired into one module would have gone dark
together.  Once #5487 is on main a follow-up may import the shared primitives
(``check_nightly_liveness.expected_fire_after`` / ``_parse_dt`` / ``_parse_date`` /
``fetch_runs``) if and only if the import stays optional with a local fallback.

WHAT BROKE (2026-08-11 -> 08-13, receipts in research/PROPHET_US_AVAILABILITY_HARDENING_2026-08-14.md).
  * 08-11: #5362 pushed daily.yml past GitHub's silent ~512,000-byte workflow
    processing cap 57 minutes before the 22:30Z cron.  The cron never fired.  Four
    manual dispatches queued jobless forever.  Zero plans originated that night.
  * 08-12 daytime: a live fleet session force-cancelled six recovery dispatches
    (receipt: POST /actions/runs/31583415065/force-cancel).
  * Nothing alarmed for two full sessions.  ``index.json.asof`` is ``date.today()``
    at bake time, so it re-stamps itself green over frozen inputs; healthcheck.py is
    a 96-hour instrument running ON the host it watches; check_dead_cron only
    inspects run records that EXIST, and a no-fire night creates none.  A cancelled
    bake and a bake that never fired leave the same trace: nothing.

ARCHITECTURE.  A thin fetch layer snapshots four independent sources into a
``WatchdogState``; a PURE ``decide(state) -> list[Action]`` turns that snapshot into
actions; a thin action layer executes them.  ``decide`` reads no clock and opens no
socket — ``state.now`` is injected — so every behavioural gate below is pinned by a
unit test in tests/test_prophet_rescue.py rather than by prose.

SAFETY INVARIANTS (masterplan §0.4; each one mutation-pinned by a named test).
  a. NEVER dispatch while a daily.yml run is queued / in_progress / waiting.
  b. NEVER exceed the auto-dispatch budget: 2 workflow_dispatch daily.yml runs since
     21:00Z today, counted across ALL actors (a human recovering by hand consumes it).
  c. NEVER cancel anything.  There is no cancel code path in this file and
     ``test_no_cancel_code_path_exists`` fails the build if one appears.  A kill is
     invisible to every staleness instrument we own; killing a wedged production run
     is an operator call.
  d. A GitHub read failure means NO DISPATCH.  Blind fails toward alerting, never
     toward blind re-arming.

REST BUDGET.  One shared 5,000/hr account bucket for the whole fleet.  A healthy wake
spends exactly THREE GitHub reads (index contents, run list, dispatch-budget probe)
plus two non-GitHub GETs (R2, VPS).  No pagination, ever.  Write calls (issue upsert,
dispatch) are spent only on an alarm.

EXIT CODE.  0 when nothing was done and nothing is owed (HEALTHY / WAIT).  Nonzero
when this lane ALERTED or DISPATCHED, so a red run is itself the signal.

Run:  python3 scripts/prophet_rescue.py [--lane actions|launchd] [--dry-run] [--now ISO]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL, like every other guard script here: this runs as a bare
# ``python3 scripts/prophet_rescue.py`` on a GitHub-hosted runner whose sys.path[0]
# is ``<repo>/scripts``, not the repo root, so ``import lib.nyse_calendar`` would
# otherwise resolve against whatever else is on the path.
sys.path.insert(0, str(REPO_ROOT))

from lib.nyse_calendar import expected_last_session, sessions_behind  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# constants
# ─────────────────────────────────────────────────────────────────────────────

#: The lane this rescues.  daily.yml is Build B — the sole authoritative,
#: ledger-advancing nightly.  closing-bell.yml (Build A) ran green on both outage
#: nights while the board it re-rendered still read price_through=2026-08-10, so it
#: is not a substitute and must never be dispatched as one.
WORKFLOW_FILE = "daily.yml"

#: ``GITHUB_REPOSITORY`` is always set inside Actions; the literal is the local /
#: launchd fallback.  A wrong slug 404s, which lands in API_DARK (alert, no
#: dispatch) rather than in a false green.
DEFAULT_REPO = (
    os.environ.get("GITHUB_REPOSITORY") or "mastermindx-market-intelligence/macro"
)

#: The public R2 data plane — ``config.yml: r2_data_plane.public_base``, hardcoded
#: because this module is stdlib-only by contract (importing lib.config would drag
#: in PyYAML and the whole engine tree, defeating the independence this lane exists
#: for).  Mirrors the base charting-app ``lib/flowSource.ts`` and
#: templates/data_base.js read from, i.e. the bytes a logged-in browser actually
#: paints Prophet from.  scripts/build_prophet_marks.py:91 reads the same URL.
R2_INDEX_URL = (
    "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/prophet/index.json"
)

#: The VPS's own read-only health view (app/main.py:559).  ``checks.site.commit_time``
#: is ``git log -1 --format=%cI`` in the served checkout, i.e. the watermark of the
#: 3-minute main pull loop.
VPS_STATUS_URL = "https://www.mastermind-x.com/api/status"

#: Cloudflare's WAF 403s python-default User-Agents on the public r2.dev host
#: (scripts/audit_r2.py:53 learned this the hard way), so every request here is
#: named.
USER_AGENT = "macro-prophet-rescue/1.0"

HTTP_TIMEOUT_S = 15

#: Safe-earliest boundary for "the bake for session D should exist".  The DST cron
#: pair is 22:30Z (EDT) / 23:30Z (EST) and daily.yml's et_gate keeps exactly one, so
#: any run created at or after D 22:00Z is the D bake.  Deliberately 30 min early:
#: a floor for existence, never a punctuality check.
FIRE_BOUNDARY_UTC = time(22, 0)

#: The deadline ladder, expressed as offsets from the fire boundary so it is
#: DST-stable and needs no second calendar.  For a session D whose boundary is
#: D 22:00Z these land on D+1 01:40Z / 09:40Z / 13:40Z — the wake times of the
#: workflow's own :40 cron.
#:  * STRAND_AFTER   the cron legitimately fires 22:30Z +27..90 min, so "no run
#:                   exists" is not a fact until well past midnight.
#:  * STALE_AFTER    a healthy bake's collect job runs ~3h; 11h40m past the fire
#:                   boundary a night that has not advanced the store is over.
#:  * DISPATCH_FLOOR past this, a fresh bake would land mid-session on mixed-vintage
#:                   inputs and the vintage gate would refuse origination anyway
#:                   (the 2026-08-13 13-hour retry: publish green, 0 plans).  Alarm
#:                   only; recovery from here is an operator call.
STRAND_AFTER = timedelta(hours=3, minutes=40)
STALE_AFTER = timedelta(hours=11, minutes=40)
DISPATCH_FLOOR = timedelta(hours=15, minutes=40)

#: Auto-dispatch budget, counted over ALL actors since 21:00Z today.  Two, because
#: one re-arm covers a dropped cron and a second covers a re-arm that itself died;
#: a third means the failure is not a scheduling failure and a robot must stop
#: spending 3-hour bakes on it.
AUTO_DISPATCH_BUDGET = 2
BUDGET_WINDOW_START_UTC = time(21, 0)

#: The VPS pull loop runs every 3 minutes.  30 minutes is ten missed pulls — a
#: dead loop, not a quiet one.
VPS_COMMIT_MAX_AGE_MIN = 30

#: Host-lane only (masterplan §0.10).  A disk-full runner takes the whole nightly
#: down and reports it as unrelated job failures — that is exactly what
#: actions-runner-2 did at 14:29Z on 2026-08-13 ("No space left on device").
DISK_HEADROOM_MIN_GB = 80.0

ISSUE_LABEL = "prophet-outage"
ISSUE_LABEL_COLOR = "b60205"
ISSUE_TITLE_PREFIX = "Prophet US staleness"

#: Newest daily.yml runs to read.  20 is ~3 days of a lane that runs 1-6 times a
#: day; the dispatch-budget question is answered by its own server-filtered probe
#: rather than by counting inside this page, so truncation here cannot inflate the
#: budget.  NEVER paginate: ~130 check-runs per page is how the shared pool empties.
RUNS_PER_PAGE = 20

# Verdicts.  The vocabulary is closed — a new failure shape gets a new name here and
# a fixture in the test matrix, never an unlabelled branch.
HEALTHY = "HEALTHY"
WAIT = "WAIT"
STRAND = "STRAND"
STALE = "STALE"
NO_COHORT = "NO_COHORT"
SERVE_SPLIT_R2 = "SERVE_SPLIT_R2"
SERVE_SPLIT_VPS = "SERVE_SPLIT_VPS"
API_DARK = "API_DARK"
DISK_LOW = "DISK_LOW"          # launchd lane only

# Action kinds.  ``notice`` is quiet (exit 0); ``alert`` and ``dispatch`` are not.
NOTICE = "notice"
ALERT = "alert"
DISPATCH = "dispatch"


# ─────────────────────────────────────────────────────────────────────────────
# state + actions
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Action:
    """One thing the responder will do (or one thing it deliberately will not).

    ``blocked_by`` names the §0.4 invariant that suppressed a dispatch, so the issue
    receipt explains the restraint instead of going silent about it.
    """

    kind: str
    verdict: str
    message: str
    blocked_by: str | None = None

    @property
    def loud(self) -> bool:
        return self.kind in (ALERT, DISPATCH)


@dataclass
class WatchdogState:
    """An already-fetched snapshot.  ``decide`` sees nothing else — no clock, no
    socket — which is what makes the gates below testable rather than aspirational.

    ``None`` on any source means BLINDNESS (the fetch failed), which is a distinct
    input from a source that answered with bad news.  The two must never collapse.
    """

    now: datetime
    main_index: dict | None = None
    main_error: str | None = None
    r2_index: dict | None = None
    r2_error: str | None = None
    vps_status: dict | None = None
    vps_error: str | None = None
    runs: list[dict] | None = None
    runs_error: str | None = None
    dispatch_runs_today: int | None = None
    dispatch_probe_error: str | None = None
    lane: str = "actions"
    disk_free_gb: float | None = None


# ─────────────────────────────────────────────────────────────────────────────
# small pure helpers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_dt(value: object) -> datetime | None:
    """A GitHub ISO-8601 stamp, or None.  Unparseable is blindness, not a breach."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def expected_fire_after(now: datetime) -> tuple[date, datetime]:
    """The session whose bake is owed, and when its fire window opened.

    Anchored on ``lib.nyse_calendar.expected_last_session`` so weekends and market
    holidays cannot manufacture a breach: on a Saturday this resolves to Friday and
    asks for Friday's 22:00Z bake, which already happened.  On the Tuesday after a
    Monday holiday it resolves to Friday for the same reason.  There is no weekday
    filter anywhere in this module — the calendar IS the filter.
    """
    session = expected_last_session(now)
    return session, datetime.combine(session, FIRE_BOUNDARY_UTC, tzinfo=timezone.utc)


def cohort_size(index: dict | None, session: date) -> int | None:
    """How many plans in ``index`` were recorded for ``session``.

    Per-plan ``recorded_at`` is the honest cohort stamp.  Top-level ``asof`` /
    ``recorded_at`` are the publication clock — ``date.today()`` at bake time — and
    scripts/build_prophet.py:2100 says so in a comment: "a successful rerun can
    refresh this publication stamp while its input freezes".  Reading them here is
    how every previous sensor scored a frozen board green.
    """
    if not isinstance(index, dict):
        return None
    plans = index.get("plans")
    if not isinstance(plans, list):
        return None
    wanted = session.isoformat()
    return sum(
        1 for p in plans
        if isinstance(p, dict) and str(p.get("recorded_at") or "")[:10] == wanted
    )


def intake_eligible(index: dict | None) -> int | None:
    """``intake.eligible_after_skips`` — candidates that survived the skip filters.

    >0 with an empty cohort is the mixed-vintage wedge signature: the pipeline had
    work and refused it.  None means the field is absent, which is not evidence of
    zero.
    """
    if not isinstance(index, dict):
        return None
    intake = index.get("intake")
    if not isinstance(intake, dict):
        return None
    value = intake.get("eligible_after_skips")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ─────────────────────────────────────────────────────────────────────────────
# the pure decision core
# ─────────────────────────────────────────────────────────────────────────────
def _dispatch_blockers(state: WatchdogState, in_flight: dict | None,
                       dispatch_deadline: datetime) -> list[tuple[str, str]]:
    """Every §0.4 reason a re-arm must not happen, as (code, human sentence) pairs.

    ALL FOUR INVARIANTS LIVE HERE AND NOWHERE ELSE.  That is deliberate: a guard
    duplicated at the call site would let a mutation of one copy pass the test suite
    because the other copy still refused.  Callers compute *whether a dispatch is
    wanted* without consulting these, then ask this function whether it may happen —
    so flipping any single check below turns exactly one test red.
    """
    blockers: list[tuple[str, str]] = []

    # (d) blind -> no dispatch.  Both halves: an unreadable run list means we cannot
    # know whether a bake is alive, and an unreadable budget probe means we cannot
    # know how many re-arms already exist.  Either way, re-arming would be a guess.
    if state.runs is None or state.dispatch_runs_today is None:
        blockers.append((
            "api_dark",
            "the GitHub API could not be read this wake, so a dispatch would be "
            "blind — alerting instead (§0.4d)",
        ))

    # (a) a live run owns the night.  The 2026-08-12 kill spree is the counterexample
    # this exists for: piling dispatches onto a lane that is already working is how a
    # 3-hour bake gets restarted from zero.
    if in_flight is not None:
        blockers.append((
            "run_in_flight",
            f"{WORKFLOW_FILE} run {in_flight.get('id')} is "
            f"{in_flight.get('status')} — a bake is alive, so nothing is owed (§0.4a)",
        ))

    # (b) budget.  Counted across all actors: an operator recovering by hand spends
    # the same allowance, because the resource being protected is the runner pool and
    # the ledger, not this lane's pride.
    spent = state.dispatch_runs_today
    if spent is not None and spent >= AUTO_DISPATCH_BUDGET:
        blockers.append((
            "budget_spent",
            f"{spent} workflow_dispatch {WORKFLOW_FILE} runs already exist since "
            f"{BUDGET_WINDOW_START_UTC.isoformat(timespec='minutes')}Z "
            f"(budget {AUTO_DISPATCH_BUDGET}, any actor) — alert only (§0.4b)",
        ))

    # Past the floor a re-bake cannot help: it would run against mixed-vintage
    # intraday data and the vintage gate would refuse origination, which is exactly
    # what the 13-hour 2026-08-13 retry produced (publish green, zero plans).
    if state.now >= dispatch_deadline:
        blockers.append((
            "past_floor",
            f"past the {dispatch_deadline.isoformat()} dispatch floor — a bake from "
            "here lands mid-session on mixed-vintage inputs and originates nothing; "
            "recovery is an operator call",
        ))

    return blockers


def decide(state: WatchdogState) -> list[Action]:
    """Pure verdict + action plan over an already-fetched snapshot.

    No network, no clock, no filesystem.  ``state.now`` is the only present moment
    this function knows about.
    """
    now = state.now
    session, boundary = expected_fire_after(now)
    strand_deadline = boundary + STRAND_AFTER
    stale_deadline = boundary + STALE_AFTER
    dispatch_deadline = boundary + DISPATCH_FLOOR
    actions: list[Action] = []

    # ── run facts ───────────────────────────────────────────────────────────
    in_flight: dict | None = None
    recent: list[dict] = []
    any_success = False
    dead_detail: str | None = None
    if state.runs is not None:
        recent = [
            r for r in state.runs
            if (created := _parse_dt(r.get("created_at"))) is not None
            and created >= boundary
        ]
        for row in recent:
            if row.get("status") != "completed":
                in_flight = in_flight or row
            if row.get("conclusion") == "success":
                any_success = True
        if recent and in_flight is None and not any_success:
            dead_detail = ", ".join(
                f"{r.get('status')}/{r.get('conclusion') or '-'}" for r in recent
            )

    # ── data facts (source_asof + cohort, NEVER top-level asof) ─────────────
    src = _parse_date(state.main_index.get("source_asof")) if state.main_index else None
    cohort = cohort_size(state.main_index, session)
    eligible = intake_eligible(state.main_index)
    data_current = src is not None and src >= session
    behind = sessions_behind(src, now) if src is not None else None

    # ── API_DARK ────────────────────────────────────────────────────────────
    api_dark = state.runs is None or state.dispatch_runs_today is None
    if api_dark:
        detail = state.runs_error or state.dispatch_probe_error or "unknown error"
        actions.append(Action(
            ALERT, API_DARK,
            f"GitHub API unreadable for {WORKFLOW_FILE} ({detail}). This lane is "
            "blind, not green: it can neither confirm a bake nor safely re-arm one. "
            "Check the shared REST pool (`gh api rate_limit`) and the token scope.",
        ))

    # ── does the night owe us a re-arm? ─────────────────────────────────────
    # Computed WITHOUT consulting the safety gates, so each gate stays independently
    # mutation-testable (see _dispatch_blockers).
    wants: str | None = None
    why = ""
    if state.runs is not None and not recent and now >= strand_deadline:
        wants = STRAND
        why = (
            f"no {WORKFLOW_FILE} run exists since {boundary.isoformat()} for session "
            f"{session.isoformat()}. A stranded workflow file (the #5362 512KB-cap "
            "class), a disabled workflow or a dropped schedule all look like this — "
            "check the file size against tests/test_workflow_file_size.py first."
        )
    elif not data_current and now >= stale_deadline:
        wants = STALE
        seen = src.isoformat() if src else (state.main_error or "unreadable")
        why = (
            f"Prophet source_asof reads {seen} but session {session.isoformat()} is "
            f"owed ({behind if behind is not None else '?'} completed sessions "
            f"behind){f'; runs concluded [{dead_detail}]' if dead_detail else ''}."
        )

    if wants is not None:
        blockers = _dispatch_blockers(state, in_flight, dispatch_deadline)
        if not blockers:
            actions.append(Action(
                DISPATCH, wants,
                f"{why} Re-arming {WORKFLOW_FILE} on main (auto-dispatch "
                f"{(state.dispatch_runs_today or 0) + 1}/{AUTO_DISPATCH_BUDGET} "
                "since 21:00Z).",
            ))
        elif any(code == "run_in_flight" for code, _ in blockers):
            # The one restraint that is good news rather than bad: the bake is
            # working. Quiet, exit 0 — a watchdog that pages while the subject is
            # healthy trains its reader to ignore it. DOMINANT over every other
            # blocker: a live run answers the question no matter what else is true.
            detail = next(text for code, text in blockers if code == "run_in_flight")
            actions.append(Action(
                NOTICE, WAIT, f"{why} No action: {detail}.",
                blocked_by="run_in_flight",
            ))
        else:
            codes = ",".join(c for c, _ in blockers)
            actions.append(Action(
                ALERT, wants,
                f"{why} NOT re-arming — " + "; ".join(b for _, b in blockers) + ".",
                blocked_by=codes,
            ))
    elif state.main_index is None and not api_dark:
        # No deadline breached and GitHub is otherwise answering, but main's index
        # could not be read. Say so: an unreadable artifact is not a fresh one. Gated
        # on `not api_dark` so a total GitHub outage pages once, not twice.
        actions.append(Action(
            ALERT, API_DARK,
            f"main site/prophet/index.json unreadable ({state.main_error}) — this "
            "lane cannot see the artifact it exists to watch.",
        ))

    # ── the zero-origination wedge (alert-only, never a dispatch) ───────────
    # source_asof advanced, so the price store is fine and a re-bake would change
    # nothing: the refusal is in the selection code or in the vintage gate. This is
    # 2026-08-13's shape — publish green, asof advanced, `source_mixed_vintage: true`,
    # `gate_go: false`, zero plans originated.
    if data_current and cohort == 0 and (eligible or 0) > 0:
        actions.append(Action(
            ALERT, NO_COHORT,
            f"source_asof is current ({src.isoformat() if src else '?'}) but ZERO "
            f"plans carry recorded_at={session.isoformat()} while intake reports "
            f"eligible_after_skips={eligible}. The store advanced and origination "
            "still produced nothing — a selection/vintage-gate wedge, not a missing "
            "bake. A re-dispatch cannot fix code, so this alerts only. Read "
            "`source_mixed_vintage` and `gate_go` in the index.",
        ))

    # ── serve split: main is the truth, the edges are what users read ───────
    if state.main_index is not None and src is not None:
        r2_src = _parse_date(state.r2_index.get("source_asof")) if state.r2_index else None
        if r2_src is not None and r2_src < src:
            actions.append(Action(
                ALERT, SERVE_SPLIT_R2,
                f"SERVE SPLIT: main source_asof {src.isoformat()} but the public R2 "
                f"mirror reads {r2_src.isoformat()} ({R2_INDEX_URL}). The browser "
                "paints from R2, so users are on the older board. Check the publish "
                "leg of the last render and the R2 sync.",
            ))

    vps_commit = None
    if isinstance(state.vps_status, dict):
        checks = state.vps_status.get("checks")
        if isinstance(checks, dict) and isinstance(checks.get("site"), dict):
            vps_commit = _parse_dt(checks["site"].get("commit_time"))
    if vps_commit is not None:
        age_min = (now - vps_commit).total_seconds() / 60.0
        if age_min > VPS_COMMIT_MAX_AGE_MIN:
            actions.append(Action(
                ALERT, SERVE_SPLIT_VPS,
                f"SERVE SPLIT: the VPS site pull is {age_min:.0f} minutes behind "
                f"main (commit_time {vps_commit.isoformat()}, loop runs every 3 min, "
                f"budget {VPS_COMMIT_MAX_AGE_MIN} min). Everything merged since then "
                "is invisible to logged-in users.",
            ))

    # ── host lane only ──────────────────────────────────────────────────────
    if state.lane == "launchd" and state.disk_free_gb is not None \
            and state.disk_free_gb < DISK_HEADROOM_MIN_GB:
        actions.append(Action(
            ALERT, DISK_LOW,
            f"runner volume has {state.disk_free_gb:.0f} GB free (floor "
            f"{DISK_HEADROOM_MIN_GB:.0f} GB). A disk-full runner reports as "
            "unrelated job failures — actions-runner-2 hit 'No space left on "
            "device' at 14:29Z on 2026-08-13 and took two jobs of the recovery bake "
            "with it.",
        ))

    if not actions:
        # Mid-bake is WAIT, not HEALTHY. The store legitimately still reads the
        # previous session while collect is running, and calling that "healthy"
        # would make the healthy label mean two different things.
        pending = in_flight is not None and not data_current
        actions.append(Action(
            NOTICE, WAIT if pending else HEALTHY,
            f"session {session.isoformat()}: source_asof "
            f"{src.isoformat() if src else '?'}, {cohort if cohort is not None else '?'} "
            f"plans recorded for it, {len(recent)} {WORKFLOW_FILE} run(s) since "
            f"{boundary.isoformat()}"
            + (f"; run {in_flight.get('id')} is {in_flight.get('status')}."
               if pending else "."),
        ))
    return actions


def exit_code(actions: list[Action]) -> int:
    """0 when the lane did nothing and nothing is owed; 1 when it alerted or acted."""
    return 1 if any(a.loud for a in actions) else 0


# ─────────────────────────────────────────────────────────────────────────────
# fetch layer — thin, total, and never raises into decide()
# ─────────────────────────────────────────────────────────────────────────────
def _get(url: str, headers: dict[str, str] | None = None,
         timeout: int = HTTP_TIMEOUT_S) -> tuple[bytes | None, str | None]:
    """GET -> (body, error).  Every failure mode is a string, never an exception."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read(), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return None, f"{exc.__class__.__name__}: {exc}"


def _get_json(url: str, headers: dict[str, str] | None = None) -> tuple[Any, str | None]:
    body, err = _get(url, headers)
    if err is not None:
        return None, err
    try:
        return json.loads(body), None
    except ValueError as exc:
        return None, f"unparseable JSON: {exc}"


def _api_headers(token: str | None) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    }


def fetch_main_index(repo: str, token: str | None) -> tuple[dict | None, str | None]:
    """main's site/prophet/index.json, read through the contents API in raw mode.

    Deliberately NOT a checkout read.  The workflow sparse-checks out only what it
    imports, and — more importantly — a checkout answers for the SHA the run started
    at, while this lane needs main's head right now.
    """
    url = (f"https://api.github.com/repos/{repo}/contents/site/prophet/index.json"
           "?ref=main")
    headers = _api_headers(token)
    headers["Accept"] = "application/vnd.github.raw"
    payload, err = _get_json(url, headers)
    if err is not None:
        return None, err
    return (payload, None) if isinstance(payload, dict) else (None, "not a JSON object")


def fetch_r2_index() -> tuple[dict | None, str | None]:
    payload, err = _get_json(R2_INDEX_URL)
    if err is not None:
        return None, err
    return (payload, None) if isinstance(payload, dict) else (None, "not a JSON object")


def fetch_vps_status() -> tuple[dict | None, str | None]:
    payload, err = _get_json(VPS_STATUS_URL)
    if err is not None:
        return None, err
    return (payload, None) if isinstance(payload, dict) else (None, "not a JSON object")


def fetch_runs(repo: str, token: str | None) -> tuple[list[dict] | None, str | None]:
    """ONE page of the newest daily.yml runs.  Never paginated (shared REST pool)."""
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}"
           f"/runs?per_page={RUNS_PER_PAGE}")
    payload, err = _get_json(url, _api_headers(token))
    if err is not None:
        return None, err
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        return None, "no workflow_runs array"
    return [
        {
            "id": r.get("id"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "created_at": r.get("created_at"),
            "event": r.get("event"),
            "html_url": r.get("html_url"),
        }
        for r in runs if isinstance(r, dict)
    ], None


def fetch_dispatch_budget(repo: str, token: str | None,
                          now: datetime) -> tuple[int | None, str | None]:
    """How many workflow_dispatch daily.yml runs exist since 21:00Z today.

    Server-side filtered on purpose: counting inside the ``fetch_runs`` page would
    silently under-report the moment that page truncates, and an under-reported
    budget is the one error direction that spends real runner hours.
    """
    since = datetime.combine(now.date(), BUDGET_WINDOW_START_UTC, tzinfo=timezone.utc)
    if now < since:                      # a 23:40Z wake is "today"; a 00:40Z wake is not
        since -= timedelta(days=1)
    created = urllib.parse.quote(f">={since.strftime('%Y-%m-%dT%H:%M:%SZ')}", safe="")
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}"
           f"/runs?event=workflow_dispatch&per_page={RUNS_PER_PAGE}&created={created}")
    payload, err = _get_json(url, _api_headers(token))
    if err is not None:
        return None, err
    if not isinstance(payload, dict) or not isinstance(payload.get("total_count"), int):
        return None, "no total_count"
    return payload["total_count"], None


def _disk_free_gb(path: Path) -> float | None:
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return None


def collect_state(repo: str, token: str | None, now: datetime, *,
                  lane: str = "actions") -> WatchdogState:
    """Three GitHub reads + two public GETs.  Nothing here can raise."""
    main_index, main_error = fetch_main_index(repo, token)
    r2_index, r2_error = fetch_r2_index()
    vps_status, vps_error = fetch_vps_status()
    runs, runs_error = fetch_runs(repo, token)
    budget, budget_error = fetch_dispatch_budget(repo, token, now)
    return WatchdogState(
        now=now,
        main_index=main_index, main_error=main_error,
        r2_index=r2_index, r2_error=r2_error,
        vps_status=vps_status, vps_error=vps_error,
        runs=runs, runs_error=runs_error,
        dispatch_runs_today=budget, dispatch_probe_error=budget_error,
        lane=lane,
        disk_free_gb=_disk_free_gb(REPO_ROOT) if lane == "launchd" else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# action layer
# ─────────────────────────────────────────────────────────────────────────────
def _post(url: str, body: dict | None, headers: dict[str, str],
          timeout: int = HTTP_TIMEOUT_S) -> tuple[int | None, bytes, str | None]:
    data = json.dumps(body).encode() if body is not None else b"{}"
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read(), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, b"", f"{exc.__class__.__name__}: {exc}"


def dispatch_nightly(repo: str, token: str | None) -> tuple[bool, str]:
    """POST workflows/daily.yml/dispatches {"ref": "main"} — the ONLY write to the
    pipeline this module is capable of.  It starts work; it can never stop any."""
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}"
           f"/dispatches")
    status, _, err = _post(url, {"ref": "main"}, _api_headers(token))
    if err is not None:
        return False, f"dispatch failed ({err})"
    return True, f"dispatched {WORKFLOW_FILE} on main (HTTP {status})"


def ensure_label(repo: str, token: str | None) -> None:
    """Create the tracking label.  422 = it already exists, which is the happy path."""
    _post(f"https://api.github.com/repos/{repo}/labels",
          {"name": ISSUE_LABEL, "color": ISSUE_LABEL_COLOR,
           "description": "Prophet US nightly staleness / rescue receipts"},
          _api_headers(token))


def issue_title(session: date) -> str:
    return f"{ISSUE_TITLE_PREFIX} — {session.isoformat()}"


def find_open_issue(repo: str, token: str | None,
                    session: date) -> tuple[int | None, str | None]:
    """The open ``prophet-outage`` issue for this session, if one exists.

    One issue per expected-session date: a wake appends a receipt to it rather than
    opening a new one, so a three-day outage reads as one thread with a timeline.
    """
    url = (f"https://api.github.com/repos/{repo}/issues"
           f"?labels={urllib.parse.quote(ISSUE_LABEL)}&state=open&per_page=50")
    payload, err = _get_json(url, _api_headers(token))
    if err is not None:
        return None, err
    if not isinstance(payload, list):
        return None, "issue list is not an array"
    wanted = issue_title(session)
    for row in payload:
        if isinstance(row, dict) and row.get("title") == wanted:
            return row.get("number"), None
    return None, None


def upsert_issue(repo: str, token: str | None, session: date, body: str) -> str:
    """Open the session's issue or comment a receipt onto the existing one."""
    number, err = find_open_issue(repo, token, session)
    if err is not None:
        return f"issue lookup failed ({err}) — receipt not filed"
    if number is None:
        ensure_label(repo, token)
        status, payload, post_err = _post(
            f"https://api.github.com/repos/{repo}/issues",
            {"title": issue_title(session), "body": body, "labels": [ISSUE_LABEL]},
            _api_headers(token),
        )
        if post_err is not None:
            return f"issue create failed ({post_err})"
        try:
            number = json.loads(payload).get("number")
        except ValueError:
            number = None
        return f"opened issue #{number} (HTTP {status})"
    status, _, post_err = _post(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        {"body": body}, _api_headers(token),
    )
    if post_err is not None:
        return f"issue comment failed ({post_err})"
    return f"commented on issue #{number} (HTTP {status})"


def push_ops_alert(text: str) -> None:
    """Best-effort push on the transports heartbeat.yml already provisions.

    Stdlib POST rather than ``engine.alert_triage.push_ops_alert`` ON PURPOSE: this
    lane must survive a repo whose engine tree does not import (the shape that took
    the nightly out in the first place), and it must run identically from a bare
    launchd python with no venv.  Env names mirror heartbeat.yml exactly, so the
    secrets already wired for healthcheck reach here with no new provisioning.
    """
    hook = (os.environ.get("DISCORD_WEBHOOK_URL")
            or os.environ.get("DISCORD_WEBHOOK_WATCHLIST"))
    if hook:
        _post(hook, {"content": text[:1900]}, {}, timeout=10)
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        _post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
              {"chat_id": tg_chat, "text": text[:4000]}, {}, timeout=10)


def macos_notify(title: str, text: str) -> None:
    """Host-lane only.  Never raises — a missing osascript is not an incident."""
    script = (f'display notification {json.dumps(text[:200])} '
              f'with title {json.dumps(title)}')
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10,
                       check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def annotate(actions: list[Action]) -> None:
    """GitHub annotations, emitted as BARE prints at the start of the line.

    Never through logging: every builder here uses a prefixing log format, so
    ``log.error("::error …")`` emits ``ERROR ::error …`` and GitHub silently drops
    it. That shipped dead five times before tests/test_gh_annotation_line_start.py
    existed. ``flush`` is load-bearing — stdout is block-buffered when piped in CI.
    """
    for action in actions:
        head = "::error" if action.loud else "::notice"
        print(f"{head} title=prophet-rescue-{action.verdict}::{action.message}",
              flush=True)


def receipt(actions: list[Action], state: WatchdogState, session: date,
            results: list[str]) -> str:
    """The issue body / comment: one wake, everything it saw and everything it did."""
    src = state.main_index.get("source_asof") if state.main_index else None
    lines = [
        f"**Wake {state.now.isoformat(timespec='seconds')}** (`{state.lane}` lane) — "
        f"expected session `{session.isoformat()}`",
        "",
        f"- main `source_asof`: `{src}` · cohort for the session: "
        f"`{cohort_size(state.main_index, session)}` · "
        f"`intake.eligible_after_skips`: `{intake_eligible(state.main_index)}`",
        f"- `{WORKFLOW_FILE}` runs read: "
        f"`{len(state.runs) if state.runs is not None else 'UNREADABLE'}` · "
        f"workflow_dispatch runs since 21:00Z: `{state.dispatch_runs_today}`",
        "",
        "**Verdicts**",
    ]
    lines += [f"- `{a.verdict}` ({a.kind}) — {a.message}" for a in actions]
    if results:
        lines += ["", "**Actions taken**"] + [f"- {r}" for r in results]
    lines += [
        "",
        "_Filed by `scripts/prophet_rescue.py`. This lane can only START work — it "
        "has no authority to stop a run, and stopping one is an operator call._",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# entrypoint
# ─────────────────────────────────────────────────────────────────────────────
def execute(actions: list[Action], state: WatchdogState, session: date, repo: str,
            token: str | None, *, dry_run: bool) -> list[str]:
    """Run the plan.  Every step is best-effort: a failed side effect degrades the
    receipt, it never changes the verdict or the exit code."""
    results: list[str] = []
    for action in actions:
        if action.kind != DISPATCH:
            continue
        if dry_run:
            results.append(f"DRY RUN: would dispatch {WORKFLOW_FILE} on main")
            continue
        ok, detail = dispatch_nightly(repo, token)
        results.append(detail)
        if not ok:
            print(f"::error title=prophet-rescue-dispatch-failed::{detail}", flush=True)
    if not any(a.loud for a in actions) or dry_run:
        return results
    body = receipt(actions, state, session, results)
    if token:
        results.append(upsert_issue(repo, token, session, body))
    summary = "; ".join(f"{a.verdict}: {a.message}" for a in actions if a.loud)
    push_ops_alert(f"🚨 Prophet US rescue [{state.lane}] — {summary}")
    if state.lane == "launchd":
        macos_notify("Prophet US rescue", summary)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lane", choices=("actions", "launchd"), default="actions",
                        help="launchd adds host-only checks (disk headroom, "
                             "local notification)")
    parser.add_argument("--dry-run", action="store_true",
                        help="decide and report, mutate nothing")
    parser.add_argument("--now", default=None,
                        help="ISO-8601 override for the decision clock (testing)")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    args = parser.parse_args(argv)

    now = _parse_dt(args.now) or datetime.now(timezone.utc)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("::warning title=prophet-rescue-anonymous::no GH_TOKEN/GITHUB_TOKEN — "
              "reads are anonymous (60/hr) and no issue receipt can be filed",
              flush=True)

    state = collect_state(args.repo, token, now, lane=args.lane)
    session, _ = expected_fire_after(now)
    actions = decide(state)
    annotate(actions)
    for line in execute(actions, state, session, args.repo, token,
                        dry_run=args.dry_run):
        print(f"  -> {line}", flush=True)
    return exit_code(actions)


if __name__ == "__main__":
    raise SystemExit(main())
