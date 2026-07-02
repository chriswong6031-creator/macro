"""Build the BTC Strategy page -> site/btc_strategy.html

A selectable scorecard page comparing Bitcoin allocation strategies. Two cores:
  • BTC Cycle Timer Strategy — a proprietary multi-year cycle timer. Long (optionally
    levered) from each projected cycle bottom through the projected up-phase, then flat
    through the down-phase, repeat. Pivots are CHAINED walk-forward from the first known
    bottom by fixed (internal) day-counts — NOT hindsight-placed. The exact day-counts are
    proprietary and are NOT surfaced on the page.
  • BTC Risk Allocation Strategy — trend (200D) + risk-throttle (350D stretch) managed
    exposure; stays invested in uptrends, de-risks at extremes, exits downtrends.
Both also stand aside through US midterm-election years until ~the vote (the same gate the
live Bitcoin Vector allocation uses, engine.btc_signals.midterm_blackout).

Everything is backtested on real daily BTC closes (engine.btc_inputs.load_price, Coinbase
spliced with Yahoo for the 2014-15 tail). Equity curves are rendered as self-contained
inline SVG (log scale) so the page has no external chart dependency.

Usage:  python -m scripts.build_btc_strategy
"""
from __future__ import annotations

import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_btc_strategy")

BULL_DAYS = 1064          # 152 weeks, trough -> peak
BEAR_DAYS = 364           # 52 weeks, peak -> trough
SEED_BOTTOM = "2015-01-14"  # first known cycle bottom in the data (walk-forward anchor)
COST_BPS = 10.0           # one-way transaction cost on each allocation change
BORROW_APR = 0.10         # annual borrow cost charged on the leveraged portion (L-1)


