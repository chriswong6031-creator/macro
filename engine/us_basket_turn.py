"""engine/us_basket_turn.py — US washout-lifecycle state machine for basket EW level series (W1-D).

The US port of `engine/china_basket_turn.py` (W8-R5).  The CN module is NOT
touched by this port and remains the control — the same discipline
`engine/us_act_now.py` applies to `engine/china_act_now.py`.

Why this exists
---------------
Measured 2026-08-07 (`research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §1.8,
gate G0.6): `china_basket_turn` was the ONLY detector in the estate that changed
state before the 2026-07 precious-metals low — `cn_gold` printed TURNING on
2026-07-16 at dd_252 = -0.4262 and CONFIRMED by 07-20, per that organ's own
forward ledger (this module reads nothing of CN's).  The US had no analog.  The US
`basket_turn` organ (`engine/basket_turn_watch.py`, a *different*, K-of-N
confluence construction) did not print IGNITION on `gold_miners` until
2026-08-05, twelve sessions after the low with GDX already ~+18.6%.

This module gives the US board the CN lifecycle machine over its own baskets.
It is a SECOND, SEPARATE organ — it does not replace, feed, or re-score
`basket_turn_watch`, whose K-of-N leg design is deliberately NOT copied here.

WHAT THE PORT ACTUALLY BUYS ON `gold_miners` (measured, not asserted)
---------------------------------------------------------------------
The paragraph above frames this organ against the incumbent's 2026-08-05
IGNITION.  Read alone that invites the wrong inference, so here is this organ's
OWN record on the same basket, replayed over the committed member tape
(`python -m engine.us_basket_turn --replay gold_miners`, 12/12 members,
2026-01-02..2026-08-06, re-measured 2026-08-07):

    first post-trough TURNING    2026-07-22   dd_252 = -0.3572   (trough 07-20)
    first CONFIRMED              2026-08-05   dd_252 = -0.3017

`basket_turn_watch` printed IGNITION on 2026-08-05.  **Both organs reach their
strongest state on the SAME session.**  This port has NO confirmed-state lead
over the incumbent on the one basket where both have been measured.  Its only
earlier print is TURNING — and TURNING oscillates by construction (see below):
the same machine printed it on 06-16, 06-17, 07-02, 07-06, 07-09 and 07-10,
each time at a LOWER low, and even the 07-22 run lapsed on 07-30 without ever
confirming.  Six early prints preceded the one that held.

The honest claim is therefore NOT "ten sessions earlier".  It is: this organ
discloses the washout lifecycle CONTINUOUSLY — depth, arrest, reclaim, hold —
where the incumbent emits a single binary event, and it pays for that with
oscillation.  Whether the continuous disclosure is worth more than the event is
an open question this ship does not answer, and no surface may imply it does.

Scope / authority (masterplan G0.6)
-----------------------------------
DISPLAY TIER, ZERO SCORED AUTHORITY.  This module ranks nothing, gates nothing,
sizes nothing, and escalates nothing.  It emits a per-basket lifecycle state and
a forward ledger row and stops there.  It does not add to, remove from, or
reorder any `act_now` lane, board population, rank, or gate, and nothing in the
render path reads it as a score.

Honest null / standing law
--------------------------
`DNR:KILL-WASHOUT-TURN` killed the 2W operator-seed **scored entry trigger**
(#1747).  What ships here is a display-tier lifecycle DISCLOSURE — the lawful
form the predecessor plan already reasoned through
(`research/PROPHET_US_MISSED_IGNITIONS_MASTERPLAN_BY_FABLE.md` G0.4, and
`engine/us_act_now.py`'s "Honest null" header).  No state emitted here is an
entry, a buy claim, or an input to one.  Sector-level standalone washout→turn as
a scored trigger stays a printed NULL.

A TURNING print is NOT a bottom call.  Replayed over the committed US member
tape, `gold_miners` printed TURNING on 2026-06-16, 06-17, 07-02, 07-06, 07-09
and 07-10 — SIX sessions, in three episodes — and made LOWER lows each time
before the 07-20 trough.  (v1 of this docstring and the ledger README listed
only four of those six; corrected 2026-08-07 against a re-run of the replay.
Under-counting the oscillation is the one direction this disclosure may never
err in.)  The state machine oscillates inside a washout by construction; that is
disclosure, not a signal, and any surface that renders it must say so.

DEVIATIONS FROM THE CN CONSTRUCTION (every one, and why)
--------------------------------------------------------
The cascade, the state precedence, every threshold, the evidence-tag vocabulary
and the CONFIRMED hysteresis are a VERBATIM port.  Nothing was re-derived,
re-fit, or re-tuned.  What differs is plumbing, and only where CN's version is
CN-specific by construction:

1. INPUT SERIES.  CN reads a pre-aggregated EW level series out of the committed
   `site/chinabasketdata/baskets.json` chart payload.  The US has no equivalent
   committed per-basket level chart available to the organ at nightly time, so
   the level series is built HERE from member closes using the house
   point-in-time dated-membership construction (a member counts only within
   [added, removed); EW mean of active member daily returns; cumprod from the
   first valid session).  That construction mirrors
   `engine/basket_freeze._ew_level_from_closes` and `engine/baskets._ew_level`
   and is COPIED rather than imported on purpose: a private helper carries its
   owner's era, and an amendment inside the freeze module must not be able to
   move a lifecycle state silently.

2. MEMBER PRICE LADDER.  Members resolve through `("stocks", "baskets/ohlcv")` —
   `engine/basket_turn_watch._DEFAULT_STORES` verbatim (W-B, #4579's sibling
   defect).  `data/stocks/` keeps first refusal as the deeper adjusted store;
   `data/baskets/ohlcv/` is the fallback rung.  CN needs no ladder because its
   input arrives already aggregated.

3. COVERAGE IS PRINTED, AND COUNTED AT THE STAMPED SESSION.  Because this module
   does its own aggregation it also owns the coverage hole CN never sees.
   `members_read` / `members_total` land in the artifact AND in every ledger row,
   and a basket under COVERAGE_WARN_FRACTION emits a bare `::warning` line at
   column 0.  W-B law: a coverage hole must be visible, never silent — a basket
   scored on a fraction of its members is not evidence about the basket.

   AMENDMENT 2026-08-07 (post-merge review of #4924): `members_read` counts
   members carrying a bar ON the basket's stamped session (deviation 6), NOT
   members that merely own a store file.  The v1 file-count reported 3/3 for a
   basket whose entire tape was a week stale — it could see a missing FILE and
   never a missing BAR, so it could not fence the stale-stamp defect below.
   `members_with_store` keeps the old file-level count beside it for triage.

4. MEMBER FLOOR.  The house EW construction needs >= 3 readable members
   (`engine/baskets._ew_level:82`, `basket_freeze._ew_level_from_closes:329`).
   Below that this module returns NONE with an `insufficient_members` evidence
   tag rather than aggregating a two-name "basket".  CN has no analog.

5. LEDGER LANE GATE.  CN gates its append on `CN_LANE=asia`; the US nightly
   sentinel is `COLLECT_LANE=nightly`, so the gate here is
   `engine.ledger_lane.nightly_advance_enabled()`.  Same house law (nightly is
   the sole advancer of forward ledgers), different lane sentinel.

6. SESSION STAMP FROM THE DATA PLANE — PER BASKET.  CN's `as_of` is the last
   date of the committed chart, which IS its data plane, and every CN basket
   shares that ONE date axis, so a single global stamp is correct there BY
   CONSTRUCTION.  This module builds each basket's level series independently
   from per-ticker parquet stores (deviation 1), which DESTROYS that
   precondition: one basket's members can go dark while the rest of the estate
   advances.  Each basket is therefore stamped from ITS OWN newest level session
   (`levels.index[-1]`), and both the prior-state read and the keep-first dedupe
   are keyed on that per-basket stamp.  A basket whose tape did not advance
   re-derives the session it already logged, the dedupe refuses the row, and
   `days_in_state` does not move.  A basket with NO readable level series has no
   data plane at all and gets NO ledger row — never a borrowed date.  The
   universe-wide `max()` survives ONLY as the artifact-level `as_of` display
   header; no ledger row is ever stamped with it.

   AMENDMENT 2026-08-07 (post-merge review of #4924).  v1 carried the CN GLOBAL
   stamp — `max()` over every ticker in the US universe — while claiming the
   per-basket property in these very words.  Measured on the patched branch: a
   basket whose members froze at 2026-07-31 accrued rows dated 08-05, 08-06 and
   08-07 with byte-identical `dd_252` and `ret_5d`, and self-promoted to
   CONFIRMED on the third — `CONFIRMED_MIN_DAYS` satisfied by CALENDAR
   REPETITION of one stale bar — while coverage read `3/3` because it counted
   store files.  Keep-first could not refuse it: the key `(date, basket_id)` was
   fresh every night.  The paragraph above was written for the intended design
   and was FALSE of the shipped code until this amendment.  No production row
   was ever written under the defect (`data/us_basket_turn/ledger.jsonl` did not
   exist before this fix landed).

7. UNIVERSE FILTER.  US baskets = `data/baskets/membership.json` minus the
   `cn_` / `hk_` / `ca_` prefixes — the same filter
   `basket_turn_watch._compute_inner` uses.

8. HYSTERESIS RUNS REQUIRE ADJACENT SESSIONS.  CN chains `days_in_state` off the
   newest prior ledger row, which is safe there because its input is one
   contiguous chart axis advanced by one nightly.  Here the prior row can sit an
   arbitrary distance back — a nightly outage, a lane that did not run, a basket
   whose members went dark for a week — and counting it as "yesterday" inflates
   the CONFIRMED hysteresis across a hole nobody observed.  The prior row is
   therefore accepted only when its `date` equals the basket's own IMMEDIATELY
   PRECEDING available session (`levels.index[-2]`); otherwise the run-length
   RESETS to 1.  Deliberately conservative: a gap costs a CONFIRMED that would
   have required the missing sessions to be real.  (Post-merge review of #4924.)

NOT a deviation, checked and rejected: CN daily price limits (±10% / ±20%) and
unadjusted A-share closes have no threshold that depends on them here.
FALLING_RET_THRESH is a 5-session EW basket return, which no single-name limit
band constrains, and the CN note at that constant ("W8-R1 uses -8% for
individual stocks; basket-level EW is smoother, use -6%") applies to a US EW
basket identically.  The thresholds therefore carry over unchanged.

STATE MACHINE (HARD PRECEDENCE cascade — verbatim from china_basket_turn)
--------------------------------------------------------------------------
States are evaluated in STRICT precedence order — first match wins:

1. FALLING (evaluated FIRST, vetoes all others):
   5d return <= FALLING_RET_THRESH  OR
   (MACD hist negative AND hist is falling — i.e. hist_d < 0)
   Rationale: a basket still in active price collapse cannot be at a bottom.

2. TURNING (checked BEFORE WASHED_OUT — extends into partial recovery where the
   basket may have started lifting off its trough while still near the 200d):
   (dd_252 <= WASHOUT_DD_THRESH) AND
   (stoch_reclaim >= STOCH_RECLAIM_THRESH with slope_20d >= 0  OR
    hist_last >= 0 AND hist_d >= TURNING_HIST_CROSS)

3. CONFIRMED (nested inside the TURNING branch):
   days_in_turning >= CONFIRMED_MIN_DAYS  AND  slope_20d >= CONFIRMED_SLOPE_MIN

4. WASHED_OUT (requires: NOT FALLING, NOT TURNING):
   dd_252 <= WASHOUT_DD_THRESH  AND  below 200d MA  AND
   decline arrested (hist_d >= WASHOUT_HIST_ARREST)

5. BASING: dd_252 <= WASHOUT_DD_THRESH and not falling hard

6. NONE — none of the above patterns match

Evidence tags are descriptive only (no forward verbs per house law).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — matches synapse registration)
# ---------------------------------------------------------------------------

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

# Expected-NULL disclosure (FT-R9 shape; US wording cites the US-binding kill row).
DISCLOSURE = (
    "Sector-level standalone washout-to-turn triggers printed NULL "
    "(Oracle P8 P-W1/S-W3; DO_NOT_REBUILD DNR:KILL-WASHOUT-TURN, which closed the "
    "2W operator-seed SCORED entry trigger) — this is a *different construction* "
    "(washout lifecycle at basket granularity, no K-of-N legs, no scored entry) "
    "shipped display-tier as an expected-NULL forward meter (FT-R9). Not a revival "
    "claim. A TURNING print is a state disclosure, never a bottom call: the machine "
    "oscillates inside a washout by construction. Forward ledger starts at ship date; "
    "any state shown for an earlier session is descriptive replay, never ledger evidence."
)

# ---------------------------------------------------------------------------
# Thresholds — VERBATIM from engine/china_basket_turn.py (v1 frozen descriptively,
# FT-R9 / PS-R9).  Amendment log: (date, field, old, new, reason) appended below.
# No US re-derivation: see "DEVIATIONS" in the module docstring.
# ---------------------------------------------------------------------------

# FALLING leg
FALLING_RET_THRESH: float = -0.06          # 5d return <= -6% => FALLING
# (W8-R1 uses -8% for individual stocks; basket-level EW is smoother, use -6%)

# WASHED_OUT legs
WASHOUT_DD_THRESH: float = -0.25           # drawdown vs 252d high <= -25%
WASHOUT_HIST_ARREST: float = -0.005        # hist_d (day-over-day MACD hist change) >= this
                                            # (stabilizing = not aggressively falling)

# TURNING legs
STOCH_RECLAIM_THRESH: float = 0.25         # stochastic (0-1 scale) >= 0.25 = "reclaim"
TURNING_HIST_CROSS: float = 0.0            # MACD hist_d crossed to positive (>= 0)

# CONFIRMED
CONFIRMED_MIN_DAYS: int = 3                # sessions basket must hold TURNING state
CONFIRMED_SLOPE_MIN: float = 0.0           # 20d slope must be non-negative (trending up)

# MACD parameters (applied to the level series)
MACD_FAST: int = 12
MACD_SLOW: int = 26
MACD_SIGNAL: int = 9

# Stochastic window (periods, applied to the level series)
STOCH_WINDOW: int = 14

# ---------------------------------------------------------------------------
# US-specific plumbing constants (deviations 2/3/4/7 above)
# ---------------------------------------------------------------------------

# Member price-store ladder — engine/basket_turn_watch._DEFAULT_STORES verbatim.
# ORDER IS LOAD-BEARING: data/stocks/ is the deeper adjusted store and keeps
# first refusal; data/baskets/ohlcv/ is the fallback rung.
_MEMBER_STORES: tuple[str, ...] = ("stocks", "baskets/ohlcv")

# Non-US basket id prefixes (basket_turn_watch._compute_inner filter).
_NON_US_PREFIXES: tuple[str, ...] = ("cn_", "hk_", "ca_")

# Coverage disclosure (W-B).  NOT a leg and NOT a gate — a thin basket still
# classifies; the hole is printed so it shows up in the Actions summary.
COVERAGE_WARN_FRACTION: float = 0.6

# House EW-level floor (engine/baskets._ew_level, basket_freeze._ew_level_from_closes).
MIN_MEMBERS_FOR_LEVEL: int = 3

_LEDGER_DIR = "us_basket_turn"
_LEDGER_FILE = "ledger.jsonl"
SCHEMA = "us_basket_turn.v1"


# ---------------------------------------------------------------------------
# Core series math (verbatim port)
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _macd(levels: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram) on the level series."""
    fast = _ema(levels, MACD_FAST)
    slow = _ema(levels, MACD_SLOW)
    macd_line = fast - slow
    signal = _ema(macd_line, MACD_SIGNAL)
    hist = macd_line - signal
    return macd_line, signal, hist


