"""One-off: backfill the GEX regime from OptionsDX 2023 EOD chains (data/gex_backfill/)
and run the forward-realized-vol GATE — does short-gamma precede higher forward RV?

OptionsDX EOD lacks OPEN INTEREST, so net GEX uses the call-vs-put VOLUME imbalance as
the dealer-positioning weight (gamma is call/put-symmetric, so the imbalance is what
carries the regime). This is a flow PROXY for standing OI — an honest first read at the
liquid index level (SPY/QQQ), not the definitive OI-GEX test. A clean confirmation would
need OI-bearing history (DoltHub / ThetaData free 1yr / Polygon $29).

Run: .venv/bin/python -m scripts.research_gex_backfill
"""
from __future__ import annotations

import glob
import io

import numpy as np
import pandas as pd
import py7zr

WINDOW = 0.10        # ±10% of spot for the gamma window
HORIZONS = (5, 10)   # forward realized-vol horizons (trading days)
MIN_BUCKET = 30
N_BOOT = 2000


def _daily(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().strip("[]").upper() for c in df.columns]
    for c in ("UNDERLYING_LAST", "STRIKE", "DTE", "C_GAMMA", "P_GAMMA", "C_VOLUME", "P_VOLUME"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["QUOTE_DATE"], errors="coerce")
    rows = []
    for d, g in df.groupby("date"):
        spot = float(g["UNDERLYING_LAST"].iloc[0])
        if not (spot and spot == spot):
            continue
        w = g[(g["DTE"] > 0) & g["STRIKE"].between(spot * (1 - WINDOW), spot * (1 + WINDOW))]
        if len(w) < 20:
            continue
        # dealer long-call / short-put; gamma is call/put-symmetric so the VOLUME imbalance carries it
        net = float(((w["C_GAMMA"].fillna(0) * w["C_VOLUME"].fillna(0))
                     - (w["P_GAMMA"].fillna(0) * w["P_VOLUME"].fillna(0))).sum())
        rows.append({"date": d, "spot": spot, "net_gex": net, "regime": "long" if net >= 0 else "short"})
    return pd.DataFrame(rows)


def _load(sym: str) -> pd.DataFrame | None:
    import os
    import tempfile
    parts = []
    for arc in sorted(glob.glob(f"data/gex_backfill/{sym}_eod_*.7z")):
        with tempfile.TemporaryDirectory() as tmp:
            with py7zr.SevenZipFile(arc, "r") as z:
                z.extractall(path=tmp)
            for txt in sorted(glob.glob(os.path.join(tmp, "**", "*.txt"), recursive=True)):
                chain = pd.read_csv(txt, skipinitialspace=True)
                parts.append(_daily(chain))
                del chain
    if not parts:
        return None
    out = pd.concat(parts, ignore_index=True).dropna(subset=["date"])
    return out.drop_duplicates("date").set_index("date").sort_index()


def _fwd_rv(spot: pd.Series, h: int) -> pd.Series:
    r = np.log(pd.to_numeric(spot, errors="coerce")).diff()
    return r.rolling(h).std().shift(-h) * np.sqrt(252)


def _boot(longg: np.ndarray, shortg: np.ndarray):
    d = np.array([np.random.choice(shortg, len(shortg)).mean() - np.random.choice(longg, len(longg)).mean()
                  for _ in range(N_BOOT)])
    return float(shortg.mean() - longg.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def _gate(sym: str, hist: pd.DataFrame):
    nL, nS = int((hist["regime"] == "long").sum()), int((hist["regime"] == "short").sum())
    span = f"{hist.index.min().date()}..{hist.index.max().date()}"
    print(f"\n== {sym.upper()}  {len(hist)} days [{span}]  regime split: long={nL} short={nS} ==")
    if hist.index.to_series().diff().dt.days.max() > 20:
        print("   ⚠ date gaps present (partial quarters) — forward-RV across gaps is unreliable")
    for h in HORIZONS:
        rv = _fwd_rv(hist["spot"], h)
        df = pd.DataFrame({"reg": hist["regime"].values, "rv": rv.values}).dropna()
        L = df[df.reg == "long"]["rv"].to_numpy()
        S = df[df.reg == "short"]["rv"].to_numpy()
        if len(L) < MIN_BUCKET or len(S) < MIN_BUCKET:
            print(f"   h={h}d: thin buckets (long {len(L)}, short {len(S)})")
            continue
        diff, lo, hi = _boot(L, S)
        verdict = "PASS — short>long, CI excludes 0" if lo > 0 else "NO EDGE — CI includes 0"
        print(f"   h={h}d: short_RV−long_RV={diff:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
              f"(long_RV={L.mean():.3f} n={len(L)} · short_RV={S.mean():.3f} n={len(S)}) → {verdict}")


def main() -> int:
    print("GEX backfill gate — OptionsDX 2023 EOD, VOLUME-imbalance proxy (no OI in feed)")
    for sym in ("spy", "qqq", "spx"):
        hist = _load(sym)
        if hist is None or hist.empty:
            print(f"\n{sym.upper()}: no data")
            continue
        _gate(sym, hist)
    print("\nNote: VOLUME proxy for OI (a flow read, not standing positioning). A PASS here is "
          "encouraging; a clean OI-based confirmation needs OI-bearing history.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
