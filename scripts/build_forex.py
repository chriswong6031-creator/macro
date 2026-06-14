"""Build the Forex Vector dashboard -> site/forex.html.

Standalone like build_commodities.py (shares only the parquet store + theme
assets). Recomputes the forex signal engine every build for daily freshness, reads
the calibration verdicts (data/forex/conviction_calibration.json) when present,
builds a broad-dollar master view-model + per-pair risk-context view-models, renders
light-theme Plotly charts, fills templates/forex.html.j2, and writes
data/forex/latest.json for the hub card.

DOLLAR-FIRST: a broad-dollar master tile (dollar-smile regime) sits above the
board; each pair's signals are scored on the dollar-orthogonalized residual, and
the verdict headline is RISK-CONTEXT (LONG/SHORT-base secondary). Returns 0 on any
engine error so it can never break the rest of the site.

Usage: python -m scripts.build_forex
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

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_forex")

# shared Glassnode light palette (same as build_commodities for a consistent product)
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
    legend={"orientation": "h", "y": 1.14, "x": 0},
    xaxis={"gridcolor": C["grid"], "zeroline": False},
    yaxis={"gridcolor": C["grid"], "zeroline": False},
)

# per-pair display metadata (label, zh, base, quote, archetype label, color)
META = {
    "EURUSD": {"label": "EUR/USD", "zh": "欧元/美元", "base": "EUR", "quote": "USD",
               "arch": ("Major", "主要货币"), "color": "#285FFF"},
    "USDJPY": {"label": "USD/JPY", "zh": "美元/日元", "base": "JPY", "quote": "USD",
               "arch": ("Haven-funder", "避险/融资货币"), "color": "#D30B0B"},
    "GBPUSD": {"label": "GBP/USD", "zh": "英镑/美元", "base": "GBP", "quote": "USD",
               "arch": ("Major", "主要货币"), "color": "#4559DC"},
    "AUDUSD": {"label": "AUD/USD", "zh": "澳元/美元", "base": "AUD", "quote": "USD",
               "arch": ("Commodity-dollar", "商品货币"), "color": "#1a7f43"},
    "USDCAD": {"label": "USD/CAD", "zh": "美元/加元", "base": "CAD", "quote": "USD",
               "arch": ("Commodity-dollar", "商品货币"), "color": "#B5651D"},
    "USDCHF": {"label": "USD/CHF", "zh": "美元/瑞郎", "base": "CHF", "quote": "USD",
               "arch": ("Haven-funder", "避险/融资货币"), "color": "#9AA4B2"},
    "USDMXN": {"label": "USD/MXN", "zh": "美元/墨西哥比索", "base": "MXN", "quote": "USD",
               "arch": ("EM", "新兴市场"), "color": "#C8A53B"},
    "USDBRL": {"label": "USD/BRL", "zh": "美元/巴西雷亚尔", "base": "BRL", "quote": "USD",
               "arch": ("EM", "新兴市场"), "color": "#1F8A70"},
    "USDCNH": {"label": "USD/CNH", "zh": "美元/离岸人民币", "base": "CNH", "quote": "USD",
               "arch": ("EM · managed", "新兴市场·受管理"), "color": "#D85A30"},
}

# dollar-smile regime -> color + favored-currency strip (en/zh)
REGIME_COLOR = {
    "Risk-off haven bid": C["red"], "US growth premium": C["blue"],
    "Global reflation": C["green"], "US-specific stress": C["amber"], "Neutral": C["ink"],
}
REGIME_ZH = {
    "Risk-off haven bid": "避险买盘（美元微笑右侧）", "US growth premium": "美国增长溢价（左侧）",
    "Global reflation": "全球再通胀（美元走软）", "US-specific stress": "美国自身风险（微笑破裂）",
    "Neutral": "中性",
}
FAVORED = {
    "Risk-off haven bid": (["USD", "JPY", "CHF"], ["美元", "日元", "瑞郎"]),
    "US growth premium": (["USD"], ["美元"]),
    "Global reflation": (["AUD", "commodity FX", "EM"], ["澳元", "商品货币", "新兴市场"]),
    "US-specific stress": (["EUR", "JPY", "gold"], ["欧元", "日元", "黄金"]),
    "Neutral": ([], []),
}


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


def _r(v, n=2):
    return round(float(v), n) if v is not None and pd.notna(v) else None


def _tail_years(df: pd.DataFrame, years: float) -> pd.DataFrame:
    cutoff = df.index.max() - pd.Timedelta(days=int(365 * years))
    return df.loc[df.index >= cutoff]


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_pair(df: pd.DataFrame, pair: str, years: float = 6) -> str:
    """Quote price + dollar-orthogonalized residual index (rebased) + risk index."""
    d = _tail_years(df, years)
    meta = META[pair]
    invert = config.load()["forex"]["assets"][pair].get("invert")
    quote = (1.0 / d["close"]) if invert else d["close"]      # show the market quote (USD/JPY etc.)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.index, y=quote, name=meta["label"],
                             line={"color": meta["color"], "width": 1.8}, yaxis="y"))
    if "resid_close" in d:
        rb = 100 * d["resid_close"] / d["resid_close"].iloc[0]
        fig.add_trace(go.Scatter(x=d.index, y=rb, name="Idiosyncratic (ex-$)",
                                 line={"color": C["indigo"], "width": 1.2, "dash": "dot"}, yaxis="y2",
                                 hovertemplate="ex-$ %{y:.0f}<extra></extra>"))
    if "shock_state" in d:
        for state, col, sym in (("exogenous_bid", C["blue"], "triangle-up"),
                                ("exogenous_pressure", C["red"], "triangle-down")):
            m = d[d["shock_state"] == state]
            if len(m):
                fig.add_trace(go.Scatter(x=m.index, y=(1.0 / m["close"]) if invert else m["close"],
                                         mode="markers", name=state.replace("_", " "),
                                         marker={"color": col, "size": 5, "symbol": sym}, yaxis="y"))
    fig.update_layout(**{**PLOT, "height": 290,
                         "yaxis": {"gridcolor": C["grid"], "title": meta["label"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False,
                                    "title": "ex-$ idx"}})
    return _html(fig)


def chart_dollar(dol: pd.DataFrame, years: float = 8) -> str:
    """Broad dollar + DXY (rebased) and the risk-off composite (right axis)."""
    d = _tail_years(dol, years)
    fig = go.Figure()
    for col, name, color in (("broad", "Broad USD", C["ink"]), ("dxy", "DXY", C["blue"])):
        s = d[col].dropna()
        if len(s):
            fig.add_trace(go.Scatter(x=s.index, y=100 * s / s.iloc[0], name=name,
                                     line={"color": color, "width": 1.8}))
    if "risk_off" in d:
        fig.add_trace(go.Scatter(x=d.index, y=d["risk_off"], name="Risk-off",
                                 line={"color": C["red"], "width": 0}, fill="tozeroy",
                                 fillcolor="rgba(211,11,11,0.07)", yaxis="y2",
                                 hovertemplate="risk-off %{y:.2f}<extra></extra>"))
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"title": "Rebased = 100", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "range": [-1, 1],
                                    "showgrid": False, "title": "risk-off"}})
    return _html(fig)


# --------------------------------------------------------------------------- #
# view-models
# --------------------------------------------------------------------------- #
def dollar_vm(dol: pd.DataFrame) -> dict:
    last = dol.iloc[-1]
    reg = last.get("smile_regime", "Neutral")
    fav_en, fav_zh = FAVORED.get(reg, ([], []))
    roc = last.get("dollar_roc")
    return {
        "regime": reg, "regime_zh": REGIME_ZH.get(reg, reg),
        "color": REGIME_COLOR.get(reg, C["ink"]),
        "dollar_dir": "weakening" if (roc or 0) < 0 else ("strengthening" if (roc or 0) > 0 else "flat"),
        "dollar_dir_zh": "走软" if (roc or 0) < 0 else ("走强" if (roc or 0) > 0 else "持平"),
        "roc": _r(100 * (roc or 0), 1),
        "risk_off": _r(last.get("risk_off"), 2),
        "risk_word": "risk-off" if (last.get("risk_off") or 0) > 0 else "risk-on",
        "risk_word_zh": "避险" if (last.get("risk_off") or 0) > 0 else "偏好风险",
        "broad": _r(last.get("broad"), 2), "dxy": _r(last.get("dxy"), 2),
        "afe": _r(last.get("broad_afe"), 1), "eme": _r(last.get("broad_eme"), 1),
        "dollar_day_z": _r(last.get("dollar_day_z"), 2),
        "dollar_day": bool((last.get("dollar_day_z") or 0) > config.load()["forex"]["dollar"]["dollar_day_z"]),
        "favored": fav_en, "favored_zh": fav_zh,
        "chart": chart_dollar(dol),
    }


def pair_vm(pair: str, df: pd.DataFrame, calib: dict, dollar_day: float) -> dict:
    from engine import forex_conviction
    meta = config.load()["forex"]["assets"][pair]
    last = df.iloc[-1]
    invert = meta.get("invert")
    quote = (1.0 / last["close"]) if invert else last["close"]
    quote_prev = (1.0 / df["close"].iloc[-22]) if invert else df["close"].iloc[-22]
    conv = forex_conviction.conviction(pair, df, meta, calib, dollar_day=dollar_day)
    cd, cs_ = last.get("carry_diff"), last.get("carry_score")
    vm = {
        "key": pair, "label": META[pair]["label"], "zh": META[pair]["zh"],
        "base": META[pair]["base"], "quote_ccy": META[pair]["quote"],
        "arch": META[pair]["arch"][0], "arch_zh": META[pair]["arch"][1],
        "quote": _r(quote, 4), "chg": _r(100 * (quote / quote_prev - 1), 1),
        "resid_chg": _r(100 * (last.get("resid_close", 1) / df["resid_close"].iloc[-22] - 1), 1)
        if "resid_close" in df else None,
        "dollar_beta": _r(last.get("dollar_beta"), 2),
        "ts_trend": last.get("ts_trend", "—"), "ts_momentum": _r(last.get("ts_momentum"), 2),
        "structure": _r(last.get("structure"), 2), "structure_state": last.get("structure_state", "—"),
        "risk_index": _r(last.get("risk_index"), 0),
        "risk_word": "Calm" if (last.get("risk_regime") == "low_risk") else "Elevated",
        "shock_z": _r(last.get("shock_z"), 2), "shock_state": last.get("shock_state", "—"),
        "pos_pctile": _r(last.get("pos_pctile"), 0), "pos_state": last.get("pos_state"),
        "carry_diff": _r(cd, 2), "carry_score": _r(cs_, 2),
        "carry_to_vol": _r(last.get("carry_to_vol"), 2),
        "carry_context": meta.get("carry") == "context",
        "reer_gap": _r(100 * last.get("reer_gap"), 1) if pd.notna(last.get("reer_gap")) else None,
        "rate_diff_10y": _r(last.get("rate_diff_10y"), 2) if pd.notna(last.get("rate_diff_10y")) else None,
        "conviction": conv,
        "chart": chart_pair(df, pair),
    }
    return vm


# archetype -> board section (label en/zh, order)
SECTIONS = [
    ("major", "Majors", "主要货币"),
    ("commodity-dollar", "Commodity dollars", "商品货币"),
    ("haven-funder", "Haven-funders", "避险/融资货币"),
    ("em", "Emerging markets", "新兴市场"),
]


def group_sections(pairs: list[dict]) -> list[dict]:
    by_arch: dict[str, list] = {}
    for vm in pairs:
        a = config.load()["forex"]["assets"][vm["key"]].get("archetype", "major")
        by_arch.setdefault("em" if a.startswith("em") else a, []).append(vm)
    out = []
    for arch, label, zh in SECTIONS:
        members = by_arch.get(arch, [])
        if members:
            out.append({"label": label, "zh": zh, "pairs": members})
    return out


def carry_table(pairs: list[dict]) -> list[dict]:
    rows = []
    for vm in pairs:
        rows.append({"label": vm["label"], "base": vm["base"],
                     "carry": None if vm["carry_context"] else vm["carry_diff"],
                     "ctv": None if vm["carry_context"] else vm["carry_to_vol"],
                     "beta": vm["dollar_beta"], "reer_gap": vm["reer_gap"],
                     "rate10": vm["rate_diff_10y"]})
    rows.sort(key=lambda r: (r["carry"] is None, -(r["carry"] or -99)))   # high carry first
    return rows


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    from engine import forex_inputs, forex_signals, forex_conviction
    try:
        cfg = config.load()["forex"]
        inputs = forex_inputs.load_all(cfg)
        if not inputs:
            log.error("no forex inputs loaded; skipping forex page")
            return 0
        results = forex_signals.compute_all(inputs, cfg)
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("forex engine failed (%s); skipping forex page", e)
        return 0

    dol = results.get("_dollar")
    if dol is None or dol.empty:
        log.error("no dollar master frame; skipping forex page")
        return 0
    dollar = dollar_vm(dol)
    dollar_day = float(dol.iloc[-1].get("dollar_day_z") or 0.0)
    calib = forex_conviction.load_calibration()

    order = [p for p in cfg["active"] if p in results and len(results[p]) >= 300]
    pairs = [pair_vm(p, results[p], calib, dollar_day) for p in order]
    sections = group_sections(pairs)
    ctable = carry_table(pairs)

    as_of = max((results[p].index.max() for p in order), default=dol.index.max()).strftime("%b %d, %Y")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cal_span = f"{min(results[p].index.min() for p in order).date()}..{max(results[p].index.max() for p in order).date()}"
    cot_ok = any("pos_pctile" in results[p].columns and results[p]["pos_pctile"].notna().any() for p in order)

    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("forex.html.j2").render(
        C=C, as_of=as_of, built=built, cal_span=cal_span,
        dollar=dollar, pairs=pairs, sections=sections, carry_table=ctable, cot_ok=cot_ok)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "forex.html").write_text(html)
    log.info("wrote %s/forex.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card; build_forex runs before it)
    outdir = config.data_dir() / "forex"
    outdir.mkdir(parents=True, exist_ok=True)
    latest = {"date": as_of, "regime": dollar["regime"], "favored": dollar["favored"],
              "risk": dollar["risk_word"],
              "pairs": {p["key"]: {"label": p["label"], "quote": p["quote"], "chg": p["chg"],
                                   "action": (p.get("conviction") or {}).get("action"),
                                   "score": (p.get("conviction") or {}).get("score")}
                        for p in pairs}}
    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
