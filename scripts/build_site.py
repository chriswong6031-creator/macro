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


# ----- market snapshot tiles + VIX monitor (display surfacing; reuse the frame) -----
# The 8 headline instruments are already in the feature frame; this surfaces them as
# at-a-glance tiles, and gives VIX a proper monitor (30-day path + OUR term-structure
# / percentile read — richer than the conventional 15/20/30 bands, which we keep only
# as a familiar label). No new data collection.
_TILE_SPEC = (
    ("SPY",   ("S&P 500 · SPY",    "标普500 · SPY"),  ("Indices", "指数"),     2),
    ("QQQ",   ("Nasdaq 100 · QQQ", "纳指100 · QQQ"),   ("Indices", "指数"),     2),
    ("vix",   ("VIX",              "VIX"),             ("Volatility", "波动率"), 2),
    ("us10y", ("10Y yield",        "10年期收益率"),     ("Rates", "利率"),       2),
    ("us30y", ("30Y yield",        "30年期收益率"),     ("Rates", "利率"),       2),
    ("us5y",  ("5Y yield",         "5年期收益率"),      ("Rates", "利率"),       2),
    ("dxy",   ("US dollar · DXY",  "美元 · DXY"),       ("FX", "外汇"),          2),
    ("oil",   ("Crude oil · WTI",  "原油 · WTI"),       ("Commodities", "商品"), 2),
)


def market_tiles(f: pd.DataFrame) -> list[dict]:
    """Level + 1-day change for the 8 headline instruments already in the frame.
    Coloured by raw sign (the price move); semantic context lives in the panels."""
    rows = []
    for col, (en, zh), (ten, tzh), dec in _TILE_SPEC:
        if col not in f.columns:
            continue
        s = f[col].dropna()
        if len(s) < 2:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        chg = last - prev
        pct = (last / prev - 1) * 100 if prev else 0.0
        is_rate = col.startswith("us")
        rows.append({
            "label": T(en, zh), "tag": T(ten, tzh),
            "level": (f"{last:.{dec}f}%" if is_rate else f"{last:,.{dec}f}"),
            "chg": f"{chg:+.{dec}f}", "pct": f"{pct:+.1f}%",
            "tone": "pos" if chg > 0 else "neg" if chg < 0 else "muted",
        })
    return rows


def vix_monitor(f: pd.DataFrame, days: int = 30) -> dict | None:
    """Current VIX + N-day range + our term-structure / percentile read. The level
    bands (low/normal/elevated/high) are the familiar framing; the term structure
    (vix/vix3m) and history percentile are the sharper read shown beside them."""
    if "vix" not in f.columns:
        return None
    v = f["vix"].dropna()
    if len(v) < 2:
        return None
    last, prev = float(v.iloc[-1]), float(v.iloc[-2])
    win = v.tail(days)
    if last < 15:
        regime, tone = T("low", "偏低"), "muted"
    elif last < 20:
        regime, tone = T("normal", "正常"), "muted"
    elif last < 30:
        regime, tone = T("elevated", "偏高"), "warn"
    else:
        regime, tone = T("high fear", "高度恐慌"), "neg"
    ratio, rword = None, None
    vr = f["vix_ratio"].dropna() if "vix_ratio" in f.columns else pd.Series(dtype=float)
    if len(vr):
        ratio = float(vr.iloc[-1])
        rword = T("backwardation", "倒挂") if ratio >= 1 else T("contango", "正向")
    return {"last": last, "chg": last - prev,
            "pct": (last / prev - 1) * 100 if prev else 0.0,
            "hi": float(win.max()), "lo": float(win.min()), "prev": prev, "days": days,
            "regime": regime, "tone": tone, "ratio": ratio, "rword": rword,
            "pctile": float((v <= last).mean() * 100)}


def chart_vix(f: pd.DataFrame, days: int = 90) -> str:
    """A focused VIX path with the conventional regime bands shaded behind it."""
    if "vix" not in f.columns:
        return ""
    v = f["vix"].dropna()
    if v.empty:
        return ""
    v = v.loc[v.index.max() - pd.Timedelta(days=days):]
    fig = go.Figure()
    for y0, y1, c in ((0, 15, "#4fb39a"), (15, 20, "#7aa7e0"),
                      (20, 30, "#e0a030"), (30, 90, "#e06464")):
        fig.add_hrect(y0=y0, y1=y1, fillcolor=c, opacity=0.07, line_width=0)
    fig.add_trace(go.Scatter(x=v.index, y=v, name="VIX",
                             line={"color": "#e07a9a", "width": 1.6}))
    fig.update_layout(**{**PLOT_LAYOUT, "height": 240}, showlegend=False)
    fig.update_yaxes(range=[max(0.0, float(v.min()) - 2), float(v.max()) + 3])
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


# Market-breadth scorecard across the full S&P Composite 1500, by size tier.
# The daily collector already stores advancing/declining, % above the 50- and
# 200-day lines, and 52w new highs/lows for each universe — but the page only
# ever charted % > 50d (large + small). This surfaces the rest as one legible
# scorecard. NB: % > 50d also feeds the regime model's growth axis, so this is
# the same breadth the model reads, not a new/contradicting signal.
_BREADTH_TIERS = (
    ("large", "breadth",          "S&P 500", ("Large cap", "大盘")),
    ("mid",   "midcap_breadth",   "S&P 400", ("Mid cap",   "中盘")),
    ("small", "smallcap_breadth", "S&P 600", ("Small cap", "小盘")),
)


