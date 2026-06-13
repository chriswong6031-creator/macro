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


def _crowd_words(p: float, lo_word: str, hi_word: str,
                 lo_verdict: str, hi_verdict: str) -> tuple[str, str]:
    """Percentile -> (label, verdict) in plain language. The vocabulary differs
    per input (long/short, cash/all-in, calm/panic) but the shape is shared."""
    if p >= 95:
        return f"extreme {hi_word}", f"{hi_verdict} — most extreme in our records; contrarian alert"
    if p >= 85:
        return f"crowded {hi_word}", f"{hi_verdict} — crowded; late to join"
    if p >= 60:
        return f"leaning {hi_word}", "above normal, nothing extreme"
    if p > 40:
        return "normal", "nothing notable"
    if p > 15:
        return f"leaning {lo_word}", "below normal, nothing extreme"
    if p > 5:
        return f"crowded {lo_word}", f"{lo_verdict} — stretched; squeezes start here"
    return f"extreme {lo_word}", f"{lo_verdict} — most extreme in our records; reversal fuel"


def positioning_rows(f: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []

    def pctile(s: pd.Series) -> float | None:
        s = s.dropna()
        if len(s) < 50:
            return None
        return float(s.rank(pct=True).iloc[-1] * 100)

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
            p = pctile(s)
            word, verdict = _crowd_words(p, "short", "long",
                                         "everyone is already short",
                                         "everyone is already long") if p is not None \
                else ("history building", "")
            rows.append({"name": label, "pct": p, "label": word, "verdict": verdict,
                         "left": "crowded short", "right": "crowded long",
                         "tip": tip + f" Today: {s.iloc[-1]:+.1f}% of open contracts"
                                + (f", {p:.0f}th percentile of 30 years" if p is not None else "")
                                + f" (as of {df.index.max().date()}, 3-day reporting lag).",
                         })
    naaim = store.read("sentiment", "naaim")
    if naaim is not None and len(naaim):
        s = naaim.iloc[:, 0]
        p = pctile(s)
        word, verdict = _crowd_words(p, "cautious", "invested",
                                     "managers are hiding in cash",
                                     "managers are nearly all-in") if p is not None \
            else ("history building", "")
        rows.append({"name": "Pro fund managers", "pct": p, "label": word, "verdict": verdict,
                     "left": "all cash", "right": "all-in",
                     "tip": "NAAIM weekly survey of professional active managers' stock exposure "
                            "(0 = all cash, 100 = fully invested, >100 = leveraged). Extremes are "
                            f"contrarian. Today: {s.iloc[-1]:.0f}"
                            + (f", {p:.0f}th percentile since 2006" if p is not None else "")
                            + f" (as of {naaim.index.max().date()}).",
                     })
    pc = store.read("cboe", "putcall")
    if pc is not None and len(pc) and "index_pc_ratio" in pc.columns:
        v = float(pc["index_pc_ratio"].iloc[-1])
        if v >= 1.3:
            word, verdict = "heavy hedging", "lots of downside protection being bought — fear elevated"
        elif v >= 1.0:
            word, verdict = "guarded", "more puts than calls — mild caution"
        elif v >= 0.8:
            word, verdict = "balanced", "nothing notable"
        else:
            word, verdict = "complacent", "very few hedges — markets unprepared for bad news"
        rows.append({"name": "Options hedging mood", "pct": None, "label": word,
                     "verdict": verdict, "left": "", "right": "",
                     "tip": "Put/call volume ratio on S&P index options, computed from CBOE's "
                            "chain: bearish bets ÷ bullish bets traded today. Above ~1.3 = heavy "
                            f"hedging; below ~0.8 = complacency. Today: {v:.2f} "
                            f"(as of {pc.index.max().date()}). A young series — labels are based "
                            "on standard thresholds until enough history accrues.",
                     })
    gex = store.read("cboe", "gex")
    if gex is not None and len(gex):
        g = gex.iloc[-1]
        pos = g["net_gex_bn"] > 0
        near = pd.notna(g.get("spot_vs_flip_pct")) and abs(g["spot_vs_flip_pct"]) < 2
        word = "dampening swings" if pos else "amplifying swings"
        verdict = ("market-makers' hedging absorbs moves — calmer tape likely" if pos else
                   "market-makers' hedging adds fuel to moves — expect bigger swings both ways")
        if near:
            verdict += " (and we're near the tipping point — it can flip any day)"
        rows.append({"name": "Market-maker effect", "pct": None, "label": word,
                     "verdict": verdict, "left": "", "right": "",
                     "tip": "Estimated dealer gamma (GEX) from the S&P options chain, standard "
                            "assumption (dealers long calls/short puts). Positive = their hedging "
                            "dampens market moves; negative = it amplifies them. Today: "
                            f"{g['net_gex_bn']:+.0f}bn per 1% move "
                            f"(as of {gex.index.max().date()}). An estimate, not ground truth.",
                     })
    vr = f["vix_ratio"].dropna()
    if len(vr):
        p = pctile(vr)
        if p is not None:
            word, verdict = _crowd_words(p, "calm", "stressed",
                                         "unusually calm conditions",
                                         "near-term fear is spiking")
            rows.append({"name": "Fear gauge", "pct": p, "label": word, "verdict": verdict,
                         "left": "calm", "right": "panic",
                         "tip": "VIX (30-day expected volatility) ÷ VIX3M (3-month). Below ~0.9 = "
                                "calm; near/above 1.0 = the market fears the immediate future more "
                                f"than the distant one — the classic stress signature. Today: "
                                f"{vr.iloc[-1]:.3f}, {p:.0f}th percentile since 2006.",
                         })
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
        return f"{'growth' if axis == 'growth' else 'inflation'} · {COMPONENT_SHORT.get(comp, comp)}"
    return ([label(c) for c in latest.get("confirming", [])],
            [label(c) for c in latest.get("contradicting", [])])


def flip_plain_text(latest: dict) -> str:
    from engine.playbook import COMPONENT_PLAIN
    fc = latest.get("flip_condition") or {}
    if not fc.get("component"):
        return ("No single indicator is close to flipping — the regime call isn't "
                "hanging on one thread right now.")
    plain = COMPONENT_PLAIN.get(fc["component"], fc["component"])
    return (f"Watch {plain} — of everything supporting the current call, it's the one "
            f"closest to flipping sides. If it fades, the {fc['axis']} dial (and "
            f"possibly the regime) goes with it.")


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


def sector_rows(playbook: dict | None, timing: dict | None = None) -> list[dict]:
    if not playbook or not playbook.get("stages"):
        return []
    timing = timing or {}
    rows = sorted(playbook["stages"], key=lambda r: -r["heat"])
    for r in rows:
        tm = timing.get(r["ticker"])
        if tm:
            r["timing_state"] = tm["state"]
            r["timing_style"] = tm["state_style"]
            r["timing_note"] = (f"day {tm['dc_day']} of its cycle; "
                                f"{tm['buy_zone']}/{tm['n_holdings']} top holdings in a buy state")
        else:
            r["timing_state"] = None
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


STATE_STYLES = {
    "FRESH BUY": ("#1d4a2c", "#7fe0a0"), "TURN SIGNALED": ("#1d3a4a", "#8fd0f0"),
    "RALLY ON": ("#1d3326", "#6fce8f"), "BOTTOM WATCH": ("#2b3340", "#9fc0e8"),
    "TOP WATCH": ("#38301a", "#d8b75a"), "ROLLING OVER": ("#4a2c1a", "#e0a070"),
    "DECLINE": ("#3a2020", "#e08080"),
}
BUY_ZONE_STATES = ("FRESH BUY", "TURN SIGNALED")


def build_sector_pages(env: Environment, site: Path, generated: str) -> dict:
    """Render sectors/<FUND>.html drill-downs; return per-fund timing summary
    for the heat board."""
    import json as _json

    from collectors.sector_holdings import latest_fundamentals, latest_top10
    from engine.cycles import LADDER, analyze
    from engine.playbook import SECTOR_NAMES

    cal_path = config.data_dir() / "regime" / "ladder_calibration.json"
    calibration = _json.loads(cal_path.read_text()) if cal_path.exists() else None
    tpl = env.get_template("sector.html.j2")
    outdir = site / "sectors"
    outdir.mkdir(parents=True, exist_ok=True)

    summaries: dict[str, dict] = {}
    for fund in config.load()["sponsors"]["sector_funds"]:
        etf = store.read("yahoo", fund)
        if etf is None:
            continue
        res = analyze(etf["close"])
        if not res.get("ladder"):
            continue
        holdings = []
        t10 = latest_top10(fund)
        if t10 is not None:
            for _, r in t10.iterrows():
                tick = str(r["ticker"]).replace(".", "-")
                df = store.read("stocks", tick)
                if df is None or len(df) < 300:
                    continue
                h = analyze(df["close"], df.get("high"))
                if not h.get("ladder"):
                    continue
                holdings.append({"ticker": tick,
                                 "name": str(r.get("name", "")).title(),
                                 "weight_pct": r["weight_pct"], **h,
                                 "fundamentals": latest_fundamentals(tick)})
        buy_zone = sum(1 for h in holdings if h["ladder"]["state"] in BUY_ZONE_STATES)
        s = {"fund": fund, "name": SECTOR_NAMES.get(fund, fund), **res,
             "holdings": holdings}
        html = tpl.render(s=s, state_styles=STATE_STYLES, calibration=calibration,
                          ladder_order=LADDER, generated_utc=generated)
        (outdir / f"{fund}.html").write_text(html)
        summaries[fund] = {"state": res["ladder"]["state"],
                           "state_style": STATE_STYLES.get(res["ladder"]["state"]),
                           "dc_day": res["cycle"]["dc_day"],
                           "buy_zone": buy_zone, "n_holdings": len(holdings)}
    log.info("wrote %d sector drill-down pages", len(summaries))
    return summaries


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
    sector_timing = {}
    try:
        sector_timing = build_sector_pages(env, site, generated)
    except Exception as e:  # noqa: BLE001 — drill-downs are additive, never fatal
        log.error("sector pages failed: %s", e)
    html = env.get_template("dashboard.html.j2").render(
        latest=latest,
        pb=latest.get("playbook"),
        month_name=calendar.month_name[pd.Timestamp(latest["date"]).month],
        commodities=(latest.get("playbook") or {}).get("commodities", []),
        sector_timing=sector_timing,
        components_confirming=confirming,
        components_contradicting=contradicting,
        flip_plain=flip_plain_text(latest),
        internals=internals_rows(latest),
        sector_rows=sector_rows(latest.get("playbook"), sector_timing),
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
