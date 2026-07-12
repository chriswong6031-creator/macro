"""Index Hybrid Momentum organ (index_momentum.v1).

DISPLAY-TIER / NOT VALIDATED — context organ, authority all-false.
Ruling IHM-R1..R4, R8, R11, R14.  Program tag: IHM.

Computes the TH_RSIMACD+ hybrid indicator (RSI-based MACD, engine.canon) at four
timeframes (1D, 2B, 3B, W-FRI) for 13 index carriers across US / HK / CN / INTL.
Derives histogram velocity, depth percentile, cross events with quality tags, and
three global-turn confluence tags (IHM-R4).

Outputs
-------
  data/index_momentum/latest.json   — per-index × grid snapshot + recent events
  data/index_momentum/events.parquet — append-only cross-event ledger (idempotent)

Inputs (all git-tracked; no new collectors)
-------------------------------------------
  US:   data/yahoo/{SPY,QQQ,IWM,SOXX}.parquet          (store group "yahoo")
  MAG7: data/baskets/ohlcv/{AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA}.parquet
  HK:   data/hk/{_HSI,_HSCE,3033.HK}.parquet           (store group "hk")
  CN:   data/china/{000001.SS,510300.SS,399001.SZ}.parquet (store group "china")
  INTL: data/intl/{_KS11,_TWII}.parquet                 (store group "intl")

House law compliance
--------------------
  - All RSI/EMA math via engine.canon (IHM-R8): SMA-seeded Wilder RSI.
  - Completed bars only; W-FRI uses calendar resample (house idiom).
  - Session-grouped 2B/3B resample via canon.resample_sessions.
  - Timestamps kept naive in parquet (pandas 3.0.x tz-aware→naive raises).
  - No templates, no site/ writes, no authority fields.
  - Target wall time < 5s; one [timing] line printed.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config
from engine.canon import (
    crossover,
    crossunder,
    rsi_macd,
    resample_sessions,
    stoch_rsi_kd,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Roster v1 (IHM-R1)
# ---------------------------------------------------------------------------

# (id, store_group, store_name, label_en, label_zh, region)
# MAG7 carrier is built inline from data/baskets/ohlcv/; store_group="mag7_carrier"
# is a sentinel handled specially in _load_close().
ROSTER: list[tuple[str, str, str, str, str, str]] = [
    # US
    ("SPY",        "yahoo",   "SPY",        "S&P 500",       "标普500",    "US"),
    ("QQQ",        "yahoo",   "QQQ",        "Nasdaq 100",    "纳指100",    "US"),
    ("IWM",        "yahoo",   "IWM",        "Russell 2000",  "罗素2000",   "US"),
    ("SOXX",       "yahoo",   "SOXX",       "Semis (SOXX)",  "半导体SOXX", "US"),
    # MAG7 equal-weight carrier (indicator only; mag7_regime.v1 owns the authority organ)
    # TODO: switch to mag7_regime.v1 cap-weighted composite when M7C program merges it.
    ("MAG7",       "mag7_carrier", "MAG7",  "Mag 7 (eq-wt)","七巨头(等权)","US"),
    # HK
    ("^HSI",       "hk",      "_HSI",       "Hang Seng",     "恒生指数",   "HK"),
    ("^HSCE",      "hk",      "_HSCE",      "HSCEI",         "国企指数",   "HK"),
    ("3033.HK",    "hk",      "3033.HK",    "HS TECH",       "恒生科技",   "HK"),
    # CN (store group "china" per market_state_cn.py / china_inputs.py)
    ("000001.SS",  "china",   "000001.SS",  "Shanghai",      "上证综指",   "CN"),
    ("510300.SS",  "china",   "510300.SS",  "CSI 300",       "沪深300",    "CN"),
    ("399001.SZ",  "china",   "399001.SZ",  "Shenzhen",      "深证成指",   "CN"),
    # INTL
    ("^KS11",      "intl",    "_KS11",      "KOSPI",         "韩国综合",   "INTL"),
    ("^TWII",      "intl",    "_TWII",      "TAIEX",         "台湾加权",   "INTL"),
]

_MAG7_MEMBERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

# Grids: (label, resample_n_sessions, rule_or_None)
# 1D = daily; 2B/3B = session-grouped; W-FRI = calendar weekly
_GRIDS = [
    ("1D",    1,  None),
    ("2B",    2,  None),
    ("3B",    3,  None),
    ("W-FRI", None, "W-FRI"),
]

# 10-year trailing window for depth percentile (IHM-R2)
_DEPTH_PCTILE_YEARS = 10
_DEPTH_PCTILE_BARS  = 252 * _DEPTH_PCTILE_YEARS   # approx

# Velocity lookback (IHM-R3)
_HIST_VEL_LAG = 3

# fast_reclaim threshold (IHM-R3, calibrated descriptively on HSI 06-30→07-03)
_FAST_RECLAIM_VEL_MIN = 0.9
_FAST_RECLAIM_LOOKBACK = 10

# recent events window for snapshot (days)
_RECENT_EVENTS_DAYS = 30

# trap zone band (IHM-R2, raw absolute)
_TRAP_ZONE_LO, _TRAP_ZONE_HI = -6.0, -4.0


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_close(
    group: str, name: str, root: Path | None = None
) -> pd.Series | None:
    """Load a close series from the store.  Returns None on failure (degrade-don't-crash)."""
    if group == "mag7_carrier":
        return _load_mag7_carrier(root)
    try:
        data_root = Path(root) / "data" if root else config.data_dir()
        # Use store.read path convention: data/<group>/<safe_name>.parquet
        safe = name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")
        p = data_root / group / f"{safe}.parquet"
        if not p.exists():
            log.warning("index_momentum: %s not found at %s", name, p)
            return None
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        if "close" not in df.columns:
            log.warning("index_momentum: no 'close' column in %s/%s", group, name)
            return None
        return df["close"].dropna().astype(float)
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: load failed %s/%s: %s", group, name, e)
        return None


def _load_mag7_carrier(root: Path | None = None) -> pd.Series | None:
    """Equal-weight daily-return composite of the 7 Mag7 members from data/baskets/ohlcv/."""
    data_root = Path(root) / "data" if root else config.data_dir()
    returns = []
    for sym in _MAG7_MEMBERS:
        p = data_root / "baskets" / "ohlcv" / f"{sym}.parquet"
        if not p.exists():
            log.warning("index_momentum: MAG7 member %s not found", sym)
            continue
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            if "close" not in df.columns:
                continue
            r = df["close"].dropna().astype(float).sort_index().pct_change()
            returns.append(r)
        except Exception as e:  # noqa: BLE001
            log.warning("index_momentum: MAG7 member %s load failed: %s", sym, e)
    if not returns:
        return None
    aligned = pd.concat(returns, axis=1).dropna(how="all")
    eq_ret = aligned.mean(axis=1).dropna()
    # Reconstitute a level series from the equal-weight daily returns
    # Start at 100 on the first available date
    level = (1 + eq_ret).cumprod() * 100.0
    return level.astype(float)


# ---------------------------------------------------------------------------
# Grid computation
# ---------------------------------------------------------------------------

def _resample_to_grid(close: pd.Series, n_sessions: int | None, rule: str | None) -> pd.Series | None:
    """Resample close to the requested grid.  Returns COMPLETED-bar series only.

    IHM-R1 PIT compliance
    ---------------------
    - W-FRI: drop the trailing bucket when its label (the next Friday) is AFTER the last
      observed daily date — that week is still in progress.  Pattern mirrors the
      RUL-31 _completed_resample idiom in confluence_tiers.py.
    - 2B/3B: drop the last bucket when len(daily) % n_sessions != 0 — that bucket
      has fewer than n_sessions sessions and is still accumulating.
    """
    if close is None or len(close) < 30:
        return None
    try:
        if n_sessions is None or n_sessions == 1:
            if rule:
                # Calendar resample (W-FRI) — completed bars only (IHM-R1 PIT gate):
                # a W-FRI bar labeled with a future Friday is an in-progress week;
                # drop it by keeping only bars whose label <= last observed daily date.
                last_obs = close.index.max()
                b = close.resample(rule).last().dropna()
                b = b[b.index <= last_obs]
                return b if len(b) > 0 else None
            return close  # 1D: daily bars are already complete
        else:
            bucketed, _ = resample_sessions(close, n_sessions)
            # Drop the trailing partial bucket when the session count is not an exact
            # multiple of n_sessions — that last bucket has < n_sessions sessions.
            # Use len(close.dropna()) to match the internal count resample_sessions uses
            # (loaders always return dropna() series, but defensive here is free).
            n_sessions_total = int(close.dropna().count())
            if n_sessions_total % n_sessions != 0 and len(bucketed) > 0:
                bucketed = bucketed.iloc[:-1]
            return bucketed if len(bucketed) > 0 else None
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: resample failed n=%s rule=%s: %s", n_sessions, rule, e)
        return None


def _compute_grid(close: pd.Series, grid_label: str, n_sessions: int | None, rule: str | None) -> dict | None:
    """Compute all indicators for one index on one grid."""
    s = _resample_to_grid(close, n_sessions, rule)
    if s is None or len(s) < 100:
        return None
    try:
        macd_s, sig_s = rsi_macd(s)
        k_s, d_s = stoch_rsi_kd(s)
        hist = macd_s - sig_s
        hist_vel3 = hist - hist.shift(_HIST_VEL_LAG)

        # Depth percentile — trailing 10y window on this grid
        # Use up to _DEPTH_PCTILE_BARS bars back from each point
        depth_pctile = _rolling_percentile(macd_s, _DEPTH_PCTILE_BARS)

        # Effective window size at the latest bar (IHM spec §5 disclosure requirement).
        # Indices with < 10y history compute pctile against a shorter window; downstream
        # consumers (ledger, display) must be able to see the effective window.
        pctile_window_bars = int(min(len(macd_s.dropna()), _DEPTH_PCTILE_BARS))

        # Cross events
        bull_cross = crossover(macd_s, sig_s)
        bear_cross = crossunder(macd_s, sig_s)

        # fast_reclaim_from_depth — scalar for latest bar
        fast_reclaim = _compute_fast_reclaim(macd_s, hist_vel3, depth_pctile)

        return {
            "macd":               macd_s,
            "signal":             sig_s,
            "hist":               hist,
            "hist_vel3":          hist_vel3,
            "k":                  k_s,
            "d":                  d_s,
            "depth_pctile":       depth_pctile,
            "pctile_window_bars": pctile_window_bars,
            "bull_cross":         bull_cross,
            "bear_cross":         bear_cross,
            "fast_reclaim":       fast_reclaim,
            "dates":              s.index,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: compute_grid %s failed: %s", grid_label, e)
        return None


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """Rolling percentile rank: what fraction of the trailing window is < current value."""
    s = series.values.astype(float)
    out = np.full(len(s), np.nan)
    for i in range(len(s)):
        lo = max(0, i - window + 1)
        w = s[lo:i + 1]
        valid = w[np.isfinite(w)]
        if len(valid) >= 20:
            cur = s[i]
            if not np.isfinite(cur):
                continue
            out[i] = float(np.sum(valid < cur)) / len(valid) * 100.0
    return pd.Series(out, index=series.index)


def _compute_fast_reclaim(
    macd_s: pd.Series,
    hist_vel3: pd.Series,
    depth_pctile: pd.Series,
) -> bool | None:
    """fast_reclaim_from_depth for the current (last) bar.

    True iff:
      min(macd over last 10 bars) <= 10th pctile (depth ≤ p10)
      AND hist_vel3 >= +0.9
    (IHM-R3)
    """
    if macd_s.empty or hist_vel3.empty or depth_pctile.empty:
        return None
    try:
        last10_macd = macd_s.iloc[-_FAST_RECLAIM_LOOKBACK:]
        cur_vel3 = hist_vel3.iloc[-1]
        if not np.isfinite(cur_vel3):
            return None
        # p10 gate via the SAME strictly-less-than rank estimator as depth_pctile —
        # one percentile definition across the organ, so fast_reclaim can never
        # disagree with a displayed depth_pctile <= 10
        window = macd_s.iloc[-_DEPTH_PCTILE_BARS:].dropna()
        if len(window) < 20:
            return None
        min_depth_10bars = float(last10_macd.min())
        if not np.isfinite(min_depth_10bars):
            return None
        rank = float(np.sum(window.values < min_depth_10bars)) / len(window) * 100.0
        return bool(rank <= 10.0 and cur_vel3 >= _FAST_RECLAIM_VEL_MIN)
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: fast_reclaim compute failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Quality tag (IHM-R2)
# ---------------------------------------------------------------------------

def _quality_tag(depth_at_cross: float, pctile_at_cross: float | None) -> str:
    """washout_turn / trap_zone / ordinary based on depth_at_cross and pctile."""
    # Primary: pctile (bounded, regime-invariant)
    if pctile_at_cross is not None and np.isfinite(pctile_at_cross):
        if pctile_at_cross <= 10.0:
            return "washout_turn"
    # Secondary: raw absolute for trap_zone (consistent with IHM-R2 spec)
    if np.isfinite(depth_at_cross) and _TRAP_ZONE_LO < depth_at_cross <= _TRAP_ZONE_HI:
        return "trap_zone"
    # If no pctile available but raw depth <= -8 (deep), flag as washout_turn
    if pctile_at_cross is None or not np.isfinite(pctile_at_cross):
        if np.isfinite(depth_at_cross) and depth_at_cross <= -8.0:
            return "washout_turn"
    return "ordinary"


# ---------------------------------------------------------------------------
# Event extraction
# ---------------------------------------------------------------------------

def _extract_events(
    index_id: str,
    grid_label: str,
    grid_data: dict,
) -> list[dict]:
    """Extract cross events (both directions) from computed grid data."""
    events = []
    try:
        macd = grid_data["macd"]
        hist_vel3 = grid_data["hist_vel3"]
        depth_pctile = grid_data["depth_pctile"]
        bull_cross = grid_data["bull_cross"]
        bear_cross = grid_data["bear_cross"]

        for direction, crosses in [("bull", bull_cross), ("bear", bear_cross)]:
            fire_dates = crosses[crosses].index
            for dt in fire_dates:
                try:
                    depth = float(macd.loc[dt])
                    pctile_val = depth_pctile.loc[dt] if dt in depth_pctile.index else np.nan
                    pctile_f = float(pctile_val) if np.isfinite(float(pctile_val) if pctile_val is not None else np.nan) else None
                    vel3 = float(hist_vel3.loc[dt]) if dt in hist_vel3.index and np.isfinite(float(hist_vel3.loc[dt])) else None
                    tag = _quality_tag(depth, pctile_f)
                    events.append({
                        "index":          index_id,
                        "grid":           grid_label,
                        "date":           dt.date(),
                        "direction":      direction,
                        "depth_at_cross": round(depth, 3),
                        "depth_pctile":   round(pctile_f, 1) if pctile_f is not None else None,
                        "hist_vel3":      round(vel3, 3) if vel3 is not None else None,
                        "quality_tag":    tag,
                    })
                except Exception as e:  # noqa: BLE001
                    log.debug("index_momentum: event extract %s %s %s: %s", index_id, grid_label, dt, e)
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: extract_events %s %s: %s", index_id, grid_label, e)
    return events


# ---------------------------------------------------------------------------
# Confluence tags (IHM-R4, event-based only)
# ---------------------------------------------------------------------------

def _us_confirm_tag(
    hk_cn_event: dict,
    spy_grid1d: dict | None,
) -> bool:
    """IHM-R4a: us_confirm on any HK/CN washout_turn.

    Condition: SPY 1D hybrid hist rising over 3 sessions OR macd>signal at event date.
    Uses the closest available SPY bar at-or-before the event date (handles US market
    holidays — e.g. 2026-07-03 is US Independence Day, so SPY has no bar that day;
    we use the closest prior bar via searchsorted with 'right' side and -1).
    """
    if spy_grid1d is None:
        return False
    try:
        event_date = pd.Timestamp(hk_cn_event["date"])
        macd = spy_grid1d["macd"]
        sig  = spy_grid1d["signal"]
        hist = spy_grid1d["hist"]

        # Find the closest SPY bar at-or-before event_date
        # searchsorted('right') gives insertion point; -1 gives the last bar <= event_date
        spy_idx = macd.index.searchsorted(event_date, side="right") - 1
        if spy_idx < 0:
            return False
        spy_date = macd.index[spy_idx]

        # macd > signal at the matching SPY bar
        m_val = float(macd.iloc[spy_idx])
        s_val = float(sig.iloc[spy_idx])
        if np.isfinite(m_val) and np.isfinite(s_val) and m_val > s_val:
            return True

        # hist rising over 3 sessions ending at spy_idx
        if spy_idx >= 2:
            window = hist.iloc[max(0, spy_idx - 2):spy_idx + 1]
            if len(window) >= 2:
                diffs = window.diff().dropna()
                if (diffs > 0).all():
                    return True
    except Exception as e:  # noqa: BLE001
        log.debug("index_momentum: us_confirm_tag error: %s", e)
    return False


def _global_washout_turn_tag(
    event: dict,
    spy_grid1d: dict | None,
    lookback_sessions: int = 10,
) -> bool:
    """IHM-R4b: global_washout_turn = HK washout_turn + SPY deep cross (<=−4) within prior 10 sessions.

    PIT-compliance notes
    --------------------
    1. Restricted to grid == '1D' only.  The construction (IHM-R4b) is defined at the
       daily grain; applying a 10-daily-session SPY window to a W-FRI/2B/3B HK event is
       a grain mismatch — it over-fires the macro-washout chip on weekly events.
    2. SPY window uses searchsorted side='right' so the window end index is EXCLUSIVE
       of any SPY session AFTER the HK event date — fixes a 1-2-session look-ahead that
       was present with the prior side='left' / idx+1 idiom.
    """
    if event.get("quality_tag") != "washout_turn":
        return False
    if event.get("index") not in ("^HSI", "^HSCE", "3033.HK"):
        return False
    # Restrict to 1D grain — W-FRI/2B/3B events must not be tagged with a 10-daily-session
    # SPY window (grain mismatch; IHM-R4b is a daily-grain construction).
    if event.get("grid") != "1D":
        return False
    if spy_grid1d is None:
        return False
    try:
        event_date = pd.Timestamp(event["date"])
        spy_macd = spy_grid1d["macd"]
        spy_bull = spy_grid1d["bull_cross"]

        # SPY deep cross (macd <= -4) within prior 10 sessions
        if spy_macd.empty or spy_bull.empty:
            return False
        # side='right': insertion point AFTER any bar ON event_date, so the slice
        # spy_bull.iloc[lo_idx:idx] is strictly "SPY sessions at-or-before event_date".
        # This avoids the 1-2-session look-ahead that side='left' / idx+1 produced.
        idx = spy_bull.index.searchsorted(event_date, side="right")
        lo_idx = max(0, idx - lookback_sessions)
        window_bull = spy_bull.iloc[lo_idx:idx]
        recent_spy_crosses = window_bull[window_bull].index
        for spy_dt in recent_spy_crosses:
            try:
                spy_depth = float(spy_macd.loc[spy_dt])
                if spy_depth <= -4.0:
                    return True
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        log.debug("index_momentum: global_washout_turn_tag error: %s", e)
    return False


def _turn_breadth(all_grid1d: dict[str, dict]) -> dict:
    """IHM-R4c: count of roster indices with 1D hist > 0 and list of fresh crossers (last 3 sessions)."""
    hist_positive_count = 0
    hist_positive_ids = []
    fresh_crossers = []
    for idx_id, gd in all_grid1d.items():
        if gd is None:
            continue
        try:
            hist = gd["hist"]
            if not hist.empty and float(hist.iloc[-1]) > 0:
                hist_positive_count += 1
                hist_positive_ids.append(idx_id)
            bull_cross = gd["bull_cross"]
            recent = bull_cross[bull_cross].index
            if len(recent) > 0:
                latest_cross = recent[-1]
                last_date = hist.index[-1]
                delta_sessions = len(hist.loc[latest_cross:last_date]) - 1
                if delta_sessions <= 3:
                    fresh_crossers.append({
                        "index": idx_id,
                        "cross_date": str(latest_cross.date()),
                        "sessions_ago": int(delta_sessions),
                    })
        except Exception as e:  # noqa: BLE001
            log.debug("index_momentum: turn_breadth %s error: %s", idx_id, e)
    return {
        "hist_positive_count": hist_positive_count,
        "hist_positive_ids": hist_positive_ids,
        "fresh_crossers": fresh_crossers,
    }


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

def _current_values(grid_data: dict) -> dict:
    """Extract scalar latest-bar values for the JSON snapshot."""
    def _last(s: pd.Series) -> float | None:
        if s is None or s.empty:
            return None
        v = s.iloc[-1]
        return round(float(v), 3) if np.isfinite(float(v)) else None

    # pctile_window_bars: effective trailing bar count used for depth_pctile.
    # Disclosed per IHM spec §5: indices with < 10y history use a shorter window;
    # exposing this lets the ledger and display surfaces flag heterogeneous comparisons.
    pw_bars = grid_data.get("pctile_window_bars")
    pw_days = int(round(pw_bars * 7 / 5)) if pw_bars is not None else None  # approx calendar days

    return {
        "macd":                _last(grid_data["macd"]),
        "signal":              _last(grid_data["signal"]),
        "hist":                _last(grid_data["hist"]),
        "hist_vel3":           _last(grid_data["hist_vel3"]),
        "k":                   _last(grid_data["k"]),
        "d":                   _last(grid_data["d"]),
        "depth_pctile":        (_last(grid_data["depth_pctile"])
                                if grid_data["depth_pctile"] is not None else None),
        "pctile_window_bars":  pw_bars,
        "pctile_window_days":  pw_days,
        "fast_reclaim":        grid_data.get("fast_reclaim"),
        "as_of":               str(grid_data["dates"][-1].date()) if len(grid_data["dates"]) > 0 else None,
    }


def _recent_events_for_index(
    events: list[dict], index_id: str, grid: str,
    as_of_d: date, days: int = 30,
) -> list[dict]:
    """Filter events to the recent window, keyed to the DATA as_of (never wall clock —
    a later-day re-run on unchanged data must produce the identical snapshot)."""
    result = [
        e for e in events
        if e["index"] == index_id and e["grid"] == grid
    ]
    # Sort descending by date, keep last N days before the data as_of
    result.sort(key=lambda x: x["date"], reverse=True)
    cutoff_d = (pd.Timestamp(as_of_d) - pd.Timedelta(days=days)).date()
    result = [e for e in result if e["date"] >= cutoff_d]
    return result[:10]  # cap at 10 per (index, grid)


# ---------------------------------------------------------------------------
# Events parquet — idempotent upsert
# ---------------------------------------------------------------------------

def _upsert_events_parquet(new_events: list[dict], root: Path | None = None) -> None:
    """Append-only upsert of cross events keyed (index, grid, date, direction).

    Re-runs must not duplicate rows.  Timestamps are stored as naive date objects
    (parquet datetime without tz; pandas 3.0.x tz-aware→naive assignment raises).
    """
    if not new_events:
        return
    data_root = Path(root) / "data" if root else config.data_dir()
    out_dir = data_root / "index_momentum"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "events.parquet"

    new_df = pd.DataFrame(new_events)
    # Convert date column to naive datetime (no tz)
    new_df["date"] = pd.to_datetime(new_df["date"]).dt.normalize()
    key_cols = ["index", "grid", "date", "direction"]
    new_df = new_df.drop_duplicates(subset=key_cols)

    if out_path.exists():
        try:
            old_df = pd.read_parquet(out_path)
            old_df["date"] = pd.to_datetime(old_df["date"]).dt.normalize()
            combined = pd.concat([old_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=key_cols, keep="last")
            combined = combined.sort_values(["date", "index", "grid"]).reset_index(drop=True)
        except Exception as e:  # noqa: BLE001
            log.warning("index_momentum: events.parquet read failed, overwriting: %s", e)
            combined = new_df.sort_values(["date", "index", "grid"]).reset_index(drop=True)
    else:
        combined = new_df.sort_values(["date", "index", "grid"]).reset_index(drop=True)

    combined.to_parquet(out_path, index=False)
    log.info("index_momentum: events.parquet upserted %d total rows", len(combined))


# ---------------------------------------------------------------------------
# Main snapshot()
# ---------------------------------------------------------------------------

# IHM-R5 authority fence — display-tier, all-false. Any promotion goes through
# the IHM-R12 preregs; nothing else may flip these.
AUTHORITY_V1 = {"rank": False, "size": False, "gate": False, "escalate": False}


def snapshot(root: str | Path | None = None) -> dict:
    """Build the index_momentum.v1 snapshot.

    Writes data/index_momentum/latest.json and upserts data/index_momentum/events.parquet.
    Returns the payload dict.  Never raises — degrades to partial payload on errors.
    """
    t0 = time.time()
    _root = Path(root) if root else None

    all_events: list[dict] = []
    index_snapshots: dict[str, Any] = {}
    # Collect all 1D grids for confluence tags
    all_grid1d: dict[str, dict] = {}

    for (idx_id, grp, name, label_en, label_zh, region) in ROSTER:
        close = _load_close(grp, name, _root)
        if close is None or len(close) < 100:
            log.warning("index_momentum: insufficient data for %s, skipping", idx_id)
            index_snapshots[idx_id] = {
                "id": idx_id, "label_en": label_en, "label_zh": label_zh,
                "region": region, "grids": {}, "error": "insufficient_data",
            }
            continue

        grids_out: dict[str, Any] = {}
        for (gl, n_sess, rule) in _GRIDS:
            gd = _compute_grid(close, gl, n_sess, rule)
            if gd is None:
                grids_out[gl] = None
                continue
            curr = _current_values(gd)
            events = _extract_events(idx_id, gl, gd)
            all_events.extend(events)
            if gl == "1D":
                all_grid1d[idx_id] = gd
            grids_out[gl] = curr

        index_snapshots[idx_id] = {
            "id":        idx_id,
            "label_en":  label_en,
            "label_zh":  label_zh,
            "region":    region,
            "grids":     grids_out,
        }

    # --- SPY 1D for confluence (IHM-R4) ---
    spy_grid1d = all_grid1d.get("SPY")

    # --- Annotate events with confluence tags ---
    hk_cn_ids = {"^HSI", "^HSCE", "3033.HK", "000001.SS", "510300.SS", "399001.SZ"}
    for ev in all_events:
        ev["us_confirm"]          = False
        ev["global_washout_turn"] = False
        if ev["direction"] == "bull" and ev.get("quality_tag") == "washout_turn" and ev["index"] in hk_cn_ids:
            ev["us_confirm"]          = _us_confirm_tag(ev, spy_grid1d)
            ev["global_washout_turn"] = _global_washout_turn_tag(ev, spy_grid1d)

    # --- turn_breadth for 1D grid (IHM-R4c) ---
    breadth = _turn_breadth(all_grid1d)

    # PIT data stamp: last completed 1D bar across the roster (the build-date
    # `as_of` below is the SLA heartbeat, per the ignition_radar convention)
    _dd = [gd["dates"][-1] for gd in all_grid1d.values()
           if gd is not None and len(gd["dates"]) > 0]
    data_as_of = max(_dd).date() if _dd else date.today()

    # --- recent events per (index, grid) for snapshot ---
    for idx_id in index_snapshots:
        idx_snap = index_snapshots[idx_id]
        for gl in (g[0] for g in _GRIDS):
            if idx_snap["grids"].get(gl) is None:
                continue
            recent = _recent_events_for_index(all_events, idx_id, gl, as_of_d=data_as_of)
            # Serialize dates
            for ev in recent:
                ev["date"] = str(ev["date"])
            idx_snap["grids"][gl]["recent_events"] = recent

    # --- Upsert events parquet ---
    try:
        _upsert_events_parquet(all_events, _root)
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: events.parquet upsert failed: %s", e)

    elapsed = time.time() - t0
    log.info("[timing] index_momentum.snapshot: %.2fs", elapsed)

    # as_of = build-date SLA heartbeat (house convention shared with ignition_radar);
    # data_as_of = PIT stamp of the newest completed daily bar — freshness readers
    # that care about DATA staleness must use data_as_of, not as_of.
    as_of = str(date.today())
    payload = {
        "organ":       "index_momentum.v1",
        "as_of":       as_of,
        "data_as_of":  str(data_as_of),
        "authority":   dict(AUTHORITY_V1),
        "accruing":    (
            "DISPLAY-ONLY / NOT VALIDATED. Forward ledger accruing. "
            "Each washout_turn / global_washout_turn event graded on fwd20/fwd60 "
            "absolute + vs SPY at first read (IHM-R11). "
            "Promotion to authority requires IHM-R12 preregs."
        ),
        "indices":     index_snapshots,
        "turn_breadth": breadth,
        "n_roster":    len(ROSTER),
        "_timing_s":   round(elapsed, 2),
    }

    # --- Write latest.json ---
    try:
        data_root = Path(_root) / "data" if _root else config.data_dir()
        out_dir = data_root / "index_momentum"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "latest.json"
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("index_momentum: wrote %s", out_path)
    except Exception as e:  # noqa: BLE001
        log.warning("index_momentum: write latest.json failed: %s", e)

    return payload
