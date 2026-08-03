"""Direct B4 first-base selection contracts.

The integration fixture is synthetic and network-free, but uses real B3,
Company Facts conversion, and query-snapshot objects.  This pins the pilot to
the ordinary governed query kernel rather than a caller-supplied occurrence.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
import sys

import pytest

from engine.fundamental_forensics.attested_history_pilot import (
    AttestedHistoryPilotError,
    filing_metadata_from_companyfacts,
    prepare_attested_history_base_candidate,
)
from engine.fundamental_forensics.attested_occurrence_governance import (
    build_attested_occurrence_governance_bundle,
)
from engine.fundamental_forensics.filing_attestation import build_filing_attestation
from engine.fundamental_forensics.query import (
    BitemporalMetricQueryEngine,
    QueryValidationError,
)


ROOT = Path(__file__).resolve().parents[1]
PILOT_CLOCK = "2026-08-03T18:00:00.000000Z"


def _b4_helpers():
    path = ROOT / "tests" / "test_fundamental_forensics_attested_query_snapshots.py"
    spec = importlib.util.spec_from_file_location("_pilot_b4_fixture_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prepare(*, conversion, attestation):
    return prepare_attested_history_base_candidate(
        conversion=conversion,
        attestation=attestation,
        ticker="AAA",
        source_snapshot_at=PILOT_CLOCK,
        recorded_at=PILOT_CLOCK,
        computed_at=PILOT_CLOCK,
        published_at=PILOT_CLOCK,
    )


def test_selects_only_the_exact_b3_corresponding_companyfacts_occurrence(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, _base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)

    result = _prepare(conversion=conversion, attestation=material.attestation)
    expected_match = material.attestation.to_dict()["company_facts"]["matches"][0]
    expected_occurrence = conversion.occurrences[0].occurrence

    assert result.selected_occurrence_id == expected_occurrence.occurrence_id
    assert result.selected_match_id == expected_match["match_id"]
    assert result.prepared.matrix.cells[0].metric_id == "attested_occurrence"
    selected = {
        node.provenance.selected_raw_fact.occurrence_id
        for node in result.prepared.matrix.cells[0].nodes
        if node.provenance.selected_raw_fact is not None
    }
    assert selected == {expected_occurrence.occurrence_id}
    assert set(filing_metadata_from_companyfacts(conversion)) == {
        item.occurrence.occurrence_id for item in conversion.occurrences
    }


def test_refuses_a_b3_record_without_companyfacts_authority(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, _base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)
    no_companyfacts = build_filing_attestation(
        material.package,
        material.extraction,
        authority=material.authority,
        attested_at="2026-08-02T17:01:00.000000Z",
    )

    with pytest.raises(AttestedHistoryPilotError, match="no Company Facts evidence"):
        _prepare(conversion=conversion, attestation=no_companyfacts)


def test_preparation_is_deterministic_and_has_no_selected_occurrence_override(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, _base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)

    first = _prepare(conversion=conversion, attestation=material.attestation)
    second = _prepare(conversion=conversion, attestation=material.attestation)

    assert first.selected_occurrence_id == second.selected_occurrence_id
    assert first.selected_match_id == second.selected_match_id
    assert first.prepared.snapshot_id == second.prepared.snapshot_id
    assert first.prepared.manifest == second.prepared.manifest
    # The public API has no occurrence-id parameter: a caller has only B3's
    # exact correspondence and the governed query selector to work through.
    assert "occurrence_id" not in inspect.signature(
        prepare_attested_history_base_candidate
    ).parameters


def test_real_shape_unrelated_filed_date_anomaly_cannot_poison_exact_b3_candidate(
    monkeypatch, tmp_path
):
    """Pin AAPL's real UTC acceptance-date versus SEC filed-date shape.

    AAPL's retained history contains filings accepted around 22:00 UTC whose
    Company Facts ``filed`` date is the following calendar day.  The ordinary
    query invariant correctly rejects that metadata relationship.  B4 must
    therefore bind only the metadata for the exact B3 candidate it is trying,
    while continuing to query the complete committed ledger.
    """
    helper = _b4_helpers()
    companyfacts = {
        "cik": 1,
        "entityName": "Fixture",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-01-01",
                                "end": "2024-12-31",
                                "val": 1,
                                "accn": "0000000001-26-000001",
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-02-20",
                                "frame": "CY2024",
                            },
                            {
                                "start": "2018-01-01",
                                "end": "2018-12-31",
                                "val": 2,
                                "accn": "0000000001-19-000119",
                                "fy": 2018,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2019-10-31",
                                "frame": "CY2018",
                            },
                        ]
                    },
                }
            }
        },
    }
    submissions = {
        "cik": "0000000001",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000000001-26-000001",
                    "0000000001-19-000119",
                ],
                "form": ["10-K", "10-K"],
                "filingDate": ["2026-02-20", "2019-10-31"],
                "acceptanceDateTime": [
                    "2026-02-20T16:00:00.000000Z",
                    "2019-10-30T22:12:36.000000Z",
                ],
                "primaryDocument": ["annual.htm", "historical.htm"],
            }
        },
    }
    _store, _base, material, conversion, _expected = helper._material(
        monkeypatch,
        tmp_path,
        companyfacts_response=json.dumps(
            companyfacts, separators=(",", ":")
        ).encode("utf-8"),
        submissions=submissions,
    )

    with pytest.raises(
        QueryValidationError, match="filing metadata filed_at follows source acceptance"
    ):
        target = next(
            item.occurrence
            for item in conversion.occurrences
            if item.accession == "0000000001-26-000001"
        )
        BitemporalMetricQueryEngine(
            conversion.ledger,
            build_attested_occurrence_governance_bundle(
                occurrence=target, recorded_at=PILOT_CLOCK
            ),
            entities={"AAA": conversion.receipt.cik},
            filing_metadata=filing_metadata_from_companyfacts(conversion),
        )

    result = _prepare(conversion=conversion, attestation=material.attestation)
    target = next(
        item.occurrence
        for item in conversion.occurrences
        if item.accession == "0000000001-26-000001"
    )
    assert len(conversion.ledger.events) == 2
    assert result.selected_occurrence_id == target.occurrence_id
    assert result.prepared.matrix.cells[0].state.value == "value"
    assert {
        node.provenance.selected_raw_fact.occurrence_id
        for node in result.prepared.matrix.cells[0].nodes
        if node.provenance.selected_raw_fact is not None
    } == {target.occurrence_id}
