"""Generate the static dashboard (site/macro.html) from stored engine output.

Reads regime/latest.json, regime_history.parquet, run_status.json and the
parquet store — never refetches and never recomputes the classifier, so the
site builds even when every scraper is down.

Usage: python -m scripts.build_site
"""
from __future__ import annotations

import calendar
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.holdings import active_changes  # noqa: E402
from collectors.sponsors import flows_table  # noqa: E402
from engine.i18n import t as T  # noqa: E402
from engine.i18n import tr as TR  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_site")

QUAD_COLORS = {"Q1": "#2e9e4f", "Q2": "#d4a017", "Q3": "#d04545", "Q4": "#3f78d8"}
# Charts render on a TRANSPARENT surface so they sit on whatever card colour the
# active theme provides (white in light mode, dark panel in dark) — no more
# dark-slate rectangles inside white cards. Font + gridlines default to a neutral
# mid-grey that stays legible on either background; theme.js then re-themes them
# crisply for the active theme on load and on toggle (Plotly.relayout). The one
# near-white trace (SPY, below) is recoloured to a neutral slate so it stays
# visible on white too. The .chart/.tv wrapper rounds the corners to match.
PLOT_LAYOUT = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)", font={"size": 11, "color": "#8b93a1"},
    xaxis={"gridcolor": "rgba(128,138,160,0.16)", "zerolinecolor": "rgba(128,138,160,0.28)"},
    yaxis={"gridcolor": "rgba(128,138,160,0.16)", "zerolinecolor": "rgba(128,138,160,0.28)"},
    margin={"l": 45, "r": 15, "t": 10, "b": 30}, height=300,
    legend={"orientation": "h", "y": 1.08},
)


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False})


def _range_selector() -> dict:
    return dict(
        buttons=[
            dict(count=1, label="1M", step="month", stepmode="backward"),
            dict(count=3, label="3M", step="month", stepmode="backward"),
            dict(count=6, label="6M", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1Y", step="year", stepmode="backward"),
            dict(step="all", label="All"),
        ],
        bgcolor="rgba(128,138,160,0.14)", activecolor="rgba(120,167,224,0.55)",
        bordercolor="rgba(128,138,160,0.30)", borderwidth=1,
        font={"size": 10, "color": "#8b93a1"},
        x=0, xanchor="left", y=1.0, yanchor="bottom",
    )


def _apply_range(fig: go.Figure, *, subplot: bool = False, has_legend: bool = False,
                 height: int = 300) -> None:
    """Add 1M…All range-selector buttons to the (date) x-axis and make room for
    them. Colours are theme-neutral — the buttons are baked at build time and do
    not re-theme on toggle, so they must read on both light and dark cards. The
    companion charts.js rescales the y-axis to the visible window on zoom (it
    leaves fixed-range axes, e.g. the ±1 score chart, alone)."""
    if subplot:
        # make_subplots(shared_xaxes=True) makes the TOP x-axis FOLLOW the bottom
        # (xaxis.matches='x2'); a rangeselector on a follower axis is inert — the
        # button click gets overridden back. Flip the link so the TOP axis drives
        # (bottom follows it), then the selector sits at the top AND works.
        fig.update_xaxes(matches=None, row=1, col=1)
        fig.update_xaxes(matches="x", row=2, col=1)
        fig.update_xaxes(rangeselector=_range_selector(), row=1, col=1)
    else:
        fig.update_xaxes(rangeselector=_range_selector())
    top = 58 if has_legend else 40
    fig.update_layout(margin={"l": 45, "r": 15, "t": top, "b": 30}, height=height)
    if has_legend:
        fig.update_layout(legend={"orientation": "h", "y": 1.26, "x": 0, "xanchor": "left"})


def chart_regime(f: pd.DataFrame, hist: pd.DataFrame, days: int = 730) -> str:
    two_y = f.index.max() - pd.Timedelta(days=days)
    spy = f.loc[two_y:, "SPY"].dropna()
    sub = hist.loc[two_y:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=spy.index, y=spy, name="SPY",
                             line={"color": "#64748b", "width": 1.5}))
    q = sub["quad"].dropna()
    if not q.empty:
        seg_id = (q != q.shift()).cumsum()
        for _, seg in q.groupby(seg_id):
            fig.add_vrect(x0=seg.index.min(), x1=seg.index.max(),
                          fillcolor=QUAD_COLORS.get(seg.iloc[0], "#888"),
                          opacity=0.16, line_width=0)
    fig.update_layout(**PLOT_LAYOUT, showlegend=False)
    _apply_range(fig, height=300)
    return _html(fig)


def chart_axes(hist: pd.DataFrame, days: int = 730) -> str:
    two_y = hist.index.max() - pd.Timedelta(days=days)
    sub = hist.loc[two_y:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub.index, y=sub["growth_score"], name="growth",
                             line={"color": "#5fbf7f", "width": 1.2}))
    fig.add_trace(go.Scatter(x=sub.index, y=sub["inflation_score"], name="inflation",
                             line={"color": "#e07070", "width": 1.2}))
    fig.add_hline(y=0, line={"color": "#666", "width": 0.6})
    fig.update_layout(**PLOT_LAYOUT)
    # autorange=False is what charts.js keys off to LEAVE this axis fixed on zoom —
    # the ±1 band is the meaning here, so it must not rescale to the visible slice
    fig.update_yaxes(range=[-1.05, 1.05], autorange=False)
    _apply_range(fig, has_legend=True, height=300)
    return _html(fig)


def chart_liquidity(f: pd.DataFrame) -> str:
    cfg = config.load()["engine"]["liquidity"]
    two_y = f.index.max() - pd.Timedelta(days=730)
    nl = f.loc[two_y:, "net_liquidity_bn"].dropna()
    roc = (f["net_liquidity_bn"] - f["net_liquidity_bn"].shift(cfg["roc_window_d"])).loc[two_y:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                        vertical_spacing=0.06)
    fig.add_trace(go.Scatter(x=nl.index, y=nl, name="net liquidity",
                             line={"color": "#7aa7e0", "width": 1.3}), row=1, col=1)
    fig.add_trace(go.Bar(x=roc.index, y=roc, name="4w RoC",
                         marker={"color": ["#5fbf7f" if v >= 0 else "#e07070"
                                           for v in roc.fillna(0)]}), row=2, col=1)
    fig.add_hline(y=cfg["expanding_threshold_bn"], line={"color": "#5fbf7f", "width": 0.5,
                                                         "dash": "dot"}, row=2, col=1)
    fig.add_hline(y=cfg["contracting_threshold_bn"], line={"color": "#e07070", "width": 0.5,
                                                           "dash": "dot"}, row=2, col=1)
    layout = {**PLOT_LAYOUT, "height": 340}
    fig.update_layout(**layout, showlegend=False)
    _apply_range(fig, subplot=True, height=340)
    return _html(fig)


