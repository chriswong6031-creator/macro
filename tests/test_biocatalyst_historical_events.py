from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from engine.biocatalyst.historical_events import (
    HistoricalEventError,
    HistoricalEventPublisher,
    query_events,
)


def _event(event_id: str, event_date: str, *, ticker: str = "ABC", family: str = "regulatory") -> dict:
    return {
        "contract_id": "biocatalyst_historical_event_record.v1",
        "schema_version": "1.0.0",
        "event_id": event_id,
        "source": {"provider": "BioPharmCatalyst", "source_id": "biopharmcatalyst_jv_snapshot", "license_class": "licensed_finite_snapshot", "family": "historical_fda", "source_ordinal": 1, "capture_observed_at": "2026-08-17T07:55:47Z", "source_published_at": None, "source_published_at_state": "unknown"},
        "company": {"ticker_evidence": ticker, "name_evidence": "Alpha", "resolution_state": "unresolved", "security_id": None, "issuer_id": None, "resolution_basis": "none", "issuer_relationship_state": "unavailable"},
        "event": {"date": event_date, "date_precision": "day", "family": family, "stage": "Approved", "description": "Approved", "source_available_at": None, "observed_at": "2026-08-17T07:55:47Z"},
        "asset": {"kind": "drug", "label": "Drug A", "indication": "Cancer"},
        "historical_market": {"price_at_event": "$10", "price_movement": "+5%"},
        "normalization": {"state": "deterministic", "repair": "none"},
        "unsafe_fields": ["current_price"],
        "authority": {"classification": "licensed_historical_context", "decision_authority": False, "allowed_uses": ["display", "context", "explain"], "forbidden_uses": ["originate_signal", "rank_security", "select_security", "size_position", "gate_decision", "execute_trade", "raise_authority"]},
    }


def _coverage(count: int) -> dict:
    return {"state": "partial", "source_rows": count, "normalized_rows": count, "identity_resolved": 0, "identity_unresolved": count, "duplicates_collapsed": 0, "families": {"historical_fda": count}, "family_source_rows": {"historical_fda": count, "device_history": 0, "device_pipeline_history": 0}}


