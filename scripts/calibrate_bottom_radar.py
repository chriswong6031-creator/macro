"""Calibrate + validate the Bottom-formation Radar (engine/bottom_radar) — the GO/NO-GO
gate for the anticipation tier (research/ANTICIPATION_ENGINE_DESIGN.md).

Walk-forward over the deep-history names (data/stocks/*, full OHLCV+volume, 600-day
trailing window, no look-ahead — same machinery as calibrate_bottom_confidence). At each
bottoming-state eval it computes the LIVE radar raw score + stage + vetos, then labels
the forward outcome as a STOP-aware R-multiple:
  entry  = close[i]
  stop   = (candidate/cycle low) * (1 - buffer)
  win    = forward path reaches +X% BEFORE touching the stop  (R = X / risk)
  loss   = forward path touches the stop first                (R = -1)
  timeout= neither within N bars                              (R = endpoint_ret / risk)
durable_bottom = win. We measure, OUT OF SAMPLE only:
  (1) CALIBRATION: raw-score decile -> realized durable rate (must rise monotonically).
  (2) PER-STAGE EXPECTANCY: mean R for primed / turning / confirmed (net of the stop +
      one-way cost). PRIMED must show E[R] > 0 to earn a starter size, else ordering-only.
  (3) DEAD-CAT CONTROL: vetoed events' durable rate must be materially BELOW non-vetoed.
Writes data/regime/bottom_radar_calibration.json + prints the verdict.

Usage: python -m scripts.calibrate_bottom_radar [--x 8] [--n 42] [--step 10]
"""
from __future__ import annotations
import argparse, json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from engine import cycles, bottom_radar
from lib import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("calibrate_radar")

WIN, BUFFER, COST = 600, 0.02, 0.001       # window, stop buffer below the low, one-way cost


