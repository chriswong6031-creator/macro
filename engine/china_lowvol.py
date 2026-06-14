"""China "Defensive (low-vol)" sleeve — a validated A-share defensive tilt.

Phase 0 (scripts/china_lowvol_phase0.py → reports/china-lowvol-phase0.md) found the
low-volatility anomaly present on A-shares in its textbook DEFENSIVE form: the
lowest-volatility quintile earned market-like returns (~27% vs ~28%) with a materially
SHALLOWER drawdown (−57% vs −66% market, −71% high-vol) → a higher Sharpe (0.98 vs 0.88
market vs 0.76 high-vol), monotone Q1→Q5 across both volatility and beta, cross-sectional
and sector-neutral. It is NOT a long-short alpha (the Q1−Q5 spread is ~0) — it is a
risk-adjusted DEFENSIVE TILT: same return, less risk, low turnover.

So this surfaces the lowest-volatility names (annualized trailing σ) — the defensive
sleeve — applying the same responsibility screens as the reversal watch (non-ST/delisting
+ a market-cap floor). It is the conservative complement to the aggressive Mean-reversion
watch (engine/china_reversal.py): defensive exposure, not a return-maximizer.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.china_reversal import is_st          # shared ST/delisting screen

log = logging.getLogger(__name__)

NOTE = ("Lowest-volatility A-share names — the validated defensive tilt (low-vol anomaly): "
        "market-like returns with lower drawdown. A risk-aware sleeve, not a return-maximizer.")


def _causal_beta(R: pd.DataFrame, m: pd.Series, win: int, minp: int) -> pd.DataFrame:
    return (R.rolling(win, min_periods=minp).cov(m)
            .div(m.rolling(win, min_periods=minp).var(), axis=0)).shift(1)


def lowvol_sleeve(closes: pd.DataFrame, tkr_sector: dict, tkr_name: dict, *,
                  tkr_name_zh: dict | None = None, tkr_mktcap: dict | None = None,
                  win: int = 252, top_n: int = 16, min_sector: int = 6,
                  mcap_floor_yi: float = 30.0, vol_floor: float = 0.06, asof=None) -> dict | None:
    """Rank the universe by trailing annualized volatility (ascending) and surface the
    lowest-vol names — the validated A-share defensive sleeve. Screened for ST/delisting
    + a market-cap floor. Best-effort: None on missing/short data, never raises."""
    if closes is None or closes.empty:
        return None
    tkr_name_zh = tkr_name_zh or {}
    tkr_mktcap = tkr_mktcap or {}
    if asof is not None:
        closes = closes.loc[:pd.Timestamp(asof)]
    minp = max(win // 2, 60)
    if len(closes) < minp + 5:
        log.warning("china lowvol: panel too short (%d)", len(closes))
        return None

    R = closes.pct_change(fill_method=None)
    vol = (R.rolling(win, min_periods=minp).std() * np.sqrt(252)).iloc[-1]
    beta = _causal_beta(R, R.mean(axis=1), win, minp).iloc[-1]      # beta to the EW market
    d = pd.DataFrame({"vol": vol, "beta": beta})
    d["sector"] = [tkr_sector.get(t, "—") for t in d.index]
    d = d[d["vol"].notna() & (d["sector"] != "—")]
    # vol floor: a sub-floor annualized σ (here <6%) is a HALTED / suspended / flat-priced
    # stock, not a genuinely defensive one — exclude the artifact (real A-share low-vol
    # utilities run ~10-15%). Without this, a halted name with near-zero σ ranks #1.
    n_flat = int((d["vol"] < vol_floor).sum())
    d = d[d["vol"] >= vol_floor]

    n_pre = len(d)
    d = d.drop(index=[t for t in d.index if is_st(tkr_name_zh.get(t), tkr_name.get(t))], errors="ignore")
    n_st = n_pre - len(d)
    n_pre2 = len(d)
    if tkr_mktcap:
        d = d[[float(tkr_mktcap.get(t, mcap_floor_yi)) >= mcap_floor_yi for t in d.index]]
    n_illiq = n_pre2 - len(d)
    if len(d) < min_sector * 2:
        log.warning("china lowvol: too few names after screens (%d)", len(d))
        return None

    d["vol_pct"] = d["vol"].rank(pct=True) * 100.0                  # low pct = low vol = defensive
    order = d.sort_values("vol")                                    # lowest vol first

    def rec(t: str) -> dict:
        r = d.loc[t]
        return {"ticker": t, "name": tkr_name.get(t, t), "sector": r["sector"],
                "vol_pct_ann": round(float(r["vol"]) * 100, 1),
                "beta": round(float(r["beta"]), 2) if np.isfinite(r["beta"]) else None,
                "vol_rank_pct": round(float(r["vol_pct"]), 0),
                "mktcap_yi": round(float(tkr_mktcap.get(t, 0)), 0) if tkr_mktcap else None}

    return {"as_of": str(closes.index.max().date()), "n": int(len(d)), "note": NOTE,
            "win_days": win, "sleeve": [rec(t) for t in order.head(top_n).index],
            "screened": {"st": int(n_st), "illiquid": int(n_illiq), "flat": int(n_flat)}}
