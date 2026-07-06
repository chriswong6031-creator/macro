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
from markupsafe import Markup  # noqa: E402

from lib import config, site_assets, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_hk")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
          "charts.js", "tablesort.js", "aibrief.js", "stockview.js")


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
            "entry": lad.get("entry"),     # cycle-entry call -> action board buckets
            "age_short": lad.get("age_short"), "age_short_zh": lad.get("age_short_zh"),
            "why": lad.get("why"), "regime_label": lad.get("regime_label"),
            "dc_day": cyc.get("dc_day"), "dc_band": cyc.get("dc_band"),
            "ic_week": cyc.get("ic_week"), "ic_band": cyc.get("ic_band"),
            "mtf_json": json.dumps(a["mtf"]),
        })
    cards.sort(key=lambda c: (c["rank"] is None, c["rank"] or 999))
    return cards


def _action_board(sectors: list[dict]) -> dict:
    """Bucket the sector cards' cycle-entry calls into a 'what to act on' board —
    the HK analog of build_site.action_board / build_china._china_action_board.

    Urgency routing (the #1513 lane split, ported):
      now → buy_now; imminent/soon → buy_soon; hold → hold; exit → take_profits;
      caution splits by entry tag:
        "DON'T CHASE"             → on_the_run  (uptrend intact, extended — do not chase)
        "UNCONFIRMED — HIGH RISK" → avoid       (bear-trend countertrend bounce)
        anything else (incl. "TAKE PROFITS") → take_profits
      all other urgency values → avoid.
    Tag literals must match engine/cycles.py entry_timing byte-for-byte
    (em dash in UNCONFIRMED, ASCII apostrophe in DON'T)."""
    buy_now, buy_soon, on_the_run, take_profits, hold, avoid = [], [], [], [], [], []
    for s in sectors:
        e = s.get("entry") or {}
        tag = e.get("tag", "")
        item = {"ticker": s["ticker"], "name": s["name"], "label": s.get("label") or s.get("state"),
                "tag": tag, "days": e.get("days_hi"), "dir": s.get("dir")}
        u = e.get("urgency")
        if u == "now":
            buy_now.append(item)
        elif u in ("imminent", "soon"):
            buy_soon.append(item)
        elif u == "caution":
            if tag == "DON'T CHASE":
                on_the_run.append(item)
            elif tag == "UNCONFIRMED — HIGH RISK":
                avoid.append(item)
            else:
                take_profits.append(item)
        elif u == "exit":
            take_profits.append(item)
        elif u == "hold":
            hold.append(item)
        else:
            avoid.append(item)
    buy_soon.sort(key=lambda x: (x["days"] if x["days"] is not None else 99))
    return {"buy_now": buy_now, "buy_soon": buy_soon, "on_the_run": on_the_run,
            "take_profits": take_profits, "hold": hold, "avoid": avoid}


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
    """Market breadth — how many HK large-caps are actually participating. HK's
    searchable universe (~73 liquid names) IS its breadth list, so this reads the
    existing curated breadth.parquet (fresher than the deep-history cache) and adds
    the same broad/thin/mixed participation read the US/CN/CA cards use. DISPLAY-ONLY."""
    from collectors.breadth import breadth_summary
    return breadth_summary(store.read("hk_breadth", "breadth"), full=False)


def _full_breadth() -> dict | None:
    """Full HK main-board advance/decline participation (collectors/hk_full_breadth,
    ~2000+ names) — the widest-denominator complement to the curated 73-name gauge.
    A snapshot (no MA history), so it carries adv/dec/%-up + universe size only.
    Eastmoney spot is flaky → degrades to None (the curated gauge stays primary)."""
    df = store.read("hk_full_breadth", "breadth")
    if df is None or df.empty or "pct_up" not in df.columns:
        return None
    r = df.dropna(subset=["pct_up"])
    if r.empty:
        return None
    last = r.iloc[-1]
    return {"n_members": int(last["n_members"]), "adv": int(last["adv"]),
            "dec": int(last["dec"]), "pct_up": round(float(last["pct_up"]), 1),
            "asof": str(r.index[-1].date())}


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
        write_page(outdir / f"{sector_slug(name)}.html", env.get_template("hk_sector.html.j2").render(s=s))
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
    write_page(Path(config.load()["storage"]["site_dir"]) / "hk_history.html", html)
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
    div = ci.southbound_price_divergence()   # DISPLAY-ONLY context chip (not scored)
    if div:
        vm["sb_divergence"] = div
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


