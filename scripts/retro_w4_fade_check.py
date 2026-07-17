"""scripts/retro_w4_fade_check.py — MLC-W4 charter-mandated retro-check.

Replays the histogram-fade-off-peak leg over the 2026-07-07 → 2026-07-13 window
for healthcare/pharma-family baskets + AI/semis complex.

DATA PATH: production path — per-member OHLCV via engine.basket_index._load_member_ohlcv
(data/baskets/ohlcv/<ticker>.parquet, fallback to data/stocks/, data/yahoo/), union
calendar via engine.basket_index.deep_calendar, equal-weight level via
engine.baskets._ew_level — exactly the same chain compute_theme_intel uses for the MTF
engines that need the deep tape (back to ~2014; 3000+ sessions, well above the 40-session
MACD warmup).

Note on fp/breadth inputs: rollover_risk is called with fp=None, fp5=None, breadth_d=None,
perf=None — these require live scoring state (RS pctile, member breadth breadth_d, etc.)
that is not reconstructable as-of from committed data alone. The BAND shown is therefore
the price-legs-only view of rollover_risk. The goal of this retro-check is the behaviour
of the NEW hist-fade leg; the other legs are absent but their absence is disclosed.

Run one-shot: python -m scripts.retro_w4_fade_check
NOT wired into any nightly workflow.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from engine.basket_index import _load_member_ohlcv, deep_calendar  # noqa: E402
from engine.baskets import _ew_level                                # noqa: E402
from engine.basket_score import _macd_hist_fade_leg, rollover_risk  # noqa: E402
from lib import config                                               # noqa: E402

_WINDOW_START = "2026-07-07"
_WINDOW_END   = "2026-07-13"

# Healthcare/pharma family + AI/semis complex (all must exist in membership.json)
_TARGET_BASKETS = [
    "big_pharma",
    "managed_care",
    "obesity_glp1",
    "us_sector_health",
    "ai_semiconductors",
    "semicap_equipment",
    "ai_infra",
    "memory_storage",
]


def _load_membership() -> dict:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        print(f"FATAL: membership.json not found at {p}")
        sys.exit(1)
    d = json.loads(p.read_text())
    bdict = d.get("baskets", {})
    if isinstance(bdict, list):
        bdict = {b["id"]: b for b in bdict}
    return bdict


def _build_level_from_ohlcv(bid: str, members: list) -> tuple[pd.Series | None, str]:
    """Build deep EW level series from per-member OHLCV.

    Returns (level_series_or_None, note_string).
    The note reports coverage gaps.
    """
    # Step 1: union trading calendar across all members
    idx = deep_calendar(members)
    if idx.empty:
        return None, "deep_calendar returned empty index (no OHLCV data for any member)"

    # Step 2: build per-member close matrix over the union calendar
    present_tickers = []
    close_cols: dict[str, pd.Series] = {}
    missing_ohlcv: list[str] = []
    partial_ohlcv: list[str] = []  # have data but not through 07-13

    window_end = pd.Timestamp(_WINDOW_END)

    for m in members:
        t = m["ticker"]
        df = _load_member_ohlcv(t)
        if df is None or "close" not in df.columns:
            missing_ohlcv.append(t)
            continue
        ser = df["close"].copy()
        ser.index = pd.DatetimeIndex(ser.index)
        if ser.index.max() < window_end:
            partial_ohlcv.append(f"{t}(to {ser.index.max().date()})")
        close_cols[t] = ser.reindex(idx).ffill()
        present_tickers.append(t)

    notes = []
    if missing_ohlcv:
        notes.append(f"NO_OHLCV: {missing_ohlcv}")
    if partial_ohlcv:
        notes.append(f"PARTIAL(before window end): {partial_ohlcv}")

    if len(present_tickers) < 3:
        note = f"ONLY {len(present_tickers)} members with OHLCV (<3 required); " + "; ".join(notes)
        return None, note

    # Step 3: build close DataFrame and compute returns
    closes = pd.DataFrame(close_cols, index=idx)
    rets = closes.pct_change(fill_method=None)

    # Step 4: equal-weight level via production function (point-in-time dated membership)
    lvl = _ew_level(rets, members, idx)

    note = ("; ".join(notes)) if notes else f"OK ({len(present_tickers)} members with OHLCV)"
    return lvl, note


def main() -> None:  # noqa: C901 (intentionally long — retro-check, not production)
    bdict = _load_membership()

    print("=" * 80)
    print("MLC-W4 Retro-check: histogram-fade-off-peak leg")
    print(f"Data path : engine.basket_index._load_member_ohlcv + engine.baskets._ew_level")
    print(f"Retro window : {_WINDOW_START} -> {_WINDOW_END} (business days in store)")
    print(f"fp/fp5/breadth/perf : ALL NULL — price-legs-only view of rollover_risk")
    print(f"                      (rs_pctile, breadth_d, perf inputs not reconstructable as-of)")
    print()

    # Collect business days in the window that actually appear in any basket's calendar
    # (we'll resolve per-basket below)

    col_hdr = (f"{'Basket':<22} {'Date':<12} {'StreakStart':<12} {'FadeSess':>9} "
               f"{'HistPeak':>9} {'HistCur':>9} {'Slope%':>9} {'LegFired':>9} "
               f"{'RollBand':>9}")
    print(col_hdr)
    print("-" * 115)

    first_fire_map: dict[str, str] = {}  # basket -> first date it fired

    for bid in _TARGET_BASKETS:
        if bid not in bdict:
            print(f"  {bid:<20}  NOT IN membership.json")
            continue

        members = bdict[bid].get("members", [])
        if not members:
            print(f"  {bid:<20}  NO MEMBERS IN BASKET")
            continue

        lvl_full, coverage_note = _build_level_from_ohlcv(bid, members)

        if lvl_full is None:
            print(f"  {bid:<20}  LEVEL BUILD FAILED: {coverage_note}")
            continue

        lvl_clean = lvl_full.dropna()
        if lvl_clean.empty:
            print(f"  {bid:<20}  LEVEL SERIES ALL-NaN")
            continue

        print(f"  {bid} — {coverage_note}")
        print(f"    Level series: {lvl_clean.index.min().date()} -> {lvl_clean.index.max().date()} "
              f"({len(lvl_clean)} non-NaN rows)")

        # Filter index to the retro window
        window_idx = lvl_full.index[
            (lvl_full.index >= pd.Timestamp(_WINDOW_START)) &
            (lvl_full.index <= pd.Timestamp(_WINDOW_END))
        ]

        if len(window_idx) == 0:
            # No rows in window — report what we can from full series
            print(f"    NOTE: NO rows in {_WINDOW_START}..{_WINDOW_END} in this basket's calendar")
            print(f"          Level store ends {lvl_clean.index.max().date()}; "
                  f"MACD warmup requires 40 rows (have {len(lvl_clean)}).")
            # Still run the leg on full history for reference
            fired, n_fade, peak_val, cur_val, slope = _macd_hist_fade_leg(lvl_clean)
            slope_pct = f"{slope*100:+.4f}" if slope is not None else "NULL"
            peak_str  = f"{peak_val:.5f}"   if np.isfinite(peak_val) else "NULL"
            cur_str   = f"{cur_val:.5f}"    if np.isfinite(cur_val)  else "NULL"
            rr = rollover_risk(lvl_clean, None, None, None, None)
            print(f"    As of {lvl_clean.index.max().date()} (most recent available):")
            print(f"      LegFired={fired}  n_fade(consec declines)={n_fade}  hist_peak={peak_str}  "
                  f"hist_cur={cur_str}  slope%={slope_pct}  band={rr['band']}")
            print(f"      Reasons: {rr['reasons']}")
            print()
            continue

        fired_dates = []
        for dt in window_idx:
            # Truncate level to <=dt (simulate day-of-compute)
            lvl_as_of = lvl_full[lvl_full.index <= dt].dropna()

            if len(lvl_as_of) < 40:
                print(
                    f"    {str(dt.date()):<12}  INSUFFICIENT HISTORY "
                    f"({len(lvl_as_of)} rows < 40 required for MACD warmup)"
                )
                continue

            fired, n_fade, peak_val, cur_val, slope = _macd_hist_fade_leg(lvl_as_of)
            rr = rollover_risk(lvl_as_of, None, None, None, None)

            slope_pct = f"{slope*100:+.4f}" if slope is not None else "NULL"
            peak_str  = f"{peak_val:.5f}"   if np.isfinite(peak_val) else "NULL"
            cur_str   = f"{cur_val:.5f}"    if np.isfinite(cur_val)  else "NULL"
            fade_str  = str(n_fade)         if fired else "NULL"

            # Compute the true MACD histogram peak date (the argmax in the 21-session window),
            # which is the start of the fade streak — n_fade counts consecutive declines AFTER
            # this date, so "fade-streak start" is the honest label (not "peak date").
            if fired:
                try:
                    _s = lvl_as_of.dropna()
                    _ema12 = _s.ewm(span=12, min_periods=12).mean()
                    _ema26 = _s.ewm(span=26, min_periods=26).mean()
                    _line  = _ema12 - _ema26
                    _sig   = _line.ewm(span=9, min_periods=9).mean()
                    _hist  = (_line - _sig).dropna()
                    _h     = _hist.to_numpy()
                    _n     = len(_h)
                    _win   = _h[max(0, _n - 21):]
                    _pidx  = max(0, _n - 21) + int(np.argmax(_win))
                    streak_start = str(_hist.index[_pidx].date())
                except Exception:
                    streak_start = "err"
            else:
                streak_start = "NULL"
            peak_date = streak_start  # column renamed to StreakStart in header

            print(
                f"    {str(dt.date()):<12}  {str(peak_date):<12} "
                f"{fade_str:>9} {peak_str:>9} {cur_str:>9} {slope_pct:>9} "
                f"{'YES' if fired else 'NO':>9} {rr['band']:>9}"
            )
            if rr["reasons"]:
                print(f"               reasons: {rr['reasons']}")

            if fired:
                fired_dates.append(dt.date())

        if fired_dates:
            first_fire_map[bid] = str(fired_dates[0])
            print(f"    *** LEG FIRST FIRED: {fired_dates[0]} ***")
        else:
            print(f"    LEG NEVER FIRED in {_WINDOW_START}..{_WINDOW_END} window")

        print()

    print("=" * 80)
    print("SUMMARY")
    print()
    fired_baskets = [bid for bid in _TARGET_BASKETS if bid in first_fire_map]
    null_baskets  = [bid for bid in _TARGET_BASKETS if bid not in first_fire_map]

    if fired_baskets:
        print("Baskets where leg FIRED in the 07-07..07-13 window:")
        for bid in fired_baskets:
            print(f"  {bid:<22}  first fire: {first_fire_map[bid]}")
    else:
        print("Leg did NOT fire for ANY basket in the 07-07..07-13 window.")

    if null_baskets:
        print()
        print("Baskets with NO fire in the window:")
        for bid in null_baskets:
            print(f"  {bid}")

    print()
    print("Interpretation:")
    print("  LegFired=YES  — all 3 conditions met: peak within 21 sess, >=3 consec fade,")
    print("                   10d-SMA slope negative.")
    print("  LegFired=NO   — one or more conditions unmet (see HistPeak/FadeSess/Slope%).")
    print("  NULL fields   — insufficient history or leg not fired.")
    print()
    print("Frozen parameters (MLC-W4; pre-registered-arbitrary):")
    print("  MACD(12, 26, 9)  |  Min history: 40 sess  |  Peak look-back: 21 sess")
    print("  Min fade run: 3 consec sess  |  SMA slope window: 10 sess / 5 sess lookback")
    print("  Leg weight in rollover_risk: 0.20 (additive; outside _rollover_weights calibration)")
    print()
    print("IMPORTANT: rollover_risk band shown is PRICE-LEGS-ONLY (fp/fp5/breadth/perf=None).")
    print("  Full band includes rs_pctile, breadth, perf legs which are not reconstructable")
    print("  from committed data as-of these dates.")


if __name__ == "__main__":
    main()
