"""Strict Company Facts/Submissions bridge tests."""
from __future__ import annotations

from copy import copy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

import pytest

from engine.fundamental_forensics import companyfacts_ledger as companyfacts_ledger_module
from collectors.fundamental_forensics_companyfacts import (
    iter_companyfacts_occurrences,
    manifest_id_for,
)
from engine.fundamental_forensics.models import canonical_json as source_canonical_json
from engine.fundamental_forensics.companyfacts_ledger import (
    CompanyFactsLedgerConversion,
    CompanyFactsLedgerError,
    CompanyFactsLedgerInputTooLarge,
    RevisionEvidence,
    SubmissionSourceWitness,
    convert_companyfacts_to_raw_ledger,
)
from engine.fundamental_forensics.raw_ledger import (
    AvailabilityStatus,
    FactEventType,
    ReplayClock,
    canonical_json as raw_canonical_json,
)


CIK = "0000000001"
CAPTURE_ID = "ffseccfc_" + "a" * 64


def _entry(
    accession: str,
    value: int | str,
    *,
    form: str = "10-K",
    start: str | None = "2024-01-01",
    end: str = "2024-12-31",
    fy: int = 2024,
    fp: str = "FY",
    filed: str = "2025-02-15",
    frame: str | None = "CY2024",
) -> dict:
    record = {
        "val": value,
        "accn": accession,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
        "end": end,
    }
    if start is not None:
        record["start"] = start
    if frame is not None:
        record["frame"] = frame
    return record


def _companyfacts(entries: list[dict]) -> dict:
    return {
        "cik": 1,
        "entityName": "Fixture Corporation",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": entries}
                }
            }
        },
    }


def _columns(rows: list[tuple[str, str | None]]) -> dict:
    return {
        "accessionNumber": [item[0] for item in rows],
        "acceptanceDateTime": [item[1] for item in rows],
    }


def _submissions(
    rows: list[tuple[str, str | None]], *, files: list[dict] | None = None, cik: str = CIK
) -> dict:
    return {
        "cik": cik,
        "filings": {
            "recent": _columns(rows),
            "files": [] if files is None else files,
        },
    }


def _manifest(
    payload: dict,
    *,
    recorded_at: str = "2025-04-01T12:00:01.000000Z",
    captured_at: str = "2025-04-01T12:00:01.000000Z",
) -> dict:
    logical = source_canonical_json(payload).encode("utf-8")
    occurrence_digest = sha256()
    occurrence_count = 0
    for occurrence in iter_companyfacts_occurrences(payload):
        occurrence_digest.update(source_canonical_json(occurrence).encode("utf-8"))
        occurrence_count += 1
    response_sha = sha256(b"fixture SEC response bytes").hexdigest()
    record = {
        "schema": "fundamental_forensics.sec_companyfacts_manifest/v2",
        "manifest_id": "",
        "issuer": {
            "ticker": "FIXT",
            "cik": CIK,
            "entity_name": payload["entityName"],
        },
        "clocks": {
            "source_snapshot_at": "2025-04-01T12:00:00.000000Z",
            "recorded_at": recorded_at,
            "acquisition_started_at": "2025-04-01T12:00:00.000000Z",
            "captured_at": captured_at,
        },
        "temporal_scope": {
            "kind": "current_sec_companyfacts_snapshot",
            "point_in_time_eligible": False,
            "acceptance_joined": False,
            "fact_filed_dates_preserved": True,
        },
        "source": {
            "capture_id": CAPTURE_ID,
            "capture_receipt_key": f"{CIK}/companyfacts_v3/captures/{CAPTURE_ID}.json",
            "response_sha256": response_sha,
            "response_bytes": 26,
            "response_object_path": f"{CIK}/companyfacts_v3/objects/{response_sha[:2]}/{response_sha}.json.gz",
            "logical_sha256": sha256(logical).hexdigest(),
            "logical_bytes": len(logical),
            "fact_occurrence_count": occurrence_count,
            "fact_occurrence_sha256": occurrence_digest.hexdigest(),
        },
    }
    record["manifest_id"] = manifest_id_for(record)
    return record


def _convert(
    payload: dict,
    submissions: dict,
    *,
    older: dict[str, dict] | None = None,
    evidence=None,
    **limits,
):
    return convert_companyfacts_to_raw_ledger(
        companyfacts=payload,
        capture_manifest=_manifest(payload),
        submissions=submissions,
        submissions_recorded_at=limits.pop(
            "submissions_recorded_at", "2025-04-01T12:00:02.000000Z"
        ),
        older_submissions_files=older,
        revision_evidence=evidence,
        **limits,
    )


