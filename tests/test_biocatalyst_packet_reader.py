"""W7-B pins for the single allowlisted operating-packet reader."""
from __future__ import annotations

import copy
import json

import pytest

from engine.biocatalyst import packet_reader
from engine.biocatalyst.packet_producer import operating_packet_bytes
from engine.biocatalyst.packet_reader import (
    NEURAL_WEB_READER_ID,
    OperatingPacketReaderError,
    read_operating_packet,
    register_operating_packet_reader,
    registered_reader_ids,
)
from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256

from tests.test_biocatalyst_packet_producer import (  # noqa: F401  (fixture helpers)
    EVALUATED_AT,
    _build,
    _projection,
    _reads,
    _sector_packet,
)


READ_AT = "2026-08-01T15:05:00Z"


@pytest.fixture(autouse=True)
def _clean_registry():
    packet_reader._reset_reader_registry()
    yield
    packet_reader._reset_reader_registry()


@pytest.fixture()
def registered() -> str:
    register_operating_packet_reader(NEURAL_WEB_READER_ID, consumer="neural_web")
    return NEURAL_WEB_READER_ID


def _packet(**kwargs) -> dict:
    return _build(**kwargs)


def _contradicting_packet() -> dict:
    reads = _reads(
        **{
            "biocatalyst.trials.change_tape.v1": {
                "contradictions": [
                    {
                        "kind": "registry_value_disagreement",
                        "entity_ref": "trial:NCT00000001",
                        "detail": "primary completion date disagrees across versions",
                    }
                ],
                "corrections": [
                    {
                        "kind": "registry_correction",
                        "entity_ref": "trial:NCT00000001",
                        "detail": "sponsor corrected a typo in the official title",
                    }
                ],
            }
        }
    )
    return _build(owner_projection_reads=reads)


def test_exactly_one_reader_may_be_registered(registered: str) -> None:
    assert registered_reader_ids() == (NEURAL_WEB_READER_ID,)
    # A second registration fails, including a re-registration of the same id.
    with pytest.raises(OperatingPacketReaderError, match="reader_allowlist_exhausted"):
        register_operating_packet_reader(NEURAL_WEB_READER_ID, consumer="neural_web")
    with pytest.raises(OperatingPacketReaderError, match="reader_allowlist_exhausted"):
        register_operating_packet_reader(NEURAL_WEB_READER_ID, consumer="mastermind_ai")
    assert registered_reader_ids() == (NEURAL_WEB_READER_ID,)


def test_a_reader_outside_the_allowlist_is_refused_even_while_empty() -> None:
    assert registered_reader_ids() == ()
    with pytest.raises(OperatingPacketReaderError, match="reader_not_allowlisted"):
        register_operating_packet_reader("neuralweb.some_other_reader.v1", consumer="neural_web")
    assert registered_reader_ids() == ()


def test_an_unregistered_reader_cannot_read(registered: str) -> None:
    packet = _packet()
    with pytest.raises(OperatingPacketReaderError, match="reader_not_registered"):
        read_operating_packet(
            packet, reader_id="neuralweb.some_other_reader.v1", evaluated_at=READ_AT
        )


def test_reader_validates_schema_and_hash_before_use(registered: str) -> None:
    packet = _packet()
    view = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert view.packet_id == packet["packet_id"]
    assert view.sector == "biopharma"

    tampered = copy.deepcopy(packet)
    tampered["entity_refs"] = ["trial:NCT00000002"]
    with pytest.raises(OperatingPacketReaderError, match="operating_packet_unavailable"):
        read_operating_packet(tampered, reader_id=registered, evaluated_at=READ_AT)

    off_schema = copy.deepcopy(packet)
    off_schema.pop("identity_state")
    off_schema["packet_hash"] = canonical_json_sha256(
        {key: value for key, value in off_schema.items() if key != "packet_hash"}
    )
    with pytest.raises(OperatingPacketReaderError, match="operating_packet_unavailable"):
        read_operating_packet(off_schema, reader_id=registered, evaluated_at=READ_AT)


