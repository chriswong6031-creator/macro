"""Generate the static dashboard (site/index.html) from stored engine output.

Reads regime/latest.json, regime_history.parquet, run_status.json and the
parquet store — never refetches and never recomputes the classifier, so the
site builds even when every scraper is down.

Usage: python -m scripts.build_site
"""
from __future__ import annotations

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
from engine.inputs import build_features  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_site")

QUAD_COLORS = {"Q1": "#2e9e4f", "Q2": "#d4a017", "Q3": "#d04545", "Q4": "#3f78d8"}
PLOT_LAYOUT = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)", font={"size": 11},
    margin={"l": 45, "r": 15, "t": 10, "b": 30}, height=300,
    legend={"orientation": "h", "y": 1.08},
)


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False})


def chart_regime(f: pd.DataFrame, hist: pd.DataFrame) -> str:
    two_y = f.index.max() - pd.Timedelta(days=730)
    spy = f.loc[two_y:, "SPY"].dropna()
    sub = hist.loc[two_y:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=spy.index, y=spy, name="SPY",
                             line={"color": "#d7dce3", "width": 1.3}))
    q = sub["quad"].dropna()
    if not q.empty:
        seg_id = (q != q.shift()).cumsum()
        for _, seg in q.groupby(seg_id):
            fig.add_vrect(x0=seg.index.min(), x1=seg.index.max(),
                          fillcolor=QUAD_COLORS.get(seg.iloc[0], "#888"),
                          opacity=0.16, line_width=0)
    fig.update_layout(**PLOT_LAYOUT, showlegend=False)
    return _html(fig)


def chart_axes(hist: pd.DataFrame) -> str:
    two_y = hist.index.max() - pd.Timedelta(days=730)
    sub = hist.loc[two_y:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub.index, y=sub["growth_score"], name="growth",
                             line={"color": "#5fbf7f", "width": 1.2}))
    fig.add_trace(go.Scatter(x=sub.index, y=sub["inflation_score"], name="inflation",
                             line={"color": "#e07070", "width": 1.2}))
    fig.add_hline(y=0, line={"color": "#666", "width": 0.6})
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_yaxes(range=[-1.05, 1.05])
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
    layout = {**PLOT_LAYOUT, "height": 340}
    fig.update_layout(**layout)
    return _html(fig)


def positioning_rows(f: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []

    def pctile(s: pd.Series) -> str:
        s = s.dropna()
        if len(s) < 50:
            return "n/a"
        return f"{(s.rank(pct=True).iloc[-1] * 100):.0f}"

    for key, label in [("cot_es_spx", "COT ES net spec %OI"),
                       ("cot_ust10y", "COT 10Y net spec %OI"),
                       ("cot_dollar", "COT DXY net spec %OI"),
                       ("cot_gold", "COT gold net spec %OI")]:
        df = store.read("cot", key)
        if df is not None and "net_spec_pct_oi" in df.columns and len(df):
            s = df["net_spec_pct_oi"]
            rows.append({"name": label, "value": f"{s.iloc[-1]:+.1f}%",
                         "pctile": pctile(s), "asof": str(df.index.max().date())})
    naaim = store.read("sentiment", "naaim")
    if naaim is not None and len(naaim):
        s = naaim.iloc[:, 0]
        rows.append({"name": "NAAIM exposure", "value": f"{s.iloc[-1]:.0f}",
                     "pctile": pctile(s), "asof": str(naaim.index.max().date())})
    pc = store.read("cboe", "putcall")
    if pc is not None and len(pc):
        for col, label in [("index_pc_ratio", "SPX put/call (computed)"),
                           ("equity_pc_ratio", "Equity put/call proxy")]:
            if col in pc.columns:
                s = pc[col]
                rows.append({"name": label, "value": f"{s.iloc[-1]:.2f}",
                             "pctile": pctile(s), "asof": str(pc.index.max().date())})
    gex = store.read("cboe", "gex")
    if gex is not None and len(gex):
        g = gex.iloc[-1]
        flip = (f"{g['spot_vs_flip_pct']:+.1f}% from flip"
                if pd.notna(g.get("spot_vs_flip_pct")) else "no near flip")
        rows.append({"name": "Net GEX (computed)", "value": f"{g['net_gex_bn']:+.0f}bn",
                     "pctile": flip, "asof": str(gex.index.max().date())})
    vr = f["vix_ratio"].dropna()
    if len(vr):
        rows.append({"name": "VIX/VIX3M", "value": f"{vr.iloc[-1]:.3f}",
                     "pctile": pctile(vr), "asof": str(vr.index[-1].date())})
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


def flows_html_table() -> str | None:
    ft = flows_table()
    if ft is None or ft.dropna(how="all").empty:
        return None
    recent = ft.dropna(how="all").tail(10).round(0)
    recent.index = [str(d.date()) for d in recent.index]
    return recent.to_html(border=0, classes="", na_rep="—")


def health_rows() -> list[dict]:
    sources = store.read_status().get("sources", {})
    return [{"name": k, "status": v.get("status", "?"), "rows": v.get("rows", 0),
             "last_date": v.get("last_date"), "error": (v.get("error") or "")[:90]}
            for k, v in sorted(sources.items())]


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    with open(config.data_dir() / "regime" / "latest.json") as fh:
        latest = json.load(fh)
    hist = pd.read_parquet(config.data_dir() / "regime" / "regime_history.parquet")
    hist.index = pd.to_datetime(hist.index)
    f = build_features()

    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    tpl = env.get_template("dashboard.html.j2")
    html = tpl.render(
        latest=latest,
        generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        chart_regime=chart_regime(f, hist),
        chart_axes=chart_axes(hist),
        chart_liquidity=chart_liquidity(f),
        chart_credit_breadth=chart_credit_breadth(f),
        positioning=positioning_rows(f),
        holdings_changes=holdings_rows(),
        holdings_threshold=config.load()["holdings"]["active_change_alert_pct"],
        flows_html=flows_html_table(),
        health=health_rows(),
    )
    out = site / "index.html"
    out.write_text(html)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
