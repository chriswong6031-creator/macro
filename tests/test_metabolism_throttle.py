"""tests/test_metabolism_throttle.py — Hermetic tests for Metabolism V10 Throttle.

COVERAGE:
  DEFAULTS  absent/garbage env → safe fail-open defaults
  INTENSITY each multiplier value (low/normal/high/max)
  PACE      pace_extra_cycles mapping (single/2x/4x)
  DOCKET    effective_docket_size at high/max/low intensities; DORMANT stays 0
            at every intensity; clamp never exceeds base at max intensity+FOCUS
  FAILURE   throttle import raises → effective_docket_size returns V9 behaviour

All tests are HERMETIC (monkeypatch env, in-process, no real data / network).
"""
from __future__ import annotations

import sys
import textwrap
from math import floor
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Minimal repo fixture (reused from test_metabolism_attention pattern)
# ---------------------------------------------------------------------------

_MINIMAL_CHARTERS_YML = textwrap.dedent("""\
schema: lobe_charters.v1
generated_at: '2026-07-12'
charters:
  test-lobe:
    lobe_id: test-lobe
    tier: display
    lifecycle_state: active
    information_domain: context
    fitness_sensors:
      - id: freshness_sla
        store: data/metabolism/fitness/test-lobe.json
  focus-lobe:
    lobe_id: focus-lobe
    tier: display
    lifecycle_state: active
    information_domain: context
""")

_MINIMAL_SYNAPSE_YML = textwrap.dedent("""\
meta:
  schema_version: 1
artifacts:
  test-lobe:
    path: data/test/data.json
    format: json
    producer: scripts/build_test.py
    owner_program: test
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/a.py
      - engine/b.py
    external_consumers: []
  focus-lobe:
    path: data/focus/data.json
    format: json
    producer: scripts/build_focus.py
    owner_program: focus
    cadence: daily
    storage: git
    freshness_sla_hours: 30
    tier: display
    horizon_role: context
    consumers:
      - engine/a.py
      - engine/b.py
    external_consumers:
      - mastermind:anchor
""")

_MINIMAL_ATTENTION_YML = textwrap.dedent("""\
schema: metabolism_attention.v1
generated_at: "2026-07-12"
owner_program: metabolism-v9
max_focus_lobes: 8
docket_share:
  FOCUS: 1.0
  STANDARD: 0.6
  MAINTENANCE: 0.2
  DORMANT: 0.0
dispatch_priority:
  FOCUS: 0
  STANDARD: 1
  MAINTENANCE: 2
  DORMANT: 3
""")


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data" / "metabolism").mkdir(parents=True)
    (root / "config" / "lobe_charters.yml").write_text(_MINIMAL_CHARTERS_YML, encoding="utf-8")
    (root / "config" / "synapse.yml").write_text(_MINIMAL_SYNAPSE_YML, encoding="utf-8")
    (root / "config" / "metabolism_attention.yml").write_text(_MINIMAL_ATTENTION_YML, encoding="utf-8")
    return root


def _make_allocation(band: str, lobe_id: str = "test-lobe") -> dict:
    return {
        "allocations": {
            lobe_id: {
                "band": band,
                "weight": 1.0 if band == "FOCUS" else 0.6,
                "structural_band": "STANDARD",
                "llm_band": None,
                "floored": False,
                "rationale": "",
            }
        }
    }


# ===========================================================================
# DEFAULTS — absent / garbage env values
# ===========================================================================

class TestDefaults:

    def test_intensity_absent_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("METAB_INTENSITY", raising=False)
        from engine.metabolism.throttle import intensity
        assert intensity() == "normal"

    def test_intensity_garbage_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_INTENSITY", "turbo")
        from engine.metabolism.throttle import intensity
        assert intensity() == "normal"

    def test_intensity_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_INTENSITY", "")
        from engine.metabolism.throttle import intensity
        assert intensity() == "normal"

    def test_pace_absent_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("METAB_PACE", raising=False)
        from engine.metabolism.throttle import pace
        assert pace() == "single"

    def test_pace_garbage_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "overdrive")
        from engine.metabolism.throttle import pace
        assert pace() == "single"

    def test_pace_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "")
        from engine.metabolism.throttle import pace
        assert pace() == "single"

    def test_intensity_multiplier_defaults_to_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("METAB_INTENSITY", raising=False)
        from engine.metabolism.throttle import intensity_multiplier
        assert intensity_multiplier() == 1.0

    def test_pace_extra_cycles_default_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("METAB_PACE", raising=False)
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles() == 0

    def test_describe_safe_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("METAB_INTENSITY", raising=False)
        monkeypatch.delenv("METAB_PACE", raising=False)
        from engine.metabolism.throttle import describe
        d = describe()
        assert d["intensity"] == "normal"
        assert d["multiplier"] == 1.0
        assert d["pace"] == "single"
        assert d["extra_cycles"] == 0


