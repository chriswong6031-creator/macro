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

from lib import config, site_assets, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_canada")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "timemachine.js",
          "charts.js", "tablesort.js", "stockview.js", "stocktable.js", "heatmap.js")


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


def _drilldown_closes() -> tuple[pd.DataFrame, str | None]:
    """Close matrix for the per-sector drill-down holdings cards.

    Source of record is the curated breadth cache (canada_breadth/_closes_cache.parquet,
    written by the collect lane). It is gitignored rebuild-only, so on the re-render
    lanes (build_vector -> build_canada with no collectors) and in fresh worktrees it is
    absent; there we fall back to the COMMITTED broad S&P/TSX Composite panel
    (canada_search/closes.parquet, ~218 iShares-XIC names) which carries 73/74 curated
    constituents with deep history. Curated cache is tried FIRST so the nightly lane's
    drill-down is unchanged; the fallback only rescues lanes that lack the cache. Same
    two sources as engine.board_ledger._load_ca_wide(). Returns (df, source_label);
    (empty, None) when neither source is usable."""
    dd = config.data_dir()
    sources = [
        (dd / "canada_breadth" / "_closes_cache.parquet", "canada_breadth"),
        (dd / "canada_search" / "closes.parquet", "canada_search"),
    ]
    for path, label in sources:
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            log.error("HKCA-13: canada drill-down panel %s unreadable: %s", label, exc)
            continue
        if df.empty or df.shape[1] == 0:
            continue
        return df, label
    return pd.DataFrame(), None


def _check_closes_cache() -> dict | None:
    """HKCA-13: surface a TRULY empty per-sector drill-down in the health table.

    The drill-down holdings read _drilldown_closes() -- the curated breadth cache
    (gitignored, rebuilt only by the collect lane) with a fallback to the committed
    canada_search Composite panel. A warning row is emitted ONLY when NEITHER source
    yields usable closes, i.e. the drill-down would genuinely ship with zero stock
    cards. DO NOT rebuild the cache here; that belongs in the collect lane."""
    df, label = _drilldown_closes()
    if df.empty:
        log.error(
            "HKCA-13: no canada drill-down close panel (neither canada_breadth cache "
            "nor canada_search) -- sector pages will ship with empty stock-level cards.  "
            "Fix: run scripts/collect.py --only canada_breadth (or canada_universe)."
        )
        return {
            "en": "Sector drill-down data (MISSING -- run canada_breadth collector)",
            "zh": "板块下钻数据（缺失 -- 请运行 canada_breadth 收集器）",
            "status": "MISSING",
            "rows": 0,
            "last": "—",
        }
    last_date = df.index.max().date() if hasattr(df.index, "max") else "?"
    log.info("canada drill-down panel: %s (%d names, last=%s)", label, df.shape[1], last_date)
    return None   # None = healthy; drill-down has a usable close panel


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
    # HKCA-13: make a missing/empty _closes_cache.parquet visible in the health table.
    cache_warn = _check_closes_cache()
    if cache_warn is not None:
        rows.append(cache_warn)
    return rows


