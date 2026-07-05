"""First-pass out-of-sample + timing-placebo gauntlet for COMPOUND entry rules.

This is the Tier-1.5 bridge between the mechanical screen (oracle_screen.py,
in-sample effect + era-direction count) and the canonical, fully pre-registered
P3 episode gauntlet (oracle_gauntlet_p3.py).  It answers the one question the
screen does not: does a floor-passing compound's edge survive OUT OF SAMPLE and
beat a random-timing null?

It deliberately reuses oracle_screen's look-ahead-safe primitives verbatim —
`get_entry_dates` (grammar firewall) and `_compute_forward_returns` (stored,
as-of-t forward RS) — and only adds split / placebo bookkeeping on top.  No new
forward-return math is introduced, so nothing here can leak the future that the
screener does not already leak (i.e. none).

Pre-registered pass criteria (FROZEN; do not tune to results):
  G1 OOS holdout (split date frozen via --split, default 2019-12-31):
      holdout effect_63d SAME SIGN as dev AND holdout hit_63d >= 0.52 AND
      holdout n >= 100.
  G2 per-era persistence: >= 3 of 4 eras with positive real mean (n>=20/era).
  G3 timing placebo: real mean_63d > 95th pctile of N random-timing draws
      (each draw resamples, per node, the same #entries from that node's
      realizable 63d-excess outcomes).  Reported one-sided p = P(null >= real).
  VERDICT PASS = G1 and G2 and G3.

A PASS here is a promotion candidate pending the formal P3 pre-registration —
it does NOT license a gauntleted/promoted claim on user-facing surfaces.

Usage:
    python -m scripts.oracle_gauntlet_compound --ids A15_... A9_... \
        --data-dir data --compounds-dir data/oracle/compounds
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.oracle_screen import (  # noqa: E402
    _load_panel, _load_episodes, _load_spy, _load_rotation_groups,
    _compute_forward_returns, _ERA_CUTS,
)
from engine.oracle.compounds import (  # noqa: E402
    get_entry_dates, augment_panel_with_derived, load_registry,
)

H = 63  # promotion-relevant horizon


def run(ids, data_dir: Path, compounds_dir: Path, split: pd.Timestamp,
        n_placebo: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    panel = augment_panel_with_derived(_load_panel(data_dir, "s"))
    episodes = _load_episodes(data_dir, "s")
    spy = _load_spy(data_dir)
    rg = _load_rotation_groups(data_dir)
    reg = {c["id"]: c for c in load_registry(compounds_dir)}

    # Placebo urn: realizable 63d excess per node over ALL panel dates.
    all_entry = {node: list(panel.xs(node, level="node").index)
                 for node in panel.index.get_level_values("node").unique()}
    urn_fwd = _compute_forward_returns(all_entry, panel, spy, [H], "s")
    urn = {n: g["excess"].dropna().values
           for n, g in urn_fwd[urn_fwd.horizon_d == H].groupby("node")}

    results = {}
    for cid in ids:
        if cid not in reg:
            print(f"[skip] {cid} not in registry")
            continue
        ed = get_entry_dates(reg[cid], panel, episodes, rg)
        fwd = _compute_forward_returns(ed, panel, spy, [H], "s")
        f = fwd[fwd.horizon_d == H].dropna(subset=["excess"]).copy()
        real = float(f["excess"].mean())
        n = len(f)
        hit = float((f["excess"] > 0).mean())
        print(f"\n===== {cid} =====  n={n}  effect63={real*100:+.2f}%  hit63={hit*100:.1f}%")

        # G2 — per-era magnitude
        pos = 0
        print(" G2 per-era:")
        for era, _, _ in _ERA_CUTS:
            s = f[f["era"] == era]["excess"]
            if len(s) >= 20:
                m = float(s.mean()); pos += int(m > 0)
                print(f"    {era}: n={len(s):5d}  eff={m*100:+.2f}%  hit={(s>0).mean()*100:.1f}%")
            else:
                print(f"    {era}: n={len(s):5d}  (insufficient)")
        g2 = pos >= 3

        # G1 — OOS holdout
        f["ed"] = pd.to_datetime(f["entry_date"])
        dev = f[f["ed"] <= split]["excess"]
        hold = f[f["ed"] > split]["excess"]
        dv, hv = float(dev.mean()), float(hold.mean())
        hh = float((hold > 0).mean()) if len(hold) else float("nan")
        g1 = (np.sign(hv) == np.sign(dv)) and (hh >= 0.52) and (len(hold) >= 100)
        print(f" G1 OOS: dev(<= {split.date()}) n={len(dev)} eff={dv*100:+.2f}%  |  "
              f"HOLDOUT n={len(hold)} eff={hv*100:+.2f}% hit={hh*100:.1f}%")

        # G3 — timing placebo
        cnt = f.groupby("node").size().to_dict()
        draws = np.full(n_placebo, np.nan)
        for i in range(n_placebo):
            vals = [rng.choice(urn[nd], size=k, replace=True)
                    for nd, k in cnt.items() if urn.get(nd) is not None and len(urn[nd])]
            if vals:
                draws[i] = np.concatenate(vals).mean()
        p95 = float(np.nanpercentile(draws, 95))
        pval = float(np.mean(draws >= real))
        g3 = real > p95
        print(f" G3 placebo: real={real*100:+.2f}%  null_mean={np.nanmean(draws)*100:+.2f}%  "
              f"null_p95={p95*100:+.2f}%  p={pval:.3f}")

        verdict = bool(g1 and g2 and g3)
        print(f" --> G1={'PASS' if g1 else 'FAIL'}  G2={'PASS' if g2 else 'FAIL'} "
              f"({pos}/4)  G3={'PASS' if g3 else 'FAIL'}  ==> "
              f"{'*** GAUNTLET PASS ***' if verdict else 'FAIL'}")
        results[cid] = {"n": n, "effect_63d": real, "hit_63d": hit,
                        "g1_oos": g1, "g2_era_pos": pos, "g3_placebo": g3,
                        "placebo_p": pval, "verdict": verdict}
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ids", nargs="+", required=True, help="compound ids to gauntlet")
    p.add_argument("--data-dir", type=Path, default=ROOT / "data")
    p.add_argument("--compounds-dir", type=Path, default=None)
    p.add_argument("--split", type=str, default="2019-12-31", help="frozen dev/holdout boundary")
    p.add_argument("--n-placebo", type=int, default=500)
    p.add_argument("--seed", type=int, default=20260704)
    args = p.parse_args()
    compounds_dir = args.compounds_dir or (args.data_dir / "oracle" / "compounds")
    run(args.ids, args.data_dir, compounds_dir, pd.Timestamp(args.split),
        args.n_placebo, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