def _stoch(levels: pd.Series, window: int = STOCH_WINDOW) -> pd.Series:
    """Stochastic %K on the level series (0..1 scale, NaN when window < min)."""
    roll_min = levels.rolling(window, min_periods=window).min()
    roll_max = levels.rolling(window, min_periods=window).max()
    rng = roll_max - roll_min
    stoch = (levels - roll_min) / rng.where(rng != 0)
    return stoch


def _ret_nd(levels: pd.Series, n: int) -> float | None:
    """n-session return from the last available value. None if insufficient data."""
    vals = levels.dropna()
    if len(vals) < n + 1:
        return None
    prev = float(vals.iloc[-(n + 1)])
    if prev == 0:
        return None
    return float(vals.iloc[-1]) / prev - 1.0


def _drawdown_vs_252d_high(levels: pd.Series) -> float | None:
    """Current EW level relative to the rolling 252-session high. Returns a negative fraction."""
    vals = levels.dropna()
    if len(vals) < 10:
        return None
    high_252 = float(vals[-252:].max() if len(vals) >= 252 else vals.max())
    current = float(vals.iloc[-1])
    if high_252 <= 0:
        return None
    return current / high_252 - 1.0  # e.g. -0.43 for -43% drawdown


def _above_200d(levels: pd.Series) -> bool | None:
    """Is the current level above its 200-session simple moving average?"""
    vals = levels.dropna()
    if len(vals) < 200:
        return None
    ma200 = float(vals.iloc[-200:].mean())
    return float(vals.iloc[-1]) > ma200