def test_end_to_end_joins_declared_older_submission_file_and_retains_duplicates() -> None:
    older_accession = "0000000001-23-000001"
    recent_accession = "0000000001-25-000001"
    duplicate = _entry(older_accession, 1000, filed="2023-02-15", fy=2022, frame="CY2022")
    payload = _companyfacts(
        [duplicate, dict(duplicate), _entry(recent_accession, 1200)]
    )
    older_name = "CIK0000000001-submissions-001.json"
    conversion = _convert(
        payload,
        _submissions(
            [(recent_accession, "2025-02-15T16:00:00.000Z")],
            files=[{"name": older_name}],
        ),
        older={
            older_name: {
                "cik": CIK,
                **_columns([(older_accession, "2023-02-15T16:00:00.000Z")]),
            }
        },
    )

    assert len(conversion.ledger.events) == 3
    assert conversion.receipt.older_submissions_file_count == 1
    assert conversion.receipt.unmapped_accession_count == 0
    assert conversion.receipt.availability == "available"
    assert [item.occurrence.parsed_value for item in conversion.occurrences] == ["1000", "1000", "1200"]
    duplicate_ids = [
        item.occurrence.occurrence_id
        for item in conversion.occurrences
        if item.accession == older_accession
    ]
    assert len(duplicate_ids) == 2
    assert len(set(duplicate_ids)) == 2
    old = conversion.occurrences[0]
    assert old.occurrence.accepted_at == datetime(2023, 2, 15, 16, tzinfo=timezone.utc)
    assert old.taxonomy == "us-gaap"
    assert old.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert old.start == "2024-01-01"
    assert old.end == "2024-12-31"
    assert old.fy == 2022
    assert old.fp == "FY"
    assert old.frame == "CY2022"
    assert old.form == "10-K"
    assert old.filed == "2023-02-15"
    assert old.accession == older_accession
    assert old.occurrence.context.explicit_dimensions == ()
    assert old.occurrence.context.typed_dimensions == ()
    assert old.occurrence.dimensions_known is False
    assert conversion.receipt.mapped_accessions == (
        older_accession,
        recent_accession,
    )
    assert conversion.receipt.unmapped_accessions == ()
    assert conversion.submission_sources == conversion.receipt.submission_sources
    assert [
        (item.source_name, item.row_count, item.is_older)
        for item in conversion.submission_sources
    ] == [
        ("recent", 1, False),
        (older_name, 1, True),
    ]


def test_missing_acceptance_is_preserved_but_fails_closed_for_source_replay() -> None:
    accession = "0000000001-25-000123"
    payload = _companyfacts([_entry(accession, "123.4500")])
    conversion = _convert(payload, _submissions([]))
    item = conversion.occurrences[0]

    assert item.pit_eligible is False
    assert item.availability is AvailabilityStatus.NOT_AVAILABLE
    assert item.occurrence.parsed_value == "123.45"
    assert item.occurrence.raw_token == "123.45"
    source = conversion.ledger.select(
        item.occurrence.logical_key,
        as_of="2025-05-01T00:00:00Z",
        clock=ReplayClock.SOURCE_EVENT,
    )
    system = conversion.ledger.select(
        item.occurrence.logical_key,
        as_of="2025-05-01T00:00:00Z",
        clock=ReplayClock.SYSTEM,
    )
    assert source.status is AvailabilityStatus.NOT_AVAILABLE
    assert source.candidate_occurrence_ids == ()
    assert source.reason == "no raw occurrence was available at the requested cutoff"
    assert system.status is AvailabilityStatus.AVAILABLE
    assert conversion.receipt.unmapped_accession_count == 1
    assert conversion.receipt.availability == "partial"


def test_future_submission_acceptance_relative_to_capture_clock_is_rejected() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1)])
    with pytest.raises(CompanyFactsLedgerError, match="cannot be after manifest captured_at"):
        _convert(
            payload,
            _submissions([(accession, "2025-04-02T00:00:00.000Z")]),
            submissions_recorded_at="2025-04-03T00:00:00Z",
        )


def test_actual_system_availability_is_gated_by_capture_not_only_recording() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1)])
    conversion = convert_companyfacts_to_raw_ledger(
        companyfacts=payload,
        capture_manifest=_manifest(
            payload,
            recorded_at="2025-04-01T12:00:04.000000Z",
            captured_at="2025-04-01T12:00:04.000000Z",
        ),
        submissions=_submissions(
            [(accession, "2025-02-15T16:00:00Z")]
        ),
        submissions_recorded_at="2025-04-01T12:00:02Z",
    )

    event = conversion.ledger.events[0]
    assert event.recorded_at == datetime(
        2025, 4, 1, 12, 0, 4, tzinfo=timezone.utc
    )
    assert conversion.ledger.select(
        event.logical_key,
        as_of="2025-04-01T12:00:03Z",
        clock="system",
    ).status is AvailabilityStatus.NOT_AVAILABLE
    assert conversion.ledger.select(
        event.logical_key,
        as_of="2025-04-01T12:00:04Z",
        clock="system",
    ).occurrence is event


