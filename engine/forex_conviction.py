"""Forex CONVICTION engine — a multi-factor, weighted, RISK-CONTEXT verdict.

Same machinery as engine.commodity_conviction (signed MEASURED weights, a
[-100,+100] score, factor-agreement confidence, cycle position) but:

  * FX framing: the headline is a RISK-CONTEXT / regime read; the directional
    LONG-base / SHORT-base label is SECONDARY. FX fails UIP and carry has fat
    left-tail crash risk, so a confident "STRONG LONG" would be dishonest.
  * No `dollar` per-pair factor: the shared dollar move is handled architecturally
    (signals run on the dollar-orthogonalized residual) and shown in the master
    tile — keeping it a per-pair factor too would double-count it.
  * Dollar-day haircut: on a day dominated by a broad-dollar move, per-pair
    residual signals are small relative to the dollar — confidence is shrunk so the
    board can't print false 8-pair consensus.
  * Peg / intervention override: managed (USD/CNH) -> FLAT; an MoF intervention
    watch zone (USD/JPY) caps conviction; SNB history is flagged.

Reuses commodity_conviction.{cycle_position, _action, ACTIONS, _reading} verbatim.
Weights come from data/forex/conviction_calibration.json once calibrated (Phase 2);
until then a documented prior is used and confidence is dampened.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config
from engine.commodity_conviction import cycle_position, _action, _reading

log = logging.getLogger(__name__)

CALIB_PATH = "forex/conviction_calibration.json"

FX_FACTOR_LABELS = {
    "trend": ("Trend (idiosyncratic)", "趋势（特异）"),
    "structure": ("Price structure", "价格结构"),
    "carry": ("Carry (rate diff)", "套息（利差）"),
    "riskoff": ("Risk appetite", "风险偏好"),
    "positioning": ("Positioning (COT)", "持仓（COT）"),
    "risk": ("Risk index", "风险指数"),
    "shock": ("Residual shock", "残差冲击"),
}
FX_FACTOR_GROUP = {
    "trend": "Trend & Structure", "structure": "Trend & Structure",
    "carry": "Carry & Rates",
    "riskoff": "Risk & Positioning", "positioning": "Risk & Positioning",
    "risk": "Risk & Positioning",
    "shock": "Shocks",
}
# Phase-1 prior (un-calibrated). trend = workhorse + carry-crash filter; carry high
# but vol-penalized + crash-gated; riskoff is the regime conditioner; havens get the
# right sign via the per-pair beta folded into the riskoff factor itself.
FX_PRIOR = {"trend": 0.22, "structure": 0.10, "carry": 0.20, "riskoff": 0.18,
            "positioning": 0.10, "risk": 0.12, "shock": 0.08}

# action label -> FX LONG/SHORT/FLAT (base currency), css reused from the commodity theme
_FX_ACTION = {
    "STRONG BUY": ("STRONG LONG", "强烈做多", "sbuy"),
    "BUY": ("LONG", "做多", "buy"),
    "HOLD": ("FLAT", "观望", "hold"),
    "SELL": ("SHORT", "做空", "sell"),
    "STRONG SELL": ("STRONG SHORT", "强烈做空", "ssell"),
}

FRAMING = ("Risk-context / regime read — not a trade call. FX fails UIP and carry "
           "carries fat-tailed crash risk; treat as context, not alpha.",
           "风险背景/格局解读 — 非交易建议。外汇不满足UIP，套息具肥尾崩盘风险；仅作背景，非超额收益。")


def load_calibration() -> dict:
    p = config.data_dir() / "forex" / "conviction_calibration.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("forex conviction calibration unreadable (%s)", e)
    return {}


def asset_weights(pair: str, meta: dict, calib: dict) -> dict:
    w = (calib.get("assets", {}).get(pair, {}) or {}).get("weights")
    w = dict(w) if w else dict(FX_PRIOR)
    if meta.get("carry") == "context":      # EM with no clean free front-end rate
        w.pop("carry", None)
    return w


def factor_panel(pair: str, sig: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Naive-bullish [-1,1] FX factor time series (+ = bullish the BASE currency)."""
    idx = sig.index
    f = pd.DataFrame(index=idx)
    if "ts_momentum" in sig:
        f["trend"] = sig["ts_momentum"].clip(-1, 1)
    if "structure" in sig:
        f["structure"] = sig["structure"].clip(-1, 1)
    if "risk_index" in sig:
        f["risk"] = ((50.0 - sig["risk_index"]) / 50.0).clip(-1, 1)
    if "carry_score" in sig and meta.get("carry") != "context":
        f["carry"] = sig["carry_score"].clip(-1, 1)
    if "riskoff" in sig:
        f["riskoff"] = sig["riskoff"].clip(-1, 1)
    if "pos_pctile" in sig:                 # crowded long = contrarian bearish
        f["positioning"] = (-(sig["pos_pctile"] - 50.0) / 50.0).clip(-1, 1)
    if "shock_z" in sig:
        f["shock"] = np.tanh(sig["shock_z"] / 2.0)
    return f


