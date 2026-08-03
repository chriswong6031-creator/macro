"""Focused security tests for authenticated share-count materialization publication."""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
from io import BytesIO
import os
from pathlib import Path
import time

import fcntl

import pytest

from engine.capital_structure import share_count_publication as publication


def _binding(*, suffix: str = "a") -> dict:
    return {
        "schema": "capital_structure.share_count_materialization_input_binding/v1",
        "ledger_head_receipt_id": "share-count-ledger-receipt-v2:cs:" + suffix * 24,
        "ledger_sequence": 1,
        "compiler_version": "capital-structure-share-count-materializer/2.1.0",
        "materialized_at": "2026-08-03T00:00:00Z",
        "prefixes": {
            "observations": {"count": 0, "rolling_sha256": suffix * 64},
            "source_snapshots": {"count": 1, "rolling_sha256": suffix * 64},
            "bridges": {"count": 1, "rolling_sha256": suffix * 64},
            "source_manifests": {"count": 1, "rolling_sha256": suffix * 64},
        },
    }


def _publisher(tmp_path: Path):
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    return signer, publication.InMemoryShareCountHeadGuard(signer), tmp_path / "workspace"


def _publish(root: Path, signer, guard, ledger: bytes = b"{}\n", *, suffix: str = "a", **kwargs):
    return publication._publish_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard, canonical_ledger_bytes=ledger,
        input_binding=_binding(suffix=suffix), validate_ledger=False,
        now=datetime(2026, 8, 3, tzinfo=timezone.utc), **kwargs,
    )


class _CountingGuard(publication.InMemoryShareCountHeadGuard):
    def __init__(self, signer) -> None:
        super().__init__(signer)
        self.artifact_reads = 0
        self.artifact_read_keys: list[str] = []
        self.reject_ledger_reads = False
        self.artifact_seals = 0
        self.advances = 0
        self.migrations = 0

    def read_artifact(self, *, key: str, max_bytes: int) -> bytes:
        self.artifact_reads += 1
        self.artifact_read_keys.append(key)
        if self.reject_ledger_reads and key.endswith("/ledger.json"):
            raise AssertionError("selected external ledger opened before selector proofs completed")
        return super().read_artifact(key=key, max_bytes=max_bytes)

    def reset_artifact_reads(self, *, reject_ledgers: bool = False) -> None:
        self.artifact_reads = 0
        self.artifact_read_keys.clear()
        self.reject_ledger_reads = reject_ledgers

    def seal_artifact(self, *, key: str, body: bytes, max_bytes: int) -> None:
        self.artifact_seals += 1
        return super().seal_artifact(key=key, body=body, max_bytes=max_bytes)

    def advance(self, *, expected, expected_token, candidate) -> None:
        self.advances += 1
        return super().advance(
            expected=expected,
            expected_token=expected_token,
            candidate=candidate,
        )

    def migrate_v2_to_v3(self, *, expected, expected_token, candidate) -> None:
        self.migrations += 1
        return super().migrate_v2_to_v3(
            expected=expected,
            expected_token=expected_token,
            candidate=candidate,
        )

    def reset_writes(self) -> None:
        self.artifact_seals = 0
        self.advances = 0
        self.migrations = 0


def _forbid_local_ledger_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    original_read = publication._bounded_read_at

    def ordered_read(
        directory_fd,
        name,
        *,
        max_bytes,
        label,
        operation,
        missing_ok=False,
    ):
        if name == "ledger.json":
            raise AssertionError("local ledger opened before selector proofs completed")
        return original_read(
            directory_fd,
            name,
            max_bytes=max_bytes,
            label=label,
            operation=operation,
            missing_ok=missing_ok,
        )

    monkeypatch.setattr(publication, "_bounded_read_at", ordered_read)


def _dummy_ref(sequence: int, *, salt: str) -> dict:
    digest = publication._sha(f"{salt}:{sequence}".encode())
    return {
        "sequence": sequence,
        "receipt_id": "receipt:cs-share-count-materialization-v2:" + digest,
        "receipt_sha256": digest,
        "receipt_byte_length": 1,
    }


def _synthetic_receipt(
    signer,
    sequence: int,
    *,
    ledger: bytes,
    ancestor_overrides: dict[int, dict] | None = None,
) -> tuple[dict, bytes]:
    refs = [
        _dummy_ref(sequence - (1 << level), salt=f"{sequence}:{level}")
        for level in range((sequence - 1).bit_length())
    ]
    for level, reference in (ancestor_overrides or {}).items():
        refs[level] = copy.deepcopy(reference)
    digest = publication._sha(ledger)
    unsigned = {
        "schema": publication.RECEIPT_SCHEMA,
        "receipt_id": "",
        "sequence": sequence,
        "previous_receipt": None if sequence == 1 else copy.deepcopy(refs[0]),
        "ancestor_refs": refs,
        "published_at": "2026-08-03T00:00:00Z",
        "generation": {
            "generation_id": publication._generation_id(digest),
            "ledger_sha256": digest,
            "ledger_byte_length": len(ledger),
        },
        "input_binding": _binding(),
        "output_authority": publication._output_authority(),
        "auth": {
            "scheme": publication.AUTH_SCHEME,
            "key_id": signer.key_id,
            "signature": "",
        },
    }
    receipt = publication._sign_receipt(unsigned, signer=signer)
    return receipt, publication._canonical_bytes(receipt) + b"\n"


def _receipt_ref(receipt: dict, body: bytes) -> dict:
    return publication._receipt_ref(receipt, body)


def _store_receipt(guard, receipt: dict, body: bytes) -> None:
    guard._artifacts[publication._receipt_external_key(receipt["receipt_id"])] = body


def _select_external_head(guard, signer, receipt: dict, body: bytes, ledger: bytes) -> None:
    head = publication._head_witness(
        receipt=receipt,
        receipt_body=body,
        signer=signer,
    )
    _store_receipt(guard, receipt, body)
    guard._artifacts[head["ledger_object_key"]] = ledger
    guard._witness = head
    guard._version += 1


def _sparse_proof_receipts(
    signer,
    *,
    local_receipt: dict,
    local_body: bytes,
    top_sequence: int,
    ledger: bytes,
) -> tuple[dict[int, tuple[dict, bytes]], list[int]]:
    path = [top_sequence]
    while path[-1] > local_receipt["sequence"]:
        delta = path[-1] - local_receipt["sequence"]
        path.append(path[-1] - (1 << (delta.bit_length() - 1)))
    built = {local_receipt["sequence"]: (local_receipt, local_body)}
    for index in range(len(path) - 2, -1, -1):
        sequence, lower_sequence = path[index], path[index + 1]
        lower_receipt, lower_body = built[lower_sequence]
        level = (sequence - lower_sequence).bit_length() - 1
        built[sequence] = _synthetic_receipt(
            signer,
            sequence,
            ledger=ledger,
            ancestor_overrides={level: _receipt_ref(lower_receipt, lower_body)},
        )
    return built, path


