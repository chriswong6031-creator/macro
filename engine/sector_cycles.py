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
from engine import cycle_ontology as onto
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

# W0.3 — engine-owned read: zh phase labels for the generated sentence.
PHASE_ZH = {
    "Trough":    "筑底阶段",
    "Recovery":  "复苏阶段",
    "Expansion": "扩张阶段",
    "Peak":      "顶部阶段",
    "Downturn":  "下行阶段",
}


def _engine_read(name: str, phase: str, pos: float, above200: bool,
                 proj: dict | None, rs_63d: float | None,
                 rs_rank: int | None) -> tuple[str, str]:
    """Generate a factual, templated engine-owned read sentence (EN + ZH).
    Pure function of the engine's computed fields — no hand-editing required.
    Doctrine (masterplan §4 W0.3): the engine owns every plotted number; narrative
    may annotate but the ENGINE read is primary and is always present."""
    phase_short = (PHASES.get(phase) or {}).get("short", phase)
    phase_zh = PHASE_ZH.get(phase, phase)
    pos_int = int(round(pos))

    # trend context
    trend_en = "above" if above200 else "below"
    trend_zh = "位于" if above200 else "低于"

    # RS context (optional — omit if not computed)
    if rs_63d is not None and rs_rank is not None:
        sign = "+" if rs_63d >= 0 else ""
        rs_en = f" RS vs SPY: {sign}{rs_63d:.1f}% (rank #{rs_rank})."
        rs_zh = f"相对标普RS：{sign}{rs_63d:.1f}%（排名第{rs_rank}）。"
    elif rs_63d is not None:
        sign = "+" if rs_63d >= 0 else ""
        rs_en = f" RS vs SPY: {sign}{rs_63d:.1f}%."
        rs_zh = f"相对标普RS：{sign}{rs_63d:.1f}%。"
    else:
        rs_en = rs_zh = ""

    # projection context (optional)
    if proj and proj.get("central") and proj.get("nextTurn"):
        nt = proj["nextTurn"]          # "peak" or "trough"
        cen = proj["central"]          # YYYY-MM
        proj_en = f" Next projected {nt}: {cen}."
        next_zh = "顶部" if nt == "peak" else "底部"
        proj_zh = f"预计下一{next_zh}：{cen}。"
    else:
        proj_en = proj_zh = ""

    read_en = (f"{name} is in a {phase_short} phase (cycle position {pos_int}/100), "
               f"{trend_en} its 200-day.{rs_en}{proj_en}")
    read_zh = (f"{name}{phase_zh}（周期位置 {pos_int}/100），"
               f"{trend_zh}200日均线。{rs_zh}{proj_zh}")
    return read_en, read_zh
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
    """Next-turn projection — W1.6 overdue rewrite.

    PRIOR BEHAVIOUR (BUG): projected from TODAY with a max(0.05, med−since) floor,
    making overdue cycles appear perpetually "imminent" (the receding-horizon pathology
    from NP-1 / D1 §4.5 and _project_next comment above).

    FIX: delegate entirely to onto.project_next() which anchors at the last CONFIRMED
    turn and emits overdue / overdue_frac instead of silently walking the date forward.
    The lo/hi band edges are ALSO anchored at last_confirmed + IQR_half (not today).
    All existing output keys (central, low, high, central_x, nextTurn, period_yrs)
    are preserved so JS consumers see zero breaking changes; new keys (overdue,
    overdue_frac, last_confirmed_x, last_confirmed_t) are additive.
    """
    today_x = _yf(last_ts)
    return onto.project_next(swings, today_x)


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


