"""Fear/Greed composite v1 — DISPLAY-ONLY sentiment context (P1.2).

Computes a 0-100 dial (100 = greed) as an equal-weight z-mean of qualifying legs,
each z-scored against its own trailing history and oriented so that a positive z
points toward greed.

HARD RULE (R4 min-history gate): a leg enters the z-mean ONLY with
  - >=252 daily observations covering its z-window
  - >=104 weekly observations
  - >=40 lower-frequency (quarterly) observations

Younger legs are EXCLUDED from the composite and returned as raw context tiles
in the ``young_tiles`` key (not flagged-but-included, strictly excluded).

Legs (orientation = greed-positive):
  spx_momentum   SPY close vs 125d MA  (above MA = greed)
  nh_nl_ratio    breadth nh/(nh+nl)    (high = greed)
  mcclellan      McClellan oscillator  (positive = greed)
  hy_oas         HY OAS                (low OAS = greed, so negated)
  safe_haven     SPY−TLT 20d rel ret   (SPY > TLT = greed)
  vix_level      VIX level             (low = greed, negated)
  vix_trend      VIX 20d change        (falling = greed, negated)
  vix_term       VIX/VIX3M             (low = greed/contango, negated)
  skew           CBOE SKEW             (low SKEW = less tail fear = greed, negated)
  naaim          NAAIM exposure        (high = greed)
  insider        quarterly net buy $   (net buying = greed)

Young legs (not enough history at the gate threshold):
  putcall, aaii  — rendered as raw context tiles, never enter z-mean.

Output structure (JSON-serialisable):
  {
    "dial": 0-100 int,
    "label_en": str,      # Extreme Fear / Fear / Neutral / Greed / Extreme Greed
    "label_zh": str,
    "legs_included": [...],       # leg dicts that entered the composite
    "legs_excluded_young": [...], # leg dicts that were young (below gate)
    "as_of": "YYYY-MM-DD",
    "generated_utc": "...",
    "disclaimer_en": str,
    "disclaimer_zh": str,
  }

Leg dict:
  {
    "key": str,
    "name_en": str, "name_zh": str,
    "value": float | None,      # raw value
    "z": float | None,          # z-score (greed-positive)
    "pct": int | None,          # 0-100 percentile in own history (greed direction)
    "pct_hist": list[float],    # 0-100 percentile-through-time, last 60 obs, oldest→newest
                                # same greed-direction convention as pct (inverted for lower=greed legs)
                                # [] when data missing or series too short
    "freshness": str,           # "fresh" / "stale" / "young" / "missing"
    "obs_count": int | None,
    "orientation": str,         # "higher=greed" / "lower=greed"
    "unit": str,
  }
"""
from __future__ import annotations

import glob
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Min-history gate thresholds (R4)
# ---------------------------------------------------------------------------
DAILY_MIN = 252
WEEKLY_MIN = 104
QUARTERLY_MIN = 40

# Dial band thresholds (0-100, greed=high)
_BANDS = [
    (20, "Extreme Fear",  "极度恐惧"),
    (40, "Fear",          "恐惧"),
    (60, "Neutral",       "中性"),
    (80, "Greed",         "贪婪"),
    (101, "Extreme Greed", "极度贪婪"),
]


def _r(x, n: int = 3) -> float | None:
    """Round to n decimal places, return None for NaN/inf."""
    if x is None:
        return None
    try:
        f = float(x)
        return round(f, n) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _last(s: pd.Series) -> float | None:
    """Last finite value of a series."""
    s = s.dropna()
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return v if np.isfinite(v) else None


def _z_score(series: pd.Series, window: int | None = None) -> pd.Series:
    """Rolling z-score (centre=mean, scale=std). window=None uses full expanding."""
    if window:
        mu = series.rolling(window, min_periods=DAILY_MIN).mean()
        sd = series.rolling(window, min_periods=DAILY_MIN).std()
    else:
        mu = series.expanding(min_periods=DAILY_MIN).mean()
        sd = series.expanding(min_periods=DAILY_MIN).std()
    z = (series - mu) / sd.replace(0, np.nan)
    return z


