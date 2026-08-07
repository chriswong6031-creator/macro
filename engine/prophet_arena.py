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
    ``n = len(buy)`` so the cap is a no-op.  The result is the admitted population in
    champion order; every selection policy is a re-ordering, a restriction or a
    re-capping OF THAT LIST.  The Arena never re-implements the filter.
  * geometry (invalidation / T1 / T2 / R)   -> :func:`prophet_bridge.compute_geometry`
  * plan id                                 -> ``prophet_bridge._make_id``
  * ticker+direction identity               -> :func:`prophet_bridge.plan_key`
  * the horizon leash                       -> ``prophet_bridge._load_stage_tilt_inputs``
                                               / ``_compute_stage_tilt`` (so a shadow
                                               plan on a Stage-2 ∩ EC-positive name
                                               carries the same 56d horizon the live
                                               plan would have, and C0 stays a true
                                               control).

DELIBERATE SCOPE OMISSION: shadow plans carry no option contract and no thesis prose.
The live forward ledger's ``option_result_pct`` is null on all 16 closed rows — options
are not part of the ruler — and thesis strings cannot change an outcome.  Resolving
either for 7 policies × 12 plans would spend render budget on fields the measurement
never reads.

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
  2. STRICTLY AFTER signal_date.  ``closes.index > sig_ts`` — the signal day's own
     close is excluded because the plan was not live yet (L541).
  3. SAME-DAY PRECEDENCE IS WORST-CASE-FIRST: invalidation, then T2, then T1 (L566-581).
     A bar that is simultaneously below invalidation and above T2 records INVALIDATED.
  4. FIRST-TRIGGER-CLOSES.  The scan breaks on the first bar that trips anything; a plan
     that touches T1 and later T2 is recorded T1_HIT forever (L502-506).
  5. EXPIRY IS CHECKED LAST WITHIN THE BAR, on CALENDAR days: ``(ts - sig_ts).days >=
     horizon_days`` (L599).  Not sessions — the 9 EXPIRED champion rows carry
     days_held 45/45/45/45/45/45/45/46/47.
  6. ``stock_result_pct = (close_price / entry - 1) * 100`` rounded to 4 (L611-612).
  7. ``days_held = close_date - signal_date`` in calendar days (L621).
  8. A frame that ends before signal_date + horizon leaves the plan OPEN indefinitely.
     That is correct behaviour, not a missed expiry (L509-511).

  ARENA-ADDED (C6 only, and the one convention with no champion line to mirror):
  9. The 21-session time stop is evaluated AFTER the three price triggers and BEFORE
     the calendar expiry check.  "21st session" counts POST-SIGNAL BARS in the same
     frame the replay walks (1-based), NOT calendar days — the rule is about how long
     dead money is held, and sessions are the unit a holder experiences.  A bar that
     is both the 21st session and past the calendar horizon records ``time_stopped``,
     because the time stop is the earlier-firing rule of the two by construction
     (21 sessions ≈ 29-31 calendar days vs a 45d horizon).

FORWARD LEDGERS (house law)
---------------------------
``data/prophet_arena/<policy>.jsonl`` — one file per policy, append-only, keep-first.
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
LEDGER_SCHEMA = "prophet_arena.ledger/v1"
SCOREBOARD_SCHEMA = "prophet_arena.scoreboard/v1"
REGISTRATION_DOC = "research/PROPHET_ARENA_REGISTRATION.md"

#: Closed shadow plans a policy needs before its record is read as a headline.
HEADLINE_MIN_CLOSED = 20

#: C4 — dispersion states and caps.
DISPERSION_LEAN_IN = "lean_in"
DISPERSION_CAP_LEAN_IN = pb.N_CANDIDATES        # 12 — the champion cap
DISPERSION_CAP_OTHERWISE = 6                    # the pre-2026-07-28 cap
DISPERSION_MAX_STALE_SESSIONS = 5

#: C3 — slots inside the 12-cap reserved for Door W names when Door W supplies them.
DOOR_W_RESERVED_SLOTS = 4

