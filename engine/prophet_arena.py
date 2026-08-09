"""engine/prophet_arena.py — the Prophet Arena: champion-vs-challenger shadow harness.

WHY THIS EXISTS
---------------
The closed-plan record says intake policy — not geometry, not management — is the
binding accuracy constraint on Prophet US.  As of 2026-08-05 ``data/prophet/ledger.jsonl``
holds 16 closed plans: 12.5% win rate (2 of 16 with a positive stock result), mean
stock_result −5.03%, median −5.51%, and 9 of the 16 closed EXPIRED (rode the full
horizon to a −4.44% mean).  House law forbids changing the LIVE pick rule without
measured evidence plus operator ratification, and a one-off backtest of a re-slice is
not that evidence: the champion's own record accrues prospectively, so its challengers
must accrue the same way, on the same nights, against the same ruler.

The Arena manufactures that evidence CONTINUOUSLY.  Every night, K frozen challenger
policies re-slice the SAME nightly candidate artifact the live path just used into
shadow plan sets.  Each shadow plan is graded by the SAME closure rules the champion's
forward ledger uses, onto its own prospective per-policy ledger, with a scoreboard on
top.  Nothing here is a backtest and nothing here is a backfill — the ledgers start
empty and fill one night at a time, exactly as the champion's did.

ZERO LIVE-CHAIN INFLUENCE (fence, test-pinned)
----------------------------------------------
Nothing in the pick chain may import or read Arena output.  ``prophet_bridge``,
``us_board_rank`` and ``build_prophet`` are import-fenced by
``tests/test_prophet_arena.py::TestImportFence``.  The Arena reads the live artifact
and writes only ``data/prophet_arena/**`` and ``site/stockdata/prophet_arena.json``.
Every artifact is display tier with all four authority permissions false.  A policy
that wins here does not ship — it produces a scoreboard packet for the operator, and
the CHANGE ships as its own PR.  See ``research/PROPHET_ARENA_REGISTRATION.md`` §Promotion.

REUSE, NEVER REIMPLEMENT
------------------------
Selection admission, the sort key, the geometry and the id are the CHAMPION'S, called
through ``engine.prophet_bridge`` with modified inputs:

  * admission + champion order -> :func:`prophet_bridge.select_candidates` called with
    ``n=None``.  The result is the admitted population in
    champion order; C0 and the closure-grain C6 retain that full population, while
    registered selection challengers may re-order, restrict or explicitly re-cap it.
    The Arena never re-implements the filter.
  * geometry (invalidation / T1 / T2 / R)   -> :func:`prophet_bridge.compute_geometry`
  * plan id                                 -> ``prophet_bridge._make_id``
  * ticker+direction identity               -> :func:`prophet_bridge.plan_key`
  * run/price clocks                        -> ``_resolve_origination_clocks``
  * tier-native signal dates                -> ``_resolve_candidate_signal_dates``
  * the horizon leash                       -> ``prophet_bridge._load_stage_tilt_inputs``
                                               / ``_compute_stage_tilt`` (so a shadow
                                               plan on a Stage-2 ∩ EC-positive name
                                               carries the same 56d horizon the live
                                               plan would have, and C0 stays a true
                                               control).

DELIBERATE SCOPE OMISSION: shadow plans carry no option contract and no thesis prose.
The live forward ledger's ``option_result_pct`` is null on all 16 closed rows — options
are not part of the ruler — and thesis strings cannot change an outcome.  Resolving
either for every policy plan would spend render budget on fields the measurement never
reads.

THE RULER (one function, both sides)
------------------------------------
:func:`replay_closure` is the ONLY grader.  It mirrors
``scripts/build_prophet.py::_determine_outcome`` line for line — see that function's
docstring and the CONVENTION PINS block below.  The champion is graded by it too (C0),
so a champion-vs-challenger difference can never be a difference of rulers.

CONVENTION PINS (mirrored from scripts/build_prophet.py::_determine_outcome, L484-625)
---------------------------------------------------------------------------------------
  1. CLOSE-based, never touch-based.  Triggers compare daily CLOSES; an intraday spike
     through T1 that closes below it does not close the plan (build_prophet.py L519:
     "conservative (may miss intraday crosses)").
  2. STRICTLY AFTER the plan's price clock.  ``closes.index > clock_ts`` — the close
     whose price became ``entry`` is excluded because the plan was not live before it.
     No position exists until ``trigger`` confirms; an unconfirmed trigger that reaches
     the horizon closes ``NO_ENTRY`` with null P&L, exactly like the live ruler.
  3. SAME-DAY PRECEDENCE IS WORST-CASE-FIRST: invalidation, then T2, then T1 (L566-581).
     A bar that is simultaneously below invalidation and above T2 records INVALIDATED.
  4. FIRST-TRIGGER-CLOSES.  The scan breaks on the first bar that trips anything; a plan
     that touches T1 and later T2 is recorded T1_HIT forever (L502-506).
  5. EXPIRY IS CHECKED LAST WITHIN THE BAR, on CALENDAR days: ``(ts - clock_ts).days >=
     horizon_days`` (L599).  Not sessions — the 9 EXPIRED champion rows carry
     days_held 45/45/45/45/45/45/45/46/47.
  6. ``stock_result_pct = (close_price / entry - 1) * 100`` rounded to 4 (L611-612).
  7. ``days_held = close_date - price_basis_date`` in calendar days (L621).
  8. A frame that ends before price_basis_date + horizon leaves the plan OPEN indefinitely.
     That is correct behaviour, not a missed expiry (L509-511).

  ARENA-ADDED (C6 only, and the one convention with no champion line to mirror):
  9. The 21-session time stop is evaluated AFTER the three price triggers and BEFORE
     the calendar expiry check.  "21st session" counts POST-ENTRY-CLOCK BARS in the same
     frame the replay walks (1-based), NOT calendar days — the rule is about how long
     dead money is held, and sessions are the unit a holder experiences.  A bar that
     is both the 21st session and past the calendar horizon records ``time_stopped``,
     because the time stop is the earlier-firing rule of the two by construction
     (21 sessions ≈ 29-31 calendar days vs a 45d horizon).

FORWARD LEDGERS (house law)
---------------------------
``data/prophet_arena/price_basis_trigger_v2/<policy>.jsonl`` — one file per policy,
append-only, keep-first.  The top-level v1 ledgers are sealed evidence from the retired
formation-clock/no-trigger harness.  They remain byte-for-byte readable but are never
advanced, graded or included in the active scoreboard.
NIGHTLY IS THE SOLE ADVANCER: every append is gated on
``engine.ledger_lane.nightly_advance_enabled()`` (COLLECT_LANE=nightly).  A non-nightly
run computes and returns everything and writes NOTHING.

Keep-first is keyed on ``(policy, plan_id, kind)`` where kind ∈ {"open", "close"} — one
origination stamp and at most one closure row per shadow plan per policy.  Keying on
``(policy, plan_id)`` alone would make a closure unrecordable, since the origination row
already holds that key; within each kind the dedup is exactly ``(policy, plan_id)``.

NO BACKFILL.  The ledgers start empty on the night this ships.  A headline read is
withheld until a policy has ``HEADLINE_MIN_CLOSED`` (20) closed shadow plans.
"""
from __future__ import annotations

import json
import logging
import math
import os
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from engine import prophet_bridge as pb
from engine.ledger_lane import nightly_advance_enabled

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Schema / constants — FROZEN at registration.                                 #
# --------------------------------------------------------------------------- #
LEGACY_LEDGER_SCHEMA = "prophet_arena.ledger/v1"
LEDGER_SCHEMA = "prophet_arena.ledger/v2"
LEDGER_ERA = "price_basis_trigger_v2"
TEMPORAL_CONTRACT = "price_basis+trigger+tier_dates/v1"
SCOREBOARD_SCHEMA = "prophet_arena.scoreboard/v1"
REGISTRATION_DOC = "research/PROPHET_ARENA_REGISTRATION.md"

#: Closed shadow plans a policy needs before its record is read as a headline.
HEADLINE_MIN_CLOSED = 20

#: Frozen 2026-08-05 challenger-book size.  This is NOT the live champion's cap:
#: C0 is lossless as of 2026-08-08.  Selection challengers remain on their explicitly
#: registered 12-row book so their prospective ledgers do not change mid-experiment.
REGISTERED_CHALLENGER_CAP = 12

#: C4 — dispersion states and caps, frozen at registration.
DISPERSION_LEAN_IN = "lean_in"
DISPERSION_CAP_LEAN_IN = REGISTERED_CHALLENGER_CAP
DISPERSION_CAP_OTHERWISE = 6                    # the pre-2026-07-28 cap
DISPERSION_MAX_STALE_SESSIONS = 5

#: C3 — slots inside its registered 12-row challenger book reserved for Door W names.
DOOR_W_RESERVED_SLOTS = 4

#: C5 — full alignment on the SEA taxonomy axis.  ``align_class`` counts how many of the
#: OTHER two canon grids agreed at the event bar, so its MAXIMUM is 2 and 2 means fully
#: aligned (masterplan §taxonomy; Door W's own W3 leg uses the same ``align_class == 2``).
ALIGN_FULL_CLASS = 2
#: The live counterpart ``align_now`` counts how many of ALL THREE grids are bull right
#: now, so ITS full value is 3.  The two are NOT interchangeable and the gate must not
#: compare them to the same number — that would admit a 2-of-3 name as "fully aligned".
ALIGN_FULL_NOW = 3