def chart_credit_breadth(f: pd.DataFrame) -> str:
    two_y = f.index.max() - pd.Timedelta(days=730)
    oas = f.loc[two_y:, "hy_oas"].dropna()
    br = f.loc[two_y:, "pct_above_50"].dropna()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06)
    fig.add_trace(go.Scatter(x=oas.index, y=oas, name="HY OAS %",
                             line={"color": "#e0a030", "width": 1.2}), row=1, col=1)
    fig.add_trace(go.Scatter(x=br.index, y=br, name="% S&P500 > 50DMA",
                             line={"color": "#9b8de0", "width": 1.2}), row=2, col=1)
    # small-cap participation (S&P 600) overlaid — large strong / small weak = fragile,
    # small leading = broadening. The gap between the two lines IS the divergence read.
    scb = f.loc[two_y:, "sc_pct_above_50"].dropna()
    if not scb.empty:
        fig.add_trace(go.Scatter(x=scb.index, y=scb, name="% small-cap > 50DMA",
                                 line={"color": "#4fb39a", "width": 1.2}), row=2, col=1)
    layout = {**PLOT_LAYOUT, "height": 340}
    fig.update_layout(**layout)
    _apply_range(fig, subplot=True, has_legend=True, height=340)
    return _html(fig)


def _crowd_words(p: float, lo_word: str, hi_word: str,
                 lo_verdict: str, hi_verdict: str,
                 lo_word_zh: str, hi_word_zh: str,
                 lo_verdict_zh: str, hi_verdict_zh: str) -> tuple[T, T]:
    """Percentile -> (label, verdict) in plain language. The vocabulary differs
    per input (long/short, cash/all-in, calm/panic) but the shape is shared.
    Returns bilingual T(...) markup for both label and verdict."""
    if p >= 95:
        return (T(f"extreme {hi_word}", f"极度{hi_word_zh}"),
                T(f"{hi_verdict} — most extreme in our records; contrarian alert",
                  f"{hi_verdict_zh} — 我们记录中最极端；反向预警"))
    if p >= 85:
        return (T(f"crowded {hi_word}", f"拥挤{hi_word_zh}"),
                T(f"{hi_verdict} — crowded; late to join",
                  f"{hi_verdict_zh} — 拥挤；加入已晚"))
    if p >= 60:
        return (T(f"leaning {hi_word}", f"偏向{hi_word_zh}"),
                T("above normal, nothing extreme", "高于正常，但不极端"))
    if p > 40:
        return (T("normal", "正常"), T("nothing notable", "无显著"))
    if p > 15:
        return (T(f"leaning {lo_word}", f"偏向{lo_word_zh}"),
                T("below normal, nothing extreme", "低于正常，但不极端"))
    if p > 5:
        return (T(f"crowded {lo_word}", f"拥挤{lo_word_zh}"),
                T(f"{lo_verdict} — stretched; squeezes start here",
                  f"{lo_verdict_zh} — 已拉伸；逼空由此开始"))
    return (T(f"extreme {lo_word}", f"极度{lo_word_zh}"),
            T(f"{lo_verdict} — most extreme in our records; reversal fuel",
              f"{lo_verdict_zh} — 我们记录中最极端；反转燃料"))


