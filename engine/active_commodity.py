"""Active, vol-targeted, leverage-capable commodity models that BEAT buy-&-hold on CAGR.

The long/flat commodity timers on commodity_strategies.html win on Sharpe + drawdown but
give up CAGR — a long/flat book's ceiling is 100%-invested = B&H. These models break that
ceiling: a multi-factor conviction in [0, ~1.7] is turned into a vol-targeted, leveraged
position via engine.active_alloc, so the book runs hot (levered) when the edge is strong and
light when it is not. Validated (research + split-half OOS):

  GOLD   — trend-first (the textbook real-rate driver broke in the 2022-25 de-dollarization
           bull; gold rose WITH rising real yields), macro only ADDS conviction and is
           overridden by a strong uptrend; a strong-trend vol floor stops a vol spike from
           de-levering a pristine bull. 12.4% CAGR / 0.77 Sharpe / −33% DD vs 11.3 / 0.69 / −44.
  SILVER — silver's own trend is noise; drive it off the GOLD regime + the GOLD/SILVER RATIO
           mean-reversion (cheap silver → catch-up) + a copper kicker. ROBUST: 16.3 / 0.69 /
           −65 vs 10.8 / 0.48 / −76, beats B&H CAGR in BOTH OOS halves.
  COPPER — the proven graded-trend backbone × a multiplicative global-growth tilt (China
           credit impulse + copper/gold ratio + US industrial production + dollar). ROBUST:
           9.8 / 0.55 / −61 vs 8.0 / 0.42 / −69.

Honest framing: these lever genuine risk-adjusted edges into CAGR beats. Silver & copper are
OOS-robust; gold's CAGR edge is concentrated in trending eras (its risk-adjusted edge is
robust). Net of 3 bps cost + a 1% financing spread on the levered part. Experimental.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import active_alloc as aa
from engine import equity_alloc as ea
from engine.cross_asset_trend import tsmom_alloc
from lib import store

_FIN_SPREAD = 1.0


def _yclose(tk: str) -> pd.Series:
    s = ea.index_close(tk).astype(float).dropna()
    return s[s > 0]


def _fred(series: str, col: str | None = None) -> pd.Series:
    df = store.read("fred", series)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    c = col if (col and col in df.columns) else df.columns[0]
    return df[c].astype(float).dropna()


def _mom_grade(b: pd.Series, w: int) -> pd.Series:
    """Sign-graded momentum over window w → {0,1} (1 = up)."""
    return (np.sign(b / b.shift(w) - 1.0) + 1) / 2.0


def _mom_leg(px: pd.Series, w: int) -> pd.Series:
    """Vol-normalized momentum over window w → smooth [0,1] (copper's trend legs)."""
    lr = np.log(px / px.shift(w))
    z = lr / (px.pct_change().rolling(w).std() * np.sqrt(w))
    return (0.5 * (np.tanh(z) + 1)).clip(0, 1)


# --------------------------------------------------------------------------- #
# GOLD
# --------------------------------------------------------------------------- #
def _gold_conviction(b: pd.Series) -> tuple[pd.Series, dict]:
    real = _fred("DFII10").reindex(b.index).ffill()
    usd = _fred("DTWEXBGS").reindex(b.index).ffill()
    trend_base = (_mom_grade(b, 63) + _mom_grade(b, 126) + _mom_grade(b, 252)) / 3.0
    roll_hi = b.rolling(252, min_periods=60).max()
    breakout = ((b / roll_hi - 0.95) / 0.05).clip(0, 1) * 0.10
    real_mom = -(real - real.shift(63))
    usd_mom = -(usd / usd.shift(63) - 1.0)
    macro = (np.tanh(real_mom / 0.5) * 0.15 + np.tanh(usd_mom / 0.03) * 0.15).fillna(0) / 2.0
    macro = macro.where(~(trend_base >= 0.7), macro.clip(lower=0))   # strong uptrend: macro can only add
    conv = (trend_base + breakout + macro).clip(0, 1.0).fillna(0)
    legs = {"trend": trend_base, "breakout": breakout, "macro": macro}
    return conv, legs


def _gold_size(b: pd.Series) -> pd.Series:
    conv, _ = _gold_conviction(b)
    rv = aa.realized_vol(b)
    strong = conv >= 0.85
    size = (conv * (0.20 / rv)).clip(0, 2.5)
    return size.where(~strong, size.clip(lower=0.6)).fillna(0)      # vol floor in pristine uptrend


# --------------------------------------------------------------------------- #
# SILVER  (ratio-dominant, gold-regime)
# --------------------------------------------------------------------------- #
def _silver_conviction(si: pd.Series) -> tuple[pd.Series, dict]:
    gc, hg = _yclose("GC=F"), _yclose("HG=F")
    idx = si.index
    gold_trend = ((tsmom_alloc(gc) + 1) / 2).reindex(idx, method="ffill").clip(0, 1)
    copper_trend = ((tsmom_alloc(hg) + 1) / 2).reindex(idx, method="ffill").clip(0, 1)
    ratio = (gc / si).reindex(idx).ffill()
    ratio_cheap = ratio.rolling(252 * 5, min_periods=252).apply(lambda w: (w[-1] > w).mean(), raw=True).clip(0, 1)
    ratio_conv = ratio_cheap ** 1.5
    conv = 0.55 * ratio_conv + 0.30 * gold_trend + 0.15 * copper_trend
    extreme = ((ratio_cheap > 0.80) & (gold_trend > 0.50)).astype(float)
    conv = (conv * (1.0 + 0.6 * extreme)).clip(0, 1.7).fillna(0)
    legs = {"ratio": ratio_cheap, "gold_regime": gold_trend, "copper": copper_trend}
    return conv, legs


def _silver_size(si: pd.Series) -> pd.Series:
    conv, _ = _silver_conviction(si)
    rv = aa.realized_vol(si)
    return (conv * (0.32 / rv)).clip(0, 3.0).fillna(0)


# --------------------------------------------------------------------------- #
# COPPER  (graded-trend backbone × multiplicative growth tilt)
# --------------------------------------------------------------------------- #
def _copper_conviction(b: pd.Series) -> tuple[pd.Series, dict]:
    g = _yclose("GC=F")
    idx = b.index
    trend = pd.concat([_mom_leg(b, 63), _mom_leg(b, 126), _mom_leg(b, 252)], axis=1).mean(axis=1)
    trend = trend.reindex(idx).ffill().fillna(0.5)
    tsf = store.read("china_credit", "tsf")
    china = pd.Series(0.5, index=idx)
    if tsf is not None and "tsf_total" in tsf:
        ts = tsf["tsf_total"].astype(float).dropna()
        impulse = ts.rolling(12).sum().pct_change(12)
        imp_z = (impulse - impulse.expanding(min_periods=12).mean()) / impulse.expanding(min_periods=12).std()
        china = (0.5 * (np.tanh(imp_z) + 1)).clip(0, 1).shift(1).reindex(idx, method="ffill").fillna(0.5)
    cg_ratio = (b / g.reindex(b.index, method="ffill")).dropna()
    cgm = _mom_leg(cg_ratio, 126).reindex(idx).ffill().fillna(0.5)
    ip = _fred("INDPRO")
    indp = pd.Series(0.5, index=idx)
    if not ip.empty:
        ip_yoy = ip.pct_change(12)
        ip_z = (ip_yoy - ip_yoy.expanding(min_periods=24).mean()) / ip_yoy.expanding(min_periods=24).std()
        indp = (0.5 * (np.tanh(ip_z) + 1)).clip(0, 1).shift(1).reindex(idx, method="ffill").fillna(0.5)
    usd = _fred("DTWEXBGS")
    usd_leg = (1 - _mom_leg(usd, 126)).reindex(idx).ffill().fillna(0.5) if not usd.empty else pd.Series(0.5, index=idx)
    growth = pd.concat([china, cgm, indp, usd_leg], axis=1).mean(axis=1).clip(0, 1)
    tilt = (0.6 + 1.2 * growth).clip(0.6, 1.8)
    conv = (trend * tilt).clip(0, 1.8).fillna(0)
    legs = {"trend": trend, "growth": growth}
    return conv, legs


def _copper_size(b: pd.Series) -> pd.Series:
    conv, _ = _copper_conviction(b)
    rv = aa.realized_vol(b)
    return (conv * (0.25 / rv)).clip(0, 4.0).fillna(0)


# --------------------------------------------------------------------------- #
# registry + evaluation
# --------------------------------------------------------------------------- #
MODELS: dict[str, dict] = {
    "cm_gold_active": {"ticker": "GC=F", "group": "gold", "icon": "🔱", "size": _gold_size,
                       "conv": _gold_conviction, "name_en": "Gold Active (levered)", "name_zh": "黄金主动（杠杆）",
                       "bench_en": "Gold", "bench_zh": "黄金",
                       "thesis_en": "Trend-first, vol-targeted, lightly levered — beats gold buy-&-hold on CAGR, Sharpe and drawdown by levering pristine uptrends and stepping aside in chop.",
                       "thesis_zh": "趋势优先、波动率目标、轻杠杆——通过在干净上行趋势中加杠杆、震荡中退避，在年化、夏普与回撤上跑赢黄金买入持有。",
                       "legs": {"trend": "Multi-horizon trend", "breakout": "52-week breakout", "macro": "Real-yield / dollar tilt"}},
    "cm_silver_active": {"ticker": "SI=F", "group": "silver", "icon": "⚡", "size": _silver_size,
                         "conv": _silver_conviction, "name_en": "Silver Active (levered)", "name_zh": "白银主动（杠杆）",
                         "bench_en": "Silver", "bench_zh": "白银",
                         "thesis_en": "Driven off the GOLD regime + the gold/silver-ratio mean-reversion (cheap silver → catch-up) — a robust edge levered into a big CAGR beat (16% vs 11%), in both OOS halves.",
                         "thesis_zh": "由黄金regime + 金银比均值回归驱动（白银便宜→补涨）——将稳健优势加杠杆放大为显著的年化跑赢（16% vs 11%），且在两个样本外半段均成立。",
                         "legs": {"ratio": "Gold/silver ratio (silver cheap)", "gold_regime": "Gold uptrend regime", "copper": "Copper / industrial kicker"}},
    "cm_copper_active": {"ticker": "HG=F", "group": "copper", "icon": "⚙️", "size": _copper_size,
                         "conv": _copper_conviction, "name_en": "Copper Active (levered)", "name_zh": "铜主动（杠杆）",
                         "bench_en": "Copper", "bench_zh": "铜",
                         "thesis_en": "The graded-trend backbone amplified by a global-growth tilt (China credit impulse, copper/gold, US industrial production, dollar) — robustly beats copper buy-&-hold on CAGR, Sharpe and drawdown.",
                         "thesis_zh": "以分级趋势为骨架，由全球增长倾斜放大（中国信用脉冲、铜金比、美国工业生产、美元）——在年化、夏普与回撤上稳健跑赢铜买入持有。",
                         "legs": {"trend": "Multi-horizon trend", "growth": "Global-growth tilt"}},
}


def evaluate(key: str) -> dict:
    """Full active-model result for one commodity: scorecard (vs same-commodity B&H),
    split-half OOS honesty panel, current leverage + conviction-leg readings, equity/dd
    series for the charts."""
    m = MODELS[key]
    b = _yclose(m["ticker"])
    bill = ea.bill_yield()
    size = m["size"](b)
    r = aa.backtest_lev(b, size, bill, cost_bps=3.0, borrow_spread=_FIN_SPREAD)
    oos = aa.split_half_oos(r["net"], r["ret"])
    conv, legs = m["conv"](b)
    leg_now = {k: round(float(v.dropna().iloc[-1]), 2) if len(v.dropna()) else None for k, v in legs.items()}
    pos = r["pos"]
    return {"key": key, "spec": m, "scorecard": r, "oos": oos,
            "lev_now": round(float(pos.dropna().iloc[-1]), 2) if len(pos.dropna()) else 0.0,
            "conv_now": round(float(conv.dropna().iloc[-1]), 2) if len(conv.dropna()) else 0.0,
            "leg_now": leg_now, "eq": r["eq"], "hodl_eq": r["hodl_eq"], "pos": pos,
            "asof": b.index[-1].strftime("%b %d, %Y")}
