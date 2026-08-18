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
  a. NEVER dispatch while a daily.yml run is queued / in_progress / waiting —
     UNLESS that run is provably WEDGED (2026-08-17 amendment, ``wedged_run``):
     old enough that no healthy bake explains it AND its jobs read shows zero
     jobs in progress with every live job queued beyond any plausible runner
     wait.  The 08-16/17 outage is why: collect_tail sat queued on a runs-on
     label carried by NO live runner, GitHub holds such a run 'alive' ~24h until
     its queued-job kill, and this invariant read the hostage as a live bake and
     refused to dispatch for two days while every Prophet board froze.  The
     wedge verdict is FAIL-CLOSED: an unreadable jobs list, an unparseable
     created_at, a fresh run, or any single in-progress job keeps the full
     refusal.  A wrong WEDGED call costs at worst a budgeted double-bake —
     the failure mode daily.yml's own concurrency comment declares acceptable
     ("a double-run, never a zero-run"); a wrong ALIVE call cost four days.
  b. NEVER exceed the auto-dispatch budget: 2 workflow_dispatch daily.yml runs since
     21:00Z today, counted across ALL actors (a human recovering by hand consumes it).
  c. NEVER cancel anything.  There is no cancel code path in this file and
     ``test_no_cancel_code_path_exists`` fails the build if one appears.  A kill is
     invisible to every staleness instrument we own; killing a wedged production run
     is an operator call.
  d. A GitHub read failure means NO DISPATCH.  Blind fails toward alerting, never
     toward blind re-arming.

REST BUDGET — TWO DIFFERENT POOLS, do not conflate them.  In the Actions lane the
`GITHUB_TOKEN` draws the per-repository 1,000/hr installation pool, which is this
lane's own and cannot starve a session.  The launchd lane borrows `gh auth token`,
so it spends the fleet's SHARED 5,000/hr account bucket — the one `ship_loop_guard.py`
fails closed without — which is why the host lane wakes twice a day rather than
hourly.  Either way: a healthy wake spends exactly THREE GitHub reads (index
contents, run list, dispatch-budget probe) plus two non-GitHub GETs (R2, VPS).  An
ALARM wake spends two more reads (the issue thread, for the attempt ledger and the
duplicate-alert check) plus its writes.  No pagination, ever.

EXIT CODE.  0 when nothing was done and nothing is owed (HEALTHY / WAIT).  Nonzero
when this lane ALERTED or DISPATCHED, so a red run is itself the signal.

Run:  python3 scripts/prophet_rescue.py [--lane actions|launchd] [--dry-run] [--now ISO]
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
from zoneinfo import ZoneInfo

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

#: Keep in lockstep with daily.yml's schedule / et_gate (tests/test_daily_et_gate.py).
EDT_CRON = "30 22 * * *"
EST_CRON = "30 23 * * *"

# run_started_at on a concurrency-queued skip equals created_at (31851452961:
# both 23:45:40Z) while et_gate did not start until 02:16:14Z.  Wall-clock span
# is therefore not a skip signal.  Pre-run-name receipts use the cancelled-
# sibling rule in counts_as_bake().

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

#: Wedge classification floors (§0.4a amendment, 2026-08-17).  A run must be at
#: least this old before a wedge verdict is even considered — the serial band
#: from fire to collect's first commit is ~3h, and a busy macstudio pool can
#: legitimately hold a queued job ~1h, so 6h clears every healthy shape seen in
#: the timings ledger.  And every still-live job inside it must have been queued
#: at least WEDGED_JOB_QUEUE_MIN — the 08-16/17 hostage's collect_tail was
#: queued 17h+ (label with no runner), while ordinary contention (the 13F census
#: backlog) resolved in ~1h.  Both floors are deliberately far above normal: the
#: cost of a missed wedge is one more quiet wake, the cost of a false wedge is a
#: budgeted double-bake.
WEDGED_RUN_MIN_AGE = timedelta(hours=6)
WEDGED_JOB_QUEUE_MIN = timedelta(hours=3)

#: Auto-dispatch budget, counted over ALL actors since 21:00Z today.  Two, because
#: one re-arm covers a dropped cron and a second covers a re-arm that itself died;
#: a third means the failure is not a scheduling failure and a robot must stop
#: spending 3-hour bakes on it.
AUTO_DISPATCH_BUDGET = 2
BUDGET_WINDOW_START_UTC = time(21, 0)