def positioning_rows(f: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []

    def pctile(s: pd.Series) -> float | None:
        s = s.dropna()
        if len(s) < 50:
            return None
        return float(s.rank(pct=True).iloc[-1] * 100)

    cot_meta = {
        "cot_es_spx": (T("S&P 500 futures speculators", "标普500 期货投机者"),
                       "Net bets of speculative futures traders on the S&P 500, as % of all open "
                       "contracts (CFTC weekly data). Deeply negative + low percentile = everyone's "
                       "already short — fuel for squeezes. Very high = crowded long.",
                       "投机性期货交易者在标普500上的净头寸，占全部未平仓合约的百分比（CFTC 周度数据）。"
                       "深度为负 + 低百分位 = 大家都已做空 — 逼空燃料。极高 = 拥挤做多。"),
        "cot_ust10y": (T("10-yr Treasury futures speculators", "10年期美债 期货投机者"),
                       "Speculators' net position in 10-year Treasury futures. Extreme shorts have "
                       "historically preceded falling yields (bond rallies), and vice versa.",
                       "投机者在10年期美债期货上的净头寸。历史上极端做空往往先于收益率下行（债券上涨），反之亦然。"),
        "cot_dollar": (T("US Dollar futures speculators", "美元 期货投机者"),
                       "Speculators' net position on the dollar index. Extremes tend to mark dollar "
                       "turning points, which matter for commodities and foreign earnings.",
                       "投机者在美元指数上的净头寸。极端值往往标志美元的转折点，对大宗商品与海外盈利至关重要。"),
        "cot_gold": (T("Gold futures speculators", "黄金 期货投机者"),
                     "Speculators' net position in gold futures. Near the 100th percentile = the "
                     "most crowded gold trade in decades — vulnerable to shakeouts.",
                     "投机者在黄金期货上的净头寸。接近第100百分位 = 数十年来最拥挤的黄金交易 — 易遭洗盘。"),
    }
    for key, (label, tip_en, tip_zh) in cot_meta.items():
        df = store.read("cot", key)
        if df is not None and "net_spec_pct_oi" in df.columns and len(df):
            s = df["net_spec_pct_oi"]
            p = pctile(s)
            word, verdict = _crowd_words(p, "short", "long",
                                         "everyone is already short",
                                         "everyone is already long",
                                         "做空", "做多",
                                         "大家都已做空",
                                         "大家都已做多") if p is not None \
                else (T("history building", "历史积累中"), T("", ""))
            rows.append({"name": label, "pct": p, "label": word, "verdict": verdict,
                         "left": T("crowded short", "拥挤做空"), "right": T("crowded long", "拥挤做多"),
                         "tip": T(tip_en + f" Today: {s.iloc[-1]:+.1f}% of open contracts"
                                  + (f", {p:.0f}th percentile of 30 years" if p is not None else "")
                                  + f" (as of {df.index.max().date()}, 3-day reporting lag).",
                                  tip_zh + f" 今日：占未平仓合约 {s.iloc[-1]:+.1f}%"
                                  + (f"，30年内第 {p:.0f} 百分位" if p is not None else "")
                                  + f"（截至 {df.index.max().date()}，报告延迟3天）。"),
                         })
    naaim = store.read("sentiment", "naaim")
    if naaim is not None and len(naaim):
        s = naaim.iloc[:, 0]
        p = pctile(s)
        word, verdict = _crowd_words(p, "cautious", "invested",
                                     "managers are hiding in cash",
                                     "managers are nearly all-in",
                                     "谨慎", "重仓",
                                     "基金经理躲入现金",
                                     "基金经理几乎满仓") if p is not None \
            else (T("history building", "历史积累中"), T("", ""))
        rows.append({"name": T("Pro fund managers", "专业基金经理"), "pct": p,
                     "label": word, "verdict": verdict,
                     "left": T("all cash", "全现金"), "right": T("all-in", "满仓"),
                     "tip": T("NAAIM weekly survey of professional active managers' stock exposure "
                              "(0 = all cash, 100 = fully invested, >100 = leveraged). Extremes are "
                              f"contrarian. Today: {s.iloc[-1]:.0f}"
                              + (f", {p:.0f}th percentile since 2006" if p is not None else "")
                              + f" (as of {naaim.index.max().date()}).",
                              "NAAIM 对专业主动型管理者股票敞口的周度调查"
                              "（0 = 全现金，100 = 满仓，>100 = 加杠杆）。极端值具反向意义。"
                              f"今日：{s.iloc[-1]:.0f}"
                              + (f"，2006年以来第 {p:.0f} 百分位" if p is not None else "")
                              + f"（截至 {naaim.index.max().date()}）。"),
                     })
    pc = store.read("cboe", "putcall")
    if pc is not None and len(pc) and "index_pc_ratio" in pc.columns:
        v = float(pc["index_pc_ratio"].iloc[-1])
        if v >= 1.3:
            word = T("heavy hedging", "大量对冲")
            verdict = T("lots of downside protection being bought — fear elevated",
                        "大量买入下行保护 — 恐慌升高")
        elif v >= 1.0:
            word = T("guarded", "警惕")
            verdict = T("more puts than calls — mild caution", "看跌多于看涨 — 轻度谨慎")
        elif v >= 0.8:
            word = T("balanced", "均衡")
            verdict = T("nothing notable", "无显著")
        else:
            word = T("complacent", "自满")
            verdict = T("very few hedges — markets unprepared for bad news",
                        "极少对冲 — 市场对坏消息毫无防备")
        rows.append({"name": T("Options hedging mood", "期权对冲情绪"), "pct": None, "label": word,
                     "verdict": verdict, "left": "", "right": "",
                     "tip": T("Put/call volume ratio on S&P index options, computed from CBOE's "
                              "chain: bearish bets ÷ bullish bets traded today. Above ~1.3 = heavy "
                              f"hedging; below ~0.8 = complacency. Today: {v:.2f} "
                              f"(as of {pc.index.max().date()}). A young series — labels are based "
                              "on standard thresholds until enough history accrues.",
                              "标普指数期权的看跌/看涨成交量比，由 CBOE 期权链计算："
                              "今日看空押注 ÷ 看多押注。高于约1.3 = 大量对冲；低于约0.8 = 自满。"
                              f"今日：{v:.2f}（截至 {pc.index.max().date()}）。"
                              "这是一个较新的序列 — 在积累足够历史前，标签基于标准阈值。"),
                     })
    gex = store.read("cboe", "gex")
    if gex is not None and len(gex):
        g = gex.iloc[-1]
        pos = g["net_gex_bn"] > 0
        near = pd.notna(g.get("spot_vs_flip_pct")) and abs(g["spot_vs_flip_pct"]) < 2
        word = T("dampening swings", "抑制波动") if pos else T("amplifying swings", "放大波动")
        verdict_en = ("market-makers' hedging absorbs moves — calmer tape likely" if pos else
                      "market-makers' hedging adds fuel to moves — expect bigger swings both ways")
        verdict_zh = ("做市商对冲吸收波动 — 盘面可能更平静" if pos else
                      "做市商对冲为波动添柴 — 预期双向波动更大")
        if near:
            verdict_en += " (and we're near the tipping point — it can flip any day)"
            verdict_zh += "（且我们已接近临界点 — 随时可能反转）"
        rows.append({"name": T("Market-maker effect", "做市商效应"), "pct": None, "label": word,
                     "verdict": T(verdict_en, verdict_zh), "left": "", "right": "",
                     "tip": T("Estimated dealer gamma (GEX) from the S&P options chain, standard "
                              "assumption (dealers long calls/short puts). Positive = their hedging "
                              "dampens market moves; negative = it amplifies them. Today: "
                              f"{g['net_gex_bn']:+.0f}bn per 1% move "
                              f"(as of {gex.index.max().date()}). An estimate, not ground truth.",
                              "由标普期权链估算的做市商 gamma（GEX），采用标准假设"
                              "（做市商持有多头看涨/空头看跌）。正值 = 其对冲抑制市场波动；"
                              f"负值 = 放大波动。今日：每1%波动 {g['net_gex_bn']:+.0f}十亿 "
                              f"（截至 {gex.index.max().date()}）。这是估算，并非真实值。"),
                     })
    vr = f["vix_ratio"].dropna()
    if len(vr):
        p = pctile(vr)
        if p is not None:
            word, verdict = _crowd_words(p, "calm", "stressed",
                                         "unusually calm conditions",
                                         "near-term fear is spiking",
                                         "平静", "紧张",
                                         "异常平静的环境",
                                         "近期恐慌正在飙升")
            rows.append({"name": T("Fear gauge", "恐慌指标"), "pct": p, "label": word,
                         "verdict": verdict,
                         "left": T("calm", "平静"), "right": T("panic", "恐慌"),
                         "tip": T("VIX (30-day expected volatility) ÷ VIX3M (3-month). Below ~0.9 = "
                                  "calm; near/above 1.0 = the market fears the immediate future more "
                                  f"than the distant one — the classic stress signature. Today: "
                                  f"{vr.iloc[-1]:.3f}, {p:.0f}th percentile since 2006.",
                                  "VIX（30天预期波动率）÷ VIX3M（3个月）。低于约0.9 = 平静；"
                                  "接近/高于1.0 = 市场对近期的恐惧超过对远期 — 经典的压力特征。"
                                  f"今日：{vr.iloc[-1]:.3f}，2006年以来第 {p:.0f} 百分位。"),
                         })
    return rows


COMPONENT_SHORT = {
    "copper_gold": "copper vs gold", "xly_xlp": "consumer confidence trade",
    "us2y_direction": "2-yr yield", "iwm_spy": "small caps",
    "cyclical_defensive": "cyclical sectors", "breadth_direction": "market breadth",
    "payrolls_trend": "payrolls", "indpro_trend": "industrial production",
    "breakeven_10y_direction": "10-yr inflation expectations",
    "breakeven_5y5y_direction": "long-run inflation expectations",
    "energy_rs": "energy sector", "oil_trend": "oil",
    "inflation_beta_basket": "inflation-winners basket",
    "tips_nominal_momentum": "TIPS spread",
}

COMPONENT_SHORT_ZH = {
    "copper_gold": "铜对黄金", "xly_xlp": "消费信心交易",
    "us2y_direction": "2年期收益率", "iwm_spy": "小盘股",
    "cyclical_defensive": "周期性板块", "breadth_direction": "市场广度",
    "payrolls_trend": "非农就业", "indpro_trend": "工业生产",
    "breakeven_10y_direction": "10年期通胀预期",
    "breakeven_5y5y_direction": "长期通胀预期",
    "energy_rs": "能源板块", "oil_trend": "原油",
    "inflation_beta_basket": "通胀受益篮子",
    "tips_nominal_momentum": "TIPS 利差",
}


def component_chips(latest: dict) -> tuple[list[str], list[str]]:
    def label(raw: str) -> str:
        axis, _, comp = raw.partition("_")
        en_prefix = "growth" if axis == "growth" else "inflation"
        zh_prefix = "增长" if axis == "growth" else "通胀"
        return T(f"{en_prefix} · {COMPONENT_SHORT.get(comp, comp)}",
                 f"{zh_prefix} · {COMPONENT_SHORT_ZH.get(comp, comp)}")
    return ([label(c) for c in latest.get("confirming", [])],
            [label(c) for c in latest.get("contradicting", [])])


def flip_plain_text(latest: dict) -> str:
    from engine.playbook import COMPONENT_PLAIN
    fc = latest.get("flip_condition") or {}
    if not fc.get("component"):
        return T("No single indicator is close to flipping — the regime call isn't "
                 "hanging on one thread right now.",
                 "没有单一指标接近翻转 — 当前的周期判断目前并非系于一线。")
    plain = COMPONENT_PLAIN.get(fc["component"], fc["component"])
    return T(f"Watch {plain} — of everything supporting the current call, it's the one "
             f"closest to flipping sides. If it fades, the {fc['axis']} dial (and "
             f"possibly the regime) goes with it.",
             f"关注 {plain} — 在支撑当前判断的所有因素中，它最接近翻转。"
             f"若其转弱，{fc['axis']} 刻度（乃至周期）也会随之改变。")


INTERNALS_META = {
    "xly_xlp": (T("Shoppers: wants vs needs", "购物者：想要 vs 必需"), False,
                T("Consumer-discretionary stocks vs consumer-staples stocks. Rising = people are "
                  "buying TVs and vacations, not just groceries — confidence. Falling = belt-tightening.",
                  "可选消费股 vs 必需消费股。上升 = 人们在买电视和度假，不只是买杂货 — 信心。下降 = 勒紧裤带。")),
    "xlk_xlu": (T("Tech vs utilities", "科技 vs 公用事业"), False,
                T("The market's boldest sector vs its sleepiest. Rising = growth appetite; "
                  "falling = safety-seeking.",
                  "市场最大胆的板块 vs 最沉闷的板块。上升 = 增长偏好；下降 = 寻求安全。")),
    "hyg_lqd": (T("Junk bonds vs quality bonds", "垃圾债 vs 优质债"), False,
                T("Risky-company bonds vs blue-chip bonds. Rising = credit investors relaxed; "
                  "falling = they're getting picky — often an early warning.",
                  "高风险公司债 vs 蓝筹债。上升 = 信用投资者放松；下降 = 他们开始挑剔 — 往往是早期预警。")),
    "sphb_splv": (T("Daring vs defensive stocks", "进取股 vs 防御股"), False,
                  T("The most volatile S&P stocks vs the calmest. The purest read on whether "
                    "fund managers are playing offense or defense.",
                    "标普中波动最大的股票 vs 最平稳的股票。最纯粹地反映基金经理在打进攻还是防守。")),
    "vix_ratio": (T("Panic gauge (now vs later)", "恐慌指标（现在 vs 之后）"), True,
                  T("Near-term fear vs 3-month fear. Rising toward 1.0 = stress building right now; "
                    "comfortably below 0.9 = calm.",
                    "近期恐慌 vs 3个月恐慌。升向1.0 = 压力正在累积；稳稳低于0.9 = 平静。")),
    "copper_gold": (T("Copper vs gold", "铜 vs 黄金"), False,
                    T("The economist's metal vs the doomsday metal. Rising = bets on real economic "
                      "activity; falling = safety-seeking. Historically leads bond yields.",
                      "经济学家的金属 vs 末日金属。上升 = 押注真实经济活动；下降 = 寻求安全。历史上领先债券收益率。")),
}


def internals_rows(latest: dict) -> list[dict]:
    out = []
    for key, v in latest.get("pair_ratios", {}).items():
        meta = INTERNALS_META.get(key)
        if not meta:
            continue
        label, invert, tip = meta
        chg = v["chg_20d_pct"]
        good = (chg < 0) if invert else (chg > 0)
        verdict = {
            ("xly_xlp", True): T("consumers confident", "消费者有信心"),
            ("xly_xlp", False): T("consumers cautious", "消费者谨慎"),
            ("xlk_xlu", True): T("growth appetite", "增长偏好"),
            ("xlk_xlu", False): T("safety-seeking", "寻求安全"),
            ("hyg_lqd", True): T("credit relaxed", "信用放松"),
            ("hyg_lqd", False): T("credit getting picky", "信用趋于挑剔"),
            ("sphb_splv", True): T("playing offense", "打进攻"),
            ("sphb_splv", False): T("playing defense", "打防守"),
            ("vix_ratio", True): T("calm", "平静"),
            ("vix_ratio", False): T("near-term stress building", "近期压力累积"),
            ("copper_gold", True): T("growth optimism", "增长乐观"),
            ("copper_gold", False): T("defensive bid", "防御性买盘"),
        }.get((key, good), "")
        out.append({"label": label, "tip": tip, "chg": chg, "good": good,
                    "verdict": verdict})
    return out


def _chg20_pct(f: pd.DataFrame, col: str) -> float | None:
    """20-trading-day percent change of a ratio/level, or None if too short."""
    if col not in f.columns:
        return None
    s = f[col].dropna()
    if len(s) < 21:
        return None
    return float(s.iloc[-1] / s.iloc[-21] - 1) * 100


def size_style_rows(f: pd.DataFrame) -> list[dict]:
    """US equity SIZE & STYLE tape. Size ratios (small/mid vs large) carry a
    clean risk-on direction → coloured pos/neg. Growth-vs-value is regime-
    dependent (no inherently 'good' side) → neutral tone, verdict carries the
    read. Mirrors the 20-day-direction logic of the internals panel."""
    specs = [
        ("iwm_spy", T("Small caps vs large", "小盘对大盘"),
         T("Russell 2000 vs S&P 500 (IWM/SPY)", "罗素2000 对 标普500 (IWM/SPY)"), "size",
         T("small caps leading — broadening, risk-on", "小盘领先 — 扩散、风险偏好"),
         T("large-cap-led — narrowing participation", "大盘主导 — 参与度收窄")),
        ("mid_spy", T("Mid caps vs large", "中盘对大盘"),
         T("S&P MidCap 400 vs S&P 500 (IJH/SPY)", "标普中盘400 对 标普500 (IJH/SPY)"), "size",
         T("mid caps leading — broadening", "中盘领先 — 扩散"),
         T("mega-cap-led — narrowing", "超大盘主导 — 收窄")),
        ("growth_value", T("Growth vs value", "成长对价值"),
         T("Russell 1000 Growth vs Value (IWF/IWD). Style rotation: growth tends "
           "to lead in disinflation/slowdowns, value in reflation.",
           "罗素1000 成长 对 价值 (IWF/IWD)。风格轮动：成长在去通胀/放缓中领先，价值在再通胀中领先。"), "style",
         T("growth leadership", "成长领先"),
         T("value leadership", "价值领先")),
    ]
    rows: list[dict] = []
    for key, label, tip, kind, up_v, dn_v in specs:
        chg = _chg20_pct(f, key)
        if chg is None:
            continue
        up = chg >= 0
        tone = "muted" if kind == "style" else ("pos" if up else "neg")
        rows.append({"label": label, "tip": tip, "chg": chg, "tone": tone,
                     "verdict": up_v if up else dn_v})
    return rows


def breadth_divergence(f: pd.DataFrame) -> dict | None:
    """Small-cap (S&P 600) vs large-cap (S&P 500) participation: the gap between
    % of each universe above its 50-day line. Large strong while small lags =
    a narrow, fragile, mega-cap-led tape; small leading = healthy broadening."""
    def last(col):
        if col not in f.columns:
            return None
        s = f[col].dropna()
        return float(s.iloc[-1]) if len(s) else None
    lc, sc = last("pct_above_50"), last("sc_pct_above_50")
    if lc is None or sc is None:
        return None
    gap = sc - lc
    if gap >= 5:
        verdict = T("small caps participating MORE than large caps — healthy, broad-based tape",
                    "小盘参与度高于大盘 — 健康、广泛的盘面")
    elif gap <= -5:
        verdict = T("small caps lagging large caps — narrow, mega-cap-led advance (more fragile)",
                    "小盘落后于大盘 — 狭窄、由超大盘主导的上涨（更脆弱）")
    else:
        verdict = T("small- and large-cap participation roughly in line",
                    "小盘与大盘参与度大致一致")
    return {"sc": sc, "lc": lc, "gap": gap, "verdict": verdict}


# heat-bar fill uses theme-aware CSS variables (legible in both modes)
HEAT_COLORS = {"70+": "var(--orange)", "55-69": "var(--up)",
               "40-54": "var(--muted)", "0-39": "var(--info)"}

# Plain-English reading of each heat band for the hover tooltip — kept jargon-free
# on purpose (the technical band-record table lives in the column header tooltip).
HEAT_READ = {
    "70+": ("running very hot — and a near-fully-confirmed sector is usually a late "
            "one. Better to hold with tight stops or trim than to start a position here.",
            "非常热 — 几乎全部确认的板块通常已经偏晚。与其此时建仓，不如持有并收紧止损或减仓。"),
    "55-69": ("a healthy, confirmed uptrend. Fine to hold; buying it right here hasn't "
              "paid off historically — prefer a pullback that holds the trend.",
              "健康、已确认的上涨趋势。可以持有；历史上此时直接买入并不划算 — 优先选择守住趋势的回调。"),
    "40-54": ("a mixed picture, with no clear edge in either direction.",
              "图景混杂，任一方向都没有明显优势。"),
    "0-39": ("beaten down and quiet. It tends to drift back up eventually, but the "
             "timing is unreliable — wait for the buy trigger to confirm.",
             "已被打压、走势清淡。最终往往会回升，但择时不可靠 — 等待买入触发信号确认。"),
}


def _compact_season(line: str | None) -> tuple[str, str]:
    """'Jun: -0.4% avg, up 46% of years (n=28)' -> ('-0.4% (46%)', full)"""
    if not line:
        return "—", T("Not enough history for a seasonal read.", "历史数据不足，无法做季节性判断。")
    try:
        avg = line.split(":")[1].split("avg")[0].strip()
        hit = line.split("up ")[1].split("%")[0]
        return f"{avg} ({hit}%)", line
    except (IndexError, ValueError):
        return line, line


def _b(en: str, zh: str) -> str:
    """Inline bilingual span (raw markup) for use inside composed tooltip HTML."""
    return f'<span class="l-en">{en}</span><span class="l-zh">{zh}</span>'


def _season_tooltip(seas: dict | None, month: int | None):
    """Rich seasonality hover: a 12-month bar chart of average returns + a two-column
    table (avg / % positive / years), with the current calendar month highlighted.
    Colours use the theme's --up/--down vars so they follow the Asia red/green swap.
    Falls back to a short note when there isn't enough history."""
    from markupsafe import Markup
    if not seas:
        return T("Not enough history for a seasonal read.", "历史数据不足，无法做季节性判断。")
    # latest.json is a JSON round-trip, which stringifies the int month keys
    seas = {int(k): v for k, v in seas.items()}
    month = int(month) if month is not None else None
    months = range(1, 13)
    vmax = max((abs(seas[m]["avg_pct"]) for m in months if m in seas), default=1.0) or 1.0

    # --- bar chart: positive bars up (green), negative down (red) -------------
    W, H = 320, 86
    padL, padR, base_y, span, label_y = 8, 8, 40, 26, 80
    slot = (W - padL - padR) / 12
    bw = slot * 0.56
    svg = [f'<line x1="{padL}" y1="{base_y}" x2="{W - padR}" y2="{base_y}" '
           f'style="stroke:var(--line);stroke-width:1"/>']
    for i, m in enumerate(months):
        cx = padL + slot * (i + 0.5)
        cur = (m == month)
        if cur:                                    # faint full-height column tint
            svg.append(f'<rect x="{cx - slot / 2:.1f}" y="6" width="{slot:.1f}" '
                       f'height="{base_y + span:.1f}" rx="2" '
                       f'style="fill:var(--text);opacity:.07"/>')
        s = seas.get(m)
        if s:
            up = s["avg_pct"] >= 0
            h = max(abs(s["avg_pct"]) / vmax * span, 1.0)
            y = base_y - h if up else base_y
            col = "var(--up)" if up else "var(--down)"
            svg.append(f'<rect x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                       f'height="{h:.1f}" rx="1.5" '
                       f'style="fill:{col};opacity:{1 if cur else .55}"/>')
        svg.append(                                    # numeric labels read in both languages
            f'<text x="{cx:.1f}" y="{label_y}" text-anchor="middle" '
            f'style="font-size:9px;fill:{"var(--text)" if cur else "var(--muted)"};'
            f'font-weight:{700 if cur else 400}">{m}</text>')
    chart = (f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;'
             f'margin:4px 0 6px;overflow:visible">{"".join(svg)}</svg>')

    # --- two stacked 6-month tables, current month row highlighted ------------
    def _col(rng) -> str:
        rows = ['<colgroup><col style="width:28%"><col style="width:28%">'
                '<col style="width:23%"><col style="width:21%"></colgroup>',
                f'<tr><th style="text-align:left">{_b("Month", "月份")}</th>'
                f'<th>{_b("Avg", "均值")}</th><th>{_b("Up", "收涨")}</th>'
                f'<th>{_b("Yrs", "年数")}</th></tr>']
        for m in rng:
            s, cur = seas.get(m), (m == month)
            tr = ' style="background:var(--panel2);font-weight:700"' if cur else ''
            name = _b(calendar.month_abbr[m], f"{m}月")
            if s:
                cls = "pos" if s["avg_pct"] >= 0 else "neg"
                rows.append(
                    f'<tr{tr}><td style="text-align:left">{name}</td>'
                    f'<td class="{cls}">{s["avg_pct"]:+.1f}%</td>'
                    f'<td>{s["hit_pct"]:.0f}%</td>'
                    f'<td class="muted">{s["n"]}</td></tr>')
            else:
                rows.append(f'<tr{tr}><td style="text-align:left">{name}</td>'
                            f'<td class="muted">—</td><td class="muted">—</td>'
                            f'<td class="muted">—</td></tr>')
        return ('<table style="margin:0;flex:1 1 0;min-width:0">'
                + "".join(rows) + "</table>")

    tables = (f'<div style="display:flex;gap:10px">'
              f'{_col(range(1, 7))}{_col(range(7, 13))}</div>')
    title = ('<b style="font-size:12px;display:block;margin-bottom:1px">'
             + _b("Seasonality — average return by month",
                  "季节性 — 各月平均回报") + '</b>')
    foot = ('<div class="muted" style="font-size:10.5px;margin-top:6px;line-height:1.4">'
            + _b("Each month’s average return across this instrument’s full history, and "
                 "how often it closed up. Weak evidence — background colour only, never a "
                 "signal on its own (and left out of the heat score).",
                 "该标的全部历史中每个月的平均回报及收涨频率。属于弱证据 — 仅作背景参考，"
                 "绝不单独作为信号（且已排除在热度分数之外）。") + '</div>')
    return Markup(f"{title}{chart}{tables}{foot}")


def action_board(sector_timing: dict, notable: list[dict]) -> dict:
    """Bucket sector + standout-stock cycle signals into an at-a-glance
    'what to act on now' board for the front page."""
    from engine.playbook import SECTOR_NAMES
    buy_now, buy_soon, take_profits, hold, avoid = [], [], [], [], []
    for fund, tm in sector_timing.items():
        e = tm.get("entry") or {}
        item = {"ticker": fund, "name": SECTOR_NAMES.get(fund, fund),
                "label": tm["label"], "tag": e.get("tag", ""),
                "text": e.get("text", ""), "days": e.get("days_hi"),
                "age_short": tm.get("age_short"), "age_short_zh": tm.get("age_short_zh"),
                "eq_badge": tm.get("eq_badge"), "eq_dir": tm.get("eq_dir"),
                "eq_tip": tm.get("eq_tip"), "style": tm.get("state_style")}
        u = e.get("urgency")
        if u == "now":
            buy_now.append(item)
        elif u in ("imminent", "soon"):
            buy_soon.append(item)
        elif u in ("caution", "exit"):
            take_profits.append(item)
        elif u == "hold":
            hold.append(item)
        else:
            avoid.append(item)
    buy_soon.sort(key=lambda x: (x["days"] if x["days"] is not None else 99))
    # de-dup notable stocks, cap, sort buys-first then by days
    seen, notable_clean = set(), []
    order = {"now": 0, "imminent": 1, "exit": 2}
    for n in sorted(notable, key=lambda x: (order.get(x["urgency"], 9),
                                            x["days"] if x.get("days") is not None else 99)):
        if n["ticker"] in seen:
            continue
        seen.add(n["ticker"])
        notable_clean.append(n)
    return {"buy_now": buy_now, "buy_soon": buy_soon, "take_profits": take_profits,
            "hold": hold, "avoid": avoid, "notable": notable_clean[:10]}


def sector_rows(playbook: dict | None, timing: dict | None = None) -> list[dict]:
    if not playbook or not playbook.get("stages"):
        return []
    timing = timing or {}
    rows = sorted(playbook["stages"], key=lambda r: -r["heat"])
    for r in rows:
        tm = timing.get(r["ticker"])
        if tm:
            r["timing_state"] = tm["state"]
            r["timing_label"] = tm.get("label", tm["state"])
            r["timing_style"] = tm["state_style"]
            r["timing_note"] = T(
                f"day {tm['dc_day']} of its cycle; "
                f"{tm['buy_zone']}/{tm['n_holdings']} top holdings in a buy setup",
                f"周期第 {tm['dc_day']} 天；"
                f"{tm['buy_zone']}/{tm['n_holdings']} 个重仓处于买入预备")
        else:
            r["timing_state"] = None
        r["heat_color"] = HEAT_COLORS.get(r["heat_band"], "var(--muted)")
        parts = r.get("heat_parts", {})
        cal = r.get("heat_cal")
        read_en, read_zh = HEAT_READ.get(r["heat_band"],
                                         (r["heat_note"], r.get("heat_note_zh", r["heat_note"])))
        cal_txt_en = (f" History check: in the past, sectors scoring in this {r['heat_band']} "
                      f"range went on to beat the market {cal['hit_pct']}% of the time over "
                      f"the next 3 months (average {cal['avg_excess_pct']:+}%, across "
                      f"{cal['n']} cases)." if cal else "")
        cal_txt_zh = (f" 历史回测：过去得分落在 {r['heat_band']} 区间的板块，"
                      f"未来 3 个月跑赢市场的概率为 {cal['hit_pct']}%"
                      f"（平均 {cal['avg_excess_pct']:+}%，共 {cal['n']} 个样本）。" if cal else "")
        r["heat_tip"] = T(
            f"Heat {r['heat']} out of 100 — how strong and confirmed this sector looks right "
            f"now (0 = ice-cold, 100 = red-hot). It adds up four things: how well it fits the "
            f"current market backdrop ({parts.get('regime')}), the health of its trend "
            f"({parts.get('tape')}), its chart strength ({parts.get('technicals')}), and a "
            f"crowding penalty when it's overstretched ({parts.get('crowding')}). "
            f"Reading — {r['heat_label']}: {read_en}{cal_txt_en}",
            f"热度 {r['heat']}/100 — 衡量该板块此刻有多强、有多被确认（0 = 冰冷，100 = 火热）。"
            f"它由四部分相加：与当前市场环境的契合度（{parts.get('regime')}）、"
            f"趋势的健康度（{parts.get('tape')}）、图表强度（{parts.get('technicals')}）、"
            f"以及过度拉伸时的拥挤度扣分（{parts.get('crowding')}）。"
            f"解读 — {TR(r['heat_label'])}：{read_zh}{cal_txt_zh}")
        tech_bits = [f"RSI {r['tech_rsi14']:.0f}" if r.get("tech_rsi14") is not None else "RSI —",
                     ("✓" if r.get("tech_above200") else "✗") + "200d",
                     ("✓" if r.get("tech_above50") else "✗") + "50d"]
        r["tech_str"] = " · ".join(tech_bits)
        r["tech_ok"] = bool(r.get("tech_above200")) and bool(r.get("tech_above50"))
        r["season_str"], _ = _compact_season(r.get("season_this"))
        r["season_tip"] = _season_tooltip(r.get("season_all"), r.get("season_month"))
        if r.get("trigger_gap_pct") is not None:
            r["trigger_str"] = f"+{r['trigger_gap_pct']}%"
            if r.get("trigger_progress_pct") is not None:
                r["trigger_str"] += f" ({r['trigger_progress_pct']:.0f}% there)"
        else:
            r["trigger_str"] = "—"
    return rows


def holdings_rows() -> list[dict]:
    cfg = config.load()["holdings"]
    out = []
    for fund in cfg["watchlist"]:
        ch = active_changes(fund)
        if ch is None or ch.empty:
            continue
        big = ch[ch["active_chg_pct"].abs() >= cfg["active_change_alert_pct"] / 2]
        for pos, row in big.dropna(subset=["active_chg_pct"]).iterrows():
            out.append({"fund": fund, "position": pos, "pct": row["active_chg_pct"],
                        "window": f"{row['window_start']}..{row['window_end']}"})
    return sorted(out, key=lambda r: -abs(r["pct"]))[:20]


def accumulation_rows() -> list[dict]:
    """Decomposed sector-ETF accumulation signals for the dashboard panel: each
    holding's weight change split into a price part and a residual ('active'), with
    the stock's cycle state attached. See engine/holdings_signals.py."""
    from engine.holdings_signals import all_accumulation_signals
    from engine.playbook import SECTOR_NAMES
    n = config.load()["holdings_signals"].get("panel_top_n", 12)
    rows = []
    for s in all_accumulation_signals()[:n]:
        rows.append({
            "fund": s["fund"], "sector": SECTOR_NAMES.get(s["fund"], s["fund"]),
            "ticker": s["ticker"], "name": s["name"],
            "raw_change": s["raw_change"], "active_change": s["active_change"],
            "active_pct": s["active_pct"],
            "flow_str": _fmt_money_mn(s["est_flow_mn"]) if s.get("est_flow_mn") is not None else "—",
            "direction": s["direction"], "confirmed": s["confirmed"],
            "ladder": s["ladder"], "window": f"{s['t0']}..{s['t1']}"})
    return rows


def _fmt_money_mn(v: float) -> str:
    """$ millions -> human string: 1234 -> +$1.2B, -87 -> -$87M."""
    if pd.isna(v):
        return "—"
    sign = "+" if v >= 0 else "−"
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    return f"{sign}${a:.0f}M"


def flows_html_table() -> str | None:
    from engine.playbook import SECTOR_NAMES
    ft = flows_table()
    if ft is None or ft.dropna(how="all").empty:
        return None
    recent = ft.dropna(how="all").tail(10)
    recent.columns = [SECTOR_NAMES.get(c.replace("_flow_mn", ""),
                                       c.replace("_flow_mn", ""))
                      for c in recent.columns]
    rows = ["<table><tr><th class='l'>date</th>"
            + "".join(f"<th>{c}</th>" for c in recent.columns) + "</tr>"]
    for d, r in recent.iterrows():
        cells = "".join(
            f"<td class='{'pos' if v >= 0 else 'neg'}'>{_fmt_money_mn(v)}</td>"
            if pd.notna(v) else "<td>—</td>" for v in r)
        rows.append(f"<tr><td class='l muted'>{d.date()}</td>{cells}</tr>")
    rows.append("</table>")
    return "".join(rows)


STATE_STYLES = {
    "FRESH BUY": ("#1d4a2c", "#7fe0a0"), "TURN SIGNALED": ("#1d3a4a", "#8fd0f0"),
    "RALLY ON": ("#1d3326", "#6fce8f"), "BOTTOM WATCH": ("#2b3340", "#9fc0e8"),
    "TOP WATCH": ("#38301a", "#d8b75a"), "ROLLING OVER": ("#4a2c1a", "#e0a070"),
    "DECLINE": ("#3a2020", "#e08080"),
    "COUNTERTREND BOUNCE": ("#3a2e1a", "#e0b070"),
}
BUY_ZONE_STATES = ("FRESH BUY", "TURN SIGNALED")


def build_etf_page(env: Environment, site: Path, generated: str) -> None:
    """Render etfs.html — the broad-universe ETF flow radar (share-based
    flow-normalized active decisions). See engine/holdings_signals.top_etf_accumulation."""
    from engine.holdings_signals import top_etf_accumulation
    try:
        rows = top_etf_accumulation()
    except Exception as e:  # noqa: BLE001
        log.error("etf signals failed: %s", e)
        rows = []
    html = env.get_template("etfs.html.j2").render(etf_rows=rows, generated_utc=generated)
    (site / "etfs.html").write_text(html)
    log.info("wrote etfs.html (%d signal rows)", len(rows))


def build_factors_page(env: Environment, site: Path, generated: str) -> dict | None:
    """Render factors.html — the cross-sectional equity factor rankings (SEC
    EDGAR fundamentals x prices). Fundamentals fetch is cached weekly; ranks
    recompute daily. Additive — any failure logs and skips the page entirely.
    See research/QUANT_FACTOR_EXPANSION.md."""
    if not config.load().get("edgar", {}).get("enabled"):
        return None
    from collectors.edgar import fetch_panel
    from engine.equity_factors import compute_factors
    try:
        fetch_panel()                              # point-in-time panel (weekly-cached); also writes the back-compat latest-FY fundamentals.parquet slice
        try:
            from collectors.finra import fetch_short_interest
            fetch_short_interest()                 # Phase 3: bi-monthly short interest (cached)
        except Exception as e:  # noqa: BLE001 — short interest is an optional factor leg
            log.warning("finra short interest failed: %s", e)
        try:
            from collectors.sec_insider import fetch_insider
            fetch_insider()                        # Phase 4: Form-4 insider buying (cached)
        except Exception as e:  # noqa: BLE001 — insider panel is optional
            log.warning("sec insider failed: %s", e)
        fac = compute_factors()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("factor engine failed: %s", e)
        return None
    if not fac:
        return None
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "factors.json").write_text(json.dumps(fac, separators=(",", ":"), default=str))
    html = env.get_template("factors.html.j2").render(fac=fac, generated_utc=generated)
    (site / "factors.html").write_text(html)
    log.info("wrote factors.html (%d names, FY%s)", fac.get("n"), fac.get("fy"))
    return fac


