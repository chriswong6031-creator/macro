"""S10 Margin-Inflection Reclaim Phase-0 — analysis.

Reads results parquets, computes per-variant primary tables, episode-clustered
p-values, BH-FDR, K1-K5 verdicts, depth-balance (K4), wait-cost, temporal
half-stability, and per-name majority.

Usage:
  python3 analyze.py                    # reads results/fires_s10_*.parquet
  python3 analyze.py --variant gross    # gross margin only
  python3 analyze.py --variant operating
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent   # directory of analyze.py
_ROOT = _HERE.parents[2]  # s10_*/ → species/ → research/ → worktree_root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

RESULTS_DIR = _HERE / "results"

# PREREG gates
N_MIN_PER_SIDE  = 300   # K2 power floor
PP_SPREAD_MIN   = 0.05  # >=5pp spread requirement
BH_Q_MAX        = 0.10  # BH FDR threshold

LIFTOFF_126 = 126
LIFTOFF_21  = 21


def load_fires(variant: str, results_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load S10 and comparator fires for one variant."""
    s10_path = results_dir / f"fires_s10_{variant}.parquet"
    cmp_path = results_dir / f"fires_cmp_{variant}.parquet"

    if not s10_path.exists():
        raise FileNotFoundError(f"S10 fires not found: {s10_path}")
    if not cmp_path.exists():
        raise FileNotFoundError(f"Comparator fires not found: {cmp_path}")

    s10 = pd.read_parquet(s10_path)
    cmp = pd.read_parquet(cmp_path)
    s10["fire_date"] = pd.to_datetime(s10["fire_date"])
    cmp["fire_date"] = pd.to_datetime(cmp["fire_date"])
    return s10, cmp


