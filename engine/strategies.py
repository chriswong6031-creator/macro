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
    group: str | None = None      # optional grouping key (e.g. commodity) for toggle-grid pages


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
    caveat_en="Phase-0 (2007→ HYG): the drawdown-control edge is robust — MaxDD −15% vs −34% "
              "buy & hold, survives leave-one-crisis-out, dd-reduction CI excludes zero — but it "
              "does NOT beat a naive 200-day trend on HY (Sharpe 0.75 vs 0.83). DISPLAY-ONLY / "
              "experimental, not a scored signal. Benchmark = HYG dividend-adjusted close; a "
              "deeper-history re-run awaits the ICE BofA HY total-return index (1986→) in CI. "
              "See reports/credit-carry-phase0.md. Not investment advice.",
    caveat_zh="Phase-0（2007 起，HYG）：回撤控制优势稳健——最大回撤 −15% 对比买入持有 −34%，通过留一危机检验，"
              "回撤缩减置信区间不含零——但并未跑赢 HY 上的朴素 200 日趋势（夏普 0.75 对 0.83）。仅展示 / 实验性，"
              "非评分信号。基准 = HYG 经分红调整收盘价；更深历史的复跑有待 CI 中的 ICE BofA 高收益总回报指数"
              "（1986 起）。见 reports/credit-carry-phase0.md。非投资建议。")


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
    # DTB3's column follows its config alias (us3m -> us3m_bill, 2026-07-30). The
    # SERIES choice is deliberately unchanged here — this spread is a scored strategy
    # input, so re-basing it to the CMT node is a signal change, not a plumbing fix.
    b = (d3["us3m_bill"] if "us3m_bill" in d3 else d3.iloc[:, 0]).astype(float)
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
    caveat_en="Phase-0 (2002→ TLT): the drawdown-control edge is robust — MaxDD −18% vs −48% buy & "
              "hold, beats the naive baselines, survives leave-one-crisis-out — but the deflated "
              "Sharpe is marginal (0.83 < 0.90), so the risk-adjusted edge may be noise at this "
              "sample depth. DISPLAY-ONLY / experimental, not a scored signal: a long-only single-ETF "
              "timer is far weaker than the leveraged multi-country bond-factor research; its real job "
              "is crisis convexity + standing aside in 2022-type regimes. See "
              "reports/duration-timing-phase0.md. Not investment advice.",
    caveat_zh="Phase-0（2002 起，TLT）：回撤控制优势稳健——最大回撤 −18% 对比买入持有 −48%，跑赢朴素基准，"
              "通过留一危机检验——但贬值夏普处于临界（0.83 < 0.90），在此样本深度下风险调整后优势可能是噪声。"
              "仅展示 / 实验性，非评分信号：仅做多的单一 ETF 择时远弱于带杠杆的多国债券因子研究；其真正作用是"
              "危机凸性 + 在 2022 式行情中退守。见 reports/duration-timing-phase0.md。非投资建议。")


# =========================================================================== #
# Strategies 4-27 — a broader tactical SUITE (the same long/flat-vs-cash harness)
# --------------------------------------------------------------------------- #
# Design rules, identical to the first three so the cards stay comparable & honest:
#   * each strategy is ONE risk asset (its total-return adjusted close) timed
#     against a cash sleeve (T-bills, or 5y Treasuries for the credit sleeves);
#   * the 0-100 score is a renormalized weighted mean of economically-motivated
#     legs in [0,1] (1 = de-risk), every leg PIT-aligned onto the asset's calendar
#     then shifted by its publication lag — no look-ahead;
#   * glide_path turns the score into a graded, 5-day-debounced weight;
#   * NOTHING here claims to beat buy-&-hold on CAGR. Trend on crash-prone assets
#     (Nasdaq/semis/BTC) usually does; the macro/credit timers mostly trade CAGR
#     for a higher Sharpe and a much shallower drawdown. The card shows the truth
#     either way (win/lose colouring vs B&H is computed, not asserted).
# All are `experimental=True`: full Phase-0 (leave-one-crisis-out, DSR gate) is a
# fast-follow. The legs reuse the validated repo gauges + classic published factors
# (Moskowitz-Ooi-Pedersen trend, Moreira-Muir vol-management, Antonacci dual
# momentum, Barroso-Santa-Clara momentum-crash scaling, Sahm rule, the
# curve-inversion recession trigger, HY-OAS-leads-equity, Fed net liquidity).
# =========================================================================== #
_W5Y = 252 * 5


def _fred(series: str, col: str | None = None) -> pd.Series | None:
    df = store.read("fred", series)
    if df is None or getattr(df, "empty", True):
        return None
    c = col if (col and col in df.columns) else df.columns[0]
    return df[c].astype(float).dropna()


def _close(ticker: str) -> pd.Series | None:
    """Graceful adjusted-close reader (None instead of raising) — for optional
    score-leg inputs like ^VIX. The store maps ^VIX->_VIX; try both."""
    df = store.read("yahoo", ticker)
    if (df is None or getattr(df, "empty", True)) and ticker.startswith("^"):
        df = store.read("yahoo", "_" + ticker[1:])
    if df is None or getattr(df, "empty", True) or "close" not in getattr(df, "columns", []):
        return None
    return df["close"].astype(float).dropna()


