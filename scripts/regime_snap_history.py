"""Regime-snap detector — historical verification harness (engine/regime_snap.py).

Runs the DISPLAY-ONLY relief-snap detector over the full available history and
prints the days it fires, so the calls can be eyeballed against the canonical
relief events BEFORE any response logic is wired. This is NOT yet a Phase-0
predictive validation (no FDR / Deflated-Sharpe / split-half); it is a
"does it fire where it should, and how often" sanity check. The forward-return
block is a coarse sanity read only — overlapping windows, no multiple-testing
correction — explicitly not an edge claim.

Usage:
  python scripts/regime_snap_history.py
  REGIME_SNAP_DATA_DIR=/path/to/another/checkout/data python scripts/regime_snap_history.py
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # import our own engine

from lib import config  # noqa: E402

_DATA_OVERRIDE = os.environ.get("REGIME_SNAP_DATA_DIR")
if _DATA_OVERRIDE:
    _p = Path(_DATA_OVERRIDE)
    config.data_dir = lambda: _p  # type: ignore[assignment]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.inputs import build_features  # noqa: E402
from engine.conditions import conditions_frame  # noqa: E402
from engine import regime_snap  # noqa: E402

# Canonical relief episodes the detector should light up on (name -> window).
EVENTS = [
    ("2018 Q4 selloff -> Jan-19 relief", "2018-12-01", "2019-02-15"),
    ("COVID crash + bottom/snapback", "2020-02-20", "2020-05-15"),
    ("2022 bear: CPI / Oct relief rallies", "2022-07-01", "2022-11-30"),
    ("SVB resolution (Mar-23)", "2023-03-10", "2023-04-15"),
    ("2024 yen-carry unwind snapback", "2024-08-02", "2024-09-05"),
    ("2025 tariff selloff -> relief", "2025-04-01", "2025-06-15"),
]


def _episodes(snap: pd.Series) -> list[pd.Timestamp]:
    """Start date of each fire episode (a fire day whose prior day didn't fire)."""
    s = snap.fillna(0).astype(int)
    starts = s[(s == 1) & (s.shift(1).fillna(0) == 0)]
    return list(starts.index)


def main() -> None:
    cfg = regime_snap._cfg()
    print("=" * 78)
    print("REGIME-SNAP DETECTOR — historical verification (DISPLAY-ONLY)")
    print("data_dir:", config.data_dir())
    print("config:", {k: cfg[k] for k in cfg})
    print("=" * 78)

    f = build_features()
    cf = conditions_frame(f)
    sf = regime_snap.snap_frame(cf, cfg)
    spy = f["SPY"].reindex(sf.index)

    legs = [k for k in regime_snap._LEG_KEYS if f"roro_{k}" in cf.columns]
    print(f"frame: {str(sf.index.min())[:10]} -> {str(sf.index.max())[:10]}  "
          f"rows={len(sf)}  RORO legs present={legs}")
    valid = sf["vel_pctile"].notna()
    print(f"detector live from {str(sf.index[valid][0])[:10]} "
          f"(needs velocity-percentile warmup)\n")

    snap = sf["snap"]
    fired = sf[snap == 1]
    eps = _episodes(snap)
    print(f"TOTAL fire-days: {int(snap.sum())}   EPISODES (deduped): {len(eps)}")
    yr = fired.groupby(fired.index.year).size()
    print("fire-days by year:", {int(k): int(v) for k, v in yr.items()})
    live_yrs = sf[valid].index.year.nunique()
    print(f"=> ~{len(eps) / max(live_yrs, 1):.1f} episodes/yr over {live_yrs} live years\n")

    # forward-return sanity (episode-start days only; overlapping -> coarse) --------
    print("-" * 78)
    print("FORWARD SPY RETURN after an episode start (coarse sanity, NOT an edge claim)")
    print(f"{'horizon':>8} | {'snap mean':>10} {'snap hit%':>9} {'n':>4} | "
          f"{'base mean':>10} {'base hit%':>9}")
    for h in (5, 21, 63):
        fwd = spy.shift(-h) / spy - 1.0
        ep_idx = pd.DatetimeIndex(eps)
        sv = fwd.reindex(ep_idx).dropna()
        bv = fwd.dropna()
        if len(sv):
            print(f"{h:>6}d  | {sv.mean() * 100:>9.2f}% {(sv > 0).mean() * 100:>8.0f}% "
                  f"{len(sv):>4} | {bv.mean() * 100:>9.2f}% {(bv > 0).mean() * 100:>8.0f}%")
    print("-" * 78 + "\n")

    # canonical events -------------------------------------------------------------
    def fmt_legs(row) -> str:
        return ",".join(k for k in legs if bool(row.get(f"{k}_flip", False)))

    for name, a, b in EVENTS:
        win = sf.loc[a:b]
        if win.empty:
            print(f"[{name}]  (no data in window)\n")
            continue
        hits = win[win["snap"] == 1]
        print(f"[{name}]  {a}..{b}  -> {len(hits)} fire-day(s)")
        if not hits.empty:
            # peak-relief day in the window
            for dt, r in hits.iterrows():
                print(f"    {str(dt)[:10]}  relief={int(r['relief_magnitude']):3d}  "
                      f"legs_up={int(r['legs_up'])}/{int(r['legs_total'])}  "
                      f"velΔ={r['roro_velocity']:+.2f}  fear_built={r['fear_built']:.2f}  "
                      f"[{fmt_legs(r)}]")
        else:
            # show how close it came on the strongest day
            near = win.loc[win["roro_velocity"].idxmax()]
            print(f"    (nearest miss {str(win['roro_velocity'].idxmax())[:10]}: "
                  f"vel_pct={near['vel_pctile']:.2f} legs_up={int(near['legs_up'])} "
                  f"fear_built={near['fear_built']:.2f})")
        print()

    # most recent episodes ---------------------------------------------------------
    print("-" * 78)
    print("MOST RECENT 12 episodes:")
    for dt in eps[-12:]:
        r = sf.loc[dt]
        print(f"    {str(dt)[:10]}  relief={int(r['relief_magnitude']):3d}  "
              f"legs_up={int(r['legs_up'])}/{int(r['legs_total'])}  "
              f"velΔ={r['roro_velocity']:+.2f}  fear_built={r['fear_built']:.2f}  "
              f"[{fmt_legs(r)}]")

    print("\nlatest snapshot:", regime_snap.snap_snapshot(cf, cfg))


if __name__ == "__main__":
    main()