def _wmean(tiers: list[dict], key: str) -> float | None:
    """Member-count-weighted mean of a per-tier metric, skipping missing tiers."""
    num = sum(t[key] * t["n"] for t in tiers if t[key] is not None)
    den = sum(t["n"] for t in tiers if t[key] is not None)
    return num / den if den else None


def _breadth_read(pa50: float | None, net_nh: int) -> tuple:
    """Plain-language read of composite breadth -> (label, verdict, tone)."""
    if pa50 is not None and pa50 >= 60 and net_nh >= 0:
        return (T("broad", "广泛"),
                T("The advance is well-supported across the full 1,500",
                  "上涨在整个 1500 只股票中获得良好支撑"), "pos")
    if pa50 is not None and (pa50 <= 40 or net_nh < 0):
        return (T("thin", "稀薄"),
                T("Few names hold their trend — rallies here are fragile",
                  "守住趋势的个股很少 — 此时的反弹较脆弱"), "neg")
    return (T("mixed", "参差"),
            T("No clear breadth edge either way",
              "广度上没有明显的方向性优势"), "muted")


def breadth_scorecard() -> dict | None:
    """Latest breadth read across the S&P 1500 size tiers + a weighted composite."""
    tiers, asof = [], None
    for key, ns, univ, (en, zh) in _BREADTH_TIERS:
        p = config.data_dir() / ns / "breadth.parquet"
        if not p.exists():
            continue
        try:
            row = pd.read_parquet(p).dropna(subset=["pct_above_50"]).iloc[-1]
        except Exception:  # noqa: BLE001 — additive, never fatal
            continue
        adv, dec = float(row.get("adv", 0) or 0), float(row.get("dec", 0) or 0)
        nh, nl = float(row.get("nh", 0) or 0), float(row.get("nl", 0) or 0)
        pa200 = row.get("pct_above_200")
        tiers.append({
            "key": key, "label": T(en, zh), "univ": univ,
            "n": int(row.get("n_members", 0) or 0),
            "adv": int(adv), "dec": int(dec),
            "adv_pct": (100 * adv / (adv + dec)) if (adv + dec) else None,
            "pa50": float(row["pct_above_50"]),
            "pa200": float(pa200) if pd.notna(pa200) else None,
            "nh": int(nh), "nl": int(nl), "net_nh": int(nh - nl),
        })
        asof = row.name if asof is None else max(asof, row.name)
    if not tiers:
        return None
    adv, dec = sum(t["adv"] for t in tiers), sum(t["dec"] for t in tiers)
    net_nh = sum(t["net_nh"] for t in tiers)
    pa50, pa200 = _wmean(tiers, "pa50"), _wmean(tiers, "pa200")
    label, verdict, tone = _breadth_read(pa50, net_nh)
    return {
        "asof": pd.Timestamp(asof).strftime("%Y-%m-%d") if asof is not None else None,
        "tiers": tiers,
        "comp": {"n": sum(t["n"] for t in tiers), "adv": adv, "dec": dec,
                 "adv_pct": (100 * adv / (adv + dec)) if (adv + dec) else None,
                 "pa50": pa50, "pa200": pa200, "net_nh": net_nh,
                 "label": label, "verdict": verdict, "tone": tone},
    }


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


def _mini_svg(vals, color: str = "var(--link)", w: int = 260, h: int = 54,
              baseline=None, dot: bool = True) -> str:
    """A tiny theme-aware inline sparkline (area + line + last-point marker),
    used both for the nowcast hover charts and the standout-stock cards. Pure
    SVG so it needs no client JS and works offline. `vals` should already be a
    clean numeric list. `baseline` draws a dashed reference line (0 = stall,
    2 = the Fed's inflation target, …)."""
    vals = [float(v) for v in vals if v is not None and v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if baseline is not None:
        lo, hi = min(lo, float(baseline)), max(hi, float(baseline))
    rng = (hi - lo) or 1.0
    n = len(vals)
    pad = h * 0.10  # keep the line off the top/bottom edges

    def xy(i, v):
        return (i / (n - 1) * w, (h - pad) - ((v - lo) / rng) * (h - 2 * pad) + pad)

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(vals)))
    out = [f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
           f'width="100%" height="{h}">']
    if baseline is not None:
        by = (h - pad) - ((float(baseline) - lo) / rng) * (h - 2 * pad) + pad
        out.append(f'<line x1="0" y1="{by:.1f}" x2="{w}" y2="{by:.1f}" '
                   f'stroke="var(--muted)" stroke-width="0.8" stroke-dasharray="3 3" '
                   f'opacity="0.55"/>')
    out.append(f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" '
               f'opacity="0.12" stroke="none"/>')
    out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
               f'stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/>')
    if dot:
        lx, ly = xy(n - 1, vals[-1])
        out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/>')
    out.append("</svg>")
    return "".join(out)


