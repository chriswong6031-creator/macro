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


def _cond_up_prob(df: pd.DataFrame, cfg: dict, horizon: int):
    """P(up over `horizon`d) conditioned on momentum_state x risk_regime, shrunk
    toward the momentum marginal (empirical Bayes), nudged by the CONFIRMED macro
    regime, and CAPPED to [floor, ceil] — the anti-overfit discipline for ~3
    cycles (per the methodology research). Returns (prob, n_cell, cell, tilt_pp).
    Replaces the momentum-only base rate: a high-risk bull and a low-risk bull no
    longer get identical odds."""
    close = df["close"]
    fwd_up = (close.shift(-horizon) > close).astype(float)
    mom = df.get("momentum_state")
    if mom is None:
        return None, 0, None, 0
    valid = fwd_up.notna() & mom.notna()
    now_mom = mom.iloc[-1]
    mm = valid & (mom == now_mom)
    base = fwd_up[valid].mean()
    p_marg = fwd_up[mm].mean() if mm.sum() > cfg["prob_min_cell_n"] else base
    p, n, cell = p_marg, 0, str(now_mom)
    risk = df.get("risk_regime")
    if risk is not None and pd.notna(risk.iloc[-1]):
        now_risk = risk.iloc[-1]
        cm = valid & (mom == now_mom) & (risk == now_risk)
        n = int(cm.sum())
        a = cfg["prob_shrink_alpha"]
        p = (fwd_up[cm].sum() + a * p_marg) / (n + a) if n > 0 else p_marg
        cell = f"{now_mom} / {str(now_risk).replace('_risk', '')} risk"
        if n < cfg["prob_min_cell_n"]:
            p = p_marg               # cell too thin -> fall back to the marginal
    macro = df.get("macro_regime")
    tilt = 0.0
    if macro is not None and pd.notna(macro.iloc[-1]):
        t = cfg["macro_tilt_pp"] / 100.0
        tilt = t if macro.iloc[-1] == "tailwind" else (-t if macro.iloc[-1] == "headwind" else 0.0)
    # halving-cycle prior (orthogonal): accumulation phase tilts up, markdown down
    cyc = df.get("cycle_phase")
    if cyc is not None and pd.notna(cyc.iloc[-1]) and cfg.get("cycle_tilt_pp"):
        ct = cfg["cycle_tilt_pp"] / 100.0
        tilt += ct if cyc.iloc[-1] == "accumulation" else (-ct if cyc.iloc[-1] == "markdown" else 0.0)
    p = min(max(p + tilt, cfg["prob_floor"]), cfg["prob_ceil"])
    return float(p), n, cell, round(100 * tilt)


def env_probabilities(df: pd.DataFrame, cfg: dict) -> dict:
    """Mid-term P(up) conditioned on the full confirmed state (momentum x risk +
    macro tilt), not momentum alone. Carries honest n + cell label."""
    h = cfg["prob_horizon_d"]
    p, n, cell, tilt = _cond_up_prob(df, cfg, h)
    now = df["momentum_state"].iloc[-1] if "momentum_state" in df else None
    if p is None:
        return {"now": now, "p_bull_7d": None, "p_bear_7d": None}
    return {"now": now, "p_bull_7d": round(100 * p), "p_bear_7d": round(100 * (1 - p)),
            "n": n, "cell": cell, "tilt": tilt, "horizon": h}  # tilt = macro + cycle prior


