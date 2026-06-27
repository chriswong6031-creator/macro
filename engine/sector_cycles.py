"""Sector Cycle Intelligence — data-driven cycle map for the 11 US sector ETFs.

Sister engine to the hand-authored Cycle Intelligence page (cycle_data.js): where
that page curates a dozen macro cycles by hand, THIS one derives each US GICS
sector ETF's cycle ENTIRELY from its real price tape, so the chart shows true
price (not a stylised oscillator) and the turning points / phase / projection are
reproducible from data.

For each sector ETF it emits, over a rolling ~6-year window:
  • a rebased-to-100 weekly PRICE series (the default "true chart line"), and a
    0–100 cycle-POSITION oscillator (the toggle view) — both on one shared axis so
    every sector overlays cleanly;
  • the confirmed historical PEAKS / TROUGHS (significant swings, alternating), each
    a slot a researched narrative can later bind to;
  • the CURRENT phase via engine.cycles.analyze() (the same 8-state ladder the rest
    of the site uses) mapped onto the 5-phase taxonomy the cycle page already paints
    (Trough/Recovery/Expansion/Peak/Downturn = bottoming/early/expanding/topping/rolling);
  • a NEXT-turn projection from the sector's own median half-cycle length;
  • a relative-strength leadership read vs SPY (which sectors lead / lag).

The output JSON is the single source of truth for scripts/build_sector_cycles.py →
site/sector_cycles.html. Narratives are layered in from data/sector_cycles/
narratives.json (researched against the dated turns this engine surfaces).

Pure-read + additive: any failure on one sector is logged and skipped, never fatal.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import cycles
from engine.inputs import yahoo_closes
from lib import config

log = logging.getLogger(__name__)

# ── sector metadata ─────────────────────────────────────────────────────────
# name = GICS sector; group = cyclical nature (drives the cross-sector grouping);
# accent = a distinct, dark-bg-legible hue per line (no two adjacent in the wheel).
SECTORS: dict[str, dict] = {
    "XLK":  {"name": "Technology",             "short": "Tech",        "group": "Growth",    "accent": "#38bdf8"},
    "XLC":  {"name": "Communication Services",  "short": "Comm",        "group": "Growth",    "accent": "#818cf8"},
    "XLY":  {"name": "Consumer Discretionary",  "short": "Discretionary","group": "Cyclical", "accent": "#f472b6"},
    "XLF":  {"name": "Financials",              "short": "Financials",  "group": "Cyclical",  "accent": "#34d399"},
    "XLI":  {"name": "Industrials",             "short": "Industrials", "group": "Cyclical",  "accent": "#fbbf24"},
    "XLB":  {"name": "Materials",               "short": "Materials",   "group": "Cyclical",  "accent": "#a3e635"},
    "XLE":  {"name": "Energy",                  "short": "Energy",      "group": "Cyclical",  "accent": "#fb923c"},
    "XLV":  {"name": "Health Care",             "short": "Health",      "group": "Defensive", "accent": "#2dd4bf"},
    "XLP":  {"name": "Consumer Staples",        "short": "Staples",     "group": "Defensive", "accent": "#94a3b8"},
    "XLU":  {"name": "Utilities",               "short": "Utilities",   "group": "Defensive", "accent": "#c084fc"},
    "XLRE": {"name": "Real Estate",             "short": "Real Estate", "group": "Rate-sens", "accent": "#f87171"},
}

# Phase taxonomy — identical hues/labels to site/cycle_data.js CYCLE_PHASES so this
# page reads the same as Cycle Intelligence. Internal ladder states fold into these.
# cool -> warm cycle wheel: bottoming (cold/cheap) -> prime entry (turning) ->
# trending (healthy) -> topping (hot) -> rolling over (declining).
PHASES = {
    "Trough":    {"label": "Trough",    "short": "Bottoming",    "hue": "#5b9bf0"},
    "Recovery":  {"label": "Recovery",  "short": "Prime entry",  "hue": "#2dd4bf"},
    "Expansion": {"label": "Expansion", "short": "Trending",     "hue": "#45b873"},
    "Peak":      {"label": "Peak",      "short": "Topping",      "hue": "#e0a030"},
    "Downturn":  {"label": "Downturn",  "short": "Rolling over", "hue": "#e0556b"},
}

WINDOW_YEARS = 6
_TODAY_PAD = 0.30          # forward x-headroom (yrs) for the projection leg
_ZZ_PCT = 14.0            # ZigZag reversal threshold — a sector "major" swing (intermediate cycle)
_MAJOR_PCT = 20.0         # legs this big get a "major" flag (prioritised for narration)


def _yf(ts: pd.Timestamp) -> float:
    """Decimal year (day-precision), matching the cycle page's x-axis convention."""
    return ts.year + (ts.dayofyear - 1) / 365.25


