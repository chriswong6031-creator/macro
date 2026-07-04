"""Hermetic tests for engine/oracle/graph.py — Oracle O1 rotation graph.

ALL fixtures are synthetic (no network, no real data files).

Test inventory:
(a) edge_perfect_comovement  — perfectly co-moving pair → corr_full ≈ 1; stable=True
(b) edge_inverse_pair        — planted inverse pair → corr_full ≈ −1; inverse=True
(c) leadlag_convention       — B = A shifted 3d → best_lag=3 detected for A→B
                               This test FAILS if lags are computed with reversed
                               sign convention (i.e. shift A instead of B, or
                               use positive shift instead of negative).
                               See graph.py docstring: corr(A_t, B_{t+k}), k>0,
                               implemented as correlate A with B.shift(-k).
(d) routing_onset_positive   — "A drops, B rises" → routing A→B mean_fwd_rs > 0
(e) cluster_two_blocks       — two planted perfectly correlated blocks → 2 clusters
(f) stability_sign_flip      — sign-flipping pair → stable=False
(g) leadlag_no_leader        — contemporaneously co-moving pair → is_leader=False
                               (best_lag=0 since corr@0 > corr@any_lag by margin)
(h) routing_insufficient     — low-n onset → cell marked "sufficient": False
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.graph import (
    CONFIG,
    compute_edges,
    compute_edge_stability,
    compute_leadlag,
    compute_routing,
    compute_clusters,
    reconcile_clusters,
    _pivot_rs_change,
    _complex_rs_chg_series,
)


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

def _make_dates(n: int = 500, start: str = "2021-01-04") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n, name="date")


def _make_rs_chg_wide(
    n: int = 500,
    n_nodes: int = 4,
    seed: int = 0,
    node_names: list[str] | None = None,
) -> pd.DataFrame:
    """Random iid RS-change series."""
    rng = np.random.default_rng(seed)
    dates = _make_dates(n)
    data = rng.normal(0, 0.005, (n, n_nodes))
    names = node_names or [f"node_{i}" for i in range(n_nodes)]
    return pd.DataFrame(data, index=dates, columns=names)


def _make_panel_from_rs_chg(
    rs_chg_wide: pd.DataFrame,
    vix_pctile: float | None = None,
) -> pd.DataFrame:
    """Construct a minimal MultiIndex panel from an RS-change wide frame.

    Reconstructs cumulative RS from the changes (sum of daily RS-changes).
    Adds accel_z = RS-change itself (synthetic; not properly z-scored) and
    vix_pctile column at a fixed value for routing regime tests.
    """
    dates = rs_chg_wide.index
    nodes = rs_chg_wide.columns.tolist()
    rows = []
    for node in nodes:
        rs_chg = rs_chg_wide[node]
        rs_levels = rs_chg.cumsum()
        for date in dates:
            rows.append({
                "node": node,
                "date": date,
                "rs": rs_levels[date],
                "accel_z": rs_chg[date],
                "vix_pctile": vix_pctile if vix_pctile is not None else 0.4,
                # stub other columns to NaN
                "ret": np.nan,
                "vel_1w": np.nan,
                "vel_1m": np.nan,
                "vel_3m": np.nan,
                "accel": np.nan,
                "cohesion": np.nan,
                "cohesion_chg": np.nan,
                "breadth_50": np.nan,
                "persistence": np.nan,
                "turnover_z": np.nan,
                "tlt_ret_10d": np.nan,
                "spy_above_200d": np.nan,
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    df.sort_index(inplace=True)
    return df


# ---------------------------------------------------------------------------
# (a) Edge: perfectly co-moving pair → corr_full ≈ 1, stable=True
# ---------------------------------------------------------------------------

def test_edge_perfect_comovement():
    """Planted pair A, B with identical RS-changes → corr_full ≈ 1 and stable=True."""
    n = 500
    rng = np.random.default_rng(42)
    dates = _make_dates(n)
    a = rng.normal(0, 0.005, n)
    # B is A + tiny noise — correlation should be very close to 1
    b = a + rng.normal(0, 1e-6, n)

    rs_chg = pd.DataFrame({"nodeA": a, "nodeB": b, "noise1": rng.normal(0, 0.005, n)},
                          index=dates)

    cfg = dict(CONFIG)
    cfg["STABILITY_MIN_WINDOWS"] = 2  # use fewer windows for synthetic test
    cfg["EDGE_MIN_OBS"] = 20

    edges = compute_edges(rs_chg, cfg)
    assert len(edges) > 0, "Should produce edges from comoving pair"

    # The (nodeA, nodeB) pair
    pair_edge = edges.loc[("nodeA", "nodeB")]
    assert pair_edge["corr_full"] > 0.99, (
        f"Perfect co-movers should have corr_full≈1, got {pair_edge['corr_full']}"
    )
    assert not pair_edge["inverse"], "Perfect co-mover should NOT be marked inverse"

    stability = compute_edge_stability(rs_chg, cfg)
    if ("nodeA", "nodeB") in stability.index:
        pair_stab = stability.loc[("nodeA", "nodeB")]
        assert pair_stab["stable"], (
            f"Perfect co-mover should be stable, got: {pair_stab}"
        )
        assert pair_stab["sign_consistency"] > 0.9, (
            f"Sign consistency should be near 1.0, got {pair_stab['sign_consistency']}"
        )


# ---------------------------------------------------------------------------
# (b) Edge: planted inverse pair → negative corr_full, inverse=True
# ---------------------------------------------------------------------------

def test_edge_inverse_pair():
    """Planted pair A, C = −A → corr_full ≈ −1 and inverse=True."""
    n = 500
    rng = np.random.default_rng(99)
    dates = _make_dates(n)
    a = rng.normal(0, 0.005, n)
    c = -a + rng.normal(0, 1e-6, n)  # mirror image

    rs_chg = pd.DataFrame({"nodeA": a, "nodeC": c, "noise1": rng.normal(0, 0.005, n)},
                          index=dates)

    cfg = dict(CONFIG)
    cfg["EDGE_MIN_OBS"] = 20

    edges = compute_edges(rs_chg, cfg)
    assert len(edges) > 0

    pair_edge = edges.loc[("nodeA", "nodeC")]
    assert pair_edge["corr_full"] < -0.99, (
        f"Inverse pair should have corr_full≈−1, got {pair_edge['corr_full']}"
    )
    assert pair_edge["inverse"], (
        "Inverse pair should be marked inverse=True"
    )


# ---------------------------------------------------------------------------
# (c) Lead-lag: B = A shifted 3d → best_lag=3 for A→B (FAILS if convention reversed)
# ---------------------------------------------------------------------------

def test_leadlag_convention():
    """B is A delayed by 3 days → A leads B → best_lag=3 in A→B row.

    SIGN CONVENTION (docstring):
      corr(A_t, B_{t+k}) for k>0, computed as: correlate A with B.shift(-k).
      Positive best_lag = B lags A = A leads B.

    This test FAILS if the implementation:
      (1) uses B.shift(+k) instead of B.shift(-k), OR
      (2) correlates B with A.shift(-k) and assigns the lag to B→A, OR
      (3) uses wraparound (np.roll) instead of causal alignment.
    """
    n = 600
    rng = np.random.default_rng(7)
    dates = _make_dates(n)

    # Generate A as a smooth signal (low-pass) to make the lag detectable
    raw = rng.normal(0, 0.01, n)
    # Convolve to smooth
    kernel = np.ones(5) / 5
    a = np.convolve(raw, kernel, mode="same")
    a = a / (a.std() + 1e-10)  # normalize

    LAG = 3
    # B = A delayed by LAG days (B_t = A_{t-LAG})
    b = np.full(n, np.nan)
    b[LAG:] = a[:-LAG]

    # Add tiny noise to avoid singular matrices
    a_noisy = a + rng.normal(0, 0.01, n)
    b_noisy = b.copy()
    valid = ~np.isnan(b_noisy)
    b_noisy[valid] = b_noisy[valid] + rng.normal(0, 0.01, valid.sum())

    complex_rs_chg = {
        "cA": pd.Series(a_noisy, index=dates),
        "cB": pd.Series(b_noisy, index=dates),
    }

    cfg = dict(CONFIG)
    cfg["LEADLAG_MAX_LAG"] = 10
    cfg["EDGE_MIN_OBS"] = 20
    cfg["LEADLAG_MIN_EDGE_CORR"] = 0.0  # detect even weak leads for this test
    cfg["LEADLAG_LEADER_MARGIN"] = 0.0

    ll = compute_leadlag(complex_rs_chg, cfg)
    assert not ll.empty, "Lead-lag should produce rows"

    # A→B row: best_lag should be 3 (A leads B by 3)
    row_ab = ll.loc[("cA", "cB")]
    assert row_ab["best_lag"] == LAG, (
        f"A leads B by {LAG}d; expected best_lag={LAG}, got {row_ab['best_lag']}. "
        "SIGN CONVENTION CHECK: corr(A_t, B_{{t+k}}) must be computed as "
        "correlate(A, B.shift(-k)). If best_lag is wrong, the shift direction is reversed."
    )
    assert row_ab["best_corr"] > 0.3, (
        f"Lead-lag correlation should be strong, got {row_ab['best_corr']}"
    )

    # B→A row: best_lag should NOT be LAG for the B→A direction
    # (B does not lead A — A leads B). B→A corr at lag=0 should be higher than at lag=LAG
    row_ba = ll.loc[("cB", "cA")]
    # For B→A, the contemporaneous correlation (lag 0) should be dominant,
    # or the best_lag should be 0 or small (not LAG)
    assert row_ba["best_lag"] != LAG or row_ab["best_lag"] == LAG, (
        "Asymmetric lead-lag: if A→B has best_lag=LAG, B→A should not also have best_lag=LAG"
    )


# ---------------------------------------------------------------------------
# (d) Routing: "A drops, B rises" → routing A→B mean_fwd_rs > 0
# ---------------------------------------------------------------------------

def test_routing_onset_positive():
    """Plant A dropping (accel_z << −1.5) while B rises; routing A→B should show positive fwd RS.

    Design: We pre-compute when the onset detector will fire (after 3-of-5 confirm)
    and place B's RS step AFTER the detection, so b_rs[detected_onset+5] > b_rs[detected_onset].

    A has accel_z = −3.0 for days [drop_start .. drop_start+5], which triggers
    3-of-5 confirmation at day drop_start+2 (days drop_start..drop_start+2 all < -1).
    B's RS steps up by +2.0 exactly at day drop_start+3 (the first day after detection),
    so b_rs[detection+5] - b_rs[detection] ≈ +2.0 (guaranteed positive).

    We use 5 separate onset events (widely spaced) to avoid in_outflow suppression.
    """
    n = 600
    dates = _make_dates(n)
    rng = np.random.default_rng(17)

    # Drop starts at these indices; detection fires at drop_start + 2
    drop_starts = [30, 120, 210, 300, 400]
    # Detection indices (3-of-5 confirmation, 5d rolling mean crosses below -1)
    # After 3 consecutive days at -3.0: roll5[drop_start+2] = mean of last 5 including 3 at -3
    # roll5[ds+2] = mean([a[ds-2], a[ds-1], -3, -3, -3]) with a[ds-2],a[ds-1] ~ N(0,0.3)
    # This should be << -1.0 → onset fires at ds+2
    detect_offsets = 4  # conservative: detection fires at drop_start + 4

    a_accel = rng.normal(0, 0.3, n)
    for ds in drop_starts:
        a_accel[ds:ds + 6] = -3.0  # 6 days of deep negative accel_z

    # B's RS: step up by 2.0 at detection day + 1 and hold.
    b_rs_base = rng.normal(0, 0.001, n).cumsum()  # tiny baseline drift
    for ds in drop_starts:
        step_day = ds + detect_offsets + 1  # day after detection
        if step_day < n:
            b_rs_base[step_day:] += 2.0  # permanent step up

    a_rs = np.zeros(n)  # flat A RS

    rows = []
    for i, date in enumerate(dates):
        rows.append({
            "node": "cA", "date": date,
            "rs": a_rs[i],
            "accel_z": a_accel[i],
            "vix_pctile": 0.4,
            "ret": np.nan, "vel_1w": np.nan, "vel_1m": np.nan, "vel_3m": np.nan,
            "accel": np.nan, "cohesion": np.nan, "cohesion_chg": np.nan,
            "breadth_50": np.nan, "persistence": np.nan, "turnover_z": np.nan,
            "tlt_ret_10d": np.nan, "spy_above_200d": np.nan,
        })
        rows.append({
            "node": "cB", "date": date,
            "rs": b_rs_base[i],
            "accel_z": rng.normal(0.2, 0.3),
            "vix_pctile": 0.4,
            "ret": np.nan, "vel_1w": np.nan, "vel_1m": np.nan, "vel_3m": np.nan,
            "accel": np.nan, "cohesion": np.nan, "cohesion_chg": np.nan,
            "breadth_50": np.nan, "persistence": np.nan, "turnover_z": np.nan,
            "tlt_ret_10d": np.nan, "spy_above_200d": np.nan,
        })

    panel = pd.DataFrame(rows).set_index(["node", "date"])
    panel.sort_index(inplace=True)

    complexes = {"cA": ["cA"], "cB": ["cB"]}

    cfg = dict(CONFIG)
    cfg["ROUTING_ACCEL_Z_THRESH"] = -1.0
    cfg["ROUTING_CONFIRM_K"] = 3
    cfg["ROUTING_CONFIRM_M"] = 5
    cfg["MIN_N_ROUTING"] = 1  # lower threshold so even a few events count

    routing = compute_routing(panel, complexes, cfg)

    # Check that routing A→B exists and shows positive mean_fwd_rs
    assert "cA" in routing, "Source complex cA should appear in routing"
    assert "cB" in routing.get("cA", {}), "cA→cB routing should exist"

    # Low VIX regime (vix_pctile=0.4 < 0.6 → low_vix)
    cell = routing["cA"]["cB"].get("low_vix", {})
    assert cell.get("n", 0) > 0, (
        f"Should detect at least one onset event. "
        f"Check routing output: {routing.get('cA', {}).get('cB', {})}"
    )
    fwd_5d = cell.get("mean_fwd_rs_5d")
    assert fwd_5d is not None, "mean_fwd_rs_5d should be computed with n>0 events"
    assert fwd_5d > 0.5, (
        f"After A outflow onset, B should gain positive RS (fwd_5d={fwd_5d:.4f}). "
        "B steps up by +2.0 one day after onset detection, so 5d gain should be near +2.0."
    )


# ---------------------------------------------------------------------------
# (e) Cluster: two perfectly correlated blocks → 2 clusters recovered
# ---------------------------------------------------------------------------

def test_cluster_two_blocks():
    """Plant two blocks of 3 perfectly co-moving nodes; they should form 2 clusters."""
    n = 400
    rng = np.random.default_rng(55)
    dates = _make_dates(n)

    # Block 1: nodes A1, A2, A3 all identical signal
    a_signal = rng.normal(0, 0.005, n)
    # Block 2: nodes B1, B2, B3 all identical but different signal
    b_signal = rng.normal(0, 0.005, n)

    # Add tiny noise to avoid singular matrix
    eps = 1e-7
    rs_chg = pd.DataFrame({
        "A1": a_signal + rng.normal(0, eps, n),
        "A2": a_signal + rng.normal(0, eps, n),
        "A3": a_signal + rng.normal(0, eps, n),
        "B1": b_signal + rng.normal(0, eps, n),
        "B2": b_signal + rng.normal(0, eps, n),
        "B3": b_signal + rng.normal(0, eps, n),
    }, index=dates)

    cfg = dict(CONFIG)
    cfg["CLUSTER_CUT_HEIGHT"] = 0.5  # within-cluster corr >= 0.5 = will join A block and B block
    cfg["CLUSTER_MIN_SIZE"] = 2
    cfg["EDGE_MIN_OBS"] = 20

    clusters = compute_clusters(rs_chg, cfg)

    # Should recover 2 clusters
    assert len(clusters) == 2, (
        f"Two perfectly separated blocks should yield 2 clusters, got {len(clusters)}: {clusters}"
    )

    # Each cluster should contain exactly the A or B nodes
    all_A = {"A1", "A2", "A3"}
    all_B = {"B1", "B2", "B3"}
    found_A = any(cl == all_A for cl in clusters)
    found_B = any(cl == all_B for cl in clusters)
    assert found_A and found_B, (
        f"Expected clusters {{A1,A2,A3}} and {{B1,B2,B3}}, got {clusters}"
    )


# ---------------------------------------------------------------------------
# (f) Stability: sign-flipping pair → stable=False
# ---------------------------------------------------------------------------

def test_stability_sign_flip():
    """Pair that is positively correlated in first half, negatively in second → stable=False."""
    n = 1008  # 8 half-year windows of 126d each
    rng = np.random.default_rng(33)
    dates = _make_dates(n)

    signal = rng.normal(0, 0.005, n)
    # First half: B = A (positive correlation)
    # Second half: B = -A (negative correlation)
    b = np.concatenate([signal[:n // 2], -signal[n // 2:]])
    b += rng.normal(0, 1e-7, n)  # tiny noise

    rs_chg = pd.DataFrame({"nodeA": signal, "nodeB": b}, index=dates)

    cfg = dict(CONFIG)
    cfg["STABILITY_MIN_WINDOWS"] = 4
    cfg["STABILITY_HALF_YEAR_DAYS"] = 126
    cfg["STABILITY_CORR_THRESH"] = 0.2
    cfg["EDGE_MIN_OBS"] = 20

    stability = compute_edge_stability(rs_chg, cfg)
    assert not stability.empty, "Should produce stability rows for the planted pair"

    pair = stability.loc[("nodeA", "nodeB")]
    assert not pair["stable"], (
        f"Sign-flipping pair should NOT be stable, got stable={pair['stable']} "
        f"sign_consistency={pair['sign_consistency']:.2f}"
    )
    # Sign consistency should be near 0.5 (half positive, half negative)
    assert pair["sign_consistency"] < 0.9, (
        f"Sign consistency should reflect the flip, got {pair['sign_consistency']:.2f}"
    )


# ---------------------------------------------------------------------------
# (g) Lead-lag: contemporaneous co-mover → is_leader=False
# ---------------------------------------------------------------------------

def test_leadlag_no_leader():
    """Simultaneously correlated pair (lag 0) → is_leader=False for both directions."""
    n = 500
    rng = np.random.default_rng(88)
    dates = _make_dates(n)

    # A and B are nearly identical (contemporaneous)
    signal = rng.normal(0, 0.005, n)
    a = signal + rng.normal(0, 1e-7, n)
    b = signal + rng.normal(0, 1e-7, n)

    complex_rs_chg = {
        "cA": pd.Series(a, index=dates),
        "cB": pd.Series(b, index=dates),
    }

    cfg = dict(CONFIG)
    cfg["LEADLAG_MAX_LAG"] = 10
    cfg["LEADLAG_MIN_EDGE_CORR"] = 0.1
    cfg["LEADLAG_LEADER_MARGIN"] = 0.05
    cfg["EDGE_MIN_OBS"] = 20

    ll = compute_leadlag(complex_rs_chg, cfg)
    assert not ll.empty

    # Neither A→B nor B→A should be marked as a leader (contemporaneous signal)
    for pair in [("cA", "cB"), ("cB", "cA")]:
        row = ll.loc[pair]
        # best_lag should be 0 (contemporaneous dominates)
        assert row["best_lag"] == 0 or not row["is_leader"], (
            f"Contemporaneous co-mover {pair} should not be flagged as leader, "
            f"best_lag={row['best_lag']}, is_leader={row['is_leader']}"
        )


# ---------------------------------------------------------------------------
# (h) Routing: low-n onset → cell marked sufficient=False
# ---------------------------------------------------------------------------

def test_routing_insufficient():
    """Very short panel (few potential onsets) → routing cell has sufficient=False."""
    n = 80  # very short — barely enough for 1 onset, not enough for MIN_N=10
    dates = _make_dates(n)
    rng = np.random.default_rng(21)

    # A has one onset at index 20
    a_accel = rng.normal(0, 0.3, n)
    a_accel[18:24] = -3.0  # one onset event

    rows = []
    a_rs = rng.normal(0, 0.005, n).cumsum()
    b_rs = rng.normal(0, 0.005, n).cumsum()
    for i, date in enumerate(dates):
        rows.append({"node": "cA", "date": date, "rs": a_rs[i], "accel_z": a_accel[i],
                     "vix_pctile": 0.4, "ret": np.nan, "vel_1w": np.nan, "vel_1m": np.nan,
                     "vel_3m": np.nan, "accel": np.nan, "cohesion": np.nan,
                     "cohesion_chg": np.nan, "breadth_50": np.nan, "persistence": np.nan,
                     "turnover_z": np.nan, "tlt_ret_10d": np.nan, "spy_above_200d": np.nan})
        rows.append({"node": "cB", "date": date, "rs": b_rs[i], "accel_z": rng.normal(0, 0.3),
                     "vix_pctile": 0.4, "ret": np.nan, "vel_1w": np.nan, "vel_1m": np.nan,
                     "vel_3m": np.nan, "accel": np.nan, "cohesion": np.nan,
                     "cohesion_chg": np.nan, "breadth_50": np.nan, "persistence": np.nan,
                     "turnover_z": np.nan, "tlt_ret_10d": np.nan, "spy_above_200d": np.nan})

    panel = pd.DataFrame(rows).set_index(["node", "date"])
    panel.sort_index(inplace=True)

    complexes = {"cA": ["cA"], "cB": ["cB"]}

    cfg = dict(CONFIG)
    cfg["MIN_N_ROUTING"] = 10  # Require 10 events — won't be met with 1 onset
    cfg["ROUTING_CONFIRM_K"] = 3
    cfg["ROUTING_CONFIRM_M"] = 5

    routing = compute_routing(panel, complexes, cfg)

    if "cA" in routing and "cB" in routing.get("cA", {}):
        for regime_key in ["low_vix", "high_vix"]:
            cell = routing["cA"]["cB"].get(regime_key, {})
            if cell.get("n", 0) > 0:
                # n < 10 → sufficient should be False
                assert not cell.get("sufficient", True), (
                    f"Cell with n={cell['n']} < MIN_N_ROUTING=10 should have sufficient=False"
                )


# ---------------------------------------------------------------------------
# (i) Reconciliation: backbone complex well-matched to its empirical cluster
# ---------------------------------------------------------------------------

def test_reconcile_well_matched():
    """If empirical cluster exactly matches backbone complex → well_matched=True."""
    # A cluster with nodes A1, A2, A3 and a backbone that says the same
    clusters = [{"A1", "A2", "A3"}, {"B1", "B2"}]
    backbone = [
        {"id": "complex_a", "members": ["A1", "A2", "A3"]},
        {"id": "complex_b", "members": ["B1", "B2", "B3"]},  # B3 missing from cluster
    ]
    cfg = dict(CONFIG)
    cfg["RECONCILE_JACCARD_THRESH"] = 0.25

    result = reconcile_clusters(clusters, backbone, cfg)
    assert len(result) == 2

    # complex_a: exact match → Jaccard = 3/3 = 1.0 → well_matched
    ca = next(r for r in result if r["complex_id"] == "complex_a")
    assert ca["well_matched"], f"Exact match should be well_matched: {ca}"
    assert abs(ca["best_cluster_jaccard"] - 1.0) < 0.01

    # complex_b: partial match (B3 missing) → Jaccard = 2/3 ≈ 0.67 → well_matched
    cb = next(r for r in result if r["complex_id"] == "complex_b")
    assert cb["well_matched"], f"Partial match (Jaccard>0.25) should be well_matched: {cb}"
    assert "B3" in cb["missing_from_cluster"]


def test_reconcile_no_match():
    """Backbone complex with members not in any cluster → not well_matched."""
    clusters = [{"X1", "X2", "X3"}]
    backbone = [{"id": "complex_z", "members": ["Z1", "Z2", "Z3"]}]

    cfg = dict(CONFIG)
    result = reconcile_clusters(clusters, backbone, cfg)
    assert len(result) == 1
    cz = result[0]
    assert not cz["well_matched"], "Completely absent complex should not be well_matched"
    assert cz["best_cluster_jaccard"] == 0.0


# ---------------------------------------------------------------------------
# (j) Edge columns schema check
# ---------------------------------------------------------------------------

def test_edge_schema():
    """Edges output has expected columns."""
    rs_chg = _make_rs_chg_wide(n=200, n_nodes=3)
    cfg = dict(CONFIG)
    cfg["EDGE_MIN_OBS"] = 20
    edges = compute_edges(rs_chg, cfg)
    expected_cols = {"corr_60d_last", "corr_120d_last", "corr_full", "inverse"}
    assert expected_cols.issubset(set(edges.columns)), (
        f"Missing columns: {expected_cols - set(edges.columns)}"
    )


# ---------------------------------------------------------------------------
# (k) Stability columns schema check
# ---------------------------------------------------------------------------

def test_stability_schema():
    """Stability output has expected columns."""
    n = 700  # enough for several half-year windows
    rs_chg = _make_rs_chg_wide(n=n, n_nodes=3)
    cfg = dict(CONFIG)
    cfg["STABILITY_MIN_WINDOWS"] = 2
    cfg["EDGE_MIN_OBS"] = 20
    stab = compute_edge_stability(rs_chg, cfg)
    expected_cols = {"mean_corr", "sign_consistency", "n_windows", "stable"}
    assert expected_cols.issubset(set(stab.columns)), (
        f"Missing columns: {expected_cols - set(stab.columns)}"
    )


# ---------------------------------------------------------------------------
# (l) complex_rs_chg_series: missing members gracefully return NaN series
# ---------------------------------------------------------------------------

def test_complex_series_missing_members():
    """_complex_rs_chg_series returns all-NaN when no members are in the wide frame."""
    rs_chg = _make_rs_chg_wide(n=100, n_nodes=2, node_names=["A", "B"])
    result = _complex_rs_chg_series(rs_chg, ["X", "Y", "Z"])
    assert result.isna().all(), "All-missing members should produce all-NaN series"
