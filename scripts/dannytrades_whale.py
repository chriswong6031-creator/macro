"""scripts/dannytrades_whale.py — settle the two open questions from the phase-0:

  Q1 (the whale lead): on Danny's ACTUAL timeframe (monthly bars) and with a FAITHFUL
     saturating whale metric (engine.dannytrades.whale_buy_fraction, not the percentile
     proxy), and with NON-OVERLAPPING forward returns (the overlap that wrecked the
     daily 63d significance is gone here) — does whale accumulation carry an edge? We
     test both the LEVEL ("how much accumulation") and the CHANGE ("whales ENTERING",
     which is what Danny actually tracks).

  Q2 (the validated contrarian read): does a HIGH composite / HIGH whale LEVEL really
     predict WORSE forward returns, monotonically across deciles? (The one gate-passing
     result — confirm it's clean, not a one-bucket artifact.)

Same yfinance OHLCV cache as the phase-0. Run: python3 -m scripts.dannytrades_whale
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dannytrades as dt  # noqa: E402
from engine.validation import ic_summary, rank_ic  # noqa: E402
from scripts.dannytrades_phase0 import _load  # noqa: E402

WHALE_WIN_M = 6          # months of accumulation window (his "3mo–1yr")
MIN_NAMES = 20


def _monthly(df: pd.DataFrame) -> pd.DataFrame:
    m = pd.DataFrame({
        "close": df["close"].resample("ME").last(),
        "high": df["high"].resample("ME").max(),
        "low": df["low"].resample("ME").min(),
        "volume": df["volume"].resample("ME").sum(),
    }).dropna()
    m["whale"] = dt.whale_buy_fraction(m["high"], m["low"], m["close"], m["volume"], WHALE_WIN_M)
    m["whale_chg"] = m["whale"].diff(3)                          # 3-month change = "entering"
    m["fwd_1m"] = m["close"].pct_change(fill_method=None).shift(-1) * 100   # non-overlapping
    m["fwd_3m_no"] = m["close"].pct_change(3, fill_method=None).shift(-3) * 100
    return m


def _cluster_boot(work: pd.DataFrame, mask, n_boot=1000, seed=11) -> dict:
    """Ticker-cluster bootstrap of (P(up|mask) − P(up|all)) on a NON-overlapping pool."""
    w = work.dropna(subset=["fwd_1m"])
    up = (w["fwd_1m"].values > 0).astype(float)
    m = mask.reindex(w.index).fillna(False).values
    if m.sum() < 30:
        return {"n": int(m.sum())}
    base = up.mean()
    real = up[m].mean() - base
    g = pd.DataFrame({"t": w["ticker"].values, "up": up, "m": m.astype(float),
                      "um": up * m})
    agg = g.groupby("t").agg(n=("up", "size"), su=("up", "sum"),
                             nm=("m", "sum"), sum_um=("um", "sum"))
    n, su, nm, sum_um = (agg[c].values for c in ("n", "su", "nm", "sum_um"))
    rng = np.random.default_rng(seed)
    T = len(agg)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, T, T)
        NM, SUM, N, SU = nm[s].sum(), sum_um[s].sum(), n[s].sum(), su[s].sum()
        boots[b] = (SUM / NM - SU / N) if (NM > 0 and N > 0) else np.nan
    boots = boots[np.isfinite(boots)]
    return {"n": int(m.sum()), "p_up": round(float(up[m].mean()), 3),
            "base_p_up": round(float(base), 3), "lift": round(float(real), 4),
            "ci95": [round(float(np.percentile(boots, 2.5)), 4),
                     round(float(np.percentile(boots, 97.5)), 4)],
            "p_lift_gt0": round(float((boots > 0).mean()), 3),
            "mean_fwd_1m": round(float(w["fwd_1m"].values[m].mean()), 2),
            "base_fwd_1m": round(float(w["fwd_1m"].mean()), 2)}


def monthly_tests(data: dict) -> dict:
    frames = []
    for t, df in data.items():
        if t == "SPY":
            continue
        m = _monthly(df)
        m["ticker"] = t
        m["date"] = m.index
        frames.append(m)
    pool = pd.concat(frames, ignore_index=True)

    # --- Q1a: cross-sectional IC (non-overlapping monthly) ---
    out = {"pool_rows": int(len(pool))}
    dates = np.sort(pool["date"].dropna().unique())
    for sig in ["whale", "whale_chg"]:
        for fcol, lbl in [("fwd_1m", "1m"), ("fwd_3m_no", "3m_nonoverlap")]:
            ics = []
            for d in dates:
                sub = pool[pool["date"] == d][[sig, fcol]].dropna()
                if len(sub) >= MIN_NAMES:
                    ics.append(rank_ic(sub[sig], sub[fcol]))
            s = ic_summary(pd.Series(ics, dtype=float).dropna(), periods_per_year=12)
            out[f"ic_{sig}_{lbl}"] = {"mean_ic": s.get("mean_ic"), "t_hac": s.get("t_hac"),
                                      "p_hac": s.get("p_hac"), "hit": s.get("hit"), "n": s.get("n")}

    # --- Q1b: event study with bootstrap CI (non-overlapping) ---
    out["event_whale_hot_gt75"] = _cluster_boot(pool, pool["whale"] > 75)
    out["event_whale_cold_lt40"] = _cluster_boot(pool, pool["whale"] < 40)
    out["event_whales_entering"] = _cluster_boot(pool, pool["whale_chg"] > 10)
    out["event_whales_leaving"] = _cluster_boot(pool, pool["whale_chg"] < -10)
    return out


def extension_deciles(data: dict) -> dict:
    """Q2: does a HIGH composite / HIGH whale level predict WORSE forward 63d returns,
    monotonically? Pool daily; decile the signal; mean forward return per decile;
    Spearman(decile, mean_ret) (negative = contrarian/extension)."""
    rows_score, rows_whale = [], []
    for t, df in data.items():
        if t == "SPY":
            continue
        sig = dt.signals(df["close"].astype(float), df["high"].astype(float),
                         df["low"].astype(float), df["volume"].astype(float))
        fwd = df["close"].astype(float).pct_change(63, fill_method=None).shift(-63) * 100
        rows_score.append(pd.DataFrame({"sig": sig["score"], "fwd": fwd}))
        rows_whale.append(pd.DataFrame({"sig": sig["whale"], "fwd": fwd}))

    def deciles(frames):
        p = pd.concat(frames, ignore_index=True).dropna()
        p["dec"] = pd.qcut(p["sig"], 10, labels=False, duplicates="drop")
        g = p.groupby("dec")["fwd"].agg(["mean", "median", "size"])
        # Spearman = Pearson on ranks (avoids the scipy dependency pandas' spearman needs)
        sp = float(pd.Series(g.index).rank().corr(g["mean"].reset_index(drop=True).rank()))
        return {"by_decile_mean": [round(float(x), 2) for x in g["mean"]],
                "top_minus_bottom": round(float(g["mean"].iloc[-1] - g["mean"].iloc[0]), 2),
                "spearman_decile_vs_ret": round(sp, 3), "n": int(g["size"].sum())}
    return {"composite_score": deciles(rows_score), "whale_level": deciles(rows_whale)}


def main() -> int:
    data = _load(Path("/tmp/dtcache"))
    print(f"loaded {len(data)} tickers", file=sys.stderr)
    res = {"monthly": monthly_tests(data), "extension_deciles": extension_deciles(data)}
    Path("/tmp/dt_whale.json").write_text(json.dumps(res, indent=2, default=float))

    m = res["monthly"]
    print("\n" + "=" * 78)
    print("WHALE LEAD — faithful metric, monthly bars, NON-OVERLAPPING forward returns")
    print("=" * 78)
    print("\n[Q1a] Cross-sectional IC (non-overlapping):")
    for k in ["ic_whale_1m", "ic_whale_3m_nonoverlap", "ic_whale_chg_1m", "ic_whale_chg_3m_nonoverlap"]:
        v = m[k]
        print(f"    {k:28s} IC={v['mean_ic']}  t={v['t_hac']}  p={v['p_hac']}  hit={v['hit']}  n={v['n']}")
    print("\n[Q1b] Event study (next-month, ticker-cluster bootstrap CI):")
    for k in ["event_whale_hot_gt75", "event_whale_cold_lt40", "event_whales_entering", "event_whales_leaving"]:
        v = m[k]
        if v.get("n", 0) >= 30:
            print(f"    {k:24s} n={v['n']:5d}  P(up)={v['p_up']} (base {v['base_p_up']})  "
                  f"lift={v['lift']:+.4f} CI={v['ci95']} P(>0)={v['p_lift_gt0']}  "
                  f"meanFwd={v['mean_fwd_1m']:+.2f}% (base {v['base_fwd_1m']:+.2f}%)")
    ed = res["extension_deciles"]
    print("\n[Q2] Extension monotonicity (forward 63d return by signal decile):")
    for k, v in ed.items():
        print(f"    {k:16s} decile means: {v['by_decile_mean']}")
        print(f"    {'':16s} top−bottom={v['top_minus_bottom']}%  Spearman(decile,ret)={v['spearman_decile_vs_ret']}  "
              f"({'CONTRARIAN' if v['spearman_decile_vs_ret'] < -0.3 else 'MOMENTUM' if v['spearman_decile_vs_ret'] > 0.3 else 'FLAT'})")
    print("\nwrote /tmp/dt_whale.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
