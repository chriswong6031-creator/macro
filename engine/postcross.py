"""engine/postcross.py — Post-cross lifecycle detector (BASED/ARMED/SHAKEN chips).

HONESTY CONTRACT (updated 2026-07-03 after OOS adjudication — DURABLE_BOTTOM_FRAMEWORK.md §8):
  * NO state has rank/ordering power, ever (W8-A clean15 lift failed its gate).
  * ARMED: W8-A-OOS **FAILED** (deep-panel stop5 edge did not transfer to the 2,335-name
    baskets panel: -0.40pp vs the -2pp gate, sign-unstable across halves). The ``armed``
    field is computed and emitted ONLY for silent forward-ledger accrual — it must NOT
    render a chip, drive eligibility on its own, or carry any displayed claim.
  * SHAKEN: W8-B-OOS **PASSED all gates** (OOS stop5 42.5 vs FRESH 47.1 = -4.6pp, clean15
    NI +1.6pp, sign-stable both ticker halves + both time halves; deep panel concurs
    35.8 vs 40.3). Ships as display chip + Lane-R eligibility door.
  * BASED: claim-free eligibility door (both panels show stale-based fires no riskier
    than fresh: OOS stop5 45.3 vs 47.1). No displayed edge claim.

What this module provides
-------------------------
:func:`postcross` — given a daily close series, compute at the LATEST bar:

  * ``based``        : bool — the stale 3D cross is in the population window [3,8 ticks]
                       and the "not-launched" + ext_atr screens pass. A prerequisite for
                       ARMED/SHAKEN. Does NOT imply any directional edge.
  * ``armed``        : 'strict' | 'net' | None — W-ARM trigger fires (weekly RSI-MACD
                       histogram is negative, net-rising, above the threshold, and linear
                       extrapolation crosses zero within 2 weeks).
                       'strict' = three bars each strictly > prior.
                       'net'    = last bar > bar[last-3] (relaxed, MCD variant).
  * ``shaken``       : bool — post-cross new low > 1.5 ATR below cross price then recovery
                       above the midpoint with weekly hist net-rising.
  * ``ticks_since_cross`` : int | None
  * ``ext_pct``      : float | None — (close / cross_price - 1) × 100
  * ``ext_atr``      : float | None — ext / ATR-at-cross (pre-registered screen [-6, +2])
  * ``max_drawup_pct``: float | None — max upward excursion since cross (× 100)
  * ``wk_hist_last`` : float | None — most-recent known weekly histogram value
  * ``wk_w2x``       : float | None — linear-extrapolated weeks to zero

All conditions are CAUSAL + LEAK-FREE (known-date guards on every weekly bar).
Input: a daily close pd.Series with a DatetimeIndex. No OHLCV needed beyond close
(ATR is approximated from close-based EWM std; full open/high/low not required for
the lifecycle display).

ATR approximation note: the backtest in wave8_warm.py uses daily ATR from hi-lo EWM
(alpha=1/14). Here we only have close, so we approximate ATR as
  atrp ≈ close.pct_change().abs().ewm(alpha=1/14, min_periods=14).mean()
which is the close-to-close version. It is CONSERVATIVE (under-states intraday range),
making the SHAKEN new-low threshold harder to cross (if anything, safe direction).
The builder may inject a richer ATR if it has OHLCV; this fallback is a graceful
minimum.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.technicals import rsi  # faithful Wilder RSI matching Pine ta.rsi

# ── W8 constants (pre-registered in wave8_warm.py / DURABLE_BOTTOM_FRAMEWORK.md §8) ──
_STALE_LO = 3        # tick-age lower bound for population
_STALE_HI = 8        # tick-age upper bound
_MAXUP_GATE = 0.05   # not-launched: max upward extension < 5%
_OB_VETO = 85.0      # 3D stoch K or D >= 85 → exclude (MCK has k3=81.5; must admit)
_EXT_ATR_LO = -6.0   # ext_atr lower bound
_EXT_ATR_HI = +2.0   # ext_atr upper bound

# W-ARM (weekly hist) conditions
_W_HIST_THETA = 0.75      # STRICT: last hist > -0.75
_W_HIST_THETA_NET = 1.00  # NET: last hist > -1.00
_W_HIST_LOOKBACK = 5      # OLS extrapolation over last 5 known weekly bars
_W_HIST_STRICT_N = 3      # strictly rising: last N bars each > prior
_W2X_MAX = 2.0            # linear cross <= 2 weeks ahead

# SHAKEN conditions
_SHAKEN_NEW_LOW_ATR = 1.5   # new low must be > 1.5 ATR below cross price
_SHAKEN_MID_FRAC = 0.5      # recovery above midpoint = (cross + new_low) / 2
_SHAKEN_SEARCH = 20         # daily bars to search for the shake-out dip
_SHAKEN_TICK_HI = 20        # allow up to 20 ticks (shake-out can lag)

_NULL = {
    "based": False, "armed": None, "shaken": False,
    "ticks_since_cross": None, "ext_pct": None, "ext_atr": None,
    "max_drawup_pct": None, "wk_hist_last": None, "wk_w2x": None,
}


def _rsi_macd(series: pd.Series,
              fast: int = 14, base: int = 60, sig: int = 5) -> tuple[pd.Series, pd.Series]:
    """RSI-MACD (MACD of RSI): EMA(RSI, fast) − EMA(RSI, base) with EMA(diff, sig)
    as signal. Matches the variant used in confluence_tiers.py / wave8_warm.py."""
    r14 = rsi(series, fast)           # faithful Wilder RSI
    m = r14.ewm(span=fast, adjust=False).mean() - r14.ewm(span=base, adjust=False).mean()
    s = m.ewm(span=sig, adjust=False).mean()
    return m, s


def _stoch_rsi_kd(series: pd.Series,
                  stoch_len: int = 14, smooth_k: int = 3, smooth_d: int = 3
                  ) -> tuple[pd.Series, pd.Series]:
    """StochRSI K/D (matches tuning_harness.stoch_rsi_kd / confluence_tiers.py)."""
    r = rsi(series, stoch_len)
    lo = r.rolling(stoch_len).min()
    hi = r.rolling(stoch_len).max()
    raw = (r - lo) / (hi - lo + 1e-10) * 100.0
    k = raw.rolling(smooth_k).mean()
    d = k.rolling(smooth_d).mean()
    return k, d


def _xup(a: pd.Series, b: pd.Series) -> pd.Series:
    """Bullish cross: a crosses above b (a[i] >= b[i] and a[i-1] < b[i-1])."""
    cross = (a >= b) & (a.shift(1) < b.shift(1))
    return cross.fillna(False)


def _3d_resample(daily_close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Resample daily to 3-business-day bars. Returns (3d_close, known_dates_per_bar)."""
    groups = (pd.RangeIndex(len(daily_close)) // 3)
    s3 = (daily_close.groupby(groups).last()
          .set_axis(daily_close.groupby(groups).apply(lambda x: x.index[-1])))
    known = s3.index   # for each 3D bar, its known date = last daily bar in the group
    return s3, pd.Series(known, index=s3.index)


def _weekly_hist_grid(daily_close: pd.Series):
    """Build weekly RSI-MACD histogram with known-date guard.

    Returns (hist_arr, known_arr) or (None, None) if insufficient history.
    known_arr[i] = last trading day in week i (the day the bar becomes visible).
    """
    wk = daily_close.resample("W-FRI").last().dropna()
    if len(wk) < 70:
        return None, None
    known_w = (daily_close.resample("W-FRI")
               .apply(lambda x: x.dropna().index.max())
               .reindex(wk.index).dropna())
    wk = wk.reindex(known_w.index)
    wm, ws = _rsi_macd(wk)
    hist = (wm - ws).to_numpy().astype(float)
    known = pd.to_datetime(known_w.values)
    return hist, known


def _w_arm_at_date(hist_arr, known_arr, daily_date: pd.Timestamp) -> dict:
    """Evaluate W-ARM trigger at a given daily date (causal / leak-free)."""
    null = {"fires_strict": False, "fires_net": False, "last_hist": None,
            "w2x_weeks": None, "reason": "no_data"}
    if hist_arr is None:
        return null
    mask = known_arr <= daily_date
    valid = hist_arr[mask]
    if len(valid) < _W_HIST_STRICT_N + 1:
        return {**null, "reason": "insufficient_weekly_bars"}

    last_hist = float(valid[-1])
    if np.isnan(last_hist) or last_hist >= 0:
        return {**null, "last_hist": last_hist, "reason": "hist_not_negative"}

    prev3 = float(valid[-4]) if len(valid) >= 4 else None
    above_theta = last_hist > -_W_HIST_THETA
    above_theta_net = last_hist > -_W_HIST_THETA_NET

    strictly_rising = all(
        valid[-(i + 1)] > valid[-(i + 2)]
        for i in range(_W_HIST_STRICT_N)
    )
    net_rising = (prev3 is not None
                  and not np.isnan(prev3) and last_hist > prev3)

    seg = [v for v in valid[-_W_HIST_LOOKBACK:] if not np.isnan(v)]
    w2x = None
    if len(seg) >= 3:
        xs = np.arange(len(seg), dtype=float)
        ys = np.array(seg, dtype=float)
        xm, ym = xs.mean(), ys.mean()
        denom = ((xs - xm) ** 2).sum()
        if abs(denom) > 1e-10:
            a = ((xs - xm) * (ys - ym)).sum() / denom
            b = ym - a * xm
            if a > 0:
                w2x = float((0 - b) / a - (len(seg) - 1))

    extrap_ok = w2x is not None and 0 < w2x <= _W2X_MAX

    fires_strict = bool(last_hist < 0 and above_theta and strictly_rising and extrap_ok)
    fires_net = bool(last_hist < 0 and above_theta_net and net_rising and extrap_ok)

    return {
        "fires_strict": fires_strict,
        "fires_net": fires_net,
        "last_hist": last_hist,
        "w2x_weeks": w2x,
        "reason": "ok" if (fires_strict or fires_net) else "conditions_not_met",
    }


def postcross(daily_close: pd.Series, atr_series: pd.Series | None = None) -> dict:
    """Compute the post-cross lifecycle state at the latest bar of *daily_close*.

    Parameters
    ----------
    daily_close : pd.Series with DatetimeIndex (business days)
    atr_series  : optional daily ATR-% series (same index). When None, a
                  close-to-close EWM-std approximation is used (conservative).

    Returns
    -------
    dict with keys: based, armed, shaken, ticks_since_cross, ext_pct,
    ext_atr, max_drawup_pct, wk_hist_last, wk_w2x.
    Never raises — returns _NULL on any error.
    """
    try:
        c = pd.to_numeric(daily_close, errors="coerce").dropna().astype(float)
        if len(c) < 100:
            return _NULL.copy()

        idx = c.index
        n = len(c)
        c_arr = c.to_numpy()

        # ── ATR (close-to-close approximation if no OHLCV) ──────────────────
        if atr_series is not None:
            atr_aligned = pd.to_numeric(atr_series, errors="coerce").reindex(idx).ffill()
            atrp = atr_aligned.to_numpy().astype(float)
        else:
            daily_pct = c.pct_change().abs()
            atrp = daily_pct.ewm(alpha=1 / 14, min_periods=14).mean().to_numpy().astype(float)

        # ── 3D RSI-MACD cross detection ──────────────────────────────────────
        s3, kn3 = _3d_resample(c)
        if len(s3) < 20:
            return _NULL.copy()
        m3, sig3 = _rsi_macd(s3)
        k3_tf, d3_tf = _stoch_rsi_kd(s3)
        cross_up_3d = _xup(m3, sig3)

        # Map 3D indicators to daily (ffill from known date)
        def _to_daily_ffill(s_3d, kn):
            return s_3d.reindex(idx, method=None).reindex(kn.values).reindex(idx, method="ffill")

        k3_daily = k3_tf.reindex(kn3.values).reindex(idx, method="ffill").to_numpy().astype(float)
        d3_daily = d3_tf.reindex(kn3.values).reindex(idx, method="ffill").to_numpy().astype(float)

        # ── Weekly RSI-MACD histogram grid ────────────────────────────────────
        hist_arr, known_arr = _weekly_hist_grid(c)

        # ── Most-recent 3D cross (latest cross in history) ───────────────────
        cross_events = []
        for ci in range(len(s3)):
            if bool(cross_up_3d.iloc[ci]):
                known_ts = pd.Timestamp(kn3.index[ci])
                kpos = idx.searchsorted(known_ts, side="left")
                if kpos < n and idx[kpos] == known_ts:
                    cross_price = float(c_arr[kpos])
                    if not np.isnan(cross_price) and cross_price > 0:
                        cross_events.append({
                            "kpos": int(kpos),
                            "known": known_ts,
                            "price": cross_price,
                            "ci": int(ci),
                        })
        if not cross_events:
            return _NULL.copy()

        # Use the MOST RECENT cross
        ev = cross_events[-1]
        cross_kpos = ev["kpos"]
        cross_known = ev["known"]
        cross_price = ev["price"]
        cross_ci = ev["ci"]
        last_bar = n - 1

        # ── Tick age at the last bar ──────────────────────────────────────────
        # Ticks = count of 3D bars with known_date strictly AFTER cross_known and <= last bar date
        last_date = idx[last_bar]
        ticks = int(((kn3.values > cross_known) & (kn3.values <= last_date)).sum())

        # ── Not-launched check ────────────────────────────────────────────────
        window = c_arr[cross_kpos: last_bar + 1]
        max_up = float(np.nanmax(window) / cross_price - 1.0) if len(window) > 0 else 0.0
        atrp_at_cross = float(atrp[cross_kpos]) if cross_kpos < len(atrp) else np.nan
        ext = float(c_arr[last_bar] / cross_price - 1.0)
        ext_atr = (ext / atrp_at_cross) if (not np.isnan(atrp_at_cross) and atrp_at_cross > 0) else None

        # 3D stoch at last bar
        k3_last = float(k3_daily[last_bar]) if last_bar < len(k3_daily) else np.nan
        d3_last = float(d3_daily[last_bar]) if last_bar < len(d3_daily) else np.nan
        deeply_ob = ((not np.isnan(k3_last) and k3_last >= _OB_VETO)
                     or (not np.isnan(d3_last) and d3_last >= _OB_VETO))

        in_population = (
            _STALE_LO <= ticks <= _STALE_HI
            and max_up < _MAXUP_GATE
            and not deeply_ob
            and ext_atr is not None
            and _EXT_ATR_LO <= ext_atr <= _EXT_ATR_HI
        )
        based = in_population

        # ── W-ARM (ARMED) ─────────────────────────────────────────────────────
        armed: str | None = None
        wk_hist_last: float | None = None
        wk_w2x: float | None = None
        if based and hist_arr is not None:
            w_arm = _w_arm_at_date(hist_arr, known_arr, last_date)
            wk_hist_last = w_arm.get("last_hist")
            wk_w2x = w_arm.get("w2x_weeks")
            if w_arm["fires_strict"]:
                armed = "strict"
            elif w_arm["fires_net"]:
                armed = "net"

        # ── SHAKEN ────────────────────────────────────────────────────────────
        shaken = False
        if _STALE_LO <= ticks <= _SHAKEN_TICK_HI and not np.isnan(atrp_at_cross) and atrp_at_cross > 0:
            shake_thr = cross_price * (1.0 - _SHAKEN_NEW_LOW_ATR * atrp_at_cross)
            # Search for new low in [cross_kpos+1 .. cross_kpos+_SHAKEN_SEARCH]
            new_low_price = np.inf
            new_low_pos = None
            for j1 in range(cross_kpos + 1, min(cross_kpos + _SHAKEN_SEARCH + 1, n)):
                if c_arr[j1] < shake_thr and c_arr[j1] < new_low_price:
                    new_low_price = float(c_arr[j1])
                    new_low_pos = j1
            if new_low_pos is not None:
                midpoint = (cross_price + new_low_price) / 2.0
                # Recovery: current close > midpoint AND weekly hist net-rising at last_bar
                if c_arr[last_bar] > midpoint and hist_arr is not None:
                    w_shk = _w_arm_at_date(hist_arr, known_arr, last_date)
                    shaken = bool(w_shk["fires_net"])

        return {
            "based": bool(based),
            "armed": armed,
            "shaken": bool(shaken),
            "ticks_since_cross": int(ticks),
            "ext_pct": round(ext * 100.0, 2),
            "ext_atr": round(float(ext_atr), 3) if ext_atr is not None else None,
            "max_drawup_pct": round(max_up * 100.0, 2),
            "wk_hist_last": round(float(wk_hist_last), 4) if wk_hist_last is not None else None,
            "wk_w2x": round(float(wk_w2x), 2) if wk_w2x is not None else None,
        }
    except Exception:  # noqa: BLE001 — display-only; never fatal
        return _NULL.copy()
