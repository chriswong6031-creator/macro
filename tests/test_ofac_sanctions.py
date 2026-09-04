from __future__ import annotations

import hashlib
import json

import pytest

import collectors.ofac_sanctions as ofac_collector
import engine.ofac_sanctions as ofac_engine
from collectors.ofac_sanctions import (
    SourceIntegrityError,
    fetch_bytes,
    make_receipt,
    validate_source_url,
)
from engine.ofac_sanctions import (
    ProjectionBoundsError,
    REQUIRED_STATES,
    SourceShapeError,
    build_projection,
    canonical_json_bytes,
    parse_current_sdn,
    parse_delta,
)


CURRENT_NS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"
DELTA_NS = "https://www.treasury.gov/ofac/DeltaFile/1.0"

EXPECTED_REQUIRED_STATES = {
    "CURRENT",
    "ADDED_SINCE_PREVIOUS",
    "REMOVED_SINCE_PREVIOUS",
    "SOURCE_CORRECTED",
    "GEOGRAPHY_UNRESOLVED",
    "IDENTITY_UNRESOLVED",
    "SOURCE_STALE",
    "SOURCE_UNAVAILABLE",
    "PARSER_SHAPE_CHANGED",
    "NO_RESULTS",
}


def test_acquisition_receipts_and_projection_name_the_same_parser_revision() -> None:
    assert ofac_collector.PARSER_REVISION == ofac_engine.PARSER_REVISION


def _current_xml(*entries: str, count: int | None = None) -> bytes:
    record_count = len(entries) if count is None else count
    return (
        f'<?xml version="1.0"?><sdnList xmlns="{CURRENT_NS}">'
        f"<publshInformation><Publish_Date>09/03/2026</Publish_Date>"
        f"<Record_Count>{record_count}</Record_Count></publshInformation>"
        f"{''.join(entries)}</sdnList>"
    ).encode()


def _entry(
    uid: str = "101",
    name: str = "ACME SHIPPING",
    country: str = "United States",
    *,
    nationality: str = "Canada",
    duplicate_address: bool = False,
) -> str:
    address = (
        "<address><uid>501</uid><address1>1 Main Street</address1>"
        f"<city>New York</city><country>{country}</country></address>"
    )
    return (
        "<sdnEntry>"
        f"<uid>{uid}</uid><lastName>{name}</lastName><sdnType>Entity</sdnType>"
        "<programList><program>TEST-PROGRAM</program></programList>"
        f"<nationalityList><nationality><country>{nationality}</country></nationality></nationalityList>"
        f"<addressList>{address}{address if duplicate_address else ''}</addressList>"
        "</sdnEntry>"
    )


def _delta_xml(*entities: str) -> bytes:
    return (
        f'<?xml version="1.0"?><sanctionsData xmlns="{DELTA_NS}">'
        "<publicationInfo><datePublished>2026-09-03T00:00:00-04:00</datePublished>"
        "<publicationType>Standard Action</publicationType></publicationInfo>"
        f"<entities>{''.join(entities)}</entities></sanctionsData>"
    ).encode()


def _delta_entity(uid: str, action: str, country: str = "United States") -> str:
    return (
        f'<entity id="{uid}" action="{action}">'
        '<generalInfo><entityType refId="601">Entity</entityType></generalInfo>'
        '<sanctionsPrograms><sanctionsProgram refId="42">TEST-PROGRAM</sanctionsProgram></sanctionsPrograms>'
        '<names><name id="1"><isPrimary>true</isPrimary><translations><translation id="2">'
        f"<formattedFullName>ENTITY {uid}</formattedFullName>"
        "</translation></translations></name></names>"
        f"<addresses><address id=\"3\"><country refId=\"840\">{country}</country>"
        '<translations><translation id="4"><addressParts>'
        '<addressPart id="5"><type refId="1454">CITY</type><value>New York</value></addressPart>'
        "</addressParts></translation></translations></address></addresses>"
        "</entity>"
    )


