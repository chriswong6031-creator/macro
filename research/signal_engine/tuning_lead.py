"""COUNT-NEUTRAL matched-event lead analysis (the decisive 'do we enter earlier?').

The raw per-signal stats in tuning_harness are confounded by signal COUNT: a trigger
that fires more often will look different for reasons unrelated to timing. This driver
isolates the owner's actual question -- "does the candidate enter the SAME move EARLIER
and at a BETTER price than the lagging 3D MACD?" -- by PAIRING each baseline buy with
the nearest candidate buy and measuring the lead (in trading days) and the entry-price
improvement. It is immune to the candidate simply firing more.

For each baseline (base3d) buy at daily fill bar fb (since SINCE):
  * find the nearest candidate buy whose fill bar fc is within [fb-WIN, fb+WIN]
  * lead_days   = fb - fc           (positive => candidate entered EARLIER)
  * price_impr  = base_px/cand_px-1 (positive => candidate entered CHEAPER/lower)
Plus coverage (fraction of baseline moves the candidate also caught) and the count of
EXTRA candidate buys with no baseline match (the cost of firing earlier = more entries).

Run:  python3 research/signal_engine/tuning_lead.py m2d_s3d_early
"""
from __future__ import annotations

import sys
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tuning_harness as H   # noqa: E402

WIN = 12   # trading-day window to call two buys "the same move"


def fills(daily: pd.Series, cfg: dict) -> list[int]:
    """Daily fill-bar indices of this variant's raw buys (since SINCE)."""
    fr = H.build_signals(daily, cfg)
    c_idx = fr.index
    out = []
    for i in np.where(fr["buy"].to_numpy())[0]:
        f = i + 1
        if f < len(c_idx) and c_idx[i] >= H.SINCE:
            out.append(f)
    return out


def analyze(cand: str, tickers=None) -> dict:
    base_cfg = H.VARIANTS["base3d"]
    cand_cfg = H.VARIANTS[cand]
    files = sorted(glob.glob(str(H.DATA / "*.parquet")))
    if tickers:
        files = [f for f in files if Path(f).stem in set(tickers)]
    leads, imprs = [], []
    n_base = n_matched = n_cand = n_extra = 0
    per = []
    for fp in files:
        t = Path(fp).stem
        try:
            daily = pd.read_parquet(fp)["close"].dropna()
            if len(daily) < 400:
                continue
            c = daily.to_numpy()
            bf = fills(daily, base_cfg)
            cf = fills(daily, cand_cfg)
            if not bf:
                continue
            n_base += len(bf)
            n_cand += len(cf)
            cf_arr = np.array(cf)
            used = set()
            ml, mi = [], []
            for f in bf:
                if len(cf_arr) == 0:
                    continue
                j = int(np.argmin(np.abs(cf_arr - f)))
                fc = int(cf_arr[j])
                if abs(fc - f) <= WIN and j not in used:
                    used.add(j)
                    n_matched += 1
                    ml.append(f - fc)                 # +ve = candidate earlier
                    mi.append(c[f] / c[fc] - 1)       # +ve = candidate cheaper
            n_extra += max(0, len(cf) - len(used))
            leads.extend(ml)
            imprs.extend(mi)
            if ml:
                per.append({"t": t, "lead": float(np.mean(ml)),
                            "impr": float(100 * np.mean(mi)), "n": len(ml)})
        except Exception:
            continue
    leads = np.array(leads) if leads else np.array([0.0])
    imprs = np.array(imprs) if imprs else np.array([0.0])
    return {
        "candidate": cand, "win": WIN,
        "base_buys": n_base, "cand_buys": n_cand,
        "matched": n_matched, "coverage_pct": round(100 * n_matched / max(n_base, 1), 1),
        "extra_cand_buys": n_extra,
        "lead_mean_days": round(float(leads.mean()), 2),
        "lead_median_days": round(float(np.median(leads)), 2),
        "pct_earlier": round(float(100 * (leads > 0).mean()), 1),
        "pct_same_or_earlier": round(float(100 * (leads >= 0).mean()), 1),
        "price_impr_mean_pct": round(float(100 * imprs.mean()), 2),
        "pct_cheaper": round(float(100 * (imprs > 0).mean()), 1),
        "names_earlier_avg": round(float(100 * np.mean([p["lead"] > 0 for p in per])), 1) if per else 0.0,
        "n_names": len(per),
    }


if __name__ == "__main__":
    cand = sys.argv[1] if len(sys.argv) > 1 else "m2d_s3d_early"
    print(json.dumps(analyze(cand), indent=1))
