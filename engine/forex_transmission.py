"""Dollar cross-asset transmission — how today's broad-USD move co-moves with the
other markets the dashboard tracks (equities, commodities, bonds, EM, crypto).

The dollar is the master price: a stronger dollar mechanically pressures dollar-priced
commodities, tightens global financial conditions for EM, and competes with risk
assets. This leaf publishes, for each asset, the LIVE rolling beta and correlation of
its daily return to the broad-dollar return — a fast (~quarter) and a slow (~year)
window — plus a stability read (do the two windows agree on sign?) and, for the
risk-sensitive legs, a calm-vs-stress split (the sign flip is the whole story).

HONESTY BAR (load-bearing):
  • CONTEMPORANEOUS CO-MOVEMENT, not causation or a forecast. At a daily frequency
    every row is coincident — the dollar move often IS the same risk/tightening
    impulse. There is deliberately NO "USD leads asset X" tag (the only dollar->asset
    lead in the literature is a slow ~1–1.5y EM-growth/financial-conditions effect,
    surfaced separately as a caged macro note, with no point estimates).
  • Betas are UNSTABLE and regime-dependent — sign flips are common. We compute them
    live from the store and flag instability rather than hardcoding any literature
    number.
  • Display-only. Nothing here is scored or feeds a trade verdict.

Pure / additive leaf: guards missing data, returns {} rather than raising.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# config key -> display metadata. is_yield: the series is a yield level (price return
# proxied by -Δyield). regime: show a calm-vs-stress correlation split. gold: show the
# real-rate (DFII10) decomposition leg.
_ASSET_META = {
    "SPY":   {"label": "US equities", "zh": "美国股票", "is_yield": False, "regime": True},
    "EEM":   {"label": "EM equities", "zh": "新兴市场股票", "is_yield": False, "regime": True},
    "GC=F":  {"label": "Gold", "zh": "黄金", "is_yield": False, "gold": True},
    "CL=F":  {"label": "Oil (WTI)", "zh": "原油", "is_yield": False},
    "HG=F":  {"label": "Copper", "zh": "铜", "is_yield": False},
    "UST10": {"label": "10y Treasury", "zh": "10年期国债", "is_yield": True},
    "BTC":   {"label": "Bitcoin", "zh": "比特币", "is_yield": False, "regime": True},
}


def _ret(s: pd.Series, is_yield: bool) -> pd.Series:
    """Daily return. Prices -> log return (non-positive prices, e.g. WTI's Apr-2020
    negative print, masked to NaN); a yield level -> -Δyield (duration-return sign
    proxy, so a falling yield = a positive bond return)."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    if is_yield:
        return (-s.diff()).rename(s.name)
    return np.log(s.where(s > 0)).diff().rename(s.name)