#: C6 — the no-progress time stop, in POST-ENTRY-CLOCK SESSIONS (CONVENTION PIN 9).
TIME_STOP_SESSIONS = 21
OUTCOME_TIME_STOPPED = "time_stopped"

#: Outcomes the champion's own ledger can record (mirrored by the replay).
CHAMPION_OUTCOMES = ("T1_HIT", "T2_HIT", "INVALIDATED", "EXPIRED", "NO_ENTRY")

# WIN DEFINITION (see _stats): a win is a POSITIVE stock result, never a target label.
# The champion's single T1_HIT is its only positive row, and an EXPIRED row that happens
# to expire green is a win too.  Grading on the NUMBER rather than the outcome enum is
# what lets C6's added ``time_stopped`` outcome be compared without a special case.

#: The line every Arena surface carries.  The Arena reports; the operator decides.
STANDING_LINE_EN = (
    "shadow record — the live policy changes only by operator ratification"
)
STANDING_LINE_ZH = "影子记录 — 实盘策略仅在操作者批准后才会更改"


@dataclass(frozen=True)
class Policy:
    """One frozen challenger.  ``grain`` says WHERE it differs from the champion.

    ``selection`` policies pick a different set of names and are graded by the champion's
    closure rules.  ``closure`` policies pick the SAME names as C0 and differ only in how
    the plan exits — so their comparison against C0 is PER-PLAN PAIRED (same plan ids,
    same entries, different exits), never cohort-level.
    """

    key: str
    label_en: str
    label_zh: str
    grain: str                      # "selection" | "closure"
    time_stop_sessions: int | None  # closure knob; None = champion closure exactly
    rationale: str


POLICIES: tuple[Policy, ...] = (
    Policy(
        key="C0_champion_mirror",
        label_en="the live rule, mirrored",
        label_zh="实盘规则镜像",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "CONTROL. Exactly the live select_candidates on the night's artifact, with "
            "the same duplicate-id and open-plan suppression the live path applies. Also "
            "the harness-validity pin: C0's plan ids must match the live origination's "
            "ids exactly. A mismatch means the harness is reading a different world than "
            "the champion did, and the scoreboard says so rather than diverging quietly."
        ),
    ),
    Policy(
        key="C1_buy_soon_first",
        label_en="earlier entries first",
        label_zh="优先较早入场",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "Same admission, same champion sort — but act_level==2 rows are lifted above "
            "act_level==3 rows before it. The #4547 entry-ladder cells put buy_soon at "
            "+3.19pp per-name median excess at H=10 (n=31), the best NON-THIN cell, while "
            "buy_now read −0.48pp at H=10 on a THIN n=9 cell. The champion's "
            "act_level-descending tie-break prefers the more imminent entry — the cell "
            "that measured worse, on the thinner evidence."
        ),
    ),
    Policy(
        key="C3_door_w_union",
        label_en="washout turns added",
        label_zh="纳入超跌转折",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "The candidate pool becomes the champion pool UNION Door W "
            "(engine.prophet_doors.door_w_candidates) — the class that is invisible to "
            "intake because those names carry no entry signal at all, so no amount of "
            "re-ordering can ever reach them. The census behind it is a single-date one "
            "(2026-07-31): of 65 names in WASHOUT_TURN with 2D+3D+W all bullish, 61 were "
            "neither on the board nor cascade-eligible. Tests the operator's washout-turn "
            "thesis at PLAN grain rather than at screen grain."
        ),
    ),
    Policy(
        key="C4_dispersion_cap",
        label_en="book size follows dispersion",
        label_zh="持仓数量随离散度",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "Champion admission and order, re-sliced into the challenger's frozen 12-row "
            "book when data/dispersion/regime.json reads state 'lean_in' and 6 otherwise. "
            "The dial "
            "prints 'Selection pays — high dispersion' every night and has ZERO pick-chain "
            "consumers: prophet_bridge, build_prophet and us_board_rank contain no "
            "reference to it at all, and its one sizing consumer is clamped to a no-op in "
            "production. This is the cheapest possible test of whether it should size the "
            "challenger book. C0 itself remains lossless."
        ),
    ),
    Policy(
        key="C5_align2_gate",
        label_en="weekly-aligned only",
        label_zh="仅限周线同向",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "Champion selection restricted to names whose event-atlas weekly alignment "
            "reads fully aligned (align_class == 2, its maximum). The Signal Episode Atlas "
            "first read calls misalignment a negative marker against a pooled washout edge "
            "of +0.23pp (13w excess) — see the registration for exactly how much of that "
            "is published and how much is reproducible-but-unpublished. Intake ignores "
            "alignment entirely today. The gate is measured inside this challenger's "
            "registered 12-row book; C0 itself remains lossless."
        ),
    ),
    Policy(
        key="C6_time_stop_21",
        label_en="cut dead money at 21 sessions",
        label_zh="21个交易日止损离场",
        grain="closure",
        time_stop_sessions=TIME_STOP_SESSIONS,
        rationale=(
            "The same plan set as C0 — a CLOSURE policy, not a selection one. A shadow "
            "plan still below its entry at the close of its 21st session exits there. "
            "9 of the champion's 16 closed plans EXPIRED, riding the full horizon to a "
            "−4.44% mean (the whole closed book averages −5.03%); a no-progress time stop "
            "is the direct counterfactual. Because the entries are identical, C6-vs-C0 is "
            "compared PER-PLAN PAIRED, never as two cohorts."
        ),
    ),
    Policy(
        key="C7_buy_soon_admitted",
        label_en="almost-ready entries admitted",
        label_zh="纳入「即将买入」档",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "SUCCESSOR to C2_stage_ran_preferred (retired 2026-08-09). The A1 status class "
            "refuses buy_soon outright on the CN loser ledger (CN entry statuses graded worst-"
            "first: buy_soon 46.7% loser rate), while the US entry-ladder battery graded "
            "buy_soon the best NON-THIN US cell: +3.19pp per-name median excess at H=10, n=31, "
            "9.7% loser rate, #1 in ranked_non_thin_by_per_name_median. Two retrospective "
            "reads, one cell, opposite verdicts — the kind of question a prospective shadow "
            "record exists to answer. Admission-only: the probe relaxes the status leg for "
            "buy_soon rows alone; tone, band, tier, entry-signal presence and the champion's "
            "own ordering are untouched, so a buy_soon row must earn its slot by score."
        ),
    ),
)

POLICY_KEYS: tuple[str, ...] = tuple(p.key for p in POLICIES)
CHAMPION_KEY = "C0_champion_mirror"
_POLICY_BY_KEY: dict[str, Policy] = {p.key: p for p in POLICIES}


@dataclass(frozen=True)
class RetiredPolicy:
    """A key whose accrual STOPPED.  The ledger file is sealed in place — kept on disk,
    never advanced, its open stamps never graded — mirroring the sealed v1 era."""

    key: str
    label_en: str
    label_zh: str
    retired: str      # date
    reason: str
    successor: str | None


RETIRED_POLICIES: tuple[RetiredPolicy, ...] = (
    RetiredPolicy(
        key="C2_stage_ran_preferred",
        label_en="already-moving names first",
        label_zh="优先已启动个股",
        retired="2026-08-09",
        reason=(
            "the champion's admission moved from an act-level threshold to a status class "
            "(ANTICIPATION A1, 2026-08-09), which makes this policy's frozen widening — "
            "patching act_level, an input admission no longer reads — unable to admit "
            "anything; the status class itself now admits hold, the status that carried 47 "
            "of the 55 rows behind this policy's evidence, so the champion absorbed the "
            "bulk of the thesis and the leftover cells (extended n=8, topping n=0) are too "
            "thin to re-register today"
        ),
        successor="C7_buy_soon_admitted",
    ),
)

RETIRED_POLICY_KEYS: tuple[str, ...] = tuple(p.key for p in RETIRED_POLICIES)


# --------------------------------------------------------------------------- #
# Paths                                                                        #
# --------------------------------------------------------------------------- #
def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def arena_dir(repo_root: Path | None = None) -> Path:
    """``<repo>/data/prophet_arena``.

    Every path helper in this module takes the REPO root, never the data dir — the module
    writes under both ``data/`` and ``site/``, so one argument that means two different
    things is a defect waiting to happen.  (Note the neighbours disagree with each other:
    ``prophet_doors.door_w_candidates`` takes a repo root, ``event_atlas.live_state``
    takes a data dir; both are adapted at their call sites here.)
    """
    return (Path(repo_root) if repo_root is not None else _repo_root()) / "data" / "prophet_arena"


def ledger_path(policy_key: str, repo_root: Path | None = None) -> Path:
    """The active v2 ledger; sealed top-level v1 ledgers are never returned here."""
    return arena_dir(repo_root) / LEDGER_ERA / f"{policy_key}.jsonl"


def legacy_ledger_path(policy_key: str, repo_root: Path | None = None) -> Path:
    """The sealed pre-price-clock ledger, retained read-only for audit disclosure."""
    return arena_dir(repo_root) / f"{policy_key}.jsonl"


def scoreboard_path(repo_root: Path | None = None) -> Path:
    return arena_dir(repo_root) / "scoreboard.json"


def _warn(msg: str) -> None:
    """Bare-print a GitHub annotation.

    NOT a logger call: GitHub parses a workflow command only when "::" STARTS the line,
    and this module's logging format prefixes every record, which silently drops it.
    ``flush`` is load-bearing — stdout is block-buffered when piped in CI.
    """
    print(f"::warning title=prophet_arena::{msg}", flush=True)


