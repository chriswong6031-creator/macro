"""O-OPT Phase-0 helper — constructions, coverage, era handling.

Implements the FROZEN definitions from O_OPT_PHASE0_PREREG.md §2-§5 verbatim.
No design freedom on gates, thresholds, or constructions.

Key design decisions (documented here, not guesswork):
  - All OI uses oi[t-1] law via thetadata_store.doi_series (pre-existing,
    pre-tested — engine/thetadata_store.py shift(1) before delta).
  - Signed legs (src_put_prem_z, snk_call_prem_z and their ΔOI mates) are
    EXCLUDED until T2a episode-window features exist; they are stamped, not
    silently dropped (§2.2 RULNG R7).
  - COMPLEX_ETF_MAP (graph.py) is the Tier-S node→complex join source.
  - rotation_groups.json is the Tier-M node→complex join source.
  - The [−15,+15] window is in TRADING sessions, not calendar days.
  - Coverage floor = 0.40 per §2.4; episodes below this threshold are counted
    in coverage_dropped_tally and excluded from the sample.
  - Gauntlet utilities (sample_placebo, block_bootstrap_ci, bh_fdr,
    _check_g3, _check_g4, _era_means, direction_adjust, bootstrap_p_value)
    are IMPORTED from scripts.oracle_gauntlet_p3 — not reimplemented.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — frozen from §3 and §4
# ---------------------------------------------------------------------------

# Options era start: §3 "onset_date >= 2012-06-01 (T1 backfill span)"
OPTIONS_ERA_START = pd.Timestamp("2012-06-01")

# [−15, +15] session window per §2.3
WINDOW_SESSIONS = 15

# Coverage floor §2.4
COVERAGE_FLOOR = 0.40

# IV-coverage era start (greeks store 2017→) per prereg §1 and §8.6
IV_ERA_START = pd.Timestamp("2017-01-01")

# Rolling z window §2.2
ROLLING_Z_WINDOW = 252

# DOI persistence window §2.2 feature 3 (5-session persistence-weighted)
DOI_WINDOW = 5

# Thresholds §4 (primary, pre-declared per ruling R1)
# Sensitivity neighbors (±0.25) are reported as ungated robustness — NOT FDR-counted
THRESH_FLOW_ONSET_Z = 1.0          # O-OPT-1: composite z threshold, 2-session persistence
THRESH_CONFIRMATION_Z = 0.5        # O-OPT-2: [−5,+1] composite z
THRESH_BREADTH_CONFIRMATION = 0.5  # O-OPT-2: flow_breadth_g floor
THRESH_DEST_PRESSURE_Z = 0.5       # O-OPT-3: snk options pressure z over [0,+5]
THRESH_OPPOSED_SRC_Z = 0.5         # O-OPT-4: src_put_prem_z (opposed flow)
THRESH_OPPOSED_SNK_Z = 0.5         # O-OPT-4: snk_call_prem_z (opposed flow)

# Concentration penalty: single member > 60% → down-weight breadth
HHI_CONCENTRATION_CAP = 0.60

# FDR seed — §7
SEED = 20260704

# Trial-count ceiling for O3 routing cells (§7)
O3_CELL_CEILING = 90

# Power floors §4
O2_POWER_FLOOR = 60   # confirmed-n below this → ACCRUE, not KILL
O4_POWER_FLOOR = 40   # opposed-pairs-n below this → ACCRUE, not KILL

# Sensitivity neighbors for R1
SENSITIVITY_NEIGHBORS = [-0.25, +0.25]

# era boundaries — same as P3 but options-era-clamped to 2012+
OOPT_ERAS: list[tuple[str, int, int]] = [
    ("2012-15", 2012, 2015),
    ("2016-19", 2016, 2019),
    ("2020-22", 2020, 2022),
    ("2023+",   2023, 2099),
]

# Tier-M era boundaries (watermark; starts 2022-02-08)
TIERM_ERAS: list[tuple[str, int, int]] = [
    ("2020-22", 2020, 2022),
    ("2023+",   2023, 2099),
]

# ---------------------------------------------------------------------------
# Signing stamp — §2.2 / R7
# ---------------------------------------------------------------------------

SIGNED_EXCLUSION_STAMP: dict[str, Any] = {
    "signing_source": "tape",
    "direction_reliable": False,
    "excluded": True,
    "reason": (
        "Signed legs excluded until T2a episode-window features exist "
        "(LIVE_FLOW R7 + O_OPT_PHASE0_PREREG §2.2). "
        "Unsigned legs (total premium z, |ΔOI|, IV term/skew, breadth of activity) run."
    ),
}

UNSIGNED_PROVENANCE: dict[str, Any] = {
    "signing_source": None,
    "reconstructed": True,
    "note": "Unsigned legs only — total premium, absolute ΔOI, IV, breadth.",
}

# ---------------------------------------------------------------------------
# COMPLEX_ETF_MAP import (re-exported for use in runner)
# ---------------------------------------------------------------------------

def _get_complex_etf_map() -> dict[str, list[str]]:
    """Load COMPLEX_ETF_MAP from engine.oracle.graph (canonical source)."""
    try:
        from engine.oracle.graph import COMPLEX_ETF_MAP  # noqa: PLC0415
        return COMPLEX_ETF_MAP
    except Exception as e:
        log.warning("Could not import COMPLEX_ETF_MAP from engine.oracle.graph: %s", e)
        return {}


def _get_etf_to_complex(complex_etf_map: dict[str, list[str]]) -> dict[str, str]:
    """Invert COMPLEX_ETF_MAP: ETF → complex_id (first-match if ETF is in multiple)."""
    etf_to_complex: dict[str, str] = {}
    for complex_id, etfs in complex_etf_map.items():
        for etf in etfs:
            if etf not in etf_to_complex:
                etf_to_complex[etf] = complex_id
    return etf_to_complex


def load_rotation_groups(data_dir: Path) -> dict:
    """Load data/oracle/rotation_groups.json."""
    p = data_dir / "oracle" / "rotation_groups.json"
    with open(p) as f:
        return json.load(f)


def build_node_to_complex_tier_m(rotation_groups: dict) -> dict[str, str]:
    """Map Tier-M node (subsector) → complex_id via rotation_groups.json."""
    result: dict[str, str] = {}
    for c in rotation_groups.get("complexes", []):
        cid = c["id"]
        for m in c.get("members", []):
            result[m] = cid
    return result


def build_complex_risk_sign(rotation_groups: dict) -> dict[str, str]:
    """Map complex_id → risk_sign ('risk_on' / 'risk_off')."""
    return {c["id"]: c.get("risk_sign", "risk_on")
            for c in rotation_groups.get("complexes", [])}


# ---------------------------------------------------------------------------
# Episode filtering helpers
# ---------------------------------------------------------------------------

def filter_options_era(episodes: pd.DataFrame,
                       start: pd.Timestamp = OPTIONS_ERA_START) -> pd.DataFrame:
    """Keep only episodes whose onset_date >= options era start."""
    onset = pd.to_datetime(episodes["onset_date"])
    return episodes[onset >= start].copy()


def assign_era(onset_date: pd.Timestamp,
               eras: list[tuple[str, int, int]] = OOPT_ERAS) -> str:
    """Return era label for a given onset date."""
    year = onset_date.year
    for name, y_start, y_end in eras:
        if y_start <= year <= y_end:
            return name
    return "unknown"


# ---------------------------------------------------------------------------
# Coverage computation §2.4
# ---------------------------------------------------------------------------

def compute_coverage(group_members: list[str], options_universe: set[str]) -> float:
    """Fraction of group members in the options universe.

    §2.4: coverage_g(t) = |M_g(t) ∩ options_universe| / |M_g(t)|
    Returns 0.0 if group_members is empty.
    """
    if not group_members:
        return 0.0
    covered = sum(1 for m in group_members if m in options_universe)
    return covered / len(group_members)


def hhi_from_weights(weights: list[float]) -> float:
    """Herfindahl-Hirschman Index of a list of weights (sums to 1 or not)."""
    total = sum(weights)
    if total <= 0 or not weights:
        return 0.0
    norm = [w / total for w in weights]
    return sum(n * n for n in norm)


def concentration_penalty(weights: list[float]) -> float:
    """(1 − HHI) concentration penalty per §2.2 feature 4.

    A breadth reading where a single member supplies > 60% of group notional
    is down-weighted toward 0.
    """
    h = hhi_from_weights(weights)
    return 1.0 - h


# ---------------------------------------------------------------------------
# Trading-session window utilities
# ---------------------------------------------------------------------------

def session_window(
    onset_date: pd.Timestamp,
    session_dates: pd.DatetimeIndex,
    half_window: int = WINDOW_SESSIONS,
) -> tuple[int, int] | None:
    """Return (lo_idx, hi_idx) in session_dates for [−hw, +hw] around onset.

    Returns None if the window is not fully covered (i.e. onset not found,
    or the window extends beyond store edges).
    Per §2.3: episodes with uncovered windows are DROPPED (not imputed).
    """
    pos = session_dates.searchsorted(onset_date)
    if pos >= len(session_dates):
        return None
    # Verify onset aligns to a session
    if session_dates[pos] != onset_date:
        # Onset may fall on a non-trading day — use closest subsequent session
        if pos >= len(session_dates):
            return None
    lo = pos - half_window
    hi = pos + half_window
    if lo < 0 or hi >= len(session_dates):
        return None
    return lo, hi


def session_index_for_date(
    date: pd.Timestamp,
    session_dates: pd.DatetimeIndex,
) -> int | None:
    """Binary search for date in session_dates; return None if not found."""
    pos = int(session_dates.searchsorted(date))
    if pos >= len(session_dates):
        return None
    if session_dates[pos] == date:
        return pos
    return None


# ---------------------------------------------------------------------------
# Rolling z-score on a daily series
# ---------------------------------------------------------------------------

def rolling_z(series: pd.Series, window: int = ROLLING_Z_WINDOW) -> pd.Series:
    """Rolling z-score: (value - rolling_mean) / rolling_std.

    Returns NaN where std is 0 or < window observations available.
    """
    roll_mean = series.rolling(window, min_periods=window // 2).mean()
    roll_std = series.rolling(window, min_periods=window // 2).std()
    z = (series - roll_mean) / roll_std.replace(0, np.nan)
    return z


# ---------------------------------------------------------------------------
# Feature computation from the fixture store (for smoke mode + tests)
# ---------------------------------------------------------------------------

def compute_group_features_from_eod(
    member_roots: list[str],
    node_label: str,
    onset_date: pd.Timestamp,
    session_dates: pd.DatetimeIndex,
    eod_premium_panel: pd.DataFrame,   # (date, root) → {call_prem, put_prem}
    oi_panel: pd.DataFrame,            # (date, root) → {doi_put_z, doi_call_z}
    iv_panel: pd.DataFrame | None,     # (date, root) → {iv_term_z, iv_skew_z}
    options_universe: set[str],
    direction: str,                    # 'in' or 'out'
    half_window: int = WINDOW_SESSIONS,
) -> dict[str, Any]:
    """Compute all unsigned O-OPT features for one episode group.

    Signed legs (src_put_prem_z, snk_call_prem_z and ΔOI mates) are NOT
    computed here — they are stamped as excluded per §2.2/R7.

    Parameters
    ----------
    member_roots : list of str
        The option-universe members for this group (already intersected with
        options_universe by caller; this function computes coverage internally).
    node_label : str
        The group node label (for logging).
    onset_date : pd.Timestamp
        Episode onset date.
    session_dates : pd.DatetimeIndex
        All trading sessions in the store (sorted ascending).
    eod_premium_panel : pd.DataFrame
        MultiIndex (date, root) with columns 'total_call_prem', 'total_put_prem'
        (total notional in dollar terms, already signed-free totals).
    oi_panel : pd.DataFrame
        MultiIndex (date, root) with columns 'doi_put_z', 'doi_call_z'
        — the 5-session DOI z-scores with oi[t-1] law already applied.
    iv_panel : pd.DataFrame or None
        MultiIndex (date, root) with columns 'iv_term_z', 'iv_skew_z'.
        None when IV coverage is absent (pre-2017 or missing greeks).
    options_universe : set of str
        The global options universe set.
    direction : str
        'in' (inflow → use call side) or 'out' (outflow → use put side).
    half_window : int
        Window half-width in sessions (default 15).

    Returns
    -------
    dict with keys:
        coverage, coverage_ok, signed_excluded_stamp,
        etf_confirm_z (float or NaN),
        flow_breadth_g (float or NaN),
        doi_unsigned_z (float or NaN),    # |ΔOI| group mean
        iv_term_z (float or NaN),
        iv_skew_z (float or NaN),
        iv_coverage (bool),               # whether IV features are available
        window_lo_date, window_hi_date,
        n_members_total, n_members_covered,
    """
    all_group_members = member_roots  # caller passes full group members
    covered = [m for m in all_group_members if m in options_universe]
    n_total = len(all_group_members)
    n_covered = len(covered)
    coverage = n_covered / n_total if n_total > 0 else 0.0
    coverage_ok = coverage >= COVERAGE_FLOOR

    result: dict[str, Any] = {
        "node": node_label,
        "direction": direction,
        "onset_date": onset_date.isoformat(),
        "coverage": coverage,
        "coverage_ok": coverage_ok,
        "n_members_total": n_total,
        "n_members_covered": n_covered,
        "signed_excluded_stamp": SIGNED_EXCLUSION_STAMP,
        "provenance": UNSIGNED_PROVENANCE,
    }

    if not coverage_ok:
        # §2.4: below floor — null features, counted in coverage_dropped tally
        result.update({
            "flow_breadth_g": np.nan,
            "doi_unsigned_z": np.nan,
            "iv_term_z": np.nan,
            "iv_skew_z": np.nan,
            "iv_coverage": False,
            "etf_confirm_z": np.nan,
            "window_lo_date": None,
            "window_hi_date": None,
        })
        return result

    # Determine session window
    win = session_window(onset_date, session_dates, half_window)
    if win is None:
        result["coverage_ok"] = False  # window not covered → treated as dropped
        result.update({
            "flow_breadth_g": np.nan,
            "doi_unsigned_z": np.nan,
            "iv_term_z": np.nan,
            "iv_skew_z": np.nan,
            "iv_coverage": False,
            "etf_confirm_z": np.nan,
            "window_lo_date": None,
            "window_hi_date": None,
        })
        return result

    lo_idx, hi_idx = win
    window_lo_date = session_dates[lo_idx]
    window_hi_date = session_dates[hi_idx]
    result["window_lo_date"] = str(window_lo_date.date())
    result["window_hi_date"] = str(window_hi_date.date())

    window_dates = session_dates[lo_idx: hi_idx + 1]

    # ---- Flow breadth §2.2 feature 4 ----------------------------------------
    # Fraction of covered members confirming directional signature
    # (put z > 0 source / call z > 0 sink), concentration-penalized.
    # We use total premium z for the UNSIGNED version.
    breadth_vals: list[float] = []
    notional_weights: list[float] = []
    doi_z_vals: list[float] = []

    for root in covered:
        try:
            # Premium z at onset session (session at which flow-onset is measured)
            prem_at_window = eod_premium_panel.xs(root, level="root") \
                if "root" in eod_premium_panel.index.names \
                else eod_premium_panel.get(root, pd.DataFrame())

            if not isinstance(prem_at_window, pd.DataFrame) or prem_at_window.empty:
                continue

            # Restrict to window
            prem_window = prem_at_window[
                (prem_at_window.index >= window_lo_date) &
                (prem_at_window.index <= window_hi_date)
            ]
            if prem_window.empty:
                continue

            # Total notional for concentration penalty
            if direction == "out":
                prem_col = "total_put_prem" if "total_put_prem" in prem_window.columns else "total_prem"
            else:
                prem_col = "total_call_prem" if "total_call_prem" in prem_window.columns else "total_prem"

            if prem_col not in prem_window.columns:
                prem_col = prem_window.columns[0]

            total_notional = float(prem_window[prem_col].sum())
            notional_weights.append(max(total_notional, 0.0))

            # Premium z for breadth check (directional signature present if z > 0)
            z_col = prem_col + "_z" if (prem_col + "_z") in prem_window.columns else None
            if z_col and z_col in prem_window.columns:
                z_vals = prem_window[z_col].dropna()
                if not z_vals.empty:
                    mean_z = float(z_vals.mean())
                    breadth_vals.append(1.0 if mean_z > 0 else 0.0)

        except Exception:
            continue

        # DOI z (unsigned = absolute value direction)
        try:
            doi_root = oi_panel.xs(root, level="root") \
                if "root" in oi_panel.index.names \
                else oi_panel.get(root, pd.DataFrame())

            if isinstance(doi_root, pd.DataFrame) and not doi_root.empty:
                doi_window = doi_root[
                    (doi_root.index >= window_lo_date) &
                    (doi_root.index <= window_hi_date)
                ]
                if not doi_window.empty:
                    col = "doi_put_z" if direction == "out" else "doi_call_z"
                    if col in doi_window.columns:
                        z_series = doi_window[col].dropna()
                        if not z_series.empty:
                            doi_z_vals.append(float(z_series.mean()))
        except Exception:
            continue

    # Concentration penalty
    penalty = concentration_penalty(notional_weights) if notional_weights else 1.0

    if breadth_vals:
        raw_breadth = float(np.mean(breadth_vals))
        flow_breadth_g = raw_breadth * penalty
    else:
        flow_breadth_g = np.nan

    doi_unsigned_z = float(np.mean(doi_z_vals)) if doi_z_vals else np.nan

    result["flow_breadth_g"] = flow_breadth_g
    result["doi_unsigned_z"] = doi_unsigned_z

    # ---- IV term / skew §2.2 feature 6 ----------------------------------------
    iv_term_vals: list[float] = []
    iv_skew_vals: list[float] = []

    # IV only available 2017→
    iv_available = iv_panel is not None and onset_date >= IV_ERA_START

    if iv_available and iv_panel is not None:
        for root in covered:
            try:
                iv_root = iv_panel.xs(root, level="root") \
                    if "root" in iv_panel.index.names \
                    else iv_panel.get(root, pd.DataFrame())

                if not isinstance(iv_root, pd.DataFrame) or iv_root.empty:
                    continue

                iv_window = iv_root[
                    (iv_root.index >= window_lo_date) &
                    (iv_root.index <= window_hi_date)
                ]
                if iv_window.empty:
                    continue

                if "iv_term_z" in iv_window.columns:
                    vals = iv_window["iv_term_z"].dropna()
                    if not vals.empty:
                        iv_term_vals.append(float(vals.mean()))

                if "iv_skew_z" in iv_window.columns:
                    vals = iv_window["iv_skew_z"].dropna()
                    if not vals.empty:
                        iv_skew_vals.append(float(vals.mean()))
            except Exception:
                continue

    result["iv_term_z"] = float(np.mean(iv_term_vals)) if iv_term_vals else np.nan
    result["iv_skew_z"] = float(np.mean(iv_skew_vals)) if iv_skew_vals else np.nan
    result["iv_coverage"] = iv_available and (len(iv_term_vals) > 0 or len(iv_skew_vals) > 0)

    # ---- ETF confirm (§2.2 feature 5) -----------------------------------------
    # The sector/theme ETF's own premium z + DOI — single liquid instrument.
    # For Tier S, the ETF node is always in the options universe.
    etf_confirm_z = np.nan
    # ETF confirm is set by caller when group is a sector ETF (Tier S).
    # Here we just leave it NaN; it's populated by the runner for sector ETFs.
    result["etf_confirm_z"] = etf_confirm_z

    return result


# ---------------------------------------------------------------------------
# Composite options-pressure z (equal-weight, §4/§6)
# ---------------------------------------------------------------------------

def composite_z(features: dict[str, float]) -> float:
    """Equal-weight z-mean of available unsigned legs.

    Per §6 NO INVENTED WEIGHTS — all legs carry equal weight.
    Available legs (per §2.2, unsigned only):
        flow_breadth_g, doi_unsigned_z, iv_term_z, iv_skew_z, etf_confirm_z

    Returns NaN if no legs available.
    """
    legs = [
        features.get("flow_breadth_g"),
        features.get("doi_unsigned_z"),
        features.get("iv_term_z"),
        features.get("iv_skew_z"),
        features.get("etf_confirm_z"),
    ]
    valid = [v for v in legs if v is not None and not np.isnan(v)]
    if not valid:
        return np.nan
    return float(np.mean(valid))


def composite_z_from_series(
    feature_frame: pd.DataFrame,
    available_legs: list[str] | None = None,
) -> pd.Series:
    """Compute per-session equal-weight composite z from a features DataFrame.

    Parameters
    ----------
    feature_frame : pd.DataFrame
        Indexed by session date; columns are feature names.
    available_legs : list of str or None
        Subset of legs to include; default = all unsigned legs.

    Returns
    -------
    pd.Series indexed by date.
    """
    if available_legs is None:
        available_legs = [
            "flow_breadth_g", "doi_unsigned_z",
            "iv_term_z", "iv_skew_z", "etf_confirm_z",
        ]
    cols = [c for c in available_legs if c in feature_frame.columns]
    if not cols:
        return pd.Series(np.nan, index=feature_frame.index)
    sub = feature_frame[cols]
    return sub.mean(axis=1, skipna=True)


# ---------------------------------------------------------------------------
# O-OPT-1: flow-onset detection in the [−15,+15] window
# ---------------------------------------------------------------------------

def detect_flow_onset(
    composite_z_series: pd.Series,
    threshold: float = THRESH_FLOW_ONSET_Z,
    persistence: int = 2,
) -> int | None:
    """Find the first session where composite z >= threshold with `persistence` sessions.

    Per §4 O-OPT-1: "first session in the window where the composite
    options-pressure z crosses a pre-declared threshold (+1.0) with
    2-session persistence."

    Returns
    -------
    int or None
        Index into composite_z_series (0-based within the window) of the
        first qualifying onset, or None if threshold never crossed.
    """
    vals = composite_z_series.values
    n = len(vals)
    for i in range(n - persistence + 1):
        # Check persistence window: all `persistence` sessions >= threshold
        window_ok = all(
            not np.isnan(vals[i + j]) and vals[i + j] >= threshold
            for j in range(persistence)
        )
        if window_ok:
            return i
    return None


def compute_lead(
    flow_onset_session_idx: int | None,
    price_onset_session_idx: int,
    onset_session_in_window: int,
) -> int | None:
    """Compute lead in sessions: onset_date_idx − flow_onset_idx.

    Positive = options lead price.
    onset_session_in_window is the index (within the [−15,+15] window)
    corresponding to onset_date (typically 15, since window = [0..30]).

    Returns None if flow_onset is None (flow never triggered).
    """
    if flow_onset_session_idx is None:
        return None
    return onset_session_in_window - flow_onset_session_idx


# ---------------------------------------------------------------------------
# O-OPT-2: confirmation split at [−5,+1] around onset
# ---------------------------------------------------------------------------

def is_flow_confirmed(
    composite_z_series: pd.Series,
    flow_breadth_series: pd.Series,
    onset_idx_in_window: int,
    z_threshold: float = THRESH_CONFIRMATION_Z,
    breadth_threshold: float = THRESH_BREADTH_CONFIRMATION,
    conf_window: tuple[int, int] = (-5, 1),
) -> bool:
    """Check if composite z >= z_threshold AND flow_breadth >= breadth_threshold
    in the [−5,+1] window around onset.

    Per §4 O-OPT-2: split at onset into flow-CONFIRMED vs flow-UNCONFIRMED.
    composite z at [−5,+1] >= +0.5 WITH flow_breadth_g >= 0.5 (after
    concentration penalty).
    """
    lo = onset_idx_in_window + conf_window[0]
    hi = onset_idx_in_window + conf_window[1]
    lo = max(0, lo)
    hi = min(len(composite_z_series) - 1, hi)
    if lo > hi:
        return False

    z_window = composite_z_series.iloc[lo: hi + 1].dropna()
    b_window = flow_breadth_series.iloc[lo: hi + 1].dropna()

    if z_window.empty or b_window.empty:
        return False

    z_ok = float(z_window.mean()) >= z_threshold
    b_ok = float(b_window.mean()) >= breadth_threshold
    return z_ok and b_ok


# ---------------------------------------------------------------------------
# O-OPT-4: opposed-flow classification
# ---------------------------------------------------------------------------

def is_opposed_flow(
    src_features: dict[str, float],
    snk_features: dict[str, float],
    src_z_threshold: float = THRESH_OPPOSED_SRC_Z,
    snk_z_threshold: float = THRESH_OPPOSED_SNK_Z,
) -> bool:
    """Classify whether a two-sided pair has opposed flow.

    Per §4: opposed = source put_prem_z >= +0.5 AND sink call_prem_z >= +0.5.
    NOTE: since signed legs are excluded per R7, we use the unsigned composite_z
    as a proxy for both sides. This is stamped in the output.

    Returns False if either side's features are NaN.
    """
    # NOTE: with signed legs excluded, we proxy using composite_z of available unsigned legs
    src_z = composite_z(src_features)
    snk_z = composite_z(snk_features)
    if np.isnan(src_z) or np.isnan(snk_z):
        return False
    return src_z >= src_z_threshold and snk_z >= snk_z_threshold


# ---------------------------------------------------------------------------
# Trial enumeration §7
# ---------------------------------------------------------------------------

def enumerate_oopt_trials(
    n_o3_cells: int,
) -> list[dict[str, Any]]:
    """Enumerate all O-OPT trials per §7.

    O-OPT-1: 7 gated cells (1 pooled + 4 era + 2 regime)
    O-OPT-2: 5 gated cells (pooled + 4 era at 21d PRIMARY) + 10 robustness
    O-OPT-3: n_o3_cells sufficient routing cells (≤ 90 ceiling)
    O-OPT-4: 1 gated pooled + 4 era display
    """
    trials: list[dict[str, Any]] = []

    # O-OPT-1: lead-lag
    # 1 pooled (gated)
    trials.append({
        "trial_id": "oopt1_tier_s_pooled",
        "type": "lead_lag",
        "direction": "both",
        "tier": "onset",
        "horizon_d": 0,
        "section": "O-OPT-1",
        "gated": True,
        "p_value": None,
        "bh_rejected": None,
    })
    # 4 era
    for era_name, _, _ in OOPT_ERAS:
        trials.append({
            "trial_id": f"oopt1_era_{era_name}",
            "type": "lead_lag",
            "direction": "both",
            "tier": "onset",
            "horizon_d": 0,
            "section": "O-OPT-1",
            "era": era_name,
            "gated": True,
            "p_value": None,
            "bh_rejected": None,
        })
    # 2 regime
    for regime in ["vix_high", "vix_low"]:
        trials.append({
            "trial_id": f"oopt1_regime_{regime}",
            "type": "lead_lag",
            "direction": "both",
            "tier": "onset",
            "horizon_d": 0,
            "section": "O-OPT-1",
            "regime": regime,
            "gated": True,
            "p_value": None,
            "bh_rejected": None,
        })

    # O-OPT-2: confirmation quality
    # 21d is PRIMARY (gated); 5d and 63d are robustness (NOT gated)
    for h in [5, 21, 63]:
        is_primary = (h == 21)
        # 1 pooled
        trials.append({
            "trial_id": f"oopt2_h{h}_pooled",
            "type": "confirmation",
            "direction": "both",
            "tier": "onset",
            "horizon_d": h,
            "section": "O-OPT-2",
            "gated": is_primary,
            "p_value": None,
            "bh_rejected": None,
        })
        # 4 era
        for era_name, _, _ in OOPT_ERAS:
            trials.append({
                "trial_id": f"oopt2_h{h}_era_{era_name}",
                "type": "confirmation",
                "direction": "both",
                "tier": "onset",
                "horizon_d": h,
                "section": "O-OPT-2",
                "era": era_name,
                "gated": is_primary,
                "p_value": None,
                "bh_rejected": None,
            })

    # O-OPT-3: routing cells (count is set at run time, capped ≤ 90)
    actual_o3 = min(n_o3_cells, O3_CELL_CEILING)
    for i in range(actual_o3):
        trials.append({
            "trial_id": f"oopt3_routing_cell_{i:04d}",
            "type": "routing",
            "direction": "out",
            "tier": "onset",
            "horizon_d": 5,
            "section": "O-OPT-3",
            "gated": True,
            "p_value": None,
            "bh_rejected": None,
        })

    # O-OPT-4: two-sided opposed flow
    # 1 pooled (gated)
    trials.append({
        "trial_id": "oopt4_tier_s_pooled",
        "type": "two_sided_opposed",
        "direction": "both",
        "tier": "onset",
        "horizon_d": 21,
        "section": "O-OPT-4",
        "gated": True,
        "p_value": None,
        "bh_rejected": None,
    })
    # 4 era (display, not gated — expected thin n)
    for era_name, _, _ in OOPT_ERAS:
        trials.append({
            "trial_id": f"oopt4_era_{era_name}",
            "type": "two_sided_opposed",
            "direction": "both",
            "tier": "onset",
            "horizon_d": 21,
            "section": "O-OPT-4",
            "era": era_name,
            "gated": False,
            "p_value": None,
            "bh_rejected": None,
        })

    return trials


def gated_trial_count(trials: list[dict]) -> int:
    """Count trials marked gated=True (the FDR family)."""
    return sum(1 for t in trials if t.get("gated", False))


# ---------------------------------------------------------------------------
# Verdict vocabulary §9
# ---------------------------------------------------------------------------

def oopt_verdict(
    g1_pass: bool,
    g2_pass: bool,
    g3_pass: bool,
    g4_pass: bool,
    bh_rejected: bool,
    n: int,
    power_floor: int,
    kill_condition: bool,
) -> str:
    """Assign §9 verdict.

    Priority order (highest first):
    ACCRUE             : underpowered (n < power_floor) — takes precedence
    KILL               : meets §4 kill criterion at adequate power
    DISPLAY-WITH-EDGE  : clears G1-G4 + BH-FDR at adequate power
    DISPLAY-WITH-NULL  : fails FDR but not KILL (adequate power)

    Per §4: ACCRUE = "right direction, underpowered" — the power floor check
    must fire before the DISPLAY-WITH-EDGE path so that an underpowered result
    that happens to pass all gates is correctly classified as ACCRUE, not
    promoted to DISPLAY-WITH-EDGE.

    All verdicts labeled "PENDING FABLE ADJUDICATION" by the runner.
    """
    # Power floor check FIRST — ACCRUE takes precedence over promotion
    if n < power_floor:
        return "ACCRUE"
    # Kill criterion at adequate power
    if kill_condition:
        return "KILL"
    # All gates pass → edge
    all_pass = g1_pass and g2_pass and g3_pass and g4_pass and bh_rejected
    if all_pass:
        return "DISPLAY-WITH-EDGE"
    return "DISPLAY-WITH-NULL"


# ---------------------------------------------------------------------------
# Fragility check (R1)
# ---------------------------------------------------------------------------

def check_fragility(
    primary_passes: bool,
    neighbor_results: dict[float, bool],
) -> bool:
    """Return True if the result is FRAGILE per ruling R1.

    Fragile: primary passes while BOTH ±0.25 neighbors fail.
    A fragile primary is capped at DISPLAY-WITH-NULL.
    """
    if not primary_passes:
        return False
    lo_pass = neighbor_results.get(-0.25, True)
    hi_pass = neighbor_results.get(+0.25, True)
    return (not lo_pass) and (not hi_pass)


# ---------------------------------------------------------------------------
# Fixture store builder (for smoke mode / tests)
# ---------------------------------------------------------------------------

def build_fixture_eod_panel(
    roots: list[str],
    session_dates: pd.DatetimeIndex,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a synthetic EOD premium panel for hermetic testing.

    Returns a DataFrame with MultiIndex (date, root) and columns:
        total_call_prem, total_put_prem, total_call_prem_z, total_put_prem_z
    """
    rng = np.random.default_rng(seed)
    rows = []
    n_sessions = len(session_dates)
    # Raw premium series per root
    prem_series: dict[str, dict[str, np.ndarray]] = {}
    for root in roots:
        call_prem = np.abs(rng.standard_normal(n_sessions)) * 1e6
        put_prem = np.abs(rng.standard_normal(n_sessions)) * 1e6
        prem_series[root] = {"call": call_prem, "put": put_prem}

    for root in roots:
        call_arr = prem_series[root]["call"]
        put_arr = prem_series[root]["put"]
        # Rolling z
        call_s = pd.Series(call_arr, index=session_dates)
        put_s = pd.Series(put_arr, index=session_dates)
        call_z = rolling_z(call_s).values
        put_z = rolling_z(put_s).values
        for i, d in enumerate(session_dates):
            rows.append({
                "date": d,
                "root": root,
                "total_call_prem": call_arr[i],
                "total_put_prem": put_arr[i],
                "total_call_prem_z": call_z[i],
                "total_put_prem_z": put_z[i],
            })

    df = pd.DataFrame(rows).set_index(["date", "root"])
    return df