def _leadership(close_full: pd.DataFrame, ticker: str, bench: str = "SPY",
                asof: pd.Timestamp | None = None) -> dict:
    """RS vs SPY: 63d & 126d relative momentum + above-200d-trend of the ratio.

    Parameters
    ----------
    asof : when provided, slice BOTH ticker and benchmark series to ≤ asof
        before computing RS.  This makes historical/PIT rebuilds explicit and
        verifiable.  In the live path `closes` is already sliced by compute(),
        so asof is not strictly required there, but can be passed for clarity.
    """
    if ticker not in close_full or bench not in close_full:
        return {"thin_history": False}
    t = close_full[ticker].dropna()
    b = close_full[bench].dropna()
    if asof is not None:
        t = t[t.index <= asof]
        b = b[b.index <= asof]
    rs = (t / b.reindex(t.index).ffill()).dropna()
    if len(rs) < 210:
        log.warning("_leadership: %s has only %d RS rows (< 210 min) — thin_history flagged",
                    ticker, len(rs))
        return {"thin_history": True, "rs_rows": len(rs)}
    m63 = float(rs.pct_change(63).iloc[-1] * 100)
    m126 = float(rs.pct_change(126).iloc[-1] * 100)
    ma200 = float(rs.rolling(200).mean().iloc[-1])
    return {"rs_63d": round(m63, 1), "rs_126d": round(m126, 1),
            "rs_above_trend": bool(rs.iloc[-1] > ma200), "thin_history": False}


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


def _price_series(closes_px: pd.DataFrame | None, ticker: str,
                  tr_full: pd.Series) -> pd.Series | None:
    """Resolve a ticker's structure-basis (close_price) series from the price panel.

    Returns:
      - the ticker's close_price series (tagged .attrs['price_basis']='price') when present;
      - a copy of the TR series tagged 'tr_fallback' when the ticker is ABSENT from the
        price panel (a declared close_price gap) — so _record_core stamps basis:'tr_fallback'
        and NEVER silently mixes a TR structure read into a price-epoch build;
      - None when no price panel was supplied at all (the legacy TR-only path → basis 'tr').
    """
    if closes_px is None:
        return None
    if ticker in closes_px:
        s = closes_px[ticker].dropna()
        if not s.empty:
            s = s.copy()
            s.attrs["price_basis"] = "price"
            return s
    # ticker missing from the price panel → explicit, labeled TR fallback
    fb = tr_full.copy()
    fb.attrs["price_basis"] = "tr_fallback"
    log.warning("sector_cycles: %s absent from close_price panel — structure basis "
                "tr_fallback (declared gap; not silent)", ticker)
    return fb


