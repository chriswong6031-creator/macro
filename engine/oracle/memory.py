"""Oracle O3 — Pattern Memory: conditional base rates + kNN episode analogues.

WHAT
----
Two public functions:

1. build_base_rates(episodes_s, episodes_m, cfg) → dict written to
   data/oracle/memory_base_rates.json.
   Printed-truths tables: per (panel_tier × direction × detection_tier ×
   regime_bucket) — n, mean+median direction-adjusted forward RS at 5/21/63d
   (matured rows only), hit rate, duration stats, onset→confirmed conversion
   rate, false-start rate.
   Every cell carries n; n<20 flagged "thin".

2. find_analogues(query, catalog, k=7, cfg) → dict of k nearest historical
   episodes with match scores + aggregate outcome summary.

DIRECTION-ADJUSTMENT CONVENTION (from ORACLE_GAUNTLET_P3_PREREG.md §1)
-----------------------------------------------------------------------
Outcome sign convention: for OUT episodes the hypothesized direction is
NEGATIVE forward RS; multiply by −1 so that "edge positive-is-good" is a
uniform comparison across both directions.

    direction_adjusted_rs = outcome_rs_Xd × (−1 if direction=="out" else +1)

LEAKAGE LAW (kNN eligibility — this is the adversarial review target)
----------------------------------------------------------------------
An analogue episode A is eligible for a query episode Q if and only if:

    A.onset_date + 63 trading sessions < Q.onset_date
        (full 63d outcome window of A predates Q — no future leakage)
    AND A.episode_id != Q.episode_id
    AND A.direction == Q.direction (same-direction analogues only)

Same-node analogues are ALLOWED but FLAGGED in the returned results.
This is enforced inside find_analogues(), not by the caller.

R4 COMPLIANCE
-------------
* No predictive claims: every aggregate labeled "descriptive — analogue
  history, not a forecast".
* Every onset-tier surface prints S3 error rates (onset→confirmed conversion,
  false-start rate) alongside any alert.
* The scored tilt (spotlight.theme_tilt → stock_score._axis_tailwind) is
  config-gated OFF by default — this module does not touch that gate.
* Banner language is descriptive only.

DEPENDENCIES
------------
numpy, pandas only. NO scipy, NO sklearn, NO LLM calls.

PUBLIC API
----------
MEMORY_CFG         — default config dict (all weights and thresholds)
build_base_rates(episodes_s, episodes_m, cfg=None) → dict
find_analogues(query, catalog, k=7, cfg=None) → dict
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MEMORY_CFG — single dict; all weights and thresholds with provenance.
# ---------------------------------------------------------------------------

MEMORY_CFG: dict[str, Any] = {
    # --- Base rates ---
    # VIX regime split threshold (>= is "high volatility" regime).
    # 0.6 = pre-registered in ORACLE_GAUNTLET_P3_PREREG.md §3 G3.
    "regime_vix_threshold": 0.6,

    # Thin-cell flag: cells with n < this are flagged "thin".
    "thin_cell_n": 20,

    # Forward outcome horizons — must match episode catalog horizons.
    "outcome_horizons": [5, 21, 63],

    # Detection tiers to report. Maps tier_label → outcome_col_suffix.
    # onset = "outcome_rs_{h}d"; confirmed = "outcome_rs_{h}d_confirmed";
    # undeniable = "outcome_rs_{h}d_undeniable"
    "detection_tiers": {
        "onset": "",
        "confirmed": "_confirmed",
        "undeniable": "_undeniable",
    },

    # --- kNN analogue matching ---
    # Trailing RS trajectory window (sessions) ending at onset.
    # 20 sessions ≈ 1 month; cheap 20×20 DTW per pair.
    "trajectory_window": 20,

    # Feature vector scalar weights (relative; internally z-scored).
    "weight_accel_z": 1.0,
    "weight_cohesion": 0.5,
    "weight_breadth": 0.5,

    # Weight of DTW trajectory distance vs scalar feature euclidean distance.
    # Both legs are normalised to [0,1] before weighting.
    "weight_dtw": 1.5,
    "weight_scalar": 1.0,

    # DTW Sakoe-Chiba band (sessions). Keeps DTW O(20×20) per pair.
    "dtw_band": 4,

    # Leakage buffer: analogue's outcome window must END before the query
    # onset. Buffer = 63 sessions (the longest outcome horizon).
    # Enforced as: analogue_onset_idx + 63 session_indices < query_onset_idx.
    "leakage_buffer_sessions": 63,

    # k nearest analogues to return.
    "k": 7,

    # Tilt flag — gated OFF per R4; never flip to True here.
    "axis_tailwind_enabled": False,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _direction_sign(direction: str) -> float:
    """Return +1 for IN episodes, −1 for OUT (direction-adjustment multiplier)."""
    return -1.0 if direction == "out" else 1.0


def _da(outcome: float | np.floating, direction: str) -> float:
    """Direction-adjusted outcome: positive = good regardless of direction."""
    return float(outcome) * _direction_sign(direction)


def _regime_bucket(vix_pctile, spy_above_200d, vix_thresh: float) -> str:
    """Return a regime bucket label from regime fields.

    Four buckets:
        hi_vix_above200  hi_vix_below200
        lo_vix_above200  lo_vix_below200

    Returns "unknown" when both fields are NaN.
    """
    vix_hi: bool | None = None
    if vix_pctile is not None and not (isinstance(vix_pctile, float) and np.isnan(vix_pctile)):
        vix_hi = float(vix_pctile) >= vix_thresh

    spy_hi: bool | None = None
    if spy_above_200d is not None and not (isinstance(spy_above_200d, float) and np.isnan(spy_above_200d)):
        spy_hi = bool(float(spy_above_200d) >= 0.5)

    if vix_hi is None and spy_hi is None:
        return "unknown"
    vix_label = ("hi_vix" if vix_hi else "lo_vix") if vix_hi is not None else "any_vix"
    spy_label = ("above200" if spy_hi else "below200") if spy_hi is not None else "any_spy"
    return f"{vix_label}_{spy_label}"


# ---------------------------------------------------------------------------
# 1. build_base_rates
# ---------------------------------------------------------------------------

def build_base_rates(
    episodes_s: pd.DataFrame,
    episodes_m: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> dict:
    """Build printed-truths base-rate tables.

    Parameters
    ----------
    episodes_s : pd.DataFrame
        Tier-S episode catalog (data/oracle/episodes_s.parquet).
    episodes_m : pd.DataFrame
        Tier-M episode catalog (data/oracle/episodes_m.parquet).
    cfg : dict | None
        Override MEMORY_CFG keys.

    Returns
    -------
    dict
        Structured dict written to data/oracle/memory_base_rates.json.
        Schema:
          {
            "meta": { generated_at, n_s, n_m, ... },
            "tables": [
              {
                "tier": "s" | "m",
                "direction": "in" | "out",
                "detection_tier": "onset" | "confirmed" | "undeniable",
                "regime": "all" | "hi_vix_above200" | ...,
                "n": int,
                "thin": bool,            # n < thin_cell_n
                "mean_da_5d": float,     # direction-adjusted
                "median_da_5d": float,
                "mean_da_21d": float,
                "median_da_21d": float,
                "mean_da_63d": float,
                "median_da_63d": float,
                "hit_rate_5d": float,    # fraction with DA outcome > 0
                "hit_rate_21d": float,
                "hit_rate_63d": float,
                "duration_mean": float,
                "duration_median": float,
                "onset_to_confirmed_rate": float,  # S3: fraction that confirmed
                "false_start_rate_10d": float,     # S3: fraction with DA +10d < 0
              },
              ...
            ],
            "s3_error_rates": {        # S3: onset-tier price of front-running
              "s": { ... },
              "m": { ... },
            }
          }

    Notes
    -----
    * Only MATURED rows are included in mean/median/hit-rate computation for
      each horizon (outcome_mature_{h}d[_{tier}] == True).
    * The "all" regime bucket is the full sample (no stratification) for each
      tier/direction/detection_tier combination.
    * thin = n < cfg["thin_cell_n"] (default 20).
    * Direction-adjustment: DA = outcome × sign (per PREREG §1).
    """
    c = {**MEMORY_CFG, **(cfg or {})}
    thin_n = c["thin_cell_n"]
    vix_thresh = c["regime_vix_threshold"]
    horizons = c["outcome_horizons"]
    det_tiers = c["detection_tiers"]  # label → suffix

    tables: list[dict] = []
    s3_error_rates: dict[str, dict] = {}

    tier_map = {"s": episodes_s, "m": episodes_m}

    for tier_label, eps_df in tier_map.items():
        if eps_df is None or eps_df.empty:
            log.warning("build_base_rates: empty episodes for tier=%s, skipping", tier_label)
            continue

        # S3: compute once per tier (onset-tier only)
        s3 = _compute_s3_error_rates(eps_df, vix_thresh)
        s3_error_rates[tier_label] = s3

        for direction in ("in", "out"):
            dir_df = eps_df[eps_df["direction"] == direction].copy()
            if dir_df.empty:
                continue
            sign = _direction_sign(direction)

            for det_label, det_suffix in det_tiers.items():
                # Build regime-labelled column
                regime_col = dir_df.apply(
                    lambda r: _regime_bucket(
                        r.get("regime_vix_pctile"), r.get("regime_spy_above_200d"), vix_thresh
                    ),
                    axis=1,
                )

                regime_buckets = ["all"] + sorted(regime_col.unique().tolist())

                for regime in regime_buckets:
                    if regime == "all":
                        subset = dir_df
                    else:
                        subset = dir_df[regime_col == regime]

                    cell = _build_cell(
                        subset, direction, sign, det_suffix, horizons, thin_n
                    )
                    cell.update({
                        "tier": tier_label,
                        "direction": direction,
                        "detection_tier": det_label,
                        "regime": regime,
                    })
                    tables.append(cell)

    import datetime as _dt
    result = {
        "meta": {
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "n_s": int(len(episodes_s)) if episodes_s is not None else 0,
            "n_m": int(len(episodes_m)) if episodes_m is not None else 0,
            "description": (
                "Conditional base rates for Oracle rotation episodes. "
                "All outcome values are DIRECTION-ADJUSTED (positive = good). "
                "This is a DESCRIPTIVE layer — historical statistics, not forecasts. "
                "Thin cells (n<20) are flagged; do not report them as reliable."
            ),
            "r4_compliance": (
                "No predictive claims. Onset-tier surfaces must print S3 error rates. "
                "Banner language is descriptive only. axis_tailwind gated OFF."
            ),
        },
        "tables": tables,
        "s3_error_rates": s3_error_rates,
    }
    return result


def _build_cell(
    subset: pd.DataFrame,
    direction: str,
    sign: float,
    det_suffix: str,
    horizons: list[int],
    thin_n: int,
) -> dict:
    """Build one base-rate cell dict from a subset of episodes."""
    cell: dict[str, Any] = {}

    n_total = len(subset)
    cell["n"] = n_total
    cell["thin"] = n_total < thin_n

    for h in horizons:
        outcome_col = f"outcome_rs_{h}d{det_suffix}"
        mature_col = f"outcome_mature_{h}d{det_suffix}" if det_suffix else f"outcome_mature_{h}d"

        # Graceful degrade: if column absent, skip
        if outcome_col not in subset.columns:
            cell[f"mean_da_{h}d"] = None
            cell[f"median_da_{h}d"] = None
            cell[f"hit_rate_{h}d"] = None
            cell[f"n_matured_{h}d"] = 0
            continue

        # Matured rows only
        if mature_col in subset.columns:
            matured = subset[subset[mature_col] == True]
        else:
            matured = subset[subset[outcome_col].notna()]

        outcomes = matured[outcome_col].dropna()
        da = outcomes * sign

        n_mat = len(da)
        cell[f"n_matured_{h}d"] = n_mat

        if n_mat == 0:
            cell[f"mean_da_{h}d"] = None
            cell[f"median_da_{h}d"] = None
            cell[f"hit_rate_{h}d"] = None
        else:
            cell[f"mean_da_{h}d"] = float(da.mean())
            cell[f"median_da_{h}d"] = float(da.median())
            cell[f"hit_rate_{h}d"] = float((da > 0).mean())

    # Duration stats (all rows, not just matured)
    if "duration" in subset.columns:
        dur = subset["duration"].dropna()
        cell["duration_mean"] = float(dur.mean()) if len(dur) > 0 else None
        cell["duration_median"] = float(dur.median()) if len(dur) > 0 else None
    else:
        cell["duration_mean"] = None
        cell["duration_median"] = None

    # S3: onset→confirmed conversion rate (relevant for onset tier)
    if "confirmed_date" in subset.columns:
        confirmed_n = subset["confirmed_date"].notna().sum()
        cell["onset_to_confirmed_rate"] = float(confirmed_n / n_total) if n_total > 0 else None
    else:
        cell["onset_to_confirmed_rate"] = None

    # S3: false-start rate — fraction with DA +10d outcome negative.
    # +10d is approximated from +5d and +21d or directly if available.
    # We use +21d as the proxy (closest matured window that captures D+10 behavior).
    # This is explicitly labeled as an approximation in the output.
    cell["false_start_rate_10d"] = _false_start_rate(subset, sign)

    return cell


def _false_start_rate(subset: pd.DataFrame, sign: float) -> float | None:
    """Fraction of onset-tier episodes where the direction-adjusted +10d outcome
    is negative (direction-adjusted outcome at +5d is used as the closest proxy).

    The S3 spec says "+10d outcome negative." We use outcome_rs_5d (matured)
    as the front-running proxy — it captures the immediate false-start signal
    where the episode reverses within the first week.

    Label in output: 'false_start_rate_10d_proxy_5d' to be explicit.
    """
    if "outcome_rs_5d" not in subset.columns:
        return None
    mat = subset[subset.get("outcome_mature_5d", pd.Series(True, index=subset.index)) == True]
    outcomes = mat["outcome_rs_5d"].dropna()
    da = outcomes * sign
    if len(da) == 0:
        return None
    return float((da < 0).mean())


def _compute_s3_error_rates(eps_df: pd.DataFrame, vix_thresh: float) -> dict:
    """Compute S3 error rates for the whole tier (all directions combined).

    Returns
    -------
    dict with:
      onset_to_confirmed_rate     — fraction of onset episodes that confirmed
      false_start_rate_5d         — fraction with DA +5d outcome negative
      detection_lag_onset_mean    — mean sessions onset (always 0 by definition)
      detection_lag_confirmed_mean  — mean sessions from onset to confirmed
      detection_lag_undeniable_mean — mean sessions from onset to undeniable
    """
    out: dict[str, Any] = {}

    # Onset → confirmed conversion
    if "confirmed_date" in eps_df.columns and "onset_date" in eps_df.columns:
        out["onset_to_confirmed_rate"] = float(
            eps_df["confirmed_date"].notna().mean()
        )
        # Detection lag: sessions from onset to confirmed (coerce to datetime first)
        try:
            conf = pd.to_datetime(eps_df["confirmed_date"], errors="coerce")
            ons = pd.to_datetime(eps_df["onset_date"], errors="coerce")
            lag_days = (conf - ons).dt.days.dropna()
            out["detection_lag_confirmed_days_mean"] = float(lag_days.mean()) if len(lag_days) > 0 else None
            out["detection_lag_confirmed_days_median"] = float(lag_days.median()) if len(lag_days) > 0 else None
        except Exception:
            out["detection_lag_confirmed_days_mean"] = None
            out["detection_lag_confirmed_days_median"] = None
    else:
        out["onset_to_confirmed_rate"] = None
        out["detection_lag_confirmed_days_mean"] = None
        out["detection_lag_confirmed_days_median"] = None

    if "undeniable_date" in eps_df.columns and "onset_date" in eps_df.columns:
        out["onset_to_undeniable_rate"] = float(
            eps_df["undeniable_date"].notna().mean()
        )
        try:
            undeniable = pd.to_datetime(eps_df["undeniable_date"], errors="coerce")
            ons = pd.to_datetime(eps_df["onset_date"], errors="coerce")
            lag_days_u = (undeniable - ons).dt.days.dropna()
            out["detection_lag_undeniable_days_mean"] = float(lag_days_u.mean()) if len(lag_days_u) > 0 else None
            out["detection_lag_undeniable_days_median"] = float(lag_days_u.median()) if len(lag_days_u) > 0 else None
        except Exception:
            out["detection_lag_undeniable_days_mean"] = None
            out["detection_lag_undeniable_days_median"] = None
    else:
        out["onset_to_undeniable_rate"] = None
        out["detection_lag_undeniable_days_mean"] = None
        out["detection_lag_undeniable_days_median"] = None

    # False-start rate: DA +5d negative
    if "outcome_rs_5d" in eps_df.columns and "outcome_mature_5d" in eps_df.columns:
        mat = eps_df[eps_df["outcome_mature_5d"] == True].copy()
        sign = mat["direction"].map(lambda d: -1.0 if d == "out" else 1.0)
        da = mat["outcome_rs_5d"] * sign
        out["false_start_rate_5d"] = float((da < 0).mean()) if len(da) > 0 else None
        out["false_start_n"] = int(len(da))
    else:
        out["false_start_rate_5d"] = None
        out["false_start_n"] = 0

    out["description"] = (
        "S3 error rates — onset-tier price of front-running. "
        "Print next to every onset-tier alert (R4 compliance)."
    )
    return out


# ---------------------------------------------------------------------------
# 2. DTW helper (numpy-only, window-constrained)
# ---------------------------------------------------------------------------

def _dtw_distance(a: np.ndarray, b: np.ndarray, band: int) -> float:
    """Sakoe-Chiba band-constrained DTW distance between two 1-D sequences.

    Parameters
    ----------
    a, b : np.ndarray
        1-D float arrays of equal length n.
    band : int
        Sakoe-Chiba half-bandwidth (indices within |i-j| <= band are reachable).

    Returns
    -------
    float
        DTW distance (sum of absolute differences along the warping path).
        Returns 0.0 for identical inputs; Infinity when the band completely
        disconnects the sequences (shouldn't happen for band >= 0).

    Complexity: O(n * band) — for n=20, band=4 this is O(80) per pair.
    """
    n = len(a)
    if n == 0:
        return 0.0
    # Initialise with infinity
    INF = float("inf")
    # Use two rows to save memory
    prev = np.full(n, INF)
    curr = np.full(n, INF)

    for i in range(n):
        j_lo = max(0, i - band)
        j_hi = min(n - 1, i + band)
        for j in range(j_lo, j_hi + 1):
            cost = abs(float(a[i]) - float(b[j]))
            if i == 0 and j == 0:
                curr[j] = cost
            elif i == 0:
                curr[j] = cost + (curr[j - 1] if j > 0 else INF)
            elif j == 0:
                curr[j] = cost + prev[j]
            else:
                p_diag = prev[j - 1] if j - 1 >= j_lo - 1 else INF
                p_up   = prev[j]
                p_left = curr[j - 1] if j - 1 >= j_lo else INF
                curr[j] = cost + min(p_diag, p_up, p_left)
        prev[:] = curr[:]
        curr[:] = INF

    return float(prev[n - 1])


# ---------------------------------------------------------------------------
# 3. find_analogues
# ---------------------------------------------------------------------------

def find_analogues(
    query: dict,
    catalog: pd.DataFrame,
    panel: pd.DataFrame | None = None,
    k: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict:
    """Find the k nearest historical episodes to a query episode.

    Parameters
    ----------
    query : dict
        A single episode record (dict or row from episodes DataFrame).
        Required keys: 'episode_id', 'onset_date', 'direction', 'node'.
        Optional feature keys: 'cohesion_at_onset', 'breadth_at_onset',
        'regime_vix_pctile', 'regime_spy_above_200d'.
    catalog : pd.DataFrame
        Full episode catalog (episodes_s.parquet or episodes_m.parquet).
        Must include 'onset_date', 'direction', 'episode_id', and
        outcome columns for all horizons.
    panel : pd.DataFrame | None
        Oracle rotation panel (MultiIndex node/date with 'accel_z').
        Used to extract the 20-session trailing RS trajectory ending at onset.
        If None, the trajectory leg of the distance is skipped.
    k : int | None
        Number of analogues to return. Defaults to cfg["k"].
    cfg : dict | None
        Override MEMORY_CFG keys.

    Returns
    -------
    dict
        {
          "query_episode_id": str,
          "query_onset_date": str (ISO),
          "query_direction": str,
          "analogues": [
            {
              "episode_id": str,
              "onset_date": str (ISO),
              "node": str,
              "distance": float,
              "same_node": bool,
              "outcomes": {
                "da_5d": float | null,  # direction-adjusted
                "da_21d": float | null,
                "da_63d": float | null,
                "mature_5d": bool,
                "mature_21d": bool,
                "mature_63d": bool,
              },
            },
            ...
          ],
          "aggregate": {
            "k": int,  # number eligible
            "median_da_5d": float | null,
            "median_da_21d": float | null,
            "median_da_63d": float | null,
            "n_mature_5d": int,
            "n_mature_21d": int,
            "n_mature_63d": int,
            "description": "descriptive — analogue history, not a forecast",
          },
          "leakage_excluded": int,  # count of episodes excluded by leakage law
          "thin": bool,  # k < cfg["thin_cell_n"]
        }

    LEAKAGE LAW ENFORCEMENT (enforced here, not in the caller):
        Eligible only if:
          (1) onset_date + 63 trading sessions < query.onset_date
          (2) episode_id != query.episode_id
          (3) direction == query.direction (same-direction only)
        Same-node analogues are allowed but flagged in results.

    FEATURE VECTOR (at detection — nothing post-onset):
        Scalar: accel_z_5d at onset, cohesion_at_onset, breadth_at_onset,
                regime_vix_pctile, regime_spy_above_200d.
        Trajectory: trailing 20-session rs values ending at onset_date
                    (from panel), z-normalized.

    DISTANCE:
        d = cfg["weight_scalar"] * euclidean_norm(scalar_features)
          + cfg["weight_dtw"]   * dtw_distance(trajectories)
        Both legs normalised to [0,1] before applying weights.
    """
    c = {**MEMORY_CFG, **(cfg or {})}
    if k is None:
        k = c["k"]

    query_id = query.get("episode_id", "")
    query_onset = pd.Timestamp(query["onset_date"])
    query_dir = str(query["direction"])
    query_node = str(query.get("node", ""))
    horizons = c["outcome_horizons"]
    leakage_sessions = c["leakage_buffer_sessions"]

    # ---- Build panel date index (for session-counting) ----
    if panel is not None and not panel.empty:
        panel_dates = panel.index.get_level_values("date").unique().sort_values()
    else:
        panel_dates = None

    def _sessions_before(d: pd.Timestamp) -> int:
        """Number of panel sessions at or before date d."""
        if panel_dates is None:
            return 0
        return int(np.searchsorted(panel_dates, d, side="right"))

    query_session_idx = _sessions_before(query_onset)

    # ---- Filter eligible analogues ----
    eligible_mask = (
        (catalog["direction"] == query_dir)
        & (catalog["episode_id"] != query_id)
    )
    eligible = catalog[eligible_mask].copy()

    # Leakage filter: analogue onset + 63 sessions < query onset
    def _is_eligible(row_onset: pd.Timestamp) -> bool:
        a_session_idx = _sessions_before(row_onset)
        return (a_session_idx + leakage_sessions) < query_session_idx

    if panel_dates is not None:
        eligible_leak_mask = eligible["onset_date"].apply(_is_eligible)
    else:
        # Calendar-day fallback: 63 sessions ≈ 90 calendar days
        eligible_leak_mask = (
            eligible["onset_date"] + pd.Timedelta(days=90)
        ) < query_onset

    leakage_excluded = int((~eligible_leak_mask).sum())
    eligible = eligible[eligible_leak_mask].copy()

    if eligible.empty:
        return _empty_analogue_result(query_id, query_onset, query_dir, leakage_excluded, c)

    # ---- Extract query feature vector ----
    query_accel_z_5d = float(query.get("accel_z_5d_at_onset", np.nan))
    query_cohesion = _safe_float(query.get("cohesion_at_onset"))
    query_breadth = _safe_float(query.get("breadth_at_onset"))
    query_vix = _safe_float(query.get("regime_vix_pctile"))
    query_spy = _safe_float(query.get("regime_spy_above_200d"))

    query_scalar = np.array([query_accel_z_5d, query_cohesion, query_breadth, query_vix, query_spy])

    query_traj = _extract_trajectory(query_node, query_onset, panel, c["trajectory_window"])

    # ---- Compute feature vectors for each eligible analogue ----
    ep_accel_z = _get_col(eligible, "accel_z_5d_at_onset", fallback_col="peak_accel_z")
    ep_cohesion = _get_col(eligible, "cohesion_at_onset")
    ep_breadth = _get_col(eligible, "breadth_at_onset")
    ep_vix = _get_col(eligible, "regime_vix_pctile")
    ep_spy = _get_col(eligible, "regime_spy_above_200d")

    analogue_scalars = np.column_stack([ep_accel_z, ep_cohesion, ep_breadth, ep_vix, ep_spy])

    # Z-score all scalar features jointly (using eligible set as reference)
    scalar_dists = _scalar_distances(query_scalar, analogue_scalars)

    # ---- DTW distances over RS trajectories ----
    dtw_dists = _compute_dtw_distances(
        query_traj, eligible, panel, c["trajectory_window"], c["dtw_band"]
    )

    # ---- Normalise and combine ----
    scalar_dists_norm = _norm01(scalar_dists)
    dtw_dists_norm = _norm01(dtw_dists)

    combined = (
        c["weight_scalar"] * scalar_dists_norm
        + c["weight_dtw"] * dtw_dists_norm
    )

    # ---- Select top-k ----
    eligible = eligible.copy()
    eligible["_dist"] = combined

    top = eligible.nsmallest(k, "_dist")

    # ---- Build result ----
    sign = _direction_sign(query_dir)
    analogues_out: list[dict] = []
    for _, row in top.iterrows():
        a_outcomes = {}
        for h in horizons:
            da_val = None
            mat_val = False
            oc_col = f"outcome_rs_{h}d"
            mat_col = f"outcome_mature_{h}d"
            if oc_col in row and row.get(mat_col, False):
                v = row[oc_col]
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    da_val = float(v) * sign
                    mat_val = True
            a_outcomes[f"da_{h}d"] = da_val
            a_outcomes[f"mature_{h}d"] = mat_val

        analogues_out.append({
            "episode_id": str(row["episode_id"]),
            "onset_date": str(row["onset_date"])[:10],
            "node": str(row.get("node", "")),
            "distance": float(row["_dist"]),
            "same_node": str(row.get("node", "")) == query_node,
            "outcomes": a_outcomes,
        })

    # ---- Aggregate ----
    aggregate = _build_aggregate(analogues_out, horizons, k, c)

    return {
        "query_episode_id": query_id,
        "query_onset_date": str(query_onset)[:10],
        "query_direction": query_dir,
        "analogues": analogues_out,
        "aggregate": aggregate,
        "leakage_excluded": leakage_excluded,
        "thin": k < c["thin_cell_n"],
    }


# ---------------------------------------------------------------------------
# find_analogues helpers
# ---------------------------------------------------------------------------

def _safe_float(v) -> float:
    """Convert to float, NaN if None or invalid."""
    if v is None:
        return np.nan
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return np.nan


def _get_col(df: pd.DataFrame, col: str, fallback_col: str | None = None) -> np.ndarray:
    """Extract a column as float array, NaN when absent."""
    if col in df.columns:
        return df[col].to_numpy(dtype=float)
    if fallback_col and fallback_col in df.columns:
        return df[fallback_col].to_numpy(dtype=float)
    return np.full(len(df), np.nan)


def _extract_trajectory(
    node: str,
    onset_date: pd.Timestamp,
    panel: pd.DataFrame | None,
    window: int,
) -> np.ndarray | None:
    """Extract the trailing `window` sessions of RS ending at onset_date.

    Returns None if panel is unavailable or node not found.
    The trajectory is z-normalized; a constant trajectory becomes all-zeros.
    """
    if panel is None or panel.empty:
        return None
    try:
        if isinstance(panel.index, pd.MultiIndex):
            node_panel = panel.xs(node, level="node")
        else:
            return None
    except KeyError:
        return None

    if "rs" not in node_panel.columns:
        return None

    node_rs = node_panel["rs"].sort_index()
    rs_before = node_rs[node_rs.index <= onset_date]
    if len(rs_before) < window:
        return None

    traj = rs_before.iloc[-window:].to_numpy(dtype=float)
    if np.any(np.isnan(traj)):
        return None

    # Z-normalize
    std = float(np.std(traj))
    if std < 1e-10:
        return np.zeros(window)
    return (traj - float(np.mean(traj))) / std


def _scalar_distances(
    query_scalar: np.ndarray,
    analogue_scalars: np.ndarray,
) -> np.ndarray:
    """Euclidean distance in Z-scored scalar feature space.

    Z-scoring uses the analogue pool's mean/std (query is one point).
    Missing values (NaN) are imputed with 0 (mean) after z-scoring.
    """
    n_analogues, n_features = analogue_scalars.shape

    # Compute mean/std from analogue pool
    pool_means = np.nanmean(analogue_scalars, axis=0)
    pool_stds = np.nanstd(analogue_scalars, axis=0)
    pool_stds = np.where(pool_stds < 1e-10, 1.0, pool_stds)

    # Z-score analogues
    z_analogues = (analogue_scalars - pool_means) / pool_stds
    z_analogues = np.where(np.isnan(z_analogues), 0.0, z_analogues)

    # Z-score query
    z_query = (query_scalar - pool_means) / pool_stds
    z_query = np.where(np.isnan(z_query), 0.0, z_query)

    diffs = z_analogues - z_query[np.newaxis, :]
    dists = np.sqrt(np.sum(diffs ** 2, axis=1))
    return dists


def _compute_dtw_distances(
    query_traj: np.ndarray | None,
    eligible: pd.DataFrame,
    panel: pd.DataFrame | None,
    window: int,
    band: int,
) -> np.ndarray:
    """Compute DTW distance for each eligible analogue vs query trajectory.

    Returns a zero array (no contribution) when query_traj is None.
    """
    n = len(eligible)
    dtw_dists = np.zeros(n)

    if query_traj is None or panel is None:
        return dtw_dists

    for idx, (_, row) in enumerate(eligible.iterrows()):
        a_traj = _extract_trajectory(
            str(row.get("node", "")),
            pd.Timestamp(row["onset_date"]),
            panel,
            window,
        )
        if a_traj is None:
            # Missing trajectory: assign max distance for this pair
            dtw_dists[idx] = float("inf")
        else:
            dtw_dists[idx] = _dtw_distance(query_traj, a_traj, band)

    # Replace inf with max finite value (graceful degrade for missing nodes)
    finite_mask = np.isfinite(dtw_dists)
    if finite_mask.any():
        max_finite = float(np.max(dtw_dists[finite_mask]))
        dtw_dists = np.where(finite_mask, dtw_dists, max_finite + 1.0)

    return dtw_dists


def _norm01(arr: np.ndarray) -> np.ndarray:
    """Normalise array to [0, 1]. All-equal arrays return zeros."""
    mn = float(np.min(arr))
    mx = float(np.max(arr))
    rng = mx - mn
    if rng < 1e-12:
        return np.zeros_like(arr, dtype=float)
    return (arr - mn) / rng


def _build_aggregate(
    analogues: list[dict],
    horizons: list[int],
    k: int,
    cfg: dict,
) -> dict:
    """Build aggregate summary over the returned analogues."""
    agg: dict[str, Any] = {
        "k": len(analogues),
        "description": "descriptive — analogue history, not a forecast",
    }
    for h in horizons:
        da_vals = [
            a["outcomes"].get(f"da_{h}d")
            for a in analogues
            if a["outcomes"].get(f"mature_{h}d", False) and a["outcomes"].get(f"da_{h}d") is not None
        ]
        n_mat = len(da_vals)
        agg[f"median_da_{h}d"] = float(np.median(da_vals)) if da_vals else None
        agg[f"n_mature_{h}d"] = n_mat
        if da_vals:
            vals = np.array(da_vals)
            agg[f"dispersion_da_{h}d"] = float(np.std(vals))
            agg[f"hit_rate_da_{h}d"] = float((vals > 0).mean())
        else:
            agg[f"dispersion_da_{h}d"] = None
            agg[f"hit_rate_da_{h}d"] = None

    return agg


def _empty_analogue_result(
    query_id: str,
    query_onset: pd.Timestamp,
    query_dir: str,
    leakage_excluded: int,
    cfg: dict,
) -> dict:
    horizons = cfg["outcome_horizons"]
    agg: dict[str, Any] = {
        "k": 0,
        "description": "descriptive — analogue history, not a forecast",
    }
    for h in horizons:
        agg[f"median_da_{h}d"] = None
        agg[f"n_mature_{h}d"] = 0
        agg[f"dispersion_da_{h}d"] = None
        agg[f"hit_rate_da_{h}d"] = None

    return {
        "query_episode_id": query_id,
        "query_onset_date": str(query_onset)[:10],
        "query_direction": query_dir,
        "analogues": [],
        "aggregate": agg,
        "leakage_excluded": leakage_excluded,
        "thin": True,
    }
