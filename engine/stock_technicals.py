"""engine/stock_technicals.py — the canonical, OHLCV-aware per-stock technical snapshot.

The thin ``engine.technicals.snapshot(close)`` only knows price (RSI, MA distance,
52w-high). This module is the richer, research-vetted superset used by the US standout
board: deeper trend / momentum / volatility / volume reads, computed once over full
history so the live snapshot and any backtest share one code path.

Design contract:

* **Graceful by column.** ``snapshot(close, high, low, volume, bench)`` computes whatever
  the supplied columns allow. high/low/volume are optional — the ~1,400 breadth names carry
  CLOSE ONLY, so every OHLCV-only field (ATR, ADX, Choppiness, NR7, CMF, relative volume,
  Donchian-from-range) returns ``None`` for them, while the ~114 ``data/stocks`` names and
  the optionable GEX subset get the full read. Missing is **None**, never silently 0.
* **Reuse, don't re-implement.** RSI and MACD come from the CANONICAL
  ``engine.technicals`` (the repo had RSI implemented five different ways; this routes the
  standout board through the one with ``min_periods`` set). The 52-week-high window matches
  ``engine.technicals.tech_frame`` (252 / min_periods=200).
* **Research-grounded.** The added legs are the ones the literature survey rated
  strong/moderate for single-stock ranking + timing: volatility-scaled momentum
  (Daniel-Moskowitz), 52-week-high proximity (George-Hwang), ADX/DMI trend strength,
  realized-vol percentile (HVP), Bollinger-bandwidth percentile (BBWP), the TTM squeeze
  (Bollinger inside Keltner), Choppiness, NR7, OBV/CMF/relative-volume confirmation, and
  Donchian position. None of these is claimed as a standalone alpha here — they feed the
  display + the *entry-timing* axis + the vol-squeeze / GEX confirmers.

Everything is pure (functions of pandas Series) and unit-testable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window, rolling_slope
from engine.technicals import macd_hist, rsi

# ---------------------------------------------------------------------------
# tiny helpers
# ---------------------------------------------------------------------------
def _last(s: pd.Series | None) -> float | None:
    """Latest finite value of a series, else None."""
    if s is None or len(s) == 0:
        return None
    v = s.iloc[-1]
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(v) or np.isinf(v)) else v


def _r(x: float | None, nd: int = 2) -> float | None:
    return None if x is None else round(x, nd)


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (the RMA used by ATR/ADX) — EMA with alpha = 1/n."""
    return s.ewm(alpha=1.0 / n, min_periods=n, adjust=False).mean()


