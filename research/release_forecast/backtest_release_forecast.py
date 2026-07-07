"""Macro Release Intelligence — Walk-Forward Backtest (V1).

Runs the frozen walk-forward for cpi_headline, cpi_core, nfp.

Writes:
  research/release_forecast/results/backtest_v1_summary.json
  research/release_forecast/RESULTS_V1.md

Per PREREG_V1.md:
  Era splits: pre-2010 / 2010-2020 / 2021+
  NFP COVID rows (2020-03..2020-06) printed separately (incl/excl pair)
  Metrics: MAE + RMSE vs each baseline per era
  Coverage: p10-p90 interval
  Skew hit-rate + Wilson 95% CI
  Kill rule: model MAE >= naive MAE in BOTH full and 2021+ slice -> benchmark_only

Usage:
  python research/release_forecast/backtest_release_forecast.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Repo root
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (  # noqa: E402
    COVID_MONTHS,
    MIN_QUANTILE_OBS,
    _compute_quantiles,
    _wilson,
    run_walk_forward_full,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Era classification
# ---------------------------------------------------------------------------

def _era(period: pd.Timestamp) -> str:
    """Classify period into era per PREREG_V1.md §6.1.

    pre_2010:        1997-01 .. 2009-12
    2010_2020:       2010-01 .. 2020-02  (pre-COVID per spec)
    covid:           2020-03 .. 2020-06  (printed separately; NOT assigned to a main era cell)
    2020_recovery:   2020-07 .. 2020-12  (gap unassigned in PREREG; see AMENDMENTS)
    2021_plus:       2021-01 .. latest
    """
    if period.year < 2010:
        return "pre_2010"
    y, m = period.year, period.month
    if y == 2020:
        if m <= 2:
            return "2010_2020"
        elif m <= 6:
            return "covid"        # 2020-03..2020-06: COVID, separate row
        else:
            return "2020_recovery"  # 2020-07..2020-12: gap in PREREG
    if y < 2021:
        return "2010_2020"
    return "2021_plus"


def _is_covid(period: pd.Timestamp) -> bool:
    return (period.year, period.month) in COVID_MONTHS


# ---------------------------------------------------------------------------
# Metrics computation
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
    """Fraction of actuals in [p10, p90]."""
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
    """Sign(model - naive) == sign(actual - naive) hit-rate + Wilson 95% CI."""
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


def _compute_metrics(rows: list[dict], errors_accum: np.ndarray, min_q: int = MIN_QUANTILE_OBS) -> dict:
    """Compute all metrics for a subset of walk-forward rows."""
    if not rows:
        return {"n": 0, "mae_model": None, "rmse_model": None,
                "mae_naive": None, "rmse_naive": None,
                "mae_trailing3m": None, "rmse_trailing3m": None,
                "mae_ar3": None, "rmse_ar3": None,
                "coverage_p10_p90": None,
                "skew_hit_rate": None, "skew_wilson_ci": None, "skew_n": 0}

    actuals = [r["actual"] for r in rows]
    preds = [r["predicted"] for r in rows]
    naive_preds = [r["baseline_naive"] for r in rows]
    t3m_preds = [r["baseline_trailing3m"] for r in rows]
    ar3_preds = [r["baseline_ar3"] for r in rows]

    model_errors = [a - p for a, p in zip(actuals, preds)]
    naive_errors = [a - n for a, n in zip(actuals, naive_preds)]
    t3m_errors = [a - t for a, t in zip(actuals, t3m_preds)]
    ar3_errors = [a - b for a, b in zip(actuals, ar3_preds)]

    # Quantile intervals from expanding residual history.
    # CRITICAL: use result_pos (the ordinal position of this result among ALL walk-forward
    # predictions) to slice errors_accum[:result_pos], giving only residuals from strictly
    # PRIOR predictions. Using r["idx"] (record index, ~60..351) would pull FUTURE residuals.
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


# ---------------------------------------------------------------------------
# Kill rule
# ---------------------------------------------------------------------------

def _check_kill_rule(metrics_full: dict, metrics_2021: dict) -> bool:
    """True = kill (model MAE >= naive MAE in BOTH full and 2021+ slice)."""
    mae_m_full = metrics_full.get("mae_model")
    mae_n_full = metrics_full.get("mae_naive")
    mae_m_2021 = metrics_2021.get("mae_model")
    mae_n_2021 = metrics_2021.get("mae_naive")

    if mae_m_full is None or mae_n_full is None:
        return False  # insufficient data to trigger kill
    if mae_m_2021 is None or mae_n_2021 is None:
        return False

    return (mae_m_full >= mae_n_full) and (mae_m_2021 >= mae_n_2021)


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest() -> dict:
    print("=== Macro Release Intelligence: Walk-Forward Backtest V1 ===\n")
    root = _REPO
    summary: dict[str, Any] = {}

    for release in ["cpi_headline", "cpi_core", "nfp", "claims"]:
        print(f"Running walk-forward: {release} ...")
        wf = run_walk_forward_full(release, root)
        results = wf["results"]
        print(f"  {len(results)} predictions")

        # Accumulate errors for quantile intervals
        errors_accum = np.array([r["actual"] - r["predicted"] for r in results])

        # Filter rows by era
        def get_period(r):
            p = r.get("period")
            if p is None:
                return None
            return pd.Timestamp(p)

        rows_all = [r for r in results if get_period(r) is not None]
        rows_pre2010 = [r for r in rows_all if _era(get_period(r)) == "pre_2010"]
        rows_2010_2020 = [r for r in rows_all if _era(get_period(r)) == "2010_2020"]
        rows_covid = [r for r in rows_all if _era(get_period(r)) == "covid"]
        rows_2020_recovery = [r for r in rows_all if _era(get_period(r)) == "2020_recovery"]
        rows_2021 = [r for r in rows_all if _era(get_period(r)) == "2021_plus"]

        # NFP: apply 2010 eval floor — drop pre-2010 predictions from NFP evaluation
        if release == "nfp":
            rows_nfp_eval = [r for r in rows_all if _era(get_period(r)) != "pre_2010"]
            errors_accum_nfp_eval = np.array([r["actual"] - r["predicted"] for r in rows_nfp_eval])
        else:
            rows_nfp_eval = rows_all

        # Compute metrics per era
        # For full NFP: use 2010+ per prereg (rename "full" to "2010_plus" for NFP)
        if release == "nfp":
            m_full_or_2010plus = _compute_metrics(rows_nfp_eval, errors_accum)
        else:
            m_full_or_2010plus = _compute_metrics(rows_all, errors_accum)
        m_pre2010 = _compute_metrics(rows_pre2010, errors_accum)
        m_2010_2020 = _compute_metrics(rows_2010_2020, errors_accum)
        m_covid = _compute_metrics(rows_covid, errors_accum)
        m_2020_recovery = _compute_metrics(rows_2020_recovery, errors_accum)
        m_2021 = _compute_metrics(rows_2021, errors_accum)

        # Supplementary: 2015+ rows for stable-feature-set coverage (disclosure fix 9)
        # Reference month >= 2015-01 means sticky/median/flex/PPI features are consistently present
        rows_2015_plus = [
            r for r in rows_all
            if get_period(r) is not None and get_period(r) >= pd.Timestamp("2015-01-01")
        ]
        m_2015_plus = _compute_metrics(rows_2015_plus, errors_accum)

        if release == "nfp":
            era_metrics = {
                "full_2010_plus": m_full_or_2010plus,  # per-prereg NFP eval starts 2010
                "pre_2010": m_pre2010,
                "2010_2020": m_2010_2020,
                "covid_months_2020_03_06": m_covid,
                "2020_recovery": m_2020_recovery,
                "2021_plus": m_2021,
                "2010_2020_excl_covid": _compute_metrics(rows_2010_2020, errors_accum),
                "2015_plus_stable_features": m_2015_plus,
            }
        elif release == "claims":
            # Claims: add 2010-2019 pre-COVID visibility slice per MRI-R9 task spec
            rows_2010_2019 = [
                r for r in rows_all
                if get_period(r) is not None
                and get_period(r) >= pd.Timestamp("2010-01-01")
                and get_period(r) < pd.Timestamp("2020-01-01")
            ]
            m_2010_2019 = _compute_metrics(rows_2010_2019, errors_accum)
            era_metrics = {
                "full": m_full_or_2010plus,
                "pre_2010": m_pre2010,
                "2010_2020": m_2010_2020,
                "2010_2019_pre_covid": m_2010_2019,
                "covid_months_2020_03_06": m_covid,
                "2020_recovery": m_2020_recovery,
                "2021_plus": m_2021,
            }
        else:
            era_metrics = {
                "full": m_full_or_2010plus,
                "pre_2010": m_pre2010,
                "2010_2020": m_2010_2020,
                "covid_months_2020_03_06": m_covid,
                "2020_recovery": m_2020_recovery,
                "2021_plus": m_2021,
                "2015_plus_stable_features": m_2015_plus,
            }

        # Kill rule (use full/2010_plus for NFP)
        m_kill_full = era_metrics.get("full_2010_plus") or era_metrics.get("full", {})
        killed = _check_kill_rule(m_kill_full, m_2021)
        status = "benchmark_only" if killed else "active"

        print(f"  Kill rule: {'TRIGGERED -> benchmark_only' if killed else 'NOT triggered -> active'}")
        print(f"  Full/2010+ window: MAE model={m_kill_full.get('mae_model')} vs naive={m_kill_full.get('mae_naive')}")
        print(f"  2021+ slice: MAE model={m_2021.get('mae_model')} vs naive={m_2021.get('mae_naive')}")
        print()

        n_eval = len(rows_nfp_eval) if release == "nfp" else len(results)
        summary[release] = {
            "status": status,
            "benchmark_only": killed,
            "n_predictions": len(results),
            "n_eval_predictions": n_eval,  # for NFP: 2010+ only per prereg
            "era_metrics": era_metrics,
        }

    return summary


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt_num(v, digits=4):
    if v is None:
        return "null"
    return f"{v:.{digits}f}"


def _fmt_pct(v):
    if v is None:
        return "null"
    return f"{v*100:.1f}%"


def _fmt_ci(ci):
    if ci is None:
        return "null"
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def render_era_table(era_metrics: dict, release: str) -> str:
    """Render the per-era metrics table as Markdown."""
    if release == "nfp":
        eras = [
            "full_2010_plus", "pre_2010", "2010_2020",
            "covid_months_2020_03_06", "2020_recovery", "2021_plus",
            "2010_2020_excl_covid", "2015_plus_stable_features",
        ]
    elif release == "claims":
        eras = [
            "full", "pre_2010", "2010_2020", "2010_2019_pre_covid",
            "covid_months_2020_03_06", "2020_recovery", "2021_plus",
        ]
    else:
        eras = [
            "full", "pre_2010", "2010_2020", "covid_months_2020_03_06",
            "2020_recovery", "2021_plus", "2015_plus_stable_features",
        ]

    era_labels = {
        "full": "Full",
        "full_2010_plus": "Full (2010+, per prereg)",
        "pre_2010": "pre-2010",
        "2010_2020": "2010–2020-02",
        "2010_2019_pre_covid": "2010–2019 (pre-COVID visibility)",
        "covid_months_2020_03_06": "COVID (2020-03..06)",
        "2020_recovery": "2020-07..12 (recovery gap)",
        "2021_plus": "2021+",
        "2010_2020_excl_covid": "2010–2020-02 (excl. COVID)",
        "2015_plus_stable_features": "2015+ (stable feature set, supplementary)",
    }

    lines = []
    lines.append("| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |")
    lines.append("|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|")

    for era in eras:
        m = era_metrics.get(era, {})
        if not m:
            continue
        label = era_labels.get(era, era)
        row = (
            f"| {label} "
            f"| {m.get('n', 0)} "
            f"| {_fmt_num(m.get('mae_model'))} "
            f"| {_fmt_num(m.get('mae_naive'))} "
            f"| {_fmt_num(m.get('mae_trailing3m'))} "
            f"| {_fmt_num(m.get('mae_ar3'))} "
            f"| {_fmt_num(m.get('rmse_model'))} "
            f"| {_fmt_num(m.get('rmse_naive'))} "
            f"| {_fmt_pct(m.get('coverage_p10_p90'))} "
            f"| {_fmt_num(m.get('skew_hit_rate'), 3)} "
            f"| {_fmt_ci(m.get('skew_wilson_ci'))} "
            f"| {m.get('skew_n', 0)} |"
        )
        lines.append(row)
    return "\n".join(lines)


def generate_results_md(summary: dict) -> str:
    lines = []
    lines.append("# Backtest Results V1 — Macro Release Intelligence")
    lines.append("")
    lines.append("**Run date:** 2026-07-07")
    lines.append("**Spec:** research/release_forecast/PREREG_V1.md (frozen before run)")
    lines.append("**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs")
    lines.append("**Era law:** pre-2010 / 2010-01..2020-02 / COVID 2020-03..06 / 2020-07..12 (recovery gap) / 2021+; NFP COVID printed separately")
    lines.append("**Kill rule:** model MAE >= naive MAE in BOTH full/2010+ AND 2021+ slice -> benchmark_only")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Release | Status | N predictions (total) | N eval predictions |")
    lines.append("|---------|--------|-----------------------|--------------------|")
    for rel, data in summary.items():
        status = data.get("status", "unknown")
        n = data.get("n_predictions", 0)
        n_eval = data.get("n_eval_predictions", n)
        lines.append(f"| {rel} | **{status}** | {n} | {n_eval} |")
    lines.append("")
    lines.append("*NFP n_eval_predictions = 2010+ only per PREREG_V1.md §4.1; pre-2010 NFP rows trained on but not reported in full-window metrics.*")
    lines.append("")

    for rel, data in summary.items():
        status = data.get("status", "unknown")
        killed = data.get("benchmark_only", False)

        lines.append(f"---")
        lines.append(f"## {rel}")
        lines.append(f"")
        lines.append(f"**Status:** {status}")
        if killed:
            lines.append(f"**Kill rule triggered:** model MAE >= naive MAE in full/2010+ window AND 2021+ slice.")
        else:
            lines.append(f"**Kill rule:** NOT triggered. Model beats naive in at least one of: full/2010+ window, 2021+ slice.")
        lines.append(f"**Total predictions:** {data.get('n_predictions', 0)}")
        n_eval = data.get("n_eval_predictions", data.get("n_predictions", 0))
        if rel == "nfp":
            lines.append(f"**Eval predictions (2010+):** {n_eval}")
        lines.append("")

        era_metrics = data.get("era_metrics", {})
        lines.append("### Era-Split Metrics Table")
        lines.append("")
        lines.append("Columns: MAE/RMSE vs model/naive/trailing3m/ar3; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.")
        lines.append("")
        lines.append(render_era_table(era_metrics, rel))
        lines.append("")
        lines.append("**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.")
        lines.append("")

        # Print nulls explicitly
        m_full = era_metrics.get("full_2010_plus") or era_metrics.get("full", {})
        m_2021 = era_metrics.get("2021_plus", {})
        lines.append("### Kill Rule Detail")
        lines.append("")
        full_label = "2010+ window (per prereg)" if rel == "nfp" else "Full window"
        lines.append(f"- {full_label}: MAE model={_fmt_num(m_full.get('mae_model'))} vs naive={_fmt_num(m_full.get('mae_naive'))}")
        lines.append(f"- 2021+ slice: MAE model={_fmt_num(m_2021.get('mae_model'))} vs naive={_fmt_num(m_2021.get('mae_naive'))}")
        lines.append(f"- Kill triggered: {'YES -> benchmark_only' if killed else 'NO -> active'}")
        lines.append("")

    lines.append("---")
    lines.append("## Notes and Deviations")
    lines.append("")
    lines.append("1. **GASREGW absent**: PR-A not merged at backtest time. Gasoline leg dropped for CPI headline (absent_legs=['gasoline_mom']). All CPI headline predictions are made without gasoline feature.")
    lines.append("2. **ADP absent**: PR-A not merged. ADP leg dropped for NFP (absent_legs=['adp_change']).")
    lines.append("3. **Withheld taxes**: data starts 2023-02-14; YoY feature available only from ~2024-02. All NFP predictions before 2024-02 run without this leg.")
    lines.append("4. **AWHMAN revision-optimistic**: uses latest-revised AWHMAN. Declared in provenance.")
    lines.append("5. **Sticky/median/flex CPI and PPI**: absent before 2014-02/03; predictions before this date use only own-lags.")
    lines.append("6. **NFP COVID rows**: 2020-03 through 2020-06 in a separate era row; not assigned to the 2010-2020 reference cell per PREREG_V1.md §6.1 (which ends that era at 2020-02).")
    lines.append("7. **2020-07..12 recovery gap**: PREREG_V1.md §6.1 does not assign 2020-07..2020-12 to any era. These months are reported separately as '2020_recovery'. See AMENDMENTS section of PREREG_V1.md.")
    lines.append("8. **NFP evaluation floor**: per PREREG_V1.md §4.1 'NFP evaluation window starts 2010'. Pre-2010 NFP predictions are EXCLUDED from the NFP full-window metrics ('full_2010_plus' row). Pre-2010 rows still contribute to training.")
    lines.append("9. **Complete-case feature selection — CRITICAL DISCLOSURE**: the model uses complete-case training at each step. After the 2014 feature-onset boundary (sticky/median/flex CPI, PPI legs), pre-2014 training rows are dropped whenever post-2014 features are present in the prediction row. This means: (a) the effective training window for post-2014 predictions is NOT the full expanding window — rows before 2014 with missing features are excluded; (b) pooled residual quantiles mix two feature-set regimes (pre-2014 own-lags-only and post-2014 full-feature). Supplementary coverage computed over predictions with reference month >= 2015-01 (stable feature set) is reported in the era table above as '2015+' rows where data permits.")
    lines.append("10. **Skew hit-rate is CONDITIONAL**: computed only over predictions where the model takes a directional stance vs naive (sign(model-naive) != 0). n_stance (Skew n column) may be substantially smaller than n_total (n column). Both are printed.")
    lines.append("11. **Display-only**: all outputs carry display_only=True, authority=False. No signals or scores originate from this module.")
    lines.append("")
    lines.append("*Pre-registered spec frozen before any results were observed. No weight tuning after seeing results.*")

    return "\n".join(lines)


def main():
    summary = run_backtest()

    # Write JSON
    json_path = _RESULTS_DIR / "backtest_v1_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Written: {json_path}")

    # Write per-step predictions for reproducibility (Fix: metrics recomputable without re-executing)
    root = _REPO
    steps: dict[str, list[dict]] = {}
    for release in ["cpi_headline", "cpi_core", "nfp", "claims"]:
        from engine.release_forecast import run_walk_forward_full
        wf = run_walk_forward_full(release, root)
        results = wf["results"]
        step_rows = []
        for r in results:
            step_rows.append({
                "result_pos": r.get("result_pos"),
                "idx": r.get("idx"),
                "period": str(r.get("period")) if r.get("period") is not None else None,
                "release_date": str(r.get("release_date")) if r.get("release_date") is not None else None,
                "predicted": r.get("predicted"),
                "actual": r.get("actual"),
                "baseline_naive": r.get("baseline_naive"),
                "baseline_trailing3m": r.get("baseline_trailing3m"),
                "baseline_ar3": r.get("baseline_ar3"),
                "n_train": r.get("n_train"),
                "n_features_used": r.get("n_features_used"),
            })
        steps[release] = step_rows
    steps_path = _RESULTS_DIR / "backtest_v1_steps.json"
    with open(steps_path, "w") as f:
        json.dump(steps, f, indent=2, default=str)
    print(f"Written: {steps_path}")

    # Write Markdown
    md = generate_results_md(summary)
    md_path = Path(__file__).resolve().parent / "RESULTS_V1.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Written: {md_path}")

    # Print summary tables to stdout
    print("\n" + "=" * 70)
    print(md)
    print("=" * 70)

    return summary


if __name__ == "__main__":
    main()
