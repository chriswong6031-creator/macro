"""Behavioral fingerprint v0 — the frozen enumeration (registration §5).

A fingerprint is a flat vector of interpretable, unit-free path statistics for one
(ticker, epoch) at one date: **not** a classifier output, no discrete labels
inside the representation. W1 keys every fingerprint to ``epoch_0`` (listing to
date) and stamps ``epoch_detector = "none/provisional"`` — the detector is a PR-4
object and does not exist yet.

Two blocks, and the split is load-bearing
-----------------------------------------
* **Metric block** — continuous, label-free. The only block any future distance,
  neighborhood, or map may read. Nothing in it encodes sector, industry, cap,
  plane, or basket membership, and nothing in it is a gap-family member.
* **Diagnostic block** — sector, industry, cap bucket, plane id, venue class, the
  gap family, close-jump response. Census and baseline use only; never a distance
  input, never a map input.

Why the gap family is diagnostic-only: ``data/stocks`` has no ``open``, so the gap
family is structurally unavailable for the ~240 deepest-history names and fails
the ≥95%-of-universe availability bar. The plane-availability law says such a
family is **excluded from the metric block entirely** rather than masked per name
(masterplan §4 law vi) — otherwise a neighborhood could partition by data plane
before it partitions by behavior.

Windows
-------
Registration §5 names the windows for most features. Where it names a family's
statistic without a window, the window is pinned here and recorded in the spec
JSON, which is what ``fingerprint_spec_hash`` covers. The masterplan's "each
feature at ≥2 window lengths" is satisfied at the **family** level — the reading
that makes §5's own enumeration (several single-window members per family)
internally consistent — and that reading is recorded in the spec as
``window_law_reading`` rather than left implicit.

Causality
---------
Every value at ``asof`` is a function of rows ``<= asof`` only: the frame is
sliced before anything is computed, and no feature reads a forward window.
Truncation-invariance is test-enforced. The one exception is called out where it
lives: F3 (recovery velocity) is derived from the episode catalog, whose
*resolution* labels use future data by design (masterplan §7.2) — F3 is therefore
a research-time coordinate, masked for names with no catalogued episode, and the
catalog is never a live surface.

Cross-sectional percentiles
---------------------------
Raw values are ranked PIT against the contemporaneous evaluated universe at
``asof``. Blind-arm names participate **only** as anonymous members of those
denominators; no per-name blind row is produced anywhere.

Instability
-----------
A feature is flagged ``unstable`` when adjacent windows of the same statistic
disagree by ≥2 cross-sectional quartiles (the quartile-jump rule). Flagged, never
silently averaged.

Substrate reuse: Ulcer/NATR from ``engine.path_risk_signals``; Amihud and
Corwin-Schultz from ``engine.entry_primitives``; ATR/realized-vol from
``engine.stock_technicals``; RSI from ``engine.canon``; the gap family from
``engine.path_personality``. Moving averages are plain pandas rolling means
computed here (``engine.canon`` carries no 20/50/200DMA helper).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from engine.canon import rsi as _canon_rsi
from engine.entry_primitives import amihud_series, corwin_schultz_spread_series
from engine.path_personality import (
    _event_gap_contrib_series as _pp_event_gap_contrib,
    _gap_share_series as _pp_gap_share,
)
from engine.path_risk_signals import _ulcer_index
from engine.stock_identity.plane import PLANES_WITH_OPEN
from engine.stock_technicals import atr as _atr, realized_vol as _realized_vol

log = logging.getLogger(__name__)

SPEC_VERSION = "v0"

#: Minimum trailing sessions before ANY metric-block value is emitted. Below this a
#: name is coverage-masked (all-null + mask), never an error — the IPO stressor in
#: the pilot exists precisely to exercise this path.
MIN_SESSIONS = 252

#: ZigZag retracement threshold for the F8 swing-period statistic. A spec constant
#: (frozen in the hash), NOT a calibration constant — the fingerprint spec must not
#: depend on the sealed partition, or the two seals would be entangled.
SWING_ZIGZAG_PCT = 0.15

#: F7 bounce-rate geometry: a 50DMA "tag" requires the session's low to reach the
#: 50DMA while the prior close sat above it, in a 50>200 context; the bounce is
#: judged 10 sessions later. Minimum tags before a rate is emitted.
BOUNCE_FWD = 10
BOUNCE_MIN_TAGS = 5

#: F8 detrended-ACF band (sessions) — the 6-36 month cyclicality band of §4 F8.
ACF_BAND = (126, 756)

_UNSTABLE_QUARTILE_JUMP = 2


# ---------------------------------------------------------------------------
# The frozen enumeration
# ---------------------------------------------------------------------------
def _f(name: str, family: str, block: str, windows: Sequence[int] | None, stat: str,
       needs: Sequence[str] = ("close",)) -> dict[str, Any]:
    return {
        "name": name,
        "family": family,
        "block": block,
        "windows": list(windows) if windows else [],
        "stat": stat,
        "needs": list(needs),
    }


METRIC_FEATURES: tuple[dict[str, Any], ...] = (
    # --- F1 trend grammar -------------------------------------------------
    _f("f1_kaufman_er_63", "F1", "metric", [63], "kaufman efficiency ratio"),
    _f("f1_kaufman_er_126", "F1", "metric", [126], "kaufman efficiency ratio"),
    _f("f1_kaufman_er_252", "F1", "metric", [252], "kaufman efficiency ratio"),
    _f("f1_logprice_r2_126", "F1", "metric", [126], "R^2 of log price on time"),
    _f("f1_logprice_r2_252", "F1", "metric", [252], "R^2 of log price on time"),
    _f("f1_share_above_50dma_252", "F1", "metric", [252], "share of sessions close>SMA50"),
    _f("f1_share_above_200dma_252", "F1", "metric", [252], "share of sessions close>SMA200"),
    _f("f1_new_high_cadence_252", "F1", "metric", [252],
       "share of sessions setting a trailing-252d closing high"),
    _f("f1_new_high_cadence_756", "F1", "metric", [756],
       "share of sessions setting a trailing-252d closing high"),
    # --- F2 drawdown grammar ---------------------------------------------
    _f("f2_drawdown_median_756", "F2", "metric", [756], "median completed peak-to-trough depth"),
    _f("f2_drawdown_p90_756", "F2", "metric", [756], "P90 completed peak-to-trough depth"),
    _f("f2_resets_per_year_15pct", "F2", "metric", [756], "drawdowns >=15% per year"),
    _f("f2_resets_per_year_30pct", "F2", "metric", [756], "drawdowns >=30% per year"),
    _f("f2_time_under_water_median_756", "F2", "metric", [756],
       "median completed underwater spell length in sessions"),
    _f("f2_ulcer_126", "F2", "metric", [126], "Ulcer Index"),
    _f("f2_ulcer_252", "F2", "metric", [252], "Ulcer Index"),
    # --- F3 recovery velocity (episode-catalog derived) -------------------
    _f("f3_post_trough_63d_atr_median", "F3", "metric", None,
       "median 63-session post-durable-low advance in A0 units (episode catalog)"),
    _f("f3_time_to_50pct_retrace_median", "F3", "metric", None,
       "median sessions from durable low to 50% retrace of episode depth (episode catalog)"),
    # --- F4 mean reversion ------------------------------------------------
    _f("f4_ar1_daily_252", "F4", "metric", [252], "lag-1 autocorrelation of daily log returns"),
    _f("f4_ar1_weekly_756", "F4", "metric", [756], "lag-1 autocorrelation of weekly log returns"),
    _f("f4_variance_ratio_k5_756", "F4", "metric", [756], "Lo-MacKinlay variance ratio q=5"),
    _f("f4_variance_ratio_k20_756", "F4", "metric", [756], "Lo-MacKinlay variance ratio q=20"),
    _f("f4_mr_half_life_252", "F4", "metric", [252],
       "OU half-life of log price in sessions, capped at 252"),
    _f("f4_oscillator_dwell_extreme_252", "F4", "metric", [252],
       "mean run length of consecutive RSI(14) extreme sessions (<30 or >70)"),
    # --- F5 volatility ----------------------------------------------------
    _f("f5_realized_vol_21", "F5", "metric", [21], "annualized close-to-close realized vol"),
    _f("f5_realized_vol_63", "F5", "metric", [63], "annualized close-to-close realized vol"),
    _f("f5_realized_vol_252", "F5", "metric", [252], "annualized close-to-close realized vol"),
    _f("f5_vol_of_vol_252", "F5", "metric", [252],
       "std of the 21-session realized-vol series over 252 sessions"),
    _f("f5_acf_abs_ret_1_252", "F5", "metric", [252],
       "lag-1 autocorrelation of |daily log return| (vol clustering)"),
    _f("f5_natr_regime_spread_252", "F5", "metric", [252],
       "P75-P25 spread of nATR(14) over 252 sessions", ("close", "high", "low")),
    # --- F7 MA relations --------------------------------------------------
    _f("f7_atr_dist_20dma_252", "F7", "metric", [252],
       "mean (close-SMA20)/ATR14", ("close", "high", "low")),
    _f("f7_atr_dist_50dma_252", "F7", "metric", [252],
       "mean (close-SMA50)/ATR14", ("close", "high", "low")),
    _f("f7_atr_dist_200dma_252", "F7", "metric", [252],
       "mean (close-SMA200)/ATR14", ("close", "high", "low")),
    _f("f7_cross_freq_50dma_252", "F7", "metric", [252], "SMA50 crossings per session"),
    _f("f7_cross_freq_200dma_252", "F7", "metric", [252], "SMA200 crossings per session"),
    _f("f7_dwell_run_above_50dma_252", "F7", "metric", [252],
       "mean length of consecutive above-SMA50 runs"),
    _f("f7_dwell_run_above_200dma_252", "F7", "metric", [252],
       "mean length of consecutive above-SMA200 runs"),
    _f("f7_bounce_rate_50dma_756", "F7", "metric", [756],
       "share of 50DMA tags in a 50>200 context higher 10 sessions later",
       ("close", "high", "low")),
    # --- F8 cyclicality ---------------------------------------------------
    _f("f8_detrended_acf_peak_1260", "F8", "metric", [1260],
       "max autocorrelation of detrended log price over lags 126-756"),
    _f("f8_detrended_acf_peak_lag_1260", "F8", "metric", [1260],
       "lag in sessions of that maximum"),
    _f("f8_detrended_acf_peak_sharpness_1260", "F8", "metric", [1260],
       "(peak - band mean)/band std"),
    # Registration §5 pins 1260 for the ACF-peak members and leaves the swing-period
    # stat's window to the builder; 756 is pinned alongside 1260 so F8 satisfies the
    # family-level ">=2 windows" law and so the pair doubles as a plateau check on a
    # name's cycle length.
    _f("f8_swing_period_median_756", "F8", "metric", [756],
       "median sessions between alternating 15% ZigZag swing extremes"),
    _f("f8_swing_period_median_1260", "F8", "metric", [1260],
       "median sessions between alternating 15% ZigZag swing extremes"),
    # --- F9 factor / idiosyncratic ---------------------------------------
    _f("f9_beta_univ_ew_252", "F9", "metric", [252], "OLS beta of daily returns on UNIV_EW"),
    _f("f9_beta_univ_ew_756", "F9", "metric", [756], "OLS beta of daily returns on UNIV_EW"),
    _f("f9_idio_share_252", "F9", "metric", [252], "1 - R^2 of that regression"),
    _f("f9_idio_share_756", "F9", "metric", [756], "1 - R^2 of that regression"),
    # --- F10 liquidity ----------------------------------------------------
    _f("f10_dollar_adv_63", "F10", "metric", [63],
       "median close*volume", ("close", "volume")),
    _f("f10_dollar_adv_252", "F10", "metric", [252],
       "median close*volume", ("close", "volume")),
    _f("f10_turnover_proxy_252", "F10", "metric", [252],
       "mean(volume,21)/mean(volume,252) - share-count-free turnover proxy",
       ("close", "volume")),
    _f("f10_amihud_252", "F10", "metric", [252],
       "252-session mean of the 20-session Amihud ILLIQ", ("close", "volume")),
    _f("f10_cs_spread_252", "F10", "metric", [252],
       "252-session mean Corwin-Schultz spread", ("close", "high", "low")),
)

DIAGNOSTIC_FEATURES: tuple[dict[str, Any], ...] = (
    _f("d_sector", "diag", "diagnostic", None, "GICS sector label or UNKNOWN", ()),
    _f("d_industry", "diag", "diagnostic", None,
       "industry label - no tracked per-name industry store exists; always UNKNOWN in v0", ()),
    _f("d_cap_bucket", "diag", "diagnostic", [252],
       "dollar-ADV tercile (PROXY for market cap - no tracked per-name cap store)", ()),
    _f("d_market_cap_b", "diag", "diagnostic", None,
       "index-screener market cap in $bn where present (mixed coverage; never a stratifier)", ()),
    _f("d_price_plane_id", "diag", "diagnostic", None, "plane the history was read from", ()),
    _f("d_listing_venue_class", "diag", "diagnostic", None, "venue class or UNKNOWN", ()),
    _f("d_f6_gap_share_252", "F6", "diagnostic", [252],
       "overnight-gap share of variance (needs open)", ("open", "close")),
    _f("d_f6_event_gap_contrib_252", "F6", "diagnostic", [252],
       "top-5 gap contribution to gap variance (needs open)", ("open", "close")),
    _f("d_f6_gap_fill_rate_252", "F6", "diagnostic", [252],
       "share of gaps closing back through the prior close same session (needs open)",
       ("open", "high", "low", "close")),
    _f("d_close_jump_freq_252", "F6", "diagnostic", [252],
       "share of sessions with |close-to-close| > 2.5 trailing sigma"),
    _f("d_close_jump_drift5_252", "F6", "diagnostic", [252],
       "mean signed 5-session drift after those close jumps, in A0 units",
       ("close", "high", "low")),
)

ALL_FEATURES: tuple[dict[str, Any], ...] = METRIC_FEATURES + DIAGNOSTIC_FEATURES
METRIC_NAMES: tuple[str, ...] = tuple(f["name"] for f in METRIC_FEATURES)
DIAGNOSTIC_NAMES: tuple[str, ...] = tuple(f["name"] for f in DIAGNOSTIC_FEATURES)

#: Numeric diagnostic features that still get a cross-sectional percentile.
DIAGNOSTIC_NUMERIC: tuple[str, ...] = (
    "d_f6_gap_share_252",
    "d_f6_event_gap_contrib_252",
    "d_f6_gap_fill_rate_252",
    "d_close_jump_freq_252",
    "d_close_jump_drift5_252",
)

#: Adjacent-window pairs for the quartile-jump instability rule. Only members that
#: measure the SAME statistic at different windows are comparable.
ADJACENT_WINDOW_PAIRS: tuple[tuple[str, str], ...] = (
    ("f1_kaufman_er_63", "f1_kaufman_er_126"),
    ("f1_kaufman_er_126", "f1_kaufman_er_252"),
    ("f1_logprice_r2_126", "f1_logprice_r2_252"),
    ("f1_new_high_cadence_252", "f1_new_high_cadence_756"),
    ("f2_ulcer_126", "f2_ulcer_252"),
    ("f5_realized_vol_21", "f5_realized_vol_63"),
    ("f5_realized_vol_63", "f5_realized_vol_252"),
    ("f9_beta_univ_ew_252", "f9_beta_univ_ew_756"),
    ("f9_idio_share_252", "f9_idio_share_756"),
    ("f10_dollar_adv_63", "f10_dollar_adv_252"),
    ("f8_swing_period_median_756", "f8_swing_period_median_1260"),
)

#: Feature families whose members are structurally unavailable on an open-less plane.
#: The law: such a family is excluded from the METRIC block entirely, not masked.
PLANE_GATED_FAMILIES: tuple[str, ...] = ("F6",)

WINDOW_LAW_READING = (
    "masterplan §4's '>=2 window lengths' is applied at the FAMILY level: every "
    "feature family below carries at least two distinct windows across its members. "
    "This is the reading under which registration §5's own enumeration (which names "
    "several single-window members, e.g. time-under-water 756 and Amihud 252) is "
    "internally consistent with the masterplan."
)


def spec() -> dict[str, Any]:
    """The canonical, ordered spec object. This is what the hash covers."""
    return {
        "schema": "stock_identity.fingerprint_spec.v1",
        "version": SPEC_VERSION,
        "epoch_key": "epoch_0",
        "epoch_detector": "none/provisional",
        "min_sessions": MIN_SESSIONS,
        "window_law_reading": WINDOW_LAW_READING,
        "plane_gated_families_excluded_from_metric_block": list(PLANE_GATED_FAMILIES),
        "swing_zigzag_pct": SWING_ZIGZAG_PCT,
        "bounce_forward_sessions": BOUNCE_FWD,
        "bounce_min_tags": BOUNCE_MIN_TAGS,
        "acf_band_sessions": list(ACF_BAND),
        "unstable_rule": (
            f"adjacent-window quartile jump >= {_UNSTABLE_QUARTILE_JUMP} quartiles, "
            "quartiles taken from the cross-sectional PIT percentile at asof"
        ),
        "adjacent_window_pairs": [list(p) for p in ADJACENT_WINDOW_PAIRS],
        "universal_factor_panel": ["UNIV_EW"],
        "features": [dict(f) for f in ALL_FEATURES],
    }


def spec_hash(spec_obj: dict[str, Any] | None = None) -> str:
    """SHA256 over the canonical spec JSON — ``fingerprint_spec_hash``."""
    payload = spec_obj if spec_obj is not None else spec()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# numeric helpers (scalar-at-asof; each reads a trailing window only)
# ---------------------------------------------------------------------------
def _tail(a: np.ndarray, n: int) -> np.ndarray | None:
    if len(a) < n:
        return None
    return a[-n:]


def _kaufman_er(close: np.ndarray, n: int) -> float | None:
    w = _tail(close, n + 1)
    if w is None:
        return None
    direction = abs(float(w[-1] - w[0]))
    volatility = float(np.abs(np.diff(w)).sum())
    if volatility <= 0:
        return None
    return direction / volatility


def _logprice_r2(close: np.ndarray, n: int) -> float | None:
    w = _tail(close, n)
    if w is None or (w <= 0).any():
        return None
    y = np.log(w)
    x = np.arange(len(y), dtype=float)
    if float(np.std(y)) == 0.0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(r):
        return None
    return r * r


def _sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(n, min_periods=n).mean()


def _share_above(close: pd.Series, ma: pd.Series, n: int) -> float | None:
    both = pd.concat([close, ma], axis=1).dropna()
    if len(both) < n:
        return None
    w = both.iloc[-n:]
    return float((w.iloc[:, 0] > w.iloc[:, 1]).mean())


def _mean_run_above(close: pd.Series, ma: pd.Series, n: int) -> float | None:
    both = pd.concat([close, ma], axis=1).dropna()
    if len(both) < n:
        return None
    flag = (both.iloc[-n:, 0] > both.iloc[-n:, 1]).to_numpy()
    runs, cur = [], 0
    for v in flag:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    if not runs:
        return 0.0
    return float(np.mean(runs))


def _cross_freq(close: pd.Series, ma: pd.Series, n: int) -> float | None:
    both = pd.concat([close, ma], axis=1).dropna()
    if len(both) < n:
        return None
    flag = (both.iloc[-n:, 0] > both.iloc[-n:, 1]).to_numpy().astype(int)
    return float(np.abs(np.diff(flag)).sum()) / float(n)


def _new_high_cadence(close: np.ndarray, n: int, lookback: int = 252) -> float | None:
    if len(close) < n + lookback:
        return None
    s = pd.Series(close)
    roll_max = s.rolling(lookback, min_periods=lookback).max()
    is_high = (s >= roll_max).to_numpy()[-n:]
    return float(np.mean(is_high))


def _drawdown_episodes(close: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Completed drawdown depths (fractions >0), completed underwater durations, and
    the count of sessions covered. A drawdown runs from a running-max peak to the
    trough before the close regains that peak; the still-open spell at the right edge
    is *censored* and excluded from both arrays (never counted as a shallow one)."""
    depths: list[float] = []
    durations: list[int] = []
    if len(close) < 2:
        return np.asarray(depths), np.asarray(durations, dtype=float), len(close)
    peak = close[0]
    trough = close[0]
    peak_i = 0
    underwater = False
    for i in range(1, len(close)):
        c = close[i]
        if c >= peak:
            if underwater:
                depths.append((peak - trough) / peak)
                durations.append(i - peak_i)
                underwater = False
            peak = c
            trough = c
            peak_i = i
        else:
            underwater = True
            trough = min(trough, c)
    return (
        np.asarray(depths, dtype=float),
        np.asarray(durations, dtype=float),
        len(close),
    )


