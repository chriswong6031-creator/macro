"""External freshness sentinel — the dead-man switch that lives OUTSIDE GitHub.

Masterplan W1 (research/NIGHTLY_RESILIENCE_AND_LIVE_TRANSITION_MASTERPLAN_2026-08-06.md,
acceptance gate §0.1). The 2026-08-06 outage left the boards frozen for six days
because every alarm lived inside GitHub Actions — the thing that was failing. A red
run in a channel nobody watches is indistinguishable from silence; this sentinel
makes silence impossible by checking the LIVE estate from the VPS that serves it
(app/deploy/macro-sentinel.timer, every 30 minutes), on infrastructure that fails
independently of GitHub.

What it checks (the user-visible truth, not the pipeline's own claims):
  * page bake stamps — HTTP ``Last-Modified`` of the live us_stocks / china /
    intelligence_hub pages. The nightly re-bakes them every day (max observed gap
    over 60 days: 23.2h), so a stamp older than 26h means the render→merge→
    VPS-pull chain is dead somewhere.
  * the board's own delay disclosure — us_stocks renders ``… prices as of
    YYYY-MM-DD`` ONLY when the engine itself knows the board lags current prices
    (templates/dashboard.html.j2 ``_su.staleness.delayed``; absent on a healthy
    bake, weekends included). This is the check the bake stamp cannot make: the
    Jul-31→Aug-6 outage re-baked the page every single day while the board froze,
    so Last-Modified stayed green throughout. A page-wide "as of" scrape cannot
    make it either — the page carries a dozen per-panel as-of dates on their own
    cadences (options ceilings, rotation tooltips) that stay fresh while the
    board freezes, which is why this anchors on the ONE string the delayed board
    emits and breaches when that self-reported lag exceeds its budget.
    china.html emits the same disclosure from the same shape of engine input —
    templates/china.html.j2 ``board_staleness.delayed``, computed by
    scripts/build_china_library.compute_board_staleness against the A-share
    session calendar in lib/cn_calendar.py. It is deliberately placed OUTSIDE
    that template's macro/stocks mode split, because china.html renders no
    setups board and a disclosure nested in the stocks-only half would leave
    THIS surface silent during the very freeze it announces. Its budget is 12
    days rather than 4 — see the SURFACES comment; mainland Golden Week and
    Spring Festival are legitimately ~10 sessionless calendar days.
  * R2 publish time — ``Last-Modified`` of ``massive_stock_day/_manifest.json``
    on the public R2 base, the same anchor scripts/audit_r2.py + daily.yml
    already budget at 26h (the manifest is put unconditionally on every
    successful full publish, no-delta days included).
  * the Prophet US store's source watermark — ``source_asof`` in the SERVED
    ``prophet/index.json``. This is the third shape, and it exists because the
    2026-08-08 audit found the same re-stamp trap one layer down:
    data/us_prophet_rank/candidates/2026-08.parquet froze at stamp_date
    2026-08-05 while us_stocks.html kept re-baking every day, so BOTH checks
    above stayed green through it (0/7 nightlies green since 08-05; every
    Prophet writer sits behind ``needs: engine``). The page's delayed-board
    marker cannot see it either — that marker reports the PRICE lag, not
    whether the Prophet ranker ran. Only the store's own asof does.

    Read from the served tree on disk (SERVED_DIR, default the Caddyfile's
    ``root * /opt/macro/site.served``) rather than over HTTP, because
    ``/prophet/index.json`` sits BEHIND the registration wall: an anonymous GET
    to https://www.mastermind-x.com/prophet/index.json answers ``HTTP 401`` +
    ``x-regwall: deny`` (probed 2026-08-08), and app/regwall.py's PUBLIC_PATHS
    grants only ``/prophet/showcase.json`` — a deliberately DELAYED artifact
    (kind ``delayed_winners``, as_of weeks behind by design) that would be a
    dishonest freshness anchor. Adding the index to the public allowlist is a
    paywall decision, not a sentinel one. The served file IS the live estate:
    it is the exact byte-for-byte payload Caddy hands an entitled reader, and
    the sentinel already runs on that host. A missing or unreadable file is
    INDETERMINATE (the sentinel is blind), never a breach — the same verdict
    discipline the HTTP surfaces use for a network error.

    Freshness is measured against the EXCHANGE CALENDAR, not the wall clock:
    ``source_asof`` must be within ``asof_max_sessions_behind`` completed NYSE sessions
    of lib/nyse_calendar.expected_last_session(). This is the cross-cutting
    lesson of every stale-store incident here — when the pipeline dies, every
    store freezes together and agrees with itself; only the calendar knows a
    completed session is missing. A calendar-anchored budget also means a
    weekend or a market holiday can never manufacture a breach, so the budget
    can be far tighter than the page budgets above without flapping.

<<<<<<< HEAD
  * the Prophet Live ARMED PACK's own watermark — ``as_of`` in the public R2
    object ``live_flow/prophet_live_armed.json``. The nightly builds it
    (daily.yml) and the */5 intraday evaluator reads it and nothing else, so a
    frozen pack means every intraday arm/trigger decision all day is being made
    against a session that has already ended — and it is the third instance of
    the same re-stamp shape: measured 2026-08-15, the object answered HTTP 200
    with ``Last-Modified: Fri, 14 Aug 2026 04:29:13 GMT`` and ``as_of``
    2026-08-13, i.e. the pack is being SERVED fine and is a session behind. No
    surface above can see that: the pack feeds no page bake, no board delay
    marker and no Prophet index field.

    Its coverage is DISCLOSED and not budgeted (``meta.armed_n`` /
    ``meta.universe_n`` / ``meta.skipped.probe_cap_cross`` ride the operator
    line — the same 2026-08-15 read showed 91 armed of a 1,763 universe with
    1,535 names cut by the probe cap). The arming budget is a product question
    owned by the Prophet Live lane, so alarming on it here would be this
    module inventing a threshold it has no standing to set; printing the three
    numbers every pass is what makes the next wave's threshold arguable from
    evidence instead of from memory.
=======
  * the CN Prophet Live runtime board — ``built_at`` in the live-plane artifact
    ``/live/cn_prophet_live.json`` (CN-PR-4, research/CN_BREATHING_PLATFORM_
    ARCHITECTURE_2026-08-15.md §6/§8). This is the fourth shape, and it is the
    first one judged on a SESSION PHASE rather than on a budget that runs all
    day. A */5-class runtime lane cannot be expressed by the 26h bake budget in
    either direction: 26h would let the board sit dead for a whole session, and
    a flat 10-minute budget would page every night, every weekend, every Golden
    Week and through every lunch break — mainland sessions run 09:30-11:30 and
    13:00-15:00 CST with a 90-minute close in the middle, and NOTHING is owed
    outside them. So the budget is the phase: 10 minutes while the session is
    live, 100 minutes through the 11:30 lunch freeze (states freeze at the
    11:30 anchor by contract — a pass that does not tick through lunch is
    correct behaviour, not an outage), and outside a mainland session the
    surface is quiet — not read at all, and never a breach.

    ``absent_ok`` for the same reason us_board_provisional carries it, one step
    earlier: this lane has not shipped its first artifact yet, so absence is the
    ordinary state rather than blindness. First SIGHT is recorded (``cn_first_
    seen`` in the SLA record), which is what lets the close-board check tell "the
    lane was never live" from "the lane was live yesterday and is gone today".

    The close-board SLA is a CLOCK question the staleness budget cannot ask:
    by 15:20 CST on a session day the payload must either carry
    ``liveness.first_close_board_at`` no later than 15:15 CST, or honestly
    disclose ``close_pending`` with ``revision == intraday_provisional``. A
    disclosed pending is NOT a breach — upstream being unresolved is a fact the
    reader is told; a silent miss is not. It alerts through the same transport
    with its own dedup namespace, at most once per session (the
    ``record_first_fresh`` idempotency, mirrored).
>>>>>>> efcf483c819d (WIP checkpoint: CN Breathing Platform session-1 close — DO NOT MERGE)

Verdict discipline (borrowed from scripts/audit_r2.py): a definitive server answer
(HTTP 200 with an over-budget stamp) is a BREACH and alerts immediately; a network
error or non-200 is INDETERMINATE and only escalates to a "sentinel is blind"
alert after BLIND_AFTER consecutive passes. Blindness can never masquerade as
recovery: a surface already in breach that stops answering STAYS in the breach
set, and the recovery notice is sent only when every breached surface has read
definitively fresh. Breach alerts repeat every REALERT_HOURS while the condition
persists — immediately only when a NEW surface joins (set churn or shrink rides
the window, so a flapping fetch cannot page every pass) — and alerts are
dispatched BEFORE the state files are written, so a full disk cannot silence the
alarm it should be raising.

Outputs:
  * operator alert via, in order of attempt: Telegram (TELEGRAM_BOT_TOKEN +
    TELEGRAM_CHAT_ID), Discord webhook (DISCORD_WEBHOOK_URL or
    DISCORD_WEBHOOK_WATCHLIST), and email through app.mailer (MAIL_SMTP_* from
    /etc/macro-api.env; recipient MAIL_SENTINEL_TO falling back to
    MAIL_SUPPORT_TO). Any one succeeding counts as delivered; all three failing
    is logged loudly and the run exits non-zero either way.
  * machine-readable staleness state at <public-dir>/live/staleness.json, written
    by atomic rename (the live-plane convention) and served read-only at
    /live/staleness.json — the input a later wave's on-site staleness banner
    reads. ``ok`` there is the honest tri-state fold: false when anything is in
    active breach OR the sentinel has been blind past threshold — "I can't tell"
    must never render as "fresh".
  * private counters (consecutive failures, last-alert stamps) at
    <state-dir>/state.json so the 30-minute cadence can hold the re-alert window.
  * the SLA record at <state-dir>/first_fresh.json — one append-only stamp per
    (session, surface) recording when a surface FIRST read definitively fresh.
    Both files above are overwritten wholesale every pass, so without this the
    estate could answer "is it fresh now" and could not answer "was it live by
    18:30 ET on Tuesday" — the only form the W-L1 provisional-board gate takes.
    Its summary (streak + recent sessions) rides staleness.json as ``sla``; it
    measures and never pages.

    An SLA surface may name a CLIENT ARTIFACT (``sla.client_path`` +
    ``sla.client_session_path``), and when it does, the stamp additionally
    requires that artifact to name the same session. A surface may also name a
    ``client_contract``: then naming a date is not enough — the payload at
    ``client_state_path`` must pass the same fail-dark shape/freshness gates as
    the browser renderer. The gate the record exists to measure is a READER
    question — "fresh picks live on the site by 18:30 ET" — and the artifact
    the sentinel budgets for staleness is not always the one a browser consumes.
    For the close-pass board they are two different
    files written by two different steps: the full board lands in
    live/us_board_provisional.json, and the small ``board_state`` key the
    dashboard actually paints from is merged into live/prophet_live.json by a
    LATER, SEPARATE step that fails DARK by design
    (scripts/close_pass_mirror.annotate_live_strip returns False and writes
    nothing when the evaluator's artifact is absent or unparseable, and its
    caller discards that result). So the board can land fresh and on time while
    no reader sees anything — and without this condition the SLA would score
    those sessions as passes. An SLA that can pass while the feature is
    invisible measures the wrong thing.

    The client read is deliberately NOT a surface. It never enters ``evaluate``'s
    stale/indeterminate sets, so it can neither page nor feed the blindness
    escalation: a key that is legitimately absent for most of every day (the
    evaluator rewrites prophet_live.json whole every five minutes and carries no
    ``board_state`` of its own) would otherwise be exactly the false-positive
    factory the falsifier law below forbids. It can only withhold a stamp, and a
    withheld stamp reads as a MISSED session in the streak — measurement, never
    an alarm.

    Each stamp additionally carries the W-L1 LATENCY DECOMPOSITION (PR-C): the
    close the board was built from, the instant the payload was built, the
    instant a reader could first see it, and the two gaps between them. A
    pass/fail on one deadline says the estate missed; it never says WHERE the
    time went, and the Fri 2026-08-14 board is the case in point — published
    23:19:14Z (19:19 ET) against an 18:30 SLA and a 16:15 product target, with
    the record unable to say whether the hour went into waiting for closes or
    into the pass itself. The decomposition is measured, never asserted: every
    field is OPTIONAL and reads null when the payload does not carry it (the
    close-provenance keys are a sibling lane's addition and are absent on every
    board published before it), a missing input yields null rather than a
    fabricated zero, and ``visible_resolution_sec`` publishes the 30-minute
    cadence as the honest error bar on ``candidate_to_visible_sec`` instead of
    letting a second-precision number imply second-precision knowledge.

    Those facts, and the armed pack's coverage counts, ride the PRIVATE record
    and the operator's stdout only — never /live/staleness.json, which Caddy
    serves to anyone. Coverage counts and per-session provenance for a walled
    artifact are a paywall decision (#3391, the same one that keeps the board
    itself off the public plane), and a watchdog must not make it as a side
    effect of measuring. ``public_report`` is where that boundary is drawn.

Stdlib-only ON PURPOSE (urllib, json, re): the sentinel must not depend on the
venv contents, the engine tree, or lib.config being healthy — it is the observer
of last resort, so its import closure is as small as honesty allows (app.mailer
and lib.nyse_calendar, both themselves stdlib-only with zero data dependencies,
are imported lazily and failure-guarded — an unimportable calendar degrades the
Prophet surface to INDETERMINATE, it never crashes the pass or fakes a verdict).

Falsifier law (masterplan B5): >2 false-positive pages in a month means the
budgets are wrong — fix the budgets, never mute the sentinel.

Usage:
  python -m scripts.freshness_sentinel                  # one sentinel pass
  python -m scripts.freshness_sentinel --dry-run        # report only, no state/alert
  python -m scripts.freshness_sentinel --now 2026-08-08T05:00:00+00:00
      # clock override — the §0.1 acceptance drill: point the clock one simulated
      # day past the last bake and watch the alert fire without killing anything.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Cloudflare's WAF 403s python-default User-Agents on the public r2.dev host
# (scripts/audit_r2.py, same constant class).
UA = "macro-freshness-sentinel/1.0"

DEFAULT_BASE = "https://www.mastermind-x.com"
# Same public data-plane base templates/data_base.js and scripts/audit_r2.py pin.
DEFAULT_R2_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
DEFAULT_PUBLIC_DIR = "/var/lib/macro-live/public"
DEFAULT_STATE_DIR = "/var/lib/macro-sentinel"
# The Caddyfile's static root (`root * /opt/macro/site.served`) — macro-update
# rsyncs the git work-tree site/ into it by atomic per-file rename, so what is
# here is exactly what the edge serves. Read-only to this process.
DEFAULT_SERVED_DIR = "/opt/macro/site.served"

#: Consecutive INDETERMINATE passes (per surface) before the sentinel reports its
#: own blindness. 6 passes at the 30-minute cadence ≈ 3 hours without a
#: definitive read.
BLIND_AFTER = 6
#: While a breach persists, repeat the alert this often (hours) instead of every pass.
REALERT_HOURS = 6.0
#: Nightly bake budget (masterplan W1: 26h). daily.yml fires 22:30 UTC seven days
#: a week; max observed inter-bake gap on these pages over 60 days is 23.2h.
BAKE_BUDGET_HOURS = 26.0
#: Page body cap. The biggest board page is ~1 MB; hitting the cap means the read
#: was truncated and the verdict would be built on a partial body → INDETERMINATE.
BODY_CAP = 2_000_000
#: Sessions of first-fresh-at history kept in <state-dir>/first_fresh.json. The
#: file is APPEND-ONLY within a session — once a (session, surface) pair is
#: stamped it is never rewritten, because "when did it FIRST read fresh" has
#: exactly one answer and a later pass re-stamping it would erase the only
#: measurement the SLA has. 40 sessions ≈ two months, which is the smallest
#: window that can still show a five-session gate failing and recovering.
SLA_HISTORY_SESSIONS = 40
#: Sessions reported in the public staleness.json SLA block (and walked when the
#: consecutive-met streak is computed).
SLA_REPORT_SESSIONS = 10
FIRST_FRESH_SCHEMA = "sentinel.first_fresh/v1"

#: Completed NYSE sessions the Prophet store may lag before it is a breach.
#: 1 absorbs a single missed nightly (and its next-day retry); the SECOND missed
#: session pages — "breach by day 2". The real freeze reads exactly there: a
#: store stamped 2026-08-05, checked 2026-08-08, is 2 completed sessions behind
#: (08-06, 08-07) and must alarm. This is far tighter than the 4-day us_stocks
#: board budget and can afford to be, because the anchor is the exchange
#: calendar rather than the wall clock: a weekend, a long weekend and a market
#: holiday all add ZERO to this count, so the routine quiet stretches that force
#: the calendar-blind budgets wide cannot flap this one. Prophet also earns the
#: tighter budget — it is the surface a reader acts on, and the nightly that
#: writes it is the same `needs: engine` chain whose death this catches.
PROPHET_MAX_SESSIONS_BEHIND = 1

<<<<<<< HEAD
#: The sentinel's own cadence in seconds (app/deploy/macro-sentinel.timer fires
#: every 30 minutes). It is the RESOLUTION of every "first user-visible at"
#: instant this module records, and it is published beside those measurements
#: rather than left implicit: a board that landed at 18:04 and was first seen at
#: 18:31 reads as "27 minutes to visible" and the true figure is anywhere in
#: [0, 30] minutes. Stating the error bar is the difference between a
#: measurement and a number. Tightening it is a timer change, not a code change,
#: and this constant is what a later cadence must be re-derived from.
VISIBLE_RESOLUTION_SECONDS = 1800

#: Completed NYSE sessions the Prophet Live ARMED PACK may lag before it is a
#: breach — deliberately the same 1 as prophet_us above, and NOT 0.
#:
#: 0 was measured wrong before it was written. The pack is produced by the
#: NIGHTLY (daily.yml) and lands late: the object's own Last-Modified on
#: 2026-08-15 was 04:29:13Z, i.e. ~00:30 ET the morning AFTER the session it
#: describes. ``expected_last_session`` rolls to today at 17:00 ET, so a 0
#: budget declares a breach from 17:00 ET until the nightly's pack step lands —
#: about seven hours, every session day, on a healthy estate. That is the
#: false-positive factory this module's own falsifier law forbids, and it would
#: have been discovered by being paged five times a week.
#:
#: 1 keeps the "breach by day 2" shape the two sibling content surfaces already
#: use: the first missed nightly is absorbed, the second pages. The cost is
#: named rather than hidden — a pack that dies on a Thursday night is reported
#: (the sessions-behind count is on the operator line from the first pass) but
#: does not PAGE until the following Monday evening. A publication-deadline
#: budget ("session D's pack is expected by 06:00 UTC on D+1", the clock
#: engine/close_pass/board.NIGHTLY_EXPECTED_BY_UTC already encodes) is the
#: instrument that would page the same evening; it is a different budget SHAPE
#: than anything here uses, so it belongs to a wave that can prove it against a
#: month of real landing times rather than to this one.
ARMED_PACK_MAX_SESSIONS_BEHIND = 1
=======
# --------------------------------------------------------------------------- #
# CN Prophet Live (CN-PR-4) — the mainland runtime board's phase clock.
#
# Every boundary below is Asia/Shanghai, which has no DST, so the UTC twins are
# fixed year-round and are the ones the drills quote:
#     09:10 CST = 01:10 UTC   pre-open warmup begins
#     09:30 CST = 01:30 UTC   morning session opens        ── 10-minute budget
#     11:30 CST = 03:30 UTC   lunch freeze begins          ── 100-minute budget
#     13:00 CST = 05:00 UTC   afternoon session opens      ── 10-minute budget
#     15:15 CST = 07:15 UTC   post-close pass stands down
#     15:20 CST = 07:20 UTC   close-board SLA is judged
#     17:00 CST = 09:00 UTC   watch window closes
# --------------------------------------------------------------------------- #
#: Minutes the artifact's ``built_at`` may lag while a mainland session is LIVE.
#: The evaluator ticks every 5 minutes (§5), so 10 absorbs exactly one missed
#: pass and pages on the second — the same "breach by the second miss" shape
#: PROPHET_MAX_SESSIONS_BEHIND uses one cadence up.
CN_LIVE_SESSION_BUDGET_MIN = 10.0
#: Minutes allowed through the 11:30-13:00 CST lunch break. States FREEZE at the
#: 11:30 anchor by contract (§2 session_break: passes may run but no transitions,
#: no fades), so a lane that stops writing across lunch is behaving correctly.
#: 100 clears the full 90-minute break with 10 minutes of slack, which means the
#: first afternoon pass is what re-arms the tight budget — not the clock.
CN_LIVE_LUNCH_BUDGET_MIN = 100.0
#: Completed A-share sessions the artifact's own ``session`` may lag. During a
#: live session the artifact names TODAY while the calendar's newest COMPLETED
#: session is yesterday, so a healthy in-flight board reads 0 behind; 1 absorbs
#: one missed session and the second pages.
CN_MAX_SESSIONS_BEHIND = 1
#: When the sentinel judges the close board (Asia/Shanghai).
CN_CLOSE_SLA_BY_CST = "15:20"
#: What ``liveness.first_close_board_at`` must beat (Asia/Shanghai). §2's
#: post_close window ends at 15:15; a board stamped later than that missed it.
CN_CLOSE_BOARD_BY_CST = "15:15"
#: Session-day CST window in which the CN surface is read at all. Opens with the
#: pre-open warmup and stays open past the close SLA so a late board can still be
#: SEEN and judged; outside it the lane owes nothing and is not observed.
CN_WATCH_OPEN_CST = "09:10"
CN_WATCH_CLOSE_CST = "17:00"
#: Where the close-board SLA stamps live inside the (shared) first_fresh record.
#: A sibling key of ``sessions`` rather than a second file: same append-only
#: discipline, same atomic write, nothing new to rotate.
CN_CLOSE_SLA_KEY = "cn_close_sla"
#: First-sight marker. ``absent_ok`` says a missing artifact is not blindness;
#: this says whether it was ever there, which is the difference between "the
#: lane has not shipped yet" and "the lane shipped and is gone at the close".
CN_FIRST_SEEN_KEY = "cn_first_seen"
>>>>>>> efcf483c819d (WIP checkpoint: CN Breathing Platform session-1 close — DO NOT MERGE)

# Per-surface freshness budgets. ``delay_budget_days`` applies to the board's own
# delayed-board disclosure (see module docstring): the marker only renders when
# the ENGINE says prices lag, so its presence is already trading-day aware —
# weekends and holidays never print it. 4 calendar days ≈ two missed sessions
# past a long weekend; the Jul-31 freeze would have paged on Aug 4 while the
# bake stamp stayed green the whole time. None = the page has no board stamp to
# anchor on.
#
# china is 12, not 4, and the difference is a calendar fact rather than a weaker
# standard. The mainland exchanges close for Spring Festival and National Day
# Golden Week, each of which runs ~9-10 CALENDAR days with no session at all — a
# 4-day budget would page every October and every February on a board that is
# behaving exactly as it should. 12 clears the longest legitimate closure with
# two days to spare. It is also the budget that absorbs the deliberate
# imprecision in lib/cn_calendar.py: that holiday table is minimal ON PURPOSE
# (a missing entry reads as a false "stale", never a silently-wrong "fresh"), so
# the china board may legitimately print its disclosure part-way through a long
# holiday. Printing it is honest — the prices really are 10 days old — and the
# budget is what decides whether that is a holiday or an outage.
# Consequence to accept: a China board that dies the day Golden Week starts is
# caught ~12 days later, not ~4. The bake-stamp check still covers that surface
# at 26h; only the board-lag check waits.
SURFACES: list[dict] = [
    {
        "id": "us_stocks",
        "kind": "page",
        "path": "/us_stocks.html",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": 4,
    },
    {
        "id": "china",
        "kind": "page",
        "path": "/china.html",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": 12,
    },
    {
        "id": "hub",
        "kind": "page",
        "path": "/intelligence_hub.html",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": None,
    },
    {
        "id": "r2_massive_stock_day",
        "kind": "r2",
        "path": "/massive_stock_day/_manifest.json",
        "bake_budget_hours": BAKE_BUDGET_HOURS,
        "delay_budget_days": None,
    },
    # bake_budget_hours is None ON PURPOSE — this surface is judged on CONTENT,
    # not on a stamp. The served file's mtime is set by the rsync of a git
    # checkout, so an unchanged file legitimately keeps an old mtime while a
    # touched-but-frozen one gets a fresh stamp: exactly the re-stamp trap this
    # surface exists to defeat. ``asof`` measured against the session calendar
    # is the honest read, and it is the only one budgeted here.
    {
        "id": "prophet_us",
        "kind": "served_file",
        "path": "/prophet/index.json",
        "bake_budget_hours": None,
        "delay_budget_days": None,
        # Never monitor index.asof: it is the publication/run clock and a rerun over
        # frozen inputs re-stamps it green. source_asof is
        # us_standouts.staleness.price_through, the ranked-price watermark the plan
        # builder actually consumed.
        "asof_field": "source_asof",
        "asof_max_sessions_behind": PROPHET_MAX_SESSIONS_BEHIND,
        "required_false_fields": (
            "source_delayed", "source_unknown", "source_mixed_vintage",
        ),
        "required_values": {"source_basis": "panel_majority"},
    },
    # W-L1a — the evening close-pass provisional board, on the VPS live plane
    # (kind live_file: <public-dir>/live/…, the plane the daemons write, NOT the
    # git-rsynced site.served tree the prophet surface reads).
    #
    # ``absent_ok`` is the load-bearing key. This artifact is LEGITIMATELY absent
    # for most of every day: it is published once, after the close, and there is
    # nothing to publish before then. Without the exemption a missing file would
    # count toward the blindness escalation and page "the sentinel is blind"
    # every single morning by construction — the false-positive factory the
    # module's own falsifier law forbids. Absence is not blindness here; it is
    # the ordinary pre-publication state, and the SLA record below is what
    # measures whether an evening board ever arrived.
    #
    # The staleness budget is 1 session for the same reason prophet_us is: a
    # single missed evening is absorbed, the SECOND is a definitive breach. It is
    # a STALENESS budget, not the SLA — the SLA is a clock-time question ("live
    # by 18:30 ET on the session it describes") that no sessions-behind budget
    # can express, which is why ``sla`` exists at all. That split is why this
    # entry keeps its budget while its SLA looks at a DIFFERENT file below: the
    # staleness question is about the full board (this artifact is the one a
    # later card renderer and the confirmation delta read), and the SLA question
    # is about the reader.
    #
    # ``client_path`` / ``client_session_path`` are what make the SLA a reader
    # measurement. The dashboard never fetches THIS file: it polls
    # live/prophet_live.json and paints from that artifact's top-level
    # ``board_state`` key, which a separate, later step merges in
    # (scripts/close_pass_mirror.annotate_live_strip) and which fails dark on an
    # absent or unparseable evaluator artifact. Both files are written by the
    # same 5-minute timer seconds apart, which is precisely why the divergence is
    # invisible until it happens: the board publishes FIRST and unconditionally,
    # the annotate runs SECOND and its False return is discarded by the caller,
    # so a dark surface leaves this artifact looking perfect. See the module
    # docstring for why this read is not a surface of its own.
    {
        "id": "us_board_provisional",
        "kind": "live_file",
        "path": "/live/us_board_provisional.json",
        "bake_budget_hours": None,
        "delay_budget_days": None,
        "asof_field": "as_of",
        "asof_max_sessions_behind": 1,
        "absent_ok": True,
        # PR-C: the payload facts the latency decomposition is measured FROM.
        # Named rather than inlined so the extractor is one function with one
        # test, and so a surface that carries no such payload simply omits the
        # key instead of every reader having to know which shapes exist.
        "facts": "close_pass",
        # masterplan §0 W-L1: live by 18:30 ET, five consecutive green sessions.
        "sla": {
            "by_et": "18:30",
            "sessions_required": 5,
            "client_path": "/live/prophet_live.json",
            "client_state_path": ("board_state",),
            "client_contract": "wl1.provisional_cards/paintable-v1",
            "client_session_path": ("board_state", "board", "as_of"),
        },
    },
<<<<<<< HEAD
    # PR-C — the intraday lane's INPUT, on the public R2 read base.
    #
    # Read over HTTP rather than off a live-plane path because the VPS does not
    # hold this artifact: the pack is a GitHub-Actions product that the */5
    # evaluator pulls from R2 (engine/prophet_live/r2io.PACK_KEY), so R2 is the
    # plane where "is the pack stale" is actually answerable. That makes this
    # the one content surface whose transport can fail independently of the
    # box the sentinel runs on, which is a feature — the two other content
    # surfaces are both local file reads and would go silent together.
    #
    # bake_budget_hours is None for the reason prophet_us's is: the object is
    # re-PUT on every nightly, so Last-Modified reports the publish and says
    # nothing about the content. ``as_of`` against the session calendar is the
    # only honest read, and it is the only one budgeted.
    #
    # No ``absent_ok``. Unlike the evening board this artifact has no legitimate
    # absent state — it is written once a night and stays. A 404 (the shape a
    # migration to the private operational bucket would take;
    # config/r2_delivery_plane_classification.v1.json classifies this key
    # PRIVATE_OPERATIONAL with that move still pending) therefore reads as the
    # sentinel losing sight of the surface and escalates through the blindness
    # counter after BLIND_AFTER passes. That is the correct outcome for a
    # repointed artifact: loud, honest, and repaired by a config change rather
    # than silently green.
    {
        "id": "prophet_live_armed",
        "kind": "r2",
        "path": "/live_flow/prophet_live_armed.json",
        "bake_budget_hours": None,
        "delay_budget_days": None,
        "asof_field": "as_of",
        "asof_max_sessions_behind": ARMED_PACK_MAX_SESSIONS_BEHIND,
        # Coverage is DISCLOSED, never budgeted — see the module docstring.
        "facts": "armed_pack",
=======
    # CN-PR-4 — the mainland runtime board on the same live plane. It follows
    # the us_board_provisional precedent exactly where the precedent applies
    # (live_file kind, live-plane root, absent_ok, a sessions-behind budget on
    # the artifact's own session stamp) and diverges in the one place a runtime
    # lane must: ``phase_clock`` routes it to a check that asks the mainland
    # session calendar what is owed RIGHT NOW instead of budgeting a whole day.
    #
    # ``absent_ok`` is doing more work here than it does above, because this
    # lane has not shipped its FIRST artifact yet. Absence alerts nothing until
    # first sight, and first sight is recorded (CN_FIRST_SEEN_KEY) so the
    # exemption cannot quietly become permanent: once the board has been seen,
    # a missing artifact at the close is a breach like any other.
    #
    # ``close_sla`` is deliberately NOT named ``sla``. The SLA machinery above
    # walks the NYSE calendar and compares against ``by_et``; pointing it at a
    # mainland artifact would measure this board against the wrong exchange's
    # sessions and the wrong clock. Same idea, own calendar, own function.
    #
    # The id is ``cn_live_board`` and NOT ``cn_prophet_live``, which would read
    # more naturally against the filename. The reader-side client artifact this
    # module deliberately never makes a surface is ``/live/prophet_live.json``,
    # and the structural guard that proves it (tests/test_freshness_sentinel.py
    # ``test_a_dark_reader_never_breaches_never_blinds_and_never_pages``) asserts
    # that NO surface key contains the substring ``prophet_live``. A surface
    # named for this artifact would trip that guard on a substring while being a
    # completely different file — and the fix for a name collision is a name,
    # never a weakened guard.
    {
        "id": "cn_live_board",
        "kind": "live_file",
        "path": "/live/cn_prophet_live.json",
        "bake_budget_hours": None,
        "delay_budget_days": None,
        # The artifact's own CN session date (§6 top-level ``session``), not a
        # publication clock — the same "never monitor the run stamp" rule the
        # prophet_us entry states at length.
        "asof_field": "session",
        "asof_max_sessions_behind": CN_MAX_SESSIONS_BEHIND,
        "absent_ok": True,
        "phase_clock": "cn",
        "close_sla": {
            "by_cst": CN_CLOSE_SLA_BY_CST,
            "board_by_cst": CN_CLOSE_BOARD_BY_CST,
            "liveness_field": "first_close_board_at",
            "pending_revision": "intraday_provisional",
        },
>>>>>>> efcf483c819d (WIP checkpoint: CN Breathing Platform session-1 close — DO NOT MERGE)
    },
]

# The English renderings of the delayed-board marker. us_stocks
# (templates/dashboard.html.j2): "dots reflect prices as of D" and "Board is
# delayed — prices are as of D". china (templates/china.html.j2): "BOARD
# DELAYED — prices as of D". Both pages ship the l-en span in every bake
# regardless of the reader's language, so matching the English form is
# sufficient; the zh twin carries no ISO date in this phrase.
_DELAY_RE = re.compile(r"prices (?:are )?as of (20\d{2}-\d{2}-\d{2})", re.IGNORECASE)


@dataclass
class FetchResult:
    """One HTTP observation of a surface. ``error`` set ⇒ nothing else is trusted."""

    status: int | None = None
    last_modified: datetime | None = None
    body: str | None = None
    error: str | None = None


#: The read a surface gets when this pass deliberately performed none — the CN
#: live surface outside its watch window (run() skips the read; there is nothing
#: to judge and nothing owed) — or when a caller supplied no read for it at all.
#: It maps to INDETERMINATE through the ordinary path, which is the honest
#: verdict for "I did not look": only the phase-aware check may turn a
#: not-looked-at CN surface into a quiet ``ok``, and it does that BEFORE reading
#: this. An unlooked-at surface must never be able to read as fresh.
_NOT_READ = FetchResult(error="no read performed for this surface")


# --------------------------------------------------------------------------- #
# Fetching (real transport — tests inject FetchResults instead)
# --------------------------------------------------------------------------- #
def fetch(url: str, *, want_body: bool, timeout: float = 20.0) -> FetchResult:
    """GET (pages, for the delay-marker parse) or HEAD (R2 manifest) one surface.

    Any network-layer failure — and a body that hits BODY_CAP, which would make
    every downstream parse a guess — lands in ``error``; the caller maps it to
    INDETERMINATE, never to a breach.
    """
    req = urllib.request.Request(
        url, method="GET" if want_body else "HEAD", headers={"User-Agent": UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            lm_raw = resp.headers.get("Last-Modified")
            lm = None
            if lm_raw:
                try:
                    lm = parsedate_to_datetime(lm_raw)
                    if lm.tzinfo is None:
                        lm = lm.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    lm = None
            body = None
            if want_body:
                raw = resp.read(BODY_CAP + 1)
                if len(raw) > BODY_CAP:
                    return FetchResult(
                        status=resp.status,
                        error=f"body exceeded {BODY_CAP} byte cap — truncated read",
                    )
                body = raw.decode("utf-8", errors="replace")
            return FetchResult(status=resp.status, last_modified=lm, body=body)
    except urllib.error.HTTPError as exc:
        return FetchResult(status=exc.code, error=f"HTTP {exc.code} {exc.reason}")
    except Exception as exc:  # noqa: BLE001 — DNS/timeout/TLS all become INDETERMINATE
        return FetchResult(error=f"{type(exc).__name__}: {exc}")


def read_served(served_dir: Path, path: str) -> FetchResult:
    """Read one artifact out of the SERVED tree — the walled surfaces' transport.

    Shaped as a FetchResult so it flows through the same evaluate/alert path as
    the HTTP surfaces: ``status=200`` + mtime + body on success, ``error`` set on
    anything else. A missing file, a permission error and an unreadable byte all
    land in ``error`` → INDETERMINATE, so a sentinel pointed at the wrong root
    (or run off the VPS entirely) reports its own blindness instead of paging a
    fake outage.
    """
    target = served_dir / path.lstrip("/")
    try:
        stat = target.stat()
        raw = target.read_bytes()
    except OSError as exc:
        return FetchResult(error=f"served read failed: {type(exc).__name__}: {exc}")
    if len(raw) > BODY_CAP:
        return FetchResult(status=200, error=f"served body exceeded {BODY_CAP} byte cap")
    return FetchResult(
        status=200,
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        body=raw.decode("utf-8", errors="replace"),
    )


def sessions_behind(asof: str, now: datetime) -> int:
    """Completed NYSE sessions the store stamped ``asof`` is missing (0 = current).

    Lazy, failure-guarded import for the same reason app.mailer is one: the
    sentinel must survive a broken tree. lib/nyse_calendar is pure rule
    arithmetic with zero data dependencies, so importing it costs the sentinel
    none of its independence — but an ImportError still has to degrade to
    "I can't tell" rather than to a verdict. Raises so the caller can map the
    failure to INDETERMINATE.
    """
    from datetime import date as _date  # noqa: PLC0415 — stdlib, kept with its one caller

    from lib import nyse_calendar  # noqa: PLC0415 — see docstring

    return nyse_calendar.sessions_behind(_date.fromisoformat(asof), now)


def cn_sessions_behind(asof: str, now: datetime) -> int:
    """Completed A-share sessions the artifact stamped ``asof`` is missing.

    The mainland twin of ``sessions_behind`` above, composed INLINE from the two
    primitives lib/cn_calendar.py already exports rather than added to that
    module: ``expected_last_session`` knows the 15:00 CST close plus its settle
    buffer, and ``sessions_between`` counts sessions strictly after a date, so
    ``sessions_between(stamp, expected_last_session(now))`` is exactly "how many
    completed sessions has this artifact missed" with zero new calendar code to
    keep in step. ``sessions_between`` returns 0 when the end is not past the
    start, so an artifact naming TODAY's in-flight session (the healthy runtime
    case, where the newest COMPLETED session is yesterday) reads 0 behind rather
    than going negative.

    Same lazy, failure-guarded import discipline as its NYSE sibling: an
    unimportable calendar must degrade the surface to "I can't tell", never take
    the watchdog down and never fabricate a verdict. Raises so the caller maps
    it to INDETERMINATE.
    """
    from datetime import date as _date  # noqa: PLC0415 — stdlib, kept with its one caller

    from lib import cn_calendar  # noqa: PLC0415 — see docstring

    return cn_calendar.sessions_between(
        _date.fromisoformat(asof), cn_calendar.expected_last_session(now)
    )


def board_delay_stamp(body: str) -> str | None:
    """The board's self-reported price-through date, or None when not delayed.

    Oldest match on purpose (they should agree — both render from the same
    ``_su.staleness.price_through``): if a second marker family ever appears,
    the oldest is the honest one. A page-wide max over every "as of" string is
    exactly wrong here — see the module docstring.
    """
    dates = _DELAY_RE.findall(body or "")
    return min(dates) if dates else None


# --------------------------------------------------------------------------- #
# Payload FACTS — the optional inputs to the W-L1 latency decomposition and to
# the armed pack's coverage disclosure.
#
# EVERY reader here is total and every field is optional. The producers these
# read are moving: the close-provenance keys are a sibling lane's addition, so
# every board published before it carries none of them, and a replay of an
# archived payload must not crash the watchdog or — much worse — read a missing
# field as a zero. A null says "not measured"; a zero says "measured, and it was
# instant". Those are different claims and only one of them is true here.
#
# Nothing in this section can produce a VERDICT. Facts annotate; the budgets
# above are the only things that decide stale/ok, and a fact that fails to parse
# costs its own line and nothing else.
# --------------------------------------------------------------------------- #
def _opt_str(value: object) -> str | None:
    """A non-empty string, or None. Anything else is unmeasured, not coerced."""
    return value if isinstance(value, str) and value else None


def _opt_int(value: object) -> int | None:
    """An integer count, or None. ``bool`` is excluded explicitly — it is an
    ``int`` subclass in Python, so a stray ``True`` would otherwise publish as a
    coverage count of 1."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _opt_bool(value: object) -> bool | None:
    """A real boolean, or None. ``False`` is a MEASUREMENT (the close was not
    final) and must never collapse into "absent" — which is exactly what a
    falsy-test here would do."""
    return value if isinstance(value, bool) else None