def test_explicit_evidence_builds_an_amendment_then_recast_chain() -> None:
    original = "0000000001-24-000001"
    amendment = "0000000001-25-000001"
    recast = "0000000001-25-000002"
    payload = _companyfacts(
        [
            _entry(original, 100),
            _entry(amendment, 110, form="10-K/A"),
            _entry(recast, 120, form="10-K"),
        ]
    )
    conversion = _convert(
        payload,
        _submissions(
            [
                (original, "2024-02-15T16:00:00.000Z"),
                (amendment, "2025-02-15T16:00:00.000Z"),
                (recast, "2025-03-15T16:00:00.000Z"),
            ]
        ),
        evidence=[
            RevisionEvidence(
                amendment,
                original,
                FactEventType.AMENDMENT,
                "spine:amends-accession",
                "2025-04-01T12:00:03Z",
            ),
            RevisionEvidence(
                recast,
                amendment,
                FactEventType.COMPARATIVE_RECAST,
                "issuer:comparative-recast",
                "2025-04-01T12:00:04Z",
            ),
        ],
    )
    by_accession = {item.accession: item.occurrence for item in conversion.occurrences}

    assert by_accession[amendment].event_type is FactEventType.AMENDMENT
    assert by_accession[amendment].revision_of == by_accession[original].occurrence_id
    assert by_accession[recast].event_type is FactEventType.COMPARATIVE_RECAST
    assert by_accession[recast].revision_of == by_accession[amendment].occurrence_id
    assert conversion.ledger.revision_chain(by_accession[recast].occurrence_id) == (
        by_accession[original],
        by_accession[amendment],
        by_accession[recast],
    )
    assert conversion.receipt.typed_revision_count == 2


def test_amendment_form_alone_does_not_fabricate_a_fact_level_parent() -> None:
    original = "0000000001-24-000001"
    amendment = "0000000001-25-000001"
    payload = _companyfacts([_entry(original, 100), _entry(amendment, 110, form="10-K/A")])
    conversion = _convert(
        payload,
        _submissions(
            [
                (original, "2024-02-15T16:00:00.000Z"),
                (amendment, "2025-02-15T16:00:00.000Z"),
            ]
        ),
    )
    amended = next(item for item in conversion.occurrences if item.accession == amendment)

    assert amended.amendment_declared is True
    assert amended.occurrence.event_type is FactEventType.FILED
    assert amended.occurrence.revision_of is None


def _reordered(value):
    if isinstance(value, dict):
        return {key: _reordered(value[key]) for key in reversed(tuple(value))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


def test_canonical_input_and_output_are_deterministic_across_mapping_byte_order() -> None:
    old = "0000000001-24-000001"
    new = "0000000001-25-000001"
    payload = _companyfacts([_entry(old, 100), _entry(new, 110)])
    submissions = _submissions(
        [
            (old, "2024-02-15T16:00:00.000Z"),
            (new, "2025-02-15T16:00:00.000Z"),
        ]
    )
    first = _convert(payload, submissions)
    second = _convert(_reordered(payload), _reordered(submissions))

    assert first.receipt.input_sha256 == second.receipt.input_sha256
    assert first.receipt.output_sha256 == second.receipt.output_sha256
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert [item.occurrence.occurrence_id for item in first.occurrences] == [
        item.occurrence.occurrence_id for item in second.occurrences
    ]
    assert first.ledger.events[0].source.document_id == second.ledger.events[0].source.document_id
    assert first.ledger.events[0].context.context_id == second.ledger.events[0].context.context_id
    assert first.ledger.events[0].unit.unit_id == second.ledger.events[0].unit.unit_id


def test_binary_float_value_is_rejected_before_a_raw_fact_is_created() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1.25)])
    with pytest.raises(CompanyFactsLedgerError, match="never float"):
        convert_companyfacts_to_raw_ledger(
            companyfacts=payload,
            capture_manifest=_manifest(payload),
            submissions=_submissions([(accession, "2025-02-15T16:00:00.000Z")]),
            submissions_recorded_at="2025-04-01T12:00:02Z",
        )


def test_companyfacts_decimal_expansion_is_bounded_before_source_serialization() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1)])
    manifest = _manifest(payload)
    payload["facts"]["us-gaap"][
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]["units"]["USD"][0]["val"] = Decimal("1e1000000000")

    with pytest.raises(CompanyFactsLedgerError, match="unsafe bounded expansion"):
        convert_companyfacts_to_raw_ledger(
            companyfacts=payload,
            capture_manifest=manifest,
            submissions=_submissions(
                [(accession, "2025-02-15T16:00:00Z")]
            ),
            submissions_recorded_at="2025-04-01T12:00:02Z",
        )


@pytest.mark.parametrize("mutation", ["clock", "digest", "payload"])
def test_capture_manifest_clock_and_digest_bindings_reject_mutations(mutation: str) -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 100)])
    manifest = _manifest(payload)
    if mutation == "clock":
        manifest["clocks"]["recorded_at"] = "2025-04-01T12:00:02.000000Z"
    elif mutation == "digest":
        manifest["source"]["logical_sha256"] = "0" * 64
    else:
        payload["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"][0]["val"] = 101

    with pytest.raises(CompanyFactsLedgerError):
        convert_companyfacts_to_raw_ledger(
            companyfacts=payload,
            capture_manifest=manifest,
            submissions=_submissions([(accession, "2025-02-15T16:00:00.000Z")]),
            submissions_recorded_at="2025-04-01T12:00:02Z",
        )


def test_bounded_occurrence_payload_and_submission_inputs_fail_closed() -> None:
    first = "0000000001-25-000001"
    second = "0000000001-25-000002"
    payload = _companyfacts([_entry(first, 1), _entry(second, 2)])
    submissions = _submissions(
        [
            (first, "2025-02-15T16:00:00.000Z"),
            (second, "2025-02-16T16:00:00.000Z"),
        ]
    )
    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="occurrence"):
        _convert(payload, submissions, max_occurrences=1)
    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="payload"):
        _convert(payload, submissions, max_payload_bytes=1)
    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="Submissions row"):
        _convert(payload, submissions, max_submission_rows=1)