# ===========================================================================
# INTENSITY — each multiplier value
# ===========================================================================

class TestIntensityMultipliers:

    def test_low_multiplier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_INTENSITY", "low")
        from engine.metabolism.throttle import intensity_multiplier
        assert intensity_multiplier() == 0.5

    def test_normal_multiplier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_INTENSITY", "normal")
        from engine.metabolism.throttle import intensity_multiplier
        assert intensity_multiplier() == 1.0

    def test_high_multiplier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_INTENSITY", "high")
        from engine.metabolism.throttle import intensity_multiplier
        assert intensity_multiplier() == 1.5

    def test_max_multiplier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_INTENSITY", "max")
        from engine.metabolism.throttle import intensity_multiplier
        assert intensity_multiplier() == 2.0

    def test_intensity_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env value is lowercased before matching."""
        monkeypatch.setenv("METAB_INTENSITY", "HIGH")
        from engine.metabolism.throttle import intensity
        assert intensity() == "high"

    def test_intensity_multiplier_table_complete(self) -> None:
        """INTENSITY_MULT covers all four valid keys with correct values."""
        from engine.metabolism.throttle import INTENSITY_MULT
        assert INTENSITY_MULT == {"low": 0.5, "normal": 1.0, "high": 1.5, "max": 2.0}


# ===========================================================================
# PACE — pace_extra_cycles mapping
# ===========================================================================

class TestPaceExtraCycles:

    def test_single_gives_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "single")
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles() == 0

    def test_2x_gives_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "2x")
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles() == 1

    def test_4x_gives_three(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METAB_PACE", "4x")
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles() == 3

    def test_explicit_pace_arg_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing p= directly bypasses env lookup."""
        monkeypatch.setenv("METAB_PACE", "single")
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles("4x") == 3

    def test_garbage_pace_arg_returns_zero(self) -> None:
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles("warp-speed") == 0

    def test_all_pace_values_round_trip(self) -> None:
        from engine.metabolism.throttle import pace_extra_cycles
        assert pace_extra_cycles("single") == 0
        assert pace_extra_cycles("2x") == 1
        assert pace_extra_cycles("4x") == 3


# ===========================================================================
# DOCKET — effective_docket_size at various intensities
# ===========================================================================

class TestEffectiveDocketSizeWithThrottle:
    """
    Config shares: STANDARD=0.6, MAINTENANCE=0.2, FOCUS=1.0, DORMANT=0.0
    base_size=5

    STANDARD + high:      floor(5 * 0.6 * 1.5) = floor(4.5) = 4
    STANDARD + max:       floor(5 * 0.6 * 2.0) = floor(6.0) = 6 → clamped to 5
    MAINTENANCE + low:    floor(5 * 0.2 * 0.5) = floor(0.5) = 0 → max(1, 0) = 1
    FOCUS + max:          floor(5 * 1.0 * 2.0) = floor(10) = 10 → clamped to 5
    """

    def test_standard_high_intensity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """STANDARD 0.6 * high 1.5 → floor(5 * 0.6 * 1.5) = floor(4.5) = 4."""
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "high")
        alloc = _make_allocation("STANDARD")
        from engine.metabolism.attention import effective_docket_size
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 4

    def test_standard_max_intensity_clamped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """STANDARD 0.6 * max 2.0 → floor(6.0) = 6 → clamped to base_size=5."""
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "max")
        alloc = _make_allocation("STANDARD")
        from engine.metabolism.attention import effective_docket_size
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 5

    def test_maintenance_low_intensity_min_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MAINTENANCE 0.2 * low 0.5 → floor(0.5) = 0 → max(1, 0) = 1."""
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "low")
        alloc = _make_allocation("MAINTENANCE")
        from engine.metabolism.attention import effective_docket_size
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 1

    def test_focus_max_intensity_clamped_to_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """FOCUS 1.0 * max 2.0 → floor(10) = 10 → clamped to base_size=5 (G5)."""
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "max")
        alloc = _make_allocation("FOCUS")
        from engine.metabolism.attention import effective_docket_size
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 5

    def test_focus_max_clamp_never_exceeds_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """G5: at max intensity FOCUS result never exceeds any base_size value."""
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "max")
        alloc = _make_allocation("FOCUS")
        from engine.metabolism.attention import effective_docket_size
        for base in (1, 3, 7, 10, 100):
            result = effective_docket_size("test-lobe", base, root=root, allocation=alloc)
            assert result <= base, f"base={base}: result {result} exceeded base"

    def test_dormant_stays_zero_at_low(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "low")
        alloc = _make_allocation("DORMANT")
        from engine.metabolism.attention import effective_docket_size
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc) == 0

    def test_dormant_stays_zero_at_normal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "normal")
        alloc = _make_allocation("DORMANT")
        from engine.metabolism.attention import effective_docket_size
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc) == 0

    def test_dormant_stays_zero_at_high(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "high")
        alloc = _make_allocation("DORMANT")
        from engine.metabolism.attention import effective_docket_size
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc) == 0

    def test_dormant_stays_zero_at_max(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "max")
        alloc = _make_allocation("DORMANT")
        from engine.metabolism.attention import effective_docket_size
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc) == 0

    def test_normal_intensity_preserves_v9_behaviour(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Normal intensity (multiplier=1.0) produces the same result as V9."""
        root = _make_repo(tmp_path)
        monkeypatch.setenv("METAB_INTENSITY", "normal")
        from engine.metabolism.attention import effective_docket_size
        # STANDARD: floor(5 * 0.6 * 1.0) = 3
        alloc = _make_allocation("STANDARD")
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc) == 3
        # MAINTENANCE: floor(5 * 0.2 * 1.0) = 1 → max(1,1)=1
        alloc_m = _make_allocation("MAINTENANCE")
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc_m) == 1
        # FOCUS: floor(5 * 1.0 * 1.0) = 5
        alloc_f = _make_allocation("FOCUS")
        assert effective_docket_size("test-lobe", 5, root=root, allocation=alloc_f) == 5