def _pct_in_history(series: pd.Series, latest_val: float) -> int | None:
    """Percentile of latest_val in the full history of series (0-100)."""
    valid = series.dropna()
    if len(valid) < 2:
        return None
    pct = float((valid <= latest_val).mean())
    return int(round(pct * 100))


def _pct_hist(series: pd.Series, n: int = 60) -> list[float]:
    """Percentile-through-time for the sparkline.

    For each of the last *n* observations, returns its percentile within the
    FULL history up to that point (same expanding-window convention as
    ``_pct_in_history`` — no look-ahead bias).  Oldest→newest order.

    Null-safe: returns [] for an empty or too-short series.  NaNs are dropped
    before ranking so they never produce spurious values.  Values are rounded
    to 1 dp to keep the JSON payload light (11 legs × 60 points ≈ 660 floats).
    """
    s = series.dropna()
    if len(s) < 2:
        return []
    # Work on the last n observations only (cap window; full history still used
    # for ranking via expanding iloc slice).
    tail_start = max(0, len(s) - n)
    result: list[float] = []
    for i in range(tail_start, len(s)):
        # history up to and including index i (expanding, point-in-time)
        history = s.iloc[: i + 1]
        val = float(s.iloc[i])
        pct = float((history <= val).mean()) * 100.0
        result.append(round(pct, 1))
    return result


def _dial_band(dial: int) -> tuple[str, str]:
    for threshold, en, zh in _BANDS:
        if dial < threshold:
            return en, zh
    return "Extreme Greed", "极度贪婪"


# ---------------------------------------------------------------------------
# Individual leg builders — each returns a leg dict
# ---------------------------------------------------------------------------

