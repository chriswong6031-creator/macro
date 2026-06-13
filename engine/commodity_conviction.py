"""Commodity CONVICTION engine — a forward-looking, multi-factor, weighted verdict.

Answers the trader's real question per commodity: *what should I do right now, and
where are we headed?* Output is a single signed conviction score in [-100, +100]
mapped to STRONG BUY / BUY / HOLD / SELL / STRONG SELL, plus:
  * a CYCLE-POSITION read (are we in a bull/bear/flat leg, how far in, and roughly
    how long until the next top/bottom — measured from this commodity's own 25y of
    bull/bear leg durations), and
  * a transparent FACTOR BREAKDOWN (every factor's naive-bullish reading, its signed
    MEASURED weight, and its contribution), grouped into themes the user asked for:
    Trend/Cycle, Macro backdrop, Dollar & Carry (rates path), Risk & Liquidity,
    Value & Positioning, and Shocks/Disruptions.

Design principles (house rules):
  * MECHANICAL core. Every factor is naive-bullish-oriented ([-1,+1], + = bullish);
    each weight is SIGNED and its sign+magnitude come from MEASURED forward-return
    predictive strength (data/commodity/conviction_calibration.json, written by
    scripts/research_commodity_conviction.py). So an INVERTED signal (e.g. oil's
    12-mo trend, which mean-reverts) gets a NEGATIVE weight automatically — the
    verdict can never contradict the calibration.
  * NO double-counting: driver_score already folds dollar + real-yield + breakevens
    + growth, so the explicit NEW factors are the ORTHOGONAL ones — forward rate
    path / carry (fed-funds futures + 2s10s curve), risk-off (VIX + MOVE + HY
    credit), and liquidity (net Fed liquidity + M2).
  * Degrades safely: any missing series drops that factor and its weight is
    redistributed; the engine never raises (returns {} on total failure) so it can
    never break the page build.

Reuses engine.commodity_mtf (cycle-ladder regime + MTF alignment) and the existing
calibrated commodity signals frame from engine.commodity_signals.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config, store
from engine import commodity_mtf

log = logging.getLogger(__name__)

CALIB_PATH = "commodity/conviction_calibration.json"

# ---------------------------------------------------------------------------- #
# extra macro series (beyond engine.commodity_inputs' configured drivers) — the
# orthogonal dimensions: forward rate path / carry, risk-off, liquidity.
# ---------------------------------------------------------------------------- #
def _series(group: str, name: str, col: str | None = None) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or getattr(df, "empty", True):
        return None
    s = df[col] if (col and col in df.columns) else df.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce")
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def load_macro_extras() -> dict[str, pd.Series]:
    """The forward-looking / orthogonal macro series the conviction engine adds on
    top of the configured commodity drivers. All optional — missing -> factor drops."""
    out: dict[str, pd.Series] = {}
    spec = {
        "fed_funds_fut": ("yahoo", "ZQ_F", "close"),   # rate-path: price up = cuts priced = dovish
        "curve_2s10s": ("fred", "T10Y2Y", None),       # bull-steepening = early-cycle/easing
        "move": ("yahoo", "_MOVE", "close"),           # bond vol (rate uncertainty)
        "vix": ("fred", "VIXCLS", None),               # equity vol (risk-off)
        "hy_oas": ("fred", "BAMLH0A0HYM2", None),      # HY credit spread (risk-off)
        "fed_balance": ("fred", "WALCL", None),        # liquidity
        "rrp": ("fred", "RRPONTSYD", None),            # liquidity drain
        "m2": ("fred", "M2SL", None),                  # money supply
        "dxy": ("yahoo", "DX-Y.NYB", "close"),
        "dollar_cot": ("cot", "cot_dollar", "net_spec_pct_oi"),
    }
    for key, (g, n, c) in spec.items():
        s = _series(g, n, c)
        if s is not None:
            out[key] = s
    # net Fed liquidity ($bn): balance sheet minus reverse-repo drain
    if "fed_balance" in out:
        rrp = out.get("rrp")
        netliq = out["fed_balance"] / 1000.0
        if rrp is not None:
            netliq = netliq.subtract(rrp.reindex(netliq.index).ffill().fillna(0.0))
        out["net_liquidity"] = netliq
    return out


# ---------------------------------------------------------------------------- #
# normalization: every factor lands in [-1, +1], naive-bullish oriented.
# ---------------------------------------------------------------------------- #
def _align(s: pd.Series | None, idx: pd.DatetimeIndex) -> pd.Series | None:
    if s is None:
        return None
    return s.reindex(s.index.union(idx)).ffill().reindex(idx)


def _zclip(s: pd.Series, lb: int = 504, cap: float = 2.5) -> pd.Series:
    """Rolling z-score scaled into [-1, 1] (a robust, regime-relative normalizer)."""
    mp = max(40, lb // 6)
    m = s.rolling(lb, min_periods=mp).mean()
    sd = s.rolling(lb, min_periods=mp).std()
    z = (s - m) / sd.replace(0, np.nan)
    return (z.clip(-cap, cap) / cap)


def _chg(s: pd.Series, w: int) -> pd.Series:
    return s.diff(w)


def _ret(s: pd.Series, w: int) -> pd.Series:
    return s.pct_change(w)


# ---------------------------------------------------------------------------- #
# factor panel — historical, naive-bullish [-1,1]. One source of truth for both
# calibration (research) and the live verdict (last row).
# ---------------------------------------------------------------------------- #
# value-factor orientation per asset (high gold/silver ratio = silver cheap):
#   silver: high GSR -> bullish silver (+);  gold: high GSR -> gold rich -> bearish (-)
_VALUE_SIGN = {"gold": -1.0, "silver": 1.0}

FACTOR_LABELS = {
    "trend": ("12-month trend", "12个月趋势"),
    "structure": ("Price structure", "价格结构"),
    "dollar": ("US dollar", "美元"),
    "real_rates": ("Real rates", "实际利率"),
    "carry": ("Rates path / carry", "利率路径/套利"),
    "riskoff": ("Risk appetite", "风险偏好"),
    "liquidity": ("Liquidity", "流动性"),
    "growth": ("Growth", "增长"),
    "inflation": ("Inflation expectations", "通胀预期"),
    "value": ("Value (ratio)", "价值（比价）"),
    "positioning": ("Positioning (COT)", "持仓（COT）"),
    "shock": ("Residual shock", "残差冲击"),
    "risk": ("Risk index", "风险指数"),
    "cycle": ("Cycle regime", "周期格局"),
    "mtf": ("Timeframe alignment", "多周期共振"),
    "alerts": ("Disruptions / alerts", "扰动/警报"),
}

# which theme each factor belongs to (for the grouped UI)
FACTOR_GROUP = {
    "trend": "Trend & Cycle", "structure": "Trend & Cycle", "cycle": "Trend & Cycle",
    "mtf": "Trend & Cycle",
    "growth": "Macro backdrop", "inflation": "Macro backdrop",
    "dollar": "Dollar & Carry", "real_rates": "Dollar & Carry", "carry": "Dollar & Carry",
    "riskoff": "Risk & Liquidity", "liquidity": "Risk & Liquidity", "risk": "Risk & Liquidity",
    "value": "Value & Positioning", "positioning": "Value & Positioning",
    "shock": "Shocks", "alerts": "Shocks",
}

# factors computed cheaply over full history (calibratable, vectorized). DECOMPOSED
# macro (dollar/real_rates/carry/inflation/growth) — no composite driver_score factor,
# so the orthogonal macro dimensions are each measured and weighted on their own.
PANEL_FACTORS = ["trend", "structure", "dollar", "real_rates", "carry", "riskoff",
                 "liquidity", "growth", "inflation", "value", "positioning", "shock", "risk"]


def factor_panel(asset: str, sig: pd.DataFrame, drivers: dict,
                 extras: dict) -> pd.DataFrame:
    """Naive-bullish [-1,1] factor time series for one commodity. Cheap/vectorized
    (no per-row cycle walk) so research can calibrate weights over 25y."""
    idx = sig.index
    f = pd.DataFrame(index=idx)

    # --- price / technical -------------------------------------------------- #
    if "ts_momentum" in sig:
        f["trend"] = sig["ts_momentum"].clip(-1, 1)
    if "structure" in sig:
        st = sig["structure"]
        f["structure"] = (st.clip(-1, 1) if st.abs().max() <= 1.5 else _zclip(st))
    if "risk_index" in sig:                         # low risk = naive bullish
        f["risk"] = ((50.0 - sig["risk_index"]) / 50.0).clip(-1, 1)

    # --- explicit, DECOMPOSED macro factors (orthogonal — no composite to
    # double-count against; gives the user DXY / real-rates / carry as their own
    # measured factors). dollar & real-rates are naive-bullish = falling. --------
    dxy = _align(drivers.get("dxy"), idx)
    broad = _align(drivers.get("broad_dollar"), idx)
    dparts = [_zclip(_ret(s, 63)) for s in (dxy, broad) if s is not None]
    if dparts:
        f["dollar"] = (-pd.concat(dparts, axis=1).mean(axis=1)).clip(-1, 1)  # rising $ = bearish
    ry = _align(drivers.get("real_yield"), idx)
    if ry is not None:
        f["real_rates"] = (-_zclip(_chg(ry, 63))).clip(-1, 1)                # rising real yield = bearish

    # --- value / positioning / shock --------------------------------------- #
    if asset in ("gold", "silver") and "gsr_pctile" in sig:
        f["value"] = _VALUE_SIGN[asset] * ((sig["gsr_pctile"] - 50.0) / 50.0)
    elif asset == "oil" and "bw_spread_pctile" in sig:
        f["value"] = ((sig["bw_spread_pctile"] - 50.0) / 50.0)        # widening = bullish
    if "pos_pctile" in sig:                          # crowded short = contrarian bullish
        f["positioning"] = (-(sig["pos_pctile"] - 50.0) / 50.0)
    if "shock_z" in sig:
        f["shock"] = np.tanh(sig["shock_z"] / 2.0)

    # --- NEW orthogonal macro: carry / risk-off / liquidity / growth / infl - #
    zq = _align(extras.get("fed_funds_fut"), idx)
    curve = _align(extras.get("curve_2s10s"), idx)
    carry_parts = []
    if zq is not None:
        carry_parts.append(0.6 * _zclip(_ret(zq, 63)))          # price up = cuts = dovish = bullish
    if curve is not None:
        carry_parts.append(0.4 * _zclip(_chg(curve, 63)))       # steepening = easing = bullish
    if carry_parts:
        f["carry"] = pd.concat(carry_parts, axis=1).sum(axis=1, min_count=1).clip(-1, 1)

    stress = []
    for k in ("vix", "move", "hy_oas"):
        s = _align(extras.get(k), idx)
        if s is not None:
            stress.append(_zclip(s))
    if stress:                                       # high stress = risk-off = naive bearish
        f["riskoff"] = (-pd.concat(stress, axis=1).mean(axis=1)).clip(-1, 1)

    netliq = _align(extras.get("net_liquidity"), idx)
    m2 = _align(extras.get("m2"), idx)
    liq_parts = []
    if netliq is not None:
        liq_parts.append(0.7 * _zclip(_chg(netliq, 63)))
    if m2 is not None:
        liq_parts.append(0.3 * _zclip(_ret(m2, 90)))
    if liq_parts:
        f["liquidity"] = pd.concat(liq_parts, axis=1).sum(axis=1, min_count=1).clip(-1, 1)

    indpro = _align(drivers.get("indpro"), idx)
    gparts = []
    if indpro is not None:
        gparts.append(_zclip(_ret(indpro, 126)))
    cg = sig.get("copper_gold") if hasattr(sig, "get") else None
    if cg is not None:
        gparts.append(_zclip(_ret(cg, 63)))
    if gparts:
        f["growth"] = pd.concat(gparts, axis=1).mean(axis=1).clip(-1, 1)

    be = _align(drivers.get("breakeven10"), idx)
    if be is not None:
        f["inflation"] = _zclip(_chg(be, 63)).clip(-1, 1)

    return f


# ---------------------------------------------------------------------------- #
# bull / bear cycle segmentation -> position + forward time-to-turn
# ---------------------------------------------------------------------------- #
def _leg(kind: str, t, p, i0: int, i1: int) -> dict:
    return {"kind": kind, "start": t[i0], "end": t[i1],
            "days": int((t[i1] - t[i0]).days), "amp": float(p[i1] / p[i0] - 1.0)}


def cycle_segments(close: pd.Series, min_amp: float = 0.20) -> list[dict]:
    """ZigZag legs: alternating bull (trough->peak) / bear (peak->trough), each
    confirmed only when price reverses `min_amp` (fraction) off the running extreme.
    Returns CONFIRMED legs oldest->newest (the still-forming final leg is excluded —
    cycle_position() derives the current leg from the last confirmed pivot)."""
    c = close.dropna()
    if len(c) < 200:
        return []
    p = c.to_numpy().astype(float)
    pos = p[p > 0]
    floor = max(1e-6, 0.02 * float(np.median(pos))) if len(pos) else 1e-6
    p = np.where(p <= 0, floor, p)          # winsorize the 2020 negative-oil print
    t = c.index
    n = len(p)
    legs: list[dict] = []
    piv_i = 0                                # last confirmed pivot
    hi_i = lo_i = 0                          # running peak / trough since the pivot
    direction = 0                            # 0 unknown, +1 in up-move, -1 in down-move
    for i in range(1, n):
        if direction >= 0 and p[i] > p[hi_i]:
            hi_i = i
        if direction <= 0 and p[i] < p[lo_i]:
            lo_i = i
        if direction == 0:                   # seed the first leg from bar 0
            if p[i] <= p[hi_i] * (1 - min_amp) and hi_i > piv_i:
                legs.append(_leg("bull", t, p, piv_i, hi_i))
                piv_i, lo_i, direction = hi_i, i, -1
            elif p[i] >= p[lo_i] * (1 + min_amp) and lo_i > piv_i:
                legs.append(_leg("bear", t, p, piv_i, lo_i))
                piv_i, hi_i, direction = lo_i, i, 1
        elif direction > 0:                  # seeking a peak; confirm on min_amp drop
            if p[i] <= p[hi_i] * (1 - min_amp):
                legs.append(_leg("bull", t, p, piv_i, hi_i))
                piv_i, lo_i, direction = hi_i, i, -1
        else:                                # seeking a trough; confirm on min_amp rise
            if p[i] >= p[lo_i] * (1 + min_amp):
                legs.append(_leg("bear", t, p, piv_i, lo_i))
                piv_i, hi_i, direction = lo_i, i, 1
    return legs


# per-asset cycle amplitude (more volatile commodities need a larger swing to count
# a "major" leg). Refined by scripts.research_commodity_conviction -> calibration json.
_CYCLE_AMP = {"gold": 0.18, "silver": 0.28, "copper": 0.24, "oil": 0.32}


def cycle_position(close: pd.Series, asset: str, min_amp: float = 0.20) -> dict:
    """Where are we in the current bull/bear leg, and ~how long to the next turn —
    measured from this commodity's own historical leg durations."""
    c = close.dropna()
    legs = cycle_segments(c, min_amp)
    if not legs:
        return {}
    last = legs[-1]
    # current (forming) leg runs in the OPPOSITE direction of the last confirmed leg,
    # from its end pivot to now
    cur_kind = "bear" if last["kind"] == "bull" else "bull"
    start = last["end"]
    cur = c.loc[c.index >= start]
    if len(cur) < 2:
        return {}
    days_in = (c.index[-1] - start).days
    if cur_kind == "bull":
        ext = cur.min(); ext_dt = cur.idxmin()
        amp = c.iloc[-1] / cur.min() - 1.0
        nxt, nxt_zh = "top", "顶部"
    else:
        ext = cur.max(); ext_dt = cur.idxmax()
        amp = c.iloc[-1] / cur.max() - 1.0
        nxt, nxt_zh = "bottom", "底部"

    same = [l["days"] for l in legs if l["kind"] == cur_kind]
    same_amp = [abs(l["amp"]) for l in legs if l["kind"] == cur_kind]
    med = float(np.median(same)) if same else 365.0
    p25 = float(np.percentile(same, 25)) if len(same) >= 3 else med * 0.6
    p75 = float(np.percentile(same, 75)) if len(same) >= 3 else med * 1.5
    typ_amp = float(np.median(same_amp)) if same_amp else 0.4

    frac = days_in / med if med else 1.0
    if frac < 0.40:
        phase, phase_zh = "early", "早期"
    elif frac < 0.80:
        phase, phase_zh = "mid", "中期"
    elif frac <= 1.05:
        phase, phase_zh = "late", "晚期"
    else:
        phase, phase_zh = "overdue", "逾期"
    eta = max(0, int(round(med - days_in)))
    eta_lo = max(0, int(round(p25 - days_in)))
    eta_hi = max(0, int(round(p75 - days_in)))

    return {
        "regime": cur_kind, "days_in": int(days_in),
        "median_len_d": int(round(med)), "p25_d": int(round(p25)), "p75_d": int(round(p75)),
        "eta_days": eta, "eta_lo": eta_lo, "eta_hi": eta_hi,
        "phase": phase, "phase_zh": phase_zh,
        "next_event": nxt, "next_event_zh": nxt_zh,
        "amp_so_far": round(100 * amp, 1), "typical_amp": round(100 * typ_amp, 1),
        "n_legs": len(same), "pivot_date": str(ext_dt.date()),
    }


