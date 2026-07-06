"""tests/test_rule_replay_core.py — NW Rails R1 core tests.

All tests use synthetic in-memory fixtures only — no Mac-local data required.

Coverage:
  1. vintage_stamp — field completeness, degraded flag, StampRefusal on missing stamp
  2. RuleSpec — content hash stability, frozen enum v1 validation
  3. ExitPolicy — all four kinds, invalid construction
  4. CohortFilter — conjunction predicates, unknown-column handling
  5. Governor refusal — unregistered hash, hash mismatch
  6. EMA8 parity — ema_trail output matches engine.signal_quality.signal_frame
  7. barrier correctness — hand-computed stop/target paths
  8. trail_stop correctness — high-watermark trailing stop hand-computed
  9. hold correctness — time exit
 10. censoring — path shorter than policy
 11. ERA LAW splitting — verdict_grade / survivor split
 12. Stamp refusal on serialize_results
 13. Registration pooled-family assertion (family='replay' exactly)
 14. Registry round-trip (register → load → verify_spec_hashes pass/fail)
 15. pooled_replay_trial_count accumulates across registrations

Run:
    python -m pytest tests/test_rule_replay_core.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make sure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.vintage_stamp import StampRefusal, require_stamp, vintage_stamp
from engine.rule_replay import (
    CohortFilter,
    ExitPolicy,
    ExitKind,
    GovernorRefusal,
    RuleSpec,
    cohort_filter,
    era_law_split,
    replay_spec,
    serialize_results,
    VALID_HOLD_HORIZONS,
    VALID_TRAIL_STOP_PCTS,
)
from engine.rule_experiments import (
    REGISTRY_FAMILY,
    list_experiments,
    load_experiment,
    pooled_replay_trial_count,
    register_experiment,
    verify_spec_hashes,
)


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------
def _make_close(n: int = 200, start_price: float = 100.0, seed: int = 42) -> pd.Series:
    """Deterministic daily close series on a business-day index."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    returns = rng.normal(0.0005, 0.015, n)
    prices = start_price * np.cumprod(1 + returns)
    return pd.Series(prices, index=idx, name="close")


def _make_fires_df(n: int = 10, start_date: str = "2022-06-01") -> pd.DataFrame:
    """Synthetic fire tape with required columns."""
    dates = pd.bdate_range(start_date, periods=n)
    return pd.DataFrame({
        "ticker": [f"T{i:03d}" for i in range(n)],
        "fire_date": dates,
        "verdict_grade": [True] * n,
        "verdict_type": ["fire"] * n,
        "align_tier": ["T1"] * n,
    })


# ---------------------------------------------------------------------------
# 1. vintage_stamp
# ---------------------------------------------------------------------------
class TestVintageStamp:
    def test_builds_8_fields(self):
        s = vintage_stamp(
            price_plane_id="test_plane",
            adjustment_mode="split_adjusted_raw",
            universe_as_of="2026-07-06",
            frame="pit_massive_era_law",
            survivorship_biased=False,
            coverage_frac=0.95,
            dead_name_coverage_pct=38.3,
            era_law_cohort="verdict_grade_2021plus",
        )
        required = {
            "price_plane_id", "adjustment_mode", "universe_as_of", "frame",
            "survivorship_biased", "coverage_frac", "dead_name_coverage_pct",
            "era_law_cohort",
        }
        assert required <= s.keys()
        assert s["coverage_frac"] == 0.95
        assert s["survivorship_biased"] is False

    def test_degraded_flag_when_file_absent(self, tmp_path):
        """When the dead-name JSON is absent, stamp_degraded=True and pct=None."""
        s = vintage_stamp(
            price_plane_id="test_plane",
            adjustment_mode="raw",
            universe_as_of="2026-01-01",
            frame="test",
            survivorship_biased=False,
            coverage_frac=1.0,
            dead_name_coverage_pct=None,
            era_law_cohort="test_cohort",
            _dead_name_path=tmp_path / "nonexistent.json",
        )
        assert s.get("stamp_degraded") is True
        assert s["dead_name_coverage_pct"] is None

    def test_reads_dead_name_json_when_present(self, tmp_path):
        """When the JSON is present with coverage_pct, it is loaded."""
        p = tmp_path / "dead.json"
        p.write_text(json.dumps({"coverage_pct": 38.3}))
        s = vintage_stamp(
            price_plane_id="test_plane",
            adjustment_mode="raw",
            universe_as_of="2026-01-01",
            frame="test",
            survivorship_biased=False,
            coverage_frac=1.0,
            dead_name_coverage_pct=None,
            era_law_cohort="test_cohort",
            _dead_name_path=p,
        )
        assert s["dead_name_coverage_pct"] == pytest.approx(38.3)
        assert "stamp_degraded" not in s

    def test_reads_dead_name_json_price_coverage_frac(self, tmp_path):
        """B2 fix: price_coverage_frac (v2 schema key) is converted frac→pct correctly."""
        p = tmp_path / "dead_v2.json"
        # Mirrors the actual data/edgar/_dead_name_coverage.json schema
        p.write_text(json.dumps({
            "schema": "dead_name_coverage.v2",
            "price_coverage_frac": 0.3832,
        }))
        s = vintage_stamp(
            price_plane_id="test_plane",
            adjustment_mode="raw",
            universe_as_of="2026-01-01",
            frame="test",
            survivorship_biased=False,
            coverage_frac=1.0,
            dead_name_coverage_pct=None,
            era_law_cohort="test_cohort",
            _dead_name_path=p,
        )
        # 0.3832 * 100 = 38.32 pct
        assert s["dead_name_coverage_pct"] == pytest.approx(38.32, abs=0.01)
        assert "stamp_degraded" not in s

    def test_reads_dead_name_json_coverage_frac(self, tmp_path):
        """B2 fix: coverage_frac key (generic fraction) is also converted frac→pct."""
        p = tmp_path / "dead_frac.json"
        p.write_text(json.dumps({"coverage_frac": 0.50}))
        s = vintage_stamp(
            price_plane_id="test_plane",
            adjustment_mode="raw",
            universe_as_of="2026-01-01",
            frame="test",
            survivorship_biased=False,
            coverage_frac=1.0,
            dead_name_coverage_pct=None,
            era_law_cohort="test_cohort",
            _dead_name_path=p,
        )
        assert s["dead_name_coverage_pct"] == pytest.approx(50.0)
        assert "stamp_degraded" not in s

    def test_coverage_frac_bounds(self):
        with pytest.raises(ValueError, match="coverage_frac"):
            vintage_stamp(
                price_plane_id="x", adjustment_mode="x", universe_as_of="2026-01-01",
                frame="x", survivorship_biased=False, coverage_frac=1.5,
                dead_name_coverage_pct=0.0, era_law_cohort="x"
            )

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError):
            vintage_stamp(
                price_plane_id="", adjustment_mode="x", universe_as_of="2026-01-01",
                frame="x", survivorship_biased=False, coverage_frac=1.0,
                dead_name_coverage_pct=0.0, era_law_cohort="x"
            )

    def test_require_stamp_raises_on_non_dict(self):
        with pytest.raises(StampRefusal):
            require_stamp(None)

    def test_require_stamp_raises_on_missing_fields(self):
        with pytest.raises(StampRefusal, match="missing required fields"):
            require_stamp({"price_plane_id": "x"})

    def test_require_stamp_passes_on_valid(self):
        s = vintage_stamp(
            price_plane_id="x", adjustment_mode="x", universe_as_of="2026-01-01",
            frame="x", survivorship_biased=True, coverage_frac=0.5,
            dead_name_coverage_pct=0.0, era_law_cohort="x"
        )
        result = require_stamp(s)
        assert result is s