def scenarios_3d(df: pd.DataFrame, cfg: dict, high: pd.Series, low: pd.Series) -> dict:
    """3-day scenarios: ATR-band targets SCALED by forward vol (DVOL), swing
    levels, invalidation; bull/bear probability from the SAME conditional model
    (momentum x risk + macro), horizon 3 — not a momentum-only lookup."""
    close = df["close"]
    tr = pd.concat([(high - low), (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    dvol = df.get("dvol")          # forward vol widens/narrows the 3d cones
    vscale = 1.0
    if dvol is not None and pd.notna(dvol.iloc[-1]):
        vscale = float(np.clip(dvol.iloc[-1] / cfg["atr_dvol_ref"], 0.6, 2.0))
    px = close.iloc[-1]
    swing_hi = high.rolling(20).max().iloc[-1]
    swing_lo = low.rolling(20).min().iloc[-1]
    p, n, cell, tilt = _cond_up_prob(df, cfg, 3)
    bull = round(100 * p) if p is not None else 50
    a1, a2, ai = 1.5 * vscale * atr, 2.5 * vscale * atr, 1.0 * atr
    return {
        "bull_prob": bull, "bear_prob": 100 - bull, "cell": cell, "n": n, "tilt": tilt,
        "vscale": round(vscale, 2),
        "bull_target": px + a1, "bull_target2": max(swing_hi, px + a2), "bull_invalid": px - ai,
        "bear_target": px - a1, "bear_target2": min(swing_lo, px - a2), "bear_invalid": px + ai,
    }


# --------------------------------------------------------------------------- #
# conviction layer: turn a capped/shrunk directional prob into an HONEST state
# (TOSS-UP / LEAN / EDGE). Calibrated to the MEASURED reliable-cell spread
# (51.9-57.1% up-rate at 7d across n>300 cells) so ~3pp from 50% reads as a
# coin-flip, NOT a confident call. The tape is an orthogonal 2nd vote that only
# demotes on conflict — it never manufactures edge. (D-vec-CONV; see DECISIONS.)
# --------------------------------------------------------------------------- #
def _tape_sign(mtf_rows: list[dict], keys: set) -> int:
    """Net technical-tape direction over the timeframes in `keys`: +1 up, -1 down,
    0 mixed/flat. mid horizon ~ {W,2W}; short horizon ~ {D,3D}."""
    s = 0
    for r in mtf_rows:
        if r.get("key") in keys:
            t = r.get("trend")
            s += 1 if t == "up" else (-1 if t == "down" else 0)
    return 0 if s == 0 else (1 if s > 0 else -1)


def _conviction(p_bull, n, tilt, tape_sign, verdict_sign, min_cell_n, bands=(3, 7)):
    """Map a directional probability to a conviction state. TOSS-UP (|p-50|<=3) =
    no edge / coin-flip; LEAN (<=7) = within the reliable cell spread, driver-backed;
    EDGE (>7) = beyond the reliable ceiling (tilt-to-cap only) and only when
    corroborated by the page verdict + a reliable cell + a non-conflicting tape.
    A thin cell (n<min_cell_n) can never print an EDGE. Returns a render-ready dict."""
    tilt = tilt or 0
    if p_bull is None:
        return {"state": "TOSS-UP", "dir": 0, "lean": 0, "conf": "thin", "n": n,
                "tape": "neutral", "confirmed": False, "p_bull": 50, "p_bear": 50, "tilt": tilt}
    lean = abs(p_bull - 50)
    prob_dir = 1 if p_bull > 50 else (-1 if p_bull < 50 else 0)
    toss_pp, edge_pp = bands
    # (1) sample-size gate -> confidence tier; a thin cell can never print an EDGE
    if n is None or n < min_cell_n:
        conf, forced_tossup = "thin", True
    elif n < 300:
        conf, forced_tossup = "moderate", False
    else:
        conf, forced_tossup = "reliable", False
    # (2) band on the directional distance from 50 (3-state, calibrated)
    if forced_tossup or lean <= toss_pp:
        state = "TOSS-UP"
    elif lean <= edge_pp:
        state = "LEAN"
    else:
        state = "EDGE"
    # (2b) a non-reliable cell (n<300) cannot honestly claim an EDGE-sized (>7pp) move —
    #      that is the overfit signature of a thin cell (e.g. bear/low_risk n=26 -> ~31%
    #      after shrinkage); the swing isn't real, so show NO edge, not a confident bear.
    if conf != "reliable" and lean > edge_pp:
        state = "TOSS-UP"
    # (3) technical tape = orthogonal 2nd vote: only modulates, never overrides
    tape, confirmed = "neutral", False
    if state != "TOSS-UP" and tape_sign != 0 and prob_dir != 0:
        if tape_sign == prob_dir:
            tape = "confirm"
            confirmed = bool(tilt) and ((tilt > 0) == (prob_dir > 0))
        else:
            tape, state = "conflict", "LEAN"     # demote EDGE->LEAN on tape conflict
    # (4) EDGE corroboration gate: needs verdict agreement + reliable cell + no conflict
    if state == "EDGE" and not (verdict_sign == prob_dir and tape != "conflict" and conf == "reliable"):
        state = "LEAN"
    return {"state": state, "dir": prob_dir, "lean": lean, "conf": conf, "n": n,
            "tape": tape, "confirmed": confirmed,
            "p_bull": p_bull, "p_bear": 100 - p_bull, "tilt": tilt}


def _conviction_why(c: dict, cell, n, horizon: int):
    """Honest one-liner (EN, ZH). TOSS-UP names the cell, odds, sample, and points
    to where the edge actually lives (the cycle, not the week)."""
    cell_txt = (cell or "this regime").replace(" / ", "-").replace(" risk", "")
    nfmt = f"{n:,}" if n else "—"
    pb, pl = c["p_bear"], c["p_bull"]
    near = "week" if horizon >= 7 else "next few days"
    near_zh = "本周" if horizon >= 7 else "未来几天"
    if c["state"] == "TOSS-UP":
        en = (f"{cell_txt}: {horizon}d direction ~{pb}/{pl} over {nfmt} samples — a coin-flip. "
              f"The edge is in the cycle, not the {near}.")
        zh = (f"{cell_txt}：{horizon} 天方向约 {pb}/{pl}，样本 {nfmt} — 接近抛硬币。"
              f"优势在周期，而非{near_zh}。")
        return en, zh
    dword, dword_zh = ("bull", "看多") if c["dir"] > 0 else ("bear", "看空")
    drv = f"{c['tilt']:+d}pp macro+cycle tilt" if c["tilt"] else "the cell base-rate"
    drv_zh = f"{c['tilt']:+d}pp 宏观+周期偏移" if c["tilt"] else "区间基准率"
    tf, tf_zh = ("weekly", "周线") if horizon >= 7 else ("daily", "日线")
    tape_en = (" Tape agrees." if c["tape"] == "confirm"
               else (f" But the {tf} tape disagrees — nimble only." if c["tape"] == "conflict" else ""))
    tape_zh = ("，盘面一致。" if c["tape"] == "confirm"
               else (f"，但{tf_zh}盘面相反 — 仅适合灵活交易。" if c["tape"] == "conflict" else "。"))
    en = f"{horizon}d lean {dword} — {nfmt} samples, {drv}.{tape_en}"
    zh = f"{horizon} 天倾向{dword_zh} — 样本 {nfmt}，{drv_zh}{tape_zh}"
    return en, zh


def cross_asset(sig_close: pd.Series) -> list[dict]:
    """Trend (3d) chip + conviction (1-3) per asset across index/commodities/
    crypto. Reads the shared macro parquet store (free)."""
    groups = [
        ("Index", [("S&P 500", "yahoo", "SPY"), ("Nasdaq", "yahoo", "QQQ"),
                   ("Russell 2000", "yahoo", "_RUT"), ("Dow Jones", "yahoo", "_DJI"),
                   ("DXY", "yahoo", "DX-Y.NYB")]),
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
# landing hub (owns site/index.html exclusively). build_site.py writes the macro
# dashboard straight to macro.html, so index.html is never the raw dashboard and
# Home (-> index.html) can't regress to it — even if this step is skipped, the
# committed hub stays in place.
# --------------------------------------------------------------------------- #
HUB_MARKER = "<!-- bitcoin-vector-landing-hub -->"


def build_landing(site: Path, vm: dict) -> None:
    """Install the landing hub at index.html. Idempotent: safe to run every
    build, independent of build_site.py ordering — the hub is rendered from the
    stored engine state, not from any HTML file build_site emits."""
    macro = _macro_state()
    hub = _hub_html(vm, macro, home_alert_feed(), _china_state(), _commodities_state(),
                    _watchlist_state(), _etf_state(), _hk_state(), _forex_state())
    (site / "index.html").write_text(hub)
    log.info("wrote landing hub -> index.html")


def _macro_state() -> dict:
    try:
        d = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        # plain-English regime name only — never the Q-code (macro D28: a user
        # misread "Q1" as calendar Q1)
        return {"label": d.get("quad_name", "—"), "date": d.get("date", "")}
    except Exception:
        return {"label": "—", "date": ""}


def _china_state() -> dict:
    """China A-share regime for the hub card (written by build_china, which runs
    before build_vector). `present` gates the card so the hub still works if the
    China page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "china_regime" / "latest.json").read_text())
        return {"label": d.get("quad_name", "—"), "date": d.get("date", ""),
                "present": (site / "china.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "present": (site / "china.html").exists()}


def _hk_state() -> dict:
    """Hong Kong / Hang Seng regime for the hub card (written by build_hk, which
    runs before build_vector). `present` gates the card so the hub still works if
    the HK page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "hk_regime" / "latest.json").read_text())
        return {"label": d.get("quad_name", "—"), "date": d.get("date", ""),
                "risk": d.get("risk_state", ""), "present": (site / "hk.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "risk": "", "present": (site / "hk.html").exists()}


def _commodities_state() -> dict:
    """Commodity-complex regime for the hub card (written by build_commodities,
    which runs before build_vector). `present` gates the card so the hub still
    works if the commodities page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "commodity" / "latest.json").read_text())
        return {"label": d.get("regime", "—"), "date": d.get("date", ""),
                "favored": d.get("favored", []),
                "present": (site / "commodities.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "favored": [],
                "present": (site / "commodities.html").exists()}


def _forex_state() -> dict:
    """Forex Vector dollar-smile regime for the hub card (written by build_forex,
    which runs before build_vector). `present` gates the card so the hub still works
    if the forex page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "forex" / "latest.json").read_text())
        return {"label": d.get("regime", "—"), "date": d.get("date", ""),
                "favored": d.get("favored", []), "risk": d.get("risk", ""),
                "present": (site / "forex.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "favored": [], "risk": "",
                "present": (site / "forex.html").exists()}


def _watchlist_state() -> dict:
    """The holdings watchlist is pure client state — no server-side signal — so
    the card is gated purely on the page having been built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    return {"present": (site / "watchlist.html").exists()}


def _etf_state() -> dict:
    """ETF flow radar card — gated purely on the page having been built this run
    (signals are share-flow decisions, no single regime label to show)."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    return {"present": (site / "etfs.html").exists()}


MACRO_SEV = {"act": "high", "warn": "medium", "info": "info"}


def home_alert_feed() -> list[dict]:
    """Normalize MAJOR alerts from both dashboards into one timeline for the hub.
    Macro feed = data/alerts/alerts_log.parquet (date-resolution); vector feed =
    data/vector/alerts.jsonl (timestamp-resolution). Both filtered to their
    'major' severity tiers (config home.alerts), merged newest-first, capped."""
    h = config.load()["home"]["alerts"]
    out: list[dict] = []
    try:
        from engine.i18n import tr as _tr
    except Exception:  # noqa: BLE001
        def _tr(en):
            return en

    # --- macro --- (config paths are repo-root-relative)
    mp = Path(config.ROOT) / h["macro_feed"]
    try:
        mdf = pd.read_parquet(mp)
        from engine.alerts import alert_view
        major = mdf[mdf["severity"].isin(h["macro_major_severities"])
                    & ~mdf["rule"].isin(h.get("macro_exclude_rules", []))]
        for _, r in major.iterrows():
            v = alert_view(r["rule"], r["severity"], r["message"])
            link = ("macro.html#" + v["anchor"]) if v["anchor"] else "macro.html"
            out.append({
                "source": "macro", "source_label": h["macro_label"],
                "source_label_zh": _tr(h["macro_label"]),
                "ts": pd.Timestamp(r["date"]).isoformat(), "date_only": True,
                "severity": MACRO_SEV.get(r["severity"], "info"),
                "type": r["rule"],
                "headline": v["icon"] + " " + v["plain_en"],
                "headline_zh": v["icon"] + " " + (v.get("plain_zh") or v["plain_en"]),
                # the macro alert LOG stores only the English message (no message_zh
                # column), so the numeric detail line falls back to English in zh mode
                "detail": r["message"], "detail_zh": r["message"],
                "what": v["what_en"], "what_zh": v.get("what_zh") or v["what_en"],
                "link": link, "tier": v["tier"],
                "edge": v["edge_en"], "edge_zh": v.get("edge_zh") or v["edge_en"],
                "cta": "Open scorecard →", "cta_zh": "打开记分卡 →",
                "dedupe": r["message"],
            })
    except Exception as e:  # noqa: BLE001
        log.warning("home feed: macro alerts unavailable (%s)", e)

    # --- vector ---
    try:
        from engine import btc_alerts
        for e in btc_alerts.load_events():
            if e["severity"] in h["vector_major_severities"]:
                out.append({
                    "source": "vector", "source_label": "Bitcoin Vector",
                    "source_label_zh": "比特币向量",
                    "ts": e["ts"], "date_only": False, "severity": e["severity"],
                    "type": e["type"],
                    "headline": e["headline"], "headline_zh": e.get("headline_zh") or e["headline"],
                    "detail": e["detail"], "detail_zh": e.get("detail_zh") or e["detail"],
                    "what": e.get("forward", ""), "what_zh": e.get("forward_zh", ""),
                    "tier": e.get("tier", "watch"),
                    "edge": e.get("edge", ""), "edge_zh": e.get("edge_zh", ""),
                    "link": "vector.html" + e.get("anchor", "#timeline"),
                    "cta": "Open →", "cta_zh": "打开 →", "dedupe": e["headline"],
                })
    except Exception as e:  # noqa: BLE001
        log.warning("home feed: vector alerts unavailable (%s)", e)

    # --- commodity ---
    try:
        from engine import commodity_alerts
        sevs = h.get("commodity_major_severities", ["high", "medium"])
        for e in commodity_alerts.load_events():
            if e["severity"] in sevs:
                out.append({
                    "source": "commodity", "source_label": "Commodity Vector",
                    "source_label_zh": "大宗商品向量",
                    "ts": e["ts"], "date_only": (pd.Timestamp(e["ts"]).hour == 0
                                                 and pd.Timestamp(e["ts"]).minute == 0),
                    "severity": e["severity"], "type": e["type"],
                    # commodity_alerts emits no zh headline/detail yet → English fallback
                    "headline": e["headline"], "headline_zh": e.get("headline_zh") or e["headline"],
                    "detail": e["detail"], "detail_zh": e.get("detail_zh") or e["detail"],
                    "what": e.get("forward", ""), "what_zh": e.get("forward_zh", ""),
                    "tier": e.get("tier", "watch"),
                    "edge": e.get("edge", ""), "edge_zh": e.get("edge_zh", ""),
                    "link": "commodities.html" + e.get("anchor", "#timeline"),
                    "cta": "Open →", "cta_zh": "打开 →", "dedupe": e["headline"],
                })
    except Exception as e:  # noqa: BLE001
        log.warning("home feed: commodity alerts unavailable (%s)", e)

    out.sort(key=lambda x: x["ts"], reverse=True)
    # collapse identical headlines that re-fire within the dedup window (keep newest)
    win = pd.Timedelta(days=h.get("dedup_window_days", 5))
    seen: dict[str, pd.Timestamp] = {}
    deduped = []
    for a in out:
        ts = pd.Timestamp(a["ts"])
        key = a.get("dedupe") or a["headline"]
        if key in seen and (seen[key] - ts) < win:
            continue
        seen[key] = ts
        deduped.append(a)
    return deduped[:h["max_items"]]


def _when_zh(ts: pd.Timestamp, date_only: bool) -> str:
    """Chinese sibling of the feed's `when` label (`6月12日` / `6月12日 · 15:00 UTC`)."""
    base = f"{ts.month}月{ts.day}日"
    return base if date_only else f"{base} · {ts.strftime('%H:%M')} UTC"


def _hub_alert_rows(alerts: list[dict]) -> str:
    # Emit each text bilingually (dual <span class="l-en/l-zh">); theme.css shows the
    # one matching the active data-lang. Each source supplies whatever zh it has and
    # falls back to English otherwise (see home_alert_feed: commodity headlines/details
    # and the macro numeric detail line have no zh at source).
    try:
        from engine.i18n import t as T
    except Exception:  # noqa: BLE001
        def T(en, zh=""):
            return en

    if not alerts:
        return ('<div class="ha-empty">'
                + str(T("No major alerts right now — both engines quiet on top-tier signals.",
                        "目前没有重大警报 — 两个引擎在顶级信号上均保持平静。"))
                + '</div>')
    rows = []
    for a in alerts:
        ts = pd.Timestamp(a["ts"])
        when = ts.strftime("%b %d") if a["date_only"] else ts.strftime("%b %d · %H:%M UTC")
        src_cls = {"macro": "s-macro", "vector": "s-vector",
                   "commodity": "s-commodity"}.get(a["source"], "s-vector")
        src = T(a["source_label"], a.get("source_label_zh") or a["source_label"])
        head = T(a["headline"], a.get("headline_zh") or a["headline"])
        detail = T(a["detail"], a.get("detail_zh") or a["detail"])
        whenspan = T(when, _when_zh(ts, a["date_only"]))
        what = (f'<div class="ha-what">{T(a["what"], a.get("what_zh") or a["what"])}</div>'
                if a.get("what") else "")
        edge = (f'<div class="ha-edge"><b>{T("Conviction:", "可信度：")}</b> '
                f'{T(a["edge"], a.get("edge_zh") or a["edge"])}</div>'
                if a.get("edge") else "")
        cta = T(a.get("cta", "Open →"), a.get("cta_zh") or a.get("cta", "Open →"))
        rows.append(f"""<details class="ha-item">
  <summary>
    <span class="ha-dot d-{a['severity']}"></span>
    <span class="ha-src {src_cls}">{src}</span>
    <span class="ha-head">{head}</span>
    <span class="ha-when">{whenspan}</span>
  </summary>
  <div class="ha-detail">{detail}{what}{edge}<a class="ha-open" href="{a['link']}">{cta}</a></div>
</details>""")
    return "\n".join(rows)


def _hub_html(vm: dict, macro: dict, alerts: list[dict], china: dict | None = None,
              commodities: dict | None = None, watchlist: dict | None = None,
              etf: dict | None = None, hk: dict | None = None,
              forex: dict | None = None) -> str:
    # Bilingual via the i18n layer when present, identity fallback when absent.
    try:
        from engine.i18n import t as T, tr as TR
    except Exception:  # noqa: BLE001
        def T(en, zh=""):
            return en

        def TR(en):
            return en
    risk_cls = "on" if vm["risk_on"] else "off"
    macro_label = config.load()["home"]["alerts"]["macro_label"]
    n_major = len(alerts)
    china = china or {"present": False}
    china_card = ("" if not china.get("present") else f"""
  <a class="c" href="china.html">
    <div class="ico">\U0001F1E8\U0001F1F3</div>
    <h2>{T('China A-Shares', '中国A股')}</h2>
    <p>{T('Regime, sector rotation & cycle read for the Mainland A-share market.', '中国A股市场的周期状态、板块轮动与周期解读。')}</p>
    <span class="stat">{T(china['label'], TR(china['label']))}</span>
    <div class="go">{T('Open China A-Shares →', '打开中国A股 →')}</div>
  </a>""")
    hk = hk or {"present": False}
    hk_risk = hk.get("risk", "")
    hk_card = ("" if not hk.get("present") else f"""
  <a class="c" href="hk.html">
    <div class="ico">\U0001F1ED\U0001F1F0</div>
    <h2>{T('Hong Kong', '香港')}</h2>
    <p>{T('Regime, a primary global risk-on/off overlay, sector rotation & cycle read for the Hang Seng market.', '恒生市场的周期状态、以全球风险开关为主的叠加、板块轮动与周期解读。')}</p>
    <span class="stat">{T(hk['label'], TR(hk['label']))}{(' · ' + T(hk_risk, TR(hk_risk))) if hk_risk else ''}</span>
    <div class="go">{T('Open Hong Kong →', '打开香港 →')}</div>
  </a>""")
    commodities = commodities or {"present": False}
    fav = ", ".join(commodities.get("favored", []))
    commodities_card = ("" if not commodities.get("present") else f"""
  <a class="c" href="commodities.html">
    <div class="ico">◆</div>
    <h2>{T('Commodity Vector', '大宗商品向量')}</h2>
    <p>{T('Regime, allocation & shock-detection for gold, silver, oil & copper.', '黄金、白银、原油与铜的周期、配置与冲击检测。')}</p>
    <span class="stat">{T(commodities['label'], TR(commodities['label']))}{(' · ' + fav) if fav else ''}</span>
    <div class="go">{T('Open Commodity Vector →', '打开大宗商品向量 →')}</div>
  </a>""")
    forex = forex or {"present": False}
    fx_risk = forex.get("risk", "")
    forex_card = ("" if not forex.get("present") else f"""
  <a class="c" href="forex.html">
    <div class="ico">💱</div>
    <h2>{T('Forex Vector', '外汇向量')}</h2>
    <p>{T('Dollar-first currency board — the dollar-smile regime plus risk-context signals on 9 pairs, each scored on its dollar-orthogonalized residual.', '以美元为先的货币面板——美元微笑格局，以及9个货币对在剥离美元后的风险背景信号。')}</p>
    <span class="stat">{T(forex['label'], TR(forex['label']))}{(' · ' + T(fx_risk, TR(fx_risk))) if fx_risk else ''}</span>
    <div class="go">{T('Open Forex Vector →', '打开外汇向量 →')}</div>
  </a>""")
    watchlist = watchlist or {"present": False}
    watchlist_card = ("" if not watchlist.get("present") else f"""
  <a class="c" href="watchlist.html">
    <div class="ico">📋</div>
    <h2>{T('Watchlist', '持仓清单')}</h2>
    <p>{T('Track your own holdings — equities, ETFs, commodities and crypto — each with its live signal.', '跟踪你自己的持仓——股票、ETF、大宗商品与加密货币——每个都附带实时信号。')}</p>
    <span class="stat">{T('Your holdings', '你的持仓')}</span>
    <div class="go">{T('Open Watchlist →', '打开持仓清单 →')}</div>
  </a>""")
    etf = etf or {"present": False}
    etf_card = ("" if not etf.get("present") else f"""
  <a class="c" href="etfs.html">
    <div class="ico">🐳</div>
    <h2>{T('ETF Flow Radar', 'ETF 资金雷达')}</h2>
    <p>{T('What funds are accumulating and trimming — flow-normalized share decisions across popular ETFs, tagged manager-conviction vs index-rebalance.', '基金在增持与减持什么——主流 ETF 经资金流标准化的份额决策，并标注“经理人信念”与“指数再平衡”。')}</p>
    <span class="stat">{T('Manager and index flows', '经理人与指数资金流')}</span>
    <div class="go">{T('Open ETF Flow Radar →', '打开 ETF 资金雷达 →')}</div>
  </a>""")
    return f"""{HUB_MARKER}
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Intelligence</title>
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('lang');if(l)document.documentElement.setAttribute('data-lang',l);}}catch(e){{}}</script>
<link rel="stylesheet" href="theme.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;background:var(--bg);color:var(--text);
 font-family:Inter,sans-serif;display:flex;flex-direction:column;align-items:center;
 padding:22px 20px 60px}}
/* top bar — theme + language toggles pinned to the right of the content column */
.hub-top{{width:100%;max-width:1120px;display:flex;justify-content:flex-end;
 align-items:center;gap:10px;margin-bottom:22px}}
.h{{text-align:center;margin-bottom:36px}}
.h h1{{font-size:40px;font-weight:800;color:var(--text);letter-spacing:-.03em;margin:0 0 8px}}
.h p{{color:var(--muted);font-size:17px;margin:0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:24px;width:100%;max-width:1120px}}
@media(max-width:720px){{.cards{{grid-template-columns:1fr}}}}
/* combined alert feed */
.feed{{width:100%;max-width:880px;margin-top:30px}}
.feed-h{{display:flex;align-items:baseline;justify-content:space-between;margin:0 4px 12px}}
.feed-h h3{{font-size:16px;font-weight:800;color:var(--text);margin:0}}
.feed-h .n{{font-size:13px;color:var(--muted);font-weight:600}}
.feed-card{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:10px 22px}}
.ha-item{{border-bottom:1px solid var(--line)}}
.ha-item:last-child{{border-bottom:none}}
.ha-item summary{{display:flex;align-items:center;gap:11px;padding:13px 0;cursor:pointer;
 list-style:none;flex-wrap:wrap}}
.ha-item summary::-webkit-details-marker{{display:none}}
.ha-dot{{width:10px;height:10px;border-radius:50%;flex:none}}
.ha-dot.d-high{{background:var(--act)}} .ha-dot.d-medium{{background:var(--info)}} .ha-dot.d-info{{background:var(--muted)}}
.ha-src{{font-size:11px;font-weight:700;padding:3px 9px;border-radius:7px}}
.ha-src.s-macro{{background:color-mix(in srgb,#6366f1 16%,var(--panel));color:color-mix(in srgb,#6366f1 78%,var(--text))}}
.ha-src.s-vector{{background:color-mix(in srgb,var(--info) 16%,var(--panel));color:color-mix(in srgb,var(--info) 80%,var(--text))}}
.ha-src.s-commodity{{background:color-mix(in srgb,var(--warn) 18%,var(--panel));color:color-mix(in srgb,var(--warn) 82%,var(--text))}}
.ha-head{{flex:1;min-width:200px;font-weight:600;color:var(--text);font-size:14px}}
.ha-when{{font-size:12px;color:var(--muted);font-weight:600}}
.ha-detail{{padding:0 0 13px 21px;font-size:13px;color:var(--text);line-height:1.6}}
.ha-detail a{{font-weight:700;white-space:nowrap}}
.ha-what{{margin:7px 0 9px;padding-top:8px;border-top:1px solid var(--line);
 font-size:12.5px;color:var(--muted);line-height:1.55}}
.ha-edge{{margin:4px 0 9px;font-size:12px;color:var(--text);line-height:1.5}}
.ha-edge b{{color:var(--muted);font-weight:600}}
.ha-open{{display:inline-block;color:var(--link);font-weight:700}}
.ha-empty{{padding:18px;text-align:center;color:var(--muted);font-size:14px}}
.c{{background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:30px;
 text-decoration:none;color:inherit;transition:transform .15s,box-shadow .15s,border-color .15s;display:block}}
.c:hover{{transform:translateY(-3px);box-shadow:0 12px 30px rgba(16,24,64,.18);border-color:var(--link)}}
.c .ico{{font-size:30px}}
.c h2{{font-size:23px;font-weight:800;color:var(--text);margin:14px 0 6px;letter-spacing:-.02em}}
.c p{{color:var(--muted);font-size:14px;margin:0 0 18px;min-height:40px}}
.stat{{display:inline-block;padding:6px 12px;border-radius:9px;background:var(--panel2);
 color:var(--text);font-weight:700;font-size:13px;margin-right:8px}}
.stat.on{{background:color-mix(in srgb,var(--info) 16%,var(--panel));color:color-mix(in srgb,var(--info) 80%,var(--text))}}
.stat.off{{background:color-mix(in srgb,var(--act) 16%,var(--panel));color:color-mix(in srgb,var(--act) 80%,var(--text))}}
.go{{margin-top:18px;font-weight:700;color:var(--link);font-size:14px}}
.foot{{margin-top:40px;color:var(--muted);font-size:12px;text-align:center}}
.site-footer{{width:100%;max-width:880px;margin:30px auto 0;padding-top:22px;
 border-top:1px solid var(--line);text-align:center;line-height:1.6}}
.site-footer .made{{display:block;font-size:13.5px;font-weight:700;color:var(--text);letter-spacing:.2px}}
.site-footer .dev{{display:block;margin-top:1px;font-size:12px;color:var(--muted)}}
</style></head><body>
<div class="hub-top">
  <button class="theme-switch" aria-label="Toggle dark / light mode">
    <span class="ic sun">☀️</span><span class="ic moon">🌙</span><span class="knob"></span>
  </button>
  <div class="lang-toggle" role="group" aria-label="Language">
    <span class="pill"></span>
    <span class="opt en-opt" data-l="en">EN</span>
    <span class="opt zh-opt" data-l="zh">中文</span>
  </div>
</div>
<div class="h"><h1>{T('Market Intelligence', '市场情报')}</h1>
<p>{T('Market regime dashboards, one zero-cost data engine.', '市场周期仪表盘，一套零成本数据引擎。')}</p></div>
<div class="cards">
  <a class="c" href="macro.html">
    <div class="ico">\U0001F30D</div>
    <h2>{T(macro_label, TR(macro_label))}</h2>
    <p>{T('Regime, liquidity & sector-flow read across the global business cycle.', '纵观全球商业周期的市场状态、流动性与板块资金流向解读。')}</p>
    <span class="stat">{T(macro['label'], TR(macro['label']))}</span>
    <div class="go">{T(f"Open {macro_label} →", f"打开{TR(macro_label)} →")}</div>
  </a>{china_card}{hk_card}
  <a class="c" href="vector.html">
    <div class="ico">₿</div>
    <h2>{T('Bitcoin Vector', '比特币向量')}</h2>
    <p>{T('Risk regime, momentum, structure & backtested allocation for Bitcoin.', '比特币的风险状态、动量、结构与经回测的仓位策略。')}</p>
    <span class="stat {risk_cls}">{T('Risk', '风险')} {T(vm['risk_word'], TR(vm['risk_word']))} · {vm['risk_index']}</span>
    <span class="stat">{T('Momentum', '动量')} {vm['momentum']}</span>
    <div class="go">{T('Open Bitcoin Vector →', '打开比特币向量 →')}</div>
  </a>{commodities_card}{forex_card}{etf_card}{watchlist_card}
</div>
<div class="feed">
  <div class="feed-h"><h3>{T('Latest Alerts', '最新警报')}</h3>
    <span class="n">{n_major} {T('major · from both feeds ·', '条重要 · 来自两个数据源 ·')} <a href="vector.html#timeline">{T('full Vector timeline →', '完整向量时间线 →')}</a></span></div>
  <div class="feed-card">{_hub_alert_rows(alerts)}</div>
</div>
<div class="foot">{T('Built', '生成于')} {vm['built']} · {T('mechanical, backtested, free public data · not investment advice', '机械化 · 经回测 · 免费公开数据 · 非投资建议')}</div>
<footer class="site-footer">
  <span class="made">{T('Made with ❤️ in Canada', '用 ❤️ 在加拿大制作')}</span>
  <span class="dev">{T('Developed by', '开发者')} Chris Wong</span>
</footer>
<script src="theme.js"></script>
</body></html>"""


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def gauge_pos(value: float, lo: float, hi: float) -> float:
    return round(100 * min(max((value - lo) / (hi - lo), 0), 1), 1)


TYPE_LABEL = {"flash_crash": "Flash", "risk_regime": "Risk", "structure_shift": "Structure",
              "momentum_trigger": "Momentum", "allocation_change": "Allocation",
              "fundamentals": "Fundamentals", "market_mode": "Mode",
              "leadership": "Leadership", "risk_extreme": "Risk"}
TYPE_LABEL_ZH = {"flash_crash": "闪崩", "risk_regime": "风险", "structure_shift": "结构",
                 "momentum_trigger": "动量", "allocation_change": "配置",
                 "fundamentals": "基本面", "market_mode": "模式",
                 "leadership": "领涨", "risk_extreme": "风险"}
_WD_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]  # Monday=0


def _group_timeline(events: list[dict]) -> list[dict]:
    """Group events by day (newest first) for the timeline UI, enriching each
    with a display label/filter key and a parsed time."""
    days: dict[str, list] = {}
    for e in events:
        ts = pd.Timestamp(e["ts"])
        day = ts.strftime("%Y-%m-%d")
        e = {**e, "label": TYPE_LABEL.get(e["type"], e["type"]),
             "label_zh": TYPE_LABEL_ZH.get(e["type"], TYPE_LABEL.get(e["type"], e["type"])),
             "filter": "flash" if e["type"] == "flash_crash" else
                       ("risk" if e["type"] in ("risk_regime", "risk_extreme") else
                        ("structure" if e["type"] == "structure_shift" else
                         ("momentum" if e["type"] == "momentum_trigger" else "other"))),
             "time": ts.strftime("%H:%M UTC") if (ts.hour or ts.minute) else "",
             "daylabel": ts.strftime("%a %b %d"),
             "daylabel_zh": f"{ts.month}月{ts.day}日 {_WD_ZH[ts.weekday()]}"}
        days.setdefault(day, []).append(e)
    return [{"day": d, "daylabel": evs[0]["daylabel"],
             "daylabel_zh": evs[0]["daylabel_zh"], "events": evs}
            for d, evs in sorted(days.items(), reverse=True)]


def _r(v, n=2):
    """Round a possibly-NaN/None scalar to n places, else None (template shows —)."""
    return round(float(v), n) if v is not None and pd.notna(v) else None


def chart_ethbtc(ratio: pd.Series, ma: pd.Series | None, cfg: dict) -> str:
    d = _tail(ratio, 365 * 5)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.index, y=d.values, name="ETH/BTC",
                             line={"color": C["blue"], "width": 1.6}))
    if ma is not None:
        fig.add_trace(go.Scatter(x=d.index, y=ma.reindex(d.index).values, name="50w MA",
                                 line={"color": C["faint"], "dash": "dot", "width": 1.2}))
    for lvl, lbl, col in ((cfg["btc_season_line"], "0.05 · deep BTC-season", C["red"]),
                          (cfg["alt_season_line"], "0.07 · alt-season", C["blue"])):
        fig.add_hline(y=lvl, line={"color": col, "dash": "dash", "width": 1},
                      annotation_text=lbl, annotation_font_size=10)
    fig.update_layout(**{**PLOT, "height": 300})
    return _html(fig)


