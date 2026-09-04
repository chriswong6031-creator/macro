"""Machine-consumer tests for the Macro workspace snapshot (F01 / R1A).

Asserts the bounded consumer is ACTIVE (owner-approved fields only, authority
all false) on good input and becomes INERT with a visible audit receipt on
malformed / hash-tampered / stale / unreadable input.

    python3 -m pytest tests/test_macro_workspace_consumer.py -x -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.market_os.macro_workspaces import consumer, contract, liquidity_regime  # noqa: E402

BUILT_AT = "2026-09-04T00:00:00Z"

_APPROVED_SUMMARY_KEYS = {
    "workspace", "region", "state_id", "state_label_en", "funding_pressure",
    "balance_sheet_support", "one_month_vector", "effective_date", "freshness",
    "coverage_ratio", "contradiction_present", "contradiction_kind", "method_version",
}


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
        "regime_vector": {"rate_pressure_rates_scare_score": 43.2},
    }


def _sealed(regime: dict, **kw) -> dict:
    return contract.finalize(liquidity_regime.compose(regime, built_at=BUILT_AT, **kw))


def test_active_on_valid_snapshot_exposes_only_approved_fields() -> None:
    snap = _sealed(_base_regime())
    out = consumer.summarize(snap)
    assert out["state"] == "ACTIVE" and out["active"] is True
    assert set(out["summary"].keys()) == _APPROVED_SUMMARY_KEYS
    assert out["summary"]["state_id"] == "C"
    assert out["authority"] == {
        "can_rank": False, "can_gate": False, "can_size": False,
        "can_originate_signal": False, "can_execute": False, "class": "context_only",
    }
    assert out["audit"]["contract_ok"] is True
    assert out["audit"]["content_sha256"] == snap["generation"]["content_sha256"]


def test_inert_on_malformed_object() -> None:
    out = consumer.summarize({"not": "a snapshot"})
    assert out["state"] == "INERT" and out["active"] is False
    assert out["summary"] is None
    assert out["audit"]["contract_ok"] is False
    assert out["audit"]["reason_code"] == "CONTRACT_INVALID"


def test_inert_on_hash_tamper() -> None:
    snap = _sealed(_base_regime())
    snap["headline"]["effective_date"] = "1999-01-01"  # break the sealed digest
    out = consumer.summarize(snap)
    assert out["state"] == "INERT"
    assert out["audit"]["reason_code"] == "CONTRACT_INVALID"


def test_inert_on_unsupported_version() -> None:
    snap = _sealed(_base_regime())
    snap["schema"]["version"] = "2.0.0"
    out = consumer.summarize(snap)
    assert out["state"] == "INERT"
    # F9: strengthen -- an unsupported schema version must surface a visible,
    # typed audit reason, not just a bare INERT state.
    assert out["audit"]["contract_ok"] is False
    assert out["audit"]["reason_code"] == "CONTRACT_INVALID"
    assert "2.0.0" in out["audit"]["detail"] or "unsupported schema version" in out["audit"]["detail"]


def test_inert_on_stale_snapshot_but_active_when_stale_allowed() -> None:
    reg = _base_regime()
    reg["conditions"]["stale_inputs"] = ["nfci"]
    snap = _sealed(reg)
    assert snap["availability"]["state"] == "STALE_SOURCE"
    strict = consumer.summarize(snap)
    assert strict["state"] == "INERT"
    assert strict["audit"]["reason_code"] == "STALE_OR_DEGRADED"
    lenient = consumer.summarize(snap, allow_stale=True)
    assert lenient["state"] == "ACTIVE"


def test_inert_on_unreadable_path() -> None:
    out = consumer.summarize_from_path(ROOT / "does" / "not" / "exist.json")
    assert out["state"] == "INERT"
    assert out["audit"]["reason_code"] == "SNAPSHOT_UNREADABLE"


def test_inert_on_snapshot_not_json(tmp_path) -> None:
    # F9: a readable file that is not valid JSON is a distinct typed failure
    # from an unreadable path -- must not raise, must surface SNAPSHOT_NOT_JSON.
    p = tmp_path / "latest.json"
    p.write_bytes(b"{not: valid json,,,")
    out = consumer.summarize_from_path(p)
    assert out["state"] == "INERT" and out["active"] is False
    assert out["summary"] is None
    assert out["audit"]["contract_ok"] is False
    assert out["audit"]["reason_code"] == "SNAPSHOT_NOT_JSON"


def test_summarize_from_path_roundtrip(tmp_path) -> None:
    import json
    snap = _sealed(_base_regime())
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(snap), encoding="utf-8")
    out = consumer.summarize_from_path(p)
    assert out["state"] == "ACTIVE"
    assert out["summary"]["workspace"] == "liquidity_regime"
