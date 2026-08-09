"""Contract tests for immutable quarter catalogs and their CAS current pointer."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import jsonschema
import pytest

from engine.institutional_census.catalog import (
    FILINGS_COLUMNS,
    HOLDINGS_COLUMNS,
    MANAGER_RELATIONSHIP_COLUMNS,
    Institutional13FCatalogError,
    holding_bucket_role,
    load_catalog_generation,
    parquet_schema,
    prepare_catalog_generation,
    publish_catalog_generation,
)
from engine.institutional_census.models import (
    HOLDING_BUCKET_ROLES,
    CatalogPointer,
    catalog_pointer_key,
)
from engine.research_vault.r2_store import LocalStore

ROOT = Path(__file__).resolve().parents[1]
PERIOD = "2026-06-30"


def _digest(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()


def _receipt(seed: str) -> str:
    return "i13fraw_" + _digest(seed)


def _filing(accession: str, cik: str, receipt: str, accepted_at: str) -> dict:
    return {
        "accession": accession,
        "filer_cik": cik,
        "filer_name": f"Fixture Manager {cik}",
        "form": "13F-HR",
        "filing_date": accepted_at[:10],
        "accepted_at": accepted_at,
        "report_period": PERIOD,
        "report_type": "13F HOLDINGS REPORT",
        "form13f_file_number": "028-00001",
        "is_amendment": False,
        "amendment_number": None,
        "amendment_type": None,
        "amends_accession": None,
        "lineage_state": "original",
        "confidential_omitted": False,
        "table_entry_total": 1,
        "table_value_total_usd": 1000,
        "other_manager_count": 0,
        "source_receipt_id": receipt,
        "normalization_id": "norm_" + _digest(accession),
        "raw_sha256": _digest("raw:" + accession),
        "first_seen_at": accepted_at,
        "retained_at": "2026-08-07T18:00:00Z",
        "parser_version": "parser-v1",
        "quality_state": "valid",
    }


def _holding(accession: str, sk: int, cusip: str) -> dict:
    return {
        "accession": accession,
        "infotable_sk": sk,
        "name_of_issuer": f"Issuer {cusip}",
        "title_of_class": "COM",
        "cusip": cusip,
        "figi": None,
        "value_reported": "1000",
        "value_unit": "USD",
        "value_usd": 1000,
        "ssh_prn_amt": "10",
        "ssh_prn_type": "SH",
        "put_call": None,
        "investment_discretion": "SOLE",
        "other_manager": None,
        "voting_authority_sole": 10,
        "voting_authority_shared": 0,
        "voting_authority_none": 0,
        "row_hash": _digest(f"{accession}:{sk}:{cusip}"),
    }


def _manager(accession: str) -> dict:
    return {
        "accession": accession,
        "relationship_kind": "included_manager",
        "source_table": "OTHERMANAGER2",
        "manager_sequence": 1,
        "other_manager_sk": 1,
        "manager_cik": "1234",
        "manager_name": "Included Manager",
        "form13f_file_number": "028-00001",
        "crd_number": None,
        "sec_file_number": None,
    }


def _prepared(
    *,
    reverse: bool = False,
    published_at: str = "2026-08-07T19:00:00Z",
    coverage_state: str = "rolling",
):
    accessions = ["0001067983-26-000123", "0001350694-26-000456"]
    receipts = [_receipt("berkshire"), _receipt("bridgewater")]
    filings = [
        _filing(accessions[0], "1067983", receipts[0], "2026-08-07T16:30:00Z"),
        _filing(accessions[1], "1350694", receipts[1], "2026-08-07T17:30:00Z"),
    ]
    holdings = [
        _holding(accessions[0], 2, "084670702"),
        _holding(accessions[0], 1, "037833100"),
        _holding(accessions[1], 1, "594918104"),
    ]
    managers = [_manager(accessions[1])]
    if reverse:
        filings.reverse()
        holdings.reverse()
        receipts.reverse()
    return prepare_catalog_generation(
        report_period=PERIOD,
        source_cutoff_at="2026-08-07T18:00:00Z",
        published_at=published_at,
        producer_version="catalog-v1",
        filings=filings,
        holdings=holdings,
        manager_relationships=managers,
        source_receipt_ids=receipts,
        coverage={"state": coverage_state, "discovered_filings": 2, "complete": False},
    )


class _RecordingProxy:
    def __init__(self, inner: LocalStore, *, lose_pointer_ack: bool = False) -> None:
        self.inner = inner
        self.lose_pointer_ack = lose_pointer_ack
        self.conditional_calls: list[tuple[str, str | None]] = []

    def get_bytes(self, key):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key):
        return self.inner.get_bytes_strict(key)

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes_strict_bounded_versioned(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded_versioned(key, maximum_bytes)

    def validate_strict_conditional_write_capability(self):
        return self.inner.validate_strict_conditional_write_capability()

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        self.conditional_calls.append((key, expected_version))
        result = self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )
        if key == catalog_pointer_key(PERIOD) and self.lose_pointer_ack:
            self.lose_pointer_ack = False
            raise TimeoutError("simulated pointer acknowledgement loss")
        return result

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        raise AssertionError("catalog publication must never use unconditional put")

    def list_prefix(self, prefix):
        return self.inner.list_prefix(prefix)

    def exists(self, key):
        return self.inner.exists(key)

    def upload_time(self, key):
        return self.inner.upload_time(key)


class _SuccessorRaceProxy(_RecordingProxy):
    def __init__(self, inner: LocalStore, *, successor_payload: bytes) -> None:
        super().__init__(inner)
        self.successor_payload = successor_payload
        self.raced = False

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        if key == catalog_pointer_key(PERIOD) and not self.raced:
            self.raced = True
            assert self.inner.put_bytes_strict_conditional(
                key,
                self.successor_payload,
                expected_version=expected_version,
                content_type="application/json",
            )
            return False
        return super().put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )


def test_prepare_is_deterministic_and_parquet_is_projection_only() -> None:
    first = _prepared()
    second = _prepared(reverse=True)

    assert first.generation_id == second.generation_id
    assert first.manifest_payload == second.manifest_payload
    assert dict(first.payloads) == dict(second.payloads)
    assert [row["accession"] for row in first.filings] == sorted(
        row["accession"] for row in first.filings
    )
    assert [field.name for field in parquet_schema("filings_parquet")] == list(FILINGS_COLUMNS)
    assert [field.name for field in parquet_schema("holdings_parquet")] == list(HOLDINGS_COLUMNS)
    assert [field.name for field in parquet_schema("manager_relationships_parquet")] == list(
        MANAGER_RELATIONSHIP_COLUMNS
    )
    assert parquet_schema("holdings_parquet").metadata[b"authority"].startswith(
        b"projection-only"
    )


def test_publish_orders_artifacts_then_manifest_then_pointer_and_loads(tmp_path: Path) -> None:
    prepared = _prepared()
    proxy = _RecordingProxy(LocalStore(tmp_path / "store"))
    published = publish_catalog_generation(proxy, prepared)

    assert published.pointer_updated is True
    assert published.current_generation_id == prepared.generation_id
    assert published.superseded is False
    # Empty buckets are byte-identical and therefore share one content object;
    # only each first-seen immutable key needs a conditional create.
    expected_immutable_keys = list(
        dict.fromkeys(item.object_key for item in prepared.manifest.artifacts)
    )
    assert [key for key, _ in proxy.conditional_calls[:-2]] == expected_immutable_keys
    assert proxy.conditional_calls[-2][0] == prepared.manifest.manifest_key
    assert proxy.conditional_calls[-1][0] == catalog_pointer_key(PERIOD)

    restored = load_catalog_generation(proxy, report_period=PERIOD)
    assert restored.generation_id == prepared.generation_id
    assert tuple(dict(row) for row in restored.filings) == tuple(
        dict(row) for row in prepared.filings
    )
    assert tuple(dict(row) for row in restored.holdings) == tuple(
        dict(row) for row in prepared.holdings
    )


def test_manifest_and_pointer_validate_against_published_contracts(tmp_path: Path) -> None:
    prepared = _prepared()
    manifest_schema = json.loads(
        (ROOT / "contracts/institutional_13f_catalog_manifest.v1.schema.json").read_text()
    )
    pointer_schema = json.loads(
        (ROOT / "contracts/institutional_13f_catalog_pointer.v1.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(manifest_schema).validate(prepared.manifest.to_dict())
    pointer = CatalogPointer.from_manifest(prepared.manifest)
    jsonschema.Draft202012Validator(pointer_schema).validate(pointer.to_dict())

    store = LocalStore(tmp_path / "store")
    publish_catalog_generation(store, prepared)
    encoded = store.get_bytes(catalog_pointer_key(PERIOD))
    assert encoded == pointer.to_json_bytes()


def test_filing_projection_contract_persists_form13f_file_number() -> None:
    prepared = _prepared()
    schema = json.loads(
        (
            ROOT
            / "contracts"
            / "institutional_13f_filing_projection_row.v1.schema.json"
        ).read_text()
    )
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )

    for row in prepared.filings:
        validator.validate(dict(row))
        assert row["form13f_file_number"] == "028-00001"
    assert "form13f_file_number" in FILINGS_COLUMNS
    assert parquet_schema("filings_parquet").field("form13f_file_number").nullable


def test_republication_is_idempotent_and_does_not_advance_pointer(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    prepared = _prepared()
    first = publish_catalog_generation(store, prepared)
    second = publish_catalog_generation(store, prepared)

    assert first.pointer_updated is True
    assert second.pointer_updated is False
    assert second.generation_id == first.generation_id


def test_lost_pointer_acknowledgement_reconciles_exact_winner(tmp_path: Path) -> None:
    proxy = _RecordingProxy(LocalStore(tmp_path / "store"), lose_pointer_ack=True)
    prepared = _prepared()

    published = publish_catalog_generation(proxy, prepared)

    assert published.pointer_updated is True
    assert published.current_generation_id == prepared.generation_id
    assert (
        load_catalog_generation(proxy, report_period=PERIOD).generation_id
        == prepared.generation_id
    )


def test_pointer_conflict_preserves_verified_newer_successor(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    prior = _prepared(published_at="2026-08-07T19:00:00Z", coverage_state="prior")
    candidate = _prepared(
        published_at="2026-08-07T20:00:00Z", coverage_state="candidate"
    )
    successor = _prepared(
        published_at="2026-08-07T21:00:00Z", coverage_state="successor"
    )
    publish_catalog_generation(store, prior)
    publish_catalog_generation(store, successor)

    # Restore a valid older predecessor only to stage a deterministic race;
    # successor immutables stay present and verified in the test store.
    key = catalog_pointer_key(PERIOD)
    observed = store.get_bytes_strict_bounded_versioned(key, 16 * 1024)
    assert store.put_bytes_strict_conditional(
        key,
        CatalogPointer.from_manifest(prior.manifest).to_json_bytes(),
        expected_version=observed.version,
        content_type="application/json",
    )
    proxy = _SuccessorRaceProxy(
        store,
        successor_payload=CatalogPointer.from_manifest(successor.manifest).to_json_bytes(),
    )

    published = publish_catalog_generation(proxy, candidate)

    assert published.generation_id == candidate.generation_id
    assert published.pointer_updated is False
    assert published.superseded is True
    assert published.current_generation_id == successor.generation_id
    assert load_catalog_generation(store, report_period=PERIOD).generation_id == successor.generation_id


def test_newer_pointer_cannot_be_rewound(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    newer = _prepared(published_at="2026-08-08T19:00:00Z", coverage_state="newer")
    older = _prepared(published_at="2026-08-07T19:00:00Z", coverage_state="older")
    publish_catalog_generation(store, newer)

    with pytest.raises(Institutional13FCatalogError, match="rewind"):
        publish_catalog_generation(store, older)

    assert load_catalog_generation(store, report_period=PERIOD).generation_id == newer.generation_id


def _one_filing_successor(
    prior,
    *,
    source_cutoff_at: str,
    published_at: str,
    correction: dict | None = None,
):
    accession = str(prior.filings[0]["accession"])
    filings = [dict(prior.filings[0])]
    holdings = [
        dict(row) for row in prior.holdings if str(row["accession"]) == accession
    ]
    managers = [
        dict(row)
        for row in prior.manager_relationships
        if str(row["accession"]) == accession
    ]
    coverage = {"state": "rolling", "discovered_filings": 1, "complete": False}
    if correction is not None:
        coverage["correction"] = correction
    return prepare_catalog_generation(
        report_period=PERIOD,
        source_cutoff_at=source_cutoff_at,
        published_at=published_at,
        producer_version="catalog-v1",
        filings=filings,
        holdings=holdings,
        manager_relationships=managers,
        source_receipt_ids=[str(filings[0]["source_receipt_id"])],
        coverage=coverage,
    )


def _append_filing_successor(
    prior,
    *,
    accession: str,
    cik: str,
    receipt_seed: str,
    accepted_at: str,
    source_cutoff_at: str,
    published_at: str,
):
    receipt = _receipt(receipt_seed)
    filings = [dict(row) for row in prior.filings]
    filings.append(_filing(accession, cik, receipt, accepted_at))
    holdings = [dict(row) for row in prior.holdings]
    holdings.append(_holding(accession, 1, _digest(accession)[:9]))
    managers = [dict(row) for row in prior.manager_relationships]
    return prepare_catalog_generation(
        report_period=PERIOD,
        source_cutoff_at=source_cutoff_at,
        published_at=published_at,
        producer_version="catalog-v1",
        filings=filings,
        holdings=holdings,
        manager_relationships=managers,
        source_receipt_ids=[str(row["source_receipt_id"]) for row in filings],
        coverage={"state": "rolling", "discovered_filings": len(filings), "complete": False},
    )


def test_later_publication_cannot_rewind_source_cutoff_or_drop_filings(
    tmp_path: Path,
) -> None:
    store = LocalStore(tmp_path / "store")
    prior = _prepared(published_at="2026-08-07T19:00:00Z")
    publish_catalog_generation(store, prior)
    rewind = _one_filing_successor(
        prior,
        source_cutoff_at="2026-08-07T17:00:00Z",
        published_at="2026-08-07T20:00:00Z",
    )

    with pytest.raises(Institutional13FCatalogError, match="source_cutoff_at cannot rewind"):
        publish_catalog_generation(store, rewind)

    current = load_catalog_generation(store, report_period=PERIOD)
    assert current.generation_id == prior.generation_id
    assert current.manifest.counts.filing_rows == 2


def test_newer_cutoff_cannot_silently_drop_or_replace_accessions(
    tmp_path: Path,
) -> None:
    store = LocalStore(tmp_path / "store")
    prior = _prepared(published_at="2026-08-07T19:00:00Z")
    publish_catalog_generation(store, prior)
    truncated = _one_filing_successor(
        prior,
        source_cutoff_at="2026-08-07T20:00:00Z",
        published_at="2026-08-07T21:00:00Z",
    )

    with pytest.raises(
        Institutional13FCatalogError,
        match="drops or changes accessions without an explicit correction",
    ):
        publish_catalog_generation(store, truncated)

    assert load_catalog_generation(store, report_period=PERIOD).generation_id == prior.generation_id


def test_exact_hash_bound_correction_can_remove_a_named_accession(
    tmp_path: Path,
) -> None:
    store = LocalStore(tmp_path / "store")
    prior = _prepared(published_at="2026-08-07T19:00:00Z")
    publish_catalog_generation(store, prior)
    removed = str(prior.filings[1]["accession"])
    corrected = _one_filing_successor(
        prior,
        source_cutoff_at="2026-08-07T20:00:00Z",
        published_at="2026-08-07T21:00:00Z",
        correction={
            "schema": "institutional_13f.catalog_correction/v1",
            "supersedes_generation_id": prior.generation_id,
            "reason": "SEC completed-window reconciliation removed a quarantined filing.",
            "removed_accessions": [removed],
            "replaced_accessions": [],
        },
    )

    result = publish_catalog_generation(store, corrected)

    assert result.pointer_updated is True
    current = load_catalog_generation(store, report_period=PERIOD)
    assert current.generation_id == corrected.generation_id
    assert [row["accession"] for row in current.filings] == [prior.filings[0]["accession"]]


def test_disjoint_cas_winner_cannot_silently_discard_candidate_append(
    tmp_path: Path,
) -> None:
    store = LocalStore(tmp_path / "store")
    prior = _prepared(published_at="2026-08-07T19:00:00Z")
    candidate = _append_filing_successor(
        prior,
        accession="0001649339-26-000789",
        cik="1649339",
        receipt_seed="candidate-only-filing",
        accepted_at="2026-08-07T17:40:00Z",
        source_cutoff_at="2026-08-07T20:00:00Z",
        published_at="2026-08-07T20:30:00Z",
    )
    successor = _append_filing_successor(
        prior,
        accession="0001166559-26-000321",
        cik="1166559",
        receipt_seed="winner-only-filing",
        accepted_at="2026-08-07T17:50:00Z",
        source_cutoff_at="2026-08-07T21:00:00Z",
        published_at="2026-08-07T21:30:00Z",
    )
    publish_catalog_generation(store, prior)
    publish_catalog_generation(store, successor)

    # Leave the successor's immutable generation in place, then stage a race
    # from the shared predecessor so the winner lacks the candidate-only row.
    key = catalog_pointer_key(PERIOD)
    observed = store.get_bytes_strict_bounded_versioned(key, 16 * 1024)
    assert store.put_bytes_strict_conditional(
        key,
        CatalogPointer.from_manifest(prior.manifest).to_json_bytes(),
        expected_version=observed.version,
        content_type="application/json",
    )
    proxy = _SuccessorRaceProxy(
        store,
        successor_payload=CatalogPointer.from_manifest(successor.manifest).to_json_bytes(),
    )

    with pytest.raises(
        Institutional13FCatalogError,
        match="winner does not preserve the desired generation",
    ):
        publish_catalog_generation(proxy, candidate)

    current = load_catalog_generation(store, report_period=PERIOD)
    assert current.generation_id == successor.generation_id
    assert "0001649339-26-000789" not in {row["accession"] for row in current.filings}


def test_tampered_projection_or_manifest_is_rejected(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "store")
    prepared = _prepared()
    publish_catalog_generation(store, prepared)
    holdings = next(
        item
        for item in prepared.manifest.artifacts
        if item.role in HOLDING_BUCKET_ROLES and (item.row_count or 0) > 0
    )
    assert store.put_bytes(
        holdings.object_key,
        b"x" * holdings.byte_length,
        "application/vnd.apache.parquet",
    )

    with pytest.raises(Institutional13FCatalogError, match="digest or byte length"):
        load_catalog_generation(store, report_period=PERIOD)


def test_duplicate_primary_key_and_orphan_child_are_rejected() -> None:
    prepared = _prepared()
    duplicate = [dict(prepared.holdings[0]), dict(prepared.holdings[0])]
    with pytest.raises(Institutional13FCatalogError, match="duplicate holdings_parquet"):
        prepare_catalog_generation(
            report_period=PERIOD,
            source_cutoff_at="2026-08-07T18:00:00Z",
            published_at="2026-08-07T19:00:00Z",
            producer_version="catalog-v1",
            filings=[dict(item) for item in prepared.filings],
            holdings=duplicate,
            source_receipt_ids=[row["source_receipt_id"] for row in prepared.filings],
            coverage={"complete": False},
        )

    orphan = _holding("0000000001-26-000001", 1, "000000001")
    with pytest.raises(Institutional13FCatalogError, match="no filing"):
        prepare_catalog_generation(
            report_period=PERIOD,
            source_cutoff_at="2026-08-07T18:00:00Z",
            published_at="2026-08-07T19:00:00Z",
            producer_version="catalog-v1",
            filings=[dict(item) for item in prepared.filings],
            holdings=[orphan],
            source_receipt_ids=[row["source_receipt_id"] for row in prepared.filings],
            coverage={"complete": False},
        )


def test_manifest_identity_binds_counts_hashes_versions_and_three_clocks() -> None:
    prepared = _prepared()
    body = prepared.manifest.to_dict()
    assert set(body["clocks"]) == {"report_period", "source_cutoff_at", "published_at"}
    assert body["producer_version"] == "catalog-v1"
    assert body["counts"] == {
        "filing_rows": 2,
        "holding_rows": 3,
        "manager_relationship_rows": 1,
        "source_receipts": 2,
    }
    assert all(item["sha256"] and item["byte_length"] for item in body["artifacts"])

    changed = _prepared(coverage_state="materially-different")
    assert changed.generation_id != prepared.generation_id


def test_rolling_addition_rewrites_only_one_of_sixty_four_holding_buckets() -> None:
    prior = _prepared()
    accession = "0001649339-26-000789"
    receipt = _receipt("rolling-new-filer")
    filings = [dict(item) for item in prior.filings]
    filings.append(_filing(accession, "1649339", receipt, "2026-08-07T17:45:00Z"))
    holdings = [dict(item) for item in prior.holdings]
    holdings.append(_holding(accession, 1, "02079K305"))
    updated = prepare_catalog_generation(
        report_period=PERIOD,
        source_cutoff_at="2026-08-07T18:00:00Z",
        published_at="2026-08-07T20:00:00Z",
        producer_version="catalog-v1",
        filings=filings,
        holdings=holdings,
        manager_relationships=[dict(item) for item in prior.manager_relationships],
        source_receipt_ids=[*(row["source_receipt_id"] for row in filings[:-1]), receipt],
        coverage={"state": "rolling", "discovered_filings": 3, "complete": False},
    )

    before = {item.role: item.sha256 for item in prior.manifest.artifacts}
    after = {item.role: item.sha256 for item in updated.manifest.artifacts}
    changed_buckets = [
        role for role in HOLDING_BUCKET_ROLES if before[role] != after[role]
    ]
    assert changed_buckets == [holding_bucket_role(accession)]
    assert len([role for role in HOLDING_BUCKET_ROLES if before[role] == after[role]]) == 63
