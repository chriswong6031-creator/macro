"""Consolidated "Signal Stack" read for the US macro page.

Institutions don't ask "is it bullish?" — they ask "*which parts of the evidence
disagree?*". This collapses the dashboard's already-computed subsystem reads into
one stacked card: each leg's direction, the regime-core agreement headline, the
constructive/cautionary tally, and the single most salient contradiction.

DISPLAY-ONLY. This module invents **no** new signal and feeds **nothing** scored —
it is a re-presentation of fields already on ``latest`` (see engine/conditions.py,
engine/axes.py, engine/regime.py). The headline "agreement" is the existing,
validated regime-core ``confidence``; the cross-subsystem legs are explicitly
tagged SCORED vs CONTEXT so an unvalidated leg can never masquerade as conviction.

Pure function of the stored ``latest`` state dict — no I/O, no recompute — so it
is cheap, deterministic and unit-testable.
"""
from __future__ import annotations

BULL, FLAT, BEAR = 1, 0, -1
_TONE = {BULL: "up", FLAT: "flat", BEAR: "down"}
_WORD_EN = {BULL: "bullish", FLAT: "neutral", BEAR: "bearish"}
_WORD_ZH = {BULL: "偏多", FLAT: "中性", BEAR: "偏空"}

# Stored English tokens -> (en, zh) display. Kept here so translation lives in one
# place rather than depending on i18n token coverage for free-form state strings.
_LIQ = {"expanding": ("expanding", "扩张"), "neutral": ("neutral", "中性"),
        "contracting": ("contracting", "收缩")}
_FC_STATE = {"loose": ("loose", "宽松"), "neutral": ("neutral", "中性"),
             "tight": ("tight", "紧张")}
_FC_TREND = {"loosening": ("loosening", "转松"), "tightening": ("tightening", "转紧"),
             "stable": ("stable", "稳定")}
_RORO = {"risk-on": ("risk-on", "风险偏好"), "risk-off": ("risk-off", "风险规避"),
         "neutral": ("neutral", "中性")}
_NEWS = {"optimistic": ("optimistic", "乐观"), "pessimistic": ("pessimistic", "悲观"),
         "neutral": ("neutral", "中性")}
_QUAD_ZH = {"Goldilocks": "理想增长", "Reflation": "再通胀", "Stagflation": "滞胀",
            "Growth Scare": "增长恐慌", "Deflation": "通缩"}

# Readable labels for the regime-core component keys (latest.confirming / .contradicting),
# so an internal dissenter can be named when no stack leg is fighting the regime.
_COMPONENT_LABELS = {
    "growth_copper_gold": ("copper/gold", "铜金比"),
    "growth_xly_xlp": ("discretionary vs staples", "可选 vs 必需消费"),
    "growth_us2y_direction": ("2y yield direction", "2年期收益率方向"),
    "growth_iwm_spy": ("small-caps vs large", "小盘 vs 大盘"),
    "growth_cyclical_defensive": ("cyclicals vs defensives", "周期 vs 防御"),
    "growth_breadth_direction": ("market breadth", "市场广度"),
    "growth_payrolls_trend": ("payrolls trend", "非农趋势"),
    "growth_indpro_trend": ("industrial production", "工业产出"),
    "growth_wei_trend": ("weekly econ index", "周度经济指数"),
    "growth_gdpnow_trend": ("GDPNow", "GDPNow"),
    "inflation_breakeven_10y_direction": ("10y breakevens", "10年通胀预期"),
    "inflation_breakeven_5y5y_direction": ("5y5y breakevens", "5y5y通胀预期"),
    "inflation_energy_rs": ("energy leadership", "能源相对强度"),
    "inflation_oil_trend": ("oil trend", "油价趋势"),
    "inflation_inflation_beta_basket": ("inflation-beta basket", "通胀贝塔篮子"),
    "inflation_tips_nominal_momentum": ("TIPS vs nominal", "TIPS vs 名义"),
    "inflation_sticky_cpi_direction": ("sticky CPI", "粘性CPI"),
}

# How worth-naming each leg is as THE main contradiction (higher = more salient).
_SALIENCE = {"breadth": 6, "credit": 5, "liquidity": 5, "options": 4,
             "volatility": 3, "sentiment": 3, "regime": 0}