def test_rejects_cik_accession_and_submission_shape_mismatches() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1)])
    wrong_cik = _submissions([(accession, "2025-02-15T16:00:00.000Z")], cik="2")
    with pytest.raises(CompanyFactsLedgerError, match="CIK"):
        _convert(payload, wrong_cik)

    malformed = _submissions([(accession, "2025-02-15T16:00:00.000Z")])
    malformed["filings"]["recent"]["acceptanceDateTime"] = []
    with pytest.raises(CompanyFactsLedgerError, match="inconsistent lengths"):
        _convert(payload, malformed)

    bad_accession = _companyfacts([_entry("bad-accession", 1)])
    with pytest.raises(CompanyFactsLedgerError, match="accn"):
        _convert(
            bad_accession,
            _submissions([(accession, "2025-02-15T16:00:00.000Z")]),
        )


def test_submissions_recorded_clock_is_mandatory_binds_receipt_and_sets_system_time() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1)])
    submissions = _submissions([(accession, "2025-02-15T16:00:00Z")])

    with pytest.raises(TypeError, match="submissions_recorded_at"):
        convert_companyfacts_to_raw_ledger(
            companyfacts=payload,
            capture_manifest=_manifest(payload),
            submissions=submissions,
        )
    with pytest.raises(CompanyFactsLedgerError, match="timezone"):
        _convert(payload, submissions, submissions_recorded_at="2025-04-01T12:00:02")
    with pytest.raises(CompanyFactsLedgerError, match="after submissions_recorded_at"):
        _convert(
            payload,
            submissions,
            submissions_recorded_at="2025-02-14T00:00:00Z",
        )

    first = _convert(
        payload,
        submissions,
        submissions_recorded_at="2025-04-01T12:00:05Z",
    )
    second = _convert(
        payload,
        submissions,
        submissions_recorded_at="2025-04-01T12:00:06Z",
    )
    assert first.ledger.events[0].recorded_at == datetime(
        2025, 4, 1, 12, 0, 5, tzinfo=timezone.utc
    )
    assert dict(first.receipt.clocks)["submissions_recorded_at"] == (
        "2025-04-01T12:00:05.000000Z"
    )
    assert first.receipt.submissions_clock_scope == (
        "recent_and_all_supplied_older_files"
    )
    assert first.receipt.input_sha256 != second.receipt.input_sha256
    assert first.ledger.events[0].occurrence_id != second.ledger.events[0].occurrence_id


def test_revision_evidence_clock_is_mandatory_time_safe_and_drives_child_identity() -> None:
    original = "0000000001-24-000001"
    amendment = "0000000001-25-000001"
    payload = _companyfacts([_entry(original, 100), _entry(amendment, 110)])
    submissions = _submissions(
        [
            (original, "2024-02-15T16:00:00Z"),
            (amendment, "2025-02-15T16:00:00Z"),
        ]
    )
    with pytest.raises(TypeError, match="available_at"):
        RevisionEvidence(
            amendment,
            original,
            FactEventType.AMENDMENT,
            "spine:missing-clock",
        )
    with pytest.raises(CompanyFactsLedgerError, match="available_at cannot precede"):
        _convert(
            payload,
            submissions,
            evidence=[
                RevisionEvidence(
                    amendment,
                    original,
                    FactEventType.AMENDMENT,
                    "spine:early",
                    "2025-02-14T00:00:00Z",
                )
            ],
        )
    with pytest.raises(CompanyFactsLedgerError, match="available_at is required"):
        _convert(
            payload,
            submissions,
            evidence=[
                {
                    "child_accession": amendment,
                    "parent_accession": original,
                    "event_type": "amendment",
                    "evidence_id": "spine:no-clock",
                }
            ],
        )

    def converted(
        clock: str,
        event_type: FactEventType = FactEventType.AMENDMENT,
        evidence_id: str = "spine:explicit-parent",
    ):
        return _convert(
            payload,
            submissions,
            evidence=[
                RevisionEvidence(
                    amendment,
                    original,
                    event_type,
                    evidence_id,
                    clock,
                )
            ],
        )

    first = converted("2025-04-01T12:00:07Z")
    later = converted("2025-04-01T12:00:08Z")
    retyped = converted("2025-04-01T12:00:07Z", FactEventType.RESTATEMENT)
    reidentified = converted(
        "2025-04-01T12:00:07Z",
        evidence_id="spine:different-evidence",
    )
    first_by_accession = {item.accession: item for item in first.occurrences}
    later_by_accession = {item.accession: item for item in later.occurrences}
    retyped_by_accession = {item.accession: item for item in retyped.occurrences}
    reidentified_by_accession = {
        item.accession: item for item in reidentified.occurrences
    }

    assert first_by_accession[original].occurrence.recorded_at == datetime(
        2025, 4, 1, 12, 0, 2, tzinfo=timezone.utc
    )
    assert first_by_accession[amendment].occurrence.recorded_at == datetime(
        2025, 4, 1, 12, 0, 7, tzinfo=timezone.utc
    )
    assert first_by_accession[amendment].revision_evidence_available_at == datetime(
        2025, 4, 1, 12, 0, 7, tzinfo=timezone.utc
    )
    assert first_by_accession[amendment].occurrence.occurrence_id != (
        later_by_accession[amendment].occurrence.occurrence_id
    )
    assert first_by_accession[amendment].occurrence.occurrence_id != (
        retyped_by_accession[amendment].occurrence.occurrence_id
    )
    assert first_by_accession[amendment].occurrence.occurrence_id != (
        reidentified_by_accession[amendment].occurrence.occurrence_id
    )
    assert first.receipt.output_sha256 != later.receipt.output_sha256