def _hk_signal_stack(latest: dict) -> dict | None:
    """Consolidated cross-subsystem 'signal stack' read (display-only). Pure function
    of the HK `latest` state; never fatal."""
    try:
        from engine.hk_signal_stack import build_hk_signal_stack
        return build_hk_signal_stack(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("hk signal stack failed (%s); skipping", e)
        return None


def _hk_market_tiles() -> list[dict]:
    """CROSS-ASSET 'market snapshot' tiles — level + 1-day move for the non-index
    instruments that drive HK (the true HS-TECH index, USD/HKD peg, offshore yuan,
    gold, the dollar, overnight HIBOR). Broad-index confluence and HSI technicals
    live in the Market State tape; this strip is the cross-asset complement."""
    # (store group, name, column, en, zh, tag_en, tag_zh, decimals, is_rate, invert_tone)
    spec = [
        ("hk", "HSTECH", "close", "HS-TECH", "恒生科技", "growth", "成长", 0, False, False),
        ("hk", "HKD=X", "close", "USD / HKD", "美元兑港元", "peg", "联汇", 4, False, True),
        ("china", "CNH_F", "close", "Offshore yuan", "离岸人民币", "USDCNH", "美元离岸", 3, False, True),
        ("yahoo", "GC_F", "close", "Gold", "黄金", "USD/oz", "美元/盎司", 0, False, False),
        ("yahoo", "DX-Y.NYB", "close", "US Dollar", "美元指数", "DXY", "美元", 2, False, True),
        ("hkma", "interbank_liquidity", "hibor_on", "Overnight HIBOR", "隔夜HIBOR", "yield", "利率", 2, True, False),
    ]
    out: list[dict] = []
    for grp, name, col, en, zh, ten, tzh, dec, is_rate, invert in spec:
        try:
            df = store.read(grp, name)
            if (df is None or df.empty or col not in df.columns) and name == "HSTECH":
                df, col = store.read("hk", "3033.HK"), "close"   # fallback to the ETF proxy
                en, zh = "HS-TECH ETF", "恒生科技ETF"
            if df is None or df.empty or col not in df.columns:
                continue
            s = df[col].astype(float).dropna()
            if len(s) < 2:
                continue
            last, prev = float(s.iloc[-1]), float(s.iloc[-2])
            chg = last - prev
            pct = (last / prev - 1) * 100 if prev else 0.0
            tone = "pos" if chg > 0 else "neg" if chg < 0 else "muted"
            if invert and tone != "muted":      # weaker HKD / yuan / stronger USD = risk-off
                tone = "neg" if chg > 0 else "pos"
            chg_dec = max(dec, 1)                # never collapse a sub-unit move to "+0" (e.g. gold)
            out.append({
                "label": Markup('<span class="l-en">{}</span><span class="l-zh">{}</span>').format(en, zh),
                "tag": Markup('<span class="l-en">{}</span><span class="l-zh">{}</span>').format(ten, tzh),
                "level": (f"{last:.{dec}f}%" if is_rate else f"{last:,.{dec}f}"),
                "chg": f"{chg:+.{chg_dec}f}", "pct": f"{pct:+.1f}%", "tone": tone,
            })
        except Exception:  # noqa: BLE001 — a single bad series never breaks the strip
            continue
    return out


def _hk_property_vm() -> dict | None:
    """HK residential-property panel (Centaline CCL) — level/trend block + chart, or
    None if the CCL feed is missing (the collector is a fragile single-host scrape)."""
    try:
        from engine import hk_property
        v = hk_property.property_view()
        if not v:
            return None
        ccl = v.get("ccl") or {}
        if ccl.get("chart"):
            v["chart_html"] = _panel_line(ccl["chart"], "#c08bd8", height=190)
        return v
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("hk property vm failed (%s); skipping", e)
        return None


def _hk_valuation_vm() -> dict | None:
    """HK index valuation (Baidu PE/PB market-median across the big-cap cohort) — the
    currency-clean valuation read hk_fundamentals deliberately skips. PE/PB only
    (Baidu serves no dividend-yield chart). Display-only."""
    df = store.read("hk_valuation", "median")
    if df is None or df.empty or "pe" not in df.columns:
        return None
    out: dict = {}
    for col, key in (("pe", "pe"), ("pb", "pb")):
        s = df[col].dropna() if col in df.columns else pd.Series(dtype=float)
        if s.empty:
            continue
        lvl = float(s.iloc[-1])
        out[key] = {
            "level": round(lvl, 2),
            "pctile": int(round((s <= lvl).mean() * 100)),
            "chg_1y": round(100 * (lvl / float(s.iloc[-253]) - 1), 1) if len(s) > 253 else None,
            "span": f"{s.index.min():%Y-%m} → {s.index.max():%Y-%m}",
        }
    if not out:
        return None
    out["pe_chart_html"] = _panel_line(
        {"dates": [d.strftime("%Y-%m-%d") for d in df["pe"].dropna().index],
         "vals": [round(float(v), 2) for v in df["pe"].dropna()]}, "#5fbf7f", height=180)
    out["n"] = int(df["n_pe"].dropna().iloc[-1]) if "n_pe" in df.columns and not df["n_pe"].dropna().empty else None
    return out


def _hk_ah_official_vm() -> dict | None:
    """Official ~190-pair A/H premium index (reconstructed daily) + the latest market-
    wide spot mean — the calibrated 'HK is the cheaper way to own China' gauge. Display
    only. Complements the computed 12-pair basket (vm['ah'])."""
    prem = store.read("hk_ah_official", "ah_premium")
    spot = store.read("hk_ah_official", "ah_spot")
    if (prem is None or prem.empty or "hsahp" not in prem.columns) and \
       (spot is None or spot.empty):
        return None
    out: dict = {}
    if prem is not None and "hsahp" in getattr(prem, "columns", []):
        s = prem["hsahp"].dropna()
        if not s.empty:
            lvl = float(s.iloc[-1])
            out.update({
                "premium_pct": round(lvl, 1),
                "pctile": int(round((s <= lvl).mean() * 100)),
                "chg_1y": round(lvl - float(s.iloc[-253]), 1) if len(s) > 253 else None,
                "span": f"{s.index.min():%Y-%m} → {s.index.max():%Y-%m}",
                "chart_html": _panel_line(
                    {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
                     "vals": [round(float(v), 1) for v in s]}, "#c08bd8", height=190, zero=False),
            })
    if spot is not None and not spot.empty and "hsahp" in spot.columns:
        r = spot.dropna(subset=["hsahp"])
        if not r.empty:
            out["spot_mean"] = round(float(r["hsahp"].iloc[-1]), 1)
            out["spot_median"] = (round(float(r["hsahp_median"].iloc[-1]), 1)
                                  if "hsahp_median" in r.columns else None)
            out["n_pairs"] = (int(r["n_pairs"].iloc[-1])
                             if "n_pairs" in r.columns and pd.notna(r["n_pairs"].iloc[-1]) else None)
    return out or None


def _hk_southbound_channels_vm() -> dict | None:
    """Per-channel southbound split (港股通沪 vs 港股通深) — net flow momentum + the
    cumulative mainland HK holdings, the richer view of the #1 HK capital flow."""
    out: dict = {}
    for nm, key, en, zh in (("southbound_sh", "sh", "Shanghai → HK", "沪市港股通"),
                            ("southbound_sz", "sz", "Shenzhen → HK", "深市港股通")):
        df = store.read("hk_connect", nm)
        if df is None or df.empty or "net" not in df.columns:
            continue
        net = df["net"].dropna()
        if net.empty:
            continue
        out[key] = {
            "label_en": en, "label_zh": zh,
            "net": round(float(net.iloc[-1]), 1),
            "sum_20d": round(float(net.tail(20).sum()), 1),
            "sum_60d": round(float(net.tail(60).sum()), 1),
            "cum": (round(float(df["cum"].dropna().iloc[-1]), 0)
                    if "cum" in df.columns and not df["cum"].dropna().empty else None),
        }
    return out or None


def _hk_alloc_card() -> dict:
    """Compact allocation card for the HK macro page (graceful — present=False if
    no HK allocation artifact exists yet, so the macro page never depends on it)."""
    try:
        p = config.data_dir() / "hk_regime" / "hk_alloc_latest.json"
        d = json.loads(p.read_text())
        return d if d.get("present") else {"present": False}
    except Exception:  # noqa: BLE001 — button is additive, never fatal
        return {"present": False}


def _hk_track_record_vm() -> dict | None:
    """W6 track-record panel (§7.4) — the standout-board forward scorecard, rendered
    honestly in its 'accruing' state (or with graded hit-rates + rank-IC once the
    min-IC-dates gate clears).

    Returns a compact, template-ready dict (bilingual copy assembled here so the
    template stays declarative) or None if the ledger module is unavailable. Never
    raises — the panel is presence-gated in hk.html.j2.
    """
    from engine import board_ledger

    sc = board_ledger.scorecard("HK")
    if not sc:
        return None

    status = sc.get("status", "accruing")
    first_read_est = sc.get("first_read_est")   # program-level stable-read date

    # honest 'accruing since' = the ledger's first logged call-date; the first single
    # 21-trading-day grade lands ~21 business days later.
    first_write = None
    first_21d = None
    try:
        p = board_ledger._store_path("HK")
        if p.exists():
            _df = pd.read_parquet(p)
            if not _df.empty and "date" in _df.columns:
                fw = pd.to_datetime(_df["date"]).min()
                first_write = fw.strftime("%Y-%m-%d")
                first_21d = (fw + pd.offsets.BDay(21)).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001 — dates are cosmetic; panel still renders
        pass

    out = {
        "status": status,
        "first_write": first_write,
        "first_21d_read": first_21d,
        "first_stable_read": first_read_est,
        "n_calls": sc.get("n_calls", 0),
        "n_graded": sc.get("n_graded", 0),
        "n_suspended": sc.get("n_suspended", 0),
        "survivorship": sc.get("survivorship"),
    }

    if status == "scored":
        # per-horizon rank-IC + per-group hit-rates, template-ready
        horizons = []
        for h_key in ("5d", "10d", "21d", "63d"):
            hh = (sc.get("by_horizon") or {}).get(h_key)
            if not hh:
                continue
            groups = []
            for gname, gd in (hh.get("by_group") or {}).items():
                groups.append({
                    "group": gname,
                    "n": gd.get("n"),
                    "pos_rate": gd.get("pos_rate"),
                    "mean_excess": gd.get("mean_excess"),
                })
            horizons.append({
                "h": h_key,
                "n": hh.get("n"),
                "rank_ic": hh.get("rank_ic"),
                "n_ic_dates": hh.get("n_ic_dates"),
                "hit_rate_21d": hh.get("hit_rate_21d"),
                "n_buy": hh.get("n_buy"),
                "by_group": groups,
            })
        out["horizons"] = horizons

    return out


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
            "actions": _action_board(sectors),   # "what to act on now" sector board (stocks page)
            "breadth": _breadth(),
            "full_breadth": _full_breadth(),     # full main-board adv/dec (fragile; None when blocked)
            "benchmark": _benchmark_card(),
            "pair": latest.get("pair_ratios", {}),
            "pref": latest.get("preference_check", {}),
            "gv": latest.get("global_snapshot", {}),
            "vhsi": _vhsi_vm(),
            "signal_stack": _hk_signal_stack(latest),   # consolidated cross-subsystem read
            "market_tiles": _hk_market_tiles(),         # cross-asset market-snapshot tiles
            "alloc_card": _hk_alloc_card(),             # allocation button (graceful)
            "valuation": _hk_valuation_vm(),            # PE/PB market-median band
            "ah_official": _hk_ah_official_vm(),        # official ~190-pair A/H index
            "sb_channels": _hk_southbound_channels_vm(),  # per-channel southbound split
        }
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        # conditions (RORO + uncalibrated slowdown/drawdown gauges) + Fear↔Euphoria
        # charts — None-safe. The dicts already ride in vm via "latest"; here we just
        # render their plotly lines (display-only, never scored).
        try:
            cond = latest.get("conditions")
            if cond and cond.get("charts"):
                ch = cond["charts"]
                cond["roro_html"] = _panel_line(ch.get("roro"), "#3f9fd8", height=170, zero=True)
                cond["recession_html"] = _panel_line(ch.get("recession"), "#d4a017", height=150)
                cond["drawdown_html"] = _panel_line(ch.get("drawdown"), "#d04545", height=150)
                fe = latest.get("fear_euphoria")
                if fe is not None and ch.get("fear_euphoria"):
                    fe["chart_html"] = _panel_line(ch["fear_euphoria"], "#c08bd8", height=160)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk conditions charts failed (%s); skipping", e)

        # Market State command-center (display-only) — the HK 6-factor scorecard +
        # side-by-side .ms-front board. Reuses engine.market_state with HK_PROFILE
        # (engine/market_state_hk.py): the index tape over Hang Seng / HSCEI / HS TECH
        # plus the conditions readers (RORO, VHSI+HIBOR vol proxy, breadth percentile,
        # HKMA/peg liquidity, slowdown/drawdown guard). None-safe; never breaks the page.
        try:
            from engine import market_state as _ms
            from engine.market_state_hk import HK_PROFILE
            from engine.hk_inputs import build_features as _hk_feats
            _f = _hk_feats()
            # precompute the % >50d-MA 5y percentile + a price/breadth divergence flag for F4
            _b = _f["pct_above_50"].dropna() if "pct_above_50" in getattr(_f, "columns", []) else None
            if _b is not None and len(_b) >= 60:
                _win = _b.tail(252 * 5)
                _pctile = float((_win <= _win.iloc[-1]).mean())
                _px = _f["^HSI"].dropna() if "^HSI" in _f.columns else None
                _div = bool(_px is not None and len(_px) > 21 and len(_b) > 21
                            and _b.iloc[-1] < _b.iloc[-22] and _px.iloc[-1] > _px.iloc[-22])
                latest.setdefault("conditions", {})["breadth"] = {"above200_pctile": _pctile, "div": _div}
            # external-driver Risk Radar (engine/risk_radar_intl.py: US rate shocks + dollar
            # strength — HK's US-coupling is recent but real). Populated BEFORE market_state so
            # HK_PROFILE.radar_override surfaces it. None-safe; display-only.
            from engine import risk_radar_intl as _rri
            latest["risk_radar"] = _rri.snapshot(_rri.HK_PROFILE)
            # forward-grade self-audit + bounded auto-tune (vs realized HSI path); hard-forces the
            # verdict only once HK's own log validates (can_force). Display-only until then.
            try:
                from engine import risk_radar_intl_audit as _rra, risk_radar_intl_tune as _rrt
                latest["risk_radar"]["forward_log"] = _rra.snapshot_and_grade(latest["risk_radar"], _rri.HK_PROFILE)
                latest["risk_radar"]["can_force"] = bool(latest["risk_radar"]["forward_log"].get("can_force"))
                _rrt.tune(_rri.HK_PROFILE)
            except Exception as _e:  # noqa: BLE001
                log.warning("hk risk-radar audit/tune failed (%s); skipping", _e)
            vm["market_state"] = _ms.market_state_snapshot(
                latest, _f, latest.get("alerts") or [], profile=HK_PROFILE)
        except Exception as e:  # noqa: BLE001 — additive panel, never fatal
            log.error("hk market_state failed (%s); skipping", e)
            vm["market_state"] = None

        # HK / US / China macro release calendar — display-only scheduling context
        # (pure date arithmetic; no news API). None-safe.
        try:
            from engine import hk_event_calendar as hec
            vm["calendar"] = hec.hk_macro_events(horizon_days=14)
            vm["event_strip"] = hec.high_impact_strip(horizon_days=14)
            vm["imminent"] = hec.imminent_line(horizon_days=14)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk calendar build failed (%s); skipping", e)
            vm["calendar"], vm["event_strip"], vm["imminent"] = [], [], None

        # HK residential-property panel (Centaline CCL) — display/regime context, None-safe
        try:
            vm["property"] = _hk_property_vm()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk property build failed (%s); skipping", e)
            vm["property"] = None

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

        # consolidated SCOREBOARD — the HK Stock Desk: ONE toggle (Amplifiers / Cushions /
        # All) over the validated global-risk-beta read, each row enriched with price,
        # cycle, southbound smart-money flow + A/H value. Built after the library so
        # hkstockdata/ exists.
        try:
            sb = build_hk_library.compute_hk_scoreboard(betas)
            vm["hk_scoreboard"] = sb
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk scoreboard build failed (%s); skipping", e)
            vm["hk_scoreboard"] = None

        # standout cards + the unified, regime-conditioned HK conviction (southbound flow +
        # A/H value + beta-neutral RS). This also patches the conviction score + edge z back
        # onto the scoreboard rows, so the scoreboard JSON is persisted AFTER it runs.
        try:
            vm["setups"] = build_hk_library.compute_hk_standouts(vm.get("hk_scoreboard"))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk standouts build failed (%s); skipping", e)
            vm["setups"] = None
        try:
            if vm.get("hk_scoreboard"):
                (site / "factordata").mkdir(parents=True, exist_ok=True)
                (site / "factordata" / "hk_scoreboard.json").write_text(
                    json.dumps(vm["hk_scoreboard"], separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk scoreboard persist failed (%s); skipping", e)

        # W6 TRACK-RECORD panel (§7.4) — the program's public-accountability centerpiece.
        # Reads the standout-board forward scorecard and renders the honest 'accruing' state
        # (or graded hit-rates + rank-IC once the min-IC-dates gate clears). View-model only;
        # never fatal — the panel is presence-gated in the template.
        try:
            vm["track_record"] = _hk_track_record_vm()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("hk track-record view-model failed (%s); skipping", e)
            vm["track_record"] = None

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        # One shared view-model feeds BOTH the HK macro-regime page and the HK
        # Stock & Exposure board — the same hk.html.j2 is rendered twice with a
        # `mode` flag (macro / stocks) that selects which sections show. No data is
        # recomputed and the heavy page CSS lives in exactly one template.
        tmpl = env.get_template("hk.html.j2")
        html = tmpl.render(**vm, mode="macro")
        write_page(site / "hk.html", html)
        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, site)
        log.info("wrote %s/hk.html (%d KB, %d sectors)", site, len(html) // 1024, len(vm["sectors"]))

        # HK Stock & Exposure board — same VM, the "looking for stocks" half.
        # HK has no validated stock-picking edge — this is beta/sector positioning.
        html_st = tmpl.render(**vm, mode="stocks")
        write_page(site / "hk_stocks.html", html_st)
        log.info("wrote %s/hk_stocks.html (%d KB)", site, len(html_st) // 1024)
        # landing-hub card stat (presence-gated by the .html existing)
        _bt = vm.get("betas") or {}
        _n = len(_bt.get("amplifiers") or []) + len(_bt.get("cushions") or [])
        _label = (f"{_n} beta exposures" if _n else "Beta exposure & sector positioning")
        hkdir = config.data_dir() / "hk_stocks"
        hkdir.mkdir(parents=True, exist_ok=True)
        (hkdir / "latest.json").write_text(json.dumps(
            {"date": latest.get("date", ""), "label": _label, "n_setups": _n}, indent=2))

        # HK stock search shell (the per-ticker library was built above, before the
        # hk.html render, so its global-beta board could feed the page)
        try:
            from engine.cycles import STATE_DISPLAY
            stock_html = env.get_template("hk_lookup.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str),
                generated_utc=vm["built"])
            write_page(site / "hk_lookup.html", stock_html)
            log.info("wrote %s/hk_lookup.html + hkstockdata/", site)
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
    except Exception as e:  # noqa: BLE001
        log.error("hk page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