def _sign(x) -> int:
    if x is None:
        return FLAT
    return BULL if x > 0 else (BEAR if x < 0 else FLAT)


def _pretty(key: str) -> str:
    return key.split("_", 1)[-1].replace("_", " ")


def _leg(key, label_en, label_zh, state_en, state_zh, direction, tier):
    return {"key": key, "label_en": label_en, "label_zh": label_zh,
            "state_en": state_en, "state_zh": state_zh, "dir": direction,
            "tone": _TONE[direction], "tier": tier}


def _vix_zh(s: str) -> str:
    if "contango" in s or "calm" in s:
        return "Contango（平静）"
    if "backward" in s or "stress" in s:
        return "Backwardation（紧张）"
    return s


def build_signal_stack(latest: dict) -> dict | None:
    """Assemble the consolidated stack from the stored ``latest`` state.

    Returns a render-ready dict, or ``None`` if too little is available
    (each leg is independently graceful — a missing source just drops its row).
    """
    if not isinstance(latest, dict) or not latest:
        return None
    cond = latest.get("conditions") or {}
    fc = cond.get("financial_conditions") or {}
    ra = cond.get("risk_appetite") or {}
    flags = latest.get("transition_flags") or {}
    confirming = set(latest.get("confirming") or [])
    contradicting = set(latest.get("contradicting") or [])

    legs: list[dict] = []

    # 1. Macro regime (SCORED) — growth/inflation quadrant anchors the read.
    gs = latest.get("growth_score")
    quad = latest.get("quad")
    if quad:
        d = BULL if quad in ("Q1", "Q2") else (BEAR if quad in ("Q3", "Q4") else FLAT)
        name = latest.get("quad_name") or quad
        legs.append(_leg("regime", "Macro regime", "宏观周期",
                         name, _QUAD_ZH.get(name, name), d, "scored"))

    # 2. Liquidity (SCORED) — Fed net-liquidity 4-week trend.
    liq = latest.get("liquidity_overlay")
    if liq:
        se, sz = _LIQ.get(liq, (liq, liq))
        d = {"expanding": BULL, "contracting": BEAR}.get(liq, FLAT)
        legs.append(_leg("liquidity", "Liquidity", "流动性", se, sz, d, "scored"))

    # 3. Credit & financial conditions (SCORED) — NFCI level + 13w trend.
    state = fc.get("state")
    if state:
        se, sz = _FC_STATE.get(state, (state, state))
        trend = fc.get("trend")
        if trend:
            te, tz = _FC_TREND.get(trend, (trend, trend))
            se, sz = f"{se} · {te}", f"{sz} · {tz}"
        d = {"loose": BULL, "tight": BEAR}.get(state, FLAT)
        legs.append(_leg("credit", "Credit & conditions", "信用与金融条件",
                         se, sz, d, "scored"))

    # 4. Volatility (CONTEXT) — VIX term structure (contango calm / backwardation stress).
    vts = ra.get("vix_term_state")
    if vts:
        d = (BULL if ("contango" in vts or "calm" in vts)
             else (BEAR if ("backward" in vts or "stress" in vts) else FLAT))
        legs.append(_leg("volatility", "Volatility", "波动率",
                         vts, _vix_zh(vts), d, "context"))

    # 5. Breadth (SCORED) — derived from the regime-core breadth component membership.
    bkey = "growth_breadth_direction"
    if bkey in confirming or bkey in contradicting:
        d = BULL if bkey in confirming else BEAR
        diverging = bool(flags.get("flag_breadth_price"))
        se = ("confirming" if d == BULL else "lagging") + (" · diverging from price" if diverging else "")
        sz = ("确认" if d == BULL else "走弱") + ("· 与价格背离" if diverging else "")
        legs.append(_leg("breadth", "Breadth", "市场广度", se, sz, d, "scored"))

    # 6. Options / dealer gamma (CONTEXT) — fragility flag near the gamma flip.
    if "flag_gex" in flags:
        fragile = bool(flags.get("flag_gex"))
        legs.append(_leg("options", "Options / dealer gamma", "期权 / 做市商Gamma",
                         "fragile (near gamma flip)" if fragile else "stable",
                         "脆弱（接近Gamma翻转）" if fragile else "稳定",
                         BEAR if fragile else FLAT, "context"))

    # 7. Sentiment / positioning (CONTEXT) — RORO risk-on/off composite + news tone.
    rs = ra.get("roro_state")
    if rs:
        se, sz = _RORO.get(rs, (rs, rs))
        nss = ra.get("news_sentiment_state")
        if nss:
            ne, nz = _NEWS.get(nss, (nss, nss))
            se, sz = f"{se} · news {ne}", f"{sz} · 新闻{nz}"
        d = {"risk-on": BULL, "risk-off": BEAR}.get(rs, FLAT)
        legs.append(_leg("sentiment", "Sentiment / positioning", "情绪 / 仓位",
                         se, sz, d, "context"))

    if len(legs) < 3:
        return None

    # ---- headline: the EXISTING validated regime-core agreement ----------------
    conf = latest.get("confidence")
    agreement_pct = round(conf * 100) if conf is not None else None
    if conf is None:
        quality_en = quality_zh = None
    elif conf >= 0.45:
        quality_en, quality_zh = "solid — well-supported", "扎实 — 支撑充分"
    elif conf >= 0.30:
        quality_en, quality_zh = "usable, not high-conviction", "可用，但非高信心"
    else:
        quality_en, quality_zh = "mixed — expect chop", "分歧 — 预期震荡"

    # ---- net lean + final read -------------------------------------------------
    anchor = _sign(gs) if gs is not None else FLAT
    n = len(legs)
    n_bull = sum(1 for x in legs if x["dir"] == BULL)
    n_bear = sum(1 for x in legs if x["dir"] == BEAR)
    n_flat = n - n_bull - n_bear

    dissent = sorted([x for x in legs if anchor and x["dir"] == -anchor],
                     key=lambda x: _SALIENCE.get(x["key"], 0), reverse=True)
    fragile = (bool(flags.get("flag_gex"))
               or latest.get("transition_state") in ("WEAKENING", "TRANSITIONING", "NEW REGIME")
               or bool(dissent))
    final_en = _WORD_EN[anchor] + (" but fragile" if fragile and anchor else "")
    final_zh = _WORD_ZH[anchor] + ("（但脆弱）" if fragile and anchor else "")

    # ---- single most salient contradiction (3-tier, always honest) -------------
    contradiction_en = contradiction_zh = None
    if dissent:
        t = dissent[0]
        contradiction_en = f"{t['label_en'].lower()} {t['state_en']} vs regime {_WORD_EN[anchor]}"
        contradiction_zh = f"{t['label_zh']}{t['state_zh']} 对阵周期{_WORD_ZH[anchor]}"
    elif contradicting and anchor:
        ckey = sorted(contradicting)[0]
        le, lz = _COMPONENT_LABELS.get(ckey, (_pretty(ckey), _pretty(ckey)))
        nm = latest.get("quad_name") or quad or "regime"
        contradiction_en = f"{le} pulling against the {nm} call"
        contradiction_zh = f"{lz}与{_QUAD_ZH.get(nm, nm)}判断相左"
    else:
        nss = ra.get("news_sentiment_state")
        if rs == "risk-on" and nss == "pessimistic":
            contradiction_en = "positioning risk-on but news tone pessimistic"
            contradiction_zh = "仓位偏向风险，但新闻情绪悲观"
        elif rs == "risk-off" and nss == "optimistic":
            contradiction_en = "positioning risk-off but news tone optimistic"
            contradiction_zh = "仓位偏向规避，但新闻情绪乐观"

    return {
        "legs": legs,
        "agreement_pct": agreement_pct,
        "quality_en": quality_en, "quality_zh": quality_zh,
        "anchor": anchor, "anchor_tone": _TONE[anchor],
        "final_en": final_en, "final_zh": final_zh,
        "n": n, "n_bull": n_bull, "n_bear": n_bear, "n_flat": n_flat,
        "n_dissent": len(dissent),
        "contradiction_en": contradiction_en, "contradiction_zh": contradiction_zh,
    }
