"""engine/prophet_bridge.py — Prophet Origination Bridge (W1, display-only).

Converts us_standouts.json buy-lane entries into prophet.trade_plan/v1 envelopes
and resolves option contracts from the ThetaData EOD store.

PUBLIC API
----------
originate_plans(standouts_path, asof, existing_ids, thetadata_store) -> list[dict]
    Return a list of new prophet.trade_plan/v1 dicts.  IDs already in
    existing_ids are skipped (duplicate-suppression contract).

resolve_option(ticker, direction, entry, horizon_days, signal_date,
               thetadata_store, asof, clock_date=None) -> dict | None
    Return an option_contract dict or None when the store lacks the symbol.

PICK RULE (pre-registered, display-only)
-----------------------------------------
OURS: selection rule documented here; all levels are display-only.

1. Source: site/factordata/us_standouts.json buy[] lane (nightly artifact).
2. Filter:
     a. conviction.band != "low"
     b. gate_go == True  → act_level >= 2  AND conviction.score >= 0  (normal mode)
        gate_go == False → act_level >= 2  OR  conviction.score >= 60 (caution mode)
     c. when the board carries the tier contract, tier must be actionable T1/T2/T3;
        projected T4 remains visible on the board but cannot originate a trade plan.
   Reason: gate_go=False is a macro-caution flag; tighten score threshold, but
   don't eliminate imminent-entry (act_level>=2) setups entirely.
3. Sort: descending by the us_prophet_v1 priority score (row["prophet"]["score"]);
   ties broken by act_level descending, then ticker ascending.  Rows with no
   numeric priority score (pre-v1 artifacts) sort BELOW every scored row and,
   among themselves, by the legacy key (conviction.score descending).
   W1 2026-08-03, operator-signed: ORDERING ONLY — the filters in step 2 and the
   filters are byte-identical to the pre-W1 rule, so the ADMITTED population for a
   given artifact does not move.  See select_candidates() for the ruling citation.
4. Originate every admitted row that is not a duplicate ID, is not blocked by an
   already-open plan on the same ticker+direction, and passes plan validation.  The
   former 12-plan per-run slice was an attention cap masquerading as an opportunity
   gate; featured-board, sector and portfolio-risk caps live elsewhere and are not
   changed by this bridge.
5. Exclude entries where entry_signal is null.
6. Exclude entries where dir != "up" (only BULL universe currently).

GEOMETRY RULES (OURS — display-only, pre-registered)
------------------------------------------------------
  invalidation = hold.invalidation if present
                 else max-protective of (20d swing low, entry − 2×ATR14)
                    for BULL: max(swing_low, entry − 2×ATR14)  [closest to entry]
                    for BEAR: min(swing_high, entry + 2×ATR14) [closest to entry]
  R = |entry − invalidation|  (risk unit)
  T1 = entry + 1.5 × R  (BULL)  or  entry − 1.5 × R  (BEAR)
  T2 = entry + 3.0 × R  (BULL)  or  entry − 3.0 × R  (BEAR)
  horizon_days = 45 default
  min_hold_days = 10 default

ID STABILITY
------------
  <TICKER>-<DIRECTION>-<formation_date>
  formation_date = hold.anchor if present, else us_standouts as_of.
  The ID never migrates when a later signal event is known.  On new tier-aware plans,
  signal_date is the native T1/T2 event close; T3 has no fired event and keeps it null.
  Pre-contract fixtures/artifacts retain the old formation-date alias explicitly marked
  ``signal_date_basis=legacy_formation_alias``.
  Plans persist across runs until invalidated/expired/T2-hit.
  Re-origination is suppressed when the ID already exists in existing_ids.

THE PRICE AND PUBLICATION CLOCKS ARE DISTINCT (2026-08-08)
-----------------------------------------------------------
  ``price_basis_date`` and ``entry_date`` name the NYSE session whose close supplied
  ``entry`` (normally ``us_standouts.as_of``).  ``asof`` and ``recorded_at`` name the
  run/publication date.  A Saturday recovery run can therefore publish on Saturday
  while honestly retaining Friday as its price and grading clock.  A malformed,
  future, weekend or NYSE-holiday price basis fails closed and is disclosed in the
  intake artifact; the bridge never guesses a prior session.

THE GRADING CLOCK IS ``entry_date``, NOT ``signal_date`` (2026-08-06)
---------------------------------------------------------------------
  Historical ``signal_date`` values were BASE-FORMATION aliases (``hold.anchor``) and
  could precede origination by months — 94 of 103 live plans carried a gap, PINS by
  152 days.  New plans keep formation separately and use the causal tier event date.
  ``entry`` is the source price-basis session's close, so anchoring the horizon and
  outcome scan to ``signal_date`` graded every plan on bars that PREDATED it: all
  9 EXPIRED ledger rows and both winners closed before their own plan existed, and
  14 plans were born already past horizon.

  The id keeps carrying the formation date (no key migration — the ledger, the state
  files and every downstream consumer are keyed on it).  Every new plan also carries
  explicit ``formation_date`` and ``price_basis_date`` fields.  ``entry_date`` mirrors
  ``price_basis_date`` — the date whose close IS ``entry`` — and the clock, the
  outcome scan, the management τ and the option min-expiry all resolve through
  :func:`plan_clock_date`. Rows graded on the old clock are quarantined
  (``data/prophet/ledger_quarantine.json``), never rewritten: the forward ledger
  is append-only, so a poisoned row is DISCLOSED and excluded from summaries
  rather than edited away.

RE-ORIGINATION BLOCK WHILE ACTIVE (W1 2026-08-03, operator-signed)
-------------------------------------------------------------------
  The ID carries formation_date, so a NEW formation on a name that was already
  live used to originate a SECOND plan for it and duplicate exposure in the plan book
  (CLF/PI/BDC each did this within one week; 10 ticker+direction pairs held
  duplicate open plans as of 2026-08-03).  ``originate_plans(active_keys=...)``
  now skips a candidate whose ``<TICKER>-<DIRECTION>`` key already has an OPEN
  plan.  Closure is exactly what the forward ledger says — a closed plan frees
  the slot on the next run.  ``active_keys=None`` (the default) disables the
  block entirely, so every pre-W1 caller keeps its old behaviour.

OPTION RESOLUTION (display-only)
---------------------------------
  expiry   = nearest monthly expiry >= price_basis_date + horizon_days + 15d
  strike   = nearest strike to 0.60-delta CALL (BULL) / PUT (BEAR)
             if greeks available; else first OTM strike from EOD data
  premium  = latest EOD mid-price (bid+ask)/2 at the chosen strike/expiry
  Null + honest note when store lacks the symbol or no greeks row found.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from engine.government_revenue.federation import reviewed_award_change_context
from engine.government_revenue.freshness import effective_freshness
from engine.prophet_integrity import (
    RECONSTRUCTED_ORIGINATION_PREFIX,
    is_reconstructed,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Backward-compatible default for direct ``select_candidates`` callers and research
# comparisons.  Live ``originate_plans`` deliberately requests the uncapped population;
# featured-board and risk limits are separate authority lanes.
N_CANDIDATES = 12
HORIZON_DAYS_DEFAULT = 45  # BASE_HORIZON_DAYS in PSQ-TILT design; already a named constant
MIN_HOLD_DAYS_DEFAULT = 10
T1_MULTIPLIER = 1.5
T2_MULTIPLIER = 3.0
ATR_MULTIPLIER = 2.0       # invalidation = entry ± 2×ATR14 (protective backstop)
TARGET_DELTA = 0.60        # nearest-delta strike for option resolution

# ── PSQ-TILT W1: hold-leash (provisional, bear-gated, shadow auto-demote) ──────
# The leash extends the intended HOLD horizon for Stage-2 ∩ EC-positive picks —
# hold-quality evidence from the PSQ 2026-07-20 quality re-grade (median fwd126 /
# EA right-shift). Authority boundary (binding): never an entry veto, never rank
# suppression, never a win-rate gate or fused rank bonus. The cap 1.25× is the PSQ
# adjudication ceiling (research/reports/PROPHET_STAGE_QUALITY_RESULTS.md §Adjudication).
STAGE_TILT_LEASH = 1.25
STAGE_TILT_DEMOTE_MIN_MATURED = 30   # §4 floor: n_matured_126 needed before diff can demote

# R0-C disclosure: the leash's earnings-call arm reads a local-only EquityDesk backfill
# parquet that is gitignored and absent on every CI/deploy host, so in production the EC
# lookup always answers null and the leash is pinned at 1.0. That is a STARVED negative,
# not an honest one, and the two used to be indistinguishable in the emitted plan. Every
# stage_tilt block now states which it is. Fail-closed default: with no source record we
# never claim a source exists. This is disclosure only — it never moves the leash.
STAGE_TILT_EC_SOURCE_UNAVAILABLE = "unavailable"

# ── ANTICIPATION §6.2 A1 — status-class admission (ported to the #5071 base) ──
# The admission gate used to be an ACT-LEVEL threshold (``act_level >= 2``, with a
# conviction escape in caution mode).  act_level is derived from the ladder's urgency
# word (engine/entry_signal.py:_ACT_LEVEL), and every PATIENCE status maps to 0 or 1 —
# so the US board was mathematically incapable of originating a plan before
# confirmation, while the CN board (identical indicator engine, identical not_topped
# veto) has featured the patience statuses since 2026-08-04.  Measured receipts:
# research/prophet_us_audit/CN_US_PROPHET_PARITY_ANATOMY_2026-08-07.md (US admitted set
# 27/27 buy_now/partial/buy_soon while the SAME board carried 23 bounce_wait rows) and
# ENTRY_LATENESS_FORENSIC_2026-08-07.md (median +6.34% pre-signal run-up; entry placed
# +2.72% above the signal close).
#
# The new admission is a STATUS CLASS, not a threshold:
#   patience     — the turn is not confirmed yet; this is the pre-move bench.
#   confirmation — the window is open now (the only class the old gate could see).
# ``extended`` stays OUT (it is the anti-chase guard — a stretched leader is exactly
# what this change exists to stop buying) and ``buy_soon`` stays OUT (it graded WORST
# of the CN entry statuses; admitting it imports the chase without the evidence).
ADMISSION_CLASS_PATIENCE = "patience"
ADMISSION_CLASS_CONFIRMATION = "confirmation"
#: §6.9 R3 — the EARLY-TURN starter tier.  Not a status class: a row already admitted
#: by :data:`PATIENCE_STATUSES` is RE-classed to this when the mechanical turn
#: signature fires under washout/leader-pullback context (engine/us_early_turn.py).
#: It never widens admission on its own — see :func:`select_candidates`.
ADMISSION_CLASS_EARLY_TURN = "early_turn_starter"
PATIENCE_STATUSES = frozenset({"bounce_wait", "wait_pullback", "hold"})
CONFIRMATION_STATUSES = frozenset({"buy_now", "partial"})
ADMITTED_STATUSES = PATIENCE_STATUSES | CONFIRMATION_STATUSES

#: The board ``dir`` values a candidate may carry.
#:
#: MEASURED, 2026-08-08: ``dir`` is a SIGNAL TONE, not a price arrow — the ladder-state
#: map says so in as many words (``engine/cycles.py``: "``dir`` here drives the
#: alert-feed colour ... it is a signal-tone, not a price arrow, which is why
#: COUNTERTREND BOUNCE also uses 'caution'").  COUNTERTREND BOUNCE is the state that
#: emits ``bounce_wait`` — "daily bottoming setup INSIDE a bearish higher-timeframe
#: regime" — i.e. the patience cohort this whole change exists to admit.  On the
#: 2026-08-07 board ALL 28 bounce_wait rows carry ``dir="caution"``; a literal
#: ``dir == "up"`` filter admits ZERO of them and the inversion is inert.
#:
#: The tone bucket is shared with TOP WATCH (``extended``/``topping`` — the chase-risk
#: cohort), so ``caution`` alone would be too wide.  It is the STATUS gate that makes
#: this safe: ``extended`` and ``topping`` are refused by ADMITTED_STATUSES no matter
#: what tone they carry, and only COUNTERTREND BOUNCE survives both tests.
ADMITTED_DIRECTIONS = frozenset({"up", "caution"})

#: ``down`` stays REFUSED **by recorded ruling** (§6.7, A1 2026-08-08).  It covers
#: DECLINE and ROLLING OVER (genuinely bearish) and also BOTTOM WATCH ("NEARING A LOW ·
#: GET READY"), which is arguably the earliest patience state of all — admitting it is
#: a real widening that belongs to a ruling, not to this change.  The refusal is
#: DISCLOSED (``intake_stats["refused_direction"]``), never silent: one row on the
#: 2026-08-07 board is affected.
REFUSED_DIRECTIONS = frozenset({"down"})

#: The rest of the ladder's status vocabulary (engine/entry_signal.py:_HEADLINE).
#: Refusing one of these is the RULE working; refusing anything else is vocabulary
#: drift and is counted + named by the caller's stats dict instead of vanishing.
_KNOWN_REFUSED_STATUSES = frozenset({
    "await_confluence", "buy_soon", "watch", "extended",
    "topping", "exit", "avoid", "blocked",
})

# ── ANTICIPATION §6.9 R5 — per-name "why not" receipts ────────────────────────────────
#
# THE SPECIFICITY RULE — the whole reason this is not "report the first failing gate".
# :func:`select_candidates` SHORT-CIRCUITS: it ``continue``s at the first refusal, because
# admission only needs ONE gate to say no.  Its order is
# ``no_entry_signal → direction → band_low → tier → status``, and ``intake_stats`` counts
# the refusals that way — as AGGREGATE tallies with no ticker attached, which is why the
# per-name surface cannot be read off ``intake_stats`` and derives its own row-level view
# through the SAME admission helpers instead.
#
# Measured on the committed 2026-08-07 board: **8 of the 25 refused rows fail MORE THAN
# ONE gate**, and **every ``extended``/``topping`` row also carries ``band == 'low'``.
# Because the band is tested BEFORE the status, a first-failing-gate receipt labels every
# anti-chase name "No setup yet" and the ran-too-far story — the exact thing the shelf
# exists to tell — becomes invisible on the surface.
#
# So the receipt evaluates EVERY gate without short-circuiting and then picks the
# headline by :data:`REFUSAL_ORDER`, which is a MOST-ACTIONABLE-FIRST order, NOT gate
# order.  Nothing is hidden by that choice: every other failing code rides the row's
# ``why`` list and is disclosed on the chip's Tier-2 hover.  Do not "repair" this into
# gate order — that is the defect, not the design.
REFUSAL_ORDER = (
    "plan_not_built",   # cleared every gate; only the plan build itself failed
    "already_open",     # cleared every gate; the name already has a live plan
    "not_ready",        # the patience statuses that are ALMOST admitted
    "ran_too_far",      # the anti-chase refusal — must outrank the band it co-occurs with
    "stood_down",       # an explicit avoid/exit/blocked stance
    "grade_low",        # the tier cascade graded it below the actionable set
    "conviction_low",   # the board's own `band == 'low'`
    "pointing_down",    # tone refused by ruling (§6.7 A1)
    "no_trigger",       # no entry signal on the row at all
    "unknown",          # fail-closed generic — an unmapped/renamed status word
)

#: Refused ``entry_signal.status`` → receipt code.  Every word here is a member of
#: :data:`_KNOWN_REFUSED_STATUSES` (the test pins the two key sets equal); anything else
#: falls through to ``"unknown"`` in :func:`refusal_receipts`, which is the FAIL-CLOSED
#: path: a renamed or newly minted status word must never drop the row from the shelf and
#: must never raise inside a render.
REFUSAL_STATUS_MAP = {
    "extended": "ran_too_far",
    "topping": "ran_too_far",
    "buy_soon": "not_ready",
    "await_confluence": "not_ready",
    "watch": "not_ready",
    "blocked": "stood_down",
    "exit": "stood_down",
    "avoid": "stood_down",
}

#: code → (EN, ZH).  The ONE place this feature's user-facing wording lives, so the
#: dashboard shelf and the published receipts can never word the same refusal
#: differently.
#:
#: ``conviction_low`` deliberately reuses the BOARD'S OWN public band name for
#: ``band == 'low'`` ("No setup" / "暂无买点") rather than coining a second phrase for the
#: same fact — one word through the whole flow.  ``stood_down`` uses the doctrine's own
#: ratified stance verb ("Stand aside", DESIGN_DOCTRINE §2 Law 1) for the same reason: an
#: interface teaches its vocabulary by repeating it.  No internal token — a status slug, a
#: tier name, a gate name — appears in any string here: the reader is told what is true
#: about the stock, never which branch of our code said so.
REFUSAL_COPY = {
    "plan_not_built": ("Cleared every check — no entry plan came together tonight",
                       "各项检查都通过 — 但今晚没能形成完整计划"),
    "already_open":   ("Already has a plan running",
                       "已有在跑的计划"),
    "not_ready":      ("Setting up, but the entry hasn't come",
                       "形态在走，入场点还没到"),
    "ran_too_far":    ("Ran too far — waiting for a pullback",
                       "涨得太急 — 等回调"),
    "stood_down":     ("Standing aside for now",
                       "暂时回避"),
    "grade_low":      ("Signal too weak to act on",
                       "信号强度不足以行动"),
    "conviction_low": ("No setup yet",
                       "暂无买点"),
    "pointing_down":  ("Still heading down",
                       "方向仍朝下"),
    "no_trigger":     ("No entry trigger yet",
                       "还没有入场触发"),
    "unknown":        ("Held back for another reason",
                       "另有原因，暂未纳入"),
}

#: The "one identifiable thing stands between this name and a plan" cohort.  The shelf
#: paints these rails with the WAIT hue so the reader's eye lands on the names that are
#: closest to rejoining the board, instead of treating a 25-name list as flat.
REFUSAL_NEAR = frozenset({"plan_not_built", "already_open", "not_ready"})

#: Per-group ticker cap.  The group's ``n`` always reports the TRUE count, so an
#: overflow is DISCLOSED by the arithmetic rather than silently truncated away.
REFUSAL_NAMES_CAP = 14

#: Direction suffixes :func:`plan_key` appends.  ``refusal_receipts`` accepts either a
#: bare ticker set (build_site reads tickers out of the published index) or the
#: ``<TICKER>-<DIRECTION>`` key set (build_prophet already holds ``active_keys``), so it
#: strips ONLY these two suffixes — a blind rsplit on "-" would turn the plain ticker
#: ``BRK-B`` into ``BRK`` and hand a different company someone else's open plan.
_REFUSAL_KEY_SUFFIXES = ("-BULL", "-BEAR")

#: Month names for the era's plain-word "in force since" line.  The era literal itself is
#: a Tier-2 receipt (DESIGN_DOCTRINE §2 Law 5: plain words at a glance, the identifier on
#: hover), so Tier 1 needs the date in a form a reader actually reads.
_REFUSAL_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

#: The selection rule this run's plans were originated under.  Stamped on every plan
#: and on index.json so a later side-by-side can separate eras without guessing from
#: dates (the #4942 era-stamp pattern).  CHARTERED LITERAL — §6.2 fixed this string and
#: the §6.6 measurement lane filters on it; it is never re-dated to the build date.
SELECTION_ERA = "anticipation-v1-2026-08-08"

# ── Reconstructed-origination disclosure ─────────────────────────────────────────────
# research/PROPHET_OUTAGE_BACKFILL_2026_08.md §0.10.  A plan minted by the operator's
# force-majeure replay carries `origination_mode: "outage_backfill_<date>"`; a live plan
# carries the key not at all.  This block is the ONE place that reader-facing wording
# lives, for the same reason REFUSAL_COPY is: `build_prophet` publishes it onto the row
# and `build_site` renders a count of it on the US board, and the two must never word
# the same fact differently.
#
# VOCABULARY RULING (doctrine §2 Law 2, and §0.10 by name).  The internal name of this
# event never reaches a reader: not "backfill", not "mixed vintage", not "force majeure",
# not the era literal, not the mode slug.  The reader is told the true, useful thing —
# the run that would have made this pick did not finish, so the pick was rebuilt
# afterwards from that day's data — and the machine identifier stays on the row for a
# reader who wants to split the cohort themselves (§0.6c).
#
# NO STANCE CLAUSE, DELIBERATELY (doctrine §2 Law 1).  Law 1 asks every PANEL to answer
# "so what do I do"; this is a provenance chip riding a row whose stance is already the
# card's whole point (buy / near / wait / hold / avoid, plus `what_to_do_now`).  A second
# stance here would either duplicate it or contradict it.  How the pick was originated
# does not change what to do about it today — and saying otherwise would be the false
# claim this disclosure exists to avoid.

#: Tier 1, per row — the quiet chip.  Four words, no jargon, no alarm colour implied:
#: it states a fact about how the row was made, not a warning about the stock.
RECONSTRUCTED_CHIP = ("Reconstructed after an outage", "系统中断后补记")

#: Tier 2, per row — the receipt behind the chip.  ~48 words (budget ≤80).  Says the
#: three things a reader needs and nothing else: why it exists, what it was rebuilt
#: from and when, and that the record can be read with these separated out.
RECONSTRUCTED_RECEIPT_EN = (
    "The nightly run that would have made this pick didn't finish that weekend. It was"
    " rebuilt afterwards from the data as it stood on {date}, and its windows are timed"
    " from that date. Rebuilt picks are marked, and counted on their own in the record."
)
RECONSTRUCTED_RECEIPT_ZH = (
    "那个周末的夜间选股没能跑完。它是事后按 {date} 当时的数据重新算出来的，各个时间窗口都从这一天"
    "起算。补记的选股都有标注，成绩记录里也单独计数。"
)

#: Tier 1, board level — the count clause that merges into an existing footnote
#: (doctrine Law 4: one footnote per panel, never a second stamp).  Leading separator
#: is the caller's job, so the clause can ride any footnote.
#:
#: THE REFERENT IS NAMED, NOT IMPLIED.  On the US board this clause lands one line under
#: "N more already have a plan running", and a bare "N running plans were reconstructed"
#: reads as "N OF THOSE" — which is false: this count is taken over EVERY open plan, not
#: over the subset tonight's board happened to consider.  Rendered once and read, the
#: ambiguity was obvious; naming the population ("of the plans now running") costs three
#: words and removes it.  The ZH half drops "另有" for exactly the same reason — 另有
#: means "additionally", which is the wrong relationship to the line above it.
RECONSTRUCTED_FOOTNOTE_EN = "{n} of the plans now running {were} reconstructed after an outage"
RECONSTRUCTED_FOOTNOTE_ZH = "在跑的计划中有 {n} 只是中断后补记的"

#: Tier 2, board level — the hover behind that clause.
RECONSTRUCTED_FOOTNOTE_TIP_EN = (
    "The nightly run didn't finish over the weekend of {date}. These plans were rebuilt"
    " afterwards from the data as it stood that day, their windows are timed from it,"
    " and they are counted on their own in the record."
)
RECONSTRUCTED_FOOTNOTE_TIP_ZH = (
    "{date} 那个周末的夜间选股没能跑完。这些计划是事后按当天的数据重新算出来的，时间窗口都从那天"
    "起算，成绩记录里也单独计数。"
)

#: The record block's own disclosure line, shaped like its sibling QUARANTINE_NOTE so
#: the two read as one voice where they sit together.  It claims a SPLIT, not an
#: exclusion: these rows ARE in the rate (the backfill never writes the ledger — the
#: nightly advances them like any other plan), and the count is what lets a reader take
#: them back out.  Claiming "excluded" here would be a wrong number wearing right units.
RECONSTRUCTED_RECORD_NOTE_EN = (
    "{n} of these were reconstructed after an outage on {date} — counted here, and"
    " marked so they can be counted apart"
)
RECONSTRUCTED_RECORD_NOTE_ZH = (
    "其中 {n} 条是 {date} 系统中断后补记的 — 已计入，也已标注，可单独拆分统计"
)

#: Publication-lag tolerance: how many SESSIONS the entry basis may trail the run's
#: price basis before a plan is refused.  The forensic measured a median 5d and max
#: 57d lag between the basis a plan's ``entry`` was taken from and the day the plan was
#: actually served — ASTS was served 16.1% stale.
#:
#: STRUCTURAL NOTE (measured on the #5071 base, 2026-08-09): the 57d class is already
#: IMPOSSIBLE here.  ``_resolve_origination_clocks`` refuses the whole run unless
#: ``staleness.price_through`` is exactly ``last_session_on_or_before(recorded_at)``
#: and the board declares ``delayed=false``/``unknown=false``/``basis=panel_majority``,
#: so ``price_basis_date`` can never trail the run by even one session.  This guard is
#: therefore a SECOND fence over that one rather than duplicate machinery: it measures
#: the lag it was chartered to measure, discloses it on every plan, and fails closed if
#: the clock contract is ever loosened.  Pinned by the lag-guard property test.
STALE_BASIS_MAX_SESSIONS = 3

#: Legacy shadow ledger (§6.5).  The OLD gate keeps running every night with ZERO
#: authority so the two selections can be compared later on the same tape.
LEGACY_N_CANDIDATES = 12          # FROZEN — the pre-ANTICIPATION cap, shadow only
LEGACY_SHADOW_DIR = "prophet/legacy_shadow"
LEGACY_SHADOW_SCHEMA = "prophet.legacy_shadow/v1"
LEGACY_SHADOW_KEY = ("date", "ticker")

# Monthly expiry calendar helper: US options use 3rd Friday of month.
# We find the first monthly expiry >= min_expiry_date.
_MONTHS = range(1, 13)


def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of the given month/year."""
    first = date(year, month, 1)
    # weekday(): Mon=0 ... Fri=4
    day_of_week = first.weekday()
    # days until first Friday
    days_to_friday = (4 - day_of_week) % 7
    first_friday = first + timedelta(days=days_to_friday)
    return first_friday + timedelta(weeks=2)


