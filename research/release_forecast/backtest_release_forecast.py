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


# ---------------------------------------------------------------------------
# Expanding mean benchmark (MRI-R28b — REPORTED columns, non-binding)
# ---------------------------------------------------------------------------

def _attach_expanding_mean(results: list[dict]) -> None:
    """Annotate each result row with baseline_expanding_mean (no lookahead).

    At prediction step with result_pos=j, expanding_mean = mean of actuals
    from strictly prior result rows (result_pos 0..j-1). This uses only
    data that was in the training window before this prediction was made.
    result_pos=0 -> None (no prior observations in results list).

    Note: this slightly underestimates the true expanding mean of the target
    series because it excludes the burn-in records (indices 0..min_obs-1 that
    were used for training but never produced a prediction). However, it is
    strictly no-lookahead and computable without re-running the engine.
    """
    # Build cumulative sum indexed by result_pos
    # results are assumed sorted by time (ascending result_pos)
    n = len(results)
    cum_sum = 0.0
    cum_count = 0
    # Sort by result_pos to be safe
    sorted_results = sorted(results, key=lambda r: r.get("result_pos", 0))
    for r in sorted_results:
        if cum_count == 0:
            r["baseline_expanding_mean"] = None
        else:
            r["baseline_expanding_mean"] = cum_sum / cum_count
        actual = r.get("actual")
        if actual is not None and not (isinstance(actual, float) and np.isnan(actual)):
            cum_sum += actual
            cum_count += 1


