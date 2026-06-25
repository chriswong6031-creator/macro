"""PHASE-0b — is HY-OAS stress LEADING or just COINCIDENT-AND-PERSISTENT?

The scored gate (exp_credit_roc_gate) shows HY-OAS velocity/level associates with
forward drawdowns. But credit spreads are notoriously CONTEMPORANEOUS with equity
stress: OAS_t is high precisely WHEN a selloff is already underway, and because OAS is
persistent, "high OAS_t -> drawdown over [t+1..t+63]" can be mostly "the stress that is
already here keeps going", NOT foresight. The honest early-warning test is:

  (A) FROM-CALM test: does high credit-stress predict a forward >=10% drawdown when the
      market is CURRENTLY calm (within 3% of its 252d high, i.e. NOT already falling)?
      If the edge survives from calm -> genuine lead. If it vanishes -> persistence.
  (B) DAILY LEAD-LAG: corr(dHY_OAS_t, SPY_ret_{t+k}) for k=-20..+20. Peak at k<0 means
      OAS changes LAG equity; k>0 means OAS LEADS equity; k~0 means coincident.

Run: python -m scripts.exp_credit_lead
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import inputs  # noqa: E402
from lib import store  # noqa: E402

H = 63
DD_THRESH = -0.10


def main() -> int:
    f = inputs.build_features()
    g = store.read("yahoo", "_GSPC")
    spx = (g["close"] if g is not None else inputs.yahoo_closes().get("SPY"))
    spx = spx[~spx.index.duplicated(keep="last")].sort_index()
    spx = spx.reindex(f.index.union(spx.index)).ffill().reindex(f.index)

    # forward 63d worst drawdown & the >=10% flag (strictly forward)
    fwd_worst = spx.rolling(H).min().shift(-H) / spx - 1.0
    dd10 = (fwd_worst <= DD_THRESH).astype(float).where(fwd_worst.notna())

    # CURRENT state: distance below the trailing 252d high (0 = at high)
    hi252 = spx.rolling(252).max()
    below_hi = spx / hi252 - 1.0
    calm = below_hi >= -0.03          # within 3% of the 252d high == not already falling

    hy = f["hy_oas"]
    stress = {
        "hy_oas_chg63": hy - hy.shift(63),
        "hy_oas_z504": (hy - hy.rolling(504).mean()) / hy.rolling(504).std(),
    }

    print(f"\n=== PHASE-0b: HY-OAS leading vs coincident (asof {f.index[-1].date()}) ===")
    print("\n(A) FROM-CALM test — P(>=10% fwd 63d dd) by credit-stress tercile, "
          "WHEN currently within 3% of 252d high:")
    for name, s in stress.items():
        j = pd.concat([s.rename("s"), dd10.rename("dd"), calm.rename("calm")],
                      axis=1).dropna()
        jc = j[j["calm"]]
        base_all = j["dd"].mean()
        base_calm = jc["dd"].mean()
        # terciles of credit-stress within the CALM subsample
        if len(jc) < 300:
            print(f"  {name}: too few calm obs ({len(jc)})"); continue
        band = pd.qcut(jc["s"].rank(method="first"), 3, labels=["low", "mid", "high"])
        p_lo = jc.loc[band == "low", "dd"].mean()
        p_hi = jc.loc[band == "high", "dd"].mean()
        n_hi = int((band == "high").sum())
        print(f"  {name:14s} base(all)={base_all:.3f} base(calm)={base_calm:.3f} | "
              f"calm&low-stress={p_lo:.3f}  calm&HIGH-stress={p_hi:.3f}  "
              f"(n_hi={n_hi})  edge-from-calm={ (p_hi-base_calm)*100:+.1f}pp")

    print("\n(B) DAILY LEAD-LAG — corr(dHY_OAS_t, SPY_ret_{t+k}); "
          "k<0 => OAS lags equity, k>0 => OAS leads equity:")
    dhy = hy.diff()
    spx_ret = spx.pct_change()
    pairs = []
    for k in (-15, -10, -5, -3, -1, 0, 1, 3, 5, 10, 15):
        c = pd.concat([dhy.rename("o"), spx_ret.shift(-k).rename("r")], axis=1).dropna()
        cc = float(c["o"].corr(c["r"])) if len(c) > 250 else float("nan")
        pairs.append((k, cc))
    for k, cc in pairs:
        tag = "OAS leads eq" if k > 0 else ("OAS lags eq" if k < 0 else "coincident")
        bar = "#" * int(abs(cc) * 200)
        print(f"  k={k:+3d} ({tag:12s}) corr={cc:+.3f} {bar}")
    kbest = min(pairs, key=lambda x: x[1])  # most negative (OAS up <-> eq down)
    print(f"\n  strongest (most negative) co-move at k={kbest[0]:+d} "
          f"(corr {kbest[1]:+.3f}) -> {'LEADS' if kbest[0]>0 else ('LAGS' if kbest[0]<0 else 'COINCIDENT')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
