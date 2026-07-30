"""Market State — the composite "what kind of market is this?" read.

A DISPLAY-ONLY synthesis (in the same family as fear_euphoria / signal_stack):
it never scores, sizes, or feeds any axis / regime / macro_risk. It transparently
BLENDS signals the dashboard already computes — the index multi-timeframe tape,
cross-asset risk appetite, the volatility regime, market breadth, Fed liquidity &
credit, and the downturn-risk guards — into ONE 0-100 risk-on score and a
Green / Yellow / Red verdict:

    GREEN  · RISK-ON   — trend, breadth and cross-asset confirmation line up.
    YELLOW · MIXED     — signals disagree / a transition is underway. Trade smaller.
    RED    · RISK-OFF  — the tape is under stress and trend is down. Defend first.

This is confirmation-over-prediction by construction: every leg reads what has
ALREADY turned (price across timeframes, vol term structure, credit, breadth),
not a forecast. A handful of early-warning OVERRIDES (an 'act' alert, a fresh
regime flip, a high/extreme drawdown-risk or acute systemic-stress band) can cap
or force the verdict so the headline can never read "risk-on" while a stress
gauge is screaming. The HEAVIEST of these is the Risk Radar (engine/risk_radar.py):
an active radar imposes an amplified score CEILING that descends with its intensity
and with every other risk gauge flashing at the same time — so the validated leading
drawdown signal dominates the bullish legs instead of being averaged into silence.

Pure functions, never raises: any shortfall degrades the affected leg (or the
whole read) to None and the page still builds. No new data is fetched — the
index tape is read off the feature frame already in memory.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

log = logging.getLogger("market_state")

# component weights (only the legs that resolve are renormalised at blend time)
WEIGHTS = {
    "trend": 0.24,        # the broad-market tape across timeframes — "the market itself"
    "risk": 0.18,         # cross-asset risk appetite (RORO + bonds/FX confirmation)
    "vol": 0.16,          # the volatility regime (term structure / VRP / complacency)
    "breadth": 0.16,      # participation — how many stocks are in the move
    "liquidity": 0.14,    # the money tide + credit
    "stress": 0.12,       # the downturn-risk guard (macro-risk / drawdown / recession)
}

# the broad US tape, longest-horizon weighted (a "state" read leans on W/M)
_TF_W = {"D": 0.15, "3D": 0.15, "W": 0.40, "M": 0.30}
_INDEXES = [
    ("SPY", "S&P 500", "标普500"),
    ("QQQ", "Nasdaq 100", "纳指100"),
    ("IWM", "Russell 2000", "罗素2000"),
]
_TF_LABEL = {"D": ("Daily", "日"), "3D": ("3-Day", "3日"), "W": ("Weekly", "周"), "M": ("Monthly", "月")}


# --------------------------------------------------------- market profile ----
# The blender, tape, verdict/cap/flip and override machinery below are all
# market-neutral. Only the index tape, the five conditions readers, the radar
# source, and which early-warning overrides apply differ per market. A
# MarketProfile gathers exactly those so the SAME engine serves the US macro
# page and the China / HK / Canada home pages (engine/market_state_cn.py etc.).
# US_PROFILE (defined below, once the default readers exist) reproduces today's
# behaviour byte-for-byte, so a profile-less call is unchanged.
@dataclass(frozen=True)
class MarketProfile:
    key: str                                    # "us" | "cn" | "hk" | "ca"
    indices: tuple                              # ((ticker, en, zh), ...) for the tape
    tape_noun_en: str                           # e.g. "US indices" / "China indices"
    tape_noun_zh: str
    component_readers: tuple                     # (fn(latest)->comp|None, ...) the 5 non-trend legs
    radar_override: Callable | None = None       # fn(latest, overrides)->dict ; None = no radar
    # which early-warning overrides apply: any of
    #   "alert_act" · "new_regime" · "stress_band" · "dislocation"
    overrides: frozenset = field(
        default_factory=lambda: frozenset({"alert_act", "new_regime", "stress_band", "dislocation"}))
    caveat_en: str = ""                          # honest "display-only / lighter than US" board footnote
    caveat_zh: str = ""


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _num(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _arrow(sign: int) -> str:
    return "▲" if sign > 0 else "▼" if sign < 0 else "▶"


def _tone_from_score(s01: float) -> str:
    if s01 >= 0.60:
        return "good"
    if s01 >= 0.42:
        return "warn"
    return "bad"


# --------------------------------------------------------------- the tape ----

def _tf_sign(st: dict) -> int:
    """Up / flat / down for one already-computed _tf_state dict."""
    if not st:
        return 0
    mp = st.get("macd_pos")
    rsi = _num(st.get("rsi14"))
    if mp is None:
        return 0
    if mp and (rsi is None or rsi >= 50):
        return 1
    if (not mp) and (rsi is None or rsi < 50):
        return -1
    return 0  # macd/rsi disagree → genuinely mixed


def _index_mtf(close: pd.Series) -> dict | None:
    """Per-timeframe arrow read for one index. None if too little history.

    PREMISE REPAIR — R3b (2026-07-18):
    The W timeframe now reads the COMPLETED weekly bar only (completed_only=True),
    mirroring the IHM-R1 PIT gate in engine/index_momentum.py.
    Before this fix the live partial-week resample was used, so the in-progress
    bounce week of 07-14..16 produced macd_pos=True / trend=85 GOOD while the
    completed 07-10 weekly bar had already rolled over (QQQ hist −0.212,
    vel3 −1.324).  07-16 counterfactual: trend 85 → materially lower.
    Switch date: 2026-07-18.  See research/RISK_SCORING_REVAMP_MASTERPLAN_BY_FABLE.md §2 R3b.
    """
    from engine import cycles  # lazy — keeps module import cheap
    s = close.dropna().astype(float)
    if len(s) < 60:
        return None
    snap = cycles.mtf_snapshot(s, completed_only=True)
    cells, score_num, score_den = {}, 0.0, 0.0
    for tf, w in _TF_W.items():
        st = snap.get(tf) or {}
        if not st:
            cells[tf] = None
            continue
        sign = _tf_sign(st)
        cells[tf] = {
            "sign": sign, "arrow": _arrow(sign),
            "tone": "good" if sign > 0 else "bad" if sign < 0 else "flat",
            "rsi": _num(st.get("rsi14")), "macd_pos": bool(st.get("macd_pos")),
        }
        score_num += w * sign
        score_den += w
    if score_den == 0:
        return None
    mean = score_num / score_den               # [-1, 1]
    short = _tf_sign(snap.get("D") or {}) + _tf_sign(snap.get("3D") or {})
    mid = _tf_sign(snap.get("W") or {})
    long = _tf_sign(snap.get("M") or {})
    if mean >= 0.34:
        conf_en, conf_zh, tone = "Uptrend", "上升趋势", "good"
    elif mean <= -0.34:
        conf_en, conf_zh, tone = "Downtrend", "下降趋势", "bad"
    elif short > 0 >= mid:
        conf_en, conf_zh, tone = "Turning up", "转强中", "warn"
    elif short < 0 <= mid:
        conf_en, conf_zh, tone = "Rolling over", "转弱中", "warn"
    else:
        conf_en, conf_zh, tone = "Mixed", "分化", "warn"
    return {"cells": cells, "mean": mean, "confluence_en": conf_en,
            "confluence_zh": conf_zh, "tone": tone}


def _build_tape(frame, indices=None) -> tuple[dict | None, float | None]:
    """The multi-timeframe board + an aggregate trend score01."""
    if frame is None:
        return None, None
    rows, means = [], []
    for tkr, en, zh in (indices or _INDEXES):
        if tkr not in getattr(frame, "columns", []):
            continue
        mtf = _index_mtf(frame[tkr])
        if mtf is None:
            continue
        rows.append({"ticker": tkr, "label_en": en, "label_zh": zh, **mtf})
        means.append(mtf["mean"])
    if not rows:
        return None, None
    agg = float(np.mean(means))                # [-1, 1]
    return {"indices": rows}, _clamp((agg + 1) / 2)


# ----------------------------------------------------------- the components ----

def _component(key, label_en, label_zh, s01, read_en, read_zh, metrics, mean=None,
               degraded=None):
    """One blended leg. `degraded` = list of {key, note_en, note_zh} for inputs that have NO
    current print, so the leg is carried on fewer gauges than its label implies. The leg still
    renders (a null never blocks display tier) but it now SAYS which input is missing instead of
    imputing a neutral reading and presenting the result at full confidence."""
    if s01 is None:
        return None
    s01 = _clamp(s01)
    if mean is None:
        sign = 1 if s01 >= 0.58 else -1 if s01 <= 0.42 else 0
    else:
        sign = 1 if mean >= 0.25 else -1 if mean <= -0.25 else 0
    out = {
        "key": key, "label_en": label_en, "label_zh": label_zh,
        "score": round(s01 * 100), "weight": WEIGHTS[key],
        "tone": _tone_from_score(s01), "arrow": _arrow(sign),
        "read_en": read_en, "read_zh": read_zh,
        "metrics": [m for m in metrics if m and m.get("v") not in (None, "")],
        "degraded": bool(degraded),
    }
    if degraded:
        out["degraded_inputs"] = [d["key"] for d in degraded]
        out["degraded_note_en"] = " ".join(d["note_en"] for d in degraded)
        out["degraded_note_zh"] = "".join(d["note_zh"] for d in degraded)
    return out


def _metric(k_en, k_zh, v):
    return {"k_en": k_en, "k_zh": k_zh, "v": v}


def _comp_risk(latest: dict) -> dict | None:
    C = latest.get("conditions") or {}
    ra = C.get("risk_appetite") or {}
    state = ra.get("roro_state")
    if state is None:
        return None
    base = {"risk-on": 0.78, "neutral": 0.5, "risk-off": 0.22}.get(state, 0.5)
    cac = latest.get("cross_asset_confirm") or {}
    agree = _num(cac.get("agree_pct"))
    tb = cac.get("to_brain") or {}
    adj = 0.0
    if agree is not None:
        adj += (agree - 50) / 100 * 0.30
    if (tb.get("stock_bond_hedge") or "") == "breakdown":
        adj -= 0.08
    s01 = _clamp(base + adj)
    zh_state = {"risk-on": "风险偏好", "neutral": "中性", "risk-off": "避险"}.get(state, state)
    read_en = f"Cross-asset RORO {state}"
    read_zh = f"跨资产 RORO {zh_state}"
    if cac.get("verdict"):
        read_en += f"; bonds/FX {cac['verdict']}"
        read_zh += f"；债/汇 {cac.get('verdict_zh') or cac['verdict']}"
    return _component(
        "risk", "Risk appetite", "风险偏好", s01, read_en, read_zh,
        [_metric("RORO", "RORO", state),
         _metric("Bonds/FX agree", "债/汇一致", f"{int(agree)}%" if agree is not None else None),
         _metric("Bond health", "债券健康", tb.get("bond_health")),
         _metric("Stock-bond hedge", "股债对冲", tb.get("stock_bond_hedge"))])


def _comp_vol(latest: dict) -> dict | None:
    C = latest.get("conditions") or {}
    ra = C.get("risk_appetite") or {}
    cmp_ = C.get("complacency") or {}
    term = _num(ra.get("vix_term"))
    if term is None:
        return None
    if term < 0.90:
        term_s = 0.85
    elif term < 1.0:
        term_s = 0.62
    elif term < 1.05:
        term_s = 0.42
    else:
        term_s = 0.20                              # backwardation = stress
    vix_p = _num(cmp_.get("vix_pctile"))
    vix_s = 0.6 if vix_p is None else _clamp(1 - vix_p)   # high vol pctile → lower
    s01 = 0.62 * term_s + 0.38 * vix_s
    if (cmp_.get("state") or "") in ("watch", "high"):
        s01 -= 0.06                                # complacency caveat
    s01 = _clamp(s01)
    contango = term < 1.0
    read_en = f"VIX term {'contango (calm)' if contango else 'backwardation (stress)'}"
    read_zh = f"VIX 期限{'正向（平静）' if contango else '倒挂（承压）'}"
    if vix_p is not None:
        read_en += f"; vol {int(vix_p*100)}%ile"
        read_zh += f"；波动 {int(vix_p*100)} 百分位"
    return _component(
        "vol", "Volatility regime", "波动率环境", s01, read_en, read_zh,
        [_metric("VIX term", "VIX 期限", f"{term:.2f}"),
         _metric("VIX %ile", "VIX 百分位", f"{int(vix_p*100)}%" if vix_p is not None else None),
         _metric("VRP %ile", "VRP 百分位",
                 f"{int(_num(ra.get('vrp_pctile'))*100)}%" if _num(ra.get("vrp_pctile")) is not None else None),
         _metric("Complacency", "自满", cmp_.get("state"))])


_ZH_YEAR_WORD = {1: "一年", 2: "两年", 3: "三年", 4: "四年", 5: "五年",
                 6: "六年", 7: "七年", 8: "八年", 9: "九年", 10: "十年"}


def _breadth_window_label() -> tuple[str, str]:
    """(en, zh) label for the breadth-percentile lookback, derived from the config key the
    percentile itself uses (engine.conditions.complacency.breadth_pctile_lookback_d, in TRADING
    days ~252/yr). Falls back to the shipped 504d ~= 2y if config is unreadable."""
    d = 504
    try:
        from lib import config  # noqa: PLC0415
        d = int(((config.load()["engine"]["conditions"].get("complacency") or {})
                 .get("breadth_pctile_lookback_d")) or 504)
    except Exception:  # noqa: BLE001 — copy label, never fatal
        pass
    yrs = max(1, int(round(d / 252)))
    return (f"{yrs}y", _ZH_YEAR_WORD.get(yrs, f"{yrs}年"))


def _comp_breadth(latest: dict) -> dict | None:
    C = latest.get("conditions") or {}
    cmp_ = C.get("complacency") or {}
    b200 = _num(cmp_.get("breadth_above200_pctile"))
    if b200 is None:
        return None
    div = bool(cmp_.get("breadth_div"))
    s01 = _clamp(b200 - (0.16 if div else 0.0))
    # The percentile window is conditions.complacency.breadth_pctile_lookback_d (504 trading days
    # ~= 2 years), NOT five years — the copy said "of 5y" and had since the leg shipped, inflating
    # the claimed history by 2.5x (audit 2026-07-29). Read from the SAME config key the percentile
    # is computed from so the two can never drift apart again.
    win_en, win_zh = _breadth_window_label()
    read_en = (f"Breadth {int(b200*100)}%ile of {win_en}; "
               + ("a divergence vs price" if div else "confirming price"))
    read_zh = (f"广度处于{win_zh} {int(b200*100)} 百分位；" + ("与价格背离" if div else "确认价格"))
    return _component(
        "breadth", "Breadth & participation", "广度与参与", s01, read_en, read_zh,
        [_metric(">200d %ile", ">200日 百分位", f"{int(b200*100)}%"),
         _metric("Divergence", "背离", "yes" if div else "no")])


def _comp_liquidity(latest: dict) -> dict | None:
    C = latest.get("conditions") or {}
    liq = latest.get("liquidity_overlay")
    if liq is None:
        return None
    base_liq = {"expanding": 0.82, "neutral": 0.5, "contracting": 0.28}.get(liq, 0.5)
    cmp_ = C.get("complacency") or {}
    fc = C.get("financial_conditions") or {}
    ss = C.get("systemic_stress") or {}
    credit = 0.5
    hy = _num(cmp_.get("hy_oas_chg_21d_bp"))
    if hy is not None:
        credit += _clamp(-hy / 40 * 0.18, -0.18, 0.18)   # tightening (-bp) → healthier
    # DEGRADED-NOT-IMPUTED (audit 2026-07-29). Each of these two terms is an additive OFFSET
    # around 0.5, so a missing input contributes 0.0 — arithmetically the only unbiased choice
    # (there is no denominator to renormalise), but the leg then PRESENTS at full confidence
    # while silently carrying one fewer gauge. Today conditions.financial_conditions is entirely
    # None (the NFCI print of 2026-07-17 aged past inputs.py's ffill_limit=7), the metric row
    # simply vanished, and nothing on the page said the credit leg had lost a gauge. The
    # arithmetic is UNCHANGED — what changes is that the shortfall is now named. Weights and
    # offsets are untouched.
    degraded = []
    if fc.get("state") is None:
        degraded.append({
            "key": "financial_conditions",
            "note_en": "Financial conditions (NFCI) has no current print, so this leg is carried "
                       "on the Fed liquidity tide, HY credit and systemic stress only.",
            "note_zh": "金融条件（NFCI）暂无最新数据，本项仅由联储流动性、高收益信用与系统性压力构成。",
        })
    if ss.get("state") is None:
        degraded.append({
            "key": "systemic_stress",
            "note_en": "Systemic stress has no current print, so it is not contributing here.",
            "note_zh": "系统性压力暂无最新数据，未参与本项。",
        })
    credit += {"loose": 0.12, "tight": -0.14, "neutral": 0.0}.get(fc.get("state"), 0.0)
    credit += {"calm": 0.06, "normal": 0.0, "elevated": -0.12, "acute": -0.28}.get(ss.get("state"), 0.0)
    credit = _clamp(credit)
    s01 = _clamp(0.55 * base_liq + 0.45 * credit)
    zh_liq = {"expanding": "扩张", "neutral": "中性", "contracting": "收缩"}.get(liq, liq)
    read_en = f"Fed liquidity {liq}"
    read_zh = f"联储流动性{zh_liq}"
    # DIRECTION off the UNROUNDED change (audit 2026-07-29). `hy_oas_chg_21d_bp` is rounded to
    # whole bp, so a -0.4bp TIGHTENING becomes -0.0 — and `-0.0 < 0` is False, so the copy read
    # "widening" while credit had in fact tightened. conditions now also ships the exact value;
    # `credit_widen` (the unrounded > 0 test) is the fallback, the rounded value the last resort.
    if hy is not None:
        exact = _num(cmp_.get("hy_oas_chg_21d_bp_exact"))
        if exact is not None:
            dir_en, dir_zh = (("widening", "走阔") if exact > 0 else
                              ("tightening", "收窄") if exact < 0 else ("flat", "持平"))
        elif cmp_.get("credit_widen") is not None:
            dir_en, dir_zh = (("widening", "走阔") if cmp_.get("credit_widen")
                              else ("tightening", "收窄"))
        else:
            dir_en, dir_zh = ("tightening", "收窄") if hy < 0 else ("widening", "走阔")
        read_en += f"; HY credit {dir_en}"
        read_zh += f"；高收益信用{dir_zh}"
    return _component(
        "liquidity", "Liquidity & credit", "流动性与信用", s01, read_en, read_zh,
        [_metric("Fed liquidity", "联储流动性", liq),
         _metric("HY OAS Δ21d", "高收益利差 21日", f"{hy:+.0f}bp" if hy is not None else None),
         # an absent NFCI print still drops this row (an EN-only "no print" string in a value
         # slot would break the bilingual contract) — the bilingual degraded_note_en/zh below
         # is what discloses it, per the house degraded-block idiom.
         _metric("Conditions", "金融条件", fc.get("state")),
         _metric("Systemic stress", "系统性压力", ss.get("state"))],
        degraded=degraded)


def _comp_stress(latest: dict) -> dict | None:
    C = latest.get("conditions") or {}
    mr = latest.get("macro_risk") or {}
    score = _num(mr.get("score"))               # 0-1 risk-OFF
    if score is None:
        return None
    risk_on = 1 - score
    dd = C.get("drawdown_risk") or {}
    dd_s = {"low": 0.85, "elevated": 0.5, "high": 0.25, "extreme": 0.1}.get(dd.get("band"), 0.6)
    rec = C.get("recession") or {}
    rec_score = _num(rec.get("score"))
    rec_health = 0.7 if rec_score is None else _clamp(1 - rec_score / 100)
    s01 = _clamp(0.5 * risk_on + 0.3 * dd_s + 0.2 * rec_health)
    read_en = f"Downturn risk {mr.get('label', '—')}; drawdown band {dd.get('band', '—')}"
    read_zh = f"下行风险{ {'low':'低','elevated':'偏高','high':'高'}.get(mr.get('label'), mr.get('label') or '—') }；回撤区间{ {'low':'低','elevated':'偏高','high':'高','extreme':'极高'}.get(dd.get('band'), dd.get('band') or '—') }"
    return _component(
        "stress", "Downturn-risk guard", "下行风险护栏", s01, read_en, read_zh,
        [_metric("Macro-risk", "宏观风险", f"{int(score*100)}/100"),
         _metric("Drawdown band", "回撤区间", dd.get("band")),
         _metric("P(>10% / 3mo)", "三月内跌超10%", f"{dd.get('dd10_prob_pct')}%" if dd.get("dd10_prob_pct") is not None else None),
         _metric("Recession", "衰退", rec.get("label"))])


# --------------------------------------------------------------- assembly ----

_HEADLINES = {
    "RISK_ON": ("Risk-on — the tape, breadth and cross-asset signals line up. Trend-following and adding on strength is supported.",
                "风险偏好 — 价格、广度与跨资产信号一致。顺势交易与逢强加仓得到支持。"),
    "MIXED": ("Mixed / transition — the signals disagree. Trade smaller, favour quality, take profits faster; don't position aggressively.",
              "混合 / 转换 — 信号分歧。缩小仓位、偏好质量、更快获利了结；勿激进布局。"),
    "RISK_OFF": ("Risk-off — stress is elevated; defend capital first.",
                 "避险 — 压力升高；优先防守。"),
}
_POSTURE = {
    "RISK_ON": ("Risk-on", "风险偏好"), "MIXED": ("Mixed / transition", "混合 / 转换"),
    "RISK_OFF": ("Risk-off", "避险"),
}
_LABEL = {"RISK_ON": ("Risk-on", "风险偏好"), "MIXED": ("Mixed", "混合"), "RISK_OFF": ("Risk-off", "避险")}
_COLOR = {"RISK_ON": "green", "MIXED": "yellow", "RISK_OFF": "red"}
_VERDICT_ORDER = ["RISK_OFF", "MIXED", "RISK_ON"]


def _verdict_from_score(score: int) -> str:
    if score >= 60:
        return "RISK_ON"
    if score >= 42:
        return "MIXED"
    return "RISK_OFF"


def _cap(verdict: str, ceiling: str) -> str:
    """Lower `verdict` to at most `ceiling` (using risk-off < mixed < risk-on)."""
    return verdict if _VERDICT_ORDER.index(verdict) <= _VERDICT_ORDER.index(ceiling) else ceiling


# Risk Radar bands → plain Chinese + a one-line "what to do" (English, 中文).
_RADAR_ZH = {"calm": "平静", "watch": "观察", "caution": "警戒", "elevated": "升高", "risk-off": "避险"}
_RADAR_DO = {
    "calm": ("Normal exposure.", "正常仓位。"),
    "watch": ("A risk is building — stay normal, just watch it.", "风险在积累 — 保持正常，留意即可。"),
    "caution": ("Trim chasing; favour good entries over extended leaders.", "减少追高；择优入场而非追逐已延展的龙头。"),
    "elevated": ("De-risk: cut size, don't add to froth, honour stops.", "降险：减仓、勿加注泡沫、严守止损。"),
    "risk-off": ("Protect capital: raise cash, no new chases.", "保住本金：提高现金、勿追新高。"),
}

# ---- amplification calibration (per-corroborator pull, in score points) ----------------
# The confluence multiplier started as a flat 6 pts per corroborator. These are now an
# OVERLAY that engine/market_state_tune.py rewrites within bounds from the forward-grade
# scorecard — so a corroborator that reliably precedes drawdowns pulls harder and one that
# does not gets pruned toward zero, WITHOUT a human re-picking the weights. Absent file =>
# the original flat-6 behaviour. engine.market_state_tune and the live engine share
# _ceiling_for so the backtest can never diverge from production.
CORROBORATORS = ("conjunction", "two_plus_scares", "complacency", "breadth_div",
                 "drawdown_band", "systemic_stress", "turning_point")
_DEFAULT_WEIGHTS = {k: 6.0 for k in CORROBORATORS}
_DEFAULT_CALIB = {"weights": dict(_DEFAULT_WEIGHTS),
                  "base": {"caution": 56, "elevated": 38, "risk-off": 26},
                  "severe_bump": 10, "floor": 12}
_WEIGHT_BOUNDS = (0.0, 12.0)        # 0 = pruned, 12 = double the default pull
# BOUNDED, DO-NO-HARM applies to EVERY overlay field, not just weights (audit 2026-07-29).
# `weights` were clamped; `base`, `severe_bump` and `floor` were applied verbatim — an overlay
# could ship base={"caution": -500} or floor="x" and the ceiling would go negative or raise
# inside the live override. These bounds are the SCORE SCALE itself (0-100) plus the structural
# ordering the three bases must satisfy — deliberately NOT new tuning magnitudes, so no
# calibration value moves: today's 56/38/26, bump 10, floor 12 all sit inside them untouched.
_SCORE_BOUNDS = (0.0, 100.0)
_BASE_ORDER = ("caution", "elevated", "risk-off")   # must be monotonically non-increasing


def _bounded(v, lo: float, hi: float):
    """float(v) clamped to [lo, hi]; None when v is not a finite number."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return min(hi, max(lo, f))


