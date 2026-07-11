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
from markupsafe import Markup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go  # noqa: E402

from lib import config, site_assets, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_china")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
          "charts.js", "tablesort.js", "aibrief.js", "stockview.js")


def _range_selector() -> dict:
    """1M…All range-selector buttons (theme-neutral; baked at build, charts.js
    rescales the y-axis to the visible window on zoom)."""
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


def _load_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001 — persisted artifacts are fallback-only
        log.warning("fallback JSON unreadable (%s): %s", path, e)
    return None


def _chart_regime(px: pd.Series, hist: pd.DataFrame, days: int = 3650) -> str:
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
    fig.update_yaxes(range=[-1.05, 1.05], autorange=False)   # fixed ±1 band — charts.js leaves it alone
    fig.update_xaxes(rangeselector=_range_selector())
    fig.update_layout(margin={"l": 45, "r": 15, "t": 54, "b": 30}, legend={"orientation": "h", "y": 1.18})
    return _chart_html(fig)


# ---- market-internals panel charts + view-models ------------------------------
def _panel_line(series: dict, color: str, height: int = 200, zero: bool = False,
                fill: bool = False, hline: float | None = None, hline_text: str = "") -> str:
    """Single-line panel chart from an internals {dates, vals} dict."""
    if not series or not series.get("dates"):
        return ""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(series["dates"]), y=series["vals"], mode="lines",
        line={"color": color, "width": 1.5},
        fill="tozeroy" if fill else None,
        fillcolor=("rgba(63,120,216,0.10)" if fill else None)))
    if zero:
        fig.add_hline(y=0, line={"color": "rgba(128,138,160,0.5)", "width": 0.8})
    if hline is not None:
        fig.add_hline(y=hline, line={"color": "#d04545", "width": 0.8, "dash": "dot"},
                      annotation_text=hline_text, annotation_position="top left",
                      annotation_font={"size": 10, "color": "#d04545"})
    fig.update_layout(**{**PLOT_LAYOUT, "height": height}, showlegend=False)
    return _chart_html(fig)


def china_regime_timeline(hist: pd.DataFrame) -> dict:
    """Compact columnar JSON for the client-side Time Machine (timemachine.js),
    mirroring build_site.regime_timeline() over the China regime history. The China
    engine doesn't track transition_state / recession / shock / warning flags, so
    those keys carry safe defaults — timemachine.js degrades to 'no warnings'."""
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


def _health_rows() -> list[dict]:
    """Data-health for the China collectors, from data/run_status.json."""
    sources = store.read_status().get("sources", {})
    labels = {"china_prices": ("Prices / sectors", "价格 / 板块"),
              "china_macro": ("Macro (PMI/CPI/credit)", "宏观 (PMI/CPI/信贷)"),
              "china_breadth": ("Breadth", "市场宽度"),
              "china_margin": ("Margin (融资融券)", "两融"),
              "china_connect": ("Stock Connect (沪深港通)", "沪深港通"),
              "china_flows": ("Sentiment / flows", "情绪 / 资金流"),
              "china_credit": ("Social financing (社融)", "社会融资规模")}
    rows = []
    for key, (en, zh) in labels.items():
        s = sources.get(key)
        if not s:
            continue
        rows.append({"en": en, "zh": zh, "status": s.get("status", "?"),
                     "rows": s.get("rows", 0), "last": s.get("last_date") or "—"})
    return rows