def _leg_spx_momentum() -> dict:
    """SPY close vs 125-day MA: above MA = greed."""
    key = "spx_momentum"
    meta = {"key": key, "name_en": "SPX momentum (vs 125d MA)",
            "name_zh": "标普动量（对比125日均线）",
            "orientation": "higher=greed", "unit": "% above/below MA"}
    try:
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None}
        c = spy["close"].dropna()
        obs = len(c)
        ma = c.rolling(125, min_periods=100).mean()
        spread = (c / ma - 1) * 100          # % above MA; positive = greed
        z_s = _z_score(spread)
        z_val = _last(z_s)
        raw = _last(spread)
        pct = _pct_in_history(spread.dropna(), raw) if raw is not None else None
        ts_max = spy.index.max()
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 2), "z": _r(z_val),
                "pct": pct, "pct_hist": _pct_hist(spread), "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_nh_nl_ratio() -> dict:
    """52-week high/low ratio: nh/(nh+nl). High = greed."""
    key = "nh_nl_ratio"
    meta = {"key": key, "name_en": "52-week strength (new-high ratio)",
            "name_zh": "52周强势（新高比例）",
            "orientation": "higher=greed", "unit": "ratio 0-1"}
    try:
        b = store.read("breadth", "breadth")
        if b is None or "nh" not in b.columns or "nl" not in b.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None}
        nh = b["nh"].dropna()
        nl = b["nl"].reindex(nh.index).fillna(0)
        tot = nh + nl
        ratio = (nh / tot.replace(0, np.nan)).dropna()
        obs = len(ratio)
        z_s = _z_score(ratio)
        z_val = _last(z_s)
        raw = _last(ratio)
        pct = _pct_in_history(ratio, raw) if raw is not None else None
        ts_max = ratio.index.max()
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw), "z": _r(z_val),
                "pct": pct, "pct_hist": _pct_hist(ratio), "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_mcclellan() -> dict:
    """McClellan oscillator (reuses engine.advanced_breadth). Positive = greed."""
    key = "mcclellan"
    meta = {"key": key, "name_en": "McClellan oscillator",
            "name_zh": "麦克莱伦振荡器",
            "orientation": "higher=greed", "unit": "oscillator"}
    try:
        from engine.advanced_breadth import mcclellan as _mcc
        b = store.read("breadth", "breadth")
        if b is None or "adv" not in b.columns or "dec" not in b.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None}
        adv = b["adv"].dropna()
        dec = b["dec"].reindex(adv.index).fillna(0)
        # Rebuild oscillator series for z-scoring (mcclellan() only returns latest dict)
        from engine.advanced_breadth import _ratio_net_adv
        rana = _ratio_net_adv(adv, dec).dropna()
        obs = len(rana)
        if obs < 39 + 5:       # need slow+5 for warm-up
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": obs}
        osc = (rana.ewm(span=19, adjust=False).mean()
               - rana.ewm(span=39, adjust=False).mean())
        z_s = _z_score(osc)
        z_val = _last(z_s)
        raw = _last(osc)
        pct = _pct_in_history(osc.dropna(), raw) if raw is not None else None
        ts_max = osc.index.max()
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 1), "z": _r(z_val),
                "pct": pct, "pct_hist": _pct_hist(osc), "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_hy_oas() -> dict:
    """HY OAS: BAMLH0A0HYM2. Falling OAS = greed, so negate z-score.
    Fallback: HYG/IEF price ratio."""
    key = "hy_oas"
    meta = {"key": key, "name_en": "Junk demand (HY OAS)",
            "name_zh": "高收益需求（HY 利差）",
            "orientation": "lower=greed", "unit": "OAS bps"}
    try:
        oas_df = store.read("fred", "BAMLH0A0HYM2")
        primary_ok = False
        if oas_df is not None and "hy_oas" in oas_df.columns:
            oas = oas_df["hy_oas"].dropna()
            obs = len(oas)
            if obs >= DAILY_MIN:
                primary_ok = True

        if primary_ok:
            z_s = _z_score(oas)
            z_val = _last(-z_s)      # negate: lower OAS = greed = positive z
            raw = _last(oas)
            pct_raw = _pct_in_history(oas.dropna(), raw)
            # invert pct: high OAS = high percentile = fear = low greed pct
            pct = (100 - pct_raw) if pct_raw is not None else None
            # invert pct_hist: lower OAS = greed direction (same convention as pct)
            pct_hist_raw = _pct_hist(oas)
            pct_hist = [round(100.0 - v, 1) for v in pct_hist_raw]
            ts_max = oas.index.max()
            fresh = _freshness(ts_max)
            return {**meta, "value": _r(raw, 2), "z": _r(z_val),
                    "pct": pct, "pct_hist": pct_hist, "freshness": fresh,
                    "obs_count": obs, "last_date": _ts_iso(ts_max)}
        else:
            # fallback: HYG/IEF price ratio (higher ratio = greed — no inversion needed)
            hyg = store.read("yahoo", "HYG")
            ief = store.read("yahoo", "IEF")
            if hyg is None or ief is None:
                return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                        "freshness": "missing", "obs_count": 0, "last_date": None}
            hc = hyg["close"].dropna() if "close" in hyg.columns else pd.Series(dtype=float)
            ic = ief["close"].dropna() if "close" in ief.columns else pd.Series(dtype=float)
            ratio = (hc / ic.reindex(hc.index).ffill(limit=5)).dropna()
            obs = len(ratio)
            z_s = _z_score(ratio)
            z_val = _last(z_s)       # higher ratio = greed
            raw = _last(ratio)
            pct = _pct_in_history(ratio.dropna(), raw) if raw is not None else None
            ts_max = ratio.index.max() if obs else None
            fresh = _freshness(ts_max)
            meta["unit"] = "HYG/IEF ratio (fallback)"
            return {**meta, "value": _r(raw), "z": _r(z_val),
                    "pct": pct, "pct_hist": _pct_hist(ratio), "freshness": fresh,
                    "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_safe_haven() -> dict:
    """Safe haven: SPY vs TLT 20-day relative return. SPY > TLT = greed."""
    key = "safe_haven"
    meta = {"key": key, "name_en": "Safe haven demand (SPY − TLT 20d)",
            "name_zh": "避险需求（SPY−TLT 20日）",
            "orientation": "higher=greed", "unit": "20d ret diff %"}
    try:
        spy = store.read("yahoo", "SPY")
        tlt = store.read("yahoo", "TLT")
        if spy is None or tlt is None:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None, "last_date": None}
        sc = spy["close"].dropna() if "close" in spy.columns else pd.Series(dtype=float)
        tc = tlt["close"].dropna() if "close" in tlt.columns else pd.Series(dtype=float)
        # align on common dates
        sc, tc = sc.align(tc, join="inner")
        spy_ret = sc.pct_change(20)
        tlt_ret = tc.pct_change(20)
        diff = (spy_ret - tlt_ret) * 100    # positive = SPY outperforms = greed
        diff = diff.dropna()
        obs = len(diff)
        z_s = _z_score(diff)
        z_val = _last(z_s)
        raw = _last(diff)
        pct = _pct_in_history(diff, raw) if raw is not None else None
        ts_max = diff.index.max() if obs else None
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 2), "z": _r(z_val),
                "pct": pct, "pct_hist": _pct_hist(diff), "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_vix_level() -> dict:
    """VIX level: low VIX = greed, negate z."""
    key = "vix_level"
    meta = {"key": key, "name_en": "VIX level",
            "name_zh": "VIX 水平",
            "orientation": "lower=greed", "unit": "VIX points"}
    try:
        v = store.read("yahoo", "_VIX")
        if v is None or "close" not in v.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None, "last_date": None}
        c = v["close"].dropna()
        obs = len(c)
        z_s = _z_score(c)
        z_val = _last(-z_s)          # negate: low VIX = greed
        raw = _last(c)
        pct_raw = _pct_in_history(c, raw)
        pct = (100 - pct_raw) if pct_raw is not None else None   # invert: low = greedy
        # invert pct_hist: low VIX = greed direction
        pct_hist_raw = _pct_hist(c)
        pct_hist = [round(100.0 - v, 1) for v in pct_hist_raw]
        ts_max = c.index.max()
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 1), "z": _r(z_val),
                "pct": pct, "pct_hist": pct_hist, "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_vix_trend() -> dict:
    """VIX 20-day change: falling = greed, negate z."""
    key = "vix_trend"
    meta = {"key": key, "name_en": "VIX trend (20d change)",
            "name_zh": "VIX 趋势（20日变动）",
            "orientation": "lower=greed", "unit": "VIX 20d delta"}
    try:
        v = store.read("yahoo", "_VIX")
        if v is None or "close" not in v.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None, "last_date": None}
        c = v["close"].dropna()
        chg = c.diff(20).dropna()
        obs = len(chg)
        z_s = _z_score(chg)
        z_val = _last(-z_s)          # negate: falling VIX = greed
        raw = _last(chg)
        pct_raw = _pct_in_history(chg, raw)
        pct = (100 - pct_raw) if pct_raw is not None else None
        # invert pct_hist: falling VIX = greed direction
        pct_hist_raw = _pct_hist(chg)
        pct_hist = [round(100.0 - v, 1) for v in pct_hist_raw]
        ts_max = chg.index.max() if obs else None
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 2), "z": _r(z_val),
                "pct": pct, "pct_hist": pct_hist, "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_vix_term() -> dict:
    """VIX/VIX3M term structure (canon). Low = contango = greed, negate z."""
    key = "vix_term"
    meta = {"key": key, "name_en": "VIX term structure (VIX/VIX3M)",
            "name_zh": "VIX 期限结构（VIX/VIX3M）",
            "orientation": "lower=greed", "unit": "ratio (>=1=backwardation)"}
    try:
        from engine import canon
        v = store.read("yahoo", "_VIX")
        v3 = store.read("yahoo", "_VIX3M")
        if v is None or v3 is None:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None, "last_date": None}
        vc = v["close"].dropna() if "close" in v.columns else pd.Series(dtype=float)
        v3c = v3["close"].dropna() if "close" in v3.columns else pd.Series(dtype=float)
        # canon.vix_term for the series
        ratio = canon.vix_term(vc, v3c).dropna()
        obs = len(ratio)
        z_s = _z_score(ratio)
        z_val = _last(-z_s)          # negate: low ratio (contango) = greed
        raw = _last(ratio)
        pct_raw = _pct_in_history(ratio, raw)
        pct = (100 - pct_raw) if pct_raw is not None else None
        # invert pct_hist: low ratio (contango) = greed direction
        pct_hist_raw = _pct_hist(ratio)
        pct_hist = [round(100.0 - v, 1) for v in pct_hist_raw]
        ts_max = ratio.index.max() if obs else None
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 3), "z": _r(z_val),
                "pct": pct, "pct_hist": pct_hist, "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_skew() -> dict:
    """CBOE SKEW: low SKEW = less tail fear = greed, negate z."""
    key = "skew"
    meta = {"key": key, "name_en": "CBOE SKEW (tail risk pricing)",
            "name_zh": "CBOE SKEW（尾部风险定价）",
            "orientation": "lower=greed", "unit": "SKEW index"}
    try:
        sk = store.read("cboe", "skew")
        if sk is None or "skew" not in sk.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None, "last_date": None}
        s = sk["skew"].dropna()
        obs = len(s)
        z_s = _z_score(s)
        z_val = _last(-z_s)          # negate: low SKEW = greed
        raw = _last(s)
        pct_raw = _pct_in_history(s, raw)
        pct = (100 - pct_raw) if pct_raw is not None else None
        # invert pct_hist: low SKEW = greed direction
        pct_hist_raw = _pct_hist(s)
        pct_hist = [round(100.0 - v, 1) for v in pct_hist_raw]
        ts_max = s.index.max()
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 1), "z": _r(z_val),
                "pct": pct, "pct_hist": pct_hist, "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