def _ar1(x: np.ndarray) -> float | None:
    x = x[np.isfinite(x)]
    if len(x) < 30 or float(np.std(x)) == 0.0:
        return None
    r = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    return r if np.isfinite(r) else None


def _variance_ratio(logret: np.ndarray, q: int) -> float | None:
    r = logret[np.isfinite(logret)]
    if len(r) < max(60, 5 * q):
        return None
    var1 = float(np.var(r, ddof=1))
    if var1 <= 0:
        return None
    agg = np.convolve(r, np.ones(q), mode="valid")  # overlapping q-period sums
    varq = float(np.var(agg, ddof=1))
    return varq / (q * var1)


def _mr_half_life(close: np.ndarray, cap: float = 252.0) -> float | None:
    w = close[close > 0]
    if len(w) < 60:
        return None
    y = np.log(w)
    lag = y[:-1]
    dy = np.diff(y)
    if float(np.std(lag)) == 0.0:
        return None
    beta = float(np.polyfit(lag, dy, 1)[0])
    if beta >= 0 or (1.0 + beta) <= 0:
        return cap  # no mean reversion detected inside the window -> report the cap
    hl = -np.log(2.0) / np.log(1.0 + beta)
    if not np.isfinite(hl) or hl < 0:
        return cap
    return float(min(hl, cap))