#: `checks.site.commit_time` is CONTEXT ONLY and must not become a verdict.  It is
#: the timestamp of main's newest commit in the served checkout, not a heartbeat of
#: the pull loop: main goes quiet for perfectly ordinary reasons (an hour with no
#: merges, a weekend), so an age threshold on it false-fires at our own wake times.
#: An adversarial pass measured ~5% false fires at these hours, which is a
#: false-positive factory — the thing that gets a watchdog muted. It is printed in
#: the receipt so a human triaging a REAL alarm can see it, and nothing else.
VPS_COMMIT_CONTEXT_ONLY = True

#: Host-lane only (masterplan §0.10).  A disk-full runner takes the whole nightly
#: down and reports it as unrelated job failures — that is exactly what
#: actions-runner-2 did at 14:29Z on 2026-08-13 ("No space left on device").
DISK_HEADROOM_MIN_GB = 80.0

ISSUE_LABEL = "prophet-outage"
ISSUE_LABEL_COLOR = "b60205"
ISSUE_TITLE_PREFIX = "Prophet US staleness"

#: Machine tokens inside the issue receipts.  The issue thread is this lane's ONLY
#: durable state — it has no database and writes nothing to the repo — so the
#: attempt ledger and the duplicate-alert check both read back from it.
#:
#: WHY THE RUN LIST IS NOT ENOUGH FOR THE BUDGET.  A dispatch POST that 404s, 403s,
#: or is silently dropped creates no run record, so `dispatch_runs_today` stays 0
#: and an unfixed budget would re-fire every wake forever.  Counting ATTEMPTS (what
#: we tried) rather than only EFFECTS (what GitHub recorded) is what makes the
#: budget a real bound.  `spent = max(runs, receipts)`.
DISPATCH_RECEIPT_TOKEN = "DISPATCH-RECEIPT"
VERDICT_TOKEN = "RESCUE-VERDICTS"

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
# There is deliberately no SERVE_SPLIT_VPS: see VPS_COMMIT_CONTEXT_ONLY above.
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
    #: Jobs of the newest non-completed run, fetched ONLY on the alarm path when
    #: pass one was blocked by ``run_in_flight`` (same two-pass economy as the
    #: issue thread) — the wedge-classification input (§0.4a amendment).
    #: None = not fetched or unreadable — fail-closed toward the full refusal.
    in_flight_jobs: list[dict] | None = None
    in_flight_jobs_error: str | None = None
    dispatch_runs_today: int | None = None
    dispatch_probe_error: str | None = None
    #: Read back from the session's issue thread on the ALARM path only (see
    #: DISPATCH_RECEIPT_TOKEN). ``dispatch_receipts_today`` is the ATTEMPT ledger
    #: that makes the budget a real bound even when a dispatch POST left no run
    #: record; ``last_receipt_verdicts`` is the newest wake's verdict set, used to
    #: suppress a duplicate comment + push for an unchanged situation.
    issue_number: int | None = None
    issue_error: str | None = None
    dispatch_receipts_today: int | None = None
    last_receipt_verdicts: tuple[str, ...] | None = None
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


@dataclass(frozen=True)
class RunFacts:
    """What the run list says, derived once and shared by decide() and receipt()."""

    recent: tuple[dict, ...] = ()
    in_flight: dict | None = None
    any_success: bool = False
    dead_detail: str | None = None
    anomalies: tuple[str, ...] = ()
    gate_skips: tuple[dict, ...] = ()

    @property
    def in_flight_id(self):
        return self.in_flight.get("id") if self.in_flight else None


def intended_schedule_cron(when: datetime) -> str:
    """Which daily.yml cron the America/New_York regime intends at ``when``.

    Mirrors daily.yml et_gate: EDT (UTC-4) → 22:30Z, anything else → 23:30Z.
    """
    instant = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    offset = instant.astimezone(ZoneInfo("America/New_York")).utcoffset()
    return EDT_CRON if offset == timedelta(hours=-4) else EST_CRON


def is_et_gate_skip(row: dict, *, now: datetime) -> bool:
    """True when a schedule run's ``run-name`` is the off-regime DST cron.

    workflow_dispatch never skips (et_gate proceeds).  An unlabelled success
    (pre-run-name ``display_title: daily``) is handled by ``counts_as_bake``.
    """
    if row.get("event") != "schedule" or row.get("conclusion") != "success":
        return False
    title = " ".join(str(row.get(k) or "") for k in ("display_title", "name"))
    if EDT_CRON not in title and EST_CRON not in title:
        return False
    when = _parse_dt(row.get("created_at")) or now
    return intended_schedule_cron(when) not in title