def _detrended_osc(close: pd.Series, trend: int = 252, win: int = 252,
                   smooth: int = 10) -> pd.Series:
    """0–100 cycle-position oscillator: where price sits within its own DETRENDED
    cyclical range. Detrend by a long EMA (so a secular uptrend doesn't pin it at
    100), then stochastic-normalise the detrended ratio over `win`, lightly smoothed.
    100 = stretched above trend (late/expensive), 0 = washed out below (cheap)."""
    c = close.dropna()
    dt = (c / c.ewm(span=trend, min_periods=trend // 2).mean()).ewm(span=smooth).mean()
    lo = dt.rolling(win, min_periods=win // 3).min()
    hi = dt.rolling(win, min_periods=win // 3).max()
    osc = 100.0 * (dt - lo) / (hi - lo).replace(0, np.nan)
    return osc.ewm(span=smooth).mean().clip(0, 100)


def _detect_swings(close: pd.Series, pct: float = _ZZ_PCT) -> list[dict]:
    """Major alternating peaks/troughs via a ZigZag (% reversal) filter — the
    standard tool for clean intermediate-cycle turning points.

    A new pivot is confirmed only once price reverses by ≥ `pct` from the running
    extreme of the current leg, so noise is filtered and turns strictly alternate.
    The final entry is the running extreme of the still-open leg, flagged
    `provisional` (it can still extend / hasn't reversed by the threshold yet)."""
    c = close.dropna()
    arr = c.to_numpy()
    n = len(arr)
    if n < 30:
        return []
    th = pct / 100.0
    piv: list[tuple[int, str]] = []
    trend = 0                      # 0 unknown, +1 up-leg, -1 down-leg
    ext_i, ext_px = 0, arr[0]      # running extreme of the current leg
    ref_px = arr[0]                # provisional first-pivot price (unknown leg)
    for i in range(1, n):
        p = arr[i]
        if trend == 0:
            if p >= ref_px * (1 + th):
                piv.append((0, "trough")); trend, ext_i, ext_px = 1, i, p
            elif p <= ref_px * (1 - th):
                piv.append((0, "peak")); trend, ext_i, ext_px = -1, i, p
            else:
                if p < ref_px:
                    ref_px = p          # seed the unknown leg from the lower start
        elif trend == 1:
            if p > ext_px:
                ext_i, ext_px = i, p
            elif p <= ext_px * (1 - th):
                piv.append((ext_i, "peak")); trend, ext_i, ext_px = -1, i, p
        else:
            if p < ext_px:
                ext_i, ext_px = i, p
            elif p >= ext_px * (1 + th):
                piv.append((ext_i, "trough")); trend, ext_i, ext_px = 1, i, p
    prov_kind = "peak" if trend == 1 else "trough" if trend == -1 else "peak"
    piv.append((ext_i, prov_kind))

    out: list[dict] = []
    for n_, (i, kind) in enumerate(piv):
        ts = c.index[i]
        prev_px = arr[piv[n_ - 1][0]] if n_ else None
        mag = round(abs(arr[i] - prev_px) / prev_px * 100.0, 1) if prev_px else None
        out.append({"i": i, "date": str(ts.date()), "t": ts.strftime("%Y-%m"),
                    "x": round(_yf(ts), 3), "px": round(float(arr[i]), 2),
                    "k": kind, "mag_pct": mag,
                    "major": bool(mag is not None and mag >= _MAJOR_PCT),
                    "provisional": n_ == len(piv) - 1})
    return out


def _classify_phase(pos: float, slope: float, w: dict, t3: dict,
                    above200: bool) -> tuple[str, str]:
    """Multi-month sector cycle phase: LEVEL from the 0–100 position, DIRECTION from
    the WEEKLY + 3-day MACD (the user's chosen 3D/weekly confluence) with the
    oscillator slope as a tiebreaker. The slow clock — topping / expanding /
    rolling-over / bottoming / recovering — NOT the daily timing ladder.

    pos high + rising = topping; high + falling = rolling over; mid + rising =
    expanding; mid/low + falling = rolling/bottoming; low + rising = early recovery."""
    # weekly is primary (×2), 3-day secondary (×1), oscillator slope is the tiebreaker
    votes = (2 if w.get("macd_pos") else -2) + (1 if t3.get("macd_pos") else -1)
    if slope > 3:
        votes += 1
    elif slope < -3:
        votes -= 1
    # fresh weekly roll-over / turn-up nudges the call early
    if w.get("macd_cross_dn") or w.get("macd_curl_dn"):
        votes -= 1
    if w.get("macd_cross_up") or w.get("macd_curl_up"):
        votes += 1
    rising = votes > 0 or (votes == 0 and bool(w.get("macd_pos")))
    falling = not rising
    if pos >= 68:
        return ("Peak", "Topping") if rising else ("Downturn", "Rolling over")
    if pos <= 32:
        # bottomed AND turning up = the actionable buy window; still falling = bottoming
        return ("Recovery", "Prime entry") if rising else ("Trough", "Bottoming")
    if rising:
        return ("Expansion", "Trending")
    return ("Downturn", "Rolling over")


def _project_next(swings: list[dict], last_ts: pd.Timestamp) -> dict | None:
    """Next-turn projection from the sector's own median half-cycle length."""
    if len(swings) < 3:
        return None
    xs = [s["x"] for s in swings]
    halves = [xs[n] - xs[n - 1] for n in range(1, len(xs))]
    if not halves:
        return None
    med = float(np.median(halves))
    lo_h, hi_h = float(np.percentile(halves, 25)), float(np.percentile(halves, 75))
    last = swings[-1]
    next_kind = "peak" if last["k"] == "trough" else "trough"
    base_x = _yf(last_ts)                       # project from TODAY, not the lagged pivot
    since = base_x - last["x"]
    central = base_x + max(0.05, med - since)
    return {
        "nextTurn": next_kind,
        "central": _x_to_ym(central),
        "low": _x_to_ym(base_x + max(0.0, lo_h - since)),
        "high": _x_to_ym(base_x + max(0.1, hi_h - since)),
        "central_x": round(central, 3),
        "period_yrs": {"median": round(med * 2, 2), "lo": round(lo_h * 2, 2),
                       "hi": round(hi_h * 2, 2)},
    }


def _x_to_ym(x: float) -> str:
    yr = int(x)
    mo = min(12, max(1, int(round((x - yr) * 12)) + 1))
    if mo == 13:
        yr, mo = yr + 1, 1
    return f"{yr}-{mo:02d}"


def _weekly_points(s: pd.Series, value_fn=None) -> list[dict]:
    """Downsample to weekly {x, v} points for a clean overlay (≈313 pts / 6y)."""
    w = s.resample("W-FRI").last().dropna()
    out = []
    for ts, v in w.items():
        if pd.isna(v):
            continue
        out.append({"x": round(_yf(ts), 3), "v": round(float(value_fn(v) if value_fn else v), 2)})
    return out


def _leadership(close_full: pd.DataFrame, ticker: str, bench: str = "SPY") -> dict:
    """RS vs SPY: 63d & 126d relative momentum + above-200d-trend of the ratio."""
    if ticker not in close_full or bench not in close_full:
        return {}
    rs = (close_full[ticker] / close_full[bench]).dropna()
    if len(rs) < 210:
        return {}
    m63 = float(rs.pct_change(63).iloc[-1] * 100)
    m126 = float(rs.pct_change(126).iloc[-1] * 100)
    ma200 = float(rs.rolling(200).mean().iloc[-1])
    return {"rs_63d": round(m63, 1), "rs_126d": round(m126, 1),
            "rs_above_trend": bool(rs.iloc[-1] > ma200)}


def build_sector(ticker: str, meta: dict, closes: pd.DataFrame,
                 win_start: pd.Timestamp) -> dict | None:
    """One sector ETF -> its full cycle record (price, oscillator, turns, phase, projection)."""
    full = closes[ticker].dropna() if ticker in closes else pd.Series(dtype=float)
    if len(full) < 300:
        log.warning("sector_cycles: %s too thin (%d rows) — skipped", ticker, len(full))
        return None
    win = full[full.index >= win_start]
    if len(win) < 60:
        return None
    last_ts = full.index[-1]

    # --- chart series: rebased-to-100 price + 0–100 oscillator (weekly) ---
    base = float(win.iloc[0])
    price_pts = _weekly_points(win, lambda v: v / base * 100.0)
    osc_full = _detrended_osc(full)
    osc_pts = _weekly_points(osc_full[osc_full.index >= win_start])

    # --- turning points within the window ---
    swings_all = _detect_swings(full)
    swings = [s for s in swings_all if s["x"] >= _yf(win_start) - 0.05]
    for s in swings:                           # attach rebased y + osc y for the chart
        s["rebased"] = round(s["px"] / base * 100.0, 2)
        oy = osc_full.reindex([pd.Timestamp(s["date"])], method="nearest")
        s["osc"] = round(float(oy.iloc[0]), 1) if len(oy) and pd.notna(oy.iloc[0]) else None
        s["narr_id"] = None                    # filled from narratives.json at build time

    # --- current phase: the SLOW (weekly/3-day) cycle clock, confirmed by MTF MACD ---
    res = cycles.analyze(full, kind="equity")
    lad = (res or {}).get("ladder") or {}
    mtf = (res or {}).get("mtf") or {}
    timing_state = lad.get("state") or ""          # the fast daily-timing read (secondary)
    osc_clean = osc_full.dropna()
    pos_now = float(osc_clean.iloc[-1]) if len(osc_clean) else 50.0
    osc_slope = float(osc_clean.iloc[-1] - osc_clean.iloc[-22]) if len(osc_clean) > 22 else 0.0
    above200 = bool(len(full) >= 200 and full.iloc[-1] > full.iloc[-200:].mean())
    phase, phase_label = _classify_phase(pos_now, osc_slope, mtf.get("W") or {},
                                         mtf.get("3D") or {}, above200)
    lead = _leadership(closes, ticker)

    last_trough = next((s["t"] for s in reversed(swings) if s["k"] == "trough"), None)
    last_peak = next((s["t"] for s in reversed(swings) if s["k"] == "peak"), None)
    proj = _project_next(swings_all, last_ts)

    # tilt: direction of the ladder + leadership
    up = phase in ("Recovery", "Expansion")
    rs_strong = (lead.get("rs_63d") or 0) > 0 and lead.get("rs_above_trend")
    if up and rs_strong and above200:
        tilt = "tailwind"
    elif (not up) and (not above200) and (lead.get("rs_63d") or 0) < 0:
        tilt = "headwind"
    else:
        tilt = "mixed"
    if proj is not None:
        proj["tilt"] = tilt

    ret_win = round((float(win.iloc[-1]) / base - 1.0) * 100.0, 1)

    return {
        "id": ticker.lower(), "ticker": ticker, "name": meta["name"], "short": meta["short"],
        "group": meta["group"], "accent": meta["accent"],
        "now": {
            "phase": phase, "phaseLabel": phase_label, "pos": round(pos_now, 1),
            "osc_slope": round(osc_slope, 1),
            "timing_state": timing_state, "action": (lad.get("action") or ""),
            "w_macd_up": bool((mtf.get("W") or {}).get("macd_pos")),
            "t3_macd_up": bool((mtf.get("3D") or {}).get("macd_pos")),
            "lastTrough": last_trough, "lastPeak": last_peak,
            "above200d": above200, "ret_win_pct": ret_win,
            "rs_63d": lead.get("rs_63d"), "rs_126d": lead.get("rs_126d"),
            "rs_above_trend": lead.get("rs_above_trend"),
            "dc_phase": (res.get("cycle") or {}).get("dc_phase"),
            "read": None,           # narrative.json fills the live read
        },
        "proj": proj,
        "turns": swings,
        "price": price_pts,
        "osc": osc_pts,
        "n_turns_all": len(swings_all),
    }


def compute(asof: str | None = None) -> dict | None:
    """Top-level: build every sector's cycle record + page meta. Returns None if the
    close panel can't be loaded (build script then no-ops)."""
    try:
        closes = yahoo_closes()
    except Exception as e:  # noqa: BLE001
        log.error("sector_cycles: cannot load yahoo_closes: %s", e)
        return None
    if closes is None or closes.empty:
        return None
    if asof:
        closes = closes[closes.index <= pd.Timestamp(asof)]
    last_ts = closes.index[-1]
    win_start = last_ts - pd.DateOffset(years=WINDOW_YEARS)

    sectors = []
    for tk, meta in SECTORS.items():
        try:
            rec = build_sector(tk, meta, closes, win_start)
        except Exception as e:  # noqa: BLE001
            log.exception("sector_cycles: %s failed: %s", tk, e)
            rec = None
        if rec:
            sectors.append(rec)
    if not sectors:
        return None

    # leadership rank (best 63d RS = 1) for the "who leads" read
    ranked = sorted([s for s in sectors if s["now"].get("rs_63d") is not None],
                    key=lambda s: s["now"]["rs_63d"], reverse=True)
    for n, s in enumerate(ranked, 1):
        s["now"]["rs_rank"] = n

    x_lo = round(_yf(win_start), 3)
    x_hi = round(_yf(last_ts) + _TODAY_PAD, 3)
    return {
        "meta": {
            "asOf": str(last_ts.date()),
            "today": round(_yf(last_ts), 3),
            "xDomain": [x_lo, x_hi],
            "window_years": WINDOW_YEARS,
            "rebaseDate": str(win_start.date()),
            "benchmark": config.load()["engine"]["rs_ranking"]["benchmark"],
            "n_sectors": len(sectors),
        },
        "phases": PHASES,
        "sectors": sectors,
    }
