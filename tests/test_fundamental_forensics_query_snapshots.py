"""Contract tests for private, replayable Fundamental Forensics snapshots."""
from __future__ import annotations

import io
from copy import deepcopy
from collections.abc import Mapping
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Thread

import pytest

import engine.fundamental_forensics.query_snapshots as snapshots
from engine.fundamental_forensics.metric_registry import load_core_metric_registry
from engine.fundamental_forensics.query import (
    BitemporalMetricQueryEngine,
    FilingMetadata,
    PeriodRequest,
    QueryPolicy,
)
from engine.fundamental_forensics.query_snapshots import (
    QUERY_SNAPSHOT_PREFIX,
    QUERY_SNAPSHOT_PUBLICATION_CONTRACT,
    QuerySnapshotError,
    QuerySnapshotPointer,
    load_query_snapshot,
    prepare_query_snapshot,
    publish_query_snapshot,
    replay_query_snapshot,
    verify_query_snapshot,
)
from engine.fundamental_forensics.raw_ledger import (
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    SourceIdentity,
    make_raw_fact,
)
from engine.research_vault.r2_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
ENTITY = "0000000001"
PERIOD = PeriodRequest.duration("2025-01-01", "2025-12-31", label="FY2025")
POLICY = QueryPolicy(
    source_snapshot_at="2026-08-05T00:00:00Z",
    recorded_at="2026-08-05T00:00:00Z",
)


def _digest(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()


def _fact(
    *,
    value: str,
    accession: str,
    document_id: str,
    accepted_at: str,
    recorded_at: str,
    event_type: FactEventType = FactEventType.FILED,
    revision_of: str | None = None,
    dimensions_known: bool = True,
):
    return make_raw_fact(
        source=SourceIdentity(
            source="sec-edgar",
            entity_id=ENTITY,
            accession=accession,
            document_id=document_id,
            body_sha256=_digest(f"{accession}:{document_id}"),
            source_url=f"https://www.sec.gov/Archives/{accession}",
        ),
        concept_qname="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        context=FactContext(
            context_id=f"ctx-{accession}",
            entity_scheme="http://www.sec.gov/CIK",
            entity_identifier=ENTITY,
            start="2025-01-01",
            end="2025-12-31",
        ),
        unit=FactUnit("USD", ["iso4217:USD"]),
        raw_token=value,
        parsed_value=value,
        dimensions_known=dimensions_known,
        accepted_at=accepted_at,
        recorded_at=recorded_at,
        event_type=event_type,
        revision_of=revision_of,
        source_span=(0, len(value)),
    )


def _metadata(*facts) -> dict[str, FilingMetadata]:
    return {
        fact.occurrence_id: FilingMetadata(
            accession=fact.source.accession,
            document_id=fact.source.document_id,
            source_body_sha256=fact.source.body_sha256,
            available_at=fact.recorded_at,
            form="10-K",
        )
        for fact in facts
    }


def _material():
    original = _fact(
        value="100",
        accession="0000000001-26-000001",
        document_id="fixture-10k.htm",
        accepted_at="2026-08-02T01:00:00Z",
        recorded_at="2026-08-02T02:00:00Z",
    )
    restated = _fact(
        value="110",
        accession="0000000001-26-000002",
        document_id="fixture-10ka.htm",
        accepted_at="2026-08-03T01:00:00Z",
        recorded_at="2026-08-04T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=original.occurrence_id,
    )
    ledger = RawFactLedger((original, restated))
    metadata = _metadata(original, restated)
    matrix = BitemporalMetricQueryEngine(
        ledger,
        load_core_metric_registry(ROOT),
        entities={"AAA": ENTITY},
        filing_metadata=metadata,
    ).query_matrix(tickers=["AAA"], metrics=["revenue"], periods=[PERIOD], policy=POLICY)
    return ledger, metadata, matrix


def _prepared(*, published_at: str = "2026-08-06T01:00:00Z"):
    ledger, metadata, matrix = _material()
    return prepare_query_snapshot(
        matrix=matrix,
        ledger=ledger,
        filing_metadata=metadata,
        computed_at="2026-08-06T00:00:00Z",
        published_at=published_at,
    )


