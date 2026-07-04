"""Appendix A — EXPLORATORY zone-quality addendum (dev-only, non-registered).

Motivated by owner review: a buy zone is a STATE, not an event. Two metrics the
frozen SPEC did not include:

  1. fill_to_zone_low_40d — (min intraday LOW over bars t+2..t+41) / fill − 1.
     "How far below the fill did the zone ultimately trade" — punishes nothing
     for being early into a zone that held 4% lower, unlike a fixed race.
  2. vol-scaled race — same ±k close race as the charter metric, but
     k = clamp(1.0 × sigma20d × sqrt(20), 5%, 15%) per fire. Answers the
     "flat −5% is too tight for high-vol washouts" objection.

DEV FIRES ONLY (F1/P1, ≤2024-12-31). Holdout stays sealed: it was unlocked once
for the registered predictions; exploratory metrics do not get to fish in it.

Output: results/addendum_zone_metrics.csv (per-stratum table) + printed summary.
"""
from __future__ import annotations

import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from loader import load_massive_ticker  # noqa: E402

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)

DATA_ROOT = Path(__file__).resolve().parents[6] / "data"
DEV_END = pd.Timestamp("2024-12-31")
ZONE_BARS = 40
K_FLOOR, K_CAP = 0.05, 0.15
RACE_MAX = 131


def _one_ticker(args):
    ticker, fire_dates = args
    df = load_massive_ticker(ticker, DATA_ROOT)
    if df.empty:
        return []
    close, low = df["close"], df["low"]
    idx = close.index
    rets = close.pct_change()
    sig20 = rets.rolling(20).std()
    out = []
    for fd in fire_dates:
        pos = idx.searchsorted(pd.Timestamp(fd), side="right") - 1
        if pos < 0 or pos + 2 >= len(idx):
            continue
        fill = float(close.iloc[pos + 1])
        if not np.isfinite(fill) or fill <= 0:
            continue
        row = {"ticker": ticker, "fire_date": pd.Timestamp(fd)}

        # 1) zone low over next 40 sessions (intraday lows, after fill bar)
        lo_win = low.iloc[pos + 2: pos + 2 + ZONE_BARS]
        if len(lo_win) >= ZONE_BARS:
            row["fill_to_zone_low_40d"] = float(lo_win.min()) / fill - 1.0
        # 2) vol-scaled symmetric close race
        s = sig20.iloc[pos]
        if np.isfinite(s) and s > 0:
            k = float(np.clip(s * np.sqrt(20), K_FLOOR, K_CAP))
            row["k_used"] = k
            c_win = close.iloc[pos + 2: pos + 2 + RACE_MAX].to_numpy(dtype=float)
            res = None
            for c in c_win:
                r = c / fill - 1.0
                if r <= -k:
                    res = 1
                    break
                if r >= k:
                    res = 0
                    break
            if res is None and len(c_win) >= RACE_MAX:
                res = 0  # mature non-stop
            row["vol_race_stop"] = res
        out.append(row)
    return out


def main() -> None:
    fires = pd.read_parquet(HERE / "results" / "fires_with_metrics_p1.parquet")
    fires["fire_date"] = pd.to_datetime(fires["fire_date"])
    dev = fires[(fires["fire_date"] <= DEV_END) & (fires["fire_type"] == "F1")
                & (fires["contiguity_ok"] != False)].copy()  # noqa: E712
    print(f"dev F1/P1 fires: {len(dev)}")

    jobs = [(t, g["fire_date"].tolist()) for t, g in dev.groupby("ticker")]
    rows = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        for chunk in ex.map(_one_ticker, jobs, chunksize=64):
            rows.extend(chunk)
    add = pd.DataFrame(rows)
    dev = dev.merge(add, on=["ticker", "fire_date"], how="left")
    print(f"addendum coverage: zone_low {dev['fill_to_zone_low_40d'].notna().mean():.1%}, "
          f"vol_race {dev['vol_race_stop'].notna().mean():.1%}, "
          f"median k = {dev['k_used'].median():.3f}")

    has3 = (dev["cohort_frac_w"].notna() & dev["rs_spy_slope20"].notna()
            & dev["loc60_15"].notna())
    strata = {
        "S7 cohort-rank REPAIR":  dev["rs_cohort_rank_slope20"] == 1,
        "S7 cohort-rank DETER":   dev["rs_cohort_rank_slope20"] == 0,
        "H-B computable baseline": has3,
        "cohort>=40":             has3 & (dev["cohort_frac_w"] >= 0.40),
        "TRIPLE-LOCK":            (has3 & (dev["cohort_frac_w"] >= 0.40)
                                   & (dev["rs_spy_slope20"] == 1)
                                   & (dev["loc60_15"] == 1)),
        "ALL dev F1":             pd.Series(True, index=dev.index),
    }
    out_rows = []
    hdr = (f"{'stratum':<26} {'n':>6} {'med_zone_low40':>14} {'pct_within_5%':>13} "
           f"{'pct_within_8%':>13} {'vol_race_stop':>13} {'med_k':>6}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for name, mask in strata.items():
        sub = dev[mask.fillna(False)]
        zl = sub["fill_to_zone_low_40d"].dropna()
        vr = sub["vol_race_stop"].dropna()
        r = {
            "stratum": name,
            "n": len(sub),
            "med_zone_low_40d": zl.median(),
            "pct_zone_within_5": float((zl > -0.05).mean()) if len(zl) else np.nan,
            "pct_zone_within_8": float((zl > -0.08).mean()) if len(zl) else np.nan,
            "vol_race_stop": float((vr == 1).mean()) if len(vr) else np.nan,
            "med_k": sub["k_used"].median(),
        }
        out_rows.append(r)
        print(f"{name:<26} {r['n']:>6} {r['med_zone_low_40d']:>14.3f} "
              f"{r['pct_zone_within_5']:>13.3f} {r['pct_zone_within_8']:>13.3f} "
              f"{r['vol_race_stop']:>13.3f} {r['med_k']:>6.3f}")

    pd.DataFrame(out_rows).to_csv(HERE / "results" / "addendum_zone_metrics.csv",
                                  index=False)
    print("\nsaved results/addendum_zone_metrics.csv")


if __name__ == "__main__":
    main()
