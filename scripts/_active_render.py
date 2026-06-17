"""Shared rendering for the ACTIVE (leverage-capable) strategies — used by both
scripts.build_masterminds (multi-asset GTAA) and scripts.build_commodity_strategies
(the active levered commodity models). Charts reuse the build_spvector / build_vector
Plotly size-helpers; the detail pages use templates/active_detail.html.j2.
"""
from __future__ import annotations

import plotly.graph_objects as go

from scripts.build_spvector import _chart_dd, _chart_growth
from scripts.build_vector import C, PLOT, _html


def chart_leverage(pos) -> str:
    """Gross exposure / leverage over time (downsampled filled line)."""
    p = pos.dropna()
    if p.empty:
        return ""
    st = max(1, len(p) // 1400)
    x = [d.strftime("%Y-%m-%d") for d in p.index[::st]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=[round(float(v), 3) for v in p.iloc[::st]], name="exposure",
                             fill="tozeroy", line={"color": C["blue"], "width": 1.3},
                             fillcolor="rgba(40,95,255,0.10)"))
    fig.add_hline(y=1.0, line={"color": C["muted"], "width": 1, "dash": "dot"})
    fig.update_layout(**{**PLOT, "height": 240})
    return _html(fig)


def charts_for(eq, hodl, pos, label: str) -> dict:
    dd_s = (eq / eq.cummax() - 1) * 100
    dd_h = (hodl / hodl.cummax() - 1) * 100
    return {"growth": _chart_growth(eq, hodl, strat_label=label),
            "dd": _chart_dd(dd_s, dd_h, strat_label=label),
            "lev": chart_leverage(pos)}


def _lev_band(lev: float):
    if lev >= 1.5:
        return ("#1FA971", "Levered long", "加杠杆做多")
    if lev >= 0.8:
        return (C["blue"], "Fully invested", "满仓")
    if lev >= 0.3:
        return (C["amber"], "Trimmed", "减仓")
    return ("#9aa4b2", "Defensive (mostly cash)", "防守（多为现金）")


def card(*, key, icon, href, name_en, name_zh, thesis_en, thesis_zh, sc, extra_en, extra_zh,
         experimental=True) -> dict:
    """A scorecard-grid card dict (same shape the strategies grid template consumes)."""
    return {"key": key, "icon": icon, "href": href, "name_en": name_en, "name_zh": name_zh,
            "thesis_en": thesis_en, "thesis_zh": thesis_zh, "experimental": experimental,
            "cagr": sc["cagr"], "hodl_cagr": sc["hodl_cagr"], "sharpe": sc["sharpe"],
            "hodl_sharpe": sc["hodl_sharpe"], "maxdd": sc["maxdd"], "hodl_maxdd": sc["hodl_maxdd"],
            "income": sc["avg_leverage"], "years": sc["years"],
            "stance_en": extra_en, "stance_zh": extra_zh}


def commodity_detail_vm(ev: dict, *, built: str, back, caveat, verdict) -> dict:
    """View-model for a single-asset active commodity model (leverage dial + factor chips)."""
    m, sc = ev["spec"], ev["scorecard"]
    color, lab_en, lab_zh = _lev_band(ev["lev_now"])
    legdefs = m["legs"]
    factors = [{"label_en": legdefs.get(k, k), "label_zh": legdefs.get(k, k), "value": v}
               for k, v in ev["leg_now"].items() if v is not None]
    return {
        "s": {"key": ev["key"], "icon": m["icon"], "name_en": m["name_en"], "name_zh": m["name_zh"],
              "thesis_en": m["thesis_en"], "thesis_zh": m["thesis_zh"],
              "bench_en": m["bench_en"], "bench_zh": m["bench_zh"]},
        "as_of": ev["asof"], "built": built,
        "exposure_title_en": "Recommended exposure right now", "exposure_title_zh": "当前建议敞口",
        "alloc": None, "alloc_max": 1, "gross_now": ev["lev_now"],
        "lev_now": ev["lev_now"], "lev_color": color, "lev_label_en": lab_en, "lev_label_zh": lab_zh,
        "factors": factors, "sc": sc,
        "bench_label_en": m["bench_en"] + " buy-&-hold", "bench_label_zh": m["bench_zh"] + "买入持有",
        "charts": charts_for(ev["eq"], ev["hodl_eq"], ev["pos"], m["name_en"]),
        "oos": ev["oos"], "verdict_en": verdict[0], "verdict_zh": verdict[1],
        "caveat_en": caveat[0], "caveat_zh": caveat[1],
        "back_href": back[0], "back_label_en": back[1], "back_label_zh": back[2],
    }
