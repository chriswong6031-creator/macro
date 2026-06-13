"""Playbook: turn the regime + sector data into plain-English, executable
conclusions — with every claim carrying its measured historical stat.

What the 2007->present evidence actually supports (scripts/research_playbook.py;
split-half validated):

1. INDEX-LEVEL RISK is where the regime earns its keep:
   - Fed liquidity expanding was the most robust bullish conditional in BOTH
     halves of the sample — but the robust part is the DIRECTION/odds (more
     months positive than when contracting; shallower drawdowns), NOT the
     average-return magnitude, which is fragile at the honest sample size
     (net liquidity is a single macro series ≈ a few hundred episodes, not
     asset-days). So the dial leads with the odds, not a point forecast.
   - Q3 (stagflation) was the weakest quad for forward returns in both halves.
   - Risk-off quads (Q3/Q4) ran materially deeper 3-month drawdowns; average
     returns there are flattered by rebounds — the ride is worse, not the mean.
   - Transition warning states preceded weaker near-term returns pre-2017;
     the post-2017 dip-buying era blunted that edge (shown honestly).

2. SECTOR PICKING vs the index has NO stable monthly-horizon edge — signs flip
   across sample halves. What does hold:
   - Chasing extended leaders lost (44.7% hit, -0.6%/3m) -> "don't chase".
   - Buying below-trend bounces lost everywhere (-0.2 to -1.2%) -> "don't
     anticipate; wait for the trend cross".
   - 12-month relative momentum, held ~3-6m, is the only mild persistent
     tilt (+0.1-0.3%, ~51%).
   So sector output is framed as: confirmed leadership (descriptive), an
   evidence-backed avoid list, and a next-rotation watchlist with explicit
   wait-for-confirmation execution rules.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SECTOR_NAMES = {
    "XLB": "Materials", "XLC": "Communications", "XLE": "Energy",
    "XLF": "Financials", "XLI": "Industrials", "XLK": "Technology",
    "XLP": "Consumer Staples", "XLRE": "Real Estate", "XLU": "Utilities",
    "XLV": "Health Care", "XLY": "Consumer Discretionary",
    "SMH": "Semiconductors", "IWM": "Small Caps", "RSP": "Equal-Weight S&P",
    "QUAL": "Quality factor", "MTUM": "Momentum factor", "USMV": "Min-vol factor",
    "LQD": "IG Corporate Bonds", "GC=F": "Gold",
}

QUAD_MEANING = {
    "Q1": "Goldilocks — growth improving while inflation cools",
    "Q2": "Reflation — growth and inflation both heating up",
    "Q3": "Stagflation — inflation rising while growth rolls over",
    "Q4": "Growth scare — growth and inflation both falling",
}
QUAD_MEANING_ZH = {
    "Q1": "理想增长 — 增长改善、通胀降温",
    "Q2": "再通胀 — 增长与通胀同步升温",
    "Q3": "滞胀 — 通胀上行而增长走弱",
    "Q4": "增长恐慌 — 增长与通胀同步回落",
}
# user-facing names — the Q-codes collide with calendar quarters in users' minds
QUAD_SHORT = {"Q1": "Goldilocks", "Q2": "Reflation",
              "Q3": "Stagflation", "Q4": "Growth scare"}
# canonical Chinese for the short quad names + transition states, for composed prose
QUAD_SHORT_ZH = {"Q1": "理想增长", "Q2": "再通胀",
                 "Q3": "滞胀", "Q4": "增长恐慌"}
STATE_ZH = {"STABLE": "稳定", "WEAKENING": "走弱",
            "TRANSITIONING": "转换中", "NEW_REGIME": "新周期", "NEW REGIME": "新周期"}
# rotation-stage words (matches glossary: leading/weakening/improving/lagging)
STAGE_ZH = {"leading": "领先", "weakening": "走弱",
            "improving": "改善", "lagging": "落后"}

EXTENDED_PCTILE = 92

COMPONENT_PLAIN = {
    "copper_gold": "the copper-vs-gold price trend (a classic growth-expectations gauge)",
    "xly_xlp": "consumer discretionary vs staples (shopper confidence)",
    "us2y_direction": "the 2-year Treasury yield direction",
    "iwm_spy": "small caps vs large caps",
    "cyclical_defensive": "economically-sensitive sectors vs defensive ones",
    "breadth_direction": "how many S&P 500 stocks are in uptrends",
    "payrolls_trend": "the payrolls trend",
    "indpro_trend": "industrial production",
    "breakeven_10y_direction": "the bond market's 10-year inflation expectation",
    "breakeven_5y5y_direction": "long-horizon inflation expectations",
    "energy_rs": "energy sector relative strength",
    "oil_trend": "the oil price trend",
    "inflation_beta_basket": "inflation-winner sectors vs inflation-loser sectors",
    "tips_nominal_momentum": "the TIPS-vs-Treasury inflation spread",
}
COMPONENT_PLAIN_ZH = {
    "copper_gold": "铜金价格比走势（经典的增长预期指标）",
    "xly_xlp": "可选消费 vs 必需消费（消费者信心）",
    "us2y_direction": "2 年期美债收益率方向",
    "iwm_spy": "小盘股 vs 大盘股",
    "cyclical_defensive": "周期敏感板块 vs 防御板块",
    "breadth_direction": "处于上涨趋势的 S&P 500 个股数量",
    "payrolls_trend": "非农就业趋势",
    "indpro_trend": "工业生产",
    "breakeven_10y_direction": "债市的 10 年通胀预期",
    "breakeven_5y5y_direction": "长期通胀预期",
    "energy_rs": "能源板块相对强弱",
    "oil_trend": "油价走势",
    "inflation_beta_basket": "通胀受益板块 vs 通胀受损板块",
    "tips_nominal_momentum": "TIPS 与名义美债的通胀利差",
}


# ---------------------------------------------------------------- stages ----

def stage_table(closes: pd.DataFrame, asof: pd.Timestamp | None = None) -> pd.DataFrame:
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    sectors = config.load()["yahoo"]["tickers"]["sectors"]
    if asof is not None:
        closes = closes[closes.index <= asof]
    rows = []
    for t in sectors:
        if t not in closes.columns or bench not in closes.columns:
            continue
        rs = (closes[t] / closes[bench]).dropna()
        if len(rs) < 260:
            continue
        ma = rs.rolling(200).mean()
        above = bool(rs.iloc[-1] > ma.iloc[-1])
        mom20 = float(rs.pct_change(20).iloc[-1] * 100)
        mom60 = float(rs.pct_change(60).iloc[-1] * 100)
        mom252 = float(rs.pct_change(252).iloc[-1] * 100)
        pctile = float(rs.iloc[-252:].rank(pct=True).iloc[-1] * 100)
        if above and mom20 > 0:
            stage = "leading"
        elif above:
            stage = "weakening"
        elif mom20 > 0:
            stage = "improving"
        else:
            stage = "lagging"
        rows.append({"ticker": t, "name": SECTOR_NAMES.get(t, t), "stage": stage,
                     "mom_20d_pct": round(mom20, 2), "mom_60d_pct": round(mom60, 2),
                     "mom_252d_pct": round(mom252, 2), "above_trend": above,
                     "pctile_252d": round(pctile, 1),
                     "extended": stage == "leading" and pctile >= EXTENDED_PCTILE})
    return pd.DataFrame(rows).set_index("ticker")


# ------------------------------------------------- quad transition matrix ----

def quad_segments(quad: pd.Series) -> pd.DataFrame:
    q = quad.dropna()
    seg_id = (q != q.shift()).cumsum()
    g = q.groupby(seg_id)
    return pd.DataFrame({"quad": g.first(), "days": g.size(),
                         "start": g.apply(lambda s: s.index.min())}).reset_index(drop=True)


def transition_stats(quad: pd.Series) -> dict:
    seg = quad_segments(quad)
    out: dict = {"matrix": {}, "median_days": {}, "n_by_quad": {},
                 "n_segments": len(seg)}
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = seg["quad"].shift(-1)[seg["quad"] == q].dropna()
        if len(nxt):
            out["matrix"][q] = nxt.value_counts(normalize=True).round(2).to_dict()
        dur = seg.loc[seg["quad"] == q, "days"]
        if len(dur):
            out["median_days"][q] = int(dur.median())
            out["n_by_quad"][q] = int(len(dur))
    cur = seg.iloc[-1]
    out["current"] = {"quad": cur["quad"], "age_days": int(cur["days"]),
                      "median_days": out["median_days"].get(cur["quad"])}
    return out


# ------------------------------------------------------ measured evidence ----

def risk_evidence(closes: pd.DataFrame, regime: pd.DataFrame,
                  f: pd.DataFrame | None = None) -> dict:
    """Index-level conditional stats for the exposure dial, computed from the
    classifier's own history so the numbers shown are always current. When the
    feature frame `f` is supplied, also measures the conditions-layer edges
    (NFCI financial conditions, recession-risk composite) so those dial rules
    cite real forward-return stats, not assertions."""
    spy = closes["SPY"]
    quad = regime["quad"].reindex(spy.index)
    liq = regime["liquidity"].reindex(spy.index)
    state = regime["transition_state"].reindex(spy.index) \
        if "transition_state" in regime.columns else pd.Series(index=spy.index, dtype=object)
    weekly = pd.Series(False, index=spy.index)
    weekly.iloc[::5] = True
    fwd21 = spy.pct_change(21).shift(-21)
    dd63 = (spy.rolling(63).min().shift(-63) / spy - 1)

    def cond(mask: pd.Series) -> dict | None:
        m = mask.reindex(spy.index).fillna(False) & weekly & fwd21.notna()
        if m.sum() < 40:
            return None
        return {"n": int(m.sum()),
                "fwd21_avg_pct": round(100 * fwd21[m].mean(), 2),
                "fwd21_hit_pct": round(100 * (fwd21[m] > 0).mean(), 1),
                "avg_worst_dd63_pct": round(100 * dd63[m].mean(), 2)}

    out = {
        "liquidity_expanding": cond(liq == "expanding"),
        "liquidity_contracting": cond(liq == "contracting"),
        "quad_q3": cond(quad == "Q3"),
        "risk_on_quads": cond(quad.isin(["Q1", "Q2"])),
        "risk_off_quads": cond(quad.isin(["Q3", "Q4"])),
        "risk_on_stable": cond(quad.isin(["Q1", "Q2"]) & (state == "STABLE")),
        "risk_on_warning": cond(quad.isin(["Q1", "Q2"]) & (state != "STABLE")),
    }
    if f is not None:
        try:
            from engine.conditions import conditions_frame
            rc = config.load()["engine"]["conditions"]["recession"]
            cf = conditions_frame(f)
            if "nfci_chg" in cf:
                out["conditions_nfci_tightening"] = cond(cf["nfci_chg"] > 0)
                out["conditions_nfci_loosening"] = cond(cf["nfci_chg"] <= 0)
            if "recession_risk" in cf:
                rr = cf["recession_risk"]
                out["conditions_recession_high"] = cond(rr >= rc["high_score"])
                out["conditions_recession_low"] = cond(rr < rc["elevated_score"])
        except Exception:  # noqa: BLE001 — evidence is additive, never fatal
            pass
    return {k: v for k, v in out.items() if v}


# evidence constants measured in scripts/research_playbook.py (2000->2026 grid,
# split-half checked) — recomputing the full grid daily is wasteful; re-run the
# research script after any engine change and update if materially different
SECTOR_EVIDENCE = {
    "dont_chase": {"hit_pct": 44.7, "avg_excess_pct": -0.57, "horizon": "3m",
                   "desc": "buying regime-favored sectors already at >92nd pctile RS"},
    "dont_anticipate": {"hit_pct": 45.6, "avg_excess_pct": -0.73, "horizon": "3m",
                        "desc": "buying below-trend sectors on a momentum uptick (all variants negative)"},
    "momentum_tilt": {"hit_pct": 51.0, "avg_excess_pct": 0.27, "horizon": "6m",
                      "desc": "top-3 sectors by 12m relative momentum, held ~3-6m (the only mild persistent edge)"},
}


# --------------------------------------------------------------- exposure ----

def exposure_dial(latest: dict, evidence: dict) -> dict:
    """Transparent additive rules -> posture. Every rule cites its measured stat."""
    score = 0
    reasons = []

    liq = latest["liquidity_overlay"]
    ev_exp = evidence.get("liquidity_expanding")
    ev_con = evidence.get("liquidity_contracting")
    exp_hit = ev_exp["fwd21_hit_pct"] if ev_exp else None
    con_hit = ev_con["fwd21_hit_pct"] if ev_con else None
    # The robust edge here is DIRECTIONAL/odds, not the average-return magnitude:
    # net liquidity is a single macro series (~= a few hundred episodes, not
    # asset-days), and at that honest N the return gap is fragile while the
    # hit-rate gap holds up. So lead with the odds and call it odds, not a point
    # forecast — fwd21_avg_pct is deliberately dropped from this narrative (same
    # drawdown/odds-over-avg-return lesson as the risk-off caveat below). The
    # regime read itself is lagged 3 business days (regime.py:liquidity_overlay)
    # — a trader's real-time info set, not look-ahead.
    if liq == "expanding":
        score += 1
        odds_en = ((f" (S&P positive next month ~{exp_hit}% of the time"
                    + (f" vs ~{con_hit}% when contracting" if con_hit is not None else "")
                    + " — odds, not a point forecast: one macro series ≈ a few "
                      "hundred episodes, not asset-days; regime read lagged 3bd)")
                   if exp_hit is not None else "")
        odds_zh = ((f"（S&P 次月为正的概率约 {exp_hit}%"
                    + (f"，收缩时约 {con_hit}%" if con_hit is not None else "")
                    + " — 这是胜率而非点预测：单一宏观序列 ≈ 数百个事件而非资产日；"
                      "周期读数滞后 3 个交易日）")
                   if exp_hit is not None else "")
        reasons.append(("+", "Fed liquidity is expanding — historically the most "
                        "reliable directional tailwind" + odds_en,
                        "美联储流动性正在扩张 — 历来是最可靠的方向性顺风" + odds_zh))
    elif liq == "contracting":
        score -= 1
        odds_en = ((f" (S&P positive next month only ~{con_hit}% of the time"
                    + (f" vs ~{exp_hit}% when expanding" if exp_hit is not None else "")
                    + " — odds, not a point forecast; regime read lagged 3bd)")
                   if con_hit is not None else "")
        odds_zh = ((f"（S&P 次月为正的概率仅约 {con_hit}%"
                    + (f"，扩张时约 {exp_hit}%" if exp_hit is not None else "")
                    + " — 这是胜率而非点预测；周期读数滞后 3 个交易日）")
                   if con_hit is not None else "")
        reasons.append(("-", "Fed liquidity is contracting — a persistent headwind "
                        "for risk assets" + odds_en,
                        "美联储流动性正在收缩 — 对风险资产构成持续逆风" + odds_zh))

    quad = latest["quad"]
    state = latest["transition_state"]
    if quad in ("Q1", "Q2") and state == "STABLE":
        score += 1
        ev = evidence.get("risk_on_stable")
        reasons.append(("+", f"Risk-friendly regime ({QUAD_SHORT[quad]}) with no transition "
                        "warnings"
                        + (f" — in this condition the S&P averaged "
                           f"+{ev['fwd21_avg_pct']}%/month, {ev['fwd21_hit_pct']}% positive"
                           if ev else ""),
                        f"利好风险的周期（{QUAD_SHORT_ZH[quad]}），且无转换预警"
                        + (f" — 在此条件下 S&P 平均月度 "
                           f"+{ev['fwd21_avg_pct']}%，{ev['fwd21_hit_pct']}% 为正"
                           if ev else "")))
    if quad == "Q3":
        score -= 1
        ev = evidence.get("quad_q3")
        reasons.append(("-", "Stagflation (Q3) was historically the weakest backdrop for stocks"
                        + (f" ({ev['fwd21_avg_pct']:+}%/month avg)" if ev else ""),
                        "滞胀（Q3）历来是股票最弱的环境"
                        + (f"（平均月度 {ev['fwd21_avg_pct']:+}%）" if ev else "")))
    if quad == "Q4" and "Recession" in latest.get("label", ""):
        score -= 1
        reasons.append(("-", "Growth-scare with credit confirming recession — the deep-drawdown zone",
                        "增长恐慌，且信贷确认衰退 — 处于深度回撤区"))

    # --- conditions-layer rules (research/QUANT_FACTOR_EXPANSION.md) -------------
    # Independent, often EARLIER signals than the price-based quad: the Fed-research
    # recession composite (Sahm + Excess Bond Premium + term-premium-adjusted curve)
    # and broad financial conditions (NFCI). Each cites its measured forward-return
    # edge over the classifier's own 2007-> history (engine/playbook.risk_evidence).
    cond_layer = latest.get("conditions") or {}
    rec = (cond_layer.get("recession") or {})
    if rec.get("label") == "high":
        score -= 1
        ev = evidence.get("conditions_recession_high")
        evl = evidence.get("conditions_recession_low")
        tail = (f" — S&P averaged {ev['fwd21_avg_pct']:+}%/month, {ev['fwd21_hit_pct']}% positive "
                f"(vs +{evl['fwd21_avg_pct']}%, {evl['fwd21_hit_pct']}% when recession-risk is low) "
                f"and ran a {ev['avg_worst_dd63_pct']}% worst 3-month drawdown"
                if ev and evl else "")
        reasons.append(("-", f"Recession-risk composite is HIGH ({rec.get('score', 0):.0f}/100: "
                        f"Sahm + Excess Bond Premium + term-premium-adjusted curve)" + tail,
                        f"衰退风险综合评分高（{rec.get('score', 0):.0f}/100：Sahm 法则＋超额债券溢价＋"
                        f"期限溢价调整曲线）— 历史前瞻回报更弱、回撤更深"))
    elif rec.get("label") == "elevated":
        ev = evidence.get("conditions_recession_high")
        reasons.append(("i", "Recession-risk composite is ELEVATED — an early warning that often "
                        "leads the price-based recession tag; trim conviction, widen stops"
                        + (f" (the high band ran {ev['avg_worst_dd63_pct']}% worst 3-month drawdowns)"
                           if ev else ""),
                        "衰退风险综合评分偏高 — 通常领先于价格端的衰退标签的早期预警；"
                        "减少高信心押注、放宽止损"))
    fc = (cond_layer.get("financial_conditions") or {})
    if fc.get("trend") == "tightening" and (fc.get("nfci") or 0) > 0:
        score -= 1
        ev = evidence.get("conditions_nfci_tightening")
        evl = evidence.get("conditions_nfci_loosening")
        tail = (f" — S&P positive next month {ev['fwd21_hit_pct']}% of the time vs "
                f"{evl['fwd21_hit_pct']}% when loosening" if ev and evl else "")
        reasons.append(("-", "Financial conditions are tight AND tightening (Chicago Fed NFCI) — "
                        "a broad risk-off backdrop beyond Fed liquidity alone" + tail,
                        "金融条件偏紧且持续收紧（芝加哥联储 NFCI）— 超出单一美联储流动性的广泛避险背景"
                        + (f"（次月为正概率 {ev['fwd21_hit_pct']}% vs 宽松时 {evl['fwd21_hit_pct']}%）"
                           if ev and evl else "")))

    if quad in ("Q3", "Q4"):
        ev_on, ev_off = evidence.get("risk_on_quads"), evidence.get("risk_off_quads")
        if ev_on and ev_off:
            reasons.append(("i", f"Risk-off regimes don't lower average returns much (rebounds), "
                            f"but 3-month drawdowns run deeper "
                            f"({ev_off['avg_worst_dd63_pct']}% vs {ev_on['avg_worst_dd63_pct']}%) "
                            f"— smaller positions, wider stops",
                            f"避险周期不会大幅拉低平均回报（因反弹），"
                            f"但 3 个月回撤更深 "
                            f"（{ev_off['avg_worst_dd63_pct']}% vs {ev_on['avg_worst_dd63_pct']}%）"
                            f" — 缩小仓位、放宽止损"))
    if state in ("TRANSITIONING", "NEW_REGIME"):
        score -= 1
        reasons.append(("-", f"Transition radar reads {state} — the regime is shifting; "
                        "reduce conviction bets until it settles (this early-warning "
                        "worked best pre-2017; the 2017-2021 dip-buying era blunted it)",
                        f"转换雷达显示 {STATE_ZH.get(state, state)} — 周期正在转变；"
                        "在其稳定前减少高信心押注（此预警在 2017 年前效果最佳；"
                        "2017-2021 的逢低买入时代削弱了它）"))
    elif state == "WEAKENING":
        reasons.append(("i", "Transition radar reads WEAKENING (2+ warning flags) — "
                        "no action required yet, but stop adding regime-dependent risk",
                        "转换雷达显示走弱（2 个以上预警标志）— "
                        "暂无需操作，但停止增加依赖周期的风险"))

    if latest["confidence"] < 0.3:
        score = min(score, 0)
        reasons.append(("i", f"Signal agreement is low ({latest['confidence']:.0%}) — "
                        "the regime label itself is uncertain; neutral posture caps apply",
                        f"信号一致度偏低（{latest['confidence']:.0%}）— "
                        "周期标签本身不确定；适用中性立场上限"))

    posture = {2: "AGGRESSIVE", 1: "CONSTRUCTIVE", 0: "NEUTRAL",
               -1: "CAREFUL", -2: "DEFENSIVE"}[max(-2, min(2, score))]
    meaning = {
        "AGGRESSIVE": "conditions support full risk budget; buy dips in confirmed leaders",
        "CONSTRUCTIVE": "lean long; normal position sizes in confirmed leaders",
        "NEUTRAL": "no edge either way; core holdings only, no new conviction bets",
        "CAREFUL": "reduce size, tighten stops, let cash build",
        "DEFENSIVE": "minimum equity risk; capital preservation mode",
    }[posture]
    meaning_zh = {
        "AGGRESSIVE": "条件支持动用全部风险预算；在已确认的领涨者中逢低买入",
        "CONSTRUCTIVE": "偏多；在已确认的领涨者中采用常规仓位",
        "NEUTRAL": "双向均无优势；仅持核心仓位，不新增高信心押注",
        "CAREFUL": "缩小仓位、收紧止损、逐步积累现金",
        "DEFENSIVE": "股票风险敞口最小化；资本保全模式",
    }[posture]
    return {"score": score, "posture": posture, "meaning": meaning,
            "meaning_zh": meaning_zh, "reasons": reasons}


# --------------------------------------------------------------- assembly ----

def _trigger_lines(latest_flags: dict, flip: dict, pending: dict | None,
                   next_quad: str | None) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    if pending and pending.get("quad"):
        pname = QUAD_SHORT.get(str(pending["quad"]), pending["quad"])
        pname_zh = QUAD_SHORT_ZH.get(str(pending["quad"]), pending["quad"])
        lines.append((f"A regime change to {pname} is already counting down: "
                      f"{pending['days']} of {pending['need']} confirmation days done.",
                      f"转向 {pname_zh} 的周期切换已在倒计时："
                      f"已完成 {pending['days']}/{pending['need']} 个确认交易日。"))
    if flip and flip.get("component"):
        plain = COMPONENT_PLAIN.get(flip["component"], flip["component"])
        plain_zh = COMPONENT_PLAIN_ZH.get(flip["component"], flip["component"])
        lines.append((f"The most fragile support is {plain} — if it rolls over, "
                      f"the {flip['axis']} signal flips.",
                      f"最脆弱的支撑是{plain_zh} — 若其反转，"
                      f"{flip['axis']} 信号将翻转。"))
    flag_plain = {
        "flag_breadth_price": "the index is near highs but fewer stocks are participating",
        "flag_credit_equity": "stocks are up but credit markets are getting nervous",
        "flag_ratio_inflection": "risk-appetite ratios just turned against the regime",
        "flag_inflation_basket": "inflation-sensitive sectors are turning against the regime",
        "flag_confidence_decay": "the signals behind the regime are losing agreement",
        "flag_gex": "options positioning suggests a fragile, swingy market",
    }
    flag_plain_zh = {
        "flag_breadth_price": "指数接近高位，但参与上涨的个股在减少",
        "flag_credit_equity": "股票上涨，但信贷市场日趋紧张",
        "flag_ratio_inflection": "风险偏好比率刚转为不利于当前周期",
        "flag_inflation_basket": "通胀敏感板块正转为不利于当前周期",
        "flag_confidence_decay": "支撑当前周期的信号一致度正在下降",
        "flag_gex": "期权持仓显示市场脆弱、波动加剧",
    }
    on = [k for k, v in latest_flags.items() if v and k in flag_plain]
    lines.extend((f"Warning already active: {flag_plain[k]}.",
                  f"预警已激活：{flag_plain_zh[k]}。") for k in on)
    if next_quad:
        watch_by_quad = {
            "Q2": "inflation expectations and energy turning up while growth holds",
            "Q3": "inflation rising while breadth and cyclicals fade",
            "Q4": "credit spreads widening and defensives taking leadership",
            "Q1": "inflation expectations cooling while breadth holds up",
        }
        watch_by_quad_zh = {
            "Q2": "通胀预期与能源走高，而增长保持稳健",
            "Q3": "通胀上升，而市场广度与周期股走弱",
            "Q4": "信贷利差走阔，防御板块取得领先",
            "Q1": "通胀预期降温，而市场广度保持坚挺",
        }
        lines.append((f"For a shift to {QUAD_SHORT[next_quad]}, watch for "
                      f"{watch_by_quad[next_quad]}.",
                      f"若要转向 {QUAD_SHORT_ZH[next_quad]}，关注 "
                      f"{watch_by_quad_zh[next_quad]}。"))
    return lines[:4]


HEAT_BANDS = {
    "70+": ("OVERHEATED", "everything is confirmed — which historically meant late: "
            "this band UNDERperformed the index going forward. Hold with tight stops "
            "or trim; don't initiate here."),
    "55-69": ("HOT", "confirmed strength. Fine to hold; fresh entries showed no "
              "historical edge — prefer pullbacks that hold the trend."),
    "40-54": ("NEUTRAL", "mixed picture, no statistical lean either way."),
    "0-39": ("COLD", "washed out. Historically this band mildly mean-reverts upward, "
             "but timing is unreliable — wait for the confirmation trigger."),
}
HEAT_BANDS_ZH = {
    "70+": ("过热", "一切均已确认 — 这在历史上往往意味着行情偏晚："
            "该区间此后跑输指数。持有时收紧止损或减仓；不要在此处建仓。"),
    "55-69": ("偏热", "强势已确认。可以持有；新建仓位无历史优势 — "
              "优先选择守住趋势的回调。"),
    "40-54": ("中性", "图景混杂，统计上无明显倾向。"),
    "0-39": ("偏冷", "已超卖。历史上该区间存在温和的均值上行回归，"
             "但择时不可靠 — 等待确认触发信号。"),
}


def build_playbook(f: pd.DataFrame, regime: pd.DataFrame, closes: pd.DataFrame,
                   latest: dict) -> dict:
    from engine.technicals import (_score_components, band_for, calibrate,
                                   season_line, seasonality, snapshot)
    quad = latest["quad"]
    prefs = config.load()["engine"]["sector_preferences"]
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    stages = stage_table(closes)
    trans = transition_stats(regime["quad"])
    evidence = risk_evidence(closes, regime, f)
    dial = exposure_dial(latest, evidence)
    heat_cal = calibrate(closes, regime)

    aligned = set(prefs.get(quad, [])) & set(stages.index)

    # --- enrich each sector with technicals, seasonality, heat, trigger gap ----
    month = int(closes.index.max().month)
    nxt_month = month % 12 + 1
    enriched: list[dict] = []
    tech_by_ticker: dict[str, dict] = {}
    for t, row in stages.iterrows():
        close = closes[t].dropna()
        tech = snapshot(close)
        seas = seasonality(close)
        heat = _score_components(t in aligned, dial["score"], row["stage"],
                                 bool(row["extended"]), tech, row["pctile_252d"])
        band = band_for(heat["score"])
        cal = heat_cal.get(band)
        rec = {**row.to_dict(), "ticker": t, **{f"tech_{k}": v for k, v in tech.items()},
               "heat": heat["score"], "heat_parts": heat, "heat_band": band,
               "heat_label": HEAT_BANDS[band][0], "heat_note": HEAT_BANDS[band][1],
               "heat_note_zh": HEAT_BANDS_ZH[band][1],
               "heat_cal": cal,
               "season_this": season_line(seas, month),
               "season_next": season_line(seas, nxt_month),
               "season_all": seas, "season_month": month}
        # distance to the buy trigger for names below their RS trend
        if not row["above_trend"]:
            rs = (closes[t] / closes[bench]).dropna()
            ma200 = rs.rolling(200).mean()
            gap = float((ma200.iloc[-1] / rs.iloc[-1] - 1) * 100)
            lo60 = float(rs.iloc[-60:].min())
            denom = float(ma200.iloc[-1]) - lo60
            progress = float((rs.iloc[-1] - lo60) / denom * 100) if denom > 0 else None
            rec["trigger_gap_pct"] = round(gap, 1)
            rec["trigger_progress_pct"] = round(min(max(progress, 0), 100), 0) \
                if progress is not None else None
        enriched.append(rec)
        tech_by_ticker[t] = rec

    leaders, avoid = [], []
    for t, row in stages.iterrows():
        is_aligned = t in aligned
        if row["stage"] == "leading" and not row["extended"]:
            trend_note = (f"3-month RS {row['mom_60d_pct']:+.1f}%"
                          if row["mom_60d_pct"] > 0 else
                          f"rebuilding after a soft 3 months ({row['mom_60d_pct']:+.1f}%)")
            trend_note_zh = (f"3 个月 RS {row['mom_60d_pct']:+.1f}%"
                             if row["mom_60d_pct"] > 0 else
                             f"在疲软的 3 个月后重建中（{row['mom_60d_pct']:+.1f}%）")
            rec = tech_by_ticker.get(t, {})
            tech_bits = []
            tech_bits_zh = []
            if rec.get("tech_rsi14") is not None:
                tech_bits.append(f"RSI {rec['tech_rsi14']:.0f}")
                tech_bits_zh.append(f"RSI {rec['tech_rsi14']:.0f}")
            if rec.get("tech_above200") and rec.get("tech_above50"):
                tech_bits.append("above both moving averages")
                tech_bits_zh.append("位于两条均线之上")
            elif rec.get("tech_above200"):
                tech_bits.append("above its 200-day average")
                tech_bits_zh.append("位于其 200 日均线之上")
            tech_txt = (" Tech: " + ", ".join(tech_bits) + "." if tech_bits else "")
            tech_txt_zh = (" 技术面：" + "、".join(tech_bits_zh) + "。" if tech_bits_zh else "")
            season_txt = f" {rec['season_this']}." if rec.get("season_this") else ""
            season_txt_zh = f" {rec['season_this']}。" if rec.get("season_this") else ""
            leaders.append({
                "ticker": t, "name": row["name"],
                "aligned": is_aligned, "mom_60d_pct": row["mom_60d_pct"],
                "why": (f"Established uptrend vs the market, short-term momentum positive "
                        f"({row['mom_20d_pct']:+.1f}% vs the market this month; {trend_note})"
                        + (" — and the current regime historically favored it."
                           if is_aligned else ".") + tech_txt + season_txt),
                "why_zh": (f"相对市场已确立上涨趋势，短期动量为正 "
                           f"（本月相对市场 {row['mom_20d_pct']:+.1f}%；{trend_note_zh}）"
                           + ("，且当前周期历史上偏好它。"
                              if is_aligned else "。") + tech_txt_zh + season_txt_zh),
            })
        elif row["extended"]:
            avoid.append({"ticker": t, "name": row["name"], "call": "DON'T CHASE",
                          "why": (f"Leadership is real but stretched (RS at the "
                                  f"{row['pctile_252d']:.0f}th pctile of its year). "
                                  f"Historically, buying here won only "
                                  f"{SECTOR_EVIDENCE['dont_chase']['hit_pct']}% of the time "
                                  f"over 3 months. Wait for a pullback that holds the trend."),
                          "why_zh": (f"领涨真实但已超买（RS 处于其年度的 "
                                     f"第 {row['pctile_252d']:.0f} 百分位）。"
                                     f"历史上，在此处买入 3 个月内仅有 "
                                     f"{SECTOR_EVIDENCE['dont_chase']['hit_pct']}% 的胜率。"
                                     f"等待守住趋势的回调。")})
        elif row["stage"] == "improving":
            avoid.append({"ticker": t, "name": row["name"], "call": "TOO EARLY",
                          "why": (f"Momentum just turned up ({row['mom_20d_pct']:+.1f}% this month) but "
                                  f"it's still below its long-term trend vs the market. Tempting — "
                                  f"and historically a losing entry "
                                  f"({SECTOR_EVIDENCE['dont_anticipate']['avg_excess_pct']}%/3m avg). "
                                  f"Wait for the trend line to actually break."),
                          "why_zh": (f"动量刚转为向上（本月 {row['mom_20d_pct']:+.1f}%），但 "
                                     f"相对市场仍低于其长期趋势。颇具诱惑 — "
                                     f"但历史上是亏损的入场点 "
                                     f"（3 个月平均 {SECTOR_EVIDENCE['dont_anticipate']['avg_excess_pct']}%）。"
                                     f"等待趋势线真正突破。")})
        elif is_aligned and row["stage"] in ("weakening", "lagging"):
            avoid.append({"ticker": t, "name": row["name"], "call": "REGIME-TAPE CONFLICT",
                          "why": (f"The regime map favors it but the market is selling it "
                                  f"({row['mom_20d_pct']:+.1f}% vs the market this month). Tape wins — stand aside "
                                  f"until it stabilizes above trend."),
                          "why_zh": (f"周期图偏好它，但市场正在抛售它 "
                                     f"（本月相对市场 {row['mom_20d_pct']:+.1f}%）。盘面为王 — 暂时观望，"
                                     f"直到其在趋势之上企稳。")})
    leaders.sort(key=lambda x: (not x["aligned"], -x["mom_60d_pct"]))

    mom_tilt = stages.sort_values("mom_252d_pct", ascending=False).head(3)
    momentum_tilt = {
        "tickers": [{"ticker": t, "name": r["name"], "mom_252d_pct": r["mom_252d_pct"]}
                    for t, r in mom_tilt.iterrows()],
        "note": (f"Top-3 by 12-month relative momentum — the only sector tilt with a "
                 f"persistent (if mild) historical edge: "
                 f"+{SECTOR_EVIDENCE['momentum_tilt']['avg_excess_pct']}% avg vs SPY over "
                 f"~6 months, {SECTOR_EVIDENCE['momentum_tilt']['hit_pct']}% hit rate. "
                 f"A tilt, not a trade."),
        "note_zh": (f"按 12 个月相对动量排名前三 — 唯一具有持续（尽管温和）历史优势的板块倾斜："
                    f"约 6 个月内相对 SPY 平均 "
                    f"+{SECTOR_EVIDENCE['momentum_tilt']['avg_excess_pct']}%，"
                    f"{SECTOR_EVIDENCE['momentum_tilt']['hit_pct']}% 胜率。"
                    f"这是一种倾斜，而非一笔交易。"),
    }

    nxt = trans["matrix"].get(quad, {})
    next_quad = max(nxt, key=nxt.get) if nxt else None
    watchlist = []
    if next_quad:
        for t in prefs.get(next_quad, []):
            if t in stages.index and stages.loc[t, "stage"] in ("improving", "lagging"):
                row = stages.loc[t]
                rec = tech_by_ticker.get(t, {})
                trigger_txt = ""
                trigger_txt_zh = ""
                if rec.get("trigger_gap_pct") is not None:
                    trigger_txt = (f" Trigger distance: needs {rec['trigger_gap_pct']:+.1f}% "
                                   f"more outperformance vs the market to confirm")
                    trigger_txt_zh = (f" 触发距离：还需相对市场再多 "
                                      f"{rec['trigger_gap_pct']:+.1f}% 的超额表现方可确认")
                    if rec.get("trigger_progress_pct") is not None:
                        trigger_txt += (f" — already {rec['trigger_progress_pct']:.0f}% of the "
                                        f"way there from its recent low")
                        trigger_txt_zh += (f" — 自近期低点已完成 "
                                           f"{rec['trigger_progress_pct']:.0f}% 的路程")
                    trigger_txt += "."
                    trigger_txt_zh += "。"
                season_txt = f" Seasonality: {rec['season_next']}." if rec.get("season_next") else ""
                season_txt_zh = f" 季节性：{rec['season_next']}。" if rec.get("season_next") else ""
                watchlist.append({
                    "ticker": t, "name": row["name"],
                    "why": (f"Historically favored if the regime shifts to "
                            f"{QUAD_SHORT[next_quad]}. Currently {row['stage']} "
                            f"({row['mom_20d_pct']:+.1f}% vs the market this month). Don't buy in "
                            f"anticipation — wait for the trend cross.{trigger_txt}"
                            f"{season_txt}"),
                    "why_zh": (f"若周期转向 {QUAD_SHORT_ZH[next_quad]}，历史上受青睐。"
                               f"当前为{STAGE_ZH.get(row['stage'], row['stage'])} "
                               f"（本月相对市场 {row['mom_20d_pct']:+.1f}%）。不要提前买入 — "
                               f"等待趋势交叉。{trigger_txt_zh}"
                               f"{season_txt_zh}")})

    pending = None
    last = regime.dropna(subset=["quad"]).iloc[-1]
    if last["pending_quad"] and str(last["pending_quad"]) not in ("None", "nan"):
        pending = {"quad": last["pending_quad"], "days": int(last["pending_days"]),
                   "need": config.load()["engine"]["quad"]["hysteresis_days"]}

    triggers = _trigger_lines(latest.get("transition_flags", {}),
                              latest.get("flip_condition", {}), pending, next_quad)

    headline = (f"{QUAD_MEANING[quad]}. Posture: {dial['posture']} — {dial['meaning']}.")

    # --- regime progress: where are we in this regime's typical lifespan? -----
    cur = trans["current"]
    seg = quad_segments(regime["quad"])
    durs = seg.loc[seg["quad"] == quad, "days"].to_numpy()
    progress = None
    if len(durs) >= 8:
        age = cur["age_days"]
        t33, t66, p90 = (float(np.percentile(durs, p)) for p in (33, 66, 90))
        pct_longer = float((durs > age).mean() * 100)
        longer = durs[durs > age]
        med_remaining = int(np.median(longer) - age) if len(longer) else None
        phase = ("early" if age < t33 else "mid" if age < t66
                 else "late" if age <= p90 else "overdue")
        phase_note = {
            "early": "still young — regime-aligned positions have historical room to run",
            "mid": "mid-life — ride it, but keep the next-shift watchlist warm",
            "late": "older than most — tighten stops on regime-dependent positions "
                    "and take the transition radar seriously",
            "overdue": "has outlived nearly all its predecessors — treat every "
                       "warning flag as live",
        }[phase]
        phase_note_zh = {
            "early": "仍处早期 — 顺应周期的仓位在历史上仍有上行空间",
            "mid": "中期 — 顺势持有，但保持下一次转换的观察名单热度",
            "late": "比多数周期更长 — 收紧依赖周期仓位的止损，"
                    "并认真对待转换雷达",
            "overdue": "已超越几乎所有前期周期 — 将每一个预警标志视为有效",
        }[phase]
        progress = {
            "age_days": int(age), "median_days": int(np.median(durs)),
            "pct_longer": round(pct_longer, 0),
            "median_remaining_days": med_remaining,
            "phase": phase, "phase_note": phase_note, "phase_note_zh": phase_note_zh,
            "bar_pct": round(min(age / p90, 1.0) * 100, 1),
            "zone_early_pct": round(t33 / p90 * 100, 1),
            "zone_mid_pct": round(t66 / p90 * 100, 1),
            "n_history": int(len(durs)),
        }

    age_note = None
    age_note_zh = None
    if cur.get("median_days") and nxt:
        age_note = (f"This {QUAD_SHORT[quad]} stretch is {cur['age_days']} trading days old "
                    f"(historical median: {cur['median_days']}). When {QUAD_SHORT[quad]} ended, "
                    f"it went to: "
                    + ", ".join(f"{QUAD_SHORT.get(k, k)} {v:.0%}"
                                for k, v in sorted(nxt.items(), key=lambda kv: -kv[1])))
        age_note_zh = (f"本轮{QUAD_SHORT_ZH[quad]}已持续 {cur['age_days']} 个交易日 "
                       f"（历史中位数：{cur['median_days']}）。当{QUAD_SHORT_ZH[quad]}结束时，"
                       f"它转向了："
                       + "、".join(f"{QUAD_SHORT_ZH.get(k, k)} {v:.0%}"
                                  for k, v in sorted(nxt.items(), key=lambda kv: -kv[1])))

    next_list = [{"code": k, "name": QUAD_SHORT.get(k, k),
                  "meaning": QUAD_MEANING.get(k, ""), "prob_pct": round(v * 100)}
                 for k, v in sorted(nxt.items(), key=lambda kv: -kv[1])]

    # commodities & macro tape: technicals + seasonality, no heat score (no
    # RS-vs-SPY stage or regime alignment is meaningful for these)
    commodities = []
    for t, label in [("GC=F", "Gold"), ("CL=F", "Crude Oil"),
                     ("HG=F", "Copper"), ("DX-Y.NYB", "US Dollar")]:
        if t not in closes.columns:
            continue
        c = closes[t].dropna()
        if len(c) < 300:
            continue
        from engine.technicals import season_line as _sl
        from engine.technicals import seasonality as _seas
        from engine.technicals import snapshot as _snap
        tech = _snap(c)
        seas = _seas(c)
        commodities.append({"ticker": t, "name": label, **tech,
                            "season_this": _sl(seas, month),
                            "mom_60d_pct": round(float(c.pct_change(60).iloc[-1] * 100), 1)})

    return {
        "headline": headline,
        "dial": dial,
        "leaders": leaders[:4],
        "avoid": avoid[:4],
        "momentum_tilt": momentum_tilt,
        "next_quad": next_quad,
        "next_quad_name": QUAD_SHORT.get(next_quad, next_quad) if next_quad else None,
        "next_quad_probs": nxt,
        "next_list": next_list,
        "progress": progress,
        "regime_age_note": age_note,
        "regime_age_note_zh": age_note_zh,
        "quad_meaning": {"en": QUAD_MEANING[quad], "zh": QUAD_MEANING_ZH[quad]},
        "watchlist": watchlist[:4],
        "triggers": triggers,
        "stages": enriched,
        "heat_calibration": heat_cal,
        "commodities": commodities,
        "evidence": evidence,
        "honesty": ("Sector picks vs the index showed no stable edge in our 2000-2026 backtest "
                    "(results flip between decades) — so sector calls here are risk filters and "
                    "confirmation tools, not return predictions. The exposure dial conditions "
                    "are the statistically robust part."),
        "honesty_zh": ("在我们 2000-2026 年的回测中，相对指数的板块选择并无稳定优势 "
                       "（结果在不同年代间反复翻转）— 因此这里的板块判断是风险过滤与"
                       "确认工具，而非回报预测。仓位刻度盘的条件才是统计上稳健的部分。"),
    }