def _action_board(sectors: list[dict]) -> dict:
    """Bucket the sector cards' cycle-entry calls into a 'what to act on' board.

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


def _sector_cards(latest: dict) -> list[dict]:
    """Merge the RS-rank table (from the regime run) with per-sector cycle analysis."""
    from engine.canada_inputs import canada_closes
    from engine.cycles import analyze, STATE_DISPLAY as _STATE_DISPLAY_MAP
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
            "label_zh": _STATE_DISPLAY_MAP.get(lad.get("state") or "", {}).get("label_zh"),
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
    write_page(Path(config.load()["storage"]["site_dir"]) / "canada_history.html", html)
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
    ccloses, _ = _drilldown_closes()
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
        write_page(outdir / f"{fund}.html", env.get_template("canada_sector.html.j2").render(s=s))
        built += 1
    log.info("wrote %d canada sector pages", built)
    return built


def _board_asof(latest: dict) -> str:
    """The board's own price date (the CA close the board was ranked on). Prefer the
    engine's `latest.date`; fall back to the S&P/TSX benchmark's last close date."""
    d = latest.get("date")
    if d:
        return str(d)
    df = store.read("canada", config.load()["canada"]["yahoo"]["market_index"])
    if df is not None and not df.empty:
        return str(df.index.max().date())
    return str(pd.Timestamp.utcnow().date())


def _canada_board_ledger(setups: dict | None, latest: dict) -> list[dict]:
    """Log today's ranked Branch-B board to the standout-board forward ledger and grade
    matured calls (masterplan §5.4). Returns health rows (empty when healthy).

    Fail-open-LOUD: any failure yields a visible health row rather than a silent pass —
    the board's scoreboard must never fail invisibly."""
    rows = (setups or {}).get("buy") or []
    if not rows:
        return [{"en": "Board ledger (no ranked names to log)", "zh": "榜单账本（无可记录个股）",
                 "status": "SKIP", "rows": 0, "last": "—"}]
    asof = _board_asof(latest)
    from scripts.build_canada_library import _ENTRY_STATE
    calls = []
    for r in rows:
        es = r.get("entry_signal") or {}
        sig = r.get("signal") or {}
        # gate_tier honesty: the confluence gate DID run for every board name (it is stamped
        # per-name in build_canada_library.main). A tier of T1..T4 means a fresh cross today;
        # its ABSENCE on a ran verdict is a real "no confluence buy this tape" — record it as
        # the string 'none' so a zero-cross board is a LOGGED fact, not indistinguishable from
        # "the gate never ran" (which would leave gate_tier null). Only a row with no verdict
        # dict at all stays None.
        _tier = sig.get("tier") or (r.get("conviction") or {}).get("gate_tier")
        gate_tier = _tier or ("none" if sig else None)
        calls.append({
            "ticker": r.get("ticker"),
            "group": r.get("group"),                       # 'entry_open' | 'setting_up'
            "edge_z": r.get("alpha"),                      # momentum SCREEN z (accruing)
            "gate_tier": gate_tier,
            "align_tier": r.get("align_tier"),
            "entry_state": _ENTRY_STATE.get(es.get("status")),
            "close_asof": r.get("price"),
            # CA2 close-only port stamps (log-and-grade, nullable-bool; None = not computed):
            # extended (pullback-zone chase read OR extension grade), hold_basing (in a base
            # vs its anchor), dt_compress (dannytrades vol-compression / non-neutral read).
            "extended": (bool(r.get("extended")) or ((r.get("pullback_zone") or {}).get("stance") == "chase")) if (r.get("extended") or r.get("pullback_zone")) else None,
            "hold_basing": ((r.get("hold") or {}).get("state") == "intact") if r.get("hold") else None,
            "dt_compress": ((r.get("dt_contra") or {}).get("state") not in (None, "neutral")) if r.get("dt_contra") else None,
        })
    # W0.2 Stage C (§5.2 move 2): the CA WATCH strip was never appended — its
    # strong-but-blocked rows are exactly the near-miss cohort the rejection
    # ledger exists to grade ("rejection ≠ blacklist" is a pre-registered
    # hypothesis feeding S6, so these are natural controls, not noise).
    # watch_reason='knife' maps to the CLOSED-taxonomy 'knife_demote' (Appendix A
    # anchors that row to the HK quintile "port to US/CA" — CA's knife IS that);
    # 'blocked' (alignment gate) has NO taxonomy row yet → reason stays null and
    # the free-text block_reason is carried for display/audit (extending the
    # taxonomy needs a §8 row + monthly-review sign-off).
    for w in (setups or {}).get("watch") or []:
        if not w.get("ticker"):
            continue
        calls.append({
            "ticker": w.get("ticker"),
            "group": "watch",
            "edge_z": w.get("alpha"),              # same screen z as board rows
            "primary_rejection_reason": ("knife_demote"
                                         if w.get("watch_reason") == "knife" else None),
            "block_reason": w.get("block_reason"),
            "knife_demoted": (w.get("watch_reason") == "knife"),
        })
    health: list[dict] = []
    try:
        from engine import board_ledger
        n = board_ledger.append_board(calls, market="CA", asof=asof)
        if n <= 0:
            health.append({"en": "Board ledger (append wrote 0 rows — see build log)",
                           "zh": "榜单账本（写入 0 行 — 查看构建日志）",
                           "status": "ERROR", "rows": 0, "last": asof})
            log.error("CA board ledger: append_board wrote 0 rows for %s (%d calls)",
                      asof, len(calls))
        else:
            log.info("CA board ledger: logged %d ranked names for %s (ledger=%d)",
                     len(calls), asof, n)
        # nightly grade of matured calls — 'accruing' until forward returns exist. The
        # track-record PANEL (W6, §7.4) ships in 'accruing' state from day one, so ALWAYS
        # attach the scorecard (it self-reports status='accruing' with first_read_est until
        # the MIN_IC_DATES gate is met ≈ 2026-08-24). This is the desk's accountability
        # centerpiece — it must render honestly-empty, never be absent.
        setups["board_track"] = board_ledger.scorecard("CA")
        g = board_ledger.grade("CA")
        if g.get("available"):
            log.info("CA board ledger: grade n_calls=%s n_graded=%s n_suspended=%s",
                     g.get("n_calls"), g.get("n_graded"), g.get("n_suspended"))
    except Exception as e:  # noqa: BLE001 — fail-open-LOUD (health row + log)
        health.append({"en": "Board ledger (FAILED — see build log)",
                       "zh": "榜单账本（失败 — 查看构建日志）",
                       "status": "ERROR", "rows": 0, "last": asof})
        log.error("CA board ledger failed (%s)", e)
    return health


