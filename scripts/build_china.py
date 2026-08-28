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

from lib import config, illus, site_assets, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

# The board definition the ENGINE is producing RIGHT NOW — imported, never copied.
# A local copy of this string ("cn_prophet_v2", added by #4029) went stale when #4509
# moved the board to cn_prophet_v3 on 2026-08-05: _is_current_prophet_artifact then
# rejected the live board AND the persisted fallback alike, so china_stocks.html
# served a "data coverage degraded — board incomplete today" outage shell on top of a
# complete, same-day board (24 featured / 204 eligible, as_of 2026-08-06). The reject
# is meant to catch a SUPERSEDED artifact, so it has to read the current definition
# from its producer or it re-breaks on every version bump.
#
# Module scope on purpose: main() wraps the whole vm assembly in a catch-all that only
# logs and returns 0, so an engine that cannot be imported has to fail HERE, loudly,
# rather than inside that handler where it would silently freeze both china pages.
from engine.china_board_rank import BOARD_DEFINITION as _CN_PROPHET_DEFINITION  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_china")

ASSETS = ("theme.css", "product-nav-icons.css", "dashboard-icons.css",
          "dashboard-icons.js", "theme.js",
          "mtf.js", "chart_i18n.js", "timemachine.js",
          "charts.js", "tablesort.js", "aibrief.js", "stockview.js",
          "illus.css", "illus.js")


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


def _is_current_prophet_artifact(doc: dict | None) -> bool:
    """True when `doc` is a board the CURRENT engine definition produced.

    Both halves are deliberate: the schema pin catches a shape the template cannot
    render, the definition pin catches a board from a SUPERSEDED ranking. Neither
    may be a copy that drifts from its producer — see the import note up top.
    """
    return bool(
        isinstance(doc, dict)
        and doc.get("schema_version") == "2.0.0"
        and doc.get("board_definition") == _CN_PROPHET_DEFINITION
    )


#: What this path tells the reader. It carries its OWN headline rather than
#: inheriting the W0.7 buy-count-collapse banner's, because that headline —
#: "data coverage degraded — board incomplete today" — is affirmatively FALSE
#: here and is the sentence that cost two days: on 2026-08-06 the data was
#: complete and current (24 names, as_of today) and the renderer simply refused
#: it, so the page reported a China FEED outage and that is what got chased.
#: "Incomplete" also understates the shell, which is empty, not partial.
#:
#: The wording asserts nothing about internals, because one `else` covers four
#: causes and each sentence has to be true on all of them: the live build may
#: have crashed OR built fine and been refused on a stamp, and the stored board
#: may be superseded, absent, or (after an engine rollback) NEWER. "Isn't
#: available" and "we won't show one from a different ranking" hold in every
#: case; "could not be built" and "an older board was withheld" did not. The
#: diagnosis belongs in the log line at the call site, not on the page.
#:
#: Version-free on purpose: the old copy named "v2" outright, so the moment the
#: engine moved to v3 the banner asserted a version that no longer existed —
#: and raw internal slugs are banned from glance-tier copy regardless. The
#: closing clause is the stance DESIGN_DOCTRINE requires, since on this path
#: the banner IS the whole panel.
_PROPHET_OUTAGE_HEADLINE = "no Prophet board today"
_PROPHET_OUTAGE_HEADLINE_ZH = "今日暂无先知榜单"
_PROPHET_OUTAGE_REASON = (
    "Today's board isn't available, and we won't show one from a different "
    "ranking in its place. Nothing to act on here today."
)
_PROPHET_OUTAGE_REASON_ZH = (
    "今日榜单暂不可用，我们不会用另一套排序的榜单顶替。今日此处无可操作标的。"
)


def _prophet_outage_shell(reason: str = _PROPHET_OUTAGE_REASON,
                          reason_zh: str = _PROPHET_OUTAGE_REASON_ZH) -> dict:
    """Never render a superseded board beneath the current Prophet heading."""
    return {
        "schema_version": "2.0.0",
        "as_of": None,
        "rank_by": _CN_PROPHET_DEFINITION,
        "board_definition": _CN_PROPHET_DEFINITION,
        "ranking": {},
        "buy": [],
        "more_actionable": [],
        "late_or_unfillable": [],
        "forming": [],
        "watch": [],
        "lane_counts": {
            "featured": 0,
            "more_actionable": 0,
            "late_or_unfillable": 0,
            "forming": 0,
        },
        "execution_coverage": {
            "raw_eligible": 0,
            "actionable_t1_t3": 0,
            "fresh_same_day_micro_count": 0,
            "fresh_same_day_micro_rate_pct": 0.0,
        },
        "laggards": [],
        "eligible": 0,
        "actionable": 0,
        "universe": 0,
        "quality_screen": {},
        "coverage": {},
        "sleeve_chip": {},
        "track_ledger": None,
        "cap_composition": {
            "large": 0, "mid": 0, "small": 0, "unknown": 0,
        },
        "ripening": [],
        "ripening_falling": [],
        "ran": [],
        "data_outage": {
            "flag": True,
            "headline": _PROPHET_OUTAGE_HEADLINE,
            "headline_zh": _PROPHET_OUTAGE_HEADLINE_ZH,
            "reason": reason,
            "reason_zh": reason_zh,
        },
    }


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
def _ilx(series: dict, accent: str, *, kind: str = "line", height: int = 190,
         baseline: float | None = None, reference: float | None = None,
         unit_en: str = "", unit_zh: str | None = None, bands=None,
         value_fmt: str = "{:,.1f}", aria_en: str = "") -> str:
    """Bridge an internals {dates, vals} dict to an ilx / Signal-Ink fragment.
    Replaces the retired Plotly `_panel_line`; all illustrative China charts route
    through lib.illus (SSR SVG + CSS animation, no client charting library)."""
    if not series or not series.get("dates"):
        return ""
    return illus.illus(series, kind=kind, accent=accent, height=height,
                       baseline=baseline, reference=reference,
                       unit_en=unit_en, unit_zh=unit_zh, bands=bands,
                       value_fmt=value_fmt, aria_en=aria_en or f"{kind} chart")


