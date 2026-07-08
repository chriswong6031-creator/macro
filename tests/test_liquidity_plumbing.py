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
    from engine.neuralweb.liquidity_plumbing import compute  # noqa: F401
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
    _FUNDING_NULL_KEYS = [
        "effr_minus_iorb_bp",
        "sofr_minus_iorb_bp",
        "srf_takeup_bn",
        "discount_window_primary_credit_bn",
    ]

    def test_funding_fields_all_null(self):
        """All funding numeric fields must be null in Phase 1 (no data source yet)."""
        result = _full_compute()
        funding = result["funding"]
        for key in self._FUNDING_NULL_KEYS:
            assert key in funding, f"funding block missing key {key!r}"
            assert funding[key] is None, (
                f"funding.{key} must be null in Phase 1, got {funding[key]!r}"
            )

    def test_funding_reserve_scarcity_state(self):
        """funding.reserve_scarcity_state must equal 'unknown' in Phase 1."""
        result = _full_compute()
        assert result["funding"]["reserve_scarcity_state"] == "unknown"

    def test_gaps_mentions_funding(self):
        """gaps[] must include a note about funding scarcity spreads not being integrated."""
        result = _full_compute()
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert "funding" in gaps_text or "phase 3" in gaps_text, (
            f"gaps must mention funding scarcity spreads not integrated; got: {result['gaps']}"
        )


# ---------------------------------------------------------------------------
# 13. Foreign dollar block — all fields null (Phase 1)
# ---------------------------------------------------------------------------

class TestForeignDollarBlockNull:
    def test_swap_lines_null(self):
        """foreign_dollar.swap_lines_bn must be null in Phase 1."""
        result = _full_compute()
        assert result["foreign_dollar"]["swap_lines_bn"] is None

    def test_fima_repo_null(self):
        """foreign_dollar.fima_repo_bn must be null in Phase 1."""
        result = _full_compute()
        assert result["foreign_dollar"]["fima_repo_bn"] is None

    def test_foreign_dollar_state(self):
        """foreign_dollar.state must equal 'not_integrated_yet'."""
        result = _full_compute()
        assert result["foreign_dollar"]["state"] == "not_integrated_yet"

    def test_gaps_mentions_foreign_dollar(self):
        """gaps[] must include a note about H.4.1 swap/FIMA not being integrated."""
        result = _full_compute()
        gaps_text = " ".join(str(g) for g in result["gaps"]).lower()
        assert any(
            term in gaps_text for term in ("swap", "fima", "h.4.1", "foreign", "phase 5")
        ), (
            f"gaps must mention H.4.1 swap/FIMA not integrated; got: {result['gaps']}"
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
        """fed.reserve_balances_bn must be null in Phase 1 (H.4.1 not integrated)."""
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