def _mean_extreme_run(rsi: pd.Series, n: int, low: float = 30.0, high: float = 70.0) -> float | None:
    s = rsi.dropna()
    if len(s) < n:
        return None
    flag = ((s.iloc[-n:] < low) | (s.iloc[-n:] > high)).to_numpy()
    runs, cur = [], 0
    for v in flag:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return float(np.mean(runs)) if runs else 0.0


def _detrended_acf_peak(close: np.ndarray, n: int) -> tuple[float | None, float | None, float | None]:
    w = _tail(close, n)
    if w is None or (w <= 0).any():
        return None, None, None
    y = np.log(w)
    x = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    sd = float(np.std(resid))
    if sd == 0.0:
        return None, None, None
    resid = resid - float(np.mean(resid))
    denom = float(np.dot(resid, resid))
    lo, hi = ACF_BAND
    lags = np.arange(lo, min(hi, len(resid) - 30) + 1, 7)
    if len(lags) < 5:
        return None, None, None
    vals = np.asarray([float(np.dot(resid[: len(resid) - k], resid[k:]) / denom) for k in lags])
    j = int(np.argmax(vals))
    peak = float(vals[j])
    band_sd = float(np.std(vals))
    sharpness = (peak - float(np.mean(vals))) / band_sd if band_sd > 0 else None
    return peak, float(lags[j]), sharpness