# ----------------------------------------------------------------------------- data
def load_close() -> pd.Series:
    try:
        from engine import btc_inputs
        s = btc_inputs.load_price()["close"].dropna()
    except Exception as e:  # pragma: no cover - fallback paths
        log.warning("btc_inputs.load_price failed (%s); falling back to store", e)
        from lib import store
        try:
            s = store.read("coinbase", "btc_daily")["close"].dropna()
        except Exception:
            s = store.read("yahoo", "BTC-USD")["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated()].sort_index()


# ------------------------------------------------------------------------- pivots
def cycle_pivots(start=SEED_BOTTOM, n=12):
    """Chained schedule of (date, kind) from the seed bottom: bottom, top, bottom..."""
    out = [(pd.Timestamp(start), "bottom")]
    cur, is_bottom = pd.Timestamp(start), True
    for _ in range(n):
        cur = cur + pd.Timedelta(days=BULL_DAYS if is_bottom else BEAR_DAYS)
        out.append((cur, "top" if is_bottom else "bottom"))
        is_bottom = not is_bottom
    return out


def cycle_alloc(close: pd.Series, pivots) -> pd.Series:
    """1.0 while holding (bottom -> top), 0.0 while waiting (top -> bottom)."""
    a = pd.Series(0.0, index=close.index)
    for (d0, k0), (d1, _k1) in zip(pivots[:-1], pivots[1:]):
        if k0 == "bottom":
            a[(close.index >= d0) & (close.index < d1)] = 1.0
    return a


def risk_alloc(close: pd.Series) -> pd.Series:
    """Trend (200D) + risk-throttle (350D stretch) managed exposure."""
    sma200 = close.rolling(200).mean()
    sma350 = close.rolling(350).mean()
    trend_on = close > sma200
    expo = pd.Series(
        np.where(close < sma350 * 2.0, 1.0, np.where(close < sma350 * 3.5, 0.6, 0.3)),
        index=close.index,
    )
    return expo.where(trend_on, 0.0).fillna(0.0)


# -------------------------------------------------------------------- simulation
def simulate(close: pd.Series, alloc: pd.Series, lev=1.0, borrow_apr=0.0, cost_bps=COST_BPS):
    """Equity curve with leverage, daily borrow drag on (L-1), turnover cost and
    margin liquidation (position equity hitting zero) modelled honestly."""
    ret = close.pct_change().fillna(0.0).to_numpy()
    pos = alloc.shift(1).fillna(0.0).to_numpy()
    e, prev, liq = 1.0, 0.0, False
    db = borrow_apr / 365.0
    out = np.empty(len(ret))
    for i in range(len(ret)):
        p = pos[i]
        if p != prev:
            e *= 1.0 - abs(p - prev) * cost_bps / 1e4
            if p > 0 and prev == 0:
                liq = False                       # fresh entry resets the margin clock
        if p > 0 and not liq:
            lr = lev * ret[i] - (lev - 1.0) * db
            if (1.0 + lr) <= 0:                   # wiped out -> liquidated for this hold
                e, liq = 0.0, True
            else:
                e *= 1.0 + lr
        prev = p
        out[i] = e
    return pd.Series(out, index=close.index)


def metrics(eq: pd.Series, alloc: pd.Series) -> dict:
    r = eq.pct_change().fillna(0.0)
    yrs = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total = float(eq.iloc[-1])
    cagr = (total ** (1.0 / yrs) - 1.0) if total > 0 else -1.0
    sharpe = float(r.mean() / r.std() * math.sqrt(365)) if r.std() > 0 else 0.0
    maxdd = float((eq / eq.cummax() - 1.0).min())
    calmar = (cagr / abs(maxdd)) if maxdd < 0 else float("nan")
    return {
        "total": total,
        "cagr": cagr * 100.0,
        "sharpe": sharpe,
        "maxdd": maxdd * 100.0,
        "calmar": calmar,
        "timein": float((alloc > 0).mean() * 100.0),
    }


# -------------------------------------------------------------------------- chart
def equity_svg(dates, series: dict, w=920, h=320, pad=46):
    """Self-contained inline SVG, log-scaled. `series` = {label: (values, color)}."""
    allv = [v for vals, _ in series.values() for v in vals if v and v > 0]
    lo, hi = min(allv), max(allv)
    llo, lhi = math.log10(lo), math.log10(hi)
    span = max(lhi - llo, 1e-9)
    n = len(dates)

    def xx(i):
        return pad + i / max(n - 1, 1) * (w - pad - 12)

    def yy(v):
        v = max(v, lo)
        return h - pad - (math.log10(v) - llo) / span * (h - 2 * pad)

    parts = [f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
             f'style="width:100%;height:{h}px" xmlns="http://www.w3.org/2000/svg">']
    # log gridlines at powers of 10
    p0, p1 = math.ceil(llo), math.floor(lhi)
    for p in range(int(p0), int(p1) + 1):
        y = yy(10 ** p)
        parts.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{w-12}" y2="{y:.1f}" '
                     f'stroke="var(--line)" stroke-width="1" opacity="0.6"/>')
        lab = f"{10**p:,.0f}×" if p >= 0 else f"{10**p:g}×"
        parts.append(f'<text x="6" y="{y-3:.1f}" font-size="10" fill="var(--muted)">{lab}</text>')
    # year ticks
    yrs = pd.to_datetime(dates).year
    last = None
    for i, yr in enumerate(yrs):
        if yr != last and yr % 2 == 1:
            parts.append(f'<text x="{xx(i):.1f}" y="{h-6}" font-size="10" '
                         f'fill="var(--muted)" text-anchor="middle">{yr}</text>')
            last = yr
    # polylines
    for label, (vals, color) in series.items():
        pts = " ".join(f"{xx(i):.1f},{yy(v):.1f}" for i, v in enumerate(vals) if v and v > 0)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                     f'stroke-width="2" stroke-linejoin="round"/>')
    parts.append("</svg>")
    return "".join(parts)


def downsample(eq: pd.Series, k=240):
    if len(eq) <= k:
        return list(eq.index), list(eq.to_numpy())
    idx = np.linspace(0, len(eq) - 1, k).astype(int)
    return list(eq.index[idx]), list(eq.to_numpy()[idx])


