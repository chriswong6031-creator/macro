"""engine/china_signals.py — A-share-specific signals the US stack can't supply.

The US technical/score logic assumes things that do NOT transfer to A-shares (3–12m momentum,
VIX-as-fear, the low-vol/size/quality anomalies). This module adds the China-validated reads,
all CLOSE-ONLY (A-shares carry no per-stock OHLCV in the panel):

  • the **QVIX vol-regime confirmer** — the GEX-analog for a market with no single-stock options,
    with the US interpretation INVERTED: China has a *positive* return-volatility correlation
    (anti-leverage), so a high QVIX *level* is not "fear". We gate on `qvix_z` (vs its own 60d),
    not the level — a panic SPIKE taxes a chase; a suppressed/compressed regime is constructive.
  • a **margin-financing (融资余额) crowding** risk — a surging financing balance is the 2015
    fire-sale mechanism (leverage crowding), a contrarian RISK, never a positive.
  • close-only **short-term-reversal** technicals (RSI-5/10 with tighter A-share thresholds, the
    5-day return, distance-from-MA20) + the MA120 trend-regime gate + a price-LIMIT / board-type
    flag — used for display + a reversal-setup read.

Research basis: reports/CHINA_STOCKS_OVERHAUL.md (Jansen-Swinkels-Zhou 2021; the QVIX
anti-leverage finding; the 2015 leverage-fire-sale literature; price-limit magnet-effect studies).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(v) or np.isinf(v)) else v


# ---------------------------------------------------------------------------
# board type + price-limit width (STAR/ChiNext = ±20%, main board = ±10%)
# ---------------------------------------------------------------------------
def board_type(ticker: str) -> tuple[str, float]:
    """(board, daily_limit_pct) from the ticker. STAR (688xxx.SS) and ChiNext (300/301xxx.SZ)
    have ±20% limits and faster reversal; Beijing (8/4xxxx.BJ) ±30%; main board ±10%."""
    t = (ticker or "").upper().split(".")[0]
    if t.startswith("688") or t.startswith("689"):
        return "star", 20.0
    if t.startswith("300") or t.startswith("301"):
        return "chinext", 20.0
    if t.startswith(("8", "4", "92")):
        return "bse", 30.0
    return "main", 10.0


# ---------------------------------------------------------------------------
# short-term reversal technicals (close-only)
# ---------------------------------------------------------------------------
def _rsi(close: pd.Series, n: int) -> float | None:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    v = (100 - 100 / (1 + rs)).iloc[-1]
    return _f(v)


def ashare_tech(close: pd.Series, ticker: str = "") -> dict:
    """A-share close-only reversal read. RSI uses SHORTER windows (5/10) with TIGHTER thresholds
    than the US (overreaction cycles are faster); the MA120 gate says whether reversal-buys are in
    a supportive uptrend; the price-limit flag marks a ±limit day (continuation day+1, fade after)."""
    c = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    out: dict = {"rsi5": None, "rsi10": None, "ret_5d": None, "dist_ma20_z": None,
                 "above_ma120": None, "ma20_slope_up": None, "limit_flag": None,
                 "board": board_type(ticker)[0], "reversal_setup": None}
    if len(c) < 130:
        return out
    out["rsi5"] = _rsi(c, 5)
    out["rsi10"] = _rsi(c, 10)
    if len(c) > 5:
        out["ret_5d"] = round(float(c.iloc[-1] / c.iloc[-6] - 1.0) * 100, 1)
    ma20 = c.rolling(20, min_periods=20).mean()
    sd20 = c.rolling(20, min_periods=20).std(ddof=0)
    if pd.notna(ma20.iloc[-1]) and sd20.iloc[-1]:
        out["dist_ma20_z"] = round(float((c.iloc[-1] - ma20.iloc[-1]) / sd20.iloc[-1]), 2)
    ma120 = c.rolling(120, min_periods=120).mean()
    if pd.notna(ma120.iloc[-1]):
        out["above_ma120"] = bool(c.iloc[-1] > ma120.iloc[-1])
    if ma20.notna().sum() > 6:
        out["ma20_slope_up"] = bool(ma20.iloc[-1] > ma20.iloc[-6])
    # price-limit flag: a daily SIMPLE move within 0.5pp of the board's ±limit is a (near-)limit event
    last_ret = float(c.iloc[-1] / c.iloc[-2] - 1.0) if len(c) > 1 and c.iloc[-2] > 0 else 0.0
    _, lim = board_type(ticker)
    out["limit_flag"] = ("up" if last_ret > 0 and abs(last_ret) >= (lim - 0.5) / 100.0
                         else "down" if last_ret < 0 and abs(last_ret) >= (lim - 0.5) / 100.0
                         else None)
    # reversal SETUP: oversold (RSI-10 < threshold) AND a constructive regime (above MA120) AND not
    # mid-limit-down. Threshold tightens in a downtrend (research: require deeper oversold off-trend).
    rsi10 = out["rsi10"]
    if rsi10 is not None and out["above_ma120"] is not None:
        thr = 30.0 if out["above_ma120"] else 22.0
        out["reversal_setup"] = bool(rsi10 < thr and out["limit_flag"] != "down")
    return out


# ---------------------------------------------------------------------------
# QVIX vol-regime confirmer — the GEX-analog (INVERTED vs US)
# ---------------------------------------------------------------------------
QVIX_DEFAULTS = {"panic_z": 2.0, "elevated_z": 1.0, "calm_z": -1.0, "win": 60}


def qvix_regime(qvix_close: pd.Series, cfg: dict | None = None) -> dict | None:
    """Market vol-regime from QVIX (China VIX, from 50/300-ETF options). Returns a CONFIRM/NEUTRAL/
    CAUTION verdict + a `stress` 0..1 (for the conviction risk overlay). CRITICAL: gate on `qvix_z`
    (vs its own 60d), NOT the level — China's positive return-vol correlation means a high QVIX
    *level* often accompanies a speculative rally, so the absolute level is not fear. A panic SPIKE
    (z high) is the crash-risk regime → CAUTION/stress; a suppressed regime (z low) is constructive
    (compressed vol → a reversal can release cleanly)."""
    cf = {**QVIX_DEFAULTS, **(cfg or {})}
    q = pd.to_numeric(qvix_close, errors="coerce").dropna().astype(float)
    if len(q) < cf["win"] + 5:
        return None
    mu = q.rolling(cf["win"], min_periods=cf["win"] // 2).mean()
    sd = q.rolling(cf["win"], min_periods=cf["win"] // 2).std(ddof=0)
    z = _f((q.iloc[-1] - mu.iloc[-1]) / sd.iloc[-1]) if sd.iloc[-1] else None
    level = _f(q.iloc[-1])
    pctile = _f((q <= q.iloc[-1]).tail(252).mean())
    if z is None:
        return None
    if z >= cf["panic_z"]:
        regime, verdict, stress = "panic", "caution", 0.6
        en = "QVIX panic spike — vol expanding fast; halt new chases, even oversold names keep falling"
        zh = "QVIX 恐慌飙升 — 波动快速放大；暂停追高，超卖股也可能续跌"
    elif z >= cf["elevated_z"]:
        regime, verdict, stress = "elevated", "neutral", 0.3
        en = "QVIX elevated vs its 60d — size down, require deeper oversold for reversal entries"
        zh = "QVIX 相对 60 日偏高 — 减小仓位，反转入场需更深超卖"
    elif z <= cf["calm_z"]:
        regime, verdict, stress = "suppressed", "confirm", 0.0
        en = "QVIX suppressed (compressed vol) — a coiled regime; clean reversal releases more likely"
        zh = "QVIX 受抑（波动压缩）— 蓄势区制；反转更易顺畅释放"
    else:
        regime, verdict, stress = "normal", "neutral", 0.0
        en = "QVIX normal — full signal operation"
        zh = "QVIX 正常 — 信号正常运作"
    return {"regime": regime, "verdict": verdict, "qvix_z": round(z, 2),
            "level": round(level, 1) if level is not None else None,
            "pctile": round(pctile, 2) if pctile is not None else None,
            "stress": stress, "en": en, "zh": zh,
            "caveat": "Index-vol QVIX (no single-stock options in A-shares); read as a market regime, "
                      "not a per-stock signal. China's positive return-vol link inverts the US 'high VIX = fear'.",
            "caveat_zh": "指数波动率 QVIX（A 股无个股期权）；为市场区制而非个股信号。中国正的收益-波动相关性"
                         "使其与美式“高 VIX=恐慌”相反。"}


# ---------------------------------------------------------------------------
# margin-financing (融资余额) crowding risk
# ---------------------------------------------------------------------------
def margin_crowding(chg_pct: float | None, pct_mcap: float | None = None) -> dict | None:
    """A surging margin (融资) balance = leverage crowding = the 2015 fire-sale mechanism: a
    contrarian RISK read, never a positive. Returns {risk 0..1, band, crowded}. chg_pct is the ~20d
    financing-balance change %; pct_mcap is financing / market cap (an absolute crowding gauge)."""
    chg = _f(chg_pct)
    pm = _f(pct_mcap)
    if chg is None and pm is None:
        return None
    # rapid balance build (>+12% over ~a month) OR a high absolute financing/mcap (>8%) = crowded
    r_chg = float(np.clip(((chg or 0.0) - 4.0) / 16.0, 0.0, 1.0))      # +4%→0, +20%→1
    r_abs = float(np.clip(((pm or 0.0) - 4.0) / 8.0, 0.0, 1.0))        # 4%→0, 12%→1
    risk = max(r_chg, r_abs)
    band = "crowded" if risk >= 0.6 else "elevated" if risk >= 0.3 else "normal"
    return {"risk": round(risk, 2), "band": band, "crowded": risk >= 0.6,
            "chg_pct": round(chg, 1) if chg is not None else None,
            "pct_mcap": round(pm, 1) if pm is not None else None}