def china_regime_timeline(hist: pd.DataFrame) -> dict:
    """Compact columnar JSON for the client-side Time Machine (timemachine.js),
    mirroring build_site.regime_timeline() over the China regime history. The China
    engine doesn't track transition_state / recession / shock / warning flags, so
    those keys carry safe defaults — timemachine.js degrades to 'no warnings'."""
    # Labeled AND both axes present — mirror of build_hk.hk_regime_timeline():
    # a labeled-yet-axis-dark store row (the 2026-08-08 HK null-inflation-tail
    # shape) must never ship, no matter which lane wrote the store.
    h = hist[hist["quad"].notna()
             & hist["growth_score"].notna() & hist["inflation_score"].notna()].copy()
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
        # margin crowd meter — line, info accent, peak level as a reference marker
        margin["chart_html"] = _ilx(margin.get("chart"), "var(--info)", height=190,
                                     reference=margin.get("peak"), unit_en="%",
                                     value_fmt="{:,.2f}", aria_en="Margin financing chart")
        vm["margin"] = margin
    sb = ci.southbound_flow()
    if sb:
        # southbound flow — THE waterline (up-tint above 0, down-tint below)
        sb["chart_html"] = _ilx(sb.get("chart_cum"), "var(--info)", kind="baseline",
                                height=190, baseline=0, unit_en="亿", unit_zh="亿",
                                aria_en="Southbound cumulative flow chart")
        vm["southbound"] = sb
    credit = ci.credit_tape()
    if credit:
        if credit.get("impulse_chart"):
            credit["impulse_html"] = _ilx(credit["impulse_chart"], "var(--info)",
                                          kind="bars", height=180, baseline=0,
                                          unit_en="%", aria_en="Credit impulse chart")
        if credit.get("scissors_chart"):
            credit["scissors_html"] = _ilx(credit["scissors_chart"], "var(--info)",
                                           kind="bars", height=180, baseline=0,
                                           unit_en="pp", aria_en="M1 minus M2 chart")
        if credit.get("loans_chart"):
            credit["loans_html"] = _ilx(credit["loans_chart"], "var(--muted)",
                                        height=160, aria_en="New loans chart")
        vm["credit"] = credit
    flows = ci.flow_snaps()
    if flows:
        vm["flows"] = flows
    turn = ci.market_turnover()
    if turn:
        # turnover thermometer — line, warn accent; ¥1T threshold as reference
        turn["chart_html"] = _ilx(turn.get("chart"), "var(--warn)", height=150,
                                  reference=10000, unit_en="亿", unit_zh="亿",
                                  value_fmt="{:,.0f}", aria_en="Market turnover chart")
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
        # net rising cities — sign-colored bars around zero
        v["breadth"]["chart_html"] = _ilx(v["breadth"]["chart"], "var(--info)",
                                          kind="bars", height=170, baseline=0,
                                          value_fmt="{:,.0f}", aria_en="City price breadth chart")
    if v.get("climate") and v["climate"].get("chart"):
        # NBS builder climate — line, orange accent, neutral 100 reference
        v["climate"]["chart_html"] = _ilx(v["climate"]["chart"], "var(--orange)",
                                          height=170, reference=100,
                                          aria_en="Builder climate index chart")
    if v.get("construction") and v["construction"].get("chart"):
        v["construction"]["chart_html"] = _ilx(v["construction"]["chart"], "var(--info)",
                                               height=170, aria_en="Construction demand chart")
    if v.get("cgb") and v["cgb"].get("chart"):
        v["cgb"]["chart_html"] = _ilx(v["cgb"]["chart"], "var(--warn)", height=170,
                                      unit_en="%", value_fmt="{:,.2f}",
                                      aria_en="Government bond yield chart")
    if v.get("prop_etf") and v["prop_etf"].get("chart"):
        # property-ETF drawdown from all-time high — underwater fill
        v["prop_etf"]["chart_html"] = _ilx(v["prop_etf"]["chart"], "var(--down)",
                                           kind="drawdown", height=170, unit_en="%",
                                           aria_en="Property ETF drawdown chart")
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

    def row(x: dict, field: str, val_key: str) -> dict:
        name = x.get("SECURITY_NAME")  # Eastmoney has no separate EN name; name_zh==name
        return {"ticker": x.get("SECURITY_CODE"), "name": name, "name_zh": name,
                "chg": round(float(x.get("CHANGE_RATE") or 0), 2),
                val_key: round(float(x.get(field) or 0) / 1e8, 2)}   # 亿

    nb, sb = latest(nb), latest(sb)
    date = (nb or sb)[0]["TRADE_DATE"][:10] if (nb or sb) else None
    nb.sort(key=lambda x: -(x.get("DEAL_AMT") or 0))                 # foreign turnover
    sb.sort(key=lambda x: -(x.get("NET_BUY_AMT") or 0))             # mainland net
    return {"date": date,
            "northbound_turnover": [row(x, "DEAL_AMT", "turnover") for x in nb[:8]],
            "southbound_buy": [row(x, "NET_BUY_AMT", "net") for x in sb[:6]],
            "southbound_sell": [row(x, "NET_BUY_AMT", "net") for x in
                        sorted(sb, key=lambda x: (x.get("NET_BUY_AMT") or 0))[:4]]}