def test_adapter_occurrence_identity_binds_submissions_acceptance_clock() -> None:
    accession = "0000000001-25-000001"
    payload = _companyfacts([_entry(accession, 1)])
    first = _convert(
        payload,
        _submissions([(accession, "2025-02-15T16:00:00Z")]),
    )
    later = _convert(
        payload,
        _submissions([(accession, "2025-02-16T16:00:00Z")]),
    )

    assert first.ledger.events[0].accepted_at != later.ledger.events[0].accepted_at
    assert first.ledger.events[0].occurrence_id != later.ledger.events[0].occurrence_id


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("output_sha256", "0" * 64),
        ("occurrence_count", 0),
        ("output_occurrence_count", 0),
        ("mapped_accessions", ()),
        ("mapped_accession_count", 0),
        ("unmapped_accessions", ("0000000001-25-000001",)),
        ("unmapped_accession_count", 1),
        ("pit_eligible_count", 0),
        ("typed_revision_count", 1),
        ("availability", "partial"),
    ],
)
def test_conversion_revalidates_receipt_output_counts_partitions_and_availability(
    field: str, bad_value
) -> None:
    accession = "0000000001-25-000001"
    conversion = _convert(
        _companyfacts([_entry(accession, 1)]),
        _submissions([(accession, "2025-02-15T16:00:00Z")]),
    )
    tampered = copy(conversion.receipt)
    object.__setattr__(tampered, field, bad_value)

    with pytest.raises(CompanyFactsLedgerError):
        CompanyFactsLedgerConversion(
            ledger=conversion.ledger,
            occurrences=conversion.occurrences,
            submission_sources=conversion.submission_sources,
            receipt=tampered,
        )


@pytest.mark.parametrize(
    "field",
    ["submission_row_count", "older_submissions_file_count"],
)
def test_conversion_recomputes_source_counts_even_for_readdressed_receipt(
    field: str,
) -> None:
    accession = "0000000001-25-000001"
    conversion = _convert(
        _companyfacts([_entry(accession, 1)]),
        _submissions([(accession, "2025-02-15T16:00:00Z")]),
    )
    tampered = copy(conversion.receipt)
    object.__setattr__(tampered, field, 999)
    object.__setattr__(
        tampered,
        "receipt_id",
        "cffledger_"
        + sha256(
            raw_canonical_json(tampered.to_dict(include_id=False)).encode("utf-8")
        ).hexdigest(),
    )

    with pytest.raises(CompanyFactsLedgerError, match="source witnesses|conversion witnesses"):
        CompanyFactsLedgerConversion(
            ledger=conversion.ledger,
            occurrences=conversion.occurrences,
            submission_sources=conversion.submission_sources,
            receipt=tampered,
        )


def test_frozen_receipt_and_conversion_reject_mutated_sequence_containers() -> None:
    accession = "0000000001-25-000001"
    conversion = _convert(
        _companyfacts([_entry(accession, 1)]),
        _submissions([(accession, "2025-02-15T16:00:00Z")]),
    )

    outer_mutated = copy(conversion.receipt)
    object.__setattr__(outer_mutated, "clocks", list(conversion.receipt.clocks))
    with pytest.raises(TypeError, match="immutable tuple"):
        CompanyFactsLedgerConversion(
            ledger=conversion.ledger,
            occurrences=conversion.occurrences,
            submission_sources=conversion.submission_sources,
            receipt=outer_mutated,
        )

    inner_mutated = copy(conversion.receipt)
    object.__setattr__(
        inner_mutated,
        "clocks",
        (list(conversion.receipt.clocks[0]), *conversion.receipt.clocks[1:]),
    )
    with pytest.raises(TypeError, match="immutable pairs"):
        CompanyFactsLedgerConversion(
            ledger=conversion.ledger,
            occurrences=conversion.occurrences,
            submission_sources=conversion.submission_sources,
            receipt=inner_mutated,
        )

    with pytest.raises(TypeError, match="occurrences must be an immutable tuple"):
        CompanyFactsLedgerConversion(
            ledger=conversion.ledger,
            occurrences=list(conversion.occurrences),
            submission_sources=conversion.submission_sources,
            receipt=conversion.receipt,
        )


def test_submission_source_witness_is_strict_and_immutable() -> None:
    with pytest.raises(CompanyFactsLedgerError, match="canonical SEC filename"):
        SubmissionSourceWitness(
            source_name="wrong.json",
            payload_sha256="a" * 64,
            row_count=0,
            is_older=True,
        )
    with pytest.raises(CompanyFactsLedgerError, match="row_count"):
        SubmissionSourceWitness(
            source_name="recent",
            payload_sha256="a" * 64,
            row_count=-1,
            is_older=False,
        )