def _next_monthly_expiry(min_date: date) -> date:
    """Return the nearest monthly (3rd Friday) expiry >= min_date."""
    y, m = min_date.year, min_date.month
    for _ in range(24):  # search up to 2 years
        tf = _third_friday(y, m)
        if tf >= min_date:
            return tf
        m += 1
        if m > 12:
            m = 1
            y += 1
    raise ValueError(f"Could not find monthly expiry after {min_date}")


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _swing_low_20d(price_history: pd.DataFrame, asof: str) -> float | None:
    """Return the 20-day swing low (lowest close) on or before asof."""
    try:
        asof_ts = pd.Timestamp(asof)
        mask = price_history.index <= asof_ts
        subset = price_history[mask].tail(20)
        if subset.empty:
            return None
        return float(subset["close"].min())
    except Exception:
        return None


def _swing_high_20d(price_history: pd.DataFrame, asof: str) -> float | None:
    """Return the 20-day swing high (highest close) on or before asof."""
    try:
        asof_ts = pd.Timestamp(asof)
        mask = price_history.index <= asof_ts
        subset = price_history[mask].tail(20)
        if subset.empty:
            return None
        return float(subset["close"].max())
    except Exception:
        return None


def compute_geometry(
    entry: float,
    direction: str,  # "BULL" or "BEAR"
    atr_pct: float | None,
    hold_invalidation: float | None,
    price_history: pd.DataFrame | None,
    asof: str,
) -> dict[str, float | None]:
    """
    OURS: Compute invalidation, T1, T2 from the pre-registered geometry rules.

    Returns a dict with keys: invalidation, t1, t2, r_unit.
    All values are floats or None.
    """
    atr_abs = (entry * atr_pct / 100.0) if atr_pct else None

    # --- Compute protective invalidation ---
    if hold_invalidation is not None:
        # Use swing-structure hard invalidation from hold field (preferred)
        invalidation = float(hold_invalidation)
    else:
        # Fallback: max-protective of (20d swing level, entry ± 2×ATR14)
        if direction == "BULL":
            swing = _swing_low_20d(price_history, asof) if price_history is not None else None
            atr_stop = (entry - ATR_MULTIPLIER * atr_abs) if atr_abs else None
            candidates = [c for c in [swing, atr_stop] if c is not None]
            # Most protective = highest (closest to entry from below)
            invalidation = max(candidates) if candidates else None
        else:  # BEAR
            swing = _swing_high_20d(price_history, asof) if price_history is not None else None
            atr_stop = (entry + ATR_MULTIPLIER * atr_abs) if atr_abs else None
            candidates = [c for c in [swing, atr_stop] if c is not None]
            # Most protective = lowest (closest to entry from above)
            invalidation = min(candidates) if candidates else None

    if invalidation is None:
        return {"invalidation": None, "t1": None, "t2": None, "r_unit": None}

    r_unit = abs(entry - invalidation)

    if direction == "BULL":
        t1 = entry + T1_MULTIPLIER * r_unit
        t2 = entry + T2_MULTIPLIER * r_unit
    else:
        t1 = entry - T1_MULTIPLIER * r_unit
        t2 = entry - T2_MULTIPLIER * r_unit

    return {
        "invalidation": round(invalidation, 4),
        "t1": round(t1, 4),
        "t2": round(t2, 4),
        "r_unit": round(r_unit, 4),
    }


# ---------------------------------------------------------------------------
# Pick selection
# ---------------------------------------------------------------------------

def _priority_score(row: dict) -> float | None:
    """The us_prophet_v1 board priority score for a buy row, or None.

    ``row["prophet"]["score"]`` is stamped by ``engine.us_board_rank`` (#4331) and is
    the key the BOARD is already ordered by.  Returns None — not 0 — for a row that
    predates the score or carries a non-numeric / non-finite value, so a legacy row
    lands in the fallback tier of the sort key instead of at the bottom of the scored
    one.  ``bool`` is rejected explicitly: ``isinstance(True, int)`` is True in Python,
    and a stray ``"score": true`` must not read as 1.0.
    """
    block = row.get("prophet")
    if not isinstance(block, dict):
        return None
    score = block.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    value = float(score)
    return value if math.isfinite(value) else None


def _conviction_score(row: dict) -> float:
    """The legacy (pre-W1) primary sort leg: ``conviction.score``, 0.0 when unreadable."""
    score = (row.get("conviction") or {}).get("score", 0)
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return 0.0
    value = float(score)
    return value if math.isfinite(value) else 0.0


def _selection_sort_key(row: dict):
    """Total order over admitted candidates. ORDERING ONLY — never admission.

    Legs, in precedence order:
      1. tier      — 0 when the row carries a us_prophet_v1 priority score, else 1.
                     Every scored row therefore outranks every legacy row.
      2. rank      — priority score desc within tier 0; conviction.score desc within
                     tier 1 (the verbatim pre-W1 primary key).
      3. act_level — descending (unchanged).
      4. ticker    — ascending.

    The ticker leg is load-bearing, not cosmetic: without it a tie on the legs above is
    resolved by the ARTIFACT's incoming buy[] order, so the same board re-emitted in a
    different order would originate a different set of plans and the intake would not be
    provably deterministic.  Ticker is the only stable per-row identity here, so it is
    the final key (tests/test_prophet_bridge_order_invariance.py).
    """
    priority = _priority_score(row)
    return (
        0 if priority is not None else 1,
        -(priority if priority is not None else _conviction_score(row)),
        -((row.get("entry_signal") or {}).get("act_level") or 0),
        str(row.get("ticker") or ""),
    )


def plan_key(ticker: str, direction: str) -> str:
    """``<TICKER>-<DIRECTION>`` — the identity the re-origination block is keyed on.

    Deliberately NOT the plan id: the id also carries ``formation_date``. A fresh
    formation on a name that was already live used to originate a second plan for it.
    See the RE-ORIGINATION BLOCK note in the module docstring.
    """
    return f"{str(ticker or '').strip().upper()}-{str(direction or '').strip().upper()}"


# ---------------------------------------------------------------------------
# The grading clock (2026-08-06) — see the module docstring
# ---------------------------------------------------------------------------

def plan_clock_date(plan: Mapping[str, Any]) -> str | None:
    """The date whose close IS ``plan["entry"]`` — the ONE anchor every clock reads.

    Precedence, and why each rung is where it is:

      1. ``price_basis_date`` — explicit NYSE session whose close supplied ``entry``.
      2. ``entry_date`` — compatibility clock; mirrors ``price_basis_date`` on every
         newly originated plan.
      3. ``asof``       — the run that originated a legacy plan.  This fallback avoids
         a backfill migration, but can only be treated as legacy provenance because an
         old weekend run may have used the prior session's price.
      4. ``signal_date`` — LAST, and only because a hand-written or fixture plan may
         carry nothing else. Legacy rows used it as a formation alias, while tier-aware
         rows use it as an event close; neither proves the close that supplied entry.
         Reading it FIRST is the defect this function exists to fix.

    ``None`` only when the plan carries none of the four — the callers treat that as
    "cannot grade", never as "grade from bar zero".
    """
    for key in ("price_basis_date", "entry_date", "asof", "signal_date"):
        value = plan.get(key)
        if value:
            text = str(value).strip()
            if text:
                return text
    return None


def _normalise_iso_date(value: Any) -> str | None:
    """Return the date leg of a YYYY-MM-DD-ish value, or ``None`` when unreadable."""
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def _resolve_origination_clocks(
    *,
    price_through: Any,
    recorded_asof: Any,
    panel_mixed_vintage: bool = False,
    source_delayed: Any = None,
    source_unknown: Any = None,
    source_basis: Any = None,
) -> tuple[str | None, str | None, list[str]]:
    """Resolve publication and entry-price dates without inventing a market session.

    ``staleness.price_through`` is the vintage the board actually ranked, not merely
    the date on which its JSON wrapper was rebuilt.  Consequently a non-session or
    missing price watermark is not rounded back to Friday, and a delayed/unknown board
    cannot be laundered by a current top-level ``as_of`` stamp.  The candidate is
    refused and the caller exposes the returned errors in
    ``intake.validation_failures``.
    """
    recorded_at = _normalise_iso_date(recorded_asof)
    price_basis_date = _normalise_iso_date(price_through)
    errors: list[str] = []

    if recorded_at is None:
        errors.append(f"recorded_at {recorded_asof!r} is not an ISO-8601 date")
    if price_basis_date is None:
        errors.append(
            f"price_basis_date {price_through!r} from "
            "us_standouts.staleness.price_through "
            "is not an ISO-8601 date"
        )
    else:
        try:
            from lib.nyse_calendar import is_session  # noqa: PLC0415

            if not is_session(date.fromisoformat(price_basis_date)):
                errors.append(
                    f"price_basis_date {price_basis_date!r} from "
                    "us_standouts.staleness.price_through is not an NYSE session"
                )
        except Exception as exc:  # noqa: BLE001 — a price-date gate must fail closed
            errors.append(
                f"price_basis_date {price_basis_date!r} could not be checked against "
                f"the NYSE calendar: {exc}"
            )

    if recorded_at is not None and price_basis_date is not None:
        if date.fromisoformat(price_basis_date) > date.fromisoformat(recorded_at):
            errors.append(
                f"price_basis_date {price_basis_date!r} postdates recorded_at "
                f"{recorded_at!r}"
            )
        try:
            from lib.nyse_calendar import last_session_on_or_before  # noqa: PLC0415

            expected = last_session_on_or_before(date.fromisoformat(recorded_at))
            if date.fromisoformat(price_basis_date) != expected:
                errors.append(
                    f"price_basis_date {price_basis_date!r} is not the last completed "
                    f"NYSE session for recorded_at {recorded_at!r} ({expected.isoformat()}); "
                    "stale boards cannot originate plans"
                )
        except Exception as exc:  # noqa: BLE001 — source-freshness gate fails closed
            errors.append(
                f"price/session freshness could not be checked: {exc}"
            )
    if panel_mixed_vintage:
        errors.append(
            "us_standouts staleness.inputs.panel.mixed_vintage is true; "
            "mixed-vintage boards cannot originate plans"
        )
    if source_unknown is not False:
        errors.append(
            "us_standouts staleness.unknown must be explicitly false; "
            "an unknown ranked-price vintage cannot originate plans"
        )
    if source_delayed is not False:
        errors.append(
            "us_standouts staleness.delayed must be explicitly false; "
            "a delayed or undisclosed ranked-price vintage cannot originate plans"
        )
    if source_basis != "panel_majority":
        errors.append(
            "us_standouts staleness.basis must be 'panel_majority'; "
            f"wrapper-only or undisclosed price authority is unsafe ({source_basis!r})"
        )

    return recorded_at, price_basis_date, errors


def _resolve_candidate_signal_dates(
    candidate: Mapping[str, Any],
    *,
    formation_date: str,
    price_basis_date: str | None,
) -> tuple[dict[str, Any], list[str]]:
    """Resolve a plan's causal signal clock from the board's tier-native contract.

    T1 and T2 are fired events and therefore require ``tier_event_date``.  T3 is an
    actionable *observation* of a forming cross, so it deliberately has no signal date
    or confirmation date.  T4 is not an actionable Prophet tier.  Marker confirmation
    is copied only for T1 and only when the marker's own event date matches the tier
    event; a T2 cross must never inherit an unrelated §7 marker date.

    Rows from before the additive tier-date contract remain readable through an
    explicit legacy basis.  This compatibility path is intentionally detectable and
    does not pretend the formation label was a proven causal event.
    """
    signal = candidate.get("signal")
    tier_contract_present = isinstance(signal, Mapping) and any(
        key in signal for key in (
            "tier_event_date", "tier_observed_date", "tier_observation_provisional",
        )
    )
    if (
        not isinstance(signal, Mapping)
        or not signal.get("tier_cascade")
        or not tier_contract_present
    ):
        legacy_tier = (
            str(signal.get("tier_cascade")).strip().upper()
            if isinstance(signal, Mapping) and signal.get("tier_cascade") else None
        )
        legacy_last = (
            signal.get("last")
            if isinstance(signal, Mapping) and isinstance(signal.get("last"), Mapping)
            else {}
        )
        return ({
            "signal_tier": legacy_tier,
            "signal_date": formation_date,
            "confirmed_date": None,
            "observed_date": price_basis_date,
            "signal_date_basis": "legacy_formation_alias",
            "signal_provisional": bool(
                isinstance(signal, Mapping)
                and (signal.get("provisional") or legacy_tier == "T3")
            ),
            "source_marker_date": _normalise_iso_date(legacy_last.get("date")),
        }, [])

    tier = str(signal.get("tier_cascade") or "").strip().upper()
    raw_event = signal.get("tier_event_date")
    raw_observed = signal.get("tier_observed_date")
    event_date = _normalise_iso_date(raw_event) if raw_event is not None else None
    observed_date = (
        _normalise_iso_date(raw_observed) if raw_observed is not None else None
    )
    provisional = bool(signal.get("tier_observation_provisional"))
    last = signal.get("last") if isinstance(signal.get("last"), Mapping) else {}
    source_marker_date = _normalise_iso_date(last.get("date")) if last else None
    errors: list[str] = []

    if tier not in ("T1", "T2", "T3"):
        errors.append(
            f"tier_cascade {tier or None!r} is not actionable; Prophet admits T1/T2/T3"
        )
    if observed_date is None:
        errors.append(
            f"tier_observed_date {raw_observed!r} is required for tier-aware plans"
        )
    elif price_basis_date is not None and observed_date != price_basis_date:
        errors.append(
            f"tier_observed_date {observed_date!r} does not match price_basis_date "
            f"{price_basis_date!r}"
        )

    confirmed_date: str | None = None
    if tier in ("T1", "T2"):
        if event_date is None:
            errors.append(
                f"tier_event_date {raw_event!r} is required for fired tier {tier}"
            )
        elif observed_date is not None and event_date > observed_date:
            errors.append(
                f"tier_event_date {event_date!r} postdates tier_observed_date "
                f"{observed_date!r}"
            )
        if event_date is not None and formation_date > event_date:
            errors.append(
                f"formation_date {formation_date!r} postdates tier_event_date "
                f"{event_date!r}"
            )
        if tier == "T1" and last:
            marker_event = _normalise_iso_date(last.get("signal_date"))
            marker_confirmed = (
                _normalise_iso_date(last.get("confirmed_date"))
                if last.get("confirmed_date") is not None else None
            )
            if marker_confirmed is not None:
                if (
                    str(last.get("type") or "").lower() not in ("buy", "rebuy")
                    or marker_event != event_date
                ):
                    errors.append(
                        "T1 marker confirmed_date does not belong to the tier event"
                    )
                elif provisional:
                    errors.append(
                        "provisional T1 cannot carry a confirmed marker date"
                    )
                else:
                    confirmed_date = marker_confirmed
        if tier == "T2" and provisional:
            errors.append("fired T2 cannot be marked provisional")
    elif tier == "T3":
        if raw_event is not None:
            errors.append("projected T3 must not carry tier_event_date")
        if not provisional:
            errors.append("projected T3 must be marked provisional")

    if confirmed_date is not None and event_date is not None:
        if confirmed_date < event_date:
            errors.append("confirmed_date predates tier_event_date")
        if observed_date is not None and confirmed_date > observed_date:
            errors.append("confirmed_date postdates tier_observed_date")

    return ({
        "signal_tier": tier or None,
        "signal_date": event_date if tier in ("T1", "T2") else None,
        "confirmed_date": confirmed_date,
        "observed_date": observed_date,
        "signal_date_basis": (
            "tier_event_date" if tier in ("T1", "T2") else "tier_observation"
        ),
        "signal_provisional": provisional,
        "source_marker_date": source_marker_date,
    }, errors)


# ---------------------------------------------------------------------------
# Forward-ledger quarantine (2026-08-06)
# ---------------------------------------------------------------------------
# The ledger is append-only: a row graded on the pre-origination clock cannot be
# rewritten or deleted.  It is listed here instead, and every reader that
# SUMMARISES the record drops the listed ids.  Per-plan closure facts (is this plan
# finished?) must NOT read this list — the plan really did close, it is only the
# NUMBER attached to that close that is unusable.

QUARANTINE_FILENAME = "ledger_quarantine.json"
QUARANTINE_SCHEMA = "prophet.ledger_quarantine/v1"
QUARANTINE_REASON = "graded_on_pre_origination_clock"


