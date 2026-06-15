"""Treasury auction absorption — DISPLAY-ONLY coincident context (NEVER a score).

Turns coupon-auction RESULTS (collectors.treasury_auctions) into a per-tenor "is the
market absorbing duration supply smoothly?" read plus one composite absorption regime
(firm / smooth / watch / stressed) for the bonds page.

WHY THIS IS NEVER SCORED OR PROPAGATED — scripts/auction_stress_phase0.py, 1,362
coupon auctions 2008-2026: the demand signal is REAL but priced within the session.
Contemporaneous IC(stress, auction-day Δyield) = +0.28, but the FORWARD IC is ~-0.07,
the WRONG sign vs the "weak auction => higher yields" thesis (a mean-reversion
snapback), and the long end (10y/30y) has no forward signal at all. So this leaf is a
coincident CONTEXT panel only: it never touches engine.conditions / engine.axes, the
bond health score, or the cross-asset drivers hand-off, and every snapshot carries
context_only=True.

SIGNAL (per tenor, CAUSAL expanding-z over only PRIOR auctions of that tenor):
    stress = mean[ -z(bid_to_cover), -z(indirect_share), +z(dealer_share) ]
  higher = weaker demand. The composite regime is the mean stress over recent coupon
  auctions; per-tenor tiles show the latest raw demand metrics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from collectors import treasury_auctions
from lib import config

_REG_WORD = {"firm": ("firm", "强劲"), "smooth": ("smooth", "顺畅"),
             "watch": ("softening", "转弱"), "stressed": ("weak", "承压")}


def _cfg() -> dict:
    return config.load()["auction_stress"]


def _r(v, n=2):
    return round(float(v), n) if v is not None and pd.notna(v) else None


def _pct(v, n=0):
    return round(float(v) * 100, n) if v is not None and pd.notna(v) else None


def _causal_z(g: pd.Series, minobs: int) -> pd.Series:
    """Expanding z using only PRIOR observations (shift(1)); NaN until `minobs` priors."""
    mu = g.shift(1).expanding(min_periods=minobs).mean()
    sd = g.shift(1).expanding(min_periods=minobs).std(ddof=0)
    return (g - mu) / sd.replace(0, np.nan)


def _regime(z, cfg) -> str | None:
    if z is None or pd.isna(z):
        return None
    if z >= cfg["stressed_z"]:
        return "stressed"
    if z >= cfg["watch_z"]:
        return "watch"
    if z <= cfg["firm_z"]:
        return "firm"
    return "smooth"


def auction_frame(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Event panel (one row per auction) with per-tenor causal demand z + composite
    stress (higher = weaker demand) + a rolling smoothing for the chart."""
    cfg = _cfg()
    if df is None:
        df = treasury_auctions.load_results()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["auction_date"] = pd.to_datetime(df["auction_date"])
    df = df.dropna(subset=["auction_date", "tenor", "btc"]).sort_values("auction_date")
    df["tenor"] = df["tenor"].astype(int)
    minobs = int(cfg["z_minobs"])
    for col in ("btc", "indirect_share", "dealer_share"):
        if col in df:
            df[f"z_{col}"] = df.groupby("tenor")[col].transform(lambda s: _causal_z(s, minobs))
    parts = []
    if "z_btc" in df:
        parts.append(-df["z_btc"])                 # low bid-to-cover = weak demand
    if "z_indirect_share" in df:
        parts.append(-df["z_indirect_share"])      # low real-money share = weak demand
    if "z_dealer_share" in df:
        parts.append(df["z_dealer_share"])         # high dealer takedown = weak demand
    df["stress"] = pd.concat(parts, axis=1).mean(axis=1) if parts else np.nan
    df["stress_roll"] = df["stress"].rolling(12, min_periods=4).mean()
    return df.reset_index(drop=True)