def _drilldown_closes() -> tuple[pd.DataFrame, str | None]:
    """Constituent close matrix for the per-sector drill-down holdings cards.

    Source of record is the curated breadth cache (china_breadth/_closes_cache.parquet,
    written by the collect lane). It is gitignored rebuild-only, so on the re-render
    lanes (build_vector -> build_china, no collectors) and in fresh worktrees it can be
    absent; there we fall back to the COMMITTED broad A-share search panel
    (china_search/closes.parquet, ~1560 top-mcap names) which carries 76/82 curated
    constituents with deep history. Curated cache is tried FIRST so the nightly lane's
    drill-down is byte-unchanged; the fallback only rescues lanes that lack the cache --
    the same china_search-first precedence build_china_library.universe() already uses,
    and mirrors scripts/build_canada.py::_drilldown_closes() (HKCA-13). Returns
    (df, source_label); (empty, None) when neither source is usable."""
    dd = config.data_dir()
    sources = [
        (dd / "china_breadth" / "_closes_cache.parquet", "china_breadth"),
        (dd / "china_search" / "closes.parquet", "china_search"),
    ]
    for path, label in sources:
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001 — corrupt committed parquet must not break the build
            log.error("china drill-down panel %s unreadable: %s", label, exc)
            continue
        if df.empty or df.shape[1] == 0:
            continue
        return df, label
    return pd.DataFrame(), None


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
    ccloses, _dd_src = _drilldown_closes()
    if not ccloses.empty:
        log.info("china sector drill-down: constituent panel = %s (%d names)",
                 _dd_src, ccloses.shape[1])
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
            a = analyze(close, market="CN")
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
    from engine.cycles import analyze, STATE_DISPLAY as _STATE_DISPLAY_MAP
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
            a = analyze(close, market="CN")
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
            "label_zh": _STATE_DISPLAY_MAP.get(lad.get("state") or "", {}).get("label_zh"),
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
    # Apply rotation re-rank (replaces the simple 60d RS sort).
    # score_and_rank:
    #   - augments each card with rotation_rank, rotation_score, oscillator
    #     readings and fast-RS momentum (mom5, mom10)
    #   - preserves the old 60d RS rank as card["rank60"]
    #   - overwrites card["rank"] with the rotation_rank so downstream
    #     consumers (template, pb_sector) see the new unified order
    #   - returns the list sorted by rotation_rank ascending (1 = best)
    from engine.china_sector_rotation import score_and_rank
    bench = config.load()["china"]["engine"]["rs_ranking"]["benchmark"]
    try:
        cards = score_and_rank(cards, closes, bench)
    except Exception as e:  # noqa: BLE001 — rotation is display-only; degrade gracefully
        log.warning("china_sector_rotation.score_and_rank failed (%s); falling back to 60d RS sort", e)
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
    macro instruments already on disk (SHCOMP, offshore yuan, gold, the 10Y CGB yield).
    Coloured by raw sign; semantic read lives in the panels below."""
    # (store group, ticker, column, en, zh, tag_en, tag_zh, decimals, is_rate, invert_tone)
    # NO CSI 300 / ChiNext rows: their face tiles are LIVE-ONLY (templates/china.html.j2).
    # The real index histories can't be baked honestly — Yahoo daily history runs weeks
    # stale for 000300.SS and is absent for 399006.SZ (probed 2026-08-11) — and the old
    # 510300.SS/159915.SZ ETF rows rendered NAVs ~4.7/~3.6 under index labels (the
    # 2026-08-11 production bug). Live spark quotes resolve both indexes fine.
    spec = [
        ("china", "000001.SS", "close", "Shanghai Comp", "上证综指", "index", "指数", 1, False, False),
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
                "sym": name,   # stable identifier for template lookup by ticker
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
            # signed DISTANCE from the 200-day average, not just the side of it. The
            # shared Risk Radar dialog's Leading tile reads "N% above/below its 200-day
            # average"; `above200` alone cannot say how stretched. Same px/ma200 already
            # computed above — no extra series read.
            "dist200": (round(100 * (px / ma200 - 1), 1) if ma200 == ma200 and ma200 else None),
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
    a = analyze(close, market="CN")
    return {"name": "Shanghai Composite", "ticker": mi,
            "mtf_json": json.dumps(a["mtf"]),
            "state": a["ladder"].get("state"), "label": a["ladder"].get("label"),
            "dc_day": a["cycle"].get("dc_day"), "dc_band": a["cycle"].get("dc_band"),
            "ic_week": a["cycle"].get("ic_week"), "ic_band": a["cycle"].get("ic_band"),
            "price": round(float(close.iloc[-1]), 2),
            "chg": round(100 * (close.iloc[-1] / close.iloc[-2] - 1), 2)}


# ── Risk Radar dialog view-model (templates/_risk_radar_dlg.html.j2) ─────────────────
# DISPLAY ASSEMBLY ONLY. Every value below is READ from a store some other engine step
# already computed — nothing here derives a statistic, scores anything, or gates
# anything. Each payload sits in its own try/except so a store that is missing, stale
# or malformed drops ONE section instead of the page (the macro renders every section
# conditionally, so an omitted key is an honest absence, never an error).
# The ctx schema is the shared CN/HK/CA contract — see the header of
# templates/_risk_radar_dlg.html.j2 before changing a key name.

_CN_PBOC_ZH = {"easing": "宽松", "neutral": "中性", "tightening": "收紧"}
_CN_PBOC_EN = {"easing": "Easing", "neutral": "Neutral", "tightening": "Tightening"}


def _rd_word(value, bands):
    """Pick the (en, zh, tone) triple whose threshold `value` clears. `bands` is an
    ordered [(threshold, en, zh, tone), ...] high-to-low; the last entry is the floor."""
    if value is None:
        return None
    for thr, en, zh, tone in bands:
        if value >= thr:
            return (en, zh, tone)
    return None


def _radar_dlg_vm(vm: dict, latest: dict) -> dict:
    """Assemble the `radar_dlg` ctx the shared Risk Radar dialog consumes on china.html.

    Reads ONLY values already on the view-model / in already-built stores:
      leading   index_health SHCOMP row (dist200) + the radar's own dominant firing leg
      overseas  market_state.radar.contagion   (data/contagion_links/latest.json)
      track     market_state.radar.track       (data/risk_radar/scorecard.json markets.cn)
      calendar  vm['event_strip'] / vm['calendar']  (engine/china_event_calendar.py)
      chips     internals.pboc + cn_market_state_json.external.usdcnh
      factors   cn_participation_json (margin_to_mcap, qvix) + internals.southbound
                + cn_microstructure_json.latest_aggregate (limit-up counts)
      gauges    latest.conditions recession score + the two rendered ilx charts
      leaders   vm['top_setups'] (the standout board's own display rows) + the
                limit-up heat line
      fx        market_state.radar.fx_context  (lib/forex_link)
    """
    ctx: dict = {}
    rd = ((vm.get("market_state") or {}).get("radar")) or {}

    # ── one as-of for the whole dialog ────────────────────────────────────────────
    try:
        ctx["asof"] = str(latest.get("date") or "")[:10] or None
    except Exception:  # noqa: BLE001
        pass

    # Plain-word profile caveat. NOT the engine's RadarProfile.caveat_en: that string
    # opens with the word "validated", which is CI-forbidden in emitted copy
    # (scripts/check_validated_claims.py) — and its jargon ("US–China yield differential")
    # is Tier-1 banned besides. This says the same thing in the doctrine's language.
    # The trailing clause restores the effect-size honesty the first rewrite dropped:
    # CN_PROFILE's caveat opens "Validated but modest" — the CI-forbidden word had to go,
    # the word "modest" did not. Without it the sentence reads as a strong claim.
    ctx["caveat_en"] = ("A-share pullbacks are mostly led from outside — US rates, the yuan, "
                        "and how broadly the market is falling. The pull is real but modest.")
    ctx["caveat_zh"] = ("A股回撤多由外部因素引导——美债利率、人民币汇率，以及下跌的广度。"
                        "这种引导确实存在，但幅度有限。")

    # ── Leading tile: benchmark stretch vs its 200-day average + the loudest leg ──
    try:
        row = next((r for r in (vm.get("index_health") or [])
                    if r.get("ticker") == "000001.SS"), None)
        dist = row.get("dist200") if row else None
        leg = None
        for s in (rd.get("scares") or []):
            if s.get("label_en") == rd.get("label_en") and s.get("firing_legs"):
                leg = (s["firing_legs"][0] or {}).get("leg")
                break
        if dist is not None or leg:
            ctx["leading"] = {
                "bench_en": "Shanghai Composite", "bench_zh": "上证综指",
                "stretch_pct": dist, "leg": leg,
                "tip_en": ("Where the index sits against its own 200-day average. "
                           "The further above, the more there is to give back."),
                "tip_zh": "指数当前点位相对自身200日均线的位置。高出越多，可回吐的空间越大。",
            }
    except Exception as e:  # noqa: BLE001 — one tile, never the page
        log.warning("radar_dlg leading tile skipped (%s)", e)

    # ── Overseas tile: imported pressure (contagion links) ────────────────────────
    try:
        cg = rd.get("contagion") or {}
        if cg.get("level"):
            exp = []
            for e in (cg.get("top_exporters") or [])[:3]:
                dd = e.get("dd21")
                if e.get("name_en") and dd is not None:
                    exp.append((e["name_en"], e.get("name_zh") or e["name_en"], round(dd * 100)))
            ctx["overseas"] = {
                "level": cg.get("level"),
                "line_en": cg.get("line_en"), "line_zh": cg.get("line_zh"),
                "tip_en": ("How far the markets that trade with China have fallen from their "
                           "own recent highs: "
                           + " · ".join(f"{n} {d}% off" for n, _z, d in exp)) if exp else None,
                "tip_zh": ("与中国关联最深的市场距各自近期高点的回撤："
                           + "；".join(f"{z} {d}%" for _n, z, d in exp)) if exp else None,
            }
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg overseas tile skipped (%s)", e)

    # ── Track-record tile: this market's own graded ledger, past year ─────────────
    try:
        al = (((rd.get("track") or {}).get("windows") or {}).get("y1") or {}).get("alerts") or {}
        if al:
            ctx["track"] = {"n": al.get("n") or 0, "tp": al.get("tp") or 0,
                            "hit_rate": al.get("hit_rate")}
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg track tile skipped (%s)", e)

    # ── Calendar tile: next high-impact releases. Display-only listing. ───────────
    try:
        rows = list(vm.get("event_strip") or []) or list(vm.get("calendar") or [])
        cal = [{"date": r.get("date"), "name_en": r.get("name_en"),
                "name_zh": r.get("name_zh"), "importance": r.get("importance")}
               for r in rows[:3] if r.get("date") and r.get("name_en")]
        if cal:
            ctx["calendar"] = cal
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg calendar tile skipped (%s)", e)

    # ── Context chips: policy stance + the offshore yuan ──────────────────────────
    chips = []
    try:
        pb = (vm.get("internals") or {}).get("pboc") or {}
        bias = pb.get("bias")
        if bias in _CN_PBOC_EN:
            rrr = pb.get("rrr_big")
            chips.append({
                "label_en": "Policy stance", "label_zh": "政策取向",
                "value_en": _CN_PBOC_EN[bias], "value_zh": _CN_PBOC_ZH[bias],
                "tone": {"easing": "up", "tightening": "down"}.get(bias, "muted"),
                "tip_en": (f"Reserve requirement for the big banks is {rrr}% — the lower it "
                           "goes, the more the banks can lend.") if rrr is not None else None,
                "tip_zh": (f"大型银行存款准备金率为 {rrr}%——比率越低，银行可放贷的资金越多。")
                          if rrr is not None else None,
            })
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg policy chip skipped (%s)", e)
    try:
        ext = ((vm.get("cn_market_state_json") or {}).get("external") or {}).get("usdcnh") or {}
        q, ch = ext.get("quote"), ext.get("chg_pct")
        if q is not None:
            # USD/CNH UP = more yuan per dollar = a weaker yuan = a headwind for A-shares.
            if ch is None or abs(ch) < 0.05:
                d_en, d_zh, tone = "steady", "持平", "muted"
            elif ch > 0:
                d_en, d_zh, tone = "weaker", "走弱", "down"
            else:
                d_en, d_zh, tone = "firmer", "走强", "up"
            chips.append({
                "label_en": "Offshore yuan", "label_zh": "离岸人民币",
                "value_en": f"{q:.2f}, {d_en}", "value_zh": f"{q:.2f}，{d_zh}",
                "tone": tone,
                "tip_en": ("Yuan per dollar offshore"
                           + (f", {ch:+.1f}% on the day" if ch is not None else "")
                           + ". A weaker yuan is a headwind for A-shares."),
                "tip_zh": ("离岸市场每美元兑人民币"
                           + (f"，当日 {ch:+.1f}%" if ch is not None else "")
                           + "。人民币走弱对A股构成逆风。"),
            })
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg yuan chip skipped (%s)", e)
    if chips:
        ctx["policy_chips"] = chips

    # ── Country factor rows: who is crowded, how fearful, how hot the tape is ─────
    factors = []
    part = vm.get("cn_participation_json") or {}
    try:
        m2m = part.get("margin_to_mcap")
        pctile = ((vm.get("internals") or {}).get("margin") or {}).get("pctile")
        if m2m is not None:
            w = _rd_word(pctile, [(80, "crowded", "拥挤", "down"),
                                  (55, "building", "升温", "warn"),
                                  (0, "calm", "平静", "up")]) or ("—", "—", "muted")
            factors.append({
                "label_en": "Margin balance", "label_zh": "两融余额",
                "value": f"{m2m:.2f}%", "read_en": w[0], "read_zh": w[1], "tone": w[2],
                "pct": int(pctile) if isinstance(pctile, (int, float)) else None,
                "tip_en": ("Borrowed money invested in A-shares, as a share of tradable market "
                           "value. Crowded borrowing makes a fall run further."),
                "tip_zh": "两融余额占流通市值的比重。杠杆越拥挤，下跌时的连锁反应越大。",
            })
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg margin row skipped (%s)", e)
    try:
        qv, qz = part.get("qvix"), part.get("qvix_z")
        if qv is not None:
            w = _rd_word(qz, [(1.0, "fearful", "恐慌", "down"),
                              (0.0, "building", "升温", "warn"),
                              (-99, "calm", "平静", "up")]) or ("—", "—", "muted")
            factors.append({
                "label_en": "Options fear", "label_zh": "期权恐慌",
                "value": f"{qv:.1f}", "read_en": w[0], "read_zh": w[1], "tone": w[2],
                "tip_en": ("What options traders are paying for protection on the CSI 300. "
                           "Higher means more demand for downside cover."),
                "tip_zh": "沪深300期权隐含波动率——数值越高，说明市场为下跌保护付出的代价越大。",
            })
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg qvix row skipped (%s)", e)
    try:
        agg = (vm.get("cn_microstructure_json") or {}).get("latest_aggregate") or {}
        lu = agg.get("limit_up_count")
        if lu is not None:
            lu = int(lu)
            w = _rd_word(lu, [(60, "hot", "火热", "down"),
                              (25, "building", "升温", "warn"),
                              (0, "quiet", "清淡", "muted")]) or ("—", "—", "muted")
            factors.append({
                "label_en": "Limit-up breadth", "label_zh": "涨停梯队",
                # no bar: a raw count has no honest 0-100 scale to draw against, and a
                # made-up ceiling is the vetoed "fake magnitude bar" idiom (DESIGN_DOCTRINE §3).
                "value": f"{lu}", "read_en": w[0], "read_zh": w[1], "tone": w[2], "pct": None,
                "tip_en": "How many A-shares hit their daily price limit today.",
                "tip_zh": "今日触及涨停板的A股数量。",
            })
            sealed = agg.get("sealed_up_close")
            if sealed is not None and lu > 0:
                sealed = int(sealed)
                ratio = sealed / lu
                w2 = _rd_word(ratio, [(0.7, "firm", "牢固", "muted"),
                                      (0.4, "mixed", "参半", "muted"),
                                      (0, "loose", "松动", "muted")]) or ("—", "—", "muted")
                factors.append({
                    "label_en": "Held to the close", "label_zh": "收盘封住",
                    "value": f"{sealed}", "read_en": w2[0], "read_zh": w2[1], "tone": "muted",
                    "tip_en": (f"{sealed} of the {lu} names that hit their limit were still "
                               "limit-up at the close — the rest were sold back down."),
                    "tip_zh": f"今日 {lu} 只涨停股中，{sealed} 只收盘仍封住涨停，其余盘中被打开。",
                })
            lb = agg.get("lianban_2plus")
            if lb is not None:
                lb = int(lb)
                w3 = _rd_word(lb, [(15, "hot", "火热", "down"),
                                   (5, "building", "升温", "warn"),
                                   (1, "thin", "稀少", "muted"),
                                   (0, "none", "无", "muted")]) or ("—", "—", "muted")
                factors.append({
                    "label_en": "Second-day runners", "label_zh": "连板家数",
                    "value": f"{lb}", "read_en": w3[0], "read_zh": w3[1], "tone": w3[2],
                    "tip_en": ("Names that hit the limit again after doing it the day before — "
                               "the clearest sign speculative money is chasing."),
                    "tip_zh": "连续两日以上涨停的个股数量——投机资金追逐程度最直接的体现。",
                })
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg microstructure rows skipped (%s)", e)
    try:
        sb = (vm.get("internals") or {}).get("southbound") or {}
        cum, days = sb.get("cum_20d"), sb.get("pos_days_20")
        if cum is not None:
            # /100 → 亿, the page's own established southbound display unit
            # (templates/china.html.j2 southbound card + flows dialog use the same divisor).
            yi = cum / 100.0
            if days is not None and days >= 12:
                w = ("buying", "净买入", "up")
            elif days is not None and days <= 7:
                w = ("selling", "净卖出", "down")
            else:
                w = ("mixed", "进出参半", "muted")
            factors.append({
                "label_en": "Southbound, 20 sessions", "label_zh": "南向资金 · 近20日",
                "value": f"{'+' if yi >= 0 else '−'}¥{abs(yi):,.0f}亿",
                "read_en": w[0], "read_zh": w[1], "tone": w[2],
                "tip_en": (f"Mainland money into Hong Kong over the last 20 sessions"
                           + (f", net buyers on {days} of them" if days is not None else "")
                           + ". Read it as risk appetite, not as an A-share flow."),
                "tip_zh": ("近20个交易日内地资金流入港股的净额"
                           + (f"，其中 {days} 日为净买入" if days is not None else "")
                           + "。反映风险偏好，并非A股本身的资金流。"),
            })
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg southbound row skipped (%s)", e)
    if factors:
        ctx["factors"] = factors
    # ONE merged note under the rows (DESIGN_DOCTRINE Law 4 — one footnote per panel).
    # It carries the disclosure the plain-word caveat rewrite dropped: CN_PROFILE's own
    # caveat ends "the internal froth legs are excluded (they mean-revert)", i.e. NONE of
    # the rows above (margin, options fear, limit-up, southbound) is an input to the risk
    # score — its legs are rateshock / usd_cnh / us_cn_diff / cn_breadth. Without this the
    # section reads as a causal breakdown of the headline number, which it is not.
    # The participation store is a separate nightly step and can lag the page by days;
    # that clause joins the SAME note rather than adding a second one.
    _note_en = ("These local readings are context. The risk score itself is driven by US "
                "rates, the yuan and how broadly the market is falling.")
    _note_zh = "以上本地读数仅为背景。风险分数本身由美债利率、人民币汇率与市场下跌的广度驱动。"
    try:
        p_date = str(part.get("date") or "")[:10]
        page_date = str(latest.get("date") or "")[:10]
        if p_date and page_date and p_date < page_date:
            _note_en += (f" Margin and options figures are as of {p_date}, a little behind "
                         "the rest of this page.")
            # no leading space: a half-width gap after 。 is a stray in Chinese setting
            _note_zh += f"两融与期权读数截至 {p_date}，略滞后于本页其余数据。"
    except Exception:  # noqa: BLE001
        pass
    ctx["factors_note_en"], ctx["factors_note_zh"] = _note_en, _note_zh

    # ── Gauges: the two CN charts the old bespoke dialog carried (nothing lost) ───
    # LABEL <-> SOURCE, settled 2026-08-11 against engine/china_conditions.py — the old
    # `#cnx-dlg-risk` had them CROSSED, and nobody noticed because both of its charts read
    # `conditions.recession.chart_html` / `conditions.drawdown.chart_html`, keys the
    # builder never writes (it writes `recession_html` / `drawdown_html` on `conditions`),
    # so the charts were dead markup. W1 preserved the crossed pairing and made it visible.
    # The engine's own definitions:
    #   conditions["recession"]      = china_recession()  -> weighted macro SLOWDOWN legs
    #                                  (credit impulse, PPI, PMI, M1-M2, property, GDP);
    #                                  charts["recession"] is that same series, and
    #                                  build_china stamps it aria_en="Slowdown gauge chart".
    #   conditions["drawdown_risk"]  = china_drawdown()   -> expanding rank-percentile of
    #                                  A-share stress legs (slowdown + margin froth + flat
    #                                  CGB + QVIX + turnover mania) = DEEP-DRAWDOWN risk;
    #                                  charts["drawdown"], aria_en="Drawdown gauge chart".
    # Read-words come from the ENGINE's own band label (`recession.label` on _REC_BANDS
    # 26/45, `drawdown_risk.band` on 50/75/90), not from thresholds invented here — the
    # old 60/40 cut points contradicted the gauge's own history-anchored bands.
    _REC_READ = {"low": ("calm", "平静", "up"),
                 "elevated": ("softening", "走弱", "warn"),
                 "high": ("weak", "疲弱", "down")}
    _DD_READ = {"low": ("calm", "平静", "up"),
                "elevated": ("building", "升温", "warn"),
                "high": ("high", "偏高", "down"),
                "extreme": ("extreme", "极高", "down")}
    try:
        cond = latest.get("conditions") or {}
        gauges = []
        rec = cond.get("recession") or {}
        rec_sc = rec.get("score")
        if rec_sc is not None or cond.get("recession_html"):
            w = _REC_READ.get(rec.get("label"), (None, None, "muted"))
            gauges.append({
                "label_en": "Slowdown gauge", "label_zh": "放缓仪表",
                "score": round(rec_sc) if rec_sc is not None else None,
                "read_en": w[0], "read_zh": w[1], "tone": w[2],
                "chart_html": cond.get("recession_html"),
            })
        dd = cond.get("drawdown_risk") or {}
        dd_sc = dd.get("score")
        if dd_sc is not None or cond.get("drawdown_html"):
            w = _DD_READ.get(dd.get("band"), (None, None, "muted"))
            gauges.append({
                "label_en": "Deep-drawdown gauge", "label_zh": "深跌仪表",
                "score": round(dd_sc) if dd_sc is not None else None,
                "read_en": w[0], "read_zh": w[1], "tone": w[2],
                "chart_html": cond.get("drawdown_html"),
            })
        if gauges:
            ctx["gauges"] = gauges
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg gauges skipped (%s)", e)

    # ── Leaders: the standout board's own top rows + the limit-up heat line ───────
    try:
        rows = []
        for i, s in enumerate(list(vm.get("top_setups") or [])[:5]):
            if not isinstance(s, dict) or not s.get("ticker"):
                continue
            nm = str(s.get("name") or "")
            nm_en = nm.split(" / ", 1)[0].strip() or s["ticker"]
            # Name only — no industry. `industry`/`sector` are English-only strings on
            # these rows, so appending one gives the ZH view "中国卫星 · Industrials":
            # untranslated English inside Chinese copy, a bilingual-parity defect
            # (DESIGN_DOCTRINE §5.5). Ticker + name + board rank is complete on its own.
            rows.append({
                "ticker": s["ticker"],
                "name_en": nm_en,
                "name_zh": s.get("name_zh") or nm_en,
                "value": f"#{i + 1}", "pct": None, "tone": "muted",
            })
        agg = (vm.get("cn_microstructure_json") or {}).get("latest_aggregate") or {}
        lu, lb = agg.get("limit_up_count"), agg.get("lianban_2plus")
        line_en = line_zh = None
        if lu is not None and lb is not None:
            lu, lb = int(lu), int(lb)
            if lb > 0:
                line_en = f"Today {lu} names hit their daily limit, {lb} for a second day running."
                line_zh = f"今日 {lu} 只个股涨停，其中 {lb} 只连板。"
            else:
                line_en = f"Today {lu} names hit their daily limit, none for a second day."
                line_zh = f"今日 {lu} 只个股涨停，无连板。"
        if rows or line_en:
            ctx["leaders"] = {
                "line_en": line_en, "line_zh": line_zh, "rows": rows,
                "absent_en": "Coverage building — no names on the standout board today.",
                "absent_zh": "数据积累中 — 今日标的板暂无名单。",
            }
    except Exception as e:  # noqa: BLE001
        log.warning("radar_dlg leaders skipped (%s)", e)

    # ── FX context (already attached to the radar by lib/forex_link) ──────────────
    try:
        if rd.get("fx_context"):
            ctx["fx"] = rd["fx_context"]
    except Exception:  # noqa: BLE001
        pass

    return ctx


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
                assemble_act_now, load_cycle_rows, load_member_names, load_theme_intel,
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
            # Hover-card leaders print company names, never bare symbols.
            _member_names = load_member_names(str(baskets_json_path))
            act_now_v2 = assemble_act_now(
                sectors, theme_intel, cycle_rows,
                basket_turn=_basket_turn_cn,
                ths_baskets=_ths_baskets,
                member_names=_member_names,
                href_exists=lambda h: (site_dir / h).exists(),
            )
            # W8-R3 rider: persist the assembled board so build_china_sector_central can
            # read+render the same four-lane act-now board on the China SI Overview
            # (reader pattern — build_china is a serial head that runs first in asia-close.yml).
            if act_now_v2 is not None:
                _anv2_out = {"act_now_v2": act_now_v2,
                             "sectors_by_ticker": {s["ticker"]: s for s in sectors}}
                (site_dir / "chinabasketdata" / "act_now_cn.json").write_text(
                    json.dumps(_anv2_out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
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
                cond["roro_html"] = _ilx(ch.get("roro"), "var(--info)", kind="bars",
                                         height=170, baseline=0, aria_en="Risk-on/off chart")
                cond["recession_html"] = _ilx(ch.get("recession"), "var(--warn)",
                                              height=150, aria_en="Slowdown gauge chart")
                cond["drawdown_html"] = _ilx(ch.get("drawdown"), "var(--down)",
                                             height=150, aria_en="Drawdown gauge chart")
                fe = latest.get("fear_euphoria")
                if fe is not None and ch.get("fear_euphoria"):
                    # 0-100 fear↔euphoria percentile: soft warn zone ≥70 (Euphoria),
                    # soft info zone ≤30 (Fear); plum accent per the ilx China ruling.
                    fe_bands = [
                        {"hi": 100, "lo": 70,
                         "tint": "color-mix(in srgb, var(--warn) 15%, transparent)",
                         "label_en": "Euphoria", "label_zh": "亢奋", "pos": "top"},
                        {"hi": 30, "lo": 0,
                         "tint": "color-mix(in srgb, var(--info) 15%, transparent)",
                         "label_en": "Fear", "label_zh": "恐惧", "pos": "bottom"},
                    ]
                    fe["chart_html"] = _ilx(ch["fear_euphoria"], "#c08bd8", height=160,
                                            bands=fe_bands, value_fmt="{:,.0f}",
                                            aria_en="Fear and euphoria gauge chart")
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
            # Ledger/tuner advance ONLY on the nightly lane (house law: nightly is the sole
            # advancer); re-render lanes take the read-only scorecard fast-path.
            try:
                from engine import risk_radar_intl_audit as _rra
                if _rra.ledger_lane_armed():
                    from engine import risk_radar_intl_tune as _rrt
                    latest["risk_radar"]["forward_log"] = _rra.snapshot_and_grade(latest["risk_radar"], _rri.CN_PROFILE)
                    latest["risk_radar"]["can_force"] = bool(latest["risk_radar"]["forward_log"].get("can_force"))
                    _rrt.tune(_rri.CN_PROFILE)
                else:
                    # Read-only fast-path: snapshot still renders; ledger/tuner do not advance.
                    _sc = _rra.scorecard(_rri.CN_PROFILE.key, log_governance=False)
                    latest["risk_radar"]["forward_log"] = _sc
                    latest["risk_radar"]["can_force"] = bool(_sc.get("can_force"))
            except Exception as _e:  # noqa: BLE001
                log.warning("china risk-radar audit/tune failed (%s); skipping", _e)
            # Write the scorecard immediately after the CN ledger is updated so the
            # same-build card reflects today's just-appended row. Never fatal.
            try:
                from engine import risk_radar_scorecard as _rrs  # noqa: PLC0415
                _rrs.write()
            except Exception as _e:  # noqa: BLE001
                log.warning("build_china: risk-radar scorecard write (pre-render) failed: %s", _e)
            # CGL W1: load the contagion artifact so the directed-pressure table
            # (template CGL var) is available; the actual per-market pressure block
            # is attached to vm["market_state"]["radar"] AFTER market_state_snapshot
            # builds the post-transform rd dict (_radar_to_rd rebuilds from scratch
            # so pre-transform attachments to latest["risk_radar"] are discarded).
            vm.setdefault("CGL", None)
            _cgl_art_cn: dict | None = None
            try:
                _cgl_path = config.data_dir() / "contagion_links" / "latest.json"
                if _cgl_path.exists():
                    _cgl_art_cn = json.loads(_cgl_path.read_text(encoding="utf-8"))
                    vm["CGL"] = _cgl_art_cn
            except Exception:  # noqa: BLE001 — additive, never fatal
                pass
            vm["market_state"] = _ms.market_state_snapshot(
                latest, _f, latest.get("alerts") or [], profile=CN_PROFILE)
            # Attach contagion block to the post-transform radar dict so rd.contagion
            # resolves in _risk_radar_card.html.j2 (build_site.py idiom, CGL W1).
            # FIX 2: disclose staleness when the CGL artifact predates the page's as_of.
            try:
                if _cgl_art_cn and vm.get("market_state") and isinstance(
                    (vm["market_state"] or {}).get("radar"), dict
                ):
                    _cn_pressure = (_cgl_art_cn.get("pressure") or {}).get("cn")
                    if _cn_pressure is not None:
                        _blk = dict(_cn_pressure)
                        try:
                            from datetime import date as _date_cls  # noqa: PLC0415
                            _cgl_built_date = str(_cgl_art_cn.get("built", ""))[:10]
                            _page_asof = str(latest.get("date", ""))[:10]
                            if _cgl_built_date and _page_asof and _cgl_built_date < _page_asof:
                                _blk["stale"] = True
                                _blk["built_date"] = _cgl_built_date
                        except Exception:  # noqa: BLE001
                            pass
                        vm["market_state"]["radar"]["contagion"] = _blk
            except Exception:  # noqa: BLE001 — additive, never fatal
                pass
            # MSX-1 FX context attach — post-transform, mirrors CGL pattern above.
            # Reads data/forex/latest.json via lib.forex_link (fail-open).
            # Absent forex data → no attach (never blocks the build).
            # stale=True when forex asof predates the page's as_of (mirrors CGL staleness).
            try:
                if vm.get("market_state") and isinstance(
                    (vm["market_state"] or {}).get("radar"), dict
                ):
                    from lib import forex_link as _fxl  # noqa: PLC0415
                    _fxl.attach_fx_context(
                        vm["market_state"]["radar"],
                        page_asof=str(latest.get("date", "") or ""),
                    )
            except Exception:  # noqa: BLE001 — additive, never fatal
                pass
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
            # exc_info: this fallback silently served a stale china_standouts.json for
            # 3 sessions (07-13→07-16) because the one-line message gave no traceback
            # to locate the crash. Full traceback or the outage is invisible in CI.
            log.error("china stock library build failed (%s); skipping — will fall back "
                      "to the persisted (possibly STALE) china_standouts.json", e, exc_info=True)
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

        # CN THEME TAPE (W-C) — theme cycle state × member board states × why-not
        # attributions, for the panel below the stock board. The whole join lives in
        # engine/cn_theme_tape.py; this only reads the finished nightly artifacts and
        # hands it the frames. Display tier, zero authority: it ranks, gates and sizes
        # nothing, and every source is read-only here.
        #
        # Each source is read in its own try, so one unreadable artifact costs its own
        # chip and not the panel — a missing flow desk drops the flow chips, a missing
        # continuation ledger drops the watch marks, and the tape still renders. If the
        # two that matter (baskets + cycles) are gone, build_cn_theme_tape returns None
        # and the partial emits nothing at all.
        vm["cn_theme_tape"] = None
        try:
            import pandas as _pd

            from engine.cn_theme_tape import build_cn_theme_tape

            _data = config.data_dir()

            def _opt_parquet(path):
                """Read an optional frame; absence and corruption both degrade to None."""
                try:
                    return _pd.read_parquet(path) if path.exists() else None
                except Exception as _e:  # noqa: BLE001 — additive, never fatal
                    log.warning("cn theme tape: %s unreadable (%s)", path.name, _e)
                    return None

            def _opt_json(path):
                try:
                    return json.loads(path.read_text()) if path.exists() else None
                except Exception as _e:  # noqa: BLE001 — additive, never fatal
                    log.warning("cn theme tape: %s unreadable (%s)", path.name, _e)
                    return None

            _membership = _opt_json(_data / "baskets_china" / "membership.json")
            if _membership:
                vm["cn_theme_tape"] = build_cn_theme_tape(
                    _membership,
                    _opt_parquet(_data / "china_sector_cycles" / "forward_log.parquet"),
                    _opt_parquet(_data / "china_prophet_rank" / "candidates.parquet"),
                    flow=_opt_json(site / "flowdata" / "desk.json"),
                    watch=_opt_parquet(_data / "china_standout_track" / "board.parquet"),
                )
                log.info("cn theme tape: %d themes shown",
                         len((vm["cn_theme_tape"] or {}).get("rows") or []))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("cn theme tape unavailable (%s)", e)

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
        if not _is_current_prophet_artifact(vm.get("setups")):
            fallback = _load_json(factordata / "china_standouts.json")
            if _is_current_prophet_artifact(fallback):
                vm["setups"] = fallback
                log.info(
                    "using persisted China Prophet v2 fallback (%d featured)",
                    len(fallback.get("buy") or []),
                )
            else:
                vm["setups"] = _prophet_outage_shell()
                log.error(
                    "China Prophet board unavailable; rejected persisted fallback "
                    "stamped %r (current definition is %r)",
                    (fallback or {}).get("board_definition"),
                    _CN_PROPHET_DEFINITION,
                )
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
            _rd_asof = str((_rd_artifact or {}).get("as_of") or "")[:10]
            _board_asof = str((vm.get("setups") or {}).get("as_of") or "")[:10]
            if (
                _rd_artifact
                and _rd_asof
                and _rd_asof == _board_asof
                and isinstance(_rd_artifact.get("rows"), list)
            ):
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
                log.warning(
                    "china stocks: reversion desk hidden (desk asof=%s, board asof=%s)",
                    _rd_asof or "missing",
                    _board_asof or "missing",
                )
        except Exception as _rd_e:  # noqa: BLE001 — additive, never fatal
            log.error("china stocks: reversion_desk load failed (%s); skipping", _rd_e)
            vm["reversion_desk"] = None

        # W-FCT: ticker → "EN / ZH" display-name map for panels whose artifacts
        # don't carry names (Turn Setups / mtf_upturn_cn). data/china_search/
        # members.parquet is COMMITTED, so this resolves on re-render lanes too.
        # Never fatal; the template degrades to ticker-only for missing names.
        try:
            _nm_syms = set((((vm.get("mtf_upturn_cn") or {}).get("members")) or {}).keys())
            _nm_map = {}
            if _nm_syms:
                _mem = pd.read_parquet(
                    config.data_dir() / "china_search" / "members.parquet",
                    columns=["name"])
                _all_names = {str(k): str(v) for k, v in _mem["name"].items()}
                _nm_map = {s: _all_names[s] for s in _nm_syms if s in _all_names}
            vm["cn_name_by_ticker"] = _nm_map
        except Exception as _nm_e:  # noqa: BLE001 — additive, never fatal
            log.warning("cn_name_by_ticker map failed (%s); Turn Setups names "
                        "degrade to ticker-only", _nm_e)
            vm["cn_name_by_ticker"] = {}

        # ── MX5 hero: 11-session score path log ──────────────────────────────
        # Appended nightly; deduped by date.  Never fatal.  The READ is
        # unconditional — every render (incl. CHINA_FAST_RENDER dev renders and
        # nights where the snapshot degrades) draws the path from the committed
        # log; only the APPEND is gated so off-lane renders never advance the
        # ledger (house law: nightly is the sole advancer).
        try:
            import os as _osenv
            _score_log_path = config.data_dir() / "china_market_state" / "score_log.parquet"
            _ms_snap = vm.get("market_state")
            _ms_sc = _ms_snap.get("score") if _ms_snap else None
            if _osenv.environ.get("CHINA_FAST_RENDER"):
                pass                       # dev re-render: read-only, never append
            elif _ms_sc is None:
                log.warning("china score_log: market_state score unavailable — no append "
                            "(path renders from the committed log)")
            else:
                _score_log_path.parent.mkdir(parents=True, exist_ok=True)
                _new_row = pd.DataFrame([{
                    "date": latest.get("date"),
                    "score": int(_ms_sc),
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
            if _score_log_path.exists():
                _all = pd.read_parquet(_score_log_path).sort_values("date")
                _hist = _all.tail(11).copy()
                vm["ms_history"] = _hist.to_dict(orient="records")
                log.info("china score_log: last %d of %d rows -> ms_history",
                         len(_hist), len(_all))
        except Exception as _msh_e:  # noqa: BLE001 — additive, never fatal
            log.warning("china ms_history build failed (%s); skipping", _msh_e)
            vm.setdefault("ms_history", None)

        # ── MX5 tiles: enrich buy setups with name_zh + industry ─────────────
        # Spec §6.2: top-5 buy rows need name_zh (Chinese company name) and
        # industry (sub-industry or sector).  Enrich in-place using name_zh_by
        # built earlier in build_china_library.main() — if already on the row
        # (standouts pipeline may have passed it through), use it; else fall back
        # to the name field's " / ZH" half.  Never fatal.
        try:
            _su = vm.get("setups") or {}
            _buys = list((_su.get("buy") or []))
            for _row in _buys:
                if not isinstance(_row, dict):
                    continue
                # name_zh: prefer the row's own field; else split "EN / 中文"
                if not _row.get("name_zh"):
                    _nm = _row.get("name") or ""
                    _parts = _nm.split(" / ", 1)
                    _row["name_zh"] = _parts[1].strip() if len(_parts) > 1 else _parts[0].strip()
                # industry: prefer sub_industry; fall back to sector
                if not _row.get("industry"):
                    _row["industry"] = _row.get("sub_industry") or _row.get("sector") or ""
            vm["top_setups"] = _buys[:5]
        except Exception as _ts_e:  # noqa: BLE001 — additive, never fatal
            log.warning("china top_setups enrich failed (%s); skipping", _ts_e)
            vm["top_setups"] = []

        # ── MX5: china_brief card vm key ─────────────────────────────────────
        # Spec §6.6: dlg-aibrief needs master_brief.v2 content.  Load the
        # pre-existing site/china_brief.json produced by the AI brief pipeline.
        try:
            _brief_path = site / "china_brief.json"
            if _brief_path.exists():
                vm["china_brief"] = json.loads(_brief_path.read_text())
            else:
                vm["china_brief"] = None
                log.debug("china_brief.json not found; aibrief dialog will degrade")
        except Exception as _cb_e:  # noqa: BLE001 — additive, never fatal
            log.warning("china_brief load failed (%s); skipping", _cb_e)
            vm["china_brief"] = None

        # ── MX5: HSI market tile ──────────────────────────────────────────────
        # Spec §6.4: add HSI to vm['market_tiles'] (after building the base list).
        # USD/CNH and 10Y CGB stay in the list but will be displayed in
        # dlg-markets (not as glance tiles) — the template handles that split.
        # This just adds HSI so the 4 glance tiles are SSE/CSI300/ChiNext/HSI.
        try:
            _hsi_df = store.read("hk", "_HSI")
            if _hsi_df is not None and "close" in _hsi_df.columns:
                _hs = _hsi_df["close"].astype(float).dropna()
                if len(_hs) >= 2:
                    _hl, _hp = float(_hs.iloc[-1]), float(_hs.iloc[-2])
                    _hchg = _hl - _hp
                    _hpct = (_hl / _hp - 1) * 100 if _hp else 0.0
                    _htone = "pos" if _hchg > 0 else "neg" if _hchg < 0 else "muted"
                    vm["hsi_tile"] = {
                        "label": Markup('<span class="l-en">Hang Seng</span><span class="l-zh">恒生指数</span>'),
                        "tag": Markup('<span class="l-en">Hong Kong</span><span class="l-zh">港股</span>'),
                        "level": f"{_hl:,.0f}",
                        "chg": f"{_hchg:+.0f}",
                        "pct": f"{_hpct:+.1f}%",
                        "tone": _htone,
                        "sym": "^HSI",
                    }
        except Exception as _hsi_e:  # noqa: BLE001 — additive, never fatal
            log.warning("china hsi_tile failed (%s); skipping", _hsi_e)
            vm["hsi_tile"] = None
        vm.setdefault("hsi_tile", None)

        # Delayed-board disclosure input, hoisted to its own view-model key so it reaches BOTH
        # renders below. The macro page (china.html) is the surface
        # scripts/freshness_sentinel.py watches, and it does not render the setups board — so
        # reading setups.staleness inside the stocks-only block would leave china.html with no
        # marker and the sentinel's china delay budget with nothing to anchor on.
        # Recomputed directly when the library is missing or fell back to a persisted artifact:
        # a board serving yesterday's JSON is precisely when the disclosure must still be
        # honest, and compute_board_staleness reads the CSI300 anchor independently of it.
        try:
            from scripts import build_china_library as _bcl
            _stale = ((vm.get("setups") or {}).get("staleness")
                      or _bcl.compute_board_staleness())
        except Exception as _stale_e:  # noqa: BLE001 — never break the page over a badge
            log.warning("china board staleness unavailable (%s); disclosure suppressed",
                        _stale_e)
            _stale = {"price_through": None, "age_days": None, "delayed": False}
        vm["board_staleness"] = _stale
        if _stale.get("delayed"):
            log.warning(
                "china board DELAYED — prices as of %s (%s days behind); "
                "rendering the delayed-board disclosure",
                _stale.get("price_through"), _stale.get("age_days"),
            )

        # ── Risk Radar dialog ctx (templates/_risk_radar_dlg.html.j2) ────────
        # Assembled LAST: it reads market_state, internals, index_health, the
        # chinastatedata JSONs, the calendar and top_setups, so every one of them
        # must already be on the vm. Display-only; absent-safe section by section.
        try:
            vm["radar_dlg"] = _radar_dlg_vm(vm, latest)
        except Exception as _rdlg_e:  # noqa: BLE001 — additive, never fatal
            log.warning("china radar_dlg ctx failed (%s); dialog renders core only", _rdlg_e)
            vm["radar_dlg"] = {}

        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t, t_pctile=i18n.t_pctile)
        # One shared view-model feeds BOTH the China macro-regime page and the
        # A-share Stock Dashboard — the same china.html.j2 is rendered twice with
        # a `mode` flag (macro / stocks) that selects which sections show. No data
        # is recomputed and the heavy page CSS lives in exactly one template.
        tmpl = env.get_template("china.html.j2")
        # DEV-ONLY: dump the fully-built view-model so scripts/render_china_fast.py can
        # re-render china.html / china_stocks.html in ~1s without re-running collectors +
        # engine. Env-gated (CHINA_VM_DUMP=1); never fires on the nightly/commit path.
        import os as _os
        if _os.environ.get("CHINA_VM_DUMP"):
            try:
                import pickle as _pkl
                _vm_cache = config.data_dir() / "_dev_china_vm.pkl"
                with open(_vm_cache, "wb") as _fh:
                    _pkl.dump(vm, _fh)
                log.info("CHINA_VM_DUMP: wrote %s", _vm_cache)
            except Exception as _e:  # noqa: BLE001 — dev-only, never fatal
                log.error("CHINA_VM_DUMP failed (%s)", _e)
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
        # log.exception, not log.error: this handler wraps the ENTIRE vm assembly +
        # both page renders, so a bare message ("'str object' has no attribute
        # 'get'", 2026-07-12 incident) localizes NOTHING — china.html/china_stocks
        # .html silently freeze while the lane reports success. The traceback is
        # the only way the next reader finds the crash site.
        log.exception("china page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
