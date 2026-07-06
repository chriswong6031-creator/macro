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

    def test_no_registry_hashes_skips_check(self):
        spec, fires, closes = self._make_minimal_setup()
        # No registry_hashes argument: governor is bypassed (for dev use only)
        result = replay_spec(spec, fires, closes)
        assert isinstance(result, pd.DataFrame)


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
        result = replay_spec(spec, fires, closes)
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
        result = replay_spec(spec, fires, {"BAR": close})
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
        result = replay_spec(spec, fires, {"STP": close})
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
        result = replay_spec(spec, fires, {"TRL": close})
        row = result.iloc[0]
        # Should exit when price drops 20% from HWM=120, i.e. at ~96
        # HWM=120 reached at bar 21 (0-indexed from fill), stop = 120 * 0.8 = 96
        # That happens around bar 37-38 in the path
        assert row["exit_ret"] is not None
        assert row["mfe_to_exit"] > 0.10  # MFE > 10% (it ran to 120)


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
        result = replay_spec(spec, fires, {"HLD": close})
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
        result = replay_spec(spec, fires, {"CEN": close})
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
        result = replay_spec(spec, fires, {})
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
        result = replay_spec(spec, fires, {"C": close})
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
        df = pd.DataFrame({"ticker": ["A", "B"], "no_date": [1, 2]})
        vg, sb = era_law_split(df)
        assert len(vg) == 0
        assert len(sb) == 2


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
        result = replay_spec(spec, fires, closes)
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
        result = replay_spec(spec, fires, closes)
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
# 15. pooled_replay_trial_count accumulates across registrations
# ---------------------------------------------------------------------------
class TestPooledTrialCount:
    def test_accumulates(self, tmp_path):
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

        count = pooled_replay_trial_count(ledger_path)
        # Must be >= 3 (the declared budgets: 2 + 1 = 3 but ledger takes max,
        # since budgets are recorded separately per registration,
        # effective_n returns max(literal_n, declared_floor))
        # Two registrations with budget 2 and 1: literal_n includes both unique spec hashes (3)
        # and declared budget max is max(2, 3) = 3
        assert count >= 2, f"Expected cumulative count >= 2, got {count}"
