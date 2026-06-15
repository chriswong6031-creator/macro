"""Build the Hong Kong / Hang Seng dashboard -> site/hk.html.

Standalone, like scripts/build_china.py — shares only the parquet store with the
other pipelines. Recomputes the HK regime (so live == backtest), runs the cycle
engine over each synthetic sector basket for the rotation board + MTF cards, and
renders the dark, bilingual templates/hk.html.j2 with a GLOBAL RISK OVERLAY hero
(HK's primary driver). Returns 0 on ANY engine error so it can never break the
macro / china / vector site builds.

Usage: python -m scripts.build_hk   (run after build_site/build_china, before build_vector)
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go  # noqa: E402

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_hk")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
          "charts.js", "tablesort.js")


def _range_selector() -> dict:
    """1M…All range-selector buttons (theme-neutral; charts.js rescales y on zoom)."""
    return dict(
        buttons=[dict(count=3, label="3M", step="month", stepmode="backward"),
                 dict(count=6, label="6M", step="month", stepmode="backward"),
                 dict(count=1, label="YTD", step="year", stepmode="todate"),
                 dict(count=1, label="1Y", step="year", stepmode="backward"),
                 dict(count=3, label="3Y", step="year", stepmode="backward"),
                 dict(step="all", label="All")],
        bgcolor="rgba(128,138,160,0.14)", activecolor="rgba(120,167,224,0.55)",
        bordercolor="rgba(128,138,160,0.30)", borderwidth=1,
        font={"size": 10, "color": "#8b93a1"}, x=0, xanchor="left", y=1.0, yanchor="bottom")

QUAD_COLORS = {"Q1": "#2e9e4f", "Q2": "#d4a017", "Q3": "#d04545", "Q4": "#3f78d8"}
PLOT_LAYOUT = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"size": 11, "color": "#8b93a1"},
    xaxis={"gridcolor": "rgba(128,138,160,0.16)", "zerolinecolor": "rgba(128,138,160,0.28)"},
    yaxis={"gridcolor": "rgba(128,138,160,0.16)", "zerolinecolor": "rgba(128,138,160,0.28)"},
    margin={"l": 45, "r": 15, "t": 10, "b": 30}, height=300,
    legend={"orientation": "h", "y": 1.08})


def tv_symbol(ticker: str) -> str:
    """TradingView symbol for an HK ticker. `0700.HK -> HKEX:700` (strip leading
    zeros); indices fall back to a sensible TV symbol."""
    if ticker.endswith(".HK"):
        code = ticker[:-3].lstrip("0") or "0"
        return f"HKEX:{code}"
    return {"^HSI": "HSI", "^HSCE": "HKEX:HSCEI", "^HSCC": "HSI"}.get(ticker, ticker)


def sector_slug(name: str) -> str:
    return "hk-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _chart_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def _chart_regime(px: pd.Series, hist: pd.DataFrame, days: int = 3650) -> str:
    cut = px.index.max() - pd.Timedelta(days=days)
    s = px.loc[cut:].dropna()
    sub = hist.loc[cut:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s, name="HSI", line={"color": "#64748b", "width": 1.5}))
    q = sub["quad"].dropna()
    if not q.empty:
        seg_id = (q != q.shift()).cumsum()
        for _, seg in q.groupby(seg_id):
            fig.add_vrect(x0=seg.index.min(), x1=seg.index.max(),
                          fillcolor=QUAD_COLORS.get(seg.iloc[0], "#888"), opacity=0.16, line_width=0)
    fig.update_layout(**PLOT_LAYOUT, showlegend=False)
    fig.update_xaxes(rangeselector=_range_selector())
    fig.update_layout(margin={"l": 45, "r": 15, "t": 40, "b": 30})
    return _chart_html(fig)


def _chart_axes(hist: pd.DataFrame, days: int = 3650) -> str:
    cut = hist.index.max() - pd.Timedelta(days=days)
    sub = hist.loc[cut:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub.index, y=sub["growth_score"], name="growth",
                             line={"color": "#5fbf7f", "width": 1.2}))
    fig.add_trace(go.Scatter(x=sub.index, y=sub["inflation_score"], name="inflation",
                             line={"color": "#e07070", "width": 1.2}))
    if "global_score" in sub.columns:
        fig.add_trace(go.Scatter(x=sub.index, y=sub["global_score"], name="global risk",
                                 line={"color": "#d4a017", "width": 1.0, "dash": "dot"}))
    fig.add_hline(y=0, line={"color": "#666", "width": 0.6})
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_yaxes(range=[-1.05, 1.05], autorange=False)   # fixed ±1 band — charts.js leaves it alone
    fig.update_xaxes(rangeselector=_range_selector())
    fig.update_layout(margin={"l": 45, "r": 15, "t": 54, "b": 30}, legend={"orientation": "h", "y": 1.18})
    return _chart_html(fig)


def _basket_series(cc: pd.DataFrame, members: list[str]) -> pd.Series:
    from engine.hk_inputs import sector_basket
    return sector_basket(cc, members).dropna()


def _sector_cards(latest: dict) -> list[dict]:
    """Merge the RS-rank table (from the regime run) with per-basket cycle analysis."""
    from engine.cycles import analyze
    from engine.hk_inputs import constituent_closes
    sectors = config.load()["hk"]["sectors"]
    cc = constituent_closes()
    rs_by = {r["ticker"]: r for r in latest.get("sector_rs", [])}
    cards = []
    for name, meta in sectors.items():
        basket = _basket_series(cc, meta["members"])
        if len(basket) < 60:
            continue
        try:
            a = analyze(basket)
        except Exception as e:  # noqa: BLE001
            log.warning("hk sector analyze failed for %s: %s", name, e)
            continue
        lad, cyc = a["ladder"], a["cycle"]
        rs = rs_by.get(name, {})
        cards.append({
            "ticker": sector_slug(name), "name": name, "tv": meta.get("tv", ""),
            "rank": rs.get("rank"), "mom20": rs.get("mom_20d_pct"),
            "mom60": rs.get("mom_60d_pct"), "above200": rs.get("above_200d_trend"),
            "pctile": rs.get("pctile_252d"),
            "state": lad.get("state"), "label": lad.get("label"),
            "action": lad.get("action"), "dir": lad.get("dir"),
            "age_short": lad.get("age_short"), "age_short_zh": lad.get("age_short_zh"),
            "why": lad.get("why"), "regime_label": lad.get("regime_label"),
            "dc_day": cyc.get("dc_day"), "dc_band": cyc.get("dc_band"),
            "ic_week": cyc.get("ic_week"), "ic_band": cyc.get("ic_band"),
            "mtf_json": json.dumps(a["mtf"]),
        })
    cards.sort(key=lambda c: (c["rank"] is None, c["rank"] or 999))
    return cards


def _benchmark_card() -> dict | None:
    """Headline cycle card for the Hang Seng Index (deep 1986-> history)."""
    from engine.cycles import analyze
    mi = config.load()["hk"]["yahoo"]["market_index"]
    df = store.read("hk", mi)
    if df is None or "close" not in df.columns:
        return None
    close = df["close"].dropna()
    a = analyze(close)
    return {"name": "Hang Seng Index", "ticker": mi,
            "mtf_json": json.dumps(a["mtf"]),
            "state": a["ladder"].get("state"), "label": a["ladder"].get("label"),
            "dir": a["ladder"].get("dir"),
            "dc_day": a["cycle"].get("dc_day"), "dc_band": a["cycle"].get("dc_band"),
            "ic_week": a["cycle"].get("ic_week"), "ic_band": a["cycle"].get("ic_band"),
            "price": round(float(close.iloc[-1]), 2),
            "chg": round(100 * (close.iloc[-1] / close.iloc[-2] - 1), 2)}


def _breadth() -> dict | None:
    br = store.read("hk_breadth", "breadth")
    if br is None or br.empty:
        return None
    last = br.iloc[-1]
    return {
        "pct_above_50": round(float(last.get("pct_above_50", float("nan"))), 1),
        "pct_above_200": round(float(last.get("pct_above_200", float("nan"))), 1),
        "nh": int(last.get("nh", 0)), "nl": int(last.get("nl", 0)),
        "ad_trend": "up" if br["ad_line"].diff(20).iloc[-1] > 0 else "down",
        "n_members": int(last.get("n_members", 0)),
        "pct50_chg20": round(float(br["pct_above_50"].diff(20).iloc[-1]), 1),
    }


def _build_sector_pages(env) -> int:
    """Per-sector drill-down: the basket's own cycle + each curated constituent
    analyzed. Output site/sectors/<slug>.html."""
    from engine.cycles import analyze
    from engine.hk_inputs import constituent_closes
    cfg = config.load()["hk"]
    sectors = cfg["sectors"]
    names = cfg.get("names", {})
    cc = constituent_closes()
    outdir = Path(config.load()["storage"]["site_dir"]) / "sectors"
    outdir.mkdir(parents=True, exist_ok=True)
    built = 0
    for name, meta in sectors.items():
        basket = _basket_series(cc, meta["members"])
        if len(basket) < 60:
            continue
        try:
            a = analyze(basket)
        except Exception as e:  # noqa: BLE001
            log.warning("hk sector page %s analyze failed: %s", name, e)
            continue
        from scripts.build_hk_library import chart_series
        s = {"fund": name, "name": name, "tv": meta.get("tv", ""),
             "mtf_json": json.dumps(a["mtf"]), "ladder": a["ladder"], "cycle": a["cycle"],
             "chart_json": json.dumps(chart_series(basket)), "holdings": []}
        for tick in meta["members"]:
            cser = cc[tick].dropna() if tick in cc.columns else None
            if cser is None or len(cser) < 250:
                continue
            try:
                h = analyze(cser)
            except Exception:  # noqa: BLE001
                continue
            s["holdings"].append({"ticker": tick, "name": names.get(tick, tick),
                                  "ladder": h["ladder"], "cycle": h["cycle"],
                                  "mtf_json": json.dumps(h["mtf"])})
        (outdir / f"{sector_slug(name)}.html").write_text(env.get_template("hk_sector.html.j2").render(s=s))
        built += 1
    log.info("wrote %d hk sector pages", built)
    return built


def _build_history(env, latest: dict, generated: str) -> None:
    from engine.playbook import QUAD_SHORT, next_quads_line, transition_stats
    hist = store.read("hk_regime", "regime_history")
    if hist is None or "quad" not in hist.columns:
        log.warning("hk history: no regime_history; skipping history page")
        return
    mi = config.load()["hk"]["yahoo"]["market_index"]
    mdf = store.read("hk", mi)
    px = mdf["close"] if mdf is not None else pd.Series(dtype=float)
    trans = transition_stats(hist["quad"])
    rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        rows.append({"name": QUAD_SHORT[q], "n": trans["n_by_quad"].get(q, "—"),
                     "median": trans["median_days"].get(q, "—"),
                     "next": next_quads_line(nxt), "next_zh": next_quads_line(nxt, zh=True)})
    html = env.get_template("hk_history.html.j2").render(
        latest=latest, generated_utc=generated,
        chart_regime=_chart_regime(px, hist) if not px.empty else "", chart_axes=_chart_axes(hist),
        lifespan_rows=rows)
    (Path(config.load()["storage"]["site_dir"]) / "hk_history.html").write_text(html)
    log.info("wrote hk_history.html (%d regime periods)", trans.get("n_segments", 0))


def _panel_line(series: dict, color: str, height: int = 190, zero: bool = False,
                fill: bool = False, hline: float | None = None, hline_text: str = "") -> str:
    """Single-line panel chart from an internals {dates, vals} dict."""
    if not series or not series.get("dates"):
        return ""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(series["dates"]), y=series["vals"], mode="lines",
        line={"color": color, "width": 1.5}, fill="tozeroy" if fill else None,
        fillcolor=("rgba(63,120,216,0.10)" if fill else None)))
    if zero:
        fig.add_hline(y=0, line={"color": "rgba(128,138,160,0.5)", "width": 0.8})
    if hline is not None:
        fig.add_hline(y=hline, line={"color": "#d04545", "width": 0.8, "dash": "dot"},
                      annotation_text=hline_text, annotation_position="top left",
                      annotation_font={"size": 10, "color": "#d04545"})
    fig.update_layout(**{**PLOT_LAYOUT, "height": height}, showlegend=False)
    return _chart_html(fig)


def hk_regime_timeline(hist: pd.DataFrame) -> dict:
    """Compact columnar JSON for the client-side Time Machine (timemachine.js),
    mirroring build_site.regime_timeline() over the HK regime history. HK doesn't
    track transition_state / recession / shock / warning flags, so those carry safe
    defaults — timemachine.js degrades to 'no warnings'."""
    h = hist[hist["quad"].notna()].copy()
    n = len(h)

    def r3(col: str) -> list:
        return [None if pd.isna(v) else round(float(v), 3) for v in h[col]]

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in h.index],
        "quad":  h["quad"].fillna("").tolist(),
        "g":     r3("growth_score"),
        "i":     r3("inflation_score"),
        "conf":  r3("regime_confidence"),
        "liq":   h["liquidity"].fillna("unknown").tolist() if "liquidity" in h else ["unknown"] * n,
        "cyc":   h["cycle"].fillna("unknown").tolist() if "cycle" in h else ["unknown"] * n,
        "trans": ["STABLE"] * n, "rec": [0] * n, "shock": [0] * n, "flags": [0] * n,
        "flag_order": [],
    }


def _internals_vm(latest: dict) -> dict:
    """HK market-internals panels: Southbound Connect flow (the #1 HK flow) +
    a slim China credit/policy backdrop (HSI is China-earnings-driven). Reuses the
    china_internals view-models verbatim — these stores are shared, read HK-side.
    Each piece is None-safe so a missing source just drops its panel."""
    from engine import china_internals as ci
    vm: dict = {}
    sb = ci.southbound_flow()
    if sb:
        sb["chart_html"] = _panel_line(sb.get("chart_cum"), "#3f78d8", height=190, zero=True, fill=True)
        if sb.get("hold_chart"):
            sb["hold_html"] = _panel_line(sb["hold_chart"], "#5fbf7f", height=150)
        vm["southbound"] = sb
    credit = ci.credit_tape()
    if credit:
        if credit.get("impulse_chart"):
            credit["impulse_html"] = _panel_line(credit["impulse_chart"], "#3f9fd8", height=170, zero=True)
        vm["credit"] = credit
    pboc = ci.pboc_policy()
    if pboc:
        vm["pboc"] = pboc
    return vm


def _funding_vm(latest: dict) -> dict | None:
    """HKMA peg-funding panel — the Aggregate Balance drains when HKMA defends the
    7.85 weak-side peg (the real HK funding-tightening mechanism), + HIBOR + TWI."""
    h = store.read("hkma", "interbank_liquidity")
    if h is None or h.empty or "agg_balance" not in h.columns:
        return None
    ab = h["agg_balance"].dropna()
    if ab.empty:
        return None
    latest_ab = float(ab.iloc[-1])
    yr_ago = float(ab.iloc[-252]) if len(ab) > 252 else None
    out = {
        "agg_balance": round(latest_ab),
        "agg_chg_1y_pct": round(100 * (latest_ab / yr_ago - 1), 1) if yr_ago else None,
        "agg_pctile": int(round((ab <= latest_ab).mean() * 100)),
        "agg_max": round(float(ab.max())),
        "chart_html": _panel_line({"dates": [d.strftime("%Y-%m-%d") for d in ab.index],
                                    "vals": [round(float(v)) for v in ab]}, "#d4a017", height=200, fill=True),
    }
    for col, key in (("hibor_on", "hibor_on"), ("hibor_1m", "hibor_1m"),
                     ("twi", "twi"), ("base_rate", "base_rate")):
        s = h[col].dropna() if col in h.columns else pd.Series(dtype=float)
        if not s.empty:
            out[key] = round(float(s.iloc[-1]), 2)
            if col == "hibor_on":
                out["hibor_on_chg20"] = round(float(s.iloc[-1] - s.iloc[-21]), 2) if len(s) > 21 else None
    # peg state from the global snapshot
    gv = latest.get("global_snapshot") or {}
    out["peg"] = gv.get("peg")
    return out


def _lifespan_rows(quad: pd.Series) -> list[dict]:
    """Per-quad base rates (count, median length, two most-common next quads)."""
    from engine.playbook import QUAD_SHORT, next_quads_line, transition_stats
    trans = transition_stats(quad)
    rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        rows.append({"name": QUAD_SHORT[q], "n": trans["n_by_quad"].get(q, "—"),
                     "median": trans["median_days"].get(q, "—"),
                     "next": next_quads_line(nxt), "next_zh": next_quads_line(nxt, zh=True)})
    return rows


def _vhsi_vm() -> dict | None:
    """VHSI — HK's own fear gauge (HSI 30-day implied vol). level + percentile + 20d chg."""
    v = store.read("hk", "^HSIL")
    if v is None or "close" not in v.columns:
        return None
    s = v["close"].dropna()
    if s.empty:
        return None
    latest = float(s.iloc[-1])
    return {"level": round(latest, 2),
            "pctile": int(round((s <= latest).mean() * 100)),
            "chg20": round(latest - float(s.iloc[-21]), 2) if len(s) > 21 else None}


def main() -> int:
    try:
        from engine.hk_run import run
        latest = run()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("hk engine failed (%s); skipping hk page", e)
        return 0

    try:
        sectors = _sector_cards(latest)
        vm = {
            "latest": latest,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "sectors": sectors,
            "breadth": _breadth(),
            "benchmark": _benchmark_card(),
            "pair": latest.get("pair_ratios", {}),
            "pref": latest.get("preference_check", {}),
            "gv": latest.get("global_snapshot", {}),
            "vhsi": _vhsi_vm(),
        }
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        # market-internals (southbound flow + China credit/policy backdrop) — None-safe
        try:
            vm["internals"] = _internals_vm(latest)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk internals build failed (%s); skipping", e)
            vm["internals"] = {}

        # HKMA peg-funding panel (Aggregate Balance + HIBOR + TWI)
        try:
            vm["funding"] = _funding_vm(latest)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk funding panel failed (%s); skipping", e)
            vm["funding"] = None

        # AH-premium computed basket (H-share vs A-share twin, FX-adjusted)
        try:
            from engine.hk_ah import ah_basket
            ah = ah_basket()
            if ah and ah.get("chart"):
                ah["chart_html"] = _panel_line(ah["chart"], "#c08bd8", height=190, zero=True)
            vm["ah"] = ah
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk AH premium failed (%s); skipping", e)
            vm["ah"] = None

        # regime history -> Time Machine JSON + lifespan base rates
        hist = store.read("hk_regime", "regime_history")
        if hist is not None and "quad" in hist.columns:
            (site / "hk_regime_timeline.json").write_text(
                json.dumps(hk_regime_timeline(hist), separators=(",", ":")))
            vm["lifespan_rows"] = _lifespan_rows(hist["quad"])

        # playbook — quad meaning, lifespan progress, next-quad odds, exposure dial
        try:
            from engine import hk_playbook
            vm["pb"] = hk_playbook.build(latest, hist, sectors, vm.get("internals") or {})
            if vm["pb"] and vm["pb"].get("preferred"):   # sector NAME -> drill-down slug
                for x in vm["pb"]["preferred"]:
                    x["slug"] = sector_slug(x.get("ticker", ""))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk playbook build failed (%s); skipping", e)
            vm["pb"] = None

        # per-stock GLOBAL-RISK BETA — the honest per-name HK read (HK has no residual
        # stock-selection alpha; engine/hk_global_beta.py). Built here so the
        # "amplifiers vs cushions" board renders server-side, and the betas embed into
        # the stock library below. Conditioned on the live global risk_state.
        betas = None
        try:
            from scripts import build_hk_library
            betas = build_hk_library.main()
            vm["betas"] = betas
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk global-beta / stock library build failed (%s); skipping", e)
            vm["betas"] = None

        # consolidated SCOREBOARD — the HK parallel of the China screener: ONE toggle
        # (Amplifiers / Cushions / All) over the validated global-risk-beta read, each
        # row enriched with price + cycle. Built after the library so hkstockdata/ exists.
        try:
            sb = build_hk_library.compute_hk_scoreboard(betas)
            vm["hk_scoreboard"] = sb
            if sb:
                (site / "factordata" / "hk_scoreboard.json").write_text(
                    json.dumps(sb, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk scoreboard build failed (%s); skipping", e)
            vm["hk_scoreboard"] = None

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        html = env.get_template("hk.html.j2").render(**vm)
        (site / "hk.html").write_text(html)
        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                (site / a).write_text(src.read_text())
        log.info("wrote %s/hk.html (%d KB, %d sectors)", site, len(html) // 1024, len(vm["sectors"]))

        # HK stock search shell (the per-ticker library was built above, before the
        # hk.html render, so its global-beta board could feed the page)
        try:
            from engine.cycles import STATE_DISPLAY
            stock_html = env.get_template("hk_stock.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str),
                generated_utc=vm["built"])
            (site / "hk_stock.html").write_text(stock_html)
            log.info("wrote %s/hk_stock.html + hkstockdata/", site)
        except Exception as e:  # noqa: BLE001 — search is additive, never fatal
            log.error("hk stock search render failed (%s); skipping", e)

        # history page (regime-over-HSI + the dials + lifespan base rates)
        try:
            _build_history(env, latest, vm["built"])
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk history build failed (%s); skipping", e)

        # per-sector drill-down pages (basket cycle + curated constituents)
        try:
            _build_sector_pages(env)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk sector pages build failed (%s); skipping", e)

        # daily bilingual narrative brief
        try:
            from scripts import hk_brief
            hk_brief.main()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk brief build failed (%s); skipping", e)
    except Exception as e:  # noqa: BLE001
        log.error("hk page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