# --------------------------------------------------------------------------- #
# Price frames — the SAME store ladder the live lifecycle grades on.           #
# --------------------------------------------------------------------------- #
_PRICE_SUBDIRS = ("data/baskets/ohlcv", "data/stocks")
_CLOSE_COLUMNS = ("close", "Close", "adj_close", "Adj Close")


def load_closes(ticker: str, repo_root: Path | None = None) -> pd.Series | None:
    """Daily closes for ``ticker``, or None.

    Mirrors ``build_prophet._load_price_history_for_management`` (store ladder) and
    ``_determine_outcome``'s close-column resolution, so the Arena grades on exactly the
    series the live ledger grades on.  Never raises.
    """
    root = repo_root if repo_root is not None else _repo_root()
    for sub in _PRICE_SUBDIRS:
        p = Path(root) / sub / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            if not isinstance(df.index, pd.DatetimeIndex):
                for c in ("date", "Date"):
                    if c in df.columns:
                        df = df.set_index(c)
                        break
            df.index = pd.to_datetime(df.index)
            for col in _CLOSE_COLUMNS:
                if col in df.columns:
                    s = pd.to_numeric(df[col], errors="coerce").dropna().sort_index()
                    return s if len(s) else None
        except Exception as e:  # noqa: BLE001 — one unreadable name is never fatal
            log.debug("prophet_arena: price load failed for %s (%s)", ticker, e)
    return None


