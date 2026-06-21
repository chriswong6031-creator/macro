"""engine/options_desk.py — the DELIVERABLE-READ layer over the options engines.

Two jobs, both pure synthesis (no new data, no new alpha claim):

  1. regime_game_plan(snap)  — turn the VALIDATED index vol-regime (engine/vol_regime
     snapshot) into a plain-English "market weather + game plan" the Options Desk hero
     renders: one verdict, one sub-line, a few bullets (sizing / hedging / what-to-watch),
     bilingual. This is the answer to "gex.html doesn't give me a deliverable signal" —
     the index-level read here IS validated (term-structure + MOVE forward-vol gate) and
     carries an honest "regime read, not an intraday timer; subtract-only" frame.

  2. name_signal(model, ...)  — fold ONE underlying's rich gex_model payload (gamma
     regime, vol-hole, walls, expected move, IV term, smile) PLUS two newly-computed
     per-name reads — VRP (IV30 vs the name's own realized vol) and a put-skew proxy —
     into a single synthesized "what this is telling you" verdict + reasons. DISPLAY /
     CONTEXT only and explicitly single-name-fragile (the dealer-sign assumption is weak
     for single names; these accrue toward a future validation but are NOT scored today).

Nothing here moves money on its own. The index regime can drive a subtract-only sizing /
risk nudge (validated); the single-name reads are context for the desk and the stock
view's ENTRY-timing color, never selection rank. See engine/vol_regime.py (the gate),
engine/gex_model.py (the per-name model), LIMITATIONS.md.
"""
from __future__ import annotations

import numpy as np


def _bi(en: str, zh: str) -> dict:
    return {"en": en, "zh": zh}