def _slope_20d(levels: pd.Series) -> float | None:
    """Linear regression slope over the last 20 sessions (normalised by mean level)."""
    vals = levels.dropna()
    if len(vals) < 20:
        return None
    seg = vals.iloc[-20:].values.astype(float)
    x = np.arange(len(seg), dtype=float)
    mu = np.mean(seg)
    if mu == 0:
        return None
    # OLS slope
    slope = float(np.polyfit(x, seg, 1)[0]) / mu
    return slope


# ---------------------------------------------------------------------------
# Single-basket classification (verbatim port — the ported CONSTRUCTION)
# ---------------------------------------------------------------------------

def classify_basket(levels: pd.Series, prev_state: str | None = None,
                    days_in_state: int = 0) -> dict[str, Any]:
    """Classify one basket's EW level series into a washout-lifecycle state.

    Parameters
    ----------
    levels        : pd.Series — EW index level series (may contain NaNs at start)
    prev_state    : str | None — previous session's state (for CONFIRMED hysteresis)
    days_in_state : int — sessions this basket has been in `prev_state`

    Returns
    -------
    dict with keys:
        state        : str — FALLING / WASHED_OUT / BASING / TURNING / CONFIRMED / NONE
        evidence     : list[str] — descriptive evidence tags (no forward verbs)
        dd_252       : float | None — drawdown vs 252d high (negative fraction)
        hist_d       : float | None — day-over-day change in MACD histogram
        slope_20d    : float | None — normalised 20d linear regression slope
        stoch_last   : float | None — last stochastic value (0..1)
        ret_5d       : float | None — 5-session return
        above_200d   : bool | None — EW level above 200-session SMA
        days_in_state: int — sessions in current returned state
    """
    vals = levels.dropna()

    # Default payload
    out: dict[str, Any] = {
        "state": "NONE",
        "evidence": [],
        "dd_252": None,
        "hist_d": None,
        "slope_20d": None,
        "stoch_last": None,
        "ret_5d": None,
        "above_200d": None,
        "days_in_state": 0,
    }

    if len(vals) < 30:
        out["evidence"].append("insufficient_history")
        return out

    # -- Compute series metrics --
    ret_5d = _ret_nd(vals, 5)
    dd_252 = _drawdown_vs_252d_high(vals)
    ab200 = _above_200d(vals)
    slp20 = _slope_20d(vals)
    out["ret_5d"] = round(ret_5d, 4) if ret_5d is not None else None
    out["dd_252"] = round(dd_252, 4) if dd_252 is not None else None
    out["slope_20d"] = round(slp20, 5) if slp20 is not None else None
    out["above_200d"] = ab200

    # MACD on levels
    _, _, hist_series = _macd(vals)
    hist_last = float(hist_series.iloc[-1]) if not hist_series.empty else None
    hist_prev = float(hist_series.iloc[-2]) if len(hist_series) >= 2 else None
    hist_d: float | None = None
    if hist_last is not None and hist_prev is not None:
        hist_d = hist_last - hist_prev
    out["hist_d"] = round(hist_d, 6) if hist_d is not None else None

    # Stochastic on levels
    stoch_series = _stoch(vals)
    stoch_last: float | None = None
    if not stoch_series.empty and not pd.isna(stoch_series.iloc[-1]):
        stoch_last = float(stoch_series.iloc[-1])
    out["stoch_last"] = round(stoch_last, 4) if stoch_last is not None else None

    evidence: list[str] = []

    # ── HARD PRECEDENCE CASCADE ──────────────────────────────────────────────

    # 1. FALLING — evaluated FIRST, vetoes all others
    falling_ret = ret_5d is not None and ret_5d <= FALLING_RET_THRESH
    falling_macd = (hist_last is not None and hist_last < 0
                    and hist_d is not None and hist_d < 0)
    if falling_ret or falling_macd:
        if falling_ret:
            evidence.append(f"5d_ret={round(ret_5d, 4)}_<=_{FALLING_RET_THRESH}")
        if falling_macd:
            evidence.append(f"macd_hist_neg_and_falling:hist={round(hist_last or 0, 4)},d={round(hist_d or 0, 6)}")
        out["state"] = "FALLING"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state == "FALLING" else 1
        out["days_in_state"] = days_new
        return out

    # 2. Check washout depth (used by WASHED_OUT, TURNING, BASING, CONFIRMED)
    washout_depth_qualifies = (
        dd_252 is not None and dd_252 <= WASHOUT_DD_THRESH
        and (ab200 is False or ab200 is None)  # below or unknown 200d
    )

    # Decline arrested: hist_d is not aggressively falling
    hist_arrested = hist_d is not None and hist_d >= WASHOUT_HIST_ARREST

    # 3. TURNING — checked BEFORE WASHED_OUT since it extends into partial recovery
    # (basket may be slightly above 200d already as it turns)
    stoch_reclaim = stoch_last is not None and stoch_last >= STOCH_RECLAIM_THRESH
    # hist_crossed_positive requires the histogram itself to be non-negative (a true
    # cross from below zero), not merely that hist_d >= 0 (which fires on any
    # deceleration of a still-negative histogram). Without this guard, a basket in a
    # steady near-linear decline whose histogram converges toward zero from below would
    # land in TURNING while price is still falling. (FT-review fix #2, ported.)
    hist_crossed_positive = (
        hist_d is not None and hist_d >= TURNING_HIST_CROSS
        and hist_last is not None and hist_last >= 0.0
    )
    # Downtrend guard: if 20d slope is available and negative, the basket is still
    # trending down and cannot be labelled TURNING on stoch alone.
    slope_still_negative = slp20 is not None and slp20 < 0.0
    stoch_reclaim_valid = stoch_reclaim and not slope_still_negative
    turning_context = dd_252 is not None and dd_252 <= WASHOUT_DD_THRESH  # still deep
    turning_signals = stoch_reclaim_valid or hist_crossed_positive

    if turning_context and turning_signals:
        if stoch_reclaim_valid:
            evidence.append(f"stoch_reclaim={round(stoch_last or 0, 3)}_>=_{STOCH_RECLAIM_THRESH}")
        if hist_crossed_positive:
            evidence.append(f"macd_hist_d_positive={round(hist_d or 0, 6)}")
        evidence.append(f"dd_252={round(dd_252 or 0, 4)}")

        # 4. CONFIRMED — TURNING held long enough AND slope positive
        in_turning = prev_state in ("TURNING", "CONFIRMED")
        days_turning = (days_in_state + 1) if in_turning else 1
        if (days_turning >= CONFIRMED_MIN_DAYS
                and slp20 is not None and slp20 >= CONFIRMED_SLOPE_MIN):
            evidence.append(f"days_turning={days_turning},slope_20d={round(slp20 or 0, 5)}")
            out["state"] = "CONFIRMED"
            out["evidence"] = evidence
            out["days_in_state"] = days_turning
            return out

        out["state"] = "TURNING"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state in ("TURNING", "CONFIRMED") else 1
        out["days_in_state"] = days_new
        return out

    # 5. WASHED_OUT — deep drawdown, below 200d, decline arrested
    if washout_depth_qualifies and hist_arrested:
        evidence.append(f"dd_252={round(dd_252 or 0, 4)}_<=_{WASHOUT_DD_THRESH}")
        evidence.append(f"below_200d=True,hist_arrested=True(d={round(hist_d or 0, 6)})")
        out["state"] = "WASHED_OUT"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state == "WASHED_OUT" else 1
        out["days_in_state"] = days_new
        return out

    # 6. BASING — washout depth qualifies but no turning evidence yet
    if dd_252 is not None and dd_252 <= WASHOUT_DD_THRESH:
        evidence.append(f"dd_252={round(dd_252 or 0, 4)}_basing_no_turn_yet")
        out["state"] = "BASING"
        out["evidence"] = evidence
        days_new = (days_in_state + 1) if prev_state == "BASING" else 1
        out["days_in_state"] = days_new
        return out

    # 7. NONE
    out["state"] = "NONE"
    out["evidence"] = evidence
    out["days_in_state"] = 0
    return out


