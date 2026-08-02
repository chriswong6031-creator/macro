"""Adversarial contracts for the immutable ``ffqsv2_`` verified-history overlay."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from collectors.fundamental_forensics_companyfacts import companyfacts_capture_from_json_bytes
from engine.fundamental_forensics.attested_query_snapshots import (
    AttestationMaterial,
    AttestedOccurrenceBinding,
    AttestedQuerySnapshotError,
    load_attested_query_snapshot,
    prepare_attested_query_snapshot,
    publish_attested_query_snapshot,
    verify_attested_query_snapshot_source,
)
import engine.fundamental_forensics.attested_query_snapshots as attested_snapshots
import engine.fundamental_forensics.companyfacts_ledger as companyfacts_ledger
from engine.fundamental_forensics.companyfacts_ledger import (
    CompanyFactsLedgerConversion,
    convert_companyfacts_to_raw_ledger,
)
from engine.fundamental_forensics.metric_registry import load_core_metric_registry
from engine.fundamental_forensics.query import BitemporalMetricQueryEngine, FilingMetadata, PeriodRequest, QueryPolicy
from engine.fundamental_forensics.query_snapshots import prepare_query_snapshot, publish_query_snapshot
from engine.fundamental_forensics.raw_ledger import RawFactLedger


ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-08-02T17:00:00.000000Z"


def _b3_helpers():
    """Load the sealed B3 fixture helpers without making their tests a dependency."""
    path = ROOT / "tests" / "test_fundamental_forensics_attestation.py"
    spec = importlib.util.spec_from_file_location("_b3_fixture_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _attestation(*, helper, monkeypatch, package, extraction, authority, paths):
    """Build B3 evidence with the kernel's mandatory explicit clock."""
    from engine.fundamental_forensics.filing_attestation import build_filing_attestation

    del helper, monkeypatch
    return build_filing_attestation(
        package,
        extraction,
        authority=authority,
        companyfacts_paths=paths,
        attested_at=STAMP,
    )


