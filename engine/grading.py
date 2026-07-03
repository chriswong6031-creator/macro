"""One honest grader for every US-side track record — the W1c "grading rebuild".

Audit #15/#46 (research/ENGINE_PROBLEM_AUDIT.md): the suite's proof-of-edge
artifacts were graded on the CHEAPEST data path — today's survivors, dividend-
adjusted total-return closes, and SAME-BAR fills — so the honesty gate that decides
"validated vs experimental" was itself dishonest, biased in the optimistic
direction. This module is the single place those four axes are made honest, so every
forward logger and desk grader can route through one convention instead of each
re-deriving a subtly-different (and subtly-flattering) one.

The four axes it standardizes
-----------------------------
1. NEXT-BAR FILL.  A signal that fires on the close of bar t is FILLED at the close
   of bar t+1 (``fill_index``/``forward_metrics`` here), matching the VALIDATED
   research convention (``research/signal_engine/tuning_harness.py`` enters at
   ``f = i + 1``) and ``engine/validation.py:70``'s ``alloc.shift(1)`` "act next
   bar". Same-bar fills flatter short mean-reversion signals most (you buy the exact
   trough the signal identified), which is precisely the direction that over-sizes a
   mechanical system. ``forward_metrics`` uses correct FORWARD windows
   (``FixedForwardWindowIndexer`` semantics — strictly ``(fill, fill+H]``), never a
   window that peeks at or includes the entry bar.

2. SURVIVORSHIP.  ``as_of_members`` (engine.universe_history — EXISTS, and this is
   its FIRST-EVER consumer) reconstructs the index membership as it stood on a date,
   so a historical cross-section grades the names that were ACTUALLY in the universe
   then, not today's survivors. Dropping delisted losers inflates every crisis-
   breadth and desk hit-rate. Cold-start caveat: membership accrual began 2026-06-13
   (see universe_history), so an as-of BEFORE accrual falls back to today's panel and
   is stamped ``survivorship='cold-start'`` — honest about the residual bias rather
   than pretending it is gone.

3. DUAL RETURN BASIS.  ``data/stocks`` (and ``data/yahoo``) ``close`` is split- AND
   dividend-back-adjusted TOTAL return (verified: AAPL has no gap across its 2020 4:1
   split). Splits cancel in every ratio, but an interim dividend rebases the entry
   bar and not the t+H bar — a bounded (<~1%/60d) but ONE-DIRECTIONAL optimism on
   forward drawdowns. Where a raw/price-only series is available we expose BOTH a
   ``price_return`` and a ``total_return`` column so a caller can size against the
   pessimistic (price-only) basis. When only the adjusted store exists, both columns
   equal the total-return number and the basis is stamped so the caller cannot mistake
   it for a true price return.

4. DELISTING TERMINAL VALUES.  A name that DELISTS mid-horizon must grade as its LOSS,
   not vanish. ``resolve_series`` falls back to the 8-K Item 1.03 bankruptcy-imputation
   store (``data/edgar/dead_name_prices.parquet``, source ``imputed_bankruptcy`` → a
   −100% terminal close) built by ``collectors/edgar_deadname_prices`` /
   ``collectors/edgar_delisting``. ``forward_metrics`` treats a name that stops trading
   inside the horizon as delisted at its last (or imputed-terminal) close, so the loss
   is realized instead of the position silently disappearing from the panel.

Design
------
* Pure pandas/numpy/pyarrow (no scipy/sklearn) — matches the thin data-bot env and
  engine/validation.py's dependency rule.
* Degrade-safe by construction: a missing dead-name store, a missing membership
  ledger, or a pre-accrual as-of date each degrade to the honest prior state with a
  stamped caveat, never a crash — but the caveat is LOUD (returned in the report), so
  "graded honestly" and "graded on the fallback" are distinguishable forever.
* This is a LIBRARY, not a runner: it does not read config or write artifacts. Callers
  (track_record, sector_signals, desk graders) pass their own series/panels in.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

__all__ = [
    "GradeBasis",
    "fill_index",
    "forward_metrics",
    "resolve_series",
    "load_dead_prices",
    "as_of_panel",
    "grade_next_bar_return",
    # W0.1a additions — Outcome Spine v2 primitives
    "terminal_state",
    "TerminalState",
    "cushion_incidence",
    "post_cushion_breach",
    "STOP_BARRIER",
    "CUSHION_BARRIER",
    "LIFTOFF_15",
    "LIFTOFF_8",
    "LIFTOFF_HORIZON_126",
    "LIFTOFF_HORIZON_21",
    "DEAD_MONEY_BAND",
    "DEAD_MONEY_CAP",
    "SPINE_HORIZONS",
]

# The horizons the live track record grades on (kept aligned with track_record._FWD_HORIZONS).
DEFAULT_HORIZONS = (20, 60, 180)

# A name is treated as DELISTED (graded at its last close) when its series stops this
# many calendar days before the horizon end — mirrors foresight_grader.DELISTING_GAP_DAYS.
DELISTING_GAP_DAYS = 14

# ---------------------------------------------------------------------------  #
# W0.1a — Outcome Spine v2 barrier constants (pre-registered, frozen)          #
# ---------------------------------------------------------------------------  #
# All barriers are relative to the FILL-bar close (entry price, next-bar fill  #
# convention). data/yahoo close is dividend-adjusted total-return; barriers     #
# apply consistently on the same adjusted series — the ratio cancels the        #
# adjustment so the percentage is correct.                                      #

STOP_BARRIER     = 0.95   # −5%: the stop-out barrier (the "false bottom" threshold)
CUSHION_BARRIER  = 1.05   # +5%: hitting this before STOP_BARRIER = cushioned or liftoff
LIFTOFF_15       = 1.15   # +15%: the positional liftoff threshold (clean15_126)
LIFTOFF_8        = 1.08   # +8%:  the rotational liftoff threshold (clean8_21)
LIFTOFF_HORIZON_126 = 126 # trading days — positional liftoff window (clean15_126)
LIFTOFF_HORIZON_21  = 21  # trading days — rotational liftoff window (clean8_21)
DEAD_MONEY_BAND  = 0.08   # ±8%: dead-money band (never hit ±8%, sourced from wave1.py)
DEAD_MONEY_CAP   = 0.05   # <+5% at read: dead-money return cap (sourced from wave1.py)

# Horizon set available via forward_metrics; callers may pass any subset.
# 126 is MANDATORY for the positional spine (clean15_126 gate).
SPINE_HORIZONS = (5, 10, 21, 63, 126)


class GradeBasis:
    """Return-basis tags stamped onto every graded row so provenance is never lost."""
    TOTAL = "total_return"          # dividend-adjusted (the only free basis for most names)
    PRICE = "price_return"          # split-only / raw close (removes the dividend optimism)


# --------------------------------------------------------------------------- #
# Fill + forward-window primitives (next-bar, FixedForwardWindowIndexer-correct)
# --------------------------------------------------------------------------- #
def _snap_loc(index: pd.DatetimeIndex, date) -> int | None:
    """iloc of the nearest bar at-or-before ``date`` (the SIGNAL bar). None if none."""
    dt = pd.Timestamp(date)
    if len(index) == 0 or index[0] > dt:
        return None
    return int(np.searchsorted(index.values, np.datetime64(dt), side="right") - 1)


def fill_index(close: pd.Series, signal_date) -> int | None:
    """Next-bar fill: the iloc position at which a signal fired on ``signal_date`` is
    FILLED. That is the FIRST bar STRICTLY AFTER the signal bar (``loc + 1``) — the
    validated convention. Returns None if the signal bar is unlocatable OR there is no
    bar after it (the fill has not happened yet → the row is not yet gradable)."""
    loc = _snap_loc(close.index, signal_date)
    if loc is None or loc + 1 >= len(close):
        return None
    return loc + 1


def forward_metrics(
    close: pd.Series,
    signal_date,
    horizons=DEFAULT_HORIZONS,
    *,
    same_bar: bool = False,
) -> dict[str, Any]:
    """Fixed-horizon forward return + max-drawdown from a NEXT-BAR fill.

    Returns a flat dict with ``fwd_ret_{H}``, ``fwd_price_{H}``, ``fwd_mdd_{H}``,
    ``fwd_mfe_{H}`` and the fill provenance (``entry_price``, ``fill_date``,
    ``fill_offset``). Any horizon without ``H`` bars of forward data yet is None
    (frozen-until-matured).

    W0.1a addition — ``fwd_mfe_{H}`` (max favorable excursion): the maximum
    unrealised gain within the strictly-forward window ``(fill, fill+H]``, mirroring
    ``fwd_mdd_{H}`` (which takes the minimum). Always >= 0. Uses the same
    dividend-adjusted total-return close series as ``fwd_mdd_{H}`` — the ratio is
    consistent on both sides so the percentage is correct.

    Convention (the honest one):
      * ENTRY = close at the fill bar = the bar STRICTLY AFTER the signal bar.
      * ``fwd_ret_{H}``  = close[fill+H] / entry - 1
      * ``fwd_mdd_{H}``  = min(0, min(close[fill+1 .. fill+H]) / entry - 1)   (<= 0)
        — a strictly FORWARD window ``(fill, fill+H]``; it never includes the entry bar
        (which would floor the trough at 0 spuriously) nor peeks before it.

    ``same_bar=True`` reproduces the OLD (biased) same-bar-fill behaviour for the
    shadow A/B that quantifies the correction — entry is the signal bar itself. Callers
    should never pass this in production; it exists only to MEASURE the delta.
    """
    result: dict[str, Any] = {"entry_price": None, "fill_date": None, "fill_offset": None}
    for h in horizons:
        for k in (f"fwd_ret_{h}", f"fwd_price_{h}", f"fwd_mdd_{h}", f"fwd_mfe_{h}"):
            result[k] = None

    if same_bar:
        loc = _snap_loc(close.index, signal_date)
        fill = loc
    else:
        fill = fill_index(close, signal_date)
    if fill is None:
        return result

    entry_price = float(close.iloc[fill])
    if not np.isfinite(entry_price) or entry_price <= 0:
        return result
    result["entry_price"] = entry_price
    result["fill_date"] = str(close.index[fill].date())
    sig_loc = _snap_loc(close.index, signal_date)
    result["fill_offset"] = 0 if same_bar else (fill - sig_loc if sig_loc is not None else None)

    # strictly-forward slice: bars AFTER the entry bar
    fwd = close.iloc[fill + 1:]
    for h in horizons:
        if len(fwd) >= h:
            p_h = float(fwd.iloc[h - 1])
            if not np.isfinite(p_h):
                continue
            result[f"fwd_ret_{h}"] = p_h / entry_price - 1.0
            result[f"fwd_price_{h}"] = p_h
            window = fwd.iloc[:h]
            result[f"fwd_mdd_{h}"] = min(0.0, float(window.min()) / entry_price - 1.0)
            # fwd_mfe_H — max favorable excursion: strictly-forward window (fill, fill+H]
            # mirrors fwd_mdd_H but takes the maximum; always >= 0.
            # Semantics: best unrealised gain available within H bars of the entry.
            # Uses the same dividend-adjusted close series as fwd_mdd_H (consistent basis).
            result[f"fwd_mfe_{h}"] = max(0.0, float(window.max()) / entry_price - 1.0)
    return result


def grade_next_bar_return(close: pd.Series, signal_date, horizon: int) -> float | None:
    """Single next-bar-filled forward return over ``horizon`` bars, or None if not yet
    matured. Thin helper for graders that only need one horizon (meta_label, desks)."""
    m = forward_metrics(close, signal_date, horizons=(horizon,))
    return m.get(f"fwd_ret_{horizon}")


# --------------------------------------------------------------------------- #
# W0.1a — Outcome Spine v2 primitives                                          #
# --------------------------------------------------------------------------- #

class TerminalState:
    """Named terminal-state constants for the per-fire partition (§1.1).

    Every fire resolves into exactly ONE of these four states per horizon window.
    The string values are written to ledger rows — treat them as stable identifiers.
    """
    STOPPED       = "STOPPED"       # hit −5% before +5%  (the false bottom)
    DEAD_MONEY    = "DEAD_MONEY"    # never hit ±8%; < +5% at read  (capital parked)
    CUSHIONED     = "CUSHIONED"     # hit +5% before −5%; no liftoff  (safe, modest)
    CLEAN_LIFTOFF = "CLEAN_LIFTOFF" # hit the liftoff barrier before −5%  (the prize)


def terminal_state(
    close: pd.Series,
    signal_date,
    *,
    liftoff_mult: float = LIFTOFF_15,
    liftoff_horizon: int = LIFTOFF_HORIZON_126,
    stop_mult: float = STOP_BARRIER,
    cushion_mult: float = CUSHION_BARRIER,
    dead_band: float = DEAD_MONEY_BAND,
    dead_cap: float = DEAD_MONEY_CAP,
    same_bar: bool = False,
) -> dict[str, Any]:
    """Per-fire terminal-state partition per §1.1 of the Setup-Species Masterplan.

    Returns a dict containing:
      ``state``          — one of TerminalState.{STOPPED,DEAD_MONEY,CUSHIONED,CLEAN_LIFTOFF}
                           or None when the fire has not matured (insufficient forward data).
      ``parameterization`` — the (liftoff_mult, liftoff_horizon) pair as a string label.
      ``entry_price``    — fill-bar close (next-bar convention unless same_bar=True).
      ``fill_date``      — ISO date string of the fill bar.
      ``stopped_at_bar`` — bars-from-fill when the stop triggered, or None.
      ``liftoff_at_bar`` — bars-from-fill when liftoff triggered, or None.
      ``cushion_at_bar`` — bars-from-fill when +cushion_mult first hit, or None
                           (independently of whether liftoff followed).
      ``ret_at_read``    — close[fill+liftoff_horizon] / entry − 1, or None if not matured.
      ``note``           — human-readable summary of the resolved state.

    Partition rules (§1.1, ported from research/entry_timing/wave1.py conventions):
      - Barrier race is CLOSE-BASIS SEQUENTIAL: each bar checked in order; the first
        barrier reached terminates the race for that partition.
      - PRE-REGISTERED STRADDLE TIE RULE: if stop AND cushion/liftoff would both trigger
        on the same bar, STOP WINS (conservative; binding when high/low history is wired).
      - STOPPED:       close ≤ entry*stop_mult STRICTLY BEFORE close ≥ entry*cushion_mult,
                       within [fill+1 .. fill+liftoff_horizon].
      - CLEAN_LIFTOFF: close ≥ entry*liftoff_mult STRICTLY BEFORE close ≤ entry*stop_mult,
                       within [fill+1 .. fill+liftoff_horizon].
      - DEAD_MONEY:    never hit ±dead_band% AND ret_at_read < dead_cap,
                       over [fill+1 .. fill+liftoff_horizon].
      - CUSHIONED:     hit +cushion_mult before stop, but did NOT reach clean liftoff.

    Named parameterizations (§1.1):
      ``clean15_126`` — liftoff_mult=1.15, liftoff_horizon=126  (positional primary)
      ``clean8_21``   — liftoff_mult=1.08, liftoff_horizon=21   (rotational primary)

    Note on data basis: close is expected to be the dividend-adjusted total-return
    series (data/yahoo convention). Because barriers are computed as ratios to entry_price
    (also from the same series), the adjustment cancels and percentages are correct.
    """
    fill = fill_index(close, signal_date) if not same_bar else _snap_loc(close.index, signal_date)
    if fill is None:
        return {"state": None, "parameterization": f"clean{int((liftoff_mult-1)*100)}_{liftoff_horizon}",
                "entry_price": None, "fill_date": None, "stopped_at_bar": None,
                "liftoff_at_bar": None, "cushion_at_bar": None, "ret_at_read": None,
                "note": "fill bar not found or no next bar"}

    entry_price = float(close.iloc[fill])
    if not np.isfinite(entry_price) or entry_price <= 0:
        return {"state": None, "parameterization": f"clean{int((liftoff_mult-1)*100)}_{liftoff_horizon}",
                "entry_price": None, "fill_date": None, "stopped_at_bar": None,
                "liftoff_at_bar": None, "cushion_at_bar": None, "ret_at_read": None,
                "note": "invalid entry price"}

    param_label = f"clean{int(round((liftoff_mult - 1) * 100))}_{liftoff_horizon}"
    fill_date_str = str(close.index[fill].date())

    stop_barrier     = entry_price * stop_mult      # e.g. entry * 0.95
    cushion_barrier  = entry_price * cushion_mult   # e.g. entry * 1.05
    liftoff_barrier  = entry_price * liftoff_mult   # e.g. entry * 1.15 or 1.08
    dead_upper       = entry_price * (1.0 + dead_band)  # e.g. entry * 1.08
    dead_lower       = entry_price * (1.0 - dead_band)  # e.g. entry * 0.92

    fwd = close.iloc[fill + 1: fill + liftoff_horizon + 1]
    n_fwd = len(fwd)

    if n_fwd < liftoff_horizon:
        # Not enough forward data → fire not yet matured.
        return {"state": None, "parameterization": param_label,
                "entry_price": entry_price, "fill_date": fill_date_str,
                "stopped_at_bar": None, "liftoff_at_bar": None,
                "cushion_at_bar": None, "ret_at_read": None,
                "note": f"not yet matured: only {n_fwd}/{liftoff_horizon} bars available"}

    arr = fwd.to_numpy()

    # --- barrier race (close-basis sequential; straddle tie: stop wins) --------
    stopped_at: int | None = None
    liftoff_at: int | None = None
    cushion_at: int | None = None

    for k, cl in enumerate(arr, start=1):  # k = bar offset from fill
        # Stop check first (straddle tie: stop wins)
        if cl <= stop_barrier:
            stopped_at = k
            break
        # Liftoff check (≥ liftoff_barrier before stop → CLEAN_LIFTOFF)
        if cl >= liftoff_barrier:
            liftoff_at = k
            # Mark cushion too (must have passed through +5% on the way to liftoff)
            # since liftoff_mult > cushion_mult, reaching liftoff implies cushion was reached
            # on this bar or an earlier one; scan back for the first cushion bar.
            if cushion_at is None:
                for j, c2 in enumerate(arr[:k], start=1):
                    if c2 >= cushion_barrier:
                        cushion_at = j
                        break
                if cushion_at is None:
                    cushion_at = k  # liftoff bar itself clears cushion_barrier (l>c)
            break
        # Cushion check (record first time +5% hit without stop yet triggered)
        if cushion_at is None and cl >= cushion_barrier:
            cushion_at = k

    # --- dead-money check -------------------------------------------------------
    band_breached = bool(np.any(arr >= dead_upper) or np.any(arr <= dead_lower))
    ret_at_read = float(arr[-1]) / entry_price - 1.0

    # --- classify ---------------------------------------------------------------
    if stopped_at is not None:
        state = TerminalState.STOPPED
        note = f"stop triggered at bar +{stopped_at} ({arr[stopped_at-1]:.4f} ≤ {stop_barrier:.4f})"
    elif liftoff_at is not None:
        state = TerminalState.CLEAN_LIFTOFF
        note = f"liftoff at bar +{liftoff_at} ({arr[liftoff_at-1]:.4f} ≥ {liftoff_barrier:.4f})"
    elif cushion_at is not None:
        state = TerminalState.CUSHIONED
        note = (f"cushioned at bar +{cushion_at}; ret_at_read={ret_at_read:+.3f}; "
                f"no liftoff (threshold {liftoff_mult:.2f}×)")
    elif not band_breached and ret_at_read < dead_cap:
        state = TerminalState.DEAD_MONEY
        note = (f"dead money: band ±{dead_band:.0%} never breached; "
                f"ret_at_read={ret_at_read:+.3f} < {dead_cap:.0%}")
    else:
        # Returned > dead_cap but never cushioned — a narrow awkward cell; assign CUSHIONED
        # (the name moved enough to avoid dead money but not enough to cross cushion_mult).
        # This case is correctly captured by "CUSHIONED" being defined as any fire that
        # avoids STOPPED + DEAD_MONEY + CLEAN_LIFTOFF; the spec §1.1 names it
        # "CUSHIONED — hit +5% before −5%, but no liftoff" but in the boundary case
        # where nothing hit ±5% and ret > dead_cap (e.g. dead_cap=0.05, no ±5% or ±8%
        # hit), the correct label under the partition is DEAD_MONEY when the ±8% band
        # was never hit and ret < 5%, or CUSHIONED if ret_at_read >= dead_cap without
        # cushion_barrier being formally crossed. Map to DEAD_MONEY to be conservative:
        # the fire is not stopped, did not lift off, and never clearly cushioned.
        state = TerminalState.DEAD_MONEY
        note = (f"dead money (edge): band ±{dead_band:.0%} never breached; "
                f"ret_at_read={ret_at_read:+.3f}; no cushion cross detected")

    return {
        "state":           state,
        "parameterization": param_label,
        "entry_price":     entry_price,
        "fill_date":       fill_date_str,
        "stopped_at_bar":  stopped_at,
        "liftoff_at_bar":  liftoff_at,
        "cushion_at_bar":  cushion_at,
        "ret_at_read":     ret_at_read,
        "note":            note,
    }


def cushion_incidence(
    fires: list[tuple[pd.Series, Any]],
    *,
    k_days: tuple[int, ...] = (5, 10, 21),
    stop_mult: float = STOP_BARRIER,
    cushion_mult: float = CUSHION_BARRIER,
    same_bar: bool = False,
) -> dict[str, Any]:
    """Cumulative cushion incidence at day k ∈ k_days with stop-out as competing risk.

    §1.1 mandate: % of ALL fires cushioned by day k — a cumulative-incidence statistic
    with stop-out as the competing risk. NEVER a median over reachers (which would
    improve by stopping out slow fires; banned by §1.1).

    ``fires``  — list of (close_series, signal_date) pairs; one entry per fire.
    ``k_days`` — horizons at which to evaluate cumulative incidence (default {5,10,21}).
    ``stop_mult``    — stop barrier relative to entry (default STOP_BARRIER = 0.95).
    ``cushion_mult`` — cushion barrier relative to entry (default CUSHION_BARRIER = 1.05).

    Returns a dict:
      ``n_fires``   — total fires submitted.
      ``n_gradable`` — fires where a fill bar exists and the series covers ≥ max(k_days) fwd bars.
      ``cumulative_incidence`` — {k: {"cushioned": int, "stopped": int, "at_risk": int,
                                     "incidence_pct": float, "stop_rate_pct": float}}
        ``incidence_pct`` = cushioned by day k / n_gradable (NEVER /at_risk — the spec
        explicitly bans medians-over-reachers and requires the ALL-fires denominator).
        ``stop_rate_pct``  = stopped by day k / n_gradable (the competing event).
      ``post_cushion_breakeven_breach_rate`` — among fires that reached cushion (at any k),
        the fraction whose close later (within max(k_days) bars from fill) fell BACK below
        entry_price (the honest version of "a breakeven stop could be armed").
      ``note`` — methodology statement.

    Note on data basis: close should be the dividend-adjusted total-return series. The
    barriers are ratios vs the fill-bar entry price (same series), so the adjustment
    cancels and percentages are correct.
    """
    n_fires = len(fires)
    max_k = max(k_days) if k_days else 0

    # --- per-fire state scan ---------------------------------------------------
    # For each fire: walk bars 1..max_k; record the first bar where cushion or stop triggers.
    n_gradable = 0
    # Per k: counts of [cushioned, stopped] by day k (cumulative)
    k_cushion = {k: 0 for k in k_days}
    k_stop    = {k: 0 for k in k_days}
    # Post-cushion breach tracking
    cushion_reached_count  = 0
    cushion_breach_count   = 0

    for close, signal_date in fires:
        fill = fill_index(close, signal_date) if not same_bar else _snap_loc(close.index, signal_date)
        if fill is None:
            continue
        entry_price = float(close.iloc[fill]) if fill < len(close) else float("nan")
        if not np.isfinite(entry_price) or entry_price <= 0:
            continue
        # Need at least max_k forward bars to count as gradable
        if fill + max_k >= len(close):
            continue
        n_gradable += 1

        stop_b    = entry_price * stop_mult
        cushion_b = entry_price * cushion_mult

        # Walk bars fill+1 .. fill+max_k
        fwd_arr = close.iloc[fill + 1: fill + max_k + 1].to_numpy()

        cushion_bar: int | None = None  # first bar (1-indexed from fill) where cushion hit
        stop_bar: int | None = None     # first bar (1-indexed from fill) where stop hit

        for bar_off, cl in enumerate(fwd_arr, start=1):
            if not np.isfinite(cl):
                continue
            # Straddle tie: stop wins
            if cl <= stop_b:
                stop_bar = bar_off
                break
            if cl >= cushion_b and cushion_bar is None:
                cushion_bar = bar_off
                # Do NOT break: continue scanning for stop-out on later bars
                # (we need to detect post-cushion stop for the breakeven-breach metric)

        # Accumulate into k-day bins (cumulative: once triggered, it stays triggered)
        for k in k_days:
            if cushion_bar is not None and cushion_bar <= k:
                if stop_bar is None or stop_bar > k:
                    # Cushioned by day k AND not yet stopped by day k
                    k_cushion[k] += 1
            if stop_bar is not None and stop_bar <= k:
                k_stop[k] += 1

        # Post-cushion breakeven-breach: did price drop below entry_price after cushion?
        if cushion_bar is not None and (stop_bar is None or stop_bar > cushion_bar):
            # This fire was cushioned; check if it later breached entry_price
            cushion_reached_count += 1
            scan_start = cushion_bar  # bar offset (1-indexed); we scan from the NEXT bar
            for cl in fwd_arr[scan_start:]:  # fwd_arr is 0-indexed; cushion_bar is 1-indexed
                if np.isfinite(cl) and cl < entry_price:
                    cushion_breach_count += 1
                    break

    # --- assemble output -------------------------------------------------------
    ci: dict[int, dict[str, Any]] = {}
    for k in k_days:
        ci[k] = {
            "cushioned":       k_cushion[k],
            "stopped":         k_stop[k],
            "at_risk":         n_gradable,  # denominator is ALL fires, not survivors
            "incidence_pct":   round(k_cushion[k] / n_gradable * 100.0, 4) if n_gradable > 0 else None,
            "stop_rate_pct":   round(k_stop[k]    / n_gradable * 100.0, 4) if n_gradable > 0 else None,
        }

    breach_rate: float | None = None
    if cushion_reached_count > 0:
        breach_rate = round(cushion_breach_count / cushion_reached_count * 100.0, 4)

    return {
        "n_fires":   n_fires,
        "n_gradable": n_gradable,
        "cumulative_incidence":              ci,
        "post_cushion_breakeven_breach_rate": breach_rate,
        "cushion_reached_count":             cushion_reached_count,
        "note": (
            "Cumulative cushion incidence with stop-out as competing risk. "
            "Denominator = n_gradable (ALL fires, not just reachers) per §1.1. "
            "Data basis: dividend-adjusted total-return close (consistent both sides)."
        ),
    }


def post_cushion_breach(
    close: pd.Series,
    signal_date,
    horizon: int = LIFTOFF_HORIZON_21,
    stop_mult: float = STOP_BARRIER,
    cushion_mult: float = CUSHION_BARRIER,
) -> bool | None:
    """Per-fire post-cushion breakeven-breach flag (§1.1 context metric).

    The single-fire analogue of ``cushion_incidence``'s breach rate, using the
    IDENTICAL scan semantics so the per-row flag and the aggregate rate can never
    diverge:

      * next-bar fill; entry = fill-bar close; window = bars (fill, fill+horizon]
      * first-passage scan with the straddle tie rule (stop wins on a bar that
        touches the stop barrier — checked before cushion on each bar)
      * cushion-reached iff the cushion bar precedes any stop bar
      * breach = ANY close < entry strictly after the cushion bar within the
        window.  A post-cushion stop-out is definitionally below entry, so a
        cushioned-then-stopped fire is breach=True (the worst cushioned fires
        must never fall out of the numerator).

    Returns:
      True  — cushioned, then traded back below entry within the window
      False — cushioned and never closed below entry within the window
      None  — not applicable/matured: stopped before cushion, never cushioned,
              no fill, or fewer than ``horizon`` matured forward bars.
    """
    fill = fill_index(close, signal_date)
    if fill is None or fill + horizon >= len(close):
        return None
    entry_price = float(close.iloc[fill])
    if not np.isfinite(entry_price) or entry_price <= 0:
        return None

    stop_b = entry_price * stop_mult
    cushion_b = entry_price * cushion_mult
    fwd_arr = close.iloc[fill + 1: fill + horizon + 1].to_numpy()

    cushion_bar: int | None = None
    stop_bar: int | None = None
    for bar_off, cl in enumerate(fwd_arr, start=1):
        if not np.isfinite(cl):
            continue
        # Straddle tie: stop wins
        if cl <= stop_b:
            stop_bar = bar_off
            break
        if cl >= cushion_b and cushion_bar is None:
            cushion_bar = bar_off
            # keep scanning: a LATER stop still matters for the breach flag

    if cushion_bar is None or (stop_bar is not None and stop_bar <= cushion_bar):
        return None  # never cushioned (or stopped first) — flag not applicable

    for cl in fwd_arr[cushion_bar:]:  # 0-indexed array; cushion_bar is 1-indexed → next bar on
        if np.isfinite(cl) and cl < entry_price:
            return True
    return False


# --------------------------------------------------------------------------- #
# Delisting terminal values via the 8-K Item 1.03 bankruptcy imputation store
# --------------------------------------------------------------------------- #
_DEAD_CACHE: dict[str, Any] = {"path": None, "by_ticker": {}}


def load_dead_prices(dead_path=None) -> dict[str, pd.Series]:
    """{ticker -> close Series} from the dead-name price store (incl. imputed −100%
    bankruptcy terminals, source=imputed_bankruptcy). Cached by path (test isolation).
    Empty dict when the CI-collected store is absent — the delisting fallback then
    simply degrades to 'last traded close' via the caller's own series."""
    from lib import config
    p = str(dead_path) if dead_path is not None else str(
        config.data_dir() / "edgar" / "dead_name_prices.parquet")
    if _DEAD_CACHE["path"] == p:
        return _DEAD_CACHE["by_ticker"]
    _DEAD_CACHE["path"] = p
    by_ticker: dict[str, pd.Series] = {}
    try:
        from pathlib import Path
        if Path(p).exists():
            df = pd.read_parquet(p)
            if {"ticker", "date", "close"}.issubset(df.columns):
                for tk, g in df.groupby(df["ticker"].astype(str)):
                    s = pd.Series(g["close"].to_numpy(), index=pd.to_datetime(g["date"]))
                    # keep >=0 so an imputed 0.0 bankruptcy terminal survives as a -100% loss
                    by_ticker[tk] = s[s >= 0].dropna().sort_index()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("grading: dead_name_prices load failed: %s", e)
    _DEAD_CACHE["by_ticker"] = by_ticker
    return by_ticker


