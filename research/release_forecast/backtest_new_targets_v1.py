"""MRI Track N — Walk-Forward Backtest V1 (PCE Headline, PCE Core, PPI Final Demand).

Runs the frozen walk-forward for the three modelled Track N targets.
retail_sales is SCAFFOLD-ONLY (no_data) — not backtested here.

SPECIFICATION: research/release_forecast/PREREG_NEW_TARGETS_V1.md (frozen 2026-07-08)
Governing ruling: MRI-R23 (§11.1 of research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md)

Era splits: pre_2010 / 2010_2020 / covid (2020-03..06) / 2020_recovery / 2021_plus
Metrics: MAE + RMSE vs each baseline (naive_prior, trailing_3m, ar3) per era
Coverage: p10-p90 interval hit rate
Skew hit-rate + Wilson 95% CI
Kill rule: model MAE >= naive MAE in BOTH full AND 2021+ -> benchmark_only (KILLED)
COVID months excluded from era stats (printed separately)

PPI THIN-HISTORY CAVEAT: PPIFIS vintage starts 2014-02; first walk-forward prediction
approximately 2019-02; approximately 90 total and 50-60 2021+ predictions.

Writes:
  research/release_forecast/results/backtest_new_targets_v1_summary.json
  research/release_forecast/RESULTS_NEW_TARGETS_V1.md

Usage:
  python research/release_forecast/backtest_new_targets_v1.py
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
)
from engine.release_targets_v11 import (  # noqa: E402
    build_wf_pce_headline,
    build_wf_pce_core,
    build_wf_ppi_finaldemand,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_RESULTS_MD = Path(__file__).resolve().parent / "RESULTS_NEW_TARGETS_V1.md"


# ---------------------------------------------------------------------------
# Era classification (identical to backtest_release_forecast.py)
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


def _is_covid(period: pd.Timestamp) -> bool:
    return (period.year, period.month) in COVID_MONTHS


# ---------------------------------------------------------------------------
# Metrics (identical protocol to champion backtest)
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


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if not n:
        return None
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


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
    n_valid = len(valid)
    rate = round(hits / n_valid, 4)
    ci = _wilson(hits, n_valid)
    return rate, ci, n_valid


def _compute_metrics(
    rows: list[dict],
    errors_accum: np.ndarray,
    min_q: int = MIN_QUANTILE_OBS,
) -> dict:
    """Compute all metrics for a subset of walk-forward rows."""
    if not rows:
        return {
            "n": 0,
            "mae_model": None, "rmse_model": None,
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
    ar3_preds = [r["baseline_ar3"] for r in rows]

    model_errors = [a - p for a, p in zip(actuals, preds) if a is not None and p is not None]
    naive_errors = [a - n for a, n in zip(actuals, naive_preds) if a is not None and n is not None]
    t3m_errors = [a - t for a, t in zip(actuals, t3m_preds) if a is not None and t is not None]
    ar3_errors = [a - b for a, b in zip(actuals, ar3_preds) if a is not None and b is not None]

    # Quantile intervals from expanding residual history (use result_pos, not idx)
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
    """True = kill (model MAE >= naive MAE in BOTH full AND 2021+ slice)."""
    mae_m_full = metrics_full.get("mae_model")
    mae_n_full = metrics_full.get("mae_naive")
    mae_m_2021 = metrics_2021.get("mae_model")
    mae_n_2021 = metrics_2021.get("mae_naive")

    if mae_m_full is None or mae_n_full is None:
        return False  # insufficient data
    if mae_m_2021 is None or mae_n_2021 is None:
        return False

    return (mae_m_full >= mae_n_full) and (mae_m_2021 >= mae_n_2021)


# ---------------------------------------------------------------------------
# Per-target backtest runner
# ---------------------------------------------------------------------------

def _run_one_target(release: str, wf: dict) -> dict:
    """Run era breakdown and metrics for one target's walk-forward output."""
    results = wf["results"]
    metadata = wf.get("metadata", {})
    print(f"  {len(results)} predictions")

    if not results:
        return {
            "release": release,
            "n_predictions": 0,
            "era_metrics": {},
            "kill_rule": "INSUFFICIENT_DATA",
            "verdict": "INSUFFICIENT_DATA",
            "metadata": metadata,
        }

    errors_accum = np.array([r["actual"] - r["predicted"] for r in results])

    def get_period(r: dict) -> pd.Timestamp | None:
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

    m_full = _compute_metrics(rows_all, errors_accum)
    m_pre2010 = _compute_metrics(rows_pre2010, errors_accum)
    m_2010_2020 = _compute_metrics(rows_2010_2020, errors_accum)
    m_covid = _compute_metrics(rows_covid, errors_accum)
    m_2020_recovery = _compute_metrics(rows_2020_recovery, errors_accum)
    m_2021 = _compute_metrics(rows_2021, errors_accum)

    killed = _check_kill_rule(m_full, m_2021)
    kill_label = "KILLED" if killed else "PASS"
    verdict = "BENCHMARK_ONLY" if killed else "MODEL"

    era_metrics = {
        "full": m_full,
        "pre_2010": m_pre2010,
        "2010_2020": m_2010_2020,
        "covid_months_2020_03_06": m_covid,
        "2020_recovery": m_2020_recovery,
        "2021_plus": m_2021,
    }

    return {
        "release": release,
        "n_predictions": len(results),
        "era_metrics": era_metrics,
        "kill_rule": kill_label,
        "verdict": verdict,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Markdown table helpers
# ---------------------------------------------------------------------------

def _fmt(v: float | None, decimals: int = 4) -> str:
    if v is None:
        return "null"
    return f"{v:.{decimals}f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "null"
    return f"{v:.1%}"


def _era_table_md(era_metrics: dict, release: str) -> str:
    header = (
        "| Era | n | MAE model | MAE naive | MAE t3m | MAE AR3 | "
        "RMSE model | RMSE naive | Coverage p10-p90 | Skew HR | Skew CI | Skew n |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = []
    era_order = ["full", "pre_2010", "2010_2020", "covid_months_2020_03_06",
                 "2020_recovery", "2021_plus"]
    for era in era_order:
        if era not in era_metrics:
            continue
        m = era_metrics[era]
        era_label = era.replace("_", " ")
        ci = m.get("skew_wilson_ci")
        ci_str = f"[{ci[0]:.3f},{ci[1]:.3f}]" if ci else "null"
        rows.append(
            f"| {era_label} | {m['n']} | {_fmt(m['mae_model'])} | {_fmt(m['mae_naive'])} | "
            f"{_fmt(m['mae_trailing3m'])} | {_fmt(m['mae_ar3'])} | "
            f"{_fmt(m['rmse_model'])} | {_fmt(m['rmse_naive'])} | "
            f"{_fmt(m['coverage_p10_p90'])} | {_fmt(m['skew_hit_rate'])} | "
            f"{ci_str} | {m.get('skew_n', 0)} |"
        )
    return header + "\n".join(rows)


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest() -> dict:
    print("=== MRI Track N — Walk-Forward Backtest V1 ===\n")
    root = _REPO
    summary: dict[str, Any] = {}
    target_configs = [
        ("pce_headline", build_wf_pce_headline),
        ("pce_core", build_wf_pce_core),
        ("ppi_finaldemand", build_wf_ppi_finaldemand),
    ]

    for release, wf_fn in target_configs:
        print(f"\nRunning walk-forward: {release} ...")
        wf = wf_fn(root)
        result = _run_one_target(release, wf)
        summary[release] = result
        print(f"  Verdict: {result['verdict']} (kill rule: {result['kill_rule']})")
        m_full = result["era_metrics"].get("full", {})
        m_2021 = result["era_metrics"].get("2021_plus", {})
        print(f"  Full:   MAE model={_fmt(m_full.get('mae_model'))} vs naive={_fmt(m_full.get('mae_naive'))} (n={m_full.get('n', 0)})")
        print(f"  2021+:  MAE model={_fmt(m_2021.get('mae_model'))} vs naive={_fmt(m_2021.get('mae_naive'))} (n={m_2021.get('n', 0)})")

    # retail_sales: scaffold-only, print status
    summary["retail_sales"] = {
        "release": "retail_sales",
        "n_predictions": 0,
        "era_metrics": {},
        "kill_rule": "NOT_APPLICABLE",
        "verdict": "SCAFFOLD_ONLY_NO_DATA",
        "metadata": {
            "reason": "RSAFS data absent from disk as of 2026-07-08. Attempt clock has not started.",
        },
    }
    print("\nretail_sales: SCAFFOLD-ONLY — RSAFS absent, no backtest run, attempt clock not started.")

    # Write JSON summary
    json_path = _RESULTS_DIR / "backtest_new_targets_v1_summary.json"
    # Convert any numpy types for JSON serialization
    def _jsonify(obj: Any) -> Any:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    def _deep_jsonify(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _deep_jsonify(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_deep_jsonify(v) for v in obj]
        return _jsonify(obj)

    with open(json_path, "w") as f:
        json.dump(_deep_jsonify(summary), f, indent=2, default=str)
    print(f"\nJSON summary written: {json_path}")

    # Write Markdown results
    _write_results_md(summary)
    print(f"Markdown results written: {_RESULTS_MD}")

    return summary


def _write_results_md(summary: dict) -> None:
    lines: list[str] = []
    lines.append("# MRI Track N — Walk-Forward Backtest Results V1")
    lines.append("")
    lines.append("**Generated:** 2026-07-08")
    lines.append("**Spec:** research/release_forecast/PREREG_NEW_TARGETS_V1.md (frozen before results)")
    lines.append("**Ruling:** MRI-R23 (§11.1 of masterplan)")
    lines.append("")
    lines.append("Anti-mining: spec frozen in PREREG_NEW_TARGETS_V1.md BEFORE this backtest was run.")
    lines.append("No model or feature changes may be made after observing these results.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Summary Table")
    lines.append("")
    lines.append("| Target | n_predictions | Full MAE model | Full MAE naive | 2021+ MAE model | 2021+ MAE naive | Kill rule | VERDICT |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for release, res in summary.items():
        m_full = res["era_metrics"].get("full", {})
        m_2021 = res["era_metrics"].get("2021_plus", {})
        lines.append(
            f"| {release} | {res['n_predictions']} | "
            f"{_fmt(m_full.get('mae_model'))} | {_fmt(m_full.get('mae_naive'))} | "
            f"{_fmt(m_2021.get('mae_model'))} | {_fmt(m_2021.get('mae_naive'))} | "
            f"{res['kill_rule']} | **{res['verdict']}** |"
        )
    lines.append("")
    lines.append("Kill rule: KILLED = model MAE >= naive MAE in BOTH full AND 2021+ -> BENCHMARK_ONLY.")
    lines.append("COVID months (2020-03..06) excluded from era stats.")
    lines.append("")
    lines.append("---")
    lines.append("")

    for release in ["pce_headline", "pce_core", "ppi_finaldemand", "retail_sales"]:
        res = summary.get(release, {})
        lines.append(f"## {release}")
        lines.append("")
        verdict = res.get("verdict", "UNKNOWN")
        kill = res.get("kill_rule", "UNKNOWN")
        lines.append(f"**Verdict: {verdict}** (kill rule: {kill})")
        lines.append("")

        if release == "retail_sales":
            lines.append(
                "SCAFFOLD-ONLY. RSAFS data is absent from disk as of 2026-07-08. "
                "No backtest was run. The attempt clock (#1 of 2) has not started. "
                "Projection emits `no_data_rsafs_absent`. Machinery ships so that "
                "when data accrues the model can be specified and run."
            )
            lines.append("")
            continue

        if release == "ppi_finaldemand":
            lines.append(
                "**THIN-HISTORY CAVEAT:** PPIFIS vintage history starts 2014-02. "
                "After the 60-observation burn-in, the first walk-forward prediction "
                "is approximately 2019-02, yielding approximately 90 total predictions "
                "and approximately 50-60 in the 2021+ era. Statistics are informative "
                "but thin-history confidence is reduced. Kill rule applied as written."
            )
            lines.append("")

        m_full = res["era_metrics"].get("full", {})
        m_2021 = res["era_metrics"].get("2021_plus", {})
        lines.append(
            f"Full window: MAE model={_fmt(m_full.get('mae_model'))} vs "
            f"naive={_fmt(m_full.get('mae_naive'))} vs "
            f"trailing3m={_fmt(m_full.get('mae_trailing3m'))} vs "
            f"AR3={_fmt(m_full.get('mae_ar3'))} (n={m_full.get('n', 0)})"
        )
        lines.append(
            f"2021+ era: MAE model={_fmt(m_2021.get('mae_model'))} vs "
            f"naive={_fmt(m_2021.get('mae_naive'))} vs "
            f"trailing3m={_fmt(m_2021.get('mae_trailing3m'))} vs "
            f"AR3={_fmt(m_2021.get('mae_ar3'))} (n={m_2021.get('n', 0)})"
        )
        lines.append("")
        lines.append("### Era Breakdown")
        lines.append("")
        lines.append(_era_table_md(res["era_metrics"], release))
        lines.append("")

        # Coverage note
        cov_full = m_full.get("coverage_p10_p90")
        if cov_full is not None:
            lines.append(f"Full p10-p90 coverage: {_fmt_pct(cov_full)} (target: ~80%)")
        cov_2021 = m_2021.get("coverage_p10_p90")
        if cov_2021 is not None:
            lines.append(f"2021+ p10-p90 coverage: {_fmt_pct(cov_2021)} (target: ~80%)")
        lines.append("")

        # Skew hit rate note
        shr = m_full.get("skew_hit_rate")
        sci = m_full.get("skew_wilson_ci")
        sn = m_full.get("skew_n", 0)
        if shr is not None and sn > 0:
            ci_str = f"[{sci[0]:.3f},{sci[1]:.3f}]" if sci else "null"
            lines.append(f"Full skew hit-rate: {shr:.1%} (Wilson 95%: {ci_str}, n={sn})")
        lines.append("")

        if res.get("metadata", {}).get("thin_history"):
            lines.append(f"_Thin-history caveat: {res['metadata'].get('thin_history_caveat', '')}_")
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- All outputs are display_only=True, authority=False.")
    lines.append("- Nulls are printed, not hidden (MRI-R19).")
    lines.append("- sticky/median/flex CPI sourced from ALFRED first-prints (PIT fix 2026-07-08); GASREGW declared unrevised in provenance.")
    lines.append("- PPI thin history: kill rule applied as written; no relaxation for thin history.")
    lines.append("- Round 2 will wire surviving targets into engine/release_forecast.py dispatch.")
    lines.append("")

    with open(_RESULTS_MD, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    run_backtest()
