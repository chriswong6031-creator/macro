"""NFP Revision-Direction Backtest — Track R (MRI-R37, W11-D).

Runs the frozen walk-forward for the NFP first→third revision-direction model
per PREREG_NFP_REVISION_V1.md (frozen before this run).

Writes:
  research/release_forecast/results/backtest_nfp_revision_v1.json
  research/release_forecast/RESULTS_NFP_REVISION_V1.md

Uses the TRUE first→third target when data/fred_vintage/payems_all_vintages.parquet
is available (FRED_API_KEY needed; see scripts/collect_payems_vintages.py).
Falls back to first_to_cumulative_fallback target if not.

Usage:
  python research/release_forecast/backtest_nfp_revision_v1.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from engine.release_revision_model import (
    MIN_TRAIN_OBS,
    COVID_MONTHS,
    STRENGTH_THRESHOLD,
    build_revision_features,
    build_revision_target_df,
    evaluate_hit_rate,
    load_multi_vintage,
    run_revision_walk_forward,
    _wilson,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
_ROOT = _REPO


# ---------------------------------------------------------------------------
# Era classification
# ---------------------------------------------------------------------------

def _era(period: pd.Timestamp) -> str:
    y, m = period.year, period.month
    if (y, m) in COVID_MONTHS:
        return "covid"
    if y < 2010:
        return "pre_2010"
    if y < 2021:
        if y == 2020 and m > 6:
            return "2020_recovery"
        return "2010_2020"
    return "2021_plus"


# ---------------------------------------------------------------------------
# Era-split hit-rate computation
# ---------------------------------------------------------------------------

def _era_hit_rate(subset: list[dict]) -> dict[str, Any]:
    """Compute hit-rate stats for a subset of walk-forward results."""
    # Only directional predictions (predicted_sign != 0) count in hit-rate
    directional = [r for r in subset if r.get("predicted_sign", 0) != 0]
    n_total = len(subset)
    n_dir = len(directional)
    hits = sum(1 for r in directional if r["predicted_sign"] == r["actual_target"])
    hr = hits / n_dir if n_dir > 0 else None
    wilson = _wilson(hits, n_dir) if n_dir > 0 else None

    # Majority baseline (over ALL steps, not just directional)
    all_non_zero = [r for r in subset if r.get("actual_target", 0) != 0]
    n_up = sum(1 for r in all_non_zero if r["actual_target"] > 0)
    n_down = sum(1 for r in all_non_zero if r["actual_target"] < 0)
    majority_base = max(n_up, n_down) / len(all_non_zero) if all_non_zero else None

    # Sign-of-negative-fp-surprise baseline
    fp_dir = [r for r in subset if r.get("sign_neg_fp_baseline", 0) != 0]
    fp_hits = sum(1 for r in fp_dir if r["sign_neg_fp_baseline"] == r["actual_target"])
    fp_hr = fp_hits / len(fp_dir) if fp_dir else None

    return {
        "n_total": n_total,
        "n_directional": n_dir,
        "n_hits": hits,
        "hit_rate": round(hr, 4) if hr is not None else None,
        "wilson_95_ci": wilson,
        "majority_base_rate": round(majority_base, 4) if majority_base is not None else None,
        "n_up_actual": n_up,
        "n_down_actual": n_down,
        "fp_baseline_hr": round(fp_hr, 4) if fp_hr is not None else None,
        "fp_baseline_n_dir": len(fp_dir),
    }


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

def run_backtest() -> dict[str, Any]:
    """Run the Track R walk-forward backtest."""
    # Load multi-vintage PAYEMS store
    mv_df, basis = load_multi_vintage(_ROOT)
    print(f"[trackR] basis: {basis}")
    print(f"[trackR] mv_df shape: {mv_df.shape}")

    if mv_df.empty:
        print("[trackR] ERROR: no PAYEMS vintage data found")
        sys.exit(1)

    # Load initial-print vintages for ICSA features
    iv_path = _ROOT / "data" / "fred_vintage" / "vintages.parquet"
    if iv_path.exists():
        init_vintages = pd.read_parquet(iv_path)
        for col in ("period", "realtime_start", "realtime_end"):
            if col in init_vintages.columns:
                init_vintages[col] = pd.to_datetime(init_vintages[col], errors="coerce")
        print(f"[trackR] init_vintages loaded: {init_vintages.shape}")
    else:
        init_vintages = None
        print("[trackR] WARNING: init_vintages not found — ICSA feature will be null")

    # Build revision target DataFrame
    target_df = build_revision_target_df(mv_df, basis)
    print(f"[trackR] target_df shape: {target_df.shape}")
    print(f"[trackR] target distribution:\n{target_df['target'].value_counts().to_dict()}")

    # Build records
    records = []
    for _, row in target_df.iterrows():
        period = pd.Timestamp(row["period"])
        decision_date = pd.Timestamp(row["decision_date"])
        features = build_revision_features(
            period=period,
            decision_date=decision_date,
            first_print_mom=float(row["first_print_mom"]),
            mv_df=mv_df,
            init_vintages=init_vintages,
        )
        # label_observable_date = third_release_date: the date the training
        # label (third-print MoM direction) first became visible in ALFRED.
        # Passed to run_revision_walk_forward to enforce PIT compliance and
        # eliminate training-label look-ahead (the bug that voided the prior run).
        label_obs = row.get("third_release_date")
        rec = {
            "period": period,
            "first_release_date": pd.Timestamp(row["first_release_date"]),
            "decision_date": decision_date,
            "label_observable_date": (
                pd.Timestamp(label_obs) if label_obs is not None and pd.notna(label_obs)
                else None
            ),
            "first_print_mom": float(row["first_print_mom"]),
            "third_print_mom": float(row["third_print_mom"]),
            "revision": float(row["revision"]),
            "target": int(row["target"]),
            **features,
        }
        records.append(rec)

    records.sort(key=lambda r: r["first_release_date"])
    print(f"[trackR] built {len(records)} records")

    # Run walk-forward
    wf_results = run_revision_walk_forward(records, min_obs=MIN_TRAIN_OBS)
    print(f"[trackR] walk-forward steps: {len(wf_results)}")

    # Overall kill-rule evaluation (non-covid, non-zero-target)
    full_stats = evaluate_hit_rate(wf_results, exclude_covid=True, exclude_zero_target=True)
    print(f"[trackR] full stats: {full_stats}")

    # Era-split breakdown
    era_subsets: dict[str, list[dict]] = {
        "pre_2010": [],
        "2010_2020": [],
        "covid": [],
        "2020_recovery": [],
        "2021_plus": [],
    }
    for r in wf_results:
        if r.get("actual_target", 0) == 0:
            continue  # skip zero-revision steps
        era = _era(pd.Timestamp(r["period"]))
        era_subsets[era].append(r)

    era_results: dict[str, Any] = {}
    for era_name, subset in era_subsets.items():
        era_results[era_name] = _era_hit_rate(subset)

    # Full non-covid window (for kill rule)
    full_non_covid = [
        r for r in wf_results
        if not r.get("is_covid", False) and r.get("actual_target", 0) != 0
    ]
    era_results["full_non_covid"] = _era_hit_rate(full_non_covid)

    # Kill rule verdict
    kill_triggered = full_stats["kill_triggered"]
    verdict = "kill" if kill_triggered else "active"
    print(f"[trackR] Kill rule: Wilson_LB={full_stats.get('wilson_ci', [None])[0] if full_stats.get('wilson_ci') else None} "
          f"vs majority_base_rate={full_stats.get('majority_base_rate')} -> {verdict}")

    # Build feature presence summary
    feature_names = [
        "fp_surprise_vs_AR1", "sin_month", "cos_month", "icsa_4m_survey_week_change"
    ]
    feature_presence = {}
    for fn in feature_names:
        present = sum(1 for r in records if r.get(fn) is not None)
        feature_presence[fn] = {"n_present": present, "pct_present": round(present / len(records), 3)}

    result = {
        "run_date": str(date.today()),
        "spec": "research/release_forecast/PREREG_NFP_REVISION_V1.md",
        "basis": basis,
        "n_records": len(records),
        "n_wf_steps": len(wf_results),
        "min_train_obs": MIN_TRAIN_OBS,
        "strength_threshold": STRENGTH_THRESHOLD,
        "kill_rule": {
            "verdict": verdict,
            "kill_triggered": kill_triggered,
            "wilson_lb": (
                full_stats["wilson_ci"][0] if full_stats.get("wilson_ci") else None
            ),
            "majority_base_rate": full_stats.get("majority_base_rate"),
            "hit_rate": full_stats.get("hit_rate"),
            "n_directional": full_stats.get("n"),
        },
        "era_results": era_results,
        "feature_presence": feature_presence,
    }

    # Save JSON
    json_path = _RESULTS_DIR / "backtest_nfp_revision_v1.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[trackR] wrote {json_path}")

    return result


def write_results_md(result: dict[str, Any]) -> None:
    """Write RESULTS_NFP_REVISION_V1.md."""
    basis = result["basis"]
    basis_label = (
        "TRUE first→third revision (ALFRED output_type=2)"
        if basis == "first_to_third"
        else "FALLBACK first→cumulative revision (output_type=4)"
    )
    kill = result["kill_rule"]
    era = result["era_results"]

    def _fmt_ci(ci):
        if ci is None:
            return "N/A"
        return f"[{ci[0]:.3f}, {ci[1]:.3f}]"

    def _fmt_hr(era_name: str) -> str:
        d = era.get(era_name, {})
        hr = d.get("hit_rate")
        ci = d.get("wilson_95_ci")
        n = d.get("n_directional", 0)
        mbr = d.get("majority_base_rate")
        return (
            f"HR={hr:.3f} (n={n})" if hr is not None else "N/A (n=0)"
        ) + f" Wilson95={_fmt_ci(ci)}" + (f" maj_base={mbr:.3f}" if mbr is not None else "")

    lines = [
        "# Backtest Results V1 — NFP Revision-Direction Model (Track R)",
        "",
        f"**Run date:** {result['run_date']}",
        f"**Spec:** research/release_forecast/PREREG_NFP_REVISION_V1.md (frozen before run)",
        f"**Target basis:** {basis_label}",
        f"**Algorithm:** Ridge(λ=1.0, numpy closed-form), expanding window, MIN_TRAIN_OBS={result['min_train_obs']}",
        f"**Kill rule:** Walk-forward hit-rate Wilson LB must exceed majority-class base rate (full non-covid window); non-directional steps (|y_hat| < {result['strength_threshold']}) excluded",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| Records available | {result['n_records']} |",
        f"| Walk-forward steps | {result['n_wf_steps']} |",
        f"| Target basis | {basis} |",
        f"| Kill verdict | **{kill['verdict'].upper()}** |",
        f"| Hit rate (full non-covid) | {round(kill['hit_rate'], 3) if kill['hit_rate'] is not None else 'N/A'} |",
        f"| Wilson 95% LB | {round(kill['wilson_lb'], 3) if kill['wilson_lb'] is not None else 'N/A'} |",
        f"| Majority base rate | {round(kill['majority_base_rate'], 3) if kill['majority_base_rate'] is not None else 'N/A'} |",
        f"| n directional steps | {kill['n_directional']} |",
        "",
        "---",
        "",
        "## Kill Rule Detail",
        "",
        (
            f"**Kill TRIGGERED** (model suppressed — lean='none'):"
            if kill["kill_triggered"] else
            "**Kill NOT triggered** — model active."
        ),
        "",
        f"- Wilson LB: {round(kill['wilson_lb'], 4) if kill['wilson_lb'] is not None else 'N/A'}",
        f"- Majority base rate: {round(kill['majority_base_rate'], 4) if kill['majority_base_rate'] is not None else 'N/A'}",
        f"- Kill condition (Wilson LB <= majority base rate): {kill['kill_triggered']}",
        "",
        "---",
        "",
        "## Era-Split Results",
        "",
        "Directional only (steps where |y_hat| >= strength_threshold); majority base rate = max(n_up, n_down) / n_total in each era.",
        "",
        "| Era | n_dir | n_hits | Hit Rate | Wilson 95% CI | Majority Base Rate | FP-Baseline HR |",
        "|-----|-------|--------|----------|---------------|--------------------|----------------|",
    ]
    for era_name in ["pre_2010", "2010_2020", "covid", "2020_recovery", "2021_plus", "full_non_covid"]:
        d = era.get(era_name, {})
        n_dir = d.get("n_directional", 0)
        n_hits = d.get("n_hits", 0)
        hr = d.get("hit_rate")
        ci = d.get("wilson_95_ci")
        mbr = d.get("majority_base_rate")
        fp_hr = d.get("fp_baseline_hr")
        lines.append(
            f"| {era_name} | {n_dir} | {n_hits} | "
            f"{'N/A' if hr is None else f'{hr:.3f}'} | "
            f"{'N/A' if ci is None else _fmt_ci(ci)} | "
            f"{'N/A' if mbr is None else f'{mbr:.3f}'} | "
            f"{'N/A' if fp_hr is None else f'{fp_hr:.3f}'} |"
        )

    # Pre-2010 note: with data starting from ~1997, the model accumulates 60 training
    # rows by ~2002 and therefore CAN produce directional calls before 2010.
    pre2010_dir = era.get("pre_2010", {}).get("n_directional", 0)
    pre2010_note = (
        f"Pre-2010 directional n={pre2010_dir} (model has ≥60 training rows available"
        " before 2010 given data starting ~1997)."
        if pre2010_dir > 0
        else
        "Pre-2010 directional n=0 (model needs 60 training rows before the first prediction;  "
        "check whether data starts late enough to exceed that threshold before 2010)."
    )
    lines += [
        "",
        f"**Note:** {pre2010_note}",
        f"COVID rows (2020-03..2020-06) are excluded from the kill-rule evaluation per PREREG §3.2.",
        f"n_directional in the kill-rule evaluation ({result['kill_rule']['n_directional']}) "
        f"equals the full_non_covid directional count in the era table — any difference between "
        f"this and prior runs reflects the PIT-compliance fix (look-ahead-corrected training windows "
        f"can raise or lower the directional call rate at certain folds).",
        "",
        "---",
        "",
        "## Feature Presence",
        "",
        "| Feature | n_present | pct_present |",
        "|---------|-----------|-------------|",
    ]
    for fn, stats in result.get("feature_presence", {}).items():
        lines.append(
            f"| {fn} | {stats['n_present']} | {stats['pct_present']:.1%} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Provenance",
        "",
        f"- **Basis:** {basis}",
        f"- **Multi-vintage store:** data/fred_vintage/payems_all_vintages.parquet (output_type=2)",
        f"- **Fallback store:** data/fred_vintage/vintages.parquet (output_type=4)",
        f"- **display_only:** true",
        f"- **authority:** false",
        "",
        "---",
        "",
        "## Interpretation",
        "",
        (
            "The kill rule is TRIGGERED. Per PREREG_NFP_REVISION_V1.md §4: "
            "walk-forward hit-rate Wilson LB does not exceed the majority-class base rate "
            "in the full non-covid window. The `revision_lean` field will display 'none' "
            "(suppressed). Attempt #1 of 2 is exhausted under this kill condition. "
            "A second attempt may be registered under program-level adjudication "
            "(per PREREG_NFP_REVISION_V1.md §12.3)."
            if kill["kill_triggered"] else
            "The kill rule is NOT triggered. The model is ACTIVE: `revision_lean` will "
            "display directional calls when |y_hat| >= strength_threshold."
        ),
        "",
        "The LEVEL-bias annotation (expansions +216k / contractions -262k cumulative level "
        "revision) is a SEPARATE display field — descriptive, no model, always displayed "
        "regardless of kill outcome. MoM-change bias is NOT significant and must not be implied.",
    ]

    md_path = Path(__file__).resolve().parent / "RESULTS_NFP_REVISION_V1.md"
    md_path.write_text("\n".join(lines) + "\n")
    print(f"[trackR] wrote {md_path}")


if __name__ == "__main__":
    result = run_backtest()
    write_results_md(result)
    print("\n[trackR] backtest complete.")
    print(f"  Kill verdict: {result['kill_rule']['verdict'].upper()}")
    print(f"  Basis: {result['basis']}")
    print(f"  Hit rate: {result['kill_rule']['hit_rate']}")
    print(f"  Wilson LB: {result['kill_rule']['wilson_lb']}")
    print(f"  Majority base rate: {result['kill_rule']['majority_base_rate']}")
