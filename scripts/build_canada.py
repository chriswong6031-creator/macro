"""Build the Canada / S&P/TSX dashboard -> site/canada.html (+ canada_stock.html).

Standalone, like scripts/build_china.py — shares only the parquet store with the
other pipelines. Recomputes the Canada regime (so live == backtest), runs the cycle
engine over each sector ETF for the rotation board + MTF cards, and renders the
dark, bilingual templates/canada.html.j2. LEADS with the commodity/CAD/BoC-vs-Fed
overlay hero (the primary Canada driver). Returns 0 on ANY engine error so it can
never break the macro / vector site builds.

Usage: python -m scripts.build_canada   (run after build_site, before build_vector)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go  # noqa: E402

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_canada")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
          "charts.js", "tablesort.js")


def _range_selector() -> dict:
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


def _chart_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def _chart_regime(px: pd.Series, hist: pd.DataFrame, days: int = 3650) -> str:
    cut = px.index.max() - pd.Timedelta(days=days)
    s = px.loc[cut:].dropna()
    sub = hist.loc[cut:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s, name="TSX", line={"color": "#64748b", "width": 1.5}))
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
    fig.add_hline(y=0, line={"color": "#666", "width": 0.6})
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_yaxes(range=[-1.05, 1.05], autorange=False)
    fig.update_xaxes(rangeselector=_range_selector())
    fig.update_layout(margin={"l": 45, "r": 15, "t": 54, "b": 30}, legend={"orientation": "h", "y": 1.18})
    return _chart_html(fig)


def _chart_curve(days: int = 2600) -> str:
    """BoC policy rate + GoC 2y/10y yields over ~10y (the rate-path / curve panel)."""
    pr, g2, g10 = (store.read("canada_macro", c) for c in ("policy_rate", "goc_2y", "goc_10y"))
    if g2 is None or g10 is None:
        return ""
    fig = go.Figure()
    series = [("policy_rate", pr, "#c08bd8", "BoC policy"),
              ("goc_2y", g2, "#3f9fd8", "GoC 2y"),
              ("goc_10y", g10, "#5fbf7f", "GoC 10y")]
    cut = g10.index.max() - pd.Timedelta(days=days)
    for col, df, color, label in series:
        if df is None or df.empty:
            continue
        s = df[df.index >= cut].iloc[:, 0].dropna()
        fig.add_trace(go.Scatter(x=s.index, y=s, name=label, line={"color": color, "width": 1.4}))
    fig.update_layout(**PLOT_LAYOUT, showlegend=True)
    fig.update_xaxes(rangeselector=_range_selector())
    fig.update_layout(margin={"l": 45, "r": 15, "t": 44, "b": 30}, legend={"orientation": "h", "y": 1.14})
    return _chart_html(fig)


def canada_regime_timeline(hist: pd.DataFrame) -> dict:
    """Compact columnar JSON for the client-side Time Machine (timemachine.js),
    mirroring build_china.china_regime_timeline. The Canada engine doesn't track
    transition/recession/shock/warning flags, so those carry safe defaults."""
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


def _lifespan_rows(quad: pd.Series) -> list[dict]:
    from engine.playbook import QUAD_SHORT, next_quads_line, transition_stats
    trans = transition_stats(quad)
    rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        rows.append({"name": QUAD_SHORT[q], "n": trans["n_by_quad"].get(q, "—"),
                     "median": trans["median_days"].get(q, "—"),
                     "next": next_quads_line(nxt), "next_zh": next_quads_line(nxt, zh=True)})
    return rows


def _health_rows() -> list[dict]:
    sources = store.read_status().get("sources", {})
    labels = {"canada_prices": ("Prices / sectors", "价格 / 板块"),
              "canada_macro": ("Macro (BoC / StatsCan / FRED)", "宏观 (央行 / 统计局 / FRED)"),
              "canada_breadth": ("Breadth", "市场宽度")}
    rows = []
    for key, (en, zh) in labels.items():
        s = sources.get(key)
        if not s:
            continue
        rows.append({"en": en, "zh": zh, "status": s.get("status", "?"),
                     "rows": s.get("rows", 0), "last": s.get("last_date") or "—"})
    return rows


def _action_board(sectors: list[dict]) -> dict:
    """Bucket the sector cards' cycle-entry calls into a 'what to act on' board."""
    buy_now, buy_soon, take_profits, hold, avoid = [], [], [], [], []
    for s in sectors:
        e = s.get("entry") or {}
        item = {"ticker": s["ticker"], "name": s["name"], "label": s.get("label") or s.get("state"),
                "tag": e.get("tag", ""), "days": e.get("days_hi"), "dir": s.get("dir")}
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
    return {"buy_now": buy_now, "buy_soon": buy_soon, "take_profits": take_profits,
            "hold": hold, "avoid": avoid}


