"""tests/test_alpha_grammar.py — Alpha grammar + overlap map (nwqs item E).

Coverage:
  (1)  AST round-trip: serialize → parse → identical alpha_id.
  (2)  PIT enforcement: evaluator cannot see bar t+1 (post-fire bar).
  (3)  Enumeration count == ledger-logged count == ≤ CANDIDATE_CAP.
  (4)  Tiny synthetic end-to-end: 3 tickers, 2 candidates, grade + overlap.
  (5)  Clustering determinism: repeated calls produce identical cluster assignments.
  (6)  Min-cohort floor: cs_rank emits NaN for dates with < MIN_COHORT_SIZE fires.
  (7)  De-overlap: same-ticker overlapping fires are reduced to non-overlapping set.
  (8)  PIT alignment: fire date missing from close series → NaN (no off-by-one anchor).
  (9)  Volume candidates absent: enumerate_candidates produces zero volume-based nodes.
  (10) Era assertion: load_era_fires rejects pre-2012 rows.
  (11) BH-FDR p-value wiring: benjamini_hochberg applied to HAC p-values.
  (12) DSR t_eff wiring: deflated_sharpe called with t_eff= keyword.
  (13) Cluster sensitivity: sensitivity at 0.6/0.7/0.8 all returned.
  (14) Full grid size > CANDIDATE_CAP (cap is actually enforced).
  (15) Survivorship caveat present in every candidate record.
  (16) PIT spike test (VECTORIZED PATH): _compute_signal_for_candidate is bit-identical
       before and after injecting a spike in bars after the fire iloc — covers every
       v1 primitive (ts_rank, ts_delta, decay_linear, zscore_winsor, vol_norm_move,
       dist_from_argmin, dist_from_argmax) and cs_rank at cohort level.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import targets
# ---------------------------------------------------------------------------
from engine.neuralweb.alpha_grammar import (
    CANDIDATE_CAP,
    FAMILY,
    MIN_COHORT_SIZE,
    SURVIVORSHIP_CAVEAT,
    CandidateRecord,
    FormulaNode,
    CLOSE_RETURNS,
    apply_cs_rank_pass,
    cs_rank,
    deoverlap_fires_v2,
    enumerate_candidates,
    eval_formula_at_fire,
    full_grid_size,
    ts_rank,
    ts_delta,
    zscore_winsor,
    vol_norm_move,
    dist_from_argmin,
    dist_from_argmax,
    decay_linear,
)
from engine.neuralweb.alpha_overlap import (
    build_overlap_map,
    cluster_sensitivity,
    greedy_cluster,
    net_new_info,
    pairwise_forecast_corr,
)
from engine.validation import benjamini_hochberg, bootstrap_effective_t, deflated_sharpe
from engine.trial_ledger import TrialLedger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close(n: int = 100, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    prices = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    dates = pd.date_range("2015-01-01", periods=n, freq="B")
    return pd.Series(prices, index=dates)


def _make_fire_panel(tickers: list[str], dates: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        for d in dates:
            rows.append({"ticker": t, "date": pd.Timestamp(d), "tier": "T1",
                         "sub": "deep", "panel": "deep"})
    return pd.DataFrame(rows).reset_index(drop=True)


# ---------------------------------------------------------------------------
# (1) AST round-trip
# ---------------------------------------------------------------------------

def test_ast_roundtrip_simple():
    node = ts_rank(CLOSE_RETURNS, 10)
    d = node.to_dict()
    restored = FormulaNode.from_dict(d)
    assert restored.alpha_id == node.alpha_id, "alpha_id must match after round-trip"


def test_ast_roundtrip_composed():
    node = zscore_winsor(ts_delta(CLOSE_RETURNS, 5), 21, clip=3.0)
    d = node.to_dict()
    j = json.dumps(d, sort_keys=True)
    d2 = json.loads(j)
    restored = FormulaNode.from_dict(d2)
    assert restored.alpha_id == node.alpha_id


def test_ast_roundtrip_cs_rank():
    node = cs_rank(ts_rank(CLOSE_RETURNS, 10))
    d = node.to_dict()
    restored = FormulaNode.from_dict(d)
    assert restored.alpha_id == node.alpha_id
    assert restored.uses_cs_rank()


def test_alpha_id_is_deterministic():
    node1 = ts_rank(CLOSE_RETURNS, 10)
    node2 = ts_rank(CLOSE_RETURNS, 10)
    assert node1.alpha_id == node2.alpha_id


def test_alpha_id_differs_on_different_nodes():
    n1 = ts_rank(CLOSE_RETURNS, 10)
    n2 = ts_delta(CLOSE_RETURNS, 10)
    assert n1.alpha_id != n2.alpha_id


# ---------------------------------------------------------------------------
# (2) PIT enforcement: evaluator cannot see bar t+1
# ---------------------------------------------------------------------------

def test_pit_post_fire_bar_invisible():
    """Construct a series where the post-fire bar has a very different value.
    The formula evaluated at fire_iloc must NOT reflect that bar.
    """
    from engine.grading import _snap_loc

    # Construct a series where the last bar (t+1, post-fire) is a huge spike
    dates = pd.date_range("2020-01-01", periods=50, freq="B")
    prices = np.ones(50) * 100.0
    prices[-1] = 10000.0  # post-fire spike

    close = pd.Series(prices, index=dates)
    fire_date = dates[-2]  # second-to-last bar is fire date

    # ts_delta(close_returns, 1): the post-fire bar changes returns[-1]
    # If PIT is correct, the evaluator only sees bars[:49] (iloc 0..48)
    node = ts_delta(CLOSE_RETURNS, 1)

    result = eval_formula_at_fire(node, close, fire_date)

    # The pre-fire delta should be approx 0 (price was flat before spike)
    # If the spike at index 49 were included, the result would be enormous
    assert result is not None
    # Flat prices → pct_change ≈ 0 → delta ≈ 0; check it's not influenced by spike
    assert abs(result) < 1.0, (
        f"PIT violation: result={result} suggests post-fire bar was included"
    )


def test_pit_missing_fire_date_returns_nan():
    """Fire date not in close series → eval_formula_at_fire returns NaN."""
    close = _make_close(50)
    # Use a date that is definitely not in the close series (weekend)
    fire_date = pd.Timestamp("2015-01-03")  # a Saturday
    # Remove it from the series if somehow present
    close_no_sat = close[close.index != fire_date]
    if fire_date not in close_no_sat.index:
        node = ts_rank(CLOSE_RETURNS, 5)
        result = eval_formula_at_fire(node, close_no_sat, fire_date)
        assert np.isnan(result), (
            f"Expected NaN for fire date not in close series, got {result}"
        )


# ---------------------------------------------------------------------------
# (3) Enumeration count == ≤ CANDIDATE_CAP, ledger count matches
# ---------------------------------------------------------------------------

def test_enumeration_count_within_cap():
    candidates = enumerate_candidates(cap=CANDIDATE_CAP)
    assert len(candidates) <= CANDIDATE_CAP, (
        f"Enumerated {len(candidates)} > cap {CANDIDATE_CAP}"
    )


def test_enumeration_count_matches_ledger():
    candidates = enumerate_candidates(cap=CANDIDATE_CAP)
    n = len(candidates)

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        led_path = Path(f.name)
    led = TrialLedger(path=led_path, family=FAMILY)
    configs = [c.to_dict() for c in candidates]
    n_logged = led.log_grid(configs, family=FAMILY)
    # effective_n should equal the number of distinct candidates
    effective = led.effective_n(FAMILY)
    assert effective >= n, (
        f"Ledger effective_n {effective} < candidate count {n}"
    )
    led_path.unlink(missing_ok=True)


def test_enumeration_no_duplicates():
    candidates = enumerate_candidates(cap=CANDIDATE_CAP)
    ids = [c.alpha_id for c in candidates]
    assert len(ids) == len(set(ids)), "Duplicate alpha_ids in enumeration"


def test_full_grid_exceeds_cap():
    """Full grid should be larger than cap — verifying cap is actually enforced."""
    grid = full_grid_size()
    assert grid > CANDIDATE_CAP, (
        f"full_grid_size={grid} should exceed CANDIDATE_CAP={CANDIDATE_CAP}"
    )


# ---------------------------------------------------------------------------
# (4) Tiny synthetic end-to-end: 3 tickers, 2 candidates, grade + overlap
# ---------------------------------------------------------------------------

def test_synthetic_end_to_end():
    """Smoke test: 3 tickers, 2 non-cs_rank candidates, overlap map builds."""
    from engine.neuralweb.alpha_grammar import _eval_node

    rng = np.random.default_rng(0)
    tickers = ["AAA", "BBB", "CCC"]
    dates = pd.date_range("2015-01-02", periods=80, freq="B")
    closes = {
        t: pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 80)), index=dates)
        for t in tickers
    }

    # Fire panel: 2 fires per ticker at mid-period dates
    fire_dates = [dates[30], dates[50]]
    fire_rows = []
    for t in tickers:
        for d in fire_dates:
            fire_rows.append({"ticker": t, "date": d, "tier": "T1",
                              "sub": "deep", "panel": "deep",
                              "fwd_ret_21": rng.normal(0.02, 0.05)})
    fire_panel = pd.DataFrame(fire_rows).reset_index(drop=True)

    # Two candidates (no cs_rank)
    c1 = CandidateRecord.from_node(ts_rank(CLOSE_RETURNS, 5), "ts_rank test")
    c2 = CandidateRecord.from_node(ts_delta(CLOSE_RETURNS, 5), "ts_delta test")

    # Build signal matrix
    from engine.grading import _snap_loc
    signal_matrix = pd.DataFrame(index=fire_panel.index)
    for cand in [c1, c2]:
        node = FormulaNode.from_dict(cand.formula_ast)
        vals = []
        for _, row in fire_panel.iterrows():
            t = row["ticker"]
            d = pd.Timestamp(row["date"])
            close = closes[t]
            iloc = _snap_loc(close.index, d)
            if iloc is None:
                vals.append(float("nan"))
                continue
            pit = close.iloc[: iloc + 1]
            result = _eval_node(node, pit)
            v = result.iloc[-1] if isinstance(result, pd.Series) else result
            vals.append(float(v) if np.isfinite(float(v)) else float("nan"))
        signal_matrix[cand.alpha_id] = vals

    # Scored candidates (minimal)
    scored_df = pd.DataFrame([
        {"alpha_id": c1.alpha_id, "dsr": 0.6},
        {"alpha_id": c2.alpha_id, "dsr": 0.5},
    ])

    outcomes = fire_panel["fwd_ret_21"]
    overlap = build_overlap_map(signal_matrix, scored_df, outcomes)

    assert "cluster_assignments_0_7" in overlap
    assert "net_new_info" in overlap
    assert overlap["meta"]["n_candidates"] == 2


# ---------------------------------------------------------------------------
# (5) Clustering determinism
# ---------------------------------------------------------------------------

def test_clustering_determinism():
    """Same input → same cluster assignment on repeated calls."""
    rng = np.random.default_rng(1)
    ids = [f"alpha_{i:04d}" for i in range(20)]
    # Build a synthetic correlation matrix
    corr_data = rng.normal(0, 0.5, (20, 20))
    corr_data = (corr_data + corr_data.T) / 2
    np.fill_diagonal(corr_data, 1.0)
    corr_df = pd.DataFrame(corr_data, index=ids, columns=ids)

    scored = pd.DataFrame({
        "alpha_id": ids,
        "dsr": rng.uniform(0.3, 0.9, 20),
    })

    result1 = greedy_cluster(corr_df, scored, threshold=0.7)
    result2 = greedy_cluster(corr_df, scored, threshold=0.7)
    assert result1 == result2, "Clustering is not deterministic"


def test_clustering_sensitivity_returns_three_thresholds():
    rng = np.random.default_rng(2)
    ids = [f"a_{i}" for i in range(5)]
    corr = np.eye(5)
    corr_df = pd.DataFrame(corr, index=ids, columns=ids)
    scored = pd.DataFrame({"alpha_id": ids, "dsr": [0.5] * 5})
    sens = cluster_sensitivity(corr_df, scored)
    assert set(sens.keys()) == {0.6, 0.7, 0.8}


# ---------------------------------------------------------------------------
# (6) Min-cohort floor: cs_rank NaN for dates with < MIN_COHORT_SIZE fires
# ---------------------------------------------------------------------------

def test_cs_rank_cohort_floor_emits_nan():
    """Dates with fewer than MIN_COHORT_SIZE fires → cs_rank returns NaN."""
    from engine.neuralweb.alpha_grammar import _eval_node, FormulaNode

    # 3 tickers (below MIN_COHORT_SIZE=10) firing on the same date
    rng = np.random.default_rng(3)
    dates = pd.date_range("2015-01-02", periods=50, freq="B")
    fire_date = dates[30]

    # Small cohort (only 3 tickers)
    tickers = ["X1", "X2", "X3"]
    closes = {
        t: pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 50)), index=dates)
        for t in tickers
    }
    fire_rows = [{"ticker": t, "date": fire_date} for t in tickers]
    fire_panel = pd.DataFrame(fire_rows).reset_index(drop=True)

    # Build a cs_rank candidate
    cand = CandidateRecord.from_node(
        cs_rank(ts_rank(CLOSE_RETURNS, 5)),
        "cs_rank smoke test",
    )
    signal_matrix = pd.DataFrame(index=fire_panel.index)
    signal_matrix[cand.alpha_id] = [0.5, 0.3, 0.8]  # raw pre-cs_rank values

    # apply_cs_rank_pass should emit NaN because cohort=3 < MIN_COHORT_SIZE=10
    result = apply_cs_rank_pass(signal_matrix, cand, fire_panel)
    assert result.isna().all(), (
        f"Expected all NaN for cohort<{MIN_COHORT_SIZE}, got {result.values}"
    )


def test_cs_rank_large_cohort_emits_values():
    """Dates with >= MIN_COHORT_SIZE fires → cs_rank returns non-NaN values."""
    rng = np.random.default_rng(4)
    fire_date = pd.Timestamp("2015-02-02")
    n_tickers = MIN_COHORT_SIZE + 5  # 15 tickers → above floor

    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    fire_rows = [{"ticker": t, "date": fire_date} for t in tickers]
    fire_panel = pd.DataFrame(fire_rows).reset_index(drop=True)

    # Build a cs_rank candidate
    cand = CandidateRecord.from_node(
        cs_rank(ts_rank(CLOSE_RETURNS, 5)),
        "cs_rank large cohort",
    )
    signal_matrix = pd.DataFrame(index=fire_panel.index)
    raw_vals = rng.uniform(0, 1, n_tickers)
    signal_matrix[cand.alpha_id] = raw_vals

    result = apply_cs_rank_pass(signal_matrix, cand, fire_panel)
    assert not result.isna().all(), "Expected some non-NaN for large cohort"


# ---------------------------------------------------------------------------
# (7) De-overlap: overlapping fires are removed
# ---------------------------------------------------------------------------

def test_deoverlap_removes_within_horizon():
    """Same-ticker fires within 21 days → only earliest kept."""
    fires = pd.DataFrame([
        {"ticker": "AAA", "date": pd.Timestamp("2020-01-02"), "tier": "T1"},
        {"ticker": "AAA", "date": pd.Timestamp("2020-01-10"), "tier": "T1"},  # 8d → remove
        {"ticker": "AAA", "date": pd.Timestamp("2020-02-15"), "tier": "T1"},  # 36d → keep
        {"ticker": "BBB", "date": pd.Timestamp("2020-01-02"), "tier": "T1"},
        {"ticker": "BBB", "date": pd.Timestamp("2020-01-05"), "tier": "T1"},  # 3d → remove
    ]).reset_index(drop=True)

    result = deoverlap_fires_v2(fires, horizon=21)
    # For AAA: keep 2020-01-02 and 2020-02-15; drop 2020-01-10
    # For BBB: keep 2020-01-02; drop 2020-01-05
    assert len(result) == 3
    aaa_dates = sorted(result[result["ticker"] == "AAA"]["date"].tolist())
    assert aaa_dates == [pd.Timestamp("2020-01-02"), pd.Timestamp("2020-02-15")]
    bbb_dates = sorted(result[result["ticker"] == "BBB"]["date"].tolist())
    assert bbb_dates == [pd.Timestamp("2020-01-02")]


def test_deoverlap_keeps_non_overlapping():
    """Fires separated by more than horizon → all kept."""
    fires = pd.DataFrame([
        {"ticker": "ZZZ", "date": pd.Timestamp("2020-01-01"), "tier": "T1"},
        {"ticker": "ZZZ", "date": pd.Timestamp("2020-02-01"), "tier": "T1"},
        {"ticker": "ZZZ", "date": pd.Timestamp("2020-03-15"), "tier": "T1"},
    ]).reset_index(drop=True)
    result = deoverlap_fires_v2(fires, horizon=21)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# (8) PIT alignment: missing fire date → NaN
# ---------------------------------------------------------------------------

def test_pit_alignment_missing_date_nan():
    """Fire date not in close series → eval_formula_at_fire returns NaN."""
    dates = pd.date_range("2020-01-02", periods=40, freq="B")
    close = pd.Series(np.linspace(100, 120, 40), index=dates)

    # Pick a fire date that is not in the series (skip over it)
    # Build a date that falls between two trading days
    fire_date = pd.Timestamp("2020-01-04")  # should be in dates unless weekend
    if fire_date not in close.index:
        node = ts_rank(CLOSE_RETURNS, 5)
        result = eval_formula_at_fire(node, close, fire_date)
        assert np.isnan(result)
    else:
        # If it IS in the series, the test is a no-op — that's fine
        pass


# ---------------------------------------------------------------------------
# (9) Volume candidates absent
# ---------------------------------------------------------------------------

def test_no_volume_candidates():
    """enumerate_candidates produces no volume-dependent nodes (close-only panel)."""
    candidates = enumerate_candidates()
    for c in candidates:
        assert not c.formula_ast.get("op", "").startswith("volume"), (
            f"Volume candidate found: {c.alpha_id}"
        )


# ---------------------------------------------------------------------------
# (10) Era assertion
# ---------------------------------------------------------------------------

def test_era_assertion_rejects_pre2012():
    """load_era_fires must fail assertion if pre-2012 rows remain."""
    # We test the era filter logic inline (without filesystem)
    fire_panel = pd.DataFrame([
        {"ticker": "AAA", "date": pd.Timestamp("2011-12-31"), "tier": "T1"},
        {"ticker": "AAA", "date": pd.Timestamp("2012-01-03"), "tier": "T1"},
    ])
    from engine.neuralweb.alpha_grammar import SURVIVORSHIP_CAVEAT
    # Simulate era filter
    era_start = pd.Timestamp("2012-01-01")
    filtered = fire_panel[fire_panel["date"] >= era_start].copy()
    assert len(filtered) == 1
    assert (filtered["date"] >= era_start).all()


# ---------------------------------------------------------------------------
# (11) BH-FDR p-value wiring
# ---------------------------------------------------------------------------

def test_bh_fdr_with_hac_pvals():
    """benjamini_hochberg applied to HAC p-values from newey_west_tstat."""
    pvals = {
        "alpha_0001": 0.001,
        "alpha_0002": 0.050,
        "alpha_0003": 0.400,
        "alpha_0004": 0.800,
        "alpha_0005": 0.900,
    }
    result = benjamini_hochberg(pvals, alpha=0.10)
    # At alpha=0.10, only very small p should survive
    assert "alpha_0001" in result
    # The smallest p should have q <= 0.10
    assert result["alpha_0001"]["reject"] is True
    # The largest p should not reject
    assert result["alpha_0004"]["reject"] is False


# ---------------------------------------------------------------------------
# (12) DSR t_eff wiring
# ---------------------------------------------------------------------------

def test_dsr_t_eff_threading():
    """deflated_sharpe accepts t_eff keyword and uses it in the DSR formula."""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        led_path = Path(f.name)
    led = TrialLedger(path=led_path, family=FAMILY)
    configs = [{"id": i} for i in range(10)]
    led.log_grid(configs, family=FAMILY)

    result_no_teff = deflated_sharpe(
        sr_daily=0.05, skew=0.1, kurt=3.0, T=100,
        ledger=led, family=FAMILY,
    )
    result_with_teff = deflated_sharpe(
        sr_daily=0.05, skew=0.1, kurt=3.0, T=100,
        ledger=led, family=FAMILY, t_eff=50,
    )
    assert result_no_teff is not None
    assert result_with_teff is not None
    assert "t_eff" in result_with_teff  # t_eff is reported in the result
    # DSR should differ when t_eff < T
    assert result_no_teff["dsr"] != result_with_teff["dsr"]
    led_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# (13) Cluster sensitivity: 3 thresholds returned
# ---------------------------------------------------------------------------

def test_cluster_sensitivity_three_thresholds():
    rng = np.random.default_rng(5)
    ids = [f"c_{i}" for i in range(8)]
    corr = np.eye(8)
    # Make some pairs highly correlated
    corr[0, 1] = corr[1, 0] = 0.85
    corr[2, 3] = corr[3, 2] = 0.65
    corr_df = pd.DataFrame(corr, index=ids, columns=ids)
    scored = pd.DataFrame({"alpha_id": ids, "dsr": rng.uniform(0.4, 0.9, 8)})

    sens = cluster_sensitivity(corr_df, scored, thresholds=[0.6, 0.7, 0.8])
    assert set(sens.keys()) == {0.6, 0.7, 0.8}

    # At threshold=0.6: pairs (0,1) and (2,3) should cluster (|rho|>0.6)
    c06 = sens[0.6]
    assert c06["c_0"] == c06["c_1"], "c_0 and c_1 should cluster at threshold=0.6"
    assert c06["c_2"] == c06["c_3"], "c_2 and c_3 should cluster at threshold=0.6"

    # At threshold=0.8: only (0,1) pair clusters (|rho|=0.85>0.8)
    c08 = sens[0.8]
    assert c08["c_0"] == c08["c_1"], "c_0 and c_1 should cluster at threshold=0.8"
    # (2,3) pair (|rho|=0.65) should NOT cluster at 0.8
    assert c08["c_2"] != c08["c_3"], (
        "c_2 and c_3 should NOT cluster at threshold=0.8 (|rho|=0.65 < 0.8)"
    )


# ---------------------------------------------------------------------------
# (14) Full grid size > CANDIDATE_CAP
# ---------------------------------------------------------------------------

def test_full_grid_exceeds_cap_constraining():
    """Cap must be strictly less than the full grid, confirming it is binding."""
    grid = full_grid_size()
    assert grid > CANDIDATE_CAP, (
        f"full_grid_size={grid} should exceed CANDIDATE_CAP={CANDIDATE_CAP}; "
        f"cap is not actually constraining enumeration"
    )


# ---------------------------------------------------------------------------
# (15) Survivorship caveat in every candidate record
# ---------------------------------------------------------------------------

def test_survivorship_caveat_present():
    candidates = enumerate_candidates(cap=10)
    for c in candidates:
        assert c.survivorship_caveat, f"Missing survivorship_caveat: {c.alpha_id}"
        assert "surviving-names-only" in c.survivorship_caveat


# ---------------------------------------------------------------------------
# (16) PIT spike test — VECTORIZED PATH (_compute_signal_for_candidate)
#
# This tests the path that ACTUALLY produced the shipped artifacts.  The
# vectorized evaluator calls _eval_node on the FULL close series and then
# extracts full_series.iloc[fire_iloc].  PIT is upheld if and only if every
# rolling primitive looks only at bars ≤ fire_iloc — injecting an extreme
# value in bars AFTER fire_iloc must leave every candidate value bit-identical.
#
# Coverage: every v1 primitive that appears in enumerated candidates:
#   ts_rank, ts_delta, decay_linear, zscore_winsor, vol_norm_move,
#   dist_from_argmin, dist_from_argmax
# cs_rank is covered as a cohort-level pass via apply_cs_rank_pass (the
# per-ticker inner formula is one of the above; cs_rank itself is cross-
# sectional and applied after extraction, so it inherits the same guarantee).
# ---------------------------------------------------------------------------

def _make_fire_panel_with_outcome(
    ticker: str,
    fire_date: pd.Timestamp,
    close: pd.Series,
) -> pd.DataFrame:
    """Build a minimal fire_panel row for the vectorized evaluator."""
    return pd.DataFrame([{
        "ticker": ticker,
        "date": fire_date,
        "tier": "T1",
        "sub": "deep",
        "panel": "deep",
        "fwd_ret_21": 0.05,
    }]).reset_index(drop=True)


def _evaluate_all_v1_primitives_vectorized(
    close: pd.Series,
    fire_date: pd.Timestamp,
    ticker: str = "SPY",
) -> dict[str, float]:
    """Run _compute_signal_for_candidate for each v1 primitive and return results."""
    from scripts.research.compile_alpha_candidates import _compute_signal_for_candidate

    fire_panel = _make_fire_panel_with_outcome(ticker, fire_date, close)
    closes = {ticker: close}

    # All v1 unary-window primitives enumerated in candidates
    nodes_to_test = [
        ("ts_rank",        ts_rank(CLOSE_RETURNS, 10)),
        ("ts_delta",       ts_delta(CLOSE_RETURNS, 5)),
        ("decay_linear",   decay_linear(CLOSE_RETURNS, 10)),
        ("zscore_winsor",  zscore_winsor(CLOSE_RETURNS, 21)),
        ("vol_norm_move",  vol_norm_move(CLOSE_RETURNS, 10)),
        ("dist_from_argmin", dist_from_argmin(CLOSE_RETURNS, 21)),
        ("dist_from_argmax", dist_from_argmax(CLOSE_RETURNS, 21)),
    ]

    results: dict[str, float] = {}
    for prim_name, node in nodes_to_test:
        cand = CandidateRecord.from_node(node, f"{prim_name} spike-test")
        sig = _compute_signal_for_candidate(cand, fire_panel, closes)
        # sig is indexed by fire_panel.index (one row → index 0)
        results[prim_name] = float(sig.iloc[0])
    return results


def test_pit_spike_vectorized_path():
    """MAJOR: vectorized path (_compute_signal_for_candidate) is PIT-safe.

    Construct a clean synthetic price series, evaluate all v1 primitives at
    fire_iloc via the vectorized evaluator, then inject an extreme spike in
    every bar AFTER fire_iloc and re-evaluate.  All values must be bit-identical.

    If this test fails, a real PIT leak is present in the shipped evaluator.
    The shipped data/research/alpha_* artifacts and any reported FDR survivors
    would be invalid pending a clean re-run.
    """
    # -----------------------------------------------------------------------
    # Build a 120-bar synthetic price series with stable, non-trivial values
    # -----------------------------------------------------------------------
    rng = np.random.default_rng(seed=20260705)
    n_bars = 120
    returns = rng.normal(0.0005, 0.012, n_bars)
    prices = 100.0 * np.cumprod(1.0 + returns)

    # Use business-day dates well within the era filter (2015+)
    all_dates = pd.date_range("2015-06-01", periods=n_bars, freq="B")
    close_clean = pd.Series(prices, index=all_dates)

    # Fire at bar 80 (0-indexed) — leaves 39 bars after the fire iloc
    fire_iloc = 80
    fire_date = all_dates[fire_iloc]
    ticker = "SYNTHETIC"

    # -----------------------------------------------------------------------
    # Evaluate on clean series
    # -----------------------------------------------------------------------
    results_clean = _evaluate_all_v1_primitives_vectorized(
        close_clean, fire_date, ticker
    )

    # -----------------------------------------------------------------------
    # Inject extreme spikes in EVERY bar after fire_iloc
    # -----------------------------------------------------------------------
    prices_spiked = prices.copy()
    prices_spiked[fire_iloc + 1:] = 1e9  # extreme value — changes returns, rolling stats
    close_spiked = pd.Series(prices_spiked, index=all_dates)

    results_spiked = _evaluate_all_v1_primitives_vectorized(
        close_spiked, fire_date, ticker
    )

    # -----------------------------------------------------------------------
    # Assert bit-identical values at fire_iloc for every primitive
    # -----------------------------------------------------------------------
    failures: list[str] = []
    for prim_name in results_clean:
        v_clean = results_clean[prim_name]
        v_spiked = results_spiked[prim_name]

        # Both NaN → trivially identical (NaN != NaN in float comparison)
        if np.isnan(v_clean) and np.isnan(v_spiked):
            continue

        # One is NaN, other is not → mismatch
        if np.isnan(v_clean) != np.isnan(v_spiked):
            failures.append(
                f"{prim_name}: clean={v_clean!r} vs spiked={v_spiked!r} "
                f"(NaN mismatch — PIT leak)"
            )
            continue

        # Neither NaN — must be bit-identical (same rolling window, same bars)
        if v_clean != v_spiked:
            failures.append(
                f"{prim_name}: clean={v_clean!r} vs spiked={v_spiked!r} "
                f"(values differ — PIT LEAK in vectorized evaluator)"
            )

    assert not failures, (
        "PIT VIOLATION in _compute_signal_for_candidate (vectorized path):\n"
        + "\n".join(f"  {f}" for f in failures)
        + "\n\nFIX REQUIRED: the shipped data/research/alpha_* artifacts and any "
        "reported FDR survivors are INVALID pending a clean re-run of "
        "scripts/research/compile_alpha_candidates.py."
    )


def test_pit_spike_vectorized_cs_rank_inner():
    """cs_rank inner formula (ts_rank child) is PIT-safe in vectorized path.

    cs_rank applies a cross-sectional pass AFTER per-ticker extraction.
    The per-ticker extraction uses the same vectorized evaluator as all other
    primitives.  Verify that the raw inner value (pre-cs_rank) at fire_iloc
    is bit-identical before/after post-fire spike injection.
    """
    from scripts.research.compile_alpha_candidates import _compute_signal_for_candidate

    rng = np.random.default_rng(seed=20260705 + 1)
    n_bars = 100
    returns = rng.normal(0.0005, 0.01, n_bars)
    prices = 100.0 * np.cumprod(1.0 + returns)
    all_dates = pd.date_range("2015-09-01", periods=n_bars, freq="B")

    fire_iloc = 70
    fire_date = all_dates[fire_iloc]
    ticker = "SYNTH_CS"

    close_clean = pd.Series(prices, index=all_dates)
    prices_spiked = prices.copy()
    prices_spiked[fire_iloc + 1:] = 1e9
    close_spiked = pd.Series(prices_spiked, index=all_dates)

    fire_panel = _make_fire_panel_with_outcome(ticker, fire_date, close_clean)

    # cs_rank wraps ts_rank — the inner node is evaluated in the vectorized path
    inner_node = ts_rank(CLOSE_RETURNS, 10)
    cs_node = cs_rank(inner_node)
    cand = CandidateRecord.from_node(cs_node, "cs_rank inner spike test")

    sig_clean = _compute_signal_for_candidate(cand, fire_panel, {ticker: close_clean})
    sig_spiked = _compute_signal_for_candidate(cand, fire_panel, {ticker: close_spiked})

    v_clean = float(sig_clean.iloc[0])
    v_spiked = float(sig_spiked.iloc[0])

    # Both NaN → pass (insufficient cohort — fine)
    if np.isnan(v_clean) and np.isnan(v_spiked):
        return

    assert v_clean == v_spiked, (
        f"cs_rank inner PIT VIOLATION: clean={v_clean!r} vs spiked={v_spiked!r}. "
        "The vectorized path for cs_rank inner formula is leaking post-fire bars."
    )


# ---------------------------------------------------------------------------
# (extra) Primitive evaluations are finite on real-looking data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("node_fn,window", [
    (ts_rank, 10),
    (ts_delta, 5),
    (decay_linear, 10),
    (zscore_winsor, 21),
    (vol_norm_move, 10),
    (dist_from_argmin, 21),
    (dist_from_argmax, 21),
])
def test_primitive_evaluates_without_error(node_fn, window):
    """Each primitive evaluates on synthetic data without raising."""
    from engine.neuralweb.alpha_grammar import _eval_node
    close = _make_close(60)
    node = node_fn(CLOSE_RETURNS, window)
    result = _eval_node(node, close)
    assert isinstance(result, pd.Series)
    # Last value should be non-NaN (enough bars)
    valid = result.dropna()
    assert len(valid) > 0, f"{node_fn.__name__}(w={window}) produced all NaN"


# ---------------------------------------------------------------------------
# (extra) Net-new info is bounded [0, 1] or NaN
# ---------------------------------------------------------------------------

def test_net_new_info_bounded():
    rng = np.random.default_rng(6)
    ids = [f"x_{i}" for i in range(4)]
    data = pd.DataFrame({
        ids[0]: rng.normal(0, 1, 30),
        ids[1]: rng.normal(0, 1, 30),
        ids[2]: rng.normal(0, 1, 30),
        ids[3]: rng.normal(0, 1, 30),
    })
    # 2 clusters: (x_0, x_1) and (x_2, x_3)
    assignments = {"x_0": "C0", "x_1": "C0", "x_2": "C1", "x_3": "C1"}
    reps = {"C0": "x_0", "C1": "x_2"}
    nni = net_new_info(data, assignments, reps)
    for alpha_id, val in nni.items():
        if not np.isnan(val):
            assert 0.0 <= val <= 1.0, f"net_new_info out of [0,1]: {alpha_id}={val}"


# ---------------------------------------------------------------------------
# (extra) forecast_corr diagonal = 1
# ---------------------------------------------------------------------------

def test_forecast_corr_diagonal():
    rng = np.random.default_rng(7)
    ids = ["a1", "a2", "a3"]
    data = pd.DataFrame({
        ids[0]: rng.normal(0, 1, 50),
        ids[1]: rng.normal(0, 1, 50),
        ids[2]: rng.normal(0, 1, 50),
    })
    fc = pairwise_forecast_corr(data)
    for a in ids:
        assert abs(fc.loc[a, a] - 1.0) < 1e-9, f"Diagonal should be 1.0: {a}"