def _ms_calib(root=None) -> dict:
    """Read the amplification overlay (data/market_state/calibration.json); fall back to the
    flat-6 defaults. Never raises — a bad file degrades to defaults.

    EVERY overlay field is bounded (see _SCORE_BOUNDS / _BASE_ORDER): non-numeric or non-finite
    values are DROPPED (the default survives) rather than propagated, scores are clamped to the
    0-100 scale, and the three state bases are forced monotonically non-increasing so an overlay
    can never make 'risk-off' cap HIGHER than 'caution'."""
    c = {"weights": dict(_DEFAULT_WEIGHTS), "base": dict(_DEFAULT_CALIB["base"]),
         "severe_bump": _DEFAULT_CALIB["severe_bump"], "floor": _DEFAULT_CALIB["floor"]}
    try:
        from lib import config
        from pathlib import Path
        base_dir = config.data_dir() if root is None else (Path(root) / "data")
        p = base_dir / "market_state" / "calibration.json"
        if p.exists():
            ov = json.loads(p.read_text())
            for k, v in (ov.get("weights") or {}).items():
                if k in _DEFAULT_WEIGHTS:
                    b = _bounded(v, *_WEIGHT_BOUNDS)
                    if b is not None:
                        c["weights"][k] = b
            for k, v in (ov.get("base") or {}).items():
                if k in c["base"]:
                    b = _bounded(v, *_SCORE_BOUNDS)
                    if b is not None:
                        c["base"][k] = b
            # a looser state must never cap lower than a tighter one
            prev = None
            for k in _BASE_ORDER:
                if k in c["base"]:
                    if prev is not None:
                        c["base"][k] = min(c["base"][k], prev)
                    prev = c["base"][k]
            for k in ("severe_bump", "floor"):
                if ov.get(k) is not None:
                    b = _bounded(ov[k], *_SCORE_BOUNDS)
                    if b is not None:
                        c[k] = b
    except Exception:  # noqa: BLE001
        pass
    return c


