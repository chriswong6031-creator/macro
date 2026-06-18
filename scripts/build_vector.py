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


def _runs(s: pd.Series):
    """Contiguous constant-value runs -> [(start, end, value), ...] so a price
    panel can be shaded by a regime/state series (allocation level, ETF-flow
    accumulation/distribution state, risk regime, …)."""
    s = s.dropna()
    if s.empty:
        return []
    grp = (s != s.shift()).cumsum()
    return [(g.index[0], g.index[-1], g.iloc[0]) for _, g in s.groupby(grp)]


def _plot_idx(index, daily_days: int = 400, weekly_days: int = 1825,
              weekly_step: int = 7, monthly_step: int = 30):
    """Resolution-adaptive index for the heavy full-history overlay charts: daily
    for the last ~400d, ~weekly out to 5y, ~monthly before that. Older points are
    sub-pixel at the 5Y/All zoom and the recent window stays full daily, so the
    line is visually identical at every zoom — but ~5x fewer points get serialized
    (plotly emits one full date-string + value array PER trace, so the full daily
    record dominates the page weight)."""
    if len(index) == 0:
        return index
    end = index.max()
    d0 = end - pd.Timedelta(days=daily_days)
    w0 = end - pd.Timedelta(days=weekly_days)
    daily = index[index >= d0]
    weekly = index[(index < d0) & (index >= w0)][::weekly_step]
    monthly = index[index < w0][::monthly_step]
    return monthly.union(weekly).union(daily)


def _plot_y(s: pd.Series, n: int):
    """Round a y-series to n places and return a plain Python list (NaN -> null).
    plotly base64-packs numpy float64 arrays at a fixed ~10.7 chars/point whatever
    the value; a rounded text list is smaller for these magnitudes and shrinks
    further the fewer decimals it carries. n<=0 emits ints (e.g. whole-dollar)."""
    if n <= 0:
        return [None if pd.isna(v) else int(round(float(v))) for v in s]
    return [None if pd.isna(v) else round(float(v), n) for v in s]


def _dx(index):
    """Date-only x strings ('2015-08-17') for a daily DatetimeIndex. Plotly's
    default datetime serialization emits the full '...T00:00:00.000' per point
    PER trace; for daily data the time part is dead weight, so date strings ~halve
    every x array while still rendering on a normal plotly date axis (sparse
    Timestamp shapes/markers serialize as ISO and land on the same date scale)."""
    return [t.strftime("%Y-%m-%d") for t in index]


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


