"""Expect-Drift Feature Panel — LT-2a.

Pre-registration: research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md (§1-§2, LOCKED).
Program: LT External Foundation; see research/long_hold/LT_EXTERNAL_FOUNDATION_ADJUDICATION.md.

Builds the 7 at-entry features (ED-1 .. ED-7) for every fire in
data/research/long_hold_labels.parquet.  Output is OUTCOME-BLIND: no label,
total_return, or outcome column is written to the panel.

Output:
  data/research/expect_drift_panel.parquet
  data/research/expect_drift_panel_manifest.json

Synapse: config/synapse.yml (tier: display, horizon_role: hold_thesis,
  fdr_family: long_hold).

Population constraint: ALL fires from long_hold_labels.parquet (features are
at-entry and outcome-blind; per AMENDMENT_A2_G1_RETEST.md §4 the join to 2024+
outcomes is forbidden until the A2 freeze, but computing features for those fire
dates is explicitly permitted).

Firewall: horizon_role=hold_thesis.  NEVER feeds board ordering / alert triage /
top-setups / push floor.  Enforced by check_synapse_reads.py.

Reference event E(f) definition (§1):
  Latest 8-K item 2.02 with filing_date <= fire_date - 1 trading session
  AND within 120 calendar days of fire_date.  No qualifying event =>
  event-anchored features (ED-3/4/5/7) are missing (NaN).

SUE construction (§1):
  d_q = eps_q - eps_{q-4} (calendar-matched ±50d).
  SUE_q = d_q / σ(last 8 seasonal diffs, min 4).
  Visibility: only rows with asof_date <= fire_date.
  Matches engine/sue.py construction evaluated PIT per-fire.

Features (§2):
  ED-1  sue_latest          cont  Most recent SUE_q at fire_date
  ED-2  sue_streak          int   Consecutive quarters with d_q > 0 (cap 8)
  ED-3  pead_drift          cont  Cumulative stock-minus-benchmark over E(f)+1..min(E(f)+20,fire_date-1)
  ED-4  bad_news_absorption bin   d_q<0 at E(f) + no close below 63d-pre-min in 10 post sessions
                                  + stock-minus-benchmark over E(f)+1..E(f)+5 >= 0
  ED-5  good_news_hold      bin   d_q>0 + close(E(f)+1)/close(E(f))-1 >= +2% + close(E(f)+10)>=close(E(f)+1)
  ED-6  sue_accel           cont  SUE_latest - SUE_prev
  ED-7  confirmed_absorption bin  (ED-4 OR ED-5) AND ED-3 > 0

Usage:
    python scripts/research/build_expect_drift_panel.py
    python scripts/research/build_expect_drift_panel.py --dry-run
    python scripts/research/build_expect_drift_panel.py --limit 500
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_LABELS_PATH = _DATA / "research" / "long_hold_labels.parquet"
_LABELS_MANIFEST_PATH = _DATA / "research" / "long_hold_labels_manifest.json"
_EARNINGS_8K_PATH = _DATA / "edgar" / "earnings_8k_dates.parquet"
_EPS_PATH = _DATA / "edgar" / "eps_quarterly.parquet"

_OUT_PARQUET = _DATA / "research" / "expect_drift_panel.parquet"
_OUT_MANIFEST = _DATA / "research" / "expect_drift_panel_manifest.json"

# Price stores (same resolution as long_hold_label_panel.py — imports below)
_YAHOO_DIR = _DATA / "yahoo"
_STOCKS_DIR = _DATA / "stocks"
_MASSIVE_DIR_LOCAL = _DATA / "massive_stock_day"
_MASSIVE_DIR_MAC = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
_DEAD_NAME_PRICES_PATH = _DATA / "edgar" / "dead_name_prices.parquet"
_SECTOR_OHLCV_DIR = _DATA / "baskets" / "ohlcv"

# ---------------------------------------------------------------------------
# Constants (§1)
# ---------------------------------------------------------------------------
_EVENT_WINDOW_DAYS = 120    # maximum calendar days before fire for E(f)
_TOL_YEAR_AGO_DAYS = 50     # calendar tolerance for year-ago quarter match (SUE)
_SUE_MIN_DIFFS = 4          # minimum seasonal diffs to compute SUE
_SUE_VOL_WINDOW = 8         # trailing diffs used for σ
_PEAD_MIN_SESSIONS = 5      # minimum elapsed sessions for pead_drift
_PEAD_MAX_SESSIONS = 20     # maximum sessions for pead_drift window end
_BNA_POST_SESSIONS = 10     # bad_news_absorption: post-event sessions to scan
_BNA_PRE_SESSIONS = 63      # bad_news_absorption: pre-event sessions for min-close
_BNA_MOMENTUM = 5           # bad_news_absorption: sessions for stock-vs-bm return
_GNH_REACT_MIN = 0.02       # good_news_hold: minimum next-session reaction
_GNH_HOLD_SESSIONS = 10     # good_news_hold: sessions to confirm close >= E(f)+1

# ---------------------------------------------------------------------------
# Import store-resolution helpers from label panel (don't copy — import)
# ---------------------------------------------------------------------------
from scripts.research.long_hold_label_panel import (  # noqa: E402
    _find_massive_dir,
    _load_dead_name_closes,
    _load_massive_closes,
    _load_stocks_closes,
    _load_yahoo_closes,
    _build_sector_closes,
    _build_ticker_sector_map,
    resolve_price,
)


# ---------------------------------------------------------------------------
# SUE helpers (per engine/sue.py construction, evaluated PIT per-fire)
# ---------------------------------------------------------------------------

def _seasonal_diffs_pit(
    period_ends: np.ndarray,
    eps_vals: np.ndarray,
    tol_days: int = _TOL_YEAR_AGO_DAYS,
) -> list[tuple[pd.Timestamp, float]]:
    """Compute (period_end, d_q = eps_q - eps_{q-4}) pairs for all quarters
    that have a year-ago match within ±tol_days calendar days.

    Returns list sorted ascending by period_end.
    Matches engine/sue.py _seasonal_diffs exactly.
    """
    out: list[tuple[pd.Timestamp, float]] = []
    pe = period_ends.astype("datetime64[D]")
    for i in range(len(pe)):
        target = pe[i] - np.timedelta64(365, "D")
        best_j, best_gap = -1, tol_days + 1
        for j in range(i):
            gap = abs(int((pe[j] - target) / np.timedelta64(1, "D")))
            if gap <= best_gap:
                best_gap, best_j = gap, j
        if best_j >= 0 and best_gap <= tol_days:
            out.append((pd.Timestamp(pe[i]), float(eps_vals[i] - eps_vals[best_j])))
    return out


def _sue_for_ticker_pit(
    ticker_eps: pd.DataFrame,
    fire_date: pd.Timestamp,
) -> dict[str, Any]:
    """Compute PIT-gated SUE features for a single ticker at fire_date.

    Returns dict with keys:
      sue_latest, sue_prev, sue_streak, sue_accel, sue_latest_period_end
    All None if insufficient data.
    """
    result: dict[str, Any] = {
        "sue_latest": None,
        "sue_prev": None,
        "sue_streak": None,
        "sue_accel": None,
        "sue_latest_period_end": None,
    }

    # PIT visibility gate: only rows with asof_date <= fire_date
    visible = ticker_eps[ticker_eps["asof_date"] <= fire_date].sort_values("period_end")
    if len(visible) < _SUE_MIN_DIFFS + 2:
        return result

    diffs = _seasonal_diffs_pit(
        visible["period_end"].values,
        visible["eps_q"].values,
    )
    if len(diffs) < _SUE_MIN_DIFFS:
        return result

    # σ over up to _SUE_VOL_WINDOW trailing diffs
    recent_diffs = [d for _pe, d in diffs[-_SUE_VOL_WINDOW:]]
    sd = float(pd.Series(recent_diffs).std())
    if not sd or np.isnan(sd) or sd == 0:
        return result

    last_pe, last_d = diffs[-1]
    result["sue_latest"] = float(last_d / sd)
    result["sue_latest_period_end"] = last_pe

    # sue_streak: consecutive quarters with d_q > 0 ending at the most recent visible quarter
    streak = 0
    for _pe, d in reversed(diffs):
        if d > 0:
            streak += 1
        else:
            break
    result["sue_streak"] = min(int(streak), 8)

    # sue_prev and sue_accel: second-most-recent visible quarter
    if len(diffs) >= 2:
        prev_d = diffs[-2][1]
        result["sue_prev"] = float(prev_d / sd)
        result["sue_accel"] = float(result["sue_latest"] - result["sue_prev"])

    return result


# ---------------------------------------------------------------------------
# Reference event E(f) selection (§1)
# ---------------------------------------------------------------------------

def _select_event_ef(
    ticker: str,
    fire_date: pd.Timestamp,
    earnings_by_ticker: dict[str, pd.DataFrame],
) -> pd.Timestamp | None:
    """Select reference event E(f): the latest 8-K 2.02 filing with
    filing_date <= fire_date - 1 trading session (business day)
    AND within 120 calendar days of fire_date.

    Returns filing_date (as Timestamp) or None if no qualifying event.
    All rows in earnings_by_ticker are already pre-filtered to item 2.02.
    """
    events = earnings_by_ticker.get(ticker)
    if events is None or events.empty:
        return None

    # fire_date - 1 business day cutoff
    cutoff_high = fire_date - pd.tseries.offsets.BDay(1)
    # cutoff_high is a Timestamp; normalize to midnight for date comparison
    cutoff_high = cutoff_high.normalize()
    cutoff_low = (fire_date - pd.Timedelta(days=_EVENT_WINDOW_DAYS)).normalize()

    # Filter: filing_date in [cutoff_low, cutoff_high]
    mask = (events["filing_date"] >= cutoff_low) & (events["filing_date"] <= cutoff_high)
    candidates = events[mask]
    if candidates.empty:
        return None

    # Return latest filing_date
    return candidates["filing_date"].max()


# ---------------------------------------------------------------------------
# PEAD drift (ED-3)
# ---------------------------------------------------------------------------

def _pead_drift_feature(
    close: pd.Series,
    sector_close: pd.Series | None,
    event_date: pd.Timestamp,
    fire_date: pd.Timestamp,
) -> float | None:
    """Cumulative stock-minus-benchmark return over sessions E(f)+1 to
    min(E(f)+20, fire_date-1).  Requires >= 5 elapsed sessions.

    Returns None if insufficient sessions.
    """
    if close is None or close.empty:
        return None

    # Find first bar after event_date
    idx = close.index
    start_pos = int(np.searchsorted(idx.values, np.datetime64(event_date), side="right"))
    if start_pos >= len(idx):
        return None

    # Find the bar at fire_date - 1 (exclusive upper bound: up to last bar < fire_date)
    end_pos_exclusive = int(np.searchsorted(idx.values, np.datetime64(fire_date), side="left"))
    # We want bars from start_pos to min(start_pos + 20, end_pos_exclusive)
    end_pos = min(start_pos + _PEAD_MAX_SESSIONS, end_pos_exclusive)

    n_sessions = end_pos - start_pos
    if n_sessions < _PEAD_MIN_SESSIONS:
        return None

    window = close.iloc[start_pos:end_pos]
    if len(window) < _PEAD_MIN_SESSIONS:
        return None

    # Stock return over the window
    stock_ret = float(window.iloc[-1]) / float(window.iloc[0]) - 1.0

    # Benchmark return over the same date range
    if sector_close is not None and not sector_close.empty:
        bm_idx = sector_close.index
        bm_start = int(np.searchsorted(bm_idx.values, np.datetime64(idx[start_pos]), side="right")) - 1
        bm_end = int(np.searchsorted(bm_idx.values, np.datetime64(idx[end_pos - 1]), side="right")) - 1
        if bm_start >= 0 and bm_end >= 0 and bm_end > bm_start:
            bm_start_val = float(sector_close.iloc[bm_start])
            bm_end_val = float(sector_close.iloc[bm_end])
            if bm_start_val > 0:
                bm_ret = bm_end_val / bm_start_val - 1.0
                return float(stock_ret - bm_ret)

    # No benchmark available: return raw stock return (will be noted in coverage)
    return float(stock_ret)


# ---------------------------------------------------------------------------
# Bad-news absorption (ED-4)
# ---------------------------------------------------------------------------

def _bad_news_absorption_feature(
    close: pd.Series,
    sector_close: pd.Series | None,
    event_date: pd.Timestamp,
    d_q_at_event: float | None,
    fire_date: pd.Timestamp | None = None,
) -> bool | None:
    """Binary: most recent visible d_q < 0 at E(f) AND no close in the 10 sessions
    after E(f) below the minimum close of the 63 sessions before E(f) AND
    stock-minus-benchmark return over E(f)+1..E(f)+5 >= 0.

    PIT constraint: post-event windows (E(f)+10 and E(f)+5) are capped at
    fire_date-1 (exclusive) so no post-entry price bar is read.  fire_date is
    required for PIT correctness; if omitted the window is uncapped (legacy
    behaviour retained for unit tests that don't supply it, but production
    callers must always pass fire_date).

    Returns True/False or None if insufficient data.
    """
    if close is None or close.empty:
        return None
    if d_q_at_event is None:
        return None

    # Condition 1: d_q < 0
    if d_q_at_event >= 0:
        return False

    idx = close.index
    event_pos = int(np.searchsorted(idx.values, np.datetime64(event_date), side="right")) - 1
    if event_pos < 0:
        # event_date before price history starts
        return None

    # PIT cap: the last bar we may use is strictly before fire_date
    if fire_date is not None:
        # exclusive upper bound: bars with index < fire_date
        pit_end = int(np.searchsorted(idx.values, np.datetime64(fire_date), side="left"))
    else:
        pit_end = len(idx)

    # 63 sessions before E(f) (inclusive of event_pos if it exists in index)
    pre_start = max(0, event_pos - _BNA_PRE_SESSIONS + 1)
    pre_window = close.iloc[pre_start:event_pos + 1]
    if len(pre_window) < 5:  # too few pre-event bars
        return None
    pre_min = float(pre_window.min())

    # 10 sessions after E(f), capped at fire_date-1
    post_start = event_pos + 1
    post_end = min(post_start + _BNA_POST_SESSIONS, pit_end)
    if post_end - post_start < 1:
        return None
    post_window = close.iloc[post_start:post_end]

    # Condition 2: no close below pre_min in post window
    if float(post_window.min()) < pre_min:
        return False

    # Condition 3: stock-minus-benchmark return over E(f)+1..E(f)+5 >= 0,
    # capped at fire_date-1
    momentum_end = min(post_start + _BNA_MOMENTUM, pit_end)
    if momentum_end - post_start < 1:
        return None
    stock_momentum_window = close.iloc[post_start:momentum_end]
    if len(stock_momentum_window) < 1:
        return None

    stock_mom_ret = float(stock_momentum_window.iloc[-1]) / float(close.iloc[event_pos]) - 1.0

    if sector_close is not None and not sector_close.empty:
        bm_idx = sector_close.index
        bm_s = int(np.searchsorted(bm_idx.values, np.datetime64(idx[event_pos]), side="right")) - 1
        bm_e = int(np.searchsorted(bm_idx.values, np.datetime64(idx[momentum_end - 1]), side="right"))
        if bm_s >= 0 and bm_e - 1 >= bm_s and float(sector_close.iloc[bm_s]) > 0:
            bm_mom_ret = float(sector_close.iloc[bm_e - 1]) / float(sector_close.iloc[bm_s]) - 1.0
            excess_mom = stock_mom_ret - bm_mom_ret
        else:
            excess_mom = stock_mom_ret
    else:
        excess_mom = stock_mom_ret

    return bool(excess_mom >= 0)


# ---------------------------------------------------------------------------
# Good-news hold (ED-5)
# ---------------------------------------------------------------------------

def _good_news_hold_feature(
    close: pd.Series,
    event_date: pd.Timestamp,
    d_q_at_event: float | None,
    fire_date: pd.Timestamp | None = None,
) -> bool | None:
    """Binary: most recent visible d_q > 0 AND close(E(f)+1)/close(E(f)) - 1 >= +2%
    AND close(E(f)+10) >= close(E(f)+1).

    PIT constraint: the E(f)+10 session is capped at fire_date-1 (exclusive) so
    no post-entry price bar is read.  When the cap prevents reaching E(f)+10, the
    feature is set to None (insufficient data).  fire_date is required for PIT
    correctness; if omitted the window is uncapped (legacy behaviour retained for
    unit tests that don't supply it, but production callers must always pass
    fire_date).

    Returns True/False or None if insufficient data.
    """
    if close is None or close.empty:
        return None
    if d_q_at_event is None:
        return None

    # Condition 1: d_q > 0
    if d_q_at_event <= 0:
        return False

    idx = close.index

    # PIT cap: the last bar we may use is strictly before fire_date
    if fire_date is not None:
        pit_end = int(np.searchsorted(idx.values, np.datetime64(fire_date), side="left"))
    else:
        pit_end = len(idx)

    event_pos = int(np.searchsorted(idx.values, np.datetime64(event_date), side="right")) - 1
    if event_pos < 0:
        return None

    # E(f)+1 session
    pos_plus1 = event_pos + 1
    if pos_plus1 >= pit_end:
        return None

    # E(f)+10 session — must be within PIT window
    pos_plus10 = event_pos + _GNH_HOLD_SESSIONS
    if pos_plus10 >= pit_end:
        # E(f)+10 extends past fire_date — insufficient PIT data
        return None

    close_ef = float(close.iloc[event_pos])
    close_ef1 = float(close.iloc[pos_plus1])
    close_ef10 = float(close.iloc[pos_plus10])

    if close_ef <= 0:
        return None

    # Condition 2: initial reaction >= +2%
    reaction = (close_ef1 / close_ef) - 1.0
    if reaction < _GNH_REACT_MIN:
        return False

    # Condition 3: hold — close at E(f)+10 >= close at E(f)+1
    return bool(close_ef10 >= close_ef1)


# ---------------------------------------------------------------------------
# Get d_q at event: the most recent visible d_q at E(f) (prereg ED-4/ED-5)
# ---------------------------------------------------------------------------

def _dq_at_event(
    ticker_eps: pd.DataFrame,
    event_date: pd.Timestamp,
) -> float | None:
    """Return d_q for the most recent quarter visible at E(f).

    d_q = eps_q - eps_{q-4}. Uses the same seasonal-diff construction as SUE.
    Anchored at E(f), not fire_date (ED-4/ED-5: "Most recent visible d_q at
    E(f)") — a quarter announced between E(f) and the fire must not swap in.
    """
    visible = ticker_eps[ticker_eps["asof_date"] <= event_date].sort_values("period_end")
    if len(visible) < _SUE_MIN_DIFFS + 1:
        return None

    diffs = _seasonal_diffs_pit(visible["period_end"].values, visible["eps_q"].values)
    if not diffs:
        return None

    return float(diffs[-1][1])


# ---------------------------------------------------------------------------
# Main per-fire feature computation
# ---------------------------------------------------------------------------

def _compute_features_for_fire(
    ticker: str,
    fire_date: pd.Timestamp,
    close: pd.Series | None,
    sector_close: pd.Series | None,
    ticker_eps: pd.DataFrame | None,
    event_date: pd.Timestamp | None,
) -> dict[str, Any]:
    """Compute all 7 ED features for a single fire.

    All inputs are pre-filtered for the ticker.
    event_date = E(f) or None (no qualifying event).
    """
    rec: dict[str, Any] = {
        "sue_latest": None,
        "sue_streak": None,
        "pead_drift": None,
        "bad_news_absorption": None,
        "good_news_hold": None,
        "sue_accel": None,
        "confirmed_absorption": None,
        # Coverage/diagnostic
        "event_ef_date": None,
        "has_event": False,
        "has_sue": False,
        "sue_missing_reason": None,
    }

    # --- SUE features (ED-1, ED-2, ED-6) ---
    if ticker_eps is not None and len(ticker_eps) > 0:
        sue_result = _sue_for_ticker_pit(ticker_eps, fire_date)
        if sue_result["sue_latest"] is not None:
            rec["sue_latest"] = sue_result["sue_latest"]
            rec["sue_streak"] = sue_result["sue_streak"]
            rec["sue_accel"] = sue_result["sue_accel"]
            rec["has_sue"] = True
        else:
            rec["sue_missing_reason"] = "insufficient_diffs"
    else:
        rec["sue_missing_reason"] = "no_eps_data"

    # --- Event-anchored features (ED-3, ED-4, ED-5, ED-7) ---
    if event_date is not None:
        rec["event_ef_date"] = event_date
        rec["has_event"] = True

        # d_q at E(f) for bad_news_absorption / good_news_hold
        if ticker_eps is not None and len(ticker_eps) > 0:
            dq = _dq_at_event(ticker_eps, event_date)
        else:
            dq = None

        # ED-3: pead_drift
        pead = _pead_drift_feature(close, sector_close, event_date, fire_date)
        rec["pead_drift"] = pead

        # ED-4: bad_news_absorption (PIT-capped at fire_date)
        bna = _bad_news_absorption_feature(close, sector_close, event_date, dq, fire_date)
        rec["bad_news_absorption"] = bna

        # ED-5: good_news_hold (PIT-capped at fire_date)
        gnh = _good_news_hold_feature(close, event_date, dq, fire_date)
        rec["good_news_hold"] = gnh

        # ED-7: confirmed_absorption = (ED-4 OR ED-5) AND ED-3 > 0
        if pead is not None and (bna is not None or gnh is not None):
            absorbed = bool(bna) if bna is not None else False
            held = bool(gnh) if gnh is not None else False
            rec["confirmed_absorption"] = bool((absorbed or held) and pead > 0)

    return rec


# ---------------------------------------------------------------------------
# Panel builder
# ---------------------------------------------------------------------------

def build_panel(
    labels: pd.DataFrame,
    yahoo_closes: dict[str, pd.Series],
    stocks_closes: dict[str, pd.Series],
    massive_closes: dict[str, pd.Series],
    dead_name_closes: dict[str, pd.Series],
    sector_closes: dict[str, pd.Series],
    ticker_sector_map: dict[str, str],
    eps_by_ticker: dict[str, pd.DataFrame],
    earnings_by_ticker: dict[str, pd.DataFrame],
    *,
    limit: int | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the expect_drift feature panel for all fires.

    NO outcome columns are written — features only.
    """
    if limit is not None:
        labels = labels.head(limit).copy()

    n_total = len(labels)
    log.info("Building expect_drift panel for %d fires...", n_total)

    # SPY fallback for tickers not covered by the sector map (prereg §1 §SPY remedy).
    # Per the pre-registration: 'where a sector benchmark is unavailable, SPY with
    # benchmark="market" stamp'.  Load once from yahoo_closes so the stamp is
    # truthfully backed by a real SPY series when available.
    spy_close: pd.Series | None = yahoo_closes.get("SPY")
    if spy_close is None:
        log.warning(
            "SPY not found in yahoo_closes — event-anchored features for tickers "
            "without a sector map will use raw absolute returns (no benchmark "
            "adjustment). benchmark='market' stamp will still be set but will not "
            "be SPY-relative for those rows."
        )

    rows_out: list[dict[str, Any]] = []
    t0 = time.time()

    for i, row in labels.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["fire_date"])
        # survivorship_biased is inherited from label manifest per prereg §4
        survivorship_biased = bool(row.get("survivorship_biased", True))

        # Resolve price series (same priority as label panel)
        close, _ = resolve_price(
            ticker, yahoo_closes, stocks_closes, massive_closes,
            dead_name_closes=dead_name_closes,
        )

        # Resolve sector benchmark; fall back to SPY for tickers without a sector map.
        # When SPY is used, benchmark is still stamped 'market' per prereg §1.
        sector_key = ticker_sector_map.get(ticker)
        if sector_key:
            sector_close = sector_closes.get(sector_key)
            benchmark = sector_key
        else:
            # No sector map: use SPY as the market benchmark per prereg §1 remedy
            sector_close = spy_close  # may still be None if SPY absent from store
            benchmark = "market"

        # EPS data
        ticker_eps = eps_by_ticker.get(ticker)  # may be None

        # Select E(f)
        event_date = _select_event_ef(ticker, fire_date, earnings_by_ticker)

        # Compute features
        feat = _compute_features_for_fire(
            ticker, fire_date, close, sector_close, ticker_eps, event_date
        )

        # Build output row — NO outcome columns
        out_row: dict[str, Any] = {
            "ticker": ticker,
            "fire_date": fire_date,
            # The 7 registered features
            "sue_latest": feat["sue_latest"],
            "sue_streak": feat["sue_streak"],
            "pead_drift": feat["pead_drift"],
            "bad_news_absorption": feat["bad_news_absorption"],
            "good_news_hold": feat["good_news_hold"],
            "sue_accel": feat["sue_accel"],
            "confirmed_absorption": feat["confirmed_absorption"],
            # Coverage / stamp fields
            "benchmark": benchmark,
            "has_event": feat["has_event"],
            "event_ef_date": feat["event_ef_date"],
            "has_sue": feat["has_sue"],
            "sue_missing_reason": feat["sue_missing_reason"],
            "survivorship_biased": survivorship_biased,
            "coverage_frac": None,      # filled post-loop per cohort
            "horizon_role": "hold_thesis",
            "_display_only": True,
        }
        rows_out.append(out_row)

        if verbose and (i % 10000 == 0):
            elapsed = time.time() - t0
            log.info("Progress: %d/%d fires (%.1fs)", i, n_total, elapsed)

    log.info("Feature loop done: %d rows in %.1fs", len(rows_out), time.time() - t0)

    panel = pd.DataFrame(rows_out)

    # Per-cohort coverage_frac (% of fires with at least one non-null feature)
    panel["_has_any_feature"] = (
        panel["sue_latest"].notna() |
        panel["sue_streak"].notna() |
        panel["pead_drift"].notna() |
        panel["bad_news_absorption"].notna() |
        panel["good_news_hold"].notna() |
        panel["sue_accel"].notna() |
        panel["confirmed_absorption"].notna()
    )
    panel["cohort_year"] = panel["fire_date"].dt.year
    for yr, grp in panel.groupby("cohort_year"):
        n_yr = len(grp)
        n_cov = int(grp["_has_any_feature"].sum())
        panel.loc[grp.index, "coverage_frac"] = float(n_cov / n_yr) if n_yr > 0 else 0.0
    panel = panel.drop(columns=["_has_any_feature", "cohort_year"])

    log.info("Panel built: %d rows", len(panel))
    return panel


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------