def _swing_period_median(close: np.ndarray, n: int, pct: float = SWING_ZIGZAG_PCT) -> float | None:
    """Median sessions between alternating ZigZag swing extremes (PTT swing-period
    shape). A swing flips when price retraces ``pct`` from the running extreme."""
    w = _tail(close, n)
    if w is None or len(w) < 60:
        return None
    pivots: list[int] = []
    direction = 0  # 0 undecided, +1 rising, -1 falling
    max_i, max_v = 0, float(w[0])
    min_i, min_v = 0, float(w[0])
    # While the direction is undecided the running MAX and MIN must be tracked
    # separately: collapsing them onto one "extreme" makes it track the latest price,
    # and the flip test then demands a `pct` move in a single session, which never
    # happens — the feature reads as universally unavailable rather than as a bug.
    for i in range(1, len(w)):
        c = float(w[i])
        if direction >= 0 and c > max_v:
            max_i, max_v = i, c
        if direction <= 0 and c < min_v:
            min_i, min_v = i, c
        if direction >= 0 and max_v > 0 and c <= max_v * (1.0 - pct):
            pivots.append(max_i)
            direction = -1
            min_i, min_v = i, c
        elif direction <= 0 and min_v > 0 and c >= min_v * (1.0 + pct):
            pivots.append(min_i)
            direction = 1
            max_i, max_v = i, c
    if len(pivots) < 3:
        return None
    return float(np.median(np.diff(np.asarray(pivots, dtype=float))))


