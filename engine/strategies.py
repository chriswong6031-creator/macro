"""Tactical-strategy REGISTRY — the scalable backbone behind the Strategies hub.

A strategy here is just three Series the (asset-agnostic) backtest harness already
knows how to consume:
    benchmark  — a total-return price Series of the risk asset
    alloc      — a weight in [0,1] (long/flat; next-bar lag applied by backtest_core)
    cash_yield — the annualized % the flat sleeve earns (T-bills / Treasuries)
plus an optional 0-100 `score` with a per-leg BREAKDOWN (same shape as
equity_alloc.risk_legs) so the detail page can show WHY, not just a number.

Each strategy is one frozen `StrategySpec` of pure factory callables; adding a future
strategy = append one spec. The expensive macro inputs (build_features /
conditions_frame / regime) are built ONCE in `_ctx()` and shared across all strategies.

Strategy #1 (S&P / Macro Vector) is a thin WRAPPER over the existing, validated
engine.equity_alloc.vector_alloc — its behavior is unchanged (its live page is still
rendered by the untouched scripts.build_spvector). The two NEW strategies (Credit Carry,
Duration Timing) are macro-factor-driven yield harvesters, built defensively per the
research: the durable edge is timing the LEFT TAIL that destroys the yield (de-risk into
Treasuries/cash before the recession drawdown), not chasing the yield. Shipped
experimental, full Phase-0 (leave-one-crisis-out / DSR gate) as a fast-follow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine import total_return as tr
from lib import store


# --------------------------------------------------------------------------- #
# spec
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategySpec:
    key: str                      # url/file slug (strategy_<key>.html)
    name_en: str
    name_zh: str
    thesis_en: str                # one-line scorecard subtitle
    thesis_zh: str
    icon: str
    bench_en: str                 # risk-asset label ("S&P 500", "High-yield credit")
    bench_zh: str
    cash_en: str                  # flat-sleeve label ("T-bills", "Treasuries")
    cash_zh: str
    risk_word_en: str             # what the score measures ("Macro risk", "Credit stress")
    risk_word_zh: str
    # the three factories the harness needs (ctx is the shared feature bundle)
    benchmark: Callable[[dict], pd.Series]
    alloc: Callable[[dict, pd.Series], pd.Series]
    cash_yield: Callable[[dict], pd.Series]
    risk_yield: Callable[[dict], pd.Series]          # risk-asset income (% ann) for the headline
    score: Callable[[dict, pd.Series], dict] | None  # {"score": Series, "legs": {...}} or None
    bands: tuple = (25, 50, 75)
    cost_bps: float = 3.0
    experimental: bool = False
    caveat_en: str = ""
    caveat_zh: str = ""
    own_page: str | None = None   # if set, the hub card links here instead of strategy_<key>.html


def _ctx() -> dict:
    """Build the shared macro feature bundle ONCE for all strategies (expensive)."""
    from engine.inputs import build_features
    from engine.conditions import conditions_frame
    f = build_features()
    cf = conditions_frame(f)
    reg = store.read("regime", "regime_history")
    return {"f": f, "cf": cf, "regime": reg}


# --------------------------------------------------------------------------- #
# score composer — mirrors equity_alloc.risk_legs so the detail page reuses the
# exact same leg-breakdown rendering (renormalized weighted mean of [0,1] legs).
# --------------------------------------------------------------------------- #
def _compose(legs: dict[str, dict], idx: pd.Index) -> dict:
    """legs: {name: {"series": Series in [0,1] (already PIT-lagged), "weight": float,
    "label": str, "lag": int}}. Returns {"score": 0-100 Series, "legs": {name: {label,
    weight, lag, active, series(0-100), value, points}}} where `points` across active
    legs sums to the composite at the as-of date (legible, not a black box)."""
    # ffill each leg onto the common index: a leg sourced from a FRED series that
    # publishes/ends a few days before the benchmark's last bar would otherwise read
    # NaN at the as-of date and silently drop out of the composite (causal — ffill only
    # carries PAST readings forward, never future).
    al = {n: {**d, "series": d["series"].reindex(idx).ffill()} for n, d in legs.items()}
    num = sum(d["series"].fillna(0) * d["weight"] for d in al.values())
    den = sum(d["series"].notna().astype(float) * d["weight"] for d in al.values())
    score = (100.0 * num / den.replace(0, np.nan)).clip(0, 100)
    sc = score.dropna()
    asof = sc.index[-1] if len(sc) else None
    den_at = float(den.loc[asof]) if asof is not None and pd.notna(den.loc[asof]) and den.loc[asof] else None
    out: dict[str, dict] = {}
    for n, d in al.items():
        si = d["series"].get(asof, np.nan) if asof is not None else np.nan
        active = pd.notna(si)
        value = round(100.0 * float(si), 1) if active else None
        points = (round(100.0 * d["weight"] * float(si) / den_at, 1)
                  if active and den_at else None)
        out[n] = {"label": d["label"], "weight": d["weight"], "lag": d.get("lag", 0),
                  "active": bool(active), "series": (d["series"] * 100.0).clip(0, 100),
                  "value": value, "points": points}
    return {"score": score, "legs": out}


def _pctile(s: pd.Series, window: int) -> pd.Series:
    from engine.indicators import pct_rank_window
    return pct_rank_window(s, window)


# =========================================================================== #
# Strategy 1 — S&P / Macro Vector (wrapper over the validated engine; unchanged)
# =========================================================================== #
def _spvector_bench(ctx):
    return ea.index_close("SPY")


def _spvector_cash(ctx):
    return ea.bill_yield()


def _spvector_alloc(ctx, bench):
    return ea.vector_alloc(bench, f=ctx["f"], regime=ctx["regime"], cf=ctx["cf"])


def _spvector_score(ctx, bench):
    return ea.risk_legs(ctx["f"], ctx["regime"], ctx["cf"])


def _spvector_riskyield(ctx):
    # S&P 500 dividend yield ≈ 1.3% currently (the adjusted-close benchmark has no
    # separate dividend series; a static display constant for the income headline).
    b = ea.index_close("SPY")
    return pd.Series(1.3, index=b.index)


SPVECTOR = StrategySpec(
    key="spvector", icon="📈",
    name_en="S&P / Macro Vector", name_zh="标普宏观向量",
    thesis_en="Stay-in / step-out: the broad US index vs T-bills on a 0–100 macro risk score.",
    thesis_zh="进出场：美国大盘指数与短期国债之间，按 0–100 宏观风险分数切换。",
    bench_en="S&P 500", bench_zh="标普500", cash_en="T-bills", cash_zh="短期国债",
    risk_word_en="Macro risk", risk_word_zh="宏观风险",
    benchmark=_spvector_bench, alloc=_spvector_alloc, cash_yield=_spvector_cash,
    risk_yield=_spvector_riskyield, score=_spvector_score,
    experimental=False, own_page="spvector.html")


# =========================================================================== #
# Strategy 2 — Credit Carry (HY credit total-return ↔ Treasuries)
# =========================================================================== #
def _credit_bench(ctx):
    return tr.hy_tr()


def _credit_cash(ctx):
    return tr.treasury_cash_yield()          # de-risked sleeve sits in 5y Treasuries


def _credit_riskyield(ctx):
    return tr.hy_yield()                      # HY yield-to-worst proxy (5y + OAS)


def _credit_score(ctx, bench) -> dict:
    """0-100 CREDIT-stress score (higher = de-risk HY → Treasuries). Three legs,
    renormalized weighted mean — reuses the repo's validated credit/recession/vol
    gauges; the de-risk leg IS the edge (cut HY before the default/liquidity drawdown
    that claws the carry back), per the credit-risk-premium-is-cyclical research."""
    f, cf = ctx["f"], ctx["cf"]
    idx = cf.index
    legs: dict[str, dict] = {}
    if "hy_oas" in f.columns and f["hy_oas"].notna().any():
        widen = _pctile(f["hy_oas"].diff(63), 252 * 5)          # HY-OAS 63d RoC percentile
        legs["hy_widening"] = {"series": widen.shift(3).clip(0, 1), "weight": 1.0,
                               "lag": 3, "label": "Credit stress (HY-OAS widening)"}
    if "recession_risk" in cf:
        legs["recession"] = {"series": (cf["recession_risk"] / 100.0).shift(22).clip(0, 1),
                             "weight": 1.0, "lag": 22, "label": "Recession risk"}
    if "vrp_pctile" in cf:
        legs["vol"] = {"series": cf["vrp_pctile"].shift(3).clip(0, 1), "weight": 0.5,
                       "lag": 3, "label": "Equity vol-risk premium (risk-off)"}
    return _compose(legs, idx)


def _credit_alloc(ctx, bench):
    """Graded HY weight from the credit score via the same hysteretic glide path as the
    vector (5-day debounce). Re-entry is symmetric: when credit calms back to band 0 the
    book rotates back into HY to re-harvest the carry. No aggressive spread-chasing."""
    sc = _credit_score(ctx, bench)["score"]
    return ea.glide_path(sc).reindex(bench.index, method="ffill").fillna(1.0)


CREDIT_CARRY = StrategySpec(
    key="credit_carry", icon="💳",
    name_en="Credit Carry", name_zh="信用套息",
    thesis_en="Harvest the high-yield carry; rotate to Treasuries before the default cycle claws it back.",
    thesis_zh="收割高收益债票息；在违约周期吞噬之前轮动至国债。",
    bench_en="High-yield credit (TR)", bench_zh="高收益信用债（总回报）",
    cash_en="Treasuries", cash_zh="国债",
    risk_word_en="Credit stress", risk_word_zh="信用压力",
    benchmark=_credit_bench, alloc=_credit_alloc, cash_yield=_credit_cash,
    risk_yield=_credit_riskyield, score=_credit_score,
    experimental=True,
    caveat_en="High-yield total return = HYG dividend-adjusted close (≈ ICE BofA HY TR; "
              "the authoritative index is used when cached in CI). History begins 2007 "
              "(HYG inception) — a small independent-bear sample. Experimental, under validation.",
    caveat_zh="高收益总回报 = HYG 经分红调整收盘价（≈ ICE BofA 高收益总回报指数；CI 缓存时使用权威指数）。"
              "历史自 2007 年（HYG 成立）起，独立熊市样本较小。实验性，验证中。")


# =========================================================================== #
# Strategy 3 — Duration / Treasury Timing (long Treasuries TR ↔ short/cash)
# =========================================================================== #
def _duration_bench(ctx):
    return tr.long_treasury_tr()


def _duration_cash(ctx):
    return ea.bill_yield()                    # de-risked sleeve sits in T-bills


def _duration_riskyield(ctx):
    return tr.long_yield()                    # 30y Treasury yield


def _term_spread() -> pd.Series:
    d10 = store.read("fred", "DGS10")
    d3 = store.read("fred", "DTB3")
    if d10 is None or d3 is None:
        return pd.Series(dtype=float)
    a = d10["us10y"].astype(float) if "us10y" in d10 else d10.iloc[:, 0].astype(float)
    b = d3["us3m"].astype(float) if "us3m" in d3 else d3.iloc[:, 0].astype(float)
    idx = a.index.union(b.index)
    return (a.reindex(idx).ffill() - b.reindex(idx).ffill()).dropna()


def _duration_score(ctx, bench) -> dict:
    """0-100 own-duration risk score (higher = step aside to cash). Classic, honest
    bond legs — VALUE (real yield), CARRY (curve slope), TREND (TSMOM) — the
    Brooks-Moskowitz / Cochrane-Piazzesi / century-of-trend factors. Long-only ETF
    version: it can only express 'underweight', so its real job is to stand aside in
    the 2022-type regime (negative real yield + downtrend), not to short."""
    cf = ctx["cf"]
    idx = cf.index
    legs: dict[str, dict] = {}
    real = store.read("fred", "DFII10")
    if real is not None and not real.empty:
        ry = real["us10y_real"].astype(float) if "us10y_real" in real else real.iloc[:, 0].astype(float)
        riskoff = (1.0 - _pctile(ry, 252 * 5))        # low real yield (expensive) → de-risk
        legs["value"] = {"series": riskoff.shift(1).clip(0, 1), "weight": 1.0, "lag": 1,
                         "label": "Real-yield value (expensive → step aside)"}
    ts = _term_spread()
    if not ts.empty:
        riskoff = (1.0 - _pctile(ts, 252 * 5))        # inverted / negative carry → de-risk
        legs["carry"] = {"series": riskoff.shift(1).clip(0, 1), "weight": 0.5, "lag": 1,
                         "label": "Curve carry (10y − 3m)"}
    from engine.cross_asset_trend import tsmom_alloc
    trend = tsmom_alloc(bench)                         # [-1,1]; downtrend → de-risk
    legs["trend"] = {"series": ((1.0 - trend) / 2.0).clip(0, 1), "weight": 1.0, "lag": 0,
                     "label": "Trend (time-series momentum)"}
    return _compose(legs, idx)


def _duration_alloc(ctx, bench):
    sc = _duration_score(ctx, bench)["score"]
    return ea.glide_path(sc).reindex(bench.index, method="ffill").fillna(1.0)


DURATION_TIMING = StrategySpec(
    key="duration_timing", icon="🏛️",
    name_en="Duration / Treasury Timing", name_zh="久期 / 国债择时",
    thesis_en="Own long Treasuries when they're cheap and trending; step to T-bills before the rate shock.",
    thesis_zh="当长期国债便宜且趋势向上时持有；在利率冲击前退守短债。",
    bench_en="Long Treasuries (TR)", bench_zh="长期国债（总回报）",
    cash_en="T-bills", cash_zh="短期国债",
    risk_word_en="Duration risk", risk_word_zh="久期风险",
    benchmark=_duration_bench, alloc=_duration_alloc, cash_yield=_duration_cash,
    risk_yield=_duration_riskyield, score=_duration_score,
    experimental=True,
    caveat_en="Long-Treasury total return = TLT dividend-adjusted close (2002→). A long-only "
              "single-ETF timer is far weaker than the leveraged multi-country bond-factor "
              "research; its real job is crisis convexity + standing aside in 2022-type regimes. "
              "Experimental, under validation.",
    caveat_zh="长期国债总回报 = TLT 经分红调整收盘价（2002 年起）。仅做多的单一 ETF 择时远弱于"
              "带杠杆的多国债券因子研究；其真正作用是危机凸性 + 在 2022 式行情中退守。实验性，验证中。")


STRATEGIES: list[StrategySpec] = [SPVECTOR, CREDIT_CARRY, DURATION_TIMING]


def by_key(key: str) -> StrategySpec | None:
    return next((s for s in STRATEGIES if s.key == key), None)