def build_manifest(
    panel: pd.DataFrame,
    labels_manifest: dict[str, Any],
    runtime_seconds: float,
    limit: int | None,
) -> dict[str, Any]:
    """Build expect_drift_panel_manifest.json."""
    n_fires = int(len(panel))
    n_tickers = int(panel["ticker"].nunique())

    # Per-feature coverage
    features = [
        "sue_latest", "sue_streak", "pead_drift",
        "bad_news_absorption", "good_news_hold", "sue_accel",
        "confirmed_absorption",
    ]
    per_feature_coverage: dict[str, float] = {}
    for f in features:
        n_nonnull = int(panel[f].notna().sum())
        pct = round(100.0 * n_nonnull / n_fires, 2) if n_fires > 0 else 0.0
        per_feature_coverage[f] = pct

    # Population hash (sorted ticker|fire_date pairs for reproducibility)
    _hash_input = (
        panel[["ticker", "fire_date"]]
        .sort_values(["ticker", "fire_date"])
        .assign(fire_date=lambda d: d["fire_date"].astype(str))
        .apply(lambda r: f"{r['ticker']}|{r['fire_date']}", axis=1)
        .str.cat(sep=",")
    )
    population_hash = hashlib.sha256(_hash_input.encode()).hexdigest()[:16]

    # Survivorship biased stamp from labels manifest
    survivorship_biased = bool(
        labels_manifest.get("survivorship_biased", True)
        if isinstance(labels_manifest, dict) else True
    )
    # Check if any fire is not survivorship biased
    any_unbiased = bool((panel["survivorship_biased"] == False).any())  # noqa: E712
    survivorship_biased_summary = not any_unbiased  # True = all fires are biased

    # Event coverage
    n_with_event = int(panel["has_event"].sum())
    event_coverage_pct = round(100.0 * n_with_event / n_fires, 2) if n_fires > 0 else 0.0

    # SUE coverage
    n_with_sue = int(panel["has_sue"].sum())
    sue_coverage_pct = round(100.0 * n_with_sue / n_fires, 2) if n_fires > 0 else 0.0

    manifest: dict[str, Any] = {
        "artifact": "expect_drift_panel",
        "version": "LT-2a-v1",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(float(runtime_seconds), 1),
        "prereg_reference": "research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md",
        "population": {
            "source": "data/research/long_hold_labels.parquet",
            "n_fires": n_fires,
            "n_tickers": n_tickers,
            "date_range": [
                str(panel["fire_date"].min().date()),
                str(panel["fire_date"].max().date()),
            ],
            "population_hash": population_hash,
            "limit_applied": limit,
        },
        "survivorship_biased": survivorship_biased_summary,
        "survivorship_note": (
            "survivorship_biased per fire is inherited from long_hold_labels.parquet. "
            "Features are at-entry and outcome-blind; the biased flag applies to the "
            "outcome labels (not feature computation), but is carried here to support "
            "study-level filtering."
        ),
        "event_coverage": {
            "n_fires_with_event": int(n_with_event),
            "pct_fires_with_event": float(event_coverage_pct),
            "note": (
                "E(f) = latest 8-K item 2.02 with filing_date <= fire_date - 1 BDay "
                "and within 120 calendar days. Fires without qualifying event have "
                "pead_drift, bad_news_absorption, good_news_hold, confirmed_absorption = NaN."
            ),
        },
        "sue_coverage": {
            "n_fires_with_sue": int(n_with_sue),
            "pct_fires_with_sue": float(sue_coverage_pct),
        },
        "per_feature_coverage_pct": per_feature_coverage,
        "fdr_family": "long_hold",
        "horizon_role": "hold_thesis",
        "tier": "display",
        "_display_only": True,
        "outcome_firewall": (
            "This panel carries ONLY at-entry features (ED-1..ED-7). "
            "No outcome column (label, total_return_*, sector_rel_*, missed_hold) "
            "is present. Per AMENDMENT_A2_G1_RETEST.md §4, the join of these features "
            "to 2024+ outcomes is FORBIDDEN until the A2 analysis script commits."
        ),
        "firewall": (
            "horizon_role=hold_thesis. MUST NOT feed board ordering / alert triage / "
            "top-setups gates / push floor. Enforced by check_synapse_reads.py."
        ),
    }
    return manifest


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def run(
    dry_run: bool = False,
    limit: int | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Build the expect_drift feature panel. Returns the manifest dict."""
    t_start = time.time()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    log.info("=== Expect-Drift Panel Builder LT-2a ===")
    log.info("Pre-registration: research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md")

    # --- Load population (fires from long_hold_labels.parquet) ---
    if not _LABELS_PATH.exists():
        raise RuntimeError(f"Labels parquet not found: {_LABELS_PATH}")
    labels = pd.read_parquet(_LABELS_PATH)
    labels["fire_date"] = pd.to_datetime(labels["fire_date"])
    log.info("Loaded %d fires from %s", len(labels), _LABELS_PATH)

    # Load labels manifest for survivorship_biased stamp propagation
    labels_manifest: dict[str, Any] = {}
    if _LABELS_MANIFEST_PATH.exists():
        try:
            labels_manifest = json.loads(_LABELS_MANIFEST_PATH.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("Labels manifest load fail: %s", exc)

    if dry_run:
        log.info("DRY RUN — skipping feature computation")
        manifest = {
            "dry_run": True,
            "n_fires": int(len(labels)),
            "labels_path": str(_LABELS_PATH),
        }
        print(json.dumps(manifest, indent=2, default=str))
        return manifest

    # --- Load EDGAR earnings 8K dates ---
    log.info("Loading earnings 8K dates from %s...", _EARNINGS_8K_PATH)
    if not _EARNINGS_8K_PATH.exists():
        raise RuntimeError(f"Earnings 8K dates not found: {_EARNINGS_8K_PATH}")

    earnings_8k = pd.read_parquet(_EARNINGS_8K_PATH)
    earnings_8k["filing_date"] = pd.to_datetime(earnings_8k["filing_date"])
    earnings_8k["acceptance_datetime"] = pd.to_datetime(earnings_8k["acceptance_datetime"])
    # All rows in this parquet already have item 2.02 (pre-filtered by collector)
    log.info("Loaded %d 8K records, %d tickers", len(earnings_8k), earnings_8k["ticker"].nunique())

    # Index by ticker for fast lookup
    earnings_by_ticker: dict[str, pd.DataFrame] = {}
    for tic, grp in earnings_8k.groupby("ticker"):
        earnings_by_ticker[str(tic)] = grp.sort_values("filing_date").reset_index(drop=True)

    # --- Load EPS panel ---
    log.info("Loading EPS panel from %s...", _EPS_PATH)
    if not _EPS_PATH.exists():
        raise RuntimeError(f"EPS quarterly panel not found: {_EPS_PATH}")

    eps_panel = pd.read_parquet(_EPS_PATH)
    eps_panel["period_end"] = pd.to_datetime(eps_panel["period_end"])
    eps_panel["asof_date"] = pd.to_datetime(eps_panel["asof_date"])
    log.info("Loaded %d EPS records, %d tickers", len(eps_panel), eps_panel["ticker"].nunique())

    # Index by ticker
    eps_by_ticker: dict[str, pd.DataFrame] = {}
    for tic, grp in eps_panel.groupby("ticker"):
        eps_by_ticker[str(tic)] = grp.sort_values("period_end").reset_index(drop=True)

    # --- Load price stores (same resolution as long_hold_label_panel.py) ---
    log.info("Loading price stores...")
    yahoo_closes = _load_yahoo_closes()

    massive_dir = _find_massive_dir()
    massive_closes: dict[str, pd.Series] = {}
    if massive_dir is not None:
        log.info("Loading massive store from %s...", massive_dir)
        massive_closes = _load_massive_closes(massive_dir)
    else:
        log.warning("Massive store unreachable — falling back to yahoo+stocks for price data")

    stocks_closes = _load_stocks_closes()

    log.info("Loading dead-name price store...")
    dead_name_closes = _load_dead_name_closes()

    # --- Load sector benchmarks ---
    log.info("Building sector EW benchmark series...")
    sector_closes = _build_sector_closes()
    ticker_sector_map = _build_ticker_sector_map()
    log.info(
        "Sector closes: %d baskets; sector map: %d tickers",
        len(sector_closes), len(ticker_sector_map),
    )

    # --- Build panel ---
    panel = build_panel(
        labels=labels,
        yahoo_closes=yahoo_closes,
        stocks_closes=stocks_closes,
        massive_closes=massive_closes,
        dead_name_closes=dead_name_closes,
        sector_closes=sector_closes,
        ticker_sector_map=ticker_sector_map,
        eps_by_ticker=eps_by_ticker,
        earnings_by_ticker=earnings_by_ticker,
        limit=limit,
        verbose=verbose,
    )

    runtime = time.time() - t_start

    # --- Build manifest ---
    manifest = build_manifest(
        panel=panel,
        labels_manifest=labels_manifest,
        runtime_seconds=runtime,
        limit=limit,
    )

    # Log per-feature coverage
    log.info("Per-feature coverage: %s", manifest["per_feature_coverage_pct"])

    if limit is not None:
        log.info("SMOKE RUN (limit=%d) — not writing output files", limit)
        return manifest

    # --- Write outputs ---
    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    log.info("Writing %s...", _OUT_PARQUET)
    # Ensure numpy types are cast to native Python before parquet
    panel.to_parquet(_OUT_PARQUET, index=False)

    log.info("Writing %s...", _OUT_MANIFEST)
    _OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, default=str))

    log.info("=== DONE: runtime=%.1fs ===", runtime)
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build expect_drift feature panel (LT-2a, EXPECT_DRIFT_FAMILY_PREREG.md)."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print manifest without running computation.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap to first N rows for smoke testing.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress logs.")
    args = parser.parse_args(argv)

    try:
        manifest = run(
            dry_run=args.dry_run,
            limit=args.limit,
            verbose=not args.quiet,
        )
        print(json.dumps(manifest, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("Expect-drift panel builder failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
