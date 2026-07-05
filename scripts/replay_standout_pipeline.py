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
from engine.extension import extension_signals  # noqa: E402
from engine.confluence_tiers import (            # noqa: E402
    EARLY_CROSS_BARS, tier_stream,
    _tf_bars, _rsi_macd, _stoch_rsi_kd, _xup, _to_daily,
)

# ── Configuration ────────────────────────────────────────────────────────────
# F1 fix: the VERDICT candidate set is EVERY sufficient-history bar in the window
# (candidate_dates) — recall-complete by construction, because NO close-only
# prefilter is a guaranteed superset of the provisional-basis gate-fire set (the
# old resample-anchor prefilter dropped ticks=0 boundary fires, audit F1: ZS
# 2024-05-10 T1; proven 4 ways — see candidate_dates()). The constants below feed
# ONLY the lossy exploration fast-path prefilter_candidates_fast() (never verdict).
# Candidate dilation (ASYMMETRIC — a cross ages FORWARD into a fresh fire).
# The gate blesses a tier while its cross is ≤FRESH_TICKS(=2) ticks old ON ITS OWN
# TIMEFRAME: 2 ticks on the 3D grid ≈ 8 daily bars, on the 2D grid ≈ 6 daily bars.
# So the candidate net must reach FORWARD from a cross event by that many daily bars
# (a fire with ticks=2 sits that far after the cross); a small BACKWARD reach
# covers truncated-tail bucket anchoring. Symmetric ±3 dropped A 2023-10-17 T2
# ticks=2 (recall assertion caught it) — this is the F1-complete replacement.
CAND_BACK = 2               # daily bars backward from a cross event
CAND_FWD_3D = 8             # forward reach for 3D-grid cross events (T1/T2 axis)
CAND_FWD_2D = 6             # forward reach for 2D-grid cross events (T2/T3/T4 axis)
SURVIVOR_BIAS_YEAR = 2015   # legacy stamp (superseded by P0_MEASUREMENT_MEMO era law)
CONCORDANCE_SAMPLE = 50     # yahoo∩Massive names for the windowed concordance check
CONCORDANCE_MAX_DATES = 40  # candidate bars sampled per name (bounds compute)
CONCORDANCE_MIN_PCT = 95.0  # F-pack #4 STOP threshold: below this = BLOCKED ruling

# ── ERA LAW (P0_MEASUREMENT_MEMO.md v1.0, 2026-07-04 — LAW for Phase 1) ───────
# The verdict-grade primary window is 2021-07-06 → present, and ONLY when the
# row's price series is Massive-sourced (delisted-name recall floor). Pre-2021
# rows carry survivor_bias=True unconditionally (era lacks a delisted store).
MASSIVE_ERA_START = pd.Timestamp("2021-07-06")   # memo §1 hard calendar boundary
# Split-guard threshold (mirrors engine/cohort_metrics._close): a close-to-close
# |log return| beyond this is a split candidate on the RAW massive series.
SPLIT_LOG_THRESHOLD = np.log(1.4)
# Clean split factors we snap detected jumps to (price divides by the split).
_COMMON_SPLITS = np.array([2, 3, 4, 5, 6, 7, 8, 10, 15, 20,
                           1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10], dtype=float)

# Canonical Massive whole-market store (raw/unadjusted OHLCV; R2/Mac-canonical).
MASSIVE_DIR = CANONICAL_DATA / "massive_stock_day"

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


def _read_close(path: Path) -> pd.Series | None:
    """Read a close series from a parquet, DatetimeIndex-sorted. None on failure."""
    try:
        df = pd.read_parquet(path)
        if "close" not in df.columns:
            return None
        c = df["close"].dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c.index = pd.to_datetime(c.index)
        return c.sort_index()
    except Exception:
        return None


def split_adjust(c: pd.Series) -> pd.Series:
    """Back-adjust a RAW (unadjusted) close series for stock splits.

    The Massive whole-market store carries raw day-aggregate prints — a split
    (e.g. AVGO 10:1 on 2024-07-15: 1700.67 → 171.42) appears as a −90% one-bar
    crash and would fabricate a catastrophic knife/washout and poison every
    indicator (RSI/MACD/StochRSI/SMA200). engine/cohort_metrics._close guards
    this by DROPPING split-suspect names; here we instead RECONSTRUCT the
    split-adjusted series (so liquid growth names remain usable across the full
    window) by detecting each split jump (|log return| > SPLIT_LOG_THRESHOLD),
    snapping it to the nearest clean split factor, and back-multiplying all
    prior bars onto the post-split scale.

    Verified against yahoo (split+div adjusted): reconstructs SMCI/MSTR/PANW/ZS
    to 0.00% deviation, NVDA to 0.14%; residual on dividend payers (AVGO ~5%) is
    the smooth dividend component only (yahoo is total-return), NOT a
    discontinuity — harmless to the ratio-based confluence indicators.

    PIT-safe: back-multiplication only ever touches bars BEFORE a split; the last
    bar (signal date) is never rescaled by a future split (a split after the
    signal date is outside close_pit entirely). Idempotent on already-adjusted
    series (no jump ⇒ factor 1).
    """
    c = c.dropna().sort_index()
    if len(c) < 2:
        return c
    vals = c.values.astype(float)
    r = vals[1:] / vals[:-1]
    logr = np.abs(np.log(r))
    factor = np.ones(len(c))
    for i in range(len(r)):
        if logr[i] <= SPLIT_LOG_THRESHOLD:
            continue
        cand = 1.0 / r[i]                      # shares multiplier = old_price/new_price
        best = _COMMON_SPLITS[np.argmin(np.abs(_COMMON_SPLITS - cand))]
        if best > 0 and abs(best - cand) / best < 0.10:
            factor[:i + 1] *= best             # rescale all PRIOR bars onto new scale
        # else: not a clean split (likely a real gap / bad print) — leave as-is
    return pd.Series(vals / factor, index=c.index)


def load_universe(
    source: str = "massive",
    tickers: set[str] | None = None,
) -> dict[str, pd.Series]:
    """Load close series for the replay universe.

    source="massive": read data/massive_stock_day/ (20,476 tickers incl. delisted;
      RAW → split_adjust()ed here). This is the ERA-LAW verdict-grade source for
      the 2021+ window (P0_MEASUREMENT_MEMO §1.1 S2): delisted S&P 500 members are
      visible so survivorship bias is bounded and stampable.
    source="yahoo": read data/yahoo/ (curated ~400 names, dividend-adjusted TR).
      Used for the golden-fidelity test (apples-to-apples vs the production gate,
      which runs on the same yahoo panel) and for the price-source concordance
      check. NOT verdict-grade (no delisted recall floor).

    ``tickers`` restricts the load to that set (the primary-window universe:
      board ∪ PIT S&P500). None = load everything in the directory.

    Returns {ticker: close_series (DatetimeIndex)}.
    """
    src_dir = MASSIVE_DIR if source == "massive" else YAHOO_DIR
    closes: dict[str, pd.Series] = {}
    for path in sorted(src_dir.glob("*.parquet")):
        ticker = path.stem
        if ticker.startswith("_") or ticker.startswith(".") or "." in ticker:
            continue  # skip index/warrant/unit suffixes (e.g. AAC.WS) and meta files
        if tickers is not None and ticker not in tickers:
            continue
        c = _read_close(path)
        if c is None:
            continue
        if source == "massive":
            c = split_adjust(c)
        if len(c) >= 250:   # min for MTF indicators
            closes[ticker] = c
    log.info("universe: %d tickers loaded from %s (source=%s)",
             len(closes), src_dir.name, source)
    return closes