def _rehash_manifest(root: Path, generation_id: str, manifest: dict) -> None:
    unhashed = dict(manifest)
    unhashed.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = sha256(
        json.dumps(unhashed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    generation = root / "generations" / generation_id
    (generation / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    (root / "current.json").write_text(
        json.dumps(pointer, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def test_publish_and_read_are_pointer_bound_and_byte_deterministic(tmp_path: Path) -> None:
    events = [_event("bpcjv_event_" + "a" * 24, "2024-01-01")]
    publisher = HistoricalEventPublisher(tmp_path)
    first = publisher.publish(events, coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    second = publisher.publish(events, coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    assert first.generation_id == second.generation_id
    assert first.events == tuple(events)
    assert publisher.read_current().events == tuple(events)


def test_published_generation_and_record_match_closed_json_schemas(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    projection = publisher.publish(
        [_event("bpcjv_event_" + "a" * 24, "2024-01-01")],
        coverage=_coverage(1),
        capture_observed_at="2026-08-17T07:55:47Z",
        published_at="2026-08-24T20:00:00Z",
    )
    contracts = Path(__file__).resolve().parents[1] / "contracts" / "biocatalyst"
    generation = tmp_path / "generations" / projection.generation_id
    Draft202012Validator(
        json.loads((contracts / "historical_event_generation.v1.schema.json").read_text())
    ).validate(json.loads((generation / "manifest.json").read_text()))
    Draft202012Validator(
        json.loads((contracts / "historical_event_record.v1.schema.json").read_text())
    ).validate(json.loads((generation / "events.jsonl").read_text().splitlines()[0]))


def test_reader_rejects_manifest_or_artifact_tampering(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    projection = publisher.publish([_event("bpcjv_event_" + "a" * 24, "2024-01-01")], coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    artifact = tmp_path / "generations" / projection.generation_id / "events.jsonl"
    artifact.write_text("{}\n", encoding="utf-8")
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_ARTIFACT_INVALID"):
        publisher.read_current()


def test_publish_and_reader_reject_incoherent_coverage_even_when_rehashed(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_COVERAGE_INVALID"):
        publisher.publish(
            [_event("bpcjv_event_" + "a" * 24, "2024-01-01")],
            coverage={"state": "partial", "normalized_rows": 1},
            capture_observed_at="2026-08-17T07:55:47Z",
            published_at="2026-08-24T20:00:00Z",
        )

    projection = publisher.publish(
        [_event("bpcjv_event_" + "a" * 24, "2024-01-01")],
        coverage=_coverage(1),
        capture_observed_at="2026-08-17T07:55:47Z",
        published_at="2026-08-24T20:00:00Z",
    )
    manifest_path = tmp_path / "generations" / projection.generation_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"]["identity_resolved"] = 1
    _rehash_manifest(tmp_path, projection.generation_id, manifest)
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_COVERAGE_INVALID"):
        publisher.read_current()


def test_reader_rejects_rehashed_clock_or_pointer_clock_divergence(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    projection = publisher.publish(
        [_event("bpcjv_event_" + "a" * 24, "2024-01-01")],
        coverage=_coverage(1),
        capture_observed_at="2026-08-17T07:55:47Z",
        published_at="2026-08-24T20:00:00Z",
    )
    manifest_path = tmp_path / "generations" / projection.generation_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["published_at"] = "not-a-clock"
    _rehash_manifest(tmp_path, projection.generation_id, manifest)
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_GENERATION_INVALID"):
        publisher.read_current()


def test_reader_rejects_symlinked_artifact(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    projection = publisher.publish([_event("bpcjv_event_" + "a" * 24, "2024-01-01")], coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    artifact = tmp_path / "generations" / projection.generation_id / "events.jsonl"
    outside = tmp_path / "outside.jsonl"
    artifact.rename(outside)
    artifact.symlink_to(outside)
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_ARTIFACT_INVALID"):
        publisher.read_current()


@pytest.mark.parametrize("mutation", ["nested_extra", "url_value", "rights_change"])
def test_closed_record_validator_rejects_nested_or_rights_mutation(tmp_path: Path, mutation: str) -> None:
    event = _event("bpcjv_event_" + "a" * 24, "2024-01-01")
    if mutation == "nested_extra":
        event["company"]["fuzzy_score"] = 0.99
    elif mutation == "url_value":
        event["event"]["description"] = "read https://private.example/source"
    else:
        event["authority"]["allowed_uses"] = ["display", "rank"]
    with pytest.raises(HistoricalEventError):
        HistoricalEventPublisher(tmp_path).publish([event], coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")


@pytest.mark.parametrize("state", ["resolved_without_id", "unresolved_with_id", "clock_divergence"])
def test_closed_record_validator_rejects_incoherent_identity_or_clock(tmp_path: Path, state: str) -> None:
    event = _event("bpcjv_event_" + "a" * 24, "2024-01-01")
    if state == "resolved_without_id":
        event["company"]["resolution_state"] = "resolved"
        event["company"]["resolution_basis"] = "current_catalog_only"
    elif state == "unresolved_with_id":
        event["company"]["security_id"] = "SEC:US-XNAS-ABC"
    else:
        event["event"]["observed_at"] = "2026-08-18T07:55:47Z"
    with pytest.raises(HistoricalEventError):
        HistoricalEventPublisher(tmp_path).publish(
            [event],
            coverage=_coverage(1),
            capture_observed_at="2026-08-17T07:55:47Z",
            published_at="2026-08-24T20:00:00Z",
        )


def test_failed_publish_keeps_last_good_pointer(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    first = publisher.publish([_event("bpcjv_event_" + "a" * 24, "2024-01-01")], coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    pointer_before = (tmp_path / "current.json").read_bytes()
    with pytest.raises(HistoricalEventError):
        publisher.publish([{"bad": "row"}], coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:01:00Z")
    assert (tmp_path / "current.json").read_bytes() == pointer_before
    assert publisher.read_current().generation_id == first.generation_id


def test_query_order_filters_and_cursor_are_deterministic() -> None:
    events = tuple([
        _event("bpcjv_event_" + "a" * 24, "2024-01-01", ticker="AAA"),
        _event("bpcjv_event_" + "b" * 24, "2025-01-01", ticker="BBB"),
        _event("bpcjv_event_" + "c" * 24, "2023-01-01", ticker="AAA", family="device"),
    ])
    page = query_events(events, q="AAA", family="all", stage=None, asset=None, from_date=None, to_date=None, limit=1, cursor=None, cursor_key=b"secret")
    assert [row["event"]["date"] for row in page.rows] == ["2024-01-01"]
    assert page.next_cursor
    next_page = query_events(events, q="AAA", family="all", stage=None, asset=None, from_date=None, to_date=None, limit=1, cursor=page.next_cursor, cursor_key=b"secret")
    assert [row["event"]["date"] for row in next_page.rows] == ["2023-01-01"]
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_CURSOR_QUERY_MISMATCH"):
        query_events(events, q="BBB", family="all", stage=None, asset=None, from_date=None, to_date=None, limit=1, cursor=page.next_cursor, cursor_key=b"secret")
    with pytest.raises(HistoricalEventError, match="HISTORICAL_EVENT_CURSOR_INVALID"):
        query_events(events, q=None, family="all", stage=None, asset=None, from_date=None, to_date=None, limit=1, cursor="A" * 10_000, cursor_key=b"secret")


def test_public_projection_contains_no_private_locator_or_hash_keys(tmp_path: Path) -> None:
    publisher = HistoricalEventPublisher(tmp_path)
    projection = publisher.publish([_event("bpcjv_event_" + "a" * 24, "2024-01-01")], coverage=_coverage(1), capture_observed_at="2026-08-17T07:55:47Z", published_at="2026-08-24T20:00:00Z")
    rendered = json.dumps({"events": projection.events})
    for forbidden in ("object_key", "company_url", "catalyst_url", "raw_row", "source_sha256"):
        assert forbidden not in rendered