def _from_meta_or_top(doc: dict, meta: dict, key: str) -> object:
    """One field, preferring ``meta`` and falling back to the payload root.

    The close-provenance keys are landing in a sibling PR that this one must not
    touch, and its final nesting is not merged yet. Reading both places costs
    two dict lookups and removes the failure mode where a correct producer and a
    correct watchdog ship a null between them; ``meta`` wins so that if the two
    ever disagree, the more specific location is authoritative rather than
    whichever the reader happened to check first.
    """
    if key in meta:
        return meta[key]
    return doc.get(key)


def close_pass_facts(doc: object) -> dict:
    """The close-pass board payload's latency + coverage + provenance facts.

    Keys mirror the payload's own vocabulary (engine/close_pass/board.build_board
    and its meta block) so a reader of the record can grep straight back to the
    producer. ``board_generated_at`` is the ONE rename: the payload calls it
    ``built_at`` and the board_state projection calls the identical value
    ``generated_at``, so the record picks the name the reader-facing projection
    uses and states here that the two are the same instant.
    """
    if not isinstance(doc, dict):
        return {}
    meta = doc.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    skipped = meta.get("skipped")
    return {
        "board_generated_at": _opt_str(doc.get("built_at")),
        "close_observed_at": _opt_str(_from_meta_or_top(doc, meta, "close_observed_at")),
        "close_source": _opt_str(_from_meta_or_top(doc, meta, "close_source")),
        "close_basis": _opt_str(_from_meta_or_top(doc, meta, "close_basis")),
        "close_finalized": _opt_bool(_from_meta_or_top(doc, meta, "close_finalized")),
        "coverage": {
            "universe_n": _opt_int(meta.get("universe_n")),
            "evaluated_n": _opt_int(meta.get("evaluated_n")),
            "admitted_n": _opt_int(meta.get("admitted_n")),
        },
        # Passed through whole rather than key-by-key: the producer adds skip
        # reasons as it learns them (``corp_action_today`` is a sibling lane's),
        # and an allowlist here would silently drop every reason invented after
        # this line was written — the exact shape of disclosure rot.
        "skipped": dict(skipped) if isinstance(skipped, dict) else None,
    }