def load_quarantined_ids(path: "str | Path | None" = None) -> set[str]:
    """Plan ids whose ledger row is excluded from every RECORD SUMMARY.

    Absent file → empty set (no quarantine is the normal state, not an error).  An
    unreadable/garbled file also returns empty rather than raising: the quarantine
    subtracts rows from a display-tier summary, and a summary that crashes tells the
    reader less than a summary that over-reports affected rows and says so upstream.
    """
    if path is None:
        try:
            from lib import config  # noqa: PLC0415
            root = Path(config.data_dir())
        except Exception:  # noqa: BLE001
            root = Path(__file__).resolve().parent.parent / "data"
        path = root / "prophet" / QUARANTINE_FILENAME
    p = Path(path)
    if not p.exists():
        return set()
    try:
        with p.open(encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_bridge: quarantine file unreadable (%s) — treating as empty", e)
        return set()
    rows = payload.get("quarantined") if isinstance(payload, dict) else payload
    out: set[str] = set()
    for row in rows or []:
        plan_id = row.get("id") if isinstance(row, dict) else row
        if plan_id:
            out.add(str(plan_id))
    return out


def entry_status(row: Mapping[str, Any]) -> str:
    """The board row's entry STATUS word, lowercased; ``""`` when unreadable.

    ONE reader, so admission, the ``admission_class`` stamp and the shadow ledger can
    never disagree about what a row's status is.
    """
    es = row.get("entry_signal")
    if not isinstance(es, Mapping):
        return ""
    return str(es.get("status") or "").strip().lower()


def admission_class(status: str) -> str | None:
    """``"patience"`` / ``"confirmation"`` / ``None`` for a status outside the gate."""
    key = str(status or "").strip().lower()
    if key in PATIENCE_STATUSES:
        return ADMISSION_CLASS_PATIENCE
    if key in CONFIRMATION_STATUSES:
        return ADMISSION_CLASS_CONFIRMATION
    return None


def select_candidates(
    standouts: dict,
    n: int | None = N_CANDIDATES,
    stats: dict | None = None,
) -> list[dict]:
    """
    Apply the pick rule to us_standouts.json and return a filtered, sorted list of at
    most n buy entries (``n=None`` → uncapped).

    ADMISSION (ANTICIPATION §6.2 A1, ported 2026-08-09 — operator-ruled ship-live):
      ``entry_signal`` present
      AND ``dir`` in :data:`ADMITTED_DIRECTIONS`   (a TONE test, not a price arrow)
      AND ``conviction.band != 'low'``
      AND ``signal.tier_cascade`` in {T1,T2,T3} when present
      AND ``entry_signal.status`` in :data:`ADMITTED_STATUSES`

    The pre-2026-08-08 rule was an act-level threshold — ``act_level >= 2`` (gate_go),
    or ``act_level >= 2 OR conviction.score >= 60`` (caution mode) — and it is
    preserved verbatim, with zero authority, in :func:`legacy_admitted` so the shadow
    ledger can keep grading it.  See the ADMISSION CLASS note in the constants block
    for the measured reason it moved.

    A row whose status is not in the vocabulary is REFUSED, not defaulted: the plan
    must be able to state which class admitted it, and a row with no class has no
    honest answer.  Refusals are counted into ``stats`` (``unknown_status`` /
    ``unknown_status_values`` / ``refused_status`` / ``refused_direction``) rather than
    dropped silently — a board that renamed a status word would otherwise empty the
    intake with no alarm.

    ORDER (W1 2026-08-03, scored + operator-signed) is UNCHANGED: the us_prophet_v1
    priority score, then act_level, then ticker — see the sort block below.  ``n``
    remains for research/backward-compatible direct callers; live plan origination
    always passes ``n=None`` and applies no positional slice.

    ``stats`` is an optional out-dict; never read, only written.
    """
    # buy[] ONLY. standouts["leaders"] (2026-07-28 leaders strip) is deliberately
    # excluded: those rows have no fresh entry signal, hence no plan geometry.
    buys: list[dict] = standouts.get("buy", [])

    selected: list[dict] = []
    by_class: dict[str, int] = {
        ADMISSION_CLASS_PATIENCE: 0, ADMISSION_CLASS_CONFIRMATION: 0}
    unknown_status: list[str] = []
    refused_status: dict[str, int] = {}
    refused_direction: dict[str, int] = {}
    refused_no_entry_signal = 0
    refused_band_low = 0
    refused_tier: dict[str, int] = {}
    for b in buys:
        # entry_signal null => skip
        es = b.get("entry_signal")
        if not es:
            refused_no_entry_signal += 1
            continue
        # Tone filter — `dir` is the ladder's alert TONE, not a long/short arrow.
        # `down` (DECLINE / ROLLING OVER / BOTTOM WATCH) is refused BY RULING and the
        # refusal is disclosed; `caution` (COUNTERTREND BOUNCE, and TOP WATCH which the
        # status gate refuses anyway) is admitted.  See ADMITTED_DIRECTIONS.
        tone = str(b.get("dir", "up") or "up").strip().lower()
        if tone not in ADMITTED_DIRECTIONS:
            refused_direction[tone] = refused_direction.get(tone, 0) + 1
            continue
        conv = b.get("conviction") or {}
        band = conv.get("band", "")

        if band == "low":
            refused_band_low += 1
            continue

        # The wide board may display the earliest projected T4 lane, but Prophet's
        # actionable contract has always been T1-T3 (signal_gate.BUYABLE_TIERS).  Old
        # artifacts/fixtures that predate ``tier_cascade`` retain their prior behavior;
        # a present tier is authoritative and cannot be waved through by score alone.
        signal = b.get("signal")
        if isinstance(signal, Mapping):
            signal_tier = signal.get("tier_cascade")
            if signal_tier is not None and signal_tier not in ("T1", "T2", "T3"):
                refused_tier[str(signal_tier)] = refused_tier.get(str(signal_tier), 0) + 1
                continue

        status = entry_status(b)
        klass = admission_class(status)
        if klass is None:
            # Refused. `extended`/`buy_soon`/`topping`/... are deliberate exclusions;
            # anything else is a vocabulary drift the caller must be able to see.
            if status:
                refused_status[status] = refused_status.get(status, 0) + 1
            if status and status not in _KNOWN_REFUSED_STATUSES:
                unknown_status.append(status)
            continue

        by_class[klass] += 1
        selected.append(b)

    if stats is not None:
        stats["admitted_by_class"] = dict(by_class)
        stats["unknown_status"] = len(unknown_status)
        stats["unknown_status_values"] = sorted(set(unknown_status))
        stats["refused_status"] = dict(sorted(refused_status.items()))
        stats["refused_direction"] = dict(sorted(refused_direction.items()))
        stats["refused_no_entry_signal"] = refused_no_entry_signal
        stats["refused_band_low"] = refused_band_low
        stats["refused_tier"] = dict(sorted(refused_tier.items()))
        stats["buy_rows"] = len(buys)

    # Sort: us_prophet_v1 priority score desc, act_level desc, ticker asc.
    #
    # W1 2026-08-03 (SCORED, operator-signed): the primary key moved from raw
    # conviction.score to row["prophet"]["score"] — the SAME us_prophet_v1 priority
    # score the board is ranked by (engine/us_board_rank.py, #4331; weights
    # signal 30 / entry 25 / edge 25 / runway 10 / quality 10).
    # research/US_BOARD_MEASUREMENT.md graded conviction/board order ANTI-predictive
    # (retro P@1 0.20 vs alpha-order 0.60) and its Grade-A "Primary sort key" ruling is
    # "order by residual alpha (or an alpha+timing blend at the very top)"; the priority
    # score IS that ratified blend, so intake and board now share ONE ranking system.
    #
    # ORDERING IS UNCHANGED BY ANTICIPATION A1: the sort key is the same function it
    # was on 2026-08-03, so this change moves WHICH ROWS are admitted and never how the
    # admitted rows are ranked.  A caller that elects to pass a finite ``n`` may still
    # re-slice its own research sample, but the live originator consumes the entire
    # order.  DNR:KILL-PROPHET-POP-MERGE is not re-opened: no new blend is constructed
    # here, and the graded buy POPULATION (the board's own buy[] lane) is untouched —
    # only which of that population the intake is allowed to plan.
    # Pinned by tests/test_prophet_w1_intake_repair.py and
    # tests/test_prophet_bridge_order_invariance.py.
    #
    # Legacy self-heal: a row with no numeric prophet.score sorts BELOW every scored row
    # and, among its own kind, by the OLD key — so a pre-v1 artifact selects exactly what
    # it selects today.  Key legs and the load-bearing ticker leg: _selection_sort_key.
    #
    # ``n=None`` returns the FULL admitted ordering.  The live caller applies duplicate-id
    # and open-plan skips and originates every remaining candidate.  There is no
    # positional opportunity gate in the plan lane (#5071 lossless origination), and A1
    # imports no cap: the "12→16 with sector cap 4" half of the §6.2 spec is SUPERSEDED
    # by lossless origination and is deliberately not ported.
    selected.sort(key=_selection_sort_key)
    return selected if n is None else selected[:n]


def _refusal_open_tickers(open_keys: Iterable[str] | None) -> frozenset[str]:
    """Normalise an open-plan key set to the TICKERS it covers.

    Accepts both shapes the two call sites hold: build_prophet passes the
    ``<TICKER>-<DIRECTION>`` keys from ``open_plan_keys`` verbatim, build_site passes
    bare tickers read out of the published index.  Both forms are kept, so a caller that
    mixes them still matches.  See :data:`_REFUSAL_KEY_SUFFIXES` for why the direction is
    stripped by an exact suffix rather than by splitting on the last hyphen.
    """
    out: set[str] = set()
    for raw in open_keys or ():
        key = str(raw or "").strip().upper()
        if not key:
            continue
        out.add(key)
        for suffix in _REFUSAL_KEY_SUFFIXES:
            if key.endswith(suffix):
                out.add(key[: -len(suffix)])
                break
    return frozenset(out)


def _refusal_codes(row: Mapping[str, Any]) -> list[str]:
    """EVERY admission gate this board row fails, in :data:`REFUSAL_ORDER` order.

    The gates are the same five :func:`select_candidates` applies, evaluated with NO
    short-circuit — see the SPECIFICITY RULE note above :data:`REFUSAL_ORDER` for the
    measured reason a first-failing-gate answer is the wrong one.  An empty list means
    the row cleared admission; what happens to it then is the caller's call, because
    only the caller knows whether a plan was actually originated for it.
    """
    codes: list[str] = []
    if not row.get("entry_signal"):
        codes.append("no_trigger")
    tone = str(row.get("dir", "up") or "up").strip().lower()
    if tone not in ADMITTED_DIRECTIONS:
        codes.append("pointing_down")
    conviction = row.get("conviction")
    if isinstance(conviction, Mapping) and conviction.get("band", "") == "low":
        codes.append("conviction_low")
    signal = row.get("signal")
    if isinstance(signal, Mapping):
        tier = signal.get("tier_cascade")
        if tier is not None and tier not in ("T1", "T2", "T3"):
            codes.append("grade_low")
    if row.get("entry_signal"):
        # The status gate, read through the SAME two helpers admission reads it through,
        # so the shelf can never disagree with the gate about what a row's status is.
        #
        # FAIL-CLOSED, and deliberately not guarded on `status` being truthy: a row that
        # carries an entry_signal with no readable status word is REFUSED by
        # `admission_class` (it returns None), so the receipt must say so too. Reporting
        # nothing there would let a row the intake refused vanish from the shelf that
        # exists to account for exactly those rows. Measured on the committed
        # 2026-08-07 board: zero rows are in that state, so this costs nothing today and
        # is the difference between an honest shelf and a silent hole the day it happens.
        status = entry_status(row)
        if admission_class(status) is None:
            codes.append(REFUSAL_STATUS_MAP.get(status, "unknown"))
    order = {code: i for i, code in enumerate(REFUSAL_ORDER)}
    return sorted(set(codes), key=lambda c: order.get(c, len(REFUSAL_ORDER)))


def refusal_codes(row: Mapping[str, Any]) -> list[str]:
    """PUBLIC reader for :func:`_refusal_codes` — the per-row "why not" vocabulary.

    Added for ``engine/us_candidate_lanes.py``, which places every cascade-eligible name
    into a display lane and must reuse THIS vocabulary rather than coin a second one.
    A thin alias on purpose: importing the private helper would let its semantics move
    under a consumer that never sees the rename, and re-implementing the gate list is
    exactly the drift ``_refusal_codes`` exists to prevent.

    DISPLAY TIER, both ways — this reports the gate and never moves it, and nothing this
    function is called from reaches admission.
    """
    return _refusal_codes(row)


def _refusal_era() -> dict[str, str]:
    """The selection era as a Tier-1 date plus its Tier-2 identifier.

    :data:`SELECTION_ERA` is a CHARTERED LITERAL carrying its own start date, so the
    "in force since" line is READ off it rather than maintained as a second source that
    could drift.  Fail-soft: an era string that stops matching the shape yields empty
    date strings and the shelf simply prints its footnote without the clause — never a
    wrong date, and never a raised exception inside a render.
    """
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})\s*$", SELECTION_ERA)
    if not match:
        return {"era": SELECTION_ERA, "era_since_en": "", "era_since_zh": ""}
    year, month, day = (int(g) for g in match.groups())
    if not 1 <= month <= 12:
        return {"era": SELECTION_ERA, "era_since_en": "", "era_since_zh": ""}
    return {
        "era": SELECTION_ERA,
        "era_since_en": f"{day} {_REFUSAL_MONTHS_EN[month - 1]} {year}",
        "era_since_zh": f"{year}年{month}月{day}日",
    }


