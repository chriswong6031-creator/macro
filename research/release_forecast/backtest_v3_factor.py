"""MRI Track M — v3_factor Backtest (PCA top-3 + Ridge Challenger).

SPECIFICATION: research/release_forecast/PREREG_V3_FACTOR.md (frozen 2026-07-08).
ANTI-MINING: run ONCE after prereg commit; no spec changes after observing results.

Runs the expanding-window walk-forward for cpi_headline, cpi_core, nfp using
the v3_factor model (PCA top-3 + ridge on factors + naive anchor).

Also runs the champion (v2 ridge) via run_walk_forward_full() on the same folds
for head-to-head comparison.

Era splits: pre_2010 / 2010_2020 / covid (2020-03..06) / 2020_recovery / 2021_plus.
NFP full-window metric: 2010+ only (per champion prereg §4.1).

Outputs:
  research/release_forecast/RESULTS_V3_FACTOR.md
  research/release_forecast/results/backtest_v3_factor_summary.json

Usage:
  python research/release_forecast/backtest_v3_factor.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (  # noqa: E402
    COVID_MONTHS,
    MIN_QUANTILE_OBS,
    _compute_quantiles,
    _wilson,
    run_walk_forward_full,
)
from engine.release_forecast_v3 import (  # noqa: E402
    run_walk_forward_v3_cpi,
    run_walk_forward_v3_nfp,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
_RESULTS_MD = Path(__file__).resolve().parent / "RESULTS_V3_FACTOR.md"


# ---------------------------------------------------------------------------
# Era classification (same as champion backtest)
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
# Metrics (same as champion backtest)
# ---------------------------------------------------------------------------

def _mae(errors: list[float]) -> float | None:
    if not errors:
        return None
    return float(np.mean(np.abs(errors)))


def _rmse(errors: list[float]) -> float | None:
    if not errors:
        return None
    return float(np.sqrt(np.mean(np.array(errors) ** 2)))


def _coverage(actuals: list[float], p10s: list[float], p90s: list[float]) -> float | None:
    pairs = [(a, lo, hi) for a, lo, hi in zip(actuals, p10s, p90s)
             if a is not None and lo is not None and hi is not None]
    if not pairs:
        return None
    hits = sum(1 for a, lo, hi in pairs if lo <= a <= hi)
    return round(hits / len(pairs), 4)


def _skew_hit_rate(
    predicted: list[float],
    actuals: list[float],
    naive: list[float],
) -> tuple[float | None, list[float] | None, int]:
    valid = [
        (p, a, n) for p, a, n in zip(predicted, actuals, naive)
        if p is not None and a is not None and n is not None
        and (p - n) != 0 and (a - n) != 0
    ]
    if not valid:
        return None, None, 0
    hits = sum(1 for p, a, n in valid if math.copysign(1, p - n) == math.copysign(1, a - n))
    n = len(valid)
    rate = round(hits / n, 4)
    ci = _wilson(hits, n)
    return rate, ci, n


def _compute_metrics(
    rows: list[dict],
    errors_accum: np.ndarray,
    min_q: int = MIN_QUANTILE_OBS,
) -> dict:
    if not rows:
        return {
            "n": 0, "mae_model": None, "rmse_model": None,
            "mae_naive": None, "rmse_naive": None,
            "mae_trailing3m": None, "rmse_trailing3m": None,
            "mae_ar3": None, "rmse_ar3": None,
            "coverage_p10_p90": None,
            "skew_hit_rate": None, "skew_wilson_ci": None, "skew_n": 0,
        }

    actuals = [r["actual"] for r in rows]
    preds = [r["predicted"] for r in rows]
    naive_preds = [r["baseline_naive"] for r in rows]
    t3m_preds = [r.get("baseline_trailing3m") for r in rows]
    ar3_preds = [r.get("baseline_ar3") for r in rows]

    model_errors = [a - p for a, p in zip(actuals, preds) if a is not None and p is not None]
    naive_errors = [a - n for a, n in zip(actuals, naive_preds) if a is not None and n is not None]
    t3m_errors = [a - t for a, t in zip(actuals, t3m_preds) if a is not None and t is not None]
    ar3_errors = [a - b for a, b in zip(actuals, ar3_preds) if a is not None and b is not None]

    # Build p10/p90 from accumulated residual history (use result_pos for strict past)
    p10s, p90s = [], []
    for r in rows:
        pos = r.get("result_pos", 0)
        past_errors = errors_accum[:pos]
        if len(past_errors) >= min_q:
            p10 = r["predicted"] + float(np.quantile(past_errors, 0.10))
            p90 = r["predicted"] + float(np.quantile(past_errors, 0.90))
        else:
            p10, p90 = None, None
        p10s.append(p10)
        p90s.append(p90)

    cov = _coverage(actuals, p10s, p90s)
    hit_rate, ci, skew_n = _skew_hit_rate(preds, actuals, naive_preds)

    return {
        "n": len(rows),
        "mae_model": round(_mae(model_errors), 4) if _mae(model_errors) is not None else None,
        "rmse_model": round(_rmse(model_errors), 4) if _rmse(model_errors) is not None else None,
        "mae_naive": round(_mae(naive_errors), 4) if _mae(naive_errors) is not None else None,
        "rmse_naive": round(_rmse(naive_errors), 4) if _rmse(naive_errors) is not None else None,
        "mae_trailing3m": round(_mae(t3m_errors), 4) if _mae(t3m_errors) is not None else None,
        "rmse_trailing3m": round(_rmse(t3m_errors), 4) if _rmse(t3m_errors) is not None else None,
        "mae_ar3": round(_mae(ar3_errors), 4) if _mae(ar3_errors) is not None else None,
        "rmse_ar3": round(_rmse(ar3_errors), 4) if _rmse(ar3_errors) is not None else None,
        "coverage_p10_p90": cov,
        "skew_hit_rate": hit_rate,
        "skew_wilson_ci": ci,
        "skew_n": skew_n,
    }


def _check_kill_rule(metrics_full: dict, metrics_2021: dict) -> bool:
    """True = kill (challenger MAE >= naive MAE in BOTH full AND 2021+ slice)."""
    mae_m_full = metrics_full.get("mae_model")
    mae_n_full = metrics_full.get("mae_naive")
    mae_m_2021 = metrics_2021.get("mae_model")
    mae_n_2021 = metrics_2021.get("mae_naive")
    if any(x is None for x in [mae_m_full, mae_n_full, mae_m_2021, mae_n_2021]):
        return False
    return (mae_m_full >= mae_n_full) and (mae_m_2021 >= mae_n_2021)


# ---------------------------------------------------------------------------
# Head-to-head helper
# ---------------------------------------------------------------------------

def _build_h2h_table(
    v3_rows: list[dict],
    champ_rows: list[dict],
    era_name: str,
    v3_errors_accum: np.ndarray,
    champ_errors_accum: np.ndarray,
) -> dict:
    """Build head-to-head metrics for v3 vs champion on same era rows."""
    v3_m = _compute_metrics(v3_rows, v3_errors_accum)
    champ_m = _compute_metrics(champ_rows, champ_errors_accum)
    return {
        "era": era_name,
        "n_v3": v3_m["n"],
        "n_champ": champ_m["n"],
        "mae_v3": v3_m["mae_model"],
        "mae_champ": champ_m["mae_model"],
        "mae_naive": v3_m["mae_naive"],
        "cov_v3": v3_m["coverage_p10_p90"],
        "cov_champ": champ_m["coverage_p10_p90"],
        "skew_hr_v3": v3_m["skew_hit_rate"],
        "skew_hr_champ": champ_m["skew_hit_rate"],
    }


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest() -> dict:
    print("=== MRI Track M v3_factor Backtest ===\n")
    root = _REPO
    summary: dict[str, Any] = {}
    md_lines: list[str] = []

    md_lines.append("# Results V3 Factor — MRI Track M Challenger (PCA + Ridge)")
    md_lines.append("")
    md_lines.append("**Run date:** 2026-07-08")
    md_lines.append("**Spec:** research/release_forecast/PREREG_V3_FACTOR.md (frozen 2026-07-08)")
    md_lines.append("**Model:** v3_factor — PCA top-3 via SVD + ridge(lambda=1.0) on [factors + naive anchor]")
    md_lines.append("**Anti-mining:** backtest run once after prereg commit; no spec changes post-results.")
    md_lines.append("")
    md_lines.append("Kill rule: challenger MAE >= naive MAE in BOTH full window AND 2021+ -> benchmark_only/no_shadow")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    for release in ["cpi_headline", "cpi_core", "nfp"]:
        print(f"Running v3 walk-forward: {release} ...")

        # --- v3 walk-forward ---
        if release in ("cpi_headline", "cpi_core"):
            wf_v3 = run_walk_forward_v3_cpi(release, root)
        else:
            wf_v3 = run_walk_forward_v3_nfp(root)

        results_v3 = wf_v3["results"]
        print(f"  v3: {len(results_v3)} predictions")

        # --- champion walk-forward ---
        print(f"  Running champion walk-forward: {release} ...")
        wf_champ = run_walk_forward_full(release, root)
        results_champ = wf_champ["results"]
        print(f"  champion: {len(results_champ)} predictions")

        # Accumulated errors for quantile intervals
        errors_v3 = np.array([r["actual"] - r["predicted"] for r in results_v3])
        errors_champ = np.array([r["actual"] - r["predicted"] for r in results_champ])

        def get_period(r: dict) -> pd.Timestamp | None:
            p = r.get("period")
            return pd.Timestamp(p) if p is not None else None

        # Era rows — v3
        rows_all_v3 = [r for r in results_v3 if get_period(r) is not None]
        rows_pre2010_v3 = [r for r in rows_all_v3 if _era(get_period(r)) == "pre_2010"]
        rows_2010_2020_v3 = [r for r in rows_all_v3 if _era(get_period(r)) == "2010_2020"]
        rows_covid_v3 = [r for r in rows_all_v3 if _era(get_period(r)) == "covid"]
        rows_recovery_v3 = [r for r in rows_all_v3 if _era(get_period(r)) == "2020_recovery"]
        rows_2021_v3 = [r for r in rows_all_v3 if _era(get_period(r)) == "2021_plus"]

        # Era rows — champion (for h2h)
        rows_all_champ = [r for r in results_champ if get_period(r) is not None]
        rows_pre2010_champ = [r for r in rows_all_champ if _era(get_period(r)) == "pre_2010"]
        rows_2010_2020_champ = [r for r in rows_all_champ if _era(get_period(r)) == "2010_2020"]
        rows_covid_champ = [r for r in rows_all_champ if _era(get_period(r)) == "covid"]
        rows_recovery_champ = [r for r in rows_all_champ if _era(get_period(r)) == "2020_recovery"]
        rows_2021_champ = [r for r in rows_all_champ if _era(get_period(r)) == "2021_plus"]

        # NFP: 2010+ evaluation floor per prereg
        if release == "nfp":
            rows_eval_v3 = [r for r in rows_all_v3 if _era(get_period(r)) != "pre_2010"]
            rows_eval_champ = [r for r in rows_all_champ if _era(get_period(r)) != "pre_2010"]
            errors_eval_v3 = np.array([r["actual"] - r["predicted"] for r in rows_eval_v3])
            errors_eval_champ = np.array([r["actual"] - r["predicted"] for r in rows_eval_champ])
        else:
            rows_eval_v3 = rows_all_v3
            rows_eval_champ = rows_all_champ
            errors_eval_v3 = errors_v3
            errors_eval_champ = errors_champ

        # --- Compute metrics ---
        m_full_v3 = _compute_metrics(rows_eval_v3, errors_v3)
        m_pre2010_v3 = _compute_metrics(rows_pre2010_v3, errors_v3)
        m_2010_2020_v3 = _compute_metrics(rows_2010_2020_v3, errors_v3)
        m_covid_v3 = _compute_metrics(rows_covid_v3, errors_v3)
        m_recovery_v3 = _compute_metrics(rows_recovery_v3, errors_v3)
        m_2021_v3 = _compute_metrics(rows_2021_v3, errors_v3)

        rows_2015_v3 = [
            r for r in rows_all_v3
            if get_period(r) is not None and get_period(r) >= pd.Timestamp("2015-01-01")
        ]
        m_2015_v3 = _compute_metrics(rows_2015_v3, errors_v3)

        kill = _check_kill_rule(m_full_v3, m_2021_v3)
        verdict = "SHADOW-ELIGIBLE" if not kill else "NULL (benchmark_only)"

        # Champion full metrics (for h2h)
        m_full_champ = _compute_metrics(rows_eval_champ, errors_champ)
        m_2021_champ = _compute_metrics(rows_2021_champ, errors_champ)

        summary[release] = {
            "n_v3": len(results_v3),
            "n_champ": len(results_champ),
            "kill_triggered": kill,
            "verdict": verdict,
            "era_metrics_v3": {
                "full" if release != "nfp" else "full_2010_plus": m_full_v3,
                "pre_2010": m_pre2010_v3,
                "2010_2020": m_2010_2020_v3,
                "covid": m_covid_v3,
                "2020_recovery": m_recovery_v3,
                "2021_plus": m_2021_v3,
                "2015_plus": m_2015_v3,
            },
            "champion_full": m_full_champ,
            "champion_2021": m_2021_champ,
        }

        print(f"  Kill: {kill} -> {verdict}")
        print(f"  Full MAE v3={m_full_v3['mae_model']} naive={m_full_v3['mae_naive']} champ={m_full_champ['mae_model']}")
        print(f"  2021+ MAE v3={m_2021_v3['mae_model']} naive={m_2021_v3['mae_naive']} champ={m_2021_champ['mae_model']}")

        # --- Markdown output ---
        full_label = "Full (2010+, per prereg)" if release == "nfp" else "Full"
        md_lines.append(f"## {release}")
        md_lines.append("")
        md_lines.append(f"**v3_factor total predictions:** {len(results_v3)}")
        md_lines.append(f"**champion total predictions:** {len(results_champ)}")
        md_lines.append(f"**Kill rule triggered:** {kill}")
        md_lines.append(f"**Verdict: {verdict}**")
        md_lines.append("")

        # Era table — v3
        md_lines.append("### v3_factor Era-Split Metrics")
        md_lines.append("")
        md_lines.append("| Era | n | MAE v3 | MAE Naive | MAE Trail3m | MAE AR3 | RMSE v3 | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |")
        md_lines.append("|-----|---|--------|-----------|-------------|---------|---------|------------|-------------|---------|---------------|--------|")

        era_rows = [
            (full_label, m_full_v3),
            ("pre-2010", m_pre2010_v3),
            ("2010–2020-02", m_2010_2020_v3),
            ("COVID (2020-03..06)", m_covid_v3),
            ("2020-07..12 (recovery gap)", m_recovery_v3),
            ("2021+", m_2021_v3),
            ("2015+ (stable feature set, suppl.)", m_2015_v3),
        ]
        for era_name, m in era_rows:
            cov_str = f"{m['coverage_p10_p90']*100:.1f}%" if m['coverage_p10_p90'] is not None else "—"
            ci_str = str(m['skew_wilson_ci']) if m['skew_wilson_ci'] is not None else "—"
            md_lines.append(
                f"| {era_name} | {m['n']} "
                f"| {m['mae_model'] or '—'} | {m['mae_naive'] or '—'} "
                f"| {m['mae_trailing3m'] or '—'} | {m['mae_ar3'] or '—'} "
                f"| {m['rmse_model'] or '—'} | {m['rmse_naive'] or '—'} "
                f"| {cov_str} | {m['skew_hit_rate'] or '—'} "
                f"| {ci_str} | {m['skew_n']} |"
            )
        md_lines.append("")

        # Kill rule detail
        md_lines.append("### Kill Rule Detail")
        md_lines.append("")
        fw_key = "2010+ window (per prereg)" if release == "nfp" else "Full window"
        md_lines.append(f"- {fw_key}: MAE v3={m_full_v3['mae_model']} vs naive={m_full_v3['mae_naive']}")
        md_lines.append(f"- 2021+ slice: MAE v3={m_2021_v3['mae_model']} vs naive={m_2021_v3['mae_naive']}")
        md_lines.append(f"- Kill triggered: {'YES -> benchmark_only' if kill else 'NO -> shadow-eligible'}")
        md_lines.append("")

        # Head-to-head vs champion
        md_lines.append("### Head-to-Head: v3_factor vs Champion (v2 ridge)")
        md_lines.append("")
        md_lines.append("| Era | n | MAE v3 | MAE Champion | MAE Naive | Cov v3 | Cov Champ | Skew HR v3 | Skew HR Champ |")
        md_lines.append("|-----|---|--------|-------------|-----------|--------|-----------|------------|---------------|")

        h2h_eras = [
            (full_label, rows_eval_v3, rows_eval_champ),
            ("pre-2010", rows_pre2010_v3, rows_pre2010_champ),
            ("2010–2020-02", rows_2010_2020_v3, rows_2010_2020_champ),
            ("COVID (2020-03..06)", rows_covid_v3, rows_covid_champ),
            ("2020-07..12", rows_recovery_v3, rows_recovery_champ),
            ("2021+", rows_2021_v3, rows_2021_champ),
        ]
        for era_name, v3_era_rows, champ_era_rows in h2h_eras:
            v3_m = _compute_metrics(v3_era_rows, errors_v3)
            c_m = _compute_metrics(champ_era_rows, errors_champ)
            cov_v3 = f"{v3_m['coverage_p10_p90']*100:.1f}%" if v3_m['coverage_p10_p90'] is not None else "—"
            cov_c = f"{c_m['coverage_p10_p90']*100:.1f}%" if c_m['coverage_p10_p90'] is not None else "—"
            md_lines.append(
                f"| {era_name} | {v3_m['n']} "
                f"| {v3_m['mae_model'] or '—'} | {c_m['mae_model'] or '—'} | {v3_m['mae_naive'] or '—'} "
                f"| {cov_v3} | {cov_c} "
                f"| {v3_m['skew_hit_rate'] or '—'} | {c_m['skew_hit_rate'] or '—'} |"
            )
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    # Summary verdict section
    md_lines.append("## Summary Verdicts")
    md_lines.append("")
    md_lines.append("| Target | Full MAE v3 | Full MAE Naive | Full MAE Champ | 2021+ MAE v3 | 2021+ MAE Naive | 2021+ MAE Champ | Kill? | Verdict |")
    md_lines.append("|--------|-------------|----------------|----------------|--------------|-----------------|-----------------|-------|---------|")
    for release, s in summary.items():
        era_key = "full_2010_plus" if release == "nfp" else "full"
        m_full = s["era_metrics_v3"].get(era_key, s["era_metrics_v3"].get("full", {}))
        m_2021 = s["era_metrics_v3"].get("2021_plus", {})
        m_fc = s["champion_full"]
        m_2021c = s["champion_2021"]
        md_lines.append(
            f"| {release} "
            f"| {m_full.get('mae_model', '—')} "
            f"| {m_full.get('mae_naive', '—')} "
            f"| {m_fc.get('mae_model', '—')} "
            f"| {m_2021.get('mae_model', '—')} "
            f"| {m_2021.get('mae_naive', '—')} "
            f"| {m_2021c.get('mae_model', '—')} "
            f"| {'YES' if s['kill_triggered'] else 'NO'} "
            f"| {s['verdict']} |"
        )
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Data Legs Absent / Caveats")
    md_lines.append("")
    md_lines.append("- **ppi_fes_mom_lag1 (PPIFES):** ALFRED vintages start 2010-04; absent pre-2010. Dropped via complete-case.")
    md_lines.append("- **dollar_mom (DTWEXBGS):** Daily series starts 2006-01-02; monthly avg MoM computable from 2006-02. Absent pre-2006. Dropped via complete-case.")
    md_lines.append("- **shelter_nowcast:** Requires ZORI (2015-01+) with 12-month window; first usable ~2016-01. Absent pre-2016. Dropped via complete-case.")
    md_lines.append("- **gasoline_mom (headline only):** GASREGW starts 1990-08; covered full CPI history. Not expected to be absent.")
    md_lines.append("- **adp_change (NFP):** ADPMNUSNERSA starts 2010-01; adp_change computable from 2010-02. ADP 2022-08 methodology redesign = regime break noted.")
    md_lines.append("- **claims_survey_week (NFP):** ICSA/CCSA vintages start 2009-05/2009-09. Absent pre-2009. Dropped via complete-case.")
    md_lines.append("- **withheld_tax_yoy (NFP):** Data starts 2023-02-14; YoY computable ~2024-02. Effectively absent for all historical backtest. Dropped.")
    md_lines.append("- **sticky/median/flex/ppi_fis:** ALFRED vintages start 2014-02/2014-03; absent pre-2014. Dropped. Pre-2014 v3 runs on own lags only (k≤3 features).")
    md_lines.append("")

    # Write markdown
    md_content = "\n".join(md_lines)
    _RESULTS_MD.write_text(md_content, encoding="utf-8")
    print(f"\nResults written to: {_RESULTS_MD}")

    # Write JSON summary
    summary_path = _RESULTS_DIR / "backtest_v3_factor_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"JSON summary written to: {summary_path}")

    return summary


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_backtest()
    print("\n=== FINAL VERDICTS ===")
    for release, s in results.items():
        print(f"  {release}: {s['verdict']}")
