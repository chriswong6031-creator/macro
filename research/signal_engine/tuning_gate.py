"""The VERDICT GATE: per-name held-out generalization of a candidate vs base3d.

Loads two dump files (written by tuning_harness.py --dump) and reports, aligned by
ticker, the fraction of held-out names where the candidate is shallower-DD / better-
located / lower-shake / lower-chase than base3d — on the full panel AND the strict
subset (excl the 5 hand-examined exit cases). The charter promotion bar: shallower-DD
AND better-location on a MAJORITY (>50%) of held-out names. Also reports a 'DD-tie'
rate (within 1pp) so we can see 'matches base DD but enters earlier' cases.

Run:  python3 research/signal_engine/tuning_gate.py <base_dump> <cand_dump>
"""
from __future__ import annotations

import sys
import json

import numpy as np

STRICT_EXCL = {"JNJ", "LLY", "WMT", "MCD", "NVDA"}


def _load(p):
    return {r["t"]: r for r in json.load(open(p))["per_name"]}


def gate(base_dump, cand_dump):
    base, cand = _load(base_dump), _load(cand_dump)

    def stats(names):
        common = sorted(set(base) & set(cand) & set(names))
        if not common:
            return None
        dd_sh = [cand[t]["dd"] > base[t]["dd"] for t in common]       # less neg = shallower
        dd_tie = [abs(cand[t]["dd"] - base[t]["dd"]) <= 1.0 for t in common]
        loc = [cand[t]["locw"] < base[t]["locw"] for t in common]     # lower = better
        shake = [cand[t]["shake"] < base[t]["shake"] for t in common]
        chase = [cand[t]["chase"] < base[t]["chase"] for t in common]
        ddd = [cand[t]["dd"] - base[t]["dd"] for t in common]
        return {
            "n": len(common),
            "dd_shallower_pct": round(100 * np.mean(dd_sh), 1),
            "dd_tie_pct": round(100 * np.mean(dd_tie), 1),
            "median_dd_delta": round(float(np.median(ddd)), 2),
            "loc_better_pct": round(100 * np.mean(loc), 1),
            "shake_better_pct": round(100 * np.mean(shake), 1),
            "chase_better_pct": round(100 * np.mean(chase), 1),
            "avg_sig_base": round(float(np.mean([base[t]["n"] for t in common])), 2),
            "avg_sig_cand": round(float(np.mean([cand[t]["n"] for t in common])), 2),
        }

    full = stats(set(base) | set(cand))
    strict = stats({t for t in (set(base) | set(cand)) if t not in STRICT_EXCL})
    cand_agg = json.load(open(cand_dump))["agg"]
    base_agg = json.load(open(base_dump))["agg"]
    passes = bool(full and full["dd_shallower_pct"] > 50 and full["loc_better_pct"] > 50
                  and strict and strict["dd_shallower_pct"] > 50 and strict["loc_better_pct"] > 50)
    return {
        "candidate": cand_agg.get("variant"), "filter": cand_agg.get("filter"),
        "PASSES_GATE": passes,
        "agg_dd_base": round(base_agg["dd"], 2), "agg_dd_cand": round(cand_agg["dd"], 2),
        "agg_locw_base": round(base_agg["locw"], 3), "agg_locw_cand": round(cand_agg["locw"], 3),
        "agg_chase_base": round(base_agg["chase"], 3), "agg_chase_cand": round(cand_agg["chase"], 3),
        "full": full, "strict": strict,
    }


if __name__ == "__main__":
    print(json.dumps(gate(sys.argv[1], sys.argv[2]), indent=1))