def armed_pack_facts(doc: object) -> dict:
    """The Prophet Live armed pack's coverage counts. Disclosure only.

    ``probe_cap_cross`` is broken out of ``skipped`` because it is the count the
    arming budget is actually about — names the probe budget refused to look at,
    as opposed to names it looked at and declined. The whole ``skipped`` map
    rides along for the same anti-rot reason as above.
    """
    if not isinstance(doc, dict):
        return {}
    meta = doc.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    skipped = meta.get("skipped")
    skipped = skipped if isinstance(skipped, dict) else {}
    return {
        "coverage": {
            "universe_n": _opt_int(meta.get("universe_n")),
            "probed_n": _opt_int(meta.get("probed_n")),
            "armed_n": _opt_int(meta.get("armed_n")),
            "probe_cap_cross": _opt_int(skipped.get("probe_cap_cross")),
        },
        "skipped": dict(skipped) or None,
    }


#: Surface ``facts`` name → extractor. A surface that names an UNKNOWN reader
#: gets no facts rather than an exception: an unimplemented extractor must
#: degrade the disclosure, never the watchdog.
FACT_READERS = {
    "close_pass": close_pass_facts,
    "armed_pack": armed_pack_facts,
}


def _seconds_between(earlier: object, later: object) -> float | None:
    """``later - earlier`` in seconds, or None when either instant is unusable.

    Both arguments go through ``_instant``, which requires a TIMEZONE-QUALIFIED
    ISO string: a naive stamp answers None rather than being assumed UTC. The
    assumption would be free five months of the year and an hour wrong for the
    rest, and this figure's whole job is to be trusted to the minute.

    A negative result is returned as measured. Clamping it at zero would hide
    the one thing a negative can mean — a producer stamping a close it had not
    observed yet — behind a plausible-looking 0.0.
    """
    start, end = _instant(earlier), _instant(later)
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 1)