def alloc_sizing(last: pd.Series, eq: pd.Series, acfg: dict) -> dict:
    """Decompose the live optimal allocation into the Point-4 factors that now SIZE it,
    so the % on the page is explained, not a bare number: the conviction multiplier
    (from the directional-confidence cycle position, tiered TOSS-UP/LEAN/EDGE) and the
    ENFORCED drawdown brake (its current cap + how far the strategy is underwater).
    This is what closes the old 'conviction is just a label' gap on the dashboard."""
    from engine import btc_signals
    cp = float(last["cycle_position"]) if pd.notna(last.get("cycle_position")) else 0.5
    dd = float(eq.iloc[-1] / eq.cummax().iloc[-1] - 1.0)
    thr, decay = float(acfg.get("dd_threshold", 0.25)), float(acfg.get("dd_decay", 1.0))
    floor = float(acfg.get("dd_floor", 0.40))
    cap = min(1.0, max(floor, 1.0 - decay * max(0.0, (-dd) - thr)))
    return {
        "tier": btc_signals.conviction_tier(cp, acfg),
        "mult": round(float(btc_signals.conviction_multiplier(cp, acfg)), 2),
        "brake_active": bool(cap < 0.999),
        "brake_cap": round(100 * cap),
        "dd": round(100 * dd),
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
    # cycle-time prior (orthogonal): the bottom-anchored 1064/364 phase — markup tilts up,
    # markdown down, FADING to the opposite sign inside the top/bottom reversal zone (so it
    # backs off near a projected turn). Same +/-cycle_tilt_pp magnitude, never a trigger.
    # Falls back to the halving phase if the bottom-anchored column is absent.
    cph, cpct = df.get("cphase_phase"), df.get("cphase_pct")
    cyc = df.get("cycle_phase")
    if cfg.get("cycle_tilt_pp") and cph is not None and pd.notna(cph.iloc[-1]):
        ct = cfg["cycle_tilt_pp"] / 100.0
        tz = cfg.get("cycle_top_zone", 0.85)
        in_zone = cpct is not None and pd.notna(cpct.iloc[-1]) and cpct.iloc[-1] >= tz
        if cph.iloc[-1] == "markup":
            tilt += -ct if in_zone else ct
        elif cph.iloc[-1] == "markdown":
            tilt += ct if in_zone else -ct
    elif cyc is not None and pd.notna(cyc.iloc[-1]) and cfg.get("cycle_tilt_pp"):
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
# forward-risk layer: the CONFIRMED quantity the engine actually predicts.
# Short-horizon DIRECTION is a coin-flip (see conviction layer), but forward
# DRAWDOWN is calibrated + both-halves-stable (data/vector/calibration.json ->
# risk_drawdown). We lead the cards with the conditional forward drawdown (avg
# dip + 5th-pctile tail) for the LIVE risk_index band, vs the calm-band baseline.
# (D-vec-RISK; see DECISIONS.)
# --------------------------------------------------------------------------- #
_RISK_BANDS = [(0, 25), (25, 50), (50, 75), (75, 100)]
_RISK_WORD = {"0-25": ("CALM", "平静"), "25-50": ("ELEVATED", "偏高"),
              "50-75": ("HIGH", "偏高警戒"), "75-100": ("EXTREME", "极端")}


def _band_of(ri: float):
    """Right-closed band to match calibrate's pd.cut(include_lowest=True): the
    first band is [0,25], the rest (lo,hi]; ri==50 -> '25-50'."""
    for lo, hi in _RISK_BANDS:
        if (lo == 0 and ri <= hi) or (lo < ri <= hi):
            return (lo, hi)
    return (75, 100)


def _fwd_dd(close: pd.Series, ri: pd.Series, band, horizon: int, mask=None):
    """Forward worst adverse excursion over a `horizon`-trading-day window,
    conditioned on risk_index in `band` at window start (right-closed to reconcile
    with calibration.json). Close-based. Returns avg dip + p05 tail + median pop."""
    lo, hi = band
    fwd_min = close.shift(-1).rolling(horizon).min().shift(-(horizon - 1))
    fwd_max = close.shift(-1).rolling(horizon).max().shift(-(horizon - 1))
    dd = 100 * (fwd_min / close - 1.0)   # worst dip over the window (<=0)
    up = 100 * (fwd_max / close - 1.0)   # best pop over the window (>=0)
    sel = ((ri >= lo) if lo == 0 else (ri > lo)) & (ri <= hi) & dd.notna()
    if mask is not None:
        sel &= mask
    n = int(sel.sum())
    if n < 20:
        return None
    return {"avg": round(float(dd[sel].mean()), 1), "tail": round(float(dd[sel].quantile(0.05)), 1),
            "up": round(float(up[sel].median()), 1), "n": n}


def forward_risk(df: pd.DataFrame, horizon: int) -> dict:
    """Calibrated forward-drawdown read, conditioned on the LIVE risk_index band.
    Carries the calm-band (0-25) baseline for excess-over-calm framing, a both-
    halves (pre/post-2021) stability flag, and a thin-n flag — both drive UI
    de-emphasis. 7d reconciles with calibration.json risk_drawdown; 3d is a DIRECT
    window (never a sqrt/linear haircut)."""
    if "risk_index" not in df:
        return {"tail": None}
    close, ri = df["close"], df["risk_index"]
    band = _band_of(float(ri.iloc[-1]))
    split = pd.Timestamp("2021-01-01")
    pre, post = df.index < split, df.index >= split
    cur = _fwd_dd(close, ri, band, horizon)
    calm = _fwd_dd(close, ri, (0, 25), horizon)
    pre_d = _fwd_dd(close, ri, band, horizon, mask=pre)
    post_d = _fwd_dd(close, ri, band, horizon, mask=post)
    if not cur:
        return {"tail": None}
    stable = bool(pre_d and post_d and
                  abs(pre_d["tail"] - post_d["tail"]) <= max(6.0, 0.4 * abs(cur["tail"])))
    n = cur["n"]
    R = {"band": f"{band[0]}-{band[1]}", "horizon": horizon, "n": n,
         "avg": cur["avg"], "tail": cur["tail"], "up": cur["up"],
         "calm_avg": calm["avg"] if calm else None, "calm_tail": calm["tail"] if calm else None,
         "thin": n < 150, "stable": stable}
    R.update(_risk_lines(R))
    return R


def kelly_sizing(sig: pd.DataFrame, cfg: dict) -> dict | None:
    """Conviction -> capped fractional-Kelly position size (D-vec-KELLY). The honest
    'how much to hold' the conviction/forward-drawdown apparatus implies: the EDGE is
    the calibrated forward-90d return of the CURRENT composite stance (direction is a
    coin-flip, so the edge comes from the regime, not the 3-7d call); fractional-Kelly
    f = kelly_frac · max(E,0)/σ² sizes on it; and the position is CAPPED so the 90d
    worst-case dip (the calibration's forward-drawdown p05 tail for the live risk band)
    stays inside a drawdown budget. The binding constraint (edge vs tail) is named.
    Pure, conservative (half/quarter-Kelly), and 0 when the regime edge is non-positive."""
    if "composite_state" not in sig or "close" not in sig:
        return None
    close = sig["close"]
    fwd90 = close.shift(-90) / close - 1
    cur = sig["composite_state"].iloc[-1]
    r = fwd90.loc[sig.index[sig["composite_state"] == cur]].dropna()
    R90 = forward_risk(sig, 90)
    if len(r) < 50 or not R90 or R90.get("tail") is None:
        return None
    E, sd = float(r.mean()), float(r.std())
    kf = cfg.get("kelly_frac", 0.5)
    ddb = cfg.get("dd_budget", 0.25)
    pos_max = cfg.get("pos_max", 1.0)
    tail = abs(R90["tail"]) / 100.0
    f_kelly = (kf * max(E, 0.0) / (sd * sd)) if sd else 0.0
    f_tail = (ddb / tail) if tail else pos_max
    size = max(0.0, min(f_kelly, f_tail, pos_max))
    return {"size_pct": round(100 * size), "stance": cur,
            "edge_90": round(100 * E, 1), "vol_90": round(100 * sd, 1),
            "tail_90": round(R90["tail"]), "f_kelly": round(f_kelly, 2),
            "f_tail": round(f_tail, 2), "kelly_frac": kf, "dd_budget": round(100 * ddb),
            "binding": "edge" if f_kelly <= f_tail else "tail", "n": int(len(r))}


# FOMC decision dates (2nd meeting day) — Fed-published 2024-2026; 2027 estimated.
_FOMC_DATES = ("2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
               "2024-09-18", "2024-11-07", "2024-12-18", "2025-01-29", "2025-03-19",
               "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29",
               "2025-12-10", "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
               "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09", "2027-01-27",
               "2027-03-17", "2027-05-05", "2027-06-16", "2027-07-28", "2027-09-22",
               "2027-11-03", "2027-12-15")


def _next_first_friday(today: pd.Timestamp):
    for base in (today, today + pd.offsets.MonthBegin(1)):
        first = pd.Timestamp(base.year, base.month, 1)
        fri = first + pd.Timedelta(days=(4 - first.weekday()) % 7)   # first Friday
        if fri >= today:
            return fri
    return None


def catalyst_window(as_of, cfg: dict) -> dict | None:
    """Next scheduled macro BINARY (FOMC decision / monthly jobs report) + a 'don't
    size into the binary' gate. Deterministic calendar — FOMC dates are Fed-published,
    NFP is the first Friday. Vol compresses into these and gaps out of them; the Kelly
    size models neither the event jump nor the vol crush, so an imminent binary is an
    honest sizing caveat, not a forecast. (D-vec-CAT)"""
    today = pd.Timestamp(as_of)
    today = (today.tz_localize(None) if today.tz is not None else today).normalize()
    fomc = [pd.Timestamp(x) for x in _FOMC_DATES if pd.Timestamp(x) >= today]
    events = {k: v for k, v in {"FOMC": fomc[0] if fomc else None,
                                "Jobs report": _next_first_friday(today)}.items() if v is not None}
    if not events:
        return None
    nxt = min(events, key=events.get)
    d = events[nxt]
    return {"next_event": nxt, "next_date": f"{d.strftime('%b')} {d.day}",
            "days": int((d - today).days), "imminent": int((d - today).days) <= cfg.get("imminent_days", 3),
            "fomc_days": int((fomc[0] - today).days) if fomc else None}


def _risk_lines(R: dict) -> dict:
    """Honest EN/ZH prose for the forward-risk read: the band state word + the
    horizon-welded headline, the avg-vs-tail main line, and the band-gated guard
    (contrarian/anti-extrapolation only for the high bands; near-term-only otherwise)."""
    band, h, n = R["band"], R["horizon"], R["n"]
    w_en, w_zh = _RISK_WORD.get(band, ("ELEVATED", "偏高"))
    contrarian = band in ("50-75", "75-100")
    avg, tail, cavg, ctail = R["avg"], R["tail"], R["calm_avg"], R["calm_tail"]
    main_en = (f"Worst-case is the 1-in-20 dip, typical is the average — {n:,} windows in this "
               f"risk band, confirmed in both pre/post-2021 halves. "
               f"Worst-case {tail}% (calm {ctail}%) · typical {avg}% (calm {cavg}%), next {h} days.")
    main_zh = (f"极端为二十中之一的回撤，常见为平均值 — 本风险区间 {n:,} 个窗口，2021 年前后两半均确认。"
               f"极端 {tail}%（平静 {ctail}%）· 常见 {avg}%（平静 {cavg}%），未来 {h} 天。")
    if contrarian:
        guard_en = ("Near-term drawdown risk only. At the 90-day scale high risk historically marks "
                    "bottoms — NOT a sell signal; see the cycle verdict.")
        guard_zh = ("仅为近端回撤风险。在 90 天尺度上，高风险历史上往往标记底部 — 这不是卖出信号；请参见周期判断。")
    else:
        guard_en = (f"A near-term (next-{h}-day) drawdown read, not a cycle call. Risk grades "
                    f"drawdown — it does not rank it perfectly across bands.")
        guard_zh = f"近端（未来 {h} 天）回撤判断，并非周期判断。风险对回撤分级 — 并非在各区间严格排序。"
    return {"word_en": w_en, "word_zh": w_zh, "contrarian": contrarian,
            "head_en": f"{w_en} · next {h} days", "head_zh": f"{w_zh} · 未来 {h} 天",
            "main_en": main_en, "main_zh": main_zh, "guard_en": guard_en, "guard_zh": guard_zh}


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
    drv = f"{c['tilt']:+d}pp macro + 1064/364-cycle tilt" if c["tilt"] else "the cell base-rate"
    drv_zh = f"{c['tilt']:+d}pp 宏观+1064/364周期偏移" if c["tilt"] else "区间基准率"
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
                           days: int | None = None) -> str:
    """Full-history (2015->) BTC price + backtested strategy, with the price panel
    SHADED by the model's allocation (green = fully in / amber = half / clear =
    out) and buy/sell markers at every allocation change — so you can read, at a
    glance, when risk drove the model fully in or fully out. Log price axis;
    1Y/2Y/5Y/All buttons rescale both axes. `days=None` = the whole record."""
    d = df if days is None else _tail(df, days)
    eq, hodl = eq.reindex(d.index), hodl.reindex(d.index)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.28, 0.22],
                        vertical_spacing=0.04)

    # --- allocation regime shading behind the price (the headline upgrade) ---
    # Explicit shapes on row-1's axes (xref="x", yref="y domain" spans the full
    # panel height on the log axis). add_vrect(row=,col=) defers and drops here.
    shade = {1.0: "rgba(34,170,94,0.13)", 0.5: "rgba(245,173,66,0.15)"}  # 0.0 = clear
    for start, end, lvl in _runs(d["alloc_optimal"]):
        fc = shade.get(round(lvl, 1))
        if fc:
            fig.add_shape(type="rect", xref="x", yref="y domain",
                          x0=start, x1=end, y0=0, y1=1,
                          fillcolor=fc, line_width=0, layer="below")

    # downsample only the heavy full-history line traces; the markers, regime
    # shapes and range-button extents below stay full-resolution and exact.
    pidx = _plot_idx(d.index)
    pxs = _dx(pidx)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(d["close"].reindex(pidx), 0), name="BTC Price",
                             line={"color": C["priceln"], "width": 1.4}), row=1, col=1)
    # strategy equity rescaled to price axis for visual overlay
    scale = d["close"].iloc[0] / eq.iloc[0]
    sx = eq * scale
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(sx.reindex(pidx), 0), name="Optimal strategy",
                             line={"color": C["blue"], "width": 1.8}), row=1, col=1)

    # --- buy/sell markers at allocation changes (▲ add when it steps up) ---
    chg = d["alloc_optimal"].diff()
    for mask, sym, col, nm, off in [
        (chg > 0, "triangle-up", "#1FA971", "Buy / add", 0.90),
        (chg < 0, "triangle-down", C["red"], "Sell / trim", 1.10),
    ]:
        idx = d.index[mask.fillna(False).to_numpy()]
        if len(idx):
            to = d["alloc_optimal"].reindex(idx)
            fr = to - chg.reindex(idx)
            txt = [f"{a:.0%} → {b:.0%}" for a, b in zip(fr, to)]
            fig.add_trace(go.Scatter(
                x=idx, y=d["close"].reindex(idx) * off, mode="markers", name=nm,
                marker={"symbol": sym, "color": col, "size": 8,
                        "line": {"width": 0.5, "color": "#fff"}},
                text=txt, hovertemplate="%{x|%b %d %Y} · " + nm + " %{text}<extra></extra>",
            ), row=1, col=1)

    # risk index two-tone (split at threshold 25)
    ri = d["risk_index"].reindex(pidx)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(ri.where(ri < 25), 1), name="Risk (low)",
                             line={"color": C["blue"], "width": 1.5}, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(ri.where(ri >= 25), 1), name="Risk (high)",
                             line={"color": C["red"], "width": 1.5}, showlegend=False), row=2, col=1)
    fig.add_hline(y=25, line={"color": C["faint"], "width": 1, "dash": "dot"}, row=2, col=1)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(d["alloc_optimal"].reindex(pidx), 2), name="Allocation",
                             line={"color": C["indigo"], "width": 1.2, "shape": "hv"},
                             fill="tozeroy", fillcolor="rgba(40,95,255,0.10)",
                             showlegend=False), row=3, col=1)

    # --- range buttons: precompute x+y so the LOG price axis rescales on zoom ---
    now = d.index.max()
    btns = []
    for label, dd in [("1Y", 365), ("2Y", 730), ("5Y", 1825), ("All", None)]:
        x0 = d.index.min() if dd is None else max(d.index.min(), now - pd.Timedelta(days=dd))
        w = (d.index >= x0)
        lo = float(min(d["close"][w].min(), sx[w].min()))
        hi = float(max(d["close"][w].max(), sx[w].max()))
        xr = [x0.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")]
        yr = [float(np.log10(lo * 0.88)), float(np.log10(hi * 1.14))]
        btns.append({"label": label, "method": "relayout",
                     "args": [{"xaxis.range": xr, "xaxis2.range": xr,
                               "xaxis3.range": xr, "yaxis.range": yr}]})
        if label == "1Y":            # open on the 1Y view; wider frames via the buttons
            default_xr, default_yr = xr, yr

    fig.update_yaxes(title_text="Price $", type="log", range=default_yr, row=1, col=1)
    fig.update_xaxes(range=default_xr)
    fig.update_yaxes(title_text="Risk", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="Alloc", range=[-0.05, 1.05], row=3, col=1)
    fig.update_layout(
        **{**PLOT, "height": 480, "margin": {"l": 48, "r": 52, "t": 44, "b": 28}},
        updatemenus=[{
            "type": "buttons", "direction": "right", "showactive": True, "active": 0,
            "x": 1, "xanchor": "right", "y": 1.02, "yanchor": "bottom",
            "bgcolor": "rgba(255,255,255,0.7)", "bordercolor": C["grid"],
            "borderwidth": 1, "font": {"size": 10, "color": C["text"]},
            "pad": {"t": 2, "b": 2, "l": 4, "r": 4}, "buttons": btns,
        }],
    )
    return _html(fig)


def chart_oscillator(s: pd.Series, close: pd.Series, name: str, days: int = 365) -> str:
    s, close = _tail(s, days), _tail(close, days)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=_dx(close.index), y=_plot_y(close, 0), name="BTC",
                             line={"color": C["priceln"], "width": 1}, opacity=0.5),
                  secondary_y=True)
    fig.add_trace(go.Scatter(x=_dx(s.index), y=_plot_y(s.where(s >= 0), 3), name=name,
                             line={"color": C["blue"], "width": 1.6}), secondary_y=False)
    fig.add_trace(go.Scatter(x=_dx(s.index), y=_plot_y(s.where(s < 0), 3), name=name + " (neg)",
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
            fig.add_trace(go.Scatter(x=_dx(d.index), y=_plot_y(d[col], 1), name=nm,
                                     line={"color": color, "width": 1.6 if col == "bfi" else 1.2}))
    fig.add_hrect(y0=40, y1=60, fillcolor=C["grid"], opacity=0.5, line_width=0)
    fig.update_yaxes(range=[0, 100])
    fig.update_layout(**{**PLOT, "height": 240})
    return _html(fig)


def chart_etf_flow(df: pd.DataFrame) -> str:
    """Swissblock's 'Risk Index & ETF Net Flows' (#9): BTC price shaded by the
    spot-ETF accumulation (blue) / distribution (red) regime, with daily net-flow
    bars + the 5-day net flow below. ETF era only (2024->)."""
    d = df[df["etf_flow_btc"].notna()]
    if d.empty:
        return ""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.56, 0.44],
                        vertical_spacing=0.05)
    shade = {"accumulation": "rgba(40,95,255,0.11)", "distribution": "rgba(211,11,11,0.10)"}
    for start, end, st in _runs(d["etf_flow_state"]):
        fc = shade.get(st)
        if fc:
            fig.add_shape(type="rect", xref="x", yref="y domain", x0=start, x1=end,
                          y0=0, y1=1, fillcolor=fc, line_width=0, layer="below")
    fig.add_trace(go.Scatter(x=_dx(d.index), y=_plot_y(d["close"], 0), name="BTC Price",
                             line={"color": C["priceln"], "width": 1.5}), row=1, col=1)
    flow = d["etf_flow_btc"]
    colors = np.where(flow >= 0, C["blue"], C["red"]).tolist()
    fig.add_trace(go.Bar(x=_dx(d.index), y=_plot_y(flow, 1), name="Daily net flow",
                         marker={"color": colors, "line": {"width": 0}},
                         showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=_dx(d.index), y=_plot_y(d["etf_flow_sum"], 1), name="5-day net flow",
                             line={"color": C["indigo"], "width": 1.6}), row=2, col=1)
    fig.add_hline(y=0, line={"color": C["faint"], "width": 1}, row=2, col=1)
    fig.update_yaxes(title_text="Price $", type="log", row=1, col=1)
    fig.update_yaxes(title_text="Net flow (BTC)", row=2, col=1)
    fig.update_layout(**{**PLOT, "height": 340, "barmode": "relative"})
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
                    _watchlist_state(), _etf_state(), _hk_state(), _forex_state(),
                    _bonds_state(), _us_stocks_state(), _strategies_state(), _crossasset_state(),
                    _market_stocks_state("china"), _market_stocks_state("hk"),
                    canada=_canada_state())
    (site / "index.html").write_text(hub)
    log.info("wrote landing hub -> index.html")


def _macro_state() -> dict:
    try:
        d = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        # plain-English regime name only — never the Q-code (macro D28: a user
        # misread "Q1" as calendar Q1). `quad` is carried separately to COLOR the
        # landing-hub regime chip (q1..q4) and feed the risk-pulse — never shown.
        return {"label": d.get("quad_name", "—"), "date": d.get("date", ""),
                "quad": d.get("quad", "")}
    except Exception:
        return {"label": "—", "date": "", "quad": ""}


