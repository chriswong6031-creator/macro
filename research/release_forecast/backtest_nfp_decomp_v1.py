"""NFP Decomposition + AHE/AWH Backtest (PR-H).

Runs the frozen walk-forward for:
  1. ahe_mom (AHE MoM %, ridge model, CES0500000003)
  2. awh_level (avg weekly hours, persistence-only, AWHAETP)
  3. NFP decomposition sanity: components-sum-to-point, BD prior 12-month profile

Writes:
  research/release_forecast/results/backtest_nfp_decomp_v1.json
  research/release_forecast/results/backtest_nfp_decomp_v1.md

Per PREREG_NFP_DECOMP_V1.md (frozen before this run).

Usage:
  python research/release_forecast/backtest_nfp_decomp_v1.py
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

from engine.release_forecast import (
    MIN_QUANTILE_OBS,
    MIN_TRAIN_OBS,
    run_walk_forward_full,
    _wf_nfp_full,
    load_vintages,
    knowable_series,
)
from engine.release_components_nfp import compute_bd_prior_12month_profile

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Era classification (same law as PREREG_V1.md §6.1 + PREREG_NFP_DECOMP_V1.md §3.8)
# ---------------------------------------------------------------------------

def _era(period: pd.Timestamp) -> str:
    if period.year < 2010:
        return "pre_2010"
    y, m = period.year, period.month
    if y == 2020:
        if m <= 2:
            return "2010_2020"
        elif m <= 6:
            return "covid"
        else:
            return "2020_recovery"
    if y < 2021:
        return "2010_2020"
    return "2021_plus"


# ---------------------------------------------------------------------------
# Metric helpers (reuse pattern from backtest_release_forecast.py)
# ---------------------------------------------------------------------------

def _mae(errors):
    if not errors:
        return None
    return float(np.mean(np.abs(errors)))


def _rmse(errors):
    if not errors:
        return None
    return float(np.sqrt(np.mean(np.array(errors) ** 2)))


def _wilson(k: int, n: int, z: float = 1.96):
    if not n:
        return None
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def _compute_metrics(rows: list[dict], errors_accum: np.ndarray) -> dict:
    if not rows:
        return {"n": 0, "mae_model": None, "rmse_model": None,
                "mae_naive": None, "rmse_naive": None,
                "mae_trailing3m": None, "rmse_trailing3m": None,
                "coverage_p10_p90": None,
                "skew_hit_rate": None, "skew_wilson_ci": None, "skew_n": 0}

    actuals = [r["actual"] for r in rows]
    preds = [r["predicted"] for r in rows]
    naive_preds = [r["baseline_naive"] for r in rows]
    t3m_preds = [r["baseline_trailing3m"] for r in rows]

    model_errors = [a - p for a, p in zip(actuals, preds)]
    naive_errors = [a - n for a, n in zip(actuals, naive_preds)]
    t3m_errors = [a - t for a, t in zip(actuals, t3m_preds)]

    # Coverage: use result_pos to slice errors_accum for PIT quantiles
    p10s, p90s = [], []
    for r in rows:
        pos = r.get("result_pos", 0)
        past_errors = errors_accum[:pos]
        if len(past_errors) >= MIN_QUANTILE_OBS:
            p10 = r["predicted"] + float(np.quantile(past_errors, 0.10))
            p90 = r["predicted"] + float(np.quantile(past_errors, 0.90))
        else:
            p10, p90 = None, None
        p10s.append(p10)
        p90s.append(p90)

    pairs = [(a, lo, hi) for a, lo, hi in zip(actuals, p10s, p90s)
             if lo is not None and hi is not None]
    cov = round(sum(1 for a, lo, hi in pairs if lo <= a <= hi) / len(pairs), 4) if pairs else None

    # Skew hit-rate: sign(model - naive) == sign(actual - naive)
    valid = [(p, a, n) for p, a, n in zip(preds, actuals, naive_preds)
             if (p - n) != 0 and (a - n) != 0]
    skew_hr, skew_ci, skew_n = None, None, 0
    if valid:
        hits = sum(1 for p, a, n in valid if math.copysign(1, p - n) == math.copysign(1, a - n))
        skew_n = len(valid)
        skew_hr = round(hits / skew_n, 4)
        skew_ci = _wilson(hits, skew_n)

    return {
        "n": len(rows),
        "mae_model": round(_mae(model_errors), 4) if _mae(model_errors) is not None else None,
        "rmse_model": round(_rmse(model_errors), 4) if _rmse(model_errors) is not None else None,
        "mae_naive": round(_mae(naive_errors), 4) if _mae(naive_errors) is not None else None,
        "rmse_naive": round(_rmse(naive_errors), 4) if _rmse(naive_errors) is not None else None,
        "mae_trailing3m": round(_mae(t3m_errors), 4) if _mae(t3m_errors) is not None else None,
        "rmse_trailing3m": round(_rmse(t3m_errors), 4) if _rmse(t3m_errors) is not None else None,
        "coverage_p10_p90": cov,
        "skew_hit_rate": skew_hr,
        "skew_wilson_ci": skew_ci,
        "skew_n": skew_n,
    }


def _check_kill_rule(metrics_full: dict, metrics_2021: dict) -> bool:
    mae_m_full = metrics_full.get("mae_model")
    mae_n_full = metrics_full.get("mae_naive")
    mae_m_2021 = metrics_2021.get("mae_model")
    mae_n_2021 = metrics_2021.get("mae_naive")
    if any(v is None for v in [mae_m_full, mae_n_full, mae_m_2021, mae_n_2021]):
        return False
    return (mae_m_full >= mae_n_full) and (mae_m_2021 >= mae_n_2021)


# ---------------------------------------------------------------------------
# Run backtest
# ---------------------------------------------------------------------------

def run_backtest() -> dict:
    print("=== NFP Decomposition + AHE/AWH Backtest (PR-H) ===\n")
    root = _REPO
    summary: dict[str, Any] = {}

    # -----------------------------------------------------------------------
    # 1. AHE Mom backtest
    # -----------------------------------------------------------------------
    print("Running walk-forward: ahe ...")
    wf_ahe = run_walk_forward_full("ahe", root)
    results_ahe = wf_ahe["results"]
    print(f"  {len(results_ahe)} predictions")

    if results_ahe:
        errors_ahe = np.array([r["actual"] - r["predicted"] for r in results_ahe])

        def get_period(r):
            p = r.get("period")
            return pd.Timestamp(p) if p is not None else None

        rows_all = [r for r in results_ahe if get_period(r) is not None]
        rows_pre2010 = [r for r in rows_all if _era(get_period(r)) == "pre_2010"]
        rows_2010_2020 = [r for r in rows_all if _era(get_period(r)) == "2010_2020"]
        rows_covid = [r for r in rows_all if _era(get_period(r)) == "covid"]
        rows_2020_recovery = [r for r in rows_all if _era(get_period(r)) == "2020_recovery"]
        rows_2021 = [r for r in rows_all if _era(get_period(r)) == "2021_plus"]

        m_full = _compute_metrics(rows_all, errors_ahe)
        m_pre2010 = _compute_metrics(rows_pre2010, errors_ahe)
        m_2010_2020 = _compute_metrics(rows_2010_2020, errors_ahe)
        m_covid = _compute_metrics(rows_covid, errors_ahe)
        m_2020_recovery = _compute_metrics(rows_2020_recovery, errors_ahe)
        m_2021 = _compute_metrics(rows_2021, errors_ahe)

        killed = _check_kill_rule(m_full, m_2021)
        status = "benchmark_only" if killed else "active"

        print(f"  Kill rule: {'TRIGGERED -> benchmark_only' if killed else 'NOT triggered -> active'}")
        print(f"  Full: MAE model={m_full.get('mae_model')} vs naive={m_full.get('mae_naive')}")
        print(f"  2021+: MAE model={m_2021.get('mae_model')} vs naive={m_2021.get('mae_naive')}")
        print()

        summary["ahe"] = {
            "status": status,
            "benchmark_only": killed,
            "n_predictions": len(results_ahe),
            "era_metrics": {
                "full": m_full,
                "pre_2010": m_pre2010,
                "2010_2020": m_2010_2020,
                "covid_months_2020_03_06": m_covid,
                "2020_recovery": m_2020_recovery,
                "2021_plus": m_2021,
            },
        }
    else:
        print("  No AHE walk-forward results (insufficient data).")
        summary["ahe"] = {
            "status": "no_data",
            "benchmark_only": False,
            "n_predictions": 0,
            "era_metrics": {},
        }

    # -----------------------------------------------------------------------
    # 2. AWH persistence check
    # -----------------------------------------------------------------------
    print("Running persistence check: awh ...")
    wf_awh = run_walk_forward_full("awh", root)
    results_awh = wf_awh["results"]
    print(f"  {len(results_awh)} persistence steps")

    if results_awh:
        errors_awh = np.array([r["actual"] - r["predicted"] for r in results_awh])
        # AWH: model IS naive. Report MAE for context only.
        mae_persist = round(float(np.mean(np.abs(errors_awh))), 4)
        rmse_persist = round(float(np.sqrt(np.mean(errors_awh ** 2))), 4)
        print(f"  AWH persistence MAE={mae_persist} (hours/wk), RMSE={rmse_persist}")

        # Quantile coverage (p10-p90 from residual history)
        p10s, p90s = [], []
        for r in results_awh:
            pos = r.get("result_pos", 0)
            past = errors_awh[:pos]
            if len(past) >= MIN_QUANTILE_OBS:
                p10s.append(r["predicted"] + float(np.quantile(past, 0.10)))
                p90s.append(r["predicted"] + float(np.quantile(past, 0.90)))
            else:
                p10s.append(None)
                p90s.append(None)

        pairs = [(r["actual"], lo, hi) for r, lo, hi in zip(results_awh, p10s, p90s)
                 if lo is not None and hi is not None]
        cov = round(sum(1 for a, lo, hi in pairs if lo <= a <= hi) / len(pairs), 4) if pairs else None
        print(f"  AWH p10-p90 coverage={cov}")
        print()

        summary["awh"] = {
            "status": "persistence_only",
            "persistence_only": True,
            "n_steps": len(results_awh),
            "mae_persistence": mae_persist,
            "rmse_persistence": rmse_persist,
            "coverage_p10_p90": cov,
        }
    else:
        print("  No AWH results (insufficient data).")
        summary["awh"] = {"status": "no_data", "n_steps": 0}

    # -----------------------------------------------------------------------
    # 3. NFP decomposition sanity
    # -----------------------------------------------------------------------
    print("Running NFP decomposition sanity (BD prior 12-month profile) ...")
    try:
        vintages = load_vintages(_REPO)
        nfp_full = _wf_nfp_full(vintages, _REPO)
        nfp_results = nfp_full["results"]
        print(f"  {len(nfp_results)} NFP walk-forward steps for BD prior analysis")

        # Build BD prior 12-month profile using full walk-forward history
        # (backtest uses all data; live projection would be PIT-restricted)
        current_year = 2026  # backtest run year
        bd_profile = compute_bd_prior_12month_profile(
            nfp_results,
            as_of_year=current_year,
            lookback_years=5,
        )

        # Also compute 2023-view profile to demonstrate Amendment A COVID fix:
        # as_of_year=2023 → cutoff=2018, window includes 2020 COVID months.
        # Without COVID exclusion, April inherits 2020-04 residual (~-19956k → ~-4000k prior).
        # With Amendment A, 2020-03..06 are excluded → April uses only 2019, 2021, 2022, 2023.
        bd_profile_2023 = compute_bd_prior_12month_profile(
            nfp_results,
            as_of_year=2023,
            lookback_years=5,
        )

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        print("\n  Birth-Death Prior 12-Month Profile (trailing 5yr mean of actual-predicted, k jobs):")
        print(f"  {'Month':<6} {'Prior (k)':>10}")
        print(f"  {'------':<6} {'----------':>10}")
        for m_idx in range(1, 13):
            val = bd_profile.get(m_idx)
            val_str = f"{val:+.1f}" if val is not None else "null"
            print(f"  {month_names[m_idx - 1]:<6} {val_str:>10}")
        print()
        print("  2023-view BD profile (demonstrates Amendment A COVID fix):")
        for m_idx in range(1, 13):
            val = bd_profile_2023.get(m_idx)
            val_str = f"{val:+.1f}" if val is not None else "null"
            print(f"  {month_names[m_idx - 1]:<6} {val_str:>10}")
        print()

        # Decomposition components-sum-to-point sanity: sample a few steps
        # Using the NFP walk-forward results at a recent step
        from engine.release_components_nfp import build_nfp_components
        # Find last 5 steps with data for spot-check
        decomp_spot_checks = []
        n_spot = min(5, len(nfp_results))
        for r in nfp_results[-n_spot:]:
            model_point = r.get("predicted")
            period_ts = r.get("period")
            if model_point is None or period_ts is None:
                continue
            try:
                period_ts = pd.Timestamp(period_ts)
                ref_m = date(period_ts.year, period_ts.month, 1)
                asof_d = date(period_ts.year, period_ts.month, 1)  # approximate
                # Use all prior WF results for BD prior
                prior_results = [
                    {
                        "actual": rr.get("actual"),
                        "predicted": rr.get("predicted"),
                        "period": rr.get("period"),
                    }
                    for rr in nfp_results
                    if rr.get("result_pos", 9999) < r.get("result_pos", 0)
                ]
                comps = build_nfp_components(
                    model_point, asof_d, ref_m, vintages, prior_results,
                    knowable_series_fn=knowable_series,
                )
                # Check sum
                parts = [comps.get("private_trend"), comps.get("government_trend"),
                         comps.get("birth_death_residual_prior")]
                parts_present = [p for p in parts if p is not None]
                parts_sum = sum(parts_present) if parts_present else None
                residual = comps.get("residual")
                recon = None
                if parts_sum is not None:
                    recon = parts_sum + (residual or 0.0)
                decomp_spot_checks.append({
                    "period": str(period_ts.date()),
                    "model_point": round(model_point, 2),
                    "private_trend": comps.get("private_trend"),
                    "government_trend": comps.get("government_trend"),
                    "bd_prior": comps.get("birth_death_residual_prior"),
                    "residual": residual,
                    "parts_sum_plus_residual": round(recon, 2) if recon is not None else None,
                    "reconstruction_error": round(abs(recon - model_point), 4) if recon is not None else None,
                    "absent_parts": comps.get("absent_parts", []),
                })
            except Exception as ex:
                decomp_spot_checks.append({"period": str(period_ts), "error": str(ex)})

        print("  Decomposition spot-checks (last 5 NFP steps):")
        for sc in decomp_spot_checks:
            print(f"    period={sc.get('period')}: model={sc.get('model_point')}, "
                  f"private={sc.get('private_trend')}, govt={sc.get('government_trend')}, "
                  f"bd_prior={sc.get('bd_prior')}, residual={sc.get('residual')}, "
                  f"recon_err={sc.get('reconstruction_error')}, "
                  f"absent={sc.get('absent_parts')}")
        print()

        summary["nfp_decomp"] = {
            "bd_prior_12month_profile": {str(m): bd_profile[m] for m in range(1, 13)},
            "bd_prior_12month_profile_2023_view": {str(m): bd_profile_2023[m] for m in range(1, 13)},
            "decomp_spot_checks": decomp_spot_checks,
            "n_nfp_wf_steps": len(nfp_results),
        }

    except Exception as e:
        print(f"  NFP decomposition sanity failed: {e}")
        import traceback
        traceback.print_exc()
        summary["nfp_decomp"] = {"error": str(e)}

    return summary


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _fmt_num(v, digits=4):
    if v is None:
        return "null"
    return f"{v:.{digits}f}"


def generate_md(summary: dict) -> str:
    lines = []
    lines.append("# NFP Decomposition + AHE/AWH Backtest (PR-H)")
    lines.append("")
    lines.append("**Run date:** 2026-07-07")
    lines.append("**Spec:** research/release_forecast/PREREG_NFP_DECOMP_V1.md (frozen before run)")
    lines.append("")

    # AHE summary
    lines.append("## AHE MoM % — Ridge Model (Attempt 1)")
    lines.append("")
    ahe = summary.get("ahe", {})
    lines.append(f"**Status:** {ahe.get('status', 'unknown')}")
    lines.append(f"**Total predictions:** {ahe.get('n_predictions', 0)}")
    lines.append(f"**Kill rule:** {'TRIGGERED -> benchmark_only' if ahe.get('benchmark_only') else 'NOT triggered -> active'}")
    lines.append("")

    era_metrics = ahe.get("era_metrics", {})
    if era_metrics:
        lines.append("### Era-Split Metrics")
        lines.append("")
        lines.append("| Era | n | MAE Model | MAE Naive | MAE Trail3m | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |")
        lines.append("|-----|---|-----------|-----------|-------------|------------|------------|-------------|---------|---------------|--------|")
        eras = ["full", "pre_2010", "2010_2020", "covid_months_2020_03_06", "2020_recovery", "2021_plus"]
        era_labels = {
            "full": "Full",
            "pre_2010": "pre-2010",
            "2010_2020": "2010-2020-02",
            "covid_months_2020_03_06": "COVID 2020-03..06",
            "2020_recovery": "2020-07..12",
            "2021_plus": "2021+",
        }
        for era in eras:
            m = era_metrics.get(era, {})
            if not m or m.get("n", 0) == 0:
                continue
            ci = m.get("skew_wilson_ci")
            ci_str = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "null"
            cov = m.get("coverage_p10_p90")
            cov_str = f"{cov*100:.1f}%" if cov is not None else "null"
            lines.append(
                f"| {era_labels.get(era, era)} "
                f"| {m.get('n', 0)} "
                f"| {_fmt_num(m.get('mae_model'))} "
                f"| {_fmt_num(m.get('mae_naive'))} "
                f"| {_fmt_num(m.get('mae_trailing3m'))} "
                f"| {_fmt_num(m.get('rmse_model'))} "
                f"| {_fmt_num(m.get('rmse_naive'))} "
                f"| {cov_str} "
                f"| {_fmt_num(m.get('skew_hit_rate'), 3)} "
                f"| {ci_str} "
                f"| {m.get('skew_n', 0)} |"
            )
        lines.append("")
        m_full = era_metrics.get("full", {})
        m_2021 = era_metrics.get("2021_plus", {})
        lines.append("### Kill Rule Detail")
        lines.append(f"- Full window: MAE model={_fmt_num(m_full.get('mae_model'))} vs naive={_fmt_num(m_full.get('mae_naive'))}")
        lines.append(f"- 2021+ slice: MAE model={_fmt_num(m_2021.get('mae_model'))} vs naive={_fmt_num(m_2021.get('mae_naive'))}")
        lines.append(f"- Kill triggered: {'YES -> benchmark_only' if ahe.get('benchmark_only') else 'NO -> active'}")
        lines.append("")

    # AWH summary
    lines.append("---")
    lines.append("## AWH Level — Persistence-Only (No Skill Claim)")
    lines.append("")
    awh = summary.get("awh", {})
    lines.append(f"**Status:** {awh.get('status', 'unknown')}")
    lines.append(f"**n steps:** {awh.get('n_steps', 0)}")
    lines.append(f"**MAE (persistence):** {_fmt_num(awh.get('mae_persistence'))} hrs/wk")
    lines.append(f"**RMSE (persistence):** {_fmt_num(awh.get('rmse_persistence'))} hrs/wk")
    lines.append(f"**Coverage p10-p90:** {awh.get('coverage_p10_p90')}")
    lines.append("")
    lines.append("*Model IS the naive baseline. No skill claim. Published as labor-demand context.*")
    lines.append("")

    # NFP decomposition sanity
    lines.append("---")
    lines.append("## NFP Decomposition Sanity")
    lines.append("")
    nd = summary.get("nfp_decomp", {})
    if "error" in nd:
        lines.append(f"**Error:** {nd['error']}")
    else:
        lines.append(f"**NFP walk-forward steps used:** {nd.get('n_nfp_wf_steps', 0)}")
        lines.append("")
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        lines.append("### Birth-Death Prior 12-Month Profile — 2026 View (trailing 5yr mean of actual−predicted, k jobs)")
        lines.append("")
        lines.append("*Window: 2021-2026. COVID window 2020-03..06 is outside this cutoff (excluded by year, not Amendment A).*")
        lines.append("")
        lines.append("| Month | BD Prior (k jobs) |")
        lines.append("|-------|-------------------|")
        profile = nd.get("bd_prior_12month_profile", {})
        for m_idx in range(1, 13):
            val = profile.get(str(m_idx))
            val_str = f"{val:+.1f}" if val is not None else "null"
            lines.append(f"| {month_names[m_idx - 1]} | {val_str} |")
        lines.append("")

        lines.append("### Birth-Death Prior 12-Month Profile — 2023 View (demonstrates Amendment A COVID fix)")
        lines.append("")
        lines.append(
            "*Window: 2018-2023. Without Amendment A, April would inherit the 2020-04 residual "
            "(~-19,956k), producing ~-4,000k prior. With Amendment A (COVID exclusion 2020-03..06), "
            "April uses only 2018, 2019, 2021, 2022, 2023 residuals — the large negative artifact is removed.*"
        )
        lines.append("")
        lines.append("| Month | BD Prior (k jobs) |")
        lines.append("|-------|-------------------|")
        profile_2023 = nd.get("bd_prior_12month_profile_2023_view", {})
        for m_idx in range(1, 13):
            val = profile_2023.get(str(m_idx))
            val_str = f"{val:+.1f}" if val is not None else "null"
            lines.append(f"| {month_names[m_idx - 1]} | {val_str} |")
        lines.append("")
        lines.append("### Decomposition Spot-Checks (last 5 NFP walk-forward steps)")
        lines.append("")
        lines.append("| Period | Model | Private | Govt | BD Prior | Residual | Recon Err | Absent |")
        lines.append("|--------|-------|---------|------|----------|----------|-----------|--------|")
        for sc in nd.get("decomp_spot_checks", []):
            if "error" in sc:
                lines.append(f"| {sc.get('period')} | ERROR | — | — | — | — | — | {sc['error']} |")
            else:
                lines.append(
                    f"| {sc.get('period')} "
                    f"| {_fmt_num(sc.get('model_point'), 1)} "
                    f"| {_fmt_num(sc.get('private_trend'), 1)} "
                    f"| {_fmt_num(sc.get('government_trend'), 1)} "
                    f"| {_fmt_num(sc.get('bd_prior'), 1)} "
                    f"| {_fmt_num(sc.get('residual'), 1)} "
                    f"| {_fmt_num(sc.get('reconstruction_error'), 4) if sc.get('reconstruction_error') is not None else 'null'} "
                    f"| {','.join(sc.get('absent_parts', [])) or 'none'} |"
                )
        lines.append("")
        lines.append(
            "*Reconstruction error: arithmetic identity check — residual is defined as "
            "model_point minus the sum of the present parts, so |sum(parts) + residual − model_point| "
            "is identically zero by construction when all parts are present. "
            "This does NOT demonstrate decomposition quality; private and government components are "
            "absent from the data and the residual is a plug term, not an independently estimated quantity.*"
        )

    lines.append("")
    lines.append("---")
    lines.append("## Notes")
    lines.append("")
    lines.append("1. AHE vintages (CES0500000003) begin 2006-03. pre-2010 era may have fewer than 60 obs → first predictions may start later.")
    lines.append("2. AWHAETP/JTSJOL vintages similarly begin 2006-03 → legs absent for early periods.")
    lines.append("3. AWH model is persistence-only with explicit no-skill-claim disclosure (persistence_only=True in output).")
    lines.append("4. BD prior uses only prior walk-forward steps (result_pos PIT law). No future residuals used.")
    lines.append("5. Decomposition spot-checks use approximate asof dates; live projection uses exact T-1 dates from the event calendar.")
    lines.append("6. All outputs display_only=True, authority=False.")

    return "\n".join(lines)


def main():
    summary = run_backtest()

    # Write JSON
    json_path = _RESULTS_DIR / "backtest_nfp_decomp_v1.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Written: {json_path}")

    # Write Markdown
    md = generate_md(summary)
    md_path = _RESULTS_DIR / "backtest_nfp_decomp_v1.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Written: {md_path}")

    print("\n" + "=" * 70)
    print(md)
    print("=" * 70)

    return summary


if __name__ == "__main__":
    main()