def _onto(series: pd.Series, idx: pd.Index, lag: int = 0) -> pd.Series:
    """Carry a leg onto the asset's trading calendar (ffill — causal), THEN shift by
    its publication lag in TRADING days. Doing the reindex before the shift means a
    monthly macro print is lagged by N trading days, not N months."""
    s = series.reindex(idx, method="ffill")
    return (s.shift(lag) if lag else s).clip(0, 1)


def _trend_derisk(bench: pd.Series) -> pd.Series:
    """[0,1] de-risk from time-series momentum: 1 when fully down-trending. Reuses
    the validated tsmom_alloc (3/6/12m sign, skips the last week); backtest_core adds
    the next-bar lag so this is causal as-is (lag 0)."""
    from engine.cross_asset_trend import tsmom_alloc
    return ((1.0 - tsmom_alloc(bench)) / 2.0).clip(0, 1)


def _realvol_derisk(bench: pd.Series, win: int = 21) -> pd.Series:
    """[0,1] de-risk = 5y percentile of trailing realized vol (Moreira-Muir / Barroso-
    Santa-Clara: cut exposure when vol is high — vol is persistent and predicts
    drawdown far better than returns)."""
    return _pctile(bench.pct_change().rolling(win).std(), _W5Y).clip(0, 1)


def _leg(series: pd.Series, idx: pd.Index, weight: float, lag: int, label: str) -> dict:
    return {"series": _onto(series, idx, lag), "weight": float(weight), "lag": int(lag),
            "label": label}


# --------------------------------------------------------------------------- #
# score builders (each returns the _compose output on the asset's calendar)
# --------------------------------------------------------------------------- #
def _sc_trend(ctx, bench) -> dict:
    """Time-series momentum + a realized-vol guard — the managed-futures core."""
    i = bench.index
    return _compose({
        "trend": _leg(_trend_derisk(bench), i, 1.0, 0, "Trend (time-series momentum)"),
        "realvol": _leg(_realvol_derisk(bench), i, 0.5, 1, "Realized-volatility risk-off"),
    }, i)


def _sc_dualmom(ctx, bench) -> dict:
    """Antonacci absolute momentum: de-risk when the trailing 6m/12m total return is
    BELOW what cash earned over the same window (be in the asset only when it out-
    earns the risk-free leg)."""
    i = bench.index
    cy = ea.bill_yield().reindex(i, method="ffill").fillna(0.0) / 100.0
    parts = []
    for n in (126, 252):
        parts.append((bench.pct_change(n) < cy * (n / 252.0)).astype(float))
    below = sum(parts) / len(parts)
    return _compose({"abs_mom": _leg(below, i, 1.0, 1, "Absolute momentum (below cash)")}, i)


def _sc_gcross(ctx, bench) -> dict:
    """The famous 50/200-day moving-average ('golden/death cross') timer — kept as an
    honest, widely-quoted baseline."""
    i = bench.index
    s50, s200 = bench.rolling(50).mean(), bench.rolling(200).mean()
    d = (s50 < s200).astype(float).where(s200.notna())
    return _compose({"gcross": _leg(d, i, 1.0, 1, "50/200-day moving-average cross")}, i)


def _sc_volmanaged(ctx, bench) -> dict:
    """Pure Moreira-Muir volatility management: scale down into high-vol regimes."""
    i = bench.index
    return _compose({"realvol": _leg(_realvol_derisk(bench), i, 1.0, 1,
                                     "Realized-volatility risk-off")}, i)


def _sc_vixterm(ctx, bench) -> dict:
    """VIX term-structure stress: backwardation (VIX > VIX3M) is the market pricing
    near-term fear above one-quarter fear — the cleanest fast risk-off tell."""
    i = bench.index
    v, v3 = _close("^VIX"), _close("^VIX3M")
    legs = {}
    if v is not None and v3 is not None:
        j = v.index.intersection(v3.index)
        ratio = (v.reindex(j) / v3.reindex(j))
        legs["vix_term"] = _leg(((ratio - 0.9) / 0.25), i, 1.0, 0,
                                "VIX term-structure (backwardation)")
        legs["vix_level"] = _leg(_pctile(v, _W5Y), i, 0.5, 0, "VIX level (risk-off)")
    return _compose(legs, i)


def _sc_netliq(ctx, bench) -> dict:
    """Fed net liquidity = balance sheet − overnight RRP. A contracting (falling)
    net-liquidity tide is the macro headwind that drains risk assets."""
    i = bench.index
    wal, rrp = _fred("WALCL"), _fred("RRPONTSYD")
    legs = {}
    if wal is not None:
        if rrp is not None:
            ci = wal.index.union(rrp.index)
            net = (wal.reindex(ci).ffill() - rrp.reindex(ci).ffill()).dropna()
        else:
            net = wal
        legs["liquidity"] = _leg(_pctile(-net.diff(63), _W5Y), i, 1.0, 5,
                                 "Net liquidity contracting (Fed BS − RRP)")
    return _compose(legs, i)


def _sc_curve(ctx, bench) -> dict:
    """Yield-curve recession trigger: inversion plus (the more reliable signal) the
    RE-STEEPENING out of inversion that has led every modern recession."""
    i = bench.index
    sp = _fred("T10Y3M")
    legs = {}
    if sp is not None:
        inv = (sp < 0).astype(float)
        recently_inv = (sp.rolling(252).min() < 0).astype(float)
        uninvert = recently_inv * (sp > 0).astype(float) * (sp.diff(21) > 0).astype(float)
        legs["curve"] = _leg(0.5 * inv + 0.5 * uninvert, i, 1.0, 1,
                             "Yield-curve recession trigger (10y−3m)")
    return _compose(legs, i)