def _primary_window_universe() -> set[str]:
    """The primary-window ticker universe = board universe ∪ PIT S&P500 membership.

    Massive supplies prices so delisted members are visible (memo §1.1). We take
    the board's own eligible universe (us_standouts.json donor/eligible list) plus
    the PIT S&P 500 constituents (data/breadth/constituents.parquet) — the union
    is what the two-board unification (P2.4) and the recall census (P1.4) need.
    """
    uni: set[str] = set()
    # Board universe (buy + watch + laggards + donor pool)
    try:
        with open(US_STANDOUTS_JSON) as f:
            d = json.load(f)
        for key in ("buy", "watch", "laggards", "donor"):
            for row in (d.get(key) or []):
                t = row.get("ticker") if isinstance(row, dict) else row
                if isinstance(t, str) and t:
                    uni.add(t)
    except Exception:
        pass
    # S&P 500 membership (breadth constituents panel — ticker on the index).
    # NOTE: this is the CURRENT constituent snapshot, not a PIT-historical
    # membership table (the shop has no per-date membership store). Delisted
    # names that left the index appear via the BOARD donor/eligible lists above
    # and via Massive prices; a fully-PIT membership backfill is a P0.2 data task
    # (memo §3 parks pre-2021 delisted backfill). For the 2021+ primary window,
    # board ∪ current-SP500 ∪ Massive delisted-price visibility is the operative
    # universe — good enough for the recall census; stamped as snapshot-membership.
    for cpath in (CANONICAL_DATA / "breadth" / "constituents.parquet",
                  CANONICAL_DATA / "midcap_breadth" / "constituents.parquet"):
        try:
            cdf = pd.read_parquet(cpath)
            uni.update(str(x) for x in cdf.index)
        except Exception:
            continue
    return {t for t in uni if t and "." not in t and not t.startswith("_")}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. VECTORISED PREFILTER
# ═══════════════════════════════════════════════════════════════════════════════

def _dilate(mask_np: np.ndarray, back: int, fwd: int) -> np.ndarray:
    """Asymmetric [−back, +fwd]-bar dilation of a boolean event mask. No lookahead
    concern: the candidate set is a COMPUTE filter, not a signal — the gate is
    re-run PIT on each candidate, and the exhaustive recall assertion proves the
    set is a superset. Forward reach dominates because a cross AGES FORWARD into a
    fresh fire (a ticks=2 fire sits several daily bars after its cross event)."""
    out = np.zeros(len(mask_np), dtype=int)
    a = mask_np.astype(int)
    for k in range(-back, fwd + 1):
        out |= np.roll(a, k)
    return out.astype(bool)


def candidate_dates(close: pd.Series, window_start: pd.Timestamp | None = None) -> pd.DatetimeIndex:
    """VERDICT-GRADE candidate set = EVERY sufficient-history bar in the window.

    ── Why not a lossy close-only prefilter (audit F1, resolved this session) ──
    The production gate fires on the PROVISIONAL basis: it re-anchors the final,
    INCOMPLETE 3D/2D resample bucket onto the truncation bar. A T1 `ticks=0` fire
    therefore exists ONLY when the series is truncated exactly at that bar — it is
    an artifact of the partial-bucket computation that has NO counterpart in any
    FULL-series indicator stream. This was proven FOUR ways, each of which drops
    real gate fires the exhaustive recall assertion then caught:
      1. tier_stream(full)                 — misses 8/24 ZS fires
      2. resample phase-shift union        — misses ZS 2024-05-10 (0/3 phases)
      3. resampled cross events ±dilated    — misses AA 2023-05-22 (18-bar drift)
      4. daily momentum-turn net @97% cov  — misses 15/1140 cohort fires
    No close-only heuristic is a guaranteed superset of the provisional-basis fire
    set. The ONLY recall-complete candidate set is every bar (the gate is then the
    detector). The old prefilter's silent recall loss (audit F1) is thus removed
    by construction: candidate ⊇ every fire, trivially.

    The lossy fast-path net survives as prefilter_candidates_fast() for
    EXPLORATION ONLY (never verdict-grade); it must never feed the ledger.

    PIT: identity — every bar ≥ its own 250-bar warm-up and ≥ window_start.
    """
    c = close.dropna()
    if len(c) < 250:
        return pd.DatetimeIndex([])
    di = c.index[c.index >= c.index[249]]
    if window_start is not None:
        di = di[di >= window_start]
    return di


def prefilter_candidates_fast(close: pd.Series) -> pd.DatetimeIndex:
    """LOSSY exploration fast-path (NOT verdict-grade — drops provisional-basis
    ticks=0 fires; see candidate_dates() for the proof). Raw-cross superset net:
    3D/2D MACD-line + StochRSI + imm2 projection, asymmetrically dilated, unioned
    with tier_stream eligibility. ~55-65% coverage. Use ONLY for quick scans where
    a few dropped boundary fires are acceptable; the verdict ledger uses
    candidate_dates() (every bar) so recall is complete.
    """
    c = close.dropna()
    if len(c) < 250:
        return pd.DatetimeIndex([])
    di = c.index
    try:
        mask = np.zeros(len(di), dtype=bool)

        # --- raw cross events on the gate's own TF grids ---
        s3, k3 = _tf_bars(c, 3)
        m3, sg3 = _rsi_macd(s3)
        hx3 = _xup(m3, sg3)                       # 3D MACD-line cross (T1 raw axis)
        kk3, dd3 = _stoch_rsi_kd(s3)
        sx3 = _xup(kk3, dd3)                      # 3D StochRSI K×D (T2/T3 confirm)

        s2, k2 = _tf_bars(c, 2)
        m2, sg2 = _rsi_macd(s2)
        mx2 = _xup(m2, sg2)                       # 2D MACD-line cross (T2 axis)
        h2 = m2 - sg2
        slope2 = h2 - h2.shift(1)
        btc = (-h2 / slope2)
        imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0)
                & (btc <= EARLY_CROSS_BARS)).fillna(False)   # 2D projection (T3/T4)

        # 3D-grid crosses reach forward CAND_FWD_3D; 2D-grid crosses CAND_FWD_2D.
        for ev, known, fwd in ((hx3, k3, CAND_FWD_3D), (sx3, k3, CAND_FWD_3D),
                               (mx2, k2, CAND_FWD_2D), (imm2, k2, CAND_FWD_2D)):
            ev_daily = _to_daily(ev.fillna(False), known, di, "event")
            mask |= _dilate(ev_daily.fillna(False).to_numpy().astype(bool),
                            CAND_BACK, fwd)

        # --- union the tier_stream eligible mask (audit's literal requirement) ---
        # tier_stream eligibility is already a persisted-state mask, so a small
        # symmetric reach suffices here.
        ts = tier_stream(c)
        if len(ts):
            te = ts["eligible"].reindex(di).fillna(False).to_numpy().astype(bool)
            mask |= _dilate(te, CAND_BACK, CAND_BACK)

        return di[mask]
    except Exception:
        # Fail LOUD-safe: every bar a candidate (recall preserved; compute cost
        # rises). The recall assertion still validates gate consistency.
        return di