def _sector_cards(latest: dict) -> list[dict]:
    """Merge the RS-rank table (from the regime run) with per-sector cycle analysis."""
    from engine.canada_inputs import canada_closes
    from engine.cycles import analyze
    names = config.load()["canada"]["yahoo"]["sector_etfs"]
    closes = canada_closes()
    rs_by = {r["ticker"]: r for r in latest.get("sector_rs", [])}
    cards = []
    for t, meta in names.items():
        if t not in closes.columns:
            continue
        close = closes[t].dropna()
        if len(close) < 60:
            continue
        try:
            a = analyze(close)
        except Exception as e:  # noqa: BLE001
            log.warning("canada sector analyze failed for %s: %s", t, e)
            continue
        lad, cyc = a["ladder"], a["cycle"]
        rs = rs_by.get(t, {})
        cards.append({
            "ticker": t, "name": meta[0], "tv": meta[1] if len(meta) > 1 else "",
            "rank": rs.get("rank"), "mom20": rs.get("mom_20d_pct"),
            "mom60": rs.get("mom_60d_pct"), "above200": rs.get("above_200d_trend"),
            "pctile": rs.get("pctile_252d"),
            "state": lad.get("state"), "label": lad.get("label"),
            "action": lad.get("action"), "dir": lad.get("dir"),
            "entry": lad.get("entry"),
            "age_short": lad.get("age_short"), "age_short_zh": lad.get("age_short_zh"),
            "eq_badge": lad.get("eq_badge"), "eq_dir": lad.get("eq_dir"),
            "eq_tip": lad.get("eq_tip"),
            "why": lad.get("why"), "regime_label": lad.get("regime_label"),
            "dc_day": cyc.get("dc_day"), "dc_band": cyc.get("dc_band"),
            "ic_week": cyc.get("ic_week"), "ic_band": cyc.get("ic_band"),
            "mtf_json": json.dumps(a["mtf"]),
            "price": round(float(close.iloc[-1]), 3),
        })
    cards.sort(key=lambda c: (c["rank"] is None, c["rank"] or 999))
    return cards


def _breadth() -> dict | None:
    """Market breadth — how many TSX names are actually participating. Computed across
    the FULL S&P/TSX Composite universe (~220 names via the XIC holdings cache) for a
    true full-market read, not just the curated large-cap gauge; falls back to the
    curated breadth.parquet if the universe cache is missing/sparse. DISPLAY-ONLY."""
    from collectors.breadth import BreadthAdapter, breadth_summary
    closes = store.read("canada_search", "closes")
    if closes is not None and not closes.empty and closes.shape[1] >= 120:
        return breadth_summary(BreadthAdapter().compute(closes), full=True)
    return breadth_summary(store.read("canada_breadth", "breadth"), full=False)


def _benchmark_card() -> dict | None:
    """Headline cycle card for the S&P/TSX Composite (deep history)."""
    from engine.cycles import analyze
    mi = config.load()["canada"]["yahoo"]["market_index"]
    df = store.read("canada", mi)
    if df is None or "close" not in df.columns:
        return None
    close = df["close"].dropna()
    a = analyze(close)
    return {"name": "S&P/TSX Composite", "ticker": mi,
            "mtf_json": json.dumps(a["mtf"]),
            "state": a["ladder"].get("state"), "label": a["ladder"].get("label"),
            "dc_day": a["cycle"].get("dc_day"), "dc_band": a["cycle"].get("dc_band"),
            "ic_week": a["cycle"].get("ic_week"), "ic_band": a["cycle"].get("ic_band"),
            "price": round(float(close.iloc[-1]), 2),
            "chg": round(100 * (close.iloc[-1] / close.iloc[-2] - 1), 2)}


def _housing_note() -> dict | None:
    """Housing / household-debt fragility context from FRED real house prices
    (BIS QCAR628BIS). Display-only; degrades to None when FRED is absent."""
    hp = store.read("canada_macro", "house_prices")
    if hp is None or hp.empty:
        return None
    s = hp.iloc[:, 0].dropna()
    if len(s) < 5:
        return None
    yoy = (s.iloc[-1] / s.iloc[-5] - 1) * 100 if len(s) >= 5 else None   # quarterly -> ~1y
    off_peak = (s.iloc[-1] / s.max() - 1) * 100
    return {"level": round(float(s.iloc[-1]), 1),
            "yoy": round(float(yoy), 1) if yoy is not None else None,
            "off_peak": round(float(off_peak), 1),
            "asof": str(s.index.max().date())}