def _plain_date(iso: Any) -> tuple[str, str]:
    """``"2026-08-09"`` → ``("9 Aug 2026", "2026年8月9日")``; unparseable → ``("", "")``.

    The same plain-word date form :func:`_refusal_era` already puts on the board, for the
    same doctrine reason (Law 2/Law 3: a date a reader reads, at full precision, not an
    identifier).  FAIL-SOFT by design — every caller drops its date clause on ``("", "")``
    rather than printing a wrong day, and no render may raise here.
    """
    match = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    if not match:
        return ("", "")
    year, month, day = (int(g) for g in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return ("", "")
    return (f"{day} {_REFUSAL_MONTHS_EN[month - 1]} {year}", f"{year}年{month}月{day}日")


def origination_note(row: Mapping[str, Any] | None) -> dict[str, str] | None:
    """The per-row disclosure — chip (Tier 1) + receipt (Tier 2), EN and ZH.

    ``None`` for a live plan, which is how a renderer draws nothing without knowing this
    feature exists.  Self-describing on purpose: the row ships FINISHED user copy, not a
    code to look up, because the surfaces that draw these rows do not all live in this
    repository and a code they must word themselves is a second place for the wording to
    drift (the mistake REFUSAL_COPY's byte-equal mirror test exists to catch).

    The date is the plan's own ``recorded_at`` — the origination day being replayed, which
    is also the day every window is graded from.  A row whose date will not parse ships
    the chip with NO receipt rather than a receipt with a wrong or blank day.
    """
    if not is_reconstructed(row):
        return None
    assert row is not None  # narrowed by is_reconstructed
    date_en, date_zh = _plain_date(row.get("recorded_at"))
    note = {"en": RECONSTRUCTED_CHIP[0], "zh": RECONSTRUCTED_CHIP[1]}
    if date_en:
        note["tip_en"] = RECONSTRUCTED_RECEIPT_EN.format(date=date_en)
        note["tip_zh"] = RECONSTRUCTED_RECEIPT_ZH.format(date=date_zh)
        note["date_en"] = date_en
        note["date_zh"] = date_zh
    return note


def origination_disclosure(rows: Iterable[Mapping[str, Any]] | None) -> dict[str, Any] | None:
    """Board-level disclosure over a plan population — ``None`` when none were rebuilt.

    ``None`` rather than a zero row is the whole safety property: with no reconstructed
    plans in the population every caller omits its key, and the artifact and the rendered
    page are byte-identical to what they were before this feature existed.

    ``date`` is the EARLIEST reconstructed ``recorded_at`` in the population.  One replay
    is one date, so today that is simply "the date"; if a second event ever adds a second
    date the clause still names a true day rather than silently averaging two.
    """
    reconstructed = [r for r in (rows or []) if is_reconstructed(r)]
    if not reconstructed:
        return None
    dates = sorted(
        str(r.get("recorded_at") or "") for r in reconstructed if r.get("recorded_at")
    )
    date_en, date_zh = _plain_date(dates[0] if dates else None)
    n = len(reconstructed)
    out: dict[str, Any] = {
        "n": n,
        "date": dates[0] if dates else None,
        # Plural agreement done here, not in a template: a template that writes
        # `plan{{ 's' if n != 1 }}` has quietly hard-coded English grammar into a
        # bilingual surface, and the ZH half never needed it in the first place.
        "en": RECONSTRUCTED_FOOTNOTE_EN.format(n=n, were="were" if n != 1 else "was"),
        "zh": RECONSTRUCTED_FOOTNOTE_ZH.format(n=n),
    }
    if date_en:
        out["tip_en"] = RECONSTRUCTED_FOOTNOTE_TIP_EN.format(date=date_en)
        out["tip_zh"] = RECONSTRUCTED_FOOTNOTE_TIP_ZH.format(date=date_zh)
    return out


def refusal_receipts(
    standouts: Mapping[str, Any] | None,
    open_keys: Iterable[str] | None = (),
    originated_tickers: Iterable[str] | None = None,
    reconstructed_plans: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Per-name "why not" receipts for every buy-lane row the intake did NOT plan.

    ANTICIPATION §6.9 R5.  ONE function, TWO call sites, so the macro dashboard shelf and
    the published ``site/prophet/index.json`` receipts can never drift:

      * ``scripts/build_site.py`` renders the shelf from the SAME
        ``site/factordata/us_standouts.json`` generation the board above it renders from.
        It deliberately does NOT read ``site/prophet/index.json`` for the reason list:
        ``build_site`` runs BEFORE ``build_prophet`` in daily.yml, and ``render.yml``
        never runs ``build_prophet`` at all — so SSR-ing the published receipts would
        print LAST NIGHT'S refusals underneath TONIGHT'S cards and claim a name was
        passed on when tonight's run planned it.  Reading last night's index for the
        OPEN-PLAN keys only is safe, and is all it does: open plans persist across
        nights, while every refusal REASON comes from tonight's board rows.
      * ``scripts/build_prophet.py`` publishes the same structure into the intake block
        additively, for the Terminal rider.

    WHY NOT ``intake_stats``:  #5105's lossless disclosure records refusals as AGGREGATE
    tallies (``refused_status`` / ``refused_band_low`` / ``refused_tier`` …) and
    ``continue``s past the row — no ticker is retained, so "why isn't this name on the
    board?" is unanswerable from it.  This function is the per-name layer over the SAME
    gate, reading status through :func:`entry_status` / :func:`admission_class` so the two
    can never disagree; it adds no second gate and no second vocabulary.

    ``open_keys`` — open-plan identities (``<TICKER>-<DIRECTION>`` keys or bare tickers).
    ``originated_tickers`` — ``None`` means "this call site does not know what was
    originated tonight" (build_site's case: it knows the gate, not the origination run),
    and then a row that cleared every gate and holds no open plan produces NO receipt at
    all rather than an invented one.  When a set IS passed (build_prophet's case), a
    cleared row missing from it is disclosed as ``plan_not_built``.

    ``reconstructed_plans`` — the OPEN plans a call site knows were rebuilt after the
    outage rather than originated live (build_site reads them out of the published index;
    ``None`` / empty from every other caller).  It rides this dict rather than a second
    template argument because the shelf takes exactly one ``cx``, and it is safe to read
    from last night's index for the SAME reason the open-plan keys are: how a plan was
    originated is a fact about its past that no later night can change.

    Returns ``{"considered", "planned", "passed", "groups", "unmapped", "era",
    "era_since_en", "era_since_zh"}``, plus ``"reconstructed"`` ONLY when some were —
    absent, never zero, so a board with none renders byte-identically to before.
    ``passed`` is the number of names passed on;
    ``planned`` is the remainder of the considered set.  Groups follow
    :data:`REFUSAL_ORDER`, empties omitted; names sort by the board's own priority score
    descending, then ticker ascending; ``why`` is the row's FULL failing set with the
    headline first.  Display tier throughout — this reports the gate, it never moves it.
    """
    buys = (standouts or {}).get("buy") or []
    if not isinstance(buys, list):
        buys = []
    open_tickers = _refusal_open_tickers(open_keys)
    originated = (
        None if originated_tickers is None
        else {str(t or "").strip().upper() for t in originated_tickers}
    )

    rows: list[dict[str, Any]] = []
    for row in buys:
        if not isinstance(row, Mapping):
            continue
        ticker = str(row.get("ticker") or "").strip()
        codes = _refusal_codes(row)
        if not codes:
            # Cleared every gate.  It is either already running, or it should have become
            # a plan tonight and did not — and if this call site cannot tell the two
            # apart it says nothing rather than guessing.
            key = ticker.upper()
            if key and key in open_tickers:
                codes = ["already_open"]
            elif originated is not None and key and key not in originated:
                codes = ["plan_not_built"]
            else:
                continue
        score = (row.get("prophet") or {}).get("score")
        rows.append({
            "ticker": ticker,
            "name": str(row.get("name") or ticker),
            "score": score if isinstance(score, (int, float)) else 0,
            "why": codes,
        })

    groups: list[dict[str, Any]] = []
    for code in REFUSAL_ORDER:
        members = sorted(
            (r for r in rows if r["why"][0] == code),
            key=lambda r: (-float(r["score"] or 0), r["ticker"]),
        )
        if not members:
            continue
        en, zh = REFUSAL_COPY[code]
        groups.append({
            "reason": code,
            "en": en,
            "zh": zh,
            "near": code in REFUSAL_NEAR,
            # TRUE count, always — the cap below trims what is DRAWN, never what is
            # counted, so an overflowing group discloses itself instead of lying small.
            "n": len(members),
            "names": members[:REFUSAL_NAMES_CAP],
        })

    # AN OPEN PLAN IS NOT A REFUSAL.  ``already_open`` rows cleared every gate and are
    # being acted on right now — they are on the cards above, not passed on — so counting
    # them as "passed on" states something false at a glance.  Measured on the committed
    # board through build_site's call site: 48 of the 73 receipted rows are open plans, so
    # the undivided figure reads "we put down 73 of 79" when the honest sentence is "we
    # declined 25 and are already trading 48".  ``passed`` stays the LOSSLESS total (every
    # row that earned a receipt, which the published artifact needs); ``declined`` is the
    # figure a surface should headline, and the two are kept apart here rather than in a
    # template so both call sites inherit the same arithmetic.
    open_now = sum(1 for r in rows if r["why"][0] == "already_open")
    receipts = {
        "considered": len(buys),
        "planned": len(buys) - len(rows),
        "passed": len(rows),
        "open_now": open_now,
        "declined": len(rows) - open_now,
        "groups": groups,
        # A non-zero `unmapped` is the vocabulary-drift alarm: the ladder minted or
        # renamed a status word and the copy table has not caught up.  The rows still
        # render, under the honest generic line.
        "unmapped": sum(1 for r in rows if r["why"][0] == "unknown"),
        **_refusal_era(),
    }
    # ADDED ONLY WHEN TRUE (§0.10).  The key is absent — not zero, not null — whenever
    # nothing was reconstructed, so `{% if cx.reconstructed %}` in the shelf is false on
    # every board that exists today and the rendered footnote is byte-identical.
    disclosure = origination_disclosure(reconstructed_plans)
    if disclosure:
        receipts["reconstructed"] = disclosure
    return receipts


def legacy_admitted(standouts: dict) -> list[dict]:
    """The PRE-ANTICIPATION gate, frozen verbatim — shadow ledger only, ZERO authority.

    This is the rule :func:`select_candidates` ran until this change:

      gate_go=True  → act_level >= 2 AND band != 'low'
      gate_go=False → (act_level >= 2 OR conviction.score >= 60) AND band != 'low'

    plus the same entry-signal-present, ``dir == 'up'`` and T1–T3 ``tier_cascade``
    filters and the same sort.  It exists so §6.5's comparison contract is real: the
    old selection keeps accruing on the same nightly tape, so "was the inversion an
    improvement?" is answerable from two ledgers rather than from memory.  FROZEN — a
    later change to the live admission must not touch this function, and the cap it
    reports is :data:`LEGACY_N_CANDIDATES`, not the live population.

    Returns the admitted rows UNCAPPED, in legacy (== current) sort order.
    """
    gate_go: bool = standouts.get("gate_go", False)
    buys: list[dict] = standouts.get("buy", [])
    selected: list[dict] = []
    for b in buys:
        es = b.get("entry_signal")
        if not es:
            continue
        if b.get("dir", "up") != "up":
            continue
        conv = b.get("conviction") or {}
        band = conv.get("band", "")
        score = conv.get("score", 0) or 0
        act_level = es.get("act_level", 0) or 0
        if band == "low":
            continue
        signal = b.get("signal")
        if isinstance(signal, Mapping):
            signal_tier = signal.get("tier_cascade")
            if signal_tier is not None and signal_tier not in ("T1", "T2", "T3"):
                continue
        if gate_go:
            if not (act_level >= 2):
                continue
        else:
            if not (act_level >= 2 or score >= 60):
                continue
        selected.append(b)
    selected.sort(key=_selection_sort_key)
    return selected


# ---------------------------------------------------------------------------
# Legacy shadow ledger (ANTICIPATION §6.5) — the OLD gate keeps accruing
# ---------------------------------------------------------------------------
# STORAGE: month-grouped DAY parts, ``data/prophet/legacy_shadow/YYYY-MM/
# YYYY-MM-DD.parquet`` — the W7 storage law.  A nightly writes a NEW file and rewrites
# nothing, so git stores one blob per night instead of re-storing a whole month.
#
# AUTHORITY: none.  Nothing in the live pick chain reads this store.  It is written so
# that the operator's "check later" is answerable from data instead of memory.
#
# LANE: nightly is the sole advancer of forward stores.  The gate is TWO-SIDED by
# construction (see :func:`append_legacy_shadow`) because a one-sided gate is how a
# lane guard goes dead: a writer that only consults its own default branch writes in
# every lane the moment a caller forgets the argument (the #5000 shape), and a writer
# that only trusts its caller writes whatever the caller claims.

def _legacy_shadow_dir(root: Any = None, store_dir: Any = None) -> Path:
    """The store directory.

    ``store_dir`` wins when supplied and is the form the BUILDER uses: it hands the
    directory outright (``LEDGER_DIR / "legacy_shadow"``) so the store is always
    co-located with the forward ledger and any caller that redirects one redirects the
    other.  Deriving it from a repo root instead would fail OPEN — a harness that
    points ``LEDGER_DIR`` somewhere unexpected would silently write the real data tree.
    """
    if store_dir is not None:
        return Path(store_dir)
    if root is None:
        try:
            from lib import config  # noqa: PLC0415
            base = Path(config.data_dir())
        except Exception:  # noqa: BLE001
            base = Path(__file__).resolve().parent.parent / "data"
    else:
        base = Path(root) / "data"
    return base / LEGACY_SHADOW_DIR


def _legacy_shadow_part_path(asof: str, root: Any = None, store_dir: Any = None) -> Path:
    """``legacy_shadow/YYYY-MM/YYYY-MM-DD.parquet`` — keyed by the RUN's asof."""
    day = str(asof)[:10]
    return _legacy_shadow_dir(root, store_dir) / day[:7] / f"{day}.parquet"


def legacy_shadow_rows(
    standouts: dict,
    asof: str,
    existing_ids: set[str] | None = None,
    active_keys: set[str] | None = None,
) -> list[dict]:
    """One row per legacy-admitted candidate for ``asof`` (§6.5 schema).

    ``would_have_planned`` replays the FULL legacy path, not just the gate: the same
    duplicate-id and open-plan skips ``originate_plans`` applies, then the legacy
    12-slot cap over the survivors (the P4 filters-then-cap order).  Without the skips
    the flag would over-count every night on which the old gate's top rows were names
    it had already planned — which is precisely the failure P4 was built to fix, and it
    would make the legacy arm look busier than it ever was.

    ``skip_reason`` names why a row that cleared the gate still would not have been
    planned: ``duplicate_id`` / ``open_plan`` / ``below_cap`` / ``None``.
    """
    admitted = legacy_admitted(standouts)
    standouts_asof = standouts.get("as_of", asof)
    existing = set(existing_ids or ())
    active = set(active_keys or ())

    rows: list[dict] = []
    seen_ids: set[str] = set()
    planned = 0
    for index, b in enumerate(admitted, start=1):
        ticker = str(b.get("ticker") or "")
        if not ticker:
            continue
        es = b.get("entry_signal") or {}
        anchor = (b.get("hold") or {}).get("anchor")
        plan_id = _make_id(ticker, "BULL", anchor if anchor else standouts_asof)

        skip_reason: str | None = None
        if plan_id in existing or plan_id in seen_ids:
            skip_reason = "duplicate_id"
        elif active and plan_key(ticker, "BULL") in active:
            skip_reason = "open_plan"
        else:
            seen_ids.add(plan_id)

        would_plan = False
        if skip_reason is None:
            if planned < LEGACY_N_CANDIDATES:
                would_plan = True
                planned += 1
            else:
                skip_reason = "below_cap"

        act_level = es.get("act_level")
        rows.append({
            "schema": LEGACY_SHADOW_SCHEMA,
            "date": str(asof)[:10],
            "ticker": ticker,
            "entry_signal": entry_status(b) or None,
            "act_level": int(act_level) if isinstance(act_level, (int, float))
            and not isinstance(act_level, bool) else None,
            # `score` is the RANKING key (us_prophet_v1 priority) — the number `rank` is
            # derived from.  `conviction_score` is the number the legacy caution-mode
            # escape actually gated on.  Both ship: one column named `score` could only
            # ever be read as the wrong one of the two.
            "score": _priority_score(b),
            "conviction_score": _conviction_score(b),
            "rank": index,
            "would_have_planned": would_plan,
            "skip_reason": skip_reason,
            "gate_go": bool(standouts.get("gate_go", False)),
            "board_asof": str(standouts_asof)[:10],
            "cap": LEGACY_N_CANDIDATES,
            "selection_era": SELECTION_ERA,
            "authority": "none",
        })
    return rows


def append_legacy_shadow(
    rows: list[dict],
    asof: str,
    root: Any = None,
    store_dir: Any = None,
    *,
    lane_nightly: bool,
) -> int:
    """Append shadow rows to the run day's part.  Returns that part's row count, or 0.

    ``lane_nightly`` is KEYWORD-ONLY and has NO DEFAULT: omitting it is a ``TypeError``,
    not a permissive branch.  That is deliberate.  A lane guard whose production caller
    passes nothing and whose default branch is "allow" is a guard that only the test
    suite ever exercises (#5000); a guard with no default cannot be reached at all
    without the caller stating its lane.

    The gate is then TWO-SIDED: the caller's declared lane AND this process's own
    ``ledger_lane.nightly_advance_enabled()`` must both be true.  The caller's half
    makes the gate visible at the production call site; the module's half means a
    caller that claims nightly in a render/intraday process still writes nothing.

    Keep-FIRST on ``(date, ticker)``: a second run on the same night rewrites nothing
    and adds nothing, so idempotence does not depend on the caller being careful.
    """
    from engine import ledger_lane  # noqa: PLC0415

    if not lane_nightly:
        log.info("prophet_bridge: legacy shadow append gated — caller is not the "
                 "US nightly lane")
        return 0
    if not ledger_lane.nightly_advance_enabled():
        log.info("prophet_bridge: legacy shadow append gated — COLLECT_LANE is not "
                 "the US nightly lane")
        return 0
    if not rows or not asof:
        return 0
    try:
        new = pd.DataFrame(rows)
        path = _legacy_shadow_part_path(asof, root, store_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prior = pd.read_parquet(path)
            columns = list(dict.fromkeys([*prior.columns, *new.columns]))
            combined = pd.concat(
                [prior.reindex(columns=columns), new.reindex(columns=columns)],
                ignore_index=True)
        else:
            combined = new
        combined = combined.drop_duplicates(subset=list(LEGACY_SHADOW_KEY), keep="first")
        combined.to_parquet(path, index=False)
        return int(len(combined))
    except Exception as exc:  # noqa: BLE001 — a shadow ledger never breaks the nightly
        # Bare print at line start (house law): a logger prefix makes GitHub drop it.
        print(f"::warning title=prophet-legacy-shadow::legacy shadow append failed: {exc}",
              flush=True)
        log.warning("prophet_bridge: legacy shadow append failed: %s", exc)
        return 0


def load_legacy_shadow(root: Any = None, *, days: Iterable[str] | None = None,
                       store_dir: Any = None) -> pd.DataFrame:
    """Read the shadow store as ONE frame (studies / tests).  Empty frame when absent."""
    store = _legacy_shadow_dir(root, store_dir)
    if not store.exists():
        return pd.DataFrame()
    wanted = {str(d)[:10] for d in days} if days is not None else None
    frames: list[pd.DataFrame] = []
    for part in sorted(store.glob("*/*.parquet")):
        if wanted is not None and part.stem not in wanted:
            continue
        try:
            frames.append(pd.read_parquet(part))
        except Exception as exc:  # noqa: BLE001 — one bad part must not blind the rest
            log.warning("prophet_bridge: shadow part %s unreadable (%s)", part.name, exc)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Publication-lag guard (ANTICIPATION §6.2 A1)
# ---------------------------------------------------------------------------
# MEASURED DEFECT (ENTRY_LATENESS_FORENSIC_2026-08-07 §1c): the date whose close a
# plan's `entry` was taken from trailed the day the plan was actually SERVED by a
# median of 5 days (p75 11, max 57), and price moved a median +3.03% over that lag.
# ASTS was served 16.1% above the close its entry was priced at.
#
# WHAT THE #5071 BASE ALREADY DOES (verified 2026-08-09, not assumed):
# `_resolve_origination_clocks` refuses the entire run unless
# `staleness.price_through == last_session_on_or_before(recorded_at)` and the board
# declares `delayed=false`, `unknown=false`, `basis="panel_majority"`.  So the price
# basis cannot trail the run by even one session, and the 57d class is structurally
# impossible rather than merely unlikely.  Re-deriving an entry from "the current
# close" therefore has NOTHING to re-derive from — the entry ALREADY is that close.
#
# WHAT IS LEFT, and what this guard does: measure the lag anyway, DISCLOSE it on every
# plan (`entry_basis`), and REFUSE any candidate whose measured lag exceeds the
# tolerance.  It is a second fence over a stronger first fence, so in production it
# fires never — which is exactly the property the test pins.  If the clock contract is
# ever loosened, this fence still fails closed instead of publishing a stale price.

def entry_basis_date(row: Mapping[str, Any], price_basis_date: str | None) -> tuple[str, str]:
    """``(basis_date, source)`` — the date whose close ``entry_signal.spot`` came from.

    ``price_basis_date`` is the run's PROVEN ranked-price vintage (#5071's six-clock
    contract), and it is the honest answer: the board's `price`/`entry_signal.spot`
    pair is written at that watermark.  The row's own ``signal_asof`` is the SIGNAL's
    vintage, not the price's — on the 2026-08-07 board every row reads
    ``signal_asof=2026-08-05`` while ``price``/``spot`` are the 08-07 closes — so
    reading it here would manufacture a two-session price lag that does not exist.
    It is disclosed separately as ``signal_basis_date``.
    """
    if price_basis_date:
        text = str(price_basis_date).strip()[:10]
        if text:
            return text, "staleness_price_through"
    value = row.get("signal_asof")
    if value:
        text = str(value).strip()[:10]
        if text:
            return text, "board_signal_asof"
    return "", "unresolved"


def _business_days_between(start: str, end: str) -> int | None:
    """Business days after ``start`` through ``end``; ``None`` when unusable.

    OVERSTATES the lag on a week containing a market holiday (it counts calendar
    business days, not sessions).  That direction is deliberate: erring toward "stale"
    refuses a plan, and erring toward "fresh" publishes at a price the tape has left
    behind.
    """
    try:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(start_ts) or pd.isna(end_ts) or end_ts < start_ts:
        return None
    return int(len(pd.bdate_range(start_ts + pd.Timedelta(days=1), end_ts)))


def _sessions_between(price_history: "pd.DataFrame | None", start: str, end: str) -> int | None:
    """Sessions strictly after ``start`` and up to ``end``, counted on the NAME's tape.

    The ticker's own index is the honest calendar: it already excludes weekends, market
    holidays and any day the name did not trade.  ``None`` when the dates are unusable;
    the caller falls back to a business-day count and says so.
    """
    if price_history is None or getattr(price_history, "empty", True):
        return None
    try:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(start_ts) or pd.isna(end_ts):
        return None
    try:
        index = price_history.index
        return int(((index > start_ts) & (index <= end_ts)).sum())
    except Exception:  # noqa: BLE001
        return None


def resolve_entry_basis(
    row: Mapping[str, Any],
    *,
    price_basis_date: str | None,
    asof: str,
    price_history: "pd.DataFrame | None" = None,
) -> dict[str, Any]:
    """The publication-lag disclosure block stamped on every plan.

    ``state`` is ``"current"`` when the measured lag is within
    :data:`STALE_BASIS_MAX_SESSIONS`, and ``"stale"`` when it is not — the caller
    refuses a stale candidate with a printed reason.  ``signal_lag_sessions`` is the
    SEPARATE, non-blocking disclosure of how old the row's SIGNAL is relative to the
    price it is priced at; that lateness is answered by the entry ZONE (§6.9 R3), not
    by refusing the plan.
    """
    basis_date, basis_source = entry_basis_date(row, price_basis_date)
    lag = _sessions_between(price_history, basis_date, asof) if basis_date else None
    lag_basis = "sessions"
    if lag is None:
        lag = _business_days_between(basis_date, asof) if basis_date else None
        lag_basis = "business_days"
    signal_basis = str(row.get("signal_asof") or "").strip()[:10] or None
    signal_lag = None
    if signal_basis and basis_date:
        signal_lag = _sessions_between(price_history, signal_basis, basis_date)
        if signal_lag is None:
            signal_lag = _business_days_between(signal_basis, basis_date)
    stale = lag is not None and lag > STALE_BASIS_MAX_SESSIONS
    return {
        "basis_date": basis_date or None,
        "basis_source": basis_source,
        "run_asof": asof,
        "lag": lag,
        "lag_basis": lag_basis if lag is not None else "unresolved",
        "max_lag": STALE_BASIS_MAX_SESSIONS,
        "state": "stale" if stale else "current",
        # The SIGNAL's own vintage — disclosed, never a refusal reason.  A late signal
        # stops implying a late PRICE because the plan waits at its zone.
        "signal_basis_date": signal_basis,
        "signal_lag_sessions": signal_lag,
        "era": SELECTION_ERA,
    }


# ---------------------------------------------------------------------------
# Structure-anchored entry zones (ANTICIPATION §6.9 R3)
# ---------------------------------------------------------------------------
# THE DEFECT (§6.9, operator-verified): even the patience picks were up hard over the
# prior two sessions at admission, because the plan's entry has always been the asof
# CLOSE.  A signal that arrives late therefore implies a late PRICE, and the two are
# not the same thing: the structure the name is turning at does not move just because
# our state machine took another two sessions to label it.
#
# THE ANSWER: every plan carries the structure-anchored band it is willing to buy at,
# and the plan's stance names the band.  The disclosed `entry` stays the point-in-time
# price_basis close — a plan never fabricates a fill it did not get — but the reader is
# told to WAIT at the zone instead of paying the print.  The R4 receipt (#5007, 933
# fires / 504 sessions) measured exactly this mechanic: median entry-vs-low 7.26% →
# 2.29%, half-stable ±0.75pp.  The ZONE is what reproduced there; the RESET_TURN signal
# standalone did not, and is not promoted here either.
#
# Three zone classes, in precedence order:
#   wait_reset  — the name is stretched on the daily AND the 3D stochastic (the NVDA
#                 acceptance).  Reset band only, and the plan may never ask the reader
#                 to pay above the last print.
#   reset_band  — a patience-status row.  The board's own MA10/MA20 reset band; this is
#                 the ADAM acceptance shape (a Continuation/Ready leader-pullback's zone
#                 is the RESET band with chase-above at the pullback high, never the
#                 post-pop range).
#   accumulate  — a confirmation-status row: the cycle-low-anchored accumulate band the
#                 entry ladder already computes, with its chase line above spot.

ZONE_SCHEMA = "prophet.entry_zone/v1"
ZONE_CLASS_ACCUMULATE = "accumulate"
ZONE_CLASS_RESET_BAND = "reset_band"
ZONE_CLASS_WAIT_RESET = "wait_reset"

ZONE_STANCE_ACCUMULATE = "accumulate"
ZONE_STANCE_WAIT = "wait"
ZONE_STANCE_STARTER = "starter"

#: How long a zone stays live before its expiry rule applies.  Floor, in sessions — the
#: board's own ``entry_signal.timing.opens_in_days_hi`` raises it when the ladder says
#: the window opens later than that.  10 sessions ≈ two trading weeks, the span over
#: which a daily-cycle reset either happens or the premise has moved on.
ZONE_EXPIRY_SESSIONS_MIN = 10

#: Expiry classes.  A washout-class name is V-RISK: a washed-out recovery frequently
#: never revisits its band (the BABA 90→128 and NVDA V-bottom receipts), so letting the
#: zone simply die would mean the plan misses the whole move it correctly anticipated.
#: A pullback-class name in an intact uptrend has no such asymmetry — if the reset never
#: comes, the premise was that the reset was coming, and the plan expires honestly.
ZONE_CONVERSION_WASHOUT = "washout"
ZONE_CONVERSION_PULLBACK = "pullback"


# ---------------------------------------------------------------------------
# ZONE-BASIS COPY — plain-word EN/ZH for every token the payload can carry
# ---------------------------------------------------------------------------
# `entry_zone` is whitelisted onto the published `index.json` row (the Terminal and the
# showcase read that file, not the per-plan JSON), so every string in it is USER-VISIBLE
# copy, not an internal note.
#
# THE DEFECT THIS FIXES.  The leader-pullback branch below used to interpolate the
# ORGAN'S OWN STATE ENUM straight into the sentence —
#
#     f"leader pullback ({leader_pullback.get('state') or 'reset'}) — reset band, ..."
#
# which renders as "leader pullback (RESET_TURN) — …" the moment the organ's coverage is
# actually published.  It never surfaced before because nothing published
# `site/anticipationdata/us_leader_pullback.json`, so `is_leader_pullback` was False on
# every production row and the branch was unreachable.  Shipping the publisher makes it
# reachable, so the copy has to be plain words first.
#
# The same audit applies to `conversion_evidence`, which carried a MODULE NAME and two
# more raw states ("us_basket_turn washout/turning membership") and a board slug
# ("board lane=bottoming").
#
# HOUSE LAW (docs/DESIGN_DOCTRINE.md, glance tier): no raw enum tokens, no internal state
# or study names, no untranslated stats, no falsifier/refutation vocabulary. ZH is written
# as ZH, not as a gloss of the English clause order.
# `tests/test_prophet_zone_basis_copy.py` enumerates every reachable branch and fails on a
# raw token, a missing ZH half, or falsifier vocabulary.

#: Organ state (engine.us_leader_pullback) → plain words. Only PULLBACK and RESET_TURN can
#: reach here (`us_early_turn.LEADER_PULLBACK_CONTEXT_STATES`), but the map is EXHAUSTIVE
#: over the organ's vocabulary so a future context-set widening cannot leak a token: an
#: unmapped state falls back to the generic phrase, never to the enum.
ZONE_LEADER_STATE_COPY: dict[str, dict[str, str]] = {
    "PULLBACK": {
        "en": "a market leader in a controlled pullback",
        "zh": "强势股正在有序回踩",
    },
    "RESET_TURN": {
        "en": "a market leader whose pullback has just turned back up",
        "zh": "强势股回踩后刚刚重新走强",
    },
    "RESUMED": {
        "en": "a market leader that has already resumed its advance",
        "zh": "强势股已经重拾升势",
    },
    "LEADER": {
        "en": "a market leader with no pullback under way",
        "zh": "强势股目前没有回踩",
    },
    "NONE": {
        "en": "a market leader in a controlled pullback",
        "zh": "强势股正在有序回踩",
    },
}
#: Used when the organ named no state at all — never the word "None", never an enum.
ZONE_LEADER_STATE_FALLBACK = {
    "en": "a market leader in a controlled pullback",
    "zh": "强势股正在有序回踩",
}

#: Band provenance → plain words. Keys are the exact strings `_reset_band_or_board` and
#: `engine.us_early_turn.reset_band` can return; an unknown string is REPLACED by the
#: generic phrase rather than passed through, so a new band source cannot ship raw.
ZONE_BAND_BASIS_COPY: dict[str, dict[str, str]] = {
    "entry ladder reset band": {
        "en": "the pullback band the entry ladder already showed",
        "zh": "入场阶梯原本给出的回踩区间",
    },
    "MA10/MA20 reset": {
        "en": "the 10- and 20-day average band under the price",
        "zh": "价格下方的 10 日与 20 日均线区间",
    },
    "1-2x ATR band (price already under both short MAs)": {
        "en": "one to two average daily ranges below the price, since it is already "
              "under both short averages",
        "zh": "价格已跌破两条短期均线，区间取其下方一到两个日均波幅",
    },
    "board band (reset band unresolved)": {
        "en": "the band already on the board, because a pullback band could not be drawn",
        "zh": "沿用看板已有区间，因为无法画出回踩区间",
    },
}
ZONE_BAND_BASIS_FALLBACK = {
    "en": "the band already on the board",
    "zh": "看板已有的区间",
}

#: Conversion evidence → plain words. The first key replaces a string that named an
#: internal module AND two raw organ states.
ZONE_CONVERSION_EVIDENCE_COPY: dict[str, dict[str, str]] = {
    "group_washout": {
        "en": "its group has already sold off hard and is starting to turn",
        "zh": "所属板块已经深度回落，并开始转向",
    },
    "board_bottoming": {
        "en": "the board reads this as a name coming off a low",
        "zh": "看板把它归入低位回升的一类",
    },
    "no_washout": {
        "en": "nothing here says this name has sold off hard first",
        "zh": "没有迹象显示该股先经历过深度回落",
    },
}


def _copy(table: Mapping[str, Mapping[str, str]], key: Any,
          fallback: Mapping[str, str]) -> tuple[str, str]:
    """``(en, zh)`` for ``key``; the fallback PHRASE for anything unmapped.

    Never returns the key.  That is the whole point: a token this table has not been
    taught is a token the reader must not see.
    """
    row = table.get(str(key or "").strip().upper()) or table.get(str(key or "").strip())
    if not isinstance(row, Mapping):
        row = fallback
    return str(row.get("en") or fallback["en"]), str(row.get("zh") or fallback["zh"])


def _zone_expiry_sessions(row: Mapping[str, Any]) -> int:
    """Sessions the zone stays live: the ladder's own window, floored."""
    es = row.get("entry_signal")
    hi = None
    if isinstance(es, Mapping):
        timing = es.get("timing")
        if isinstance(timing, Mapping):
            hi = timing.get("opens_in_days_hi")
    try:
        window = int(hi) if hi is not None else 0
    except (TypeError, ValueError):
        window = 0
    return max(ZONE_EXPIRY_SESSIONS_MIN, window)


def _add_business_days(start: str, n: int) -> str | None:
    try:
        stamp = pd.Timestamp(start)
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(stamp) or n <= 0:
        return None
    span = pd.bdate_range(stamp + pd.Timedelta(days=1), periods=n)
    return str(span[-1].date()) if len(span) else None


def zone_conversion_class(row: Mapping[str, Any],
                          washout_context: bool = False) -> tuple[str, str, str]:
    """``(conversion_class, evidence_en, evidence_zh)`` — V-risk, or a plain pullback?

    Washout evidence, in the order it is trusted: the ``us_basket_turn`` organ's own
    state for a basket this ticker is an active member of (passed in by the caller as
    ``washout_context``), then the board's own bottoming-vs-continuation lane.  Either
    is enough — this decides whether an unfilled zone CONVERTS or EXPIRES, and the
    asymmetric cost is missing a V-shaped recovery entirely.

    MEASURED EXCLUSION (2026-08-09, on the committed 2026-08-07 board): the row's
    ``coiled.washout_ctx`` flag is NOT used, despite reading like the obvious input.
    It is true on 71 of 79 buy rows — a near-constant, not a discriminator — and
    conditioning on it would have made 46 of 47 plans convert, which is a conversion
    rule with no class in it.  The organ state (8/79) and the board lane (34/79
    bottoming vs 35 continuation) are the reads that actually split the population.

    The evidence half is USER-VISIBLE COPY and ships as an EN/ZH pair: it used to name an
    internal module and two raw organ states ("us_basket_turn washout/turning membership")
    and a board slug ("board lane=bottoming").  The machine-readable half is the returned
    ``conversion_class``, which is what any caller should branch on.
    """
    if washout_context:
        return (ZONE_CONVERSION_WASHOUT,
                *_copy(ZONE_CONVERSION_EVIDENCE_COPY, "group_washout",
                       ZONE_CONVERSION_EVIDENCE_COPY["group_washout"]))
    if str(row.get("lane") or "").strip().lower() == "bottoming":
        return (ZONE_CONVERSION_WASHOUT,
                *_copy(ZONE_CONVERSION_EVIDENCE_COPY, "board_bottoming",
                       ZONE_CONVERSION_EVIDENCE_COPY["board_bottoming"]))
    return (ZONE_CONVERSION_PULLBACK,
            *_copy(ZONE_CONVERSION_EVIDENCE_COPY, "no_washout",
                   ZONE_CONVERSION_EVIDENCE_COPY["no_washout"]))


def build_entry_zone(
    row: Mapping[str, Any],
    *,
    entry: float,
    klass: str | None,
    price_basis_date: str,
    price_history: "pd.DataFrame | None" = None,
    extension: Mapping[str, Any] | None = None,
    washout_context: bool = False,
    early_turn: bool = False,
    leader_pullback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The structure-anchored band this plan waits at.

    ``entry`` remains the PIT close and is NOT moved by anything here — the zone is a
    separate, additive disclosure.  ``trigger`` is adjusted by the CALLER for a
    wait_reset plan (never above the last print); this function only reports what the
    zone is and which stance goes with it.
    """
    es = row.get("entry_signal") if isinstance(row.get("entry_signal"), Mapping) else {}
    board_zone = es.get("buy_zone") if isinstance(es.get("buy_zone"), Mapping) else {}
    low = board_zone.get("low")
    high = board_zone.get("high")
    chase_above = es.get("chase_above")
    both_extended = bool((extension or {}).get("both_extended"))
    is_leader_pullback = bool((leader_pullback or {}).get("leader_pullback"))

    def _reset_band_or_board(current_low: Any, current_high: Any) -> tuple[Any, Any, str]:
        """The MA10/MA20 reset band, falling back to whatever the board carried.

        A CONFIRMATION row carries the ACCUMULATE band (anchored at the cycle low and
        topped at spot), which is not a reset band at all — that is precisely the ADAM
        defect: the board printed 9.61-9.82 AT THE TOP of the pop while the constructive
        entry was the 8.40-8.70 reset.  A patience row whose band already sits below the
        last print is kept as-is.
        """
        if klass == ADMISSION_CLASS_PATIENCE and current_high is not None and entry \
                and float(current_high) < float(entry):
            return current_low, current_high, "entry ladder reset band"
        try:
            from engine.us_early_turn import reset_band  # noqa: PLC0415
            band = reset_band(price_history, price_basis_date, atr_pct=es.get("atr_pct"))
            if band.get("high") is not None:
                return band.get("low"), band.get("high"), str(band.get("basis"))
        except Exception as exc:  # noqa: BLE001 — a zone never breaks origination
            log.info("prophet_bridge: reset band unavailable (%s)", exc)
        return current_low, current_high, "board band (reset band unresolved)"

    # Every `basis`/`basis_zh` below is USER-VISIBLE COPY on the published index row.
    # `band_basis` is the raw provenance string `_reset_band_or_board` returns; it is
    # NEVER interpolated directly — `_copy` maps it to plain words in both languages, and
    # an unmapped source falls back to a phrase rather than passing through.
    if both_extended:
        zone_class = ZONE_CLASS_WAIT_RESET
        stance = ZONE_STANCE_WAIT
        low, high, band_basis = _reset_band_or_board(low, high)
        band_en, band_zh = _copy(ZONE_BAND_BASIS_COPY, band_basis,
                                 ZONE_BAND_BASIS_FALLBACK)
        basis = (f"the daily and 3-day readings are both stretched, so this plan only "
                 f"buys a pullback — {band_en}")
        basis_zh = f"日线与三日读数都已拉伸，因此本计划只在回踩时买入——{band_zh}"
        chase_above = entry
    elif is_leader_pullback:
        # §6.8(b) ZONE LAW, ADAM acceptance case #2: a Continuation/Ready leader
        # pullback's zone is the RESET BAND and the chase line is the PULLBACK HIGH —
        # never the post-pop range.  The pullback high comes from the organ that owns
        # the state (#5007); without it the reset band's own top is the honest ceiling,
        # and it is never allowed to sit above the last print.
        zone_class = ZONE_CLASS_RESET_BAND
        stance = ZONE_STANCE_WAIT
        low, high, band_basis = _reset_band_or_board(low, high)
        pullback_high = (leader_pullback or {}).get("pullback_high")
        try:
            chase_above = float(pullback_high) if pullback_high is not None else None
        except (TypeError, ValueError):
            chase_above = None
        if chase_above is None:
            chase_above = high if high is not None else entry
        # THE RAW-TOKEN SEAM. `leader_pullback["state"]` is the organ's own enum
        # (PULLBACK / RESET_TURN); it used to be interpolated verbatim and would have
        # rendered "leader pullback (RESET_TURN)" the night the coverage publisher went
        # live. It is mapped, never printed.
        state_en, state_zh = _copy(ZONE_LEADER_STATE_COPY,
                                   (leader_pullback or {}).get("state"),
                                   ZONE_LEADER_STATE_FALLBACK)
        band_en, band_zh = _copy(ZONE_BAND_BASIS_COPY, band_basis,
                                 ZONE_BAND_BASIS_FALLBACK)
        basis = (f"{state_en} — wait for the pullback band and do not pay up past the "
                 f"pullback high ({band_en})")
        basis_zh = f"{state_zh}——在回踩区间等待，不要追过回踩前的高点（{band_zh}）"
    elif klass == ADMISSION_CLASS_PATIENCE:
        zone_class = ZONE_CLASS_RESET_BAND
        stance = ZONE_STANCE_WAIT
        basis = ("the 10- and 20-day average band under the last price, from the entry "
                 "ladder")
        basis_zh = "最新价下方的 10 日与 20 日均线区间，来自入场阶梯"
    else:
        zone_class = ZONE_CLASS_ACCUMULATE
        stance = ZONE_STANCE_ACCUMULATE
        basis = "the build-in band anchored at the cycle low, from the entry ladder"
        basis_zh = "以本轮低点为锚的分批建仓区间，来自入场阶梯"

    if early_turn:
        stance = ZONE_STANCE_STARTER

    conversion_class, conversion_evidence, conversion_evidence_zh = zone_conversion_class(
        row, washout_context)
    sessions = _zone_expiry_sessions(row)

    def _px(value: Any) -> float | None:
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        return round(out, 4) if math.isfinite(out) and out > 0 else None

    low_px, high_px = _px(low), _px(high)
    pct_from_entry = None
    if high_px is not None and entry:
        mid = (high_px + (low_px if low_px is not None else high_px)) / 2.0
        pct_from_entry = round(100.0 * (mid / float(entry) - 1.0), 2)

    return {
        "schema": ZONE_SCHEMA,
        "low": low_px,
        "high": high_px,
        "chase_above": _px(chase_above),
        "pct_from_entry": pct_from_entry,
        "zone_class": zone_class,
        "stance": stance,
        # Plain-word copy, bilingual by construction — the EN and ZH halves are written
        # in the same branch so they can never desync (the house law every other
        # EN/ZH pair on this payload follows).
        "basis": basis,
        "basis_zh": basis_zh,
        "price_basis_date": price_basis_date,
        "expiry_sessions": sessions,
        "expiry_date": _add_business_days(price_basis_date, sessions),
        "conversion_class": conversion_class,
        "conversion_evidence": conversion_evidence,
        "conversion_evidence_zh": conversion_evidence_zh,
        "converts_on_expiry": conversion_class == ZONE_CONVERSION_WASHOUT,
        # Nullable and NAMED: a starved extension read and an honest "not stretched"
        # must never be indistinguishable.  A name whose price store cannot support the
        # read keeps its board zone — inventing a stance for an unmeasurable name would
        # be worse than saying the read is missing, and the count ships in intake_stats.
        "extension": dict(extension) if extension else None,
        "leader_pullback": dict(leader_pullback) if leader_pullback else None,
        "era": SELECTION_ERA,
    }


def evaluate_entry_zone(
    plan: Mapping[str, Any],
    price_history: "pd.DataFrame | None",
    asof: str,
) -> dict[str, Any]:
    """Nightly re-evaluation of a plan's zone: filled, still live, expired, converted.

    THE CONVERSION (§6.9 R3, operator chart review 2026-08-08): a washout-class zone
    that was never filled by its expiry does NOT die — it converts to a STARTER stance.
    V-shaped washout recoveries frequently never revisit the band, and a plan that
    correctly anticipated the turn should not miss the entire move on a technicality.
    A pullback-class zone in an intact uptrend expires instead: there, "the reset never
    came" falsifies the premise rather than confirming it.

    PURE FUNCTION over the plan + its PIT tape.  It writes nothing: plan JSONs are
    immutable publication records and corrections are an append-only overlay, so the
    converted stance is DERIVED every night and rendered, never back-written into the
    originating artifact.
    """
    zone = plan.get("entry_zone")
    out: dict[str, Any] = {
        "state": "none", "filled": False, "filled_date": None,
        "expired": False, "converted": False, "stance": None,
        "sessions_remaining": None, "reason": None,
    }
    if not isinstance(zone, Mapping) or zone.get("high") is None:
        out["reason"] = "plan carries no entry zone (pre-R3 plan)"
        return out

    high = float(zone["high"])
    start = str(zone.get("price_basis_date") or plan.get("price_basis_date") or "")[:10]
    expiry = str(zone.get("expiry_date") or "")[:10]
    out["stance"] = zone.get("stance")

    # FILLED := the tape traded INTO the band (intraday low at or below the band top)
    # at any point from the plan's price basis onward.  `low` is the honest column;
    # a close-only store would systematically under-report fills, so it falls back with
    # the substitution named rather than pretending precision it does not have.
    filled_date = None
    basis_col = "low"
    if price_history is not None and not getattr(price_history, "empty", True):
        try:
            frame = price_history[price_history.index >= pd.Timestamp(start)] if start \
                else price_history
            frame = frame[frame.index <= pd.Timestamp(asof)]
            if "low" not in frame.columns:
                basis_col = "close"
            series = frame[basis_col].dropna() if basis_col in frame.columns else None
            if series is not None and not series.empty:
                hits = series[series <= high]
                if not hits.empty:
                    filled_date = str(pd.Timestamp(hits.index[0]).date())
        except Exception as exc:  # noqa: BLE001
            out["reason"] = f"zone fill unreadable: {exc}"
    out["fill_basis"] = basis_col

    if filled_date is not None:
        out.update({"state": "filled", "filled": True, "filled_date": filled_date})
        return out

    remaining = _business_days_between(asof, expiry) if expiry else None
    out["sessions_remaining"] = remaining
    expired = bool(expiry) and expiry < str(asof)[:10]
    if not expired:
        out["state"] = "live"
        return out

    out["expired"] = True
    if zone.get("converts_on_expiry"):
        out.update({
            "state": "converted",
            "converted": True,
            "stance": ZONE_STANCE_STARTER,
            "reason": (
                "washout-class zone unfilled at expiry — a V-shaped recovery does not "
                "revisit its band; the plan converts to a starter stance"),
        })
    else:
        out.update({
            "state": "expired",
            "stance": ZONE_STANCE_WAIT,
            "reason": (
                "pullback-class zone unfilled at expiry — the reset the plan was "
                "waiting for did not arrive"),
        })
    return out


# ---------------------------------------------------------------------------
# Thesis template (deterministic, no LLM)
# ---------------------------------------------------------------------------

_VALIDATED_PAT = re.compile(r"\b(validated|已验证)\b", re.IGNORECASE)
_VALIDATED_PAT_ZH = re.compile(r"已验证", re.IGNORECASE)
_VALIDATED_PAT_EN = re.compile(r"\bvalidated\b", re.IGNORECASE)


def _sanitize_thesis_text(text: str) -> str:
    """Strip forbidden 'validated'/'已验证' tokens from thesis driver/caution strings.

    The plan JSON is rendered user-facing (terminal oracle-tab). House law forbids
    affirmative 'validated' claims outside the allowlist gate. Source conviction
    drivers/cautions may carry these tokens (e.g. 'validated risk gate: trim').
    Replace them with 'risk gate' to preserve the semantic content without the claim.
    """
    return _VALIDATED_PAT.sub("risk gate", text)


def _sanitize_thesis_text_zh(text: str) -> str:
    """ZH counterpart of _sanitize_thesis_text — replaces forbidden tokens with ZH equivalents.
    '已验证' → '风险管控'; 'validated' (EN in ZH context) → '风险管控'."""
    text = _VALIDATED_PAT_ZH.sub("风险管控", text)
    text = _VALIDATED_PAT_EN.sub("风险管控", text)
    return text


_GOVERNMENT_REVENUE_METRICS = (
    "ttm_obligations",
    "prior_ttm_obligations",
    "award_velocity_yoy_pct",
    "velocity_basis",
    "latest_complete_month",
    "funded_capacity_observed",
    "potential_capacity_observed",
    "funded_backlog",
    "total_backlog",
    "backlog_sample_coverage_pct",
    "awards_visible",
    "awards_with_current_value",
    "backlog_scope",
    "funding_pct",
    "net_award_action_flow_90d",
    "positive_award_action_flow_90d",
    "award_action_flow_basis",
    "modification_impulse_90d",
    "deobligations_90d",
    "agency_concentration",
    "program_concentration",
)


def _government_revenue_freshness(
    payload: dict,
    reference: Any | None = None,
) -> tuple[str, str, str]:
    """Read elapsed-time-aware governed health rails.

    The award-event rail is returned alongside the aggregate because
    ``effective_freshness`` deliberately EXCLUDES it from the aggregate
    (``engine/government_revenue/freshness.py`` line 171): a dead award-event
    spine leaves ``status == "ok"``.  ``reviewed_award_change_context`` then
    gates on that rail on its own, so dropping it here would publish an empty
    ``award_change_events`` list with no stated cause — indistinguishable from
    a ticker that genuinely had no award changes.  Mastermind already discloses
    it (``engine/neuralweb/mastermind_context.py`` line 2101); this rail must
    not be the silent sibling.
    """
    evaluated = effective_freshness(payload, reference=reference)
    return (
        str(evaluated["status"]),
        str(evaluated["opportunities"]),
        str(evaluated.get("award_events") or "unknown"),
    )


def _load_government_revenue_context(
    standouts_path: Path,
    asof: str | None = None,
) -> dict[str, dict]:
    """Load sparse official-procurement context after candidate selection.

    The workbench is deliberately an annotation source, not an originating
    engine.  This function is called only *after* ``select_candidates`` and its
    output may reach prose/provenance fields only.  Missing, malformed, or
    mismatched artifacts degrade to ``{}`` so the prior plan output remains
    byte-identical when no procurement evidence exists.
    """
    candidates: list[Path] = []
    # Normal layout: <repo>/site/factordata/us_standouts.json.
    try:
        candidates.append(standouts_path.resolve().parents[2])
    except (IndexError, OSError):
        pass
    candidates.append(Path(__file__).resolve().parent.parent)

    payload: dict | None = None
    seen: set[Path] = set()
    for repo in candidates:
        if repo in seen:
            continue
        seen.add(repo)
        path = repo / "data" / "government_revenue" / "latest.json"
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(loaded, dict):
            payload = loaded
            break

    if not payload or payload.get("schema_version") != "company_government_revenue.v1":
        return {}

    # Prophet's ``asof`` is the sole knowledge clock. A current workbench must
    # never annotate a historical/backfill plan. Date-only anchors mean evidence
    # known through the end of that UTC day; malformed/missing knowledge stamps
    # fail closed whenever a cutoff is supplied.
    cutoff = None
    if asof is not None:
        try:
            cutoff = pd.Timestamp(asof)
            if cutoff.tzinfo is None:
                cutoff = cutoff.tz_localize("UTC")
            else:
                cutoff = cutoff.tz_convert("UTC")
            if len(str(asof).strip()) <= 10:
                cutoff = cutoff.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
            payload_known = pd.Timestamp(payload.get("known_at"))
            payload_day = pd.Timestamp(payload.get("as_of"))
            if pd.isna(payload_known) or pd.isna(payload_day):
                return {}
            payload_known = (
                payload_known.tz_localize("UTC")
                if payload_known.tzinfo is None
                else payload_known.tz_convert("UTC")
            )
            payload_day = (
                payload_day.tz_localize("UTC")
                if payload_day.tzinfo is None
                else payload_day.tz_convert("UTC")
            )
        except (TypeError, ValueError, OverflowError):
            return {}
        if payload_known > cutoff or payload_day > cutoff:
            return {}

    overall_status, opportunity_status, award_event_status = _government_revenue_freshness(
        payload,
        reference=cutoff,
    )
    if overall_status != "ok":
        # Prophet prose must never make an aged or degraded procurement snapshot
        # look current. The source remains visible on its governed workbench.
        return {}
    opportunities_current = opportunity_status == "ok"

    out: dict[str, dict] = {}
    for company in payload.get("companies") or []:
        if not isinstance(company, dict):
            continue
        ticker = str(company.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        raw_metrics = company.get("metrics") or {}
        metrics = {
            key: raw_metrics.get(key)
            for key in _GOVERNMENT_REVENUE_METRICS
            if raw_metrics.get(key) is not None
        }
        context = {
            "as_of": payload.get("as_of"),
            "known_at": payload.get("known_at"),
            "freshness": {
                "status": overall_status,
                "opportunities": opportunity_status,
                "award_events": award_event_status,
            },
            "metrics": metrics,
            "recompete_candidates": (company.get("recompete_candidates") or [])[:3],
            "opportunity_candidates": (
                (company.get("opportunity_candidates") or [])[:2]
                if opportunities_current
                else []
            ),
            "catalyst_facts": (company.get("catalyst_facts") or [])[:3],
            "award_change_events": reviewed_award_change_context(
                payload, ticker, cutoff
            ),
            "confidence": company.get("confidence"),
            "provenance": (company.get("provenance") or [])[:3],
            "allowed_behavior": "annotate_only",
            "authority": {
                "can_add_candidates": False,
                "can_rank": False,
                "can_size": False,
                "can_gate": False,
                "can_escalate": False,
            },
            "honesty_note": (
                "official procurement context; obligations are not recognized revenue "
                "and award ceilings are not GAAP backlog"
            ),
        }
        out[ticker] = context
    return out


def _load_earnings_evidence_context(
    standouts_path: Path, tickers: list[str], *, asof: str,
) -> dict[str, dict[str, Any]]:
    """Load exact earnings evidence strictly after candidate selection.

    This is an inert annotation seam. It never enters ``select_candidates`` or
    any geometry/horizon/option calculation, and every returned packet carries
    explicit false signal-authority permissions.
    """
    from engine.neuralweb.earnings_context_reader import read_earnings_evidence  # noqa: PLC0415

    candidate_root = standouts_path.resolve().parent
    for ancestor in (candidate_root, *candidate_root.parents):
        if (ancestor / "engine").is_dir() and (ancestor / "site").is_dir():
            candidate_root = ancestor
            break
    out: dict[str, dict[str, Any]] = {}
    for ticker in sorted(set(tickers)):
        result = read_earnings_evidence(
            {"ticker": ticker, "as_of": asof}, root=candidate_root,
        )
        if result.get("available") is True and result.get("authority") == "context_only":
            out[ticker] = result
    return out


def _earnings_plan_annotation(context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep only the citation-bearing display subset a plan renderer can use."""
    if not context or context.get("available") is not True:
        return None
    permissions = context.get("permissions") if isinstance(context.get("permissions"), dict) else {}
    if permissions.get("prophet_authority") is not False or permissions.get("may_rank") is not False:
        return None
    return {
        "schema": "earnings.context_annotation/v1",
        "authority": "context_only",
        "event": context.get("event"),
        "categories": list(context.get("categories") or [])[:8],
        "facts": list(context.get("facts") or [])[:2],
        "receipts": context.get("receipts"),
        "links": context.get("links"),
        "permissions": permissions,
        "note": "attached after selection; cannot change rank, confidence, geometry, horizon, options, or tranches",
    }


def _government_revenue_sentence(context: dict | None) -> tuple[str, str] | None:
    """Return deterministic EN/ZH plan annotation from procurement facts."""
    if not context:
        return None
    freshness = context.get("freshness")
    if isinstance(freshness, dict) and str(freshness.get("status") or "").lower() != "ok":
        return None
    metrics = context.get("metrics") or {}
    velocity = metrics.get("award_velocity_yoy_pct")
    latest_month = metrics.get("latest_complete_month")
    funded_backlog = metrics.get("funded_capacity_observed")
    if funded_backlog is None:
        funded_backlog = metrics.get("funded_backlog")

    parts_en: list[str] = []
    parts_zh: list[str] = []
    if isinstance(velocity, (int, float)) and math.isfinite(float(velocity)):
        stamp_en = f" through {latest_month}" if latest_month else ""
        stamp_zh = f"（截至 {latest_month}）" if latest_month else ""
        parts_en.append(f"official award-obligation velocity was {float(velocity):+.1f}% YoY{stamp_en}")
        parts_zh.append(f"官方合同义务金额同比增速为 {float(velocity):+.1f}%{stamp_zh}")
    if isinstance(funded_backlog, (int, float)) and math.isfinite(float(funded_backlog)):
        parts_en.append(f"observed funded contract capacity was ${float(funded_backlog) / 1_000_000_000:.2f}B")
        parts_zh.append(f"观察到的已拨款合同余量为 ${float(funded_backlog) / 1_000_000_000:.2f}B")
    opportunity = next(
        (
            row for row in context.get("opportunity_candidates") or []
            if isinstance(row, dict)
            and str(row.get("source_url") or "").startswith(
                ("https://sam.gov/", "https://api.sam.gov/")
            )
        ),
        None,
    )
    if opportunity:
        title = re.sub(r"<[^>]*>", " ", str(opportunity.get("title") or "SAM.gov opportunity"))
        title = " ".join(title.split())[:96]
        days = opportunity.get("days_to_response")
        timing_en = (
            f" with a response due in {days} days"
            if isinstance(days, int) and days >= 0
            else ""
        )
        timing_zh = (
            f"，距响应截止还有 {days} 天"
            if isinstance(days, int) and days >= 0
            else ""
        )
        parts_en.append(
            f"SAM.gov lists “{title}”{timing_en}; its issuer link is rule-based, not a bidder or award forecast"
        )
        parts_zh.append(
            f"SAM.gov 列出“{title}”{timing_zh}；发行人关联来自规则匹配，并非投标方或授标预测"
        )
    award_change = next(
        (
            row for row in context.get("award_change_events") or []
            if isinstance(row, dict) and row.get("event_type")
        ),
        None,
    )
    if award_change:
        event_type = str(award_change.get("event_type") or "award change").replace("_", " ")
        recipient = " ".join(str(award_change.get("recipient_name") or "covered recipient").split())[:96]
        effective = award_change.get("effective_at")
        timing_en = f" effective {str(effective)[:10]}" if effective else ""
        timing_zh = f"（生效日 {str(effective)[:10]}）" if effective else ""
        parts_en.append(
            f"USAspending recorded {event_type} for {recipient}{timing_en} through a reviewed issuer path; it is not recognized revenue"
        )
        parts_zh.append(
            f"USAspending 记录了 {recipient} 的 {event_type}{timing_zh}，并经核验的发行人路径关联；这不等同于确认收入"
        )
    if not parts_en:
        return None
    return (
        "Government-revenue context: " + "; ".join(parts_en)
        + ". Context only—obligations are not recognized revenue and contract capacity is not GAAP backlog.",
        "政府收入背景：" + "；".join(parts_zh)
        + "。仅作背景注释；合同义务金额不等同于确认收入，合同余量不等同于 GAAP 在手订单。",
    )


def _build_thesis(
    ticker: str,
    b: dict,
    opt_ctx: dict | None = None,
    government_revenue_ctx: dict | None = None,
) -> str:
    """
    OURS: Build a 2-3 sentence deterministic thesis woven from the candidate's
    actual drivers, cautions, and technical flags (above200, weekly_bull, coiled,
    washout_ctx, dc phase).  Mechanical, specific, no predictive claims, no
    "validated".  Display-only.

    OEU M-PRO: when ``opt_ctx`` carries dealer-positioning context for this name
    (lib.options_context.load_gex_walls), ONE template sentence about the wall
    overhead is appended before the honesty footer.  Template string, no LLM,
    past tense + as-of stamp (a thesis is written once and read for weeks).
    ``opt_ctx=None`` → byte-identical to the pre-M-PRO thesis.
    """
    conv = b.get("conviction") or {}
    es = b.get("entry_signal") or {}
    hold = b.get("hold") or {}
    drivers = conv.get("drivers", []) or []
    cautions = conv.get("cautions", []) or []
    score = conv.get("score", "N/A")
    band = conv.get("band", "N/A")

    # ── Sentence 1: technical setup summary ──────────────────────────────────
    tech_flags: list[str] = []
    if es.get("above200"):
        tech_flags.append("above 200-day moving average")
    if es.get("weekly_bull"):
        tech_flags.append("weekly structure bullish")
    if es.get("coiled"):
        tech_flags.append("coiled compression setup")
    washout = es.get("washout_ctx") or hold.get("washout_ctx")
    if washout:
        tech_flags.append("post-washout recovery context")
    dc_phase = hold.get("dc_phase") or es.get("dc_phase")
    if dc_phase:
        tech_flags.append(f"Donchian phase: {dc_phase}")

    entry_grade = es.get("entry_grade") or ""
    archetype = b.get("archetype") or b.get("setup_type") or ""

    s1_parts = [f"{ticker} — conviction {score}/100 ({band})"]
    if tech_flags:
        s1_parts.append(f"Technical context: {'; '.join(tech_flags[:3])}.")
    elif entry_grade:
        s1_parts.append(f"Entry grade: {entry_grade}.")
    if archetype:
        s1_parts.append(f"Setup type: {archetype}.")
    sentence1 = " ".join(s1_parts).strip()

    # ── Sentence 2: conviction drivers (actual strings from the engine) ───────
    sentence2 = ""
    if drivers:
        sanitized = [_sanitize_thesis_text(str(d)) for d in drivers[:3]]
        sentence2 = f"Drivers: {'; '.join(sanitized)}."

    # ── Sentence 3: cautions and trust tier ──────────────────────────────────
    sentence3_parts: list[str] = []
    if cautions:
        sanitized_c = [_sanitize_thesis_text(str(c)) for c in cautions[:2]]
        sentence3_parts.append(f"Cautions: {'; '.join(sanitized_c)}.")
    trust = _sanitize_thesis_text((conv.get("trust_tier") or {}).get("en", ""))
    if trust:
        sentence3_parts.append(f"Trust tier: {trust}.")
    sentence3 = " ".join(sentence3_parts)

    # ── Assemble + honesty footer ─────────────────────────────────────────────
    parts = [sentence1]
    if sentence2:
        parts.append(sentence2)
    if sentence3:
        parts.append(sentence3)
    _dealer = _dealer_sentence(opt_ctx, b)
    if _dealer:
        parts.append(_dealer[0])
    _government_revenue = _government_revenue_sentence(government_revenue_ctx)
    if _government_revenue:
        parts.append(_government_revenue[0])
    parts.append(
        "DISPLAY-ONLY: machine-generated from factor scores; no forward return"
        " guarantee; display-tier artifact."
    )
    return " ".join(parts)


def _dealer_sentence(opt_ctx: dict | None, b: dict) -> tuple[str, str] | None:
    """(en, zh) dealer-positioning sentence for the thesis, or None.

    Thin wrapper over lib.options_context.dealer_context_sentence so both thesis
    builders share ONE string and can never drift apart.  Never raises: a missing
    store, an unimportable lib, or a name with no options coverage all return None
    and the thesis reads exactly as it did before.
    """
    if not opt_ctx:
        return None
    try:
        from lib.options_context import dealer_context_sentence  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    entry = (b.get("entry_signal") or {}).get("spot")
    try:
        return dealer_context_sentence(opt_ctx, entry=entry)
    except Exception:  # noqa: BLE001 — display context is never fatal
        return None


def _build_thesis_zh(
    ticker: str,
    b: dict,
    opt_ctx: dict | None = None,
    government_revenue_ctx: dict | None = None,
) -> str:
    """ZH counterpart of _build_thesis — same deterministic template, translated strings.
    Data interpolation (ticker, score, prices) is unchanged; no LLM at runtime.
    ``opt_ctx`` carries the same M-PRO dealer-positioning context; the ZH sentence is
    the paired half of the EN one (lib.options_context.dealer_context_sentence)."""
    conv = b.get("conviction") or {}
    es = b.get("entry_signal") or {}
    hold = b.get("hold") or {}
    drivers_zh = conv.get("drivers_zh", []) or conv.get("drivers", []) or []
    cautions_zh = conv.get("cautions_zh", []) or conv.get("cautions", []) or []
    score = conv.get("score", "N/A")
    band = conv.get("band", "N/A")

    # Band translation map
    _BAND_ZH = {"high": "高", "constructive": "积极", "neutral": "中性",
                "caution": "留意", "avoid": "回避"}
    band_zh = _BAND_ZH.get(str(band), str(band))

    tech_flags_zh: list[str] = []
    if es.get("above200"):
        tech_flags_zh.append("站上200日均线")
    if es.get("weekly_bull"):
        tech_flags_zh.append("周线结构看多")
    if es.get("coiled"):
        tech_flags_zh.append("盘整蓄势形态")
    washout = es.get("washout_ctx") or hold.get("washout_ctx")
    if washout:
        tech_flags_zh.append("超跌回暖背景")
    dc_phase = hold.get("dc_phase") or es.get("dc_phase")
    if dc_phase:
        tech_flags_zh.append(f"唐奇安阶段: {dc_phase}")

    entry_grade = es.get("entry_grade") or ""
    archetype = b.get("archetype") or b.get("setup_type") or ""

    s1_parts = [f"{ticker} — 确信度 {score}/100（{band_zh}）"]
    if tech_flags_zh:
        s1_parts.append(f"技术背景: {'; '.join(tech_flags_zh[:3])}。")
    elif entry_grade:
        s1_parts.append(f"入场评级: {entry_grade}。")
    if archetype:
        s1_parts.append(f"形态类型: {archetype}。")
    sentence1 = " ".join(s1_parts).strip()

    sentence2 = ""
    if drivers_zh:
        sanitized = [_sanitize_thesis_text_zh(str(d)) for d in drivers_zh[:3]]
        sentence2 = f"驱动因素: {'; '.join(sanitized)}。"

    sentence3_parts: list[str] = []
    if cautions_zh:
        sanitized_c = [_sanitize_thesis_text_zh(str(c)) for c in cautions_zh[:2]]
        sentence3_parts.append(f"注意事项: {'; '.join(sanitized_c)}。")
    trust_zh = _sanitize_thesis_text_zh((conv.get("trust_tier") or {}).get("zh", ""))
    if trust_zh:
        sentence3_parts.append(f"可信度: {trust_zh}。")
    sentence3 = " ".join(sentence3_parts)

    parts = [sentence1]
    if sentence2:
        parts.append(sentence2)
    if sentence3:
        parts.append(sentence3)
    _dealer = _dealer_sentence(opt_ctx, b)
    if _dealer:
        parts.append(_dealer[1])
    _government_revenue = _government_revenue_sentence(government_revenue_ctx)
    if _government_revenue:
        parts.append(_government_revenue[1])
    parts.append("仅供展示：由因子分数机器生成；无前瞻收益保证；展示层级输出。")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Content blocks: what_to_do_now, profit_plan
# (deterministic templates — NO LLM — keyed to phase + price levels)
# ---------------------------------------------------------------------------

def _fmt_price(price: float | None) -> str:
    """Format a price for display, or return '—' if None."""
    if price is None:
        return "—"
    return f"${price:.2f}"


def _zone_lines_en(
    entry_zone: Mapping[str, Any] | None,
    zone_state: Mapping[str, Any] | None,
    entry: float | None,
    invalidation: float | None,
    t1: float | None,
) -> list[str] | None:
    """The pre-entry lines for a plan that carries a structure-anchored zone (§6.9 R3).

    ``None`` when the plan has no zone (every pre-R3 plan), so the caller falls through
    to the original trigger-based copy and nothing that shipped before this change
    reads differently.

    VOICE: window vocabulary, not certainty; no study names, no raw status slugs, no
    refutation language — a zone that does not fill is a window that closed, and the
    copy says so in those words.
    """
    if not isinstance(entry_zone, Mapping) or entry_zone.get("high") is None:
        return None
    low = _fmt_price(entry_zone.get("low"))
    high = _fmt_price(entry_zone.get("high"))
    chase = _fmt_price(entry_zone.get("chase_above"))
    inval_str = _fmt_price(invalidation)
    t1_str = _fmt_price(t1)
    band = f"{low}–{high}" if entry_zone.get("low") is not None else high
    state = (zone_state or {}).get("state")

    if state == "converted":
        return [
            f"The {band} zone never filled and the move ran without it. Treat this as a"
            f" starter-size window, not a full entry.",
            f"Keep the first piece small and let any pullback do the adding. Exit on a"
            f" close below {inval_str}.",
        ]
    if state == "expired":
        return [
            f"The {band} pullback window has closed without filling. No entry here —"
            f" wait for the next setup rather than paying up.",
            f"If you are already long from earlier, {inval_str} is still the exit level.",
        ]

    zone_class = entry_zone.get("zone_class")
    if zone_class == ZONE_CLASS_ACCUMULATE:
        lines = [
            f"Accumulate into the {band} zone. Do not pay above {chase} — above that"
            f" you are chasing the bar, not entering it.",
        ]
    elif zone_class == ZONE_CLASS_WAIT_RESET:
        lines = [
            f"Wait for a pullback into the {band} zone before starting. The daily and"
            f" 3-day reads are both stretched, so there is no entry at {chase} or above.",
        ]
    else:
        lines = [
            f"Wait for a pullback into the {band} zone before starting. No entry above"
            f" {chase}; the plan waits at the band rather than paying the last print.",
        ]
    if entry_zone.get("stance") == ZONE_STANCE_STARTER:
        lines.append(
            f"Starter size only — this is a window, not a certainty. Exit on a close"
            f" below {inval_str}.")
    else:
        lines.append(
            f"Keep the first tranche small; there is no need to rush. Exit on a close"
            f" below {inval_str}.")
    if t1 is not None:
        lines.append(
            f"If the zone fills, scale in gradually toward T1 ({t1_str}).")
    return lines[:3]


def _zone_lines_zh(
    entry_zone: Mapping[str, Any] | None,
    zone_state: Mapping[str, Any] | None,
    entry: float | None,
    invalidation: float | None,
    t1: float | None,
) -> list[str] | None:
    """ZH counterpart of :func:`_zone_lines_en` — same data, translated templates."""
    if not isinstance(entry_zone, Mapping) or entry_zone.get("high") is None:
        return None
    low = _fmt_price(entry_zone.get("low"))
    high = _fmt_price(entry_zone.get("high"))
    chase = _fmt_price(entry_zone.get("chase_above"))
    inval_str = _fmt_price(invalidation)
    t1_str = _fmt_price(t1)
    band = f"{low}–{high}" if entry_zone.get("low") is not None else high
    state = (zone_state or {}).get("state")

    if state == "converted":
        return [
            f"{band} 区间未被回踩，行情已自行走出。此处按试探性小仓位窗口对待，不是完整建仓。",
            f"首笔保持小仓位，后续回调再加。收盘跌破 {inval_str} 即离场。",
        ]
    if state == "expired":
        return [
            f"{band} 回调窗口已过期且未被触及。此处不入场——等待下一个形态，不要追价。",
            f"若此前已持有，{inval_str} 仍是离场位。",
        ]

    zone_class = entry_zone.get("zone_class")
    if zone_class == ZONE_CLASS_ACCUMULATE:
        lines = [
            f"在 {band} 区间内分批建仓。不要在 {chase} 之上买入——高于该位属于追价，而非入场。",
        ]
    elif zone_class == ZONE_CLASS_WAIT_RESET:
        lines = [
            f"等待价格回落至 {band} 区间再建仓。日线与三日读数均已拉伸，{chase} 及以上不入场。",
        ]
    else:
        lines = [
            f"等待价格回落至 {band} 区间再建仓。不要在 {chase} 之上买入；计划在区间等待，"
            f"而非按最新价追入。",
        ]
    if entry_zone.get("stance") == ZONE_STANCE_STARTER:
        lines.append(
            f"仅试探性小仓位——这是一个观察窗口，而非确定性结论。收盘跌破 {inval_str} 即离场。")
    else:
        lines.append(
            f"首笔保持小仓位，无需急于入场。收盘跌破 {inval_str} 即离场。")
    if t1 is not None:
        lines.append(f"若区间被触及，可逐步加仓至 T1（{t1_str}）。")
    return lines[:3]


def _build_what_to_do_now(
    phase: str,
    entry: float | None,
    trigger: float | None,
    invalidation: float | None,
    t1: float | None,
    t2: float | None,
    tranche: int = 1,
    *,
    entry_zone: Mapping[str, Any] | None = None,
    zone_state: Mapping[str, Any] | None = None,
) -> list[str]:
    """
    OURS: Build 2-3 numbered actionable lines keyed to lifecycle phase.
    Phase-dependent templates with price levels interpolated from plan fields.
    Display-only — no predictive claims.

    ``entry_zone``/``zone_state`` (§6.9 R3) replace the pre-entry lines with the
    structure-anchored band the plan waits at.  Both default to ``None``, so every
    caller and every pre-R3 plan keeps the exact copy it had.

    Returns a list of strings (one per numbered bullet).
    """
    trigger_str = _fmt_price(trigger)
    t1_str = _fmt_price(t1)
    t2_str = _fmt_price(t2)
    inval_str = _fmt_price(invalidation)

    if phase == "pre_trigger":
        zone_lines = _zone_lines_en(entry_zone, zone_state, entry, invalidation, t1)
        if zone_lines:
            return zone_lines
        lines = [
            f"Watch for price to reach the trigger level ({trigger_str}) before"
            f" entering. No position until trigger is confirmed.",
            f"Keep size small on initial entry; the buy zone extends from trigger"
            f" up to {t1_str} (T1). There is no need to rush.",
        ]
        if t2 is not None:
            lines.append(
                f"If trigger confirms, scale in gradually. Invalidation is"
                f" {inval_str}; exit on a close below that level."
            )
        return lines

    if phase in ("triggered_pre_t1", "triggered_pre_t1"):
        lines = [
            f"Trigger is confirmed. Hold the current position and let the trade"
            f" advance toward T1 ({t1_str}).",
            f"Add to the position on short-term pullbacks as long as price remains"
            f" above {inval_str} (invalidation level).",
        ]
        if t2 is not None:
            lines.append(
                f"Continue building as the move confirms. Full position size"
                f" targets T2 at {t2_str}. Do not chase — add into weakness."
            )
        return lines

    if phase in ("at_t1", "between_t1_t2"):
        lines = [
            f"T1 ({t1_str}) has been reached. Scale out approximately 40% of the"
            f" position here and trail stop to entry ({_fmt_price(entry)}).",
        ]
        if t2 is not None:
            lines.append(
                f"Hold the remaining position for T2 ({t2_str}). Trail stop"
                f" to breakeven to protect against a reversal."
            )
        lines.append(
            f"T2 at {t2_str} — let remaining position run unless price closes"
            f" back below {t1_str}."
            if t2 is not None else
            f"No T2 defined. Consider closing fully or trailing stop closely."
        )
        return lines[:3]

    if phase == "post_t1_failed_hold":
        return [
            f"Trade gave back gains after T1. Reduce exposure — trim to a smaller"
            f" position or exit if price closes below entry ({_fmt_price(entry)}).",
            f"Invalidation is {inval_str}. A close below that level is a full exit"
            f" signal.",
            f"Do not add here. Re-assess if price reclaims {t1_str} (T1) on volume.",
        ]

    if phase in ("at_t2", "post_t2"):
        lines = [
            f"T2 ({t2_str}) has been reached. Close the majority of the position"
            f" (approximately 60–80%).",
            f"Trail stop on any remaining shares to protect profits. Consider"
            f" a hard stop at T1 ({t1_str}) for the residual position.",
        ]
        return lines

    if phase == "overtime":
        return [
            f"Trade has exceeded its intended horizon without reaching T1 ({t1_str})."
            f" Reassess thesis strength.",
            f"Trim position to reduce time-decay risk. A close below"
            f" {inval_str} (invalidation) is a full exit signal.",
            f"Do not add to the position in overtime. Either T1 is reached soon"
            f" or the setup is deferred.",
        ]

    if phase == "invalidated":
        return [
            f"Invalidation level ({inval_str}) has been breached."
            f" Exit the full position.",
            f"This plan is no longer active. Do not hold through invalidation.",
        ]

    # Fallback for unknown phases
    return [
        f"Monitor price relative to trigger ({trigger_str}) and T1 ({t1_str}).",
        f"Exit on a close below invalidation ({inval_str}).",
    ]


def _build_what_to_do_now_zh(
    phase: str,
    entry: float | None,
    trigger: float | None,
    invalidation: float | None,
    t1: float | None,
    t2: float | None,
    tranche: int = 1,
    *,
    entry_zone: Mapping[str, Any] | None = None,
    zone_state: Mapping[str, Any] | None = None,
) -> list[str]:
    """ZH counterpart of _build_what_to_do_now — translated template strings,
    identical data interpolation. No LLM at runtime."""
    trigger_str = _fmt_price(trigger)
    t1_str = _fmt_price(t1)
    t2_str = _fmt_price(t2)
    inval_str = _fmt_price(invalidation)

    if phase == "pre_trigger":
        zone_lines = _zone_lines_zh(entry_zone, zone_state, entry, invalidation, t1)
        if zone_lines:
            return zone_lines
        lines = [
            f"等待价格触及触发点（{trigger_str}）后再入场，触发确认前不建仓。",
            f"初始建仓保持小仓位；买入区间从触发点延伸至 {t1_str}（T1），无需急于入场。",
        ]
        if t2 is not None:
            lines.append(
                f"触发确认后逐步加仓。止损参考位为 {inval_str}，收盘跌破该位即离场。"
            )
        return lines

    if phase in ("triggered_pre_t1",):
        lines = [
            f"触发点已确认。持有当前仓位，等待价格向 T1（{t1_str}）推进。",
            f"只要价格维持在 {inval_str}（无效化位）上方，可在短期回调中加仓。",
        ]
        if t2 is not None:
            lines.append(
                f"行情持续确认后继续加仓，目标 T2 为 {t2_str}。勿追高，回调时加仓。"
            )
        return lines

    if phase in ("at_t1", "between_t1_t2"):
        lines = [
            f"T1（{t1_str}）已达到。在此减仓约 40%，将止损上移至入场位（{_fmt_price(entry)}）。",
        ]
        if t2 is not None:
            lines.append(
                f"剩余仓位持有待 T2（{t2_str}）。将止损移至盈亏平衡点以防反转。"
            )
        lines.append(
            f"T2 目标为 {t2_str}——除非价格收盘回落至 {t1_str} 下方，否则让剩余仓位继续运行。"
            if t2 is not None else
            f"无 T2 目标。考虑全部平仓或紧追止损。"
        )
        return lines[:3]

    if phase == "post_t1_failed_hold":
        return [
            f"T1 后涨幅回吐。减少敞口——减仓或若价格收盘跌破入场位（{_fmt_price(entry)}）则离场。",
            f"无效化位为 {inval_str}，收盘跌破该位即全部离场。",
            f"不要在此加仓。若价格放量重新站上 {t1_str}（T1），再重新评估。",
        ]

    if phase in ("at_t2", "post_t2"):
        lines = [
            f"T2（{t2_str}）已达到。平掉大部分仓位（约 60–80%）。",
            f"剩余仓位追踪止损以保护盈利。考虑将止损硬停在 T1（{t1_str}）。",
        ]
        return lines

    if phase == "overtime":
        return [
            f"交易超出预期持有周期但未达 T1（{t1_str}）。重新评估论点。",
            f"减仓以降低时间风险。收盘跌破 {inval_str}（无效化位）即全部离场。",
            f"超时期间不要加仓。等待 T1 尽快达到，否则该形态推迟执行。",
        ]

    if phase == "invalidated":
        return [
            f"无效化位（{inval_str}）已被突破，全部离场。",
            f"该计划已失效，不要持仓硬撑。",
        ]

    # Fallback
    return [
        f"监测价格相对于触发点（{trigger_str}）和 T1（{t1_str}）的表现。",
        f"收盘跌破无效化位（{inval_str}）即离场。",
    ]


def _build_profit_plan(
    phase: str,
    entry: float | None,
    t1: float | None,
    t2: float | None,
    p1: float | None = None,
    p2: float | None = None,
) -> list[dict]:
    """
    OURS: Build profit-taking plan rows.

    Each row: {level: float|None, label: str, action: str, status: str}
    status ∈ ACTIVE | PENDING | DONE
    Derived from geometry/phase.  Display-only.
    """
    rows: list[dict] = []

    # T1 row
    t1_status: str
    if phase in ("at_t1", "between_t1_t2", "post_t1_failed_hold", "at_t2", "post_t2"):
        t1_status = "DONE"
    elif phase == "invalidated":
        t1_status = "DONE"  # plan terminated
    else:
        t1_status = "ACTIVE"  # awaiting T1

    rows.append({
        "level": t1,
        "label": "T1",
        "action": "Scale out 40%, trail stop to entry",
        "status": t1_status,
    })

    # T2 row (only if T2 is defined)
    if t2 is not None:
        t2_status: str
        if phase in ("at_t2", "post_t2"):
            t2_status = "DONE"
        elif phase in ("at_t1", "between_t1_t2"):
            # T1 done, T2 next
            t2_status = "ACTIVE"
        else:
            t2_status = "PENDING"
        rows.append({
            "level": t2,
            "label": "T2",
            "action": "Close remaining 60%, exit full position",
            "status": t2_status,
        })

    return rows


def _build_profit_plan_zh(
    phase: str,
    entry: float | None,
    t1: float | None,
    t2: float | None,
    p1: float | None = None,
    p2: float | None = None,
) -> list[dict]:
    """ZH counterpart of _build_profit_plan — same row structure, translated action strings.
    label stays "T1"/"T2" (universal); action_zh added per row. No LLM at runtime."""
    rows: list[dict] = []

    t1_status: str
    if phase in ("at_t1", "between_t1_t2", "post_t1_failed_hold", "at_t2", "post_t2"):
        t1_status = "DONE"
    elif phase == "invalidated":
        t1_status = "DONE"
    else:
        t1_status = "ACTIVE"

    rows.append({
        "level": t1,
        "label": "T1",
        "action": "减仓 40%，将止损上移至入场位",
        "status": t1_status,
    })

    if t2 is not None:
        t2_status: str
        if phase in ("at_t2", "post_t2"):
            t2_status = "DONE"
        elif phase in ("at_t1", "between_t1_t2"):
            t2_status = "ACTIVE"
        else:
            t2_status = "PENDING"
        rows.append({
            "level": t2,
            "label": "T2",
            "action": "平仓剩余 60%，全部离场",
            "status": t2_status,
        })

    return rows


# ---------------------------------------------------------------------------
# ID construction
# ---------------------------------------------------------------------------

def _make_id(ticker: str, direction: str, formation_date: str) -> str:
    """Stable plan ID: <TICKER>-<DIRECTION>-<formation_date>."""
    clean_date = formation_date.replace("-", "")
    return f"{ticker}-{direction}-{clean_date}"


# ---------------------------------------------------------------------------
# Option resolution
# ---------------------------------------------------------------------------

def _load_greeks(ticker: str, thetadata_store: str, asof: str) -> pd.DataFrame | None:
    """Load greeks for the asof year; return None if not found."""
    year = asof[:4]
    path = Path(thetadata_store) / "greeks" / ticker / f"{year}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df
    except Exception as e:
        log.warning("prophet_bridge: failed to load greeks for %s: %s", ticker, e)
        return None


def _load_eod(ticker: str, thetadata_store: str, asof: str) -> pd.DataFrame | None:
    """Load EOD for the asof year; return None if not found."""
    year = asof[:4]
    path = Path(thetadata_store) / "eod" / ticker / f"{year}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df
    except Exception as e:
        log.warning("prophet_bridge: failed to load EOD for %s: %s", ticker, e)
        return None


def _lookup_open_interest(
    ticker: str,
    thetadata_store: str,
    asof: str,
    expiry: "date",
    strike: float,
    right: str,
) -> int | None:
    """Open interest for ONE resolved contract, or None (OEU M-PRO receipt).

    Reads {store}/oi/{TICKER}/{YYYY}.parquet — the same store tier the OI timing law
    governs.  OPRA publishes OI once a day for the PREVIOUS session, so the row dated
    `asof` describes positions as of the prior close; the receipt labels that vintage
    rather than pretending the number is live.  Display-only: this never reaches a
    signal, a gate, or a size.  Never raises.
    """
    path = Path(thetadata_store) / "oi" / ticker / f"{asof[:4]}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty or "open_interest" not in df.columns:
            return None
        mask = (
            (df["expiration"] == pd.Timestamp(expiry))
            & (df["right"] == right)
            & (df["strike"].astype(float) == float(strike))
            & (df["date"] <= pd.Timestamp(asof))
        )
        sub = df[mask]
        if sub.empty:
            return None
        sub = sub.sort_values("date")
        oi = sub["open_interest"].dropna()
        return int(oi.iloc[-1]) if len(oi) else None
    except Exception as e:  # noqa: BLE001 — receipt is garnish, never fatal
        log.debug("prophet_bridge: OI lookup failed for %s %s: %s", ticker, strike, e)
        return None


def _structure_receipt(
    ticker: str,
    bid: float | None,
    ask: float | None,
    thetadata_store: str,
    asof: str,
    expiry: "date",
    strike: float,
    right: str,
    implied_vol: float | None = None,
) -> dict | None:
    """Display-tier structure receipt for the resolved contract, or None (M-PRO hook 4).

    Answers "is this contract actually tradeable, and is it expensive for THIS name?"
    with a plain word (liquid / workable / wide / thin) plus the numbers behind it.
    Every input is independently nullable and the whole thing is fail-open: a receipt
    that cannot be built is simply absent, and the plan card renders as it always did.
    """
    try:
        from lib.options_context import load_iv_rank, structure_receipt  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    try:
        oi = _lookup_open_interest(ticker, thetadata_store, asof, expiry, strike, right)
        iv_ctx = (load_iv_rank([ticker]) or {}).get(ticker)
        return structure_receipt(
            bid=bid, ask=ask, open_interest=oi,
            implied_vol=implied_vol, iv_rank_ctx=iv_ctx,
        )
    except Exception as e:  # noqa: BLE001
        log.debug("prophet_bridge: structure receipt failed for %s: %s", ticker, e)
        return None


def resolve_option(
    ticker: str,
    direction: str,
    entry: float,
    horizon_days: int,
    signal_date: str,
    thetadata_store: str | None,
    asof: str,
    clock_date: str | None = None,
) -> dict | None:
    """
    Resolve an option contract for the plan.

    Returns option_contract dict or None + logs an honest note.

    OURS (display-only):
      right    = C (BULL) / P (BEAR)
      expiry   = nearest monthly >= clock_date + horizon_days + 15d
      strike   = nearest strike to 0.60-delta; else first OTM strike from EOD
      premium  = EOD mid (bid+ask)/2 at the chosen contract on asof date

    ``clock_date`` is the plan's ENTRY date (the day whose close is ``entry``) and is
    the same anchor the horizon clock and the outcome scan read — see
    :func:`plan_clock_date`.  It defaults to ``signal_date`` only so a legacy caller
    that predates the split keeps its old behaviour; the live path always passes it.
    Anchoring the min-expiry on a legacy formation-alias ``signal_date`` bought
    contracts that could expire BEFORE the intended hold even began (PINS: anchor
    152 days before origination, so a 45-day hold asked for an expiry already in the
    past). A tier-native event close is likewise not a substitute for entry provenance.
    """
    if not thetadata_store:
        log.info("prophet_bridge: THETADATA_STORE not set; option rec skipped for %s", ticker)
        return None

    right = "C" if direction == "BULL" else "P"
    anchor = clock_date or signal_date
    try:
        sig = date.fromisoformat(str(anchor)[:10])
    except ValueError:
        log.warning("prophet_bridge: bad option clock date %r for %s", anchor, ticker)
        return None

    min_expiry = sig + timedelta(days=horizon_days + 15)
    try:
        target_expiry = _next_monthly_expiry(min_expiry)
    except ValueError as e:
        log.warning("prophet_bridge: expiry search failed for %s: %s", ticker, e)
        return None

    expiry_str = target_expiry.isoformat()

    # --- Try to find the 0.60-delta strike from greeks ---
    greeks = _load_greeks(ticker, thetadata_store, asof)
    if greeks is not None:
        asof_ts = pd.Timestamp(asof)
        exp_ts = pd.Timestamp(target_expiry)

        mask = (
            (greeks["date"] == asof_ts)
            & (greeks["expiration"] == exp_ts)
            & (greeks["right"] == right)
        )
        subset = greeks[mask]

        if not subset.empty:
            # For CALL: want delta closest to +0.60
            # For PUT: want delta closest to -0.60
            target_delta_val = TARGET_DELTA if right == "C" else -TARGET_DELTA
            idx = (subset["delta"] - target_delta_val).abs().idxmin()
            row = subset.loc[idx]
            strike = float(row["strike"])
            bid = float(row.get("bid", 0) or 0)
            ask = float(row.get("ask", 0) or 0)
            premium = round((bid + ask) / 2, 4) if (bid or ask) else None
            _iv = row.get("implied_vol")
            return {
                "right": right,
                "strike": strike,
                "expiry": expiry_str,
                "entry_premium": premium,
                "freshness": "EOD mark",
                "delta_approx": round(float(row["delta"]), 4),
                "note": f"delta-targeted ({TARGET_DELTA:.2f})",
                # OEU M-PRO display-tier receipt (spread / open interest / IV vs the
                # name's own recent range). None when the inputs are unavailable.
                "structure": _structure_receipt(
                    ticker, bid, ask, thetadata_store, asof,
                    target_expiry, strike, right,
                    implied_vol=(None if _iv is None else float(_iv)),
                ),
            }

    # --- Fallback: first OTM strike from EOD ---
    eod = _load_eod(ticker, thetadata_store, asof)
    if eod is not None:
        asof_ts = pd.Timestamp(asof)
        exp_ts = pd.Timestamp(target_expiry)

        if "date" in eod.columns:
            date_col = "date"
        elif "Date" in eod.columns:
            date_col = "Date"
        else:
            date_col = None

        if date_col:
            mask = (
                (eod[date_col] == asof_ts)
                & (eod.get("expiration", eod.get("Expiration", pd.Series(dtype=object))) == exp_ts)
                & (eod.get("right", eod.get("Right", pd.Series(dtype=object))) == right)
            )
            subset = eod[mask]
            if not subset.empty:
                # First OTM: CALL above entry, PUT below entry
                strike_col = "strike" if "strike" in subset.columns else "Strike"
                if right == "C":
                    otm = subset[subset[strike_col] >= entry]
                else:
                    otm = subset[subset[strike_col] <= entry]
                if not otm.empty:
                    row = otm.iloc[0] if right == "C" else otm.iloc[-1]
                    strike = float(row[strike_col])
                    bid = float(row.get("bid", 0) or 0)
                    ask = float(row.get("ask", 0) or 0)
                    premium = round((bid + ask) / 2, 4) if (bid or ask) else None
                    return {
                        "right": right,
                        "strike": strike,
                        "expiry": expiry_str,
                        "entry_premium": premium,
                        "freshness": "EOD mark",
                        "delta_approx": None,
                        "note": "greeks unavailable; first-OTM strike from EOD",
                        # M-PRO receipt — no greeks here, so no contract IV; the
                        # spread + open-interest half still stands on its own.
                        "structure": _structure_receipt(
                            ticker, bid, ask, thetadata_store, asof,
                            target_expiry, strike, right,
                        ),
                    }

    log.info(
        "prophet_bridge: no option data for %s %s %s in store %s; rec=null",
        ticker, right, expiry_str, thetadata_store,
    )
    return None


# ---------------------------------------------------------------------------
# Plan origination
# ---------------------------------------------------------------------------

# ── Plan-lane price sourcing (P3 2026-08-06) ────────────────────────────────
# Per-ticker parquet rungs, in priority order.  These carry full OHLCV.
_PLAN_PRICE_DIRS = ("data/baskets/ohlcv", "data/stocks")

# Third rung: the wide index-constituent close panels the stock library already
# builds its universe from (scripts/build_stock_library.universe()).  Same groups,
# SAME PRIORITY ORDER, so a name resolves to the identical source in both places.
#
# WHY IT EXISTS: 27 of 103 live plans (23 distinct tickers) were priced by NOTHING —
# no ohlcv parquet, no stocks parquet — so they could not be managed, could not be
# closed, and permanently blocked their ticker+direction slot.  19 of the 23 are
# columns in these panels.  The remaining 4 (BIDU, GRAB, SE, WB) are foreign issuers
# in no US index cache; they stay unpriced, and that is a real null, not a lookup bug.
#
# The panels carry CLOSE ONLY.  That is sufficient — the management engine and the
# outcome scan both read `close` and nothing else — and the frame is emitted with a
# single `close` column so a consumer cannot silently read a missing `high` as data.
# Ordering matters more than agreement here: the per-ticker parquets ALWAYS win, so a
# name present in both is never served from a panel and the two can never disagree
# on a shipped plan.
_PLAN_PRICE_PANELS = (
    "breadth", "midcap_breadth", "smallcap_breadth", "russell_breadth",
)


def _panel_close_history(ticker: str, repo: Path) -> pd.DataFrame | None:
    """One-column ``close`` frame for ``ticker`` from the first panel carrying it."""
    for group in _PLAN_PRICE_PANELS:
        cache = repo / "data" / group / "_closes_cache.parquet"
        if not cache.exists():
            continue
        try:
            panel = pd.read_parquet(cache, columns=[ticker])
        except Exception:  # noqa: BLE001 — absent column is the common case, not an error
            continue
        try:
            series = panel[ticker].dropna()
            if series.empty:
                continue
            df = pd.DataFrame({"close": series.astype(float)})
            df.index = pd.to_datetime(df.index)
            return df.sort_index()
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_bridge: panel %s unusable for %s: %s", group, ticker, e)
    return None


def _load_price_history(ticker: str) -> pd.DataFrame | None:
    """Load price history: baskets/ohlcv → stocks → index-constituent close panels."""
    repo = Path(__file__).resolve().parent.parent
    for sub in _PLAN_PRICE_DIRS:
        p = repo / sub / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if not isinstance(df.index, pd.DatetimeIndex):
                    if "date" in df.columns:
                        df = df.set_index("date")
                    elif "Date" in df.columns:
                        df = df.set_index("Date")
                df.index = pd.to_datetime(df.index)
                return df
            except Exception as e:
                log.warning("prophet_bridge: price history load failed %s: %s", ticker, e)
    return _panel_close_history(ticker, repo)


# ---------------------------------------------------------------------------
# PSQ-TILT W1 — hold-leash (runs strictly AFTER select_candidates)
# ---------------------------------------------------------------------------
# Authority boundary (binding): the leash NEVER touches selection (ids/order),
# NEVER vetoes an entry, NEVER suppresses rank, NEVER gates on a win-rate. It
# only extends the intended HOLD horizon for a Stage-2 ∩ EC-positive pick. Any
# tilt-input failure degrades to leash 1.0 with a ::warning:: — origination
# NEVER raises because of the tilt. See research/PROPHET_STAGE_TILT_W1_DESIGN.md.

def _bear_from_regime(data_root: "Path | None" = None) -> bool:
    """§2 bear-gate — deterministic, artifact-based.

    Reads data/regime/latest.json (committed nightly by engine/run.py):
        bear = risk_radar.context_gate.spy_below_200dma is not False
               OR risk_radar.state == "risk-off"
    Missing file / missing keys / unparseable → bear = True (fail-safe: tilt off).
    Strict tape leg (review #3203 hardening): only a definite False (SPY confirmed
    above its 200dma) clears it — a present-but-None sentinel (upstream SPY data
    gap) counts as bear.
    Does NOT activate the macro_stance management socket (whole-book confidence
    shift — out of scope). The bear boolean lives in the driver/bridge only.
    """
    try:
        from lib import config  # noqa: PLC0415
        root = Path(data_root) if data_root is not None else config.data_dir()
        p = root / "regime" / "latest.json"
        with p.open(encoding="utf-8") as f:
            regime = json.load(f)
        rr = regime["risk_radar"]
        spy_below = rr["context_gate"]["spy_below_200dma"]
        risk_off = rr.get("state") == "risk-off"
        return bool(spy_below is not False or risk_off)
    except Exception as e:  # noqa: BLE001
        # Bare print, NOT a logger call: GitHub only parses a workflow command when
        # "::" STARTS the line, and this module's logging format prefixes every
        # record (e.g. "WARNING ::warning ..."), which silently drops the annotation.
        print(f"::warning:: prophet_bridge: regime bear-gate unreadable ({e}) — tilt fails "
              "safe to bear=True (leash 1.0)",
              flush=True)
        return True


def _stage_tilt_demoted(data_root: "Path | None" = None) -> bool:
    """§4 auto-demote — read the shadow's committed summary (measurement, not memory).

    DEMOTED when median_tilt.n_matured_126.stage2_ec >= STAGE_TILT_DEMOTE_MIN_MATURED (30)
    AND median_tilt.diff <= 0. Until the floor is met the tilt stays provisional-active.
    Missing summary / missing block / unparseable → NOT demoted (the floor simply
    is not yet met; the tilt stays provisional until the shadow accrues). The shadow
    itself never gates picks — the TILT reads the measurement and self-demotes.
    """
    try:
        from lib import config  # noqa: PLC0415
        root = Path(data_root) if data_root is not None else config.data_dir()
        p = root / "prophet_stage_shadow" / "summary.json"
        if not p.exists():
            return False
        with p.open(encoding="utf-8") as f:
            summary = json.load(f)
        mt = summary.get("median_tilt") or {}
        n_matured = (mt.get("n_matured_126") or {}).get("stage2_ec")
        diff = mt.get("diff")
        if n_matured is None or diff is None:
            return False
        return int(n_matured) >= STAGE_TILT_DEMOTE_MIN_MATURED and float(diff) <= 0
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: prophet_bridge: shadow summary unreadable for demote check ({e}) "
              "— leaving tilt provisional-active",
              flush=True)
        return False


def _load_stage_tilt_inputs(data_root: "Path | None" = None) -> dict:
    """Load the once-per-run tilt inputs (EC table + bench + bear + demote).

    Loaded once per nightly run (NOT per pick). Any load failure degrades that
    input so the per-pick compute falls back to leash 1.0. Never raises.

    R0-C: the point-in-time primitives come from ``engine.prophet_stage_inputs`` — a
    governed production module — NOT from ``engine.prophet_stage_fusion``, which is a
    research backtest harness and must never be a live dependency of origination.

    R0-C disclosure: the EC table's backing parquet is a local-only EquityDesk backfill
    that is absent on every CI/deploy host, so ``load_ec_table`` fails open to an EMPTY
    frame and every EC lookup answers null. That made "no positive earnings call" and
    "no earnings-call data at all" the same output. ``ec_source`` records which one it
    is, and an unavailable source now emits a ``::warning::`` instead of degrading in
    silence. The leash value is unchanged by this disclosure.
    """
    from lib import config  # noqa: PLC0415
    import engine.prophet_stage_inputs as psi  # noqa: PLC0415
    root = Path(data_root) if data_root is not None else config.data_dir()

    ec_by_ticker: dict = {}
    ec_load_ok = True
    ec_source: dict = {"state": psi.EC_SOURCE_UNAVAILABLE, "path": None,
                       "reason": "earnings-call source not resolved"}
    try:
        ec_table, ec_source = psi.load_ec_table_with_source()
        ec_by_ticker = psi.ec_index(ec_table)
    except Exception as e:  # noqa: BLE001
        ec_load_ok = False
        ec_source = {"state": psi.EC_SOURCE_UNAVAILABLE, "path": ec_source.get("path"),
                     "reason": f"earnings-call source load failed: {e}"}
        print(f"::warning:: prophet_bridge: EC table load failed ({e}) — tilt eligibility off "
              "(leash 1.0)",
              flush=True)

    if ec_source.get("state") != psi.EC_SOURCE_AVAILABLE:
        # The silent-degrade alarm. Without this the Stage tilt reads as a healthy
        # negative on every host where its data source does not exist.
        print("::warning:: prophet_bridge: earnings-call source unavailable "
              f"({ec_source.get('path')}) — {ec_source.get('reason')}; the Stage hold-tilt "
              "cannot become eligible on this host (every pick stays at leash 1.0)",
              flush=True)

    try:
        bench = psi.load_bench_close(root)
    except Exception as e:  # noqa: BLE001
        bench = None
        print(f"::warning:: prophet_bridge: bench close load failed ({e})", flush=True)

    return {
        "root": root,
        # Duck-typed point-in-time interface (EC_SENT_GATE / load_ticker_prices /
        # stage_at_entry / ec_sent_at_entry). Tests substitute a stub here.
        "stage_inputs": psi,
        "ec_by_ticker": ec_by_ticker,
        "ec_load_ok": ec_load_ok,
        "ec_source": ec_source,
        "bench": bench,
        "bear": _bear_from_regime(root),
        "demoted": _stage_tilt_demoted(root),
    }


def _compute_stage_tilt(ticker: str, entry_date: str, tilt_inputs: dict) -> tuple[int, dict]:
    """§1 per-pick leash. Returns (horizon_days, stage_tilt_block).

    Uses the SAME PIT functions the shadow uses (``prophet_stage_inputs.stage_at_entry``
    / ``ec_sent_at_entry``) — one code path. Any classify/lookup failure degrades
    this pick to leash 1.0 with a ::warning::; NEVER raises.

    ``ec_source_state`` (R0-C) is DISCLOSURE, not behavior: it separates "this name has
    no positive earnings call" (``available``) from "there is no earnings-call data on
    this host" (``unavailable``). It never enters the eligibility test and never moves
    the leash.
    """
    pit = tilt_inputs["stage_inputs"]
    root = tilt_inputs["root"]
    ec_by_ticker = tilt_inputs["ec_by_ticker"]
    bench = tilt_inputs["bench"]
    bear = bool(tilt_inputs["bear"])
    demoted = bool(tilt_inputs["demoted"])
    ec_source = tilt_inputs.get("ec_source") or {}

    stage_at_entry_val: int | None = None
    ec_sent: float | None = None
    ec_call_date: str | None = None

    try:
        close, vol = pit.load_ticker_prices(ticker, root)
        if close is not None and not close.empty:
            st, _wis, _nwk = pit.stage_at_entry(close, vol, bench, entry_date)
            stage_at_entry_val = int(st)
        # EC most-recent call_date < entry_date (strictly-before, PIT).
        if tilt_inputs.get("ec_load_ok", True):
            ec_sent = pit.ec_sent_at_entry(ec_by_ticker, ticker, entry_date)
            if ec_sent is not None:
                g = ec_by_ticker.get(str(ticker))
                if g is not None and not g.empty:
                    import pandas as _pd  # noqa: PLC0415
                    prior = g[g["call_date"] < _pd.Timestamp(entry_date)]
                    if not prior.empty:
                        ec_call_date = str(prior["call_date"].iloc[-1].date())
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: prophet_bridge: stage-tilt compute failed for {ticker} ({e}) — "
              "leash 1.0 for this pick",
              flush=True)
        stage_at_entry_val = None
        ec_sent = None
        ec_call_date = None

    eligible = (
        stage_at_entry_val == 2
        and ec_sent is not None
        and ec_sent >= pit.EC_SENT_GATE
    )
    # bear gate and auto-demote both force the leash back to 1.0.
    leash = STAGE_TILT_LEASH if (eligible and not bear and not demoted) else 1.0
    # Scaled horizon flows to τ/overtime (management), the EXPIRED ledger close,
    # and option-expiry min-date (longer intended hold → longer-dated contract).
    horizon_days = round(HORIZON_DAYS_DEFAULT * leash)

    stage_tilt = {
        "leash": leash,
        "eligible": bool(eligible),          # stage2 ∩ EC, before bear-gate / demote
        "stage_at_entry": stage_at_entry_val,
        "ec_sent": ec_sent,
        "ec_call_date": ec_call_date,
        # Disclosure only (R0-C) — never read by the eligibility test above.
        "ec_source_state": str(ec_source.get("state") or STAGE_TILT_EC_SOURCE_UNAVAILABLE),
        "ec_source_path": ec_source.get("path"),
        "ec_source_reason": ec_source.get("reason"),
        "bear_gate": bool(bear),             # True = gate forced 1.0
        "provisional": True,
        "demoted": bool(demoted),
        "basis": (
            "PSQ 2026-07-20 quality re-grade; provisional — forward-shadow "
            "checked (~2026-12)"
        ),
    }
    return horizon_days, stage_tilt


def originate_plans(
    standouts_path: str | Path,
    asof: str,
    existing_ids: set[str],
    thetadata_store: str | None = None,
    active_keys: set[str] | None = None,
    intake_stats: dict | None = None,
) -> list[dict]:
    """
    Read us_standouts.json, apply the pick rule, and return new
    prophet.trade_plan/v1 dicts for IDs not in existing_ids.

    Parameters
    ----------
    standouts_path : path to site/factordata/us_standouts.json
    asof           : ISO-8601 run/publication date.  It is not assumed to be the
                     session whose close supplied the entry price.
    existing_ids   : set of plan IDs already persisted (duplicate suppression)
    thetadata_store: path to ThetaData EOD store root
    active_keys    : W1 re-origination block — ``<TICKER>-<DIRECTION>`` keys
                     (``plan_key()``) that already have an OPEN plan.  A candidate
                     matching one is skipped no matter how fresh its signal_date is;
                     a plan that has CLOSED is absent from this set, so the name
                     becomes originatable again.  ``None`` disables the block.
    intake_stats   : optional out-dict.  When supplied it is populated with
                     ``reorigination_blocked`` (int),
                     ``reorigination_blocked_keys`` (sorted list),
                     the complete admitted/blocked/originated disposition, lossless
                     status, and per-candidate validation failures so the caller can
                     disclose every disposition in its artifact. Never read, only
                     written.

    Returns
    -------
    list of prophet.trade_plan/v1 dicts (validated before return)

    LOSSLESS ORIGINATION (2026-08-08)
    ---------------------------------
    Every admitted candidate that survives duplicate-ID and open-plan suppression is
    attempted.  A candidate can then disappear only through a disclosed validation
    failure.  No featured, sector, notification, funding or portfolio-risk authority is
    widened here; those are separate lanes over this lossless plan population.
    """
    from engine.options_structure import validate_trade_plan  # noqa: PLC0415

    standouts_path = Path(standouts_path)
    with standouts_path.open(encoding="utf-8") as f:
        standouts = json.load(f)

    # Kept only as a legacy formation-anchor fallback.  It is never price authority;
    # `_resolve_origination_clocks` consumes the ranked-price watermark below.
    standouts_asof = standouts.get("as_of", asof)
    staleness = (
        standouts.get("staleness")
        if isinstance(standouts.get("staleness"), Mapping) else {}
    )
    staleness_inputs = (
        staleness.get("inputs")
        if isinstance(staleness.get("inputs"), Mapping) else {}
    )
    panel_staleness = (
        staleness_inputs.get("panel")
        if isinstance(staleness_inputs.get("panel"), Mapping) else {}
    )
    recorded_at, price_basis_date, clock_errors = _resolve_origination_clocks(
        price_through=staleness.get("price_through"),
        recorded_asof=asof,
        panel_mixed_vintage=bool(panel_staleness.get("mixed_vintage")),
        source_delayed=staleness.get("delayed"),
        source_unknown=staleness.get("unknown"),
        source_basis=staleness.get("basis"),
    )

    # ── Pass 1: full admitted ordering → apply the two policy skips ──
    admission_stats: dict[str, Any] = {}
    admitted = select_candidates(standouts, n=None, stats=admission_stats)
    if admission_stats.get("unknown_status"):
        # Bare print at line start (house law): a logger prefix makes GitHub drop it.
        print(
            "::warning title=prophet-unknown-entry-status::"
            f"{admission_stats['unknown_status']} buy row(s) carry an entry status "
            f"outside the admission vocabulary "
            f"({', '.join(admission_stats.get('unknown_status_values') or [])}) — "
            "refused, not defaulted",
            flush=True,
        )
    candidates: list[tuple[dict, str, str, str]] = []
    blocked_keys: list[str] = []
    duplicate_id_blocked = 0
    policy_survivors = 0
    validation_failures: list[dict[str, Any]] = []
    _seen_ids: set[str] = set()

    def _record_failure(
        *, ticker: str | None, plan_id: str | None, stage: str, errors: list[str]
    ) -> None:
        validation_failures.append({
            "ticker": ticker,
            "id": plan_id,
            "stage": stage,
            "errors": [str(error) for error in errors],
        })

    for b in admitted:
        ticker = str(b.get("ticker") or "").strip().upper()
        if not ticker:
            policy_survivors += 1
            _record_failure(
                ticker=None,
                plan_id=None,
                stage="candidate_identity",
                errors=["ticker is required"],
            )
            continue
        hold = b.get("hold") or {}
        anchor = hold.get("anchor")
        formation_date = _normalise_iso_date(anchor if anchor else standouts_asof)
        if formation_date is None:
            policy_survivors += 1
            _record_failure(
                ticker=ticker,
                plan_id=None,
                stage="candidate_identity",
                errors=[
                    f"formation_date {(anchor if anchor else standouts_asof)!r} "
                    "is not an ISO-8601 date"
                ],
            )
            continue
        plan_id = _make_id(ticker, "BULL", formation_date)

        if plan_id in existing_ids or plan_id in _seen_ids:
            duplicate_id_blocked += 1
            log.info("prophet_bridge: suppressing duplicate %s", plan_id)
            continue

        # W1 re-origination block — checked AFTER the id check so the count below is the
        # NEW failure mode (a fresh signal_date on a name that is already live) and not
        # the same-id duplicate suppression that has always been in force.
        key = plan_key(ticker, "BULL")
        if active_keys and key in active_keys:
            blocked_keys.append(key)
            log.info(
                "prophet_bridge: re-origination blocked for %s (would have been %s) — "
                "an open plan on the same ticker+direction is still active",
                key, plan_id,
            )
            continue

        policy_survivors += 1
        _seen_ids.add(plan_id)
        candidates.append((b, ticker, formation_date, plan_id))

    eligible_after_skips = policy_survivors
    # Exact earnings evidence is loaded only for the already-selected names.
    # It cannot broaden the candidate set or influence ordering.
    try:
        _earnings_evidence_map = _load_earnings_evidence_context(
            standouts_path, [ticker for _row, ticker, _formation, _id in candidates],
            asof=asof,
        )
    except Exception as e:  # noqa: BLE001 - display context is fail-open.
        log.info("prophet_bridge: exact earnings evidence unavailable (%s); plans remain unchanged", e)
        _earnings_evidence_map = {}
    log.info(
        "prophet_bridge: %d candidates selected (gate_go=%s)",
        len(candidates), standouts.get("gate_go"),
    )

    # ── PSQ-TILT W1: hold-leash inputs (once per run; NOT per pick) ────────────
    # STRICTLY AFTER select_candidates — the tilt cannot read into selection, so
    # the selected id set/order are byte-identical whether the tilt is on or off.
    # Never raises: a failed input degrades the affected pick to leash 1.0.
    try:
        _tilt_inputs = _load_stage_tilt_inputs()
    except Exception as e:  # noqa: BLE001
        print(f"::warning:: prophet_bridge: stage-tilt inputs unavailable ({e}) — all picks "
              "default to leash 1.0",
              flush=True)
        _tilt_inputs = None

    # ── OEU M-PRO: dealer-positioning context for the thesis prose (display-tier) ──
    # Loaded ONCE per run and STRICTLY AFTER select_candidates, exactly like the
    # stage-tilt inputs above: the selected id set and their order are byte-identical
    # whether this map is populated or empty. It reaches thesis STRINGS only — never
    # geometry, never the option choice, never a score. One file read; {} on absence.
    try:
        from lib.options_context import load_gex_walls  # noqa: PLC0415
        _wall_map = load_gex_walls()
    except Exception as e:  # noqa: BLE001
        log.info("prophet_bridge: dealer-positioning context unavailable (%s); "
                 "theses render without it", e)
        _wall_map = {}

    # Government Revenue Foresight context is loaded once and strictly after
    # ``select_candidates``.  It can annotate an already-selected plan, but it
    # cannot alter selection, order, confidence, geometry, horizon, or options.
    try:
        _government_revenue_map = _load_government_revenue_context(standouts_path, asof)
    except Exception as e:  # noqa: BLE001
        log.info("prophet_bridge: government-revenue context unavailable (%s); "
                 "plans render without it", e)
        _government_revenue_map = {}

    # ── §6.9 R3: EARLY-TURN + washout context, loaded ONCE and strictly AFTER
    # select_candidates.  Like every other context map above, it can re-CLASS an
    # already-selected plan and shape its zone; it can never broaden the candidate set
    # or move the order.  Empty map on any absence — a starter class is a licence, and
    # a licence that cannot be resolved is not granted.
    try:
        from engine.us_early_turn import load_basket_turn_membership  # noqa: PLC0415
        _turn_membership = load_basket_turn_membership()
    except Exception as e:  # noqa: BLE001
        log.info("prophet_bridge: basket-turn context unavailable (%s); "
                 "EARLY-TURN admits nothing this run", e)
        _turn_membership = {}

    # The LEADER half of the same intake, resolved ONCE for the same reasons — and for
    # one more.  `assess_early_turn` falls back to loading the artifact ITSELF when no
    # map is passed, so leaving this out re-read (and re-parsed) a ~700-name JSON file
    # once per candidate.  Loading it here also pins the whole run to ONE snapshot of the
    # organ's coverage, which is what makes the per-plan `state_asof` disclosure mean
    # something.  The publisher is `scripts/build_leader_pullback_coverage.py`, scheduled
    # BEFORE build_prophet in config/dag.yml; an empty map is the fail-closed direction
    # and `leader_pullback_context` names that absence on every row it declines.
    try:
        from engine.us_early_turn import load_leader_pullback_states  # noqa: PLC0415
        _leader_states = load_leader_pullback_states()
    except Exception as e:  # noqa: BLE001
        log.info("prophet_bridge: leader-pullback coverage unavailable (%s); "
                 "EARLY-TURN admits on washout context only this run", e)
        _leader_states = {}
    log.info("prophet_bridge: EARLY-TURN context maps — washout %d tickers, "
             "leader-pullback %d tickers", len(_turn_membership), len(_leader_states))

    plans: list[dict] = []
    stale_basis_skipped: list[str] = []
    early_turn_plans: list[str] = []
    wait_reset_plans: list[str] = []
    for b, ticker, formation_date, plan_id in candidates:
        direction = "BULL"  # all dir="up" entries
        government_revenue_ctx = _government_revenue_map.get(ticker.upper())

        # The BASE-FORMATION anchor remains the plan id's date component.  The causal
        # signal/observation clocks come from the selected tier, never from this ID label.
        hold = b.get("hold") or {}
        signal_dates, signal_clock_errors = _resolve_candidate_signal_dates(
            b,
            formation_date=formation_date,
            price_basis_date=price_basis_date,
        )
        signal_date = signal_dates["signal_date"]

        # The duplicate-id and open-plan skips ran in pass 1.  Clock provenance is a
        # validation gate, never an invitation to guess the prior Friday.
        if clock_errors or signal_clock_errors:
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="clock_provenance",
                errors=[*clock_errors, *signal_clock_errors],
            )
            continue

        es = b.get("entry_signal") or {}
        conv = b.get("conviction") or {}

        # Entry: spot from entry_signal (latest close proxy)
        spot = es.get("spot")
        if spot is None:
            log.warning("prophet_bridge: no spot for %s; skipping", ticker)
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="entry_price",
                errors=["entry_signal.spot is required"],
            )
            continue
        try:
            entry = float(spot)
        except (TypeError, ValueError):
            entry = float("nan")
        if not math.isfinite(entry) or entry <= 0.0:
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="entry_price",
                errors=[f"entry_signal.spot {spot!r} is not a positive finite price"],
            )
            continue

        # Trigger: chase_above breakout level if present, else entry
        chase_above = es.get("chase_above")
        try:
            trigger = float(chase_above) if chase_above is not None else entry
        except (TypeError, ValueError):
            trigger = float("nan")
        if not math.isfinite(trigger) or trigger <= 0.0:
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="entry_price",
                errors=[f"entry_signal.chase_above {chase_above!r} is not a positive finite price"],
            )
            continue

        # Confidence from conviction score (0-100 → capped at 92 in engine)
        try:
            confidence = min(float(conv.get("score", 60)), 92.0)
        except (TypeError, ValueError):
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="plan_inputs",
                errors=[f"conviction.score {conv.get('score')!r} is not numeric"],
            )
            continue

        # Price history for swing-level geometry fallback
        ph = _load_price_history(ticker)

        # ATR from entry_signal.atr_pct
        atr_pct = es.get("atr_pct")

        # ── Publication-lag guard (ANTICIPATION §6.2 A1) ────────────────────────
        # The lag is measured, DISCLOSED on the plan, and — beyond the tolerance —
        # fatal.  See STALE_BASIS_MAX_SESSIONS: on this base the clock contract makes
        # a stale basis impossible, so this branch is a second fence that must never
        # fire in production.  It is here so the property survives a loosened clock.
        entry_basis = resolve_entry_basis(
            b, price_basis_date=price_basis_date, asof=asof, price_history=ph)
        if entry_basis["state"] == "stale":
            print(
                "::warning title=prophet-stale-entry-basis::"
                f"skipping {ticker} — entry basis {entry_basis['basis_date']} is "
                f"{entry_basis['lag']} {entry_basis['lag_basis']} behind the run asof "
                f"{asof} (tolerance {STALE_BASIS_MAX_SESSIONS}); a plan is never "
                "published at a stale price",
                flush=True,
            )
            stale_basis_skipped.append(f"{ticker}:{entry_basis['lag']}")
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="stale_entry_basis",
                errors=[
                    f"entry basis {entry_basis['basis_date']} trails the run asof "
                    f"{asof} by {entry_basis['lag']} {entry_basis['lag_basis']}"
                ],
            )
            continue

        # ── §6.9 R3: extension read, EARLY-TURN class, structure-anchored zone ──
        candidate_class = admission_class(entry_status(b))
        try:
            from engine import us_early_turn  # noqa: PLC0415
            extension = us_early_turn.extension_state(ph, price_basis_date)
            early = us_early_turn.assess_early_turn(
                ticker, ph, asof=price_basis_date,
                membership=_turn_membership, leader_states=_leader_states,
                board_row=b)
        except Exception as e:  # noqa: BLE001 — display context never breaks a plan
            log.info("prophet_bridge: early-turn read unavailable for %s (%s)", ticker, e)
            extension = None
            early = {"fired": False, "reason": f"early-turn read failed: {e}"}
        # ORGAN state only.  The board's own lane is applied inside
        # zone_conversion_class; the board's `coiled.washout_ctx` flag is deliberately
        # NOT an input (measured near-constant — see zone_conversion_class).
        washout_ctx = bool((early.get("washout") or {}).get("washout_context"))
        if early.get("fired"):
            candidate_class = ADMISSION_CLASS_EARLY_TURN
            early_turn_plans.append(ticker)

        entry_zone = build_entry_zone(
            b,
            entry=entry,
            klass=admission_class(entry_status(b)),
            price_basis_date=price_basis_date,
            price_history=ph,
            extension=extension,
            washout_context=washout_ctx,
            early_turn=bool(early.get("fired")),
            leader_pullback=early.get("leader_pullback"),
        )
        if entry_zone["zone_class"] == ZONE_CLASS_WAIT_RESET:
            wait_reset_plans.append(ticker)
            # A wait_reset plan may NEVER ask the reader to pay above the last print.
            # `trigger` keeps its management-engine meaning (BULL fires at price >=
            # trigger), so it is clamped to the entry rather than moved below it: a
            # trigger under spot would read as "already triggered" on night one.
            trigger = min(trigger, entry)

        # ── PSQ-TILT W1: hold-leash for this pick (Stage-2 ∩ EC-positive) ──────
        # Runs here — after selection, before geometry/option resolution. The
        # scaled horizon flows into resolve_option (later expiry) and the plan
        # dict (τ/overtime + EXPIRED ledger close read plan.horizon_days).
        if _tilt_inputs is not None:
            plan_horizon_days, stage_tilt = _compute_stage_tilt(
                ticker=ticker,
                entry_date=price_basis_date,
                tilt_inputs=_tilt_inputs,
            )
        else:
            plan_horizon_days = HORIZON_DAYS_DEFAULT
            stage_tilt = {
                "leash": 1.0, "eligible": False, "stage_at_entry": None,
                "ec_sent": None, "ec_call_date": None,
                "ec_source_state": STAGE_TILT_EC_SOURCE_UNAVAILABLE,
                "ec_source_path": None,
                "ec_source_reason": "stage-tilt inputs unavailable — no source resolved",
                "bear_gate": True,
                "provisional": True, "demoted": False,
                "basis": (
                    "PSQ 2026-07-20 quality re-grade; provisional — forward-shadow "
                    "checked (~2026-12)"
                ),
            }

        # Geometry
        try:
            geo = compute_geometry(
                entry=entry,
                direction=direction,
                atr_pct=float(atr_pct) if atr_pct else None,
                hold_invalidation=hold.get("invalidation"),
                price_history=ph,
                asof=price_basis_date,
            )
        except (TypeError, ValueError) as exc:
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="geometry",
                errors=[str(exc)],
            )
            continue

        # Option contract.  The min-expiry clock is the entry-price session, the same
        # anchor the horizon and the outcome scan read — never the formation anchor.
        opt = resolve_option(
            ticker=ticker,
            direction=direction,
            entry=entry,
            horizon_days=plan_horizon_days,  # PSQ-TILT: scaled hold → later-dated contract
            signal_date=signal_date,
            thetadata_store=thetadata_store,
            asof=price_basis_date,
            clock_date=price_basis_date,
        )

        # ── Content blocks (deterministic, NO LLM) ─────────────────────────
        # Origination phase is always pre_trigger; content blocks are keyed
        # to phase so they can be regenerated by the management engine later.
        init_phase = "pre_trigger"
        t1_price = geo["t1"]
        t2_price = geo["t2"]

        what_to_do_now = _build_what_to_do_now(
            phase=init_phase,
            entry=entry,
            trigger=trigger,
            invalidation=geo["invalidation"],
            t1=t1_price,
            t2=t2_price,
            tranche=1,
            entry_zone=entry_zone,
        )
        what_to_do_now_zh = _build_what_to_do_now_zh(
            phase=init_phase,
            entry=entry,
            trigger=trigger,
            invalidation=geo["invalidation"],
            t1=t1_price,
            t2=t2_price,
            tranche=1,
            entry_zone=entry_zone,
        )
        profit_plan = _build_profit_plan(
            phase=init_phase,
            entry=entry,
            t1=t1_price,
            t2=t2_price,
            p1=0.0,
            p2=0.0 if t2_price is not None else None,
        )
        profit_plan_zh = _build_profit_plan_zh(
            phase=init_phase,
            entry=entry,
            t1=t1_price,
            t2=t2_price,
            p1=0.0,
            p2=0.0 if t2_price is not None else None,
        )

        # Build the plan dict
        plan: dict[str, Any] = {
            "schema": "prophet.trade_plan/v1",
            "id": plan_id,
            "asof": asof,
            # Run/publication clock.  A recovery run may occur on a weekend; unlike
            # price_basis_date this date is not required to be an NYSE session.
            "recorded_at": recorded_at,
            "asset": ticker,
            "direction": direction,
            "thesis": _build_thesis(
                ticker, b, _wall_map.get(ticker), government_revenue_ctx
            ),
            "thesis_zh": _build_thesis_zh(
                ticker, b, _wall_map.get(ticker), government_revenue_ctx
            ),
            "source_engines": ["us_standouts_buy_lane", "neural_web"],
            "trigger": round(trigger, 4),
            "entry": round(entry, 4),
            "invalidation": geo["invalidation"],
            "targets": [
                t for t in [t1_price, t2_price] if t is not None
            ],
            "horizon_days": plan_horizon_days,  # PSQ-TILT: 45 base × leash (45 or 56)
            "min_hold_days": MIN_HOLD_DAYS_DEFAULT,  # unchanged (10)
            "tranche": 1,
            "option_contract": opt,
            # PSQ-TILT W1 provenance (provisional; display data field, not copy).
            "stage_tilt": stage_tilt,
            "management_ref": f"prophet/state/{plan_id}.json",
            "authority_tier": "display",
            "reliability": {
                "plan": (
                    "display — us_standouts buy-lane originated; display-only until"
                    " forward ledger gate passes"
                ),
                "option_premium": (
                    "EOD mark — delayed; not NBBO-live; display-only"
                )
                if opt
                else "null — symbol not in ThetaData store",
            },
            # formation_date is the immutable ID anchor.  The remaining fields are the
            # tier-native causal date family resolved above.
            "formation_date": formation_date,
            "signal_date": signal_date,
            "confirmed_date": signal_dates["confirmed_date"],
            "observed_date": signal_dates["observed_date"],
            "signal_tier": signal_dates["signal_tier"],
            "signal_date_basis": signal_dates["signal_date_basis"],
            "signal_provisional": signal_dates["signal_provisional"],
            "source_marker_date": signal_dates["source_marker_date"],
            # price_basis_date/entry_date: the NYSE session whose close IS `entry`.
            # The horizon clock, outcome scan, management τ and option min-expiry all
            # read this via plan_clock_date().  It must never inherit a weekend run date.
            "price_basis_date": price_basis_date,
            "entry_date": price_basis_date,
            # ── Content blocks (optional; graceful fallback on absence) ───────
            # These are regenerated by the management engine on each nightly run
            # with the current phase.  display-only artifact.
            "what_to_do_now": what_to_do_now,       # list[str] — numbered bullets (EN)
            "what_to_do_now_zh": what_to_do_now_zh, # list[str] — numbered bullets (ZH)
            "profit_plan": profit_plan,              # list[{level, label, action, status}] (EN)
            "profit_plan_zh": profit_plan_zh,        # list[{level, label, action, status}] (ZH)
            # Extra metadata (display)
            "_signal_date": signal_date,
            # The us_prophet_v1 priority score this pick was ORDERED by, frozen onto
            # the plan at origination.  The index sorts `plans[]` by it (P6) so the
            # shipped order is the order the artifact says it is; None on a legacy
            # board row with no numeric prophet.score, which sorts below every scored
            # plan by the old conviction key — the same self-heal select_candidates uses.
            "_priority_score": _priority_score(b),
            "_conviction_score": conv.get("score"),
            "_act_level": es.get("act_level"),
            "_r_unit": geo["r_unit"],
            "_gate_go": standouts.get("gate_go"),
            # ── ANTICIPATION §6.2 A1 provenance (ADDITIVE — nothing was renamed) ──
            # Which class of entry status admitted this plan, and under which selection
            # rule.  Both ship on every plan so a later side-by-side never has to infer
            # the era from a date, and so a patience plan is distinguishable from a
            # confirmation plan at the row level rather than only in aggregate.
            "admission_class": candidate_class,
            "entry_status": entry_status(b) or None,
            "selection_era": SELECTION_ERA,
            # Publication-lag disclosure: which day's close `entry` is, how far behind
            # the run that is, and how old the SIGNAL is relative to that price.
            "entry_basis": entry_basis,
            # ── §6.9 R3: the structure-anchored band this plan waits at ───────────
            # `entry` above remains the point-in-time close — a plan never fabricates a
            # fill.  The ZONE is what the plan acts on, and its stance is what the copy
            # says out loud.
            "entry_zone": entry_zone,
            "early_turn": {
                "fired": bool(early.get("fired")),
                "reason": early.get("reason"),
                "timeframes": early.get("signature_timeframes") or [],
                "washout_state": (early.get("washout") or {}).get("state"),
                "leader_pullback_source": (
                    early.get("leader_pullback") or {}).get("source"),
            },
        }

        if government_revenue_ctx:
            plan["government_revenue_context"] = government_revenue_ctx
            plan["context_engines"] = ["government_revenue_foresight"]

        earnings_annotation = _earnings_plan_annotation(_earnings_evidence_map.get(ticker))
        if earnings_annotation:
            plan["earnings_evidence_context"] = earnings_annotation
            plan.setdefault("context_engines", []).append("earnings_evidence_spine")

        # Validate
        from engine.options_structure import validate_trade_plan as _vtp  # noqa: PLC0415
        errs = _vtp(plan)
        if errs:
            log.warning(
                "prophet_bridge: plan %s failed validation: %s", plan_id, errs
            )
            _record_failure(
                ticker=ticker,
                plan_id=plan_id,
                stage="trade_plan_schema",
                errors=errs,
            )
            continue

        plans.append(plan)
        existing_ids.add(plan_id)
        log.info(
            "prophet_bridge: originated plan %s entry=%.2f inval=%s T1=%s T2=%s opt=%s",
            plan_id,
            entry,
            geo["invalidation"],
            geo["t1"],
            geo["t2"],
            "Y" if opt else "N",
        )

    # ── Lossless disposition: every admitted row must be accounted for ──
    validation_failed = len(validation_failures)
    unaccounted = (
        len(admitted)
        - duplicate_id_blocked
        - len(blocked_keys)
        - validation_failed
        - len(plans)
    )
    lossless = unaccounted == 0
    log.info(
        "prophet_bridge: re-origination block skipped %d candidate(s)%s",
        len(blocked_keys),
        f" ({', '.join(sorted(set(blocked_keys)))})" if blocked_keys else "",
    )
    log.info(
        "prophet_bridge: intake — %d admitted (%d patience / %d confirmation), "
        "%d duplicate-id, %d open-plan blocked, %d eligible after skips, "
        "%d validation failed, %d originated, %d truncated, lossless=%s",
        len(admitted),
        (admission_stats.get("admitted_by_class") or {}).get(ADMISSION_CLASS_PATIENCE, 0),
        (admission_stats.get("admitted_by_class") or {}).get(
            ADMISSION_CLASS_CONFIRMATION, 0),
        duplicate_id_blocked, len(blocked_keys),
        eligible_after_skips, validation_failed, len(plans), 0, lossless,
    )
    log.info(
        "prophet_bridge: §6.9 R3 — %d wait_reset zone(s) (%s), %d early-turn starter(s) "
        "(%s), %d stale-basis refusal(s) (%s)",
        len(wait_reset_plans), ", ".join(sorted(wait_reset_plans)) or "none",
        len(early_turn_plans), ", ".join(sorted(early_turn_plans)) or "none",
        len(stale_basis_skipped), ", ".join(sorted(stale_basis_skipped)) or "none",
    )
    if validation_failures:
        print(
            "::warning title=Prophet intake validation failures::"
            f"{validation_failed} candidate(s) were not originated; see index.intake."
            "validation_failures",
            flush=True,
        )
    if not lossless:
        print(
            "::warning title=Prophet intake disposition mismatch::"
            f"{unaccounted} admitted candidate(s) have no disclosed disposition",
            flush=True,
        )
    if intake_stats is not None:
        intake_stats["mode"] = "lossless"
        intake_stats["reorigination_blocked"] = len(blocked_keys)
        intake_stats["reorigination_blocked_keys"] = sorted(set(blocked_keys))
        intake_stats["admitted"] = len(admitted)
        intake_stats["duplicate_id_blocked"] = duplicate_id_blocked
        intake_stats["eligible_after_skips"] = eligible_after_skips
        # Retain the old key as an explicit null so downstream readers can distinguish
        # "no cap" from a missing disclosure.  No 12→16 compromise is imported here.
        intake_stats["cap"] = None
        intake_stats["cap_applied"] = False
        intake_stats["truncated"] = 0
        intake_stats["validation_failed"] = validation_failed
        intake_stats["validation_failures"] = validation_failures
        intake_stats["originated"] = len(plans)
        intake_stats["unaccounted"] = unaccounted
        intake_stats["lossless"] = lossless
        intake_stats["all_survivors_originated"] = (
            validation_failed == 0 and len(plans) == eligible_after_skips
        )
        # ── A1 disclosure: the new admission, every refusal, and both guards ──
        intake_stats["selection_era"] = SELECTION_ERA
        intake_stats["admitted_statuses"] = sorted(ADMITTED_STATUSES)
        intake_stats["admitted_directions"] = sorted(ADMITTED_DIRECTIONS)
        intake_stats["buy_rows"] = admission_stats.get("buy_rows", 0)
        intake_stats["admitted_by_class"] = admission_stats.get("admitted_by_class", {})
        intake_stats["unknown_status"] = admission_stats.get("unknown_status", 0)
        intake_stats["unknown_status_values"] = admission_stats.get(
            "unknown_status_values", [])
        intake_stats["refused_status"] = admission_stats.get("refused_status", {})
        intake_stats["refused_direction"] = admission_stats.get("refused_direction", {})
        intake_stats["refused_no_entry_signal"] = admission_stats.get(
            "refused_no_entry_signal", 0)
        intake_stats["refused_band_low"] = admission_stats.get("refused_band_low", 0)
        intake_stats["refused_tier"] = admission_stats.get("refused_tier", {})
        intake_stats["stale_basis_max"] = STALE_BASIS_MAX_SESSIONS
        intake_stats["stale_basis_skipped"] = sorted(stale_basis_skipped)
        intake_stats["originated_by_class"] = {
            klass: sum(1 for p in plans if p.get("admission_class") == klass)
            for klass in (ADMISSION_CLASS_PATIENCE, ADMISSION_CLASS_CONFIRMATION,
                          ADMISSION_CLASS_EARLY_TURN)
        }
        # §6.9 R3 disclosure
        intake_stats["zone_class_counts"] = {
            klass: sum(1 for p in plans
                       if (p.get("entry_zone") or {}).get("zone_class") == klass)
            for klass in (ZONE_CLASS_ACCUMULATE, ZONE_CLASS_RESET_BAND,
                          ZONE_CLASS_WAIT_RESET)
        }
        intake_stats["zone_conversion_classes"] = {
            klass: sum(1 for p in plans
                       if (p.get("entry_zone") or {}).get("conversion_class") == klass)
            for klass in (ZONE_CONVERSION_WASHOUT, ZONE_CONVERSION_PULLBACK)
        }
        intake_stats["wait_reset"] = sorted(wait_reset_plans)
        intake_stats["early_turn_starters"] = sorted(early_turn_plans)
        # A starved extension read fails OPEN for the anti-chase guard (a name we could
        # not measure keeps its board zone), so the count is printed rather than left to
        # be inferred from a silent zero — the #4979 ext_z blackout in miniature.
        intake_stats["zone_extension_unavailable"] = sum(
            1 for p in plans
            if ((p.get("entry_zone") or {}).get("extension") or {}).get("source")
            != "price_store_stoch_rsi"
        )
        intake_stats["leader_pullback_source"] = sorted({
            str((p.get("early_turn") or {}).get("leader_pullback_source"))
            for p in plans
        })
        # THE RECEIPT FOR AN HONEST ZERO.  "No leader-pullback admissions" has two
        # completely different causes — the organ covered these names and none of them is
        # in an open controlled pullback, or the organ covered NONE of them — and a bare
        # zero cannot tell them apart.  Measured 2026-08-09 on the committed 2026-08-07
        # board: 0 admissions either way, but 54/54 candidates read "no coverage" before
        # the publisher and 26/54 carried a real organ state after it, the other 28 being
        # names the deck store does not carry at all.  Printed, never inferred.
        _leader_ctx = [(p.get("entry_zone") or {}).get("leader_pullback") or {}
                       for p in plans]
        intake_stats["leader_pullback_coverage"] = {
            "map_tickers": len(_leader_states),
            "plans": len(plans),
            "with_organ_state": sum(1 for c in _leader_ctx if c.get("state")),
            "outside_organ_universe": sum(
                1 for c in _leader_ctx
                if not c.get("state") and "outside" in str(c.get("reason") or "")),
            "no_coverage_published": sum(
                1 for c in _leader_ctx
                if "published no coverage" in str(c.get("reason") or "")),
            "licensed": sum(1 for c in _leader_ctx if c.get("leader_pullback")),
        }

    # ── W9F: Government Revenue post-selection annotation (display/context) ────
    # Runs HERE and nowhere earlier: selection, ordering, sizing, and gating are
    # complete and `plans` is final, so the adapter's only possible effect is to
    # hang evidence off a plan that already exists. It derives its universe FROM
    # this list, so there is no path by which procurement evidence influences
    # WHICH names are in it, and it fingerprints the decision projection before
    # and after its own work — a pass that moved any decision field discards
    # itself. Fail-open at every layer; a raise here would cost the nightly its
    # plans for an annotation, which is never the right trade.
    return _annotate_with_government_revenue(plans, asof)


def _annotate_with_government_revenue(plans: list[dict], asof: str) -> list[dict]:
    """Attach Government Revenue annotation to plans Prophet ALREADY selected.

    Separate function so the post-selection boundary is visible in a stack trace
    and monkeypatchable in the byte-identity suite.  Today's candidate radar is
    legitimately empty (Wave 9C: it stays empty until a real post-baseline
    eligible event exists), so this is provably inert in production until the
    first exact candidate lands — and `tests/test_government_revenue_prophet_
    annotation.py` pins that inertness against the committed artifact.
    """
    if not plans:
        return plans
    try:
        from engine.government_revenue.prophet_annotation import (  # noqa: PLC0415
            annotate_plans_from_repo,
        )

        return annotate_plans_from_repo(
            plans,
            repo_root=Path(__file__).resolve().parents[1],
            generated_at=f"{asof}T00:00:00+00:00",
        )
    except Exception as exc:  # noqa: BLE001 — annotation never costs Prophet its plans
        log.warning("prophet_bridge: government-revenue annotation skipped (%s)", exc)
        return plans
