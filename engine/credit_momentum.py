"""Corporate Credit Watch — Credit Momentum Organ (credit_momentum.v1).

DISPLAY-TIER / NOT VALIDATED — authority all-false, accruing forward.
Program: CCW. Wave: W3. Rulings: CCW-R6, R10, R13, R15, R16.
Masterplan refs: §3-P3, §3-P4, §3-P5, §2.5-5/6/7.

Computes spread velocity/acceleration and oscillator states (RSI-MACD + StochRSI)
across D / 2B / 3B / W-FRI grids for the full credit roster.

Spread series: velocity-percentile is PRIMARY; oscillator crosses ship as SECONDARY
(CCW-R15 / §2.5-6 — sanity-study outcome documented in oscillator_sanity.json).

Spread orientation: widening = deterioration = severity (CCW-R13).

DENSITY GATE: a theme qualifies for oscillator/confluence only if
  - n_bonds >= 8 AND
  - matched_n / n_bonds >= 0.6 on rolling 21d basis
Sub-threshold themes emit level/delta/velocity with plain-word note only.

Outputs
-------
  data/corp_bonds/credit_momentum.json     — per-series snapshot + tags
  data/corp_bonds/forward_log.jsonl        — keep-FIRST event ledger

Inputs
------
  Deep-history (archive-merged):
    data/archive/BAMLH0A0HYM2.parquet + data/fred/BAMLH0A0HYM2.parquet  → hy_oas
    data/archive/BAMLC0A0CM.parquet   + data/fred/BAMLC0A0CM.parquet    → ig_oas
  Deep-history FRED (1983+):
    data/fred/DBAA.parquet, data/fred/DAAA.parquet
  Rolling-window (~3y) ladder:
    data/archive/BAML{C0A1CAAA,C0A2CAA,C0A3CA,C0A4CBBB,H0A1HYBB,H0A2HYB}.parquet
    data/fred/BAMLH0A3HYC.parquet  → ccc_oas
  Yahoo ETF prices:
    data/yahoo/{LQD,HYG,TLT,IEF}.parquet  (JNK if present)
  CCW-W2 series:
    data/corp_bonds/series/theme_daily.parquet
    data/corp_bonds/series/market_daily.parquet
  Equity closes for divergence:
    data/baskets/ohlcv/<TICKER>.parquet (theme equity members)
    data/yahoo/<TICKER>.parquet (fallback)
  FINRA breadth (CCW-W5, already collected):
    data/corp_bonds/finra_corporateMarketBreadth.parquet
    data/corp_bonds/finra_corporateMarketSentiment.parquet
  Own-store holdings (for own-store breadth):
    data/corp_bonds/holdings/<FUND>/<date>.parquet
  Issuer registry:
    data/corp_bonds/issuer_themes.json
"""
from __future__ import annotations

import json
import logging
import os
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
# Authority contract (CCW-R10 — display-tier, all-false)
# ---------------------------------------------------------------------------

AUTHORITY_V1 = {"rank": False, "size": False, "gate": False, "escalate": False}

_ACCRUING_NOTE = (
    "DISPLAY-ONLY / NOT VALIDATED. Forward ledger accruing since first nightly "
    "run. Spread velocity-percentile is the PRIMARY read; oscillator crosses ship "
    "as SECONDARY per CCW-R15/§2.5-6. Oscillator sanity study documented in "
    "data/corp_bonds/oscillator_sanity.json. Promotion requires pre-registered "
    "gauntlet (CCW-R10). Nulls are printed, not hidden."
)

# Track-record disclaimer (pre-gauntlet)
_TAG_NO_RECORD = "no track record yet — first events accruing"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GRIDS = [
    ("1D",    1,   None),
    ("2B",    2,   None),
    ("3B",    3,   None),
    ("W-FRI", None, "W-FRI"),
]

# Minimum DAILY bars required before resampling each grid (§2.5-5).
# Interpretation: we require >= N daily bars of raw history before resampling
# so the resampled series contains >= 200 completed bars.
# 1D: 200 daily bars → 200 resampled 1D bars (trivial, no resample)
# 2B: 400 daily bars → ~200 completed 2B bars
# 3B: 600 daily bars → ~200 completed 3B bars
# W-FRI: 200 daily bars → ~40 weekly bars (min acceptable for weekly oscillator)
_MIN_DAILY_BARS: dict[str, int] = {
    "1D":    200,
    "2B":    400,   # ~200 completed 2B bars need ~400 daily bars
    "3B":    600,   # ~200 completed 3B bars need ~600 daily bars
    "W-FRI": 200,   # weekly: ~4 years of daily bars
}

# Minimum RESAMPLED bars required after resampling (oscillator computation floor).
_MIN_RESAMPLED_BARS = 200

# Velocity lookbacks
_VEL21 = 21
_VEL63 = 63

# Rolling percentile window (10y)
_PCTILE_YEARS = 10
_PCTILE_BARS  = 252 * _PCTILE_YEARS

# Post-2021 era cutoff for era-aware percentile
_ERA_CUTOFF = pd.Timestamp("2021-01-01")

# Histogram velocity lag (from IHM pattern)
_HIST_VEL_LAG = 3

# Density gate thresholds (§2.5-7, CCW-R15)
# NOTE (Fix 8 — CCW review, R15 interpretation of record):
# The density gate applies ONLY to own-panel theme/market series built from the
# CCW-W2 bond panel (theme_daily.parquet / market_daily.parquet). It checks
# n_bonds >= 8 AND matched_n/n_bonds >= 0.60 on a rolling 21d basis.
# FRED/ETF index series (hy_oas, ig_oas, Moody's spreads, LQD/HYG/TLT/IEF etc.)
# are index-native — they represent published market indices with full and
# continuous coverage; the density gate does NOT apply to them.
_DENSITY_N_MIN = 8
_DENSITY_MATCH_RATIO = 0.6
_DENSITY_ROLL = 21   # rolling days for density check

# Spread widening episode threshold for velocity tag (pctile >= 85 = stress)
_VEL_PCTILE_STRESS = 85.0

# Debounce: min bars for a credit_market_turn state to persist
_DEBOUNCE_MARKET_TURN = 5
_DEBOUNCE_THEME_STRESS = 3

# Interim TLT label
_INTERIM_LABEL = "interim proxy — the rates program's yield organ replaces this"

# Forward ledger rulers
_FWD_H_PRIMARY   = 21   # h21 business days
_FWD_H_SECONDARY = 63   # h63 business days


# ---------------------------------------------------------------------------
# Root helper
# ---------------------------------------------------------------------------

def _data_root(root: Path | None) -> Path:
    return root if root is not None else Path(config.data_dir())


# ---------------------------------------------------------------------------
# Series loaders
# ---------------------------------------------------------------------------

def _load_archive_merged(fred_id: str, alias: str, root: Path) -> pd.Series | None:
    """Load a FRED series, combining archive (deep history) + live feed (combine_first)."""
    fred_path = root / "fred" / f"{fred_id}.parquet"
    arch_path  = root / "archive" / f"{fred_id}.parquet"

    live: pd.Series | None = None
    arch: pd.Series | None = None

    for path, tag in [(fred_path, "live"), (arch_path, "archive")]:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                s = df.iloc[:, 0].dropna().astype(float)
                if tag == "live":
                    live = s
                else:
                    arch = s
            except Exception as exc:  # noqa: BLE001
                log.warning("credit_momentum: load %s %s failed: %s", tag, fred_id, exc)

    if live is None and arch is None:
        log.warning("credit_momentum: %s (%s) not found", fred_id, alias)
        return None

    if arch is not None and live is not None:
        merged = live.combine_first(arch)
        return merged.sort_index().dropna()
    # Exactly one of live/arch is non-None
    s = live if live is not None else arch
    return s.sort_index().dropna()  # type: ignore[union-attr]


def _load_yahoo_close(ticker: str, root: Path) -> pd.Series | None:
    """Load a yahoo ETF/ticker close series."""
    safe = ticker.replace("^", "_").replace("=", "_").replace("/", "_")
    path = root / "yahoo" / f"{safe}.parquet"
    if not path.exists():
        log.info("credit_momentum: yahoo %s not found at %s", ticker, path)
        return None
    try:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        col = "close" if "close" in df.columns else ("close_price" if "close_price" in df.columns else None)
        if col is None:
            log.warning("credit_momentum: no close col in yahoo/%s", ticker)
            return None
        return df[col].dropna().astype(float)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: yahoo %s load failed: %s", ticker, exc)
        return None


def _load_equity_close(ticker: str, root: Path) -> pd.Series | None:
    """Load an equity close: try data/baskets/ohlcv/<t>.parquet then data/yahoo/<t>.parquet."""
    for subdir in ["baskets/ohlcv", "yahoo"]:
        path = root / subdir / f"{ticker}.parquet"
        if path.exists():
            try:
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                col = "close" if "close" in df.columns else ("close_price" if "close_price" in df.columns else None)
                if col is None:
                    continue
                return df[col].dropna().astype(float)
            except Exception as exc:  # noqa: BLE001
                log.warning("credit_momentum: equity %s/%s load failed: %s", subdir, ticker, exc)
    return None


