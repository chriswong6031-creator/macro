#!/usr/bin/env python3
"""IMCE A1 — CELH fixed recognition telemetry (records only). NOT RUNTIME CODE.

This is a research reproduction receipt. Nothing imports it; no engine, collector,
workflow, page, or nightly path calls it. It exists so a future operator can
regenerate `celh_recognition_events.csv` / `celh_2w_state_full.csv` byte-for-byte
from the canonical price plane and verify that no outcome field was ever computed.

NAMED CONSTRUCTION (IMCE-00 freeze D3.1; prereg V1 §4 design-provenance law [A4]):

    bars      = engine.canon._resample_weekly(daily_close, "2W-FRI")
                (the house calendar 2-week bar; the SAME call the confluence
                 contract uses at engine/canon.py:492)
    macd      = engine.technicals.macd_hist semantics — classic 12-26-9:
                ema12 = close.ewm(span=12, min_periods=12).mean()
                ema26 = close.ewm(span=26, min_periods=26).mean()
                macd  = ema12 - ema26
                signal= macd.ewm(span=9, min_periods=9).mean()
                hist  = macd - signal        (asserted equal to macd_hist(w2))
    completed-bar semantics = canon's `.shift(1)` idiom: the state measured AT a
                bar's close is only ACTIONABLE from the next completed bar. Both
                dates are recorded (`bar_close_date`, `actionable_from`).

    This composes two EXISTING named house constructions. It mints no third MACD
    and no new indicator, per the construction-naming law.

INPUT PLANE (load-bearing): data/yahoo/CELH.parquet, column `close`, FULL history.
    `resample("2W-FRI")` bin boundaries depend on the series start, so truncating
    the input changes every bar. Do not slice before resampling.

ZERO OUTCOME COMPUTATION: this file contains no forward return, no horizon offset,
no +21d/+63d/+126d field, no win/hit rate, no p-value, no skill or accuracy metric.
Outcome fields may attach to these events only after the A4 criteria commit
(IMCE-00 freeze §13 A1; G8-B1 two-commit discipline).

Usage:  python3 research/imce/celh/celh_recognition_tape_2w.py [--repo REPO] [--out DIR]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

DEFAULT_REPO = pathlib.Path(__file__).resolve().parents[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--parquet", default=None,
                    help="override path to the CELH price plane (default <repo>/data/yahoo/CELH.parquet)")
    ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parent))
    args = ap.parse_args()

    repo = pathlib.Path(args.repo)
    sys.path.insert(0, str(repo))
    from engine.canon import _resample_weekly          # named 2W bar construction
    from engine.technicals import macd_hist            # named classic 12-26-9

    src = pathlib.Path(args.parquet) if args.parquet else repo / "data" / "yahoo" / "CELH.parquet"
    daily = pd.read_parquet(src)["close"]
    daily.index = pd.to_datetime(daily.index)
    print(f"input plane {src}: {len(daily)} daily bars "
          f"{daily.index[0].date()}..{daily.index[-1].date()}")

    w2, _ = _resample_weekly(daily, "2W-FRI")
    ema12 = w2.ewm(span=12, min_periods=12).mean()
    ema26 = w2.ewm(span=26, min_periods=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, min_periods=9).mean()
    hist = macd - signal
    ref = macd_hist(w2)
    assert hist.dropna().round(10).equals(ref.dropna().round(10)), \
        "histogram diverges from engine.technicals.macd_hist — construction violated"

    f = pd.DataFrame({"close_2w": w2, "macd": macd, "signal": signal, "hist": hist}).dropna()
    f["hist_sign"] = f["hist"].map(lambda v: "positive" if v > 0 else ("negative" if v < 0 else "zero"))
    d1 = f["hist"].diff()
    f["hist_d1"] = d1
    f["hist_d1_state"] = d1.map(
        lambda v: "not_available_for_date" if pd.isna(v)
        else ("expanding" if v > 0 else ("contracting" if v < 0 else "flat")))
    above = f["macd"] >= f["signal"]
    f["state"] = above.map({True: "bull", False: "bear"})
    prev = above.shift(1)
    f["cross"] = ""
    f.loc[above & (prev == False), "cross"] = "bullish_cross"    # noqa: E712
    f.loc[(~above) & (prev == True), "cross"] = "bearish_cross"  # noqa: E712
    f["actionable_from"] = list(f.index[1:]) + [pd.NaT]
    f["construction"] = "canon._resample_weekly(2W-FRI) + technicals.macd_hist(12-26-9), completed-bar shift(1)"
    f.index.name = "bar_close_date"

    out = pathlib.Path(args.out)
    full = f.reset_index()
    full.to_csv(out / "celh_2w_state_full.csv", index=False)
    ev = full[full["cross"] != ""]
    ev.to_csv(out / "celh_recognition_events.csv", index=False)

    forbidden = {"fwd", "forward", "ret", "return", "win", "hit", "pnl", "alpha", "skill", "pval"}
    assert not any(any(t in c.lower() for t in forbidden) for c in full.columns), \
        "outcome-shaped column detected — A1 forbids outcome computation"

    print(f"2W-FRI bars {len(w2)}; defined-histogram bars {len(f)} "
          f"(first {f.index[0].date()}; 26+9-bar warm-up, not a data gap)")
    print(f"cross events {len(ev)} "
          f"(bullish {(ev['cross'] == 'bullish_cross').sum()}, bearish {(ev['cross'] == 'bearish_cross').sum()})")
    print(f"autopsy window 2018-01-01+: {(ev['bar_close_date'] >= '2018-01-01').sum()} events")
    print(f"wrote {out/'celh_recognition_events.csv'} and {out/'celh_2w_state_full.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