def _ceiling_for(state: str, severe_gated: bool, amp_keys, calib: dict) -> int | None:
    """The amplified score ceiling for a radar-active state under `calib`. Shared by the live
    override and the tuner's do-no-harm backtest so they can never disagree. None if calm."""
    if state not in ("caution", "elevated", "risk-off"):
        return None
    base = calib["base"].get(state, _DEFAULT_CALIB["base"][state])
    if severe_gated:
        base -= calib.get("severe_bump", 10)
    pull = sum(calib["weights"].get(k, 6.0) for k in (amp_keys or []))
    return int(max(calib.get("floor", 12), round(base - pull)))


def _rr_scorecard_track(market_key: str) -> dict | None:
    """Load the MARKET block from data/risk_radar/scorecard.json for ``market_key``
    (one of "us"/"cn"/"hk"/"ca") and return it as-is, or None if the file is absent,
    unreadable, or the market key is missing.  Fail-soft: never raises."""
    try:
        from lib import config  # noqa: PLC0415
        p = config.data_dir() / "risk_radar" / "scorecard.json"
        if not p.exists():
            return None
        blob = json.loads(p.read_text(encoding="utf-8"))
        markets = blob.get("markets") or {}
        return markets.get(market_key) or None
    except Exception:  # noqa: BLE001
        return None


