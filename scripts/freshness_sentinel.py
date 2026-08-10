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
    requires that artifact to name the same session. The gate the record exists
    to measure is a READER question — "fresh picks live on the site by 18:30
    ET" — and the artifact the sentinel budgets for staleness is not always the
    one a browser consumes. For the close-pass board they are two different
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
        # masterplan §0 W-L1: live by 18:30 ET, five consecutive green sessions.
        "sla": {
            "by_et": "18:30",
            "sessions_required": 5,
            "client_path": "/live/prophet_live.json",
            "client_session_path": ("board_state", "board", "as_of"),
        },
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
# Pure evaluation core
# --------------------------------------------------------------------------- #
def check_surface(surface: dict, fr: FetchResult, now: datetime) -> dict:
    """One surface → {id, status ∈ ok|stale|indeterminate, ages, detail}."""
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


def client_visible_session(fr: FetchResult | None, sla: dict) -> str | None:
    """The session the READER'S artifact names, or None when it shows nothing.

    Deliberately total and deliberately silent: an absent file, an unparseable
    one, a missing key and a key of the wrong shape all answer None, because
    every one of them means the same thing to a browser — nothing paints. There
    is no error channel here ON PURPOSE. None is not a verdict about the estate,
    it only withholds an SLA stamp (see ``record_first_fresh``), and the caller
    must never be able to turn it into a breach: this key is legitimately absent
    for most of every day and alarming on it would page daily by construction.
    """
    if fr is None or fr.error or fr.status != 200 or not fr.body:
        return None
    try:
        node = json.loads(fr.body)
    except ValueError:
        return None
    for step in sla.get("client_session_path") or ():
        if not isinstance(node, dict):
            return None
        node = node.get(step)
    return node if isinstance(node, str) and node else None


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
    checked = {s["id"]: check_surface(s, results[s["id"]], now) for s in surfaces}
    for s in surfaces:
        sla = s.get("sla") or {}
        if not sla.get("client_path"):
            continue
        # A session date, and nothing else, on an artifact that already carries
        # this surface's own ``asof`` — so publishing it in the public
        # staleness.json adds no fact that was not already there, and it is what
        # makes "board fresh, reader dark" diagnosable instead of a silent
        # never-stamping SLA.
        checked[s["id"]]["client_session"] = client_visible_session(
            (client_reads or {}).get(sla["client_path"]), sla
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
        per[s["id"]] = {
            "first_fresh_at": now.isoformat(),
            "first_fresh_et": et.strftime("%H:%M") if et else None,
            "by_et": sla["by_et"],
            "met": met,
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


def send_email(msg: str, now: datetime) -> bool:
    """Operator email through the estate's one send path (app.mailer, stdlib-only).

    Lazy, failure-guarded import: the sentinel must survive a broken app tree.
    idem_key = (message digest, REALERT_HOURS bucket): a crash-loop resending the
    SAME alert in one window collapses to a single email via the ledger, while a
    different alert in the same window (breach then recovery) still goes out.
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
    status = mailer.send(
        template="freshness_sentinel",
        cls="transactional",
        to_email=to_addr,
        subject="Mastermind freshness sentinel alert",
        html="",
        text=msg,
        idem_key=f"freshness-sentinel:{bucket}:{digest}",
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
def run(now: datetime, base: str, r2_base: str, public_dir: Path, state_dir: Path,
        dry_run: bool = False, fetcher=fetch, served_dir: Path | None = None,
        served_reader=read_served) -> int:
    served_dir = Path(DEFAULT_SERVED_DIR) if served_dir is None else served_dir
    results: dict[str, FetchResult] = {}
    for s in SURFACES:
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
        results[s["id"]] = fetcher(
            root.rstrip("/") + s["path"], want_body=s["delay_budget_days"] is not None
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

    # ALERTS FIRST, state files second: a full disk or a permissions break on
    # /var/lib must never silence the alarm it should be raising.
    delivered_any = True
    for msg in alerts:
        delivered = notify_operator(msg, now)
        print(f"sentinel alert ({', '.join(delivered) or 'NO TRANSPORT DELIVERED'}):\n{msg}")
        if not delivered:
            delivered_any = False
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
    first_fresh = record_first_fresh(load_first_fresh(state_dir), report, now)
    report["sla"] = sla_summary(first_fresh, now)

    for target, payload in (
        (public_dir / "live" / "staleness.json", report),
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