# ---------------------------------------------------------------------------
# US member tape → EW level series (deviations 1/2/4)
# ---------------------------------------------------------------------------

def _load_close(ticker: str, data_root: Path) -> pd.Series | None:
    """Load one member's close series, walking the member store ladder.

    A rung that exists but carries no usable `close` column falls through to the
    next rung rather than returning a frame the caller cannot read — the same
    contract as `basket_turn_watch._load_prices`.
    """
    for sub in _MEMBER_STORES:
        p = data_root / sub / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns or df.empty:
                log.debug("_load_close(%s): %s/ frame has no usable close", ticker, sub)
                continue
            df.index = pd.to_datetime(df.index)
            s = df["close"].astype(float)
            s = s[~s.index.duplicated(keep="last")].sort_index()
            if s.dropna().empty:
                continue
            return s
        except Exception as e:  # noqa: BLE001
            log.debug("_load_close(%s) from %s/: %s", ticker, sub, e)
            continue
    return None


def active_members(basket: dict) -> list[dict]:
    """Currently active (non-removed) member records with a ticker."""
    return [
        m for m in (basket.get("members") or [])
        if m.get("removed") is None and m.get("ticker")
    ]


def ew_level_from_closes(members: list[dict], closes: dict[str, pd.Series]) -> pd.Series:
    """Point-in-time equal-weight LEVEL series from member closes.

    A member counts only within [added, removed); the level is the cumulative
    product of the equal-weight mean of active member daily returns, based at 1.0
    on the first session with any active member.  Mirrors
    `engine/basket_freeze._ew_level_from_closes` / `engine/baskets._ew_level`
    (copied, not imported — deviation 1).

    Returns an EMPTY series when fewer than MIN_MEMBERS_FOR_LEVEL members are
    readable: an EW "basket" of two names is not the basket.
    """
    present = [m for m in members if (m.get("ticker") or "") in closes]
    if len(present) < MIN_MEMBERS_FOR_LEVEL:
        return pd.Series(dtype="float64")

    mat = pd.DataFrame({m["ticker"]: closes[m["ticker"]] for m in present}).sort_index()
    if mat.empty:
        return pd.Series(dtype="float64")
    idx = mat.index

    mask = pd.DataFrame(False, index=idx, columns=list(mat.columns))
    for m in present:
        t = m["ticker"]
        added = m.get("added")
        if added:
            a = idx >= pd.Timestamp(added)
        else:
            a = np.ones(len(idx), dtype=bool)
        rem = m.get("removed")
        if rem:
            a = a & (idx < pd.Timestamp(rem))
        mask[t] = a

    rets = mat.pct_change(fill_method=None)
    ew = rets.where(mask).mean(axis=1)
    first = ew.first_valid_index()
    if first is None:
        return pd.Series(dtype="float64")
    lvl = pd.Series(np.nan, index=idx, dtype="float64")
    lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    return lvl.dropna()


