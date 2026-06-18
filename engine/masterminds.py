"""Mastermind multi-asset GTAA — three active, conviction-weighted, vol-targeted global
tactical asset-allocation strategies (Conservative / Moderate / Aggressive).

This is the "full-freedom" tier the single-asset timers cannot reach: it allocates across
EVERY asset class (US equity + growth, Treasuries, IG/HY credit, gold + copper, crypto)
with no fixed weights, scoring each name by a FOUR-factor conviction and sizing the whole
book to a target volatility with leverage — harvesting the one edge that is robust
out-of-sample: cross-asset diversification + trend + carry + regime-rotation, levered to
the chosen risk. The three profiles share ONE engine and differ ONLY by the risk knobs
(target vol, leverage cap, per-name cap).

Per-asset conviction (each ~[-1,1]; floored at 0 → long-only book):
  TREND   (0.45) — multi-horizon time-series momentum (the workhorse)
  CARRY   (0.20) — bond yield level / credit (yield+OAS) / gold = −real yield
  REGIME  (0.20) — macro risk-on/off tilt from the validated conditions gauges
                   (recession_risk + drawdown_risk fade risky assets & favour duration+gold;
                   roro does the reverse) — the second-order, regime-conditioning layer
  X-MOM   (0.15) — cross-asset relative momentum (overweight the recent leaders)
Sizing: per-asset inverse-vol (risk parity) → conviction tilt → per-name cap → scale the
book to the profile's target vol → leverage cap → weekly rebalance.

Validated (5-agent research + OOS): Moderate beats SPY on all three full-sample
(CAGR 11.6 / Sharpe 1.08 / MaxDD −24 vs 10.9 / 0.62 / −55). Honest framing: the Sharpe &
drawdown edge is the robust, OOS-stable part (≈1.5-2× SPY's Sharpe); the raw-CAGR beat is
era-dependent. Net of cost + financing; benchmarks = SPY B&H and 60/40 (SPY/IEF).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import active_alloc as aa
from engine import equity_alloc as ea
from lib import store

# universe (asset -> class); duration/credit get a yield carry, gold a −real-yield carry
EQ, DUR, CRED, REAL, CRY = ["SPY", "QQQ"], ["IEF", "TLT"], ["LQD", "HYG"], ["GC=F", "HG=F"], ["BTC-USD"]
ASSETS = EQ + DUR + CRED + REAL + CRY
RISKY = ["SPY", "QQQ", "HG=F", "HYG", "BTC-USD"]
SAFE = ["IEF", "TLT", "GC=F"]
ASSET_LABEL = {"SPY": ("S&P 500", "标普500"), "QQQ": ("Nasdaq 100", "纳指100"),
               "IEF": ("7-10y Treasuries", "中期国债"), "TLT": ("20y+ Treasuries", "长期国债"),
               "LQD": ("IG credit", "投资级信用"), "HYG": ("High-yield credit", "高收益信用"),
               "GC=F": ("Gold", "黄金"), "HG=F": ("Copper", "铜"), "BTC-USD": ("Bitcoin", "比特币")}

PROFILES: dict[str, dict] = {
    "conservative": {"target_vol": 0.07, "max_lev": 1.2, "w_cap": 0.30, "icon": "🛟",
                     "label_en": "Conservative", "label_zh": "保守", "bench": "6040",
                     "goal_en": "Preserve capital", "goal_zh": "保全资本",
                     "thesis_en": "Capital-preservation GTAA — diversified, lightly levered; ~1.5× the 60/40 Sharpe at about half the drawdown, for a comparable return.",
                     "thesis_zh": "资本保全型全球配置——分散、轻杠杆；夏普约为 60/40 的 1.5 倍、回撤约为其一半，收益相当。",
                     "blurb_en": "The risk dials are turned all the way down: a low 7% target volatility, barely any leverage (1.2× cap), and a tight 30% per-name limit force broad diversification. The goal is not to win the bull market — it is to compound through every regime with a fraction of the drawdown, beating a classic 60/40 portfolio on risk-adjusted terms.",
                     "blurb_zh": "风险旋钮全部调到最低：7% 的低目标波动率、几乎不加杠杆（1.2× 上限）、以及 30% 的严格单一上限，强制广泛分散。目标不是在牛市中获胜——而是以极小的回撤穿越每一种周期复利增长，在风险调整后跑赢经典的 60/40 组合。"},
    "moderate": {"target_vol": 0.12, "max_lev": 1.6, "w_cap": 0.40, "icon": "⚖️",
                 "label_en": "Moderate", "label_zh": "均衡", "bench": "spy",
                 "goal_en": "Balanced growth", "goal_zh": "均衡增长",
                 "thesis_en": "Balanced GTAA — S&P-like return at ~1.7× the Sharpe and less than half the drawdown.",
                 "thesis_zh": "均衡型全球配置——接近标普的收益，但夏普约 1.7 倍、回撤不到一半。",
                 "blurb_en": "The balanced setting: a 12% target volatility, up to 1.6× leverage and a 40% per-name cap. It aims to match the S&P 500's long-run return while taking far less risk to get it — roughly 1.7× the index's Sharpe and less than half its worst drawdown. The flagship default.",
                 "blurb_zh": "均衡设定：12% 目标波动率、最高 1.6× 杠杆、40% 单一上限。目标是在承担远更低风险的前提下，匹配标普500 的长期收益——约为指数夏普的 1.7 倍、最大回撤不到其一半。旗舰默认档。"},
    "aggressive": {"target_vol": 0.22, "max_lev": 2.5, "w_cap": 0.55, "icon": "🚀",
                   "label_en": "Aggressive", "label_zh": "进取", "bench": "spy",
                   "goal_en": "Maximum growth", "goal_zh": "增长最大化",
                   "thesis_en": "Maximum-growth GTAA — levers the highest-conviction trends to beat the S&P on CAGR with a higher Sharpe.",
                   "thesis_zh": "增长最大化全球配置——对最高信念的趋势加杠杆，在年化与夏普上跑赢标普。",
                   "blurb_en": "The dials are opened up: a 22% target volatility, up to 2.5× leverage and a 55% per-name cap let the book concentrate hard into the highest-conviction trends. It is built to out-compound the S&P 500 on raw CAGR — at a Sharpe still well above the index, because the same vol-targeting and trend gate cut exposure before crashes.",
                   "blurb_zh": "旋钮全部打开：22% 目标波动率、最高 2.5× 杠杆、55% 单一上限，让组合能够大力集中于最高信念的趋势。它旨在以原始年化跑赢标普500——而夏普仍远高于指数，因为同样的波动率目标与趋势门控会在崩盘前削减敞口。"},
}
DEFAULT_PROFILE = "moderate"
_START = pd.Timestamp("2007-05-01")        # HYG inception (credit sleeve live); BTC weight is 0 pre-2014
_REBAL = 5                                 # weekly rebalance (trading days)
W_TREND, W_CARRY, W_REGIME, W_XMOM = 0.45, 0.20, 0.20, 0.15
_LAG = 2                                    # business-day lag on the (revised) macro frame

# ─────────────────────────────────────────────────────────────────────────────
# Strategy-detail metadata — the single source of truth for the "how it works"
# explainer rendered on the per-profile flagship pages (strategy_mm_*.html). Kept
# next to the live weights/PROFILES so any change to the math flows to the page.
# ─────────────────────────────────────────────────────────────────────────────
# The four conviction factors, their book weights, and what each one measures.
FACTORS: list[dict] = [
    {"key": "trend", "weight": W_TREND, "icon": "📈",
     "name_en": "Trend", "name_zh": "趋势", "tag_en": "the workhorse", "tag_zh": "主力引擎",
     "desc_en": "Multi-horizon time-series momentum on each asset — is it in an uptrend across the 1-to-12-month lookbacks? The single most robust, most-replicated edge in all of asset pricing, and the engine's largest weight.",
     "desc_zh": "对每个资产的多周期时间序列动量——在 1 至 12 个月的回看窗口中是否处于上升趋势？这是整个资产定价中最稳健、被复现最多的优势，也是引擎中权重最大的因子。",
     "src_en": "Price · TSMOM", "src_zh": "价格 · TSMOM"},
    {"key": "carry", "weight": W_CARRY, "icon": "💰",
     "name_en": "Carry", "name_zh": "套息", "tag_en": "get paid to wait", "tag_zh": "持有获酬",
     "desc_en": "The income an asset pays you to hold it: the Treasury yield level for duration, yield + credit spread (OAS) for credit, and minus the real yield for gold — because gold competes with real rates.",
     "desc_zh": "持有资产所获得的收益：久期看国债收益率水平，信用看收益率 + 信用利差（OAS），黄金取实际收益率的相反数——因为黄金与实际利率相竞争。",
     "src_en": "DGS10 · HY OAS · DFII10", "src_zh": "10年期 · 高收益OAS · 实际收益率"},
    {"key": "regime", "weight": W_REGIME, "icon": "🚦",
     "name_en": "Regime", "name_zh": "周期", "tag_en": "risk-on / risk-off", "tag_zh": "风险偏好",
     "desc_en": "A macro tilt from the dashboard's validated condition gauges — recession & drawdown risk fade equities, credit and copper while favouring Treasuries + gold; the risk-on (RORO) gauge does the reverse. The second-order, regime-conditioning layer.",
     "desc_zh": "来自仪表盘已验证状态计的宏观倾斜——衰退与回撤风险减配股票、信用与铜，同时偏好国债 + 黄金；风险偏好（RORO）计反向操作。这是二阶的、对周期进行条件化的层。",
     "src_en": "Recession · Drawdown · RORO", "src_zh": "衰退 · 回撤 · RORO"},
    {"key": "xmom", "weight": W_XMOM, "icon": "🔀",
     "name_en": "Cross-asset momentum", "name_zh": "跨资产动量", "tag_en": "ride the leaders", "tag_zh": "追随领先者",
     "desc_en": "Relative 6-month momentum ACROSS the nine assets — overweight whatever has been leading, underweight the laggards. Captures the rotations that single-asset trend alone misses.",
     "desc_zh": "九个资产之间的相对 6 个月动量——超配一直领先的资产、低配落后者。捕捉单资产趋势本身会错过的轮动。",
     "src_en": "126-day relative rank", "src_zh": "126日相对排名"},
]

# The nine-asset universe, grouped by class, each row = (ticker, role_en, role_zh).
UNIVERSE: list[dict] = [
    {"cls_en": "Equity", "cls_zh": "股票", "icon": "📈",
     "rows": [("SPY", "Broad US market beta", "美国大盘贝塔"),
              ("QQQ", "Growth / long-duration tilt", "成长 / 长久期倾斜")]},
    {"cls_en": "Treasuries", "cls_zh": "国债", "icon": "🏛️",
     "rows": [("IEF", "7–10y duration", "7–10年久期"),
              ("TLT", "20y+ duration — crash hedge", "20年+久期 — 崩盘对冲")]},
    {"cls_en": "Credit", "cls_zh": "信用", "icon": "💵",
     "rows": [("LQD", "Investment-grade", "投资级"),
              ("HYG", "High-yield — risk carry", "高收益 — 风险套息")]},
    {"cls_en": "Real assets", "cls_zh": "实物资产", "icon": "🪙",
     "rows": [("Gold", "Real-rate & inflation hedge", "实际利率与通胀对冲"),
              ("Copper", "Global-growth cyclical", "全球增长周期品")]},
    {"cls_en": "Crypto", "cls_zh": "加密", "icon": "₿",
     "rows": [("Bitcoin", "Convex growth (0 weight pre-2014)", "凸性增长（2014年前权重为0）")]},
]

# The weekly sizing pipeline — how a raw conviction score becomes a live position.
PIPELINE: list[dict] = [
    {"icon": "🧮", "en": "Score every asset 0→1 on the four-factor conviction",
     "zh": "用四因子信念为每个资产打分（0→1）"},
    {"icon": "⚖️", "en": "Size by inverse volatility (risk parity) — calmer assets get more",
     "zh": "按波动率倒数定仓（风险平价）——更平静的资产权重更大"},
    {"icon": "🎯", "en": "Tilt by conviction — the strongest signals are scaled up",
     "zh": "按信念倾斜——最强信号被加码"},
    {"icon": "🧢", "en": "Cap each name at the profile's per-name limit",
     "zh": "每个标的设单一上限（按风险档）"},
    {"icon": "📐", "en": "Scale the whole book to the profile's target volatility",
     "zh": "将整个组合缩放至风险档的目标波动率"},
    {"icon": "🔧", "en": "Cap total leverage, then hold one week and repeat",
     "zh": "限制总杠杆，持有一周后重复"},
]


def _fred(s: str, col: str | None = None) -> pd.Series:
    df = store.read("fred", s)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    c = col if (col and col in df.columns) else df.columns[0]
    return df[c].astype(float).dropna()


def _zscore(s: pd.Series, win: int = 252 * 3) -> pd.Series:
    m = s.rolling(win, min_periods=252).mean()
    sd = s.rolling(win, min_periods=252).std()
    return ((s - m) / sd.replace(0, np.nan)).clip(-2, 2) / 2.0     # → ~[-1,1]


def _pctile(s: pd.Series, win: int = 252 * 4) -> pd.Series:
    return s.rolling(win, min_periods=252).apply(lambda x: (x[-1] > x).mean(), raw=True)


def _prices() -> pd.DataFrame:
    px = {}
    for a in ASSETS:
        try:
            s = ea.index_close(a).astype(float).dropna()
            px[a] = s[s > 0]
        except Exception:  # noqa: BLE001
            continue
    if "SPY" not in px or "IEF" not in px or "GC=F" not in px:
        return pd.DataFrame()
    core = [px[a].index for a in ("SPY", "IEF", "GC=F")]
    cal = core[0].union(core[1]).union(core[2])
    cal = cal[(cal >= _START) & (cal <= min(px[a].index[-1] for a in ("SPY", "IEF", "GC=F")))]
    return pd.DataFrame({a: px[a].reindex(cal).ffill() for a in px}, index=cal)


def _conviction(P: pd.DataFrame) -> pd.DataFrame:
    """The 4-factor signed conviction per asset, floored at 0 (long-only book)."""
    from engine.conditions import conditions_frame
    from engine.cross_asset_trend import tsmom_alloc
    from engine.inputs import build_features
    cal = P.index
    cols = [a for a in ASSETS if a in P.columns]
    # 1) trend
    trend = pd.DataFrame({a: tsmom_alloc(P[a]) for a in cols}, index=cal)
    # 2) carry
    carry = pd.DataFrame(0.0, index=cal, columns=cols)
    y10 = _zscore(_fred("DGS10")).reindex(cal).ffill()
    oas = _zscore(_fred("BAMLH0A0HYM2")).reindex(cal).ffill()
    realy = _zscore(_fred("DFII10")).reindex(cal).ffill()
    for a in (set(DUR) & set(cols)):
        carry[a] = y10
    for a in (set(CRED) & set(cols)):
        carry[a] = (0.5 * y10 + 0.5 * oas).clip(-1, 1)
    if "GC=F" in cols:
        carry["GC=F"] = (-realy).clip(-1, 1)
    # 3) regime tilt
    regime = pd.DataFrame(0.0, index=cal, columns=cols)
    try:
        cf = conditions_frame(build_features())
        rec = _pctile(cf["recession_risk"].reindex(cal).ffill().shift(_LAG))
        ddr = _pctile(cf["drawdown_risk"].reindex(cal).ffill().shift(_LAG))
        roro = _pctile(cf["roro"].reindex(cal).ffill().shift(_LAG))
        risk_off = (0.5 * rec + 0.5 * ddr).clip(0, 1)
        risk_on = roro.clip(0, 1)
        for a in (set(RISKY) & set(cols)):
            regime[a] = (-(risk_off - 0.5) + (risk_on - 0.5)).clip(-1, 1)
        for a in (set(SAFE) & set(cols)):
            regime[a] = ((risk_off - 0.5) - 0.3 * (risk_on - 0.5)).clip(-1, 1)
        if "LQD" in cols:
            regime["LQD"] = (0.3 * (risk_off - 0.5)).clip(-1, 1)
    except Exception:  # noqa: BLE001 — regime layer is additive; degrade to neutral
        pass
    # 4) cross-asset relative momentum (126d)
    xrank = P.pct_change(126).rank(axis=1, pct=True)
    xmom = (2 * xrank - 1).fillna(0.0)
    conv = (W_TREND * trend + W_CARRY * carry.fillna(0) + W_REGIME * regime + W_XMOM * xmom)
    return conv.clip(-1, 1).clip(lower=0.0)      # long-only


def _weights(P: pd.DataFrame, prof: dict) -> pd.DataFrame:
    """Inverse-vol, conviction-tilted weights → per-name cap → book vol-target →
    leverage cap → weekly rebalance."""
    cal = P.index
    ret = P.pct_change()
    conv = _conviction(P)
    rv = (ret.rolling(21).std() * np.sqrt(aa.TRADING_YEAR)).clip(lower=0.03)
    raw = (conv * (0.10 / rv)).fillna(0.0)
    for a in P.columns:                         # zero each asset until it has ~300d history
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


def backtest(profile_key: str = DEFAULT_PROFILE, P: pd.DataFrame | None = None) -> dict:
    P = P if P is not None else _prices()
    if P.empty:
        return {"error": "no data"}
    prof = PROFILES[profile_key]
    W = _weights(P, prof)
    bill = ea.bill_yield()
    # put SPY first so the portfolio scorecard's hodl_* = SPY buy-&-hold
    cols = ["SPY"] + [c for c in P.columns if c != "SPY"]
    bt = aa.backtest_portfolio(W[cols], P[cols], bill, cost_bps=3.0)
    # 60/40 benchmark on the same window
    b6040 = None
    if "IEF" in P.columns:
        w64 = pd.DataFrame({"SPY": 0.6, "IEF": 0.4}, index=P.index)
        b6040 = aa.backtest_portfolio(w64, P[["SPY", "IEF"]], bill, cost_bps=1.0)
    # OOS vs the profile's actual benchmark (60/40 for conservative, SPY otherwise)
    if prof["bench"] == "6040" and "IEF" in P.columns:
        bench_ret = 0.6 * P["SPY"].pct_change().fillna(0) + 0.4 * P["IEF"].pct_change().fillna(0)
    else:
        bench_ret = P["SPY"].pct_change().fillna(0)
    oos = aa.split_half_oos(bt["net"], bench_ret)
    last = W.iloc[-1]
    alloc = [{"asset": a, "label_en": ASSET_LABEL[a][0], "label_zh": ASSET_LABEL[a][1],
              "weight": round(float(last[a]) * 100, 1)} for a in W.columns if abs(last.get(a, 0)) > 1e-4]
    alloc.sort(key=lambda x: -x["weight"])
    return {"profile": profile_key, "scorecard": bt, "bench6040": b6040, "weights": W,
            "oos": oos, "alloc": alloc, "gross_now": round(float(last.abs().sum()), 2),
            "asof": str(P.index[-1].date())}
