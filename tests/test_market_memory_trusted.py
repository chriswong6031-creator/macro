"""Adversarial W1B.1 tests for trusted regime publication and federation."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine import options_market_memory_context as options_context
from engine import options_signal_episode
from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_identity as identity
from engine.neuralweb import market_memory_pit as pit
from engine.neuralweb import market_memory_projection as projection
from engine.neuralweb import market_memory_trusted as trusted
from scripts import audit_options_market_memory_context as options_context_audit
from tests.test_market_memory_pit import (
    _api_client,
    _assert_private,
    _query_url,
)
from tests.test_market_memory_pit import (
    _packet as _w1a_packet,
)
from tests.test_options_signal_episode import (
    _campaign_episode,
    _campaign_h60_outcome,
    _episode,
)

SNAPSHOT_CLOCK = datetime(2026, 8, 10, 10, 0, 0, tzinfo=timezone.utc)
IDENTITY_CLOCK = SNAPSHOT_CLOCK + timedelta(seconds=1)
CAPTURE_CLOCK = SNAPSHOT_CLOCK + timedelta(seconds=2)
DEPLOYED_COMMIT = "a" * 40


@dataclass(frozen=True)
class Candidate:
    public: Path
    private: Path
    source: Path
    raw_body: bytes
    snapshot: dict
    identity_evidence: identity.CanaryIdentityEvidence


def _raw_regime(*, growth_score: float = 0.133) -> dict:
    return {
        "schema_version": 1,
        "asof": "2026-08-10",
        "date": "2026-08-10",
        "quad": "Q2",
        "quad_name": "forbidden human label",
        "label": "must never enter trusted public objects",
        "raw_quad": "Q2",
        "pending_quad": None,
        "pending_days": 0,
        "pending_need": 7,
        "growth_score": growth_score,
        "inflation_score": 0.4,
        "growth_confidence": 0.1,
        "inflation_confidence": 0.3,
        "confidence": 0.2,
        "liquidity_overlay": "contracting",
        "cycle_tag": "late",
        "transition_state": "TRANSITIONING",
        "transition_state_raw": "WEAKENING",
        "transition_ratcheted": True,
        "transition_dwell_remaining": 5,
        "transition_flags": {
            "flag_breadth_price": False,
            "flag_credit_equity": False,
            "flag_ratio_inflection": False,
            "flag_inflation_basket": False,
            "flag_confidence_decay": True,
            "flag_gex": False,
            "flag_rotation_persistence": True,
        },
        "options": {
            "signal_episode": "forbidden",
            "H+60": {"outcome": 0.9},
            "U-CHAIN": {"rank": 1},
        },
        "Prophet": {"candidate": True, "gate": True, "size": 1.0},
        "freshness": {
            "asof": "2026-08-10",
            "built_at": "2026-08-10T09:55:00Z",
            "age_days": 0,
            "age_sessions": 0,
            "max_age_sessions": 1,
            "stale": False,
        },
    }


def _write_raw(path: Path, *, growth_score: float = 0.133) -> bytes:
    body = (
        json.dumps(
            _raw_regime(growth_score=growth_score),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    path.write_bytes(body)
    return body


def _candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    growth_score: float = 0.133,
) -> Candidate:
    source = tmp_path / "latest.json"
    raw_body = _write_raw(source, growth_score=growth_score)
    monkeypatch.setattr(projection, "_utc_now", lambda: SNAPSHOT_CLOCK)
    snapshot = projection.build_macro_regime_snapshot(source)
    monkeypatch.setattr(identity, "_utc_now", lambda: IDENTITY_CLOCK)
    identity_evidence = identity.build_current_spy_identity()
    monkeypatch.setattr(trusted, "_utc_now", lambda: CAPTURE_CLOCK)
    return Candidate(
        public=tmp_path / "public" / "trusted-v1",
        private=tmp_path / "state" / "context-projection",
        source=source,
        raw_body=raw_body,
        snapshot=snapshot,
        identity_evidence=identity_evidence,
    )


def _capture(candidate: Candidate) -> pit.StoredMarketMemoryContext:
    return trusted.capture_trusted_regime_context(
        candidate.public,
        candidate.private,
        snapshot=candidate.snapshot,
        identity_evidence=candidate.identity_evidence,
        raw_source_body=candidate.raw_body,
        deployed_commit=DEPLOYED_COMMIT,
    )


def _options_context_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Candidate:
    snapshot_clock = datetime(2026, 8, 11, 14, 30, tzinfo=timezone.utc)
    identity_clock = snapshot_clock + timedelta(minutes=1)
    capture_clock = identity_clock + timedelta(seconds=1)
    source = tmp_path / "options-context-regime.json"
    raw = _raw_regime()
    raw.update({"asof": "2026-08-11", "date": "2026-08-11"})
    raw["freshness"].update(
        {"asof": "2026-08-11", "built_at": "2026-08-11T14:25:00Z"}
    )
    raw_body = (
        json.dumps(raw, allow_nan=False, sort_keys=True).encode("utf-8") + b"\n"
    )
    source.write_bytes(raw_body)
    monkeypatch.setattr(projection, "_utc_now", lambda: snapshot_clock)
    snapshot = projection.build_macro_regime_snapshot(source)
    monkeypatch.setattr(identity, "_utc_now", lambda: identity_clock)
    identity_evidence = identity.build_current_spy_identity()
    monkeypatch.setattr(trusted, "_utc_now", lambda: capture_clock)
    return Candidate(
        public=tmp_path / "options-context-public" / "trusted-v1",
        private=tmp_path / "options-context-private",
        source=source,
        raw_body=raw_body,
        snapshot=snapshot,
        identity_evidence=identity_evidence,
    )


def _episode_for_context(
    stored: pit.StoredMarketMemoryContext,
    *,
    source_event_id: str = "options-context-spy",
    seconds: int = 0,
) -> dict:
    clock = datetime.fromisoformat(
        stored.packet["clocks"]["event_time"].replace("Z", "+00:00")
    ) + timedelta(seconds=seconds)
    timestamp = clock.isoformat().replace("+00:00", "Z")
    return _episode(
        id=source_event_id,
        ts=timestamp,
        observed_at=timestamp,
        decision_at=timestamp,
        available_at=timestamp,
        source_snapshot_asof=timestamp,
        root="SPY",
        exp="2026-08-21",
        dte=10,
        oi_vintage="2026-08-10",
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        for nested in value.values():
            keys.update(_all_keys(nested))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for nested in value:
            keys.update(_all_keys(nested))
        return keys
    return set()


def _missing_packet_from_trusted(packet: mm.AsKnownAtContext) -> mm.AsKnownAtContext:
    identity_source_ids = set(packet["identity_receipt"]["source_receipt_ids"])
    sources = [
        copy.deepcopy(row)
        for row in packet["source_receipts"]
        if row["receipt_id"] in identity_source_ids
    ]
    features = []
    observed_at = packet["clocks"]["as_known_at"]
    for feature_id, spec in mm.CANONICAL_FEATURE_REGISTRY.items():
        features.append(
            {
                "feature_id": feature_id,
                "feature_role": "decision_time_context",
                "domain": spec.domain,
                "status": "missing",
                "value": None,
                "unit": spec.unit,
                "observed_at": observed_at,
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
    return mm.build_as_known_at_context(
        subject=copy.deepcopy(packet["subject"]),
        event_time=packet["clocks"]["event_time"],
        as_known_at=packet["clocks"]["as_known_at"],
        mode="operational_pit",
        source_receipts=sources,
        identity_receipt=copy.deepcopy(packet["identity_receipt"]),
        feature_receipts=features,
    )


def test_packet_policy_observes_only_macro_and_preserves_all_authority_fences(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    packet = trusted.build_trusted_packet(
        candidate.snapshot, candidate.identity_evidence
    )

    observed = [
        row for row in packet["feature_receipts"] if row["status"] == "observed"
    ]
    missing = [row for row in packet["feature_receipts"] if row["status"] == "missing"]
    assert [row["feature_id"] for row in observed] == ["macro.regime_state"]
    assert {row["feature_id"] for row in missing} == set(
        mm.CANONICAL_FEATURE_REGISTRY
    ) - {"macro.regime_state"}
    assert {row["source_id"] for row in packet["source_receipts"]} == {
        "security_master_membership",
        "market_calendar",
        "market_regime_store",
    }
    regime_source = next(
        row
        for row in packet["source_receipts"]
        if row["source_id"] == "market_regime_store"
    )
    assert regime_source["artifact_sha256"] == sha256(candidate.raw_body).hexdigest()
    assert regime_source["available_at"] == candidate.snapshot["observed_at"]
    assert regime_source["observed_at"] == candidate.snapshot["observed_at"]
    assert (
        regime_source["event_time"] == candidate.snapshot["source_artifact"]["built_at"]
    )
    assert observed[0]["source_receipt_ids"] == [regime_source["receipt_id"]]
    assert packet["authority"] == dict(mm.AUTHORITY)
    assert packet["authority"]["context_only"] is True
    assert packet["authority"]["proposal_weight"] == 0
    assert packet["authority"]["may_write_options_episode"] is False
    assert packet["authority"]["may_append_outcome"] is False
    assert packet["authority"]["may_train_prophet"] is False
    assert (
        next(
            row for row in missing if row["feature_id"] == "options.chain_surface_state"
        )["value"]
        is None
    )
    assert (
        next(
            row
            for row in missing
            if row["feature_id"] == "prophet_context.signal_state"
        )["value"]
        is None
    )
    assert _all_keys(observed[0]["value"]).isdisjoint(
        {"label", "outcome", "rank", "gate", "size", "trade", "signal_episode"}
    )

    with pytest.raises(pit.MarketMemoryStoreError, match="observed-feature"):
        trusted._validate_trusted_packet(_w1a_packet())


def test_capture_writes_private_evidence_before_public_and_reads_exactly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    events: list[tuple[str, str]] = []
    original_private_write = trusted._write_exact_bytes_create_once
    original_public_write = pit._write_create_once
    original_head = pit._replace_head

    def trace_private(
        root: Path,
        path: Path,
        body: bytes,
        *,
        label: str,
        limit: int,
    ) -> bool:
        events.append(("private", label))
        return original_private_write(root, path, body, label=label, limit=limit)

    def trace_public(root: Path, path: Path, body: bytes, *, label: str) -> bool:
        events.append(("public", label))
        return original_public_write(root, path, body, label=label)

    def trace_head(root: Path, head: dict) -> None:
        events.append(("head", str(head["generation_id"])))
        original_head(root, head)

    monkeypatch.setattr(trusted, "_write_exact_bytes_create_once", trace_private)
    monkeypatch.setattr(pit, "_write_create_once", trace_public)
    monkeypatch.setattr(pit, "_replace_head", trace_head)
    stored = _capture(candidate)
    receipt = stored.capture_receipt

    private_positions = [
        index for index, event in enumerate(events) if event[0] == "private"
    ]
    feature_position = events.index(("public", "trusted feature object"))
    packet_position = events.index(("public", "trusted packet object"))
    assert (
        private_positions
        and max(private_positions) < feature_position < packet_position
    )
    assert events[-1][0] == "head"

    raw_path = (
        candidate.private
        / "raw_objects"
        / receipt["source_evidence"]["raw_source_sha256"][:2]
        / f"{receipt['source_evidence']['raw_source_sha256']}.json"
    )
    membership_path = (
        candidate.private
        / "membership_objects"
        / receipt["source_evidence"]["membership_artifact_sha256"][:2]
        / (f"{receipt['source_evidence']['membership_artifact_sha256']}.json")
    )
    calendar_path = (
        candidate.private
        / "calendar_objects"
        / receipt["source_evidence"]["calendar_artifact_sha256"][:2]
        / (f"{receipt['source_evidence']['calendar_artifact_sha256']}.json")
    )
    assert raw_path.read_bytes() == candidate.raw_body
    assert (
        membership_path.read_bytes()
        == candidate.identity_evidence.membership_artifact_bytes
    )
    assert (
        calendar_path.read_bytes()
        == candidate.identity_evidence.calendar_artifact_bytes
    )
    assert not list(candidate.public.glob("raw_objects/**/*"))
    assert not list(candidate.public.glob("membership_objects/**/*"))
    assert not list(candidate.public.glob("calendar_objects/**/*"))

    reader = trusted.TrustedFileAsKnownAtReader(candidate.public)
    by_query = reader.read_stored_as_known_at(
        subject=stored.packet["subject"],
        event_time=stored.packet["clocks"]["event_time"],
        as_known_at=stored.packet["clocks"]["as_known_at"],
    )
    by_context = reader.read_stored_context_id(stored.packet["context_id"])
    assert by_query == stored
    assert by_context == stored
    assert (
        receipt["packet_sha256"] == sha256(_canonical_bytes(stored.packet)).hexdigest()
    )
    assert (
        receipt["source_evidence"]["raw_source_sha256"]
        == sha256(candidate.raw_body).hexdigest()
    )
    assert (
        receipt["source_evidence"]["membership_artifact_sha256"]
        == sha256(candidate.identity_evidence.membership_artifact_bytes).hexdigest()
    )
    assert (
        receipt["source_evidence"]["calendar_artifact_sha256"]
        == sha256(candidate.identity_evidence.calendar_artifact_bytes).hexdigest()
    )


def test_identical_retry_is_idempotent_and_does_not_republish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    first = _capture(candidate)
    head = (candidate.public / "HEAD.json").read_bytes()
    private_receipts = list(candidate.private.glob("capture_receipts/*/*.json"))

    monkeypatch.setattr(
        trusted, "_utc_now", lambda: CAPTURE_CLOCK + timedelta(seconds=5)
    )
    second = _capture(candidate)

    assert second == first
    assert (candidate.public / "HEAD.json").read_bytes() == head
    assert list(candidate.private.glob("capture_receipts/*/*.json")) == private_receipts
    assert len(list(candidate.public.glob("objects/*/*.json"))) == 1
    assert len(list(candidate.public.glob("feature_objects/*/*.json"))) == 1
    assert len(list(candidate.public.glob("contexts/*/*.json"))) == 1
    assert len(list(candidate.public.glob("queries/*/*.json"))) == 1


@pytest.mark.parametrize(
    ("target", "mutation"),
    [
        ("raw", "missing"),
        ("membership", "corrupt"),
        ("calendar", "missing"),
        ("receipt", "corrupt"),
    ],
)
def test_idempotent_retry_revalidates_all_private_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target: str,
    mutation: str,
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    receipt = stored.capture_receipt
    evidence = receipt["source_evidence"]
    paths = {
        "raw": trusted._private_object_path(
            candidate.private, "raw", evidence["raw_source_sha256"]
        ),
        "membership": trusted._private_object_path(
            candidate.private,
            "membership",
            evidence["membership_artifact_sha256"],
        ),
        "calendar": trusted._private_object_path(
            candidate.private, "calendar", evidence["calendar_artifact_sha256"]
        ),
        "receipt": trusted._private_receipt_path(
            candidate.private, receipt["capture_id"]
        ),
    }
    path = paths[target]
    if mutation == "missing":
        path.unlink()
    else:
        path.write_bytes(b"{}")
    monkeypatch.setattr(
        trusted, "_utc_now", lambda: CAPTURE_CLOCK + timedelta(seconds=5)
    )

    with pytest.raises(pit.MarketMemoryPITError):
        _capture(candidate)


def test_trusted_capture_receipt_schema_seals_evidence_and_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    receipt = _capture(candidate).capture_receipt
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "contracts"
            / "market_memory"
            / "trusted_capture_receipt.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)

    mutants = []
    authority = copy.deepcopy(receipt)
    authority["authority"]["may_train_prophet"] = True
    mutants.append(authority)
    component_claim = copy.deepcopy(receipt)
    component_claim["evidence_policy"]["component_source_receipts_authenticated"] = True
    mutants.append(component_claim)
    extra_feature = copy.deepcopy(receipt)
    extra_feature["observed_feature_ids"].append("options.chain_surface_state")
    mutants.append(extra_feature)
    extra_field = copy.deepcopy(receipt)
    extra_field["outcome"] = {"forward_return": 1.0}
    mutants.append(extra_field)

    for mutant in mutants:
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(mutant)


def test_persisted_feature_object_matches_its_declared_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    feature_path = (
        candidate.public / stored.capture_receipt["feature_snapshot"]["object_key"]
    )
    feature = json.loads(feature_path.read_text(encoding="utf-8"))
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "contracts/market_memory/macro_regime_feature_object.v1.schema.json"
        ).read_text(encoding="utf-8")
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(feature)
    assert feature["schema"] == projection.FEATURE_OBJECT_SCHEMA
    assert trusted._canonical_bytes(feature) == feature_path.read_bytes()
    assert (
        sha256(feature_path.read_bytes()).hexdigest()
        == (stored.capture_receipt["feature_snapshot"]["content_sha256"])
    )


def test_changed_raw_or_identity_bytes_cannot_cross_any_publication_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    changed_raw = candidate.raw_body + b" "
    with pytest.raises(
        trusted.MarketMemoryTrustedCaptureError, match="raw regime source differs"
    ):
        trusted.capture_trusted_regime_context(
            candidate.public,
            candidate.private,
            snapshot=candidate.snapshot,
            identity_evidence=candidate.identity_evidence,
            raw_source_body=changed_raw,
            deployed_commit=DEPLOYED_COMMIT,
        )
    assert not candidate.public.exists()
    assert not candidate.private.exists()

    changed_identity = replace(
        candidate.identity_evidence,
        membership_artifact_bytes=(
            candidate.identity_evidence.membership_artifact_bytes + b" "
        ),
    )
    with pytest.raises(identity.MarketMemoryIdentityError):
        trusted.capture_trusted_regime_context(
            candidate.public,
            candidate.private,
            snapshot=candidate.snapshot,
            identity_evidence=changed_identity,
            raw_source_body=candidate.raw_body,
            deployed_commit=DEPLOYED_COMMIT,
        )
    assert not candidate.public.exists()
    assert not candidate.private.exists()


def test_same_exact_query_rejects_a_new_self_consistent_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = _candidate(monkeypatch, tmp_path)
    stored = _capture(first)
    changed_source = tmp_path / "changed.json"
    changed_body = _write_raw(changed_source, growth_score=0.25)
    monkeypatch.setattr(projection, "_utc_now", lambda: SNAPSHOT_CLOCK)
    changed_snapshot = projection.build_macro_regime_snapshot(changed_source)

    with pytest.raises(
        trusted.MarketMemoryTrustedCaptureError,
        match="already has a different immutable capture",
    ):
        trusted.capture_trusted_regime_context(
            first.public,
            first.private,
            snapshot=changed_snapshot,
            identity_evidence=first.identity_evidence,
            raw_source_body=changed_body,
            deployed_commit=DEPLOYED_COMMIT,
        )
    exact = trusted.TrustedFileAsKnownAtReader(first.public).read_as_known_at(
        subject=stored.packet["subject"],
        event_time=stored.packet["clocks"]["event_time"],
        as_known_at=stored.packet["clocks"]["as_known_at"],
    )
    assert exact == stored.packet


def test_crash_before_head_is_invisible_and_later_retry_recovers_original_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    packet = trusted.build_trusted_packet(
        candidate.snapshot, candidate.identity_evidence
    )
    original_replace = pit._replace_head
    calls = 0

    def fail_capture_head(root: Path, head: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise pit.MarketMemoryStoreError("injected trusted HEAD crash")
        original_replace(root, head)

    monkeypatch.setattr(pit, "_replace_head", fail_capture_head)
    with pytest.raises(pit.MarketMemoryStoreError, match="trusted HEAD crash"):
        _capture(candidate)

    reader = trusted.TrustedFileAsKnownAtReader(candidate.public)
    with pytest.raises(pit.MarketMemoryContextNotFound):
        reader.read_stored_as_known_at(
            subject=packet["subject"],
            event_time=packet["clocks"]["event_time"],
            as_known_at=packet["clocks"]["as_known_at"],
        )
    with pytest.raises(pit.MarketMemoryContextNotFound):
        reader.read_stored_context_id(packet["context_id"])

    monkeypatch.setattr(pit, "_replace_head", original_replace)
    monkeypatch.setattr(
        trusted, "_utc_now", lambda: CAPTURE_CLOCK + timedelta(seconds=5)
    )
    recovered = _capture(candidate)
    assert recovered.packet == packet
    assert len(trusted._load_state(candidate.public).generation["captures"]) == 1
    assert len(list(candidate.public.glob("queries/*/*.json"))) == 1


@pytest.mark.parametrize("target", ["packet", "feature", "receipt", "head"])
def test_reader_fails_closed_on_tampered_public_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    receipt = stored.capture_receipt
    if target == "packet":
        path = candidate.public / receipt["object_key"]
    elif target == "feature":
        path = candidate.public / receipt["feature_snapshot"]["object_key"]
    elif target == "receipt":
        path = pit._query_path(candidate.public, receipt["query_id"])
    else:
        path = candidate.public / "HEAD.json"
    path.write_bytes(b"{}")

    with pytest.raises(pit.MarketMemoryStoreError):
        trusted.TrustedFileAsKnownAtReader(candidate.public).read_stored_as_known_at(
            subject=stored.packet["subject"],
            event_time=stored.packet["clocks"]["event_time"],
            as_known_at=stored.packet["clocks"]["as_known_at"],
        )


@pytest.mark.parametrize("target", ["packet", "feature", "receipt", "generation"])
def test_reader_rejects_oversized_public_objects_before_parsing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    receipt = stored.capture_receipt
    if target == "packet":
        path = candidate.public / receipt["object_key"]
        bound = pit._MAX_PACKET_BYTES
    elif target == "feature":
        path = candidate.public / receipt["feature_snapshot"]["object_key"]
        bound = trusted._MAX_FEATURE_BYTES
    elif target == "receipt":
        path = pit._query_path(candidate.public, receipt["query_id"])
        bound = trusted._MAX_RECEIPT_BYTES
    else:
        state = trusted._load_state(candidate.public)
        path = pit._generation_path(candidate.public, state.head["generation_id"])
        bound = trusted._MAX_GENERATION_BYTES
    path.write_bytes(b"{" + b" " * bound + b"}")

    with pytest.raises(pit.MarketMemoryStoreError, match="exceeds|large|size"):
        trusted.TrustedFileAsKnownAtReader(candidate.public).read_stored_as_known_at(
            subject=stored.packet["subject"],
            event_time=stored.packet["clocks"]["event_time"],
            as_known_at=stored.packet["clocks"]["as_known_at"],
        )


def test_exact_reader_has_no_nearest_latest_or_context_guessing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    reader = trusted.TrustedFileAsKnownAtReader(candidate.public)

    with pytest.raises(pit.MarketMemoryContextNotFound):
        reader.read_as_known_at(
            subject=stored.packet["subject"],
            event_time=stored.packet["clocks"]["event_time"],
            as_known_at="2026-08-10T10:00:01.000001Z",
        )
    with pytest.raises(pit.MarketMemoryContextNotFound):
        reader.read_stored_context_id("mmctx_" + "f" * 64)
    assert not hasattr(reader, "read_latest")
    assert not hasattr(reader, "read_nearest")


def test_trusted_pinned_generation_reads_published_empty_ancestor_and_rejects_orphan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    trusted.initialize_trusted_store(candidate.public)
    reader = trusted.TrustedFileAsKnownAtReader(candidate.public)
    empty = reader.read_pinned_generation()
    stored = _capture(candidate)
    current = reader.read_pinned_generation()

    assert empty.captures == ()
    assert reader.read_pinned_generation(generation_id=empty.generation_id) == empty
    assert (
        reader.read_stored_from_pinned_generation(
            current, query_id=stored.capture_receipt["query_id"]
        )
        == stored
    )
    state = trusted._load_state(candidate.public)
    orphan = pit._new_generation(
        store_id=state.manifest["store_id"],
        previous_generation_id=current.generation_id,
        captures=[row.as_dict() for row in current.captures],
    )
    orphan_body = pit._canonical_bytes(orphan)
    pit._write_create_once(
        candidate.public,
        pit._generation_path(candidate.public, orphan["generation_id"]),
        orphan_body,
        label="test trusted crash-orphan generation",
    )
    with pytest.raises(pit.MarketMemoryContextNotFound, match="not published"):
        reader.read_pinned_generation(generation_id=orphan["generation_id"])


def test_trusted_repeated_pin_rewalks_ancestor_under_unchanged_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    _capture(candidate)
    reader = trusted.TrustedFileAsKnownAtReader(candidate.public)
    reader.read_pinned_generation()
    state = trusted._load_state(candidate.public)
    ancestor_id = state.generation["previous_generation_id"]
    assert ancestor_id is not None
    pit._generation_path(candidate.public, ancestor_id).unlink()

    with pytest.raises(pit.MarketMemoryStoreError, match="unavailable"):
        reader.read_pinned_generation()


def test_trusted_pinned_receipt_rejects_cross_store_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    first = _capture(candidate)
    second_candidate = replace(
        candidate,
        public=tmp_path / "second-public" / "trusted-v1",
        private=tmp_path / "second-state" / "context-projection",
    )
    second = _capture(second_candidate)
    first_state = trusted._load_state(candidate.public)
    genesis_id = first_state.generation["previous_generation_id"]
    assert genesis_id is not None
    forged = pit._new_generation(
        store_id=first_state.manifest["store_id"],
        previous_generation_id=genesis_id,
        captures=[pit._capture_entry(second.capture_receipt)],
    )
    body = pit._canonical_bytes(forged)
    pit._write_create_once(
        candidate.public,
        pit._generation_path(candidate.public, forged["generation_id"]),
        body,
        label="test trusted cross-owner generation",
    )
    pit._replace_head(candidate.public, pit._new_head(forged, generation_body=body))
    receipt_body = pit._canonical_bytes(second.capture_receipt)
    pit._query_path(candidate.public, second.capture_receipt["query_id"]).write_bytes(
        receipt_body
    )
    pit._context_path(
        candidate.public, second.capture_receipt["context_id"]
    ).write_bytes(receipt_body)
    reader = trusted.TrustedFileAsKnownAtReader(candidate.public)
    pinned = reader.read_pinned_generation()

    with pytest.raises(pit.MarketMemoryStoreError, match="another store"):
        reader.read_pinned_capture_receipt(
            pinned, query_id=second.capture_receipt["query_id"]
        )
    assert first.capture_receipt["store_id"] != second.capture_receipt["store_id"]


def test_composite_serves_each_exact_store_and_rejects_cross_store_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    trusted_stored = _capture(candidate)
    w1a_root = tmp_path / "w1a"
    generic_w1a = _w1a_packet()
    monkeypatch.setattr(
        pit,
        "_utc_now",
        lambda: datetime(2026, 8, 7, 20, 5, 30, tzinfo=timezone.utc),
    )
    pit.capture_context(w1a_root, generic_w1a)
    # Query normalization samples the W1A process clock even when the trusted
    # store is consulted first; restore it past both exact capture cutoffs.
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURE_CLOCK)
    composite = trusted.CompositeAsKnownAtReader(w1a_root, candidate.public)

    assert (
        composite.read_as_known_at(
            subject=trusted_stored.packet["subject"],
            event_time=trusted_stored.packet["clocks"]["event_time"],
            as_known_at=trusted_stored.packet["clocks"]["as_known_at"],
        )
        == trusted_stored.packet
    )
    assert (
        composite.read_as_known_at(
            subject=generic_w1a["subject"],
            event_time=generic_w1a["clocks"]["event_time"],
            as_known_at=generic_w1a["clocks"]["as_known_at"],
        )
        == generic_w1a
    )

    conflict_root = tmp_path / "w1a-conflict"
    conflicting = _missing_packet_from_trusted(trusted_stored.packet)
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURE_CLOCK)
    pit.capture_context(conflict_root, conflicting)
    conflicted = trusted.CompositeAsKnownAtReader(conflict_root, candidate.public)
    with pytest.raises(pit.MarketMemoryStoreError, match="ambiguously published"):
        conflicted.read_as_known_at(
            subject=trusted_stored.packet["subject"],
            event_time=trusted_stored.packet["clocks"]["event_time"],
            as_known_at=trusted_stored.packet["clocks"]["as_known_at"],
        )


def test_private_api_serves_exact_trusted_capture_with_hash_bound_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    trusted_stored = _capture(candidate)
    w1a_root = tmp_path / "w1a"
    monkeypatch.setattr(
        pit,
        "_utc_now",
        lambda: datetime(2026, 8, 7, 20, 5, 30, tzinfo=timezone.utc),
    )
    pit.capture_context(w1a_root, _w1a_packet())
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURE_CLOCK)
    monkeypatch.setenv("MARKET_MEMORY_CONTEXT_STORE_DIR", str(w1a_root))
    monkeypatch.setenv("MARKET_MEMORY_TRUSTED_STORE_DIR", str(candidate.public))
    client = _api_client()

    exact = client.get(_query_url(trusted_stored.packet))
    by_id = client.get(
        f"/api/market-memory/v1/context/{trusted_stored.packet['context_id']}"
    )

    for response in (exact, by_id):
        assert response.status_code == 200
        _assert_private(response)
        assert response.json() == trusted_stored.response_payload()
        assert response.headers["etag"] == (
            f'"{trusted_stored.capture_receipt["packet_sha256"]}"'
        )
        assert (
            response.headers["x-market-memory-capture-id"]
            == trusted_stored.capture_receipt["capture_id"]
        )


def test_composite_never_falls_back_around_trusted_corruption(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    trusted_stored = _capture(candidate)
    fallback = _missing_packet_from_trusted(trusted_stored.packet)
    w1a_root = tmp_path / "w1a"
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURE_CLOCK)
    pit.capture_context(w1a_root, fallback)
    packet_path = candidate.public / trusted_stored.capture_receipt["object_key"]
    packet_path.write_bytes(b"{}")

    with pytest.raises(pit.MarketMemoryStoreError):
        trusted.CompositeAsKnownAtReader(
            w1a_root, candidate.public
        ).read_stored_as_known_at(
            subject=trusted_stored.packet["subject"],
            event_time=trusted_stored.packet["clocks"]["event_time"],
            as_known_at=trusted_stored.packet["clocks"]["as_known_at"],
        )


def test_public_objects_strip_labels_outcomes_options_episodes_and_prophet_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    feature_body = (
        candidate.public / stored.capture_receipt["feature_snapshot"]["object_key"]
    ).read_bytes()
    packet_body = (candidate.public / stored.capture_receipt["object_key"]).read_bytes()
    public_text = (feature_body + packet_body).decode("utf-8").lower()

    assert b'"label"' in candidate.raw_body
    assert b'"signal_episode"' in candidate.raw_body
    assert b'"Prophet"' in candidate.raw_body
    for forbidden in (
        '"label"',
        '"outcome"',
        '"signal_episode"',
        '"h+60"',
        '"u-chain"',
        '"candidate"',
    ):
        assert forbidden not in public_text
    implementation = Path(trusted.__file__).read_text(encoding="utf-8").lower()
    assert "options.signal_episode" not in implementation
    assert "h+60" not in implementation
    assert "u-chain" not in implementation
    assert "build_prophet" not in implementation
    assert "write_prophet" not in implementation


def _empty_w1a_store(root: Path) -> Path:
    store = pit.validate_store_root(root)
    pit._mkdir_durable(store)
    pit._initialize_or_load_store(store)
    return store


def _options_context_reader(
    candidate: Candidate, w1a_root: Path
) -> options_context.PinnedCompositeAsKnownAtReader:
    composite = trusted.CompositeAsKnownAtReader(w1a_root, candidate.public)
    return options_context.PinnedCompositeAsKnownAtReader(composite)


def test_options_context_reference_binds_only_the_exact_requested_as_of_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _options_context_candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    w1a_root = _empty_w1a_store(tmp_path / "options-context-w1a")
    monkeypatch.setattr(
        pit,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc),
    )
    reader = _options_context_reader(candidate, w1a_root)
    episode = _episode_for_context(stored)
    reference = options_context.resolve_episode_context_reference(
        episode, reader=reader
    )

    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "contracts/options/options.market_memory_context_reference.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(reference)
    assert reference["disposition"] == "bound"
    assert reference["reason"] is None
    assert reference["owner"]["record_sha256"] == sha256(
        _canonical_bytes(episode)
    ).hexdigest()
    assert reference["query"] == {
        "subject": stored.packet["subject"],
        "identity_config_sha256": candidate.identity_evidence.config_sha256,
        "event_time": episode["event_time"],
        "as_known_at": episode["available_at"],
        "mode": "operational_pit",
        "fallback_policy": "exact_no_fallback",
    }
    assert reference["context"]["context_id"] == stored.packet["context_id"]
    assert reference["context"]["capture_id"] == stored.capture_receipt["capture_id"]
    assert (
        reference["context"]["capture_schema"]
        == trusted.TRUSTED_CAPTURE_RECEIPT_SCHEMA
    )
    assert reference["evidence_policy"] == options_context.EVIDENCE_POLICY
    assert reference["authority"] == dict(mm.AUTHORITY)
    assert {
        "feature_values",
        "coordinates",
        "outcome",
        "forward_return",
        "selection",
        "trade",
    }.isdisjoint(_all_keys(reference))

    one_second_later = _episode_for_context(
        stored, source_event_id="options-context-spy-later", seconds=1
    )
    absent = options_context.resolve_episode_context_reference(
        one_second_later, reader=reader
    )
    assert absent["disposition"] == "abstained"
    assert absent["reason"] == "exact_requested_as_of_context_absent"
    assert absent["context"] is None


def test_options_context_binds_a_prospective_campaign_at_its_crossing_clock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _options_context_candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    event_time = stored.packet["clocks"]["event_time"]
    available_at = stored.packet["clocks"]["as_known_at"]
    crossing_clock = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    first_clock = (crossing_clock - timedelta(minutes=1)).isoformat().replace(
        "+00:00", "Z"
    )

    common = {
        "root": "SPY",
        "exp": "2026-08-21",
        "strike": 105.0,
        "right": "C",
        "dte": 10,
        "size": 10_000,
        "avg_price": 1.5,
        "premium": 1_500_000.0,
        "vol_gt_oi": True,
        "oi_vintage": "2026-08-10",
    }
    first = _episode(
        id="prospective-first",
        ts=first_clock,
        observed_at=first_clock,
        decision_at=first_clock,
        available_at=first_clock,
        source_snapshot_asof=first_clock,
        **common,
    )
    crossing = _episode(
        id="prospective-crossing",
        ts=event_time,
        observed_at=available_at,
        decision_at=available_at,
        available_at=available_at,
        source_snapshot_asof=available_at,
        **common,
    )
    episodes = [first, crossing]
    outcomes = [_campaign_h60_outcome(row) for row in episodes]
    campaigns, pending = options_signal_episode.derive_campaigns(episodes, outcomes)
    assert pending == []
    assert len(campaigns) == 1
    assert campaigns[0]["evidence_phase"] == "prospective_after_rule_freeze"

    w1a_root = _empty_w1a_store(tmp_path / "prospective-campaign-w1a")
    monkeypatch.setattr(
        pit,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc),
    )
    reference = options_context.resolve_campaign_context_reference(
        campaigns[0],
        episodes=episodes,
        h60_outcomes=outcomes,
        reader=_options_context_reader(candidate, w1a_root),
    )

    assert reference["disposition"] == "bound"
    assert reference["owner"]["event_time"] == event_time
    assert reference["owner"]["requested_as_of"] == available_at
    assert (
        reference["owner"]["requested_as_of_basis"]
        == "campaign_formed_at_anchor_available_at"
    )
    assert reference["context"]["context_id"] == stored.packet["context_id"]


def test_options_context_rejects_a_reader_that_returns_a_nearby_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _options_context_candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    episode = _episode_for_context(
        stored, source_event_id="options-context-nearby", seconds=1
    )

    class NearbyReader:
        def read_stored_as_known_at(
            self, **_query: object
        ) -> pit.StoredMarketMemoryContext:
            return stored

    with pytest.raises(
        options_context.OptionsMarketMemoryContextError,
        match="clocks differ from the exact options request",
    ):
        options_context.resolve_episode_context_reference(
            episode, reader=NearbyReader()
        )


def test_options_context_abstains_before_lookup_for_retrospective_or_unsupported_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class ForbiddenReader:
        def read_stored_as_known_at(
            self, **_query: object
        ) -> pit.StoredMarketMemoryContext:
            pytest.fail("an ineligible owner must not reach Market Memory lookup")

    first = _campaign_episode("retro-first", 1_500_000.0)
    second = _campaign_episode(
        "retro-second", 1_500_000.0, available_at="2026-07-02T14:32:00Z"
    )
    episodes = [first, second]
    outcomes = [_campaign_h60_outcome(row) for row in episodes]
    campaigns, pending = options_signal_episode.derive_campaigns(episodes, outcomes)
    assert pending == []
    assert len(campaigns) == 1
    retrospective = options_context.resolve_campaign_context_reference(
        campaigns[0],
        episodes=episodes,
        h60_outcomes=outcomes,
        reader=ForbiddenReader(),
    )
    assert retrospective["disposition"] == "abstained"
    assert retrospective["reason"] == "campaign_retrospective_discovery"
    assert retrospective["query"]["subject"] is None

    canary_identity = options_context.load_canary_identity_snapshot()
    unsupported = options_context.resolve_episode_context_reference(
        first,
        reader=ForbiddenReader(),
        canary_identity=canary_identity,
    )
    assert unsupported["disposition"] == "abstained"
    assert unsupported["reason"] == "identity_not_operationally_supported"
    assert unsupported["query"]["subject"] is None

    with pytest.raises(
        options_context.OptionsMarketMemoryContextError,
        match="differs from its validated config bytes",
    ):
        options_context.CanaryIdentitySnapshot(
            symbol=canary_identity.symbol,
            subject_id=canary_identity.subject_id,
            instrument_id=canary_identity.instrument_id,
            config_sha256="f" * 64,
            config_body=canary_identity.config_body,
        )
    with pytest.raises(TypeError):
        options_context.EVIDENCE_POLICY[
            "training_eligible"
        ] = True  # type: ignore[index]


def test_options_context_audit_seals_sorted_owners_generations_and_closed_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _options_context_candidate(monkeypatch, tmp_path)
    stored = _capture(candidate)
    w1a_root = _empty_w1a_store(tmp_path / "audit-w1a")
    monkeypatch.setattr(
        pit,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc),
    )
    reader = _options_context_reader(candidate, w1a_root)
    bound = options_context.resolve_episode_context_reference(
        _episode_for_context(stored), reader=reader
    )
    unsupported = options_context.resolve_episode_context_reference(
        _campaign_episode("audit-unsupported", 50_000.0), reader=reader
    )
    references = sorted(
        [unsupported, bound],
        key=lambda row: (row["owner"]["schema"], row["owner"]["id"]),
    )
    sources = [
        {
            "path": "config/market_memory_canary.v1.json",
            "sha256": "1" * 64,
            "bytes": 1,
            "record_count": 1,
        },
        {
            "path": "data/options_signal_episode/campaigns.jsonl",
            "sha256": "2" * 64,
            "bytes": 2,
            "record_count": 0,
        },
        {
            "path": "data/options_signal_episode/episodes.jsonl",
            "sha256": "3" * 64,
            "bytes": 3,
            "record_count": 2,
        },
        {
            "path": "data/options_signal_episode/outcomes_h60.jsonl",
            "sha256": "4" * 64,
            "bytes": 4,
            "record_count": 0,
        },
    ]
    audit = options_context.build_audit_receipt(
        references=references,
        source_artifacts=sources,
        context_generations=reader.generation_receipts(),
        audited_at="2026-08-11T16:00:00Z",
    )

    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "contracts/options/options.market_memory_context_audit.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(audit)
    assert audit["counts"] == {
        "references": 2,
        "episode_references": 2,
        "campaign_references": 0,
        "bound": 1,
        "abstained": 1,
        "campaign_retrospective_discovery": 0,
        "identity_not_operationally_supported": 1,
        "exact_requested_as_of_context_absent": 0,
    }
    assert [row["profile"] for row in audit["context_generations"]] == sorted(
        row["profile"] for row in audit["context_generations"]
    )
    assert (
        options_context.validate_audit_receipt(audit, references=references) == audit
    )

    reversed_references = list(reversed(references))
    with pytest.raises(
        options_context.OptionsMarketMemoryContextError, match="sorted"
    ):
        options_context.build_audit_receipt(
            references=reversed_references,
            source_artifacts=sources,
            context_generations=reader.generation_receipts(),
            audited_at="2026-08-11T16:00:00Z",
        )
    tampered = copy.deepcopy(audit)
    tampered["counts"]["bound"] = 2
    with pytest.raises(options_context.OptionsMarketMemoryContextError):
        options_context.validate_audit_receipt(tampered, references=references)


def test_options_context_live_audit_replays_the_frozen_repository_corpus(
    tmp_path: Path,
) -> None:
    source_root = Path(__file__).resolve().parents[1]
    repository_root = tmp_path / "repository"
    data_root = repository_root / "data/options_signal_episode"
    config_root = repository_root / "config"
    data_root.mkdir(parents=True)
    config_root.mkdir()
    for name in ("episodes.jsonl", "campaigns.jsonl", "outcomes_h60.jsonl"):
        source = source_root / "data/options_signal_episode" / name
        (data_root / name).write_bytes(source.read_bytes())
    config_path = config_root / "market_memory_canary.v1.json"
    config_path.write_bytes(
        (source_root / "config/market_memory_canary.v1.json").read_bytes()
    )
    w1a_root = _empty_w1a_store(tmp_path / "live-audit-w1a")
    trusted_root = tmp_path / "live-audit-trusted"
    trusted.initialize_trusted_store(trusted_root)

    audit = options_context_audit.build_live_audit(
        repository_root=repository_root,
        w1a_store_root=w1a_root,
        trusted_store_root=trusted_root,
        config_path=config_path,
    )

    episode_count = len(
        options_signal_episode._decode_jsonl(
            (data_root / "episodes.jsonl").read_bytes(),
            data_root / "episodes.jsonl",
        )
    )
    campaign_count = len(
        options_signal_episode._decode_jsonl(
            (data_root / "campaigns.jsonl").read_bytes(),
            data_root / "campaigns.jsonl",
        )
    )
    assert audit["counts"]["references"] == episode_count + campaign_count
    assert audit["counts"]["episode_references"] == episode_count
    assert audit["counts"]["campaign_references"] == campaign_count
    assert audit["counts"]["bound"] == 0
    assert audit["counts"]["abstained"] == episode_count + campaign_count
    assert [row["path"] for row in audit["source_artifacts"]] == [
        "config/market_memory_canary.v1.json",
        "data/options_signal_episode/campaigns.jsonl",
        "data/options_signal_episode/episodes.jsonl",
        "data/options_signal_episode/outcomes_h60.jsonl",
    ]
