"""tests/test_liquidity_plumbing.py — Contract tests for neuralweb.liquidity_plumbing.v1

Tests are authored against the FROZEN CONTRACT in .liq_plumbing_contract.md.
All inputs are SYNTHETIC and deterministic — no live nightly data dependency.
The engine module (engine/neuralweb/liquidity_plumbing.py) is being built in a
parallel lane; these tests target the contract shape and will be run at
integration time once the engine module lands.

Coverage:
  1.  top_level_schema_keys        — all required top-level keys are present
  2.  authority_constants           — score_raise=False, exact constant values
  3.  headline_benign_expansion     — benign-expansion → benign_liquidity_tailwind
  4.  headline_stress_expansion_rrp — stress-expansion + rrp_exhausted → stress_liquidity_expansion
  5.  headline_mechanical           — stress-expansion + fed_share<0.5 + !rrp_exhausted → mechanical_liquidity_tailwind
  6.  headline_neutral              — neutral overlay → neutral_with_buffer
  7.  headline_neutral_hollow       — neutral-hollow quality → neutral_hollow
  8.  headline_contracting          — contracting overlay → orderly_drain
  9.  headline_unknown_degraded     — unknown quality / degraded flag → data_degraded
  10. fail_open_missing_netliq       — missing netliq source → gaps[] entry, still valid dict
  11. fail_open_missing_regime       — missing regime_latest source → gaps[] entry, still valid dict
  12. funding_block_null             — all funding fields are null
  13. foreign_dollar_block_null      — all foreign_dollar fields are null
  14. no_validated_word              — serialized output contains no "validated"
  15. forbidden_states               — Phase-1 forbidden headline states never fire
  16. quantity_block_keys            — quantity block has required keys
  17. quality_block_keys             — quality block has required keys
  18. rrp_block_keys                 — rrp block has required keys
  19. fed_block_keys                 — fed block has required keys
  20. treasury_block_keys            — treasury block has required keys
  21. entry_effect_block             — entry_effect block present with correct non-score keys
  22. gaps_is_list                   — gaps key is a list

Phase-3 robust-readout coverage (funding spreads + components + reserves +
stress-overlay carry-through — additive to schema v1):
  23. spread_helpers                 — _to_series/_spread_bp/_level_d20_pctile known values
  24. reserve_scarcity_state         — descriptive-vocabulary derivation table
  25. funding_spreads_compute        — synthetic funding frames → known bp levels/deltas/pctiles
  26. components_block               — walcl/rrp/tga {level,d20,d65,pctile} + netliq sparkline
  27. reserve_balances               — WRESBAL frame consumed (incl. millions guard); fail-open null
  28. quality_stress_overlay         — regime stress_overlay dict carried through, bool tolerated
  29. phase_status                   — additive integration-status field present
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

# Ensure the project root is on sys.path so the import resolves even when pytest
# is invoked from a worktree directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Import target — the engine module being built in parallel.
# If the engine module does not yet exist, every test in this file is skipped
# with a clear message rather than erroring with ImportError.
# ---------------------------------------------------------------------------

try:
    from engine.neuralweb.liquidity_plumbing import (  # noqa: F401
        _derive_reserve_scarcity_state,
        _derive_tga_impulse,
        _level_d20_pctile,
        _spread_bp,
        _to_series,
        compute,
    )
    _ENGINE_AVAILABLE = True
except ImportError:
    _ENGINE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ENGINE_AVAILABLE,
    reason="engine.neuralweb.liquidity_plumbing not yet built — authoring only",
)


# ---------------------------------------------------------------------------
# Synthetic fixtures — hand-built regime_latest dicts + tiny fake pandas frames
# ---------------------------------------------------------------------------

def _regime_latest(
    *,
    quality_label: str = "benign-expansion",
    rrp_buffer_bn: float = 200.0,
    rrp_exhausted: bool = False,
    fed_share: float = 0.8,
    mechanical: bool = False,
    stress_overlay: bool = False,
    walcl_stale_days: int = 1,
    degraded: bool = False,
    overlay: str = "expanding",
    financial_conditions: str = "accommodative",
    systemic_stress: str = "low",
    fed_stance: str = "neutral",
    administered_rate_posture: str | None = None,
) -> dict:
    """Build a minimal deterministic regime_latest dict matching the contract sources."""
    return {
        "liquidity_quality": {
            "label": quality_label,
            "rrp_buffer_bn": rrp_buffer_bn,
            "rrp_exhausted": rrp_exhausted,
            "composition": {
                "d_walcl": 50.0,
                "d_neg_rrp": 30.0,
                "d_neg_tga": 20.0,
                "fed_share": fed_share,
                "mechanical": mechanical,
            },
            "stress_overlay": stress_overlay,
            "walcl_stale_days": walcl_stale_days,
            "degraded": degraded,
        },
        "liquidity_overlay": overlay,
        "fed_stance": {
            "stance": fed_stance,
            "administered_rate_posture": administered_rate_posture,
        },
        "conditions": {
            "financial_conditions": financial_conditions,
            "systemic_stress": systemic_stress,
        },
    }


def _netliq_frame(n: int = 10) -> pd.DataFrame:
    """Tiny deterministic netliq DataFrame matching the data/macro/fed_net_liquidity.parquet schema."""
    dates = pd.bdate_range("2026-06-01", periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "netliq_bn": [6000.0 + i * 5 for i in range(n)],
            "walcl_bn": [7500.0 + i * 5 for i in range(n)],
            "rrp_bn": [200.0 - i * 2 for i in range(n)],
            "tga_bn": [800.0 + i * 1 for i in range(n)],
            "netliq_d20": [float(i * 5) if i >= 20 else None for i in range(n)],
            "netliq_d65": [float(i * 5) if i >= 65 else None for i in range(n)],
            "netliq_pctile_expanding": [0.5 + i * 0.01 for i in range(n)],
        }
    )


def _treasury_frames() -> dict[str, pd.DataFrame]:
    """Tiny deterministic treasury DataFrames."""
    dates = pd.bdate_range("2026-06-01", periods=5)
    net_issuance = pd.DataFrame(
        {
            "date": dates,
            "net_issuance_20d_bn": [50.0] * 5,
        }
    )
    tga = pd.DataFrame(
        {
            "date": dates,
            "tga_bn": [800.0] * 5,
            "tga_chg_20d_bn": [-10.0] * 5,
        }
    )
    return {"net_issuance": net_issuance, "tga": tga}


def _auction_snapshot() -> dict:
    """Minimal auction context snapshot."""
    return {
        "asof": "2026-06-30",
        "recent_auctions": [],
        "absorption_note": "context_only",
    }


def _config() -> dict:
    """Minimal config dict."""
    return {}


# ---------------------------------------------------------------------------
# Helper: call compute() with full synthetic inputs
# ---------------------------------------------------------------------------

def _full_compute(regime_kwargs: dict[str, Any] | None = None) -> dict:
    """Run compute() with deterministic synthetic inputs."""
    regime = _regime_latest(**(regime_kwargs or {}))
    netliq = _netliq_frame()
    tframes = _treasury_frames()
    auctions = _auction_snapshot()
    cfg = _config()
    return compute(regime, netliq, tframes, auctions, cfg)


# ---------------------------------------------------------------------------
# 1. Top-level schema keys — all required keys present
# ---------------------------------------------------------------------------

class TestTopLevelSchemaKeys:
    _REQUIRED_KEYS = [
        "schema",
        "asof",
        "authority",
        "headline",
        "fed",
        "treasury",
        "rrp",
        "quantity",
        "quality",
        "funding",
        "foreign_dollar",
        "entry_effect",
        "gaps",
        "degraded",
    ]

    def test_all_required_keys_present(self):
        """Every top-level key from the v1 schema must be present in compute() output."""
        result = _full_compute()
        for key in self._REQUIRED_KEYS:
            assert key in result, f"Missing required top-level key: {key!r}"

    def test_schema_value(self):
        """schema must equal 'neuralweb.liquidity_plumbing.v1'."""
        result = _full_compute()
        assert result["schema"] == "neuralweb.liquidity_plumbing.v1"

    def test_asof_is_date_string(self):
        """asof must be a YYYY-MM-DD string."""
        result = _full_compute()
        assert isinstance(result["asof"], str)
        assert len(result["asof"]) == 10
        assert result["asof"][4] == "-" and result["asof"][7] == "-"

    def test_degraded_is_bool(self):
        """degraded must be a bool."""
        result = _full_compute()
        assert isinstance(result["degraded"], bool)


# ---------------------------------------------------------------------------
# 2. Authority constants — score_raise=False, exact contract values
# ---------------------------------------------------------------------------

class TestAuthorityConstants:
    def test_score_raise_is_false(self):
        """authority.score_raise must be False — DE-ESCALATION only."""
        result = _full_compute()
        auth = result["authority"]
        assert auth["score_raise"] is False, (
            "authority.score_raise must be False; lobe is DE-ESCALATION ONLY"
        )

    def test_entry_tailwind_value(self):
        """authority.entry_tailwind must equal 'measured_near_term_only'."""
        result = _full_compute()
        assert result["authority"]["entry_tailwind"] == "measured_near_term_only"

    def test_score_lower_value(self):
        """authority.score_lower must equal the contract string."""
        result = _full_compute()
        assert result["authority"]["score_lower"] == (
            "buy_setup_caution_only_where_existing_engine_allows"
        )

    def test_explain_true(self):
        """authority.explain must be True."""
        result = _full_compute()
        assert result["authority"]["explain"] is True

    def test_attend_true(self):
        """authority.attend must be True."""
        result = _full_compute()
        assert result["authority"]["attend"] is True

    def test_deescalate_true(self):
        """authority.deescalate must be True."""
        result = _full_compute()
        assert result["authority"]["deescalate"] is True

    def test_hard_gate_false(self):
        """authority.hard_gate must be False."""
        result = _full_compute()
        assert result["authority"]["hard_gate"] is False


# ---------------------------------------------------------------------------
# 3-9. headline.state derivation — contract derivation table
# ---------------------------------------------------------------------------

class TestHeadlineStateDerivation:
    """Exercise every branch of the headline.state derivation table from the contract."""

    def test_benign_expansion(self):
        """benign-expansion quality label → benign_liquidity_tailwind."""
        result = _full_compute({
            "quality_label": "benign-expansion",
            "overlay": "expanding",
            "rrp_exhausted": False,
            "fed_share": 0.8,
            "mechanical": False,
            "degraded": False,
        })
        assert result["headline"]["state"] == "benign_liquidity_tailwind", (
            f"Expected benign_liquidity_tailwind, got {result['headline']['state']!r}"
        )

    def test_stress_expansion_rrp_exhausted(self):
        """stress-expansion + rrp_exhausted → stress_liquidity_expansion."""
        result = _full_compute({
            "quality_label": "stress-expansion",
            "overlay": "expanding",
            "rrp_exhausted": True,
            "fed_share": 0.8,
            "mechanical": False,
            "stress_overlay": True,
            "degraded": False,
        })
        assert result["headline"]["state"] == "stress_liquidity_expansion", (
            f"Expected stress_liquidity_expansion, got {result['headline']['state']!r}"
        )

    def test_stress_expansion_stress_confirming(self):
        """stress-expansion + stress_confirming → stress_liquidity_expansion (stress_overlay path)."""
        result = _full_compute({
            "quality_label": "stress-expansion",
            "overlay": "expanding",
            "rrp_exhausted": False,
            "fed_share": 0.8,
            "mechanical": False,
            "stress_overlay": True,   # stress_confirming = True via stress_overlay
            "degraded": False,
        })
        assert result["headline"]["state"] == "stress_liquidity_expansion", (
            f"Expected stress_liquidity_expansion (stress_overlay path), "
            f"got {result['headline']['state']!r}"
        )

    def test_mechanical_tailwind(self):
        """stress-expansion + fed_share<0.5 + !rrp_exhausted → mechanical_liquidity_tailwind."""
        result = _full_compute({
            "quality_label": "stress-expansion",
            "overlay": "expanding",
            "rrp_exhausted": False,
            "fed_share": 0.35,   # < 0.5 → mechanical
            "mechanical": True,
            "stress_overlay": False,
            "degraded": False,
        })
        assert result["headline"]["state"] == "mechanical_liquidity_tailwind", (
            f"Expected mechanical_liquidity_tailwind, got {result['headline']['state']!r}"
        )

    def test_neutral_with_buffer(self):
        """neutral quality → neutral_with_buffer."""
        result = _full_compute({
            "quality_label": "neutral",
            "overlay": "neutral",
            "rrp_exhausted": False,
            "fed_share": 0.7,
            "mechanical": False,
            "degraded": False,
        })
        assert result["headline"]["state"] == "neutral_with_buffer", (
            f"Expected neutral_with_buffer, got {result['headline']['state']!r}"
        )

    def test_neutral_hollow(self):
        """neutral-hollow quality → neutral_hollow."""
        result = _full_compute({
            "quality_label": "neutral-hollow",
            "overlay": "neutral",
            "rrp_exhausted": False,
            "fed_share": 0.6,
            "mechanical": False,
            "degraded": False,
        })
        assert result["headline"]["state"] == "neutral_hollow", (
            f"Expected neutral_hollow, got {result['headline']['state']!r}"
        )

    def test_contracting(self):
        """contracting overlay → orderly_drain."""
        result = _full_compute({
            "quality_label": "contracting",
            "overlay": "contracting",
            "rrp_exhausted": False,
            "fed_share": 0.7,
            "mechanical": False,
            "degraded": False,
        })
        assert result["headline"]["state"] == "orderly_drain", (
            f"Expected orderly_drain, got {result['headline']['state']!r}"
        )

    def test_unknown_label(self):
        """unknown quality label → data_degraded."""
        result = _full_compute({
            "quality_label": "unknown",
            "overlay": "unknown",
            "rrp_exhausted": False,
            "fed_share": 0.6,
            "mechanical": False,
            "degraded": False,
        })
        assert result["headline"]["state"] == "data_degraded", (
            f"Expected data_degraded for unknown quality, got {result['headline']['state']!r}"
        )

    def test_degraded_flag(self):
        """degraded=True → data_degraded regardless of quality label."""
        result = _full_compute({
            "quality_label": "benign-expansion",
            "overlay": "expanding",
            "rrp_exhausted": False,
            "fed_share": 0.8,
            "mechanical": False,
            "degraded": True,   # override — forces data_degraded
        })
        assert result["headline"]["state"] == "data_degraded", (
            f"Expected data_degraded when degraded=True, got {result['headline']['state']!r}"
        )

    def test_headline_has_summary(self):
        """headline.summary must be a non-empty string."""
        result = _full_compute()
        summary = result["headline"].get("summary")
        assert isinstance(summary, str) and len(summary) > 0, (
            "headline.summary must be a non-empty string"
        )


# ---------------------------------------------------------------------------
# 10-11. Fail-open — missing sources → gaps[] entries + still-valid dict
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_missing_netliq_source_adds_gap(self):
        """compute() with None netliq_frame → gaps entry, still valid dict."""
        regime = _regime_latest()
        tframes = _treasury_frames()
        # Pass None as the netliq frame to simulate a missing data source.
        result = compute(regime, None, tframes, _auction_snapshot(), _config())
        assert isinstance(result, dict), "compute() must return a dict even with missing netliq"
        assert "gaps" in result
        assert isinstance(result["gaps"], list)
        # At least one gap entry must mention the missing source
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert any(
            term in gaps_text for term in ("netliq", "net_liquidity", "fed_net_liquidity")
        ), f"gaps must mention missing netliq source; got: {result['gaps']}"

    def test_missing_netliq_result_is_valid_schema(self):
        """compute() with None netliq_frame → output still has all top-level keys."""
        regime = _regime_latest()
        result = compute(regime, None, _treasury_frames(), _auction_snapshot(), _config())
        required_keys = [
            "schema", "asof", "authority", "headline",
            "fed", "treasury", "rrp", "quantity", "quality",
            "funding", "foreign_dollar", "entry_effect", "gaps", "degraded",
        ]
        for key in required_keys:
            assert key in result, f"Fail-open: missing key {key!r} with missing netliq"

    def test_missing_regime_source_adds_gap(self):
        """compute() with None regime_latest → gaps entry, still valid dict."""
        netliq = _netliq_frame()
        tframes = _treasury_frames()
        result = compute(None, netliq, tframes, _auction_snapshot(), _config())
        assert isinstance(result, dict), "compute() must return a dict even with missing regime"
        assert "gaps" in result
        assert isinstance(result["gaps"], list)
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert any(
            term in gaps_text for term in ("regime", "latest", "quality")
        ), f"gaps must mention missing regime source; got: {result['gaps']}"

    def test_missing_regime_result_is_valid_schema(self):
        """compute() with None regime_latest → output still has all top-level keys."""
        netliq = _netliq_frame()
        result = compute(None, netliq, _treasury_frames(), _auction_snapshot(), _config())
        required_keys = [
            "schema", "asof", "authority", "headline",
            "fed", "treasury", "rrp", "quantity", "quality",
            "funding", "foreign_dollar", "entry_effect", "gaps", "degraded",
        ]
        for key in required_keys:
            assert key in result, f"Fail-open: missing key {key!r} with missing regime"

    def test_never_raises(self):
        """compute() must never raise — fail-open law."""
        bad_inputs = [
            (None, None, None, None, None),
            ({}, pd.DataFrame(), {}, {}, {}),
            ("not_a_dict", _netliq_frame(), _treasury_frames(), _auction_snapshot(), _config()),
        ]
        for args in bad_inputs:
            try:
                result = compute(*args)
                assert isinstance(result, dict), f"compute() must return a dict for inputs {args!r}"
            except Exception as exc:
                pytest.fail(
                    f"compute() raised {type(exc).__name__}: {exc} — fail-open law violated; "
                    f"inputs: {args!r}"
                )


# ---------------------------------------------------------------------------
# 12. Funding block — all fields null (Phase 1)
# ---------------------------------------------------------------------------

class TestFundingBlockNull:
    """Fail-open: with NO funding frames supplied, every spread nulls out."""

    _FUNDING_NULL_KEYS = [
        "effr_minus_iorb_bp",
        "sofr_minus_iorb_bp",
        "sofr_99pctl_minus_iorb_bp",
        "srf_takeup_bn",
        "discount_window_primary_credit_bn",
    ]

    def test_funding_fields_all_null(self):
        """All funding numeric fields must be null when no funding frames are passed."""
        result = _full_compute()
        funding = result["funding"]
        for key in self._FUNDING_NULL_KEYS:
            assert key in funding, f"funding block missing key {key!r}"
            assert funding[key] is None, (
                f"funding.{key} must be null without funding inputs, got {funding[key]!r}"
            )

    def test_funding_reserve_scarcity_state(self):
        """funding.reserve_scarcity_state must equal 'unknown' without funding inputs."""
        result = _full_compute()
        assert result["funding"]["reserve_scarcity_state"] == "unknown"

    def test_gaps_mentions_funding(self):
        """gaps[] must note the missing funding spread inputs."""
        result = _full_compute()
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert "funding" in gaps_text or "iorb" in gaps_text, (
            f"gaps must mention missing funding spread inputs; got: {result['gaps']}"
        )

    def test_gaps_mentions_srf_discount_window(self):
        """gaps[] must always note that SRF/discount-window are not collected yet."""
        result = _full_compute()
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert "srf" in gaps_text and "discount" in gaps_text, (
            f"gaps must mention SRF/discount-window pending collection; got: {result['gaps']}"
        )


# ---------------------------------------------------------------------------
# 13. Foreign dollar block — Phase-5 integrated (IRD-W1); swap_frames absent
#     path → state=data_unavailable; swap_frames present path tested in #30.
# ---------------------------------------------------------------------------

class TestForeignDollarBlockNull:
    """When swap_frames=None (absent), swap_lines_bn and facility_loans_bn must be
    null and state must reflect the absence.  fima_repo_bn is permanently null
    (no free per-facility breakout — IRD-R5)."""

    def test_swap_lines_null_when_no_frames(self):
        """foreign_dollar.swap_lines_bn must be null when swap_frames absent."""
        result = _full_compute()
        assert result["foreign_dollar"]["swap_lines_bn"] is None

    def test_facility_loans_null_when_no_frames(self):
        """foreign_dollar.facility_loans_bn must be null when swap_frames absent."""
        result = _full_compute()
        assert result["foreign_dollar"]["facility_loans_bn"] is None

    def test_fima_repo_permanently_null(self):
        """foreign_dollar.fima_repo_bn must be null (no free per-facility breakout)."""
        result = _full_compute()
        assert result["foreign_dollar"]["fima_repo_bn"] is None

    def test_foreign_dollar_state_data_unavailable(self):
        """foreign_dollar.state must equal 'data_unavailable' when swap_frames absent."""
        result = _full_compute()
        assert result["foreign_dollar"]["state"] == "data_unavailable"

    def test_gaps_mentions_swap(self):
        """gaps[] must include a note about SWPT parquet missing when no frames given."""
        result = _full_compute()
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert any(
            term in gaps_text for term in ("swpt", "swap", "swap_lines_bn")
        ), (
            f"gaps must mention SWPT/swap unavailable; got: {result['gaps']}"
        )


# ---------------------------------------------------------------------------
# 14. No "validated" word in serialized output
# ---------------------------------------------------------------------------

class TestNoValidatedWord:
    def test_validated_absent_benign(self):
        """'validated' must not appear in output for benign-expansion case."""
        result = _full_compute({"quality_label": "benign-expansion"})
        json_str = json.dumps(result, ensure_ascii=False, default=str)
        assert "validated" not in json_str.lower(), (
            "Output contains the word 'validated' — CI-guarded epistemics law"
        )

    def test_validated_absent_contracting(self):
        """'validated' must not appear in output for contracting case."""
        result = _full_compute({
            "quality_label": "contracting",
            "overlay": "contracting",
        })
        json_str = json.dumps(result, ensure_ascii=False, default=str)
        assert "validated" not in json_str.lower(), (
            "Output contains the word 'validated' — CI-guarded epistemics law"
        )

    def test_validated_absent_degraded(self):
        """'validated' must not appear in output for degraded case."""
        result = _full_compute({"degraded": True})
        json_str = json.dumps(result, ensure_ascii=False, default=str)
        assert "validated" not in json_str.lower(), (
            "Output contains the word 'validated' — CI-guarded epistemics law"
        )


# ---------------------------------------------------------------------------
# 15. Forbidden headline states — Phase-1 states that must never fire
# ---------------------------------------------------------------------------

class TestForbiddenStates:
    """reserve_scarcity_warning and foreign_dollar_stress must never fire in Phase 1."""

    _FORBIDDEN_STATES = {"reserve_scarcity_warning", "foreign_dollar_stress"}

    def _assert_not_forbidden(self, result: dict) -> None:
        state = result["headline"]["state"]
        assert state not in self._FORBIDDEN_STATES, (
            f"Forbidden headline.state {state!r} fired in Phase 1 — "
            "funding/foreign-dollar data is not integrated yet"
        )

    def test_benign_no_forbidden(self):
        self._assert_not_forbidden(_full_compute({"quality_label": "benign-expansion"}))

    def test_stress_no_forbidden(self):
        self._assert_not_forbidden(_full_compute({
            "quality_label": "stress-expansion",
            "rrp_exhausted": True,
        }))

    def test_degraded_no_forbidden(self):
        self._assert_not_forbidden(_full_compute({"degraded": True}))

    def test_neutral_no_forbidden(self):
        self._assert_not_forbidden(_full_compute({"quality_label": "neutral", "overlay": "neutral"}))


# ---------------------------------------------------------------------------
# 16-20. Block key presence
# ---------------------------------------------------------------------------

class TestQuantityBlockKeys:
    _REQUIRED = ["netliq_bn", "netliq_chg_20d_bn", "netliq_chg_65d_bn",
                 "netliq_pctile_expanding", "overlay"]

    def test_quantity_block_has_required_keys(self):
        result = _full_compute()
        q = result["quantity"]
        for key in self._REQUIRED:
            assert key in q, f"quantity block missing key {key!r}"

    def test_overlay_value_in_known_set(self):
        result = _full_compute()
        assert result["quantity"]["overlay"] in (
            "expanding", "contracting", "neutral", "unknown"
        )


class TestQualityBlockKeys:
    _REQUIRED = ["label", "fed_share", "mechanical", "stress_confirming"]

    def test_quality_block_has_required_keys(self):
        result = _full_compute()
        q = result["quality"]
        for key in self._REQUIRED:
            assert key in q, f"quality block missing key {key!r}"

    def test_mechanical_is_bool_or_null(self):
        result = _full_compute()
        val = result["quality"]["mechanical"]
        assert val is None or isinstance(val, bool), (
            f"quality.mechanical must be bool or null, got {val!r}"
        )


class TestRrpBlockKeys:
    _REQUIRED = ["rrp_bn", "rrp_chg_20d_bn", "buffer_state"]
    _VALID_BUFFER_STATES = {"abundant", "adequate", "exhausted", "unknown"}

    def test_rrp_block_has_required_keys(self):
        result = _full_compute()
        r = result["rrp"]
        for key in self._REQUIRED:
            assert key in r, f"rrp block missing key {key!r}"

    def test_buffer_state_in_known_set(self):
        result = _full_compute()
        assert result["rrp"]["buffer_state"] in self._VALID_BUFFER_STATES, (
            f"rrp.buffer_state must be one of {self._VALID_BUFFER_STATES}"
        )


class TestFedBlockKeys:
    _REQUIRED = ["assets_bn", "assets_chg_20d_bn", "reserve_balances_bn",
                 "walcl_stale_days", "policy_stance", "administered_rate_posture", "asof"]

    def test_fed_block_has_required_keys(self):
        result = _full_compute()
        f = result["fed"]
        for key in self._REQUIRED:
            assert key in f, f"fed block missing key {key!r}"

    def test_reserve_balances_null(self):
        """fed.reserve_balances_bn must be null when no WRESBAL frame is passed."""
        result = _full_compute()
        assert result["fed"]["reserve_balances_bn"] is None


class TestTreasuryBlockKeys:
    _REQUIRED = ["tga_bn", "tga_chg_20d_bn", "net_issuance_20d_bn",
                 "expected_tga_pressure", "coupon_supply_pressure", "asof"]

    def test_treasury_block_has_required_keys(self):
        result = _full_compute()
        t = result["treasury"]
        for key in self._REQUIRED:
            assert key in t, f"treasury block missing key {key!r}"

    def test_expected_tga_pressure_value(self):
        """treasury.expected_tga_pressure must equal the contract sentinel string."""
        result = _full_compute()
        assert result["treasury"]["expected_tga_pressure"] == (
            "unknown_until_financing_estimates_parser"
        )

    def test_coupon_supply_pressure_value(self):
        """treasury.coupon_supply_pressure must equal 'context_only'."""
        result = _full_compute()
        assert result["treasury"]["coupon_supply_pressure"] == "context_only"


# ---------------------------------------------------------------------------
# 21. entry_effect block — contract keys, no score origination
# ---------------------------------------------------------------------------

class TestEntryEffectBlock:
    _REQUIRED = ["direction", "quality", "measured_basis", "use"]
    _VALID_DIRECTIONS = {"tailwind", "headwind", "neutral", "unknown"}
    _VALID_QUALITIES = {"benign", "low_quality_tailwind", "neutral", "contraction", "unknown"}

    def test_entry_effect_has_required_keys(self):
        result = _full_compute()
        ee = result["entry_effect"]
        for key in self._REQUIRED:
            assert key in ee, f"entry_effect missing key {key!r}"

    def test_measured_basis_value(self):
        """entry_effect.measured_basis must equal 'cycle_ladder_21d_odds'."""
        result = _full_compute()
        assert result["entry_effect"]["measured_basis"] == "cycle_ladder_21d_odds"

    def test_direction_in_known_set(self):
        result = _full_compute()
        assert result["entry_effect"]["direction"] in self._VALID_DIRECTIONS

    def test_quality_in_known_set(self):
        result = _full_compute()
        assert result["entry_effect"]["quality"] in self._VALID_QUALITIES

    def test_use_mentions_existing_setup(self):
        """entry_effect.use must mention 'existing' buy setup — not origination."""
        result = _full_compute()
        use_str = result["entry_effect"]["use"].lower()
        assert "existing" in use_str, (
            f"entry_effect.use must reference 'existing' setup to enforce non-origination; "
            f"got {result['entry_effect']['use']!r}"
        )


# ---------------------------------------------------------------------------
# 22. gaps is a list
# ---------------------------------------------------------------------------

class TestGapsIsList:
    def test_gaps_is_list_benign(self):
        result = _full_compute({"quality_label": "benign-expansion"})
        assert isinstance(result["gaps"], list)

    def test_gaps_is_list_degraded(self):
        result = _full_compute({"degraded": True})
        assert isinstance(result["gaps"], list)

    def test_gaps_is_list_missing_inputs(self):
        result = compute(None, None, None, None, None)
        assert isinstance(result["gaps"], list)

    def test_gaps_entries_are_strings(self):
        """All gaps entries must be strings (for display consumption)."""
        result = _full_compute()
        for entry in result["gaps"]:
            assert isinstance(entry, str), (
                f"gaps entries must be strings, got {type(entry).__name__}: {entry!r}"
            )


# ---------------------------------------------------------------------------
# Phase-3 robust readout — synthetic funding / components / reserves fixtures
# ---------------------------------------------------------------------------

def _funding_frames(n: int = 300) -> dict[str, pd.DataFrame]:
    """Deterministic single-column rate frames mirroring the real parquet shapes.

    IORB flat at 4.40. EFFR at 4.33 (−7bp) then 4.36 (−4bp) for the last 20
    rows — a +3bp 20d drift. SOFR flat at 4.35 (−5bp). SOFR-99pctl flat at
    4.50 (+10bp).
    """
    dates = pd.bdate_range("2025-01-01", periods=n)
    k = min(20, n)
    effr_vals = [4.33] * (n - k) + [4.36] * k
    return {
        "effr": pd.DataFrame({"effr": effr_vals}, index=dates),
        "iorb": pd.DataFrame({"iorb": [4.40] * n}, index=dates),
        "sofr": pd.DataFrame({"sofr": [4.35] * n}, index=dates),
        "sofr_p99": pd.DataFrame({"sofr_p99": [4.50] * n}, index=dates),
    }


def _reserves_frame(n: int = 30, base: float = 3300.0) -> pd.DataFrame:
    """Deterministic WRESBAL-shaped frame ($bn weekly, rising +1/wk)."""
    dates = pd.date_range("2026-01-07", periods=n, freq="7D")
    return pd.DataFrame({"reserve_balances": [base + i for i in range(n)]}, index=dates)


# ---------------------------------------------------------------------------
# 23. Spread helpers — known values on synthetic series
# ---------------------------------------------------------------------------

class TestSpreadHelpers:
    def test_to_series_datetime_index(self):
        frames = _funding_frames(10)
        s = _to_series(frames["iorb"])
        assert s is not None and len(s) == 10
        assert float(s.iloc[-1]) == 4.40

    def test_to_series_date_column(self):
        """Frames with a 'date' column (netliq parquet style) also normalize."""
        df = pd.DataFrame({"date": pd.bdate_range("2026-01-01", periods=5),
                           "v": [1.0, 2.0, 3.0, 4.0, 5.0]})
        s = _to_series(df)
        assert s is not None and float(s.iloc[-1]) == 5.0

    def test_to_series_none_and_empty(self):
        assert _to_series(None) is None
        assert _to_series(pd.DataFrame()) is None

    def test_spread_bp_known_value(self):
        frames = _funding_frames(50)
        sp = _spread_bp(_to_series(frames["sofr"]), _to_series(frames["iorb"]))
        assert sp is not None
        assert round(float(sp.iloc[-1]), 2) == -5.0

    def test_spread_bp_alignment_intersection_only(self):
        """Spread must use intersecting dates only (EFFR publishes T+1 vs IORB)."""
        frames = _funding_frames(50)
        effr_short = frames["effr"].iloc[:-2]  # EFFR lags two sessions
        sp = _spread_bp(_to_series(effr_short), _to_series(frames["iorb"]))
        assert sp is not None
        assert sp.index[-1] == effr_short.index[-1]

    def test_spread_bp_none_inputs(self):
        assert _spread_bp(None, _to_series(_funding_frames(5)["iorb"])) is None
        assert _spread_bp(_to_series(_funding_frames(5)["effr"]), None) is None

    def test_level_d20_pctile_known_values(self):
        frames = _funding_frames(300)
        sp = _spread_bp(_to_series(frames["effr"]), _to_series(frames["iorb"]))
        level, d20, pctile = _level_d20_pctile(sp)
        assert level == -4.0
        assert d20 == 3.0          # −4bp now vs −7bp 20 rows ago
        assert pctile == 1.0       # latest is the joint-highest of the history

    def test_level_d20_pctile_short_series(self):
        """≤ 20 rows → level + pctile present, d20 null."""
        frames = _funding_frames(10)
        sp = _spread_bp(_to_series(frames["sofr"]), _to_series(frames["iorb"]))
        level, d20, pctile = _level_d20_pctile(sp)
        assert level == -5.0
        assert d20 is None
        assert pctile == 1.0

    def test_level_d20_pctile_empty(self):
        assert _level_d20_pctile(None) == (None, None, None)
        assert _level_d20_pctile(pd.Series(dtype=float)) == (None, None, None)


# ---------------------------------------------------------------------------
# 24. reserve_scarcity_state derivation — descriptive vocabulary only
# ---------------------------------------------------------------------------

class TestReserveScarcityState:
    _VALID = {"comfortable", "normalizing", "tightening", "scarce", "unknown"}

    def test_unknown_when_no_levels(self):
        assert _derive_reserve_scarcity_state(None, None, None, None) == "unknown"

    def test_scarce_effr_at_iorb(self):
        """EFFR at/above IORB (Sep-2019 signature) → scarce."""
        assert _derive_reserve_scarcity_state(1.0, -5.0, 2.0, 0.0) == "scarce"

    def test_scarce_sofr_squeeze(self):
        """SOFR ≥ +10bp over IORB (repo squeeze) → scarce."""
        assert _derive_reserve_scarcity_state(-6.0, 12.0, 0.0, 8.0) == "scarce"

    def test_tightening_both_near_iorb(self):
        """Both EFFR and SOFR within 5bp below IORB → tightening."""
        assert _derive_reserve_scarcity_state(-4.0, -5.0, 3.0, 0.0) == "tightening"

    def test_normalizing_effr_near_iorb_only(self):
        """EFFR compressed but SOFR still comfortably below → normalizing."""
        assert _derive_reserve_scarcity_state(-4.0, -8.0, 0.0, 0.0) == "normalizing"

    def test_normalizing_on_drift(self):
        """Levels comfortable but spreads drifting up ≥ +2bp / 20d → normalizing."""
        assert _derive_reserve_scarcity_state(-8.0, -8.0, 3.0, 0.0) == "normalizing"

    def test_comfortable(self):
        assert _derive_reserve_scarcity_state(-8.0, -8.0, 0.0, -1.0) == "comfortable"

    def test_vocabulary_is_frozen(self):
        """Every reachable output is inside the frozen descriptive vocabulary."""
        cases = [
            (None, None, None, None), (1.0, -5.0, 0.0, 0.0),
            (-4.0, -5.0, 0.0, 0.0), (-4.0, -8.0, 0.0, 0.0),
            (-8.0, -8.0, 3.0, 0.0), (-8.0, -8.0, 0.0, 0.0),
            (None, -8.0, None, 0.0), (-8.0, None, 0.0, None),
        ]
        for args in cases:
            assert _derive_reserve_scarcity_state(*args) in self._VALID, args


# ---------------------------------------------------------------------------
# 25. Funding spreads through compute() — synthetic frames, known values
# ---------------------------------------------------------------------------

class TestFundingSpreadsCompute:
    def _result(self, frames: dict | None = None) -> dict:
        return compute(
            _regime_latest(), _netliq_frame(), _treasury_frames(),
            _auction_snapshot(), _config(),
            funding_frames=frames if frames is not None else _funding_frames(),
        )

    def test_known_spread_levels(self):
        f = self._result()["funding"]
        assert f["effr_minus_iorb_bp"] == -4.0
        assert f["sofr_minus_iorb_bp"] == -5.0
        assert f["sofr_99pctl_minus_iorb_bp"] == 10.0

    def test_known_20d_deltas(self):
        f = self._result()["funding"]
        assert f["effr_minus_iorb_d20_bp"] == 3.0
        assert f["sofr_minus_iorb_d20_bp"] == 0.0
        assert f["sofr_99pctl_minus_iorb_d20_bp"] == 0.0

    def test_expanding_percentiles(self):
        f = self._result()["funding"]
        assert f["effr_minus_iorb_pctile"] == 1.0
        assert f["sofr_minus_iorb_pctile"] == 1.0
        assert f["sofr_99pctl_minus_iorb_pctile"] == 1.0

    def test_scarcity_state_derived(self):
        """−4bp EFFR + −5bp SOFR (both within 5bp of IORB) → tightening."""
        f = self._result()["funding"]
        assert f["reserve_scarcity_state"] == "tightening"

    def test_funding_asof(self):
        frames = _funding_frames()
        f = self._result(frames)["funding"]
        assert f["asof"] == str(frames["iorb"].index[-1].date())

    def test_srf_discount_window_stay_null(self):
        f = self._result()["funding"]
        assert f["srf_takeup_bn"] is None
        assert f["discount_window_primary_credit_bn"] is None

    def test_partial_inputs_fail_open(self):
        """Missing SOFR → SOFR fields null + gap, other spreads intact."""
        frames = _funding_frames()
        frames["sofr"] = None
        result = self._result(frames)
        f = result["funding"]
        assert f["sofr_minus_iorb_bp"] is None
        assert f["effr_minus_iorb_bp"] == -4.0
        gaps_text = " ".join(result["gaps"]).lower()
        assert "sofr.parquet" in gaps_text

    def test_missing_iorb_nulls_everything(self):
        frames = _funding_frames()
        frames["iorb"] = None
        result = self._result(frames)
        f = result["funding"]
        assert f["effr_minus_iorb_bp"] is None
        assert f["sofr_minus_iorb_bp"] is None
        assert f["reserve_scarcity_state"] == "unknown"
        gaps_text = " ".join(result["gaps"]).lower()
        assert "iorb" in gaps_text

    def test_no_validated_word_with_funding(self):
        result = self._result()
        assert "validated" not in json.dumps(result, default=str).lower()


# ---------------------------------------------------------------------------
# 26. Components block — per-component stats + netliq sparkline
# ---------------------------------------------------------------------------

class TestComponentsBlock:
    def _result(self) -> dict:
        # n=100 → d20 and d65 both computable (need > 65 rows)
        return compute(
            _regime_latest(), _netliq_frame(100), _treasury_frames(),
            _auction_snapshot(), _config(),
        )

    def test_component_keys_present(self):
        comps = self._result()["components"]
        for comp in ("walcl", "rrp", "tga"):
            for key in ("level_bn", "d20_bn", "d65_bn", "pctile"):
                assert key in comps[comp], f"components.{comp} missing {key!r}"

    def test_walcl_known_values(self):
        """walcl_bn = 7500 + 5i → level 7995, d20 = +100, d65 = +325, pctile 1.0."""
        w = self._result()["components"]["walcl"]
        assert w["level_bn"] == 7995.0
        assert w["d20_bn"] == 100.0
        assert w["d65_bn"] == 325.0
        assert w["pctile"] == 1.0

    def test_rrp_known_values(self):
        """rrp_bn = 200 − 2i → level 2, d20 = −40, d65 = −130, pctile = 1/100."""
        r = self._result()["components"]["rrp"]
        assert r["level_bn"] == 2.0
        assert r["d20_bn"] == -40.0
        assert r["d65_bn"] == -130.0
        assert r["pctile"] == 0.01

    def test_tga_known_values(self):
        """tga_bn = 800 + i → level 899, d20 = +20, d65 = +65."""
        t = self._result()["components"]["tga"]
        assert t["level_bn"] == 899.0
        assert t["d20_bn"] == 20.0
        assert t["d65_bn"] == 65.0

    def test_sparkline_shape_and_window(self):
        result = self._result()
        spark = result["components"]["netliq_sparkline_90d"]
        assert isinstance(spark, list) and len(spark) > 0
        for pt in spark:
            assert set(pt.keys()) == {"d", "v"}
            assert isinstance(pt["d"], str) and isinstance(pt["v"], float)
        # last point equals the latest netliq level; window is ≤ 90 calendar days
        assert spark[-1]["v"] == 6495.0
        first = pd.Timestamp(spark[0]["d"])
        last = pd.Timestamp(spark[-1]["d"])
        assert (last - first).days <= 90

    def test_short_frame_nulls_deltas_keeps_levels(self):
        """10-row frame → levels + pctile present, d20/d65 null (honest nulls)."""
        result = compute(
            _regime_latest(), _netliq_frame(10), _treasury_frames(),
            _auction_snapshot(), _config(),
        )
        w = result["components"]["walcl"]
        assert w["level_bn"] is not None
        assert w["d20_bn"] is None and w["d65_bn"] is None

    def test_missing_netliq_fails_open(self):
        result = compute(
            _regime_latest(), None, _treasury_frames(),
            _auction_snapshot(), _config(),
        )
        comps = result["components"]
        assert comps["walcl"]["level_bn"] is None
        assert comps["netliq_sparkline_90d"] == []
        gaps_text = " ".join(result["gaps"]).lower()
        assert "components" in gaps_text or "fed_net_liquidity" in gaps_text


# ---------------------------------------------------------------------------
# 27. Reserve balances (WRESBAL) — consumed when present, fail-open when not
# ---------------------------------------------------------------------------

class TestReserveBalances:
    def test_reserves_consumed(self):
        result = compute(
            _regime_latest(), _netliq_frame(100), _treasury_frames(),
            _auction_snapshot(), _config(),
            reserves_frame=_reserves_frame(),
        )
        assert result["fed"]["reserve_balances_bn"] == 3329.0
        assert "reserves" in result["components"]
        assert result["components"]["reserves"]["level_bn"] == 3329.0

    def test_reserves_millions_guard(self):
        """A millions-denominated WRESBAL store (WALCL-style) normalizes to $bn."""
        frame = _reserves_frame(base=3_300_000.0)
        result = compute(
            _regime_latest(), _netliq_frame(), _treasury_frames(),
            _auction_snapshot(), _config(),
            reserves_frame=frame,
        )
        assert result["fed"]["reserve_balances_bn"] == 3300.029

    def test_reserves_absent_fail_open(self):
        result = _full_compute()
        assert result["fed"]["reserve_balances_bn"] is None
        assert "reserves" not in result["components"]
        gaps_text = " ".join(result["gaps"]).lower()
        assert "wresbal" in gaps_text


# ---------------------------------------------------------------------------
# 28. Quality block — stress overlay carried through
# ---------------------------------------------------------------------------

class TestQualityStressOverlay:
    _OVERLAY_KEYS = {"hy_oas_pct", "hy_oas_z", "nfci", "nfci_trend", "confirming_stress"}

    def test_dict_overlay_carried_through(self):
        """The real regime stress_overlay dict must survive into quality.stress_overlay."""
        regime = _regime_latest()
        regime["liquidity_quality"]["stress_overlay"] = {
            "confirming_stress": False,
            "hy_oas_pct": 2.7,
            "hy_oas_chg_20d": -0.01,
            "hy_oas_z": 0.03,
            "nfci": -0.515,
            "nfci_trend": "loose",
        }
        result = compute(regime, _netliq_frame(), _treasury_frames(),
                         _auction_snapshot(), _config())
        so = result["quality"]["stress_overlay"]
        assert set(so.keys()) == self._OVERLAY_KEYS
        assert so["hy_oas_pct"] == 2.7
        assert so["hy_oas_z"] == 0.03
        assert so["nfci"] == -0.515
        assert so["nfci_trend"] == "loose"
        assert so["confirming_stress"] is False

    def test_bool_overlay_tolerated(self):
        """Synthetic bool stress_overlay → confirming_stress set, detail keys null."""
        result = _full_compute({"stress_overlay": True})
        so = result["quality"]["stress_overlay"]
        assert so["confirming_stress"] is True
        for k in ("hy_oas_pct", "hy_oas_z", "nfci", "nfci_trend"):
            assert so[k] is None

    def test_missing_overlay_all_null(self):
        regime = _regime_latest()
        del regime["liquidity_quality"]["stress_overlay"]
        result = compute(regime, _netliq_frame(), _treasury_frames(),
                         _auction_snapshot(), _config())
        so = result["quality"]["stress_overlay"]
        assert all(so[k] is None for k in self._OVERLAY_KEYS)

    def test_walcl_stale_days_in_quality(self):
        result = _full_compute({"walcl_stale_days": 4})
        assert result["quality"]["walcl_stale_days"] == 4
        # fed block copy stays (template renders it today)
        assert result["fed"]["walcl_stale_days"] == 4


# ---------------------------------------------------------------------------
# 29. phase_status — additive integration-status field
# ---------------------------------------------------------------------------

class TestPhaseStatus:
    def test_phase_status_present(self):
        result = _full_compute()
        ps = result["phase_status"]
        assert ps["p3_funding_spreads"] == "integrated"
        assert ps["p3_srf_discount_window"] == "pending_collection"
        # Phase-5: p5_swap_fima renamed to two keys after IRD-W1 integration
        assert ps["p5_swap_lines"] == "integrated_ird_w1"
        assert ps["p5_fima_repo"] == "pending_no_free_breakout"

    def test_schema_still_v1(self):
        """phase_status is additive — schema string must NOT bump."""
        result = _full_compute()
        assert result["schema"] == "neuralweb.liquidity_plumbing.v1"


# ---------------------------------------------------------------------------
# 30. Swap-lines integration (IRD-W1 Phase-5) — synthetic SWPT/WLCFLL frames
# ---------------------------------------------------------------------------

def _swap_frame(vals_millions: list[float], label: str) -> pd.DataFrame:
    """Build a minimal SWPT/WLCFLL-shaped frame (weekly, $M column matching alias)."""
    dates = pd.bdate_range("2026-06-01", periods=len(vals_millions), freq="W-FRI")
    return pd.DataFrame({label: vals_millions}, index=dates)


class TestSwapLinesIntegration:
    """compute() with swap_frames provided should populate foreign_dollar fields.

    IRD-R5: swap-line levels are CONFIRMATION tier only — state label is
    informational, never triggers alerts.  fima_repo_bn is permanently null.
    """

    def test_elevated_draw_state(self):
        """swap_lines_bn > 100 → state == 'elevated_draw'."""
        swpt = _swap_frame([150_000.0], "swap_lines_tot")   # $150B in $M units
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt},
        )
        fd = result["foreign_dollar"]
        assert fd["swap_lines_bn"] == pytest.approx(150.0, abs=1e-2)
        assert fd["state"] == "elevated_draw"
        assert fd["fima_repo_bn"] is None

    def test_low_draw_state(self):
        """1 < swap_lines_bn <= 100 → state == 'low_draw'."""
        swpt = _swap_frame([50_000.0], "swap_lines_tot")    # $50B
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt},
        )
        fd = result["foreign_dollar"]
        assert fd["swap_lines_bn"] == pytest.approx(50.0, abs=1e-2)
        assert fd["state"] == "low_draw"

    def test_quiescent_state(self):
        """swap_lines_bn == 0 → state == 'quiescent'."""
        swpt = _swap_frame([0.0], "swap_lines_tot")
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt},
        )
        fd = result["foreign_dollar"]
        assert fd["swap_lines_bn"] == pytest.approx(0.0, abs=1e-3)
        assert fd["state"] == "quiescent"

    def test_quiescent_standing_residual(self):
        """Sub-$1bn standing balance (routine FX ops, e.g. SWPT=$170M live
        2026-07-12) is quiescent, not a draw — IRD-R5 no-cry-wolf floor."""
        swpt = _swap_frame([170.0], "swap_lines_tot")   # $170M
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt},
        )
        fd = result["foreign_dollar"]
        assert fd["swap_lines_bn"] == pytest.approx(0.17, abs=1e-2)
        assert fd["state"] == "quiescent"

    def test_facility_loans_populated(self):
        """facility_loans_bn set when WLCFLL frame present."""
        swpt = _swap_frame([20_000.0], "swap_lines_tot")
        wlcfll = _swap_frame([5_000.0], "fed_facility_loans")
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt, "fed_facility_loans": wlcfll},
        )
        fd = result["foreign_dollar"]
        assert fd["facility_loans_bn"] == pytest.approx(5.0, abs=1e-2)
        assert fd["fima_repo_bn"] is None

    def test_swpt_present_wlcfll_absent_gap(self):
        """When only SWPT provided, facility_loans_bn null and gap logged."""
        swpt = _swap_frame([30_000.0], "swap_lines_tot")
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt},
        )
        fd = result["foreign_dollar"]
        assert fd["facility_loans_bn"] is None
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert "wlcfll" in gaps_text or "facility_loans" in gaps_text, (
            f"gaps must mention WLCFLL absent; got: {result['gaps']}"
        )

    def test_no_alert_trigger(self):
        """Elevated swap lines must NOT change headline to a forbidden state."""
        swpt = _swap_frame([500_000.0], "swap_lines_tot")   # extreme value
        result = compute(
            _regime_latest(),
            _netliq_frame(),
            _treasury_frames(),
            _auction_snapshot(),
            _config(),
            swap_frames={"swap_lines_tot": swpt},
        )
        # IRD-R5: swap lines are confirmation only — headline driven by regime
        assert result["headline"]["state"] not in ("foreign_dollar_stress",)
        assert result["authority"]["score_raise"] is False


# ---------------------------------------------------------------------------
# 31. TGA impulse detector (RLT-R4) — _derive_tga_impulse unit tests
# ---------------------------------------------------------------------------

def _tga_series_bn(
    values: list[float],
    start: str = "2026-06-01",
) -> pd.Series:
    """Build a business-daily TGA series (values in $bn) for impulse testing."""
    dates = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=dates)


def _jun_jul_2026_tga() -> pd.Series:
    """Reproduce the Jun 30 → Jul 9 2026 TGA drawdown shape (from masterplan §0).

    Jun-30 ~919bn → Jul-9 ~745bn is ~$174bn drawdown over ~7 business days.
    We build a series with a flat pre-period (May) then a sharp drawdown in Jul.
    """
    # 40 business days starting 2026-05-01
    dates = pd.bdate_range("2026-05-01", periods=40)
    vals = [900.0] * 22 + [919.1] + [880.0, 850.0, 807.4, 770.6, 760.0, 744.6] + [744.6] * 10
    # Trim to 40 rows
    vals = vals[:40]
    return pd.Series(vals, index=dates[:len(vals)])


class TestTgaImpulseUnit:
    """Unit tests for _derive_tga_impulse (RLT-R4) using synthetic series."""

    def test_null_input_returns_inactive(self):
        result = _derive_tga_impulse(None)
        assert result["active"] is False
        assert result["direction"] is None
        assert result["magnitude_bn"] is None

    def test_empty_series_returns_inactive(self):
        result = _derive_tga_impulse(pd.Series(dtype=float))
        assert result["active"] is False

    def test_sub_threshold_null(self):
        """A move of only $50bn should NOT trigger (< $75bn threshold)."""
        s = _tga_series_bn([900.0, 890.0, 870.0, 860.0, 855.0, 850.0])
        result = _derive_tga_impulse(s)
        assert result["active"] is False

    def test_fast_drawdown_episode(self):
        """$175bn drawdown over 9 business sessions triggers the fast-episode rule."""
        # Start at 919, drop to 744 over 9 sessions (>= $75bn in <= 10 sessions)
        vals = [919.0, 900.0, 870.0, 840.0, 810.0, 790.0, 770.0, 760.0, 750.0, 744.0]
        s = _tga_series_bn(vals)
        result = _derive_tga_impulse(s)
        assert result["active"] is True
        assert result["direction"] == "drawdown"
        assert result["magnitude_bn"] >= 75.0
        assert result["days"] is not None and result["days"] <= 10
        assert result["since"] is not None

    def test_fast_build_episode(self):
        """$100bn build over 8 business sessions triggers the fast-episode rule."""
        vals = [700.0, 720.0, 740.0, 760.0, 780.0, 800.0, 810.0, 815.0, 800.0]
        s = _tga_series_bn(vals)
        result = _derive_tga_impulse(s)
        assert result["active"] is True
        assert result["direction"] == "build"
        assert result["magnitude_bn"] >= 75.0

    def test_direction_drawdown(self):
        """direction field must be 'drawdown' when TGA falls."""
        vals = [900.0] * 2 + [800.0] * 2 + [750.0] * 6
        s = _tga_series_bn(vals)
        result = _derive_tga_impulse(s)
        if result["active"]:
            assert result["direction"] == "drawdown"

    def test_quarter_end_adjacent_true(self):
        """Episode starting on Jun 30 or within 7 BD after should set quarter_end_adjacent=True."""
        # Jun 30 is the quarter end. Start series from Jun 30, show a big drawdown immediately.
        vals = [919.0, 880.0, 840.0, 800.0, 760.0, 744.0] + [744.0] * 4
        s = _tga_series_bn(vals, start="2026-06-30")
        result = _derive_tga_impulse(s)
        assert result["active"] is True
        assert result["quarter_end_adjacent"] is True

    def test_quarter_end_adjacent_false(self):
        """Fast-path episode well after a QE date: episode_start > 7 BD from last QE → not adjacent.

        QE-first ordering: the QE path checks cumulative from the last quarter-end.
        When the total move from last-QE to latest is < $120bn (QE path doesn't fire)
        but the most-recent 10 sessions show a ≥ $75bn move (fast path fires), and the
        fast episode_start is > 7 BD after the last QE, quarter_end_adjacent is False.

        Design: 30 BD starting 2026-05-04 (34 BD after Mar-31 QE). Stable at 900
        for 20 sessions then fast drop to 820 over 10 sessions (−80bn, ≥ $75bn fast
        threshold). Total from Mar-31 (last QE) = 900→820 = −80bn < $120bn → QE
        path does NOT fire. Fast path fires; episode_start ~2026-05-29 which is
        ~42 BD from Mar-31 → quarter_end_adjacent = False.
        """
        # 30 BD: stable at 900 for first 20, then drop 8bn/session for 10 sessions → 820
        base_vals = [900.0] * 20
        drop_vals = [892.0, 884.0, 876.0, 868.0, 860.0, 852.0, 844.0, 836.0, 828.0, 820.0]
        all_vals = base_vals + drop_vals
        s = _tga_series_bn(all_vals, start="2026-05-04")
        result = _derive_tga_impulse(s)
        # Fast episode should fire (−80bn ≥ $75bn threshold)
        assert result["active"] is True, "Expected fast episode to fire on −80bn drop"
        assert result["direction"] == "drawdown"
        # Mar-31 is ~34 BD before May-4; episode_start is ~May-29 (~46 BD from Mar-31) → not adjacent
        assert result["quarter_end_adjacent"] is False, (
            f"Expected quarter_end_adjacent=False for mid-May episode, got "
            f"since={result['since']}, qe_adj={result['quarter_end_adjacent']}"
        )

    def test_summary_en_is_nonempty_string(self):
        vals = [919.0, 880.0, 840.0, 800.0, 760.0, 744.0] + [744.0] * 4
        s = _tga_series_bn(vals, start="2026-06-30")
        result = _derive_tga_impulse(s)
        assert isinstance(result["summary_en"], str) and len(result["summary_en"]) > 10
        assert isinstance(result["summary_zh"], str) and len(result["summary_zh"]) > 5

    def test_no_validated_word_in_summary(self):
        """'validated' must not appear in any impulse summary (CI guard)."""
        vals = [919.0, 880.0, 840.0, 800.0, 760.0, 744.0] + [744.0] * 4
        s = _tga_series_bn(vals, start="2026-06-30")
        result = _derive_tga_impulse(s)
        assert "validated" not in result["summary_en"].lower()
        assert "validated" not in result["summary_zh"].lower()

    def test_impulse_block_keys(self):
        """All required keys must be present in the impulse block."""
        vals = [919.0, 880.0, 840.0, 800.0, 760.0, 744.0] + [744.0] * 4
        s = _tga_series_bn(vals, start="2026-06-30")
        result = _derive_tga_impulse(s)
        for key in ("active", "direction", "magnitude_bn", "days", "since",
                    "quarter_end_adjacent", "summary_en", "summary_zh"):
            assert key in result, f"tga_impulse missing key {key!r}"

    def test_impulse_in_treasury_block(self):
        """compute() must include tga_impulse sub-block in the treasury block."""
        result = _full_compute()
        t = result["treasury"]
        assert "tga_impulse" in t, "treasury block must contain tga_impulse key"
        imp = t["tga_impulse"]
        for key in ("active", "direction", "magnitude_bn", "days", "since",
                    "quarter_end_adjacent", "summary_en", "summary_zh"):
            assert key in imp, f"tga_impulse sub-block missing key {key!r}"

    def test_qe_anchored_episode_not_preempted_by_fast_path(self):
        """RLT-R4 VERIFY: Jun-30 QE episode must be preferred over a pre-QE fast anchor.

        Reproduces the scenario where the 10-BD trailing window spans before the
        quarter-end date, giving a truncated magnitude and quarter_end_adjacent=False.
        With QE-first ordering the QE path must be preferred, giving:
        - since = on or after Jun-30
        - quarter_end_adjacent = True
        - magnitude >= the QE-slice move (not truncated by the fast-path anchor)

        Series: 5 pre-QE rows (Jun-25 area) ending at 919, then Jun-30 at 919.1,
        then 8 post-QE rows declining to 744.6 (~$174.5bn from Jun-30).
        The 10-BD fast window spans from Jun-25 to Jul-9 (includes pre-QE values),
        so the old code would anchor at Jun-25 and report ~$127bn and adjacent=False.
        The fixed code must anchor at Jun-30 and report ~$174.5bn and adjacent=True.
        """
        # Build with explicit dates to control alignment precisely.
        # Jun-30 2026 is a Tuesday; bdate_range("2026-06-24") gives:
        #   Jun-24(1), Jun-25(2), Jun-26(3), Jun-29(4), Jun-30(5)=QE, Jul-1..Jul-9 (6..12)
        vals = [900.0, 910.0, 915.0, 919.0, 919.1,   # Jun-24..Jun-30 (QE spike)
                880.0, 850.0, 807.0, 771.0, 760.0, 745.0, 744.6]  # Jul-1..Jul-9
        s = _tga_series_bn(vals, start="2026-06-24")
        result = _derive_tga_impulse(s)
        assert result["active"] is True
        assert result["direction"] == "drawdown"
        # QE-anchored: first date ≥ Jun-30 is Jun-30 itself (919.1 → 744.6 = −174.5bn)
        assert result["magnitude_bn"] >= 120.0, (
            f"Expected QE-anchored magnitude >= $120bn, got {result['magnitude_bn']:.1f}bn "
            f"(since={result['since']}). Fast-path pre-emption bug not fixed."
        )
        assert result["quarter_end_adjacent"] is True, (
            f"Expected quarter_end_adjacent=True for Jun-30 anchor, got "
            f"since={result['since']}, adj={result['quarter_end_adjacent']}"
        )
        # since must be on or after Jun-30 (the QE anchor)
        import datetime as _dt
        since_date = _dt.date.fromisoformat(result["since"])
        assert since_date >= _dt.date(2026, 6, 30), (
            f"since={result['since']} should be on/after Jun-30 (QE anchor), not pre-QE"
        )


# ---------------------------------------------------------------------------
# 32. Phase-label fix (RLT-R4) — p3_reserve_balances reflects actual load state
# ---------------------------------------------------------------------------

class TestPhaseStatusDynamic:
    """p3_reserve_balances must reflect actual load state (not always fail-open string)."""

    def test_fail_open_when_no_reserves_frame(self):
        """Without WRESBAL, p3_reserve_balances must be the fail-open sentinel."""
        result = _full_compute()
        ps = result["phase_status"]
        assert ps["p3_reserve_balances"] == "fail_open_until_wresbal_collected", (
            f"Expected fail-open sentinel without reserves frame, got {ps['p3_reserve_balances']!r}"
        )

    def test_integrated_when_reserves_loaded(self):
        """With WRESBAL frame present, p3_reserve_balances must be 'integrated'."""
        reserves = _reserves_frame()
        result = compute(
            _regime_latest(), _netliq_frame(), _treasury_frames(),
            _auction_snapshot(), _config(),
            reserves_frame=reserves,
        )
        ps = result["phase_status"]
        assert ps["p3_reserve_balances"] == "integrated", (
            f"Expected 'integrated' with WRESBAL loaded, got {ps['p3_reserve_balances']!r}"
        )