# --------------------------------------------------------------------------- #
# 1) index vol-regime -> market-weather game plan
# --------------------------------------------------------------------------- #
def regime_game_plan(snap: dict) -> dict:
    """Plain-English deliverable read from a vol_regime.snapshot() dict. Returns
    {verdict, icon, css, sub, bullets[], gross, scored} — bilingual strings."""
    if not snap or not snap.get("available"):
        return {"available": False}
    regime = snap.get("regime")
    rs = snap.get("risk_score")
    vt = snap.get("vol_target_scalar")
    ins = snap.get("insurance_cost")
    vrp_state = snap.get("vrp_state")
    vvix_state = snap.get("vvix_state")
    flags = snap.get("flags") or []
    ts_state = snap.get("ts_slope_state")

    # verdict + tone keyed off the validated regime label
    MAP = {
        "calm-contango": ("Risk-on backdrop", "顺风 · 偏多",
                          "gp-calm", "🟢",
                          "Vol is cheap and the term structure is in calm contango — the "
                          "surface is NOT forecasting stress. Constructive for holding / "
                          "adding equity risk; trend-following works in calm regimes.",
                          "波动率便宜、期限结构处于平静的Contango — 波动率曲面未预示压力。"
                          "适合持有/增配风险；平静体制下趋势策略有效。"),
        "normalizing": ("Mixed — normalizing", "中性 · 修复中",
                        "gp-neutral", "🟡",
                        "The vol surface is neither cheap-calm nor stressed. No regime "
                        "edge either way — size to plan and let the levels below guide "
                        "tactical entries.",
                        "波动率曲面既不便宜平静、也未承压。两边都无体制优势 — 按计划"
                        "定仓，用下方价位指导战术性入场。"),
        "warning": ("Caution — fragility building", "警惕 · 脆弱性上升",
                    "gp-warn", "🟠",
                    "The term structure is flattening and/or bond-vol (MOVE) is rich and/or "
                    "the vol-risk-premium is collapsing — the surface is starting to price "
                    "stress. Trim gross, respect stops, don't chase strength.",
                    "期限结构走平、和/或债券波动率(MOVE)偏高、和/或波动风险溢价正在收缩 — "
                    "曲面开始计入压力。降低总仓、尊重止损、不要追高。"),
        "backwardation-stress": ("Risk-off — stress regime", "避险 · 压力体制",
                                 "gp-jumpy", "🔴",
                                 "The term structure is in BACKWARDATION — near-dated vol is "
                                 "bid above longer-dated, the classic stress tell. De-risk / "
                                 "cut gross / favor hedges. Bounces in this regime are sharp "
                                 "and unreliable — mean-reversion is a trap until the curve "
                                 "re-contangos.",
                                 "期限结构呈现Backwardation — 近月波动率高于远月，典型的压力"
                                 "信号。降险/减总仓/偏好对冲。此体制下的反弹尖锐且不可靠 — "
                                 "在曲线重回Contango前，抄底是陷阱。"),
    }
    title_en, title_zh, css, icon, sub_en, sub_zh = MAP.get(
        regime, ("Vol regime", "波动率体制", "gp-neutral", "🟡", "", ""))

    bullets = []
    # sizing bullet from the (mechanical) vol-target scalar
    if vt is not None:
        if vt >= 1.15:
            bullets.append(_bi(
                f"Sizing: vol sits BELOW the risk target — the vol-target scalar is {vt:.2f}× "
                "(room to run a fuller book within a fixed risk budget).",
                f"仓位：波动率低于风险目标 — 波动率目标系数为 {vt:.2f}×（在固定风险预算内可加大仓位）。"))
        elif vt <= 0.85:
            bullets.append(_bi(
                f"Sizing: vol sits ABOVE the risk target — the vol-target scalar is {vt:.2f}× "
                "(trim gross to hold risk constant; this is the drawdown lever, not a forecast).",
                f"仓位：波动率高于风险目标 — 波动率目标系数为 {vt:.2f}×（缩减总仓以保持风险恒定；"
                "这是回撤管理工具，而非预测）。"))
        else:
            bullets.append(_bi(
                f"Sizing: vol near the risk target — scalar {vt:.2f}× (normal gross).",
                f"仓位：波动率接近风险目标 — 系数 {vt:.2f}×（正常总仓）。"))
    # hedging bullet from insurance cost (SKEW percentile)
    if ins:
        if "cheap" in ins:
            bullets.append(_bi(
                "Hedging: downside protection is CHEAP (low SKEW percentile) — if you want "
                "tail insurance, convexity is on sale here.",
                "对冲：下行保护便宜（SKEW百分位低）— 若需尾部保险，此处凸性折价。"))
        elif "expensive" in ins:
            bullets.append(_bi(
                "Hedging: downside protection is EXPENSIVE (high SKEW percentile) — fear is "
                "already priced; new hedges are dear and a mild contrarian tell.",
                "对冲：下行保护昂贵（SKEW百分位高）— 恐惧已被定价；新对冲成本高，且为温和"
                "的反向提示。"))
    # premium bullet from VRP state
    if vrp_state and "rich" in vrp_state:
        bullets.append(_bi(
            "Premium: implied vol is rich vs a forward realized-vol forecast — historically "
            "a constructive backdrop for equities at the 1–3 month horizon (context).",
            "溢价：相对前瞻已实现波动率预测，隐含波动率偏贵 — 历史上对1–3个月股票是建设性"
            "背景（参考）。"))
    elif vrp_state and ("thin" in vrp_state or "collaps" in vrp_state):
        bullets.append(_bi(
            "Premium: the vol-risk-premium is thin/collapsing — realized vol is catching up "
            "to implied, a de-risk tell.",
            "溢价：波动风险溢价偏薄/正在收缩 — 已实现波动率正在追上隐含，提示降险。"))
    # vol-of-vol (VVIX) peak-fear vs complacency read (context — candidate, not yet scored)
    if vvix_state and "complacent" in vvix_state:
        bullets.append(_bi(
            "Vol-of-vol: VVIX is CHEAP relative to VIX (complacency) — historically this has "
            "preceded RISING realized vol. A quiet-fragility tell (context, candidate).",
            "波动率的波动率：VVIX 相对 VIX 偏便宜（自满）— 历史上往往先行于已实现波动率上升。"
            "属于平静下的脆弱性提示（参考，候选信号）。"))
    elif vvix_state and ("peak-fear" in vvix_state or "fear-priced" in vvix_state):
        bullets.append(_bi(
            "Vol-of-vol: VVIX is RICH/extreme vs VIX — fear is already priced into vol-of-vol; "
            "historically this mean-reverts (contrarian-constructive context, candidate).",
            "波动率的波动率：VVIX 相对 VIX 偏贵/极端 — 恐慌已被计入波动率之波动率；历史上倾向"
            "均值回归（反向建设性参考，候选信号）。"))
    # confluence flags
    if len(flags) >= 2:
        bullets.append(_bi(
            f"Fragility confluence: {len(flags)} stress tells firing ({', '.join(flags)}).",
            f"脆弱性共振：{len(flags)} 个压力信号触发（{', '.join(flags)}）。"))

    return {
        "available": True,
        "verdict": _bi(title_en, title_zh),
        "icon": icon, "css": css,
        "sub": _bi(sub_en, sub_zh),
        "bullets": bullets,
        "risk_score": rs,
        "regime": regime,
        "ts_state": ts_state,
        "gross_scalar": vt,
        "scored": snap.get("scored_active", False),
        "asof": snap.get("asof"),
    }