def _beta_idio(ret: np.ndarray, fac: np.ndarray, n: int) -> tuple[float | None, float | None]:
    if len(ret) < n or len(fac) < n:
        return None, None
    y = ret[-n:]
    x = fac[-n:]
    m = np.isfinite(y) & np.isfinite(x)
    y, x = y[m], x[m]
    if len(y) < max(60, n // 3) or float(np.std(x)) == 0.0 or float(np.std(y)) == 0.0:
        return None, None
    beta = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))
    r = float(np.corrcoef(y, x)[0, 1])
    if not np.isfinite(beta) or not np.isfinite(r):
        return None, None
    return beta, float(1.0 - r * r)


def _gap_fill_rate(df: pd.DataFrame, n: int) -> float | None:
    """Share of material gaps that trade back through the prior close intraday."""
    if not {"open", "high", "low", "close"}.issubset(df.columns) or len(df) < n + 1:
        return None
    sub = df.iloc[-(n + 1):]
    prev_close = sub["close"].shift(1)
    gap = (sub["open"] - prev_close) / prev_close.replace(0.0, np.nan)
    material = gap.abs() > 0.01
    if int(material.sum()) < 5:
        return None
    up = material & (gap > 0)
    dn = material & (gap < 0)
    filled = pd.Series(False, index=sub.index)
    filled[up] = sub.loc[up, "low"] <= prev_close[up]
    filled[dn] = sub.loc[dn, "high"] >= prev_close[dn]
    return float(filled[material].mean())


