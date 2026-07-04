"""Oracle O1 — Rotation Graph: nodes, edges, lead-lag tensor, flow-routing matrix.

WHAT
----
Estimates the co-movement structure of the rotation panel: which nodes (sectors,
subsectors, themes, baskets) move together or inverse, which lead which, and where
money historically flows when a complex rolls over. Outputs the edge-stability
ledger, lead-lag tensor, flow-routing matrix, and data-derived cluster
reconciliation against the hand-named backbone in data/oracle/rotation_groups.json.

WHY
---
The rotation panel (O0) records *what happened* per node per day.  The graph layer
learns *which nodes are structurally linked* and *in what direction* so that:
(a) a rollover in one complex narrows the search space for the next move;
(b) lead-lag signals can flag "semis are turning before hardware confirms" — the
    earliest footprint of a rotation; and
(c) the flow-routing matrix turns the operator's "where does the money go?"
    intuition into an empirical conditional distribution, regime-split, with n
    printed for every cell (insufficient data = labeled, not asserted).

HONESTY FRAMING
---------------
* Edge estimation uses RS-CHANGE correlation, not RS-level correlation. Level
  correlation is a regime artefact (all tech names correlate in a bull); change
  correlation captures genuine co-movement in the incremental signal.
* All thresholds live in CONFIG at module top with provenance comments. They will
  be re-tuned in calibration (O6 gauntlet) — scattering constants makes that
  impossible.
* Cells with n < MIN_N_ROUTING are labeled "insufficient", never asserting an edge.
* The data-derived clusters vs backbone reconciliation prints disagreements but
  NEVER auto-resolves them — operator and Fable adjudicate membership.
* Lead-lag sign convention: corr(A_t, B_{t+k}) for k > 0 means "does A today
  predict B k days later?". A positive best_lag means B LAGS A (A leads B).
  Stated in the output as "A leads B by best_lag days". Tests MUST use this
  convention — a reversed sign will cause the planted-lead-lag test to fail.

PUBLIC API
----------
compute_edges(rs_change_wide, cfg) -> pd.DataFrame
    Rolling pairwise RS-change correlation at 60d and 120d windows.

compute_edge_stability(rs_change_wide, cfg) -> pd.DataFrame
    Per-edge stability across non-overlapping half-year windows.

compute_leadlag(complex_rs_chg, cfg) -> pd.DataFrame
    Cross-correlation of complex mean-RS-change at lags 1..MAX_LAG.

compute_routing(panel, complexes, cfg) -> dict
    Flow-routing matrix: for each complex outflow onset, fwd RS-change of others.

compute_clusters(rs_change_wide, cfg) -> list[set[str]]
    Numpy agglomerative clustering on 1 - corr(RS-changes).

reconcile_clusters(clusters, backbone_complexes) -> list[dict]
    Jaccard overlap between data-derived clusters and backbone complexes.

build_graph(panel, backbone, cfg) -> dict
    Top-level orchestrator: returns the full graph dict ready for JSON serialization.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIG — ALL thresholds in one place with provenance comments.
# Calibration (O6 gauntlet) will re-tune these; never scatter constants.
# ---------------------------------------------------------------------------

CONFIG: dict[str, Any] = {
    # Edge estimation windows (trading days)
    # 60d ≈ 1 quarter: captures regime-level co-movement
    # 120d ≈ 2 quarters: smoother, less noisy, more structural
    "EDGE_WINDOW_60D": 60,
    "EDGE_WINDOW_120D": 120,
    # Minimum observations to compute a meaningful correlation
    # Derived: 60d window, require at least 50% non-null overlap
    "EDGE_MIN_OBS": 30,
    # Stability ledger: |corr| threshold to count a window as having a real edge
    # 0.2 = moderate correlation; below this is indistinguishable from noise
    # at short window lengths (Provenance: standard exploratory threshold)
    "STABILITY_CORR_THRESH": 0.2,
    # Stability: a half-year window = 126 trading days (~6 calendar months)
    "STABILITY_HALF_YEAR_DAYS": 126,
    # Stability: minimum number of windows required to publish a stability score
    # At 126d windows on panel_s (1998→, ~7000 days) we get ~55 windows.
    # Require at least 4 to avoid asserting stability from a single regime.
    "STABILITY_MIN_WINDOWS": 4,
    # Lead-lag tensor: max lag (days). Lags 1..10 by task spec.
    # Cross-correlation at lag k: corr(A_t, B_{t+k})
    "LEADLAG_MAX_LAG": 10,
    # Minimum absolute correlation at lag>0 required to call a "candidate leader"
    # Provenance: lags 1-10d are short; 0.15 keeps the list manageable
    "LEADLAG_MIN_EDGE_CORR": 0.15,
    # Margin by which |corr@lag>0| must exceed |corr@lag=0| to flag as leader
    # Provenance: ruling from §4 — accel_z>1 lasts median 2 days; we want to see
    # corr_at_lag clearly exceed same-day to claim a true lead, not just noise
    "LEADLAG_LEADER_MARGIN": 0.05,
    # Flow-routing matrix parameters
    # Outflow onset: complex 5d-mean accel_z crossing below −1.0 with ≥3-of-5 days below
    # Threshold: grounded in measured distributions (§4): accel_z q75=0.60 q90=1.26
    # -1.0 is below the q10 (approximately the 10th pctile on the downside),
    # representing genuine deceleration beyond typical noise
    "ROUTING_ACCEL_Z_THRESH": -1.0,
    # N-of-M confirmation: require at least ROUTING_CONFIRM_K of last ROUTING_CONFIRM_M
    # days to be below threshold (prevents single-day noise from triggering)
    # Provenance: accel_z>1 lasts median 2 days (p90=5); use 3-of-5 as minimum
    "ROUTING_CONFIRM_K": 3,
    "ROUTING_CONFIRM_M": 5,
    # Forward windows to compute routing statistics (days)
    "ROUTING_FWD_WINDOWS": [5, 10, 15],
    # VIX percentile split for regime-conditional routing
    # 0.6 = above-median VIX = elevated vol regime
    # Provenance: standard risk-off/risk-on split used across the repo
    "ROUTING_HIGH_VIX_THRESH": 0.6,
    # Minimum n per routing cell to publish a result (vs label "insufficient")
    # Provenance: house law — cells with n<10 labeled "insufficient" not asserted
    "MIN_N_ROUTING": 10,
    # Clustering: agglomerative average linkage on 1-corr distance
    # Cut height: 0.6 means max within-cluster (1-corr) distance = 0.6,
    # i.e. within-cluster correlation ≥ 0.4
    # Provenance: empirical — at this height we expect 6-12 clusters on panel_m
    "CLUSTER_CUT_HEIGHT": 0.6,
    # Minimum cluster size to report
    "CLUSTER_MIN_SIZE": 2,
    # Jaccard overlap threshold to consider a backbone complex "well-matched"
    "RECONCILE_JACCARD_THRESH": 0.25,
}

# Mapping from backbone complex id → panel_s ETF nodes that represent it.
# Used when running the graph on panel_s (sector ETFs only).
COMPLEX_ETF_MAP: dict[str, list[str]] = {
    "ai_compute": ["XLK"],
    "software": ["XLK"],
    "healthcare_defensive": ["XLV"],
    "consumer_staples_defensive": ["XLP"],
    "energy_commodities": ["XLE", "XLB"],
    "financials_rates": ["XLF"],
    "long_duration_growth": ["XLRE", "XLU"],
    "short_duration_value": ["XLI", "XLB"],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pivot_rs_change(panel: pd.DataFrame) -> pd.DataFrame:
    """Pivot panel to wide form: index=date, columns=node, values=rs.diff().

    Returns a DataFrame of RS-changes (not RS levels). NaN where rs is NaN.
    """
    rs_wide = panel["rs"].unstack(level="node")
    rs_chg_wide = rs_wide.diff()  # day-over-day RS change
    return rs_chg_wide


def _rolling_corr_pair(
    a: np.ndarray,
    b: np.ndarray,
    window: int,
    min_obs: int,
) -> np.ndarray:
    """Rolling Pearson correlation of two 1-D arrays, causal (left-aligned).

    Returns array of same length; NaN where fewer than min_obs valid pairs.
    Uses pure numpy to avoid scipy dependency.
    """
    n = len(a)
    result = np.full(n, np.nan)
    for i in range(window - 1, n):
        xa = a[i - window + 1: i + 1]
        xb = b[i - window + 1: i + 1]
        # Drop positions where either is NaN
        mask = ~(np.isnan(xa) | np.isnan(xb))
        if mask.sum() < min_obs:
            continue
        xa_c = xa[mask]
        xb_c = xb[mask]
        if xa_c.std() < 1e-12 or xb_c.std() < 1e-12:
            continue
        result[i] = float(np.corrcoef(xa_c, xb_c)[0, 1])
    return result


def _full_corr_matrix(rs_chg_wide: pd.DataFrame, min_obs: int) -> pd.DataFrame:
    """Full-sample Pearson correlation matrix of RS-change columns.

    Uses rank().corr() to avoid scipy for robustness; plain Pearson here
    because RS-changes are approximately normal (not using rank to avoid
    losing sign information at the margin).
    """
    arr = rs_chg_wide.values
    n_nodes = arr.shape[1]
    nodes = rs_chg_wide.columns.tolist()
    corr_mat = np.full((n_nodes, n_nodes), np.nan)
    for i in range(n_nodes):
        corr_mat[i, i] = 1.0
        for j in range(i + 1, n_nodes):
            a = arr[:, i]
            b = arr[:, j]
            mask = ~(np.isnan(a) | np.isnan(b))
            if mask.sum() < min_obs:
                continue
            xa = a[mask]
            xb = b[mask]
            if xa.std() < 1e-12 or xb.std() < 1e-12:
                continue
            c = float(np.corrcoef(xa, xb)[0, 1])
            corr_mat[i, j] = c
            corr_mat[j, i] = c
    return pd.DataFrame(corr_mat, index=nodes, columns=nodes)


def _complex_rs_chg_series(
    rs_chg_wide: pd.DataFrame,
    complex_members: list[str],
) -> pd.Series:
    """Mean RS-change across available members of a complex."""
    avail = [m for m in complex_members if m in rs_chg_wide.columns]
    if not avail:
        return pd.Series(np.nan, index=rs_chg_wide.index, dtype=float)
    return rs_chg_wide[avail].mean(axis=1, skipna=True)


# ---------------------------------------------------------------------------
# Public: Edge estimation
# ---------------------------------------------------------------------------


def compute_edges(
    rs_chg_wide: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Rolling pairwise RS-change correlation at 60d and 120d windows.

    Returns a DataFrame indexed by (node_a, node_b) with columns:
      corr_60d_last  — final 60d rolling correlation (most recent window)
      corr_120d_last — final 120d rolling correlation (most recent window)
      corr_full      — full-sample correlation (entire available history)
      inverse        — True if corr_full < −STABILITY_CORR_THRESH

    Only node pairs with at least MIN_OBS valid overlapping observations
    are included.

    NOTE: We correlate RS-CHANGES, not RS levels, to capture co-movement
    in the incremental signal rather than shared regime trends.
    """
    cfg = cfg or CONFIG
    win_60 = cfg["EDGE_WINDOW_60D"]
    win_120 = cfg["EDGE_WINDOW_120D"]
    min_obs = cfg["EDGE_MIN_OBS"]
    inv_thresh = cfg["STABILITY_CORR_THRESH"]

    nodes = rs_chg_wide.columns.tolist()
    arr = rs_chg_wide.values
    n = arr.shape[0]
    n_nodes = len(nodes)

    rows = []
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            a = arr[:, i]
            b = arr[:, j]

            # Full-sample correlation
            mask = ~(np.isnan(a) | np.isnan(b))
            if mask.sum() < min_obs:
                continue
            xa = a[mask]
            xb = b[mask]
            if xa.std() < 1e-12 or xb.std() < 1e-12:
                continue
            corr_full = float(np.corrcoef(xa, xb)[0, 1])

            # 60d rolling — take last value
            roll60 = _rolling_corr_pair(a, b, win_60, min_obs)
            corr_60d_last = float(roll60[~np.isnan(roll60)][-1]) if np.any(~np.isnan(roll60)) else np.nan

            # 120d rolling — take last value
            roll120 = _rolling_corr_pair(a, b, win_120, min_obs)
            corr_120d_last = float(roll120[~np.isnan(roll120)][-1]) if np.any(~np.isnan(roll120)) else np.nan

            rows.append({
                "node_a": nodes[i],
                "node_b": nodes[j],
                "corr_60d_last": corr_60d_last,
                "corr_120d_last": corr_120d_last,
                "corr_full": corr_full,
                "inverse": bool(corr_full < -inv_thresh),
            })

    if not rows:
        return pd.DataFrame(columns=["node_a", "node_b", "corr_60d_last",
                                     "corr_120d_last", "corr_full", "inverse"])
    return pd.DataFrame(rows).set_index(["node_a", "node_b"])