def _sc_sahm(ctx, bench) -> dict:
    """Labor-market recession timer: the Sahm rule (unemployment-rate uptick) plus a
    jobless-claims uptrend — both lead equity drawdowns."""
    i = bench.index
    sahm, claims = _fred("SAHMREALTIME"), _fred("ICSA")
    legs = {}
    if sahm is not None:
        legs["sahm"] = _leg((sahm / 0.6), i, 1.0, 22, "Sahm-rule recession trigger")
    if claims is not None:
        legs["claims"] = _leg(_pctile(claims.pct_change(13), _W5Y), i, 0.5, 5,
                              "Jobless-claims uptrend")
    return _compose(legs, i)


def _sc_credit_gate(ctx, bench) -> dict:
    """Credit leads equity: high-yield spreads WIDENING (rate of change) plus a wide
    LEVEL flag risk-off the stock sleeve before the equity drawdown confirms."""
    i = bench.index
    hy = _fred("BAMLH0A0HYM2")
    legs = {}
    if hy is not None:
        legs["hy_widening"] = _leg(_pctile(hy.diff(63), _W5Y), i, 1.0, 3,
                                   "Credit stress (HY-OAS widening)")
        legs["hy_level"] = _leg(_pctile(hy, _W5Y), i, 0.5, 3, "High-yield spread level")
    return _compose(legs, i)


def _sc_fincond(ctx, bench) -> dict:
    """Financial-conditions timer: de-risk only when the Chicago Fed NFCI is BOTH
    tight (>0) AND tightening (13w change>0) — the regime that precedes stress."""
    i = bench.index
    nfci, anfci = _fred("NFCI"), _fred("ANFCI")
    legs = {}
    if nfci is not None:
        tight = (nfci > 0) & (nfci.diff(13) > 0)
        legs["nfci"] = _leg(_pctile(nfci, _W5Y).where(tight, 0.0), i, 1.0, 5,
                            "Financial conditions (tight & tightening)")
    if anfci is not None:
        legs["anfci"] = _leg(_pctile(anfci, _W5Y), i, 0.5, 5,
                             "Adjusted financial conditions")
    return _compose(legs, i)


def _sc_momcrash(ctx, bench) -> dict:
    """Barroso-Santa-Clara risk-managed momentum: ride the momentum ETF but scale by
    its OWN realized volatility — momentum crashes are a volatility phenomenon."""
    i = bench.index
    return _compose({
        "trend": _leg(_trend_derisk(bench), i, 0.7, 0, "Trend (time-series momentum)"),
        "mom_crash": _leg(_realvol_derisk(bench), i, 1.0, 1,
                          "Momentum-crash guard (own volatility)"),
    }, i)


def _sc_lowvol(ctx, bench) -> dict:
    """Min-vol is already defensive — so the only reason to step aside is a genuine
    MARKET volatility panic. The leg is the broad-market (SPY) realized-vol percentile."""
    i = bench.index
    spy = _close("SPY")
    legs = {}
    if spy is not None:
        legs["realvol"] = _leg(_realvol_derisk(spy), i, 1.0, 1,
                               "Market volatility (extreme-stress step-aside)")
    return _compose(legs, i)


def _sc_quality(ctx, bench) -> dict:
    """Quality leads in slowdowns but still draws down in crashes — pair its own trend
    with the repo's recession-risk gauge."""
    i = bench.index
    cf = ctx["cf"]
    legs = {"trend": _leg(_trend_derisk(bench), i, 0.5, 0, "Trend (time-series momentum)")}
    if "recession_risk" in cf:
        legs["recession"] = _leg(cf["recession_risk"] / 100.0, i, 1.0, 22, "Recession risk")
    return _compose(legs, i)


def _sc_eqweight(ctx, bench) -> dict:
    """Equal-weight trend + a breadth tell: when equal-weight is losing to cap-weight
    (RSP/SPY rolling over) the rally has narrowed to a few names — late-cycle risk."""
    i = bench.index
    spy = _close("SPY")
    legs = {"trend": _leg(_trend_derisk(bench), i, 1.0, 0, "Trend (time-series momentum)")}
    if spy is not None:
        rs = (bench / spy.reindex(bench.index).ffill()).dropna()
        legs["breadth"] = _leg(_pctile(-(rs / rs.shift(63) - 1.0), _W5Y), i, 0.5, 1,
                               "Breadth narrowing (equal vs cap weight)")
    return _compose(legs, i)


def _sc_gold_macro(ctx, bench) -> dict:
    """Gold's macro drivers: RISING real yields (opportunity cost) and a STRONG dollar
    are gold's two headwinds; add its own trend as a tie-breaker."""
    i = bench.index
    real, usd = _fred("DFII10"), _fred("DTWEXBGS")
    legs = {"trend": _leg(_trend_derisk(bench), i, 0.5, 0, "Trend (time-series momentum)")}
    if real is not None:
        legs["realrate"] = _leg(_pctile(real.diff(63), _W5Y), i, 1.0, 1,
                                "Real yields rising (gold headwind)")
    if usd is not None:
        legs["dollar"] = _leg(_pctile(usd.diff(63), _W5Y), i, 0.5, 2,
                              "US dollar strengthening")
    return _compose(legs, i)


