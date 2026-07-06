"""tests/test_trim_grid_v1.py — Unit tests for TRIM-GRID-1 (PR-F3.3, RUL-F3.5).

Coverage:
  1. ScaledPolicy construction validation — fractions sum, frozen-legs-only
  2. profit_take only valid inside scaled (not as standalone ExitPolicy)
  3. Weighted aggregation including held-to-reference legs
     (synthetic fixture where naive drop-never-triggered gives wrong sign — EXIT-GRID-1 bug regression)
  4. content_hash determinism for ScaledPolicy
  5. mfe15 touch semantics — close basis, first touch
  6. trim_grid_v1 grid builder: exactly 6 cells, correct fractions and legs
  7. ScaledPolicy RuleSpec hash stability
  8. trim_grid_v1 end-to-end run with synthetic data (registry + governor)
  9. TrialLedger pooled SUM and max()-basis both printed in summary
 10. held-to-reference leg included at reference return (EXIT-GRID-1 bug regression test)

Run:
    python -m pytest tests/test_trim_grid_v1.py -x -q
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
    ExitKind,
    GovernorRefusal,
    RuleSpec,
    ScaledPolicy,
    cohort_filter,
    _compute_per_fire,
    _compute_per_fire_scaled,
)
from engine.rule_experiments import (
    register_experiment,
    pooled_replay_trial_count,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_close(n: int = 300, start_price: float = 100.0, seed: int = 42) -> pd.Series:
    """Deterministic daily close series on a business-day index."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-10-01", periods=n)
    returns = rng.normal(0.0003, 0.012, n)
    prices = start_price * np.cumprod(1 + returns)
    return pd.Series(prices, index=idx, name="close")