def test_snapshot_round_trip_is_deterministic_and_replays_from_frozen_inputs(tmp_path: Path) -> None:
    prepared = _prepared()
    duplicate = _prepared()
    assert duplicate.snapshot_id == prepared.snapshot_id
    assert duplicate.manifest == prepared.manifest
    assert duplicate.payloads == prepared.payloads
    assert prepared.snapshot_id.startswith("ffqs_")
    assert tuple(item.role for item in prepared.artifacts) == (
        "matrix_json",
        "ledger_json",
        "filing_metadata_json",
        "cells_parquet",
    )
    assert prepared.manifest["input_scope"] == {
        "ledger_scope": "committed_ledger_only",
        "sec_source_completeness_attested": False,
        "publication_contract": QUERY_SNAPSHOT_PUBLICATION_CONTRACT,
    }
    assert prepared.manifest["query_binding"] == {
        "selection": "latest_known_as_of",
        "entities": [{"ticker": "AAA", "entity_id": ENTITY}],
    }
    assert all(item.object_key.startswith(f"{QUERY_SNAPSHOT_PREFIX}/objects/sha256/") for item in prepared.artifacts)

    store = LocalStore(tmp_path / "private")
    published = publish_query_snapshot(store, prepared)
    by_id = load_query_snapshot(store, snapshot_id=published.snapshot_id)
    latest = verify_query_snapshot(store)

    assert by_id.matrix.to_json_bytes() == prepared.matrix.to_json_bytes()
    assert latest.snapshot_id == prepared.snapshot_id
    assert len(latest.ledger.events) == 2  # complete ledger, not just the selected restatement.
    assert len(latest.filing_metadata) == 2
    assert latest.cells[0]["value"] == "110"
    assert replay_query_snapshot(latest).to_json_bytes() == prepared.matrix.to_json_bytes()
    pointer = QuerySnapshotPointer.from_snapshot(latest)
    assert QuerySnapshotPointer.from_dict(pointer.to_dict()) == pointer
    # Retrying the exact immutable operation is idempotent; it must not be
    # mistaken for an attempted stale latest-pointer rewind.
    assert publish_query_snapshot(store, prepared).snapshot_id == prepared.snapshot_id


def test_snapshot_rejects_semantically_unreplayable_ledger_before_any_write(tmp_path: Path) -> None:
    _, _, matrix = _material()
    unrelated = _fact(
        value="999",
        accession="0000000001-26-000003",
        document_id="unrelated.htm",
        accepted_at="2026-08-02T01:00:00Z",
        recorded_at="2026-08-02T02:00:00Z",
    )
    wrong_ledger = RawFactLedger((unrelated,))
    wrong_metadata = _metadata(unrelated)

    with pytest.raises(QuerySnapshotError, match="replay does not match"):
        prepare_query_snapshot(
            matrix=matrix,
            ledger=wrong_ledger,
            filing_metadata=wrong_metadata,
            computed_at="2026-08-06T00:00:00Z",
            published_at="2026-08-06T01:00:00Z",
        )
    assert not (tmp_path / "private").exists()


def test_latest_pointer_advances_last_and_cannot_rewind_sequentially(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "private")
    first = _prepared(published_at="2026-08-06T01:00:00Z")
    second = _prepared(published_at="2026-08-06T02:00:00Z")
    assert first.snapshot_id != second.snapshot_id

    assert publish_query_snapshot(store, first).snapshot_id == first.snapshot_id
    assert publish_query_snapshot(store, second).snapshot_id == second.snapshot_id
    with pytest.raises(QuerySnapshotError, match="stale snapshot"):
        publish_query_snapshot(store, first)
    assert load_query_snapshot(store).snapshot_id == second.snapshot_id