def _load_theme_daily(root: Path) -> pd.DataFrame:
    """Load data/corp_bonds/series/theme_daily.parquet."""
    path = root / "corp_bonds" / "series" / "theme_daily.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
        if "as_of" in df.columns:
            df["as_of"] = pd.to_datetime(df["as_of"])
            df = df.sort_values("as_of")
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: theme_daily load failed: %s", exc)
        return pd.DataFrame()


def _load_market_daily(root: Path) -> pd.DataFrame:
    """Load data/corp_bonds/series/market_daily.parquet."""
    path = root / "corp_bonds" / "series" / "market_daily.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path)
        if "as_of" in df.columns:
            df["as_of"] = pd.to_datetime(df["as_of"])
            df = df.sort_values("as_of")
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: market_daily load failed: %s", exc)
        return pd.DataFrame()


def _load_issuer_registry(root: Path) -> dict:
    path = root / "corp_bonds" / "issuer_themes.json"
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: issuer registry load failed: %s", exc)
        return {"themes": {}}


def _load_bond_panel_latest(root: Path) -> pd.DataFrame:
    path = root / "corp_bonds" / "series" / "bond_panel_latest.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: bond_panel_latest load failed: %s", exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """Rolling percentile rank (strictly less than): fraction of trailing window < current."""
    s = series.values.astype(float)
    out = np.full(len(s), np.nan)
    for i in range(len(s)):
        lo = max(0, i - window + 1)
        w = s[lo : i + 1]
        valid = w[np.isfinite(w)]
        if len(valid) >= 20:
            cur = s[i]
            if not np.isfinite(cur):
                continue
            out[i] = float(np.sum(valid < cur)) / len(valid) * 100.0
    return pd.Series(out, index=series.index)


def _rolling_percentile_post2021(series: pd.Series, window: int) -> pd.Series:
    """Same but restricted to post-2021 window for era-split display."""
    # Truncate the input to post-2021 dates first
    post = series[series.index >= _ERA_CUTOFF]
    if len(post) < 30:
        return pd.Series(np.nan, index=series.index)
    result_post = _rolling_percentile(post, window)
    # Reindex back to full series (pre-era values will be NaN)
    return result_post.reindex(series.index)


def _velocity_pctile(vel: pd.Series) -> pd.Series:
    """10y rolling percentile of a velocity series."""
    return _rolling_percentile(vel, _PCTILE_BARS)


# ---------------------------------------------------------------------------
# Resample (mirroring index_momentum pattern)
# ---------------------------------------------------------------------------

def _resample_to_grid(series: pd.Series, n_sessions: int | None, rule: str | None) -> pd.Series | None:
    """Resample to grid; completed bars only."""
    if series is None or len(series) < 30:
        return None
    try:
        if n_sessions is None or n_sessions == 1:
            if rule:
                # Calendar resample (W-FRI) — drop incomplete trailing bar
                last_obs = series.index.max()
                b = series.resample(rule).last().dropna()
                b = b[b.index <= last_obs]
                return b if len(b) > 0 else None
            return series  # 1D: already daily
        else:
            bucketed, _ = resample_sessions(series, n_sessions)
            n_total = int(series.dropna().count())
            if n_total % n_sessions != 0 and len(bucketed) > 0:
                bucketed = bucketed.iloc[:-1]
            return bucketed if len(bucketed) > 0 else None
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: resample failed n=%s rule=%s: %s", n_sessions, rule, exc)
        return None


# ---------------------------------------------------------------------------
# Grid computation (core)
# ---------------------------------------------------------------------------