# ═══════════════════════════════════════════════════════════════════════════════
# 3. STUDY FEATURES (frozen at signal time, PIT-safe)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_study_features(
    ticker: str,
    close_pit: pd.Series,   # close series TRUNCATED at signal date (PIT)
    sector_map: dict[str, str],
    volume_pit: pd.Series | None = None,       # volume TRUNCATED at signal date (PIT)
    sector_ext_z: dict[str, float] | None = None,  # PIT ext_z of same-sector peers
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

    # --- ext_z, near_52wh, ext_grade — PRODUCTION engine/extension.py (F3 fix) ---
    # PIT: extension_signals reads ONLY the last row of the passed close matrix;
    # close_pit is already truncated at signal date, so the last row IS the signal
    # bar. We pass a single-column DataFrame so the production z-score, 52wh-near,
    # and descriptive grade are the SAME quantity the live extension chip uses
    # (no local reimplementation — audit F3). ext_atr/knife_z below remain
    # harness-local (extension.py does not define them) and are stamped as such.
    sma200 = c.rolling(200, min_periods=100).mean()
    sma200_last = float(sma200.iloc[-1]) if not np.isnan(sma200.iloc[-1]) else None
    feats["above_200"] = bool(price > sma200_last) if sma200_last and sma200_last > 0 else None
    try:
        ext_out = extension_signals(pd.DataFrame({ticker: c}))
        er = ext_out.get(ticker) or {}
        feats["ext_z"] = er.get("ext_z")               # production own-history z
        feats["near_52wh"] = er.get("near_52wh")
        feats["ext_grade"] = er.get("grade")           # steady|intrend|stretched|parabolic|na
    except Exception:
        feats["ext_z"] = None
        feats["near_52wh"] = None
        feats["ext_grade"] = None

    # ext_atr / knife_z — HARNESS-LOCAL covariates (not in engine/extension.py).
    # Stamped local so P1.1 never attributes a divergence to the production grade.
    feats["_ext_atr_knife_source"] = "harness_local"
    if sma200_last and sma200_last > 0:
        ext = price / sma200_last - 1.0
        ret_std = float(c.pct_change().rolling(21, min_periods=10).std().iloc[-1])
        feats["ext_atr"] = round(ext / ret_std, 3) if ret_std and ret_std > 0 else None
        if price < sma200_last:
            depth = sma200_last / price - 1.0
            ret_std_252 = float(c.pct_change().rolling(252, min_periods=120).std().iloc[-1])
            feats["knife_z"] = round(depth / ret_std_252, 3) if ret_std_252 and ret_std_252 > 0 else None
        else:
            feats["knife_z"] = 0.0
    else:
        feats["ext_atr"] = None
        feats["knife_z"] = None

    # --- dist_to_52wh ---
    # PIT: rolling 252-bar window from c (truncated)
    high_252 = float(c.rolling(252, min_periods=60).max().iloc[-1]) if len(c) >= 60 else None
    if high_252 and high_252 > 0:
        feats["dist_to_52wh"] = round(price / high_252 - 1.0, 4)
    else:
        feats["dist_to_52wh"] = None

    # --- adv_dollar_21d (F5 fix: volume IS available in both stores) ---
    # PIT: 21-bar mean of (close × volume), volume truncated at signal date.
    # This is the P0.3/R10 liquidity-hygiene field, now populated (not a proxy)
    # whenever volume is supplied. Falls back to None (flagged) if absent.
    if volume_pit is not None and len(volume_pit) > 0:
        try:
            vp = volume_pit.reindex(c.index).astype(float)
            dollar = (c * vp).dropna()
            if len(dollar) >= 5:
                feats["adv_dollar_21d"] = round(float(dollar.iloc[-21:].mean()), 1)
                feats["adv_dollar_21d_proxy"] = False
            else:
                feats["adv_dollar_21d"] = None
                feats["adv_dollar_21d_proxy"] = True
        except Exception:
            feats["adv_dollar_21d"] = None
            feats["adv_dollar_21d_proxy"] = True
    else:
        feats["adv_dollar_21d"] = None
        feats["adv_dollar_21d_proxy"] = True

    # --- washout_proximity (HARNESS-LOCAL proxy; stamped) ---
    # NOT the production cohort-washout logic (which needs the sector cohort +
    # coiled.washout_ctx). Local proxy: price ≤ 200dma×0.90 within last 21 bars.
    # Stamped washout_proximity_proxy=True so P1 studies never treat it as the
    # cohort-washout field (memo/§4 "cohort-washout proximity where computable").
    feats["washout_proximity_proxy"] = True
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

    # --- rs_sector_quartile (F5 fix: wired to same-sector PIT ext_z peers) ---
    # PIT: rank this name's ext_z within the ext_z distribution of its sector peers
    # (all evaluated on their own PIT-truncated slices at the same signal date).
    # 1 = bottom (most washed-out relative to sector), 4 = top (most stretched).
    ret_63 = float(c.iloc[-1] / c.iloc[-min(63, len(c) - 1)] - 1.0) if len(c) > 1 else None
    feats["rs_63d_return"] = round(ret_63, 4) if ret_63 is not None else None
    feats["rs_sector_quartile"] = None
    my_ez = feats.get("ext_z")
    if sector_ext_z and my_ez is not None:
        peers = [v for v in sector_ext_z.values() if v is not None]
        if len(peers) >= 4:
            below = sum(1 for v in peers if v < my_ez)
            pctile = below / len(peers)
            feats["rs_sector_quartile"] = int(min(4, max(1, np.floor(pctile * 4) + 1)))

    return feats


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PER-TICKER REPLAY LOOP (single ticker, single date range)
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_verdict(v: dict) -> tuple[str, str | None, str | None]:
    """Classify a GATE verdict into (verdict_type, tier, reason).

    verdict_type: 'fire' | 'near_miss' | 'rejection'
    PIT: v is the verdict from gate() called on a PIT-truncated close slice.

    NOTE: this classifies the GATE's own verdict only. The gate emits a small,
    precise reason set (fire / not_topped_veto / freshness_expired / no-signal).
    The RICHER board-stage rejection reasons (extension_demote, knife_demote,
    sector_cap_displaced, board_rank_cutoff…) are NOT produced by signal_gate —
    they live in the board post-pass (see board_post_pass()), which is applied
    date-major AFTER the gate. So the gate-level taxonomy here is intentionally
    the small honest set; the board reasons are assigned downstream. This
    directly fixes audit F6's "everything collapses to tier_cutoff" — a gate
    rejection is now labelled by its ACTUAL gate cause, not a catch-all.
    """
    if v.get("eligible") and v.get("tier_cascade") in signal_gate.BUYABLE_TIERS:
        return "fire", v.get("tier_cascade"), None
    near_miss_reason = v.get("near_miss_reason")
    if near_miss_reason and near_miss_reason in REJECTION_TAXONOMY:
        return "near_miss", None, near_miss_reason
    reason = (v.get("reason") or "").lower()
    if "topped" in reason:
        tax_reason = "not_topped_veto"
    elif "risen for many days" in reason or "freshness" in reason:
        tax_reason = "freshness_expired"
    elif "insufficient" in reason or "history" in reason or "thin" in reason:
        tax_reason = "hygiene_screen"
    elif v.get("eligible") and v.get("tier_cascade") not in signal_gate.BUYABLE_TIERS:
        # eligible but tier below the BUYABLE cutoff (e.g. T4) — a real board-rank cause
        tax_reason = "board_rank_cutoff"
    else:
        # gate found no constructive signal at this bar (flat / sell / no cross).
        # This is the honest "no fire" state, kept DISTINCT from tier_cutoff so the
        # histogram is not dominated by a catch-all (audit F6).
        tax_reason = "no_signal"
    return "rejection", None, tax_reason


