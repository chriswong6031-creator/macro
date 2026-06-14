"""Calibrate + validate the multi-timeframe Bottom-Confidence score.

Walk-forward over the deep-history names (data/stocks/*, ~40y, no look-ahead,
600-day trailing window — same machinery as calibrate_ladder / entry_quality),
computing the LIVE engine `bottom_confidence` at each bottoming-state evaluation
and bucketing the forward outcome by score band. Honest lens (D43): forward
DRAWDOWN p10 + "cycle-low held over 21d" (the durability the score claims), NOT
endpoint return. Writes data/regime/bottom_confidence_calibration.json (shipped to
the UI like ladder_calibration.json) and prints the validation table — the score
is only worth surfacing if held-rate rises monotonically with the band.

Usage: python -m scripts.calibrate_bottom_confidence
"""
from __future__ import annotations
import json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from engine.cycles import (cycle_state, mtf_snapshot, early_signals, ladder_state,
                           regime_state, entry_quality, bottom_confidence,
                           macd_parts, stoch_rsi)
from lib import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("calibrate_bc")

WIN, STEP, FWD = 600, 10, 21
BANDS = [("0-20", 0, 20), ("20-40", 20, 40), ("40-60", 40, 60), ("60+", 60, 101)]


def _monthly_turnup(close: pd.Series) -> pd.Series:
    """Month-end-indexed bool of whether the MONTHLY bar is 'turning up' (same
    flags _tf_turning_up reads). Precomputed ONCE per name and asof-looked-up per
    eval — a 600-day window is too short for the monthly bar (mtf_snapshot gates it
    at >900d), so we inject this instead of re-resampling 950 bars every step."""
    m = close.resample("ME").last().dropna()
    if len(m) < 40:
        return pd.Series(dtype=bool)
    h = macd_parts(m)["hist"].to_numpy(); sv = stoch_rsi(m).to_numpy()
    out = {}
    for j in range(3, len(m)):
        if np.isnan(h[j]) or np.isnan(h[j - 1]) or np.isnan(h[j - 2]):
            continue
        cross = h[j] > 0 and (h[j - 3:j] <= 0).any()
        curl = h[j] < 0 and h[j] > h[j - 1] <= h[j - 2]
        appr = h[j] < 0 and h[j] > h[j - 1] > h[j - 2] and (h[j] - h[j - 3]) / 3 > 0
        stp = (not np.isnan(sv[j])) and j >= 4 and sv[j] >= 20 and (sv[j - 3:j] < 20).any()
        out[m.index[j]] = bool(cross or curl or appr or stp)
    return pd.Series(out)


def main() -> int:
    data = config.data_dir() / "stocks"
    buckets = {b[0]: [] for b in BANDS}
    n_inst = 0
    files = sorted(data.glob("*.parquet"))
    for fi, f in enumerate(files):
        if (fi + 1) % 20 == 0:
            log.info("...%d/%d names", fi + 1, len(files))
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        close = df["close"].dropna(); high = df.get("high")
        if len(close) < WIN + FWD + 50:
            continue
        n_inst += 1; cv = close.to_numpy()
        mflags = _monthly_turnup(close)          # precomputed once per name
        for i in range(WIN, len(close) - FWD - 1, STEP):
            sub = close.iloc[i - WIN:i + 1]
            hsub = high.reindex(sub.index) if high is not None else None
            try:
                cyc = cycle_state(sub, hsub, "equity")
                if not cyc:
                    continue
                mtf = mtf_snapshot(sub, "equity")
                # inject the precomputed monthly bar (the 600d window omits it) so the
                # calibrated score matches the LIVE engine, which sees full history.
                if len(mflags):
                    mu = mflags.asof(close.index[i])
                    mtf["M"] = {"macd_cross_up": bool(mu)} if pd.notna(mu) else {}
                early = early_signals(sub, cyc, mtf)
                lad = ladder_state(cyc, mtf, early)
                if not lad:
                    continue
                reg = regime_state(cyc, mtf)
                eq = entry_quality(sub, cyc, mtf, early, reg, state=lad["state"])
                bc = bottom_confidence(mtf, eq, lad["state"])
            except Exception:
                continue
            if not bc:
                continue
            p0 = cv[i]
            dd = cv[i + 1:i + 1 + FWD].min() / p0 - 1.0
            ret = cv[i + FWD] / p0 - 1.0
            low = cyc.get("cand_price") or cyc.get("dcl_price") or p0
            held = float(cv[i + 1:i + 1 + FWD].min() >= low)
            s = bc["score"]
            for name, lo, hi in BANDS:
                if lo <= s < hi:
                    buckets[name].append((ret, dd, held)); break
    out = {}
    print(f"\n=== Bottom-Confidence calibration: {n_inst} names ===")
    print(f"{'band':6s} {'n':>6s} {'held21':>7s} {'dd_p10':>7s} {'dd_med':>7s} {'ret21':>7s}")
    for name, _, _ in BANDS:
        v = buckets[name]
        if len(v) < 40:
            print(f"{name:6s} {len(v):>6d}  (thin)"); continue
        a = np.array(v)
        rec = {"n": len(a), "held_pct": round(100 * a[:, 2].mean(), 1),
               "dd_p10_pct": round(100 * np.percentile(a[:, 1], 10), 2),
               "dd_med_pct": round(100 * np.median(a[:, 1]), 2),
               "ret_med_pct": round(100 * np.median(a[:, 0]), 2)}
        out[name] = rec
        print(f"{name:6s} {rec['n']:>6d} {rec['held_pct']:>6}% {rec['dd_p10_pct']:>7} "
              f"{rec['dd_med_pct']:>7} {rec['ret_med_pct']:>7}")
    p = config.data_dir() / "regime" / "bottom_confidence_calibration.json"
    p.write_text(json.dumps({"fwd": FWD, "bands": out}, indent=1))
    log.info("wrote %s", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
