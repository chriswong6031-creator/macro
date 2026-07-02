"""Leakage-tax shadow harness — the first client of the PIT truth layer (W1b).

SHADOW ONLY. Recomputes the growth/inflation axes + quad history on the leak-free
point-in-time 'release' frame (via the parameterized engine.inputs.build_features)
and diffs it against the live ('latest') frame. NOTHING here touches a live artifact
or the render critical path — it is a standalone script that writes one measurement
product, calibration/leakage_tax.json.

The premise (masterplan W1b): we do NOT migrate the 404 engines onto PIT. We MEASURE
the timing+revision look-ahead the live regime carries and publish it, so each engine's
passport can be flipped honestly (frame: latest -> demoted) if its PIT edge collapses.

What it measures:
  1. Per-leg availability shift — how many days earlier the live axis "knew" each
     revision-prone econ leg (the raw look-ahead removed by PIT).
  2. Quad-label agreement % (PIT vs latest), overall and by year.
  3. Flip-date drift — for each quad transition, how many days earlier/later the flip
     occurs on the PIT frame (distribution).
  4. Split-half edge delta — a simple quad->SPY directional backtest run on both frames,
     with a paired bootstrap CI on the Sharpe difference. Answers: how much of the
     regime's claimed edge survives once the look-ahead is removed?

Run:
  python -m scripts.shadow_pit_regime            # last 5y (default, cheap)
  python -m scripts.shadow_pit_regime --full     # full PIT-covered history
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# the PIT frame build inserts many columns one at a time (mirrors the live build);
# the fragmentation is cosmetic for a shadow harness that runs occasionally.
warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import pit  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from engine.regime import classify  # noqa: E402
from engine.validation import block_bootstrap_ci, paired_delta_ci  # noqa: E402
from lib import config  # noqa: E402

# quad -> directional exposure for the edge backtest. Q1 Goldilocks / Q2 Reflation are
# the risk-on growth-accelerating quads (long); Q3 Stagflation / Q4 Growth-scare are
# risk-off (flat). This is the coarsest honest read of "does the quad time SPY" — the
# point is the DELTA between frames, not the absolute Sharpe.
QUAD_EXPOSURE = {"Q1": 1.0, "Q2": 1.0, "Q3": 0.0, "Q4": 0.0}
COST_BPS = 2.0


def _exposure(quad: pd.Series) -> pd.Series:
    return quad.map(QUAD_EXPOSURE).astype(float)


def _availability_shift() -> dict:
    """Per-leg: the release lag PIT removes. For vintaged legs this is realtime_start −
    period (the true look-ahead the live axis had). For calendar legs it is the modelled
    lag_bd. Reported in days."""
    v = pit._vintages()
    out = {}
    for sid, col in pit.VINTAGED_SID_TO_COL.items():
        if v is None or v.empty or not (v["series"] == sid).any():
            continue
        s = v[v["series"] == sid]
        lag = (s["realtime_start"] - s["period"]).dt.days
        out[col] = {
            "source": "vintage",
            "median_lag_days": round(float(lag.median()), 1),
            "p90_lag_days": round(float(lag.quantile(0.9)), 1),
            "max_lag_days": int(lag.max()),
            "n": int(len(s)),
        }
    lags = pit._release_lags()
    for col, spec in lags.items():
        if col in out:
            continue
        out[col] = {
            "source": "calendar_prior",
            "modelled_lag_bd": spec.get("lag_bd"),
            "cadence": spec.get("cadence"),
            "note": spec.get("note"),
        }
    return out


def _quad_agreement(live: pd.Series, pit_q: pd.Series) -> dict:
    j = pd.concat([live.rename("live"), pit_q.rename("pit")], axis=1).dropna()
    if j.empty:
        return {"overall_pct": None, "n": 0, "by_year": {}}
    agree = (j["live"] == j["pit"])
    by_year = {}
    for yr, g in agree.groupby(j.index.year):
        by_year[int(yr)] = {"agree_pct": round(100.0 * float(g.mean()), 1), "n": int(len(g))}
    # confusion: where they disagree, what does PIT say instead
    dis = j[~agree]
    confusion = {}
    if not dis.empty:
        for (lv, pv), cnt in dis.groupby(["live", "pit"]).size().items():
            confusion[f"{lv}->{pv}"] = int(cnt)
    return {
        "overall_pct": round(100.0 * float(agree.mean()), 1),
        "n": int(len(j)),
        "by_year": by_year,
        "disagreement_confusion_live_to_pit": dict(sorted(
            confusion.items(), key=lambda kv: -kv[1])),
    }


def _flip_dates(quad: pd.Series) -> pd.DataFrame:
    """Transition table: rows where the confirmed quad changes value."""
    q = quad.dropna()
    chg = q.ne(q.shift())
    flips = q[chg]
    # drop the first (warm-up) point
    flips = flips.iloc[1:]
    return pd.DataFrame({"date": flips.index, "to_quad": flips.values})


def _flip_drift(live: pd.Series, pit_q: pd.Series, tol_days: int = 45) -> dict:
    """For each PIT flip, find the nearest live flip TO THE SAME QUAD within tol_days and
    report the signed day gap (pit_date − live_date). Negative = PIT flips earlier."""
    lf = _flip_dates(live)
    pf = _flip_dates(pit_q)
    if lf.empty or pf.empty:
        return {"n_pit_flips": int(len(pf)), "n_live_flips": int(len(lf)),
                "matched": 0, "note": "too few flips to match"}
    drifts = []
    unmatched_pit = 0
    for _, prow in pf.iterrows():
        cand = lf[lf["to_quad"] == prow["to_quad"]]
        if cand.empty:
            unmatched_pit += 1
            continue
        gaps = (prow["date"] - cand["date"]).dt.days
        near = gaps.reindex(gaps.abs().sort_values().index).iloc[0]
        if abs(near) <= tol_days:
            drifts.append(int(near))
        else:
            unmatched_pit += 1
    if not drifts:
        return {"n_pit_flips": int(len(pf)), "n_live_flips": int(len(lf)),
                "matched": 0, "unmatched_pit_flips": unmatched_pit,
                "note": "no PIT flips matched a same-quad live flip within tolerance"}
    arr = np.array(drifts)
    return {
        "n_pit_flips": int(len(pf)),
        "n_live_flips": int(len(lf)),
        "matched": int(len(drifts)),
        "unmatched_pit_flips": int(unmatched_pit),
        "median_drift_days": round(float(np.median(arr)), 1),
        "mean_drift_days": round(float(arr.mean()), 1),
        "p10_p90_drift_days": [int(np.percentile(arr, 10)), int(np.percentile(arr, 90))],
        "pct_pit_later": round(100.0 * float((arr > 0).mean()), 1),
        "pct_pit_earlier": round(100.0 * float((arr < 0).mean()), 1),
        "note": ("Signed gap pit_date − live_date, matched to nearest same-quad live "
                 "flip within %d days. Positive = the PIT (leak-free) flip lands LATER "
                 "than the live one, i.e. the live regime called the turn before the "
                 "data was available." % tol_days),
    }


def _split_half_edge(quad: pd.Series, spy: pd.Series, split: pd.Timestamp) -> dict:
    """Directional quad->SPY backtest, reported full / pre-split / post-split. Exposure is
    shifted one bar (act on yesterday's confirmed quad) to avoid same-bar look-ahead."""
    ret = spy.pct_change().reindex(quad.index)
    expo = _exposure(quad).shift(1)
    j = pd.concat([expo.rename("e"), ret.rename("r")], axis=1).dropna()
    if len(j) < 60:
        return {"n": len(j), "note": "too short"}
    turnover = j["e"].diff().abs().fillna(0)
    net = j["e"] * j["r"] - turnover * (COST_BPS / 1e4)

    def _stats(r: pd.Series) -> dict:
        r = r.dropna()
        if len(r) < 30:
            return {"n": len(r), "sharpe": None, "cagr_pct": None}
        sd = float(r.std())
        sh = float(r.mean() / sd * np.sqrt(252)) if sd else None
        eq = float((1 + r).prod())
        yrs = len(r) / 252.0
        cagr = (eq ** (1 / yrs) - 1) if (yrs > 0 and eq > 0) else None
        return {"n": int(len(r)), "sharpe": round(sh, 3) if sh is not None else None,
                "cagr_pct": round(100 * cagr, 2) if cagr is not None else None}

    pre = net[net.index < split]
    post = net[net.index >= split]
    return {"net": net, "full": _stats(net), "pre": _stats(pre), "post": _stats(post)}


def run(full: bool = False) -> dict:
    cfg_span = None
    live_f = build_features(pit_basis="latest")
    pit_f = build_features(pit_basis="release")

    # restrict to the window where the PIT frame actually has econ coverage: the axes
    # need the monthly legs, which only exist from the first vintage release onward.
    live_r = classify(live_f)
    pit_r = classify(pit_f)

    # the analysis span: PIT-covered dates only (a leak-free frame can't score pre-1997
    # growth). Default: last 5 years for a cheap run; --full = whole covered span.
    live_q = live_r["quad"].dropna()
    pit_q = pit_r["quad"].dropna()
    covered_start = pit_q.first_valid_index()
    end = pit_q.index.max()
    if not full:
        five_y = end - pd.DateOffset(years=5)
        start = max(covered_start, five_y)
    else:
        start = covered_start
    win = (slice(start, end))
    live_qw = live_q.loc[win]
    pit_qw = pit_q.loc[win]
    cfg_span = f"{start.date()}..{end.date()}"

    # 1. availability shift (independent of window)
    avail = _availability_shift()

    # 2. quad agreement
    agreement = _quad_agreement(live_qw, pit_qw)

    # 3. flip drift
    drift = _flip_drift(live_qw, pit_qw)

    # 4. split-half edge on both frames
    spy = live_f["SPY"].dropna()
    split = start + (end - start) / 2
    live_bt = _split_half_edge(live_qw, spy, split)
    pit_bt = _split_half_edge(pit_qw, spy, split)
    edge_delta = {}
    if "net" in live_bt and "net" in pit_bt:
        # paired bootstrap of PIT edge − live edge (does removing the leak cost Sharpe?)
        pd_ci = paired_delta_ci(pit_bt["net"], live_bt["net"], block=21, B=3000)
        edge_delta = {
            "live_frame": {k: v for k, v in live_bt.items() if k != "net"},
            "pit_frame": {k: v for k, v in pit_bt.items() if k != "net"},
            "paired_delta_pit_minus_live": pd_ci,
            "split_date": str(split.date()),
            "note": ("Quad->SPY directional backtest (Q1/Q2 long, Q3/Q4 flat), exposure "
                     "shifted 1 bar, %.0fbps cost. delta = PIT − live Sharpe/Calmar; a "
                     "NEGATIVE, CI-excludes-0 delta means the live edge was partly a "
                     "look-ahead artifact. Coarse by design — the frame DELTA is the "
                     "signal, not the absolute number." % COST_BPS),
        }

    coverage = pit.coverage_report()

    return {
        "meta": {
            "generated": pd.Timestamp.now("UTC").isoformat(),
            "mode": "full" if full else "last_5y",
            "analysis_span": cfg_span,
            "pit_covered_from": str(covered_start.date()),
            "n_days_analyzed": int(len(pit_qw)),
            "shadow_only": True,
            "note": ("Leak-free 'release' frame vs live 'latest' frame. Growth/inflation "
                     "axes recomputed on both via engine.inputs.build_features(pit_basis) "
                     "— same axis math, injected frame. No live artifact touched."),
        },
        "vintage_coverage": coverage,
        "availability_shift_days": avail,
        "quad_agreement": agreement,
        "flip_date_drift": drift,
        "split_half_edge_delta": edge_delta,
        "headline": _headline(agreement, drift, avail, edge_delta, coverage),
    }


def _headline(agreement, drift, avail, edge_delta, coverage) -> dict:
    # biggest-leak legs = vintaged legs with the largest median release lag
    vintaged = {c: d for c, d in avail.items() if d.get("source") == "vintage"}
    biggest = sorted(vintaged.items(),
                     key=lambda kv: -(kv[1].get("median_lag_days") or 0))[:4]
    ds_ci = (edge_delta.get("paired_delta_pit_minus_live") or {}).get("delta_sharpe_ci")
    return {
        "quad_agreement_pct": agreement.get("overall_pct"),
        "flip_median_drift_days": drift.get("median_drift_days"),
        "flip_pct_pit_later": drift.get("pct_pit_later"),
        "biggest_leak_legs": [
            {"leg": c, "median_release_lag_days": d.get("median_lag_days")}
            for c, d in biggest],
        "split_half_delta_sharpe_ci_pit_minus_live": ds_ci,
        "vintage_store_gaps": coverage.get("vintage_store_gaps"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                    help="analyze the full PIT-covered span (default: last 5y)")
    ap.add_argument("--out", default=None, help="output path (default calibration/leakage_tax.json)")
    args = ap.parse_args()

    report = run(full=args.full)

    out = Path(args.out) if args.out else (config.data_dir().parent / "calibration" / "leakage_tax.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))

    h = report["headline"]
    print(f"\n=== LEAKAGE TAX ({report['meta']['analysis_span']}, "
          f"{report['meta']['n_days_analyzed']} days, {report['meta']['mode']}) ===")
    print(f"quad agreement PIT vs latest : {h['quad_agreement_pct']}%")
    print(f"flip median drift (pit-live) : {h['flip_median_drift_days']}d  "
          f"({h['flip_pct_pit_later']}% of PIT flips land later)")
    print("biggest-leak legs (median release lag):")
    for leg in h["biggest_leak_legs"]:
        print(f"  {leg['leg']:14s} {leg['median_release_lag_days']}d")
    print(f"split-half ΔSharpe CI (PIT−live): {h['split_half_delta_sharpe_ci_pit_minus_live']}")
    print(f"vintage store gaps: {len(h['vintage_store_gaps'])} legs -> "
          f"{', '.join(h['vintage_store_gaps'][:6])}...")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