class _CorruptObjectReadbackStore(LocalStore):
    """A Store adapter that acknowledges one immutable write then lies on readback."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._corrupt_key: str | None = None

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        result = super().put_bytes(key, data, content_type)
        if result and "/objects/" in key and self._corrupt_key is None:
            self._corrupt_key = key
        return result

    def get_bytes_strict(self, key: str) -> bytes | None:
        value = super().get_bytes_strict(key)
        if key == self._corrupt_key and value is not None:
            return value + b"tampered"
        return value


def test_failed_immutable_readback_never_creates_latest_pointer(tmp_path: Path) -> None:
    store = _CorruptObjectReadbackStore(tmp_path / "private")
    with pytest.raises(QuerySnapshotError, match="read-back mismatch"):
        publish_query_snapshot(store, _prepared())
    assert store.get_bytes(f"{QUERY_SNAPSHOT_PREFIX}/latest.json") is None


@pytest.mark.parametrize("role", ("matrix_json", "ledger_json", "filing_metadata_json", "cells_parquet"))
def test_verification_rejects_tampering_of_every_bound_sidecar(tmp_path: Path, role: str) -> None:
    store = LocalStore(tmp_path / "private")
    snapshot = publish_query_snapshot(store, _prepared())
    artifact = next(item for item in snapshot.manifest["objects"] if item["role"] == role)
    (store.root / artifact["object_key"]).write_bytes(b"tampered")

    with pytest.raises(QuerySnapshotError, match="digest or byte length mismatch"):
        verify_query_snapshot(store, snapshot_id=snapshot.snapshot_id)


def test_snapshot_rejects_bad_metadata_and_clock_ordering() -> None:
    ledger, metadata, matrix = _material()
    unknown_metadata = dict(metadata)
    unknown_metadata["not-an-occurrence"] = next(iter(metadata.values()))
    with pytest.raises(QuerySnapshotError, match="unknown occurrence_id"):
        prepare_query_snapshot(
            matrix=matrix,
            ledger=ledger,
            filing_metadata=unknown_metadata,
            computed_at="2026-08-06T00:00:00Z",
            published_at="2026-08-06T01:00:00Z",
        )
    with pytest.raises(QuerySnapshotError, match="computed_at predates"):
        prepare_query_snapshot(
            matrix=matrix,
            ledger=ledger,
            filing_metadata=metadata,
            computed_at=POLICY.recorded_at - timedelta(microseconds=1),
            published_at="2026-08-06T01:00:00Z",
        )
    with pytest.raises(QuerySnapshotError, match="published_at predates"):
        prepare_query_snapshot(
            matrix=matrix,
            ledger=ledger,
            filing_metadata=metadata,
            computed_at="2026-08-06T00:00:00Z",
            published_at="2026-08-05T23:59:59Z",
        )


def test_formula_missing_and_not_evaluable_cells_replay_byte_identically(tmp_path: Path) -> None:
    fact = _fact(
        value="100",
        accession="0000000001-26-000010",
        document_id="unknown-dimensions.htm",
        accepted_at="2026-08-02T01:00:00Z",
        recorded_at="2026-08-02T02:00:00Z",
        dimensions_known=False,
    )
    ledger = RawFactLedger((fact,))
    metadata = _metadata(fact)
    matrix = BitemporalMetricQueryEngine(
        ledger,
        load_core_metric_registry(ROOT),
        entities={"AAA": ENTITY},
        filing_metadata=metadata,
    ).query_matrix(
        tickers=["AAA"],
        metrics=["revenue", "gross_profit", "gross_margin"],
        periods=[PERIOD],
        policy=POLICY,
    )
    assert {cell.state.value for cell in matrix.cells} == {"missing", "not_evaluable"}
    assert any(cell.metric_id == "gross_margin" and cell.state.value == "not_evaluable" for cell in matrix.cells)
    prepared = prepare_query_snapshot(
        matrix=matrix,
        ledger=ledger,
        filing_metadata=metadata,
        computed_at="2026-08-06T00:00:00Z",
        published_at="2026-08-06T01:00:00Z",
    )
    store = LocalStore(tmp_path / "private")
    published = publish_query_snapshot(store, prepared)
    loaded = verify_query_snapshot(store, snapshot_id=published.snapshot_id)
    assert replay_query_snapshot(loaded).to_json_bytes() == matrix.to_json_bytes()


def test_manifest_cutoff_binding_and_pointer_canonicality_reject_tampering(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "private")
    snapshot = publish_query_snapshot(store, _prepared())

    # A syntactically valid, re-identified manifest cannot lie about the
    # source cutoff: it must bind exactly to the authoritative matrix receipt.
    forged = deepcopy(dict(snapshot.manifest))
    forged["clocks"]["source_snapshot_at"] = "2026-08-04T00:00:00.000000Z"
    body = dict(forged)
    body.pop("snapshot_id")
    forged_id = "ffqs_" + sha256(snapshots.canonical_json(body).encode("utf-8")).hexdigest()
    forged["snapshot_id"] = forged_id
    forged_key = f"{QUERY_SNAPSHOT_PREFIX}/manifests/{forged_id}.json"
    assert store.put_bytes(forged_key, snapshots.canonical_json(forged).encode("utf-8"))
    with pytest.raises(QuerySnapshotError, match="source cutoff does not match matrix"):
        load_query_snapshot(store, snapshot_id=forged_id)

    pointer_path = store.root / f"{QUERY_SNAPSHOT_PREFIX}/latest.json"
    pointer_path.write_bytes(pointer_path.read_bytes() + b" ")
    with pytest.raises(QuerySnapshotError, match="pointer is not canonical"):
        load_query_snapshot(store)


def test_parquet_projection_rejects_schema_and_duplicate_row_mutations() -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    prepared = _prepared()
    source = pq.read_table(io.BytesIO(prepared.payloads["cells_parquet"]))

    duplicate_buffer = io.BytesIO()
    pq.write_table(pa.concat_tables([source, source]), duplicate_buffer, compression="zstd")
    with pytest.raises(QuerySnapshotError, match="row count"):
        snapshots._decode_cells_parquet(duplicate_buffer.getvalue(), prepared.matrix)

    schema_buffer = io.BytesIO()
    pq.write_table(source.drop(["reason"]), schema_buffer, compression="zstd")
    with pytest.raises(QuerySnapshotError, match="schema"):
        snapshots._decode_cells_parquet(schema_buffer.getvalue(), prepared.matrix)


def test_manifest_rejects_hostile_object_key_before_object_read() -> None:
    prepared = _prepared()
    manifest = deepcopy(dict(prepared.manifest))
    manifest["objects"][0]["object_key"] = f"{QUERY_SNAPSHOT_PREFIX}/objects/../latest.json"
    with pytest.raises(QuerySnapshotError, match="unsafe"):
        snapshots._validate_manifest(manifest)


class _InfinitePointerMapping(Mapping[str, object]):
    """An attacker-controlled Mapping whose item stream never terminates."""

    def __init__(self, pointer: QuerySnapshotPointer) -> None:
        self._pairs = tuple(pointer.to_dict().items())
        self.items_seen = 0

    def __getitem__(self, key: str) -> object:
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 1

    def items(self):
        while True:
            for pair in self._pairs:
                self.items_seen += 1
                yield pair
            self.items_seen += 1
            yield ("unexpected", "value")


def test_pointer_decoder_bounds_a_hostile_infinite_mapping() -> None:
    pointer = QuerySnapshotPointer(
        snapshot_id="ffqs_" + "a" * 64,
        manifest_key=f"{QUERY_SNAPSHOT_PREFIX}/manifests/ffqs_{'a' * 64}.json",
        query_hash="b" * 64,
        published_at="2026-08-06T01:00:00Z",
    )
    hostile = _InfinitePointerMapping(pointer)
    with pytest.raises(QuerySnapshotError, match="shape is invalid"):
        QuerySnapshotPointer.from_dict(hostile)
    assert hostile.items_seen == len(pointer.to_dict()) + 1


class _PointerReadbackFailureStore(LocalStore):
    """Corrupt only the read after a newer pointer write; rollback still writes."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._pointer_writes = 0
        self.corrupt_pointer_readback = False

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        result = super().put_bytes(key, data, content_type)
        if result and key == f"{QUERY_SNAPSHOT_PREFIX}/latest.json":
            self._pointer_writes += 1
            if self._pointer_writes >= 2:
                self.corrupt_pointer_readback = True
        return result

    def get_bytes_strict(self, key: str) -> bytes | None:
        value = super().get_bytes_strict(key)
        if key == f"{QUERY_SNAPSHOT_PREFIX}/latest.json" and self.corrupt_pointer_readback:
            return b"corrupt-pointer-readback"
        return value