def _sc_copper(ctx, bench) -> dict:
    """Dr. Copper as a growth play: own it on its own up-trend, step aside when global
    industrial growth (US industrial production momentum) is rolling over."""
    i = bench.index
    indpro = _fred("INDPRO")
    legs = {"trend": _leg(_trend_derisk(bench), i, 0.7, 0, "Trend (time-series momentum)")}
    if indpro is not None:
        legs["growth"] = _leg(1.0 - _pctile(indpro.pct_change(6), _W5Y), i, 1.0, 30,
                              "Industrial growth slowing")
    return _compose(legs, i)


def _sc_ig_carry(ctx, bench) -> dict:
    """Investment-grade carry: harvest the IG spread, rotate to Treasuries when the
    Baa−Aaa quality spread (deep history) is widening + recession risk rises."""
    i = bench.index
    cf = ctx["cf"]
    aaa, baa = _fred("DAAA"), _fred("DBAA")
    legs = {}
    if aaa is not None and baa is not None:
        j = aaa.index.intersection(baa.index)
        spread = (baa.reindex(j) - aaa.reindex(j)).dropna()
        legs["ig_widening"] = _leg(_pctile(spread.diff(63), _W5Y), i, 1.0, 3,
                                   "IG credit stress (Baa−Aaa widening)")
    if "recession_risk" in cf:
        legs["recession"] = _leg(cf["recession_risk"] / 100.0, i, 0.5, 22, "Recession risk")
    return _compose(legs, i)


def _sc_em_carry(ctx, bench) -> dict:
    """EM hard-currency debt carry: the dollar is the EM wrecking ball — de-risk into
    Treasuries when the EM-weighted broad dollar is rising, plus a global HY-stress leg."""
    i = bench.index
    usd_em, hy = _fred("DTWEXEMEGS"), _fred("BAMLH0A0HYM2")
    legs = {}
    if usd_em is not None:
        legs["dollar_em"] = _leg(_pctile(usd_em.diff(63), _W5Y), i, 1.0, 2,
                                 "EM-weighted dollar strengthening")
    if hy is not None:
        legs["hy_widening"] = _leg(_pctile(hy.diff(63), _W5Y), i, 0.5, 3,
                                   "Global credit stress (HY-OAS widening)")
    return _compose(legs, i)


def _sc_ftq(ctx, bench) -> dict:
    """Intermediate Treasuries as the flight-to-quality hedge: own the duration, but
    step to bills when the 10y yield is in a clear up-trend (the 2022-type rate shock)."""
    i = bench.index
    y10 = _fred("DGS10")
    legs = {"trend": _leg(_trend_derisk(bench), i, 0.5, 0, "Trend (time-series momentum)")}
    if y10 is not None:
        legs["rates_trend"] = _leg(_pctile(y10.diff(63), _W5Y), i, 1.0, 1,
                                   "Rates rising (duration headwind)")
    return _compose(legs, i)


# --------------------------------------------------------------------------- #
# factory + the 24 config rows (asset/cash/income/score builder + labels)
# --------------------------------------------------------------------------- #
def _yield_plus(fred_id: str, add: float):
    def f(ctx):
        s = _fred(fred_id)
        return (s + add) if s is not None else pd.Series(dtype=float)
    return f


def _make(cfg: dict) -> StrategySpec:
    tk, score_fn, cash_kind = cfg["ticker"], cfg["score"], cfg.get("cash", "bills")
    income = cfg.get("income", 0.0)

    def benchmark(ctx, tk=tk):
        return ea.index_close(tk)

    def cash_yield(ctx, cash_kind=cash_kind):
        return tr.treasury_cash_yield() if cash_kind == "tsy" else ea.bill_yield()

    def risk_yield(ctx, income=income, tk=tk):
        if callable(income):
            out = income(ctx)
            if isinstance(out, pd.Series):
                return out
            income = out                          # constant fell through
        return pd.Series(float(income), index=ea.index_close(tk).index)

    def score(ctx, bench, score_fn=score_fn):
        return score_fn(ctx, bench)

    def alloc(ctx, bench, score_fn=score_fn):
        sc = score_fn(ctx, bench)["score"]
        return ea.glide_path(sc).reindex(bench.index, method="ffill").fillna(1.0)

    return StrategySpec(
        key=cfg["key"], icon=cfg["icon"], name_en=cfg["name_en"], name_zh=cfg["name_zh"],
        thesis_en=cfg["thesis_en"], thesis_zh=cfg["thesis_zh"],
        bench_en=cfg["bench_en"], bench_zh=cfg["bench_zh"],
        cash_en=("Treasuries" if cash_kind == "tsy" else "T-bills"),
        cash_zh=("国债" if cash_kind == "tsy" else "短期国债"),
        risk_word_en=cfg["risk_word_en"], risk_word_zh=cfg["risk_word_zh"],
        benchmark=benchmark, alloc=alloc, cash_yield=cash_yield, risk_yield=risk_yield,
        score=score, experimental=True, caveat_en=cfg["caveat_en"], caveat_zh=cfg["caveat_zh"])


def _cav(asset_en: str, asset_zh: str, span: str, note_en: str, note_zh: str) -> tuple[str, str]:
    return (f"{asset_en} total return = dividend/coupon-adjusted close ({span}). {note_en} "
            "Experimental — full Phase-0 (leave-one-crisis-out, deflated-Sharpe) is a fast-follow.",
            f"{asset_zh}总回报 = 经分红/票息调整收盘价（{span}）。{note_zh} "
            "实验性 —— 完整 Phase-0（留一危机、贬值夏普）为后续跟进。")


