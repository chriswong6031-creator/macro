"""Robustness check on the 'credit is VIX in disguise' finding: residualize HY-OAS
velocity against VIX-only, rate-speed-only, both, and an IRRELEVANT control basis.
If the irrelevant control leaves the IC ~intact but VIX collapses it -> resid_z is
sound and VIX genuinely subsumes credit. Run: python -m scripts.exp_incremental_check"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import warnings; warnings.filterwarnings("ignore")

from engine import inputs
from engine.validation import resid_z
from scripts.calibrate_rate_inflation import _spear, equity_targets, H

ZWIN = 504
def cz(s, win=ZWIN, mp=252): return (s - s.rolling(win, min_periods=mp).mean()) / s.rolling(win, min_periods=mp).std()

def main() -> int:
    f = inputs.build_features()
    eq = equity_targets(f.index)
    dd = eq["dd_depth"]
    hy = f["hy_oas"]
    cand = hy - hy.shift(63)                 # the leg under test
    vix = f["vix_close"]
    rr = f["us10y_real"] - f["us10y_real"].shift(63)
    # irrelevant control: a deterministic smooth series (sine of the day index) — has
    # NO relation to dd but IS autocorrelated, so a sound residualizer should not use it.
    t = np.arange(len(f.index))
    ctrl = pd.Series(np.sin(t / 90.0), index=f.index)

    z = cz(cand)
    raw = _spear(z, dd)
    def inc(basis): return round(_spear(resid_z(z, [cz(b) for b in basis], ZWIN, 252), dd), 3)
    print(f"\n=== incremental-IC robustness (asof {f.index[-1].date()}) ===")
    print(f"  raw IC (hy_oas_chg63 z vs fwd dd)      = {round(raw,3)}")
    print(f"  resid vs IRRELEVANT sine control       = {inc([ctrl])}   (should stay ~raw)")
    print(f"  resid vs real-rate speed ONLY          = {inc([rr])}")
    print(f"  resid vs VIX ONLY                      = {inc([vix])}   (the suspected killer)")
    print(f"  resid vs VIX + rate-speed              = {inc([vix, rr])}")
    # how correlated are hy_oas_chg63 and VIX directly?
    j = pd.concat([cz(cand).rename('a'), cz(vix).rename('b')], axis=1).dropna()
    print(f"\n  corr(z hy_oas_chg63, z VIX)            = {round(float(j['a'].corr(j['b'])),3)}")
    jl = pd.concat([cz(hy).rename('a'), cz(vix).rename('b')], axis=1).dropna()
    print(f"  corr(z hy_oas LEVEL, z VIX)            = {round(float(jl['a'].corr(jl['b'])),3)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