def _leg_naaim() -> dict:
    """NAAIM exposure: high exposure = greed. Weekly, min=104 obs."""
    key = "naaim"
    meta = {"key": key, "name_en": "NAAIM exposure",
            "name_zh": "NAAIM 仓位敞口",
            "orientation": "higher=greed", "unit": "% exposure 0-200"}
    try:
        df = store.read("sentiment", "naaim")
        if df is None or "naaim_exposure" not in df.columns:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": None, "last_date": None}
        n = df["naaim_exposure"].dropna()
        obs = len(n)
        z_s = n.expanding(min_periods=WEEKLY_MIN).apply(
            lambda x: (x.iloc[-1] - x.mean()) / (x.std() or np.nan), raw=False)
        z_val = _last(z_s)
        raw = _last(n)
        pct = _pct_in_history(n, raw) if raw is not None else None
        ts_max = n.index.max()
        fresh = _freshness(ts_max)
        return {**meta, "value": _r(raw, 1), "z": _r(z_val),
                "pct": pct, "pct_hist": _pct_hist(n), "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


_INSIDER_TXN_CAP_USD = 1e8   # $100 M: realistic ceiling for a single Form-4 transaction

def _build_insider_time_series() -> pd.Series:
    """Aggregate quarterly insider net buy$ from panel store as a time-series
    indexed by quarter end date. Returns empty Series on any shortfall.

    Data quality notes:
    - Dedup on (ticker, trans_date, code, shares, price) to drop duplicate rows
      that appear when a single Form-4 amendment is stored more than once.
    - Cap individual transaction usd at _INSIDER_TXN_CAP_USD: the raw panel
      occasionally carries price values that are orders-of-magnitude wrong
      (e.g. price in cents instead of dollars, or EDGAR data-entry errors),
      producing individual rows in the multi-trillion-dollar range.  Any
      single insider trade above $100 M is already exceptional; capping there
      keeps the quarterly aggregate realistic (~single-digit to ~$50 B) while
      not distorting the signal direction.
    """
    panel_dir = config.data_dir() / "sec_insider" / "panel"
    if not panel_dir.exists():
        return pd.Series(dtype=float)
    files = sorted(glob.glob(str(panel_dir / "*.parquet")))
    records: list[dict] = []
    for fp in files:
        try:
            df = pd.read_parquet(fp)
            if df.empty or "code" not in df.columns or "usd" not in df.columns:
                continue
            q = df["quarter"].iloc[0] if "quarter" in df.columns else None
            if not q:
                continue
            # Dedup: a Form-4 amendment can land in the same quarter file twice
            dedup_cols = [c for c in ("ticker", "trans_date", "code", "shares", "price")
                          if c in df.columns]
            if dedup_cols:
                df = df.drop_duplicates(subset=dedup_cols)
            # Cap per-transaction usd to filter out corrupt price rows
            df = df[df["usd"] <= _INSIDER_TXN_CAP_USD]
            buys = df[df["code"] == "P"]["usd"].sum()
            sells = df[df["code"] == "S"]["usd"].sum()
            records.append({"quarter": q, "net_usd": buys - sells})
        except Exception:  # noqa: BLE001
            continue
    if not records:
        return pd.Series(dtype=float)
    ts = (pd.DataFrame(records)
          .sort_values("quarter")
          .drop_duplicates("quarter", keep="last")
          .reset_index(drop=True))
    # Parse quarter labels (e.g. "2022q3") to period-end dates
    def _quarter_to_date(q: str) -> pd.Timestamp | None:
        try:
            yr, qn = q.lower().split("q")
            month = int(qn) * 3
            return pd.Timestamp(int(yr), month, 1) + pd.offsets.MonthEnd(0)
        except Exception:  # noqa: BLE001
            return None
    ts["date"] = ts["quarter"].map(_quarter_to_date)
    ts = ts.dropna(subset=["date"])
    return ts.set_index("date")["net_usd"]


def _leg_insider() -> dict:
    """Insider net buy$ (quarterly). Net buying = greed."""
    key = "insider"
    meta = {"key": key, "name_en": "Insider demand (quarterly net buy $)",
            "name_zh": "内部人需求（季度净购入）",
            "orientation": "higher=greed", "unit": "net USD billions"}
    try:
        ts = _build_insider_time_series()
        obs = len(ts)
        if obs == 0:
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": 0, "last_date": None}
        # normalise to billions
        ts_b = ts / 1e9
        # Sanity gate: if any quarterly net value exceeds ±200 B something is wrong
        if ts_b.abs().max() > 200:
            log.error(
                "insider: implausible net_usd values (max abs=%.1f B); "
                "skipping leg to avoid displaying broken data",
                ts_b.abs().max(),
            )
            return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                    "freshness": "missing", "obs_count": obs, "last_date": None}
        # z-score with expanding window, min_periods=QUARTERLY_MIN
        mu = ts_b.expanding(min_periods=QUARTERLY_MIN).mean()
        sd = ts_b.expanding(min_periods=QUARTERLY_MIN).std()
        z_s = (ts_b - mu) / sd.replace(0, np.nan)
        z_val = _last(z_s)
        raw = _last(ts_b)
        pct = _pct_in_history(ts_b, raw) if raw is not None else None
        # Use a quarterly-cadence staleness window (95 days ≈ one quarter + buffer)
        # so that quarterly data is not incorrectly reported as 'stale'
        ts_max = ts.index.max()
        fresh = _freshness(ts_max, stale_days=48)   # 48*2=96 days
        return {**meta, "value": _r(raw, 1), "z": _r(z_val),
                "pct": pct, "pct_hist": _pct_hist(ts_b), "freshness": fresh,
                "obs_count": obs, "last_date": _ts_iso(ts_max)}
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %s", key, e)
        return {**meta, "value": None, "z": None, "pct": None, "pct_hist": [],
                "freshness": "missing", "obs_count": None, "last_date": None}


