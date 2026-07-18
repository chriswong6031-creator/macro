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

from lib import config, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

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


# --- plotly weight helpers (mirror scripts/build_vector.py) ---------------- #
def _plot_idx(index, daily_days: int = 400, weekly_days: int = 1825,
              weekly_step: int = 7, monthly_step: int = 30):
    """Resolution-adaptive index for the heavy full-history overlay charts: daily
    for the last ~400d, ~weekly out to 5y, ~monthly before that. Older points are
    sub-pixel at 5Y/All zoom and the recent window stays full daily, so the line
    is visually identical at every zoom — but ~5x fewer points get serialized
    (plotly emits one full date-string + value array PER trace)."""
    if len(index) == 0:
        return index
    end = index.max()
    d0 = end - pd.Timedelta(days=daily_days)
    w0 = end - pd.Timedelta(days=weekly_days)
    daily = index[index >= d0]
    weekly = index[(index < d0) & (index >= w0)][::weekly_step]
    monthly = index[index < w0][::monthly_step]
    return monthly.union(weekly).union(daily)


def _plot_y(s: pd.Series, n: int):
    """Round a y-series to n places and return a plain Python list (NaN -> null).
    plotly base64-packs numpy float64 arrays at a fixed ~10.7 chars/point whatever
    the value; a rounded text list is smaller and shrinks with fewer decimals.
    n<=0 emits ints."""
    if n <= 0:
        return [None if pd.isna(v) else int(round(float(v))) for v in s]
    return [None if pd.isna(v) else round(float(v), n) for v in s]


def _dx(index):
    """Date-only x strings ('2015-08-17') for a daily DatetimeIndex — plotly's
    default datetime serialization emits the full '...T00:00:00.000' per point PER
    trace, so date strings ~halve every x array while still rendering on a normal
    plotly date axis."""
    return [t.strftime("%Y-%m-%d") for t in index]


def _pdec(s) -> int:
    """Decimals giving a price series ~5 significant figures regardless of
    magnitude (EUR/USD ~1.08 -> 4dp, USD/JPY ~150 -> 2dp)."""
    a = np.abs(pd.Series(s).to_numpy(dtype="float64"))
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 2
    return max(0, 4 - int(np.floor(np.log10(float(np.median(a))))))


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_pair(df: pd.DataFrame, pair: str, years: float = 6) -> str:
    """Quote price + dollar-orthogonalized residual index (rebased) + risk index."""
    d = _tail_years(df, years)
    meta = META[pair]
    invert = config.load()["forex"]["assets"][pair].get("invert")
    quote = (1.0 / d["close"]) if invert else d["close"]      # show the market quote (USD/JPY etc.)
    # downsample only the heavy full-history line traces; the sparse shock markers
    # below stay full-resolution and exact.
    pidx = _plot_idx(d.index)
    px = _dx(pidx)
    qdec = _pdec(quote)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=px, y=_plot_y(quote.reindex(pidx), qdec), name=meta["label"],
                             line={"color": meta["color"], "width": 1.8}, yaxis="y"))
    if "resid_close" in d:
        rb = 100 * d["resid_close"] / d["resid_close"].iloc[0]
        fig.add_trace(go.Scatter(x=px, y=_plot_y(rb.reindex(pidx), 2), name="Idiosyncratic (ex-$)",
                                 line={"color": C["indigo"], "width": 1.2, "dash": "dot"}, yaxis="y2",
                                 hovertemplate="ex-$ %{y:.0f}<extra></extra>"))
    if "shock_state" in d:
        for state, col, sym in (("exogenous_bid", C["blue"], "triangle-up"),
                                ("exogenous_pressure", C["red"], "triangle-down")):
            m = d[d["shock_state"] == state]
            if len(m):
                my = (1.0 / m["close"]) if invert else m["close"]
                fig.add_trace(go.Scatter(x=_dx(m.index), y=_plot_y(my, qdec),
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
    for col, name, color in (("broad", "Broad USD", C["indigo"]), ("dxy", "DXY", C["blue"])):
        s = d[col].dropna()
        if len(s):
            rb = 100 * s / s.iloc[0]
            pidx = _plot_idx(s.index)
            fig.add_trace(go.Scatter(x=_dx(pidx), y=_plot_y(rb.reindex(pidx), 2), name=name,
                                     line={"color": color, "width": 1.8}))
    if "risk_off" in d:
        pidx = _plot_idx(d.index)
        fig.add_trace(go.Scatter(x=_dx(pidx), y=_plot_y(d["risk_off"].reindex(pidx), 3), name="Risk-off",
                                 line={"color": C["red"], "width": 0}, fill="tozeroy",
                                 fillcolor="rgba(211,11,11,0.07)", yaxis="y2",
                                 hovertemplate="risk-off %{y:.2f}<extra></extra>"))
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"title": "Rebased = 100", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "range": [-1, 1],
                                    "showgrid": False, "title": "risk-off"}})
    return _html(fig)