class PriceCache:
    """Per-run ticker -> closes cache shared by origination geometry and the replay.

    One parquet read per ticker per night no matter how many policies hold it.
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self._root = repo_root
        self._cache: dict[str, pd.Series | None] = {}

    def get(self, ticker: str) -> pd.Series | None:
        key = str(ticker)
        if key not in self._cache:
            self._cache[key] = load_closes(key, self._root)
        return self._cache[key]


# --------------------------------------------------------------------------- #
# THE RULER — closure replay.                                                  #
# --------------------------------------------------------------------------- #
def replay_closure(
    plan: dict,
    closes: "pd.Series | None",
    *,
    time_stop_sessions: int | None = None,
) -> dict | None:
    """Replay the champion's closure rules over daily closes.  Pure; never writes.

    Returns ``{"outcome", "close_date", "close_price", "stock_result_pct", "days_held",
    "sessions_held"}`` for a plan that has closed, or None while it is still open.

    ``closes`` must already be PIT-filtered to <= the run's asof by the caller (the live
    path filters in ``advance_ledger`` before calling ``_determine_outcome``; the Arena
    filters in :func:`grade_open_plans`).

    ``time_stop_sessions`` is the ONLY knob.  None reproduces the champion exactly.  An
    int adds CONVENTION PIN 9: a plan whose close is below entry at that post-clock
    session closes there as ``time_stopped``.

    Every convention here is pinned to a line of ``scripts/build_prophet.py`` in this
    module's docstring; read that block before changing anything in this function.
    """
    entry = plan.get("entry")
    # The live ruler starts at the close whose price supplied ``entry``.  A tier event
    # may precede that close, while T3 deliberately has no signal_date at all.  Reading
    # signal_date here would therefore either scan pre-origination bars or make every
    # valid T3 shadow immortal.  ``plan_clock_date`` also retains the legacy fallback.
    clock_date_str = pb.plan_clock_date(plan)
    if entry is None or clock_date_str is None or closes is None or not len(closes):
        return None

    direction = plan.get("direction", "BULL")
    invalidation = plan.get("invalidation")
    targets = plan.get("targets") or []
    t1 = targets[0] if len(targets) > 0 else None
    t2 = targets[1] if len(targets) > 1 else None
    horizon_days = plan.get("horizon_days", pb.HORIZON_DAYS_DEFAULT)
    trigger = plan.get("trigger")

    try:
        clock_ts = pd.Timestamp(clock_date_str)
    except Exception:  # noqa: BLE001
        return None

    # PIN 2 — strictly after the entry-price clock.
    after = closes[closes.index > clock_ts]
    if not len(after):
        return None

    outcome: str | None = None
    close_ts = None
    close_price: float | None = None
    sessions_held: int | None = None
    # Legacy rows with no trigger predate the contract and are treated as confirmed at
    # the clock.  A present trigger must print before any P&L-bearing outcome can exist.
    triggered = trigger is None

    for session_idx, (ts, raw) in enumerate(after.items(), start=1):
        try:
            px = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(px):
            continue
        days = (ts - clock_ts).days

        if not triggered:
            if direction == "BULL":
                triggered = px >= float(trigger)
            else:
                triggered = px <= float(trigger)
            if not triggered:
                if days >= horizon_days:
                    outcome = "NO_ENTRY"
                    close_ts = ts
                    close_price = None
                    sessions_held = session_idx
                    break
                continue
            # The confirmation bar is itself eligible for stop/target evaluation.

        # PIN 3 — worst case first, then T2, then T1.  PIN 4 — first trigger closes.
        if direction == "BULL":
            if invalidation is not None and px <= invalidation:
                outcome = "INVALIDATED"
            elif t2 is not None and px >= t2:
                outcome = "T2_HIT"
            elif t1 is not None and px >= t1:
                outcome = "T1_HIT"
        else:  # BEAR
            if invalidation is not None and px >= invalidation:
                outcome = "INVALIDATED"
            elif t2 is not None and px <= t2:
                outcome = "T2_HIT"
            elif t1 is not None and px <= t1:
                outcome = "T1_HIT"

        # PIN 9 — arena-added, C6 only. After the price triggers, before calendar expiry.
        if outcome is None and time_stop_sessions is not None:
            if session_idx >= int(time_stop_sessions) and entry and px < float(entry):
                outcome = OUTCOME_TIME_STOPPED

        # PIN 5 — expiry last within the bar, on CALENDAR days.
        if outcome is None and days >= horizon_days:
            outcome = "EXPIRED"

        if outcome is not None:
            close_ts = ts
            close_price = px
            sessions_held = session_idx
            break

    if outcome is None or close_ts is None:
        return None

    # PIN 6 — signed percent against the plan's entry.
    stock_result_pct: float | None = None
    if close_price is not None and entry and float(entry) > 0:
        stock_result_pct = round((close_price / float(entry) - 1.0) * 100.0, 4)

    # PIN 7 — calendar days held.
    close_date = close_ts.date()
    days_held: int | None = None
    try:
        days_held = (close_date - clock_ts.date()).days
    except Exception:  # noqa: BLE001
        days_held = None

    return {
        "outcome": outcome,
        "close_date": close_date.isoformat(),
        "close_price": (
            round(float(close_price), 4) if close_price is not None else None
        ),
        "stock_result_pct": stock_result_pct,
        "days_held": days_held,
        "sessions_held": sessions_held,
    }


# --------------------------------------------------------------------------- #
# Policy inputs — every one fail-open, every one counted.                      #
# --------------------------------------------------------------------------- #
def _act_level(row: dict) -> int:
    es = row.get("entry_signal") or {}
    try:
        return int(es.get("act_level") or 0)
    except (TypeError, ValueError):
        return 0


def buy_soon_widened(standouts: dict, probe_status: str = "hold") -> list[dict]:
    """The champion's admitted pool WITH buy_soon rows admitted — champion order, uncapped.

    C7's one-leg relaxation, the same probe idiom C2 used against the act_level gate
    (retired 2026-08-09 — see the registration doc): a COPY of the artifact is built in
    which only the buy_soon rows' entry status is lifted to an admitted value, and
    ``pb.select_candidates`` judges the copy — so tone, band, tier, entry-signal presence
    and the champion's ordering all remain the champion's own code.  The rows returned are
    the ORIGINAL, unpatched dicts; the patch is an admission probe, never plan material.

    ``probe_status`` is mechanically irrelevant to selection today — admission class is
    receipts-only and the sort key never reads status — and the invariance is test-pinned
    so a future class-dependent selection change re-opens this choice loudly rather than
    silently.  It must name an ADMITTED status; anything else is a construction error.
    """
    if probe_status not in pb.ADMITTED_STATUSES:
        raise ValueError(f"probe_status must be an admitted status, got {probe_status!r}")
    buys = standouts.get("buy") or []
    originals: dict[str, dict] = {str(r.get("ticker")): r for r in buys}
    patched: list[dict] = []
    for row in buys:
        if pb.entry_status(row) == "buy_soon":
            probe = dict(row)
            es = dict(row.get("entry_signal") or {})
            es["status"] = probe_status
            probe["entry_signal"] = es
            patched.append(probe)
        else:
            patched.append(row)
    shadow = dict(standouts)
    shadow["buy"] = patched
    admitted = pb.select_candidates(shadow, n=None)
    return [originals[str(r.get("ticker"))] for r in admitted]


def read_dispersion_state(
    asof: str, repo_root: Path | None = None
) -> tuple[int, dict]:
    """C4's cap plus the receipt saying WHICH mode fired.

    Returns ``(cap, receipt)``.  Fails OPEN to C4's registered lean-in cap on every
    unhappy path —
    absent file, unreadable JSON, null state, or a state older than
    ``DISPERSION_MAX_STALE_SESSIONS``.  The mode is always recorded, so "the cap was 12"
    never has to be guessed between "lean_in fired" and "the dial was missing".

    STALENESS UNIT: business days between the artifact's ``as_of`` and the run's asof
    (``numpy.busday_count``).  Market holidays are business days but not sessions, so
    this OVER-counts elapsed sessions slightly and therefore declares staleness slightly
    EARLY — which fails open, the safe direction for a policy that must never quietly
    size a book off a dead dial.
    """
    root = repo_root if repo_root is not None else _repo_root()
    path = Path(root) / "data" / "dispersion" / "regime.json"
    receipt: dict[str, Any] = {
        "mode": None,
        "state": None,
        "artifact_as_of": None,
        "stale_sessions": None,
        "cap": DISPERSION_CAP_LEAN_IN,
        "path": "data/dispersion/regime.json",
    }
    if not path.exists():
        receipt["mode"] = "fail_open_absent"
        return DISPERSION_CAP_LEAN_IN, receipt
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        receipt["mode"] = "fail_open_unreadable"
        receipt["reason"] = f"{type(e).__name__}"
        return DISPERSION_CAP_LEAN_IN, receipt

    state = payload.get("state")
    receipt["state"] = state
    receipt["artifact_as_of"] = payload.get("as_of")
    if state is None:
        receipt["mode"] = "fail_open_null_state"
        return DISPERSION_CAP_LEAN_IN, receipt

    try:
        import numpy as np  # noqa: PLC0415

        stale = int(
            np.busday_count(
                pd.Timestamp(str(payload.get("as_of"))[:10]).date(),
                pd.Timestamp(str(asof)[:10]).date(),
            )
        )
    except Exception as e:  # noqa: BLE001
        receipt["mode"] = "fail_open_undatable"
        receipt["reason"] = f"{type(e).__name__}"
        return DISPERSION_CAP_LEAN_IN, receipt
    receipt["stale_sessions"] = stale
    if stale > DISPERSION_MAX_STALE_SESSIONS:
        receipt["mode"] = "fail_open_stale"
        return DISPERSION_CAP_LEAN_IN, receipt

    if str(state) == DISPERSION_LEAN_IN:
        receipt["mode"] = "lean_in"
        receipt["cap"] = DISPERSION_CAP_LEAN_IN
        return DISPERSION_CAP_LEAN_IN, receipt
    receipt["mode"] = "not_lean_in"
    receipt["cap"] = DISPERSION_CAP_OTHERWISE
    return DISPERSION_CAP_OTHERWISE, receipt


class AtlasGate:
    """C5's per-name weekly-alignment read, cached, fail-open-to-EXCLUDED with counts.

    ``engine.event_atlas.live_state`` returns a top-level ``align_now`` (how many of the
    THREE canon grids are bull right now, 0-3) and, per grid, an ``align_class`` (how many
    of the OTHER two grids were bull at that grid's latest event, 0-2).  They are DIFFERENT
    MEASURES WITH DIFFERENT MAXIMA — comparing both to the literal 2 would silently admit a
    2-of-3 name as "fully aligned" — so each is compared to its own full value and the
    choice is RECORDED per name rather than collapsed:

      1. PRIMARY — the weekly ("W") grid's ``align_class == ALIGN_FULL_CLASS`` (2).  This is
         the SEA taxonomy axis the alignment read is built on, and the same leg Door W's own
         W3 uses.
      2. FALLBACK — when the name has no weekly event on record, ``align_now ==
         ALIGN_FULL_NOW`` (3, all three grids bull now).  This is a LIVE-state proxy for an
         AT-EVENT measure, not the same quantity, so it is counted separately in
         ``admitted_via_fallback`` and the scoreboard never presents it as the primary read.

    A name the atlas cannot read at all is EXCLUDED and counted in ``excluded_unreadable`` —
    the gate never admits on ignorance.
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self._root = repo_root
        self._cache: dict[str, tuple[bool, str]] = {}
        self.counts: dict[str, int] = {
            "admitted": 0,
            "admitted_via_fallback": 0,
            "excluded_misaligned": 0,
            "excluded_unreadable": 0,
        }

    def _evaluate(self, ticker: str) -> tuple[bool, str]:
        try:
            from engine import event_atlas  # noqa: PLC0415

            state = event_atlas.live_state(
                ticker,
                data_root=(Path(self._root) / "data") if self._root is not None else None,
            )
        except Exception as e:  # noqa: BLE001
            log.debug("prophet_arena: atlas read failed for %s (%s)", ticker, e)
            return False, "unreadable"
        if not isinstance(state, dict):
            return False, "unreadable"

        weekly = (state.get("grids") or {}).get("W")
        if isinstance(weekly, dict) and weekly.get("align_class") is not None:
            try:
                return (int(weekly["align_class"]) >= ALIGN_FULL_CLASS), "weekly_align_class"
            except (TypeError, ValueError):
                pass

        align_now = state.get("align_now")
        if align_now is not None:
            try:
                return (int(align_now) >= ALIGN_FULL_NOW), "fallback_align_now"
            except (TypeError, ValueError):
                pass
        return False, "unreadable"

    def admits(self, ticker: str) -> bool:
        key = str(ticker)
        if key not in self._cache:
            self._cache[key] = self._evaluate(key)
        ok, basis = self._cache[key]
        if basis == "unreadable":
            self.counts["excluded_unreadable"] += 1
        elif ok:
            self.counts["admitted"] += 1
            if basis == "fallback_align_now":
                self.counts["admitted_via_fallback"] += 1
        else:
            self.counts["excluded_misaligned"] += 1
        return ok

    def receipt(self) -> dict:
        out = dict(self.counts)
        out["basis"] = (
            "event_atlas weekly align_class == 2 (its full value), falling back to "
            "align_now == 3 (its full value) when the name has no weekly event on record; "
            "a name the atlas cannot read is excluded, never admitted"
        )
        return out


def door_w_rows(
    prices: PriceCache, repo_root: Path | None = None
) -> tuple[list[dict], dict]:
    """Door W receipts mapped into candidate-shaped rows, plus a disclosure.

    The mapping is deliberately MINIMAL and is the one construction choice in the Arena
    that manufactures a field rather than reading one: Door W names carry no entry signal
    at all — that is precisely why intake cannot see them — so an ``entry_signal`` is
    synthesized with ``act_level = 2`` to make them plan-able.  Nothing else is invented:

      * ``entry.spot``  = the last close from the SAME price frame the replay grades on
        (never a Door W field), so entry and exit are quoted from one source.
      * ``atr_pct``     = None — geometry falls back to the champion's 20-day swing low.
      * conviction      = null score / null band.  ``select_candidates`` reads a null
        score as 0 and a null band as not-"low", so these rows are admitted rather than
        scored, and they never borrow a champion rank they did not earn.

    A name whose closes are unreadable is SKIPPED and counted — it has no entry price and
    therefore no geometry.  Returns ``(rows, disclosure)``; never raises.
    """
    disclosure: dict[str, Any] = {
        "ok": True,
        "candidates": 0,
        "rows": 0,
        "skipped_no_prices": 0,
        "skipped_tickers": [],
        "reason": None,
    }
    try:
        from engine.prophet_doors import door_w_candidates  # noqa: PLC0415

        # door_w_candidates takes the REPO root (it appends "/data" itself via
        # prophet_doors.data_root) — unlike event_atlas.live_state, which takes the
        # data dir. Both adapters live here so neither convention leaks.
        result = door_w_candidates(Path(repo_root) if repo_root is not None else None)
    except Exception as e:  # noqa: BLE001
        disclosure["ok"] = False
        disclosure["reason"] = f"door_w unavailable ({type(e).__name__})"
        _warn(f"Door W unavailable ({type(e).__name__}) — C3 ran as champion-only tonight")
        return [], disclosure

    candidates = (result or {}).get("candidates") or []
    disclosure["candidates"] = len(candidates)
    disclosure["door_w_disclosure"] = (result or {}).get("disclosure")

    rows: list[dict] = []
    skipped: list[str] = []
    for entry in candidates:
        try:
            depth_key, ticker, receipt = entry[0], str(entry[1]), entry[2]
        except Exception:  # noqa: BLE001
            continue
        closes = prices.get(ticker)
        if closes is None or not len(closes):
            skipped.append(ticker)
            continue
        try:
            spot = float(closes.iloc[-1])
        except (TypeError, ValueError):
            skipped.append(ticker)
            continue
        if not math.isfinite(spot) or spot <= 0:
            skipped.append(ticker)
            continue
        rows.append({
            "ticker": ticker,
            "dir": "up",
            "entry_signal": {
                "act_level": 2,
                "spot": spot,
                "atr_pct": None,
                "status": "door_w",
                "chase_above": None,
            },
            "conviction": {"score": None, "band": None},
            "hold": {},
            "_arena_source": "door_w",
            "_arena_door_w": {
                "depth_sort_key": depth_key if math.isfinite(float(depth_key)) else None,
                "weeks_since_cross": receipt.get("weeks_since_cross"),
                "depth_pctile": receipt.get("depth_pctile"),
                "align_class": receipt.get("align_class"),
                "data_through": receipt.get("data_through"),
            },
        })

    disclosure["rows"] = len(rows)
    disclosure["skipped_no_prices"] = len(skipped)
    disclosure["skipped_tickers"] = sorted(skipped)
    return rows, disclosure


# --------------------------------------------------------------------------- #
# Selection — every policy is a transform of the champion's admitted list.     #
# --------------------------------------------------------------------------- #
def admitted_pool(standouts: dict) -> list[dict]:
    """The champion's ADMITTED population, in champion order, uncapped.

    ``select_candidates(..., n=None)`` is the same lossless ordering consumed by live
    ``originate_plans``.  The Arena therefore never re-implements the admission rule: a
    change to the champion's filter propagates to every policy automatically.
    """
    return pb.select_candidates(standouts, n=None)


def select_for_policy(
    policy_key: str,
    standouts: dict,
    *,
    cap: int = REGISTERED_CHALLENGER_CAP,
    door_rows: list[dict] | None = None,
    atlas: "AtlasGate | None" = None,
    dispersion_cap: int | None = None,
) -> tuple[list[dict], dict]:
    """Rows this policy would originate tonight, plus its receipts.

    Selection only — suppression (existing ids / open plans) and geometry come later, in
    :func:`originate_shadow_plans`, exactly as they do on the live path.
    """
    pool = admitted_pool(standouts)
    is_lossless_mirror = policy_key in (CHAMPION_KEY, "C6_time_stop_21")
    receipts: dict[str, Any] = {
        "admitted": len(pool),
        "cap": None if is_lossless_mirror else cap,
        "cap_applied": not is_lossless_mirror,
    }

    if policy_key == "C0_champion_mirror":
        receipts["selection_basis"] = "lossless live champion mirror"
        receipts["truncated"] = 0
        return pool, receipts

    if policy_key == "C1_buy_soon_first":
        # act_level==2 first, the CHAMPION'S OWN sort key within each group. The secondary
        # leg is pb._selection_sort_key itself rather than a reliance on sort stability
        # over an already-ordered list — same result here, but it stays correct if the
        # pool is ever handed over in another order.
        rows = sorted(
            pool, key=lambda r: (0 if _act_level(r) == 2 else 1, pb._selection_sort_key(r))
        )
        receipts["act_level_2"] = sum(1 for r in pool if _act_level(r) == 2)
        receipts["lifted"] = sum(1 for r in rows[:cap] if _act_level(r) == 2)
        return rows[:cap], receipts

    if policy_key == "C3_door_w_union":
        doors = list(door_rows or [])
        champion_tickers = {str(r.get("ticker")) for r in pool}
        # UNION DEDUPE: a name in both pools is ONE row and originates ONE plan. The
        # champion's row wins, because it carries the real entry signal and conviction.
        deduped = [d for d in doors if str(d.get("ticker")) not in champion_tickers]
        receipts["door_w_offered"] = len(doors)
        receipts["door_w_already_in_champion_pool"] = len(doors) - len(deduped)
        # Door W names rank among THEMSELVES by their own key (depth percentile ascending
        # — the deepest washout first), never by a champion score they do not have.
        deduped.sort(
            key=lambda d: (
                d["_arena_door_w"]["depth_sort_key"]
                if d["_arena_door_w"]["depth_sort_key"] is not None
                else float("inf"),
                str(d.get("ticker")),
            )
        )
        reserved = min(DOOR_W_RESERVED_SLOTS, len(deduped), cap)
        picks = pool[: cap - reserved] + deduped[:reserved]
        # Backfill either way so the book is always the full cap when the union can fill
        # it: a short champion pool takes more Door W names and vice versa.
        if len(picks) < cap:
            taken = {id(r) for r in picks}
            for extra in list(deduped[reserved:]) + list(pool[cap - reserved:]):
                if len(picks) >= cap:
                    break
                if id(extra) not in taken:
                    picks.append(extra)
                    taken.add(id(extra))
        receipts["door_w_reserved_slots"] = reserved
        receipts["door_w_selected"] = sum(
            1 for r in picks if r.get("_arena_source") == "door_w"
        )
        receipts["champion_rows_displaced"] = max(0, len(pool[:cap]) - len(
            [r for r in picks if r.get("_arena_source") != "door_w"]
        ))
        return picks, receipts

    if policy_key == "C4_dispersion_cap":
        effective = dispersion_cap if dispersion_cap is not None else cap
        receipts["cap"] = effective
        return pool[:effective], receipts

    if policy_key == "C5_align2_gate":
        gate = atlas if atlas is not None else AtlasGate()
        kept = [r for r in pool if gate.admits(str(r.get("ticker") or ""))]
        receipts["align_gate"] = gate.receipt()
        receipts["passed_gate"] = len(kept)
        receipts["excluded"] = len(pool) - len(kept)
        return kept[:cap], receipts

    if policy_key == "C6_time_stop_21":
        # CLOSURE-grain: the plan SET is C0's by construction. Its validity pin is that
        # equality, and its comparison against C0 is per-plan paired.
        receipts["selection_basis"] = "identical to lossless C0 by construction"
        receipts["truncated"] = 0
        return pool, receipts

    if policy_key == "C7_buy_soon_admitted":
        # ONE-LEG WIDENING, champion order — see buy_soon_widened() and the registration.
        widened = buy_soon_widened(standouts)
        pool_tickers = {str(r.get("ticker")) for r in pool}
        rows = widened[:cap]
        receipts["admitted_with_widening"] = len(widened)
        receipts["buy_soon_in_board"] = sum(
            1 for r in (standouts.get("buy") or []) if pb.entry_status(r) == "buy_soon"
        )
        receipts["buy_soon_admitted_by_widening"] = sum(
            1 for r in widened if str(r.get("ticker")) not in pool_tickers
        )
        receipts["buy_soon_selected"] = sum(
            1 for r in rows if str(r.get("ticker")) not in pool_tickers
        )
        receipts["widening"] = (
            "the status-class gate is relaxed for buy_soon rows only; tone, band, tier, "
            "entry-signal presence and the champion's own ordering stay the champion's"
        )
        return rows, receipts

    raise ValueError(f"unknown policy key: {policy_key!r}")


# --------------------------------------------------------------------------- #
# Origination — the champion's geometry and id, on the policy's rows.          #
# --------------------------------------------------------------------------- #
def originate_shadow_plans(
    policy_key: str,
    rows: list[dict],
    *,
    asof: str,
    standouts_asof: str,
    price_through: Any,
    source_delayed: Any,
    source_unknown: Any,
    source_basis: Any,
    existing_ids: set[str],
    active_keys: set[str] | None,
    prices: PriceCache,
    tilt_inputs: dict | None = None,
    panel_mixed_vintage: bool = False,
) -> tuple[list[dict], dict]:
    """Shadow plans for one policy's rows, using the bridge's geometry and id.

    Mirrors ``prophet_bridge.originate_plans``' skip ladder in order — duplicate id, open
    ticker+direction key, missing spot — so C0's emitted ids can equal the live path's.

    Clock and tier-date provenance are not challenger knobs.  Every policy calls the
    same fail-closed bridge resolvers as live origination, so C0/C6 can differ from the
    champion only by their registered policy and never because Arena guessed a date.

    ASYMMETRY, DELIBERATE: a champion-pool row whose geometry comes back null is still
    originated, because the live path originates it too (``validate_trade_plan`` does not
    require geometry); such a plan can only ever EXPIRE.  A DOOR W row whose geometry is
    null is SKIPPED AND COUNTED, per the policy's own registration — a synthesized row
    with no invalidation is not a plan, it is a ticker.
    """
    recorded_at, price_basis_date, clock_errors = pb._resolve_origination_clocks(
        price_through=price_through,
        recorded_asof=asof,
        panel_mixed_vintage=panel_mixed_vintage,
        source_delayed=source_delayed,
        source_unknown=source_unknown,
        source_basis=source_basis,
    )

    plans: list[dict] = []
    receipts: dict[str, Any] = {
        "offered": len(rows),
        "skipped_duplicate_id": 0,
        "skipped_open_plan": 0,
        "skipped_clock_provenance": 0,
        "skipped_no_spot": 0,
        "skipped_door_w_no_geometry": 0,
        "skipped_door_w_tickers": [],
        "recorded_at": recorded_at,
        "price_basis_date": price_basis_date,
        "clock_errors": list(clock_errors),
        "validation_failures": [],
    }
    seen_ids: set[str] = set()

    def _record_failure(
        *, ticker: str | None, plan_id: str | None, errors: list[str]
    ) -> None:
        receipts["validation_failures"].append({
            "ticker": ticker,
            "id": plan_id,
            "stage": "clock_provenance",
            "errors": [str(error) for error in errors],
        })

    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            _record_failure(
                ticker=None, plan_id=None, errors=["ticker is required"]
            )
            continue
        direction = "BULL"
        hold = row.get("hold") or {}
        anchor = hold.get("anchor")
        raw_formation_date = anchor if anchor else standouts_asof
        formation_date = pb._normalise_iso_date(raw_formation_date)
        if formation_date is None:
            _record_failure(
                ticker=ticker,
                plan_id=None,
                errors=[
                    f"formation_date {raw_formation_date!r} is not an ISO-8601 date"
                ],
            )
            continue
        plan_id = pb._make_id(ticker, direction, formation_date)

        if plan_id in existing_ids or plan_id in seen_ids:
            receipts["skipped_duplicate_id"] += 1
            continue
        if active_keys and pb.plan_key(ticker, direction) in active_keys:
            receipts["skipped_open_plan"] += 1
            continue
        # Match the live two-pass ladder: once a policy survivor claims this immutable
        # identity, a later duplicate cannot replace it merely because validation fails.
        seen_ids.add(plan_id)

        signal_dates, signal_clock_errors = pb._resolve_candidate_signal_dates(
            row,
            formation_date=formation_date,
            price_basis_date=price_basis_date,
        )
        temporal_errors = [*clock_errors, *signal_clock_errors]
        if temporal_errors:
            receipts["skipped_clock_provenance"] += 1
            _record_failure(
                ticker=ticker, plan_id=plan_id, errors=temporal_errors
            )
            continue

        es = row.get("entry_signal") or {}
        spot = es.get("spot")
        if spot is None:
            receipts["skipped_no_spot"] += 1
            continue
        entry = float(spot)

        atr_pct = es.get("atr_pct")
        closes = prices.get(ticker)
        history = (
            pd.DataFrame({"close": closes}) if closes is not None and len(closes) else None
        )
        geo = pb.compute_geometry(
            entry=entry,
            direction=direction,
            atr_pct=float(atr_pct) if atr_pct else None,
            hold_invalidation=hold.get("invalidation"),
            price_history=history,
            asof=price_basis_date,
        )

        is_door_w = row.get("_arena_source") == "door_w"
        if is_door_w and geo.get("invalidation") is None:
            receipts["skipped_door_w_no_geometry"] += 1
            receipts["skipped_door_w_tickers"].append(ticker)
            continue

        horizon_days = pb.HORIZON_DAYS_DEFAULT
        if tilt_inputs is not None:
            try:
                horizon_days, _tilt = pb._compute_stage_tilt(
                    ticker=ticker,
                    entry_date=price_basis_date,
                    tilt_inputs=tilt_inputs,
                )
            except Exception as e:  # noqa: BLE001 — a tilt failure is leash 1.0, never fatal
                log.debug("prophet_arena: tilt failed for %s (%s)", ticker, e)
                horizon_days = pb.HORIZON_DAYS_DEFAULT

        targets = [t for t in (geo["t1"], geo["t2"]) if t is not None]
        plan = {
            "schema": "prophet.trade_plan/v1",
            "id": plan_id,
            "asof": asof,
            "asset": ticker,
            "direction": direction,
            "source_engines": ["prophet_arena_shadow", "us_standouts_buy_lane"],
            "entry": round(entry, 4),
            "trigger": round(float(es.get("chase_above") or entry), 4),
            "invalidation": geo["invalidation"],
            "targets": targets,
            "horizon_days": horizon_days,
            "min_hold_days": pb.MIN_HOLD_DAYS_DEFAULT,
            "tranche": 1,
            "formation_date": formation_date,
            "signal_date": signal_dates["signal_date"],
            "confirmed_date": signal_dates["confirmed_date"],
            "observed_date": signal_dates["observed_date"],
            "signal_tier": signal_dates["signal_tier"],
            "signal_date_basis": signal_dates["signal_date_basis"],
            "signal_provisional": signal_dates["signal_provisional"],
            "source_marker_date": signal_dates["source_marker_date"],
            "price_basis_date": price_basis_date,
            "entry_date": price_basis_date,
            "recorded_at": recorded_at,
            "_signal_date": signal_dates["signal_date"],
            "_r_unit": geo["r_unit"],
            "authority_tier": "display",
            "_arena_policy": policy_key,
            "_arena_source": row.get("_arena_source") or "us_standouts_buy_lane",
        }
        if is_door_w:
            plan["_arena_door_w"] = row.get("_arena_door_w")
        plans.append(plan)

    receipts["originated"] = len(plans)
    receipts["validation_failed"] = len(receipts["validation_failures"])
    receipts["skipped_door_w_tickers"] = sorted(receipts["skipped_door_w_tickers"])
    return plans, receipts


# --------------------------------------------------------------------------- #
# Ledgers — append-only, keep-first on (policy, plan_id, kind).                #
# --------------------------------------------------------------------------- #
_LEDGER_HEADER = (
    "# prophet_arena forward ledger — schema " + LEDGER_SCHEMA + "\n"
    "# active era " + LEDGER_ERA + "; temporal contract " + TEMPORAL_CONTRACT + "\n"
    "# One policy per file. kind=open is the origination stamp, kind=close the graded\n"
    "# outcome. Append-only, keep-first on (policy, id, kind). Nightly is the SOLE\n"
    "# advancer. SHADOW TIER: nothing here has ever changed a live plan, and the live\n"
    "# policy changes only by operator ratification (research/PROPHET_ARENA_REGISTRATION.md).\n"
)


def read_ledger(policy_key: str, root: Path | None = None) -> list[dict]:
    """Every row for one policy, keep-FIRST on (policy, id, kind).  Fail-open to []."""
    p = ledger_path(policy_key, root)
    if not p.exists():
        return []
    seen: set[tuple[str, str, str]] = set()
    rows: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001 — one bad line never kills the file
                continue
            key = (
                str(row.get("policy") or ""),
                str(row.get("id") or ""),
                str(row.get("kind") or ""),
            )
            if not key[1] or key in seen:
                continue
            seen.add(key)
            rows.append(row)
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_arena: ledger read failed for %s (%s)", policy_key, e)
    return rows


def sealed_legacy_summary(root: Path | None = None) -> dict:
    """Counts from the sealed v1 files for disclosure only; never returns grade data.

    RETIRED keys are counted too.  A key leaving :data:`POLICIES` stops its accrual; it
    does not un-write the v1 era it already sat through, and dropping its rows here would
    silently shrink a disclosed audit total the day a policy retires.
    """
    by_policy: dict[str, dict[str, int]] = {}
    total_open = total_close = total_other = 0
    for policy_key in (*POLICY_KEYS, *RETIRED_POLICY_KEYS):
        counts = {"open": 0, "close": 0, "other": 0}
        path = legacy_ledger_path(policy_key, root)
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:  # noqa: BLE001 — disclosure remains best-effort
                        counts["other"] += 1
                        continue
                    kind = str(row.get("kind") or "")
                    if kind in ("open", "close"):
                        counts[kind] += 1
                    else:
                        counts["other"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "prophet_arena: sealed legacy count failed for %s (%s)",
                    policy_key,
                    exc,
                )
        by_policy[policy_key] = counts
        total_open += counts["open"]
        total_close += counts["close"]
        total_other += counts["other"]
    return {
        "schema": LEGACY_LEDGER_SCHEMA,
        "path": "data/prophet_arena/<policy>.jsonl",
        "open_rows": total_open,
        "close_rows": total_close,
        "other_or_corrupt_rows": total_other,
        "by_policy": by_policy,
        "status": "sealed_read_only_excluded",
    }


def ledger_state(policy_key: str, root: Path | None = None) -> dict[str, dict]:
    """``{plan_id: {"open": row, "close": row|None}}`` folded from the policy ledger."""
    out: dict[str, dict] = {}
    for row in read_ledger(policy_key, root):
        pid = str(row.get("id") or "")
        slot = out.setdefault(pid, {"open": None, "close": None})
        kind = str(row.get("kind") or "")
        if kind in slot and slot[kind] is None:
            slot[kind] = row
    return out


def append_rows(
    policy_key: str, rows: list[dict], root: Path | None = None, *, force: bool = False
) -> int:
    """Append rows whose (policy, id, kind) is not already present.  Returns the count.

    NIGHTLY-GATED: writes nothing unless ``ledger_lane.nightly_advance_enabled()`` (or an
    explicit ``force``, which exists for tests only).  This is the same sentinel every
    other forward ledger in the repo uses.
    """
    if not rows:
        return 0
    if not (force or nightly_advance_enabled()):
        log.info(
            "prophet_arena: not the nightly lane — %d row(s) for %s NOT appended",
            len(rows), policy_key,
        )
        return 0
    existing = {
        (str(r.get("policy") or ""), str(r.get("id") or ""), str(r.get("kind") or ""))
        for r in read_ledger(policy_key, root)
    }
    fresh = []
    for row in rows:
        key = (
            str(row.get("policy") or ""),
            str(row.get("id") or ""),
            str(row.get("kind") or ""),
        )
        if key in existing:
            continue
        existing.add(key)
        fresh.append(row)
    if not fresh:
        return 0

    p = ledger_path(policy_key, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(_LEDGER_HEADER, encoding="utf-8")
    with p.open("a", encoding="utf-8") as fh:
        for row in fresh:
            fh.write(json.dumps(row, allow_nan=False, default=str, sort_keys=True) + "\n")
    return len(fresh)


def open_row(policy_key: str, plan: dict, *, arena_night: str) -> dict:
    """The origination stamp for one shadow plan."""
    return {
        "schema": LEDGER_SCHEMA,
        "temporal_contract": TEMPORAL_CONTRACT,
        "kind": "open",
        "policy": policy_key,
        "id": plan["id"],
        "asset": plan.get("asset"),
        "direction": plan.get("direction"),
        "formation_date": plan.get("formation_date"),
        "signal_date": plan.get("signal_date"),
        "confirmed_date": plan.get("confirmed_date"),
        "observed_date": plan.get("observed_date"),
        "signal_tier": plan.get("signal_tier"),
        "signal_date_basis": plan.get("signal_date_basis"),
        "signal_provisional": plan.get("signal_provisional"),
        "source_marker_date": plan.get("source_marker_date"),
        "price_basis_date": plan.get("price_basis_date"),
        "entry_date": plan.get("entry_date"),
        "recorded_at": plan.get("recorded_at"),
        "arena_night": arena_night,
        "entry": plan.get("entry"),
        "trigger": plan.get("trigger"),
        "invalidation": plan.get("invalidation"),
        "targets": plan.get("targets") or [],
        "horizon_days": plan.get("horizon_days"),
        "source": plan.get("_arena_source"),
    }


def close_row(policy_key: str, plan: dict, verdict: dict, *, asof: str) -> dict:
    """The graded closure row for one shadow plan."""
    return {
        "schema": LEDGER_SCHEMA,
        "temporal_contract": TEMPORAL_CONTRACT,
        "kind": "close",
        "policy": policy_key,
        "id": plan["id"],
        "asset": plan.get("asset"),
        "formation_date": plan.get("formation_date"),
        "signal_date": plan.get("signal_date"),
        "confirmed_date": plan.get("confirmed_date"),
        "observed_date": plan.get("observed_date"),
        "signal_tier": plan.get("signal_tier"),
        "signal_date_basis": plan.get("signal_date_basis"),
        "signal_provisional": plan.get("signal_provisional"),
        "source_marker_date": plan.get("source_marker_date"),
        "price_basis_date": plan.get("price_basis_date"),
        "entry_date": plan.get("entry_date"),
        "recorded_at": plan.get("recorded_at"),
        "trigger": plan.get("trigger"),
        "close_date": verdict.get("close_date"),
        "outcome": verdict.get("outcome"),
        "stock_result_pct": verdict.get("stock_result_pct"),
        "option_result_pct": None,
        "days_held": verdict.get("days_held"),
        "sessions_held": verdict.get("sessions_held"),
        "asof": asof,
    }


# --------------------------------------------------------------------------- #
# Grading — replay the ruler over every still-open shadow plan.                #
# --------------------------------------------------------------------------- #
def grade_open_plans(
    policy: Policy,
    state: dict[str, dict],
    *,
    asof: str,
    prices: PriceCache,
) -> list[dict]:
    """Closure rows for shadow plans that are open in the ledger and have now closed."""
    asof_ts = pd.Timestamp(str(asof)[:10])
    out: list[dict] = []
    for plan_id, slot in sorted(state.items()):
        if slot.get("close") is not None or slot.get("open") is None:
            continue
        stamp = slot["open"]
        closes = prices.get(str(stamp.get("asset") or ""))
        if closes is None or not len(closes):
            continue
        pit = closes[closes.index <= asof_ts]
        if not len(pit):
            continue
        plan = {
            "id": plan_id,
            "asset": stamp.get("asset"),
            "direction": stamp.get("direction") or "BULL",
            "entry": stamp.get("entry"),
            "trigger": stamp.get("trigger"),
            "invalidation": stamp.get("invalidation"),
            "targets": stamp.get("targets") or [],
            "horizon_days": stamp.get("horizon_days") or pb.HORIZON_DAYS_DEFAULT,
            "formation_date": stamp.get("formation_date"),
            "signal_date": stamp.get("signal_date"),
            "confirmed_date": stamp.get("confirmed_date"),
            "observed_date": stamp.get("observed_date"),
            "signal_tier": stamp.get("signal_tier"),
            "signal_date_basis": stamp.get("signal_date_basis"),
            "signal_provisional": stamp.get("signal_provisional"),
            "source_marker_date": stamp.get("source_marker_date"),
            "price_basis_date": stamp.get("price_basis_date"),
            "entry_date": stamp.get("entry_date"),
            "recorded_at": stamp.get("recorded_at"),
        }
        verdict = replay_closure(
            plan, pit, time_stop_sessions=policy.time_stop_sessions
        )
        if verdict is not None:
            out.append(close_row(policy.key, plan, verdict, asof=asof))
    return out


# --------------------------------------------------------------------------- #
# Scoreboard                                                                   #
# --------------------------------------------------------------------------- #
def _stats(results: list[float]) -> dict:
    """Win rate / mean / median over closed shadow results.  Nulls printed, not hidden."""
    if not results:
        return {"n": 0, "win_rate_pct": None, "avg_pct": None, "median_pct": None}
    wins = sum(1 for r in results if r > 0)
    return {
        "n": len(results),
        "win_rate_pct": round(100.0 * wins / len(results), 1),
        "avg_pct": round(statistics.fmean(results), 2),
        "median_pct": round(statistics.median(results), 2),
    }


def _policy_record(policy_key: str, root: Path | None) -> dict:
    """Folded per-policy record: open/closed counts, results, outcomes, nights."""
    state = ledger_state(policy_key, root)
    closed = {
        pid: slot for pid, slot in state.items() if slot.get("close") is not None
    }
    results = [
        float(slot["close"]["stock_result_pct"])
        for slot in closed.values()
        if slot["close"].get("stock_result_pct") is not None
    ]
    outcomes: dict[str, int] = {}
    for slot in closed.values():
        key = str(slot["close"].get("outcome") or "")
        outcomes[key] = outcomes.get(key, 0) + 1
    nights = sorted({
        str((slot.get("open") or {}).get("arena_night") or "")
        for slot in state.values()
        if (slot.get("open") or {}).get("arena_night")
    })
    return {
        "state": state,
        "closed": closed,
        "results": results,
        "outcomes": outcomes,
        "nights": nights,
    }


def _same_cohort_vs_champion(
    record: dict, champion: dict
) -> dict:
    """Head-to-head over the nights BOTH policies originated a plan that has since closed.

    Cohort-level, and only over shared nights — a policy that simply started later must
    not read as better than the champion because it missed a bad week.
    """
    def _by_night(rec: dict) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for slot in rec["closed"].values():
            night = str((slot.get("open") or {}).get("arena_night") or "")
            value = slot["close"].get("stock_result_pct")
            if night and value is not None:
                out.setdefault(night, []).append(float(value))
        return out

    mine, theirs = _by_night(record), _by_night(champion)
    shared = sorted(set(mine) & set(theirs))
    if not shared:
        return {
            "shared_nights": 0,
            "n_policy": 0,
            "n_champion": 0,
            "avg_pct": None,
            "champion_avg_pct": None,
            "diff_pp": None,
        }
    a = [v for night in shared for v in mine[night]]
    b = [v for night in shared for v in theirs[night]]
    avg_a = statistics.fmean(a) if a else None
    avg_b = statistics.fmean(b) if b else None
    return {
        "shared_nights": len(shared),
        "n_policy": len(a),
        "n_champion": len(b),
        "avg_pct": round(avg_a, 2) if avg_a is not None else None,
        "champion_avg_pct": round(avg_b, 2) if avg_b is not None else None,
        "diff_pp": (
            round(avg_a - avg_b, 2)
            if avg_a is not None and avg_b is not None
            else None
        ),
    }


def _paired_vs_champion(record: dict, champion: dict) -> dict:
    """PER-PLAN PAIRED comparison — the only honest read for a CLOSURE-grain policy.

    A closure policy holds the SAME plan ids as the champion with the same entries, so
    the two records differ only in where each plan exited.  Averaging two cohorts would
    throw that pairing away; this differences each plan against itself.
    """
    pairs: list[tuple[str, float, float]] = []
    for pid, slot in sorted(record["closed"].items()):
        other = champion["closed"].get(pid)
        if other is None:
            continue
        mine = slot["close"].get("stock_result_pct")
        theirs = other["close"].get("stock_result_pct")
        if mine is None or theirs is None:
            continue
        pairs.append((pid, float(mine), float(theirs)))
    if not pairs:
        return {
            "n_paired": 0, "avg_diff_pp": None, "median_diff_pp": None,
            "better": 0, "worse": 0, "same": 0, "unpaired_plans": len(record["closed"]),
        }
    diffs = [m - t for _pid, m, t in pairs]
    return {
        "n_paired": len(pairs),
        "avg_diff_pp": round(statistics.fmean(diffs), 2),
        "median_diff_pp": round(statistics.median(diffs), 2),
        "better": sum(1 for d in diffs if d > 0),
        "worse": sum(1 for d in diffs if d < 0),
        "same": sum(1 for d in diffs if d == 0),
        "unpaired_plans": len(record["closed"]) - len(pairs),
    }


def _retired_block(policy: RetiredPolicy, root: Path | None) -> dict:
    """One sealed key's disclosure: who it was, why it stopped, what it accrued.

    The counts come from :func:`read_ledger` — the SAME reader every active policy is
    folded by, keep-first and all — so a sealed record is never re-counted by a second,
    subtly different parser.  ``ledger_present`` separates "sealed at zero" from "the
    file is not on this root at all", which is what a fresh temporary root looks like.
    """
    rows = read_ledger(policy.key, root)
    return {
        "policy": policy.key,
        "label": policy.label_en,
        "label_zh": policy.label_zh,
        "retired": policy.retired,
        "reason": policy.reason,
        "successor": policy.successor,
        "sealed": True,
        "ledger_path": f"data/prophet_arena/{LEDGER_ERA}/{policy.key}.jsonl",
        "ledger_present": ledger_path(policy.key, root).exists(),
        "opens": sum(1 for r in rows if str(r.get("kind") or "") == "open"),
        "closes": sum(1 for r in rows if str(r.get("kind") or "") == "close"),
    }


def build_scoreboard(
    *,
    asof: str,
    root: Path | None = None,
    validity: dict | None = None,
    tonight: dict | None = None,
) -> dict:
    """The whole-arena scoreboard.  Display tier, authority all false, plain words."""
    records = {key: _policy_record(key, root) for key in POLICY_KEYS}
    champion = records[CHAMPION_KEY]
    sealed_legacy = sealed_legacy_summary(root)

    policies: list[dict] = []
    for policy in POLICIES:
        record = records[policy.key]
        stats = _stats(record["results"])
        n_closed = len(record["closed"])
        n_open = len(record["state"]) - n_closed
        expired = record["outcomes"].get("EXPIRED", 0)
        timed = record["outcomes"].get(OUTCOME_TIME_STOPPED, 0)
        block: dict[str, Any] = {
            "policy": policy.key,
            "label": policy.label_en,
            "label_zh": policy.label_zh,
            "grain": policy.grain,
            "n_open": n_open,
            "n_closed": n_closed,
            "win_rate_pct": stats["win_rate_pct"],
            "avg_pct": stats["avg_pct"],
            "median_pct": stats["median_pct"],
            "expired_share_pct": (
                round(100.0 * expired / n_closed, 1) if n_closed else None
            ),
            "time_stopped_share_pct": (
                round(100.0 * timed / n_closed, 1) if n_closed else None
            ),
            "outcomes": dict(sorted(record["outcomes"].items())),
            "nights_recorded": len(record["nights"]),
            "reading": (
                "too early to read — needs "
                f"{HEADLINE_MIN_CLOSED} closed shadow plans, has {n_closed}"
                if n_closed < HEADLINE_MIN_CLOSED
                else "readable — enough closed shadow plans for a headline"
            ),
            "readable": n_closed >= HEADLINE_MIN_CLOSED,
        }
        if policy.key != CHAMPION_KEY:
            if policy.grain == "closure":
                block["vs_champion"] = _paired_vs_champion(record, champion)
                block["vs_champion_basis"] = (
                    "per-plan paired — same plan ids and entries as the live rule, "
                    "different exits"
                )
            else:
                block["vs_champion"] = _same_cohort_vs_champion(record, champion)
                block["vs_champion_basis"] = (
                    "same-cohort — only the nights on which both this policy and the "
                    "live rule started a plan that has since finished"
                )
        policies.append(block)

    checks = dict(validity or {})
    mismatch = int(checks.get("c0_mismatch_count", 0) or 0)
    checks.setdefault("c0_mismatch_count", mismatch)
    checks["harness_ok"] = mismatch == 0
    checks["meaning"] = (
        "the mirror of the live rule started exactly the same plans the live run did"
        if mismatch == 0
        else (
            "the mirror of the live rule started a different set of plans than the live "
            "run — treat every number on this page as suspect until that is fixed"
        )
    )

    scoreboard = {
        "schema": SCOREBOARD_SCHEMA,
        "as_of": asof,
        "tier": "display",
        "authority": {
            "tier": "display",
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_escalate": False,
        },
        "registration": REGISTRATION_DOC,
        "ledger_era": LEDGER_ERA,
        "temporal_contract": TEMPORAL_CONTRACT,
        "historical_boundary": {
            "active_path": f"data/prophet_arena/{LEDGER_ERA}/<policy>.jsonl",
            "active_schema": LEDGER_SCHEMA,
            "sealed_prior": sealed_legacy,
            "reason": (
                "v1 open rows did not persist price_basis_date, trigger or tier-native "
                "date provenance; their formation-clock outcomes cannot be repaired by "
                "guessing and are excluded from every active grade and summary"
            ),
        },
        "standing_line": STANDING_LINE_EN,
        "standing_line_zh": STANDING_LINE_ZH,
        "headline_min_closed": HEADLINE_MIN_CLOSED,
        "harness_validity": checks,
        "policies": policies,
        # A retired key stays VISIBLE with its sealed count. Deleting the block would
        # make a policy that once traded look like one that never existed, which is the
        # same disclosure failure the sealed v1 era is kept on disk to avoid.
        "retired_policies": [_retired_block(p, root) for p in RETIRED_POLICIES],
        "tonight": tonight or {},
        "note": (
            "Each policy is a frozen way of choosing which plans to start, or when to "
            "close them, run beside the live rule on the same nights and scored by the "
            "same closure rules. Nothing here has ever changed a live plan. The active "
            "price-basis/trigger era starts empty and fills one night at a time; the sealed "
            "formation-clock era remains audit-visible but is excluded, never rewritten. "
            "There is no backfill, so a small count means young, not weak. "
            + STANDING_LINE_EN + "."
        ),
        "note_zh": (
            "每条策略都是一种已冻结的选股或离场规则，与实盘规则在同一批交易夜并行运行，"
            "并以相同的平仓规则评分。此处的任何结果都从未改变过实盘计划。当前价基准/触发器时代"
            "从零开始逐夜累积；旧形成日期时钟记录只保留作审计并完全排除，绝不改写。没有回填 — "
            "样本少代表时间短，而非结论弱。" + STANDING_LINE_ZH + "。"
        ),
    }
    return scoreboard


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, allow_nan=False, indent=2, default=str, sort_keys=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# --------------------------------------------------------------------------- #
# The nightly entry point.                                                     #
# --------------------------------------------------------------------------- #
def run_arena(
    standouts: dict,
    *,
    asof: str,
    existing_ids: set[str],
    active_keys: set[str] | None = None,
    live_plan_ids: set[str] | None = None,
    repo_root: Path | None = None,
    write: bool = True,
    tilt_inputs: "dict | str | None" = "auto",
) -> dict:
    """One nightly Arena pass.  Returns the scoreboard; raises nothing the caller must catch.

    ``standouts`` is the IN-MEMORY artifact the live origination just used — passed in, not
    re-read, so the Arena and the champion provably slice the same world.

    ``live_plan_ids`` are the ids the live run actually originated.  C0 must reproduce them
    exactly; the difference is the harness-validity flag.

    ``tilt_inputs`` defaults to ``"auto"`` (load the bridge's hold-leash inputs, so a
    shadow plan carries the same horizon the live plan would).  Pass ``None`` to disable —
    the horizon then defaults to 45 for every plan.  The bridge's loader resolves its own
    data dir through ``lib.config``, so a test running against a temporary root must pass
    ``None`` or it would read the real store.
    """
    root = repo_root if repo_root is not None else _repo_root()
    standouts_asof = standouts.get("as_of", asof)
    staleness = standouts.get("staleness") or {}
    panel_mixed_vintage = bool(
        staleness.get("inputs", {}).get("panel", {}).get(
            "mixed_vintage"
        )
    )
    prices = PriceCache(root)

    # Shared, once-per-run policy inputs. Every one fails open with a receipt.
    dispersion_cap, dispersion_receipt = read_dispersion_state(asof, root)
    atlas = AtlasGate(root)
    doors, door_disclosure = door_w_rows(prices, root)

    if tilt_inputs == "auto":
        try:
            tilt_inputs = pb._load_stage_tilt_inputs()
        except Exception as e:  # noqa: BLE001
            log.info(
                "prophet_arena: stage-tilt inputs unavailable (%s) — horizons default", e
            )
            tilt_inputs = None

    tonight: dict[str, Any] = {
        "asof": asof,
        "standouts_as_of": standouts_asof,
        "price_through": staleness.get("price_through"),
        "source_delayed": staleness.get("delayed"),
        "source_unknown": staleness.get("unknown"),
        "source_basis": staleness.get("basis"),
        "panel_mixed_vintage": panel_mixed_vintage,
        "gate_go": standouts.get("gate_go"),
        "dispersion": dispersion_receipt,
        "door_w": door_disclosure,
        "policies": {},
    }
    validity: dict[str, Any] = {}

    for policy in POLICIES:
        rows, sel_receipts = select_for_policy(
            policy.key,
            standouts,
            # C0/C6 deliberately ignore this frozen challenger cap and return the full
            # live population. Selection challengers retain their registered sample.
            cap=REGISTERED_CHALLENGER_CAP,
            door_rows=doors,
            atlas=atlas,
            dispersion_cap=dispersion_cap,
        )
        plans, org_receipts = originate_shadow_plans(
            policy.key,
            rows,
            asof=asof,
            standouts_asof=standouts_asof,
            price_through=staleness.get("price_through"),
            source_delayed=staleness.get("delayed"),
            source_unknown=staleness.get("unknown"),
            source_basis=staleness.get("basis"),
            existing_ids=set(existing_ids),
            active_keys=active_keys,
            prices=prices,
            tilt_inputs=tilt_inputs,
            panel_mixed_vintage=panel_mixed_vintage,
        )
        ids = sorted(p["id"] for p in plans)
        tonight["policies"][policy.key] = {
            "selected_tickers": [str(r.get("ticker")) for r in rows],
            "plan_ids": ids,
            "n_plans": len(plans),
            "selection": sel_receipts,
            "origination": org_receipts,
        }

        if policy.key == CHAMPION_KEY and live_plan_ids is not None:
            live = sorted(live_plan_ids)
            missing = sorted(set(live) - set(ids))
            extra = sorted(set(ids) - set(live))
            validity = {
                "c0_plan_ids": ids,
                "live_plan_ids": live,
                "c0_mismatch_count": len(missing) + len(extra),
                "missing_from_mirror": missing,
                "extra_in_mirror": extra,
            }
            if missing or extra:
                _warn(
                    "C0 mirror did not match the live origination "
                    f"(missing={missing} extra={extra}) — scoreboard flagged"
                )

        # Origination stamps, then grade everything still open (including tonight's).
        state = ledger_state(policy.key, root)
        new_open = [
            open_row(policy.key, plan, arena_night=str(asof)[:10])
            for plan in plans
            if plan["id"] not in state
        ]
        if write:
            appended = append_rows(policy.key, new_open, root)
            tonight["policies"][policy.key]["ledger_rows_appended"] = appended
            state = ledger_state(policy.key, root)
        closures = grade_open_plans(policy, state, asof=asof, prices=prices)
        if write:
            tonight["policies"][policy.key]["ledger_closures_appended"] = append_rows(
                policy.key, closures, root
            )

    scoreboard = build_scoreboard(asof=asof, root=root, validity=validity, tonight=tonight)
    if write:
        _write_json_atomic(scoreboard_path(root), scoreboard)
        _write_json_atomic(
            Path(root) / "site" / "stockdata" / "prophet_arena.json", scoreboard
        )
    return scoreboard
