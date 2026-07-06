#!/usr/bin/env python3
"""Paired analysis v2 — window-based T2/T3/T4 precursor pairing for T1 onsets.

Pre-registered spec:
  - Event set: TIER_ONSET events (first day each distinct tier within episode),
    full universes (US all eligible baskets/ohlcv; CN all ~1,460 eligible names).
  - Pairing: for each T1 onset at date t1, find most-recent T2 onset in
    [t1-12 sessions, t1-1] on same name.  Same for T3, T4.  One pair max
    per T1 onset per tier type.  Window is calendar-session count using the
    name's own trading calendar.
  - Stop convention: -5% from fill; breach if low[fill_day] <= 0.95*fill
    (fill day's low included, per spec); gap-through exits at open.
  - Common-exit: both legs exit at close of T1 entry date + 63 sessions
    (each leg's own -5% stop still applies from its fill; stopped legs sit
    at stop price, cash until common-exit date but return is locked at stop).
  - Outputs: /tmp/tier_deepdive/paired_v2.json + markdown tables to stdout.

Output (final message consumed by orchestrator): all tables + 3-line interpretation.
"""
from __future__ import annotations

import gc
import glob
import json
import os
import sys
import time
import warnings
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path wiring (same as _bt_tier_deepdive.py)
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parents[1]
_REPO_ROOT = _WORKTREE.parents[2]
_DATA_ROOT = _REPO_ROOT / "data"
_OUT_DIR = Path("/tmp/tier_deepdive")
_OUT_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(_WORKTREE))

from engine.confluence_tiers import tier_stream, MIN_HISTORY  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (pre-registered)
# ---------------------------------------------------------------------------
CN_START = pd.Timestamp("2016-01-01")
US_START = pd.Timestamp("2015-01-01")
COMMON_END = pd.Timestamp("2026-05-31")

GAP_MERGE = 5          # merge episodes with < 5 ineligible sessions
STOP_MULT = 0.95       # -5% hard stop
PAIR_WINDOW = 12       # sessions lookback for precursor search
COMMON_EXIT_H = 63     # common-exit horizon in sessions
TRUNC_63 = pd.Timestamp("2026-03-01")  # events after → 63d not fully matured

WORKERS = 4

# ---------------------------------------------------------------------------
# Shared loaders (replicated from v1 harness to keep this self-contained)
# ---------------------------------------------------------------------------

def _load_close_ohlcv(fp: str) -> tuple[pd.Series, pd.DataFrame]:
    df = pd.read_parquet(fp)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    close = df["close"].dropna()
    return close, df


def load_cn_benchmark() -> pd.Series:
    fp = _DATA_ROOT / "china" / "510300.SS.parquet"
    df = pd.read_parquet(str(fp))
    df.index = pd.to_datetime(df.index)
    return df["close"].sort_index()


def load_us_benchmark() -> pd.Series:
    fp = _DATA_ROOT / "yahoo" / "SPY.parquet"
    df = pd.read_parquet(str(fp))
    df.index = pd.to_datetime(df.index)
    return df["close"].sort_index()


# ---------------------------------------------------------------------------
# Episode extraction (identical to v1)
# ---------------------------------------------------------------------------