def _china_action_board(sectors: list[dict]) -> dict:
    """Bucket the sector cards' cycle-entry calls into a 'what to act on' board —
    the China analog of build_site.action_board (no per-stock notable branch).

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


def _internals_vm() -> dict:
    """Market-internals panels (margin crowd-meter, southbound flow, credit/tape,
    sentiment snapshots) + their plotly charts. Each piece is independently None-safe
    so a missing source just drops its panel."""
    from engine import china_internals as ci
    vm: dict = {}
    margin = ci.margin_meter()
    if margin:
        margin["chart_html"] = _panel_line(margin.get("chart"), "#e0a030", height=190,
                                            hline=margin.get("peak"),
                                            hline_text=f"2015 peak {margin.get('peak')}%")
        vm["margin"] = margin
    sb = ci.southbound_flow()
    if sb:
        sb["chart_html"] = _panel_line(sb.get("chart_cum"), "#3f78d8", height=190,
                                       zero=True, fill=True)
        vm["southbound"] = sb
    credit = ci.credit_tape()
    if credit:
        if credit.get("impulse_chart"):
            credit["impulse_html"] = _panel_line(credit["impulse_chart"], "#3f9fd8",
                                                 height=180, zero=True)
        if credit.get("scissors_chart"):
            credit["scissors_html"] = _panel_line(credit["scissors_chart"], "#5fbf7f",
                                                   height=180, zero=True)
        if credit.get("loans_chart"):
            credit["loans_html"] = _panel_line(credit["loans_chart"], "#8b93a1", height=160)
        vm["credit"] = credit
    flows = ci.flow_snaps()
    if flows:
        vm["flows"] = flows
    turn = ci.market_turnover()
    if turn:
        turn["chart_html"] = _panel_line(turn.get("chart"), "#c08bd8", height=150,
                                         hline=10000, hline_text="¥1T")
        vm["turnover"] = turn
    pboc = ci.pboc_policy()
    if pboc:
        vm["pboc"] = pboc
    return vm


def _property_vm() -> dict | None:
    """China Property & Fiscal panel (70-city price breadth, NBS climate composite,
    rebar/iron-ore construction demand, CGB curve, property-ETF drawdown) + charts.
    DISPLAY/regime context only — never a scored A-share signal."""
    from engine import china_property as cp
    v = cp.property_view()
    if not v:
        return None
    if v.get("breadth") and v["breadth"].get("chart"):
        v["breadth"]["chart_html"] = _panel_line(v["breadth"]["chart"], "#c97f9a", height=170, zero=True)
    if v.get("climate") and v["climate"].get("chart"):
        v["climate"]["chart_html"] = _panel_line(v["climate"]["chart"], "#5fbf7f", height=170,
                                                 hline=100, hline_text="neutral 100")
    if v.get("construction") and v["construction"].get("chart"):
        v["construction"]["chart_html"] = _panel_line(v["construction"]["chart"], "#e0a030", height=170)
    if v.get("cgb") and v["cgb"].get("chart"):
        v["cgb"]["chart_html"] = _panel_line(v["cgb"]["chart"], "#3f9fd8", height=170)
    if v.get("prop_etf") and v["prop_etf"].get("chart"):
        v["prop_etf"]["chart_html"] = _panel_line(v["prop_etf"]["chart"], "#d04545", height=170,
                                                 zero=True, fill=True)
    return v


def _leaderboard() -> dict | None:
    """Stock-Connect 'smart money' leaderboard — today's most-active A-shares by foreign
    (northbound) turnover + the HK names mainland (southbound) money net-bought/sold.
    A build-time fetch (ephemeral top-N, no history needed); fully best-effort."""
    import requests
    UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    H = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}

    def fetch(mt: str) -> list:
        p = {"reportName": "RPT_MUTUAL_TOP10DEAL", "columns": "ALL", "pageSize": 10,
             "sortColumns": "TRADE_DATE", "sortTypes": -1, "pageNumber": 1,
             "filter": f'(MUTUAL_TYPE="{mt}")'}
        r = requests.get(DC, params=p, headers=H, timeout=20)
        return (r.json().get("result") or {}).get("data") or []

    try:
        nb = fetch("001") + fetch("003")    # northbound (foreign -> A-shares)
        sb = fetch("002") + fetch("004")    # southbound (mainland -> HK)
    except Exception as e:  # noqa: BLE001
        log.warning("china leaderboard fetch failed: %s", e)
        return None
    if not nb and not sb:
        return None

    def latest(rows: list) -> list:
        if not rows:
            return []
        d = max(x["TRADE_DATE"] for x in rows)
        return [x for x in rows if x["TRADE_DATE"] == d]

    def row(x: dict, field: str) -> dict:
        return {"code": x.get("SECURITY_CODE"), "name": x.get("SECURITY_NAME"),
                "chg": round(float(x.get("CHANGE_RATE") or 0), 2),
                "val": round(float(x.get(field) or 0) / 1e8, 2)}   # 亿

    nb, sb = latest(nb), latest(sb)
    date = (nb or sb)[0]["TRADE_DATE"][:10] if (nb or sb) else None
    nb.sort(key=lambda x: -(x.get("DEAL_AMT") or 0))                 # foreign turnover
    sb.sort(key=lambda x: -(x.get("NET_BUY_AMT") or 0))             # mainland net
    return {"date": date,
            "nb": [row(x, "DEAL_AMT") for x in nb[:8]],
            "sb_buy": [row(x, "NET_BUY_AMT") for x in sb[:6]],
            "sb_sell": [row(x, "NET_BUY_AMT") for x in
                        sorted(sb, key=lambda x: (x.get("NET_BUY_AMT") or 0))[:4]]}


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
        write_page(outdir / f"{fund}.html", env.get_template("china_sector.html.j2").render(s=s))
        built += 1
    log.info("wrote %d china sector pages", built)
    return built


def _build_history(env, latest: dict, generated: str) -> None:
    import math
    from engine.playbook import QUAD_SHORT, next_quads_line, transition_stats
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
        rows.append({"name": QUAD_SHORT[q], "n": trans["n_by_quad"].get(q, "—"),
                     "median": trans["median_days"].get(q, "—"),
                     "next": next_quads_line(nxt), "next_zh": next_quads_line(nxt, zh=True)})

    # CN-SYS W8 — phase history block (display-only; degrade silently if artifacts absent)
    phase_strip: list[dict] = []
    era_table: list[dict] = []
    phase_current: dict = {}
    analogs: list[dict] = []
    try:
        _root = Path(__file__).resolve().parent.parent
        _chinastate = Path(config.load()["storage"]["site_dir"]) / "chinastatedata"
        cp_path = _chinastate / "cycle_phase.json"
        if cp_path.exists():
            import json as _json
            cp = _json.loads(cp_path.read_text())
            phase_current = {
                "phase": cp.get("phase", ""),
                "confidence": cp.get("confidence"),
                "asof": cp.get("asof", ""),
                "falsifiers": cp.get("falsifiers", []),
            }
            era_table = cp.get("era_table", [])
        phase_tape_path = _root / "data" / "china_cycle_phase" / "phase_tape.parquet"
        if phase_tape_path.exists():
            tape = pd.read_parquet(phase_tape_path)
            tape.index = pd.to_datetime(tape.index)
            for idx, row in tape.tail(90).iterrows():
                v = row.get("confidence")
                conf = None if (v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))) else float(v)
                phase_strip.append({
                    "d": idx.strftime("%Y-%m-%d"),
                    "phase": str(row.get("phase", "")),
                    "confidence": conf,
                })
        analogs_path = Path(config.load()["storage"]["site_dir"]) / "china_intel" / "analogs.json"
        if analogs_path.exists():
            import json as _json
            a_data = _json.loads(analogs_path.read_text())
            analogs = a_data.get("analogs", [])[:5]  # top-5 closest analogs, display-only
    except Exception as e:  # noqa: BLE001
        log.warning("phase history block failed (%s); degrading to empty", e)

    html = env.get_template("china_history.html.j2").render(
        latest=latest, generated_utc=generated,
        chart_regime=_chart_regime(px, hist) if not px.empty else "", chart_axes=_chart_axes(hist),
        lifespan_rows=rows,
        # CN-SYS W8 phase history additions (degrade-safe: empty list / dict if absent)
        phase_strip=phase_strip,
        era_table=era_table,
        phase_current=phase_current,
        analogs=analogs,
    )
    write_page(Path(config.load()["storage"]["site_dir"]) / "china_history.html", html)
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
            "entry": lad.get("entry"),     # cycle-entry call -> action board buckets
            "age_short": lad.get("age_short"), "age_short_zh": lad.get("age_short_zh"),
            "eq_badge": lad.get("eq_badge"), "eq_dir": lad.get("eq_dir"),
            "eq_tip": lad.get("eq_tip"),
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
    """Market breadth — how many A-shares are actually participating. Computed across
    the FULL searchable A-share universe (~800 names) for a true full-market read, not
    just the curated large-cap gauge; falls back to the curated breadth.parquet if the
    universe cache is missing/sparse. DISPLAY-ONLY."""
    from collectors.breadth import BreadthAdapter, breadth_summary
    closes = store.read("china_search", "closes")
    if closes is not None and not closes.empty and closes.shape[1] >= 150:
        return breadth_summary(BreadthAdapter().compute(closes), full=True)
    return breadth_summary(store.read("china_breadth", "breadth"), full=False)


def _china_signal_stack(latest: dict) -> dict | None:
    """Consolidated cross-subsystem 'signal stack' read (display-only). Pure function of
    the China `latest` state; never fatal."""
    try:
        from engine.china_signal_stack import build_china_signal_stack
        return build_china_signal_stack(latest)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china signal stack failed (%s); skipping", e)
        return None


def _china_market_tiles() -> list[dict]:
    """Cross-asset 'market snapshot' tiles — level + 1-day move for the headline A-share /
    macro instruments already on disk (SHCOMP, CSI 300, ChiNext, offshore yuan, gold, the
    10Y CGB yield, copper). Coloured by raw sign; semantic read lives in the panels below."""
    # (store group, ticker, column, en, zh, tag_en, tag_zh, decimals, is_rate, invert_tone)
    spec = [
        ("china", "000001.SS", "close", "Shanghai Comp", "上证综指", "index", "指数", 1, False, False),
        ("china", "510300.SS", "close", "CSI 300 ETF", "沪深300", "large-cap", "大盘", 2, False, False),
        ("china", "159915.SZ", "close", "ChiNext ETF", "创业板", "growth", "成长", 2, False, False),
        ("china", "CNH_F", "close", "Offshore yuan", "离岸人民币", "USDCNH", "美元离岸", 3, False, True),
        ("yahoo", "GC_F", "close", "Gold", "黄金", "USD/oz", "美元/盎司", 0, False, False),
        ("china_property", "cgb", "cgb_10y", "10Y CGB", "10年国债", "yield", "收益率", 2, True, False),
    ]
    out: list[dict] = []
    for grp, name, col, en, zh, ten, tzh, dec, is_rate, invert in spec:
        try:
            df = store.read(grp, name)
            if df is None or df.empty or col not in df.columns:
                continue
            s = df[col].astype(float).dropna()
            if len(s) < 2:
                continue
            last, prev = float(s.iloc[-1]), float(s.iloc[-2])
            chg = last - prev
            pct = (last / prev - 1) * 100 if prev else 0.0
            tone = "pos" if chg > 0 else "neg" if chg < 0 else "muted"
            if invert and tone != "muted":      # a weaker yuan (USDCNH up) = risk-off
                tone = "neg" if chg > 0 else "pos"
            out.append({
                "label": Markup('<span class="l-en">{}</span><span class="l-zh">{}</span>').format(en, zh),
                "tag": Markup('<span class="l-en">{}</span><span class="l-zh">{}</span>').format(ten, tzh),
                "level": (f"{last:.{dec}f}%" if is_rate else f"{last:,.{dec}f}"),
                "chg": f"{chg:+.{dec}f}", "pct": f"{pct:+.1f}%", "tone": tone,
            })
        except Exception:  # noqa: BLE001 — a single bad series never breaks the strip
            continue
    return out


def _china_alloc_card() -> dict:
    """Compact China Income Vector card for the index-health allocation button (the
    blue link → china_allocation.html). Reads data/china_regime/china_alloc_latest.json
    GRACEFULLY (mirrors build_site._spvector_state for the US side) — a missing file just
    yields a present=False default so the macro page never depends on the allocation build."""
    try:
        p = config.data_dir() / "china_regime" / "china_alloc_latest.json"
        d = json.loads(p.read_text())
        return d if d.get("present") else {"present": False}
    except Exception:  # noqa: BLE001 — button is additive, never fatal
        return {"present": False}


def _china_index_health() -> list[dict]:
    """Health snapshot for the major China indexes — the 'how is the market
    itself doing' read that leads the macro page. Price, % off the 52-week high
    (drawdown), 50/200d trend, RSI(14). Pure price math off the stored daily
    closes; reuses engine.technicals.rsi. SHCOMP (000001.SS, deep history) +
    CSI 300 ETF (510300.SS, the benchmark) + Shenzhen Component (399001.SZ)."""
    from engine.technicals import rsi
    out = []
    # 510300.SS is the CSI 300 ETF (no raw CSI 300 index series on disk) — label it as
    # an ETF so its ~unit NAV price reads correctly next to the index-level tiles.
    for tkr, label, zh in [("000001.SS", "Shanghai Composite", "上证综指"),
                           ("510300.SS", "CSI 300 ETF", "沪深300 ETF"),
                           ("399001.SZ", "Shenzhen Component", "深证成指")]:
        df = store.read("china", tkr)
        if df is None or df.empty or "close" not in df.columns:
            continue
        c = df["close"].astype(float).dropna()
        if len(c) < 60:
            continue
        px = float(c.iloc[-1])
        hi52 = float(c.tail(252).max())
        ma50 = float(c.tail(50).mean())
        ma200 = float(c.tail(200).mean()) if len(c) >= 200 else float("nan")
        try:
            r = float(rsi(c).iloc[-1])
        except Exception:  # noqa: BLE001 — never let one index break the panel
            r = float("nan")
        out.append({
            "ticker": tkr, "label": label, "label_zh": zh, "price": round(px, 2),
            "chg": round(100 * (px / float(c.iloc[-2]) - 1), 2) if len(c) >= 2 else 0.0,
            "dd": round(100 * (px / hi52 - 1), 1),
            "above50": bool(px >= ma50),
            "above200": (bool(px >= ma200) if ma200 == ma200 else None),
            "rsi": round(r) if r == r else None,
        })
    return out


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

    # Continuous regime probabilities via the informed HMM (v1, L2) — the SAME engine as the US
    # (engine/regime_hmm.py): soft P(Quad) + monthly transition matrix + hazard, replacing the
    # |score|*agreement coin-flip "confidence". DISPLAY-ONLY; a ~1s informed fit on the committed
    # China regime history (follows the ffill-corrected axis scores once the regime reruns).
    try:
        from engine.regime_hmm import fit_regime_hmm
        _crh = store.read("china_regime", "regime_history")
        latest["regime_hmm"] = fit_regime_hmm(_crh, history_days=252) if _crh is not None else None
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china regime-hmm leaf failed (%s); skipping", e)
        latest["regime_hmm"] = None

    # Base-effect forward projection for China (engine/china_base_effect.py) — the Hedgeye kernel
    # on a monthly level reconstructed from China's YoY-only CPI/PPI/IndPro. China PPI is heavily
    # base-driven (the +0.5% -> +3.9% reflation IS a base effect), so this is high-signal here.
    # DISPLAY-ONLY leaf, anchored to the actual latest YoY. Same contract as the US base_effect.
    try:
        from engine import china_base_effect as _cbe
        latest["base_effect"] = _cbe.compute()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china base-effect leaf failed (%s); skipping", e)
        latest["base_effect"] = None

    # China Income Vector allocation deep-dive (site/china_allocation.html) +
    # data/china_regime/china_alloc_latest.json — built here (no workflow edit needed) so
    # it runs on every CI build of build_china, BEFORE the index-health button reads its
    # card. Wrapped so an allocation-data gap never breaks the macro page.
    try:
        from scripts.build_china_allocation import build as _build_alloc
        _build_alloc()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china allocation build failed (%s); skipping", e)

    try:
        sectors = _sector_cards(latest)

        # CN-SYS W8: load spine + lobe snapshot payloads for the market-state
        # cockpit strip and the stocks-board microstructure chips.  None-safe:
        # the strip degrades silently when these files haven't been built yet.
        def _load_chinastatedata(name: str) -> dict | None:
            path = Path(config.load()["storage"]["site_dir"]) / "chinastatedata" / name
            return _load_json(path)

        _cn_market_state_json = _load_chinastatedata("market_state.json")
        _cn_participation_json = _load_chinastatedata("participation.json")
        _cn_cycle_phase_json   = _load_chinastatedata("cycle_phase.json")
        _cn_policy_json        = _load_chinastatedata("policy_transmission.json")
        _cn_microstructure_json = _load_chinastatedata("microstructure.json")

        # index name_packets by ticker for O(1) lookup on stocks cards
        _micro_by_ticker: dict = {}
        if _cn_microstructure_json:
            for pkt in (_cn_microstructure_json.get("name_packets") or []):
                ticker = pkt.get("ticker")
                if ticker:
                    _micro_by_ticker[ticker] = pkt

        # ── W8-R3: Act-Now v2 assembler ──────────────────────────────────────
        act_now_v2 = None
        try:
            from engine.china_act_now import (  # noqa: PLC0415
                assemble_act_now, load_cycle_rows, load_theme_intel,
            )
            cfg = config.load()
            site_dir = Path(cfg["storage"]["site_dir"])
            baskets_json_path = site_dir / "chinabasketdata" / "baskets.json"
            data_dir = Path(cfg["storage"].get("data_dir", "data"))
            forward_log_path = data_dir / "china_sector_cycles" / "forward_log.parquet"
            theme_intel = load_theme_intel(str(baskets_json_path))
            cycle_rows = load_cycle_rows(str(forward_log_path))
            # W8-R7 rider: load basket_turn_cn artifact for bottoming-watch organ chips
            _basket_turn_cn: dict | None = None
            try:
                _bt_cn_path = site_dir / "chinabasketdata" / "basket_turn_cn.json"
                if _bt_cn_path.exists():
                    _basket_turn_cn = json.loads(_bt_cn_path.read_text())
            except Exception as _bte:  # noqa: BLE001
                log.debug("basket_turn_cn load failed (%s) — rider omitted", _bte)
            # Fix 3: load baskets_ths.json for organ-rider THS name enrichment
            _ths_baskets: dict | None = None
            try:
                _ths_path = site_dir / "chinabasketdata" / "baskets_ths.json"
                if _ths_path.exists():
                    _ths_raw = json.loads(_ths_path.read_text())
                    _ths_baskets = {b["id"]: b for b in (_ths_raw.get("baskets") or []) if b.get("id")}
                else:
                    log.debug("baskets_ths.json absent — THS organ-rider enrichment skipped")
            except Exception as _thse:  # noqa: BLE001
                log.debug("baskets_ths.json load failed (%s) — THS enrichment skipped", _thse)
            act_now_v2 = assemble_act_now(
                sectors, theme_intel, cycle_rows,
                basket_turn=_basket_turn_cn,
                ths_baskets=_ths_baskets,
            )
        except Exception as _e:  # noqa: BLE001 — additive, never fatal
            log.error("china act_now_v2 build failed (%s); skipping", _e)
            act_now_v2 = None

        vm = {
            "latest": latest,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "sectors": sectors,
            "breadth": _breadth(),
            "benchmark": _benchmark_card(),
            "pair": latest.get("pair_ratios", {}),
            "pref": latest.get("preference_check", {}),
            "actions": _china_action_board(sectors),
            "act_now_v2": act_now_v2,            # W8-R3: four-lane board (stocks mode)
            "mtf_upturn_cn": None,               # W8-R7: populated after library call below
            "health": _health_rows(),
            "index_health": _china_index_health(),  # macro-page index-health strip
            "alloc_card": _china_alloc_card(),       # China Income Vector button (blue card)
            "signal_stack": _china_signal_stack(latest),  # consolidated cross-subsystem read
            "market_tiles": _china_market_tiles(),   # cross-asset market-snapshot tiles
            # CN-SYS W8 — spine + lobe snapshots (context_only; CN-SYS-R1)
            "cn_market_state_json": _cn_market_state_json,
            "cn_participation_json": _cn_participation_json,
            "cn_cycle_phase_json": _cn_cycle_phase_json,
            "cn_policy_json": _cn_policy_json,
            "cn_microstructure_json": _cn_microstructure_json,
            "cn_micro_by_ticker": _micro_by_ticker,
            # PR-4: O(1) lookup dict for SECTOR row payload enrichment in the anv2 board
            "sectors_by_ticker": {s["ticker"]: s for s in sectors},
        }
        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)

        # market-internals panels (margin / southbound / credit / sentiment) — None-safe
        try:
            vm["internals"] = _internals_vm()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china internals build failed (%s); skipping", e)
            vm["internals"] = {}

        # property & fiscal panel (70-city price breadth / climate / construction
        # demand / CGB curve / property-ETF drawdown) — display/regime context, None-safe
        try:
            vm["property"] = _property_vm()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china property build failed (%s); skipping", e)
            vm["property"] = None

        # conditions (RORO + uncalibrated recession/drawdown gauges) + Fear↔Euphoria
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
            log.error("china conditions charts failed (%s); skipping", e)

        # Market State command-center (display-only) — the China 6-factor scorecard +
        # side-by-side .ms-front board. Reuses engine.market_state with CN_PROFILE
        # (engine/market_state_cn.py): the index tape over Shanghai/CSI 300/Shenzhen plus
        # the conditions readers (RORO, QVIX+margin vol proxy, breadth percentile, PBoC
        # liquidity, slowdown/drawdown guard). None-safe; never breaks the page.
        try:
            from engine import market_state as _ms
            from engine.market_state_cn import CN_PROFILE
            from engine.china_inputs import build_features
            _f = build_features()
            # precompute the % >200d-MA 5y percentile + a price/breadth divergence flag for F4
            _b = _f["pct_above_200"].dropna() if "pct_above_200" in getattr(_f, "columns", []) else None
            if _b is not None and len(_b) >= 60:
                _win = _b.tail(252 * 5)
                _pctile = float((_win <= _win.iloc[-1]).mean())
                _px = _f["510300.SS"].dropna() if "510300.SS" in _f.columns else None
                _div = bool(_px is not None and len(_px) > 21 and len(_b) > 21
                            and _b.iloc[-1] < _b.iloc[-22] and _px.iloc[-1] > _px.iloc[-22])
                latest.setdefault("conditions", {})["breadth"] = {"above200_pctile": _pctile, "div": _div}
            # validated external-driver Risk Radar (engine/risk_radar_intl.py: US rate shocks,
            # US–China yield gap, USD/CNH + breadth — the legs that MEASURABLY lead A-share
            # drawdowns). Populated BEFORE market_state so CN_PROFILE.radar_override surfaces it
            # on the board. None-safe; display-only (does not force the verdict).
            from engine import risk_radar_intl as _rri
            latest["risk_radar"] = _rri.snapshot(_rri.CN_PROFILE)
            # forward-grade self-audit + bounded auto-tune: log+grade today's call against the
            # realized SHCOMP path, attach the scorecard, and let the radar hard-force the verdict
            # ONLY once its own log validates (can_force). Display-only until then. Never fatal.
            try:
                from engine import risk_radar_intl_audit as _rra, risk_radar_intl_tune as _rrt
                latest["risk_radar"]["forward_log"] = _rra.snapshot_and_grade(latest["risk_radar"], _rri.CN_PROFILE)
                latest["risk_radar"]["can_force"] = bool(latest["risk_radar"]["forward_log"].get("can_force"))
                _rrt.tune(_rri.CN_PROFILE)
            except Exception as _e:  # noqa: BLE001
                log.warning("china risk-radar audit/tune failed (%s); skipping", _e)
            vm["market_state"] = _ms.market_state_snapshot(
                latest, _f, latest.get("alerts") or [], profile=CN_PROFILE)
        except Exception as e:  # noqa: BLE001 — additive panel, never fatal
            log.error("china market_state failed (%s); skipping", e)
            vm["market_state"] = None

        # China macro/policy release calendar — display-only scheduling context (no
        # news API; pure date arithmetic over series already collected). None-safe.
        try:
            from engine import china_event_calendar as cec
            vm["calendar"] = cec.china_macro_events(horizon_days=14)
            vm["event_strip"] = cec.high_impact_strip(horizon_days=14)
            vm["imminent"] = cec.imminent_line(horizon_days=14)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china calendar build failed (%s); skipping", e)
            vm["calendar"], vm["event_strip"], vm["imminent"] = [], [], None

        # Macro news & official policy tone — CCTV 新闻联播 z-scored policy tone +
        # Eastmoney 全球财经快讯 filtered flashes (engine/china_news.py). Keyless,
        # display-only, never scored; degrades to None before the collector has
        # accrued tone history or if the flash fetch is unavailable. None-safe.
        try:
            from engine import china_news as cnews
            vm["china_news"] = cnews.panel()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china news panel failed (%s); skipping", e)
            vm["china_news"] = None

        # regime history -> Time Machine JSON + lifespan base rates on the main page
        hist = store.read("china_regime", "regime_history")
        if hist is not None and "quad" in hist.columns:
            (site / "china_regime_timeline.json").write_text(
                json.dumps(china_regime_timeline(hist), separators=(",", ":")))
            vm["lifespan_rows"] = _lifespan_rows(hist["quad"])

        # playbook — quad meaning, lifespan progress, next-quad odds, exposure dial
        try:
            from engine import china_playbook
            vm["pb"] = china_playbook.build(latest, hist, vm["sectors"], vm.get("internals") or {})
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china playbook build failed (%s); skipping", e)
            vm["pb"] = None

        # Stock-Connect smart-money leaderboard (best-effort build-time fetch)
        try:
            vm["leaderboard"] = _leaderboard()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china leaderboard failed (%s); skipping", e)
            vm["leaderboard"] = None

        # sector-neutral residual-alpha leg (per-stock signal score + "Alpha leaders"
        # panel). Computed once here, rendered on china.html, and passed into the stock
        # library so each chinastockdata record carries its alpha. Phase 0 = GO context leg.
        alpha = None
        try:
            from scripts.build_china_library import compute_china_alpha
            alpha = compute_china_alpha()
            vm["alpha"] = alpha
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china alpha build failed (%s); skipping", e)
            vm["alpha"] = None

        # build the per-ticker stock library NOW (records carry ladder + alpha) and
        # capture the cross-sectional "Top setups" ranking (selection × timing) for
        # china.html. Built here so the setups board renders server-side below.
        setups = None
        try:
            from scripts import build_china_library
            setups = build_china_library.main(alpha=alpha)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china stock library build failed (%s); skipping", e)
        vm["setups"] = setups
        # W8-R7: populate mtf_upturn_cn from in-memory setups result (written by library
        # during the call above).  Reading here — AFTER build_china_library.main() — ensures
        # the current cycle's data is always used, even on the very first deploy when no
        # pre-existing artifact file is present on disk.
        if setups is not None:
            vm["mtf_upturn_cn"] = setups.get("mtf_upturn_cn")  # full result dict or None

        # "Mean-reversion watch" — the VALIDATED A-share signal (3mo within-sector deep
        # dips, screened). Separate from the momentum-anchored setups; Phase 0 showed this
        # is the real edge (reports/china-reversal-phase0.md). Honest contrarian framing.
        try:
            from scripts.build_china_library import compute_china_reversal
            rev = compute_china_reversal()
            vm["reversal"] = rev
            if rev:
                (site / "factordata").mkdir(parents=True, exist_ok=True)
                (site / "factordata" / "china_reversal.json").write_text(
                    json.dumps(rev, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china reversal watch failed (%s); skipping", e)
            vm["reversal"] = None

        # "Defensive (low-vol)" sleeve — the validated A-share defensive tilt (lowest
        # trailing volatility; low-vol anomaly, reports/china-lowvol-phase0.md). The
        # conservative complement to the aggressive Mean-reversion watch.
        try:
            from scripts.build_china_library import compute_china_lowvol
            lv = compute_china_lowvol()
            vm["lowvol"] = lv
            if lv:
                (site / "factordata").mkdir(parents=True, exist_ok=True)
                (site / "factordata" / "china_lowvol.json").write_text(
                    json.dumps(lv, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china lowvol sleeve failed (%s); skipping", e)
            vm["lowvol"] = None

        # "Standout individual stocks" — the US notable-cards feature, ported. Enrich the
        # reversal-led setups shortlist with price + off-52w-high + sparkline + a China
        # confluence flag (reversal ∩ low-vol). Runs after reversal+lowvol so confluence
        # can be computed. Updates vm["setups"] in place (falls back to raw setups).
        try:
            from scripts.build_china_library import compute_china_standouts
            vm["setups"] = compute_china_standouts(setups, vm.get("reversal"), vm.get("lowvol"))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china standouts enrich failed (%s); using raw setups", e)

        # consolidated SCOREBOARD — merge the 4 single-signal screener JSONs (reversal,
        # low-vol, alpha, setups, + confluence) into one toggle-ready board. Runs last,
        # after all screener JSONs + the stock library are written.
        try:
            from scripts.build_china_library import compute_china_scoreboard
            sb = compute_china_scoreboard()
            vm["scoreboard"] = sb
            if sb:
                (site / "factordata" / "china_scoreboard.json").write_text(
                    json.dumps(sb, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china scoreboard build failed (%s); skipping", e)
            vm["scoreboard"] = None

        factordata = site / "factordata"
        if not (vm.get("setups") or {}).get("buy"):
            fallback = _load_json(factordata / "china_standouts.json")
            if fallback and fallback.get("buy"):
                vm["setups"] = fallback
                log.info("using persisted china_standouts.json fallback (%d buy)", len(fallback["buy"]))
        if not ((vm.get("scoreboard") or {}).get("modes")):
            fallback = _load_json(factordata / "china_scoreboard.json")
            if fallback and fallback.get("modes"):
                vm["scoreboard"] = fallback
                log.info("using persisted china_scoreboard.json fallback")

        # Flagship-2 Reversion Desk — CN Pick Lab (spec §4/§7).
        # Load the artifact produced by build_china_library's CN pick-lab producer block
        # and transform it to the schema the template expects.  Never fatal.
        try:
            _rd_artifact = _load_json(factordata / "china_reversion_desk.json")
            if _rd_artifact and isinstance(_rd_artifact.get("rows"), list):
                _rd_picks = []
                for _row in _rd_artifact["rows"]:
                    _chips = _row.get("chips") or {}
                    _rev_depth = _row.get("rev_depth") or {}
                    # Derive rev_depth_pct from rev_depth.rev_3m (raw 3-month return %)
                    _rev_3m = _rev_depth.get("rev_3m")
                    # off_high: use rev_3m as a proxy for distance from high (it's the
                    # 3-month return — negative means off high by that amount)
                    _off_high = float(_rev_3m) if _rev_3m is not None else None
                    # name: combine EN/ZH for bilingual split in template
                    _name = _row.get("name") or ""
                    _name_zh = _row.get("name_zh") or _name
                    _name_combined = f"{_name} / {_name_zh}" if _name_zh and _name_zh != _name else _name
                    _rd_picks.append({
                        "ticker": _row.get("ticker"),
                        "name": _name_combined,
                        "sector": _row.get("sector"),
                        "price": _row.get("close"),          # template reads .get('price')
                        "rev_depth_pct": _rev_3m,            # template reads .get('rev_depth_pct')
                        "off_high": _off_high,               # template reads .get('off_high')
                        # flatten chips to top-level (template reads top-level keys)
                        "washout_2w": _chips.get("washout_2w"),
                        "coiled": _chips.get("coiled"),
                        "chase_veto": _chips.get("chase_veto"),
                        "cycle_phase": _chips.get("cycle_phase"),
                        # pass through remaining fields for completeness
                        "rank": _row.get("rank"),
                        "score": _row.get("score"),
                    })
                vm["reversion_desk"] = {
                    "as_of": _rd_artifact.get("as_of"),
                    "picks": _rd_picks,
                    "n_picks": len(_rd_picks),
                    "authority": "display_only",
                }
                log.info("china stocks: reversion_desk loaded (%d picks)", len(_rd_picks))
            else:
                vm["reversion_desk"] = None
                log.debug("china stocks: no reversion_desk artifact — flagship-2 block hidden")
        except Exception as _rd_e:  # noqa: BLE001 — additive, never fatal
            log.error("china stocks: reversion_desk load failed (%s); skipping", _rd_e)
            vm["reversion_desk"] = None

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        # One shared view-model feeds BOTH the China macro-regime page and the
        # A-share Stock Dashboard — the same china.html.j2 is rendered twice with
        # a `mode` flag (macro / stocks) that selects which sections show. No data
        # is recomputed and the heavy page CSS lives in exactly one template.
        tmpl = env.get_template("china.html.j2")
        html = tmpl.render(**vm, mode="macro")
        write_page(site / "china.html", html)
        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, site)
        log.info("wrote %s/china.html (%d KB, %d sectors)", site, len(html) // 1024, len(vm["sectors"]))

        # Dedicated China news intelligence feed. Same display-only payload as the
        # China dashboard section, expanded into a searchable/filtered news surface.
        try:
            news_html = env.get_template("china_news.html.j2").render(**vm, mode="macro")
            write_page(site / "china_news.html", news_html)
            log.info("wrote %s/china_news.html (%d KB)", site, len(news_html) // 1024)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china news page render failed (%s); skipping", e)

        # A-share Stock Dashboard — same VM, the "looking for stocks" half.
        html_st = tmpl.render(**vm, mode="stocks")
        write_page(site / "china_stocks.html", html_st)
        log.info("wrote %s/china_stocks.html (%d KB)", site, len(html_st) // 1024)
        # landing-hub card stat (presence-gated by the .html existing)
        _su = vm.get("setups") or {}
        _n = len(_su.get("buy") or [])
        _label = (f"{_n} mean-reversion setups" if _n else "Setups · reversal · screener")
        cndir = config.data_dir() / "china_stocks"
        cndir.mkdir(parents=True, exist_ok=True)
        (cndir / "latest.json").write_text(json.dumps(
            {"date": latest.get("date", ""), "label": _label, "n_setups": _n}, indent=2))

        # A-share stock search shell (the per-ticker library was built above, before
        # the china.html render, so its "Top setups" ranking could feed the page)
        try:
            from engine.cycles import STATE_DISPLAY
            stock_html = env.get_template("china_lookup.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str),
                generated_utc=vm["built"])
            write_page(site / "china_lookup.html", stock_html)
            log.info("wrote %s/china_lookup.html + chinastockdata/", site)
        except Exception as e:  # noqa: BLE001 — search is additive, never fatal
            log.error("china stock search render failed (%s); skipping", e)

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

        # CN-SYS W5a: the 10 China Intelligence sub-builders (validation → news →
        # policy_watch → altdata → radar → synthesis → analogs → special_sits →
        # intel_hub → intel_bus) were EXTRACTED from this inline importlib chain
        # into discrete asia-close.yml run_py steps so per-step timing is visible
        # and the intel surfaces land even when the main china render fails.
        # DO NOT re-add them here — they run as separate steps after build_china.
        # See research/CHINA_SYSTEM_MASTERPLAN_BY_FABLE.md §6 W5a Scope 2.
    except Exception as e:  # noqa: BLE001
        log.error("china page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
