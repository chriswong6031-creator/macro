"""Build the Bitcoin Vector dashboard -> site/vector.html.

FULLY INDEPENDENT of the macro build_site.py (different theme, templates, data) —
the two pipelines share only the parquet store. Reads data/vector/signals.parquet
+ calibration.json (never recomputes the engine) plus raw inputs for the
cross-asset card, builds a view-model, renders Plotly charts (light theme), and
fills templates/vector.html.j2.

Usage: python -m scripts.build_vector
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
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_vector")

# Glassnode/Swissblock light palette (extracted from their CSS, VECTOR_SKELETON.md)
C = {
    "blue": "#285FFF", "indigo": "#4559DC", "blue_dk": "#1F5EFF",
    "r1": "#E2E7FC", "r2": "#B8C6FA", "r3": "#8FA5F6", "r4": "#6888FB", "r5": "#285FFF",
    "ink": "#0B1733", "text": "#344054", "muted": "#6F6F6F", "faint": "#A0A0A0",
    "red": "#D30B0B", "redfill": "#FEB5B5", "amber": "#F5AD42",
    "grid": "#EAECF0", "card": "#FFFFFF", "bg": "#F7F8FA", "priceln": "#9AA4B2",
}
PLOT = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"size": 11, "color": C["text"], "family": "Inter, sans-serif"},
    margin={"l": 48, "r": 52, "t": 8, "b": 28},
    legend={"orientation": "h", "y": 1.1, "x": 0},
    xaxis={"gridcolor": C["grid"], "zeroline": False},
    yaxis={"gridcolor": C["grid"], "zeroline": False},
)


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


def _tail(obj, days: int):
    """Last `days` of a Series/DataFrame by index (pandas 2.2 dropped .last())."""
    cutoff = obj.index.max() - pd.Timedelta(days=days)
    return obj.loc[obj.index >= cutoff]


# --------------------------------------------------------------------------- #
# view-model computations
# --------------------------------------------------------------------------- #
def alloc_equity(close: pd.Series, alloc: pd.Series) -> pd.Series:
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)
    return (1 + pos * ret).cumprod()


def scorecard(close: pd.Series, alloc: pd.Series) -> dict:
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)
    strat = pos * ret
    yrs = (close.index[-1] - close.index[0]).days / 365.25
    eq = (1 + strat).cumprod()
    hodl = (1 + ret).cumprod()

    def cagr(e):
        return (e.iloc[-1]) ** (1 / yrs) - 1 if yrs and e.iloc[-1] > 0 else float("nan")

    def shp(r):
        return r.mean() / r.std() * np.sqrt(365) if r.std() else float("nan")

    def srt(r):
        dn = r[r < 0].std()
        return r.mean() / dn * np.sqrt(365) if dn else float("nan")

    def mdd(e):
        return float((e / e.cummax() - 1).min())
    return {
        "cagr": round(100 * cagr(eq)), "sharpe": round(shp(strat), 2),
        "sortino": round(srt(strat), 2), "maxdd": round(100 * mdd(eq)),
        "in_market": round(100 * (pos > 0).mean()),
        "hodl_cagr": round(100 * cagr(hodl)), "hodl_sharpe": round(shp(ret), 2),
        "hodl_maxdd": round(100 * mdd(hodl)), "x_hodl": round(eq.iloc[-1] / hodl.iloc[-1], 2),
    }


def env_probabilities(state: pd.Series, horizon: int = 7) -> dict:
    """Empirical P(bull in `horizon` days | today's state) base rates."""
    s = state.dropna()
    binary = (s == "bull").astype(int)
    fut = binary.shift(-horizon)
    out = {}
    for st in ("bull", "bear", "neutral"):
        m = (s == st) & fut.notna()
        out[st] = round(100 * fut[m].mean()) if m.sum() > 20 else None
    now = s.iloc[-1]
    p_bull = out.get(now)
    return {"now": now, "p_bull_7d": p_bull,
            "p_bear_7d": (100 - p_bull) if p_bull is not None else None}


def scenarios_3d(close: pd.Series, high: pd.Series, low: pd.Series, state: str) -> dict:
    """Mechanical 3-day scenarios: ATR-band targets + recent swing levels +
    invalidation (Hawkeye/SEM idea). No look-ahead, no LLM prose."""
    tr = pd.concat([(high - low), (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    px = close.iloc[-1]
    swing_hi = high.rolling(20).max().iloc[-1]
    swing_lo = low.rolling(20).min().iloc[-1]
    base_bull = 60 if state == "bull" else (40 if state == "neutral" else 25)
    return {
        "bull_prob": base_bull, "bear_prob": 100 - base_bull,
        "bull_target": px + 1.5 * atr, "bull_target2": max(swing_hi, px + 2.5 * atr),
        "bull_invalid": px - 1.0 * atr,
        "bear_target": px - 1.5 * atr, "bear_target2": min(swing_lo, px - 2.5 * atr),
        "bear_invalid": px + 1.0 * atr,
    }


def cross_asset(sig_close: pd.Series) -> list[dict]:
    """Trend (3d) chip + conviction (1-3) per asset across index/commodities/
    crypto. Reads the shared macro parquet store (free)."""
    groups = [
        ("Index", [("S&P 500", "yahoo", "SPY"), ("Nasdaq", "yahoo", "QQQ"),
                   ("Dow Jones", "yahoo", "_DJI"), ("DXY", "yahoo", "DX-Y.NYB")]),
        ("Commodities", [("Gold", "yahoo", "GC_F"), ("Silver", "yahoo", "SI_F"),
                         ("Brent Oil", "yahoo", "BZ_F")]),
        ("Crypto", [("BTC", None, None), ("ETH", "yahoo", "ETH-USD"),
                    ("SOL", "yahoo", "SOL-USD")]),
    ]
    out = []
    for gname, assets in groups:
        rows = []
        for label, grp, name in assets:
            s = sig_close if grp is None else _series(grp, name)
            if s is None or len(s) < 30:
                rows.append({"label": label, "trend": "—", "conv": 0})
                continue
            r3 = s.pct_change(3).iloc[-1]
            r10 = s.pct_change(10).iloc[-1]
            trend = "Bull" if r3 > 0 else "Bear"
            # conviction: agreement of 3d & 10d direction + magnitude vs 30d vol
            vol = s.pct_change().rolling(30).std().iloc[-1] or 0.01
            mag = abs(r3) / (vol * np.sqrt(3))
            conv = 1 + int(np.sign(r3) == np.sign(r10)) + int(mag > 1.0)
            rows.append({"label": label, "trend": trend, "conv": min(conv, 3)})
        out.append({"group": gname, "rows": rows})
    return out


def _series(group: str, name: str) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[-1]
    s = df[col] if "close" in df.columns else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_risk_vs_strategy(df: pd.DataFrame, eq: pd.Series, hodl: pd.Series,
                           days: int = 730) -> str:
    d = _tail(df, days)
    eq, hodl = eq.reindex(d.index), hodl.reindex(d.index)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.28, 0.22],
                        vertical_spacing=0.04)
    fig.add_trace(go.Scatter(x=d.index, y=d["close"], name="BTC Price",
                             line={"color": C["priceln"], "width": 1.4}), row=1, col=1)
    # strategy equity rescaled to price axis for visual overlay
    scale = d["close"].iloc[0] / eq.iloc[0]
    fig.add_trace(go.Scatter(x=eq.index, y=eq * scale, name="Optimal strategy",
                             line={"color": C["blue"], "width": 1.8}), row=1, col=1)
    # risk index two-tone (split at threshold 25)
    ri = d["risk_index"]
    fig.add_trace(go.Scatter(x=ri.index, y=ri.where(ri < 25), name="Risk (low)",
                             line={"color": C["blue"], "width": 1.5}, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=ri.index, y=ri.where(ri >= 25), name="Risk (high)",
                             line={"color": C["red"], "width": 1.5}, showlegend=False), row=2, col=1)
    fig.add_hline(y=25, line={"color": C["faint"], "width": 1, "dash": "dot"}, row=2, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["alloc_optimal"], name="Allocation",
                             line={"color": C["indigo"], "width": 1.2, "shape": "hv"},
                             fill="tozeroy", fillcolor="rgba(40,95,255,0.10)",
                             showlegend=False), row=3, col=1)
    fig.update_yaxes(title_text="Price $", row=1, col=1)
    fig.update_yaxes(title_text="Risk", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="Alloc", range=[-0.05, 1.05], row=3, col=1)
    fig.update_layout(**{**PLOT, "height": 460})
    return _html(fig)


def chart_oscillator(s: pd.Series, close: pd.Series, name: str, days: int = 365) -> str:
    s, close = _tail(s, days), _tail(close, days)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=close.index, y=close, name="BTC",
                             line={"color": C["priceln"], "width": 1}, opacity=0.5),
                  secondary_y=True)
    fig.add_trace(go.Scatter(x=s.index, y=s.where(s >= 0), name=name,
                             line={"color": C["blue"], "width": 1.6}), secondary_y=False)
    fig.add_trace(go.Scatter(x=s.index, y=s.where(s < 0), name=name + " (neg)",
                             line={"color": C["red"], "width": 1.6}, showlegend=False),
                  secondary_y=False)
    for y in (0.5, -0.5):
        fig.add_hline(y=y, line={"color": C["faint"], "width": 1, "dash": "dot"})
    fig.update_yaxes(range=[-1.05, 1.05], secondary_y=False)
    fig.update_yaxes(showgrid=False, secondary_y=True)
    fig.update_layout(**{**PLOT, "height": 240})
    return _html(fig)


