"""China A-share playbook — turns the regime + live internals into conclusions.

The US engine/playbook.py is irreducibly US (its exposure conditions are calibrated
on US liquidity/credit/breadth). This is the China analog, grounded in the China
calibration (scripts/calibrate_china.py, reports/china-calibration.md):
  - the Growth-scare quad is the market's measured best contrarian bottom
    (+9.2/+5.1 fwd, ~70% hit, robust both split-halves);
  - an expanding PBoC stance (M2 accelerating) is the one cleanly monotone tailwind;
  - Stagflation is regime-unstable pre-2016 (2008 GFC) — lean on confirmation;
  - no stable single-sector monthly outperformance signal exists (risk-filter only).

Produces a `pb` dict the template renders: quad meaning, lifespan progress vs the
classifier's own history, next-quad base rates, an exposure DIAL with reasons built
from live internals (margin crowding, PBoC liquidity, southbound flow, M1-M2 scissors),
the framework-preferred sectors with live tape agreement, and confirmed leaders / avoids.
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from lib import config

log = logging.getLogger(__name__)


def _strip_internal_ids(s: str) -> str:
    """Remove parentheticals containing internal ruling IDs (§, SS prefix) from
    user-facing reason strings.  Engine-side log strings are left untouched.

    Examples stripped:
        '(§W6-CN: triple-count collapse)' → ''
        '(SS-CN Fix 5)'                   → ''
    """
    return re.sub(r'\s*\((§|SS)[^)]*\)', '', s)

QUAD_MEANING_CN = {
    "Q1": ("Goldilocks — growth firming while price pressure eases. Historically the "
           "friendliest A-share backdrop for tech, quality growth and consumer leaders.",
           "理想增长 — 增长回暖、物价压力缓解。历史上对科技、优质成长与消费龙头最友好的 A 股环境。"),
    "Q2": ("Reflation — growth and prices both rising. Favors cyclicals, brokers, materials "
           "and property, but the backtest shows only a mild edge — fade strength, don't chase.",
           "再通胀 — 增长与物价同步上行。利好周期股、券商、材料与地产，但回测仅显示微弱优势 — 宜逢强减持而非追高。"),
    "Q3": ("Stagflation — growth fading while prices stay hot. The dangerous quad; defensives, "
           "banks and upstream materials hold up best. Historically unstable in China — lean on confirmation.",
           "滞胀 — 增长走弱而物价高企。最危险的象限；防御板块、银行与上游材料相对抗跌。在中国历史上不稳定 — 宜依赖确认信号。"),
    "Q4": ("Growth-scare — both growth and prices falling, fear peaking. The market's measured "
           "best contrarian bottom (highest forward return, ~70% hit). Accumulate quality into the fear.",
           "增长恐慌 — 增长与物价齐跌、恐慌见顶。实测最佳的逆向底部（前瞻收益最高，命中率约 70%）。在恐慌中吸纳优质资产。"),
}

_POSTURES = ["DEFENSIVE", "CAREFUL", "NEUTRAL", "CONSTRUCTIVE", "AGGRESSIVE"]


def _dial(latest: dict, internals: dict) -> dict:
    """Exposure posture + signed reasons, from quad base + live internals."""
    score, reasons = 0, []
    quad = latest.get("quad")
    if quad == "Q4":
        score += 2
        reasons.append(("+", "Growth-scare is the market's measured best contrarian bottom (~70% hit) — accumulate quality into the fear.",
                        "增长恐慌是实测最佳的逆向底部（命中率约70%）— 在恐慌中吸纳优质资产。"))
    elif quad == "Q1":
        score += 1
        reasons.append(("+", "Goldilocks — growth firming with price pressure easing, the friendliest backdrop for quality growth.",
                        "理想增长 — 增长回暖、物价压力缓解，最利好优质成长。"))
    elif quad == "Q2":
        reasons.append(("i", "Reflation carries only a mild measured edge — favor cyclicals/materials but fade strength.",
                        "再通胀仅有微弱的实测优势 — 偏好周期／材料，但逢强减持。"))
    elif quad == "Q3":
        score -= 1
        reasons.append(("-", "Stagflation is the dangerous quad — defensives/banks/upstream hold up best; it is regime-unstable in China.",
                        "滞胀是最危险的象限 — 防御／银行／上游相对抗跌；在中国周期不稳定。"))

    # --- MONETARY-CONDITIONS: ONE VOTE (max contribution ±1) ---
    # Collapsed from three co-moving PBoC-aggregate legs (M2-accel, M1−M2 scissors, TSF
    # credit-impulse) to a single monetary-conditions vote per research/CHINA_ENGINE_REASSESSMENT.md
    # §W6-CN Fix 5. Root cause: all three legs derive from the same monthly PBoC aggregates;
    # counting them separately let "easing = 3 legs × +1 = AGGRESSIVE" with zero tape confirmation.
    # The "china_leads" canonical module (W3-CN plan) will own the final computation; this dial
    # uses the same monthly inputs but caps at ONE monetary-conditions vote.
    #
    # SYMMETRIC BANDS (fixes the old scissors asymmetry: was +1 at ≥0 but −1 only at ≤−5):
    #   scissors < −2 → bearish vote; scissors > +2 → bullish vote; −2..+2 → neutral.
    # Vote = sign-vote of the MAJORITY of available legs (majority rules, 1-vote cap).
    _monetary_legs: list[int] = []   # each leg contributes −1, 0, or +1

    liq = latest.get("liquidity_overlay")
    if liq == "expanding":
        _monetary_legs.append(1)
    elif liq == "contracting":
        _monetary_legs.append(-1)
    else:
        _monetary_legs.append(0)

    c = (internals or {}).get("credit")
    _SCISSORS_THR = 2.0     # symmetric band: ±2pp threshold
    if c and c.get("scissors") is not None:
        sc = float(c["scissors"])
        if sc >= _SCISSORS_THR:
            _monetary_legs.append(1)
        elif sc <= -_SCISSORS_THR:
            _monetary_legs.append(-1)
        else:
            _monetary_legs.append(0)

    if c and c.get("credit_impulse") is not None and c.get("credit_impulse_6mo") is not None:
        ci, ci6 = float(c["credit_impulse"]), float(c["credit_impulse_6mo"])
        if ci > ci6 and ci > 0:
            _monetary_legs.append(1)
        elif ci < ci6 and ci < 0:
            _monetary_legs.append(-1)
        else:
            _monetary_legs.append(0)

    # Majority-rules vote (ties → 0), capped at ONE score point.
    _positive = sum(1 for v in _monetary_legs if v > 0)
    _negative = sum(1 for v in _monetary_legs if v < 0)
    _n_avail = len(_monetary_legs)
    if _n_avail > 0 and _positive > _negative:
        score += 1
        _all_agree = _positive == _n_avail
        _en_str = (
            "PBoC monetary conditions easing — M2 accelerating, scissors positive, credit impulse rising "
            f"({_positive}/{_n_avail} legs agree). ONE monetary-conditions vote "
            "(§W6-CN: collapsed from three co-moving legs to prevent triple-count)."
            if _all_agree else
            f"PBoC monetary conditions tilting easing ({_positive}/{_n_avail} legs). "
            "ONE monetary-conditions vote (§W6-CN: triple-count collapse)."
        )
        reasons.append(("+", _strip_internal_ids(_en_str), (
            f"央行货币条件趋宽（{_positive}/{_n_avail}项指标同意）— 综合M2/剪刀差/社融的单次货币投票。"
        )))
    elif _n_avail > 0 and _negative > _positive:
        score -= 1
        _en_str = (
            f"PBoC monetary conditions tightening ({_negative}/{_n_avail} legs agree). "
            "ONE monetary-conditions vote (§W6-CN: triple-count collapse)."
        )
        reasons.append(("-", _strip_internal_ids(_en_str), (
            f"央行货币条件趋紧（{_negative}/{_n_avail}项指标同意）— 综合M2/剪刀差/社融的单次货币投票。"
        )))
    else:
        if _n_avail > 0:
            reasons.append(("i", (
                f"PBoC monetary conditions mixed ({_positive} easing / {_negative} tightening / "
                f"{_n_avail - _positive - _negative} neutral) — no net vote."
            ), "央行货币条件分歧 — 无净投票。"))

    # --- NON-MONETARY CONTEXT LEGS (unchanged) ---
    m = (internals or {}).get("margin")
    if m and m.get("pctile") is not None:
        if m["pctile"] >= 85:
            score -= 1
            reasons.append(("-", f"Margin leverage crowded ({m['pctile']}th percentile of float) — late-stage froth, tighten risk.",
                            f"融资杠杆拥挤（占流通市值 {m['pctile']} 分位）— 后期泡沫，收紧风险。"))
        elif m["pctile"] <= 20:
            score += 1
            reasons.append(("+", f"Margin leverage capitulated ({m['pctile']}th percentile) — washed-out positioning.",
                            f"融资杠杆已出清（{m['pctile']} 分位）— 仓位已被洗净。"))

    sb = (internals or {}).get("southbound")
    if sb and sb.get("net_z") is not None:
        if sb["net_z"] >= 1.0:
            score += 1
            reasons.append(("+", "Southbound buying strong — mainland money leaning risk-on.",
                            "南向资金大幅净买入 — 内地资金偏向风险偏好。"))
        elif sb["net_z"] <= -1.0:
            score -= 1
            reasons.append(("-", "Southbound selling — mainland money leaning risk-off.",
                            "南向资金净卖出 — 内地资金偏向避险。"))

    idx = max(0, min(4, 2 + score))
    return {"posture": _POSTURES[idx], "score": score, "reasons": reasons}


def build(latest: dict, hist: pd.DataFrame | None, sectors: list[dict], internals: dict) -> dict:
    from engine.playbook import QUAD_SHORT, QUAD_SHORT_ZH, quad_segments, transition_stats
    pb: dict = {}
    quad = latest.get("quad")
    qm = QUAD_MEANING_CN.get(quad)
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
            log.warning("china playbook progress/next failed: %s", e)

    pb["dial"] = _dial(latest, internals)

    pref = latest.get("preference_check") or {}
    names = config.load()["china"]["yahoo"]["sector_etfs"]
    # Use rotation rank from the passed `sectors` list (now set by score_and_rank)
    # so there is ONE rank system page-wide.  Fallback to pref.actual_ranks (60d RS)
    # only when sectors is empty or the ticker is absent.
    _sector_rank_by_ticker = {s["ticker"]: s.get("rank") for s in (sectors or [])}
    _old_ranks = pref.get("actual_ranks") or {}
    pb["preferred"] = [
        {"ticker": t, "name": (names.get(t) or [t])[0],
         "rank": _sector_rank_by_ticker.get(t, _old_ranks.get(t))}
        for t in pref.get("preferred", [])
    ]
    pb["pref_agreement"] = pref.get("agreement")
    pb["pref_disagree"] = pref.get("disagreement_flag")

    pb["leaders"] = [{"ticker": s["ticker"], "name": s["name"], "mom20": s.get("mom20"), "rank": s.get("rank")}
                     for s in sectors
                     if s.get("above200") and (s.get("mom20") or 0) > 0 and s.get("dir") == "up"][:5]
    pb["avoid"] = [{"ticker": s["ticker"], "name": s["name"], "state": s.get("label") or s.get("state")}
                   for s in sectors
                   if s.get("dir") == "down" or s.get("state") in ("DECLINE", "COUNTERTREND BOUNCE")][:5]

    pb["honesty"] = {
        "en": "China regimes are shorter and less stable than the US — this is a risk-context map with "
              "measured odds, not a forecast. No stable single-sector outperformance signal exists at "
              "monthly horizons, so the dial sizes risk and the sector names are filters, not buy calls.",
        "zh": "中国的周期比美国更短、更不稳定 — 这是带有实测概率的风险背景图，而非预测。月度尺度上不存在稳定的"
              "单一板块跑赢信号，故刻度盘用于衡量风险、板块名称仅作过滤，而非买入指令。"}
    return pb