def nowcast_history(f: "pd.DataFrame") -> dict:
    """Per-metric historical mini-charts for the Macro-nowcast hover popovers.
    Reuses the SAME transforms the dashboard headline numbers use (raw level for
    WEI/GDPNow, the annualized-smoothed monthly print for sticky/flexible CPI) so
    the last charted point matches the displayed value. Returns SVG + key stats
    keyed by metric; metrics absent from the feature frame are simply omitted."""
    from engine.conditions import _ann_monthly_pct
    sm = config.load()["engine"]["conditions"]["inflation_nowcast"]["smooth_months"]
    out: dict[str, dict] = {}

    def _trend(distinct, lookback, kind, eps):
        """Directional read over `lookback` distinct prints. `kind` decides the
        vocabulary AND the favourability colour: a growth metric rising is
        market-friendly (good), an inflation metric accelerating is not (bad).
        Returns (word, dir) where dir in {good, bad, flat} drives the colour."""
        if len(distinct) <= lookback:
            return None, None
        chg = float(distinct.iloc[-1]) - float(distinct.iloc[-1 - lookback])
        if kind == "growth":
            if chg > eps:
                return "rising", "good"
            if chg < -eps:
                return "falling", "bad"
        else:
            if chg > eps:
                return "accelerating", "bad"
            if chg < -eps:
                return "cooling", "good"
        return "flat", "flat"

    def pack(name, raw, color, baseline, keep, per_year, kind, lookback, eps, monthly=False):
        if raw is None:
            return
        s = raw.dropna()
        if monthly:                       # collapse ffilled daily rows to monthly prints
            s = s[s.ne(s.shift())]
        s = s.iloc[-keep:]
        if len(s) < 3:
            return
        word, tdir = _trend(s, lookback, kind, eps)
        out[name] = {
            "svg": _mini_svg(list(s), color=color, baseline=baseline),
            "lo": round(float(s.min()), 1), "hi": round(float(s.max()), 1),
            "last": round(float(s.iloc[-1]), 1), "years": round(len(s) / per_year, 1),
            "trend": word, "dir": tdir, "kind": kind, "baseline": baseline,
        }

    col = lambda c: f[c] if c in f.columns else None  # noqa: E731
    pack("wei", col("wei"), "var(--link)", 0.0, 160, 52, "growth", 13, 0.08, monthly=True)
    # GDPNow window stops short of the 2020 COVID -32%→+37% whipsaw, which would
    # otherwise squash all post-pandemic detail into a flat line.
    pack("gdpnow", col("gdpnow"), "var(--link)", 0.0, 20, 4, "growth", 1, 0.10, monthly=True)
    sticky = col("sticky_cpi")
    flex = col("flex_cpi")
    if sticky is not None:
        pack("sticky", _ann_monthly_pct(sticky, sm), "var(--orange)", 2.0, 84, 12,
             "inflation", 3, 0.10, monthly=True)
    if flex is not None:
        pack("flexible", _ann_monthly_pct(flex, sm), "var(--orange)", 2.0, 84, 12,
             "inflation", 3, 0.30, monthly=True)
    return out


