"""Phase-0 (RESEARCH-ONLY) for the HK southbound-vs-price divergence chip (P1b).

Pre-registered question: does the divergence read add INCREMENTAL predictive
content for forward HSI returns (21d/63d) over the named incumbent — HK breadth
(pct_above_50, level + 20d slope) + southbound window-cum LEVEL z — after
orthogonalizing the divergence signal against that incumbent?

Honest prior = DISPLAY: the divergence is a derived interaction of two things the
incumbent already contains, and the Connect-era overlap (~2014→) is the binding
power constraint. Single-asset time-series test. Imports validation primitives,
prints a verdict, WIRES NOTHING. See HK_SOUTHBOUND_DIVERGENCE_SPEC.md §4.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V  # noqa: E402
from lib import store  # noqa: E402

HORIZONS = [21, 63]
WIN = 63
MIN_POWER_OBS = 1500


def _z(s: pd.Series, win: int = 252) -> pd.Series:
    return (s - s.rolling(win, min_periods=win // 4).mean()) / s.rolling(win, min_periods=win // 4).std()


def _rolling_ic(sig: pd.Series, fwd: pd.Series, win: int = 126, step: int = 10) -> list:
    idx = sig.dropna().index.intersection(fwd.dropna().index)
    s, f = sig.reindex(idx), fwd.reindex(idx)
    ics = []
    for i in range(win, len(idx) + 1, step):
        ic = V.rank_ic(s.iloc[i - win:i].values, f.iloc[i - win:i].values)
        if np.isfinite(ic):
            ics.append(ic)
    return ics


def main() -> None:
    sb = store.read("china_connect", "southbound")
    hsi = store.read("hk", "^HSI")
    brth = store.read("hk_breadth", "breadth")
    if sb is None or hsi is None or brth is None:
        print("missing store data (southbound/HSI/breadth) -> cannot test -> DISPLAY")
        return
    net = sb["net"].dropna()
    close = hsi["close"].dropna()
    pab = brth["pct_above_50"].dropna()

    # binding window = overlap of all three on a daily grid (Connect era)
    idx = close.index.intersection(net.index).intersection(pab.index)
    n = len(idx)
    print(f"overlap (Connect-era) obs: {n} (power floor {MIN_POWER_OBS})")
    if n < 300:
        print("VERDICT: DISPLAY (overlap far too short to test)")
        return

    close, net, pab = close.reindex(idx).ffill(), net.reindex(idx).ffill(), pab.reindex(idx).ffill()

    # incumbent: window-cum southbound LEVEL z (== the chip's flow_z) + breadth level/slope z
    flow_z = _z(net.rolling(WIN).sum())
    breadth_z = _z(pab)
    breadth_slope_z = _z(pab.diff(20))
    px_trend = close / close.shift(WIN) - 1.0

    # divergence as a continuous interaction (two trials: sign-agreement & magnitude)
    div_sign = np.sign(flow_z.fillna(0)) * np.sign(px_trend.fillna(0))
    div_mag = (flow_z * px_trend)
    basis = [breadth_z, breadth_slope_z, flow_z]

    rows, pvals = [], {}
    for label, raw in (("div_sign", div_sign), ("div_mag", div_mag)):
        resid = V.resid_z(raw, basis=basis, win=252, min_p=120)   # orthogonalize vs incumbent
        for h in HORIZONS:
            fwd = close.shift(-h) / close - 1.0
            summ = V.ic_summary(_rolling_ic(resid, fwd), periods_per_year=max(1, 252 // h))
            pvals[f"{label}@{h}"] = summ.get("p_hac")
            rows.append((f"{label}@{h}", summ.get("mean_ic"), summ.get("t_hac"),
                         summ.get("p_hac"), summ.get("n")))

    bh = V.benjamini_hochberg({k: v for k, v in pvals.items() if v is not None}, alpha=0.10)

    # honest overlay: long-HSI only on confirms&flow-up, flat otherwise; excess DSR
    flow_up = flow_z >= 0.5
    px_up = px_trend >= 0.02
    alloc = ((flow_up & px_up).astype(float)).reindex(idx).fillna(0)
    ret = close.pct_change().fillna(0)
    strat = (alloc.shift(1).fillna(0) * ret)
    excess = strat - ret                                  # vs buy-and-hold
    m = V.ret_moments(excess)
    dsr = V.deflated_sharpe(m[0], m[1], m[2], m[3], n_trials=len(pvals))
    ci = V.block_bootstrap_ci(excess, block=21)

    print("\n  trial          mean_ic    t_hac      p      n")
    for nm, ic, t, p, nn in rows:
        print(f"  {nm:12s} {str(ic):>8} {str(t):>8} {str(p):>7} {str(nn):>5}")
    survivors = [k for k, v in bh.items() if v["reject"]]
    dsr_val = dsr.get("dsr", 0.0)
    print("\n  BH-FDR rejects:", survivors or "none")
    print(f"  overlay excess DSR: {dsr_val} ({V.dsr_verdict(dsr_val)}) "
          f"| sharpe CI: {ci.get('sharpe_ci')} | P(sharpe>0): {ci.get('sharpe_gt0_prob')}")

    # A GO needs incremental FDR survival AND a tradable overlay clearing DSR>=0.90.
    # Note: survivors here carry NEGATIVE IC (anti-predictive) and the overlay DSR
    # fails — the exact derived-from-incumbent / single-asset-timing trap -> DISPLAY.
    if n < MIN_POWER_OBS:
        verdict = (f"DISPLAY (underpowered — overlap n={n} < {MIN_POWER_OBS}; "
                   "an underpowered result must NOT be read as a GO)")
    elif survivors and dsr_val >= 0.90:
        verdict = "PROMOTE-CANDIDATE (separate follow-up, never auto-wire): " + ", ".join(survivors)
    else:
        verdict = "DISPLAY (incremental IC does not yield a tradable edge: overlay DSR<0.90 over breadth+southbound)"
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    main()