# --------------------------------------------------------------------------- #
# 2) per-name options model -> synthesized deliverable read
# --------------------------------------------------------------------------- #
def _nearest_iv(strikes, ivs, target):
    """IV at the strike nearest `target` from a smile leg (strikes, ivs parallel lists;
    ivs may contain None). Returns (iv, strike) or (None, None)."""
    best, bk, bd = None, None, None
    for k, v in zip(strikes or [], ivs or []):
        if k is None or v is None:
            continue
        d = abs(k - target)
        if bd is None or d < bd:
            best, bk, bd = v, k, d
    return best, bk


def put_skew_proxy(smile: dict, spot: float) -> dict | None:
    """A robust, delta-free skew proxy from the front-expiry smile: OTM put IV (~0.9·spot)
    minus OTM call IV (~1.1·spot). Positive = downside fear bid (the normal equity skew);
    a steepening vs flat read is the tell. Display-only (single-name skew is contested)."""
    if not smile or not spot or spot <= 0:
        return None
    ks = smile.get("strikes") or []
    piv = smile.get("put_iv") or []
    civ = smile.get("call_iv") or []
    put_otm, kp = _nearest_iv(ks, piv, spot * 0.90)
    call_otm, kc = _nearest_iv(ks, civ, spot * 1.10)
    if put_otm is None or call_otm is None:
        return None
    return {"skew_pts": round(float(put_otm - call_otm), 2),
            "put_iv": round(float(put_otm), 1), "call_iv": round(float(call_otm), 1),
            "put_k": kp, "call_k": kc, "expiry": smile.get("expiry")}


def iv_term_slope(term: list) -> dict | None:
    """Front vs back ATM-IV slope from the term structure. Positive = contango (back IV >
    front), the calm shape; negative = inverted (event/stress risk bid into the front)."""
    rows = [r for r in (term or []) if r.get("atm_iv")]
    if len(rows) < 2:
        return None
    rows = sorted(rows, key=lambda r: r.get("days", 0))
    front, back = rows[0], rows[-1]
    slope = float(back["atm_iv"]) - float(front["atm_iv"])
    return {"slope_pts": round(slope, 2), "front_iv": round(float(front["atm_iv"]), 1),
            "back_iv": round(float(back["atm_iv"]), 1),
            "front_days": front.get("days"), "back_days": back.get("days"),
            "shape": "inverted" if slope < -0.5 else "contango" if slope > 0.5 else "flat"}


def name_vrp(iv30: float | None, realized_vol_ann: float | None) -> dict | None:
    """Per-name vol-risk-premium: IV30 minus the name's own trailing realized vol (annual
    %). Rich (positive) = options expensive vs how the stock has actually moved; cheap
    (negative) = options underpricing realized motion. Context, never scored single-name."""
    if iv30 is None or realized_vol_ann is None or realized_vol_ann <= 0:
        return None
    vrp = float(iv30) - float(realized_vol_ann)
    ratio = float(iv30) / float(realized_vol_ann)
    return {"vrp_pts": round(vrp, 1), "iv30": round(float(iv30), 1),
            "realized": round(float(realized_vol_ann), 1), "ratio": round(ratio, 2),
            "state": ("rich" if ratio >= 1.25 else "cheap" if ratio <= 0.95 else "fair")}