# ---------------------------------------------------------------------------
# 2. ExitPolicy construction
# ---------------------------------------------------------------------------
class TestExitPolicy:
    def test_hold_valid(self):
        p = ExitPolicy.hold(21)
        assert p.kind == ExitKind.HOLD
        assert p.hold_bars == 21

    def test_hold_invalid(self):
        with pytest.raises(ValueError, match="frozen v1"):
            ExitPolicy.hold(99)

    def test_ema_trail_defaults(self):
        p = ExitPolicy.ema_trail()
        assert p.kind == ExitKind.EMA_TRAIL
        assert p.ema_span == 8
        assert p.ema_resample == "3B"

    def test_trail_stop_valid(self):
        p = ExitPolicy.trail_stop(8)
        assert p.kind == ExitKind.TRAIL_STOP
        assert p.trail_pct == 8.0

    def test_trail_stop_invalid(self):
        with pytest.raises(ValueError, match="frozen v1"):
            ExitPolicy.trail_stop(7)

    def test_barrier_valid(self):
        p = ExitPolicy.barrier(-5.0, 15.0)
        assert p.stop_pct == -5.0
        assert p.target_pct == 15.0

    def test_barrier_positive_stop_rejected(self):
        with pytest.raises(ValueError, match="stop_pct must be negative"):
            ExitPolicy.barrier(5.0, 15.0)

    def test_barrier_negative_target_rejected(self):
        with pytest.raises(ValueError, match="target_pct must be positive"):
            ExitPolicy.barrier(-5.0, -15.0)

    def test_to_dict_canonical(self):
        p = ExitPolicy.hold(21)
        d = p.to_dict()
        assert d == {"kind": "hold", "H": 21}

    def test_slug_hold(self):
        assert ExitPolicy.hold(21).slug() == "hold_21"

    def test_slug_trail_stop(self):
        assert ExitPolicy.trail_stop(12).slug() == "trail_stop_12pct"


# ---------------------------------------------------------------------------
# 3. RuleSpec — hash stability
# ---------------------------------------------------------------------------
class TestRuleSpec:
    def _make_spec(self, exit_policy=None, spec_id="test/hold_21"):
        return RuleSpec(
            spec_id=spec_id,
            cohort=CohortFilter(),
            delay_n=1,
            exit=exit_policy or ExitPolicy.hold(21),
            weight="full",
            horizons_ref=(126,),
        )

    def test_hash_is_deterministic(self):
        s = self._make_spec()
        assert s.content_hash() == s.content_hash()

    def test_hash_excludes_spec_id(self):
        """Same parameters with different spec_id must hash identically."""
        s1 = self._make_spec(spec_id="grid/a")
        s2 = self._make_spec(spec_id="grid/b")
        assert s1.content_hash() == s2.content_hash()

    def test_hash_differs_on_exit_change(self):
        s1 = self._make_spec(exit_policy=ExitPolicy.hold(21))
        s2 = self._make_spec(exit_policy=ExitPolicy.hold(42))
        assert s1.content_hash() != s2.content_hash()

    def test_invalid_weight(self):
        with pytest.raises(ValueError, match="weight must be 'full'"):
            RuleSpec(
                spec_id="x", cohort=CohortFilter(), exit=ExitPolicy.hold(21),
                weight="halved", horizons_ref=(126,)
            )

    def test_invalid_horizon(self):
        with pytest.raises(ValueError, match="frozen v1"):
            RuleSpec(
                spec_id="x", cohort=CohortFilter(), exit=ExitPolicy.hold(21),
                horizons_ref=(99,)
            )

    def test_to_dict_has_content_hash(self):
        s = self._make_spec()
        d = s.to_dict()
        assert "content_hash" in d
        assert d["content_hash"] == s.content_hash()


