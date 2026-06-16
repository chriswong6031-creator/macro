"""One-off research: is COUNTERTREND BOUNCE an accurate label?

Re-walks the cycle ladder over the local equity panel and, for every
COUNTERTREND BOUNCE instance (plus FRESH BUY / TURN SIGNALED baselines),
measures the questions the *label* implicitly makes claims about:

  * "merely a bounce / bottom not in"  -> held-rate: did price avoid undercutting
    the trigger low over the next 21/63/126d?  (low held => the bottom WAS in)
  * "cascades toward the larger cycle low" -> cascade-rate: made a new low below
    the trigger within 21/63d?
  * "buying is bad" -> forward return / hit-rate at 21/63/126d.
  * the user's hypothesis: a chunk of these are the START of a new weekly/investor
    cycle -> split EVERY metric by investor-cycle phase, ic_failed, failed_cycle,
    washout depth below the 200d, and the regime score. If "countertrend bounce off
    a washed-out / overdue investor cycle" holds far more often than "countertrend
    bounce mid-decline", the single label is conflating two regimes.

Usage: python -m scripts.research_countertrend_bounce
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.cycles import (  # noqa: E402
    cycle_state, mtf_snapshot, early_signals, ladder_state, regime_state,
    _tf_state,
)
from lib import config, store  # noqa: E402

HORIZONS = (21, 63, 126)
STEP = 7
WINDOW = 600
STATES = ("COUNTERTREND BOUNCE", "FRESH BUY", "TURN SIGNALED", "DECLINE", "RALLY ON")


def build_panel() -> dict[str, pd.DataFrame]:
    panel: dict[str, pd.DataFrame] = {}
    funds = config.load()["sponsors"]["sector_funds"] + ["SPY", "IWM", "QQQ", "DIA"]
    for t in funds:
        df = store.read("yahoo", t)
        if df is not None and len(df) > 1500:
            panel[t] = df
    sdir = config.data_dir() / "stocks"
    for p in sorted(sdir.glob("*.parquet")):
        t = p.stem
        df = store.read("stocks", t)
        if df is not None and len(df) > 1500:
            panel[t] = df
    return panel


def _washout_depth(c: np.ndarray, i: int) -> float:
    """% below the 200d SMA at i (negative = below). 0 if not enough history."""
    if i < 200:
        return 0.0
    sma = c[i - 199: i + 1].mean()
    return c[i] / sma - 1.0 if sma else 0.0


def main() -> int:
    panel = build_panel()
    print(f"panel: {len(panel)} instruments", flush=True)

    rows = []
    for name, df in panel.items():
        c = df["close"].dropna()
        h = df["high"].dropna() if "high" in df else None
        if len(c) < 700:
            continue
        cv = c.to_numpy()
        for i in range(320, len(c) - max(HORIZONS), STEP):
            sub = c.iloc[max(0, i - WINDOW): i + 1]
            hsub = h.reindex(sub.index) if h is not None else None
            try:
                cyc = cycle_state(sub, hsub)
                if not cyc:
                    continue
                mtf = mtf_snapshot(sub)
                early = early_signals(sub, cyc, mtf)
                lad = ladder_state(cyc, mtf, early)
                reg = regime_state(cyc, mtf)
            except Exception:
                continue
            st = lad.get("state")
            if st not in STATES:
                continue
            # trigger low that defines this setup
            L = cyc.get("cand_price") or cyc.get("dcl_price") or cv[i]
            rec = {
                "name": name, "i": i, "state": st,
                "ic_phase": cyc.get("ic_phase"),
                "ic_failed": bool(cyc.get("ic_failed")),
                "failed_cycle": bool(cyc.get("failed_cycle")),
                "translation": cyc.get("translation"),
                "regime_score": reg.get("score"),
                "wo_depth": _washout_depth(cv, i),
                "L": float(L),
            }
            for hh in HORIZONS:
                fwd = cv[i + 1: i + 1 + hh]
                if len(fwd) < hh:
                    rec[f"ret_{hh}"] = np.nan
                    rec[f"held_{hh}"] = np.nan
                    rec[f"casc_{hh}"] = np.nan
                    continue
                rec[f"ret_{hh}"] = cv[i + hh] / cv[i] - 1.0
                lowest = float(fwd.min())
                rec[f"held_{hh}"] = lowest >= L            # never undercut trigger low
                rec[f"casc_{hh}"] = lowest < L * 0.995     # broke below it
            rows.append(rec)

    d = pd.DataFrame(rows)
    print(f"records: {len(d)}", flush=True)
    print("\n==== STATE BASELINES (all instances) ====", flush=True)
    _summ(d, "state")

    cb = d[d["state"] == "COUNTERTREND BOUNCE"].copy()
    print(f"\n==== COUNTERTREND BOUNCE = {len(cb)} instances ====", flush=True)

    print("\n-- by investor-cycle phase --", flush=True)
    _summ(cb, "ic_phase")

    print("\n-- by ic_failed --", flush=True)
    _summ(cb, "ic_failed")

    print("\n-- by failed_cycle (daily) --", flush=True)
    _summ(cb, "failed_cycle")

    print("\n-- by translation of last cycle --", flush=True)
    _summ(cb, "translation")

    cb["wo_band"] = pd.cut(cb["wo_depth"],
                           [-1, -0.20, -0.12, -0.06, 0.0, 1.0],
                           labels=["<-20% (deep knife)", "-12..-20%", "-6..-12%",
                                   "-6..0% (mild)", ">200d (above)"])
    print("\n-- by washout depth below 200d --", flush=True)
    _summ(cb, "wo_band")

    cb["reg_band"] = pd.cut(cb["regime_score"],
                            [-99, -4, -3, -2, -1.5, 99],
                            labels=["<=-4 (deep bear)", "-3..-4", "-2..-3",
                                    "-1.5..-2 (mild bear)", ">-1.5"])
    print("\n-- by regime score --", flush=True)
    _summ(cb, "reg_band")

    # the key cross: washed-out/overdue (possible new-cycle birth) vs mid-decline
    cb["regime_kind"] = np.where(
        cb["ic_phase"].isin(["late", "overdue"]) | cb["ic_failed"]
        | (cb["wo_depth"] <= -0.12),
        "washed-out / overdue (possible new cycle)",
        "early/mid investor cycle (mid-decline)")
    print("\n==== KEY SPLIT: new-cycle-candidate vs mid-decline ====", flush=True)
    _summ(cb, "regime_kind")
    return 0


def _summ(d: pd.DataFrame, by: str) -> None:
    hdr = f"{by:>40} {'n':>7} | " + " | ".join(
        f"r{h}% hit{h} held{h} casc{h}".replace(str(h), str(h), 1) for h in HORIZONS)
    print(f"{'group':>40} {'n':>7} | "
          + "  ".join(f"ret{h}  hit{h}  held{h} casc{h}" for h in HORIZONS), flush=True)
    for g, sub in d.groupby(by, dropna=False, observed=False):
        line = f"{str(g):>40} {len(sub):>7} | "
        cells = []
        for h in HORIZONS:
            r = sub[f"ret_{h}"].mean() * 100
            hit = (sub[f"ret_{h}"] > 0).mean() * 100
            held = sub[f"held_{h}"].mean() * 100
            casc = sub[f"casc_{h}"].mean() * 100
            cells.append(f"{r:+5.1f} {hit:4.0f} {held:4.0f} {casc:4.0f}")
        print(line + "  ".join(cells), flush=True)


if __name__ == "__main__":
    sys.exit(main())