def _close_jump_stats(df: pd.DataFrame, n: int, atr14: pd.Series) -> tuple[float | None, float | None]:
    """Frequency of >2.5-sigma close-to-close moves and their mean 5-session drift.

    The drift window is strictly forward *within the observed frame*, so the value
    at asof only uses jumps whose 5-session window has already completed. That keeps
    the statistic causal: a jump in the final 5 sessions contributes nothing."""
    close = df["close"]
    if len(close) < n + 63:
        return None, None
    lr = np.log(close / close.shift(1))
    sigma = lr.rolling(63, min_periods=63).std(ddof=0).shift(1)
    jump = (lr.abs() > 2.5 * sigma) & sigma.notna()
    window = jump.iloc[-n:]
    freq = float(window.mean())
    idx = np.flatnonzero(window.to_numpy())
    base = len(close) - n
    drifts: list[float] = []
    for j in idx:
        t = base + j
        if t + 5 >= len(close):
            continue
        a0 = float(atr14.iloc[t]) if np.isfinite(atr14.iloc[t]) else np.nan
        if not np.isfinite(a0) or a0 <= 0:
            continue
        drifts.append(float(close.iloc[t + 5] - close.iloc[t]) / a0)
    drift = float(np.mean(drifts)) if len(drifts) >= 5 else None
    return freq, drift


# ---------------------------------------------------------------------------
# per-name computation
# ---------------------------------------------------------------------------
def metric_names_for_plane(plane_id: str) -> tuple[str, ...]:
    """Metric-block names — identical on every plane, by the plane-availability law.

    The gap family is not "masked on stocks and present on baskets": it is out of
    the metric block universe-wide. This function exists so a caller cannot
    accidentally reintroduce plane-conditional metric membership.
    """
    del plane_id
    return METRIC_NAMES


