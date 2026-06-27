"""ANTICIPATION-EXCEPTION surfacing diagnostic — variant (a) vs (b) vs union.

The grid wants an "anticipation exception": surface a stock that is IMMINENTLY forming the
confirmed confluence BUY (so the eye/brain catches it ~a few bars early), ranked BELOW a
confirmed TAKE (CHARTER §2: acting on the early leg is empirically WORSE entry quality, so the
exception is a SURFACING/eligibility rule, never a stronger-than-TAKE buy).

So the question here is NOT "does it make money" (that is the killed return-backtest, CHARTER §4)
and NOT "does it lower drawdown" (CONFLUENCE_TUNING.md already killed it as a tradeable trigger).
The question is purely: **does the anticipation marker reliably PRECEDE a confirmed base3d BUY,
and which form catches more imminent buys without drowning the grid in false alarms?**

Two forms (the owner's two options):
  (a) m2d_s3d_early    — StochRSI bottom-turn FROM oversold (<20) while the 2D MACD hist is
                          rising pre-cross.  [the in-engine `early` leg / early_now]
  (b) m2d_s3d_early_hi — StochRSI cross-up FROM ABOVE oversold while the 2D MACD has ALSO
                          crossed + weekly bull (the "doesn't always drop below 20" case).

Metrics, on the 114 held-out US names, signals since SINCE (leak-free, raw — no forward filter):
  RECALL_K     = % of confirmed base3d BUYs preceded by an anticipation marker within K bars
                 (also vs base3d TAKE buys — the ones the grid actually surfaces)
  PRECISION_K  = % of anticipation markers FOLLOWED by a base3d BUY within K bars
                 (1 - precision = false-alarm rate: markers that never become a buy)
  LEAD         = mean trading-day lead of the marker ahead of the buy it precedes
  MARKERS/name = chattiness

Run:  python3 research/signal_engine/tuning_anticipation.py [K]
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


def _bars(daily, variant, want_filter=False):
    """Signal-bar integer indices (since SINCE) for a variant's raw buys (or TAKE-filtered)."""
    fr = H.build_signals(daily, H.VARIANTS[variant],
                         high=None, low=None)
    if want_filter:
        col = H.daily_filter(fr)
        mask = col.to_numpy()
    else:
        mask = fr["buy"].to_numpy()
    idx = fr.index
    return [i for i in np.where(mask)[0] if idx[i] >= H.SINCE]


def _recall(truth, markers, K):
    """% of truth bars preceded by a marker in [b-K, b]; + mean lead of the nearest such."""
    if not truth:
        return None, None, 0
    m = np.array(markers)
    hit, leads = 0, []
    for b in truth:
        if len(m) == 0:
            continue
        prior = m[(m <= b) & (m >= b - K)]
        if len(prior):
            hit += 1
            leads.append(b - int(prior.max()))   # nearest preceding marker
    return 100 * hit / len(truth), (float(np.mean(leads)) if leads else None), hit


def _precision(markers, truth, K):
    """% of markers followed by a truth bar in [m, m+K] (1-this = false-alarm rate)."""
    if not markers:
        return None, 0
    t = np.array(truth)
    hit = 0
    for mk in markers:
        if len(t) == 0:
            continue
        if np.any((t >= mk) & (t <= mk + K)):
            hit += 1
    return 100 * hit / len(markers), hit


def run(K=10):
    files = sorted(glob.glob(str(H.DATA / "*.parquet")))
    rows = {"a": [], "b": [], "union": []}
    agg = {k: {"recall_raw": [], "recall_take": [], "prec": [], "lead": [],
               "markers": [], "n_buys": [], "n_takes": []} for k in rows}
    n_names = 0
    for fp in files:
        t = Path(fp).stem
        try:
            daily = pd.read_parquet(fp)["close"].dropna()
            if len(daily) < 400:
                continue
            base_raw = _bars(daily, "base3d", want_filter=False)
            base_take = _bars(daily, "base3d", want_filter=True)
            if not base_raw:
                continue
            n_names += 1
            ma = _bars(daily, "m2d_s3d_early")
            mb = _bars(daily, "m2d_s3d_early_hi")
            mu = sorted(set(ma) | set(mb))
            for key, mk in (("a", ma), ("b", mb), ("union", mu)):
                rr, lead, _ = _recall(base_raw, mk, K)
                rt, _, _ = _recall(base_take, mk, K)
                pr, _ = _precision(mk, base_raw, K)
                a = agg[key]
                if rr is not None: a["recall_raw"].append(rr)
                if rt is not None: a["recall_take"].append(rt)
                if pr is not None: a["prec"].append(pr)
                if lead is not None: a["lead"].append(lead)
                a["markers"].append(len(mk))
                a["n_buys"].append(len(base_raw))
                a["n_takes"].append(len(base_take))
        except Exception:
            continue

    def mean(x):
        return round(float(np.mean(x)), 1) if x else None

    out = {"K_bars": K, "n_names": n_names, "since": str(H.SINCE.date())}
    for key in ("a", "b", "union"):
        a = agg[key]
        out[key] = {
            "recall_raw_pct": mean(a["recall_raw"]),     # % base3d buys surfaced imminently
            "recall_take_pct": mean(a["recall_take"]),   # % base3d TAKEs surfaced imminently
            "precision_pct": mean(a["prec"]),            # % markers that become a buy
            "false_alarm_pct": round(100 - mean(a["prec"]), 1) if a["prec"] else None,
            "mean_lead_days": mean(a["lead"]),
            "markers_per_name": mean(a["markers"]),
            "buys_per_name": mean(a["n_buys"]),
            "takes_per_name": mean(a["n_takes"]),
        }
    out["legend"] = {
        "a": "m2d_s3d_early (from-OS, the in-engine early leg)",
        "b": "m2d_s3d_early_hi (from-above-OS + 2D cross)",
        "union": "fires if EITHER (a) or (b) fires",
    }
    return out


if __name__ == "__main__":
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(json.dumps(run(K), indent=1))
