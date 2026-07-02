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

import json
import logging

import numpy as np
import pandas as pd

from engine import basket_index, cycles
from engine.inputs import yahoo_closes
from lib import config

log = logging.getLogger(__name__)

# ── sector metadata ─────────────────────────────────────────────────────────
# name = GICS sector; group = cyclical nature (drives the cross-sector grouping);
# accent = a distinct, dark-bg-legible hue per line (no two adjacent in the wheel).
SECTORS: dict[str, dict] = {
    "XLK":  {"name": "Technology",             "short": "Tech",        "group": "Growth",    "accent": "#38bdf8", "name_zh": "科技",       "short_zh": "科技"},
    "XLC":  {"name": "Communication Services",  "short": "Comm",        "group": "Growth",    "accent": "#818cf8", "name_zh": "通讯服务",   "short_zh": "通讯"},
    "XLY":  {"name": "Consumer Discretionary",  "short": "Discretionary","group": "Cyclical", "accent": "#f472b6", "name_zh": "非必需消费", "short_zh": "非必需"},
    "XLF":  {"name": "Financials",              "short": "Financials",  "group": "Cyclical",  "accent": "#34d399", "name_zh": "金融",       "short_zh": "金融"},
    "XLI":  {"name": "Industrials",             "short": "Industrials", "group": "Cyclical",  "accent": "#fbbf24", "name_zh": "工业",       "short_zh": "工业"},
    "XLB":  {"name": "Materials",               "short": "Materials",   "group": "Cyclical",  "accent": "#a3e635", "name_zh": "原材料",     "short_zh": "原材料"},
    "XLE":  {"name": "Energy",                  "short": "Energy",      "group": "Cyclical",  "accent": "#fb923c", "name_zh": "能源",       "short_zh": "能源"},
    "XLV":  {"name": "Health Care",             "short": "Health",      "group": "Defensive", "accent": "#2dd4bf", "name_zh": "医疗保健",   "short_zh": "医疗"},
    "XLP":  {"name": "Consumer Staples",        "short": "Staples",     "group": "Defensive", "accent": "#94a3b8", "name_zh": "必需消费",   "short_zh": "必需"},
    "XLU":  {"name": "Utilities",               "short": "Utilities",   "group": "Defensive", "accent": "#c084fc", "name_zh": "公用事业",   "short_zh": "公用"},
    "XLRE": {"name": "Real Estate",             "short": "Real Estate", "group": "Rate-sens", "accent": "#f87171", "name_zh": "房地产",     "short_zh": "房地产"},
}