# ---------------------------------------------------------------------------- #
# weights: signed, magnitude = MEASURED predictive strength. Loaded from the
# research calibration; falls back to a sensible prior.
# ---------------------------------------------------------------------------- #
# Prior weights (used until research overwrites them). Signs encode known polarity:
#   oil trend INVERTED (-), oil shock fades (-), gold macro contrarian (handled by
#   driver_score sign in calibration), risk high = bearish near-term (+ naive low-risk).
_PRIOR = {
    "trend": 0.14, "structure": 0.06, "dollar": 0.12, "real_rates": 0.09, "carry": 0.09,
    "riskoff": 0.08, "liquidity": 0.07, "growth": 0.07, "inflation": 0.05, "value": 0.10,
    "positioning": 0.04, "shock": 0.06, "risk": 0.07, "cycle": 0.10, "mtf": 0.06,
    "alerts": 0.04,
}


def default_weights(asset: str) -> dict:
    w = dict(_PRIOR)
    # apply known inversions from the commodity calibration (mirrors commodity_mtf)
    if asset == "oil":
        w["trend"] = -abs(w["trend"])
        w["shock"] = -abs(w["shock"])
    if asset == "silver":
        w["positioning"] = abs(w["positioning"])
    return w


def load_calibration() -> dict:
    p = config.data_dir() / "commodity" / "conviction_calibration.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            log.warning("conviction calibration unreadable (%s)", e)
    return {}


