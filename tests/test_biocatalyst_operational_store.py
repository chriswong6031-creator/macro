"""Bounded, hermetic tests for the inert BC-O1a operational store.

Every test runs under ``tmp_path``: the state root is injectable and is never
created implicitly, so nothing here touches a production path, a route, a
source, or a pointer.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from engine.biocatalyst import operational_store as store_module
from engine.biocatalyst.operational_store import (
    CORRIGIBLE_RECORD_KINDS,
    IMMUTABLE_RECORD_KINDS,
    MAX_QUERY_LIMIT,
    O1A_RECORD_KINDS,
    O1B_RECORD_KINDS,
    OPERATIONAL_RECORD_CONTRACT_ID,
    RECORD_KINDS,
    RESERVED_RECORD_KIND_ALIASES,
    STORE_META_FILENAME,
    STORE_SCHEMA_VERSION,
    OperationalStore,
    OperationalStoreConflictError,
    OperationalStoreCorruptionError,
    OperationalStoreError,
    OperationalStoreSchemaVersionError,
    OperationalStoreUnavailableError,
    build_operational_record,
    cursor_for,
    operational_record_id,
    operational_record_semantic_issues,
    provision_operational_store,
    replay_sequence,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    canonical_json_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "engine" / "biocatalyst" / "operational_store.py"


def _run_receipt_payload(run_id: str = "ctgov_run_a") -> dict:
    return {
        "source_id": "clinicaltrials_gov_v2",
        "run_id": run_id,
        "started_at": "2026-08-06T10:00:00Z",
        "finished_at": "2026-08-06T10:05:00Z",
        "run_state": "complete",
        "evidence_sha256": "a" * 64,
    }


def _queue_payload(review_state: str = "open") -> dict:
    return {
        "queue_item_id": "idq_1",
        "subject_ref": "internal:program_alpha",
        "review_state": review_state,
        "blocker": "reviewed_point_in_time_company_identity_contract",
    }


def _object_path(root: Path, record_kind: str, record_id: str) -> Path:
    return root / "objects" / record_kind / record_id[5:7] / f"{record_id}.json"


@pytest.fixture()
def store(tmp_path: Path) -> OperationalStore:
    root = tmp_path / "operational"
    provision_operational_store(root)
    return OperationalStore(root)


# ---- contract registration ------------------------------------------------


def test_operational_record_contract_is_registered() -> None:
    registry = ContractRegistry(ROOT)
    assert OPERATIONAL_RECORD_CONTRACT_ID in registry.contract_ids


def test_record_kinds_are_the_o1a_and_o1b_kinds_and_no_alias() -> None:
    # O1b added record kinds to this store; it did not fork a second one.
    assert RECORD_KINDS == O1A_RECORD_KINDS + O1B_RECORD_KINDS
    assert len(O1A_RECORD_KINDS) == 7
    assert len(RECORD_KINDS) == 14
    assert len(set(RECORD_KINDS)) == len(RECORD_KINDS)
    # A near-miss spelling is never quietly accepted as a new kind.
    assert set(RECORD_KINDS).isdisjoint(RESERVED_RECORD_KIND_ALIASES)
    assert IMMUTABLE_RECORD_KINDS | CORRIGIBLE_RECORD_KINDS == set(RECORD_KINDS)
    assert not IMMUTABLE_RECORD_KINDS & CORRIGIBLE_RECORD_KINDS


# ---- the explicit UNAVAILABLE state ---------------------------------------


def test_missing_state_root_fails_closed_and_is_not_created(tmp_path: Path) -> None:
    root = tmp_path / "never_provisioned"
    unprovisioned = OperationalStore(root)
    with pytest.raises(OperationalStoreUnavailableError) as read_error:
        unprovisioned.read("source_run_receipt", limit=5)
    assert read_error.value.code == "OPERATIONAL_STATE_ROOT_MISSING"
    with pytest.raises(OperationalStoreUnavailableError):
        unprovisioned.append(
            "source_run_receipt", _run_receipt_payload(), idempotency_key="run:a"
        )
    assert not root.exists()


def test_unprovisioned_directory_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "bare_directory"
    root.mkdir()
    with pytest.raises(OperationalStoreUnavailableError) as error:
        OperationalStore(root).read("soak_receipt", limit=1)
    assert error.value.code == "OPERATIONAL_STATE_ROOT_NOT_PROVISIONED"


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root bypasses mode bits"
)
def test_unwritable_state_root_fails_closed_on_write(store: OperationalStore) -> None:
    root = store.state_root
    os.chmod(root, 0o500)
    try:
        with pytest.raises(OperationalStoreUnavailableError) as error:
            store.append(
                "source_run_receipt", _run_receipt_payload(), idempotency_key="run:a"
            )
        assert error.value.code == "OPERATIONAL_STATE_ROOT_UNWRITABLE"
        # A read-only root still reads: unavailability is per-operation.
        assert store.read("source_run_receipt", limit=1).records == ()
    finally:
        os.chmod(root, 0o700)


# ---- versioned schemas and migration detection ----------------------------


def test_store_schema_version_drift_is_reported(store: OperationalStore) -> None:
    meta_path = store.state_root / STORE_META_FILENAME
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["store_schema_version"] == STORE_SCHEMA_VERSION
    meta["store_schema_version"] = STORE_SCHEMA_VERSION + 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(OperationalStoreSchemaVersionError) as error:
        store.read("source_run_receipt", limit=1)
    assert error.value.code == "STORE_SCHEMA_VERSION_DRIFT"


def test_future_record_schema_version_is_reported_not_misread(
    store: OperationalStore,
) -> None:
    document = build_operational_record(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    future = {key: value for key, value in document.items() if key != "record_id"}
    future["record_schema_version"] = "2.0.0"
    future["record_id"] = operational_record_id(future)
    path = _object_path(store.state_root, "source_run_receipt", future["record_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(future))
    with pytest.raises(OperationalStoreSchemaVersionError) as error:
        store.get("source_run_receipt", future["record_id"])
    assert error.value.code == "RECORD_SCHEMA_VERSION_UNSUPPORTED"


# ---- idempotency ----------------------------------------------------------


def test_same_logical_record_twice_is_a_no_op_with_the_same_id(
    store: OperationalStore,
) -> None:
    first = store.append(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    second = store.append(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    assert first.record_id == second.record_id
    assert first.created is True and second.created is False
    assert len(store.read("source_run_receipt", limit=MAX_QUERY_LIMIT).records) == 1


def test_different_bytes_under_the_same_idempotency_key_fail_closed(
    store: OperationalStore,
) -> None:
    store.append(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    with pytest.raises(OperationalStoreConflictError) as error:
        store.append(
            "source_run_receipt",
            _run_receipt_payload(run_id="ctgov_run_b"),
            idempotency_key="run:a",
            recorded_at="2026-08-06T10:05:00.000000Z",
        )
    assert error.value.code == "OPERATIONAL_IDEMPOTENCY_KEY_CONFLICT"
    assert len(store.read("source_run_receipt", limit=MAX_QUERY_LIMIT).records) == 1


def test_content_address_collision_with_other_bytes_fails_closed(
    store: OperationalStore,
) -> None:
    receipt = store.append(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    path = _object_path(store.state_root, "source_run_receipt", receipt.record_id)
    path.write_bytes(b'{"tampered":true}')
    with pytest.raises(OperationalStoreConflictError) as error:
        store.append(
            "source_run_receipt",
            _run_receipt_payload(),
            idempotency_key="run:a",
            recorded_at="2026-08-06T10:05:00.000000Z",
        )
    assert error.value.code == "IMMUTABLE_OBJECT_COLLISION"


# ---- append-only, no second write path ------------------------------------


def test_store_exposes_no_delete_or_update_api() -> None:
    public = {name for name in dir(OperationalStore) if not name.startswith("_")}
    assert public == {"append", "get", "read", "rebuild_index", "replay_digest", "state_root"}
    banned = ("delete", "remove", "update", "overwrite", "purge", "truncate", "drop")
    module_public = [name for name in dir(store_module) if not name.startswith("_")]
    assert not [
        name for name in module_public if any(word in name.lower() for word in banned)
    ]


def _qualified_functions(tree: ast.AST) -> dict[str, ast.AST]:
    functions: dict[str, ast.AST] = {}
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions[f"{node.name}.{child.name}"] = child
    return functions


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                names.add(f"{func.value.id}.{func.attr}")
            names.add(func.attr)
    return names


def _callers_of(functions: dict[str, ast.AST], target: str) -> set[str]:
    return {name for name, node in functions.items() if target in _call_names(node)}


def test_exactly_one_write_path_exists_in_the_module() -> None:
    functions = _qualified_functions(ast.parse(MODULE_PATH.read_text(encoding="utf-8")))

    # One primitive performs the rename; nothing else opens a file for writing.
    assert _callers_of(functions, "os.replace") == {"_atomic_write"}
    assert _callers_of(functions, "os.fdopen") == {"_atomic_write"}
    assert _callers_of(functions, "os.unlink") == {"_atomic_write"}
    assert _callers_of(functions, "write_bytes") == set()
    assert _callers_of(functions, "write_text") == set()

    # Only three callers durably write, and only one of them writes a record.
    assert _callers_of(functions, "_atomic_write") == {
        "OperationalStore._put_record_object",
        "OperationalStore._put_pointer",
        "provision_operational_store",
    }
    assert _callers_of(functions, "_put_record_object") == {"OperationalStore.append"}
    assert _callers_of(functions, "_put_pointer") == {
        "OperationalStore.append",
        "OperationalStore.rebuild_index",
    }
    # Index recovery re-derives pointers; it can never mint a record.
    assert "_put_record_object" not in _call_names(functions["OperationalStore.rebuild_index"])


# ---- correction-linked semantics ------------------------------------------


def test_correction_is_a_new_record_and_never_mutates_the_original(
    store: OperationalStore,
) -> None:
    original = store.append(
        "identity_review_queue_item",
        _queue_payload(),
        idempotency_key="idq:1",
        recorded_at="2026-08-06T10:00:00.000000Z",
    )
    path = _object_path(store.state_root, "identity_review_queue_item", original.record_id)
    before = path.read_bytes()
    correction = store.append(
        "identity_review_queue_item",
        _queue_payload(review_state="closed"),
        idempotency_key="idq:1:r2",
        corrects_record_id=original.record_id,
        recorded_at="2026-08-06T11:00:00.000000Z",
    )
    assert correction.record_id != original.record_id
    assert path.read_bytes() == before
    assert sha256(path.read_bytes()).hexdigest() == sha256(before).hexdigest()
    corrected = store.get("identity_review_queue_item", correction.record_id)
    assert corrected["corrects_record_id"] == original.record_id
    assert store.get("identity_review_queue_item", original.record_id)["payload"][
        "review_state"
    ] == "open"
    assert len(store.read("identity_review_queue_item", limit=MAX_QUERY_LIMIT).records) == 2


@pytest.mark.parametrize("record_kind", sorted(IMMUTABLE_RECORD_KINDS))
def test_correcting_an_append_only_kind_fails_closed(
    store: OperationalStore, record_kind: str
) -> None:
    anchor = store.append(
        "identity_review_queue_item",
        _queue_payload(),
        idempotency_key="idq:1",
        recorded_at="2026-08-06T10:00:00.000000Z",
    )
    with pytest.raises(OperationalStoreError) as error:
        store.append(
            record_kind,
            {"unused": True},
            idempotency_key="bad:1",
            corrects_record_id=anchor.record_id,
        )
    assert error.value.code == "OPERATIONAL_RECORD_KIND_NOT_CORRIGIBLE"


def test_correction_predecessor_must_already_exist(store: OperationalStore) -> None:
    with pytest.raises(OperationalStoreError) as error:
        store.append(
            "identity_review_queue_item",
            _queue_payload(),
            idempotency_key="idq:1",
            corrects_record_id="bcop_" + "0" * 32,
        )
    assert error.value.code == "OPERATIONAL_CORRECTION_PREDECESSOR_MISSING"


def test_correction_lineage_binds_predecessor_to_successor(
    store: OperationalStore,
) -> None:
    original = store.append(
        "identity_review_queue_item",
        _queue_payload(),
        idempotency_key="idq:1",
        recorded_at="2026-08-06T10:00:00.000000Z",
    )
    correction = store.append(
        "identity_review_queue_item",
        _queue_payload(review_state="closed"),
        idempotency_key="idq:1:r2",
        corrects_record_id=original.record_id,
        recorded_at="2026-08-06T11:00:00.000000Z",
    )
    lineage = store.append(
        "correction_lineage",
        {
            "superseded_record_id": original.record_id,
            "superseding_record_id": correction.record_id,
            "correction_reason": "operator_correction",
        },
        idempotency_key="lineage:1",
        recorded_at="2026-08-06T11:00:01.000000Z",
    )
    document = store.get("correction_lineage", lineage.record_id)
    assert document["payload"]["superseded_record_id"] == original.record_id
    assert document["payload"]["superseding_record_id"] == correction.record_id
    assert document["corrects_record_id"] is None


# ---- bounded query --------------------------------------------------------


def test_read_requires_an_explicit_bounded_limit(store: OperationalStore) -> None:
    with pytest.raises(TypeError):
        store.read("source_run_receipt")  # type: ignore[call-arg]
    for bad_limit in (0, -1, MAX_QUERY_LIMIT + 1, True, 1.0, "5"):
        with pytest.raises(OperationalStoreError) as error:
            store.read("source_run_receipt", limit=bad_limit)  # type: ignore[arg-type]
        assert error.value.code == "OPERATIONAL_QUERY_LIMIT_INVALID"


def test_read_paginates_deterministically_by_cursor(store: OperationalStore) -> None:
    ids = []
    for index in range(5):
        ids.append(
            store.append(
                "source_run_receipt",
                _run_receipt_payload(run_id=f"ctgov_run_{index}"),
                idempotency_key=f"run:{index}",
                recorded_at=f"2026-08-06T10:0{index}:00.000000Z",
            ).record_id
        )
    seen: list[str] = []
    cursor = None
    while True:
        page = store.read("source_run_receipt", limit=2, cursor=cursor)
        seen.extend(document["record_id"] for document in page.records)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == ids
    with pytest.raises(OperationalStoreError) as error:
        store.read("source_run_receipt", limit=2, cursor="not-a-cursor")
    assert error.value.code == "OPERATIONAL_QUERY_CURSOR_INVALID"


# ---- restore, replay, crash safety ----------------------------------------


def test_store_rebuilt_from_its_own_objects_yields_identical_reads(
    store: OperationalStore, tmp_path: Path
) -> None:
    for index in range(3):
        store.append(
            "soak_receipt",
            {
                "soak_id": f"soak_{index}",
                "window_start": "2026-08-01T00:00:00Z",
                "window_end": "2026-08-06T00:00:00Z",
                "observed_state": "within_slo",
                "evidence_sha256": f"{index}" * 64,
            },
            idempotency_key=f"soak:{index}",
            recorded_at=f"2026-08-06T10:0{index}:00.000000Z",
        )
    before = store.read("soak_receipt", limit=MAX_QUERY_LIMIT)

    index_root = store.state_root / "index"
    keys_root = store.state_root / "keys"
    for path in list(index_root.rglob("*.json")) + list(keys_root.rglob("*.json")):
        path.unlink()
    assert store.read("soak_receipt", limit=MAX_QUERY_LIMIT).records == ()

    report = OperationalStore(store.state_root).rebuild_index()
    assert report.object_count == 3
    assert report.index_entries_written == 3
    assert report.key_pointers_written == 3
    assert OperationalStore(store.state_root).read(
        "soak_receipt", limit=MAX_QUERY_LIMIT
    ) == before


def test_replay_of_an_append_sequence_is_deterministic(tmp_path: Path) -> None:
    sequence = [
        {
            "record_kind": "source_run_receipt",
            "payload": _run_receipt_payload(run_id=f"ctgov_run_{index}"),
            "idempotency_key": f"run:{index}",
            "recorded_at": f"2026-08-06T10:0{index}:00.000000Z",
        }
        for index in range(4)
    ]
    digests = []
    id_sequences = []
    for name in ("first", "second"):
        root = tmp_path / name
        provision_operational_store(root)
        replay_store = OperationalStore(root)
        id_sequences.append(replay_sequence(replay_store, sequence))
        digests.append(replay_store.replay_digest("source_run_receipt", limit=MAX_QUERY_LIMIT))
    assert id_sequences[0] == id_sequences[1]
    assert digests[0] == digests[1]
    assert len(set(id_sequences[0])) == 4


def test_interrupted_write_leaves_no_partially_visible_record(
    store: OperationalStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_replace = os.replace

    def crash_between_temp_write_and_rename(source, destination):  # type: ignore[no-untyped-def]
        if f"{os.sep}objects{os.sep}" in str(destination):
            raise OSError("simulated crash before rename")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", crash_between_temp_write_and_rename)
    with pytest.raises(OSError):
        store.append(
            "source_run_receipt",
            _run_receipt_payload(),
            idempotency_key="run:a",
            recorded_at="2026-08-06T10:05:00.000000Z",
        )
    monkeypatch.undo()

    leftovers = [path for path in (store.state_root / "objects").rglob("*") if path.is_file()]
    assert leftovers == []
    assert store.read("source_run_receipt", limit=MAX_QUERY_LIMIT).records == ()
    assert list((store.state_root / "index").rglob("*.json")) == []
    assert list((store.state_root / "keys").rglob("*.json")) == []


def test_object_that_does_not_match_its_content_address_is_detected(
    store: OperationalStore,
) -> None:
    receipt = store.append(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    path = _object_path(store.state_root, "source_run_receipt", receipt.record_id)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["run_state"] = "failed"
    path.write_bytes(canonical_json_bytes(document))
    with pytest.raises(OperationalStoreCorruptionError) as error:
        store.get("source_run_receipt", receipt.record_id)
    assert error.value.code == "RECORD_OBJECT_CORRUPT"


# ---- authority fences -----------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_key",
    ["score", "peer_rank", "issuer_id", "ticker", "probability", "position_size", "model_id"],
)
def test_payload_may_not_carry_scoring_or_security_identity_keys(
    store: OperationalStore, forbidden_key: str
) -> None:
    payload = dict(_queue_payload())
    payload[forbidden_key] = "x"
    with pytest.raises(ContractValidationError) as error:
        store.append("identity_review_queue_item", payload, idempotency_key="idq:1")
    assert "operational_record.authority_fence" in str(
        error.value
    ) or "schema" in str(error.value)
    assert store.read("identity_review_queue_item", limit=MAX_QUERY_LIMIT).records == ()


@pytest.mark.parametrize("record_kind", sorted(RESERVED_RECORD_KIND_ALIASES))
def test_reserved_record_kind_aliases_are_refused(
    store: OperationalStore, record_kind: str
) -> None:
    # "forecast" and "prediction" are near-misses for forecast_snapshot; a
    # second spelling would be a second home for the same evidence.
    with pytest.raises(OperationalStoreError) as error:
        store.append(record_kind, {"any": 1}, idempotency_key="x:1")
    assert error.value.code == "OPERATIONAL_RECORD_KIND_RESERVED_ALIAS"


def test_subject_refs_are_internal_and_never_a_security_join(
    store: OperationalStore,
) -> None:
    payload = dict(_queue_payload())
    payload["subject_ref"] = "ticker:MRNA"
    with pytest.raises(ContractValidationError):
        store.append("identity_review_queue_item", payload, idempotency_key="idq:1")
    payload["subject_ref"] = "nct:NCT01234567"
    receipt = store.append("identity_review_queue_item", payload, idempotency_key="idq:2")
    assert receipt.created is True


# ---- record-level semantics ----------------------------------------------


def test_semantic_issues_flag_a_rebound_record_id() -> None:
    document = build_operational_record(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    assert operational_record_semantic_issues(document) == []
    tampered = dict(document)
    tampered["record_id"] = "bcop_" + "0" * 32
    codes = {issue.code for issue in operational_record_semantic_issues(tampered)}
    assert "operational_record.identity" in codes


def test_soak_window_must_not_run_backwards(store: OperationalStore) -> None:
    with pytest.raises(ContractValidationError) as error:
        store.append(
            "soak_receipt",
            {
                "soak_id": "soak_0",
                "window_start": "2026-08-06T00:00:00Z",
                "window_end": "2026-08-01T00:00:00Z",
                "observed_state": "within_slo",
                "evidence_sha256": "0" * 64,
            },
            idempotency_key="soak:0",
        )
    assert "operational_record.interval" in str(error.value)


def test_cursor_is_chronological_with_a_content_addressed_tiebreak() -> None:
    document = build_operational_record(
        "source_run_receipt",
        _run_receipt_payload(),
        idempotency_key="run:a",
        recorded_at="2026-08-06T10:05:00.000000Z",
    )
    assert cursor_for(document) == f"20260806T100500000000Z__{document['record_id']}"


def test_get_fails_closed_for_an_unknown_record(store: OperationalStore) -> None:
    with pytest.raises(OperationalStoreError) as missing:
        store.get("source_run_receipt", "bcop_" + "0" * 32)
    assert missing.value.code == "OPERATIONAL_RECORD_NOT_FOUND"
    with pytest.raises(OperationalStoreError) as unknown_kind:
        store.get("forecast", "bcop_" + "0" * 32)
    assert unknown_kind.value.code == "OPERATIONAL_RECORD_KIND_UNKNOWN"