def _material(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    helper = _b3_helpers()
    package, manifest, index_content = helper._package()
    extraction = helper._numeric_extraction(package, monkeypatch)
    state: dict = {}
    response = helper._companyfacts_body()
    authority = helper._authority(
        tmp_path,
        package,
        manifest,
        index_content,
        prepare=helper._companyfacts_prepare(state, response),
    )
    attestation = _attestation(
        helper=helper,
        monkeypatch=monkeypatch,
        package=package,
        extraction=extraction,
        authority=authority,
        paths=state["paths"],
    )
    capture_bytes = authority.read_file(kind="raw", relative_path=state["paths"].capture_path, maximum_bytes=1024 * 1024).content
    manifest_bytes = authority.read_file(kind="archive", relative_path=state["paths"].manifest_path, maximum_bytes=1024 * 1024).content
    companyfacts_capture_from_json_bytes(capture_bytes)
    companyfacts = json.loads(response)
    capture_manifest = json.loads(manifest_bytes)
    submissions = {
        "cik": "0000000001",
        "filings": {
            "recent": {
                "accessionNumber": ["0000000001-26-000001"],
                "form": ["10-K"],
                "filingDate": ["2026-02-20"],
                "acceptanceDateTime": ["2026-02-20T16:00:00.000000Z"],
                "primaryDocument": ["annual.htm"],
            }
        }
    }
    conversion = convert_companyfacts_to_raw_ledger(
        companyfacts=companyfacts,
        capture_manifest=capture_manifest,
        submissions=submissions,
        submissions_recorded_at="2026-08-02T16:30:00.000000Z",
    )
    occurrence = conversion.occurrences[0].occurrence
    metadata = {
        occurrence.occurrence_id: FilingMetadata(
            accession=occurrence.source.accession,
            document_id=occurrence.source.document_id,
            source_body_sha256=occurrence.source.body_sha256,
            available_at=occurrence.recorded_at,
            form="10-K",
        )
    }
    # The current governed core catalog rightly rejects dimensions-unknown
    # Company Facts rows for a consolidated metric. B4 is an overlay contract,
    # so exercise its selected-raw-fact join under a narrowly test-local future
    # profile that admits this row; B4 itself continues to preserve
    # ``dimensions_known=false`` and makes no dimensional identity claim.
    monkeypatch.setattr(
        BitemporalMetricQueryEngine,
        "_fact_dimensions_allowed",
        staticmethod(lambda fact, contract: not fact.context.explicit_dimensions and not fact.context.typed_dimensions),
    )
    matrix = BitemporalMetricQueryEngine(
        conversion.ledger,
        load_core_metric_registry(ROOT),
        entities={"AAA": "0000000001"},
        filing_metadata=metadata,
    ).query_matrix(
        tickers=["AAA"],
        metrics=["revenue"],
        periods=[PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024")],
        policy=QueryPolicy(source_snapshot_at="2026-08-02T18:00:00.000000Z", recorded_at="2026-08-02T18:00:00.000000Z"),
    )
    store = authority._store
    base = publish_query_snapshot(
        store,
        prepare_query_snapshot(
            matrix=matrix,
            ledger=conversion.ledger,
            filing_metadata=metadata,
            computed_at="2026-08-02T18:32:00.000000Z",
            published_at="2026-08-02T18:33:00.000000Z",
        ),
    )
    match = attestation.to_dict()["company_facts"]["matches"][0]
    material = AttestationMaterial(
        attestation=attestation,
        package=package,
        extraction=extraction,
        authority=authority,
        companyfacts_paths=state["paths"],
    )
    binding = AttestedOccurrenceBinding(
        occurrence_id=occurrence.occurrence_id,
        attestation_id=attestation.attestation_id,
        match_id=match["match_id"],
    )
    return store, base, material, conversion, binding


def _prepared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    store, base, material, conversion, binding = _material(monkeypatch, tmp_path)
    prepared = prepare_attested_query_snapshot(
        store=store,
        query_snapshot_id=base.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
        occurrence_bindings=(binding,),
        operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
        published_at="2026-08-02T19:01:00.000000Z",
    )
    return store, base, material, conversion, binding, prepared


def _mixed_coverage_prepared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build a real formula matrix with one exact join and visible uncovered leaves."""
    store, _base, material, conversion, binding = _material(monkeypatch, tmp_path)
    revenue = conversion.occurrences[0].occurrence
    gross_profit = replace(
        revenue,
        concept_qname="us-gaap:GrossProfit",
        source_occurrence_key="b4-test-uncovered-gross-profit",
        occurrence_id=None,
    )
    ledger = RawFactLedger((revenue, gross_profit))
    metadata = {
        item.occurrence_id: FilingMetadata(
            accession=item.source.accession,
            document_id=item.source.document_id,
            source_body_sha256=item.source.body_sha256,
            available_at=item.recorded_at,
            form="10-K",
        )
        for item in ledger.events
    }
    matrix = BitemporalMetricQueryEngine(
        ledger,
        load_core_metric_registry(ROOT),
        entities={"AAA": "0000000001"},
        filing_metadata=metadata,
    ).query_matrix(
        tickers=["AAA"],
        metrics=["gross_margin", "revenue", "gross_profit", "net_income_loss"],
        periods=[PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024")],
        policy=QueryPolicy(
            source_snapshot_at="2026-08-02T18:00:00.000000Z",
            recorded_at="2026-08-02T18:00:00.000000Z",
        ),
    )
    base = publish_query_snapshot(
        store,
        prepare_query_snapshot(
            matrix=matrix,
            ledger=ledger,
            filing_metadata=metadata,
            computed_at="2026-08-02T18:34:00.000000Z",
            published_at="2026-08-02T18:35:00.000000Z",
        ),
    )
    prepared = prepare_attested_query_snapshot(
        store=store,
        query_snapshot_id=base.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
        occurrence_bindings=(binding,),
        operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
        published_at="2026-08-02T19:01:00.000000Z",
    )
    return store, base, material, conversion, prepared


def test_real_b3_companyfacts_conversion_path_publishes_and_renews(monkeypatch, tmp_path):
    store, base, material, conversion, binding, prepared = _prepared(monkeypatch, tmp_path)
    snapshot = publish_attested_query_snapshot(
        store, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    assert snapshot.snapshot_id.startswith("ffqsv2_")
    assert snapshot.base_snapshot_id == base.snapshot_id
    assert snapshot.manifest["base_snapshot"]["snapshot_id"] == base.snapshot_id
    assert snapshot.cell_coverage[0]["status"] == "all_leaves_attested"
    assert snapshot.manifest["nonclaims"]["dimensions_known"] is False
    assert load_attested_query_snapshot(store).snapshot_id == snapshot.snapshot_id
    assert verify_attested_query_snapshot_source(
        store,
        snapshot_id=snapshot.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    ).snapshot_id == snapshot.snapshot_id
    # The B4 pointer is deliberately isolated from the v1 query-snapshot key.
    assert store.get_bytes_strict("fundamental_forensics/attested-query-snapshots/v2/latest.json") is not None
    assert store.get_bytes_strict("fundamental_forensics/query-snapshots/v1/latest.json") is not None


def test_rejects_ambiguous_or_crosswired_occurrence_choice(monkeypatch, tmp_path):
    store, base, material, conversion, binding = _material(monkeypatch, tmp_path)
    with pytest.raises(AttestedQuerySnapshotError, match="choose an occurrence twice"):
        prepare_attested_query_snapshot(
            store=store, query_snapshot_id=base.snapshot_id, attestation_materials=(material,),
            companyfacts_conversion=conversion, occurrence_bindings=(binding, binding),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z", published_at="2026-08-02T19:01:00.000000Z",
        )
    forged = AttestedOccurrenceBinding(binding.occurrence_id, binding.attestation_id, "ffatt_match_" + "0" * 64)
    with pytest.raises(AttestedQuerySnapshotError, match="missing or reused"):
        prepare_attested_query_snapshot(
            store=store, query_snapshot_id=base.snapshot_id, attestation_materials=(material,),
            companyfacts_conversion=conversion, occurrence_bindings=(forged,),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z", published_at="2026-08-02T19:01:00.000000Z",
        )


def test_rejects_tampered_overlay_and_clock_rewind(monkeypatch, tmp_path):
    store, _base, material, conversion, _binding, prepared = _prepared(monkeypatch, tmp_path)
    with pytest.raises(AttestedQuerySnapshotError, match="predates"):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=prepared.manifest["base_snapshot"]["snapshot_id"],
            attestation_materials=(material,),
            companyfacts_conversion=conversion,
            occurrence_bindings=(_binding,),
            operator_verification_observed_at="2026-08-02T01:00:00.000000Z",
            published_at="2026-08-02T19:01:00.000000Z",
        )
    snapshot = publish_attested_query_snapshot(
        store, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    binding_object = next(item for item in prepared.artifacts if item.role == "bindings_json")
    assert store.put_bytes(binding_object.object_key, b"{}") is True
    with pytest.raises(AttestedQuerySnapshotError, match="digest mismatch"):
        load_attested_query_snapshot(store, snapshot_id=snapshot.snapshot_id)


def test_coverage_states_are_exact_and_nonclaims_are_frozen(monkeypatch, tmp_path):
    rows = attested_snapshots._coverage_rows(
        {"all": ("a",), "partial": ("a", "b"), "none": ("b",), "outside": ("z",), "empty": ()},
        ({"occurrence_id": "a"},),
        {"a", "b"},
    )
    assert {item["root_cell_id"]: item["status"] for item in rows} == {
        "all": "all_leaves_attested", "partial": "partially_attested", "none": "not_attested",
        "outside": "not_evaluable", "empty": "not_evaluable",
    }
    store, _base, material, conversion, _binding, prepared = _prepared(monkeypatch, tmp_path)
    snapshot = publish_attested_query_snapshot(
        store, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    assert snapshot.manifest["coverage_summary"]["root_cell_count"] == 1
    assert snapshot.manifest["nonclaims"]["trusted_timestamp_authority"] is False
    assert snapshot.manifest["nonclaims"]["investment_or_legal_authority"] is False
    with pytest.raises(TypeError):
        snapshot.manifest["nonclaims"]["dimensions_known"] = True
    with pytest.raises(TypeError):
        snapshot.attestations[next(iter(snapshot.attestations))]["company_facts"]["matches"][0]["unit"] = "shares"


def test_real_formula_roots_persist_mixed_coverage_and_renew_exactly(monkeypatch, tmp_path):
    """Coverage must follow actual v1 DAG leaves, not a hand-written helper map."""
    store, base, material, conversion, prepared = _mixed_coverage_prepared(monkeypatch, tmp_path)
    snapshot = publish_attested_query_snapshot(
        store, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    base_cells = {cell.metric_id: cell.cell_id for cell in base.matrix.cells}
    expected = {
        base_cells["gross_margin"]: "partially_attested",
        base_cells["revenue"]: "all_leaves_attested",
        base_cells["gross_profit"]: "not_attested",
        base_cells["net_income_loss"]: "not_evaluable",
    }
    assert {row["root_cell_id"]: row["status"] for row in snapshot.cell_coverage} == expected
    assert snapshot.manifest["coverage_summary"] == {
        "coverage_scope": "selected_raw_fact_leaves_only",
        "positive_label": "B3_selected_member_companyfacts_row_correspondence_only",
        "root_cell_count": 4,
        "all_leaves_attested": 1,
        "partially_attested": 1,
        "not_attested": 1,
        "not_evaluable": 1,
    }
    assert load_attested_query_snapshot(store, snapshot_id=snapshot.snapshot_id).cell_coverage == snapshot.cell_coverage
    assert verify_attested_query_snapshot_source(
        store,
        snapshot_id=snapshot.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    ).cell_coverage == snapshot.cell_coverage


def test_companyfacts_source_renewal_failure_rejects_prepare_and_source_verify(monkeypatch, tmp_path):
    store, base, material, conversion, binding, prepared = _prepared(monkeypatch, tmp_path)
    snapshot = publish_attested_query_snapshot(
        store, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    paths = material.companyfacts_paths
    assert paths is not None
    response = material.authority._snapshot.entry_for(kind="raw", relative_path=paths.response_path)
    assert store.put_bytes(response.object_key, b"tampered Company Facts response") is True
    with pytest.raises(AttestedQuerySnapshotError, match="filing attestation source replay failed"):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=base.snapshot_id,
            attestation_materials=(material,),
            companyfacts_conversion=conversion,
            occurrence_bindings=(binding,),
            operator_verification_observed_at="2026-08-02T19:02:00.000000Z",
            published_at="2026-08-02T19:03:00.000000Z",
        )
    with pytest.raises(AttestedQuerySnapshotError, match="filing attestation source replay failed"):
        verify_attested_query_snapshot_source(
            store,
            snapshot_id=snapshot.snapshot_id,
            attestation_materials=(material,),
            companyfacts_conversion=conversion,
        )


def test_conversion_bridge_rejects_tampering_foreign_leaves_and_unused_attestations(monkeypatch, tmp_path):
    store, base, material, conversion, binding = _material(monkeypatch, tmp_path)
    foreign = AttestedOccurrenceBinding(
        "rawfact_" + "f" * 64,
        binding.attestation_id,
        binding.match_id,
    )
    with pytest.raises(AttestedQuerySnapshotError, match="selected converted occurrence"):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=base.snapshot_id,
            attestation_materials=(material,),
            companyfacts_conversion=conversion,
            occurrence_bindings=(foreign,),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
            published_at="2026-08-02T19:01:00.000000Z",
        )


@pytest.mark.parametrize(
    ("companion_change", "error"),
    (
        ({"start": "2023-01-01"}, "duration does not bind companion period"),
        ({"unit": "shares"}, "unit does not bind companion unit"),
    ),
)
def test_conversion_companion_cannot_rewrite_raw_period_or_unit(
    monkeypatch, tmp_path, companion_change, error,
):
    """A self-consistent conversion receipt cannot cross-wire companion metadata."""
    store, base, material, conversion, binding = _material(monkeypatch, tmp_path)
    companions = (
        replace(conversion.occurrences[0], **companion_change),
        *conversion.occurrences[1:],
    )
    output_sha = companyfacts_ledger._output_sha256(conversion.ledger, companions)
    receipt_body = conversion.receipt.to_dict(include_id=False)
    receipt_body["output_sha256"] = output_sha
    object.__setattr__(conversion.receipt, "output_sha256", output_sha)
    object.__setattr__(
        conversion.receipt,
        "receipt_id",
        companyfacts_ledger._receipt_id(receipt_body),
    )
    forged_conversion = CompanyFactsLedgerConversion(
        ledger=conversion.ledger,
        occurrences=companions,
        submission_sources=conversion.submission_sources,
        receipt=conversion.receipt,
    )
    with pytest.raises(AttestedQuerySnapshotError, match=error):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=base.snapshot_id,
            attestation_materials=(material,),
            companyfacts_conversion=forged_conversion,
            occurrence_bindings=(binding,),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
            published_at="2026-08-02T19:01:00.000000Z",
        )


def test_publish_renews_sources_and_freezes_prepared_identity_before_writes(monkeypatch, tmp_path):
    """Prepared is caller data; source replay and captured identity remain mandatory."""
    store, _base, material, conversion, _binding, prepared = _prepared(monkeypatch, tmp_path)
    real_snapshot_id = prepared.snapshot_id
    fake_snapshot_id = "ffqsv2_" + "f" * 64
    original_replay = attested_snapshots.verify_filing_attestation_source

    def mutate_prepared_during_replay(*args, **kwargs):
        object.__setattr__(prepared, "snapshot_id", fake_snapshot_id)
        object.__setattr__(prepared, "manifest_key", attested_snapshots._manifest_key(fake_snapshot_id))
        return original_replay(*args, **kwargs)

    monkeypatch.setattr(
        attested_snapshots,
        "verify_filing_attestation_source",
        mutate_prepared_during_replay,
    )
    snapshot = publish_attested_query_snapshot(
        store,
        prepared,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    )
    assert snapshot.snapshot_id == real_snapshot_id
    assert store.get_bytes_strict(attested_snapshots._manifest_key(fake_snapshot_id)) is None
    assert load_attested_query_snapshot(store).snapshot_id == real_snapshot_id

    poison_store, _base, poison_material, poison_conversion, _binding, poison_prepared = _prepared(
        monkeypatch, tmp_path / "source-replay-poison",
    )

    def reject_source_replay(*_args, **_kwargs):
        raise ValueError("source replay poison")

    monkeypatch.setattr(
        attested_snapshots,
        "verify_filing_attestation_source",
        reject_source_replay,
    )
    with pytest.raises(AttestedQuerySnapshotError, match="filing attestation source replay failed"):
        publish_attested_query_snapshot(
            poison_store,
            poison_prepared,
            attestation_materials=(poison_material,),
            companyfacts_conversion=poison_conversion,
        )
    assert poison_store.list_prefix(attested_snapshots.ATTESTED_QUERY_SNAPSHOT_PREFIX) == []


def test_conversion_bridge_rejects_receipt_missing_companion_and_unused_attestation(monkeypatch, tmp_path):
    store, base, material, conversion, binding = _material(monkeypatch, tmp_path)
    object.__setattr__(conversion.receipt, "output_sha256", "0" * 64)
    with pytest.raises(AttestedQuerySnapshotError, match="conversion invariant"):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=base.snapshot_id,
            attestation_materials=(material,),
            companyfacts_conversion=conversion,
            occurrence_bindings=(binding,),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
            published_at="2026-08-02T19:01:00.000000Z",
        )

    store, base, material, conversion, binding = _material(monkeypatch, tmp_path / "missing-companion")
    object.__setattr__(conversion, "occurrences", ())
    with pytest.raises(AttestedQuerySnapshotError, match="conversion invariant"):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=base.snapshot_id,
            attestation_materials=(material,),
            companyfacts_conversion=conversion,
            occurrence_bindings=(binding,),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
            published_at="2026-08-02T19:01:00.000000Z",
        )

    from engine.fundamental_forensics.filing_attestation import build_filing_attestation

    store, base, material, conversion, binding = _material(monkeypatch, tmp_path / "unused-attestation")
    surplus_kwargs = {
        "authority": material.authority,
        "companyfacts_paths": material.companyfacts_paths,
        "attested_at": "2026-08-02T17:01:00.000000Z",
    }
    surplus = AttestationMaterial(
        attestation=build_filing_attestation(
            material.package,
            material.extraction,
            **surplus_kwargs,
        ),
        package=material.package,
        extraction=material.extraction,
        authority=material.authority,
        companyfacts_paths=material.companyfacts_paths,
    )
    with pytest.raises(AttestedQuerySnapshotError, match="every stored attestation"):
        prepare_attested_query_snapshot(
            store=store,
            query_snapshot_id=base.snapshot_id,
            attestation_materials=(material, surplus),
            companyfacts_conversion=conversion,
            occurrence_bindings=(binding,),
            operator_verification_observed_at="2026-08-02T19:00:00.000000Z",
            published_at="2026-08-02T19:01:00.000000Z",
        )


class _BoundedProxy:
    """A store whose legacy strict method is poisonous to prove B4 never uses it."""

    def __init__(
        self,
        inner,
        *,
        reject_manifest: bool = False,
        reject_pointer: bool = False,
        corrupt_pointer_readback: bool = False,
    ):
        self.inner = inner
        self.reject_manifest = reject_manifest
        self.reject_pointer = reject_pointer
        self.corrupt_pointer_readback = corrupt_pointer_readback
        self.strict_calls = 0

    def get_bytes(self, key):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key):
        self.strict_calls += 1
        raise AssertionError("B4 must not invoke the mutable legacy strict read")

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        if self.reject_manifest and "/manifests/ffqsv2_" in key:
            return False
        if self.reject_pointer and key == attested_snapshots._latest_key():
            return False
        result = self.inner.put_bytes(key, data, content_type)
        if self.corrupt_pointer_readback and key == attested_snapshots._latest_key():
            assert self.inner.put_bytes(key, b"{}", content_type="application/json") is True
        return result

    def list_prefix(self, prefix):
        return self.inner.list_prefix(prefix)

    def exists(self, key):
        return self.inner.exists(key)

    def upload_time(self, key):
        return self.inner.upload_time(key)


def test_bounded_preflight_proxy_pointer_last_and_monotonicity(monkeypatch, tmp_path):
    store, base, material, conversion, binding, first = _prepared(monkeypatch, tmp_path)
    proxy = _BoundedProxy(store)
    # The B3 material holds the native pinned authority; only B4's v1 overlay
    # read goes through the hostile transport.
    prepared = prepare_attested_query_snapshot(
        store=proxy, query_snapshot_id=base.snapshot_id, attestation_materials=(material,),
        companyfacts_conversion=conversion, occurrence_bindings=(binding,),
        operator_verification_observed_at="2026-08-02T19:00:00.000000Z", published_at="2026-08-02T19:01:00.000000Z",
    )
    assert proxy.strict_calls == 0
    published = publish_attested_query_snapshot(
        proxy, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    assert proxy.strict_calls == 0
    later = prepare_attested_query_snapshot(
        store=proxy, query_snapshot_id=base.snapshot_id, attestation_materials=(material,),
        companyfacts_conversion=conversion, occurrence_bindings=(binding,),
        operator_verification_observed_at="2026-08-02T19:02:00.000000Z", published_at="2026-08-02T19:03:00.000000Z",
    )
    latest = publish_attested_query_snapshot(
        proxy, later, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    assert publish_attested_query_snapshot(
        proxy, later, attestation_materials=(material,), companyfacts_conversion=conversion,
    ).snapshot_id == latest.snapshot_id  # idempotent
    with pytest.raises(AttestedQuerySnapshotError, match="cannot rewind"):
        publish_attested_query_snapshot(
            proxy, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
        )
    blocked = _BoundedProxy(store, reject_manifest=True)
    third = prepare_attested_query_snapshot(
        store=blocked, query_snapshot_id=base.snapshot_id, attestation_materials=(material,),
        companyfacts_conversion=conversion, occurrence_bindings=(binding,),
        operator_verification_observed_at="2026-08-02T19:04:00.000000Z", published_at="2026-08-02T19:05:00.000000Z",
    )
    with pytest.raises(AttestedQuerySnapshotError, match="manifest write failed"):
        publish_attested_query_snapshot(
            blocked, third, attestation_materials=(material,), companyfacts_conversion=conversion,
        )
    assert load_attested_query_snapshot(store).snapshot_id == latest.snapshot_id


def test_bounded_load_and_pointer_failures_never_cross_into_v1(monkeypatch, tmp_path):
    store, base, material, conversion, binding, prepared = _prepared(monkeypatch, tmp_path)
    proxy = _BoundedProxy(store)
    v1_pointer_key = "fundamental_forensics/query-snapshots/v1/latest.json"
    v1_pointer = store.get_bytes_strict(v1_pointer_key)
    assert v1_pointer is not None
    snapshot = publish_attested_query_snapshot(
        proxy, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    assert store.get_bytes_strict(v1_pointer_key) == v1_pointer
    assert load_attested_query_snapshot(proxy).snapshot_id == snapshot.snapshot_id
    assert verify_attested_query_snapshot_source(
        proxy,
        snapshot_id=snapshot.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    ).snapshot_id == snapshot.snapshot_id
    assert proxy.strict_calls == 0

    latest_key = attested_snapshots._latest_key()
    original_pointer = store.get_bytes_strict(latest_key)
    assert original_pointer is not None
    malformed_base = json.loads(original_pointer)
    malformed_base["base_snapshot_id"] = "ffqs_" + "0" * 64
    assert store.put_bytes(
        latest_key,
        json.dumps(malformed_base, sort_keys=True, separators=(",", ":")).encode(),
        content_type="application/json",
    ) is True
    with pytest.raises(AttestedQuerySnapshotError, match="latest pointer does not bind manifest"):
        load_attested_query_snapshot(proxy)
    malformed_id = json.loads(original_pointer)
    malformed_id["snapshot_id"] = "ffqsv2_" + "0" * 64
    malformed_id["manifest_key"] = attested_snapshots._manifest_key(malformed_id["snapshot_id"])
    assert store.put_bytes(
        latest_key,
        json.dumps(malformed_id, sort_keys=True, separators=(",", ":")).encode(),
        content_type="application/json",
    ) is True
    with pytest.raises(AttestedQuerySnapshotError, match="required private object is missing"):
        load_attested_query_snapshot(proxy)
    assert store.put_bytes(latest_key, b" " + original_pointer, content_type="application/json") is True
    with pytest.raises(AttestedQuerySnapshotError, match="pointer is not canonical"):
        load_attested_query_snapshot(proxy)
    assert store.put_bytes(latest_key, original_pointer, content_type="application/json") is True

    rejected = _BoundedProxy(store, reject_pointer=True)
    later = prepare_attested_query_snapshot(
        store=rejected,
        query_snapshot_id=base.snapshot_id,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
        occurrence_bindings=(binding,),
        operator_verification_observed_at="2026-08-02T19:02:00.000000Z",
        published_at="2026-08-02T19:03:00.000000Z",
    )
    with pytest.raises(AttestedQuerySnapshotError, match="latest pointer write failed"):
        publish_attested_query_snapshot(
            rejected, later, attestation_materials=(material,), companyfacts_conversion=conversion,
        )
    assert load_attested_query_snapshot(proxy).snapshot_id == snapshot.snapshot_id
    assert store.get_bytes_strict(v1_pointer_key) == v1_pointer

    corrupt_store, _corrupt_base, corrupt_material, corrupt_conversion, _corrupt_binding, corrupt_prepared = _prepared(
        monkeypatch, tmp_path / "pointer-readback",
    )
    corrupt = _BoundedProxy(corrupt_store, corrupt_pointer_readback=True)
    with pytest.raises(AttestedQuerySnapshotError, match="pointer read-back mismatch"):
        publish_attested_query_snapshot(
            corrupt,
            corrupt_prepared,
            attestation_materials=(corrupt_material,),
            companyfacts_conversion=corrupt_conversion,
        )


def test_hostile_nominals_and_restore_json_fail_closed(monkeypatch, tmp_path):
    class HostileDict(dict):
        pass

    with pytest.raises(AttestedQuerySnapshotError, match="shape"):
        attested_snapshots._strict_object(HostileDict({"x": 1}), field="hostile", required=frozenset({"x"}))
    with pytest.raises(AttestedQuerySnapshotError, match="depth"):
        attested_snapshots._json_object(b'{"a":' * 70 + b"0" + b"}" * 70, field="deep", limit=4096)
    with pytest.raises(AttestedQuerySnapshotError, match="floats"):
        attested_snapshots._json_object(b'{"x":1.5}', field="float", limit=4096)
    store, _base, material, conversion, binding, prepared = _prepared(monkeypatch, tmp_path)
    with pytest.raises(AttestedQuerySnapshotError, match="immutable tuple"):
        prepare_attested_query_snapshot(
            store=store, query_snapshot_id=prepared.manifest["base_snapshot"]["snapshot_id"], attestation_materials=[material],
            companyfacts_conversion=conversion, occurrence_bindings=(binding,), operator_verification_observed_at="2026-08-02T19:00:00.000000Z", published_at="2026-08-02T19:01:00.000000Z",
        )
    snapshot = publish_attested_query_snapshot(
        store, prepared, attestation_materials=(material,), companyfacts_conversion=conversion,
    )
    duplicate = b'{"schema":"x","schema":"y"}'
    assert store.put_bytes(snapshot.manifest_key, duplicate, content_type="application/json") is True
    with pytest.raises(AttestedQuerySnapshotError, match="duplicate"):
        load_attested_query_snapshot(store, snapshot_id=snapshot.snapshot_id)


def test_forged_prepared_conversion_cannot_publish_a_pointer(monkeypatch, tmp_path):
    """A caller-constructed Prepared cannot cross-wire a B3 match around its companion."""
    store, _base, material, conversion_value, _binding, prepared = _prepared(monkeypatch, tmp_path)
    payloads = dict(prepared.payloads)
    conversion = json.loads(payloads["companyfacts_conversion_json"])
    conversion["occurrences"][0]["entry_index"] = 999  # receipt output SHA no longer binds companion metadata
    payloads["companyfacts_conversion_json"] = json.dumps(conversion, sort_keys=True, separators=(",", ":")).encode()
    changed = attested_snapshots._artifact("companyfacts_conversion_json", payloads["companyfacts_conversion_json"])
    artifacts = tuple(changed if item.role == changed.role else item for item in prepared.artifacts)
    manifest = attested_snapshots._thaw(prepared.manifest)
    manifest["objects"] = [item.to_dict() for item in artifacts]
    body = dict(manifest); body.pop("snapshot_id")
    snapshot_id = attested_snapshots._identity(body)
    manifest["snapshot_id"] = snapshot_id
    forged = attested_snapshots.PreparedAttestedQuerySnapshot(
        snapshot_id=snapshot_id,
        manifest_key=attested_snapshots._manifest_key(snapshot_id),
        manifest=manifest,
        artifacts=artifacts,
        payloads=payloads,
    )
    with pytest.raises(AttestedQuerySnapshotError, match="conversion"):
        publish_attested_query_snapshot(
            store,
            forged,
            attestation_materials=(material,),
            companyfacts_conversion=conversion_value,
        )
    assert store.get_bytes_strict("fundamental_forensics/attested-query-snapshots/v2/latest.json") is None
