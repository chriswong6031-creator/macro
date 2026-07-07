"""EXIT-TAX-SCENARIOS — Scenario-rate after-tax table (RUL-F3.10).

Answers the one honest question: does short-term-rate churn at hold(21)-recycling
erase its edge vs deferring into long-term treatment at 252d+ holds?

ALL exit-grid holds (≤126 bars) are SHORT-TERM by construction — the tax kink only
appears at the 252d comparison. This is stated plainly throughout.

IMPORTANT CAVEATS (printed in every output):
  - THIS IS SCENARIO ANALYSIS, NOT TAX ADVICE.
  - Symbolic rates {0, 15, 20, 35, 40}% are scenarios, not jurisdiction facts.
  - Real tax is complex (jurisdictions, holding periods, wash sales, lots, etc).
  - Survivorship: the 252d long-hold cohort is SURVIVOR-BIASED (2021+ fires that
    matured). Survivor-only numbers are an UPPER BOUND on long-hold performance.
    Both cohorts are printed separately.

Per RUL-F3.10:
  - Scenario rates: 0/15/20/35/40%.
  - Short-term: hold(21) recycled ~12x/yr (252/21 ≈ 12 cycles/yr).
  - Long-term: 252d+ hold using long_hold_labels.parquet total_return_252d.
  - Survivorship_biased column is split and both cohorts printed separately.
  - Long_hold_labels degradation: if file absent, use manifest statistics.

Usage:
  python3 -m scripts.research.exit_tax_scenarios
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
_DATA = _REPO / "data"
_MAIN_CHECKOUT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
_MAIN_DATA = _MAIN_CHECKOUT / "data"

_OUT_JSON = _DATA / "execution" / "exit_tax_scenarios.json"
_LABELS_PATH_WT = _DATA / "research" / "long_hold_labels.parquet"
_LABELS_PATH_MAIN = _MAIN_DATA / "research" / "long_hold_labels.parquet"
_MANIFEST_PATH = _DATA / "research" / "long_hold_labels_manifest.json"

# ── scenario rates ─────────────────────────────────────────────────────────────
SCENARIO_RATES = [0.0, 0.15, 0.20, 0.35, 0.40]

# hold(21) from exit_grid_v1 summary stats
HOLD21_GROSS_MEAN_RET = 0.0193   # +1.93% per cycle (from wait_grid_v1 delay1_hold21)
HOLD21_WR = 0.577
HOLD21_N_FIRES = 49_939
CYCLES_PER_YEAR = 252.0 / 21.0   # ≈ 12 cycles/yr

# Reference: what exit-grid hold_126 gives (gross, from registered summary)
HOLD126_GROSS_MEAN_RET = 0.073   # +7.3% (from exit_grid_v1)
HOLD126_WR = 0.590
REFERENCE_HORIZON_BARS = 126

# ── tax engine (symbolic scenarios) ───────────────────────────────────────────

class TaxScenario(NamedTuple):
    """One symbolic tax scenario."""
    rate: float        # e.g. 0.35
    label: str         # e.g. "35%"


def _after_tax_return(gross_ret: float, tax_rate: float) -> float:
    """After-tax return on a single period gain.

    If gross_ret > 0: after_tax = gross_ret * (1 - tax_rate).
    If gross_ret ≤ 0: no tax event on loss (simplified — ignores loss harvesting).
    This is a SCENARIO simplification.
    """
    if gross_ret > 0:
        return gross_ret * (1.0 - tax_rate)
    return gross_ret   # losses not modeled as tax credits (conservative)


def _compound_after_tax_annual(
    per_cycle_gross_ret: float,
    cycles_per_year: float,
    st_rate: float,
) -> float:
    """Compound after-tax annual return for short-term recycling.

    Per-cycle after-tax return compounded cycles_per_year times.
    Returns annualized after-tax return as a fraction.
    """
    per_cycle_at = _after_tax_return(per_cycle_gross_ret, st_rate)
    # compound: (1 + r_at)^cycles - 1
    return math.pow(1.0 + per_cycle_at, cycles_per_year) - 1.0


def _lt_after_tax_annual(
    gross_252d_ret: float,
    lt_rate: float,
    periods_per_year: float = 1.0,  # 252d ≈ 1 year
) -> float:
    """After-tax annual return for long-term hold at 252d horizon.

    Uses LT rate (≤ ST rate by assumption in US tax law — scenarios are illustrative).
    """
    annual_gross = math.pow(1.0 + gross_252d_ret, periods_per_year) - 1.0
    return _after_tax_return(annual_gross, lt_rate)


def _run_exit_grid_scenarios(
    gross_mean_ret_per_cycle: float,
    cycles_per_year: float,
    n_fires: int,
    wr: float,
    hold_bars: int,
    scenarios: list[TaxScenario],
) -> list[dict]:
    """Compute after-tax compounded annual return for exit-grid cells.

    All exit-grid holds (≤126 bars) are short-term by construction.
    """
    results = []
    for sc in scenarios:
        at_annual = _compound_after_tax_annual(
            gross_mean_ret_per_cycle, cycles_per_year, sc.rate
        )
        gross_annual = _compound_after_tax_annual(
            gross_mean_ret_per_cycle, cycles_per_year, 0.0
        )
        results.append({
            "scenario_rate": sc.rate,
            "scenario_label": sc.label,
            "gross_per_cycle_mean_ret": round(gross_mean_ret_per_cycle, 6),
            "cycles_per_year": round(cycles_per_year, 2),
            "gross_annual_compounded": round(gross_annual, 6),
            "after_tax_annual_compounded": round(at_annual, 6),
            "tax_drag_annual_bps": round((gross_annual - at_annual) * 10_000, 2),
            "hold_bars": hold_bars,
            "n_fires": n_fires,
            "wr": wr,
            "note": (
                f"ALL exit-grid holds (≤{REFERENCE_HORIZON_BARS} bars) are "
                f"SHORT-TERM by construction; LT rate comparison requires 252d horizon."
            ),
        })
    return results


def _run_lt_scenarios(
    gross_252d_mean_ret: float,
    n_fires: int,
    wr: float,
    survivorship_biased: bool,
    scenarios: list[TaxScenario],
    cohort_label: str,
) -> list[dict]:
    """Compute after-tax annual return for 252d long-hold cohort.

    Uses LT rate for ST scenarios (the kink: ST→LT deferral is the question).
    For the tax-kink comparison:
      - ST scenario rate applied to hold(21) recycling at 12x/yr.
      - The same rate, treated as LT (or explicitly paired LT rates), for 252d hold.
    Per RUL-F3.10, scenarios rates are symbolic; we pair:
      ST rates 0/35/40% with LT rates 0/15/20% (illustrative pairing).
    """
    # Pairing: for each ST scenario, also show what LT rate applies
    # (US-style: 0% → 0%, 35/40% ST → 20% LT, 15/20% → 15% LT — illustrative)
    LT_PAIR = {0.0: 0.0, 0.15: 0.15, 0.20: 0.15, 0.35: 0.20, 0.40: 0.20}

    results = []
    for sc in scenarios:
        lt_rate = LT_PAIR.get(sc.rate, sc.rate)
        at_annual = _lt_after_tax_annual(gross_252d_mean_ret, lt_rate)
        gross_annual = _lt_after_tax_annual(gross_252d_mean_ret, 0.0)
        results.append({
            "cohort": cohort_label,
            "survivorship_biased": survivorship_biased,
            "scenario_st_rate": sc.rate,
            "scenario_lt_rate": lt_rate,
            "scenario_label": sc.label,
            "gross_252d_mean_ret": round(gross_252d_mean_ret, 6),
            "gross_annual_approx": round(gross_annual, 6),
            "after_tax_annual_lt": round(at_annual, 6),
            "tax_drag_annual_bps": round((gross_annual - at_annual) * 10_000, 2),
            "n_fires": n_fires,
            "wr": wr,
            "survivorship_note": (
                "UPPER BOUND — survivor-biased cohort includes only names that "
                "matured with positive 252d outcomes; true long-hold return is lower."
            ) if survivorship_biased else (
                "Non-survivor-biased cohort (honest 252d matured fires)."
            ),
        })
    return results


def _load_long_hold_labels() -> pd.DataFrame | None:
    """Try to load long_hold_labels.parquet from worktree or main checkout."""
    for p in [_LABELS_PATH_WT, _LABELS_PATH_MAIN]:
        if p.exists():
            try:
                df = pd.read_parquet(p)
                print(f"[lhl] loaded long_hold_labels from {p}: {len(df)} rows")
                print(f"[lhl] cols: {list(df.columns[:12])}")
                return df
            except Exception as e:
                print(f"[lhl] failed to read {p}: {e}")
    print("[lhl] long_hold_labels.parquet not found in worktree or main checkout")
    return None


def _load_manifest_stats() -> dict:
    """Load summary stats from long_hold_labels_manifest.json."""
    if not _MANIFEST_PATH.exists():
        print("[manifest] not found at", _MANIFEST_PATH)
        return {}
    try:
        with open(_MANIFEST_PATH) as f:
            m = json.load(f)
        return m
    except Exception as e:
        print(f"[manifest] failed: {e}")
        return {}


def _get_252d_stats_from_df(df: pd.DataFrame) -> list[dict]:
    """Extract 252d return stats split by survivorship_biased column.

    Returns list of dicts with cohort info.
    """
    if "total_return_252d" not in df.columns:
        print("[lhl] 'total_return_252d' column not found; cannot compute 252d stats")
        return []

    cohorts = []
    for biased in [False, True]:
        if "survivorship_biased" in df.columns:
            sub = df[df["survivorship_biased"] == biased].copy()
            label = "survivor_biased" if biased else "honest_cohort"
        else:
            sub = df.copy()
            biased = None
            label = "all_fires_survivorship_unknown"

        sub_252 = sub.dropna(subset=["total_return_252d"])
        n = len(sub_252)
        if n == 0:
            print(f"[lhl] cohort={label}: n=0 fires with valid total_return_252d")
            cohorts.append({
                "cohort": label,
                "survivorship_biased": biased,
                "n_fires_with_252d": 0,
                "mean_252d_ret": None,
                "median_252d_ret": None,
                "wr_252d": None,
                "note": "No fires with valid total_return_252d in this cohort.",
            })
            continue

        vals = sub_252["total_return_252d"].values.astype(float)
        mean_ret = float(np.nanmean(vals))
        median_ret = float(np.nanmedian(vals))
        wr = float(np.mean(vals > 0))
        print(f"[lhl] cohort={label}: n={n}, mean={mean_ret:.4f}, "
              f"median={median_ret:.4f}, WR={wr:.4f}")
        cohorts.append({
            "cohort": label,
            "survivorship_biased": biased,
            "n_fires_with_252d": n,
            "mean_252d_ret": round(mean_ret, 6),
            "median_252d_ret": round(median_ret, 6),
            "wr_252d": round(wr, 4),
        })
        if biased is None:
            break  # only one cohort if no survivorship column

    return cohorts


def _get_252d_stats_from_manifest(manifest: dict) -> list[dict]:
    """Extract 252d return stats from manifest when parquet is absent."""
    print("[manifest] using manifest for 252d cohort stats (parquet absent)")
    cohorts = []

    # honest cohort from manifest
    oos = manifest.get("oos_honest_cohort_252d", {})
    ep = manifest.get("episode_cluster_counts", {})
    n_honest = ep.get("honest_cohort_252d_n_fires", 0)

    if n_honest > 0:
        cohorts.append({
            "cohort": "honest_cohort_from_manifest",
            "survivorship_biased": False,
            "n_fires_with_252d": n_honest,
            "mean_252d_ret": None,   # manifest doesn't store mean returns
            "median_252d_ret": None,
            "wr_252d": None,
            "manifest_note": (
                f"n_fires={n_honest}, n_clusters={ep.get('honest_cohort_252d_episode_clusters','?')}. "
                "Mean/WR not available from manifest alone — parquet required for return stats."
            ),
        })
    else:
        cohorts.append({
            "cohort": "honest_cohort_from_manifest",
            "survivorship_biased": False,
            "n_fires_with_252d": 0,
            "mean_252d_ret": None,
            "median_252d_ret": None,
            "wr_252d": None,
            "manifest_note": "honest_cohort_252d_n_fires=0 or not found in manifest.",
        })

    # For survivorship-biased: manifest tracks by year, all 2021+ are biased
    # Cannot derive aggregate return stats without parquet
    cohorts.append({
        "cohort": "survivor_biased_from_manifest",
        "survivorship_biased": True,
        "n_fires_with_252d": None,
        "mean_252d_ret": None,
        "median_252d_ret": None,
        "wr_252d": None,
        "manifest_note": (
            "Survivorship-biased cohort stats require parquet. "
            "Manifest confirms 2021+ cohort is survivorship_biased=True."
        ),
    })

    return cohorts


def main() -> None:
    print("=" * 70)
    print("EXIT-TAX-SCENARIOS — Scenario after-tax table (RUL-F3.10)")
    print(f"Run at: {datetime.utcnow().isoformat()}Z")
    print("=" * 70)

    print("\n" + "!" * 70)
    print("IMPORTANT: THIS IS SCENARIO ANALYSIS, NOT TAX ADVICE.")
    print("Symbolic rates are illustrative. Real tax depends on jurisdiction,")
    print("tax lots, wash-sale rules, entity type, and many other factors.")
    print("!" * 70 + "\n")

    print("House law note: ALL exit-grid holds (≤126 bars) are SHORT-TERM by")
    print("construction. The within-grid 'tax kink' is zero. The comparison")
    print("must reach the 252d horizon to show any kink. This is stated plainly.\n")

    # ── scenarios ──────────────────────────────────────────────────────────────
    scenarios = [TaxScenario(rate=r, label=f"{int(r*100)}%")
                 for r in SCENARIO_RATES]

    # ── exit grid (short-term, hold_21 recycled 12x/yr) ───────────────────────
    print("--- Exit-grid hold_21 (short-term, ~12 cycles/yr) ---")
    exit21_scenarios = _run_exit_grid_scenarios(
        gross_mean_ret_per_cycle=HOLD21_GROSS_MEAN_RET,
        cycles_per_year=CYCLES_PER_YEAR,
        n_fires=HOLD21_N_FIRES,
        wr=HOLD21_WR,
        hold_bars=21,
        scenarios=scenarios,
    )
    for r in exit21_scenarios:
        print(f"  ST={r['scenario_label']:4s}  gross_annual={r['gross_annual_compounded']*100:.2f}%  "
              f"net_annual={r['after_tax_annual_compounded']*100:.2f}%  "
              f"tax_drag={r['tax_drag_annual_bps']:.1f}bps")

    # ── exit grid hold_126 for reference ──────────────────────────────────────
    print("\n--- Exit-grid hold_126 reference (short-term, ~2 cycles/yr) ---")
    cycles_126 = 252.0 / 126.0
    exit126_scenarios = _run_exit_grid_scenarios(
        gross_mean_ret_per_cycle=HOLD126_GROSS_MEAN_RET,
        cycles_per_year=cycles_126,
        n_fires=HOLD21_N_FIRES,  # same cohort
        wr=HOLD126_WR,
        hold_bars=126,
        scenarios=scenarios,
    )
    for r in exit126_scenarios:
        print(f"  ST={r['scenario_label']:4s}  gross_annual={r['gross_annual_compounded']*100:.2f}%  "
              f"net_annual={r['after_tax_annual_compounded']*100:.2f}%  "
              f"tax_drag={r['tax_drag_annual_bps']:.1f}bps")

    # ── long-hold 252d ─────────────────────────────────────────────────────────
    print("\n--- Long-hold 252d (LT treatment applies) ---")
    lhl_df = _load_long_hold_labels()
    manifest = _load_manifest_stats()

    if lhl_df is not None:
        cohort_stats = _get_252d_stats_from_df(lhl_df)
        lhl_source = "parquet"
    else:
        cohort_stats = _get_252d_stats_from_manifest(manifest)
        lhl_source = "manifest_only"

    lt_scenarios_by_cohort = {}
    for cs in cohort_stats:
        if cs["mean_252d_ret"] is not None:
            lt_rows = _run_lt_scenarios(
                gross_252d_mean_ret=cs["mean_252d_ret"],
                n_fires=cs["n_fires_with_252d"],
                wr=cs["wr_252d"],
                survivorship_biased=cs["survivorship_biased"],
                scenarios=scenarios,
                cohort_label=cs["cohort"],
            )
            lt_scenarios_by_cohort[cs["cohort"]] = lt_rows
            print(f"\n  cohort={cs['cohort']} (n={cs['n_fires_with_252d']}, "
                  f"survivorship_biased={cs['survivorship_biased']})")
            for r in lt_rows:
                print(f"    ST={r['scenario_st_rate']*100:.0f}%→LT={r['scenario_lt_rate']*100:.0f}%  "
                      f"gross={r['gross_annual_approx']*100:.2f}%  "
                      f"net={r['after_tax_annual_lt']*100:.2f}%  "
                      f"drag={r['tax_drag_annual_bps']:.1f}bps  "
                      f"{'[UPPER BOUND]' if r['survivorship_biased'] else '[honest]'}")
        else:
            print(f"\n  cohort={cs['cohort']}: mean_252d_ret=None — "
                  f"cannot compute LT scenario (parquet required for return stats)")
            lt_scenarios_by_cohort[cs["cohort"]] = {
                "status": "DEFER",
                "reason": "long_hold_labels.parquet absent; return stats unavailable from manifest",
                "n_fires_with_252d": cs.get("n_fires_with_252d"),
                "manifest_note": cs.get("manifest_note", ""),
            }

    # ── kink analysis ──────────────────────────────────────────────────────────
    print("\n--- Tax kink analysis ---")
    print("All exit-grid cells (≤126 bars) are SHORT-TERM. The kink only appears")
    print("at the 252d comparison. For the kink to favor long-hold:")
    print("  after_tax_lt_252d > after_tax_st_hold21_compounded_annual")
    print("This comparison is only valid if survivorship cohort is acknowledged.")

    # ── write output ───────────────────────────────────────────────────────────
    _OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "derived_from_surface": ["exit_grid_v1", "wait_grid_v1"],
        "run_at": datetime.utcnow().isoformat() + "Z",
        "verdict_criteria": "descriptive-only",
        "THIS_IS": "SCENARIO_ANALYSIS_NOT_TAX_ADVICE",
        "scenario_rates": SCENARIO_RATES,
        "house_law_note": (
            "All exit-grid holds (≤126 bars) are SHORT-TERM by construction. "
            "The within-grid tax kink is zero. "
            "The ST vs LT comparison requires reaching the 252d horizon."
        ),
        "hold21_source": {
            "exp_id": "exit_grid_v1 / wait_grid_v1",
            "gross_mean_ret_per_cycle": HOLD21_GROSS_MEAN_RET,
            "wr": HOLD21_WR,
            "n_fires": HOLD21_N_FIRES,
            "cycles_per_year": round(CYCLES_PER_YEAR, 4),
        },
        "hold126_reference": {
            "gross_mean_ret_per_cycle": HOLD126_GROSS_MEAN_RET,
            "wr": HOLD126_WR,
            "cycles_per_year": round(252.0 / 126.0, 4),
        },
        "exit_grid_scenarios": {
            "hold_21": exit21_scenarios,
            "hold_126_reference": exit126_scenarios,
        },
        "long_hold_252d_source": lhl_source,
        "long_hold_252d_cohort_stats": cohort_stats,
        "long_hold_252d_scenarios": lt_scenarios_by_cohort,
        "survivorship_note": (
            "The survivor-biased cohort (2021+ fires that matured to 252d) is an "
            "UPPER BOUND on long-hold performance. Both cohorts are printed. "
            "The honest cohort is the decision-relevant comparator."
        ),
    }

    with open(_OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, allow_nan=False)

    print(f"\n[out] written: {_OUT_JSON}")
    print("\nIMPORTANT: THIS IS SCENARIO ANALYSIS, NOT TAX ADVICE.")
    print("Done.")


if __name__ == "__main__":
    main()