def _load_membership(data_root: Path) -> dict[str, dict]:
    """US baskets from data/baskets/membership.json (cn_/hk_/ca_ filtered out).

    A membership failure is TOTAL failure — it yields a zero-basket artifact —
    so it is annotated, not merely logged.  v1 used `log.warning` here, which
    means a 59%-coverage basket printed a `::warning` in the Actions summary
    while the organ producing NOTHING AT ALL printed nothing: the louder the
    failure, the quieter the signal.  The annotation must be a BARE print at
    column 0 — this package's logging format prefixes every record and GitHub
    silently drops a `::` that does not start its line
    (tests/test_gh_annotation_line_start.py; this module runs inside an Actions
    step via scripts/build_baskets.py, so it is NOT exempt).
    """
    mp = data_root / "baskets" / "membership.json"
    if not mp.exists():
        print(
            f"::warning title=us-basket-turn::membership.json not found at {mp} "
            f"— 0 US baskets classified, artifact and ledger are EMPTY for this run",
            flush=True,
        )
        log.warning("us_basket_turn: membership.json not found at %s", mp)
        return {}
    try:
        raw = json.loads(mp.read_text())
    except Exception as e:  # noqa: BLE001
        print(
            f"::warning title=us-basket-turn::membership.json unreadable ({e}) "
            f"— 0 US baskets classified, artifact and ledger are EMPTY for this run",
            flush=True,
        )
        log.warning("us_basket_turn: membership.json unreadable: %s", e, exc_info=True)
        return {}
    baskets = raw.get("baskets") or {}
    return {
        bid: b for bid, b in baskets.items()
        if not any(bid.startswith(p) for p in _NON_US_PREFIXES)
    }


