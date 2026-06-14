"""Measured per-sector macro betas — the UPGRADE path from the coarse 3-tier
textbook prior (engine.confluence.sector_macro_beta).

Ties each SPDR's macro sensitivity to what the overlay actually penalizes: its
CONDITIONAL forward-63d drawdown depth under high macro risk (MRS >= 0.5), on the
deep SPDR history. Steps, kept deliberately low-parameter:

  1. d[s] = median fwd-63d drawdown of sector s under high MRS (weekly-declustered).
  2. standardize d across sectors -> z; deeper-than-average drawdown => higher beta.
  3. map to [-1, +1] (≈2σ -> ±1).
  4. SHRINK toward the textbook prior (50/50) so it stays coarse and overfit-resistant;
     a sector with too few high-MRS obs keeps the prior outright.
  5. validate: measured vs prior positively correlated AND cyclical-tier mean beta
     still > defensive-tier mean. Print a config-ready block + a verdict.

OFFLINE ONLY. Output is reviewed and pasted into config.yml — never recomputed in
the daily build (keeps the build deterministic). See research/MACRO_RISK_INTEGRATION.md.

Usage:  python -m scripts.calibrate_macro_betas
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.conditions import macro_risk_series, sector_macro_beta  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from engine.regime import classify  # noqa: E402
from engine.transition import compute_flags, state_machine  # noqa: E402
from lib import config, store  # noqa: E402
from scripts.research_macro_sector import _fwd_drawdown  # noqa: E402

SPDRS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
CYCLICAL = {"XLK", "XLY", "XLF", "XLC", "XLI", "XLB"}
DEFENSIVE = {"XLP", "XLU", "XLV"}
HIGH_MRS = 0.50
WEEKLY = 5
SHRINK_TO_PRIOR = 0.50      # 0 = pure measured, 1 = pure prior
MIN_OBS = 50                # below this, keep the prior for that sector


def _regime_with_state(f: pd.DataFrame) -> pd.DataFrame:
    regime = classify(f)
    flags = compute_flags(f, regime)
    regime = regime.join(flags)
    regime["transition_state"] = state_machine(flags, regime)
    return regime


def main() -> int:
    print("=" * 80)
    print(f"MEASURED SECTOR MACRO BETAS  (cond. fwd-63d drawdown under MRS≥{HIGH_MRS}, "
          f"shrink {SHRINK_TO_PRIOR:.0%} -> prior)")
    print("=" * 80)

    f = build_features()
    regime = _regime_with_state(f)
    mrs = macro_risk_series(f, regime).dropna()
    sampler = pd.Series(False, index=mrs.index)
    sampler.iloc[::WEEKLY] = True
    hi = (mrs >= HIGH_MRS)

    rows = {}
    for t in SPDRS:
        df = store.read("yahoo", t)
        if df is None or "close" not in df:
            continue
        dd = _fwd_drawdown(df["close"].dropna())
        idx = dd.index
        m = sampler.reindex(idx, fill_value=False) & hi.reindex(idx, fill_value=False)
        v = dd[m].dropna()
        rows[t] = (float(v.median()) if len(v) >= MIN_OBS else None, int(len(v)))

    # standardize the available conditional drawdowns across sectors
    avail = {t: d for t, (d, n) in rows.items() if d is not None}
    arr = np.array(list(avail.values()))
    mean, std = float(arr.mean()), float(arr.std() or 1.0)

    prior = {t: sector_macro_beta(t) for t in SPDRS}
    measured, final = {}, {}
    for t in SPDRS:
        d, n = rows.get(t, (None, 0))
        if d is None:
            measured[t] = None
            final[t] = round(prior[t], 2)                 # too thin -> keep prior
            continue
        z = (mean - d) / std                              # deeper dd => higher beta
        mb = float(np.clip(z / 2.0, -1.0, 1.0))           # ≈2σ -> ±1
        measured[t] = mb
        final[t] = round(SHRINK_TO_PRIOR * prior[t] + (1 - SHRINK_TO_PRIOR) * mb, 2)

    print(f"\n{'sector':<7}{'n':>5}{'cond.dd%':>10}{'measured':>10}{'prior':>8}{'final':>8}  tier")
    for t in SPDRS:
        d, n = rows.get(t, (None, 0))
        tier = "cyclical" if t in CYCLICAL else "defensive" if t in DEFENSIVE else "neutral"
        dstr = f"{100*d:+.1f}" if d is not None else "  thin"
        mstr = f"{measured[t]:+.2f}" if measured[t] is not None else "  —"
        print(f"{t:<7}{n:>5}{dstr:>10}{mstr:>10}{prior[t]:>8.2f}{final[t]:>8.2f}  {tier}")

    # ---- validation -------------------------------------------------------
    pv = np.array([prior[t] for t in SPDRS if measured[t] is not None])
    mv = np.array([measured[t] for t in SPDRS if measured[t] is not None])
    corr = float(np.corrcoef(pv, mv)[0, 1]) if len(pv) > 2 else float("nan")
    cyc_mean = np.mean([final[t] for t in SPDRS if t in CYCLICAL])
    def_mean = np.mean([final[t] for t in SPDRS if t in DEFENSIVE])
    ok = (corr > 0) and (cyc_mean > def_mean)

    print(f"\ncorr(measured, prior) = {corr:+.2f}   cyclical-tier mean final = {cyc_mean:+.2f}"
          f"   defensive-tier mean final = {def_mean:+.2f}")
    print("=" * 80)
    if ok:
        print("VERDICT: ADOPT — measured agrees with the prior's structure (positive corr) and")
        print("  the cyclical/defensive ordering is preserved. Paste the block below into")
        print("  config.yml engine.confluence.sector_macro_beta (SPDR keys); keep the GICS-name")
        print("  aliases pointing at the same tier values.")
        print("\nsector_macro_beta (measured, shrunk):")
        for t in SPDRS:
            print(f"      {t}: {final[t]}")
    else:
        print("VERDICT: KEEP PRIOR — measured diverges from the prior's structure; do not adopt.")
    print("=" * 80)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
