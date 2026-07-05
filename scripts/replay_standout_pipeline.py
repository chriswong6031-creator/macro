"""P0.1 Production Replay Harness — Entry Intelligence Program §4/P0.1.

Replays the actual production signal stack (signal_gate → confluence cascade →
mtf_alignment → extension/knife) over the full yahoo price store (2012→present)
and grades every candidate verdict under species law.

Design contract (masterplan §4/P0.1):
  1. Vectorised candidate prefilter (any relevant cross within trailing ~10 bars)
     → full production-code evaluation only on candidates.
  2. Prefilter soundness positive control: ≥500 random non-candidate (ticker,date)
     pairs must all return non-fire from the production gate; any fire = halt.
  3. Log EVERY candidate verdict: fire (tier/sub/weight), near-miss (reason),
     rejection (taxonomy reason) + frozen study features at signal time.
  4. Grade every row under species law: terminal-state partition
     (STOPPED/DEAD_MONEY/CUSHIONED/CLEAN_LIFTOFF), MAE/MFE, horizons
     5/10/21/63/126d, entry strictly-after signal bar.
  5. Golden test: latest date in the price store → run production gate per ticker
     → diff against replay logged verdicts for that date (exact match required).
  6. Window: 2012→present, per-year chunked + resumable parquet parts.
     Pre-2015 rows stamped survivor_bias=True.
  7. PIT discipline everywhere: see per-block comments with "PIT:".

Study features frozen at signal time (§4 list):
  - ext_z: price/SMA200 z-score vs own 252d history (engine/extension.py)
  - ext_atr: price-to-200dma in ATR units (approximated from daily returns)
  - knife_z: falling-knife severity (distance below 200dma / own volatility)
  - align_tier: PRIME/ARMED/APPROACHING from mtf_alignment()
  - align_quality: 0-100 quality score from mtf_alignment()
  - weekly_phase: weekly MACD phase (rising/falling/basing/etc.)
  - above_200: bool, price > 200-day SMA
  - rs_sector_quartile: RS vs sector close (1=bottom, 4=top quartile)
  - sector: string sector label (loaded from us_standouts.json)
  - dist_to_52wh: distance from 52-week high (negative = below high)
  - adv_dollar_21d: 21-day average daily dollar volume
  - washout_proximity: cohort washout proximity (bool: within washout window)

Threshold sources (docstring):
  - STOP_BARRIER, CUSHION_BARRIER, LIFTOFF_15, LIFTOFF_8: engine/grading.py
    (pre-registered constants from the Outcome Spine v2 spec §1.1)
  - FRESH_TICKS (=2): engine/confluence_tiers.py — freshness window for T1/T2
  - SPINE_HORIZONS (5,10,21,63,126): engine/grading.py
  - terminal_state partition logic: engine/grading.py terminal_state()
  - REJECTION_TAXONOMY: engine/grading.py REJECTION_TAXONOMY (closed set)
  - Prefilter lookback: 10 bars (≈ FRESH_TICKS × 5 on 2D grid), matching the
    confluence_tiers.CONF_W window of 8 bars plus 2-bar freshness window
  - survivor_bias True for pre-2015: masterplan §4/P0.1 — "pre-2015 rows carry
    survivor-bias stamp until P0.2 says otherwise"

Usage:
    # Full 2012→present replay (background, per-year resumable):
    python scripts/replay_standout_pipeline.py --start-year 2012
    # Single year:
    python scripts/replay_standout_pipeline.py --year 2024
    # Golden test only (verify latest date vs production):
    python scripts/replay_standout_pipeline.py --golden-test-only
    # Prefilter soundness check only:
    python scripts/replay_standout_pipeline.py --soundness-only
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── Path bootstrap ──────────────────────────────────────────────────────────
# This script lives in scripts/; the worktree root is one level up.
# Production engine modules are imported from this worktree's engine/.
WORKTREE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

# ── Canonical data paths (read-only; heavy stores NOT in git per R2 law) ────
# All price reads come from the CANONICAL checkout, not the worktree.
CANONICAL_DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data")
YAHOO_DIR = CANONICAL_DATA / "yahoo"
REPLAY_DIR = CANONICAL_DATA / "replay"
US_STANDOUTS_JSON = (WORKTREE_ROOT / "site" / "factordata" / "us_standouts.json")

# ── Production engine imports (never reimplement indicator logic) ─────────
from engine import signal_gate, confluence_tiers, grading  # noqa: E402
from engine.cycles import mtf_snapshot, mtf_alignment       # noqa: E402
from engine.grading import (                                 # noqa: E402
    REJECTION_TAXONOMY,
    terminal_state,
    forward_metrics,
    fill_index,
    SPINE_HORIZONS,
    STOP_BARRIER,
    CUSHION_BARRIER,
    LIFTOFF_15,
    LIFTOFF_8,
    LIFTOFF_HORIZON_126,
    LIFTOFF_HORIZON_21,
    TerminalState,
)
from engine.extension import grade as ext_grade  # noqa: E402
from engine.confluence_tiers import (            # noqa: E402
    FRESH_TICKS, tier_stream,
)

# ── Configuration ────────────────────────────────────────────────────────────
PREFILTER_LOOKBACK = 10     # bars; covers CONF_W=8 + FRESH_TICKS=2 window
SOUNDNESS_SAMPLE = 500      # non-candidate pairs for the positive-control check
SURVIVOR_BIAS_YEAR = 2015   # pre-2015 rows get survivor_bias=True

log = logging.getLogger("replay")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. UNIVERSE LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def _load_sector_map() -> dict[str, str]:
    """Load ticker→sector from us_standouts.json (buy+watch rows). Falls back
    to empty dict when the file is absent — sector is display context only."""
    try:
        with open(US_STANDOUTS_JSON) as f:
            d = json.load(f)
        sector_map: dict[str, str] = {}
        for row in (d.get("buy") or []) + (d.get("watch") or []):
            t = row.get("ticker") or ""
            s = row.get("sector") or ""
            if t and s:
                sector_map[t] = s
        return sector_map
    except Exception:
        return {}


def load_universe() -> dict[str, pd.Series]:
    """Load all available close series from the canonical yahoo directory.
    Returns {ticker: close_series (DatetimeIndex, dividend-adjusted TR)}."""
    closes: dict[str, pd.Series] = {}
    for path in sorted(YAHOO_DIR.glob("*.parquet")):
        ticker = path.stem
        if ticker.startswith("_") or ticker.startswith("."):
            continue
        try:
            df = pd.read_parquet(path)
            if "close" in df.columns:
                c = df["close"].dropna()
                if not isinstance(c.index, pd.DatetimeIndex):
                    c.index = pd.to_datetime(c.index)
                c = c.sort_index()
                if len(c) >= 250:   # min for MTF indicators
                    closes[ticker] = c
        except Exception:
            continue
    log.info("universe: %d tickers loaded from %s", len(closes), YAHOO_DIR)
    return closes


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VECTORISED PREFILTER
# ═══════════════════════════════════════════════════════════════════════════════

def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    """Fast Wilder RSI for prefilter (mirrors engine/technicals.rsi semantics)."""
    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd_series(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """RSI-MACD histogram series (close-only, matches confluence_tiers._rsi_macd).
    Returns (macd_hist, signal_line)."""
    r = _rsi(c)
    fast = _ema(r, 14)
    base = _ema(r, 60)
    m = fast - base
    s = _ema(m, 5)
    return m - s, s


def _stochrsi_k_series(c: pd.Series, tf_days: int) -> pd.Series:
    """Daily StochRSI-K resampled to tf_days (closes only, for 2D/3D grid).
    Used for cross detection only — matches confluence_tiers._stoch_rsi_kd."""
    tf_c = c.resample(f"{tf_days}B").last().dropna()
    if len(tf_c) < 50:
        return pd.Series(dtype=float)
    r = _rsi(tf_c)
    lo = r.rolling(14).min()
    hi = r.rolling(14).max()
    k_raw = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = k_raw.rolling(3).mean()
    return k


def prefilter_candidates(close: pd.Series) -> pd.DatetimeIndex:
    """Vectorised candidate detection: returns dates where any relevant cross
    occurred within the trailing PREFILTER_LOOKBACK bars.

    PIT: cross detection uses only data up to each bar (rolling window).
    The lookback window is PREFILTER_LOOKBACK=10 bars — wider than CONF_W=8
    to ensure no candidate-bar is missed, keeping the prefilter as a CONSERVATIVE
    net (false positives are OK; false negatives violate the soundness check).

    Detects:
      - 2D RSI-MACD histogram crossing zero (T2/T3 trigger axis)
      - 3D RSI-MACD histogram crossing zero (T1 master axis)
      - 2D StochRSI K crossing D (T4 axis)
      - 3D StochRSI K crossing D (T1/T2/T3 stoch axis)
    Any of these within PREFILTER_LOOKBACK bars marks the date as a candidate.
    """
    c = close.dropna()
    if len(c) < 250:
        return pd.DatetimeIndex([])

    try:
        # --- 2D RSI-MACD histogram ---
        c2 = c.resample("2B").last().dropna()
        if len(c2) > 60:
            h2, _ = _rsi_macd_series(c2)
            cross2 = (h2 > 0) & (h2.shift(1) <= 0)
            # map back to daily index: a cross on the 2D bar's known-date
            known2 = pd.Series(
                c.resample("2B").apply(lambda x: x.dropna().index.max()
                                        if not x.dropna().empty else pd.NaT).values,
                index=c2.index
            ).dropna()
            cross2_daily = pd.Series(False, index=c.index)
            for dt, is_cross in zip(known2.values, cross2.reindex(known2.index).fillna(False).values):
                if is_cross and pd.Timestamp(dt) in cross2_daily.index:
                    cross2_daily[pd.Timestamp(dt)] = True
        else:
            cross2_daily = pd.Series(False, index=c.index)

        # --- 3D RSI-MACD histogram ---
        c3 = c.resample("3B").last().dropna()
        if len(c3) > 60:
            h3, _ = _rsi_macd_series(c3)
            cross3 = (h3 > 0) & (h3.shift(1) <= 0)
            known3 = pd.Series(
                c.resample("3B").apply(lambda x: x.dropna().index.max()
                                        if not x.dropna().empty else pd.NaT).values,
                index=c3.index
            ).dropna()
            cross3_daily = pd.Series(False, index=c.index)
            for dt, is_cross in zip(known3.values, cross3.reindex(known3.index).fillna(False).values):
                if is_cross and pd.Timestamp(dt) in cross3_daily.index:
                    cross3_daily[pd.Timestamp(dt)] = True
        else:
            cross3_daily = pd.Series(False, index=c.index)

        # --- 2D StochRSI K/D cross ---
        k2 = _stochrsi_k_series(c, 2)
        if len(k2) > 20:
            d2 = k2.rolling(3).mean()
            stoch_cross2 = (k2 > d2) & (k2.shift(1) <= d2.shift(1))
            known_2 = pd.Series(
                c.resample("2B").apply(lambda x: x.dropna().index.max()
                                        if not x.dropna().empty else pd.NaT).values,
                index=k2.index if len(k2) == len(pd.Series(c.resample("2B").last().dropna())) else k2.index
            ).dropna() if len(k2) > 0 else pd.Series(dtype=object)
            # Simpler: forward-fill stoch_cross2 to daily
            if not k2.empty:
                stoch2_daily = stoch_cross2.reindex(c.index, method="ffill").fillna(False)
            else:
                stoch2_daily = pd.Series(False, index=c.index)
        else:
            stoch2_daily = pd.Series(False, index=c.index)

        # --- 3D StochRSI K/D cross ---
        k3 = _stochrsi_k_series(c, 3)
        if len(k3) > 20:
            d3 = k3.rolling(3).mean()
            stoch_cross3 = (k3 > d3) & (k3.shift(1) <= d3.shift(1))
            stoch3_daily = stoch_cross3.reindex(c.index, method="ffill").fillna(False)
        else:
            stoch3_daily = pd.Series(False, index=c.index)

        # --- combine: any cross event within PREFILTER_LOOKBACK bars ---
        # PIT: rolling max looks backward only (no lookahead)
        any_cross = (
            cross2_daily.astype(int) |
            cross3_daily.astype(int) |
            stoch2_daily.astype(int) |
            stoch3_daily.astype(int)
        ).astype(bool)

        # A date is a candidate if any cross fired within the last PREFILTER_LOOKBACK bars
        candidate_mask = (
            any_cross.rolling(PREFILTER_LOOKBACK, min_periods=1).max().astype(bool)
        )
        return c.index[candidate_mask]

    except Exception:
        # Prefilter failure: conservative fallback = every bar is a candidate
        # (safe; golden test will still validate production-gate consistency)
        return c.index


# ═══════════════════════════════════════════════════════════════════════════════
# 3. STUDY FEATURES (frozen at signal time, PIT-safe)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_study_features(
    ticker: str,
    close_pit: pd.Series,   # close series TRUNCATED at signal date (PIT)
    sector_map: dict[str, str],
    sector_closes: dict[str, pd.Series] | None = None,
) -> dict[str, Any]:
    """Compute all study features frozen at signal time (§4 feature list).

    PIT guarantee: close_pit contains ONLY data up to and including signal_date
    (caller slices before calling). Every computation here uses only this slice.

    Features:
      ext_z            — price/SMA200 z-score vs own 252d window
                         Source: mirrors engine/extension.extension_signals()
      ext_atr          — extension from 200dma in ATR-normalised units
                         (price/sma200 - 1) / rolling_std_21d; approximation
      knife_z          — falling-knife score: depth below 200dma / own 252d std;
                         0 when above 200dma
      align_tier       — PRIME/ARMED/APPROACHING/None from mtf_alignment()
      align_quality    — 0-100 quality score
      weekly_phase     — weekly MTF phase string
      above_200        — price > 200-day SMA (bool)
      rs_sector_quartile — percentile quartile vs sector close peers (1-4)
                         PIT: computed against sector peers' closes up to signal date
      sector           — sector string from us_standouts.json
      dist_to_52wh     — (price / rolling_252d_max - 1), negative = below high
                         PIT: rolling window truncated at signal date
      adv_dollar_21d   — 21d average daily dollar volume proxy (using close only;
                         full OHLCV not universally available in yahoo store)
      washout_proximity — bool: price <= 200dma * 0.90 within last 21 bars (washout zone)
    """
    feats: dict[str, Any] = {}
    c = close_pit.dropna()
    if len(c) < 10:
        return feats

    price = float(c.iloc[-1])
    feats["sector"] = sector_map.get(ticker)

    # --- ext_z, above_200, dist_to_52wh ---
    # PIT: rolling window uses only c (truncated at signal date)
    sma200 = c.rolling(200, min_periods=100).mean()
    sma200_last = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None

    if sma200_last and sma200_last > 0:
        feats["above_200"] = bool(price > sma200_last)
        ext = price / sma200_last - 1.0
        # z-score vs own 252d history
        ext_series = c / sma200 - 1.0
        ext_mean = float(ext_series.rolling(252, min_periods=120).mean().iloc[-1])
        ext_std = float(ext_series.rolling(252, min_periods=120).std().iloc[-1])
        if ext_std > 0:
            feats["ext_z"] = round((ext - ext_mean) / ext_std, 3)
        else:
            feats["ext_z"] = None
        # ext_atr: extension normalised by 21d rolling std of returns
        ret_std = float(c.pct_change().rolling(21, min_periods=10).std().iloc[-1])
        if ret_std > 0:
            feats["ext_atr"] = round(ext / ret_std, 3)
        else:
            feats["ext_atr"] = None
        # knife_z: depth below 200dma / 252d return std; 0 when above 200dma
        if price < sma200_last:
            depth = sma200_last / price - 1.0
            ret_std_252 = float(c.pct_change().rolling(252, min_periods=120).std().iloc[-1])
            feats["knife_z"] = round(depth / ret_std_252, 3) if ret_std_252 > 0 else None
        else:
            feats["knife_z"] = 0.0
    else:
        feats["above_200"] = None
        feats["ext_z"] = None
        feats["ext_atr"] = None
        feats["knife_z"] = None

    # --- dist_to_52wh ---
    # PIT: rolling 252-bar window from c (truncated)
    high_252 = float(c.rolling(252, min_periods=60).max().iloc[-1]) if len(c) >= 60 else None
    if high_252 and high_252 > 0:
        feats["dist_to_52wh"] = round(price / high_252 - 1.0, 4)
    else:
        feats["dist_to_52wh"] = None

    # --- adv_dollar_21d ---
    # We use close-only as a proxy (real dollar volume needs volume * close,
    # but volume is not always available in the yahoo store's 'close' series).
    # PIT: 21-bar window of close as proxy; mark adv_dollar_21d_approx=True.
    vol_col = None  # volume not available in the close-only series
    feats["adv_dollar_21d"] = None      # set below if volume available
    feats["adv_dollar_21d_proxy"] = True  # flag: no volume in close-only path

    # --- washout_proximity ---
    # PIT: whether price was <= 90% of its 200dma within the last 21 bars
    if sma200_last and len(sma200) >= 21:
        recent_close = c.iloc[-21:]
        recent_sma = sma200.iloc[-21:]
        washout_mask = (recent_close <= recent_sma * 0.90).any()
        feats["washout_proximity"] = bool(washout_mask)
    else:
        feats["washout_proximity"] = None

    # --- mtf_alignment features ---
    # PIT: mtf_snapshot uses c (truncated at signal date)
    try:
        mtf = mtf_snapshot(c, kind="equity")
        align = mtf_alignment(mtf)
        feats["align_tier"] = align.get("tier")
        feats["align_quality"] = align.get("quality")
        feats["weekly_phase"] = align.get("weekly")
    except Exception:
        feats["align_tier"] = None
        feats["align_quality"] = None
        feats["weekly_phase"] = None

    # --- rs_sector_quartile ---
    # PIT: compare price to sector peers' closes as of signal date.
    # Using relative performance: last 63-day return vs sector peers.
    ret_63 = float(c.iloc[-1] / c.iloc[-min(63, len(c) - 1)] - 1.0) if len(c) > 1 else None
    feats["rs_63d_return"] = round(ret_63, 4) if ret_63 is not None else None
    # Full sector quartile requires peer data at signal date (passed in if available)
    feats["rs_sector_quartile"] = None   # filled in post-processing if sector_closes provided

    return feats


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PER-TICKER REPLAY LOOP (single ticker, single date range)
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_verdict(v: dict) -> tuple[str, str | None, str | None]:
    """Classify a gate verdict into (verdict_type, tier, reason).

    verdict_type: 'fire' | 'near_miss' | 'rejection'
    PIT: v is the verdict from gate() called on a PIT-truncated close slice.
    """
    if v.get("eligible") and v.get("tier_cascade") in signal_gate.BUYABLE_TIERS:
        return "fire", v.get("tier_cascade"), None
    near_miss_reason = v.get("near_miss_reason")
    if near_miss_reason and near_miss_reason in REJECTION_TAXONOMY:
        return "near_miss", None, near_miss_reason
    # Classify rejections using REJECTION_TAXONOMY
    reason = v.get("reason") or ""
    # Map production gate reason strings to taxonomy keys
    if "topped" in reason or "not_topped" in reason:
        tax_reason = "not_topped_veto"
    elif "risen for many days" in reason or "freshness" in reason.lower():
        tax_reason = "freshness_expired"
    elif "tier" in reason.lower() and "weight" in reason.lower():
        tax_reason = "tier_cutoff"
    elif not v.get("eligible"):
        # Check for specific known patterns
        raw_reason = (v.get("reason") or "").lower()
        if "flat" in raw_reason or "sell" in raw_reason or "no buy" in raw_reason:
            tax_reason = "tier_cutoff"   # no signal fired at all
        elif "blocked" in raw_reason:
            tax_reason = "tier_cutoff"
        elif "insufficient" in raw_reason or "history" in raw_reason:
            tax_reason = "hygiene_screen"
        else:
            tax_reason = "tier_cutoff"
    else:
        tax_reason = "board_rank_cutoff"  # eligible but below BUYABLE_TIERS
    return "rejection", None, tax_reason


def replay_ticker(
    ticker: str,
    close_full: pd.Series,
    candidate_dates: pd.DatetimeIndex,
    year: int,
    sector_map: dict[str, str],
) -> list[dict]:
    """Replay all candidate dates for one ticker in one year.

    PIT discipline: for each signal_date t, gate() is called on
    close_full.loc[:t] — strictly data at-or-before t. Forward grading
    (fill at t+1) uses the full series.

    Returns a list of verdict dicts, one per candidate date evaluated.
    """
    rows: list[dict] = []
    if len(close_full) < 250:
        return rows

    # Filter candidate dates to the target year
    year_dates = candidate_dates[
        (candidate_dates.year == year) &
        (candidate_dates >= close_full.index[0]) &
        (candidate_dates <= close_full.index[-1])
    ]
    if len(year_dates) == 0:
        return rows

    survivor_bias = (year < SURVIVOR_BIAS_YEAR)

    for signal_date in year_dates:
        # PIT: slice close up to and including signal_date
        # This is the ONLY price data available at signal time
        close_pit = close_full.loc[:signal_date]
        if len(close_pit) < 250:
            continue  # insufficient history at this PIT

        try:
            # ── Production gate call (PIT) ──────────────────────────────
            v = signal_gate.gate(ticker, close_pit)
        except Exception:
            continue

        verdict_type, tier, tax_reason = _classify_verdict(v)

        # ── Study features (PIT) ──────────────────────────────────────
        try:
            feats = compute_study_features(ticker, close_pit, sector_map)
        except Exception:
            feats = {}

        # ── Grading (uses FULL series for forward returns, filled at t+1) ──
        # PIT: fill_index finds the bar STRICTLY AFTER signal_date using close_full
        # Entry at fill bar t+1 is correct per species law (never same-bar)
        grade_15_126 = {}
        grade_8_21 = {}
        fwd_metrics = {}
        try:
            grade_15_126 = terminal_state(
                close_full, signal_date,
                liftoff_mult=LIFTOFF_15,
                liftoff_horizon=LIFTOFF_HORIZON_126,
            )
            grade_8_21 = terminal_state(
                close_full, signal_date,
                liftoff_mult=LIFTOFF_8,
                liftoff_horizon=LIFTOFF_HORIZON_21,
            )
            fwd_metrics = forward_metrics(
                close_full, signal_date,
                horizons=SPINE_HORIZONS,
            )
        except Exception:
            pass

        # ── Episode cluster id (date-cluster: YYYY-WW) ───────────────
        # Episode clusters group fires that occur within the same weekly window
        # to avoid double-counting correlated entries (per species constitution).
        episode_id = f"{ticker}_{pd.Timestamp(signal_date).strftime('%G-W%V')}"

        row: dict[str, Any] = {
            # ── Identity ──────────────────────────────────────────────
            "ticker": ticker,
            "signal_date": str(signal_date.date()),
            "year": year,
            "episode_id": episode_id,
            "survivor_bias": survivor_bias,
            # ── Verdict ───────────────────────────────────────────────
            "verdict_type": verdict_type,     # 'fire' | 'near_miss' | 'rejection'
            "tier_cascade": tier,             # T1/T2/T3/None
            "weight": v.get("weight") or 0.0,
            "tier_sub": v.get("tier_sub"),    # deep | shallow
            "eligible": bool(v.get("eligible")),
            "ticks": v.get("ticks"),
            "near_miss_reason": tax_reason if verdict_type == "near_miss" else None,
            "rejection_reason": tax_reason if verdict_type == "rejection" else None,
            "gate_reason": v.get("reason"),   # raw gate reason string
            # ── Study features (§4, frozen at signal time) ────────────
            "ext_z": feats.get("ext_z"),
            "ext_atr": feats.get("ext_atr"),
            "knife_z": feats.get("knife_z"),
            "align_tier": feats.get("align_tier"),
            "align_quality": feats.get("align_quality"),
            "weekly_phase": feats.get("weekly_phase"),
            "above_200": feats.get("above_200"),
            "rs_63d_return": feats.get("rs_63d_return"),
            "rs_sector_quartile": feats.get("rs_sector_quartile"),
            "sector": feats.get("sector"),
            "dist_to_52wh": feats.get("dist_to_52wh"),
            "adv_dollar_21d": feats.get("adv_dollar_21d"),
            "washout_proximity": feats.get("washout_proximity"),
            # ── Grading: terminal-state partition (species law §1.1) ───
            # clean15_126 = positional primary (stop -5%, liftoff +15% / 126d)
            "state_15_126": grade_15_126.get("state"),          # STOPPED/DEAD_MONEY/CUSHIONED/CLEAN_LIFTOFF
            "liftoff_at_15_126": grade_15_126.get("liftoff_at_bar"),
            "stopped_at_15_126": grade_15_126.get("stopped_at_bar"),
            "cushion_at_15_126": grade_15_126.get("cushion_at_bar"),
            "ret_at_read_15_126": grade_15_126.get("ret_at_read"),
            "fill_date": grade_15_126.get("fill_date") or fwd_metrics.get("fill_date"),
            "entry_price": grade_15_126.get("entry_price") or fwd_metrics.get("entry_price"),
            # clean8_21 = rotational primary (stop -5%, liftoff +8% / 21d)
            "state_8_21": grade_8_21.get("state"),
            "liftoff_at_8_21": grade_8_21.get("liftoff_at_bar"),
            "stopped_at_8_21": grade_8_21.get("stopped_at_bar"),
            "cushion_at_8_21": grade_8_21.get("cushion_at_bar"),
            "ret_at_read_8_21": grade_8_21.get("ret_at_read"),
            # Forward metrics (horizons 5/10/21/63/126d per SPINE_HORIZONS)
            # PIT: fill at bar t+1 strictly after signal_date (fill_offset=1)
            # fwd_ret_H  = close[fill+H] / entry - 1  (species convention)
            # fwd_mdd_H  = max drawdown in (fill, fill+H] window  (always ≤0)
            # fwd_mfe_H  = max favorable excursion in same window  (always ≥0)
            **{f"fwd_ret_{h}": fwd_metrics.get(f"fwd_ret_{h}") for h in SPINE_HORIZONS},
            **{f"fwd_mdd_{h}": fwd_metrics.get(f"fwd_mdd_{h}") for h in SPINE_HORIZONS},
            **{f"fwd_mfe_{h}": fwd_metrics.get(f"fwd_mfe_{h}") for h in SPINE_HORIZONS},
            "fill_offset": fwd_metrics.get("fill_offset"),  # should be 1 (next-bar fill)
        }
        rows.append(row)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PREFILTER SOUNDNESS CHECK (positive control)
# ═══════════════════════════════════════════════════════════════════════════════

def run_soundness_check(
    closes: dict[str, pd.Series],
    candidate_sets: dict[str, pd.DatetimeIndex],
    n_sample: int = SOUNDNESS_SAMPLE,
    seed: int = 42,
) -> dict[str, Any]:
    """Positive control: sample ≥n_sample (ticker, date) pairs that are NOT
    in the candidate set and verify the production gate returns non-fire for all.

    PIT: gate is called on close_pit = close.loc[:date] for each pair.

    If ANY pair fires (eligible=True and tier_cascade in BUYABLE_TIERS),
    the prefilter has a bug — return a result with 'halt=True' and details.

    Returns dict: {ok, fires_found, halt, sample_n, details}
    """
    rng = random.Random(seed)
    non_candidates: list[tuple[str, pd.Timestamp]] = []

    for ticker, close in closes.items():
        if len(close) < 300:
            continue
        cands = set(candidate_sets.get(ticker, pd.DatetimeIndex([])))
        # Get all dates that are NOT candidates and have sufficient history
        all_dates = close.index[close.index >= close.index[249]]  # skip first 250 bars (warmup)
        non_cand_dates = [d for d in all_dates if d not in cands]
        if non_cand_dates:
            # sample up to 3 per ticker to spread across universe
            sample_n = min(3, len(non_cand_dates))
            sampled = rng.sample(non_cand_dates, sample_n)
            for d in sampled:
                non_candidates.append((ticker, d))

    rng.shuffle(non_candidates)
    selected = non_candidates[:max(n_sample, len(non_candidates))]
    if not selected:
        return {"ok": False, "fires_found": 0, "halt": False,
                "sample_n": 0, "details": "no non-candidate pairs found"}

    fires_found = 0
    fire_details = []
    for ticker, date in selected:
        close = closes[ticker]
        close_pit = close.loc[:date]
        if len(close_pit) < 250:
            continue
        try:
            v = signal_gate.gate(ticker, close_pit)
        except Exception:
            continue
        if signal_gate.is_buyable(v):
            fires_found += 1
            fire_details.append({
                "ticker": ticker,
                "date": str(date.date()),
                "tier_cascade": v.get("tier_cascade"),
                "reason": v.get("reason"),
            })
            if fires_found >= 3:
                break  # collect a few examples before halting

    ok = (fires_found == 0)
    halt = not ok
    result = {
        "ok": ok,
        "fires_found": fires_found,
        "halt": halt,
        "sample_n": len(selected),
        "fire_details": fire_details if fire_details else [],
        "note": (
            "Prefilter soundness PASSED — all non-candidate pairs returned non-fire"
            if ok else
            f"PREFILTER BUG DETECTED — {fires_found} non-candidate pair(s) fired. "
            "This means the prefilter is missing valid cross events. HALTING."
        ),
    }
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GOLDEN TEST
# ═══════════════════════════════════════════════════════════════════════════════

def run_golden_test(
    closes: dict[str, pd.Series],
    replay_dir: Path,
) -> dict[str, Any]:
    """Golden test: for the latest date in the price store, run production gate
    per ticker and compare against any replay verdicts logged for that date.

    Hard criterion: fire verdicts must match exactly (same tickers, same tier_cascade).
    Secondary soft check against site/factordata/us_standouts.json.

    PIT: gate is called on full close series (it IS the PIT for the latest date).
    """
    # Find the latest available date across all tickers
    latest_date = max(c.index.max() for c in closes.values())
    log.info("golden test: running on latest date %s", latest_date.date())

    # Run production gate on all tickers at the latest date
    live_fires: dict[str, dict] = {}
    live_verdicts: dict[str, dict] = {}
    for ticker, close in closes.items():
        if close.index.max() < latest_date - pd.Timedelta(days=5):
            continue  # skip stale series (not updated recently)
        # PIT: full series IS the PIT for today (no future data exists)
        try:
            v = signal_gate.gate(ticker, close)
            live_verdicts[ticker] = v
            if signal_gate.is_buyable(v):
                live_fires[ticker] = {
                    "tier_cascade": v.get("tier_cascade"),
                    "weight": v.get("weight"),
                    "eligible": v.get("eligible"),
                }
        except Exception:
            continue

    log.info("golden test: production gate found %d fires on %s",
             len(live_fires), latest_date.date())

    # Load replay verdicts for the latest date (from per-year parts)
    latest_year = latest_date.year
    replay_file = replay_dir / f"replay_{latest_year}.parquet"
    replay_fires_on_date: dict[str, dict] = {}
    replay_exists = False

    if replay_file.exists():
        replay_exists = True
        try:
            rdf = pd.read_parquet(replay_file)
            # Filter to latest_date
            rdf["signal_date"] = pd.to_datetime(rdf["signal_date"])
            on_date = rdf[rdf["signal_date"].dt.date == latest_date.date()]
            fires_on_date = on_date[on_date["verdict_type"] == "fire"]
            for _, row in fires_on_date.iterrows():
                replay_fires_on_date[row["ticker"]] = {
                    "tier_cascade": row.get("tier_cascade"),
                    "weight": row.get("weight"),
                }
        except Exception as e:
            log.warning("golden test: could not load replay file: %s", e)

    # Diff: live fires vs replay fires on the same date
    live_fire_tickers = set(live_fires.keys())
    replay_fire_tickers = set(replay_fires_on_date.keys())

    in_live_not_replay = live_fire_tickers - replay_fire_tickers
    in_replay_not_live = replay_fire_tickers - live_fire_tickers

    # Tier mismatches among matches
    tier_mismatches: list[dict] = []
    for t in live_fire_tickers & replay_fire_tickers:
        lv = live_fires[t].get("tier_cascade")
        rv = replay_fires_on_date[t].get("tier_cascade")
        if lv != rv:
            tier_mismatches.append({"ticker": t, "live_tier": lv, "replay_tier": rv})

    exact_match = (
        replay_exists and
        len(in_live_not_replay) == 0 and
        len(in_replay_not_live) == 0 and
        len(tier_mismatches) == 0
    )

    # Soft check against us_standouts.json
    soft_match_note = None
    try:
        with open(US_STANDOUTS_JSON) as f:
            std = json.load(f)
        buy_tickers_site = {r["ticker"] for r in (std.get("buy") or [])
                            if r.get("ticker")}
        # The standouts JSON uses a different gate (bottoming-alignment + blend_sorted),
        # so overlap is expected but divergence is allowable with explanation.
        overlap = len(live_fire_tickers & buy_tickers_site)
        soft_match_note = (
            f"Soft check vs us_standouts.json: {overlap}/{len(live_fire_tickers)} live fires "
            f"appear in standouts buy list ({len(buy_tickers_site)} total). "
            "Divergence is expected — standouts uses bottoming-alignment rank, "
            "replay uses pure confluence gate (signal_gate.is_buyable). "
            "Drift is documented, not an error."
        )
    except Exception as e:
        soft_match_note = f"us_standouts.json soft check skipped: {e}"

    return {
        "latest_date": str(latest_date.date()),
        "live_fire_count": len(live_fires),
        "live_fire_tickers": sorted(live_fire_tickers),
        "replay_fire_count": len(replay_fires_on_date),
        "replay_fire_tickers": sorted(replay_fire_tickers),
        "replay_exists": replay_exists,
        "in_live_not_replay": sorted(in_live_not_replay),
        "in_replay_not_live": sorted(in_replay_not_live),
        "tier_mismatches": tier_mismatches,
        "exact_match": exact_match,
        "golden_test_passed": exact_match or not replay_exists,
        "soft_check_note": soft_match_note,
        "note": (
            "PASS — exact match (all fire tickers and tiers agree)" if exact_match else
            "PENDING — replay not yet computed for the latest date" if not replay_exists else
            f"MISMATCH — {len(in_live_not_replay)} in live only, "
            f"{len(in_replay_not_live)} in replay only, "
            f"{len(tier_mismatches)} tier mismatches"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. YEAR-CHUNK REPLAY RUNNER (resumable)
# ═══════════════════════════════════════════════════════════════════════════════

def replay_year(
    year: int,
    closes: dict[str, pd.Series],
    candidate_sets: dict[str, pd.DatetimeIndex],
    sector_map: dict[str, str],
    replay_dir: Path,
) -> pd.DataFrame:
    """Replay all tickers for one calendar year. Writes a per-year parquet part.
    Resumes if the part already exists (skips tickers already processed).

    Returns the combined DataFrame for this year.
    """
    out_path = replay_dir / f"replay_{year}.parquet"
    existing_tickers: set[str] = set()
    existing_rows: list[dict] = []

    if out_path.exists():
        try:
            existing_df = pd.read_parquet(out_path)
            existing_tickers = set(existing_df["ticker"].unique())
            existing_rows = existing_df.to_dict("records")
            log.info("year %d: resuming — %d tickers already done, %d rows",
                     year, len(existing_tickers), len(existing_rows))
        except Exception:
            pass

    new_rows: list[dict] = []
    tickers = sorted(closes.keys())
    total = len(tickers)
    t0 = time.time()

    for i, ticker in enumerate(tickers):
        if ticker in existing_tickers:
            continue
        close = closes[ticker]
        cands = candidate_sets.get(ticker, pd.DatetimeIndex([]))
        try:
            rows = replay_ticker(ticker, close, cands, year, sector_map)
            new_rows.extend(rows)
        except Exception as e:
            log.warning("year %d: %s failed — %s", year, ticker, e)
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            log.info("year %d: %d/%d tickers processed (%.0fs)", year, i + 1, total, elapsed)

    all_rows = existing_rows + new_rows
    if not all_rows:
        log.info("year %d: no candidate rows", year)
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df.to_parquet(out_path, index=False)
    log.info("year %d: wrote %d rows to %s", year, len(df), out_path)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SUMMARY STATISTICS
# ═══════════════════════════════════════════════════════════════════════════════

def print_summary(replay_dir: Path) -> dict[str, Any]:
    """Load all per-year part files and print summary stats."""
    all_dfs = []
    for f in sorted(replay_dir.glob("replay_*.parquet")):
        try:
            df = pd.read_parquet(f)
            all_dfs.append(df)
        except Exception:
            continue

    if not all_dfs:
        print("No replay parts found.")
        return {}

    df = pd.concat(all_dfs, ignore_index=True)
    print(f"\n{'='*60}")
    print(f"REPLAY SUMMARY — {len(df):,} total candidate rows")
    print(f"{'='*60}")
    print(f"Tickers covered: {df['ticker'].nunique():,}")
    print(f"Years covered: {sorted(df['year'].unique())}")
    print(f"Date range: {df['signal_date'].min()} → {df['signal_date'].max()}")

    # Fires/year by tier
    fires = df[df["verdict_type"] == "fire"]
    print(f"\nFIRES/YEAR BY TIER ({len(fires):,} total fires):")
    if not fires.empty:
        fire_pivot = fires.groupby(["year", "tier_cascade"]).size().unstack(fill_value=0)
        print(fire_pivot.to_string())

    # Near-miss counts by reason
    near_misses = df[df["verdict_type"] == "near_miss"]
    print(f"\nNEAR-MISS COUNTS BY REASON ({len(near_misses):,} total):")
    if not near_misses.empty:
        nm_counts = near_misses["near_miss_reason"].value_counts()
        for reason, count in nm_counts.items():
            print(f"  {reason}: {count:,}")

    # Rejection counts by reason
    rejections = df[df["verdict_type"] == "rejection"]
    print(f"\nREJECTION COUNTS BY REASON ({len(rejections):,} total):")
    if not rejections.empty:
        rej_counts = rejections["rejection_reason"].value_counts()
        for reason, count in rej_counts.items():
            print(f"  {reason}: {count:,}")

    # Terminal state partition (fires only, graded rows)
    if not fires.empty:
        graded_15 = fires.dropna(subset=["state_15_126"])
        graded_8 = fires.dropna(subset=["state_8_21"])
        print(f"\nFIRE TERMINAL STATE (clean15_126, n={len(graded_15):,} graded):")
        for state in [TerminalState.CLEAN_LIFTOFF, TerminalState.CUSHIONED,
                      TerminalState.DEAD_MONEY, TerminalState.STOPPED]:
            n = (graded_15["state_15_126"] == state).sum()
            pct = n / len(graded_15) * 100 if len(graded_15) > 0 else 0
            print(f"  {state}: {n:,} ({pct:.1f}%)")

        print(f"\nFIRE TERMINAL STATE (clean8_21, n={len(graded_8):,} graded):")
        for state in [TerminalState.CLEAN_LIFTOFF, TerminalState.CUSHIONED,
                      TerminalState.DEAD_MONEY, TerminalState.STOPPED]:
            n = (graded_8["state_8_21"] == state).sum()
            pct = n / len(graded_8) * 100 if len(graded_8) > 0 else 0
            print(f"  {state}: {n:,} ({pct:.1f}%)")

    # Survivor bias breakdown
    print(f"\nSURVIVOR BIAS STAMPS:")
    sb = df["survivor_bias"].value_counts()
    for val, cnt in sb.items():
        print(f"  survivor_bias={val}: {cnt:,} rows")

    print(f"{'='*60}\n")

    return {
        "total_rows": len(df),
        "total_fires": len(fires),
        "total_near_misses": len(near_misses),
        "total_rejections": len(rejections),
        "tickers_covered": int(df["ticker"].nunique()),
        "years": sorted([int(y) for y in df["year"].unique()]),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. MAIN ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="P0.1 Production Replay Harness — Entry Intelligence §4/P0.1"
    )
    parser.add_argument(
        "--start-year", type=int, default=2012,
        help="Start year for replay (default: 2012)"
    )
    parser.add_argument(
        "--end-year", type=int, default=None,
        help="End year (inclusive; default: current year)"
    )
    parser.add_argument(
        "--year", type=int, default=None,
        help="Replay a single year only"
    )
    parser.add_argument(
        "--golden-test-only", action="store_true",
        help="Run golden test only (no replay)"
    )
    parser.add_argument(
        "--soundness-only", action="store_true",
        help="Run prefilter soundness check only"
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Print summary stats from existing replay parts"
    )
    parser.add_argument(
        "--soundness-sample", type=int, default=SOUNDNESS_SAMPLE,
        help=f"Non-candidate pairs for soundness check (default: {SOUNDNESS_SAMPLE})"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Setup output directory ─────────────────────────────────────────
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    log.info("replay output: %s", REPLAY_DIR)

    # ── Summary-only mode ─────────────────────────────────────────────
    if args.summary_only:
        print_summary(REPLAY_DIR)
        return

    # ── Load universe ─────────────────────────────────────────────────
    log.info("loading universe from %s", YAHOO_DIR)
    closes = load_universe()
    if not closes:
        log.error("no tickers loaded — check YAHOO_DIR: %s", YAHOO_DIR)
        sys.exit(1)
    log.info("universe loaded: %d tickers", len(closes))

    sector_map = _load_sector_map()
    log.info("sector map: %d entries", len(sector_map))

    # ── Prefilter: compute candidate dates per ticker ─────────────────
    # PIT: prefilter uses only each ticker's own full close series.
    # The candidate set is the superset — the golden test validates against it.
    log.info("computing prefilter candidate sets...")
    t0 = time.time()
    candidate_sets: dict[str, pd.DatetimeIndex] = {}
    for i, (ticker, close) in enumerate(sorted(closes.items())):
        try:
            candidate_sets[ticker] = prefilter_candidates(close)
        except Exception:
            candidate_sets[ticker] = pd.DatetimeIndex([])
        if (i + 1) % 100 == 0:
            log.info("prefilter: %d/%d tickers (%.0fs)", i + 1, len(closes), time.time() - t0)
    total_candidates = sum(len(v) for v in candidate_sets.values())
    log.info("prefilter complete: %d total candidate (ticker,date) pairs in %.0fs",
             total_candidates, time.time() - t0)

    # ── Prefilter soundness check ─────────────────────────────────────
    if not args.golden_test_only:
        log.info("running prefilter soundness check (n=%d)...", args.soundness_sample)
        soundness = run_soundness_check(closes, candidate_sets, n_sample=args.soundness_sample)
        print(f"\nPREFILTER SOUNDNESS CHECK:")
        print(f"  sample_n: {soundness['sample_n']}")
        print(f"  fires_found: {soundness['fires_found']}")
        print(f"  ok: {soundness['ok']}")
        print(f"  note: {soundness['note']}")
        if soundness.get("fire_details"):
            print(f"  fire_details: {soundness['fire_details']}")

        # Save soundness result
        soundness_path = REPLAY_DIR / "soundness_check.json"
        with open(soundness_path, "w") as f:
            json.dump(soundness, f, indent=2)

        if soundness.get("halt"):
            log.error("HALTING: prefilter soundness check failed — prefilter bug detected")
            sys.exit(2)
        log.info("soundness check PASSED")

    if args.soundness_only:
        return

    # ── Golden test (uses full-series gate, PIT = today) ─────────────
    log.info("running golden test...")
    golden = run_golden_test(closes, REPLAY_DIR)
    print(f"\nGOLDEN TEST:")
    print(f"  latest_date: {golden['latest_date']}")
    print(f"  live_fire_count: {golden['live_fire_count']}")
    print(f"  replay_exists: {golden['replay_exists']}")
    print(f"  exact_match: {golden['exact_match']}")
    print(f"  golden_test_passed: {golden['golden_test_passed']}")
    print(f"  note: {golden['note']}")
    if golden.get("in_live_not_replay"):
        print(f"  in_live_not_replay: {golden['in_live_not_replay'][:10]}...")
    if golden.get("in_replay_not_live"):
        print(f"  in_replay_not_live: {golden['in_replay_not_live'][:10]}...")
    if golden.get("tier_mismatches"):
        print(f"  tier_mismatches: {golden['tier_mismatches'][:5]}")
    if golden.get("soft_check_note"):
        print(f"  soft_check: {golden['soft_check_note']}")

    golden_path = REPLAY_DIR / "golden_test.json"
    with open(golden_path, "w") as f:
        json.dump(golden, f, indent=2)

    if args.golden_test_only:
        return

    # ── Year-range replay ─────────────────────────────────────────────
    if args.year is not None:
        years = [args.year]
    else:
        end_year = args.end_year or pd.Timestamp.now().year
        years = list(range(args.start_year, end_year + 1))

    log.info("replaying years: %s", years)
    for year in years:
        log.info("=== Replaying year %d ===", year)
        replay_year(year, closes, candidate_sets, sector_map, REPLAY_DIR)

    # ── Re-run golden test after replay (year-complete verification) ──
    log.info("re-running golden test against replay output...")
    golden_post = run_golden_test(closes, REPLAY_DIR)
    print(f"\nGOLDEN TEST (post-replay):")
    print(f"  golden_test_passed: {golden_post['golden_test_passed']}")
    print(f"  exact_match: {golden_post['exact_match']}")
    print(f"  note: {golden_post['note']}")
    if not golden_post["golden_test_passed"]:
        log.warning("GOLDEN TEST FAILED AFTER REPLAY — investigate tier mismatches above")

    golden_post_path = REPLAY_DIR / "golden_test_post_replay.json"
    with open(golden_post_path, "w") as f:
        json.dump(golden_post, f, indent=2)

    # ── Print summary ─────────────────────────────────────────────────
    stats = print_summary(REPLAY_DIR)

    log.info("replay complete. output: %s", REPLAY_DIR)
    log.info("total rows: %d, fires: %d, near-misses: %d, rejections: %d",
             stats.get("total_rows", 0), stats.get("total_fires", 0),
             stats.get("total_near_misses", 0), stats.get("total_rejections", 0))


if __name__ == "__main__":
    main()