# ---------------------------------------------------------------------------
# Young-tile builders (excluded from composite, rendered as raw context)
# ---------------------------------------------------------------------------

def _young_tile_putcall() -> dict:
    """CBOE put/call — young, excluded from composite."""
    try:
        df = store.read("cboe", "putcall")
        if df is None or "equity_pc_ratio" not in df.columns:
            return {"key": "putcall", "freshness": "missing", "obs_count": None,
                    "name_en": "CBOE put/call ratio",
                    "name_zh": "CBOE 看跌/看涨比率",
                    "value": None}
        eq = df["equity_pc_ratio"].dropna()
        return {"key": "putcall", "freshness": "young",
                "obs_count": len(eq),
                "name_en": "CBOE put/call ratio",
                "name_zh": "CBOE 看跌/看涨比率",
                "value": _r(float(eq.iloc[-1])) if len(eq) else None,
                "as_of": eq.index.max().strftime("%Y-%m-%d") if len(eq) else None,
                "note_en": "Series too young to z-score (< 252 obs); shown as raw context.",
                "note_zh": "序列过短，无法计算 z 分数（< 252 条）；显示为原始参考。"}
    except Exception as e:  # noqa: BLE001
        log.warning("putcall young tile failed: %s", e)
        return {"key": "putcall", "freshness": "missing", "obs_count": None,
                "name_en": "CBOE put/call ratio", "name_zh": "CBOE 看跌/看涨比率",
                "value": None}


