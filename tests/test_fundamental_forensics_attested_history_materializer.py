"""Pure planning contracts for the offline B4 materializer seam."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import pytest

import engine.fundamental_forensics.attested_history_materializer as materializer
import engine.fundamental_forensics.attested_query_snapshots as b4
from engine.fundamental_forensics.attested_history_materializer import (
    AttestedHistoryMaterializerError,
    enumerate_attested_binding_candidates,
)
from engine.fundamental_forensics.attested_query_snapshots import (
    AttestationMaterial,
    prepare_attested_query_snapshot,
)
from engine.fundamental_forensics.filing_attestation import (
    PinnedSourceAuthority,
    build_filing_attestation,
)
from engine.fundamental_forensics.query_snapshots import QuerySnapshot, _snapshot_id


ROOT = Path(__file__).resolve().parents[1]


def _b4_helpers():
    """Load real B4 fixtures without making their test module a dependency."""
    path = ROOT / "tests" / "test_fundamental_forensics_attested_query_snapshots.py"
    spec = importlib.util.spec_from_file_location("_b4_materializer_fixture_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _leaf(report, occurrence_id):
    return next(item for item in report.leaves if item.occurrence_id == occurrence_id)


def test_unique_exact_candidate_emits_b4_binding_without_source_or_store_reads(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, expected = helper._material(monkeypatch, tmp_path)

    def no_source_read(*_args, **_kwargs):
        raise AssertionError("pure materializer must not renew B3 source evidence")

    monkeypatch.setattr(PinnedSourceAuthority, "read_file", no_source_read)
    monkeypatch.setattr(PinnedSourceAuthority, "read_gzip_file", no_source_read)
    monkeypatch.setattr(PinnedSourceAuthority, "read_archive_document", no_source_read)

    report = enumerate_attested_binding_candidates(
        query_snapshot=base,
        companyfacts_conversion=conversion,
        attestation_materials=(material,),
    )

    assert report.bindings == (expected,)
    leaf = _leaf(report, expected.occurrence_id)
    assert leaf.binding == expected
    assert [(item.attestation_id, item.match_id) for item in leaf.candidates] == [
        (expected.attestation_id, expected.match_id)
    ]
    assert leaf.rejection_reasons == ()
    assert report.used_attestation_ids == (expected.attestation_id,)
    assert report.unused_attestation_ids == ()
    assert report.coverage[0].status == "all_leaves_attested"

    # Restored B3 records are also sufficient for a no-I/O scheduled preflight.
    from_records = enumerate_attested_binding_candidates(
        query_snapshot=base,
        companyfacts_conversion=conversion,
        attestation_records=(material.attestation,),
    )
    assert from_records.bindings == report.bindings


def test_partial_coverage_keeps_unbound_selected_leaves_and_reasons(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, _prepared = helper._mixed_coverage_prepared(
        monkeypatch, tmp_path
    )
    report = enumerate_attested_binding_candidates(
        query_snapshot=base,
        companyfacts_conversion=conversion,
        attestation_materials=(material,),
    )

    bound = report.bindings[0].occurrence_id
    missing = next(
        item.occurrence_id
        for item in base.ledger.events
        if item.occurrence_id != bound and item.concept_qname == "us-gaap:GrossProfit"
    )
    assert _leaf(report, missing).rejection_reasons == (
        "selected_occurrence_not_in_companyfacts_conversion",
    )
    assert _leaf(report, missing).binding is None

    statuses = {item.root_cell_id: item.status for item in report.coverage}
    by_metric = {cell.metric_id: cell.cell_id for cell in base.matrix.cells}
    assert statuses == {
        by_metric["gross_margin"]: "partially_attested",
        by_metric["revenue"]: "all_leaves_attested",
        by_metric["gross_profit"]: "not_attested",
        by_metric["net_income_loss"]: "not_evaluable",
    }


def test_multiple_exact_b3_records_stay_ambiguous_and_emit_no_binding(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, expected = helper._material(monkeypatch, tmp_path)
    later = AttestationMaterial(
        attestation=build_filing_attestation(
            material.package,
            material.extraction,
            authority=material.authority,
            companyfacts_paths=material.companyfacts_paths,
            attested_at="2026-08-02T17:01:00.000000Z",
        ),
        package=material.package,
        extraction=material.extraction,
        authority=material.authority,
        companyfacts_paths=material.companyfacts_paths,
    )

    report = enumerate_attested_binding_candidates(
        query_snapshot=base,
        companyfacts_conversion=conversion,
        attestation_materials=(later, material),
    )

    leaf = _leaf(report, expected.occurrence_id)
    assert len(leaf.candidates) == 2
    assert leaf.rejection_reasons == ("ambiguous_exact_b3_matches",)
    assert leaf.binding is None
    assert report.bindings == ()
    assert report.coverage[0].status == "not_attested"
    assert report.unused_attestation_ids == tuple(
        sorted((material.attestation.attestation_id, later.attestation.attestation_id))
    )


def test_b3_record_without_companyfacts_projection_preserves_non_attested_coverage(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, expected = helper._material(monkeypatch, tmp_path)
    no_companyfacts = build_filing_attestation(
        material.package,
        material.extraction,
        authority=material.authority,
        attested_at="2026-08-02T17:01:00.000000Z",
    )

    report = enumerate_attested_binding_candidates(
        query_snapshot=base,
        companyfacts_conversion=conversion,
        attestation_records=(no_companyfacts,),
    )

    leaf = _leaf(report, expected.occurrence_id)
    assert leaf.candidates == ()
    assert leaf.rejection_reasons == (
        "no_b3_attestation_binds_companyfacts_conversion",
    )
    assert report.bindings == ()
    assert report.coverage[0].status == "not_attested"


def test_reported_binding_is_accepted_by_the_existing_b4_preparer(monkeypatch, tmp_path):
    helper = _b4_helpers()
    store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)
    report = enumerate_attested_binding_candidates(
        query_snapshot=base,
        companyfacts_conversion=conversion,
        attestation_materials=(material,),
    )

    prepared = prepare_attested_query_snapshot(
        store=store,
        query_snapshot_id=base.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
        occurrence_bindings=report.bindings,
        operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
        published_at="2026-08-02T19:01:00.000000Z",
    )
    assert prepared.manifest["base_snapshot"]["snapshot_id"] == base.snapshot_id


def test_requires_one_immutable_b3_input_route_and_enforces_candidate_cap(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)

    with pytest.raises(AttestedHistoryMaterializerError, match="immutable tuple"):
        enumerate_attested_binding_candidates(
            query_snapshot=base,
            companyfacts_conversion=conversion,
            attestation_materials=[material],  # type: ignore[arg-type]
        )
    with pytest.raises(AttestedHistoryMaterializerError, match="exactly one"):
        enumerate_attested_binding_candidates(
            query_snapshot=base,
            companyfacts_conversion=conversion,
            attestation_materials=(material,),
            attestation_records=(material.attestation,),
        )

    monkeypatch.setattr(materializer, "HARD_MAX_ATTESTED_HISTORY_CANDIDATES", 0)
    with pytest.raises(AttestedHistoryMaterializerError, match="candidate count exceeds"):
        enumerate_attested_binding_candidates(
            query_snapshot=base,
            companyfacts_conversion=conversion,
            attestation_materials=(material,),
        )


def test_rejects_a_hand_built_query_snapshot_with_forged_identity(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)
    forged_id = "ffqs_" + ("0" * 64)
    forged = QuerySnapshot(
        snapshot_id=forged_id,
        manifest_key=f"fundamental_forensics/query-snapshots/v1/manifests/{forged_id}.json",
        manifest={},
        matrix=base.matrix,
        ledger=base.ledger,
        filing_metadata=base.filing_metadata,
        cells=base.cells,
    )

    with pytest.raises(AttestedHistoryMaterializerError, match="snapshot invariant failed"):
        enumerate_attested_binding_candidates(
            query_snapshot=forged,
            companyfacts_conversion=conversion,
            attestation_materials=(material,),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("query_hash", "0" * 64),
        ("governance_bundle_id", "0" * 64),
        ("ledger_event_count", 999),
    ),
)
def test_rejects_rehashed_manifest_crosswired_from_loaded_snapshot(
    monkeypatch,
    tmp_path,
    field,
    value,
):
    helper = _b4_helpers()
    _store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)
    manifest = dict(base.manifest)
    manifest[field] = value
    body = dict(manifest)
    body.pop("snapshot_id")
    manifest["snapshot_id"] = _snapshot_id(body)
    forged = QuerySnapshot(
        snapshot_id=manifest["snapshot_id"],
        manifest_key=(
            "fundamental_forensics/query-snapshots/v1/manifests/"
            f"{manifest['snapshot_id']}.json"
        ),
        manifest=manifest,
        matrix=base.matrix,
        ledger=base.ledger,
        filing_metadata=base.filing_metadata,
        cells=base.cells,
    )

    with pytest.raises(AttestedHistoryMaterializerError, match="snapshot invariant failed"):
        enumerate_attested_binding_candidates(
            query_snapshot=forged,
            companyfacts_conversion=conversion,
            attestation_materials=(material,),
        )


def test_attestation_material_route_requires_structural_replay_bindings(
    monkeypatch,
    tmp_path,
):
    helper = _b4_helpers()
    _store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)

    with pytest.raises(
        AttestedHistoryMaterializerError,
        match="structurally bind its sealed B3 record",
    ):
        enumerate_attested_binding_candidates(
            query_snapshot=base,
            companyfacts_conversion=conversion,
            attestation_materials=(replace(material, companyfacts_paths=None),),
        )


def test_preflights_exact_b4_binding_wire_envelope(monkeypatch, tmp_path):
    helper = _b4_helpers()
    _store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)
    monkeypatch.setattr(b4, "HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS_BYTES", 64)

    with pytest.raises(
        AttestedHistoryMaterializerError,
        match="does not fit the B4 artifact envelope",
    ):
        enumerate_attested_binding_candidates(
            query_snapshot=base,
            companyfacts_conversion=conversion,
            attestation_materials=(material,),
        )