def chart_bfi(df: pd.DataFrame, days: int = 365) -> str:
    d = _tail(df, days)
    fig = go.Figure()
    for col, color, nm in [("network_growth", C["r3"], "Network Growth"),
                           ("liquidity", C["amber"], "Liquidity"),
                           ("bfi", C["blue"], "BFI")]:
        if col in d:
            fig.add_trace(go.Scatter(x=d.index, y=d[col], name=nm,
                                     line={"color": color, "width": 1.6 if col == "bfi" else 1.2}))
    fig.add_hrect(y0=40, y1=60, fillcolor=C["grid"], opacity=0.5, line_width=0)
    fig.update_yaxes(range=[0, 100])
    fig.update_layout(**{**PLOT, "height": 240})
    return _html(fig)


# --------------------------------------------------------------------------- #
# landing hub + macro relocation (post-processes the macro build's output;
# never edits the parallel-owned build_site.py / macro templates)
# --------------------------------------------------------------------------- #
HUB_MARKER = "<!-- bitcoin-vector-landing-hub -->"
MACRO_TITLE_HINT = "Macro Regime Dashboard"
VECTOR_NAV = ('<a class="navbtn" href="index.html">🏠 Home</a>\n      '
              '<a class="navbtn" href="vector.html">₿ Bitcoin Vector</a>\n      ')


