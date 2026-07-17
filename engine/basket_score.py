"""Advanced per-theme TEXTURES for the Theme Rotation Desk (display-only).

Refines the engine.theme_scoring read with the specific signals a user needs to time a
theme: how long it has been in a bull market, how overbought/extended it is, whether it is
an EMERGING clean entry, whether it is at ROLL-OVER risk — plus a market CONCENTRATION /
narrowness block (the user's core concern: the tape can get narrow, low advance-decline).

HONEST BY CONSTRUCTION: every texture carries `directional: False`. These DESCRIBE state
(trend age, stretch, distribution) — they do NOT forecast returns. Cross-sectional theme
momentum has ~0 rank-IC; the one validated edge is the absolute-trend (SMA-200) gate, which
is drawdown-control, not alpha. Mirrors the theme_crowding / group_flow honesty contract.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lib import config

# Hand weights for the rollover_risk breadth-free legs (rs>=.8 · rolling-over · decel<-.4 ·
# below-50d · 5d<-1%&rs>.7). scripts.calibrate_baskets can OVERRIDE these with OOS-validated
# weights (it found below-50d + extension dominate forward drawdown; the accel legs add
# nothing OOS) — read additively, fall back to the hand weights if the calibration is absent.
_ROLLOVER_HAND = (0.30, 0.25, 0.20, 0.15, 0.10)


def _rollover_weights() -> tuple:
    try:
        p = config.data_dir() / "strategies" / "baskets_calibration.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        rf = d.get("rollover_fit") or {}
        w = rf.get("wired_weights")
        if rf.get("verdict") == "ship_fitted_weights" and isinstance(w, list) and len(w) == 5:
            return tuple(float(x) for x in w)
    except Exception:  # noqa: BLE001 — calibration is enrichment, never fatal
        pass
    return _ROLLOVER_HAND


def _rsi(s: pd.Series, n: int = 14) -> float | None:
    s = s.dropna()
    if len(s) < n + 2:
        return None
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    v = (100 - 100 / (1 + rs)).iloc[-1]
    return float(v) if np.isfinite(v) else None


def bull_age(lvl: pd.Series) -> dict | None:
    """Days the EW level has held above its 200d SMA (bull-market age) + drawdown from peak.

    'How long has this theme been in a bull market' — the consecutive run above a rising
    long trend, with a maturity stage (young → building → mature → aging) and the current
    drawdown from the trailing peak / distance from the 52-week high."""
    s = lvl.dropna()
    if len(s) < 60:
        return None
    sma = s.rolling(200, min_periods=60).mean()
    above = (s > sma).to_numpy()
    days = 0
    for k in range(len(above) - 1, -1, -1):
        if above[k]:
            days += 1
        else:
            break
    in_bull = bool(above[-1])
    peak = float(s.cummax().iloc[-1])
    dd = float(s.iloc[-1] / peak - 1.0) if peak else None
    w = min(252, len(s))
    hi = float(s.iloc[-w:].max())
    from_hi = float(s.iloc[-1] / hi - 1.0) if hi else None
    if not in_bull:
        stage, stage_zh = "downtrend", "下行"
    elif days < 40:
        stage, stage_zh = "young", "初期"
    elif days < 130:
        stage, stage_zh = "building", "上升中"
    elif days < 300:
        stage, stage_zh = "mature", "成熟"
    else:
        stage, stage_zh = "aging", "老化"
    return {"in_bull": in_bull, "days": int(days), "approx_months": round(days / 21.0, 1),
            "drawdown_from_peak": round(dd, 4) if dd is not None else None,
            "from_52w_high": round(from_hi, 4) if from_hi is not None else None,
            "stage": stage, "stage_zh": stage_zh, "directional": False}


def overbought(lvl: pd.Series, rs_pctile: float | None, crowd: dict | None) -> dict:
    """Basket-level RSI(14) + RS percentile + % members extended → an overbought band.

    NOT a sell signal — high readings mean 'late / stretched / chase-risk', the asymmetric
    down-size context from theme_crowding, never a short."""
    rsi = _rsi(lvl)
    ext = None
    if isinstance(crowd, dict):
        # READ THE % of members extended from crowd["extension"] (pct_stretched /
        # pct_parabolic, emitted 0-100 by theme_crowding) — NOT legs["extension"]["value"],
        # which is the median ext Z-SCORE (~0-3): feeding that to `min(ext*1.5,1.2)` pins
        # the band to its 1.2 ceiling for any z>=0.8, collapsing the overbought resolution.
        e = crowd.get("extension") if isinstance(crowd.get("extension"), dict) else {}
        for k in ("pct_stretched", "pct_parabolic"):
            if isinstance(e.get(k), (int, float)):
                ext = float(e[k]) / 100.0          # 0-100 -> fraction extended
                break
    comps = []
    if rsi is not None:
        comps.append(min(max((rsi - 50) / 30.0, 0.0), 1.2))      # 50→0, 80→1
    if rs_pctile is not None:
        comps.append(min(max((rs_pctile - 0.5) / 0.4, 0.0), 1.2))  # .50→0, .90→1
    if ext is not None:
        comps.append(min(ext * 1.5, 1.2))
    val = float(np.clip(np.mean(comps), 0.0, 1.2)) if comps else 0.0
    if rsi is not None and rsi < 35:
        band, band_zh = "oversold", "超卖"
    elif val >= 0.9:
        band, band_zh = "extreme", "极度超买"
    elif val >= 0.6:
        band, band_zh = "overbought", "超买"
    elif val >= 0.35:
        band, band_zh = "elevated", "偏高"
    else:
        band, band_zh = "neutral", "中性"
    return {"rsi": round(rsi, 1) if rsi is not None else None,
            "rs_pctile": round(rs_pctile, 3) if rs_pctile is not None else None,
            "pct_extended": round(ext, 3) if ext is not None else None,
            "value": round(val, 3), "band": band, "band_zh": band_zh, "directional": False}


def clean_entry(lvl: pd.Series, fp: dict | None, breadth_d: dict | None,
                rsi_val: float | None) -> dict:
    """An EMERGING 'clean entry' — building momentum, NOT extended, NOT overbought, broad,
    above trend, on a shallow pullback (a healthy entry, not a vertical chase)."""
    s = lvl.dropna()
    reasons, q = [], 0.0
    accel = (fp or {}).get("accel_z")
    rs_p = (fp or {}).get("rs_pctile")
    if accel is not None and accel > 0.3:
        q += 0.30; reasons.append("accelerating")
    not_ext = (rs_p is None or rs_p < 0.75)
    if not_ext:
        q += 0.20; reasons.append("not extended")
    if rsi_val is not None and rsi_val < 65:
        q += 0.15; reasons.append("RSI room")
    pct50 = (breadth_d or {}).get("pct50")
    if pct50 is not None and pct50 >= 0.5:
        q += 0.15; reasons.append("breadth supportive")
    if len(s) >= 60:
        sma200 = s.rolling(200, min_periods=60).mean().iloc[-1]
        if pd.notna(sma200) and s.iloc[-1] > sma200:
            q += 0.10; reasons.append("above 200d trend")
    if len(s) >= 20:
        w = min(20, len(s))
        recent_dd = s.iloc[-1] / s.iloc[-w:].max() - 1.0
        if -0.08 < recent_dd < -0.004:
            q += 0.10; reasons.append("shallow pullback")
    # BACKDROP VETO — a "clean entry" is by definition a HEALTHY base turning up, so it must
    # never flag on a BREAKING tape: collapsed breadth (pct50 < 0.4), net new lows, or a hard
    # down-acceleration. Without this, a deteriorating theme (e.g. cn_banks: breadth 0.0, 7 new
    # lows) still ticked accel + not-extended + RSI-room to flag YES — advertising a "clean
    # entry" card on an out-of-favour / AVOID theme. Mirrors theme_scoring._label's `breaking`
    # so the texture can never contradict the lifecycle verdict. NB: below-200d is NOT a veto —
    # an EMERGING theme is below its slow trend by construction (see act_now_stocks); breadth /
    # momentum, not the 200d, separate a real early entry (cn_brokers) from a falling knife.
    nh, nl = (breadth_d or {}).get("nh", 0), (breadth_d or {}).get("nl", 0)
    breaking = ((pct50 is not None and pct50 < 0.4) or (nh - nl) < 0
                or (accel is not None and accel < -0.5))
    return {"flag": bool(q >= 0.6 and not_ext and not breaking), "quality": round(min(q, 1.0), 3),
            "reasons": reasons[:4], "directional": False}


def rollover_risk(lvl: pd.Series, fp: dict | None, fp5: dict | None,
                  breadth_d: dict | None, perf: dict | None) -> dict:
    """Distribution / roll-over risk — was extended, momentum now decelerating off the high,
    breadth deteriorating, below short trend. 'Risky right now, about to roll over.'"""
    s = lvl.dropna()
    reasons, r = [], 0.0
    # breadth-free leg weights: OOS-calibrated (below-50d + extension dominate fwd drawdown)
    # when scripts.calibrate_baskets has shipped them, else the hand weights. A 0-weight leg
    # still appends its descriptive reason but adds nothing to the risk score.
    W = _rollover_weights()
    rs_p = (fp or {}).get("rs_pctile")
    accel = (fp or {}).get("accel_z")
    accel5 = (fp5 or {}).get("accel_z")
    if rs_p is not None and rs_p >= 0.8:
        r += W[0]; reasons.append("extended (RS " + str(round(rs_p * 100)) + "%ile)")
    if accel is not None and accel5 is not None and accel < accel5 and accel < 0:
        r += W[1]; reasons.append("momentum rolling over")
    elif accel is not None and accel < -0.4:
        r += W[2]; reasons.append("decelerating")
    pct50 = (breadth_d or {}).get("pct50")
    nh, nl = (breadth_d or {}).get("nh", 0), (breadth_d or {}).get("nl", 0)
    if pct50 is not None and pct50 < 0.45:
        r += 0.20; reasons.append("breadth weakening")     # breadth legs stay hand (no single-ETF proxy)
    if nl > nh:
        r += 0.10; reasons.append("more new lows")
    if len(s) >= 50:
        sma50 = s.rolling(50, min_periods=25).mean().iloc[-1]
        if pd.notna(sma50) and s.iloc[-1] < sma50:
            r += W[3]; reasons.append("below 50d")
    d5 = (perf or {}).get("5d", {}).get("rel")
    if d5 is not None and d5 < -0.01 and rs_p is not None and rs_p > 0.7:
        r += W[4]; reasons.append("rolling off the high")
    band, band_zh = ("high", "高") if r >= 0.6 else ("elevated", "升高") if r >= 0.35 else ("low", "低")
    return {"risk": round(min(r, 1.0), 3), "band": band, "band_zh": band_zh,
            "reasons": reasons[:4], "directional": False}


def theme_textures(lvl: pd.Series, fp: dict | None, fp5: dict | None,
                   crowd: dict | None, breadth_d: dict | None, perf: dict | None,
                   mc_closes: pd.DataFrame | None = None) -> dict:
    """All four per-theme textures + the basket RSI (one call per basket).

    `mc_closes` (optional, ADDITIVE): the dated live-masked member close matrix. When
    present it feeds the intra-basket breadth-DIVERGENCE texture (level pinned near its
    high while the members roll over one by one — engine.basket_breadth_divergence, a
    display-only de-risk read). None-safe skip keeps every existing caller byte-identical."""
    rsi = _rsi(lvl)
    rs_p = (fp or {}).get("rs_pctile")
    out = {
        "bull_age": bull_age(lvl),
        "overbought": overbought(lvl, rs_p, crowd),
        "clean_entry": clean_entry(lvl, fp, breadth_d, rsi),
        "rollover_risk": rollover_risk(lvl, fp, fp5, breadth_d, perf),
    }
    if mc_closes is not None:
        from engine import basket_breadth_divergence as _bd   # local: keeps import graph light
        out["breadth_divergence"] = _bd.breadth_divergence(mc_closes, lvl)
    return out


def act_now_stocks(members: list, theme: dict) -> dict:
    """WHAT TO ACT ON NOW (stock level) — the member stocks with a genuine buy entry RIGHT
    NOW, GATED by theme health: if the theme is out of favour (deteriorating / fading /
    avoid / trim, or a NEUTRAL theme below its long-term trend) it recommends NOTHING.
    A label the engine has AFFIRMATIVELY called constructive (EMERGING / DOMINANT) is NOT
    vetoed by the slow 200d `in_bull` flag — such a theme is early / below-trend by
    construction, and theme_scoring._reco has already demoted its verb to HOLD; vetoing it
    again here just made the board self-contradict ("out of favour (emerging)"). Otherwise
    only members whose per-stock Conviction Profile is a buy/add, with the cycle NOT blocking
    and a decent entry-axis percentile (good price, not chasing). Honest: a focus list, never
    an order.

    `members` carry a plucked `conviction` block (score, verdict, cycle_blocked, entry_pct)."""
    label = (theme or {}).get("label")
    reco = (theme or {}).get("reco")
    tx = (theme or {}).get("textures") or {}
    in_bull = (tx.get("bull_age") or {}).get("in_bull", True)
    # "Out of favour" must mean the theme's OWN lifecycle read is risk-off — a fading /
    # deteriorating label or a trim / avoid reco. The raw 200d-SMA `in_bull` flag is a SLOW
    # filter: an EMERGING / DOMINANT theme freshly turning up off a base sits below its 200d
    # (in_bull False) BY CONSTRUCTION, so it must not override the engine's own constructive
    # call — that produced the self-contradicting "out of favour (emerging)" scoreboard while
    # suppressing members that DID have an open entry. Drawdown-control for an early /
    # below-trend theme is already applied upstream in theme_scoring._reco (it demotes the verb
    # to HOLD). So a False `in_bull` only counts as a downtrend veto when the label is NOT
    # constructive (i.e. neutral / missing).
    risk_label = label in ("deteriorating", "fading")
    risk_reco = reco in ("avoid", "trim")
    constructive = label in ("emerging", "dominant")
    downtrend = (in_bull is False) and not constructive
    # Members the ranker can NEVER surface — no conviction read (not in the per-stock
    # library, or a thin record without a score). Carried on every payload so the detail
    # page prints the gap explicitly: an all-uncovered basket must read as a coverage
    # gap, not a misleading "no clean entry".
    uncovered = [m.get("symbol") for m in members or []
                 if (m.get("conviction") or {}).get("score") is None]
    if risk_label or risk_reco or downtrend:
        why = label if risk_label else reco if risk_reco else "downtrend"
        why_en = "in a downtrend" if why == "downtrend" else str(why)
        why_zh = {"deteriorating": "走弱", "fading": "退潮", "avoid": "建议回避",
                  "trim": "建议减持", "downtrend": "处于下行趋势"}.get(why, str(why))
        return {"status": "theme_out_of_favour", "buys": [], "uncovered": uncovered,
                "note_en": "Theme is out of favour (" + why_en + ") — no stock buys recommended here right now.",
                "note_zh": "主题暂不被青睐（" + why_zh + "）— 当前不建议买入该主题个股。"}
    buys = []
    for m in members or []:
        c = m.get("conviction")
        if not c or c.get("score") is None:
            continue
        # Two-gauge: a member is "act now" only when the ENTRY gauge says the window is
        # open (buy_now / partial), not when the conviction score is merely high — and
        # never when the cycle blocks. Falls back to the entry-axis percentile for any
        # older record that predates the entry_signal block.
        entry = c.get("entry") or {}
        status = entry.get("status")
        ep = c.get("entry_pct")
        if status:
            is_buy = status in ("buy_now", "partial") and not c.get("cycle_blocked")
        else:
            v = (c.get("verdict") or "").lower()
            is_buy = ("buy" in v or "add" in v or "leader" in v) and not c.get("cycle_blocked") \
                and (ep is None or ep >= 0.45)
        if is_buy and (c.get("score") or 0) >= 50:
            buys.append({"symbol": m.get("symbol"), "name": m.get("name"),
                         "score": c.get("score"), "verdict": c.get("verdict"),
                         "verdict_zh": c.get("verdict_zh"), "entry_pct": ep,
                         "entry_status": status, "act_level": entry.get("act_level"),
                         "zone_low": entry.get("zone_low"), "zone_high": entry.get("zone_high"),
                         "ret_20d": m.get("ret_20d"), "ret_ytd": m.get("ret_ytd"),
                         "rationale": m.get("rationale")})
    buys.sort(key=lambda x: (-(x.get("act_level") or 0), -(x.get("entry_pct") or 0), -(x.get("score") or 0)))
    if not buys:
        return {"status": "no_clean_entries", "buys": [], "uncovered": uncovered,
                "note_en": "Theme is in favour, but no member has a clean entry right now — most are extended or mid-trend. Wait for a pullback.",
                "note_zh": "主题尚可，但当前无成分股具备干净入场点 — 多数已延展或处于趋势中段。等待回调。"}
    return {"status": "ok", "buys": buys[:12], "uncovered": uncovered}


_BREADTH_DIR = {"us": "breadth", "china": "china_breadth",
                "hk": "hk_breadth", "canada": "canada_breadth", "intl": "intl_breadth"}


def market_concentration(region: str = "us") -> dict:
    """Broad-market narrowness from the region's breadth tape (the user's 'market is narrow now').

    Daily + 3-day + weekly + monthly advance-decline ratio, % above 50/200d, new-hi/lo, and a
    broad/narrowing/narrow verdict. Read-only over data/<region>_breadth/breadth.parquet; {} on
    miss (the section then hides)."""
    try:
        b = pd.read_parquet(config.data_dir() / _BREADTH_DIR.get(region, "breadth") / "breadth.parquet")
    except Exception:  # noqa: BLE001
        return {}
    if b.empty:
        return {}
    last = b.iloc[-1]
    def f(c):
        try:
            return float(last[c])
        except Exception:  # noqa: BLE001
            return None
    adv, dec = f("adv"), f("dec")
    # guard dec>0 explicitly — a falsy-but-negative dec would pass `and dec` and yield a
    # nonsensical negative advance/decline ratio.
    ad = round(adv / dec, 2) if (adv is not None and dec is not None and dec > 0) else None
    out = {"adv": int(adv) if adv is not None else None,
           "dec": int(dec) if dec is not None else None, "ad_ratio": ad,
           "pct_above_50": round(f("pct_above_50"), 1) if f("pct_above_50") is not None else None,
           "pct_above_200": round(f("pct_above_200"), 1) if f("pct_above_200") is not None else None,
           "nh": int(f("nh")) if f("nh") is not None else None,
           "nl": int(f("nl")) if f("nl") is not None else None,
           "directional": False}
    for lbl, n in (("ad_3d", 3), ("ad_w", 5), ("ad_m", 21)):
        seg = b.iloc[-n:]
        sa, sd = seg["adv"].sum(), seg["dec"].sum()
        out[lbl] = round(float(sa / sd), 2) if sd else None
    p50 = out["pct_above_50"]
    if ad is not None and p50 is not None:
        if ad < 0.95 and p50 < 45:
            out["verdict"], out["verdict_zh"] = "narrow", "狭窄"
        elif ad > 1.3 and p50 > 58:
            out["verdict"], out["verdict_zh"] = "broad", "广泛"
        else:
            out["verdict"], out["verdict_zh"] = "mixed", "中性"
    return out