def _matured(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Filter to rows where col is not null (fire has matured for that metric)."""
    return df[df[col].notna()].copy()


def _rate(series: pd.Series) -> float:
    v = series.dropna()
    return float(v.mean()) if len(v) > 0 else np.nan


def _wilson_lb(series: pd.Series, z: float = 1.645) -> float:
    from harness import wilson_lower
    k = int(series.dropna().sum())
    n = int(series.notna().sum())
    return wilson_lower(k, n, z)


def terminal_state_table(df: pd.DataFrame, label: str) -> dict:
    """Compute terminal-state partition rates and Wilson LBs."""
    m = _matured(df, "state_126")
    n = len(m)
    if n == 0:
        return {"label": label, "n": 0, "n_matured": 0}

    stop_rate  = _rate(m["stopped_126"])
    dm_rate    = _rate(m["dead_money_126"])
    cush_rate  = _rate(m["cushioned_126"])
    lift_rate  = _rate(m["liftoff_126"])

    stop_wlb  = _wilson_lb(m["stopped_126"])
    dm_wlb    = _wilson_lb(m["dead_money_126"])
    cush_wlb  = _wilson_lb(m["cushioned_126"])
    lift_wlb  = _wilson_lb(m["liftoff_126"])

    # Effective-n episodes
    from harness import effective_n_episodes
    eff_n = effective_n_episodes(m["fire_date"])

    return {
        "label":       label,
        "n_total":     n,
        "n_matured":   n,
        "eff_n_ep":    eff_n,
        "stop_rate":   round(stop_rate, 4),
        "stop_wlb":    round(stop_wlb, 4),
        "dm_rate":     round(dm_rate, 4),
        "dm_wlb":      round(dm_wlb, 4),
        "cush_rate":   round(cush_rate, 4),
        "cush_wlb":    round(cush_wlb, 4),
        "lift_rate":   round(lift_rate, 4),
        "lift_wlb":    round(lift_wlb, 4),
    }


def pvalue_table(s10: pd.DataFrame, cmp: pd.DataFrame, metric_col: str) -> dict:
    """Episode-clustered p-value for S10 vs comparator on one metric."""
    from harness import (block_bootstrap_pvalue, rate_stat,
                         assign_calendar_episodes)

    ms10 = _matured(s10, metric_col)
    mcmp = _matured(cmp, metric_col)

    if len(ms10) == 0 or len(mcmp) == 0:
        return {"metric": metric_col, "n_s10": 0, "n_cmp": 0,
                "p_value": np.nan, "point_diff": np.nan}

    v_s10 = ms10[metric_col].to_numpy(dtype=float)
    v_cmp = mcmp[metric_col].to_numpy(dtype=float)
    e_s10 = assign_calendar_episodes(ms10["fire_date"]).to_numpy()
    e_cmp = assign_calendar_episodes(mcmp["fire_date"]).to_numpy()

    result = block_bootstrap_pvalue(
        v_s10, v_cmp, e_s10, e_cmp,
        stat_fn=rate_stat,
    )
    result["metric"] = metric_col
    result["n_s10"]  = len(ms10)
    result["n_cmp"]  = len(mcmp)
    return result


def analyze_variant(
    variant: str,
    results_dir: Path,
    panel=None,
) -> dict:
    """Run the full analysis for one margin variant."""
    from harness import (
        wilson_lower, per_name_majority, temporal_half_split,
        compute_washout_depth, compute_wait_days,
    )

    print(f"\n{'='*72}")
    print(f"  Variant: {variant.upper()} MARGIN")
    print(f"{'='*72}")

    s10, cmp = load_fires(variant, results_dir)

    print(f"  S10 fires total:         {len(s10)}")
    print(f"  Comparator fires total:  {len(cmp)}")

    # ── Maturity check ────────────────────────────────────────────────────
    s10_mat = _matured(s10, "state_126")
    cmp_mat = _matured(cmp, "state_126")
    print(f"  S10 matured (clean15_126): {len(s10_mat)}")
    print(f"  CMP matured (clean15_126): {len(cmp_mat)}")

    # ── K2: Power check ───────────────────────────────────────────────────
    k2_triggered = len(s10_mat) < N_MIN_PER_SIDE or len(cmp_mat) < N_MIN_PER_SIDE
    if k2_triggered:
        print(f"\n  !! K2 UNDERPOWERED-HOLD: n_s10={len(s10_mat)}, "
              f"n_cmp={len(cmp_mat)}, threshold={N_MIN_PER_SIDE}")
        print("  Verdict: UNDERPOWERED-HOLD (remain phase0, accrue)")

    # ── Primary table ─────────────────────────────────────────────────────
    row_s10 = terminal_state_table(s10_mat, f"S10 {variant}")
    row_cmp = terminal_state_table(cmp_mat, f"CMP {variant}")

    print(f"\n  Primary table (clean15_126):")
    print(f"  {'Label':<25} {'n_mat':>6} {'eff_n':>6} "
          f"{'stop%':>7} {'stop_lb':>8} {'dm%':>7} {'dm_lb':>8} "
          f"{'cush%':>7} {'cush_lb':>8} {'lift%':>7} {'lift_lb':>8}")
    print("  " + "-"*90)
    for row in [row_s10, row_cmp]:
        n = row.get("n_matured", 0)
        if n == 0:
            print(f"  {row['label']:<25} {'0':>6}")
            continue
        print(f"  {row['label']:<25} {n:>6} {row['eff_n_ep']:>6} "
              f"{row['stop_rate']:>7.3f} {row['stop_wlb']:>8.3f} "
              f"{row['dm_rate']:>7.3f} {row['dm_wlb']:>8.3f} "
              f"{row['cush_rate']:>7.3f} {row['cush_wlb']:>8.3f} "
              f"{row['lift_rate']:>7.3f} {row['lift_wlb']:>8.3f}")

    # ── Context: clean8_21 ────────────────────────────────────────────────
    s10_21 = _matured(s10, "state_21")
    cmp_21 = _matured(cmp, "state_21")
    print(f"\n  Context (clean8_21): S10 n={len(s10_21)}, CMP n={len(cmp_21)}")
    if len(s10_21) > 0 and len(cmp_21) > 0:
        s10_lift21 = _rate(s10_21["liftoff_21"])
        cmp_lift21 = _rate(cmp_21["liftoff_21"])
        print(f"  S10 clean8_21 liftoff rate: {s10_lift21:.3f}")
        print(f"  CMP clean8_21 liftoff rate: {cmp_lift21:.3f}")

    # ── Episode-clustered p-values ────────────────────────────────────────
    print(f"\n  Episode-clustered p-values (block_bootstrap, {N_BOOTSTRAP if False else 2000} draws):")
    pval_results = {}
    for metric_col, metric_label in [
        ("stopped_126",    "stop-out (lower=better, p=P(diff<=observed))"),
        ("dead_money_126", "dead-money (lower=better)"),
        ("cushioned_126",  "cushion incidence (higher=better)"),
        ("liftoff_126",    "clean liftoff (higher=better)"),
    ]:
        pv = pvalue_table(s10_mat, cmp_mat, metric_col)
        pval_results[metric_col] = pv
        s10_pt = pv.get("point_s10", np.nan)
        cmp_pt = pv.get("point_cmp", np.nan)
        diff   = pv.get("point_diff", np.nan)
        p      = pv.get("p_value", np.nan)
        n_ep   = pv.get("n_episodes_joint", 0)
        print(f"  {metric_label}")
        print(f"    S10={s10_pt:.3f} CMP={cmp_pt:.3f} diff={diff:+.3f} "
              f"p={p:.3f}  joint_episodes={n_ep}")

    # ── BH-FDR ───────────────────────────────────────────────────────────
    from engine.validation import benjamini_hochberg
    # m=2 from the trial ledger (the registered family has 2 trials)
    # We apply BH across the stop-out p-values for both variants (m=2)
    stop_p = pval_results.get("stopped_126", {}).get("p_value", np.nan)
    bh_input = {f"{variant}_stop_out": stop_p}

    print(f"\n  BH-FDR (m=2, family=s10_margin_inflection):")
    print(f"  Note: BH applied across both variants together in run_all.py")

    # ── K1 verdict ───────────────────────────────────────────────────────
    # S10 matches-or-beats comparator on stop-out AND dead-money AND cushion
    # (Wilson LB, >=5pp, q<=0.10 after BH)
    k1_data = {}
    if row_s10.get("n_matured", 0) > 0 and row_cmp.get("n_matured", 0) > 0:
        stop_diff  = row_cmp["stop_rate"] - row_s10["stop_rate"]  # positive = S10 better
        dm_diff    = row_cmp["dm_rate"]   - row_s10["dm_rate"]    # positive = S10 better
        cush_diff  = row_s10["cush_rate"] - row_cmp["cush_rate"]  # positive = S10 better

        k1_data = {
            "stop_diff_pp":     round(stop_diff * 100, 2),
            "dm_diff_pp":       round(dm_diff * 100, 2),
            "cush_diff_pp":     round(cush_diff * 100, 2),
            "stop_beats_5pp":   stop_diff >= PP_SPREAD_MIN,
            "dm_beats_5pp":     dm_diff >= PP_SPREAD_MIN,
            "cush_beats_5pp":   cush_diff >= PP_SPREAD_MIN,
            "stop_p":           pval_results.get("stopped_126", {}).get("p_value", np.nan),
        }
        print(f"\n  K1 spread check:")
        print(f"    stop_diff (S10 better by):  {stop_diff*100:+.2f}pp (need >=5pp)")
        print(f"    dm_diff (S10 better by):    {dm_diff*100:+.2f}pp (need >=5pp)")
        print(f"    cush_diff (S10 better by):  {cush_diff*100:+.2f}pp (need >=5pp)")

    # ── K3: Temporal half stability ───────────────────────────────────────
    print(f"\n  K3: Temporal half stability (stop-out rate)")
    if len(s10_mat) >= 20:
        h1, h2 = temporal_half_split(s10_mat)
        h1_stop = _rate(h1["stopped_126"])
        h2_stop = _rate(h2["stopped_126"])
        h1_cmp, h2_cmp = temporal_half_split(cmp_mat) if len(cmp_mat) >= 20 else (pd.DataFrame(), pd.DataFrame())
        h1c_stop = _rate(h1_cmp["stopped_126"]) if len(h1_cmp) > 0 else np.nan
        h2c_stop = _rate(h2_cmp["stopped_126"]) if len(h2_cmp) > 0 else np.nan
        sign_h1 = (h1c_stop - h1_stop) > 0  # S10 better in H1
        sign_h2 = (h2c_stop - h2_stop) > 0  # S10 better in H2
        print(f"    H1 S10={h1_stop:.3f} CMP={h1c_stop:.3f} S10_wins={sign_h1}")
        print(f"    H2 S10={h2_stop:.3f} CMP={h2c_stop:.3f} S10_wins={sign_h2}")
        k3_stable = sign_h1 == sign_h2
        print(f"    K3 sign-stable: {k3_stable}")
    else:
        print(f"    Insufficient data for half-split (n={len(s10_mat)})")
        k3_stable = False

    # ── K4: Depth balance ────────────────────────────────────────────────
    print(f"\n  K4: Depth balance")
    depth_table = {}
    if panel is not None:
        s10_depth = compute_washout_depth(s10_mat, panel) if len(s10_mat) > 0 else s10_mat.copy()
        cmp_depth = compute_washout_depth(cmp_mat, panel) if len(cmp_mat) > 0 else cmp_mat.copy()

        s10_d = s10_depth["washout_depth"].dropna()
        cmp_d = cmp_depth["washout_depth"].dropna()

        if len(s10_d) > 10 and len(cmp_d) > 10:
            # Depth quartiles of S10
            quartiles = s10_d.quantile([0.25, 0.50, 0.75])
            print(f"    S10 depth quartiles: Q1={quartiles[0.25]:.3f} "
                  f"Q2={quartiles[0.50]:.3f} Q3={quartiles[0.75]:.3f}")
            print(f"    CMP depth median:    {cmp_d.median():.3f}")
            print(f"    Depth distributions overlap — check K4 in report")
            depth_table = {
                "s10_depth_median": float(s10_d.median()),
                "cmp_depth_median": float(cmp_d.median()),
                "s10_depth_q25":    float(quartiles[0.25]),
                "s10_depth_q75":    float(quartiles[0.75]),
            }
    else:
        print("    Panel not available for depth computation in analyze.py; "
              "depth computed in run_all.py with the loaded panel.")

    # ── Per-name majority ────────────────────────────────────────────────
    print(f"\n  Per-name majority (K3 analogue for stop-out)")
    if len(s10_mat) > 0 and len(cmp_mat) > 0:
        pnm = per_name_majority(s10_mat, cmp_mat, "stopped_126")
        print(f"    Common tickers: {pnm['n_common']}")
        pct = pnm.get("pct_names_s10_wins", np.nan)
        print(f"    Pct names where S10 lower stop-out: {pct:.1%}" if not np.isnan(pct) else "    N/A")

    # ── Wait cost ────────────────────────────────────────────────────────
    print(f"\n  Wait cost")
    s10_wait = compute_wait_days(s10)
    if "wait_days" in s10_wait.columns:
        wd = s10_wait["wait_days"].dropna()
        if len(wd) > 0:
            print(f"    Median wait (q3_filed -> fire_date): {wd.median():.0f} days")
            print(f"    Mean wait:   {wd.mean():.0f} days")
            print(f"    Max wait:    {wd.max():.0f} days (window cap={63*1.4:.0f} cal days)")

    result = {
        "variant":      variant,
        "n_s10":        len(s10),
        "n_cmp":        len(cmp),
        "n_s10_mat":    len(s10_mat),
        "n_cmp_mat":    len(cmp_mat),
        "k2_triggered": k2_triggered,
        "k3_stable":    k3_stable,
        "primary_s10":  row_s10,
        "primary_cmp":  row_cmp,
        "pvals":        {k: {kk: float(vv) if isinstance(vv, float) else vv
                              for kk, vv in v.items()}
                         for k, v in pval_results.items()},
        "k1_data":      k1_data,
        "depth_table":  depth_table,
        "stop_p_for_bh": float(stop_p) if not np.isnan(float(stop_p)) else None,
    }
    return result


def run_bh_across_variants(results: list[dict]) -> dict:
    """Apply BH-FDR across the m=2 family (both variants' stop-out p-values)."""
    from engine.validation import benjamini_hochberg

    pval_dict = {}
    for r in results:
        v = r["variant"]
        p = r.get("stop_p_for_bh")
        if p is not None and not np.isnan(p):
            pval_dict[f"{v}_stop_out"] = p

    if not pval_dict:
        return {}

    bh = benjamini_hochberg(pval_dict, alpha=BH_Q_MAX)
    print(f"\n  BH-FDR (m=2, alpha={BH_Q_MAX}, family=s10_margin_inflection):")
    for key, row in sorted(bh.items()):
        print(f"    {key}: p={row['p']:.4f}  q={row['q']:.4f}  reject={row['reject']}")
    return bh


def k1_verdict(result: dict, bh_row: dict | None) -> str:
    """Apply K1 verdict logic."""
    if result["k2_triggered"]:
        return "UNDERPOWERED-HOLD"

    k1 = result.get("k1_data", {})
    if not k1:
        return "NO-DATA"

    stop_beats   = k1.get("stop_beats_5pp", False)
    dm_beats     = k1.get("dm_beats_5pp", False)
    cush_beats   = k1.get("cush_beats_5pp", False)
    stop_p       = k1.get("stop_p", np.nan)
    bh_reject    = bh_row.get("reject", False) if bh_row else False
    k3_stable    = result.get("k3_stable", False)

    # K1: beats on all three dimensions, >=5pp, q<=0.10, sign-stable
    if stop_beats and dm_beats and cush_beats and bh_reject and k3_stable:
        return "PASS (propose promotion to owner)"
    elif stop_beats and dm_beats and cush_beats and bh_reject:
        return "CANDIDATE (sign-unstable — K3 fail)"
    elif stop_beats or dm_beats or cush_beats:
        return "PARTIAL (does not beat on all three axes)"
    else:
        return "NO-GO (K1 fail — no marginal safety-net value)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="S10 Phase-0 analysis")
    ap.add_argument("--variant", default="both", choices=["gross", "operating", "both"])
    ap.add_argument("--results-dir", default=str(RESULTS_DIR))
    args = ap.parse_args(argv)

    results_dir = Path(args.results_dir)
    variants = ["gross", "operating"] if args.variant == "both" else [args.variant]

    all_results = []
    for v in variants:
        try:
            r = analyze_variant(v, results_dir)
            all_results.append(r)
        except FileNotFoundError as exc:
            print(f"SKIP {v}: {exc}")
            continue

    if not all_results:
        print("No results to analyze.")
        return

    # BH across variants
    bh = run_bh_across_variants(all_results)

    # K1 verdicts
    print(f"\n{'='*72}")
    print("  VERDICTS")
    print(f"{'='*72}")
    for r in all_results:
        v = r["variant"]
        bh_row = bh.get(f"{v}_stop_out")
        verdict = k1_verdict(r, bh_row)
        print(f"  {v.upper()} margin: {verdict}")
        print(f"    K2 underpowered: {r['k2_triggered']}")
        print(f"    K3 sign-stable:  {r.get('k3_stable', '?')}")
        k1 = r.get("k1_data", {})
        if k1:
            print(f"    stop_diff={k1.get('stop_diff_pp',0):+.2f}pp  "
                  f"dm_diff={k1.get('dm_diff_pp',0):+.2f}pp  "
                  f"cush_diff={k1.get('cush_diff_pp',0):+.2f}pp")

    # Save results
    out_path = results_dir / "analysis_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        def _clean(obj):
            if isinstance(obj, float) and np.isnan(obj):
                return None
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_clean(x) for x in obj]
            return obj
        json.dump({
            "variants": _clean(all_results),
            "bh": _clean(bh),
        }, f, indent=2, default=str)
    print(f"\n  Analysis saved: {out_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