def build_landing(site: Path, vm: dict) -> None:
    """Relocate the macro dashboard to macro.html and install the hub at
    index.html. Idempotent: safe to run every build, after build_site.py."""
    idx = site / "index.html"
    if idx.exists() and HUB_MARKER not in idx.read_text() and MACRO_TITLE_HINT in idx.read_text()[:4000]:
        macro_html = idx.read_text()
        # add a Bitcoin Vector entry to the macro nav (before the first navbtn)
        if 'href="vector.html"' not in macro_html and '<a class="navbtn"' in macro_html:
            macro_html = macro_html.replace('<a class="navbtn"', VECTOR_NAV + '<a class="navbtn"', 1)
        (site / "macro.html").write_text(macro_html)
        log.info("relocated macro dashboard -> macro.html")

    macro = _macro_state()
    hub = _hub_html(vm, macro)
    idx.write_text(hub)
    log.info("wrote landing hub -> index.html")


def _macro_state() -> dict:
    try:
        d = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        # plain-English regime name only — never the Q-code (macro D28: a user
        # misread "Q1" as calendar Q1)
        return {"label": d.get("quad_name", "—"), "date": d.get("date", "")}
    except Exception:
        return {"label": "—", "date": ""}


def _hub_html(vm: dict, macro: dict) -> str:
    risk_cls = "on" if vm["risk_on"] else "off"
    return f"""{HUB_MARKER}
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Intelligence</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;background:{C['bg']};color:{C['text']};
 font-family:Inter,sans-serif;display:flex;flex-direction:column;align-items:center;
 justify-content:center;padding:40px 20px}}
.h{{text-align:center;margin-bottom:40px}}
.h h1{{font-size:40px;font-weight:800;color:{C['ink']};letter-spacing:-.03em;margin:0 0 8px}}
.h p{{color:{C['muted']};font-size:17px;margin:0}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:24px;width:100%;max-width:860px}}
@media(max-width:720px){{.cards{{grid-template-columns:1fr}}}}
.c{{background:#fff;border:1px solid {C['grid']};border-radius:20px;padding:30px;
 text-decoration:none;color:inherit;transition:transform .15s,box-shadow .15s;display:block}}
.c:hover{{transform:translateY(-3px);box-shadow:0 12px 30px rgba(16,24,64,.10);border-color:{C['r2']}}}
.c .ico{{font-size:30px}}
.c h2{{font-size:23px;font-weight:800;color:{C['ink']};margin:14px 0 6px;letter-spacing:-.02em}}
.c p{{color:{C['muted']};font-size:14px;margin:0 0 18px;min-height:40px}}
.stat{{display:inline-block;padding:6px 12px;border-radius:9px;background:{C['bg']};
 font-weight:700;font-size:13px;margin-right:8px}}
.stat.on{{background:#E8EEFF;color:{C['blue']}}} .stat.off{{background:#FDEBEB;color:{C['red']}}}
.go{{margin-top:18px;font-weight:700;color:{C['blue']};font-size:14px}}
.foot{{margin-top:40px;color:{C['faint']};font-size:12px;text-align:center}}
</style></head><body>
<div class="h"><h1>Market Intelligence</h1>
<p>Two dashboards, one zero-cost data engine.</p></div>
<div class="cards">
  <a class="c" href="macro.html">
    <div class="ico">\U0001F30D</div>
    <h2>Macro Dashboard</h2>
    <p>Regime, liquidity &amp; sector-flow read across the global business cycle.</p>
    <span class="stat">{macro['label']}</span>
    <div class="go">Open Macro Dashboard →</div>
  </a>
  <a class="c" href="vector.html">
    <div class="ico">₿</div>
    <h2>Bitcoin Vector</h2>
    <p>Risk regime, momentum, structure &amp; backtested allocation for Bitcoin.</p>
    <span class="stat {risk_cls}">Risk {vm['risk_word']} · {vm['risk_index']}</span>
    <span class="stat">Momentum {vm['momentum']}</span>
    <div class="go">Open Bitcoin Vector →</div>
  </a>
</div>
<div class="foot">Built {vm['built']} · mechanical, backtested, free public data · not investment advice</div>
</body></html>"""


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def gauge_pos(value: float, lo: float, hi: float) -> float:
    return round(100 * min(max((value - lo) / (hi - lo), 0), 1), 1)