def _make_fires_df(n: int = 6, start_date: str = "2022-01-03") -> pd.DataFrame:
    """Synthetic fire tape with verdict_grade=True and 2021+ dates."""
    dates = pd.bdate_range(start_date, periods=n)
    return pd.DataFrame({
        "ticker": [f"T{i:03d}" for i in range(n)],
        "signal_date": [d.strftime("%Y-%m-%d") for d in dates],
        "year": [d.year for d in dates],
        "episode_id": [
            f"T{i:03d}_{d.year}-W{d.isocalendar().week:02d}"
            for i, d in enumerate(dates)
        ],
        "verdict_type": ["fire"] * n,
        "verdict_grade": [True] * n,
        "tier_cascade": (["T1", "T2"] * (n // 2 + 1))[:n],
    })


def _simple_cohort() -> CohortFilter:
    return cohort_filter(
        ("eq", "verdict_type", "fire"),
        ("eq", "verdict_grade", True),
    )


# ---------------------------------------------------------------------------
# 1. ScaledPolicy construction validation
# ---------------------------------------------------------------------------

def test_scaled_fractions_must_sum_to_one() -> None:
    """ScaledPolicy raises ValueError when fractions do not sum to 1.0."""
    with pytest.raises(ValueError, match="sum to 1.0"):
        ScaledPolicy.scaled([
            (0.5, ExitPolicy.hold(21)),
            (0.3, ExitPolicy.hold(126)),  # 0.5 + 0.3 = 0.8 ≠ 1.0
        ])


def test_scaled_fractions_must_be_positive() -> None:
    """ScaledPolicy raises ValueError when a fraction is zero or negative."""
    with pytest.raises(ValueError, match="fraction must be > 0"):
        ScaledPolicy.scaled([
            (0.0, ExitPolicy.hold(21)),
            (1.0, ExitPolicy.hold(126)),
        ])


def test_scaled_requires_at_least_two_legs() -> None:
    """ScaledPolicy requires at least 2 legs."""
    with pytest.raises(ValueError, match="at least 2 legs"):
        ScaledPolicy.scaled([
            (1.0, ExitPolicy.hold(21)),
        ])


def test_scaled_rejects_nested_scaled_kind() -> None:
    """ScaledPolicy rejects a leg with SCALED kind (no nesting)."""
    # Cannot pass a ScaledPolicy as a leg (it's not an ExitPolicy)
    # but test that SCALED ExitKind is blocked
    fake_scaled_ep = ExitPolicy(kind=ExitKind.SCALED)
    with pytest.raises(ValueError, match="not in the frozen v1 vocabulary"):
        ScaledPolicy.scaled([
            (0.5, fake_scaled_ep),
            (0.5, ExitPolicy.hold(126)),
        ])


def test_scaled_allows_profit_take_as_leg() -> None:
    """profit_take is a valid leg inside ScaledPolicy."""
    sp = ScaledPolicy.scaled([
        (0.5, ExitPolicy.profit_take(15.0)),
        (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
    ])
    assert len(sp.legs) == 2
    frac0, leg0 = sp.legs[0]
    assert abs(frac0 - 0.5) < 1e-9
    assert leg0.kind == ExitKind.PROFIT_TAKE
    assert leg0.target_pct == 15.0


def test_scaled_valid_three_legs() -> None:
    """ScaledPolicy accepts a three-leg policy with fractions summing to 1."""
    sp = ScaledPolicy.scaled([
        (1/3, ExitPolicy.hold(21)),
        (1/3, ExitPolicy.hold(63)),
        (1/3, ExitPolicy.hold(126)),
    ])
    assert len(sp.legs) == 3
    total = sum(f for f, _ in sp.legs)
    assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 2. profit_take is NOT valid as a standalone ExitPolicy in RuleSpec
# ---------------------------------------------------------------------------

def test_profit_take_rejected_as_standalone_policy() -> None:
    """RuleSpec raises ValueError when a bare profit_take ExitPolicy is used."""
    with pytest.raises(ValueError, match="profit_take is only valid as a leg inside a ScaledPolicy"):
        RuleSpec(
            spec_id="invalid/profit_take_standalone",
            cohort=_simple_cohort(),
            delay_n=1,
            exit=ExitPolicy.profit_take(15.0),
            horizons_ref=(126,),
        )


def test_profit_take_pct_must_be_positive() -> None:
    """profit_take raises ValueError for non-positive pct."""
    with pytest.raises(ValueError, match="must be positive"):
        ExitPolicy.profit_take(-5.0)
    with pytest.raises(ValueError, match="must be positive"):
        ExitPolicy.profit_take(0.0)


# ---------------------------------------------------------------------------
# 3. Weighted aggregation including held-to-reference legs
#    (EXIT-GRID-1 bug regression test)
# ---------------------------------------------------------------------------

def _make_flat_close_then_big_gain(n_flat: int = 50, gain_at: int = 60, n_total: int = 200) -> pd.Series:
    """Close series: flat for n_flat bars, then jumps +20%, stays flat.
    Hold(21) exits at +0% (flat), hold(126) exits at +20% (the gain).
    A naive implementation that drops the hold(126) leg if 'never triggered' (always False
    for a hold policy) would give wrong results — this validates the weighted sum.
    """
    idx = pd.bdate_range("2021-10-01", periods=n_total)
    prices = np.ones(n_total) * 100.0
    prices[gain_at:] = 120.0  # +20% gain at bar gain_at
    return pd.Series(prices, index=idx, name="close")


def test_weighted_aggregation_no_drop_of_held_to_reference() -> None:
    """Weighted aggregation INCLUDES held-to-reference legs at reference return.

    Fixture: a close series where hold(21) exits flat (~0%) and hold(126) exits at +20%.
    A 50/50 ScaledPolicy should return ~+10% (weighted average).

    The EXIT-GRID-1 bug was dropping legs where 'held_to_reference=True' from the
    aggregation, which for trail_stop/barrier policies would invert the sign.
    For hold policies held_to_reference is never set, but the same logic must hold
    for scaled policies with mix of legs.
    """
    close = _make_flat_close_then_big_gain(n_flat=50, gain_at=60, n_total=200)
    fill_idx = 0  # enter at the first bar

    scaled = ScaledPolicy.scaled([
        (0.5, ExitPolicy.hold(21)),
        (0.5, ExitPolicy.hold(126)),
    ])
    result = _compute_per_fire_scaled(close, fill_idx, scaled, horizons_ref=(126,))

    assert not result["censored"], f"Should not be censored; got: {result}"
    # Hold(21) exits at bar 21: price is still ~100 (flat region) → return ~0%
    # Hold(126) exits at bar 126: price is 120 (gain region) → return ~+20%
    # Weighted: 0.5 * 0% + 0.5 * 20% = ~10%
    assert result["exit_ret"] is not None
    assert result["exit_ret"] > 0.05, (
        f"Expected weighted return ~10%, got {result['exit_ret']:.4f}. "
        "If this fails, a leg may have been dropped from the weighted average."
    )
    assert result["exit_ret"] < 0.18, (
        f"Weighted return should not equal hold(126) alone (~20%), got {result['exit_ret']:.4f}. "
        "If this fails, the 50/50 split may not be applied correctly."
    )


def test_held_to_reference_trail_stop_included() -> None:
    """A trail_stop leg that never triggers is held_to_reference and INCLUDED at reference return.

    Fixture: price moves monotonically upward — trail_stop(8) never fires.
    50% hold(21) + 50% trail_stop(8):
        - hold(21) exits at +small gain
        - trail_stop(8) never fires → held_to_reference → included at reference return (large gain)
    If trail_stop were DROPPED (the EXIT-GRID-1 bug), the weighted return would be only
    the hold(21) return (~small gain). With correct inclusion it should be ~halfway.

    This is the exact regression test for the EXIT-GRID-1 aggregation bug.
    """
    # Monotonically rising close: trail_stop(8%) will never fire
    n = 200
    idx = pd.bdate_range("2021-10-01", periods=n)
    # 0.2% gain per day — strongly rising, trail_stop(8%) never fires
    prices = 100.0 * (1.002 ** np.arange(n))
    close = pd.Series(prices, index=idx, name="close")
    fill_idx = 0

    scaled = ScaledPolicy.scaled([
        (0.5, ExitPolicy.hold(21)),
        (0.5, ExitPolicy.trail_stop(8.0)),
    ])
    result = _compute_per_fire_scaled(close, fill_idx, scaled, horizons_ref=(126,))

    assert not result["censored"], f"Should not be censored; got: {result}"
    assert result["exit_ret"] is not None

    # hold(21) alone exits at bar 21: return = (100 * 1.002^21) / 100 - 1 ≈ +4.4%
    hold21_ret = (1.002 ** 21) - 1.0

    # hold(126) alone (the reference): return = (100 * 1.002^126) / 100 - 1 ≈ +28.5%
    hold126_ret = (1.002 ** 126) - 1.0

    # trail_stop(8) never fires → held_to_reference at reference return (= hold_126 return)
    # Weighted: 0.5 * hold21_ret + 0.5 * hold126_ret ≈ 0.5 * 4.4% + 0.5 * 28.5% ≈ 16.4%
    expected_weighted = 0.5 * hold21_ret + 0.5 * hold126_ret

    # If the bug were present (trail_stop leg dropped): result would be just hold21_ret
    # So we check that result is NOT near hold21_ret alone
    bug_present_result = hold21_ret  # this is what the buggy implementation would return

    assert abs(result["exit_ret"] - expected_weighted) < 0.02, (
        f"Weighted return {result['exit_ret']:.4f} should be near {expected_weighted:.4f} "
        f"(50% hold21={hold21_ret:.4f} + 50% held-to-reference={hold126_ret:.4f}). "
        f"Bug-present value would be {bug_present_result:.4f}."
    )
    # Explicit anti-bug assertion: must NOT be close to hold(21) alone
    assert abs(result["exit_ret"] - bug_present_result) > 0.05, (
        f"EXIT-GRID-1 bug regression: weighted return {result['exit_ret']:.4f} is too close "
        f"to hold(21)-alone {bug_present_result:.4f}. The trail_stop leg is likely being "
        "dropped instead of included at reference return."
    )


# ---------------------------------------------------------------------------
# 4. ScaledPolicy content_hash determinism
# ---------------------------------------------------------------------------

def test_scaled_policy_content_hash_determinism() -> None:
    """Same ScaledPolicy legs produce identical hash on repeated construction."""
    sp1 = ScaledPolicy.scaled([
        (0.5, ExitPolicy.hold(21)),
        (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
    ])
    sp2 = ScaledPolicy.scaled([
        (0.5, ExitPolicy.hold(21)),
        (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
    ])
    assert sp1.content_hash() == sp2.content_hash()


def test_scaled_policy_hash_differs_by_fraction() -> None:
    """Different fractions produce different hashes."""
    sp1 = ScaledPolicy.scaled([
        (0.5, ExitPolicy.hold(21)),
        (0.5, ExitPolicy.hold(126)),
    ])
    sp2 = ScaledPolicy.scaled([
        (0.25, ExitPolicy.hold(21)),
        (0.75, ExitPolicy.hold(126)),
    ])
    assert sp1.content_hash() != sp2.content_hash()


def test_rulspec_with_scaled_hash_determinism() -> None:
    """RuleSpec wrapping a ScaledPolicy produces stable content_hash."""
    cohort = _simple_cohort()
    spec1 = RuleSpec(
        spec_id="trim_grid_v1/trim50_h21_ema8",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.hold(21)),
            (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
        ]),
        horizons_ref=(126,),
    )
    spec2 = RuleSpec(
        spec_id="trim_grid_v1/trim50_h21_ema8",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.hold(21)),
            (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
        ]),
        horizons_ref=(126,),
    )
    assert spec1.content_hash() == spec2.content_hash()

    # Spec_id is excluded from hash — different id, same parameters → same hash
    spec3 = RuleSpec(
        spec_id="different_name/trim50_h21_ema8",
        cohort=cohort,
        delay_n=1,
        exit=ScaledPolicy.scaled([
            (0.5, ExitPolicy.hold(21)),
            (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
        ]),
        horizons_ref=(126,),
    )
    assert spec1.content_hash() == spec3.content_hash()


# ---------------------------------------------------------------------------
# 5. mfe15 profit_take touch semantics (close basis, first touch)
# ---------------------------------------------------------------------------

def test_profit_take_first_touch_on_close() -> None:
    """profit_take(15) exits at the first close >= +15% from entry.

    Close basis: exact threshold at 115% triggers exit on that bar (not next bar).
    """
    # Price: 100 for 10 bars, then 116 for remaining bars
    n = 200
    idx = pd.bdate_range("2021-10-01", periods=n)
    prices = np.ones(n) * 100.0
    prices[10:] = 116.0  # +16% at bar 10 — above +15% threshold
    close = pd.Series(prices, index=idx, name="close")
    fill_idx = 0

    pt_policy = ExitPolicy.profit_take(15.0)
    result = _compute_per_fire(close, fill_idx, pt_policy, horizons_ref=(126,))

    assert not result["censored"], "Should not be censored"
    assert result["exit_ret"] is not None
    # Expected: exit at bar 10 (first bar where price >= 115)
    # exit_bar_offset is 1-indexed: bar 10 in fwd_slice → offset 10
    assert result["exit_bar_offset"] == 10, (
        f"Expected exit at bar offset 10 (first touch), got {result['exit_bar_offset']}"
    )
    # Return = 116/100 - 1 = 0.16
    assert abs(result["exit_ret"] - 0.16) < 0.001


def test_profit_take_never_touched_held_to_reference() -> None:
    """profit_take(15) that never touches target holds to reference (not dropped).

    This verifies the EXIT-GRID-1 bug-class prevention for profit_take legs:
    never-touched = held_to_reference = included at reference return.
    """
    # Price: always exactly 100 (no gain) → profit_take(15) never fires
    n = 200
    idx = pd.bdate_range("2021-10-01", periods=n)
    prices = np.ones(n) * 100.0
    close = pd.Series(prices, index=idx, name="close")
    fill_idx = 0

    pt_policy = ExitPolicy.profit_take(15.0)
    result = _compute_per_fire(close, fill_idx, pt_policy, horizons_ref=(126,))

    assert not result["censored"], "Should not be censored (full window available)"
    assert not result.get("short_path", False), "Should not be short_path"
    assert result.get("held_to_reference", False), (
        "profit_take that never fires should be held_to_reference=True"
    )
    # exit_ret should be the reference-horizon return (100/100 - 1 = 0)
    assert result["exit_ret"] is not None
    assert abs(result["exit_ret"]) < 0.001, (
        f"Expected held-to-reference return ~0 (flat price), got {result['exit_ret']}"
    )


def test_profit_take_exact_threshold_triggers() -> None:
    """profit_take(15) triggers exactly at the 15% threshold (>=, not >)."""
    n = 200
    idx = pd.bdate_range("2021-10-01", periods=n)
    prices = np.ones(n) * 100.0
    prices[20:] = 115.0  # exactly +15% at bar 20
    close = pd.Series(prices, index=idx, name="close")
    fill_idx = 0

    pt_policy = ExitPolicy.profit_take(15.0)
    result = _compute_per_fire(close, fill_idx, pt_policy, horizons_ref=(126,))

    assert not result.get("held_to_reference", False), (
        "Should NOT be held_to_reference — exact threshold should trigger"
    )
    assert result["exit_bar_offset"] == 20
    assert abs(result["exit_ret"] - 0.15) < 0.001


# ---------------------------------------------------------------------------
# 6. trim_grid_v1 grid builder: exactly 6 cells, correct fractions
# ---------------------------------------------------------------------------

def test_trim_grid_v1_6_cells() -> None:
    """_build_trim_grid_v1_specs produces exactly 6 cells."""
    from scripts.run_rule_replay import _build_trim_grid_v1_specs
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)
    assert len(specs) == 6, f"Expected 6 cells, got {len(specs)}"


def test_trim_grid_v1_cell_names() -> None:
    """Each frozen cell has the expected spec_id."""
    from scripts.run_rule_replay import _build_trim_grid_v1_specs
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)
    expected_ids = {
        "trim_grid_v1/trim50_h21_ema8",
        "trim_grid_v1/trim50_h21_h126",
        "trim_grid_v1/trim25_h21_ema8",
        "trim_grid_v1/trim33_h21_h63_h126",
        "trim_grid_v1/trim50_ema8_h126",
        "trim_grid_v1/trim50_mfe15_ema8",
    }
    actual_ids = {s.spec_id for s in specs}
    assert actual_ids == expected_ids, (
        f"Spec IDs mismatch.\nExpected: {sorted(expected_ids)}\nActual: {sorted(actual_ids)}"
    )