def _radar_to_rd(rr: dict) -> dict:
    """Map a risk_radar.v2 (US) / risk_radar_intl.v1 (CN/HK/CA) payload into the `rd` dict
    the shared .rrx Risk-Radar card consumes. Pure; the amplifying US override and the
    display-only override both build on it. `amp`/`ceiling` default to off (the US override
    fills them in when the radar is loud)."""
    state = rr.get("state")
    top = _num(rr.get("top_score"))
    dp = rr.get("drawdown_prob") or {}
    _mkt = rr.get("market") or "us"
    return {
        "state": state,
        "top_score": round(top) if top is not None else None,
        "label_en": rr.get("dominant_label_en") or "calm",
        "label_zh": rr.get("dominant_label_zh") or "平静",
        "state_zh": _RADAR_ZH.get(state, state or ""),
        "do_en": _RADAR_DO.get(state, ("", ""))[0],
        "do_zh": _RADAR_DO.get(state, ("", ""))[1],
        "gross": _num(rr.get("gross_factor")),
        "dd5": _num(dp.get("h5")), "dd10": _num(dp.get("h10")), "dd21": _num(dp.get("h21")),
        "dd_lift": _num(dp.get("lift_h21")),
        # unconditional "normal" base rates per horizon — the reference the radar card draws the
        # escalating odds against (so a small near-term bar can't be misread as "no risk").
        "dd_base": {"h5": _num(dp.get("base_h5")), "h10": _num(dp.get("base_h10")),
                    "h21": _num(dp.get("base_h21"))},
        "is_loud": state in ("caution", "elevated", "risk-off"),
        # carried so the board can pass ms.radar.scares to the card (the US page passes
        # latest.risk_radar.scares separately, so this is harmless duplication there).
        "scares": rr.get("scares") or [],
        # the radar's own forward-grade scorecard (engine/risk_radar_intl_audit) — drives the
        # card's "self-audit" line. None on the US radar (which logs via market_state_audit).
        "forward_log": rr.get("forward_log"),
        # election-cycle MODULATOR (engine/election_cycle.py) — display chip + sizing prior; only
        # set on the US radar (the intl radars carry no midterm prior — the backtest refuted it).
        "cycle": rr.get("cycle_context"),
        # RC-R11 washout counter-read — display-tier context chip beside the banner (US radar only).
        "counterread": rr.get("counterread"),
        "amp": 0, "amp_keys": [], "amp_flags_en": [], "amp_flags_zh": [],
        "severe_gated": False, "ceiling": None,
        # amplification-provenance defaults (the US override fills them in when the radar is
        # loud); present here so every consumer can read them unconditionally.
        "amp_unavailable": [], "amp_unavailable_keys": [], "amp_n_checked": 0,
        "amp_available": 0, "ceiling_base": None, "ceiling_severe_bump": 0,
        "ceiling_amp_pull": 0.0, "ceiling_floor": None,
        # display-only DE-ESCALATION read ("risk-off may be ending"); the US override fills it in
        # below from the radar trajectory + the liquidity tide. Stays None on the intl radars and
        # the no-source calm radar, so the card's {% if rd.recovery %} guard simply skips it.
        "recovery": None,
        # forward-ledger track record for this market (data/risk_radar/scorecard.json).
        # Display-only; None when the scorecard is absent (first build, engine builder not yet run).
        # The card template guards with {% if radar.track is defined and radar.track %}.
        "track": _rr_scorecard_track(_mkt),
    }


# Base score ceilings the intl radar applies ONLY once its own graded log validates it. No
# corroborator multiplier — China/HK/Canada lack the US conditions gauges (complacency /
# systemic_stress / turning_point), so radar intensity alone caps the verdict.
_RADAR_INTL_CEIL = {"caution": 56, "elevated": 38, "risk-off": 26}
_RADAR_MARKET = {"cn": ("China", "中国"), "hk": ("Hong Kong", "香港"), "ca": ("Canada", "加拿大")}