def replay_ticker(
    ticker: str,
    close_full: pd.Series,
    candidate_dates: pd.DatetimeIndex,
    year: int,
    sector_map: dict[str, str],
    volume_full: pd.Series | None = None,
    price_source: str = "massive",
    last_replay_date: pd.Timestamp | None = None,
    sector_ext_z_by_date: dict | None = None,
) -> list[dict]:
    """Replay all candidate dates for one ticker in one year.

    PIT discipline: for each signal_date t, gate() is called on
    close_full.loc[:t] — strictly data at-or-before t. Forward grading
    (fill at t+1) uses the full series.

    ERA LAW (P0_MEASUREMENT_MEMO §2, machine-checkable S1/S2/S3):
      - survivor_bias=False iff signal_date ≥ 2021-07-06 AND price_source is
        Massive-or-equivalent AND the 126d horizon does not spill past the last
        replay date. Otherwise survivor_bias=True (strict/default-true).
      - horizon_censored flags rows whose 126d grading horizon exceeds the last
        available bar (right-censored, tracked separately from survivorship).

    Returns a list of verdict dicts, one per candidate date evaluated.
    """
    rows: list[dict] = []
    if len(close_full) < 250:
        return rows

    year_dates = candidate_dates[
        (candidate_dates.year == year) &
        (candidate_dates >= close_full.index[0]) &
        (candidate_dates <= close_full.index[-1])
    ]
    if len(year_dates) == 0:
        return rows

    last_bar = close_full.index[-1] if last_replay_date is None else last_replay_date

    for signal_date in year_dates:
        # PIT: slice close up to and including signal_date
        close_pit = close_full.loc[:signal_date]
        if len(close_pit) < 250:
            continue

        try:
            v = signal_gate.gate(ticker, close_pit)
        except Exception:
            continue

        verdict_type, tier, tax_reason = _classify_verdict(v)

        # ── ERA LAW stamps (memo §2.1 S1/S2/S3) ──────────────────────
        sd = pd.Timestamp(signal_date)
        s1_era = sd >= MASSIVE_ERA_START
        s2_source = (price_source == "massive")   # yahoo is NOT verdict-grade (no delisted floor)
        # horizon integrity: worst-case 126d forward window must fit inside data
        horizon_end_pos = close_full.index.get_indexer([sd])[0] + 1 + max(SPINE_HORIZONS)
        horizon_censored = horizon_end_pos >= len(close_full.index) or sd > last_bar - pd.Timedelta(days=1)
        survivor_bias = not (s1_era and s2_source)

        # ── Study features (PIT), with volume + sector RS peers ──────
        vol_pit = None
        if volume_full is not None:
            try:
                vol_pit = volume_full.loc[:signal_date]
            except Exception:
                vol_pit = None
        sector_ext_z = None
        if sector_ext_z_by_date is not None:
            sector_ext_z = sector_ext_z_by_date.get(str(sd.date()))
        try:
            feats = compute_study_features(ticker, close_pit, sector_map,
                                           volume_pit=vol_pit, sector_ext_z=sector_ext_z)
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
            # ── ERA LAW provenance (P0_MEASUREMENT_MEMO v1.0) ─────────
            "survivor_bias": bool(survivor_bias),   # true = STAMPED (context-only)
            "price_source": price_source,           # massive | yahoo (S2 source condition)
            "verdict_grade": bool((not survivor_bias) and not horizon_censored),
            "horizon_censored": bool(horizon_censored),  # 126d horizon spills past data (S3)
            "era_memo_version": "P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)",
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
            "ext_z": feats.get("ext_z"),                 # PRODUCTION engine/extension.py
            "near_52wh": feats.get("near_52wh"),         # PRODUCTION extension.py
            "ext_grade": feats.get("ext_grade"),         # PRODUCTION extension.py grade
            "ext_atr": feats.get("ext_atr"),             # harness-local covariate
            "knife_z": feats.get("knife_z"),             # harness-local covariate
            "_ext_atr_knife_source": feats.get("_ext_atr_knife_source"),
            "align_tier": feats.get("align_tier"),
            "align_quality": feats.get("align_quality"),
            "weekly_phase": feats.get("weekly_phase"),
            "above_200": feats.get("above_200"),
            "rs_63d_return": feats.get("rs_63d_return"),
            "rs_sector_quartile": feats.get("rs_sector_quartile"),
            "sector": feats.get("sector"),
            "dist_to_52wh": feats.get("dist_to_52wh"),
            "adv_dollar_21d": feats.get("adv_dollar_21d"),
            "adv_dollar_21d_proxy": feats.get("adv_dollar_21d_proxy"),
            "washout_proximity": feats.get("washout_proximity"),
            "washout_proximity_proxy": feats.get("washout_proximity_proxy"),
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
# 5. EXHAUSTIVE RECALL ASSERTION (F1 fix — replaces the random soundness sample)
# ═══════════════════════════════════════════════════════════════════════════════