def test_hmac_domain_witness_authentication_and_exact_noop(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    head, token = guard.read()
    assert first.published is True
    assert first.ledger_bytes == b"{}\n"
    assert "input_prefix" not in first.receipt
    assert head is not None and token == "1"
    assert signer.verify(b"x", signer.sign(b"x"), key_id=signer.key_id)
    replay = _publish(root, signer, guard)
    assert replay.published is False
    assert replay.receipt_id == first.receipt_id
    assert guard.read()[1] == "1"
    guard._witness["signature"] = "0" * 64  # explicit hostile external mutation
    with pytest.raises(publication.ShareCountPublicationError, match="authentication"):
        guard.read()


def test_v3_migration_preserves_exact_selection_and_binds_scope_and_v2_bytes(
    tmp_path: Path,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    first = _publish(root, signer, guard)
    v2_head, v2_token = guard.read()
    assert v2_head is not None and v2_token == "1"
    guard.reset_artifact_reads()
    guard.reset_writes()

    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    v3_head, v3_token = guard.read()
    assert recovered is not None and recovered.receipt_id == first.receipt_id
    assert v3_head is not None and v3_head["schema"] == publication.WITNESS_V3_SCHEMA
    assert v3_token == "2"
    assert publication._head_selection(v3_head) == publication._head_selection(v2_head)
    assert v3_head["guard_scope"] == guard.guard_scope
    assert v3_head["migration"] == {
        "from_schema": publication.WITNESS_V2_SCHEMA,
        "from_witness_sha256": publication._sha(
            publication._canonical_bytes(v2_head) + b"\n",
        ),
    }
    assert guard.migrations == 1
    assert guard.advances == 0
    assert guard.artifact_seals == 0
    assert guard.artifact_reads == 0


def test_v3_head_signature_is_cross_domain_and_scope_exact(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    v3_head, _ = guard.read()
    assert v3_head is not None

    cross_domain = copy.deepcopy(v3_head)
    cross_domain["signature"] = signer.sign(publication._head_v3_payload(cross_domain))
    with pytest.raises(publication.ShareCountPublicationError, match="authentication"):
        publication._validate_head_witness_v3(
            cross_domain,
            signer=signer,
            expected_scope=guard.guard_scope,
        )

    wrong_scope = copy.deepcopy(v3_head)
    wrong_scope["guard_scope"]["account_id"] = "f" * 32
    wrong_scope["signature"] = signer.sign_head_v3(
        publication._head_v3_payload(wrong_scope),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="configured R2 authority"):
        publication._validate_head_witness_v3(
            wrong_scope,
            signer=signer,
            expected_scope=guard.guard_scope,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", "f" * 32),
        ("bucket", "different-bucket"),
        ("head_key", "capital_structure/share_counts/v2/other_head.json"),
    ],
)
def test_signed_v3_scope_mismatch_full_recovery_reads_no_artifact_or_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    source_root = tmp_path / "source"
    _publish(source_root, signer, guard)
    publication._recover_share_count_materialization_for_test(
        root=source_root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    hostile, _ = guard.read()
    assert hostile is not None
    hostile = copy.deepcopy(hostile)
    hostile["guard_scope"][field] = value
    hostile["signature"] = signer.sign_head_v3(
        publication._head_v3_payload(hostile),
    )
    guard._witness = hostile
    guard.reset_artifact_reads(reject_ledgers=True)
    guard.reset_writes()
    _forbid_local_ledger_reads(monkeypatch)

    clean_root = tmp_path / field
    with pytest.raises(publication.ShareCountPublicationError):
        publication._recover_share_count_materialization_for_test(
            root=clean_root,
            signer=signer,
            head_guard=guard,
        )
    assert guard.artifact_reads == 0
    assert guard.artifact_seals == guard.advances == guard.migrations == 0
    assert not (
        clean_root
        / "data/capital_structure/share_counts/v2"
        / publication.POINTER_NAME
    ).exists()


def test_v3_migration_flag_false_leaves_v2_head_and_token_unchanged(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    before, token = guard.read()
    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=False,
    )
    after, after_token = guard.read()
    assert recovered is not None
    assert before == after and token == after_token == "1"
    assert after is not None and after["schema"] == publication.WITNESS_V2_SCHEMA


def test_v3_clean_recovery_and_exact_noop_work_but_successor_blocks_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    source_root = tmp_path / "source"
    first = _publish(source_root, signer, guard)
    publication._recover_share_count_materialization_for_test(
        root=source_root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    clean_root = tmp_path / "clean"
    clean = publication._recover_share_count_materialization_for_test(
        root=clean_root,
        signer=signer,
        head_guard=guard,
    )
    assert clean is not None and clean.receipt_id == first.receipt_id
    noop = _publish(clean_root, signer, guard)
    assert noop.published is False and noop.receipt_id == first.receipt_id

    guard.reset_artifact_reads()
    guard.reset_writes()
    monkeypatch.setattr(
        publication,
        "_stage_ledger",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("v3 successor reached staging"),
        ),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="new publication is disabled"):
        _publish(clean_root, signer, guard, b'{"generation":2}\n', suffix="b")
    assert guard.artifact_reads == 0
    assert guard.artifact_seals == guard.advances == guard.migrations == 0


def test_v3_migration_mode_refuses_genesis_before_staging_or_remote_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    monkeypatch.setattr(
        publication,
        "_stage_ledger",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("v3 genesis reached staging"),
        ),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="cannot create a genesis"):
        _publish(
            tmp_path / "workspace",
            signer,
            guard,
            migrate_head_v3=True,
        )
    assert guard.read()[0] is None
    assert guard.artifact_reads == 0
    assert guard.artifact_seals == guard.advances == guard.migrations == 0


def test_old_v2_writer_wins_first_then_next_clean_run_migrates_latest_selection(
    tmp_path: Path,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    first_head, first_token = guard.read()
    assert first_head is not None and first_token == "1"
    second = _publish(
        tmp_path / "old-v2-writer",
        signer,
        guard,
        b'{"generation":2}\n',
        suffix="b",
    )
    second_head, _ = guard.read()
    assert second_head is not None and second.sequence == 2
    stale_candidate = publication._migrated_head_witness_v3(
        first_head,
        signer=signer,
        guard_scope=guard.guard_scope,
    )
    with pytest.raises(publication.ShareCountPublicationConflict):
        guard.migrate_v2_to_v3(
            expected=first_head,
            expected_token=first_token,
            candidate=stale_candidate,
        )

    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    migrated, _ = guard.read()
    assert recovered is not None and recovered.receipt_id == second.receipt_id
    assert migrated is not None and migrated["schema"] == publication.WITNESS_V3_SCHEMA
    assert publication._head_selection(migrated) == publication._head_selection(second_head)
    assert migrated["migration"]["from_witness_sha256"] == publication._sha(
        publication._canonical_bytes(second_head) + b"\n",
    )


def test_v3_migration_wins_then_old_v2_writer_rejects_before_head_mutation(
    tmp_path: Path,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    v2_head, v2_token = guard.read()
    assert v2_head is not None and v2_token == "1"
    publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    v3_head, v3_token = guard.read()
    assert v3_head is not None and v3_token == "2"
    with pytest.raises(publication.ShareCountPublicationError, match="shape"):
        # This is the old binary's read-before-PUT validator: v3 at the same key
        # is an unsupported schema, so it cannot reach its conditional write.
        publication._validate_head_witness(v3_head, signer=signer)

    next_receipt, next_body = _synthetic_receipt(
        signer,
        2,
        ledger=b'{"generation":2}\n',
        ancestor_overrides={
            0: {
                "sequence": first.sequence,
                "receipt_id": first.receipt_id,
                "receipt_sha256": v2_head["receipt_sha256"],
                "receipt_byte_length": v2_head["receipt_byte_length"],
            },
        },
    )
    old_candidate = publication._head_witness(
        receipt=next_receipt,
        receipt_body=next_body,
        signer=signer,
    )
    with pytest.raises(publication.ShareCountPublicationError, match="migration fence"):
        guard.advance(
            expected=v2_head,
            expected_token=v2_token,
            candidate=old_candidate,
        )
    assert guard.read() == (v3_head, v3_token)


def test_byte_identical_concurrent_v3_migration_is_success(tmp_path: Path) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")

    class ConcurrentGuard(publication.InMemoryShareCountHeadGuard):
        def migrate_v2_to_v3(self, *, expected, expected_token, candidate) -> None:
            observed, token = self.read()
            assert observed == expected and token == expected_token
            self._witness = dict(candidate)
            self._version += 1
            raise publication.ShareCountPublicationConflict("concurrent identical winner")

    guard = ConcurrentGuard(signer)
    root = tmp_path / "workspace"
    first = _publish(root, signer, guard)
    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    head, token = guard.read()
    assert recovered is not None and recovered.receipt_id == first.receipt_id
    assert head is not None and head["schema"] == publication.WITNESS_V3_SCHEMA
    assert token == "2"


def test_input_binding_is_constant_size_and_matches_exact_tail_prefixes() -> None:
    binding = _binding()
    ledger = {
        "ledger_head_receipt_id": binding["ledger_head_receipt_id"],
        "compiler_version": binding["compiler_version"],
        "materialized_at": binding["materialized_at"],
        "ledger_receipts": [{
            "sequence": binding["ledger_sequence"],
            "prefixes": copy.deepcopy(binding["prefixes"]),
        }],
    }
    assert publication._validate_input_binding(binding, ledger) == binding
    assert not any(isinstance(value, list) for value in binding.values())

    detached = copy.deepcopy(binding)
    detached["prefixes"]["source_manifests"]["rolling_sha256"] = "f" * 64
    with pytest.raises(publication.ShareCountPublicationError, match="exact ledger tail prefixes"):
        publication._validate_input_binding(detached, ledger)

    inconsistent = copy.deepcopy(binding)
    inconsistent["prefixes"]["bridges"]["count"] = 2
    with pytest.raises(publication.ShareCountPublicationError, match="counts are inconsistent"):
        publication._validate_binding_shape(inconsistent)


def test_external_clean_workspace_recovery_returns_bounded_verified_bytes(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    recovered = publication._recover_share_count_materialization_for_test(
        root=tmp_path / "clean-workspace", signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.recovered is True
    assert recovered.receipt_id == first.receipt_id
    assert recovered.ledger_bytes == first.ledger_bytes
    assert recovered.ledger_path.read_bytes() == first.ledger_bytes


def test_lagging_valid_local_pointer_converges_to_newer_external_head(tmp_path: Path) -> None:
    signer, guard, root_a = _publisher(tmp_path)
    _publish(root_a, signer, guard)
    root_b = tmp_path / "other-workspace"
    second = _publish(root_b, signer, guard, b'{"generation":2}\n', suffix="b")
    converged = publication._recover_share_count_materialization_for_test(
        root=root_a, signer=signer, head_guard=guard,
    )
    assert converged is not None and converged.recovered is True
    assert converged.receipt_id == second.receipt_id
    assert converged.ledger_bytes == b'{"generation":2}\n'


def test_replayed_signed_older_head_cannot_roll_back_authenticated_local_high_water(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    first = _publish(root, signer, guard)
    replayed_head = copy.deepcopy(guard.read()[0])
    second = _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")
    assert replayed_head is not None and second.sequence == 2

    # This is a captured, correctly signed sequence-1 body, not malformed data.
    guard._witness = replayed_head
    guard._version += 1
    guard.reset_artifact_reads(reject_ledgers=True)
    _forbid_local_ledger_reads(monkeypatch)
    with pytest.raises(publication.ShareCountPublicationError, match="local high-water"):
        publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard,
        )

    pointer = (root / "data/capital_structure/share_counts/v2/current_receipt.json").read_text()
    assert second.receipt_id in pointer
    assert first.receipt_id not in pointer
    assert guard.artifact_read_keys == []


def test_signed_external_fork_cannot_replace_authenticated_local_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    local = _publish(root, signer, guard)
    fork_guard = publication.InMemoryShareCountHeadGuard(signer)
    fork = _publish(tmp_path / "fork-writer", signer, fork_guard, b'{"fork":true}\n', suffix="b")
    assert local.sequence == fork.sequence == 1 and local.receipt_id != fork.receipt_id
    guard._witness = copy.deepcopy(fork_guard._witness)
    guard._artifacts.update(fork_guard._artifacts)
    guard._version += 1

    guard.reset_artifact_reads(reject_ledgers=True)
    _forbid_local_ledger_reads(monkeypatch)
    with pytest.raises(publication.ShareCountPublicationError, match="forks authenticated local high-water"):
        publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard,
        )
    assert guard.artifact_read_keys == []


@pytest.mark.parametrize("sequence", [513, 10_000])
def test_clean_recovery_reads_only_selected_receipt_and_ledger_at_large_sequence(
    tmp_path: Path,
    sequence: int,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    ledger = publication._canonical_bytes({"synthetic_sequence": sequence}) + b"\n"
    receipt, body = _synthetic_receipt(signer, sequence, ledger=ledger)
    _select_external_head(guard, signer, receipt, body, ledger)
    guard.reset_artifact_reads()

    recovered = publication._recover_share_count_materialization_for_test(
        root=tmp_path / f"clean-{sequence}", signer=signer, head_guard=guard,
    )

    assert recovered is not None and recovered.sequence == sequence
    assert guard.artifact_reads == 2
    head, _ = guard.read()
    assert head is not None
    assert guard.artifact_read_keys == [
        head["receipt_object_key"],
        head["ledger_object_key"],
    ]
    receipts = list(
        (tmp_path / f"clean-{sequence}/data/capital_structure/share_counts/v2/receipts").iterdir(),
    )
    assert len(receipts) == 1


def test_sequence_bound_refuses_the_next_sequence_before_seal_or_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    keys_before = set(guard._artifacts)
    monkeypatch.setattr(publication, "MAX_RECEIPT_SEQUENCE", 1)

    with pytest.raises(publication.ShareCountPublicationTooLarge, match="binary-lifting bound"):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")

    head, token = guard.read()
    assert head is not None and head["receipt_id"] == first.receipt_id and token == "1"
    assert set(guard._artifacts) == keys_before
    base = root / "data/capital_structure/share_counts/v2"
    assert not (base / publication.PENDING_NAME).exists()
    assert not (base / publication.RECOVERY_NAME).exists()


@pytest.mark.parametrize("top_sequence", [513, 10_000])
def test_surviving_local_high_water_uses_logarithmic_authenticated_skip_proof(
    tmp_path: Path,
    top_sequence: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / f"high-water-{top_sequence}"
    local = _publish(root, signer, guard)
    local_body = publication._canonical_bytes(dict(local.receipt)) + b"\n"
    ledger = publication._canonical_bytes({"synthetic_sequence": top_sequence}) + b"\n"
    built, path = _sparse_proof_receipts(
        signer,
        local_receipt=dict(local.receipt),
        local_body=local_body,
        top_sequence=top_sequence,
        ledger=ledger,
    )
    for sequence in path[:-1]:
        receipt, body = built[sequence]
        _store_receipt(guard, receipt, body)
    top_receipt, top_body = built[top_sequence]
    _select_external_head(guard, signer, top_receipt, top_body, ledger)
    guard.reset_artifact_reads()

    def reject_old_local_ledger(*args, **kwargs):
        raise AssertionError("superseded local ledger opened during external convergence")

    monkeypatch.setattr(publication, "_load_local_result", reject_old_local_ledger)

    recovered = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )

    assert recovered is not None and recovered.sequence == top_sequence
    assert guard.artifact_reads == len(path)
    assert guard.artifact_reads <= 2 + (top_sequence - 1).bit_length()
    head, _ = guard.read()
    assert head is not None
    assert guard.artifact_read_keys[-1] == head["ledger_object_key"]
    assert sum(key.endswith("/ledger.json") for key in guard.artifact_read_keys) == 1
    assert all(
        "/receipts/" in key for key in guard.artifact_read_keys[:-1]
    )


def test_binary_lifting_publication_derives_exact_authenticated_ancestors(
    tmp_path: Path,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    receipts = []
    for sequence in range(1, 10):
        result = _publish(
            root,
            signer,
            guard,
            publication._canonical_bytes({"sequence": sequence}) + b"\n",
            suffix=format(sequence, "x"),
        )
        receipts.append(result.receipt)

    for sequence, receipt in enumerate(receipts, start=1):
        expected = []
        for level in range((sequence - 1).bit_length()):
            ancestor = receipts[sequence - (1 << level) - 1]
            ancestor_body = publication._canonical_bytes(dict(ancestor)) + b"\n"
            expected.append(_receipt_ref(dict(ancestor), ancestor_body))
        assert receipt["ancestor_refs"] == expected
        assert receipt["previous_receipt"] == (None if sequence == 1 else expected[0])


@pytest.mark.parametrize("field", ["receipt_id", "receipt_sha256", "receipt_byte_length"])
def test_head_transition_requires_the_full_exact_predecessor_reference(
    tmp_path: Path,
    field: str,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    previous, _ = guard.read()
    _publish(root, signer, guard, b'{"sequence":2}\n', suffix="b")
    candidate, _ = guard.read()
    assert previous is not None and candidate is not None
    candidate = copy.deepcopy(candidate)
    if field == "receipt_byte_length":
        candidate["previous_receipt"][field] += 1
    else:
        candidate["previous_receipt"][field] = (
            "receipt:cs-share-count-materialization-v2:" + "f" * 64
            if field == "receipt_id"
            else "f" * 64
        )
    candidate["signature"] = signer.sign(publication._head_payload(candidate))

    with pytest.raises(publication.ShareCountPublicationError, match="exact-predecessor"):
        publication._validate_head_transition(
            previous=previous,
            candidate=candidate,
            signer=signer,
        )


def test_divergent_signed_skip_reference_cannot_cross_local_high_water(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    local = _publish(root, signer, guard)
    sequence = 513
    ledger = b'{"divergent":true}\n'
    receipt, body = _synthetic_receipt(signer, sequence, ledger=ledger)
    assert receipt["ancestor_refs"][-1]["sequence"] == local.sequence
    _select_external_head(guard, signer, receipt, body, ledger)

    guard.reset_artifact_reads(reject_ledgers=True)
    _forbid_local_ledger_reads(monkeypatch)
    with pytest.raises(publication.ShareCountPublicationError, match="ancestry diverges"):
        publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard,
        )
    assert guard.artifact_read_keys == [
        publication._receipt_external_key(receipt["receipt_id"]),
    ]


def test_signed_malformed_binary_lifting_table_is_rejected(tmp_path: Path) -> None:
    signer, guard, _ = _publisher(tmp_path)
    ledger = b'{"malformed":true}\n'
    receipt, _ = _synthetic_receipt(signer, 513, ledger=ledger)
    receipt["ancestor_refs"][-1]["sequence"] = 2
    receipt["receipt_id"] = publication._receipt_id(receipt)
    receipt["auth"]["signature"] = signer.sign(publication._receipt_auth_payload(receipt))
    body = publication._canonical_bytes(receipt) + b"\n"
    _select_external_head(guard, signer, receipt, body, ledger)

    with pytest.raises(publication.ShareCountPublicationError, match="ancestor level 9 reference sequence"):
        publication._recover_share_count_materialization_for_test(
            root=tmp_path / "malformed", signer=signer, head_guard=guard,
        )


def test_fault_before_cas_is_cleaned_and_after_cas_recovers(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)

    def before(stage: str) -> None:
        if stage == "before_cas":
            raise RuntimeError("simulated pre-CAS crash")

    with pytest.raises(RuntimeError, match="pre-CAS"):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b", fault=before)
    assert publication._recover_share_count_materialization_for_test(root=root, signer=signer, head_guard=guard).receipt_id == first.receipt_id

    def after(stage: str) -> None:
        if stage == "after_cas":
            raise RuntimeError("simulated post-CAS crash")

    with pytest.raises(publication.ShareCountPublishIndeterminate):
        _publish(root, signer, guard, b'{"generation":3}\n', suffix="c", fault=after)
    healed = publication._recover_share_count_materialization_for_test(root=root, signer=signer, head_guard=guard)
    assert healed is not None and healed.recovered is True
    assert healed.ledger_bytes == b'{"generation":3}\n'


def test_concurrent_head_conflict_does_not_rebind_the_selected_head(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    competitor_root = tmp_path / "competitor"

    def compete(stage: str) -> None:
        if stage == "before_cas":
            _publish(competitor_root, signer, guard, b'{"winner":true}\n', suffix="b")

    with pytest.raises(publication.ShareCountPublicationConflict):
        _publish(root, signer, guard, b'{"loser":true}\n', suffix="c", fault=compete)
    head, _ = guard.read()
    assert head is not None and head["sequence"] == 2
    assert head["generation_id"].endswith(publication._sha(b'{"winner":true}\n'))
    converged = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert converged is not None and converged.ledger_bytes == b'{"winner":true}\n'


def test_tampered_remote_artifact_and_oversized_object_fail_closed(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    head, _ = guard.read()
    guard._artifacts[head["ledger_object_key"]] = b'{"tampered":true}\n'
    with pytest.raises(publication.ShareCountPublicationError, match="ledger bytes mismatch"):
        publication._recover_share_count_materialization_for_test(
            root=tmp_path / "clean", signer=signer, head_guard=guard,
        )
    assert not (
        tmp_path
        / "clean/data/capital_structure/share_counts/v2"
        / publication.POINTER_NAME
    ).exists()
    with pytest.raises(publication.ShareCountPublicationTooLarge):
        guard.seal_artifact(
            key="capital_structure/share_counts/v2/receipts/" + "f" * 64 + ".json",
            body=b"x", max_bytes=0,
        )


@pytest.mark.parametrize(
    ("hostile_kind", "error"),
    [
        ("receipt_length", "external receipt bytes mismatch"),
        ("ledger_digest_length", "external ledger bytes mismatch"),
        ("noncanonical_ledger", "external ledger is not canonical"),
        ("artifact_path", "ledger_object_key"),
    ],
)
def test_selected_external_validation_fails_before_pointer_install(
    tmp_path: Path,
    hostile_kind: str,
    error: str,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    ledger = (
        b'{"z":1,"a":2}\n'
        if hostile_kind == "noncanonical_ledger"
        else b'{"selected":true}\n'
    )
    receipt, body = _synthetic_receipt(signer, 1, ledger=ledger)
    _select_external_head(guard, signer, receipt, body, ledger)

    assert guard._witness is not None
    if hostile_kind == "receipt_length":
        guard._witness["receipt_byte_length"] += 1
        guard._witness["signature"] = signer.sign(
            publication._head_payload(guard._witness),
        )
    elif hostile_kind == "ledger_digest_length":
        guard._artifacts[guard._witness["ledger_object_key"]] = ledger + b"x"
    elif hostile_kind == "artifact_path":
        guard._witness["ledger_object_key"] = "capital_structure/share_counts/v2/ledger.json"
        guard._witness["signature"] = signer.sign(
            publication._head_payload(guard._witness),
        )

    root = tmp_path / hostile_kind
    with pytest.raises(publication.ShareCountPublicationError, match=error):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
        )

    base = root / "data/capital_structure/share_counts/v2"
    assert not (base / publication.POINTER_NAME).exists()


def test_missing_production_environment_is_a_hard_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", raising=False)
    monkeypatch.delenv("SHARE_COUNT_HEAD_GUARD_BUCKET", raising=False)
    monkeypatch.delenv("R2_CAPITAL_STRUCTURE_BUCKET", raising=False)
    monkeypatch.delenv("R2_BUCKET", raising=False)
    monkeypatch.delenv("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", raising=False)
    with pytest.raises(publication.ShareCountPublicationError, match="unconfigured"):
        publication.recover_share_count_materialization()


def test_production_v2_flag_false_allows_missing_account_and_constructs_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine.capital_structure import source_store

    monkeypatch.setenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", "s" * 32)
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_BUCKET", "fixture")
    monkeypatch.delenv("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("SHARE_COUNT_HEAD_GUARD_KEY_ID", raising=False)
    monkeypatch.delenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_KEY_ID", raising=False)
    calls = []
    client = object()
    monkeypatch.setattr(
        source_store,
        "_capital_structure_r2_client",
        lambda: calls.append("constructed") or client,
    )
    signer, guard = publication._production_trust(migration_enabled=False)
    assert signer.key_id == "share-count-head-v2"
    assert isinstance(guard, publication.R2ShareCountHeadGuard)
    assert guard._client is client
    assert guard._guard_scope is None
    assert calls == ["constructed"]


def test_production_migration_requires_account_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine.capital_structure import source_store

    monkeypatch.setenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", "s" * 32)
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_BUCKET", "fixture")
    monkeypatch.delenv("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", raising=False)
    calls = []
    monkeypatch.setattr(
        source_store,
        "_capital_structure_r2_client",
        lambda: calls.append("constructed") or object(),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="requires.*ACCOUNT_ID"):
        publication._production_trust(migration_enabled=True)
    assert calls == []


def test_production_migration_rejects_malformed_account_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine.capital_structure import source_store

    monkeypatch.setenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", "s" * 32)
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_BUCKET", "fixture")
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", "A" * 32)
    monkeypatch.setenv(
        "R2_CAPITAL_STRUCTURE_ENDPOINT",
        "https://" + "a" * 32 + ".r2.cloudflarestorage.com",
    )
    calls = []
    monkeypatch.setattr(
        source_store,
        "_capital_structure_r2_client",
        lambda: calls.append("constructed") or object(),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="lowercase hexadecimal"):
        publication._production_trust(migration_enabled=True)
    assert calls == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://" + "b" * 32 + ".r2.cloudflarestorage.com",
        "http://" + "a" * 32 + ".r2.cloudflarestorage.com",
        "https://" + "a" * 32 + ".r2.cloudflarestorage.com/",
        "https://" + "a" * 32 + ".r2.cloudflarestorage.com:443",
        "https://user@" + "a" * 32 + ".r2.cloudflarestorage.com",
    ],
)
def test_production_account_endpoint_mismatch_stops_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    from engine.capital_structure import source_store

    monkeypatch.setenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", "s" * 32)
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_BUCKET", "fixture")
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", "a" * 32)
    monkeypatch.setenv("R2_CAPITAL_STRUCTURE_ENDPOINT", endpoint)
    calls = []
    monkeypatch.setattr(
        source_store,
        "_capital_structure_r2_client",
        lambda: calls.append("constructed") or object(),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="exact Cloudflare R2 endpoint"):
        publication._production_trust(migration_enabled=False)
    assert calls == []


@pytest.mark.parametrize("jurisdiction", ["", "eu.", "fedramp."])
def test_production_account_accepts_only_exact_cloudflare_r2_hosts(
    monkeypatch: pytest.MonkeyPatch,
    jurisdiction: str,
) -> None:
    from engine.capital_structure import source_store

    account_id = "a" * 32
    monkeypatch.setenv("CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_HMAC_KEY", "s" * 32)
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_BUCKET", "fixture")
    monkeypatch.setenv("SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID", account_id)
    monkeypatch.setenv(
        "R2_CAPITAL_STRUCTURE_ENDPOINT",
        f"https://{account_id}.{jurisdiction}r2.cloudflarestorage.com",
    )
    client = object()
    monkeypatch.setattr(source_store, "_capital_structure_r2_client", lambda: client)
    _, guard = publication._production_trust(migration_enabled=True)
    assert guard._client is client


def test_malformed_migration_flag_stops_before_production_trust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED",
        "True",
    )
    calls = []
    monkeypatch.setattr(
        publication,
        "_production_trust",
        lambda **_kwargs: calls.append("trust") or (_ for _ in ()).throw(
            AssertionError("trust must not be constructed"),
        ),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="exactly true or false"):
        publication.recover_share_count_materialization()
    assert calls == []


def test_production_migration_flag_parser_defaults_false_and_is_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED",
        "True",
    )
    with pytest.raises(publication.ShareCountPublicationError, match="exactly true or false"):
        publication._head_v3_migration_enabled()
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED",
        "true",
    )
    assert publication._head_v3_migration_enabled() is True
    monkeypatch.delenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED",
        raising=False,
    )
    assert publication._head_v3_migration_enabled() is False


@pytest.mark.parametrize("swap_level", ["share_counts", "data"])
def test_held_dirfds_reject_parent_rebind_without_writing_outside(
    tmp_path: Path, swap_level: str,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    outside = tmp_path / f"outside-{swap_level}"
    outside.mkdir()

    def swap_after_validation(stage: str) -> None:
        if stage != "before_cas":
            return
        if swap_level == "share_counts":
            target = root / "data/capital_structure/share_counts"
            moved = target.with_name("share_counts-held-by-publisher")
        else:
            target = root / "data"
            moved = root / "data-held-by-publisher"
            (outside / "capital_structure/share_counts").mkdir(parents=True)
        target.rename(moved)
        target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(publication.ShareCountPublicationError, match="rebound"):
        _publish(
            root,
            signer,
            guard,
            b'{"generation":2}\n',
            suffix="b",
            fault=swap_after_validation,
        )

    assert not [path for path in outside.rglob("*") if not path.is_dir()]
    head, _ = guard.read()
    assert head is not None and head["receipt_id"] == first.receipt_id


def test_post_cas_parent_rebind_is_indeterminate_but_recoverable_and_never_escapes(
    tmp_path: Path,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    base = root / "data/capital_structure/share_counts"
    moved = base.with_name("share_counts-held-after-cas")
    outside = tmp_path / "outside-after-cas"
    outside.mkdir()

    def swap_after_cas(stage: str) -> None:
        if stage == "after_cas":
            base.rename(moved)
            base.symlink_to(outside, target_is_directory=True)

    with pytest.raises(publication.ShareCountPublishIndeterminate):
        _publish(
            root,
            signer,
            guard,
            b'{"generation":2}\n',
            suffix="b",
            fault=swap_after_cas,
        )
    assert list(outside.iterdir()) == []

    base.unlink()
    moved.rename(base)
    healed = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert healed is not None and healed.sequence == 2
    assert healed.ledger_bytes == b'{"generation":2}\n'


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo"])
def test_publication_base_rejects_unsafe_directory_entry_without_touching_target(
    tmp_path: Path, unsafe_kind: str,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    parent = root / "data/capital_structure"
    parent.mkdir(parents=True)
    base = parent / "share_counts"
    outside = tmp_path / f"unsafe-target-{unsafe_kind}"
    outside.mkdir()
    if unsafe_kind == "symlink":
        base.symlink_to(outside, target_is_directory=True)
    else:
        os.mkfifo(base)

    with pytest.raises(publication.ShareCountPublicationError, match="cannot be opened safely"):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
            deadline=time.monotonic() + 0.2,
        )
    assert list(outside.iterdir()) == []


def test_public_api_exposes_no_generic_production_signing_or_trust_override() -> None:
    assert "publish_share_count_materialization" not in publication.__all__
    assert not hasattr(publication, "publish_share_count_materialization")


def test_explicit_operation_budget_is_positive_and_capped() -> None:
    assert publication._operation_budget(0.25) == 0.25
    assert (
        publication._operation_budget(publication.PUBLICATION_TIMEOUT_SECONDS * 2)
        == publication.PUBLICATION_TIMEOUT_SECONDS
    )
    for invalid in (0, -1, float("inf"), float("nan"), True):
        with pytest.raises(publication.ShareCountPublicationError, match="budget must be positive"):
            publication._operation_budget(invalid)


def test_lease_rejects_unsafe_lock_file_without_blocking(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    lock = root / "data/capital_structure/share_counts/v2/.share_count_publish.lock"
    lock.parent.mkdir(parents=True)
    os.mkfifo(lock)
    with pytest.raises(publication.ShareCountPublicationError, match="lease path is unsafe"):
        publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard, deadline=time.monotonic() + 0.2,
        )


def test_lease_deadline_includes_a_held_cross_process_lock(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    lock = root / "data/capital_structure/share_counts/v2/.share_count_publish.lock"
    lock.parent.mkdir(parents=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(publication.ShareCountPublicationError, match="lease timed out"):
            publication._recover_share_count_materialization_for_test(
                root=root, signer=signer, head_guard=guard, deadline=time.monotonic() + 0.08,
            )
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_slow_external_head_read_cannot_return_success_after_deadline(tmp_path: Path) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    clock = [0.0]

    class SlowGuard(publication.InMemoryShareCountHeadGuard):
        def read(self):
            # Advance a deterministic operation clock instead of relying on a
            # sub-second wall-clock sleep.  Shared CI runners may wake a sleep
            # early, but the contract under test is that an external read
            # which consumes the remaining budget cannot return success.
            clock[0] += 0.35
            return super().read()

    guard = SlowGuard(signer)
    with pytest.raises(publication.ShareCountPublicationError, match="deadline exceeded"):
        publication._recover_share_count_materialization_for_test(
            root=tmp_path / "slow-workspace",
            signer=signer,
            head_guard=guard,
            deadline=0.1,
            monotonic=lambda: clock[0],
        )
    assert clock[0] == pytest.approx(0.35)


def test_same_head_new_token_conflict_clears_cas_started_recovery_state(tmp_path: Path) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    original_advance = guard.advance

    def churn_token_then_conflict(*, expected, expected_token, candidate) -> None:
        guard._version += 1
        original_advance(
            expected=expected,
            expected_token=expected_token,
            candidate=candidate,
        )

    guard.advance = churn_token_then_conflict
    with pytest.raises(publication.ShareCountPublicationConflict):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")

    base = root / "data/capital_structure/share_counts/v2"
    assert not (base / publication.PENDING_NAME).exists()
    assert not (base / publication.RECOVERY_NAME).exists()
    recovered = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.receipt_id == first.receipt_id


def test_exception_after_cas_started_write_but_before_advance_cleans_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    original_write = publication._write_signed_record
    advance_calls = 0
    original_advance = guard.advance

    def count_advance(*, expected, expected_token, candidate) -> None:
        nonlocal advance_calls
        advance_calls += 1
        original_advance(
            expected=expected,
            expected_token=expected_token,
            candidate=candidate,
        )

    def fail_after_write(lane, name, record, *, max_bytes, label):
        body = original_write(
            lane, name, record, max_bytes=max_bytes, label=label,
        )
        if name == publication.PENDING_NAME and record.get("phase") == "cas_started":
            raise publication.ShareCountPublicationError("injected pre-invocation failure")
        return body

    guard.advance = count_advance
    monkeypatch.setattr(publication, "_write_signed_record", fail_after_write)
    with pytest.raises(publication.ShareCountPublicationError, match="pre-invocation"):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")
    assert advance_calls == 0

    base = root / "data/capital_structure/share_counts/v2"
    assert not (base / publication.PENDING_NAME).exists()
    assert not (base / publication.RECOVERY_NAME).exists()
    monkeypatch.setattr(publication, "_write_signed_record", original_write)
    recovered = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.receipt_id == first.receipt_id


def test_abrupt_crash_after_capsule_before_marker_recovers_authoritative_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    original_write = publication._write_signed_record

    def crash_after_capsule(lane, name, record, *, max_bytes, label):
        body = original_write(
            lane, name, record, max_bytes=max_bytes, label=label,
        )
        if name == publication.RECOVERY_NAME:
            # Deliberately bypass the publisher's ordinary error cleanup: this
            # models process death after capsule fsync and before marker write.
            raise SystemExit("crash after recovery capsule")
        return body

    monkeypatch.setattr(publication, "_write_signed_record", crash_after_capsule)
    with pytest.raises(SystemExit, match="after recovery capsule"):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")

    base = root / "data/capital_structure/share_counts/v2"
    assert (base / publication.RECOVERY_NAME).exists()
    assert not (base / publication.PENDING_NAME).exists()
    assert guard.read()[0] is not None and guard.read()[0]["receipt_id"] == first.receipt_id

    monkeypatch.setattr(publication, "_write_signed_record", original_write)
    recovered = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.receipt_id == first.receipt_id
    assert not (base / publication.RECOVERY_NAME).exists()
    assert not (base / publication.PENDING_NAME).exists()


def test_abrupt_crash_after_cas_started_before_advance_replays_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    original_write = publication._write_signed_record
    original_advance = guard.advance
    advance_calls = 0

    def count_advance(*, expected, expected_token, candidate) -> None:
        nonlocal advance_calls
        advance_calls += 1
        original_advance(
            expected=expected,
            expected_token=expected_token,
            candidate=candidate,
        )

    def crash_after_cas_started(lane, name, record, *, max_bytes, label):
        body = original_write(
            lane, name, record, max_bytes=max_bytes, label=label,
        )
        if name == publication.PENDING_NAME and record.get("phase") == "cas_started":
            # This is the former unrecoverable gap: the durable marker claims
            # CAS intent, but no guard call has been entered.
            raise SystemExit("crash after cas_started")
        return body

    guard.advance = count_advance
    monkeypatch.setattr(publication, "_write_signed_record", crash_after_cas_started)
    with pytest.raises(SystemExit, match="after cas_started"):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")
    assert advance_calls == 0

    base = root / "data/capital_structure/share_counts/v2"
    assert (base / publication.PENDING_NAME).exists()
    assert (base / publication.RECOVERY_NAME).exists()
    assert guard.read()[0] is not None and guard.read()[0]["sequence"] == 1

    monkeypatch.setattr(publication, "_write_signed_record", original_write)
    recovered = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.sequence == 2
    assert recovered.ledger_bytes == b'{"generation":2}\n'
    assert advance_calls == 1
    assert not (base / publication.PENDING_NAME).exists()
    assert not (base / publication.RECOVERY_NAME).exists()


def test_marker_first_cleanup_crash_leaves_capsule_only_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    original_remove = publication._remove_exact_at

    def crash_after_marker(directory_fd, name, body, *, max_bytes, label, operation):
        original_remove(
            directory_fd,
            name,
            body,
            max_bytes=max_bytes,
            label=label,
            operation=operation,
        )
        if name == publication.PENDING_NAME:
            # The external head and local pointer have both committed.  An
            # abrupt death in the historical marker-first cleanup order leaves
            # the capsule alone for the next process.
            raise SystemExit("crash after pending marker cleanup")

    monkeypatch.setattr(publication, "_remove_exact_at", crash_after_marker)
    with pytest.raises(publication.ShareCountPublishIndeterminate):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")

    base = root / "data/capital_structure/share_counts/v2"
    assert not (base / publication.PENDING_NAME).exists()
    assert (base / publication.RECOVERY_NAME).exists()
    selected, version = guard.read()
    assert selected is not None and selected["sequence"] == 2 and version == "2"

    monkeypatch.setattr(publication, "_remove_exact_at", original_remove)
    recovered = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.sequence == 2
    assert recovered.ledger_bytes == b'{"generation":2}\n'
    assert guard.read()[1] == "2"  # recovery did not re-drive a committed CAS
    assert not (base / publication.PENDING_NAME).exists()
    assert not (base / publication.RECOVERY_NAME).exists()


def test_prepared_records_survive_delayed_selected_local_ledger_failure(
    tmp_path: Path,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    selected = _publish(root, signer, guard)

    def crash_with_prepared_records(stage: str) -> None:
        if stage == "before_cas":
            raise SystemExit("crash with prepared records")

    with pytest.raises(SystemExit, match="prepared records"):
        _publish(
            root,
            signer,
            guard,
            b'{"candidate":true}\n',
            suffix="b",
            fault=crash_with_prepared_records,
        )

    base = root / "data/capital_structure/share_counts/v2"
    marker_path = base / publication.PENDING_NAME
    capsule_path = base / publication.RECOVERY_NAME
    marker_body = marker_path.read_bytes()
    capsule_body = capsule_path.read_bytes()

    selected.ledger_path.unlink()
    with pytest.raises(publication.ShareCountPublicationError, match="immutable ledger is missing"):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
        )

    assert marker_path.read_bytes() == marker_body
    assert capsule_path.read_bytes() == capsule_body

    selected.ledger_path.write_bytes(selected.ledger_bytes)
    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
    )
    assert recovered is not None and recovered.receipt_id == selected.receipt_id
    assert recovered.ledger_bytes == selected.ledger_bytes
    assert not marker_path.exists()
    assert not capsule_path.exists()


def test_pending_expected_witness_is_temporary_high_water_when_pointer_is_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    first = _publish(root, signer, guard)

    def crash_before_cas(stage: str) -> None:
        if stage == "before_cas":
            raise SystemExit("crash with prepared marker")

    with pytest.raises(SystemExit, match="prepared marker"):
        _publish(
            root,
            signer,
            guard,
            b'{"candidate":true}\n',
            suffix="b",
            fault=crash_before_cas,
        )

    pointer_path = root / "data/capital_structure/share_counts/v2/current_receipt.json"
    pointer_path.unlink()  # same-crash local selector loss
    fork_ledger = b'{"signed":"fork"}\n'
    fork_receipt, fork_body = _synthetic_receipt(signer, 2, ledger=fork_ledger)
    _select_external_head(guard, signer, fork_receipt, fork_body, fork_ledger)

    guard.reset_artifact_reads(reject_ledgers=True)
    _forbid_local_ledger_reads(monkeypatch)
    with pytest.raises(
        publication.ShareCountPublicationError,
        match="(?:forks|diverges from) pending expected high-water",
    ):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
        )
    assert guard.read()[0] is not None and guard.read()[0]["receipt_id"] != first.receipt_id
    assert guard.artifact_read_keys == [
        publication._receipt_external_key(fork_receipt["receipt_id"]),
    ]


def test_pending_expected_high_water_beats_replayed_older_local_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    first = _publish(root, signer, guard)
    pointer_path = root / "data/capital_structure/share_counts/v2/current_receipt.json"
    first_pointer = pointer_path.read_bytes()
    _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")

    def crash_before_cas(stage: str) -> None:
        if stage == "before_cas":
            raise SystemExit("crash with expected E")

    with pytest.raises(SystemExit, match="expected E"):
        _publish(
            root,
            signer,
            guard,
            b'{"candidate":true}\n',
            suffix="c",
            fault=crash_before_cas,
        )

    # Valid but older F is restored locally while the signed marker retains E.
    pointer_path.write_bytes(first_pointer)
    fork_ledger = b'{"signed":"fork-from-f"}\n'
    first_body = publication._canonical_bytes(dict(first.receipt)) + b"\n"
    fork_receipt, fork_body = _synthetic_receipt(
        signer,
        2,
        ledger=fork_ledger,
        ancestor_overrides={0: _receipt_ref(first.receipt, first_body)},
    )
    _select_external_head(guard, signer, fork_receipt, fork_body, fork_ledger)

    guard.reset_artifact_reads(reject_ledgers=True)
    _forbid_local_ledger_reads(monkeypatch)
    with pytest.raises(
        publication.ShareCountPublicationError,
        match="forks pending expected high-water",
    ):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
        )
    assert guard.artifact_read_keys == [
        publication._receipt_external_key(fork_receipt["receipt_id"]),
    ]


def test_orphan_capsule_before_marker_rejects_sibling_and_retains_exact_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    first = _publish(root, signer, guard)
    original_write = publication._write_signed_record

    def crash_after_capsule(lane, name, record, *, max_bytes, label):
        body = original_write(
            lane, name, record, max_bytes=max_bytes, label=label,
        )
        if name == publication.RECOVERY_NAME:
            raise SystemExit("crash after recovery capsule")
        return body

    monkeypatch.setattr(publication, "_write_signed_record", crash_after_capsule)
    with pytest.raises(SystemExit, match="after recovery capsule"):
        _publish(root, signer, guard, b'{"candidate":true}\n', suffix="b")
    monkeypatch.setattr(publication, "_write_signed_record", original_write)

    # A separate clean publisher observes E and legitimately wins E -> C'.
    competitor = _publish(
        tmp_path / "competing-publisher",
        signer,
        guard,
        b'{"competing":true}\n',
        suffix="c",
    )
    assert competitor.sequence == 2 and competitor.receipt_id != first.receipt_id

    base = root / "data/capital_structure/share_counts/v2"
    capsule_path = base / publication.RECOVERY_NAME
    pointer_path = base / publication.POINTER_NAME
    capsule_before = capsule_path.read_bytes()
    pointer_before = pointer_path.read_bytes()
    guard.reset_artifact_reads(reject_ledgers=True)
    guard.reset_writes()
    with pytest.raises(publication.ShareCountPublicationError, match="orphan recovery capsule conflicts"):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
        )
    assert capsule_path.read_bytes() == capsule_before
    assert pointer_path.read_bytes() == pointer_before
    assert guard.artifact_reads == 0
    assert guard.artifact_seals == guard.advances == guard.migrations == 0
    assert (base / publication.RECOVERY_NAME).exists()
    assert not (base / publication.PENDING_NAME).exists()


def test_v3_head_with_any_legacy_bytes_fails_unchanged_before_artifact_or_ledger_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    _publish(root, signer, guard)
    publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    base = root / "data/capital_structure/share_counts/v2"
    pointer_path = base / publication.POINTER_NAME
    capsule_path = base / publication.RECOVERY_NAME
    pointer_before = pointer_path.read_bytes()
    malformed = b"malformed-legacy-capsule\n"
    capsule_path.write_bytes(malformed)
    guard.reset_artifact_reads(reject_ledgers=True)
    guard.reset_writes()
    _forbid_local_ledger_reads(monkeypatch)

    with pytest.raises(publication.ShareCountPublishIndeterminate, match="cannot coexist"):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
            migrate_head_v3=True,
        )
    assert pointer_path.read_bytes() == pointer_before
    assert capsule_path.read_bytes() == malformed
    assert guard.artifact_reads == 0
    assert guard.artifact_seals == guard.advances == guard.migrations == 0


def test_legacy_seen_at_entry_defers_v3_migration_until_next_clean_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    _publish(root, signer, guard)
    original_write = publication._write_signed_record

    def crash_after_capsule(lane, name, record, *, max_bytes, label):
        body = original_write(
            lane,
            name,
            record,
            max_bytes=max_bytes,
            label=label,
        )
        if name == publication.RECOVERY_NAME:
            raise SystemExit("crash after recovery capsule")
        return body

    monkeypatch.setattr(publication, "_write_signed_record", crash_after_capsule)
    with pytest.raises(SystemExit, match="after recovery capsule"):
        _publish(root, signer, guard, b'{"candidate":true}\n', suffix="b")
    monkeypatch.setattr(publication, "_write_signed_record", original_write)
    guard.reset_writes()

    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    head, token = guard.read()
    assert recovered is not None
    assert head is not None and head["schema"] == publication.WITNESS_V2_SCHEMA
    assert token == "1" and guard.migrations == 0
    assert not (
        root
        / "data/capital_structure/share_counts/v2"
        / publication.RECOVERY_NAME
    ).exists()

    publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    head, token = guard.read()
    assert head is not None and head["schema"] == publication.WITNESS_V3_SCHEMA
    assert token == "2" and guard.migrations == 1


def test_v3_migration_exactly_rereads_both_legacy_names_absent_after_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    _publish(root, signer, guard)
    original_recover = publication._recover_locked
    injected = b"appeared-after-recovery\n"
    capsule_path = (
        root
        / "data/capital_structure/share_counts/v2"
        / publication.RECOVERY_NAME
    )

    def recover_then_inject(lane, *, signer, guard, trace=None):
        result = original_recover(
            lane,
            signer=signer,
            guard=guard,
            trace=trace,
        )
        capsule_path.write_bytes(injected)
        return result

    monkeypatch.setattr(publication, "_recover_locked", recover_then_inject)
    guard.reset_writes()
    with pytest.raises(publication.ShareCountPublishIndeterminate, match="exact post-recovery"):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
            migrate_head_v3=True,
        )
    head, token = guard.read()
    assert head is not None and head["schema"] == publication.WITNESS_V2_SCHEMA
    assert token == "1" and guard.migrations == 0
    assert capsule_path.read_bytes() == injected


def test_orphan_capsule_accepts_bounded_descendant_of_committed_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    _publish(root, signer, guard)
    original_remove = publication._remove_exact_at

    def crash_after_marker(directory_fd, name, body, *, max_bytes, label, operation):
        original_remove(
            directory_fd,
            name,
            body,
            max_bytes=max_bytes,
            label=label,
            operation=operation,
        )
        if name == publication.PENDING_NAME:
            raise SystemExit("crash after pending marker cleanup")

    monkeypatch.setattr(publication, "_remove_exact_at", crash_after_marker)
    with pytest.raises(publication.ShareCountPublishIndeterminate):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")
    monkeypatch.setattr(publication, "_remove_exact_at", original_remove)

    pointer_path = root / "data/capital_structure/share_counts/v2/current_receipt.json"
    pointer_path.unlink()
    descendant = _publish(
        tmp_path / "descendant-publisher",
        signer,
        guard,
        b'{"generation":3}\n',
        suffix="c",
    )
    assert descendant.sequence == 3

    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
    )
    base = root / "data/capital_structure/share_counts/v2"
    assert recovered is not None and recovered.sequence == 3
    assert recovered.ledger_bytes == b'{"generation":3}\n'
    assert not (base / publication.RECOVERY_NAME).exists()


def test_orphan_capsule_rejects_divergent_descendant_proof_before_ledger_and_retains_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = publication.HmacShareCountSigner(b"s" * 32, key_id="test-share-count")
    guard = _CountingGuard(signer)
    root = tmp_path / "workspace"
    _publish(root, signer, guard)
    original_remove = publication._remove_exact_at

    def crash_after_marker(directory_fd, name, body, *, max_bytes, label, operation):
        original_remove(
            directory_fd,
            name,
            body,
            max_bytes=max_bytes,
            label=label,
            operation=operation,
        )
        if name == publication.PENDING_NAME:
            raise SystemExit("crash after pending marker cleanup")

    monkeypatch.setattr(publication, "_remove_exact_at", crash_after_marker)
    with pytest.raises(publication.ShareCountPublishIndeterminate):
        _publish(root, signer, guard, b'{"generation":2}\n', suffix="b")
    monkeypatch.setattr(publication, "_remove_exact_at", original_remove)

    hostile_ledger = b'{"hostile":3}\n'
    hostile_receipt, hostile_body = _synthetic_receipt(
        signer,
        3,
        ledger=hostile_ledger,
        ancestor_overrides={0: _dummy_ref(2, salt="sibling-of-candidate")},
    )
    _select_external_head(
        guard,
        signer,
        hostile_receipt,
        hostile_body,
        hostile_ledger,
    )
    base = root / "data/capital_structure/share_counts/v2"
    capsule_path = base / publication.RECOVERY_NAME
    pointer_path = base / publication.POINTER_NAME
    capsule_before = capsule_path.read_bytes()
    pointer_before = pointer_path.read_bytes()
    guard.reset_artifact_reads(reject_ledgers=True)
    guard.reset_writes()

    with pytest.raises(publication.ShareCountPublicationError, match="diverges from pending"):
        publication._recover_share_count_materialization_for_test(
            root=root,
            signer=signer,
            head_guard=guard,
        )
    assert guard.artifact_read_keys == [
        publication._receipt_external_key(hostile_receipt["receipt_id"]),
    ]
    assert capsule_path.read_bytes() == capsule_before
    assert pointer_path.read_bytes() == pointer_before
    assert guard.artifact_seals == guard.advances == guard.migrations == 0


def test_capsule_embedded_pointers_must_match_its_signed_witnesses(
    tmp_path: Path,
) -> None:
    signer, guard, root = _publisher(tmp_path)
    first = _publish(root, signer, guard)
    first_head, _ = guard.read()
    second_root = tmp_path / "other-publisher"
    second = _publish(second_root, signer, guard, b'{"generation":2}\n', suffix="b")
    second_head, _ = guard.read()
    assert first_head is not None and second_head is not None

    first_pointer = (
        root / "data/capital_structure/share_counts/v2/current_receipt.json"
    ).read_bytes()
    second_pointer = (
        second_root / "data/capital_structure/share_counts/v2/current_receipt.json"
    ).read_bytes()
    capsule = publication._capsule(
        expected=first_head,
        candidate=second_head,
        expected_pointer=first_pointer,
        candidate_pointer=second_pointer,
        signer=signer,
    )
    capsule["candidate_pointer_b64"] = base64.b64encode(first_pointer).decode("ascii")
    capsule["candidate_pointer_sha256"] = publication._sha(first_pointer)
    capsule["signature"] = signer.sign(publication._recovery_payload(capsule))
    with pytest.raises(publication.ShareCountPublicationError, match="candidate pointer is detached"):
        publication._validate_capsule(capsule, signer=signer)
    assert first.receipt_id != second.receipt_id


class _FakeR2:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.etags: dict[str, str] = {}
        self.put_calls: list[dict] = []

    def head_object(self, *, Bucket: str, Key: str):
        if Key not in self.objects:
            error = RuntimeError("missing")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"ContentLength": len(self.objects[Key]), "ETag": self.etags[Key]}

    def get_object(self, *, Bucket: str, Key: str, Range: str, IfMatch: str):
        if IfMatch != self.etags.get(Key):
            error = RuntimeError("precondition")
            error.response = {"Error": {"Code": "412"}, "ResponseMetadata": {"HTTPStatusCode": 412}}
            raise error
        body = self.objects[Key]
        return {"ContentLength": len(body), "ETag": IfMatch, "Body": BytesIO(body)}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **kwargs):
        self.put_calls.append({"Bucket": Bucket, "Key": Key, "Body": Body, **kwargs})
        if kwargs.get("IfNoneMatch") == "*" and Key in self.objects:
            error = RuntimeError("exists")
            error.response = {"Error": {"Code": "412"}, "ResponseMetadata": {"HTTPStatusCode": 412}}
            raise error
        if "IfMatch" in kwargs and kwargs["IfMatch"] != self.etags.get(Key):
            error = RuntimeError("changed")
            error.response = {"Error": {"Code": "412"}, "ResponseMetadata": {"HTTPStatusCode": 412}}
            raise error
        self.objects[Key] = Body; self.etags[Key] = '"' + publication._sha(Body) + '"'