def asset_weights(asset: str, calib: dict) -> dict:
    w = (calib.get("assets", {}).get(asset, {}) or {}).get("weights")
    return dict(w) if w else default_weights(asset)


# ---------------------------------------------------------------------------- #
# action mapping
# ---------------------------------------------------------------------------- #
ACTIONS = [  # (low_inclusive, label, zh, css)
    (60, "STRONG BUY", "强烈买入", "sbuy"),
    (20, "BUY", "买入", "buy"),
    (-20, "HOLD", "持有", "hold"),
    (-60, "SELL", "卖出", "sell"),
    (-101, "STRONG SELL", "强烈卖出", "ssell"),
]


def _action(score: float, thresholds: dict | None = None) -> tuple[str, str, str]:
    t = thresholds or {}
    sb, b, s, ss = (t.get("strong_buy", 60), t.get("buy", 20),
                    t.get("sell", -20), t.get("strong_sell", -60))
    if score >= sb:
        return "STRONG BUY", "强烈买入", "sbuy"
    if score >= b:
        return "BUY", "买入", "buy"
    if score > s:
        return "HOLD", "持有", "hold"
    if score > ss:
        return "SELL", "卖出", "sell"
    return "STRONG SELL", "强烈卖出", "ssell"


# ---------------------------------------------------------------------------- #
# factor readings (human "why" per factor)
# ---------------------------------------------------------------------------- #
def _reading(key: str, val: float) -> tuple[str, str]:
    if val is None or not np.isfinite(val):
        return "n/a", "无数据"
    strength = "strongly " if abs(val) >= 0.55 else ("" if abs(val) >= 0.2 else "mildly ")
    s_zh = "强烈" if abs(val) >= 0.55 else ("" if abs(val) >= 0.2 else "略微")
    if val > 0.08:
        return f"{strength}bullish", f"{s_zh}看多"
    if val < -0.08:
        return f"{strength}bearish", f"{s_zh}看空"
    return "neutral", "中性"