def test_every_fact_submission_evidence_and_older_filename_must_match_capture_cik() -> None:
    accession = "0000000001-25-000001"
    other_cik_accession = "0000000002-25-000001"
    with pytest.raises(CompanyFactsLedgerError, match="CIK prefix"):
        _convert(
            _companyfacts([_entry(other_cik_accession, 1)]),
            _submissions([]),
        )
    with pytest.raises(CompanyFactsLedgerError, match="CIK prefix"):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([(other_cik_accession, "2025-02-15T16:00:00Z")]),
        )
    wrong_name = "CIK0000000002-submissions-001.json"
    with pytest.raises(CompanyFactsLedgerError, match="filename CIK"):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([], files=[{"name": wrong_name}]),
        )
    with pytest.raises(CompanyFactsLedgerError, match="parent_accession CIK prefix"):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([(accession, "2025-02-15T16:00:00Z")]),
            evidence=[
                RevisionEvidence(
                    accession,
                    other_cik_accession,
                    FactEventType.AMENDMENT,
                    "spine:wrong-cik",
                    "2025-04-01T12:00:03Z",
                )
            ],
        )


def test_sec_identifiers_reject_non_ascii_digits() -> None:
    accession = "0000000001-25-000001"
    unicode_accession = "٠٠٠٠٠٠٠٠٠١-٢٥-٠٠٠٠٠١"
    with pytest.raises(CompanyFactsLedgerError, match="accn"):
        _convert(
            _companyfacts([_entry(unicode_accession, 1)]),
            _submissions([]),
        )

    payload = _companyfacts([_entry(accession, 1)])
    manifest = _manifest(payload)
    payload["cik"] = "١"
    with pytest.raises(CompanyFactsLedgerError, match="companyfacts.cik"):
        convert_companyfacts_to_raw_ledger(
            companyfacts=payload,
            capture_manifest=manifest,
            submissions=_submissions([]),
            submissions_recorded_at="2025-04-01T12:00:02Z",
        )

    with pytest.raises(CompanyFactsLedgerError, match="submissions.cik"):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([], cik="١"),
        )

    unicode_filename = "CIK٠٠٠٠٠٠٠٠٠١-submissions-001.json"
    with pytest.raises(CompanyFactsLedgerError, match="canonical SEC CIK"):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([], files=[{"name": unicode_filename}]),
        )


def test_older_iterable_and_aggregate_bytes_are_stopped_incrementally() -> None:
    accession = "0000000001-25-000001"
    names = [f"CIK{CIK}-submissions-{index:03d}.json" for index in range(1, 4)]
    payload = _companyfacts([_entry(accession, 1)])
    submissions = _submissions(
        [(accession, "2025-02-15T16:00:00Z")],
        files=[{"name": name} for name in names],
    )
    consumed: list[str] = []

    def too_many():
        for name in names:
            consumed.append(name)
            yield name, _columns([])

    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="file count"):
        _convert(
            payload,
            submissions,
            older=too_many(),
            max_older_submissions_files=1,
        )
    assert consumed == names[:2]

    manifest = _manifest(payload)
    empty_evidence_bytes = raw_canonical_json([]).encode("utf-8")
    base_bytes = (
        len(source_canonical_json(payload).encode("utf-8"))
        + len(raw_canonical_json(submissions).encode("utf-8"))
        + len(raw_canonical_json(manifest).encode("utf-8"))
        + len(empty_evidence_bytes)
    )
    first_older_bytes = len(raw_canonical_json(_columns([])).encode("utf-8"))
    incrementally_consumed: list[str] = []

    def aggregate_overflow():
        for name in names:
            incrementally_consumed.append(name)
            yield name, _columns([])

    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="combined"):
        convert_companyfacts_to_raw_ledger(
            companyfacts=payload,
            capture_manifest=manifest,
            submissions=submissions,
            submissions_recorded_at="2025-04-01T12:00:02Z",
            older_submissions_files=aggregate_overflow(),
            max_total_input_bytes=base_bytes + first_older_bytes - 1,
        )
    assert incrementally_consumed == names[:1]


@pytest.mark.parametrize(
    "malformed",
    [
        [("CIK0000000001-submissions-001.json",)],
        [("CIK0000000001-submissions-001.json", [])],
        ["CIK0000000001-submissions-001.json"],
    ],
)
def test_malformed_older_iterable_entries_are_domain_errors(malformed) -> None:
    accession = "0000000001-25-000001"
    name = "CIK0000000001-submissions-001.json"
    with pytest.raises(CompanyFactsLedgerError):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([], files=[{"name": name}]),
            older=malformed,
        )


def test_broken_older_pair_iterator_is_wrapped_as_a_domain_error() -> None:
    accession = "0000000001-25-000001"
    name = "CIK0000000001-submissions-001.json"

    class BrokenPair:
        def __iter__(self):
            raise RuntimeError("broken pair iterator")

    with pytest.raises(CompanyFactsLedgerError, match="must be .* pairs"):
        _convert(
            _companyfacts([_entry(accession, 1)]),
            _submissions([], files=[{"name": name}]),
            older=[BrokenPair()],
        )