def regime_stance(latest: dict, pb: dict | None) -> dict | None:
    """Turn the regime's AGE × the transition-radar STATE into a single actionable
    verdict on the 'let winners run … look for a regime change' spectrum — the
    methodology that used to live only inside a help tooltip. Radar state drives
    the call (it already encodes the warning count); age modulates it (an old
    regime makes the same warnings matter more)."""
    prog = (pb or {}).get("progress") if pb else None
    if not prog:
        return None
    ts = latest.get("transition_state") or "STABLE"
    age_frac = max(0.0, min(1.0, (prog.get("bar_pct") or 50) / 100.0))
    n_warn = sum(1 for v in (latest.get("transition_flags") or {}).values() if v)
    # radar state -> (verdict bucket, marker base position on the 0..1 spectrum)
    table = {"STABLE": ("run", 0.12), "WEAKENING": ("hold", 0.50),
             "TRANSITIONING": ("shift", 0.80), "NEW_REGIME": ("reset", 0.93)}
    key, base = table.get(ts, ("hold", 0.5))
    pos = min(0.95, max(0.05, base + 0.12 * age_frac))
    # an OLD regime that is already weakening tips over into 'look for a change'
    if ts == "WEAKENING" and age_frac >= 0.75:
        key, pos = "shift", min(0.95, pos + 0.12)
    age_word = "young" if age_frac < 0.4 else ("mid-life" if age_frac < 0.72 else "old")
    return {"key": key, "pos_pct": round(pos * 100), "radar": ts,
            "age_word": age_word, "n_warn": n_warn}


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
    # ----- standout-stock ranking ------------------------------------------------
    # Within each urgency tier, rank by the alpha-aware SETUP score (selection =
    # sector-neutral residual momentum × timing = the calibrated cycle entry +
    # reversal overlay; see engine/setups.py). This upgrades the old |eq_score|-only
    # order so a sector-neutral LEADER on a fresh, constructive entry outranks an
    # equally-timed laggard. setup_score is always set (timing-only fallback when a
    # name has no residual), so every card ranks on the same scale. Then prefer
    # fresher signals. A soft conviction floor still drops 'minimal' (|eq|<15) timing
    # setups, but only while enough genuine ones remain so the strip never starves.
    order = {"now": 0, "imminent": 1, "exit": 2}

    def _conv(n):
        return abs(n.get("eq_score") or 0)

    def _decis(n):
        # decisiveness in the tier's DIRECTION: buys want the highest setup first,
        # exits want the most-negative (strongest sell) first.
        ss = n.get("setup_score")
        if ss is None:                                  # defensive — always set now
            ss = (n.get("eq_score") or 0) / 100.0
        return ss if n.get("urgency") == "exit" else -ss

    def _rank(n):
        # exact setup decisiveness leads; the factor composite breaks near-ties only
        # (a crowded/decayed leg — it should settle ties, never override the setup).
        return (order.get(n["urgency"], 9), _decis(n),
                -(n.get("factor_z") or 0.0),
                n.get("age_days") if n.get("age_days") is not None else 999,
                n["days"] if n.get("days") is not None else 99)

    from engine.setups import norm_company

    # A soft per-sector cap keeps one hot sector (e.g. all of XLK in a tech rip) from
    # crowding out the board — the best names per sector fill first, then any spare
    # slots backfill from the overflow (already in rank order). Dual-class listings
    # (GOOG + GOOGL) are collapsed to the best-ranked variant.
    CAP, FLOOR, PER_SECTOR = 24, 15, 5
    strong = [n for n in notable if _conv(n) >= FLOOR]
    pool = strong if len(strong) >= 6 else notable
    seen, seen_name, by_sec, picked, overflow = set(), set(), {}, [], []
    for n in sorted(pool, key=_rank):
        if n["ticker"] in seen:
            continue
        nm = norm_company(n.get("name"))
        if nm and nm in seen_name:                      # dual-class / multi-listing dupe
            continue
        seen.add(n["ticker"])
        if nm:
            seen_name.add(nm)
        sec = n.get("sector")
        if by_sec.get(sec, 0) < PER_SECTOR:
            by_sec[sec] = by_sec.get(sec, 0) + 1
            picked.append(n)
        else:
            overflow.append(n)
    notable_clean = (picked + overflow)[:CAP]
    return {"buy_now": buy_now, "buy_soon": buy_soon, "take_profits": take_profits,
            "hold": hold, "avoid": avoid, "notable": notable_clean[:CAP]}


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
        # macro-risk leg: shown only when non-zero so the pre-overlay tooltip is
        # byte-identical. Can be a penalty (cyclical, risk-off) or a small credit
        # (defensive) — phrased as an adjustment, and it keeps the parts reconciling
        # to the displayed heat number (the honesty contract).
        _mp = parts.get("macro") or 0
        macro_en = (f", plus a macro-risk adjustment for an elevated macro-risk backdrop on a "
                    f"macro-sensitive sector ({_mp:+d})" if _mp else "")
        macro_zh = (f"，并计入宏观风险调整（{_mp:+d}，宏观风险升高且板块对宏观敏感时）"
                    if _mp else "")
        r["heat_tip"] = T(
            f"Heat {r['heat']} out of 100 — how strong and confirmed this sector looks right "
            f"now (0 = ice-cold, 100 = red-hot). It adds up these parts: how well it fits the "
            f"current market backdrop ({parts.get('regime')}), the health of its trend "
            f"({parts.get('tape')}), its chart strength ({parts.get('technicals')}), and a "
            f"crowding penalty when it's overstretched ({parts.get('crowding')}){macro_en}. "
            f"Reading — {r['heat_label']}: {read_en}{cal_txt_en}",
            f"热度 {r['heat']}/100 — 衡量该板块此刻有多强、有多被确认（0 = 冰冷，100 = 火热）。"
            f"它由以下几部分相加：与当前市场环境的契合度（{parts.get('regime')}）、"
            f"趋势的健康度（{parts.get('tape')}）、图表强度（{parts.get('technicals')}）、"
            f"以及过度拉伸时的拥挤度扣分（{parts.get('crowding')}）{macro_zh}。"
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
    """Compact teaser for the dashboard's "real fund moves" panel: the top
    conviction-ranked ACCUMULATION decisions across the thematic/active fund
    universe (same engine as the full radar at etfs.html). Conviction = pp of
    fund weight committed, so a tiny-position double doesn't outrank a real add."""
    from engine.holdings_signals import top_etf_accumulation
    n = config.load()["holdings_signals"].get("panel_top_n", 12)
    try:
        acc = top_etf_accumulation().get("accumulation", [])[:n]
    except Exception as e:  # noqa: BLE001 — panel is additive, never fatal
        log.error("fund moves panel failed: %s", e)
        return []
    return [{
        "fund": s["etf"], "fund_name": s.get("etf_name", s["etf"]),
        "ticker": s["ticker"], "name": s["name"], "sector": s.get("sector", ""),
        "weight_pct": s.get("weight_pct"), "conviction_pp": s.get("conviction_pp"),
        "active_chg_pct": s.get("active_chg_pct"), "direction": s["direction"],
        "is_active": s.get("is_active", False), "confirmed": s.get("confirmed", False),
        "ladder": s.get("ladder"), "window": s.get("window", ""),
    } for s in acc]


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


def _fund_flows_by_ticker(rows: list[dict]) -> dict[str, list[dict]]:
    """Group every fund decision by the STOCK it touched, so each ticker's page
    can answer "which thematic/active funds are buying or selling me". Sorted by
    conviction magnitude within each ticker."""
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["ticker"], []).append({
            "fund": r["etf"], "fund_name": r.get("etf_name", r["etf"]),
            "theme": r.get("category", ""), "is_active": r.get("is_active", False),
            "direction": r["direction"], "conviction_pp": r.get("conviction_pp"),
            "weight_pct": r.get("weight_pct"), "active_chg_pct": r.get("active_chg_pct"),
            "is_new": r.get("is_new", False), "is_exit": r.get("is_exit", False),
            "window": r.get("window", ""),
        })
    for tk in by:
        by[tk].sort(key=lambda m: -abs(m.get("conviction_pp") or 0))
    return by


