"""Generate the static dashboard (site/index.html) from stored engine output.

Reads regime/latest.json, regime_history.parquet, run_status.json and the
parquet store — never refetches and never recomputes the classifier, so the
site builds even when every scraper is down.

Usage: python -m scripts.build_site
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.holdings import active_changes  # noqa: E402
from collectors.sponsors import flows_table  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_site")

QUAD_COLORS = {"Q1": "#2e9e4f", "Q2": "#d4a017", "Q3": "#d04545", "Q4": "#3f78d8"}
PLOT_LAYOUT = dict(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)", font={"size": 11},
    margin={"l": 45, "r": 15, "t": 10, "b": 30}, height=300,
    legend={"orientation": "h", "y": 1.08},
)


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False})


def chart_regime(f: pd.DataFrame, hist: pd.DataFrame, days: int = 730) -> str:
    two_y = f.index.max() - pd.Timedelta(days=days)
    spy = f.loc[two_y:, "SPY"].dropna()
    sub = hist.loc[two_y:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=spy.index, y=spy, name="SPY",
                             line={"color": "#d7dce3", "width": 1.3}))
    q = sub["quad"].dropna()
    if not q.empty:
        seg_id = (q != q.shift()).cumsum()
        for _, seg in q.groupby(seg_id):
            fig.add_vrect(x0=seg.index.min(), x1=seg.index.max(),
                          fillcolor=QUAD_COLORS.get(seg.iloc[0], "#888"),
                          opacity=0.16, line_width=0)
    fig.update_layout(**PLOT_LAYOUT, showlegend=False)
    return _html(fig)


def chart_axes(hist: pd.DataFrame, days: int = 730) -> str:
    two_y = hist.index.max() - pd.Timedelta(days=days)
    sub = hist.loc[two_y:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub.index, y=sub["growth_score"], name="growth",
                             line={"color": "#5fbf7f", "width": 1.2}))
    fig.add_trace(go.Scatter(x=sub.index, y=sub["inflation_score"], name="inflation",
                             line={"color": "#e07070", "width": 1.2}))
    fig.add_hline(y=0, line={"color": "#666", "width": 0.6})
    fig.update_layout(**PLOT_LAYOUT)
    fig.update_yaxes(range=[-1.05, 1.05])
    return _html(fig)


def chart_liquidity(f: pd.DataFrame) -> str:
    cfg = config.load()["engine"]["liquidity"]
    two_y = f.index.max() - pd.Timedelta(days=730)
    nl = f.loc[two_y:, "net_liquidity_bn"].dropna()
    roc = (f["net_liquidity_bn"] - f["net_liquidity_bn"].shift(cfg["roc_window_d"])).loc[two_y:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35],
                        vertical_spacing=0.06)
    fig.add_trace(go.Scatter(x=nl.index, y=nl, name="net liquidity",
                             line={"color": "#7aa7e0", "width": 1.3}), row=1, col=1)
    fig.add_trace(go.Bar(x=roc.index, y=roc, name="4w RoC",
                         marker={"color": ["#5fbf7f" if v >= 0 else "#e07070"
                                           for v in roc.fillna(0)]}), row=2, col=1)
    fig.add_hline(y=cfg["expanding_threshold_bn"], line={"color": "#5fbf7f", "width": 0.5,
                                                         "dash": "dot"}, row=2, col=1)
    fig.add_hline(y=cfg["contracting_threshold_bn"], line={"color": "#e07070", "width": 0.5,
                                                           "dash": "dot"}, row=2, col=1)
    layout = {**PLOT_LAYOUT, "height": 340}
    fig.update_layout(**layout, showlegend=False)
    return _html(fig)


def chart_credit_breadth(f: pd.DataFrame) -> str:
    two_y = f.index.max() - pd.Timedelta(days=730)
    oas = f.loc[two_y:, "hy_oas"].dropna()
    br = f.loc[two_y:, "pct_above_50"].dropna()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06)
    fig.add_trace(go.Scatter(x=oas.index, y=oas, name="HY OAS %",
                             line={"color": "#e0a030", "width": 1.2}), row=1, col=1)
    fig.add_trace(go.Scatter(x=br.index, y=br, name="% S&P500 > 50DMA",
                             line={"color": "#9b8de0", "width": 1.2}), row=2, col=1)
    layout = {**PLOT_LAYOUT, "height": 340}
    fig.update_layout(**layout)
    return _html(fig)


def positioning_rows(f: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []

    def pctile(s: pd.Series) -> str:
        s = s.dropna()
        if len(s) < 50:
            return "n/a"
        return f"{(s.rank(pct=True).iloc[-1] * 100):.0f}"

    cot_meta = {
        "cot_es_spx": ("S&P 500 futures speculators",
                       "Net bets of speculative futures traders on the S&P 500, as % of all open "
                       "contracts (CFTC weekly data). Deeply negative + low percentile = everyone's "
                       "already short — fuel for squeezes. Very high = crowded long."),
        "cot_ust10y": ("10-yr Treasury futures speculators",
                       "Speculators' net position in 10-year Treasury futures. Extreme shorts have "
                       "historically preceded falling yields (bond rallies), and vice versa."),
        "cot_dollar": ("US Dollar futures speculators",
                       "Speculators' net position on the dollar index. Extremes tend to mark dollar "
                       "turning points, which matter for commodities and foreign earnings."),
        "cot_gold": ("Gold futures speculators",
                     "Speculators' net position in gold futures. Near the 100th percentile = the "
                     "most crowded gold trade in decades — vulnerable to shakeouts."),
    }
    for key, (label, tip) in cot_meta.items():
        df = store.read("cot", key)
        if df is not None and "net_spec_pct_oi" in df.columns and len(df):
            s = df["net_spec_pct_oi"]
            rows.append({"name": label, "tip": tip, "value": f"{s.iloc[-1]:+.1f}%",
                         "pctile": pctile(s), "asof": str(df.index.max().date())})
    naaim = store.read("sentiment", "naaim")
    if naaim is not None and len(naaim):
        s = naaim.iloc[:, 0]
        rows.append({"name": "Active managers' equity exposure",
                     "tip": "NAAIM weekly survey: how invested professional active managers are "
                            "(0 = all cash, 100 = fully invested, >100 = leveraged). Extremes are "
                            "contrarian: >95th percentile = managers all-in.",
                     "value": f"{s.iloc[-1]:.0f}",
                     "pctile": pctile(s), "asof": str(naaim.index.max().date())})
    pc = store.read("cboe", "putcall")
    if pc is not None and len(pc):
        for col, label, tip in [
            ("index_pc_ratio", "S&P index put/call ratio",
             "Volume of bearish (put) vs bullish (call) S&P index options traded today, computed "
             "from CBOE's chain. Above ~1.2 = heavy hedging/fear; below ~0.8 = complacency. "
             "History builds from June 2026, so the percentile matures over time."),
            ("equity_pc_ratio", "Stock-ETF put/call ratio",
             "Same idea using SPY+QQQ+IWM options — closer to what retail and fast money are doing."),
        ]:
            if col in pc.columns:
                s = pc[col]
                rows.append({"name": label, "tip": tip, "value": f"{s.iloc[-1]:.2f}",
                             "pctile": pctile(s), "asof": str(pc.index.max().date())})
    gex = store.read("cboe", "gex")
    if gex is not None and len(gex):
        g = gex.iloc[-1]
        flip = (f"{g['spot_vs_flip_pct']:+.1f}% from flip"
                if pd.notna(g.get("spot_vs_flip_pct")) else "no near flip")
        rows.append({"name": "Options dealers' stabilizer (GEX)",
                     "tip": "Estimated dealer gamma exposure, computed from the S&P options chain "
                            "under the standard assumption (dealers long calls, short puts). "
                            "POSITIVE = dealers trade against moves, dampening swings. NEGATIVE = "
                            "their hedging amplifies moves — expect bigger, faster swings both ways. "
                            "An estimate, not ground truth.",
                     "value": f"{g['net_gex_bn']:+.0f}bn",
                     "pctile": flip, "asof": str(gex.index.max().date())})
    vr = f["vix_ratio"].dropna()
    if len(vr):
        rows.append({"name": "Fear now vs fear later (VIX ratio)",
                     "tip": "VIX (30-day expected volatility) divided by VIX3M (3-month). Below ~0.9 "
                            "= calm, normal. Near or above 1.0 = the market fears the immediate "
                            "future more than the distant one — the classic stress signature.",
                     "value": f"{vr.iloc[-1]:.3f}",
                     "pctile": pctile(vr), "asof": str(vr.index[-1].date())})
    return rows


COMPONENT_SHORT = {
    "copper_gold": "copper vs gold", "xly_xlp": "consumer confidence trade",
    "us2y_direction": "2-yr yield", "iwm_spy": "small caps",
    "cyclical_defensive": "cyclical sectors", "breadth_direction": "market breadth",
    "payrolls_trend": "payrolls", "indpro_trend": "industrial production",
    "breakeven_10y_direction": "10-yr inflation expectations",
    "breakeven_5y5y_direction": "long-run inflation expectations",
    "energy_rs": "energy sector", "oil_trend": "oil",
    "inflation_beta_basket": "inflation-winners basket",
    "tips_nominal_momentum": "TIPS spread",
}


def component_chips(latest: dict) -> tuple[list[str], list[str]]:
    def label(raw: str) -> str:
        axis, _, comp = raw.partition("_")
        return f"{'G' if axis == 'growth' else 'I'} · {COMPONENT_SHORT.get(comp, comp)}"
    return ([label(c) for c in latest.get("confirming", [])],
            [label(c) for c in latest.get("contradicting", [])])


def flip_plain_text(latest: dict) -> str:
    from engine.playbook import COMPONENT_PLAIN
    fc = latest.get("flip_condition") or {}
    if not fc.get("component"):
        return ("No single indicator is close to flipping — the regime call isn't "
                "hanging on one thread right now.")
    plain = COMPONENT_PLAIN.get(fc["component"], fc["component"])
    return (f"Watch {plain}: it's the {fc['axis']}-dial supporter closest to its cutoff "
            f"(signal strength {fc['z']} vs the ±{fc['threshold']} threshold). "
            f"If it fades, the {fc['axis']} dial — and possibly the regime — flips.")


INTERNALS_META = {
    "xly_xlp": ("Shoppers: wants vs needs", False,
                "Consumer-discretionary stocks vs consumer-staples stocks. Rising = people are "
                "buying TVs and vacations, not just groceries — confidence. Falling = belt-tightening."),
    "xlk_xlu": ("Tech vs utilities", False,
                "The market's boldest sector vs its sleepiest. Rising = growth appetite; "
                "falling = safety-seeking."),
    "hyg_lqd": ("Junk bonds vs quality bonds", False,
                "Risky-company bonds vs blue-chip bonds. Rising = credit investors relaxed; "
                "falling = they're getting picky — often an early warning."),
    "sphb_splv": ("Daring vs defensive stocks", False,
                  "The most volatile S&P stocks vs the calmest. The purest read on whether "
                  "fund managers are playing offense or defense."),
    "vix_ratio": ("Panic gauge (now vs later)", True,
                  "Near-term fear vs 3-month fear. Rising toward 1.0 = stress building right now; "
                  "comfortably below 0.9 = calm."),
    "copper_gold": ("Copper vs gold", False,
                    "The economist's metal vs the doomsday metal. Rising = bets on real economic "
                    "activity; falling = safety-seeking. Historically leads bond yields."),
}


def internals_rows(latest: dict) -> list[dict]:
    out = []
    for key, v in latest.get("pair_ratios", {}).items():
        meta = INTERNALS_META.get(key)
        if not meta:
            continue
        label, invert, tip = meta
        chg = v["chg_20d_pct"]
        good = (chg < 0) if invert else (chg > 0)
        verdict = {
            ("xly_xlp", True): "consumers confident", ("xly_xlp", False): "consumers cautious",
            ("xlk_xlu", True): "growth appetite", ("xlk_xlu", False): "safety-seeking",
            ("hyg_lqd", True): "credit relaxed", ("hyg_lqd", False): "credit getting picky",
            ("sphb_splv", True): "playing offense", ("sphb_splv", False): "playing defense",
            ("vix_ratio", True): "calm", ("vix_ratio", False): "near-term stress building",
            ("copper_gold", True): "growth optimism", ("copper_gold", False): "defensive bid",
        }.get((key, good), "")
        out.append({"label": label, "tip": tip, "chg": chg, "good": good,
                    "verdict": verdict})
    return out


STAGE_STYLE = {
    "improving": ("#2b3340", "#9fc0e8"), "leading": ("#1d3326", "#6fce8f"),
    "weakening": ("#38301a", "#d8b75a"), "lagging": ("#3a2020", "#e08080"),
}

HEAT_COLORS = {"70+": "#e07b30", "55-69": "#3f8f5f",
               "40-54": "#4a5160", "0-39": "#3a4860"}


def _compact_season(line: str | None) -> tuple[str, str]:
    """'Jun: -0.4% avg, up 46% of years (n=28)' -> ('-0.4% (46%)', full)"""
    if not line:
        return "—", "Not enough history for a seasonal read."
    try:
        avg = line.split(":")[1].split("avg")[0].strip()
        hit = line.split("up ")[1].split("%")[0]
        return f"{avg} ({hit}%)", line
    except (IndexError, ValueError):
        return line, line


def sector_rows(playbook: dict | None) -> list[dict]:
    if not playbook or not playbook.get("stages"):
        return []
    rows = sorted(playbook["stages"], key=lambda r: -r["heat"])
    for r in rows:
        bg, fg = STAGE_STYLE.get(r["stage"], ("#2a2f3a", "#d7dce3"))
        r["stage_color"], r["stage_fg"] = bg, fg
        r["heat_color"] = HEAT_COLORS.get(r["heat_band"], "#4a5160")
        parts = r.get("heat_parts", {})
        cal = r.get("heat_cal")
        cal_txt = (f" Historical reality-check for the {r['heat_band']} band: beat the "
                   f"index {cal['hit_pct']}% of the time over the next 3 months "
                   f"(avg {cal['avg_excess_pct']:+}%, n={cal['n']})." if cal else "")
        r["heat_tip"] = (f"Heat {r['heat']}/100 = regime fit {parts.get('regime')} "
                         f"+ tape {parts.get('tape')} + technicals {parts.get('technicals')} "
                         f"+ crowding {parts.get('crowding')}. {r['heat_label']}: "
                         f"{r['heat_note']}{cal_txt}")
        tech_bits = [f"RSI {r['tech_rsi14']:.0f}" if r.get("tech_rsi14") is not None else "RSI —",
                     ("✓" if r.get("tech_above200") else "✗") + "200d",
                     ("✓" if r.get("tech_above50") else "✗") + "50d"]
        r["tech_str"] = " · ".join(tech_bits)
        r["tech_ok"] = bool(r.get("tech_above200")) and bool(r.get("tech_above50"))
        r["season_str"], r["season_tip"] = _compact_season(r.get("season_this"))
        if r.get("trigger_gap_pct") is not None:
            r["trigger_str"] = f"+{r['trigger_gap_pct']}%"
            if r.get("trigger_progress_pct") is not None:
                r["trigger_str"] += f" ({r['trigger_progress_pct']:.0f}% there)"
        else:
            r["trigger_str"] = "—"
    return rows


def holdings_rows() -> list[dict]:
    cfg = config.load()["holdings"]
    out = []
    for fund in cfg["watchlist"]:
        ch = active_changes(fund)
        if ch is None or ch.empty:
            continue
        big = ch[ch["active_chg_pct"].abs() >= cfg["active_change_alert_pct"] / 2]
        for pos, row in big.dropna(subset=["active_chg_pct"]).iterrows():
            out.append({"fund": fund, "position": pos, "pct": row["active_chg_pct"],
                        "window": f"{row['window_start']}..{row['window_end']}"})
    return sorted(out, key=lambda r: -abs(r["pct"]))[:20]


def _fmt_money_mn(v: float) -> str:
    """$ millions -> human string: 1234 -> +$1.2B, -87 -> -$87M."""
    if pd.isna(v):
        return "—"
    sign = "+" if v >= 0 else "−"
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    return f"{sign}${a:.0f}M"


def flows_html_table() -> str | None:
    from engine.playbook import SECTOR_NAMES
    ft = flows_table()
    if ft is None or ft.dropna(how="all").empty:
        return None
    recent = ft.dropna(how="all").tail(10)
    recent.columns = [SECTOR_NAMES.get(c.replace("_flow_mn", ""),
                                       c.replace("_flow_mn", ""))
                      for c in recent.columns]
    rows = ["<table><tr><th class='l'>date</th>"
            + "".join(f"<th>{c}</th>" for c in recent.columns) + "</tr>"]
    for d, r in recent.iterrows():
        cells = "".join(
            f"<td class='{'pos' if v >= 0 else 'neg'}'>{_fmt_money_mn(v)}</td>"
            if pd.notna(v) else "<td>—</td>" for v in r)
        rows.append(f"<tr><td class='l muted'>{d.date()}</td>{cells}</tr>")
    rows.append("</table>")
    return "".join(rows)


def health_rows() -> list[dict]:
    sources = store.read_status().get("sources", {})
    return [{"name": k, "status": v.get("status", "?"), "rows": v.get("rows", 0),
             "last_date": v.get("last_date"), "error": (v.get("error") or "")[:90]}
            for k, v in sorted(sources.items())]


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    with open(config.data_dir() / "regime" / "latest.json") as fh:
        latest = json.load(fh)
    hist = pd.read_parquet(config.data_dir() / "regime" / "regime_history.parquet")
    hist.index = pd.to_datetime(hist.index)
    f = build_features()

    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    confirming, contradicting = component_chips(latest)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    import calendar
    html = env.get_template("dashboard.html.j2").render(
        latest=latest,
        pb=latest.get("playbook"),
        month_name=calendar.month_name[pd.Timestamp(latest["date"]).month],
        commodities=(latest.get("playbook") or {}).get("commodities", []),
        components_confirming=confirming,
        components_contradicting=contradicting,
        flip_plain=flip_plain_text(latest),
        internals=internals_rows(latest),
        sector_rows=sector_rows(latest.get("playbook")),
        generated_utc=generated,
        chart_liquidity=chart_liquidity(f),
        chart_credit_breadth=chart_credit_breadth(f),
        positioning=positioning_rows(f),
        holdings_changes=holdings_rows(),
        holdings_threshold=config.load()["holdings"]["active_change_alert_pct"],
        flows_html=flows_html_table(),
        health=health_rows(),
    )
    out = site / "index.html"
    out.write_text(html)
    log.info("wrote %s (%.0f KB)", out, out.stat().st_size / 1024)

    # --- history page: the longer-window charts + lifespan base rates ----------
    from engine.playbook import QUAD_SHORT, transition_stats
    trans = transition_stats(hist["quad"])
    lifespan_rows = []
    for q in ("Q1", "Q2", "Q3", "Q4"):
        nxt = trans["matrix"].get(q, {})
        nxt_str = ", ".join(f"{QUAD_SHORT.get(k, k)} {v:.0%}" for k, v in
                            sorted(nxt.items(), key=lambda kv: -kv[1])[:2]) or "—"
        lifespan_rows.append({"name": QUAD_SHORT[q],
                              "n": trans["n_by_quad"].get(q, "—"),
                              "median": trans["median_days"].get(q, "—"),
                              "next": nxt_str})
    hist_html = env.get_template("history.html.j2").render(
        latest=latest,
        generated_utc=generated,
        chart_regime=chart_regime(f, hist, days=1095),
        chart_axes=chart_axes(hist, days=1095),
        lifespan_rows=lifespan_rows,
    )
    out2 = site / "history.html"
    out2.write_text(hist_html)
    log.info("wrote %s (%.0f KB)", out2, out2.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