# --------------------------------------------------------------------------- #
# Pure evaluation core
# --------------------------------------------------------------------------- #
def check_surface(surface: dict, fr: FetchResult, now: datetime) -> dict:
    """One surface → {id, status ∈ ok|stale|indeterminate, ages, detail}."""
    if surface.get("phase_clock") == "cn":
        # CN-PR-4: judged on the mainland session clock, not on the wall-clock
        # budgets below. Dispatched HERE rather than in evaluate() so that every
        # caller — run(), the tests, scripts/build_output_health.py's importer —
        # reaches the phase-aware check through the one entry point they already
        # use, and a future surface cannot get the wrong check by calling around.
        return check_cn_live_surface(surface, fr, now)
    out: dict = {
        "id": surface["id"],
        "kind": surface["kind"],
        "status": "ok",
        "bake_budget_hours": surface["bake_budget_hours"],
        "delay_budget_days": surface["delay_budget_days"],
        "bake_stamp": None,
        "bake_age_hours": None,
        "board_delayed": False,
        "board_price_through": None,
        "board_delay_days": None,
        "asof": None,
        "asof_sessions_behind": None,
        "absent": False,
        # PR-C. PRIVATE annotations — latency/coverage/provenance read off the
        # payload. Always present and always a dict so no consumer has to
        # branch on its existence; ``public_report`` strips it before anything
        # reaches the publicly-served staleness file.
        "facts": {},
        "detail": "",
    }
    if fr.error or fr.status != 200:
        out["status"] = "indeterminate"
        out["detail"] = fr.error or f"HTTP {fr.status}"
        # A surface that publishes once a day has a NORMAL absent state, and the
        # difference between "not published yet" and "I cannot see" is the whole
        # question the blindness counter exists to answer. Narrow on purpose:
        # only a genuinely missing file qualifies — a permission error, a
        # truncated read or an HTTP failure is still blindness.
        if surface.get("absent_ok") and "FileNotFoundError" in (fr.error or ""):
            out["absent"] = True
            out["detail"] = "not published yet (absence is a normal state here)"
        return out

    problems: list[str] = []
    bake_budget_h = surface["bake_budget_hours"]

    if bake_budget_h is not None and fr.last_modified is None:
        # A 200 with no parseable Last-Modified is a serving-config regression —
        # the sentinel cannot do its job. Indeterminate (not a staleness
        # verdict), so it escalates through the blindness counter rather than
        # paging as an outage.
        out["status"] = "indeterminate"
        out["detail"] = "no Last-Modified header on a 200 response"
        return out

    bake_age_h = None
    if fr.last_modified is not None:
        bake_age_h = (now - fr.last_modified).total_seconds() / 3600.0
        out["bake_stamp"] = fr.last_modified.isoformat()
        out["bake_age_hours"] = round(bake_age_h, 1)
    # A None budget records the stamp for the operator line and budgets nothing
    # (see the prophet_us SURFACES comment) — it is never "budget satisfied".
    if bake_budget_h is not None and bake_age_h > bake_budget_h:
        problems.append(
            f"bake stamp {bake_age_h:.1f}h old (budget {bake_budget_h:.0f}h)"
        )

    if surface["delay_budget_days"] is not None and fr.body is not None:
        stamp = board_delay_stamp(fr.body)
        if stamp is not None:
            out["board_delayed"] = True
            out["board_price_through"] = stamp
            try:
                stamp_dt = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
                delay_d = (now - stamp_dt).total_seconds() / 86400.0
                out["board_delay_days"] = round(delay_d, 1)
                if delay_d > surface["delay_budget_days"]:
                    msg = (
                        f"board reports itself delayed — prices as of {stamp},"
                        f" {delay_d:.1f}d old (budget {surface['delay_budget_days']}d)"
                    )
                    if bake_age_h <= surface["bake_budget_hours"]:
                        # The re-stamp trap: the page kept re-baking while the
                        # board froze — the failure mode Last-Modified alone
                        # cannot see (Jul-31→Aug-6 re-baked every day).
                        msg += "; page re-bakes are landing, board data is not"
                    problems.append(msg)
            except ValueError:
                problems.append(f"unparseable board price-through date {stamp!r}")

    if surface.get("asof_field") and fr.body is not None:
        try:
            doc = json.loads(fr.body)
        except ValueError as exc:
            # A body that is not JSON is a transport-shaped failure, not a
            # staleness one: an HTML error shell, a half-written file mid-rsync,
            # or a login page served in place of the payload all land here. It
            # escalates through the blindness counter — a wrong-shape body must
            # never be read as an outage verdict, in either direction.
            out["status"] = "indeterminate"
            out["detail"] = f"served body is not JSON ({exc})"
            return out
        # Facts are read from a payload that PARSED, before any budget runs and
        # regardless of what the budgets go on to decide. A stale board's
        # decomposition is exactly as interesting as a fresh one's — more so,
        # since it is the pass that has to explain itself.
        reader = FACT_READERS.get(surface.get("facts") or "")
        if reader is not None:
            out["facts"] = reader(doc)
        stamp = doc.get(surface["asof_field"]) if isinstance(doc, dict) else None
        for field in surface.get("required_false_fields", ()):
            value = doc.get(field) if isinstance(doc, dict) else None
            if value is not False:
                problems.append(
                    f"served payload {field!r} must be explicitly false "
                    f"({value!r}) — Prophet source freshness is not authoritative"
                )
        for field, expected in surface.get("required_values", {}).items():
            value = doc.get(field) if isinstance(doc, dict) else None
            if value != expected:
                problems.append(
                    f"served payload {field!r} must equal {expected!r} "
                    f"({value!r}) — Prophet source authority is not proven"
                )
        if not isinstance(stamp, str) or not stamp:
            # Well-formed JSON that cannot say when it is from IS a definitive
            # regression in the artifact, so it breaches rather than going
            # blind: the writer dropped the one field the store is judged on,
            # and a surface that cannot vouch for its own date must not read
            # as fresh.
            problems.append(
                f"served payload carries no usable {surface['asof_field']!r} field"
                f" ({stamp!r}) — the store cannot vouch for its own date"
            )
        else:
            out["asof"] = stamp
            budget = surface["asof_max_sessions_behind"]
            try:
                behind = sessions_behind(stamp, now)
            except Exception as exc:  # noqa: BLE001 — bad date / unimportable calendar
                out["status"] = "indeterminate"
                out["detail"] = (
                    f"cannot measure {stamp!r} against the NYSE calendar"
                    f" ({type(exc).__name__}: {exc})"
                )
                return out
            out["asof_sessions_behind"] = behind
            if behind > budget:
                msg = (
                    f"store as of {stamp} is {behind} completed NYSE session(s)"
                    f" behind the calendar (budget {budget})"
                )
                if bake_age_h is not None and bake_age_h <= BAKE_BUDGET_HOURS:
                    # The one-layer-down re-stamp trap: the file is landing on
                    # the VPS on schedule and its CONTENT is frozen (the
                    # 2026-08-05 candidates freeze under a daily-fresh page).
                    msg += "; the file is being re-published, the store is not"
                problems.append(msg)

    if problems:
        out["status"] = "stale"
        out["detail"] = "; ".join(problems)
    return out