def test_reader_cannot_write_back_to_the_packet(registered: str) -> None:
    """MUTATION PIN: the reader cannot mutate the packet or its own view."""

    packet = _packet()
    before = canonical_json_bytes(packet)
    view = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)

    assert canonical_json_bytes(packet) == before, "the reader must not touch its input"

    with pytest.raises((TypeError, AttributeError)):
        view.identity_state["availability"] = "available"  # type: ignore[index]
    with pytest.raises((TypeError, AttributeError)):
        view.coverage["observed"] = 999  # type: ignore[index]
    with pytest.raises((TypeError, AttributeError)):
        view.forecast_references["refs"] = ["forecast:1"]  # type: ignore[index]
    with pytest.raises((TypeError, AttributeError)):
        view.point_in_time_facts[0]["value"] = "rewritten"  # type: ignore[index]
    with pytest.raises((TypeError, AttributeError)):
        view.owner_projection_reads[0]["row_count"] = 999  # type: ignore[index]
    with pytest.raises(AttributeError):
        view.packet_id = "biocatalyst_operating_packet:" + "0" * 24  # type: ignore[misc]

    assert canonical_json_bytes(packet) == before
    unchanged = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert unchanged.packet_hash == view.packet_hash


def test_reader_exposes_no_write_seam(registered: str) -> None:
    for name in dir(packet_reader):
        if name.startswith("_"):
            continue
        assert not any(
            token in name.lower() for token in ("write", "persist", "commit", "publish", "emit")
        ), f"the reader must expose no write seam, found {name!r}"


def test_reader_cannot_raise_authority(registered: str) -> None:
    """MUTATION PIN: the reader can never grant more than the carrier caps."""

    packet = _packet()
    assert packet["authority_caps"]["max_authority"] == "A1_EXPLAIN"
    view = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert view.granted_max_authority == "A1_EXPLAIN"
    assert view.granted_actions == ("observe", "explain")
    assert view.llm_may_originate_signals is False

    with pytest.raises(OperatingPacketReaderError, match="authority_escalation_forbidden"):
        read_operating_packet(
            packet, reader_id=registered, evaluated_at=READ_AT, max_authority="A2_RECOMMEND"
        )

    packet_reader._reset_reader_registry()
    register_operating_packet_reader(
        NEURAL_WEB_READER_ID, consumer="neural_web", max_authority="A0_OBSERVE"
    )
    observe_only = read_operating_packet(
        packet, reader_id=NEURAL_WEB_READER_ID, evaluated_at=READ_AT, max_authority="A0_OBSERVE"
    )
    assert observe_only.granted_max_authority == "A0_OBSERVE"
    assert observe_only.granted_actions == ("observe",)
    with pytest.raises(OperatingPacketReaderError, match="authority_escalation_forbidden"):
        read_operating_packet(
            packet,
            reader_id=NEURAL_WEB_READER_ID,
            evaluated_at=READ_AT,
            max_authority="A1_EXPLAIN",
        )


def test_reader_refuses_a_carrier_that_would_originate_signals(registered: str) -> None:
    packet = _packet()
    escalated = copy.deepcopy(packet)
    escalated["authority_caps"]["llm_may_originate_signals"] = True
    escalated["packet_hash"] = canonical_json_sha256(
        {key: value for key, value in escalated.items() if key != "packet_hash"}
    )
    with pytest.raises(OperatingPacketReaderError):
        read_operating_packet(escalated, reader_id=registered, evaluated_at=READ_AT)


def test_contradictions_propagate_and_are_never_smoothed(registered: str) -> None:
    packet = _contradicting_packet()
    view = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert view.contradiction_state == "present"
    assert len(view.contradictions) == 1
    assert view.contradictions[0]["kind"] == "registry_value_disagreement"
    assert view.contradictions[0]["entity_ref"] == "trial:NCT00000001"
    assert view.correction_state == "present"
    assert len(view.corrections) == 1
    assert [dict(item) for item in view.contradictions] == packet["contradictions"]["items"]

    # A carrier that claims none_known while carrying items is refused rather
    # than silently flattened.
    smoothed = copy.deepcopy(packet)
    smoothed["contradictions"]["state"] = "none_known"
    smoothed["packet_hash"] = canonical_json_sha256(
        {key: value for key, value in smoothed.items() if key != "packet_hash"}
    )
    with pytest.raises(OperatingPacketReaderError, match="contradiction_reference_unavailable"):
        read_operating_packet(smoothed, reader_id=registered, evaluated_at=READ_AT)