# ---------------------------------------------------------------------------
# Public: Edge-stability ledger
# ---------------------------------------------------------------------------


def compute_edge_stability(
    rs_chg_wide: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Per-edge stability across non-overlapping half-year windows.

    For each pair of nodes, splits the available history into ~126-day
    non-overlapping windows.  Per window: computes the correlation.  Stability
    is the fraction of windows with |corr| ≥ STABILITY_CORR_THRESH AND consistent
    sign (all positive or all negative in windows that exceed the threshold).

    Returns a DataFrame indexed by (node_a, node_b) with columns:
      mean_corr        — mean across all window correlations
      sign_consistency — fraction of threshold-exceeding windows with majority sign
      n_windows        — total non-overlapping half-year windows
      stable           — bool: n_windows >= MIN_WINDOWS AND sign_consistency >= 0.75
                          AND |mean_corr| >= STABILITY_CORR_THRESH

    Only pairs with n_windows >= STABILITY_MIN_WINDOWS are included.
    """
    cfg = cfg or CONFIG
    half_yr = cfg["STABILITY_HALF_YEAR_DAYS"]
    corr_thresh = cfg["STABILITY_CORR_THRESH"]
    min_windows = cfg["STABILITY_MIN_WINDOWS"]
    min_obs = cfg["EDGE_MIN_OBS"]

    nodes = rs_chg_wide.columns.tolist()
    arr = rs_chg_wide.values
    n = arr.shape[0]
    n_nodes = len(nodes)

    # Partition into non-overlapping half-year windows
    window_starts = list(range(0, n - half_yr + 1, half_yr))

    rows = []
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            a = arr[:, i]
            b = arr[:, j]

            window_corrs: list[float] = []
            for ws in window_starts:
                we = ws + half_yr
                xa = a[ws:we]
                xb = b[ws:we]
                mask = ~(np.isnan(xa) | np.isnan(xb))
                if mask.sum() < min_obs:
                    window_corrs.append(np.nan)
                    continue
                xa_c = xa[mask]
                xb_c = xb[mask]
                if xa_c.std() < 1e-12 or xb_c.std() < 1e-12:
                    window_corrs.append(np.nan)
                    continue
                window_corrs.append(float(np.corrcoef(xa_c, xb_c)[0, 1]))

            valid = [c for c in window_corrs if not np.isnan(c)]
            n_valid = len(valid)
            if n_valid < min_windows:
                continue

            mean_corr = float(np.mean(valid))

            # Sign consistency: among windows exceeding |thresh|, what fraction
            # agree with the majority sign?
            strong = [c for c in valid if abs(c) >= corr_thresh]
            if len(strong) == 0:
                sign_consistency = 0.0
            else:
                pos = sum(1 for c in strong if c > 0)
                neg = len(strong) - pos
                sign_consistency = float(max(pos, neg) / len(strong))

            stable = bool(
                n_valid >= min_windows
                and sign_consistency >= 0.75
                and abs(mean_corr) >= corr_thresh
            )

            rows.append({
                "node_a": nodes[i],
                "node_b": nodes[j],
                "mean_corr": mean_corr,
                "sign_consistency": sign_consistency,
                "n_windows": n_valid,
                "stable": stable,
            })

    if not rows:
        return pd.DataFrame(columns=["node_a", "node_b", "mean_corr",
                                     "sign_consistency", "n_windows", "stable"])
    return pd.DataFrame(rows).set_index(["node_a", "node_b"])


# ---------------------------------------------------------------------------
# Public: Lead-lag tensor
# ---------------------------------------------------------------------------


def compute_leadlag(
    complex_rs_chg: dict[str, pd.Series],
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Cross-correlation of complex mean-RS-change series at lags 1..MAX_LAG.

    Sign convention (CRITICAL for tests):
      lag k means: corr(A_t, B_{t+k}) for k > 0
      Positive best_lag means B lags A by best_lag days, i.e. A LEADS B.
      This is the "causal" convention: A at time t predicts B at time t+k.
      Implementation: we shift B backward by k (B.shift(-k) aligns B_{t+k}
      with index t), then correlate with A.

    For each ordered pair (A, B):
      corr_at_lag_0 — contemporaneous correlation (lag 0)
      best_lag       — lag in 1..MAX_LAG with maximum |corr|
      best_corr      — correlation at best_lag
      is_leader      — True if |best_corr| > |corr_at_lag_0| + LEADER_MARGIN
      lags           — list of (lag, corr) for lags 0..MAX_LAG

    Returns a DataFrame indexed by (complex_a, complex_b) with those columns.
    Pairs where one series is all-NaN are skipped.
    """
    cfg = cfg or CONFIG
    max_lag = cfg["LEADLAG_MAX_LAG"]
    min_edge = cfg["LEADLAG_MIN_EDGE_CORR"]
    leader_margin = cfg["LEADLAG_LEADER_MARGIN"]

    complex_ids = list(complex_rs_chg.keys())
    rows = []

    for a_id in complex_ids:
        for b_id in complex_ids:
            if a_id == b_id:
                continue
            a_ser = complex_rs_chg[a_id]
            b_ser = complex_rs_chg[b_id]

            # Align on common index
            common = a_ser.index.intersection(b_ser.index)
            if len(common) < cfg["EDGE_MIN_OBS"]:
                continue
            a_arr = a_ser.reindex(common).values.astype(float)
            b_arr = b_ser.reindex(common).values.astype(float)

            # Lag 0 correlation
            mask0 = ~(np.isnan(a_arr) | np.isnan(b_arr))
            if mask0.sum() < cfg["EDGE_MIN_OBS"]:
                continue
            corr0 = float(np.corrcoef(a_arr[mask0], b_arr[mask0])[0, 1]) if mask0.sum() >= 2 else np.nan

            # Cross-correlation at lags 1..MAX_LAG
            # corr(A_t, B_{t+k}) = align A with B.shift(-k)
            lag_corrs: list[tuple[int, float]] = [(0, corr0)]
            best_lag = 0
            best_corr = corr0

            for k in range(1, max_lag + 1):
                # B shifted so B[t+k] aligns with t (B.shift(-k))
                b_shifted = np.full_like(b_arr, np.nan)
                if k < len(b_arr):
                    b_shifted[: len(b_arr) - k] = b_arr[k:]

                mask_k = ~(np.isnan(a_arr) | np.isnan(b_shifted))
                if mask_k.sum() < cfg["EDGE_MIN_OBS"]:
                    lag_corrs.append((k, np.nan))
                    continue
                c_k = float(np.corrcoef(a_arr[mask_k], b_shifted[mask_k])[0, 1])
                lag_corrs.append((k, c_k))

                if not np.isnan(c_k) and abs(c_k) > abs(best_corr if not np.isnan(best_corr) else 0.0):
                    best_lag = k
                    best_corr = c_k

            is_leader = bool(
                not np.isnan(best_corr)
                and not np.isnan(corr0)
                and best_lag > 0
                and abs(best_corr) >= min_edge
                and abs(best_corr) > abs(corr0) + leader_margin
            )

            rows.append({
                "complex_a": a_id,
                "complex_b": b_id,
                "corr_at_lag_0": corr0,
                "best_lag": best_lag,
                "best_corr": best_corr,
                "is_leader": is_leader,
                "lags": lag_corrs,
            })

    if not rows:
        return pd.DataFrame(columns=["complex_a", "complex_b", "corr_at_lag_0",
                                     "best_lag", "best_corr", "is_leader", "lags"])
    return pd.DataFrame(rows).set_index(["complex_a", "complex_b"])


# ---------------------------------------------------------------------------
# Public: Flow-Routing Matrix
# ---------------------------------------------------------------------------


def compute_routing(
    panel: pd.DataFrame,
    complexes: dict[str, list[str]],
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Flow-Routing Matrix: empirical destination of RS after complex outflow onset.

    For each complex A, detects outflow onsets (5d-mean accel_z crossing below
    −1.0 with ≥3-of-5 days below the threshold — §4 grounded).  For each onset
    event, records the forward RS-change of every OTHER complex at 5/10/15d.
    Aggregates into a routing matrix split by VIX regime (high/low).

    Returns a nested dict:
    {
      "source_complex": {
        "dest_complex": {
          "high_vix": {
            "mean_fwd_rs_5d": ...,  "mean_fwd_rs_10d": ..., "mean_fwd_rs_15d": ...,
            "hit_rate_positive_5d": ..., "n": ..., "sufficient": bool
          },
          "low_vix": { ... }
        }
      },
      "_config": { accel_z_thresh, confirm_k, confirm_m, fwd_windows, min_n }
    }

    Cells with n < MIN_N_ROUTING have "sufficient": False — do not assert edge.
    """
    cfg = cfg or CONFIG
    accel_thresh = cfg["ROUTING_ACCEL_Z_THRESH"]
    confirm_k = cfg["ROUTING_CONFIRM_K"]
    confirm_m = cfg["ROUTING_CONFIRM_M"]
    fwd_windows = cfg["ROUTING_FWD_WINDOWS"]
    high_vix = cfg["ROUTING_HIGH_VIX_THRESH"]
    min_n = cfg["MIN_N_ROUTING"]

    # Build accel_z and rs wide frames, and vix_pctile
    accel_z_wide = panel["accel_z"].unstack(level="node") if "accel_z" in panel.columns else pd.DataFrame()
    rs_wide = panel["rs"].unstack(level="node") if "rs" in panel.columns else pd.DataFrame()
    vix_wide = panel["vix_pctile"].unstack(level="node") if "vix_pctile" in panel.columns else pd.DataFrame()
    vix_ser: pd.Series | None = None
    if not vix_wide.empty:
        # Use any node's vix_pctile (all same by construction)
        vix_ser = vix_wide.iloc[:, 0]

    if accel_z_wide.empty or rs_wide.empty:
        return {"_config": {}, "_note": "insufficient panel columns"}

    # Build complex-level accel_z and rs series: mean across available members
    complex_accel: dict[str, pd.Series] = {}
    complex_rs: dict[str, pd.Series] = {}
    for cid, members in complexes.items():
        avail_accel = [m for m in members if m in accel_z_wide.columns]
        avail_rs = [m for m in members if m in rs_wide.columns]
        if avail_accel:
            complex_accel[cid] = accel_z_wide[avail_accel].mean(axis=1, skipna=True)
        if avail_rs:
            complex_rs[cid] = rs_wide[avail_rs].mean(axis=1, skipna=True)

    dates = accel_z_wide.index
    routing: dict[str, dict] = {}

    for src_id, src_accel in complex_accel.items():
        # Detect outflow onset: 5d-mean accel_z crossing below −1.0
        # with at least CONFIRM_K of last CONFIRM_M days below threshold.
        # "Crossing below" = the 5d-mean was NOT below threshold at t-1 but IS at t.
        accel_arr = src_accel.values
        n = len(accel_arr)

        # 5d rolling mean of accel_z
        roll5 = np.full(n, np.nan)
        for i in range(4, n):
            window = accel_arr[i - 4: i + 1]
            valid = window[~np.isnan(window)]
            if len(valid) >= 3:
                roll5[i] = float(valid.mean())

        # Confirmation: ≥CONFIRM_K of last CONFIRM_M days below threshold
        confirm_flags = np.zeros(n, dtype=bool)
        for i in range(confirm_m - 1, n):
            window = accel_arr[i - confirm_m + 1: i + 1]
            below = np.sum(window < accel_thresh)
            if below >= confirm_k:
                confirm_flags[i] = True

        # Onset = confirm on day i AND roll5[i] < thresh AND roll5[i-1] >= thresh
        # (crossing transition — avoid re-triggering on sustained outflow)
        onset_indices: list[int] = []
        in_outflow = False
        for i in range(1, n):
            if confirm_flags[i] and not np.isnan(roll5[i]) and roll5[i] < accel_thresh:
                if not in_outflow:
                    onset_indices.append(i)
                    in_outflow = True
            else:
                # Reset: require accel_z to recover above -0.5 before re-triggering
                if not np.isnan(roll5[i]) and roll5[i] >= -0.5:
                    in_outflow = False

        if not onset_indices:
            routing[src_id] = {}
            continue

        src_routing: dict[str, dict] = {}
        for dest_id, dest_rs in complex_rs.items():
            if dest_id == src_id:
                continue
            dest_arr = dest_rs.values

            # For each onset, collect forward RS-change at each window
            # High/low VIX buckets
            for regime_label, vix_cond in [("high_vix", True), ("low_vix", False)]:
                fwd_by_window: dict[int, list[float]] = {w: [] for w in fwd_windows}
                n_events = 0
                for onset_i in onset_indices:
                    # VIX regime check at onset date
                    vix_val = float(vix_ser.iloc[onset_i]) if vix_ser is not None and onset_i < len(vix_ser) else np.nan
                    if not np.isnan(vix_val):
                        is_high_vix = vix_val >= high_vix
                        if is_high_vix != vix_cond:
                            continue
                    # else: vix unavailable — include in both regimes

                    rs_at_onset = dest_arr[onset_i] if onset_i < len(dest_arr) else np.nan
                    if np.isnan(rs_at_onset):
                        continue
                    n_events += 1
                    for fwd_w in fwd_windows:
                        fwd_i = onset_i + fwd_w
                        if fwd_i < len(dest_arr) and not np.isnan(dest_arr[fwd_i]):
                            fwd_rs_chg = dest_arr[fwd_i] - rs_at_onset
                            fwd_by_window[fwd_w].append(fwd_rs_chg)

                cell: dict[str, Any] = {"n": n_events, "sufficient": n_events >= min_n}
                for fwd_w in fwd_windows:
                    vals = fwd_by_window[fwd_w]
                    if len(vals) >= 1:
                        cell[f"mean_fwd_rs_{fwd_w}d"] = float(np.mean(vals))
                        cell[f"hit_rate_positive_{fwd_w}d"] = float(np.mean([v > 0 for v in vals]))
                    else:
                        cell[f"mean_fwd_rs_{fwd_w}d"] = None
                        cell[f"hit_rate_positive_{fwd_w}d"] = None

                if dest_id not in src_routing:
                    src_routing[dest_id] = {}
                src_routing[dest_id][regime_label] = cell

        routing[src_id] = src_routing

    return {
        **routing,
        "_config": {
            "accel_z_thresh": accel_thresh,
            "confirm_k": confirm_k,
            "confirm_m": confirm_m,
            "fwd_windows": fwd_windows,
            "high_vix_thresh": high_vix,
            "min_n": min_n,
        },
    }


# ---------------------------------------------------------------------------
# Public: Data-derived clustering
# ---------------------------------------------------------------------------


def compute_clusters(
    rs_chg_wide: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
) -> list[set[str]]:
    """Agglomerative clustering (average linkage) on 1 − corr(RS-changes).

    Uses plain numpy — no scipy, no networkx, no sklearn.

    Returns a list of sets of node names (clusters).
    Singletons below MIN_CLUSTER_SIZE are excluded from the returned list
    but are noted in the log.
    """
    cfg = cfg or CONFIG
    cut_height = cfg["CLUSTER_CUT_HEIGHT"]
    min_size = cfg["CLUSTER_MIN_SIZE"]
    min_obs = cfg["EDGE_MIN_OBS"]

    nodes = rs_chg_wide.columns.tolist()
    n = len(nodes)
    if n < 2:
        return [{nodes[0]}] if n == 1 else []

    # Full-sample correlation matrix
    corr_mat = _full_corr_matrix(rs_chg_wide, min_obs).values

    # Distance matrix: 1 - corr; NaN → max distance 2.0 (no correlation known)
    dist_mat = np.where(np.isnan(corr_mat), 2.0, 1.0 - corr_mat)
    np.fill_diagonal(dist_mat, 0.0)

    # Agglomerative clustering with average linkage (pure numpy).
    # We maintain a list of active clusters and a condensed distance matrix.
    # At each step: merge the pair with smallest average-linkage distance.
    # Stop when minimum distance >= cut_height.
    cluster_members: list[list[int]] = [[i] for i in range(n)]
    active = list(range(n))

    # Working distance matrix between current clusters
    # (starts as node-node distance; updated after each merge)
    cluster_dist = dist_mat.copy()

    while len(active) > 1:
        # Find the pair with smallest distance
        best_i, best_j, best_d = -1, -1, float("inf")
        for ii in range(len(active)):
            for jj in range(ii + 1, len(active)):
                ci, cj = active[ii], active[jj]
                d = cluster_dist[ci, cj]
                if d < best_d:
                    best_d = d
                    best_i, best_j = ci, cj

        if best_d >= cut_height:
            break

        # Merge best_j into best_i using average linkage update
        mi = cluster_members[best_i]
        mj = cluster_members[best_j]
        merged = mi + mj
        cluster_members[best_i] = merged
        active.remove(best_j)

        # Update distances from the merged cluster to all others
        ni_sz = len(mi)
        nj_sz = len(mj)
        n_merged = len(merged)
        for other in active:
            if other == best_i:
                continue
            # Average linkage: weighted average of distances
            d_new = (cluster_dist[best_i, other] * ni_sz
                     + cluster_dist[best_j, other] * nj_sz) / n_merged
            cluster_dist[best_i, other] = d_new
            cluster_dist[other, best_i] = d_new

    result = []
    for ci in active:
        members_set = {nodes[idx] for idx in cluster_members[ci]}
        if len(members_set) >= min_size:
            result.append(members_set)

    log.info(
        "Clustering: %d nodes → %d clusters (cut_height=%.2f, min_size=%d)",
        n, len(result), cut_height, min_size,
    )
    return result


# ---------------------------------------------------------------------------
# Public: Cluster reconciliation vs backbone
# ---------------------------------------------------------------------------


def reconcile_clusters(
    clusters: list[set[str]],
    backbone_complexes: list[dict],
    cfg: dict[str, Any] | None = None,
) -> list[dict]:
    """Jaccard reconciliation of data-derived clusters vs hand-named backbone.

    For each backbone complex: finds the empirical cluster with highest Jaccard
    overlap.  Disagreements (Jaccard below threshold, or members scattered across
    multiple clusters) are listed — never auto-resolved.

    Returns a list of dicts, one per backbone complex:
      {
        "complex_id": str,
        "best_cluster_jaccard": float,
        "best_cluster_size": int,
        "matched_members": list[str],       # backbone members found in best cluster
        "missing_from_cluster": list[str],  # backbone members NOT in best cluster
        "extra_in_cluster": list[str],      # cluster members NOT in backbone
        "well_matched": bool,               # Jaccard >= RECONCILE_JACCARD_THRESH
        "note": str,
      }
    """
    cfg = cfg or CONFIG
    thresh = cfg["RECONCILE_JACCARD_THRESH"]

    results = []
    for bc in backbone_complexes:
        cid = bc["id"]
        backbone_set = set(bc.get("members", []))

        best_jaccard = 0.0
        best_cluster: set[str] = set()
        for cl in clusters:
            intersection = backbone_set & cl
            union = backbone_set | cl
            if not union:
                continue
            j = len(intersection) / len(union)
            if j > best_jaccard:
                best_jaccard = j
                best_cluster = cl

        matched = list(backbone_set & best_cluster)
        missing = list(backbone_set - best_cluster)
        extra = list(best_cluster - backbone_set)

        well_matched = bool(best_jaccard >= thresh)
        if well_matched:
            note = f"Good overlap (Jaccard={best_jaccard:.2f})."
        elif best_jaccard > 0:
            note = (
                f"Partial overlap (Jaccard={best_jaccard:.2f}). "
                f"Missing from best cluster: {missing[:5]}. "
                f"Extra in cluster: {extra[:5]}. "
                "DISAGREEMENT — do not auto-resolve; flag for Fable adjudication."
            )
        else:
            note = (
                "No empirical cluster matches this backbone complex. "
                "Backbone members may be too sparse in the panel, or the complex "
                "is genuinely polyphyletic. DISAGREEMENT — adjudication required."
            )

        results.append({
            "complex_id": cid,
            "best_cluster_jaccard": round(best_jaccard, 4),
            "best_cluster_size": len(best_cluster),
            "matched_members": sorted(matched),
            "missing_from_cluster": sorted(missing),
            "extra_in_cluster": sorted(extra[:20]),  # cap for readability
            "well_matched": well_matched,
            "note": note,
        })

    return results


# ---------------------------------------------------------------------------
# Public: Complex-level edges (mean-RS-change series correlation)
# ---------------------------------------------------------------------------


def compute_complex_edges(
    complex_rs_chg: dict[str, pd.Series],
    cfg: dict[str, Any] | None = None,
) -> list[dict]:
    """Edge estimation at complex level (correlation of complex mean-RS-change series).

    Returns list of {complex_a, complex_b, corr_full, inverse}.
    """
    cfg = cfg or CONFIG
    min_obs = cfg["EDGE_MIN_OBS"]
    inv_thresh = cfg["STABILITY_CORR_THRESH"]

    ids = list(complex_rs_chg.keys())
    rows = []
    for i, a_id in enumerate(ids):
        for j in range(i + 1, len(ids)):
            b_id = ids[j]
            a_ser = complex_rs_chg[a_id]
            b_ser = complex_rs_chg[b_id]
            common = a_ser.index.intersection(b_ser.index)
            if len(common) < min_obs:
                continue
            a_arr = a_ser.reindex(common).values.astype(float)
            b_arr = b_ser.reindex(common).values.astype(float)
            mask = ~(np.isnan(a_arr) | np.isnan(b_arr))
            if mask.sum() < min_obs:
                continue
            xa = a_arr[mask]
            xb = b_arr[mask]
            if xa.std() < 1e-12 or xb.std() < 1e-12:
                continue
            c = float(np.corrcoef(xa, xb)[0, 1])
            rows.append({
                "complex_a": a_id,
                "complex_b": b_id,
                "corr_full": c,
                "inverse": bool(c < -inv_thresh),
            })
    return rows


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def build_graph(
    panel: pd.DataFrame,
    backbone: dict,
    cfg: dict[str, Any] | None = None,
) -> dict:
    """Build the full Oracle graph dict from a rotation panel + backbone map.

    Parameters
    ----------
    panel    : MultiIndex (node, date) DataFrame from panel.py
    backbone : parsed rotation_groups.json (the dict with "complexes" key)
    cfg      : CONFIG override (defaults to module-level CONFIG)

    Returns
    -------
    A JSON-serializable dict with keys:
      asof          — ISO date of latest panel row
      config        — CONFIG echo
      node_count    — number of panel nodes
      edges         — pairwise node RS-change correlations
      edge_stability— per-edge stability ledger
      complex_edges — complex-level edges
      leadlag       — lead-lag tensor
      routing       — flow-routing matrix
      clusters      — data-derived clusters (list of lists)
      reconciliation— Jaccard reconciliation vs backbone

    NOTE: edges/edge_stability are computed on the FULL node universe.
    For large Tier M panels (354 nodes) this is O(n^2) ~ 62k pairs; use
    --tier s for faster runs during development.
    """
    cfg = cfg or CONFIG

    complexes = {bc["id"]: bc["members"] for bc in backbone.get("complexes", [])}
    backbone_list = backbone.get("complexes", [])

    # Panel date range
    dates = panel.index.get_level_values("date")
    asof = str(dates.max().date()) if len(dates) else "unknown"

    # RS-change wide matrix
    log.info("Pivoting RS-change matrix...")
    rs_chg_wide = _pivot_rs_change(panel)

    # Pairwise node edges (may be slow on large panels)
    log.info("Computing pairwise node edges (%d nodes)...", rs_chg_wide.shape[1])
    edges_df = compute_edges(rs_chg_wide, cfg)
    log.info("Edge pairs computed: %d", len(edges_df))

    # Edge stability ledger
    log.info("Computing edge stability ledger...")
    stability_df = compute_edge_stability(rs_chg_wide, cfg)
    log.info("Stability pairs computed: %d", len(stability_df))

    # Complex RS-change series (mean across available members)
    complex_rs_chg: dict[str, pd.Series] = {}
    for cid, members in complexes.items():
        complex_rs_chg[cid] = _complex_rs_chg_series(rs_chg_wide, members)

    # Complex-level edges
    log.info("Computing complex-level edges...")
    cx_edges = compute_complex_edges(complex_rs_chg, cfg)

    # Lead-lag tensor
    log.info("Computing lead-lag tensor...")
    ll_df = compute_leadlag(complex_rs_chg, cfg)

    # Flow-routing matrix
    log.info("Computing flow-routing matrix...")
    routing = compute_routing(panel, complexes, cfg)

    # Data-derived clusters
    log.info("Clustering nodes...")
    clusters = compute_clusters(rs_chg_wide, cfg)
    clusters_serializable = [sorted(cl) for cl in clusters]

    # Reconciliation
    log.info("Reconciling clusters vs backbone...")
    reconciliation = reconcile_clusters(clusters, backbone_list, cfg)

    # Serialize edge DataFrames
    def _df_to_records(df: pd.DataFrame) -> list[dict]:
        if df.empty:
            return []
        return df.reset_index().to_dict(orient="records")

    def _ll_to_records(df: pd.DataFrame) -> list[dict]:
        """Serialize lead-lag DataFrame, converting lags list."""
        if df.empty:
            return []
        recs = []
        for idx, row in df.iterrows():
            r = {"complex_a": idx[0], "complex_b": idx[1]}
            r.update({k: v for k, v in row.items() if k != "lags"})
            # lags is list of (lag, corr) tuples → list of [lag, corr]
            r["lags"] = [[lag, corr] for lag, corr in row.get("lags", [])]
            recs.append(r)
        return recs

    return {
        "asof": asof,
        "config": cfg,
        "node_count": rs_chg_wide.shape[1],
        "edges": _df_to_records(edges_df),
        "edge_stability": _df_to_records(stability_df),
        "complex_edges": cx_edges,
        "leadlag": _ll_to_records(ll_df),
        "routing": routing,
        "clusters": clusters_serializable,
        "reconciliation": reconciliation,
    }