def counts_as_bake(row: dict, recent: list[dict], *, now: datetime) -> bool:
    """A ``success`` that actually ran the nightly, not an et_gate no-op.

    Named off-regime cron → skip.  Unlabelled schedule success sitting next to
    a cancelled schedule sibling is the 2026-08-14/15 shape (31851452961
    display_title was just ``daily``; run_started_at equalled created_at while
    the run sat pending, so duration cannot tell).  A lone unlabelled success
    still counts — that is a pre-run-name real bake.
    """
    if row.get("conclusion") != "success":
        return False
    if is_et_gate_skip(row, now=now):
        return False
    if row.get("event") == "schedule":
        title = " ".join(str(row.get(k) or "") for k in ("display_title", "name"))
        named = EDT_CRON in title or EST_CRON in title
        if not named and any(
            sib.get("event") == "schedule" and sib.get("conclusion") == "cancelled"
            for sib in recent
        ):
            return False
    return True


def run_facts(runs: list[dict] | None, boundary: datetime,
              *, now: datetime | None = None) -> RunFacts:
    """Classify the run list.

    THE IN-FLIGHT TEST IGNORES ``created_at`` ENTIRELY, and that is the safe
    direction.  §0.4a says never dispatch while ANY daily.yml run is alive, and a
    row whose timestamp will not parse is exactly the row an attacker of this logic
    would want dropped: drop it and the lane dispatches over a live bake.  A row
    with no ``status`` at all is likewise treated as alive — an unreadable row is
    not evidence of absence.  Both shapes are reported as anomalies so a human
    triaging the receipt knows the classification rested on a malformed row.

    ``recent`` (the STRAND question, "does a run for tonight exist at all") still
    needs a parseable timestamp, because a row we cannot date cannot prove a bake
    happened.  The two questions genuinely differ, and each fails toward caution.
    """
    if runs is None:
        return RunFacts()
    clock = now if now is not None else boundary
    recent: list[dict] = []
    in_flight: dict | None = None
    any_success = False
    anomalies: list[str] = []
    gate_skips: list[dict] = []
    for row in runs:
        status = row.get("status")
        created = _parse_dt(row.get("created_at"))
        if status is None:
            anomalies.append(f"run {row.get('id')} has no status — treated as alive")
        if status != "completed":
            if in_flight is None:
                in_flight = row
            if created is None:
                anomalies.append(
                    f"run {row.get('id')} is {status!r} with an unparseable "
                    f"created_at {row.get('created_at')!r} — treated as alive"
                )
        if created is not None and created >= boundary:
            recent.append(row)
    for row in recent:
        if row.get("conclusion") != "success":
            continue
        if counts_as_bake(row, recent, now=clock):
            any_success = True
        else:
            gate_skips.append(row)
    dead_detail = None
    if recent and in_flight is None and not any_success:
        dead_detail = ", ".join(
            f"{r.get('status')}/{r.get('conclusion') or '-'}" for r in recent
        )
    return RunFacts(tuple(recent), in_flight, any_success, dead_detail,
                    tuple(anomalies), tuple(gate_skips))


def wedged_run(in_flight: dict | None, jobs: list[dict] | None,
               now: datetime) -> str | None:
    """Evidence sentence when the in-flight run is provably WEDGED, else None.

    §0.4a amendment (2026-08-17).  The 08-16/17 outage: collect_tail queued on a
    runs-on label carried by NO live runner held run 31977372592 'alive' ~24h
    (GitHub only kills a queued job after 24h), its per-cron concurrency group
    pended the next night's slot behind it, and this lane's unamended §0.4a read
    the hostage as a live bake — refusing to dispatch for two days while every
    Prophet board froze.

    FAIL-CLOSED at every input: no run, no jobs read, an unparseable run or job
    timestamp, a run younger than WEDGED_RUN_MIN_AGE, ANY job in progress, or
    any live job inside the WEDGED_JOB_QUEUE_MIN floor -> None (full §0.4a
    refusal stands).  A wrong WEDGED call costs at worst a budgeted double-bake
    — daily.yml's own declared-acceptable failure mode ("a double-run, never a
    zero-run"); a wrong ALIVE call cost four days of frozen boards.
    """
    if in_flight is None or jobs is None:
        return None
    created = _parse_dt(in_flight.get("created_at"))
    if created is None:
        return None
    age = now - created
    if age < WEDGED_RUN_MIN_AGE:
        return None
    hours = age.total_seconds() / 3600
    live = [j for j in jobs if isinstance(j, dict) and j.get("status") != "completed"]
    if any(j.get("status") == "in_progress" for j in live):
        return None
    if not live:
        # Also covers an EMPTY jobs list: total_count 0 after hours alive is the
        # #5362 jobless-queued shape (created during a strand, will never start).
        return (f"alive {hours:.1f}h with zero live jobs — the #5362 "
                "jobless-queued shape, or a run stuck concluding")
    stuck: list[str] = []
    for job in live:
        queued_at = _parse_dt(job.get("started_at")) or _parse_dt(job.get("created_at"))
        if queued_at is None:
            return None
        wait = now - queued_at
        if wait < WEDGED_JOB_QUEUE_MIN:
            return None
        stuck.append(f"{job.get('name')} queued {wait.total_seconds() / 3600:.1f}h")
    return (f"alive {hours:.1f}h with zero jobs in progress and every live job "
            f"past the {WEDGED_JOB_QUEUE_MIN.total_seconds() / 3600:.0f}h queue "
            f"floor [{'; '.join(stuck)}] — the 2026-08-16/17 hostage shape "
            "(check the job's runs-on label against the live runner pool)")