def test_r2_guard_uses_head_then_bounded_ifmatch_get_and_conditional_put(tmp_path: Path) -> None:
    signer = publication.HmacShareCountSigner(b"k" * 32, key_id="test")
    r2 = _FakeR2(); guard = publication.R2ShareCountHeadGuard(client=r2, bucket="fixture", signer=signer)
    result = _publish(tmp_path / "r2", signer, guard)
    head, etag = guard.read()
    assert head is not None and etag is not None and result.sequence == 1
    assert publication.HEAD_GUARD_KEY in r2.objects


def test_r2_v3_migration_uses_same_key_exact_token_and_old_reader_never_puts(
    tmp_path: Path,
) -> None:
    signer = publication.HmacShareCountSigner(b"k" * 32, key_id="test")
    r2 = _FakeR2()
    guard = publication.R2ShareCountHeadGuard(
        client=r2,
        bucket="fixture",
        signer=signer,
        account_id="a" * 32,
    )
    root = tmp_path / "r2"
    first = _publish(root, signer, guard)
    v2_head, v2_token = guard.read()
    assert v2_head is not None and v2_token is not None
    puts_before_migration = len(r2.put_calls)
    publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
        migrate_head_v3=True,
    )
    v3_head, _ = guard.read()
    assert v3_head is not None and v3_head["schema"] == publication.WITNESS_V3_SCHEMA
    migration_puts = r2.put_calls[puts_before_migration:]
    assert len(migration_puts) == 1
    assert migration_puts[0]["Key"] == publication.HEAD_GUARD_KEY
    assert migration_puts[0]["IfMatch"] == v2_token
    assert "IfNoneMatch" not in migration_puts[0]

    puts_before_old_read = len(r2.put_calls)
    raw = publication._parse_canonical_json(
        r2.objects[publication.HEAD_GUARD_KEY],
        label="old v2 reader fixture",
    )
    with pytest.raises(publication.ShareCountPublicationError, match="shape"):
        publication._validate_head_witness(raw, signer=signer)
    assert len(r2.put_calls) == puts_before_old_read

    next_receipt, next_body = _synthetic_receipt(
        signer,
        2,
        ledger=b'{"old-writer":2}\n',
        ancestor_overrides={
            0: {
                "sequence": first.sequence,
                "receipt_id": first.receipt_id,
                "receipt_sha256": v2_head["receipt_sha256"],
                "receipt_byte_length": v2_head["receipt_byte_length"],
            },
        },
    )
    old_v2_candidate = publication._head_witness(
        receipt=next_receipt,
        receipt_body=next_body,
        signer=signer,
    )
    with pytest.raises(publication.ShareCountPublicationError, match="migration fence"):
        guard.advance(
            expected=v2_head,
            expected_token=v2_token,
            candidate=old_v2_candidate,
        )
    assert len(r2.put_calls) == puts_before_old_read