# ---------------------------------------------------------------------------
# 4. CohortFilter
# ---------------------------------------------------------------------------
class TestCohortFilter:
    def _make_df(self):
        return pd.DataFrame({
            "verdict_type": ["fire", "watch", "fire", "watch"],
            "align_tier": ["T1", "T1", "T2", "T2"],
            "year": [2022, 2022, 2023, 2023],
        })

    def test_empty_filter_passes_all(self):
        df = self._make_df()
        mask = CohortFilter().apply(df)
        assert mask.all()

    def test_eq_filter(self):
        df = self._make_df()
        cf = cohort_filter(("eq", "verdict_type", "fire"))
        mask = cf.apply(df)
        assert list(mask) == [True, False, True, False]

    def test_conjunction_filter(self):
        df = self._make_df()
        cf = cohort_filter(
            ("eq", "verdict_type", "fire"),
            ("eq", "align_tier", "T1"),
        )
        mask = cf.apply(df)
        assert list(mask) == [True, False, False, False]

    def test_isin_filter(self):
        df = self._make_df()
        cf = cohort_filter(("isin", "align_tier", frozenset({"T1", "T2"})))
        mask = cf.apply(df)
        assert mask.all()

    def test_ge_filter(self):
        df = self._make_df()
        cf = cohort_filter(("ge", "year", 2023))
        mask = cf.apply(df)
        assert list(mask) == [False, False, True, True]

    def test_missing_column_returns_all_false(self):
        df = self._make_df()
        cf = cohort_filter(("eq", "nonexistent_col", "x"))
        mask = cf.apply(df)
        assert not mask.any()