def _china_state() -> dict:
    """China A-share regime for the hub card (written by build_china, which runs
    before build_vector). `present` gates the card so the hub still works if the
    China page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "china_regime" / "latest.json").read_text())
        return {"label": d.get("quad_name", "—"), "date": d.get("date", ""),
                "quad": d.get("quad", ""), "present": (site / "china.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "quad": "", "present": (site / "china.html").exists()}


def _hk_state() -> dict:
    """Hong Kong / Hang Seng regime for the hub card (written by build_hk, which
    runs before build_vector). `present` gates the card so the hub still works if
    the HK page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "hk_regime" / "latest.json").read_text())
        return {"label": d.get("quad_name", "—"), "date": d.get("date", ""),
                "quad": d.get("quad", ""),
                "risk": d.get("risk_state", ""), "present": (site / "hk.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "quad": "", "risk": "", "present": (site / "hk.html").exists()}


def _canada_state() -> dict:
    """Canada / S&P/TSX regime for the hub card (written by build_canada, which runs
    before build_vector). `present` gates the card; surfaces the commodity/CAD overlay
    risk state as the secondary label (HK-style)."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "canada_regime" / "latest.json").read_text())
        return {"label": d.get("quad_name", "—"), "date": d.get("date", ""),
                "quad": d.get("quad", ""),
                "risk": (d.get("overlay") or {}).get("state", ""),
                "present": (site / "canada.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "quad": "", "risk": "", "present": (site / "canada.html").exists()}


def _intl_state() -> dict:
    """International comparative dashboard summary for the hub card (written by
    build_intl, which runs before build_vector). `present` gates the card."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "intl" / "hub.json").read_text())
        rw = d.get("recession_watch", 0)
        return {"label": d.get("label", "—"), "date": d.get("date", ""),
                "risk": (f"{rw} recession-watch" if rw else ""),
                "present": (site / "intl.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "risk": "", "present": (site / "intl.html").exists()}


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


def _spr_state() -> dict:
    """Strategic Petroleum Reserves read for the hub card (written by build_spr, which
    runs before build_vector). `present` gates the card so the hub still works if the
    SPR page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "spr" / "latest.json").read_text())
        return {"label": d.get("label", "—"), "fill": d.get("us_fill_pct"),
                "date": d.get("date", ""), "present": (site / "spr.html").exists()}
    except Exception:
        return {"label": "—", "fill": None, "date": "",
                "present": (site / "spr.html").exists()}


def _forex_state() -> dict:
    """Forex Vector dollar-smile regime for the hub card (written by build_forex,
    which runs before build_vector). `present` gates the card so the hub still works
    if the forex page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "forex" / "latest.json").read_text())
        desk = d.get("dollar_desk") or {}
        return {"label": d.get("regime", "—"), "date": d.get("date", ""),
                "favored": d.get("favored", []), "risk": d.get("risk", ""),
                "desk_lean": desk.get("lean", ""), "real_rate": desk.get("real_rate_regime", ""),
                "present": (site / "forex.html").exists()}
    except Exception:
        return {"label": "—", "date": "", "favored": [], "risk": "", "desk_lean": "",
                "real_rate": "", "present": (site / "forex.html").exists()}


def _bonds_state() -> dict:
    """Bonds & bond-health read for the hub card (written by build_bonds, which runs
    before build_vector). `present` gates the card so the hub still works if the
    bonds page wasn't built this run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "bonds" / "latest.json").read_text())
        return {"score": d.get("health_score"), "label": d.get("health_label", "—"),
                "phase": d.get("cycle_phase", ""), "date": d.get("date", ""),
                "present": (site / "bonds.html").exists()}
    except Exception:
        return {"label": "—", "phase": "", "date": "", "score": None,
                "present": (site / "bonds.html").exists()}


def _crossasset_state() -> dict:
    """Cross-asset trend/correlation read for the hub card (written by
    build_crossasset, which runs before build_vector)."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "crossasset" / "latest.json").read_text())
        return {"regime": d.get("regime", "—"), "correlation": d.get("correlation", ""),
                "date": d.get("date", ""), "present": (site / "crossasset.html").exists()}
    except Exception:
        return {"regime": "—", "correlation": "", "date": "",
                "present": (site / "crossasset.html").exists()}


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


def _us_stocks_state() -> dict:
    """US Stock Dashboard stat for the United States hero card's stock half
    (written by build_site alongside macro.html). Presence-gated on us_stocks.html."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / "us_stocks" / "latest.json").read_text())
        return {"label": d.get("label", "—"), "n_setups": d.get("n_setups", 0),
                "date": d.get("date", ""), "present": (site / "us_stocks.html").exists()}
    except Exception:
        return {"label": "—", "n_setups": 0, "date": "", "present": (site / "us_stocks.html").exists()}


def _market_stocks_state(market: str) -> dict:
    """Stock-dashboard stat for the China/HK hero half-cards — the live label/count
    written by build_china / build_hk to data/<market>_stocks/latest.json (e.g.
    '12 mean-reversion setups', '24 beta exposures'). Falls back to a generic label."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        d = json.loads((config.data_dir() / f"{market}_stocks" / "latest.json").read_text())
        return {"label": d.get("label") or "—", "n_setups": d.get("n_setups", 0)}
    except Exception:  # noqa: BLE001
        return {"label": "", "n_setups": 0}


def _spvector_state() -> dict:
    """S&P / Macro Vector card — gated on the page existing; shows the current macro
    risk band + recommended equity weight from data/regime/spvector_latest.json when
    build_spvector has run (static label otherwise)."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    present = (site / "spvector.html").exists()
    try:
        import json
        d = json.loads((config.data_dir() / "regime" / "spvector_latest.json").read_text())
        return {"label": d.get("band") or "Index ↔ T-bills",
                "weight": d.get("equity_weight"), "present": present}
    except Exception:  # noqa: BLE001
        return {"label": "Index ↔ T-bills", "weight": None, "present": present}


def _strategies_state() -> dict:
    """Strategy Scorecards umbrella card — gated on the hub page existing; shows the
    strategy count from data/regime/strategies_latest.json when build_strategies has run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    present = (site / "strategies.html").exists()
    try:
        import json
        d = json.loads((config.data_dir() / "regime" / "strategies_latest.json").read_text())
        return {"present": present, "n": d.get("n", 0)}
    except Exception:  # noqa: BLE001
        return {"present": present, "n": 0}


def _ipo_state() -> dict:
    """IPO Radar card — gated on the page existing; shows the issuance-window band +
    the honest aftermarket gap (IPO ETF vs S&P, 5y) from data/regime/ipo_latest.json
    when build_ipo has run."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    present = (site / "ipo.html").exists()
    try:
        import json
        d = json.loads((config.data_dir() / "regime" / "ipo_latest.json").read_text())
        gap = d.get("gap_5y")
        return {"present": present, "band": d.get("window_band") or "—",
                "verdict": d.get("verdict"), "priced_90d": d.get("priced_90d"),
                "gap_5y_pp": (round(gap * 100, 1) if gap is not None else None)}
    except Exception:  # noqa: BLE001
        return {"present": present, "band": "—", "verdict": None,
                "priced_90d": None, "gap_5y_pp": None}


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


# landing-hub: the static CSS lives in a module-level raw string so its many CSS
# braces stay single (the rest of _hub_html is an f-string with doubled braces).
# --------------------------------------------------------------------------- #
# AURORA globe flight-deck landing hub. The CSS + globe DOM are verified-static raw
# strings; per-build data (regimes, prices, alerts) is injected via .replace(). All
# bilingual text is literal <span class="l-en/l-zh"> pairs (theme.css toggles them).
# --------------------------------------------------------------------------- #
_GLOBE_HUB_CSS = r"""<style>
html{overflow-x:hidden}

*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);
 font-family:Inter,sans-serif;display:flex;flex-direction:column;align-items:center;
 padding:22px 20px 56px;position:relative;overflow-x:hidden}