def _compute_grid_data(series: pd.Series, grid_label: str, n_sessions: int | None, rule: str | None) -> dict | None:
    """Compute RSI-MACD + StochRSI indicators on a grid. Returns None if insufficient bars.

    Gating (Fix 1 — CCW review):
      1. BEFORE resampling: require len(daily_series) >= _MIN_DAILY_BARS[grid_label]
         This ensures 2B needs 400 daily bars (not 400 resampled bars which would be 800 daily),
         and 3B needs 600 daily bars (not 600 resampled bars which would be 1800 daily).
      2. AFTER resampling: require len(resampled) >= _MIN_RESAMPLED_BARS (200)
         This is the actual oscillator computation floor.
    """
    # Gate 1: daily bar check BEFORE resampling
    min_daily = _MIN_DAILY_BARS.get(grid_label, 200)
    if series is None or len(series) < min_daily:
        return None
    s = _resample_to_grid(series, n_sessions, rule)
    if s is None:
        return None
    # Gate 2: resampled bar check AFTER resampling
    if len(s) < _MIN_RESAMPLED_BARS:
        return None
    try:
        macd_s, sig_s = rsi_macd(s)
        k_s, d_s = stoch_rsi_kd(s)
        hist = macd_s - sig_s
        hist_vel3 = hist - hist.shift(_HIST_VEL_LAG)
        depth_pctile = _rolling_percentile(macd_s, _PCTILE_BARS)
        bull_cross = crossover(macd_s, sig_s)
        bear_cross = crossunder(macd_s, sig_s)
        return {
            "macd": macd_s,
            "signal": sig_s,
            "hist": hist,
            "hist_vel3": hist_vel3,
            "k": k_s,
            "d": d_s,
            "depth_pctile": depth_pctile,
            "bull_cross": bull_cross,
            "bear_cross": bear_cross,
            "dates": s.index,
            "n_bars": len(s),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: compute_grid %s failed: %s", grid_label, exc)
        return None


def _grid_snapshot(gd: dict) -> dict:
    """Extract scalar latest-bar values from a computed grid dict."""
    def _last(s: pd.Series | None) -> float | None:
        if s is None or s.empty:
            return None
        v = s.iloc[-1]
        return round(float(v), 4) if np.isfinite(float(v)) else None

    return {
        "macd":         _last(gd["macd"]),
        "signal":       _last(gd["signal"]),
        "hist":         _last(gd["hist"]),
        "hist_vel3":    _last(gd["hist_vel3"]),
        "k":            _last(gd["k"]),
        "d":            _last(gd["d"]),
        "depth_pctile": _last(gd["depth_pctile"]),
        "as_of":        str(gd["dates"][-1].date()) if len(gd["dates"]) > 0 else None,
        "n_bars":       gd.get("n_bars"),
    }


def _quality_tag(depth: float | None, pctile: float | None) -> str:
    """Classify a cross event: washout_turn / ordinary (IHM vocabulary)."""
    if pctile is not None and np.isfinite(float(pctile)) and float(pctile) <= 10.0:
        return "washout_turn"
    return "ordinary"


def _extract_cross_events(
    series_id: str,
    grid_label: str,
    gd: dict,
    orientation: str = "price",   # 'price' or 'spread'
    sanity_verdict: str | None = None,
) -> list[dict]:
    """Extract bull/bear cross events from a computed grid.

    For spread series (orientation='spread') — SEVERITY INVERSION (Fix 2, CCW review):
    RSI-MACD/StochRSI bull_cross (MACD crossing above signal) is a MOMENTUM indicator
    on the raw spread value, meaning the spread is ACCELERATING UPWARD = WIDENING.
    Empirically verified: mean d1 at bull_cross on HY OAS ≈ +0.071 bp (widening).
    Therefore the correct mapping is:
      bull_cross → 'widening_deterioration'   (spread rising = stress worsening)
      bear_cross → 'tightening_improvement'   (spread falling = stress easing)
    This is inverted from a price series where bull_cross = improvement.

    All crosses flagged secondary=True per CCW-R15/§2.5-6.
    The sanity field references oscillator_sanity.json verdict for this series×grid.
    """
    events = []
    try:
        macd = gd["macd"]
        hist_vel3 = gd["hist_vel3"]
        depth_pctile = gd["depth_pctile"]
        bull_cross = gd["bull_cross"]
        bear_cross = gd["bear_cross"]

        for direction, crosses in [("bull", bull_cross), ("bear", bear_cross)]:
            fire_dates = crosses[crosses].index
            for dt in fire_dates:
                try:
                    depth = float(macd.loc[dt]) if dt in macd.index else np.nan
                    p_val = depth_pctile.loc[dt] if dt in depth_pctile.index else np.nan
                    p_f = float(p_val) if np.isfinite(float(p_val) if p_val is not None else np.nan) else None
                    vel3 = float(hist_vel3.loc[dt]) if dt in hist_vel3.index and np.isfinite(float(hist_vel3.loc[dt])) else None
                    tag = _quality_tag(depth, p_f)
                    # Spread semantics (severity inversion vs price):
                    # bull_cross = spread momentum UP = widening = deterioration
                    # bear_cross = spread momentum DOWN = tightening = improvement
                    severity = None
                    if orientation == "spread":
                        if direction == "bull":
                            severity = "widening_deterioration"
                        else:
                            severity = "tightening_improvement"
                    events.append({
                        "series_id":     series_id,
                        "grid":          grid_label,
                        "date":          dt.date(),
                        "direction":     direction,
                        "orientation":   orientation,
                        "severity":      severity,
                        "depth_at_cross": round(float(depth), 4) if np.isfinite(float(depth)) else None,
                        "depth_pctile":  round(p_f, 1) if p_f is not None else None,
                        "hist_vel3":     round(vel3, 4) if vel3 is not None else None,
                        "quality_tag":   tag,
                        "secondary":     True if orientation == "spread" else False,
                        "event_type":    "oscillator_cross",
                        # Sanity verdict reference (populated from oscillator_sanity.json)
                        "sanity":        sanity_verdict,
                        # Forward ruler (CCW-R15 §3-P3)
                        "ruler_primary_h":   _FWD_H_PRIMARY,
                        "ruler_secondary_h": _FWD_H_SECONDARY,
                    })
                except Exception as exc:  # noqa: BLE001
                    log.debug("credit_momentum: event %s %s %s: %s", series_id, grid_label, dt, exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: extract_cross_events %s %s: %s", series_id, grid_label, exc)
    return events


# ---------------------------------------------------------------------------
# Velocity / acceleration computation
# ---------------------------------------------------------------------------

def _compute_velocity(daily_series: pd.Series, composition_mask: pd.Series | None = None) -> dict:
    """Compute vel21/vel63 with rolling 10y percentile + post-2021 era variant.

    Returns a dict with {vel21, vel63, vel21_pctile, vel63_pctile,
                         vel21_pctile_post2021, vel63_pctile_post2021,
                         accel_vel21 (1d diff of vel21)}.

    composition_mask: boolean series indexed same as daily_series; True = suppress.
    For spread series, higher velocity = MORE widening = deterioration.
    """
    out: dict = {
        "vel21": None, "vel63": None,
        "vel21_pctile": None, "vel63_pctile": None,
        "vel21_pctile_post2021": None, "vel63_pctile_post2021": None,
        "accel_vel21": None,
    }
    if daily_series is None or len(daily_series) < max(_VEL21, 30):
        return out

    try:
        s = daily_series.dropna().astype(float)

        # Apply composition mask: null out composition-change bars
        if composition_mask is not None:
            mask = composition_mask.reindex(s.index).fillna(False).astype(bool)
            s = s.where(~mask)

        vel21 = s.diff(_VEL21)
        vel63 = s.diff(_VEL63) if len(s) >= _VEL63 else pd.Series(np.nan, index=s.index)
        accel = vel21.diff(1)  # d(vel21)

        def _safe_last(x: pd.Series) -> float | None:
            if x.empty:
                return None
            v = x.iloc[-1]
            return round(float(v), 4) if pd.notna(v) and np.isfinite(float(v)) else None

        def _safe_pctile(v: pd.Series) -> float | None:
            p = _velocity_pctile(v)
            return _safe_last(p)

        def _safe_pctile_post(v: pd.Series) -> float | None:
            p = _rolling_percentile_post2021(v, _PCTILE_BARS)
            return _safe_last(p)

        out["vel21"] = _safe_last(vel21)
        out["vel63"] = _safe_last(vel63)
        out["vel21_pctile"] = _safe_pctile(vel21)
        out["vel63_pctile"] = _safe_pctile(vel63)
        out["vel21_pctile_post2021"] = _safe_pctile_post(vel21)
        out["vel63_pctile_post2021"] = _safe_pctile_post(vel63)
        out["accel_vel21"] = _safe_last(accel)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: velocity compute failed: %s", exc)
    return out


# ---------------------------------------------------------------------------
# Density gate (§2.5-7, CCW-R15)
# ---------------------------------------------------------------------------

def _check_density_gate(theme_df: pd.DataFrame, theme: str) -> tuple[bool, str]:
    """Returns (gate_open, reason_string)."""
    if theme_df is None or theme_df.empty:
        return False, "no theme_daily data"
    t = theme_df[theme_df["theme"] == theme].copy()
    if t.empty:
        return False, "theme not in theme_daily"
    t = t.sort_values("as_of")
    if len(t) < _DENSITY_ROLL:
        return False, f"fewer than {_DENSITY_ROLL} dates in theme_daily (accruing)"

    # Rolling 21d check on latest window
    recent = t.tail(_DENSITY_ROLL)
    avg_n_bonds = recent["n_bonds"].mean() if "n_bonds" in recent.columns else 0.0
    avg_match_ratio = (
        (recent["matched_n"] / recent["n_bonds"].replace(0, np.nan)).mean()
        if "matched_n" in recent.columns and "n_bonds" in recent.columns
        else 0.0
    )

    if avg_n_bonds < _DENSITY_N_MIN:
        return False, f"avg n_bonds {avg_n_bonds:.1f} < {_DENSITY_N_MIN} (density gate: too few bonds)"
    if round(avg_match_ratio, 9) < _DENSITY_MATCH_RATIO:
        return False, f"avg match ratio {avg_match_ratio:.2f} < {_DENSITY_MATCH_RATIO} (density gate: too few repricing bonds)"
    return True, "density gate open"


# ---------------------------------------------------------------------------
# Per-series state builder
# ---------------------------------------------------------------------------

def _build_series_state(
    series_id: str,
    series: pd.Series | None,
    orientation: str = "price",   # 'spread' or 'price'
    accruing_note: str | None = None,
    composition_mask: pd.Series | None = None,
    all_events: list | None = None,
    _return_raw_grids: bool = False,
    sanity_verdict: str | None = None,
) -> dict | tuple[dict, dict]:
    """Build a complete state dict for one series.

    If _return_raw_grids=True, returns (state_dict, {grid_label: raw_gd}) so the
    caller can thread raw grid dicts into K-of-N tag computation (Fix 5 — theme_stress
    unreachable legs 2/3 needed actual gd, not snapshot dicts).

    Fix 7: composition_change mask is applied to the series BEFORE grid computation,
    so cross emission is suppressed on composition bars.
    """
    raw_grids: dict = {}

    if series is None or len(series) < 5:
        out = {
            "series_id": series_id,
            "orientation": orientation,
            "level": None,
            "d1": None,
            "d21": None,
            "velocity": {},
            "grids": {},
            "state": "accruing",
            "accruing_note": accruing_note or "series not available",
        }
        return (out, raw_grids) if _return_raw_grids else out

    s = series.dropna().astype(float).sort_index()

    # Fix 7: apply composition_change mask BEFORE grid computation (suppresses cross
    # emission on composition bars, not just velocity). Mask is already applied inside
    # _compute_velocity; we also apply it to the series fed to the grid.
    s_for_grid = s
    if composition_mask is not None:
        mask_aligned = composition_mask.reindex(s.index).fillna(False).astype(bool)
        s_for_grid = s.where(~mask_aligned)

    level = float(s.iloc[-1]) if not s.empty else None
    d1    = float(s.diff(1).iloc[-1]) if len(s) >= 2 else None
    d21   = float(s.diff(21).iloc[-1]) if len(s) >= 22 else None

    vel = _compute_velocity(s, composition_mask=composition_mask)
    grids_out: dict = {}

    for (gl, n_sess, rule) in _GRIDS:
        # Use composition-masked series for grid (Fix 7)
        gd = _compute_grid_data(s_for_grid, gl, n_sess, rule)
        if gd is None:
            grids_out[gl] = None
            raw_grids[gl] = None
            continue
        raw_grids[gl] = gd
        snap = _grid_snapshot(gd)
        # For spread series, crosses are flagged secondary
        if all_events is not None:
            evts = _extract_cross_events(series_id, gl, gd, orientation=orientation,
                                          sanity_verdict=sanity_verdict)
            all_events.extend(evts)
        snap["secondary_note"] = ("oscillator crosses secondary — velocity-pctile is primary"
                                  if orientation == "spread" else None)
        grids_out[gl] = snap

    # State classification (plain-word)
    vel21_p = vel.get("vel21_pctile")
    if orientation == "spread":
        if vel21_p is not None and vel21_p >= _VEL_PCTILE_STRESS:
            state = "widening_stress"
        elif vel21_p is not None and vel21_p >= 65:
            state = "widening"
        elif vel21_p is not None and vel21_p <= 35:
            state = "tightening"
        else:
            state = "stable" if vel21_p is not None else "accruing"
    else:
        state = "accruing" if vel21_p is None else "active"

    out: dict = {
        "series_id":     series_id,
        "orientation":   orientation,
        "severity_note": ("spread: widening = deterioration" if orientation == "spread" else None),
        "level":         round(level, 4) if level is not None else None,
        "d1":            round(d1, 4) if d1 is not None else None,
        "d21":           round(d21, 4) if d21 is not None else None,
        "velocity":      vel,
        "grids":         grids_out,
        "state":         state,
    }
    if accruing_note:
        out["accruing_note"] = accruing_note
    return (out, raw_grids) if _return_raw_grids else out


# ---------------------------------------------------------------------------
# Velocity-threshold forward ledger event
# ---------------------------------------------------------------------------

def _make_ledger_event(
    series_id: str,
    event_type: str,   # 'velocity_threshold', 'tag_fire'   (oscillator_cross excluded per Fix 3)
    as_of: date,
    payload: dict,
    registered_at: str | None = None,
) -> dict:
    """Build one forward-ledger row (keep-FIRST contract).

    Fix 3 (CCW review): ledger emits ONLY velocity_threshold and tag_fire events.
    Oscillator crosses are excluded (failed episode discrimination per sanity study,
    and the 12.8k backfilled cross rows violated truth-schema).
    registered_at stamps the run date; source='live' marks this is a current event.
    """
    import datetime as _dt
    _registered_at = registered_at or str(_dt.date.today())
    # Stable event_id: deterministic per (series, type, date)
    event_id = f"ccw:{event_type}:{series_id}:{as_of}"
    return {
        "event_id":        event_id,
        "series_id":       series_id,
        "event_type":      event_type,
        "as_of":           str(as_of),
        "registered_at":   _registered_at,
        "source":          "live",
        "ruler_h_primary": _FWD_H_PRIMARY,
        "ruler_h_secondary": _FWD_H_SECONDARY,
        # Graded fields (stamped null at emission; filled by future grader)
        "graded_at":             None,
        "direction_hit_h_primary": None,
        "direction_hit_h_secondary": None,
        "delta_bp_h_primary":    None,
        "equity_twin_h_primary": None,
        **payload,
    }


def _upsert_forward_log(new_events: list[dict], root: Path) -> int:
    """Append to data/corp_bonds/forward_log.jsonl, keep-FIRST per event_id.

    Fix 3 (CCW review):
      - Nightly-lane only: guarded by COLLECT_LANE=='nightly' env var (mirrors
        engine/ownership_ledger.py:79-82). Intraday/test runs return 0 without writing.
      - Only emits events whose as_of == today (current-bar-only, no historical backfill).
      - Oscillator crosses are NOT written here (excluded from ledger per Fix 3).

    Returns number of new rows written (0 if not in nightly lane).
    """
    import datetime as _dt

    # COLLECT_LANE guard: nightly lane only
    collect_lane = os.environ.get("COLLECT_LANE", "")
    if collect_lane != "nightly":
        log.debug("credit_momentum: forward_log write skipped (COLLECT_LANE=%r, want 'nightly')", collect_lane)
        return 0

    path = root / "corp_bonds" / "forward_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Filter to current-bar-only: as_of must be today
    today_str = str(_dt.date.today())
    current_events = [ev for ev in new_events if str(ev.get("as_of", "")) == today_str]

    if not current_events:
        return 0

    # Load existing
    existing: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    ev = json.loads(line)
                    eid = ev.get("event_id")
                    if eid:
                        existing[eid] = ev
                except json.JSONDecodeError:
                    pass

    n_new = 0
    for ev in current_events:
        eid = ev.get("event_id")
        if eid and eid not in existing:
            existing[eid] = ev
            n_new += 1

    # Write back (all events, sorted by as_of)
    all_events_sorted = sorted(existing.values(), key=lambda e: e.get("as_of", ""))
    with open(path, "w") as fh:
        for ev in all_events_sorted:
            fh.write(json.dumps(ev, default=str) + "\n")

    return n_new


# ---------------------------------------------------------------------------
# Credit-vs-equity divergence
# ---------------------------------------------------------------------------

def _compute_divergence_quadrant(
    theme: str,
    theme_df: pd.DataFrame,
    registry: dict,
    root: Path,
) -> dict:
    """Compute 21d credit-spread direction vs equity-return direction.

    Quadrants:
      risk_formation: equity UP, credit WIDENING (deterioration)
      converging_good: equity UP, credit TIGHTENING
      converging_bad: equity DOWN, credit WIDENING
      neutral: equity DOWN, credit TIGHTENING
      accruing: insufficient data

    CCW-R13: spread orientation = widening = deterioration.
    """
    result = {
        "theme": theme,
        "quadrant": "accruing",
        "credit_d21_bp": None,
        "equity_return_21d": None,
        "n_equity_tickers": 0,
        "note": "accruing — insufficient history",
    }

    # Get theme spread series from theme_daily
    t_sub = theme_df[theme_df["theme"] == theme].sort_values("as_of") if not theme_df.empty else pd.DataFrame()
    if t_sub.empty or len(t_sub) < 22:
        result["note"] = "accruing — fewer than 22 theme_daily dates"
        return result

    # Credit d21: use matched d1 cumulated over 21 dates OR direct spread diff
    if "g_spread_bp_pw" in t_sub.columns:
        spread_s = t_sub.set_index("as_of")["g_spread_bp_pw"].dropna()
        if len(spread_s) >= 22:
            credit_d21 = float(spread_s.iloc[-1] - spread_s.iloc[-22]) if len(spread_s) >= 22 else None
        else:
            credit_d21 = None
    else:
        credit_d21 = None

    result["credit_d21_bp"] = round(credit_d21, 2) if credit_d21 is not None else None

    # Equity tickers for this theme
    themes_map = registry.get("themes", {})
    theme_data = themes_map.get(theme, {})
    eq_tickers = [idata.get("equity_ticker") for _, idata in theme_data.get("issuers", {}).items()
                  if idata.get("equity_ticker")]
    result["n_equity_tickers"] = len(eq_tickers)

    if not eq_tickers:
        result["note"] = "accruing — no equity tickers in registry"
        return result

    # Equal-weight equity return over 21d
    returns_21d = []
    for tk in eq_tickers:
        s = _load_equity_close(tk, root)
        if s is not None and len(s) >= 22:
            ret = float(s.iloc[-1] / s.iloc[-22] - 1.0)
            returns_21d.append(ret)

    if not returns_21d:
        result["note"] = "accruing — equity closes not available"
        return result

    eq_ret_21d = float(np.mean(returns_21d))
    result["equity_return_21d"] = round(eq_ret_21d * 100.0, 2)  # in percent

    # Classify quadrant
    if credit_d21 is not None:
        credit_widening = credit_d21 > 0
        equity_up = eq_ret_21d > 0
        if equity_up and credit_widening:
            result["quadrant"] = "risk_formation"
        elif equity_up and not credit_widening:
            result["quadrant"] = "converging_good"
        elif not equity_up and credit_widening:
            result["quadrant"] = "converging_bad"
        else:
            result["quadrant"] = "neutral"
        result["note"] = None
    else:
        result["note"] = "accruing — credit spread history insufficient"

    return result


# ---------------------------------------------------------------------------
# ORCL named series (fallen-angel watch)
# ---------------------------------------------------------------------------

def _build_orcl_watch(panel: pd.DataFrame, root: Path) -> dict:
    """ORCL par-weighted g-spread minus matched-maturity IG peer median.

    SPEC DEVIATION (documented): masterplan §3-P5 specified BBB-median as the
    comparison, but the panel carries no per-bond ratings; the peer group is
    the full IG-segment bond panel at matched maturity bucket. Deferred until
    a ratings source lands. Disclosed here and in the final report.
    """
    result = {
        "issuer": "ORCL",
        "g_spread_bp_pw": None,
        "ig_peer_median_bp": None,
        "premium_vs_ig_peers_bp": None,
        "peer_group": "IG-segment bonds at matched maturity bucket (no per-bond ratings available; BBB-median deferred)",
        "note": "accruing",
    }

    if panel.empty or "issuer" not in panel.columns:
        return result

    orcl = panel[panel["issuer"].str.upper() == "ORCL"] if "issuer" in panel.columns else pd.DataFrame()
    if orcl.empty:
        # Try cusip6 prefix approach via registry — but just report accruing
        result["note"] = "ORCL bonds not matched in panel (accruing)"
        return result

    ig_panel = panel[panel["segment"] == "ig"] if "segment" in panel.columns else panel
    if ig_panel.empty:
        result["note"] = "IG panel empty"
        return result

    # ORCL par-weighted g-spread
    orcl_valid = orcl.dropna(subset=["g_spread_bp", "par"]) if "g_spread_bp" in orcl.columns else pd.DataFrame()
    if not orcl_valid.empty:
        orcl_gspread = float((orcl_valid["g_spread_bp"] * orcl_valid["par"]).sum() / orcl_valid["par"].sum())
        result["g_spread_bp_pw"] = round(orcl_gspread, 2)

        # Matched-maturity IG peer median (WAM bucket matching)
        orcl_wam = float((orcl_valid["tenor_yrs"] * orcl_valid["par"]).sum() / orcl_valid["par"].sum()) if "tenor_yrs" in orcl_valid.columns else None
        if orcl_wam is not None and "tenor_yrs" in ig_panel.columns:
            # Match within ±3y WAM window
            lo, hi = orcl_wam - 3.0, orcl_wam + 3.0
            peers = ig_panel[
                (ig_panel["tenor_yrs"] >= lo) &
                (ig_panel["tenor_yrs"] <= hi) &
                ig_panel["g_spread_bp"].notna()
            ]
            if not peers.empty and len(peers) >= 3:
                peer_med = float(peers["g_spread_bp"].median())
                result["ig_peer_median_bp"] = round(peer_med, 2)
                result["premium_vs_ig_peers_bp"] = round(orcl_gspread - peer_med, 2)
                result["note"] = "live — labeled vs IG peers at matched maturity"
            else:
                result["note"] = "accruing — insufficient IG peers at matched maturity"
        else:
            result["note"] = "accruing — no tenor data"
    else:
        result["note"] = "accruing — ORCL g-spread not yet computed"

    return result


# ---------------------------------------------------------------------------
# Fallen-angel / new-issuance watch
# ---------------------------------------------------------------------------

def _build_transition_watch(root: Path) -> dict:
    """Detect ISIN fund migrations (IG → HY or HY → IG) across holdings snapshots."""
    result = {
        "n_snapshots": 0,
        "fallen_angel_candidates": [],
        "rising_star_candidates": [],
        "new_issuance_events": [],
        "note": "accruing",
    }

    holdings_dir = root / "corp_bonds" / "holdings"
    if not holdings_dir.exists():
        return result

    # Collect all (date, fund, isin) triples
    ig_funds = {"SPSB", "SPIB", "SPLB"}
    hy_funds = {"JNK", "SPHY"}

    fund_isin_dates: dict[str, set] = {}  # isin -> set of date strings when in IG
    hy_isin_dates: dict[str, set] = {}
    all_dates: list[str] = []
    isin_issuer: dict[str, str] = {}

    for fund in list(ig_funds) + list(hy_funds):
        fund_dir = holdings_dir / fund
        if not fund_dir.exists():
            continue
        for p in sorted(fund_dir.glob("*.parquet")):
            dt_str = p.stem
            all_dates.append(dt_str)
            try:
                df = pd.read_parquet(p)
                if "isin" not in df.columns:
                    continue
                for _, row in df.iterrows():
                    isin = str(row.get("isin", ""))
                    if not isin:
                        continue
                    name = str(row.get("name", ""))
                    isin_issuer[isin] = name
                    if fund in ig_funds:
                        fund_isin_dates.setdefault(isin, set()).add(dt_str)
                    elif fund in hy_funds:
                        hy_isin_dates.setdefault(isin, set()).add(dt_str)
            except Exception as exc:  # noqa: BLE001
                log.debug("credit_momentum: transition_watch %s %s: %s", fund, p.stem, exc)

    unique_dates = sorted(set(all_dates))
    result["n_snapshots"] = len(unique_dates)

    if len(unique_dates) < 2:
        result["note"] = "accruing — fewer than 2 holdings snapshots (need ≥2 to detect transitions)"
        return result

    # Fallen-angel candidates: appeared in IG funds, then later only in HY funds
    for isin, ig_dates in fund_isin_dates.items():
        hy_dates = hy_isin_dates.get(isin, set())
        if hy_dates:
            last_ig = max(ig_dates)
            first_hy = min(hy_dates)
            if first_hy > last_ig:
                result["fallen_angel_candidates"].append({
                    "isin": isin,
                    "name": isin_issuer.get(isin, ""),
                    "last_ig_date": last_ig,
                    "first_hy_date": first_hy,
                })

    # Rising-star candidates: appeared in HY funds, then later only in IG funds
    for isin, hy_dates in hy_isin_dates.items():
        ig_dates = fund_isin_dates.get(isin, set())
        if ig_dates:
            last_hy = max(hy_dates)
            first_ig = min(ig_dates)
            if first_ig > last_hy:
                result["rising_star_candidates"].append({
                    "isin": isin,
                    "name": isin_issuer.get(isin, ""),
                    "last_hy_date": last_hy,
                    "first_ig_date": first_ig,
                })

    # New-issuance: ISINs appearing in the latest snapshot not in prior snapshots
    if len(unique_dates) >= 2:
        latest = unique_dates[-1]
        prior  = unique_dates[-2]
        latest_isins: set = set()
        prior_isins:  set = set()
        for fund in list(ig_funds) + list(hy_funds):
            for dt, target in [(latest, latest_isins), (prior, prior_isins)]:
                p = holdings_dir / fund / f"{dt}.parquet"
                if p.exists():
                    try:
                        df = pd.read_parquet(p)
                        if "isin" in df.columns:
                            target.update(df["isin"].dropna().tolist())
                    except Exception:  # noqa: BLE001
                        pass
        new_isins = latest_isins - prior_isins
        if new_isins:
            result["new_issuance_events"].append({
                "date": latest,
                "n_new_isins": len(new_isins),
                "note": "new ISINs entering panel — potential new issuance",
            })

    result["note"] = "live" if len(unique_dates) >= 2 else "accruing"
    return result


# ---------------------------------------------------------------------------
# Interim T-bond block (R6: no yield_momentum.v1 yet)
# ---------------------------------------------------------------------------

def _build_interim_tlt(root: Path, all_events: list) -> dict:
    """Interim TLT/IEF ETF-price momentum block (R6 gate — removed when RIC ships)."""
    result = {
        "_label": _INTERIM_LABEL,
        "TLT": None,
        "IEF": None,
    }
    for ticker in ["TLT", "IEF"]:
        s = _load_yahoo_close(ticker, root)
        if s is None:
            result[ticker] = {"state": "accruing", "note": "data not available"}
            continue
        state = _build_series_state(
            f"interim_{ticker}",
            s,
            orientation="price",
            accruing_note=None,
            all_events=all_events,
        )
        result[ticker] = state
    return result


# ---------------------------------------------------------------------------
# K-of-N confluence tags
# ---------------------------------------------------------------------------

def _compute_credit_market_turn_tag(
    hy_oas_vel: dict,
    quality_spread_vel: dict,
    ccc_bb_vel: dict,
) -> dict:
    """credit_market_turn: >= 2 of:
      1. broad HY vel21_pctile >= 85
      2. quality_spread (HY-IG) widening over 21d (vel21 > 0)
      3. ccc_bb differential widening over 21d (vel21 > 0)
    """
    leg1 = (hy_oas_vel.get("vel21_pctile") or 0.0) >= _VEL_PCTILE_STRESS
    leg2 = (quality_spread_vel.get("vel21") or 0.0) > 0
    leg3 = (ccc_bb_vel.get("vel21") or 0.0) > 0
    score = int(leg1) + int(leg2) + int(leg3)
    fired = score >= 2
    return {
        "tag": "credit_market_turn",
        "fired": fired,
        "score": score,
        "legs": {
            "hy_vel21_pctile_ge85": leg1,
            "quality_spread_widening_21d": leg2,
            "ccc_bb_widening_21d": leg3,
        },
        "track_record_note": _TAG_NO_RECORD,
    }


def _compute_credit_theme_stress_tag(
    theme: str,
    vel_state: dict,
    gd_3b: dict | None,
    theme_price_3b_gd: dict | None,
    series_as_of: pd.Timestamp | None = None,
) -> dict:
    """credit_theme_stress for one theme: >= 2 of:
      1. vel21_pctile >= 85
      2. 3B BULL cross on spread (SEVERITY INVERSION, Fix 2: bull = spread widening = deterioration)
      3. theme price 3B BEAR cross (price down = deterioration)

    Leg 2 fires on BULL cross (not bear) because on spread series the RSI-MACD
    bull_cross means spread momentum is UP = widening = stress. Verified: mean d1 at
    bull cross ≈ +0.071 bp on HY OAS (CCW review Fix 2).

    as_of is used instead of pd.Timestamp.now() (Fix 2 + Fix 5 — series-time, not wall clock).
    """
    leg1 = (vel_state.get("vel21_pctile") or 0.0) >= _VEL_PCTILE_STRESS
    # Leg2: 3B BULL cross on SPREAD (bull = widening = deterioration; Fix 2)
    # gd_3b is the raw grid dict (contains 'bull_cross' pd.Series), not a snapshot
    leg2 = False
    if gd_3b is not None:
        bull_crosses = gd_3b.get("bull_cross")
        if bull_crosses is not None and hasattr(bull_crosses, '__len__') and len(bull_crosses) > 0:
            recent_fire = bull_crosses[bull_crosses]
            if len(recent_fire) > 0:
                ref_ts = series_as_of if series_as_of is not None else recent_fire.index[-1]
                leg2 = (ref_ts - recent_fire.index[-1]).days <= 30
    # Leg3: theme price 3B BEAR cross (price momentum down = stress)
    # theme_price_3b_gd is the raw grid dict for the price series
    leg3 = False
    if theme_price_3b_gd is not None:
        bear_crosses_p = theme_price_3b_gd.get("bear_cross")
        if bear_crosses_p is not None and hasattr(bear_crosses_p, '__len__') and len(bear_crosses_p) > 0:
            recent_fire_p = bear_crosses_p[bear_crosses_p]
            if len(recent_fire_p) > 0:
                ref_ts = series_as_of if series_as_of is not None else recent_fire_p.index[-1]
                leg3 = (ref_ts - recent_fire_p.index[-1]).days <= 30
    score = int(leg1) + int(leg2) + int(leg3)
    fired = score >= 2
    return {
        "tag": "credit_theme_stress",
        "theme": theme,
        "fired": fired,
        "score": score,
        "legs": {
            "vel21_pctile_ge85": leg1,
            # Leg 2: bull cross on spread = widening (Fix 2: inverted vs price semantics)
            "spread_3b_bull_cross_widening_secondary": leg2,
            "price_3b_bear_cross": leg3,
        },
        "track_record_note": _TAG_NO_RECORD,
    }


# ---------------------------------------------------------------------------
# FINRA breadth (from data/corp_bonds/)
# ---------------------------------------------------------------------------

def _load_finra_breadth(root: Path) -> dict:
    """Load and process FINRA breadth and sentiment data.

    Source label: 'FINRA trade data' — NEVER blended with own-store numbers (CCW-R14).

    productCategory in breadth: 'all securities' / 'investment grade' / 'high yield' / 'convertibles'
    productCategory in sentiment: 'customer buy' / 'customer sell' / ...  (NOT the grade dimension)
    tradeType in sentiment: 'investment grade' / 'high yield' / ... (grade dimension)
    """
    result: dict = {
        "_source": "FINRA trade data",
        "_note": "CCW-R14: never blended with own-store numbers; distinctly labeled",
        "breadth": {},
        "sentiment": {},
        "n_days_breadth": 0,
    }

    breadth_path = root / "corp_bonds" / "finra_corporateMarketBreadth.parquet"
    sentiment_path = root / "corp_bonds" / "finra_corporateMarketSentiment.parquet"

    # --- Breadth ---
    if breadth_path.exists():
        try:
            bdf = pd.read_parquet(breadth_path)
            if "tradeReportDate" in bdf.columns:
                bdf["tradeReportDate"] = pd.to_datetime(bdf["tradeReportDate"])
                bdf = bdf.sort_values("tradeReportDate")

            for cat in ["all securities", "investment grade", "high yield", "convertibles"]:
                sub = bdf[bdf["productCategory"] == cat].copy() if "productCategory" in bdf.columns else pd.DataFrame()
                if sub.empty:
                    result["breadth"][cat] = {"state": "no_data"}
                    continue
                sub = sub.sort_values("tradeReportDate").set_index("tradeReportDate")

                # Advance share = advances / (advances + declines)
                adv = sub["advances"].astype(float)
                dec = sub["declines"].astype(float)
                denom = (adv + dec).replace(0, np.nan)
                adv_share = adv / denom  # 0..1

                # 5d smoothed
                adv_share_5d = adv_share.rolling(5, min_periods=1).mean()

                # Velocity / percentile on smoothed advance share
                vel_state = _compute_velocity(adv_share_5d)

                # 52wk high/low net share
                wk_high_net = None
                if "fiftyTwoWeekHigh" in sub.columns and "fiftyTwoWeekLow" in sub.columns:
                    wk_high = sub["fiftyTwoWeekHigh"].astype(float)
                    wk_low  = sub["fiftyTwoWeekLow"].astype(float)
                    total   = sub["totalTrades"].astype(float)
                    wk_high_net_s = (wk_high - wk_low) / total.replace(0, np.nan)
                    wk_high_net = float(wk_high_net_s.iloc[-1]) if not wk_high_net_s.empty else None

                # Canon momentum on smoothed advance share (D grid only — 751 days = lawful)
                adv_grid = _compute_grid_data(adv_share_5d, "1D", 1, None)
                adv_grid_snap = _grid_snapshot(adv_grid) if adv_grid is not None else None

                result["breadth"][cat] = {
                    "advance_share_latest":     float(adv_share.iloc[-1]) if not adv_share.empty else None,
                    "advance_share_5d_ma":      float(adv_share_5d.iloc[-1]) if not adv_share_5d.empty else None,
                    "vel21_advance_share":      vel_state.get("vel21"),
                    "vel21_pctile_advance_share": vel_state.get("vel21_pctile"),
                    "wk52_high_low_net_share":  round(wk_high_net, 4) if wk_high_net is not None else None,
                    "n_days":                   len(sub),
                    "latest_date":              str(sub.index[-1].date()) if not sub.empty else None,
                    "momentum_1d":              adv_grid_snap,
                }
                if cat == "all securities":
                    result["n_days_breadth"] = len(sub)

        except Exception as exc:  # noqa: BLE001
            log.warning("credit_momentum: FINRA breadth load failed: %s", exc)

    # --- Sentiment (buy/sell imbalance) ---
    # CRITICAL: buy/sell LIVES in productCategory; tradeType is the GRADE dimension
    if sentiment_path.exists():
        try:
            sdf = pd.read_parquet(sentiment_path)
            if "tradeReportDate" in sdf.columns:
                sdf["tradeReportDate"] = pd.to_datetime(sdf["tradeReportDate"])
                sdf = sdf.sort_values("tradeReportDate")

            for grade in ["investment grade", "high yield", "all securities"]:
                grade_sub = sdf[sdf["tradeType"] == grade].copy() if "tradeType" in sdf.columns else pd.DataFrame()
                if grade_sub.empty:
                    result["sentiment"][grade] = {"state": "no_data"}
                    continue

                # Pivot productCategory: buy/sell volume ratio
                buy_sub  = grade_sub[grade_sub["productCategory"] == "customer buy"]
                sell_sub = grade_sub[grade_sub["productCategory"] == "customer sell"]

                if buy_sub.empty or sell_sub.empty:
                    result["sentiment"][grade] = {"state": "no_buy_sell_data"}
                    continue

                buy_vol  = buy_sub.set_index("tradeReportDate")["totalVolume"].astype(float)
                sell_vol = sell_sub.set_index("tradeReportDate")["totalVolume"].astype(float)

                # Align
                common = buy_vol.index.intersection(sell_vol.index)
                if len(common) < 5:
                    result["sentiment"][grade] = {"state": "insufficient_data"}
                    continue

                buy_v  = buy_vol.reindex(common)
                sell_v = sell_vol.reindex(common)
                ratio  = buy_v / sell_v.replace(0, np.nan)   # >1 = net buyer, <1 = net seller

                ratio_5d = ratio.rolling(5, min_periods=1).mean()
                latest_ratio = float(ratio.iloc[-1]) if not ratio.empty else None

                result["sentiment"][grade] = {
                    "buy_sell_ratio_latest": round(latest_ratio, 4) if latest_ratio is not None else None,
                    "buy_sell_ratio_5d_ma":  round(float(ratio_5d.iloc[-1]), 4) if not ratio_5d.empty else None,
                    "buy_vol_latest":        float(buy_v.iloc[-1]) if not buy_v.empty else None,
                    "sell_vol_latest":       float(sell_v.iloc[-1]) if not sell_v.empty else None,
                    "n_days":                len(common),
                    "latest_date":           str(common[-1].date()) if len(common) > 0 else None,
                    "_note": (
                        "ratio>1 = customer net buyer; "
                        "productCategory carries buy/sell; tradeType carries grade (CCW-W5 FINRA schema)"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            log.warning("credit_momentum: FINRA sentiment load failed: %s", exc)

    return result


# ---------------------------------------------------------------------------
# Own-store breadth
# ---------------------------------------------------------------------------

def _build_own_store_breadth(root: Path) -> dict:
    """Compute breadth from own holdings store.

    With only ~1-2 snapshots, emits machinery + accruing nulls.
    Advancing/declining = bond price up/down from prior snapshot.
    """
    result: dict = {
        "_source": "own-store holdings (SPSB/SPIB/SPLB/JNK/SPHY)",
        "n_snapshots": 0,
        "ig": {"state": "accruing"},
        "hy": {"state": "accruing"},
        "all": {"state": "accruing"},
        "note": "accruing — fewer than 2 snapshots",
    }

    holdings_dir = root / "corp_bonds" / "holdings"
    if not holdings_dir.exists():
        return result

    ig_funds = {"SPSB", "SPIB", "SPLB"}
    hy_funds = {"JNK", "SPHY"}

    # Collect snapshots by date
    by_date: dict[str, list] = {}
    for fund in sorted(list(ig_funds) + list(hy_funds)):
        fund_dir = holdings_dir / fund
        if not fund_dir.exists():
            continue
        for p in sorted(fund_dir.glob("*.parquet")):
            dt = p.stem
            try:
                df = pd.read_parquet(p)
                if df.empty:
                    continue
                df["_fund"] = fund
                df["_segment"] = "ig" if fund in ig_funds else "hy"
                by_date.setdefault(dt, []).append(df)
            except Exception as exc:  # noqa: BLE001
                log.debug("credit_momentum: own breadth load %s %s: %s", fund, dt, exc)

    sorted_dates = sorted(by_date.keys())
    result["n_snapshots"] = len(sorted_dates)

    if len(sorted_dates) < 2:
        result["note"] = f"accruing — {len(sorted_dates)} snapshot(s); need ≥2 for advancing/declining"
        return result

    # For each consecutive date pair, compute advance/decline share
    adv_records = []
    for i in range(1, len(sorted_dates)):
        d_prev = sorted_dates[i - 1]
        d_curr = sorted_dates[i]
        prev_frames = by_date.get(d_prev, [])
        curr_frames = by_date.get(d_curr, [])
        if not prev_frames or not curr_frames:
            continue
        prev_df = pd.concat(prev_frames, ignore_index=True)
        curr_df = pd.concat(curr_frames, ignore_index=True)

        if "isin" not in prev_df.columns or "isin" not in curr_df.columns:
            continue

        # Matched on ISIN
        prev_idx = prev_df.set_index("isin")
        curr_idx = curr_df.set_index("isin")
        common = prev_idx.index.intersection(curr_idx.index)
        if len(common) == 0:
            continue

        for seg, seg_label in [("ig", "ig"), ("hy", "hy"), (None, "all")]:
            if seg:
                p_seg = prev_idx[prev_idx.get("_segment") == seg] if "_segment" in prev_idx.columns else prev_idx
                c_seg = curr_idx[curr_idx.get("_segment") == seg] if "_segment" in curr_idx.columns else curr_idx
                common_seg = p_seg.index.intersection(c_seg.index)
            else:
                p_seg = prev_idx
                c_seg = curr_idx
                common_seg = common

            if len(common_seg) == 0:
                continue

            # Price change: use price_clean if available
            price_col = "price_clean" if "price_clean" in p_seg.columns else (
                "market_value" if "market_value" in p_seg.columns else None
            )
            if price_col is None:
                continue
            p_price = p_seg[price_col].reindex(common_seg).astype(float)
            c_price = c_seg[price_col].reindex(common_seg).astype(float)
            delta   = c_price - p_price
            n_adv = int((delta > 0).sum())
            n_dec = int((delta < 0).sum())
            n_tot = int(delta.notna().sum())
            adv_share = n_adv / n_tot if n_tot > 0 else None

            adv_records.append({
                "date":      d_curr,
                "segment":   seg_label,
                "n_bonds":   n_tot,
                "n_adv":     n_adv,
                "n_dec":     n_dec,
                "adv_share": adv_share,
            })

    if not adv_records:
        result["note"] = "accruing — no matched-panel price deltas computable"
        return result

    adf = pd.DataFrame(adv_records)
    latest_date = sorted_dates[-1]

    for seg_label in ["ig", "hy", "all"]:
        seg_df = adf[adf["segment"] == seg_label].sort_values("date")
        if seg_df.empty:
            result[seg_label] = {"state": "accruing", "n_days": 0}
            continue
        latest = seg_df[seg_df["date"] == latest_date]
        result[seg_label] = {
            "n_days":           len(seg_df),
            "n_bonds_latest":   int(latest["n_bonds"].iloc[0]) if not latest.empty else None,
            "adv_share_latest": float(latest["adv_share"].iloc[0]) if not latest.empty and latest["adv_share"].iloc[0] is not None else None,
            "latest_date":      latest_date,
            "note":             f"accruing ({len(seg_df)} day(s) of history)",
        }

    result["note"] = f"accruing ({len(sorted_dates)} snapshots; {len(adv_records)} advance records)"
    return result


# ---------------------------------------------------------------------------
# Main snapshot() function
# ---------------------------------------------------------------------------

def snapshot(root: str | Path | None = None) -> dict:
    """Build credit_momentum.v1 snapshot.

    Writes:
      data/corp_bonds/credit_momentum.json
      data/corp_bonds/forward_log.jsonl (keep-FIRST events)

    Returns payload dict. Never raises — degrades gracefully on missing inputs.
    """
    t0 = time.time()
    _root = Path(root) if root else _data_root(None)

    all_events: list[dict] = []
    ledger_events: list[dict] = []

    # Load oscillator sanity verdict to embed in cross states (Fix 4)
    _sanity_verdict: str | None = None
    _sanity_path = _root / "corp_bonds" / "oscillator_sanity.json"
    if _sanity_path.exists():
        try:
            _sv = json.loads(_sanity_path.read_text())
            _sanity_verdict = _sv.get("verdict")
        except Exception:  # noqa: BLE001
            pass

    # -----------------------------------------------------------------------
    # A. Load deep-history series (archive-merged)
    # -----------------------------------------------------------------------
    hy_oas  = _load_archive_merged("BAMLH0A0HYM2", "hy_oas",  _root)
    ig_oas  = _load_archive_merged("BAMLC0A0CM",   "ig_oas",  _root)

    # Derived spreads
    quality_spread: pd.Series | None = None
    if hy_oas is not None and ig_oas is not None:
        aligned = pd.concat([hy_oas, ig_oas], axis=1).dropna()
        if not aligned.empty:
            quality_spread = (aligned.iloc[:, 0] - aligned.iloc[:, 1]).rename("quality_spread")

    # Moody's spread
    moodys_spread: pd.Series | None = None
    dbaa = _load_archive_merged("DBAA", "baa_corp", _root)
    daaa = _load_archive_merged("DAAA", "aaa_corp", _root)
    if dbaa is not None and daaa is not None:
        m_aligned = pd.concat([dbaa, daaa], axis=1).dropna()
        if not m_aligned.empty:
            moodys_spread = (m_aligned.iloc[:, 0] - m_aligned.iloc[:, 1]).rename("moodys_spread")

    # CCC-BB spread
    ccc_oas = _load_archive_merged("BAMLH0A3HYC", "ccc_oas", _root)
    bb_oas  = _load_archive_merged("BAMLH0A1HYBB", "bb_oas",  _root)
    ccc_bb: pd.Series | None = None
    if ccc_oas is not None and bb_oas is not None:
        cb_aligned = pd.concat([ccc_oas, bb_oas], axis=1).dropna()
        if not cb_aligned.empty:
            ccc_bb = (cb_aligned.iloc[:, 0] - cb_aligned.iloc[:, 1]).rename("ccc_bb")

    # Ladder buckets (~3y history)
    ladder_map = {
        "aaa_oas": ("BAMLC0A1CAAA", "aaa_oas"),
        "aa_oas":  ("BAMLC0A2CAA",  "aa_oas"),
        "a_oas":   ("BAMLC0A3CA",   "a_oas"),
        "bbb_oas": ("BAMLC0A4CBBB", "bbb_oas"),
        "bb_oas":  ("BAMLH0A1HYBB", "bb_oas"),
        "b_oas":   ("BAMLH0A2HYB",  "b_oas"),
    }
    ladder_series: dict[str, pd.Series | None] = {}
    for alias, (fred_id, col_alias) in ladder_map.items():
        ladder_series[alias] = _load_archive_merged(fred_id, col_alias, _root)

    # ETF prices
    etf_series: dict[str, pd.Series | None] = {}
    for ticker in ["LQD", "HYG", "TLT", "IEF"]:
        etf_series[ticker] = _load_yahoo_close(ticker, _root)
    # JNK if available
    etf_series["JNK"] = _load_yahoo_close("JNK", _root)

    # -----------------------------------------------------------------------
    # B. Build roster states
    # -----------------------------------------------------------------------
    roster: dict[str, dict] = {}

    # Deep-history spread series (PRIMARY = velocity percentile, orientation=spread)
    # Pass sanity_verdict so cross events embed the oscillator study finding (Fix 4)
    for series_id, series in [
        ("hy_oas",        hy_oas),
        ("ig_oas",        ig_oas),
        ("quality_spread", quality_spread),
        ("moodys_spread",  moodys_spread),
        ("ccc_bb",         ccc_bb),
    ]:
        roster[series_id] = _build_series_state(
            series_id, series, orientation="spread",
            all_events=all_events,
            sanity_verdict=_sanity_verdict,
        )

    # Ladder buckets (~3y, daily only until bars accrue)
    for alias in ladder_map:
        s = ladder_series.get(alias)
        n = len(s) if s is not None else 0
        roster[alias] = _build_series_state(
            alias, s, orientation="spread",
            accruing_note=(f"~3y history ({n} days) — 2B/3B/W grids unlock at ~400/600/200 bars" if n < 600 else None),
            all_events=all_events,
        )

    # ETF prices (orientation=price — canon normally)
    for ticker, s in etf_series.items():
        if s is None:
            roster[ticker] = {"series_id": ticker, "state": "accruing", "note": "data not available"}
        else:
            roster[ticker] = _build_series_state(
                ticker, s, orientation="price",
                all_events=all_events,
            )

    # -----------------------------------------------------------------------
    # C. Velocity for tag computation
    # -----------------------------------------------------------------------
    hy_oas_vel = _compute_velocity(hy_oas) if hy_oas is not None else {}
    quality_spread_vel = _compute_velocity(quality_spread) if quality_spread is not None else {}
    ccc_bb_vel = _compute_velocity(ccc_bb) if ccc_bb is not None else {}

    # -----------------------------------------------------------------------
    # D. Theme / market accruing series
    # -----------------------------------------------------------------------
    theme_df   = _load_theme_daily(_root)
    market_df  = _load_market_daily(_root)
    registry   = _load_issuer_registry(_root)
    theme_states: dict[str, dict] = {}
    market_states: dict[str, dict] = {}

    # Market IG/HY from market_daily
    for seg in ["ig", "hy"]:
        m_sub = market_df[market_df["segment"] == seg].copy() if not market_df.empty and "segment" in market_df.columns else pd.DataFrame()
        if not m_sub.empty and "as_of" in m_sub.columns:
            m_sub = m_sub.sort_values("as_of").set_index("as_of")
            if "g_spread_bp_pw" in m_sub.columns:
                s = m_sub["g_spread_bp_pw"].dropna().astype(float)
                n_dates = len(s)
                market_states[seg] = _build_series_state(
                    f"market_{seg}_gspread",
                    s,
                    orientation="spread",
                    accruing_note=f"accruing ({n_dates} dates of history)",
                    all_events=all_events,
                )
            else:
                market_states[seg] = {"state": "accruing", "note": "g_spread_bp_pw not in market_daily"}
        else:
            market_states[seg] = {"state": "accruing", "note": "no market_daily data"}

    # Theme series + density gate
    theme_tags: list[dict] = []
    divergence: list[dict] = []

    if not theme_df.empty:
        themes = theme_df["theme"].unique().tolist() if "theme" in theme_df.columns else []
        for theme in themes:
            t_sub = theme_df[theme_df["theme"] == theme].sort_values("as_of")
            n_dates = len(t_sub)
            gate_open, gate_reason = _check_density_gate(theme_df, theme)

            # Spread series (Fix 5: use _return_raw_grids=True to get raw 3B gd)
            spread_raw_grids: dict = {}
            if "g_spread_bp_pw" in t_sub.columns and "as_of" in t_sub.columns:
                s_spread = t_sub.set_index("as_of")["g_spread_bp_pw"].dropna().astype(float)
                comp_mask = None
                if "composition_change" in t_sub.columns:
                    comp_mask = t_sub.set_index("as_of")["composition_change"].astype(bool)

                _spread_result = _build_series_state(
                    f"theme_{theme}_gspread",
                    s_spread,
                    orientation="spread",
                    accruing_note=(None if gate_open else f"density gate closed: {gate_reason} — velocity only, no oscillator"),
                    composition_mask=comp_mask,
                    all_events=all_events if gate_open else None,  # only emit events when gate open
                    _return_raw_grids=True,
                )
                spread_state, spread_raw_grids = _spread_result
            else:
                spread_state = {"state": "accruing", "note": "no g_spread_bp_pw"}

            # Price series (Fix 5: use _return_raw_grids=True to get raw 3B gd)
            price_raw_grids: dict = {}
            if "price_clean_pw" in t_sub.columns:
                s_price = t_sub.set_index("as_of")["price_clean_pw"].dropna().astype(float)
                _price_result = _build_series_state(
                    f"theme_{theme}_price",
                    s_price,
                    orientation="price",
                    all_events=all_events if gate_open else None,
                    _return_raw_grids=True,
                )
                price_state, price_raw_grids = _price_result
            else:
                price_state = {"state": "accruing", "note": "no price_clean_pw"}

            theme_states[theme] = {
                "theme":        theme,
                "n_dates":      n_dates,
                "density_gate": {"open": gate_open, "reason": gate_reason},
                "spread":       spread_state,
                "price":        price_state,
            }

            # Theme stress tag (density-gated)
            # Fix 5: thread actual 3B raw grid dicts (not None/snapshots).
            # Use series as_of from the spread series (not pd.Timestamp.now()).
            if gate_open:
                vel_state = spread_state.get("velocity", {})
                # 3B raw grid from spread series (bull-cross = widening = deterioration)
                spread_gd_3b = spread_raw_grids.get("3B")
                # 3B raw grid from price series (bear-cross = price down = deterioration)
                price_gd_3b = price_raw_grids.get("3B")
                # Series as_of: latest bar date of the spread series
                _s_idx = spread_state.get("grids", {}).get("3B") or {}
                _as_of_str = _s_idx.get("as_of") if isinstance(_s_idx, dict) else None
                series_as_of = pd.Timestamp(_as_of_str) if _as_of_str else None
                tag = _compute_credit_theme_stress_tag(
                    theme, vel_state, spread_gd_3b, price_gd_3b, series_as_of=series_as_of,
                )
                theme_tags.append(tag)

            # Credit-vs-equity divergence
            div_q = _compute_divergence_quadrant(theme, theme_df, registry, _root)
            divergence.append(div_q)

    # -----------------------------------------------------------------------
    # E. Global credit_market_turn tag
    # -----------------------------------------------------------------------
    market_turn_tag = _compute_credit_market_turn_tag(
        hy_oas_vel, quality_spread_vel, ccc_bb_vel
    )

    # -----------------------------------------------------------------------
    # F. Interim T-bond block (R6: no yield_momentum.v1 yet)
    # -----------------------------------------------------------------------
    interim_tlt = _build_interim_tlt(_root, all_events)

    # -----------------------------------------------------------------------
    # G. FINRA breadth (CCW-R14: distinctly labeled, never blended)
    # -----------------------------------------------------------------------
    finra_breadth = _load_finra_breadth(_root)

    # -----------------------------------------------------------------------
    # H. Own-store breadth
    # -----------------------------------------------------------------------
    own_breadth = _build_own_store_breadth(_root)

    # -----------------------------------------------------------------------
    # I. Fallen-angel watch + ORCL named series
    # -----------------------------------------------------------------------
    transition_watch = _build_transition_watch(_root)
    panel = _load_bond_panel_latest(_root)
    orcl_watch = _build_orcl_watch(panel, _root)

    # -----------------------------------------------------------------------
    # J. Forward ledger events — velocity_threshold + tag_fire ONLY (Fix 3)
    #
    # Ledger emits ONLY:
    #   (a) velocity_threshold: vel21_pctile >= 85 crossing from below, on the latest
    #       bar of the series (current-bar-only, no historical backfill).
    #   (b) tag_fire: credit_market_turn and credit_theme_stress fired.
    #
    # Oscillator crosses are NOT written to the ledger:
    #   - They failed episode discrimination (sanity study; symmetric fire rates).
    #   - The prior 12.8k backfilled cross rows violated truth-schema.
    #   - Crosses remain computed and displayed as secondary context in the JSON.
    #
    # Interim TLT/IEF series NEVER emit ledger events (display only, R6 removability).
    # The COLLECT_LANE guard is enforced inside _upsert_forward_log.
    # -----------------------------------------------------------------------
    today_as_of = date.today()

    # (a) Velocity threshold events — deep-history spread series only
    # (NOT ladder series, NOT ETF prices, NOT interim TLT/IEF, NOT theme series)
    for _sid, _vel in [
        ("hy_oas", hy_oas_vel),
        ("quality_spread", quality_spread_vel),
        ("ccc_bb", ccc_bb_vel),
    ]:
        _p = _vel.get("vel21_pctile")
        if _p is not None and _p >= _VEL_PCTILE_STRESS:
            ledger_events.append(_make_ledger_event(
                _sid, "velocity_threshold", today_as_of,
                {"vel21_pctile": _p, "vel21": _vel.get("vel21"),
                 "orientation": "spread",
                 "note": "spread widening stress velocity threshold (vel21_pctile >= 85)"},
            ))

    # (b) Tag fire events
    if market_turn_tag.get("fired"):
        ledger_events.append(_make_ledger_event(
            "credit_market_turn", "tag_fire", today_as_of,
            {"tag_score": market_turn_tag.get("score"), "legs": market_turn_tag.get("legs", {})},
        ))
    for tt in theme_tags:
        if isinstance(tt, dict) and tt.get("fired"):
            ledger_events.append(_make_ledger_event(
                f"credit_theme_stress:{tt.get('theme', 'unknown')}", "tag_fire", today_as_of,
                {"tag_score": tt.get("score"), "theme": tt.get("theme"),
                 "legs": tt.get("legs", {})},
            ))

    # Oscillator crosses: NOT added to ledger (Fix 3 — excluded from truth-schema)
    # They are available in all_events for display in the JSON roster only.

    # Upsert forward log
    n_new_ledger = 0
    try:
        n_new_ledger = _upsert_forward_log(ledger_events, _root)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: forward_log upsert failed: %s", exc)

    # -----------------------------------------------------------------------
    # K. Ladder snapshot
    # -----------------------------------------------------------------------
    ladder_snapshot = {alias: roster.get(alias, {}) for alias in ladder_map}

    # -----------------------------------------------------------------------
    # L. Assemble payload
    # -----------------------------------------------------------------------
    elapsed = time.time() - t0
    log.info("[timing] credit_momentum.snapshot: %.2fs", elapsed)

    payload: dict[str, Any] = {
        "organ":       "credit_momentum.v1",
        "as_of":       str(date.today()),
        "authority":   dict(AUTHORITY_V1),
        "accruing":    _ACCRUING_NOTE,
        # Oscillator sanity study result (Fix 4 — verdict embedded, crosses carry 'sanity' field)
        "oscillator_sanity": {
            "verdict":  _sanity_verdict,
            "source":   "data/corp_bonds/oscillator_sanity.json",
            "note":     ("DEMOTED or SECONDARY-CONFIRMED per discrimination study. "
                         "Cross states carry 'sanity' field referencing this verdict. "
                         "Crosses are retained as secondary context (1-of-3 in K-of-N tags, "
                         "never sole basis) regardless of verdict — velocity-percentile PRIMARY."),
        },
        # Core spread roster
        "roster": {
            "hy_oas":        roster["hy_oas"],
            "ig_oas":        roster["ig_oas"],
            "quality_spread": roster["quality_spread"],
            "moodys_spread":  roster["moodys_spread"],
            "ccc_bb":         roster["ccc_bb"],
        },
        # ETF price roster
        "etf_prices": {t: roster.get(t, {"state": "accruing"}) for t in ["LQD", "HYG", "TLT", "IEF", "JNK"]},
        # Ladder (3y rolling)
        "ladder":        ladder_snapshot,
        # Accruing theme/market series
        "market":        market_states,
        "themes":        theme_states,
        # Confluence tags
        "tags": {
            "credit_market_turn": market_turn_tag,
            "credit_theme_stress": theme_tags,
        },
        # Interim T-bond block (R6)
        "interim_tlt":   interim_tlt,
        # Breadth (own-store + FINRA — never blended)
        "breadth": {
            "own_store": own_breadth,
            "finra":     finra_breadth,
            "_note": "Two breadth sources; labeled distinctly; NEVER blended (CCW-R14)",
        },
        # Fallen-angel + ORCL
        "watch": {
            "transition":   transition_watch,
            "orcl":         orcl_watch,
        },
        # Credit-vs-equity divergence
        "divergence":    divergence,
        # Metadata
        "_timing_s":     round(elapsed, 2),
        "_n_ledger_new": n_new_ledger,
    }

    # -----------------------------------------------------------------------
    # M. Write JSON
    # -----------------------------------------------------------------------
    out_dir = _root / "corp_bonds"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "credit_momentum.json"
    try:
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("credit_momentum: wrote %s", out_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("credit_momentum: write failed: %s", exc)

    return payload


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="credit_momentum.v1 organ")
    ap.add_argument("--root", default=None, help="data root override")
    args = ap.parse_args()
    result = snapshot(root=args.root)
    print(f"[credit_momentum] as_of={result['as_of']} timing={result['_timing_s']}s "
          f"ledger_new={result['_n_ledger_new']}")