def compute_raw(
    df: pd.DataFrame,
    *,
    plane_id: str,
    asof: pd.Timestamp,
    factor_returns: pd.Series | None = None,
    catalog_stats: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Raw fingerprint values for one instrument at ``asof``.

    Returns ``{feature_name: value_or_None}`` plus ``_n_sessions``. Every value is a
    function of rows ``<= asof``. A name shorter than ``MIN_SESSIONS`` returns all
    metric nulls with the session count recorded — coverage-masked, never an error.
    """
    frame = df.loc[df.index <= asof]
    out: dict[str, Any] = {name: None for name in (METRIC_NAMES + DIAGNOSTIC_NAMES)}
    out["_n_sessions"] = int(len(frame))
    out["d_price_plane_id"] = plane_id
    out["d_industry"] = "UNKNOWN"
    if len(frame) < MIN_SESSIONS:
        return out

    close = frame["close"]
    close_v = close.to_numpy(dtype=float)
    has_hl = {"high", "low"}.issubset(frame.columns)
    has_vol = "volume" in frame.columns
    has_open = "open" in frame.columns and plane_id in PLANES_WITH_OPEN

    logret = np.log(close / close.shift(1)).to_numpy(dtype=float)[1:]

    atr14 = (
        _atr(frame["high"], frame["low"], close, n=14)
        if has_hl
        else pd.Series(np.nan, index=frame.index)
    )

    # --- F1 --------------------------------------------------------------
    for n in (63, 126, 252):
        out[f"f1_kaufman_er_{n}"] = _kaufman_er(close_v, n)
    for n in (126, 252):
        out[f"f1_logprice_r2_{n}"] = _logprice_r2(close_v, n)
    sma20, sma50, sma200 = _sma(close, 20), _sma(close, 50), _sma(close, 200)
    out["f1_share_above_50dma_252"] = _share_above(close, sma50, 252)
    out["f1_share_above_200dma_252"] = _share_above(close, sma200, 252)
    out["f1_new_high_cadence_252"] = _new_high_cadence(close_v, 252)
    out["f1_new_high_cadence_756"] = _new_high_cadence(close_v, 756)

    # --- F2 --------------------------------------------------------------
    w756 = _tail(close_v, 756)
    if w756 is not None:
        depths, durations, _ = _drawdown_episodes(w756)
        if len(depths):
            out["f2_drawdown_median_756"] = float(np.median(depths))
            out["f2_drawdown_p90_756"] = float(np.percentile(depths, 90))
            years = 756.0 / 252.0
            out["f2_resets_per_year_15pct"] = float((depths >= 0.15).sum()) / years
            out["f2_resets_per_year_30pct"] = float((depths >= 0.30).sum()) / years
        else:
            out["f2_drawdown_median_756"] = 0.0
            out["f2_drawdown_p90_756"] = 0.0
            out["f2_resets_per_year_15pct"] = 0.0
            out["f2_resets_per_year_30pct"] = 0.0
        if len(durations):
            out["f2_time_under_water_median_756"] = float(np.median(durations))
    for n in (126, 252):
        ui = _ulcer_index(close, n=n)
        v = float(ui.iloc[-1]) if len(ui) and np.isfinite(ui.iloc[-1]) else None
        out[f"f2_ulcer_{n}"] = v

    # --- F3 (episode-catalog derived) ------------------------------------
    if catalog_stats:
        for key in ("f3_post_trough_63d_atr_median", "f3_time_to_50pct_retrace_median"):
            v = catalog_stats.get(key)
            out[key] = None if v is None or not np.isfinite(float(v)) else float(v)

    # --- F4 --------------------------------------------------------------
    out["f4_ar1_daily_252"] = _ar1(logret[-252:]) if len(logret) >= 252 else None
    weekly = close.resample("W-FRI").last().dropna()
    wlr = np.log(weekly / weekly.shift(1)).to_numpy(dtype=float)[1:]
    if len(close) >= 756:
        n_weeks = 756 // 5
        out["f4_ar1_weekly_756"] = _ar1(wlr[-n_weeks:]) if len(wlr) >= n_weeks else None
    if len(logret) >= 756:
        out["f4_variance_ratio_k5_756"] = _variance_ratio(logret[-756:], 5)
        out["f4_variance_ratio_k20_756"] = _variance_ratio(logret[-756:], 20)
    out["f4_mr_half_life_252"] = _mr_half_life(close_v[-252:])
    out["f4_oscillator_dwell_extreme_252"] = _mean_extreme_run(_canon_rsi(close, 14), 252)

    # --- F5 --------------------------------------------------------------
    for n in (21, 63, 252):
        rv = _realized_vol(close, n=n)
        v = float(rv.iloc[-1]) if len(rv) and np.isfinite(rv.iloc[-1]) else None
        out[f"f5_realized_vol_{n}"] = v
    rv21 = _realized_vol(close, n=21)
    if rv21.notna().sum() >= 252:
        out["f5_vol_of_vol_252"] = float(rv21.dropna().iloc[-252:].std(ddof=0))
    out["f5_acf_abs_ret_1_252"] = _ar1(np.abs(logret[-252:])) if len(logret) >= 252 else None
    if has_hl:
        natr = 100.0 * atr14 / close.replace(0.0, np.nan)
        nn = natr.dropna()
        if len(nn) >= 252:
            tail = nn.iloc[-252:]
            out["f5_natr_regime_spread_252"] = float(
                np.percentile(tail, 75) - np.percentile(tail, 25)
            )

    # --- F7 --------------------------------------------------------------
    if has_hl:
        for n, ma in ((20, sma20), (50, sma50), (200, sma200)):
            both = pd.concat([close, ma, atr14], axis=1).dropna()
            if len(both) >= 252:
                w = both.iloc[-252:]
                a0 = w.iloc[:, 2].replace(0.0, np.nan)
                out[f"f7_atr_dist_{n}dma_252"] = float(
                    ((w.iloc[:, 0] - w.iloc[:, 1]) / a0).mean()
                )
    out["f7_cross_freq_50dma_252"] = _cross_freq(close, sma50, 252)
    out["f7_cross_freq_200dma_252"] = _cross_freq(close, sma200, 252)
    out["f7_dwell_run_above_50dma_252"] = _mean_run_above(close, sma50, 252)
    out["f7_dwell_run_above_200dma_252"] = _mean_run_above(close, sma200, 252)
    if has_hl and len(frame) >= 756 + BOUNCE_FWD:
        sub = frame.iloc[-(756 + BOUNCE_FWD):]
        s50 = _sma(sub["close"], 50)
        s200 = _sma(sub["close"], 200)
        tags = 0
        hits = 0
        cl = sub["close"].to_numpy(dtype=float)
        lo = sub["low"].to_numpy(dtype=float)
        a50 = s50.to_numpy(dtype=float)
        a200 = s200.to_numpy(dtype=float)
        for i in range(1, len(sub) - BOUNCE_FWD):
            if not (np.isfinite(a50[i]) and np.isfinite(a200[i]) and np.isfinite(a50[i - 1])):
                continue
            if not (a50[i] > a200[i] and cl[i - 1] > a50[i - 1]):
                continue
            if lo[i] <= a50[i]:
                tags += 1
                if cl[i + BOUNCE_FWD] > cl[i]:
                    hits += 1
        if tags >= BOUNCE_MIN_TAGS:
            out["f7_bounce_rate_50dma_756"] = float(hits) / float(tags)

    # --- F8 --------------------------------------------------------------
    peak, lag, sharp = _detrended_acf_peak(close_v, 1260)
    out["f8_detrended_acf_peak_1260"] = peak
    out["f8_detrended_acf_peak_lag_1260"] = lag
    out["f8_detrended_acf_peak_sharpness_1260"] = sharp
    out["f8_swing_period_median_756"] = _swing_period_median(close_v, 756)
    out["f8_swing_period_median_1260"] = _swing_period_median(close_v, 1260)

    # --- F9 --------------------------------------------------------------
    if factor_returns is not None and len(factor_returns):
        aligned = pd.DataFrame(
            {"r": np.log(close / close.shift(1)), "f": factor_returns.reindex(close.index)}
        ).dropna()
        rr = aligned["r"].to_numpy(dtype=float)
        ff = aligned["f"].to_numpy(dtype=float)
        for n in (252, 756):
            b, idio = _beta_idio(rr, ff, n)
            out[f"f9_beta_univ_ew_{n}"] = b
            out[f"f9_idio_share_{n}"] = idio

    # --- F10 -------------------------------------------------------------
    if has_vol:
        dv = close * frame["volume"]
        for n in (63, 252):
            r = dv.rolling(n, min_periods=n).median()
            out[f"f10_dollar_adv_{n}"] = (
                float(r.iloc[-1]) if len(r) and np.isfinite(r.iloc[-1]) else None
            )
        v21 = frame["volume"].rolling(21, min_periods=21).mean()
        v252 = frame["volume"].rolling(252, min_periods=252).mean()
        if np.isfinite(v21.iloc[-1]) and np.isfinite(v252.iloc[-1]) and v252.iloc[-1] > 0:
            out["f10_turnover_proxy_252"] = float(v21.iloc[-1] / v252.iloc[-1])
        am = amihud_series(close, frame["volume"], win=20)
        am252 = am.rolling(252, min_periods=252).mean()
        if len(am252) and np.isfinite(am252.iloc[-1]):
            out["f10_amihud_252"] = float(am252.iloc[-1])
    if has_hl:
        cs = corwin_schultz_spread_series(frame["high"], frame["low"])
        cs252 = cs.rolling(252, min_periods=252).mean()
        if len(cs252) and np.isfinite(cs252.iloc[-1]):
            out["f10_cs_spread_252"] = float(cs252.iloc[-1])

    # --- diagnostic block -------------------------------------------------
    if has_open:
        gs = _pp_gap_share(frame["open"], close)
        if len(gs) and np.isfinite(gs.iloc[-1]):
            out["d_f6_gap_share_252"] = float(gs.iloc[-1])
        eg = _pp_event_gap_contrib(frame["open"], close)
        if len(eg) and np.isfinite(eg.iloc[-1]):
            out["d_f6_event_gap_contrib_252"] = float(eg.iloc[-1])
        out["d_f6_gap_fill_rate_252"] = _gap_fill_rate(frame, 252)
    if has_hl:
        freq, drift = _close_jump_stats(frame, 252, atr14)
        out["d_close_jump_freq_252"] = freq
        out["d_close_jump_drift5_252"] = drift

    return out


def coverage_mask(raw: dict[str, Any], names: Iterable[str] | None = None) -> dict[str, bool]:
    """``{feature: True if a value is present}`` — the mask that rides with the row."""
    keys = tuple(names) if names is not None else (METRIC_NAMES + DIAGNOSTIC_NUMERIC)
    return {k: raw.get(k) is not None for k in keys}


# ---------------------------------------------------------------------------
# cross-section
# ---------------------------------------------------------------------------
def cross_sectional_percentiles(
    values: pd.DataFrame, names: Sequence[str] | None = None
) -> pd.DataFrame:
    """PIT percentile rank (0-100) of each name's value within the contemporaneous
    universe column. Nulls stay null (a missing value is not a low rank)."""
    cols = list(names) if names is not None else [
        c for c in values.columns if c in set(METRIC_NAMES) | set(DIAGNOSTIC_NUMERIC)
    ]
    out = {}
    for c in cols:
        s = pd.to_numeric(values[c], errors="coerce")
        out[c] = s.rank(pct=True, na_option="keep") * 100.0
    return pd.DataFrame(out, index=values.index)


def _quartile(pct: float | None) -> int | None:
    if pct is None or not np.isfinite(pct):
        return None
    return int(min(3, max(0, int(pct // 25.0)))) + 1


def unstable_flags(percentiles: pd.DataFrame) -> pd.DataFrame:
    """Adjacent-window quartile-jump instability, per name per feature.

    A feature is unstable for a name when it and its adjacent-window sibling sit
    ``>= 2`` quartiles apart in the cross-section. Both members of the pair are
    flagged: the disagreement is a property of the pair, not of one side.
    """
    flags = pd.DataFrame(False, index=percentiles.index, columns=list(percentiles.columns))
    for a, b in ADJACENT_WINDOW_PAIRS:
        if a not in percentiles.columns or b not in percentiles.columns:
            continue
        qa = percentiles[a].map(_quartile)
        qb = percentiles[b].map(_quartile)
        both = qa.notna() & qb.notna()
        jump = both & ((qa - qb).abs() >= _UNSTABLE_QUARTILE_JUMP)
        flags.loc[jump, a] = True
        flags.loc[jump, b] = True
    return flags


def universe_equal_weight_factor(returns_by_symbol: dict[str, pd.Series]) -> pd.Series:
    """UNIV_EW — the declared universal factor panel v0.

    Equal-weight mean daily log return across every evaluated-universe name present
    on each date. On-plane and identical for every name, which is what keeps the
    §10 miner-emergence test non-tautological: no commodity factor exists in v0, so
    a miner cluster cannot emerge because we handed it a gold factor.
    """
    if not returns_by_symbol:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(returns_by_symbol)
    return frame.mean(axis=1, skipna=True).rename("UNIV_EW")