# ---------------------------------------------------------------------------
# Prior state (ledger read — CONFIRMED hysteresis accrues honestly)
# ---------------------------------------------------------------------------

def _ledger_path(data_root: Path) -> Path:
    return data_root / _LEDGER_DIR / _LEDGER_FILE


def load_ledger(data_root: Path) -> list[dict]:
    """All ledger rows. Returns [] when the file is missing or unreadable."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as e:  # noqa: BLE001
        log.warning("us_basket_turn: ledger read failed: %s", e)
        return []
    return out


def _ledger_rows_by_basket(data_root: Path) -> dict[str, list[dict]]:
    """basket_id -> its ledger rows, ascending by `date` (one read of the file)."""
    by: dict[str, list[dict]] = {}
    for row in load_ledger(data_root):
        bid = row.get("basket_id") or ""
        if not bid or not (row.get("date") or ""):
            continue
        by.setdefault(bid, []).append(row)
    for rows in by.values():
        rows.sort(key=lambda r: r.get("date") or "")
    return by


def _prior_state(rows: list[dict], session: str,
                 prev_session: str | None) -> tuple[str | None, int]:
    """(state, days_in_state) to chain INTO `session`, or (None, 0) to reset.

    Two fences, both deviations from CN (6 and 8):

    * `session` is the BASKET's own stamped session, not a universe-wide date.
      Rows at or after it are ignored — a row stamped at the session being
      classified is this session's own output, never its prior.
    * the surviving row must sit exactly at `prev_session`, the basket's own
      immediately preceding available session.  A newer-but-not-adjacent row
      means the ledger skipped sessions, and a run-length counted across that
      hole is a hysteresis the sessions never supported, so the run RESETS.
    """
    if not session or not prev_session:
        return (None, 0)
    newest: dict | None = None
    for row in rows:
        rdate = row.get("date") or ""
        if not rdate or rdate >= session:
            continue
        if newest is None or rdate > (newest.get("date") or ""):
            newest = row
    if newest is None or (newest.get("date") or "") != prev_session:
        return (None, 0)
    return (newest.get("state") or None, int(newest.get("days_in_state", 0) or 0))


def _members_at_session(members: list[dict], closes: dict[str, pd.Series],
                        session: str | None) -> int:
    """Members carrying a non-null bar ON `session` (PIT `added` honoured).

    Deviation 3's amendment: the coverage line counts BARS, not FILES, so it can
    see a member whose tape went dark behind the basket's stamped session.
    """
    if not session:
        return 0
    try:
        ts = pd.Timestamp(session)
    except Exception:  # noqa: BLE001 — an unparseable stamp is not a coverage claim
        return 0
    n = 0
    for m in members:
        s = closes.get(m.get("ticker") or "")
        if s is None:
            continue
        added = m.get("added")
        if added:
            try:
                if pd.Timestamp(added) > ts:
                    continue
            except Exception:  # noqa: BLE001 — an unparseable added date does not gate
                pass
        try:
            v = s.get(ts)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(v, pd.Series):  # defensive: _load_close already de-duplicates
            v = v.iloc[-1] if len(v) else None
        if v is None or pd.isna(v):
            continue
        n += 1
    return n


def _null_row(evidence: str) -> dict[str, Any]:
    """The all-None state payload, with one descriptive evidence tag."""
    return {
        "state": "NONE",
        "evidence": [evidence],
        "dd_252": None, "hist_d": None, "slope_20d": None,
        "stoch_last": None, "ret_5d": None, "above_200d": None,
        "days_in_state": 0,
    }


# ---------------------------------------------------------------------------
# Batch compute over the US basket universe
# ---------------------------------------------------------------------------

def compute_all(data_root: Path | None = None) -> dict[str, Any]:
    """Classify every US basket from committed member closes. Never raises.

    Returns the full artifact dict: schema, as_of, data_session, disclosure,
    authority, coverage summary, and per-basket states.
    """
    from lib import config as _cfg
    root = data_root if data_root is not None else _cfg.data_dir()

    us_baskets = _load_membership(root)

    # Member tape (one read per distinct ticker across all baskets).
    all_tickers: set[str] = set()
    for b in us_baskets.values():
        all_tickers.update(m["ticker"] for m in active_members(b))

    closes: dict[str, pd.Series] = {}
    for tk in sorted(all_tickers):
        s = _load_close(tk, root)
        if s is not None:
            closes[tk] = s

    # --- universe display header (NOT a ledger stamp) -------------------------
    # Deviation 6.  The newest member bar ANYWHERE in the US universe.  This is
    # the artifact's freshness header and nothing else: every ledger row is
    # stamped from its OWN basket's last level session, below.  Stamping a
    # basket with this date is precisely the defect the amendment closed.
    universe_session: str | None = None
    try:
        last_bars = [s.dropna().index.max() for s in closes.values() if len(s.dropna())]
        if last_bars:
            universe_session = str(pd.Timestamp(max(last_bars)).date())
    except Exception as e:  # noqa: BLE001 — stamp derivation is never fatal
        log.debug("us_basket_turn: universe_session derivation failed: %s", e)

    as_of = universe_session or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger_rows = _ledger_rows_by_basket(root)

    results: dict[str, dict] = {}
    coverage_holes: list[str] = []
    stale_baskets: list[str] = []
    sessionless: list[str] = []

    for bid in sorted(us_baskets):
        members = active_members(us_baskets[bid])
        total = len(members)
        with_store = sum(1 for m in members if m["ticker"] in closes)

        levels = pd.Series(dtype="float64")
        build_error: str | None = None
        try:
            levels = ew_level_from_closes(members, closes)
        except Exception as e:  # noqa: BLE001 — one basket never kills the organ
            log.warning("us_basket_turn: %s level build failed: %s", bid, e)
            build_error = f"error:{e}"

        # Deviation 6: this basket's OWN data plane, and the session before it.
        basket_session: str | None = None
        prev_session: str | None = None
        if not levels.empty:
            basket_session = str(pd.Timestamp(levels.index[-1]).date())
            if len(levels.index) >= 2:
                prev_session = str(pd.Timestamp(levels.index[-2]).date())

        # Coverage at the stamped session (deviation 3 amendment).  With no
        # session there is no bar to count at, so the store-file count is the
        # only reading available and stands in — the evidence tag says so.
        read = _members_at_session(members, closes, basket_session) \
            if basket_session else with_store

        # W-B law (deviation 3): the hole is printed, never silent.  BARE print at
        # line start, never a logger — GitHub only parses '::' at column 0 and this
        # package's logging format prefixes every record
        # (tests/test_gh_annotation_line_start.py).
        if total > 0 and (read / total) < COVERAGE_WARN_FRACTION:
            coverage_holes.append(bid)
            print(
                f"::warning title=us-basket-turn-coverage::"
                f"{bid} reads {read}/{total} members",
                flush=True,
            )

        # A basket behind the estate is the shape that used to be written under a
        # borrowed fresh date.  It is now stamped honestly AND said out loud.
        if basket_session and universe_session and basket_session < universe_session:
            stale_baskets.append(bid)
            print(
                f"::warning title=us-basket-turn-stale::{bid} last member bar is "
                f"{basket_session}, behind the universe session {universe_session} "
                f"— its row is stamped {basket_session} and re-derives, it does not accrue",
                flush=True,
            )
        if basket_session is None:
            sessionless.append(bid)

        ps, dis = _prior_state(ledger_rows.get(bid, []), basket_session or "", prev_session)

        if levels.empty:
            out = _null_row(build_error or f"insufficient_members:{with_store}/{total}")
        else:
            try:
                out = classify_basket(levels, prev_state=ps, days_in_state=dis)
            except Exception as e:  # noqa: BLE001 — one basket never kills the organ
                log.warning("us_basket_turn: %s failed: %s", bid, e)
                out = _null_row(f"error:{e}")

        out["members_read"] = read
        out["members_with_store"] = with_store
        out["members_total"] = total
        out["data_session"] = basket_session
        results[bid] = out

    return {
        "schema": SCHEMA,
        "as_of": as_of,
        # Universe-wide display header.  NOT the stamp on any ledger row — read
        # `baskets[<id>]["data_session"]` for the session a row actually carries.
        "data_session": universe_session,
        "disclosure": DISCLOSURE,
        "authority": AUTHORITY,
        "coverage": {
            "warn_fraction": COVERAGE_WARN_FRACTION,
            "baskets_below_warn": sorted(coverage_holes),
            "baskets_behind_universe": sorted(stale_baskets),
            "baskets_without_session": sorted(sessionless),
            "members_read": sum(r.get("members_read", 0) for r in results.values()),
            "members_total": sum(r.get("members_total", 0) for r in results.values()),
        },
        "baskets": results,
    }


# ---------------------------------------------------------------------------
# Artifact writer (site/basketdata/us_basket_turn.json)
# ---------------------------------------------------------------------------

def write_artifact(artifact: dict[str, Any], site_root: Path | None = None) -> Path:
    """Write the us_basket_turn.json artifact to site/basketdata/."""
    if site_root is None:
        from lib import config as _cfg
        site_root = _cfg.ROOT / _cfg.load()["storage"]["site_dir"]
    out_dir = site_root / "basketdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "us_basket_turn.json"
    out_path.write_text(
        json.dumps(artifact, separators=(",", ":"), default=str) + "\n",
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# Ledger writer (data/us_basket_turn/ledger.jsonl)
# ---------------------------------------------------------------------------

def append_ledger(artifact: dict[str, Any], data_root: Path) -> int:
    """Append one row per basket to the PIT forward ledger. Returns rows appended.

    Append-only, keep-first per (date, basket_id), where `date` is the BASKET's
    OWN stamped session (`baskets[<id>]["data_session"]`, deviation 6) — never
    the artifact-level universe header.  That is what makes keep-first a real
    fence: a basket whose tape did not advance re-derives the session it already
    logged, so the key collides and the row is refused, instead of accruing a
    fresh-dated duplicate of one stale bar.  A basket with no session at all
    (no readable level series) gets NO row — a ledger date is a measurement, and
    borrowing one from a sibling basket is a fabrication.

    Gated on the US nightly lane (`COLLECT_LANE=nightly`, deviation 5) — house
    law: nightly is the sole advancer of forward ledgers, and an intraday lane's
    `data/` writes are discarded.
    """
    if not _ledger_advance_enabled():
        log.info("us_basket_turn: ledger append skipped (COLLECT_LANE != nightly)")
        return 0

    baskets = artifact.get("baskets") or {}
    if not baskets:
        return 0

    ledger_path = _ledger_path(data_root)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    seen: set[tuple[str, str]] = {
        (r.get("date", ""), r.get("basket_id", "")) for r in load_ledger(data_root)
    }

    rows_written = 0
    skipped_no_session = 0
    stamps: set[str] = set()
    with ledger_path.open("a") as fh:
        for bid in sorted(baskets):
            st = baskets[bid]
            stamp = st.get("data_session") or ""
            if not stamp:
                skipped_no_session += 1
                continue
            key = (stamp, bid)
            if key in seen:
                continue
            stamps.add(stamp)
            row = {
                "date": stamp,
                "as_of": stamp,
                "basket_id": bid,
                "state": st.get("state", "NONE"),
                "dd_252": st.get("dd_252"),
                "hist_d": st.get("hist_d"),
                "slope_20d": st.get("slope_20d"),
                "ret_5d": st.get("ret_5d"),
                "evidence": st.get("evidence", []),
                "days_in_state": st.get("days_in_state", 0),
                "members_read": st.get("members_read"),
                "members_with_store": st.get("members_with_store"),
                "members_total": st.get("members_total"),
            }
            fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")
            rows_written += 1
            seen.add(key)

    log.info("us_basket_turn: ledger appended %d rows across sessions %s "
             "(%d basket(s) had no data-plane session and were not written)",
             rows_written, sorted(stamps) or "-", skipped_no_session)
    return rows_written


# ---------------------------------------------------------------------------
# Entry point (called from scripts/build_baskets.py)
# ---------------------------------------------------------------------------

def run(data_root: Path | None = None, site_root: Path | None = None) -> dict[str, Any]:
    """Compute + write artifact + conditionally append ledger. Returns the artifact."""
    from lib import config as _cfg
    root = data_root if data_root is not None else _cfg.data_dir()

    t0 = time.time()
    artifact = compute_all(data_root=root)
    elapsed = time.time() - t0

    state_counts: dict[str, int] = {}
    for st in artifact.get("baskets", {}).values():
        s = st.get("state", "NONE")
        state_counts[s] = state_counts.get(s, 0) + 1
    log.info("us_basket_turn: classified %d baskets in %.2fs — state dist: %s",
             len(artifact.get("baskets", {})), elapsed, state_counts)

    out_path = write_artifact(artifact, site_root)
    log.info("us_basket_turn: wrote artifact %s", out_path)

    append_ledger(artifact, root)
    return artifact


# ---------------------------------------------------------------------------
# Descriptive replay (evidence, never a ledger write)
# ---------------------------------------------------------------------------

def replay(basket_id: str, start: str, end: str,
           data_root: Path | None = None) -> list[dict[str, Any]]:
    """Walk one basket's committed member tape session by session.

    DESCRIPTIVE ONLY.  Chains prev_state/days_in_state exactly as the nightly
    would have, but writes nothing: a replayed state is not ledger evidence (the
    forward ledger starts at ship date).  Used to produce PR-body evidence.
    """
    from lib import config as _cfg
    root = data_root if data_root is not None else _cfg.data_dir()

    baskets = _load_membership(root)
    basket = baskets.get(basket_id)
    if basket is None:
        return []
    members = active_members(basket)
    closes = {}
    for m in members:
        s = _load_close(m["ticker"], root)
        if s is not None:
            closes[m["ticker"]] = s

    levels = ew_level_from_closes(members, closes)
    if levels.empty:
        return []

    rows: list[dict[str, Any]] = []
    prev_state: str | None = None
    days = 0
    t_start, t_end = pd.Timestamp(start), pd.Timestamp(end)
    for d in levels.index:
        if d > t_end:
            break
        out = classify_basket(levels.loc[:d], prev_state=prev_state, days_in_state=days)
        if d >= t_start:
            rows.append({
                "date": str(d.date()),
                "basket_id": basket_id,
                "members_read": len(closes),
                "members_total": len(members),
                "level": round(float(levels.loc[d]), 6),
                **{k: out[k] for k in
                   ("state", "dd_252", "slope_20d", "stoch_last", "ret_5d", "days_in_state")},
            })
        prev_state, days = out["state"], out["days_in_state"]
    return rows


def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--replay", metavar="BASKET_ID",
                    help="descriptive replay for one basket (writes nothing)")
    ap.add_argument("--from", dest="start", default="2026-06-01")
    ap.add_argument("--to", dest="end", default="2026-08-06")
    args = ap.parse_args(argv)

    if args.replay:
        for r in replay(args.replay, args.start, args.end):
            print(f"{r['date']}  {r['state']:<11} dd_252={r['dd_252']} "
                  f"slope_20d={r['slope_20d']} stoch={r['stoch_last']} "
                  f"ret_5d={r['ret_5d']} d={r['days_in_state']}")
        return 0

    logging.basicConfig(level=logging.INFO)
    run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