def build_etf_page(env: Environment, site: Path, generated: str,
                   rows: list[dict] | None = None) -> None:
    """Render etfs.html — the "real fund moves" board: conviction-ranked,
    accumulation-first holding decisions across the curated thematic/active ETF
    universe. Also writes site/stockdata/fund_flows.json so each stock page can
    show which funds bought/sold it. See engine/holdings_signals."""
    from engine.holdings_signals import all_etf_signals, split_by_conviction
    if rows is None:
        try:
            rows = all_etf_signals()
        except Exception as e:  # noqa: BLE001
            log.error("etf signals failed: %s", e)
            rows = []
    split = split_by_conviction(rows)
    html = env.get_template("etfs.html.j2").render(
        accumulation=split["accumulation"], trims=split["trims"],
        generated_utc=generated)
    (site / "etfs.html").write_text(html)
    # per-stock feed (built before the stock library so it can be attached there)
    outdir = site / "stockdata"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "fund_flows.json").write_text(
        json.dumps(_fund_flows_by_ticker(rows), separators=(",", ":"), default=str))
    log.info("wrote etfs.html (%d accumulation, %d trims) + fund_flows.json (%d names)",
             len(split["accumulation"]), len(split["trims"]),
             len({r["ticker"] for r in rows}))


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
        try:
            from collectors.edgar_eps import build_eps_panel
            build_eps_panel()                      # SUE: quarterly diluted-EPS panel (weekly-cached)
        except Exception as e:  # noqa: BLE001 — SUE factor is an optional leg
            log.warning("edgar quarterly EPS panel failed: %s", e)
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


ETF_GICS = {                       # SPDR sector fund -> GICS sector (residual-alpha leaders)
    "XLK": "Information Technology", "XLF": "Financials", "XLV": "Health Care",
    "XLY": "Consumer Discretionary", "XLP": "Consumer Staples", "XLE": "Energy",
    "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities",
    "XLRE": "Real Estate", "XLC": "Communication Services",
}


def build_alpha_data(site: Path) -> dict | None:
    """Compute the sector-neutral residual-momentum cross-section and write
    factordata/alpha.json (consumed by the sector pages + per-stock panels).
    Additive — any failure logs and skips. See research/RESIDUAL_ALPHA_MOMENTUM.md."""
    from engine.residual_alpha import compute_residual_alpha
    try:
        alpha = compute_residual_alpha()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("residual-alpha engine failed: %s", e)
        return None
    if not alpha:
        return None
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "alpha.json").write_text(json.dumps(alpha, separators=(",", ":"), default=str))
    log.info("wrote alpha.json (%d names, %d sectors)", alpha.get("n"),
             len(alpha.get("by_sector", {})))
    return alpha


def build_insider_data(site: Path) -> dict | None:
    """Per-ticker insider-conviction map (net Form-4 buying as bps of market cap over
    a trailing window + distinct-insider CLUSTER count) → factordata/insider_signals.
    json, the CONFIRMER chip on the standout / Top-setups boards. Market cap is read
    from the prior factors.json (slow-moving — a one-build lag is immaterial). Reuses
    the validated net_mcap_bps construction (engine.equity_factors.insider_signals).
    Additive + graceful: returns/writes nothing if the panel or caps are missing."""
    from engine.equity_factors import insider_signals
    mktcap = None
    fp = site / "factordata" / "factors.json"
    if fp.exists():
        try:
            tbl = (json.loads(fp.read_text()) or {}).get("table", [])
            mktcap = pd.Series({r["ticker"]: (r.get("mktcap_bn") or 0) * 1e9
                                for r in tbl if r.get("ticker") and r.get("mktcap_bn")})
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("insider mktcap load failed (%s)", e)
    try:
        sig = insider_signals(mktcap)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("insider signals failed: %s", e)
        return None
    if not sig:
        return None
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "insider_signals.json").write_text(
        json.dumps(sig, separators=(",", ":"), default=str))
    log.info("wrote insider_signals.json (%d names with 6mo Form-4 activity)", len(sig))
    return sig


def build_smartmoney_data(site: Path) -> dict | None:
    """Compute curated super-investor 13F holdings and write
    factordata/smartmoney.json (consumed by the per-stock "who holds this" panel +
    a future consensus board). Additive — any failure logs and skips. CONTEXT only,
    never wired into any score. See collectors/edgar_13f.py + engine/smart_money.py."""
    from engine.smart_money import compute_smart_money
    try:
        sm = compute_smart_money()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("smart-money engine failed: %s", e)
        return None
    if not sm:
        return None
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "smartmoney.json").write_text(json.dumps(sm, separators=(",", ":"), default=str))
    log.info("wrote smartmoney.json (%d funds, %d names)", sm.get("n_funds"), sm.get("n_names"))
    return sm