def build_sector_pages(env: Environment, site: Path, generated: str) -> dict:
    """Render sectors/<FUND>.html drill-downs; return per-fund timing summary
    for the heat board."""
    import json as _json

    from collectors.sector_holdings import latest_fundamentals, latest_top10
    from engine.cycles import LADDER, STATE_DISPLAY, analyze
    from engine.holdings_signals import accumulation_signals
    from engine.playbook import SECTOR_NAMES
    from scripts.build_stock_library import current_liquidity

    cal_path = config.data_dir() / "regime" / "ladder_calibration.json"
    calibration = _json.loads(cal_path.read_text()) if cal_path.exists() else None
    # live US net-liquidity regime — the orthogonal macro conviction modifier
    # threaded into every per-sector / per-stock ladder read (None => omitted).
    liq = current_liquidity()
    tpl = env.get_template("sector.html.j2")
    outdir = site / "sectors"
    outdir.mkdir(parents=True, exist_ok=True)

    import json as _json2
    summaries: dict[str, dict] = {}
    notable: list[dict] = []
    for fund in config.load()["sponsors"]["sector_funds"]:
        etf = store.read("yahoo", fund)
        if etf is None:
            continue
        res = analyze(etf["close"], liquidity=liq)
        if not res.get("ladder"):
            continue
        holdings = []
        t10 = latest_top10(fund)
        if t10 is not None:
            for _, r in t10.iterrows():
                tick = str(r["ticker"]).replace(".", "-")
                df = store.read("stocks", tick)
                if df is None or len(df) < 300:
                    continue
                h = analyze(df["close"], df.get("high"), liquidity=liq)
                if not h.get("ladder"):
                    continue
                h["mtf_json"] = _json2.dumps(h.get("mtf", {}))
                holdings.append({"ticker": tick,
                                 "name": str(r.get("name", "")).title(),
                                 "weight_pct": r["weight_pct"], **h,
                                 "fundamentals": latest_fundamentals(tick)})
                # collect decisive individual-stock signals for the front page
                urg = h["ladder"]["entry"]["urgency"]
                if urg in ("now", "imminent", "exit"):
                    notable.append({"ticker": tick, "name": str(r.get("name", "")).title(),
                                    "sector": SECTOR_NAMES.get(fund, fund),
                                    "label": h["ladder"]["label"],
                                    "tag": h["ladder"]["entry"]["tag"], "urgency": urg,
                                    "days": h["ladder"]["entry"].get("days_hi"),
                                    "age_short": h["ladder"].get("age_short"),
                                    "age_short_zh": h["ladder"].get("age_short_zh"),
                                    "eq_badge": h["ladder"].get("eq_badge"),
                                    "eq_dir": h["ladder"].get("eq_dir"),
                                    "eq_tip": h["ladder"].get("eq_tip")})
        buy_zone = sum(1 for h in holdings if h["ladder"]["state"] in BUY_ZONE_STATES)
        s = {"fund": fund, "name": SECTOR_NAMES.get(fund, fund),
             "mtf_json": _json2.dumps(res.get("mtf", {})), **res,
             "holdings": holdings, "accumulation": accumulation_signals(fund)}
        html = tpl.render(s=s, state_styles=STATE_STYLES, calibration=calibration,
                          ladder_order=LADDER, state_display=STATE_DISPLAY,
                          generated_utc=generated)
        (outdir / f"{fund}.html").write_text(html)
        summaries[fund] = {"state": res["ladder"]["state"],
                           "label": res["ladder"]["label"],
                           "action": res["ladder"]["action"],
                           "entry": res["ladder"]["entry"],
                           "state_style": STATE_STYLES.get(res["ladder"]["state"]),
                           "dc_day": res["cycle"]["dc_day"],
                           "age_short": res["ladder"].get("age_short"),
                           "age_short_zh": res["ladder"].get("age_short_zh"),
                           "age_days": res["ladder"].get("age_days"),
                           "eq_badge": res["ladder"].get("eq_badge"),
                           "eq_dir": res["ladder"].get("eq_dir"),
                           "eq_tip": res["ladder"].get("eq_tip"),
                           "buy_zone": buy_zone, "n_holdings": len(holdings)}
    log.info("wrote %d sector drill-down pages", len(summaries))
    return summaries, notable