def _beta_corr(da: pd.Series, du: pd.Series, w: int) -> tuple[float | None, float | None]:
    """Last rolling beta (of asset return on USD return) and correlation over window w."""
    j = pd.concat([da.rename("a"), du.rename("u")], axis=1).dropna()
    if len(j) < max(20, w // 3):
        return None, None
    cov = j["a"].rolling(w, min_periods=max(20, w // 3)).cov(j["u"])
    var = j["u"].rolling(w, min_periods=max(20, w // 3)).var()
    corr = j["a"].rolling(w, min_periods=max(20, w // 3)).corr(j["u"])
    beta = cov / var.replace(0, np.nan)
    b = beta.dropna()
    c = corr.dropna()
    return (float(b.iloc[-1]) if len(b) else None,
            float(c.iloc[-1]) if len(c) else None)


def _regime_split(da: pd.Series, du: pd.Series, risk_off: pd.Series) -> dict | None:
    """Correlation of asset vs USD returns conditioned on the risk-off regime
    (risk_off > 0 = stress, else calm). The sign flip across regimes is the headline."""
    if risk_off is None:
        return None
    j = pd.concat([da.rename("a"), du.rename("u"),
                   risk_off.reindex(da.index.union(du.index)).rename("r")], axis=1).dropna()
    if len(j) < 200:
        return None
    stress = j[j["r"] > 0]
    calm = j[j["r"] <= 0]
    out = {}
    if len(calm) >= 60:
        out["calm"] = round(float(calm["a"].corr(calm["u"])), 2)
    if len(stress) >= 60:
        out["stress"] = round(float(stress["a"].corr(stress["u"])), 2)
    return out or None


def transmission(broad: pd.Series | None, assets: dict, real: pd.Series | None,
                 risk_off: pd.Series | None, cfg: dict) -> dict:
    """Build the dollar transmission map. `broad` = broad-USD level series; `assets` =
    {config_key: level series}; `real` = DFII10 real yield (for the gold leg);
    `risk_off` = the dollar-smile risk-off composite (for the regime split)."""
    try:
        if broad is None or broad.empty:
            return {}
        fast, slow = cfg.get("fast_window_d", 63), cfg.get("slow_window_d", 252)
        stale = cfg.get("stale_corr", 0.10)
        du = _ret(broad, False)
        # current USD direction over the fast window
        roc = float(broad.dropna().pct_change(fast).iloc[-1]) if len(broad.dropna()) > fast else 0.0
        flat = cfg.get("flat_roc", 0.005)
        usd_dir = "strengthening" if roc > flat else ("weakening" if roc < -flat else "flat")

        rows, headwind, tailwind, unstable = [], [], [], []
        # raw Δreal-yield for the gold decomposition (negative corr = gold rises when
        # real yields fall — the textbook real-rate channel)
        dr = pd.to_numeric(real, errors="coerce").dropna().diff() if real is not None else None
        for key, s in assets.items():
            meta = _ASSET_META.get(key, {"label": key, "zh": key, "is_yield": False})
            if s is None or len(pd.to_numeric(s, errors="coerce").dropna()) < 200:
                continue
            da = _ret(s, meta.get("is_yield", False))
            bf, cf = _beta_corr(da, du, fast)
            bs, cs_ = _beta_corr(da, du, slow)
            if cf is None and cs_ is None:
                continue
            # Use CORRELATION (unit-free, comparable across price-return and yield legs)
            # for the sign/stability read; beta is kept in the data but not the headline.
            # decoupled if the fast corr is tiny; flipping if fast & slow disagree on sign.
            if cf is not None and abs(cf) < stale:
                stability = "decoupled"
            elif (cf is not None and cs_ is not None and cf != 0 and cs_ != 0
                  and np.sign(cf) != np.sign(cs_)):
                stability = "flipping"
            else:
                stability = "stable"
            # effect of a STRENGTHENING dollar (sign of the fast correlation)
            if stability == "decoupled" or cf is None:
                effect = "neutral"
            elif cf < 0:
                effect = "headwind"
            else:
                effect = "tailwind"
            row = {"key": key, "label": meta["label"], "label_zh": meta["zh"],
                   "beta_fast": round(bf, 2) if bf is not None else None,
                   "beta_slow": round(bs, 2) if bs is not None else None,
                   "corr_fast": round(cf, 2) if cf is not None else None,
                   "corr_slow": round(cs_, 2) if cs_ is not None else None,
                   "stability": stability, "effect": effect}
            if meta.get("regime"):
                rs = _regime_split(da, du, risk_off)
                if rs:
                    row["regime_split"] = rs
            if meta.get("gold") and dr is not None:
                _, gc = _beta_corr(da, dr, fast)
                if gc is not None:
                    row["real_corr"] = round(gc, 2)             # gold vs Δreal-yield
            rows.append(row)
            if stability == "flipping":
                unstable.append(meta["label"])
            elif effect == "headwind":
                headwind.append(meta["label"])
            elif effect == "tailwind":
                tailwind.append(meta["label"])
        if not rows:
            return {}
        rows.sort(key=lambda r: -(abs(r["corr_fast"]) if r["corr_fast"] is not None else 0))

        # one-line plain read, no point estimates
        verb = {"strengthening": "stronger", "weakening": "weaker", "flat": "flat"}[usd_dir]
        verb_zh = {"strengthening": "走强", "weakening": "走软", "flat": "横盘"}[usd_dir]
        if usd_dir == "flat":
            read = "The dollar is broadly flat — cross-asset transmission is muted right now."
            read_zh = "美元大体横盘 — 当前跨资产传导较弱。"
        else:
            hp = ", ".join(headwind[:3]) if usd_dir == "strengthening" else ", ".join(tailwind[:3])
            other = tailwind if usd_dir == "strengthening" else headwind
            parts = []
            if hp:
                parts.append(f"a {verb} dollar is a {'headwind' if usd_dir=='strengthening' else 'tailwind'} for {hp}")
            if unstable:
                parts.append(f"{', '.join(unstable[:2])} {'is' if len(unstable)==1 else 'are'} sign-unstable (read with caution)")
            read = "Today: " + "; ".join(parts) + "." if parts else \
                   f"The dollar is {verb}; transmission is mixed."
            read_zh = f"当前美元{verb_zh}；详见下表（同步关系，非预测）。"

        return {"usd_dir": usd_dir, "usd_roc_pct": round(100 * roc, 1),
                "rows": rows, "headwind_for": headwind, "tailwind_for": tailwind,
                "unstable": unstable, "read": read, "read_zh": read_zh,
                "fast_d": fast, "slow_d": slow}
    except Exception as e:  # noqa: BLE001 — transmission must never break the build
        log.warning("transmission failed (%s)", e)
        return {}