def _verdict(s: dict) -> tuple[str, str]:
    rw = _REG_WORD.get(s.get("regime"), ("—", "—"))
    soft = [t["label"] for t in s["tenors"] if t.get("soft")]
    en = [f"Duration absorption {rw[0]} (recent coupon-demand z {s.get('composite_z')})."]
    zh = [f"久期吸收{rw[1]}（近期息票需求z {s.get('composite_z')}）。"]
    if soft:
        en.append(f"Softest at {', '.join(soft)}.")
        zh.append(f"最弱：{', '.join(soft)}。")
    en.append("Coincident context — auction results are priced intraday, not a forward signal.")
    zh.append("同步背景——招标结果于盘中即被定价，非前瞻信号。")
    return " ".join(en), "".join(zh)


def auction_snapshot(df: pd.DataFrame | None = None) -> dict | None:
    """DISPLAY-ONLY snapshot. Returns None if there is no data (build skips the panel)."""
    cfg = _cfg()
    fr = df if (df is not None and "stress" in getattr(df, "columns", [])) else auction_frame(df)
    if fr is None or fr.empty:
        return None
    fr = fr.dropna(subset=["auction_date"]).sort_values("auction_date")
    as_of = fr["auction_date"].max()

    recent = fr[fr["auction_date"] >= as_of - pd.Timedelta(days=int(cfg["recent_window_d"]))]
    comp = float(recent["stress"].dropna().mean()) if recent["stress"].notna().any() else None
    comp = _r(comp, 2)        # classify on the displayed value so chip & number always agree

    tenors = []
    for t in cfg["tenors"]:
        sub = fr[fr["tenor"] == t]
        if sub.empty:
            continue
        r = sub.iloc[-1]
        dz = (-float(r["stress"])) if pd.notna(r.get("stress")) else None   # +ve = strong demand
        tenors.append({
            "tenor": int(t), "label": f"{int(t)}Y", "date": r["auction_date"].strftime("%Y-%m-%d"),
            "btc": _r(r.get("btc")), "indirect_pct": _pct(r.get("indirect_share")),
            "dealer_pct": _pct(r.get("dealer_share")), "demand_z": _r(dz, 1),
            "soft": bool(dz is not None and dz < -0.5),
        })

    sw = int(cfg["supply_window_d"])
    cur = fr[fr["auction_date"] >= as_of - pd.Timedelta(days=sw)]
    prev = fr[(fr["auction_date"] < as_of - pd.Timedelta(days=sw))
              & (fr["auction_date"] >= as_of - pd.Timedelta(days=2 * sw))]
    gross = float(cur["offering"].dropna().sum()) / 1e9 if "offering" in fr else None
    gross_prev = float(prev["offering"].dropna().sum()) / 1e9 if "offering" in fr else None
    trend = None
    if gross is not None and gross_prev:
        trend = "rising" if gross > gross_prev * 1.05 else "falling" if gross < gross_prev * 0.95 else "flat"
    supply = {"coupon_gross_bn": _r(gross, 0), "window_d": sw, "trend": trend, "n": int(len(cur))}

    recent_auctions = []
    for _, r in fr.tail(3)[::-1].iterrows():
        st = r.get("stress")
        recent_auctions.append({
            "term": r.get("term"), "date": r["auction_date"].strftime("%Y-%m-%d"),
            "btc": _r(r.get("btc")), "indirect_pct": _pct(r.get("indirect_share")),
            "dealer_pct": _pct(r.get("dealer_share")),
            "soft": bool(pd.notna(st) and float(st) >= cfg["watch_z"]),
        })

    snap = {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "context_only": True,                       # NEVER scored or propagated
        "composite_z": _r(comp, 2),
        "regime": _regime(comp, cfg),
        "tenors": tenors, "supply": supply, "recent": recent_auctions,
        "n_auctions": int(len(fr)),
        "span": f"{fr['auction_date'].min().date()}..{fr['auction_date'].max().date()}",
    }
    snap["verdict_en"], snap["verdict_zh"] = _verdict(snap)
    return snap