def name_signal(model: dict, realized_vol_ann: float | None = None) -> dict:
    """Synthesize ONE underlying's options model into a deliverable read. Adds the
    new per-name computed fields (vrp, skew, term slope) and a plain-English verdict
    that fuses the gamma regime, the vol-hole state, the premium and the skew — with the
    honest single-name caveat baked in."""
    s = model.get("summary") or {}
    em = model.get("expected_move") or {}
    vh = model.get("vol_hole") or {}
    spot = s.get("spot")
    iv30 = s.get("iv30")

    skew = put_skew_proxy(model.get("smile") or {}, spot)
    slope = iv_term_slope(model.get("term") or [])
    vrp = name_vrp(iv30, realized_vol_ann)
    regime = s.get("regime")           # "long" / "short" dealer gamma
    vh_state = vh.get("state")

    reasons = []
    # regime / vol-hole read
    if regime == "short":
        reasons.append(_bi(
            "Dealers are net SHORT gamma here — hedging chases moves, so realized vol tends "
            "to expand and trends/air-pockets run bigger (jumpy).",
            "做市商在此为净空头Gamma — 对冲追逐走势，已实现波动倾向放大、趋势/急跌更大（跳动）。"))
    elif regime == "long":
        reasons.append(_bi(
            "Dealers are net LONG gamma — hedging fades moves, so price tends to pin / "
            "mean-revert between the walls (calmer).",
            "做市商为净多头Gamma — 对冲抑制走势，价格倾向在墙之间磁吸/均值回归（更平静）。"))
    if slope and slope["shape"] == "inverted":
        reasons.append(_bi(
            f"IV term structure is INVERTED ({slope['front_iv']}→{slope['back_iv']}) — the "
            "front is bid, i.e. a near-term event/stress is priced.",
            f"IV期限结构倒挂（{slope['front_iv']}→{slope['back_iv']}）— 近月被买入，"
            "即计入近期事件/压力。"))
    if vrp:
        if vrp["state"] == "rich":
            reasons.append(_bi(
                f"Options look RICH — IV30 {vrp['iv30']} vs realized {vrp['realized']} "
                f"({vrp['ratio']}×): premium-selling is favored, buying is dear.",
                f"期权偏贵 — IV30 {vrp['iv30']} 对已实现 {vrp['realized']}（{vrp['ratio']}×）："
                "适合卖方，买方成本高。"))
        elif vrp["state"] == "cheap":
            reasons.append(_bi(
                f"Options look CHEAP — IV30 {vrp['iv30']} vs realized {vrp['realized']} "
                f"({vrp['ratio']}×): convexity/long-vol is relatively well-priced.",
                f"期权偏便宜 — IV30 {vrp['iv30']} 对已实现 {vrp['realized']}（{vrp['ratio']}×）："
                "凸性/做多波动相对划算。"))
    if skew and skew["skew_pts"] is not None:
        if skew["skew_pts"] >= 6:
            reasons.append(_bi(
                f"Heavy put skew ({skew['skew_pts']:+.1f} pts) — downside protection is bid; "
                "the market is paying up for crash insurance on this name.",
                f"明显看跌偏斜（{skew['skew_pts']:+.1f} 点）— 下行保护被买入；市场为该标的的"
                "崩盘保险付高价。"))

    # one-line verdict (context, not a buy/sell)
    if regime == "short" and (vh_state == "EXPANSION"):
        verdict = _bi("Jumpy / expansion risk", "跳动 · 扩张风险")
        tone = "neg"
    elif regime == "long" and vh_state in ("IN_HOLE", "COILED_UP", "COILED_DOWN"):
        verdict = _bi("Pinned / range-bound", "磁吸 · 区间")
        tone = "pos"
    elif slope and slope["shape"] == "inverted":
        verdict = _bi("Event risk priced", "计入事件风险")
        tone = "warn"
    else:
        verdict = _bi("Neutral vol context", "中性波动背景")
        tone = "neutral"

    return {
        "verdict": verdict, "tone": tone, "reasons": reasons,
        "vrp": vrp, "skew": skew, "term_slope": slope,
        "caveat": _bi(
            "Single-name dealer positioning is an assumption and can be wrong (covered-call "
            "ETFs / heavy retail flow flip the sign). Context for timing, never a buy/sell.",
            "个股做市商持仓为假设、可能出错（备兑ETF/散户大量流动会翻转符号）。仅作择时背景，"
            "绝非买卖信号。"),
    }
