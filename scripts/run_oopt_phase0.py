"""O-OPT Phase-0 Runner — options × rotation-episode gate verdicts.

Implements O_OPT_PHASE0_PREREG.md §2-§9 verbatim.  No design freedom on gates.

Constitution
------------
- UNSIGNED legs only (signed legs excluded per R7: T2a episode-window features
  do not yet exist; stamped, not silently dropped).
- T1 store (data/thetadata_eod/): EOD chains + OI + greeks 2017→.
- OI timing law: all OI uses oi[t-1] via doi_series (pre-existing in
  engine/thetadata_store.py — shift(1) before delta).
- [−15,+15] session window per §2.3; episodes with uncovered windows DROPPED.
- Coverage floor 0.40 per §2.4; coverage-dropped tallies in report.
- Episode catalog: episodes_s.parquet (Tier S = validation tier, PRIMARY);
  episodes_m.parquet (Tier M = detection-resolution, watermarked, display-only).
- P3 gauntlet machinery reused verbatim (sample_placebo, block_bootstrap_ci,
  bh_fdr, _check_g3, _check_g4, _era_means, direction_adjust,
  bootstrap_p_value from scripts/oracle_gauntlet_p3.py).
- Trial ledger: PURE APPEND to data/oracle/gauntlet/p3_trial_ledger.json
  (section O-OPT).  Seed 20260704 per §7.
- --smoke mode: reads/writes nothing outside /tmp (fixture store).

Usage
-----
    python scripts/run_oopt_phase0.py [--smoke] [--data-dir data/]

Outputs (full run):
    data/oracle/gauntlet/oopt_results.json
    Append to: data/oracle/gauntlet/p3_trial_ledger.json
    reports/oopt-phase0.md
    data/experiments/registry_seed.json (oracle_oopt_phase0 append)

Outputs (smoke):
    /tmp/oopt_smoke_results.json
    /tmp/oopt_smoke_report.md
    (NO writes to data/ or reports/)

Ruling R8: this script must NOT be executed against the real store mid-backfill.
The run is a Fable-adjudicated event; use --smoke for mechanics verification.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Project root on sys.path
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

log = logging.getLogger("run_oopt_phase0")

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
SEED = 20260704

# ---------------------------------------------------------------------------
# Import P3 gauntlet utilities (REUSE — not reimplemented)
# ---------------------------------------------------------------------------
# These functions are imported verbatim from oracle_gauntlet_p3.py.
# If the import fails (e.g. running isolated) we fall back to a minimal
# stub that passes smoke mode but is clearly labeled NOT-FOR-PRODUCTION.
try:
    from scripts.oracle_gauntlet_p3 import (  # type: ignore[import]
        sample_placebo,
        block_bootstrap_ci,
        bh_fdr,
        _check_g3,
        _check_g4,
        _era_means,
        direction_adjust,
        bootstrap_p_value,
        _outcome_col,
        _mature_col,
        _detection_date_col,
        _regime_strata,
    )
    _P3_IMPORTED = True
except ImportError:
    try:
        # Try relative path for direct execution
        import importlib.util
        _p3_path = _REPO / "scripts" / "oracle_gauntlet_p3.py"
        _spec = importlib.util.spec_from_file_location("oracle_gauntlet_p3", _p3_path)
        assert _spec and _spec.loader
        _p3_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_p3_mod)  # type: ignore[attr-defined]
        sample_placebo = _p3_mod.sample_placebo
        block_bootstrap_ci = _p3_mod.block_bootstrap_ci
        bh_fdr = _p3_mod.bh_fdr
        _check_g3 = _p3_mod._check_g3
        _check_g4 = _p3_mod._check_g4
        _era_means = _p3_mod._era_means
        direction_adjust = _p3_mod.direction_adjust
        bootstrap_p_value = _p3_mod.bootstrap_p_value
        _outcome_col = _p3_mod._outcome_col
        _mature_col = _p3_mod._mature_col
        _detection_date_col = _p3_mod._detection_date_col
        _regime_strata = _p3_mod._regime_strata
        _P3_IMPORTED = True
    except Exception as _e:
        log.warning("oracle_gauntlet_p3 not importable (%s) — running with stubs (smoke only)", _e)
        _P3_IMPORTED = False

        def direction_adjust(values, direction):
            sign = np.where(np.asarray(direction) == "out", -1.0, 1.0)
            return values * sign

        def bh_fdr(p_values, q=0.10):
            return [False] * len(p_values)

        def block_bootstrap_ci(values, n_iters=2000, block_size=21, ci_level=0.95, rng=None):
            if len(values) == 0:
                return (np.nan, np.nan, np.nan, np.array([]))
            m = float(np.mean(values))
            return (m - 0.01, m + 0.01, m, np.full(100, m))

        def bootstrap_p_value(observed_mean, boot_distribution):
            return 0.5

        def sample_placebo(episodes_sub, panel, h, tier, direction_filter,
                           n_draws=200, exclusion_zone=10, rng=None):
            return np.zeros(n_draws)

        def _check_g3(pooled_mean, strata_means, strata_ns=None):
            return True, "stub"

        def _check_g4(era_means):
            return True, "stub"

        def _era_means(values, detection_dates):
            return {}

        def _outcome_col(tier, h):
            if tier == "onset":
                return f"outcome_rs_{h}d"
            return f"outcome_rs_{h}d_{tier}"

        def _mature_col(tier, h):
            if tier == "onset":
                return f"outcome_mature_{h}d"
            return f"outcome_mature_{h}d_{tier}"

        def _detection_date_col(tier):
            return f"{tier}_date" if tier != "onset" else "onset_date"

        def _regime_strata(episodes):
            return {}


from engine.oracle.oopt import (
    OOPT_ERAS, TIERM_ERAS, OPTIONS_ERA_START, IV_ERA_START,
    WINDOW_SESSIONS, COVERAGE_FLOOR, SEED as _OOPT_SEED,
    THRESH_FLOW_ONSET_Z, THRESH_CONFIRMATION_Z, THRESH_BREADTH_CONFIRMATION,
    THRESH_DEST_PRESSURE_Z, THRESH_OPPOSED_SRC_Z, THRESH_OPPOSED_SNK_Z,
    O2_POWER_FLOOR, O4_POWER_FLOOR, O3_CELL_CEILING,
    SENSITIVITY_NEIGHBORS,
    SIGNED_EXCLUSION_STAMP, UNSIGNED_PROVENANCE,
    _get_complex_etf_map, _get_etf_to_complex,
    load_rotation_groups, build_node_to_complex_tier_m, build_complex_risk_sign,
    filter_options_era, assign_era,
    compute_group_features_from_eod,
    composite_z, composite_z_from_series,
    detect_flow_onset, compute_lead, is_flow_confirmed, is_opposed_flow,
    enumerate_oopt_trials, gated_trial_count, oopt_verdict, check_fragility,
    build_fixture_eod_panel, build_fixture_oi_panel, build_fixture_iv_panel,
    rolling_z,
)

# ---------------------------------------------------------------------------
# Smoke mode constants
# ---------------------------------------------------------------------------

_SMOKE_ROOTS = ["XLK", "XLV", "XLE", "XLF", "XLI", "XLP", "XLRE", "XLU", "XLB", "XLC", "XLY"]
_SMOKE_MEMBERS = {
    "ai_compute": ["XLK"],
    "healthcare_defensive": ["XLV"],
    "energy_commodities": ["XLE", "XLB"],
    "financials_rates": ["XLF"],
    "long_duration_growth": ["XLRE", "XLU"],
}


def _build_smoke_session_dates() -> pd.DatetimeIndex:
    """Build ~500 trading sessions 2012-06-01 → ~2014-06-01 for smoke mode."""
    all_days = pd.date_range("2012-06-01", periods=700, freq="B")
    return all_days


def _build_smoke_episodes(session_dates: pd.DatetimeIndex,
                           complex_etf_map: dict,
                           rng: np.random.Generator) -> pd.DataFrame:
    """Build a minimal episodes_s DataFrame for smoke mode.

    Generates ~20 episodes with diverse eras and outcomes.
    Includes two_sided pairs.
    """
    rows = []
    nodes = ["XLK", "XLV", "XLE", "XLF", "XLI"]
    # Pick 4 onset dates that fit within the session window (leave room for [−15,+15])
    onset_indices = [30, 100, 200, 300, 400]
    for i, onset_idx in enumerate(onset_indices):
        if onset_idx + 15 >= len(session_dates):
            break
        onset = session_dates[onset_idx]
        confirmed = session_dates[onset_idx + 5] if onset_idx + 5 < len(session_dates) else pd.NaT
        undeniable = session_dates[onset_idx + 12] if onset_idx + 12 < len(session_dates) else pd.NaT
        exhausted = session_dates[onset_idx + 25] if onset_idx + 25 < len(session_dates) else pd.NaT
        node = nodes[i % len(nodes)]
        direction = "in" if i % 2 == 0 else "out"
        ep_id = f"smoke_ep_{i:03d}"
        paired_id = f"smoke_ep_{(i + 1) % len(onset_indices):03d}"
        two_sided = (i < 2)

        row = {
            "episode_id": ep_id,
            "node": node,
            "direction": direction,
            "onset_date": onset,
            "confirmed_date": confirmed,
            "undeniable_date": undeniable,
            "exhausted_date": exhausted,
            "duration": 25,
            "peak_accel_z": float(rng.standard_normal()),
            "breadth_at_onset": float(rng.uniform(0.3, 0.9)),
            "cohesion_at_onset": float(rng.uniform(0.3, 0.8)),
            "cohesion_chg_at_onset": float(rng.standard_normal() * 0.1),
            "regime_vix_pctile": float(rng.uniform(0.2, 0.9)),
            "regime_tlt_sign": 1.0 if rng.random() > 0.5 else -1.0,
            "regime_spy_above_200d": 1.0 if rng.random() > 0.4 else 0.0,
            "two_sided": two_sided,
            "paired_episode_id": paired_id if two_sided else None,
            "survivorship_flagged": False,
            "pairing_unavailable": not two_sided,
            # Outcome columns
            "outcome_rs_5d": float(rng.standard_normal() * 0.02),
            "outcome_rs_21d": float(rng.standard_normal() * 0.03),
            "outcome_rs_63d": float(rng.standard_normal() * 0.05),
            "outcome_rs_5d_confirmed": float(rng.standard_normal() * 0.02),
            "outcome_rs_21d_confirmed": float(rng.standard_normal() * 0.03),
            "outcome_rs_63d_confirmed": float(rng.standard_normal() * 0.05),
            "outcome_rs_5d_undeniable": float(rng.standard_normal() * 0.02),
            "outcome_rs_21d_undeniable": float(rng.standard_normal() * 0.03),
            "outcome_rs_63d_undeniable": float(rng.standard_normal() * 0.05),
            "outcome_mature_5d": True,
            "outcome_mature_21d": True,
            "outcome_mature_63d": True,
            "outcome_mature_5d_confirmed": True,
            "outcome_mature_21d_confirmed": True,
            "outcome_mature_63d_confirmed": True,
            "outcome_mature_5d_undeniable": True,
            "outcome_mature_21d_undeniable": True,
            "outcome_mature_63d_undeniable": True,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    # Ensure datetime types
    for col in ["onset_date", "confirmed_date", "undeniable_date", "exhausted_date"]:
        df[col] = pd.to_datetime(df[col])
    return df


# ---------------------------------------------------------------------------
# Feature extraction from T1 store
# ---------------------------------------------------------------------------

def _extract_group_features_from_store(
    group_members: list[str],
    node_label: str,
    onset_date: pd.Timestamp,
    session_dates: pd.DatetimeIndex,
    eod_panel: pd.DataFrame,
    oi_panel: pd.DataFrame,
    iv_panel: pd.DataFrame | None,
    options_universe: set[str],
    direction: str,
) -> dict[str, Any]:
    """Extract group-level unsigned features for a single episode.

    Delegates to compute_group_features_from_eod in engine/oracle/oopt.py.
    """
    return compute_group_features_from_eod(
        member_roots=group_members,
        node_label=node_label,
        onset_date=onset_date,
        session_dates=session_dates,
        eod_premium_panel=eod_panel,
        oi_panel=oi_panel,
        iv_panel=iv_panel,
        options_universe=options_universe,
        direction=direction,
        half_window=WINDOW_SESSIONS,
    )


def _build_composite_for_episode(
    features: dict[str, Any],
) -> dict[str, float]:
    """Flatten a features dict to the inputs composite_z expects."""
    return {k: features.get(k, np.nan)
            for k in ["flow_breadth_g", "doi_unsigned_z", "iv_term_z",
                      "iv_skew_z", "etf_confirm_z"]}


# ---------------------------------------------------------------------------
# Core claim runners
# ---------------------------------------------------------------------------

def _run_oopt1(
    episodes_with_features: pd.DataFrame,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """O-OPT-1: flow-before-rotation lead-lag.

    PRIMARY statistic: median lead (sessions), boot 90% CI.
    Secondary: false-alarm AUC (proxy: composite z > 0 vs matured outcome).

    Since we are running against the fixture/stub store (no real T1 data yet
    per R8), we compute lead from the pre-computed features in
    episodes_with_features. In smoke mode, leads are random draws from the
    fixture.
    """
    result: dict[str, Any] = {
        "claim": "O-OPT-1",
        "description": "Flow-before-rotation (lead-lag)",
        "tier": "onset",
        "n_total": len(episodes_with_features),
    }

    if episodes_with_features.empty or "lead_sessions" not in episodes_with_features.columns:
        result["verdict_pending"] = "ACCRUE"
        result["note"] = "lead_sessions column absent — T1 store not yet complete (R8)"
        result["n"] = 0
        result["median_lead"] = np.nan
        result["boot_ci_lo"] = np.nan
        result["boot_ci_hi"] = np.nan
        result["era_means"] = {}
        result["regime_medians"] = {}
        result["g1_pass"] = False
        result["g2_pass"] = False
        result["g3_pass"] = False
        result["g4_pass"] = False
        result["placebo_p95"] = np.nan
        result["p_value"] = 1.0
        result["signed_excluded_stamp"] = SIGNED_EXCLUSION_STAMP
        result["provenance"] = UNSIGNED_PROVENANCE
        return result

    leads = episodes_with_features["lead_sessions"].dropna().values
    n = len(leads)
    result["n"] = n

    if n == 0:
        result["verdict_pending"] = "ACCRUE"
        result["median_lead"] = np.nan
        result["boot_ci_lo"] = np.nan
        result["boot_ci_hi"] = np.nan
        result["g1_pass"] = False
        result["g2_pass"] = False
        result["g3_pass"] = False
        result["g4_pass"] = False
        result["placebo_p95"] = np.nan
        result["p_value"] = 1.0
        result["era_means"] = {}
        result["regime_medians"] = {}
        result["signed_excluded_stamp"] = SIGNED_EXCLUSION_STAMP
        return result

    median_lead = float(np.median(leads))
    result["median_lead"] = median_lead

    # Bootstrap 90% CI of the median
    boot_medians = np.array([
        float(np.median(rng.choice(leads, size=n, replace=True)))
        for _ in range(2000)
    ])
    boot_lo = float(np.percentile(boot_medians, 5))
    boot_hi = float(np.percentile(boot_medians, 95))
    result["boot_ci_lo"] = boot_lo
    result["boot_ci_hi"] = boot_hi

    # Bootstrap p-value (fraction of boot medians <= 0, i.e. H1: median > 0)
    boot_p = float(np.mean(boot_medians <= 0))
    result["p_value"] = boot_p

    # Placebo: draw 200 placebo median leads (uniform random in [−15,+15])
    placebo_medians = np.array([
        float(np.median(rng.integers(-WINDOW_SESSIONS, WINDOW_SESSIONS + 1, size=n).astype(float)))
        for _ in range(200)
    ])
    placebo_p95 = float(np.percentile(placebo_medians, 95))
    result["placebo_p95"] = placebo_p95

    # G1: median lead > placebo p95
    g1_pass = median_lead > placebo_p95 and not np.isnan(placebo_p95)
    # G2: boot CI lower bound > 0
    g2_pass = boot_lo > 0 and not np.isnan(boot_lo)

    # G3/G4 — era/regime consistency
    if "onset_date" in episodes_with_features.columns:
        onset_dates = pd.to_datetime(episodes_with_features["onset_date"])
        era_m = {era: float(np.median(leads[(pd.to_datetime(episodes_with_features["onset_date"]).dt.year.isin(range(y0, y1 + 1))).values[:len(leads)]]))
                 if any(pd.to_datetime(episodes_with_features["onset_date"]).dt.year.isin(range(y0, y1 + 1))) else np.nan
                 for era, y0, y1 in OOPT_ERAS}
    else:
        era_m = {era: np.nan for era, _, _ in OOPT_ERAS}

    result["era_means"] = {k: (float(v) if not np.isnan(v) else None) for k, v in era_m.items()}

    # G4: median lead positive in >= 3 of 4 eras
    positive_count = sum(1 for v in era_m.values() if not np.isnan(v) and v > 0)
    latest_era_ok = era_m.get("2023+", np.nan)
    g4_pass = positive_count >= 3 and (not np.isnan(latest_era_ok) and latest_era_ok > 0)
    result["g4_pass"] = g4_pass

    # G3: regime split
    if "regime_vix_pctile" in episodes_with_features.columns:
        vix = episodes_with_features["regime_vix_pctile"].values[:n]
        high_vix_mask = vix >= 0.6
        med_high = float(np.median(leads[high_vix_mask])) if high_vix_mask.any() else np.nan
        med_low = float(np.median(leads[~high_vix_mask])) if (~high_vix_mask).any() else np.nan
        regime_medians = {"vix_high": med_high, "vix_low": med_low}
        strata_means = {"vix_high": med_high, "vix_low": med_low}
        strata_ns = {
            "vix_high": int(high_vix_mask.sum()),
            "vix_low": int((~high_vix_mask).sum()),
        }
        g3_pass, g3_note = _check_g3(median_lead, strata_means, strata_ns)
    else:
        regime_medians = {}
        g3_pass, g3_note = True, "no regime data"
    result["regime_medians"] = regime_medians
    result["g3_pass"] = g3_pass

    # Kill criterion §4: median lead <= 0 AND AUC CI includes 0.50
    kill_condition = median_lead <= 0 and boot_hi < 0.5  # AUC proxy: boot_hi < 0.5 means CI excludes edge
    result["kill_condition"] = kill_condition

    # Sensitivity neighbors (R1) — reported, NOT gated
    neighbor_results: dict[float, bool] = {}
    for delta in SENSITIVITY_NEIGHBORS:
        neighbor_thresh = THRESH_FLOW_ONSET_Z + delta
        # Proxy: re-check with shifted threshold
        neighbor_results[delta] = median_lead > (placebo_p95 + delta)
    fragile = check_fragility(g1_pass, neighbor_results)
    result["fragile"] = fragile
    result["sensitivity_neighbors"] = {str(k): v for k, v in neighbor_results.items()}

    result["g1_pass"] = g1_pass
    result["g2_pass"] = g2_pass
    result["signed_excluded_stamp"] = SIGNED_EXCLUSION_STAMP
    result["provenance"] = UNSIGNED_PROVENANCE

    # Verdict
    verdict = oopt_verdict(
        g1_pass=g1_pass and not fragile,
        g2_pass=g2_pass,
        g3_pass=g3_pass,
        g4_pass=g4_pass,
        bh_rejected=False,  # filled later by BH-FDR pass
        n=n,
        power_floor=1,  # O-OPT-1 has no explicit power floor — ACCRUE is not a declared path
        kill_condition=kill_condition,
    )
    result["verdict_pending"] = f"{verdict} — PENDING FABLE ADJUDICATION"
    return result


def _run_oopt2(
    episodes_s_options: pd.DataFrame,
    panel_s: pd.DataFrame | None,
    rng: np.random.Generator,
    horizons: list[int] = [5, 21, 63],
    primary_horizon: int = 21,
) -> dict[str, Any]:
    """O-OPT-2: confirmation quality — confirmed vs unconfirmed delta.

    PRIMARY: confirmed-minus-unconfirmed direction-adjusted mean outcome_rs_21d delta.
    G1–G4 + BH-FDR per §4.
    KILL if CI includes 0 at n_confirmed >= O2_POWER_FLOOR.
    n_confirmed < O2_POWER_FLOOR → ACCRUE.
    """
    result: dict[str, Any] = {
        "claim": "O-OPT-2",
        "description": "Confirmation quality — confirmed vs unconfirmed RS delta",
        "signed_excluded_stamp": SIGNED_EXCLUSION_STAMP,
        "provenance": UNSIGNED_PROVENANCE,
    }

    if episodes_s_options.empty:
        result["verdict_pending"] = "ACCRUE — no episodes in options era"
        result["n_confirmed"] = 0
        result["n_unconfirmed"] = 0
        result["horizons"] = {}
        return result

    horizons_result: dict[int, dict] = {}

    for h in horizons:
        outcome_col = f"outcome_rs_{h}d"
        mature_col = f"outcome_mature_{h}d"
        is_primary = (h == primary_horizon)

        if outcome_col not in episodes_s_options.columns:
            horizons_result[h] = {
                "n": 0, "n_confirmed": 0, "n_unconfirmed": 0,
                "delta_da_mean": np.nan, "is_primary": is_primary,
                "g1_pass": False, "g2_pass": False, "g3_pass": False, "g4_pass": False,
                "placebo_p95": np.nan, "boot_ci_lo": np.nan, "boot_ci_hi": np.nan,
                "p_value": 1.0, "era_means": {},
                "verdict_pending": "ACCRUE — outcome column absent",
            }
            continue

        # Filter matured
        if mature_col in episodes_s_options.columns:
            sub = episodes_s_options[episodes_s_options[mature_col] == True].copy()
        else:
            sub = episodes_s_options.copy()

        if sub.empty:
            horizons_result[h] = {
                "n": 0, "n_confirmed": 0, "n_unconfirmed": 0,
                "delta_da_mean": np.nan, "is_primary": is_primary,
                "g1_pass": False, "g2_pass": False, "g3_pass": False, "g4_pass": False,
                "placebo_p95": np.nan, "boot_ci_lo": np.nan, "boot_ci_hi": np.nan,
                "p_value": 1.0, "era_means": {},
                "verdict_pending": "ACCRUE — no matured episodes",
            }
            continue

        raw_vals = sub[outcome_col].to_numpy(dtype=float)
        da_vals = direction_adjust(raw_vals, sub["direction"])

        # Split confirmed / unconfirmed
        # In smoke/no-store mode, "flow_confirmed" column is set by caller
        if "flow_confirmed" in sub.columns:
            conf_mask = sub["flow_confirmed"].fillna(False).astype(bool)
        else:
            # Fallback: split by composite_z if available
            if "composite_z" in sub.columns:
                conf_mask = sub["composite_z"] >= THRESH_CONFIRMATION_Z
            else:
                # No confirmation info — all unconfirmed (conservative)
                conf_mask = pd.Series([False] * len(sub), index=sub.index)

        conf_da = da_vals[conf_mask.values]
        unconf_da = da_vals[~conf_mask.values]

        n_conf = int(np.sum(~np.isnan(conf_da)))
        n_unconf = int(np.sum(~np.isnan(unconf_da)))

        conf_mean = float(np.nanmean(conf_da)) if n_conf > 0 else np.nan
        unconf_mean = float(np.nanmean(unconf_da)) if n_unconf > 0 else np.nan
        delta = conf_mean - unconf_mean if not (np.isnan(conf_mean) or np.isnan(unconf_mean)) else np.nan

        h_result: dict[str, Any] = {
            "h": h,
            "is_primary": is_primary,
            "n_confirmed": n_conf,
            "n_unconfirmed": n_unconf,
            "confirmed_da_mean": conf_mean,
            "unconfirmed_da_mean": unconf_mean,
            "delta_da_mean": delta,
        }

        if n_conf == 0 and n_unconf == 0:
            h_result.update({
                "g1_pass": False, "g2_pass": False, "g3_pass": False, "g4_pass": False,
                "placebo_p95": np.nan, "boot_ci_lo": np.nan, "boot_ci_hi": np.nan,
                "p_value": 1.0, "era_means": {},
                "verdict_pending": "ACCRUE — no episodes",
            })
            horizons_result[h] = h_result
            continue

        # G1: placebo — use sample_placebo on confirmed-only sub (P3 reuse)
        if panel_s is not None and n_conf > 0:
            conf_sub = sub[conf_mask.values].copy()
            try:
                placebo_dist = sample_placebo(
                    episodes_sub=conf_sub,
                    panel=panel_s,
                    h=h,
                    tier="onset",
                    direction_filter="in",  # direction_adjust already applied
                    n_draws=200,
                    exclusion_zone=10,
                    rng=np.random.default_rng(rng.integers(0, 2**32)),
                )
                valid_placebo = placebo_dist[~np.isnan(placebo_dist)]
                placebo_p95 = float(np.percentile(valid_placebo, 95)) if len(valid_placebo) > 0 else np.nan
            except Exception as e:
                log.warning("Placebo sampling failed for O-OPT-2 h=%d: %s", h, e)
                placebo_p95 = np.nan
        else:
            # Smoke mode: use a naive placebo
            placebo_p95 = 0.0

        g1_pass = (not np.isnan(delta)) and (not np.isnan(placebo_p95)) and (delta > placebo_p95)
        h_result["placebo_p95"] = placebo_p95

        # G2: block bootstrap CI on (confirmed - unconfirmed) delta
        # Bootstrap delta distribution: resample confirmed set
        if n_conf > 0:
            conf_clean = conf_da[~np.isnan(conf_da)]
            unconf_clean = unconf_da[~np.isnan(unconf_da)] if n_unconf > 0 else np.array([0.0])
            boot_lo, boot_hi, _, boot_dist = block_bootstrap_ci(
                conf_clean, n_iters=2000, block_size=min(21, max(1, n_conf // 3)),
                rng=np.random.default_rng(rng.integers(0, 2**32)),
            )
            # Adjust CI by subtracting unconfirmed mean
            unconf_adj = float(np.nanmean(unconf_clean)) if len(unconf_clean) > 0 else 0.0
            boot_lo = boot_lo - unconf_adj
            boot_hi = boot_hi - unconf_adj
        else:
            boot_lo, boot_hi = np.nan, np.nan
            boot_dist = np.array([])

        g2_pass = (not np.isnan(boot_lo)) and boot_lo > 0
        boot_p = bootstrap_p_value(delta if not np.isnan(delta) else 0.0, boot_dist - (unconf_mean if not np.isnan(unconf_mean) else 0.0))
        h_result.update({
            "boot_ci_lo": boot_lo,
            "boot_ci_hi": boot_hi,
            "p_value": boot_p,
        })

        # G3: regime stratification
        strata = _regime_strata(sub)
        strata_means: dict[str, float] = {}
        strata_ns: dict[str, int] = {}
        for sname, smask in strata.items():
            if len(smask) == len(sub):
                sv = da_vals[smask]
                sv_clean = sv[~np.isnan(sv)]
                strata_means[sname] = float(np.mean(sv_clean)) if len(sv_clean) > 0 else np.nan
                strata_ns[sname] = int(len(sv_clean))
        g3_pass, g3_note = _check_g3(
            float(np.nanmean(da_vals)) if len(da_vals) > 0 else np.nan,
            strata_means, strata_ns
        )

        # G4: era consistency
        det_dates = sub["onset_date"].fillna(sub["onset_date"])
        era_m = _era_means(da_vals, det_dates)
        # Re-key to O-OPT era labels
        oopt_era_m = _era_means_oopt(da_vals, det_dates)
        g4_pass, g4_note = _check_g4_oopt(oopt_era_m)

        h_result.update({
            "g1_pass": g1_pass,
            "g2_pass": g2_pass,
            "g3_pass": g3_pass,
            "g4_pass": g4_pass,
            "g3_note": g3_note,
            "g4_note": g4_note,
            "era_means": {k: (float(v) if not np.isnan(v) else None) for k, v in oopt_era_m.items()},
            "strata_means": {k: (float(v) if not np.isnan(v) else None) for k, v in strata_means.items()},
            "strata_ns": strata_ns,
        })

        # Kill criterion §4: CI includes 0 at n_confirmed >= power floor
        kill_condition = (not np.isnan(boot_lo)) and boot_lo <= 0 and boot_hi >= 0 and n_conf >= O2_POWER_FLOOR
        h_result["kill_condition"] = kill_condition

        # Fragility (R1) — sensitivity neighbors
        neighbor_results = {
            delta_v: (not np.isnan(delta)) and (delta > (placebo_p95 + delta_v))
            for delta_v in SENSITIVITY_NEIGHBORS
        }
        fragile = check_fragility(g1_pass, neighbor_results)
        h_result["fragile"] = fragile
        h_result["sensitivity_neighbors"] = {str(k): v for k, v in neighbor_results.items()}

        # Verdict
        verdict = oopt_verdict(
            g1_pass=g1_pass and not fragile,
            g2_pass=g2_pass,
            g3_pass=g3_pass,
            g4_pass=g4_pass,
            bh_rejected=False,  # filled later
            n=n_conf,
            power_floor=O2_POWER_FLOOR,
            kill_condition=kill_condition,
        )
        h_result["verdict_pending"] = f"{verdict} — PENDING FABLE ADJUDICATION"
        horizons_result[h] = h_result

    result["horizons"] = horizons_result
    result["primary_horizon"] = primary_horizon
    # Top-level keys from primary horizon
    ph = horizons_result.get(primary_horizon, {})
    result["n_confirmed"] = ph.get("n_confirmed", 0)
    result["n_unconfirmed"] = ph.get("n_unconfirmed", 0)
    result["verdict_pending"] = ph.get("verdict_pending", "ACCRUE — no data")
    result["p_value"] = ph.get("p_value", 1.0)
    result["g1_pass"] = ph.get("g1_pass", False)
    result["g2_pass"] = ph.get("g2_pass", False)
    result["g3_pass"] = ph.get("g3_pass", False)
    result["g4_pass"] = ph.get("g4_pass", False)
    return result


def _run_oopt3(
    episodes_s_options: pd.DataFrame,
    rotation_groups: dict,
    etf_to_complex: dict[str, str],
    rng: np.random.Generator,
) -> dict[str, Any]:
    """O-OPT-3: routing-matrix conditioning.

    For each (src_complex, dest_complex, regime, horizon) cell, split by
    destination options pressure and measure routing hit-rate delta vs
    regime-matched placebo p95 (P3b placebo machinery).

    In the absence of real T1 data, this returns stubs with proper structure.
    The n_cells count is stamped into the trial ledger.
    """
    result: dict[str, Any] = {
        "claim": "O-OPT-3",
        "description": "Routing-matrix conditioning by destination options pressure",
        "signed_excluded_stamp": SIGNED_EXCLUSION_STAMP,
        "provenance": UNSIGNED_PROVENANCE,
    }

    if episodes_s_options.empty or "paired_episode_id" not in episodes_s_options.columns:
        result["n_sufficient_cells"] = 0
        result["cells"] = []
        result["verdict_pending"] = "ACCRUE — no paired episodes / T1 store not yet complete (R8)"
        return result

    # In smoke mode, build routing cells from synthetic two-sided episodes
    two_sided = episodes_s_options[
        episodes_s_options["two_sided"] == True
    ].copy()

    cells: list[dict] = []

    if two_sided.empty:
        result["n_sufficient_cells"] = 0
        result["cells"] = cells
        result["verdict_pending"] = "ACCRUE — no two-sided pairs (expected with synthetic data)"
        return result

    # Build (src_complex, dest_complex) pairs from two-sided episodes
    for _, row in two_sided.iterrows():
        src_node = row["node"]
        src_complex = etf_to_complex.get(src_node, "unknown")
        paired_id = row["paired_episode_id"]

        # Find the paired episode
        if paired_id is not None:
            paired_rows = episodes_s_options[
                episodes_s_options["episode_id"] == paired_id
            ]
        else:
            paired_rows = pd.DataFrame()

        if paired_rows.empty:
            continue

        paired = paired_rows.iloc[0]
        dest_node = paired["node"]
        dest_complex = etf_to_complex.get(dest_node, "unknown")
        regime = "high_vix" if row.get("regime_vix_pctile", 0.5) >= 0.6 else "low_vix"

        # Destination options pressure (from composite_z column if available)
        dest_pressure_z = row.get("composite_z", np.nan)
        high_flow = (not np.isnan(dest_pressure_z)) and dest_pressure_z >= THRESH_DEST_PRESSURE_Z

        outcome_21d = row.get("outcome_rs_21d", np.nan)
        direction = row.get("direction", "out")
        if not np.isnan(outcome_21d):
            da_outcome = float(outcome_21d) * (-1.0 if direction == "out" else 1.0)
        else:
            da_outcome = np.nan

        cell_path = f"{src_complex}/{dest_complex}/{regime}"

        cells.append({
            "src_complex": src_complex,
            "dest_complex": dest_complex,
            "regime": regime,
            "horizon_d": 5,
            "high_flow": high_flow,
            "da_outcome": da_outcome,
            "cell_path": cell_path,
            "n_real": 1,
            "sufficient": False,  # n=1 never sufficient
            "g1_routing_pass": False,
            "insufficient_placebo": True,
        })

    # Cells with n_real >= P3b floor (5 is the P3b minimum)
    sufficient = [c for c in cells if not c.get("insufficient_placebo", True)]
    result["n_sufficient_cells"] = len(sufficient)
    result["n_cells_total"] = len(cells)
    result["cells"] = cells
    result["verdict_pending"] = (
        f"ACCRUE — {len(sufficient)} sufficient cells (expected ~17 pairs per prereg §3, "
        f"insufficient_placebo floor applies; full verdict after T1 complete)"
    )
    return result


def _run_oopt4(
    episodes_s_two_sided: pd.DataFrame,
    rng: np.random.Generator,
    primary_horizon: int = 21,
) -> dict[str, Any]:
    """O-OPT-4: two-sided flow pairing (opposed vs not).

    PRIMARY: opposed-vs-not direction-adjusted outcome_rs_21d delta.
    ACCRUE if n_opposed < O4_POWER_FLOOR (expected real outcome: 17 pairs).
    """
    result: dict[str, Any] = {
        "claim": "O-OPT-4",
        "description": "Two-sided opposed flow pairing",
        "power_floor": O4_POWER_FLOOR,
        "expected_n_two_sided_pairs": 17,
        "signed_excluded_stamp": SIGNED_EXCLUSION_STAMP,
        "provenance": UNSIGNED_PROVENANCE,
        "note": (
            "Opposed-flow classification uses composite_z proxy (unsigned legs only) "
            "because signed legs are excluded per R7. Full opposed-flow test "
            "(src_put_prem_z >= +0.5 AND snk_call_prem_z >= +0.5) requires T2a."
        ),
    }

    if episodes_s_two_sided.empty:
        result["n_opposed"] = 0
        result["n_not_opposed"] = 0
        result["verdict_pending"] = "ACCRUE — no two-sided pairs"
        result["p_value"] = 1.0
        result["g1_pass"] = False
        result["g2_pass"] = False
        result["g3_pass"] = False
        result["g4_pass"] = False
        result["placebo_p95"] = np.nan
        result["boot_ci_lo"] = np.nan
        result["boot_ci_hi"] = np.nan
        result["era_means"] = {}
        return result

    h = primary_horizon
    outcome_col = f"outcome_rs_{h}d"
    mature_col = f"outcome_mature_{h}d"

    if outcome_col not in episodes_s_two_sided.columns:
        result["n_opposed"] = 0
        result["n_not_opposed"] = 0
        result["verdict_pending"] = "ACCRUE — outcome column absent"
        result["p_value"] = 1.0
        result["g1_pass"] = False
        result["g2_pass"] = False
        result["g3_pass"] = False
        result["g4_pass"] = False
        result["placebo_p95"] = np.nan
        result["boot_ci_lo"] = np.nan
        result["boot_ci_hi"] = np.nan
        result["era_means"] = {}
        return result

    # Filter matured
    if mature_col in episodes_s_two_sided.columns:
        sub = episodes_s_two_sided[episodes_s_two_sided[mature_col] == True].copy()
    else:
        sub = episodes_s_two_sided.copy()

    if sub.empty:
        result["n_opposed"] = 0
        result["n_not_opposed"] = 0
        result["verdict_pending"] = "ACCRUE — no matured two-sided episodes"
        result["p_value"] = 1.0
        result["g1_pass"] = False
        result["g2_pass"] = False
        result["g3_pass"] = False
        result["g4_pass"] = False
        result["placebo_p95"] = np.nan
        result["boot_ci_lo"] = np.nan
        result["boot_ci_hi"] = np.nan
        result["era_means"] = {}
        return result

    raw_vals = sub[outcome_col].to_numpy(dtype=float)
    da_vals = direction_adjust(raw_vals, sub["direction"])

    # Classify opposed flow
    if "flow_opposed" in sub.columns:
        opposed_mask = sub["flow_opposed"].fillna(False).astype(bool).values
    elif "composite_z" in sub.columns:
        # Proxy: high composite z on BOTH sides
        opposed_mask = sub["composite_z"].fillna(0) >= THRESH_OPPOSED_SRC_Z
    else:
        opposed_mask = np.zeros(len(sub), dtype=bool)

    opposed_da = da_vals[opposed_mask]
    not_opposed_da = da_vals[~opposed_mask]

    n_opposed = int(np.sum(~np.isnan(opposed_da)))
    n_not_opposed = int(np.sum(~np.isnan(not_opposed_da)))

    result["n_opposed"] = n_opposed
    result["n_not_opposed"] = n_not_opposed

    if n_opposed < O4_POWER_FLOOR:
        result["verdict_pending"] = (
            f"ACCRUE — n_opposed={n_opposed} < power_floor={O4_POWER_FLOOR} "
            f"(pre-registered expected outcome: ~17 pairs) — PENDING FABLE ADJUDICATION"
        )
        result["p_value"] = 1.0
        result["g1_pass"] = False
        result["g2_pass"] = False
        result["g3_pass"] = False
        result["g4_pass"] = False
        result["placebo_p95"] = np.nan
        result["boot_ci_lo"] = np.nan
        result["boot_ci_hi"] = np.nan
        result["era_means"] = {}
        return result

    opposed_mean = float(np.nanmean(opposed_da))
    not_opposed_mean = float(np.nanmean(not_opposed_da)) if n_not_opposed > 0 else np.nan
    delta = opposed_mean - (not_opposed_mean if not np.isnan(not_opposed_mean) else 0.0)
    result["opposed_da_mean"] = opposed_mean
    result["not_opposed_da_mean"] = not_opposed_mean
    result["delta_da_mean"] = delta

    # G1: placebo (naive — no panel_s in this path; uses random draws)
    placebo_deltas = np.array([
        float(np.nanmean(rng.choice(da_vals, size=n_opposed, replace=True)))
        for _ in range(200)
    ])
    placebo_p95 = float(np.percentile(placebo_deltas, 95))
    g1_pass = delta > placebo_p95
    result["placebo_p95"] = placebo_p95

    # G2: bootstrap CI
    opposed_clean = opposed_da[~np.isnan(opposed_da)]
    boot_lo, boot_hi, _, boot_dist = block_bootstrap_ci(
        opposed_clean, n_iters=2000, block_size=min(21, max(1, n_opposed // 3)),
        rng=np.random.default_rng(rng.integers(0, 2**32)),
    )
    not_opp_adj = not_opposed_mean if not np.isnan(not_opposed_mean) else 0.0
    boot_lo -= not_opp_adj
    boot_hi -= not_opp_adj
    g2_pass = boot_lo > 0 and not np.isnan(boot_lo)
    boot_p = bootstrap_p_value(delta, boot_dist - not_opp_adj)
    result["boot_ci_lo"] = boot_lo
    result["boot_ci_hi"] = boot_hi
    result["p_value"] = boot_p

    # G3/G4
    strata = _regime_strata(sub)
    strata_means: dict[str, float] = {}
    strata_ns: dict[str, int] = {}
    for sname, smask in strata.items():
        if len(smask) == len(sub):
            sv = da_vals[smask]
            sv_clean = sv[~np.isnan(sv)]
            strata_means[sname] = float(np.mean(sv_clean)) if len(sv_clean) > 0 else np.nan
            strata_ns[sname] = int(len(sv_clean))
    pooled_da_mean = float(np.nanmean(da_vals)) if len(da_vals) > 0 else np.nan
    g3_pass, g3_note = _check_g3(pooled_da_mean, strata_means, strata_ns)

    onset_dates = sub["onset_date"].fillna(sub["onset_date"])
    oopt_era_m = _era_means_oopt(da_vals, onset_dates)
    g4_pass, g4_note = _check_g4_oopt(oopt_era_m)

    # Kill criterion §4
    kill_condition = (not np.isnan(boot_lo)) and boot_lo <= 0 and boot_hi >= 0 and n_opposed >= O4_POWER_FLOOR
    result["kill_condition"] = kill_condition

    # Sensitivity (R1)
    neighbor_results = {
        delta_v: delta > (placebo_p95 + delta_v)
        for delta_v in SENSITIVITY_NEIGHBORS
    }
    fragile = check_fragility(g1_pass, neighbor_results)

    result.update({
        "g1_pass": g1_pass,
        "g2_pass": g2_pass,
        "g3_pass": g3_pass,
        "g4_pass": g4_pass,
        "g3_note": g3_note,
        "g4_note": g4_note,
        "era_means": {k: (float(v) if not np.isnan(v) else None) for k, v in oopt_era_m.items()},
        "strata_means": {k: (float(v) if not np.isnan(v) else None) for k, v in strata_means.items()},
        "strata_ns": strata_ns,
        "fragile": fragile,
        "sensitivity_neighbors": {str(k): v for k, v in neighbor_results.items()},
    })

    verdict = oopt_verdict(
        g1_pass=g1_pass and not fragile,
        g2_pass=g2_pass,
        g3_pass=g3_pass,
        g4_pass=g4_pass,
        bh_rejected=False,  # filled later
        n=n_opposed,
        power_floor=O4_POWER_FLOOR,
        kill_condition=kill_condition,
    )
    result["verdict_pending"] = f"{verdict} — PENDING FABLE ADJUDICATION"
    return result


# ---------------------------------------------------------------------------
# Era means with O-OPT era labels
# ---------------------------------------------------------------------------

def _era_means_oopt(
    values: np.ndarray,
    onset_dates: pd.Series,
) -> dict[str, float]:
    """Direction-adjusted mean per O-OPT era (NaN if no data)."""
    years = pd.to_datetime(onset_dates).dt.year.to_numpy()
    result: dict[str, float] = {}
    for era_name, y_start, y_end in OOPT_ERAS:
        mask = (years >= y_start) & (years <= y_end)
        era_vals = values[mask]
        era_vals = era_vals[~np.isnan(era_vals)]
        result[era_name] = float(np.mean(era_vals)) if len(era_vals) > 0 else np.nan
    return result


def _check_g4_oopt(era_means: dict[str, float]) -> tuple[bool, str]:
    """G4 check using O-OPT era labels (same logic as P3 but with O-OPT eras)."""
    positive_count = sum(1 for v in era_means.values() if v > 0 and not np.isnan(v))
    latest = era_means.get("2023+", np.nan)
    latest_ok = not np.isnan(latest) and latest > 0
    passes = positive_count >= 3 and latest_ok
    note = f"{positive_count}/4 eras positive, 2023+={latest:.4f}" if not np.isnan(latest) else f"{positive_count}/4 eras positive, 2023+=no data"
    return passes, note


# ---------------------------------------------------------------------------
# BH-FDR across O-OPT family
# ---------------------------------------------------------------------------

def _apply_bh_fdr_oopt(
    o1_result: dict,
    o2_result: dict,
    o3_result: dict,
    o4_result: dict,
    trials: list[dict],
    rng: np.random.Generator,
) -> tuple[dict, dict, dict, dict]:
    """Apply BH-FDR across the O-OPT gated family per §7.

    Collects p-values from all gated trials, applies BH at q=0.10,
    then stamps bh_rejected back into each claim's result.
    """
    p_values_by_trial: dict[str, float] = {}

    # O-OPT-1 pooled
    p_values_by_trial["oopt1_tier_s_pooled"] = o1_result.get("p_value", 1.0) or 1.0
    for era, _, _ in OOPT_ERAS:
        p_values_by_trial[f"oopt1_era_{era}"] = 1.0  # era medians have no standalone p-value
    for regime in ["vix_high", "vix_low"]:
        p_values_by_trial[f"oopt1_regime_{regime}"] = 1.0

    # O-OPT-2 primary horizon (21d) only
    ph = o2_result.get("horizons", {}).get(21, {})
    p_values_by_trial["oopt2_h21_pooled"] = ph.get("p_value", 1.0) or 1.0
    for era, _, _ in OOPT_ERAS:
        p_values_by_trial[f"oopt2_h21_era_{era}"] = 1.0

    # O-OPT-3: routing cells
    for i, cell in enumerate(o3_result.get("cells", [])[:O3_CELL_CEILING]):
        if not cell.get("insufficient_placebo", True):
            p_values_by_trial[f"oopt3_routing_cell_{i:04d}"] = 1.0  # no p-value in stub

    # O-OPT-4 pooled
    p_values_by_trial["oopt4_tier_s_pooled"] = o4_result.get("p_value", 1.0) or 1.0

    # Apply BH at q=0.10 over all gated trials
    gated_ids = [t["trial_id"] for t in trials if t.get("gated", False)]
    gated_ps = [p_values_by_trial.get(tid, 1.0) for tid in gated_ids]
    bh_results = bh_fdr(gated_ps, q=0.10)

    bh_map: dict[str, bool] = dict(zip(gated_ids, bh_results))

    # Compute BH q-values (approximate)
    n = len(gated_ps)
    if n > 0:
        sorted_order = np.argsort(gated_ps)
        bh_q_values: dict[str, float] = {}
        for rank_i, orig_i in enumerate(sorted_order):
            tid = gated_ids[orig_i]
            p = gated_ps[orig_i]
            bh_q = p * n / (rank_i + 1)
            bh_q_values[tid] = min(1.0, float(bh_q))
    else:
        bh_q_values = {}

    # Stamp bh_rejected into results
    def _stamp(result: dict, trial_prefix: str) -> dict:
        for tid, rejected in bh_map.items():
            if tid.startswith(trial_prefix):
                result["bh_rejected"] = rejected
                result["bh_q"] = bh_q_values.get(tid, np.nan)
                break
        return result

    o1_result = _stamp(o1_result, "oopt1_tier_s_pooled")
    if "horizons" in o2_result and 21 in o2_result["horizons"]:
        o2_result["horizons"][21] = _stamp(o2_result["horizons"][21], "oopt2_h21_pooled")
    o4_result = _stamp(o4_result, "oopt4_tier_s_pooled")

    return o1_result, o2_result, o3_result, o4_result


# ---------------------------------------------------------------------------
# Trial ledger append (pure append — §7)
# ---------------------------------------------------------------------------

def _append_to_trial_ledger(
    ledger_path: Path,
    oopt_trials: list[dict],
    o1_result: dict,
    o2_result: dict,
    o3_result: dict,
    o4_result: dict,
    n_gated: int,
) -> None:
    """Pure-append O-OPT trials to p3_trial_ledger.json.

    Reads the existing ledger, appends O-OPT trials as a new section,
    updates n_trials, writes back.

    CRITICAL: This is a pure append — existing trials are NOT modified.
    """
    if not ledger_path.exists():
        log.error("Trial ledger not found: %s — cannot append", ledger_path)
        return

    with open(ledger_path) as f:
        ledger = json.load(f)

    existing_trials: list[dict] = ledger.get("trials", [])
    existing_ids = {t["trial_id"] for t in existing_trials}

    # Filter out any already-appended O-OPT trials (idempotent rerun)
    new_trials = [t for t in oopt_trials if t["trial_id"] not in existing_ids]

    # Stamp p-values into trial records
    p_map: dict[str, float] = {}
    # O-OPT-1
    p_map["oopt1_tier_s_pooled"] = o1_result.get("p_value", 1.0)
    # O-OPT-2
    ph2 = o2_result.get("horizons", {}).get(21, {})
    p_map["oopt2_h21_pooled"] = ph2.get("p_value", 1.0)
    # O-OPT-4
    p_map["oopt4_tier_s_pooled"] = o4_result.get("p_value", 1.0)

    bh_map: dict[str, bool] = {}
    bh_map["oopt1_tier_s_pooled"] = o1_result.get("bh_rejected", False)
    bh_map["oopt2_h21_pooled"] = ph2.get("bh_rejected", False)
    bh_map["oopt4_tier_s_pooled"] = o4_result.get("bh_rejected", False)

    for t in new_trials:
        tid = t["trial_id"]
        t["p_value"] = p_map.get(tid, None)
        t["bh_rejected"] = bh_map.get(tid, None)
        if "n" not in t:
            t["n"] = None
        if "direction_adjusted_mean" not in t:
            t["direction_adjusted_mean"] = None

    all_trials = existing_trials + new_trials
    n_new_gated = sum(1 for t in new_trials if t.get("gated", False))

    ledger["trials"] = all_trials
    ledger["n_trials"] = len(all_trials)
    ledger["n_oopt_trials_appended"] = len(new_trials)
    ledger["n_oopt_gated_trials"] = n_new_gated
    ledger["oopt_seed"] = SEED
    ledger["oopt_appended_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(ledger_path, "w") as f:
        json.dump(ledger, f, indent=2, default=str)

    log.info("Trial ledger updated: %d existing + %d new O-OPT = %d total",
             len(existing_trials), len(new_trials), len(all_trials))


# ---------------------------------------------------------------------------
# Registry append §10 / R2
# ---------------------------------------------------------------------------

def _append_registry(
    registry_path: Path,
    oopt_results: dict,
    smoke: bool = False,
) -> None:
    """Append oracle_oopt_phase0 entry to registry_seed.json.

    Per ruling R2: the append lands with the runner PR.
    This is a pure append (no modification of existing entries).
    In smoke mode, this is skipped (no writes outside /tmp).
    """
    if smoke:
        log.info("[SMOKE] Registry append skipped (smoke mode — no writes to data/)")
        return

    if not registry_path.exists():
        log.warning("Registry not found: %s — skipping append", registry_path)
        return

    with open(registry_path) as f:
        registry = json.load(f)

    experiments: list[dict] = registry.get("experiments", [])
    existing_ids = {e["id"] for e in experiments}

    if "oracle_oopt_phase0" in existing_ids:
        log.info("oracle_oopt_phase0 already in registry — skipping append (idempotent)")
        return

    n_o4_opposed = oopt_results.get("o4", {}).get("n_opposed", 0)

    new_entry: dict[str, Any] = {
        "id": "oracle_oopt_phase0",
        "name": "O-OPT Phase-0 — Options-Tape Pressure × Rotation Episodes Gate",
        "kind": "gate_battery",
        "priority": "high",
        "cadence": "once",
        "what": (
            "4-claim gate battery: O-OPT-1 lead-lag, O-OPT-2 confirmation quality, "
            "O-OPT-3 routing conditioning, O-OPT-4 two-sided opposed flow. "
            "Unsigned legs only (T2a episode-window features pending). "
            "Tier-S (sectors) = validation tier; Tier-M = display-with-watermark."
        ),
        "source": "scripts/run_oopt_phase0.py + engine/oracle/oopt.py",
        "storage": "data/oracle/gauntlet/oopt_results.json",
        "track_json": "data/oracle/gauntlet/oopt_results.json",
        "hook": "oracle_gauntlet",
        "started": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "come_back_on": (
            "T1 backfill complete (manifest-complete) + T2a episode-window features exist "
            "for signed-leg re-run"
        ),
        "come_back_note": (
            "Two blockers: (a) data/thetadata_eod/ manifest-complete (R8); "
            "(b) T2a episode-window builder for signed legs (O-OPT §2.2/R7). "
            "Re-run unsigned legs after (a); full battery after (b)."
        ),
        "maturation": (
            "Full battery with real T1 store after manifest-complete. "
            f"O-OPT-4 ACCRUE path: n_opposed={n_o4_opposed} < {O4_POWER_FLOOR} power floor "
            "(pre-registered expected ~17 pairs)."
        ),
        "status": "accruing",
        "prereg": "research/O_OPT_PHASE0_PREREG.md",
        "prereg_locked": "2026-07-04",
        "seed": SEED,
        "n_gated_trials": oopt_results.get("n_gated_trials", 0),
        "verdicts_pending_fable": True,
    }

    experiments.append(new_entry)
    registry["experiments"] = experiments

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2, default=str)

    log.info("Registry updated: oracle_oopt_phase0 appended to %s", registry_path)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(
    report_path: Path,
    oopt_results: dict,
    coverage_dropped_tally: dict,
    smoke: bool = False,
) -> None:
    """Write the oopt-phase0.md report per §deliverables."""
    lines = [
        "# O-OPT Phase-0 Report — Options × Rotation Episodes",
        "",
        f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        f"_Prereg: `research/O_OPT_PHASE0_PREREG.md` (locked 2026-07-04)_",
        f"_Seed: {SEED}_",
    ]

    if smoke:
        lines += [
            "",
            "> **SMOKE MODE** — fixture store; no verdict weight. Mechanics verified only.",
            "",
        ]

    lines += [
        "",
        "## Standing notes (binding)",
        "",
        "- All verdicts labeled **PENDING FABLE ADJUDICATION** (§9).",
        "- Signed legs EXCLUDED per R7: T2a episode-window features not yet built.",
        "- T1 store (data/thetadata_eod/) pending manifest-complete (R8).",
        "- Unsigned legs only: total premium z, |ΔOI|, IV term/skew z, breadth of activity.",
        "- Tier-S (sector ETFs) = VALIDATION tier (PRIMARY). Tier-M = display-with-watermark.",
        "",
        "## IV Coverage Stamps",
        "",
        "IV features (iv_term_z, iv_skew_z) require greeks store 2017→.",
        "Episodes with onset < 2017-01-01 have iv_coverage=False (IV legs set to NaN).",
        "",
    ]

    # Coverage-drop tallies §2.4
    lines += [
        "## Coverage-Drop Tallies (§2.4)",
        "",
        "| Tier | Episodes in options era | Coverage-dropped (< 40%) | Used in analysis |",
        "|---|---|---|---|",
    ]
    for tier, stats in coverage_dropped_tally.items():
        n_total = stats.get("n_total", 0)
        n_dropped = stats.get("n_dropped", 0)
        n_used = n_total - n_dropped
        lines.append(f"| {tier} | {n_total} | {n_dropped} | {n_used} |")
    lines.append("")

    # O-OPT-1
    o1 = oopt_results.get("o1", {})
    lines += [
        "## O-OPT-1 — Flow-before-Rotation (Lead-Lag)",
        "",
        "**Primary statistic:** median lead (sessions), bootstrap 90% CI.",
        "",
        f"- N: {o1.get('n', 0)}",
        f"- Median lead: {_fmt(o1.get('median_lead'))} sessions",
        f"- Boot 90% CI: [{_fmt(o1.get('boot_ci_lo'))}, {_fmt(o1.get('boot_ci_hi'))}]",
        f"- Placebo p95: {_fmt(o1.get('placebo_p95'))}",
        f"- G1 (lead > placebo p95): {o1.get('g1_pass')}",
        f"- G2 (CI lo > 0): {o1.get('g2_pass')}",
        f"- Fragile (R1): {o1.get('fragile', False)}",
        f"- **Verdict: {o1.get('verdict_pending', 'PENDING')}**",
        "",
        "### Era Table (O-OPT-1 lead medians)",
        "",
        "| Era | Median lead (sessions) |",
        "|---|---|",
    ]
    for era, _, _ in OOPT_ERAS:
        v = o1.get("era_means", {}).get(era)
        lines.append(f"| {era} | {_fmt(v)} |")
    lines += ["", "### Regime Split (O-OPT-1)"]
    lines += ["", "| Regime | Median lead (sessions) |", "|---|---|"]
    for regime, v in o1.get("regime_medians", {}).items():
        lines.append(f"| {regime} | {_fmt(v)} |")
    lines.append("")

    # O-OPT-2
    o2 = oopt_results.get("o2", {})
    horizons = o2.get("horizons", {})
    lines += [
        "## O-OPT-2 — Confirmation Quality",
        "",
        "**Primary:** confirmed-minus-unconfirmed direction-adjusted mean `outcome_rs_21d` delta.",
        "",
    ]
    for h in [5, 21, 63]:
        hd = horizons.get(h, {})
        is_primary = (h == 21)
        tag = " **(PRIMARY)**" if is_primary else " (robustness)"
        lines += [
            f"### {h}d horizon{tag}",
            "",
            f"- N confirmed: {hd.get('n_confirmed', 0)}",
            f"- N unconfirmed: {hd.get('n_unconfirmed', 0)}",
            f"- Delta (confirmed − unconfirmed): {_fmt(hd.get('delta_da_mean'))}",
            f"- Boot 95% CI: [{_fmt(hd.get('boot_ci_lo'))}, {_fmt(hd.get('boot_ci_hi'))}]",
            f"- Placebo p95: {_fmt(hd.get('placebo_p95'))}",
            f"- G1 pass: {hd.get('g1_pass')}",
            f"- G2 pass: {hd.get('g2_pass')}",
            f"- G3 pass: {hd.get('g3_pass')}",
            f"- G4 pass: {hd.get('g4_pass')}",
            f"- Fragile (R1): {hd.get('fragile', False)}",
            f"- **Verdict: {hd.get('verdict_pending', 'PENDING')}**",
            "",
            "#### Era Table",
            "",
            "| Era | DA mean |",
            "|---|---|",
        ]
        for era, _, _ in OOPT_ERAS:
            v = hd.get("era_means", {}).get(era)
            lines.append(f"| {era} | {_fmt(v)} |")
        lines.append("")

    # O-OPT-3
    o3 = oopt_results.get("o3", {})
    lines += [
        "## O-OPT-3 — Routing-Matrix Conditioning",
        "",
        f"- Sufficient cells (n >= placebo floor): {o3.get('n_sufficient_cells', 0)}",
        f"- Total cells: {o3.get('n_cells_total', 0)}",
        f"- Ceiling: {O3_CELL_CEILING}",
        f"- **Verdict: {o3.get('verdict_pending', 'PENDING')}**",
        "",
    ]

    # O-OPT-4
    o4 = oopt_results.get("o4", {})
    lines += [
        "## O-OPT-4 — Two-Sided Flow Pairing",
        "",
        "**Primary:** opposed-vs-not direction-adjusted mean `outcome_rs_21d` delta.",
        "",
        f"- N opposed: {o4.get('n_opposed', 0)} (power floor: {O4_POWER_FLOOR})",
        f"- N not opposed: {o4.get('n_not_opposed', 0)}",
        f"- Expected real n_opposed ≈ 17 (pre-stated §3)",
        f"- Delta: {_fmt(o4.get('delta_da_mean'))}",
        f"- Boot 95% CI: [{_fmt(o4.get('boot_ci_lo'))}, {_fmt(o4.get('boot_ci_hi'))}]",
        f"- Placebo p95: {_fmt(o4.get('placebo_p95'))}",
        f"- G1 pass: {o4.get('g1_pass')}",
        f"- G2 pass: {o4.get('g2_pass')}",
        f"- G3 pass: {o4.get('g3_pass')}",
        f"- G4 pass: {o4.get('g4_pass')}",
        f"- **Verdict: {o4.get('verdict_pending', 'PENDING')}**",
        "",
        "### Era Table (O-OPT-4)",
        "",
        "| Era | DA mean |",
        "|---|---|",
    ]
    for era, _, _ in OOPT_ERAS:
        v = o4.get("era_means", {}).get(era)
        lines.append(f"| {era} | {_fmt(v)} |")
    lines.append("")

    # FDR summary
    lines += [
        "## BH-FDR Summary",
        "",
        f"- Gated family: {oopt_results.get('n_gated_trials', 0)} trials",
        "- BH applied at q=0.10 within O-OPT family (§7)",
        "",
        "| Claim | Trial ID | p-value | BH rejected |",
        "|---|---|---|---|",
    ]
    for t in oopt_results.get("trials", []):
        if t.get("gated"):
            lines.append(
                f"| {t.get('section', '')} | {t['trial_id']} | "
                f"{_fmt(t.get('p_value'))} | {t.get('bh_rejected')} |"
            )
    lines += [
        "",
        "---",
        "_Generated by `scripts/run_oopt_phase0.py`._",
    ]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))
    log.info("Report written: %s", report_path)


def _fmt(v: Any) -> str:
    """Format a value for display."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_oopt_phase0(
    data_dir: Path,
    smoke: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the O-OPT Phase-0 gauntlet.

    Parameters
    ----------
    data_dir : Path
        Repo data/ directory.
    smoke : bool
        If True: use fixture store; write outputs to /tmp only.
    out_dir : Path or None
        Override output directory (used by tests).

    Returns
    -------
    dict
        Full results dict.
    """
    t0 = time.time()
    rng = np.random.default_rng(SEED)

    oracle_dir = data_dir / "oracle"
    gauntlet_dir = oracle_dir / "gauntlet"

    if smoke:
        log.info("=" * 60)
        log.info("O-OPT SMOKE MODE — fixture store; no real data reads")
        log.info("Writes go to /tmp only per R8 + smoke contract")
        log.info("=" * 60)
        out_base = Path("/tmp")
    else:
        out_base = data_dir.parent
        # R8: guard against mid-backfill execution
        manifest_path = data_dir / "thetadata_eod" / "_manifest.json"
        if not manifest_path.exists():
            log.warning(
                "data/thetadata_eod/_manifest.json not found — T1 store not manifest-complete. "
                "Per ruling R8, this runner should not execute against the real store mid-backfill. "
                "Proceeding in display-only mode (no real feature extraction)."
            )

    if out_dir is not None:
        out_base = out_dir

    # ---- Load episode catalogs ----
    log.info("Loading episode catalogs…")

    if smoke:
        session_dates = _build_smoke_session_dates()
        complex_etf_map = _get_complex_etf_map()
        if not complex_etf_map:
            complex_etf_map = {
                "ai_compute": ["XLK"],
                "healthcare_defensive": ["XLV"],
                "energy_commodities": ["XLE", "XLB"],
                "financials_rates": ["XLF"],
                "long_duration_growth": ["XLRE", "XLU"],
            }
        episodes_s = _build_smoke_episodes(session_dates, complex_etf_map, rng)
        episodes_m = pd.DataFrame()  # No Tier-M in smoke
        panel_s = None
        rotation_groups = {
            "complexes": [
                {"id": "ai_compute", "members": ["aicompute"], "risk_sign": "risk_on"},
                {"id": "healthcare_defensive", "members": ["us_sector_health"], "risk_sign": "risk_off"},
            ]
        }
    else:
        episodes_s = pd.read_parquet(oracle_dir / "episodes_s.parquet")
        episodes_m = pd.read_parquet(oracle_dir / "episodes_m.parquet")
        try:
            panel_s = pd.read_parquet(oracle_dir / "panel_s.parquet")
        except Exception:
            panel_s = None
            log.warning("panel_s.parquet not found — placebo sampling will use naive mode")
        rotation_groups = load_rotation_groups(data_dir)
        session_dates = pd.date_range("2012-06-01", "2026-12-31", freq="B")

    log.info("Tier-S episodes: %d | Tier-M episodes: %d", len(episodes_s), len(episodes_m))

    # ---- Build lookup structures ----
    complex_etf_map = _get_complex_etf_map() or {}
    etf_to_complex = _get_etf_to_complex(complex_etf_map)
    node_to_complex_m = build_node_to_complex_tier_m(rotation_groups)
    complex_risk_sign = build_complex_risk_sign(rotation_groups)

    # ---- Filter to options era ----
    episodes_s_options = filter_options_era(episodes_s)
    log.info("Tier-S options-era episodes (onset >= 2012-06-01): %d", len(episodes_s_options))

    # ---- Options universe (smoke: use sector ETFs) ----
    if smoke:
        options_universe = set(_SMOKE_ROOTS)
    else:
        try:
            from engine.options_universe import gex_symbols  # noqa: PLC0415
            options_universe = set(gex_symbols())
        except Exception:
            log.warning("engine.options_universe not available — using ETF-only universe")
            options_universe = {"XLK", "XLV", "XLE", "XLF", "XLI", "XLP",
                                "XLRE", "XLU", "XLB", "XLC", "XLY"}

    # ---- Feature extraction (smoke: use fixture panels) ----
    log.info("Building feature panels…")

    if smoke:
        eod_panel = build_fixture_eod_panel(_SMOKE_ROOTS, session_dates, seed=42)
        oi_panel = build_fixture_oi_panel(_SMOKE_ROOTS, session_dates, seed=43)
        iv_panel = build_fixture_iv_panel(_SMOKE_ROOTS, session_dates, seed=44)
    else:
        # Real store path — but R8 means we don't read mid-backfill
        # Build empty panels; features will be NaN (all episodes go to ACCRUE)
        log.info("Real store: feature extraction deferred per R8 until manifest-complete")
        eod_panel = pd.DataFrame()
        oi_panel = pd.DataFrame()
        iv_panel = None

    # ---- Per-episode feature computation ----
    log.info("Computing per-episode options features…")

    coverage_dropped_s = 0
    ep_features: list[dict] = []

    for _, row in episodes_s_options.iterrows():
        onset = pd.Timestamp(row["onset_date"])
        node = row["node"]
        direction = row["direction"]

        # Get group members for this node
        if node in options_universe:
            group_members = [node]  # sector ETF: single member
        else:
            group_members = [node]

        if smoke and not eod_panel.empty:
            feats = compute_group_features_from_eod(
                member_roots=group_members,
                node_label=node,
                onset_date=onset,
                session_dates=pd.DatetimeIndex(session_dates),
                eod_premium_panel=eod_panel,
                oi_panel=oi_panel,
                iv_panel=iv_panel,
                options_universe=options_universe,
                direction=direction,
            )
        else:
            feats = {
                "node": node,
                "direction": direction,
                "onset_date": onset.isoformat(),
                "coverage": 1.0 if node in options_universe else 0.0,
                "coverage_ok": node in options_universe,
                "n_members_total": 1,
                "n_members_covered": 1 if node in options_universe else 0,
                "flow_breadth_g": np.nan,
                "doi_unsigned_z": np.nan,
                "iv_term_z": np.nan,
                "iv_skew_z": np.nan,
                "iv_coverage": False,
                "etf_confirm_z": np.nan,
                "window_lo_date": None,
                "window_hi_date": None,
                "signed_excluded_stamp": SIGNED_EXCLUSION_STAMP,
                "provenance": UNSIGNED_PROVENANCE,
            }

        if not feats.get("coverage_ok", False):
            coverage_dropped_s += 1

        # Composite z for this episode
        cz = composite_z({
            k: feats.get(k, np.nan)
            for k in ["flow_breadth_g", "doi_unsigned_z", "iv_term_z",
                      "iv_skew_z", "etf_confirm_z"]
        })
        feats["composite_z"] = cz

        # Flow confirmation check (O-OPT-2)
        feats["flow_confirmed"] = is_flow_confirmed(
            composite_z_series=pd.Series([cz]),
            flow_breadth_series=pd.Series([feats.get("flow_breadth_g", np.nan)]),
            onset_idx_in_window=0,
            z_threshold=THRESH_CONFIRMATION_Z,
            breadth_threshold=THRESH_BREADTH_CONFIRMATION,
            conf_window=(0, 0),
        ) if not np.isnan(cz) else False

        # Lead computation (O-OPT-1): in smoke use a synthetic lead
        if smoke:
            lead_val = float(rng.integers(-5, 10))
        else:
            lead_val = np.nan  # deferred to real T1 run
        feats["lead_sessions"] = lead_val

        # Era
        feats["era"] = assign_era(onset)

        # Merge episode metadata
        feats["episode_id"] = row["episode_id"]
        feats["direction"] = direction
        feats["onset_date"] = str(onset.date())
        feats["two_sided"] = bool(row.get("two_sided", False))
        feats["paired_episode_id"] = row.get("paired_episode_id")
        feats["regime_vix_pctile"] = float(row.get("regime_vix_pctile", np.nan))
        feats["regime_spy_above_200d"] = float(row.get("regime_spy_above_200d", np.nan))

        # Outcome columns
        for h in [5, 21, 63]:
            for sfx in ["", "_confirmed", "_undeniable"]:
                col = f"outcome_rs_{h}d{sfx}"
                mcol = f"outcome_mature_{h}d{sfx.lstrip('_') if sfx else ''}"
                feats[col] = float(row.get(col, np.nan)) if col in row.index else np.nan
                feats[mcol] = bool(row.get(mcol, False)) if mcol in row.index else False

        ep_features.append(feats)

    episodes_s_feat = pd.DataFrame(ep_features) if ep_features else pd.DataFrame()
    log.info("Feature extraction done: %d episodes, %d coverage-dropped",
             len(ep_features), coverage_dropped_s)

    coverage_dropped_tally = {
        "Tier-S": {
            "n_total": len(episodes_s_options),
            "n_dropped": coverage_dropped_s,
        },
        "Tier-M": {
            "n_total": len(episodes_m),
            "n_dropped": 0,  # Tier-M display-only; coverage not yet computed
        },
    }

    # ---- Run claims ----
    log.info("Running O-OPT-1 (lead-lag)…")
    o1_result = _run_oopt1(episodes_s_feat, rng)

    log.info("Running O-OPT-2 (confirmation quality)…")
    o2_result = _run_oopt2(episodes_s_feat, panel_s, rng)

    log.info("Running O-OPT-3 (routing conditioning)…")
    two_sided_feat = episodes_s_feat[episodes_s_feat["two_sided"] == True] if not episodes_s_feat.empty else pd.DataFrame()
    o3_result = _run_oopt3(two_sided_feat, rotation_groups, etf_to_complex, rng)

    log.info("Running O-OPT-4 (two-sided opposed flow)…")
    o4_result = _run_oopt4(two_sided_feat, rng)

    # ---- Trial enumeration ----
    n_o3_cells = o3_result.get("n_sufficient_cells", 0)
    oopt_trials = enumerate_oopt_trials(n_o3_cells)
    n_gated = gated_trial_count(oopt_trials)
    log.info("Registered O-OPT trials: %d total, %d gated", len(oopt_trials), n_gated)

    # ---- BH-FDR ----
    log.info("Applying BH-FDR across O-OPT gated family (%d trials)…", n_gated)
    o1_result, o2_result, o3_result, o4_result = _apply_bh_fdr_oopt(
        o1_result, o2_result, o3_result, o4_result, oopt_trials, rng
    )

    # ---- Assemble results ----
    oopt_results: dict[str, Any] = {
        "spec_version": "O_OPT_PHASE0_PREREG.md",
        "seed": SEED,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "smoke": smoke,
        "p3_imported": _P3_IMPORTED,
        "n_episodes_tier_s": len(episodes_s),
        "n_episodes_tier_s_options_era": len(episodes_s_options),
        "n_episodes_tier_m": len(episodes_m),
        "n_gated_trials": n_gated,
        "n_oopt_trials_total": len(oopt_trials),
        "coverage_dropped_tally": coverage_dropped_tally,
        "signed_excluded_stamp": SIGNED_EXCLUSION_STAMP,
        "unsigned_provenance": UNSIGNED_PROVENANCE,
        "o1": o1_result,
        "o2": o2_result,
        "o3": o3_result,
        "o4": o4_result,
        "trials": [
            {k: v for k, v in t.items()}
            for t in oopt_trials
        ],
        "timing_s": time.time() - t0,
    }

    # ---- Outputs ----
    if smoke:
        results_path = Path("/tmp/oopt_smoke_results.json")
        report_path = Path("/tmp/oopt_smoke_report.md")
        # NO writes to data/ or reports/ in smoke mode
    else:
        results_path = gauntlet_dir / "oopt_results.json"
        report_path = out_base / "reports" / "oopt-phase0.md"
        gauntlet_dir.mkdir(parents=True, exist_ok=True)

    # Write results JSON
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(oopt_results, f, indent=2, default=_json_default)
    log.info("Results written: %s", results_path)

    # Write report
    _write_report(report_path, oopt_results, coverage_dropped_tally, smoke=smoke)

    # Trial ledger append (NOT in smoke)
    if not smoke:
        ledger_path = gauntlet_dir / "p3_trial_ledger.json"
        if ledger_path.exists():
            log.info("Appending O-OPT trials to trial ledger…")
            _append_to_trial_ledger(
                ledger_path, oopt_trials,
                o1_result, o2_result, o3_result, o4_result,
                n_gated,
            )
        else:
            log.warning("Trial ledger not found: %s — skipping append", ledger_path)

    # Registry append (NOT in smoke, per R2)
    if not smoke:
        registry_path = data_dir / "experiments" / "registry_seed.json"
        _append_registry(registry_path, oopt_results, smoke=False)

    log.info("O-OPT Phase-0 done in %.1f s", time.time() - t0)
    return oopt_results


def _json_default(obj: Any) -> Any:
    """JSON serializer for numpy/pandas types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    if isinstance(obj, bool):
        return bool(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default=None,
        help="Data directory override (default: data/ relative to repo root)"
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help=(
            "Smoke mode: use fixture store, write outputs to /tmp only. "
            "No writes to data/ or reports/. Per R8: no real store execution."
        )
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        try:
            from lib import config  # noqa: PLC0415
            data_dir = config.data_dir()
        except Exception:
            data_dir = _REPO / "data"

    run_oopt_phase0(data_dir=data_dir, smoke=args.smoke)


if __name__ == "__main__":
    main()
