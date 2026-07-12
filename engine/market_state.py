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
    """Per-timeframe arrow read for one index. None if too little history."""
    from engine import cycles  # lazy — keeps module import cheap
    s = close.dropna().astype(float)
    if len(s) < 60:
        return None
    snap = cycles.mtf_snapshot(s)
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

def _component(key, label_en, label_zh, s01, read_en, read_zh, metrics, mean=None):
    if s01 is None:
        return None
    s01 = _clamp(s01)
    if mean is None:
        sign = 1 if s01 >= 0.58 else -1 if s01 <= 0.42 else 0
    else:
        sign = 1 if mean >= 0.25 else -1 if mean <= -0.25 else 0
    return {
        "key": key, "label_en": label_en, "label_zh": label_zh,
        "score": round(s01 * 100), "weight": WEIGHTS[key],
        "tone": _tone_from_score(s01), "arrow": _arrow(sign),
        "read_en": read_en, "read_zh": read_zh,
        "metrics": [m for m in metrics if m and m.get("v") not in (None, "")],
    }


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


def _comp_breadth(latest: dict) -> dict | None:
    C = latest.get("conditions") or {}
    cmp_ = C.get("complacency") or {}
    b200 = _num(cmp_.get("breadth_above200_pctile"))
    if b200 is None:
        return None
    div = bool(cmp_.get("breadth_div"))
    s01 = _clamp(b200 - (0.16 if div else 0.0))
    read_en = f"Breadth {int(b200*100)}%ile of 5y; " + ("a divergence vs price" if div else "confirming price")
    read_zh = f"广度处于五年 {int(b200*100)} 百分位；" + ("与价格背离" if div else "确认价格")
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
    credit += {"loose": 0.12, "tight": -0.14, "neutral": 0.0}.get(fc.get("state"), 0.0)
    credit += {"calm": 0.06, "normal": 0.0, "elevated": -0.12, "acute": -0.28}.get(ss.get("state"), 0.0)
    credit = _clamp(credit)
    s01 = _clamp(0.55 * base_liq + 0.45 * credit)
    zh_liq = {"expanding": "扩张", "neutral": "中性", "contracting": "收缩"}.get(liq, liq)
    read_en = f"Fed liquidity {liq}"
    read_zh = f"联储流动性{zh_liq}"
    if hy is not None:
        read_en += f"; HY credit {'tightening' if hy < 0 else 'widening'}"
        read_zh += f"；高收益信用{'收窄' if hy < 0 else '走阔'}"
    return _component(
        "liquidity", "Liquidity & credit", "流动性与信用", s01, read_en, read_zh,
        [_metric("Fed liquidity", "联储流动性", liq),
         _metric("HY OAS Δ21d", "高收益利差 21日", f"{hy:+.0f}bp" if hy is not None else None),
         _metric("Conditions", "金融条件", fc.get("state")),
         _metric("Systemic stress", "系统性压力", ss.get("state"))])


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


def _ms_calib(root=None) -> dict:
    """Read the amplification overlay (data/market_state/calibration.json); fall back to the
    flat-6 defaults. Never raises — a bad file degrades to defaults."""
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
                    c["weights"][k] = float(min(_WEIGHT_BOUNDS[1], max(_WEIGHT_BOUNDS[0], v)))
            c["base"].update({k: v for k, v in (ov.get("base") or {}).items() if k in c["base"]})
            for k in ("severe_bump", "floor"):
                if ov.get(k) is not None:
                    c[k] = ov[k]
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


def _radar_to_rd(rr: dict) -> dict:
    """Map a risk_radar.v2 (US) / risk_radar_intl.v1 (CN/HK/CA) payload into the `rd` dict
    the shared .rrx Risk-Radar card consumes. Pure; the amplifying US override and the
    display-only override both build on it. `amp`/`ceiling` default to off (the US override
    fills them in when the radar is loud)."""
    state = rr.get("state")
    top = _num(rr.get("top_score"))
    dp = rr.get("drawdown_prob") or {}
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
        # display-only DE-ESCALATION read ("risk-off may be ending"); the US override fills it in
        # below from the radar trajectory + the liquidity tide. Stays None on the intl radars and
        # the no-source calm radar, so the card's {% if rd.recovery %} guard simply skips it.
        "recovery": None,
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

    out.update(amp=amp, amp_keys=keys, amp_flags_en=flags_en, amp_flags_zh=flags_zh,
               severe_gated=severe_gated, ceiling=ceiling)

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
            "severe_gated": False, "ceiling": None, "recovery": None}


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
        score = raw_score
        if verdict == "RISK_OFF":
            score = min(score, 41)
        elif verdict == "MIXED":
            score = min(score, 59)
        if radar.get("ceiling") is not None:
            score = min(score, radar["ceiling"])
        # the penalised score now drives the verdict; the radar can only make it more
        # risk-off than the prior overrides, never less.
        verdict = _cap(verdict, _verdict_from_score(score))

        flip_en, flip_zh = _flip_text(comps, verdict)
        return {
            "schema": "market_state.v1",
            "asof": latest.get("date"),
            "score": score,
            "raw_score": raw_score,
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


def _flip_text(comps: list, verdict: str) -> tuple[str, str]:
    """A falsifiable 'what tips this' line, built off the weakest / strongest leg."""
    if not comps:
        return "", ""
    weakest = min(comps, key=lambda c: c["score"])
    strongest = max(comps, key=lambda c: c["score"])
    if verdict == "RISK_ON":
        return (f"→ Mixed if {weakest['label_en'].lower()} rolls over (now {weakest['score']}/100, the weakest leg).",
                f"→ 若{weakest['label_zh']}转弱（现 {weakest['score']}/100，最弱项）则转为「混合」。")
    if verdict == "RISK_OFF":
        return (f"→ Mixed when {strongest['label_en'].lower()} stabilises and stress fades.",
                f"→ 待{strongest['label_zh']}企稳且压力护栏解除后转为「混合」。")
    return (f"→ Green if {weakest['label_en'].lower()} firms up (now {weakest['score']}/100); "
            f"→ Red if it deteriorates further.",
            f"→ 若{weakest['label_zh']}转强（现 {weakest['score']}/100）则转「绿」；进一步恶化则转「红」。")


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
            snap["freshness"] = {
                "data_asof": incoming or None,
                "expected_asof": expected,
                "stale": bool(incoming) and incoming < expected,
            }
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