_RISK_TREND = ("Down-trend / vol", "下行趋势 / 波动")
_NEW_CFG: list[dict] = [
    # ---- equity trend / momentum ------------------------------------------- #
    {"key": "nasdaq_trend", "icon": "💻", "ticker": "QQQ",
     "name_en": "Nasdaq 100 Trend", "name_zh": "纳指100趋势",
     "bench_en": "Nasdaq 100", "bench_zh": "纳指100", "score": _sc_trend, "income": 0.6,
     "risk_word_en": _RISK_TREND[0], "risk_word_zh": _RISK_TREND[1],
     "thesis_en": "Ride the Nasdaq up-trend; step to T-bills when momentum rolls over and vol spikes.",
     "thesis_zh": "顺纳指上行趋势持有；动量反转、波动飙升时退守短债。",
     "caveat": _cav("Nasdaq 100 (QQQ)", "纳指100 (QQQ)", "1999→",
                    "Tech's deep -80% drawdowns are what trend-timing is built to dodge.",
                    "科技股 -80% 的深度回撤正是趋势择时要规避的对象。")},
    {"key": "smallcap_trend", "icon": "🐭", "ticker": "IWM",
     "name_en": "Small-Cap Trend", "name_zh": "小盘股趋势",
     "bench_en": "Russell 2000", "bench_zh": "罗素2000", "score": _sc_trend, "income": 1.2,
     "risk_word_en": _RISK_TREND[0], "risk_word_zh": _RISK_TREND[1],
     "thesis_en": "Time-series momentum on small caps — out of the asset through the long down-legs.",
     "thesis_zh": "小盘股时间序列动量 —— 在长期下行段离场。",
     "caveat": _cav("Russell 2000 (IWM)", "罗素2000 (IWM)", "2000→",
                    "Small caps trend AND mean-revert — trend timing helps drawdown more than CAGR here.",
                    "小盘股既有趋势又均值回归 —— 趋势择时对回撤的帮助大于年化。")},
    {"key": "semis_trend", "icon": "🔌", "ticker": "SMH",
     "name_en": "Semiconductor Trend", "name_zh": "半导体趋势",
     "bench_en": "Semiconductors", "bench_zh": "半导体", "score": _sc_trend, "income": 0.5,
     "risk_word_en": _RISK_TREND[0], "risk_word_zh": _RISK_TREND[1],
     "thesis_en": "The most cyclical equity sleeve — ride the boom, sidestep the bust with trend + vol.",
     "thesis_zh": "最具周期性的股票板块 —— 用趋势+波动顺周期持有、规避崩跌。",
     "caveat": _cav("Semiconductors (SMH)", "半导体 (SMH)", "2000→",
                    "Semis are high-beta and boom/bust; trend has historically cut the -85% drawdowns hard.",
                    "半导体高贝塔、暴涨暴跌；趋势历来能大幅压低 -85% 的回撤。")},
    {"key": "dual_momentum", "icon": "🔀", "ticker": "SPY",
     "name_en": "Dual Momentum (US)", "name_zh": "双动量（美股）",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_dualmom, "income": 1.3,
     "risk_word_en": "Below-cash momentum", "risk_word_zh": "低于现金的动量",
     "thesis_en": "Antonacci absolute momentum: hold the S&P only while it out-earns T-bills.",
     "thesis_zh": "Antonacci 绝对动量：仅当标普跑赢短债时持有。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "Absolute-momentum on a single index is the simplest dual-momentum sleeve (no cross-asset switch).",
                    "单一指数的绝对动量是最简的双动量形式（无跨资产切换）。")},
    {"key": "golden_cross", "icon": "✝️", "ticker": "SPY",
     "name_en": "Golden Cross", "name_zh": "黄金交叉",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_gcross, "income": 1.3,
     "risk_word_en": "Death-cross state", "risk_word_zh": "死叉状态",
     "thesis_en": "The textbook 50/200-day cross — a deliberately simple, widely-watched baseline.",
     "thesis_zh": "教科书式 50/200 日均线交叉 —— 刻意保留的简单、广为人知的基准。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "A slow binary timer kept for honesty — it lags turns and whipsaws in choppy markets.",
                    "为诚实而保留的缓慢二元择时 —— 转折滞后、震荡市频繁打脸。")},
    # ---- volatility-managed equity ----------------------------------------- #
    {"key": "vol_managed_sp", "icon": "🌊", "ticker": "SPY",
     "name_en": "Volatility-Managed S&P", "name_zh": "波动管理标普",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_volmanaged, "income": 1.3,
     "risk_word_en": "Realized vol", "risk_word_zh": "已实现波动",
     "thesis_en": "Moreira-Muir: cut equity into high-volatility regimes, add it back into calm.",
     "thesis_zh": "Moreira-Muir：高波动时降仓，平静时加仓。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "Vol management reliably lifts Sharpe; its CAGR edge is regime-dependent.",
                    "波动管理稳定提升夏普；其年化优势取决于行情阶段。")},
    {"key": "vix_term_timer", "icon": "📐", "ticker": "SPY",
     "name_en": "VIX Term-Structure Timer", "name_zh": "VIX 期限结构择时",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_vixterm, "income": 1.3,
     "risk_word_en": "VIX backwardation", "risk_word_zh": "VIX 贴水",
     "thesis_en": "De-risk when the VIX curve inverts (near-term fear > 3-month) — the fast stress tell.",
     "thesis_zh": "当 VIX 曲线倒挂（近月恐慌 > 三月）时降险 —— 快速的压力信号。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "VIX3M starts 2006, so the term-structure leg is inactive before then (level leg carries it).",
                    "VIX3M 自 2006 年起，此前期限结构腿不激活（由水平腿承接）。")},
    # ---- macro-regime equity timers ---------------------------------------- #
    {"key": "net_liquidity", "icon": "🪣", "ticker": "SPY",
     "name_en": "Net-Liquidity Vector", "name_zh": "净流动性向量",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_netliq, "income": 1.3,
     "risk_word_en": "Liquidity drain", "risk_word_zh": "流动性收缩",
     "thesis_en": "Follow the Fed tide: lighten up when net liquidity (balance sheet − RRP) is draining.",
     "thesis_zh": "跟随美联储潮汐：当净流动性（资产负债表 − 逆回购）收缩时减仓。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "Net liquidity is a popular but contested macro driver; the leg starts when the Fed BS series does (2002).",
                    "净流动性是流行但有争议的宏观驱动；该腿自美联储资产负债表序列起（2002）。")},
    {"key": "curve_recession", "icon": "📉", "ticker": "SPY",
     "name_en": "Yield-Curve Recession Timer", "name_zh": "收益率曲线衰退择时",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_curve, "income": 1.3,
     "risk_word_en": "Curve trigger", "risk_word_zh": "曲线触发",
     "thesis_en": "Inversion warns; the re-steepening out of inversion has led every modern recession.",
     "thesis_zh": "倒挂预警；从倒挂走向陡峭领先了每一次现代衰退。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "The curve's recession lead is long and variable — this times slowly and can be early by months.",
                    "曲线对衰退的领先期长且多变 —— 择时偏慢，可能提前数月。")},
    {"key": "sahm_timer", "icon": "🧰", "ticker": "SPY",
     "name_en": "Sahm-Rule Labor Timer", "name_zh": "Sahm 失业率择时",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_sahm, "income": 1.3,
     "risk_word_en": "Labor weakening", "risk_word_zh": "就业转弱",
     "thesis_en": "The labor market turns before earnings: de-risk on the Sahm trigger + rising jobless claims.",
     "thesis_zh": "就业先于盈利转向：Sahm 触发 + 初请上行时降险。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "Monthly labor data is lagged ~22 trading days here; it confirms recessions more than it pre-empts them.",
                    "月度就业数据在此滞后约 22 个交易日；它更多是确认衰退而非提前。")},
    {"key": "credit_gate_equity", "icon": "🚦", "ticker": "SPY",
     "name_en": "Credit-Spread Equity Gate", "name_zh": "信用利差股票闸门",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_credit_gate, "income": 1.3,
     "risk_word_en": "Credit stress", "risk_word_zh": "信用压力",
     "thesis_en": "Credit leads equity — let widening high-yield spreads pull the stock weight down first.",
     "thesis_zh": "信用领先股票 —— 让走阔的高收益利差先把股票仓位拉低。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "HY-OAS starts 1996; one of the strongest stand-alone equity de-risk gates in the suite.",
                    "高收益利差自 1996 年起；本套件中最强的独立股票降险闸门之一。")},
    {"key": "fin_conditions", "icon": "🌡️", "ticker": "SPY",
     "name_en": "Financial-Conditions Timer", "name_zh": "金融条件择时",
     "bench_en": "S&P 500", "bench_zh": "标普500", "score": _sc_fincond, "income": 1.3,
     "risk_word_en": "Conditions tightening", "risk_word_zh": "条件收紧",
     "thesis_en": "Step out only when the Chicago Fed NFCI is both tight AND tightening — the stress regime.",
     "thesis_zh": "仅当芝加哥联储 NFCI 既紧又在收紧时离场 —— 压力区间。",
     "caveat": _cav("S&P 500 (SPY)", "标普500 (SPY)", "1993→",
                    "The tight-AND-tightening double-condition keeps it invested through benign easing.",
                    "‘既紧又收紧’的双条件让它在温和宽松期保持在场。")},
    # ---- factor-ETF timing ------------------------------------------------- #
    {"key": "momentum_crashguard", "icon": "🚀", "ticker": "MTUM",
     "name_en": "Momentum w/ Crash Guard", "name_zh": "动量因子崩溃护盾",
     "bench_en": "Momentum factor", "bench_zh": "动量因子", "score": _sc_momcrash, "income": 1.0,
     "risk_word_en": "Crash risk", "risk_word_zh": "崩溃风险",
     "thesis_en": "Barroso-Santa-Clara: own the momentum factor but scale by its own volatility — momentum crashes are a vol event.",
     "thesis_zh": "Barroso-Santa-Clara：持有动量因子，但按其自身波动缩放 —— 动量崩溃本质是波动事件。",
     "caveat": _cav("Momentum factor (MTUM)", "动量因子 (MTUM)", "2013→",
                    "Short history (no 2008); MTUM is the iShares USA momentum ETF, not the academic long-short factor.",
                    "历史较短（无 2008）；MTUM 为 iShares 美国动量 ETF，非学术多空因子。")},
    {"key": "lowvol_defensive", "icon": "🛡️", "ticker": "USMV",
     "name_en": "Low-Volatility Defensive", "name_zh": "低波动防御",
     "bench_en": "Min-vol equity", "bench_zh": "最小波动股票", "score": _sc_lowvol, "income": 1.8,
     "risk_word_en": "Market panic", "risk_word_zh": "市场恐慌",
     "thesis_en": "Hold the low-vol anomaly almost always; only step aside in a genuine market volatility panic.",
     "thesis_zh": "几乎始终持有低波动异象；仅在真正的市场波动恐慌时退避。",
     "caveat": _cav("Min-vol equity (USMV)", "最小波动股票 (USMV)", "2011→",
                    "Short history (no 2008); min-vol is already defensive so the timer rarely fires.",
                    "历史较短（无 2008）；低波本已防御，择时很少触发。")},
    {"key": "quality_flight", "icon": "💎", "ticker": "QUAL",
     "name_en": "Quality Flight", "name_zh": "质量避险",
     "bench_en": "Quality factor", "bench_zh": "质量因子", "score": _sc_quality, "income": 1.3,
     "risk_word_en": "Recession risk", "risk_word_zh": "衰退风险",
     "thesis_en": "Quality compounds through slowdowns — pair its trend with the macro recession gauge.",
     "thesis_zh": "质量在放缓中复利 —— 将其趋势与宏观衰退计配对。",
     "caveat": _cav("Quality factor (QUAL)", "质量因子 (QUAL)", "2013→",
                    "Short history (no 2008); QUAL is the iShares USA quality ETF.",
                    "历史较短（无 2008）；QUAL 为 iShares 美国质量 ETF。")},
    {"key": "equalweight_trend", "icon": "⚖️", "ticker": "RSP",
     "name_en": "Equal-Weight Trend & Breadth", "name_zh": "等权趋势与广度",
     "bench_en": "Equal-weight S&P", "bench_zh": "等权标普", "score": _sc_eqweight, "income": 1.5,
     "risk_word_en": "Breadth narrowing", "risk_word_zh": "广度收窄",
     "thesis_en": "Own the equal-weight S&P on trend; trim when breadth narrows (RSP losing to cap-weight).",
     "thesis_zh": "按趋势持有等权标普；当广度收窄（等权跑输市值权重）时减仓。",
     "caveat": _cav("Equal-weight S&P (RSP)", "等权标普 (RSP)", "2003→",
                    "Breadth (RSP/SPY) is a late-cycle context tell, not a precise top-timer.",
                    "广度（RSP/SPY）是晚周期情境信号，非精确顶部择时。")},
    # ---- commodity --------------------------------------------------------- #
    {"key": "gold_macro", "icon": "🥇", "ticker": "GC=F",
     "name_en": "Gold Macro Timer", "name_zh": "黄金宏观择时",
     "bench_en": "Gold", "bench_zh": "黄金", "score": _sc_gold_macro, "income": 0.0,
     "risk_word_en": "Gold headwinds", "risk_word_zh": "黄金逆风",
     "thesis_en": "Gold's two enemies are rising real yields and a strong dollar — own it when both are calm.",
     "thesis_zh": "黄金的两大敌人是实际收益率上行与强美元 —— 二者平静时持有。",
     "caveat": _cav("Gold (GC=F)", "黄金 (GC=F)", "2000→",
                    "Continuous front-month futures close; gold pays no income so the flat sleeve earns the bill yield.",
                    "连续近月期货收盘价；黄金无票息，空仓腿赚取短债收益。")},
    {"key": "oil_trend", "icon": "🛢️", "ticker": "BZ=F",
     "name_en": "Crude-Oil Trend", "name_zh": "原油趋势",
     "bench_en": "Brent crude", "bench_zh": "布伦特原油", "score": _sc_trend, "income": 0.0,
     "risk_word_en": _RISK_TREND[0], "risk_word_zh": _RISK_TREND[1],
     "thesis_en": "Classic managed-futures trend on Brent — commodities trend strongly and crash hard.",
     "thesis_zh": "布伦特原油的经典管理期货趋势 —— 商品趋势强、崩跌也猛。",
     "caveat": _cav("Brent crude (BZ=F)", "布伦特原油 (BZ=F)", "2007→",
                    "Brent (not WTI) avoids the 2020 negative-price artifact; oil pays no income.",
                    "用布伦特（非 WTI）以规避 2020 年负价格异常；原油无票息。")},
    {"key": "copper_growth", "icon": "🟤", "ticker": "HG=F",
     "name_en": "Copper Growth Cyclical", "name_zh": "铜·增长周期",
     "bench_en": "Copper", "bench_zh": "铜", "score": _sc_copper, "income": 0.0,
     "risk_word_en": "Growth slowing", "risk_word_zh": "增长放缓",
     "thesis_en": "Dr. Copper as a growth gauge — own it on trend, stand aside when industrial growth rolls over.",
     "thesis_zh": "‘铜博士’作为增长晴雨表 —— 顺趋势持有，工业增长回落时退避。",
     "caveat": _cav("Copper (HG=F)", "铜 (HG=F)", "2000→",
                    "Industrial-production momentum is monthly and lagged ~30 trading days; copper pays no income.",
                    "工业生产动量为月度且滞后约 30 个交易日；铜无票息。")},
    # ---- crypto ------------------------------------------------------------ #
    {"key": "btc_trend", "icon": "₿", "ticker": "BTC-USD",
     "name_en": "Bitcoin Trend", "name_zh": "比特币趋势",
     "bench_en": "Bitcoin", "bench_zh": "比特币", "score": _sc_trend, "income": 0.0,
     "risk_word_en": _RISK_TREND[0], "risk_word_zh": _RISK_TREND[1],
     "thesis_en": "Trend-follow Bitcoin to keep the upside while cutting the repeated -80% drawdowns.",
     "thesis_zh": "趋势跟随比特币，保留上行同时削减反复出现的 -80% 回撤。",
     "caveat": _cav("Bitcoin (BTC-USD)", "比特币 (BTC-USD)", "2014→",
                    "Crypto trades 7d/wk; Sharpe is annualized at 252 (slightly conservative). This is where trend most clearly beats buy-&-hold.",
                    "加密 7×24 交易；夏普按 252 年化（略保守）。这是趋势最明显跑赢买入持有之处。")},
    {"key": "eth_trend", "icon": "Ξ", "ticker": "ETH-USD",
     "name_en": "Ethereum Trend", "name_zh": "以太坊趋势",
     "bench_en": "Ethereum", "bench_zh": "以太坊", "score": _sc_trend, "income": 0.0,
     "risk_word_en": _RISK_TREND[0], "risk_word_zh": _RISK_TREND[1],
     "thesis_en": "Time-series momentum on ETH — out through the long crypto-winter down-legs.",
     "thesis_zh": "以太坊时间序列动量 —— 在漫长加密寒冬的下行段离场。",
     "caveat": _cav("Ethereum (ETH-USD)", "以太坊 (ETH-USD)", "2017→",
                    "Short, single-cycle history; ETH's -94% drawdowns make the drawdown reduction the headline, not CAGR.",
                    "历史短、仅单一周期；以太坊 -94% 回撤使回撤削减成为主角，而非年化。")},
    # ---- credit / rate sleeves -------------------------------------------- #
    {"key": "ig_carry", "icon": "🏦", "ticker": "LQD", "cash": "tsy",
     "name_en": "Investment-Grade Carry", "name_zh": "投资级套息",
     "bench_en": "IG corporate (TR)", "bench_zh": "投资级公司债（总回报）",
     "score": _sc_ig_carry, "income": _yield_plus("DGS5", 1.2),
     "risk_word_en": "IG credit stress", "risk_word_zh": "投资级信用压力",
     "thesis_en": "Harvest the investment-grade spread; rotate to Treasuries when the Baa−Aaa quality spread widens.",
     "thesis_zh": "收割投资级利差；当 Baa−Aaa 质量利差走阔时轮动至国债。",
     "caveat": _cav("IG corporate (LQD)", "投资级公司债 (LQD)", "2002→",
                    "IG stress proxied by the deep-history Baa−Aaa spread (the IG-OAS series only starts 2023).",
                    "投资级压力以深历史 Baa−Aaa 利差代理（IG-OAS 序列仅自 2023 年起）。")},
    {"key": "em_debt_carry", "icon": "🌍", "ticker": "EMB", "cash": "tsy",
     "name_en": "EM Debt Carry", "name_zh": "新兴市场债套息",
     "bench_en": "EM USD debt (TR)", "bench_zh": "新兴市场美元债（总回报）",
     "score": _sc_em_carry, "income": _yield_plus("DGS5", 3.5),
     "risk_word_en": "Dollar / EM stress", "risk_word_zh": "美元 / 新兴市场压力",
     "thesis_en": "Earn the EM spread; the dollar is the wrecking ball — de-risk to Treasuries when it surges.",
     "thesis_zh": "赚取新兴市场利差；美元是破坏球 —— 其飙升时退守国债。",
     "caveat": _cav("EM USD debt (EMB)", "新兴市场美元债 (EMB)", "2007→",
                    "EM-OAS series starts 2023, so stress is proxied by the EM-weighted dollar + global HY-OAS.",
                    "EM-OAS 序列自 2023 年起，故以新兴市场加权美元 + 全球高收益利差代理压力。")},
    {"key": "flight_to_quality", "icon": "🪂", "ticker": "IEF",
     "name_en": "Flight-to-Quality Duration", "name_zh": "避险久期",
     "bench_en": "7-10y Treasuries (TR)", "bench_zh": "7-10年国债（总回报）",
     "score": _sc_ftq, "income": _yield_plus("DGS10", 0.0),
     "risk_word_en": "Rate shock", "risk_word_zh": "利率冲击",
     "thesis_en": "Own intermediate Treasuries as the crisis hedge; step to bills when the 10y yield is trending up.",
     "thesis_zh": "持有中期国债作为危机对冲；当 10 年期收益率上行趋势时退守短债。",
     "caveat": _cav("7-10y Treasuries (IEF)", "7-10年国债 (IEF)", "2002→",
                    "Long-only single-ETF rate timer — its job is the 2022-type rate-shock side-step + crisis convexity.",
                    "仅做多的单一 ETF 利率择时 —— 作用是规避 2022 式利率冲击 + 危机凸性。")},
]


def _build_new() -> list[StrategySpec]:
    out = []
    for cfg in _NEW_CFG:
        cfg = dict(cfg)
        cfg["caveat_en"], cfg["caveat_zh"] = cfg.pop("caveat")
        out.append(_make(cfg))
    return out


STRATEGIES: list[StrategySpec] = [SPVECTOR, CREDIT_CARRY, DURATION_TIMING] + _build_new()


def by_key(key: str) -> StrategySpec | None:
    return next((s for s in STRATEGIES if s.key == key), None)