def chart_real_rate(drivers: dict, years: float = 9) -> str:
    """Broad USD (rebased) vs the US 10y real yield — the dollar's structural anchor."""
    broad = drivers.get("broad_dollar")
    real = drivers.get("us10y_real")
    if broad is None or real is None:
        return ""
    cut = max(broad.index.max(), real.index.max()) - pd.Timedelta(days=int(365 * years))
    b = broad[broad.index >= cut].dropna()
    r = real[real.index >= cut].dropna()
    if b.empty or r.empty:
        return ""
    fig = go.Figure()
    rb = 100 * b / b.iloc[0]
    pidx = _plot_idx(b.index)
    fig.add_trace(go.Scatter(x=_dx(pidx), y=_plot_y(rb.reindex(pidx), 2), name="Broad USD",
                             line={"color": C["indigo"], "width": 1.8}))
    pidx2 = _plot_idx(r.index)
    fig.add_trace(go.Scatter(x=_dx(pidx2), y=_plot_y(r.reindex(pidx2), 2), name="US 10y real yield",
                             line={"color": C["blue"], "width": 1.6}, yaxis="y2",
                             hovertemplate="real %{y:.2f}%<extra></extra>"))
    fig.update_layout(**{**PLOT, "height": 270,
                         "yaxis": {"title": "Broad USD = 100", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False,
                                    "title": "10y real %"}})
    return _html(fig)