# --------------------------------------------------------------------------- #
# CN Prophet Live (CN-PR-4) — the phase-aware check.
#
# Kept whole and separate from check_surface ON PURPOSE. The generic path budgets
# a stamp against a number of hours; this one asks a calendar what is owed right
# now and budgets minutes against the answer. Folding a session-phase clock into
# the 26h page logic would either force every page surface to carry a phase table
# it has no use for, or force this surface to express "quiet through lunch" as a
# budget wide enough to swallow a dead session. They are different questions.
# --------------------------------------------------------------------------- #
def cn_phase(now: datetime) -> dict:
    """Where ``now`` sits in the mainland session day, and what that phase owes.

    ``{phase, session, in_window, budget_min, error}``. ``budget_min`` is the
    minutes the artifact's ``built_at`` may lag IN THIS PHASE, or None when the
    phase owes no tick at all (pre-open warmup, the post-close watch tail).
    ``in_window`` is whether the surface is observed at all.

    ``error`` set ⇒ the clock or the calendar could not be read, and the caller
    must go INDETERMINATE. It deliberately leaves ``in_window`` True in that
    case: a sentinel that cannot place the phase must report its own blindness,
    not silently skip the surface — skipping is how a watchdog goes quiet
    forever and reads green while doing it.
    """
    out: dict = {"phase": "unknown", "session": None, "in_window": True,
                 "budget_min": None, "error": None}
    cst = _cst(now)
    if cst is None:
        out["error"] = "no Asia/Shanghai clock available (tzdata missing)"
        return out
    try:
        from lib import cn_calendar  # noqa: PLC0415 — lazy, see sessions_behind
        is_session = cn_calendar.is_session(cst.date())
    except Exception as exc:  # noqa: BLE001 — an unimportable calendar is blindness
        out["error"] = (
            f"cannot read the A-share calendar ({type(exc).__name__}: {exc})"
        )
        return out

    if not is_session:
        # Weekends and mainland holidays owe NOTHING. Golden Week is ~10 sessionless
        # calendar days and Spring Festival is longer; a surface that pages through
        # them is the false-positive machine the module's falsifier law forbids.
        out["phase"] = "weekend" if cst.weekday() >= 5 else "holiday"
        out["in_window"] = False
        return out

    out["session"] = cst.date().isoformat()
    hhmm = cst.strftime("%H:%M")            # zero-padded ⇒ lexical compare is time order
    if hhmm < CN_WATCH_OPEN_CST or hhmm >= CN_WATCH_CLOSE_CST:
        out["phase"] = "closed"
        out["in_window"] = False
    elif hhmm < "09:30":
        out["phase"] = "pre_open"           # one warmup pass ALLOWED, none owed
    elif hhmm < "11:30":
        out["phase"] = "morning"
        out["budget_min"] = CN_LIVE_SESSION_BUDGET_MIN
    elif hhmm < "13:00":
        # States freeze at the 11:30 anchor by contract — not ticking is correct.
        out["phase"] = "session_break"
        out["budget_min"] = CN_LIVE_LUNCH_BUDGET_MIN
    elif hhmm < "15:00":
        out["phase"] = "afternoon"
        out["budget_min"] = CN_LIVE_SESSION_BUDGET_MIN
    elif hhmm < "15:15":
        out["phase"] = "post_close"         # close observability + close board pass
        out["budget_min"] = CN_LIVE_SESSION_BUDGET_MIN
    else:
        # 15:15-17:00: the passes have stood down and the close SLA is judged in
        # here, so the artifact is still READ (a late board must be seeable) and
        # no tick is owed.
        out["phase"] = "post_close_watch"
    return out


def cn_watch_open(now: datetime) -> bool:
    """Whether the CN surface is observed at all on this pass."""
    return bool(cn_phase(now)["in_window"])


def check_cn_live_surface(surface: dict, fr: FetchResult, now: datetime) -> dict:
    """The CN runtime board → the same verdict shape every other surface returns.

    Same three verdicts and the same discipline: ``stale`` only on a definitive
    over-budget read, ``indeterminate`` for everything the sentinel cannot see,
    ``ok`` otherwise. The one thing this adds is a fourth honest state that the
    other surfaces do not need — QUIET — and it is reported as ``ok`` with a
    phase note rather than as a verdict of its own, because "nothing is owed" is
    genuinely not a problem and must not colour the report's ``ok`` fold.
    """
    out: dict = {
        "id": surface["id"],
        "kind": surface["kind"],
        "status": "ok",
        "bake_budget_hours": surface["bake_budget_hours"],
        "delay_budget_days": surface["delay_budget_days"],
        "bake_stamp": None,
        "bake_age_hours": None,
        "board_delayed": False,
        "board_price_through": None,
        "board_delay_days": None,
        "asof": None,
        "asof_sessions_behind": None,
        "absent": False,
        "detail": "",
        # The phase block. Published on staleness.json so a human reading the
        # estate can tell "quiet because the mainland is closed" from "quiet
        # because the sentinel is broken" without re-deriving the calendar.
        "cn": {"phase": "unknown", "session": None, "budget_min": None,
               "built_at": None, "built_age_min": None, "payload_seen": False,
               "first_close_board_at": None, "close_pending": None,
               "revision": None, "market_phase": None},
    }
    phase = cn_phase(now)
    out["cn"]["phase"] = phase["phase"]
    out["cn"]["session"] = phase["session"]
    out["cn"]["budget_min"] = phase["budget_min"]

    if phase["error"]:
        out["status"] = "indeterminate"
        out["detail"] = phase["error"]
        return out

    if not phase["in_window"]:
        out["detail"] = (
            f"quiet — {phase['phase']}: no mainland session pass is owed"
        )
        return out

    if fr.error or fr.status != 200:
        out["status"] = "indeterminate"
        out["detail"] = fr.error or f"HTTP {fr.status}"
        # Same narrow exemption as us_board_provisional: ONLY a genuinely
        # missing file. This lane has not shipped its first artifact yet, so
        # absence is the ordinary state — and first sight is recorded elsewhere
        # (CN_FIRST_SEEN_KEY) so the exemption cannot outlive the reason for it.
        if surface.get("absent_ok") and "FileNotFoundError" in (fr.error or ""):
            out["absent"] = True
            out["detail"] = "not published yet (absence is a normal state here)"
        return out

    try:
        doc = json.loads(fr.body or "")
    except ValueError as exc:
        # Transport-shaped, not staleness-shaped: a half-written file mid-rename,
        # an error shell, a truncated read. Blindness, never an outage verdict.
        out["status"] = "indeterminate"
        out["detail"] = f"live payload is not JSON ({exc})"
        return out
    if not isinstance(doc, dict):
        out["status"] = "indeterminate"
        out["detail"] = "live payload is not a JSON object"
        return out

    liveness = doc.get("liveness")
    liveness = liveness if isinstance(liveness, dict) else {}
    out["cn"].update({
        "payload_seen": True,
        "market_phase": doc.get("market_phase"),
        "close_pending": doc.get("close_pending"),
        "revision": doc.get("revision"),
        "first_close_board_at": liveness.get("first_close_board_at"),
    })

    problems: list[str] = []

    built_at = _instant(doc.get("built_at"))
    if built_at is None:
        # A payload that cannot say when it was built is a definitive regression
        # in the artifact, exactly like a prophet index with no source_asof: the
        # writer dropped the one field the surface is judged on. Breach, not
        # blindness — a board that cannot vouch for its own instant must never
        # read as fresh.
        problems.append(
            f"live payload carries no usable 'built_at' instant"
            f" ({doc.get('built_at')!r}) — the board cannot vouch for its own tick"
        )
    else:
        age_min = (now - built_at).total_seconds() / 60.0
        out["cn"]["built_at"] = built_at.isoformat()
        out["cn"]["built_age_min"] = round(age_min, 1)
        budget = phase["budget_min"]
        if budget is not None and age_min > budget:
            problems.append(
                f"runtime board last built {age_min:.1f} min ago"
                f" (budget {budget:.0f} min in phase {phase['phase']})"
            )

    stamp = doc.get(surface["asof_field"])
    if not isinstance(stamp, str) or not stamp:
        problems.append(
            f"live payload carries no usable {surface['asof_field']!r} field"
            f" ({stamp!r}) — the board cannot vouch for its own session"
        )
    else:
        out["asof"] = stamp
        try:
            behind = cn_sessions_behind(stamp, now)
        except Exception as exc:  # noqa: BLE001 — bad date / unimportable calendar
            out["status"] = "indeterminate"
            out["detail"] = (
                f"cannot measure {stamp!r} against the A-share calendar"
                f" ({type(exc).__name__}: {exc})"
            )
            return out
        out["asof_sessions_behind"] = behind
        budget_sessions = surface["asof_max_sessions_behind"]
        if behind > budget_sessions:
            problems.append(
                f"board session {stamp} is {behind} completed A-share session(s)"
                f" behind the calendar (budget {budget_sessions})"
            )

    if problems:
        out["status"] = "stale"
        out["detail"] = "; ".join(problems)
    else:
        out["detail"] = f"{phase['phase']} — board is ticking inside its budget"
    return out


_PVC_HREF_RE = re.compile(r"[A-Za-z0-9._/-]+(?:#[A-Za-z0-9._-]+)?\Z")
_PVC_MAX_AGE_SECONDS = 96 * 60 * 60
_PVC_CLIENT_CONTRACT = "wl1.provisional_cards/paintable-v1"


def _nested_value(node: object, path: tuple[str, ...] | list[str]) -> object:
    """A fail-dark lookup used only by the client-side SLA observation."""
    for step in path:
        if not isinstance(node, dict):
            return None
        node = node.get(step)
    return node


