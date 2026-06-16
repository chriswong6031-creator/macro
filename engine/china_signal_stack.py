"""Consolidated "Signal Stack" read for the China A-share macro page.

The China analogue of engine/signal_stack.py: it collapses the dashboard's already-
computed subsystem reads into one stacked card — each leg's lean, the regime-core
agreement headline, the constructive/cautionary tally, and the single most salient
contradiction.

DISPLAY-ONLY. Invents no new signal and feeds nothing scored — it is a re-presentation
of fields already on the China ``latest`` state (engine/china_regime.py axes + quad,
engine/china_conditions.py RORO / slowdown / drawdown gauges, engine/china_market_drivers).
The headline "agreement" is the existing regime-core ``confidence``; legs are tagged
SCORED vs CONTEXT so an unvalidated leg can never masquerade as conviction. Pure function
of ``latest`` — no I/O, deterministic, unit-testable.
"""
from __future__ import annotations

BULL, FLAT, BEAR = 1, 0, -1
_TONE = {BULL: "up", FLAT: "flat", BEAR: "down"}
_WORD_EN = {BULL: "constructive", FLAT: "neutral", BEAR: "cautious"}
_WORD_ZH = {BULL: "积极", FLAT: "中性", BEAR: "谨慎"}

_QUAD_ZH = {"Goldilocks": "理想增长", "Reflation": "再通胀", "Stagflation": "滞胀",
            "Growth scare": "增长恐慌", "Growth Scare": "增长恐慌"}
_LIQ = {"expanding": ("easing", "宽松"), "neutral": ("neutral", "中性"),
        "contracting": ("tightening", "收紧")}
_RORO = {"risk-on": ("risk-on", "风险偏好"), "risk-off": ("risk-off", "风险规避"),
         "neutral": ("neutral", "中性")}

# How worth-naming each leg is as THE main contradiction (higher = more salient).
_SALIENCE = {"roro": 6, "liquidity": 5, "drawdown": 4, "slowdown": 4,
             "drivers": 3, "growth": 2, "regime": 0}


def _sign(x) -> int:
    if x is None:
        return FLAT
    return BULL if x > 0 else (BEAR if x < 0 else FLAT)


def _leg(key, label_en, label_zh, state_en, state_zh, direction, tier):
    return {"key": key, "label_en": label_en, "label_zh": label_zh,
            "state_en": state_en, "state_zh": state_zh, "dir": direction,
            "tone": _TONE[direction], "tier": tier}


def build_china_signal_stack(latest: dict) -> dict | None:
    """Assemble the consolidated stack from the stored China ``latest`` state. Returns a
    render-ready dict (same shape as engine.signal_stack.build_signal_stack), or ``None``
    if fewer than three legs are available (each leg is independently graceful)."""
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

    # 3. PBoC liquidity (SCORED) — easing = tailwind (the validated China overlay).
    liq = latest.get("liquidity_overlay")
    if liq:
        se, sz = _LIQ.get(liq, (liq, liq))
        d = {"expanding": BULL, "contracting": BEAR}.get(liq, FLAT)
        legs.append(_leg("liquidity", "PBoC liquidity", "央行流动性", se, sz, d, "scored"))

    # 4. RORO cross-asset composite (CONTEXT) — risk-on/off.
    rs = roro.get("roro_state")
    if rs:
        se, sz = _RORO.get(rs, (rs, rs))
        d = {"risk-on": BULL, "risk-off": BEAR}.get(rs, FLAT)
        legs.append(_leg("roro", "Risk appetite (RORO)", "风险偏好（RORO）", se, sz, d, "context"))

    # 5. Slowdown gauge (CONTEXT) — high = more recession-ward (display-only, mean-reverting).
    if rec.get("label"):
        lab = rec["label"]
        d = {"high": BEAR, "low": BULL}.get(lab, FLAT)
        zh = {"low": "低", "elevated": "偏高", "high": "高"}.get(lab, lab)
        legs.append(_leg("slowdown", "Slowdown gauge", "放缓仪表", lab, zh, d, "context"))

    # 6. Drawdown-risk gauge (CONTEXT) — high/extreme = fragile.
    if dd.get("band"):
        band = dd["band"]
        d = BEAR if band in ("high", "extreme") else (BULL if band in ("calm", "low") else FLAT)
        zh = {"calm": "平静", "low": "低", "elevated": "偏高", "high": "高",
              "extreme": "极端", "fragile": "脆弱"}.get(band, band)
        legs.append(_leg("drawdown", "Drawdown risk", "回撤风险", band, zh, d, "context"))

    # 7. What's driving the tape (CONTEXT) — the market-drivers verdict, if risk-directional.
    verdict = md.get("verdict")
    if verdict in ("risk-on", "risk-off"):
        se, sz = _RORO.get(verdict, (verdict, verdict))
        legs.append(_leg("drivers", "Tape drivers", "市场驱动", se, sz,
                         BULL if verdict == "risk-on" else BEAR, "context"))

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