def _young_tile_aaii() -> dict:
    """AAII bull/bear — young, excluded from composite."""
    try:
        df = store.read("sentiment", "aaii")
        if df is None or "aaii_bullish" not in df.columns:
            return {"key": "aaii", "freshness": "missing", "obs_count": None,
                    "name_en": "AAII sentiment",
                    "name_zh": "AAII 情绪调查",
                    "value": None}
        bull = df["aaii_bullish"].dropna()
        return {"key": "aaii", "freshness": "young",
                "obs_count": len(df),
                "name_en": "AAII sentiment (bullish %)",
                "name_zh": "AAII 情绪（看多占比）",
                "value": _r(float(bull.iloc[-1])) if len(bull) else None,
                "as_of": bull.index.max().strftime("%Y-%m-%d") if len(bull) else None,
                "note_en": "Series too young to z-score (< 104 weekly obs); shown as raw context.",
                "note_zh": "序列过短，无法计算 z 分数（< 104 周条）；显示为原始参考。"}
    except Exception as e:  # noqa: BLE001
        log.warning("aaii young tile failed: %s", e)
        return {"key": "aaii", "freshness": "missing", "obs_count": None,
                "name_en": "AAII sentiment", "name_zh": "AAII 情绪调查",
                "value": None}


# ---------------------------------------------------------------------------
# Min-history gate check
# ---------------------------------------------------------------------------

