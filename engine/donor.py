"""engine/donor.py — G6a market-wide donor-sector context chip (DISPLAY-ONLY).

Faithful port of research/entry_timing/wave5b.py build_sector_composites +
build_donor_timeline (§25 DONOR-UNWIND, amendments #25, Wave-5b registered
post-gate strata).  Shipped under Wave-6 pre-reg G6a (WAVE6_REPORT.md:
deep +5.96 pp / baskets +5.81 pp, episode LB +2.66 pp, majority 69.3%).

KEY CONVENTIONS (from wave5b.py — do not change without re-registering):
  * donor  = top-1 GICS sector by trailing 126d equal-weight return
              (min DONOR_MIN_MEMBERS=5 members with sufficient bars at that day).
  * EW composite  = per-sector average of each member close normalised to its
                    first valid close = 1.0; missing days excluded via skipna.
  * cracking = fresh weekly RSI-MACD bearish cross on the donor EW composite
               within the trailing DONOR_WK_LOOKBACK=4 COMPLETED W-FRI weeks
               (shift(1) prior-closed-week convention — a cross in the CURRENT
               incomplete week must NOT count) OR donor 20d EW return < 0 while
               still top-ranked.
  * intact  = neither leg fires.

Public API:
    donor_state(closes, sector_of) -> dict | None

The function never raises; on insufficient data it returns None.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── tuning_harness lives in research/signal_engine — guarded import ───────────
try:
    import sys as _sys
    _TH_PATH = Path(__file__).resolve().parents[1] / "research" / "signal_engine"
    if str(_TH_PATH) not in _sys.path:
        _sys.path.insert(0, str(_TH_PATH))
    import tuning_harness as _TH  # type: ignore
    _TH_OK = True
except Exception:  # noqa: BLE001
    _TH_OK = False

# ── wave5b §25 params (verbatim) ──────────────────────────────────────────────
DONOR_LB126       = 126    # trailing 126d EW return for donor ranking
DONOR_MIN_MEMBERS = 5      # min 5 members at that day to qualify sector
DONOR_WK_LOOKBACK = 4      # fresh weekly bearish cross within 4 COMPLETED W-FRI weeks
DONOR_20D         = 20     # donor 20d EW return threshold (< 0 while top-ranked)

# minimum per-member bars to include in composite (mirrors stocks panel in wave5b)
_MEMBER_MIN_BARS = 1500


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Pure-Python RSI — used when tuning_harness is unavailable."""
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=n - 1, min_periods=n, adjust=False).mean()
    avg_l = loss.ewm(com=n - 1, min_periods=n, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi_macd_fallback(close: pd.Series):
    """Fallback RSI-MACD when tuning_harness is not importable.

    Params mirror tuning_harness.rsi_macd exactly (RSI_LEN=14, FAST=14,
    BASE=60, SIG=5) so the fallback never silently diverges from the
    registered Wave-5b/Wave-6 spec.
    """
    r    = _rsi(close, n=14)
    macd = _ema(r, 14) - _ema(r, 60)
    sig  = _ema(macd, 5)
    return macd, sig


def _xdn(a: pd.Series, b: pd.Series) -> pd.Series:
    """Bearish cross: a crosses below b."""
    return (a < b) & (a.shift(1) >= b.shift(1))


def _rsi_macd(close: pd.Series):
    if _TH_OK:
        return _TH.rsi_macd(close)
    return _rsi_macd_fallback(close)


# ── composite builder ─────────────────────────────────────────────────────────

def _build_sector_composites(closes: dict[str, pd.Series],
                              sector_of: dict[str, Optional[str]],
                              min_bars: int = _MEMBER_MIN_BARS) -> dict:
    """Build per-GICS-sector EW composite close series.

    Faithful port of wave5b.build_sector_composites.  Each member is
    normalised to its first valid close = 1.0 before equal-weight averaging.
    Returns {'comps': {sector: pd.Series}, 'counts': {sector: pd.Series},
             'members': {sector: [tickers]}}.
    """
    from collections import defaultdict as _dd
    by_sector: dict[str, list] = _dd(list)
    for t, daily in closes.items():
        sec = sector_of.get(t)
        if sec is None:
            continue
        daily = daily.dropna()
        if len(daily) < min_bars:
            continue
        by_sector[sec].append((t, daily))

    comps: dict   = {}
    counts: dict  = {}
    members: dict = {}
    for sec, lst in by_sector.items():
        norm_list = []
        for t, daily in lst:
            first = daily.iloc[0]
            if first <= 0 or np.isnan(first):
                continue
            norm_list.append(daily / first)
        if not norm_list:
            continue
        wide = pd.concat(norm_list, axis=1)
        ew   = wide.mean(axis=1, skipna=True)
        cnt  = wide.notna().sum(axis=1)
        comps[sec]   = ew
        counts[sec]  = cnt
        members[sec] = [t for t, _ in lst]
    return {"comps": comps, "counts": counts, "members": members}


# ── donor timeline (causal) ───────────────────────────────────────────────────

def _build_donor_timeline(comp_bundle: dict) -> pd.DataFrame:
    """Per calendar day: resolve donor sector + cracking legs.

    Faithful port of wave5b.build_donor_timeline.

    Completed-week shift(1) convention: a bearish cross printed on weekly bar w
    is only actionable once that week has CLOSED (one week later).  Rolling any()
    over DONOR_WK_LOOKBACK=4 completed weeks.
    """
    comps  = comp_bundle["comps"]
    counts = comp_bundle["counts"]
    if not comps:
        return pd.DataFrame(columns=["donor", "donor_ret126",
                                     "donor_unwind_wk", "donor_unwind_20d", "donor_unwind"])

    # union daily calendar
    all_idx = None
    for s in comps.values():
        all_idx = s.index if all_idx is None else all_idx.union(s.index)
    all_idx = all_idx.sort_values()

    sec_ret126       = {}
    sec_ret20        = {}
    sec_cnt          = {}
    sec_wk_bear_recent = {}
    for sec, ew in comps.items():
        ewa = ew.reindex(all_idx)
        sec_ret126[sec] = ewa / ewa.shift(DONOR_LB126) - 1.0
        sec_ret20[sec]  = ewa / ewa.shift(DONOR_20D) - 1.0
        sec_cnt[sec]    = counts[sec].reindex(all_idx).fillna(0)

        # weekly RSI-MACD bearish cross (completed-week shift-1 convention)
        wk   = ew.resample("W-FRI").last().dropna()
        if len(wk) < 2:
            sec_wk_bear_recent[sec] = pd.Series(False, index=all_idx)
            continue
        wmacd, wsig = _rsi_macd(wk)
        wbear       = _xdn(wmacd, wsig).fillna(False)
        # shift(1): cross at week w is only KNOWN after that week closes
        wbear_known  = wbear.shift(1).fillna(False)
        # rolling any() over 4 completed weeks
        wbear_recent = wbear_known.rolling(DONOR_WK_LOOKBACK, min_periods=1).max().fillna(0).astype(bool)
        # forward-fill weekly state to daily
        sec_wk_bear_recent[sec] = wbear_recent.reindex(all_idx, method="ffill").fillna(False)

    ret126_df  = pd.DataFrame(sec_ret126, index=all_idx)
    cnt_df     = pd.DataFrame(sec_cnt,    index=all_idx)
    ret20_df   = pd.DataFrame(sec_ret20,  index=all_idx)
    wkbear_df  = pd.DataFrame(sec_wk_bear_recent, index=all_idx)

    # donor = top-1 sector by ret126 among sectors with >=5 live members
    elig       = cnt_df >= DONOR_MIN_MEMBERS
    ret126_elig = ret126_df.where(elig)
    any_elig   = ret126_elig.notna().any(axis=1)
    donor      = pd.Series(np.nan, index=all_idx, dtype=object)
    if any_elig.any():
        donor.loc[any_elig] = ret126_elig.loc[any_elig].idxmax(axis=1)

    rows = []
    for d in all_idx:
        dn = donor.loc[d]
        if not isinstance(dn, str):
            rows.append((d, None, np.nan, False, False, False))
            continue
        r126     = float(ret126_df.at[d, dn])
        r20      = float(ret20_df.at[d, dn])
        wk_bear  = bool(wkbear_df.at[d, dn])
        leg_wk   = wk_bear
        leg_20   = bool(r20 < 0)
        unwind   = bool(leg_wk or leg_20)
        rows.append((d, dn, r126, leg_wk, leg_20, unwind))

    tl = pd.DataFrame(rows, columns=["date", "donor", "donor_ret126",
                                     "donor_unwind_wk", "donor_unwind_20d", "donor_unwind"])
    return tl.set_index("date")


# ── public entry point ────────────────────────────────────────────────────────

def donor_state(closes: dict[str, pd.Series],
                sector_of: dict[str, Optional[str]]) -> Optional[dict]:
    """Compute the market-wide donor-sector context as of the latest close.

    Parameters
    ----------
    closes   : {ticker: pd.Series(close, DatetimeIndex)} — all US stocks' close
               series (dividend-adjusted).  Members with < MEMBER_MIN_BARS bars
               are excluded from the composite.
    sector_of: {ticker: GICS sector | None}

    Returns
    -------
    dict with keys:
        donor_sector  : str   — GICS name of the top-126d EW-return sector
        state         : 'cracking' | 'intact'
        legs          : {'weekly_bear_cross': bool, 'ret20_neg': bool}
        ranked_ret126 : float — 126d EW return of the donor sector composite
        asof          : str   — ISO date of the latest calendar day resolved
        n_sectors     : int   — number of GICS sectors with >=5 members
    or None on insufficient data (< 2 eligible sectors with >=5 members).

    Never raises.
    """
    try:
        comp_bundle = _build_sector_composites(closes, sector_of)
        comps       = comp_bundle.get("comps", {})
        n_sectors   = len(comps)
        if n_sectors < 2:
            return None  # insufficient data

        tl = _build_donor_timeline(comp_bundle)
        if tl.empty:
            return None

        last_row = tl.iloc[-1]
        dn       = last_row["donor"]
        if not isinstance(dn, str):
            return None

        leg_wk  = bool(last_row["donor_unwind_wk"])
        leg_20  = bool(last_row["donor_unwind_20d"])
        unwind  = bool(last_row["donor_unwind"])
        state   = "cracking" if unwind else "intact"
        r126    = float(last_row["donor_ret126"]) if not pd.isna(last_row["donor_ret126"]) else float("nan")
        asof    = tl.index[-1].strftime("%Y-%m-%d")

        return {
            "donor_sector":   dn,
            "state":          state,
            "legs":           {"weekly_bear_cross": leg_wk, "ret20_neg": leg_20},
            "ranked_ret126":  round(r126, 6) if not np.isnan(r126) else None,
            "asof":           asof,
            "n_sectors":      n_sectors,
        }
    except Exception:  # noqa: BLE001 — display-only chip, never fatal
        return None
