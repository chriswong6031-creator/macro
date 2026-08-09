"""Contracts for the read-only Market Memory composition and API."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import market_memory as api
from engine.neuralweb import market_memory as mm

PRICE_SOURCE_RECEIPT = "mmsrc_" + "a" * 64
MEMBERSHIP_SOURCE_RECEIPT = "mmsrc_" + "b" * 64
CALENDAR_SOURCE_RECEIPT = "mmsrc_" + "c" * 64
OPTIONS_OI_SOURCE_RECEIPT = "mmsrc_" + "d" * 64
DYNAMIC_SOURCE_RECEIPT = "mmsrc_" + "f" * 64
SECONDARY_SOURCE_RECEIPT = "mmsrc_" + "e" * 64
PRICE_VINTAGE = "mmv_" + "a" * 64
MEMBERSHIP_VINTAGE = "mmv_" + "b" * 64
CALENDAR_VINTAGE = "mmv_" + "c" * 64
OPTIONS_OI_VINTAGE = "mmv_" + "d" * 64
DYNAMIC_VINTAGE = "mmv_" + "f" * 64
SECONDARY_VINTAGE = "mmv_" + "e" * 64
PRICE_REVISION = "mmr_" + "1" * 64
MEMBERSHIP_REVISION = "mmr_" + "2" * 64
CALENDAR_REVISION = "mmr_" + "3" * 64
OPTIONS_OI_REVISION = "mmr_" + "4" * 64
DYNAMIC_REVISION = "mmr_" + "f" * 64
SECONDARY_REVISION = "mmr_" + "e" * 64
SECURITY_ID = "mmsecurity_" + "a" * 64
ALT_SECURITY_ID = "mmsecurity_" + "e" * 64
IDENTITY_VERSION = "mmidentityv_" + "b" * 64
UNIVERSE_ID = "mmuniverse_" + "c" * 64
ALT_UNIVERSE_ID = "mmuniverse_" + "e" * 64
CALENDAR_ID = "mmcalendar_" + "d" * 64
IDENTITY_RECEIPT = "mmidentity_" + "a" * 64
_SOURCE_ARTIFACT_BY_LOGICAL_ID = {
    PRICE_SOURCE_RECEIPT: "a" * 64,
    MEMBERSHIP_SOURCE_RECEIPT: "b" * 64,
    CALENDAR_SOURCE_RECEIPT: "c" * 64,
    OPTIONS_OI_SOURCE_RECEIPT: "d" * 64,
    SECONDARY_SOURCE_RECEIPT: "e" * 64,
    DYNAMIC_SOURCE_RECEIPT: "f" * 64,
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_site_full_user] = lambda: {"id": "test"}
    return TestClient(app)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("aapl", "AAPL"),
        (" BRK-B ", "BRK-B"),
        ("0700.hk", "0700.HK"),
        ("^vix", "^VIX"),
        ("gc=f", "GC=F"),
    ],
)
def test_normalize_ticker_accepts_canonical_market_symbols(
    raw: str, expected: str
) -> None:
    assert mm.normalize_ticker(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "../AAPL", "AAPL/../../x", "AAPL%2Fx", "A APL", "A" * 21]
)
def test_normalize_ticker_rejects_paths_and_unsafe_values(raw: str) -> None:
    with pytest.raises(mm.InvalidTicker):
        mm.normalize_ticker(raw)


def test_macro_composition_preserves_source_evidence_and_blocks_authority(
    monkeypatch,
) -> None:
    source = {
        "schema": "brain.analogues.v1",
        "asof": "2026-08-07",
        "coverage": "1997-01-01–2026-08-07",
        "n_candidates": 5000,
        "query": {"date": "2026-08-07", "quad": "goldilocks"},
        "episodes": [{"date": "2016-06-30", "distance": 1.2, "fwd": {"spx_h20": 0.04}}],
        "disclaimer": "source caveat",
    }
    from engine.neuralweb import brain_analogues

    monkeypatch.setattr(
        brain_analogues, "get_historical_analogues", lambda root, limit: source
    )

    payload = mm.macro_context(Path("/tmp/repo"), limit=4)

    assert payload["schema"] == mm.MACRO_SCHEMA
    assert payload["source_schema"] == "brain.analogues.v1"
    assert payload["episodes"] == source["episodes"]
    assert payload["historical_basis"] == "recomputed_history"
    assert payload["authority"]["may_rank"] is False
    assert payload["authority"]["may_train_prophet"] is False


def test_symbol_composition_reads_the_bounded_materialized_atlas(tmp_path) -> None:
    source = {
        "ticker": "AAPL",
        "as_of": "2026-08-07",
        "taxonomy_version": "sea.test",
        "align_now": 2,
        "bull_now": {"W": True},
        "grids": {"W": {"date": "2026-08-01", "receipt": {"horizons": {}}}},
    }
    stockdata = tmp_path / "site" / "stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_text(
        json.dumps({"event_atlas": source}), encoding="utf-8"
    )

    payload = mm.symbol_context(tmp_path, "aapl")

    assert payload["source_schema"] == "event_atlas.v1"
    assert payload["grids"] == source["grids"]
    assert payload["universe_basis"] == "current_membership_survivor_biased_backfill"
    assert payload["authority"]["may_gate"] is False


def test_symbol_composition_fails_closed_on_missing_or_oversized_artifact(
    tmp_path,
) -> None:
    missing = mm.symbol_context(tmp_path, "AAPL")
    assert missing["available"] is False

    stockdata = tmp_path / "site" / "stockdata"
    stockdata.mkdir(parents=True)
    (stockdata / "AAPL.json").write_bytes(b" " * (mm._MAX_STOCKDATA_BYTES + 1))
    oversized = mm.symbol_context(tmp_path, "AAPL")
    assert oversized["available"] is False


def test_macro_api_is_entitled_private_and_bounded(monkeypatch) -> None:
    seen = {}

    def fake(root, *, limit):
        seen["limit"] = limit
        return {
            "schema": mm.MACRO_SCHEMA,
            "available": True,
            "authority": dict(mm.AUTHORITY),
        }

    monkeypatch.setattr(mm, "macro_context", fake)
    response = _client().get("/api/market-memory/v1/macro?limit=8")

    assert response.status_code == 200
    assert seen["limit"] == 8
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert _client().get("/api/market-memory/v1/macro?limit=9").status_code == 422


@pytest.mark.parametrize("status", [401, 403])
def test_auth_and_entitlement_errors_are_private_and_never_shared_cached(
    status,
) -> None:
    app = FastAPI()
    app.include_router(api.router)

    def denied():
        raise HTTPException(status_code=status, detail="denied")

    app.dependency_overrides[api.require_site_full_user] = denied
    response = TestClient(app).get("/api/market-memory/v1/macro")

    assert response.status_code == status
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_symbol_api_statuses_and_invalid_input(monkeypatch) -> None:
    monkeypatch.setattr(
        mm,
        "symbol_context",
        lambda root, ticker: {
            "schema": mm.SYMBOL_SCHEMA,
            "available": ticker.upper() == "AAPL",
            "ticker": ticker.upper(),
        },
    )
    client = _client()
    assert client.get("/api/market-memory/v1/symbol/aapl").status_code == 200
    assert client.get("/api/market-memory/v1/symbol/ZZZZ").status_code == 404

    def invalid(root, ticker):
        raise mm.InvalidTicker("bad ticker")

    monkeypatch.setattr(mm, "symbol_context", invalid)
    response = client.get("/api/market-memory/v1/symbol/AAPL")
    assert response.status_code == 400
    assert response.json()["detail"] == "bad ticker"


def test_symbol_api_has_bounded_user_and_peer_rate_limits(monkeypatch) -> None:
    api._reset_symbol_rate_limit_for_tests()
    monkeypatch.setattr(api, "_SYMBOL_USER_LIMIT", 2)
    monkeypatch.setattr(api, "_SYMBOL_PEER_LIMIT", 10)
    monkeypatch.setattr(
        mm,
        "symbol_context",
        lambda root, ticker: {
            "schema": mm.SYMBOL_SCHEMA,
            "available": True,
            "ticker": ticker,
        },
    )
    client = _client()

    assert client.get("/api/market-memory/v1/symbol/AAPL").status_code == 200
    assert client.get("/api/market-memory/v1/symbol/MSFT").status_code == 200
    blocked = client.get("/api/market-memory/v1/symbol/NVDA")

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.headers["cache-control"] == "private, no-store"
    assert blocked.headers["vary"] == "Authorization"
    api._reset_symbol_rate_limit_for_tests()


def _as_known_at(**overrides):
    missing_features = []
    for feature_id, spec in mm.CANONICAL_FEATURE_REGISTRY.items():
        if feature_id == "price.ret_20d":
            continue
        missing_features.append(
            {
                "feature_id": feature_id,
                "feature_role": "decision_time_context",
                "domain": spec.domain,
                "status": "missing",
                "value": None,
                "unit": spec.unit,
                "observed_at": "2026-08-07T20:00:04Z",
                "pit_basis": "unknown",
                "transform_version": "market_memory.missing.v1",
                "source_receipt_ids": [],
                "missing_reason": "no_point_in_time_vintage",
                "quality": {
                    "status": "missing",
                    "flags": ["not_captured"],
                    "staleness_seconds": None,
                    "imputed": False,
                },
            }
        )
    kwargs = {
        "subject": {
            "subject_id": SECURITY_ID,
            "instrument_id": SECURITY_ID,
        },
        "event_time": "2026-08-07T20:00:00Z",
        "as_known_at": "2026-08-07T20:05:00Z",
        "mode": "operational_pit",
        "source_receipts": [
            {
                "receipt_id": PRICE_SOURCE_RECEIPT,
                "source_id": "licensed_ohlcv",
                "source_role": "market_price",
                "source_schema": "market_memory.source.ohlcv.v1",
                "artifact_sha256": "a" * 64,
                "event_time": "2026-08-07T20:00:00Z",
                "measurement_end": "2026-08-07T20:00:00Z",
                "available_at": "2026-08-07T20:00:01Z",
                "observed_at": "2026-08-07T20:00:03Z",
                "vintage_id": PRICE_VINTAGE,
                "revision_id": PRICE_REVISION,
                "pit_basis": "live_captured",
                "availability_class": "session_close",
                "availability_rule": "session_close_or_vendor_receipt.v1",
                "market_session": "US_REGULAR",
                "valid_from": None,
                "valid_through": None,
                "identity_binding": None,
                "quality": {
                    "status": "ok",
                    "flags": [],
                    "staleness_seconds": 300,
                    "imputed": False,
                },
            },
            {
                "receipt_id": MEMBERSHIP_SOURCE_RECEIPT,
                "source_id": "security_master_membership",
                "source_role": "security_identity_membership",
                "source_schema": "market_memory.source.security_membership.v1",
                "artifact_sha256": "b" * 64,
                "event_time": "2026-08-07T00:00:00Z",
                "measurement_end": "2026-08-07T00:00:00Z",
                "available_at": "2026-08-07T00:00:01Z",
                "observed_at": "2026-08-07T00:00:03Z",
                "vintage_id": MEMBERSHIP_VINTAGE,
                "revision_id": MEMBERSHIP_REVISION,
                "pit_basis": "source_vintage",
                "availability_class": "session_close",
                "availability_rule": "membership_publication_receipt.v1",
                "market_session": "US_REGULAR",
                "valid_from": "2026-08-07T00:00:00Z",
                "valid_through": "2026-08-08T00:00:00Z",
                "identity_binding": {
                    "schema": "market_memory.security_membership_binding.v1",
                    "subject_id": SECURITY_ID,
                    "instrument_id": SECURITY_ID,
                    "identity_version": IDENTITY_VERSION,
                    "universe_id": UNIVERSE_ID,
                    "membership_status": "member",
                    "content_sha256": "c" * 64,
                },
                "quality": {
                    "status": "ok",
                    "flags": [],
                    "staleness_seconds": 72_300,
                    "imputed": False,
                },
            },
            {
                "receipt_id": CALENDAR_SOURCE_RECEIPT,
                "source_id": "market_calendar",
                "source_role": "market_calendar",
                "source_schema": "market_memory.source.market_calendar.v1",
                "artifact_sha256": "c" * 64,
                "event_time": "2026-01-01T00:00:00Z",
                "measurement_end": "2026-01-01T00:00:00Z",
                "available_at": "2026-01-01T00:00:01Z",
                "observed_at": "2026-01-01T00:00:03Z",
                "vintage_id": CALENDAR_VINTAGE,
                "revision_id": CALENDAR_REVISION,
                "pit_basis": "source_vintage",
                "availability_class": "scheduled_release",
                "availability_rule": "calendar_publication_receipt.v1",
                "market_session": "US_REGULAR",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_through": "2027-01-01T00:00:00Z",
                "identity_binding": {
                    "schema": "market_memory.market_calendar_binding.v1",
                    "calendar_id": CALENDAR_ID,
                    "market_session": "US_REGULAR",
                    "content_sha256": "d" * 64,
                },
                "quality": {
                    "status": "ok",
                    "flags": [],
                    "staleness_seconds": 18_907_500,
                    "imputed": False,
                },
            },
        ],
        "identity_receipt": {
            "receipt_id": IDENTITY_RECEIPT,
            "subject_id": SECURITY_ID,
            "instrument_id": SECURITY_ID,
            "identity_version": IDENTITY_VERSION,
            "universe_id": UNIVERSE_ID,
            "membership_vintage_id": MEMBERSHIP_VINTAGE,
            "membership_revision_id": MEMBERSHIP_REVISION,
            "membership_source_receipt_id": MEMBERSHIP_SOURCE_RECEIPT,
            "membership_valid_from": "2026-08-07T00:00:00Z",
            "membership_valid_through": "2026-08-08T00:00:00Z",
            "calendar_id": CALENDAR_ID,
            "calendar_version": CALENDAR_VINTAGE,
            "calendar_revision_id": CALENDAR_REVISION,
            "calendar_source_receipt_id": CALENDAR_SOURCE_RECEIPT,
            "calendar_valid_from": "2026-01-01T00:00:00Z",
            "calendar_valid_through": "2027-01-01T00:00:00Z",
            "membership_status": "member",
            "effective_at": "2026-08-07T00:00:00Z",
            "available_at": "2026-08-07T00:00:01Z",
            "observed_at": "2026-08-07T00:00:04Z",
            "pit_basis": "source_vintage",
            "source_receipt_ids": [
                MEMBERSHIP_SOURCE_RECEIPT,
                CALENDAR_SOURCE_RECEIPT,
            ],
            "quality": {
                "status": "ok",
                "flags": [],
                "staleness_seconds": 18_907_500,
                "imputed": False,
            },
        },
        "feature_receipts": [
            {
                "feature_id": "price.ret_20d",
                "feature_role": "decision_time_context",
                "domain": "technicals",
                "status": "observed",
                "value": 0.04,
                "unit": "decimal_return",
                "observed_at": "2026-08-07T20:00:04Z",
                "pit_basis": "live_captured",
                "transform_version": "market_memory.return_20d_transform.v1",
                "source_receipt_ids": [PRICE_SOURCE_RECEIPT],
                "missing_reason": None,
                "quality": {
                    "status": "ok",
                    "flags": [],
                    "staleness_seconds": 300,
                    "imputed": False,
                },
            },
            *missing_features,
        ],
        "state_snapshot_ref": None,
    }
    for source in kwargs["source_receipts"]:
        binding = source["identity_binding"]
        if binding is not None:
            binding["content_sha256"] = mm._identity_binding_sha256(source, binding)
    kwargs.update(overrides)
    kwargs = deepcopy(kwargs)
    receipt_id_map = {}
    for source in kwargs["source_receipts"]:
        old_receipt_id = source["receipt_id"]
        try:
            new_receipt_id = mm._source_receipt_id(source)
        except mm.TemporalContractError:
            new_receipt_id = old_receipt_id
        source["receipt_id"] = new_receipt_id
        receipt_id_map[old_receipt_id] = new_receipt_id
        receipt_id_map[f"mmsrc_{source['artifact_sha256']}"] = new_receipt_id
    identity = kwargs["identity_receipt"]
    identity["membership_source_receipt_id"] = receipt_id_map.get(
        identity["membership_source_receipt_id"],
        identity["membership_source_receipt_id"],
    )
    identity["calendar_source_receipt_id"] = receipt_id_map.get(
        identity["calendar_source_receipt_id"], identity["calendar_source_receipt_id"]
    )
    identity["source_receipt_ids"] = sorted(
        receipt_id_map.get(receipt_id, receipt_id)
        for receipt_id in identity["source_receipt_ids"]
    )
    identity["receipt_id"] = mm._identity_receipt_id(identity)
    for feature in kwargs["feature_receipts"]:
        feature["source_receipt_ids"] = [
            receipt_id_map.get(receipt_id, receipt_id)
            for receipt_id in feature["source_receipt_ids"]
        ]
    return mm.build_as_known_at_context(**kwargs)


def _source(rows, receipt_id):
    exact = next((row for row in rows if row["receipt_id"] == receipt_id), None)
    if exact is not None:
        return exact
    artifact = _SOURCE_ARTIFACT_BY_LOGICAL_ID.get(receipt_id)
    return next(row for row in rows if row["artifact_sha256"] == artifact)


def _feature(rows, feature_id):
    return next(row for row in rows if row["feature_id"] == feature_id)


def _source_for_feature(feature_id):
    feature_spec = mm.CANONICAL_FEATURE_REGISTRY[feature_id]
    required_role = next(iter(feature_spec.required_source_roles))
    source_id, source_spec = next(
        (source_id, source_spec)
        for source_id, source_spec in mm.CANONICAL_SOURCE_REGISTRY.items()
        if source_spec.source_role == required_role
    )
    availability_class = min(source_spec.allowed_availability_classes)
    return {
        "receipt_id": DYNAMIC_SOURCE_RECEIPT,
        "source_id": source_id,
        "source_role": required_role,
        "source_schema": source_spec.source_schema,
        "artifact_sha256": "f" * 64,
        "event_time": "2026-08-07T20:00:00Z",
        "measurement_end": "2026-08-07T20:00:00Z",
        "available_at": "2026-08-07T20:00:01Z",
        "observed_at": "2026-08-07T20:00:03Z",
        "vintage_id": DYNAMIC_VINTAGE,
        "revision_id": DYNAMIC_REVISION,
        "pit_basis": "live_captured",
        "availability_class": availability_class,
        "availability_rule": source_spec.availability_rule,
        "market_session": "US_REGULAR",
        "valid_from": None,
        "valid_through": None,
        "identity_binding": None,
        "quality": {
            "status": "ok",
            "flags": [],
            "staleness_seconds": 300,
            "imputed": False,
        },
    }


def _observe_snapshot(features, feature_id, source_receipt_id):
    spec = mm.CANONICAL_FEATURE_REGISTRY[feature_id]
    row = _feature(features, feature_id)
    row.update(
        {
            "status": "observed",
            "value": {
                "snapshot_id": "mmsnap_" + "b" * 64,
                "schema": spec.value_schema,
                "content_sha256": "b" * 64,
                "as_of": "2026-08-07T20:00:00Z",
            },
            "observed_at": "2026-08-07T20:00:04Z",
            "pit_basis": "live_captured",
            "transform_version": spec.transform_version,
            "source_receipt_ids": [source_receipt_id],
            "missing_reason": None,
            "quality": {
                "status": "ok",
                "flags": [],
                "staleness_seconds": 300,
                "imputed": False,
            },
        }
    )
    return row


def test_as_known_at_contract_is_content_addressed_label_free_and_read_only() -> None:
    first = _as_known_at()
    second = _as_known_at()

    assert first == second
    assert first["schema"] == mm.AS_KNOWN_AT_SCHEMA
    assert first["context_id"].startswith("mmctx_")
    assert first["feature_registry_version"] == mm.FEATURE_REGISTRY_VERSION
    assert first["source_registry_version"] == mm.SOURCE_REGISTRY_VERSION
    assert first["clocks"]["as_known_at"] == first["clocks"]["knowledge_cutoff"]
    assert "labels" not in first
    assert first["label_policy"] == {
        "labels_in_context": False,
        "append_only_after_declared_horizon": True,
        "horizon_anchor": "clocks.as_known_at",
        "label_join": "reference_only_by_context_id",
        "outcome_owner": "consumer_program",
    }
    assert first["feature_receipts"][1]["missing_reason"] == "no_point_in_time_vintage"
    assert len(first["domain_coverage"]) == len(mm.CANONICAL_CONTEXT_DOMAINS)
    assert (
        next(row for row in first["domain_coverage"] if row["domain"] == "options")[
            "status"
        ]
        == "missing"
    )
    assert first["availability_policy"]["future_eod_values_forbidden"] is True
    assert first["authority"]["may_train_prophet"] is False
    assert first["authority"]["may_write_options_episode"] is False
    assert first["authority"]["context_only"] is True
    assert first["authority"]["proposal_weight"] == 0
    assert first["identity_receipt"]["membership_vintage_id"] == (MEMBERSHIP_VINTAGE)
    assert first["identity_receipt"]["membership_valid_through"] == (
        "2026-08-08T00:00:00Z"
    )
    assert first["state_snapshot_ref"] is None
    assert mm.validate_as_known_at_context(first) == first


def test_as_known_at_operational_mode_rejects_future_observation() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["observed_at"] = "2026-08-08T00:00:00Z"
    with pytest.raises(mm.TemporalContractError, match="observed_at follows"):
        _as_known_at(source_receipts=sources)


def test_as_known_at_rejects_measurements_after_context_event_time() -> None:
    sources = _as_known_at()["source_receipts"]
    price = _source(sources, PRICE_SOURCE_RECEIPT)
    price.update(
        {
            "measurement_end": "2026-08-07T20:00:01Z",
            "available_at": "2026-08-07T20:00:02Z",
            "observed_at": "2026-08-07T20:00:03Z",
        }
    )
    with pytest.raises(mm.TemporalContractError, match="context event_time"):
        _as_known_at(source_receipts=sources)


@pytest.mark.parametrize("mode", ["operational_pit", "public_reconstruction"])
def test_as_known_at_rejects_stale_missingness_receipts(mode: str) -> None:
    features = _as_known_at()["feature_receipts"]
    _feature(features, "options.chain_surface_state")["observed_at"] = (
        "2020-01-01T00:00:00Z"
    )
    with pytest.raises(mm.TemporalContractError, match="missing observed_at precedes"):
        _as_known_at(mode=mode, feature_receipts=features)


@pytest.mark.parametrize("target", ["source", "feature", "identity", "quality"])
def test_as_known_at_rejects_nested_extra_fields(target: str) -> None:
    sources = _as_known_at()["source_receipts"]
    features = _as_known_at()["feature_receipts"]
    identity = _as_known_at()["identity_receipt"]
    if target == "source":
        _source(sources, PRICE_SOURCE_RECEIPT)["future_outcome"] = 1
    elif target == "feature":
        _feature(features, "price.ret_20d")["future_outcome"] = 1
    elif target == "identity":
        identity["future_outcome"] = 1
    else:
        _feature(features, "price.ret_20d")["quality"]["future_outcome"] = 1
    with pytest.raises(mm.TemporalContractError, match="fields are not canonical"):
        _as_known_at(
            source_receipts=sources,
            feature_receipts=features,
            identity_receipt=identity,
        )


def test_as_known_at_operational_mode_rejects_reconstructed_evidence() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["pit_basis"] = "recomputed_history"
    with pytest.raises(mm.TemporalContractError, match="not operational evidence"):
        _as_known_at(source_receipts=sources)

    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d")["pit_basis"] = "current_snapshot_backfill"
    with pytest.raises(mm.TemporalContractError, match="not operational evidence"):
        _as_known_at(feature_receipts=features)


def test_as_known_at_requires_every_canonical_domain() -> None:
    with pytest.raises(mm.TemporalContractError, match="complete canonical domain set"):
        _as_known_at(required_domains=["technicals", "options"])


def test_as_known_at_rejects_future_eod_and_open_interest_availability() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT).update(
        {
            "source_id": "licensed_options_oi",
            "availability_class": "open_interest_eod",
            "available_at": "2026-08-08T12:00:00Z",
            "observed_at": "2026-08-08T12:00:01Z",
        }
    )
    with pytest.raises(
        mm.TemporalContractError, match="available_at follows as_known_at"
    ):
        _as_known_at(source_receipts=sources)


def test_as_known_at_public_reconstruction_preserves_later_observed_clock() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT).update(
        {
            "observed_at": "2026-09-01T00:00:00Z",
            "pit_basis": "public_reconstructed",
        }
    )
    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d").update(
        {
            "observed_at": "2026-09-01T00:00:01Z",
            "pit_basis": "public_reconstructed",
        }
    )
    _feature(features, "options.chain_surface_state")["observed_at"] = (
        "2026-09-01T00:00:01Z"
    )
    packet = _as_known_at(
        mode="public_reconstruction",
        source_receipts=sources,
        feature_receipts=features,
    )
    assert (
        _source(packet["source_receipts"], PRICE_SOURCE_RECEIPT)["observed_at"]
        == "2026-09-01T00:00:00Z"
    )
    assert packet["mode"] == "public_reconstruction"


def test_as_known_at_rejects_unknown_basis_for_observed_evidence() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["pit_basis"] = "unknown"
    with pytest.raises(
        mm.TemporalContractError, match="cannot be unknown for a source"
    ):
        _as_known_at(mode="public_reconstruction", source_receipts=sources)

    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d")["pit_basis"] = "unknown"
    with pytest.raises(
        mm.TemporalContractError, match="cannot be unknown for observed"
    ):
        _as_known_at(mode="public_reconstruction", feature_receipts=features)


@pytest.mark.parametrize("staleness", [float("nan"), float("inf"), float("-inf")])
def test_as_known_at_rejects_non_finite_staleness(staleness: float) -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["quality"]["staleness_seconds"] = staleness
    with pytest.raises(mm.TemporalContractError, match="must be non-negative or null"):
        _as_known_at(source_receipts=sources)


def test_as_known_at_rejects_understated_source_age_at_cutoff() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["quality"]["staleness_seconds"] = 0
    with pytest.raises(mm.TemporalContractError, match="understates age"):
        _as_known_at(source_receipts=sources)


@pytest.mark.parametrize(
    "quality",
    [
        {
            "status": "ok",
            "flags": [],
            "staleness_seconds": None,
            "imputed": False,
        },
        {
            "status": "ok",
            "flags": ["vendor_gap"],
            "staleness_seconds": 300,
            "imputed": False,
        },
        {
            "status": "degraded",
            "flags": [],
            "staleness_seconds": 300,
            "imputed": False,
        },
    ],
)
def test_as_known_at_quality_status_matches_freshness_and_registered_flags(
    quality,
) -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["quality"] = quality
    with pytest.raises(mm.TemporalContractError, match="requires"):
        _as_known_at(source_receipts=sources)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vintage_id", "winner_h60_plus_50pct"),
        ("revision_id", "target_positive_5d"),
        ("quality_flag", "profitable_trade_5d"),
    ],
)
def test_as_known_at_rejects_outcome_semantics_in_opaque_receipt_text(
    field: str, value: str
) -> None:
    sources = _as_known_at()["source_receipts"]
    price = _source(sources, PRICE_SOURCE_RECEIPT)
    if field == "quality_flag":
        price["quality"]["flags"] = [value]
    else:
        price[field] = value
    with pytest.raises(mm.TemporalContractError, match="opaque|quality registry"):
        _as_known_at(source_receipts=sources)

    features = _as_known_at()["feature_receipts"]
    _feature(features, "options.chain_surface_state")["missing_reason"] = (
        "winner_h60_plus_50pct"
    )
    with pytest.raises(mm.TemporalContractError, match="missingness registry"):
        _as_known_at(feature_receipts=features)


def test_as_known_at_rejects_tampering_and_outcome_leakage() -> None:
    packet = _as_known_at()
    packet["labels"] = [{"horizon": "5d", "value": 1.0}]
    with pytest.raises(mm.TemporalContractError, match="must not contain labels"):
        mm.validate_as_known_at_context(packet)

    packet = _as_known_at()
    packet["feature_receipts"][0]["value"] = 9.9
    with pytest.raises(mm.TemporalContractError, match="context_id"):
        mm.validate_as_known_at_context(packet)


def test_as_known_at_receipt_ids_bind_complete_source_and_identity_content() -> None:
    packet = _as_known_at()
    _source(packet["source_receipts"], PRICE_SOURCE_RECEIPT)["observed_at"] = (
        "2026-08-07T20:00:04Z"
    )
    packet["context_id"] = mm._canonical_context_id(packet)
    with pytest.raises(mm.TemporalContractError, match="canonical receipt content"):
        mm.validate_as_known_at_context(packet)

    packet = _as_known_at()
    packet["identity_receipt"]["observed_at"] = "2026-08-07T00:00:05Z"
    packet["context_id"] = mm._canonical_context_id(packet)
    with pytest.raises(mm.TemporalContractError, match="canonical identity content"):
        mm.validate_as_known_at_context(packet)


@pytest.mark.parametrize("packet", [None, 42, "bad"])
def test_as_known_at_validator_rejects_non_objects_with_contract_error(packet) -> None:
    with pytest.raises(mm.TemporalContractError, match="must be an object"):
        mm.validate_as_known_at_context(packet)


def test_as_known_at_receipt_collections_are_bounded_before_iteration() -> None:
    packet = _as_known_at()
    oversized_sources = [packet["source_receipts"][0]] * (mm._MAX_SOURCE_RECEIPTS + 1)
    with pytest.raises(mm.TemporalContractError, match="canonical bound"):
        _as_known_at(source_receipts=oversized_sources)

    packet["source_receipts"] = oversized_sources
    with pytest.raises(mm.TemporalContractError, match="canonical bound"):
        mm.validate_as_known_at_context(packet)


def test_as_known_at_enforces_value_missingness_and_source_receipts() -> None:
    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d")["source_receipt_ids"] = []
    with pytest.raises(
        mm.TemporalContractError, match="must reference at least one source"
    ):
        _as_known_at(feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d")["value"] = None
    with pytest.raises(mm.TemporalContractError, match="finite return scalar"):
        _as_known_at(feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    _feature(features, "options.chain_surface_state")["value"] = 0.0
    with pytest.raises(mm.TemporalContractError, match="missing cannot carry a value"):
        _as_known_at(feature_receipts=features)


def test_as_known_at_requires_every_registered_options_and_technical_context() -> None:
    packet = _as_known_at()
    options_rows = [
        row for row in packet["feature_receipts"] if row["domain"] == "options"
    ]
    assert {row["feature_id"] for row in options_rows} == {
        "options.chain_surface_state",
        "options.open_interest_eod_state",
        "options.flow_campaign_state",
        "options.gex_volatility_state",
    }
    assert all(row["status"] == "missing" for row in options_rows)
    options_coverage = next(
        row for row in packet["domain_coverage"] if row["domain"] == "options"
    )
    assert options_coverage["n_missing"] == 4

    features = deepcopy(packet["feature_receipts"])
    features = [
        row
        for row in features
        if row["feature_id"] != "options.open_interest_eod_state"
    ]
    with pytest.raises(mm.TemporalContractError, match="every registered"):
        _as_known_at(feature_receipts=features)

    assert {
        row["feature_id"]
        for row in packet["feature_receipts"]
        if row["domain"] == "technicals"
    } == {"price.ret_20d", "technicals.point_in_time_state"}


def test_as_known_at_basis_cannot_outrank_weakest_source() -> None:
    sources = _as_known_at()["source_receipts"]
    _source(sources, PRICE_SOURCE_RECEIPT)["pit_basis"] = "current_snapshot_backfill"
    features = _as_known_at()["feature_receipts"]
    price = _feature(features, "price.ret_20d")
    price["pit_basis"] = "source_vintage"
    with pytest.raises(mm.TemporalContractError, match="outranks its weakest source"):
        _as_known_at(
            mode="public_reconstruction",
            source_receipts=sources,
            feature_receipts=features,
        )

    second_price = deepcopy(_source(sources, PRICE_SOURCE_RECEIPT))
    second_price.update(
        {
            "receipt_id": SECONDARY_SOURCE_RECEIPT,
            "artifact_sha256": "e" * 64,
            "vintage_id": SECONDARY_VINTAGE,
            "revision_id": SECONDARY_REVISION,
            "pit_basis": "source_vintage",
        }
    )
    sources.append(second_price)
    price["source_receipt_ids"] = [
        PRICE_SOURCE_RECEIPT,
        SECONDARY_SOURCE_RECEIPT,
    ]
    with pytest.raises(mm.TemporalContractError, match="outranks its weakest source"):
        _as_known_at(
            mode="public_reconstruction",
            source_receipts=sources,
            feature_receipts=features,
        )


def test_as_known_at_identity_is_source_bound_and_allows_advance_announcement() -> None:
    identity = _as_known_at()["identity_receipt"]
    identity["membership_vintage_id"] = "mmv_" + "e" * 64
    with pytest.raises(mm.TemporalContractError, match="membership vintage/revision"):
        _as_known_at(identity_receipt=identity)

    sources = _as_known_at()["source_receipts"]
    membership = _source(sources, MEMBERSHIP_SOURCE_RECEIPT)
    membership.update(
        {
            "event_time": "2026-08-01T00:00:00Z",
            "measurement_end": "2026-08-01T00:00:00Z",
            "available_at": "2026-08-01T00:00:01Z",
            "observed_at": "2026-08-01T00:00:03Z",
        }
    )
    membership["quality"]["staleness_seconds"] = 590_700
    identity = _as_known_at()["identity_receipt"]
    identity.update(
        {
            "effective_at": "2026-08-07T00:00:00Z",
            "available_at": "2026-08-01T00:00:01Z",
            "observed_at": "2026-08-01T00:00:04Z",
        }
    )
    packet = _as_known_at(source_receipts=sources, identity_receipt=identity)
    assert (
        packet["identity_receipt"]["effective_at"]
        > packet["identity_receipt"]["available_at"]
    )

    sources = _as_known_at()["source_receipts"]
    membership = _source(sources, MEMBERSHIP_SOURCE_RECEIPT)
    membership["vintage_id"] = "  " + MEMBERSHIP_VINTAGE + "  "
    with pytest.raises(mm.TemporalContractError, match="surrounding whitespace"):
        _as_known_at(source_receipts=sources)


def test_as_known_at_rejects_stale_identity_and_swapped_source_roles() -> None:
    sources = _as_known_at()["source_receipts"]
    membership = _source(sources, MEMBERSHIP_SOURCE_RECEIPT)
    membership["valid_from"] = "2020-01-01T00:00:00Z"
    membership["valid_through"] = "2021-01-01T00:00:00Z"
    membership["identity_binding"]["content_sha256"] = mm._identity_binding_sha256(
        membership, membership["identity_binding"]
    )
    identity = _as_known_at()["identity_receipt"]
    identity.update(
        {
            "effective_at": "2020-01-01T00:00:00Z",
            "membership_valid_from": "2020-01-01T00:00:00Z",
            "membership_valid_through": "2021-01-01T00:00:00Z",
        }
    )
    with pytest.raises(mm.TemporalContractError, match="membership source validity"):
        _as_known_at(source_receipts=sources, identity_receipt=identity)

    sources = _as_known_at()["source_receipts"]
    membership = _source(sources, MEMBERSHIP_SOURCE_RECEIPT)
    calendar = _source(sources, CALENDAR_SOURCE_RECEIPT)
    membership["source_role"], calendar["source_role"] = (
        calendar["source_role"],
        membership["source_role"],
    )
    with pytest.raises(mm.TemporalContractError, match="source registry"):
        _as_known_at(source_receipts=sources)

    sources = _as_known_at()["source_receipts"]
    identity = _as_known_at()["identity_receipt"]
    identity.update(
        {
            "subject_id": ALT_SECURITY_ID,
            "instrument_id": ALT_SECURITY_ID,
            "universe_id": ALT_UNIVERSE_ID,
        }
    )
    membership = _source(sources, MEMBERSHIP_SOURCE_RECEIPT)
    membership["identity_binding"].update(
        {
            "subject_id": ALT_SECURITY_ID,
            "instrument_id": ALT_SECURITY_ID,
            "universe_id": ALT_UNIVERSE_ID,
        }
    )
    with pytest.raises(mm.TemporalContractError, match="content digest mismatch"):
        _as_known_at(
            subject={
                "subject_id": ALT_SECURITY_ID,
                "instrument_id": ALT_SECURITY_ID,
            },
            source_receipts=sources,
            identity_receipt=identity,
        )


def test_as_known_at_feature_dependencies_are_role_availability_and_transform_bound() -> (
    None
):
    features = _as_known_at()["feature_receipts"]
    macro = _observe_snapshot(features, "macro.regime_state", PRICE_SOURCE_RECEIPT)
    with pytest.raises(mm.TemporalContractError, match="source_role dependencies"):
        _as_known_at(feature_receipts=features)

    sources = _as_known_at()["source_receipts"]
    macro_source = _source_for_feature("macro.regime_state")
    sources.append(macro_source)
    features = _as_known_at()["feature_receipts"]
    macro = _observe_snapshot(
        features, "macro.regime_state", macro_source["receipt_id"]
    )
    macro["transform_version"] = "market_memory.missing.v1"
    with pytest.raises(mm.TemporalContractError, match="transform_version"):
        _as_known_at(source_receipts=sources, feature_receipts=features)


def test_as_known_at_options_oi_requires_eod_oi_source_and_availability() -> None:
    sources = _as_known_at()["source_receipts"]
    sources.append(
        {
            "receipt_id": OPTIONS_OI_SOURCE_RECEIPT,
            "source_id": "licensed_options_oi",
            "source_role": "options_open_interest_eod",
            "source_schema": "market_memory.source.options_open_interest_eod.v1",
            "artifact_sha256": "d" * 64,
            "event_time": "2026-08-07T20:00:00Z",
            "measurement_end": "2026-08-07T20:00:00Z",
            "available_at": "2026-08-07T20:00:01Z",
            "observed_at": "2026-08-07T20:00:03Z",
            "vintage_id": OPTIONS_OI_VINTAGE,
            "revision_id": OPTIONS_OI_REVISION,
            "pit_basis": "live_captured",
            "availability_class": "session_close",
            "availability_rule": "open_interest_eod_release_or_ingest_receipt.v1",
            "market_session": "US_REGULAR",
            "valid_from": None,
            "valid_through": None,
            "identity_binding": None,
            "quality": {
                "status": "ok",
                "flags": [],
                "staleness_seconds": 300,
                "imputed": False,
            },
        }
    )
    features = _as_known_at()["feature_receipts"]
    _observe_snapshot(
        features,
        "options.open_interest_eod_state",
        OPTIONS_OI_SOURCE_RECEIPT,
    )
    with pytest.raises(mm.TemporalContractError, match="availability_class"):
        _as_known_at(source_receipts=sources, feature_receipts=features)

    _source(sources, OPTIONS_OI_SOURCE_RECEIPT)["availability_class"] = (
        "open_interest_eod"
    )
    packet = _as_known_at(source_receipts=sources, feature_receipts=features)
    assert (
        _feature(packet["feature_receipts"], "options.open_interest_eod_state")[
            "status"
        ]
        == "observed"
    )


def test_as_known_at_all_registered_feature_sources_can_round_trip() -> None:
    for feature_id, spec in mm.CANONICAL_FEATURE_REGISTRY.items():
        if feature_id == "price.ret_20d":
            continue
        sources = _as_known_at()["source_receipts"]
        source = _source_for_feature(feature_id)
        sources.append(source)
        features = _as_known_at()["feature_receipts"]
        _observe_snapshot(features, feature_id, source["receipt_id"])

        packet = _as_known_at(source_receipts=sources, feature_receipts=features)

        observed = _feature(packet["feature_receipts"], feature_id)
        assert observed["status"] == "observed"
        assert observed["value"]["schema"] == spec.value_schema


def test_as_known_at_rejects_unreferenced_source_receipts() -> None:
    sources = _as_known_at()["source_receipts"]
    source = _source_for_feature("macro.regime_state")
    source.update(
        {
            "source_id": "market_regime_store",
            "source_role": "macro_regime",
            "source_schema": "market_memory.source.macro_regime.v1",
            "vintage_id": DYNAMIC_VINTAGE,
        }
    )
    sources.append(source)
    with pytest.raises(mm.TemporalContractError, match="unreferenced"):
        _as_known_at(source_receipts=sources)


@pytest.mark.parametrize(
    "mutable_ref",
    ["state:latest", "outcomes:h60:winner", "https://example.test/state/latest"],
)
def test_as_known_at_rejects_mutable_top_level_state_snapshot_ref(
    mutable_ref: str,
) -> None:
    with pytest.raises(mm.TemporalContractError, match="must be null"):
        _as_known_at(state_snapshot_ref=mutable_ref)


def test_as_known_at_rejects_unregistered_subject_and_non_typed_feature_values() -> (
    None
):
    with pytest.raises(mm.TemporalContractError, match="unregistered fields"):
        _as_known_at(
            subject={
                "subject_id": SECURITY_ID,
                "instrument_id": SECURITY_ID,
                "outcome": "winner",
            }
        )

    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d")["value"] = {
        "metric": "future_return",
        "horizon": "5d",
        "result": 0.42,
    }
    with pytest.raises(mm.TemporalContractError, match="finite return scalar"):
        _as_known_at(feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    _feature(features, "price.ret_20d")["value"] = ({"future_return": 0.5},)
    with pytest.raises(mm.TemporalContractError, match="finite return scalar"):
        _as_known_at(feature_receipts=features)


def test_as_known_at_snapshot_reference_is_typed_clocked_and_detached() -> None:
    sources = _as_known_at()["source_receipts"]
    macro_source = _source_for_feature("macro.regime_state")
    sources.append(macro_source)
    features = _as_known_at()["feature_receipts"]
    macro = _feature(features, "macro.regime_state")
    snapshot = {
        "snapshot_id": "mmsnap_" + "a" * 64,
        "schema": "market_memory.macro_regime_snapshot.v1",
        "content_sha256": "a" * 64,
        "as_of": "2026-08-07T20:00:00Z",
    }
    macro.update(
        {
            "status": "observed",
            "value": snapshot,
            "observed_at": "2026-08-07T20:00:04Z",
            "pit_basis": "live_captured",
            "transform_version": "market_memory.macro_regime_transform.v1",
            "source_receipt_ids": [macro_source["receipt_id"]],
            "missing_reason": None,
            "quality": {
                "status": "ok",
                "flags": [],
                "staleness_seconds": 300,
                "imputed": False,
            },
        }
    )
    packet = _as_known_at(source_receipts=sources, feature_receipts=features)
    snapshot["snapshot_id"] = "mutated-after-build"
    built_value = _feature(packet["feature_receipts"], "macro.regime_state")["value"]
    assert built_value["snapshot_id"] == "mmsnap_" + "a" * 64

    detached = mm.validate_as_known_at_context(packet)
    built_value["snapshot_id"] = "mutated-after-validate"
    assert (
        _feature(detached["feature_receipts"], "macro.regime_state")["value"][
            "snapshot_id"
        ]
        == "mmsnap_" + "a" * 64
    )

    features = _as_known_at()["feature_receipts"]
    macro = _feature(features, "macro.regime_state")
    macro.update(
        {
            "status": "observed",
            "value": {**snapshot, "as_of": "2026-08-07T20:00:05Z"},
            "pit_basis": "live_captured",
            "transform_version": "market_memory.macro_regime_transform.v1",
            "source_receipt_ids": [macro_source["receipt_id"]],
            "missing_reason": None,
            "quality": {
                "status": "ok",
                "flags": [],
                "staleness_seconds": 300,
                "imputed": False,
            },
        }
    )
    with pytest.raises(mm.TemporalContractError, match="follows feature observed_at"):
        _as_known_at(source_receipts=sources, feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    macro = _observe_snapshot(
        features, "macro.regime_state", macro_source["receipt_id"]
    )
    macro["value"]["as_of"] = "2026-08-07T19:59:59Z"
    with pytest.raises(mm.TemporalContractError, match="precedes a cited source"):
        _as_known_at(source_receipts=sources, feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    macro = _observe_snapshot(
        features, "macro.regime_state", macro_source["receipt_id"]
    )
    macro["value"]["snapshot_id"] = "outcomes:h60:winner"
    with pytest.raises(mm.TemporalContractError, match="content-addressed"):
        _as_known_at(source_receipts=sources, feature_receipts=features)


def test_as_known_at_context_id_is_permutation_invariant() -> None:
    first = _as_known_at()
    second = _as_known_at(
        source_receipts=list(reversed(deepcopy(first["source_receipts"]))),
        feature_receipts=list(reversed(deepcopy(first["feature_receipts"]))),
        required_domains=list(reversed(mm.CANONICAL_CONTEXT_DOMAINS)),
        identity_receipt=deepcopy(first["identity_receipt"]),
    )
    assert second == first


def test_as_known_at_registry_version_keeps_old_packets_valid(monkeypatch) -> None:
    packet = _as_known_at()
    extended = dict(mm._FEATURE_REGISTRIES)
    extended["market_memory.feature_registry.future.v2"] = MappingProxyType(
        dict(mm.CANONICAL_FEATURE_REGISTRY)
    )
    monkeypatch.setattr(mm, "_FEATURE_REGISTRIES", MappingProxyType(extended))
    assert mm.validate_as_known_at_context(packet) == packet


def test_as_known_at_authority_is_immutable_and_exact() -> None:
    with pytest.raises(TypeError):
        mm.AUTHORITY["may_train_prophet"] = True
    packet = _as_known_at()
    packet["authority"]["may_train_prophet"] = True
    packet["context_id"] = mm._canonical_context_id(packet)
    with pytest.raises(mm.TemporalContractError, match="authority policy drift"):
        mm.validate_as_known_at_context(packet)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("clocks", "bad"),
        ("subject", "bad"),
        ("source_receipts", {"x": "y"}),
        ("identity_receipt", ["bad"]),
    ],
)
def test_as_known_at_malformed_rehashed_packets_fail_typed(field, value) -> None:
    packet = _as_known_at()
    packet[field] = value
    packet["context_id"] = mm._canonical_context_id(packet)
    with pytest.raises(mm.TemporalContractError):
        mm.validate_as_known_at_context(packet)


def test_as_known_at_quality_cannot_upgrade_dependencies() -> None:
    sources = _as_known_at()["source_receipts"]
    price_source = _source(sources, PRICE_SOURCE_RECEIPT)
    price_source["quality"] = {
        "status": "degraded",
        "flags": ["vendor_gap"],
        "staleness_seconds": 300,
        "imputed": True,
    }
    with pytest.raises(mm.TemporalContractError, match="upgrades degraded"):
        _as_known_at(source_receipts=sources)

    features = _as_known_at()["feature_receipts"]
    price = _feature(features, "price.ret_20d")
    price["quality"] = {
        "status": "degraded",
        "flags": ["vendor_gap"],
        "staleness_seconds": 300,
        "imputed": True,
    }
    packet = _as_known_at(source_receipts=sources, feature_receipts=features)
    technical_coverage = next(
        row for row in packet["domain_coverage"] if row["domain"] == "technicals"
    )
    assert technical_coverage["n_degraded"] == 1
    assert technical_coverage["n_imputed"] == 1

    sources = _as_known_at()["source_receipts"]
    membership_source = _source(sources, MEMBERSHIP_SOURCE_RECEIPT)
    membership_source["quality"] = {
        "status": "degraded",
        "flags": ["identity_gap"],
        "staleness_seconds": 72_300,
        "imputed": True,
    }
    with pytest.raises(mm.TemporalContractError, match="upgrades degraded"):
        _as_known_at(source_receipts=sources)
