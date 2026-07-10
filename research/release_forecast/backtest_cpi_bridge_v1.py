"""CPI Component Bridge Backtest — Track CB, MRI-R25.

Walk-forward evaluation of engine/release_cpi_bridge.py vs:
  - naive_prior (last own-series MoM)
  - trailing_3m (3-month mean)
  - champion ridge (v2, from existing run_walk_forward_full)

Era splits per §11.1 / PREREG_V1.md:
  pre_2010: 1997-01..2009-12
  2010_2020: 2010-01..2020-02
  2021_plus: 2021-01..latest
  COVID: 2020-03..2020-06 (excluded from era stats, shown separately)

Kill rule (frozen): bridge MAE >= naive MAE in BOTH full AND 2021+ → NOT SHADOWED.
No weight/block iteration after results (anti-mining §6).

Writes:
  research/release_forecast/results/backtest_cpi_bridge_v1.json
  research/release_forecast/RESULTS_CPI_BRIDGE_V1.md

Usage:
  python research/release_forecast/backtest_cpi_bridge_v1.py
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

from engine.release_cpi_bridge import run_bridge_walk_forward  # noqa: E402
from engine.release_forecast import run_walk_forward_full, COVID_MONTHS  # noqa: E402

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Era classification (same as backtest_release_forecast.py)
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
# Metrics
# ---------------------------------------------------------------------------

def _mae(errors: list[float]) -> float | None:
    if not errors:
        return None
    return float(np.mean(np.abs(errors)))


def _rmse(errors: list[float]) -> float | None:
    if not errors:
        return None
    return float(np.sqrt(np.mean(np.array(errors) ** 2)))


def _compute_metrics(rows: list[dict]) -> dict:
    """Compute MAE/RMSE for bridge vs naive vs trailing3m."""
    if not rows:
        return {
            "n": 0,
            "mae_bridge": None, "rmse_bridge": None,
            "mae_naive": None, "rmse_naive": None,
            "mae_trailing3m": None, "rmse_trailing3m": None,
        }
    actuals = [r["actual"] for r in rows]
    preds = [r["predicted"] for r in rows]
    naives = [r["baseline_naive"] for r in rows if r.get("baseline_naive") is not None]
    t3ms = [r["baseline_trailing3m"] for r in rows if r.get("baseline_trailing3m") is not None]

    valid_bridge = [(p - a) for p, a in zip(preds, actuals)
                    if p is not None and a is not None]
    valid_naive = [(n - a) for n, a in zip(
        [r["baseline_naive"] for r in rows],
        actuals,
    ) if r.get("baseline_naive") is not None and r["actual"] is not None]
    valid_t3m = [(t - a) for t, a in zip(
        [r["baseline_trailing3m"] for r in rows],
        actuals,
    ) if r.get("baseline_trailing3m") is not None and r["actual"] is not None]

    return {
        "n": len(valid_bridge),
        "n_naive": len(valid_naive),
        "n_trailing3m": len(valid_t3m),
        "mae_bridge": _mae(valid_bridge),
        "rmse_bridge": _rmse(valid_bridge),
        "mae_naive": _mae(valid_naive),
        "rmse_naive": _rmse(valid_naive),
        "mae_trailing3m": _mae(valid_t3m),
        "rmse_trailing3m": _rmse(valid_t3m),
    }


# ---------------------------------------------------------------------------
# Expanding mean benchmark (MRI-R28b — REPORTED columns, non-binding)
# ---------------------------------------------------------------------------

def _attach_expanding_mean_bridge(aligned: list[dict]) -> None:
    """Annotate aligned bridge rows with baseline_expanding_mean (no lookahead).

    aligned rows are sorted by period. At row j, expanding_mean = mean of actuals[0:j].
    For j=0, expanding_mean is None.
    """
    cum_sum = 0.0
    cum_count = 0
    for r in aligned:
        if cum_count == 0:
            r["baseline_expanding_mean"] = None
        else:
            r["baseline_expanding_mean"] = cum_sum / cum_count
        actual = r.get("actual")
        if actual is not None:
            cum_sum += actual
            cum_count += 1


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest(release: str, root: Path) -> dict:
    """Run walk-forward for bridge + champion, compare metrics."""
    print(f"\n{'='*60}")
    print(f"Track CB backtest: {release}")
    print(f"{'='*60}")

    # Bridge walk-forward
    print("Running bridge walk-forward...")
    bridge_wf = run_bridge_walk_forward(release, root)
    bridge_results = bridge_wf["results"]
    print(f"  Bridge steps computed: {len(bridge_results)}")

    if not bridge_results:
        print("  ERROR: no bridge results")
        return {"error": "no_bridge_results"}

    # Champion walk-forward (existing engine)
    print("Running champion walk-forward...")
    champ_wf = run_walk_forward_full(release, root)
    champ_results = champ_wf["results"]
    print(f"  Champion steps computed: {len(champ_results)}")

    # Build period-keyed dicts for alignment
    def _period_key(r: dict) -> str:
        p = r.get("period")
        if p is None:
            return ""
        return pd.Timestamp(p).strftime("%Y-%m")

    bridge_by_period = {_period_key(r): r for r in bridge_results}
    champ_by_period = {_period_key(r): r for r in champ_results}

    # Align: only periods where BOTH have results
    common_periods = sorted(set(bridge_by_period) & set(champ_by_period))
    print(f"  Aligned periods: {len(common_periods)}")

    # Build aligned rows
    aligned: list[dict] = []
    for p in common_periods:
        br = bridge_by_period[p]
        cr = champ_by_period[p]
        period_ts = pd.Timestamp(br["period"])
        aligned.append({
            "period": br["period"],
            "period_key": p,
            "era": _era(period_ts),
            "is_covid": _is_covid(period_ts),
            # Bridge
            "bridge_predicted": br["predicted"],
            "actual": br["actual"],
            "baseline_naive": br.get("baseline_naive"),
            "baseline_trailing3m": br.get("baseline_trailing3m"),
            "weight_coverage": br.get("weight_coverage"),
            # Champion
            "champ_predicted": cr["predicted"],
        })

    # Attach expanding_mean to aligned rows (MRI-R28b)
    _attach_expanding_mean_bridge(aligned)

    # Slice by era (exclude COVID from era stats)
    def _slice(era_label: str) -> list[dict]:
        return [r for r in aligned if r["era"] == era_label and not r["is_covid"]]

    covid_rows = [r for r in aligned if r["is_covid"]]
    full_rows = [r for r in aligned if not r["is_covid"] and r["era"] != "2020_recovery"]

    slices = {
        "full": full_rows,
        "pre_2010": _slice("pre_2010"),
        "2010_2020": _slice("2010_2020"),
        "2021_plus": _slice("2021_plus"),
        "covid_separate": covid_rows,
    }

    # Compute bridge metrics per slice
    def _bridge_metrics(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0, "mae_bridge": None, "rmse_bridge": None,
                    "mae_naive": None, "rmse_naive": None,
                    "mae_trailing3m": None, "rmse_trailing3m": None,
                    "mae_champ": None, "rmse_champ": None,
                    "mae_expanding_mean": None}
        bridge_errors = [r["bridge_predicted"] - r["actual"]
                         for r in rows if r.get("bridge_predicted") is not None]
        naive_errors = [r["baseline_naive"] - r["actual"]
                        for r in rows if r.get("baseline_naive") is not None]
        t3m_errors = [r["baseline_trailing3m"] - r["actual"]
                      for r in rows if r.get("baseline_trailing3m") is not None]
        champ_errors = [r["champ_predicted"] - r["actual"]
                        for r in rows if r.get("champ_predicted") is not None]
        expm_errors = [r["baseline_expanding_mean"] - r["actual"]
                       for r in rows
                       if r.get("baseline_expanding_mean") is not None and r.get("actual") is not None]
        return {
            "n": len(bridge_errors),
            "mae_bridge": _mae(bridge_errors),
            "rmse_bridge": _rmse(bridge_errors),
            "mae_naive": _mae(naive_errors),
            "rmse_naive": _rmse(naive_errors),
            "mae_trailing3m": _mae(t3m_errors),
            "rmse_trailing3m": _rmse(t3m_errors),
            "mae_champ": _mae(champ_errors),
            "rmse_champ": _rmse(champ_errors),
            # REPORTED (non-binding) per MRI-R28b
            "mae_expanding_mean": _mae(expm_errors),
        }

    era_stats: dict[str, dict] = {}
    for label, rows in slices.items():
        era_stats[label] = _bridge_metrics(rows)

    # Weight coverage summary
    wc_values = [r["weight_coverage"] for r in aligned
                 if r.get("weight_coverage") is not None]
    wc_pct = float(np.mean(wc_values)) * 100 if wc_values else None

    # Kill rule: bridge MAE >= naive MAE in BOTH full AND 2021+
    full_m = era_stats["full"]
    plus_m = era_stats["2021_plus"]
    bridge_mae_full = full_m.get("mae_bridge")
    naive_mae_full = full_m.get("mae_naive")
    bridge_mae_2021 = plus_m.get("mae_bridge")
    naive_mae_2021 = plus_m.get("mae_naive")

    kill_full = (bridge_mae_full is not None and naive_mae_full is not None
                 and bridge_mae_full >= naive_mae_full)
    kill_2021 = (bridge_mae_2021 is not None and naive_mae_2021 is not None
                 and bridge_mae_2021 >= naive_mae_2021)
    kill_rule_triggered = kill_full and kill_2021

    if kill_rule_triggered:
        verdict = "NULL — kill rule triggered (MAE >= naive in BOTH full AND 2021+). NOT SHADOWED."
    else:
        verdict = "SHADOW-ELIGIBLE — bridge beats naive in at least one required slice."

    result = {
        "release": release,
        "model": "cpi_bridge",
        "n_bridge_steps": len(bridge_results),
        "n_champ_steps": len(champ_results),
        "n_aligned": len(aligned),
        "weight_coverage_pct": round(wc_pct, 1) if wc_pct is not None else None,
        "era_stats": era_stats,
        "kill_rule": {
            "triggered": kill_rule_triggered,
            "kill_full": kill_full,
            "kill_2021": kill_2021,
            "bridge_mae_full": round(bridge_mae_full, 4) if bridge_mae_full else None,
            "naive_mae_full": round(naive_mae_full, 4) if naive_mae_full else None,
            "bridge_mae_2021": round(bridge_mae_2021, 4) if bridge_mae_2021 else None,
            "naive_mae_2021": round(naive_mae_2021, 4) if naive_mae_2021 else None,
        },
        "verdict": verdict,
    }
    return result


def _print_era_table(era_stats: dict[str, dict], release: str) -> str:
    """Format era stats as a markdown table string."""
    fmt = lambda x: f"{x:.4f}" if x is not None else "—"
    lines = [
        f"\n### {release} — era metrics\n",
        "| Era | N | MAE bridge | MAE naive | MAE champ | MAE trail3m | MAE ExpandMean* |",
        "|---|---|---|---|---|---|---|",
    ]
    for era_label in ["full", "pre_2010", "2010_2020", "2021_plus", "covid_separate"]:
        m = era_stats.get(era_label, {})
        n = m.get("n", 0)
        mae_b = m.get("mae_bridge")
        mae_n = m.get("mae_naive")
        mae_c = m.get("mae_champ")
        mae_t = m.get("mae_trailing3m")
        mae_e = m.get("mae_expanding_mean")
        lines.append(
            f"| {era_label} | {n} | {fmt(mae_b)} | {fmt(mae_n)} | {fmt(mae_c)} | {fmt(mae_t)} | {fmt(mae_e)} |"
        )
    lines.append("")
    lines.append("\\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Strongest naive = min(MAE naive, MAE trail3m, MAE ExpandMean).")
    return "\n".join(lines)


def write_results_md(
    hl_result: dict,
    core_result: dict,
) -> str:
    """Write RESULTS_CPI_BRIDGE_V1.md and return the path."""
    md_path = Path(__file__).resolve().parent / "RESULTS_CPI_BRIDGE_V1.md"

    def _k(r: dict) -> dict:
        return r.get("kill_rule", {})

    lines = [
        "# Results — CPI Component Bridge V1 (Track CB, MRI-R25)",
        "",
        f"**Run date:** {date.today()}",
        "**Spec:** research/release_forecast/PREREG_CPI_BRIDGE_V1.md (frozen 2026-07-08)",
        "**Ruling:** MRI-R25",
        "",
        "---",
        "",
        "## Weight Coverage",
        "",
        f"Share of CPI basket backed by modelled (non-prior) blocks:",
        f"- Headline: **{hl_result.get('weight_coverage_pct', '—')}%** of basket",
        f"- Core: **{core_result.get('weight_coverage_pct', '—')}%** of basket",
        "",
        "Note: weight_coverage_pct can exceed 100% because core_services_ex_shelter",
        "weight (44.3) overlaps with core_goods (19.2) — both applied to same broad basket.",
        "The 5 modelled blocks cover blocks with direct HF proxies; other blocks are prior-only.",
        "",
        "### Which blocks had live proxies vs fell to prior:",
        "| Block | Proxy | Status |",
        "|---|---|---|",
        "| energy_gasoline | GASREGW (EIA weekly, unrevised) | LIVE — data present 1990+ |",
        "| energy_electricity | APU000072610 (BLS avg price) | LIVE — data present 1978+ |",
        "| shelter | ZORI + CUSR0000SAH1 | LIVE — ZORI from ~2015; falls to CPI shelter prior before |",
        "| food_at_home | WPU01 (farm PPI) + CUSR0000SAF11 | LIVE — both present 1913+ / 1952+ |",
        "| core_goods_pipeline | PPIFIS + PPIFES (ALFRED-vintaged) | LIVE — from 2014-03 only; PRIOR before that |",
        "| core_services_ex_shelter | CUSR0000SASLE (persistence) | LIVE — data present 1967+ |",
        "",
        "---",
        "",
        "## Headline Results",
        "",
        f"- Bridge walk-forward steps: {hl_result.get('n_bridge_steps')}",
        f"- Champion walk-forward steps: {hl_result.get('n_champ_steps')}",
        f"- Aligned (both have result): {hl_result.get('n_aligned')}",
        "",
    ]

    # Headline era table
    lines.append(_print_era_table(hl_result.get("era_stats", {}), "cpi_headline"))
    lines.append("")

    # Kill rule headline
    kh = _k(hl_result)

    def _sn_bridge(era_stats: dict, era_key: str) -> float | None:
        """Strongest naive for bridge (min of naive, t3m, expanding_mean)."""
        m = era_stats.get(era_key, {})
        candidates = [m.get("mae_naive"), m.get("mae_trailing3m"), m.get("mae_expanding_mean")]
        valid = [c for c in candidates if c is not None]
        return min(valid) if valid else None

    fmt4 = lambda x: f"{x:.4f}" if x is not None else "—"

    hl_es = hl_result.get("era_stats", {})
    sn_hl_full = _sn_bridge(hl_es, "full")
    sn_hl_2021 = _sn_bridge(hl_es, "2021_plus")
    hl_mae_full = hl_es.get("full", {}).get("mae_bridge")
    hl_mae_2021 = hl_es.get("2021_plus", {}).get("mae_bridge")

    core_es = core_result.get("era_stats", {})
    sn_core_full = _sn_bridge(core_es, "full")
    sn_core_2021 = _sn_bridge(core_es, "2021_plus")
    core_mae_full = core_es.get("full", {}).get("mae_bridge")
    core_mae_2021 = core_es.get("2021_plus", {}).get("mae_bridge")

    lines += [
        "### Kill Rule — cpi_headline",
        f"- Bridge MAE (full): {kh.get('bridge_mae_full')} vs naive: {kh.get('naive_mae_full')} → kill_full={kh.get('kill_full')}",
        f"- Bridge MAE (2021+): {kh.get('bridge_mae_2021')} vs naive: {kh.get('naive_mae_2021')} → kill_2021={kh.get('kill_2021')}",
        f"- **Kill rule triggered: {kh.get('triggered')}**",
        f"- **Verdict: {hl_result.get('verdict')}**",
        "",
        "### Vs Strongest Naive — cpi_headline (REPORTED, MRI-R28b)",
        f"- Full: bridge MAE={fmt4(hl_mae_full)} vs strongest_naive={fmt4(sn_hl_full)} — margin={fmt4((sn_hl_full - hl_mae_full) if (sn_hl_full and hl_mae_full) else None)} ({'BEATS' if (sn_hl_full and hl_mae_full and hl_mae_full < sn_hl_full) else 'LAGS'})",
        f"- 2021+: bridge MAE={fmt4(hl_mae_2021)} vs strongest_naive={fmt4(sn_hl_2021)} — margin={fmt4((sn_hl_2021 - hl_mae_2021) if (sn_hl_2021 and hl_mae_2021) else None)} ({'BEATS' if (sn_hl_2021 and hl_mae_2021 and hl_mae_2021 < sn_hl_2021) else 'LAGS'})",
        "",
        "---",
        "",
        "## Core Results",
        "",
        f"- Bridge walk-forward steps: {core_result.get('n_bridge_steps')}",
        f"- Champion walk-forward steps: {core_result.get('n_champ_steps')}",
        f"- Aligned: {core_result.get('n_aligned')}",
        "",
    ]

    lines.append(_print_era_table(core_result.get("era_stats", {}), "cpi_core"))
    lines.append("")

    # Kill rule core
    kc = _k(core_result)
    lines += [
        "### Kill Rule — cpi_core",
        f"- Bridge MAE (full): {kc.get('bridge_mae_full')} vs naive: {kc.get('naive_mae_full')} → kill_full={kc.get('kill_full')}",
        f"- Bridge MAE (2021+): {kc.get('bridge_mae_2021')} vs naive: {kc.get('naive_mae_2021')} → kill_2021={kc.get('kill_2021')}",
        f"- **Kill rule triggered: {kc.get('triggered')}**",
        f"- **Verdict: {core_result.get('verdict')}**",
        "",
        "### Vs Strongest Naive — cpi_core (REPORTED, MRI-R28b)",
        f"- Full: bridge MAE={fmt4(core_mae_full)} vs strongest_naive={fmt4(sn_core_full)} — margin={fmt4((sn_core_full - core_mae_full) if (sn_core_full and core_mae_full) else None)} ({'BEATS' if (sn_core_full and core_mae_full and core_mae_full < sn_core_full) else 'LAGS'})",
        f"- 2021+: bridge MAE={fmt4(core_mae_2021)} vs strongest_naive={fmt4(sn_core_2021)} — margin={fmt4((sn_core_2021 - core_mae_2021) if (sn_core_2021 and core_mae_2021) else None)} ({'BEATS' if (sn_core_2021 and core_mae_2021 and core_mae_2021 < sn_core_2021) else 'LAGS'})",
        "",
        "---",
        "",
        "## Caveats and Known Gaps",
        "",
        "1. **Weight overlap:** core_goods_pipeline (RI weight 19.2) and core_services_ex_shelter",
        "   (RI weight 44.3) cover overlapping CPI baskets. The bridge sums their contributions",
        "   additively — this double-counts the core goods universe. The residual_pp is 0 by",
        "   construction but the headline estimate may be biased. This is a known design gap.",
        "",
        "2. **Core goods pipeline gap pre-2014:** PPIFIS/PPIFES only available from 2014-03 in",
        "   ALFRED vintages. Before 2014-03, the core_goods_pipeline block falls to prior_only.",
        "   This structural break hurts pre-2014 metrics.",
        "",
        "3. **Food-at-home signal quality:** WPU01 (farm products PPI) is a coarse proxy for",
        "   food-at-home CPI. The directional signal (threshold 1.0pp, scale 0.2) is conservative.",
        "   This block is intentionally weak (confidence=0.4).",
        "",
        "4. **Non-ALFRED-vintaged series:** APU000072610, CUSR0000SAF11, WPU01, CUSR0000SASLE,",
        "   CUSR0000SAH1, ZORI all declared revision_optimistic. The backtest uses latest-revised",
        "   values — in real-time these may have differed. This is a look-ahead bias for those blocks.",
        "",
        "5. **CSXS series definition mismatch:** CUSR0000SASLE is 'all items less food, energy,",
        "   shelter' (a broad aggregate including both goods and services). Using it as persistence",
        "   for 'core services ex-shelter' introduces scope mismatch.",
        "",
        "6. **Bridge has no confidence intervals:** The bridge produces a point estimate only.",
        "   No quantile distribution is computed (unlike the champion ridge which has empirical",
        "   residual quantiles). This limits its usefulness for surprise characterization.",
        "",
        "---",
        "",
        "## Shadow Eligibility",
        "",
        f"**cpi_headline:** {hl_result.get('verdict')}",
        f"**cpi_core:** {core_result.get('verdict')}",
        "",
        "Per MRI-R25: A track failing the kill rule is NOT shadowed.",
        "The champion (frozen v2 ridge) keeps the card regardless.",
        "If shadow-eligible, nightly rows tagged `cpi_bridge` accrue for forward scoring.",
        "",
        "---",
        "",
        "## §12 Restatement (2026-07-10, MRI-R28/R29/F7)",
        "",
        "**MRI-R29 (bridge claim VOIDED):** The previous 'edges champion' verdict for this",
        "backtest is VOIDED as a promotion argument per MRI-R29. The bridge reads latest-revised",
        "sub-index parquets (audit F2), making its apparent edge revision-optimistic — this is",
        "not a real-time advantage. Forward-ledger evidence is the only valid promotion basis.",
        "",
        "**expanding_mean benchmark** added to era tables above (REPORTED, non-binding per MRI-R28b).",
        "Bridge verdicts (kill rule, shadow eligibility) stand unchanged — they were not",
        "predicated on the 'edges champion' margin that MRI-R29 voids.",
        "",
        "**F7 fix:** This file is fully regenerated from current code (stale-numbers problem fixed).",
        "Run date above reflects actual regeneration date.",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nResults written to: {md_path}")
    return str(md_path)


def main() -> None:
    root = _REPO

    print("CPI Component Bridge Backtest (Track CB, MRI-R25)")
    print("=" * 60)

    hl_result = run_backtest("cpi_headline", root)
    core_result = run_backtest("cpi_core", root)

    # Save JSON
    summary = {
        "run_date": str(date.today()),
        "cpi_headline": hl_result,
        "cpi_core": core_result,
    }
    json_path = _RESULTS_DIR / "backtest_cpi_bridge_v1.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nJSON written to: {json_path}")

    # Write markdown results
    write_results_md(hl_result, core_result)

    # Print key table
    print("\n" + "=" * 60)
    print("KEY RESULTS SUMMARY")
    print("=" * 60)

    for rel, res in [("cpi_headline", hl_result), ("cpi_core", core_result)]:
        k = res.get("kill_rule", {})
        print(f"\n{rel}:")
        print(f"  Weight coverage: {res.get('weight_coverage_pct')}%")
        print(f"  Aligned steps: {res.get('n_aligned')}")

        es = res.get("era_stats", {})
        for era in ["full", "2021_plus"]:
            m = es.get(era, {})
            mae_b = m.get("mae_bridge")
            mae_n = m.get("mae_naive")
            mae_c = m.get("mae_champ")
            n = m.get("n", 0)
            fmt = lambda x: f"{x:.4f}" if x is not None else "N/A"
            print(f"  [{era}] n={n} MAE bridge={fmt(mae_b)} naive={fmt(mae_n)} champ={fmt(mae_c)}")

        print(f"  Kill rule: {k.get('triggered')} → {res.get('verdict')}")


if __name__ == "__main__":
    main()
