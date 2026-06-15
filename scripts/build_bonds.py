"""Build the Bonds & bond-health dashboard -> site/bonds.html.

Standalone like build_forex.py / build_commodities.py (shares only the parquet
store + theme assets). HEALTH-FIRST: a Bond Health Score + cycle-clock phase sit on
top; below are the five pillars (curve & growth, credit, real & inflation, stress &
plumbing, cross-asset regime), each explainable. Recomputes the bond-health engine
every build, rebuilds the alert timeline, and writes:

  site/bonds.html            — the dashboard
  data/bonds/latest.json     — the hub card (consumed by build_vector)
  data/bonds/bond_health.json — the MACHINE-READABLE signal vector for the
                                cross-asset AI synthesis brain (the end goal)

Returns 0 on any engine error so it can never break the rest of the site.
Usage: python -m scripts.build_bonds
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
log = logging.getLogger("build_bonds")

# shared Glassnode light palette (same as build_forex for a consistent product)
C = {
    "blue": "#285FFF", "indigo": "#4559DC", "ink": "#0B1733", "text": "#344054",
    "muted": "#6F6F6F", "faint": "#A0A0A0", "red": "#D30B0B", "redfill": "#FEB5B5",
    "amber": "#F5AD42", "green": "#1a7f43", "grid": "#EAECF0", "card": "#FFFFFF",
    "bg": "#F7F8FA", "gold": "#C8A53B", "teal": "#1F8A70",
}
PLOT = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"size": 11, "color": C["text"], "family": "Inter, sans-serif"},
    margin={"l": 48, "r": 52, "t": 10, "b": 28},
    legend={"orientation": "h", "y": 1.16, "x": 0},
    xaxis={"gridcolor": C["grid"], "zeroline": False},
    yaxis={"gridcolor": C["grid"], "zeroline": False},
)

# band -> display color (shared across pillars)
HEALTH_COLOR = {"healthy": C["green"], "mixed": C["amber"], "stressed": C["red"]}
PHASE = {"recession": ("Recession", "衰退", C["red"]), "early": ("Early-cycle recovery", "周期早段复苏", C["green"]),
         "mid": ("Mid-cycle", "周期中段", C["blue"]), "late": ("Late-cycle", "周期晚段", C["amber"])}
CREDIT_BAND = {"tight": ("Tight", "偏紧", C["green"]), "normal": ("Normal", "正常", C["blue"]),
               "elevated": ("Elevated", "升高", C["amber"]), "distress": ("Distress", "困境", C["red"]),
               "crisis": ("Crisis", "危机", "#8B0000")}
MOVE_BAND = {"calm": ("Calm", "平静", C["green"]), "normal": ("Normal", "正常", C["blue"]),
             "elevated": ("Elevated", "升高", C["amber"]), "crisis": ("Crisis", "危机", C["red"])}
CORR_REGIME = {"diversifying": ("Diversifying — bonds hedge", "分散化 — 债券对冲", C["green"]),
               "mixed": ("Mixed", "中性", C["muted"]),
               "breakdown": ("Breakdown — bonds not hedging", "失效 — 债券不对冲", C["red"])}
TAX_COLOR = {"bull_steepener": C["green"], "bull_flattener": C["teal"],
             "bear_steepener": C["amber"], "bear_flattener": C["red"]}
FRAG_STATE = {"calm": ("Calm", "平静", C["green"]), "elevated": ("Elevated", "升高", C["amber"]),
              "stress": ("Stress", "压力", C["red"])}
JGB_STATE = {"steep": ("Steepening", "陡峭化", C["amber"]), "flat": ("Flat", "平坦", C["muted"]),
             "inverted": ("Inverted", "倒挂", C["red"])}
REGIONAL_PHASE = {"policy_support": ("Policy-support window", "政策支持窗口", C["green"]),
                  "risk_repair": ("Risk repair", "风险修复", C["blue"]),
                  "funding_stress": ("HK funding stress", "香港资金压力", C["red"]),
                  "fragile": ("Fragile", "脆弱", C["amber"])}
REGIONAL_LEG_LABEL = {"curve": ("China curve", "中国曲线"),
                      "credit_impulse": ("Credit impulse", "信用脉冲"),
                      "breadth": ("Market breadth", "市场广度"),
                      "fx": ("CNH/HKD FX", "人民币/港元汇率"),
                      "hk_funding": ("HK funding", "香港资金"),
                      "hk_vol": ("HK vol", "香港波动"),
                      "southbound": ("Southbound", "南向资金")}
LEG_LABEL = {"recession": ("Recession", "衰退"), "drawdown": ("Drawdown", "回撤"),
             "credit": ("Credit", "信用"), "rates_vol": ("Rates vol", "利率波动"),
             "plumbing": ("Plumbing", "资金管道")}
# calibration (scripts/calibrate_bonds) → display
VERDICT_GLYPH = {"CONFIRMED": ("✓", "measured", "已校准"), "DIRECTIONAL": ("~", "directional", "有方向性"),
                 "CONTEXT": ("·", "context", "仅背景"), "INVERTED": ("⇄", "inverted", "反向"),
                 "UNMEASURED": ("", "", "")}
LEG_CALIB_KEY = {"recession": "recession", "drawdown": "drawdown",
                 "credit": "credit", "rates_vol": "rates_vol", "plumbing": "plumbing"}


def _load_calibration() -> dict:
    """The measured calibration (scripts/calibrate_bonds → data/bonds/calibration.json).
    Empty dict if never run — the dashboard then shows the prior framing."""
    p = config.data_dir() / "bonds" / "calibration.json"
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------- #
# plotly helpers (mirror build_forex.py)
# --------------------------------------------------------------------------- #
def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


def _r(v, n=2):
    return round(float(v), n) if v is not None and pd.notna(v) else None


def _tail_years(df: pd.DataFrame, years: float) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    cutoff = df.index.max() - pd.Timedelta(days=int(365 * years))
    return df.loc[df.index >= cutoff]


def _plot_idx(index, daily_days=400, weekly_days=1825, weekly_step=7, monthly_step=30):
    if len(index) == 0:
        return index
    end = index.max()
    d0, w0 = end - pd.Timedelta(days=daily_days), end - pd.Timedelta(days=weekly_days)
    daily = index[index >= d0]
    weekly = index[(index < d0) & (index >= w0)][::weekly_step]
    monthly = index[index < w0][::monthly_step]
    return monthly.union(weekly).union(daily)


def _plot_y(s: pd.Series, n: int):
    if n <= 0:
        return [None if pd.isna(v) else int(round(float(v))) for v in s]
    return [None if pd.isna(v) else round(float(v), n) for v in s]


def _dx(index):
    return [t.strftime("%Y-%m-%d") for t in index]


def _line(fig, idx, s, name, color, width=1.7, dash=None, axis="y", n=2, fill=None, fillcolor=None):
    pidx = _plot_idx(idx)
    line = {"color": color, "width": width}
    if dash:
        line["dash"] = dash
    fig.add_trace(go.Scatter(x=_dx(pidx), y=_plot_y(s.reindex(pidx), n), name=name,
                             line=line, yaxis=axis, fill=fill, fillcolor=fillcolor))


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_health(fr: pd.DataFrame, years=8) -> str:
    d = _tail_years(fr, years)
    bcfg = config.load()["bonds"]["health"]
    fig = go.Figure()
    # healthy / stressed reference bands
    fig.add_hrect(y0=bcfg["healthy_score"], y1=100, fillcolor="rgba(26,127,67,0.06)", line_width=0)
    fig.add_hrect(y0=0, y1=bcfg["stressed_score"], fillcolor="rgba(211,11,11,0.06)", line_width=0)
    _line(fig, d.index, d["health_score"], "Bond health", C["ink"], width=2, n=1)
    fig.update_layout(**{**PLOT, "height": 250, "yaxis": {"range": [0, 100], "gridcolor": C["grid"],
                                                          "title": "health (0–100)"}})
    return _html(fig)


def chart_curve_now(f: pd.DataFrame) -> str:
    """Term structure today vs ~3mo and ~1y ago — how the curve shifted."""
    tenors = [("us3m", 0.25), ("us6m", 0.5), ("us1y", 1), ("us2y", 2), ("us3y", 3),
              ("us5y", 5), ("us7y", 7), ("us10y", 10), ("us30y", 30)]
    fig = go.Figure()
    snaps = [(-1, "Today", C["blue"], 2.2), (-64, "~3mo ago", C["faint"], 1.4),
             (-252, "~1y ago", C["amber"], 1.4)]
    xs = [t[1] for t in tenors]
    xlabels = ["3m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "30y"]
    for off, name, color, w in snaps:
        try:
            row = f.iloc[off]
        except (IndexError, KeyError):
            continue
        ys = [row.get(c) for c, _ in tenors]
        if all(v is None or pd.isna(v) for v in ys):
            continue
        fig.add_trace(go.Scatter(x=xs, y=[None if pd.isna(v) else round(float(v), 2) for v in ys],
                                 name=name, mode="lines+markers",
                                 line={"color": color, "width": w}, marker={"size": 5}))
    fig.update_layout(**{**PLOT, "height": 260,
                         "xaxis": {"tickvals": xs, "ticktext": xlabels, "title": "maturity",
                                   "gridcolor": C["grid"], "type": "log"},
                         "yaxis": {"title": "yield %", "gridcolor": C["grid"]}})
    return _html(fig)


def chart_spreads(fr: pd.DataFrame, years=12) -> str:
    d = _tail_years(fr, years)
    fig = go.Figure()
    fig.add_hline(y=0, line={"color": C["red"], "width": 1, "dash": "dot"})
    for col, name, color in (("spread_10y3m", "10y−3m (NY Fed)", C["blue"]),
                             ("spread_2s10s", "2s10s", C["indigo"]),
                             ("curve_tp_adj", "TP-adjusted 2s10s", C["teal"])):
        if col in d:
            _line(fig, d.index, d[col], name, color, n=2)
    fig.update_layout(**{**PLOT, "height": 280, "yaxis": {"title": "slope (pp)", "gridcolor": C["grid"]}})
    return _html(fig)


def chart_credit(fr: pd.DataFrame, years=12) -> str:
    d = _tail_years(fr, years)
    cfg = config.load()["bonds"]["credit"]
    fig = go.Figure()
    for lvl, lbl, col in ((cfg["hy_elevated"], "elevated", C["amber"]),
                          (cfg["hy_distress"], "distress", C["red"])):
        fig.add_hline(y=lvl, line={"color": col, "width": 1, "dash": "dash"},
                      annotation_text=lbl, annotation_font_size=9)
    if "hy_oas" in d:
        _line(fig, d.index, d["hy_oas"], "HY OAS", C["red"], n=2)
    if "ig_oas" in d:
        _line(fig, d.index, d["ig_oas"], "IG OAS", C["blue"], axis="y2", n=2)
    fig.update_layout(**{**PLOT, "height": 280,
                         "yaxis": {"title": "HY OAS %", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False, "title": "IG OAS %"}})
    return _html(fig)


def chart_real(fr: pd.DataFrame, years=12) -> str:
    d = _tail_years(fr, years)
    fig = go.Figure()
    fig.add_hline(y=0, line={"color": C["faint"], "width": 1, "dash": "dot"})
    for col, name, color in (("us10y_real", "10y real (TIPS)", C["blue"]),
                             ("breakeven_10y", "10y breakeven", C["green"]),
                             ("term_premium_10y", "term premium", C["amber"])):
        if col in d:
            _line(fig, d.index, d[col], name, color, n=2)
    fig.update_layout(**{**PLOT, "height": 280, "yaxis": {"title": "%", "gridcolor": C["grid"]}})
    return _html(fig)


def chart_move(fr: pd.DataFrame, years=12) -> str:
    d = _tail_years(fr, years)
    cfg = config.load()["bonds"]["rates_vol"]
    fig = go.Figure()
    for lvl, lbl, col in ((cfg["move_calm"], "calm", C["green"]),
                          (cfg["move_elevated"], "elevated", C["amber"]),
                          (cfg["move_crisis"], "crisis", C["red"])):
        fig.add_hline(y=lvl, line={"color": col, "width": 1, "dash": "dash"},
                      annotation_text=lbl, annotation_font_size=9)
    if "move" in d:
        _line(fig, d.index, d["move"], "MOVE", C["ink"], n=0)
    fig.update_layout(**{**PLOT, "height": 270, "yaxis": {"title": "MOVE", "gridcolor": C["grid"]}})
    return _html(fig)


def chart_corr(fr: pd.DataFrame, years=12) -> str:
    d = _tail_years(fr, years)
    cc = config.load()["engine"]["conditions"]["corr"]
    fig = go.Figure()
    fig.add_hrect(y0=cc["high"], y1=1, fillcolor="rgba(211,11,11,0.06)", line_width=0)
    fig.add_hrect(y0=-1, y1=cc["low"], fillcolor="rgba(26,127,67,0.06)", line_width=0)
    fig.add_hline(y=0, line={"color": C["faint"], "width": 1, "dash": "dot"})
    if "stock_bond_corr" in d:
        _line(fig, d.index, d["stock_bond_corr"], "63d stock-bond corr", C["indigo"], n=3)
    fig.update_layout(**{**PLOT, "height": 250, "yaxis": {"range": [-1, 1], "title": "correlation",
                                                          "gridcolor": C["grid"]}})
    return _html(fig)


def chart_sovereign(fr: pd.DataFrame, years=14) -> str:
    d = _tail_years(fr, years)
    cfg = config.load()["bonds"]["sovereign"]
    fig = go.Figure()
    for lvl, lbl, col in ((cfg["frag_elevated"], "elevated", C["amber"]), (cfg["frag_stress"], "stress", C["red"])):
        fig.add_hline(y=lvl, line={"color": col, "width": 1, "dash": "dash"}, annotation_text=lbl, annotation_font_size=9)
    if "euro_frag" in d:
        _line(fig, d.index, d["euro_frag"], "Euro frag (all−AAA 10y)", C["red"], n=2)
    if "jgb_2s10s" in d:
        _line(fig, d.index, d["jgb_2s10s"], "JGB 2s10s", C["indigo"], axis="y2", n=2)
    fig.update_layout(**{**PLOT, "height": 270,
                         "yaxis": {"title": "euro frag (pp)", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False, "title": "JGB 2s10s (pp)"}})
    return _html(fig)


def chart_regional_health(fr: pd.DataFrame, years=6) -> str:
    d = _tail_years(fr, years)
    bcfg = config.load()["bonds"]["health"]
    fig = go.Figure()
    fig.add_hrect(y0=bcfg["healthy_score"], y1=100, fillcolor="rgba(26,127,67,0.06)", line_width=0)
    fig.add_hrect(y0=0, y1=bcfg["stressed_score"], fillcolor="rgba(211,11,11,0.06)", line_width=0)
    if "health_score" in d:
        _line(fig, d.index, d["health_score"], "China/HK bond health", C["ink"], width=2, n=1)
    fig.update_layout(**{**PLOT, "height": 250, "yaxis": {"range": [0, 100], "gridcolor": C["grid"],
                                                          "title": "health (0–100)"}})
    return _html(fig)


def chart_regional_rates(fr: pd.DataFrame, years=4) -> str:
    d = _tail_years(fr, years)
    fig = go.Figure()
    for col, name, color in (("china_rate_1y", "China 1y interbank", C["blue"]),
                             ("china_rate_3m", "China 3m interbank", C["teal"]),
                             ("china_curve_1y3m", "1y−3m curve", C["amber"])):
        if col in d:
            _line(fig, d.index, d[col], name, color, n=2)
    fig.update_layout(**{**PLOT, "height": 270, "yaxis": {"title": "% / pp", "gridcolor": C["grid"]}})
    return _html(fig)


def chart_regional_liquidity(fr: pd.DataFrame, years=6) -> str:
    d = _tail_years(fr, years)
    fig = go.Figure()
    fig.add_hline(y=0, line={"color": C["faint"], "width": 1, "dash": "dot"})
    if "credit_impulse" in d:
        _line(fig, d.index, d["credit_impulse"], "China credit impulse", C["blue"], width=2, n=1)
    if "southbound_20d" in d:
        _line(fig, d.index, d["southbound_20d"] / 10000.0, "Southbound 20d (¥100bn)", C["green"], axis="y2", n=1)
    fig.update_layout(**{**PLOT, "height": 280,
                         "yaxis": {"title": "credit impulse %", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False,
                                    "title": "southbound flow"}})
    return _html(fig)


def chart_regional_fx_funding(fr: pd.DataFrame, years=4) -> str:
    d = _tail_years(fr, years)
    fig = go.Figure()
    if "hkd_weak_pressure" in d:
        _line(fig, d.index, d["hkd_weak_pressure"], "HKD weak-side pressure", C["red"], width=1.8, n=0)
    if "hibor_1m_pctile" in d:
        _line(fig, d.index, d["hibor_1m_pctile"] * 100, "HIBOR 1m percentile", C["amber"], n=0)
    if "vhsi" in d:
        _line(fig, d.index, d["vhsi"], "VHSI", C["indigo"], axis="y2", n=1)
    fig.update_layout(**{**PLOT, "height": 280,
                         "yaxis": {"range": [0, 100], "title": "stress percentile", "gridcolor": C["grid"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False, "title": "VHSI"}})
    return _html(fig)


def chart_regional_breadth(fr: pd.DataFrame, years=4) -> str:
    d = _tail_years(fr, years)
    fig = go.Figure()
    fig.add_hline(y=50, line={"color": C["faint"], "width": 1, "dash": "dot"})
    for col, name, color in (("china_pct_above_200", "China >200d", C["blue"]),
                             ("hk_pct_above_200", "HK >200d", C["indigo"]),
                             ("china_pct_above_50", "China >50d", C["teal"]),
                             ("hk_pct_above_50", "HK >50d", C["amber"])):
        if col in d:
            _line(fig, d.index, d[col], name, color, n=0)
    fig.update_layout(**{**PLOT, "height": 280, "yaxis": {"range": [0, 100], "title": "% of universe",
                                                          "gridcolor": C["grid"]}})
    return _html(fig)


# --------------------------------------------------------------------------- #
# view-model (display-ready, from the snapshot)
# --------------------------------------------------------------------------- #
def _vm(snap: dict, fr: pd.DataFrame, calib: dict | None = None) -> dict:
    calib = calib or {}
    csig = calib.get("signals", {})
    comp = csig.get("composite", {})
    comp_cond = comp.get("conditional", {}) or {}
    comp_hi = (comp_cond.get("terciles", {}) or {}).get("high", {}) or {}
    calib_vm = ({} if not comp else {
        "verdict": comp.get("verdict"),
        "hi_dd10": _r((comp_hi.get("p_dd10") or 0) * 100, 0),
        "base_dd10": _r((comp_cond.get("base_p_dd10") or 0) * 100, 0),
        "edge_pp": comp_cond.get("high_edge_pp"),
        "ic_recession": comp.get("ic_recession"),
        "span": comp.get("span"),
        "vs_best": (calib.get("composite_vs_best_leg") or {}).get("verdict"),
    })
    p = snap["pillars"]
    c, cr, ri, st, xa = p["curve"], p["credit"], p["real_inflation"], p["stress"], p["cross_asset"]
    phase = snap.get("cycle_phase")
    ph = PHASE.get(phase, (phase or "—", phase or "—", C["muted"]))
    band = cr.get("distress_band")
    cb = CREDIT_BAND.get(band, (band or "—", band or "—", C["muted"]))
    mb = st.get("move_band")
    mv = MOVE_BAND.get(mb, (mb or "—", mb or "—", C["muted"]))
    reg = xa.get("regime")
    rg = CORR_REGIME.get(reg, (reg or "—", reg or "—", C["muted"]))
    sv = p.get("sovereign", {})
    fs = FRAG_STATE.get(sv.get("frag_state"), ("—", "—", C["muted"]))
    js = JGB_STATE.get(sv.get("jgb_state"), (sv.get("jgb_state") or "—", sv.get("jgb_state") or "—", C["muted"]))
    hl = snap.get("health_label")

    def pc(v, n=0):  # percent of a 0..1 fraction
        return None if v is None else round(v * 100, n)

    return {
        "health": {
            "score": snap.get("health_score"), "label": hl,
            "label_zh": {"healthy": "健康", "mixed": "中性", "stressed": "承压"}.get(hl, hl),
            "color": HEALTH_COLOR.get(hl, C["muted"]),
            "phase_en": ph[0], "phase_zh": ph[1], "phase_color": ph[2],
            "verdict_en": snap.get("verdict_en"), "verdict_zh": snap.get("verdict_zh"),
            "recession_risk": _r(snap.get("recession_risk"), 0),
            "drawdown_risk": _r(snap.get("drawdown_risk"), 0),
            "calib": calib_vm,
            "stress_legs": [{"en": LEG_LABEL.get(k, (k, k))[0], "zh": LEG_LABEL.get(k, (k, k))[1],
                             "val": _r(v, 0),
                             "vg": VERDICT_GLYPH.get(csig.get(LEG_CALIB_KEY.get(k, ""), {}).get("verdict", ""),
                                                     ("", "", ""))}
                            for k, v in (snap.get("stress_legs") or {}).items()],
        },
        "curve": {
            "spread_10y3m": _r(c.get("spread_10y3m")), "spread_2s10s": _r(c.get("spread_2s10s")),
            "curve_tp_adj": _r(c.get("curve_tp_adjusted")), "ntfs": _r(c.get("ntfs")),
            "nyfed_prob": pc(c.get("ny_fed_recession_prob"), 1),
            "inverted": c.get("inverted"), "tp_adj_inverted": c.get("tp_adj_inverted"),
            "tax_en": c.get("move_taxonomy_en"), "tax_zh": c.get("move_taxonomy_zh"),
            "tax_note_en": c.get("move_taxonomy_note_en"), "tax_note_zh": c.get("move_taxonomy_note_zh"),
            "tax_color": TAX_COLOR.get(c.get("move_taxonomy"), C["muted"]),
            "uninversion": c.get("uninversion_alarm"),
            "bull_steepener_uninversion": c.get("bull_steepener_uninversion"),
        },
        "credit": {
            "hy_oas": _r(cr.get("hy_oas")), "ig_oas": _r(cr.get("ig_oas")),
            "hy_ig_ratio": _r(cr.get("hy_ig_ratio"), 1), "baa_aaa": _r(cr.get("baa_aaa")),
            "ebp": _r(cr.get("ebp")), "pctile": pc(cr.get("hy_pctile")),
            "band_en": cb[0], "band_zh": cb[1], "band_color": cb[2],
            "direction": cr.get("direction"),
            "direction_zh": {"widening": "扩大", "tightening": "收窄"}.get(cr.get("direction"), cr.get("direction")),
        },
        "real": {
            "real_10y": _r(ri.get("real_10y")), "real_5y": _r(ri.get("real_5y")),
            "breakeven_10y": _r(ri.get("breakeven_10y")), "breakeven_5y5y": _r(ri.get("breakeven_5y5y")),
            "term_premium": _r(ri.get("term_premium")), "tp_positive": ri.get("tp_repriced_positive"),
        },
        "stress": {
            "move": _r(st.get("move"), 0), "band_en": mv[0], "band_zh": mv[1], "color": mv[2],
            "pctile": pc(st.get("move_pctile")), "move_leads_vix": st.get("move_leads_vix"),
            "sofr_iorb_bp": _r(st.get("sofr_iorb_bp"), 0), "repo_spike_bp": _r(st.get("repo_spike_bp"), 0),
            "reserve_scarcity": st.get("reserve_scarcity"), "repo_stress": st.get("repo_stress"),
        },
        "cross": {
            "corr": _r(xa.get("stock_bond_corr"), 2), "regime_en": rg[0], "regime_zh": rg[1],
            "color": rg[2], "hedge_working": xa.get("hedge_working"),
        },
        "sovereign": {
            "euro_frag": _r(sv.get("euro_frag")), "bund_10y": _r(sv.get("bund_10y")),
            "frag_en": fs[0], "frag_zh": fs[1], "frag_color": fs[2],
            "frag_direction": sv.get("frag_direction"),
            "frag_direction_zh": {"widening": "扩大", "tightening": "收窄"}.get(sv.get("frag_direction"), ""),
            "jgb_2s10s": _r(sv.get("jgb_2s10s")), "jgb_en": js[0], "jgb_zh": js[1], "jgb_color": js[2],
        },
        "drivers": snap.get("drivers_for") or {},
        "alarms": snap.get("alarms") or [],
    }


def _regional_vm(snap: dict) -> dict:
    p = snap["pillars"]
    rates, liq, mh, fx = p["rates"], p["credit_liquidity"], p["market_health"], p["fx_funding"]
    hl = snap.get("health_label")
    ph = REGIONAL_PHASE.get(snap.get("cycle_phase"), (snap.get("cycle_phase") or "—", snap.get("cycle_phase") or "—", C["muted"]))
    legs = []
    for k, v in (snap.get("stress_legs") or {}).items():
        lab = REGIONAL_LEG_LABEL.get(k, (k, k))
        legs.append({"en": lab[0], "zh": lab[1], "val": _r(v, 0)})
    return {
        "health": {
            "score": snap.get("health_score"), "label": hl,
            "label_zh": {"healthy": "健康", "mixed": "中性", "stressed": "承压"}.get(hl, hl),
            "color": HEALTH_COLOR.get(hl, C["muted"]),
            "phase_en": ph[0], "phase_zh": ph[1], "phase_color": ph[2],
            "verdict_en": snap.get("verdict_en"), "verdict_zh": snap.get("verdict_zh"),
            "stress_legs": legs,
        },
        "rates": {
            "rate_1y": _r(rates.get("china_rate_1y")),
            "rate_3m": _r(rates.get("china_rate_3m")),
            "curve": _r(rates.get("china_curve_1y3m")),
        },
        "liquidity": {
            "credit_impulse": _r(liq.get("credit_impulse"), 1),
            "southbound_20d": _r((liq.get("southbound_20d") or 0) / 10000.0, 1) if liq.get("southbound_20d") is not None else None,
        },
        "market": {
            "china_200": _r(mh.get("china_pct_above_200"), 0),
            "hk_200": _r(mh.get("hk_pct_above_200"), 0),
            "china_50": _r(mh.get("china_pct_above_50"), 0),
            "hk_50": _r(mh.get("hk_pct_above_50"), 0),
        },
        "funding": {
            "usdcny": _r(fx.get("usdcny"), 3),
            "usdcny_60d": _r(fx.get("usdcny_60d_chg"), 1),
            "usdhkd": _r(fx.get("usdhkd"), 4),
            "hkd_pressure": _r(fx.get("hkd_weak_pressure"), 0),
            "agg_balance": _r((fx.get("agg_balance") or 0) / 1000.0, 1) if fx.get("agg_balance") is not None else None,
            "agg_balance_60d": _r(fx.get("agg_balance_60d_chg"), 1),
            "hibor_1m": _r(fx.get("hibor_1m"), 2),
            "vhsi": _r(fx.get("vhsi"), 1),
        },
        "alarms": snap.get("alarms") or [],
    }


# --------------------------------------------------------------------------- #
# alert timeline (mirrors build_forex._group_timeline)
# --------------------------------------------------------------------------- #
TYPE_LABEL = {"curve_regime": ("Curve", "曲线"), "uninversion": ("Curve", "曲线"),
              "credit_band": ("Credit", "信用"), "rates_vol": ("Rates vol", "利率波动"),
              "repo_stress": ("Plumbing", "资金管道"), "corr_regime": ("Stock-bond", "股债"),
              "recession_risk": ("Recession", "衰退")}
_WD_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _group_timeline(events: list[dict]) -> list[dict]:
    days: dict[str, list] = {}
    for e in events:
        ts = pd.Timestamp(e["ts"])
        lab = TYPE_LABEL.get(e["type"], (e["type"], e["type"]))
        e = {**e, "label": lab[0], "label_zh": lab[1],
             "daylabel": ts.strftime("%a %b %d"),
             "daylabel_zh": f"{ts.month}月{ts.day}日 {_WD_ZH[ts.weekday()]}"}
        days.setdefault(ts.strftime("%Y-%m-%d"), []).append(e)
    return [{"day": d, "daylabel": evs[0]["daylabel"], "daylabel_zh": evs[0]["daylabel_zh"], "events": evs}
            for d, evs in sorted(days.items(), reverse=True)]


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    from engine import inputs, bonds, bonds_alerts
    try:
        f = inputs.build_features()
        fr = bonds.bonds_frame(f)
        if fr.empty or "health_score" not in fr.columns:
            log.error("no bond-health frame; skipping bonds page")
            return 0
        snap = bonds.bonds_snapshot(f, fr)
        regional_fr = bonds.china_hk_bond_frame()
        regional_snap = bonds.china_hk_bond_snapshot(regional_fr)
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("bonds engine failed (%s); skipping bonds page", e)
        return 0

    calib = _load_calibration()
    vm = _vm(snap, fr, calib)
    regional_vm = _regional_vm(regional_snap)
    charts = {
        "health": chart_health(fr), "curve_now": chart_curve_now(f), "spreads": chart_spreads(fr),
        "credit": chart_credit(fr), "real": chart_real(fr), "move": chart_move(fr), "corr": chart_corr(fr),
        "sovereign": chart_sovereign(fr),
    }
    regional_charts = {
        "health": chart_regional_health(regional_fr),
        "rates": chart_regional_rates(regional_fr),
        "liquidity": chart_regional_liquidity(regional_fr),
        "funding": chart_regional_fx_funding(regional_fr),
        "breadth": chart_regional_breadth(regional_fr),
    }

    # alert timeline (deterministic, recomputed each build)
    acfg = config.load()["bonds"]["alerts"]
    try:
        events = bonds_alerts.rebuild(fr)
    except Exception as e:  # noqa: BLE001 — timeline is optional, never break the page
        log.warning("bonds alerts rebuild failed (%s)", e)
        events = bonds_alerts.load_events()
    recent = bonds_alerts.recent(events, acfg["timeline_days"])
    timeline = _group_timeline(recent)

    as_of = snap.get("as_of") or fr.dropna(how="all").index.max().strftime("%Y-%m-%d")
    as_of_disp = pd.Timestamp(as_of).strftime("%b %d, %Y")
    regional_as_of = regional_snap.get("as_of")
    regional_as_of_disp = pd.Timestamp(regional_as_of).strftime("%b %d, %Y") if regional_as_of else "—"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    span = f"{fr.index.min().date()}..{fr.index.max().date()}"
    regional_span = f"{regional_fr.index.min().date()}..{regional_fr.index.max().date()}" if not regional_fr.empty else "—"

    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("bonds.html.j2").render(
        C=C, as_of=as_of_disp, regional_as_of=regional_as_of_disp, built=built,
        span=span, regional_span=regional_span, vm=vm, regional_vm=regional_vm, charts=charts,
        regional_charts=regional_charts,
        timeline=timeline, timeline_days=acfg["timeline_days"], n_alerts=len(recent))
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "bonds.html").write_text(html)
    log.info("wrote %s/bonds.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card) + the AI signal contract
    outdir = config.data_dir() / "bonds"
    outdir.mkdir(parents=True, exist_ok=True)
    latest = {"date": as_of, "health_score": snap.get("health_score"),
              "health_label": snap.get("health_label"), "cycle_phase": snap.get("cycle_phase"),
              "verdict_en": snap.get("verdict_en"), "verdict_zh": snap.get("verdict_zh"),
              "markets": {"us": {"date": as_of, "health_score": snap.get("health_score"),
                                  "health_label": snap.get("health_label"),
                                  "cycle_phase": snap.get("cycle_phase")},
                          "china_hk": {"date": regional_as_of,
                                       "health_score": regional_snap.get("health_score"),
                                       "health_label": regional_snap.get("health_label"),
                                       "cycle_phase": regional_snap.get("cycle_phase")}}}
    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str, ensure_ascii=False))
    health_contract = {**snap, "markets": {"us": snap, "china_hk": regional_snap}}
    (outdir / "bond_health.json").write_text(json.dumps(health_contract, indent=2, default=str, ensure_ascii=False))
    log.info("wrote data/bonds/{latest,bond_health}.json — health=%s phase=%s",
             snap.get("health_score"), snap.get("cycle_phase"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