def test_pointer_readback_failure_restores_prior_latest(tmp_path: Path) -> None:
    store = _PointerReadbackFailureStore(tmp_path / "private")
    first = _prepared(published_at="2026-08-06T01:00:00Z")
    second = _prepared(published_at="2026-08-06T02:00:00Z")
    assert publish_query_snapshot(store, first).snapshot_id == first.snapshot_id
    with pytest.raises(QuerySnapshotError, match="latest pointer read-back mismatch"):
        publish_query_snapshot(store, second)
    store.corrupt_pointer_readback = False
    assert load_query_snapshot(store).snapshot_id == first.snapshot_id


class _TransientStrictReadStore(LocalStore):
    """Raises on a targeted strict read without pretending the object is absent."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fail_key: str | None = None
        self.writes_after_failure_enabled = 0
        self.failure_enabled = False

    def get_bytes_strict(self, key: str) -> bytes | None:
        if self.failure_enabled and key == self.fail_key:
            raise OSError("simulated transient private-store read failure")
        return super().get_bytes_strict(key)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        if self.failure_enabled:
            self.writes_after_failure_enabled += 1
        return super().put_bytes(key, data, content_type)


def test_transient_strict_read_failure_never_advances_latest_or_writes(tmp_path: Path) -> None:
    store = _TransientStrictReadStore(tmp_path / "private")
    first = _prepared(published_at="2026-08-06T01:00:00Z")
    second = _prepared(published_at="2026-08-06T02:00:00Z")
    assert publish_query_snapshot(store, first).snapshot_id == first.snapshot_id
    store.fail_key = second.artifacts[0].object_key
    store.failure_enabled = True
    with pytest.raises(QuerySnapshotError, match="private snapshot read failed"):
        publish_query_snapshot(store, second)
    assert store.writes_after_failure_enabled == 0
    store.failure_enabled = False
    assert load_query_snapshot(store).snapshot_id == first.snapshot_id


def test_process_local_publish_lock_keeps_newest_concurrent_pointer(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "private")
    older = _prepared(published_at="2026-08-06T01:00:00Z")
    newer = _prepared(published_at="2026-08-06T02:00:00Z")
    barrier = Barrier(2)
    outcomes: dict[str, str] = {}

    def worker(label: str, prepared) -> None:
        barrier.wait()
        try:
            outcomes[label] = publish_query_snapshot(store, prepared).snapshot_id
        except QuerySnapshotError as exc:
            outcomes[label] = str(exc)

    threads = (
        Thread(target=worker, args=("older", older)),
        Thread(target=worker, args=("newer", newer)),
    )
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert outcomes["newer"] == newer.snapshot_id
    assert outcomes["older"] in {older.snapshot_id, "stale snapshot cannot rewind latest pointer"}
    assert load_query_snapshot(store).snapshot_id == newer.snapshot_id


def test_later_live_fact_cannot_rewrite_a_prior_snapshot(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "private")
    published = publish_query_snapshot(store, _prepared())
    old = verify_query_snapshot(store, snapshot_id=published.snapshot_id)
    ledger, _, _ = _material()
    future = _fact(
        value="125",
        accession="0000000001-26-000004",
        document_id="future-restatement.htm",
        accepted_at="2026-08-07T01:00:00Z",
        recorded_at="2026-08-07T02:00:00Z",
        event_type=FactEventType.RESTATEMENT,
        revision_of=ledger.events[-1].occurrence_id,
    )
    current_ledger = RawFactLedger((*ledger.events, future))
    current_policy = QueryPolicy(
        source_snapshot_at="2026-08-08T00:00:00Z",
        recorded_at="2026-08-08T00:00:00Z",
    )
    current = BitemporalMetricQueryEngine(
        current_ledger,
        load_core_metric_registry(ROOT),
        entities={"AAA": ENTITY},
        filing_metadata=_metadata(*current_ledger.events),
    ).query_matrix(tickers=["AAA"], metrics=["revenue"], periods=[PERIOD], policy=current_policy)

    assert current.cells[0].value == 125
    assert old.matrix.cells[0].value == 110
    assert replay_query_snapshot(old).to_json_bytes() == old.matrix.to_json_bytes()
