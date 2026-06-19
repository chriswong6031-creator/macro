"""scripts/dannytrades_sweep.py — robustness sweep for the DannyTrades phase-0
confirmation-lift finding. Perturbs every key parameter (whale window, squeeze
percentile, CMF length, confirm threshold, composite weights) and re-measures:
the composite's cross-sectional IC sign, the trend-pullback confirmation lift vs
its placebo, the breakout veto effect, and pre/post-2015 stability.

A finding that only survives at the default config is overfit; one that holds
across perturbations is structural. Run: python3 -m scripts.dannytrades_sweep
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dannytrades as dt  # noqa: E402
from engine.validation import ic_summary  # noqa: E402
from scripts.dannytrades_phase0 import (  # noqa: E402
    PRIMARY_H, SPLIT_DATE, WEEKLY_STEP, _event_stats, _load, _xs_ic,
    build_pool, confirm_mask,
)


def _metrics(pool: pd.DataFrame, wm: float | None = None, seed: int = 7) -> dict:
    grid = np.sort(pool["date"].unique())[::WEEKLY_STEP]
    ic = ic_summary(_xs_ic(pool, "score", PRIMARY_H, grid), periods_per_year=52)
    confirm = confirm_mask(pool, wm)
    rng = np.random.default_rng(seed)
    shuf = pool.assign(_c=confirm.values)
    shuf["_cs"] = shuf.groupby("ticker")["_c"].transform(lambda s: rng.permutation(s.values))
    out = {"composite_ic": ic.get("mean_ic"), "ic_t": ic.get("t_hac"), "ic_n": ic.get("n")}
    # trend-pullback confirmation lift + placebo
    b = pool["base_pullback"].astype(bool) & pool["p_ret"].notna()
    sb = _event_stats(b, pool)
    sc = _event_stats(b & confirm, pool)
    sp = _event_stats(b & shuf["_cs"].astype(bool), pool)
    out["pullback_base_pup"] = sb.get("p_up")
    out["pullback_confirm_pup"] = sc.get("p_up")
    out["pullback_lift"] = (round(sc["p_up"] - sb["p_up"], 3)
                            if sc.get("n", 0) >= 30 and sb.get("n", 0) >= 30 else None)
    out["pullback_placebo_lift"] = (round(sp["p_up"] - sb["p_up"], 3)
                                    if sp.get("n", 0) >= 30 else None)
    out["pullback_dd_lift"] = (round(sc["dd_tail_p05"] - sb["dd_tail_p05"], 2)
                               if sc.get("n", 0) >= 30 else None)
    # breakout veto
    bk = pool["base_breakout"].astype(bool) & pool["p_ret"].notna()
    veto = pool["danny_sell"].astype(bool)
    sbk = _event_stats(bk, pool)
    sv = _event_stats(bk & veto, pool)
    out["breakout_base_pup"] = sbk.get("p_up")
    out["breakout_veto_pup"] = sv.get("p_up")
    out["breakout_veto_delta"] = (round(sv["p_up"] - sbk["p_up"], 3)
                                  if sv.get("n", 0) >= 30 and sbk.get("n", 0) >= 30 else None)
    # subperiod pullback lift
    for lbl, sub in [("pre", pool[pool["date"] < SPLIT_DATE]),
                     ("post", pool[pool["date"] >= SPLIT_DATE])]:
        cm = confirm_mask(sub, wm)
        bs = sub["base_pullback"].astype(bool) & sub["p_ret"].notna()
        a, c = _event_stats(bs, sub), _event_stats(bs & cm, sub)
        out[f"pullback_lift_{lbl}"] = (round(c["p_up"] - a["p_up"], 3)
                                       if c.get("n", 0) >= 30 and a.get("n", 0) >= 30 else None)
    return out


def main() -> int:
    data = _load(Path("/tmp/dtcache"))
    print(f"loaded {len(data)} tickers", file=sys.stderr)

    # variants that change the SIGNALS need a pool rebuild; whale_momentum (confirm
    # threshold) only changes the filter, so it reuses the baseline pool.
    rebuilds = {
        "baseline": {},
        "whale_win=42": {"whale_win": 42}, "whale_win=84": {"whale_win": 84},
        "squeeze=0.15": {"squeeze_pctile": 0.15}, "squeeze=0.35": {"squeeze_pctile": 0.35},
        "cmf_n=14": {"cmf_n": 14}, "cmf_n=34": {"cmf_n": 34},
        "w_whale=0.6": {"w_whale": 0.6, "w_box": 0.1, "w_poc": 0.1, "w_ribbon": 0.1, "w_momentum": 0.1},
        "w_equal": {"w_whale": 0.2, "w_box": 0.2, "w_poc": 0.2, "w_ribbon": 0.2, "w_momentum": 0.2},
    }
    results = {}
    base_pool = None
    for label, cfg in rebuilds.items():
        pool = build_pool(data, cfg)
        if label == "baseline":
            base_pool = pool
        results[label] = _metrics(pool)
        print(f"  {label} done", file=sys.stderr)
    # confirm-threshold variants reuse baseline pool
    for wm in (40.0, 60.0):
        results[f"whale_momentum={int(wm)}"] = _metrics(base_pool, wm=wm)
        print(f"  whale_momentum={int(wm)} done", file=sys.stderr)

    Path("/tmp/dt_sweep.json").write_text(json.dumps(results, indent=2, default=float))

    # table
    cols = ["composite_ic", "pullback_lift", "pullback_placebo_lift", "pullback_dd_lift",
            "breakout_veto_delta", "pullback_lift_pre", "pullback_lift_post"]
    print("\n" + "=" * 100)
    print("ROBUSTNESS SWEEP — confirmation lift across perturbations")
    print("=" * 100)
    hdr = f"{'variant':18s} " + " ".join(f"{c.replace('pullback_','pb_').replace('composite_','comp_'):>16s}" for c in cols)
    print(hdr)
    for label, m in results.items():
        line = f"{label:18s} " + " ".join(
            f"{(m.get(c) if m.get(c) is not None else float('nan')):>16.3f}" for c in cols)
        print(line)
    print("\nKEY: pb_lift>0 AND pb_lift>placebo AND lift_pre>0 AND lift_post>0 = structural")
    print("wrote /tmp/dt_sweep.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