def _gate_passes(leg: dict) -> bool:
    """True if this leg clears the min-history gate for its frequency."""
    obs = leg.get("obs_count")
    if obs is None or obs == 0:
        return False
    key = leg["key"]
    # quarterly legs
    if key in {"insider"}:
        return obs >= QUARTERLY_MIN
    # weekly legs
    if key in {"naaim"}:
        return obs >= WEEKLY_MIN
    # daily legs (all others)
    return obs >= DAILY_MIN


# ---------------------------------------------------------------------------
# Freshness helper
# ---------------------------------------------------------------------------

def _freshness(ts: pd.Timestamp | None, stale_days: int = 5) -> str:
    """'fresh' if the most recent date is within stale_days business days, else 'stale'."""
    if ts is None:
        return "missing"
    try:
        today = pd.Timestamp.now(tz=None).normalize()
        delta = (today - pd.Timestamp(ts)).days
        return "fresh" if delta <= stale_days * 2 else "stale"
    except Exception:  # noqa: BLE001
        return "unknown"


def _ts_iso(ts) -> str | None:
    """Convert a pandas Timestamp (or index value) to an ISO date string, or None."""
    if ts is None:
        return None
    try:
        return pd.Timestamp(ts).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

def compute_fear_greed() -> dict | None:
    """Compute the Fear/Greed composite and return the JSON payload.

    Returns None only if ALL legs are missing (catastrophic data shortfall).
    """
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build all legs
    all_legs = [
        _leg_spx_momentum(),
        _leg_nh_nl_ratio(),
        _leg_mcclellan(),
        _leg_hy_oas(),
        _leg_safe_haven(),
        _leg_vix_level(),
        _leg_vix_trend(),
        _leg_vix_term(),
        _leg_skew(),
        _leg_naaim(),
        _leg_insider(),
    ]

    # Young tiles (always excluded, always rendered as raw context)
    young_tiles = [_young_tile_putcall(), _young_tile_aaii()]

    # Separate into gate-qualified and gate-failed (missing = also excluded)
    included = []
    excluded_young: list[dict] = []  # legs that fail gate but have SOME data
    excluded_missing: list[dict] = []  # legs with no data

    for leg in all_legs:
        if leg.get("z") is None:
            # Either missing or gate failed
            if leg.get("obs_count") is not None and leg["obs_count"] > 0:
                leg_copy = {**leg, "freshness": "young"}
                excluded_young.append(leg_copy)
            else:
                excluded_missing.append(leg)
        elif not _gate_passes(leg):
            leg_copy = {**leg, "freshness": "young"}
            excluded_young.append(leg_copy)
        else:
            included.append(leg)

    # Log the gate decisions
    inc_keys = [l["key"] for l in included]
    exc_keys = [l["key"] for l in excluded_young]
    mis_keys = [l["key"] for l in excluded_missing]
    log.info("fear_greed: included=%s excluded_young=%s missing=%s",
             inc_keys, exc_keys, mis_keys)

    # Compute composite dial
    z_vals = [l["z"] for l in included if l.get("z") is not None
              and np.isfinite(l["z"])]

    if not z_vals:
        log.warning("fear_greed: no qualifying legs — returning None")
        return None

    z_mean = float(np.mean(z_vals))
    # Map z_mean to 0-100 dial:
    # z-mean of ±2 -> ~2.5%/97.5% tails -> clamp z to [-3, 3]
    # linear map: z=-3 -> 0 (extreme fear), z=0 -> 50 (neutral), z=3 -> 100 (greed)
    dial = int(max(0, min(100, round(50 + (z_mean / 3.0) * 50))))
    label_en, label_zh = _dial_band(dial)

    # Most recent data date across INCLUDED legs (using last_date field added to each leg).
    # Fallback to today-UTC only when no included leg carries a last_date.
    leg_dates = [leg["last_date"] for leg in included if leg.get("last_date")]
    as_of = max(leg_dates) if leg_dates else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "dial": dial,
        "label_en": label_en,
        "label_zh": label_zh,
        "legs_included": included,
        "legs_excluded_young": excluded_young + excluded_missing,
        "young_tiles": young_tiles,
        "n_legs_qualifying": len(included),
        "as_of": as_of,
        "generated_utc": generated,
        "disclaimer_en": (
            "Sentiment context only — display-only composite of public market indicators. "
            "Never scored, never feeds the regime engine, no forward claim. "
            "Greed/fear readings are not contrarian signals without regime context."
        ),
        "disclaimer_zh": (
            "仅为情绪参考 — 公开市场指标的仅展示合成。"
            "不计分，不进入周期引擎，无前瞻性判断。"
            "贪婪/恐惧读数若无周期背景，不构成反向信号。"
        ),
    }