def test_an_unavailable_lane_stays_unavailable(registered: str) -> None:
    reads = _reads()
    for read in reads:
        read.pop("contradictions", None)
        read.pop("corrections", None)
    view = read_operating_packet(
        _build(owner_projection_reads=reads), reader_id=registered, evaluated_at=READ_AT
    )
    assert view.contradiction_state == "unavailable"
    assert view.contradictions == ()
    assert view.correction_state == "unavailable"


def test_reader_checks_freshness_and_refuses_a_backdated_or_expired_carrier(
    registered: str,
) -> None:
    packet = _packet()
    view = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert view.is_fresh is True
    assert view.freshness_state == "fresh"
    assert view.packet_age_seconds == 240

    with pytest.raises(OperatingPacketReaderError, match="evaluated_at_unavailable"):
        read_operating_packet(packet, reader_id=registered, evaluated_at="2026-08-01T14:00:00Z")
    with pytest.raises(OperatingPacketReaderError, match="packet_freshness_unavailable"):
        read_operating_packet(packet, reader_id=registered, evaluated_at="2026-08-01T18:00:00Z")

    projections = [_projection()]
    stale = _build(
        projections=projections,
        sector_packet=_sector_packet(projections, health_state="stale"),
    )
    stale_view = read_operating_packet(stale, reader_id=registered, evaluated_at=READ_AT)
    assert stale_view.freshness_state == "stale"
    assert stale_view.is_fresh is False


def test_reader_bounds_its_payload_and_counts(registered: str) -> None:
    packet = _packet()
    oversized = b"x" * (2 * 1024 * 1024 + 1)
    with pytest.raises(OperatingPacketReaderError, match="packet_size_unavailable"):
        read_operating_packet(oversized, reader_id=registered, evaluated_at=READ_AT)
    with pytest.raises(OperatingPacketReaderError, match="operating_packet_unavailable"):
        read_operating_packet(b"[]", reader_id=registered, evaluated_at=READ_AT)
    with pytest.raises(OperatingPacketReaderError, match="operating_packet_unavailable"):
        read_operating_packet("not a packet", reader_id=registered, evaluated_at=READ_AT)  # type: ignore[arg-type]
    # Non-canonical bytes for an otherwise valid packet are refused.
    with pytest.raises(OperatingPacketReaderError, match="operating_packet_unavailable"):
        read_operating_packet(
            json.dumps(packet, indent=2).encode("utf-8"),
            reader_id=registered,
            evaluated_at=READ_AT,
        )


def test_reader_accepts_canonical_bytes_and_orders_deterministically(registered: str) -> None:
    packet = _packet()
    from_bytes = read_operating_packet(
        operating_packet_bytes(packet), reader_id=registered, evaluated_at=READ_AT
    )
    from_mapping = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert from_bytes == from_mapping
    assert list(from_bytes.entity_refs) == sorted(from_bytes.entity_refs)
    assert list(from_bytes.source_refs) == sorted(from_bytes.source_refs)
    fact_keys = [(fact["entity_ref"], fact["fact_key"]) for fact in from_bytes.point_in_time_facts]
    assert fact_keys == sorted(fact_keys)
    read_ids = [read["read_id"] for read in from_bytes.owner_projection_reads]
    assert read_ids == sorted(read_ids)


def test_reader_refuses_an_inferred_identity_carrier(registered: str) -> None:
    packet = _packet()
    forged = copy.deepcopy(packet)
    forged["identity_state"]["availability"] = "available"
    forged["packet_hash"] = canonical_json_sha256(
        {key: value for key, value in forged.items() if key != "packet_hash"}
    )
    with pytest.raises(OperatingPacketReaderError):
        read_operating_packet(forged, reader_id=registered, evaluated_at=READ_AT)

    view = read_operating_packet(packet, reader_id=registered, evaluated_at=READ_AT)
    assert view.identity_state["availability"] == "unavailable"
    assert view.identity_state["issuer_refs"] == ()
    assert view.identity_state["security_refs"] == ()
    assert view.forecast_references["refs"] == ()