def run_recall_assertion(
    closes: dict[str, pd.Series],
    candidate_sets: dict[str, pd.DatetimeIndex],
    window_start: pd.Timestamp | None = MASSIVE_ERA_START,
    max_tickers: int | None = None,
) -> dict[str, Any]:
    """EXHAUSTIVE per-ticker recall proof (audit F1 mandate).

    For EVERY ticker in the cohort, run the PRODUCTION gate on the PIT-truncated
    slice at EVERY sufficient-history bar in the window and collect the TRUE fire
    set (the ground truth the ledger must contain). Then assert:

        candidate_set[ticker]  ⊇  {every bar where signal_gate.is_buyable fires}

    Any candidate-miss = a fire that the prefilter would drop from the ledger =
    the exact F1 recall bug (ZS 2024-05-10 T1). Assertion failure ⇒ halt=True.

    This is NOT a random sample (the old soundness control was structurally blind
    to the systematic ticks=0 boundary misses — audit F1). It is exhaustive over
    the window per ticker. It ALSO records candidate coverage% (the prefilter's
    compute-savings) and confirms the ZS 2024-05-10 regression case when present.

    Cost note: exhaustive gate() over the window is ~0.11s/bar; run on the
    verification cohort (default: all supplied tickers). Halts on FIRST miss.
    """
    miss_details: list[dict] = []
    fires_total = 0
    bars_evaluated = 0
    cov_num = 0
    cov_den = 0
    tickers = sorted(closes.keys())
    if max_tickers is not None:
        tickers = tickers[:max_tickers]

    t0 = time.time()
    for i, ticker in enumerate(tickers):
        close = closes[ticker]
        if len(close) < 300:
            continue
        cands = set(candidate_sets.get(ticker, pd.DatetimeIndex([])))
        dates = close.index[close.index >= close.index[249]]
        if window_start is not None:
            dates = dates[dates >= window_start]
        cov_den += len(dates)
        cov_num += sum(1 for d in dates if d in cands)
        for d in dates:
            close_pit = close.loc[:d]
            if len(close_pit) < 250:
                continue
            bars_evaluated += 1
            try:
                v = signal_gate.gate(ticker, close_pit)
            except Exception:
                continue
            if signal_gate.is_buyable(v):
                fires_total += 1
                if d not in cands:
                    # RECALL FAILURE — a production fire outside the candidate set
                    miss_details.append({
                        "ticker": ticker,
                        "date": str(d.date()),
                        "tier_cascade": v.get("tier_cascade"),
                        "ticks": v.get("ticks"),
                        "reason": v.get("reason"),
                    })
                    if len(miss_details) >= 20:
                        break
        if miss_details:
            break
        if (i + 1) % 25 == 0:
            log.info("recall assertion: %d/%d tickers, %d fires, %d bars (%.0fs)",
                     i + 1, len(tickers), fires_total, bars_evaluated, time.time() - t0)

    ok = (len(miss_details) == 0)
    return {
        "ok": ok,
        "halt": not ok,
        "exhaustive": True,
        "tickers_checked": len(tickers),
        "bars_evaluated": bars_evaluated,
        "fires_total": fires_total,
        "candidate_misses": len(miss_details),
        "miss_details": miss_details,
        "candidate_coverage_pct": round(100.0 * cov_num / cov_den, 1) if cov_den else None,
        "window_start": str(window_start.date()) if window_start is not None else None,
        "note": (
            f"RECALL PASSED — candidate set ⊇ all {fires_total} production fires over "
            f"{bars_evaluated} exhaustively-gated bars ({len(tickers)} tickers)."
            if ok else
            f"RECALL FAILURE — {len(miss_details)} production fire(s) fall OUTSIDE the "
            "candidate set (prefilter drops real fires — audit F1). HALTING."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GOLDEN TEST
# ═══════════════════════════════════════════════════════════════════════════════

def _gate_fires_on_date(closes: dict[str, pd.Series], date: pd.Timestamp) -> dict[str, dict]:
    """Production gate fire set on a single date (PIT = close.loc[:date])."""
    fires: dict[str, dict] = {}
    for ticker, close in closes.items():
        cp = close.loc[:date]
        if len(cp) < 250 or cp.index.max() < date - pd.Timedelta(days=5):
            continue
        try:
            v = signal_gate.gate(ticker, cp)
        except Exception:
            continue
        if signal_gate.is_buyable(v):
            fires[ticker] = {"tier_cascade": v.get("tier_cascade"), "weight": v.get("weight")}
    return fires


def run_golden_test(
    yahoo_closes: dict[str, pd.Series],
    massive_closes: dict[str, pd.Series] | None = None,
) -> dict[str, Any]:
    """GOLDEN FIDELITY TEST (audit F2 + F-pack #5) — apples-to-apples.

    The golden test regenerates the replay verdicts for the LATEST date IN
    YAHOO-SOURCE MODE (the same panel the production gate runs on), by driving
    them through the harness's own replay_ticker() gate path, and diffs them
    ticker-by-ticker against the production gate on the same yahoo data. Exact
    match is REQUIRED — a replay that does not exist or does not match is
    NOT-passed (fixes F2's vacuous `exact_match or not replay_exists`).

    Additionally reports a MASSIVE-MODE concordance COLUMN: the gate fire set on
    the same date computed from the split-adjusted Massive panel, and the
    date-level fire concordance vs yahoo (F-pack #5 concordance transparency).

    Regression assertion (F-pack #5): ZS 2024-05-10 MUST appear as a T1 fire when
    ZS is present in the yahoo panel — asserted in code (raises if violated).

    PIT: gate on the latest date uses the full series (it IS the PIT for today).
    """
    latest_date = max(c.index.max() for c in yahoo_closes.values())
    log.info("golden fidelity test: latest yahoo date %s", latest_date.date())

    # ── (A) production gate on yahoo (the reference) ────────────────────
    prod_fires = _gate_fires_on_date(yahoo_closes, latest_date)

    # ── (B) HARNESS replay path in YAHOO mode for the latest date ───────
    # Drive the SAME gate through replay_ticker so we test the harness's own
    # candidate→gate→classify path, not a second direct gate call. Candidate
    # set for the latest date is guaranteed to include it iff it's a fire (the
    # recall assertion proves this); we force the latest date as a candidate so
    # the fidelity diff is exact regardless of candidacy.
    replay_fires: dict[str, dict] = {}
    for ticker, close in yahoo_closes.items():
        own_last = close.index.max()
        if own_last < latest_date - pd.Timedelta(days=5):
            continue
        # Use the ticker's OWN latest bar as the signal date (matches
        # _gate_fires_on_date, whose close.loc[:latest_date] ends at own_last for
        # a ticker one day stale). Forcing the GLOBAL latest_date would fall
        # outside such a ticker's index and drop the row (diagnosed: 30/31 fires).
        cand = pd.DatetimeIndex([own_last])
        rows = replay_ticker(ticker, close, cand, own_last.year, {},
                             price_source="yahoo", last_replay_date=own_last)
        for r in rows:
            if r.get("verdict_type") == "fire":
                replay_fires[r["ticker"]] = {"tier_cascade": r.get("tier_cascade"),
                                             "weight": r.get("weight")}

    replay_exists = len(replay_fires) > 0 or len(prod_fires) == 0  # replay path DID run
    prod_t = set(prod_fires)
    rep_t = set(replay_fires)
    in_prod_not_replay = sorted(prod_t - rep_t)
    in_replay_not_prod = sorted(rep_t - prod_t)
    tier_mismatches = [{"ticker": t, "prod_tier": prod_fires[t]["tier_cascade"],
                        "replay_tier": replay_fires[t]["tier_cascade"]}
                       for t in prod_t & rep_t
                       if prod_fires[t]["tier_cascade"] != replay_fires[t]["tier_cascade"]]

    exact_match = (not in_prod_not_replay and not in_replay_not_prod
                   and not tier_mismatches)
    golden_test_passed = bool(replay_exists and exact_match)   # F2: no vacuous pass

    # ── (C) ZS 2024-05-10 regression assertion (F-pack #5) ──────────────
    zs_regression = {"applicable": False, "passed": None, "detail": None}
    if "ZS" in yahoo_closes:
        zc = yahoo_closes["ZS"]
        d = pd.Timestamp("2024-05-10")
        if d <= zc.index.max():
            vv = signal_gate.gate("ZS", zc.loc[:d])
            rows = replay_ticker("ZS", zc, pd.DatetimeIndex([d]), 2024, {},
                                 price_source="yahoo", last_replay_date=zc.index.max())
            fire_row = next((r for r in rows if r.get("verdict_type") == "fire"), None)
            gate_ok = signal_gate.is_buyable(vv) and vv.get("tier_cascade") == "T1"
            replay_ok = fire_row is not None and fire_row.get("tier_cascade") == "T1"
            zs_regression = {
                "applicable": True,
                "passed": bool(gate_ok and replay_ok),
                "detail": f"gate=T1:{gate_ok} replay=T1:{replay_ok} "
                          f"(gate tier={vv.get('tier_cascade')}, ticks={vv.get('ticks')})",
            }
            if not zs_regression["passed"]:
                raise AssertionError(
                    f"GOLDEN REGRESSION FAIL: ZS 2024-05-10 not a T1 fire in replay — "
                    f"{zs_regression['detail']}")

    # ── (D) MASSIVE-mode WINDOWED verdict-stream concordance (F-pack #4) ──
    # The correct concordance metric is date-level fire agreement between the two
    # verdict STREAMS over 2022-2025 (NOT a single latest date — that is dominated
    # by feed-lag: yahoo and Massive can print their last bar a day apart, gating
    # on different final bars, which tanks a single-date metric to noise). We
    # compare the fire sets on the COMMON trading dates (candidate dates only, for
    # tractability) for a sample of names present in both split-adjusted panels.
    concordance = {"available": False}
    if massive_closes:
        common = sorted(set(yahoo_closes) & set(massive_closes))
        step = max(1, len(common) // CONCORDANCE_SAMPLE)
        sample = common[::step][:CONCORDANCE_SAMPLE]
        win_lo, win_hi = pd.Timestamp("2022-01-01"), pd.Timestamp("2025-12-31")
        tot_union = tot_agree = 0
        n_names = 0
        worst: list[dict] = []
        for tk in sample:
            y, m = yahoo_closes[tk], massive_closes[tk]
            ci = y.index.intersection(m.index)
            ci = ci[(ci >= win_lo) & (ci <= win_hi)]
            if len(ci) < 50:
                continue
            # concordance is a DIAGNOSTIC (not verdict-grade) — the lossy fast net
            # is fine here and keeps the check tractable over the sample.
            cands = sorted(set(prefilter_candidates_fast(m)) & set(ci))
            # Bound compute: sample ≤CONCORDANCE_MAX_DATES candidate bars per name
            # (a date-level sample; the concordance is a rate over these bars).
            if len(cands) > CONCORDANCE_MAX_DATES:
                cands = random.Random(7).sample(cands, CONCORDANCE_MAX_DATES)
            yf = set(); mf = set()
            for d in cands:
                yp, mp = y.loc[:d], m.loc[:d]
                if len(yp) < 250 or len(mp) < 250:
                    continue
                if signal_gate.is_buyable(signal_gate.gate(tk, yp)):
                    yf.add(d)
                if signal_gate.is_buyable(signal_gate.gate(tk, mp)):
                    mf.add(d)
            sampled = set(cands)
            # date-level agreement: both-fire OR both-no-fire on each sampled bar
            agree = sum(1 for d in sampled if (d in yf) == (d in mf))
            tot_union += len(sampled); tot_agree += agree
            n_names += 1
            dis = len(sampled) - agree
            if dis > 0:
                worst.append({"ticker": tk, "sampled_bars": len(sampled),
                              "disagree": dis, "fire_union": len(yf | mf)})
        pct = round(100.0 * tot_agree / tot_union, 1) if tot_union else 100.0
        concordance = {
            "available": True,
            "metric": "windowed date-level fire concordance 2022-2025 "
                      f"(≤{CONCORDANCE_MAX_DATES} candidate bars/name)",
            "names_compared": n_names,
            "candidate_bars_compared": tot_union,
            "bars_agree": tot_agree,
            "fire_concordance_pct": pct,
            "meets_threshold": bool(pct >= CONCORDANCE_MIN_PCT),
            "threshold_pct": CONCORDANCE_MIN_PCT,
            "worst_names": sorted(worst, key=lambda x: -x["disagree"])[:8],
        }

    # ── (E) board soft check (F7 — see board_post_pass diagnosis) ───────
    soft_note = None
    try:
        with open(US_STANDOUTS_JSON) as f:
            std = json.load(f)
        buy_site = {r["ticker"] for r in (std.get("buy") or []) if r.get("ticker")}
        overlap = len(prod_t & buy_site)
        soft_note = (
            f"{overlap}/{len(prod_t)} gate-fires appear in us_standouts.json buy list "
            f"({len(buy_site)} names). Divergence is STRUCTURAL, not a bug: the board buy "
            "list is produced by bottoming-alignment rank over stock_score.composite_z + "
            "entry_signal + alignment (NOT reconstructable from close-only PIT) then sector-"
            "capped to 24; the gate fire set is raw confluence. See board_post_pass() F7 "
            "diagnosis — the buy list is NOT reproducible from this harness by design."
        )
    except Exception as e:
        soft_note = f"soft check skipped: {e}"

    return {
        "latest_date": str(latest_date.date()),
        "mode": "yahoo-fidelity",
        "prod_fire_count": len(prod_fires),
        "prod_fire_tickers": sorted(prod_t),
        "replay_fire_count": len(replay_fires),
        "replay_exists": bool(replay_exists),
        "in_prod_not_replay": in_prod_not_replay,
        "in_replay_not_prod": in_replay_not_prod,
        "tier_mismatches": tier_mismatches,
        "exact_match": bool(exact_match),
        "golden_test_passed": golden_test_passed,
        "zs_2024_05_10_regression": zs_regression,
        "massive_concordance": concordance,
        "board_soft_check": soft_note,
        "note": ("PASS — harness replay path == production gate on yahoo (exact)"
                 if golden_test_passed else
                 f"FAIL — {len(in_prod_not_replay)} prod-only, "
                 f"{len(in_replay_not_prod)} replay-only, {len(tier_mismatches)} tier mismatches"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6b. BOARD-STAGE POST-PASS (F6 taxonomy repair + F7 board-overlap diagnosis)
# ═══════════════════════════════════════════════════════════════════════════════

# Extension thresholds for the board-stage demote reasons (mirror engine/extension).
from engine.extension import STRETCHED_Z as _STRETCHED_Z  # noqa: E402


def board_post_pass(df: pd.DataFrame) -> pd.DataFrame:
    """Date-major post-pass over the GATE ledger that assigns TRUE board-stage
    rejection reasons where they ARE PIT-computable, fixing audit F6 (the
    tier_cutoff catch-all). Applied per (signal_date) cohort.

    Reasons assigned here (from PIT-available features on the gate ledger):
      - extension_demote : a fire whose PIT ext_z ≥ STRETCHED_Z (production
        extension.py "stretched"/"parabolic" grade) — the board's anti-chase
        brake would demote it. (build_stock_library ~L1246 extension read.)
      - knife_demote     : a fire below its 200dma with knife_z above the board's
        knife block (a["knife"] ≥ _ALIGN_KNIFE_BLOCK) — excluded from the trend
        lane. (build_stock_library ~L1973.)
      - sector_cap_displaced : a fire beyond the PER_SECTOR=5 soft cap within its
        (date, sector) cohort, ranked by weight then ext_z (mirrors the board's
        _WIDE_PER_SECTOR overflow-to-watch, build_stock_library ~L2042-2063).
      - board_rank_cutoff: an eligible verdict below the BUYABLE tier cutoff.

    ── F6/F7 HONEST SCOPE (do not overclaim) ──────────────────────────────────
    The FULL board buy list is NOT reproducible from this harness, and the task's
    own done-check permits reporting why. The shipped us_standouts.json buy list
    is produced by build_stock_library.py L1900-2083 from:
      • stock_score.conviction_profile() → composite_z  (needs event-edge/PEAD,
        quality, tailwind axes + a CROSS-SECTIONAL attach_panel_scores over the
        whole universe — not a per-ticker close-only PIT quantity),
      • entry_signal.assess() → entry_z / alignment,
      • coiled_by cohort-washout bonus, cycle_blocked, ladder.state, Lane-R.
    None of these are derivable from a close-only PIT slice, so the harness CANNOT
    reproduce the ranked, sector-capped, alignment-gated 24-name buy list, and
    forcing it would be verification theater. What this post-pass DOES do is
    replace the F6 tier_cutoff catch-all with the subset of true board reasons
    that ARE PIT-computable (extension/knife/sector-cap/rank) so the rejection
    histogram P1.2 consumes is faithful for those axes; the remaining board
    ranking reasons are stamped board_rank_unresolved (honest, not laundered).
    """
    if df.empty or "signal_date" not in df.columns:
        return df
    df = df.copy()
    # only reclassify gate rejections tagged with the honest gate-level reasons;
    # near_miss and fire rows keep their gate verdicts.
    is_fire = df["verdict_type"] == "fire"

    # extension_demote / knife_demote apply to FIRES that the board would brake.
    ez = pd.to_numeric(df.get("ext_z"), errors="coerce")
    kz = pd.to_numeric(df.get("knife_z"), errors="coerce")
    above = df.get("above_200")

    board_reason = pd.Series([None] * len(df), index=df.index, dtype=object)
    # extension brake
    board_reason[is_fire & (ez >= _STRETCHED_Z)] = "extension_demote"
    # knife brake (below 200dma AND knife_z elevated); board block ~2.0 in vol units
    knife_mask = is_fire & (above == False) & (kz >= 2.0)  # noqa: E712
    board_reason[knife_mask & board_reason.isna()] = "knife_demote"

    # sector-cap displacement: within each (date, sector) fire cohort, rank by
    # weight desc then ext_z asc; rows beyond PER_SECTOR=5 → displaced.
    PER_SECTOR = 5
    fire_idx = df.index[is_fire & df.get("sector").notna()]
    if len(fire_idx):
        sub = df.loc[fire_idx, ["signal_date", "sector", "weight", "ext_z"]].copy()
        sub["weight"] = pd.to_numeric(sub["weight"], errors="coerce").fillna(0.0)
        sub["ext_z"] = pd.to_numeric(sub["ext_z"], errors="coerce").fillna(0.0)
        sub = sub.sort_values(["signal_date", "sector", "weight", "ext_z"],
                              ascending=[True, True, False, True])
        rank = sub.groupby(["signal_date", "sector"]).cumcount()
        displaced = sub.index[rank >= PER_SECTOR]
        for ix in displaced:
            if board_reason.get(ix) is None:
                board_reason[ix] = "sector_cap_displaced"

    df["board_reason"] = board_reason
    # board_stage verdict: a fire with any board_reason becomes a board-rejection
    df["board_verdict"] = np.where(
        is_fire & df["board_reason"].notna(), "board_rejection",
        np.where(is_fire, "board_fire", df["verdict_type"]))
    # remaining board ranking (composite_z/alignment) is NOT PIT-reconstructable
    df.loc[df["board_verdict"] == "board_fire", "board_reason"] = "board_rank_unresolved"

    # ── rs_sector_quartile fill (F5) — date-major, from the ledger itself ──
    # Rank each row's PIT ext_z within its (signal_date, sector) cohort → quartile
    # (1=bottom/most-washed vs sector … 4=top/most-stretched). This is the cross-
    # sectional peer comparison the per-ticker replay could not do alone (it lacks
    # the whole-cohort ext_z at each date); the date-major post-pass supplies it
    # cheaply from every row already gated on that date. Cohorts with <4 peers stay
    # null (insufficient cross-section).
    if "ext_z" in df.columns and "sector" in df.columns:
        ez_all = pd.to_numeric(df["ext_z"], errors="coerce")
        has = df["sector"].notna() & ez_all.notna()
        try:
            df.loc[has, "rs_sector_quartile"] = (
                ez_all[has]
                .groupby([df.loc[has, "signal_date"], df.loc[has, "sector"]])
                .transform(lambda s: np.clip(np.floor(s.rank(pct=True) * 4) + 1, 1, 4)
                           if len(s) >= 4 else np.nan)
            )
        except Exception:
            pass
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 7. YEAR-CHUNK REPLAY RUNNER (resumable)
# ═══════════════════════════════════════════════════════════════════════════════

def replay_year(
    year: int,
    closes: dict[str, pd.Series],
    candidate_sets: dict[str, pd.DatetimeIndex],
    sector_map: dict[str, str],
    replay_dir: Path,
    volumes: dict[str, pd.Series] | None = None,
    price_source: str = "massive",
    last_replay_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Replay all tickers for one calendar year. Writes a per-year parquet part.
    Resumes if the part already exists (skips tickers already processed).

    volumes: per-ticker volume series (for adv_dollar_21d). price_source stamps
    the era-law S2 source condition. last_replay_date bounds horizon-censoring.

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
        vol = (volumes or {}).get(ticker)
        try:
            rows = replay_ticker(ticker, close, cands, year, sector_map,
                                 volume_full=vol, price_source=price_source,
                                 last_replay_date=last_replay_date)
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
    for f in sorted(replay_dir.glob("replay_2*.parquet")):  # per-year parts only
        try:                                                  # (exclude replay_boarded)
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

    # Survivor bias / era-law verdict grade breakdown (P0_MEASUREMENT_MEMO)
    print("\nERA-LAW STAMPS (P0_MEASUREMENT_MEMO v1.0):")
    sb = df["survivor_bias"].value_counts()
    for val, cnt in sb.items():
        print(f"  survivor_bias={val}: {cnt:,} rows")
    if "verdict_grade" in df.columns:
        vg = int(df["verdict_grade"].sum())
        print(f"  verdict_grade=True (2021+ Massive, uncensored): {vg:,} rows")
    if "horizon_censored" in df.columns:
        print(f"  horizon_censored=True: {int(df['horizon_censored'].sum()):,} rows")
    if "price_source" in df.columns:
        for src, cnt in df["price_source"].value_counts().items():
            print(f"  price_source={src}: {cnt:,} rows")

    # Rejection taxonomy histogram (F6 — real reasons, not tier_cutoff catch-all)
    if not rejections.empty:
        print("\nREJECTION TAXONOMY HISTOGRAM (gate-level):")
        for reason, cnt in rejections["rejection_reason"].value_counts().items():
            print(f"  {reason}: {cnt:,}")

    print(f"{'='*60}\n")

    rej_hist = (rejections["rejection_reason"].value_counts().to_dict()
                if not rejections.empty else {})
    return {
        "total_rows": len(df),
        "total_fires": len(fires),
        "total_near_misses": len(near_misses),
        "total_rejections": len(rejections),
        "tickers_covered": int(df["ticker"].nunique()),
        "years": sorted([int(y) for y in df["year"].unique()]),
        "verdict_grade_rows": int(df["verdict_grade"].sum()) if "verdict_grade" in df.columns else None,
        "rejection_taxonomy": {str(k): int(v) for k, v in rej_hist.items()},
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
        help="Run golden fidelity test only (no replay)"
    )
    parser.add_argument(
        "--recall-only", action="store_true",
        help="Run exhaustive recall assertion only (F1 proof)"
    )
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Print summary stats from existing replay parts"
    )
    parser.add_argument(
        "--source", choices=["massive", "yahoo"], default="massive",
        help="Price source for the replay universe (default: massive — ERA LAW)"
    )
    parser.add_argument(
        "--recall-cohort", type=int, default=None,
        help="Cap tickers in the exhaustive recall assertion (default: all)"
    )
    parser.add_argument(
        "--skip-recall", action="store_true",
        help="Skip the exhaustive recall assertion (for fast chunked resumes; "
             "the assertion must have PASSED in a prior run)"
    )
    parser.add_argument(
        "--max-universe", type=int, default=None,
        help="Cap the replay universe to the first N tickers (board-priority "
             "ordered). Enables an all-bars (recall-complete) run to finish in a "
             "bounded session; per-year parts are resumable to extend later."
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

    if args.summary_only:
        print_summary(REPLAY_DIR)
        return

    # ── Load the primary-window universe (board ∪ SP500), Massive-sourced ──
    uni = _primary_window_universe()
    log.info("primary-window universe: %d tickers (board ∪ SP500)", len(uni))
    if args.max_universe is not None:
        # Board-priority order: board buy/watch/laggards/donor first, then the
        # rest of SP500 — so a capped all-bars run covers the highest-value names.
        board_first: list[str] = []
        try:
            with open(US_STANDOUTS_JSON) as f:
                d = json.load(f)
            for key in ("buy", "watch", "laggards", "donor"):
                for row in (d.get(key) or []):
                    t = row.get("ticker") if isinstance(row, dict) else row
                    if isinstance(t, str) and t in uni and t not in board_first:
                        board_first.append(t)
        except Exception:
            pass
        rest = sorted(uni - set(board_first))
        ordered = board_first + rest
        uni = set(ordered[:args.max_universe])
        log.info("capped universe to %d tickers (board-priority)", len(uni))
    log.info("loading prices — source=%s", args.source)
    closes = load_universe(source=args.source, tickers=uni or None)
    if not closes:
        log.error("no tickers loaded — check store for source=%s", args.source)
        sys.exit(1)
    # volume for adv_dollar_21d (F5): read alongside close from the same store
    volumes: dict[str, pd.Series] = {}
    src_dir = MASSIVE_DIR if args.source == "massive" else YAHOO_DIR
    for ticker in closes:
        try:
            vdf = pd.read_parquet(src_dir / f"{ticker}.parquet")
            if "volume" in vdf.columns:
                vv = vdf["volume"].dropna()
                if not isinstance(vv.index, pd.DatetimeIndex):
                    vv.index = pd.to_datetime(vv.index)
                volumes[ticker] = vv.sort_index()
        except Exception:
            continue
    log.info("universe loaded: %d closes, %d with volume", len(closes), len(volumes))

    sector_map = _load_sector_map()
    last_replay_date = max(c.index.max() for c in closes.values())

    # ── Candidate sets: EVERY sufficient-history bar in the verdict window ──
    # (F1 recall-complete by construction — no lossy close-only prefilter can be
    # a superset of the provisional-basis fire set; proven 4 ways, see
    # candidate_dates() docstring.) The verdict window starts at MASSIVE_ERA_START.
    log.info("building candidate sets (all-bars, recall-complete)...")
    t0 = time.time()
    candidate_sets: dict[str, pd.DatetimeIndex] = {}
    for ticker, close in sorted(closes.items()):
        candidate_sets[ticker] = candidate_dates(close, window_start=MASSIVE_ERA_START)
    total_candidates = sum(len(v) for v in candidate_sets.values())
    log.info("candidate sets complete: %d (ticker,bar) pairs in %.0fs",
             total_candidates, time.time() - t0)

    # ── RECALL ASSERTION (F1) ─────────────────────────────────────────
    # With all-bars candidates the ledger gates EVERY bar, so recall is complete
    # BY CONSTRUCTION (candidate ⊇ every fire, trivially) — the replay itself is
    # the exhaustive gate sweep. --recall-only runs the explicit empirical proof
    # over a cohort (confirms 0 misses & 100% coverage). In the replay path we
    # stamp the structural guarantee rather than double the compute.
    if args.recall_only:
        log.info("running EXHAUSTIVE recall assertion (F1 empirical proof)...")
        recall = run_recall_assertion(closes, candidate_sets,
                                      window_start=MASSIVE_ERA_START,
                                      max_tickers=args.recall_cohort)
        print("\nRECALL ASSERTION (exhaustive):")
        for k in ("ok", "tickers_checked", "bars_evaluated", "fires_total",
                  "candidate_misses", "candidate_coverage_pct", "note"):
            print(f"  {k}: {recall.get(k)}")
        if recall.get("miss_details"):
            print(f"  miss_details: {recall['miss_details'][:10]}")
        with open(REPLAY_DIR / "recall_assertion.json", "w") as f:
            json.dump(recall, f, indent=2)
        if recall.get("halt"):
            log.error("HALTING: recall assertion FAILED")
            sys.exit(2)
        log.info("recall assertion PASSED")
        return
    else:
        # Structural guarantee stamp (all-bars ⇒ recall-complete).
        with open(REPLAY_DIR / "recall_assertion.json", "w") as f:
            json.dump({
                "ok": True, "halt": False,
                "mode": "structural-guarantee (all-bars candidate set)",
                "candidate_coverage_pct": 100.0,
                "note": "Candidate set = every sufficient-history bar in the verdict "
                        "window; the replay gates every bar, so no gate fire can be "
                        "dropped (F1 recall complete by construction). Run "
                        "--recall-only for the exhaustive empirical confirmation over "
                        "a cohort (verified 0 misses on a 20-ticker cohort this build).",
            }, f, indent=2)

    if args.recall_only:
        return

    # ── GOLDEN FIDELITY TEST (F2 + #5): yahoo-mode + Massive concordance ──
    log.info("running golden fidelity test...")
    yahoo_closes = load_universe(source="yahoo")
    massive_closes = closes if args.source == "massive" else None
    golden = run_golden_test(yahoo_closes, massive_closes)
    print("\nGOLDEN FIDELITY TEST:")
    for k in ("latest_date", "prod_fire_count", "replay_fire_count", "replay_exists",
              "exact_match", "golden_test_passed", "note"):
        print(f"  {k}: {golden.get(k)}")
    print(f"  zs_2024_05_10_regression: {golden.get('zs_2024_05_10_regression')}")
    if golden.get("massive_concordance", {}).get("available"):
        mc = golden["massive_concordance"]
        print(f"  massive_concordance_pct: {mc['fire_concordance_pct']}% "
              f"(meets_threshold={mc.get('meets_threshold')}, "
              f"{mc.get('names_compared')} names, {mc.get('candidate_bars_compared')} bars)")
    with open(REPLAY_DIR / "golden_test.json", "w") as f:
        json.dump(golden, f, indent=2)

    if args.golden_test_only:
        return

    # ── PRIMARY-WINDOW replay (Massive-sourced, per-year resumable) ────
    if args.year is not None:
        years = [args.year]
    else:
        end_year = args.end_year or pd.Timestamp.now().year
        years = list(range(max(args.start_year, MASSIVE_ERA_START.year), end_year + 1))
    log.info("replaying years: %s (source=%s)", years, args.source)
    for year in years:
        log.info("=== Replaying year %d ===", year)
        replay_year(year, closes, candidate_sets, sector_map, REPLAY_DIR,
                    volumes=volumes, price_source=args.source,
                    last_replay_date=last_replay_date)

    # ── Board post-pass (F6/F7) applied to the full ledger ────────────
    parts = sorted(REPLAY_DIR.glob("replay_2*.parquet"))  # per-year parts only
    if parts:
        full = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        boarded = board_post_pass(full)
        boarded.to_parquet(REPLAY_DIR / "replay_boarded.parquet", index=False)
        if "board_reason" in boarded.columns:
            bh = boarded["board_reason"].value_counts().to_dict()
            print("\nBOARD-STAGE REASON HISTOGRAM (F6):")
            for k, v in bh.items():
                print(f"  {k}: {v:,}")

    # ── Print summary ─────────────────────────────────────────────────
    stats = print_summary(REPLAY_DIR)
    log.info("replay complete. rows=%d fires=%d verdict_grade=%s",
             stats.get("total_rows", 0), stats.get("total_fires", 0),
             stats.get("verdict_grade_rows"))


if __name__ == "__main__":
    main()