def _outcome(path: np.ndarray, entry: float, stop: float, x_pct: float) -> tuple[int, float]:
    """(durable, R) for a forward price path. R in stop-risk units, net of one-way cost."""
    risk = max((entry - stop) / entry, 0.005)
    target = entry * (1 + x_pct / 100.0)
    for px in path:
        if px <= stop:
            return 0, -1.0 - COST / risk
        if px >= target:
            return 1, (x_pct / 100.0) / risk - COST / risk
    # timeout: mark to the endpoint
    ret = path[-1] / entry - 1.0
    return int(ret >= x_pct / 100.0 * 0.5), ret / risk - COST / risk


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=float, default=8.0, help="target up-move %% for a durable bottom")
    ap.add_argument("--n", type=int, default=42, help="horizon in trading days")
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--universe", default="deep",
                    help="deep (data/stocks, survivor leaders) | breadth | smallcap_breadth | "
                         "midcap_breadth (the broad, non-survivor caches w/ volume)")
    ap.add_argument("--win", type=int, default=600, help="trailing PIT window")
    a = ap.parse_args()
    X, N, STEP, UNIV = a.x, a.n, a.step, a.universe
    win = a.win

    data = config.data_dir() / "stocks"
    try:
        bench = pd.read_parquet(config.data_dir() / "yahoo" / "SPY.parquet")["close"].dropna()
    except Exception:
        bench = None
    try:
        vix_s = pd.read_parquet(config.data_dir() / "yahoo" / "_VIX.parquet")["close"].dropna()
    except Exception:
        vix_s = None

    def _names():
        """Yield (ticker, close, high, volume) for the chosen universe. 'deep' = the
        survivor mega-cap leaders (data/stocks). 'breadth'/'smallcap_breadth'/
        'midcap_breadth' = the broad, NON-survivor caches with volume (where real
        dead-cats live) — the proper test of the radar's score + vetos."""
        if UNIV == "deep":
            for f in sorted(data.glob("*.parquet")):
                try:
                    df = pd.read_parquet(f)
                except Exception:
                    continue
                yield f.stem, df["close"].dropna(), df.get("high"), df.get("volume")
            return
        base = config.data_dir() / UNIV
        cc = pd.read_parquet(base / "_closes_cache.parquet")
        hc = pd.read_parquet(base / "_high_cache.parquet") if (base / "_high_cache.parquet").exists() else None
        vc = pd.read_parquet(base / "_volume_cache.parquet") if (base / "_volume_cache.parquet").exists() else None
        for t in cc.columns:
            yield (t, cc[t].dropna(),
                   hc[t] if (hc is not None and t in hc.columns) else None,
                   vc[t] if (vc is not None and t in vc.columns) else None)

    rows = []          # (raw, stage, blocked, durable, R, mae)
    names = list(_names())
    n_inst = 0
    for fi, (ticker, close, high, vol) in enumerate(names):
        if (fi + 1) % 25 == 0:
            log.info("...%d/%d names, %d events", fi + 1, len(names), len(rows))
        if len(close) < win + N + 50:
            continue
        n_inst += 1
        cv = close.to_numpy()
        vx = vix_s.reindex(close.index).ffill().to_numpy() if vix_s is not None else None
        # cap each name's walk to recent history (per-eval velocity/divergence cost).
        start_i = max(win, len(close) - 3500)
        for i in range(start_i, len(close) - N - 1, STEP):
            sub = close.iloc[i - win:i + 1]
            hsub = high.reindex(sub.index) if high is not None else None
            vsub = vol.reindex(sub.index) if vol is not None else None
            try:
                cyc = cycles.cycle_state(sub, hsub, "equity")
                if not cyc:
                    continue
                mtf = cycles.mtf_snapshot(sub, "equity")
                early = cycles.early_signals(sub, cyc, mtf)
                reg = cycles.regime_state(cyc, mtf)
                vctx = None
                if vx is not None and i >= 252 and not np.isnan(vx[i]):
                    pct = float((vx[i - 252:i + 1] <= vx[i]).mean())
                    vctx = {"pct": pct, "panic": pct >= 0.85}
                wo = cycles.washout(sub, cyc, vctx)
                r = bottom_radar.assess(sub, hsub, vsub, cyc=cyc, mtf=mtf, early=early,
                                        wo=wo, bench=bench, regime=reg)
            except Exception:
                continue
            if not r:
                continue
            # only evaluate BOTTOMING context (the radar's job) — skip pure uptrend holds
            if r["stage"] not in ("primed", "turning", "confirmed", "watch", "blocked"):
                continue
            entry = cv[i]
            low_ref = cyc.get("cand_price") or cyc.get("dcl_price") or entry
            stop = (low_ref if low_ref < entry else entry * 0.94) * (1 - BUFFER)
            path = cv[i + 1:i + 1 + N]
            if len(path) < N:
                continue
            durable, R = _outcome(path, entry, stop, X)
            mae = path.min() / entry - 1.0
            rows.append((r["raw"], r["stage"], r["blocked"], durable, R, mae))

    if len(rows) < 200:
        log.error("too few events (%d) — aborting", len(rows))
        return 1
    raw = np.array([x[0] for x in rows]); stage = np.array([x[1] for x in rows])
    blocked = np.array([x[2] for x in rows]); durable = np.array([x[3] for x in rows])
    R = np.array([x[4] for x in rows]); mae = np.array([x[5] for x in rows])

    print(f"\n=== Bottom-Radar calibration: {n_inst} names, {len(rows)} events "
          f"(durable = +{X:.0f}% in {N}d before stop) ===\n")

    # (1) calibration curve: raw-score decile -> durable rate (non-blocked only)
    nb = ~blocked
    print("RAW-SCORE CALIBRATION (non-blocked events):")
    print(f"  {'decile':<10}{'n':>7}{'raw_md':>8}{'durable%':>10}{'E[R]':>8}")
    try:
        qs = pd.qcut(raw[nb], 10, labels=False, duplicates="drop")
        for q in sorted(set(qs)):
            m = nb.copy(); m[nb] = (qs == q)
            print(f"  d{q:<9}{m.sum():>7}{np.median(raw[m]):>8.0f}"
                  f"{100*durable[m].mean():>9.0f}%{R[m].mean():>8.2f}")
    except Exception as e:
        log.warning("decile calc failed: %s", e)

    # (2) per-stage expectancy
    print("\nPER-STAGE (the ladder):")
    print(f"  {'stage':<10}{'n':>7}{'durable%':>10}{'E[R]':>8}{'MAE_md%':>9}")
    stage_out = {}
    for st in ("primed", "turning", "confirmed", "watch", "blocked"):
        m = stage == st
        if m.sum() < 30:
            print(f"  {st:<10}{m.sum():>7}  (thin)"); continue
        rec = {"n": int(m.sum()), "durable_pct": round(100*durable[m].mean(), 1),
               "expectancy_R": round(float(R[m].mean()), 3),
               "mae_med_pct": round(100*float(np.median(mae[m])), 2)}
        stage_out[st] = rec
        print(f"  {st:<10}{rec['n']:>7}{rec['durable_pct']:>9}%{rec['expectancy_R']:>8}"
              f"{rec['mae_med_pct']:>9}")

    # (3) dead-cat control
    vd, nd = durable[blocked], durable[~blocked]
    print(f"\nDEAD-CAT CONTROL: vetoed durable {100*vd.mean():.0f}% (n={vd.sum() and len(vd)}) "
          f"vs non-vetoed {100*nd.mean():.0f}% (n={len(nd)})  — vetoed must be LOWER")

    # verdict — STRICT and honest: PRIMED earns a SIZE only if it genuinely beats the
    # base rate AND the calibration discriminates AND the vetos separate dead-cats.
    # (a positive E[R] alone is just the survivor-universe base rate — it is NOT an edge.)
    primed = stage_out.get("primed", {})
    base_er = max(stage_out.get("blocked", {}).get("expectancy_R", 0),
                  stage_out.get("watch", {}).get("expectancy_R", 0))
    try:
        top_dec = durable[nb][pd.qcut(raw[nb], 10, labels=False, duplicates="drop") == 9].mean()
        bot_dec = durable[nb][pd.qcut(raw[nb], 10, labels=False, duplicates="drop") == 0].mean()
        calib_ok = (top_dec - bot_dec) >= 0.05            # ≥5pp monotone-ish lift
    except Exception:
        calib_ok = False
    deadcat_ok = (nd.mean() - vd.mean()) >= 0.05          # vetoed ≥5pp LOWER durable
    primed_beats_base = bool(primed and primed["expectancy_R"] > base_er + 0.03)
    go = bool(primed and primed_beats_base and calib_ok and deadcat_ok)
    print(f"\nVERDICT (strict): calib_lift_ok={calib_ok} deadcat_ok={deadcat_ok} "
          f"primed_beats_base={primed_beats_base} (primed E[R] {primed.get('expectancy_R')} "
          f"vs base {round(base_er,3)})")
    print(f"  -> {'GO (earns a starter size)' if go else 'NO-GO: ship watchlist-ordering / heads-up ONLY (no recommended size, no auto-buy)'}")

    out = {"x_pct": X, "n_days": N, "n_events": len(rows), "n_names": n_inst,
           "stages": stage_out, "go": go,
           "deadcat": {"vetoed_durable_pct": round(100*float(vd.mean()), 1) if len(vd) else None,
                       "nonvetoed_durable_pct": round(100*float(nd.mean()), 1)}}
    p = config.data_dir() / "regime" / "bottom_radar_calibration.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    log.info("wrote %s", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