def _build_history(env, latest: dict, generated: str) -> None:
    from engine.playbook import QUAD_SHORT, next_quads_line, transition_stats
    hist = store.read("canada_regime", "regime_history")
    if hist is None or "quad" not in hist.columns:
        log.warning("canada history: no regime_history; skipping history page")
        return
    mi = config.load()["canada"]["yahoo"]["market_index"]
    mdf = store.read("canada", mi)
    px = mdf["close"] if mdf is not None else pd.Series(dtype=float)
    trans = transition_stats(hist["quad"])
    rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        rows.append({"name": QUAD_SHORT[q], "n": trans["n_by_quad"].get(q, "—"),
                     "median": trans["median_days"].get(q, "—"),
                     "next": next_quads_line(nxt), "next_zh": next_quads_line(nxt, zh=True)})
    html = env.get_template("canada_history.html.j2").render(
        latest=latest, generated_utc=generated,
        chart_regime=_chart_regime(px, hist) if not px.empty else "", chart_axes=_chart_axes(hist),
        lifespan_rows=rows)
    (Path(config.load()["storage"]["site_dir"]) / "canada_history.html").write_text(html)
    log.info("wrote canada_history.html (%d regime periods)", trans.get("n_segments", 0))


def _build_sector_pages(env) -> int:
    """Per-sector drill-down: the ETF's own cycle + each curated constituent analyzed."""
    from engine.canada_inputs import canada_closes
    from engine.cycles import analyze
    from scripts.build_canada_library import tv_symbol
    cfg = config.load()["canada"]
    names = cfg["yahoo"]["sector_etfs"]
    constituents = cfg["constituents"]
    # map sector-ETF plain name -> the constituents sector key (best-effort)
    sect_alias = {"Financials": "Financials", "Banks": "Financials", "Energy": "Energy",
                  "Gold Miners": "Materials", "Materials": "Materials", "Base Metals": "Materials",
                  "Information Technology": "Technology", "Utilities": "Utilities",
                  "Real Estate": "Real Estate", "Consumer Staples": "Staples",
                  "Consumer Discretionary": "Discretionary", "Communication Services": "Communication"}
    closes = canada_closes()
    cache = config.data_dir() / "canada_breadth" / "_closes_cache.parquet"
    ccloses = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    outdir = Path(config.load()["storage"]["site_dir"]) / "sectors"
    outdir.mkdir(parents=True, exist_ok=True)
    built = 0
    for fund, meta in names.items():
        if fund not in closes.columns:
            continue
        close = closes[fund].dropna()
        if len(close) < 60:
            continue
        try:
            a = analyze(close)
        except Exception as e:  # noqa: BLE001
            log.warning("canada sector page %s analyze failed: %s", fund, e)
            continue
        s = {"fund": fund, "name": meta[0], "tv": tv_symbol(fund),
             "mtf_json": json.dumps(a["mtf"]), "ladder": a["ladder"], "cycle": a["cycle"],
             "holdings": []}
        for tick in constituents.get(sect_alias.get(meta[0], meta[0]), []):
            cser = ccloses[tick].dropna() if tick in ccloses.columns else None
            if cser is None or len(cser) < 250:
                continue
            try:
                h = analyze(cser)
            except Exception:  # noqa: BLE001
                continue
            s["holdings"].append({"ticker": tick, "ladder": h["ladder"], "cycle": h["cycle"],
                                  "mtf_json": json.dumps(h["mtf"])})
        (outdir / f"{fund}.html").write_text(env.get_template("canada_sector.html.j2").render(s=s))
        built += 1
    log.info("wrote %d canada sector pages", built)
    return built


# ---- quad meanings (Canada framing) -------------------------------------------
QUAD_MEANING = {
    "Goldilocks": ("growth ↑ inflation ↓ — tech / discretionary / banks lead",
                   "增长 ↑ 通胀 ↓ — 科技／可选消费／银行领先"),
    "Reflation": ("growth ↑ inflation ↑ — energy / materials / gold / financials lead",
                  "增长 ↑ 通胀 ↑ — 能源／材料／黄金／金融领先"),
    "Stagflation": ("growth ↓ inflation ↑ — energy / gold / materials / utilities",
                    "增长 ↓ 通胀 ↑ — 能源／黄金／材料／公用事业"),
    "Growth-scare": ("growth ↓ inflation ↓ — utilities / staples / telecom / banks",
                     "增长 ↓ 通胀 ↓ — 公用事业／必需消费／电信／银行"),
}