def chart_transmission(tr: dict) -> str:
    """Horizontal diverging bars of each asset's fast correlation to the broad dollar."""
    rows = [r for r in tr.get("rows", []) if r.get("corr_fast") is not None]
    if not rows:
        return ""
    rows = sorted(rows, key=lambda r: r["corr_fast"])     # most negative at bottom
    labels = [r["label"] for r in rows]
    vals = [r["corr_fast"] for r in rows]
    colors = [C["green"] if v >= 0 else C["red"] for v in vals]
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h",
                           marker={"color": colors}, width=0.62,
                           hovertemplate="%{y}: corr %{x:.2f}<extra></extra>"))
    fig.update_layout(**{**PLOT, "height": 30 + 30 * len(rows),
                         "margin": {"l": 96, "r": 24, "t": 6, "b": 26},
                         "xaxis": {"range": [-1, 1], "gridcolor": C["grid"], "zeroline": True,
                                   "zerolinecolor": C["faint"], "title": "63d corr to broad USD"},
                         "yaxis": {"gridcolor": "rgba(0,0,0,0)"}})
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

    # multi-timeframe technical confluence on the FX-CALIBRATED cycle preset
    # (forex_mtf -> cycles.analyze(kind="fx"): measured ~35d daily / ~34wk intermediate
    # cycle). The macro-fusion (driver/trend lean) gracefully zeroes out for FX, so the
    # verdict is a PURE technical read — a tactical timing overlay.
    from engine import forex_mtf
    mtf_a = forex_mtf.mtf_ladder(df["close"])
    cal_a = (calib.get("assets", {}) or {}).get(pair, {})
    verdict = forex_mtf.confluence_verdict(mtf_a, pair, last, cal_a)
    _TF = (("D", "Daily", "日线"), ("3D", "3-Day", "3日"), ("W", "Weekly", "周线"),
           ("2W", "Biweekly", "双周"), ("ME", "Monthly", "月线"))
    mtf_rows = []
    for key, lbl, lbl_zh in _TF:
        s = (mtf_a.get("mtf") or {}).get(key) or {}
        if not s:
            continue
        macd = ("up" if s.get("macd_cross_up") or s.get("macd_curl_up") else
                "down" if s.get("macd_cross_dn") or s.get("macd_curl_dn") else
                "pos" if s.get("macd_pos") else "neg")
        mtf_rows.append({"key": key, "label": lbl, "label_zh": lbl_zh,
                         "rsi14": _r(s.get("rsi14"), 0), "stoch": _r(s.get("stoch"), 0),
                         "macd": macd, "trend": (verdict.get("per_tf") or {}).get(key, "flat")})

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
        "cnh_basis": _r(last.get("cnh_basis_bps"), 0) if pd.notna(last.get("cnh_basis_bps")) else None,
        "cnh_state": last.get("cnh_basis_state") if pd.notna(last.get("cnh_basis_state")) else None,
        "conviction": conv,
        "mtf_rows": mtf_rows,
        "verdict": {"headline": verdict.get("headline"), "headline_zh": verdict.get("headline_zh"),
                    "sub": verdict.get("sub"), "sub_zh": verdict.get("sub_zh"),
                    "grade": verdict.get("grade"), "grade_zh": verdict.get("grade_zh"),
                    "ladder_label": verdict.get("ladder_label"), "ladder_label_zh": verdict.get("ladder_label_zh")},
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
# alert timeline (mirrors build_commodities._group_timeline)
# --------------------------------------------------------------------------- #
TYPE_LABEL = {"residual_shock": "Shock", "risk_regime": "Risk", "trend_flip": "Trend",
              "momentum": "Momentum", "structure": "Structure", "positioning": "COT",
              "carry_flip": "Carry", "peg_approach": "Peg", "smile_regime": "Dollar",
              "cnh_basis": "CNH",
              # MSX-1 additions
              "smile_regime_flip": "Dollar Flip", "triple_red": "Triple-Red",
              "scenario_active": "Scenario"}


def _group_timeline(events: list[dict]) -> list[dict]:
    days: dict[str, list] = {}
    for e in events:
        ts = pd.Timestamp(e["ts"])
        asset = e.get("asset")
        lab = "Dollar" if asset == "dollar" else META.get(asset, {}).get("label", asset or "")
        e = {**e, "label": TYPE_LABEL.get(e["type"], e["type"]), "asset_label": lab,
             "daylabel": ts.strftime("%a %b %d")}
        days.setdefault(ts.strftime("%Y-%m-%d"), []).append(e)
    return [{"day": d, "daylabel": evs[0]["daylabel"], "events": evs}
            for d, evs in sorted(days.items(), reverse=True)]


# --------------------------------------------------------------------------- #
# dollar desk / transmission / strength assembly
# --------------------------------------------------------------------------- #
def _extra_inputs() -> dict:
    """Multi-column / specially-named series the dollar desk needs (not in drivers)."""
    extra: dict = {}
    cotd = store.read("cot", "cot_dollar")
    if cotd is not None and "net_spec_pct_oi" in cotd.columns:
        s = pd.to_numeric(cotd["net_spec_pct_oi"], errors="coerce")
        s.index = pd.to_datetime(s.index)
        extra["cot_dollar"] = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    extra["zq_path"] = store.read("rate_futures", "zq_path")
    return extra


def _transmission_assets(cfg: dict) -> dict:
    """Load each cross-asset series for the transmission map (close, or the level)."""
    out: dict = {}
    for key, spec in cfg["transmission"]["assets"].items():
        grp, name = spec[0], spec[1]
        df = store.read(grp, name)
        if df is None or df.empty:
            continue
        s = df["close"] if "close" in df.columns else df.iloc[:, 0]
        s = pd.to_numeric(s, errors="coerce").copy()
        s.index = pd.to_datetime(s.index)
        out[key] = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    return out


