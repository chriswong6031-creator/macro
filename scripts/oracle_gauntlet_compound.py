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

  TIER S (default):
    G1 OOS holdout (split date frozen via --split, default 2019-12-31):
        holdout effect_63d SAME SIGN as dev AND holdout hit_63d >= 0.52 AND
        holdout n >= 100.
    G2 per-era persistence: >= 3 of 4 eras with positive real mean (n>=20/era).
    G3 timing placebo: real mean_63d > 95th pctile of N random-timing draws
        (each draw resamples, per node, the same #entries from that node's
        realizable 63d-excess outcomes).  Reported one-sided p = P(null >= real).
    VERDICT PASS = G1 and G2 and G3.

  TIER M (modern-regime; see research/ORACLE_TIERM_MODERN_GATE_PREREG.md):
    G1-modern OOS: split 2023-12-31.
        dev = entries <= split; holdout = entries > split.
        PASS = holdout same-sign AND holdout hit_63d >= 0.52 AND holdout n >= 100.
    G2-modern: 5 annual buckets (2021 / 2022 / 2023 / 2024 / 2025-26).
        bucket n < 20 counts as NOT consistent.
        PASS = >= 4 of 5 buckets same sign as overall.
    G3 placebo: unchanged (real mean_63d > null p95; urn built from tier-m panel).
    Effect/hit floor: n >= 100 AND (|effect_63d| >= 0.01 OR hit_63d >= 0.55).
    VERDICT PASS = G1 and G2 and G3 (plus floor).

A PASS here is a promotion candidate pending the formal P3 pre-registration —
it does NOT license a gauntleted/promoted claim on user-facing surfaces.

Usage:
    python -m scripts.oracle_gauntlet_compound --ids A15_... A9_... \\
        --data-dir data --compounds-dir data/oracle/compounds

    python -m scripts.oracle_gauntlet_compound --tier m --ids <id> \\
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

# ---------------------------------------------------------------------------
# Tier-M annual bucket definitions
# Pre-registered in research/ORACLE_TIERM_MODERN_GATE_PREREG.md — FROZEN.
# ---------------------------------------------------------------------------
_TIERM_BUCKETS = [
    ("2021",    "2021-01-01", "2021-12-31"),
    ("2022",    "2022-01-01", "2022-12-31"),
    ("2023",    "2023-01-01", "2023-12-31"),
    ("2024",    "2024-01-01", "2024-12-31"),
    ("2025-26", "2025-01-01", "2026-12-31"),
]
_TIERM_OOS_SPLIT = pd.Timestamp("2023-12-31")


def _load_episodes_safe(data_dir: Path, tier: str) -> pd.DataFrame:
    """Load episodes, returning an empty DataFrame if the file is absent.

    For tier-m the episodes file may not yet exist (panel build in-flight);
    compounds that do not use episode_event rules still run cleanly.
    """
    try:
        return _load_episodes(data_dir, tier)
    except FileNotFoundError:
        import warnings
        warnings.warn(
            f"episodes_{tier}.parquet not found — using empty episodes DataFrame. "
            "Compounds with episode_event rules will produce zero entries.",
            stacklevel=3,
        )
        return pd.DataFrame(columns=[
            "episode_id", "node", "direction", "onset_date",
            "confirmed_date", "undeniable_date",
        ])


