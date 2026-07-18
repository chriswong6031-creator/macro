"""Bitcoin Vector — forward-return CONES + the RECOMMENDATION engine.

This is the command-center DECISION layer. It is honest by construction:

* Short/mid-horizon DIRECTION is a measured coin-flip in this repo's own out-of-fold
  calibration (Brier skill ~0). So directional conviction is concentrated ONLY where it
  is actually MEASURED — the calibrated valuation/behaviour EXTREMES (mvrv_z<0 → +40%/90d
  at 72% hit; reserve_risk>0.02 → −42%/90d at 4% hit; Mayer>2.4 / euphoria TOPs).
* Everywhere else the recommendation is DRAWDOWN-MANAGED: size by the validated forward-
  drawdown read (risk_index is a both-halves CONFIRMED drawdown gauge) + the regime, never
  a price prediction.
* The forward-return CONES are EMPIRICAL quantiles of the realized forward distribution
  conditioned on the CURRENT regime (composite_state — categorical, inherently point-in-
  time, no fitted edges). Nothing to overfit; degrades to the risk-band cell, then to the
  unconditional marginal, when thin.

forward_cones() + recommend() are pure and NaN-safe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import forward_dist as FD
from engine.btc_master import plain_name

HORIZONS = {"7d": 7, "30d": 30, "90d": 90}
_RISK_EDGES = (0, 25, 50, 75, 100)


def _f(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _risk_band(ri: float):
    for lo, hi in zip(_RISK_EDGES[:-1], _RISK_EDGES[1:]):
        if (lo == 0 and ri <= hi) or (lo < ri <= hi):
            return lo, hi
    return 75, 100


def forward_cones(sig: pd.DataFrame, horizons: dict = HORIZONS, min_cell: int = 40) -> dict:
    """Per-horizon empirical forward-return distribution conditioned on the live regime.

    Primary conditioning = composite_state (the headline stance); falls back to the
    risk_index band when that cell is thin, then to the unconditional marginal. Returns,
    per horizon: return quantiles p5/25/50/75/95 (%), P(up) vs the unconditional base
    rate, average + p05-tail forward drawdown, n, and the conditioning label."""
    if sig is None or sig.empty or "close" not in sig:
        return {"ok": False}
    close = sig["close"]
    cs = sig.get("composite_state")
    cur = cs.iloc[-1] if cs is not None and pd.notna(cs.iloc[-1]) else None
    ri = sig.get("risk_index")
    ri_now = _f(ri.iloc[-1]) if ri is not None else None
    out = {"ok": True, "regime": cur if isinstance(cur, str) else None, "horizons": {}}
    for name, h in horizons.items():
        paths = FD.forward_paths(close, h)
        ret, mae = paths["ret"], paths["mae"]
        valid = ret.notna()
        base_up = float((ret[valid] > 0).mean()) if valid.any() else 0.5
        cell, cond = None, "all history"
        if cur is not None:
            m = (cs == cur) & valid
            if int(m.sum()) >= min_cell:
                cell, cond = m, str(cur)
        if cell is None and ri_now is not None:
            lo, hi = _risk_band(ri_now)
            m = ((ri >= lo) if lo == 0 else (ri > lo)) & (ri <= hi) & valid
            if int(m.sum()) >= min_cell:
                cell, cond = m, f"risk {lo}-{hi}"
        if cell is None:
            cell, cond = valid, "all history"
        r, mm = ret[cell], mae[cell]
        n = int(cell.sum())
        if n == 0:   # empty cell -> emit None (strict-JSON-safe; recommend() coerces via _f)
            out["horizons"][name] = {"h": h, "n": 0, "cond": cond, "p5": None, "p25": None,
                                     "p50": None, "p75": None, "p95": None, "p_up": None,
                                     "base_up": round(base_up, 3), "dd_avg": None, "dd_tail": None, "thin": True}
            continue
        out["horizons"][name] = {
            "h": h, "n": n, "cond": cond,
            "p5": round(float(r.quantile(0.05)), 1), "p25": round(float(r.quantile(0.25)), 1),
            "p50": round(float(r.quantile(0.50)), 1), "p75": round(float(r.quantile(0.75)), 1),
            "p95": round(float(r.quantile(0.95)), 1),
            "p_up": round(float((r > 0).mean()), 3), "base_up": round(base_up, 3),
            "dd_avg": round(float(mm.mean()), 1), "dd_tail": round(float(mm.quantile(0.05)), 1),
            "thin": n < 150,
        }
    return out


# --------------------------------------------------------------------------- #
# the recommendation engine
# --------------------------------------------------------------------------- #
def recommend(sig: pd.DataFrame, master: dict | None, cones: dict | None,
              fwd_risk7: dict | None, kelly: dict | None) -> dict:
    """One concrete, honest decision from the whole stack: action verb, target exposure
    band, conviction + its BASIS, rationale, price levels (accumulate zone / invalidation
    / 90d upside & downside from the cone), and the key risk. Directional conviction only
    at measured extremes; otherwise drawdown-managed sizing of a long-only BTC sleeve."""
    if sig is None or sig.empty:
        return {"ok": False}
    last = sig.iloc[-1]
    price = _f(last.get("close")) or 0.0
    score = int((master or {}).get("score", 0) or 0)

    # --- the MEASURED directional extremes (the only place direction is CALIBRATED) ---
    # STRONG legs are the ones calibration.json grades [BOTTOM]/[TOP] (real forward edge);
    # SOFT legs (valuation_state band, nupl-driven capitulation/euphoria) are [weak] context
    # → they steer the action verb but NOT a HIGH/directional claim.
    val_state = last.get("valuation_state")
    extreme = last.get("market_extreme")
    rr = _f(last.get("reserve_risk"))
    mvrv = _f(last.get("mvrv_z"))
    mayer = _f(last.get("mayer"))
    strong_value = (mvrv is not None and mvrv < 0)                       # MVRV-Z<0: +40%/90d, 72% hit [BOTTOM]
    strong_top = (rr is not None and rr > 0.02) or (mayer is not None and mayer > 2.4)  # [TOP]
    soft_value = (val_state == "undervalued") or (extreme == "capitulation")
    soft_top = (val_state == "overvalued") or (extreme == "euphoria")
    risk_hi = last.get("risk_regime") == "high_risk"
    mom_bull = last.get("momentum_state") == "bull"
    mom_bear = last.get("momentum_state") == "bear"

    # exposure anchor = the validated Kelly size (else the optimal grid), then widen to a band.
    # Override-Registry (W0): anchor on alloc_optimal_raw when present — the rec-card
    # band math should reflect what the engine actually wants, not the override-suppressed
    # final value (the display blackout is already handled upstream; the band should not
    # compound the suppression by anchoring at 0 during the gate window).
    kpct = None
    if kelly and kelly.get("size_pct") is not None:
        kpct = int(kelly["size_pct"])
    if kpct is None:
        raw_anchor = _f(last.get("alloc_optimal_raw"))  # prefer pure-engine series (W0)
        fallback = _f(last.get("alloc_optimal"))
        kpct = int(round(100 * (raw_anchor if raw_anchor is not None else (fallback or 0.0))))

    def band(c, w):
        return max(0, min(100, c - w)), max(0, min(100, c + w))

    # --- decision tree: MEASURED extremes (HIGH/directional) first, then drawdown-
    # managed sizing (MODERATE/LOW, never a directional claim — direction is a coin-flip) -
    if strong_value and not strong_top:
        action, action_zh = "ACCUMULATE", "逢低累积"
        conv, basis_en, basis_zh = "HIGH", "price at a measured deep-value extreme", "价格处于实测深度低估极值"
        lo, hi = max(kpct, 55), 100
        tone = "bull"
    elif strong_top:
        action, action_zh = "DISTRIBUTE · DE-RISK", "派发 · 降险"
        conv, basis_en, basis_zh = "HIGH", "measured cycle-top extreme", "实测周期顶部极值"
        lo, hi = 0, min(kpct, 35)
        tone = "bear"
    elif soft_top:
        action, action_zh = "TRIM · TAKE PROFIT", "减仓 · 止盈"
        conv, basis_en, basis_zh = "MODERATE", "rich valuation — manage exposure", "估值偏高 — 管理敞口"
        lo, hi = band(max(0, kpct - 15), 10)
        tone = "bear"
    elif soft_value and not risk_hi:
        action, action_zh = "ACCUMULATE (start)", "逢低累积（试探）"
        conv, basis_en, basis_zh = "MODERATE", "cheap valuation, calm market", "估值便宜、市场平静"
        lo, hi = band(max(kpct, 45), 12)
        tone = "bull"
    elif risk_hi or score <= -35:
        action, action_zh = "REDUCE · HEDGE", "减仓 · 对冲"
        conv, basis_en, basis_zh = "MODERATE", "dip risk ahead reads elevated", "未来回撤风险偏高"
        lo, hi = band(max(0, kpct - 15), 12)
        tone = "bear"
    elif mom_bull and not risk_hi and score >= 12:
        action, action_zh = "HOLD CORE · ADD ON DIPS", "持有核心 · 逢回调加仓"
        conv, basis_en, basis_zh = "MODERATE", "uptrend intact, dip risk low", "上升趋势完好、回撤风险低"
        lo, hi = band(min(100, kpct + 8), 12)
        tone = "bull"
    elif mom_bear:
        action, action_zh = "STAY DEFENSIVE", "保持防守"
        conv, basis_en, basis_zh = "MODERATE", "trend broken — cut exposure", "趋势走坏 — 降低敞口"
        lo, hi = band(max(0, kpct - 10), 10)
        tone = "bear"
    else:
        action, action_zh = "HOLD CORE", "持有核心"
        conv, basis_en, basis_zh = "LOW", "direction is a coin flip — size by risk", "方向接近抛硬币 — 按风险定仓"
        lo, hi = band(kpct, 10)
        tone = "neutral"

    # --- price levels: accumulate zone / invalidation / cone-implied 90d range -
    sth = _f(last.get("sth_cost_basis"))
    c90 = ((cones or {}).get("horizons", {}) or {}).get("90d", {})
    c30 = ((cones or {}).get("horizons", {}) or {}).get("30d", {})
    # NaN/None-safe cone reads: the key may EXIST with a None/NaN value (empty/thin cell),
    # so `.get(k, default)` won't help — coerce via _f() which maps NaN/None -> None.
    p90_75, p90_25, p90_5 = _f(c90.get("p75")), _f(c90.get("p25")), _f(c90.get("p5"))
    p30_25 = _f(c30.get("p25"))
    upside_90 = round(price * (1 + (p90_75 or 0) / 100.0)) if price else None
    downside_90 = round(price * (1 + (p90_25 or 0) / 100.0)) if price else None
    dip30 = round(price * (1 + (p30_25 or 0) / 100.0)) if price else None
    # accumulate zone: from a 30d-cone dip up toward current price (and toward STH basis)
    acc_lo = round(min([x for x in [dip30, sth] if x]) ) if (dip30 or sth) else None
    acc_hi = round(price) if price else None
    # invalidation: thesis-breaking level. A distribution/top thesis is "wrong above" the
    # 90d upside; a defensive (bear, non-top) stance flips constructive on a RECLAIM; a
    # bullish/neutral thesis breaks BELOW.
    is_top = strong_top or soft_top
    if is_top:
        invalid = upside_90
        invalid_label_en, invalid_label_zh = "thesis wrong above", "突破则判断失效"
    elif tone == "bear":
        # defensive stance: the level that would flip us back constructive (reclaim)
        invalid = (round(sth) if (sth and price and price < sth) else upside_90)
        invalid_label_en, invalid_label_zh = "reclaim to re-risk", "收复则重新加仓"
    else:
        # bullish/neutral: invalidation is a level BELOW current price. Use STH cost basis
        # only when price is at/above it (else it isn't a 'breaks below' level); otherwise
        # fall back to the cone-implied p5 downside.
        invalid = (round(sth) if (sth and price and price >= sth)
                   else (round(price * (1 + (p90_5 if p90_5 is not None else -25) / 100.0)) if price else None))
        invalid_label_en, invalid_label_zh = "thesis breaks below", "跌破则判断失效"

    # --- rationale: lead with the drivers that BACK the decision, then the opposing
    # pull (so a REDUCE shows the cautionary drivers first, an ACCUMULATE the supportive)
    pos = (master or {}).get("drivers_pos", [])
    neg = (master or {}).get("drivers_neg", [])
    primary, secondary = (neg, pos) if tone == "bear" else (pos, neg)
    rationale = []
    for d in primary[:2] + secondary[:2]:
        rationale.append({"label_en": d.get("label_en"), "label_zh": d.get("label_zh"),
                          "state_en": d.get("state_en"), "state_zh": d.get("state_zh"),
                          "tone": d.get("tone", "neutral")})

    # --- key risk: dominant cautionary driver + the next-7d forward-drawdown tail
    R7 = fwd_risk7 or {}
    key_risk_en = key_risk_zh = None
    neg = (master or {}).get("drivers_neg", [])
    dd_avg = R7.get("avg")
    dd_tail = R7.get("tail")
    if dd_tail is not None:
        # glance-tier plain name for the lead driver (falls back to its board label)
        lead, lead_zh = plain_name(neg[0]) if neg else ("volatility", "波动")
        lead = lead[0].upper() + lead[1:]
        key_risk_en = f"{lead}; worst-case dip over the next 7 days ~{dd_tail}% (typical {dd_avg}%)."
        key_risk_zh = f"{lead_zh}；未来 7 天最坏情况回撤约 {dd_tail}%（常见 {dd_avg}%）。"

    return {
        "ok": True, "action": action, "action_zh": action_zh, "tone": tone,
        "conviction": conv, "basis_en": basis_en, "basis_zh": basis_zh,
        "exposure_lo": int(lo), "exposure_hi": int(hi), "kelly_pct": kpct,
        "directional": conv == "HIGH",  # only the measured extremes are a directional call
        "levels": {
            "price": round(price) if price else None,
            "accumulate_lo": acc_lo, "accumulate_hi": acc_hi,
            "invalidation": invalid, "invalid_label_en": invalid_label_en, "invalid_label_zh": invalid_label_zh,
            "upside_90": upside_90, "downside_90": downside_90,
            "sth_basis": round(sth) if sth else None,
        },
        "rationale": rationale,
        "key_risk_en": key_risk_en, "key_risk_zh": key_risk_zh,
        "horizon_en": "weeks–months (strategic)", "horizon_zh": "数周至数月（战略）",
    }
