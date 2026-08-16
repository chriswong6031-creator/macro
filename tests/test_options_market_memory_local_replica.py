import ast
import copy
import hashlib
import json
import os
import stat
import threading
from pathlib import Path
from typing import Any

import pytest

from engine import options_market_memory_context as context_bridge
from engine import options_market_memory_local_receipts as local_receipts
from engine import options_market_memory_local_replica as replica
from engine import options_market_memory_receipt_store as upstream_store
from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_pit
from engine.neuralweb import market_memory_trusted


DEPLOYED_COMMIT = "a" * 40
STORE_ID = "omctxlocal_" + "8" * 64
_FORBIDDEN_MODULES = {
    "socket",
    "ssl",
    "http",
    "http.client",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "requests",
    "boto3",
    "botocore",
    "paramiko",
    "subprocess",
    "ftplib",
    "smtplib",
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_private(root: Path, relative: str, body: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    for directory in (root, *path.parents):
        if directory == root or root in directory.parents:
            directory.chmod(0o700)
    path.write_bytes(body)
    path.chmod(0o600)


def _tree_snapshot(root: Path) -> dict[str, tuple[Any, ...]]:
    snapshot: dict[str, tuple[Any, ...]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        metadata = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        common = (
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        if path.is_file():
            snapshot[relative] = (
                "file",
                *common,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        else:
            snapshot[relative] = ("directory", *common)
    return snapshot


def _reference(*, suffix: str = "1") -> dict[str, Any]:
    requested_as_of = "2026-08-12T14:31:00Z"
    payload: dict[str, Any] = {
        "schema": context_bridge.REFERENCE_SCHEMA,
        "reference_id": "",
        "owner": {
            "schema": "options.signal_episode/v1",
            "id": "osep_" + suffix * 24,
            "record_sha256": suffix * 64,
            "ticker": "SPY",
            "event_time": "2026-08-12T14:30:00Z",
            "requested_as_of": requested_as_of,
            "requested_as_of_basis": "durable_available_at",
            "evidence_phase": "decision_time_actual_output",
        },
        "query": {
            "subject": {
                "subject_id": "mmsecurity_" + "2" * 64,
                "instrument_id": "mmsecurity_" + "3" * 64,
            },
            "identity_config_sha256": "4" * 64,
            "event_time": "2026-08-12T14:30:00Z",
            "as_known_at": requested_as_of,
            "mode": "operational_pit",
            "fallback_policy": "exact_no_fallback",
        },
        "disposition": "abstained",
        "reason": "exact_requested_as_of_context_absent",
        "context": None,
        "evidence_policy": dict(context_bridge.EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    payload["reference_id"] = "omctxref_" + hashlib.sha256(
        _canonical_bytes(payload)
    ).hexdigest()
    return context_bridge.validate_context_reference(payload)


def _audit(references: list[dict[str, Any]], *, audited_at: str) -> dict[str, Any]:
    episode_count = sum(
        row["owner"]["schema"] == "options.signal_episode/v1" for row in references
    )
    campaign_count = len(references) - episode_count
    return context_bridge.build_audit_receipt(
        references=references,
        source_artifacts=[
            {
                "path": "config/market_memory_canary.v1.json",
                "sha256": "b" * 64,
                "bytes": 1,
                "record_count": 1,
            },
            {
                "path": "data/options_signal_episode/campaigns.jsonl",
                "sha256": "c" * 64,
                "bytes": 1,
                "record_count": campaign_count,
            },
            {
                "path": "data/options_signal_episode/episodes.jsonl",
                "sha256": "d" * 64,
                "bytes": 1,
                "record_count": episode_count,
            },
            {
                "path": "data/options_signal_episode/outcomes_h60.jsonl",
                "sha256": "e" * 64,
                "bytes": 1,
                "record_count": 0,
            },
        ],
        context_generations=[
            {
                "profile": profile,
                "store_id": "mmstore_" + str(index + 1) * 64,
                "generation_id": "mmgeneration_" + str(index + 3) * 64,
                "generation_sha256": str(index + 5) * 64,
                "capture_count": 0,
            }
            for index, profile in enumerate(
                sorted(
                    {
                        market_memory_pit.STORE_PROFILE,
                        market_memory_trusted.TRUSTED_STORE_PROFILE,
                    }
                )
            )
        ],
        audited_at=audited_at,
    )


def _publish_upstream(
    root: Path,
    *,
    references: list[dict[str, Any]],
    audited_at: str,
) -> dict[str, Any]:
    return upstream_store.publish_receipt_set(
        root,
        deployed_commit=DEPLOYED_COMMIT,
        references=references,
        audit=_audit(references, audited_at=audited_at),
    )


def _provision_destination(root: Path) -> local_receipts.RootIdentity:
    root.mkdir(mode=0o700)
    marker = {
        "schema": local_receipts.ROOT_SCHEMA,
        "store_id": STORE_ID,
        "upstream_head_schema": upstream_store.HEAD_SCHEMA,
        "upstream_reference_set_schema": upstream_store.REFERENCE_SET_SCHEMA,
        "upstream_reference_schema": context_bridge.REFERENCE_SCHEMA,
        "authority": dict(market_memory.AUTHORITY),
    }
    _write_private(root, local_receipts.ROOT_MARKER, _canonical_bytes(marker))
    metadata = root.stat()
    return local_receipts.attest_root(
        root, expected_uid=metadata.st_uid, expected_gid=metadata.st_gid
    )


def _assert_zero_authority(payload: Any) -> None:
    if isinstance(payload, dict):
        if "authority" in payload:
            authority = dict(payload["authority"])
            assert authority == dict(local_receipts.AUTHORITY)
            assert authority["proposal_weight"] == 0
            assert authority["context_only"] is True
            assert all(
                authority[key] is False
                for key in authority
                if key.startswith("may_")
            )
        for value in payload.values():
            _assert_zero_authority(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_zero_authority(item)


@pytest.fixture
def replica_roots(tmp_path: Path) -> dict[str, Any]:
    source = tmp_path / "upstream"
    dest = tmp_path / "local-w1a"
    reference = _reference()
    head = _publish_upstream(
        source, references=[reference], audited_at="2026-08-12T15:00:00Z"
    )
    identity = _provision_destination(dest)
    return {
        "source": source,
        "dest": dest,
        "identity": identity,
        "reference": reference,
        "head": head,
    }


def test_first_publication_replicates_and_w1a_a_accepts(replica_roots: dict[str, Any]) -> None:
    result = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    assert result.unchanged is False
    publication = result.publication
    assert publication.descriptor["sequence"] == 0
    assert publication.descriptor["previous_descriptor_sha256"] is None
    assert publication.head["publication_id"] == replica_roots["head"]["publication_id"]
    exact = local_receipts.read_exact_reference(
        publication,
        owner_schema="options.signal_episode/v1",
        owner_id=replica_roots["reference"]["owner"]["id"],
        requested_as_of=replica_roots["reference"]["owner"]["requested_as_of"],
        source_record_sha256=replica_roots["reference"]["owner"]["record_sha256"],
    )
    assert exact["reference_id"] == replica_roots["reference"]["reference_id"]
    _assert_zero_authority(dict(publication.descriptor))
    _assert_zero_authority(dict(publication.head))
    _assert_zero_authority(dict(publication.audit))
    _assert_zero_authority(list(publication.references))


def test_persisted_upstream_objects_are_byte_identical(replica_roots: dict[str, Any]) -> None:
    replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    source = replica_roots["source"]
    dest = replica_roots["dest"]
    head_body = (source / "HEAD.json").read_bytes()
    head_digest = hashlib.sha256(head_body).hexdigest()
    head = replica_roots["head"]
    assert (dest / "heads" / head_digest[:2] / f"{head_digest}.json").read_bytes() == head_body
    assert (dest / head["audit_object_key"]).read_bytes() == (
        source / head["audit_object_key"]
    ).read_bytes()
    assert (dest / head["reference_set_object_key"]).read_bytes() == (
        source / head["reference_set_object_key"]
    ).read_bytes()


def test_repeat_publication_is_byte_for_byte_and_mtime_noop(
    replica_roots: dict[str, Any],
) -> None:
    replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    before = _tree_snapshot(replica_roots["dest"])
    result = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    assert result.unchanged is True
    assert _tree_snapshot(replica_roots["dest"]) == before


def test_second_publication_appends_and_preserves_generation_zero(
    replica_roots: dict[str, Any],
) -> None:
    first = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    first_id = first.publication.descriptor["publication_id"]
    second_reference = _reference(suffix="2")
    _publish_upstream(
        replica_roots["source"],
        references=[second_reference],
        audited_at="2026-08-12T16:00:00Z",
    )
    second = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
        previous_high_water=first.publication.high_water,
    )
    assert second.unchanged is False
    assert second.publication.descriptor["sequence"] == 1
    assert (
        second.publication.descriptor["previous_descriptor_sha256"]
        == first.publication.high_water["descriptor_sha256"]
    )
    historical = local_receipts.read_publication(
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
        previous_high_water=second.publication.high_water,
        publication_id=first_id,
    )
    assert historical.descriptor["sequence"] == 0
    assert historical.head["publication_id"] == first_id
    assert historical.high_water["descriptor_count"] == 2


def test_older_source_cannot_move_local_head_backward(
    replica_roots: dict[str, Any], tmp_path: Path
) -> None:
    replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    older = tmp_path / "older-upstream"
    _publish_upstream(
        older, references=[_reference(suffix="9")], audited_at="2026-08-12T14:00:00Z"
    )
    _publish_upstream(
        replica_roots["source"],
        references=[_reference(suffix="2")],
        audited_at="2026-08-12T16:00:00Z",
    )
    replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    before = (replica_roots["dest"] / "HEAD.json").read_bytes()
    with pytest.raises(replica.LocalReplicaError, match="backward"):
        replica.replicate_publication(
            older, replica_roots["dest"], expected_root=replica_roots["identity"]
        )
    assert (replica_roots["dest"] / "HEAD.json").read_bytes() == before


def test_conflicting_immutable_bytes_fail_closed(replica_roots: dict[str, Any]) -> None:
    head_body = (replica_roots["source"] / "HEAD.json").read_bytes()
    digest = hashlib.sha256(head_body).hexdigest()
    _write_private(
        replica_roots["dest"],
        f"heads/{digest[:2]}/{digest}.json",
        b'{"schema":"conflict"}',
    )
    with pytest.raises(replica.LocalReplicaError, match="conflicting bytes"):
        replica.replicate_publication(
            replica_roots["source"],
            replica_roots["dest"],
            expected_root=replica_roots["identity"],
        )
    assert not (replica_roots["dest"] / "HEAD.json").exists()


def test_malformed_or_mutated_source_fails_closed(
    replica_roots: dict[str, Any],
) -> None:
    (replica_roots["source"] / "HEAD.json").write_bytes(b"{not-json")
    os.chmod(replica_roots["source"] / "HEAD.json", 0o600)
    with pytest.raises(replica.LocalReplicaError):
        replica.replicate_publication(
            replica_roots["source"],
            replica_roots["dest"],
            expected_root=replica_roots["identity"],
        )
    assert not (replica_roots["dest"] / "HEAD.json").exists()


def test_destination_symlink_hardlink_owner_mode_substitution_fails_closed(
    replica_roots: dict[str, Any], tmp_path: Path
) -> None:
    linked = tmp_path / "linked-dest"
    linked.symlink_to(replica_roots["dest"])
    with pytest.raises(replica.LocalReplicaError):
        replica.replicate_publication(
            replica_roots["source"],
            linked,
            expected_root=replica_roots["identity"],
        )
    replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    head = replica_roots["dest"] / "HEAD.json"
    alias = tmp_path / "head-hardlink"
    os.link(head, alias)
    with pytest.raises(replica.LocalReplicaError):
        replica.replicate_publication(
            replica_roots["source"],
            replica_roots["dest"],
            expected_root=replica_roots["identity"],
        )
    os.unlink(alias)
    os.chmod(replica_roots["dest"], 0o755)
    try:
        with pytest.raises(replica.LocalReplicaError):
            replica.replicate_publication(
                replica_roots["source"],
                replica_roots["dest"],
                expected_root=replica_roots["identity"],
            )
    finally:
        os.chmod(replica_roots["dest"], 0o700)


@pytest.mark.parametrize(
    "point",
    [
        "before_first_immutable",
        "between_immutable",
        "before_descriptor",
        "after_descriptor_before_head",
        "during_head",
    ],
)
def test_crash_before_head_hides_partial_history_and_retry_converges(
    replica_roots: dict[str, Any], point: str
) -> None:
    replica._FAULT = point
    try:
        with pytest.raises(replica.LocalReplicaError, match="injected fault"):
            replica.replicate_publication(
                replica_roots["source"],
                replica_roots["dest"],
                expected_root=replica_roots["identity"],
            )
    finally:
        replica._FAULT = None
    assert not (replica_roots["dest"] / "HEAD.json").exists()
    local_receipts.attest_root(
        replica_roots["dest"],
        expected_uid=replica_roots["identity"].uid,
        expected_gid=replica_roots["identity"].gid,
    )
    with pytest.raises(local_receipts.LocalReceiptError):
        local_receipts.read_publication(
            replica_roots["dest"], expected_root=replica_roots["identity"]
        )
    result = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    assert result.unchanged is False
    assert result.publication.descriptor["sequence"] == 0


def test_crash_before_head_preserves_previous_publication(
    replica_roots: dict[str, Any],
) -> None:
    first = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    _publish_upstream(
        replica_roots["source"],
        references=[_reference(suffix="2")],
        audited_at="2026-08-12T16:00:00Z",
    )
    before = (replica_roots["dest"] / "HEAD.json").read_bytes()
    replica._FAULT = "after_descriptor_before_head"
    try:
        with pytest.raises(replica.LocalReplicaError, match="injected fault"):
            replica.replicate_publication(
                replica_roots["source"],
                replica_roots["dest"],
                expected_root=replica_roots["identity"],
            )
    finally:
        replica._FAULT = None
    assert (replica_roots["dest"] / "HEAD.json").read_bytes() == before
    current = local_receipts.read_publication(
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
        previous_high_water=first.publication.high_water,
    )
    assert current.head["publication_id"] == first.publication.head["publication_id"]
    retry = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
        previous_high_water=first.publication.high_water,
    )
    assert retry.publication.descriptor["sequence"] == 1


def test_concurrent_producers_do_not_fork_descriptor_chain(
    replica_roots: dict[str, Any],
) -> None:
    errors: list[BaseException] = []
    results: list[replica.ReplicaResult] = []
    barrier = threading.Barrier(2)

    def _worker() -> None:
        try:
            barrier.wait(timeout=5)
            results.append(
                replica.replicate_publication(
                    replica_roots["source"],
                    replica_roots["dest"],
                    expected_root=replica_roots["identity"],
                )
            )
        except BaseException as exc:  # noqa: BLE001 - capture for the parent thread
            errors.append(exc)

    workers = [threading.Thread(target=_worker) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
        assert not worker.is_alive()
    assert errors == []
    assert len(results) == 2
    assert sum(item.unchanged for item in results) == 1
    publication = local_receipts.read_publication(
        replica_roots["dest"], expected_root=replica_roots["identity"]
    )
    assert publication.high_water["descriptor_count"] == 1
    assert publication.descriptor["sequence"] == 0
    assert publication.descriptor["previous_descriptor_sha256"] is None


def test_producer_does_not_mutate_source(replica_roots: dict[str, Any]) -> None:
    before = _tree_snapshot(replica_roots["source"])
    replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    assert _tree_snapshot(replica_roots["source"]) == before


def test_producer_has_no_network_or_credential_capability() -> None:
    path = Path("engine/options_market_memory_local_replica.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.add(node.module)
    assert imported.isdisjoint(_FORBIDDEN_MODULES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
            raise AssertionError("replica must not read process environment")
        if isinstance(node, ast.Name) and node.id in {"getenv", "environ"}:
            raise AssertionError("replica must not read process environment")


def test_selector_integration_remains_unarmed() -> None:
    runner = Path("scripts/run_options_sparse_selector.py").read_text(encoding="utf-8")
    assert "W1A_RECEIPT_ROOT: None = None" in runner
    assert "PROPOSALS_ARMED = False" in runner
    core = Path("engine/options_sparse_selector.py").read_text(encoding="utf-8")
    assert "SELECTOR_PROPOSALS_ARMED = False" in core


def test_production_root_is_refused(replica_roots: dict[str, Any]) -> None:
    with pytest.raises(replica.LocalReplicaError, match="production W1A root"):
        replica.replicate_publication(
            replica_roots["source"],
            local_receipts.DEFAULT_STORE_ROOT,
            expected_root=replica_roots["identity"],
        )


def test_authority_surfaces_remain_display_context_only(
    replica_roots: dict[str, Any],
) -> None:
    result = replica.replicate_publication(
        replica_roots["source"],
        replica_roots["dest"],
        expected_root=replica_roots["identity"],
    )
    _assert_zero_authority(json.loads((replica_roots["dest"] / "HEAD.json").read_text()))
    descriptor_key = result.publication.high_water["descriptor_sha256"]
    descriptor_path = (
        replica_roots["dest"]
        / "descriptors"
        / descriptor_key[:2]
        / f"{descriptor_key}.json"
    )
    _assert_zero_authority(json.loads(descriptor_path.read_text()))
    _assert_zero_authority(dict(result.publication.high_water))
    for key, value in dict(local_receipts.AUTHORITY).items():
        if key.startswith("may_"):
            assert value is False
        if key == "proposal_weight":
            assert value == 0
