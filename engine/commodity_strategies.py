"""Per-commodity tactical-strategy registry — the commodities sibling of engine.strategies.

Every commodity rises and falls for DIFFERENT reasons, so each gets its own factor
model rather than a one-size-fits-all timer:

  * GOLD   — a monetary asset: rises when real yields fall (lower opportunity cost),
             the dollar weakens, and inflation expectations rise; over-crowded
             speculative positioning is a contrarian risk.
  * SILVER — "high-beta gold + an industrial kicker" (~1.6x gold vol, ~50% industrial
             demand): gold's monetary drivers PLUS copper-led growth + a gold/silver-
             ratio mean-reversion + speculative-positioning guard.
  * COPPER — "Dr. Copper", a global-growth & dollar play: the copper/gold ratio, the
             China credit impulse (~half of world demand), US industrial production, USD.
  * OIL    — priced in dollars, with a physical term structure: a USD-led model plus
             backwardation (a tight market) and trend; inventory & positioning were
             tested and DROPPED (wrong-signed / no forward edge — see the build notes).

Each strategy = ONE commodity (continuous front-month total-return close) timed long/flat
in [0,1] vs T-bills, scored 0-100 (HIGH = de-risk) via weighted, PIT-lagged legs →
glide_path. For every commodity there are TWO strategies: a simple risk on/off TREND SWAP
(trend + realized-vol guard) and the deeper, commodity-specific MULTIFACTOR model. Each
spec carries `group` (gold/silver/copper/oil) so scripts.build_commodity_strategies can
render them under a per-commodity toggle over one scorecard grid.

DISPLAY-ONLY / experimental. Reuses the asset-agnostic harness (StrategySpec + _compose +
_onto + _pctile). Backtests net of 3 bps, total-return, next-bar, vs buy-&-hold the same
commodity. Honest by design: silver's trend-swap genuinely does NOT beat buy-&-hold (the
multifactor model does) — the card colouring shows this, computed not asserted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine.cross_asset_trend import tsmom_alloc
from engine.strategies import StrategySpec, _compose, _onto, _pctile
from lib import store

_W5Y = 252 * 5


# --------------------------------------------------------------------------- #
# data helpers
# --------------------------------------------------------------------------- #
def _yclose(tk: str) -> pd.Series:
    try:
        return ea.index_close(tk).dropna()
    except Exception:  # noqa: BLE001
        return pd.Series(dtype=float)


def _fred(series: str, col: str | None = None) -> pd.Series:
    df = store.read("fred", series)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    c = col if (col and col in df.columns) else df.columns[0]
    return df[c].astype(float).dropna()


def _col(group: str, key: str, col: str) -> pd.Series:
    df = store.read(group, key)
    if df is None or df.empty or col not in getattr(df, "columns", []):
        return pd.Series(dtype=float)
    return df[col].astype(float).dropna()


# --------------------------------------------------------------------------- #
# shared legs ([0,1] on native index; 1 = de-risk)
# --------------------------------------------------------------------------- #
def _trend_off(b: pd.Series) -> pd.Series:
    return ((1.0 - tsmom_alloc(b)) / 2.0).clip(0, 1)


def _vol_off(b: pd.Series) -> pd.Series:
    return _pctile(b.pct_change().rolling(21).std(), _W5Y).clip(0, 1)


def _swap_score(ctx, bench) -> dict:
    """The risk on/off TREND SWAP shared by every commodity: trend + realized-vol guard."""
    i = bench.index
    return _compose({
        "trend": {"series": _onto(_trend_off(bench), i, 0), "weight": 1.0, "lag": 0,
                  "label": "Trend (time-series momentum)"},
        "vol": {"series": _onto(_vol_off(bench), i, 1), "weight": 0.5, "lag": 1,
                "label": "Realized-volatility guard"},
    }, i)


# --------------------------------------------------------------------------- #
# GOLD multifactor — real yields / USD / breakeven / positioning / trend
# --------------------------------------------------------------------------- #
def _sc_gold_mf(ctx, bench) -> dict:
    i = bench.index
    legs = {}
    dfii = _fred("DFII10")
    if not dfii.empty:
        legs["real_yield"] = {"series": _onto(_pctile(dfii.diff(63), _W5Y), i, 1),
                              "weight": 1.0, "lag": 1, "label": "Real yields rising"}
    usd = _fred("DTWEXBGS")
    if not usd.empty:
        legs["usd"] = {"series": _onto(_pctile(usd, _W5Y), i, 1), "weight": 0.8, "lag": 1,
                       "label": "Strong broad dollar"}
    be = _fred("T10YIE")
    if not be.empty:
        legs["breakeven"] = {"series": _onto(1.0 - _pctile(be, _W5Y), i, 1), "weight": 0.5,
                            "lag": 1, "label": "Disinflation (low breakevens)"}
    cot = _col("cot", "cot_gold", "net_spec_pct_oi")
    if not cot.empty:
        legs["positioning"] = {"series": _onto(_pctile(cot, 156), i, 5), "weight": 0.6,
                              "lag": 5, "label": "Speculators over-long"}
    legs["trend"] = {"series": _onto(_trend_off(bench), i, 0), "weight": 0.8, "lag": 0,
                     "label": "Downtrend (TSMOM)"}
    return _compose(legs, i)


# --------------------------------------------------------------------------- #
# SILVER multifactor — gold's monetary legs + industrial (copper) + GSR + positioning
# --------------------------------------------------------------------------- #
def _sc_silver_mf(ctx, bench) -> dict:
    i = bench.index
    legs = {"trend": {"series": _onto(_trend_off(bench), i, 0), "weight": 1.0, "lag": 0,
                      "label": "Trend (TSMOM)"}}
    dfii = _fred("DFII10")
    if not dfii.empty:
        legs["realy"] = {"series": _onto(_pctile(dfii.diff(63), _W5Y), i, 1), "weight": 0.8,
                         "lag": 1, "label": "Real yields rising"}
    usd = _fred("DTWEXBGS")
    if not usd.empty:
        legs["usd"] = {"series": _onto(_pctile(usd.diff(63), _W5Y), i, 2), "weight": 0.7,
                       "lag": 2, "label": "Broad dollar rising"}
    be = _fred("T10YIE")
    if not be.empty:
        legs["infl"] = {"series": _onto(1.0 - _pctile(be, _W5Y), i, 1), "weight": 0.4,
                        "lag": 1, "label": "Inflation expectations falling"}
    hg = _yclose("HG=F")
    if not hg.empty:
        legs["copper"] = {"series": _onto(_trend_off(hg), i, 1), "weight": 0.7, "lag": 1,
                          "label": "Copper downtrend (weak growth)"}
    gc = _yclose("GC=F")
    if not gc.empty:
        ratio = (gc.reindex(i, method="ffill") / bench.reindex(i, method="ffill")).dropna()
        legs["gsr"] = {"series": _onto(1.0 - _pctile(ratio, _W5Y), i, 1), "weight": 0.5,
                       "lag": 1, "label": "Gold/silver ratio low (silver rich)"}
    cot = _col("cot", "cot_silver", "net_spec_pct_oi")
    if not cot.empty:
        legs["cot"] = {"series": _onto(_pctile(cot, _W5Y), i, 7), "weight": 0.5, "lag": 7,
                       "label": "Speculators over-long"}
    legs["vol"] = {"series": _onto(_vol_off(bench), i, 1), "weight": 0.5, "lag": 1,
                   "label": "Realized-volatility guard"}
    return _compose(legs, i)


# --------------------------------------------------------------------------- #
# COPPER multifactor — copper/gold ratio + China credit impulse + US IP + USD + trend
# --------------------------------------------------------------------------- #
def _sc_copper_mf(ctx, bench) -> dict:
    i = bench.index
    legs = {}
    gc = _yclose("GC=F")
    if not gc.empty:
        ratio = (bench / gc.reindex(bench.index, method="ffill")).dropna()
        ratio_mom = ratio / ratio.shift(126) - 1.0
        legs["ratio"] = {"series": _onto(_pctile(-ratio_mom, _W5Y), i, 1), "weight": 1.0,
                         "lag": 1, "label": "Copper/gold rolling over"}
    tsf = _col("china_credit", "tsf", "tsf_total")
    if not tsf.empty:
        impulse = tsf.rolling(12).sum().diff(12)
        legs["china"] = {"series": _onto(_pctile(-impulse, 60), i, 30), "weight": 1.0,
                         "lag": 30, "label": "China credit impulse falling"}
    ip = _fred("INDPRO", "industrial_prod")
    if not ip.empty:
        ip_mom = ip / ip.shift(6) - 1.0
        legs["indpro"] = {"series": _onto(_pctile(-ip_mom, 60), i, 30), "weight": 0.7,
                          "lag": 30, "label": "US industrial production decelerating"}
    usd = _fred("DTWEXBGS")
    if not usd.empty:
        legs["usd"] = {"series": _onto(_pctile(usd / usd.shift(63) - 1.0, _W5Y), i, 1),
                       "weight": 0.7, "lag": 1, "label": "Broad dollar rising"}
    legs["trend"] = {"series": _onto(_trend_off(bench), i, 0), "weight": 0.6, "lag": 0,
                     "label": "Trend (TSMOM)"}
    return _compose(legs, i)


# --------------------------------------------------------------------------- #
# OIL multifactor — USD-led + backwardation + trend + vol (inventory/COT dropped)
# --------------------------------------------------------------------------- #
def _sc_oil_mf(ctx, bench) -> dict:
    i = bench.index
    legs = {}
    usd = _fred("DTWEXBGS")
    if not usd.empty:
        legs["usd"] = {"series": _onto(_pctile(usd.diff(63), _W5Y), i, 1), "weight": 1.0,
                       "lag": 1, "label": "Broad dollar rising"}
    bw = _col("commodity", "signals_oil", "bw_spread")
    if not bw.empty:
        legs["backwardation"] = {"series": _onto(1.0 - _pctile(bw, _W5Y), i, 1), "weight": 0.5,
                                 "lag": 1, "label": "Term structure (contango / loose)"}
    legs["trend"] = {"series": _onto(_trend_off(bench), i, 0), "weight": 1.5, "lag": 0,
                     "label": "Trend (TSMOM)"}
    legs["vol"] = {"series": _onto(_vol_off(bench), i, 1), "weight": 1.0, "lag": 1,
                   "label": "Realized-volatility guard"}
    return _compose(legs, i)


# --------------------------------------------------------------------------- #
# factory + the 8 config rows (swap + multifactor per gold/silver/copper/oil)
# --------------------------------------------------------------------------- #
def _make(cfg: dict) -> StrategySpec:
    tk, score_fn = cfg["ticker"], cfg["score"]

    def benchmark(ctx, tk=tk):
        b = _yclose(tk)
        return b[b > 0]                       # guard against any bad/negative prints

    def cash_yield(ctx):
        return ea.bill_yield()

    def risk_yield(ctx):
        return pd.Series(0.0, index=benchmark(ctx).index)   # commodities pay no income

    def score(ctx, bench, score_fn=score_fn):
        return score_fn(ctx, bench)

    def alloc(ctx, bench, score_fn=score_fn):
        sc = score_fn(ctx, bench)["score"]
        return ea.glide_path(sc).reindex(bench.index, method="ffill").fillna(1.0)

    return StrategySpec(
        key=cfg["key"], icon=cfg["icon"], name_en=cfg["name_en"], name_zh=cfg["name_zh"],
        thesis_en=cfg["thesis_en"], thesis_zh=cfg["thesis_zh"],
        bench_en=cfg["bench_en"], bench_zh=cfg["bench_zh"], cash_en="T-bills", cash_zh="短期国债",
        risk_word_en=cfg["risk_word_en"], risk_word_zh=cfg["risk_word_zh"],
        benchmark=benchmark, alloc=alloc, cash_yield=cash_yield, risk_yield=risk_yield,
        score=score, experimental=True, group=cfg["group"],
        caveat_en=cfg["caveat_en"], caveat_zh=cfg["caveat_zh"])


def _cav(asset_en, asset_zh, span, note_en, note_zh):
    return (f"Commodity, display-only / experimental. Benchmark = {asset_en} continuous front-month "
            f"total-return close ({span}); the de-risked sleeve earns the T-bill yield. {note_en} "
            "Macro legs activate once their FRED series begin (real yields/breakevens 2003, broad USD 2006). "
            "Full Phase-0 is a fast-follow.",
            f"商品，仅展示 / 实验性。基准 = {asset_zh}连续近月总回报收盘价（{span}）；降险时空仓腿赚取短期国债收益。{note_zh} "
            "宏观腿在其 FRED 序列开始后才激活（实际收益率/通胀预期 2003 年、广义美元 2006 年）。完整 Phase-0 为后续跟进。")


_SWAP_NOTE = ("The simple risk on/off baseline — trend (time-series momentum) plus a realized-vol guard.",
              "简单的风险开关基准——趋势（时间序列动量）加已实现波动率护栏。")

_NEW_CFG: list[dict] = [
    # -------------------------------- GOLD -------------------------------- #
    {"key": "cm_gold_swap", "group": "gold", "icon": "🥇", "ticker": "GC=F", "score": _swap_score,
     "name_en": "Gold Trend Swap", "name_zh": "黄金趋势开关",
     "bench_en": "Gold", "bench_zh": "黄金", "risk_word_en": "Down-trend / vol", "risk_word_zh": "下行趋势 / 波动",
     "thesis_en": "Ride gold's trend; step to T-bills when momentum turns down and volatility spikes.",
     "thesis_zh": "顺黄金趋势持有；动量转跌、波动飙升时退守短债。",
     "caveat_en": _cav("Gold (GC=F)", "黄金 (GC=F)", "2000→", *_SWAP_NOTE)[0],
     "caveat_zh": _cav("Gold (GC=F)", "黄金 (GC=F)", "2000→", *_SWAP_NOTE)[1]},
    {"key": "cm_gold_macro", "group": "gold", "icon": "🏵️", "ticker": "GC=F", "score": _sc_gold_mf,
     "name_en": "Gold Macro Driver Model", "name_zh": "黄金宏观驱动模型",
     "bench_en": "Gold", "bench_zh": "黄金", "risk_word_en": "Monetary headwind", "risk_word_zh": "货币逆风",
     "thesis_en": "Gold's drivers, modelled: own it when real yields are falling and the dollar is weak; lean out when real yields rise, the dollar firms, disinflation sets in, or speculators are over-crowded.",
     "thesis_zh": "为黄金的驱动因素建模：实际收益率下行、美元走弱时持有；实际收益率上行、美元走强、通缩或投机过度拥挤时减仓。",
     "caveat_en": _cav("Gold (GC=F)", "黄金 (GC=F)", "2000→",
                       "Real-yield / dollar / breakeven / positioning model — its job is the deep drawdown cut, not maximal CAGR.",
                       "实际收益率 / 美元 / 通胀预期 / 持仓模型——其作用是削减深度回撤，而非追求最大年化。")[0],
     "caveat_zh": _cav("Gold (GC=F)", "黄金 (GC=F)", "2000→",
                       "Real-yield / dollar / breakeven / positioning model — its job is the deep drawdown cut, not maximal CAGR.",
                       "实际收益率 / 美元 / 通胀预期 / 持仓模型——其作用是削减深度回撤，而非追求最大年化。")[1]},
    # ------------------------------- SILVER ------------------------------- #
    {"key": "cm_silver_swap", "group": "silver", "icon": "🥈", "ticker": "SI=F", "score": _swap_score,
     "name_en": "Silver Trend Swap", "name_zh": "白银趋势开关",
     "bench_en": "Silver", "bench_zh": "白银", "risk_word_en": "Down-trend / vol", "risk_word_zh": "下行趋势 / 波动",
     "thesis_en": "Trend + vol guard on silver — kept as the honest baseline: on silver, this does NOT beat buy-&-hold (silver's whippy tape punishes a pure trend timer).",
     "thesis_zh": "白银的趋势 + 波动护栏——作为诚实基准保留：在白银上，它并不跑赢买入持有（白银的剧烈走势惩罚纯趋势择时）。",
     "caveat_en": _cav("Silver (SI=F)", "白银 (SI=F)", "2000→", *_SWAP_NOTE)[0],
     "caveat_zh": _cav("Silver (SI=F)", "白银 (SI=F)", "2000→", *_SWAP_NOTE)[1]},
    {"key": "cm_silver_macro", "group": "silver", "icon": "⚙️", "ticker": "SI=F", "score": _sc_silver_mf,
     "name_en": "Silver Macro + Industrial Model", "name_zh": "白银宏观 + 工业模型",
     "bench_en": "Silver", "bench_zh": "白银", "risk_word_en": "Monetary + growth headwind", "risk_word_zh": "货币 + 增长逆风",
     "thesis_en": "Silver = high-beta gold + an industrial kicker. Combine gold's monetary legs with copper-led growth, gold/silver-ratio mean-reversion and a positioning guard — this beats the trend swap and buy-&-hold on Sharpe and drawdown.",
     "thesis_zh": "白银 = 高贝塔黄金 + 工业属性。将黄金的货币腿与铜主导的增长、金银比均值回归及持仓护栏结合——在夏普与回撤上跑赢趋势开关与买入持有。",
     "caveat_en": _cav("Silver (SI=F)", "白银 (SI=F)", "2000→",
                       "Monetary (real yields/USD/breakevens) + industrial (copper trend, gold/silver ratio) + positioning + vol. Its edge over the trend swap is the whole point of modelling silver specifically.",
                       "货币（实际收益率/美元/通胀预期）+ 工业（铜趋势、金银比）+ 持仓 + 波动。其相对趋势开关的优势正是为白银专门建模的意义。")[0],
     "caveat_zh": _cav("Silver (SI=F)", "白银 (SI=F)", "2000→",
                       "Monetary (real yields/USD/breakevens) + industrial (copper trend, gold/silver ratio) + positioning + vol. Its edge over the trend swap is the whole point of modelling silver specifically.",
                       "货币（实际收益率/美元/通胀预期）+ 工业（铜趋势、金银比）+ 持仓 + 波动。其相对趋势开关的优势正是为白银专门建模的意义。")[1]},
    # ------------------------------- COPPER ------------------------------- #
    {"key": "cm_copper_swap", "group": "copper", "icon": "🟤", "ticker": "HG=F", "score": _swap_score,
     "name_en": "Copper Trend Swap", "name_zh": "铜趋势开关",
     "bench_en": "Copper", "bench_zh": "铜", "risk_word_en": "Down-trend / vol", "risk_word_zh": "下行趋势 / 波动",
     "thesis_en": "Trend + vol guard on copper — cuts the brutal cyclical drawdowns while keeping most of the upside.",
     "thesis_zh": "铜的趋势 + 波动护栏——削减残酷的周期性回撤，同时保留大部分上行。",
     "caveat_en": _cav("Copper (HG=F)", "铜 (HG=F)", "2000→", *_SWAP_NOTE)[0],
     "caveat_zh": _cav("Copper (HG=F)", "铜 (HG=F)", "2000→", *_SWAP_NOTE)[1]},
    {"key": "cm_copper_macro", "group": "copper", "icon": "🏗️", "ticker": "HG=F", "score": _sc_copper_mf,
     "name_en": "Copper Growth & Dollar Model", "name_zh": "铜·增长与美元模型",
     "bench_en": "Copper", "bench_zh": "铜", "risk_word_en": "Growth slowing", "risk_word_zh": "增长放缓",
     "thesis_en": "Dr. Copper, modelled: own it when the copper/gold ratio is firm, China's credit impulse and US industrial production are accelerating, and the dollar is soft; step aside when growth rolls over.",
     "thesis_zh": "为‘铜博士’建模：铜金比走强、中国信用脉冲与美国工业生产加速、美元偏弱时持有；增长回落时退避。",
     "caveat_en": _cav("Copper (HG=F)", "铜 (HG=F)", "2000→",
                       "Copper/gold ratio + China credit impulse + US industrial production + broad USD + trend. Roughly matches buy-&-hold CAGR while nearly halving the drawdown.",
                       "铜金比 + 中国信用脉冲 + 美国工业生产 + 广义美元 + 趋势。年化与买入持有大致持平，回撤近乎减半。")[0],
     "caveat_zh": _cav("Copper (HG=F)", "铜 (HG=F)", "2000→",
                       "Copper/gold ratio + China credit impulse + US industrial production + broad USD + trend. Roughly matches buy-&-hold CAGR while nearly halving the drawdown.",
                       "铜金比 + 中国信用脉冲 + 美国工业生产 + 广义美元 + 趋势。年化与买入持有大致持平，回撤近乎减半。")[1]},
    # -------------------------------- OIL --------------------------------- #
    {"key": "cm_oil_swap", "group": "oil", "icon": "🛢️", "ticker": "BZ=F", "score": _swap_score,
     "name_en": "Oil Trend Swap", "name_zh": "原油趋势开关",
     "bench_en": "Brent crude", "bench_zh": "布伦特原油", "risk_word_en": "Down-trend / vol", "risk_word_zh": "下行趋势 / 波动",
     "thesis_en": "Trend + vol guard on Brent — oil is a brutal buy-and-hold (it crashed in 2008, 2014-16 and 2020), so even the simple swap transforms the return profile.",
     "thesis_zh": "布伦特原油的趋势 + 波动护栏——原油买入持有极其惨烈（2008、2014-16、2020 均暴跌），因此即便简单开关也能重塑收益曲线。",
     "caveat_en": _cav("Brent crude (BZ=F)", "布伦特原油 (BZ=F)", "2007→",
                       "Brent (not WTI) avoids the 2020 negative-price artifact. " + _SWAP_NOTE[0], "")[0],
     "caveat_zh": _cav("Brent crude (BZ=F)", "布伦特原油 (BZ=F)", "2007→", "",
                       "使用布伦特（而非 WTI）以规避 2020 年负价格异常。" + _SWAP_NOTE[1])[1]},
    {"key": "cm_oil_macro", "group": "oil", "icon": "🛢", "ticker": "BZ=F", "score": _sc_oil_mf,
     "name_en": "Oil Macro Multifactor", "name_zh": "原油宏观多因子",
     "bench_en": "Brent crude", "bench_zh": "布伦特原油", "risk_word_en": "Dollar + glut", "risk_word_zh": "美元 + 过剩",
     "thesis_en": "A USD-led oil model: a rising broad dollar is the cleanest fundamental headwind, backwardation flags a physically tight market, and trend carries the crash-avoidance. Inventory & positioning were tested and dropped (no forward edge).",
     "thesis_zh": "以美元主导的原油模型：广义美元走强是最干净的基本面逆风，现货升水（backwardation）标志现货市场紧张，趋势承担避免暴跌的职责。库存与持仓经检验后剔除（无前瞻性）。",
     "caveat_en": _cav("Brent crude (BZ=F)", "布伦特原油 (BZ=F)", "2007→",
                       "USD (lead) + term-structure backwardation + trend + vol. Inventory-vs-seasonal and COT positioning were tested and DROPPED (wrong-signed / no forward edge). Beats buy-&-hold on all three metrics.",
                       "美元（主导）+ 期限结构升水 + 趋势 + 波动。库存季节性与 COT 持仓经检验后剔除（符号错误 / 无前瞻性）。在三项指标上均跑赢买入持有。")[0],
     "caveat_zh": _cav("Brent crude (BZ=F)", "布伦特原油 (BZ=F)", "2007→",
                       "USD (lead) + term-structure backwardation + trend + vol. Inventory-vs-seasonal and COT positioning were tested and DROPPED (wrong-signed / no forward edge). Beats buy-&-hold on all three metrics.",
                       "美元（主导）+ 期限结构升水 + 趋势 + 波动。库存季节性与 COT 持仓经检验后剔除（符号错误 / 无前瞻性）。在三项指标上均跑赢买入持有。")[1]},
]

COMMODITY_STRATEGIES: list[StrategySpec] = [_make(c) for c in _NEW_CFG]

# display order of the commodity toggle + per-group labels/icons
COMMODITY_GROUPS = [
    {"key": "gold", "icon": "🥇", "label_en": "Gold", "label_zh": "黄金"},
    {"key": "silver", "icon": "🥈", "label_en": "Silver", "label_zh": "白银"},
    {"key": "copper", "icon": "🟤", "label_en": "Copper", "label_zh": "铜"},
    {"key": "oil", "icon": "🛢️", "label_en": "Oil", "label_zh": "原油"},
]


def by_key(key: str) -> StrategySpec | None:
    return next((s for s in COMMODITY_STRATEGIES if s.key == key), None)


# per-leg display metadata (colour + 中文) for the commodity detail pages
CM_LEG_META = {
    "trend": ("#0891b2", "趋势（时间序列动量）"),
    "vol": ("#7c3aed", "已实现波动率护栏"),
    "real_yield": ("#285fff", "实际收益率上行"),
    "realy": ("#285fff", "实际收益率上行"),
    "usd": ("#0d9488", "广义美元走强"),
    "breakeven": ("#e0a106", "通缩（通胀预期低）"),
    "infl": ("#e0a106", "通胀预期下行"),
    "positioning": ("#e5484d", "投机过度做多"),
    "cot": ("#e5484d", "投机过度做多"),
    "copper": ("#b45309", "铜下行趋势（增长走弱）"),
    "gsr": ("#9333ea", "金银比偏低（白银偏贵）"),
    "ratio": ("#b45309", "铜金比走弱"),
    "china": ("#C0392B", "中国信用脉冲下行"),
    "indpro": ("#ea580c", "美国工业生产减速"),
    "backwardation": ("#0891b2", "期限结构（contango / 宽松）"),
}
CM_STANCE: dict = {}   # empty → _card falls back to each spec's own bench/cash labels