def build_sector_pages(env: Environment, site: Path, generated: str,
                       alpha: dict | None = None) -> dict:
    """Render sectors/<FUND>.html drill-downs; return per-fund timing summary
    for the heat board."""
    import json as _json

    from collectors.sector_holdings import latest_fundamentals, latest_top10
    from engine.conditions import sector_macro_beta
    from engine import ticker_alerts
    from engine.cycles import LADDER, STATE_DISPLAY, analyze
    from engine.holdings_signals import accumulation_signals
    from engine.playbook import SECTOR_NAMES
    from engine.setups import US_ALPHA_WEIGHT, timing_tilt
    from scripts.build_stock_library import current_liquidity, current_macro

    # per-ticker sector-neutral residual alpha (already computed by build_alpha_data
    # and passed in) — used to enrich the front-page "Standout individual stocks"
    # cards with an alpha sector rank + reversal overlay and an alpha-aware setup
    # score (selection × timing). Absent => cards fall back to pure cycle timing.
    alpha_pt = (alpha or {}).get("per_ticker", {})
    # confirmer legs on those same cards: a distinct-insider Form-4 BUY cluster
    # (insider_signals.json, written by build_insider_data just above) and the
    # cross-sectional factor composite (factors.json table) as a light tiebreaker.
    # Both additive + graceful — absent => the card simply omits that chip.
    insider_map: dict[str, dict] = {}
    factor_z: dict[str, float] = {}
    try:
        _ip = site / "factordata" / "insider_signals.json"
        if _ip.exists():
            insider_map = json.loads(_ip.read_text()) or {}
        _fp = site / "factordata" / "factors.json"
        if _fp.exists():
            for _r in (json.loads(_fp.read_text()) or {}).get("table", []):
                if _r.get("ticker") and _r.get("composite") is not None:
                    factor_z[_r["ticker"]] = _r["composite"]
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("standout confirmer maps unavailable (%s)", e)

    cal_path = config.data_dir() / "regime" / "ladder_calibration.json"
    calibration = _json.loads(cal_path.read_text()) if cal_path.exists() else None
    # live US net-liquidity regime + aggregate macro-risk score — the orthogonal
    # macro conviction modifiers threaded into every per-sector / per-stock ladder
    # read AND the accumulation overlay (so the overlay ladder matches the card).
    liq = current_liquidity()
    drag = current_macro()
    # benchmark + feed window for each ETF's alert timeline (the ladder log itself
    # is written by build_stock_library, where these ETFs also live — no re-write)
    _spy = store.read("yahoo", "SPY")
    _bench = _spy["close"] if _spy is not None else None
    _acfg = config.load().get("alerts", {})
    _adays = int(_acfg.get("ticker_timeline_days", 120))
    _amax = int(_acfg.get("ticker_max_events", 50))
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
        beta = sector_macro_beta(fund)
        res = analyze(etf["close"], liquidity=liq, macro_drag=drag, macro_beta=beta)
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
                h = analyze(df["close"], df.get("high"), liquidity=liq,
                            macro_drag=drag, macro_beta=beta)
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
                    lad = h["ladder"]
                    closes = df["close"].dropna()
                    px = float(closes.iloc[-1]) if len(closes) else None
                    hi52 = float(closes.iloc[-252:].max()) if len(closes) else None
                    off_high = (round((px / hi52 - 1) * 100, 1)
                                if px and hi52 else None)
                    # ~3 months of daily closes, thinned for a compact card sparkline
                    tail = closes.iloc[-66:]
                    spark = list(tail.iloc[::2].round(3)) if len(tail) > 4 else []
                    sdir = lad.get("dir")
                    scolor = ("var(--up)" if sdir == "up"
                              else "var(--down)" if sdir == "down" else "var(--warn)")
                    # alpha-aware setup score: selection (sector-neutral residual
                    # momentum) × timing (cycle entry + reversal overlay). Falls back
                    # to timing-only when the name has no residual, so EVERY card has
                    # a setup_score on the same scale for ranking. NOT a new edge —
                    # see engine/setups.py + research/US_STANDOUT_SETUP_SCORE.md.
                    apt = alpha_pt.get(tick)
                    az = apt.get("alpha") if apt else None
                    a_entry = apt.get("entry") if apt else None
                    tilt = timing_tilt(urg, lad.get("eq_dir"), a_entry)
                    setup = round((US_ALPHA_WEIGHT * az + tilt) if az is not None
                                  else tilt, 2)
                    # confirmers: an insider BUY cluster (>=2 distinct insiders net
                    # buying, Form-4 6mo) + the factor composite (light tiebreaker)
                    ins = insider_map.get(tick) or {}
                    ins_buy = ins.get("buyers", 0) >= 2 and (ins.get("net_mn") or 0) > 0
                    notable.append({"ticker": tick, "name": str(r.get("name", "")).title(),
                                    "sector": SECTOR_NAMES.get(fund, fund),
                                    "label": lad["label"], "action": lad.get("action"),
                                    "tag": lad["entry"]["tag"], "urgency": urg,
                                    "days": lad["entry"].get("days_hi"),
                                    "dir": sdir,
                                    "price": round(px, 2) if px is not None else None,
                                    "off_high": off_high,
                                    "eq_score": lad.get("eq_score"),
                                    "eq_grade": lad.get("eq_grade"),
                                    "eq_grade_zh": lad.get("eq_grade_zh"),
                                    "score": lad.get("score"),
                                    "setup_score": setup,
                                    "alpha_z": az,
                                    "alpha_sector_rank": apt.get("sector_rank") if apt else None,
                                    "alpha_sector_n": apt.get("sector_n") if apt else None,
                                    "alpha_entry": a_entry,
                                    "factor_z": factor_z.get(tick),
                                    "insider_buyers": ins.get("buyers") if ins_buy else None,
                                    "insider_bps": ins.get("bps") if ins_buy else None,
                                    "insider_net_mn": ins.get("net_mn") if ins_buy else None,
                                    "signal_date": lad.get("signal_date"),
                                    "age_days": lad.get("age_days"),
                                    "spark_svg": _mini_svg(spark, color=scolor, w=240, h=42,
                                                           dot=True),
                                    "age_short": lad.get("age_short"),
                                    "age_short_zh": lad.get("age_short_zh"),
                                    "eq_badge": lad.get("eq_badge"),
                                    "eq_dir": lad.get("eq_dir"),
                                    "eq_tip": lad.get("eq_tip")})
        buy_zone = sum(1 for h in holdings if h["ladder"]["state"] in BUY_ZONE_STATES)
        s = {"fund": fund, "name": SECTOR_NAMES.get(fund, fund),
             "mtf_json": _json2.dumps(res.get("mtf", {})), **res,
             "holdings": holdings,
             "accumulation": accumulation_signals(fund, liquidity=liq,
                                                  macro_drag=drag, macro_beta=beta)}
        if alpha and fund in ETF_GICS:                 # within-sector residual-alpha leaders
            _sa = (alpha.get("by_sector") or {}).get(ETF_GICS[fund])
            if _sa:
                s["alpha_leaders"] = _sa.get("leaders")
        ec = etf["close"].dropna()
        # technical snapshot for the at-a-glance signal-chip strip (same shape the
        # stock analyzer reads from its JSON, so both pages render identical chips)
        from engine.technicals import snapshot as _snap
        s["tech"] = _snap(ec)
        feed = ticker_alerts.build_feed(
            fund, ec, etf.get("high"), _bench, res.get("ladder"),
            str(ec.index.max().date()), days=_adays, max_events=_amax)
        html = tpl.render(s=s, state_styles=STATE_STYLES, calibration=calibration,
                          ladder_order=LADDER, state_display=STATE_DISPLAY,
                          alerts=feed, generated_utc=generated)
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


