"""Build the Strategic Petroleum Reserves dashboard -> site/spr.html.

Standalone like build_commodities.py (shares only the parquet store + theme assets).
Surfaces, for the major reserve-holding countries:

  * US SPR — LIVE weekly (EIA WCSSTUS1): level, % of authorized capacity, 4w/52w
    change, distance from peak/low, days of refinery-run cover.
  * SPR vs oil price — the 2022 release + refill against WTI/Brent (context, not signal).
  * Cross-country comparison — curated strategic-reserve figures (config, dated/sourced)
    joined with LIVE JODI monthly TOTAL national crude stocks where reported.
  * Global aggregate + the IEA 90-day reference floor.

DISPLAY-ONLY: engine.strategic_reserves is a leaf; nothing here feeds scoring.
Writes data/spr/latest.json for the landing-hub card (consumed by build_vector).

Usage: python -m scripts.build_spr
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
from engine import strategic_reserves as sr  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_spr")

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
    margin={"l": 52, "r": 56, "t": 12, "b": 28},
    legend={"orientation": "h", "y": 1.12, "x": 0},
    xaxis={"gridcolor": C["grid"], "zeroline": False},
    yaxis={"gridcolor": C["grid"], "zeroline": False},
)


# --------------------------------------------------------------------------- #
# small chart helpers (mirror scripts/build_commodities.py)
# --------------------------------------------------------------------------- #
def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


def _dx(index) -> list[str]:
    return [t.strftime("%Y-%m-%d") for t in index]


def _plot_y(s: pd.Series, n: int):
    if n <= 0:
        return [None if pd.isna(v) else int(round(float(v))) for v in s]
    return [None if pd.isna(v) else round(float(v), n) for v in s]


def _tail_years(s: pd.Series, years: float) -> pd.Series:
    if s is None or s.empty:
        return s
    return s[s.index >= s.index.max() - pd.Timedelta(days=int(years * 365.25))]


def _r(v, n=1):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), n)


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_spr_history(spr_kbbl: pd.Series) -> str:
    """Full-history US SPR level (MMbbl) — the strategic build, the 2022 drawdown,
    and the refill, all in one picture."""
    s = (spr_kbbl / 1000.0).dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_dx(s.index), y=_plot_y(s, 0), name="US SPR",
        line={"color": C["blue"], "width": 1.8}, fill="tozeroy",
        fillcolor="rgba(40,95,255,0.07)",
        hovertemplate="%{x}<br>%{y} MMbbl<extra></extra>"))
    cap = config.load()["strategic_reserves"]["spr_capacity_mb"]
    fig.add_hline(y=cap, line_dash="dot", line_color=C["faint"],
                  annotation_text=f"capacity {cap}", annotation_position="top left",
                  annotation_font_size=10)
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"gridcolor": C["grid"], "title": "MMbbl", "rangemode": "tozero"}})
    return _html(fig)


def chart_spr_vs_price(spr_kbbl: pd.Series, wti: pd.Series | None,
                       brent: pd.Series | None, years: float) -> str:
    """US SPR level (left, MMbbl) vs WTI / Brent (right, $/bbl) — the price relationship.
    Context only: SPR moves are political supply events, not a forward-return signal."""
    s = _tail_years((spr_kbbl / 1000.0).dropna(), years)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=_dx(s.index), y=_plot_y(s, 0), name="US SPR (MMbbl)",
                             line={"color": C["blue"], "width": 2.0}, yaxis="y",
                             hovertemplate="%{x}<br>SPR %{y} MMbbl<extra></extra>"))
    for px, nm, col in ((wti, "WTI ($/bbl)", C["ink"]), (brent, "Brent ($/bbl)", C["amber"])):
        if px is not None and not px.empty:
            p = _tail_years(px.dropna(), years)
            fig.add_trace(go.Scatter(x=_dx(p.index), y=_plot_y(p, 1), name=nm,
                                     line={"color": col, "width": 1.3}, yaxis="y2",
                                     hovertemplate="%{x}<br>" + nm + " %{y}<extra></extra>"))
    fig.update_layout(**{**PLOT, "height": 320,
                         "yaxis": {"gridcolor": C["grid"], "title": "SPR · MMbbl"},
                         "yaxis2": {"overlaying": "y", "side": "right", "showgrid": False,
                                    "title": "$/bbl"}})
    return _html(fig)


# --------------------------------------------------------------------------- #
# view-model
# --------------------------------------------------------------------------- #
def _us_spr_vm(spr_kbbl: pd.Series, scfg: dict) -> dict:
    """US SPR hero (live/weekly)."""
    s = sr.series(spr_kbbl)
    last_kbbl = float(s.iloc[-1])
    cap = scfg["spr_capacity_mb"]
    level_mb = last_kbbl / 1000.0
    peak_kbbl, low_kbbl = float(s.max()), float(s.min())
    vm = {
        "level_mb": _r(level_mb, 0),
        "capacity_mb": cap,
        "fill_pct": sr.fill_pct(level_mb, cap),
        "chg_4w_mb": _r((sr.change(s, 4) or 0) / 1000.0, 1),
        "chg_52w_mb": _r((sr.change(s, 52) or 0) / 1000.0, 1),
        "peak_mb": _r(peak_kbbl / 1000.0, 0), "peak_date": s.idxmax().strftime("%b %Y"),
        "low_mb": _r(low_kbbl / 1000.0, 0), "low_date": s.idxmin().strftime("%b %Y"),
        "above_low_mb": _r((last_kbbl - low_kbbl) / 1000.0, 0),
        "below_peak_mb": _r((peak_kbbl - last_kbbl) / 1000.0, 0),
        "as_of": s.index.max().strftime("%b %d, %Y"),
    }
    # days of US refinery-crude-run cover (SPR alone ÷ refiner net crude inputs, kbbl/d)
    ri = sr.series(store.read("eia", "refinery_inputs"))
    if ri is not None:
        vm["days_cover"] = sr.days_of_cover(last_kbbl, float(ri.iloc[-1]))
    return vm


def _countries_vm(scfg: dict, us_level_mb: float | None) -> list[dict]:
    rows = []
    for cfg in scfg["countries"]:
        iso = cfg["iso"]
        jodi = None if cfg.get("no_jodi") else store.read("jodi", f"crude_{iso.lower()}")
        live = us_level_mb if cfg.get("live") == "spr" else None
        rows.append(sr.merge_country_row(cfg, jodi, live_level_mb=live))
    return rows


def _gold_vm(gcfg: dict) -> dict:
    """Official central-bank gold reserves: curated tonnes + live World Bank gold
    value & share of reserves. Display-only."""
    wb_tot = store.read("worldbank", "reserves_total")
    wb_xg = store.read("worldbank", "reserves_exgold")

    def col(df, iso):
        return df[iso] if (df is not None and iso in df.columns) else None

    rows = [sr.merge_gold_row(c, col(wb_tot, c["iso"]), col(wb_xg, c["iso"]))
            for c in gcfg["countries"]]
    wb_year = next((r["wb_year"] for r in rows if r.get("wb_year")), None)
    return {
        "rows": rows,
        "top_tonnes": sr.total_official_tonnes(rows),
        "global_tonnes": gcfg.get("global_tonnes"),
        "as_of": gcfg.get("as_of", ""), "source": gcfg.get("source", ""),
        "wb_year": wb_year,
        "note_en": gcfg.get("cb_net_buying_note_en", ""),
        "note_zh": gcfg.get("cb_net_buying_note_zh", ""),
        "caveat_en": sr.GOLD_CAVEAT["en"], "caveat_zh": sr.GOLD_CAVEAT["zh"],
    }


def main() -> int:
    scfg = config.load()["strategic_reserves"]
    spr_df = store.read("eia", "spr_stocks")
    if spr_df is None or spr_df.empty:
        log.error("no EIA SPR series (data/eia/spr_stocks) — skipping SPR page")
        return 0
    spr_kbbl = sr.series(spr_df)

    us = _us_spr_vm(spr_kbbl, scfg)
    countries = _countries_vm(scfg, us["level_mb"])

    # global aggregate of ALL LIVE JODI national crude stocks (every reporting country
    # in data/jodi/, not just the curated table) — an honest "world reporters" total.
    # Recency-gated: a country whose reporting went stale (e.g. AE ended 2018) must not
    # have an old level summed into a CURRENT total.
    raw = {}
    for p in sorted((config.data_dir() / "jodi").glob("crude_*.parquet")):
        d = store.read("jodi", p.stem)
        if d is not None and not d.empty:
            raw[p.stem.replace("crude_", "").upper()] = d
    fresh = max((sr.series(d).index.max() for d in raw.values()), default=None)
    jodi_map = ({iso: d for iso, d in raw.items()
                 if (sr.series(d).index.max() >= fresh - pd.DateOffset(months=6))}
                if fresh is not None else {})
    agg = sr.global_aggregate(jodi_map)

    # oil-price overlay (Yahoo front futures, already in the store)
    def _px(t: str) -> pd.Series | None:
        df = store.read("yahoo", t)
        if df is None or df.empty:
            return None
        col = "close" if "close" in df.columns else df.columns[0]
        return sr.series(df, col)

    wti, brent = _px("CL=F"), _px("BZ=F")

    charts = {
        "history": chart_spr_history(spr_kbbl),
        "vs_price": chart_spr_vs_price(spr_kbbl, wti, brent, scfg["price_lookback_years"]),
    }

    as_of = us["as_of"]
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    gold = _gold_vm(config.load().get("gold_reserves", {"countries": []}))

    html = env.get_template("spr.html.j2").render(
        C=C, as_of=as_of, built=built, us=us, countries=countries, agg=agg,
        charts=charts, scfg=scfg, caveat=sr.SPR_CAVEAT,
        assess_word=sr.ASSESS_WORD, gold=gold)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    (site / "spr.html").write_text(html)
    log.info("wrote %s/spr.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card; runs before build_vector)
    outdir = config.data_dir() / "spr"
    outdir.mkdir(parents=True, exist_ok=True)
    latest = {
        "date": as_of,
        "us_spr_mb": us["level_mb"], "us_fill_pct": us["fill_pct"],
        "label": f"US SPR {us['level_mb']:.0f} MMbbl",
        "n_countries": len([c for c in countries if c.get("strategic_mb") or c.get("jodi_total_mb")]),
    }
    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
