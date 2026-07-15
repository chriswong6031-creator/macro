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
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.sponsors import flows_table  # noqa: E402
from engine.i18n import t as T  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from engine.market_gamma import view as market_gamma_view  # noqa: E402 — SHARED deriver: FE banner + contract (engine/run.py) call the SAME function so they can't drift
from lib import config, site_assets, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

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


# Canonical Yahoo/Polygon symbol + data-mkt per tile, so live.js can refresh the
# level (.nb-px) and % (.nb-chg) in place. The Treasury-yield tiles (us10y/30y/5y)
# are FRED series with no tradeable last-price quote -> intentionally absent.
_TILE_SYM = {
    "SPY": ("SPY", "idx"), "QQQ": ("QQQ", "idx"), "vix": ("^VIX", "idx"),
    "dxy": ("DX-Y.NYB", "idx"), "oil": ("CL=F", "fut"),
}


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
        sym, mkt = _TILE_SYM.get(col, (None, None))
        rows.append({
            "label": T(en, zh), "tag": T(ten, tzh),
            "level": (f"{last:.{dec}f}%" if is_rate else f"{last:,.{dec}f}"),
            "chg": f"{chg:+.{dec}f}", "pct": f"{pct:+.1f}%",
            "tone": "pos" if chg > 0 else "neg" if chg < 0 else "muted",
            "sym": sym, "mkt": mkt,
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


# --- Advanced breadth tracker (market internals) ----------------------------
# The classic second-derivative breadth gauges a desk watches beyond today's
# %-above-MA snapshot: ratio-adjusted McClellan Oscillator + Summation Index, the
# Zweig Breadth Thrust gauge, the High-Low (record-high-percent) Index, the A/D-
# line-vs-price divergence check, and where participation sits in its own deep
# history. Computed on the deep S&P-500 breadth series (1962-) by
# engine.advanced_breadth; DISPLAY-ONLY (a function of price is coincident with
# it — this explains the tape's quality, it does not forecast it).
_TONE_COLOR = {"pos": "var(--up)", "neg": "var(--down)", "muted": "var(--link)"}
_ABR_MCC_BAND = {
    "surging": T("surging", "急涨"), "positive": T("positive", "正向"),
    "neutral": T("neutral", "中性"), "negative": T("negative", "负向"),
    "oversold": T("oversold", "超卖"),
}
_ABR_THRUST_ZONE = {
    "thrust": T("thrust", "脉冲"), "neutral": T("neutral", "中性"),
    "washed": T("washed out", "超卖"),
}
_ABR_HL_BAND = {
    "expanding": T("expanding", "扩张"), "mixed": T("mixed", "参差"),
    "contracting": T("contracting", "收缩"),
}
_ABR_DIV = {
    "bearish_div": (T("bearish divergence", "看跌背离"),
                    T("price is making new highs the advance/decline line will not confirm — the rally is narrowing underneath",
                      "价格创新高，但腾落线未能确认 — 上涨在底层正在收窄")),
    "bullish_div": (T("bullish divergence", "看涨背离"),
                    T("price is making new lows the advance/decline line refuses to confirm — selling is narrowing",
                      "价格创新低，但腾落线拒绝确认 — 抛压正在收窄")),
    "confirmed_up": (T("confirming the highs", "确认新高"),
                     T("the advance/decline line is making new highs alongside price — the move is broadly supported",
                       "腾落线与价格同步创新高 — 走势获得广泛支撑")),
    "confirmed_down": (T("confirming the lows", "确认新低"),
                       T("the advance/decline line is making new lows with price — the weakness is broad",
                         "腾落线与价格同步创新低 — 弱势具有广度")),
    "inrange": (T("in range", "区间内"),
                T("neither price nor the advance/decline line is at a 3-month extreme — no divergence to read",
                  "价格与腾落线均未触及三个月极值 — 暂无背离可读")),
}
_ABR_GAP = {
    "broadening": (T("broadening", "扩散"),
                   T("small caps participating MORE than large — a healthy, broad-based tape",
                     "小盘参与度高于大盘 — 健康、广泛的盘面")),
    "narrowing": (T("narrowing", "收窄"),
                  T("small caps lagging large — a narrow, mega-cap-led advance (more fragile)",
                    "小盘落后于大盘 — 狭窄、由超大盘主导的上涨（更脆弱）")),
    "inline": (T("in line", "一致"),
               T("small- and large-cap participation roughly in line",
                 "小盘与大盘参与度大致一致")),
}
_ABR_HEAD = {
    "firm": (T("firm", "稳健"),
             T("the internals are confirming the tape — broad participation and positive momentum",
               "内部结构在确认盘面 — 参与广泛、动量为正")),
    "mixed": (T("mixed", "参差"),
              T("the internals send no clear signal either way right now",
                "当前内部结构没有明确的方向性信号")),
    "deteriorating": (T("deteriorating", "转弱"),
                      T("the internals are weakening under the surface — momentum and participation are rolling over",
                        "内部结构正在表层之下走弱 — 动量与参与度同步回落")),
}


def advanced_breadth_view(f: pd.DataFrame) -> dict | None:
    """Build the Advanced Breadth panel payload for the US stocks page. Reads the
    deep S&P-500 breadth series + the SPY proxy from the feature frame, calls the
    engine, and dresses the result with bilingual labels and inline sparklines.
    Additive and never fatal: any failure returns None and the panel is skipped."""
    from markupsafe import Markup
    try:
        from engine import advanced_breadth as ab
        big = pd.read_parquet(config.data_dir() / "breadth" / "breadth.parquet")
        price = f["SPY"].dropna() if "SPY" in f.columns else None
        tiers = {}
        for key, ns in (("large", "breadth"), ("mid", "midcap_breadth"),
                        ("small", "smallcap_breadth")):
            p = config.data_dir() / ns / "breadth.parquet"
            if p.exists():
                s = pd.read_parquet(p)["pct_above_50"].dropna()
                if len(s):
                    tiers[key] = float(s.iloc[-1])
        d = ab.advanced_breadth(big, price, tiers or None)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("advanced_breadth_view failed: %s", e)
        return None
    if not d:
        return None

    def spark(node, k="spark", baseline=None, w=240, h=46):
        vals = (node or {}).get(k) or []
        color = _TONE_COLOR.get((node or {}).get("tone", "muted"), "var(--link)")
        return Markup(_mini_svg(vals, color=color, w=w, h=h, baseline=baseline)) if vals else ""

    head = d["headline"]
    h_label, h_verdict = _ABR_HEAD.get(head["key"], _ABR_HEAD["mixed"])
    out = {"asof": d["asof"], "deep_from": d["deep_from"], "n_deep": d["n_deep"],
           "headline": {"label": h_label, "verdict": h_verdict, "tone": head["tone"]}}

    mcc = d.get("mcclellan")
    if mcc:
        out["mcc"] = {
            "osc": "%+.1f" % mcc["osc"], "tone": mcc["tone"],
            "band": _ABR_MCC_BAND.get(mcc["band"], _ABR_MCC_BAND["neutral"]),
            "rising": mcc["osc_rising"], "summ_rising": mcc["summ_rising"],
            "summ_chg20": "%+.0f" % mcc["summ_chg20"],
            "svg": spark(mcc, "spark", baseline=0.0),
        }
    thr = d.get("thrust")
    if thr:
        # gauge position of the live value within the 0.30-0.70 display band
        pos = max(0.0, min(100.0, (thr["value"] - 0.30) / 0.40 * 100))
        out["thrust"] = {
            "value": "%.2f" % thr["value"], "tone": thr["tone"],
            "zone": _ABR_THRUST_ZONE.get(thr["zone"], _ABR_THRUST_ZONE["neutral"]),
            "pos": round(pos, 1),
            "washed_pos": round((thr["washed"] - 0.30) / 0.40 * 100, 1),
            "thrust_pos": round((thr["thrust"] - 0.30) / 0.40 * 100, 1),
            "recent": thr["recent_thrust"], "hist_count": thr["hist_count"],
            "last": thr["last_thrust"],
        }
    hl = d.get("highlow")
    if hl:
        out["hl"] = {
            "hli": "%.0f" % hl["hli"], "tone": hl["tone"],
            "band": _ABR_HL_BAND.get(hl["band"], _ABR_HL_BAND["mixed"]),
            "net_nh": "%+d" % hl["net_nh"], "net_nh_10": "%+.1f" % hl["net_nh_10"],
            "svg": spark(hl, "spark", baseline=50.0),
        }
    div = d.get("divergence")
    if div:
        dl, dv = _ABR_DIV.get(div["state"], _ABR_DIV["inrange"])
        out["div"] = {"label": dl, "verdict": dv, "tone": div["tone"],
                      "corr": div["corr"], "window": div["window"],
                      "svg": spark(div, "spark")}
    par = d.get("participation")
    if par:
        out["par"] = {
            "pa50": "%.0f" % par["pa50"], "pa200": ("%.0f" % par["pa200"]) if par["pa200"] is not None else None,
            "chg20": "%+.1f" % par["pa50_chg20"],
            "chg_tone": "pos" if par["pa50_chg20"] > 0 else ("neg" if par["pa50_chg20"] < 0 else "muted"),
            "pctile": int(par["pctile"]) if par["pctile"] is not None else None,
            "hist_from": par["hist_from"], "ad_dir": par["ad_dir"],
            "tone": "pos" if par["pa50_chg20"] > 0 else "muted",
            "svg": spark({"spark": par["spark"], "tone": "pos" if par["pa50_chg20"] >= 0 else "neg"},
                         "spark", baseline=50.0),
        }
    gap = d.get("tiergap")
    if gap:
        gl, gv = _ABR_GAP.get(gap["state"], _ABR_GAP["inline"])
        out["gap"] = {"large": "%.0f" % gap["large"],
                      "mid": ("%.0f" % gap["mid"]) if gap["mid"] is not None else None,
                      "small": "%.0f" % gap["small"], "gap": "%+.1f" % gap["gap"],
                      "label": gl, "verdict": gv, "tone": gap["tone"]}
    return out


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
    from engine.conditions import _smooth_annual_rate
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
        pack("sticky", _smooth_annual_rate(sticky, sm), "var(--orange)", 2.0, 10, 12,
             "inflation", 3, 0.10, monthly=True)
    if flex is not None:
        pack("flexible", _smooth_annual_rate(flex, sm), "var(--orange)", 2.0, 10, 12,
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


def basket_action_items(site) -> dict:
    """Narrative-basket action items for the UNIFIED 'what to act on now' board, so the
    page acts on the narrative resolution (Memory/Storage vs Non-AI Software) and not just
    the 11 blurry GICS sectors. Sourced from the live theme-scoring recos
    (site/basketdata/baskets.json → theme_intel) and enriched with the allocation model's
    absolute-trend gate + durability + model-book weight (site/allocationdata/allocation.json).

    HONEST framing carried per item: the BUY side (enter/accumulate) is the descriptive
    leadership LENS (cross-sectional rank-IC ~0 on the clean sector backtest); the REDUCE
    side (trim/avoid) rides the backtested absolute-trend / fading-deteriorating drawdown gate
    (the one multi-decade-measured edge). `validated` flags which is which. Each item is
    badged kind='theme'. Graceful: empty buckets if the artifacts are absent.

    NEW — us_sector_* themes are separated out: they are returned in `sector_overlay` keyed
    by SPDR ticker (reverse-mapped from US_SECTOR_PAGE), not placed in narrative bucket rows.
    This prevents the board from double-listing each GICS sector (once as 🏛 cap-weighted
    cycle timing and once as 🧩 equal-weight basket).

    NEW — enter/accumulate routing now honours clean_entry from textures (or falls back to
    act_now membership). clean_entry.flag=True → buy_now (accumulate) / buy_soon (enter);
    flag absent/False → on_the_run bucket (in favour but no clean setup, don't chase)."""
    # Build reverse map: us_sector_<slug> → SPDR ticker from US_SECTOR_PAGE
    _slug_to_spdr: dict[str, str] = {}
    for _spdr, _href in US_SECTOR_PAGE.items():
        _slug = _href.replace("basket/", "").replace(".html", "")
        _slug_to_spdr[_slug] = _spdr

    buckets: dict = {"buy_now": [], "buy_soon": [], "on_the_run": [],
                     "take_profits": [], "hold": [], "avoid": [],
                     "sector_overlay": {}}
    try:
        ti = (json.loads((site / "basketdata" / "baskets.json").read_text())
              .get("theme_intel") or {})
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("basket action: baskets.json unreadable (%s)", e)
        return buckets
    themes = ti.get("themes") or []
    if not themes:
        return buckets

    # act_now lists provide a fallback when textures.clean_entry is absent
    act_now = ti.get("act_now") or {}
    act_now_buy_ids = {x["id"] for x in (act_now.get("buy") or [])}
    act_now_pullback_ids = {x["id"] for x in (act_now.get("add_on_pullback") or [])}

    alloc, book_wt = {}, {}
    try:
        aj = json.loads((site / "allocationdata" / "allocation.json").read_text())
        alloc = {r["id"]: r for r in (aj.get("ranks") or [])}
        book_wt = {w["id"]: w.get("weight")
                   for w in ((aj.get("allocation") or {}).get("weights") or [])}
    except Exception as e:  # noqa: BLE001 — enrichment only
        log.warning("basket action: allocation.json unreadable (%s)", e)

    # Lane mapping for non-buy recos — same as before
    reduce_bucket = {"hold": "hold", "trim": "take_profits", "avoid": "avoid"}

    for th in themes:
        tid = th.get("id") or ""
        reco = (th.get("reco") or "").lower()
        a = alloc.get(tid) or {}
        gate = a.get("gate") or {}
        tex = th.get("textures") or {}
        ce = tex.get("clean_entry") or {}
        # clean_entry: prefer textures.clean_entry.flag; fallback to act_now membership
        if ce:
            ce_flag = bool(ce.get("flag"))
            ce_quality = ce.get("quality")
        else:
            ce_flag = tid in act_now_buy_ids
            ce_quality = None

        _perf = th.get("perf") or {}
        _perf_20d = _perf.get("20d") or {}
        _brd = th.get("breadth") or {}
        _leader = th.get("leadership") or {}
        _top3 = [t.get("ticker") for t in (_leader.get("top") or [])[:3] if t.get("ticker")]
        _rr = (th.get("textures") or {}).get("rollover_risk") or {}
        _fd = th.get("flip_distance") or {}
        base_item = {
            "kind": "theme",
            "reco": reco,                            # raw reco; needed by action_board() reduce-side override
            "ticker": tid, "slug": tid,
            "href": "basket/" + tid + ".html",
            "name": th.get("name"), "name_zh": th.get("name_zh"),
            "label": th.get("reco_en") or reco.upper(),
            "label_zh": th.get("reco_zh") or reco,
            "score": th.get("score"),
            "alloc_rank": a.get("rank"),
            "above_trend": bool(gate.get("above_200dma")) if gate else None,
            "eligible": a.get("eligible"),
            "durability": (a.get("durability") or {}).get("bar"),
            "book_wt": book_wt.get(tid),
            "validated": reco in ("trim", "avoid"),   # the trend-gate / drawdown risk side
            "signal_grade": (th.get("signal_strength") or {}).get("grade"),
            "clean_entry": ce_flag,
            "clean_quality": ce_quality,
            # popover enrichment fields
            "perf_20d_rel": _perf_20d.get("rel"),
            "breadth_pct50": _brd.get("pct50"),
            "top_members": _top3,
            "rollover_band": _rr.get("band"),
            "rollover_band_zh": _rr.get("band_zh"),
            "reco_why_en": th.get("reco_why_en"),
            "reco_why_zh": th.get("reco_why_zh"),
            "rs_pctile": th.get("rs_pctile"),
            "flip_distance": _fd.get("route_b_pp"),
        }

        # --- us_sector_* go to sector_overlay, NOT into narrative rows ---
        if tid.startswith("us_sector_"):
            spdr = _slug_to_spdr.get(tid)
            if not spdr:
                continue   # unknown slug — skip gracefully
            # Determine which lane this reco WOULD have mapped to (used for ew_lane)
            if reco in ("accumulate", "enter"):
                ew_lane = "buy_now" if (reco == "accumulate" and ce_flag) else (
                          "buy_soon" if (reco == "enter" and ce_flag) else "on_the_run")
            else:
                ew_lane = reduce_bucket.get(reco, "avoid")
            buckets["sector_overlay"][spdr] = dict(base_item, ew_lane=ew_lane)
            continue

        # --- Narrative (non-us_sector_*) themes: route by reco + clean_entry ---
        if reco in ("accumulate", "enter"):
            if reco == "accumulate" and ce_flag:
                bkt = "buy_now"
            elif reco == "enter" and ce_flag:
                bkt = "buy_soon"
            else:
                # In favour but no clean-entry setup — don't chase, add on pullback
                bkt = "on_the_run"
                quality_pct = (
                    round(ce_quality * 100) if ce_quality is not None else None
                )
                # Carry a short reason for the template to surface
                base_item["run_reason_en"] = (
                    "In favour but no clean-entry setup — add on pullback"
                    + (f"; entry quality {quality_pct}%" if quality_pct is not None else "")
                )
                base_item["run_reason_zh"] = (
                    "顺势但无干净入场机会 — 等回调加仓"
                    + (f"；入场质量 {quality_pct}%" if quality_pct is not None else "")
                )
        else:
            bkt = reduce_bucket.get(reco)
            if not bkt:
                continue

        buckets[bkt].append(base_item)

    buckets["buy_now"].sort(key=lambda x: -(x.get("score") or 0))   # leaders first
    buckets["buy_soon"].sort(key=lambda x: -(x.get("score") or 0))
    buckets["on_the_run"].sort(key=lambda x: -(x.get("score") or 0))
    buckets["take_profits"].sort(key=lambda x: (x.get("score") or 0))  # weakest first
    buckets["avoid"].sort(key=lambda x: (x.get("score") or 0))
    for k in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"):
        buckets[k] = buckets[k][:8]
    return buckets


# US sector ETFs each have a dedicated equal-weight sector page under basket/; map the SPDR
# ticker → that page so dashboard sector affordances open it instead of the legacy
# sectors/<TICKER>.html drill-down. Mirrors US_SECTOR_PAGE in site/sector_cycles.js.
US_SECTOR_PAGE = {
    "XLK": "basket/us_sector_tech.html",
    "XLC": "basket/us_sector_comm.html",
    "XLY": "basket/us_sector_discretionary.html",
    "XLF": "basket/us_sector_financials.html",
    "XLI": "basket/us_sector_industrials.html",
    "XLB": "basket/us_sector_materials.html",
    "XLE": "basket/us_sector_energy.html",
    "XLV": "basket/us_sector_health.html",
    "XLP": "basket/us_sector_staples.html",
    "XLU": "basket/us_sector_utilities.html",
    "XLRE": "basket/us_sector_realestate.html",
}


def _action_board_stat_chip(lane: str, e: dict, item: dict) -> None:
    """Attach stat_en / stat_zh / chip_en / chip_zh / chip_tone to *item* in-place.

    Ruling: BOTTOMING·WAIT belongs in Almost ready — 2026-07-10 us_stocks scorecard
    adjudication. Conservative de-escalation-safe defaults throughout.
    All strings are QUALIFIER-FIRST so truncation never eats the honest half (<= 30 EN).
    """
    tag = e.get("tag", "")
    age_short = item.get("age_short") or ""
    age_short_zh = item.get("age_short_zh") or ""
    days = e.get("days_hi")
    gate_override = item.get("gate_override", False)
    urgency = e.get("urgency", "")

    # stat_en / stat_zh
    if lane == "buy_now":
        stat_en = f"clean entry · {age_short}" if age_short else "clean entry"
        stat_zh = f"入场干净 · {age_short_zh}" if age_short_zh else "入场干净"
    elif lane == "buy_soon":
        # lane_hint=buy_soon items are WAIT demotions (BOTTOMING·EXTENDED or UNCONFIRMED)
        if tag in ("BOTTOMING · EXTENDED — WAIT",):
            stat_en = "extended — wait"
            stat_zh = "已过热 — 等待"
        elif tag == "BOTTOMING · UNCONFIRMED — WAIT":
            stat_en = "unconfirmed — wait"
            stat_zh = "未确认 — 等待"
        elif days is not None:
            stat_en = f"trigger ~{days}d"
            stat_zh = f"触发约{days}日"
        else:
            stat_en = "unconfirmed — wait"
            stat_zh = "未确认 — 等待"
    elif lane == "on_the_run":
        stat_en = "extended · wait for pullback"
        stat_zh = "已延伸 · 等回调"
    elif lane == "take_profits":
        if gate_override:
            stat_en = "backtested gate: trim"
            stat_zh = "回测门槛：减仓"
        elif urgency == "exit":
            stat_en = "momentum rolled over"
            stat_zh = "动量掉头"
        else:
            stat_en = f"late cycle · {age_short}" if age_short else "late cycle"
            stat_zh = f"周期晚期 · {age_short_zh}" if age_short_zh else "周期晚期"
    elif lane == "hold":
        stat_en = "uptrend intact"
        stat_zh = "趋势完好"
    else:  # avoid
        if tag == "WAIT":
            stat_en = "wait for a new setup"
            stat_zh = "等待新形态"
        else:
            stat_en = "downtrend"
            stat_zh = "下跌趋势"

    item["stat_en"] = stat_en
    item["stat_zh"] = stat_zh

    # chip_en / chip_zh / chip_tone (at most one chip; gate ✓ added by template from gate_override)
    # Priority: WAIT demotions first, then HALF SIZE, then lane-specific, then days, then empty.
    if lane == "buy_soon" and tag in ("BOTTOMING · EXTENDED — WAIT",
                                      "BOTTOMING · UNCONFIRMED — WAIT"):
        chip_en, chip_zh, chip_tone = "WAIT", "等待", "warn"
    elif tag == "HALF SIZE":
        chip_en, chip_zh, chip_tone = "HALF SIZE", "半仓", "pos"
    elif lane == "hold":
        chip_en, chip_zh, chip_tone = "HOLD", "持有", "muted"
    elif lane == "avoid":
        if tag == "WAIT":
            chip_en, chip_zh, chip_tone = "WAIT", "等待", "warn"
        else:
            chip_en, chip_zh, chip_tone = "AVOID", "回避", "neg"
    elif lane == "buy_soon" and days is not None:
        chip_en, chip_zh, chip_tone = f"~{days}d", f"约{days}日", "info"
    else:
        chip_en, chip_zh, chip_tone = "", "", ""

    item["chip_en"] = chip_en
    item["chip_zh"] = chip_zh
    item["chip_tone"] = chip_tone

    # text_zh (additive alongside existing text)
    item["text_zh"] = e.get("text_zh", "")


def action_board(sector_timing: dict, notable: list[dict],
                 basket_items: dict | None = None,
                 sector_setup_lookup: dict | None = None) -> dict:
    """Bucket sector + narrative-basket + standout-stock cycle signals into an at-a-glance
    'what to act on now' board. Sectors and baskets are UNIFIED (each item carries
    kind='sector'|'theme' + an href) so the board acts on narrative resolution, not just the
    11 GICS sectors.

    Urgency routing (ratified — 2026-07-10 us_stocks scorecard adjudication):
      now → buy_now; imminent/soon → buy_soon; hold → hold; exit → take_profits;
      caution: lane_hint key consulted FIRST (engine/cycles.py sets it on every caution entry);
        lane_hint wins when it names a valid lane; fallback (no hint) by exact tag:
          "DON'T CHASE"            → on_the_run   (uptrend intact, extended)
          "UNCONFIRMED — HIGH RISK" → avoid        (bear-trend bounce)
          "TAKE PROFITS"            → take_profits
          unknown/missing           → hold         (conservative de-escalation-safe default)
      all other urgency values → avoid.

    EW overlay attach: if sector_overlay carries the SPDR ticker, attach item["ew"] + ew_lane.
    Reduce-side override (the one backtested drawdown-control edge): if overlay reco is
    trim/avoid and the cycle lane is buy_now/buy_soon/on_the_run/hold, the row is MOVED to
    take_profits or avoid respectively (gate_override=True so the template can badge ✓).

    sector_setup_lookup: optional dict keyed by SPDR ticker → sector_setup row dict.
    When provided, per-ticker setup fields (rs_60d, above200, above50, rsi_3d, stoch_3d,
    rate_str, rate_pos, season_str, season_tip) are merged onto each sector action_board item
    for the conditions popover. Additive; missing keys silently skipped."""
    from engine.playbook import SECTOR_NAMES
    buy_now, buy_soon, on_the_run, take_profits, hold, avoid = [], [], [], [], [], []

    # sector_overlay comes from basket_action_items(); keyed by SPDR ticker
    sector_overlay = (basket_items or {}).get("sector_overlay") or {}
    _setup_lk = sector_setup_lookup or {}

    _BUY_LANES = {"buy_now", "buy_soon", "on_the_run", "hold"}
    _VALID_LANES = {"buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"}

    for fund, tm in sector_timing.items():
        e = tm.get("entry") or {}
        tag = e.get("tag", "")
        item = {"ticker": fund, "name": SECTOR_NAMES.get(fund, fund),
                "kind": "sector", "href": US_SECTOR_PAGE.get(fund, "sectors/" + fund + ".html"),
                "label": tm["label"], "tag": tag,
                "text": e.get("text", ""), "days": e.get("days_hi"),
                "age_short": tm.get("age_short"), "age_short_zh": tm.get("age_short_zh"),
                "eq_badge": tm.get("eq_badge"), "eq_dir": tm.get("eq_dir"),
                "eq_tip": tm.get("eq_tip"), "eq_tip_zh": tm.get("eq_tip_zh"), "style": tm.get("state_style"),
                # cycle position + holdings context for conditions popover
                "dc_day": tm.get("dc_day"),
                "buy_zone": tm.get("buy_zone"), "n_holdings": tm.get("n_holdings")}
        # Merge sector_setup confluence fields (rs_60d, oscillators, base rates, seasonality)
        _su = _setup_lk.get(fund)
        if _su:
            item["rs_60d"] = _su.get("rs_60d")
            item["above200"] = _su.get("above200")
            item["above50"] = _su.get("above50")
            item["rsi_3d"] = _su.get("rsi_3d")
            item["stoch_3d"] = _su.get("stoch_3d")
            item["rate_str"] = _su.get("rate_str")
            item["rate_pos"] = _su.get("rate_pos")
            item["season_str"] = _su.get("season_str")
            item["season_tip"] = _su.get("season_tip")
        u = e.get("urgency")
        # Determine the cycle-timing lane.
        # caution: lane_hint FIRST; fallback to exact-tag switch; unknown → hold (safe default).
        if u == "now":
            cycle_lane = "buy_now"
        elif u in ("imminent", "soon"):
            cycle_lane = "buy_soon"
        elif u == "hold":
            cycle_lane = "hold"
        elif u == "exit":
            cycle_lane = "take_profits"
        elif u == "caution":
            hint = e.get("lane_hint", "")
            if hint in _VALID_LANES:
                cycle_lane = hint
            elif tag == "DON'T CHASE":
                cycle_lane = "on_the_run"
            elif tag == "UNCONFIRMED — HIGH RISK":
                cycle_lane = "avoid"
            elif tag == "TAKE PROFITS":
                cycle_lane = "take_profits"
            else:
                cycle_lane = "hold"   # conservative de-escalation-safe default
        else:
            cycle_lane = "avoid"

        # Attach EW overlay when available
        ov = sector_overlay.get(fund)
        if ov:
            item["ew"] = ov
            item["ew_lane"] = ov.get("ew_lane")

        # Reduce-side override: the backtested drawdown-control edge may not be hidden
        # behind a constructive cycle read.
        final_lane = cycle_lane
        if ov:
            ov_reco = (ov.get("reco") or "").lower()
            if ov_reco == "trim" and cycle_lane in _BUY_LANES:
                final_lane = "take_profits"
                item["gate_override"] = True
            elif ov_reco == "avoid" and cycle_lane in _BUY_LANES:
                final_lane = "avoid"
                item["gate_override"] = True

        # Attach stat/chip display fields and text_zh per contract
        _action_board_stat_chip(final_lane, e, item)

        if final_lane == "buy_now":
            buy_now.append(item)
        elif final_lane == "buy_soon":
            buy_soon.append(item)
        elif final_lane == "on_the_run":
            on_the_run.append(item)
        elif final_lane == "take_profits":
            take_profits.append(item)
        elif final_lane == "hold":
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
        # The urgency TIER is the cycle-timing read (risk placement). WITHIN a tier we
        # order buys by the validated selection leg — sector-neutral momentum α — not
        # the blended setup score: Phase-0 (reports/setup-score-phase0.md) showed the
        # timing blend does NOT improve forward-return ranking (it dilutes α). Sells
        # keep the cycle sell-conviction (α is not a sell signal). asc sort throughout.
        if n.get("urgency") == "exit":
            return n.get("eq_score") or 0               # most-negative (strongest sell) first
        az = n.get("alpha_z")
        if az is not None:
            return -az                                  # highest α (strongest leader) first
        return -(n.get("eq_score") or 0)                # no α: fall back to cycle conviction

    def _rank(n):
        # α (selection) leads within the cycle tier; the factor composite breaks
        # near-ties only (a crowded/decayed leg — settle ties, never drive the order).
        return (order.get(n["urgency"], 9), _decis(n),
                -(n.get("factor_z") or 0.0),
                n.get("age_days") if n.get("age_days") is not None else 999,
                n["days"] if n.get("days") is not None else 99)

    from engine.setups import norm_company

    # A soft per-sector cap keeps one hot sector (e.g. all of XLK in a tech rip) from
    # crowding out the board — the best names per sector fill first, then any spare
    # slots backfill from the overflow (already in rank order). Dual-class listings
    # (GOOG + GOOGL) are collapsed to the best-ranked variant.
    # CAP generous so the standout strip's "show more" can reveal a deep bench; the
    # per-sector cap still shapes the diverse top-of-list that's visible by default.
    CAP, FLOOR, PER_SECTOR = 60, 15, 5
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
    # UNIFY: narrative baskets lead each lane (the resolution the user acts on), GICS
    # sectors follow. on_the_run: basket rows first (same 🧩-then-🏛 pattern), then sectors.
    bi = basket_items or {}
    return {"buy_now": (bi.get("buy_now") or []) + buy_now,
            "buy_soon": (bi.get("buy_soon") or []) + buy_soon,
            "on_the_run": (bi.get("on_the_run") or []) + on_the_run,
            "take_profits": (bi.get("take_profits") or []) + take_profits,
            "hold": (bi.get("hold") or []) + hold,
            "avoid": (bi.get("avoid") or []) + avoid,
            "notable": notable_clean[:CAP]}


def sector_setup_view(latest: dict, timing: dict | None = None) -> dict | None:
    """The Sector Confluence board — the PRIMARY buy/sell setup engine
    (engine.sector_signals): a confluence of MACD + StochRSI crossovers on the
    3-day chart, daily-triggered and 200-day-gated, with extended = avoid. Replaces
    the old "leaders/avoid" scorecard + heat board (research/SECTOR_CONFLUENCE.md).

    Reads the sector + SPY closes from the parquet store, runs the engine, refreshes
    the per-state base rates live (the honesty layer), and folds in the still-useful
    columns (seasonality, 3-mo RS, trend) — seasonality reuses the existing rich
    tooltip already computed on the playbook stages. Display strings are composed
    here so the template stays attribute-safe. Additive; None on any shortfall."""
    from engine import sector_signals as ssig
    from engine.playbook import SECTOR_NAMES
    try:
        sectors = config.load()["yahoo"]["tickers"]["sectors"]
        ydir = config.data_dir() / "yahoo"
        cols = {}
        for t in sectors + ["SPY"]:
            p = ydir / f"{t}.parquet"
            if p.exists():
                cols[t] = pd.read_parquet(p)["close"]
        if "SPY" not in cols:
            return None
        closes = pd.DataFrame(cols).sort_index()
        disl = latest.get("dislocation") or {}
        put_absent = disl.get("put_state") == "put-absent"
        bd = ssig.board(closes, SECTOR_NAMES, sectors, spy=closes["SPY"], put_absent=put_absent)
        if not bd.get("sectors"):
            return None
        # live-measured base rates (overrides the static defaults so the displayed
        # numbers always match the live rule); fall back to the engine's documented
        # rates on any shortfall.
        try:
            cal = ssig.calibrate(closes, sectors, closes["SPY"])
        except Exception:  # noqa: BLE001 — calibration is the honesty extra, never fatal
            cal = {}
        stages = {s["ticker"]: s for s in ((latest.get("playbook") or {}).get("stages") or [])}
        month = pd.Timestamp(latest["date"]).month if latest.get("date") else None
        for r in bd["sectors"]:
            r["href"] = US_SECTOR_PAGE.get(r["ticker"], "sectors/" + r["ticker"] + ".html")
            st = stages.get(r["ticker"], {})
            r["verdict"] = T(r["label"], r["label_zh"])
            r["action_txt"] = T(r["action"], r["action_zh"])
            r["signal_txt"] = T(ssig.signal_line(r), ssig.signal_line(r, zh=True))
            r["conv_dots"] = ("●" * max(1, min(r["conviction"], 3))) if r["side"] != "neutral" else "·"
            r["conv_txt"] = T(r["conviction_label"], r["conviction_label_zh"])
            r["tech_str"] = f"{'✓' if r['above200'] else '✗'}200d {'✓' if r['above50'] else '✗'}50d"
            r["tech_ok"] = bool(r["above200"] and r["above50"])
            r["osc_str"] = (f"RSI {r['rsi_3d']:.0f} · Stoch {r['stoch_3d']:.0f}"
                            if r.get("rsi_3d") is not None and r.get("stoch_3d") is not None else "—")
            r["rs_str"] = f"{r['rs_60d']:+.1f}%" if r.get("rs_60d") is not None else "—"
            br = cal.get(r["state"]) or r.get("base_rate") or {}
            if br and r["side"] == "tactical" and br.get("abs63") is not None:
                # tactical oversold-bounce: lead with the ABSOLUTE bounce (the reason
                # it's surfaced), show excess-vs-SPY beside it as the honest cost.
                n = br.get("n"); nbit = f" · n={n}" if n else ""
                r["rate_str"] = T(f"{br['abs63']:+.1f}% abs · {br['abs_hit']}% up | {br['exc63']:+.1f}% vs SPY{nbit}",
                                  f"绝对 {br['abs63']:+.1f}% · {br['abs_hit']}% 上涨 | 对SPY {br['exc63']:+.1f}%{nbit}")
                r["rate_pos"] = None     # mixed read — keep the cell neutral, not green
            elif br:
                n = br.get("n")
                nbit = f" · n={n}" if n else ""
                r["rate_str"] = T(f"{br['exc63']:+.1f}% vs SPY · {br['hit']}% up{nbit}",
                                  f"对SPY {br['exc63']:+.1f}% · {br['hit']}% 上涨{nbit}")
                r["rate_pos"] = br["exc63"] >= 0
            else:
                r["rate_str"], r["rate_pos"] = T("—", "—"), None
            r["season_str"], _ = _compact_season(st.get("season_this"))
            r["season_tip"] = _season_tooltip(st.get("season_all"), st.get("season_month") or month)
            # TS-R6 two-reads reconciliation chip: when this ETF's setup-side verdict
            # (3D tactical) conflicts with the cycle timing action (slow, cap-weighted).
            # Fired when: setup side = BUY/SETUP/BUY_PARTIAL (entry-ready) AND cycle
            # timing maps to take_profits or avoid (TAKE PROFITS / exit urgency).
            r["two_reads_chip"] = None
            if timing and r.get("side") == "buy":
                tm = timing.get(r["ticker"]) or {}
                e = tm.get("entry") or {}
                u = e.get("urgency", "")
                tag = e.get("tag", "")
                cycle_label = tm.get("label", "")
                # Cycle is on the reduce side when urgency=exit, OR when caution routes
                # to take_profits (any caution tag except DON'T CHASE / UNCONFIRMED —
                # HIGH RISK, which route to on_the_run / avoid respectively).
                # Mirrors action_board routing exactly (A3 fix).
                _CAUTION_NON_REDUCE = {"DON'T CHASE", "UNCONFIRMED — HIGH RISK"}
                cycle_is_reduce = (u == "exit") or (
                    u == "caution" and tag not in _CAUTION_NON_REDUCE
                )
                if cycle_is_reduce:
                    from engine.cycles import STATE_DISPLAY as _SD
                    # ZH map mirrors ENTRY_STATUS_ZH in templates/dashboard.html.j2 ~6891-6896
                    # plus 'setup' and 'partial' keys used by the setup-side vocab.
                    _SETUP_ZH = {
                        "buy_now": "立即买入", "partial": "半仓",
                        "buy_soon": "即将买入", "setup": "构筑中",
                        "extended": "过热", "watch": "观察",
                        "avoid": "回避", "topping": "做顶",
                        "blocked": "封锁", "exit": "退出",
                    }
                    setup_label = r.get("label") or r.get("label_zh") or r["state"]
                    state_key = r.get("state", "")
                    cycle_label_zh = _SD.get(
                        tm.get("state", ""), {}
                    ).get("label_zh", cycle_label)
                    setup_label_zh = _SETUP_ZH.get(r.get("state", ""), setup_label)
                    r["two_reads_chip"] = {
                        "cycle_label_en": cycle_label,
                        "setup_label_en": setup_label,
                        "setup_state": state_key,
                        "cycle_label_zh": cycle_label_zh,
                        "setup_label_zh": setup_label_zh,
                    }
        return bd
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("sector setup view failed: %s", e)
        return None


def _vol_shock_view(latest: dict, event_risk: dict | None) -> dict | None:
    """Forward Vol-Shock Risk gauge (engine.vol_shock_scorecard) for the front of the
    macro page. Re-derives the pure snapshot with the already-built event_risk snapshot
    injected (adds the event-proximity leg's days-to) and attaches the forward-outcome
    track record so the card can print its measured hit-rate. Display-only; never fatal."""
    try:
        from engine import vol_shock_scorecard as vss
        snap = vss.snapshot(latest, event_risk=event_risk)
        if snap is None:
            return None
        snap["track_record"] = vss.track_record()
        return snap
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("vol-shock view failed (%s)", e)
        return None


def _fear_greed_view() -> dict | None:
    """Load the Fear/Greed composite from site/basketdata/fear_greed.json (written by
    build_theme_addons, which runs in the same daily pipeline). Falls back to computing
    directly when the JSON is absent (e.g. first-run order). Display-only; never fatal."""
    try:
        site_dir = config.ROOT / config.load()["storage"]["site_dir"]
        p = site_dir / "basketdata" / "fear_greed.json"
        if p.exists():
            return json.loads(p.read_text())
        # fallback: compute live (slower but always correct)
        from engine.fear_greed import compute_fear_greed
        return compute_fear_greed()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("fear_greed view failed (%s)", e)
        return None


def _vol_weather_view() -> dict | None:
    """Load vol weather chips from site/basketdata/vol_weather.json (written by
    build_theme_addons). JSON-or-None only — never falls back to compute.
    Display-only; never fatal."""
    try:
        site_dir = config.ROOT / config.load()["storage"]["site_dir"]
        p = site_dir / "basketdata" / "vol_weather.json"
        if p.exists():
            return json.loads(p.read_text())
        return None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("vol_weather view failed (%s)", e)
        return None


def _breadth_split_view() -> dict | None:
    """Load AI vs non-AI breadth split from site/basketdata/breadth_split.json
    (written by build_theme_addons). JSON-or-None only — never falls back to compute.
    Display-only; never fatal."""
    try:
        site_dir = config.ROOT / config.load()["storage"]["site_dir"]
        p = site_dir / "basketdata" / "breadth_split.json"
        if p.exists():
            return json.loads(p.read_text())
        return None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("breadth_split view failed (%s)", e)
        return None


def _froth_fragility_view(latest: dict) -> dict | None:
    """Froth & Fragility gauge (engine.froth_fragility) for the macro page: retail
    euphoria + hidden-distribution top-risk, with the forward-outcome track record
    attached. Display-only; never fatal."""
    try:
        from engine import froth_fragility as ff
        snap = ff.snapshot(latest)
        if snap is None:
            return None
        snap["track_record"] = ff.track_record()
        return snap
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("froth-fragility view failed (%s)", e)
        return None


def _leadership_board_view() -> dict | None:
    """Assemble the MLC-W1 Leadership Board payload (display-only, MLC-R2).

    Joins three sources — all DISPLAY-ONLY; no new scoring/ranking math:
      1. data/mag7_regime/latest.json   — M7C cohort state + per-member fields
      2. data/leader_radar/state_history.parquet — LRV lifecycle state per name
      3. data/earnings/earnings.parquet — next_date / as_of for earnings chip (MLC-R10)
      4. site/sectordata/sector_central.json — sector RS ranks (momentum.rs_rank/lead)

    Returns None on any hard failure (panel fails open / silent).
    Individual per-name fields are None when absent (Jinja guards handle nulls).
    Never raises — additive, display-tier, never fatal to the build.
    """
    try:
        import datetime

        # ── 1. M7C cohort payload (required: if absent, skip whole panel) ────────
        m7_path = config.data_dir() / "mag7_regime" / "latest.json"
        if not m7_path.exists():
            return None
        m7 = json.loads(m7_path.read_text(encoding="utf-8"))
        if not m7.get("trend_state"):
            return None  # degraded artifact

        M7_SYMS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

        # ── 2. LRV lifecycle states (optional — fail-open per name) ─────────────
        lifecycle_by_sym: dict[str, str] = {}
        try:
            import pandas as pd
            lp = config.data_dir() / "leader_radar" / "state_history.parquet"
            if lp.exists():
                ldf = pd.read_parquet(lp)
                # latest row per ticker (parquet is date-sorted; last wins)
                for sym in M7_SYMS:
                    rows = ldf[ldf["ticker"] == sym]
                    if not rows.empty:
                        lifecycle_by_sym[sym] = str(rows.iloc[-1]["confirmed_state"])
        except Exception as _le:  # noqa: BLE001
            log.warning("leadership_board: lifecycle load failed (%s)", _le)

        # ── 3. Earnings chip (MLC-R10: disclosure only, not a gate) ─────────────
        earnings_by_sym: dict[str, dict] = {}
        try:
            import pandas as pd
            ep = config.data_dir() / "earnings" / "earnings.parquet"
            if ep.exists():
                edf = pd.read_parquet(ep)
                today = datetime.date.today()
                for sym in M7_SYMS:
                    if sym not in edf.index:
                        continue
                    row = edf.loc[sym]
                    nd = row.get("next_date")
                    ao = row.get("as_of")
                    if pd.isna(nd) or nd is None:
                        continue
                    # as_of freshness gate: stale store must not show wrong dates
                    if ao is not None and not pd.isna(ao):
                        try:
                            ao_str = str(ao)[:10]  # ISO date prefix
                            ao_date = datetime.date.fromisoformat(ao_str)
                            stale = (today - ao_date).days > 7
                        except Exception:  # noqa: BLE001
                            stale = True
                    else:
                        stale = True
                    if stale:
                        continue
                    try:
                        next_dt = datetime.date.fromisoformat(str(nd)[:10])
                        days_until = (next_dt - today).days
                        if 0 <= days_until <= 14:
                            earnings_by_sym[sym] = {
                                "next_date": str(nd)[:10],
                                "days_until": days_until,
                            }
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as _ee:  # noqa: BLE001
            log.warning("leadership_board: earnings load failed (%s)", _ee)

        # ── 4. Sector RS strip from sector_central.json (already written) ────────
        sector_rs: list[dict] = []
        try:
            _cfg_paths = config.load().get("paths", {})
            sc_path = Path(_cfg_paths.get("site", "site")) / "sectordata" / "sector_central.json"
            if not sc_path.exists():
                # fallback: resolve relative to repo root
                sc_path = Path(__file__).parent.parent / "site" / "sectordata" / "sector_central.json"
            if sc_path.exists():
                sc_doc = json.loads(sc_path.read_text(encoding="utf-8"))
                raw_sectors = sc_doc.get("sectors") or []
                for sec in raw_sectors:
                    mom = sec.get("momentum") or {}
                    rr = mom.get("rs_rank")
                    lead = mom.get("lead")
                    if rr is None:
                        continue  # skip if rank absent
                    sector_rs.append({
                        "ticker": sec.get("ticker", ""),
                        "name": sec.get("name", ""),
                        "name_zh": sec.get("name_zh", ""),
                        "rs_rank": rr,
                        "lead": lead,  # "leading" / "mid-pack" / "lagging"
                        "conviction_en": (sec.get("conviction") or {}).get("label_en"),
                        "conviction_zh": (sec.get("conviction") or {}).get("label_zh"),
                    })
                sector_rs.sort(key=lambda x: x["rs_rank"])
        except Exception as _se:  # noqa: BLE001
            log.warning("leadership_board: sector RS load failed (%s)", _se)

        # ── 5. Enrich per-member tiles with lifecycle + earnings ─────────────────
        members_out = []
        for m in (m7.get("members") or []):
            sym = m.get("sym", "")
            lifecycle = lifecycle_by_sym.get(sym)  # None if absent
            earn = earnings_by_sym.get(sym)         # None if absent / stale / >14d
            members_out.append({**m, "lifecycle": lifecycle, "earnings": earn})

        return {
            "as_of": m7.get("as_of"),
            "trend_state": m7.get("trend_state"),
            "run": m7.get("run") or {},
            "generals": m7.get("generals") or {},
            "k7": m7.get("k7") or {},
            "cw": m7.get("cw") or {},
            "ew": m7.get("ew") or {},
            "members": members_out,
            "sector_rs": sector_rs,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("leadership_board_view failed (%s)", e)
        return None


def _mag7_regime_view() -> dict | None:
    """Load the Mag 7 regime artifact (data/mag7_regime/latest.json) for the
    us_stocks panel.  DISPLAY-ONLY; cap-weighted context read, not a scored signal.
    Written by the engine lane (engine/mag7_regime.py); may be absent on first run.
    Never raises — the panel fails open when the artifact is absent."""
    try:
        p = config.data_dir() / "mag7_regime" / "latest.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d.get("trend_state"):
            return None  # degraded artifact — don't show the panel
        return d
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("mag7_regime_view failed (%s)", e)
        return None


def _dispersion_regime_view() -> dict | None:
    """Load the L3 dispersion regime artifact (data/dispersion/regime.json) for the
    macro page selection-regime chip.  DISPLAY-ONLY; gross_mult_live is always 1.0 per
    NW Rails W2 PR-4 §5 hard constraint.  Never raises."""
    try:
        p = config.data_dir() / "dispersion" / "regime.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        if d.get("state") is None:
            return None  # degraded artifact — don't show the chip
        return d
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("dispersion_regime_view failed (%s)", e)
        return None


def _flip_confirmation_view() -> dict | None:
    """T+1 sector-flip confirmation lens snapshot (Policy-Shock W1-C).

    Reads engine.flip_confirmation.snapshot() — the detect-since-2024 descriptive
    scan plus the last flip event with T+1 verdict.  DISPLAY-ONLY; never scored.
    Returns None (never raises) so the card is hidden when data is unavailable.
    """
    try:
        from engine import flip_confirmation as _fc
        snap = _fc.snapshot()
        if not snap or snap.get("error") or not snap.get("last_event"):
            return None
        return snap
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("flip_confirmation_view failed (%s)", e)
        return None


def _sector_heat_view() -> dict | None:
    """Compact sector-heat strip for the macro.html dashboard: up to 4 heating themes
    and up to 4 cooling/broken themes, each with a link to baskets.html#theme-<id>.
    DISPLAY-ONLY — data comes from engine.sector_pulse.build_pulse('us') at build time.
    Returns None (never raises) so the strip is simply hidden when pulse is unavailable."""
    try:
        from engine.sector_pulse import build_pulse as _sp_build
        pulse = _sp_build("us")
        if not pulse:
            return None
        themes = pulse.get("themes") or []
        heating = [t for t in themes if t.get("heat") in ("heating", "hot")][:4]
        cooling = [t for t in themes if t.get("heat") in ("cooling", "broken")][:4]
        if not heating and not cooling:
            return None
        def _row(t):
            return {
                "id": t.get("id"),
                "name": t.get("name"),
                "name_zh": t.get("name_zh"),
                "heat": t.get("heat"),
                "rank": t.get("rank"),
                "rank_delta_5d": t.get("rank_delta_5d"),
                "label": t.get("label"),
                "reco": t.get("reco"),
            }
        return {
            "as_of": pulse.get("as_of"),
            "heating": [_row(t) for t in heating],
            "cooling": [_row(t) for t in cooling],
        }
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("sector_heat_view failed (%s)", e)
        return None


def _policy_lever_view() -> dict | None:
    """Load the policy-lever ARMED/QUIET card artifact (site/policy_lever.json).

    Written nightly by scripts/build_policy_lever.py (Policy-Shock W2-F).
    Display/context tier only (PS-R3): never feeds scoring.
    Returns None (never raises) if the artifact is absent or malformed.
    """
    try:
        p = config.ROOT / config.load().get("storage", {}).get("site_dir", "site") / "policy_lever.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("schema") != "policy_lever.v1":
            return None
        return d
    except Exception as e:  # noqa: BLE001 — additive / display-only, never fatal
        log.warning("policy_lever_view failed (%s)", e)
        return None


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
    the stock's cycle state attached. See engine/holdings_signals.py.

    Uses ``top_sector_residuals`` (the strongest residual movers, no alert gate) so
    the panel is always populated — on passive SPDRs the residual is tiny by
    construction and the thresholded list is almost always empty."""
    from engine.holdings_signals import top_sector_residuals
    from engine.playbook import SECTOR_NAMES
    n = config.load()["holdings_signals"].get("panel_top_n", 12)
    rows = []
    for s in top_sector_residuals(n):
        rows.append({
            "fund": s["fund"], "sector": SECTOR_NAMES.get(s["fund"], s["fund"]),
            "ticker": s["ticker"], "name": s["name"],
            "raw_change": s["raw_change"], "active_change": s["active_change"],
            "active_pct": s["active_pct"],
            "flow_str": _fmt_money_mn(s["est_flow_mn"]) if s.get("est_flow_mn") is not None else "—",
            "flow_mn": s["est_flow_mn"] if s.get("est_flow_mn") is not None else None,
            "direction": s["direction"], "confirmed": s["confirmed"],
            "ladder": s["ladder"], "window": f"{s['t0']}..{s['t1']}"})
    return rows


# --- Fear <-> Euphoria regime synthesis (DISPLAY-ONLY) -----------------------
# Maps the already-computed RORO risk-on/off composite (engine.conditions) to a
# rolling-5y 0-100 Fear<->Euphoria percentile, decomposes its 7 signed legs, and
# annotates whether positioning (COT spec + insider Form-4 breadth) confirms or
# diverges from price. This is a CONDITIONING LENS, NEVER a scored leg: it is
# read only as a render kwarg on the macro dashboard, and nothing in
# axes/regime/macro_risk reads any of it. See research/FEAR_EUPHORIA_PANEL_SPEC.md.
_FE_LEG_META = [
    ("vix", "VIX", "波动率 VIX"),
    ("hy_oas", "HY credit spread", "高收益信用利差"),
    ("skew", "SKEW (tail pricing)", "SKEW 尾部定价"),
    ("vix_term", "VIX term structure", "VIX 期限结构"),
    ("nfci", "Financial conditions (NFCI)", "金融条件 NFCI"),
    ("copper_gold", "Copper/Gold", "铜／金 比"),
    ("dxy", "Dollar (20d %Δ)", "美元（20日 %变动）"),
]


def _last_finite(s: pd.Series) -> float | None:
    """Latest finite value of a series (drops trailing NaN), else None."""
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _fe_map(pct: float) -> int:
    """Map a [0,1] percentile to a clamped 0-100 integer Fear<->Euphoria score."""
    return int(max(0, min(100, round(100 * float(pct)))))


def _fe_band(fe: int) -> str:
    """Half-open band for a 0-100 score: panic<10 / fear<35 / neutral<65 /
    greed<90 / euphoria>=90. Returns the canonical English key."""
    if fe < 10:
        return "Panic"
    if fe < 35:
        return "Fear"
    if fe < 65:
        return "Neutral"
    if fe < 90:
        return "Greed"
    return "Euphoria"


def _fe_insider_breadth(sig: dict) -> float:
    """Net Form-4 buy breadth across the insider-signals map: (#net-buyers -
    #net-sellers) / #valid using the per-ticker `bps` field (% of mktcap). None /
    non-finite bps are ignored; an empty / all-None map returns 0.0 (no crash)."""
    vals = [v["bps"] for v in sig.values()
            if v.get("bps") is not None and np.isfinite(v["bps"])]
    if not vals:
        return 0.0
    return (sum(b > 0 for b in vals) - sum(b < 0 for b in vals)) / len(vals)


def _fe_chip(cot_washed_out: bool, cot_crowded_long: bool,
             insider_buying: bool, insider_selling: bool,
             price_up: bool) -> tuple[str, str]:
    """Deterministic positioning-vs-price read (no scorer). Returns
    (chip, smart_money_lean). Descriptive only — never a buy/sell call."""
    bullish = cot_washed_out or insider_buying
    bearish = cot_crowded_long or insider_selling
    lean = ("bullish" if (bullish and not bearish)
            else "bearish" if (bearish and not bullish) else "mixed")
    chip = ("mixed" if lean == "mixed"
            else "confirms" if (lean == "bullish") == price_up else "diverges")
    return chip, lean


def _fe_legs(cf: pd.DataFrame) -> list[dict]:
    """Per-leg decomposition of the RORO composite from the signed roro_<key>
    columns: latest signed contribution, its rolling-5y percentile, and a
    risk-on/risk-off lean (hyphenated to match the i18n LEX so td() resolves it)."""
    from engine.indicators import pct_rank_window
    legs = []
    for key, en, zh in _FE_LEG_META:
        col = f"roro_{key}"
        if col not in cf.columns:
            continue
        sig = cf[col]
        val = _last_finite(sig)
        if val is None:
            continue
        p = _last_finite(pct_rank_window(sig, 252 * 5))
        if p is None:                                  # warm-up shortfall fallback
            p = _last_finite(sig.expanding(min_periods=20).rank(pct=True))
        legs.append({
            "key": key, "name_en": en, "name_zh": zh,
            "value": round(val, 3),
            "pct": _fe_map(p) if p is not None else 50,
            "lean": "risk-on" if val > 0 else "risk-off"})
    return legs


def _roro_confirmation(legs: list[dict]) -> dict | None:
    """DISPLAY-ONLY cross-asset confirmation tally over the signed RORO legs.

    Reuses _fe_legs (each leg's risk-on-positive contribution + lean): counts how
    many of the cross-asset legs agree on the dominant risk direction RIGHT NOW and
    grades the agreement (clean / not-clean / divergent). This is the dispersion the
    headline RORO mean HIDES — a 5-of-7 split and a unanimous read can average to the
    same number; this shows which it is. Majority-anchored so it reads in either
    regime. NEVER scored; never feeds axes / regime / macro_risk.
    """
    if not legs:
        return None
    on = [lg for lg in legs if lg["lean"] == "risk-on"]
    off = [lg for lg in legs if lg["lean"] == "risk-off"]
    n_on, n_off, total = len(on), len(off), len(legs)
    if n_on > n_off:
        direction, dir_zh, majority, minority = "risk-on", "偏好风险", on, off
    elif n_off > n_on:
        direction, dir_zh, majority, minority = "risk-off", "避险", off, on
    else:
        direction, dir_zh, majority, minority = "split", "对半分歧", on, off
    agree = len(majority)
    ratio = agree / total
    if direction == "split":
        verdict_en, verdict_zh = "divergent (split)", "背离（对半）"
    elif ratio >= 0.85:                       # ~6-7 of 7 aligned
        verdict_en, verdict_zh = "clean " + direction, "一致" + dir_zh
    elif ratio >= 0.70:                       # ~5 of 7 — constructive but not clean
        verdict_en, verdict_zh = direction + ", not clean", dir_zh + "（不一致）"
    else:                                     # ~4 of 7 — no real consensus
        verdict_en, verdict_zh = "divergent (no consensus)", "背离（无共识）"

    def _lab(xs: list[dict]) -> list[dict]:
        return [{"key": lg["key"], "en": lg["name_en"], "zh": lg["name_zh"]} for lg in xs]

    return {
        "n_on": n_on, "n_off": n_off, "total": total, "agree": agree,
        "direction": direction,
        "confirmed_by": _lab(majority), "dissent": _lab(minority),
        "verdict_en": verdict_en, "verdict_zh": verdict_zh,
    }


def _fe_positioning(latest: dict, f: pd.DataFrame) -> dict:
    """Positioning confirms/diverges read from US-macro inputs ONLY (no China/HK
    southbound): COT spec washout/crowding (recomputed — the boolean is not
    persisted, mirrors conditions.py) + insider Form-4 breadth, vs price trend."""
    from engine.indicators import pct_rank_window
    ccfg = config.load()["engine"]["conditions"]["capitulation"]
    cot_washed_out = cot_crowded_long = False
    cot = store.read("cot", "cot_es_spx")
    if cot is not None and "net_spec_pct_oi" in cot.columns:
        ns = cot["net_spec_pct_oi"].reindex(f.index).ffill(limit=10)
        p = _last_finite(pct_rank_window(ns, ccfg["cot_pctile_lookback_d"]))
        if p is not None:
            cot_washed_out = p < ccfg["cot_washout_pctile"]
            cot_crowded_long = p > 1 - ccfg["cot_washout_pctile"]
    sig = {}
    ip = (config.ROOT / config.load()["storage"]["site_dir"]
          / "factordata" / "insider_signals.json")
    if ip.exists():
        try:
            sig = json.loads(ip.read_text()) or {}
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("insider signals unreadable for fear/euphoria (%s)", e)
    breadth = _fe_insider_breadth(sig)
    insider_buying, insider_selling = breadth > 0.05, breadth < -0.05
    price_up = (((latest.get("dislocation") or {}).get("inputs") or {})
                .get("primary_trend") == "up")
    chip, lean = _fe_chip(cot_washed_out, cot_crowded_long,
                          insider_buying, insider_selling, price_up)
    return {"chip": chip, "smart_money_lean": lean,
            "cot_washed_out": cot_washed_out, "cot_crowded_long": cot_crowded_long,
            "insider_breadth": round(breadth, 3), "price_up": price_up}


def fear_euphoria_synthesis(latest: dict, f: pd.DataFrame) -> dict | None:
    """DISPLAY-ONLY Fear<->Euphoria regime synthesis. Zero new data: maps the
    existing RORO composite to a rolling-5y 0-100 percentile, decomposes its 7
    legs, annotates positioning confirms/diverges. NEVER scores; NEVER touches
    axes / regime / macro_risk. Returns None gracefully on any shortfall (the
    2023+ price cache can hold fewer obs than the rolling window's min_periods)."""
    from engine.conditions import conditions_frame
    from engine.indicators import pct_rank_window
    try:
        cf = conditions_frame(f)
        if "roro" not in cf or cf["roro"].dropna().empty:
            return None
        pct = _last_finite(pct_rank_window(cf["roro"], 252 * 5))
        if pct is None or not np.isfinite(pct):            # shallow-cache guard
            return None
        fe = _fe_map(pct)
        RA = (latest.get("conditions") or {}).get("risk_appetite") or {}
        legs = _fe_legs(cf)
        return {"fe_score": fe, "band": _fe_band(fe),
                "roro": RA.get("roro"), "roro_state": RA.get("roro_state"),
                "legs": legs, "confirmation": _roro_confirmation(legs),
                "positioning": _fe_positioning(latest, f)}
    except Exception as e:  # noqa: BLE001 — additive panel, never fatal
        log.warning("fear/euphoria synthesis failed: %s", e)
        return None


def regime_snap_view(cf: pd.DataFrame) -> dict | None:
    """DISPLAY-ONLY relief-radar card payload: wraps engine.regime_snap.snap_snapshot
    (the VELOCITY complement to the Fear<->Euphoria LEVEL read) and adds the
    display-derived status, gate flags and localized leg names. Zero new data, never
    scored — a render kwarg only. Verified COINCIDENT (~base-rate forward returns) so
    it is an ATTENTION radar, not a buy signal. None on shortfall (never fatal)."""
    try:
        from engine import regime_snap
        snap = regime_snap.snap_snapshot(cf)
        if snap is None:
            return None
        c = regime_snap._cfg()
        vp = snap.get("vel_pctile") or 0.0
        if snap["snap"]:
            snap["status"] = "firing"
        elif vp >= c["vel_min_pctile"] and snap["legs_up"] >= 2:
            snap["status"] = "building"          # thrust underway, full gate not met
        else:
            snap["status"] = "dormant"
        snap["gates"] = {
            "velocity": vp >= c["vel_min_pctile"],
            "legs": snap["legs_up"] >= c["min_legs"],
            "fear": (snap.get("fear_built") or 0.0) >= c["fear_min"],
            "washout": bool(snap.get("cap_recent")),
        }
        snap["min_legs"] = int(c["min_legs"])
        meta = {k: (en, zh) for k, en, zh in _FE_LEG_META}
        snap["flipped_legs_named"] = [
            {"key": k, "en": meta.get(k, (k, k))[0], "zh": meta.get(k, (k, k))[1]}
            for k in snap.get("flipped_legs", [])]
        rm = snap.get("relief_magnitude")
        snap["magnitude_band"] = (None if rm is None
                                  else "large" if rm >= 70 else "moderate" if rm >= 40 else "small")
        return snap
    except Exception as e:  # noqa: BLE001 — additive panel, never fatal
        log.warning("regime-snap view failed: %s", e)
        return None


def market_state_view(latest: dict, f: pd.DataFrame) -> dict | None:
    """DISPLAY-ONLY 'what kind of market is this?' command-center payload: wraps
    engine.market_state.market_state_snapshot, blending the index multi-timeframe
    tape (read off the in-memory feature frame) with the live cross-asset / vol /
    breadth / liquidity / downturn-risk legs into a 0-100 risk-on score and a
    Green/Yellow/Red verdict. Zero new data, never scored. None on shortfall."""
    try:
        from engine import market_state as _ms
        snap = _ms.market_state_snapshot(latest, f, latest.get("alerts") or [])
        if snap:
            # Self-auditing forward-outcome log (engine/market_state_audit.py): log today's
            # verdict, grade matured entries vs realized SPY, and attach the scorecard
            # (incl. per-corroborator precision) so the amplification is accountable and
            # the weak corroborators can be measured + pruned over time. Never fatal.
            try:
                from engine import market_state_audit as _msa
                snap["audit"] = _msa.snapshot_and_grade(snap)
                # Bounded, do-no-harm auto-calibration (engine/market_state_tune.py): once
                # enough calls are graded, re-weight / prune the corroborators from their
                # measured forward lift. Writes the overlay the engine reads NEXT build, so
                # it never feeds back into the verdict just rendered. Gated + never fatal.
                from engine import market_state_tune as _mst
                snap["audit"]["tune"] = _mst.tune()
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.warning("market_state audit/tune failed: %s", e)
            # Persist the canonical verdict so sector_central + the intraday live engine
            # consume the SAME radar-aware read (single source of truth). Never fatal.
            _ms.persist(snap)
        return snap
    except Exception as e:  # noqa: BLE001 — additive panel, never fatal
        log.warning("market_state view failed: %s", e)
        return None


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
    try:
        from engine.etf_consensus import consensus_favored, fund_coverage, attach_trajectories
        attach_trajectories(split["accumulation"],
                            cap=config.load()["etf_holdings"].get("sparkline_cap", 60))
        attach_trajectories(split["trims"],
                            cap=config.load()["etf_holdings"].get("sparkline_cap", 60))
        favored = consensus_favored(rows)
        coverage = fund_coverage()
    except Exception as e:  # noqa: BLE001 — consensus/coverage are additive, never fatal
        log.error("etf consensus/coverage failed: %s", e)
        favored, coverage = [], []
    html = env.get_template("etfs.html.j2").render(
        accumulation=split["accumulation"], trims=split["trims"],
        favored=favored, coverage=coverage, generated_utc=generated)
    write_page(site / "etfs.html", html)
    # per-stock feed (built before the stock library so it can be attached there)
    outdir = site / "stockdata"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "fund_flows.json").write_text(
        json.dumps(_fund_flows_by_ticker(rows), separators=(",", ":"), default=str))
    log.info("wrote etfs.html (%d accumulation, %d trims) + fund_flows.json (%d names)",
             len(split["accumulation"]), len(split["trims"]),
             len({r["ticker"] for r in rows}))


_IC_LABELS = {
    "value": "Value", "profitability": "Profitability", "quality": "Quality",
    "investment": "Investment", "payout": "Payout", "low_vol": "Low volatility",
    "low_beta": "Low beta", "accruals": "Accruals", "short_interest": "Low short interest",
    "composite": "Composite", "composite_orth": "Composite (de-correlated)",
}


def _load_ic_scorecard() -> dict | None:
    """Load the leak-free point-in-time IC scorecard (scripts.factor_ic_scorecard
    writes data/edgar/ic_scorecard.json) for the factors page. This is the rigor
    FactorWatch and most factor dashboards never show — IC + Newey-West t + BH-FDR.
    Degrade-never-raise: missing/unreadable/stale → return None and the panel hides.
    Read straight from the JSON; do NOT fork a slice into factors.json."""
    p = config.data_dir() / "edgar" / "ic_scorecard.json"
    if not p.exists():
        return None
    try:
        ic = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("ic scorecard unreadable: %s", e)
        return None
    facs = ic.get("factors") or {}
    if not facs:
        return None
    rows = [{"factor": k, "label_en": _IC_LABELS.get(k, k), **v} for k, v in facs.items()]
    # mirror the report's order: best forward-IC information ratio first
    rows.sort(key=lambda r: -(r["ic_ir_ann"] if r.get("ic_ir_ann") is not None else -9))
    ic["rows"] = rows
    ic["any_survive"] = any(r.get("survives_fdr") for r in rows)
    return ic


def _load_breadth() -> dict | None:
    """MARKET breadth context for the factors page — % of members above their 50d and
    200d MAs across the S&P 500 / 400 / 600 caps (data/<grp>/breadth.parquet). This is
    INDEX-member breadth, not factor-portfolio breadth. Degrade-never-raise."""
    import pandas as _pd
    groups = [("Large cap (S&P 500)", "大盘 (标普500)", "breadth"),
              ("Mid cap (S&P 400)", "中盘 (标普400)", "midcap_breadth"),
              ("Small cap (S&P 600)", "小盘 (标普600)", "smallcap_breadth")]
    rows, by, as_of = [], {}, None
    for label_en, label_zh, g in groups:
        p = config.data_dir() / g / "breadth.parquet"
        if not p.exists():
            continue
        try:
            df = _pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            continue
        if df.empty or "pct_above_50" not in df.columns:
            continue
        last = df.iloc[-1]
        r = {"label_en": label_en, "label_zh": label_zh, "group": g,
             "p50": round(float(last["pct_above_50"]), 1),
             "p200": round(float(last["pct_above_200"]), 1),
             "n": int(last.get("n_members", 0) or 0)}
        rows.append(r)
        by[g] = r
        as_of = df.index.max().strftime("%Y-%m-%d")
    if not rows:
        return None
    # small-vs-large divergence on the COMMON window (small/mid only start 2023-07)
    div = (round(by["smallcap_breadth"]["p50"] - by["breadth"]["p50"], 1)
           if "smallcap_breadth" in by and "breadth" in by else None)
    return {"groups": rows, "div_small_large": div, "as_of": as_of}


def _load_factor_series() -> dict | None:
    """Load factor portfolio return series (scripts.build_factor_series writes
    site/factordata/factor_series.json — the heavier month-end walk). Degrade-never-raise."""
    p = config.ROOT / "site" / "factordata" / "factor_series.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        return d if d.get("factors") else None
    except Exception as e:  # noqa: BLE001
        log.warning("factor series unreadable: %s", e)
        return None


def _load_nw_factor_state() -> dict | None:
    """Load the Neural Web factor intelligence state artifact (RUL-NW7/NW8, §D PR-4).

    Reads data/neuralweb/factor_intelligence_state.json (committed artifact written by
    the factor_panel job via scripts/build_factor_intelligence_state.py, RUL-NW1).
    Fail-open: absent → None, template renders a DORMANT panel with an honest note.
    Never raises; never imports engine modules.

    Declared consumer in config/synapse.yml → factor-intelligence-state (RUL-NW11).
    """
    p = config.ROOT / "data" / "neuralweb" / "factor_intelligence_state.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return None
        return d
    except Exception as e:  # noqa: BLE001
        log.warning("nw factor state unreadable: %s", e)
        return None


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
            # Regenerate the PIT per-transaction panel concat (insider_panel.parquet,
            # gitignored) from the COMMITTED per-quarter cache so the size-normalised
            # leaderboard / per-stock chip get the trailing-window + distinct-insider
            # CLUSTER construction (research/INSIDER_FACTOR.md). Guarded to the existing
            # cache: never triggers a cold 2006→ full fetch in CI — only a regen plus a
            # probe for any newly-published quarter. Falls back to the quarterly
            # aggregate (size-normalised too) if the panel is unavailable.
            pdir = config.data_dir() / "sec_insider" / "panel"
            if pdir.exists() and any(pdir.glob("*.parquet")):
                from collectors.sec_insider import backfill_panel
                backfill_panel()
        except Exception as e:  # noqa: BLE001 — panel is optional; leaderboard degrades gracefully
            log.warning("sec insider panel refresh failed: %s", e)
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
    ic = _load_ic_scorecard()                  # leak-free point-in-time IC (degrade-never-raise)
    breadth = _load_breadth()                  # market-member breadth context (degrade-never-raise)
    series = _load_factor_series()             # factor portfolio return series (degrade-never-raise)
    nw_state = _load_nw_factor_state()         # NW factor intelligence state (RUL-NW7/NW8, fail-open)
    html = env.get_template("factors.html.j2").render(
        fac=fac, ic=ic, breadth=breadth, series=series,
        nw_state=nw_state, generated_utc=generated)
    write_page(site / "factors.html", html)
    log.info("wrote factors.html (%d names, FY%s, ic=%s, nw_state=%s)", fac.get("n"), fac.get("fy"),
             "yes" if ic else "no", "yes" if nw_state else "no")
    return fac


def build_signal_lab_page(env: Environment, site: Path, generated: str) -> None:
    """🔬 Signal Lab — the consolidated, honest validation scorecard.

    Pure assembler over engine.signal_lab (curated report verdicts + the live
    leak-free factor cross-section in data/edgar/ic_scorecard.json). Surfaces
    the IC / HAC-t / FDR-q / Deflated-Sharpe that already exist but are buried
    in reports/ — including the signals we measured and refused to ship.
    Additive + graceful: never fatal to the build.
    """
    from engine import signal_lab
    payload = signal_lab.build_scorecard()
    payload["generated_utc"] = generated     # align with the rest of the site
    html = env.get_template("signal_lab.html.j2").render(**payload)
    write_page(site / "signal_lab.html", html)
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "signal_lab.json").write_text(
        json.dumps(payload, separators=(",", ":"), default=str))
    log.info("wrote signal_lab.html (%d signals, %d/%d factors survive FDR)",
             payload["summary"]["total"], payload["summary"]["factor_survivors"],
             payload["summary"]["factor_total"])


def build_alerts_page(env: Environment, site: Path, generated: str) -> None:
    """🚨 Alert Command Center — the honest triage board over every alert engine.

    Pure assembler over engine.alert_triage: pulls the recent macro / cross-asset
    feeds into one ranked board with a transparent priority, a TRUE cross-asset
    conviction tier, the regime/event backdrop, and a measured-edge column that
    shows a hit-rate / Deflated-Sharpe ONLY where Signal Lab validated the family.
    Additive + graceful: never fatal to the build.
    """
    from engine import alert_triage
    payload = alert_triage.build_triage()
    payload["generated_utc"] = generated     # align with the rest of the site
    html = env.get_template("alerts.html.j2").render(**payload)
    write_page(site / "alerts.html", html)
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "alerts_triage.json").write_text(
        json.dumps(payload, separators=(",", ":"), default=str))
    # Machine-readable feed for the admin Alerts capture tab (RUL-8: auth-only
    # consumption; no public write endpoint).  One record per deduplicated alert
    # with stable content-hash IDs and just the fields the capture tab needs.
    adir = site / "alertsdata"
    adir.mkdir(parents=True, exist_ok=True)
    feed_records = [
        {
            "alert_id": a["alert_id"],
            "emit_ts": a["ts"],
            "title": a.get("headline", ""),
            "surface": f"{a['source']}:{a['type']}",
            "severity": a["severity"],
            "tier": a["tier"],
            "priority": a["priority"],
            "source": a["source"],
        }
        for a in payload.get("alerts", [])
    ]
    (adir / "feed.json").write_text(
        json.dumps({"generated_utc": generated, "alerts": feed_records},
                   separators=(",", ":"), default=str))
    s = payload["summary"]
    log.info("wrote alerts.html (%d alerts: %d critical / %d major / %d actionable, "
             "%d with measured edge)", s["total"], s["critical"], s["major"],
             s["actionable"], s["backtested"])


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


def _attention_z(views: pd.Series, z_window: int = 90, recent_d: int = 5) -> float | None:
    """Causal robust abnormal-attention z: trailing-5d log-views mean vs a
    median/MAD baseline over the STRICTLY-PRIOR z_window (so a single anomalous day
    can't dominate, and there is no look-ahead). Pageview counts are heavily
    right-skewed -> log1p + median/MAD. Clipped to [-3, +6] for display."""
    s = np.log1p(views.dropna().astype(float))
    if len(s) < z_window // 2 + recent_d:
        return None
    recent = float(s.iloc[-recent_d:].mean())
    base = s.iloc[-(z_window + recent_d):-recent_d].dropna()   # strictly prior -> causal
    if len(base) < 20:
        return None
    med = float(base.median())
    mad = float((base - med).abs().median())
    scale = 1.4826 * mad if mad > 0 else float(base.std() or 0.0)
    if not scale:
        return None
    return float(np.clip((recent - med) / scale, -3.0, 6.0))


def build_attention_data(site: Path) -> dict | None:
    """Per-ticker abnormal-attention z from offshore (en.wikipedia.org) pageviews ->
    factordata/attention.json: a DISPLAY-ONLY over-extension / fade-risk caution chip
    (Da-Engelberg-Gao: attention -> short-horizon reversal). Mirrors
    build_insider_data: additive + graceful, returns/writes nothing if the attention
    store is absent. NEVER a scored leg — not wired into axes / top_picks / setups."""
    adir = config.data_dir() / "attention"
    if not adir.exists():
        return None
    cfg = config.load().get("wiki_pageviews", {})
    zw = cfg.get("z_window", 90)
    out: dict = {}
    try:
        for p in sorted(adir.glob("*.parquet")):
            df = pd.read_parquet(p)
            if "views" not in df.columns or df.empty:
                continue
            v = df["views"].dropna()
            z = _attention_z(v, zw)
            if z is None:
                continue
            out[p.stem] = {"z": round(z, 2), "views": int(v.iloc[-1]),
                           "asof": str(pd.Timestamp(v.index.max()).date())}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("attention data failed: %s", e)
        return None
    if not out:
        return None
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "attention.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
    log.info("wrote attention.json (%d names with offshore-attention z)", len(out))
    return out


def build_smartmoney_data(site: Path) -> dict | None:
    """Compute curated super-investor 13F holdings and write
    factordata/smartmoney.json (consumed by the per-stock "who holds this" panel +
    a future consensus board). Additive — any failure logs and skips. CONTEXT only,
    never wired into any score. See collectors/edgar_13f.py + engine/smart_money.py."""
    from engine.smart_money import compute_smart_money, enrich_since_filing
    try:
        sm = compute_smart_money()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("smart-money engine failed: %s", e)
        return None
    if not sm:
        return None
    # Attach realized price-since-filing context (DESCRIPTIVE, not a score/signal).
    # Best-effort: any failure is silently skipped per-ticker and never blocks the build.
    try:
        enrich_since_filing(sm.get("by_ticker") or {})
    except Exception as e:  # noqa: BLE001 — enrichment is additive only
        log.warning("since-filing enrichment failed (non-fatal): %s", e)
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "smartmoney.json").write_text(json.dumps(sm, separators=(",", ":"), default=str))
    log.info("wrote smartmoney.json (%d funds, %d names)", sm.get("n_funds"), sm.get("n_names"))
    return sm


# --------------------------------------------------------------------------- #
# W3-C4b — dollar-desk lean → DISPLAY-ONLY sector context chip (masterplan §5 C4b)
# --------------------------------------------------------------------------- #
# The forex Dollar Desk computes a full broad-dollar LEAN (real-rate regime + trend stack +
# liquidity + Fed path) → data/forex/latest.json. It was DISPLAY-only with no consumer
# (INTL-45). C4b surfaces it as an honest CONTEXT headwind/tailwind chip on the US
# cyclical/small-cap-relevant sector surfaces (sector.html). It is DISPLAY-ONLY and
# UNVALIDATED for sizing — the forex 60-trial family found NO per-pair dollar conviction
# that clears DSR (INTL-43), so this never touches basket_score.py or any scored leg. The
# ONLY dollar factor that cleared a gate is c4_reer_value (the N=1 REER value factor), and
# even that is not wired to a scorer. This chip is a mechanism read, not a sizing input.
#
# Sectors whose earnings are most dollar-sensitive: multinational/export/commodity-heavy
# cyclicals (a STRONG dollar = a HEADWIND via cheaper commodities + FX-translation drag on
# overseas revenue). Direction is stated as a mechanism, not a measured coefficient.
_DOLLAR_SENSITIVE_SECTORS = {
    # fund: (EN sensitivity note, ZH note) — the mechanism, not a validated coefficient
    "XLE": ("energy — commodities priced in USD; a strong dollar caps oil/gas realizations",
            "能源 —— 大宗商品以美元计价；强美元压制油气变现"),
    "XLB": ("materials — global commodity revenue; a strong dollar is a translation + demand headwind",
            "原材料 —— 全球大宗商品收入；强美元带来折算与需求逆风"),
    "XLI": ("industrials — heavy overseas/export revenue; a strong dollar drags FX-translated sales",
            "工业 —— 海外/出口收入占比高；强美元拖累外币折算销售"),
    "XLK": ("technology — large overseas revenue mix; a strong dollar is a translation headwind",
            "科技 —— 海外收入占比高；强美元带来折算逆风"),
}


def _dollar_context(site: Path, fund: str) -> dict | None:
    """DISPLAY-ONLY dollar-desk context chip for a dollar-sensitive US sector (W3-C4b).
    Reads the MEASURED broad-dollar lean from data/forex/latest.json and returns a bilingual
    headwind/tailwind chip dict, or None (fail-soft) for a non-sensitive sector or missing
    data. NEVER a scored input — labeled context/unvalidated-for-sizing on the page."""
    note = _DOLLAR_SENSITIVE_SECTORS.get(fund)
    if note is None:
        return None
    try:
        p = config.data_dir() / "forex" / "latest.json"
        if not p.exists():
            return None
        dd = (json.loads(p.read_text()) or {}).get("dollar_desk") or {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("dollar-context read failed (%s)", e)
        return None
    lean = dd.get("lean")
    if not lean:
        return None
    net = dd.get("lean_net")
    # a dollar-SUPPORTIVE backdrop (net > 0) = HEADWIND for these dollar-sensitive cyclicals;
    # dollar-SOFT (net < 0) = TAILWIND. Mixed/none = neutral context. Direction is the
    # MECHANISM (strong USD hurts multinational/commodity revenue), never a measured coefficient.
    if isinstance(net, (int, float)) and net >= 2:
        tone, arrow = "headwind", "▼"
        en = "Dollar headwind"; zh = "美元逆风"
    elif isinstance(net, (int, float)) and net <= -2:
        tone, arrow = "tailwind", "▲"
        en = "Dollar tailwind"; zh = "美元顺风"
    else:
        tone, arrow = "neutral", "◇"
        en = "Dollar mixed"; zh = "美元分化"
    return {
        "tone": tone, "arrow": arrow, "chip_en": en, "chip_zh": zh,
        "lean_en": lean, "lean_zh": dd.get("lean_zh") or lean,
        "note_en": note[0], "note_zh": note[1],
    }


def build_sector_pages(env: Environment, site: Path, generated: str,
                       alpha: dict | None = None, put_absent: bool = False,
                       rate_infl: dict | None = None) -> dict:
    """Render sectors/<FUND>.html drill-downs; return per-fund timing summary
    for the heat board. ``rate_infl`` maps fund -> the display-only per-sector
    rate/inflation transmission read (engine.sector_rate_inflation), reused from the
    already-computed playbook stages so it is the single source of truth."""
    import json as _json

    from collectors.sector_holdings import latest_fundamentals, latest_top10
    from engine.conditions import sector_macro_beta
    from engine import ticker_alerts
    from engine.cycles import LADDER, STATE_DISPLAY, analyze
    from engine.holdings_signals import accumulation_signals
    from engine.playbook import SECTOR_NAMES
    from engine.setups import US_ALPHA_WEIGHT, sue_confirmer, timing_tilt
    from scripts.build_stock_library import current_liquidity, current_macro

    # per-ticker sector-neutral residual alpha (already computed by build_alpha_data
    # and passed in) — used to enrich the front-page "Standout individual stocks"
    # cards with an alpha sector rank + reversal overlay and an alpha-aware setup
    # score (selection × timing). Absent => cards fall back to pure cycle timing.
    alpha_pt = (alpha or {}).get("per_ticker", {})
    # confirmer legs on those same cards: a distinct-insider Form-4 BUY cluster
    # (insider_signals.json, written by build_insider_data just above), the cross-
    # sectional factor composite (factors.json table) as a light tiebreaker, and the
    # validated SUE earnings-momentum z (factors.json table 'sue') as an earnings-
    # drift confirmer. All additive + graceful — absent => the card omits that chip.
    # None of these enter the setup score; they are displayed risk/conviction context.
    insider_map: dict[str, dict] = {}
    factor_z: dict[str, float] = {}
    sue_z: dict[str, float] = {}
    try:
        _ip = site / "factordata" / "insider_signals.json"
        if _ip.exists():
            insider_map = json.loads(_ip.read_text()) or {}
        _fp = site / "factordata" / "factors.json"
        if _fp.exists():
            for _r in (json.loads(_fp.read_text()) or {}).get("table", []):
                if not _r.get("ticker"):
                    continue
                # audit #25: tiebreak on the scorecard-passing rank composite, not the blind
                # equal-weight composite (which its own scorecard grades anti-predictive).
                _cz = _r.get("composite_rank")
                if _cz is None:
                    _cz = _r.get("composite")
                if _cz is not None:
                    factor_z[_r["ticker"]] = _cz
                if _r.get("sue") is not None:
                    sue_z[_r["ticker"]] = _r["sue"]
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
    # Policy-shock de-escalation state (PS-R3: display de-escalation only — no sizing/reordering)
    _shock_path = site / "live" / "shock_state.json"
    _shock_state: dict | None = None
    try:
        if _shock_path.exists():
            import json as _jsss
            _shock_state = _jsss.loads(_shock_path.read_text())
    except Exception as _sse:  # noqa: BLE001 — additive, never fatal
        log.warning("shock_state unavailable for sector pages (%s)", _sse)

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
                    # buying, Form-4 6mo) + the factor composite (light tiebreaker) +
                    # the SUE earnings-momentum z (gated to a real positive tailwind).
                    # All DISPLAY context — none touch the setup score above.
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
                                    "sue_z": sue_confirmer(sue_z.get(tick)),
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
             "rate_infl": (rate_infl or {}).get(fund),  # display-only macro overlay
             "dollar_ctx": _dollar_context(site, fund),  # W3-C4b display-only dollar-lean chip
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
        # validated confluence verdict (the same engine that drives the main-dashboard
        # Sector buy/sell setups board) — engine/sector_signals
        try:
            from engine import sector_signals as _ssig
            sig = _ssig.sector_signal(ec, SECTOR_NAMES.get(fund, fund), spy_close=_bench,
                                      ticker=fund, put_absent=put_absent)
            if sig.get("ok"):
                sig["signal_en"] = _ssig.signal_line(sig)
                sig["signal_zh"] = _ssig.signal_line(sig, zh=True)
            s["confluence"] = sig
        except Exception as _e:  # noqa: BLE001 — additive, never fatal
            log.error("sector confluence (%s) failed: %s", fund, _e)
            s["confluence"] = None
        feed = ticker_alerts.build_feed(
            fund, ec, etf.get("high"), _bench, res.get("ladder"),
            str(ec.index.max().date()), days=_adays, max_events=_amax)
        html = tpl.render(s=s, state_styles=STATE_STYLES, calibration=calibration,
                          ladder_order=LADDER, state_display=STATE_DISPLAY,
                          alerts=feed, generated_utc=generated,
                          shock_state=_shock_state)
        write_page(outdir / f"{fund}.html", html)
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
    write_page(site / "advanced.html", html)
    log.info("wrote advanced.html (%.0f KB)", (site / "advanced.html").stat().st_size / 1024)
    return cross_asset


def index_health_rows() -> list[dict]:
    """Health snapshot for the four major US indexes — the 'how is the market
    itself doing' read that leads the macro page (people open it for the index
    first, the economy second). Price, % off the 52-week high (drawdown), 50/200d
    trend, RSI(14). Pure price math off the stored daily closes; reuses
    engine.technicals.rsi."""
    from engine.technicals import rsi
    out = []
    for tkr, label, zh in [("SPY", "S&P 500", "标普500"), ("QQQ", "Nasdaq 100", "纳指100"),
                           ("_DJI", "Dow Jones", "道指"), ("_RUT", "Russell 2000", "罗素2000")]:
        df = store.read("yahoo", tkr)
        if df is None or df.empty or "close" not in df.columns:
            continue
        c = df["close"].astype(float).dropna()
        if len(c) < 60:
            continue
        px = float(c.iloc[-1])
        hi52 = float(c.tail(252).max())
        ma50 = float(c.tail(50).mean())
        ma200 = float(c.tail(200).mean()) if len(c) >= 200 else float("nan")
        try:
            r = float(rsi(c).iloc[-1])
        except Exception:  # noqa: BLE001 — never let one index break the panel
            r = float("nan")
        out.append({
            "ticker": tkr, "label": label, "label_zh": zh, "price": round(px, 2),
            "chg": round(100 * (px / float(c.iloc[-2]) - 1), 2) if len(c) >= 2 else 0.0,
            "dd": round(100 * (px / hi52 - 1), 1),
            "above50": bool(px >= ma50),
            "above200": (bool(px >= ma200) if ma200 == ma200 else None),
            "rsi": round(r) if r == r else None,
        })
    return out


def alloc_card_state() -> dict:
    """The S&P Vector allocation snapshot for the macro page's allocation CTA card.
    Best-effort: degrades to a present=False stub (CTA only, no live numbers) when
    build_spvector hasn't run yet — so build order never breaks the macro page."""
    try:
        d = json.loads((config.data_dir() / "regime" / "spvector_latest.json").read_text())
        d["present"] = True
        return d
    except Exception:  # noqa: BLE001 — additive, never fatal
        return {"present": False}


def _ms_history_view() -> list[dict] | None:
    """Last up-to-60 sessions from market_state/forward_log.jsonl.
    Returns list of {asof, score} dicts (de-duped by asof, keep last), or None
    when the file is absent/unreadable.  Graceful — never fatal."""
    try:
        p = config.data_dir() / "market_state" / "forward_log.jsonl"
        if not p.exists():
            return None
        rows: dict[str, int] = {}
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                asof = obj.get("asof")
                score = obj.get("score")
                if asof and score is not None:
                    rows[asof] = int(score)
            except Exception:  # noqa: BLE001
                continue
        if not rows:
            return None
        ordered = sorted(rows.items())[-60:]
        return [{"asof": k, "score": v} for k, v in ordered]
    except Exception:  # noqa: BLE001 — additive, never fatal
        return None


def _idx_spark_view() -> dict | None:
    """Last 20 daily closes for SPY/QQQ/^DJI/^RUT from the price store.
    Re-uses the same store.read() loader as index_health_rows.
    Returns {ticker: [float, ...]} or None on total failure."""
    tickers = [("SPY", "SPY"), ("QQQ", "QQQ"), ("_DJI", "^DJI"), ("_RUT", "^RUT")]
    out: dict[str, list[float]] = {}
    try:
        for store_key, out_key in tickers:
            try:
                df = store.read("yahoo", store_key)
                if df is None or df.empty or "close" not in df.columns:
                    continue
                c = df["close"].astype(float).dropna().tail(20)
                if len(c) < 2:
                    continue
                out[out_key] = [float(v) for v in c]
            except Exception:  # noqa: BLE001 — one ticker failure skips that tile only
                continue
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return out if out else None


# Index drawdown/risk MODEL integrated onto the macro page (the predictive layer
# from the S&P Vector engine — the allocation STRATEGY itself lives on spvector.html).
_RISK_LEG_COLORS = {"drawdown": "#e07070", "recession": "#e0a030", "nfci": "#9b8de0",
                    "hy_widening": "#d98c00", "liquidity": "#7aa7e0"}
_RISK_LEG_ZH = {"drawdown": "宏观压力回撤计", "recession": "衰退风险",
                "nfci": "金融条件（紧且收紧）", "hy_widening": "信用压力（高收益利差走阔）",
                "liquidity": "净流动性收缩"}
_RISK_LEG_ORDER = ["drawdown", "recession", "hy_widening", "nfci", "liquidity"]


def risk_model_view(f: pd.DataFrame, regime, cf: pd.DataFrame) -> dict:
    """The S&P Vector de-risk SCORE + its per-leg breakdown, for the macro page's
    integrated 'index risk model' read. Reuses engine.equity_alloc.risk_legs (each
    leg's 0-100 intensity, weight, publication lag, and points-contribution that
    sum to the composite). Degrades to {} if the engine can't compute."""
    try:
        from engine import equity_alloc as ea
        rl = ea.risk_legs(f, regime, cf)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("risk_model_view failed (%s)", e)
        return {}
    sc = rl["score"].dropna()
    if sc.empty:
        return {}
    score = round(float(sc.iloc[-1]))
    legs = []
    order = _RISK_LEG_ORDER + [n for n in rl["legs"] if n not in _RISK_LEG_ORDER]
    for n in order:
        lg = rl["legs"].get(n)
        if not lg:
            continue
        legs.append({"key": n, "label": lg["label"], "label_zh": _RISK_LEG_ZH.get(n, lg["label"]),
                     "value": lg["value"], "points": lg["points"], "weight": lg["weight"],
                     "lag": lg["lag"], "active": lg["active"],
                     "color": _RISK_LEG_COLORS.get(n, "#888")})
    band = ("low" if score < 25 else "elevated" if score < 50 else "high" if score < 75 else "extreme")
    return {"score": score, "legs": legs, "band": band}


def chart_risk_model(cf: pd.DataFrame) -> str:
    """The index drawdown-risk + recession-risk MODELS over ~25y, with NBER
    recessions shaded — the 'predict index drawdown / recession risk through a model'
    chart, integrated onto the macro page. Both are 0-100 composite gauges from
    engine.conditions; band lines mark the elevated/high thresholds."""
    start = cf.index.max() - pd.Timedelta(days=365 * 25)
    # weekly resolution — multi-decade context charts; visually identical at this zoom
    # and ~5x lighter on the page (macro.html weight discipline, [[plotly-chart-size-gotcha]]).
    dr = cf.loc[start:, "drawdown_risk"].dropna().resample("W-FRI").last().dropna().round(1)
    rr = cf.loc[start:, "recession_risk"].dropna().resample("W-FRI").last().dropna().round(1)
    fig = go.Figure()
    rec = store.read("fred", "USRECD")
    if rec is not None and not rec.empty:
        on = (rec[rec.columns[0]] > 0.5)
        on = on[on.index >= start]
        if on.any():
            seg = (on != on.shift()).cumsum()
            for _, g in on[on].groupby(seg[on]):
                fig.add_vrect(x0=g.index.min(), x1=g.index.max(),
                              fillcolor="#8b93a1", opacity=0.16, line_width=0)
    # NB: use reds/ambers OUTSIDE the chart_i18n.js swap map ({#e07070,#d04545}↔green)
    # so a RISK gauge stays red in zh mode (risk ≠ price direction — must not flip green).
    fig.add_trace(go.Scatter(x=dr.index, y=dr, name="Index drawdown-risk model",
                             line={"color": "#de5d5d", "width": 1.4}))
    fig.add_trace(go.Scatter(x=rr.index, y=rr, name="Recession-risk model",
                             line={"color": "#e0a030", "width": 1.2}))
    fig.add_hline(y=80, line={"color": "#de5d5d", "width": 0.5, "dash": "dot"})
    fig.add_hline(y=60, line={"color": "#e0a030", "width": 0.5, "dash": "dot"})
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_yaxes(range=[0, 100], autorange=False)
    _apply_range(fig, has_legend=True, height=320)
    return _html(fig)


def chart_curve(cf: pd.DataFrame) -> str:
    """Yield curve: the 2s10s slope RAW vs TERM-PREMIUM-ADJUSTED, ~25y, NBER-shaded.
    Inversion (below 0) is the classic recession lead; the TP-adjusted line strips
    the term premium so a low-TP flattening isn't misread as a recession signal
    (it's why 2022-24's raw inversion didn't fire the composite). Colours sit
    outside the zh swap map (a curve isn't a price-direction read)."""
    start = cf.index.max() - pd.Timedelta(days=365 * 25)
    raw = cf.loc[start:, "curve_raw"].dropna().resample("W-FRI").last().dropna().round(2)
    adj = cf.loc[start:, "curve_tp_adj"].dropna().resample("W-FRI").last().dropna().round(2)
    fig = go.Figure()
    rec = store.read("fred", "USRECD")
    if rec is not None and not rec.empty:
        on = (rec[rec.columns[0]] > 0.5)
        on = on[on.index >= start]
        if on.any():
            seg = (on != on.shift()).cumsum()
            for _, g in on[on].groupby(seg[on]):
                fig.add_vrect(x0=g.index.min(), x1=g.index.max(),
                              fillcolor="#8b93a1", opacity=0.16, line_width=0)
    fig.add_trace(go.Scatter(x=raw.index, y=raw, name="2s10s (raw)",
                             line={"color": "#7aa7e0", "width": 1.3}))
    fig.add_trace(go.Scatter(x=adj.index, y=adj, name="2s10s (term-premium adj.)",
                             line={"color": "#c08af0", "width": 1.3}))
    fig.add_hline(y=0, line={"color": "#9aa4b2", "width": 0.8, "dash": "dot"})
    fig.update_layout(**PLOT_LAYOUT)
    _apply_range(fig, has_legend=True, height=300)
    return _html(fig)


def chart_vix_term(f: pd.DataFrame, cf: pd.DataFrame) -> str:
    """Volatility regime: VIX level (top) + the VIX term-structure ratio VIX/VIX3M
    (bottom), ~10y. Ratio above 1.0 = BACKWARDATION (front-month fear > 3-month) —
    a stress / washout marker; the curve re-normalising back below 1.0 is the
    historically constructive 'all-clear'. Colours outside the zh swap map."""
    start = cf.index.max() - pd.Timedelta(days=365 * 10)
    vix = (f.loc[start:, "vix"].dropna().resample("W-FRI").last().dropna().round(1)
           if "vix" in f.columns else pd.Series(dtype=float))
    term = cf.loc[start:, "vix_term"].dropna().resample("W-FRI").last().dropna().round(3)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.55, 0.45],
                        vertical_spacing=0.07)
    if not vix.empty:
        fig.add_trace(go.Scatter(x=vix.index, y=vix, name="VIX",
                                 line={"color": "#7aa7e0", "width": 1.2}), row=1, col=1)
        fig.add_hline(y=30, line={"color": "#e0a030", "width": 0.5, "dash": "dot"}, row=1, col=1)
    fig.add_trace(go.Scatter(x=term.index, y=term, name="VIX / VIX3M (term structure)",
                             line={"color": "#c08af0", "width": 1.2}), row=2, col=1)
    fig.add_hline(y=1.0, line={"color": "#de5d5d", "width": 0.6, "dash": "dot"}, row=2, col=1)
    layout = {**PLOT_LAYOUT, "height": 320}
    fig.update_layout(**layout)
    _apply_range(fig, subplot=True, has_legend=True, height=320)
    return _html(fig)


def _master_brief_vm() -> dict:
    """Read site/master_brief.json (fallback data/regime/master_brief.json).
    Returns {'master_brief': <dict>} on success, {} on any failure (fail-open).
    Never fatal — a missing/malformed file simply omits the key from the VM."""
    import json as _json
    _candidates = [
        Path(__file__).parent.parent / "site" / "master_brief.json",
        Path(__file__).parent.parent / "data" / "regime" / "master_brief.json",
    ]
    for _p in _candidates:
        try:
            if _p.exists():
                return {"master_brief": _json.loads(_p.read_text(encoding="utf-8"))}
        except Exception:  # noqa: BLE001 — display-only; never fatal
            pass
    return {}


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
    from engine.conditions import conditions_frame
    _cf = conditions_frame(f)  # shared by the integrated index risk-model panel

    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"),
                      autoescape=True)
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
        build_attention_data(site)             # offshore-attention chip map (display-only); read by discovery
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("attention data failed: %s", e)
    try:
        build_smartmoney_data(site)               # 13F super-investor holdings (CONTEXT)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("smart-money data failed: %s", e)
    try:
        _put_absent = (latest.get("dislocation") or {}).get("put_state") == "put-absent"
        # per-fund rate/inflation overlay, reused from the playbook stages already in
        # latest.json (single source of truth; the playbook computed it once)
        _ri_by_fund = {st["ticker"]: st.get("rate_inflation")
                       for st in ((latest.get("playbook") or {}).get("stages") or [])
                       if st.get("rate_inflation")}
        sector_timing, notable = build_sector_pages(env, site, generated, alpha=alpha_data,
                                                    put_absent=_put_absent,
                                                    rate_infl=_ri_by_fund)
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
    try:
        build_signal_lab_page(env, site, generated)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("signal lab page failed: %s", e)
    try:
        build_alerts_page(env, site, generated)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("alerts page failed: %s", e)
    # Quant Lab (advanced analytics): cross-asset concentration + risk budgeting +
    # factor scorecard + the raw internals moved off the main dashboard. Returns the
    # cross-asset snapshot for the dashboard's compact one-bet card.
    cross_asset_snap = None
    try:
        cross_asset_snap = build_advanced_page(env, site, generated, latest, f,
                                               confirming, contradicting)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("advanced page failed: %s", e)
    # Supabase account config (public URL + publishable anon key) is BAKED into
    # theme.js at copy time so the account system (sign-in modal + cookie session)
    # is live on EVERY page — see lib/site_assets.copy_asset(), used in the loop
    # below and by every other page builder (so a builder that runs after this one
    # can no longer clobber the bake with a raw copy). The publishable key is
    # PUBLIC by design; per-user isolation is enforced by RLS
    # (templates/watchlist_supabase.sql).
    # NOTE: site/CNAME is deliberately NOT written. Pages has no custom domain
    # (repo pages cname=null) and all Pages deploys are workflow-type
    # (actions/deploy-pages), where a CNAME file in the artifact is inert.
    # The live site is apex mastermind-x.com (VPS behind Tencent EdgeOne);
    # *.github.io is a mirror. OAuth returns to the page the user started on
    # (theme.js signInWithOAuth redirectTo), not a fixed host — the allowed
    # origins live in the Supabase dashboard (see ACCOUNTS_SETUP.md).
    # copy shared static assets (theme + visual widgets) into the site
    for asset in ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
                  "account.js",
                  "stockdata.js", "watchlist.js", "factor_exposure.js", "auth.js",
                  "tablesort.js", "charts.js",
                  "masterbrief.js", "aibrief.js", "stockbrief.js", "aidesk_lean.js",
                  "stockview.js",
                  "lightweight-charts.js",
                  "allocation_scorecard.js", "live.js", "risk_state_live.js",
                  "china_risk_state_live.js",
                  "wh_banner.js", "heatmap.js",
                  "subsector_rotation.js", "subsectors.js", "subsectors_china.js",
                  # vendored (self-hosted) third-party libs — were CDN <script> tags
                  # (cdn.jsdelivr / cdn.plot.ly) that are blocked/unreliable in mainland
                  # China; served same-origin so pages load behind the GFW.
                  "supabase.js", "plotly-2.32.0.min.js",
                  # favicon vector (crisp, theme-independent). The binary
                  # favicon.ico + apple-touch-icon.png are committed static assets
                  # in site/ (regenerated by scripts/make_favicon.py, like cycle.css).
                  "favicon.svg"):
        src = config.ROOT / "templates" / asset
        if src.exists():
            site_assets.copy_asset(asset, src, site)
    # self-hosted webfonts (binary WOFF2) — copied as a tree so the @font-face in
    # theme.css resolves same-origin (Google Fonts is blocked in mainland China).
    import shutil
    fonts_src = config.ROOT / "templates" / "fonts"
    if fonts_src.exists():
        shutil.copytree(fonts_src, site / "fonts", dirs_exist_ok=True)
    # live-price progressive enhancement config (Worker URL + cadence from config.yml);
    # live.js no-ops when the URL is empty, so this is safe on the static deploy.
    try:
        from scripts.build_live_overlay import write_live_config
        write_live_config(site)
    except Exception as e:  # noqa: BLE001 — additive, never block the build
        log.warning("live_config.js skipped: %s", e)
    # Risk-Radar EXTREME alert tape (site/rr_banner.json) — the second channel of the
    # shared wh_banner.js top bar. Fires only at the radar's gate-confirmed "risk-off"
    # band; otherwise writes an inert alert:null. Additive + degrade-silent.
    try:
        from scripts.build_rr_banner import build as build_rr_banner
        build_rr_banner(site)
    except Exception as e:  # noqa: BLE001 — additive, never block the build
        log.warning("rr_banner.json skipped: %s", e)
    # per-ticker factor betas for the watchlist's Portfolio Exposure panel — the
    # client aggregates these against the user's holdings (engine/factor_exposure.py;
    # validated in reports/factor-exposure-phase0.md). Additive + graceful.
    try:
        from engine.factor_exposure import compute_exposure
        exp = compute_exposure()
        if exp:
            (site / "factor_betas.json").write_text(
                json.dumps(exp, separators=(",", ":"), default=str))
            log.info("wrote factor_betas.json (%d names)", exp.get("n", 0))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("factor_betas.json failed: %s", e)
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
    # WIDE "Standout individual stocks" board (~80-120 names ranked by the validated
    # alpha leg, each carrying the unified Conviction profile/verdict). Written by
    # build_stock_library at the END of the prior run (one-build lag, like setups.json,
    # surfaced via the card's as_of). Absent (first run) => the strip degrades to the
    # action_board notable cards below.
    us_standouts = None
    _us = site / "factordata" / "us_standouts.json"
    if _us.exists():
        try:
            us_standouts = json.loads(_us.read_text())
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("us_standouts.json unreadable (%s)", e)
    # W4 stock-personality slim attach: thread chart+mode chips into us_standouts buy cards
    # (inside .nb-more expander only per guardrail 16; fail-open if JSON absent or malformed).
    _sp_path = site / "factordata" / "stock_personality.json"
    _sp_per_ticker: dict = {}
    if _sp_path.exists():
        try:
            _sp_doc = json.loads(_sp_path.read_text())
            _sp_per_ticker = _sp_doc.get("per_ticker") or {}
        except Exception as _spe:  # noqa: BLE001 — additive, never fatal
            log.warning("stock_personality.json unreadable for board attach (%s)", _spe)
    if us_standouts and _sp_per_ticker:
        try:
            for _card in (us_standouts.get("buy") or []):
                _tk = _card.get("ticker")
                _sp_slim = _sp_per_ticker.get(_tk)
                if _sp_slim:
                    _chart = _sp_slim.get("chart") or []
                    _modes = _sp_slim.get("modes") or []
                    _mode1 = next((m for m in _modes if m != "normal"), None)
                    _card["personality"] = {
                        "chart": _chart[0] if _chart else None,
                        "mode": _mode1,
                    }
        except Exception as _spe2:  # noqa: BLE001 — additive, never fatal
            log.warning("stock_personality board attach failed (%s)", _spe2)
    # RLT-R6 sector-stance disclosure: join sector_central verdicts onto buy-board rows.
    # DISPLAY-ONLY — zero effect on selection, rank, or gating.
    # Missing sector or missing sector_central data -> field absent, chip silently omitted.
    # Ordering dependency: sector_central.json must be written by build_sector_rotation
    # before build_site.main() runs (nightly DAG step order enforces this).
    _sc_path = site / "sectordata" / "sector_central.json"
    if us_standouts and _sc_path.exists():
        try:
            _sc_doc = json.loads(_sc_path.read_text())
            # Build ETF-ticker -> (label_en, label_zh) from the sectors list
            _sc_by_etf: dict[str, tuple[str, str]] = {}
            for _sec in (_sc_doc.get("sectors") or []):
                _etf = _sec.get("ticker")
                _conv = _sec.get("conviction") or {}
                if _etf and _conv.get("label_en"):
                    _sc_by_etf[_etf] = (
                        _conv["label_en"],
                        _conv.get("label_zh") or _conv["label_en"],
                    )
            # GICS sector string -> SPDR ETF (canonical map from engine/spotlight.py)
            from engine.spotlight import GICS_TO_ETF as _GICS_ETF
            # Only buy lane has card rendering; watch rows are not rendered as cards.
            for _card in (us_standouts.get("buy") or []):
                _gics = _card.get("sector") or ""
                _etf = _GICS_ETF.get(_gics)
                if _etf and _etf in _sc_by_etf:
                    _lbl_en, _lbl_zh = _sc_by_etf[_etf]
                    _card["sector_stance"] = _lbl_en
                    _card["sector_stance_zh"] = _lbl_zh
        except Exception as _rlt6e:  # noqa: BLE001 — additive, never fatal
            log.warning("RLT-R6 sector-stance enrich failed (%s)", _rlt6e)
    # W2 surfaced-outcome strip (written by grade_us_board.py --nightly).
    # Absent on first run or before grade_us_board runs. Additive, never fatal.
    us_board_outcomes = None
    _ubo = site / "factordata" / "us_board_outcomes.json"
    if _ubo.exists():
        try:
            us_board_outcomes = json.loads(_ubo.read_text())
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("us_board_outcomes.json unreadable (%s)", e)

    # W2 outcomes strip — names that left the buy board in the last 21 board dates,
    # with their pct return since first surfaced. Written by grade_us_board --nightly.
    # Absent on first run or when the nightly hasn't run yet → strip degrades silently.
    us_board_outcomes = None
    _uo = site / "factordata" / "us_board_outcomes.json"
    if _uo.exists():
        try:
            _uod = json.loads(_uo.read_text())
            if not _uod.get("empty"):
                us_board_outcomes = _uod
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("us_board_outcomes.json unreadable (%s)", e)

    # Macro news & catalysts (LEAF, additive, never fatal). Catalysts (FOMC + jobs
    # report) are keyless and always on; filtered headlines + the optional LLM brief
    # only when macro_news.enabled. News NEVER feeds any score.
    macro_catalysts, macro_news_data, macro_brief_data = [], None, None
    event_strip, catalyst_line = [], ""
    event_risk = {"show": False}
    macro_news_disclaimer = macro_news_disclaimer_zh = ""
    try:
        from engine import event_calendar as _ec
        from engine import macro_news as _mnews
        _mncfg = config.load().get("macro_news", {}) or {}
        _horizon = _mncfg.get("catalysts_horizon_days", 14)
        macro_catalysts = _mnews.upcoming_catalysts(horizon_days=_horizon)
        # compact "US high-impact next 14 days" glance strip + the imminent-catalyst
        # text line fed to the LLM brief below (context only; never a scored input)
        event_strip = _ec.high_impact_strip(horizon_days=_horizon)
        catalyst_line = _ec.imminent_line(horizon_days=_horizon)
        # NON-DIRECTIONAL event-risk banner: known catalyst date x measured fragility.
        # Never a dampener / never scored (see engine/event_risk.py discipline note).
        from engine import event_risk as _erisk
        event_risk = _erisk.snapshot(latest, events=event_strip, horizon_days=_horizon)
        # scorecard: append today's firing (event-day only) + resolve realized moves
        # from SPY closes; attach the running track record to the banner. Best-effort.
        try:
            _erisk.append_log(event_risk)
            import pandas as _pd
            _sp = _pd.read_parquet(config.data_dir() / "yahoo" / "SPY.parquet")
            _spy = {str(i)[:10]: float(c) for i, c in _sp["close"].dropna().items()}
            _erisk.resolve(_spy)
        except Exception as _e:  # noqa: BLE001
            log.warning("event_risk scorecard skipped: %s", _e)
        try:
            event_risk["track"] = _erisk.track_record()
        except Exception:  # noqa: BLE001
            pass
        # surface the banner as a (display-only) dashboard alert
        _ea = _erisk.as_alert(event_risk)
        if _ea:
            latest.setdefault("alerts", []).append(_ea)
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
                sentiment_line=_sent, catalyst_line=catalyst_line)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("macro news failed: %s", e)

    # prediction-markets odds (additive leaf; None if no snapshot yet)
    prediction_markets = None
    try:
        from engine import prediction_markets as _pm
        prediction_markets = _pm.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("prediction markets failed: %s", e)

    # narrative-regime context (news_vector PIT bus + EPU/GPR uncertainty regime).
    # DISPLAY-ONLY leaf — measures the policy/geo narrative backdrop; never scored.
    # If news_vector.enabled the daily ingest accrues first-print events here too.
    narrative_regime = None
    try:
        from engine import news_vector as _nv
        if _nv.enabled():
            _nv.ingest()
        narrative_regime = _nv.recent_panel()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("news_vector failed: %s", e)

    # Narrative-Dominance Index banner (engine/narrative_regime.py). DISPLAY-ONLY:
    # Gate A (reports/narrative-regime-phase0.md) showed it is redundant with VIX for
    # forward vol, so gate_multiplier is pinned 1.0 — it never feeds a score.
    ndi = None
    try:
        from engine import narrative_regime as _nr
        ndi = _nr.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative_regime failed: %s", e)

    # Forward PIT state accrual (engine/dislocation.append_state_log): record today's
    # dislocation + narrative state so the mechanical-reversion fade edge becomes
    # validatable on FORWARD data later. Append-only; research-only, never scored.
    try:
        from engine import dislocation as _dz
        _dz.append_state_log(latest.get("dislocation"), ndi, narrative_regime)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("dislocation state-log accrual failed: %s", e)

    # whole-market dealer-gamma vol regime (validated index GEX) — context for the
    # standout setups below. Additive + graceful: None if the cboe gex store is absent.
    market_gamma = None
    try:
        market_gamma = market_gamma_view(store.read("cboe", "gex"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("market gamma view failed (%s)", e)
    from engine.alerts import alert_views
    from engine.signal_stack import build_signal_stack
    # One shared view-model feeds BOTH the macro-regime page and the US Stock
    # Dashboard — the same dashboard.html.j2 is rendered twice with a `mode` flag
    # (macro / stocks) that selects which sections show. No data is recomputed and
    # the heavy page CSS lives in exactly one template.
    # Relief-radar view (deterministic) + the TRIGGERED AI knife-vs-dip veto: the
    # veto runs ONLY when a snap is firing/building (so ~never on a normal build) and
    # is CONTEXT-ONLY — attached to the view for the AI-desk artifact + grading log
    # (the #518 declutter retired its on-card display), never read by any scorer.
    _rs_view = regime_snap_view(_cf)
    if _rs_view and _rs_view.get("status") != "dormant":
        try:
            from engine import regime_snap_veto
            _rs_view["veto"] = regime_snap_veto.assess(
                _rs_view,
                drivers=latest.get("market_drivers"),
                headlines=macro_news_data,
                regime=str((latest.get("regime") or {}).get("label", "")))
        except Exception as e:  # noqa: BLE001 — additive overlay, never fatal
            log.warning("regime-snap veto wiring failed: %s", e)
    # Persist the relief-radar snapshot so the AI Desk (engine.ai_desk.gather_desk_state)
    # reads it as an artifact and lights up its regime_snap leg. Display-only; never fatal.
    if _rs_view:
        try:
            _rsp = config.data_dir() / "regime" / "regime_snap.json"
            _rsp.parent.mkdir(parents=True, exist_ok=True)
            _rsp.write_text(json.dumps(_rs_view, indent=2, default=str))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("regime-snap persist failed: %s", e)
    # Multi-timeframe technical monitor (engine/mtf_monitor.py): monthly/weekly/daily/4h
    # breakdown · divergence · momentum-roll watch across major indexes, asset classes
    # and all sector ETFs. Writes site/riskdata/mtf_monitor.json (read back by risk_state
    # on the next build for its technical leg) and feeds the dashboard grid. Never fatal.
    try:
        from engine import mtf_monitor as _mtfm
        mtf_data = _mtfm.build()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("mtf monitor failed: %s", e)
        mtf_data = None
    # Policy-shock de-escalation state for dashboard fresh-entry caution chip
    # (PS-R3: display de-escalation only — no reordering, no sizing)
    _dash_shock_state: dict | None = None
    try:
        _dsp = site / "live" / "shock_state.json"
        if _dsp.exists():
            import json as _dsj
            _dash_shock_state = _dsj.loads(_dsp.read_text())
    except Exception as _dse:  # noqa: BLE001 — additive, never fatal
        log.warning("shock_state unavailable for dashboard (%s)", _dse)
    # TS-R6 A2: compute sector_setups before the vm so we can extract two_reads_chip
    # per ticker and attach it to action_board sector items (same ETF, two constructions).
    _sector_setups = sector_setup_view(latest, sector_timing)
    _two_reads_lookup: dict[str, dict] = {}
    if _sector_setups:
        for _sr in (_sector_setups.get("sectors") or []):
            if _sr.get("two_reads_chip") and _sr.get("ticker"):
                _two_reads_lookup[_sr["ticker"]] = _sr["two_reads_chip"]

    # Build sector_setup_lookup keyed by SPDR ticker for popover enrichment.
    _sector_setup_lookup: dict[str, dict] = {}
    if _sector_setups:
        for _sr in (_sector_setups.get("sectors") or []):
            if _sr.get("ticker"):
                _sector_setup_lookup[_sr["ticker"]] = _sr
    _ab = action_board(sector_timing, notable, basket_action_items(site),
                       sector_setup_lookup=_sector_setup_lookup)
    # Attach two_reads_chip to sector items across all lanes.
    if _two_reads_lookup:
        for _lane in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid", "notable"):
            for _item in (_ab.get(_lane) or []):
                if _item.get("kind") == "sector" and _item.get("ticker") in _two_reads_lookup:
                    _item["two_reads_chip"] = _two_reads_lookup[_item["ticker"]]

    # Mag 7 regime panel (data/mag7_regime/latest.json — DISPLAY-ONLY context read).
    # Injected into latest so the template accesses it as latest.mag7_regime.
    # Also published to site/stockdata/mag7_regime.json for potential JS consumption.
    # Fail-open: absent on first run; the panel simply doesn't render.
    if not latest.get("mag7_regime"):
        _m7 = _mag7_regime_view()
        if _m7:
            latest["mag7_regime"] = _m7
            try:
                _m7_site = site / "stockdata" / "mag7_regime.json"
                _m7_site.parent.mkdir(parents=True, exist_ok=True)
                _m7_site.write_text(json.dumps(_m7, separators=(",", ":"), default=str),
                                    encoding="utf-8")
            except Exception as _m7e:  # noqa: BLE001 — additive, never fatal
                log.warning("mag7_regime site publish failed (%s)", _m7e)

    vm = dict(
        latest=latest,
        mtf=mtf_data,
        macro_catalysts=macro_catalysts,
        event_strip=event_strip,
        event_risk=event_risk,
        prediction_markets=prediction_markets,
        narrative_regime=narrative_regime,
        ndi=ndi,
        macro_news=macro_news_data,
        macro_brief=macro_brief_data,
        macro_news_disclaimer=macro_news_disclaimer,
        macro_news_disclaimer_zh=macro_news_disclaimer_zh,
        alerts=alert_views(latest.get("alerts", [])),
        pb=latest.get("playbook"),
        month_name=calendar.month_name[pd.Timestamp(latest["date"]).month],
        commodities=(latest.get("playbook") or {}).get("commodities", []),
        sector_timing=sector_timing,
        action_board=_ab,
        top_setups=top_setups,
        us_standouts=us_standouts,
        us_board_outcomes=us_board_outcomes,
        market_gamma=market_gamma,
        components_confirming=confirming,
        components_contradicting=contradicting,
        flip_plain=flip_plain_text(latest),
        internals=internals_rows(latest),
        size_style=size_style_rows(f),
        breadth_div=breadth_divergence(f),
        breadth_panel=breadth_scorecard(),
        adv_breadth=advanced_breadth_view(f),    # Advanced Breadth tracker (us_stocks page)
        sector_setups=_sector_setups,  # PRIMARY confluence board
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
        index_health=index_health_rows(),       # macro-page index-health section
        alloc_card=alloc_card_state(),           # macro-page allocation CTA card
        risk_model=risk_model_view(f, hist, _cf),  # de-risk score + leg breakdown
        chart_risk_model=chart_risk_model(_cf),    # drawdown/recession risk-model chart
        chart_curve=chart_curve(_cf),              # 2s10s raw vs term-premium-adjusted
        chart_vix_term=chart_vix_term(f, _cf),     # VIX level + term-structure ratio
        cross_asset=cross_asset_snap,
        fear_euphoria=fear_euphoria_synthesis(latest, f),
        regime_snap=_rs_view,
        market_state=market_state_view(latest, f),  # Green/Yellow/Red market-state command-center (display-only)
        ms_history=_ms_history_view(),    # v5 scorecard: last ≤60 sessions {asof,score} — graceful absent
        idx_spark=_idx_spark_view(),      # v5 scorecard: 20-point sparklines SPY/QQQ/^DJI/^RUT — graceful absent
        signal_stack=build_signal_stack(latest),  # consolidated cross-subsystem read (display-only)
        vol_shock=_vol_shock_view(latest, event_risk),  # forward vol-shock risk gauge (display-only)
        froth_fragility=_froth_fragility_view(latest),  # euphoria + hidden-distribution top-risk gauge (display-only)
        fear_greed=_fear_greed_view(),    # Fear/Greed composite dial (display-only, P1.2)
        vol_weather=_vol_weather_view(),  # VSB W3: vol weather chips (display-only)
        breadth_split=_breadth_split_view(),  # VSB W4: AI vs non-AI breadth (display-only)
        sector_heat=_sector_heat_view(),  # compact sector-heat strip for macro.html (display-only)
        dispersion_regime=_dispersion_regime_view(),  # L3 selection-regime chip (NW Rails W2 PR-4, display-only)
        policy_lever=_policy_lever_view(),  # Policy-Shock W2-F lever card (display-only, PS-R3)
        flip_confirmation=_flip_confirmation_view(),  # T+1 sector-flip confirmation lens (Policy-Shock W1-C, display-only)
        shock_state=_dash_shock_state,  # policy-shock de-escalation (PS-R3, display-only)
        leadership_board=_leadership_board_view(),  # MLC-W1: megacap + sector RS glance surface (display-only)
        **_master_brief_vm(),
    )

    # DEV-ONLY fast-render cache: when MACRO_DUMP_VM is set, pickle the assembled
    # view-model so scripts/render_macro_fast.py can re-render macro.html /
    # us_stocks.html from the SAME data in <1s while iterating on the template/CSS
    # (a full build is ~4min). Completely inert on normal/daily builds (env unset),
    # and never fatal — a pickling failure just skips the cache. Not committed-path.
    if os.environ.get("MACRO_DUMP_VM"):
        try:
            import pickle as _pickle
            _vmcache = config.data_dir() / "_dev_macro_vm.pkl"
            with open(_vmcache, "wb") as _fh:
                _pickle.dump({"vm": vm, "generated": generated}, _fh)
            log.info("MACRO_DUMP_VM: cached view-model -> %s", _vmcache)
        except Exception as e:  # noqa: BLE001 — dev convenience only
            log.warning("MACRO_DUMP_VM cache failed: %s", e)
    # Write the macro dashboard straight to macro.html. index.html is owned
    # solely by build_vector.build_landing() (the landing hub) — keeping the raw
    # dashboard out of index.html is what stops Home (-> index.html) from
    # regressing to the dashboard when build_vector doesn't run after this.
    out = site / "macro.html"
    write_page(out, env.get_template("dashboard.html.j2").render(**vm, mode="macro"))
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)

    # Dedicated macro news feed. Uses the same context-only news/catalyst/sentiment
    # view model as the dashboard tab, but gives it a first-class reading surface.
    # W3: load the news side-artifacts written by build_news.py (macro_releases,
    # rejected log, calibration).  All are additive/optional — never fatal.
    _news_dir = site / "news"
    _macro_releases_data = None
    _news_rejected_data = None
    _news_calibration_data = None
    try:
        _mr_path = _news_dir / "macro_releases.json"
        if _mr_path.exists():
            _macro_releases_data = json.loads(_mr_path.read_text())
    except Exception as _e:  # noqa: BLE001 — additive, never fatal
        log.warning("news macro_releases.json load failed: %s", _e)
    try:
        _rj_path = _news_dir / "rejected.json"
        if _rj_path.exists():
            _news_rejected_data = json.loads(_rj_path.read_text())
    except Exception as _e:  # noqa: BLE001 — additive, never fatal
        log.warning("news rejected.json load failed: %s", _e)
    try:
        _cal_path = _news_dir / "calibration.json"
        if _cal_path.exists():
            _news_calibration_data = json.loads(_cal_path.read_text())
    except Exception as _e:  # noqa: BLE001 — additive, never fatal
        log.warning("news calibration.json load failed: %s", _e)
    # W3 fix: sort event-typed headlines by |novelty_z| desc then seendate desc so
    # the Delta Board renders in spec order without relying on Jinja abs().  Context
    # (non-event) headlines are left in their original intelligence_score order and
    # appended after event headlines.  A shallow copy avoids mutating the shared vm.
    _news_vm_macro_news = vm.get("macro_news")
    if _news_vm_macro_news and _news_vm_macro_news.get("headlines"):
        try:
            _raw_heads = _news_vm_macro_news["headlines"]
            _ev   = [h for h in _raw_heads if h.get("event")]
            _ctx  = [h for h in _raw_heads if not h.get("event")]
            # Two-pass stable sort: secondary (seendate desc) first, then primary
            # (abs novelty_z desc).  Python's Timsort is stable so equal-primary items
            # preserve their secondary order.
            _ev.sort(key=lambda h: h.get("seendate") or "", reverse=True)
            _ev.sort(
                key=lambda h: abs(float(h["novelty_z"])) if h.get("novelty_z") is not None else 0.0,
                reverse=True,
            )
            _sorted_macro_news = dict(_news_vm_macro_news)
            _sorted_macro_news["headlines"] = _ev + _ctx
        except Exception as _e:  # noqa: BLE001 — sort is best-effort; degrade to raw order
            log.warning("news ev_heads sort failed: %s", _e)
            _sorted_macro_news = _news_vm_macro_news
    else:
        _sorted_macro_news = _news_vm_macro_news
    out_news = site / "news.html"
    # vm already carries a 'macro_news' key (assigned above), so we must NOT splat
    # **vm AND pass macro_news= explicitly — that collides at argument binding and
    # raises "got multiple values for keyword argument 'macro_news'", which would
    # escape unguarded and abort the whole build.  Drop it from the splatted dict
    # and pass the sorted view as the sole macro_news source.
    _news_render_vm = {k: v for k, v in vm.items() if k != "macro_news"}
    # W3 guard: the template type-guards degrade schema-violating side-artifacts, but
    # a render failure here must never abort the build (every page after news.html
    # would be skipped). First retry without the side-artifacts — the template is
    # proven safe with all three None — then fall back to a minimal shell page.
    try:
        _news_html = env.get_template("news.html.j2").render(
            **_news_render_vm,
            macro_news=_sorted_macro_news,
            macro_releases=_macro_releases_data,
            news_rejected=_news_rejected_data,
            news_calibration=_news_calibration_data,
        )
    except Exception as _e:  # noqa: BLE001 — degrade, never raise
        log.error("news.html render failed (%s: %s) — retrying without side-artifacts",
                  type(_e).__name__, _e)
        try:
            _news_html = env.get_template("news.html.j2").render(
                **_news_render_vm,
                macro_news=_sorted_macro_news,
                macro_releases=None,
                news_rejected=None,
                news_calibration=None,
            )
        except Exception as _e2:  # noqa: BLE001 — degrade, never raise
            log.error("news.html artifact-free render failed too (%s: %s) — "
                      "writing minimal fallback page", type(_e2).__name__, _e2)
            _news_html = (
                '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                "<title>Macro News</title></head><body>"
                "<p>News page temporarily unavailable — a build artifact failed to "
                "render. It will be rebuilt on the next run.</p>"
                "<p>新闻页面暂不可用 — 构建产物渲染失败，将在下次构建时重建。</p>"
                "</body></html>"
            )
    write_page(out_news, _news_html)
    log.info("wrote %s (%.0f KB)", out_news, out_news.stat().st_size / 1024)

    # US Stock Dashboard — same VM, the "looking for stocks" half of the split.
    out_st = site / "us_stocks.html"
    write_page(out_st, env.get_template("dashboard.html.j2").render(**vm, mode="stocks"))
    log.info("wrote %s (%.0f KB)", out_st, out_st.stat().st_size / 1024)

    # Macro Signals — the dense data page that holds every gauge OFFLOADED from
    # macro.html so the front page stays uncluttered: business cycle, real-time
    # conditions/nowcast, the full Fear↔Euphoria breakdown, the two regime dials,
    # commodities tape, Fed liquidity, credit/breadth, VIX and positioning. Same VM,
    # display-only. Plus a machine-readable JSON the Brain / AI desks can consume.
    out_msig = site / "macro_signals.html"
    write_page(out_msig, env.get_template("macro_signals.html.j2").render(**vm))
    log.info("wrote %s (%.0f KB)", out_msig, out_msig.stat().st_size / 1024)
    try:
        _nh = {k: {kk: vv for kk, vv in (v or {}).items() if kk != "svg"}
               for k, v in (vm.get("nowcast_hist") or {}).items()}
        _msdata = {
            "date": latest.get("date", ""),
            "generated_utc": generated,
            "business_cycle": latest.get("business_cycle"),
            "conditions": latest.get("conditions"),
            "nowcast_hist": _nh,
            "fear_euphoria": vm.get("fear_euphoria"),
            "fear_greed": vm.get("fear_greed"),
            "vol_weather": vm.get("vol_weather"),
            "breadth_split": vm.get("breadth_split"),
            "growth_score": latest.get("growth_score"),
            "inflation_score": latest.get("inflation_score"),
            "components_confirming": vm.get("components_confirming"),
            "components_contradicting": vm.get("components_contradicting"),
            "commodities": vm.get("commodities"),
            "vix": vm.get("vix"),
            "positioning": vm.get("positioning"),
        }
        _msdir = site / "macrodata"
        _msdir.mkdir(parents=True, exist_ok=True)
        (_msdir / "macro_signals.json").write_text(
            json.dumps(_msdata, indent=2, default=str))
        log.info("wrote macrodata/macro_signals.json")
        # PR-D: Release Radar — copy the MRI producer's latest.json into macrodata/
        # so the client-side fetch in dashboard.html.j2 can reach it.  Fail-open:
        # absent until scripts/build_release_forecast.py (PR-C) has run; the UI
        # degrades to its "accruing" placeholder when the JSON is missing.  The
        # producer also writes the site copy itself later in the engine lane; this
        # copy just guarantees build_site renders never strand a stale/missing file.
        _rf_src = config.data_dir() / "release_forecast" / "latest.json"
        if _rf_src.exists():
            (_msdir / "release_forecast.json").write_bytes(_rf_src.read_bytes())
            log.info("macrodata: copied release_forecast.json")
        else:
            log.debug("macrodata: release_forecast.json not yet produced (PR-C pending)")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("macro_signals.json failed: %s", e)
    # landing-hub card stat (presence-gated by the .html existing)
    _ab = vm["action_board"] or {}
    _ts = top_setups or {}
    _n = (len((us_standouts or {}).get("buy") or [])
          or len(_ts.get("buy") or []) or len(_ab.get("notable") or []))
    _us_label = (f"{_n} standout stocks" if _n else "Stock signals & flows")
    usdir = config.data_dir() / "us_stocks"
    usdir.mkdir(parents=True, exist_ok=True)
    (usdir / "latest.json").write_text(json.dumps(
        {"date": latest.get("date", ""), "label": _us_label, "n_setups": _n}, indent=2))

    # --- S&P 500 sector treemap heatmap (Finviz/Perplexity-style) --------------
    # Builds marketdata/sp500_heatmap.json (offline-safe from the close cache; a
    # fresh 15-min Polygon snapshot is spliced in when a key is present) and the
    # standalone page that renders it. Additive — never fatal to the daily run.
    try:
        from scripts.build_sp500_heatmap import build as build_sp500_heatmap
        build_sp500_heatmap(site, generated_utc=generated)
        # Finviz themes treemap (theme → subsector tiles, members on hover) —
        # the second map-type on the same page; offline from the committed
        # Finviz snapshot (refresh via scripts/fetch_finviz_themes.py).
        try:
            from scripts.build_themes_heatmap import build as build_themes_heatmap
            build_themes_heatmap(site, generated_utc=generated)
        except Exception as e:  # noqa: BLE001 — additive, themes map optional
            log.error("themes heatmap failed: %s", e)
        out_hm = site / "sector_heatmap.html"
        write_page(out_hm, env.get_template("sector_heatmap.html.j2").render())
        log.info("wrote %s (%.0f KB)", out_hm, out_hm.stat().st_size / 1024)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("sector heatmap failed: %s", e)

    # --- China / Hong Kong / Canada sector treemaps (flat Sector → stock) ------
    # The international siblings of the S&P map: each builds
    # marketdata/<market>_heatmap.json (offline-safe from that market's close
    # cache) and a standalone page rendered from the shared market_heatmap.html.j2.
    # Additive — never fatal to the daily run.
    try:
        from scripts.build_market_heatmap import build_all as build_market_heatmaps
        from engine.market_heatmap import PAGE_META as _HM_MK
        build_market_heatmaps(site, generated_utc=generated)
        _hm_tmpl = env.get_template("market_heatmap.html.j2")
        for _m, _mk in _HM_MK.items():
            out_mh = site / f"{_m}_heatmap.html"
            write_page(out_mh, _hm_tmpl.render(mk=_mk))
            log.info("wrote %s (%.0f KB)", out_mh, out_mh.stat().st_size / 1024)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("market heatmaps (cn/hk/ca) failed: %s", e)

    # Subsector Rotation — Finviz broad-universe theme→subsector rotation/velocity
    # read (RRG map + emerging screen). Offline from the same committed Finviz
    # snapshot as the themes treemap; a separate lens from our curated baskets.
    try:
        from scripts.build_subsector_rotation import build as build_subsector_rotation
        build_subsector_rotation(site, generated_utc=generated)
        out_sr = site / "subsector_rotation.html"
        write_page(out_sr, env.get_template("subsector_rotation.html.j2").render())
        log.info("wrote %s (%.0f KB)", out_sr, out_sr.stat().st_size / 1024)
        # per-subsector detail pages (site/rotation/<key>.html) — additive, data-driven.
        try:
            from scripts.build_subsector_rotation_pages import build as build_sr_pages
            n_pages = build_sr_pages(site)
            log.info("wrote %d subsector detail pages", n_pages)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("subsector detail pages failed: %s", e)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("subsector rotation failed: %s", e)

    # China Subsector Rotation — A-share twin (同花顺 concepts + curated themes), reads the
    # committed China basket JSONs. Additive, never fatal.
    # W9-CN lane unification: primarily built in asia-close.yml; this is the nightly fallback.
    # Idempotency guard: skip if the committed JSON already has today's asof (asia lane ran).
    _src_json = site / "marketdata" / "subsector_rotation_china.json"
    try:
        _src_today = str(json.loads(_src_json.read_text()).get("asof", "")).startswith(generated[:10]) if _src_json.exists() else False
    except Exception:  # noqa: BLE001
        _src_today = False
    if _src_today:
        log.info("build_site: subsector_rotation_china already built by asia lane today (%s) — re-rendering HTML only", generated[:10])
        try:
            out_src = site / "subsector_rotation_china.html"
            write_page(out_src, env.get_template("subsector_rotation_china.html.j2").render())
            log.info("wrote %s (%.0f KB) from committed JSON", out_src, out_src.stat().st_size / 1024)
            try:
                from scripts.build_subsector_rotation_china_pages import build as build_src_pages
                log.info("wrote %d China subsector detail pages (re-render from committed JSON)", build_src_pages(site))
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.error("China subsector detail pages re-render failed: %s", e)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("China subsector rotation HTML re-render failed: %s", e)
    else:
        try:
            from scripts.build_subsector_rotation_china import build as build_sr_china
            build_sr_china(site, generated_utc=generated)
            out_src = site / "subsector_rotation_china.html"
            write_page(out_src, env.get_template("subsector_rotation_china.html.j2").render())
            log.info("wrote %s (%.0f KB)", out_src, out_src.stat().st_size / 1024)
            try:
                from scripts.build_subsector_rotation_china_pages import build as build_src_pages
                log.info("wrote %d China subsector detail pages", build_src_pages(site))
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.error("China subsector detail pages failed: %s", e)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("China subsector rotation failed: %s", e)

    # Subsector Confluence — the ENTRY-NOW desk: each S&P-500 sub-industry (+ the curated
    # thematic baskets) as an equal-weight synthetic index, read through the T1-T4 confluence
    # cascade + the validated regime state machine, with a double-gated stock funnel and one
    # detail page (index chart + member table) per group. The HEAVY compute runs nightly
    # (scripts.build_subsector_confluence.main, in the engine band); here we only RENDER the
    # board + detail pages from the committed JSON (render-lane safe, no recompute).
    try:
        from scripts.build_subsector_confluence import build as build_subsector_confluence
        n_sc = build_subsector_confluence(site, generated_utc=generated)
        log.info("wrote subsectors.html + %d subsector confluence detail pages", n_sc)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("subsector confluence render failed: %s", e)

    # Subsector Confluence · China — the 同花顺 (Tonghuashun) CONCEPT desk: each THS concept board
    # as an equal-weight A-share index → T1-T4 cascade + regime + double-gated funnel, benchmarked
    # to CSI 300. Heavy compute is nightly (scripts.build_subsector_confluence --china, cl_china);
    # here we only RENDER subsectors_china.html + detail pages from the committed JSON.
    try:
        from scripts.build_subsector_confluence import build_china as build_subsector_confluence_china
        n_cn = build_subsector_confluence_china(site, generated_utc=generated)
        log.info("wrote subsectors_china.html + %d China THS confluence detail pages", n_cn)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china subsector confluence render failed: %s", e)

    # Subsector Confluence · Nasdaq-100 + Russell-2000 — same engine WITHIN each US index
    # (benchmarked to QQQ / IWM so RS reads within-index leadership), with curated amalgamation
    # complexes as the rollup. These surface as extra tabs on the SHARED subsectors.html (the JS
    # fetches their JSON); here we only render their per-group detail pages from the committed
    # JSON. Heavy compute is nightly (scripts.build_subsector_confluence --nasdaq / --russell).
    try:
        from scripts.build_subsector_confluence import build_nasdaq, build_russell
        n_ndx = build_nasdaq(site, generated_utc=generated)
        n_rut = build_russell(site, generated_utc=generated)
        log.info("wrote %d Nasdaq-100 + %d Russell-2000 subsector confluence detail pages", n_ndx, n_rut)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("nasdaq/russell subsector confluence render failed: %s", e)

    # Index Leadership — a decoupled post-pass over the four committed confluence boards
    # (S&P-500 / Nasdaq-100 / Russell-2000 / thematic baskets) + their OHLC sidecars + the
    # index/style ETFs: lifts the RRG/velocity math to the INDEX level (which universe is the
    # RISING STAR — accelerating leadership), the observable leadership-driver ratios, and the
    # per-tab RUNNING / COILING lists. subsectors.js fetches marketdata/index_leadership.json.
    try:
        from scripts.build_index_leadership import build as build_index_leadership
        build_index_leadership(site, generated_utc=generated)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("index leadership build failed: %s", e)

    # Experiments registry — the running-experiments manifest (marketdata/experiments.json)
    # read by the admin console's Experiments tab: every accruing track-record / calibration /
    # PIT-vintage / parked-research / data-collection accrual with a computed come-back date +
    # a "results ready" flag, so the owner is told exactly when to return for the next step.
    try:
        from engine import experiments_registry
        experiments_registry.build(site)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("experiments registry build failed: %s", e)

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
    write_page(out2, hist_html)
    log.info("wrote %s (%.0f KB)", out2, out2.stat().st_size / 1024)

    # stock search: analyzer page + nightly library
    if config.load().get("stock_search", {}).get("enabled"):
        import json as _json

        from engine.cycles import STATE_DISPLAY
        from engine import ticker_alerts as _ta
        sd_json = _json.dumps(STATE_DISPLAY)
        write_page(site / "stock.html",
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

        # Bespoke single-stock chart data: a compact per-ticker OHLC JSON
        # (site/ohlc/<T>.json) read client-side by chart.js. Pure serialisation of
        # price data already on disk (no engine compute) and depends on the stock
        # index.json the library just wrote, so it runs right after. Garnish —
        # never break the build if it fails; charts just degrade to "no data".
        try:
            from scripts.build_chart_data import build_us as build_chart_data
            from scripts.build_chart_data import emit_intraday
            n_chart, n_candle = build_chart_data(site)
            log.info("chart data: %d ohlc files (%d candle-capable)", n_chart, n_candle)
            log.info("chart data: %d US intraday (4H) files", emit_intraday(site))
        except Exception as e:  # noqa: BLE001
            log.warning("chart data step failed (%s); stock charts degrade to no-data", e)

        # holdings watchlist: a pure client-state page over the same library
        # (selection persists in the browser; signals re-resolve from index.json
        # each load). Optional Supabase cloud sync is config-gated; blank => local-only.
        wl = config.load().get("watchlist", {})
        if wl.get("enabled", True):
            write_page(site / "watchlist.html",
                env.get_template("watchlist.html.j2").render(
                    generated_utc=generated, state_display_json=sd_json,
                    supabase_cfg_json=site_assets.supabase_cfg_json(),
                    starters_json=_json.dumps(wl.get("suggested", []))))
            log.info("wrote %s", site / "watchlist.html")

        # 🧠 AI stock briefs (LLM "Option 2") — DEFAULT-OFF LEAF. The bounded target
        # set (action-board standouts + the watchlist's suggested tickers) is written
        # to data/catalyst/brief_targets.json; the actual ~30 DeepSeek calls — by far
        # the heaviest step on this critical path (~20m, and it bloated the engine CI
        # job past its timeout) — run in the PARALLEL `stock_briefs` job
        # (scripts.build_stock_briefs), which reads this file and writes
        # site/stockbrief/<TICKER>.json. The stock page fetches those client-side, so a
        # <=1-run-old brief set is fine and the LLM never gates the daily build/deploy.
        # Gated by catalyst_stock.enabled — a no-op (and zero cost) when off.
        try:
            from engine import catalyst_stock
            if catalyst_stock.enabled():
                brief_set = ([n["ticker"] for n in notable]
                             + list(config.load().get("watchlist", {}).get("suggested", [])))
                tgt = config.data_dir() / "catalyst" / "brief_targets.json"
                tgt.parent.mkdir(parents=True, exist_ok=True)
                tgt.write_text(_json.dumps(brief_set))
                log.info("wrote %d AI stock-brief target(s) for the parallel stock_briefs job", len(brief_set))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("stock brief target write failed: %s", e)

    # W8b: Neural Web Committee View — flagship premium page (auth-required v1).
    # Copies data/neuralweb/confluence_graph.json + kernel_families.json to
    # site/neuralwebdata/ for client-side consumption, then renders committee.html.
    try:
        nwd = site / "neuralwebdata"
        nwd.mkdir(parents=True, exist_ok=True)
        # Copy confluence graph (nodes / edges / contradiction_summary)
        _cg_src = config.data_dir() / "neuralweb" / "confluence_graph.json"
        if _cg_src.exists():
            (nwd / "confluence_graph.json").write_bytes(_cg_src.read_bytes())
            log.info("neuralwebdata: copied confluence_graph.json")
        # Copy kernel families (horizon curves + recency trends)
        _kf_src = config.data_dir() / "neuralweb" / "kernel_families.json"
        if _kf_src.exists():
            (nwd / "kernel_families.json").write_bytes(_kf_src.read_bytes())
            log.info("neuralwebdata: copied kernel_families.json")
        # Signal Commons W2: copy half-life artifact for committee chip display
        # (display-only; zero behavior-changing consumers)
        _hl_src = config.data_dir() / "neuralweb" / "half_life.json"
        if _hl_src.exists():
            (nwd / "half_life.json").write_bytes(_hl_src.read_bytes())
            log.info("neuralwebdata: copied half_life.json")
        # PR-D: copy NW daily brief for committee.html client-side fetch
        _db_src = config.data_dir() / "neuralweb" / "daily_brief.json"
        if _db_src.exists():
            (nwd / "daily_brief.json").write_bytes(_db_src.read_bytes())
            log.info("neuralwebdata: copied daily_brief.json")
        # liquidity_plumbing lobe (neuralweb.liquidity_plumbing.v1) for committee card.
        # Render job is a fresh checkout, so copy from the committed data/ artifact
        # here rather than relying on the engine job's site-mirror surviving cross-job.
        _lp_src = config.data_dir() / "neuralweb" / "liquidity_plumbing.json"
        if _lp_src.exists():
            (nwd / "liquidity_plumbing.json").write_bytes(_lp_src.read_bytes())
            log.info("neuralwebdata: copied liquidity_plumbing.json")
        # PR-4 M2: copy deterministic attention items for committee.html client-side fetch
        _ad_src = config.data_dir() / "neuralweb" / "attention_deterministic.json"
        if _ad_src.exists():
            (nwd / "attention_deterministic.json").write_bytes(_ad_src.read_bytes())
            log.info("neuralwebdata: copied attention_deterministic.json")
        # NW read layer: distill the health run-history tail (last 14 runs, newest
        # last) for committee.html client-side fetch.  Fail-open: a missing or
        # malformed ledger never breaks the committee render.
        try:
            _hh_src = config.data_dir() / "neuralweb" / "nw_health_run_history.jsonl"
            if _hh_src.exists():
                _hh_rows: list = []
                for _hh_ln in _hh_src.read_text(encoding="utf-8").splitlines():
                    _hh_ln = _hh_ln.strip()
                    if _hh_ln:
                        try:
                            _hh_rows.append(json.loads(_hh_ln))
                        except Exception:  # noqa: BLE001 — skip malformed lines
                            pass
                _hh_rows = _hh_rows[-14:]
                (nwd / "health_history.json").write_text(
                    json.dumps(_hh_rows, ensure_ascii=False), encoding="utf-8")
                log.info("neuralwebdata: wrote health_history.json (%d rows)", len(_hh_rows))
                # Envelope: a top-level JSON array cannot carry in-place sibling
                # keys, so the stamp rides in the .envelope.json sidecar (the
                # sanctioned non-dict mechanism).  Best-effort — never breaks render.
                try:
                    from engine.neuralweb.envelope import write_sidecar as _nw_sidecar
                    _nw_sidecar(nwd / "health_history.json",
                                artifact_id="site-neuralweb-health-history")
                except Exception as _hh_env_e:  # noqa: BLE001 — envelope is best-effort
                    log.warning("neuralwebdata: health_history envelope sidecar failed (%s)", _hh_env_e)
        except Exception as _hh_e:  # noqa: BLE001 — additive; never break main build
            log.warning("neuralwebdata: health_history distill failed (%s); skipped", _hh_e)
        # NW read layer: distill the governance ledger tail (last 20 events, newest
        # last) for committee.html client-side fetch.  Same fail-open shape.
        try:
            _gv_src = config.data_dir() / "neuralweb" / "governance.jsonl"
            if _gv_src.exists():
                _gv_rows: list = []
                for _gv_ln in _gv_src.read_text(encoding="utf-8").splitlines():
                    _gv_ln = _gv_ln.strip()
                    if _gv_ln:
                        try:
                            _gv_rows.append(json.loads(_gv_ln))
                        except Exception:  # noqa: BLE001 — skip malformed lines
                            pass
                _gv_rows = _gv_rows[-20:]
                (nwd / "governance_recent.json").write_text(
                    json.dumps(_gv_rows, ensure_ascii=False), encoding="utf-8")
                log.info("neuralwebdata: wrote governance_recent.json (%d rows)", len(_gv_rows))
                # Envelope sidecar (same rationale as health_history above).
                try:
                    from engine.neuralweb.envelope import write_sidecar as _nw_sidecar
                    _nw_sidecar(nwd / "governance_recent.json",
                                artifact_id="site-neuralweb-governance-recent")
                except Exception as _gv_env_e:  # noqa: BLE001 — envelope is best-effort
                    log.warning("neuralwebdata: governance_recent envelope sidecar failed (%s)", _gv_env_e)
        except Exception as _gv_e:  # noqa: BLE001 — additive; never break main build
            log.warning("neuralwebdata: governance_recent distill failed (%s); skipped", _gv_e)
        # Supabase config (same as watchlist / theme.js)
        committee_html = env.get_template("committee.html.j2").render(
            generated_utc=generated,
            supabase_cfg_json=site_assets.supabase_cfg_json(),
        )
        write_page(site / "committee.html", committee_html)
        log.info("wrote %s", site / "committee.html")
    except Exception as _nwe:  # noqa: BLE001 — additive; never break main build
        log.warning("committee.html render failed (%s); page skipped", _nwe)

    # W4: TIL State of Themes terminal — cross-theme matrix with asymmetry legs,
    # falsifier health, filter chips, and weekly-delta strip. Reads the four
    # site/neuralwebdata theme artifacts already written by build_thematic_state.
    try:
        import scripts.build_state_of_themes as _sot
        _sot_html = _sot.render(config.ROOT)
        write_page(site / "state_of_themes.html", _sot_html)
        log.info("wrote %s", site / "state_of_themes.html")
    except Exception as _sot_e:  # noqa: BLE001 — additive; never break main build
        log.warning("state_of_themes.html render failed (%s); page skipped", _sot_e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