# ---------------------------------------------------------------------------
# true range / ATR / ADX-DMI  (need high+low+close)
# ---------------------------------------------------------------------------
def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    return pd.concat([(high - low).abs(), (high - pc).abs(), (low - pc).abs()],
                     axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return _wilder(true_range(high, low, close), n)


def adx_dmi(high: pd.Series, low: pd.Series, close: pd.Series,
            n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Wilder's ADX + directional indicators. Returns (adx, plus_di, minus_di).
    ADX measures trend STRENGTH (regardless of direction); +DI > -DI = up-trend."""
    up = high.diff()
    dn = -low.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = _wilder(true_range(high, low, close), n)
    plus_di = 100.0 * _wilder(plus_dm, n) / tr.replace(0, np.nan)
    minus_di = 100.0 * _wilder(minus_dm, n) / tr.replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return _wilder(dx, n), plus_di, minus_di


# ---------------------------------------------------------------------------
# volatility / compression  (BBWP & HVP are close-only; KC/squeeze/CHOP/NR7 need OHLC)
# ---------------------------------------------------------------------------
def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    """Annualized close-to-close realized volatility (%) over n days."""
    ratio = (close / close.shift(1)).where(lambda r: r > 0)   # guard non-positive (bad prints)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(ratio)
    return lr.rolling(n, min_periods=max(5, n // 2)).std(ddof=0) * np.sqrt(252) * 100.0


def bb_bandwidth(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    """Bollinger bandwidth = (upper - lower) / mid = 2k·sd / sma — low = compressed."""
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return (2.0 * k * sd) / mid.replace(0, np.nan)


def ttm_squeeze(high: pd.Series, low: pd.Series, close: pd.Series,
                n: int = 20, bb_k: float = 2.0, kc_k: float = 1.5) -> pd.Series:
    """The TTM squeeze: True when the Bollinger band sits INSIDE the Keltner channel
    (volatility compressed below the ATR envelope). Needs high/low for the Keltner ATR."""
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    bb_up, bb_lo = mid + bb_k * sd, mid - bb_k * sd
    rng = atr(high, low, close, n)
    kc_up, kc_lo = mid + kc_k * rng, mid - kc_k * rng
    return (bb_up < kc_up) & (bb_lo > kc_lo)


def choppiness(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Choppiness Index — 100·log10(Σtrueрange / (HH-LL)) / log10(n). High = ranging,
    low (<38) = trending. A STATE descriptor (filter), not a directional signal."""
    tr = true_range(high, low, close)
    tr_sum = tr.rolling(n, min_periods=n).sum()
    hh = high.rolling(n, min_periods=n).max()
    ll = low.rolling(n, min_periods=n).min()
    rng = (hh - ll).replace(0, np.nan)
    ratio = (tr_sum / rng).replace(0, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return 100.0 * np.log10(ratio) / np.log10(n)


def is_nr7(high: pd.Series, low: pd.Series) -> pd.Series:
    """Narrowest-range-in-7 (Crabel): today's range < each of the prior 6 days' ranges."""
    rng = high - low
    prior_min = rng.shift(1).rolling(6, min_periods=6).min()
    return rng < prior_min


# ---------------------------------------------------------------------------
# volume confirmation  (need volume; CMF needs high/low too)
# ---------------------------------------------------------------------------
def on_balance_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (np.sign(close.diff()).fillna(0.0) * volume).cumsum()


def chaikin_money_flow(high: pd.Series, low: pd.Series, close: pd.Series,
                       volume: pd.Series, n: int = 20) -> pd.Series:
    """CMF — volume-weighted accumulation/distribution over n days, in [-1, 1]."""
    rng = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / rng
    mfv = (mfm * volume).fillna(0.0)
    vol_sum = volume.rolling(n, min_periods=n).sum().replace(0, np.nan)
    return mfv.rolling(n, min_periods=n).sum() / vol_sum


# ---------------------------------------------------------------------------
# momentum  (close-only — vol-scaled momentum, 52w-high proximity, 12-1)
# ---------------------------------------------------------------------------
def _ret(close: pd.Series, lag: int) -> float | None:
    if len(close) <= lag:
        return None
    a, b = close.iloc[-1], close.iloc[-1 - lag]
    if not (np.isfinite(a) and np.isfinite(b)) or b <= 0:
        return None
    return float(a / b - 1.0) * 100.0


def momentum_block(close: pd.Series) -> dict:
    """Multi-horizon return + 12-1 momentum + volatility-scaled momentum (Daniel-Moskowitz:
    the 12-1 total return divided by trailing annualized vol — the form that survives momentum
    crashes) + 52-week-high proximity (George-Hwang: price / its own 252d high, 0..1)."""
    out: dict = {
        "ret_1m": _r(_ret(close, 21), 1), "ret_3m": _r(_ret(close, 63), 1),
        "ret_6m": _r(_ret(close, 126), 1), "ret_12m": _r(_ret(close, 252), 1),
    }
    # 12-1 momentum: 12-month return skipping the most recent month (reversal-purged)
    mom_12_1 = None
    if len(close) > 252:
        a, b = close.iloc[-22], close.iloc[-253]
        if np.isfinite(a) and np.isfinite(b) and b > 0:
            mom_12_1 = float(a / b - 1.0) * 100.0
    out["mom_12_1"] = _r(mom_12_1, 1)
    # volatility-scaled momentum = 12-1 return / trailing annualized vol (126d)
    vs = None
    if mom_12_1 is not None:
        av = _last(realized_vol(close, 126))
        if av and av > 0:
            vs = mom_12_1 / av
    out["mom_vol_scaled"] = _r(vs, 3)
    # 52-week-high proximity in [0, 1] — 1.0 = at a new 52w high
    hi = close.rolling(252, min_periods=200).max()
    last_close, last_hi = _last(close), _last(hi)
    out["high52w_prox"] = (_r(last_close / last_hi, 3)
                           if (last_close and last_hi and last_hi > 0) else None)
    return out


# ---------------------------------------------------------------------------
# the public snapshot
# ---------------------------------------------------------------------------
def snapshot(close: pd.Series, high: pd.Series | None = None,
             low: pd.Series | None = None, volume: pd.Series | None = None,
             bench: pd.Series | None = None) -> dict:
    """Latest-bar technical read. Superset of ``engine.technicals.snapshot`` (same keys +
    new ones), so existing template fields keep working. OHLCV-only fields are None when the
    corresponding columns are absent.

    ``bench`` (optional, e.g. SPY close aligned to the same index) adds relative-strength
    ratios. ``coverage`` records which data tier produced this read.
    """
    close = pd.to_numeric(close, errors="coerce").astype(float).dropna()
    has_hl = high is not None and low is not None and len(close) > 1
    has_vol = volume is not None
    if has_hl:
        high = pd.to_numeric(high, errors="coerce").reindex(close.index).astype(float)
        low = pd.to_numeric(low, errors="coerce").reindex(close.index).astype(float)
        # guard against an all-NaN reindex (e.g. high passed but misaligned)
        has_hl = bool(high.notna().sum() > 20 and low.notna().sum() > 20)
    if has_vol:
        volume = pd.to_numeric(volume, errors="coerce").reindex(close.index).astype(float)
        has_vol = bool((volume.fillna(0) > 0).sum() > 20)

    sma20 = close.rolling(20, min_periods=20).mean()
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    px = _last(close)
    s20, s50, s200 = _last(sma20), _last(sma50), _last(sma200)

    def _pct_vs(ref: float | None) -> float | None:
        return _r((px / ref - 1.0) * 100.0, 1) if (px and ref and ref > 0) else None

    out: dict = {
        # ---- existing keys (back-compat with the thin snapshot) ---------------
        "price": _r(px, 2),
        "above50": (px > s50) if (px and s50) else None,
        "above200": (px > s200) if (px and s200) else None,
        "pct_vs_50dma": _pct_vs(s50),
        "pct_vs_200dma": _pct_vs(s200),
        "rsi14": _r(_last(rsi(close, 14)), 0),
        "macd_pos": (lambda m: bool(m > 0) if m is not None else None)(_last(macd_hist(close))),
        "off_52w_high_pct": _r((lambda h: (px / h - 1.0) * 100.0 if (px and h and h > 0) else None)(
            _last(close.rolling(252, min_periods=200).max())), 1),
    }

    # ---- trend regime -------------------------------------------------------
    out["pct_vs_20dma"] = _pct_vs(s20)
    out["golden"] = (s50 > s200) if (s50 and s200) else None     # 50dma above 200dma
    out["sma50_slope_up"] = (lambda x: bool(x > 0) if x is not None else None)(
        _last(rolling_slope(sma50.dropna(), 20)) if sma50.notna().sum() > 25 else None)
    out["rsi2"] = _r(_last(rsi(close, 2)), 0)                     # Connors short-term

    # ---- momentum (close-only) ---------------------------------------------
    out.update(momentum_block(close))

    # ---- volatility / compression ------------------------------------------
    out["hv20"] = _r(_last(realized_vol(close, 20)), 1)
    out["hv_pctile"] = _r((lambda p: p * 100.0 if p is not None else None)(
        _last(pct_rank_window(realized_vol(close, 20), 252))), 0)
    bbw = bb_bandwidth(close, 20, 2.0)
    out["bb_bandwidth"] = _r(_last(bbw) and _last(bbw) * 100.0, 2)
    out["bbwp"] = _r((lambda p: p * 100.0 if p is not None else None)(
        _last(pct_rank_window(bbw, 252))), 0)

    # ---- relative strength vs the benchmark (optional) ----------------------
    if bench is not None:
        b = pd.to_numeric(bench, errors="coerce").reindex(close.index).astype(float)
        if b.notna().sum() > 70:
            rsl = (close / b).replace([np.inf, -np.inf], np.nan)
            out["rs_1m"] = _r(_ret(rsl.dropna(), 21), 1)
            out["rs_3m"] = _r(_ret(rsl.dropna(), 63), 1)
            out["rs_6m"] = _r(_ret(rsl.dropna(), 126), 1)

    # ---- OHLC-only block (None for close-only names) ------------------------
    if has_hl:
        a = atr(high, low, close, 14)
        out["atr14"] = _r(_last(a), 2)
        out["atr_pct"] = _r((lambda v: v / px * 100.0 if (v and px) else None)(_last(a)), 2)
        adx, pdi, mdi = adx_dmi(high, low, close, 14)
        out["adx14"] = _r(_last(adx), 1)
        out["di_plus"] = _r(_last(pdi), 1)
        out["di_minus"] = _r(_last(mdi), 1)
        ld_p, ld_m = _last(pdi), _last(mdi)
        out["adx_trend"] = (None if (ld_p is None or ld_m is None)
                            else "up" if ld_p > ld_m else "down")
        out["squeeze_on"] = (lambda x: bool(x) if x is not None else None)(
            _last(ttm_squeeze(high, low, close)))
        out["chop14"] = _r(_last(choppiness(high, low, close, 14)), 0)
        out["nr7"] = (lambda x: bool(x) if x is not None else None)(_last(is_nr7(high, low)))
        # Donchian(20) position from the high/low range, 0..1
        hh = high.rolling(20, min_periods=20).max()
        ll = low.rolling(20, min_periods=20).min()
        h_l, l_l, p_l = _last(hh), _last(ll), px
        out["donchian_pos"] = (_r((p_l - l_l) / (h_l - l_l), 2)
                               if (h_l is not None and l_l is not None and h_l > l_l and p_l) else None)
    else:
        for k in ("atr14", "atr_pct", "adx14", "di_plus", "di_minus", "adx_trend",
                  "squeeze_on", "chop14", "nr7", "donchian_pos"):
            out[k] = None

    # ---- volume confirmation (None without volume) --------------------------
    if has_vol:
        vol = volume.fillna(0.0)
        vsma = vol.rolling(20, min_periods=10).mean()
        rv = (_last(vol) / _last(vsma)) if (_last(vsma) and _last(vsma) > 0) else None
        out["rel_volume"] = _r(rv, 2)
        out["dollar_vol_20d"] = _r((lambda v: v * px if (v and px) else None)(_last(vsma)), 0)
        out["obv_slope_up"] = (lambda x: bool(x > 0) if x is not None else None)(
            _last(rolling_slope(on_balance_volume(close, vol).tail(60), 20)))
        if has_hl:
            out["cmf20"] = _r(_last(chaikin_money_flow(high, low, close, vol, 20)), 3)
            # volume-confirmed breakout: close at a 20d high on >1.5x average volume
            hh20 = high.rolling(20, min_periods=20).max()
            out["breakout_vol_confirmed"] = bool(
                px is not None and _last(hh20) is not None and px >= _last(hh20)
                and rv is not None and rv >= 1.5)
        else:
            out["cmf20"] = None
            out["breakout_vol_confirmed"] = None
    else:
        for k in ("rel_volume", "dollar_vol_20d", "obv_slope_up", "cmf20",
                  "breakout_vol_confirmed"):
            out[k] = None

    out["coverage"] = ("ohlcv" if (has_hl and has_vol) else "ohlc" if has_hl
                       else "close")
    return out