def build_advanced_page(env: Environment, site: Path, generated: str, latest: dict, f,
                        confirming, contradicting):
    """The Quant Lab — the geekier reads, kept off the main dashboard: cross-asset
    concentration + risk budgeting + the factor IC scorecard + the raw market-
    internals tables (dials / pair-ratios / size-style / accumulation / fund flows).
    Computes the cross-asset & portfolio snapshots FRESH (like build_factors_page),
    so the page is populated even if the last engine.run predates them; reads the
    factor IC scorecard JSON if present. Returns the cross-asset snapshot for the
    dashboard's compact card."""
    cross_asset = portfolio = ic_scorecard = None
    try:
        from engine.cross_asset import snapshot as _ca
        cross_asset = _ca()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("cross-asset snapshot failed: %s", e)
    try:
        from engine.portfolio import snapshot as _pf
        portfolio = _pf()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("portfolio snapshot failed: %s", e)
    icp = config.data_dir() / "edgar" / "ic_scorecard.json"
    if icp.exists():
        try:
            ic_scorecard = json.loads(icp.read_text())
        except Exception:  # noqa: BLE001
            ic_scorecard = None
    html = env.get_template("advanced.html.j2").render(
        latest=latest, generated_utc=generated,
        cross_asset=cross_asset, portfolio=portfolio, ic_scorecard=ic_scorecard,
        components_confirming=confirming, components_contradicting=contradicting,
        flip_plain=flip_plain_text(latest),
        internals=internals_rows(latest), size_style=size_style_rows(f),
        breadth_div=breadth_divergence(f),
        accumulation=accumulation_rows(), holdings_changes=holdings_rows(),
        holdings_threshold=config.load()["holdings"]["active_change_alert_pct"],
        flows_html=flows_html_table(),
    )
    (site / "advanced.html").write_text(html)
    log.info("wrote advanced.html (%.0f KB)", (site / "advanced.html").stat().st_size / 1024)
    return cross_asset


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
    alpha_data = None
    try:
        alpha_data = build_alpha_data(site)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("alpha data failed: %s", e)
    try:
        build_insider_data(site)               # confirmer-chip map; read by sector pages + library
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("insider data failed: %s", e)
    try:
        build_smartmoney_data(site)               # 13F super-investor holdings (CONTEXT)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("smart-money data failed: %s", e)
    try:
        sector_timing, notable = build_sector_pages(env, site, generated, alpha=alpha_data)
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
    # Quant Lab (advanced analytics): cross-asset concentration + risk budgeting +
    # factor scorecard + the raw internals moved off the main dashboard. Returns the
    # cross-asset snapshot for the dashboard's compact one-bet card.
    cross_asset_snap = None
    try:
        cross_asset_snap = build_advanced_page(env, site, generated, latest, f,
                                               confirming, contradicting)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("advanced page failed: %s", e)
    # copy shared static assets (theme + visual widgets) into the site
    for asset in ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
                  "stockdata.js", "watchlist.js", "auth.js", "tablesort.js", "charts.js",
                  "masterbrief.js", "stockbrief.js"):
        src = config.ROOT / "templates" / asset
        if src.exists():
            (site / asset).write_text(src.read_text())
    # broad "Top setups" board (selection × timing across the full S&P 1500),
    # written by build_stock_library at the END of the prior build_site run —
    # additive + graceful: absent (first run) => the board simply doesn't render.
    top_setups = None
    _sp = site / "factordata" / "setups.json"
    if _sp.exists():
        try:
            top_setups = json.loads(_sp.read_text())
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("setups.json unreadable (%s)", e)

    # Macro news & catalysts (LEAF, additive, never fatal). Catalysts (FOMC + jobs
    # report) are keyless and always on; filtered headlines + the optional LLM brief
    # only when macro_news.enabled. News NEVER feeds any score.
    macro_catalysts, macro_news_data, macro_brief_data = [], None, None
    macro_news_disclaimer = macro_news_disclaimer_zh = ""
    try:
        from engine import macro_news as _mnews
        _mncfg = config.load().get("macro_news", {}) or {}
        macro_catalysts = _mnews.upcoming_catalysts(
            horizon_days=_mncfg.get("catalysts_horizon_days", 14))
        macro_news_data = _mnews.macro_headlines()
        macro_news_disclaimer = _mnews.DISCLAIMER_TEXT
        macro_news_disclaimer_zh = _mnews.DISCLAIMER_TEXT_ZH
        if macro_news_data and macro_news_data.get("headlines"):
            _ra = (latest.get("conditions") or {}).get("risk_appetite") or {}
            _sent = (f"{_ra.get('news_sentiment_state')} (z={_ra.get('news_sentiment_z')})"
                     if _ra.get("news_sentiment_state") else "")
            macro_brief_data = _mnews.macro_brief(
                macro_news_data["headlines"],
                regime_line=str((latest.get("regime") or {}).get("label", "")),
                sentiment_line=_sent)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("macro news failed: %s", e)

    # prediction-markets odds (additive leaf; None if no snapshot yet)
    prediction_markets = None
    try:
        from engine import prediction_markets as _pm
        prediction_markets = _pm.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("prediction markets failed: %s", e)

    from engine.alerts import alert_views
    html = env.get_template("dashboard.html.j2").render(
        latest=latest,
        macro_catalysts=macro_catalysts,
        prediction_markets=prediction_markets,
        macro_news=macro_news_data,
        macro_brief=macro_brief_data,
        macro_news_disclaimer=macro_news_disclaimer,
        macro_news_disclaimer_zh=macro_news_disclaimer_zh,
        alerts=alert_views(latest.get("alerts", [])),
        pb=latest.get("playbook"),
        month_name=calendar.month_name[pd.Timestamp(latest["date"]).month],
        commodities=(latest.get("playbook") or {}).get("commodities", []),
        sector_timing=sector_timing,
        action_board=action_board(sector_timing, notable),
        top_setups=top_setups,
        components_confirming=confirming,
        components_contradicting=contradicting,
        flip_plain=flip_plain_text(latest),
        internals=internals_rows(latest),
        size_style=size_style_rows(f),
        breadth_div=breadth_divergence(f),
        breadth_panel=breadth_scorecard(),
        sector_rows=sector_rows(latest.get("playbook"), sector_timing),
        generated_utc=generated,
        chart_liquidity=chart_liquidity(f),
        chart_credit_breadth=chart_credit_breadth(f),
        market_tiles=market_tiles(f),
        vix=vix_monitor(f),
        chart_vix=chart_vix(f),
        positioning=positioning_rows(f),
        holdings_changes=holdings_rows(),
        holdings_threshold=config.load()["holdings"]["active_change_alert_pct"],
        accumulation=accumulation_rows(),
        flows_html=flows_html_table(),
        health=health_rows(),
        factor_leadership=factor_leadership,
        nowcast_hist=nowcast_history(f),
        stance=regime_stance(latest, latest.get("playbook")),
        cross_asset=cross_asset_snap,
    )
    # Write the macro dashboard straight to macro.html. index.html is owned
    # solely by build_vector.build_landing() (the landing hub) — keeping the raw
    # dashboard out of index.html is what stops Home (-> index.html) from
    # regressing to the dashboard when build_vector doesn't run after this.
    out = site / "macro.html"
    out.write_text(html)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)

    # --- history page: the longer-window charts + lifespan base rates ----------
    from engine.playbook import QUAD_SHORT, next_quads_line, transition_stats
    trans = transition_stats(hist["quad"])
    lifespan_rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        lifespan_rows.append({"name": QUAD_SHORT[q],
                              "n": trans["n_by_quad"].get(q, "—"),
                              "median": trans["median_days"].get(q, "—"),
                              "next": next_quads_line(nxt),
                              "next_zh": next_quads_line(nxt, zh=True)})
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
        from engine import ticker_alerts as _ta
        sd_json = _json.dumps(STATE_DISPLAY)
        (site / "stock.html").write_text(
            env.get_template("stock.html.j2").render(
                state_styles=STATE_STYLES, generated_utc=generated,
                state_display_json=sd_json,
                ticker_alert_meta_json=_json.dumps(_ta.edge_meta())))
        # refresh the cached 中文 translations of the (English-sourced) company blurbs
        # BEFORE building the library, so the per-stock JSON carries description_zh.
        # Gated + cached + degrade-never-raise: a no-op without the configured key, and
        # only new/changed blurbs hit the API (see scripts/translate_profiles.py).
        try:
            from scripts.translate_profiles import main as translate_profiles
            translate_profiles()
        except Exception as e:  # noqa: BLE001 — translation is optional, never break the build
            log.warning("profile translation step failed (%s); blurbs stay English", e)
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

        # 🧠 AI stock briefs (LLM "Option 2") — DEFAULT-OFF LEAF. Precompute a
        # research brief for a small, bounded set (the action-board standouts +
        # the watchlist's suggested tickers) into site/stockbrief/<TICKER>.json,
        # cached per ticker per day. The stock page fetches it client-side; the
        # static site cannot call the model on demand (no server-side key). Gated
        # by catalyst_stock.enabled — a no-op (and zero cost) when off.
        try:
            from engine import catalyst_stock
            if catalyst_stock.enabled():
                brief_set = ([n["ticker"] for n in notable]
                             + list(config.load().get("watchlist", {}).get("suggested", [])))
                briefs = catalyst_stock.precompute_briefs(brief_set, root=config.ROOT, site=site)
                log.info("precomputed %d AI stock brief(s)", len(briefs))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("stock brief precompute failed: %s", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