def _delta_correction(uid: str) -> str:
    return (
        f'<entity id="{uid}">'
        '<generalInfo><remarks action="update" oldValue="old wording">new wording</remarks></generalInfo>'
        '<addresses><address id="3" action="add"><country refId="840">United States</country>'
        '<translations><translation id="4"><addressParts>'
        '<addressPart id="5"><type refId="1454">CITY</type><value>New York</value></addressPart>'
        '</addressParts></translation></translations></address></addresses>'
        '</entity>'
    )


def _receipt(source_key: str, body: bytes, *, published_at: str = "2026-09-03T00:00:00Z") -> dict:
    return make_receipt(
        source_key=source_key,
        requested_url="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        final_url="https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Published/SDN.XML?X-Amz-Signature=secret",
        payload=body,
        acquired_at="2026-09-04T09:00:00Z",
        published_at=published_at,
        schema_revision=CURRENT_NS,
        rights_url="https://ofac.treasury.gov/sanctions-list-service",
    )


@pytest.fixture
def topology() -> dict:
    return {
        "type": "Topology",
        "objects": {
            "countries": {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "Polygon", "id": "840", "properties": {"name": "United States of America"}},
                    {"type": "Polygon", "id": "104", "properties": {"name": "Myanmar"}},
                    {"type": "Polygon", "id": "124", "properties": {"name": "Canada"}},
                    {"type": "Polygon", "id": "807", "properties": {"name": "Macedonia"}},
                    {"type": "Polygon", "properties": {"name": "N. Cyprus"}},
                ],
            }
        },
        "arcs": [],
    }


def test_source_url_allowlist_rejects_redirect_and_path_confusion() -> None:
    validate_source_url("https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML")
    validate_source_url(
        "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Published/rev/SDN.XML",
        redirect=True,
    )

    for hostile in (
        "http://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        "https://sanctionslistservice.ofac.treas.gov.evil.example/api/PublicationPreview/exports/SDN.XML",
        "https://user@sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        "https://sanctionslistservice.ofac.treas.gov/api/download/delta?filename=../../etc/passwd",
        "https://example.com/SDN.XML",
    ):
        with pytest.raises(ValueError):
            validate_source_url(hostile)


def test_source_url_allowlist_accepts_catalog_bound_current_xsd_redirect() -> None:
    validate_source_url(
        "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Export-XSDs/XML.xsd?X-Amz-Signature=short-lived",
        redirect=True,
    )


