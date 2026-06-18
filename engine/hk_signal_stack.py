"""Consolidated "Signal Stack" read for the Hong Kong macro page.

The HK analogue of engine/signal_stack.py (and engine/china_signal_stack.py): it
collapses the dashboard's already-computed subsystem reads into one stacked card —
each leg's lean, the regime-core agreement headline, the constructive/cautionary
tally, and the single most salient contradiction.

HK's headline edge is the GLOBAL RISK overlay (HK trades at ~2x the Mainland's
global beta) plus the HKD peg state, so those join the regime/axes/liquidity legs
the China stack carries.

DISPLAY-ONLY. Invents no new signal and feeds nothing scored — a re-presentation
of fields already on the HK ``latest`` state (engine/hk_regime.py axes + quad +
global-risk + peg, engine/hk_conditions.py RORO / slowdown / drawdown,
engine/hk_market_drivers). The headline "agreement" is the existing regime-core
``confidence``; legs are tagged SCORED vs CONTEXT. Pure function of ``latest`` — no
I/O, deterministic, unit-testable.
"""
from __future__ import annotations

BULL, FLAT, BEAR = 1, 0, -1
_TONE = {BULL: "up", FLAT: "flat", BEAR: "down"}
_WORD_EN = {BULL: "constructive", FLAT: "neutral", BEAR: "cautious"}
_WORD_ZH = {BULL: "积极", FLAT: "中性", BEAR: "谨慎"}

_QUAD_ZH = {"Goldilocks": "理想增长", "Reflation": "再通胀", "Stagflation": "滞胀",
            "Growth scare": "增长恐慌", "Growth Scare": "增长恐慌"}
_LIQ = {"expanding": ("easing", "宽松"), "neutral": ("neutral", "中性"),
        "contracting": ("tightening", "收紧"),
        "easy": ("easing", "宽松"), "tight": ("tightening", "收紧")}
_RORO = {"risk-on": ("risk-on", "风险偏好"), "risk-off": ("risk-off", "风险规避"),
         "neutral": ("neutral", "中性")}
_RISK = {"Risk-on": ("risk-on", "风险偏好"), "Risk-off": ("risk-off", "风险规避"),
         "Neutral": ("neutral", "中性"), "unknown": ("unknown", "未知")}

# Per-driver bull direction when the market_drivers fingerprint is firing "pos"
# (dir_sign > 0). HK-native drivers: some "pos" are bullish for HSI, some bearish.
_DRIVER_BULL = {
    "global_risk": +1, "china_spillover": +1, "tech_internet_leadership": +1,
    "southbound_appetite": +1, "commodity_energy": 0,
    "peg_funding_stress": -1, "us_rate_repricing": -1, "risk_off_washout": -1,
}

# How worth-naming each leg is as THE main contradiction (higher = more salient).
_SALIENCE = {"risk": 6, "roro": 6, "liquidity": 5, "peg": 5, "drawdown": 4,
             "slowdown": 4, "drivers": 3, "growth": 2, "regime": 0}


def _sign(x) -> int:
    if x is None:
        return FLAT
    return BULL if x > 0 else (BEAR if x < 0 else FLAT)


def _leg(key, label_en, label_zh, state_en, state_zh, direction, tier):
    return {"key": key, "label_en": label_en, "label_zh": label_zh,
            "state_en": state_en, "state_zh": state_zh, "dir": direction,
            "tone": _TONE[direction], "tier": tier}


