"""MRI-R30 Interval Recalibration — Coverage Comparison (BEFORE vs AFTER).

Computes per-era p10-p90 and p25-p75 coverage, and pinball loss, for each engine's
walk-forward results, comparing unscaled (BEFORE) vs vol-scaled (AFTER) bands.

Outputs: research/release_forecast/results/interval_recal_v1_coverage.json
         and prints summary tables.

Usage:
    python research/release_forecast/backtest_interval_recal_v1.py

Run from repo root. Reads from data/ (real parquets must be present).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (
    COVID_MONTHS,
    MIN_QUANTILE_OBS,
    _compute_quantiles_unscaled,
    _compute_quantiles_volscaled,
    run_walk_forward_full,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Vol-scaled parameters (frozen per PREREG_INTERVAL_RECAL_V1.md)
VOL_WINDOW = 24
MIN_SIGMA_OBS = 12


# ---------------------------------------------------------------------------
# Era classification (mirrors backtest_release_forecast.py)
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


def _is_2021plus(period: pd.Timestamp) -> bool:
    return period.year >= 2021


# ---------------------------------------------------------------------------
# Coverage metrics
# ---------------------------------------------------------------------------

def _coverage(actuals: list[float], p10s: list[float | None], p90s: list[float | None]) -> float | None:
    pairs = [
        (a, lo, hi)
        for a, lo, hi in zip(actuals, p10s, p90s)
        if a is not None and lo is not None and hi is not None
    ]
    if not pairs:
        return None
    hits = sum(1 for a, lo, hi in pairs if lo <= a <= hi)
    return round(hits / len(pairs), 4)


def _coverage_p25_p75(actuals: list[float], p25s: list[float | None], p75s: list[float | None]) -> float | None:
    pairs = [
        (a, lo, hi)
        for a, lo, hi in zip(actuals, p25s, p75s)
        if a is not None and lo is not None and hi is not None
    ]
    if not pairs:
        return None
    hits = sum(1 for a, lo, hi in pairs if lo <= a <= hi)
    return round(hits / len(pairs), 4)


def _pinball(actuals: list[float], quantile_rows: list[dict]) -> float | None:
    """5-quantile pinball loss sum: sum over q in {0.10,0.25,0.50,0.75,0.90} of pinball(q)."""
    qs = [0.10, 0.25, 0.50, 0.75, 0.90]
    keys = ["p10", "p25", "p50", "p75", "p90"]
    losses = []
    for a, qrow in zip(actuals, quantile_rows):
        if a is None:
            continue
        row_loss = 0.0
        valid = True
        for q, k in zip(qs, keys):
            v = qrow.get(k)
            if v is None:
                valid = False
                break
            diff = a - v
            row_loss += q * diff if diff >= 0 else (q - 1) * diff
        if valid:
            losses.append(row_loss)
    if not losses:
        return None
    return round(float(np.mean(losses)), 6)


# ---------------------------------------------------------------------------
# Per-step band computation: unscaled vs vol-scaled
# ---------------------------------------------------------------------------

def _compute_era_coverage(
    results: list[dict],
    era_rows_idx: list[int],
    errors_accum: np.ndarray,
) -> dict:
    """Compute BEFORE/AFTER coverage for a subset of result rows.

    era_rows_idx: indices into results[] for this era.
    errors_accum: full array of walk-forward errors in chronological order.
    """
    if not era_rows_idx:
        return {
            "n": 0,
            "cov_p10_p90_before": None, "cov_p10_p90_after": None,
            "cov_p25_p75_before": None, "cov_p25_p75_after": None,
            "pinball_before": None, "pinball_after": None,
        }

    actuals_era: list[float] = []
    # BEFORE: unscaled (original behavior — raw quantile on past errors)
    p10s_before, p25s_before, p50s_before, p75s_before, p90s_before = [], [], [], [], []
    # AFTER: vol-scaled
    p10s_after, p25s_after, p50s_after, p75s_after, p90s_after = [], [], [], [], []

    for idx in era_rows_idx:
        r = results[idx]
        actual = r.get("actual")
        predicted = r.get("predicted")
        pos = r.get("result_pos", 0)

        actuals_era.append(actual)

        # Past errors = all errors strictly before this prediction (via result_pos)
        past_errors = errors_accum[:pos]

        # BEFORE: unscaled
        q_before = _compute_quantiles_unscaled(past_errors, predicted if predicted is not None else 0.0)
        p10s_before.append(q_before["p10"])
        p25s_before.append(q_before["p25"])
        p50s_before.append(q_before["p50"])
        p75s_before.append(q_before["p75"])
        p90s_before.append(q_before["p90"])

        # AFTER: vol-scaled (uses only past_errors for both sigma_i and sigma_now)
        q_after = _compute_quantiles_volscaled(
            past_errors, predicted if predicted is not None else 0.0,
            vol_window=VOL_WINDOW, min_sigma_obs=MIN_SIGMA_OBS,
        )
        p10s_after.append(q_after["p10"])
        p25s_after.append(q_after["p25"])
        p50s_after.append(q_after["p50"])
        p75s_after.append(q_after["p75"])
        p90s_after.append(q_after["p90"])

    cov_before = _coverage(actuals_era, p10s_before, p90s_before)
    cov_after = _coverage(actuals_era, p10s_after, p90s_after)
    cov25_before = _coverage_p25_p75(actuals_era, p25s_before, p75s_before)
    cov25_after = _coverage_p25_p75(actuals_era, p25s_after, p75s_after)

    qrows_before = [
        {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90}
        for p10, p25, p50, p75, p90 in zip(p10s_before, p25s_before, p50s_before, p75s_before, p90s_before)
    ]
    qrows_after = [
        {"p10": p10, "p25": p25, "p50": p50, "p75": p75, "p90": p90}
        for p10, p25, p50, p75, p90 in zip(p10s_after, p25s_after, p50s_after, p75s_after, p90s_after)
    ]
    pinball_before = _pinball(actuals_era, qrows_before)
    pinball_after = _pinball(actuals_era, qrows_after)

    return {
        "n": len(era_rows_idx),
        "cov_p10_p90_before": cov_before,
        "cov_p10_p90_after": cov_after,
        "cov_p25_p75_before": cov25_before,
        "cov_p25_p75_after": cov25_after,
        "pinball_before": pinball_before,
        "pinball_after": pinball_after,
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_coverage_comparison() -> dict:
    """Run coverage comparison for all four engines. Returns summary dict."""
    print("=== MRI-R30 Interval Recalibration — Coverage Comparison ===\n")
    root = _REPO
    summary: dict[str, Any] = {}

    releases = [
        ("cpi_headline", "run_walk_forward_full"),
        ("cpi_core",     "run_walk_forward_full"),
        ("nfp",          "run_walk_forward_full"),
    ]

    # v3_factor challenger (CPI+NFP targets)
    from engine.release_forecast_v3 import run_walk_forward_v3_cpi, run_walk_forward_v3_nfp
    # mf_energy challenger
    from engine.release_mf_energy import run_walk_forward_mf
    # New targets (pce_headline, pce_core, ppi_finaldemand)
    from engine.release_targets_v11 import (
        build_wf_pce_headline,
        build_wf_pce_core,
        build_wf_ppi_finaldemand,
    )

    def _run_wf(release_tag: str):
        """Return (results, errors_accum) for a given release tag."""
        if release_tag in ("cpi_headline", "cpi_core", "nfp", "claims"):
            wf = run_walk_forward_full(release_tag, root)
            results = wf["results"]
        elif release_tag == "pce_headline":
            wf = build_wf_pce_headline(root)
            results = wf["results"]
        elif release_tag == "pce_core":
            wf = build_wf_pce_core(root)
            results = wf["results"]
        elif release_tag == "ppi_finaldemand":
            wf = build_wf_ppi_finaldemand(root)
            results = wf["results"]
        elif release_tag == "mf_energy":
            wf = run_walk_forward_mf(root)
            results = wf["results"]
        elif release_tag in ("v3_cpi_headline", "v3_cpi_core"):
            cpi_type = "cpi_headline" if release_tag == "v3_cpi_headline" else "cpi_core"
            wf = run_walk_forward_v3_cpi(cpi_type, root)
            results = wf["results"]
        elif release_tag == "v3_nfp":
            wf = run_walk_forward_v3_nfp(root)
            results = wf["results"]
        else:
            raise ValueError(f"Unknown release: {release_tag}")
        errors_accum = np.array([r["actual"] - r["predicted"] for r in results])
        return results, errors_accum

    def _get_period(r: dict):
        p = r.get("period")
        if p is None:
            return None
        return pd.Timestamp(p)

    target_list = [
        "cpi_headline", "cpi_core", "nfp",
        "pce_headline", "pce_core", "ppi_finaldemand",
        "v3_cpi_headline", "v3_cpi_core", "v3_nfp",
        "mf_energy",
    ]

    for release_tag in target_list:
        print(f"  Processing {release_tag} ...")
        try:
            results, errors_accum = _run_wf(release_tag)
        except Exception as e:
            print(f"    SKIP ({e})")
            summary[release_tag] = {"error": str(e)}
            continue

        if not results:
            print(f"    SKIP (no results)")
            summary[release_tag] = {"error": "no_results"}
            continue

        print(f"    {len(results)} walk-forward predictions")

        # Era classification
        rows_2021_idx = [
            i for i, r in enumerate(results)
            if _get_period(r) is not None and _is_2021plus(_get_period(r))
        ]
        rows_full_idx = [
            i for i, r in enumerate(results)
            if _get_period(r) is not None
        ]

        # 2015+ era (supplementary, for CPI)
        rows_2015_idx = [
            i for i, r in enumerate(results)
            if _get_period(r) is not None and _get_period(r).year >= 2015
        ]

        m_full = _compute_era_coverage(results, rows_full_idx, errors_accum)
        m_2021 = _compute_era_coverage(results, rows_2021_idx, errors_accum)
        m_2015 = _compute_era_coverage(results, rows_2015_idx, errors_accum)

        summary[release_tag] = {
            "full": m_full,
            "2021_plus": m_2021,
            "2015_plus": m_2015,
        }

        # Print table
        def _fmt_pct(v):
            return f"{v*100:.1f}%" if v is not None else "N/A"

        def _fmt_pb(v):
            return f"{v:.6f}" if v is not None else "N/A"

        print(f"\n  {release_tag} Coverage BEFORE vs AFTER (MRI-R30):")
        print(f"  {'Era':<12} {'n':>5} {'p10-p90 BEF':>12} {'p10-p90 AFT':>12} {'p25-p75 BEF':>12} {'p25-p75 AFT':>12} {'Pinball BEF':>12} {'Pinball AFT':>12}")
        for era_name, m in [("Full", m_full), ("2021+", m_2021), ("2015+", m_2015)]:
            print(f"  {era_name:<12} {m['n']:>5} {_fmt_pct(m['cov_p10_p90_before']):>12} {_fmt_pct(m['cov_p10_p90_after']):>12} {_fmt_pct(m['cov_p25_p75_before']):>12} {_fmt_pct(m['cov_p25_p75_after']):>12} {_fmt_pb(m['pinball_before']):>12} {_fmt_pb(m['pinball_after']):>12}")
        print()

    # Write JSON
    out_path = _RESULTS_DIR / "interval_recal_v1_coverage.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nWrote: {out_path}")

    return summary


if __name__ == "__main__":
    run_coverage_comparison()