def build_allocation_page(env, site: Path, sig: pd.DataFrame, cards: dict,
                          mtf_a: dict, verdict: dict) -> None:
    """The allocation deep-dive page: strategy variants + backtests, AND the
    altcoin-cycle / ETH allocation keyed to (cycle regime x alt-season x risk)."""
    from engine import alt_cycle
    cfg = config.load()["vector"]["alt_cycle"]
    close = sig["close"]
    last = sig.iloc[-1]
    eth = _series("yahoo", "ETH-USD")
    eb = alt_cycle.ethbtc_signal(eth, close, cfg)
    cg = store.read("coingecko", "global_market")
    dom = float(cg["btc_dominance_pct"].iloc[-1]) if cg is not None and not cg.empty else None
    ethdom = float(cg["eth_dominance_pct"].iloc[-1]) if cg is not None and not cg.empty else None
    score, bucket = alt_cycle.alt_season_score(eb, dom, cfg)
    lad = mtf_a.get("ladder") or {}
    regime = lad.get("regime")
    grid = alt_cycle.alloc_grid(regime, bucket)
    pvm = {
        "as_of": sig.index.max().strftime("%b %d, %Y"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "price": close.iloc[-1],
        "grid": grid, "regime": regime, "regime_label": lad.get("regime_label"),
        "regime_label_zh": lad.get("regime_label_zh"), "verdict": verdict,
        "alloc_pct": round(100 * last["alloc_optimal"]),
        "cards": cards,
        "alt": {
            "ethbtc": _r(eb.get("level"), 4) if eb else None,
            "ethbtc_pctile": eb.get("pctile") if eb else None,
            "above_ma": eb.get("above_ma") if eb else None,
            "slope": _r(100 * eb["slope"], 1) if eb.get("slope") is not None else None,
            "season": eb.get("season") if eb else None,
            "score": score, "bucket": bucket,
            "dom": _r(dom, 1), "ethdom": _r(ethdom, 1),
        },
        "chart_ethbtc": chart_ethbtc(eb["ratio"], eb.get("ma"), cfg) if eb else "",
    }
    html = env.get_template("vector_allocation.html.j2").render(**pvm, C=C)
    (site / "vector_allocation.html").write_text(html)
    log.info("wrote %s/vector_allocation.html (%d KB)", site, len(html) // 1024)


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

    # alert timeline (deterministic rebuild from signal + hourly history)
    from engine import btc_alerts
    acfg = config.load()["vector"]["alerts"]
    all_events = btc_alerts.rebuild(sig)
    timeline = _group_timeline(btc_alerts.recent(all_events, acfg["timeline_days"]))
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

    # Multi-timeframe cycle ladder (reuses the macro engine) + confluence verdict
    from engine import btc_mtf
    mtf_a = btc_mtf.mtf_ladder(close, hi)
    risk_on = last["risk_regime"] == "low_risk"
    verdict = btc_mtf.confluence_verdict(mtf_a, last.get("composite_state"), risk_on)
    _TF = (("D", "Daily"), ("3D", "3-Day"), ("W", "Weekly"), ("2W", "Biweekly"), ("ME", "Monthly"))
    mtf_rows = []
    for key, lbl in _TF:
        s = (mtf_a.get("mtf") or {}).get(key) or {}
        if not s:
            continue
        macd = ("up" if s.get("macd_cross_up") or s.get("macd_curl_up") else
                ("down" if s.get("macd_cross_dn") or s.get("macd_curl_dn") else
                 ("pos" if s.get("macd_pos") else "neg")))
        mtf_rows.append({"key": key, "label": lbl, "rsi14": s.get("rsi14"),
                         "rsi5": s.get("rsi5"), "stoch": s.get("stoch"), "macd": macd,
                         "trend": (verdict.get("per_tf") or {}).get(key, "flat")})
    lad = mtf_a.get("ladder") or {}

    # conviction layer: classify the mid (7d) + short (3d) directional probs into
    # an HONEST state (TOSS-UP / LEAN / EDGE) — computed here where verdict + mtf_rows
    # co-exist, then attached to env/scn so the cards lead with the state, not a
    # misleading 53/47 bar.
    _scfg = config.load()["vector"]["scenarios"]
    envd = env_probabilities(sig, _scfg)
    scnd = scenarios_3d(sig, _scfg, hi, lo)
    _min_n = _scfg["prob_min_cell_n"]
    _bands = tuple(_scfg.get("conv_band_pp", (3, 7)))
    envd["conv"] = _conviction(envd.get("p_bull_7d"), envd.get("n"), envd.get("tilt"),
                               _tape_sign(mtf_rows, {"W", "2W"}), verdict.get("mid_sign", 0), _min_n, _bands)
    envd["conv"]["why_en"], envd["conv"]["why_zh"] = _conviction_why(
        envd["conv"], envd.get("cell"), envd.get("n"), 7)
    scnd["conv"] = _conviction(scnd.get("bull_prob"), scnd.get("n"), scnd.get("tilt"),
                               _tape_sign(mtf_rows, {"D", "3D"}), verdict.get("short_sign", 0), _min_n, _bands)
    scnd["conv"]["why_en"], scnd["conv"]["why_zh"] = _conviction_why(
        scnd["conv"], scnd.get("cell"), scnd.get("n"), 3)

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
        # ---- accuracy-upgrade layers (Tier 1/1b/2) ----
        "composite_state": last.get("composite_state", "NEUTRAL"),
        "verdict": verdict,
        "mtf_rows": mtf_rows,
        "ladder": {
            "state": lad.get("state"), "label": lad.get("label"), "label_zh": lad.get("label_zh"),
            "action": lad.get("action"), "action_zh": lad.get("action_zh"),
            "regime": lad.get("regime"), "regime_label": lad.get("regime_label"),
            "regime_label_zh": lad.get("regime_label_zh"),
            "summary_line": lad.get("summary_line"), "summary_line_zh": lad.get("summary_line_zh"),
            "entry_text": (lad.get("entry") or {}).get("text"),
            "entry_text_zh": (lad.get("entry") or {}).get("text_zh"),
            "age_short": lad.get("age_short"), "strength": lad.get("strength"),
        },
        "valuation": {
            "mvrv_z": _r(last.get("mvrv_z"), 2),
            "mvrv_z_pctile": _r(last.get("mvrv_z_pctile"), 0),
            "nupl": _r(last.get("nupl"), 2),
            "mayer": _r(last.get("mayer"), 2),
            "state": last.get("valuation_state"),
            "extreme": last.get("market_extreme"),
            "sth_cb_ratio": _r(100 * last["sth_cb_ratio"], 1) if pd.notna(last.get("sth_cb_ratio")) else None,
            "sth_cost_basis": _r(last.get("sth_cost_basis"), 0),
            "deep_value": bool(pd.notna(last.get("mvrv_z")) and last["mvrv_z"] < 0),
            "overvalued": bool(pd.notna(last.get("mayer")) and last["mayer"] > 2.4),
            "hash_ribbon": last.get("hash_ribbon"),
            "puell": _r(last.get("puell"), 2),
            "reserve_risk": _r(last.get("reserve_risk"), 5),
            "reserve_risk_pctile": _r(last.get("reserve_risk_pctile"), 0),
            "rr_top": bool(pd.notna(last.get("reserve_risk")) and last["reserve_risk"] > 0.02),
        },
        "options": {
            "dvol": _r(last.get("dvol"), 1),
            "dvol_pctile": _r(last.get("dvol_pctile"), 0),
            "vrp": _r(last.get("vrp"), 1),
            "skew_25d": _r(last.get("skew_25d"), 3),
            "rr_25d": _r(last.get("rr_25d"), 1),
            "term_slope": _r(last.get("term_slope_30_90"), 1),
            "put_call": _r(last.get("put_call_oi_ratio"), 2),
            "max_pain": _r(last.get("max_pain"), 0),
            "atm_iv_30d": _r(last.get("atm_iv_30d"), 1),
            "skew_term": _r(last.get("skew_term"), 3),
            "basis_ann": _r(last.get("basis_ann"), 1),
            "basis_slope": _r(last.get("basis_slope"), 1),
        },
        "leverage": {
            "oi_total": _r(last.get("oi_total_usd"), 0),
            "oi_mcap_pctile": _r(last.get("oi_mcap_pctile"), 0),
            "funding_annual": _r(last.get("funding_annual_pct"), 1),
            "funding_z": _r(last.get("funding_z"), 1),
            "oi_divergence": _r(100 * last["oi_price_divergence"], 1) if pd.notna(last.get("oi_price_divergence")) else None,
            "stress": _r(last.get("leverage_stress"), 0),
        },
        "macro": {
            "score": _r(last.get("macro_score"), 2),
            "regime": last.get("macro_regime"),
            "net_liq_bn": _r(last.get("net_liquidity_bn"), 0),
            "net_liq_roc": _r(last.get("net_liq_roc"), 1),
            "real_yield": _r(last.get("real_yield"), 2),
            "hy_oas": _r(last.get("hy_oas"), 2),
            "vix": _r(last.get("vix"), 1),
            "dxy": _r(last.get("dxy"), 1),
            "global_m2_yoy": _r(last.get("global_m2_yoy"), 1),
            "global_liq_regime": last.get("global_liq_regime"),
        },
        "onchain": {
            "premium": _r(last.get("coinbase_premium_ema"), 2),
            "premium_hot": bool(pd.notna(last.get("coinbase_premium_ema")) and last["coinbase_premium_ema"] > 1.5),
            "ssr": _r(last.get("ssr"), 1),
            "ssr_osc": _r(last.get("ssr_oscillator"), 2),
            "mpi": _r(last.get("mpi"), 2),
        },
        "impulse": {
            "value": _r(last.get("impulse"), 2),
            "state": last.get("impulse_state"),
            "pos_pct": _r(last.get("impulse_pos_pct"), 0),
            "er": _r(last.get("efficiency_ratio"), 2),
        },
        "cycle": {
            "pct": _r(100 * last["cycle_pct"], 0) if pd.notna(last.get("cycle_pct")) else None,
            "phase": last.get("cycle_phase"),
            "days": _r(last.get("days_since_halving"), 0),
            "vdd": _r(last.get("vdd_multiple"), 2),
            "vdd_pctile": _r(last.get("vdd_pctile"), 0),
        },
        "positioning": {
            "cot_net_pct": _r(last.get("cot_net_pct"), 1),
            "cot_z": _r(last.get("cot_z"), 2),
            "crowded": bool(pd.notna(last.get("cot_z")) and last["cot_z"] > 1.5),
        },
        "correlation": {
            "spx": _r(last.get("corr_spx"), 2),
            "gold": _r(last.get("corr_gold"), 2),
            "regime": last.get("risk_asset_regime"),
        },
        "gauges": {
            "momentum": gauge_pos(last["momentum"], -1, 1),
            "risk": last["risk_index"],
            "vol": round(100 * last["vol_pctile"]) if pd.notna(last["vol_pctile"]) else 50,
            "flow": round(100 * last["flow_pctile"]) if pd.notna(last["flow_pctile"]) else 50,
        },
        "env": envd,
        "scn": scnd,
        "cards": cards,
        "cross": cross_asset(close),
        "calib": calib,
        "timeline": timeline,
        "timeline_days": acfg["timeline_days"],
        "n_alerts": sum(len(d["events"]) for d in timeline),
        "charts": {
            "risk_strategy": chart_risk_vs_strategy(sig, eq, hodl),
            "momentum": chart_oscillator(sig["momentum"], close, "Momentum"),
            "structure": chart_oscillator(sig["structure"], close, "Structure Shift"),
            "bfi": chart_bfi(sig),
        },
    }

    env = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates")),
                      autoescape=True)
    # Bilingual when the (separately-owned) i18n layer is present, identity
    # fallback when it isn't — so the page builds either way (immune to i18n churn).
    try:
        from engine import i18n
        _td, _tr = i18n.td, i18n.tr
    except Exception:  # noqa: BLE001 — i18n layer absent -> English-only, still builds
        _td = _tr = lambda en: en
    env.globals.update(td=_td, tr=_tr)
    env.filters["money"] = lambda v: f"${v:,.0f}" if pd.notna(v) else "—"
    env.filters["money1"] = lambda v: f"${v/1000:,.1f}K" if pd.notna(v) else "—"
    html = env.get_template("vector.html.j2").render(**vm, C=C)
    site = Path(config.load()["storage"]["site_dir"])
    (site / "vector.html").write_text(html)
    log.info("wrote %s/vector.html (%d KB)", site, len(html) // 1024)
    try:
        build_allocation_page(env, site, sig, cards, mtf_a, verdict)
    except Exception as e:  # noqa: BLE001 — never let the sub-page break the main build
        log.error("allocation page failed (%s)", e)
    build_landing(site, vm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