def _tailwind_freshness_gate(setups: dict | None, latest: dict) -> dict | None:
    """HARD freshness gate on the CA basket-tailwind axis (masterplan §2 principle 6):
    the tailwind panel (canada_search closes) must be no more than 3 trading days
    staler than the board's own price date. When it is, SUPPRESS the tailwind axis on
    every card and surface a banner. Returns a health row when suppressed, else None.

    Sets setups['tailwind_suppressed'] + setups['tailwind_stale_days'] so the template
    can hide the tailwind axis + show the on-page banner."""
    if not setups:
        return None
    board_date = pd.Timestamp(_board_asof(latest))
    cp = config.data_dir() / "canada_search" / "closes.parquet"
    if not cp.exists():
        setups["tailwind_suppressed"] = True
        setups["tailwind_stale_days"] = None
        return {"en": "Basket-tailwind axis SUPPRESSED (canada_search panel missing)",
                "zh": "篮子顺风轴已抑制（canada_search 面板缺失）",
                "status": "SUPPRESSED", "rows": 0, "last": "—"}
    try:
        idx = pd.read_parquet(cp, columns=[]).index
        tw_date = pd.Timestamp(idx.max())
    except Exception as e:  # noqa: BLE001
        log.warning("CA tailwind freshness: panel unreadable (%s)", e)
        return None
    # trading-day staleness ≈ business days between the two dates (calendar-day / weekend
    # aware; holidays make this a slight over-count, which fails SAFE — suppress sooner).
    stale_td = int(pd.bdate_range(tw_date, board_date).size - 1) if tw_date < board_date else 0
    setups["tailwind_stale_days"] = stale_td
    if stale_td > 3:
        setups["tailwind_suppressed"] = True
        log.error("CA tailwind freshness: panel %s is %d trading days staler than board %s "
                  "— tailwind axis SUPPRESSED", tw_date.date(), stale_td, board_date.date())
        return {"en": f"Basket-tailwind axis SUPPRESSED — panel {stale_td} trading days stale",
                "zh": f"篮子顺风轴已抑制 — 面板落后 {stale_td} 个交易日",
                "status": "SUPPRESSED", "rows": 0, "last": str(tw_date.date())}
    setups["tailwind_suppressed"] = False
    return None


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

        # Market State command-center (display-only) — the Canada 6-factor scorecard +
        # side-by-side .ms-front board. engine/canada_conditions.py builds the conditions
        # bundle (cross-asset overlay RORO + newly-built slowdown/drawdown gauges) in the
        # same shape as China/HK so engine/market_state_ca.py reuses the reader pattern.
        # None-safe; never breaks the page.
        try:
            from engine import canada_conditions as _cac
            from engine import market_state as _ms
            from engine.canada_inputs import build_features as _ca_feats
            from engine.market_state_ca import CA_PROFILE
            _f = _ca_feats()
            latest["conditions"] = _cac.snapshot(_f, latest.get("overlay") or {})
            # precompute the % >200d-MA 5y percentile + a price/breadth divergence flag for F4
            _b = _f["pct_above_200"].dropna() if "pct_above_200" in getattr(_f, "columns", []) else None
            if _b is not None and len(_b) >= 60:
                _win = _b.tail(252 * 5)
                _pctile = float((_win <= _win.iloc[-1]).mean())
                _px = _f["market_index"].dropna() if "market_index" in _f.columns else None
                _div = bool(_px is not None and len(_px) > 21 and len(_b) > 21
                            and _b.iloc[-1] < _b.iloc[-22] and _px.iloc[-1] > _px.iloc[-22])
                latest["conditions"]["breadth"] = {"above200_pctile": _pctile, "div": _div}
            # external-driver Risk Radar (engine/risk_radar_intl.py: US rate shocks, dollar
            # strength + breadth — the TSX is the least US-coupled of the three, so this is the
            # lightest read). Populated BEFORE market_state so CA_PROFILE.radar_override surfaces
            # it. None-safe; display-only.
            from engine import risk_radar_intl as _rri
            latest["risk_radar"] = _rri.snapshot(_rri.CA_PROFILE)
            # forward-grade self-audit + bounded auto-tune (vs realized TSX path); hard-forces the
            # verdict only once Canada's own log validates (can_force). Display-only until then.
            try:
                from engine import risk_radar_intl_audit as _rra, risk_radar_intl_tune as _rrt
                latest["risk_radar"]["forward_log"] = _rra.snapshot_and_grade(latest["risk_radar"], _rri.CA_PROFILE)
                latest["risk_radar"]["can_force"] = bool(latest["risk_radar"]["forward_log"].get("can_force"))
                _rrt.tune(_rri.CA_PROFILE)
            except Exception as _e:  # noqa: BLE001
                log.warning("canada risk-radar audit/tune failed (%s); skipping", _e)
            # Write the scorecard immediately after the CA ledger is updated so the
            # same-build card reflects today's just-appended row. Never fatal.
            try:
                from engine import risk_radar_scorecard as _rrs  # noqa: PLC0415
                _rrs.write()
            except Exception as _e:  # noqa: BLE001
                log.warning("build_canada: risk-radar scorecard write (pre-render) failed: %s", _e)
            vm["market_state"] = _ms.market_state_snapshot(
                latest, _f, latest.get("alerts") or [], profile=CA_PROFILE)
        except Exception as e:  # noqa: BLE001 — additive panel, never fatal
            log.error("canada market_state failed (%s); skipping", e)
            vm["market_state"] = None

        # ── ms_history: score_log forward ledger ─────────────────────────────
        # Appended nightly; deduped by date.  Never fatal.  Guard: only append
        # when market_state is populated AND we are NOT in a fast-render from
        # a pickled VM (house law: nightly is the sole advancer of ledgers).
        try:
            _ms_snap = vm.get("market_state")
            if _ms_snap and _ms_snap.get("score") is not None:
                import os as _osenv
                if not _osenv.environ.get("CANADA_FAST_RENDER"):
                    _score_log_dir = config.data_dir() / "canada_market_state"
                    _score_log_dir.mkdir(parents=True, exist_ok=True)
                    _score_log_path = _score_log_dir / "score_log.parquet"
                    _new_row = pd.DataFrame([{
                        "date": latest.get("date"),
                        "score": int(_ms_snap["score"]),
                        "verdict": _ms_snap.get("verdict", ""),
                        "color": _ms_snap.get("color", ""),
                    }])
                    if _score_log_path.exists():
                        _existing = pd.read_parquet(_score_log_path)
                        _combined = pd.concat([_existing, _new_row], ignore_index=True)
                        _combined = _combined.drop_duplicates(subset=["date"], keep="last")
                    else:
                        _combined = _new_row
                    _combined = _combined.sort_values("date").reset_index(drop=True)
                    _combined.to_parquet(_score_log_path, index=False)
                    # Expose last 11 rows as vm['ms_history'] for the hero path chart
                    _hist = _combined.tail(11).copy()
                    vm["ms_history"] = _hist.to_dict(orient="records")
                    log.info("canada score_log: %d rows, last 11 -> ms_history", len(_combined))
        except Exception as _msh_e:  # noqa: BLE001 — additive, never fatal
            log.warning("canada ms_history build failed (%s); skipping", _msh_e)
            vm.setdefault("ms_history", None)

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
        # AND apply the BRANCH-B ripe-list contract order (C7 verdict: all momentum
        # trials ACCRUE → composite suppressed, board = grouped ripe-list, rank pill).
        try:
            from scripts.build_canada_library import compute_canada_standouts
            vm["setups"] = compute_canada_standouts(setups, overlay=latest.get("overlay") or {})
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("canada standouts enrich failed (%s); using raw setups", e)

        # ── top_setups: top-5 buy rows for the glance card ───────────────────
        # MUST run AFTER vm["setups"] is assigned + standouts-enriched above
        # (the first cut ran before it → vm.get("setups") was None → the card
        # said "No active setups" while 10 buys existed). Never fatal.
        try:
            _su = vm.get("setups") or {}
            _buys = list((_su.get("buy") or []))
            for _row in _buys:
                if not isinstance(_row, dict):
                    continue
                if not _row.get("industry"):
                    _row["industry"] = _row.get("sub_industry") or _row.get("sector") or ""
            vm["top_setups"] = _buys[:5]
        except Exception as _ts_e:  # noqa: BLE001 — additive, never fatal
            log.warning("canada top_setups enrich failed (%s); skipping", _ts_e)
            vm["top_setups"] = []

        # ── BRANCH-B board ledger (masterplan §5.4) + hard freshness gate (§2.6) ──
        # This is the board's SCOREBOARD: log the ranked board each render, grade it
        # nightly. Fail-open-LOUD: a ledger failure surfaces a health row, never a crash.
        vm.setdefault("board_health", [])
        _cb = _canada_board_ledger(vm.get("setups"), latest)
        if _cb:
            vm["board_health"].extend(_cb)
        _tw = _tailwind_freshness_gate(vm.get("setups"), latest)
        if _tw:
            vm["board_health"].append(_tw)
        # Stocks-mode health banner (deliverable 5): the shared source health (which
        # already carries the HKCA-13 breadth close-cache MISSING flag from _health_rows)
        # PLUS the Branch-B board-ledger + tailwind-suppression rows. Only the DEGRADED
        # rows surface as a banner so a clean board shows nothing.
        _src_degraded = [h for h in (vm.get("health") or [])
                         if str(h.get("status", "")).upper() not in ("OK", "FRESH", "HEALTHY", "?")]
        vm["stocks_health"] = _src_degraded + vm["board_health"]
        # AI-brief doorway (W6 §7.5) — PRESENCE-GUARDED: only expose the link if a Canada
        # AI-brief page actually exists in the site output. None ships today, so the
        # template's {% if ca_aibrief_href %} keeps it hidden; the day a CA brief lands
        # (canada_aibrief.html / aibrief_canada.html) this lights up automatically.
        vm["ca_aibrief_href"] = next(
            (n for n in ("canada_aibrief.html", "aibrief_canada.html")
             if (site / n).exists()), None)

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
        # One shared view-model feeds BOTH the Canada macro-regime page and the new
        # TSX Stock Dashboard — the same canada.html.j2 is rendered twice with a `mode`
        # flag (macro / stocks) that selects which sections show. Mirrors China / HK.
        tmpl = env.get_template("canada.html.j2")
        # DEV-ONLY: dump the fully-built view-model so scripts/render_canada_fast.py
        # can re-render canada.html / canada_stocks.html in ~1s without re-running
        # collectors + engine. Env-gated (CANADA_VM_DUMP=1); never fires nightly.
        import os as _os
        if _os.environ.get("CANADA_VM_DUMP"):
            try:
                import pickle as _pkl
                _vm_cache = config.data_dir() / "_dev_canada_vm.pkl"
                with open(_vm_cache, "wb") as _fh:
                    _pkl.dump(vm, _fh)
                log.info("CANADA_VM_DUMP: wrote %s", _vm_cache)
            except Exception as _e:  # noqa: BLE001 — dev-only, never fatal
                log.error("CANADA_VM_DUMP failed (%s)", _e)
        html = tmpl.render(**vm, mode="macro")
        write_page(site / "canada.html", html)
        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, site)
        log.info("wrote %s/canada.html (%d KB, %d sectors)", site, len(html) // 1024, len(vm["sectors"]))

        # TSX Stock Dashboard — same VM, the standout-names half (show-more card strip).
        html_st = tmpl.render(**vm, mode="stocks")
        write_page(site / "canada_stocks.html", html_st)
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
            write_page(site / "canada_stock.html", stock_html)
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
