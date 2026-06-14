"""Head-to-head: should the jobless-claims leg REPLACE the Sahm leg in the
recession_risk composite, AUGMENT it (current production), or is Sahm-only best?

Context. Claims is a stronger standalone recession signal than Sahm (Phase-0) and its
real-time edge grows under point-in-time (Phase-1.5). But claims and Sahm are 0.62-
correlated, so AUGMENT (sahm w=1.0 + claims w=0.5, the shipped config) gives the labor
dimension ~1.5 effective weight — possibly over-weighting labor vs the other legs.
REPLACE (claims at the Sahm weight, no Sahm) upgrades the signal while keeping labor
weight at 1.0 and removing the double-count.

We hold the NON-labor legs fixed (recession_prob, ebp_prob, curve, ebp_level at their
config weights) and vary only the labor leg, across all three data modes from the PIT
harness (revised-full / lagged-full / ALFRED-PIT). Metric: composite AUC vs NBER at
concurrent / 6m / 12m. Verdict prefers the config that wins the LEADING horizons
(6m/12m) and is robust across modes — and only recommends disrupting the long-standing
Sahm leg if REPLACE beats AUGMENT by a clear, consistent margin.

Run: .venv/bin/python -m scripts.validate_claims_vs_sahm
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_claims_recession import WEIGHTS, auc, fwd  # noqa: E402
from scripts.validate_claims_recession_pit import panel_pit, panel_revised  # noqa: E402

# non-labor legs (held fixed) -> (panel column, config weight)
OTHER = {"recession_prob": ("leg_rprob", WEIGHTS["recession_prob"]),
         "ebp_prob": ("leg_ebp_prob", WEIGHTS["ebp_prob"]),
         "curve": ("leg_curve", WEIGHTS["curve"]),
         "ebp_level": ("leg_ebp_level", WEIGHTS["ebp_level"])}
SAHM_W = WEIGHTS["sahm"]          # 1.0


def comp(P, labor: dict):
    """Composite (0..100) from the fixed non-labor legs + a labor-leg spec
    {name:(col,weight)}; renormalized over available legs (the engine's rule)."""
    spec = {**{k: v for k, v in OTHER.items()}, **labor}
    series = {n: (P[col], w) for n, (col, w) in spec.items()}
    num = sum(s.fillna(0) * w for s, w in series.values())
    den = sum(s.notna().astype(float) * w for s, w in series.values())
    return 100.0 * num / den.replace(0, np.nan)


CONFIGS = {
    "sahm-only (pre-claims)":   {"sahm": ("leg_sahm", SAHM_W)},
    "AUGMENT sahm+claims*0.5":  {"sahm": ("leg_sahm", SAHM_W), "claims": ("leg_claims_yoy", 0.5)},
    "REPLACE claims*1.0":       {"claims": ("leg_claims_yoy", SAHM_W)},
    "REPLACE claims*0.5":       {"claims": ("leg_claims_yoy", 0.5)},
}


def evaluate(P, label):
    ys = {"concurrent": fwd(P["usrec"], 0), "6m": fwd(P["usrec"], 6), "12m": fwd(P["usrec"], 12)}
    onsets = int((P["usrec"].diff() == 1).sum())
    print(f"\n=== {label}  ({P.index.min().date()}..{P.index.max().date()}, {onsets} onsets) ===")
    print(f"{'labor-leg config':<26}" + "".join(f"{h:>12}" for h in ys))
    out = {}
    for name, labor in CONFIGS.items():
        score = comp(P, labor)
        aucs = {h: auc(score, ys[h])[0] for h in ys}
        out[name] = aucs
        print(f"{name:<26}" + "".join(f"{aucs[h]:>12.3f}" for h in ys))
    return out


def main() -> int:
    print("Labor-leg head-to-head in the recession_risk composite (composite AUC vs NBER)")
    modes = [("REVISED-FULL", panel_revised(lag=False)),
             ("LAGGED-FULL (timing-honest, 8 rec)", panel_revised(lag=True)),
             ("ALFRED-PIT (revision-honest, 1997+, 3 rec)", panel_pit())]
    res = {m: evaluate(P, m) for m, P in modes}

    print("\n" + "=" * 72)
    print("REPLACE(1.0) minus AUGMENT  — positive => dropping Sahm for claims helps")
    print(f"{'mode':<44}{'6m':>10}{'12m':>10}")
    rep_wins = aug_wins = 0
    for m in res:
        d6 = res[m]["REPLACE claims*1.0"]["6m"] - res[m]["AUGMENT sahm+claims*0.5"]["6m"]
        d12 = res[m]["REPLACE claims*1.0"]["12m"] - res[m]["AUGMENT sahm+claims*0.5"]["12m"]
        print(f"{m:<44}{d6:>+10.3f}{d12:>+10.3f}")
        rep_wins += (d6 > 0.003) + (d12 > 0.003)
        aug_wins += (d6 < -0.003) + (d12 < -0.003)
    print("=" * 72)
    if rep_wins >= 4 and aug_wins == 0:
        verdict = "REPLACE Sahm with claims (consistent, clear)"
    elif aug_wins >= 4 and rep_wins == 0:
        verdict = "KEEP AUGMENT (both legs) — claims complements Sahm"
    else:
        verdict = "KEEP AUGMENT (shipped) — REPLACE not a clear, consistent win; don't disrupt a validated leg"
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