def test_receipt_verifies_catalog_bytes_and_hash_and_scrubs_signed_query() -> None:
    payload = b"official bytes"
    catalog = {
        "fileName": "SDN.XML",
        "size": len(payload),
        "lastUpdated": "2026-09-03T00:00:00",
        "hashCodes": json.dumps({"SHA-256": hashlib.sha256(payload).hexdigest()}),
    }
    receipt = make_receipt(
        source_key="ofac_sdn_current",
        requested_url="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
        final_url="https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/Published/x/SDN.XML?X-Amz-Security-Token=secret",
        payload=payload,
        acquired_at="2026-09-04T09:00:00Z",
        published_at="2026-09-03T00:00:00Z",
        schema_revision=CURRENT_NS,
        rights_url="https://ofac.treasury.gov/sanctions-list-service",
        catalog_entry=catalog,
    )
    assert receipt["raw_sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["actual_bytes"] == len(payload)
    assert receipt["raw_bytes"] == len(payload)
    assert receipt["source_file_name"] == "SDN.XML"
    assert receipt["source_published_at"] == "2026-09-03T00:00:00Z"
    assert receipt["rights_class"] == "official_public"
    assert receipt["list_identity"] == "OFAC_SDN"
    assert receipt["entry_identity"] == "ofac_numeric_uid_within_list"
    assert receipt["address_semantics"] == "published_address_fields_only"
    assert receipt["resolved_url"].endswith("/Published/x/SDN.XML")
    assert "X-Amz" not in json.dumps(receipt)

    with pytest.raises(SourceIntegrityError, match="catalog byte count"):
        make_receipt(
            source_key="ofac_sdn_current",
            requested_url=receipt["source_url"],
            final_url=receipt["source_url"],
            payload=payload,
            acquired_at=receipt["acquired_at"],
            published_at=receipt["published_at"],
            schema_revision=CURRENT_NS,
            rights_url=receipt["rights_url"],
            catalog_entry={**catalog, "size": len(payload) + 1},
        )


def test_official_fetch_is_bounded_before_the_response_is_materialized(monkeypatch) -> None:
    class FakeResponse:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return ofac_collector.CURRENT_XML_URL

        def read(self, limit):
            assert limit == 11
            return b"x" * 11

    class FakeOpener:
        def open(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(ofac_collector.urllib.request, "build_opener", lambda *_args: FakeOpener())

    with pytest.raises(SourceIntegrityError, match="response exceeds"):
        fetch_bytes(ofac_collector.CURRENT_XML_URL, max_bytes=10)


def test_official_fetch_errors_do_not_echo_redirect_credentials(monkeypatch) -> None:
    class FakeOpener:
        def open(self, *_args, **_kwargs):
            raise OSError(
                "timeout at https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/"
                "Published/SDN.XML?X-Amz-Security-Token=secret"
            )

    monkeypatch.setattr(ofac_collector.urllib.request, "build_opener", lambda *_args: FakeOpener())

    with pytest.raises(ofac_collector.SourceUnavailableError) as caught:
        fetch_bytes(ofac_collector.CURRENT_XML_URL)
    assert ofac_collector.CURRENT_XML_URL in str(caught.value)
    assert "secret" not in str(caught.value)
    assert "X-Amz" not in str(caught.value)


def test_current_parser_uses_published_addresses_only_and_deduplicates() -> None:
    parsed = parse_current_sdn(_current_xml(_entry(duplicate_address=True)))
    assert parsed["published_at"] == "2026-09-03"
    assert len(parsed["entries"]) == 1
    entry = parsed["entries"][0]
    assert entry["uid"] == "101"
    assert entry["list_identity"] == "OFAC_SDN"
    assert entry["programs"] == ["TEST-PROGRAM"]
    assert len(entry["addresses"]) == 1
    assert entry["addresses"][0]["published_country"] == "United States"
    assert "Canada" not in json.dumps(entry["addresses"])


def test_parsers_reject_dtd_namespace_drift_and_record_count_mismatch() -> None:
    with pytest.raises(SourceShapeError, match="DTD"):
        parse_current_sdn(b'<!DOCTYPE x [<!ENTITY boom "boom">]><x>&boom;</x>')
    with pytest.raises(SourceShapeError, match="DTD"):
        parse_current_sdn(b" " * 100_001 + b'<!DOCTYPE x [<!ENTITY boom "boom">]><x>&boom;</x>')
    with pytest.raises(SourceShapeError, match="namespace"):
        parse_current_sdn(b"<sdnList><publshInformation /></sdnList>")
    with pytest.raises(SourceShapeError, match="record count"):
        parse_current_sdn(_current_xml(_entry(), count=2))


def test_hostile_xml_guard_rejects_utf16_dtd_and_bounds_delta_depth() -> None:
    entity_payload = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE sdnList [<!ENTITY boom "expanded">]>'
        f'<sdnList xmlns="{CURRENT_NS}"><publshInformation>'
        '<Publish_Date>09/03/2026</Publish_Date><Record_Count>0</Record_Count>'
        '</publshInformation></sdnList>'
    ).encode("utf-16")
    with pytest.raises(SourceShapeError, match="DTD/entity|UTF-8"):
        parse_current_sdn(entity_payload)

    depth = 300
    nested = "".join("<n>" for _ in range(depth)) + "".join("</n>" for _ in range(depth))
    with pytest.raises(SourceShapeError, match="depth"):
        parse_delta(_delta_xml(f'<entity id="1">{nested}</entity>'))


def test_projection_uses_the_exact_issue_state_vocabulary() -> None:
    assert set(REQUIRED_STATES) == EXPECTED_REQUIRED_STATES
    assert not ({"ADDED", "REMOVED", "GEO_UNRESOLVED", "STALE", "UNAVAILABLE"} & set(REQUIRED_STATES))


def test_delta_parser_preserves_explicit_action_and_published_address() -> None:
    parsed = parse_delta(
        _delta_xml(
            _delta_entity("101", "remove", "United States"),
            _delta_entity("202", "add", "Burma"),
        )
    )
    assert parsed["published_at"] == "2026-09-03T00:00:00-04:00"
    assert [(row["uid"], row["action"]) for row in parsed["changes"]] == [
        ("101", "remove"),
        ("202", "add"),
    ]
    assert {row["list_identity"] for row in parsed["changes"]} == {"OFAC_SDN"}
    assert parsed["changes"][1]["addresses"][0]["published_country"] == "Burma"


def test_delta_parser_classifies_entity_without_add_remove_as_source_correction() -> None:
    parsed = parse_delta(_delta_xml(_delta_correction("101")))
    assert parsed["changes"][0]["action"] == "correct"
    assert {
        "path": "generalInfo/remarks",
        "action": "update",
        "old_value": "old wording",
        "value": "new wording",
    } in parsed["changes"][0]["field_operations"]


def test_projection_maps_source_aliases_keeps_regions_unresolved_and_marks_deltas(topology: dict) -> None:
    current = _current_xml(
        _entry("101", "ACME SHIPPING", "United States"),
        _entry("202", "MYANMAR CO", "Burma"),
        _entry("303", "GAZA CO", "Region: Gaza"),
        _entry("404", "MACEDONIA CO", "North Macedonia, The Republic of"),
    )
    delta = _delta_xml(
        _delta_entity("101", "remove", "United States"),
        _delta_entity("202", "add", "Burma"),
    )
    projection = build_projection(
        current_xml=current,
        current_receipt=_receipt("ofac_sdn_current", current),
        delta_documents=[(delta, _receipt("ofac_sdn_delta_2026-09-03", delta))],
        topology=topology,
        previous=None,
        as_of="2026-09-04T09:30:00Z",
    )

    by_uid = {row["uid"]: row for row in projection["entries"]}
    assert by_uid["101"]["states"] == ["CURRENT"]  # current membership wins over an older remove action
    assert by_uid["202"]["states"] == ["CURRENT", "ADDED_SINCE_PREVIOUS"]
    assert by_uid["202"]["addresses"][0]["geo_id"] == "104"
    assert by_uid["303"]["addresses"][0]["state"] == "GEOGRAPHY_UNRESOLVED"
    assert by_uid["404"]["addresses"][0]["geo_id"] == "807"
    assert projection["summary"]["geo_unresolved_addresses"] == 1
    assert {row["state"] for row in projection["changes"]} == {
        "ADDED_SINCE_PREVIOUS",
        "REMOVED_SINCE_PREVIOUS",
    }
    assert all("current_location" not in json.dumps(row) for row in projection["entries"])


def test_projection_marks_same_uid_source_correction_and_is_byte_stable(topology: dict) -> None:
    before_xml = _current_xml(_entry("101", "ACME SHIPPING", "United States"))
    before = build_projection(
        current_xml=before_xml,
        current_receipt=_receipt("ofac_sdn_current", before_xml),
        delta_documents=[],
        topology=topology,
        previous=None,
        as_of="2026-09-04T09:30:00Z",
    )
    no_op = build_projection(
        current_xml=before_xml,
        current_receipt={**_receipt("ofac_sdn_current", before_xml), "acquired_at": "2026-09-04T10:00:00Z"},
        delta_documents=[],
        topology=topology,
        previous=before,
        as_of="2026-09-04T10:00:00Z",
    )
    assert canonical_json_bytes(no_op) == canonical_json_bytes(before)

    corrected_xml = _current_xml(_entry("101", "ACME SHIPPING CORRECTED", "United States"))
    corrected = build_projection(
        current_xml=corrected_xml,
        current_receipt=_receipt("ofac_sdn_current", corrected_xml),
        delta_documents=[],
        topology=topology,
        previous=before,
        as_of="2026-09-04T11:00:00Z",
    )
    assert corrected["entries"][0]["states"] == ["CURRENT", "SOURCE_CORRECTED"]
    assert corrected["entries"][0]["observed_in_source_identity"] == corrected["source_identity"]
    assert corrected["entries"][0]["superseded_observations"] == [
        {
            "addresses": before["entries"][0]["addresses"],
            "entity_type": "Entity",
            "identity_resolved": True,
            "list_identity": "OFAC_SDN",
            "name": "ACME SHIPPING",
            "observed_in_source_identity": before["source_identity"],
            "programs": ["TEST-PROGRAM"],
            "source_fingerprint": before["entries"][0]["source_fingerprint"],
            "states": ["CURRENT"],
            "uid": "101",
        }
    ]

    expanded_xml = _current_xml(
        _entry("101", "ACME SHIPPING CORRECTED", "United States"),
        _entry("202", "SECOND ENTRY", "United States"),
    )
    expanded = build_projection(
        current_xml=expanded_xml,
        current_receipt=_receipt("ofac_sdn_current", expanded_xml),
        delta_documents=[],
        topology=topology,
        previous=corrected,
        as_of="2026-09-04T12:00:00Z",
    )
    assert expanded["entries"][0]["superseded_observations"] == corrected["entries"][0][
        "superseded_observations"
    ]


def test_projection_exposes_a_deterministic_freshness_deadline_without_false_stale_state(topology: dict) -> None:
    current = _current_xml(_entry())
    projection = build_projection(
        current_xml=current,
        current_receipt=_receipt("ofac_sdn_current", current),
        delta_documents=[],
        topology=topology,
        previous=None,
        as_of="2026-09-04T09:30:00Z",
    )

    assert projection["source_state"] == "CURRENT"
    assert projection["freshness"] == {
        "published_at": "2026-09-03",
        "stale_after": "2026-09-11T00:00:00Z",
    }


def test_successful_reacquisition_clears_a_degraded_last_good_state(topology: dict) -> None:
    current = _current_xml(_entry())
    receipt = _receipt("ofac_sdn_current", current)
    accepted = build_projection(
        current_xml=current,
        current_receipt=receipt,
        delta_documents=[],
        topology=topology,
        previous=None,
        as_of="2026-09-04T09:30:00Z",
    )
    degraded = {
        **accepted,
        "source_state": "SOURCE_UNAVAILABLE",
        "degraded": {
            "state": "SOURCE_UNAVAILABLE",
            "error_code": "official_source_timeout",
            "last_good_projection_id": accepted["projection_id"],
            "facts_retained_from_last_good": True,
        },
    }

    recovered = build_projection(
        current_xml=current,
        current_receipt={**receipt, "acquired_at": "2026-09-04T10:00:00Z"},
        delta_documents=[],
        topology=topology,
        previous=degraded,
        as_of="2026-09-04T10:00:00Z",
    )

    assert recovered["source_state"] == "CURRENT"
    assert "degraded" not in recovered


def test_projection_fails_closed_before_discarding_correction_history(topology: dict) -> None:
    current = _current_xml(_entry("101", "FIRST", "United States"))
    accepted = build_projection(
        current_xml=current,
        current_receipt=_receipt("ofac_sdn_current", current),
        delta_documents=[],
        topology=topology,
        previous=None,
        as_of="2026-09-04T09:30:00Z",
    )
    accepted["entries"][0]["superseded_observations"] = [
        {
            "uid": "101",
            "list_identity": "OFAC_SDN",
            "identity_resolved": True,
            "name": "ORIGINAL",
            "entity_type": "Entity",
            "programs": ["TEST-PROGRAM"],
            "addresses": [],
            "states": ["CURRENT"],
            "source_fingerprint": "sha256:original",
            "observed_in_source_identity": "sha256:original-source",
        }
    ]
    changed = _current_xml(_entry("101", "SECOND", "United States"))

    with pytest.raises(ProjectionBoundsError, match="superseded observation bound"):
        build_projection(
            current_xml=changed,
            current_receipt=_receipt("ofac_sdn_current", changed),
            delta_documents=[],
            topology=topology,
            previous=accepted,
            as_of="2026-09-04T10:30:00Z",
            max_superseded_observations=1,
        )


def test_projection_fails_closed_instead_of_silently_truncating(topology: dict) -> None:
    current = _current_xml(_entry("101"), _entry("202"))
    with pytest.raises(ProjectionBoundsError, match="entry bound"):
        build_projection(
            current_xml=current,
            current_receipt=_receipt("ofac_sdn_current", current),
            delta_documents=[],
            topology=topology,
            previous=None,
            as_of="2026-09-04T09:30:00Z",
            max_entries=1,
        )