def _record_core(full: pd.Series, win_start: pd.Timestamp, last_ts: pd.Timestamp,
                 pct: float = _ZZ_PCT, *, series_id: str = "",
                 _phase_pending: dict | None = None,
                 price: pd.Series | None = None) -> dict | None:
    """Shared cycle math for ANY close/level series (a sector ETF or a basket index):
    rebased-to-100 price + 0–100 oscillator series (weekly), ZigZag turns, the
    weekly/3-day MACD-confirmed phase, and the median-half-cycle projection.

    W2.2 basis split (D4 §7): the STRUCTURE math — rebased price line, detrended
    oscillator, ZigZag turns, next-turn projection, and `cycles.analyze` trough/DCL/
    failed-cycle — runs on `price` (split-adj, dividend-UNadjusted `close_price`) when
    supplied, so a dividend-inflated total-return tape can no longer push a turn date or
    a drawdown level.  The MOMENTUM / RS math (MACD, StochRSI, RSI in `cycles.analyze`,
    and RS-vs-SPY folded later in _apply_leadership) stays on `full` (the TR series) so a
    return stat keeps dividend fidelity.

    `price=None` (the legacy default) runs EVERYTHING on `full` — byte-identical to W1.6.
    The emitted `now.basis` records which structure basis was actually used:
      "price"        — structure math ran on the supplied close_price series;
      "tr"           — legacy path (no price supplied);
      "tr_fallback"  — price WAS requested but the series degraded to TR (the caller
                       passed a series tagged .attrs['price_basis']=='tr_fallback', i.e.
                       close_price was missing for this ticker — never silent, always
                       labeled so the audit + graders can exclude it).

    W1.6 additions (data-only, no UI change):
    - pos_v2         : canonical_position() (100·Φ(z)) alongside legacy pos (range-stoch)
    - phase_v2       : classify_phase() from the ontology (hysteresis via _phase_pending)
    - phase_v2_age_bars: bars since last phase_v2 transition (placeholder; always 0 at
                        this single-bar call; the full phase_age_bars is computed in the
                        backfill wave W2.3 which replays the series bar-by-bar)
    - stance         : resolve_state() stance key
    - divergence     : resolve_state() divergence flag
    - tone           : stance tone (bullish|bearish|neutral|caution|anticipatory)
    - overdue        : whether the projection's central date has passed (new proj field)
    Legacy fields (phase, pos, signal, timing_state, ...) are byte-identical to W0.3
    whenever price=None.

    Parameters
    ----------
    price : the structure-math basis series (close_price).  None → legacy TR-only path.
    _phase_pending : mutable hysteresis dict, caller-owned (per-series). Pass None to
                     start fresh (default). The dict is mutated in-place by classify_phase;
                     callers that want hysteresis persistence across build iterations
                     should hold and pass the same dict per series.
    """
    # ── basis resolution (D4 §7 structure-vs-momentum split) ────────────────────
    # `struct` is what all structure math reads; `full` (TR) always drives momentum/RS.
    if price is not None:
        struct = price.replace([np.inf, -np.inf], np.nan).dropna()
        struct = struct.reindex(full.index).dropna()  # align to the momentum tape's index
        if struct.empty:
            struct = full
            basis = "tr_fallback"
        else:
            basis = "tr_fallback" if price.attrs.get("price_basis") == "tr_fallback" else "price"
    else:
        struct = full
        basis = "tr"

    win = struct[struct.index >= win_start]
    if len(win) < 60:
        return None
    base = float(win.iloc[0])
    if base <= 0:
        return None
    recent_start = last_ts - pd.DateOffset(years=DEFAULT_WINDOW_YEARS)
    price_pts = _taper_points(win, recent_start, lambda v: v / base * 100.0)
    osc_full = _detrended_osc(struct)
    osc_pts = _taper_points(osc_full[osc_full.index >= win_start], recent_start)

    swings_all = _detect_swings(struct, pct)
    swings = [s for s in swings_all if s["x"] >= _yf(win_start) - 0.05]
    for s in swings:                           # attach rebased y + osc y for the chart
        s["rebased"] = round(s["px"] / base * 100.0, 2)
        oy = osc_full.reindex([pd.Timestamp(s["date"])], method="nearest")
        s["osc"] = round(float(oy.iloc[0]), 1) if len(oy) and pd.notna(oy.iloc[0]) else None

    # analyze: structure math on `struct` (price), momentum/MACD on `full` (TR) — the
    # A13 substrate seam.  price=struct only when a distinct structure basis exists (a
    # tr_fallback series would just pass TR twice, a no-op that keeps the legacy path).
    res = cycles.analyze(full, kind="equity",
                         price=(struct if basis == "price" else None))
    lad = (res or {}).get("ladder") or {}
    mtf = (res or {}).get("mtf") or {}
    osc_clean = osc_full.dropna()               # osc_full is on `struct` (structure basis)
    pos_now = float(osc_clean.iloc[-1]) if len(osc_clean) else 50.0
    osc_slope = float(osc_clean.iloc[-1] - osc_clean.iloc[-22]) if len(osc_clean) > 22 else 0.0
    # above200 is a DRAWDOWN/trend read (structure) → measure on `struct`.
    above200 = bool(len(struct) >= 200 and struct.iloc[-1] > struct.iloc[-200:].mean())
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

    # ── W1.6: new ontology fields (additive; legacy fields above unchanged) ──
    # pos_v2: canonical 100·Φ(z) position from the ontology — a cycle-POSITION read
    # (structure) → compute on `struct` (price basis when supplied).
    try:
        pos_v2_series = onto.canonical_position(struct, freq="D")
        pos_v2_clean = pos_v2_series.dropna()
        pos_v2 = round(float(pos_v2_clean.iloc[-1]), 2) if len(pos_v2_clean) else None
    except Exception:  # noqa: BLE001
        pos_v2 = None

    # phase_v2 + hysteresis: classify_phase from the ontology with the caller's
    # mutable pending dict so hysteresis state persists within this series's computation.
    # confirm_persist=0 (OFF) preserves behavioral continuity per D1 §2.1 / M-plan note.
    pending = _phase_pending if _phase_pending is not None else {}
    ph_read: dict = {}
    try:
        ph_read = onto.classify_phase(
            pos_now, osc_slope,
            mtf.get("W") or {}, mtf.get("3D") or {},
            confirm_persist=0, pending=pending,
        )
        phase_v2 = ph_read["phase"]
        # phase_v2_age_bars: 0 here (single-bar call); W2.3 backfill wave computes this
        # properly by replaying the series bar-by-bar. Placeholder value shipped as 0.
        phase_v2_age_bars = 0
        if _phase_pending is not None:
            _phase_pending.clear()
            _phase_pending.update(ph_read.get("pending") or {})
    except Exception:  # noqa: BLE001
        phase_v2 = phase  # fall back to legacy phase
        phase_v2_age_bars = 0

    # resolve_state: full stance/divergence/tone from the 5×8 crosswalk
    ladder_state = lad.get("state") or ""
    dc_phase = (res.get("cycle") or {}).get("dc_phase")
    failed_cycle = bool((res.get("cycle") or {}).get("failed_cycle"))
    try:
        if ladder_state in onto.LADDER:
            rs_out = onto.resolve_state(
                pos=pos_now, phase=phase_v2,
                phase_dir=ph_read.get("phase_dir", "rising"),
                ladder_state=ladder_state,
                dc_phase=dc_phase,
                failed_cycle=failed_cycle,
            )
            stance = rs_out["stance"]
            divergence = rs_out["divergence"]
            tone = rs_out["tone"]
        else:
            stance = divergence = tone = None
    except Exception:  # noqa: BLE001
        stance = divergence = tone = None

    return {
        "price": price_pts, "osc": osc_pts, "turns": swings, "proj": proj,
        "n_turns_all": len(swings_all),
        # W2.2: which structure basis this record's turns/osc/projection were computed on.
        # "tr" = legacy TR-only path; "price" = close_price structure basis; "tr_fallback"
        # = price requested but close_price missing → degraded to TR (never silent).
        "basis": basis,
        "now": {
            # ── Legacy fields (byte-identical to W0.3) ──
            "phase": phase, "phaseLabel": phase_label, "pos": round(pos_now, 1),
            "signal": signal, "osc_slope": round(osc_slope, 1),
            "timing_state": lad.get("state") or "", "action": lad.get("action") or "",
            "w_macd_up": bool((mtf.get("W") or {}).get("macd_pos")),
            "t3_macd_up": bool((mtf.get("3D") or {}).get("macd_pos")),
            "lastTrough": last_trough, "lastPeak": last_peak,
            "above200d": above200, "ret_win_pct": ret_win,
            "dc_phase": dc_phase,
            # W0.3: engine-owned read generated in build_sector/build_basket after RS is
            # available (set to None here; overwritten by _set_engine_read).
            "read": None, "read_zh": None,
            # ── W1.6: new ontology fields (additive) ──
            "pos_v2":          pos_v2,
            "phase_v2":        phase_v2,
            "phase_v2_age_bars": phase_v2_age_bars,
            "stance":          stance,
            "divergence":      divergence,
            "tone":            tone,
            # W2.2: structure basis (mirrored here for the forward-log writer)
            "basis":           basis,
        },
    }


