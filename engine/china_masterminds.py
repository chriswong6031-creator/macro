"""China Mastermind multi-asset GTAA — three active, conviction-weighted, vol-targeted
tactical asset-allocation flagships (Conservative / Moderate / Aggressive), restricted to the
MAINLAND-INVESTIBLE universe (A-share ETFs + onshore gold + China govt bonds; NO crypto,
NO US treasuries, NO US stocks).

The China sibling of engine/masterminds.py. It REUSES the asset-agnostic harness
(engine.active_alloc.backtest_portfolio / split_half_oos) and the price-orthogonal China
edges the validated china_strategies registry already ships — the credit IMPULSE (TSF),
margin-leverage euphoria, and the realized-vol regime — because A-shares mean-revert and
naive price-trend WHIPSAWS here (engine.china_allocation / china_strategies docstrings). So
the conviction DOWN-weights trend (0.30 vs the US 0.45) and leans on the diversification +
credit/vol REGIME layer (0.40).

Universe (asset -> class):
  EQ_BROAD  510300.SS  CSI 300            broad A-share, the benchmark
  EQ_GROWTH 159915.SZ  ChiNext            growth kicker
  INCOME    510880.SS  SSE Dividend       defensive-equity carry (2008->)
  BOND      511010.SS  5y CGB ETF         China govt duration (the only onshore govt-bond ETF)
  GOLD      518880.SS  onshore Gold ETF   SGE-linked RMB gold
  COMMOD    512400.SS  Nonferrous Metals  copper/aluminium producer equity — the China-holdable
                                          commodity proxy (a Mainland investor cannot easily hold
                                          a broad-commodity future; this carries embedded equity beta)

Sizing (shared with US masterminds): per-asset inverse-vol (risk parity) -> conviction tilt ->
per-name cap -> scale the book to the profile target vol -> leverage cap -> weekly rebalance.
Vol targets + leverage are deliberately ONE NOTCH BELOW the US flagships (A-shares are more
volatile + mean-reverting). Cash sleeve = flat ~1.8% (onshore cash earns little — de-risking
here is a drawdown trade, not a carry trade).

DISPLAY-ONLY / experimental: a NEW scored multi-asset book on PRIORS-based knobs (calibration
is a fast-follow, mirroring how Canada/TSX shipped). Net of 3 bps + 1% financing on the levered
part; weekly rebalance. Benchmark = CSI 300 buy-&-hold (and a China 40/60 equity/bond for the
conservative tier). The OOS split-half honesty panel is wired through aa.split_half_oos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import active_alloc as aa
from engine.china_strategies import (CHINA_CASH_PCT, _cnclose, _credit_derisk,
                                      _margin_derisk, _vol_derisk)
from engine.cross_asset_trend import tsmom_alloc

# universe (asset -> class); income/bond/gold are the carry-bearing defensive sleeves
EQ_BROAD, EQ_GROWTH, INCOME = ["510300.SS"], ["159915.SZ"], ["510880.SS"]
BOND, GOLD, COMMOD = ["511010.SS"], ["518880.SS"], ["512400.SS"]
ASSETS = EQ_BROAD + EQ_GROWTH + INCOME + BOND + GOLD + COMMOD
RISKY = ["510300.SS", "159915.SZ", "512400.SS"]
SAFE = ["511010.SS", "518880.SS", "510880.SS"]
ASSET_LABEL = {
    "510300.SS": ("CSI 300", "沪深300"), "159915.SZ": ("ChiNext (growth)", "创业板（成长）"),
    "510880.SS": ("SSE Dividend", "上证红利"), "511010.SS": ("China 5y Govt Bond", "5年国债"),
    "518880.SS": ("Gold (onshore)", "黄金"), "512400.SS": ("Nonferrous Metals", "有色金属"),
}
# structural carry tilt (constant) for the income/bond/gold sleeves — China lacks a clean
# tradable yield-curve series for a time-varying carry leg, so the carry factor is a small
# steady tilt toward the carry/store-of-value holdings (the diversifying sleeves).
STRUCT_CARRY = {"510880.SS": 0.5, "511010.SS": 0.5, "518880.SS": 0.25}

PROFILES: dict[str, dict] = {
    "conservative": {"target_vol": 0.05, "max_lev": 1.0, "w_cap": 0.35, "icon": "🛟",
                     "label_en": "Conservative", "label_zh": "保守", "bench": "cn6040",
                     "thesis_en": "Capital-preservation GTAA across A-shares, China bonds & gold — no leverage, diversified, leans on the credit-impulse & vol regime, not price trend.",
                     "thesis_zh": "横跨 A 股、国债与黄金的资本保全型全球配置——零杠杆、分散，依靠信用脉冲与波动率体制，而非价格趋势。"},
    "moderate": {"target_vol": 0.09, "max_lev": 1.3, "w_cap": 0.40, "icon": "⚖️",
                 "label_en": "Moderate", "label_zh": "均衡", "bench": "csi300",
                 "thesis_en": "Balanced China GTAA — the full A-share + bond + gold + metals book, lightly levered to the highest-conviction sleeves; aims to beat CSI 300 on risk-adjusted return with a far shallower drawdown.",
                 "thesis_zh": "均衡型中国全球配置——A 股＋国债＋黄金＋有色的完整组合，对最高信念的资产轻杠杆；力求在风险调整后收益上跑赢沪深300，回撤浅得多。"},
    "aggressive": {"target_vol": 0.15, "max_lev": 1.8, "w_cap": 0.50, "icon": "🚀",
                   "label_en": "Aggressive", "label_zh": "进取", "bench": "csi300",
                   "thesis_en": "Maximum-growth China GTAA — levers the strongest A-share / metals trends while the credit & vol regime allows, rotating hard to bonds + gold when it flips to de-risk.",
                   "thesis_zh": "增长最大化中国全球配置——在信用与波动率体制许可时，对最强的 A 股／有色趋势加杠杆；体制转为降险时则大举转向国债与黄金。"},
}
DEFAULT_PROFILE = "moderate"
_START = pd.Timestamp("2013-08-01")        # CGB(2013-03) + gold(2013-07) spine live
_REBAL = 5                                 # weekly rebalance (trading days)
_LAG = 2
_LAG_CREDIT = 22                           # ~1-month publication lag on the monthly TSF print
W_TREND, W_CARRY, W_REGIME, W_XMOM = 0.30, 0.15, 0.40, 0.15


def _prices() -> pd.DataFrame:
    px = {}
    for a in ASSETS:
        s = _cnclose(a)
        s = s[s > 0]
        if not s.empty:
            px[a] = s
    if "510300.SS" not in px or "511010.SS" not in px or "518880.SS" not in px:
        return pd.DataFrame()
    core = ("510300.SS", "511010.SS", "518880.SS")
    cal = px[core[0]].index.union(px[core[1]].index).union(px[core[2]].index)
    cal = cal[(cal >= _START) & (cal <= min(px[a].index[-1] for a in core))]
    return pd.DataFrame({a: px[a].reindex(cal).ffill() for a in px}, index=cal)


def _derisk_score(cal: pd.Index) -> pd.Series | None:
    """Blend the validated China de-risk legs (credit impulse / realized vol / margin
    euphoria) into one [0,1] series on the price calendar (1 = de-risk). Weighted mean of
    whichever legs have data on each date; None if none resolve."""
    legs: list[tuple[pd.Series, float]] = []
    try:
        cr = _credit_derisk()
        if not cr.empty:
            legs.append((cr.reindex(cal, method="ffill").shift(_LAG_CREDIT), 0.45))
    except Exception:  # noqa: BLE001
        pass
    try:
        v = _vol_derisk(_cnclose("510300.SS"))
        if not v.empty:
            legs.append((v.reindex(cal, method="ffill").shift(1), 0.35))
    except Exception:  # noqa: BLE001
        pass
    try:
        mg = _margin_derisk()
        if not mg.empty:
            legs.append((mg.reindex(cal, method="ffill").shift(1), 0.20))
    except Exception:  # noqa: BLE001
        pass
    if not legs:
        return None
    num = pd.Series(0.0, index=cal)
    den = pd.Series(0.0, index=cal)
    for s, w in legs:
        present = s.notna()
        num = num.add((s.fillna(0.0) * w).where(present, 0.0), fill_value=0.0)
        den = den.add(pd.Series(np.where(present, w, 0.0), index=cal), fill_value=0.0)
    return (num / den.replace(0, np.nan)).clip(0, 1)


def _conviction(P: pd.DataFrame) -> pd.DataFrame:
    """The 4-factor signed conviction per asset, floored at 0 (long-only book). China legs:
    TREND (down-weighted), structural CARRY, the credit/vol/margin REGIME, and X-MOM."""
    cal = P.index
    cols = [a for a in ASSETS if a in P.columns]
    # 1) trend (price-based, reused verbatim) — down-weighted for A-share mean-reversion
    trend = pd.DataFrame({a: tsmom_alloc(P[a]) for a in cols}, index=cal)
    # 2) structural carry tilt toward the income/bond/gold sleeves
    carry = pd.DataFrame(0.0, index=cal, columns=cols)
    for a, v in STRUCT_CARRY.items():
        if a in carry:
            carry[a] = v
    # 3) regime tilt — the validated China de-risk legs (credit impulse / vol / margin)
    regime = pd.DataFrame(0.0, index=cal, columns=cols)
    derisk = _derisk_score(cal)
    if derisk is not None:
        tilt = ((derisk - 0.5) * 2.0).clip(-1, 1)        # +1 = de-risk
        for a in cols:
            if a in RISKY:
                regime[a] = (-tilt).clip(-1, 1)
            elif a in SAFE:
                regime[a] = tilt.clip(-1, 1)
    # 4) cross-asset relative momentum (126d)
    xrank = P.pct_change(126).rank(axis=1, pct=True)
    xmom = (2 * xrank - 1).fillna(0.0)
    conv = (W_TREND * trend + W_CARRY * carry.fillna(0) + W_REGIME * regime + W_XMOM * xmom)
    return conv.clip(-1, 1).clip(lower=0.0)              # long-only


def _weights(P: pd.DataFrame, prof: dict) -> pd.DataFrame:
    """Inverse-vol, conviction-tilted weights -> per-name cap -> book vol-target ->
    leverage cap -> weekly rebalance. (Shared with engine.masterminds._weights.)"""
    cal = P.index
    ret = P.pct_change()
    conv = _conviction(P)
    rv = (ret.rolling(21).std() * np.sqrt(aa.TRADING_YEAR)).clip(lower=0.05)
    raw = (conv * (0.10 / rv)).fillna(0.0)
    for a in P.columns:                                 # zero each asset until ~300d history
        fv = P[a].first_valid_index()
        if fv is not None:
            raw.loc[raw.index < fv + pd.Timedelta(days=300), a] = 0.0
    raw = raw.clip(upper=prof["w_cap"])
    port_vol = ((raw.shift(1) * ret).sum(axis=1).rolling(63).std() * np.sqrt(aa.TRADING_YEAR)).clip(lower=0.02)
    W = raw.mul((prof["target_vol"] / port_vol).clip(upper=3.0), axis=0)
    gross = W.abs().sum(axis=1)
    W = W.mul((prof["max_lev"] / gross.replace(0, np.nan)).clip(upper=1.0).fillna(1.0), axis=0).fillna(0.0)
    hold = pd.Series(False, index=cal)
    hold.iloc[::_REBAL] = True
    return W.where(hold).ffill().fillna(0.0)


def _bill(cal: pd.Index) -> pd.Series:
    return pd.Series(float(CHINA_CASH_PCT), index=cal)


def backtest(profile_key: str = DEFAULT_PROFILE, P: pd.DataFrame | None = None) -> dict:
    P = P if P is not None else _prices()
    if P.empty:
        return {"error": "no data"}
    prof = PROFILES[profile_key]
    W = _weights(P, prof)
    bill = _bill(P.index)
    # put CSI 300 first so the portfolio scorecard's hodl_* = CSI 300 buy-&-hold
    cols = ["510300.SS"] + [c for c in P.columns if c != "510300.SS"]
    bt = aa.backtest_portfolio(W[cols], P[cols], bill, cost_bps=3.0)
    # China 40/60 (equity/bond) benchmark for the conservative tier
    b6040 = None
    if "511010.SS" in P.columns:
        w46 = pd.DataFrame({"510300.SS": 0.4, "511010.SS": 0.6}, index=P.index)
        b6040 = aa.backtest_portfolio(w46, P[["510300.SS", "511010.SS"]], bill, cost_bps=1.0)
    if prof["bench"] == "cn6040" and "511010.SS" in P.columns:
        bench_ret = 0.4 * P["510300.SS"].pct_change().fillna(0) + 0.6 * P["511010.SS"].pct_change().fillna(0)
    else:
        bench_ret = P["510300.SS"].pct_change().fillna(0)
    oos = aa.split_half_oos(bt["net"], bench_ret)
    last = W.iloc[-1]
    alloc = [{"asset": a, "label_en": ASSET_LABEL[a][0], "label_zh": ASSET_LABEL[a][1],
              "weight": round(float(last[a]) * 100, 1)} for a in W.columns if abs(last.get(a, 0)) > 1e-4]
    alloc.sort(key=lambda x: -x["weight"])
    return {"profile": profile_key, "scorecard": bt, "bench6040": b6040, "weights": W,
            "oos": oos, "alloc": alloc, "gross_now": round(float(last.abs().sum()), 2),
            "asof": str(P.index[-1].date())}
