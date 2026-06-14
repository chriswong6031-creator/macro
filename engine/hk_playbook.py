"""Hong Kong / Hang Seng playbook — turns the HK regime + live internals into conclusions.

The US engine/playbook.py is irreducibly US, and engine/china_playbook.py is calibrated on
the China A-share tape. This is the HK analog, grounded in the HK calibration
(scripts/calibrate_hk.py, reports/hk-calibration.md, measured on ^HSI, split-half checked):
  - HSI is the regional risk-on/off proxy, so the global RISK overlay is HK's headline edge
    (Risk-on +0.9%/21d, 57% hit > Risk-off > Neutral — and Neutral is the weakest bucket);
  - Goldilocks (Q1) is the BEST quad (+1.3%/21d, 64% 63d hit) and — unlike China — the quad
    ordering is split-half STABLE: Goldilocks is positive in BOTH halves, Stagflation (Q3)
    negative in BOTH halves; Reflation/Growth-scare are middling/context;
  - dual liquidity (PBoC + Fed-via-peg) carries a measured tilt: expanding beats contracting;
  - the HKD peg tells you which way funding is flowing (weak-side defence drains HSI liquidity);
  - no stable single-sector monthly outperformance signal exists (risk-filter only).

Produces a `pb` dict the template renders: quad meaning, lifespan progress vs the classifier's
own history, next-quad base rates, an exposure DIAL with reasons built from live internals
(global risk state, dual liquidity, HKD peg, southbound flow), the framework-preferred sectors
with live tape agreement, and confirmed leaders / avoids.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

QUAD_MEANING_HK = {
    "Q1": ("Goldilocks — growth firming while price pressure eases. The measured BEST backdrop "
           "for the Hang Seng (+1.3%/21d, ~64% hit over 3 months) and the only quad positive in "
           "BOTH sample halves — the friendliest tape for internet/tech, quality growth and consumer.",
           "理想增长 — 增长回暖、物价压力缓解。实测对恒指最佳的环境（+1.3%/21日，约 64% 的三月命中率），"
           "也是唯一在两个样本半区均为正的象限 — 对互联网／科技、优质成长与消费最友好。"),
    "Q2": ("Reflation — growth and prices both rising. Favors energy, materials, financials and "
           "property, but the measured edge is middling and context-dependent — a tilt, not a green light.",
           "再通胀 — 增长与物价同步上行。利好能源、材料、金融与地产，但实测优势中等且依赖背景 — "
           "是倾斜而非放行信号。"),
    "Q3": ("Stagflation — growth fading while prices stay hot. The measured WORST quad for the Hang "
           "Seng (−0.9%/21d, ~45% hit) and negative in BOTH sample halves — defensives, telecom/utilities, "
           "banks and upstream materials hold up best.",
           "滞胀 — 增长走弱而物价高企。实测对恒指最差的象限（−0.9%/21日，约 45% 命中率），且在两个样本"
           "半区均为负 — 防御板块、电信／公用、银行与上游材料相对抗跌。"),
    "Q4": ("Growth-scare — both growth and prices falling, fear rising. Middling/context for the Hang "
           "Seng — mildly positive on average but not a clean signal across halves; lean on the global "
           "risk overlay and the cycle ladder, not the quad alone.",
           "增长恐慌 — 增长与物价齐跌、恐慌上升。对恒指属中等／背景信号 — 平均温和为正，但在样本半区间"
           "并不干净；应依靠全球风险叠加与周期阶梯，而非仅凭象限。"),
}

_POSTURES = ["DEFENSIVE", "CAREFUL", "NEUTRAL", "CONSTRUCTIVE", "AGGRESSIVE"]


def _dial(latest: dict, internals: dict) -> dict:
    """Exposure posture + signed reasons, from quad base + live HK internals.

    HK reasons (NOT China's): the global RISK overlay is the headline edge, plus dual liquidity,
    the HKD peg funding tell, and southbound flow. Each reason is a (sign, en, zh) tuple with
    sign in {"+", "-", "i"}. posture index = clamp(2 + score, 0, 4)."""
    score, reasons = 0, []

    quad = latest.get("quad")
    if quad == "Q1":
        score += 1
        reasons.append(("+", "Goldilocks is the measured-best quad for the Hang Seng — positive in both "
                        "sample halves; the friendliest tape for quality growth.",
                        "理想增长是实测对恒指最佳的象限 — 在两个样本半区均为正；对优质成长最友好。"))
    elif quad == "Q3":
        score -= 1
        reasons.append(("-", "Stagflation is the measured-worst quad for the Hang Seng — negative in both "
                        "sample halves; favor defensives/telecom-utilities/banks and tighten risk.",
                        "滞胀是实测对恒指最差的象限 — 在两个样本半区均为负；偏好防御／电信公用／银行并收紧风险。"))
    elif quad == "Q2":
        reasons.append(("i", "Reflation carries only a middling, context-dependent edge — favor "
                        "cyclicals/energy/materials, but treat it as a tilt, not a green light.",
                        "再通胀仅有中等且依赖背景的优势 — 偏好周期／能源／材料，但视作倾斜而非放行信号。"))
    elif quad == "Q4":
        reasons.append(("i", "Growth-scare is middling/context for the Hang Seng — lean on the global "
                        "risk overlay and the cycle ladder rather than the quad alone.",
                        "增长恐慌对恒指属中等／背景信号 — 应依靠全球风险叠加与周期阶梯，而非仅凭象限。"))

    risk = latest.get("risk_state")
    if risk == "Risk-on":
        score += 1
        reasons.append(("+", "Global risk-ON — HK's headline measured edge: the Hang Seng averaged "
                        "+0.9%/month with ~57% positive in this state, its strongest risk bucket.",
                        "全球风险偏好（Risk-on）— 恒指的核心实测优势：此状态下平均月度 +0.9%、约 57% 为正，"
                        "是其最强的风险桶。"))
    elif risk == "Risk-off":
        score -= 1
        reasons.append(("-", "Global risk-OFF — the regional risk proxy is being sold; size down until "
                        "the global tape stabilizes.",
                        "全球避险（Risk-off）— 区域风险代理正被抛售；在全球盘面企稳前缩小仓位。"))
    elif risk == "Neutral":
        reasons.append(("i", "Global risk NEUTRAL — historically the weakest bucket for the Hang Seng "
                        "(near-flat, ~50% positive); no directional edge from the risk overlay here.",
                        "全球风险中性（Neutral）— 历史上对恒指最弱的桶（近乎持平、约 50% 为正）；"
                        "风险叠加在此处无方向性优势。"))

    liq = latest.get("liquidity_overlay")
    if liq == "expanding":
        score += 1
        reasons.append(("+", "Dual liquidity expanding (PBoC + Fed-via-peg) — measured to beat the "
                        "contracting state for the Hang Seng.",
                        "双重流动性扩张（央行 + 通过联系汇率传导的美联储）— 实测优于收缩状态。"))
    elif liq == "contracting":
        score -= 1
        reasons.append(("-", "Dual liquidity contracting — a measured headwind for the Hang Seng; be choosier.",
                        "双重流动性收缩 — 对恒指构成实测逆风；需更挑剔。"))

    peg = (latest.get("peg_state") or "")
    if "weak" in peg.lower():
        score -= 1
        reasons.append(("-", "HKD on the weak side — the HKMA is defending the 7.85 convertibility floor, "
                        "draining HKD liquidity (a funding headwind for the Hang Seng).",
                        "港元处于弱方 — 金管局正捍卫 7.85 兑换保证下限，抽走港元流动性（对恒指构成资金逆风）。"))
    elif "strong" in peg.lower():
        score += 1
        reasons.append(("+", "HKD on the strong side — inflows pushing the peg, easing HKD funding "
                        "(a liquidity tailwind for the Hang Seng).",
                        "港元处于强方 — 资金流入推升联系汇率、宽松港元资金（对恒指构成流动性顺风）。"))

    sb = (internals or {}).get("southbound")
    if sb and sb.get("net_z") is not None:
        if sb["net_z"] >= 1.0:
            score += 1
            reasons.append(("+", "Southbound buying strong — mainland money leaning risk-on into HK.",
                            "南向资金大幅净买入 — 内地资金偏向风险偏好、流入香港。"))
        elif sb["net_z"] <= -1.0:
            score -= 1
            reasons.append(("-", "Southbound selling — mainland money leaning risk-off, pulling back from HK.",
                            "南向资金净卖出 — 内地资金偏向避险、从香港回撤。"))

    idx = max(0, min(4, 2 + score))
    return {"posture": _POSTURES[idx], "score": score, "reasons": reasons}


def build(latest: dict, hist: pd.DataFrame | None, sectors: list[dict], internals: dict) -> dict:
    from engine.playbook import QUAD_SHORT, QUAD_SHORT_ZH, quad_segments, transition_stats
    pb: dict = {}
    quad = latest.get("quad")
    qm = QUAD_MEANING_HK.get(quad)
    if qm:
        pb["quad_meaning"] = {"en": qm[0], "zh": qm[1]}

    if hist is not None and "quad" in hist.columns:
        try:
            ts = transition_stats(hist["quad"])
            seg = quad_segments(hist["quad"])
            cur = ts.get("current", {})
            age, med = cur.get("age_days"), cur.get("median_days")
            if age and med:
                durs = seg.loc[seg["quad"] == quad, "days"].iloc[:-1]   # past same-quad segments
                longer = durs[durs >= age]
                bar = max(2, min(98, round(age / (2 * med) * 100)))
                phase = "young" if bar < 25 else ("old" if bar > 60 else "mid")
                pnote = {"young": ("a young regime — let confirmed trends run",
                                   "周期尚年轻 — 让已确认的趋势继续奔跑"),
                         "mid": ("mid-life — normal conditions, trust the label",
                                 "处于中年 — 环境正常，信任标签"),
                         "old": ("an old regime — every warning deserves more weight",
                                 "周期已年老 — 每一面预警都更值得加重")}[phase]
                pb["progress"] = {
                    "age_days": age, "median_days": med, "n_history": ts["n_by_quad"].get(quad, 0),
                    "pct_longer": round(100 * len(longer) / len(durs)) if len(durs) else None,
                    "median_remaining_days": int((longer - age).median()) if len(longer) else None,
                    "bar_pct": bar, "zone_early_pct": 25, "zone_mid_pct": 60,
                    "phase": phase, "phase_note": pnote[0], "phase_note_zh": pnote[1]}
            nxt = ts["matrix"].get(quad, {})
            pb["next_list"] = [{"name": QUAD_SHORT.get(k, k), "name_zh": QUAD_SHORT_ZH.get(k, k),
                                "code": k, "prob_pct": round(v * 100)}
                               for k, v in sorted(nxt.items(), key=lambda kv: -kv[1])]
        except Exception as e:  # noqa: BLE001 — playbook is additive
            log.warning("hk playbook progress/next failed: %s", e)

    pb["dial"] = _dial(latest, internals)

    pref = latest.get("preference_check") or {}
    ranks = pref.get("actual_ranks") or {}
    prefs = config.load()["hk"]["engine"]["sector_preferences"]
    # HK sector_preferences are keyed by quad NAME (e.g. "Goldilocks"), and HK sector names ARE
    # the ticker keys (e.g. "Internet & Tech") — so name == ticker for the preferred list.
    quad_name = latest.get("quad_name")
    preferred = pref.get("preferred")
    if not preferred and quad_name:
        preferred = prefs.get(quad_name, [])
    pb["preferred"] = [{"ticker": n, "name": n, "rank": ranks.get(n)} for n in (preferred or [])]
    pb["pref_agreement"] = pref.get("agreement")
    pb["pref_disagree"] = pref.get("disagreement_flag")

    pb["leaders"] = [{"ticker": s["ticker"], "name": s["name"], "mom20": s.get("mom20"), "rank": s.get("rank")}
                     for s in sectors
                     if s.get("above200") and (s.get("mom20") or 0) > 0 and s.get("dir") == "up"][:5]
    pb["avoid"] = [{"ticker": s["ticker"], "name": s["name"], "state": s.get("label") or s.get("state")}
                   for s in sectors
                   if s.get("dir") == "down" or s.get("state") in ("DECLINE", "COUNTERTREND_BOUNCE")][:5]

    pb["honesty"] = {
        "en": "Hong Kong is the regional risk-on/off transmission proxy — the global-risk overlay and "
              "dual liquidity carry measured edges, but this remains a risk-context map with odds, not a "
              "forecast. No stable single-sector outperformance signal exists at monthly horizons, so the "
              "dial sizes risk and the sector names are filters, not buy calls; the cycle ladder is a "
              "drawdown tool, not a timing oracle.",
        "zh": "香港是区域风险偏好的传导代理 — 全球风险叠加与双重流动性具有实测优势，但这仍是带有概率的风险背景图，"
              "而非预测。月度尺度上不存在稳定的单一板块跑赢信号，故刻度盘用于衡量风险、板块名称仅作过滤而非买入指令；"
              "周期阶梯是回撤工具，而非择时神谕。"}
    return pb