def _peg_state(meta: dict, quote_level: float | None) -> dict | None:
    peg = meta.get("peg")
    if not peg:
        return None
    kind = peg.get("kind")
    if kind == "managed":
        return {"kind": "managed", "force_flat": True, "cap": 20,
                "note": ("Managed regime — the official fix sets the level; read as risk-context only.",
                         "受管理汇率 — 由中间价决定水平；仅作风险背景解读。")}
    if kind == "intervention" and quote_level is not None and peg.get("watch"):
        lo, hi = peg["watch"]
        if lo <= quote_level <= hi:
            return {"kind": "intervention", "cap": 40,
                    "note": (f"In the MoF intervention watch zone (~{lo:g}–{hi:g}); conviction capped.",
                             f"处于财务省干预观察区（约{lo:g}–{hi:g}）；信心受限。")}
    if kind == "snb":
        return {"kind": "snb",
                "note": ("SNB has historically capped CHF (2015 floor gapped ~20%).",
                         "瑞士央行历史上设过下限（2015年跳空约20%）。")}
    return None


def conviction(pair: str, sig: pd.DataFrame, meta: dict, calib: dict | None = None,
               dollar_day: float = 0.0, dollar_cfg: dict | None = None) -> dict:
    """Full FX risk-context verdict for one pair. {} on failure (never breaks build)."""
    try:
        if sig is None or sig.empty:
            return {}
        calib = calib if calib is not None else load_calibration()
        acal = calib.get("assets", {}).get(pair, {}) or {}
        reliable = acal.get("score_reliable", False)          # no calibration yet in Phase 1
        weights = asset_weights(pair, meta, calib)
        base = meta.get("base", pair)

        panel = factor_panel(pair, sig, meta)
        last = panel.iloc[-1] if len(panel) else pd.Series(dtype=float)
        factors = {k: float(last.get(k)) for k in panel.columns if pd.notna(last.get(k))}

        rows, num, den = [], 0.0, 0.0
        for k, v in factors.items():
            w = float(weights.get(k, 0.0))
            if w == 0.0:
                continue
            contrib = w * v
            num += contrib
            den += abs(w)
            r_en, r_zh = _reading(k, v)
            lab = FX_FACTOR_LABELS.get(k, (k, k))
            rows.append({"key": k, "label": lab[0], "label_zh": lab[1],
                         "group": FX_FACTOR_GROUP.get(k, "Other"),
                         "value": round(v, 3), "weight": round(w, 3),
                         "contribution": round(contrib, 4),
                         "reading": r_en, "reading_zh": r_zh})
        if den == 0:
            return {}
        score = float(np.clip(100.0 * num / den, -100, 100))
        rows.sort(key=lambda r: -abs(r["contribution"]))

        # peg / intervention override
        last_close = float(sig["close"].iloc[-1])
        quote_level = (1.0 / last_close) if (meta.get("invert") and last_close) else last_close
        peg = _peg_state(meta, quote_level)
        if peg:
            cap = peg.get("cap")
            if peg.get("force_flat"):
                score = float(np.clip(score, -15, 15))
            elif cap is not None:
                score = float(np.clip(score, -cap, cap))

        action_en, action_zh, css = _action(score, acal.get("thresholds"))
        fx_en, fx_zh, fx_css = _FX_ACTION.get(action_en, (action_en, action_zh, css))
        stance = "bullish" if score >= 20 else ("bearish" if score <= -20 else "neutral")

        # confidence = agreement x completeness, then dampened (no calib) + dollar-day haircut
        agree = abs(num) / sum(abs(r["contribution"]) for r in rows) if rows else 0.0
        completeness = den / sum(abs(w) for w in weights.values() if w) if weights else 0.0
        confidence = float(np.clip(0.5 * agree + 0.5 * completeness, 0, 1))
        if not reliable:
            confidence *= 0.6                                 # honest: un-calibrated
        dcfg = dollar_cfg or config.load()["forex"]["dollar"]
        if dollar_day and dollar_day > dcfg.get("dollar_day_z", 1.0):
            confidence *= (1.0 - dcfg.get("dollar_day_haircut", 0.5))
        confidence = round(confidence, 2)

        groups: dict[str, dict] = {}
        for r in rows:
            g = groups.setdefault(r["group"], {"name": r["group"], "num": 0.0, "den": 0.0})
            g["num"] += r["contribution"]
            g["den"] += abs(r["weight"])
        group_list = [{"name": g["name"],
                       "score": round(100 * g["num"] / g["den"], 1) if g["den"] else 0.0,
                       "weight_pct": round(100 * g["den"] / den, 1)}
                      for g in groups.values()]
        group_list.sort(key=lambda g: -abs(g["score"] * g["weight_pct"]))

        cyc = cycle_position(sig["close"], pair, 0.10)        # FX legs are smaller than commodities
        head, head_zh, sub, sub_zh = _narrate(base, fx_en, score, rows, stance, peg)

        return {
            "score": round(score, 1), "action": fx_en, "action_zh": fx_zh, "action_css": fx_css,
            "stance": stance, "confidence": confidence, "reliable": bool(reliable),
            "factors": rows, "groups": group_list, "cycle": cyc,
            "headline": head, "headline_zh": head_zh, "sub": sub, "sub_zh": sub_zh,
            "framing": FRAMING[0], "framing_zh": FRAMING[1],
            "peg": peg, "base": base, "n_factors": len(rows),
        }
    except Exception as e:  # noqa: BLE001 — verdict overlay must never break the build
        log.warning("forex conviction failed for %s (%s)", pair, e)
        return {}


def _narrate(base: str, action: str, score: float, rows: list[dict],
             stance: str, peg: dict | None) -> tuple[str, str, str, str]:
    top_up = [r for r in rows if r["contribution"] > 0][:2]
    top_dn = [r for r in rows if r["contribution"] < 0][:2]
    lead = (top_up if stance != "bearish" else top_dn) or top_dn or top_up
    drivers_txt = ", ".join(r["label"].lower() for r in lead) or "no single dominant factor"
    drivers_zh = "、".join(r["label_zh"] for r in lead) or "无单一主导因素"
    bias = ("long" if score >= 20 else ("short" if score <= -20 else "neutral"))
    bias_zh = {"long": "偏多", "short": "偏空", "neutral": "中性"}[bias]
    head = f"Risk-context: net {bias} {base} ({score:+.0f})"
    head_zh = f"风险背景：{base} 净{bias_zh}（{score:+.0f}）"
    sub = f"Led by {drivers_txt}."
    sub_zh = f"主导因素：{drivers_zh}。"
    if peg and peg.get("note"):
        sub += " " + peg["note"][0]
        sub_zh += " " + peg["note"][1]
    return head, head_zh, sub, sub_zh
