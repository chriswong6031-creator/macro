"""engine/hold.py — W6-C HOLD tracker for the durable-bottom entry desk.

Spec (BINDING): research/entry_timing/WAVE6_PREREG.md §3
State definitions ported FROM research/entry_timing/wave5.py (compute_ladder):
  LAUNCHED = maxup since anchor > 5% OR OB-persist (3D StochRSI k or d >= 80
             on any bar in [anchor..now], sticky).
  BROKEN   = min close in (anchor..now] < trough*0.97
             where trough = min(close[max(0, anchor-90)..anchor]).
  INTACT   = neither LAUNCHED nor BROKEN.

Anchor selection (pre-decided, causal):
  1. §7 take/pending buy-marker date from signal_gate.gate when an open buy marker
     exists (result markers last type in {buy, rebuy}, no sell after).
  2. Else: most recent raw 3D RSI-MACD cross-up (cascade's own fallback) if <= 45
     trading days old.
  3. Else: None (no hold state).

PROVISIONAL: hold_provisional=True when the last 3D bucket is incomplete — mirrors
the sig.provisional pattern in confluence_tiers.

Never raises. Uses engine/confluence_tiers internals via import (no duplicate math).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── reuse confluence_tiers internals (never duplicate math) ──────────────────
from engine.confluence_tiers import (
    _tf_bars,        # resample n-business-day bars
    _stoch_rsi_kd,   # 3D StochRSI k, d
    _to_daily,       # TF-bar -> daily known-date mapping
    _rsi_macd,       # RSI-MACD (FAST_LEN=14, BASE_LEN=60, SIG_LEN=5)
    _xup,            # crossover: a > b AND a.shift(1) <= b.shift(1)
    OB,              # 80
)

# ── constants (from wave5.py) ─────────────────────────────────────────────────
MAXUP_THRESH  = 0.05   # LAUNCHED: maxup > 5%
OB_THRESH     = OB     # LAUNCHED OB-persist: k or d >= 80 on any bar [anchor..now]
TROUGH_LB     = 90     # trough window: close[anchor-90..anchor]
TROUGH_TOL    = 0.97   # BROKEN: min close < trough * 0.97
CROSS_MAX_AGE = 45     # fallback cross must be <= 45 trading days old

_BUY_TYPES = ("buy", "rebuy")


def _last_3d_cross(daily_close: pd.Series) -> tuple[pd.Timestamp | None, bool]:
    """Return (date_of_last_3D_RSIMACD_crossup, provisional_flag).

    provisional = True when the last 3D bucket is incomplete (the trailing 3-bar
    bin has fewer than 3 daily bars, so the cross may repaint when it completes).
    Uses the same TF-bar / known-date pipeline as confluence_tiers.
    """
    try:
        c = daily_close.dropna()
        if len(c) < 200:
            return None, False
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        ss3, sk3 = _tf_bars(c, 3)
        if len(ss3) < 5:
            return None, False
        m3, s3 = _rsi_macd(ss3)
        mb3 = _xup(m3, s3).fillna(False)
        cross_dates = sk3[mb3.to_numpy().astype(bool)]
        if len(cross_dates) == 0:
            return None, False
        cross_date = pd.Timestamp(cross_dates.iloc[-1])
        # provisional: check if the last 3D bucket is incomplete
        last_3d_date = pd.Timestamp(sk3.iloc[-1])
        last_daily   = c.index[-1]
        # a bucket is incomplete if daily index has bars AFTER the last known 3D bar
        # i.e. bars in (last_3d_date, last_daily] exist and < 3 of them make a full bucket
        trailing = int((c.index > last_3d_date).sum())
        provisional = (trailing > 0 and trailing < 3)
        return cross_date, provisional
    except Exception:
        return None, False


def hold_state(
    daily_close: pd.Series,
    *,
    anchor_date=None,
    last_cross_fallback: bool = True,
) -> dict | None:
    """Compute the hold state for a name with an active buy position.

    Parameters
    ----------
    daily_close : pd.Series
        Daily close prices (DatetimeIndex).
    anchor_date : str | pd.Timestamp | None
        The pre-decided anchor (§7 take/pending date from signal_gate.gate).
        If None and last_cross_fallback=True, falls back to the last 3D cross.
    last_cross_fallback : bool
        When True, falls back to the most recent 3D RSI-MACD cross-up if
        anchor_date is None. Cross must be <= CROSS_MAX_AGE trading days old.

    Returns
    -------
    dict | None
        None when no anchor can be established.
        Else: {state, anchor, anchor_src, days_basing, invalidation,
               maxup_pct, ret_since_anchor_pct, ob_persist, provisional}
    """
    try:
        c = daily_close.dropna()
        if len(c) < 5:
            return None
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        idx = c.index

        provisional = False
        anchor_src  = "take"

        # ── resolve anchor ────────────────────────────────────────────────────
        if anchor_date is not None:
            anchor_ts = pd.Timestamp(anchor_date)
        elif last_cross_fallback:
            cross_date, prov = _last_3d_cross(c)
            if cross_date is None:
                return None
            # age check: anchor must be <= CROSS_MAX_AGE trading days old
            age = int((idx > cross_date).sum())
            if age > CROSS_MAX_AGE:
                return None
            anchor_ts  = cross_date
            anchor_src = "cross"
            provisional = prov
        else:
            return None

        # ── find anchor position in the daily index ───────────────────────────
        # Use the first bar on or AFTER anchor_ts (known-date convention)
        ai = idx.searchsorted(anchor_ts, side="left")
        if ai >= len(idx):
            return None

        Pc = float(c.iloc[ai])
        if np.isnan(Pc) or Pc <= 0:
            return None

        # ── trough reference: close[max(0, ai-90) .. ai] inclusive ───────────
        trough_lo = max(0, ai - TROUGH_LB)
        trough_arr = c.iloc[trough_lo : ai + 1].to_numpy()
        trough = float(np.nanmin(trough_arr)) if len(trough_arr) > 0 else Pc

        # ── compute 3D StochRSI k, d daily-mapped for OB-persist ─────────────
        # Use the full series (causal up to current bar) — mirrors compute_ladder
        try:
            ss3, sk3 = _tf_bars(c, 3)
            k3, d3   = _stoch_rsi_kd(ss3)
            k3d = _to_daily(k3, sk3, idx, "ffill").to_numpy()
            d3d = _to_daily(d3, sk3, idx, "ffill").to_numpy()
        except Exception:
            k3d = np.full(len(c), np.nan)
            d3d = np.full(len(c), np.nan)

        # ── scan [ai .. now] to compute hold metrics ──────────────────────────
        c_arr = c.to_numpy()
        n     = len(c_arr)
        fwd   = c_arr[ai:]

        # maxup = max(close[ai..now]) / Pc - 1
        maxup = float(np.nanmax(fwd) / Pc - 1.0) if len(fwd) > 0 else 0.0

        # ret_since_anchor = close[now] / Pc - 1 — SIGNED, unlike maxup which is
        # the max favorable excursion and cannot see a name that is underwater.
        ret_since_anchor = float(c_arr[-1] / Pc - 1.0)

        # OB-persist: any bar in [ai..now] has 3D StochRSI k or d >= OB_THRESH (sticky)
        ob_persist = False
        for j in range(ai, n):
            kj = k3d[j]
            dj = d3d[j]
            if (not np.isnan(kj) and kj >= OB_THRESH) or (not np.isnan(dj) and dj >= OB_THRESH):
                ob_persist = True
                break

        # min close in (ai..now] — strictly after the anchor bar
        if ai + 1 < n:
            run_min = float(np.nanmin(c_arr[ai + 1:]))
        else:
            run_min = Pc

        # ── classify ─────────────────────────────────────────────────────────
        broken   = bool(run_min < trough * TROUGH_TOL)
        launched = bool(maxup > MAXUP_THRESH or ob_persist)
        if broken:
            state = "broken"
        elif launched:
            state = "launched"
        else:
            state = "intact"

        days_basing = int((idx > anchor_ts).sum())  # trading days strictly after anchor

        return {
            "state":        state,
            "anchor":       str(anchor_ts.date()),
            "anchor_src":   anchor_src,
            "days_basing":  days_basing,
            "invalidation": round(float(trough * TROUGH_TOL), 2),
            "maxup_pct":    round(float(maxup * 100), 2),
            "ret_since_anchor_pct": round(float(ret_since_anchor * 100), 2),
            "ob_persist":   ob_persist,
            "provisional":  provisional,
        }
    except Exception:
        return None