def _desk_latest(desk: dict) -> dict:
    """Compact, scalar-only dollar-desk summary for latest.json (auto-archived +
    read by cross_asset_confirm / master_brain / the hub card)."""
    if not desk:
        return {}
    rr, fp, po = desk.get("real_rate"), desk.get("fed_path"), desk.get("positioning")
    va, trd, lq = desk.get("valuation"), desk.get("trend"), desk.get("liquidity")
    sm = desk.get("smile") or {}
    # lean_zh + lean_net let a DISPLAY consumer (e.g. the sector-page dollar-context chip,
    # W3-C4b) render the lean bilingually and know its direction (+ = dollar-supportive) —
    # display only, never a scored input.
    out = {"lean": desk.get("lean"), "lean_zh": desk.get("lean_zh"),
           "lean_net": desk.get("lean_net"), "lean_n": desk.get("lean_n")}
    if rr:
        out.update(real_rate_regime=rr.get("regime"), real_rate_z=rr.get("real_z"))
    if fp:
        out.update(fed_path_bps=fp.get("path_bps"), fed_path_lean=fp.get("lean"))
    if po:
        out.update(usd_pos_pctile=po.get("pctile"), usd_pos_state=po.get("state"))
    if va:
        out.update(usd_reer_gap_pct=va.get("gap_pct"), usd_valuation=va.get("label"))
    if trd:
        out.update(trend=trd.get("label"), trend_n_up=trd.get("n_up"))
    if lq:
        out.update(liquidity_dir=lq.get("dir"))
    out.update(smile_confidence=sm.get("confidence"), triple_red=sm.get("triple_red"))
    # BUG FIX (MSX-1): smile_decomp was omitted — build_intl.py:281 and
    # flow_regime.py:1536 both read dollar_desk.smile_decomp and got null.
    # Forward the full dict verbatim; it is already JSON-serializable (all floats/strings/bools/lists).
    sd = desk.get("smile_decomp")
    if sd is not None:
        out["smile_decomp"] = sd
    return out


def _transmission_latest(tr: dict) -> dict:
    """Compact transmission summary for latest.json."""
    if not tr:
        return {}
    return {"usd_dir": tr.get("usd_dir"),
            "corr": {r["key"]: r.get("corr_fast") for r in tr.get("rows", [])},
            "headwind_for": tr.get("headwind_for", []),
            "tailwind_for": tr.get("tailwind_for", []),
            "unstable": tr.get("unstable", [])}


# --------------------------------------------------------------------------- #
# state_changes block (MSX-1 §2.1)
# --------------------------------------------------------------------------- #
_STATE_KEYS = ("smile_regime", "lean", "risk", "fed_path_lean", "liquidity_dir",
               "trend", "triple_red", "cnh_basis_state", "regime_radar_dominant")


def _state_history_path() -> "Path":
    return config.data_dir() / "forex" / "state_history.jsonl"


