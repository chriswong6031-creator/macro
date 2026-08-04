"""Runtime proofs for the native scope-bound share-count v4 protocol."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.capital_structure import share_count_publication as publication


def _binding(suffix: str) -> dict:
    return {
        "schema": "capital_structure.share_count_materialization_input_binding/v1",
        "ledger_head_receipt_id": "share-count-ledger-receipt-v2:cs:" + suffix * 24,
        "ledger_sequence": 1,
        "compiler_version": "capital-structure-share-count-materializer/2.1.0",
        "materialized_at": "2026-08-03T00:00:00Z",
        "prefixes": {
            label: {"count": 1, "rolling_sha256": suffix * 64}
            for label in ("observations", "source_snapshots", "bridges", "source_manifests")
        },
    }


def _fixture(tmp_path: Path, name: str = "workspace"):
    signer = publication.HmacShareCountSigner(b"v" * 32, key_id="v4-runtime")
    guard = publication.InMemoryShareCountHeadGuard(signer)
    return signer, guard, tmp_path / name


def _publish(root: Path, signer, guard, suffix: str, **kwargs):
    return publication._publish_share_count_materialization_for_test(
        root=root,
        canonical_ledger_bytes=(f'{{"ledger":"{suffix}"}}\n').encode(),
        input_binding=_binding(suffix),
        signer=signer,
        head_guard=guard,
        now=datetime(2026, 8, 3, tzinfo=timezone.utc),
        validate_ledger=False,
        **kwargs,
    )


def _crash_journal(root: Path, signer, guard, suffix: str, *, v4: bool = False) -> dict:
    def crash(stage: str) -> None:
        if stage == "before_cas":
            raise SystemExit("journal durable")

    with pytest.raises(SystemExit, match="journal durable"):
        _publish(root, signer, guard, suffix, publish_head_v4=v4, fault=crash)
    body = (
        root
        / "data/capital_structure/share_counts/v2"
        / publication.JOURNAL_NAME
    ).read_bytes()
    return publication._parse_canonical_json(
        body,
        label="test journal",
        max_bytes=publication.MAX_PUBLISH_JOURNAL_BYTES,
    )


def _candidate_receipt(journal: dict, guard, signer) -> tuple[dict, bytes]:
    witness = journal["candidate_witness"]
    body = guard.read_artifact(
        key=witness["receipt_object_key"],
        max_bytes=publication.MAX_RECEIPT_BYTES,
    )
    receipt = publication._validate_receipt(
        publication._parse_canonical_json(body, label="candidate receipt"),
        signer=signer,
    )
    return receipt, body


def test_exact_v2_and_v3_structural_migrations_reach_same_selection_v4(tmp_path: Path) -> None:
    for predecessor in ("v2", "v3"):
        signer, guard, root = _fixture(tmp_path, predecessor)
        first = _publish(root, signer, guard, "a")
        if predecessor == "v3":
            publication._recover_share_count_materialization_for_test(
                root=root, signer=signer, head_guard=guard, migrate_head_v3=True,
            )
        before, _ = guard.read()
        assert before is not None and before["schema"].endswith("/" + predecessor)
        recovered = publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard, migrate_head_v4=True,
        )
        head, _ = guard.read()
        assert recovered is not None and recovered.receipt_id == first.receipt_id
        assert head is not None and head["schema"] == publication.WITNESS_V4_SCHEMA
        assert publication._head_selection(head) == publication._head_selection(before)
        assert head["transition"]["from_schema"] == before["schema"]
        publication._validate_head_migration_v4(
            previous=before,
            candidate=head,
            signer=signer,
            expected_scope=guard.guard_scope,
        )


def test_native_v4_genesis_and_successor_use_closed_journal_v2(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    first = _publish(root, signer, guard, "a", publish_head_v4=True)
    genesis, _ = guard.read()
    assert genesis is not None and genesis["transition"] == {"kind": "genesis"}
    second = _publish(root, signer, guard, "b", publish_head_v4=True)
    successor, _ = guard.read()
    assert successor is not None and successor["transition"] == {
        "kind": "successor",
        "previous_witness_sha256": publication._sha(
            publication._canonical_bytes(genesis) + b"\n"
        ),
    }
    assert first.sequence == 1 and second.sequence == 2


def test_v4_structural_migration_exits_before_caller_candidate_validation(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    first = _publish(root, signer, guard, "a")
    migrated = publication._publish_share_count_materialization_for_test(
        root=root,
        canonical_ledger_bytes=b"",
        input_binding={},
        signer=signer,
        head_guard=guard,
        migrate_head_v4=True,
        validate_ledger=True,
    )
    head, _ = guard.read()
    assert migrated.receipt_id == first.receipt_id
    assert head is not None and head["schema"] == publication.WITNESS_V4_SCHEMA


def test_v1_null_expected_journal_accepts_authenticated_v4_genesis(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    journal = _crash_journal(root, signer, guard, "a")
    receipt, receipt_body = _candidate_receipt(journal, guard, signer)
    v4 = publication._head_witness_v4(
        receipt=receipt,
        receipt_body=receipt_body,
        signer=signer,
        guard_scope=guard.guard_scope,
        previous=None,
    )
    guard.advance_v4(expected=None, expected_token=None, candidate=v4)
    result = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert result is not None and result.receipt_id == v4["receipt_id"]
    assert not (root / "data/capital_structure/share_counts/v2" / publication.JOURNAL_NAME).exists()


@pytest.mark.parametrize("successor", [False, True])
def test_journal_v2_replays_exact_native_v4_genesis_or_successor(
    tmp_path: Path, successor: bool,
) -> None:
    signer, guard, root = _fixture(tmp_path)
    if successor:
        _publish(root, signer, guard, "a", publish_head_v4=True)
    journal = _crash_journal(
        root,
        signer,
        guard,
        "b" if successor else "a",
        v4=True,
    )
    result = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    head, _ = guard.read()
    assert result is not None and head == journal["candidate_witness"]
    assert result.receipt_id == journal["candidate_witness"]["receipt_id"]
    assert not (root / "data/capital_structure/share_counts/v2" / publication.JOURNAL_NAME).exists()


def test_v1_journal_accepts_only_anchor_proven_v4_migration(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    first = _publish(root, signer, guard, "a")
    journal = _crash_journal(root, signer, guard, "b")
    expected, token = guard.read()
    assert expected == journal["expected_witness"] and token is not None
    migrated = publication._migrated_head_witness_v4(
        expected,
        signer=signer,
        guard_scope=guard.guard_scope,
    )
    guard.migrate_v2_or_v3_to_v4(
        expected=expected,
        expected_token=token,
        candidate=migrated,
    )
    result = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert result is not None and result.receipt_id == first.receipt_id


def test_v1_journal_converges_to_v4_successor_from_receipt_ancestry(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    _publish(root, signer, guard, "a")
    journal = _crash_journal(root, signer, guard, "b")
    expected, token = guard.read()
    assert expected is not None and token is not None
    migrated = publication._migrated_head_witness_v4(
        expected,
        signer=signer,
        guard_scope=guard.guard_scope,
    )
    guard.migrate_v2_or_v3_to_v4(
        expected=expected, expected_token=token, candidate=migrated,
    )
    receipt, receipt_body = _candidate_receipt(journal, guard, signer)
    selected = publication._head_witness_v4(
        receipt=receipt,
        receipt_body=receipt_body,
        signer=signer,
        guard_scope=guard.guard_scope,
        previous=migrated,
    )
    _, migrated_token = guard.read()
    guard.advance_v4(
        expected=migrated,
        expected_token=migrated_token,
        candidate=selected,
    )
    result = publication._recover_share_count_materialization_for_test(
        root=root, signer=signer, head_guard=guard,
    )
    assert result is not None and result.receipt_id == selected["receipt_id"]


def test_journal_v2_rejects_unproven_v4_selected_fork_and_retains_evidence(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path, "primary")
    _publish(root, signer, guard, "a", publish_head_v4=True)
    _crash_journal(root, signer, guard, "b", v4=True)

    other_guard = publication.InMemoryShareCountHeadGuard(signer)
    other_root = tmp_path / "other"
    _publish(other_root, signer, other_guard, "c", publish_head_v4=True)
    fork, _ = other_guard.read()
    assert fork is not None
    guard._witness = copy.deepcopy(fork)
    guard._version += 1
    with pytest.raises(publication.ShareCountPublicationError, match="forks"):
        publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard,
        )
    assert (root / "data/capital_structure/share_counts/v2" / publication.JOURNAL_NAME).exists()


def test_journal_v2_rejects_same_selection_v4_migration_as_unproven_outcome(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    _publish(root, signer, guard, "a", publish_head_v4=True)
    _crash_journal(root, signer, guard, "b", v4=True)
    expected, _ = guard.read()
    assert expected is not None
    virtual_v2 = {
        "schema": publication.WITNESS_V2_SCHEMA,
        "key_id": expected["key_id"],
        **publication._head_selection(expected),
        "signature": "",
    }
    virtual_v2["signature"] = signer.sign(publication._head_payload(virtual_v2))
    hostile = publication._migrated_head_witness_v4(
        virtual_v2,
        signer=signer,
        guard_scope=guard.guard_scope,
    )
    guard._witness = hostile
    guard._version += 1
    with pytest.raises(publication.ShareCountPublicationError, match="unproven v4 outcome"):
        publication._recover_share_count_materialization_for_test(
            root=root, signer=signer, head_guard=guard,
        )
    assert (root / "data/capital_structure/share_counts/v2" / publication.JOURNAL_NAME).exists()


def test_journal_v2_runtime_schema_resolves_local_ref_and_closes_transition_shape(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    journal = _crash_journal(root, signer, guard, "a", v4=True)
    validated = publication._validate_journal_v2(
        journal,
        signer=signer,
        expected_scope=guard.guard_scope,
    )
    assert validated["schema"] == publication.JOURNAL_V2_SCHEMA

    migration = publication._migrated_head_witness_v4(
        publication._head_witness(
            receipt=_candidate_receipt(journal, guard, signer)[0],
            receipt_body=_candidate_receipt(journal, guard, signer)[1],
            signer=signer,
        ),
        signer=signer,
        guard_scope=guard.guard_scope,
    )
    hostile = copy.deepcopy(journal)
    hostile["candidate_witness"] = migration
    hostile["signature"] = signer.sign_journal_v2(publication._journal_v2_payload(hostile))
    with pytest.raises(publication.ShareCountPublicationError, match="contract violation|genesis transition"):
        publication._validate_journal_v2(
            hostile,
            signer=signer,
            expected_scope=guard.guard_scope,
        )

    null_successor = copy.deepcopy(journal)
    prior = copy.deepcopy(null_successor["candidate_witness"])
    null_successor["candidate_witness"]["sequence"] = 2
    null_successor["candidate_witness"]["previous_receipt"] = publication._head_receipt_ref(prior)
    null_successor["candidate_witness"]["transition"] = {
        "kind": "successor",
        "previous_witness_sha256": publication._sha(
            publication._canonical_bytes(prior) + b"\n"
        ),
    }
    sign_head = signer.sign_head_v4
    null_successor["candidate_witness"]["signature"] = sign_head(
        publication._head_v4_payload(null_successor["candidate_witness"]),
    )
    null_successor["signature"] = signer.sign_journal_v2(
        publication._journal_v2_payload(null_successor),
    )
    with pytest.raises(publication.ShareCountPublicationError, match="contract violation"):
        publication._validate_contract(
            null_successor,
            "capital_structure_share_count_publish_journal_v2.schema.json",
            label="v4 publish journal",
        )
    with pytest.raises(publication.ShareCountPublicationError, match="contract violation|genesis transition"):
        publication._validate_journal_v2(
            null_successor,
            signer=signer,
            expected_scope=guard.guard_scope,
        )

    extra = copy.deepcopy(journal)
    extra["extra"] = True
    with pytest.raises(publication.ShareCountPublicationError, match="contract violation"):
        publication._validate_contract(
            extra,
            "capital_structure_share_count_publish_journal_v2.schema.json",
            label="v4 publish journal",
        )


def test_native_v4_disabled_blocks_successor_before_any_external_put(tmp_path: Path) -> None:
    signer, guard, root = _fixture(tmp_path)
    _publish(root, signer, guard, "a", publish_head_v4=True)
    seals_before = len(guard._artifacts)
    version_before = guard._version
    with pytest.raises(publication.ShareCountPublicationError, match="test seam is disabled"):
        _publish(root, signer, guard, "b")
    assert len(guard._artifacts) == seals_before
    assert guard._version == version_before


def test_native_v4_disabled_still_allows_clean_recovery_and_exact_noop(tmp_path: Path) -> None:
    signer, guard, writer = _fixture(tmp_path, "writer")
    first = _publish(writer, signer, guard, "a", publish_head_v4=True)
    clean = tmp_path / "clean"
    recovered = publication._recover_share_count_materialization_for_test(
        root=clean, signer=signer, head_guard=guard,
    )
    assert recovered is not None and recovered.receipt_id == first.receipt_id
    no_op = _publish(clean, signer, guard, "a")
    assert no_op.receipt_id == first.receipt_id and no_op.published is False


def test_production_v4_migration_flags_are_strict_mutually_exclusive_and_pretrust(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        publication,
        "_production_trust",
        lambda **_kwargs: calls.append("trust"),
    )
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V4_MIGRATION_ENABLED",
        "True",
    )
    with pytest.raises(publication.ShareCountPublicationError, match="exactly true or false"):
        publication.recover_share_count_materialization()
    assert calls == []

    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V4_MIGRATION_ENABLED",
        "true",
    )
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED",
        "true",
    )
    with pytest.raises(publication.ShareCountPublicationError, match="mutually exclusive"):
        publication.recover_share_count_materialization()
    assert calls == []