# ===========================================================================
# FAILURE — throttle import raises → V9 fallback (multiplier 1.0)
# ===========================================================================

class TestThrottleFailureFallback:

    def test_throttle_import_failure_returns_v9_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the throttle module raises on import, effective_docket_size falls
        back to multiplier=1.0 and returns the pre-V10 (V9) value unchanged."""
        root = _make_repo(tmp_path)

        # Temporarily make the throttle module unimportable from attention's perspective
        import engine.metabolism.attention as att_mod

        original_floor = att_mod.floor

        def _floor_intercepted(x: float) -> int:
            return original_floor(x)

        # Patch intensity_multiplier inside the attention module's dynamic import
        # by shadowing engine.metabolism.throttle in sys.modules with a broken stub
        class _BrokenThrottle:
            @staticmethod
            def intensity_multiplier() -> float:
                raise RuntimeError("throttle broken")

        monkeypatch.setitem(sys.modules, "engine.metabolism.throttle", _BrokenThrottle())  # type: ignore[arg-type]

        from engine.metabolism.attention import effective_docket_size

        # STANDARD + broken throttle → floor(5 * 0.6 * 1.0) = 3 (V9 result)
        alloc = _make_allocation("STANDARD")
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 3, f"Expected V9 fallback result 3, got {result}"

    def test_throttle_import_failure_dormant_still_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even with broken throttle, DORMANT always returns 0."""
        root = _make_repo(tmp_path)

        class _BrokenThrottle:
            @staticmethod
            def intensity_multiplier() -> float:
                raise RuntimeError("throttle broken")

        monkeypatch.setitem(sys.modules, "engine.metabolism.throttle", _BrokenThrottle())  # type: ignore[arg-type]

        from engine.metabolism.attention import effective_docket_size
        alloc = _make_allocation("DORMANT")
        result = effective_docket_size("test-lobe", 5, root=root, allocation=alloc)
        assert result == 0


# ===========================================================================
# NEVER-RAISE — throttle module functions never raise
# ===========================================================================

class TestNeverRaise:

    def test_intensity_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("", "garbage", "LOW", "NORMAL", "low", "normal", "high", "max"):
            monkeypatch.setenv("METAB_INTENSITY", val)
            from engine.metabolism.throttle import intensity
            result = intensity()
            assert isinstance(result, str)

    def test_pace_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("", "garbage", "SINGLE", "single", "2x", "4x"):
            monkeypatch.setenv("METAB_PACE", val)
            from engine.metabolism.throttle import pace
            result = pace()
            assert isinstance(result, str)

    def test_intensity_multiplier_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("", "garbage", "low", "normal", "high", "max"):
            monkeypatch.setenv("METAB_INTENSITY", val)
            from engine.metabolism.throttle import intensity_multiplier
            result = intensity_multiplier()
            assert isinstance(result, float)

    def test_pace_extra_cycles_never_raises(self) -> None:
        from engine.metabolism.throttle import pace_extra_cycles
        for val in (None, "single", "2x", "4x", "garbage", ""):
            result = pace_extra_cycles(val)
            assert isinstance(result, int)

    def test_describe_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for intensity_val, pace_val in [
            ("", ""), ("garbage", "garbage"), ("max", "4x"), ("low", "single"),
        ]:
            monkeypatch.setenv("METAB_INTENSITY", intensity_val)
            monkeypatch.setenv("METAB_PACE", pace_val)
            from engine.metabolism.throttle import describe
            d = describe()
            assert isinstance(d, dict)
            assert "intensity" in d
            assert "multiplier" in d
            assert "pace" in d
            assert "extra_cycles" in d