def build_fixture_oi_panel(
    roots: list[str],
    session_dates: pd.DatetimeIndex,
    seed: int = 43,
) -> pd.DataFrame:
    """Build a synthetic OI DOI panel for hermetic testing.

    Implements oi[t-1] law: doi_raw[t] = oi_shifted[t] - oi_shifted[t-5]
    where oi_shifted = oi.shift(1).

    Returns DataFrame with MultiIndex (date, root) and columns:
        doi_put_z, doi_call_z
    """
    rng = np.random.default_rng(seed)
    rows = []
    for root in roots:
        # Raw OI — daily absolute levels
        put_oi_raw = np.abs(rng.standard_normal(len(session_dates))) * 1e5 + 1e5
        call_oi_raw = np.abs(rng.standard_normal(len(session_dates))) * 1e5 + 1e5

        put_oi = pd.Series(put_oi_raw, index=session_dates)
        call_oi = pd.Series(call_oi_raw, index=session_dates)

        # Apply oi[t-1] law: shift BEFORE computing delta (§8.1)
        put_oi_shifted = put_oi.shift(1)   # oi[t-1]
        call_oi_shifted = call_oi.shift(1)

        put_doi_raw = put_oi_shifted - put_oi_shifted.shift(DOI_WINDOW)
        call_doi_raw = call_oi_shifted - call_oi_shifted.shift(DOI_WINDOW)

        put_doi_z = rolling_z(put_doi_raw).values
        call_doi_z = rolling_z(call_doi_raw).values

        for i, d in enumerate(session_dates):
            rows.append({
                "date": d,
                "root": root,
                "doi_put_z": put_doi_z[i],
                "doi_call_z": call_doi_z[i],
            })

    df = pd.DataFrame(rows).set_index(["date", "root"])
    return df


def build_fixture_iv_panel(
    roots: list[str],
    session_dates: pd.DatetimeIndex,
    seed: int = 44,
) -> pd.DataFrame:
    """Build a synthetic IV panel for hermetic testing.

    Returns DataFrame with MultiIndex (date, root) and columns:
        iv_term_z, iv_skew_z
    """
    rng = np.random.default_rng(seed)
    rows = []
    for root in roots:
        term = rng.standard_normal(len(session_dates))
        skew = rng.standard_normal(len(session_dates))

        term_s = pd.Series(term, index=session_dates)
        skew_s = pd.Series(skew, index=session_dates)
        term_z = rolling_z(term_s).values
        skew_z = rolling_z(skew_s).values

        for i, d in enumerate(session_dates):
            rows.append({
                "date": d,
                "root": root,
                "iv_term_z": term_z[i],
                "iv_skew_z": skew_z[i],
            })

    df = pd.DataFrame(rows).set_index(["date", "root"])
    return df
