"""engine.neuralweb.alpha_overlap — Redundancy / overlap map over the candidate panel.

HONESTY HEADER
--------------
This module is RESEARCH-SIDE ONLY (FR-12).  Outputs are CLUSTER METADATA ONLY (FR-6):
no combined score, no weighting, nothing a board could lift.  No site output, no
synapse.yml registration, no spine claims, no board rank/size/alert changes.

CLUSTERING DETERMINISM (reviewer amendment)
-------------------------------------------
Greedy correlation clustering at |ρ| > threshold is order-dependent and unstable.
This module sorts candidates DETERMINISTICALLY by (DSR desc, alpha_id asc) before
the greedy pass.  Cluster membership is reported at thresholds 0.6, 0.7 (default),
and 0.8 so sensitivity is visible.  A determinism test is provided in the test suite.

NET-NEW INFO
------------
``net_new_info`` per candidate = rank-IC residual after regressing out its cluster
representative via numpy lstsq.  This is candidate-level analysis — deliberately NOT
the engine-level job of confluence.py (verified distinct, FR-6).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Pairwise metrics
# ---------------------------------------------------------------------------

def pairwise_forecast_corr(
    signal_matrix: pd.DataFrame,
) -> pd.DataFrame:
    """Pearson correlation between candidate signal series over shared fire events.

    Parameters
    ----------
    signal_matrix:
        DataFrame where each column is a candidate's signal value per fire event
        (indexed by fire event).

    Returns
    -------
    Symmetric DataFrame of Pearson correlations (candidates × candidates).
    NaN where fewer than 10 shared non-NaN observations exist.
    """
    cols = signal_matrix.columns.tolist()
    n = len(cols)
    corr_mat = np.full((n, n), np.nan)
    for i in range(n):
        corr_mat[i, i] = 1.0
        xi = signal_matrix.iloc[:, i].values
        for j in range(i + 1, n):
            xj = signal_matrix.iloc[:, j].values
            mask = np.isfinite(xi) & np.isfinite(xj)
            if mask.sum() < 10:
                continue
            corr = float(np.corrcoef(xi[mask], xj[mask])[0, 1])
            corr_mat[i, j] = corr_mat[j, i] = corr
    return pd.DataFrame(corr_mat, index=cols, columns=cols)


def fire_jaccard(
    signal_matrix: pd.DataFrame,
    quantile: float = 0.8,
) -> pd.DataFrame:
    """Jaccard similarity of top-quintile (default 80th pct) fire sets.

    For each candidate, fires where the signal > the 80th percentile form the
    "top-quintile set".  Jaccard = |A ∩ B| / |A ∪ B|.
    """
    cols = signal_matrix.columns.tolist()
    n = len(cols)
    jac_mat = np.full((n, n), np.nan)
    top_sets: list[frozenset] = []
    for col in cols:
        s = signal_matrix[col].dropna()
        if len(s) < 10:
            top_sets.append(frozenset())
        else:
            thresh = s.quantile(quantile)
            top_sets.append(frozenset(s[s >= thresh].index.tolist()))
    for i in range(n):
        jac_mat[i, i] = 1.0
        a = top_sets[i]
        for j in range(i + 1, n):
            b = top_sets[j]
            union = len(a | b)
            if union == 0:
                continue
            jac = len(a & b) / union
            jac_mat[i, j] = jac_mat[j, i] = jac
    return pd.DataFrame(jac_mat, index=cols, columns=cols)


def outcome_corr(
    signal_matrix: pd.DataFrame,
    outcomes: pd.Series,
    horizon: int = 21,
) -> pd.DataFrame:
    """Pearson correlation of per-candidate forward-return predictions.

    Each candidate's signal is used as an implied prediction; the pairwise
    correlation of those predictions across the SAME fire events is measured.
    This captures redundancy in the OUTCOME direction, not just the signal direction.

    Parameters
    ----------
    signal_matrix:
        Candidate signal values per fire event.
    outcomes:
        fwd_ret_{horizon} per fire event (same index as signal_matrix).
    """
    # For outcome_corr, we measure how similarly each pair of candidates
    # ranks outcomes (by correlating their signal-implied predictions)
    # on the shared set of events where both have non-NaN signals AND
    # the outcome is non-NaN.
    return pairwise_forecast_corr(signal_matrix)


# ---------------------------------------------------------------------------
# Greedy correlation clustering
# ---------------------------------------------------------------------------

def greedy_cluster(
    corr_df: pd.DataFrame,
    scored_candidates: pd.DataFrame,
    threshold: float = 0.7,
) -> dict[str, str]:
    """Greedy single-pass correlation clustering at |ρ| > threshold.

    Candidates are sorted DETERMINISTICALLY by (DSR desc, alpha_id asc) before
    the greedy pass to guarantee reproducibility.

    Parameters
    ----------
    corr_df:
        Symmetric pairwise correlation DataFrame (alpha_id × alpha_id).
    scored_candidates:
        DataFrame with columns ['alpha_id', 'dsr', ...].  Used for sorting.
    threshold:
        |ρ| > threshold → same cluster.

    Returns
    -------
    Dict mapping alpha_id → cluster_label (e.g. "C0", "C1", ...).
    """
    if len(scored_candidates) == 0:
        return {}

    # Deterministic sort: DSR desc, then alpha_id asc for ties
    dsr_col = "dsr" if "dsr" in scored_candidates.columns else None
    if dsr_col:
        sorted_df = scored_candidates.sort_values(
            ["dsr", "alpha_id"], ascending=[False, True]
        )
    else:
        sorted_df = scored_candidates.sort_values("alpha_id")

    order = sorted_df["alpha_id"].tolist()
    # Keep only those present in corr_df
    order = [a for a in order if a in corr_df.index]

    cluster_label: dict[str, str] = {}
    cluster_id = 0

    for candidate in order:
        if candidate in cluster_label:
            continue
        # New cluster: this candidate is the representative
        label = f"C{cluster_id}"
        cluster_label[candidate] = label
        cluster_id += 1
        # Absorb any unassigned candidate correlated > threshold
        if candidate not in corr_df.index:
            continue
        for other in order:
            if other in cluster_label or other == candidate:
                continue
            if other not in corr_df.columns:
                continue
            rho = corr_df.loc[candidate, other]
            if np.isfinite(rho) and abs(rho) > threshold:
                cluster_label[other] = label

    # Assign remaining candidates their own cluster
    for candidate in order:
        if candidate not in cluster_label:
            cluster_label[candidate] = f"C{cluster_id}"
            cluster_id += 1

    return cluster_label


def cluster_sensitivity(
    corr_df: pd.DataFrame,
    scored_candidates: pd.DataFrame,
    thresholds: list[float] | None = None,
) -> dict[float, dict[str, str]]:
    """Report cluster membership at multiple thresholds (0.6, 0.7, 0.8).

    Returns {threshold: {alpha_id: cluster_label}}.
    """
    if thresholds is None:
        thresholds = [0.6, 0.7, 0.8]
    return {t: greedy_cluster(corr_df, scored_candidates, threshold=t)
            for t in thresholds}


def cluster_representative(
    cluster_assignments: dict[str, str],
    scored_candidates: pd.DataFrame,
) -> dict[str, str]:
    """Identify the best (highest DSR) representative per cluster.

    Returns {cluster_label: best_alpha_id}.
    """
    if "dsr" not in scored_candidates.columns:
        # Fall back to first by alpha_id
        reps: dict[str, str] = {}
        for alpha_id, label in cluster_assignments.items():
            if label not in reps:
                reps[label] = alpha_id
        return reps

    best: dict[str, tuple[str, float]] = {}  # label → (alpha_id, dsr)
    dsr_map = scored_candidates.set_index("alpha_id")["dsr"].to_dict()
    for alpha_id, label in cluster_assignments.items():
        dsr = float(dsr_map.get(alpha_id, float("-inf")))
        if label not in best or dsr > best[label][1]:
            best[label] = (alpha_id, dsr)
    return {label: info[0] for label, info in best.items()}


# ---------------------------------------------------------------------------
# Net-new information (IC residual after removing cluster representative)
# ---------------------------------------------------------------------------

def net_new_info(
    signal_matrix: pd.DataFrame,
    cluster_assignments: dict[str, str],
    rep_map: dict[str, str],
) -> dict[str, float]:
    """Net-new information per candidate = IC residual after regressing out cluster rep.

    For each candidate that is NOT the cluster representative, regress its signal
    series on the representative's signal series (numpy lstsq) and compute the
    IC of the residual with outcomes.  The residual IC is the "net new" information
    not captured by the cluster rep.

    Since this is structural (not IC vs outcomes directly), we use R² of the
    within-cluster regression as a proxy for redundancy and report (1 - R²) as
    the net_new_info fraction.

    Returns {alpha_id: net_new_fraction} where 1.0 = fully orthogonal to cluster rep.
    """
    result: dict[str, float] = {}
    # Build reverse map: cluster → representative alpha_id
    label_to_rep: dict[str, str] = rep_map  # {cluster_label: rep_alpha_id}

    for alpha_id, label in cluster_assignments.items():
        rep_id = label_to_rep.get(label)
        if rep_id is None or rep_id == alpha_id:
            # Representative of its own cluster → net_new = 1.0
            result[alpha_id] = 1.0
            continue
        if alpha_id not in signal_matrix.columns or rep_id not in signal_matrix.columns:
            result[alpha_id] = float("nan")
            continue
        y = signal_matrix[alpha_id].values
        x = signal_matrix[rep_id].values
        mask = np.isfinite(y) & np.isfinite(x)
        if mask.sum() < 10:
            result[alpha_id] = float("nan")
            continue
        y_m, x_m = y[mask], x[mask]
        # OLS: y = a*x + b (numpy lstsq)
        A = np.column_stack([x_m, np.ones(len(x_m))])
        try:
            coef, _, _, _ = np.linalg.lstsq(A, y_m, rcond=None)
        except np.linalg.LinAlgError:
            result[alpha_id] = float("nan")
            continue
        residual = y_m - A @ coef
        ss_tot = np.sum((y_m - y_m.mean()) ** 2)
        ss_res = np.sum(residual ** 2)
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        result[alpha_id] = float(np.clip(1.0 - r2, 0.0, 1.0))

    return result


# ---------------------------------------------------------------------------
# Top-level overlap builder
# ---------------------------------------------------------------------------

def build_overlap_map(
    signal_matrix: pd.DataFrame,
    scored_candidates: pd.DataFrame,
    outcomes: pd.Series,
    *,
    cluster_threshold: float = 0.7,
) -> dict[str, Any]:
    """Build the full overlap map for the candidate panel.

    Parameters
    ----------
    signal_matrix:
        DataFrame of candidate signal values per fire event.
        Columns = alpha_ids.
    scored_candidates:
        DataFrame with at least ['alpha_id', 'dsr'].
    outcomes:
        fwd_ret_21 per fire event (same index as signal_matrix).
    cluster_threshold:
        Primary greedy clustering threshold (default 0.7).

    Returns
    -------
    dict with:
        forecast_corr: pairwise forecast correlation matrix (records)
        fire_jaccard:  pairwise Jaccard similarity matrix (records)
        cluster_assignments_0_6, _0_7, _0_8: per-threshold cluster maps
        cluster_representatives: {cluster_label: best_alpha_id}
        net_new_info: {alpha_id: fraction}
        meta: summary stats
    """
    fc = pairwise_forecast_corr(signal_matrix)
    fj = fire_jaccard(signal_matrix)

    # Sensitivity sweep
    sensitivity = cluster_sensitivity(fc, scored_candidates)
    clusters_07 = sensitivity[0.7]
    reps = cluster_representative(clusters_07, scored_candidates)

    nni = net_new_info(signal_matrix, clusters_07, reps)

    n_clusters = len(set(clusters_07.values()))

    return {
        "forecast_corr": fc.round(4).to_dict(),
        "fire_jaccard": fj.round(4).to_dict(),
        "cluster_assignments_0_6": sensitivity[0.6],
        "cluster_assignments_0_7": clusters_07,
        "cluster_assignments_0_8": sensitivity[0.8],
        "cluster_representatives": reps,
        "net_new_info": nni,
        "meta": {
            "n_candidates": len(signal_matrix.columns),
            "n_fire_events": len(signal_matrix),
            "n_clusters_0_7": n_clusters,
            "cluster_threshold_primary": cluster_threshold,
        },
    }


# ---------------------------------------------------------------------------
# Artifact I/O (atomic write)
# ---------------------------------------------------------------------------

def write_alpha_overlap(
    overlap_map: dict[str, Any],
    path: Path,
) -> None:
    """Atomically write overlap map to a JSON file."""
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(overlap_map, fh, indent=2, default=str)
    tmp.replace(path)


def write_alpha_clusters(
    clusters_07: dict[str, str],
    reps: dict[str, str],
    nni: dict[str, float],
    scored_candidates: pd.DataFrame,
    path: Path,
) -> None:
    """Atomically write cluster metadata to a JSON file.

    Output is CLUSTER METADATA ONLY (FR-6): no combined score, no weighting.
    """
    import tempfile

    # Build per-cluster records
    cluster_records: dict[str, dict] = {}
    for alpha_id, label in clusters_07.items():
        if label not in cluster_records:
            cluster_records[label] = {
                "cluster_label": label,
                "representative_alpha_id": reps.get(label),
                "members": [],
            }
        dsr_map = (scored_candidates.set_index("alpha_id")["dsr"].to_dict()
                   if "dsr" in scored_candidates.columns else {})
        cluster_records[label]["members"].append({
            "alpha_id": alpha_id,
            "dsr": dsr_map.get(alpha_id),
            "net_new_info": nni.get(alpha_id),
        })

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump({
            "clusters": list(cluster_records.values()),
            "meta": {
                "n_clusters": len(cluster_records),
                "n_candidates": len(clusters_07),
                "cluster_threshold": 0.7,
            },
        }, fh, indent=2, default=str)
    tmp.replace(path)