#: C5 — full alignment on the SEA taxonomy axis.  ``align_class`` counts how many of the
#: OTHER two canon grids agreed at the event bar, so its MAXIMUM is 2 and 2 means fully
#: aligned (masterplan §taxonomy; Door W's own W3 leg uses the same ``align_class == 2``).
ALIGN_FULL_CLASS = 2
#: The live counterpart ``align_now`` counts how many of ALL THREE grids are bull right
#: now, so ITS full value is 3.  The two are NOT interchangeable and the gate must not
#: compare them to the same number — that would admit a 2-of-3 name as "fully aligned".
ALIGN_FULL_NOW = 3

#: C6 — the no-progress time stop, in POST-SIGNAL SESSIONS (see CONVENTION PIN 9).
TIME_STOP_SESSIONS = 21
OUTCOME_TIME_STOPPED = "time_stopped"

#: Outcomes the champion's own ledger can record (mirrored by the replay).
CHAMPION_OUTCOMES = ("T1_HIT", "T2_HIT", "INVALIDATED", "EXPIRED")

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
        key="C2_stage_ran_preferred",
        label_en="already-moving names first",
        label_zh="优先已启动个股",
        grain="selection",
        time_stop_sessions=None,
        rationale=(
            "Rows the board stages as 'ran' (engine.us_board_rank.STAGE_RAN, entry status "
            "extended/topping/hold) are admitted and lifted above the rest. The STAGE_RAN "
            "shelf graded a 14.5% loser rate against 27.6% for the rest of the buy lane "
            "(n=55) with no half-split flip, yet the board's own stage order ranks 'ran' "
            "BELOW live and setting_up. REGISTERED DEVIATION: this policy WIDENS the pool "
            "rather than only re-ordering it, because the champion's act_level gate and "
            "the stage-ran population are structurally disjoint — see stage_ran_widened()."
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
            "Champion selection, champion order — but the nightly cap is 12 when "
            "data/dispersion/regime.json reads state 'lean_in' and 6 otherwise. The dial "
            "prints 'Selection pays — high dispersion' every night and has ZERO pick-chain "
            "consumers: prophet_bridge, build_prophet and us_board_rank contain no "
            "reference to it at all, and its one sizing consumer is clamped to a no-op in "
            "production. This is the cheapest possible test of whether it should size the "
            "book."
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
            "alignment entirely today. A restriction frees cap slots, so this policy can "
            "also reach rows the champion's cap cut."
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
)

