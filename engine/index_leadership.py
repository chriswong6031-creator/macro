"""engine/index_leadership.py — INDEX-LEVEL leadership & rotation acceleration.

Pure compute. Lifts the subsector RRG / velocity math (``engine.subsector_rotation``)
to the INDEX level so the Subsector Confluence board can answer two questions the
per-subsector tabs cannot on their own:

  1. **Which of the four universes is the RISING STAR** — not the one leading *now*,
     but the one whose leadership is *accelerating* most vs the others. Measured on
     three orthogonal legs, cross-ranked across the tabs:
       • return acceleration   (index vs the cross-tab median, recent pace vs baseline)
       • breadth thrust        (Δ share of the tab's subsector-baskets above their 50-DMA)
       • participation         (share of the tab's subsectors improving / accelerating)

  2. **Within each universe, two DELIBERATELY-SEPARATE rotation lists** (the user's
     runner-vs-bottomer split — a runner must never crowd out a bottomer):
       • RUNNING  — already leading AND accelerating  (RRG 'leading' quadrant).
       • COILING  — laggards turning up               (RRG 'improving' quadrant), with a
         higher-timeframe guard so a relative-strength uptick in a subsector still in a
         confirmed downtrend / distribution does NOT masquerade as 'about to run'
         (the "3-day bounce in a 2-week/monthly bear" trap). This is a v1 rotation-derived
         coil list; the deeper bottom-radar port (2W timeframe + macro veto + capitulation
         legs) is a later phase.

It also reads the observable LEADERSHIP-DRIVER ratios (RSP/SPY breadth-of-leadership,
IWM/SPY size, IWF/IWD style, XLK/RSP tech-concentration) so the page can say WHY
leadership sits where it does — the measurable read, not a regime label.

HONEST BY CONSTRUCTION. Cross-sectional (each tab is judged vs the other tabs); a
4-point z-score is noisy, so the raw legs are always surfaced alongside the composite.
DISPLAY-ONLY context, never scored into an allocation — the same posture as
``engine.subsector_rotation`` / ``engine.velocity`` / ``engine.market_state``.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from engine.subsector_rotation import _rotation_metrics, _zscore

# trading-day windows for the rolling horizons (match subsector_rotation's MOM set).
_HZ_BARS = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}


# ----------------------------------------------------------------- primitives ----

def horizon_returns(close: pd.Series | None) -> dict[str, float | None]:
    """{'1W','1M','3M','6M','1Y': pct} rolling returns off a close series (leak-free —
    each is last / bar-n-ago). None per horizon when the series is too short."""
    out = {h: None for h in _HZ_BARS}
    if close is None:
        return out
    c = close.dropna()
    if len(c) < 6:
        return out
    last = float(c.iloc[-1])
    for h, n in _HZ_BARS.items():
        if len(c) > n:
            base = c.iloc[-1 - n]
            if not pd.isna(base) and float(base) != 0.0:
                out[h] = round((last / float(base) - 1.0) * 100.0, 3)
    return out


def _above_ma(close: pd.Series, window: int = 50, lag: int = 0) -> float | None:
    """1.0 if close is above its `window`-DMA `lag` bars back, else 0.0 (None if short)."""
    c = close.dropna()
    if len(c) < window + lag + 1:
        return None
    ma = c.rolling(window).mean()
    i = -1 - lag
    px, m = c.iloc[i], ma.iloc[i]
    if pd.isna(px) or pd.isna(m):
        return None
    return 1.0 if float(px) > float(m) else 0.0


def breadth_thrust(closes: Sequence[pd.Series], window: int = 50, lag: int = 20) -> float | None:
    """Δ in the share of a tab's subsector-baskets trading above their own `window`-DMA
    (now vs `lag` bars ago) — a self-contained breadth THRUST off price history alone
    (no snapshot log needed). Positive = more baskets reclaiming their trend = broadening."""
    now, prev = [], []
    for c in closes:
        a = _above_ma(c, window, 0)
        b = _above_ma(c, window, lag)
        if a is not None:
            now.append(a)
        if b is not None:
            prev.append(b)
    if not now or not prev:
        return None
    return round(float(np.mean(now)) - float(np.mean(prev)), 4)


# -------------------------------------------------------------- within-a-tab ----

def within_tab_rotation(groups: Mapping[str, Mapping]) -> dict:
    """Cross-sectional RRG over ONE tab's subsectors (benchmark = the median subsector,
    exactly like subsector_rotation), then split into the two separate lists.

    `groups` : {key: {"hz": {horizon: pct}, "regime_state", "regime_side", "above200",
                       "n_priced", "label", "sector", "entry_tier", "rs_60d"}}
    Returns  : {"metrics": {key: rot}, "rising": [entry], "coiling": [entry],
                "participation": {"frac_improving", "mean_emerging", "n"}}
    """
    keys = list(groups)
    if not keys:
        return {"metrics": {}, "rising": [], "coiling": [],
                "participation": {"frac_improving": None, "mean_emerging": None, "n": 0}}

    met = _rotation_metrics({k: dict(groups[k].get("hz") or {}) for k in keys})

    def _entry(k: str) -> dict:
        g, m = groups[k], met[k]
        return {
            "key": k, "label": g.get("label") or k, "sector": g.get("sector"),
            "rs_ratio": m["rs_ratio"], "rs_mom": m["rs_mom"], "accel": m["accel"],
            "quadrant": m["quadrant"], "emerging_score": m["emerging_score"],
            "regime_state": g.get("regime_state"), "regime_side": g.get("regime_side"),
            "entry_tier": g.get("entry_tier"), "rs_60d": g.get("rs_60d"),
            "above200": bool(g.get("above200")),
        }

    def _rising_ok(k: str) -> bool:
        g, m = groups[k], met[k]
        if (g.get("n_priced") or 0) < 3 or m["quadrant"] != "leading" or m["rs_mom"] <= 0:
            return False
        # a genuine RUNNER leads its peers AND is not distributing / below its own trend — a
        # relative-strength 'leader' that is TOPPING/SELLING or below its 200-DMA is a late/hollow
        # leader (it belongs to the board's headwind list), not a rising star.
        return g.get("regime_state") not in ("TOPPING", "SELL", "BELOW_TREND")

    def _coiling_ok(k: str) -> bool:
        g, m = groups[k], met[k]
        if (g.get("n_priced") or 0) < 3 or m["quadrant"] != "improving":
            return False
        if m["accel"] is not None and m["accel"] < 0:
            return False
        side, state = g.get("regime_side"), g.get("regime_state")
        if side == "avoid" or state in ("SELL", "TOPPING"):
            return False
        # the "3D bounce in a 2W/1M bear" guard: a laggard turning up while still below its
        # own trend is a knife, not a coil — require it be above its 200-DMA to qualify.
        if state == "BELOW_TREND" and not g.get("above200"):
            return False
        return True

    rising = sorted((_entry(k) for k in keys if _rising_ok(k)),
                    key=lambda e: e["emerging_score"], reverse=True)
    coiling = sorted((_entry(k) for k in keys if _coiling_ok(k)),
                     key=lambda e: e["emerging_score"], reverse=True)

    improving = [k for k in keys if met[k]["rs_mom"] > 0 and (met[k]["accel"] is None or met[k]["accel"] >= 0)]
    emerging_vals = [met[k]["emerging_score"] for k in keys]
    partic = {
        "frac_improving": round(len(improving) / len(keys), 3) if keys else None,
        "mean_emerging": round(float(np.mean(emerging_vals)), 3) if emerging_vals else None,
        "n": len(keys),
    }
    return {"metrics": met, "rising": rising, "coiling": coiling, "participation": partic}


# --------------------------------------------------------------- cross-a-tab ----

def cross_tab_leadership(
    tab_reps: Mapping[str, Mapping[str, float]],
    tab_breadth: Mapping[str, float | None],
    tab_partic: Mapping[str, float | None],
    *, weights: tuple[float, float, float] = (0.40, 0.30, 0.30),
) -> dict:
    """Rank the tabs by a Leadership Acceleration Score (LAS).

    tab_reps    : {tab: {horizon: pct}} — the tab's representative index return.
    tab_breadth : {tab: breadth_thrust} — Δ share above 50-DMA.
    tab_partic  : {tab: frac_improving} — share of the tab's subsectors improving.

    LAS = w1·z(return_accel) + w2·z(breadth_thrust) + w3·z(participation), z-scored
    ACROSS the tabs. rising_star = argmax(LAS); leader_now = argmax(rs_ratio level).
    """
    tabs = list(tab_reps)
    rot = _rotation_metrics(dict(tab_reps)) if tabs else {}
    z_ret = _zscore({t: (rot.get(t, {}).get("z_accel")) for t in tabs})
    z_brd = _zscore({t: tab_breadth.get(t) for t in tabs})
    z_par = _zscore({t: tab_partic.get(t) for t in tabs})
    w1, w2, w3 = weights

    out: dict[str, dict] = {}
    for t in tabs:
        m = rot.get(t, {})
        las = w1 * z_ret.get(t, 0.0) + w2 * z_brd.get(t, 0.0) + w3 * z_par.get(t, 0.0)
        out[t] = {
            "rs_ratio": m.get("rs_ratio"), "rs_mom": m.get("rs_mom"),
            "accel": m.get("accel"), "quadrant": m.get("quadrant"),
            "breadth_thrust": tab_breadth.get(t), "participation": tab_partic.get(t),
            "z_return": round(z_ret.get(t, 0.0), 3), "z_breadth": round(z_brd.get(t, 0.0), 3),
            "z_participation": round(z_par.get(t, 0.0), 3), "las": round(float(las), 3),
        }

    rising_star = max(tabs, key=lambda t: out[t]["las"]) if tabs else None
    leader_now = max(tabs, key=lambda t: (out[t]["rs_ratio"] if out[t]["rs_ratio"] is not None else -9e9)) if tabs else None
    return {"tabs": out, "rising_star": rising_star, "leader_now": leader_now}


# ----------------------------------------------------------- driver ratios ----

def ratio_read(num: pd.Series, den: pd.Series) -> dict | None:
    """RS-ratio read for a leadership pair: latest ratio, 20d/60d momentum, 200-DMA
    posture, 1y percentile. All leak-free (trailing only)."""
    if num is None or den is None:
        return None
    r = (num.dropna() / den.reindex(num.index)).dropna()
    if len(r) < 70:
        return None

    def _mom(n: int) -> float | None:
        if len(r) <= n:
            return None
        base = float(r.iloc[-1 - n])
        return round((float(r.iloc[-1]) / base - 1.0) * 100.0, 2) if base else None

    ma200 = r.rolling(200).mean().iloc[-1] if len(r) >= 200 else None
    win = r.iloc[-252:]
    pctile = round(float(win.rank(pct=True).iloc[-1]) * 100.0, 0) if len(win) > 20 else None
    return {
        "last": round(float(r.iloc[-1]), 4),
        "mom20": _mom(20), "mom60": _mom(60),
        "above200": (bool(r.iloc[-1] > ma200) if ma200 is not None and not pd.isna(ma200) else None),
        "pctile": pctile,
    }