GROUP_ZH = {"Growth": "成长", "Cyclical": "周期", "Defensive": "防御", "Rate-sens": "利率敏感", "Thematic": "主题"}
CATEGORY_ZH = {
    "AI & Technology": "AI 与科技", "Artificial Intelligence": "人工智能",
    "Consumer Cyclical": "周期性消费", "Consumer Defensive": "防御性消费",
    "Crypto & Digital Assets": "加密与数字资产", "Energy & Power": "能源与电力",
    "Financials": "金融", "Healthcare": "医疗保健", "Industrials": "工业",
    "Industrials & Defense": "工业与国防", "Materials & Mining": "材料与矿业",
    "Semiconductors": "半导体", "Semiconductors & Hardware": "半导体与硬件", "Software": "软件",
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

WINDOW_YEARS = 15          # full history window: surfaces ~15y of cycles (where the tape exists)
DEFAULT_WINDOW_YEARS = 7   # default VISIBLE span; the chart opens here, a "Max/15Y" toggle expands to WINDOW_YEARS
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


def _taper_points(s: pd.Series, recent_start: pd.Timestamp, value_fn=None) -> list[dict]:
    """Tapered-cadence {x, v} points for the long 15y window: WEEKLY within the default
    visible span (last DEFAULT_WINDOW_YEARS) where the user actually looks, MONTHLY for the
    deep-history tail behind it. Keeps the default view crisp while ~halving the payload of
    the zoomed-out Max view. Turns/legs are detected on the full daily tape, so this purely
    cosmetic thinning never moves a pivot date."""
    s = s.dropna()
    if s.empty:
        return []
    old = s[s.index < recent_start].resample("ME").last().dropna()
    recent = s[s.index >= recent_start].resample("W-FRI").last().dropna()
    out = []
    for ts, v in pd.concat([old, recent]).items():
        if pd.isna(v):
            continue
        out.append({"x": round(_yf(ts), 3), "v": round(float(value_fn(v) if value_fn else v), 2)})
    out.sort(key=lambda p: p["x"])
    # anchor the line at the window's true first bar: the month-end resample would
    # otherwise start the plot at the first month's CLOSE — up to a month of drift
    # after the rebase base, so the "rebased to 100" line visibly starts off 100
    first = {"x": round(_yf(s.index[0]), 3),
             "v": round(float(value_fn(s.iloc[0]) if value_fn else s.iloc[0]), 2)}
    if not out or first["x"] < out[0]["x"]:
        out.insert(0, first)
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


def _zz_pct_for(full: pd.Series) -> float:
    """Volatility-scaled ZigZag threshold: a 14% reversal is a "major" swing for a
    typical sector, but a thematic basket (crypto, uranium, neoclouds) swings that
    much weekly — so scale the threshold up with realised vol to keep the turn count
    sane (a basket's major turns ARE bigger). Sectors keep the fixed 14% so their
    detected dates — and the narrative keys bound to them — never move."""
    r = full.pct_change().dropna()
    if len(r) < 60:
        return _ZZ_PCT
    vol = float(r.std()) * (252.0 ** 0.5)            # annualised
    return float(min(55.0, _ZZ_PCT * max(1.0, vol / 0.22)))


def _record_core(full: pd.Series, win_start: pd.Timestamp, last_ts: pd.Timestamp,
                 pct: float = _ZZ_PCT) -> dict | None:
    """Shared cycle math for ANY close/level series (a sector ETF or a basket index):
    rebased-to-100 price + 0–100 oscillator series (weekly), ZigZag turns, the
    weekly/3-day MACD-confirmed phase, and the median-half-cycle projection."""
    win = full[full.index >= win_start]
    if len(win) < 60:
        return None
    base = float(win.iloc[0])
    if base <= 0:
        return None
    recent_start = last_ts - pd.DateOffset(years=DEFAULT_WINDOW_YEARS)
    price_pts = _taper_points(win, recent_start, lambda v: v / base * 100.0)
    osc_full = _detrended_osc(full)
    osc_pts = _taper_points(osc_full[osc_full.index >= win_start], recent_start)

    swings_all = _detect_swings(full, pct)
    swings = [s for s in swings_all if s["x"] >= _yf(win_start) - 0.05]
    for s in swings:                           # attach rebased y + osc y for the chart
        s["rebased"] = round(s["px"] / base * 100.0, 2)
        oy = osc_full.reindex([pd.Timestamp(s["date"])], method="nearest")
        s["osc"] = round(float(oy.iloc[0]), 1) if len(oy) and pd.notna(oy.iloc[0]) else None

    res = cycles.analyze(full, kind="equity")
    lad = (res or {}).get("ladder") or {}
    mtf = (res or {}).get("mtf") or {}
    osc_clean = osc_full.dropna()
    pos_now = float(osc_clean.iloc[-1]) if len(osc_clean) else 50.0
    osc_slope = float(osc_clean.iloc[-1] - osc_clean.iloc[-22]) if len(osc_clean) > 22 else 0.0
    above200 = bool(len(full) >= 200 and full.iloc[-1] > full.iloc[-200:].mean())
    phase, phase_label = _classify_phase(pos_now, osc_slope, mtf.get("W") or {},
                                         mtf.get("3D") or {}, above200)
    last_trough = next((s["t"] for s in reversed(swings) if s["k"] == "trough"), None)
    last_peak = next((s["t"] for s in reversed(swings) if s["k"] == "peak"), None)
    proj = _project_next(swings_all, last_ts)
    ret_win = round((float(win.iloc[-1]) / base - 1.0) * 100.0, 1)
    # actionable transition badge: washed-out + curling UP = BUY; stretched + rolling
    # DOWN = SELL (the extremes turning, e.g. Utilities buy / Tech sell)
    signal = ("BUY" if pos_now <= 45 and osc_slope > 0.5
              else "SELL" if pos_now >= 55 and osc_slope < -0.5 else None)
    return {
        "price": price_pts, "osc": osc_pts, "turns": swings, "proj": proj,
        "n_turns_all": len(swings_all),
        "now": {
            "phase": phase, "phaseLabel": phase_label, "pos": round(pos_now, 1),
            "signal": signal, "osc_slope": round(osc_slope, 1),
            "timing_state": lad.get("state") or "", "action": lad.get("action") or "",
            "w_macd_up": bool((mtf.get("W") or {}).get("macd_pos")),
            "t3_macd_up": bool((mtf.get("3D") or {}).get("macd_pos")),
            "lastTrough": last_trough, "lastPeak": last_peak,
            "above200d": above200, "ret_win_pct": ret_win,
            "dc_phase": (res.get("cycle") or {}).get("dc_phase"),
            "read": None,           # narrative.json fills the live read
        },
    }


def _apply_leadership(rec: dict, lead: dict) -> None:
    """Fold RS-vs-SPY leadership into the record's `now` + a tailwind/headwind tilt."""
    nw = rec["now"]
    nw["rs_63d"] = lead.get("rs_63d")
    nw["rs_126d"] = lead.get("rs_126d")
    nw["rs_above_trend"] = lead.get("rs_above_trend")
    up = nw["phase"] in ("Recovery", "Expansion")
    rs_strong = (lead.get("rs_63d") or 0) > 0 and lead.get("rs_above_trend")
    if up and rs_strong and nw["above200d"]:
        tilt = "tailwind"
    elif (not up) and (not nw["above200d"]) and (lead.get("rs_63d") or 0) < 0:
        tilt = "headwind"
    else:
        tilt = "mixed"
    if rec.get("proj") is not None:
        rec["proj"]["tilt"] = tilt


def build_sector(ticker: str, meta: dict, closes: pd.DataFrame,
                 win_start: pd.Timestamp) -> dict | None:
    """One sector ETF -> its full cycle record (price, oscillator, turns, phase, projection)."""
    full = closes[ticker].dropna() if ticker in closes else pd.Series(dtype=float)
    if len(full) < 300:
        log.warning("sector_cycles: %s too thin (%d rows) — skipped", ticker, len(full))
        return None
    core = _record_core(full, win_start, full.index[-1])
    if core is None:
        return None
    rec = dict(core)
    rec.update({"id": ticker.lower(), "ticker": ticker, "kind": "sector",
                "name": meta["name"], "short": meta["short"],
                "name_zh": meta.get("name_zh"), "short_zh": meta.get("short_zh"),
                "group": meta["group"], "group_zh": GROUP_ZH.get(meta["group"], meta["group"]),
                "accent": meta["accent"]})
    _apply_leadership(rec, _leadership(closes, ticker))
    return rec


def _basket_rs(full: pd.Series, spy: pd.Series | None) -> dict:
    """RS of a basket index vs SPY (scale-invariant — ratio momentum)."""
    if spy is None or spy.empty:
        return {}
    rs = (full / spy.reindex(full.index).ffill()).dropna()
    if len(rs) < 210:
        return {}
    return {"rs_63d": round(float(rs.pct_change(63).iloc[-1] * 100), 1),
            "rs_126d": round(float(rs.pct_change(126).iloc[-1] * 100), 1),
            "rs_above_trend": bool(rs.iloc[-1] > rs.rolling(200).mean().iloc[-1])}


def build_basket(bid: str, bmeta: dict, win_start: pd.Timestamp, last_ts: pd.Timestamp,
                 spy: pd.Series | None, accent: str) -> dict | None:
    """One thematic basket -> its cycle record, off the equal-weight member index
    (engine.basket_index.consolidated_candle, current-membership deep tape)."""
    members = bmeta.get("members") or []
    if len(members) < 3:
        return None
    try:
        idx = basket_index.deep_calendar(members)
        if idx is None or len(idx) < 300:
            return None
        cand, cmeta = basket_index.consolidated_candle(members, idx, mode="equal", pit=False)
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: basket %s candle failed: %s", bid, e)
        return None
    if cand is None or "close" not in cand:
        return None
    # inf-poisoned rows (a member's 0→real price jump) crash the cycle math with
    # NaN scores downstream — strip them so the basket renders on its clean tape
    full = cand["close"].replace([np.inf, -np.inf], np.nan).dropna()
    if len(full) < 300:
        return None
    core = _record_core(full, win_start, last_ts, pct=_zz_pct_for(full))
    if core is None:
        return None
    cat = bmeta.get("category") or "Thematic"
    nm_zh = bmeta.get("name_zh") or bmeta.get("name") or bid
    rec = dict(core)
    rec.update({"id": "b-" + bid, "ticker": bmeta.get("etf_proxy") or "", "kind": "basket",
                "name": bmeta.get("name") or bid, "short": bmeta.get("name") or bid,
                "name_zh": nm_zh, "short_zh": nm_zh,
                "group": cat, "group_zh": CATEGORY_ZH.get(cat, cat), "accent": accent,
                "theme": bmeta.get("theme"), "theme_zh": bmeta.get("theme_zh"),
                "etf_proxy": bmeta.get("etf_proxy"),
                "coverage": (cmeta or {}).get("coverage_pct"),
                "n_members": (cmeta or {}).get("n_live")})
    _apply_leadership(rec, _basket_rs(full, spy))
    return rec


def _load_baskets() -> dict:
    """Thematic basket membership (data/baskets/membership.json)."""
    f = config.data_dir() / "baskets" / "membership.json"
    if not f.exists():
        return {}
    try:
        return (json.loads(f.read_text(encoding="utf-8")) or {}).get("baskets", {})
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: membership.json unreadable: %s", e)
        return {}


def _basket_accent(i: int, n: int) -> str:
    """Evenly-spaced, dark-bg-legible hue per basket so toggled lines stay distinct."""
    hue = round((i * 360.0 / max(n, 1) + 12) % 360)
    return f"hsl({hue} 64% 62%)"


# Index-amalgamation families (Nasdaq-100 / Russell-2000): the curated complexes from the subsector
# desks (data/baskets_<ns>/membership.json["amalgamations"]) on the SAME cycle clock, so the user
# can watch how leadership rotates among an index's complexes and project each one's next turn.
_AMALGAM_FAMILIES = {
    "nasdaq": {"label": "Nasdaq-100", "label_zh": "纳斯达克100", "benchmark": "QQQ"},
    "russell": {"label": "Russell-2000", "label_zh": "罗素2000", "benchmark": "IWM"},
}


def _bench_close(bench: str, closes: pd.DataFrame) -> pd.Series | None:
    """RS benchmark for an index family: the index ETF close (QQQ / IWM), from the close panel
    if present, else the deep member store."""
    if bench in closes:
        s = closes[bench].dropna()
        if not s.empty:
            return s
    try:
        df = basket_index._load_member_ohlcv(bench)
        return df["close"].dropna() if df is not None and "close" in df else None
    except Exception:  # noqa: BLE001
        return None


def _load_amalgams(ns: str) -> dict:
    f = config.data_dir() / f"baskets_{ns}" / "membership.json"
    if not f.exists():
        return {}
    try:
        return (json.loads(f.read_text(encoding="utf-8")) or {}).get("amalgamations", {})
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: %s amalgamations unreadable: %s", ns, e)
        return {}


def build_amalgam_family(ns: str, win_start: pd.Timestamp, last_ts: pd.Timestamp,
                         closes: pd.DataFrame) -> list[dict]:
    """Cycle records for one index's amalgamation complexes (kind=ns, id=`<ns>-<key>`), RS'd to
    the index ETF so leadership reads WITHIN the index."""
    fam = _AMALGAM_FAMILIES[ns]
    amalgams = _load_amalgams(ns)
    bench = _bench_close(fam["benchmark"], closes)
    keys = list(amalgams)
    out: list[dict] = []
    for i, key in enumerate(keys):
        spec = amalgams[key]
        bmeta = {"members": spec.get("members") or [], "name": spec.get("name") or key,
                 "name_zh": spec.get("name_zh"), "category": fam["label"],
                 "etf_proxy": "", "theme": None}
        try:
            rec = build_basket(key, bmeta, win_start, last_ts, bench, _basket_accent(i, len(keys)))
        except Exception as e:  # noqa: BLE001
            log.exception("sector_cycles: %s amalgam %s failed: %s", ns, key, e)
            rec = None
        if not rec:
            continue
        rec["id"] = f"{ns}-{key}"               # distinct from thematic 'b-<id>' namespace
        rec["kind"] = ns                         # the JS family key
        rec["group"] = fam["label"]
        rec["group_zh"] = fam["label_zh"]
        out.append(rec)
    ranked = sorted([b for b in out if b["now"].get("rs_63d") is not None],
                    key=lambda b: b["now"]["rs_63d"], reverse=True)
    for n, b in enumerate(ranked, 1):
        b["now"]["rs_rank"] = n
    return out


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

    # --- thematic baskets (Phase 2): same machinery off the equal-weight member index;
    #     OFF by default in the UI, the user toggles individual baskets onto the chart ---
    spy = closes["SPY"].dropna() if "SPY" in closes else None
    basket_defs = _load_baskets()
    keys = list(basket_defs.keys())
    baskets = []
    for i, bid in enumerate(keys):
        try:
            rec = build_basket(bid, basket_defs[bid], win_start, last_ts, spy,
                               _basket_accent(i, len(keys)))
        except Exception as e:  # noqa: BLE001
            log.exception("sector_cycles: basket %s failed: %s", bid, e)
            rec = None
        if rec:
            baskets.append(rec)
    branked = sorted([b for b in baskets if b["now"].get("rs_63d") is not None],
                     key=lambda b: b["now"]["rs_63d"], reverse=True)
    for n, b in enumerate(branked, 1):
        b["now"]["rs_rank"] = n
    baskets.sort(key=lambda b: (b.get("group") or "", b["name"]))   # grouped for the chip rail

    # --- index amalgamation families (Nasdaq-100 / Russell-2000 complexes) ---
    amalgam_families = {}
    for ns in _AMALGAM_FAMILIES:
        try:
            fam_recs = build_amalgam_family(ns, win_start, last_ts, closes)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.exception("sector_cycles: amalgam family %s failed: %s", ns, e)
            fam_recs = []
        if fam_recs:
            amalgam_families[ns] = fam_recs

    x_lo = round(_yf(win_start), 3)
    x_hi = round(_yf(last_ts) + _TODAY_PAD, 3)
    x_lo_default = round(_yf(last_ts - pd.DateOffset(years=DEFAULT_WINDOW_YEARS)), 3)
    return {
        "meta": {
            "asOf": str(last_ts.date()),
            "today": round(_yf(last_ts), 3),
            "xDomain": [x_lo, x_hi],
            "xDomainDefault": [x_lo_default, x_hi],
            "window_years": WINDOW_YEARS,
            "default_window_years": DEFAULT_WINDOW_YEARS,
            "rebaseDate": str(win_start.date()),
            "benchmark": config.load()["engine"]["rs_ranking"]["benchmark"],
            "n_sectors": len(sectors),
            "n_baskets": len(baskets),
            "families": [{"key": ns, "label": _AMALGAM_FAMILIES[ns]["label"],
                          "label_zh": _AMALGAM_FAMILIES[ns]["label_zh"],
                          "benchmark": _AMALGAM_FAMILIES[ns]["benchmark"],
                          "n": len(amalgam_families[ns])}
                         for ns in _AMALGAM_FAMILIES if ns in amalgam_families],
        },
        "phases": PHASES,
        "sectors": sectors,
        "baskets": baskets,
        **amalgam_families,
    }