def extract_episodes(
    stream_df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    if stream_df.empty:
        return []
    df = stream_df.copy()
    df = df[(df.index >= start) & (df.index <= end)]
    if df.empty:
        return []

    elig = df["eligible"].fillna(False).astype(bool)
    dates = df.index
    episodes = []
    i = 0
    n = len(dates)

    while i < n:
        if not elig.iloc[i]:
            i += 1
            continue
        ep_start = i
        j = i
        while j < n:
            if elig.iloc[j]:
                j += 1
            else:
                gap_start = j
                k = j
                while k < n and not elig.iloc[k]:
                    k += 1
                gap_len = k - gap_start
                if gap_len < GAP_MERGE:
                    j = k
                else:
                    break
        ep_end = j - 1
        ep_slice = df.iloc[ep_start: ep_end + 1]
        ep_elig = ep_slice[ep_slice["eligible"].fillna(False).astype(bool)]
        if ep_elig.empty:
            i = ep_end + 1
            continue

        board_fire_date = ep_elig.index[0]
        board_fire_tier = ep_elig.iloc[0]["tier"]
        tier_onsets: dict[str, pd.Timestamp] = {}
        for tier_label in ("T4", "T3", "T2", "T1"):
            tier_rows = ep_elig[ep_elig["tier"] == tier_label]
            if not tier_rows.empty:
                tier_onsets[tier_label] = tier_rows.index[0]

        episodes.append({
            "start_date": ep_elig.index[0],
            "end_date": ep_elig.index[-1],
            "board_fire_date": board_fire_date,
            "board_fire_tier": board_fire_tier,
            "tier_onsets": tier_onsets,
        })
        i = ep_end + 1

    return episodes


# ---------------------------------------------------------------------------
# Entry price helpers (identical to v1)
# ---------------------------------------------------------------------------

def cn_entry_price(ohlcv: pd.DataFrame, t_date: pd.Timestamp) -> float | None:
    dates = ohlcv.index
    pos = dates.searchsorted(t_date, side="right")
    if pos >= len(dates):
        return None
    row = ohlcv.iloc[pos]
    hi = float(row["high"])
    lo = float(row["low"])
    if hi == lo:
        return None
    return (hi + lo) / 2.0


def us_entry_price(ohlcv: pd.DataFrame, t_date: pd.Timestamp) -> float | None:
    dates = ohlcv.index
    pos = dates.searchsorted(t_date, side="right")
    if pos >= len(dates):
        return None
    row = ohlcv.iloc[pos]
    op = float(row["open"]) if "open" in row.index else float("nan")
    if np.isfinite(op) and op > 0:
        return op
    cl = float(row["close"])
    if np.isfinite(cl) and cl > 0:
        return cl
    return None


def fill_date_bar(ohlcv: pd.DataFrame, t_date: pd.Timestamp) -> pd.Timestamp | None:
    dates = ohlcv.index
    pos = dates.searchsorted(t_date, side="right")
    if pos >= len(dates):
        return None
    return dates[pos]


# ---------------------------------------------------------------------------
# With-stop return computation
# Spec: stop -5% from fill; breach if low <= 0.95*fill INCLUDING fill day's low.
# Gap-through exits at open.  Common-exit: close at T1_fill_date + 63 sessions
# (session count from the name's own trading calendar).
# ---------------------------------------------------------------------------

def _wstop_return(
    ohlcv: pd.DataFrame,
    fill_price: float,
    fill_bar_date: pd.Timestamp,
    horizon_sessions: int,
    common_exit_date: pd.Timestamp | None = None,
) -> tuple[float | None, bool, float | None]:
    """Compute with-stop return for horizon_sessions after (and including) fill_bar_date.

    Returns (ret, stopped, exit_price).
    If common_exit_date is given, the window ends at common_exit_date instead of
    fill_bar_date + horizon_sessions (whichever comes first).

    Spec: fill day's low IS checked (slice starts from fill_bar_date, not fill_bar_date+1).
    """
    stop_price = fill_price * STOP_MULT
    fwd_ohlcv = ohlcv[ohlcv.index >= fill_bar_date]

    if common_exit_date is not None:
        # For common-exit: stop still applies from fill, exit locked at stop price if hit.
        # Window is fill_bar onwards up to common_exit_date.
        fwd_ohlcv = fwd_ohlcv[fwd_ohlcv.index <= common_exit_date]
        if len(fwd_ohlcv) == 0:
            return None, False, None
        has_low = "low" in fwd_ohlcv.columns
        has_open = "open" in fwd_ohlcv.columns
        for i in range(len(fwd_ohlcv)):
            row = fwd_ohlcv.iloc[i]
            lo = float(row["low"]) if has_low else float(row["close"])
            if np.isfinite(lo) and lo <= stop_price:
                # Gap-through
                exit_p = stop_price
                if has_open:
                    op = float(row["open"])
                    if np.isfinite(op) and op < stop_price:
                        exit_p = op
                return exit_p / fill_price - 1.0, True, exit_p
        # No stop; exit at close of last bar in window
        exit_cl = float(fwd_ohlcv.iloc[-1]["close"])
        if np.isfinite(exit_cl) and exit_cl > 0:
            return exit_cl / fill_price - 1.0, False, exit_cl
        return None, False, None

    # Fixed-horizon path
    if len(fwd_ohlcv) <= horizon_sessions:
        # Not enough forward bars
        return None, False, None

    has_low = "low" in fwd_ohlcv.columns
    has_open = "open" in fwd_ohlcv.columns
    # Check fill bar + horizon_sessions bars (fill bar included per spec)
    window = fwd_ohlcv.iloc[: horizon_sessions + 1]  # fill bar + H bars
    for i in range(len(window)):
        row = window.iloc[i]
        lo = float(row["low"]) if has_low else float(row["close"])
        if np.isfinite(lo) and lo <= stop_price:
            exit_p = stop_price
            if has_open:
                op = float(row["open"])
                if np.isfinite(op) and op < stop_price:
                    exit_p = op
            return exit_p / fill_price - 1.0, True, exit_p

    # No stop; exit at close of bar at fill + horizon_sessions
    exit_cl = float(fwd_ohlcv.iloc[horizon_sessions]["close"])
    if np.isfinite(exit_cl) and exit_cl > 0:
        return exit_cl / fill_price - 1.0, False, exit_cl
    return None, False, None


def _excess_wstop(
    wstop_ret: float | None,
    benchmark: pd.Series,
    fill_bar_date: pd.Timestamp,
    ohlcv_index: pd.Index,
    horizon_sessions: int,
) -> float | None:
    """Compute benchmark excess for a with-stop return over horizon_sessions."""
    if wstop_ret is None:
        return None
    # Benchmark aligned to stock sessions
    bench_aligned = benchmark.reindex(ohlcv_index, method="ffill")
    pos = ohlcv_index.searchsorted(fill_bar_date, side="left")
    if pos + horizon_sessions >= len(bench_aligned):
        return None
    b0 = float(bench_aligned.iloc[pos])
    bh = float(bench_aligned.iloc[pos + horizon_sessions])
    if b0 <= 0 or not np.isfinite(b0) or not np.isfinite(bh):
        return None
    bench_ret = bh / b0 - 1.0
    return wstop_ret - bench_ret


# ---------------------------------------------------------------------------
# Per-ticker worker: collect all TIER_ONSET events with full data
# ---------------------------------------------------------------------------

def _collect_tier_onsets_cn(args) -> list[dict]:
    """CN ticker: return list of {tier, onset_date, fill_date, fill_price, ohlcv_path, close_path}."""
    ticker, close_path, start, end = args
    try:
        close, ohlcv = _load_close_ohlcv(close_path)
        hist_before = close[close.index < start]
        if len(hist_before) < MIN_HISTORY:
            return []
        stream_df = tier_stream(close)
        if stream_df.empty:
            return []
        episodes = extract_episodes(stream_df, start, end)
        rows = []
        for ep in episodes:
            for onset_tier, onset_date in ep["tier_onsets"].items():
                fill = cn_entry_price(ohlcv, onset_date)
                if fill is None or not np.isfinite(fill) or fill <= 0:
                    continue
                fdate = fill_date_bar(ohlcv, onset_date)
                if fdate is None:
                    continue
                rows.append({
                    "ticker": ticker,
                    "tier": onset_tier,
                    "onset_date": onset_date,
                    "fill_date": fdate,
                    "fill_price": fill,
                    "close_path": close_path,
                    "truncated_63": onset_date > TRUNC_63,
                })
        return rows
    except Exception:
        return []


def _collect_tier_onsets_us(args) -> list[dict]:
    """US ticker: return list of TIER_ONSET events."""
    ticker, close_path, start, end = args
    try:
        close, ohlcv = _load_close_ohlcv(close_path)
        hist_before = close[close.index < start]
        if len(hist_before) < MIN_HISTORY:
            return []
        stream_df = tier_stream(close)
        if stream_df.empty:
            return []
        episodes = extract_episodes(stream_df, start, end)
        rows = []
        for ep in episodes:
            for onset_tier, onset_date in ep["tier_onsets"].items():
                fill = us_entry_price(ohlcv, onset_date)
                if fill is None or not np.isfinite(fill) or fill <= 0:
                    continue
                fdate = fill_date_bar(ohlcv, onset_date)
                if fdate is None:
                    continue
                rows.append({
                    "ticker": ticker,
                    "tier": onset_tier,
                    "onset_date": onset_date,
                    "fill_date": fdate,
                    "fill_price": fill,
                    "close_path": close_path,
                    "truncated_63": onset_date > TRUNC_63,
                })
        return rows
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Window-based pairing
# ---------------------------------------------------------------------------

def build_pairs_window(
    onset_events: list[dict],
) -> dict[str, list[dict]]:
    """For each T1 onset, find most-recent T2/T3/T4 precursor within PAIR_WINDOW sessions.

    Session count uses the name's own OHLCV trading calendar (sessions between onset dates
    on the same name's index).

    Returns dict with keys 'T2_vs_T1', 'T3_vs_T1', 'T4_vs_T1'.
    """
    from collections import defaultdict

    # Group by ticker
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for ev in onset_events:
        by_ticker[ev["ticker"]].append(ev)

    pairs: dict[str, list[dict]] = {
        "T2_vs_T1": [],
        "T3_vs_T1": [],
        "T4_vs_T1": [],
    }

    for ticker, events in by_ticker.items():
        # Sort all events by onset_date
        events_sorted = sorted(events, key=lambda x: x["onset_date"])

        # Build T1 list and per-tier lists
        t1_events = [e for e in events_sorted if e["tier"] == "T1"]
        if not t1_events:
            continue

        # Load OHLCV once for session-count lookup
        close_path = events_sorted[0]["close_path"]
        try:
            _, ohlcv = _load_close_ohlcv(close_path)
            ohlcv_dates = ohlcv.index  # sorted trading calendar
        except Exception:
            continue

        for early_tier_label in ("T2", "T3", "T4"):
            early_events = [e for e in events_sorted if e["tier"] == early_tier_label]
            if not early_events:
                continue

            pair_key = f"{early_tier_label}_vs_T1"

            for t1_ev in t1_events:
                t1_date = t1_ev["onset_date"]
                t1_pos = ohlcv_dates.searchsorted(t1_date, side="left")

                # Window: [t1 - PAIR_WINDOW sessions, t1 - 1 session]
                window_start_pos = max(0, t1_pos - PAIR_WINDOW)
                window_start_date = ohlcv_dates[window_start_pos] if window_start_pos < len(ohlcv_dates) else None
                if window_start_date is None:
                    continue

                # Find most-recent early_tier onset in [window_start_date, t1_date - 1 session]
                best_early = None
                for ee in reversed(early_events):
                    ed = ee["onset_date"]
                    if ed >= t1_date:
                        continue
                    # Session distance: count sessions in [ed, t1_date) on this ticker's calendar
                    ed_pos = ohlcv_dates.searchsorted(ed, side="left")
                    session_dist = t1_pos - ed_pos  # sessions between ed and t1 (t1 not included)
                    if session_dist < 1:
                        continue
                    if session_dist <= PAIR_WINDOW:
                        best_early = (ee, session_dist)
                        break

                if best_early is None:
                    continue

                early_ev, lead_sessions = best_early
                pairs[pair_key].append({
                    "ticker": ticker,
                    "early_onset_date": early_ev["onset_date"],
                    "t1_onset_date": t1_date,
                    "lead_sessions": lead_sessions,
                    "early_fill_date": early_ev["fill_date"],
                    "t1_fill_date": t1_ev["fill_date"],
                    "early_fill_price": early_ev["fill_price"],
                    "t1_fill_price": t1_ev["fill_price"],
                    "close_path": close_path,
                    "ohlcv_dates": ohlcv_dates,  # keep for outcome calc
                    "early_truncated_63": early_ev["truncated_63"],
                    "t1_truncated_63": t1_ev["truncated_63"],
                })

    return pairs


# ---------------------------------------------------------------------------
# Compute outcomes for each pair
# ---------------------------------------------------------------------------

def _compute_pair_outcomes(
    pair: dict,
    benchmark: pd.Series,
    market: str,
) -> dict | None:
    """Compute per-pair metrics: lead, fill_discount, wstop 21/63 for each leg,
    common-exit diff."""
    try:
        close_path = pair["close_path"]
        ohlcv_dates = pair["ohlcv_dates"]
        _, ohlcv = _load_close_ohlcv(close_path)

        early_fill = pair["early_fill_price"]
        t1_fill = pair["t1_fill_price"]
        early_fill_date = pair["early_fill_date"]
        t1_fill_date = pair["t1_fill_date"]
        t1_onset_date = pair["t1_onset_date"]

        fill_discount = early_fill / t1_fill - 1.0 if (t1_fill > 0) else None

        # --- with-stop returns for each leg at 21d and 63d ---
        def leg_wstop(fill_price, fill_date_bar, horizon):
            ret, stopped, ep = _wstop_return(ohlcv, fill_price, fill_date_bar, horizon, common_exit_date=None)
            return ret, stopped

        early_ws21, _ = leg_wstop(early_fill, early_fill_date, 21)
        t1_ws21, _ = leg_wstop(t1_fill, t1_fill_date, 21)
        early_ws63, _ = leg_wstop(early_fill, early_fill_date, 63)
        t1_ws63, _ = leg_wstop(t1_fill, t1_fill_date, 63)

        # Benchmark-excess for each leg
        def leg_excess(wstop_ret, fill_date_bar, horizon):
            return _excess_wstop(wstop_ret, benchmark, fill_date_bar, ohlcv.index, horizon)

        early_excess21 = leg_excess(early_ws21, early_fill_date, 21)
        t1_excess21 = leg_excess(t1_ws21, t1_fill_date, 21)
        early_excess63 = leg_excess(early_ws63, early_fill_date, 63)
        t1_excess63 = leg_excess(t1_ws63, t1_fill_date, 63)

        # --- Common-exit: both legs exit at close of t1_fill_date + 63 sessions ---
        # Find t1_fill_date position and advance 63 sessions
        t1_fill_pos = ohlcv.index.searchsorted(t1_fill_date, side="left")
        common_exit_pos = t1_fill_pos + 63
        if common_exit_pos >= len(ohlcv.index):
            common_exit_date = None
        else:
            common_exit_date = ohlcv.index[common_exit_pos]

        if common_exit_date is None:
            common_early_ret = None
            common_t1_ret = None
            common_diff = None
            early_beat = None
        else:
            # Each leg: own -5% stop from fill, then cash until common_exit_date
            # but the return is locked at stop exit price once hit.
            # We compute return from fill to common_exit_date (with stop).
            common_early_ret, _, _ = _wstop_return(
                ohlcv, early_fill, early_fill_date, COMMON_EXIT_H,
                common_exit_date=common_exit_date,
            )
            common_t1_ret, _, _ = _wstop_return(
                ohlcv, t1_fill, t1_fill_date, COMMON_EXIT_H,
                common_exit_date=common_exit_date,
            )
            if common_early_ret is not None and common_t1_ret is not None:
                common_diff = common_early_ret - common_t1_ret
                early_beat = common_early_ret > common_t1_ret
            else:
                common_diff = None
                early_beat = None

        return {
            "lead_sessions": pair["lead_sessions"],
            "fill_discount": fill_discount,
            "early_ws21": early_ws21,
            "t1_ws21": t1_ws21,
            "early_excess21": early_excess21,
            "t1_excess21": t1_excess21,
            "early_ws63": early_ws63,
            "t1_ws63": t1_ws63,
            "early_excess63": early_excess63,
            "t1_excess63": t1_excess63,
            "common_early_ret": common_early_ret,
            "common_t1_ret": common_t1_ret,
            "common_diff": common_diff,
            "early_beat": early_beat,
            "early_truncated_63": pair["early_truncated_63"],
            "t1_truncated_63": pair["t1_truncated_63"],
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Coverage stats and conversion analysis
# ---------------------------------------------------------------------------

def coverage_stats(
    onset_events: list[dict],
) -> dict:
    """
    (a) Share of T1 onsets with a T2/T3/T4 precursor within 12 sessions.
    (b) Conversion: share of T2/T3 onsets followed by T1 within 12 sessions,
        and 21d/63d with-stop excess of CONVERTED vs UNCONVERTED.
    """
    from collections import defaultdict

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for ev in onset_events:
        by_ticker[ev["ticker"]].append(ev)

    # (a) T1 precursor coverage
    t1_total = 0
    t1_with_t2 = 0
    t1_with_t3 = 0
    t1_with_t4 = 0

    # (b) Conversion tracking
    # For each T2/T3 onset: was it followed by T1 within 12 sessions?
    t2_converted = []   # list of onset event dicts where T1 followed
    t2_unconverted = []
    t3_converted = []
    t3_unconverted = []

    for ticker, events in by_ticker.items():
        events_sorted = sorted(events, key=lambda x: x["onset_date"])
        t1_events = [e for e in events_sorted if e["tier"] == "T1"]

        # Load ohlcv calendar for session distance
        close_path = events_sorted[0]["close_path"]
        try:
            _, ohlcv = _load_close_ohlcv(close_path)
            ohlcv_dates = ohlcv.index
        except Exception:
            continue

        # --- (a) T1 coverage ---
        for t1_ev in t1_events:
            t1_total += 1
            t1_date = t1_ev["onset_date"]
            t1_pos = ohlcv_dates.searchsorted(t1_date, side="left")

            found_t2 = False
            found_t3 = False
            found_t4 = False

            for ee in events_sorted:
                ed = ee["onset_date"]
                if ed >= t1_date:
                    continue
                ed_pos = ohlcv_dates.searchsorted(ed, side="left")
                session_dist = t1_pos - ed_pos
                if session_dist < 1 or session_dist > PAIR_WINDOW:
                    continue
                if ee["tier"] == "T2":
                    found_t2 = True
                elif ee["tier"] == "T3":
                    found_t3 = True
                elif ee["tier"] == "T4":
                    found_t4 = True

            if found_t2:
                t1_with_t2 += 1
            if found_t3:
                t1_with_t3 += 1
            if found_t4:
                t1_with_t4 += 1

        # --- (b) Conversion ---
        for early_tier_label in ("T2", "T3"):
            early_events = [e for e in events_sorted if e["tier"] == early_tier_label]
            for early_ev in early_events:
                ed = early_ev["onset_date"]
                ed_pos = ohlcv_dates.searchsorted(ed, side="left")

                # Check if any T1 follows within PAIR_WINDOW sessions
                converted = False
                for t1_ev in t1_events:
                    t1_pos = ohlcv_dates.searchsorted(t1_ev["onset_date"], side="left")
                    session_dist = t1_pos - ed_pos
                    if 1 <= session_dist <= PAIR_WINDOW:
                        converted = True
                        break

                ev_copy = dict(early_ev)
                if early_tier_label == "T2":
                    if converted:
                        t2_converted.append(ev_copy)
                    else:
                        t2_unconverted.append(ev_copy)
                else:  # T3
                    if converted:
                        t3_converted.append(ev_copy)
                    else:
                        t3_unconverted.append(ev_copy)

    def _safe_mean(vals):
        vs = [v for v in vals if v is not None and np.isfinite(v)]
        return float(np.mean(vs)) if vs else None

    def _safe_median(vals):
        vs = [v for v in vals if v is not None and np.isfinite(v)]
        return float(np.median(vs)) if vs else None

    def _conv_stats(event_list, benchmark, market):
        """Compute 21d/63d wstop excess for a list of onset events."""
        ws21_list = []
        ws63_list = []
        ex21_list = []
        ex63_list = []
        for ev in event_list:
            if ev.get("truncated_63", True):
                continue
            try:
                _, ohlcv = _load_close_ohlcv(ev["close_path"])
                fill = ev["fill_price"]
                fdate = ev["fill_date"]
                ws21, _ = leg_wstop_fn(ohlcv, fill, fdate, 21)
                ws63, _ = leg_wstop_fn(ohlcv, fill, fdate, 63)
                ex21 = _excess_wstop(ws21, benchmark, fdate, ohlcv.index, 21)
                ex63 = _excess_wstop(ws63, benchmark, fdate, ohlcv.index, 63)
                if ws21 is not None:
                    ws21_list.append(ws21)
                if ws63 is not None:
                    ws63_list.append(ws63)
                if ex21 is not None:
                    ex21_list.append(ex21)
                if ex63 is not None:
                    ex63_list.append(ex63)
            except Exception:
                pass
        return {
            "n": len(event_list),
            "wstop_mean_21": _safe_mean(ws21_list),
            "wstop_median_21": _safe_median(ws21_list),
            "excess_mean_21": _safe_mean(ex21_list),
            "excess_median_21": _safe_median(ex21_list),
            "wstop_mean_63": _safe_mean(ws63_list),
            "wstop_median_63": _safe_median(ws63_list),
            "excess_mean_63": _safe_mean(ex63_list),
            "excess_median_63": _safe_median(ex63_list),
        }

    # We need leg_wstop as a closure-compatible fn
    def leg_wstop_fn(ohlcv, fill_price, fill_date_bar, horizon):
        ret, stopped, _ = _wstop_return(ohlcv, fill_price, fill_date_bar, horizon, common_exit_date=None)
        return ret, stopped

    return {
        "t1_total": t1_total,
        "t1_with_t2_precursor": t1_with_t2,
        "t1_with_t2_pct": round(t1_with_t2 / t1_total * 100, 2) if t1_total > 0 else None,
        "t1_with_t3_precursor": t1_with_t3,
        "t1_with_t3_pct": round(t1_with_t3 / t1_total * 100, 2) if t1_total > 0 else None,
        "t1_with_t4_precursor": t1_with_t4,
        "t1_with_t4_pct": round(t1_with_t4 / t1_total * 100, 2) if t1_total > 0 else None,
        "t2_converted_n": len(t2_converted),
        "t2_unconverted_n": len(t2_unconverted),
        "t2_conversion_rate_pct": round(
            len(t2_converted) / (len(t2_converted) + len(t2_unconverted)) * 100, 2
        ) if (t2_converted or t2_unconverted) else None,
        "t3_converted_n": len(t3_converted),
        "t3_unconverted_n": len(t3_unconverted),
        "t3_conversion_rate_pct": round(
            len(t3_converted) / (len(t3_converted) + len(t3_unconverted)) * 100, 2
        ) if (t3_converted or t3_unconverted) else None,
        "_t2_converted": t2_converted,
        "_t2_unconverted": t2_unconverted,
        "_t3_converted": t3_converted,
        "_t3_unconverted": t3_unconverted,
    }


# ---------------------------------------------------------------------------
# Aggregate pair statistics
# ---------------------------------------------------------------------------

def _safe_mean(vals):
    vs = [v for v in vals if v is not None and np.isfinite(v)]
    return float(np.mean(vs)) if vs else None


def _safe_median(vals):
    vs = [v for v in vals if v is not None and np.isfinite(v)]
    return float(np.median(vs)) if vs else None


def aggregate_pairs(computed: list[dict]) -> dict:
    """Aggregate outcomes across pairs."""
    if not computed:
        return {"n": 0}

    def col(key):
        return [r[key] for r in computed if r.get(key) is not None]

    leads = col("lead_sessions")
    discounts = col("fill_discount")

    # Non-truncated for 63d metrics
    nt = [r for r in computed if not r.get("t1_truncated_63", True) and not r.get("early_truncated_63", True)]

    common_diffs = [r["common_diff"] for r in nt if r.get("common_diff") is not None]
    early_beats = [r["early_beat"] for r in nt if r.get("early_beat") is not None]

    return {
        "n": len(computed),
        "n_non_truncated_63": len(nt),
        "median_lead_sessions": _safe_median(leads),
        "mean_lead_sessions": _safe_mean(leads),
        "median_fill_discount": _safe_median(discounts),
        "mean_fill_discount": _safe_mean(discounts),
        # Per-leg with-stop excess at 21d
        "early_excess21_mean": _safe_mean(col("early_excess21")),
        "early_excess21_median": _safe_median(col("early_excess21")),
        "t1_excess21_mean": _safe_mean(col("t1_excess21")),
        "t1_excess21_median": _safe_median(col("t1_excess21")),
        # Per-leg with-stop excess at 63d (non-truncated)
        "early_excess63_mean": _safe_mean([r["early_excess63"] for r in nt if r.get("early_excess63") is not None]),
        "early_excess63_median": _safe_median([r["early_excess63"] for r in nt if r.get("early_excess63") is not None]),
        "t1_excess63_mean": _safe_mean([r["t1_excess63"] for r in nt if r.get("t1_excess63") is not None]),
        "t1_excess63_median": _safe_median([r["t1_excess63"] for r in nt if r.get("t1_excess63") is not None]),
        # With-stop raw returns at 21d
        "early_wstop21_mean": _safe_mean(col("early_ws21")),
        "early_wstop21_median": _safe_median(col("early_ws21")),
        "t1_wstop21_mean": _safe_mean(col("t1_ws21")),
        "t1_wstop21_median": _safe_median(col("t1_ws21")),
        # With-stop raw returns at 63d (non-truncated)
        "early_wstop63_mean": _safe_mean([r["early_ws63"] for r in nt if r.get("early_ws63") is not None]),
        "early_wstop63_median": _safe_median([r["early_ws63"] for r in nt if r.get("early_ws63") is not None]),
        "t1_wstop63_mean": _safe_mean([r["t1_ws63"] for r in nt if r.get("t1_ws63") is not None]),
        "t1_wstop63_median": _safe_median([r["t1_ws63"] for r in nt if r.get("t1_ws63") is not None]),
        # Common-exit
        "common_diff_mean": _safe_mean(common_diffs),
        "common_diff_median": _safe_median(common_diffs),
        "win_share_early": (
            float(sum(1 for b in early_beats if b) / len(early_beats) * 100)
            if early_beats else None
        ),
    }


# ---------------------------------------------------------------------------
# Markdown table helpers
# ---------------------------------------------------------------------------

def _pct(v, decimals=1):
    if v is None:
        return "—"
    return f"{v * 100:.{decimals}f}%"


def _val(v, decimals=2):
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def _n(v):
    if v is None:
        return "—"
    return str(int(v))


def print_pair_table(market: str, stats: dict[str, dict]) -> str:
    lines = []
    lines.append(f"\n### {market} — Paired Analysis (window={PAIR_WINDOW} sessions)")
    lines.append("")
    lines.append("| Pair type | n pairs | n non-trunc | lead_med (sess) | fill_discount_med |"
                 " early_excess21_med | T1_excess21_med | early_excess63_med | T1_excess63_med |"
                 " common_diff_med | win_share_early |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for pkey in ("T2_vs_T1", "T3_vs_T1", "T4_vs_T1"):
        s = stats.get(pkey, {})
        if not s or s.get("n", 0) == 0:
            lines.append(f"| {pkey} | 0 | — | — | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {pkey} | {s['n']} | {_n(s.get('n_non_truncated_63'))} |"
            f" {_val(s.get('median_lead_sessions'), 1)} |"
            f" {_pct(s.get('median_fill_discount'))} |"
            f" {_pct(s.get('early_excess21_median'))} |"
            f" {_pct(s.get('t1_excess21_median'))} |"
            f" {_pct(s.get('early_excess63_median'))} |"
            f" {_pct(s.get('t1_excess63_median'))} |"
            f" {_pct(s.get('common_diff_median'))} |"
            f" {_val(s.get('win_share_early'), 1)}% |"
        )
    return "\n".join(lines)


def print_coverage_table(market: str, cov: dict) -> str:
    lines = []
    lines.append(f"\n### {market} — Coverage Stats")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| T1 onsets total | {cov['t1_total']} |")
    lines.append(f"| T1 with T2 precursor (≤12 sess) | {cov['t1_with_t2_precursor']} ({_val(cov['t1_with_t2_pct'], 1)}%) |")
    lines.append(f"| T1 with T3 precursor (≤12 sess) | {cov['t1_with_t3_precursor']} ({_val(cov['t1_with_t3_pct'], 1)}%) |")
    lines.append(f"| T1 with T4 precursor (≤12 sess) | {cov['t1_with_t4_precursor']} ({_val(cov['t1_with_t4_pct'], 1)}%) |")
    lines.append(f"| T2 conversion rate (T1 follows ≤12 sess) | {_val(cov['t2_conversion_rate_pct'], 1)}% ({cov['t2_converted_n']} of {cov['t2_converted_n'] + cov['t2_unconverted_n']}) |")
    lines.append(f"| T3 conversion rate (T1 follows ≤12 sess) | {_val(cov['t3_conversion_rate_pct'], 1)}% ({cov['t3_converted_n']} of {cov['t3_converted_n'] + cov['t3_unconverted_n']}) |")
    return "\n".join(lines)


def print_conversion_table(market: str, conv_stats: dict) -> str:
    lines = []
    lines.append(f"\n### {market} — Conversion Risk (T2/T3: converted vs unconverted)")
    lines.append("")
    lines.append("| Tier | State | n | wstop_mean_21 | wstop_med_21 | excess_mean_21 | excess_med_21 |"
                 " wstop_mean_63 | wstop_med_63 | excess_mean_63 | excess_med_63 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for tier_label in ("T2", "T3"):
        for state in ("converted", "unconverted"):
            key = f"{tier_label}_{state}"
            s = conv_stats.get(key, {})
            n = s.get("n", 0)
            lines.append(
                f"| {tier_label} | {state} | {n} |"
                f" {_pct(s.get('wstop_mean_21'))} |"
                f" {_pct(s.get('wstop_median_21'))} |"
                f" {_pct(s.get('excess_mean_21'))} |"
                f" {_pct(s.get('excess_median_21'))} |"
                f" {_pct(s.get('wstop_mean_63'))} |"
                f" {_pct(s.get('wstop_median_63'))} |"
                f" {_pct(s.get('excess_mean_63'))} |"
                f" {_pct(s.get('excess_median_63'))} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_market(market: str) -> dict:
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"Running {market} lane ...")

    if market == "CN":
        members = pd.read_parquet(_DATA_ROOT / "china_search" / "members.parquet")
        tickers = members.index.tolist()
        all_paths = [
            (t, str(_DATA_ROOT / "china_stocks" / f"{t}.parquet"), CN_START, COMMON_END)
            for t in tickers
            if (_DATA_ROOT / "china_stocks" / f"{t}.parquet").exists()
        ]
        print(f"  CN candidates: {len(all_paths)}")
        fn = _collect_tier_onsets_cn
        benchmark = load_cn_benchmark()
        market_str = "CN"
    else:
        fps = sorted(glob.glob(str(_DATA_ROOT / "baskets" / "ohlcv" / "*.parquet")))
        all_paths = [
            (Path(fp).stem, fp, US_START, COMMON_END)
            for fp in fps
        ]
        print(f"  US candidates: {len(all_paths)}")
        fn = _collect_tier_onsets_us
        benchmark = load_us_benchmark()
        market_str = "US"

    # Collect tier onsets with multiprocessing
    print(f"  Collecting TIER_ONSET events with {WORKERS} workers ...")
    with Pool(WORKERS) as pool:
        results_nested = pool.map(fn, all_paths)

    onset_events = []
    for r in results_nested:
        onset_events.extend(r)

    print(f"  Total TIER_ONSET events: {len(onset_events)}")
    t1_n = sum(1 for e in onset_events if e["tier"] == "T1")
    t2_n = sum(1 for e in onset_events if e["tier"] == "T2")
    t3_n = sum(1 for e in onset_events if e["tier"] == "T3")
    t4_n = sum(1 for e in onset_events if e["tier"] == "T4")
    print(f"  T1={t1_n} T2={t2_n} T3={t3_n} T4={t4_n}")

    # Build window-based pairs
    print("  Building window-based pairs ...")
    pairs = build_pairs_window(onset_events)
    for pk, plist in pairs.items():
        print(f"    {pk}: {len(plist)} pairs")

    # Compute outcomes per pair
    pair_stats_by_type = {}
    for pkey, plist in pairs.items():
        print(f"  Computing outcomes for {pkey} ({len(plist)} pairs) ...")
        computed = []
        for p in plist:
            out = _compute_pair_outcomes(p, benchmark, market_str)
            if out is not None:
                computed.append(out)
        pair_stats_by_type[pkey] = aggregate_pairs(computed)
        print(f"    {pkey}: {len(computed)} gradable outcomes")

    # Coverage and conversion stats
    print("  Computing coverage stats ...")
    cov = coverage_stats(onset_events)

    # Compute wstop/excess for converted/unconverted
    print("  Computing conversion risk outcomes ...")
    conv_stats_out = {}
    for tier_label in ("T2", "T3"):
        for state in ("converted", "unconverted"):
            key_in = f"_{tier_label.lower()}_{state}"
            ev_list = cov.get(key_in, [])
            # Compute outcomes
            ws21_list, ws63_list, ex21_list, ex63_list = [], [], [], []
            for ev in ev_list:
                if ev.get("truncated_63", True):
                    continue
                try:
                    _, ohlcv = _load_close_ohlcv(ev["close_path"])
                    fill = ev["fill_price"]
                    fdate = ev["fill_date"]
                    ret21, _, _ = _wstop_return(ohlcv, fill, fdate, 21)
                    ret63, _, _ = _wstop_return(ohlcv, fill, fdate, 63)
                    ex21 = _excess_wstop(ret21, benchmark, fdate, ohlcv.index, 21)
                    ex63 = _excess_wstop(ret63, benchmark, fdate, ohlcv.index, 63)
                    if ret21 is not None:
                        ws21_list.append(ret21)
                    if ret63 is not None:
                        ws63_list.append(ret63)
                    if ex21 is not None:
                        ex21_list.append(ex21)
                    if ex63 is not None:
                        ex63_list.append(ex63)
                except Exception:
                    pass

            key_out = f"{tier_label}_{state}"
            conv_stats_out[key_out] = {
                "n": len(ev_list),
                "wstop_mean_21": _safe_mean(ws21_list),
                "wstop_median_21": _safe_median(ws21_list),
                "excess_mean_21": _safe_mean(ex21_list),
                "excess_median_21": _safe_median(ex21_list),
                "wstop_mean_63": _safe_mean(ws63_list),
                "wstop_median_63": _safe_median(ws63_list),
                "excess_mean_63": _safe_mean(ex63_list),
                "excess_median_63": _safe_median(ex63_list),
            }

    elapsed = time.time() - t0
    print(f"  {market} lane complete in {elapsed:.1f}s")

    # Strip internal lists before serializing (not needed in JSON output)
    cov_clean = {k: v for k, v in cov.items() if not k.startswith("_")}

    return {
        "market": market,
        "n_tickers": len(all_paths),
        "n_tier_onset_events": len(onset_events),
        "tier_onset_counts": {"T1": t1_n, "T2": t2_n, "T3": t3_n, "T4": t4_n},
        "pair_counts": {pk: len(plist) for pk, plist in pairs.items()},
        "pair_stats": pair_stats_by_type,
        "coverage": cov_clean,
        "conversion_stats": conv_stats_out,
        "elapsed_s": round(elapsed, 1),
    }


def main():
    t_total = time.time()
    results = {}
    all_tables = []

    for market in ("CN", "US"):
        result = run_market(market)
        results[market] = result

        pair_table = print_pair_table(market, result["pair_stats"])
        cov_table = print_coverage_table(market, result["coverage"])
        conv_table = print_conversion_table(market, result["conversion_stats"])

        all_tables.append(pair_table)
        all_tables.append(cov_table)
        all_tables.append(conv_table)

        print(pair_table)
        print(cov_table)
        print(conv_table)

    # Selection-bias note
    bias_note = (
        "\n**Selection-bias note:** pairs condition on T1 eventually firing "
        "(i.e., T2/T3/T4 was followed by T1 within 12 sessions). "
        "The converted/unconverted split is the honest complement: "
        "it shows what happened to T2/T3 onsets whether or not T1 ever confirmed. "
        "Unconverted onsets are the 'buy-early-and-confirmation-never-comes' population."
    )
    trunc_note = (
        "\n**Truncated-cohort note:** events after 2026-03-01 lack full 63d forward data. "
        "Pair stats at 63d and common-exit use only pairs where BOTH legs are non-truncated."
    )

    print(bias_note)
    print(trunc_note)

    total_elapsed = time.time() - t_total

    results["meta"] = {
        "pair_window_sessions": PAIR_WINDOW,
        "stop_mult": STOP_MULT,
        "common_exit_horizon_sessions": COMMON_EXIT_H,
        "trunc_63_cutoff": str(TRUNC_63.date()),
        "fill_day_low_included": True,
        "total_elapsed_s": round(total_elapsed, 1),
        "notes": [
            "Window-based pairing: for each T1 onset, finds most-recent T2/T3/T4 within PAIR_WINDOW sessions on same name.",
            "Session count uses the name's own OHLCV trading calendar.",
            "Fill day's low is included in stop monitoring (per spec).",
            "Common-exit: both legs exit at close of T1_fill_date + 63 sessions; each leg's own -5% stop from its fill still applies.",
            "Coverage (a): share of T1 onsets with T2/T3/T4 precursor within 12 sessions.",
            "Coverage (b): conversion rate = share of T2/T3 onsets followed by T1 within 12 sessions.",
            "Conversion risk: 21d/63d wstop excess split by converted vs unconverted T2/T3 onsets.",
            "No VALIDATED language used. All metrics are descriptive.",
            "Pairs condition on T1 firing — selection-bias applies; converted/unconverted split is honest complement.",
            f"CN universe: china_search/members.parquet (2026 snapshot, survivorship-biased). "
            f"US universe: all baskets/ohlcv/ parquets.",
        ],
        "caveats": [
            "CN universe has no PIT ledger — survivorship-biased.",
            "tier_stream T1 uses raw 3D RSI-MACD cross as fallback (no take_date); T1 event counts differ from live board.",
            f"Events after {TRUNC_63.date()} lack full 63d forward data (truncated). 63d/common-exit stats exclude these.",
        ],
    }

    # Serialize
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, pd.Timestamp):
            return str(obj.date())
        if isinstance(obj, pd.DatetimeIndex):
            return None  # strip indices
        raise TypeError(f"Not serializable: {type(obj)}")

    out_path = _OUT_DIR / "paired_v2.json"
    with open(str(out_path), "w") as f:
        json.dump(results, f, indent=2, default=_json_safe)

    print(f"\nResults written to {out_path}")
    print(f"Total runtime: {total_elapsed:.1f}s ({total_elapsed/60:.1f}m)")
    return results


if __name__ == "__main__":
    main()