def main() -> int:
    try:
        from engine.canada_run import run
        latest = run()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("canada engine failed (%s); skipping canada page", e)
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
            "actions": _action_board(sectors),
            "health": _health_rows(),
            "overlay": latest.get("overlay", {}),
            "coupling": (latest.get("overlay") or {}).get("coupling", {}),
            "housing": _housing_note(),
            "curve_chart": _chart_curve(),
            "quad_meaning": QUAD_MEANING.get(latest.get("quad_name")),
        }
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        # regime history -> Time Machine JSON + lifespan base rates
        hist = store.read("canada_regime", "regime_history")
        if hist is not None and "quad" in hist.columns:
            (site / "canada_regime_timeline.json").write_text(
                json.dumps(canada_regime_timeline(hist), separators=(",", ":")))
            vm["lifespan_rows"] = _lifespan_rows(hist["quad"])
            vm["axes_chart"] = _chart_axes(hist, days=1825)

        # residual-alpha leg (per-stock signal + alpha-led leaders)
        alpha = None
        try:
            from scripts.build_canada_library import compute_canada_alpha
            alpha = compute_canada_alpha()
            vm["alpha"] = alpha
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("canada alpha build failed (%s); skipping", e)
            vm["alpha"] = None

        # build the per-ticker stock library NOW (records carry ladder + alpha) and
        # capture the cross-sectional alpha-led "Top setups" ranking for canada.html.
        setups = None
        try:
            from scripts import build_canada_library
            setups = build_canada_library.main(alpha=alpha)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("canada stock library build failed (%s); skipping", e)
        vm["setups"] = setups

        # enrich the alpha-led setups shortlist into "Standout individual stocks" cards
        try:
            from scripts.build_canada_library import compute_canada_standouts
            vm["setups"] = compute_canada_standouts(setups)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("canada standouts enrich failed (%s); using raw setups", e)

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        # One shared view-model feeds BOTH the Canada macro-regime page and the new
        # TSX Stock Dashboard — the same canada.html.j2 is rendered twice with a `mode`
        # flag (macro / stocks) that selects which sections show. Mirrors China / HK.
        tmpl = env.get_template("canada.html.j2")
        html = tmpl.render(**vm, mode="macro")
        (site / "canada.html").write_text(html)
        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                (site / a).write_text(src.read_text())
        log.info("wrote %s/canada.html (%d KB, %d sectors)", site, len(html) // 1024, len(vm["sectors"]))

        # TSX Stock Dashboard — same VM, the standout-names half (show-more card strip).
        html_st = tmpl.render(**vm, mode="stocks")
        (site / "canada_stocks.html").write_text(html_st)
        log.info("wrote %s/canada_stocks.html (%d KB)", site, len(html_st) // 1024)
        # landing-hub card stat (presence-gated by the .html existing)
        _su = vm.get("setups") or {}
        _n = len(_su.get("buy") or [])
        cadir = config.data_dir() / "canada_stocks"
        cadir.mkdir(parents=True, exist_ok=True)
        (cadir / "latest.json").write_text(json.dumps(
            {"date": latest.get("date", ""),
             "label": (f"{_n} standout TSX names" if _n else "TSX standouts · alpha · setups"),
             "n_setups": _n}, indent=2))

        # TSX stock search shell (the per-ticker library was built above)
        try:
            from engine.cycles import STATE_DISPLAY
            stock_html = env.get_template("canada_stock.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str),
                generated_utc=vm["built"])
            (site / "canada_stock.html").write_text(stock_html)
            log.info("wrote %s/canada_stock.html + canadastockdata/", site)
        except Exception as e:  # noqa: BLE001 — search is additive, never fatal
            log.error("canada stock search render failed (%s); skipping", e)

        # history page (regime-over-index + the two dials + lifespan base rates)
        try:
            _build_history(env, latest, vm["built"])
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("canada history build failed (%s); skipping", e)

        # per-sector drill-down pages
        try:
            _build_sector_pages(env)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("canada sector pages build failed (%s); skipping", e)
    except Exception as e:  # noqa: BLE001
        log.error("canada page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
