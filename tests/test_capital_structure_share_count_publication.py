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
    with pytest.raises(publication.ShareCountPublicationError, match="unconfigured"):
        publication.recover_share_count_materialization()


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


def test_orphan_capsule_before_marker_converges_competing_successor(
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
    recovered = publication._recover_share_count_materialization_for_test(
        root=root,
        signer=signer,
        head_guard=guard,
    )
    assert recovered is not None and recovered.receipt_id == competitor.receipt_id
    assert recovered.ledger_bytes == b'{"competing":true}\n'
    assert not (base / publication.RECOVERY_NAME).exists()
    assert not (base / publication.PENDING_NAME).exists()


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
