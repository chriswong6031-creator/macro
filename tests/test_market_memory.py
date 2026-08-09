"""Contracts for the read-only Market Memory composition and API."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import market_memory as api
from engine.neuralweb import market_memory as mm


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_site_full_user] = lambda: {"id": "test"}
    return TestClient(app)


@pytest.mark.parametrize("raw,expected", [
    ("aapl", "AAPL"),
    (" BRK-B ", "BRK-B"),
    ("0700.hk", "0700.HK"),
    ("^vix", "^VIX"),
    ("gc=f", "GC=F"),
])
def test_normalize_ticker_accepts_canonical_market_symbols(raw: str, expected: str) -> None:
    assert mm.normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "../AAPL", "AAPL/../../x", "AAPL%2Fx", "A APL", "A" * 21])
def test_normalize_ticker_rejects_paths_and_unsafe_values(raw: str) -> None:
    with pytest.raises(mm.InvalidTicker):
        mm.normalize_ticker(raw)


def test_macro_composition_preserves_source_evidence_and_blocks_authority(monkeypatch) -> None:
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
    monkeypatch.setattr(brain_analogues, "get_historical_analogues", lambda root, limit: source)

    payload = mm.macro_context(Path("/tmp/repo"), limit=4)

    assert payload["schema"] == mm.MACRO_SCHEMA
    assert payload["source_schema"] == "brain.analogues.v1"
    assert payload["episodes"] == source["episodes"]
    assert payload["historical_basis"] == "recomputed_history"
    assert payload["authority"]["may_rank"] is False
    assert payload["authority"]["may_train_prophet"] is False


def test_symbol_composition_delegates_to_atlas_without_recomputing_receipts(monkeypatch) -> None:
    source = {
        "ticker": "AAPL",
        "as_of": "2026-08-07",
        "taxonomy_version": "sea.test",
        "align_now": 2,
        "bull_now": {"W": True},
        "grids": {"W": {"date": "2026-08-01", "receipt": {"horizons": {}}}},
    }
    from engine import event_atlas
    seen = {}

    def fake_live_state(ticker, *, data_root):
        seen.update(ticker=ticker, data_root=data_root)
        return source

    monkeypatch.setattr(event_atlas, "live_state", fake_live_state)
    payload = mm.symbol_context(Path("/repo"), "aapl")

    assert seen == {"ticker": "AAPL", "data_root": Path("/repo/data")}
    assert payload["source_schema"] == event_atlas.SCHEMA
    assert payload["grids"] is source["grids"]
    assert payload["universe_basis"] == "current_membership_survivor_biased_backfill"
    assert payload["authority"]["may_gate"] is False


def test_macro_api_is_entitled_private_and_bounded(monkeypatch) -> None:
    seen = {}

    def fake(root, *, limit):
        seen["limit"] = limit
        return {"schema": mm.MACRO_SCHEMA, "available": True, "authority": mm.AUTHORITY}

    monkeypatch.setattr(mm, "macro_context", fake)
    response = _client().get("/api/market-memory/v1/macro?limit=8")

    assert response.status_code == 200
    assert seen["limit"] == 8
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert _client().get("/api/market-memory/v1/macro?limit=9").status_code == 422


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


def _as_known_at(**overrides):
    kwargs = {
        "subject": {"ticker": "AAPL", "instrument_id": "security:aapl"},
        "event_time": "2026-08-07T20:00:00Z",
        "as_known_at": "2026-08-07T20:05:00Z",
        "mode": "operational_pit",
        "source_receipts": [{
            "receipt_id": "price:aapl:2026-08-07",
            "source_id": "licensed_ohlcv",
            "event_time": "2026-08-07T20:00:00Z",
            "measurement_end": "2026-08-07T20:00:00Z",
            "available_at": "2026-08-07T20:00:01Z",
            "observed_at": "2026-08-07T20:00:03Z",
            "vintage_id": "vendor-2026-08-07-close",
            "revision_id": "sha256:abc",
            "pit_basis": "live_captured",
            "availability_class": "session_close",
            "market_session": "US_REGULAR",
            "quality": {"status": "ok", "flags": [], "staleness_seconds": 3, "imputed": False},
        }],
        "feature_receipts": [{
            "feature_id": "price.ret_20d",
            "domain": "technicals",
            "status": "observed",
            "value": 0.04,
            "unit": "decimal_return",
            "observed_at": "2026-08-07T20:00:04Z",
            "pit_basis": "live_captured",
            "transform_version": "returns.v1",
            "source_receipt_ids": ["price:aapl:2026-08-07"],
            "missing_reason": None,
            "quality": {"status": "ok", "flags": [], "staleness_seconds": 4, "imputed": False},
        }, {
            "feature_id": "options.iv_surface",
            "domain": "options",
            "status": "missing",
            "value": None,
            "unit": "surface",
            "observed_at": "2026-08-07T20:00:04Z",
            "pit_basis": "unknown",
            "transform_version": "options_surface.v0",
            "source_receipt_ids": [],
            "missing_reason": "no_point_in_time_vintage",
            "quality": {"status": "missing", "flags": ["not_captured"], "staleness_seconds": None, "imputed": False},
        }],
        "state_snapshot_ref": "state:2026-08-07T20:05:00Z",
    }
    kwargs.update(overrides)
    return mm.build_as_known_at_context(**kwargs)


def test_as_known_at_contract_is_content_addressed_label_free_and_read_only() -> None:
    first = _as_known_at()
    second = _as_known_at()

    assert first == second
    assert first["schema"] == mm.AS_KNOWN_AT_SCHEMA
    assert first["context_id"].startswith("mmctx_")
    assert first["clocks"]["as_known_at"] == first["clocks"]["knowledge_cutoff"]
    assert "labels" not in first
    assert first["label_policy"] == {
        "labels_in_context": False,
        "append_only_after_declared_horizon": True,
        "outcome_owner": "consumer_program",
    }
    assert first["feature_receipts"][1]["missing_reason"] == "no_point_in_time_vintage"
    assert len(first["domain_coverage"]) == len(mm.CANONICAL_CONTEXT_DOMAINS)
    assert next(row for row in first["domain_coverage"] if row["domain"] == "options")["status"] == "missing"
    assert first["availability_policy"]["future_eod_values_forbidden"] is True
    assert first["authority"]["may_train_prophet"] is False
    assert mm.validate_as_known_at_context(first) == first


def test_as_known_at_operational_mode_rejects_future_observation() -> None:
    sources = _as_known_at()["source_receipts"]
    sources[0]["observed_at"] = "2026-08-08T00:00:00Z"
    with pytest.raises(mm.TemporalContractError, match="observed_at follows"):
        _as_known_at(source_receipts=sources)


def test_as_known_at_operational_mode_rejects_reconstructed_evidence() -> None:
    sources = _as_known_at()["source_receipts"]
    sources[0]["pit_basis"] = "recomputed_history"
    with pytest.raises(mm.TemporalContractError, match="not operational evidence"):
        _as_known_at(source_receipts=sources)

    features = _as_known_at()["feature_receipts"]
    features[0]["pit_basis"] = "current_snapshot_backfill"
    with pytest.raises(mm.TemporalContractError, match="not operational evidence"):
        _as_known_at(feature_receipts=features)


def test_as_known_at_requires_every_canonical_domain() -> None:
    with pytest.raises(mm.TemporalContractError, match="complete canonical domain set"):
        _as_known_at(required_domains=["technicals", "options"])


def test_as_known_at_rejects_future_eod_and_open_interest_availability() -> None:
    sources = _as_known_at()["source_receipts"]
    sources[0].update({
        "source_id": "licensed_options_oi",
        "availability_class": "open_interest_eod",
        "available_at": "2026-08-08T12:00:00Z",
        "observed_at": "2026-08-08T12:00:01Z",
    })
    with pytest.raises(mm.TemporalContractError, match="available_at follows as_known_at"):
        _as_known_at(source_receipts=sources)


def test_as_known_at_public_reconstruction_preserves_later_observed_clock() -> None:
    sources = _as_known_at()["source_receipts"]
    sources[0].update({
        "observed_at": "2026-09-01T00:00:00Z",
        "pit_basis": "public_reconstructed",
    })
    features = _as_known_at()["feature_receipts"]
    features[0].update({
        "observed_at": "2026-09-01T00:00:01Z",
        "pit_basis": "public_reconstructed",
    })
    features[1]["observed_at"] = "2026-09-01T00:00:01Z"
    packet = _as_known_at(
        mode="public_reconstruction",
        source_receipts=sources,
        feature_receipts=features,
    )
    assert packet["source_receipts"][0]["observed_at"] == "2026-09-01T00:00:00Z"
    assert packet["mode"] == "public_reconstruction"


def test_as_known_at_rejects_unknown_basis_for_observed_evidence() -> None:
    sources = _as_known_at()["source_receipts"]
    sources[0]["pit_basis"] = "unknown"
    with pytest.raises(mm.TemporalContractError, match="cannot be unknown for a source"):
        _as_known_at(mode="public_reconstruction", source_receipts=sources)

    features = _as_known_at()["feature_receipts"]
    features[0]["pit_basis"] = "unknown"
    with pytest.raises(mm.TemporalContractError, match="cannot be unknown for observed"):
        _as_known_at(mode="public_reconstruction", feature_receipts=features)


@pytest.mark.parametrize("staleness", [float("nan"), float("inf"), float("-inf")])
def test_as_known_at_rejects_non_finite_staleness(staleness: float) -> None:
    sources = _as_known_at()["source_receipts"]
    sources[0]["quality"]["staleness_seconds"] = staleness
    with pytest.raises(mm.TemporalContractError, match="must be non-negative or null"):
        _as_known_at(source_receipts=sources)


def test_as_known_at_rejects_tampering_and_outcome_leakage() -> None:
    packet = _as_known_at()
    packet["labels"] = [{"horizon": "5d", "value": 1.0}]
    with pytest.raises(mm.TemporalContractError, match="must not contain labels"):
        mm.validate_as_known_at_context(packet)

    packet = _as_known_at()
    packet["feature_receipts"][0]["value"] = 9.9
    with pytest.raises(mm.TemporalContractError, match="context_id"):
        mm.validate_as_known_at_context(packet)


def test_as_known_at_enforces_value_missingness_and_source_receipts() -> None:
    features = _as_known_at()["feature_receipts"]
    features[0]["source_receipt_ids"] = []
    with pytest.raises(mm.TemporalContractError, match="must reference at least one source"):
        _as_known_at(feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    features[0]["value"] = None
    with pytest.raises(mm.TemporalContractError, match="value cannot be null"):
        _as_known_at(feature_receipts=features)

    features = _as_known_at()["feature_receipts"]
    features[1]["value"] = 0.0
    with pytest.raises(mm.TemporalContractError, match="missing cannot carry a value"):
        _as_known_at(feature_receipts=features)
