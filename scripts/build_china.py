"""Build the China A-share dashboard -> site/china.html.

Standalone, like scripts/build_vector.py — shares only the parquet store with the
other pipelines. Recomputes the China regime (so live == backtest), runs the cycle
engine over each sector ETF for the rotation board + MTF cards, and renders the
dark, bilingual templates/china.html.j2. Returns 0 on ANY engine error so it can
never break the macro / vector site builds.

Usage: python -m scripts.build_china   (run after build_site, before build_vector)
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
log = logging.getLogger("build_china")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js")

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


def _chart_regime(px: pd.Series, hist: pd.DataFrame, days: int = 1095) -> str:
    cut = px.index.max() - pd.Timedelta(days=days)
    s = px.loc[cut:].dropna()
    sub = hist.loc[cut:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s, name="SHCOMP", line={"color": "#64748b", "width": 1.5}))
    q = sub["quad"].dropna()
    if not q.empty:
        seg_id = (q != q.shift()).cumsum()
        for _, seg in q.groupby(seg_id):
            fig.add_vrect(x0=seg.index.min(), x1=seg.index.max(),
                          fillcolor=QUAD_COLORS.get(seg.iloc[0], "#888"), opacity=0.16, line_width=0)
    fig.update_layout(**PLOT_LAYOUT, showlegend=False)
    return _chart_html(fig)


def _chart_axes(hist: pd.DataFrame, days: int = 1095) -> str:
    cut = hist.index.max() - pd.Timedelta(days=days)
    sub = hist.loc[cut:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub.index, y=sub["growth_score"], name="growth",
                             line={"color": "#5fbf7f", "width": 1.2}))
    fig.add_trace(go.Scatter(x=sub.index, y=sub["inflation_score"], name="inflation",
                             line={"color": "#e07070", "width": 1.2}))
    fig.add_hline(y=0, line={"color": "#666", "width": 0.6})
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_yaxes(range=[-1.05, 1.05])
    return _chart_html(fig)


def _build_sector_pages(env) -> int:
    """Per-sector drill-down: the ETF's own cycle + each curated constituent analyzed.
    Output site/sectors/<FUND>.html (e.g. site/sectors/512690.SS.html)."""
    from engine.china_inputs import china_closes
    from engine.cycles import analyze
    from scripts.build_china_library import tv_symbol
    cfg = config.load()["china"]
    names = cfg["yahoo"]["sector_etfs"]
    constituents = cfg["constituents"]
    closes = china_closes()
    cache = config.data_dir() / "china_breadth" / "_closes_cache.parquet"
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
            log.warning("china sector page %s analyze failed: %s", fund, e)
            continue
        s = {"fund": fund, "name": meta[0], "tv": tv_symbol(fund),
             "mtf_json": json.dumps(a["mtf"]), "ladder": a["ladder"], "cycle": a["cycle"],
             "holdings": []}
        for tick in constituents.get(meta[0], []):
            cser = ccloses[tick].dropna() if tick in ccloses.columns else None
            if cser is None or len(cser) < 250:
                continue
            try:
                h = analyze(cser)
            except Exception:  # noqa: BLE001
                continue
            s["holdings"].append({"ticker": tick, "ladder": h["ladder"], "cycle": h["cycle"],
                                  "mtf_json": json.dumps(h["mtf"])})
        (outdir / f"{fund}.html").write_text(env.get_template("china_sector.html.j2").render(s=s))
        built += 1
    log.info("wrote %d china sector pages", built)
    return built


def _build_history(env, latest: dict, generated: str) -> None:
    from engine.playbook import QUAD_SHORT, transition_stats
    hist = store.read("china_regime", "regime_history")
    if hist is None or "quad" not in hist.columns:
        log.warning("china history: no regime_history; skipping history page")
        return
    mi = config.load()["china"]["yahoo"]["market_index"]
    mdf = store.read("china", mi)
    px = mdf["close"] if mdf is not None else pd.Series(dtype=float)
    trans = transition_stats(hist["quad"])
    rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        nxt_str = ", ".join(f"{QUAD_SHORT.get(k, k)} {v:.0%}" for k, v in
                            sorted(nxt.items(), key=lambda kv: -kv[1])[:2]) or "—"
        rows.append({"name": QUAD_SHORT[q], "n": trans["n_by_quad"].get(q, "—"),
                     "median": trans["median_days"].get(q, "—"), "next": nxt_str})
    html = env.get_template("china_history.html.j2").render(
        latest=latest, generated_utc=generated,
        chart_regime=_chart_regime(px, hist) if not px.empty else "", chart_axes=_chart_axes(hist),
        lifespan_rows=rows)
    (Path(config.load()["storage"]["site_dir"]) / "china_history.html").write_text(html)
    log.info("wrote china_history.html (%d regime periods)", trans.get("n_segments", 0))


def _sector_cards(latest: dict) -> list[dict]:
    """Merge the RS-rank table (from the regime run) with per-sector cycle analysis."""
    from engine.china_inputs import china_closes
    from engine.cycles import analyze
    names = config.load()["china"]["yahoo"]["sector_etfs"]
    closes = china_closes()
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
            log.warning("china sector analyze failed for %s: %s", t, e)
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
            "age_short": lad.get("age_short"), "age_short_zh": lad.get("age_short_zh"),
            "why": lad.get("why"), "regime_label": lad.get("regime_label"),
            "dc_day": cyc.get("dc_day"), "dc_band": cyc.get("dc_band"),
            "ic_week": cyc.get("ic_week"), "ic_band": cyc.get("ic_band"),
            "mtf_json": json.dumps(a["mtf"]),
            "price": round(float(close.iloc[-1]), 3),
        })
    # rank order (best RS first); unranked sectors fall to the end
    cards.sort(key=lambda c: (c["rank"] is None, c["rank"] or 999))
    return cards


def _breadth() -> dict | None:
    br = store.read("china_breadth", "breadth")
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


def _benchmark_card() -> dict | None:
    """Headline cycle card for the Shanghai Composite (deep history)."""
    from engine.cycles import analyze
    mi = config.load()["china"]["yahoo"]["market_index"]
    df = store.read("china", mi)
    if df is None or "close" not in df.columns:
        return None
    close = df["close"].dropna()
    a = analyze(close)
    return {"name": "Shanghai Composite", "ticker": mi,
            "mtf_json": json.dumps(a["mtf"]),
            "state": a["ladder"].get("state"), "label": a["ladder"].get("label"),
            "dc_day": a["cycle"].get("dc_day"), "dc_band": a["cycle"].get("dc_band"),
            "ic_week": a["cycle"].get("ic_week"), "ic_band": a["cycle"].get("ic_band"),
            "price": round(float(close.iloc[-1]), 2),
            "chg": round(100 * (close.iloc[-1] / close.iloc[-2] - 1), 2)}


def main() -> int:
    try:
        from engine.china_run import run
        latest = run()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("china engine failed (%s); skipping china page", e)
        return 0

    try:
        vm = {
            "latest": latest,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "sectors": _sector_cards(latest),
            "breadth": _breadth(),
            "benchmark": _benchmark_card(),
            "pair": latest.get("pair_ratios", {}),
            "pref": latest.get("preference_check", {}),
        }
        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        html = env.get_template("china.html.j2").render(**vm)
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)
        (site / "china.html").write_text(html)
        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                (site / a).write_text(src.read_text())
        log.info("wrote %s/china.html (%d KB, %d sectors)", site, len(html) // 1024, len(vm["sectors"]))

        # A-share stock search: build the per-ticker JSON library + render the search page
        try:
            from engine.cycles import STATE_DISPLAY
            from scripts import build_china_library
            build_china_library.main()
            stock_html = env.get_template("china_stock.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str),
                generated_utc=vm["built"])
            (site / "china_stock.html").write_text(stock_html)
            log.info("wrote %s/china_stock.html + chinastockdata/", site)
        except Exception as e:  # noqa: BLE001 — search is additive, never fatal
            log.error("china stock search build failed (%s); skipping", e)

        # history page (regime-over-index + the two dials + lifespan base rates)
        try:
            _build_history(env, latest, vm["built"])
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china history build failed (%s); skipping", e)

        # per-sector drill-down pages (sector ETF cycle + curated constituents)
        try:
            _build_sector_pages(env)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china sector pages build failed (%s); skipping", e)

        # daily bilingual narrative brief
        try:
            from scripts import china_brief
            china_brief.main()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china brief build failed (%s); skipping", e)
    except Exception as e:  # noqa: BLE001
        log.error("china page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