def run(ids, data_dir: Path, compounds_dir: Path, split: pd.Timestamp,
        n_placebo: int, seed: int, tier: str = "s") -> dict:
    rng = np.random.default_rng(seed)
    panel = augment_panel_with_derived(_load_panel(data_dir, tier))
    episodes = _load_episodes_safe(data_dir, tier)
    # Tier-m: spy is None (screener convention — RS excess, no SPY benchmark).
    # Tier-s: load SPY for benchmark subtraction.
    spy = _load_spy(data_dir) if tier == "s" else None
    rg = _load_rotation_groups(data_dir)
    reg = {c["id"]: c for c in load_registry(compounds_dir)}

    # Placebo urn: realizable 63d excess per node over ALL panel dates.
    all_entry = {node: list(panel.xs(node, level="node").index)
                 for node in panel.index.get_level_values("node").unique()}
    urn_fwd = _compute_forward_returns(all_entry, panel, spy, [H], tier)
    urn = {n: g["excess"].dropna().values
           for n, g in urn_fwd[urn_fwd.horizon_d == H].groupby("node")}

    results = {}
    for cid in ids:
        if cid not in reg:
            print(f"[skip] {cid} not in registry")
            continue
        ed = get_entry_dates(reg[cid], panel, episodes, rg)
        fwd = _compute_forward_returns(ed, panel, spy, [H], tier)
        f = fwd[fwd.horizon_d == H].dropna(subset=["excess"]).copy()
        real = float(f["excess"].mean())
        n = len(f)
        hit = float((f["excess"] > 0).mean())
        print(f"\n===== {cid} =====  n={n}  effect63={real*100:+.2f}%  hit63={hit*100:.1f}%")

        if tier == "s":
            # ------------------------------------------------------------------
            # TIER-S path: unchanged from original implementation
            # ------------------------------------------------------------------
            # G2 — per-era magnitude (4 eras, >= 3 must be consistent)
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

            # G1 — OOS holdout (split = CLI --split, default 2019-12-31)
            f["ed"] = pd.to_datetime(f["entry_date"])
            dev = f[f["ed"] <= split]["excess"]
            hold = f[f["ed"] > split]["excess"]
            dv, hv = float(dev.mean()), float(hold.mean())
            hh = float((hold > 0).mean()) if len(hold) else float("nan")
            g1 = (np.sign(hv) == np.sign(dv)) and (hh >= 0.52) and (len(hold) >= 100)
            print(f" G1 OOS: dev(<= {split.date()}) n={len(dev)} eff={dv*100:+.2f}%  |  "
                  f"HOLDOUT n={len(hold)} eff={hv*100:+.2f}% hit={hh*100:.1f}%")

            # G3 — timing placebo (shared with tier-m below)
            g3, pval, p95, draws = _run_placebo(f, real, urn, n_placebo, rng)

            verdict = bool(g1 and g2 and g3)
            print(f" --> G1={'PASS' if g1 else 'FAIL'}  G2={'PASS' if g2 else 'FAIL'} "
                  f"({pos}/4)  G3={'PASS' if g3 else 'FAIL'}  ==> "
                  f"{'*** GAUNTLET PASS ***' if verdict else 'FAIL'}")
            results[cid] = {"n": n, "effect_63d": real, "hit_63d": hit,
                            "g1_oos": g1, "g2_era_pos": pos, "g3_placebo": g3,
                            "placebo_p": pval, "verdict": verdict}

        else:
            # ------------------------------------------------------------------
            # TIER-M path: modern-regime gate
            # Pre-registered in research/ORACLE_TIERM_MODERN_GATE_PREREG.md
            # ------------------------------------------------------------------
            f["ed"] = pd.to_datetime(f["entry_date"])

            # G2-modern: 5 annual buckets (2021 / 2022 / 2023 / 2024 / 2025-26)
            # bucket n < 20 → insufficient → counts as NOT consistent
            consistent_buckets = 0
            print(" G2 modern annual buckets:")
            for bkt_label, bkt_start, bkt_end in _TIERM_BUCKETS:
                mask = (f["ed"] >= pd.Timestamp(bkt_start)) & (f["ed"] <= pd.Timestamp(bkt_end))
                s = f[mask]["excess"]
                if len(s) >= 20:
                    m = float(s.mean())
                    same_sign = (np.sign(m) == np.sign(real)) if real != 0 else (m == 0)
                    consistent_buckets += int(same_sign)
                    print(f"    {bkt_label}: n={len(s):5d}  eff={m*100:+.2f}%  "
                          f"hit={(s>0).mean()*100:.1f}%  "
                          f"{'(consistent)' if same_sign else '(INCONSISTENT)'}")
                else:
                    print(f"    {bkt_label}: n={len(s):5d}  (insufficient — counts NOT consistent)")
            g2 = consistent_buckets >= 4

            # G1-modern OOS: split 2023-12-31
            m_split = _TIERM_OOS_SPLIT
            dev = f[f["ed"] <= m_split]["excess"]
            hold = f[f["ed"] > m_split]["excess"]
            dv, hv = float(dev.mean()), float(hold.mean())
            hh = float((hold > 0).mean()) if len(hold) else float("nan")
            g1 = (np.sign(hv) == np.sign(dv)) and (hh >= 0.52) and (len(hold) >= 100)
            print(f" G1-modern OOS: dev(<= {m_split.date()}) n={len(dev)} eff={dv*100:+.2f}%  |  "
                  f"HOLDOUT n={len(hold)} eff={hv*100:+.2f}% hit={hh*100:.1f}%")

            # Effect/hit floor
            floor = (n >= 100) and (abs(real) >= 0.01 or hit >= 0.55)

            # G3 — timing placebo (same logic as tier-s, urn built from tier-m panel)
            g3, pval, p95, draws = _run_placebo(f, real, urn, n_placebo, rng)

            verdict = bool(floor and g1 and g2 and g3)
            print(f" Floor: n={n}>=100={'PASS' if n>=100 else 'FAIL'}  "
                  f"|effect|>=0.01 or hit>=0.55={'PASS' if floor else 'FAIL'}")
            print(f" --> G1={'PASS' if g1 else 'FAIL'}  "
                  f"G2={'PASS' if g2 else 'FAIL'} ({consistent_buckets}/5)  "
                  f"G3={'PASS' if g3 else 'FAIL'}  ==> "
                  f"{'*** GAUNTLET PASS ***' if verdict else 'FAIL'}")
            results[cid] = {"n": n, "effect_63d": real, "hit_63d": hit,
                            "g1_oos": g1, "g2_bucket_consistent": consistent_buckets,
                            "g3_placebo": g3, "placebo_p": pval, "verdict": verdict}

    return results


def _run_placebo(
    f: pd.DataFrame,
    real: float,
    urn: dict,
    n_placebo: int,
    rng: np.random.Generator,
) -> tuple[bool, float, float, np.ndarray]:
    """Run the timing placebo (G3).

    Returns (g3_pass, p_value, null_p95, draws_array).
    Shared between tier-s and tier-m paths.
    """
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
    return g3, pval, p95, draws


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ids", nargs="+", required=True, help="compound ids to gauntlet")
    p.add_argument("--data-dir", type=Path, default=ROOT / "data")
    p.add_argument("--compounds-dir", type=Path, default=None)
    p.add_argument("--split", type=str, default="2019-12-31",
                   help="frozen dev/holdout boundary (tier s only; tier m uses 2023-12-31)")
    p.add_argument("--n-placebo", type=int, default=500)
    p.add_argument("--seed", type=int, default=20260704)
    p.add_argument("--tier", choices=["s", "m"], default="s",
                   help="panel tier: s=full-history Tier-S (default), "
                        "m=modern-regime Tier-M (2021-2026)")
    args = p.parse_args()
    compounds_dir = args.compounds_dir or (args.data_dir / "oracle" / "compounds")
    run(args.ids, args.data_dir, compounds_dir, pd.Timestamp(args.split),
        args.n_placebo, args.seed, tier=args.tier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