def budget_window_start(now: datetime) -> datetime:
    """21:00Z of the night ``now`` belongs to — the auto-dispatch budget window.

    A 23:40Z wake is inside tonight's window; a 00:40Z wake belongs to the window
    that opened yesterday evening. Shared by the API probe and the receipt ledger so
    the two can never count over different spans.
    """
    since = datetime.combine(now.date(), BUDGET_WINDOW_START_UTC, tzinfo=timezone.utc)
    return since - timedelta(days=1) if now < since else since


def count_dispatch_receipts(texts, since: datetime) -> int:
    """How many dispatch ATTEMPTS this lane recorded on the issue since ``since``."""
    pattern = re.compile(rf"{DISPATCH_RECEIPT_TOKEN}\s+(\S+)")
    total = 0
    for text in texts:
        if not isinstance(text, str):
            continue
        for stamp in pattern.findall(text):
            when = _parse_dt(stamp)
            if when is not None and when >= since:
                total += 1
    return total


def latest_verdicts(texts) -> tuple[str, ...] | None:
    """The verdict set of the NEWEST receipt carrying one, or None if there is none.

    ``texts`` must arrive oldest-first (the GitHub issue-comment order).
    """
    pattern = re.compile(rf"{VERDICT_TOKEN}\s+([A-Z0-9_,]+)")
    found: tuple[str, ...] | None = None
    for text in texts:
        if not isinstance(text, str):
            continue
        for blob in pattern.findall(text):
            found = tuple(sorted(v for v in blob.split(",") if v))
    return found