def test_trim_grid_v1_all_scaled_exits() -> None:
    """All 6 trim_grid_v1 specs use ScaledPolicy exits."""
    from scripts.run_rule_replay import _build_trim_grid_v1_specs
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)
    for spec in specs:
        assert isinstance(spec.exit, ScaledPolicy), (
            f"Expected ScaledPolicy for {spec.spec_id}, got {type(spec.exit)}"
        )


def test_trim50_h21_ema8_fractions() -> None:
    """trim50_h21_ema8 has 0.5/0.5 hold(21)/ema_trail_s8."""
    from scripts.run_rule_replay import _build_trim_grid_v1_specs
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)
    spec = next(s for s in specs if "trim50_h21_ema8" in s.spec_id)
    assert isinstance(spec.exit, ScaledPolicy)
    fracs = [f for f, _ in spec.exit.legs]
    legs = [p for _, p in spec.exit.legs]
    assert abs(fracs[0] - 0.5) < 1e-9
    assert abs(fracs[1] - 0.5) < 1e-9
    assert legs[0].kind == ExitKind.HOLD and legs[0].hold_bars == 21
    assert legs[1].kind == ExitKind.EMA_TRAIL


def test_trim33_h21_h63_h126_fractions() -> None:
    """trim33_h21_h63_h126 has three equal thirds."""
    from scripts.run_rule_replay import _build_trim_grid_v1_specs
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)
    spec = next(s for s in specs if "trim33_h21_h63_h126" in s.spec_id)
    assert isinstance(spec.exit, ScaledPolicy)
    assert len(spec.exit.legs) == 3
    for frac, _ in spec.exit.legs:
        assert abs(frac - 1.0 / 3.0) < 1e-9