# --------------------------------------------------------------------------- build
def main():
    close = load_close()
    log.info("BTC close %s..%s  n=%d", close.index.min().date(), close.index.max().date(), len(close))
    pivots = cycle_pivots()
    a_cycle = cycle_alloc(close, pivots)
    a_risk = risk_alloc(close)

    # House rule (mirrors the live Bitcoin Vector allocation): stand aside through US
    # midterm-election years until ~the vote — historically the worst window for BTC. Reuse
    # the SAME gate the Vector uses so the page and the live engine agree. (For the cycle
    # timer this is ~a no-op — its down-phase already brackets the midterms — but it adds a
    # real dodge to the trend/risk strategy.)
    gate_live = {"active": False}   # W3: the ONE stamped gated-state flag (display side)
    try:
        from engine.btc_signals import gate_state, midterm_blackout
        from lib import config
        mg = (config.load().get("vector", {}).get("allocation", {}) or {}).get("midterm_gate") \
            or {"enabled": True}
        gate = midterm_blackout(close.index, mg)
        a_cycle = a_cycle.where(~gate, 0.0)
        a_risk = a_risk.where(~gate, 0.0)
        gate_live = gate_state(close.index[-1], mg)
        log.info("midterm-election blackout active on %d days", int(gate.sum()))
    except Exception as e:  # pragma: no cover - never break the page over the overlay
        log.warning("midterm blackout overlay skipped (%s)", e)

    hodl = (1 + close.pct_change().fillna(0)).cumprod()
    eq_cycle = simulate(close, a_cycle, lev=1.0, borrow_apr=0.0)
    eq_risk = simulate(close, a_risk, lev=1.0, borrow_apr=0.0)

    m_hodl = metrics(hodl, pd.Series(1.0, index=close.index))
    m_cycle = metrics(eq_cycle, a_cycle)
    m_risk = metrics(eq_risk, a_risk)

    # leverage variants for the cycle strategy (honest: borrow drag + liquidation)
    lev_rows = []
    for L in (1, 2, 3):
        eqL = simulate(close, a_cycle, lev=float(L), borrow_apr=BORROW_APR)
        mL = metrics(eqL, a_cycle)
        note = "liquidated → $0" if mL["total"] <= 1e-6 else ("survives" if L < 3 else "")
        lev_rows.append({"lev": L, "total": mL["total"], "cagr": mL["cagr"],
                         "maxdd": mL["maxdd"], "note": note,
                         "blown": mL["total"] <= 1e-6})

    # equity-curve SVGs (strategy vs HODL)
    d_c, v_c = downsample(eq_cycle)
    _, vh_c = downsample(hodl)
    svg_cycle = equity_svg(d_c, {"4Y Cycle": (v_c, "#f2a900"), "Buy & Hold": (vh_c, "var(--muted)")})
    d_r, v_r = downsample(eq_risk)
    _, vh_r = downsample(hodl)
    svg_risk = equity_svg(d_r, {"Risk Alloc": (v_r, "#5aa7ff"), "Buy & Hold": (vh_r, "var(--muted)")})

    # current cycle phase
    today = close.index[-1]
    prev = [p for p in pivots if p[0] <= today][-1]
    nxt = [p for p in pivots if p[0] > today][0]
    is_bull = prev[1] == "bottom"
    span_days = (nxt[0] - prev[0]).days
    days_in = (today - prev[0]).days
    days_to = (nxt[0] - today).days
    phase = {
        "state": "BULL" if is_bull else "BEAR",
        "pct": round(min(max(days_in / span_days, 0), 1) * 100),
        "days_in": days_in,
        "next_kind": "Top" if nxt[1] == "top" else "Bottom",
        "next_date": nxt[0].strftime("%b %Y"),
        "days_to": days_to,
        "months_to": round(days_to / 30.4, 1),
    }

    # realized pivot table (price at each chained pivot date, if in range)
    piv_rows = []
    for d, k in pivots:
        if d < close.index.min() - pd.Timedelta(days=5):
            continue
        if d > today + pd.Timedelta(days=500):
            break
        pos = close.index.searchsorted(min(d, close.index[-1]))
        pos = min(pos, len(close) - 1)
        price = float(close.iloc[pos]) if d <= today else None
        piv_rows.append({
            "date": d.strftime("%b %Y"),
            "kind": "bottom" if k == "bottom" else "top",
            "is_bottom": k == "bottom",
            "price": price,
            "future": d > today,
        })

    strategies = [
        {
            "id": "cycle",
            "name": "BTC Cycle Timer Strategy",
            "tag": "Proprietary timing",
            "thesis": ("Our proprietary multi-year cycle timer: go fully risk-on at each projected "
                       "cycle bottom, ride the up-phase to the projected top, then sit in cash through "
                       "the down-phase and re-enter at the next projected bottom. The down-phase has "
                       "historically bottomed into the US midterm elections — the post-election fiscal "
                       "impulse throws off inflation the Fed tightens into ~18–24 months later, with BTC "
                       "capitulating in the trough — so the timer is in cash through midterm years until "
                       "the vote. The exact timing model is proprietary."),
            "metrics": m_cycle,
            "vs": {kk: m_cycle[kk] - m_hodl[kk] for kk in ("cagr", "sharpe", "maxdd")},
            "svg": svg_cycle,
            "rules": [
                "Anchor on a confirmed cycle bottom; the timer projects every pivot forward.",
                "At a projected bottom: allocate 100% (optionally leveraged).",
                "Hold through the projected up-phase to the projected top — no mid-cycle trimming.",
                "At the top: sell to cash and sit out the projected down-phase (it bottoms into the US midterms).",
                "Re-enter at the next projected bottom. Repeat.",
            ],
            "leverage": lev_rows,
            "pivots": piv_rows,
            "caveats": [
                "Walk-forward, but seeded from one known bottom and only a few completed cycles — small sample, high overfitting risk.",
                "Holds through brutal mid-cycle drawdowns (≈ −62% even unlevered, e.g. the 2021 −55% crash).",
                "Leverage is dangerous: 2× ran a −94% drawdown; 3× was LIQUIDATED to $0 by a single ~−37% day (the Mar-2020 COVID crash). Borrow cost (~10%/yr) is included.",
                "The cycle is a historical regularity, not a law — ETF/institutional flows may stretch it.",
            ],
        },
        {
            "id": "risk",
            "name": "BTC Risk Allocation Strategy",
            "tag": "Risk-managed",
            "thesis": ("Stay invested while the trend is intact and value is reasonable, de-risk as price "
                       "stretches above its long-term mean, and step aside when the trend breaks. Exposure "
                       "is scaled by a 200-day trend filter and a 350-day stretch throttle rather than by "
                       "calendar timing — and, reflecting the house view, it stands aside through US "
                       "midterm-election years until the vote, the period that has been hardest on BTC."),
            "metrics": m_risk,
            "vs": {kk: m_risk[kk] - m_hodl[kk] for kk in ("cagr", "sharpe", "maxdd")},
            "svg": svg_risk,
            "rules": [
                "Trend gate: invested only while price > 200-day SMA.",
                "Risk throttle: 100% when price < 2× the 350-day SMA…",
                "…60% when 2–3.5×, 30% when > 3.5× (overheated).",
                "Flat when the 200-day trend breaks down.",
                "Stand aside (cash) through US midterm-election years until ~election day.",
            ],
            "leverage": None,
            "pivots": None,
            "caveats": [
                "Trend-following: gives back part of every top and re-enters late after bottoms.",
                "Parameters (200/350-day, 2×/3.5×) are sensible but not exhaustively tuned.",
                "The midterm-election blackout is a deterministic calendar rule on only a few cycles of history.",
            ],
        },
    ]

    ctx = {
        "as_of": today.strftime("%b %d, %Y"),
        "btc_price": float(close.iloc[-1]),
        "btc_chg": float(close.pct_change().iloc[-1] * 100),
        "phase": phase,
        "hodl": m_hodl,
        "strategies": strategies,
        # W3 (Override-Registry N6): the ONE stamped gated-state flag — any live gate copy
        # this template family ever shows must read ctx.gate, never re-derive the window.
        "gate": gate_live,
    }

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      trim_blocks=True, lstrip_blocks=True, autoescape=False)
    try:                                       # _navlinks references t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("btc_strategy.html.j2").render(**ctx)
    out = ROOT / "site" / "btc_strategy.html"
    out.write_text(html, encoding="utf-8")
    log.info("Built %s  (%.0f KB)", out, out.stat().st_size / 1024)


if __name__ == "__main__":
    main()