def should_file_receipt(actions: list[Action],
                        last_verdicts: tuple[str, ...] | None) -> bool:
    """Whether this wake earns a new issue comment and an ops push.

    A dispatch ALWAYS earns one — it is an action taken, and an unreceipted action
    is how the attempt ledger loses count.  Otherwise an unchanged verdict set is
    not news: hourly wakes through a 14-hour outage would otherwise post fourteen
    identical comments and fourteen pushes, which is how a channel gets muted right
    before the night it matters.  The RED RUN still fires every wake — the heartbeat
    is the exit code, not the comment.
    """
    if any(a.kind == DISPATCH for a in actions):
        return True
    current = tuple(sorted({a.verdict for a in actions if a.loud}))
    if last_verdicts is None:
        return True
    return current != tuple(sorted(last_verdicts))


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
                       dispatch_deadline: datetime,
                       wedge: str | None = None) -> list[tuple[str, str]]:
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
    # 3-hour bake gets restarted from zero.  ``wedge`` is the §0.4a amendment
    # (2026-08-17): a PROVEN wedge (see ``wedged_run`` — fail-closed, jobs-API
    # evidence required) is not a live bake, so it does not own the night; the
    # 08-16/17 hostage held this blocker for two days while the boards froze.
    if in_flight is not None and wedge is None:
        blockers.append((
            "run_in_flight",
            f"{WORKFLOW_FILE} run {in_flight.get('id')} is "
            f"{in_flight.get('status')} — a bake is alive, so nothing is owed (§0.4a)",
        ))

    # (b) budget.  Counted across all actors — an operator recovering by hand spends
    # the same allowance, because the resource being protected is the runner pool and
    # the ledger, not this lane's pride — and counted as ATTEMPTS, not only effects.
    # `max(runs, receipts)`: a dispatch POST that 404s or is dropped creates no run
    # record, so an effects-only count would re-fire every wake forever.
    counted = [c for c in (state.dispatch_runs_today, state.dispatch_receipts_today)
               if c is not None]
    spent = max(counted) if counted else None
    if spent is not None and spent >= AUTO_DISPATCH_BUDGET:
        blockers.append((
            "budget_spent",
            f"{spent} auto-dispatch attempt(s) since "
            f"{BUDGET_WINDOW_START_UTC.isoformat(timespec='minutes')}Z "
            f"(runs recorded: {state.dispatch_runs_today}, receipts filed: "
            f"{state.dispatch_receipts_today}; budget {AUTO_DISPATCH_BUDGET}, any "
            "actor) — alert only (§0.4b)",
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
    facts = run_facts(state.runs, boundary, now=now)
    in_flight, recent, dead_detail = facts.in_flight, facts.recent, facts.dead_detail

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
    elif not data_current and (
        now >= stale_deadline
        or (
            now >= strand_deadline
            and in_flight is None
            and recent
            and state.main_index is not None
        )
    ):
        # 09:40Z is the "bake might still be running" deadline. Once every run
        # has completed and a readable store has not moved, waiting further is
        # how 2026-08-14/15 stayed quiet: cancelled EDT 31848262472 + 5s
        # EST-guard success 31851452961 concluded at 02:16Z, and the 02:40Z
        # wake printed WAIT until 09:40Z because a gate-skip success looked
        # like a bake. An unreadable index is API_DARK, not this branch.
        wants = STALE
        seen = src.isoformat() if src else (state.main_error or "unreadable")
        skip_note = ""
        if facts.gate_skips and any(
            r.get("conclusion") == "cancelled" for r in recent
        ):
            skip_note = (
                " Cancelled real slot + surviving et_gate no-op is not a bake "
                "(2026-08-14/15: 31848262472 superseded by 31851452961)."
            )
        why = (
            f"Prophet source_asof reads {seen} but session {session.isoformat()} is "
            f"owed ({behind if behind is not None else '?'} completed sessions "
            f"behind){f'; runs concluded [{dead_detail}]' if dead_detail else ''}."
            f"{skip_note}"
        )

    if wants is not None:
        wedge = wedged_run(in_flight, state.in_flight_jobs, now)
        blockers = _dispatch_blockers(state, in_flight, dispatch_deadline,
                                      wedge=wedge)
        if not blockers:
            wedge_note = ""
            if wedge is not None and in_flight is not None:
                wedge_note = (
                    f" Run {facts.in_flight_id} is classified WEDGED ({wedge}); "
                    "dispatching THROUGH it per the §0.4a amendment — it is not "
                    "stopped (never) and concludes on GitHub's own queued-job "
                    "kill."
                )
            actions.append(Action(
                DISPATCH, wants,
                f"{why} Re-arming {WORKFLOW_FILE} on main (auto-dispatch "
                f"{(state.dispatch_runs_today or 0) + 1}/{AUTO_DISPATCH_BUDGET} "
                f"since 21:00Z).{wedge_note}",
            ))
        elif any(code == "run_in_flight" for code, _ in blockers):
            # A live run is DOMINANT over every other blocker — it answers the
            # question no matter what else is true, and this lane will neither
            # dispatch alongside it nor stop it.
            #
            # BUT SILENCE HAS A DEADLINE. Waiting quietly forever is its own failure
            # mode, and we can mint the very run that mutes us: the #5362 512KB class
            # produced runs that sat `queued` with ZERO jobs, uncancellable, forever
            # — so a STRAND dispatch into a stranded workflow file creates a zombie
            # that would keep this lane quiet all night. Past the completion deadline
            # a run that is still alive is no longer "working", it is a question an
            # operator has to answer, so the same restraint becomes LOUD.
            detail = next(text for code, text in blockers if code == "run_in_flight")
            started = _parse_dt((in_flight or {}).get("created_at"))
            age = (f"{(now - started).total_seconds() / 3600:.1f}h"
                   if started is not None else "age unknown (unparseable created_at)")
            if now >= stale_deadline:
                actions.append(Action(
                    ALERT, wants,
                    f"{why} Run {facts.in_flight_id} has been "
                    f"{(in_flight or {}).get('status')} for {age} and the store has "
                    "still not advanced. NOT dispatching (a run is alive) and NOT "
                    "stopping it (never) — an operator look is owed: a bake this "
                    "long is either hung or a jobless queued zombie, and a zombie "
                    "keeps this lane quiet until someone breaks the tie.",
                    blocked_by="run_in_flight",
                ))
            else:
                actions.append(Action(
                    NOTICE, WAIT,
                    f"{why} No action: {detail} (running {age}).",
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

    # The VPS's `checks.site.commit_time` is CONTEXT, never a verdict — it stamps
    # main's newest commit in the served checkout, not the pull loop's pulse, so an
    # age threshold on it fires on any quiet hour on main. It is read and printed in
    # the receipt (see `vps_commit_time`), and it decides nothing.

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
        # HEALTHY REQUIRES data_current, FULL STOP. Before the deadlines a store that
        # has not advanced is legitimately still catching up — but that is WAIT, not
        # health. Printing HEALTHY over a stale store is precisely the sentence every
        # instrument produced for two days while the site served Aug-10 picks, and a
        # quiet-but-honest verdict costs nothing (both exit 0).
        actions.append(Action(
            NOTICE, HEALTHY if data_current else WAIT,
            f"session {session.isoformat()}: source_asof "
            f"{src.isoformat() if src else '?'}, {cohort if cohort is not None else '?'} "
            f"plans recorded for it, {len(recent)} {WORKFLOW_FILE} run(s) since "
            f"{boundary.isoformat()}"
            + (f"; run {facts.in_flight_id} is {in_flight.get('status')}, "
               "still within the deadline ladder." if in_flight is not None
               else ("." if data_current else "; the store has not advanced yet.")),
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
            "display_title": r.get("display_title"),
            "name": r.get("name"),
            "run_started_at": r.get("run_started_at"),
            "updated_at": r.get("updated_at"),
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


def vps_commit_time(state: WatchdogState) -> datetime | None:
    """``checks.site.commit_time`` from the VPS status view — CONTEXT for the
    receipt, never an input to a verdict (see VPS_COMMIT_CONTEXT_ONLY)."""
    if not isinstance(state.vps_status, dict):
        return None
    checks = state.vps_status.get("checks")
    if not isinstance(checks, dict) or not isinstance(checks.get("site"), dict):
        return None
    return _parse_dt(checks["site"].get("commit_time"))


def fetch_run_jobs(repo: str, token: str | None,
                   run_id: object) -> tuple[list[dict] | None, str | None]:
    """Jobs of ONE run — the wedge-classification read (§0.4a amendment).

    Spent only on the alarm path when pass one was blocked by ``run_in_flight``,
    so a healthy wake still costs exactly THREE GitHub reads.  per_page=100 and
    never paginated: daily.yml has ~20 jobs.
    """
    url = (f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
           f"/jobs?per_page=100")
    payload, err = _get_json(url, _api_headers(token))
    if err is not None:
        return None, err
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        return None, "no jobs array"
    return [
        {
            "name": j.get("name"),
            "status": j.get("status"),
            "conclusion": j.get("conclusion"),
            "started_at": j.get("started_at"),
            "created_at": j.get("created_at"),
        }
        for j in jobs if isinstance(j, dict)
    ], None


def fetch_issue_thread(repo: str, token: str | None, session: date, now: datetime):
    """The session's issue plus its attempt ledger and newest verdict set.

    TWO reads, spent ONLY on the alarm path — the enrichment pass in ``main`` runs
    this after a provisional ``decide`` has already said something is wrong, so a
    healthy wake never pays for it.  Returns
    ``(number, receipts_since_window, last_verdicts, error)``; any failure yields
    ``(…, None, None, error)`` so the budget falls back to the run-record count
    rather than silently reading zero attempts.
    """
    row, err = find_open_issue(repo, token, session)
    if err is not None:
        return None, None, None, err
    if row is None:
        return None, 0, None, None
    number = row.get("number")
    url = (f"https://api.github.com/repos/{repo}/issues/{number}/comments"
           f"?per_page=100")
    payload, err = _get_json(url, _api_headers(token))
    if err is not None or not isinstance(payload, list):
        return number, None, None, err or "comment list is not an array"
    texts = [row.get("body")] + [c.get("body") for c in payload
                                 if isinstance(c, dict)]
    return (number,
            count_dispatch_receipts(texts, budget_window_start(now)),
            latest_verdicts(texts),
            None)


def _disk_free_gb(path: Path) -> float | None:
    try:
        return shutil.disk_usage(path).free / (1024 ** 3)
    except OSError:
        return None


def collect_state(repo: str, token: str | None, now: datetime, *,
                  lane: str = "actions",
                  disk_path: Path | None = None) -> WatchdogState:
    """Three GitHub reads + two public GETs.  Nothing here can raise.

    ``disk_path`` is the volume the host lane measures.  It must be passed
    explicitly by the launchd wrapper: that wrapper runs the tool from a TEMPDIR
    extracted out of origin/main, so measuring this file's own parent would report
    on ``/var/folders`` instead of on the volume the runners actually fill.
    """
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
        disk_free_gb=(_disk_free_gb(disk_path or REPO_ROOT)
                      if lane == "launchd" else None),
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
    # SUCCESS IS THE STATUS CODE, not the absence of an exception. GitHub answers a
    # good dispatch with 204; a 403 (token scope) or 404 (workflow disabled, or the
    # #5362 unprocessable-file class) is a POST that "worked" at the socket level and
    # created nothing. Reporting that as a dispatch would put a phantom attempt in
    # the ledger and hide a real failure behind a green line.
    if status is None or not 200 <= status < 300:
        return False, (f"DISPATCH FAILED — HTTP {status if status is not None else '?'}"
                       f" ({err or 'no response'}). No run was created; the budget "
                       "still counts this attempt.")
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
                    session: date) -> tuple[dict | None, str | None]:
    """The open ``prophet-outage`` issue ROW for this session, if one exists.

    One issue per expected-session date: a wake appends a receipt to it rather than
    opening a new one, so a three-day outage reads as one thread with a timeline.
    The whole row is returned rather than just the number because its ``body`` is
    the FIRST receipt, and the attempt ledger has to count that one too.
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
            return row, None
    return None, None


def upsert_issue(repo: str, token: str | None, session: date, body: str,
                 number: int | None = None) -> str:
    """Open the session's issue or comment a receipt onto the existing one.

    ``number`` is passed in when the enrichment pass already resolved it, so the
    alarm path does not spend a second lookup on the same question.
    """
    if number is None:
        row, err = find_open_issue(repo, token, session)
        if err is not None:
            return f"issue lookup failed ({err}) — receipt not filed"
        number = row.get("number") if row else None
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
            results: list[str], dispatched_at: datetime | None = None) -> str:
    """The issue body / comment: one wake, everything it saw and everything it did.

    Carries two MACHINE TOKENS as well as prose, because this thread is the lane's
    only durable state: ``DISPATCH-RECEIPT <instant>`` is the attempt ledger the
    budget reads back, and ``RESCUE-VERDICTS <A,B>`` is what the next wake compares
    against to avoid posting the same alarm fourteen times in one night.
    """
    src = state.main_index.get("source_asof") if state.main_index else None
    _, boundary = expected_fire_after(state.now)
    facts = run_facts(state.runs, boundary)
    vps = vps_commit_time(state)
    lines = [
        f"**Wake {state.now.isoformat(timespec='seconds')}** (`{state.lane}` lane) — "
        f"expected session `{session.isoformat()}`",
        "",
        f"- main `source_asof`: `{src}` · cohort for the session: "
        f"`{cohort_size(state.main_index, session)}` · "
        f"`intake.eligible_after_skips`: `{intake_eligible(state.main_index)}`",
        f"- `{WORKFLOW_FILE}` runs read: "
        f"`{len(state.runs) if state.runs is not None else 'UNREADABLE'}` · since the "
        f"fire boundary: `{len(facts.recent)}` · in flight: `{facts.in_flight_id}`",
        f"- auto-dispatch spend since {budget_window_start(state.now).isoformat()}: "
        f"runs recorded `{state.dispatch_runs_today}`, receipts filed "
        f"`{state.dispatch_receipts_today}` (budget `{AUTO_DISPATCH_BUDGET}`)",
        # Context only — an old commit_time is not a verdict here (main goes quiet
        # for ordinary reasons), but a human triaging a real alarm wants to see it.
        f"- VPS `checks.site.commit_time` (context, not a verdict): "
        f"`{vps.isoformat() if vps else state.vps_error or 'unreadable'}`",
    ]
    if facts.anomalies:
        lines.append("- ⚠ run-list parse anomalies: " + "; ".join(facts.anomalies))
    lines += ["", "**Verdicts**"]
    lines += [f"- `{a.verdict}` ({a.kind}) — {a.message}" for a in actions]
    if results:
        lines += ["", "**Actions taken**"] + [f"- {r}" for r in results]
    verdict_set = ",".join(sorted({a.verdict for a in actions if a.loud})) or "NONE"
    lines += ["", "```", f"{VERDICT_TOKEN} {verdict_set}"]
    if dispatched_at is not None:
        lines.append(f"{DISPATCH_RECEIPT_TOKEN} "
                     f"{dispatched_at.isoformat(timespec='seconds')}")
    lines += [
        "```",
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
    dispatched_at: datetime | None = None
    for action in actions:
        if action.kind != DISPATCH:
            continue
        if dry_run:
            results.append(f"DRY RUN: would dispatch {WORKFLOW_FILE} on main")
            continue
        # Stamped whether or not the POST succeeded: the ledger counts ATTEMPTS, and
        # a failed attempt is exactly the one an effects-only count would lose.
        dispatched_at = state.now
        ok, detail = dispatch_nightly(repo, token)
        results.append(detail)
        if not ok:
            print(f"::error title=prophet-rescue-dispatch-failed::{detail}", flush=True)
    if not any(a.loud for a in actions) or dry_run:
        return results

    # DUPLICATE SUPPRESSION. The red run fires every wake regardless — that is the
    # heartbeat. What is suppressed here is the fourteenth identical comment and the
    # fourteenth identical push through one long outage, because a channel that cries
    # the same thing hourly is a channel nobody reads on the night it matters.
    if not should_file_receipt(actions, state.last_receipt_verdicts):
        results.append(
            f"receipt suppressed — unchanged verdict set "
            f"{','.join(sorted(state.last_receipt_verdicts or ()))} already filed on "
            f"issue #{state.issue_number}; the red run is still the signal"
        )
        return results

    body = receipt(actions, state, session, results, dispatched_at)
    if token:
        results.append(upsert_issue(repo, token, session, body,
                                    number=state.issue_number))
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
    parser.add_argument("--disk-path", default=None,
                        help="volume the launchd lane measures for headroom; the "
                             "wrapper passes the real checkout because the tool "
                             "itself runs from a tempdir")
    args = parser.parse_args(argv)

    if args.now:
        # A bad --now must ERROR, never fall back to the wall clock: silently
        # substituting "right now" for the instant an operator asked about turns a
        # deliberate probe into a live decision against a different night.
        now = _parse_dt(args.now)
        if now is None:
            parser.error(f"--now is not an ISO-8601 instant: {args.now!r}")
    else:
        now = datetime.now(timezone.utc)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("::warning title=prophet-rescue-anonymous::no GH_TOKEN/GITHUB_TOKEN — "
              "reads are anonymous (60/hr) and no issue receipt can be filed",
              flush=True)

    state = collect_state(args.repo, token, now, lane=args.lane,
                          disk_path=Path(args.disk_path) if args.disk_path else None)
    session, boundary = expected_fire_after(now)

    # TWO PASSES, and the split is the point. Pass one answers "is anything wrong?"
    # from the three cheap reads every wake pays for. Only if it says yes do we spend
    # the two issue reads that carry the ATTEMPT LEDGER (a dispatch POST that created
    # no run still counted) and the last verdict set (so an unchanged alarm does not
    # post its fourteenth identical comment) — plus, when pass one was blocked by
    # run_in_flight, ONE jobs read for the wedge classification (§0.4a amendment):
    # without it a queued-forever hostage run mutes this lane for days. Pass two is
    # the authoritative one — the provisional plan is discarded, never executed,
    # because its budget and wedge inputs were incomplete by construction.
    provisional = decide(state)
    if any(a.loud for a in provisional):
        number, receipts, last_verdicts, err = fetch_issue_thread(
            args.repo, token, session, now)
        state.issue_number = number
        state.dispatch_receipts_today = receipts
        state.last_receipt_verdicts = last_verdicts
        state.issue_error = err
        if err is not None:
            print("::warning title=prophet-rescue-ledger-blind::could not read the "
                  f"issue thread ({err}) — the attempt ledger falls back to run "
                  "records only", flush=True)
        if any(a.blocked_by and "run_in_flight" in a.blocked_by
               for a in provisional):
            flight = run_facts(state.runs, boundary, now=now).in_flight
            if flight is not None and flight.get("id") is not None:
                jobs, jerr = fetch_run_jobs(args.repo, token, flight["id"])
                state.in_flight_jobs = jobs
                state.in_flight_jobs_error = jerr
                if jerr is not None:
                    print("::warning title=prophet-rescue-jobs-blind::could not "
                          f"read jobs for run {flight.get('id')} ({jerr}) — the "
                          "wedge check stays fail-closed (§0.4a full refusal)",
                          flush=True)
    actions = decide(state)
    annotate(actions)
    for line in execute(actions, state, session, args.repo, token,
                        dry_run=args.dry_run):
        print(f"  -> {line}", flush=True)
    return exit_code(actions)


if __name__ == "__main__":
    raise SystemExit(main())
