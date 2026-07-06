"""tests/test_run_rule_replay.py — NW Rails R1 runner governor integration tests.

All tests use synthetic in-memory fixtures only — no Mac-local data required.

Coverage:
  1. GovernorRefusal on unregistered exp_id
  2. GovernorRefusal on spec hash mismatch (registry vs runner grid)
  3. GovernorRefusal propagates from run_experiment() correctly
  4. Lifecycle marks executed → reported after successful run
  5. Summary JSON includes all declared cells (nulls printed, not hidden)
  6. Summary includes cumulative pooled trial count
  7. Episode-cluster count appears per cell
  8. Dry-run returns without writing files
  9. Grid reconstruction produces exactly 15 cells for exit_grid_v1
 10. Spec hash determinism: same spec produces same hash across calls

Run:
    python -m pytest tests/test_run_rule_replay.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.rule_replay import (
    CohortFilter,
    ExitPolicy,
    GovernorRefusal,
    RuleSpec,
    cohort_filter,
    VALID_HOLD_HORIZONS,
    VALID_TRAIL_STOP_PCTS,
)
from engine.rule_experiments import (
    REGISTRY_FAMILY,
    load_experiment,
    pooled_replay_trial_count,
    register_experiment,
    update_experiment_status,
    verify_spec_hashes,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_close(n: int = 250, start_price: float = 100.0, seed: int = 42) -> pd.Series:
    """Deterministic daily close series on a business-day index."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    returns = rng.normal(0.0003, 0.012, n)
    prices = start_price * np.cumprod(1 + returns)
    return pd.Series(prices, index=idx, name="close")