def health_rows() -> list[dict]:
    sources = store.read_status().get("sources", {})
    return [{"name": k, "status": v.get("status", "?"), "rows": v.get("rows", 0),
             "last_date": v.get("last_date"), "error": (v.get("error") or "")[:90]}
            for k, v in sorted(sources.items())]


def regime_timeline(hist: pd.DataFrame) -> dict:
    """Compact columnar JSON of the classified regime history for the client-side
    "Time Machine" scrubber (timemachine.js). Only days with a settled quad label
    (≈1999→today) are shipped; everything is parallel arrays keyed by day index so
    the browser can rewind the whole regime core to any past date. The six warning
    flags are packed into one bitmask per day (decoded against `flag_order`)."""
    h = hist[hist["quad"].notna()].copy()

    def r3(col: str) -> list:
        return [None if pd.isna(v) else round(float(v), 3) for v in h[col]]

    flag_cols = ["flag_breadth_price", "flag_credit_equity", "flag_ratio_inflection",
                 "flag_inflation_basket", "flag_confidence_decay", "flag_gex"]
    masks = sum((h[c].astype(bool).astype(int) * (1 << i)) for i, c in enumerate(flag_cols))

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in h.index],
        "quad":  h["quad"].fillna("").tolist(),
        "g":     r3("growth_score"),
        "i":     r3("inflation_score"),
        "conf":  r3("regime_confidence"),
        "liq":   h["liquidity"].fillna("unknown").tolist(),
        "cyc":   h["cycle"].fillna("unknown").tolist(),
        "trans": h["transition_state"].fillna("STABLE").tolist(),
        "rec":   [int(bool(v)) for v in h["recession"]],
        "shock": [int(bool(v)) for v in h["inflation_shock"]],
        "flags": [int(v) for v in masks],
        "flag_order": ["breadth_price", "credit_equity", "ratio_inflection",
                       "inflation_basket", "confidence_decay", "gex"],
    }


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    with open(config.data_dir() / "regime" / "latest.json") as fh:
        latest = json.load(fh)
    hist = pd.read_parquet(config.data_dir() / "regime" / "regime_history.parquet")
    hist.index = pd.to_datetime(hist.index)
    # client-side "Time Machine": ship the classified regime history as compact JSON
    (site / "regime_timeline.json").write_text(
        json.dumps(regime_timeline(hist), separators=(",", ":")))
    f = build_features()

    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    from engine import i18n
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)  # bilingual helpers for templates
    confirming, contradicting = component_chips(latest)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    import calendar
    sector_timing, notable = {}, []
    try:
        sector_timing, notable = build_sector_pages(env, site, generated)
    except Exception as e:  # noqa: BLE001 — drill-downs are additive, never fatal
        log.error("sector pages failed: %s", e)
    try:
        build_etf_page(env, site, generated)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("etf page failed: %s", e)
    factor_leadership = None
    try:
        _fac = build_factors_page(env, site, generated)
        factor_leadership = (_fac or {}).get("leadership")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("factors page failed: %s", e)
    # copy shared static assets (theme + visual widgets) into the site
    for asset in ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
                  "stockdata.js", "watchlist.js", "auth.js", "tablesort.js", "charts.js"):
        src = config.ROOT / "templates" / asset
        if src.exists():
            (site / asset).write_text(src.read_text())
    from engine.alerts import alert_views
    html = env.get_template("dashboard.html.j2").render(
        latest=latest,
        alerts=alert_views(latest.get("alerts", [])),
        pb=latest.get("playbook"),
        month_name=calendar.month_name[pd.Timestamp(latest["date"]).month],
        commodities=(latest.get("playbook") or {}).get("commodities", []),
        sector_timing=sector_timing,
        action_board=action_board(sector_timing, notable),
        components_confirming=confirming,
        components_contradicting=contradicting,
        flip_plain=flip_plain_text(latest),
        internals=internals_rows(latest),
        size_style=size_style_rows(f),
        breadth_div=breadth_divergence(f),
        sector_rows=sector_rows(latest.get("playbook"), sector_timing),
        generated_utc=generated,
        chart_liquidity=chart_liquidity(f),
        chart_credit_breadth=chart_credit_breadth(f),
        positioning=positioning_rows(f),
        holdings_changes=holdings_rows(),
        holdings_threshold=config.load()["holdings"]["active_change_alert_pct"],
        accumulation=accumulation_rows(),
        flows_html=flows_html_table(),
        health=health_rows(),
        factor_leadership=factor_leadership,
    )
    # Write the macro dashboard straight to macro.html. index.html is owned
    # solely by build_vector.build_landing() (the landing hub) — keeping the raw
    # dashboard out of index.html is what stops Home (-> index.html) from
    # regressing to the dashboard when build_vector doesn't run after this.
    out = site / "macro.html"
    out.write_text(html)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)

    # --- history page: the longer-window charts + lifespan base rates ----------
    from engine.playbook import QUAD_SHORT, transition_stats
    trans = transition_stats(hist["quad"])
    lifespan_rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        nxt_str = ", ".join(f"{QUAD_SHORT.get(k, k)} {v:.0%}" for k, v in
                            sorted(nxt.items(), key=lambda kv: -kv[1])[:2]) or "—"
        lifespan_rows.append({"name": QUAD_SHORT[q],
                              "n": trans["n_by_quad"].get(q, "—"),
                              "median": trans["median_days"].get(q, "—"),
                              "next": nxt_str})
    hist_html = env.get_template("history.html.j2").render(
        latest=latest,
        generated_utc=generated,
        chart_regime=chart_regime(f, hist, days=1095),
        chart_axes=chart_axes(hist, days=1095),
        lifespan_rows=lifespan_rows,
    )
    out2 = site / "history.html"
    out2.write_text(hist_html)
    log.info("wrote %s (%.0f KB)", out2, out2.stat().st_size / 1024)

    # stock search: analyzer page + nightly library
    if config.load().get("stock_search", {}).get("enabled"):
        import json as _json

        from engine.cycles import STATE_DISPLAY
        sd_json = _json.dumps(STATE_DISPLAY)
        (site / "stock.html").write_text(
            env.get_template("stock.html.j2").render(
                state_styles=STATE_STYLES, generated_utc=generated,
                state_display_json=sd_json))
        from scripts.build_stock_library import main as build_library
        build_library()

        # holdings watchlist: a pure client-state page over the same library
        # (selection persists in the browser; signals re-resolve from index.json
        # each load). Optional Supabase cloud sync is config-gated; blank => local-only.
        wl = config.load().get("watchlist", {})
        if wl.get("enabled", True):
            sup = wl.get("supabase") or {}
            sup_cfg = ({"url": sup["url"], "anonKey": sup["anon_key"]}
                       if sup.get("url") and sup.get("anon_key") else None)
            (site / "watchlist.html").write_text(
                env.get_template("watchlist.html.j2").render(
                    generated_utc=generated, state_display_json=sd_json,
                    supabase_cfg_json=_json.dumps(sup_cfg),
                    starters_json=_json.dumps(wl.get("suggested", []))))
            log.info("wrote %s", site / "watchlist.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
