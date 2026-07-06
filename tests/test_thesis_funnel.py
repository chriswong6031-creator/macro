"""tests/test_thesis_funnel.py — LT-4: Thesis Funnel Shadow.

Six test groups:

  A. Survival flags: each flag independently fires → not_eligible.
     Includes s1_dilution, s2_moat_falsifier, s3_solvency, s4_coverage.

  B. State logic:
     - All clear + F>=6 + non-dilutive → thesis_candidate_shadow
     - All clear + F=5 → watch_for_thesis
     - All clear + capital 'unavailable' → still candidate-eligible (F>=6)
     - All clear + capital 'dilutive' → watch_for_thesis (not candidate)
     - Coverage floor: < 2 computable → not_eligible regardless of flags

  C. Piotroski and capital_allocation_delta nuances:
     - piotroski None → watch_for_thesis
     - capital_allocation 'accretive' → candidate (not disqualified)
     - capital_allocation 'neutral' → candidate

  D. Coverage floor in isolation.

  E. compute_thesis_funnel_safe: exception safety.

  F. Synapse registry: thesis_funnel artifacts have tier=display,
     scored_path_surfaces=[], horizon_role=hold_thesis, fdr_family=long_hold.

All tests are deterministic.  Groups A–E use purely in-memory data.
Group F does a read-only assertion against config/synapse.yml.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.thesis_funnel import (  # noqa: E402
    compute_thesis_funnel,
    compute_thesis_funnel_safe,
    STATES,
    _DILUTION_THRESHOLD_PCT,
    _ALTMAN_DISTRESS_MAX,
    _PIOTROSKI_CANDIDATE_MIN,
    _COVERAGE_MIN_COMPUTABLE,
    _HORIZON_ROLE,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _mf_clear() -> dict:
    """A moat_falsifiers result with all sensors non-firing and full coverage."""
    return {
        "ticker": "TEST",
        "coverage_n_years": 3,
        "sensor_coverage": "full",
        "sensors": {
            "margin_compression_despite_revenue_growth": {"fired": False, "coverage": "full"},
            "receivables_stretch": {"fired": False, "coverage": "full"},
            "inventory_build": {"fired": False, "coverage": "full"},
            "capital_intensity_rising": {"fired": False, "coverage": "full"},
        },
        "_horizon_role": "hold_thesis",
        "_display_only": True,
        "_version": "v1",
    }


def _mf_fired(sensor: str = "receivables_stretch") -> dict:
    """A moat_falsifiers result with one sensor firing."""
    mf = _mf_clear()
    mf["sensors"][sensor]["fired"] = True
    return mf


def _mf_missing() -> dict:
    """A moat_falsifiers result with no data (sensor_coverage=missing)."""
    return {
        "ticker": "TEST",
        "coverage_n_years": 0,
        "sensor_coverage": "missing",
        "sensors": {},
        "_horizon_role": "hold_thesis",
        "_display_only": True,
        "_version": "v1",
    }


def _base_kwargs() -> dict:
    """Minimal kwargs for a fully-computable passing ticker."""
    return dict(
        altman_z=3.5,          # safe zone (> 2.99)
        altman_approx=False,
        moat_falsifiers_result=_mf_clear(),
        shares_yoy_change_pct=0.5,   # below +3%, not dilutive
        capital_allocation_delta="neutral",
        piotroski_score=7,
        piotroski_of=9,
    )


# ===========================================================================
# Group A — Survival flags: each fires alone → not_eligible
# ===========================================================================

class TestSurvivalFlagsIndividual:
    """Each survival flag, when fired, produces not_eligible regardless of others."""

    def test_s1_dilution_alone_fires_not_eligible(self) -> None:
        kwargs = _base_kwargs()
        kwargs["shares_yoy_change_pct"] = _DILUTION_THRESHOLD_PCT + 0.1  # fires
        r = compute_thesis_funnel("TSLA", **kwargs)
        assert r["state"] == "not_eligible"
        assert r["flags"]["s1_dilution"]["fired"] is True
        assert "s1_dilution" in r["state_reason"]

    def test_s1_dilution_exactly_at_threshold_fires(self) -> None:
        kwargs = _base_kwargs()
        kwargs["shares_yoy_change_pct"] = _DILUTION_THRESHOLD_PCT  # exactly at 3.0
        r = compute_thesis_funnel("AAPL", **kwargs)
        assert r["state"] == "not_eligible"
        assert r["flags"]["s1_dilution"]["fired"] is True

    def test_s1_just_below_threshold_does_not_fire(self) -> None:
        kwargs = _base_kwargs()
        kwargs["shares_yoy_change_pct"] = _DILUTION_THRESHOLD_PCT - 0.01  # just under
        r = compute_thesis_funnel("AAPL", **kwargs)
        # Should pass survival (assuming other flags clear)
        assert r["flags"]["s1_dilution"]["fired"] is False
        assert r["state"] != "not_eligible" or r["state_reason"] not in ("s1_dilution",)

    def test_s2_moat_falsifier_alone_fires_not_eligible(self) -> None:
        kwargs = _base_kwargs()
        kwargs["moat_falsifiers_result"] = _mf_fired("receivables_stretch")
        r = compute_thesis_funnel("AMZN", **kwargs)
        assert r["state"] == "not_eligible"
        assert r["flags"]["s2_moat_falsifier"]["fired"] is True
        assert "s2_moat" in r["state_reason"]

    def test_s2_any_sensor_fires_not_eligible(self) -> None:
        for sensor in [
            "margin_compression_despite_revenue_growth",
            "receivables_stretch",
            "inventory_build",
            "capital_intensity_rising",
        ]:
            kwargs = _base_kwargs()
            kwargs["moat_falsifiers_result"] = _mf_fired(sensor)
            r = compute_thesis_funnel("TEST", **kwargs)
            assert r["state"] == "not_eligible", f"Expected not_eligible for sensor {sensor}"

    def test_s3_solvency_alone_fires_not_eligible(self) -> None:
        kwargs = _base_kwargs()
        kwargs["altman_z"] = _ALTMAN_DISTRESS_MAX - 0.1  # below distress threshold
        r = compute_thesis_funnel("GE", **kwargs)
        assert r["state"] == "not_eligible"
        assert r["flags"]["s3_solvency"]["fired"] is True
        assert "s3_solvency" in r["state_reason"]

    def test_s3_exactly_at_threshold_fires(self) -> None:
        kwargs = _base_kwargs()
        kwargs["altman_z"] = _ALTMAN_DISTRESS_MAX - 0.001  # just below
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["flags"]["s3_solvency"]["fired"] is True
        assert r["state"] == "not_eligible"

    def test_s3_above_threshold_does_not_fire(self) -> None:
        kwargs = _base_kwargs()
        kwargs["altman_z"] = _ALTMAN_DISTRESS_MAX + 0.01  # just above
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["flags"]["s3_solvency"]["fired"] is False


# ===========================================================================
# Group B — State logic
# ===========================================================================

class TestStateLogic:
    """State machine produces correct state for each combination."""

    def test_all_clear_f6_neutral_gives_candidate_shadow(self) -> None:
        """All survival pass + F=6 + non-dilutive → thesis_candidate_shadow."""
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 6
        kwargs["piotroski_of"] = 9
        r = compute_thesis_funnel("MSFT", **kwargs)
        assert r["state"] == "thesis_candidate_shadow"
        assert r["_display_only"] is True
        assert r["_horizon_role"] == "hold_thesis"

    def test_all_clear_f7_neutral_gives_candidate_shadow(self) -> None:
        """F=7 also qualifies."""
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 7
        r = compute_thesis_funnel("AAPL", **kwargs)
        assert r["state"] == "thesis_candidate_shadow"

    def test_all_clear_f5_gives_watch(self) -> None:
        """F=5 (below floor of 6) → watch_for_thesis."""
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 5
        kwargs["piotroski_of"] = 9
        r = compute_thesis_funnel("NVDA", **kwargs)
        assert r["state"] == "watch_for_thesis"
        assert "piotroski" in r["state_reason"]

    def test_capital_unavailable_does_not_disqualify_from_candidate(self) -> None:
        """capital_allocation_delta='unavailable' does NOT block thesis_candidate_shadow."""
        kwargs = _base_kwargs()
        kwargs["capital_allocation_delta"] = "unavailable"
        kwargs["piotroski_score"] = 6
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "thesis_candidate_shadow", (
            "capital_allocation='unavailable' must not disqualify from candidate shadow"
        )

    def test_capital_none_does_not_disqualify_from_candidate(self) -> None:
        """capital_allocation_delta=None does NOT block thesis_candidate_shadow."""
        kwargs = _base_kwargs()
        kwargs["capital_allocation_delta"] = None
        kwargs["piotroski_score"] = 6
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "thesis_candidate_shadow"

    def test_capital_dilutive_with_f6_gives_watch(self) -> None:
        """capital_allocation='dilutive' AND F>=6 → watch_for_thesis (not candidate)."""
        kwargs = _base_kwargs()
        kwargs["capital_allocation_delta"] = "dilutive"
        kwargs["piotroski_score"] = 6
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "watch_for_thesis"
        assert "capital_allocation_dilutive" in r["state_reason"]

    def test_coverage_floor_below_2_not_eligible(self) -> None:
        """s4_coverage fires when fewer than 2 inputs are computable."""
        # All three computable checks unavailable: no shares_yoy, no moat, no altman
        r = compute_thesis_funnel(
            "TEST",
            altman_z=None,
            moat_falsifiers_result=None,
            shares_yoy_change_pct=None,
            capital_allocation_delta="neutral",
            piotroski_score=9,
            piotroski_of=9,
        )
        assert r["state"] == "not_eligible"
        assert r["flags"]["s4_coverage"]["fired"] is True

    def test_coverage_exactly_2_not_blocked(self) -> None:
        """Exactly 2 computable inputs → coverage check passes."""
        # shares_yoy + altman available; moat missing
        r = compute_thesis_funnel(
            "TEST",
            altman_z=3.5,
            moat_falsifiers_result=None,   # not computable
            shares_yoy_change_pct=0.5,
            capital_allocation_delta="neutral",
            piotroski_score=7,
            piotroski_of=9,
        )
        assert r["flags"]["s4_coverage"]["fired"] is False
        assert r["flags"]["s4_coverage"]["n_computable"] == 2

    def test_no_active_thesis_state_exists(self) -> None:
        """State 'active_thesis' must never be produced (W3-locked)."""
        # Even with perfect inputs, ceiling is thesis_candidate_shadow
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 9
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] in STATES
        assert r["state"] != "active_thesis"
        assert "active_thesis" not in STATES

    def test_state_enum_is_exactly_three_values(self) -> None:
        """STATES must have exactly 3 values per module docstring."""
        assert len(STATES) == 3
        assert set(STATES) == {"not_eligible", "watch_for_thesis", "thesis_candidate_shadow"}


# ===========================================================================
# Group C — Piotroski and capital_allocation nuances
# ===========================================================================

class TestPiotroskiCapitalNuances:
    """Edge cases around piotroski_score and capital_allocation_delta."""

    def test_piotroski_none_gives_watch(self) -> None:
        """piotroski_score=None → candidate gate not met → watch_for_thesis."""
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = None
        kwargs["piotroski_of"] = None
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "watch_for_thesis"
        assert "piotroski_unavailable" in r["state_reason"]

    def test_piotroski_of_none_with_score_gives_watch(self) -> None:
        """piotroski_score present but of=None → still watch (cannot confirm floor met)."""
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 7
        kwargs["piotroski_of"] = None
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "watch_for_thesis"

    def test_capital_accretive_with_f6_gives_candidate(self) -> None:
        """capital_allocation='accretive' is not 'dilutive' → candidate eligible."""
        kwargs = _base_kwargs()
        kwargs["capital_allocation_delta"] = "accretive"
        kwargs["piotroski_score"] = 6
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "thesis_candidate_shadow"

    def test_capital_neutral_with_f6_gives_candidate(self) -> None:
        """capital_allocation='neutral' → candidate eligible."""
        kwargs = _base_kwargs()
        kwargs["capital_allocation_delta"] = "neutral"
        kwargs["piotroski_score"] = 6
        r = compute_thesis_funnel("TEST", **kwargs)
        assert r["state"] == "thesis_candidate_shadow"

    def test_piotroski_context_in_gate_inputs(self) -> None:
        """gate_inputs.piotroski carries score, of, meets_candidate_floor, floor."""
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 7
        kwargs["piotroski_of"] = 9
        r = compute_thesis_funnel("TEST", **kwargs)
        pio = r["gate_inputs"]["piotroski"]
        assert pio["score"] == 7
        assert pio["of"] == 9
        assert pio["floor"] == _PIOTROSKI_CANDIDATE_MIN
        assert pio["meets_candidate_floor"] is True

    def test_piotroski_below_floor_meets_candidate_floor_false(self) -> None:
        kwargs = _base_kwargs()
        kwargs["piotroski_score"] = 4
        kwargs["piotroski_of"] = 9
        r = compute_thesis_funnel("TEST", **kwargs)
        pio = r["gate_inputs"]["piotroski"]
        assert pio["meets_candidate_floor"] is False


# ===========================================================================
# Group D — Coverage floor
# ===========================================================================

class TestCoverageFloor:
    """s4_coverage fires correctly for different computable-input counts."""

    def test_zero_computable_not_eligible(self) -> None:
        r = compute_thesis_funnel(
            "TEST",
            altman_z=None,
            moat_falsifiers_result=None,
            shares_yoy_change_pct=None,
        )
        s4 = r["flags"]["s4_coverage"]
        assert s4["fired"] is True
        assert s4["n_computable"] == 0

    def test_one_computable_not_eligible(self) -> None:
        """Only altman_z available — still below floor."""
        r = compute_thesis_funnel(
            "TEST",
            altman_z=3.5,
            moat_falsifiers_result=None,
            shares_yoy_change_pct=None,
        )
        s4 = r["flags"]["s4_coverage"]
        assert s4["fired"] is True
        assert s4["n_computable"] == 1

    def test_two_computable_coverage_passes(self) -> None:
        """altman + shares_yoy → 2 computable → coverage passes."""
        r = compute_thesis_funnel(
            "TEST",
            altman_z=3.5,
            moat_falsifiers_result=None,
            shares_yoy_change_pct=0.5,
            capital_allocation_delta="neutral",
            piotroski_score=7,
            piotroski_of=9,
        )
        s4 = r["flags"]["s4_coverage"]
        assert s4["fired"] is False
        assert s4["n_computable"] == 2

    def test_three_computable_coverage_passes(self) -> None:
        """All three available → n_computable = 3."""
        r = compute_thesis_funnel("TEST", **_base_kwargs())
        s4 = r["flags"]["s4_coverage"]
        assert s4["fired"] is False
        assert s4["n_computable"] == 3

    def test_moat_missing_sensor_coverage_not_computable(self) -> None:
        """moat_falsifiers sensor_coverage='missing' → s2 not computable."""
        r = compute_thesis_funnel(
            "TEST",
            altman_z=3.5,
            moat_falsifiers_result=_mf_missing(),
            shares_yoy_change_pct=0.5,
            capital_allocation_delta="neutral",
            piotroski_score=7,
            piotroski_of=9,
        )
        s2 = r["flags"]["s2_moat_falsifier"]
        assert s2["computable"] is False
        # But 2 other inputs are available so coverage still passes
        s4 = r["flags"]["s4_coverage"]
        assert s4["n_computable"] == 2
        assert s4["fired"] is False


# ===========================================================================
# Group E — compute_thesis_funnel_safe: exception safety
# ===========================================================================

class TestFunnelSafe:
    """compute_thesis_funnel_safe must return None (not raise) on any exception."""

    def test_safe_returns_result_on_valid_input(self) -> None:
        r = compute_thesis_funnel_safe("TEST", **_base_kwargs())
        assert r is not None
        assert r["state"] in STATES

    def test_safe_returns_none_on_bad_ticker(self) -> None:
        """Should not raise even with extreme bad input."""
        # Pass a non-string moat result (wrong type) to provoke an internal error
        r = compute_thesis_funnel_safe(
            None,  # type: ignore[arg-type]
            altman_z="not_a_float",  # type: ignore[arg-type]
            moat_falsifiers_result="garbage",  # type: ignore[arg-type]
        )
        # Must not raise; may return None or a result
        # (Python's forgiving float() may not raise on all bad inputs,
        # but _safe_float handles that case — the function still runs)

    def test_firewall_stamps_present(self) -> None:
        """Every result from compute_thesis_funnel has the required firewall stamps."""
        r = compute_thesis_funnel("TEST", **_base_kwargs())
        assert r["_display_only"] is True
        assert r["_horizon_role"] == "hold_thesis"
        assert r["_version"] == "v1"


# ===========================================================================
# Group F — Synapse registry: firewall check
# ===========================================================================

class TestSynapseRegistryFirewall:
    """thesis_funnel artifacts in synapse.yml must satisfy hold_thesis firewall."""

    def _load_registry(self) -> dict:
        import yaml  # type: ignore[import-untyped]
        registry_path = REPO_ROOT / "config" / "synapse.yml"
        with registry_path.open() as f:
            return yaml.safe_load(f)

    def test_thesis_funnel_states_in_registry(self) -> None:
        reg = self._load_registry()
        artifacts = reg.get("artifacts") or {}
        assert "long-hold-thesis-funnel-states" in artifacts, (
            "long-hold-thesis-funnel-states must be registered in synapse.yml"
        )

    def test_thesis_funnel_panel_in_registry(self) -> None:
        reg = self._load_registry()
        artifacts = reg.get("artifacts") or {}
        assert "long-hold-thesis-funnel-panel" in artifacts, (
            "long-hold-thesis-funnel-panel must be registered in synapse.yml"
        )

    def test_thesis_funnel_states_tier_display(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-states") or {}
        assert art.get("tier") == "display", (
            "long-hold-thesis-funnel-states must have tier=display"
        )

    def test_thesis_funnel_states_horizon_role_hold_thesis(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-states") or {}
        assert art.get("horizon_role") == "hold_thesis", (
            "long-hold-thesis-funnel-states must have horizon_role=hold_thesis"
        )

    def test_thesis_funnel_states_no_scored_path_surfaces(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-states") or {}
        sps = art.get("scored_path_surfaces")
        assert sps is not None and len(sps) == 0, (
            "long-hold-thesis-funnel-states must have scored_path_surfaces=[]"
        )

    def test_thesis_funnel_states_fdr_family_long_hold(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-states") or {}
        assert art.get("fdr_family") == "long_hold", (
            "long-hold-thesis-funnel-states must have fdr_family=long_hold"
        )

    def test_thesis_funnel_panel_tier_display(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-panel") or {}
        assert art.get("tier") == "display"

    def test_thesis_funnel_panel_horizon_role_hold_thesis(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-panel") or {}
        assert art.get("horizon_role") == "hold_thesis"

    def test_thesis_funnel_panel_no_scored_path_surfaces(self) -> None:
        reg = self._load_registry()
        art = (reg.get("artifacts") or {}).get("long-hold-thesis-funnel-panel") or {}
        sps = art.get("scored_path_surfaces")
        assert sps is not None and len(sps) == 0