def _make_fires_df(n: int = 10, start_date: str = "2022-06-01") -> pd.DataFrame:
    """Synthetic fire tape with required columns for verdict_grade cohort."""
    dates = pd.bdate_range(start_date, periods=n)
    return pd.DataFrame({
        "ticker": [f"T{i:03d}" for i in range(n)],
        "signal_date": [d.strftime("%Y-%m-%d") for d in dates],
        "year": [d.year for d in dates],
        "episode_id": [f"T{i:03d}_{d.year}-W{d.isocalendar().week:02d}" for i, d in enumerate(dates)],
        "verdict_type": ["fire"] * n,
        "verdict_grade": [True] * n,
        "tier_cascade": (["T1", "T2"] * (n // 2 + 1))[:n],
    })


def _make_simple_cohort() -> CohortFilter:
    return cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )


def _make_simple_spec(cohort: CohortFilter | None = None) -> RuleSpec:
    c = cohort or _make_simple_cohort()
    return RuleSpec(
        spec_id="test/hold_21",
        cohort=c,
        delay_n=1,
        exit=ExitPolicy.hold(21),
        horizons_ref=(126,),
    )


def _register_one_spec(
    registry_path: Path,
    ledger_path: Path,
    exp_id: str = "test_exp_001",
) -> tuple[RuleSpec, dict]:
    """Register a single-spec experiment, return (spec, entry)."""
    spec = _make_simple_spec()
    entry = register_experiment(
        exp_id=exp_id,
        question="Test question: does hold(21) have positive WR on synthetic fires?",
        spec_hashes=[spec.content_hash()],
        declared_budget=1,
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )
    return spec, entry


# ---------------------------------------------------------------------------
# 1. GovernorRefusal on unregistered exp_id
# ---------------------------------------------------------------------------
def test_governor_refuses_unregistered_exp_id(tmp_path: Path) -> None:
    """run_experiment raises GovernorRefusal when exp_id is not in registry."""
    from scripts.run_rule_replay import run_experiment

    registry_path = tmp_path / "registry.jsonl"
    # Don't register anything

    with pytest.raises(GovernorRefusal, match="not found in registry"):
        run_experiment(
            "nonexistent_exp",
            registry_path=registry_path,
            dry_run=False,
        )


# ---------------------------------------------------------------------------
# 2. GovernorRefusal on spec hash mismatch
# ---------------------------------------------------------------------------
def test_governor_refuses_hash_mismatch(tmp_path: Path) -> None:
    """verify_spec_hashes raises GovernorRefusal when runner specs don't match registry."""
    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"

    # Register a spec
    spec_registered, entry = _register_one_spec(registry_path, ledger_path)

    # Build a DIFFERENT spec (different hold horizon)
    different_spec = RuleSpec(
        spec_id="test/hold_63_WRONG",
        cohort=_make_simple_cohort(),
        delay_n=1,
        exit=ExitPolicy.hold(63),  # registered was hold(21)
        horizons_ref=(126,),
    )

    with pytest.raises(GovernorRefusal, match="unregistered hashes"):
        verify_spec_hashes(entry, [different_spec])


# ---------------------------------------------------------------------------
# 3. GovernorRefusal on missing registration propagates from run_experiment
# ---------------------------------------------------------------------------
def test_run_experiment_propagates_governor_refusal(tmp_path: Path) -> None:
    """run_experiment raises GovernorRefusal (not a generic error) on missing exp."""
    from scripts.run_rule_replay import run_experiment

    with pytest.raises(GovernorRefusal):
        run_experiment(
            "exit_grid_v1",  # not registered in tmp registry
            registry_path=tmp_path / "empty.jsonl",
        )


# ---------------------------------------------------------------------------
# 4. Lifecycle marks executed → reported after successful run (synthetic data)
# ---------------------------------------------------------------------------
def test_lifecycle_marks_executed_reported(tmp_path: Path) -> None:
    """After run_experiment, the experiment status is executed then reported."""
    from scripts.run_rule_replay import run_experiment

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    # Build a tiny synthetic boarded parquet
    fires_df = _make_fires_df(n=5, start_date="2022-06-01")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)

    # Build close data for the tickers
    massive_dir = tmp_path / "massive_stock_day"
    massive_dir.mkdir()
    for i in range(5):
        ticker = f"T{i:03d}"
        c = _make_close(n=300, seed=i)
        close_df = pd.DataFrame({"close": c.values}, index=c.index)
        close_df.to_parquet(massive_dir / f"{ticker}.parquet")

    # Register a single-spec experiment
    cohort = _make_simple_cohort()
    spec = RuleSpec(
        spec_id="exit_grid_v1/hold_21",  # must match grid builder
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.hold(21),
        horizons_ref=(126,),
    )

    # We need to register with the EXACT hash the grid builder will produce
    # for the exit_grid_v1 cohort. Build it in a limited way for this test:
    # register only hold_21 and patch the runner's _GRID_BUILDERS temporarily.
    from scripts.run_rule_replay import _GRID_BUILDERS, _build_exit_grid_v1_specs
    import scripts.run_rule_replay as rr_module

    # Build the full exit_grid_v1 grid (15 cells) so hashes match
    full_specs = _build_exit_grid_v1_specs(cohort)
    entry = register_experiment(
        exp_id="exit_grid_v1",
        question="Test lifecycle registration.",
        spec_hashes=[s.content_hash() for s in full_specs],
        declared_budget=len(full_specs),
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )
    assert entry["status"] == "registered"

    # Run with synthetic data and tiny massive_dir
    summary = run_experiment(
        "exit_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    # Check lifecycle was updated
    final_entry = load_experiment("exit_grid_v1", registry_path)
    assert final_entry["status"] == "reported"

    # Check summary was written
    summary_path = results_dir / "exit_grid_v1_summary.json"
    assert summary_path.exists()
    with open(summary_path) as fh:
        loaded = json.load(fh)
    assert loaded["exp_id"] == "exit_grid_v1"


# ---------------------------------------------------------------------------
# 5. Summary includes all declared cells (nulls printed, not hidden)
# ---------------------------------------------------------------------------
def test_summary_includes_all_cells(tmp_path: Path) -> None:
    """Every declared cell appears in summary JSON even if some fire data is missing."""
    from scripts.run_rule_replay import run_experiment

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    fires_df = _make_fires_df(n=3, start_date="2022-06-01")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)

    # NO massive_dir data — all tickers missing, all cells should still appear
    massive_dir = tmp_path / "massive_empty"
    massive_dir.mkdir()

    cohort = _make_simple_cohort()
    from scripts.run_rule_replay import _build_exit_grid_v1_specs
    full_specs = _build_exit_grid_v1_specs(cohort)

    register_experiment(
        exp_id="exit_grid_v1",
        question="Test all-cells coverage.",
        spec_hashes=[s.content_hash() for s in full_specs],
        declared_budget=len(full_specs),
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    summary = run_experiment(
        "exit_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    # All 15 cells must be in the summary
    assert len(summary["cells"]) == 15, (
        f"Expected 15 cells, got {len(summary['cells'])}: {list(summary['cells'].keys())}"
    )
    # Every cell has an n_fires key (even if 0 or censored)
    for cell_id, stats in summary["cells"].items():
        assert "n_fires" in stats, f"Cell {cell_id} missing n_fires"


# ---------------------------------------------------------------------------
# 6. Summary includes cumulative pooled trial count
# ---------------------------------------------------------------------------
def test_summary_includes_pooled_trial_count(tmp_path: Path) -> None:
    """Cumulative pooled replay trial count appears in summary JSON."""
    from scripts.run_rule_replay import run_experiment

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    fires_df = _make_fires_df(n=3, start_date="2022-06-01")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)

    massive_dir = tmp_path / "massive_empty"
    massive_dir.mkdir()

    cohort = _make_simple_cohort()
    from scripts.run_rule_replay import _build_exit_grid_v1_specs
    full_specs = _build_exit_grid_v1_specs(cohort)

    register_experiment(
        exp_id="exit_grid_v1",
        question="Test trial count.",
        spec_hashes=[s.content_hash() for s in full_specs],
        declared_budget=len(full_specs),
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    summary = run_experiment(
        "exit_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    assert "cumulative_pooled_replay_trial_count" in summary
    assert summary["cumulative_pooled_replay_trial_count"] == 15  # only exit_grid_v1


# ---------------------------------------------------------------------------
# 7. Episode-cluster count appears per cell
# ---------------------------------------------------------------------------
def test_episode_cluster_count_per_cell(tmp_path: Path) -> None:
    """Per-cell summary includes episode_clusters count."""
    from scripts.run_rule_replay import run_experiment

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    fires_df = _make_fires_df(n=6, start_date="2022-06-01")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)

    massive_dir = tmp_path / "massive_with_data"
    massive_dir.mkdir()
    for i in range(6):
        ticker = f"T{i:03d}"
        c = _make_close(n=300, seed=i + 10)
        pd.DataFrame({"close": c.values}, index=c.index).to_parquet(
            massive_dir / f"{ticker}.parquet"
        )

    cohort = _make_simple_cohort()
    from scripts.run_rule_replay import _build_exit_grid_v1_specs
    full_specs = _build_exit_grid_v1_specs(cohort)

    register_experiment(
        exp_id="exit_grid_v1",
        question="Test episode cluster count.",
        spec_hashes=[s.content_hash() for s in full_specs],
        declared_budget=len(full_specs),
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    summary = run_experiment(
        "exit_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    # Every cell should have episode_clusters >= 0
    for cell_id, stats in summary["cells"].items():
        assert "episode_clusters" in stats, f"Cell {cell_id} missing episode_clusters"
        assert stats["episode_clusters"] >= 0, f"Cell {cell_id} episode_clusters is negative"


# ---------------------------------------------------------------------------
# 8. Dry-run returns without writing files
# ---------------------------------------------------------------------------
def test_dry_run_no_files(tmp_path: Path) -> None:
    """Dry-run returns without creating any output files."""
    from scripts.run_rule_replay import run_experiment

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    cohort = _make_simple_cohort()
    from scripts.run_rule_replay import _build_exit_grid_v1_specs
    full_specs = _build_exit_grid_v1_specs(cohort)

    register_experiment(
        exp_id="exit_grid_v1",
        question="Dry run test.",
        spec_hashes=[s.content_hash() for s in full_specs],
        declared_budget=len(full_specs),
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    result = run_experiment(
        "exit_grid_v1",
        registry_path=registry_path,
        results_dir=results_dir,
        dry_run=True,
    )

    assert result.get("dry_run") is True
    # No output files should exist
    assert not (results_dir / "exit_grid_v1_summary.json").exists()
    assert not (results_dir / "exit_grid_v1_perfire.parquet").exists()


# ---------------------------------------------------------------------------
# 9. Grid reconstruction produces exactly 15 cells for exit_grid_v1
# ---------------------------------------------------------------------------
def test_exit_grid_v1_15_cells() -> None:
    """_build_exit_grid_v1_specs produces exactly 15 cells."""
    from scripts.run_rule_replay import _build_exit_grid_v1_specs

    cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    specs = _build_exit_grid_v1_specs(cohort)
    assert len(specs) == 15, f"Expected 15 cells, got {len(specs)}"

    # Check kinds
    holds = [s for s in specs if s.exit.kind.name == "HOLD"]
    ema_trails = [s for s in specs if s.exit.kind.name == "EMA_TRAIL"]
    trail_stops = [s for s in specs if s.exit.kind.name == "TRAIL_STOP"]
    barriers = [s for s in specs if s.exit.kind.name == "BARRIER"]

    assert len(holds) == 6, f"Expected 6 hold cells, got {len(holds)}"
    assert len(ema_trails) == 1, f"Expected 1 ema_trail cell, got {len(ema_trails)}"
    assert len(trail_stops) == 4, f"Expected 4 trail_stop cells, got {len(trail_stops)}"
    assert len(barriers) == 4, f"Expected 4 barrier cells, got {len(barriers)}"

    # Check ema_trail parameters
    et = ema_trails[0]
    assert et.exit.ema_span == 8
    assert et.exit.ema_resample == "3B"

    # Check barrier parameters match §4 spec
    barrier_params = {(s.exit.stop_pct, s.exit.target_pct) for s in barriers}
    expected_params = {(-5.0, 8.0), (-5.0, 15.0), (-8.0, 15.0), (-8.0, 25.0)}
    assert barrier_params == expected_params, f"Barrier params mismatch: {barrier_params}"


# ---------------------------------------------------------------------------
# 10. Spec hash determinism
# ---------------------------------------------------------------------------
def test_spec_hash_determinism() -> None:
    """Same spec parameters produce identical hash on repeated construction."""
    cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    spec1 = RuleSpec(
        spec_id="exit_grid_v1/hold_21",
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.hold(21),
        horizons_ref=(126,),
    )
    spec2 = RuleSpec(
        spec_id="exit_grid_v1/hold_21",
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.hold(21),
        horizons_ref=(126,),
    )
    # Spec_id is excluded from hash — two specs with different ids but same params
    # must produce the same hash
    spec3 = RuleSpec(
        spec_id="different_id/hold_21",
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.hold(21),
        horizons_ref=(126,),
    )
    assert spec1.content_hash() == spec2.content_hash()
    assert spec1.content_hash() == spec3.content_hash()

    # Different spec produces different hash
    spec4 = RuleSpec(
        spec_id="exit_grid_v1/hold_42",
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.hold(42),
        horizons_ref=(126,),
    )
    assert spec1.content_hash() != spec4.content_hash()


# ---------------------------------------------------------------------------
# 11. Pooled trial count accumulates correctly
# ---------------------------------------------------------------------------
def test_pooled_trial_count_accumulates(tmp_path: Path) -> None:
    """Registering two experiments accumulates declared budgets in pooled count."""
    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"

    cohort = _make_simple_cohort()
    spec_a = _make_simple_spec(cohort)
    spec_b = RuleSpec(
        spec_id="exp_b/hold_42",
        cohort=cohort,
        delay_n=1,
        exit=ExitPolicy.hold(42),
        horizons_ref=(126,),
    )

    register_experiment(
        exp_id="exp_alpha",
        question="First experiment.",
        spec_hashes=[spec_a.content_hash()],
        declared_budget=1,
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )
    assert pooled_replay_trial_count(registry_path) == 1

    register_experiment(
        exp_id="exp_beta",
        question="Second experiment.",
        spec_hashes=[spec_b.content_hash()],
        declared_budget=1,
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )
    assert pooled_replay_trial_count(registry_path) == 2


# ---------------------------------------------------------------------------
# 12. No adhoc flag on runner (structural check)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# B1 wait_grid_v1 tests (new)
# ---------------------------------------------------------------------------

def test_wait_grid_v1_10_cells() -> None:
    """_build_wait_grid_v1_specs produces exactly 10 cells per §6.1 frozen spec."""
    from scripts.run_rule_replay import _build_wait_grid_v1_specs

    cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    specs = _build_wait_grid_v1_specs(cohort)
    assert len(specs) == 10, f"Expected 10 cells, got {len(specs)}"

    # All cells must be HOLD type
    non_hold = [s for s in specs if s.exit.kind.name != "HOLD"]
    assert len(non_hold) == 0, f"All wait_grid_v1 cells must be HOLD, got {non_hold}"

    # Delay values must match the frozen grid {1, 2, 3, 5, 10}
    delay_values = sorted({s.delay_n for s in specs})
    assert delay_values == [1, 2, 3, 5, 10], f"delay_n values must be {{1,2,3,5,10}}, got {delay_values}"

    # Hold values must match the frozen grid {21, 63}
    hold_values = sorted({s.exit.hold_bars for s in specs})
    assert hold_values == [21, 63], f"hold_bars values must be {{21, 63}}, got {hold_values}"

    # Exactly 5 × 2 = 10 combinations
    combos = {(s.delay_n, s.exit.hold_bars) for s in specs}
    expected_combos = {(d, h) for d in [1, 2, 3, 5, 10] for h in [21, 63]}
    assert combos == expected_combos, f"Combinations mismatch: {combos}"

    # All cells use full weight
    for s in specs:
        assert s.weight == "full", f"Cell {s.spec_id} has weight={s.weight!r}, expected 'full'"

    # All cells reference horizon 126
    for s in specs:
        assert s.horizons_ref == (126,), f"Cell {s.spec_id} horizons_ref={s.horizons_ref}, expected (126,)"


def test_wait_grid_v1_delay1_is_production_fill() -> None:
    """delay_n=1 in wait_grid_v1 equals the production fill used in EXIT-GRID-1 hold(21) and hold(63)."""
    from scripts.run_rule_replay import _build_wait_grid_v1_specs, _build_exit_grid_v1_specs

    cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    wait_specs = _build_wait_grid_v1_specs(cohort)
    exit_specs = _build_exit_grid_v1_specs(cohort)

    # delay_n=1, hold(21) in wait_grid must match exit_grid hold_21 hash
    wait_d1_h21 = next(s for s in wait_specs if s.delay_n == 1 and s.exit.hold_bars == 21)
    exit_h21 = next(s for s in exit_specs if s.exit.hold_bars == 21 and s.exit.kind.name == "HOLD")
    assert wait_d1_h21.content_hash() == exit_h21.content_hash(), (
        "wait_grid_v1/delay1_hold21 must share the same content hash as exit_grid_v1/hold_21 "
        "(same parameters — spec_id is excluded from hash). "
        f"wait_hash={wait_d1_h21.content_hash()[:16]}, exit_hash={exit_h21.content_hash()[:16]}"
    )

    # delay_n=1, hold(63) in wait_grid must match exit_grid hold_63 hash
    wait_d1_h63 = next(s for s in wait_specs if s.delay_n == 1 and s.exit.hold_bars == 63)
    exit_h63 = next(s for s in exit_specs if s.exit.hold_bars == 63 and s.exit.kind.name == "HOLD")
    assert wait_d1_h63.content_hash() == exit_h63.content_hash(), (
        "wait_grid_v1/delay1_hold63 must share the same content hash as exit_grid_v1/hold_63. "
        f"wait_hash={wait_d1_h63.content_hash()[:16]}, exit_hash={exit_h63.content_hash()[:16]}"
    )


def test_wait_grid_v1_hash_determinism() -> None:
    """wait_grid_v1 specs produce the same hashes on repeated construction."""
    from scripts.run_rule_replay import _build_wait_grid_v1_specs

    cohort = cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )
    specs_a = _build_wait_grid_v1_specs(cohort)
    specs_b = _build_wait_grid_v1_specs(cohort)

    hashes_a = sorted(s.content_hash() for s in specs_a)
    hashes_b = sorted(s.content_hash() for s in specs_b)
    assert hashes_a == hashes_b, "Hash set must be identical across repeated calls"

    # Each unique (delay_n, hold_bars) combination must produce a unique hash
    all_hashes = [s.content_hash() for s in specs_a]
    assert len(set(all_hashes)) == 10, (
        f"All 10 cells must have distinct hashes; got {len(set(all_hashes))} unique. "
        f"Duplicates indicate parameter collision."
    )


def test_wait_grid_v1_in_grid_builders() -> None:
    """wait_grid_v1 key must be registered in _GRID_BUILDERS."""
    from scripts.run_rule_replay import _GRID_BUILDERS
    assert "wait_grid_v1" in _GRID_BUILDERS, (
        f"'wait_grid_v1' not in _GRID_BUILDERS. Found: {sorted(_GRID_BUILDERS.keys())}"
    )


def test_wait_grid_v1_run_lifecycle(tmp_path: Path) -> None:
    """wait_grid_v1 grid passes governor verification and produces a 10-cell summary."""
    from scripts.run_rule_replay import run_experiment, _build_wait_grid_v1_specs

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    # Synthetic fire tape
    fires_df = _make_fires_df(n=8, start_date="2022-06-01")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)

    # Close data for each ticker
    massive_dir = tmp_path / "massive_stock_day"
    massive_dir.mkdir()
    for i in range(8):
        ticker = f"T{i:03d}"
        c = _make_close(n=350, seed=i + 20)
        pd.DataFrame({"close": c.values}, index=c.index).to_parquet(
            massive_dir / f"{ticker}.parquet"
        )

    # Register the wait_grid_v1 experiment
    cohort = _make_simple_cohort()
    specs = _build_wait_grid_v1_specs(cohort)
    assert len(specs) == 10

    register_experiment(
        exp_id="wait_grid_v1",
        question="Test wait_grid lifecycle.",
        spec_hashes=[s.content_hash() for s in specs],
        declared_budget=len(specs),
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    summary = run_experiment(
        "wait_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    # Must produce exactly 10 cells
    assert len(summary["cells"]) == 10, (
        f"Expected 10 cells, got {len(summary['cells'])}: {list(summary['cells'].keys())}"
    )
    # Every cell must appear
    for delay_n in [1, 2, 3, 5, 10]:
        for hold_bars in [21, 63]:
            key = f"wait_grid_v1/delay{delay_n}_hold{hold_bars}"
            assert key in summary["cells"], f"Missing cell {key}"

    # Cumulative pooled trial count must be 10 (only this experiment registered)
    assert summary["cumulative_pooled_replay_trial_count"] == 10

    # Lifecycle updated to reported
    from engine.rule_experiments import load_experiment
    entry = load_experiment("wait_grid_v1", registry_path)
    assert entry["status"] == "reported"


def test_no_adhoc_flag_exists() -> None:
    """run_rule_replay.py must not register --adhoc as an argparse argument (house-law RUL-P3)."""
    import scripts.run_rule_replay as rr_module

    # Check the source code doesn't ADD --adhoc as an argument.
    # The docstring may MENTION the prohibition, so we look for the pattern
    # that would actually register it in argparse: add_argument("--adhoc"...
    src_path = Path(rr_module.__file__)
    src = src_path.read_text(encoding="utf-8")
    assert 'add_argument("--adhoc"' not in src and "add_argument('--adhoc'" not in src, (
        "run_rule_replay.py registers '--adhoc' as an argparse argument, "
        "which is a house-law violation (RUL-P3). No adhoc/interactive mode may exist."
    )


# ---------------------------------------------------------------------------
# 13. B1 — wide trailing stop that never triggers is held_to_reference,
#     included in cell mean at the reference-horizon return (not dropped)
# ---------------------------------------------------------------------------
def test_trail_stop_held_to_reference_included_in_mean(tmp_path: Path) -> None:
    """B1 fix: when a trail_stop runs over a FULL max_H window without triggering,
    the fire is marked held_to_reference=True (not censored) and its exit_ret
    equals the reference-horizon return.  _cell_stats must include it in the mean.

    Setup: monotonically rising price path over 200 bars; a 20% trailing stop
    will never trigger on a path that never pulls back 20% from its HWM.
    The fire is placed with >= 126 bars (max_H) remaining, so the full window
    is available.
    """
    from engine.rule_replay import _compute_per_fire, ExitPolicy, ExitKind

    # Build a strictly monotone rising series: +0.1% every bar for 250 bars
    n = 250
    idx = pd.bdate_range("2022-01-03", periods=n)
    prices = 100.0 * np.cumprod(np.ones(n) * 1.001)
    close = pd.Series(prices, index=idx)

    # Fire at bar 10; 240 bars remain (well above max_H=126)
    fill_idx = 10
    policy = ExitPolicy.trail_stop(20)  # 20% trailing stop — wide, never triggers on monotone rise
    result = _compute_per_fire(close, fill_idx, policy, horizons_ref=(126,))

    # On a monotone-rising path the stop never fires → held_to_reference
    assert result["held_to_reference"] is True, (
        "Expected held_to_reference=True on a monotone-rising path with 20% trail stop; "
        f"got held_to_reference={result['held_to_reference']}, censored={result['censored']}"
    )
    assert result["censored"] is False, (
        f"censored must be False for held_to_reference rows; got {result['censored']}"
    )
    assert result["short_path"] is False, (
        f"short_path must be False when full window is available; got {result['short_path']}"
    )
    # exit_ret should be non-None (the reference-horizon return at max_H-1)
    assert result["exit_ret"] is not None, (
        "exit_ret must be set for held_to_reference rows (it is the reference-horizon return)"
    )
    # The return should be positive (monotone rising path)
    assert result["exit_ret"] > 0, (
        f"exit_ret should be positive on a rising path; got {result['exit_ret']}"
    )


def test_trail_stop_held_to_reference_included_in_cell_stats() -> None:
    """B1 fix (cell-level): _cell_stats includes held_to_reference rows in WR/mean.

    Two synthetic fires on the same monotone-rising series:
      Fire A: trail_stop triggers at bar 30 (negative return path, then recovers)
      Fire B: trail_stop never triggers (held_to_reference, positive return)

    With the B1 fix, both rows are included in the mean — WR and mean_exit_ret
    should reflect the average of the two exit returns.
    Without the fix (old code excluded all censored rows, which incorrectly grouped
    held_to_reference with genuine censors), only fire A would be included.
    """
    from scripts.run_rule_replay import _cell_stats

    # Simulate two perfire rows: one triggered, one held_to_reference
    perfire = pd.DataFrame({
        "exit_ret": [0.10, 0.15],       # fire A: +10%; fire B: +15% (held_to_reference)
        "censored": [False, False],
        "short_path": [False, False],
        "held_to_reference": [False, True],
        "ticker": ["A", "B"],
        "fire_date": pd.to_datetime(["2022-06-01", "2022-06-02"]),
    })
    # No fires DataFrame needed for the cluster count path (we rely on ticker+fire_date)
    stats = _cell_stats(perfire, pd.DataFrame())

    # Both rows should be included: WR = 2/2 = 1.0, mean = (0.10+0.15)/2 = 0.125
    assert stats["wr"] == pytest.approx(1.0), (
        f"Expected WR=1.0 (both positive), got {stats['wr']}. "
        "held_to_reference rows must be included in WR computation."
    )
    assert stats["mean_exit_ret"] == pytest.approx(0.125, abs=0.001), (
        f"Expected mean=(0.10+0.15)/2=0.125, got {stats['mean_exit_ret']}. "
        "held_to_reference rows must be included in mean_exit_ret."
    )
    # Both short_path_pct and held_to_reference_pct should be reported
    assert "short_path_pct" in stats
    assert "held_to_reference_pct" in stats
    assert stats["held_to_reference_pct"] == pytest.approx(0.5, abs=0.01)  # 1/2 = 0.5
    assert stats["short_path_pct"] == pytest.approx(0.0)