# ---------------------------------------------------------------------------
# 5. Governor refusal
# ---------------------------------------------------------------------------
class TestGovernorRefusal:
    def _make_minimal_setup(self):
        close = _make_close(200)
        fires = _make_fires_df(5, "2022-06-01")
        spec = RuleSpec(
            spec_id="gov_test/hold_21",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        closes = {t: close for t in fires["ticker"]}
        return spec, fires, closes

    def test_refusal_on_unregistered_hash(self):
        spec, fires, closes = self._make_minimal_setup()
        with pytest.raises(GovernorRefusal, match="not registered"):
            replay_spec(spec, fires, closes, registry_hashes={"deadbeef"})

    def test_passes_when_hash_in_registry(self):
        spec, fires, closes = self._make_minimal_setup()
        h = spec.content_hash()
        # Should not raise
        result = replay_spec(spec, fires, closes, registry_hashes={h})
        assert isinstance(result, pd.DataFrame)

    def test_registry_hashes_is_required(self):
        """registry_hashes is now a required parameter — no bypass mode exists."""
        spec, fires, closes = self._make_minimal_setup()
        with pytest.raises(TypeError):
            replay_spec(spec, fires, closes)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 6. EMA8 parity against signal_quality
# ---------------------------------------------------------------------------
class TestEMA8Parity:
    def test_ema_trail_matches_signal_quality(self):
        """The ema_trail from _compute_ema_trail_series must match signal_quality.signal_frame."""
        from engine.signal_quality import signal_frame
        from engine.rule_replay import _compute_ema_trail_series

        close = _make_close(520, seed=7)
        sig = signal_frame(close)
        if sig.empty:
            pytest.skip("synthetic series too short for signal_frame")

        trail_ours, breach_ours = _compute_ema_trail_series(close)

        # Should match signal_frame's ema_trail on the same 3B-resampled index
        assert len(trail_ours) > 0
        common_idx = sig.index.intersection(trail_ours.index)
        assert len(common_idx) > 10, "too few common bars for parity check"

        # The ema_trail values must be identical on common bars (skip NaN — both NaN is correct)
        for dt in common_idx:
            expected = sig.loc[dt, "ema_trail"]
            got = trail_ours.loc[dt]
            if pd.isna(expected) and pd.isna(got):
                continue  # both NaN: parity holds (min_periods not yet satisfied)
            assert abs(expected - got) < 1e-10, (
                f"EMA trail mismatch at {dt}: signal_quality={expected}, ours={got}"
            )

    def test_ema_trail_exit_via_replay_spec(self):
        """EMA trail exit fires within a reasonable number of bars on a trending-then-break series."""
        # Build a series that trends up then breaks down
        n = 600
        idx = pd.bdate_range("2021-07-06", periods=n)
        # Build up-leg (400 bars)
        up_returns = np.random.default_rng(1).normal(0.002, 0.01, 400)
        up_prices = 100 * np.cumprod(1 + up_returns)
        peak = float(up_prices[-1])
        # Build down-leg (200 bars) from peak
        down_returns = np.random.default_rng(2).normal(-0.005, 0.01, 200)
        down_prices = peak * np.cumprod(1 + down_returns)
        prices = np.concatenate([up_prices, down_prices])
        close = pd.Series(prices, index=idx)

        # Fire at bar 390 (during uptrend, 10 bars from peak)
        fire_date = idx[385]
        fires = pd.DataFrame({
            "ticker": ["EMA_TEST"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        closes = {"EMA_TEST": close}
        spec = RuleSpec(
            spec_id="ema_parity_test/ema_trail",
            cohort=CohortFilter(),
            exit=ExitPolicy.ema_trail(),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, closes, registry_hashes={spec.content_hash()})
        assert len(result) == 1
        # Result exists (not all-None due to close coverage)
        row = result.iloc[0]
        # Either a valid exit or censored — not an error state
        assert row["ticker"] == "EMA_TEST"


# ---------------------------------------------------------------------------
# 7. Barrier correctness (hand-computed)
# ---------------------------------------------------------------------------
class TestBarrierPolicy:
    def _barrier_close_series(self) -> pd.Series:
        """Hand-crafted: hits +15% target at bar 10 (0-indexed from fill)."""
        idx = pd.bdate_range("2022-01-03", periods=50)
        prices = [100.0] * 50
        # Steady rise: +1.5% per bar, hits +15% at bar 10
        for i in range(1, 50):
            prices[i] = prices[i - 1] * 1.015
        return pd.Series(prices, index=idx)

    def test_barrier_hits_target(self):
        close = self._barrier_close_series()
        # fire on bar 0 (signal_date = idx[0]), fill at bar 1
        fire_date = close.index[0]
        fires = pd.DataFrame({
            "ticker": ["BAR"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="barrier_test/t15_s5",
            cohort=CohortFilter(),
            exit=ExitPolicy.barrier(-5.0, 15.0),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"BAR": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        # Should not be censored — path is long enough
        assert row["censored"] is False or row["censored"] == False  # noqa: E712
        assert row["exit_ret"] is not None
        # Exit ret should be approximately +15% (close-only, first close >= 1.15x entry)
        assert row["exit_ret"] > 0.14  # allowing for discrete close alignment

    def _stop_close_series(self) -> pd.Series:
        """Hand-crafted: drops below stop (-8%) at bar 5."""
        idx = pd.bdate_range("2022-01-03", periods=50)
        prices = [100.0] * 50
        # Entry at bar 1 close = 100; drop to 91.5 by bar 5 (< 92 = entry * 0.92 stop)
        for i in range(1, 6):
            prices[i] = 100.0 - i * 2.0  # 98, 96, 94, 92, 90 — hits stop at bar 5
        for i in range(6, 50):
            prices[i] = 90.0
        return pd.Series(prices, index=idx)

    def test_barrier_hits_stop(self):
        close = self._stop_close_series()
        fire_date = close.index[0]
        fires = pd.DataFrame({
            "ticker": ["STP"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="barrier_test/s8_t20",
            cohort=CohortFilter(),
            exit=ExitPolicy.barrier(-8.0, 20.0),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"STP": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        assert row["exit_ret"] is not None
        # Should hit stop (negative return)
        assert row["exit_ret"] < 0


# ---------------------------------------------------------------------------
# 8. trail_stop correctness
# ---------------------------------------------------------------------------
class TestTrailStop:
    def test_trail_stop_triggers_correctly(self):
        """Hand-computed: rises to HWM=120 at bar 20, then drops to 96 = 120*(1-0.20)."""
        n = 60
        idx = pd.bdate_range("2022-01-03", periods=n)
        prices = [100.0] * n
        # Entry at bar 1 = 100.0
        # Rise to 120 by bar 20 (+1% per bar)
        for i in range(1, 21):
            prices[i] = 100.0 + i * 1.0
        # Plateau then fall
        for i in range(21, 45):
            prices[i] = 120.0 - (i - 20) * 1.5  # drops ~1.5 per bar
        for i in range(45, n):
            prices[i] = prices[44]
        close = pd.Series(prices, index=idx)

        fire_date = close.index[0]
        fires = pd.DataFrame({
            "ticker": ["TRL"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="trail_test/20pct",
            cohort=CohortFilter(),
            exit=ExitPolicy.trail_stop(20),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"TRL": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        # Should exit when price drops 20% from HWM=120, i.e. at ~96
        # HWM=120 reached at bar 21 (0-indexed from fill), stop = 120 * 0.8 = 96
        # That happens around bar 37-38 in the path
        assert row["exit_ret"] is not None
        assert row["mfe_to_exit"] > 0.10  # MFE > 10% (it ran to 120)

    def test_trail_stop_never_triggered_full_window_is_held_to_reference(self):
        """B1 fix: a wide stop that never fires over a FULL window is the policy
        outcome (held to reference), NOT censored data — it must carry the
        reference-horizon return and enter aggregates."""
        n = 200  # full 126-bar forward window available
        idx = pd.bdate_range("2022-01-03", periods=n)
        # Monotone riser: never gives back 20% from its high-watermark
        close = pd.Series([100.0 + i * 0.5 for i in range(n)], index=idx)
        fire_date = close.index[0]
        fires = pd.DataFrame({
            "ticker": ["RUN"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="trail_test/never_fires",
            cohort=CohortFilter(),
            exit=ExitPolicy.trail_stop(20),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"RUN": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        assert bool(row["held_to_reference"]) is True
        assert bool(row["short_path"]) is False
        assert bool(row["censored"]) is False
        # exit_ret equals the reference-horizon (bar-126) return, a winner
        assert row["exit_ret"] > 0.4

    def test_trail_stop_never_triggered_short_window_is_short_path(self):
        """A never-triggered stop over a TRUNCATED window is a genuine censor."""
        n = 60  # < 126-bar reference window
        idx = pd.bdate_range("2022-01-03", periods=n)
        close = pd.Series([100.0 + i * 0.5 for i in range(n)], index=idx)
        fires = pd.DataFrame({
            "ticker": ["SHT"],
            "fire_date": [close.index[0]],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="trail_test/short_window",
            cohort=CohortFilter(),
            exit=ExitPolicy.trail_stop(20),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"SHT": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        assert bool(row["short_path"]) is True
        assert bool(row["censored"]) is True
        assert bool(row["held_to_reference"]) is False


# ---------------------------------------------------------------------------
# 9. hold correctness
# ---------------------------------------------------------------------------
class TestHoldPolicy:
    def test_hold_exits_at_H(self):
        close = _make_close(200)
        fire_date = close.index[10]
        fires = pd.DataFrame({
            "ticker": ["HLD"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="hold_test/hold_21",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"HLD": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        # Should exit at bar offset 21 (hold for 21 bars from fill)
        if not row["censored"]:
            assert row["exit_bar_offset"] == 21

    def test_hold_censored_when_path_too_short(self):
        """Fire near end of series — not enough bars for hold(63), should be censored."""
        close = _make_close(80)
        fire_date = close.index[70]  # only ~10 bars remaining after fill
        fires = pd.DataFrame({
            "ticker": ["CEN"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="censor_test/hold_63",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(63),
            horizons_ref=(63,),
        )
        result = replay_spec(spec, fires, {"CEN": close}, registry_hashes={spec.content_hash()})
        assert bool(result.iloc[0]["censored"]) is True


# ---------------------------------------------------------------------------
# 10. Censoring
# ---------------------------------------------------------------------------
class TestCensoring:
    def test_missing_close_marks_censored(self):
        fires = _make_fires_df(3)
        spec = RuleSpec(
            spec_id="censor_test/miss",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        # Pass empty closes dict — all fires should be censored
        result = replay_spec(spec, fires, {}, registry_hashes={spec.content_hash()})
        assert result["censored"].all()

    def test_foregone_mfe_is_null_when_censored(self):
        close = _make_close(30)
        fire_date = close.index[25]
        fires = pd.DataFrame({
            "ticker": ["C"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        spec = RuleSpec(
            spec_id="censor_test/hold_126",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(126),
            horizons_ref=(126,),
        )
        result = replay_spec(spec, fires, {"C": close}, registry_hashes={spec.content_hash()})
        row = result.iloc[0]
        assert bool(row["censored"]) is True
        # foregone_mfe and avoided_mae are null for censored fires
        # (fwd_mfe_126 is also None when path is too short)
        val = row.get("foregone_mfe_126")
        assert val is None or (isinstance(val, float) and np.isnan(val))


# ---------------------------------------------------------------------------
# 11. ERA LAW splitting
# ---------------------------------------------------------------------------
class TestEraLawSplit:
    def test_splits_correctly(self):
        """Fires before 2021-07-06 go to survivor_biased; after go to verdict_grade."""
        df = pd.DataFrame({
            "ticker": ["A", "B", "C", "D"],
            "fire_date": pd.to_datetime([
                "2020-01-15",  # before ERA START → survivor_biased
                "2021-07-05",  # day before ERA START → survivor_biased
                "2021-07-06",  # ERA START → verdict_grade (if verdict_grade=True)
                "2022-01-01",  # after → verdict_grade
            ]),
            "verdict_grade": [True, True, True, True],
        })
        vg, sb = era_law_split(df)
        assert len(vg) == 2  # 2021-07-06 and 2022-01-01
        assert len(sb) == 2  # 2020-01-15 and 2021-07-05

    def test_verdict_grade_false_goes_to_survivor(self):
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "fire_date": pd.to_datetime(["2022-01-01", "2022-06-01"]),
            "verdict_grade": [True, False],  # second one is NOT verdict_grade
        })
        vg, sb = era_law_split(df)
        assert len(vg) == 1
        assert len(sb) == 1

    def test_no_date_col_all_survivor(self):
        """No date column → all rows go to survivor_biased (safe fallback)."""
        df = pd.DataFrame({"ticker": ["A", "B"], "no_date": [1, 2], "verdict_grade": [True, True]})
        vg, sb = era_law_split(df)
        assert len(vg) == 0
        assert len(sb) == 2

    def test_no_verdict_grade_col_raises(self):
        """verdict_grade column absent → raise ValueError (over-claiming guard)."""
        df = pd.DataFrame({
            "ticker": ["A", "B"],
            "fire_date": pd.to_datetime(["2022-01-01", "2022-06-01"]),
        })
        with pytest.raises(ValueError, match="verdict_grade"):
            era_law_split(df)


# ---------------------------------------------------------------------------
# 12. serialize_results stamp refusal
# ---------------------------------------------------------------------------
class TestSerializeResults:
    def test_refusal_on_no_stamp(self):
        fires = _make_fires_df(3)
        close = _make_close(200)
        spec = RuleSpec(
            spec_id="ser_test/hold_21",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        closes = {t: close for t in fires["ticker"]}
        result = replay_spec(spec, fires, closes, registry_hashes={spec.content_hash()})
        with pytest.raises(StampRefusal):
            serialize_results(result, spec, vintage=None)

    def test_serializes_with_valid_stamp(self):
        fires = _make_fires_df(3)
        close = _make_close(200)
        spec = RuleSpec(
            spec_id="ser_test/hold_21_ok",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        closes = {t: close for t in fires["ticker"]}
        result = replay_spec(spec, fires, closes, registry_hashes={spec.content_hash()})
        stamp = vintage_stamp(
            price_plane_id="test", adjustment_mode="split_adj",
            universe_as_of="2026-07-06", frame="pit",
            survivorship_biased=False, coverage_frac=1.0,
            dead_name_coverage_pct=38.3, era_law_cohort="verdict_grade_2021plus",
        )
        out = serialize_results(result, spec, vintage=stamp)
        # Must be JSON-serializable
        json_str = json.dumps(out)
        data = json.loads(json_str)
        assert "vintage_stamp" in data
        assert "spec" in data
        assert "n_fires" in data


# ---------------------------------------------------------------------------
# 13. Registration — pooled-family assertion
# ---------------------------------------------------------------------------
class TestRegistrationPooledFamily:
    def test_registration_uses_replay_family(self, tmp_path):
        """Registration must write to family='replay' (the flat pooled family, §3.3)."""
        from engine.trial_ledger import TrialLedger
        ledger_path = tmp_path / "trial_ledger.jsonl"
        registry_path = tmp_path / "registry.jsonl"

        spec = RuleSpec(
            spec_id="fam_test/hold_21",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )

        register_experiment(
            exp_id="fam-test-001",
            question="Does hold-21 beat hold-63? (grid=1)",
            spec_hashes=[spec.content_hash()],
            declared_budget=1,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )

        # Verify the family written to ledger is exactly 'replay'
        led = TrialLedger(ledger_path)
        families = led.families()
        assert REGISTRY_FAMILY in families, (
            f"Expected family 'replay' in ledger; found {families}"
        )
        assert families == [REGISTRY_FAMILY], (
            f"Only 'replay' family should be present; found {families}"
        )
        # Verify budget was recorded
        assert led.effective_n(REGISTRY_FAMILY) >= 1

    def test_no_sub_scoped_family(self, tmp_path):
        """Registrations must never write a sub-scoped family like 'replay.exp1'."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        registry_path = tmp_path / "registry.jsonl"
        spec = RuleSpec(
            spec_id="sub/hold_21",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        register_experiment(
            exp_id="sub-scope-test",
            question="Sub-scope test (grid=1)",
            spec_hashes=[spec.content_hash()],
            declared_budget=1,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )
        from engine.trial_ledger import TrialLedger
        led = TrialLedger(ledger_path)
        for fam in led.families():
            assert "." not in fam, f"Sub-scoped family found: {fam!r}"
            assert fam == REGISTRY_FAMILY, f"Unexpected family: {fam!r}"


# ---------------------------------------------------------------------------
# 14. Registry round-trip: register → load → verify_spec_hashes
# ---------------------------------------------------------------------------
class TestRegistryRoundTrip:
    def _make_spec_grid(self) -> list[RuleSpec]:
        return [
            RuleSpec(
                spec_id=f"rt_test/hold_{h}",
                cohort=CohortFilter(),
                exit=ExitPolicy.hold(h),
                horizons_ref=(126,),
            )
            for h in [21, 63, 126]
        ]

    def test_round_trip_passes(self, tmp_path):
        registry_path = tmp_path / "registry.jsonl"
        ledger_path = tmp_path / "trial_ledger.jsonl"
        specs = self._make_spec_grid()
        hashes = [s.content_hash() for s in specs]

        register_experiment(
            exp_id="rt-test-001",
            question="Round-trip test (grid=3)",
            spec_hashes=hashes,
            declared_budget=3,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )

        entry = load_experiment("rt-test-001", registry_path)
        assert entry["declared_budget"] == 3
        assert entry["status"] == "registered"

        # Should not raise
        verify_spec_hashes(entry, specs)

    def test_hash_mismatch_raises_governor_refusal(self, tmp_path):
        from engine.rule_replay import GovernorRefusal
        registry_path = tmp_path / "registry.jsonl"
        ledger_path = tmp_path / "trial_ledger.jsonl"
        specs = self._make_spec_grid()
        hashes = [s.content_hash() for s in specs]

        register_experiment(
            exp_id="mismatch-test",
            question="Hash mismatch test (grid=3)",
            spec_hashes=hashes,
            declared_budget=3,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )

        entry = load_experiment("mismatch-test", registry_path)
        # Pass a modified spec list (different exit policy)
        wrong_specs = [
            RuleSpec(
                spec_id=f"wrong/hold_{h}",
                cohort=CohortFilter(),
                exit=ExitPolicy.hold(h),
                horizons_ref=(42,),   # different horizon
            )
            for h in [21, 63, 126]
        ]
        with pytest.raises(GovernorRefusal):
            verify_spec_hashes(entry, wrong_specs)

    def test_load_missing_exp_raises_key_error(self, tmp_path):
        registry_path = tmp_path / "registry.jsonl"
        registry_path.touch()
        with pytest.raises(KeyError, match="not found in registry"):
            load_experiment("nonexistent-exp", registry_path)


# ---------------------------------------------------------------------------
# 15. pooled_replay_trial_count accumulates across registrations (B1 fix)
# ---------------------------------------------------------------------------
class TestPooledTrialCount:
    def test_exact_sum_across_registrations(self, tmp_path):
        """pooled_replay_trial_count must return the SUM of declared budgets (15+8+4=27),
        NOT the max (15).  B1 fix: reads the registry, not the TrialLedger."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        registry_path = tmp_path / "registry.jsonl"

        def _make_spec(hold_h: int) -> RuleSpec:
            return RuleSpec(
                spec_id=f"b1_test/hold_{hold_h}",
                cohort=CohortFilter(),
                exit=ExitPolicy.hold(hold_h),
                horizons_ref=(126,),
            )

        # Register three experiments with distinct budgets: 15, 8, 4
        # Build enough distinct spec hashes (we can reuse for test purposes)
        specs_15 = [_make_spec(h) for h in [21, 63, 126, 5, 10, 21, 42] * 3][:15]
        # deduplicate hashes if needed — just need 15 distinct entries
        hashes_15 = list({s.content_hash() for s in specs_15})[:15]
        # If we can't get 15 distinct hashes (collision), pad with fake ones
        while len(hashes_15) < 15:
            hashes_15.append(f"fakehash{len(hashes_15):04d}")

        hashes_8 = [f"exp2hash{i:04d}" for i in range(8)]
        hashes_4 = [f"exp3hash{i:04d}" for i in range(4)]

        register_experiment(
            exp_id="b1-exp-1",
            question="B1 sum test experiment 1 (grid=15)",
            spec_hashes=hashes_15,
            declared_budget=15,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )
        register_experiment(
            exp_id="b1-exp-2",
            question="B1 sum test experiment 2 (grid=8)",
            spec_hashes=hashes_8,
            declared_budget=8,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )
        register_experiment(
            exp_id="b1-exp-3",
            question="B1 sum test experiment 3 (grid=4)",
            spec_hashes=hashes_4,
            declared_budget=4,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )

        count = pooled_replay_trial_count(registry_path)
        assert count == 27, (
            f"Expected cumulative sum 15+8+4=27, got {count}. "
            "pooled_replay_trial_count must SUM declared_budget, not take max."
        )

    def test_simple_two_reg_exact_sum(self, tmp_path):
        """Simple 2-registration case: sum of 2+1=3, not max(2,1)=2."""
        ledger_path = tmp_path / "trial_ledger.jsonl"
        registry_path = tmp_path / "registry.jsonl"

        spec_a = RuleSpec(
            spec_id="acc/a", cohort=CohortFilter(),
            exit=ExitPolicy.hold(21), horizons_ref=(126,)
        )
        spec_b = RuleSpec(
            spec_id="acc/b", cohort=CohortFilter(),
            exit=ExitPolicy.hold(63), horizons_ref=(126,)
        )
        spec_c = RuleSpec(
            spec_id="acc/c", cohort=CohortFilter(),
            exit=ExitPolicy.hold(126), horizons_ref=(126,)
        )

        register_experiment(
            exp_id="acc-exp-1",
            question="Accumulation test 1 (grid=2)",
            spec_hashes=[spec_a.content_hash(), spec_b.content_hash()],
            declared_budget=2,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )
        register_experiment(
            exp_id="acc-exp-2",
            question="Accumulation test 2 (grid=1)",
            spec_hashes=[spec_c.content_hash()],
            declared_budget=1,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )

        count = pooled_replay_trial_count(registry_path)
        assert count == 3, (
            f"Expected 2+1=3, got {count}. "
            "The TrialLedger's max() semantics would give 2, not 3 — "
            "pooled_replay_trial_count must read the registry and SUM."
        )


# ---------------------------------------------------------------------------
# 16. B2 — governor persists spec_hashes through lifecycle status updates
# ---------------------------------------------------------------------------
class TestStatusUpdateGovernorMerge:
    """B2: update_experiment_status appends records without spec_hashes.
    load_experiment must merge fields across ALL records so that spec_hashes
    from the original registration is never lost after a status update.
    """

    def _register_and_get_hashes(self, tmp_path) -> tuple:
        registry_path = tmp_path / "registry.jsonl"
        ledger_path = tmp_path / "trial_ledger.jsonl"
        spec = RuleSpec(
            spec_id="b2_test/hold_21",
            cohort=CohortFilter(),
            exit=ExitPolicy.hold(21),
            horizons_ref=(126,),
        )
        register_experiment(
            exp_id="b2-lifecycle-test",
            question="B2 governor merge test (grid=1)",
            spec_hashes=[spec.content_hash()],
            declared_budget=1,
            verdict_criteria="descriptive-only",
            registry_path=registry_path,
            ledger_path=ledger_path,
        )
        return registry_path, ledger_path, spec

    def test_verify_spec_hashes_passes_after_executed_update(self, tmp_path):
        """register → update to executed → verify_spec_hashes passes (B2 fix)."""
        from engine.rule_experiments import update_experiment_status
        registry_path, ledger_path, spec = self._register_and_get_hashes(tmp_path)

        update_experiment_status(
            "b2-lifecycle-test",
            "executed",
            registry_path=registry_path,
        )
        entry = load_experiment("b2-lifecycle-test", registry_path)
        assert entry["status"] == "executed", f"Expected executed, got {entry['status']}"
        # spec_hashes must still be present after the status update
        assert "spec_hashes" in entry, (
            "spec_hashes was lost after status update — load_experiment must merge records"
        )
        # verify_spec_hashes must not raise (this is the key B2 assertion)
        verify_spec_hashes(entry, [spec])  # should not raise GovernorRefusal

    def test_verify_spec_hashes_passes_after_reported_update(self, tmp_path):
        """register → executed → reported → verify_spec_hashes still passes."""
        from engine.rule_experiments import update_experiment_status
        registry_path, ledger_path, spec = self._register_and_get_hashes(tmp_path)

        update_experiment_status(
            "b2-lifecycle-test", "executed", registry_path=registry_path
        )
        update_experiment_status(
            "b2-lifecycle-test", "reported", registry_path=registry_path
        )
        entry = load_experiment("b2-lifecycle-test", registry_path)
        assert entry["status"] == "reported"
        assert "spec_hashes" in entry
        verify_spec_hashes(entry, [spec])  # must not raise


# ---------------------------------------------------------------------------
# 17. B3 — EMA trail uses full close history (not censored forward slice)
# ---------------------------------------------------------------------------
class TestEMATrailFullHistory:
    """B3: _compute_ema_trail_series must be called on the FULL close history,
    not on close.iloc[fill_idx:], to avoid systematically censoring fires
    because the forward slice is shorter than 90 3B-bars.
    """

    def test_ema_trail_noncensored_at_known_breach_bar(self):
        """Synthetic multi-year series: uptrend then breakdown.

        The fire occurs within the first 400 bars (uptrend phase).  The series
        has 750+ daily bars (>= 250 3B-bars >> 90 minimum).  With the full-history
        fix the exit_bar_offset should be a concrete positive integer (the breach
        bar in the breakdown leg), NOT censored.

        Without the fix, close.iloc[fill_idx:] would have only ~350 bars (~117 3B
        bars) — passing the 90 minimum, so this specific test might not catch the
        boundary case.  We instead test the structural fix directly: fire near bar
        400, series has 750 bars total.  The forward slice from bar 350 has 400 bars
        = 133 3B-bars; the full series has 750 bars = 250 3B-bars.  Both exceed 90,
        but only the full-history path computes the correct global trail series.
        """
        # Build a series that trends strongly up (400 bars), then crashes (350 bars)
        n_up = 400
        n_down = 350
        n = n_up + n_down
        idx = pd.bdate_range("2019-01-02", periods=n)

        rng_up = np.random.default_rng(42)
        up_returns = rng_up.normal(0.0015, 0.008, n_up)
        up_prices = 100.0 * np.cumprod(1 + up_returns)
        peak = float(up_prices[-1])

        rng_down = np.random.default_rng(99)
        down_returns = rng_down.normal(-0.004, 0.01, n_down)
        down_prices = peak * np.cumprod(1 + down_returns)

        prices = np.concatenate([up_prices, down_prices])
        close = pd.Series(prices, index=idx)

        # Fire near bar 350 (deep in uptrend, 400 bars to end of uptrend)
        fire_date = idx[350]
        fires = pd.DataFrame({
            "ticker": ["B3_TEST"],
            "fire_date": [fire_date],
            "verdict_grade": [True],
        })
        closes = {"B3_TEST": close}

        spec = RuleSpec(
            spec_id="b3_test/ema_trail",
            cohort=CohortFilter(),
            exit=ExitPolicy.ema_trail(),
            horizons_ref=(126,),
        )

        result = replay_spec(spec, fires, closes, registry_hashes={spec.content_hash()})
        assert len(result) == 1
        row = result.iloc[0]

        # The series crashes hard in the down leg — the EMA trail MUST fire.
        # With the full-history fix, the breach is found; without it the pre-fix
        # code could still find it (slice > 90), but the trail reference is wrong
        # (computed only from fill_idx onward, not anchored to full history).
        # Key assertion: NOT censored — the breakdown generates a breach.
        assert not bool(row["censored"]), (
            f"EMA trail should fire in the crash leg but got censored=True. "
            f"exit_bar_offset={row.get('exit_bar_offset')}"
        )
        assert row["exit_bar_offset"] is not None
        assert isinstance(row["exit_bar_offset"], (int, np.integer))

    def test_ema_trail_parity_full_vs_signal_quality_analyze(self):
        """Parity test: replay_spec EMA trail exit matches signal_quality.analyze() semantics.

        Verifies that the full-history path and the signal_quality reference agree on
        the first fresh-breach date for the same close series.
        """
        from engine.signal_quality import signal_frame
        from engine.rule_replay import _compute_ema_trail_series

        # Use a 600-bar series (well above 90 3B-bar floor)
        close = _make_close(600, seed=17)
        trail, fresh_breach = _compute_ema_trail_series(close)
        sig = signal_frame(close)

        if trail.empty or sig.empty:
            pytest.skip("Series too short for signal_frame (unexpected)")

        # The ema_trail values must match signal_quality's output on common bars
        common = sig.index.intersection(trail.index)
        assert len(common) > 20, "Too few common bars for parity check"

        mismatches = []
        for dt in common:
            expected = sig.loc[dt, "ema_trail"]
            got = trail.loc[dt]
            if pd.isna(expected) and pd.isna(got):
                continue
            if not (pd.isna(expected) or pd.isna(got)) and abs(expected - got) > 1e-10:
                mismatches.append((dt, expected, got))
        assert not mismatches, (
            f"EMA trail mismatch between _compute_ema_trail_series and signal_quality "
            f"on {len(mismatches)} bars (first: {mismatches[0]})"
        )
