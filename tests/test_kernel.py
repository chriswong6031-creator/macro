"""tests/test_kernel.py — Neural Web W3 PR1: reliability kernel estimates.

Hermetic fixtures — no live data reads. All data is constructed in-memory
or written to tmp_path.

Coverage:
  (1) Cell construction from a fixture index — regime bucketing including
      __unstamped__ and __all__ marginals; horizon separation.
  (2) Signed-outcome semantics — direction-aware sign convention.
  (3) Event dedup — n_eff = distinct (symbol, as_of) within a horizon cell.
  (4) Shrinkage wiring — a low-n cell shrinks toward the family mean (numeric
      assertion using pooling constants K_POOL and LAMBDA_SELF).
  (5) Wilson CI lower bound — None below WILSON_MIN_N; computable above it.
  (6) Noise discount applied for fill_basis=='asof_legacy'.
  (7) Idempotent determinism — two builds yield identical DataFrames.
  (8) Sidecar written alongside the parquet.
  (9) REGRESSION: no cell's |shrunken_ic| EXCEEDS |mean_raw| when the
      family mean is 0-adjacent — shrinkage must never AMPLIFY toward zero.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers — build a minimal spine index parquet
# ---------------------------------------------------------------------------

# Canonical columns as declared in engine.neuralweb.query.COLUMNS
# IMPORTANT: This list MUST be kept in sync with Q.COLUMNS.
# The drift-guard test test_spine_query.test_columns_pin_drift_guard() enforces this.
# W1 Spine v2: added is_sizing, is_veto, is_alpha, is_timing, is_context, falsifier, half_life
_SPINE_COLS = [
    "signal_id", "engine", "family", "ledger", "as_of", "symbol",
    "scope_type", "universe", "horizon", "direction", "size_binding",
    "fill_basis", "score",
    "outcome_excess", "outcome_graded", "graded_at",
    "terminal_state_clean15_126", "terminal_state_clean8_21",
    "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63", "fwd_mfe_126",
    "rate_pressure", "quad_hard_label", "fused_risk_label",
    "vol_regime", "risk_radar_state", "vector_asof",
    "species_id", "archetype",
    # W1 Spine v2 role flags + metadata
    "is_sizing", "is_veto", "is_alpha", "is_timing", "is_context",
    "falsifier", "half_life",
    # R5 macro context rail: snapshot stamp + market routing + stamp basis
    "macro_context_id", "macro_context_asof", "market", "own_market_quad",
    "regime_stamp_basis",
    # NW-CI W2 — personality coordinates (R-CI3 provenance)
    "chart_primary", "micro_primary", "personality_basis",
]


def _row(
    *,
    engine: str = "test_engine",
    as_of: str = "2026-01-02",
    symbol: str = "AAA",
    horizon: int = 21,
    direction: int = 1,
    outcome_excess: float = 0.03,
    graded: bool = True,
    quad_hard_label: str | None = "Goldilocks",
    fill_basis: str = "next_bar",
    idx: int = 0,
) -> dict:
    """Build one canonical spine row."""
    return {
        "signal_id": f"test:{as_of}:{symbol}:{horizon}:{idx}",
        "engine": engine,
        "family": f"{engine}:buy",
        "ledger": "spine",
        "as_of": as_of,
        "symbol": symbol,
        "scope_type": "entity",
        "universe": "test",
        "horizon": horizon,
        "direction": direction,
        "size_binding": True,
        "fill_basis": fill_basis,
        "score": 1.0,
        "outcome_excess": outcome_excess if graded else None,
        "outcome_graded": graded,
        "graded_at": f"{as_of}",
        "terminal_state_clean15_126": None,
        "terminal_state_clean8_21": None,
        "fwd_mfe_5": None, "fwd_mfe_10": None, "fwd_mfe_21": None,
        "fwd_mfe_63": None, "fwd_mfe_126": None,
        "rate_pressure": None,
        "quad_hard_label": quad_hard_label,
        "fused_risk_label": None,
        "vol_regime": None,
        "risk_radar_state": None,
        "vector_asof": None,
        "species_id": None,
        "archetype": None,
        # W1 Spine v2 role flags (conservative defaults)
        "is_sizing": True,   # buy row fixture
        "is_veto":   False,
        "is_alpha":  True,   # buy row + direction=1
        "is_timing": False,
        "is_context": False,
        "falsifier": None,
        "half_life": None,
    }


def _write_index(tmp_path: Path, rows: list[dict]) -> Path:
    """Write a spine index parquet to tmp_path/data/neuralweb/."""
    out = tmp_path / "data" / "neuralweb"
    out.mkdir(parents=True, exist_ok=True)
    p = out / "spine_index.parquet"
    df = pd.DataFrame(rows, columns=_SPINE_COLS)
    # Ensure all missing cols are None
    for c in _SPINE_COLS:
        if c not in df.columns:
            df[c] = None
    df.to_parquet(p, index=False)
    return p


# ---------------------------------------------------------------------------
# (1) Cell construction: regime bucketing + marginals + horizon separation
# ---------------------------------------------------------------------------

def test_regime_bucketing_and_marginals(tmp_path):
    """Cells are emitted per regime bucket + __all__ marginal per (engine, horizon)."""
    rows = [
        _row(engine="eng_a", as_of="2026-01-01", symbol="A", horizon=21,
             quad_hard_label="Goldilocks", outcome_excess=0.04),
        _row(engine="eng_a", as_of="2026-01-02", symbol="B", horizon=21,
             quad_hard_label="Stagflation", outcome_excess=0.02),
        _row(engine="eng_a", as_of="2026-01-03", symbol="C", horizon=21,
             quad_hard_label=None, outcome_excess=0.01),  # → __unstamped__
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import (
        build_estimates, MARGINAL_BUCKET, UNSTAMPED_BUCKET,
    )
    df, meta = build_estimates(tmp_path)
    assert not df.empty, "expected non-empty estimates"

    # Extract cells for eng_a / h=21
    cells = df[(df["engine"] == "eng_a") & (df["horizon"] == 21)]
    regimes = set(cells["regime"].tolist())

    # Must include Goldilocks, Stagflation, __unstamped__, and __all__
    assert "Goldilocks" in regimes, f"missing Goldilocks; got {regimes}"
    assert "Stagflation" in regimes, f"missing Stagflation; got {regimes}"
    assert UNSTAMPED_BUCKET in regimes, f"missing {UNSTAMPED_BUCKET}; got {regimes}"
    assert MARGINAL_BUCKET in regimes, f"missing {MARGINAL_BUCKET}; got {regimes}"


def test_horizon_separation(tmp_path):
    """h=5 and h=21 rows land in DIFFERENT cells; each gets its own n_eff."""
    rows = [
        _row(engine="eng_b", as_of="2026-01-01", symbol="X", horizon=5,
             quad_hard_label="Goldilocks", outcome_excess=0.05),
        _row(engine="eng_b", as_of="2026-01-01", symbol="X", horizon=21,
             quad_hard_label="Goldilocks", outcome_excess=0.05),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)

    h5_all = df[(df["engine"] == "eng_b") & (df["horizon"] == 5) &
                (df["regime"] == MARGINAL_BUCKET)]
    h21_all = df[(df["engine"] == "eng_b") & (df["horizon"] == 21) &
                 (df["regime"] == MARGINAL_BUCKET)]

    assert len(h5_all) == 1, "expected one __all__ cell for h=5"
    assert len(h21_all) == 1, "expected one __all__ cell for h=21"
    # Both have n_eff=1 — same symbol+as_of, but different cells
    assert h5_all.iloc[0]["n_eff"] == 1
    assert h21_all.iloc[0]["n_eff"] == 1


# ---------------------------------------------------------------------------
# (2) Signed-outcome semantics
# ---------------------------------------------------------------------------

def test_signed_outcome_short_direction(tmp_path):
    """A SHORT row (direction=-1) with negative outcome_excess earns positive signed outcome."""
    rows = [
        _row(engine="eng_s", as_of="2026-01-01", symbol="S1", horizon=21,
             direction=-1, outcome_excess=-0.05, quad_hard_label=None),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_s") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    # mean_raw should be positive: (-0.05) * sign(-1) = +0.05
    assert cell.iloc[0]["mean_raw"] > 0, (
        f"expected positive mean_raw for short-correct signal; got {cell.iloc[0]['mean_raw']}"
    )


def test_signed_outcome_context_direction(tmp_path):
    """A context row (direction=0) keeps the raw excess sign."""
    rows = [
        _row(engine="eng_ctx", as_of="2026-01-01", symbol="C1", horizon=21,
             direction=0, outcome_excess=-0.02, quad_hard_label=None),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_ctx") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    # direction=0: signed = raw excess = -0.02
    assert cell.iloc[0]["mean_raw"] < 0


# ---------------------------------------------------------------------------
# (3) Event dedup: n_eff = distinct (symbol, as_of) within horizon cell
# ---------------------------------------------------------------------------

def test_event_dedup_same_symbol_as_of(tmp_path):
    """Multiple rows for the same (symbol, as_of, horizon) collapse to n_eff=1."""
    rows = [
        _row(engine="eng_d", as_of="2026-01-01", symbol="D1", horizon=21,
             outcome_excess=0.03, quad_hard_label=None, idx=0),
        _row(engine="eng_d", as_of="2026-01-01", symbol="D1", horizon=21,
             outcome_excess=0.05, quad_hard_label=None, idx=1),  # same event
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_d") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    # n_raw=2, n_eff=1 (deduped)
    assert cell.iloc[0]["n_raw"] == 2
    assert cell.iloc[0]["n_eff"] == 1


def test_event_dedup_different_symbols_not_collapsed(tmp_path):
    """Different symbols on the same date are distinct events → n_eff=2."""
    rows = [
        _row(engine="eng_e", as_of="2026-01-01", symbol="E1", horizon=21,
             outcome_excess=0.03, quad_hard_label=None),
        _row(engine="eng_e", as_of="2026-01-01", symbol="E2", horizon=21,
             outcome_excess=0.04, quad_hard_label=None),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_e") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    assert cell.iloc[0]["n_eff"] == 2


# ---------------------------------------------------------------------------
# (4) Shrinkage wiring: low-n cell shrinks toward family mean
# ---------------------------------------------------------------------------

def test_shrinkage_low_n_shrinks_toward_family_mean(tmp_path):
    """A low-n cell shrinks its edge toward the family mean.

    If the family mean is 0-adjacent (cells cancel), the low-n cell shrinks
    toward zero. We verify: |shrunken_ic| <= |mean_raw| when the pooling
    family mean is near zero (all other cells cancel each other).
    """
    from engine.pooling import K_POOL

    # Create one engine with three horizon cells:
    # h=5: large positive edge (many obs)
    # h=21: large negative edge (many obs) → family mean ≈ 0
    # h=63: one obs, non-trivial raw mean → should shrink toward ~0
    n_large = 30
    rows: list[dict] = []
    for i in range(n_large):
        rows.append(_row(
            engine="eng_shrink",
            as_of=f"2024-{(i % 12) + 1:02d}-01",
            symbol=f"S{i}",
            horizon=5,
            direction=1,
            outcome_excess=0.04,  # consistently positive
            quad_hard_label=None,
            idx=i,
        ))
        rows.append(_row(
            engine="eng_shrink",
            as_of=f"2024-{(i % 12) + 1:02d}-01",
            symbol=f"S{i}",
            horizon=21,
            direction=1,
            outcome_excess=-0.04,  # consistently negative — cancel h5
            quad_hard_label=None,
            idx=i,
        ))
    # One lonely observation at h=63 with a visible raw mean
    rows.append(_row(
        engine="eng_shrink",
        as_of="2026-01-01",
        symbol="LONE",
        horizon=63,
        direction=1,
        outcome_excess=0.10,
        quad_hard_label=None,
    ))
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)

    lone_cell = df[
        (df["engine"] == "eng_shrink") &
        (df["horizon"] == 63) &
        (df["regime"] == MARGINAL_BUCKET)
    ]
    assert len(lone_cell) == 1, "expected one cell for h=63"
    row = lone_cell.iloc[0]

    mean_raw = abs(float(row["mean_raw"]))
    shrunken = abs(float(row["shrunken_ic"]))

    # Shrinkage must not amplify: |shrunken| <= |mean_raw|
    assert shrunken <= mean_raw + 1e-9, (
        f"Shrinkage amplified: |shrunken_ic|={shrunken:.6f} > |mean_raw|={mean_raw:.6f}. "
        "Pooling must shrink toward zero, never amplify."
    )

    # For n_eff=1 (one observation), reliability = 1/(1+K_POOL) < 0.12
    # So shrunken_ic must be significantly below mean_raw
    reliability = 1.0 / (1.0 + K_POOL)
    # rough upper bound: shrunken <= mean_raw * reliability * some_factor
    # (exact formula is more complex due to 2-tier, but much less than mean_raw)
    assert shrunken < mean_raw * 0.9, (
        f"Expected significant shrinkage at n=1: shrunken={shrunken:.4f}, "
        f"mean_raw={mean_raw:.4f}, max_reliability={reliability:.4f}"
    )


# ---------------------------------------------------------------------------
# (5) Wilson CI lower bound: None below WILSON_MIN_N; computable above
# ---------------------------------------------------------------------------

def test_wilson_ci_none_below_min_n(tmp_path):
    """Cells with n_eff < 12 report wilson_ci_low=None (accruing)."""
    rows = [
        _row(engine="eng_ci", as_of="2026-01-01", symbol="W1", horizon=21,
             outcome_excess=0.03, quad_hard_label=None),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET, WILSON_MIN_N
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_ci") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    assert cell.iloc[0]["n_eff"] < WILSON_MIN_N
    assert cell.iloc[0]["wilson_ci_low"] is None or (
        isinstance(cell.iloc[0]["wilson_ci_low"], float) and
        math.isnan(cell.iloc[0]["wilson_ci_low"])
    ), f"Expected None for n_eff < {WILSON_MIN_N}; got {cell.iloc[0]['wilson_ci_low']}"


def test_wilson_ci_computable_above_min_n(tmp_path):
    """Cells with n_eff >= 12 compute a numeric wilson_ci_low."""
    from engine.neuralweb.kernel import WILSON_MIN_N
    n = WILSON_MIN_N + 5  # 17 observations
    rows = [
        _row(engine="eng_ci2", as_of=f"2026-01-{i:02d}", symbol=f"W{i}", horizon=21,
             outcome_excess=0.03, quad_hard_label=None)
        for i in range(1, n + 1)
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_ci2") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    ci = cell.iloc[0]["wilson_ci_low"]
    assert ci is not None, "Expected a numeric wilson_ci_low for n_eff >= WILSON_MIN_N"
    assert isinstance(ci, (int, float)) and not math.isnan(ci), (
        f"Expected finite float wilson_ci_low; got {ci}"
    )


def test_wilson_ci_population_consistency_under_cofire(tmp_path):
    """REGRESSION: Wilson CI hits and n_eff must come from the same deduped population.

    When n_raw > n_eff (same-day co-fires), a pre-dedup hits count can exceed n_eff,
    giving phat > 1 and NaN (sqrt of negative) inside the Wilson formula. This test
    constructs a cell where n_raw=2*n_eff (every event co-fires twice, all positive)
    and asserts: (a) n_eff < n_raw, (b) wilson_ci_low is a finite float <= 1.0,
    (c) hits implied by the CI is consistent with n_eff not n_raw.
    """
    from engine.neuralweb.kernel import WILSON_MIN_N, MARGINAL_BUCKET
    n_events = WILSON_MIN_N + 3  # 15 distinct (symbol, as_of) pairs
    rows: list[dict] = []
    for i in range(1, n_events + 1):
        # Two co-firing rows for every (symbol, as_of): idx=0 and idx=1
        rows.append(_row(
            engine="eng_cofire", as_of=f"2026-01-{i:02d}", symbol=f"CF{i}",
            horizon=21, outcome_excess=0.04, quad_hard_label=None, idx=0,
        ))
        rows.append(_row(
            engine="eng_cofire", as_of=f"2026-01-{i:02d}", symbol=f"CF{i}",
            horizon=21, outcome_excess=0.04, quad_hard_label=None, idx=1,
        ))
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_cofire") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1, "expected one __all__ cell"

    row = cell.iloc[0]
    assert row["n_raw"] == 2 * n_events, f"n_raw should be {2*n_events}; got {row['n_raw']}"
    assert row["n_eff"] == n_events, f"n_eff should be {n_events}; got {row['n_eff']}"

    ci = row["wilson_ci_low"]
    assert ci is not None, "wilson_ci_low must not be None when n_eff >= WILSON_MIN_N"
    assert isinstance(ci, float) and math.isfinite(ci), (
        f"wilson_ci_low must be finite (pre-dedup hits > n_eff yields NaN); got {ci}"
    )
    assert 0.0 <= ci <= 1.0, (
        f"wilson_ci_low must be in [0, 1]; got {ci} — phat > 1 would give negative sqrt"
    )


# ---------------------------------------------------------------------------
# (6) Noise discount for asof_legacy fill_basis
# ---------------------------------------------------------------------------

def test_asof_legacy_discount_applied(tmp_path):
    """asof_legacy rows receive noise=0.5 discount, reducing shrunken_ic vs next_bar.

    We build two single-cell engines with identical raw means; one is all
    asof_legacy, one is all next_bar. The asof_legacy cell must have lower
    |shrunken_ic| (more shrinkage toward zero).
    """
    n = 5
    rows_legacy = [
        _row(engine="eng_legacy", as_of=f"2026-01-{i:02d}", symbol=f"L{i}",
             horizon=21, outcome_excess=0.04, fill_basis="asof_legacy",
             quad_hard_label=None)
        for i in range(1, n + 1)
    ]
    rows_next = [
        _row(engine="eng_next", as_of=f"2026-01-{i:02d}", symbol=f"N{i}",
             horizon=21, outcome_excess=0.04, fill_basis="next_bar",
             quad_hard_label=None)
        for i in range(1, n + 1)
    ]
    _write_index(tmp_path, rows_legacy + rows_next)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)

    legacy_cell = df[
        (df["engine"] == "eng_legacy") & (df["regime"] == MARGINAL_BUCKET)
    ]
    next_cell = df[
        (df["engine"] == "eng_next") & (df["regime"] == MARGINAL_BUCKET)
    ]
    assert len(legacy_cell) == 1 and len(next_cell) == 1

    # asof_legacy cell must be MORE shrunken (smaller |shrunken_ic|) than next_bar
    # because noise discount reduces its reliability
    ic_legacy = abs(float(legacy_cell.iloc[0]["shrunken_ic"]))
    ic_next = abs(float(next_cell.iloc[0]["shrunken_ic"]))
    assert ic_legacy <= ic_next + 1e-9, (
        f"asof_legacy shrunken_ic ({ic_legacy:.6f}) should be <= "
        f"next_bar shrunken_ic ({ic_next:.6f}); noise discount not applied"
    )


# ---------------------------------------------------------------------------
# (7) Idempotent determinism
# ---------------------------------------------------------------------------

def test_build_estimates_deterministic(tmp_path):
    """Two consecutive build_estimates() calls return identical DataFrames."""
    rows = [
        _row(engine="eng_det", as_of=f"2026-01-{i:02d}", symbol=f"D{i}",
             horizon=21, outcome_excess=0.03 + 0.001 * i,
             quad_hard_label="Goldilocks" if i % 2 == 0 else None)
        for i in range(1, 8)
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates
    df1, meta1 = build_estimates(tmp_path)
    df2, meta2 = build_estimates(tmp_path)

    pd.testing.assert_frame_equal(df1, df2, check_exact=False, rtol=1e-9)
    assert meta1["n_cells"] == meta2["n_cells"]
    assert meta1["n_engines"] == meta2["n_engines"]


def test_write_estimates_idempotent(tmp_path):
    """Two consecutive write_estimates() calls yield identical parquet content."""
    rows = [
        _row(engine="eng_idem", as_of=f"2026-01-{i:02d}", symbol=f"I{i}",
             horizon=21, outcome_excess=0.02, quad_hard_label=None)
        for i in range(1, 5)
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import write_estimates
    write_estimates(tmp_path)
    df1 = pd.read_parquet(tmp_path / "data" / "neuralweb" / "kernel_estimates.parquet")
    write_estimates(tmp_path)
    df2 = pd.read_parquet(tmp_path / "data" / "neuralweb" / "kernel_estimates.parquet")

    pd.testing.assert_frame_equal(df1, df2, check_exact=False, rtol=1e-9)


# ---------------------------------------------------------------------------
# (8) Sidecar written alongside the parquet
# ---------------------------------------------------------------------------

def test_sidecar_written(tmp_path):
    """write_estimates() writes both the parquet and its .envelope.json sidecar."""
    rows = [
        _row(engine="eng_sc", as_of="2026-01-01", symbol="SC1", horizon=21,
             outcome_excess=0.03, quad_hard_label=None),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import write_estimates
    write_estimates(tmp_path)

    parquet_path = tmp_path / "data" / "neuralweb" / "kernel_estimates.parquet"
    sidecar_path = Path(str(parquet_path) + ".envelope.json")

    assert parquet_path.exists(), "parquet not written"
    assert sidecar_path.exists(), "envelope sidecar not written"

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert "byte_sha256" in sidecar, "sidecar missing byte_sha256"
    assert "produced_by" in sidecar, "sidecar missing produced_by"
    assert "tier" in sidecar, "sidecar missing tier"


# ---------------------------------------------------------------------------
# (9) REGRESSION: shrinkage must never amplify when global prior dominates
# ---------------------------------------------------------------------------

def test_no_amplification_when_family_mean_zero(tmp_path):
    """When the family (engine) contains ONLY one cell, the family mean equals
    that cell's own shrunken value, and the global prior is zero. Shrinkage
    toward zero can ONLY reduce magnitude — |shrunken_ic| <= |mean_raw|.

    This is the load-bearing variant: a single-cell family has no siblings to
    borrow from, so the two-tier pooled_edges() formula reduces to:
        pooled = lambda * reliability * mean + (1-lambda) * rel_fam * mean
    Both terms multiply mean by factors in [0,1), so |pooled| < |mean|.

    For multi-cell families, borrowing from siblings CAN raise a near-zero
    cell toward the positive family mean — that is the correct pooling behavior
    (the fundamental purpose of the hierarchy). The no-amplification property
    only holds unconditionally for isolate families and for cells with the same
    sign as their family mean.
    """
    # Single-cell engine: no siblings, so family mean = cell's shrunken value,
    # global prior = 0. Pooled output must be strictly between 0 and mean_raw.
    rows = [
        _row(engine="eng_isolate", as_of=f"2026-0{i}-01", symbol=f"I{i}",
             horizon=21, direction=1, outcome_excess=0.05,
             quad_hard_label=None, idx=i)
        for i in range(1, 8)  # 7 obs: n_eff=7, reliability=7/15≈0.47
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)

    cell = df[(df["engine"] == "eng_isolate") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    raw = float(cell.iloc[0]["mean_raw"])
    shrunken = float(cell.iloc[0]["shrunken_ic"])

    # Same sign: both positive
    assert shrunken > 0, "shrunken_ic should be positive (same direction as mean_raw)"
    # Shrinkage toward zero: shrunken < raw
    assert abs(shrunken) < abs(raw) + 1e-9, (
        f"AMPLIFICATION: |shrunken_ic|={abs(shrunken):.6f} > |mean_raw|={abs(raw):.6f}. "
        "A single-cell engine with global prior=0 must shrink toward zero."
    )


def test_no_amplification_wrong_sign_cell(tmp_path):
    """A consistently wrong-sign cell (negative raw mean) must have shrunken_ic
    with the SAME or smaller magnitude than mean_raw when the family mean is
    also negative (siblings also wrong-sign). Global prior = 0 caps the downside.
    """
    # All cells wrong-sign; family mean negative; global prior 0
    # Shrinkage pulls each cell toward 0 (reduces magnitude)
    rows: list[dict] = []
    for h in (5, 21):
        for i in range(1, 8):
            rows.append(_row(
                engine="eng_wrong", as_of=f"2025-{i:02d}-01",
                symbol=f"W{h}_{i}", horizon=h, direction=1,
                outcome_excess=-0.04, quad_hard_label=None, idx=i,
            ))
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)

    cells = df[(df["engine"] == "eng_wrong") & (df["regime"] == MARGINAL_BUCKET)]
    for _, cell in cells.iterrows():
        raw = float(cell["mean_raw"])
        shrunken = float(cell["shrunken_ic"])
        # Both negative; shrunken closer to zero than raw
        assert shrunken < 0, f"h={cell['horizon']}: shrunken_ic should be negative"
        assert abs(shrunken) <= abs(raw) + 1e-9, (
            f"AMPLIFICATION at h={cell['horizon']}: "
            f"|shrunken|={abs(shrunken):.6f} > |raw|={abs(raw):.6f}"
        )


# ---------------------------------------------------------------------------
# (10) AUDIT FIX: __unstamped__ excluded from family pooling at 0% coverage
# ---------------------------------------------------------------------------

def test_unstamped_excluded_from_pooling_at_zero_coverage(tmp_path):
    """At 0% regime coverage, __unstamped__ cells are byte-identical to __all__
    and must NOT enter the pooling family (they'd double-count every horizon in
    the family denominator). The rows are still emitted (display parity) and
    inherit the posterior of their identical __all__ twin.

    Hand-computed check: the kernel's __all__ shrunken_ic must equal
    pooled_edges() over ONLY the de-duplicated (__all__-only) member set —
    and must NOT equal the value from the duplicated 4-member family.
    """
    from engine.pooling import MemberStat, pooled_edges

    # Two horizons, all quad_hard_label=None → coverage 0.0
    rows: list[dict] = []
    for i in range(1, 21):  # h=5: n_eff=20, mean=0.04
        rows.append(_row(engine="eng_z", as_of=f"2025-01-{(i % 28) + 1:02d}",
                         symbol=f"Z5_{i}", horizon=5, outcome_excess=0.04,
                         quad_hard_label=None, idx=i))
    for i in range(1, 11):  # h=21: n_eff=10, mean=0.01
        rows.append(_row(engine="eng_z", as_of=f"2025-02-{(i % 28) + 1:02d}",
                         symbol=f"Z21_{i}", horizon=21, outcome_excess=0.01,
                         quad_hard_label=None, idx=i))
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import (
        build_estimates, MARGINAL_BUCKET, UNSTAMPED_BUCKET,
    )
    df, meta = build_estimates(tmp_path)
    eng = df[df["engine"] == "eng_z"]

    # (a) __unstamped__ rows are still emitted (display parity)
    unstamped = eng[eng["regime"] == UNSTAMPED_BUCKET]
    marginal = eng[eng["regime"] == MARGINAL_BUCKET]
    assert len(unstamped) == 2 and len(marginal) == 2

    # (b) __unstamped__ inherits its identical __all__ twin's posterior
    for h in (5, 21):
        ic_u = float(unstamped[unstamped["horizon"] == h].iloc[0]["shrunken_ic"])
        ic_a = float(marginal[marginal["horizon"] == h].iloc[0]["shrunken_ic"])
        assert abs(ic_u - ic_a) < 1e-12, (
            f"h={h}: __unstamped__ ic {ic_u} != __all__ twin ic {ic_a}"
        )

    # (c) hand-computed: __all__ posterior == pooled_edges over DE-DUPED family
    # (constant outcomes → sample var 0 → kernel floors var at 1e-9)
    dedup_members = [
        MemberStat(key="eng_z:__all__:5", n=20.0, mean=0.04, var=1e-9, noise=0.0),
        MemberStat(key="eng_z:__all__:21", n=10.0, mean=0.01, var=1e-9, noise=0.0),
    ]
    expected = pooled_edges(dedup_members)
    got_h5 = float(marginal[marginal["horizon"] == 5].iloc[0]["shrunken_ic"])
    assert abs(got_h5 - round(expected["eng_z:__all__:5"], 6)) < 1e-9, (
        f"__all__ h=5 posterior {got_h5} != de-duplicated pooled value "
        f"{expected['eng_z:__all__:5']:.6f}"
    )

    # (d) regression guard: the duplicated 4-member family gives a DIFFERENT
    # value (inflated family precision) — the kernel must not reproduce it.
    dup_members = dedup_members + [
        MemberStat(key="eng_z:__unstamped__:5", n=20.0, mean=0.04, var=1e-9, noise=0.0),
        MemberStat(key="eng_z:__unstamped__:21", n=10.0, mean=0.01, var=1e-9, noise=0.0),
    ]
    dup_expected = pooled_edges(dup_members)["eng_z:__all__:5"]
    assert abs(got_h5 - round(dup_expected, 6)) > 1e-9, (
        "kernel __all__ posterior matches the DOUBLE-COUNTED family value — "
        "__unstamped__ duplicates are back in the pooling denominator"
    )


def test_unstamped_is_member_when_coverage_positive(tmp_path):
    """Once real stamps accrue (coverage > 0), __unstamped__ is a genuine
    sub-population and must rejoin the family as its own pooling member
    (posterior computed from its own rows, not copied from __all__)."""
    rows = [
        _row(engine="eng_mix", as_of=f"2025-01-{i:02d}", symbol=f"G{i}",
             horizon=21, outcome_excess=0.05, quad_hard_label="Goldilocks", idx=i)
        for i in range(1, 9)
    ] + [
        _row(engine="eng_mix", as_of=f"2025-02-{i:02d}", symbol=f"U{i}",
             horizon=21, outcome_excess=-0.03, quad_hard_label=None, idx=i)
        for i in range(1, 5)
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import (
        build_estimates, MARGINAL_BUCKET, UNSTAMPED_BUCKET,
    )
    df, meta = build_estimates(tmp_path)
    eng = df[df["engine"] == "eng_mix"]

    cov = float(eng.iloc[0]["regime_coverage"])
    assert abs(cov - 8.0 / 12.0) < 1e-3, f"coverage should be 8/12; got {cov}"

    ic_u = float(eng[eng["regime"] == UNSTAMPED_BUCKET].iloc[0]["shrunken_ic"])
    ic_a = float(eng[eng["regime"] == MARGINAL_BUCKET].iloc[0]["shrunken_ic"])
    # Different populations (negative vs blended) → different posteriors
    assert abs(ic_u - ic_a) > 1e-9, (
        "__unstamped__ posterior equals __all__ despite coverage > 0 — "
        "it is being copied instead of pooled as its own member"
    )
    assert ic_u < ic_a, "wrong-sign __unstamped__ population must sit below the blend"


# ---------------------------------------------------------------------------
# (11) regime_coverage on the family record and per cell
# ---------------------------------------------------------------------------

def test_regime_coverage_family_record_and_cells(tmp_path):
    """regime_coverage = fraction of graded deduped events carrying a
    quad_hard_label; present on both meta.families and every cell."""
    rows = [
        _row(engine="eng_cov", as_of="2026-01-01", symbol="A", horizon=21,
             quad_hard_label="Goldilocks", outcome_excess=0.02),
        _row(engine="eng_cov", as_of="2026-01-02", symbol="B", horizon=21,
             quad_hard_label=None, outcome_excess=0.02),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates
    df, meta = build_estimates(tmp_path)

    fam = meta["families"]["eng_cov"]
    assert "regime_coverage" in fam, "family record missing regime_coverage"
    assert abs(fam["regime_coverage"] - 0.5) < 1e-9

    cells = df[df["engine"] == "eng_cov"]
    assert "regime_coverage" in cells.columns
    assert (abs(cells["regime_coverage"].astype(float) - 0.5) < 1e-9).all()


def test_regime_coverage_zero_when_no_stamps(tmp_path):
    rows = [
        _row(engine="eng_cov0", as_of="2026-01-01", symbol="A", horizon=21,
             quad_hard_label=None, outcome_excess=0.02),
    ]
    _write_index(tmp_path, rows)
    from engine.neuralweb.kernel import build_estimates
    df, meta = build_estimates(tmp_path)
    assert meta["families"]["eng_cov0"]["regime_coverage"] == 0.0


# ---------------------------------------------------------------------------
# (12) shrunken_ic_sd — per-cell posterior sd
# ---------------------------------------------------------------------------

def test_shrunken_ic_sd_hand_computed(tmp_path):
    """At zero noise, shrunken_ic_sd == sqrt(var/(n_eff + K_POOL)) — the
    normal-normal posterior sd matching reliability = n/(n+K)."""
    from engine.pooling import K_POOL

    n = 15
    # Alternate outcomes so sample var is non-degenerate
    rows = [
        _row(engine="eng_sd", as_of=f"2026-01-{i:02d}", symbol=f"S{i}",
             horizon=21, outcome_excess=(0.02 if i % 2 == 0 else 0.06),
             quad_hard_label="Goldilocks", idx=i)
        for i in range(1, n + 1)
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    cell = df[(df["engine"] == "eng_sd") & (df["regime"] == MARGINAL_BUCKET)]
    assert len(cell) == 1
    sd = cell.iloc[0]["shrunken_ic_sd"]
    assert sd is not None and isinstance(sd, float) and math.isfinite(sd)
    assert sd > 0

    # Hand-computed: sample var (ddof=1) of the signed outcomes / (n + K_POOL)
    vals = pd.Series([0.02 if i % 2 == 0 else 0.06 for i in range(1, n + 1)])
    var_raw = float(vals.var())
    expected = math.sqrt(var_raw / n * (1.0 - n / (n + K_POOL)))
    assert abs(sd - round(expected, 6)) < 1e-9, (
        f"shrunken_ic_sd {sd} != hand-computed {expected:.6f} "
        f"(= sqrt(var/(n+K)) at zero noise)"
    )


def test_shrunken_ic_sd_shrinks_with_n(tmp_path):
    """More events → tighter posterior band (same outcome dispersion)."""
    def _mk(engine: str, n: int) -> list[dict]:
        return [
            _row(engine=engine, as_of=f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                 symbol=f"{engine}_{i}", horizon=21,
                 outcome_excess=(0.02 if i % 2 == 0 else 0.06),
                 quad_hard_label=None, idx=i)
            for i in range(1, n + 1)
        ]
    _write_index(tmp_path, _mk("eng_small", 4) + _mk("eng_big", 40))

    from engine.neuralweb.kernel import build_estimates, MARGINAL_BUCKET
    df, _ = build_estimates(tmp_path)
    sd_small = float(df[(df["engine"] == "eng_small") &
                        (df["regime"] == MARGINAL_BUCKET)].iloc[0]["shrunken_ic_sd"])
    sd_big = float(df[(df["engine"] == "eng_big") &
                      (df["regime"] == MARGINAL_BUCKET)].iloc[0]["shrunken_ic_sd"])
    assert sd_big < sd_small, (
        f"posterior sd must tighten with n: n=40 sd {sd_big} !< n=4 sd {sd_small}"
    )


def test_empty_index_parquet_schema_includes_new_columns(tmp_path):
    """The empty-but-schema-valid parquet must carry the new columns."""
    _write_index(tmp_path, [])  # empty spine

    from engine.neuralweb.kernel import write_estimates
    write_estimates(tmp_path)
    out = pd.read_parquet(tmp_path / "data" / "neuralweb" / "kernel_estimates.parquet")
    for col in ("shrunken_ic_sd", "armed_reason", "regime_coverage"):
        assert col in out.columns, f"empty-schema parquet missing {col!r}"


# ---------------------------------------------------------------------------
# (13) armed_reason persisted to the parquet (reason-drop fix)
# ---------------------------------------------------------------------------

def test_armed_reason_persisted_to_cells(tmp_path):
    """pooling.arming()'s explicit reason must survive to the parquet cells
    (previously only the bool did, so the reason never reached any artifact)."""
    rows = [
        _row(engine="eng_ar", as_of="2026-01-01", symbol="A", horizon=21,
             outcome_excess=0.02, quad_hard_label=None),
    ]
    _write_index(tmp_path, rows)

    from engine.neuralweb.kernel import build_estimates
    df, meta = build_estimates(tmp_path)
    cells = df[df["engine"] == "eng_ar"]
    assert "armed_reason" in cells.columns
    reasons = cells["armed_reason"].dropna().astype(str)
    assert not reasons.empty, "armed_reason missing from cells"
    assert (reasons.str.strip() != "").all(), "armed_reason must never be empty"
    # Must match the family record's reason (n=1 → accruing)
    assert reasons.iloc[0] == meta["families"]["eng_ar"]["reason"]
