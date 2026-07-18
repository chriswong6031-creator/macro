"""engine/congress_entry.py — display-tier entry-timing snapshot for the congress
copy-watchlist.

Operator-ordered 2026-07-18.  Re-ranks a display watchlist only — no authority
path (no gate/size/allocation); receipts on hover.

Case-law notes (preserved, not overridden):
  FL-R7/A2: 2W oscillator turns tested null at basket grain ("catastrophically
  late") — these are operator-requested display context; never standalone signal,
  never sort key, never fire-qualifying.

  Entry-stack Amendment-3 kill: promoted washout-x-turn constructions are
  killed.  This module deliberately stays display-tier with plain-word null
  disclosure in the page footer.

Public API
----------
entry_snapshot(daily_close) -> dict
  Returns the frozen-field contract dict (all keys always present; see FIELDS below).

Internal pure helpers (factored for unit-testability):
  _wash_state(kc)          -> str  "now"|"recent"|"near"|"none"
  _macd_state(hist)        -> dict  w_macd shape
  _stoch_cross_state(k, d) -> dict  w_stoch shape

Compliance: pure function layer; zero I/O; never raises on valid or invalid input.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.htf_durability import _biweekly_close        # PIT-safe 2W resampler (ESX-RUL-31)
from engine.signal_quality import _stoch_rsi_kd          # RSI14->Stoch14->SMA_K3->SMA_D3 (pinned)
from engine.signal_quality import _rsi_macd              # house RSI-MACD variant (EMA(RSI14,14)-EMA(RSI14,60), signal EMA(macd,5))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (all with doc-comments per house law)
# ---------------------------------------------------------------------------

OS_FLOOR: float = 20.0        # oversold threshold — StochRSI K < this = washout "now"
NEAR_FLOOR: float = 25.0      # near-washout threshold — K <= this = washout "near"
W_CROSS_WINDOW: int = 2       # weekly bars within which a stoch k/d cross is "fresh"
W_STOCH_GAP_MAX: float = 8.0  # max k/d gap (d-k) for w_stoch "approaching" state
# Low-zone qualifier for w_stoch: a k-over-d cross only counts when D at the cross sits in the
# lower zone (< this), and "approaching" only when current D is below it. Base-rate probe
# 2026-07-18: unqualified weekly crosses fired on ~29% of a random congress-universe sample —
# mid-range K/D churn (the degenerate-signal class; leader-radar Zweig lesson). The house
# cascade contextualizes stoch crosses the same way (confluence confirm gates use from-oversold;
# setup_tier flags d<25 washout crosses — from_washout keeps that stricter receipt).
W_STOCH_ZONE_MAX: float = 40.0
W_MACD_ETA_MAX: float = 3.0   # max weekly-bar ETA for w_macd "approaching" state
MIN_WEEKLY_BARS: int = 40     # weekly bars needed for stoch/MACD detectors (coverage gate)
MIN_HTF_BARS: int = 35        # biweekly or monthly bars needed for wash detectors
MIN_DAILY_BARS: int = 60      # minimum daily bars to declare covered=True
MIN_DAILY_BARS_1M: int = 250  # additional daily-bar floor for 1M washout (needs ~35 months)


# ---------------------------------------------------------------------------
# Null contract shapes (returned when coverage fails)
# ---------------------------------------------------------------------------

def _null_wash() -> dict:
    return {"state": "none", "k": None, "coverage": False}


def _null_w_macd() -> dict:
    return {"state": "none", "kind": None, "bars_since": None, "eta_bars": None}


def _null_w_stoch() -> dict:
    return {
        "state": "none", "bars_since": None, "d_at_cross": None,
        "from_washout": False, "k": None, "d": None, "gap": None,
    }


# ---------------------------------------------------------------------------
# Pure state-machine helpers (factored for direct unit testing)
# ---------------------------------------------------------------------------

def _wash_state(kc: pd.Series) -> str:
    """Compute washout state from a cleaned (dropna) StochRSI K series.

    States (mutually exclusive, in precedence order):
      "now"    — most recent bar K < OS_FLOOR (20)
      "recent" — not now, but previous bar (kc[-2]) < OS_FLOOR
      "near"   — not now/recent, kc[-1] <= NEAR_FLOOR and falling (kc[-1] < kc[-2])
      "none"   — none of the above

    Requires at least 2 values in kc; returns "none" otherwise.
    """
    if len(kc) < 2:
        return "none"
    k_last = float(kc.iloc[-1])
    k_prev = float(kc.iloc[-2])
    if k_last < OS_FLOOR:
        return "now"
    if k_prev < OS_FLOOR:
        return "recent"
    if k_last <= NEAR_FLOOR and k_last < k_prev:
        return "near"
    return "none"


def _macd_variant_state(hist: pd.Series) -> dict:
    """Compute crossed/approaching state for a single MACD histogram series.

    Returns dict: {"crossed": bool, "bars_since": int|None, "approaching": bool,
                   "eta_bars": float|None}

    crossed: a zero-cross (hist[i] > 0 and hist[i-1] <= 0) with bars_since <= W_CROSS_WINDOW,
             matching _stoch_cross_state's freshness semantics exactly (bars_since in 0..2).
    approaching: hist[-1] < 0, rising 3 consecutive bars, slope > 0, eta <= W_MACD_ETA_MAX.
    """
    h = hist.dropna()
    null = {"crossed": False, "bars_since": None, "approaching": False, "eta_bars": None}
    if len(h) < 4:
        return null

    # ---- crossed check: any cross with bars_since <= W_CROSS_WINDOW ----
    # offsets 0..W_CROSS_WINDOW so MACD and stoch agree on what "fresh" means (review 07-18).
    crossed = False
    bars_since = None
    n = len(h)
    for offset in range(W_CROSS_WINDOW + 1):
        # offset=0 -> last bar, offset=1 -> second-to-last, etc.
        i = n - 1 - offset
        if i < 1:
            break
        if float(h.iloc[i]) > 0 and float(h.iloc[i - 1]) <= 0:
            crossed = True
            bars_since = offset  # 0 = last bar, 1 = one bar ago
            break

    if crossed:
        return {"crossed": True, "bars_since": bars_since, "approaching": False, "eta_bars": None}

    # ---- approaching check ----
    latest = float(h.iloc[-1])
    if latest < 0:
        rising = (float(h.iloc[-1]) > float(h.iloc[-2]) > float(h.iloc[-3]))
        if rising:
            slope = (float(h.iloc[-1]) - float(h.iloc[-4])) / 3.0
            if slope > 0:
                eta = -latest / slope
                if eta <= W_MACD_ETA_MAX:
                    eta_bars = round(float(max(eta, 0.5)), 1)
                    return {"crossed": False, "bars_since": None, "approaching": True, "eta_bars": eta_bars}

    return null


def _macd_state(rsi_macd_hist: pd.Series, price_macd_hist: pd.Series) -> dict:
    """Combine RSI-MACD and price-MACD variant states into the w_macd contract dict.

    Family state:
      crossed if either variant crossed (kind = "rsi_macd"|"price"|"both")
      elif either approaching (kind, eta from the firing variant; if both, smaller eta)
      else none
    """
    rs = _macd_variant_state(rsi_macd_hist)
    ps = _macd_variant_state(price_macd_hist)

    # ---- crossed resolution ----
    rs_crossed = rs["crossed"]
    ps_crossed = ps["crossed"]

    if rs_crossed or ps_crossed:
        if rs_crossed and ps_crossed:
            kind = "both"
            # take the most recent (smallest bars_since)
            r_bs = rs["bars_since"] if rs["bars_since"] is not None else 999
            p_bs = ps["bars_since"] if ps["bars_since"] is not None else 999
            bars_since = min(r_bs, p_bs)
        elif rs_crossed:
            kind = "rsi_macd"
            bars_since = rs["bars_since"]
        else:
            kind = "price"
            bars_since = ps["bars_since"]
        return {"state": "crossed", "kind": kind, "bars_since": bars_since, "eta_bars": None}

    # ---- approaching resolution ----
    rs_app = rs["approaching"]
    ps_app = ps["approaching"]

    if rs_app or ps_app:
        if rs_app and ps_app:
            kind = "both"
            r_eta = rs["eta_bars"] if rs["eta_bars"] is not None else float("inf")
            p_eta = ps["eta_bars"] if ps["eta_bars"] is not None else float("inf")
            eta_bars = min(r_eta, p_eta)
        elif rs_app:
            kind = "rsi_macd"
            eta_bars = rs["eta_bars"]
        else:
            kind = "price"
            eta_bars = ps["eta_bars"]
        return {"state": "approaching", "kind": kind, "bars_since": None, "eta_bars": eta_bars}

    return _null_w_macd()


def _stoch_cross_state(k: pd.Series, d: pd.Series) -> dict:
    """Compute w_stoch state from weekly StochRSI K and D series.

    crossed: most recent k-over-d upcross (k>=d now-or-then where prev bar k<d)
             with bars_since <= W_CROSS_WINDOW (2 weekly bars), still alive
             (k[-1] >= d[-1]) and from the lower zone (d_at_cross < W_STOCH_ZONE_MAX).
    approaching: not crossed AND k < d AND k rising (k[-1] > k[-2])
                 AND gap = d[-1]-k[-1] <= W_STOCH_GAP_MAX AND gap narrowing
                 AND d[-1] < W_STOCH_ZONE_MAX (low-zone only).

    Returns the full w_stoch contract dict shape.
    """
    null = _null_w_stoch()

    # Align k and d on their common index ONCE; every read below (cross search,
    # aliveness, gap) uses the aligned series so all comparisons share the same bars
    # (independently-dropna'd tails could otherwise compare K and D from different dates).
    common = k.dropna().index.intersection(d.dropna().index)
    if len(common) < 3:
        return null

    k_aligned = k.reindex(common)
    d_aligned = d.reindex(common)

    k_last = float(k_aligned.iloc[-1])
    k_prev = float(k_aligned.iloc[-2])
    d_last = float(d_aligned.iloc[-1])
    d_prev = float(d_aligned.iloc[-2])

    # Search backward for the most recent upcross (k >= d and prev k < d)
    n = len(k_aligned)
    cross_bar_idx = None  # position in k_aligned of the cross bar
    for i in range(n - 1, 0, -1):
        ki = float(k_aligned.iloc[i])
        ki_prev = float(k_aligned.iloc[i - 1])
        di = float(d_aligned.iloc[i])
        di_prev = float(d_aligned.iloc[i - 1])
        if ki >= di and ki_prev < di_prev:
            cross_bar_idx = i
            break

    if cross_bar_idx is not None:
        bars_since = (n - 1) - cross_bar_idx  # 0 = last bar was the cross
        d_at_cross = float(d_aligned.iloc[cross_bar_idx])
        # Qualifiers: fresh, still alive (k has not fallen back below d), and from the
        # lower zone (see W_STOCH_ZONE_MAX doc-comment) — mid-range churn does not count.
        if bars_since <= W_CROSS_WINDOW and k_last >= d_last and d_at_cross < W_STOCH_ZONE_MAX:
            from_washout = d_at_cross < 25.0
            # Compute gap at latest bar
            gap_val = round(d_last - k_last, 2)
            return {
                "state": "crossed",
                "bars_since": bars_since,
                "d_at_cross": round(d_at_cross, 1),
                "from_washout": from_washout,
                "k": round(k_last, 2),
                "d": round(d_last, 2),
                "gap": gap_val,
            }

    # ---- approaching check (low-zone only — see W_STOCH_ZONE_MAX doc-comment) ----
    gap = d_last - k_last
    if k_last < d_last and k_last > k_prev and gap <= W_STOCH_GAP_MAX and d_last < W_STOCH_ZONE_MAX:
        # Check gap is narrowing: gap now < gap one bar ago (same aligned bars)
        gap_prev = d_prev - k_prev
        if gap < gap_prev:
            return {
                "state": "approaching",
                "bars_since": None,
                "d_at_cross": None,
                "from_washout": False,
                "k": round(k_last, 2),
                "d": round(d_last, 2),
                "gap": round(gap, 2),
            }

    # ---- report latest k/d/gap even in "none" state (when coverage ok) ----
    gap_out = round(d_last - k_last, 2) if (not np.isnan(k_last) and not np.isnan(d_last)) else None
    return {
        "state": "none",
        "bars_since": None,
        "d_at_cross": None,
        "from_washout": False,
        "k": round(k_last, 2) if not np.isnan(k_last) else None,
        "d": round(d_last, 2) if not np.isnan(d_last) else None,
        "gap": gap_out,
    }


# ---------------------------------------------------------------------------
# Price MACD(12,26,9) histogram — mirrors engine/mtf_upturn._price_macd_hist
# ---------------------------------------------------------------------------

def _price_macd_hist(c: pd.Series) -> pd.Series:
    """Standard price MACD(12,26,9) histogram.

    Source: engine/mtf_upturn._price_macd_hist (lines ~253-259).
    Replicated exactly per spec (ewm span 12/26, min_periods 12/26, signal span 9 min_periods 9).
    """
    ema12 = c.ewm(span=12, min_periods=12).mean()
    ema26 = c.ewm(span=26, min_periods=26).mean()
    line = ema12 - ema26
    sig = line.ewm(span=9, min_periods=9).mean()
    return line - sig


# ---------------------------------------------------------------------------
# Detector helpers — each returns its null form on exception (never raise)
# ---------------------------------------------------------------------------

def _compute_wash_2w(daily_close: pd.Series) -> dict:
    """2W StochRSI washout state.

    Uses _biweekly_close (epoch-anchored; raw resample('2W-FRI') FORBIDDEN).
    Coverage: >= MIN_HTF_BARS (35) biweekly bars.
    """
    try:
        bw = _biweekly_close(daily_close)
        if len(bw) < MIN_HTF_BARS:
            return _null_wash()
        k, _ = _stoch_rsi_kd(bw)
        kc = k.dropna()
        if len(kc) < 2:
            return {"state": "none", "k": None, "coverage": True}
        state = _wash_state(kc)
        return {"state": state, "k": round(float(kc.iloc[-1]), 2), "coverage": True}
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_wash_2w failed: %s", exc)
        return _null_wash()


def _compute_wash_1m(daily_close: pd.Series) -> dict:
    """1M StochRSI washout state.

    Monthly resampled as ME (month-end), in-progress month included — mirrors
    house weekly convention (W-FRI in-progress week included, per setup_tier/coiled/mtf_upturn).
    Coverage: >= MIN_HTF_BARS (35) monthly bars AND >= MIN_DAILY_BARS_1M (250) daily bars.
    """
    try:
        if len(daily_close) < MIN_DAILY_BARS_1M:
            return _null_wash()
        # ME = month-end; in-progress month included (same convention as W-FRI weekly)
        mo = daily_close.resample("ME").last().dropna()
        if len(mo) < MIN_HTF_BARS:
            return _null_wash()
        k, _ = _stoch_rsi_kd(mo)
        kc = k.dropna()
        if len(kc) < 2:
            return {"state": "none", "k": None, "coverage": True}
        state = _wash_state(kc)
        return {"state": state, "k": round(float(kc.iloc[-1]), 2), "coverage": True}
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_wash_1m failed: %s", exc)
        return _null_wash()


def _compute_w_macd(wk: pd.Series) -> dict:
    """Weekly RSI-MACD and price-MACD family state.

    RSI-MACD: house variant from engine.signal_quality._rsi_macd
              (EMA(RSI14,14) - EMA(RSI14,60), signal=EMA(macd,5))
    Price MACD: MACD(12,26,9) hist via _price_macd_hist (mirrors mtf_upturn)
    """
    try:
        macd_rsi, sig_rsi = _rsi_macd(wk)
        rsi_hist = macd_rsi - sig_rsi

        price_hist = _price_macd_hist(wk)

        return _macd_state(rsi_hist, price_hist)
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_w_macd failed: %s", exc)
        return _null_w_macd()


def _compute_w_stoch(wk: pd.Series) -> dict:
    """Weekly 1W StochRSI k/d cross state."""
    try:
        k, d = _stoch_rsi_kd(wk)
        return _stoch_cross_state(k, d)
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_w_stoch failed: %s", exc)
        return _null_w_stoch()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def entry_snapshot(daily_close: pd.Series | None) -> dict:
    """Compute the entry-timing snapshot for a single name on the congress watchlist.

    Parameters
    ----------
    daily_close : pd.Series | None
        Date-indexed daily close prices (ascending).  None or too short (<MIN_DAILY_BARS)
        -> covered=False, all sub-dicts return null/none forms.

    Returns
    -------
    dict — frozen-field contract (all keys always present):
      covered     : bool
      wash_2w     : {"state": "now"|"recent"|"near"|"none", "k": float|None, "coverage": bool}
      wash_1m     : {"state": "now"|"recent"|"near"|"none", "k": float|None, "coverage": bool}
      dual_washout: bool   # wash_2w hit AND wash_1m hit (hit = state in {"now","recent"})
      w_macd      : {"state": "crossed"|"approaching"|"none", "kind": str|None,
                     "bars_since": int|None, "eta_bars": float|None}
      w_stoch     : {"state": "crossed"|"approaching"|"none", "bars_since": int|None,
                     "d_at_cross": float|None, "from_washout": bool,
                     "k": float|None, "d": float|None, "gap": float|None}

    Never raises.
    """
    # ---- null (uncovered) form ----
    uncovered: dict = {
        "covered": False,
        "wash_2w": _null_wash(),
        "wash_1m": _null_wash(),
        "dual_washout": False,
        "w_macd": _null_w_macd(),
        "w_stoch": _null_w_stoch(),
    }

    if daily_close is None:
        return uncovered

    try:
        c = daily_close.dropna()
    except Exception:
        return uncovered

    if len(c) < MIN_DAILY_BARS:
        return uncovered

    # Ensure DatetimeIndex
    try:
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
    except Exception:
        return uncovered

    # ---- weekly bars for stoch + macd detectors ----
    # House weekly convention: W-FRI, in-progress week included (same as setup_tier/coiled/mtf_upturn)
    try:
        wk = c.resample("W-FRI").last().dropna()
    except Exception as exc:
        log.debug("entry_snapshot: weekly resample failed: %s", exc)
        return uncovered

    # ---- 2W and 1M washout ----
    wash_2w = _compute_wash_2w(c)
    wash_1m = _compute_wash_1m(c)

    # ---- weekly detectors (coverage gate: >= MIN_WEEKLY_BARS) ----
    if len(wk) >= MIN_WEEKLY_BARS:
        w_macd = _compute_w_macd(wk)
        w_stoch = _compute_w_stoch(wk)
    else:
        w_macd = _null_w_macd()
        w_stoch = _null_w_stoch()

    # ---- dual_washout: both 2W and 1M hit (state in {"now","recent"}) ----
    _hit_states = {"now", "recent"}
    dual_washout = (
        wash_2w["state"] in _hit_states
        and wash_1m["state"] in _hit_states
    )

    return {
        "covered": True,
        "wash_2w": wash_2w,
        "wash_1m": wash_1m,
        "dual_washout": dual_washout,
        "w_macd": w_macd,
        "w_stoch": w_stoch,
    }