def _compute_metrics(
    rows: list[dict],
    errors_accum: np.ndarray,
    min_q: int = MIN_QUANTILE_OBS,
    trailing_key: str = "baseline_trailing3m",
) -> dict:
    """Compute all metrics for a subset of walk-forward rows.

    trailing_key: 'baseline_trailing3m' for monthly releases, 'baseline_trailing4w' for claims.
    Includes expanding_mean as REPORTED (non-binding) benchmark per MRI-R28b.
    """
    trailing_mae_label = "mae_trailing4w" if trailing_key == "baseline_trailing4w" else "mae_trailing3m"
    trailing_rmse_label = "rmse_trailing4w" if trailing_key == "baseline_trailing4w" else "rmse_trailing3m"

    if not rows:
        return {"n": 0, "mae_model": None, "rmse_model": None,
                "mae_naive": None, "rmse_naive": None,
                trailing_mae_label: None, trailing_rmse_label: None,
                "mae_ar3": None, "rmse_ar3": None,
                "mae_expanding_mean": None, "rmse_expanding_mean": None,
                "coverage_p10_p90": None,
                "skew_hit_rate": None, "skew_wilson_ci": None, "skew_n": 0}

    actuals = [r["actual"] for r in rows]
    preds = [r["predicted"] for r in rows]
    naive_preds = [r["baseline_naive"] for r in rows]
    t3m_preds = [r.get(trailing_key) for r in rows]
    ar3_preds = [r["baseline_ar3"] for r in rows]
    expm_preds = [r.get("baseline_expanding_mean") for r in rows]

    model_errors = [a - p for a, p in zip(actuals, preds) if a is not None and p is not None]
    naive_errors = [a - n for a, n in zip(actuals, naive_preds) if a is not None and n is not None]
    t3m_errors = [a - t for a, t in zip(actuals, t3m_preds) if a is not None and t is not None]
    ar3_errors = [a - b for a, b in zip(actuals, ar3_preds) if a is not None and b is not None]
    expm_errors = [a - e for a, e in zip(actuals, expm_preds) if a is not None and e is not None]

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
        trailing_mae_label: round(_mae(t3m_errors), 4) if _mae(t3m_errors) is not None else None,
        trailing_rmse_label: round(_rmse(t3m_errors), 4) if _rmse(t3m_errors) is not None else None,
        "mae_ar3": round(_mae(ar3_errors), 4) if _mae(ar3_errors) is not None else None,
        "rmse_ar3": round(_rmse(ar3_errors), 4) if _rmse(ar3_errors) is not None else None,
        # REPORTED (non-binding) per MRI-R28b — expanding mean of target's first-print MoM history
        "mae_expanding_mean": round(_mae(expm_errors), 4) if _mae(expm_errors) is not None else None,
        "rmse_expanding_mean": round(_rmse(expm_errors), 4) if _rmse(expm_errors) is not None else None,
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

        # Attach expanding_mean benchmark to each result row (MRI-R28b, no lookahead)
        _attach_expanding_mean(results)

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

        # S2 FIX: claims uses genuine trailing_4w baseline; all others use trailing_3m.
        tkey = "baseline_trailing4w" if release == "claims" else "baseline_trailing3m"

        # Compute metrics per era
        # For full NFP: use 2010+ per prereg (rename "full" to "2010_plus" for NFP)
        if release == "nfp":
            m_full_or_2010plus = _compute_metrics(rows_nfp_eval, errors_accum, trailing_key=tkey)
        else:
            m_full_or_2010plus = _compute_metrics(rows_all, errors_accum, trailing_key=tkey)
        m_pre2010 = _compute_metrics(rows_pre2010, errors_accum, trailing_key=tkey)
        m_2010_2020 = _compute_metrics(rows_2010_2020, errors_accum, trailing_key=tkey)
        m_covid = _compute_metrics(rows_covid, errors_accum, trailing_key=tkey)
        m_2020_recovery = _compute_metrics(rows_2020_recovery, errors_accum, trailing_key=tkey)
        m_2021 = _compute_metrics(rows_2021, errors_accum, trailing_key=tkey)

        # Supplementary: 2015+ rows for stable-feature-set coverage (disclosure fix 9)
        # Reference month >= 2015-01 means sticky/median/flex/PPI features are consistently present
        rows_2015_plus = [
            r for r in rows_all
            if get_period(r) is not None and get_period(r) >= pd.Timestamp("2015-01-01")
        ]
        m_2015_plus = _compute_metrics(rows_2015_plus, errors_accum, trailing_key=tkey)

        if release == "nfp":
            era_metrics = {
                "full_2010_plus": m_full_or_2010plus,  # per-prereg NFP eval starts 2010
                "pre_2010": m_pre2010,
                "2010_2020": m_2010_2020,
                "covid_months_2020_03_06": m_covid,
                "2020_recovery": m_2020_recovery,
                "2021_plus": m_2021,
                "2010_2020_excl_covid": _compute_metrics(rows_2010_2020, errors_accum, trailing_key=tkey),
                "2015_plus_stable_features": m_2015_plus,
            }
        elif release == "claims":
            # Claims: add 2010-2019 pre-COVID visibility slice per task spec.
            rows_2010_2019 = [
                r for r in rows_all
                if get_period(r) is not None
                and get_period(r) >= pd.Timestamp("2010-01-01")
                and get_period(r) < pd.Timestamp("2020-01-01")
            ]
            m_2010_2019 = _compute_metrics(rows_2010_2019, errors_accum, trailing_key=tkey)
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

    # S2: column header and key depend on release
    is_claims_table = release == "claims"
    trail_header = "MAE Trail4w" if is_claims_table else "MAE Trail3m"
    trail_key = "mae_trailing4w" if is_claims_table else "mae_trailing3m"

    lines = []
    lines.append(f"| Era | n | MAE Model | MAE Naive | {trail_header} | MAE AR3 | MAE ExpandMean* | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |")
    lines.append("|-----|---|-----------|-----------|-------------|---------|-----------------|------------|------------|-------------|---------|---------------|--------|")

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
            f"| {_fmt_num(m.get(trail_key))} "
            f"| {_fmt_num(m.get('mae_ar3'))} "
            f"| {_fmt_num(m.get('mae_expanding_mean'))} "
            f"| {_fmt_num(m.get('rmse_model'))} "
            f"| {_fmt_num(m.get('rmse_naive'))} "
            f"| {_fmt_pct(m.get('coverage_p10_p90'))} "
            f"| {_fmt_num(m.get('skew_hit_rate'), 3)} "
            f"| {_fmt_ci(m.get('skew_wilson_ci'))} "
            f"| {m.get('skew_n', 0)} |"
        )
        lines.append(row)
    lines.append("")
    lines.append("\\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history; strictly no-lookahead. Strongest naive = min(MAE Naive, MAE ExpandMean, trailing MAE).")
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
        lines.append("Columns: MAE/RMSE vs model/naive/trailing3m/ar3/expanding_mean*; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.")
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

        # MRI-R28b: vs strongest naive (REPORTED, non-binding)
        trail_key = "mae_trailing4w" if rel == "claims" else "mae_trailing3m"
        def _strongest_naive(m):
            candidates = [m.get("mae_naive"), m.get(trail_key), m.get("mae_expanding_mean")]
            valid = [c for c in candidates if c is not None]
            return min(valid) if valid else None

        sn_full = _strongest_naive(m_full)
        sn_2021 = _strongest_naive(m_2021)
        mae_model_full = m_full.get("mae_model")
        mae_model_2021 = m_2021.get("mae_model")
        lines.append("### Vs Strongest Naive (REPORTED, MRI-R28b — non-binding)")
        lines.append("")
        lines.append(f"Strongest naive = min(naive_prior, trailing3m/4w, expanding_mean).")
        if sn_full is not None and mae_model_full is not None:
            margin_full = sn_full - mae_model_full
            beats_full = margin_full > 0
            lines.append(f"- {full_label}: model MAE={_fmt_num(mae_model_full)} vs strongest_naive={_fmt_num(sn_full)} — margin={_fmt_num(margin_full)} ({'BEATS' if beats_full else 'LAGS'})")
        else:
            lines.append(f"- {full_label}: insufficient data")
        if sn_2021 is not None and mae_model_2021 is not None:
            margin_2021 = sn_2021 - mae_model_2021
            beats_2021 = margin_2021 > 0
            lines.append(f"- 2021+ slice: model MAE={_fmt_num(mae_model_2021)} vs strongest_naive={_fmt_num(sn_2021)} — margin={_fmt_num(margin_2021)} ({'BEATS' if beats_2021 else 'LAGS'})")
        else:
            lines.append(f"- 2021+ slice: insufficient data")
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
    lines.append("12. **expanding_mean benchmark**: REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history, computed at each step from prediction results up to (but not including) the current step. Slightly underestimates the true expanding mean (excludes burn-in records in training that precede the first prediction) but is strictly no-lookahead.")
    lines.append("")
    lines.append("*Pre-registered spec frozen before any results were observed. No weight tuning after seeing results.*")
    lines.append("")
    lines.append("---")
    lines.append("## §12 Restatement (2026-07-10, MRI-R28/R29/R31)")
    lines.append("")
    lines.append("Per MRI-R28 (strongest-naive law):")
    lines.append("- Wave-10 verdicts STAND as frozen — they were honest under the pre-registered rule.")
    lines.append("- The benchmark set now includes `expanding_mean` as a REPORTED (non-binding) column.")
    lines.append("- All §12 new tracks use the STRONGEST naive (min of naive_prior, trailing3m, expanding_mean) as their kill benchmark.")
    lines.append("")
    lines.append("Wave-10 verdict assessment vs strongest naive (see 'Vs Strongest Naive' sections above for exact numbers):")
    lines.append("- **cpi_headline**: champion beat naive_prior in full and 2021+ windows. Expanding_mean may be slightly harder benchmark — see table above.")
    lines.append("- **cpi_core**: champion was borderline vs naive_prior in 2021+. Vs strongest naive: beats in full window (margin=+0.0055) but lags in 2021+ (margin=-0.0089, LAGS). Honesty caveat for cpi_core: model lags expanding_mean in 2021+; verdicts stand. See 'Vs Strongest Naive' section above.")
    lines.append("- **nfp**: champion beat naive in full (2010+) window; check 2021+ vs expanding_mean above.")
    lines.append("- **claims**: see 2021+ vs strongest naive above.")
    lines.append("")
    lines.append("Per MRI-R29 (bridge claim voided): see RESULTS_CPI_BRIDGE_V1.md for bridge restatement.")
    lines.append("Per MRI-R31 (scoring upgrades): skew arm downgraded to DESCRIPTIVE until n>=24; §7 MAE arm unchanged.")

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
            # S2 FIX: for claims, capture baseline_trailing4w (genuine 4-week mean);
            # for all other releases, capture baseline_trailing3m (3-print mean).
            if release == "claims":
                trailing_step = r.get("baseline_trailing4w")
                trailing_step_key = "baseline_trailing4w"
            else:
                trailing_step = r.get("baseline_trailing3m")
                trailing_step_key = "baseline_trailing3m"
            step_rows.append({
                "result_pos": r.get("result_pos"),
                "idx": r.get("idx"),
                "period": str(r.get("period")) if r.get("period") is not None else None,
                "release_date": str(r.get("release_date")) if r.get("release_date") is not None else None,
                "predicted": r.get("predicted"),
                "actual": r.get("actual"),
                "baseline_naive": r.get("baseline_naive"),
                trailing_step_key: trailing_step,
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


# ---------------------------------------------------------------------------
# V2 Backtest (PREREG_V2.md — shelter leg + component upgrade)
# ---------------------------------------------------------------------------
# NOTE: run_walk_forward_full is already V2 (shelter_nowcast in feature_names).
# The V2 backtest re-runs the same walk-forward with the new feature set and
# compares to the V1 summary loaded from backtest_v1_summary.json.


def run_backtest_v2() -> dict:
    """Run V2 backtest for cpi_headline and cpi_core (NFP unchanged).

    The V2 model is already encoded in run_walk_forward_full (shelter_nowcast
    appended to feature_names per PREREG_V2.md §3). This function re-runs the
    walk-forward and computes metrics using the same era classification and kill
    rule as V1, then returns a summary dict with both v1 and v2 metrics for
    the CPI targets.

    NFP is excluded from V2 re-run (owned by parallel agent, unchanged).
    """
    print("=== Macro Release Intelligence: Walk-Forward Backtest V2 ===")
    print("SPEC: research/release_forecast/PREREG_V2.md (frozen before run)\n")
    root = _REPO

    # Load V1 summary for comparison
    v1_path = _RESULTS_DIR / "backtest_v1_summary.json"
    v1_summary: dict[str, Any] = {}
    if v1_path.exists():
        with open(v1_path) as f:
            v1_summary = json.load(f)
    else:
        print("  WARNING: backtest_v1_summary.json not found — V1 comparison unavailable")

    summary_v2: dict[str, Any] = {}

    for release in ["cpi_headline", "cpi_core"]:
        print(f"Running V2 walk-forward: {release} ...")
        from engine.release_forecast import run_walk_forward_full
        wf = run_walk_forward_full(release, root)
        results = wf["results"]
        print(f"  {len(results)} predictions")

        # Attach expanding_mean benchmark (MRI-R28b)
        _attach_expanding_mean(results)

        errors_accum = np.array([r["actual"] - r["predicted"] for r in results])

        def get_period(r):
            p = r.get("period")
            return pd.Timestamp(p) if p is not None else None

        rows_all = [r for r in results if get_period(r) is not None]
        rows_pre2010 = [r for r in rows_all if _era(get_period(r)) == "pre_2010"]
        rows_2010_2020 = [r for r in rows_all if _era(get_period(r)) == "2010_2020"]
        rows_covid = [r for r in rows_all if _era(get_period(r)) == "covid"]
        rows_2020_recovery = [r for r in rows_all if _era(get_period(r)) == "2020_recovery"]
        rows_2021 = [r for r in rows_all if _era(get_period(r)) == "2021_plus"]
        # 2015+ stable feature window — note: shelter available ~2016-01 so 2016+ is more precise
        # but we keep 2015+ label to match V1 supplementary row
        rows_2015_plus = [r for r in rows_all if get_period(r) >= pd.Timestamp("2015-01-01")]
        # 2016+ shelter active: first meaningful shelter window (ZORI history starts 2015-01;
        # lease-reset window M-12..M-6 needs 7 months → first usable M ~ 2016-01)
        rows_2016_plus = [r for r in rows_all if get_period(r) >= pd.Timestamp("2016-01-01")]

        m_full = _compute_metrics(rows_all, errors_accum)
        m_pre2010 = _compute_metrics(rows_pre2010, errors_accum)
        m_2010_2020 = _compute_metrics(rows_2010_2020, errors_accum)
        m_covid = _compute_metrics(rows_covid, errors_accum)
        m_2020_recovery = _compute_metrics(rows_2020_recovery, errors_accum)
        m_2021 = _compute_metrics(rows_2021, errors_accum)
        m_2015_plus = _compute_metrics(rows_2015_plus, errors_accum)
        m_2016_plus = _compute_metrics(rows_2016_plus, errors_accum)

        killed = _check_kill_rule(m_full, m_2021)
        status = "benchmark_only" if killed else "active"

        print(f"  Kill rule V2: {'TRIGGERED -> benchmark_only' if killed else 'NOT triggered -> active'}")
        print(f"  Full: MAE model={m_full.get('mae_model')} vs naive={m_full.get('mae_naive')}")
        print(f"  2021+: MAE model={m_2021.get('mae_model')} vs naive={m_2021.get('mae_naive')}")

        # Count shelter-leg predictions (M4 fix: count shelter_nowcast presence directly
        # from the feature row flag, not via n_features_used proxy which conflates
        # shelter presence with other feature availability changes).
        n_with_shelter = sum(
            1 for r in rows_all
            if r.get("shelter_nowcast_present", False)
        )
        print(f"  Predictions with shelter_nowcast active: {n_with_shelter} / {len(rows_all)}")
        print()

        era_metrics_v2 = {
            "full": m_full,
            "pre_2010": m_pre2010,
            "2010_2020": m_2010_2020,
            "covid_months_2020_03_06": m_covid,
            "2020_recovery": m_2020_recovery,
            "2021_plus": m_2021,
            "2015_plus_stable_features": m_2015_plus,
            "2016_plus_shelter_active": m_2016_plus,
        }

        summary_v2[release] = {
            "status": status,
            "benchmark_only": killed,
            "n_predictions": len(results),
            "n_eval_predictions": len(results),
            "n_with_shelter_active": n_with_shelter,
            "era_metrics": era_metrics_v2,
            "v1_era_metrics": v1_summary.get(release, {}).get("era_metrics", {}),
        }

    return summary_v2


def generate_results_v2_md(summary_v2: dict) -> str:
    """Generate RESULTS_V2.md with V1-vs-V2 comparison tables."""
    import datetime as _dt
    today = _dt.date.today().isoformat()

    lines = []
    lines.append("# Backtest Results V2 — MRI CPI Component Upgrade (Shelter Leg)")
    lines.append("")
    lines.append(f"**Run date:** {today}")
    lines.append("**Spec:** research/release_forecast/PREREG_V2.md (frozen before run)")
    lines.append("**Changes vs V1:** shelter_nowcast leg added to cpi_headline (feature 9) and cpi_core (feature 8).")
    lines.append("**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs — UNCHANGED")
    lines.append("**Kill rule:** model MAE >= naive MAE in BOTH full AND 2021+ slice -> benchmark_only — UNCHANGED")
    lines.append("**NFP:** unchanged from V1 — not re-run.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Release | Status | N predictions | N with shelter active |")
    lines.append("|---------|--------|---------------|-----------------------|")
    for rel, data in summary_v2.items():
        status = data.get("status", "unknown")
        n = data.get("n_predictions", 0)
        n_shelter = data.get("n_with_shelter_active", 0)
        lines.append(f"| {rel} | **{status}** | {n} | {n_shelter} |")
    lines.append("")

    for rel, data in summary_v2.items():
        status = data.get("status", "unknown")
        killed = data.get("benchmark_only", False)
        era_v2 = data.get("era_metrics", {})
        era_v1 = data.get("v1_era_metrics", {})

        lines.append(f"---")
        lines.append(f"## {rel}")
        lines.append("")
        lines.append(f"**V2 Status:** {status}")
        if killed:
            lines.append("**Kill rule V2 TRIGGERED:** model MAE >= naive MAE in full AND 2021+ slice. TARGET IS NOW BENCHMARK_ONLY. No v3.")
        else:
            lines.append("**Kill rule V2:** NOT triggered. Model beats naive in at least one window.")
        lines.append(f"**Total predictions:** {data.get('n_predictions', 0)}")
        lines.append(f"**Predictions with shelter active:** {data.get('n_with_shelter_active', 0)}")
        lines.append("")

        lines.append("### V2 Era-Split Metrics")
        lines.append("")
        lines.append(render_era_table(era_v2, rel))
        lines.append("")

        lines.append("### V1 vs V2 Comparison Table")
        lines.append("")
        lines.append("Key question: does the shelter leg fix cpi_core's 2021+ loss to naive (V1: MAE model=0.1355 vs naive=0.1297)?")
        lines.append("")
        lines.append("| Era | n | MAE_v1 | MAE_v2 | MAE_naive | Cov_v1 | Cov_v2 | Skew_HR_v1 | Skew_HR_v2 |")
        lines.append("|-----|---|--------|--------|-----------|--------|--------|------------|------------|")

        era_order = ["full", "pre_2010", "2010_2020", "2021_plus", "2015_plus_stable_features", "2016_plus_shelter_active"]
        era_labels = {
            "full": "Full",
            "pre_2010": "pre-2010",
            "2010_2020": "2010–2020-02",
            "2021_plus": "2021+",
            "2015_plus_stable_features": "2015+ (stable feature set)",
            "2016_plus_shelter_active": "2016+ (shelter active)",
        }
        for era in era_order:
            mv1 = era_v1.get(era, {})
            mv2 = era_v2.get(era, {})
            if not mv2:
                continue
            n = mv2.get("n", 0)
            mae_v1 = _fmt_num(mv1.get("mae_model")) if mv1 else "—"
            mae_v2 = _fmt_num(mv2.get("mae_model"))
            mae_naive = _fmt_num(mv2.get("mae_naive"))
            cov_v1 = _fmt_pct(mv1.get("coverage_p10_p90")) if mv1 else "—"
            cov_v2 = _fmt_pct(mv2.get("coverage_p10_p90"))
            shr_v1 = _fmt_num(mv1.get("skew_hit_rate"), 3) if mv1 else "—"
            shr_v2 = _fmt_num(mv2.get("skew_hit_rate"), 3)
            label = era_labels.get(era, era)
            lines.append(f"| {label} | {n} | {mae_v1} | {mae_v2} | {mae_naive} | {cov_v1} | {cov_v2} | {shr_v1} | {shr_v2} |")
        lines.append("")

        m_full = era_v2.get("full", {})
        m_2021 = era_v2.get("2021_plus", {})
        lines.append("### Kill Rule Detail (V2)")
        lines.append("")
        lines.append(f"- Full window: MAE model={_fmt_num(m_full.get('mae_model'))} vs naive={_fmt_num(m_full.get('mae_naive'))}")
        lines.append(f"- 2021+ slice: MAE model={_fmt_num(m_2021.get('mae_model'))} vs naive={_fmt_num(m_2021.get('mae_naive'))}")
        lines.append(f"- Kill triggered: {'YES -> benchmark_only (NO V3)' if killed else 'NO -> active'}")
        lines.append("")

        # Primary question: cpi_core 2021+ verdict
        if rel == "cpi_core":
            m_2021_v1_mae = era_v1.get("2021_plus", {}).get("mae_model")
            m_2021_v2_mae = m_2021.get("mae_model")
            m_2021_naive = m_2021.get("mae_naive")
            lines.append("### cpi_core 2021+ VERDICT (primary question)")
            lines.append("")
            lines.append(f"- V1 MAE model (2021+): {_fmt_num(m_2021_v1_mae)}")
            lines.append(f"- V2 MAE model (2021+): {_fmt_num(m_2021_v2_mae)}")
            lines.append(f"- Naive MAE (2021+): {_fmt_num(m_2021_naive)}")
            if m_2021_v2_mae is not None and m_2021_naive is not None:
                if m_2021_v2_mae < m_2021_naive:
                    lines.append(f"- **VERDICT: FIXED** — shelter leg fixes cpi_core's 2021+ loss to naive.")
                    lines.append(f"  V2 beats naive: {_fmt_num(m_2021_v2_mae)} < {_fmt_num(m_2021_naive)} (improvement of {_fmt_num(m_2021_naive - m_2021_v2_mae)} pp MAE).")
                else:
                    delta = m_2021_v2_mae - m_2021_v1_mae if m_2021_v1_mae else None
                    lines.append(f"- **VERDICT: NOT FIXED** — cpi_core still loses to naive in 2021+.")
                    lines.append(f"  V2 MAE {_fmt_num(m_2021_v2_mae)} vs naive {_fmt_num(m_2021_naive)}.")
                    if delta is not None:
                        direction = "improved" if delta < 0 else "worsened"
                        lines.append(f"  Change vs V1: {_fmt_num(abs(delta))} pp {direction}.")
                    if killed:
                        lines.append("  Kill rule triggered (both full+2021+ lose). cpi_core is BENCHMARK_ONLY. No v3.")
            lines.append("")

    lines.append("---")
    lines.append("## Data Sources Used in V2")
    lines.append("")
    lines.append("- **ZORI:** `data/zori/national.parquet` (fetched by `scripts/collect_zori.py`)")
    lines.append("  - History: 2015-01-31 through latest available (137 months as of 2026-07-07)")
    lines.append("  - PIT lag: 45 days conservative (PREREG_V2.md §1.1)")
    lines.append("  - Revision status: revision_optimistic (Zillow re-benchmarks periodically)")
    lines.append("  - Knowability: ZORI for month M is usable at decision date D if M_end_of_month + 45 days <= D")
    lines.append("")
    lines.append("- **CPI Shelter (CUSR0000SAH1):** `data/fred/CUSR0000SAH1.parquet`")
    lines.append("  - Latest-revised (not ALFRED-vintaged) — declared revision_optimistic")
    lines.append("  - Full history available from 1947-01")
    lines.append("")
    lines.append("- **Shelter nowcast:** (1-k)*cpi_shelter_mom_last + k*zori_signal, k=0.35 frozen")
    lines.append("  - Divergence guard: k halved to 0.175 when |zori_signal - cpi_shelter_mom| > 3*sigma_24m")
    lines.append("  - First usable in predictions: ~2016-01 (when ZORI lease-reset window M-12..M-6 has data)")
    lines.append("")
    lines.append("*Pre-registered spec frozen before any results were observed. Anti-mining: 2 of 2 attempts used.*")
    lines.append("")
    lines.append("---")
    lines.append("## §12 Restatement (2026-07-10, MRI-R28b)")
    lines.append("")
    lines.append("expanding_mean benchmark added to era tables above (REPORTED, non-binding per MRI-R28b).")
    lines.append("V2 verdicts stand as frozen. All §12 new tracks use the STRONGEST naive as kill benchmark.")
    lines.append("See RESULTS_V1.md §12 Restatement for per-target vs-strongest-naive detail.")

    return "\n".join(lines)


def main_v2() -> dict:
    """Run V2 backtest for CPI targets only and write results."""
    summary_v2 = run_backtest_v2()

    # Write JSON
    json_path = _RESULTS_DIR / "backtest_v2_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary_v2, f, indent=2, default=str)
    print(f"Written: {json_path}")

    # Write Markdown
    md = generate_results_v2_md(summary_v2)
    md_path = Path(__file__).resolve().parent / "RESULTS_V2.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"Written: {md_path}")

    print("\n" + "=" * 70)
    print(md)
    print("=" * 70)

    return summary_v2


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(description="MRI walk-forward backtest")
    _parser.add_argument("--v2", action="store_true", help="Run V2 CPI backtest (shelter leg)")
    _args = _parser.parse_args()
    if _args.v2:
        main_v2()
    else:
        main()