def main() -> int:
    # self-sufficient: recompute signals every build (daily freshness) and
    # persist them. The heavy calibration (verdicts/backtests in calibration.json)
    # is maintained separately by scripts.calibrate_vector (weekly); read it if
    # present, otherwise render without the verdict card.
    from engine import btc_signals
    try:
        sig = btc_signals.compute_all()
    except Exception as e:  # noqa: BLE001 — never break the macro site build
        log.error("vector signal engine failed (%s); skipping vector page", e)
        return 0
    sig.index = pd.to_datetime(sig.index)
    (config.data_dir() / "vector").mkdir(parents=True, exist_ok=True)
    sig.to_parquet(config.data_dir() / "vector" / "signals.parquet")

    cpath = config.data_dir() / "vector" / "calibration.json"
    calib = json.loads(cpath.read_text()) if cpath.exists() else {
        "meta": {"span": f"{sig.index.min().date()}..{sig.index.max().date()}"},
        "signals": {}, "risk_drawdown": {}}
    last = sig.iloc[-1]
    px = _series("coinbase", "btc_daily")
    close = sig["close"]
    chg24 = round(100 * (close.iloc[-1] / close.iloc[-2] - 1), 2)

    eq = alloc_equity(close, sig["alloc_optimal"])
    hodl = (1 + close.pct_change().fillna(0)).cumprod()
    cards = {v: scorecard(close, sig[f"alloc_{v}"])
             for v in ("conservative", "moderate", "aggressive", "optimal")}

    # raw OHLC for scenarios
    raw = store.read("coinbase", "btc_daily")
    hi = raw["high"].reindex(close.index).fillna(close)
    lo = raw["low"].reindex(close.index).fillna(close)

    risk_on = last["risk_regime"] == "low_risk"
    vm = {
        "as_of": sig.index.max().strftime("%b %d, %Y"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "price": close.iloc[-1], "chg24": chg24,
        "risk_on": risk_on,
        "risk_word": "ON" if risk_on else "OFF",
        "risk_index": round(last["risk_index"]),
        "risk_label": "Low Risk" if risk_on else "High Risk",
        "risk_osc": round(last["risk_oscillator"], 2),
        "momentum": round(last["momentum"], 2),
        "momentum_state": last["momentum_state"],
        "mom_strength": "Strong" if abs(last["momentum"]) > 0.5 else "Weak",
        "structure": round(last["structure"], 2), "structure_state": last["structure_state"],
        "vol_state": last["vol_state"], "vol_side": last["vol_side"],
        "flow_state": last["flow_state"],
        "bfi": round(last["bfi"]) if pd.notna(last.get("bfi")) else None,
        "bfi_zone": last.get("bfi_zone"),
        "network_growth": round(last["network_growth"]) if pd.notna(last.get("network_growth")) else None,
        "liquidity": round(last["liquidity"]) if pd.notna(last.get("liquidity")) else None,
        "cycle_pos": round(100 * last["cycle_position"]),
        "cycle_stage": ["Defensive", "Fragile", "Recovery", "Expansion"][
            min(int(last["cycle_position"] * 4), 3)],
        "alt_leader": last.get("alt_cycle_leader", "BTC"),
        "market_mode": last["market_mode"],
        "alloc_pct": round(100 * last["alloc_optimal"]),
        "gauges": {
            "momentum": gauge_pos(last["momentum"], -1, 1),
            "risk": last["risk_index"],
            "vol": round(100 * last["vol_pctile"]) if pd.notna(last["vol_pctile"]) else 50,
            "flow": round(100 * last["flow_pctile"]) if pd.notna(last["flow_pctile"]) else 50,
        },
        "env": env_probabilities(sig["momentum_state"]),
        "scn": scenarios_3d(close, hi, lo, last["momentum_state"]),
        "cards": cards,
        "cross": cross_asset(close),
        "calib": calib,
        "charts": {
            "risk_strategy": chart_risk_vs_strategy(sig, eq, hodl),
            "momentum": chart_oscillator(sig["momentum"], close, "Momentum"),
            "structure": chart_oscillator(sig["structure"], close, "Structure Shift"),
            "bfi": chart_bfi(sig),
        },
    }

    env = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates")),
                      autoescape=True)
    env.filters["money"] = lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
    env.filters["money1"] = lambda v: f"${v/1000:,.1f}K" if pd.notna(v) else "—"
    html = env.get_template("vector.html.j2").render(**vm, C=C)
    site = Path(config.load()["storage"]["site_dir"])
    (site / "vector.html").write_text(html)
    log.info("wrote %s/vector.html (%d KB)", site, len(html) // 1024)
    build_landing(site, vm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
