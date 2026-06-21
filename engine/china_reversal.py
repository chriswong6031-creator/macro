"""China "Mean-reversion watch" — the VALIDATED A-share stock signal.

Phase 0 (scripts/china_reversal_phase0.py → reports/china-reversal-phase0.md) settled the
A-share cross-section: MOMENTUM is dead; the validated edge is **3-month within-sector
REVERSAL, deepest quintile, with NO confirmation gate** (Sharpe 0.58 over 388 rebalances,
1990→2026). Crucially, the intuitive refinements all HURT — waiting for an early turn
flips the excess negative (you buy after the bounce), and a quality floor removes the
deepest decliners that carry the most reversal fuel.

So this surfaces the names most beaten-down vs their SECTOR over the last 3 months — the
mean-reversion candidates — applying only two RESPONSIBILITY screens (NOT alpha/quality
filters, which forfeit the edge):
  * non-ST   — drop ST / *ST / delisting-flagged names (structural / fraud risk)
  * liquidity — a light market-cap floor (the watch must be tradable)

Honest framing for the page: a HIGH-VARIANCE, HIGH-TURNOVER CONTRARIAN signal — research
candidates to size small, NOT a confident buy list. The measured edge is cross-sectional
SKILL (excess over the equal-weight universe), not a net-of-cost return; the long-run
drawdown is deep (−37.6%) because it buys into weakness.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

NOTE = ("Most beaten-down names vs their sector over 3 months — the validated A-share "
        "mean-reversion signal (momentum is dead here). High-variance contrarian: research "
        "candidates to size small, NOT a buy list.")

# A-share delisting-risk flags (Chinese names): ST / *ST / 退 (delist) / S (pre-reform)
_ST_PREFIXES = ("*ST", "ST", "S*ST", "SST")


def is_st(name_zh: str | None, name: str | None = None) -> bool:
    """Delisting-risk flag from the Chinese short name (ST / *ST / 退市)."""
    s = (name_zh or "").strip()
    if not s and name:                       # fall back to the combined "EN / 中文" display name
        s = name.split(" / ")[-1].strip()
    return s.startswith(_ST_PREFIXES) or "退" in s


def reversal_watch(closes: pd.DataFrame, tkr_sector: dict, tkr_name: dict, *,
                   tkr_name_zh: dict | None = None, tkr_mktcap: dict | None = None,
                   win: int = 63, top_n: int = 16, min_sector: int = 6,
                   mcap_floor_yi: float = 30.0, asof=None) -> dict | None:
    """Rank the deepest within-sector 3-month dips (screened), the validated A-share
    mean-reversion watch. `tkr_mktcap` in 亿 (1e8 CNY); names with mktcap < floor or an
    ST/delisting flag are dropped. Best-effort: None on missing/short data, never raises."""
    if closes is None or closes.empty:
        return None
    tkr_name_zh = tkr_name_zh or {}
    tkr_mktcap = tkr_mktcap or {}
    if asof is not None:
        closes = closes.loc[:pd.Timestamp(asof)]
    if len(closes) < win + 5:
        log.warning("china reversal: panel too short (%d < %d)", len(closes), win)
        return None

    r3 = closes.iloc[-1] / closes.iloc[-(win + 1)] - 1.0          # latest 3-month return
    d = pd.DataFrame({"ret": r3})
    d["sector"] = [tkr_sector.get(t, "—") for t in d.index]
    d = d[d["ret"].notna() & (d["sector"] != "—")]

    # responsibility screens (NOT alpha/quality filters — those hurt the edge)
    n_pre = len(d)
    st_drop = [t for t in d.index if is_st(tkr_name_zh.get(t), tkr_name.get(t))]
    d = d.drop(index=st_drop, errors="ignore")
    n_st = n_pre - len(d)
    n_pre2 = len(d)
    if tkr_mktcap:
        d = d[[float(tkr_mktcap.get(t, mcap_floor_yi)) >= mcap_floor_yi for t in d.index]]
    n_illiq = n_pre2 - len(d)
    if len(d) < min_sector * 2:
        log.warning("china reversal: too few names after screens (%d)", len(d))
        return None

    # within-sector reversal fuel: how far BELOW the sector this name sits over 3 months.
    # Higher rev = deeper relative dip = more mean-reversion fuel. Drop thin sectors so a
    # 2-name "sector" can't dominate the watch.
    big = d.groupby("sector")["ret"].transform("count") >= min_sector
    d = d[big]
    d["rev"] = -(d["ret"] - d.groupby("sector")["ret"].transform("mean"))
    sd = d.groupby("sector")["rev"].transform("std").replace(0, np.nan)
    d["rev_z"] = (d["rev"] / sd).clip(-3, 3)
    d["sector_n"] = d.groupby("sector")["rev"].transform("count").astype(int)
    d["sector_rank"] = d.groupby("sector")["rev"].rank(ascending=False).astype(int)
    d = d[d["rev_z"].notna()]
    if d.empty:
        return None

    def rec(t: str) -> dict:
        r = d.loc[t]
        return {"ticker": t, "name": tkr_name.get(t, t), "sector": r["sector"],
                "ret_3m": round(float(r["ret"]) * 100, 1),
                "rev_z": round(float(r["rev_z"]), 2),
                "sector_rank": int(r["sector_rank"]), "sector_n": int(r["sector_n"]),
                "mktcap_yi": round(float(tkr_mktcap.get(t, 0)), 0) if tkr_mktcap else None}

    watch = [rec(t) for t in d.sort_values("rev_z", ascending=False).head(top_n).index]
    # `watch` is the top-N DISPLAY list; `rev_z_all` is the FULL screened map so the conviction
    # SELECTION axis (CN = 0.55·rev_z) is populated for every name — not just the 16 shown. Before
    # this, ~800 names fell back to residual momentum (alpha), the signal the engine itself labels
    # "not a validated A-share edge", silently breaking the reversal-led CN rank.
    rev_z_all = {t: round(float(d.loc[t, "rev_z"]), 2) for t in d.index if pd.notna(d.loc[t, "rev_z"])}
    return {"as_of": str(closes.index.max().date()), "n": int(len(d)), "note": NOTE,
            "win_days": win, "watch": watch, "rev_z_all": rev_z_all,
            "screened": {"st": int(n_st), "illiquid": int(n_illiq)}}