# ---------------------------------------------------------------------------- #
# the verdict
# ---------------------------------------------------------------------------- #
def conviction(asset: str, sig: pd.DataFrame, drivers: dict, extras: dict,
               mtf_a: dict | None = None, alert_tilt: float | None = None,
               calib: dict | None = None) -> dict:
    """Assemble the full conviction verdict for one commodity. {} on failure."""
    try:
        if sig is None or sig.empty:
            return {}
        calib = calib if calib is not None else load_calibration()
        acal = calib.get("assets", {}).get(asset, {}) or {}
        weights = asset_weights(asset, calib)
        thresholds = acal.get("thresholds")
        reliable = acal.get("score_reliable", True)

        panel = factor_panel(asset, sig, drivers, extras)
        last = panel.iloc[-1] if len(panel) else pd.Series(dtype=float)
        factors: dict[str, float] = {k: float(last.get(k)) for k in panel.columns
                                     if pd.notna(last.get(k))}

        # live-only factors (technical confirmations + events)
        mtf_a = mtf_a or {}
        ladder = (mtf_a.get("ladder") or {})
        reg = ladder.get("regime")
        if reg in ("bull", "bear", "neutral"):
            factors["cycle"] = {"bull": 1.0, "neutral": 0.0, "bear": -1.0}[reg]
        verdict_mtf = commodity_mtf.confluence_verdict(mtf_a, asset, sig.iloc[-1],
                                                       (calib.get("_signal_calib") or {}))
        if verdict_mtf:
            mtf_sign = (verdict_mtf.get("short_sign", 0) + verdict_mtf.get("mid_sign", 0)
                        + verdict_mtf.get("long_sign", 0)) / 3.0
            factors["mtf"] = float(np.clip(mtf_sign, -1, 1))
        if alert_tilt is not None and np.isfinite(alert_tilt):
            factors["alerts"] = float(np.clip(alert_tilt, -1, 1))

        # weighted score (normalized by used weight mass)
        rows = []
        num = den = 0.0
        for k, v in factors.items():
            w = float(weights.get(k, 0.0))
            if w == 0.0:
                continue
            contrib = w * v
            num += contrib
            den += abs(w)
            r_en, r_zh = _reading(k, v)
            lab = FACTOR_LABELS.get(k, (k, k))
            rows.append({"key": k, "label": lab[0], "label_zh": lab[1],
                         "group": FACTOR_GROUP.get(k, "Other"),
                         "value": round(v, 3), "weight": round(w, 3),
                         "contribution": round(contrib, 4),
                         "reading": r_en, "reading_zh": r_zh})
        if den == 0:
            return {}
        score = float(np.clip(100.0 * num / den, -100, 100))
        rows.sort(key=lambda r: -abs(r["contribution"]))

        action, action_zh, css = _action(score, thresholds)
        stance = "bullish" if score >= 20 else ("bearish" if score <= -20 else "neutral")

        # confidence = factor agreement x data completeness
        agree = abs(num) / sum(abs(r["contribution"]) for r in rows) if rows else 0.0
        completeness = den / sum(abs(w) for w in weights.values() if w) if weights else 0.0
        confidence = round(float(np.clip(0.5 * agree + 0.5 * completeness, 0, 1)), 2)

        # grouped scores
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

        amp = (calib.get("assets", {}).get(asset, {}) or {}).get("cycle_min_amp",
                                                                  _CYCLE_AMP.get(asset, 0.20))
        cyc = cycle_position(sig["close"], asset, amp)
        if not reliable:                       # honest: weak calibration -> dampen
            confidence = round(confidence * 0.6, 2)

        head, head_zh, sub, sub_zh = _narrate(asset, action, score, cyc, rows, stance)

        return {
            "score": round(score, 1), "action": action, "action_zh": action_zh,
            "action_css": css, "stance": stance, "confidence": confidence,
            "reliable": bool(reliable),
            "factors": rows, "groups": group_list, "cycle": cyc,
            "headline": head, "headline_zh": head_zh, "sub": sub, "sub_zh": sub_zh,
            "n_factors": len(rows),
        }
    except Exception as e:  # noqa: BLE001 — verdict overlay must never break the build
        log.warning("conviction failed for %s (%s)", asset, e)
        return {}