def test_trim50_mfe15_ema8_contains_profit_take() -> None:
    """trim50_mfe15_ema8 has profit_take(15) as first leg."""
    from scripts.run_rule_replay import _build_trim_grid_v1_specs
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)
    spec = next(s for s in specs if "trim50_mfe15_ema8" in s.spec_id)
    assert isinstance(spec.exit, ScaledPolicy)
    frac0, leg0 = spec.exit.legs[0]
    assert abs(frac0 - 0.5) < 1e-9
    assert leg0.kind == ExitKind.PROFIT_TAKE
    assert leg0.target_pct == 15.0
    frac1, leg1 = spec.exit.legs[1]
    assert abs(frac1 - 0.5) < 1e-9
    assert leg1.kind == ExitKind.EMA_TRAIL


# ---------------------------------------------------------------------------
# 7. Trim_grid_v1 end-to-end run with synthetic data
# ---------------------------------------------------------------------------

def test_trim_grid_v1_e2e_run(tmp_path: Path) -> None:
    """Full run_experiment for trim_grid_v1 with synthetic data.

    Checks: 6 cells in summary, cumulative pooled trial count printed,
    TrialLedger max()-basis noted.
    """
    from scripts.run_rule_replay import run_experiment, _build_trim_grid_v1_specs

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    n_fires = 8
    fires_df = _make_fires_df(n=n_fires, start_date="2022-01-03")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)

    # Build close data for all tickers
    massive_dir = tmp_path / "massive_stock_day"
    massive_dir.mkdir()
    for i in range(n_fires):
        ticker = f"T{i:03d}"
        c = _make_close(n=300, seed=i + 100)
        pd.DataFrame({"close": c.values}, index=c.index).to_parquet(
            massive_dir / f"{ticker}.parquet"
        )

    # Register trim_grid_v1
    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)

    register_experiment(
        exp_id="trim_grid_v1",
        question=(
            "TRIM-GRID-1: On the production fire cohort (exit_grid_v1 cohort), "
            "do partial-trim policies preserve more right-tail return than all-or-nothing exits?"
        ),
        spec_hashes=[s.content_hash() for s in specs],
        declared_budget=len(specs),
        verdict_criteria="descriptive-only",
        derived_from_surface="exit_grid_v1",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    summary = run_experiment(
        "trim_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    # 6 cells in summary
    assert len(summary["cells"]) == 6, (
        f"Expected 6 cells, got {len(summary['cells'])}: {list(summary['cells'].keys())}"
    )

    # Every cell has n_fires key
    for cell_id, stats in summary["cells"].items():
        assert "n_fires" in stats, f"Cell {cell_id} missing n_fires"

    # Cumulative pooled trial count printed
    assert "cumulative_pooled_replay_trial_count" in summary
    assert summary["cumulative_pooled_replay_trial_count"] == 6  # only trim_grid_v1 registered

    # trim_grid_v1_meta block present with contamination note
    assert "trim_grid_v1_meta" in summary
    meta = summary["trim_grid_v1_meta"]
    assert meta["derived_from_surface"] == "exit_grid_v1"
    assert "contamination_note" in meta
    assert "descriptive-only" in meta["verdict_criteria"]

    # TrialLedger max()-basis note present
    assert "trial_ledger_max_basis" in meta
    assert "trial_ledger_max_basis_note" in meta

    # Summary JSON written to disk
    summary_path = results_dir / "trim_grid_v1_summary.json"
    assert summary_path.exists()
    with open(summary_path) as fh:
        loaded = json.load(fh)
    assert loaded["exp_id"] == "trim_grid_v1"
    assert loaded["derived_from_surface"] == "exit_grid_v1"
    # "validated" must never appear in the summary JSON (house law)
    summary_text = json.dumps(loaded)
    assert "validated" not in summary_text.lower(), (
        "House law violation: 'validated' found in summary JSON. "
        "Use descriptive language only."
    )


# ---------------------------------------------------------------------------
# 9. TrialLedger pooled SUM and max()-basis both printed in summary
# ---------------------------------------------------------------------------

def test_pooled_sum_and_max_basis_printed(tmp_path: Path) -> None:
    """Summary includes both cumulative pooled SUM and a max()-basis note.

    Per RUL-5: both the pooled SUM (15+10+6+6=37 in the real run) and
    the TrialLedger max()-basis (15, largest single declared budget) must
    be printed. The max()-basis comes from the trim_grid_v1_meta block.
    """
    from scripts.run_rule_replay import run_experiment, _build_trim_grid_v1_specs

    registry_path = tmp_path / "registry.jsonl"
    ledger_path = tmp_path / "ledger.jsonl"
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    fires_df = _make_fires_df(n=3, start_date="2022-01-03")
    boarded_path = tmp_path / "replay_boarded.parquet"
    fires_df.to_parquet(boarded_path, index=False)
    massive_dir = tmp_path / "massive_empty"
    massive_dir.mkdir()

    cohort = _simple_cohort()
    specs = _build_trim_grid_v1_specs(cohort)

    # Register a prior experiment to simulate the exit_grid_v1 pooled count
    # (the max-basis test needs declared_budget > 6)
    from engine.rule_experiments import register_experiment as _reg
    _reg(
        exp_id="exit_grid_v1",
        question="Prior experiment — 15 cells",
        spec_hashes=["fake_hash_%02d" % i for i in range(15)],
        declared_budget=15,
        verdict_criteria="descriptive-only",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    _reg(
        exp_id="trim_grid_v1",
        question="TRIM-GRID-1 test",
        spec_hashes=[s.content_hash() for s in specs],
        declared_budget=len(specs),
        verdict_criteria="descriptive-only",
        derived_from_surface="exit_grid_v1",
        registry_path=registry_path,
        ledger_path=ledger_path,
    )

    summary = run_experiment(
        "trim_grid_v1",
        boarded_path=boarded_path,
        massive_dir=massive_dir,
        registry_path=registry_path,
        results_dir=results_dir,
    )

    # Pooled SUM = 15 + 6 = 21
    assert summary["cumulative_pooled_replay_trial_count"] == 21

    # Max()-basis is 15 (the exit_grid_v1 budget)
    meta = summary["trim_grid_v1_meta"]
    assert meta["trial_ledger_max_basis"] == 15, (
        f"Expected max()-basis=15, got {meta['trial_ledger_max_basis']}"
    )
    # Both numbers mentioned in the note
    assert "15" in meta["trial_ledger_max_basis_note"]
    assert "21" in meta["trial_ledger_max_basis_note"]


# ---------------------------------------------------------------------------
# 10. No "validated" in output (house law check)
# ---------------------------------------------------------------------------

def test_no_validated_in_policy_dicts() -> None:
    """ScaledPolicy.to_dict() does not contain the word 'validated'."""
    sp = ScaledPolicy.scaled([
        (0.5, ExitPolicy.hold(21)),
        (0.5, ExitPolicy.ema_trail(span=8, resample="3B")),
    ])
    d_str = json.dumps(sp.to_dict())
    assert "validated" not in d_str.lower()