POLICY_KEYS: tuple[str, ...] = tuple(p.key for p in POLICIES)
CHAMPION_KEY = "C0_champion_mirror"
_POLICY_BY_KEY: dict[str, Policy] = {p.key: p for p in POLICIES}


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
    int adds CONVENTION PIN 9: a plan whose close is below entry at that post-signal
    session closes there as ``time_stopped``.

    Every convention here is pinned to a line of ``scripts/build_prophet.py`` in this
    module's docstring; read that block before changing anything in this function.
    """
    entry = plan.get("entry")
    signal_date_str = plan.get("signal_date") or plan.get("_signal_date")
    if entry is None or signal_date_str is None or closes is None or not len(closes):
        return None

    direction = plan.get("direction", "BULL")
    invalidation = plan.get("invalidation")
    targets = plan.get("targets") or []
    t1 = targets[0] if len(targets) > 0 else None
    t2 = targets[1] if len(targets) > 1 else None
    horizon_days = plan.get("horizon_days", pb.HORIZON_DAYS_DEFAULT)

    try:
        sig_ts = pd.Timestamp(signal_date_str)
    except Exception:  # noqa: BLE001
        return None

    # PIN 2 — strictly after the signal day.
    after = closes[closes.index > sig_ts]
    if not len(after):
        return None

    outcome: str | None = None
    close_ts = None
    close_price: float | None = None
    sessions_held: int | None = None

    for session_idx, (ts, raw) in enumerate(after.items(), start=1):
        try:
            px = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(px):
            continue
        days = (ts - sig_ts).days

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

    if outcome is None or close_ts is None or close_price is None:
        return None

    # PIN 6 — signed percent against the plan's entry.
    stock_result_pct: float | None = None
    if entry and float(entry) > 0:
        stock_result_pct = round((close_price / float(entry) - 1.0) * 100.0, 4)

    # PIN 7 — calendar days held.
    close_date = close_ts.date()
    days_held: int | None = None
    try:
        days_held = (close_date - sig_ts.date()).days
    except Exception:  # noqa: BLE001
        days_held = None

    return {
        "outcome": outcome,
        "close_date": close_date.isoformat(),
        "close_price": round(float(close_price), 4),
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


def _is_stage_ran(row: dict) -> bool:
    """True when the board stages this row as 'ran' (C2's evidence leg).

    Reads the row's own ``stage`` field — stamped by ``engine.us_board_rank`` — and falls
    back to the entry status bucket that produces it, so a pre-stage artifact still
    classifies.  Both legs use us_board_rank's own constants; nothing is re-spelled here.
    """
    try:
        from engine import us_board_rank as ubr  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return str(row.get("stage") or "") == "ran"
    if str(row.get("stage") or "") == ubr.STAGE_RAN:
        return True
    status = str((row.get("entry_signal") or {}).get("status") or "")
    return status in ubr._RAN_STATUSES


def stage_ran_widened(standouts: dict) -> list[dict]:
    """Stage-ran buy rows that clear every champion filter EXCEPT the act_level gate.

    WHY THIS EXISTS (measured, 2026-08-05 artifact — the finding that shaped C2).
    ``stage_for`` returns STAGE_RAN only for entry statuses extended/topping/hold, and
    ``act_level`` is derived from urgency (``entry_signal._ACT_LEVEL``), where only
    "now" (3) and "imminent" (2) clear the champion's ``act_level >= 2`` gate.  On the
    2026-07-31 artifact the two populations were exactly disjoint: 25 admitted rows, all
    stage "live"; all 17 stage-ran rows carried act_level 0 or 1, none reached the
    caution-mode ``score >= 60`` escape, and 12 of the 17 were band "low" anyway.

    So a policy that merely RE-ORDERS the admitted pool by stage-ran evidence would sort
    a set that structurally cannot contain a stage-ran row — a null by construction, and
    worse, one that would read as "no effect" rather than "never tested".  The measurement
    C2 exists to probe (the STAGE_RAN shelf's 14.5% loser rate against 27.6% for the rest
    of the buy lane) is defined ON THOSE EXCLUDED ROWS, so C2 must widen the pool to reach
    them.  This is a registered deviation from the literal "same filters" wording; see
    ``research/PROPHET_ARENA_REGISTRATION.md`` §C2.

    The widening relaxes ONE leg and reuses the champion's code for all the others: a
    COPY of the artifact is built in which only the stage-ran rows' act_level is lifted to
    the admission threshold, and ``select_candidates`` judges it.  Band, direction,
    entry-signal presence and the gate_go mode are therefore still the champion's own.
    The rows returned are the ORIGINAL, unpatched dicts — the patch is an admission probe,
    never something a shadow plan is built from.
    """
    buys = standouts.get("buy") or []
    ran_tickers = {str(r.get("ticker")) for r in buys if _is_stage_ran(r)}
    if not ran_tickers:
        return []
    patched: list[dict] = []
    for row in buys:
        if str(row.get("ticker")) in ran_tickers and (row.get("entry_signal") or {}):
            probe = dict(row)
            es = dict(row.get("entry_signal") or {})
            try:
                es["act_level"] = max(int(es.get("act_level") or 0), 2)
            except (TypeError, ValueError):
                es["act_level"] = 2
            probe["entry_signal"] = es
            patched.append(probe)
        else:
            patched.append(row)
    shadow = dict(standouts)
    shadow["buy"] = patched
    admitted = pb.select_candidates(shadow, n=max(len(patched), 1))
    originals = {str(r.get("ticker")): r for r in buys}
    return [
        originals[str(r.get("ticker"))]
        for r in admitted
        if str(r.get("ticker")) in ran_tickers and str(r.get("ticker")) in originals
    ]


def read_dispersion_state(
    asof: str, repo_root: Path | None = None
) -> tuple[int, dict]:
    """C4's cap plus the receipt saying WHICH mode fired.

    Returns ``(cap, receipt)``.  Fails OPEN to the champion cap on every unhappy path —
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

    ``select_candidates`` bundles filter + sort + cap; calling it with ``n`` = the number
    of buy rows makes the cap a no-op and hands back exactly the admitted set the live
    path would have capped.  The Arena therefore never re-implements the admission rule —
    a change to the champion's filter propagates to every policy automatically.
    """
    buys = standouts.get("buy") or []
    return pb.select_candidates(standouts, n=max(len(buys), 1))


def select_for_policy(
    policy_key: str,
    standouts: dict,
    *,
    cap: int = pb.N_CANDIDATES,
    door_rows: list[dict] | None = None,
    atlas: "AtlasGate | None" = None,
    dispersion_cap: int | None = None,
) -> tuple[list[dict], dict]:
    """Rows this policy would originate tonight, plus its receipts.

    Selection only — suppression (existing ids / open plans) and geometry come later, in
    :func:`originate_shadow_plans`, exactly as they do on the live path.
    """
    pool = admitted_pool(standouts)
    receipts: dict[str, Any] = {"admitted": len(pool), "cap": cap}

    if policy_key == "C0_champion_mirror":
        return pool[:cap], receipts

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

    if policy_key == "C2_stage_ran_preferred":
        # POOL-WIDENING, not just re-ordering — see stage_ran_widened() for the measured
        # reason the literal "same filters" version is a null by construction.
        pool_tickers = {str(r.get("ticker")) for r in pool}
        extra = [
            r for r in stage_ran_widened(standouts)
            if str(r.get("ticker")) not in pool_tickers
        ]
        combined = pool + extra
        rows = sorted(
            combined,
            key=lambda r: (0 if _is_stage_ran(r) else 1, pb._selection_sort_key(r)),
        )
        receipts["stage_ran_in_champion_pool"] = sum(1 for r in pool if _is_stage_ran(r))
        receipts["stage_ran_admitted_by_widening"] = len(extra)
        receipts["stage_ran_selected"] = sum(1 for r in rows[:cap] if _is_stage_ran(r))
        receipts["widening"] = (
            "the act_level gate is relaxed for stage-ran rows only; band, direction, "
            "entry-signal presence and the gate mode stay the champion's"
        )
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
        receipts["selection_basis"] = "identical to C0 by construction"
        return pool[:cap], receipts

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
    existing_ids: set[str],
    active_keys: set[str] | None,
    prices: PriceCache,
    tilt_inputs: dict | None = None,
) -> tuple[list[dict], dict]:
    """Shadow plans for one policy's rows, using the bridge's geometry and id.

    Mirrors ``prophet_bridge.originate_plans``' skip ladder in order — duplicate id, open
    ticker+direction key, missing spot — so C0's emitted ids can equal the live path's.

    ASYMMETRY, DELIBERATE: a champion-pool row whose geometry comes back null is still
    originated, because the live path originates it too (``validate_trade_plan`` does not
    require geometry); such a plan can only ever EXPIRE.  A DOOR W row whose geometry is
    null is SKIPPED AND COUNTED, per the policy's own registration — a synthesized row
    with no invalidation is not a plan, it is a ticker.
    """
    plans: list[dict] = []
    receipts: dict[str, Any] = {
        "offered": len(rows),
        "skipped_duplicate_id": 0,
        "skipped_open_plan": 0,
        "skipped_no_spot": 0,
        "skipped_door_w_no_geometry": 0,
        "skipped_door_w_tickers": [],
    }
    seen_ids: set[str] = set()

    for row in rows:
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        direction = "BULL"
        hold = row.get("hold") or {}
        anchor = hold.get("anchor")
        signal_date = anchor if anchor else standouts_asof
        plan_id = pb._make_id(ticker, direction, signal_date)

        if plan_id in existing_ids or plan_id in seen_ids:
            receipts["skipped_duplicate_id"] += 1
            continue
        if active_keys and pb.plan_key(ticker, direction) in active_keys:
            receipts["skipped_open_plan"] += 1
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
            asof=standouts_asof,
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
                    ticker=ticker, signal_date=signal_date, tilt_inputs=tilt_inputs
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
            "signal_date": signal_date,
            "_signal_date": signal_date,
            "_r_unit": geo["r_unit"],
            "authority_tier": "display",
            "_arena_policy": policy_key,
            "_arena_source": row.get("_arena_source") or "us_standouts_buy_lane",
        }
        if is_door_w:
            plan["_arena_door_w"] = row.get("_arena_door_w")
        plans.append(plan)
        seen_ids.add(plan_id)

    receipts["originated"] = len(plans)
    receipts["skipped_door_w_tickers"] = sorted(receipts["skipped_door_w_tickers"])
    return plans, receipts


# --------------------------------------------------------------------------- #
# Ledgers — append-only, keep-first on (policy, plan_id, kind).                #
# --------------------------------------------------------------------------- #
_LEDGER_HEADER = (
    "# prophet_arena forward ledger — schema " + LEDGER_SCHEMA + "\n"
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
        "kind": "open",
        "policy": policy_key,
        "id": plan["id"],
        "asset": plan.get("asset"),
        "direction": plan.get("direction"),
        "signal_date": plan.get("signal_date"),
        "arena_night": arena_night,
        "entry": plan.get("entry"),
        "invalidation": plan.get("invalidation"),
        "targets": plan.get("targets") or [],
        "horizon_days": plan.get("horizon_days"),
        "source": plan.get("_arena_source"),
    }


def close_row(policy_key: str, plan: dict, verdict: dict, *, asof: str) -> dict:
    """The graded closure row for one shadow plan."""
    return {
        "schema": LEDGER_SCHEMA,
        "kind": "close",
        "policy": policy_key,
        "id": plan["id"],
        "asset": plan.get("asset"),
        "signal_date": plan.get("signal_date"),
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
            "invalidation": stamp.get("invalidation"),
            "targets": stamp.get("targets") or [],
            "horizon_days": stamp.get("horizon_days") or pb.HORIZON_DAYS_DEFAULT,
            "signal_date": stamp.get("signal_date"),
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
        "standing_line": STANDING_LINE_EN,
        "standing_line_zh": STANDING_LINE_ZH,
        "headline_min_closed": HEADLINE_MIN_CLOSED,
        "harness_validity": checks,
        "policies": policies,
        "tonight": tonight or {},
        "note": (
            "Each policy is a frozen way of choosing which plans to start, or when to "
            "close them, run beside the live rule on the same nights and scored by the "
            "same closure rules. Nothing here has ever changed a live plan. Records start "
            "empty and fill one night at a time — there is no backfill, so a small count "
            "means young, not weak. " + STANDING_LINE_EN + "."
        ),
        "note_zh": (
            "每条策略都是一种已冻结的选股或离场规则，与实盘规则在同一批交易夜并行运行，"
            "并以相同的平仓规则评分。此处的任何结果都从未改变过实盘计划。记录从零开始逐夜累积，"
            "没有回填 — 样本少代表时间短，而非结论弱。" + STANDING_LINE_ZH + "。"
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
            cap=pb.N_CANDIDATES,
            door_rows=doors,
            atlas=atlas,
            dispersion_cap=dispersion_cap,
        )
        plans, org_receipts = originate_shadow_plans(
            policy.key,
            rows,
            asof=asof,
            standouts_asof=standouts_asof,
            existing_ids=set(existing_ids),
            active_keys=active_keys,
            prices=prices,
            tilt_inputs=tilt_inputs,
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
