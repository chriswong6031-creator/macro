"""S7 RS-Repair Phase-0 — analysis: dev tables per SPEC §6/§7.

Reads the per-fire parquet (results/fires_with_metrics_p*.parquet) and
produces stratum tables + bootstrap CIs.

Frozen hypotheses:
  H-A: rs_spy_slope20 (and cohort variants) stratify fire quality?
  H-B: triple-lock cohort_frac_w>=40 ∩ rs_repair ∩ loc60_15
  H-C: cohort>=50% fires during SPY-below-falling-200D (regime split)

Usage:
  python3 analyze.py --panel p1           (dev only, default)
  python3 analyze.py --panel p2
  python3 analyze.py --panel both
  python3 analyze.py --panel p1 --holdout  (WARNING: unlocks holdout)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)

log = logging.getLogger(__name__)

# Dev / holdout split per SPEC §7
DEV_END     = pd.Timestamp("2024-12-31")
HOLDOUT_START = pd.Timestamp("2025-01-01")

# Minimum episodes for a verdict (SPEC §6 guardrail)
MIN_EPISODES = 8
N_BOOTSTRAP  = 2000


def _load_fires(panel: str, results_dir: Path, holdout: bool) -> pd.DataFrame:
    fname = f"fires_with_metrics_{panel}.parquet"
    path = results_dir / fname
    if not path.exists():
        raise FileNotFoundError(f"Fires parquet not found: {path}")
    df = pd.read_parquet(path)
    df["fire_date"] = pd.to_datetime(df["fire_date"])

    if holdout:
        df = df[df["fire_date"] >= HOLDOUT_START].copy()
        print(f"[HOLDOUT UNLOCKED] Using {len(df)} fires from {HOLDOUT_START.date()} onward")
    else:
        df = df[df["fire_date"] <= DEV_END].copy()

    # PATCH 3: exclude contiguity_ok==False fires from ALL analysis
    if "contiguity_ok" in df.columns:
        n_before = len(df)
        df = df[df["contiguity_ok"] != False].copy()  # noqa: E712 (handles None/NaN safely)
        contiguity_dropped = n_before - len(df)
        print(f"[contiguity] dropped {contiguity_dropped} fires (contiguity_ok==False) "
              f"out of {n_before} ({100*contiguity_dropped/max(n_before,1):.1f}%)")
    else:
        print("[contiguity] contiguity_ok column not found; no filtering applied")

    return df


def _episode_block_ci(values: np.ndarray, episode_ids: np.ndarray,
                      stat_fn, n_draws: int, ci: float = 0.90) -> dict:
    from harness import episode_block_bootstrap
    valid = ~np.isnan(values)
    return episode_block_bootstrap(
        values[valid], episode_ids[valid], stat_fn, n_draws=n_draws, ci=ci
    )


def _stratum_row(label: str, mask: np.ndarray, df: pd.DataFrame,
                 metric_col: str, metric_fn, n_draws: int) -> dict | None:
    """Compute one stratum row (computable-subset baseline is handled by caller)."""
    from harness import cluster_episodes

    sub = df[mask].copy()
    if sub.empty:
        return None
    values = sub[metric_col].to_numpy(dtype=float)
    valid = ~np.isnan(values)
    n_fires = int(valid.sum())
    if n_fires == 0:
        return None

    dates = sub["fire_date"].tolist()
    ep_ids = np.array(cluster_episodes(dates), dtype=int)

    n_episodes = len(np.unique(ep_ids[valid]))
    n_valid = int(valid.sum())
    if n_episodes < MIN_EPISODES:
        # Deviation D1 (REPORT.md §Deviations): broad strata fire near-continuously,
        # so gap-clustering collapses to one giant episode and the frozen guardrail
        # would refuse a verdict on the headline strata. Fall back to calendar-month
        # blocks — a standard time-block bootstrap preserving temporal dependence.
        months = (sub["fire_date"].dt.year.to_numpy() * 12
                  + sub["fire_date"].dt.month.to_numpy())
        m_ids = np.unique(months, return_inverse=True)[1]
        n_months = len(np.unique(m_ids[valid]))
        if n_months >= MIN_EPISODES:
            bci = _episode_block_ci(values, m_ids, metric_fn, n_draws)
            bci.setdefault("n_valid", n_valid)
            n_episodes = n_months
            verdict = "OK (month-block D1)"
        else:
            verdict = (f"NO_VERDICT (episodes={n_episodes} < {MIN_EPISODES}; "
                       f"months={n_months} < {MIN_EPISODES})")
            bci = {"point": float(np.nanmean(values)), "ci_lo": np.nan, "ci_hi": np.nan,
                   "n_episodes": n_episodes, "n_fires": n_fires, "n_valid": n_valid}
    else:
        bci = _episode_block_ci(values, ep_ids, metric_fn, n_draws)
        bci.setdefault("n_valid", n_valid)
        verdict = "OK"

    return {
        "stratum": label,
        "n_fires": n_fires,
        "n_valid": bci.get("n_valid", n_valid),
        "n_episodes": n_episodes,
        "point": bci["point"],
        "ci_lo": bci["ci_lo"],
        "ci_hi": bci["ci_hi"],
        "verdict": verdict,
    }


def _delta_row(label: str, mask_a: np.ndarray, mask_b: np.ndarray,
               df: pd.DataFrame, metric_col: str, metric_fn,
               n_draws: int) -> dict | None:
    """Deviation D1b: paired month-block delta bootstrap (stat_A - stat_B).

    Resamples calendar months with replacement over the union subset; each
    draw computes metric_fn on stratum A fires and stratum B fires within the
    drawn months and takes the difference.  This is the honest test when the
    marginal stratum CIs overlap.
    """
    union = mask_a | mask_b
    sub = df[union].copy()
    if sub.empty:
        return None
    a_flag = mask_a[union]
    values = sub[metric_col].to_numpy(dtype=float)
    valid = ~np.isnan(values)
    if valid.sum() == 0:
        return None
    months = (sub["fire_date"].dt.year.to_numpy() * 12
              + sub["fire_date"].dt.month.to_numpy())
    uniq, m_ids = np.unique(months, return_inverse=True)
    n_months = len(uniq)
    if n_months < MIN_EPISODES:
        return None

    def _stat(vals: np.ndarray, flags: np.ndarray) -> float:
        va, vb = vals[flags], vals[~flags]
        va, vb = va[~np.isnan(va)], vb[~np.isnan(vb)]
        if len(va) == 0 or len(vb) == 0:
            return np.nan
        return float(metric_fn(va) - metric_fn(vb))

    point = _stat(values, a_flag)
    rng = np.random.default_rng(42)
    groups = {m: np.where(m_ids == m)[0] for m in range(n_months)}
    boots = np.empty(n_draws)
    for b in range(n_draws):
        drawn = rng.choice(n_months, size=n_months, replace=True)
        idx = np.concatenate([groups[m] for m in drawn])
        boots[b] = _stat(values[idx], a_flag[idx])
    ci_lo = float(np.nanquantile(boots, 0.05))
    ci_hi = float(np.nanquantile(boots, 0.95))
    return {
        "stratum": label,
        "n_fires": int(mask_a.sum()),
        "n_valid": int((~np.isnan(values[a_flag])).sum()),
        "n_episodes": n_months,
        "point": point,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "verdict": ("EXCLUDES 0" if (ci_lo > 0 or ci_hi < 0) else "spans 0"),
    }


def _print_table(rows: list[dict], title: str) -> None:
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    hdr = f"{'Stratum':<35} {'n_fires':>7} {'n_valid':>7} {'eps':>5} {'point':>7} "
    hdr += f"{'CI_lo':>7} {'CI_hi':>7} {'verdict'}"
    print(hdr)
    print("-" * 95)
    for r in rows:
        n_valid = r.get("n_valid", r["n_fires"])
        print(f"{r['stratum']:<35} {r['n_fires']:>7} {n_valid:>7} {r['n_episodes']:>5} "
              f"{r['point']:>7.3f} {r['ci_lo']:>7.3f} {r['ci_hi']:>7.3f} "
              f"{r['verdict']}")


def analyze_panel(df: pd.DataFrame, panel: str, results_dir: Path,
                  n_draws: int = N_BOOTSTRAP) -> None:
    """Run all hypothesis tables for one panel."""
    from harness import stop_out_rate, clean_rate, cluster_episodes

    print(f"\n{'#'*72}")
    print(f"# Panel: {panel.upper()}  |  Dev fires: {len(df)}  |  "
          f"Date range: {df['fire_date'].min().date()} — {df['fire_date'].max().date()}")
    print(f"{'#'*72}")

    # Usable window summary
    if "fire_type" in df.columns:
        for ft in df["fire_type"].unique():
            sub = df[df["fire_type"] == ft]
            print(f"  Fire type {ft}: n={len(sub)},  "
                  f"date range {sub['fire_date'].min().date()} – "
                  f"{sub['fire_date'].max().date()}")

    # Coverage per feature
    feat_cols = [
        "rs_spy_slope20", "rs_sect_slope20", "rs_sect_hl",
        "rs_cohort_rank_slope20", "rs_low", "cohort_frac_w",
        "loc60_12", "loc60_15", "above_10w",
    ]
    if panel == "P2":
        feat_cols.append("monthly_dwell")
    print("\nFeature coverage (% of fires with non-null value):")
    for col in feat_cols:
        if col in df.columns:
            pct = 100 * df[col].notna().mean()
            print(f"  {col:<30} {pct:5.1f}%")
        else:
            print(f"  {col:<30}  missing column")

    # Choose primary metric columns
    if panel == "P1":
        primary_metric = "race_stop_out"
        co_primary     = "clean8_21"    # P1 tail truncates 126-td maturity
    else:
        primary_metric = "race_stop_out"
        co_primary     = "clean15_126"

    for fire_type in sorted(df["fire_type"].unique() if "fire_type" in df.columns else ["F1"]):
        ft_df = df[df["fire_type"] == fire_type] if "fire_type" in df.columns else df
        print(f"\n\n{'─'*72}")
        print(f"  Fire type: {fire_type}   ({len(ft_df)} fires)")
        print(f"{'─'*72}")

        _run_ha(ft_df, fire_type, panel, primary_metric, co_primary,
                results_dir, n_draws)
        _run_hb(ft_df, fire_type, panel, primary_metric, co_primary,
                results_dir, n_draws)
        if panel == "P1":
            _run_hc(ft_df, fire_type, results_dir, n_draws)

    if panel == "P2":
        _run_p2_by_decade(df, results_dir)


def _subset_baseline(df: pd.DataFrame, feat_col: str, metric_col: str,
                     metric_fn, n_draws: int) -> dict | None:
    """Baseline on the same-computable-subset: all fires where feat_col is non-null."""
    mask = df[feat_col].notna().to_numpy() if feat_col in df.columns else np.ones(len(df), bool)
    return _stratum_row("baseline (computable subset)", mask, df, metric_col, metric_fn, n_draws)


def _run_ha(df: pd.DataFrame, fire_type: str, panel: str,
            primary_metric: str, co_primary: str,
            results_dir: Path, n_draws: int) -> None:
    """H-A: rs_spy_slope20 and cohort variants stratify fire quality."""
    from harness import stop_out_rate, liftoff_rate, clean_rate

    rows_stop = []
    rows_lift = []

    def _median_fwd(v: np.ndarray) -> float:
        v2 = v[~np.isnan(v)]
        return float(np.median(v2)) if len(v2) > 0 else np.nan

    for metric_col, metric_fn, label in [
        (primary_metric,  stop_out_rate,  "stop-out rate (lower=better)"),
        ("race_liftoff",  liftoff_rate,   "liftoff rate (higher=better)"),
        ("fwd_ret_20d",   _median_fwd,    "median fwd_ret_20d"),
        (co_primary,      clean_rate,     f"{co_primary} clean-liftoff rate"),
    ]:
        if metric_col not in df.columns:
            print(f"  [H-A] {metric_col} column missing; skip")
            continue

        rows = []
        # rs_spy_slope20 stratification
        for feat, feat_label in [
            ("rs_spy_slope20", "rs_spy_slope20"),
            ("rs_sect_slope20", "rs_sect_slope20"),
            ("rs_cohort_rank_slope20", "rs_cohort_rank_slope20"),
        ]:
            if feat not in df.columns:
                continue
            base_row = _subset_baseline(df, feat, metric_col, metric_fn, n_draws)
            if base_row:
                base_row["stratum"] = f"baseline [{feat}]"
                rows.append(base_row)
            for val, vlabel in [(1, "repair (>0)"), (0, "deterioration (<=0)")]:
                mask = (df[feat] == val).to_numpy()
                r = _stratum_row(f"  {feat}={vlabel}", mask, df,
                                 metric_col, metric_fn, n_draws)
                if r:
                    rows.append(r)

        # rs_low stratum (WAVE1 baseline that S7 must beat)
        if "rs_low" in df.columns:
            base_row = _subset_baseline(df, "rs_low", metric_col, metric_fn, n_draws)
            if base_row:
                base_row["stratum"] = "baseline [rs_low]"
                rows.append(base_row)
            mask_low = (df["rs_low"] == 1).to_numpy()
            r = _stratum_row("  rs_low=1 (WAVE1 baseline)", mask_low, df,
                              metric_col, metric_fn, n_draws)
            if r:
                rows.append(r)
            mask_high = (df["rs_low"] == 0).to_numpy()
            r = _stratum_row("  rs_low=0 (high RS)", mask_high, df,
                              metric_col, metric_fn, n_draws)
            if r:
                rows.append(r)

        _print_table(rows, f"[H-A] {fire_type}/{panel}  {label}")
        # Save
        _save_csv(rows, results_dir / f"ha_{fire_type}_{panel}_{metric_col}.csv")

        # Deviation D1b: paired delta tables (repair - deterioration per variant,
        # plus the S7 promotion bar: cohort-rank repair - rs_low stratum)
        drows = []
        for feat in ["rs_spy_slope20", "rs_sect_slope20", "rs_cohort_rank_slope20"]:
            if feat not in df.columns:
                continue
            m_rep = (df[feat] == 1).to_numpy()
            m_det = (df[feat] == 0).to_numpy()
            r = _delta_row(f"{feat}: repair - deterioration", m_rep, m_det,
                           df, metric_col, metric_fn, n_draws)
            if r:
                drows.append(r)
        if "rs_cohort_rank_slope20" in df.columns and "rs_low" in df.columns:
            m_rep = (df["rs_cohort_rank_slope20"] == 1).to_numpy()
            m_rsl = (df["rs_low"] == 1).to_numpy()
            r = _delta_row("S7 bar: cohort-rank repair - rs_low stratum",
                           m_rep, m_rsl, df, metric_col, metric_fn, n_draws)
            if r:
                drows.append(r)
        if drows:
            _print_table(drows, f"[H-A deltas] {fire_type}/{panel}  {label}")
            _save_csv(drows, results_dir / f"ha_deltas_{fire_type}_{panel}_{metric_col}.csv")


def _run_hb(df: pd.DataFrame, fire_type: str, panel: str,
            primary_metric: str, co_primary: str,
            results_dir: Path, n_draws: int) -> None:
    """H-B: triple-lock cohort_frac_w>=40 ∩ rs_repair ∩ loc60_15."""
    from harness import stop_out_rate, clean_rate

    if not all(c in df.columns for c in
               ["cohort_frac_w", "rs_spy_slope20", "loc60_15"]):
        print("  [H-B] Required features missing; skip")
        return

    has_coh = df["cohort_frac_w"].notna()
    has_rs  = df["rs_spy_slope20"].notna()
    has_loc = df["loc60_15"].notna()

    coh40 = has_coh & (df["cohort_frac_w"] >= 0.40)
    rs_rep = has_rs & (df["rs_spy_slope20"] == 1)
    loc15  = has_loc & (df["loc60_15"] == 1)

    from harness import liftoff_rate  # noqa: F811

    for metric_col, metric_fn, label in [
        (primary_metric,  stop_out_rate,  "stop-out rate"),
        ("race_liftoff",  liftoff_rate,   "liftoff rate"),
        (co_primary,      clean_rate,     f"{co_primary}"),
    ]:
        if metric_col not in df.columns:
            continue

        # Computable subset baseline = fires where all three features are non-null
        base_mask = (has_coh & has_rs & has_loc).to_numpy()
        rows = []
        base_row = _stratum_row("baseline (all 3 computable)", base_mask,
                                df, metric_col, metric_fn, n_draws)
        if base_row:
            rows.append(base_row)

        # Pairwise combos
        combos = [
            ("cohort>=40 only",          coh40.to_numpy()),
            ("rs_repair only",           rs_rep.to_numpy()),
            ("loc60_15 only",            loc15.to_numpy()),
            ("cohort>=40 + rs_repair",   (coh40 & rs_rep).to_numpy()),
            ("cohort>=40 + loc60_15",    (coh40 & loc15).to_numpy()),
            ("rs_repair + loc60_15",     (rs_rep & loc15).to_numpy()),
            ("TRIPLE-LOCK (all 3)",      (coh40 & rs_rep & loc15).to_numpy()),
        ]
        for name, mask in combos:
            r = _stratum_row(name, mask, df, metric_col, metric_fn, n_draws)
            if r:
                rows.append(r)

        _print_table(rows, f"[H-B] {fire_type}/{panel} triple-lock  {label}")
        _save_csv(rows, results_dir / f"hb_{fire_type}_{panel}_{metric_col}.csv")

        # Deviation D1b: triple-lock paired deltas vs baseline and each pair
        triple = (coh40 & rs_rep & loc15).to_numpy()
        drows = []
        for name, mask in [
            ("TRIPLE - baseline(all3)",     base_mask),
            ("TRIPLE - cohort>=40 only",    coh40.to_numpy()),
            ("TRIPLE - cohort+rs_repair",   (coh40 & rs_rep).to_numpy()),
            ("TRIPLE - cohort+loc60_15",    (coh40 & loc15).to_numpy()),
            ("TRIPLE - rs_repair+loc60_15", (rs_rep & loc15).to_numpy()),
        ]:
            r = _delta_row(name, triple, mask, df, metric_col, metric_fn, n_draws)
            if r:
                drows.append(r)
        if drows:
            _print_table(drows, f"[H-B deltas] {fire_type}/{panel}  {label}")
            _save_csv(drows, results_dir / f"hb_deltas_{fire_type}_{panel}_{metric_col}.csv")


def _run_hc(df: pd.DataFrame, fire_type: str,
            results_dir: Path, n_draws: int) -> None:
    """H-C: cohort >=50% fires during SPY below falling 200D."""
    from harness import stop_out_rate

    if "spy_below_200d" not in df.columns:
        print("  [H-C] spy_below_200d column missing; skip regime split")
        return
    if "cohort_frac_w" not in df.columns:
        print("  [H-C] cohort_frac_w missing; skip")
        return

    metric_col = "race_stop_out"
    if metric_col not in df.columns:
        return

    has_coh = df["cohort_frac_w"].notna()
    coh50 = has_coh & (df["cohort_frac_w"] >= 0.50)
    bear = df["spy_below_200d"].fillna(False).astype(bool)

    rows = []
    # Baseline: coh>=50, any regime
    base_row = _stratum_row("cohort>=50 all regimes",
                            coh50.to_numpy(), df, metric_col, stop_out_rate, n_draws)
    if base_row:
        rows.append(base_row)

    # Bear regime
    r_bear = _stratum_row("cohort>=50 + bear (SPY<200d falling)",
                          (coh50 & bear).to_numpy(), df, metric_col, stop_out_rate, n_draws)
    if r_bear:
        rows.append(r_bear)

    # Bull regime
    r_bull = _stratum_row("cohort>=50 + bull (SPY above/rising 200d)",
                          (coh50 & ~bear).to_numpy(), df, metric_col, stop_out_rate, n_draws)
    if r_bull:
        rows.append(r_bull)

    _print_table(rows, f"[H-C] {fire_type}/P1  regime split (reported, not gating)")
    _save_csv(rows, results_dir / f"hc_{fire_type}_P1_{metric_col}.csv")


def _run_p2_by_decade(df: pd.DataFrame, results_dir: Path) -> None:
    """PATCH 6: per-decade context table for P2 (context only, no verdicts).

    Columns: decade, n_fires, n_valid, stop_out_rate, liftoff_rate, median_fwd_ret_20d.
    Written to results/p2_by_decade.csv.
    """
    rows = []
    df = df.copy()
    df["decade"] = (df["fire_date"].dt.year // 10) * 10

    for decade, sub in df.groupby("decade"):
        n_fires = len(sub)

        # stop_out_rate
        if "race_stop_out" in sub.columns:
            sv = sub["race_stop_out"].dropna().to_numpy(dtype=float)
            n_valid_so = int(len(sv))
            so_rate = float(np.mean(sv == 1)) if n_valid_so > 0 else np.nan
        else:
            n_valid_so = 0
            so_rate = np.nan

        # liftoff_rate
        if "race_liftoff" in sub.columns:
            lv = sub["race_liftoff"].dropna().to_numpy(dtype=float)
            lo_rate = float(np.mean(lv == 1)) if len(lv) > 0 else np.nan
        else:
            lo_rate = np.nan

        # median fwd_ret_20d
        if "fwd_ret_20d" in sub.columns:
            fv = sub["fwd_ret_20d"].dropna().to_numpy(dtype=float)
            med_fwd = float(np.median(fv)) if len(fv) > 0 else np.nan
            n_valid = max(n_valid_so, len(fv))
        else:
            med_fwd = np.nan
            n_valid = n_valid_so

        rows.append({
            "decade": int(decade),
            "n_fires": n_fires,
            "n_valid": n_valid,
            "stop_out_rate": round(so_rate, 4) if not np.isnan(so_rate) else None,
            "liftoff_rate": round(lo_rate, 4) if not np.isnan(lo_rate) else None,
            "median_fwd_ret_20d": round(med_fwd, 4) if not np.isnan(med_fwd) else None,
        })

    if rows:
        out_path = results_dir / "p2_by_decade.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out_path, index=False)
        print(f"\n[P2 by-decade context table] -> {out_path.name}")
        # Print inline
        print(f"\n{'Decade':<8} {'n_fires':>8} {'n_valid':>8} {'stop_out':>9} "
              f"{'liftoff':>9} {'med_fwd20d':>12}")
        print("-" * 60)
        for r in rows:
            so = f"{r['stop_out_rate']:.3f}" if r["stop_out_rate"] is not None else "  N/A"
            lo = f"{r['liftoff_rate']:.3f}" if r["liftoff_rate"] is not None else "  N/A"
            mf = f"{r['median_fwd_ret_20d']:.3f}" if r["median_fwd_ret_20d"] is not None else "  N/A"
            print(f"{r['decade']:<8} {r['n_fires']:>8} {r['n_valid']:>8} "
                  f"{so:>9} {lo:>9} {mf:>12}")


def _save_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> saved {path.name}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="S7 Phase-0 analysis")
    ap.add_argument("--panel", default="p1", choices=["p1", "p2", "both"],
                    help="Which panel results to analyze")
    ap.add_argument("--holdout", action="store_true",
                    help="WARNING: unlock holdout set (2025-01+). Do NOT set until "
                         "dev tables and tier definitions are written into REPORT.md.")
    ap.add_argument("--n-draws", type=int, default=N_BOOTSTRAP)
    ap.add_argument("--results-dir", default=str(HERE / "results"),
                    help="Directory containing fires_with_metrics_*.parquet")
    args = ap.parse_args(argv)

    results_dir = Path(args.results_dir)

    panels = []
    if args.panel in ("p1", "both"):
        panels.append("P1")
    if args.panel in ("p2", "both"):
        panels.append("P2")

    for panel in panels:
        try:
            df = _load_fires(panel.lower(), results_dir, args.holdout)
        except FileNotFoundError as e:
            print(f"SKIP {panel}: {e}")
            continue
        analyze_panel(df, panel, results_dir, n_draws=args.n_draws)

    print("\n[analyze.py] Done.")


if __name__ == "__main__":
    main()