def _set_engine_read(rec: dict) -> None:
    """W0.3: populate nw.read + nw.read_zh from the engine's own computed fields.
    Called AFTER _apply_leadership so RS data is present. Overrides the None sentinel
    set in _record_core — the engine now owns the read field (doctrine §1). The
    narrative.json 'now' string demoted to 'analyst_note' in the JS (see sector_cycles.js)."""
    nw = rec.get("now")
    if nw is None:
        return
    name = rec.get("name") or rec.get("ticker") or rec.get("id") or "Series"
    read_en, read_zh = _engine_read(
        name=name,
        phase=nw.get("phase") or "Expansion",
        pos=nw.get("pos") or 50.0,
        above200=bool(nw.get("above200d")),
        proj=rec.get("proj"),
        rs_63d=nw.get("rs_63d"),
        rs_rank=nw.get("rs_rank"),
    )
    nw["read"] = read_en
    nw["read_zh"] = read_zh


def _apply_leadership(rec: dict, lead: dict) -> None:
    """Fold RS-vs-SPY leadership into the record's `now` + a tailwind/headwind tilt."""
    nw = rec["now"]
    nw["rs_63d"] = lead.get("rs_63d")
    nw["rs_126d"] = lead.get("rs_126d")
    nw["rs_above_trend"] = lead.get("rs_above_trend")
    nw["thin_history"] = lead.get("thin_history", False)  # W2.8: surface instead of silent drop
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
                 win_start: pd.Timestamp,
                 closes_px: pd.DataFrame | None = None) -> dict | None:
    """One sector ETF -> its full cycle record (price, oscillator, turns, phase, projection).

    W2.2: `closes_px` = the price-basis (close_price) panel.  When present, the structure
    math runs on this ticker's close_price series; RS/momentum stays on the TR `closes`
    panel.  When a ticker is absent from `closes_px` (a declared close_price gap), the
    per-record basis is stamped tr_fallback — never silent.  closes_px=None → legacy TR."""
    full = closes[ticker].dropna() if ticker in closes else pd.Series(dtype=float)
    if len(full) < 300:
        log.warning("sector_cycles: %s too thin (%d rows) — skipped", ticker, len(full))
        return None
    price = _price_series(closes_px, ticker, full)
    core = _record_core(full, win_start, full.index[-1], price=price)
    if core is None:
        return None
    rec = dict(core)
    rec.update({"id": ticker.lower(), "ticker": ticker, "kind": "sector",
                "name": meta["name"], "short": meta["short"],
                "name_zh": meta.get("name_zh"), "short_zh": meta.get("short_zh"),
                "group": meta["group"], "group_zh": GROUP_ZH.get(meta["group"], meta["group"]),
                "accent": meta["accent"]})
    _apply_leadership(rec, _leadership(closes, ticker))
    _set_engine_read(rec)    # W0.3: populate engine-owned read after RS is available
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
    _set_engine_read(rec)    # W0.3: populate engine-owned read after RS is available
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
    close panel can't be loaded (build script then no-ops).

    W2.2: loads BOTH the TR panel (`closes`, momentum/RS basis) and the price panel
    (`closes_px`, structure basis = close_price).  The 11 sector ETFs flip their
    structure math (turns, oscillator, projection, DCL/failed-cycle) to close_price;
    RS-vs-SPY stays on TR.  Thematic baskets + amalgam families keep their existing
    member-TR candle (basis 'tr') — their member-level price-basis candle is out of
    W2.2 scope (owned by the frozen-basket-levels wave), so their turns do NOT move
    and are NOT re-keyed."""
    try:
        closes = yahoo_closes()
    except Exception as e:  # noqa: BLE001
        log.error("sector_cycles: cannot load yahoo_closes: %s", e)
        return None
    if closes is None or closes.empty:
        return None
    # price-basis panel for the structure math (never fatal — a load failure degrades
    # every sector to a labeled tr_fallback rather than crashing the build).
    try:
        closes_px = yahoo_closes(basis="price")
    except Exception as e:  # noqa: BLE001
        log.warning("sector_cycles: cannot load price-basis panel (%s) — structure math "
                    "falls back to TR (labeled tr_fallback)", e)
        closes_px = None
    if asof:
        closes = closes[closes.index <= pd.Timestamp(asof)]
        if closes_px is not None:
            closes_px = closes_px[closes_px.index <= pd.Timestamp(asof)]
    last_ts = closes.index[-1]
    win_start = last_ts - pd.DateOffset(years=WINDOW_YEARS)

    sectors = []
    for tk, meta in SECTORS.items():
        try:
            rec = build_sector(tk, meta, closes, win_start, closes_px=closes_px)
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