def _read_state_history() -> list[dict]:
    p = _state_history_path()
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _state_changes(today_vals: dict, dol: "pd.DataFrame") -> dict:
    """Compute state_changes block from state_history.jsonl + today's values.

    Appends a row to state_history.jsonl ONLY when nightly_advance_enabled().
    Keep-first by date: re-run on the same date is a no-op.
    Off-lane: compute from existing history without appending (prev/changed_on/
    days_in_state may be null if history is empty, but never raises).

    For smile_regime we seed changed_on from the _dollar frame's smile_regime
    series when history is shorter than the actual run length — the frame is
    authoritative for that key.
    """
    from engine.ledger_lane import nightly_advance_enabled

    today_date = today_vals.get("_date", "")
    hist = _read_state_history()

    if nightly_advance_enabled() and today_date:
        existing_dates = {r["date"] for r in hist}
        if today_date not in existing_dates:
            row = {"date": today_date}
            for k in _STATE_KEYS:
                v = today_vals.get(k)
                # JSON-safe: bools/strings/None all fine; convert to plain type
                row[k] = bool(v) if isinstance(v, (bool, np.bool_)) else (
                    str(v) if v is not None else None
                )
            try:
                p = _state_history_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
                hist = _read_state_history()
            except Exception as e:  # noqa: BLE001
                log.warning("state_history append failed (%s)", e)

    hist_by_date = {r["date"]: r for r in hist}
    sorted_dates = sorted(hist_by_date)

    out: dict[str, dict] = {}
    for k in _STATE_KEYS:
        cur = today_vals.get(k)
        if isinstance(cur, (bool, np.bool_)):
            cur = bool(cur)
        elif cur is not None:
            cur = str(cur)

        prev_val = None
        changed_on = None
        days_in = None

        if sorted_dates:
            # walk back to find the last different value
            for d in reversed(sorted_dates):
                row_val = hist_by_date[d].get(k)
                if row_val != cur:
                    prev_val = row_val
                    changed_on = d
                    break
            # days_in_state: count from changed_on to today (inclusive of today_date).
            # When no flip is found in history we report None (unknown ≠ log age).
            if changed_on and today_date:
                try:
                    t0 = datetime.strptime(changed_on, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    t1 = datetime.strptime(today_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    days_in = max(1, (t1 - t0).days + 1)
                except ValueError:
                    days_in = None

        # seed smile_regime changed_on from the _dollar frame when history is thin
        if k == "smile_regime" and changed_on is None and dol is not None and not dol.empty:
            if "smile_regime" in dol.columns:
                sr = dol["smile_regime"].dropna()
                if len(sr) >= 2:
                    cur_r = sr.iloc[-1]
                    transitions = sr[sr != sr.shift()]
                    transitions = transitions[transitions != cur_r]
                    if not transitions.empty:
                        changed_on = transitions.index[-1].strftime("%Y-%m-%d")
                        # prev: the value at the last non-current transition point
                        # (i.e. the regime that existed before the current one took hold)
                        prev_val = str(transitions.iloc[-1])
                        if today_date and changed_on:
                            try:
                                t0 = datetime.strptime(changed_on, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                t1 = datetime.strptime(today_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                days_in = max(1, (t1 - t0).days + 1)
                            except ValueError:
                                pass

        out[k] = {"current": cur, "prev": prev_val,
                  "changed_on": changed_on, "days_in_state": days_in}
    return out


# --------------------------------------------------------------------------- #
# context_forward_log (MSX-1 §2.4)
# --------------------------------------------------------------------------- #
_FORWARD_LOG_KEYS = ("triple_red", "cnh_stress", "carry_unwind",
                     "dollar_wrecking_ball", "smile_regime")


def _context_forward_log_path() -> "Path":
    return config.data_dir() / "forex" / "context_forward_log.jsonl"


def _append_context_forward_log(asof: str, today_vals: dict, regime: dict) -> None:
    """One row per key per nightly; keep-first by (asof, key).

    intensity_pct from regime_radar intensity where applicable else null.
    Lane-gated: off-lane is a no-op (no write).
    """
    from engine.ledger_lane import nightly_advance_enabled
    if not nightly_advance_enabled():
        return
    if not asof:
        return

    try:
        p = _context_forward_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)

        existing: set[tuple[str, str]] = set()
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        r = json.loads(line)
                        existing.add((r.get("asof", ""), r.get("key", "")))
                    except json.JSONDecodeError:
                        continue

        # intensity_pct lookup from regime_radar
        intensity_map: dict[str, "float | None"] = {}
        for s in (regime.get("scenarios") or []):
            _s_key = s.get("key")
            if not _s_key:
                log.warning("_append_context_forward_log: scenario missing 'key'; skipping row")
                continue
            intensity_map[_s_key] = s.get("intensity_today")

        rows_to_write = []
        for key in _FORWARD_LOG_KEYS:
            if (asof, key) in existing:
                continue
            if key == "smile_regime":
                state = today_vals.get("smile_regime")
                intensity_pct = None
            elif key == "triple_red":
                state = bool(today_vals.get("triple_red")) if today_vals.get("triple_red") is not None else None
                intensity_pct = None
            else:
                # map log keys to regime scenario keys
                scenario_key_map = {
                    "cnh_stress": "em_crisis_capital_flight",
                    "carry_unwind": "carry_unwind",
                    "dollar_wrecking_ball": "dollar_wrecking_ball",
                }
                scen_key = scenario_key_map.get(key, key)
                # state = whether the scenario is active
                active_set = {s.get("key") for s in (regime.get("scenarios") or []) if s.get("active") and s.get("key")}
                state = scen_key in active_set
                intensity_pct = intensity_map.get(scen_key)

            row = {
                "asof": asof,
                "key": key,
                "state": bool(state) if isinstance(state, (bool, np.bool_)) else state,
                "intensity_pct": round(float(intensity_pct), 1) if intensity_pct is not None else None,
                "graded": None,
            }
            rows_to_write.append(row)

        if rows_to_write:
            with open(p, "a", encoding="utf-8") as fh:
                for row in rows_to_write:
                    fh.write(json.dumps(row) + "\n")
    except Exception as e:  # noqa: BLE001
        log.warning("context_forward_log append failed (%s)", e)


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

    # NEW — Dollar Desk, cross-asset transmission, strength meter, scorecards.
    # Each degrades to {} on any failure (the page renders without the section).
    from engine import forex_dollar, forex_transmission, forex_scorecards
    drivers = next(iter(inputs.values()))["drivers"] if inputs else {}
    # fold any radar-only drivers (e.g. the MOVE bond-vol index) into the shared dict
    rcfg = cfg.get("regime", {})
    if rcfg.get("enabled") and rcfg.get("add_drivers"):
        for nm, spec in rcfg["add_drivers"].items():
            if nm in drivers:
                continue
            try:
                df = store.read(spec[0], spec[1])
                if df is not None and not df.empty:
                    s = pd.to_numeric(df.iloc[:, 0], errors="coerce")
                    s.index = pd.to_datetime(s.index)
                    drivers[nm] = s[~s.index.duplicated(keep="last")].sort_index().dropna().rename(nm)
            except Exception as e:  # noqa: BLE001
                log.warning("regime driver %s load failed (%s)", nm, e)
    try:
        desk = forex_dollar.dollar_desk(dol, drivers, _extra_inputs(), cfg)
        # attach the calibrated REER-value verdict to the valuation leg (display-only
        # grade from scripts.calibrate_forex's dollar-index leg — CONFIRMED on IC but
        # gated by deflated Sharpe; never wired into a score)
        dcal = calib.get("dollar") or {}
        if desk.get("valuation") and dcal:
            desk["valuation"]["verdict"] = dcal.get("verdict")
            desk["valuation"]["ic_full"] = dcal.get("ic_full")
            desk["valuation"]["promotable"] = dcal.get("promotable")
    except Exception as e:  # noqa: BLE001
        log.warning("dollar desk failed (%s)", e)
        desk = {}
    try:
        tassets = _transmission_assets(cfg)
        transmission = forex_transmission.transmission(
            drivers.get("broad_dollar"), tassets, drivers.get("us10y_real"),
            dol.get("risk_off"), cfg["transmission"])
        if transmission:
            transmission["chart"] = chart_transmission(transmission)
    except Exception as e:  # noqa: BLE001
        log.warning("transmission failed (%s)", e)
        transmission = {}
    try:
        strength = forex_dollar.strength_meter(results, cfg["strength"], cfg["assets"])
    except Exception as e:  # noqa: BLE001
        log.warning("strength meter failed (%s)", e)
        strength = {}
    try:
        dxy_df = store.read("yahoo", "DX-Y.NYB")
        dxy_close = dxy_df["close"] if dxy_df is not None and "close" in dxy_df.columns else None
        scorecards = forex_scorecards.scorecards(results, cfg["assets"], dxy_close,
                                                 cfg["scorecards"], risk_off=dol.get("risk_off"))
    except Exception as e:  # noqa: BLE001
        log.warning("scorecards failed (%s)", e)
        scorecards = []

    # NEW — FX Stress & Regime Radar: read the JOINT currency configuration (velocity +
    # level) into named scenarios + an empirical conditional base rate. Display-only;
    # each call degrades to {} so the page renders without the section on any failure.
    from engine import forex_regime
    try:
        regime = forex_regime.fx_stress_regime(results, dol, drivers, cfg) if rcfg.get("enabled") else {}
    except Exception as e:  # noqa: BLE001 — radar must never break the page
        log.warning("forex_regime stress failed (%s)", e)
        regime = {}
    try:
        kinematics = forex_regime.fx_kinematics_table(results, drivers, cfg) if rcfg.get("enabled") else {}
    except Exception as e:  # noqa: BLE001
        log.warning("forex_regime kinematics failed (%s)", e)
        kinematics = {}

    real_rate_chart = chart_real_rate(drivers)

    # daily alert timeline (deterministic, recomputed each build; no intraday for FX)
    from engine import forex_alerts
    acfg = cfg["alerts"]
    try:
        all_events = forex_alerts.rebuild(results, desk=desk, regime=regime)
    except Exception as e:  # noqa: BLE001 — timeline is optional, never break the page
        log.warning("forex alerts rebuild failed (%s)", e)
        all_events = forex_alerts.load_events()
    recent_events = forex_alerts.recent(all_events, acfg["timeline_days"])
    timeline = _group_timeline(recent_events)

    as_of = max((results[p].index.max() for p in order), default=dol.index.max()).strftime("%b %d, %Y")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cal_span = f"{min(results[p].index.min() for p in order).date()}..{max(results[p].index.max() for p in order).date()}"
    cot_ok = any("pos_pctile" in results[p].columns and results[p]["pos_pctile"].notna().any() for p in order)

    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("forex.html.j2").render(
        C=C, as_of=as_of, built=built, cal_span=cal_span,
        dollar=dollar, desk=desk, real_rate_chart=real_rate_chart,
        transmission=transmission, strength=strength, scorecards=scorecards,
        regime=regime, kinematics=kinematics,
        pairs=pairs, sections=sections, carry_table=ctable, cot_ok=cot_ok,
        timeline=timeline, timeline_days=acfg["timeline_days"], n_alerts=len(recent_events))
    site = config.ROOT / config.load()["storage"]["site_dir"]
    write_page(site / "forex.html", html)
    log.info("wrote %s/forex.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card; build_forex runs before it)
    outdir = config.data_dir() / "forex"
    outdir.mkdir(parents=True, exist_ok=True)
    _asof_raw = max((results[p].index.max() for p in order), default=dol.index.max())
    _asof_str = _asof_raw.strftime("%Y-%m-%d")

    # ---- MSX-1: enrich pairs dict with conviction narratives + signal-frame fields ----
    last_dol = dol.iloc[-1]
    cnh_basis_state_today: "str | None" = None
    _pairs_latest: dict[str, dict] = {}
    for p in pairs:
        pk = p["key"]
        conv = p.get("conviction") or {}
        df_p = results.get(pk)
        last_p = df_p.iloc[-1] if df_p is not None and not df_p.empty else pd.Series(dtype=object)
        prow: dict = {
            "label": p["label"], "quote": p["quote"], "chg": p["chg"],
            "action": conv.get("action"), "score": conv.get("score"),
            # MSX-1 additions (additive-only):
            "headline": conv.get("headline"), "head_zh": conv.get("headline_zh"),
            "sub": conv.get("sub"), "sub_zh": conv.get("sub_zh"),
            "shock_state": (last_p.get("shock_state") if pd.notna(last_p.get("shock_state", None)) else None),
            "cycle_position": (conv.get("cycle") or {}).get("label"),
        }
        if pk == "USDCNH":
            cnh_bps = last_p.get("cnh_basis_bps")
            cnh_st = last_p.get("cnh_basis_state")
            prow["cnh_basis_bps"] = _r(cnh_bps, 0) if pd.notna(cnh_bps) else None
            prow["cnh_basis_state"] = cnh_st if (cnh_st and pd.notna(cnh_st)) else None
            cnh_basis_state_today = prow["cnh_basis_state"]
        _pairs_latest[pk] = prow

    # ---- MSX-1: state_changes block ----
    smile = (desk.get("smile") or {})
    fed_p = (desk.get("fed_path") or {})
    liq = (desk.get("liquidity") or {})
    trd = (desk.get("trend") or {})
    _today_vals = {
        "_date": _asof_str,
        "smile_regime": last_dol.get("smile_regime"),
        "lean": desk.get("lean"),
        "risk": dollar.get("risk_word"),
        "fed_path_lean": fed_p.get("lean"),
        "liquidity_dir": liq.get("dir"),
        "trend": trd.get("label"),
        "triple_red": smile.get("triple_red"),
        "cnh_basis_state": cnh_basis_state_today,
        "regime_radar_dominant": regime.get("dominant") if regime else None,
    }
    try:
        sc_block = _state_changes(_today_vals, dol)
    except Exception as e:  # noqa: BLE001
        log.warning("state_changes failed (%s)", e)
        sc_block = {}

    # ---- MSX-1: context_forward_log ----
    try:
        _append_context_forward_log(_asof_str, _today_vals, regime or {})
    except Exception as e:  # noqa: BLE001
        log.warning("context_forward_log failed (%s)", e)

    # ---- MSX-1: regime_radar scenarios compact receipts ----
    def _scenario_receipt(s: dict) -> dict:
        p_raw = s.get("prob") or {}
        return {
            "key": s.get("key"),
            "name_en": s.get("name_en"),
            "name_zh": s.get("name_zh"),
            "intensity": _r(s.get("intensity_today"), 1),
            "active": bool(s.get("active")),
            "illustrative": bool(s.get("illustrative")),
            "prob": {
                "status": p_raw.get("status"),
                "p_cond": _r(p_raw.get("p_cond"), 4),
                "base_rate": _r(p_raw.get("base_rate"), 4),
                "wilson_lo": _r(p_raw.get("wilson_lo"), 4),
                "wilson_hi": _r(p_raw.get("wilson_hi"), 4),
                "n_raw": p_raw.get("n_raw"),
                "n_eff": p_raw.get("n_eff"),
                "N": p_raw.get("N"),
            },
        }

    latest = {
        "date": as_of, "asof": _asof_str,
        "regime": dollar["regime"], "favored": dollar["favored"],
        "risk": dollar["risk_word"],
        "pairs": _pairs_latest,
        # the deepened dollar read
        "dollar_desk": _desk_latest(desk),
        "transmission": _transmission_latest(transmission),
        # MSX-1: strength meter forwarded verbatim (was display-dead-end)
        "strength": strength if strength else {},
        # MSX-1: regime_radar gains 'scenarios' compact receipts (additive)
        "regime_radar": ({"as_of": regime.get("as_of"), "dominant": regime.get("dominant"),
                          "active": [s["key"] for s in regime.get("scenarios", []) if s.get("active")],
                          "intensity": {s["key"]: _r(s.get("intensity_today"), 1)
                                        for s in regime.get("scenarios", [])},
                          # MSX-1 addition: per-scenario probability receipts
                          "scenarios": [_scenario_receipt(s) for s in regime.get("scenarios", [])]}
                         if regime else {}),
        # MSX-1: state_changes block
        "state_changes": sc_block,
        # MSX-1: additive-only warning for future editors
        "schema_note": (
            "MSX-1 additive-only enrichment: do not rename/remove existing keys. "
            "new keys: dollar_desk.smile_decomp, strength, regime_radar.scenarios, "
            "pairs.<KEY>.{headline,head_zh,sub,sub_zh,shock_state,cycle_position}, "
            "pairs.USDCNH.{cnh_basis_bps,cnh_basis_state}, state_changes."
        ),
    }
    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