.wrap{width:100%;max-width:1180px;display:flex;flex-direction:column}
.hub-top{display:flex;justify-content:flex-end;align-items:center;gap:10px;margin-bottom:10px}
.h{text-align:center;margin:6px 0 20px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:600;color:var(--muted);
 background:color-mix(in srgb,var(--panel) 64%,transparent);border:1px solid var(--line);padding:6px 14px;border-radius:999px;
 margin-bottom:14px;-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.eyebrow .live{width:7px;height:7px;border-radius:50%;background:#22c55e;
 box-shadow:0 0 0 0 color-mix(in srgb,#22c55e 55%,transparent);animation:livepulse 2.4s ease-out infinite}
@keyframes livepulse{0%{box-shadow:0 0 0 0 color-mix(in srgb,#22c55e 55%,transparent)}70%{box-shadow:0 0 0 8px transparent}100%{box-shadow:0 0 0 0 transparent}}
.h h1{font-size:clamp(30px,4.4vw,46px);font-weight:800;letter-spacing:-.035em;line-height:1.05;margin:0 0 9px;
 background:linear-gradient(176deg,var(--text) 28%,color-mix(in srgb,var(--text) 52%,var(--muted)));
 -webkit-background-clip:text;background-clip:text;color:transparent}
html[data-lang="zh"] .h h1{letter-spacing:0}
.h p{color:var(--muted);font-size:clamp(14px,2vw,16px);margin:0 auto;max-width:560px;line-height:1.5;text-wrap:balance}

/* ===== glass + accent primitives ===== */
.glass{position:relative;border-radius:16px;overflow:hidden;isolation:isolate;
 background:color-mix(in srgb,var(--panel) 80%,transparent);border:1px solid color-mix(in srgb,var(--line) 82%,transparent);
 -webkit-backdrop-filter:blur(13px) saturate(1.08);backdrop-filter:blur(13px) saturate(1.08);
 box-shadow:inset 0 1px 0 color-mix(in srgb,#fff 6%,transparent),0 8px 26px -18px rgba(0,0,0,.5)}
html[data-theme="light"] .glass{background:color-mix(in srgb,var(--panel) 90%,transparent);
 border-color:color-mix(in srgb,var(--line) 92%,transparent);
 box-shadow:0 1px 0 color-mix(in srgb,#fff 60%,transparent),0 6px 20px -14px rgba(20,30,50,.16)}
@supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){.glass{background:color-mix(in srgb,var(--panel) 96%,transparent)}}
.acc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;z-index:2;
 background:linear-gradient(90deg,var(--accent),color-mix(in srgb,var(--accent) 22%,transparent));
 transform:scaleX(0);transform-origin:left;transition:transform .3s cubic-bezier(.2,.7,.3,1)}
.acc::after{content:'';position:absolute;inset:0;z-index:-1;opacity:0;
 background:radial-gradient(360px 180px at 100% 0%,color-mix(in srgb,var(--accent) 12%,transparent),transparent 68%);transition:opacity .25s ease}

/* ===== state band: compact risk pulse + synthesis (slim, one row) ===== */
.state{--accent:#416aec;display:flex;align-items:center;gap:22px;padding:15px 20px;margin-bottom:22px;flex-wrap:wrap}
.state-wash{position:absolute;inset:0;z-index:-1;background:radial-gradient(520px 200px at 0% 0%,color-mix(in srgb,#416aec 10%,transparent),transparent 70%)}
.pulse{flex:0 0 auto;display:flex;flex-direction:column;gap:7px;min-width:230px}
.pulse-head{display:flex;align-items:baseline;gap:9px}
.pulse-eye{font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
html[data-lang="zh"] .pulse-eye{letter-spacing:0}
.pulse-num{font-size:26px;font-weight:800;line-height:1;letter-spacing:-.03em;font-variant-numeric:tabular-nums;color:var(--text)}
.pulse-band{font-size:11.5px;font-weight:800;letter-spacing:.03em;text-transform:uppercase;padding:2px 8px;border-radius:6px;
 color:color-mix(in srgb,var(--warn) 86%,var(--text));background:color-mix(in srgb,var(--warn) 14%,var(--panel2));border:1px solid color-mix(in srgb,var(--warn) 22%,transparent)}
.pulse-band.tone-off{color:color-mix(in srgb,var(--act) 86%,var(--text));background:color-mix(in srgb,var(--act) 13%,var(--panel2));border-color:color-mix(in srgb,var(--act) 22%,transparent)}
.pulse-band.tone-on{color:color-mix(in srgb,var(--ok) 86%,var(--text));background:color-mix(in srgb,var(--ok) 13%,var(--panel2));border-color:color-mix(in srgb,var(--ok) 22%,transparent)}
.pulse-track{position:relative;height:8px;border-radius:999px;background:linear-gradient(90deg,var(--act),var(--warn) 42%,#14b8a6 72%,var(--ok));opacity:.92}
.pulse-mark{position:absolute;top:50%;width:14px;height:14px;border-radius:50%;background:var(--text);border:3px solid var(--panel);
 transform:translate(-50%,-50%);box-shadow:0 1px 5px rgba(0,0,0,.35)}
.pulse-ticks{display:flex;justify-content:space-between;font-size:9.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--muted)}
html[data-lang="zh"] .pulse-ticks{letter-spacing:0}
.state-mid{flex:1;min-width:280px;display:flex;flex-direction:column;gap:6px;border-left:1px solid color-mix(in srgb,var(--line) 70%,transparent);padding-left:22px}
.state-synth{font-size:13.5px;color:var(--muted);line-height:1.5}
.state-synth b{color:var(--text);font-weight:700}
.state-alert{display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--text);text-decoration:none;width:fit-content}
.state-alert .sa-dot{width:7px;height:7px;border-radius:50%;background:var(--act);flex:none}
.state-alert .sa-txt{color:var(--muted)}
.state-alert b{font-weight:600}
.state-alert .sa-go{color:var(--link);font-weight:700;white-space:nowrap}
.state-alert:hover .sa-go{text-decoration:underline}
@media(max-width:760px){.state-mid{border-left:none;padding-left:0;border-top:1px solid color-mix(in srgb,var(--line) 70%,transparent);padding-top:12px}}

/* ===== section labels ===== */
.band{display:flex;align-items:center;gap:11px;margin:0 2px 13px}
.band h2{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);margin:0}
html[data-lang="zh"] .band h2{letter-spacing:0}
.band .ln{flex:1;height:1px;background:linear-gradient(90deg,var(--line),transparent)}
.band .cnt{font-size:11px;font-weight:600;color:var(--muted)}

/* ===== the nav grid (markets + vectors, all visible) ===== */
.nav{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:26px}
@media(max-width:880px){.nav{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.nav{grid-template-columns:1fr}}

.card{position:relative;display:flex;flex-direction:column;padding:15px 16px 14px;min-height:138px;text-decoration:none;color:inherit;
 transition:transform .18s cubic-bezier(.2,.7,.3,1),box-shadow .18s ease,border-color .18s ease}
.card:hover,.card:focus-within{transform:translateY(-3px);border-color:color-mix(in srgb,var(--accent) 48%,var(--line));
 box-shadow:0 16px 36px -16px color-mix(in srgb,var(--accent) 40%,transparent),inset 0 1px 0 color-mix(in srgb,#fff 6%,transparent)}
.card:hover.acc::before,.card:focus-within.acc::before{transform:scaleX(1)} .card:hover.acc::after{opacity:1}
.card-top{display:flex;align-items:center;gap:9px;margin-bottom:9px}
.ico{width:32px;height:32px;flex:none;display:flex;align-items:center;justify-content:center;font-size:17px;border-radius:9px;
 background:color-mix(in srgb,var(--accent) 15%,var(--panel2));border:1px solid color-mix(in srgb,var(--accent) 24%,var(--line));
 transition:transform .18s cubic-bezier(.2,.7,.3,1)}
.card:hover .ico{transform:scale(1.07) rotate(-4deg)}
.card-h{font-size:14.5px;font-weight:800;color:var(--text);margin:0;letter-spacing:-.015em;line-height:1.15}
html[data-lang="zh"] .card-h{letter-spacing:0}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.pill{font-size:11.5px;font-weight:700;letter-spacing:-.005em;background:color-mix(in srgb,var(--accent) 12%,var(--panel2));
 color:color-mix(in srgb,var(--accent) 74%,var(--text));padding:3px 9px;border-radius:7px;border:1px solid color-mix(in srgb,var(--accent) 18%,transparent)}
.pill.q1{background:color-mix(in srgb,var(--q1) 13%,var(--panel2));color:color-mix(in srgb,var(--q1) 80%,var(--text));border-color:color-mix(in srgb,var(--q1) 24%,transparent)}
.pill.q2{background:color-mix(in srgb,var(--q2) 13%,var(--panel2));color:color-mix(in srgb,var(--q2) 80%,var(--text));border-color:color-mix(in srgb,var(--q2) 24%,transparent)}
.pill.q3{background:color-mix(in srgb,var(--q3) 13%,var(--panel2));color:color-mix(in srgb,var(--q3) 80%,var(--text));border-color:color-mix(in srgb,var(--q3) 24%,transparent)}
.pill.q4{background:color-mix(in srgb,var(--q4) 13%,var(--panel2));color:color-mix(in srgb,var(--q4) 80%,var(--text));border-color:color-mix(in srgb,var(--q4) 24%,transparent)}
.pill.on{background:color-mix(in srgb,var(--info) 15%,var(--panel));color:color-mix(in srgb,var(--info) 82%,var(--text));border-color:color-mix(in srgb,var(--info) 22%,transparent)}
.pill.off{background:color-mix(in srgb,var(--act) 14%,var(--panel));color:color-mix(in srgb,var(--act) 82%,var(--text));border-color:color-mix(in srgb,var(--act) 22%,transparent)}
.pill.neg{background:color-mix(in srgb,var(--down) 13%,var(--panel2));color:color-mix(in srgb,var(--down) 80%,var(--text));border-color:color-mix(in srgb,var(--down) 22%,transparent)}
.bar{height:5px;border-radius:999px;background:color-mix(in srgb,var(--line) 70%,transparent);overflow:hidden;margin:-2px 0 9px}
.bar i{display:block;height:100%;border-radius:999px}
.bar.b-risk i{background:linear-gradient(90deg,var(--act),var(--warn))}
.bar.b-health i{background:linear-gradient(90deg,var(--warn),var(--ok))}
.go{margin-top:auto;font-weight:700;color:var(--accent);font-size:12px}
.go::after{content:' →'}
/* market cards: header chip + two clearly-labelled split BUTTONS (Macro / Stock) */
.card .pill.hd{margin-left:auto}
.split{display:flex;flex-direction:column;gap:8px;margin-top:2px}
.splitbtn{display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit;
 border:1px solid color-mix(in srgb,var(--line) 80%,transparent);border-radius:11px;padding:9px 11px;
 background:color-mix(in srgb,var(--panel2) 42%,transparent);
 transition:transform .14s ease,border-color .14s ease,background .14s ease,box-shadow .14s ease}
.splitbtn:hover{border-color:color-mix(in srgb,var(--accent) 52%,var(--line));background:color-mix(in srgb,var(--accent) 8%,var(--panel2));
 transform:translateY(-1px);box-shadow:0 7px 16px -10px color-mix(in srgb,var(--accent) 45%,transparent)}
.sb-ic{width:28px;height:28px;flex:none;display:flex;align-items:center;justify-content:center;font-size:15px;border-radius:8px;
 background:color-mix(in srgb,var(--accent) 14%,var(--panel2));border:1px solid color-mix(in srgb,var(--accent) 22%,transparent)}
.sb-tx{display:flex;flex-direction:column;line-height:1.25;min-width:0}
.sb-tx b{font-size:13px;font-weight:700;color:var(--text);letter-spacing:-.01em}
html[data-lang="zh"] .sb-tx b{letter-spacing:0}
.sb-tx em{font-style:normal;font-size:11px;color:var(--muted)}
.sb-go{margin-left:auto;color:var(--accent);font-weight:700;font-size:13px;transition:transform .14s ease}
.splitbtn:hover .sb-go{transform:translateX(2px)}

.us{--accent:#416aec} .cn{--accent:#e35d6a} .hk{--accent:#a855f7} .ca{--accent:#e5484d} .btc{--accent:#f7931a}
.com{--accent:#d4a12a} .fx{--accent:#14b8a6} .bd{--accent:#0ea5e9} .xa{--accent:#8b5cf6}
.etf{--accent:#3b82f6} .str{--accent:#10b981} .wl{--accent:#64748b}

/* ===== compact alerts (secondary, bottom) ===== */
.alerts{margin-top:4px}
.al-card{padding:6px 18px}
.ha-item{border-bottom:1px solid color-mix(in srgb,var(--line) 70%,transparent)}
.ha-item:last-child{border-bottom:none}
.ha-item summary{display:flex;align-items:center;gap:10px;padding:11px 0;cursor:pointer;list-style:none;flex-wrap:wrap;transition:padding-left .16s ease}
.ha-item summary:hover{padding-left:5px}
.ha-item summary::-webkit-details-marker{display:none}
.ha-dot{width:8px;height:8px;border-radius:50%;flex:none}
.ha-dot.d-high{background:var(--act)} .ha-dot.d-medium{background:var(--info)} .ha-dot.d-info{background:var(--muted)}
.ha-src{font-size:10px;font-weight:700;padding:2px 8px;border-radius:6px;white-space:nowrap;flex:none}
.ha-src.s-macro{background:color-mix(in srgb,#6366f1 16%,var(--panel));color:color-mix(in srgb,#6366f1 80%,var(--text))}
.ha-src.s-vector{background:color-mix(in srgb,var(--info) 16%,var(--panel));color:color-mix(in srgb,var(--info) 82%,var(--text))}
.ha-src.s-commodity{background:color-mix(in srgb,var(--warn) 18%,var(--panel));color:color-mix(in srgb,var(--warn) 84%,var(--text))}
.ha-head{flex:1;min-width:200px;font-weight:600;color:var(--text);font-size:13px}
.ha-when{font-size:11px;color:var(--muted);font-weight:600;white-space:nowrap}
.ha-detail{padding:0 0 12px 22px;font-size:12.5px;color:var(--text);line-height:1.55}
.ha-detail a{font-weight:700;color:var(--link)}
.ha-what{margin:6px 0 7px;padding-top:7px;border-top:1px solid color-mix(in srgb,var(--line) 70%,transparent);font-size:12px;color:var(--muted);line-height:1.5}
.ha-edge{margin:3px 0 7px;font-size:11.5px;color:var(--text)}
.ha-edge b{color:var(--muted);font-weight:600}
.al-more{display:block;text-align:center;padding:11px 0 6px;font-size:12.5px;font-weight:700;color:var(--link);text-decoration:none}
.al-more:hover{text-decoration:underline}

.site-footer{margin:34px auto 0;padding-top:22px;border-top:1px solid var(--line);text-align:center;line-height:1.6}
.site-footer .made{display:block;font-size:13.5px;font-weight:700;color:var(--text);letter-spacing:.2px}
.site-footer .dev{display:block;margin-top:1px;font-size:12px;color:var(--muted)}
.foot{margin-top:18px;color:var(--muted);font-size:12px;text-align:center}
a:focus-visible,.links a:focus-visible{outline:2px solid var(--link);outline-offset:2px;border-radius:8px}

@keyframes smReveal{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}
.reveal{animation:smReveal .45s cubic-bezier(.2,.7,.3,1) both}
.state.reveal{animation-delay:0ms} .nav.mk.reveal{animation-delay:70ms} .nav.vc.reveal{animation-delay:120ms} .alerts.reveal{animation-delay:160ms}
@media (prefers-reduced-motion: reduce){
 .eyebrow .live{animation:none} .reveal{animation:none}
 .card,.ico,.ha-item summary{transition:none} .card:hover{transform:none}}

/* ===== flight deck ===== */
.globe-deck{display:grid;grid-template-columns:minmax(0,2.05fr) minmax(0,1fr);gap:16px;align-items:stretch;max-width:100%}
@media(max-width:880px){.globe-deck{grid-template-columns:minmax(0,1fr)}}
@media(max-width:520px){
 .gd-clock{padding:12px 11px 10px}
 .gd-row{gap:8px;padding:6px 7px}
 .gd-r-idx{font-size:11.5px} .gd-r-px{font-size:10.5px}
 .gd-r-cd{font-size:9.5px} .gd-r-txt{font-size:10.5px}
}
/* the globe is UNBOUNDED — no card; it floats on the page's aurora. The canvas is
   transparent outside the sphere, so body::before's aurora shows through. */
.gd-stage{min-height:640px;display:flex;overflow:visible;background:none;border:none;box-shadow:none;min-width:0}
@media(max-width:880px){.gd-stage{min-height:0;height:min(94vw,500px)}}
.gd-canvas{width:100%;max-width:100%;height:100%;display:block;touch-action:none;cursor:grab;outline:none}
.gd-canvas:focus-visible{outline:2px solid var(--link);outline-offset:-2px}
.gd-poster{position:absolute;inset:0;width:100%;height:100%;transition:opacity .6s ease;pointer-events:none}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);clip-path:inset(50%);white-space:nowrap;margin:-1px;padding:0;border:0}
.gd-legend{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);clip-path:inset(50%);white-space:nowrap;margin:0;padding:0;border:0;list-style:none}
.gd-leg{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:var(--text);cursor:pointer;
 background:color-mix(in srgb,var(--panel) 70%,transparent);border:1px solid var(--line);border-radius:999px;padding:3px 9px;
 -webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.gd-leg:hover{border-color:color-mix(in srgb,var(--accent,var(--info)) 55%,var(--line))}
.gd-leg .dot{width:7px;height:7px;border-radius:50%}
.gd-leg.q1 .dot{background:var(--q1)} .gd-leg.q2 .dot{background:var(--q2)} .gd-leg.q3 .dot{background:var(--q3)} .gd-leg.q4 .dot{background:var(--q4)}
.gd-leg .l-zh{display:none} html[data-lang="zh"] .gd-leg .l-en{display:none} html[data-lang="zh"] .gd-leg .l-zh{display:inline}

/* ===== tooltip ===== */
.gd-tip{position:fixed;z-index:50;width:264px;padding:13px 14px;border-radius:14px;pointer-events:none;
 box-shadow:var(--popover-shadow);transition:opacity .12s ease}
.gd-tip.pinned{pointer-events:auto}   /* a clicked (pinned) tooltip is interactive so its "Open dashboard" link works */
.gd-tip[hidden]{display:none}
.gd-tip-h{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.gd-tip-flag{font-size:18px}
.gd-tip-name{font-weight:800;font-size:14px;color:var(--text);flex:1;letter-spacing:-.01em}
.gd-chip{font-size:11px;font-weight:800;padding:2px 8px;border-radius:7px;white-space:nowrap;
 color:color-mix(in srgb,var(--mq) 82%,var(--text));background:color-mix(in srgb,var(--mq) 15%,var(--panel));border:1px solid color-mix(in srgb,var(--mq) 26%,transparent)}
.gd-chip.q1{--mq:var(--q1)} .gd-chip.q2{--mq:var(--q2)} .gd-chip.q3{--mq:var(--q3)} .gd-chip.q4{--mq:var(--q4)}
.gd-tip-gi{display:flex;flex-direction:column;gap:6px;margin-bottom:9px}
.gd-tip-gi>div{display:flex;align-items:center;gap:8px;font-size:12px}
.gd-tip-k{color:var(--muted);font-weight:600;width:58px;flex:none}
.gd-tip-gi b{font-variant-numeric:tabular-nums;font-weight:700;width:42px;text-align:right}
.gd-bar{position:relative;flex:1;height:5px;border-radius:999px;background:color-mix(in srgb,var(--line) 60%,transparent)}
.gd-bar::before{content:'';position:absolute;left:50%;top:-2px;width:1px;height:9px;background:color-mix(in srgb,var(--line) 90%,transparent)}
.gd-bar i{position:absolute;top:0;height:100%;border-radius:999px}
.gd-tip-row{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:7px;color:var(--text)}
.gd-dots{letter-spacing:1px;color:var(--info)}
.gd-lim{font-size:10px;font-weight:700;color:var(--warn);background:color-mix(in srgb,var(--warn) 14%,var(--panel2));padding:1px 6px;border-radius:5px}
.gd-tip-idx{display:flex;align-items:center;gap:8px;font-size:12.5px;padding-top:8px;border-top:1px solid var(--line);margin-bottom:7px}
.gd-tip-idx span:first-child{color:var(--muted);flex:1}
.gd-tip-idx b{font-variant-numeric:tabular-nums}
.gd-chg{font-weight:700}
.gd-tip-foot{font-size:10.5px;color:var(--muted);line-height:1.45;margin-bottom:9px}
.gd-tip-go{display:inline-block;font-size:12px;font-weight:700;color:var(--link);text-decoration:none}
.gd-tip .l-zh{display:none} html[data-lang="zh"] .gd-tip .l-en{display:none} html[data-lang="zh"] .gd-tip .l-zh{display:inline}

/* ===== sidebar clock ===== */
.gd-clock{display:flex;flex-direction:column;padding:14px 14px 12px;min-width:0;max-width:100%}
.gd-clock>header{font-size:12px;font-weight:800;color:var(--text);letter-spacing:-.01em;margin:0 2px 11px;display:flex;gap:6px;align-items:baseline}
.gd-clock>header .gd-utc{color:var(--muted);font-variant-numeric:tabular-nums;font-weight:600}
.gd-clock ul{list-style:none;margin:0;padding:0;flex:1;display:flex;flex-direction:column;gap:3px}
.gd-row{display:flex;align-items:center;gap:10px;padding:7px 9px;border-radius:10px;border:1px solid transparent;cursor:pointer;transition:background .14s,border-color .14s}
.gd-row:hover,.gd-row.sel{background:color-mix(in srgb,var(--info) 7%,var(--panel2));border-color:color-mix(in srgb,var(--info) 22%,var(--line))}
.gd-row:focus-visible{outline:2px solid var(--link);outline-offset:1px}
.gd-r-sm{width:26px;flex:none}
.gd-sm{width:26px;height:16px;display:block}
.gd-r-main{flex:1;display:flex;flex-direction:column;min-width:0;gap:1px}
.gd-r-idx{font-size:12px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gd-r-px{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.gd-r-px em{font-style:normal;font-weight:700}
.gd-r-state{display:flex;flex-direction:column;align-items:flex-end;gap:1px;text-align:right;flex:none}
.gd-r-dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.gd-r-dot.on{background:var(--ok);box-shadow:0 0 0 3px color-mix(in srgb,var(--ok) 22%,transparent)}
.gd-r-dot.off{background:var(--muted)} .gd-r-dot.lunch{background:var(--warn)}
.gd-r-txt{font-size:11px;font-weight:700;color:var(--text)}
.gd-r-cd{font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.gd-r-state{flex-direction:row;align-items:center;gap:7px}
.gd-asof,.gd-foot{font-size:10px;color:var(--muted);margin:8px 2px 0;line-height:1.4}
.gd-clock .l-zh{display:none} html[data-lang="zh"] .gd-clock .l-en{display:none} html[data-lang="zh"] .gd-clock .l-zh{display:inline}
.gd-r-cd .l-zh,.gd-r-txt .l-zh{display:none} html[data-lang="zh"] .gd-r-cd .l-en,html[data-lang="zh"] .gd-r-txt .l-en{display:none}
html[data-lang="zh"] .gd-r-cd .l-zh,html[data-lang="zh"] .gd-r-txt .l-zh{display:inline}

/* ===== celestial day/night backdrop (sky.js) =====
   #sky floats at z-index:-1 — ABOVE the ambient aurora (body::before, also -1
   but earlier in tree order) and BEHIND all page content. Sun parks on a
   time-of-day arc in light mode; a breathing starfield + moon take over in dark. */
#sky{position:fixed;inset:0;z-index:-1;pointer-events:none;overflow:hidden;--cs:clamp(120px,13vw,214px)}
#sky-stars{position:absolute;inset:0;width:100%;height:100%;display:block}
#sky-sun,#sky-moon{position:absolute;width:var(--cs);height:var(--cs);border-radius:50%;
 transform:translate(-50%,calc(-50% + 80vh));opacity:0;
 transition:transform 1.7s cubic-bezier(.16,.78,.29,1),opacity 1.25s ease}
#sky[data-sky="day"] #sky-sun{transform:translate(-50%,-50%);opacity:1}
#sky[data-sky="night"] #sky-moon{transform:translate(-50%,-50%);opacity:1}
/* sun — a luminous light source: white-hot core, warm body, big soft bloom + a
   faint blurred corona flare (no hard cartoon spokes) */
#sky-sun{background:radial-gradient(circle at 50% 50%,#fffdf7 0%,#fff2cc 20%,#ffd87f 40%,#ffb84d 58%,rgba(255,156,54,.34) 76%,transparent 84%);
 box-shadow:0 0 46px 6px rgba(255,226,150,.6),0 0 110px 28px rgba(255,192,92,.38),0 0 220px 86px rgba(255,170,68,.18),0 0 360px 160px rgba(255,160,60,.08)}
#sky-sun::before{content:'';position:absolute;inset:-46%;border-radius:50%;filter:blur(11px);opacity:.5;
 background:repeating-conic-gradient(from 0deg,rgba(255,222,150,.16) 0deg 7deg,transparent 7deg 22deg);
 -webkit-mask:radial-gradient(circle,transparent 46%,#000 62%,transparent 92%);mask:radial-gradient(circle,transparent 46%,#000 62%,transparent 92%);
 animation:sky-spin 90s linear infinite}
#sky-sun::after{content:'';position:absolute;inset:12%;border-radius:50%;mix-blend-mode:screen;
 background:radial-gradient(circle at 44% 40%,rgba(255,255,255,.95) 0%,rgba(255,247,214,.25) 42%,transparent 62%);
 animation:sky-breathe 6.5s ease-in-out infinite}
/* moon — a 3-D shaded sphere: soft terminator, faint craters, cool halo */
#sky-moon{background:radial-gradient(circle at 34% 28%,#ffffff 0%,#eef2fb 26%,#cdd8ee 58%,#9fafcf 100%);
 box-shadow:inset -24px -20px 50px rgba(16,26,54,.58),inset 12px 9px 24px rgba(255,255,255,.42),0 0 56px 10px rgba(150,182,242,.3),0 0 160px 60px rgba(120,162,232,.15)}
#sky-moon::before{content:'';position:absolute;inset:0;border-radius:50%;opacity:.3;
 background:radial-gradient(circle at 63% 31%,rgba(116,132,166,.6) 0 5%,transparent 6%),
  radial-gradient(circle at 39% 58%,rgba(116,132,166,.5) 0 3.6%,transparent 4.6%),
  radial-gradient(circle at 71% 64%,rgba(116,132,166,.45) 0 2.6%,transparent 3.6%),
  radial-gradient(circle at 30% 37%,rgba(116,132,166,.4) 0 2%,transparent 3%),
  radial-gradient(circle at 52% 72%,rgba(116,132,166,.4) 0 2.4%,transparent 3.4%)}
#sky-moon::after{content:'';position:absolute;inset:-30%;border-radius:50%;
 background:radial-gradient(circle,rgba(150,182,242,.16) 0%,transparent 62%);
 animation:sky-breathe 7.5s ease-in-out infinite}
@keyframes sky-spin{to{transform:rotate(360deg)}}
@keyframes sky-breathe{0%,100%{opacity:.6}50%{opacity:.95}}
/* keep the header headline legible when the sun/moon glow drifts behind it */
.h{position:relative}
.h::before{content:'';position:absolute;z-index:-1;left:50%;top:-26px;transform:translateX(-50%);
 width:min(880px,95vw);height:calc(100% + 104px);pointer-events:none;
 /* vertical wash: invisible at the top (so it never cuts a hard line across the
    moon/sun) and ramping to a fully opaque --bg behind the lower text — a soft
    fade, not an edge. Sides feathered so there's no vertical seam either. */
 background:linear-gradient(180deg,transparent 0%,color-mix(in srgb,var(--bg) 20%,transparent) 32%,color-mix(in srgb,var(--bg) 72%,transparent) 66%,var(--bg) 100%);
 -webkit-mask:radial-gradient(116% 96% at 50% 46%,#000 60%,transparent 100%);
 mask:radial-gradient(116% 96% at 50% 46%,#000 60%,transparent 100%)}
@media (prefers-reduced-motion: reduce){
 #sky-sun,#sky-moon{transition:none}
 #sky-sun::before,#sky-sun::after,#sky-moon::after{animation:none}}
</style>"""

_GLOBE_DECK_DOM = r"""<section class="globe-deck command" aria-label="Global macro regime globe">
    <div class="gd-stage">
      <canvas class="gd-canvas" data-topo="world-110m.json" role="application" tabindex="0"
        aria-roledescription="interactive macro-regime globe"
        aria-label="Macro regime globe. Arrow keys rotate, plus and minus zoom, Escape deselects." aria-describedby="gd-live"></canvas>
      <span id="gd-live" class="sr-only" aria-live="polite"></span>
      <div class="gd-tip glass" role="tooltip" hidden></div>
      <ul class="gd-legend" aria-label="Markets / 市场列表">__LEGEND__</ul>
    </div>
    <aside class="gd-clock glass" aria-label="Market clock">
      <header><span class="l-en">Market clock</span><span class="l-zh">交易时钟</span> · <time class="gd-utc"></time> UTC</header>
      <ul></ul>
      <p class="gd-asof"><span class="l-en">Prices as of last build · clocks are live</span><span class="l-zh">价格为上次构建时 · 时钟为实时</span></p>
      <p class="gd-foot"><span class="l-en">Regular sessions; holidays not modeled</span><span class="l-zh">常规交易时段，未计入假期</span></p>
    </aside>
  </section>"""

_GQUAD_ZH = {"Goldilocks": "理想增长", "Reflation": "再通胀", "Stagflation": "滞胀",
             "Growth scare": "增长恐慌", "Growth-scare": "增长恐慌", "Deflation": "通缩"}
_GQCLS = {"Q1": "q1", "Q2": "q2", "Q3": "q3", "Q4": "q4"}
_EZ_MEMBERS = ["AUT", "BEL", "CYP", "EST", "FIN", "FRA", "DEU", "GRC", "IRL", "ITA",
               "LVA", "LTU", "LUX", "MLT", "NLD", "PRT", "SVK", "SVN", "ESP", "HRV"]
_ISO_NUM = {"USA": "840", "CAN": "124", "CHN": "156", "JPN": "392", "KOR": "410", "TWN": "158", "GBR": "826",
            "AUT": "040", "BEL": "056", "CYP": "196", "EST": "233", "FIN": "246", "FRA": "250", "DEU": "276",
            "GRC": "300", "IRL": "372", "ITA": "380", "LVA": "428", "LTU": "440", "LUX": "442", "MLT": "470",
            "NLD": "528", "PRT": "620", "SVK": "703", "SVN": "705", "ESP": "724", "HRV": "191"}
_GMETA = {
    "US": dict(iso3="USA", kind="country", flag="🇺🇸", name_en="United States", name_zh="美国",
               idx_en="S&P 500", idx_zh="标普500", pq="data/yahoo/_GSPC.parquet", tz="America/New_York", open="09:30", close="16:00", lunch=None, href="macro.html"),
    "CA": dict(iso3="CAN", kind="country", flag="🇨🇦", name_en="Canada", name_zh="加拿大",
               idx_en="S&P/TSX", idx_zh="标普/TSX", pq="data/canada/_GSPTSE.parquet", tz="America/Toronto", open="09:30", close="16:00", lunch=None, href="canada.html"),
    "CN": dict(iso3="CHN", kind="country", flag="🇨🇳", name_en="China", name_zh="中国",
               idx_en="Shanghai Comp", idx_zh="上证综指", pq="data/china/000001.SS.parquet", tz="Asia/Shanghai", open="09:30", close="15:00", lunch=["11:30", "13:00"], href="china.html"),
    "HK": dict(iso3=None, kind="marker", marker=[114.17, 22.32], flag="🇭🇰", name_en="Hong Kong", name_zh="香港",
               idx_en="Hang Seng", idx_zh="恒生指数", pq="data/hk/_HSI.parquet", tz="Asia/Hong_Kong", open="09:30", close="16:00", lunch=["12:00", "13:00"], href="hk.html"),
    "JP": dict(iso3="JPN", kind="country", flag="🇯🇵", name_en="Japan", name_zh="日本",
               idx_en="Nikkei 225", idx_zh="日経225", pq="data/intl/_N225.parquet", tz="Asia/Tokyo", open="09:00", close="15:00", lunch=["11:30", "12:30"], href="intl.html"),
    "KR": dict(iso3="KOR", kind="country", flag="🇰🇷", name_en="South Korea", name_zh="韩国",
               idx_en="KOSPI", idx_zh="韩国综合", pq="data/intl/_KS11.parquet", tz="Asia/Seoul", open="09:00", close="15:30", lunch=None, href="intl.html"),
    "TW": dict(iso3="TWN", kind="country", flag="🇹🇼", name_en="Taiwan", name_zh="台湾",
               idx_en="TAIEX", idx_zh="加权指数", pq="data/intl/_TWII.parquet", tz="Asia/Taipei", open="09:00", close="13:30", lunch=None, href="intl.html"),
    "GB": dict(iso3="GBR", kind="country", flag="🇬🇧", name_en="United Kingdom", name_zh="英国",
               idx_en="FTSE 100", idx_zh="富时100", pq="data/intl/_FTSE.parquet", tz="Europe/London", open="08:00", close="16:30", lunch=None, href="intl.html"),
    "EZ": dict(iso3=None, kind="bloc", ez_members=_EZ_MEMBERS, flag="🇪🇺", name_en="Eurozone", name_zh="欧元区",
               idx_en="EuroStoxx 50", idx_zh="欧洲斯托克50", pq="data/intl/_STOXX50E.parquet", tz="Europe/Berlin", open="09:00", close="17:30", lunch=None, href="intl.html"),
}
_GRISK = {"q1": ("calm — low macro stress", "平静 — 宏观压力低"),
          "q2": ("moderate — reflationary", "中等 — 再通胀"),
          "q3": ("elevated — stagflationary", "偏高 — 滞胀"),
          "q4": ("high — growth scare", "高 — 增长恐慌")}


def _g_price(pq):
    try:
        df = pd.read_parquet(config.ROOT / pq)
        c = df["close"] if "close" in df.columns else df["Close"]
        last, prev = float(c.iloc[-1]), float(c.iloc[-2])
        return "{:,.2f}".format(last), round(100 * (last / prev - 1), 2)
    except Exception:  # noqa: BLE001
        return None, None


def _g_regime_json(name):
    try:
        return json.loads((config.data_dir() / name / "latest.json").read_text())
    except Exception:  # noqa: BLE001
        return {}


def _globe_markets() -> list:
    """Assemble the 9-market globe blob (US/CA/CN/HK + JP/KR/TW/GB/EZ) from the regime
    JSONs + intl/latest.json. Numbers are real; recession/drawdown null-safe."""
    import json as _json
    home = {"US": _g_regime_json("regime"), "CN": _g_regime_json("china_regime"),
            "HK": _g_regime_json("hk_regime"), "CA": _g_regime_json("canada_regime")}
    intl = _g_regime_json("intl")
    heat = {r["cc"]: r for r in intl.get("heatmap", [])}
    rec = {r["cc"]: r["value"] for r in intl.get("rankings", {}).get("recession_score", {}).get("rows", [])}
    dd = {r["cc"]: r["value"] for r in intl.get("rankings", {}).get("drawdown_risk", {}).get("rows", [])}
    intl_date = intl.get("date", "")
    rows = []
    for cc, m in _GMETA.items():
        quad = qn = ""
        growth = infl = conf = None
        recession = drawdown = None
        asof = ""
        data_limited = False
        if cc in home:
            d = home[cc]
            quad, qn = d.get("quad", ""), d.get("quad_name", "—")
            growth, infl, conf = d.get("growth_score"), d.get("inflation_score"), d.get("confidence")
            asof = d.get("date", "")
            comp = (d.get("macro_risk") or {}).get("components") or {}
            if comp.get("recession") is not None:
                recession = round(100 * comp["recession"])
            if comp.get("drawdown") is not None:
                drawdown = round(100 * comp["drawdown"])
        else:
            h = heat.get(cc, {})
            quad, qn = h.get("quad", ""), h.get("quad_name", "—")
            growth, infl, conf = h.get("growth"), h.get("inflation"), h.get("confidence")
            data_limited = bool(h.get("data_limited"))
            asof = intl_date
            recession, drawdown = rec.get(cc), dd.get(cc)
        qc = _GQCLS.get(quad, "q1")
        price, chg = _g_price(m["pq"])
        rt_en, rt_zh = _GRISK.get(qc, ("—", "—"))
        if m["kind"] == "bloc":
            geo_ids = [_ISO_NUM[x] for x in m["ez_members"] if x in _ISO_NUM]
        elif m.get("iso3"):
            geo_ids = [_ISO_NUM[m["iso3"]]] if m["iso3"] in _ISO_NUM else []
        else:
            geo_ids = []
        rows.append({
            "cc": cc, "name_en": m["name_en"], "name_zh": m["name_zh"], "flag": m["flag"],
            "iso3": m.get("iso3"), "kind": m["kind"], "geo_ids": geo_ids,
            "ez_members": m.get("ez_members"), "marker_lonlat": m.get("marker"),
            "quad": qc, "quad_name_en": qn, "quad_name_zh": _GQUAD_ZH.get(qn, qn),
            "growth": round(growth, 3) if growth is not None else None,
            "inflation": round(infl, 3) if infl is not None else None,
            "confidence": round(conf, 3) if conf is not None else None,
            "data_limited": data_limited, "recession": recession, "drawdown_risk": drawdown,
            "risk_text_en": rt_en, "risk_text_zh": rt_zh, "macro_asof": asof,
            "index_name_en": m["idx_en"], "index_name_zh": m["idx_zh"],
            "index_price": price, "index_chg_pct": chg,
            "tz": m["tz"], "open": m["open"], "close": m["close"], "lunch": m["lunch"], "href": m["href"],
        })
    for r in rows:
        r["agrees_with"] = [o["cc"] for o in rows if o["cc"] != r["cc"] and o["quad"] == r["quad"]]
    return rows


def _bi(en, zh):
    return '<span class="l-en">' + str(en) + '</span><span class="l-zh">' + str(zh) + '</span>'


def _g_legend(blob):
    out = []
    for m in blob:
        out.append('<li><button class="gd-leg ' + m["quad"] + '" data-cc="' + m["cc"] + '">'
                   '<span class="dot"></span>' + m["flag"] + ' '
                   + _bi(m["cc"], m["cc"]) + '</button></li>')
    return "".join(out)


def _g_markets(blob, us_n, cn_n, hk_n):
    by = {m["cc"]: m for m in blob}
    SUB = {
        "US": [("macro.html", "📊", "Macro Dashboard", "宏观看板", "Regime · cycle · drivers", "周期 · 阶段 · 驱动"),
               ("us_stocks.html", "📈", "Stock Dashboard", "个股看板", str(us_n) + " standout setups", str(us_n) + " 只精选个股")],
        "CN": [("china.html", "📊", "Macro Dashboard", "宏观看板", "A-share regime · cycle", "A股周期 · 阶段"),
               ("china_stocks.html", "📈", "Stock Dashboard", "个股看板", str(cn_n) + " setups · screener", str(cn_n) + " 形态 · 筛选")],
        "HK": [("hk.html", "📊", "Macro Dashboard", "宏观看板", "Regime · risk overlay", "周期 · 风险叠加"),
               ("hk_stocks.html", "📈", "Stock Dashboard", "个股看板", str(hk_n) + " beta exposures", str(hk_n) + " 个 beta 敞口")],
        "CA": [("canada.html", "📊", "Macro Dashboard", "宏观看板", "Regime · CAD overlay", "周期 · 加元叠加"),
               ("canada_stocks.html", "📈", "Stock Dashboard", "个股看板", "TSX names & sectors", "TSX 个股与板块")],
    }
    cls = {"US": "us", "CN": "cn", "HK": "hk", "CA": "ca"}
    nm = {"US": ("United States", "美国"), "CN": ("China", "中国"), "HK": ("Hong Kong", "香港"), "CA": ("Canada · TSX", "加拿大 · TSX")}
    cards = []
    for cc in ("US", "CN", "HK", "CA"):
        m = by[cc]
        btns = []
        for href, ic, ten, tzh, sen, szh in SUB[cc]:
            btns.append('<a class="splitbtn" href="' + href + '"><span class="sb-ic" aria-hidden="true">' + ic + '</span>'
                        '<span class="sb-tx"><b>' + _bi(ten, tzh) + '</b><em>' + _bi(sen, szh) + '</em></span>'
                        '<span class="sb-go" aria-hidden="true">→</span></a>')
        cards.append('<div class="glass acc card ' + cls[cc] + '">'
                     '<div class="card-top"><span class="ico" aria-hidden="true">' + m["flag"] + '</span>'
                     '<h3 class="card-h">' + _bi(*nm[cc]) + '</h3>'
                     '<span class="pill ' + m["quad"] + ' hd">' + _bi(m["quad_name_en"], m["quad_name_zh"]) + '</span></div>'
                     '<div class="split">' + "".join(btns) + '</div></div>')
    return ('<div class="band"><h2>' + _bi("Markets", "市场") + '</h2><span class="ln"></span></div>'
            '<div class="nav mk reveal">' + "".join(cards) + '</div>')


def _g_vectors(vm, commodities, forex, bonds, crossasset, etf, strategies, watchlist):
    risk_cls = "on" if vm["risk_on"] else "off"
    mom_cls = "neg" if (vm.get("momentum") is not None and vm["momentum"] < 0) else ""
    fav = ", ".join((commodities or {}).get("favored", []))
    b_score = (bonds or {}).get("score")
    b_phase = (bonds or {}).get("phase") or ""
    fx_risk = (forex or {}).get("risk", "")
    ca_corr = (crossasset or {}).get("correlation", "")
    n_strat = (strategies or {}).get("n", 0)

    def card(cls, ic, h_en, h_zh, body, go_en, go_zh, href):
        return ('<a class="glass acc card ' + cls + '" href="' + href + '">'
                '<div class="card-top"><span class="ico" aria-hidden="true">' + ic + '</span>'
                '<h3 class="card-h">' + _bi(h_en, h_zh) + '</h3></div>' + body
                + '<span class="go">' + _bi(go_en, go_zh) + '</span></a>')

    btc = ('<div class="bar b-risk"><i style="width:' + str(vm["risk_index"]) + '%"></i></div>'
           '<div class="chips"><span class="pill ' + risk_cls + '">' + _bi("Risk " + vm["risk_word"] + " · " + str(vm["risk_index"]),
           "风险" + ("开启" if vm["risk_on"] else "关闭") + " · " + str(vm["risk_index"]))
           + '</span><span class="pill ' + mom_cls + '">' + _bi("Mom " + str(vm["momentum"]), "动量 " + str(vm["momentum"])) + '</span></div>')
    bd_bar = ('<div class="bar b-health"><i style="width:' + str(b_score) + '%"></i></div>') if b_score is not None else ""
    bd_pill = (_bi("Health " + str(b_score) + " · " + (b_phase or "late"), "健康 " + str(b_score) + " · " + ("晚期" if str(b_phase).startswith("late") else b_phase))) if b_score is not None else _bi("Bond health", "债券健康")
    bd = bd_bar + '<div class="chips"><span class="pill">' + bd_pill + '</span></div>'
    com_q = _quad_cls(name=(commodities or {}).get("label", "")) if "_quad_cls" in globals() else ""
    com = ('<div class="chips"><span class="pill ' + com_q + '">' + _bi((commodities or {}).get("label", "—"), (commodities or {}).get("label", "—"))
           + '</span>' + ('<span class="pill">' + _bi("Favored: " + fav, "偏好：" + fav) + '</span>' if fav else "") + '</div>')
    fx = '<div class="chips"><span class="pill">' + _bi((forex or {}).get("label", "—") + ((" · " + fx_risk) if fx_risk else ""), (forex or {}).get("label", "—") + ((" · " + fx_risk) if fx_risk else "")) + '</span></div>'
    xa = '<div class="chips"><span class="pill">' + _bi((crossasset or {}).get("regime", "—") + ((" · " + ca_corr) if ca_corr else ""), (crossasset or {}).get("regime", "—") + ((" · " + ca_corr) if ca_corr else "")) + '</span></div>'
    etfc = '<div class="chips"><span class="pill">' + _bi("Manager & index flows", "经理人与指数资金流") + '</span></div>'
    strc = '<div class="chips"><span class="pill">' + _bi(str(n_strat) + " strategies", str(n_strat) + " 个策略") + '</span></div>'
    wlc = '<div class="chips"><span class="pill">' + _bi("Your holdings", "你的持仓") + '</span></div>'
    cards = [
        card("btc", "₿", "Bitcoin Vector", "比特币向量", btc, "Risk, momentum & allocation", "风险、动量与配置", "vector.html"),
        card("bd", "🏛️", "Bonds & Bond Health", "债券与债券健康", bd, "Curve, credit & cycle clock", "曲线、信用与周期时钟", "bonds.html"),
        card("com", "◆", "Commodity Vector", "大宗商品向量", com, "Allocation & shock detection", "配置与冲击检测", "commodities.html"),
        card("fx", "💱", "Forex Vector", "外汇向量", fx, "Dollar-smile currency board", "美元微笑货币面板", "forex.html"),
        card("xa", "🧭", "Cross-Asset", "跨资产", xa, "Trend & correlation regime", "趋势与相关性体制", "crossasset.html"),
        card("etf", "🐋", "ETF Flow Radar", "ETF 资金雷达", etfc, "Accumulation & trims", "增持与减持", "etfs.html"),
        card("str", "🎛️", "Strategy Scorecards", "策略记分卡", strc, "Macro-factor tactical strategies", "宏观因子战术策略", "strategies.html"),
        card("wl", "📋", "Watchlist", "持仓清单", wlc, "Track holdings with live signals", "跟踪持仓与实时信号", "watchlist.html"),
    ]
    return ('<div class="band"><h2>' + _bi("Vectors & strategies", "向量与策略") + '</h2><span class="ln"></span></div>'
            '<div class="nav vc reveal">' + "".join(cards) + '</div>')


def _g_alerts(alerts):
    try:
        from engine.i18n import t as T
    except Exception:  # noqa: BLE001
        def T(en, zh=""):
            return en
    n = len(alerts)
    head = ('<div class="band"><h2>' + _bi("What changed", "近期变化") + '</h2><span class="ln"></span>'
            '<span class="cnt">' + _bi(str(n) + " signals", str(n) + " 条信号") + '</span></div>')
    if not alerts:
        rows = '<div class="ha-empty">' + str(T("No major alerts right now.", "目前没有重大警报。")) + '</div>'
    else:
        now = pd.Timestamp.utcnow().tz_localize(None)
        out = []
        for a in alerts[:5]:
            ts = pd.Timestamp(a["ts"])
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
            days = (now.normalize() - ts.normalize()).days
            when = "today" if days <= 0 else (str(days) + "d")
            when_zh = "今天" if days <= 0 else (str(days) + "天")
            sev = a["severity"]; dot = sev if sev in ("high", "medium") else "info"
            src_cls = {"macro": "s-macro", "vector": "s-vector", "commodity": "s-commodity"}.get(a["source"], "s-vector")
            src = str(T(a["source_label"], a.get("source_label_zh") or a["source_label"]))
            head_t = str(T(a["headline"], a.get("headline_zh") or a["headline"]))
            detail = str(T(a["detail"], a.get("detail_zh") or a["detail"]))
            cta = str(T(a.get("cta", "Open →"), a.get("cta_zh") or a.get("cta", "Open →")))
            out.append('<details class="ha-item"><summary><span class="ha-dot d-' + dot + '"></span>'
                       '<span class="ha-src ' + src_cls + '">' + src + '</span>'
                       '<span class="ha-head">' + head_t + '</span>'
                       '<span class="ha-when">' + _bi(when, when_zh) + '</span></summary>'
                       '<div class="ha-detail">' + detail + ' <a href="' + a["link"] + '">' + cta + '</a></div></details>')
        out.append('<a class="al-more" href="vector.html#timeline">' + _bi("View full timeline →", "查看完整时间线 →") + '</a>')
        rows = "".join(out)
    return head + '<section class="alerts reveal" id="alerts"><div class="glass al-card">' + rows + '</div></section>'


def _hub_alert_rows(alerts):  # retained name for back-compat; delegates to the compact strip
    return _g_alerts(alerts)


def _hub_html(vm: dict, macro: dict, alerts: list, china: dict | None = None,
              commodities: dict | None = None, watchlist: dict | None = None,
              etf: dict | None = None, hk: dict | None = None,
              forex: dict | None = None, bonds: dict | None = None,
              us_stocks: dict | None = None,
              strategies: dict | None = None, crossasset: dict | None = None,
              china_stocks: dict | None = None, hk_stocks: dict | None = None,
              canada: dict | None = None,
              intl: dict | None = None, ipo: dict | None = None, spr: dict | None = None,
              **_ignored) -> str:
    """The AURORA globe flight-deck landing hub. intl/ipo/spr (+ any future state)
    are accepted-and-ignored: build_landing still passes them, so the signature must
    absorb them or every daily build crashes (TypeError)."""
    built = vm["built"]
    blob = _globe_markets()
    us_n = (us_stocks or {}).get("n_setups") or 0
    cn_n = (china_stocks or {}).get("n_setups") or 0
    hk_n = (hk_stocks or {}).get("n_setups") or 0
    legend = _g_legend(blob)
    globe_deck = _GLOBE_DECK_DOM.replace("__LEGEND__", legend)
    markets = _g_markets(blob, us_n, cn_n, hk_n)
    vectors = _g_vectors(vm, commodities, forex, bonds, crossasset, etf, strategies, watchlist)
    alerts_html = _g_alerts(alerts)
    blob_json = json.dumps(blob, ensure_ascii=False)

    head = (HUB_MARKER + "\n"
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>Market Intelligence</title>\n'
            "<script>try{var h=new Date().getHours(),tod=(h>=7&&h<19)?'light':'dark',t=localStorage.getItem('theme'),a=localStorage.getItem('themeAuto');if(!t||a){t=tod;localStorage.setItem('theme',t);localStorage.setItem('themeAuto','1');}document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('lang');if(l)document.documentElement.setAttribute('data-lang',l);}catch(e){}</script>\n"
            '<link rel="stylesheet" href="theme.css">\n'
            '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">\n'
            + _GLOBE_HUB_CSS + "</head><body>")

    body = (
        '<div id="sky" aria-hidden="true"><canvas id="sky-stars"></canvas><div id="sky-sun"></div><div id="sky-moon"></div></div>'
        '<div class="wrap">'
        '<div class="hub-top">'
        '<button class="theme-switch" aria-label="Toggle dark / light mode"><span class="ic sun">☀️</span><span class="ic moon">🌙</span><span class="knob"></span></button>'
        '<div class="lang-toggle" role="group" aria-label="Language"><span class="pill"></span><span class="opt en-opt" data-l="en">EN</span><span class="opt zh-opt" data-l="zh">中文</span></div>'
        '</div>'
        '<header class="h"><span class="eyebrow"><span class="live"></span>'
        + _bi("Live · zero-cost data engine · updated " + built, "实时 · 零成本数据引擎 · 更新于 " + built)
        + '</span><h1>' + _bi("Market Intelligence", "市场情报") + '</h1>'
        '<p>' + _bi("Regime dashboards across every major asset class — one mechanical, backtested engine.",
                    "覆盖各大类资产的市场周期仪表盘——一套机械化、经回测的引擎。") + '</p></header>'
        '<div class="band"><h2>' + _bi("Global macro regime", "全球宏观周期") + '</h2><span class="ln"></span></div>'
        + globe_deck + markets + vectors + alerts_html
        + '<div class="foot">' + _bi("Built " + built + " · mechanical, backtested, free public data · not investment advice",
                                      "生成于 " + built + " · 机械化 · 经回测 · 免费公开数据 · 非投资建议") + '</div>'
        '<footer class="site-footer"><span class="made">' + _bi("Made with ❤️ in Canada", "用 ❤️ 在加拿大制作") + '</span>'
        '<span class="dev">' + _bi("Developed by Chris Wong", "开发者 Chris Wong") + '</span></footer>'
        '</div>'
        '<script id="globe-data" type="application/json">' + blob_json + '</script>'
        '<script defer src="vendor/d3-array.min.js"></script>'
        '<script defer src="vendor/d3-geo.min.js"></script>'
        '<script defer src="vendor/topojson-client.min.js"></script>'
        '<script defer src="globe-deck.js"></script>'
        '<script defer src="sky.js"></script>'
        '<script src="theme.js"></script>'
        '</body></html>'
    )
    return head + body



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


def _okx_ls_lean(z) -> str:
    """Contrarian retail-crowding label from the OKX long/short ACCOUNT-ratio z —
    DISPLAY-ONLY context with its OWN enum (NOT merged into the funding
    composite_context). z>1.5 ⇒ crowded_long (contrarian caution, not a buy);
    z<-1.5 ⇒ crowded_short (capitulation context); else balanced. Never sized."""
    if z is None or pd.isna(z):
        return "balanced"
    return "crowded_long" if z > 1.5 else "crowded_short" if z < -1.5 else "balanced"


def chart_ethbtc(ratio: pd.Series, ma: pd.Series | None, cfg: dict) -> str:
    d = _tail(ratio, 365 * 5)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=_dx(d.index), y=_plot_y(d, 4), name="ETH/BTC",
                             line={"color": C["blue"], "width": 1.6}))
    if ma is not None:
        fig.add_trace(go.Scatter(x=_dx(d.index), y=_plot_y(ma.reindex(d.index), 4), name="50w MA",
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
    # Reconcile with vector.html's headline OPTIMAL STRATEGY: TOTAL crypto exposure =
    # alloc_pct (the tactical risk gate, alloc_optimal); the alt-cycle grid only SPLITS
    # that budget across BTC/ETH/alts. So when the gate is shut (alloc_pct=0) this page
    # is 100% cash too — no more "100% cash here / 25% BTC there" incongruence.
    alloc_pct = round(100 * last["alloc_optimal"]) if pd.notna(last.get("alloc_optimal")) else 0
    _rs = grid["btc"] + grid["eth"] + grid["alts"]
    if _rs > 0 and alloc_pct > 0:
        _b = round(alloc_pct * grid["btc"] / _rs)
        _e = round(alloc_pct * grid["eth"] / _rs)
        _a = alloc_pct - _b - _e          # absorb rounding so crypto sums to alloc_pct
    else:
        _b = _e = _a = 0
    rec = {"btc": _b, "eth": _e, "alts": _a, "cash": 100 - alloc_pct,
           "regime_key": grid["regime_key"], "season_key": grid["season_key"]}
    pvm = {
        "as_of": sig.index.max().strftime("%b %d, %Y"),
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "price": close.iloc[-1],
        "grid": rec, "grid_full": grid, "regime": regime, "regime_label": lad.get("regime_label"),
        "regime_label_zh": lad.get("regime_label_zh"), "verdict": verdict,
        "alloc_pct": alloc_pct,
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


def vector_timeline(sig: pd.DataFrame, ladder: pd.DataFrame) -> dict:
    """Compact columnar JSON tape for the cycle time machine (vector_timemachine.js).
    Merges the per-day CAUSAL signals (already point-in-time in signals.parquet) with
    the backtested ladder state/regime (scripts/backtest_ladder_history.py). Starts
    where the ladder backtest is defined (~late-2015). Every value is what the
    dashboard would have shown that day — no look-ahead."""
    lad = ladder.reindex(sig.index)
    keep = lad["ladder_state"].notna()
    df, lad = sig[keep], lad[keep]
    # cycle_position 0..1 -> stage index 0..3 (Defensive/Fragile/Recovery/Expansion)
    stage = (df["cycle_position"].clip(0, 0.999).fillna(0.0) * 4).astype(int)

    def cat(s, default=""):
        return [default if pd.isna(v) else str(v) for v in s]

    def num(s, mul=1.0):
        return [None if pd.isna(v) else round(float(v) * mul) for v in s]

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "price": num(df["close"]),
        "phase": cat(df["cycle_phase"], "accumulation"),
        "cphase": cat(df["cphase_phase"], ""),   # bottom-anchored 1064/364 phase (PIT)
        "stage": [None if pd.isna(v) else int(v) for v in stage],
        "regime": cat(lad["regime"], "neutral"),
        "ladder": cat(lad["ladder_state"], ""),
        "mom": cat(df["momentum_state"], "neutral"),
        "val": cat(df["valuation_state"], "fair"),
        "extreme": cat(df["market_extreme"], "normal"),
        "composite": cat(df["composite_state"], "NEUTRAL"),
        "risk": num(df["risk_index"]),
        "alloc": num(df["alloc_optimal"], 100),
    }


def build_timeline(site: Path, sig: pd.DataFrame) -> None:
    """Refresh the ladder backtest cache (incremental) and write the time-machine tape."""
    from scripts import backtest_ladder_history as blh
    ladder = blh.update()                       # cheap after the first ~2-3min pass
    tape = vector_timeline(sig, ladder)
    blob = json.dumps(tape, separators=(",", ":"))
    (site / "vector_timeline.json").write_text(blob)
    log.info("wrote %s/vector_timeline.json (%d days, %d KB)", site, len(tape["dates"]), len(blob) // 1024)


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
    # ETF flows lag the price tape by a few days -> read the last row that HAS them
    _efl = sig[sig["etf_flow_sum"].notna()] if "etf_flow_sum" in sig.columns else sig.iloc[0:0]
    etf_last = _efl.iloc[-1] if len(_efl) else last
    etf_asof = _efl.index[-1].strftime("%b %-d") if len(_efl) else None
    px = _series("coinbase", "btc_daily")
    close = sig["close"]
    chg24 = round(100 * (close.iloc[-1] / close.iloc[-2] - 1), 2)

    eq = alloc_equity(close, sig["alloc_optimal"])
    hodl = (1 + close.pct_change().fillna(0)).cumprod()
    sizing = alloc_sizing(last, eq, config.load()["vector"]["allocation"])
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
    # forward-risk (the CONFIRMED quantity) — leads the cards; direction is secondary
    envd["risk"] = forward_risk(sig, 7)
    scnd["risk"] = forward_risk(sig, 3)
    sizing = kelly_sizing(sig, config.load()["vector"].get("sizing", {}))  # D-vec-KELLY
    try:
        catalyst = catalyst_window(datetime.now(timezone.utc), config.load()["vector"].get("catalyst", {}))
    except Exception as e:  # noqa: BLE001 — the calendar overlay must never break the build
        log.warning("catalyst window failed (%s)", e)
        catalyst = None

    # Crypto breadth / risk-appetite — consolidate the scattered ETH/BTC + dominance
    # reads (previously only on the allocation deep-dive) onto the overview, plus the
    # NEW SOL/ETH high-beta-appetite line. DISPLAY-ONLY; must never break the build.
    try:
        from engine import alt_cycle
        _acfg = config.load()["vector"]["alt_cycle"]
        _eth = _series("yahoo", "ETH-USD")
        _eb = alt_cycle.ethbtc_signal(_eth, close, _acfg)
        _se = alt_cycle.beta_ratio(_series("yahoo", "SOL-USD"), _eth, _acfg)
        _cg = store.read("coingecko", "global_market")
        _dom = float(_cg["btc_dominance_pct"].iloc[-1]) if _cg is not None and not _cg.empty else None
        _ethdom = float(_cg["eth_dominance_pct"].iloc[-1]) if _cg is not None and not _cg.empty else None
        _bscore, _bbucket = alt_cycle.alt_season_score(_eb, _dom, _acfg)
        breadth = alt_cycle.breadth_view(_eb, _se, _dom, _ethdom, _bscore, _bbucket)
    except Exception as e:  # noqa: BLE001 — breadth card is optional context
        log.warning("crypto breadth view failed (%s)", e)
        breadth = {}

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
        "alloc_sizing": sizing,
        # ---- accuracy-upgrade layers (Tier 1/1b/2) ----
        "composite_state": last.get("composite_state", "NEUTRAL"),
        "composite_context": last.get("composite_context", ""),
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
            # realized-vol cone + vol-of-vol (full history 2015->; D-vec-RVCONE)
            "rv_realized": _r(last.get("rv_realized"), 0),
            "rv_cone_pctile": _r(last.get("rv_cone_pctile"), 0),
            "vol_of_vol": _r(last.get("vol_of_vol"), 1),
            "vov_pctile": _r(last.get("vov_pctile"), 0),
            # dealer gamma-flip (zero-gamma spot) + distance-to-flip (D-vec-GAMMA)
            "gamma_flip": _r(last.get("gamma_flip"), 0),
            "dist_to_flip_pct": _r(last.get("dist_to_flip_pct"), 1),
            "gamma_regime": last.get("gamma_regime"),
        },
        "leverage": {
            "oi_total": _r(last.get("oi_total_usd"), 0),
            "oi_mcap_pctile": _r(last.get("oi_mcap_pctile"), 0),
            "funding_annual": _r(last.get("funding_annual_pct"), 1),
            "funding_z": _r(last.get("funding_z"), 1),
            # OKX rubik retail positioning — DISPLAY-ONLY context (never scored)
            "okx_ls_ratio": _r(last.get("okx_ls_ratio"), 2),
            "okx_ls_pctile": _r(last.get("okx_ls_ratio_pctile"), 0),
            "okx_ls_z": _r(last.get("okx_ls_ratio_z"), 1),
            "okx_taker_buy": _r(last.get("okx_taker_buy"), 3),
            "okx_taker_pctile": _r(last.get("okx_taker_buy_pctile"), 0),
            # neutral lean label computed server-side from the z (contrarian framing,
            # its own enum — NOT merged into the funding composite_context)
            "okx_ls_lean": _okx_ls_lean(last.get("okx_ls_ratio_z")),
            "oi_divergence": _r(100 * last["oi_price_divergence"], 1) if pd.notna(last.get("oi_price_divergence")) else None,
            "stress": _r(last.get("leverage_stress"), 0),
            # CME (regulated) basis — institutional carry context (D-vec-CME)
            "cme_basis": _r(last.get("cme_basis"), 2),
            "cme_basis_ann": _r(last.get("cme_basis_ann"), 0),
            "cme_basis_pctile": _r(last.get("cme_basis_pctile"), 0),
            "cme_basis_regime": last.get("cme_basis_regime"),
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
            # crypto-native liquidity TIDE: stablecoin supply growth (D-vec-STBL)
            "stbl_mcap_bn": _r(last.get("stbl_mcap_bn"), 0),
            "stbl_growth": _r(last.get("stbl_growth"), 1),
            "stbl_growth_z": _r(last.get("stbl_growth_z"), 1),
            "stbl_regime": last.get("stbl_regime"),
            # stablecoin PEG-deviation monitor (collateral solvency; D-vec-PEG)
            "peg_dev_bps": _r(last.get("peg_dev_bps"), 0),
            "peg_state": last.get("peg_state"),
        },
        "onchain": {
            "premium": _r(last.get("coinbase_premium_ema"), 2),
            "premium_hot": bool(pd.notna(last.get("coinbase_premium_ema")) and last["coinbase_premium_ema"] > 1.5),
            "ssr": _r(last.get("ssr"), 1),
            "ssr_osc": _r(last.get("ssr_oscillator"), 2),
            "mpi": _r(last.get("mpi"), 2),
        },
        "etf": {
            "state": etf_last.get("etf_flow_state"),
            "flow_z": _r(etf_last.get("etf_flow_z"), 2),
            "asof": etf_asof,
            "flow_5d_str": (f"{int(etf_last['etf_flow_sum']):+,} BTC"
                            if pd.notna(etf_last.get("etf_flow_sum")) else "—"),
            "daily_str": (f"${int(etf_last['etf_flow_usd_mn']):+,}M"
                          if pd.notna(etf_last.get("etf_flow_usd_mn")) else "—"),
            "cum_btc_str": (f"{int(etf_last['etf_flow_cum']):,} BTC"
                            if pd.notna(etf_last.get("etf_flow_cum")) else "—"),
            "cum_usd_bn": (_r(etf_last["etf_flow_cum"] * etf_last["close"] / 1e9, 1)
                           if pd.notna(etf_last.get("etf_flow_cum")) else None),
            "present": bool(len(_efl)),
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
        "cycle_phase": {     # bottom-anchored 1064/364 clock (the chart's theory)
            "phase": last.get("cphase_phase"),
            "pct": _r(100 * last["cphase_pct"], 0) if pd.notna(last.get("cphase_pct")) else None,
            "days_in": _r(last.get("cphase_days_in"), 0),
            "len": _r(last.get("cphase_len"), 0),
            "days_left": _r(last.get("cphase_days_left"), 0),
            "next_pivot": last.get("cphase_next_pivot"),
            "next_kind": last.get("cphase_next_kind"),
            "status": last.get("cphase_status"),
            "anchor": last.get("cphase_anchor_date"),
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
        "breadth": breadth,
        "env": envd,
        "scn": scnd,
        "sizing": sizing,
        "catalyst": catalyst,
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
            "etf_flow": chart_etf_flow(sig) if "etf_flow_btc" in sig.columns else "",
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
    # the AI brief panel fetches aibrief.js at runtime — ship it alongside the page
    # (build_site copies it too; done here so a standalone vector rebuild is complete).
    _ab = config.ROOT / "templates" / "aibrief.js"
    if _ab.exists():
        (site / "aibrief.js").write_text(_ab.read_text())
    try:
        build_allocation_page(env, site, sig, cards, mtf_a, verdict)
    except Exception as e:  # noqa: BLE001 — never let the sub-page break the main build
        log.error("allocation page failed (%s)", e)
    try:
        build_timeline(site, sig)
    except Exception as e:  # noqa: BLE001 — never let the time-machine tape break the build
        log.error("timeline tape failed (%s)", e)
    try:  # S&P / Macro Vector page + hub-card state (independent; never break the BTC build)
        from scripts.build_spvector import build as _build_spvector
        _build_spvector()
    except Exception as e:  # noqa: BLE001
        log.error("spvector page failed (%s)", e)
    try:  # Strategy Scorecards hub + per-strategy detail pages (+ data/regime/strategies_latest
          # .json for the umbrella hub card). No dedicated daily.yml step yet (PAT lacks
          # `workflow` scope), so it is built here, after build_spvector (its spvector card links
          # spvector.html) and before build_landing reads _strategies_state(). Never fatal.
        from scripts.build_strategies import build as _build_strategies
        _build_strategies()
    except Exception as e:  # noqa: BLE001
        log.error("strategies pages (via build_vector) failed (%s)", e)
    try:  # IPO Radar (display-only, never-scored) — no dedicated daily.yml step (PAT lacks
          # `workflow` scope), built here AFTER build_spvector (it reuses the validated
          # de-risk score from data/regime/spvector_latest.json) to render the standalone
          # ipo.html. Refreshes the Nasdaq IPO calendar best-effort; never fatal.
        from scripts.build_ipo import build as _build_ipo
        _build_ipo()
    except Exception as e:  # noqa: BLE001
        log.error("ipo radar page (via build_vector) failed (%s)", e)
    try:  # China Mastermind GTAA flagships — detail pages + snapshot. MUST run BEFORE
          # build_china_strategies so strategy_cnmm_*.html exist when the pinned hero links to them.
          # (PAT lacks workflow scope → piggyback on build_vector; promote to a daily.yml step later.)
        from scripts.build_china_masterminds import build as _build_china_masterminds
        _build_china_masterminds()
    except Exception as e:  # noqa: BLE001
        log.error("china mastermind flagship pages (via build_vector) failed (%s)", e)
    try:  # China Strategy Scorecards hub + detail pages (same hook rationale as the US hub;
          # the China Income Vector card pulls from build_china_allocation, so this runs after it).
        from scripts.build_china_strategies import build as _build_china_strategies
        _build_china_strategies()
    except Exception as e:  # noqa: BLE001
        log.error("china strategies pages (via build_vector) failed (%s)", e)
    try:  # Commodity Strategy Scorecards (per-commodity toggle grid) + detail pages.
        from scripts.build_commodity_strategies import build as _build_commodity_strategies
        _build_commodity_strategies()
    except Exception as e:  # noqa: BLE001
        log.error("commodity strategies pages (via build_vector) failed (%s)", e)
    try:  # Mastermind multi-asset GTAA flagship (3 risk profiles) + detail pages.
        from scripts.build_masterminds import build as _build_masterminds
        _build_masterminds()
    except Exception as e:  # noqa: BLE001
        log.error("mastermind pages (via build_vector) failed (%s)", e)
    try:  # Canada / S&P-TSX dashboard — has no dedicated daily.yml step yet (the PAT that
          # opened PR #81 lacked `workflow` scope), so it is built here, before the landing
          # hub reads _canada_state(). Self-sufficient + returns 0; never breaks the build.
          # TODO: move to a proper daily.yml/weekly.yml `build_canada` step + drop this hook
          # once a workflow-scoped token is available.
        from scripts import build_canada as _build_canada
        _build_canada.main()
    except Exception as e:  # noqa: BLE001
        log.error("canada dashboard (via build_vector) failed (%s)", e)
    try:  # International comparative dashboard (JP/KR/TW/UK/EU) — same hook pattern as
          # build_canada (PAT lacks `workflow` scope for a dedicated daily.yml step), built
          # here to render the standalone intl.html. Self-sufficient + returns 0.
          # TODO: promote to a proper daily.yml `build_intl` step once a workflow token exists.
        from scripts import build_intl as _build_intl
        _build_intl.main()
    except Exception as e:  # noqa: BLE001
        log.error("international dashboard (via build_vector) failed (%s)", e)
    try:  # China A-share thematic baskets page — like build_canada, no dedicated daily.yml
          # step yet (PAT lacks `workflow` scope), so it is built here off the china_search
          # cache that the collectors already refresh. Self-sufficient + returns 0; additive.
          # TODO: promote to a proper daily.yml `build_baskets_china` step beside build_baskets.
        from scripts import build_baskets_china as _build_baskets_china
        _build_baskets_china.main()
    except Exception as e:  # noqa: BLE001
        log.error("china baskets (via build_vector) failed (%s)", e)
    try:  # Hong Kong thematic baskets page — same pattern, off the hk_search cache.
        from scripts import build_baskets_hk as _build_baskets_hk
        _build_baskets_hk.main()
    except Exception as e:  # noqa: BLE001
        log.error("hk baskets (via build_vector) failed (%s)", e)
    try:  # Canada / S&P-TSX thematic baskets page — same pattern, off the canada_search cache.
        from scripts import build_baskets_canada as _build_baskets_canada
        _build_baskets_canada.main()
    except Exception as e:  # noqa: BLE001
        log.error("canada baskets (via build_vector) failed (%s)", e)
    build_landing(site, vm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