def test_hostile_mapping_items_and_iterator_acquisition_are_domain_errors() -> None:
    accession = "0000000001-25-000001"
    name = "CIK0000000001-submissions-001.json"
    payload = _companyfacts([_entry(accession, 1)])
    submissions_with_older = _submissions([], files=[{"name": name}])

    class HostileItems(dict):
        def items(self):
            raise RuntimeError("hostile items")

    class HostileIterator:
        def __iter__(self):
            raise RuntimeError("hostile iterator acquisition")

    for hostile in (HostileItems(), HostileIterator()):
        with pytest.raises(CompanyFactsLedgerError, match="older_submissions_files"):
            _convert(
                payload,
                submissions_with_older,
                older=hostile,
            )
        with pytest.raises(CompanyFactsLedgerError, match="revision_evidence"):
            _convert(
                payload,
                _submissions([]),
                evidence=hostile,
            )


def test_revision_evidence_has_independent_count_and_byte_bounds() -> None:
    original = "0000000001-24-000001"
    child_one = "0000000001-25-000001"
    child_two = "0000000001-25-000002"
    payload = _companyfacts(
        [_entry(original, 100), _entry(child_one, 110), _entry(child_two, 120)]
    )
    submissions = _submissions(
        [
            (original, "2024-02-15T16:00:00Z"),
            (child_one, "2025-02-15T16:00:00Z"),
            (child_two, "2025-02-16T16:00:00Z"),
        ]
    )
    evidence = [
        RevisionEvidence(
            child_one,
            original,
            FactEventType.AMENDMENT,
            "spine:one",
            "2025-04-01T12:00:03Z",
        ),
        RevisionEvidence(
            child_two,
            original,
            FactEventType.AMENDMENT,
            "spine:two",
            "2025-04-01T12:00:03Z",
        ),
    ]
    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="evidence count"):
        _convert(
            payload,
            submissions,
            evidence=evidence,
            max_revision_evidence=1,
        )
    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="evidence bytes"):
        _convert(
            payload,
            submissions,
            evidence=[
                RevisionEvidence(
                    child_one,
                    original,
                    FactEventType.AMENDMENT,
                    "x" * 500,
                    "2025-04-01T12:00:03Z",
                )
            ],
            max_revision_evidence_bytes=32,
        )
    with pytest.raises(CompanyFactsLedgerInputTooLarge, match="evidence bytes"):
        _convert(
            payload,
            submissions,
            max_revision_evidence_bytes=1,
        )


def test_duplicate_fact_revision_pairing_is_rejected_as_ambiguous() -> None:
    original = "0000000001-24-000001"
    child = "0000000001-25-000001"
    duplicate = _entry(original, 100)
    payload = _companyfacts([duplicate, dict(duplicate), _entry(child, 110)])
    with pytest.raises(CompanyFactsLedgerError, match="ambiguous fact pairing"):
        _convert(
            payload,
            _submissions(
                [
                    (original, "2024-02-15T16:00:00Z"),
                    (child, "2025-02-15T16:00:00Z"),
                ]
            ),
            evidence=[
                RevisionEvidence(
                    child,
                    original,
                    FactEventType.AMENDMENT,
                    "spine:ambiguous",
                    "2025-04-01T12:00:03Z",
                )
            ],
        )


def test_revision_accession_graph_cycle_fails_even_when_fact_keys_are_disjoint() -> None:
    first = "0000000001-24-000001"
    second = "0000000001-25-000001"
    payload = _companyfacts(
        [
            _entry(first, 100, start="2024-01-01", end="2024-12-31"),
            _entry(second, 110, start=None, end="2023-12-31"),
        ]
    )
    with pytest.raises(CompanyFactsLedgerError, match="graph contains a cycle"):
        _convert(
            payload,
            _submissions(
                [
                    (first, "2024-02-15T16:00:00Z"),
                    (second, "2025-02-15T16:00:00Z"),
                ]
            ),
            evidence=[
                RevisionEvidence(
                    first,
                    second,
                    FactEventType.AMENDMENT,
                    "spine:cycle-a",
                    "2025-04-01T12:00:03Z",
                ),
                RevisionEvidence(
                    second,
                    first,
                    FactEventType.AMENDMENT,
                    "spine:cycle-b",
                    "2025-04-01T12:00:03Z",
                ),
            ],
        )


def test_revision_evidence_graph_handles_a_large_bounded_chain_without_recursion() -> None:
    """The graph cap is 100k, so a 5k chain must not depend on DFS recursion."""
    count = 5_000
    accessions = [f"{CIK}-25-{index:06d}" for index in range(count + 1)]
    evidence = {
        accessions[index]: RevisionEvidence(
            accessions[index],
            accessions[index - 1],
            FactEventType.AMENDMENT,
            f"spine:chain-{index}",
            "2025-04-01T12:00:03Z",
        )
        for index in range(1, count + 1)
    }

    companyfacts_ledger_module._validate_revision_evidence_graph(evidence)


