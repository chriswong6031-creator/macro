"""Build the Commodity Vector dashboard -> site/commodities.html.

Standalone like build_vector.py (shares only the parquet store + theme assets).
Recomputes the commodity signal engine every build for daily freshness, reads the
weekly calibration verdicts (data/commodity/calibration.json) when present, builds a
per-asset + commodity-complex view-model, renders light-theme Plotly charts, fills
templates/commodities.html.j2, and writes data/commodity/latest.json for the hub card.

One page, four-asset selector (gold/silver/oil/copper) + a commodity-complex regime
hero. Every per-signal claim carries its MEASURED calibration verdict (house rule).

Usage: python -m scripts.build_commodities
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_commodities")

# shared Glassnode light palette (same as build_vector for a consistent product)
C = {
    "blue": "#285FFF", "indigo": "#4559DC",
    "r1": "#E2E7FC", "r2": "#B8C6FA", "r3": "#8FA5F6", "r4": "#6888FB", "r5": "#285FFF",
    "ink": "#0B1733", "text": "#344054", "muted": "#6F6F6F", "faint": "#A0A0A0",
    "red": "#D30B0B", "redfill": "#FEB5B5", "amber": "#F5AD42", "green": "#1a7f43",
    "grid": "#EAECF0", "card": "#FFFFFF", "bg": "#F7F8FA", "gold": "#C8A53B",
}
PLOT = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"size": 11, "color": C["text"], "family": "Inter, sans-serif"},
    margin={"l": 48, "r": 52, "t": 10, "b": 28},
    legend={"orientation": "h", "y": 1.12, "x": 0},
    xaxis={"gridcolor": C["grid"], "zeroline": False},
    yaxis={"gridcolor": C["grid"], "zeroline": False},
)

# per-asset display metadata
META = {
    "gold":   {"label": "Gold",   "zh": "黄金", "unit": "$/oz",  "color": C["gold"]},
    "silver": {"label": "Silver", "zh": "白银", "unit": "$/oz",  "color": "#9AA4B2"},
    "copper": {"label": "Copper", "zh": "铜",   "unit": "$/lb",  "color": "#B5651D"},
    "oil":    {"label": "Oil · WTI", "zh": "原油", "unit": "$/bbl", "color": "#1F2933"},
}
ORDER = ["gold", "silver", "copper", "oil"]

# Honest, calibration-derived interpretations (en, zh). These are stable facts from
# scripts.calibrate_commodities — they tell the user how to READ each signal per asset.
DRIVER_INTERP = {
    "gold":   ("Contrarian here — when gold's macro backdrop looks supportive it has usually already run.",
               "此处为逆向 — 当黄金宏观背景看似有利时，往往已经上涨。"),
    "silver": ("Context only — silver's macro link is unstable; lean on the gold/silver ratio.",
               "仅作背景 — 白银的宏观联系不稳定；以金银比为准。"),
    "copper": ("Directional — an improving growth + softer-dollar backdrop tends to precede copper gains.",
               "有方向性 — 增长改善与美元走软的背景往往领先铜价上涨。"),
    "oil":    ("CONFIRMED leader — oil's dollar + inflation + growth axis genuinely leads forward returns.",
               "已确认领先 — 原油的美元+通胀+增长轴确实领先未来收益。"),
}
SHOCK_INTERP = {
    "gold":   ("Bids PERSIST — an unexplained bid (e.g. central-bank buying) has historically carried forward (+8%/126d at the high band).",
               "买盘持续 — 无法解释的买盘（如央行购金）历史上会延续（高档 +8%/126天）。"),
    "silver": ("Washouts bounce — a deep negative shock preceded +14%/126d; upside shocks are noisier.",
               "超卖反弹 — 深度负冲击后未来126天 +14%；上行冲击噪声更大。"),
    "copper": ("Context only — an unexplained copper bid has NOT reliably carried forward (high-shock band ~+6%/126d, ~51% hit; fails split-half). Read the driver/positioning instead.",
               "仅作背景 — 无法解释的铜买盘并未可靠延续（高冲击档约 +6%/126天、胜率约51%；未通过前后半段检验）。以驱动/持仓为准。"),
    "oil":    ("Bids FADE — war / supply premia mean-revert (high shock → −4%/126d); washouts bounce (+13%).",
               "买盘消退 — 战争/供给溢价均值回归（高冲击→126天 −4%）；超卖反弹（+13%）。"),
}
TREND_INTERP = {
    "gold":   ("12-month trend works — up-trend preceded +7.8%/126d (75% hit).", "12个月趋势有效 — 上涨趋势后126天 +7.8%（胜率75%）。"),
    "silver": ("12-month trend works directionally for silver.", "12个月趋势对白银有方向性。"),
    "copper": ("12-month trend is weak/unstable for copper — context.", "12个月趋势对铜较弱/不稳 — 仅作背景。"),
    "oil":    ("INVERTED — oil mean-reverts; a 12-month down-trend preceded +11%/126d. Read as contrarian.",
               "反向 — 原油均值回归；12个月下跌趋势后126天 +11%。作逆向解读。"),
}


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


def _r(v, n=2):
    return round(float(v), n) if v is not None and pd.notna(v) else None


# --------------------------------------------------------------------------- #
# alert timeline (mirrors build_vector._group_timeline)
# --------------------------------------------------------------------------- #
TYPE_LABEL = {"residual_shock": "Shock", "price_shock": "Shock", "risk_regime": "Risk",
              "risk_extreme": "Risk", "driver_shift": "Driver", "trend_flip": "Trend",
              "momentum": "Momentum", "structure": "Structure", "allocation": "Allocation",
              "positioning": "COT", "value": "Value", "complex_regime": "Complex"}
FILTER_OF = {"residual_shock": "shock", "price_shock": "shock", "risk_regime": "risk",
             "risk_extreme": "risk", "driver_shift": "driver", "trend_flip": "driver",
             "allocation": "alloc"}


def _group_timeline(events: list[dict]) -> list[dict]:
    days: dict[str, list] = {}
    for e in events:
        ts = pd.Timestamp(e["ts"])
        e = {**e, "label": TYPE_LABEL.get(e["type"], e["type"]),
             "filter": FILTER_OF.get(e["type"], "other"),
             "asset_label": META.get(e.get("asset"), {}).get("label", e.get("asset", "")),
             "time": ts.strftime("%H:%M UTC") if (ts.hour or ts.minute) else "",
             "daylabel": ts.strftime("%a %b %d")}
        days.setdefault(ts.strftime("%Y-%m-%d"), []).append(e)
    return [{"day": d, "daylabel": evs[0]["daylabel"], "events": evs}
            for d, evs in sorted(days.items(), reverse=True)]


def _tail_years(df: pd.DataFrame, years: float) -> pd.DataFrame:
    cutoff = df.index.max() - pd.Timedelta(days=int(365 * years))
    return df.loc[df.index >= cutoff]


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_price(df: pd.DataFrame, asset: str, years: float = 6) -> str:
    """Price (log) + Risk Index area (right axis) + shock markers. Shows the
    risk gauge and the residual-shock episodes against price."""
    d = _tail_years(df, years)
    meta = META[asset]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.index, y=d["close"], name=meta["label"],
                             line={"color": meta["color"], "width": 1.8}, yaxis="y"))
    if "risk_index" in d:
        fig.add_trace(go.Scatter(x=d.index, y=d["risk_index"], name="Risk Index",
                                 line={"color": C["red"], "width": 0}, fill="tozeroy",
                                 fillcolor="rgba(211,11,11,0.07)", yaxis="y2",
                                 hovertemplate="Risk %{y:.0f}<extra></extra>"))
    if "shock_state" in d:
        bid = d[d["shock_state"] == "exogenous_bid"]
        prs = d[d["shock_state"] == "exogenous_pressure"]
        if len(bid):
            fig.add_trace(go.Scatter(x=bid.index, y=bid["close"], mode="markers", name="Exogenous bid",
                                     marker={"color": C["blue"], "size": 5, "symbol": "triangle-up"}, yaxis="y"))
        if len(prs):
            fig.add_trace(go.Scatter(x=prs.index, y=prs["close"], mode="markers", name="Exogenous pressure",
                                     marker={"color": C["red"], "size": 5, "symbol": "triangle-down"}, yaxis="y"))
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"type": "log", "gridcolor": C["grid"], "title": meta["unit"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "range": [0, 100],
                                    "showgrid": False, "title": "Risk"}})
    return _html(fig)


def chart_complex(results: dict) -> str:
    """Rebased relative performance of the four commodities (last ~2y) — the
    commodity-complex at a glance."""
    fig = go.Figure()
    for a in ORDER:
        s = _tail_years(results[a][["close"]], 2)["close"]
        if s.empty:
            continue
        fig.add_trace(go.Scatter(x=s.index, y=100 * s / s.iloc[0], name=META[a]["label"],
                                 line={"color": META[a]["color"], "width": 1.8}))
    fig.add_hline(y=100, line={"color": C["faint"], "width": 1, "dash": "dot"})
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"title": "Rebased = 100", "gridcolor": C["grid"]}})
    return _html(fig)


# --------------------------------------------------------------------------- #
# backtest (inline fallback when calibration.json is absent)
# --------------------------------------------------------------------------- #
def backtest(close: pd.Series, alloc: pd.Series) -> dict:
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)
    eq = (1 + pos * ret).cumprod()
    hold = (1 + ret).cumprod()
    yrs = (close.index[-1] - close.index[0]).days / 365.25

    def cagr(e):
        return round(100 * ((e.iloc[-1]) ** (1 / yrs) - 1), 1) if yrs > 0 and e.iloc[-1] > 0 else None

    def shp(r):
        return round(r.mean() / r.std() * np.sqrt(252), 2) if r.std() else None

    def mdd(e):
        return round(100 * float((e / e.cummax() - 1).min()), 1)

    return {"cagr": cagr(eq), "hold_cagr": cagr(hold), "sharpe": shp(pos * ret),
            "hold_sharpe": shp(ret), "maxdd": mdd(eq), "hold_maxdd": mdd(hold),
            "time_in_market": round(100 * (pos > 0).mean(), 1)}


# --------------------------------------------------------------------------- #
# view-model
# --------------------------------------------------------------------------- #
def asset_vm(asset: str, df: pd.DataFrame, calib: dict) -> dict:
    last = df.iloc[-1]
    close = df["close"]
    chg = _r(100 * (close.iloc[-1] / close.iloc[-22] - 1), 1)  # ~1-month
    cal_a = calib.get("assets", {}).get(asset, {})
    verdicts = {s: e.get("verdict", "") for s, e in cal_a.get("signals", {}).items()}
    if cal_a.get("risk_drawdown"):
        verdicts["risk_index"] = cal_a["risk_drawdown"].get("verdict", "")
    score = cal_a.get("allocation", {}).get("optimal") or backtest(close, df["alloc_optimal"])

    alloc_pct = int(round(100 * (last.get("alloc_optimal") or 0)))
    risk_on = last.get("risk_regime") == "low_risk"
    vm = {
        "key": asset, "label": META[asset]["label"], "zh": META[asset]["zh"],
        "unit": META[asset]["unit"], "price": _r(close.iloc[-1], 2), "chg": chg,
        "alloc_pct": alloc_pct, "market_mode": last.get("market_mode", "—"),
        "risk_on": risk_on, "risk_index": _r(last.get("risk_index"), 0),
        "risk_word": "Calm" if risk_on else "Elevated",
        "cycle_pos": _r(100 * (last.get("cycle_position") or 0), 0),
        "ts_trend": last.get("ts_trend", "—"), "ts_momentum": _r(last.get("ts_momentum"), 2),
        "momentum": _r(last.get("momentum"), 2), "momentum_state": last.get("momentum_state", "—"),
        "structure": _r(last.get("structure"), 2), "structure_state": last.get("structure_state", "—"),
        "driver_score": _r(last.get("driver_score"), 2), "driver_state": last.get("driver_state", "—"),
        "shock_z": _r(last.get("shock_z"), 2), "shock_state": last.get("shock_state", "—"),
        "decoupled": bool(last.get("decoupled")) if pd.notna(last.get("decoupled")) else False,
        "driver_corr": _r(last.get("driver_corr"), 2),
        "pos_pctile": _r(last.get("pos_pctile"), 0), "pos_state": last.get("pos_state", "—"),
        "verdicts": verdicts, "score": score,
        "driver_interp": DRIVER_INTERP[asset], "shock_interp": SHOCK_INTERP[asset],
        "trend_interp": TREND_INTERP[asset],
        "signals": cal_a.get("signals", {}),
        "chart": chart_price(df, asset),
    }
    # asset-specific extras
    if asset in ("gold", "silver") and "gsr_pctile" in df:
        vm["gsr_pctile"] = _r(last.get("gsr_pctile"), 0)
        vm["gsr_state"] = last.get("gsr_state", "—")
    if asset == "oil" and "bw_change" in df:
        vm["bw_change"] = _r(last.get("bw_change"), 2)
        vm["bw_pctile"] = _r(last.get("bw_spread_pctile"), 0)
    return vm


FAVORED = {
    "Reflation": ["copper", "oil", "silver"],
    "Stagflation": ["gold", "silver"],
    "Goldilocks": ["gold", "copper"],
    "Deflation-scare": ["gold"],
    "Neutral": [],
}


def complex_vm(results: dict, calib: dict) -> dict:
    cx = results["_complex"]
    last = cx.iloc[-1]
    regime = last.get("complex_regime", "Neutral")
    return {
        "regime": regime,
        "dollar_dir": "weakening" if last.get("dollar_dir", 0) < 0 else ("strengthening" if last.get("dollar_dir", 0) > 0 else "flat"),
        "growth_dir": "rising" if last.get("growth_dir", 0) > 0 else ("falling" if last.get("growth_dir", 0) < 0 else "flat"),
        "favored": [META[a]["label"] for a in FAVORED.get(regime, [])],
        "gsr": _r(last.get("gold_silver_ratio"), 1) if "gold_silver_ratio" in cx else _r(last.get("gsr"), 1),
        "copper_gold": _r(last.get("copper_gold"), 4),
        "chart": chart_complex(results),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    from engine import commodity_signals
    try:
        results = commodity_signals.compute_all()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("commodity engine failed (%s); skipping commodities page", e)
        return 0

    outdir = config.data_dir() / "commodity"
    outdir.mkdir(parents=True, exist_ok=True)
    cpath = outdir / "calibration.json"
    calib = json.loads(cpath.read_text()) if cpath.exists() else {"assets": {}, "meta": {}}

    assets = [asset_vm(a, results[a], calib) for a in ORDER if a in results]
    cx = complex_vm(results, calib)

    # alert timeline (deterministic rebuild from signals + any sentinel events)
    from engine import commodity_alerts
    acfg = config.load()["commodities"]["alerts"]
    try:
        all_events = commodity_alerts.rebuild(results)
    except Exception as e:  # noqa: BLE001 — timeline is optional, never break the page
        log.warning("commodity alerts rebuild failed (%s)", e)
        all_events = commodity_alerts.load_events()
    recent_events = commodity_alerts.recent(all_events, acfg["timeline_days"])
    timeline = _group_timeline(recent_events)

    # Phase 6 (annotation-only, default OFF): upcoming catalysts (keyless, always on)
    # + optional news annotation of the most recent shock events when enabled.
    from engine import commodity_news
    ncfg = config.load().get("commodity_news", {})
    catalysts = commodity_news.upcoming_catalysts(horizon_days=ncfg.get("catalysts_horizon_days", 14))
    news_disclaimer = commodity_news.DISCLAIMER_TEXT
    if commodity_news.enabled():
        annotated = 0
        for day in timeline:
            for e in day["events"]:
                if e["type"] in ("residual_shock", "price_shock") and e.get("asset") in META and annotated < 6:
                    try:  # annotation is best-effort context — never break the page build
                        ann = commodity_news.annotate_event(e["asset"], pd.Timestamp(e["ts"]).date(),
                                                            e.get("headline", ""))
                        if ann and ann.get("headlines"):
                            e["news"] = ann
                    except Exception as ex:  # noqa: BLE001
                        log.warning("news annotation failed for %s (%s)", e.get("asset"), ex)
                    annotated += 1

    as_of = results["gold"].index.max().strftime("%b %d, %Y")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    span = calib.get("meta", {}).get("split", "")
    cal_span = (f"{results['gold'].index.min().date()}..{results['gold'].index.max().date()}")

    # i18n + jinja
    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    env.filters["money"] = lambda v: ("—" if v is None else f"${v:,.2f}")
    html = env.get_template("commodities.html.j2").render(
        C=C, as_of=as_of, built=built, cal_span=cal_span, complex=cx,
        assets=assets, order=ORDER, timeline=timeline,
        timeline_days=acfg["timeline_days"], n_alerts=len(recent_events),
        catalysts=catalysts, news_disclaimer=news_disclaimer)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "commodities.html").write_text(html)
    log.info("wrote %s/commodities.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card; runs before build_vector)
    latest = {"date": as_of, "regime": cx["regime"], "favored": cx["favored"],
              "assets": {a["key"]: {"label": a["label"], "price": a["price"], "chg": a["chg"],
                                    "alloc": a["alloc_pct"], "risk": a["risk_word"],
                                    "trend": a["ts_trend"]} for a in assets}}
    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