def _radar_override_intl(latest: dict, overrides: list) -> dict:
    """Radar mapping for the China/HK/Canada radars (engine/risk_radar_intl.py). Always renders
    the .rrx card from latest['risk_radar']; HARD-FORCES the Market-State verdict (caps the
    score) ONLY once that market's own forward-grade log has matured and cleared the bar
    (rr['can_force'], set by engine/risk_radar_intl_audit.scorecard). Until then it is pure
    display — accountable by construction, never trusted on faith."""
    rr = latest.get("risk_radar") or {}
    out = _radar_to_rd(rr)
    state = rr.get("state")

    # DE-ESCALATION read (display-only) for the CN/HK/CA radar — has this market's risk peaked +
    # rolled over while the global liquidity tide (Fed/PBoC/global CB) turns supportive? Never
    # touches the ceiling below. See engine/risk_radar_recovery.py.
    try:
        from engine import risk_radar_recovery
        out["recovery"] = risk_radar_recovery.assess(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("risk_radar_intl recovery assess failed: %s", e)
        out["recovery"] = None

    if rr.get("can_force") and state in ("caution", "elevated", "risk-off"):
        ceil = _RADAR_INTL_CEIL.get(state)
        out["ceiling"] = ceil
        mkt_en, mkt_zh = _RADAR_MARKET.get(rr.get("market"), ("", ""))
        if ceil is not None and ceil < 42:
            overrides.append({"kind": "radar",
                "note_en": f"{mkt_en} Risk Radar forces Risk-off.",
                "note_zh": f"{mkt_zh}风险雷达强制为「避险」。"})
        else:
            overrides.append({"kind": "radar",
                "note_en": "Risk Radar caps at Mixed.",
                "note_zh": "风险雷达封顶为「混合」。"})
    return out


def _amp_unavailable(latest: dict) -> list:
    """Which confluence corroborators are STRUCTURALLY UNABLE to fire on the current tape.

    Audit 2026-07-29: the amplification ladder reads as "N of 7 risk gauges are flashing", but two
    of the seven are gated on a CALM-tape precondition and therefore DISARM in exactly the decline
    they would be most wanted for — complacency needs a calm surface (VIX percentile below its calm
    cut or VIX term in contango) and breadth_div needs the index within ~3% of its 1y high. That is
    why the amplified ceiling could RISE 50 -> 56 on a down day: the tape falling switched two
    corroborators off. Emitting the disarmed set (machine-readable + plain-word notes) lets a
    surface say "5 of 7 gauges could speak today" instead of implying a 7-gauge all-clear.

    Reads the SAME config keys engine/conditions.py computes the gauges from, so the note can
    never claim a threshold the gauge does not use. Never raises."""
    out = []
    try:
        C = latest.get("conditions") or {}
        cmp_ = C.get("complacency") or {}
        mcfg = {}
        try:
            from lib import config  # noqa: PLC0415
            mcfg = (config.load()["engine"]["conditions"].get("complacency") or {})
        except Exception:  # noqa: BLE001
            mcfg = {}
        vix_calm = mcfg.get("vix_calm_pctile", 0.25)
        contango = mcfg.get("contango_calm", 0.95)
        prox_thr = mcfg.get("breadth_high_prox", 0.97)

        calm_n = _num(cmp_.get("calm"))
        if calm_n is not None and calm_n < 1:
            out.append({
                "key": "complacency", "reason": "requires_calm_surface",
                "note_en": (f"Complacency cannot fire: it needs a calm surface — VIX below its "
                            f"{int(vix_calm*100)}th-percentile calm cut or VIX term under "
                            f"{contango} (contango). Neither holds, so this gauge is silent by "
                            f"construction, not reassuring."),
                "note_zh": (f"「自满」无法触发：需要平静的表面——VIX 低于 {int(vix_calm*100)} "
                            f"百分位，或 VIX 期限结构低于 {contango}（正向）。两者皆不满足，"
                            f"因此该指标是结构性沉默，并非安全信号。"),
            })
        prox = _num(cmp_.get("spy_high_prox"))
        if prox is not None and prox < float(prox_thr):
            out.append({
                "key": "breadth_div", "reason": "index_not_near_high",
                "note_en": (f"Breadth divergence cannot fire: it is only defined within "
                            f"{prox_thr:.0%} of the 1-year high and the index is at "
                            f"{prox:.0%}. Silent by construction, not confirming."),
                "note_zh": (f"「广度背离」无法触发：仅在距一年高点 {prox_thr:.0%} 以内才成立，"
                            f"当前为 {prox:.0%}。属结构性沉默，并非确认。"),
            })
        if (C.get("drawdown_risk") or {}).get("band") is None:
            out.append({
                "key": "drawdown_band", "reason": "no_current_read",
                "note_en": "Drawdown-risk band has no current read, so it cannot corroborate.",
                "note_zh": "回撤风险区间暂无读数，无法参与确认。",
            })
        if (C.get("systemic_stress") or {}).get("state") is None:
            out.append({
                "key": "systemic_stress", "reason": "no_current_read",
                "note_en": "Systemic stress has no current read, so it cannot corroborate.",
                "note_zh": "系统性压力暂无读数，无法参与确认。",
            })
        if latest.get("turning_point") is None:
            out.append({
                "key": "turning_point", "reason": "no_current_read",
                "note_en": "The turning-point read is unavailable, so it cannot corroborate.",
                "note_zh": "转折点读数暂缺，无法参与确认。",
            })
    except Exception as e:  # noqa: BLE001 — disclosure block, never fatal
        log.warning("market_state amp-availability read failed: %s", e)
    return out


def _radar_override(latest: dict, overrides: list) -> dict:
    """Summarise the Risk Radar (engine/risk_radar.py) for the hero AND, when it is at
    caution or worse, compute an AMPLIFIED score ceiling + push an override note.

    The radar is the HEAVIEST input on this read. An active radar dominates the bullish
    trend/breadth legs rather than being averaged into silence — the "conjunction over
    mean" principle the radar itself is built on (research/RISK_ENGINE_V2_FINDINGS.md).
    Two things scale how hard it pulls the verdict down:
      • intensity — its gated state, plus a SEVERE-BUT-GATED bump when the radar's own
        un-gated read is worse than its label (the context gate keeps the label quiet
        until the broad tape breaks, but the underlying drawdown risk is already high);
      • a CONFLUENCE MULTIPLIER — every OTHER risk gauge that is flashing at the same
        time (a second scare-type, complacency/fragility, a stress band) drops the
        ceiling further, so a confluence drives the verdict deep into risk-off even
        while VIX and trend still look calm.
    The caller applies the returned `ceiling` to the 0-100 score."""
    rr = latest.get("risk_radar") or {}
    state = rr.get("state")
    top = _num(rr.get("top_score"))
    ungated = rr.get("state_ungated") or state
    out = _radar_to_rd(rr)

    # DE-ESCALATION read (display-only): has risk peaked + are the pullback odds rolling over while
    # the liquidity tide turns supportive? Computed at EVERY state (also calm/watch) so the "risk-off
    # may be ending" panel persists through the cool-down. It NEVER touches the ceiling/amp/verdict
    # below — the radar's one-directional guardrail is untouched. See engine/risk_radar_recovery.py.
    try:
        from engine import risk_radar_recovery
        out["recovery"] = risk_radar_recovery.assess(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("risk_radar recovery assess failed: %s", e)
        out["recovery"] = None

    if state not in ("caution", "elevated", "risk-off"):
        return out

    # ---- confluence multiplier: the OTHER risk gauges flashing right now. Each carries a
    # STABLE key so the forward-grade log (engine/market_state_audit.py) can measure which
    # corroborators actually precede drawdowns and prune the ones that don't. ----
    C = latest.get("conditions") or {}
    cmp_ = C.get("complacency") or {}
    nhot = sum(1 for s in (rr.get("scares") or [])
               if s.get("band") in ("caution", "elevated", "risk-off"))
    _checks = [
        ("conjunction", bool(rr.get("conjunction")),
         "several scare-types firing together", "多个风险类型同时触发"),
        ("two_plus_scares", nhot >= 2,
         f"{nhot} risk types elevated", f"{nhot} 类风险升高"),
        ("complacency", (cmp_.get("state") or "") in ("watch", "high"),
         "complacency — calm VIX but fragile", "自满 — VIX 平静但脆弱"),
        ("breadth_div", bool(cmp_.get("breadth_div")),
         "narrowing breadth / leadership", "广度／领导性收窄"),
        ("drawdown_band", (C.get("drawdown_risk") or {}).get("band") in ("elevated", "high", "extreme"),
         "drawdown-risk band rising", "回撤风险区间上升"),
        ("systemic_stress", (C.get("systemic_stress") or {}).get("state") in ("elevated", "acute"),
         "systemic stress building", "系统性压力累积"),
        ("turning_point", bool((latest.get("turning_point") or {}).get("present")),
         "fragile one-factor tape", "脆弱的单因子行情"),
    ]
    keys = [k for k, on, _e, _z in _checks if on]
    flags_en = [e for _k, on, e, _z in _checks if on]
    flags_zh = [z for _k, on, _e, z in _checks if on]
    amp = len(keys)

    # severe-but-gated: un-gated read worse than the label, or the top scare screaming
    severe_gated = state == "caution" and (
        ungated in ("elevated", "risk-off") or (top is not None and top >= 85))

    # the amplified ceiling, using the (auto-tuned) per-corroborator weights
    calib = _ms_calib()
    ceiling = _ceiling_for(state, severe_gated, keys, calib)

    # which corroborators are structurally DISARMED on this tape (see _amp_unavailable) — a
    # silent gauge is not a quiet one, and the ladder's "N gauges flashing" needs that context.
    unavail = _amp_unavailable(latest)
    out.update(amp=amp, amp_keys=keys, amp_flags_en=flags_en, amp_flags_zh=flags_zh,
               severe_gated=severe_gated, ceiling=ceiling,
               amp_n_checked=len(_checks),
               amp_unavailable=unavail,
               amp_unavailable_keys=[u["key"] for u in unavail],
               amp_available=len(_checks) - len(unavail),
               ceiling_base=calib["base"].get(state),
               ceiling_severe_bump=(calib.get("severe_bump", 10) if severe_gated else 0),
               ceiling_amp_pull=sum(calib["weights"].get(k, 6.0) for k in keys),
               ceiling_floor=calib.get("floor", 12))

    # The Risk Radar banner rendered directly ABOVE this verdict already states the radar's
    # name, gated state, score and amp-flag breakdown. So the override note here stays lean —
    # it only explains the CONSEQUENCE (forced / capped) plus the severe-but-gated nuance the
    # banner doesn't surface. Restating "Risk Radar {state} ({score}/100) amplified by N…"
    # duplicated the banner headline word-for-word.
    if ceiling < 42:
        overrides.append({"kind": "radar",
            "note_en": "Risk Radar forces Risk-off.",
            "note_zh": "风险雷达强制为「避险」。"})
    else:
        overrides.append({"kind": "radar",
            "note_en": "Capped at Mixed by the Risk Radar above.",
            "note_zh": "由上方风险雷达封顶为「混合」。"})
    return out


def _calm_radar() -> dict:
    """The neutral radar payload for a market with no Risk-Radar source — the board
    simply omits the banner ({% if MS.radar.state %})."""
    return {"state": None, "top_score": None, "label_en": "calm", "label_zh": "平静",
            "state_zh": "", "do_en": "", "do_zh": "", "gross": None,
            "dd5": None, "dd10": None, "dd21": None, "dd_lift": None,
            "dd_base": {"h5": None, "h10": None, "h21": None}, "is_loud": False,
            "amp": 0, "amp_keys": [], "amp_flags_en": [], "amp_flags_zh": [],
            "severe_gated": False, "ceiling": None, "recovery": None, "track": None,
            "amp_unavailable": [], "amp_unavailable_keys": [], "amp_n_checked": 0,
            "amp_available": 0, "ceiling_base": None, "ceiling_severe_bump": 0,
            "ceiling_amp_pull": 0.0, "ceiling_floor": None}


# The default (US) profile — every field reproduces today's hardcoded behaviour, so
# market_state_snapshot(latest, frame, alerts) with no profile is byte-identical.
US_PROFILE = MarketProfile(
    key="us",
    indices=tuple(_INDEXES),
    tape_noun_en="US indices", tape_noun_zh="美股指数",
    component_readers=(_comp_risk, _comp_vol, _comp_breadth, _comp_liquidity, _comp_stress),
    radar_override=_radar_override,
    overrides=frozenset({"alert_act", "new_regime", "stress_band", "dislocation"}),
)


def market_state_snapshot(latest: dict, frame=None, alerts: list | None = None,
                          profile: "MarketProfile | None" = None) -> dict | None:
    """Blend the live signal legs into a 0-100 risk-on score + Green/Yellow/Red
    verdict. DISPLAY-ONLY; returns None only if nothing at all resolves.

    `profile` selects the market (indices, conditions readers, radar source, which
    overrides apply); defaults to US_PROFILE so existing callers are unchanged."""
    profile = profile or US_PROFILE
    try:
        if not isinstance(latest, dict):
            return None
        tape, trend_s = _build_tape(frame, profile.indices)
        comps = []
        if trend_s is not None:
            comps.append(_component(
                "trend", "Trend & technicals", "趋势与技术", trend_s,
                _tape_read_en(tape, profile.tape_noun_en),
                _tape_read_zh(tape, profile.tape_noun_zh), [], mean=(2 * trend_s - 1)))
        for fn in profile.component_readers:
            c = fn(latest)
            if c:
                comps.append(c)
        comps = [c for c in comps if c]
        if not comps:
            return None

        num = sum(c["score"] / 100 * c["weight"] for c in comps)
        den = sum(c["weight"] for c in comps)
        raw_score = int(round(100 * num / den)) if den else 50
        verdict = _verdict_from_score(raw_score)

        # ---- early-warning overrides (cap or force), each gated by the profile ----
        overrides = []
        ov = profile.overrides
        sev = {(a.get("severity") if isinstance(a, dict) else None) for a in (alerts or [])}
        if "alert_act" in ov and "act" in sev:
            verdict = _cap(verdict, "MIXED")
            overrides.append({"kind": "alert",
                              "note_en": "An act-level alert is firing — capped at Mixed pending review.",
                              "note_zh": "有行动级警报触发 — 暂封顶为「混合」待复核。"})
        if "new_regime" in ov and (latest.get("transition_state") or "") == "NEW_REGIME":
            verdict = _cap(verdict, "MIXED")
            overrides.append({"kind": "regime",
                              "note_en": "The regime just flipped — capped at Mixed until it settles.",
                              "note_zh": "周期刚刚翻转 — 在其稳定前封顶为「混合」。"})
        C = latest.get("conditions") or {}
        dd_band = (C.get("drawdown_risk") or {}).get("band")
        ss_state = (C.get("systemic_stress") or {}).get("state")
        if "stress_band" in ov and (dd_band in ("high", "extreme") or ss_state == "acute"):
            verdict = "RISK_OFF"
            overrides.append({"kind": "stress",
                              "note_en": "Elevated drawdown / systemic-stress band — forced to Risk-off.",
                              "note_zh": "回撤／系统性压力区间偏高 — 强制为「避险」。"})
        dl = latest.get("dislocation") or {}
        if "dislocation" in ov and dl.get("dislocation_active") and dl.get("verdict") == "stand_aside":
            verdict = "RISK_OFF"
            overrides.append({"kind": "dislocation",
                              "note_en": "A falling-knife dislocation is live — forced to Risk-off.",
                              "note_zh": "接飞刀式错位正在发生 — 强制为「避险」。"})

        # ---- Risk Radar override + confluence amplification (runs LAST so it wins) ----
        # The radar is the heaviest guard on this read. _radar_override returns an
        # amplified score ceiling (intensity × how many other risk gauges are flashing);
        # an active radar therefore dominates the bullish legs instead of being averaged
        # into silence, and a confluence pushes the verdict deep into risk-off even while
        # VIX and trend still look calm. Markets without a radar source skip this entirely.
        radar = profile.radar_override(latest, overrides) if profile.radar_override else _calm_radar()

        # Keep the 0-100 dial honest: a forced verdict pulls the displayed score into its
        # own band, then the radar's amplified ceiling pulls it lower still (never higher).
        #
        # PROVENANCE (audit 2026-07-29): on every radar-capped day the number the page shows is
        # the CEILING CONSTANT (base − amp pull − severe bump), not a measurement of the tape —
        # across 21 logged sessions the blend never printed below 61 while the displayed score
        # never rose above 56. raw_score was already in the payload but nothing said WHICH of the
        # two the dial was showing, so a constant read as a reading. score_source / score_ceiling
        # / capped / score_caps make the distinction machine-readable, so a surface can draw the
        # blend and the cap as two separate marks. No cap value changes here.
        score = raw_score
        caps_applied = []
        if verdict == "RISK_OFF":
            if 41 < score:
                caps_applied.append({"kind": "verdict_force", "limit": 41,
                                     "note_en": "forced into the Risk-off band by an override",
                                     "note_zh": "被覆盖规则强制进入「避险」区间"})
            score = min(score, 41)
        elif verdict == "MIXED":
            if 59 < score:
                caps_applied.append({"kind": "verdict_cap", "limit": 59,
                                     "note_en": "capped into the Mixed band by an override",
                                     "note_zh": "被覆盖规则封顶于「混合」区间"})
            score = min(score, 59)
        ceiling = radar.get("ceiling")
        if ceiling is not None:
            if ceiling < score:
                caps_applied.append({"kind": "radar_ceiling", "limit": ceiling,
                                     "note_en": "held at the Risk Radar's amplified ceiling",
                                     "note_zh": "受风险雷达放大后的上限约束"})
            score = min(score, ceiling)
        # the penalised score now drives the verdict; the radar can only make it more
        # risk-off than the prior overrides, never less.
        verdict = _cap(verdict, _verdict_from_score(score))

        binding = min(caps_applied, key=lambda c: c["limit"], default=None)
        score_source = ("blend" if binding is None else
                        {"radar_ceiling": "radar_ceiling",
                         "verdict_force": "hard_force",
                         "verdict_cap": "verdict_cap"}[binding["kind"]])

        flip_en, flip_zh = _flip_text(comps, verdict, raw_score=raw_score,
                                      radar=radar, overrides=overrides)
        return {
            "schema": "market_state.v1",
            "asof": latest.get("date"),
            "score": score,
            "raw_score": raw_score,
            # is the dial showing the blend, or a constant that overrode it?
            "score_source": score_source,
            "capped": bool(caps_applied),
            "score_ceiling": ceiling,
            "score_caps": caps_applied,
            "score_gap": (None if not caps_applied else int(raw_score - score)),
            "radar": radar,
            "verdict": verdict,
            "color": _COLOR[verdict],
            "label_en": _LABEL[verdict][0], "label_zh": _LABEL[verdict][1],
            "posture_en": _POSTURE[verdict][0], "posture_zh": _POSTURE[verdict][1],
            "headline_en": _HEADLINES[verdict][0], "headline_zh": _HEADLINES[verdict][1],
            "components": comps,
            "mtf": tape,
            "overrides": overrides,
            "flip_en": flip_en, "flip_zh": flip_zh,
            "alerts_count": len([a for a in (alerts or []) if a]),
            "market": profile.key,
            "caveat_en": profile.caveat_en, "caveat_zh": profile.caveat_zh,
            "is_display_only": True,
            # per-input last-print dates (engine/conditions._input_vintages), carried through so
            # persist()'s freshness stamp can be derived from real store vintages instead of the
            # frame calendar it used to certify itself with. Empty on markets whose conditions
            # reader does not emit them.
            "input_vintages": ((latest.get("conditions") or {}).get("vintages") or {}),
            "stale_inputs": ((latest.get("conditions") or {}).get("stale_inputs") or []),
            # which legs are running on fewer inputs than their label implies
            "degraded_components": [c["key"] for c in comps if c.get("degraded")],
        }
    except Exception as e:  # noqa: BLE001 — additive panel, never fatal
        log.warning("market_state snapshot failed: %s", e)
        return None


def _tape_read_en(tape, noun: str = "US indices") -> str:
    if not tape:
        return "Broad-market tape unavailable."
    ups = sum(1 for r in tape["indices"] if r["mean"] >= 0.34)
    n = len(tape["indices"])
    lead = ", ".join(r["confluence_en"].lower() for r in tape["indices"][:3])
    return f"{ups}/{n} {noun} in an uptrend across timeframes ({lead})."


def _tape_read_zh(tape, noun: str = "美股指数") -> str:
    if not tape:
        return "大盘多周期数据暂缺。"
    ups = sum(1 for r in tape["indices"] if r["mean"] >= 0.34)
    n = len(tape["indices"])
    return f"{ups}/{n} 个{noun}多周期呈上升趋势。"


# ---- "what tips this" — the binding-constraint machinery ------------------------------------
# Score cuts, MIRRORING _verdict_from_score: RISK_ON >= 60, MIXED >= 42, else RISK_OFF.
_FLIP_UP_TARGET = {"MIXED": 60, "RISK_OFF": 42}     # score needed for the next-BETTER verdict
_FLIP_DOWN_TARGET = {"RISK_ON": 59, "MIXED": 41}    # score at/below which the next-WORSE prints
# Which cap each override kind puts on the 0-100 dial — mirrors market_state_snapshot's own
# min() chain, so the flip line can name the constraint that is actually holding the score.
_OVERRIDE_LIMIT = {"alert": 59, "regime": 59, "stress": 41, "dislocation": 41}
_OVERRIDE_CLAIM = {
    "alert": ("the act-level alert clears", "行动级警报解除"),
    "regime": ("the fresh regime flip settles", "新周期企稳"),
    "stress": ("the drawdown / systemic-stress band comes back down", "回撤／系统性压力区间回落"),
    "dislocation": ("the falling-knife dislocation ends", "接飞刀式错位结束"),
}
# prefix + target-tier wording per (verdict, direction). zh names the target TIERS (偏多/避险),
# never colours: under the zh 红涨绿跌 swap the "green" tier paints RED on the board.
_FLIP_SHAPE = {
    ("MIXED", 1): ("→ Green if ", "偏多"),
    ("MIXED", -1): ("→ Red if ", "避险"),
    ("RISK_ON", -1): ("→ Mixed if ", "混合"),
    ("RISK_OFF", 1): ("→ Mixed when ", "混合"),
}


def _flip_constraints(radar: dict | None, overrides: list | None) -> list:
    """Every cap currently holding the 0-100 dial down, as (limit, claim_en, claim_zh). These are
    the things the blend CANNOT out-run — naming one is the only honest upside claim when it sits
    below the band the flip line is promising."""
    out = []
    for o in overrides or []:
        lim = _OVERRIDE_LIMIT.get((o or {}).get("kind"))
        if lim is not None:
            en, zh = _OVERRIDE_CLAIM[o["kind"]]
            out.append((float(lim), en, zh))
    ceil = _num((radar or {}).get("ceiling"))
    if ceil is not None:
        st = (radar or {}).get("state") or "caution"
        top = (radar or {}).get("top_score")
        now_en = f" (now {top}/100)" if top is not None else ""
        now_zh = f"（现 {top}/100）" if top is not None else ""
        out.append((float(ceil),
                    f"the Risk Radar leaves {st}{now_en}",
                    f"风险雷达退出{_RADAR_ZH.get(st, st)}{now_zh}"))
    return out


def _legs_to_cross(comps: list, raw_score, target: float, direction: int) -> list | None:
    """The smallest set of legs (most room first) whose FULL move carries the BLEND across
    `target`: direction +1 = every named leg to 100, -1 = to 0. None when even all legs together
    cannot get there; [] when the blend is already across. Weights are renormalised over the legs
    that resolved, exactly as market_state_snapshot blends them."""
    den = sum(float(c.get("weight") or 0.0) for c in comps)
    if den <= 0 or raw_score is None:
        return None
    need = (float(target) - float(raw_score)) if direction > 0 else (float(raw_score) - float(target))
    if need <= 0:
        return []
    room = []
    for c in comps:
        w = float(c.get("weight") or 0.0) / den
        s = float(c.get("score") or 0.0)
        room.append((((100.0 - s) * w) if direction > 0 else (s * w), c))
    room.sort(key=lambda t: -t[0])
    got, picked = 0.0, []
    for r, c in room:
        if r <= 0:
            continue
        picked.append(c)
        got += r
        if got >= need:
            return picked
    return None


def _legs_claim(legs: list, direction: int, n_total: int) -> tuple[str, str]:
    """Plain-word claim for a leg set. >2 legs stops naming them — "3 of the 6 legs" is the honest
    shape for a move no single reading can deliver."""
    verb_en, verb_zh = ("firms up", "转强") if direction > 0 else ("breaks down", "走坏")
    if len(legs) > 2:
        return (f"{len(legs)} of the {n_total} legs turn together",
                f"{n_total} 项中有 {len(legs)} 项同时反转")
    names_en = " and ".join(c["label_en"].lower() for c in legs)
    names_zh = "与".join(c["label_zh"] for c in legs)
    scores = ", ".join(str(c["score"]) for c in legs)
    scores_zh = "、".join(str(c["score"]) for c in legs)
    if len(legs) == 1:
        return (f"{names_en} {verb_en} (now {scores}/100)",
                f"{names_zh}{verb_zh}（现 {scores_zh}/100）")
    both_en = "both firm up" if direction > 0 else "both break down"
    return (f"{names_en} {both_en} (now {scores}/100)",
            f"{names_zh}同时{verb_zh}（现 {scores_zh}/100）")


def _radar_escalation_claim(radar: dict | None, target: float) -> tuple[str, str] | None:
    """Would the radar's NEXT-WORSE state on its own drive the score under `target`? Uses the very
    same _ceiling_for the live override uses, so the claim can never diverge from what would
    actually happen. None when the radar is absent, already at its worst, or would not get there."""
    st = (radar or {}).get("state")
    if st not in ("caution", "elevated"):
        return None
    nxt = "elevated" if st == "caution" else "risk-off"
    try:
        ceil = _ceiling_for(nxt, bool((radar or {}).get("severe_gated")),
                            (radar or {}).get("amp_keys") or [], _ms_calib())
    except Exception:  # noqa: BLE001 — claim helper, never fatal
        return None
    if ceil is None or ceil > target:
        return None
    return (f"the Risk Radar escalates to {nxt}",
            f"风险雷达升级至{_RADAR_ZH.get(nxt, nxt)}")


def _flip_clause(verdict: str, direction: int, claim: tuple[str, str]) -> tuple[str, str]:
    prefix, tier_zh = _FLIP_SHAPE[(verdict, direction)]
    return (f"{prefix}{claim[0]}.", f"→ 若{claim[1]}，则转「{tier_zh}」。")


def _flip_text(comps: list, verdict: str, *, raw_score=None, radar: dict | None = None,
               overrides: list | None = None) -> tuple[str, str]:
    """A falsifiable 'what tips this' line — every clause must name something that could
    ARITHMETICALLY move the verdict.

    IMPOSSIBLE-CLAIM REPAIR (audit 2026-07-29). This was built purely off the weakest/strongest
    leg and never saw raw_score, the radar ceiling, or the hard-force overrides — so on a
    radar-capped day (12 of 21 logged sessions) it printed

        "→ Green if risk appetite firms up (now 42/100); → Red if it deteriorates further."

    with BOTH clauses unreachable. That leg carries 0.18 of a den-1.0 blend: driving it to 100
    lifts the blend 63 -> 73 and the DISPLAYED score stays min(73, ceiling 56) = 56, still Mixed;
    driving it to 0 pulls the blend only to 55, nowhere near the 41 the Risk-off band needs. The
    line now derives from whichever constraint actually BINDS — the radar ceiling or a hard-force
    override when one of those holds the dial, otherwise the specific legs whose full move really
    does cross the boundary, and the radar's own next-state escalation when that is the shorter
    path down. Called with `comps` alone (no raw_score) it keeps the legacy weakest-leg wording:
    the arithmetic is not available to check, so no claim is manufactured. EN + ZH.
    """
    if not comps:
        return "", ""
    weakest = min(comps, key=lambda c: c["score"])
    strongest = max(comps, key=lambda c: c["score"])
    have_math = (raw_score is not None
                 and sum(float(c.get("weight") or 0.0) for c in comps) > 0)
    if not have_math:
        # legacy shape — unchanged wording, unchanged prefixes (scripts/check_ms_board_coherence)
        if verdict == "RISK_ON":
            return (f"→ Mixed if {weakest['label_en'].lower()} rolls over "
                    f"(now {weakest['score']}/100, the weakest leg).",
                    f"→ 若{weakest['label_zh']}转弱（现 {weakest['score']}/100，最弱项）则转为「混合」。")
        if verdict == "RISK_OFF":
            return (f"→ Mixed when {strongest['label_en'].lower()} stabilises and stress fades.",
                    f"→ 待{strongest['label_zh']}企稳且压力护栏解除后转为「混合」。")
        return (f"→ Green if {weakest['label_en'].lower()} firms up (now {weakest['score']}/100); "
                f"→ Red if it deteriorates further.",
                f"→ 若{weakest['label_zh']}转强（现 {weakest['score']}/100）则转「偏多」；"
                f"进一步恶化则转「避险」。")

    caps = _flip_constraints(radar, overrides)
    n = len(comps)
    parts_en, parts_zh = [], []

    # ---- UPSIDE: the next-better verdict ------------------------------------------------
    tgt = _FLIP_UP_TARGET.get(verdict)
    if tgt is not None:
        # a cap sitting BELOW the target is what binds — the blend cannot out-run it
        binding = min((c for c in caps if c[0] < tgt), key=lambda c: c[0], default=None)
        claim = None
        if binding is not None:
            claim = (binding[1], binding[2])
        else:
            legs = _legs_to_cross(comps, raw_score, tgt, 1)
            if legs:
                claim = _legs_claim(legs, 1, n)
        if claim:
            en, zh = _flip_clause(verdict, 1, claim)
            parts_en.append(en)
            parts_zh.append(zh)

    # ---- DOWNSIDE: the next-worse verdict -----------------------------------------------
    tgt = _FLIP_DOWN_TARGET.get(verdict)
    if tgt is not None:
        legs = _legs_to_cross(comps, raw_score, tgt, -1)
        esc = _radar_escalation_claim(radar, tgt)
        # prefer whichever route needs FEWER independent things to happen; the radar escalating
        # is one move, so it wins over any multi-leg breakdown.
        claim = None
        if esc is not None and (legs is None or len(legs) > 1):
            claim = esc
        elif legs:
            claim = _legs_claim(legs, -1, n)
        elif esc is not None:
            claim = esc
        if claim:
            en, zh = _flip_clause(verdict, -1, claim)
            parts_en.append(en)
            parts_zh.append(zh)

    if not parts_en:
        return "", ""
    return " ".join(parts_en), "".join(parts_zh)


# --------------------------------------------------------------- store ----
# The verdict is the SINGLE SOURCE OF TRUTH for "how risk-on is the market" across the
# whole site. The macro page computes it (with the full feature frame); persisting it here
# lets OTHER pages (engine/sector_central.py) and the intraday live engine
# (scripts/build_risk_state.py) consume the SAME radar-aware verdict instead of each
# re-deriving a (divergent) read — which is exactly how sector_central used to disagree
# with macro.html. Build order already runs build_site before build_sector_central, so the
# file is fresh when the latter reads it. Never raises.
def _store_path(root=None):
    from pathlib import Path
    from lib import config
    base = config.data_dir() if root is None else (Path(root) / "data")
    return base / "market_state" / "latest.json"


def persist(snap: dict | None, root=None, now=None) -> None:
    """Write the canonical market-state snapshot to data/market_state/latest.json.

    Freshness contract (2026-07-07 stale-regime incident):
    - NO-REGRESS: refuse to overwrite a persisted snapshot whose asof is NEWER than the
      incoming one. Two lanes raced that day (a stale scheduled engine run + a manually
      re-dispatched fresh one); ordering luck decided which verdict the site carried.
      Equal asof always overwrites (same-session recomputes are routine).
    - SELF-DECLARING STALENESS: stamp snap["freshness"] against the NYSE calendar
      (lib.nyse_calendar — independent of every price store, so it still fires when the
      whole collection push dies and all stores agree on the stale date), so downstream
      consumers (build_risk_state's nightly backbone, macro.html) can see a stale read
      without cross-referencing the store. Both legs degrade-never-raise."""
    if not snap:
        return
    try:
        p = _store_path(root)
        incoming = str(snap.get("asof") or "")
        try:
            if incoming and p.exists():
                existing = str((json.loads(p.read_text()) or {}).get("asof") or "")
                if existing and incoming < existing:
                    log.warning("market_state persist REFUSED: incoming asof %s < persisted %s "
                                "(no-regress guard)", incoming, existing)
                    return
        except Exception as e:  # noqa: BLE001 — an unreadable existing file never blocks
            log.warning("market_state no-regress check skipped: %s", e)
        try:
            from lib import nyse_calendar
            expected = str(nyse_calendar.expected_last_session(now))
            fresh = {
                "data_asof": incoming or None,
                "expected_asof": expected,
                # PRICE-calendar staleness — unchanged meaning, unchanged consumers.
                "stale": bool(incoming) and incoming < expected,
            }
            # NO LONGER SELF-CERTIFYING (audit 2026-07-29). `stale` above is derived from the
            # snapshot's own asof, which comes from the FRAME calendar — and the frame ffills slow
            # macro series onto trading days, so it reported stale:false on a session where the
            # NFCI print was 12 days old and had already dropped out of the drawdown composite and
            # the credit leg. The per-input vintages (engine/conditions._input_vintages) are real
            # per-store last-print dates, so the stamp now carries a claim it can actually back.
            # Surfacing is the template lane's call; this only makes the truth available.
            v = (snap.get("input_vintages") or {})
            stale_inputs = sorted(k for k, d in v.items() if (d or {}).get("stale"))
            ages = [d.get("age_days") for d in v.values()
                    if isinstance(d, dict) and d.get("age_days") is not None]
            fresh["inputs"] = v
            fresh["stale_inputs"] = stale_inputs
            fresh["any_input_stale"] = bool(stale_inputs)
            fresh["worst_input_age_days"] = (max(ages) if ages else None)
            snap["freshness"] = fresh
        except Exception as e:  # noqa: BLE001 — the stamp is additive, never the gate
            log.warning("market_state freshness stamp skipped: %s", e)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snap, ensure_ascii=False, default=str))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("market_state persist failed: %s", e)


def load_persisted(root=None) -> dict | None:
    """Read the persisted canonical snapshot; None if absent/unreadable."""
    try:
        p = _store_path(root)
        if p.exists():
            return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("market_state load_persisted failed: %s", e)
    return None