def _narrate(asset: str, action: str, score: float, cyc: dict,
             rows: list[dict], stance: str) -> tuple[str, str, str, str]:
    top_up = [r for r in rows if r["contribution"] > 0][:2]
    top_dn = [r for r in rows if r["contribution"] < 0][:2]
    lead = top_up if stance != "bearish" else top_dn
    lead = lead or top_dn or top_up                      # never empty if any factor exists
    drivers_txt = ", ".join(r["label"].lower() for r in lead) or "no single dominant factor"
    drivers_zh = "、".join(r["label_zh"] for r in lead) or "无单一主导因素"
    head = f"{action} · conviction {score:+.0f}"
    head_zh = f"{dict(STRONG_BUY='强烈买入', BUY='买入', HOLD='持有', SELL='卖出', STRONG_SELL='强烈卖出').get(action.replace(' ', '_'), action)} · 信心 {score:+.0f}"
    if cyc:
        leg = "bull" if cyc["regime"] == "bull" else "bear"
        leg_zh = "牛市" if leg == "bull" else "熊市"
        eta = cyc["eta_days"]
        when = (f"~{eta}d to a typical {cyc['next_event']}" if eta > 0
                else f"past the typical {cyc['next_event']} window ({cyc['phase']})")
        when_zh = (f"距典型{cyc['next_event_zh']}约 {eta} 天" if eta > 0
                   else f"已过典型{cyc['next_event_zh']}窗口（{cyc['phase_zh']}）")
        sub = (f"In a {leg} leg, {cyc['phase']} ({cyc['days_in']}d in of a typical "
               f"{cyc['median_len_d']}d), {when}. Led by {drivers_txt}.")
        sub_zh = (f"处于{leg_zh}段，{cyc['phase_zh']}（已运行 {cyc['days_in']} 天，"
                  f"典型 {cyc['median_len_d']} 天），{when_zh}。主导因素：{drivers_zh}。")
    else:
        sub = f"Driven by {drivers_txt}."
        sub_zh = f"主导因素：{drivers_zh}。"
    return head, head_zh, sub, sub_zh