def build_hk_signal_stack(latest: dict) -> dict | None:
    """Assemble the consolidated stack from the stored HK ``latest`` state. Returns a
    render-ready dict (same shape as engine.signal_stack.build_signal_stack), or
    ``None`` if fewer than three legs are available (each leg is independently
    graceful)."""
    if not isinstance(latest, dict) or not latest:
        return None
    cond = latest.get("conditions") or {}
    roro = cond.get("roro") or {}
    rec = cond.get("recession") or {}
    dd = cond.get("drawdown_risk") or {}
    md = latest.get("market_drivers") or {}

    legs: list[dict] = []

    # 1. Macro regime quad (SCORED) — anchors the read. Q1/Q2 growth-up = constructive.
    quad = latest.get("quad")
    name = latest.get("quad_name") or quad
    if quad:
        d = BULL if quad in ("Q1", "Q2") else (BEAR if quad in ("Q3", "Q4") else FLAT)
        legs.append(_leg("regime", "Macro regime", "宏观周期",
                         name, _QUAD_ZH.get(name, name), d, "scored"))

    # 2. Growth axis (SCORED) — the growth score sign.
    gs = latest.get("growth_score")
    if gs is not None:
        legs.append(_leg("growth", "Growth axis", "增长轴",
                         "rising" if gs > 0 else ("falling" if gs < 0 else "flat"),
                         "上行" if gs > 0 else ("下行" if gs < 0 else "走平"),
                         _sign(gs), "scored"))

    # 3. Global RISK overlay (SCORED) — HK's headline high-frequency driver.
    rk = latest.get("risk_state")
    if rk:
        se, sz = _RISK.get(rk, (rk, rk))
        d = {"Risk-on": BULL, "Risk-off": BEAR}.get(rk, FLAT)
        legs.append(_leg("risk", "Global risk", "全球风险", se, sz, d, "scored"))

    # 4. Dual liquidity (SCORED) — PBoC + Fed-via-peg; easing = tailwind.
    liq = latest.get("liquidity_overlay")
    if liq:
        se, sz = _LIQ.get(liq, (liq, liq))
        d = {"expanding": BULL, "easy": BULL, "contracting": BEAR, "tight": BEAR}.get(liq, FLAT)
        legs.append(_leg("liquidity", "Dual liquidity", "双重流动性", se, sz, d, "scored"))

    # 5. HKD peg state (CONTEXT) — 7.75 strong-side inflow ↔ 7.85 weak-side outflow.
    peg = latest.get("peg_state")
    if peg:
        d = BULL if "strong" in peg else (BEAR if "weak" in peg else FLAT)
        zh = ("强方（流入）" if "strong" in peg else
              ("弱方（流出）" if "weak" in peg else ("区间中" if "mid" in peg else peg)))
        legs.append(_leg("peg", "HKD peg", "港元联汇", peg, zh, d, "context"))

    # 6. RORO cross-asset composite (CONTEXT) — risk-on/off.
    rs = roro.get("roro_state")
    if rs:
        se, sz = _RORO.get(rs, (rs, rs))
        d = {"risk-on": BULL, "risk-off": BEAR}.get(rs, FLAT)
        legs.append(_leg("roro", "Risk appetite (RORO)", "风险偏好（RORO）", se, sz, d, "context"))

    # 7. Slowdown gauge (CONTEXT) — high = more slowdown-ward (display-only).
    if rec.get("label"):
        lab = rec["label"]
        d = {"high": BEAR, "low": BULL}.get(lab, FLAT)
        zh = {"low": "低", "elevated": "偏高", "high": "高"}.get(lab, lab)
        legs.append(_leg("slowdown", "Slowdown gauge", "放缓仪表", lab, zh, d, "context"))

    # 8. Drawdown-risk gauge (CONTEXT) — high/extreme = fragile.
    if dd.get("band"):
        band = dd["band"]
        d = BEAR if band in ("high", "extreme") else (BULL if band in ("calm", "low") else FLAT)
        zh = {"calm": "平静", "low": "低", "elevated": "偏高", "high": "高",
              "extreme": "极端", "fragile": "脆弱"}.get(band, band)
        legs.append(_leg("drawdown", "Drawdown risk", "回撤风险", band, zh, d, "context"))

    # 9. What's driving the tape (CONTEXT) — translate the firing driver to a HSI lean.
    if md.get("verdict") == "clear" and md.get("primary"):
        bull_dir = _DRIVER_BULL.get(md["primary"], 0)
        d = _sign(bull_dir * (md.get("dir_sign") or 0)) if bull_dir else FLAT
        if d != FLAT:
            se, sz = ("risk-on", "风险偏好") if d == BULL else ("risk-off", "风险规避")
            legs.append(_leg("drivers", "Tape drivers", "市场驱动", se, sz, d, "context"))

    if len(legs) < 3:
        return None

    # ---- headline: the existing regime-core agreement (confidence) -------------
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
    cyc = latest.get("cycle_tag")
    fragile = bool(dissent) or (dd.get("band") in ("high", "extreme"))
    final_en = _WORD_EN[anchor] + (" but fragile" if fragile and anchor else "")
    final_zh = _WORD_ZH[anchor] + ("（但脆弱）" if fragile and anchor else "")

    contradiction_en = contradiction_zh = None
    if dissent:
        tdis = dissent[0]
        contradiction_en = f"{tdis['label_en'].lower()} {tdis['state_en']} vs regime {_WORD_EN[anchor]}"
        contradiction_zh = f"{tdis['label_zh']}{tdis['state_zh']} 对阵周期{_WORD_ZH[anchor]}"

    return {
        "legs": legs,
        "agreement_pct": agreement_pct,
        "quality_en": quality_en, "quality_zh": quality_zh,
        "anchor": anchor, "anchor_tone": _TONE[anchor],
        "final_en": final_en, "final_zh": final_zh,
        "n": n, "n_bull": n_bull, "n_bear": n_bear, "n_flat": n_flat,
        "n_dissent": len(dissent),
        "contradiction_en": contradiction_en, "contradiction_zh": contradiction_zh,
        "cycle_en": cyc, "cycle_zh": cyc,
    }
