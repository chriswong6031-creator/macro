"""HTTP-client-independent checks for the bounded T1a route contract."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.biocatalyst as api
from engine.biocatalyst.protocols import build_trial_protocol_projection
from engine.biocatalyst.trials import build_trial_snapshot
from engine.sector_intelligence import canonical_json_sha256, validate_contract


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "clinicaltrials"
    / "trial_source_snapshot.after.v1.valid.json"
)


def _protocol(nct_id: str) -> dict:
    source = json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))
    source["nct_id"] = nct_id
    source["canonical_study"]["protocolSection"]["identificationModule"]["nctId"] = nct_id
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:{nct_id}:sha256:{canonical_sha}"
    source["raw_object_key"] = f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{canonical_sha}.json"
    source["source_snapshot_id"] = f"ctgov_snapshot_{nct_id}_fixture_{canonical_sha}"
    source["source_uri"] = f"https://clinicaltrials.gov/study/{nct_id}"
    validate_contract(source, repo_root=ROOT)
    trial = build_trial_snapshot(source)
    return build_trial_protocol_projection(source, trial)


def _projection() -> SimpleNamespace:
    nct_id = "NCT00000001"
    return SimpleNamespace(
        generation=SimpleNamespace(
            generation_id="ctgov_run_20260802_peer_contract",
            schema_version="1.5.0",
            last_success_at="2026-08-02T12:00:00.000000Z",
            source_dataset_timestamp_raw="2026-08-02T11:59:00",
            configured_nct_count=1,
            observed_nct_count=1,
            last_attempt_at="2026-08-02T12:00:00.000000Z",
        ),
        protocols_by_nct={nct_id: _protocol(nct_id)},
        history_models_by_nct={
            nct_id: {"available": False, "unavailable_reason": "not_collected"}
        },
    )


def test_t1a_direct_route_returns_contract_valid_partial_facts_only_set(monkeypatch) -> None:
    projection = _projection()
    monkeypatch.setattr(api, "_read_bundle", lambda: (projection, {}))

    response = api.resolve_trial_peer_set(
        {"nct_ids": ["NCT99999999", "NCT00000001"], "limit": 1},
        _user={"id": "paid-user", "tier": "pro"},
    )

    payload = json.loads(response.body)
    validate_contract(payload, repo_root=ROOT)
    assert payload["cohort_nct_ids"] == ["NCT00000001", "NCT99999999"]
    assert payload["uncovered_nct_ids"] == ["NCT99999999"]
    assert payload["trials"][0]["nct_id"] == "NCT00000001"
    assert payload["authority"]["decision_authority"] is False
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"


def test_t1a_legacy_projection_is_unavailable_not_false_all_uncovered(monkeypatch) -> None:
    projection = _projection()
    projection.generation.schema_version = "1.3.0"
    projection.protocols_by_nct = {}
    monkeypatch.setattr(api, "_read_bundle", lambda: (projection, {}))

    with pytest.raises(api.HTTPException) as caught:
        api.resolve_trial_peer_set(
            {"nct_ids": ["NCT00000001", "NCT99999999"]},
            _user={"id": "paid-user", "tier": "pro"},
        )

    assert caught.value.status_code == 503
    assert caught.value.detail == "trial intelligence temporarily unavailable"


def test_t1a_cursor_mismatch_rejects_before_public_projection_read(monkeypatch) -> None:
    binding = api._peer_set_query_binding(
        cohort_nct_ids=("NCT00000001", "NCT00000002"),
        page_limit=1,
        user={"id": "paid-user", "tier": "pro"},
    )
    cursor = api._encode_peer_set_cursor(
        1,
        generation_id="ctgov_run_20260802_peer_contract",
        query_binding=binding,
        cursor_key=b"x" * 32,
    )
    monkeypatch.setattr(api, "_peer_set_cursor_key", lambda: b"x" * 32)
    monkeypatch.setattr(
        api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(AssertionError("binding mismatch must precede read")),
    )

    with pytest.raises(api.HTTPException) as caught:
        api.resolve_trial_peer_set(
            {"nct_ids": ["NCT00000001", "NCT00000002"], "limit": 2, "cursor": cursor},
            _user={"id": "paid-user", "tier": "pro"},
        )
    assert caught.value.status_code == 400
    assert caught.value.detail == "cursor query mismatch"