def _instant(value: object) -> datetime | None:
    """One timezone-qualified ISO instant, normalized to UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc)


def _finite_number(value: object) -> bool:
    # JavaScript's ``typeof value === 'number'`` rejects booleans; Python's
    # ``bool`` is an ``int`` subclass, so spell the same boundary explicitly.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an arbitrarily large JSON integer still fails dark
        return False


def _paintable_wl1_board_state(state: object, now: datetime) -> bool:
    """Whether W-L1d's client can qualify and render this payload now.

    This is the server-side twin of ``_pvcWanted`` / ``_pvcCards`` in
    ``templates/dashboard.html.j2``. It validates only facts the renderer itself
    refuses: current producer validity, ``rel == ahead``, a non-empty parallel
    ticker/card projection, finite close-pass legs, no forbidden score, and a
    same-site card link. Optional display fields remain optional because the
    renderer degrades them to an honest empty treatment.

    The DOM readback remains the browser's final authority. This predicate says
    the payload is capable of reaching that mount; it never claims a browser
    mounted a board that the renderer would reject before painting.
    """
    if not isinstance(state, dict) or now.tzinfo is None:
        return False
    now_utc = now.astimezone(timezone.utc)
    until = _instant(state.get("valid_until"))
    born = _instant(state.get("generated_at"))
    if until is None or now_utc > until:
        return False
    if born is None or (now_utc - born).total_seconds() > _PVC_MAX_AGE_SECONDS:
        return False
    if state.get("rel") != "ahead":
        return False

    board = state.get("board")
    if not isinstance(board, dict) or board.get("card_complete") is not True:
        return False
    tickers = board.get("tickers")
    cards = board.get("cards")
    if not isinstance(tickers, list) or not isinstance(cards, list):
        return False
    if not tickers or len(cards) != len(tickers):
        return False

    for ticker, card in zip(tickers, cards):
        if not ticker or not isinstance(card, dict):
            return False
        if str(card.get("tk") or "") != str(ticker):
            return False
        if not _finite_number(card.get("signal")):
            return False
        runway = card.get("runway")
        if runway is not None and not _finite_number(runway):
            return False
        if card.get("edge") is not None:
            return False
        href = card.get("href")
        if (
            not isinstance(href, str)
            or not href
            or len(href) > 200
            or _PVC_HREF_RE.fullmatch(href) is None
            or href.startswith("/")
            or ".." in href
        ):
            return False
    return True


def client_visible_session(fr: FetchResult | None, sla: dict,
                           now: datetime) -> str | None:
    """The session the READER can paint, or None when it shows nothing.

    Deliberately total and deliberately silent: an absent file, an unparseable
    one, a missing key, a key of the wrong shape, or a renderer-rejected board
    all answer None, because every one means the same thing to a browser —
    nothing paints. There is no error channel here ON PURPOSE. None is not a
    verdict about the estate; it only withholds an SLA stamp (see
    ``record_first_fresh``), and the caller must never turn it into a breach:
    this key is legitimately absent for most of every day and alarming on it
    would page daily by construction.
    """
    if fr is None or fr.error or fr.status != 200 or not fr.body:
        return None
    try:
        node = json.loads(fr.body)
    except ValueError:
        return None
    contract = sla.get("client_contract")
    if contract:
        # Unknown contracts fail dark. Treating an unimplemented validator as a
        # pass would restore the exact "timestamp means visible" bug this hook
        # exists to prevent.
        if contract != _PVC_CLIENT_CONTRACT:
            return None
        state = _nested_value(node, sla.get("client_state_path") or ())
        if not _paintable_wl1_board_state(state, now):
            return None
    session = _nested_value(node, sla.get("client_session_path") or ())
    return session if isinstance(session, str) and session else None


def evaluate(results: dict[str, FetchResult], now: datetime,
             surfaces: list[dict] | None = None,
             client_reads: dict[str, FetchResult] | None = None) -> dict:
    """All surfaces → this pass's report. ``ok`` here is the single-pass
    staleness verdict only; run() folds active-breach and blindness into the
    SERVED ok before publishing.

    ``client_reads`` maps a client artifact PATH to its read. Those reads are
    not surfaces and never join ``stale_surfaces``/``indeterminate_surfaces``;
    they only annotate the SLA surfaces they belong to with ``client_session``,
    the one thing the reader-side gate needs. Absent ⇒ every client session is
    unknown, which withholds SLA stamps rather than manufacturing verdicts —
    "I can't tell the reader saw it" must never score as a pass.
    """
    surfaces = SURFACES if surfaces is None else surfaces
    # ``_NOT_READ`` for a surface this pass did not observe (the CN live surface
    # outside its watch window — run() skips that read deliberately). It maps to
    # INDETERMINATE everywhere except the phase-aware check, which decides for
    # itself whether "not read" meant "nothing owed"; a surface can never reach
    # ``ok`` merely by being absent from the results dict.
    checked = {s["id"]: check_surface(s, results.get(s["id"], _NOT_READ), now)
               for s in surfaces}
    for s in surfaces:
        sla = s.get("sla") or {}
        if not sla.get("client_path"):
            continue
        # A renderer-qualified client session on an artifact that already
        # carries this surface's own ``asof`` — so publishing it in the public
        # staleness.json adds no market fact that was not already there, and it
        # makes "board fresh, reader dark" diagnosable instead of a silent
        # never-stamping SLA.
        checked[s["id"]]["client_session"] = client_visible_session(
            (client_reads or {}).get(sla["client_path"]), sla, now
        )
    stale = sorted(sid for sid, c in checked.items() if c["status"] == "stale")
    indeterminate = sorted(
        sid for sid, c in checked.items() if c["status"] == "indeterminate"
    )
    return {
        "generated_at": now.isoformat(),
        "ok": not stale,
        "stale_surfaces": stale,
        "indeterminate_surfaces": indeterminate,
        "surfaces": checked,
    }


# --------------------------------------------------------------------------- #
# The SLA record (W-L1a) — "on each of the last N sessions, when did surface X
# FIRST read fresh?"
#
# staleness.json and state.json are both OVERWRITTEN every 30-minute pass, so
# before this the estate could answer "is it fresh now" and could not answer
# "was it live by 18:30 ET", which is the only form the W-L1 gate takes. The
# record is deliberately the smallest thing that closes that gap: one stamp per
# (session, surface), written once, never rewritten.
#
# It MEASURES; it does not alert. A missed SLA shows up as a broken streak in
# the public summary, not as a page — arming an alarm on a brand-new lane is how
# sentinels get muted.
# --------------------------------------------------------------------------- #
def _et(stamp: datetime) -> datetime | None:
    """A UTC instant on the Eastern clock, or None when that is unknowable.

    Lazy import for the same reason lib.nyse_calendar is one (see the module
    docstring): a box with no tzdata must degrade this one measurement to
    "unknown" rather than take the watchdog down or, worse, silently answer in
    UTC — which would read 20:47Z as "20:47, missed the 18:30 deadline" on a
    session the board actually made with 100 minutes to spare.
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 — see docstring
        return stamp.astimezone(ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 — no tzdata must never fabricate a verdict
        return None


def _cst(stamp: datetime) -> datetime | None:
    """A UTC instant on the Asia/Shanghai clock, or None when that is unknowable.

    The mainland sibling of ``_et``, and it degrades the same way for the same
    reason. Asia/Shanghai has no DST, so a box with no tzdata could in principle
    be answered with a fixed +08:00 offset — and that is exactly the shortcut
    this refuses. A hardcoded offset is a SECOND clock: it would keep answering
    confidently if the mainland ever moved (it did, five times before 1991), and
    a watchdog whose clock cannot be wrong is a watchdog whose clock is never
    checked. Unknown here degrades the CN surface to INDETERMINATE — the
    sentinel reports its own blindness rather than budgeting against a phase it
    guessed at.
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 — see docstring
        return stamp.astimezone(ZoneInfo("Asia/Shanghai"))
    except Exception:  # noqa: BLE001 — no tzdata must never fabricate a phase
        return None


def record_first_fresh(record: dict, report: dict, now: datetime,
                       surfaces: list[dict] | None = None) -> dict:
    """Stamp the first definitively-fresh read of each SLA surface, per session.

    Keyed on the artifact's OWN ``as_of`` session, never on the wall clock. The
    two disagree for five hours every evening — a pass at 01:30Z is 20:30 ET the
    PREVIOUS day — so a UTC-date key would file half the evening's measurements
    under tomorrow and make the record unreadable exactly on the lane it exists
    to measure.

    Append-only: an existing (session, surface) stamp is returned untouched.
    """
    surfaces = SURFACES if surfaces is None else surfaces
    out = dict(record or {})
    sessions = dict(out.get("sessions") or {})
    changed = False

    for s in surfaces:
        sla = s.get("sla")
        if not sla:
            continue
        c = (report.get("surfaces") or {}).get(s["id"])
        # Only a DEFINITIVE fresh read counts. An indeterminate pass says
        # nothing about when the board landed, and stamping it would record a
        # time the artifact may not have existed at.
        if c is None or c["status"] != "ok" or not c.get("asof"):
            continue
        session = c["asof"]
        per = dict(sessions.get(session) or {})
        if s["id"] in per:
            continue                       # first is first, forever
        # THE READER, not the artifact. A fresh, on-time board that no browser
        # can see is not a met SLA — and the two really do come apart, because
        # the client-visible key is merged in by a later step that fails dark
        # (module docstring). Withholding the stamp is the whole mechanism: it
        # cannot page, and the session reads MISSED in the streak until the key
        # lands, at which point the stamp records THAT time. Fail-closed when
        # the client artifact was not read at all — an unmeasured reader is an
        # unmet gate, never a free pass.
        if sla.get("client_path") and c.get("client_session") != session:
            continue
        et = _et(now)
        # Met means BOTH: on the session's own ET day, and by the deadline. The
        # date half is not pedantry — a board published at 02:00 ET the next
        # morning reads "02:00 ≤ 18:30" and would score as a pass on a session
        # it missed entirely.
        met = (
            None if et is None
            else (et.date().isoformat() == session
                  and et.strftime("%H:%M") <= sla["by_et"])
        )
        # THE DECOMPOSITION (PR-C). Written HERE, in the same append-only act
        # that stamps the session, because these five instants are only jointly
        # meaningful at the moment of first visibility: `now` is the visible
        # edge and it is unrecoverable one pass later. Additive by construction —
        # every existing stamp keeps its four keys and simply carries no
        # `latency`, which is what makes the older record readable rather than
        # broken (see `sla_streak`, which asks for nothing added here).
        facts = c.get("facts") or {}
        generated_at = facts.get("board_generated_at")
        observed_at = facts.get("close_observed_at")
        per[s["id"]] = {
            "first_fresh_at": now.isoformat(),
            "first_fresh_et": et.strftime("%H:%M") if et else None,
            "by_et": sla["by_et"],
            "met": met,
            "latency": {
                # The two producer-side instants, verbatim and possibly null.
                "close_observed_at": observed_at,
                "board_generated_at": generated_at,
                # The sentinel's own first-fresh instant, under the name the
                # question is asked in. Same value as `first_fresh_at` above,
                # spelled twice ON PURPOSE: the SLA key answers "when did the
                # gate clear" and this one answers "when could a reader first
                # see it", and a future change to either must be forced to say
                # which of the two it means.
                "first_user_visible_at": now.isoformat(),
                "close_to_candidate_sec": _seconds_between(observed_at, generated_at),
                "candidate_to_visible_sec": _seconds_between(
                    generated_at, now.isoformat()
                ),
                # The error bar, published beside the figure it qualifies.
                "visible_resolution_sec": VISIBLE_RESOLUTION_SECONDS,
            },
            "coverage": facts.get("coverage") or {},
            "provenance": {
                "close_source": facts.get("close_source"),
                "close_basis": facts.get("close_basis"),
                "close_finalized": facts.get("close_finalized"),
            },
            "skipped": facts.get("skipped"),
        }
        sessions[session] = per
        changed = True

    if changed:
        for stale_key in sorted(sessions)[:-SLA_HISTORY_SESSIONS]:
            sessions.pop(stale_key, None)
        out["schema"] = FIRST_FRESH_SCHEMA
        out["sessions"] = sessions
        out["updated_at"] = now.isoformat()
    return out


def sla_streak(record: dict, surface_id: str, now: datetime,
               cap: int = SLA_REPORT_SESSIONS) -> tuple[int | None, list[dict]]:
    """(consecutive met sessions, per-session rows newest-first) for one surface.

    Walked over the EXCHANGE CALENDAR, never over the record's own keys. A
    session on which the board never published leaves no key at all, so counting
    recorded rows would step straight over the miss and report a five-session
    streak that never happened — the gate would pass on the strength of its own
    missing data. Anchored on ``expected_last_session`` so today's board is not
    judged until today is over.

    (None, []) when the calendar cannot be imported: unknown, never a verdict.
    """
    try:
        from lib import nyse_calendar  # noqa: PLC0415 — see module docstring
        last = nyse_calendar.expected_last_session(now)
    except Exception:  # noqa: BLE001
        return None, []

    sessions = (record or {}).get("sessions") or {}
    rows: list[dict] = []
    streak, broken = 0, False
    for n in range(cap):
        day = last if n == 0 else nyse_calendar.session_n_back(last, n)
        if day is None:
            break
        entry = (sessions.get(day.isoformat()) or {}).get(surface_id) or {}
        met = entry.get("met") is True
        rows.append({"session": day.isoformat(),
                     "first_fresh_et": entry.get("first_fresh_et"),
                     "met": met})
        if met and not broken:
            streak += 1
        elif not met:
            broken = True
    return streak, rows


def sla_summary(record: dict, now: datetime,
                surfaces: list[dict] | None = None) -> dict:
    """The compact public block: per SLA surface, the streak and recent sessions.

    Timestamps and verdicts only — no signal rows — which is what keeps it
    publishable in /live/staleness.json alongside everything else there.
    """
    surfaces = SURFACES if surfaces is None else surfaces
    out: dict = {}
    for s in surfaces:
        sla = s.get("sla")
        if not sla:
            continue
        streak, rows = sla_streak(record, s["id"], now)
        out[s["id"]] = {
            "by_et": sla["by_et"],
            "sessions_required": sla.get("sessions_required"),
            "consecutive_met": streak,
            "recent": rows,
        }
    return out


<<<<<<< HEAD
def public_report(report: dict) -> dict:
    """The pass report minus every PRIVATE annotation — what /live/staleness.json gets.

    Caddy serves that file to anyone, with no registration wall in front of it
    (it is the input the on-site staleness banner reads). The freshness verdicts
    there are deliberately public; the ``facts`` block is not, and the two only
    ride the same object because they are measured in the same pass.

    What ``facts`` carries is per-session coverage and provenance for artifacts
    that are themselves DEFAULT-DENY at the Caddy boundary — how many names the
    evening board admitted, which price source it used, how many the intraday
    probe budget cut. Whether any of that becomes free content is a paywall
    decision with an owner (#3391 made exactly this call for the board itself),
    and a watchdog that publishes it as a side effect of measuring has taken
    that decision away from its owner. Stripping is the fail-safe direction: an
    operator who wants a number here can read the private record, whereas a
    number already served to the internet cannot be recalled.

    Shallow-copies down to the per-surface dicts only, which is exactly as deep
    as the key being removed — the callers publish and discard.
    """
    out = dict(report)
    out["surfaces"] = {
        sid: {k: v for k, v in c.items() if k != "facts"} if isinstance(c, dict) else c
        for sid, c in (report.get("surfaces") or {}).items()
    }
    return out
=======
# --------------------------------------------------------------------------- #
# CN close-board SLA (CN-PR-4) — "was there a close board by 15:20 CST, or an
# honest reason there was not?"
#
# This is a CLOCK question, and the staleness budget above cannot ask it: an
# artifact can tick every five minutes all session, stay perfectly inside its
# 10-minute budget, and never produce a close board at all. The two verdicts are
# orthogonal and both are needed — one watches the heartbeat, this watches the
# deliverable.
#
# It PAGES, unlike the US SLA record beside it, and the difference is deliberate.
# The US record measures a lane that was brand new when it was written (arming an
# alarm on a brand-new lane is how sentinels get muted); this condition is a
# same-day miss on a board a reader is looking at, it is bounded to at most one
# alert per session by the same append-only stamp, and it has an explicit honest
# escape — a disclosed close_pending is not a breach.
# --------------------------------------------------------------------------- #
def cn_close_sla_alert(record: dict, report: dict, now: datetime,
                       surfaces: list[dict] | None = None) -> tuple[str | None, dict]:
    """(alert to send now or None, updated record). Never raises.

    Terminal verdicts only. A stamp is written when the session's question has
    an answer that cannot change:

      * met — ``liveness.first_close_board_at`` exists and is no later than
        15:15 CST ON THE SESSION'S OWN CST DAY. The date half is not pedantry:
        a board stamped 15:14 the NEXT morning reads "15:14 ≤ 15:15" and would
        score as a pass on a session it missed entirely (the exact trap
        record_first_fresh documents one clock over).
      * missed — the deadline has passed with no board, or with a late one, and
        the payload does not disclose why. ALERT.

    A disclosed ``close_pending`` (with ``revision == intraday_provisional``) is
    NOT terminal and stamps NOTHING: upstream being unresolved is a fact the
    reader has been told, and the honest state may still resolve into a board
    ten minutes later. Leaving the session unstamped is what lets a later pass
    still judge it once the disclosure drops — stamping "met" there would let a
    lane mute this alarm permanently by leaving a flag on.

    An artifact that has NEVER been seen stamps nothing either (``absent_ok``:
    absence alerts nothing until first sight). Once first sight is recorded, an
    artifact that is missing at the close is a miss like any other — the
    exemption covers a lane that has not shipped, not a lane that died.
    """
    out = dict(record or {})
    try:
        surfaces = SURFACES if surfaces is None else surfaces
        surface = next(
            (s for s in surfaces if s.get("close_sla") and s.get("phase_clock") == "cn"),
            None,
        )
        if surface is None:
            return None, out
        sla = surface["close_sla"]
        c = (report.get("surfaces") or {}).get(surface["id"]) or {}
        cn = c.get("cn") or {}

        # First sight, recorded once and never rewritten — the marker that ends
        # the absent_ok exemption for this lane.
        if cn.get("payload_seen") and not out.get(CN_FIRST_SEEN_KEY):
            out[CN_FIRST_SEEN_KEY] = {"at": now.isoformat(),
                                      "session": cn.get("session")}

        cst = _cst(now)
        if cst is None:
            return None, out          # no clock ⇒ no verdict, ever
        session = cn.get("session")
        if not session:
            return None, out          # not a session day (or the phase is unknown)
        if cst.strftime("%H:%M") < sla["by_cst"]:
            return None, out          # the deadline has not arrived yet

        stamps = dict(out.get(CN_CLOSE_SLA_KEY) or {})
        if session in stamps:
            return None, out          # first is first: one session alerts at most once

        board_raw = cn.get("first_close_board_at")
        board_at = _instant(board_raw)
        board_cst = _cst(board_at) if board_at is not None else None
        pending_ok = (
            cn.get("close_pending") is True
            and cn.get("revision") == sla["pending_revision"]
        )

        entry: dict = {"by_cst": sla["by_cst"], "board_by_cst": sla["board_by_cst"],
                       "checked_at": now.isoformat(),
                       "first_close_board_at": board_raw}
        reason: str | None = None

        if board_cst is not None:
            on_time = (board_cst.date().isoformat() == session
                       and board_cst.strftime("%H:%M") <= sla["board_by_cst"])
            entry["met"] = on_time
            entry["first_close_board_cst"] = board_cst.isoformat()
            if not on_time:
                reason = (
                    f"close board stamped {board_cst.isoformat()}, later than"
                    f" {sla['board_by_cst']} CST on session {session}"
                )
        elif board_raw is not None:
            entry["met"] = False
            reason = (
                f"liveness.first_close_board_at is present but unreadable"
                f" ({board_raw!r}) — an unparseable stamp is not a delivered board"
            )
        elif pending_ok:
            # Honest disclosure. No stamp, no alert, keep watching.
            return None, out
        elif not cn.get("payload_seen"):
            if not out.get(CN_FIRST_SEEN_KEY):
                return None, out      # the lane has never shipped — absent_ok
            entry["met"] = False
            reason = (
                "the runtime board is absent at the close on a session day, and"
                " this lane HAS published before"
                f" (first seen {(out.get(CN_FIRST_SEEN_KEY) or {}).get('at')})"
            )
        else:
            entry["met"] = False
            reason = (
                "no liveness.first_close_board_at and no honest disclosure"
                f" (close_pending={cn.get('close_pending')!r},"
                f" revision={cn.get('revision')!r}) — a silent miss"
            )

        if reason is not None:
            entry["reason"] = reason
        stamps[session] = entry
        for stale_key in sorted(stamps)[:-SLA_HISTORY_SESSIONS]:
            stamps.pop(stale_key, None)
        out[CN_CLOSE_SLA_KEY] = stamps
        out["updated_at"] = now.isoformat()
        if entry["met"]:
            return None, out

        return (
            "CN CLOSE BOARD MISSED — no close board for A-share session "
            f"{session} by {sla['by_cst']} CST ({now.isoformat()}).\n"
            f"  • {reason}\n"
            "  • The board is the deliverable; a ticking artifact is not a"
            " substitute for one. Diagnose the stage with"
            " `python -m scripts.cn_live_rescue --classify`.\n"
            "  • Upstream unresolved is allowed IF disclosed: close_pending=true"
            " with revision=intraday_provisional silences this by telling the"
            " reader the truth. Silence does not.",
            out,
        )
    except Exception as exc:  # noqa: BLE001 — a watchdog branch must never take the pass down
        print(
            f"sentinel: CN close-SLA check failed ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return None, dict(record or {})
>>>>>>> efcf483c819d (WIP checkpoint: CN Breathing Platform session-1 close — DO NOT MERGE)


def decide_alerts(report: dict, state: dict, now: datetime) -> tuple[list[str], dict]:
    """Report + prior counters → (alert messages to send now, next counters).

    Three alert classes:
      * BREACH — definitive staleness. First detection alerts immediately; a NEW
        surface joining the breach re-alerts immediately; otherwise the alert
        repeats every REALERT_HOURS. A breached surface that turns INDETERMINATE
        stays in the breach set (sticky) — blindness must never read as
        recovery, and a flapping fetch must not churn the set into an alert
        storm.
      * BLIND — a surface has been indeterminate BLIND_AFTER consecutive passes;
        same re-alert window.
      * RECOVERED — sent once, when every breached surface has read definitively
        fresh (status ok — not merely "stopped answering").
    """
    state = dict(state or {})
    blind_counts = dict(state.get("blind_counts") or {})
    alerts: list[str] = []

    # -- blindness counters -------------------------------------------------
    for sid, c in report["surfaces"].items():
        if c.get("absent"):
            # Not published yet ≠ the sentinel cannot see. Counting a
            # once-a-day artifact's ordinary pre-publication hours as blindness
            # would page every morning; the SLA record is what notices that an
            # evening board never arrived at all.
            blind_counts.pop(sid, None)
        elif c["status"] == "indeterminate":
            blind_counts[sid] = int(blind_counts.get(sid, 0)) + 1
        else:
            blind_counts.pop(sid, None)
    blind_now = sorted(s for s, n in blind_counts.items() if n >= BLIND_AFTER)

    def _window_open(last_iso: str | None) -> bool:
        if not last_iso:
            return True
        try:
            last = datetime.fromisoformat(last_iso)
        except ValueError:
            return True
        return (now - last).total_seconds() / 3600.0 >= REALERT_HOURS

    # -- breach (sticky through blindness) -----------------------------------
    prev = set(filter(None, (state.get("breach_key") or "").split(",")))
    stale = set(report["stale_surfaces"])
    indet = set(report["indeterminate_surfaces"])
    effective = stale | (prev & indet)

    if effective:
        new_surfaces = effective - prev
        if new_surfaces or _window_open(state.get("breach_alerted_at")):
            lines = [
                "STALE LIVE ESTATE — dead-man sentinel breach "
                f"({len(effective)} surface(s)):"
            ]
            for sid in sorted(effective):
                c = report["surfaces"].get(sid)
                if c is None:
                    continue
                note = c["detail"]
                if c["status"] == "indeterminate":
                    note = f"in breach, no definitive read this pass ({note})"
                lines.append(f"  • {sid}: {note}")
            lines.append(
                "Nightly render→merge→pull chain is not delivering. This check"
                " runs on the VPS and repeats every"
                f" {REALERT_HOURS:.0f}h until the estate is fresh."
            )
            alerts.append("\n".join(lines))
            state["breach_alerted_at"] = now.isoformat()
        state["breach_key"] = ",".join(sorted(effective))
    else:
        # Empty ONLY when every previously-breached surface read a definitive
        # non-stale verdict this pass — sticky membership above guarantees a
        # blind pass cannot land here.
        if prev and state.get("breach_alerted_at"):
            alerts.append(
                "RECOVERED — live estate fresh again (previously stale: "
                f"{','.join(sorted(prev))})."
            )
        state["breach_key"] = ""
        state.pop("breach_alerted_at", None)

    # -- blindness -----------------------------------------------------------
    blind_key = ",".join(blind_now)
    prev_blind_key = state.get("blind_key") or ""
    if blind_key:
        if blind_key != prev_blind_key or _window_open(state.get("blind_alerted_at")):
            details = "; ".join(
                f"{sid}: {report['surfaces'][sid]['detail']}"
                for sid in blind_now
                if sid in report["surfaces"]
            )
            alerts.append(
                "SENTINEL BLIND — no definitive read on "
                f"{blind_key} for {BLIND_AFTER}+ consecutive passes (~"
                f"{BLIND_AFTER * 0.5:.0f}h). Last errors: {details}. The estate may"
                " be down or unreachable; treat as an outage until a pass succeeds."
            )
            state["blind_alerted_at"] = now.isoformat()
        state["blind_key"] = blind_key
    else:
        if prev_blind_key and state.get("blind_alerted_at"):
            alerts.append(
                f"RECOVERED — sentinel can see {prev_blind_key} again."
            )
        state["blind_key"] = ""
        state.pop("blind_alerted_at", None)

    state["blind_counts"] = blind_counts
    state["last_run_at"] = now.isoformat()
    return alerts, state


# --------------------------------------------------------------------------- #
# Alert transports (all best-effort; ANY success counts as delivered)
# --------------------------------------------------------------------------- #
def _post_json(url: str, payload: dict, timeout: float = 20.0) -> bool:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 204)
    except Exception as exc:  # noqa: BLE001 — transport failure is a fact to report, not a crash
        print(f"sentinel: transport POST failed ({type(exc).__name__}: {exc})", file=sys.stderr)
        return False


def send_telegram(msg: str) -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not (token and chat):
        return False
    return _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat, "text": msg, "disable_web_page_preview": True},
    )


def send_discord(msg: str) -> bool:
    url = (
        os.environ.get("DISCORD_WEBHOOK_URL")
        or os.environ.get("DISCORD_WEBHOOK_WATCHLIST")
        or ""
    ).strip()
    if not url:
        return False
    return _post_json(url, {"content": msg[:1990]})


def send_email(msg: str, now: datetime, *, subject: str | None = None,
               template: str = "freshness_sentinel") -> bool:
    """Operator email through the estate's one send path (app.mailer, stdlib-only).

    Lazy, failure-guarded import: the sentinel must survive a broken app tree.
    idem_key = (message digest, REALERT_HOURS bucket): a crash-loop resending the
    SAME alert in one window collapses to a single email via the ledger, while a
    different alert in the same window (breach then recovery) still goes out.

    ``subject`` / ``template`` default to the freshness sentinel. The commercial-
    path sibling reuses this function with its own names so GATE-4 does not
    mint a second mail vendor.
    """
    to_addr = (
        os.environ.get("MAIL_SENTINEL_TO") or os.environ.get("MAIL_SUPPORT_TO") or ""
    ).strip()
    if not to_addr:
        return False
    try:
        from app import mailer  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"sentinel: app.mailer unavailable ({type(exc).__name__})", file=sys.stderr)
        return False
    import hashlib  # noqa: PLC0415 — stdlib, kept with its one caller

    bucket = int(now.timestamp()) // int(REALERT_HOURS * 3600)
    digest = hashlib.sha256(msg.encode()).hexdigest()[:12]
    subject = subject or "Mastermind freshness sentinel alert"
    status = mailer.send(
        template=template,
        cls="transactional",
        to_email=to_addr,
        subject=subject,
        html="",
        text=msg,
        idem_key=f"{template}:{bucket}:{digest}",
    )
    return status in ("sent", "duplicate")


def notify_operator(msg: str, now: datetime,
                    transports: list | None = None) -> list[str]:
    """Fan the alert across every configured transport; return who delivered."""
    transports = transports if transports is not None else [
        ("telegram", lambda m: send_telegram(m)),
        ("discord", lambda m: send_discord(m)),
        ("email", lambda m: send_email(m, now)),
    ]
    delivered = [name for name, fn in transports if fn(msg)]
    return delivered


def cn_close_transports(now: datetime) -> list:
    """The close-board SLA's fan — same three vendors, DIFFERENT dedup namespace.

    ``send_email`` folds (template, REALERT_HOURS bucket, message digest) into
    the mailer's idem_key, so a close-board alert that shared the freshness
    template could be swallowed as a "duplicate" of an unrelated staleness page
    sent in the same six-hour window — or swallow one. Its own template name
    keys it apart. No new vendor (the GATE-4 precedent,
    scripts/commercial_path_sentinel._transports).
    """
    return [
        ("telegram", send_telegram),
        ("discord", send_discord),
        ("email", lambda m: send_email(
            m, now, subject="Mastermind CN close-board SLA alert",
            template="cn_close_board_sla",
        )),
    ]


# --------------------------------------------------------------------------- #
# State I/O
# --------------------------------------------------------------------------- #
def _atomic_write_json(path: Path, payload: dict) -> None:
    """tmp + rename in the target dir — the live-plane publish convention, so a
    reader (Caddy, the future banner fetch) never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=1, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_state(state_dir: Path) -> dict:
    return _load_json(state_dir / "state.json")


def load_first_fresh(state_dir: Path) -> dict:
    """The SLA record. An unreadable file degrades to empty — which costs at most
    the streak, never a wrong verdict, because every stamp is re-derived from the
    surfaces themselves on the next fresh read."""
    return _load_json(state_dir / "first_fresh.json")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def facts_line(check: dict) -> str | None:
    """The operator's coverage/provenance line for one surface, or None.

    Stdout, not the served file — see ``public_report``. This is the disclosure
    the armed-pack surface exists to make (arming coverage is not budgeted here,
    so an unprinted count would be an unmeasured one) and the running commentary
    on the evening board's decomposition.

    ``?`` for every unmeasured field, never a blank and never a zero: a reader
    scanning journalctl has to be able to tell "the producer did not say" from
    "the producer said none".
    """
    facts = check.get("facts") or {}
    if not facts:
        return None
    parts: list[str] = []
    coverage = facts.get("coverage") or {}
    shown = " ".join(
        f"{name}={'?' if value is None else value}" for name, value in coverage.items()
    )
    if shown:
        parts.append(f"coverage {shown}")
    # Only the close-pass shape carries provenance; keyed on presence rather
    # than on the surface id so a second board-shaped surface inherits it.
    if "close_observed_at" in facts:
        observed, generated = facts["close_observed_at"], facts.get("board_generated_at")
        gap = _seconds_between(observed, generated)
        parts.append(
            f"close {observed or '?'} → built {generated or '?'}"
            + (f" (+{gap:.0f}s)" if gap is not None else "")
        )
        finalized = facts.get("close_finalized")
        parts.append(
            f"source {facts.get('close_source') or '?'}"
            f" basis {facts.get('close_basis') or '?'}"
            f" finalized {'?' if finalized is None else finalized}"
        )
    skipped = facts.get("skipped")
    if skipped:
        parts.append("skipped " + " ".join(f"{k}={v}" for k, v in sorted(skipped.items())))
    return " | ".join(parts) or None



def run(now: datetime, base: str, r2_base: str, public_dir: Path, state_dir: Path,
        dry_run: bool = False, fetcher=fetch, served_dir: Path | None = None,
        served_reader=read_served) -> int:
    served_dir = Path(DEFAULT_SERVED_DIR) if served_dir is None else served_dir
    results: dict[str, FetchResult] = {}
    for s in SURFACES:
        if s.get("phase_clock") == "cn" and not cn_watch_open(now):
            # Outside the mainland watch window there is nothing owed and
            # nothing to judge, so the pass does not manufacture an observation
            # it would then have to explain away. The check still runs (below)
            # and reports the phase — quiet is a REPORTED state, not a gap.
            results[s["id"]] = _NOT_READ
            continue
        if s["kind"] == "served_file":
            results[s["id"]] = served_reader(served_dir, s["path"])
            continue
        if s["kind"] == "live_file":
            # The daemon-written live plane (<public-dir>/live/…), not the
            # git-rsynced site tree. Same reader, different root — a walled
            # artifact is never read over HTTP, so the sentinel's verdict cannot
            # depend on the paywall answering correctly.
            results[s["id"]] = served_reader(public_dir, s["path"])
            continue
        root = r2_base if s["kind"] == "r2" else base
        # A body is fetched only when something must be PARSED out of it — the
        # delayed-board marker on a page, or a JSON watermark on an object. The
        # massive-store manifest is judged on its header alone and stays a HEAD:
        # a surface that needs no body must not pay for one on a lane that runs
        # every 30 minutes forever.
        results[s["id"]] = fetcher(
            root.rstrip("/") + s["path"],
            want_body=s["delay_budget_days"] is not None or bool(s.get("asof_field")),
        )

    # The reader's own artifacts, read off the same live plane. NOT surfaces:
    # these never reach evaluate()'s verdict sets, so a legitimately absent key
    # can only withhold an SLA stamp and can never page or go blind. Deduped by
    # path because several SLA surfaces may one day share one client artifact.
    client_reads: dict[str, FetchResult] = {}
    for s in SURFACES:
        client_path = (s.get("sla") or {}).get("client_path")
        if client_path and client_path not in client_reads:
            client_reads[client_path] = served_reader(public_dir, client_path)

    report = evaluate(results, now, client_reads=client_reads)
    for sid, c in sorted(report["surfaces"].items()):
        if c.get("asof"):
            label, content = "store", (
                f"asof@{c['asof']} ({c['asof_sessions_behind']} session(s) behind)"
            )
        else:
            label = "board"
            content = "delayed@" + c["board_price_through"] if c["board_delayed"] else "current"
        print(
            f"{sid}: {c['status']}"
            f" | bake {c['bake_age_hours'] if c['bake_age_hours'] is not None else '?'}h"
            f" | {label} {content}"
            # The line that makes a dark surface diagnosable rather than a
            # mysteriously never-advancing streak: "board fresh, reader DARK" is
            # the exact shape of the failure this condition exists to catch.
            + (f" | reader {c['client_session'] or 'DARK'}"
               if "client_session" in c else "")
            + (f" | {c['detail']}" if c["detail"] else "")
        )
        extra = facts_line(c)
        if extra:
            print(f"  {sid}: {extra}")

    if dry_run:
        # Read the SLA record without stamping it — this is the operator's lever
        # for evaluating the W-L1 gate ("five consecutive green sessions")
        # without perturbing the very measurement being read.
        for sid, s in sorted(sla_summary(load_first_fresh(state_dir), now).items()):
            print(f"{sid}: SLA by {s['by_et']} ET | {s['consecutive_met']} consecutive"
                  f" of {s['sessions_required']} required"
                  + "".join(f"\n    {r['session']} {r['first_fresh_et'] or '--:--'}"
                            f" {'met' if r['met'] else 'MISSED'}" for r in s["recent"]))
        print("dry-run: no state written, no alert sent")
        return 0 if report["ok"] else 1

    alerts, new_state = decide_alerts(report, load_state(state_dir), now)

    # The CN close-board SLA rides the same record file and the same
    # alerts-before-state ordering. Computed here so its stamp is part of the
    # ONE first_fresh write below rather than a second file to keep in step.
    first_fresh = load_first_fresh(state_dir)
    cn_alert, first_fresh = cn_close_sla_alert(first_fresh, report, now)

    # ALERTS FIRST, state files second: a full disk or a permissions break on
    # /var/lib must never silence the alarm it should be raising.
    delivered_any = True
    for msg in alerts:
        delivered = notify_operator(msg, now)
        print(f"sentinel alert ({', '.join(delivered) or 'NO TRANSPORT DELIVERED'}):\n{msg}")
        if not delivered:
            delivered_any = False
    if cn_alert:
        cn_delivered = notify_operator(cn_alert, now, transports=cn_close_transports(now))
        print(f"sentinel alert ({', '.join(cn_delivered) or 'NO TRANSPORT DELIVERED'}):"
              f"\n{cn_alert}")
        if not cn_delivered:
            delivered_any = False
            alerts = [*alerts, cn_alert]   # so the undelivered notice below fires
    if alerts and not delivered_any:
        print(
            "sentinel: ALERT UNDELIVERED — configure TELEGRAM_BOT_TOKEN/"
            "TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL, or MAIL_SENTINEL_TO"
            " (+ MAIL_SMTP_*)",
            file=sys.stderr,
        )

    # The SERVED verdict is the honest tri-state fold: active breach holds
    # (sticky through blindness) and threshold blindness reads as not-ok — the
    # banner must never render "I can't tell" as "fresh".
    active_breach = sorted(filter(None, (new_state.get("breach_key") or "").split(",")))
    blind_now = sorted(
        s for s, n in (new_state.get("blind_counts") or {}).items() if n >= BLIND_AFTER
    )
    report["active_breach"] = active_breach
    report["blind_surfaces"] = blind_now
    report["ok"] = not active_breach and not blind_now
    report["alerting"] = {
        "breach_alerted_at": new_state.get("breach_alerted_at"),
        "blind_alerted_at": new_state.get("blind_alerted_at"),
    }

    # The SLA record rides the same pass but is a SEPARATE file: state.json is
    # rewritten wholesale every pass and this must not be, so mixing them would
    # put an append-only record inside an overwrite-only one.
    first_fresh = record_first_fresh(first_fresh, report, now)
    report["sla"] = sla_summary(first_fresh, now)

    for target, payload in (
        # public_report, never `report` — the private facts stop at the Caddy
        # boundary while the freshness verdicts cross it.
        (public_dir / "live" / "staleness.json", public_report(report)),
        (state_dir / "state.json", new_state),
        (state_dir / "first_fresh.json", first_fresh),
    ):
        try:
            _atomic_write_json(target, payload)
        except OSError as exc:
            # Next pass re-derives counters from scratch at worst (re-alert
            # rather than silence — the right failure direction).
            print(f"sentinel: could not write {target} ({exc})", file=sys.stderr)

    return 0 if report["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dead-man freshness sentinel (masterplan W1)")
    ap.add_argument("--now", default=None,
                    help="ISO clock override — the §0.1 simulated-dead-nightly drill")
    ap.add_argument("--base", default=os.environ.get("SENTINEL_BASE", DEFAULT_BASE))
    ap.add_argument("--r2-base", default=os.environ.get("SENTINEL_R2_BASE", DEFAULT_R2_BASE))
    ap.add_argument("--public-dir",
                    default=os.environ.get("SENTINEL_PUBLIC_DIR", DEFAULT_PUBLIC_DIR))
    ap.add_argument("--state-dir",
                    default=os.environ.get("SENTINEL_STATE_DIR", DEFAULT_STATE_DIR))
    ap.add_argument("--served-dir",
                    default=os.environ.get("SENTINEL_SERVED_DIR", DEFAULT_SERVED_DIR),
                    help="static root the edge serves (walled artifacts are read here)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.now:
        now = datetime.fromisoformat(args.now)
        # Naive stamps are UTC BY CONTRACT here (the repo-wide #2463 convention),
        # not local time. Without this, `--now 2026-08-08T05:00:00` from the
        # runbook silently means 05:00 in whatever zone the operator's shell is
        # in — an hours-wide shift in the very drill that is supposed to prove
        # the budgets, and it would read as a budget bug rather than a clock one.
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    else:
        now = datetime.now(timezone.utc)
    return run(
        now=now,
        base=args.base,
        r2_base=args.r2_base,
        public_dir=Path(args.public_dir),
        state_dir=Path(args.state_dir),
        served_dir=Path(args.served_dir),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