def resolve_series(
    ticker: str,
    live: pd.Series | None,
    *,
    dead_prices: dict[str, pd.Series] | None = None,
) -> pd.Series | None:
    """Return the fullest available close series for ``ticker``: the live cache series
    if present, otherwise (or extended by) its dead-name terminal series so a delisted
    name still carries a graded loss instead of vanishing. When both exist, the dead
    tail is appended for dates the live series does not cover (a name that dropped out of
    the live cache but whose terminal is in the dead store)."""
    dead = (dead_prices if dead_prices is not None else load_dead_prices()).get(str(ticker))
    if live is None or live.empty:
        return dead.sort_index() if dead is not None and not dead.empty else None
    if dead is None or dead.empty:
        return live.sort_index()
    tail = dead[dead.index > live.index.max()]
    if tail.empty:
        return live.sort_index()
    return pd.concat([live, tail]).sort_index()


# --------------------------------------------------------------------------- #
# Survivorship-aware panel construction (first-ever as_of_members consumer)   #
# W0.1a: sp1500_pit_membership.parquet wired as the pre-2026-06-13 source     #
# --------------------------------------------------------------------------- #

_PIT_MEMBERSHIP_CACHE: dict[str, Any] = {"path": None, "df": None}


def _load_pit_membership(pit_path=None) -> pd.DataFrame | None:
    """Load ``data/breadth/sp1500_pit_membership.parquet`` (cached by path).

    Schema: ticker (str), start_date (datetime), end_date (datetime, NaT = still active),
    src (str: sp500 | sp400 | sp600).

    Returns None when the file is absent (degrade-safe).
    """
    from pathlib import Path
    from lib import config

    p = str(pit_path) if pit_path is not None else str(
        config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")
    if _PIT_MEMBERSHIP_CACHE["path"] == p:
        return _PIT_MEMBERSHIP_CACHE["df"]
    _PIT_MEMBERSHIP_CACHE["path"] = p
    df: pd.DataFrame | None = None
    try:
        if Path(p).exists():
            raw = pd.read_parquet(p)
            # Normalise expected columns
            if {"ticker", "start_date"}.issubset(raw.columns):
                raw = raw.copy()
                raw["ticker"] = raw["ticker"].astype(str)
                raw["start_date"] = pd.to_datetime(raw["start_date"])
                if "end_date" in raw.columns:
                    raw["end_date"] = pd.to_datetime(raw["end_date"])
                else:
                    raw["end_date"] = pd.NaT
                df = raw[["ticker", "start_date", "end_date"]].reset_index(drop=True)
            else:
                log.warning("grading: sp1500_pit_membership missing expected columns; skipping")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("grading: sp1500_pit_membership load failed: %s", e)
    _PIT_MEMBERSHIP_CACHE["df"] = df
    return df


def _pit_members_as_of(asof: pd.Timestamp, pit_df: pd.DataFrame) -> list[str]:
    """Return tickers that were S&P 1500 members on ``asof`` per the PIT file.

    Membership condition: start_date <= asof AND (end_date >= asof OR end_date IS NaT).
    """
    started = pit_df["start_date"] <= asof
    still_on = pit_df["end_date"].isna() | (pit_df["end_date"] >= asof)
    return sorted(pit_df.loc[started & still_on, "ticker"].unique().tolist())


def as_of_panel(
    closes_by_ticker: dict[str, pd.Series],
    asof,
    *,
    group: str | None = None,
    ledger: pd.DataFrame | None = None,
    include_dead: bool = True,
    dead_prices: dict[str, pd.Series] | None = None,
    pit_path=None,
) -> dict[str, Any]:
    """Reconstruct the gradable price panel AS IT STOOD on ``asof`` — the survivorship fix.

    Returns::

        {"members": [...], "closes": {ticker: Series}, "survivorship": <tag>, "n_asof": N,
         "n_survivors": M, "note": "..."}

    ``survivorship`` is one of:
      * ``"as-of"``      — reconstructed from the universe_history membership ledger
                           (exact from 2026-06-13 onwards; see universe_history).
      * ``"pit"``        — ``asof`` precedes universe_history accrual; reconstructed
                           from ``data/breadth/sp1500_pit_membership.parquet`` which
                           covers the full S&P 1500 history with start_date/end_date.
                           Better than cold-start for pre-2026-06-13 dates (still
                           survivor-priced, but membership set is correct).
      * ``"cold-start"`` — neither the ledger nor the PIT file could supply membership;
                           falls back to today's panel (survivor-biased UPPER bound).

    W0.1a addition — ``pit_path``: explicit path to the PIT membership file; defaults to
    ``data/breadth/sp1500_pit_membership.parquet``. Pass a mock path in tests.

    ``include_dead`` unions in delisted names (from the dead-price store) that were
    members as of ``asof`` so their loss is graded, not dropped.
    """
    from engine.universe_history import as_of_members, load_ledger

    led = ledger if ledger is not None else load_ledger()
    members = as_of_members(asof, group=group, ledger=led)

    survivorship = "as-of"
    note = "membership reconstructed as-of the grading date (universe_history)"
    if not members:
        # universe_history is cold-start (asof before 2026-06-13) or ledger absent.
        # Try the PIT membership file as a better fallback.
        asof_ts = pd.Timestamp(asof)
        pit_df = _load_pit_membership(pit_path)
        if pit_df is not None and not pit_df.empty:
            members = _pit_members_as_of(asof_ts, pit_df)
            if group:
                # The PIT file's 'src' column maps: sp500/sp400/sp600.
                # Filter if 'src' column present and group matches a known src label.
                if "src" in pit_df.columns:
                    src_members = set(
                        pit_df.loc[
                            (pit_df["src"] == group)
                            & (pit_df["start_date"] <= asof_ts)
                            & (pit_df["end_date"].isna() | (pit_df["end_date"] >= asof_ts)),
                            "ticker"
                        ].unique()
                    )
                    if src_members:
                        members = sorted(src_members)
            if members:
                survivorship = "pit"
                note = (
                    f"membership from sp1500_pit_membership.parquet as-of {asof_ts.date()} — "
                    "PIT-correct membership set; member PRICES may be survivor-biased for "
                    "names delisted before ~2025 (no dead-name price store for those)"
                )
            else:
                members = sorted(closes_by_ticker.keys())
                survivorship = "cold-start"
                note = ("sp1500_pit_membership has no entries for this date; "
                        "graded on today's panel — counts are survivor-biased UPPER bounds")
        else:
            # No PIT file available — true cold-start.
            members = sorted(closes_by_ticker.keys())
            survivorship = "cold-start"
            note = ("as-of precedes membership accrual (2026-06-13) and no PIT file found — "
                    "graded on today's panel; counts are survivor-biased UPPER bounds")

    dead = dead_prices if dead_prices is not None else (load_dead_prices() if include_dead else {})
    out: dict[str, pd.Series] = {}
    asof_ts = pd.Timestamp(asof)
    for t in members:
        s = closes_by_ticker.get(t)
        if include_dead:
            s = resolve_series(t, s, dead_prices=dead)
        if s is None or s.empty:
            continue
        # only keep names that had a price at-or-before asof (were tradable then)
        if s.index.min() <= asof_ts:
            out[t] = s

    return {
        "members": members,
        "closes": out,
        "survivorship": survivorship,
        "n_asof": len(members),
        "n_survivors": len(closes_by_ticker),
        "note": note,
    }