def test_topological_drafts_uses_one_heap_key_pass_for_a_large_wide_graph() -> None:
    """A wide conversion must not repeatedly sort and shift its ready list."""
    count = 5_000
    access_count = [0]

    class CountingDraft:
        def __init__(self, index: int) -> None:
            self.draft_id = f"draft-{index:05d}"
            self.source_order = index
            self._accepted_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        @property
        def accepted_at(self):
            access_count[0] += 1
            return self._accepted_at

    drafts = tuple(CountingDraft(index) for index in range(count))
    ordered = companyfacts_ledger_module._topological_drafts(drafts, {})

    assert [item.draft_id for item in ordered] == [
        f"draft-{index:05d}" for index in range(count)
    ]
    # Heap admission computes a priority once per root.  The former
    # pop(0)+ready.sort loop reread this property quadratically.
    assert access_count[0] <= count * 2


def test_typed_parent_ids_indexes_fact_keys_once_for_many_shared_parent_edges() -> None:
    """Evidence fan-out must reuse an accession+logical-key index."""
    count = 500
    logical_key_reads = [0]
    parent_accession = f"{CIK}-24-000001"
    parent_accepted = datetime(2024, 2, 15, 16, tzinfo=timezone.utc)
    child_accepted = datetime(2025, 2, 15, 16, tzinfo=timezone.utc)

    class CountingDraft:
        def __init__(
            self,
            *,
            accession: str,
            draft_id: str,
            source_order: int,
            logical_key: str,
            accepted_at: datetime,
        ) -> None:
            self.accession = accession
            self.draft_id = draft_id
            self.source_order = source_order
            self._logical_key = logical_key
            self.accepted_at = accepted_at

        @property
        def logical_key(self) -> str:
            logical_key_reads[0] += 1
            return self._logical_key

    drafts = []
    evidence = {}
    for index in range(1, count + 1):
        key = f"logical-{index}"
        child_accession = f"{CIK}-25-{index:06d}"
        drafts.append(
            CountingDraft(
                accession=parent_accession,
                draft_id=f"parent-{index}",
                source_order=index,
                logical_key=key,
                accepted_at=parent_accepted,
            )
        )
        drafts.append(
            CountingDraft(
                accession=child_accession,
                draft_id=f"child-{index}",
                source_order=count + index,
                logical_key=key,
                accepted_at=child_accepted,
            )
        )
        evidence[child_accession] = RevisionEvidence(
            child_accession,
            parent_accession,
            FactEventType.AMENDMENT,
            f"spine:fanout-{index}",
            "2025-04-01T12:00:03Z",
        )

    typed = companyfacts_ledger_module._typed_parent_ids(tuple(drafts), evidence)

    assert len(typed) == count
    assert logical_key_reads[0] <= len(drafts) * 2


def test_revision_chain_propagates_ancestor_evidence_availability() -> None:
    original = "0000000001-24-000001"
    amendment = "0000000001-25-000001"
    recast = "0000000001-25-000002"
    conversion = _convert(
        _companyfacts(
            [
                _entry(original, 100),
                _entry(amendment, 110, form="10-K/A"),
                _entry(recast, 120),
            ]
        ),
        _submissions(
            [
                (original, "2024-02-15T16:00:00Z"),
                (amendment, "2025-02-15T16:00:00Z"),
                (recast, "2025-03-15T16:00:00Z"),
            ]
        ),
        evidence=[
            RevisionEvidence(
                amendment,
                original,
                FactEventType.AMENDMENT,
                "spine:late-parent-evidence",
                "2025-06-01T00:00:00Z",
            ),
            RevisionEvidence(
                recast,
                amendment,
                FactEventType.COMPARATIVE_RECAST,
                "spine:earlier-child-evidence",
                "2025-05-01T00:00:00Z",
            ),
        ],
    )
    by_accession = {item.accession: item.occurrence for item in conversion.occurrences}

    assert by_accession[amendment].recorded_at == datetime(
        2025, 6, 1, tzinfo=timezone.utc
    )
    assert by_accession[recast].recorded_at == datetime(
        2025, 6, 1, tzinfo=timezone.utc
    )
    before_parent_available = conversion.ledger.select(
        by_accession[original].logical_key,
        as_of="2025-05-15T00:00:00Z",
        clock=ReplayClock.SYSTEM,
    )
    assert before_parent_available.occurrence == by_accession[original]


def test_revision_parent_final_id_is_bound_into_child_occurrence_identity() -> None:
    first_parent = "0000000001-23-000001"
    second_parent = "0000000001-24-000001"
    child = "0000000001-25-000001"
    payload = _companyfacts(
        [
            _entry(first_parent, 90),
            _entry(second_parent, 100),
            _entry(child, 110),
        ]
    )
    submissions = _submissions(
        [
            (first_parent, "2023-02-15T16:00:00Z"),
            (second_parent, "2024-02-15T16:00:00Z"),
            (child, "2025-02-15T16:00:00Z"),
        ]
    )

    def converted(parent: str):
        return _convert(
            payload,
            submissions,
            evidence=[
                RevisionEvidence(
                    child,
                    parent,
                    FactEventType.AMENDMENT,
                    "spine:same-evidence-id",
                    "2025-04-01T12:00:03Z",
                )
            ],
        )

    first = next(
        item.occurrence
        for item in converted(first_parent).occurrences
        if item.accession == child
    )
    second = next(
        item.occurrence
        for item in converted(second_parent).occurrences
        if item.accession == child
    )

    assert first.revision_of != second.revision_of
    assert first.occurrence_id != second.occurrence_id
