"""Contract tests for ``mastermind.macro_workspace_snapshot.v1`` (F01 / R1A).

Self-contained: builds every fixture from a plain dict, reads only the committed
schema and the composer. No parquet, no network. Runnable standalone:

    python3 -m pytest tests/test_macro_workspace_contract.py -x -q
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import contract, liquidity_regime  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"


def _base_regime() -> dict:
    return {
        "asof": "2026-09-03", "date": "2026-09-03",
        "liquidity_overlay": "contracting",
        "liquidity_quality": {
            "asof": "2026-09-03", "label": "contracting", "quantity_roc_bn": -165.3,
            "rrp_buffer_bn": 6.7, "rrp_exhausted": True,
            "composition": {"mechanical": True},
            "stress_overlay": {"confirming_stress": False, "hy_oas_z": -0.2, "hy_oas_pct": 2.66},
            "walcl_stale_days": 1, "degraded": False,
        },
        "conditions": {
            "stale_inputs": [],
            "vintages": {
                "nfci": {"asof": "2026-08-28", "stale": False},
                "ofr_fsi": {"asof": "2026-08-30", "stale": False},
                "hy_oas": {"asof": "2026-09-02", "stale": False},
            },
            "financial_conditions": {"nfci": -0.558, "nfci_pctile": 0.046},
            "systemic_stress": {"ofr_fsi": -2.749, "ofr_fsi_pctile": 0.0278},
        },
        "regime_vector": {"rate_pressure_rates_scare_score": 43.2,
                          "rate_pressure_real10y_chg63_bp": 24.0},
    }


def _sealed(regime: dict, **kw) -> dict:
    body = liquidity_regime.compose(regime, built_at=BUILT_AT, **kw)
    return contract.finalize(body)


# --------------------------------------------------------------------------- #
# schema shape
# --------------------------------------------------------------------------- #
def test_schema_is_valid_draft_2020_12_and_closed_everywhere() -> None:
    schema = contract.load_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema"]["properties"]["contract"]["const"] == contract.CONTRACT_ID
    assert schema["properties"]["schema"]["properties"]["version"]["const"] == contract.CONTRACT_VERSION

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, node.get("properties", {}).keys()
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)


def test_schema_has_the_eighteen_closed_top_level_blocks() -> None:
    schema = contract.load_schema()
    required = set(schema["required"])
    assert required == {
        "schema", "workspace", "region", "generation", "authority", "availability",
        "headline", "axes", "metrics", "series", "drivers", "changes", "implications",
        "scenario_contract", "alert_contract", "sources", "corrections", "learning",
    }


# --------------------------------------------------------------------------- #
# seal + validate
# --------------------------------------------------------------------------- #
def test_finalize_then_validate_roundtrips() -> None:
    snap = _sealed(_base_regime())
    contract.validate(snap)  # must not raise
    gen = snap["generation"]
    assert len(gen["content_sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in gen["content_sha256"])
    assert gen["generation_id"].startswith("liquidity_regime-US-")
    assert snap["authority"]["can_gate"] is False
    assert snap["authority"]["axis_authority_ceiling"] == "DESCRIPTIVE"


def test_deterministic_digest_on_identical_input() -> None:
    a = _sealed(_base_regime())
    b = _sealed(_base_regime())
    assert a["generation"]["content_sha256"] == b["generation"]["content_sha256"]
    assert a["generation"]["generation_id"] == b["generation"]["generation_id"]


def test_digest_is_independent_of_built_at() -> None:
    a = contract.finalize(liquidity_regime.compose(_base_regime(), built_at="2026-09-04T00:00:00Z"))
    b = contract.finalize(liquidity_regime.compose(_base_regime(), built_at="2026-09-04T23:59:59Z"))
    # only built_at differs -> content digest must be identical
    assert a["generation"]["content_sha256"] == b["generation"]["content_sha256"]
    assert a["generation"]["built_at"] != b["generation"]["built_at"]


def test_digest_changes_when_owner_input_changes() -> None:
    a = _sealed(_base_regime())
    other = _base_regime()
    other["liquidity_quality"]["quantity_roc_bn"] = 250.0  # real data change
    b = _sealed(other)
    assert a["generation"]["content_sha256"] != b["generation"]["content_sha256"]


# --------------------------------------------------------------------------- #
# fail-closed
# --------------------------------------------------------------------------- #
def test_unknown_top_level_key_fails_closed() -> None:
    snap = _sealed(_base_regime())
    snap["surprise_block"] = {"x": 1}
    with pytest.raises(contract.ContractError):
        contract.validate(snap, check_hash=False)


def test_unsupported_schema_version_fails_closed() -> None:
    snap = _sealed(_base_regime())
    snap["schema"]["version"] = "2.0.0"
    with pytest.raises(contract.ContractError):
        contract.validate(snap, check_hash=False)


def test_unknown_contract_id_fails_closed() -> None:
    snap = _sealed(_base_regime())
    snap["schema"]["contract"] = "mastermind.some_other_contract.v1"
    with pytest.raises(contract.ContractError):
        contract.validate(snap, check_hash=False)


def test_content_hash_mismatch_fails_closed() -> None:
    snap = _sealed(_base_regime())
    snap["headline"]["effective_date"] = "1999-01-01"  # tamper after sealing
    with pytest.raises(contract.ContractError):
        contract.validate(snap, check_hash=True)


def test_unsealed_placeholder_digest_is_rejected() -> None:
    body = liquidity_regime.compose(_base_regime(), built_at=BUILT_AT)
    assert body["generation"]["content_sha256"] == "0" * 64
    with pytest.raises(contract.ContractError):
        contract.validate(body, check_hash=True)


def test_workspace_id_is_from_the_closed_registry() -> None:
    # The schema enum and the registry tuple are the SAME closed vocabulary —
    # cross-pinned so neither can drift without the other (was a bare ==12
    # count; widened 2026-09-04 when the Chairman-authorized expansion added
    # rates_curves as the 13th id — the F01 twelve stay frozen, expansion ids
    # append).
    from engine.market_os.macro_workspaces import registry
    snap = _sealed(_base_regime())
    schema = contract.load_schema()
    allowed = set(schema["$defs"]["workspaceId"]["enum"])
    assert snap["workspace"]["id"] in allowed
    assert allowed == set(registry.WORKSPACE_IDS)
    assert len(allowed) == 13