def persist_dial_history(payload: dict | None) -> bool:
    """Append one row to data/sentiment_us/fear_greed_dial.parquet.

    Schema: {date, dial, n_legs, label_en, logged_at (aware-UTC ISO string)}.
    Keep-FIRST per date (idempotent on re-run same day).
    logged_at is stored as a STRING to avoid pandas>=2 aware-into-naive TypeError
    on DatetimeIndex parquet setitem (see tz-aware-into-naive-parquet-ledger memory).

    Returns True if a new row was written, False if skipped (same-date or payload absent).
    """
    if not payload:
        return False
    date = payload.get("as_of")
    if not date:
        log.warning("persist_dial_history: no as_of date in payload — skipping")
        return False
    out_dir = config.data_dir() / "sentiment_us"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "fear_greed_dial.parquet"
    try:
        old = pd.read_parquet(out_path) if out_path.exists() else None
        if old is not None and "date" in old.columns and date in set(old["date"].astype(str)):
            log.info("persist_dial_history: already logged for %s (keep-first)", date)
            return False
        logged_at = datetime.now(timezone.utc).isoformat()   # aware UTC ISO string
        new_row = pd.DataFrame([{
            "date": date,
            "dial": int(payload["dial"]),
            "n_legs": int(payload.get("n_legs_qualifying", 0)),
            "label_en": payload.get("label_en", ""),
            "logged_at": logged_at,
        }])
        merged = pd.concat([old, new_row], ignore_index=True) if old is not None else new_row
        merged.to_parquet(out_path, index=False)
        log.info("persist_dial_history: wrote %s dial=%s", date, payload["dial"])
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("persist_dial_history failed: %s", e)
        return False
