import copy
import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from engine import options_market_memory_context as context_bridge
from engine import options_market_memory_local_receipts as local_receipts
from engine import options_market_memory_receipt_store as upstream_store
from engine import options_sparse_selector
from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_pit
from engine.neuralweb import market_memory_trusted


DEPLOYED_COMMIT = "a" * 40
STORE_ID = "omctxlocal_" + "9" * 64


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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
            snapshot[relative] = ("file", *common, hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            snapshot[relative] = ("directory", *common)
    return snapshot


def _attest(root: Path) -> local_receipts.RootIdentity:
    metadata = root.stat()
    return local_receipts.attest_root(
        root, expected_uid=metadata.st_uid, expected_gid=metadata.st_gid
    )


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
        row["owner"]["schema"] == "options.signal_episode/v1"
        for row in references
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


def _append_publication(
    local_root: Path,
    upstream_root: Path,
    *,
    sequence: int,
    previous_descriptor_sha256: str | None,
    references: list[dict[str, Any]],
    audited_at: str,
) -> tuple[dict[str, Any], str]:
    upstream_head = upstream_store.publish_receipt_set(
        upstream_root,
        deployed_commit=DEPLOYED_COMMIT,
        references=references,
        audit=_audit(references, audited_at=audited_at),
    )
    upstream_head_body = _canonical_bytes(upstream_head)
    upstream_head_sha256 = hashlib.sha256(upstream_head_body).hexdigest()
    upstream_head_key = (
        f"heads/{upstream_head_sha256[:2]}/{upstream_head_sha256}.json"
    )
    _write_private(local_root, upstream_head_key, upstream_head_body)
    for key in (
        upstream_head["audit_object_key"],
        upstream_head["reference_set_object_key"],
    ):
        _write_private(local_root, key, (upstream_root / key).read_bytes())

    descriptor = {
        "schema": local_receipts.DESCRIPTOR_SCHEMA,
        "sequence": sequence,
        "previous_descriptor_sha256": previous_descriptor_sha256,
        "publication_id": upstream_head["publication_id"],
        "published_at": upstream_head["published_at"],
        "deployed_commit": upstream_head["deployed_commit"],
        "upstream_head_sha256": upstream_head_sha256,
        "upstream_head_object_key": upstream_head_key,
        "audit_id": upstream_head["audit_id"],
        "audit_sha256": upstream_head["audit_sha256"],
        "audit_object_key": upstream_head["audit_object_key"],
        "reference_set_sha256": upstream_head["reference_set_sha256"],
        "reference_set_object_sha256": upstream_head[
            "reference_set_object_sha256"
        ],
        "reference_set_object_key": upstream_head["reference_set_object_key"],
        "reference_count": upstream_head["reference_count"],
        "evidence_policy": copy.deepcopy(upstream_head["evidence_policy"]),
        "authority": copy.deepcopy(upstream_head["authority"]),
    }
    descriptor_body = _canonical_bytes(descriptor)
    descriptor_sha256 = hashlib.sha256(descriptor_body).hexdigest()
    descriptor_key = (
        f"descriptors/{descriptor_sha256[:2]}/{descriptor_sha256}.json"
    )
    _write_private(local_root, descriptor_key, descriptor_body)
    local_head = {
        "schema": local_receipts.HEAD_SCHEMA,
        "store_id": STORE_ID,
        "descriptor_count": sequence + 1,
        "current_descriptor_sha256": descriptor_sha256,
        "current_descriptor_object_key": descriptor_key,
        "current_publication_id": upstream_head["publication_id"],
        "current_published_at": upstream_head["published_at"],
        "authority": copy.deepcopy(upstream_head["authority"]),
    }
    _write_private(local_root, "HEAD.json", _canonical_bytes(local_head))
    return upstream_head, descriptor_sha256


@pytest.fixture
def receipt_store(tmp_path: Path) -> dict[str, Any]:
    local_root = tmp_path / "local-w1a"
    local_root.mkdir(mode=0o700)
    marker = {
        "schema": local_receipts.ROOT_SCHEMA,
        "store_id": STORE_ID,
        "upstream_head_schema": upstream_store.HEAD_SCHEMA,
        "upstream_reference_set_schema": upstream_store.REFERENCE_SET_SCHEMA,
        "upstream_reference_schema": context_bridge.REFERENCE_SCHEMA,
        "authority": dict(market_memory.AUTHORITY),
    }
    _write_private(local_root, local_receipts.ROOT_MARKER, _canonical_bytes(marker))
    upstream_root = tmp_path / "upstream"
    reference = _reference()
    head, descriptor_sha256 = _append_publication(
        local_root,
        upstream_root,
        sequence=0,
        previous_descriptor_sha256=None,
        references=[reference],
        audited_at="2026-08-12T15:00:00Z",
    )
    return {
        "local_root": local_root,
        "upstream_root": upstream_root,
        "reference": reference,
        "head": head,
        "descriptor_sha256": descriptor_sha256,
    }


def test_w1a_local_receipt_contract_is_versioned() -> None:
    assert (
        local_receipts.HEAD_SCHEMA
        == "options.market_memory_context_local_receipt_head/v1"
    )
    assert (
        local_receipts.DESCRIPTOR_SCHEMA
        == "options.market_memory_context_local_publication_descriptor/v1"
    )


def test_valid_historical_receipt_reads_with_exact_as_of_and_source_binding(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    reference = receipt_store["reference"]
    identity = _attest(root)
    publication = local_receipts.read_publication(
        root,
        expected_root=identity,
        publication_id=receipt_store["head"]["publication_id"],
    )
    assert publication.head == receipt_store["head"]
    assert publication.references == (reference,)
    assert publication.high_water["sequence"] == 0
    assert publication.high_water["descriptor_sha256"] == receipt_store[
        "descriptor_sha256"
    ]

    bound = local_receipts.read_exact_reference(
        publication,
        owner_schema=reference["owner"]["schema"],
        owner_id=reference["owner"]["id"],
        requested_as_of=reference["owner"]["requested_as_of"],
        source_record_sha256=reference["owner"]["record_sha256"],
    )
    assert bound == reference

    with pytest.raises(local_receipts.LocalReceiptError, match="requested-as-of"):
        local_receipts.read_exact_reference(
            publication,
            owner_schema=reference["owner"]["schema"],
            owner_id=reference["owner"]["id"],
            requested_as_of="2026-08-12T14:31:01Z",
            source_record_sha256=reference["owner"]["record_sha256"],
        )
    with pytest.raises(local_receipts.LocalReceiptError, match="source hash"):
        local_receipts.read_exact_reference(
            publication,
            owner_schema=reference["owner"]["schema"],
            owner_id=reference["owner"]["id"],
            requested_as_of=reference["owner"]["requested_as_of"],
            source_record_sha256="f" * 64,
        )


def test_advancing_current_head_preserves_historical_identity_and_high_water(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    first = local_receipts.read_publication(root, expected_root=identity)
    first_head_bytes = (root / first.descriptor["upstream_head_object_key"]).read_bytes()

    second_head, _second_descriptor = _append_publication(
        root,
        receipt_store["upstream_root"],
        sequence=1,
        previous_descriptor_sha256=receipt_store["descriptor_sha256"],
        references=[_reference(suffix="5")],
        audited_at="2026-08-12T15:05:00Z",
    )
    historical = local_receipts.read_publication(
        root,
        expected_root=identity,
        previous_high_water=first.high_water,
        publication_id=first.head["publication_id"],
    )
    assert historical.head == first.head
    assert (root / historical.descriptor["upstream_head_object_key"]).read_bytes() == (
        first_head_bytes
    )
    assert historical.high_water["sequence"] == 1
    assert historical.high_water["publication_id"] == second_head["publication_id"]


def test_lower_publication_high_water_is_refused(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    old_local_head = (root / "HEAD.json").read_bytes()
    _append_publication(
        root,
        receipt_store["upstream_root"],
        sequence=1,
        previous_descriptor_sha256=receipt_store["descriptor_sha256"],
        references=[_reference(suffix="5")],
        audited_at="2026-08-12T15:05:00Z",
    )
    advanced = local_receipts.read_publication(root, expected_root=identity)
    _write_private(root, "HEAD.json", old_local_head)
    with pytest.raises(local_receipts.LocalReceiptError, match="rolled back"):
        local_receipts.read_publication(
            root,
            expected_root=identity,
            previous_high_water=advanced.high_water,
        )


@pytest.mark.parametrize(
    "key_field",
    ["upstream_head_object_key", "audit_object_key", "reference_set_object_key"],
)
def test_changed_historical_objects_are_refused(
    receipt_store: dict[str, Any], key_field: str
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    key = publication.descriptor[key_field]
    changed = _read_json(root / key)
    if key_field == "upstream_head_object_key":
        changed["deployed_commit"] = "b" * 40
    elif key_field == "audit_object_key":
        changed["source_artifacts"][0]["sha256"] = "f" * 64
    else:
        changed["reference_count"] = 0
    _write_private(root, key, _canonical_bytes(changed))
    with pytest.raises(local_receipts.LocalReceiptError, match="rewritten"):
        local_receipts.read_publication(root, expected_root=identity)


@pytest.mark.parametrize(
    "key_field",
    ["upstream_head_object_key", "audit_object_key", "reference_set_object_key"],
)
def test_missing_historical_objects_are_refused(
    receipt_store: dict[str, Any], key_field: str
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    (root / publication.descriptor[key_field]).unlink()
    with pytest.raises(local_receipts.LocalReceiptError, match="missing"):
        local_receipts.read_publication(root, expected_root=identity)


def test_omitted_publication_descriptor_is_refused(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    _append_publication(
        root,
        receipt_store["upstream_root"],
        sequence=1,
        previous_descriptor_sha256=receipt_store["descriptor_sha256"],
        references=[_reference(suffix="5")],
        audited_at="2026-08-12T15:05:00Z",
    )
    first_key = (
        f"descriptors/{receipt_store['descriptor_sha256'][:2]}/"
        f"{receipt_store['descriptor_sha256']}.json"
    )
    (root / first_key).unlink()
    with pytest.raises(local_receipts.LocalReceiptError, match="missing"):
        local_receipts.read_publication(root, expected_root=identity)


def test_symlink_substitution_is_refused(receipt_store: dict[str, Any]) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    target = root / publication.descriptor["reference_set_object_key"]
    outside = root.parent / "substitute-reference-set.json"
    outside.write_bytes(target.read_bytes())
    outside.chmod(0o600)
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(local_receipts.LocalReceiptError, match="symlink"):
        local_receipts.read_publication(root, expected_root=identity)


def test_root_substitution_is_refused(receipt_store: dict[str, Any]) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    original = root.with_name("original-local-w1a")
    root.rename(original)
    shutil.copytree(original, root, copy_function=shutil.copy2)
    with pytest.raises(local_receipts.LocalReceiptError, match="root was substituted"):
        local_receipts.read_publication(root, expected_root=identity)


def test_private_root_and_object_modes_are_exact(receipt_store: dict[str, Any]) -> None:
    root = receipt_store["local_root"]
    metadata = root.stat()
    with pytest.raises(local_receipts.LocalReceiptError, match="owner"):
        local_receipts.attest_root(
            root,
            expected_uid=metadata.st_uid + 1,
            expected_gid=metadata.st_gid,
        )
    root.chmod(0o755)
    with pytest.raises(local_receipts.LocalReceiptError, match="0700"):
        _attest(root)
    root.chmod(0o700)
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    (root / publication.descriptor["audit_object_key"]).chmod(0o644)
    with pytest.raises(local_receipts.LocalReceiptError, match="0600"):
        local_receipts.read_publication(root, expected_root=identity)


def test_hardlink_substitution_is_refused(receipt_store: dict[str, Any]) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    target = root / publication.descriptor["audit_object_key"]
    second_name = target.with_name("hardlink.json")
    os.link(target, second_name)
    with pytest.raises(local_receipts.LocalReceiptError, match="single-link"):
        local_receipts.read_publication(root, expected_root=identity)


def test_hardlink_added_during_read_is_refused(
    receipt_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    real_read = os.read
    linked = False

    def add_link_after_read(descriptor: int, size: int) -> bytes:
        nonlocal linked
        body = real_read(descriptor, size)
        if not linked:
            os.link(root / local_receipts.ROOT_MARKER, root / "marker-hardlink.json")
            linked = True
        return body

    monkeypatch.setattr(local_receipts.os, "read", add_link_after_read)
    with pytest.raises(local_receipts.LocalReceiptError, match="single-link"):
        local_receipts.read_publication(root, expected_root=identity)


def _json_copy(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_copy(item) for item in value]
    return copy.deepcopy(value)


def _restore_private_modes(root: Path) -> None:
    for path in (root, *sorted(root.rglob("*"))):
        path.chmod(0o700 if path.is_dir() else 0o600)


def test_rename_and_replace_of_immutable_object_is_refused(
    receipt_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    key = publication.descriptor["audit_object_key"]
    target = root / key
    original = target.stat()
    real_read = os.read
    replaced = False

    def replace_after_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        body = real_read(descriptor, size)
        if replaced:
            return body
        try:
            metadata = os.fstat(descriptor)
        except OSError:
            return body
        if (metadata.st_dev, metadata.st_ino) != (original.st_dev, original.st_ino):
            return body
        relocated = target.with_name("relocated-audit.json")
        target.rename(relocated)
        _write_private(root, key, relocated.read_bytes())
        replaced = True
        return body

    monkeypatch.setattr(local_receipts.os, "read", replace_after_read)
    with pytest.raises(local_receipts.LocalReceiptError, match="path identity"):
        local_receipts.read_publication(root, expected_root=identity)


def test_rename_and_replace_of_root_is_refused(
    receipt_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    real_read = os.read
    replaced = False

    def replace_root_after_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        body = real_read(descriptor, size)
        if replaced:
            return body
        original = root.with_name("original-local-w1a")
        root.rename(original)
        shutil.copytree(original, root, copy_function=shutil.copy2)
        _restore_private_modes(root)
        replaced = True
        return body

    monkeypatch.setattr(local_receipts.os, "read", replace_root_after_read)
    with pytest.raises(
        local_receipts.LocalReceiptError,
        match="no longer resolves to the attested directory",
    ):
        local_receipts.read_publication(root, expected_root=identity)


@pytest.mark.parametrize("mutation", ["malformed", "conflicting"])
def test_malformed_or_conflicting_local_head_is_refused(
    receipt_store: dict[str, Any], mutation: str
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    head = _read_json(root / "HEAD.json")
    if mutation == "malformed":
        head["unreviewed_field"] = True
        expected = "fields are not canonical"
    else:
        head["current_publication_id"] = "omctxpub_" + "f" * 64
        expected = "conflicts"
    _write_private(root, "HEAD.json", _canonical_bytes(head))
    with pytest.raises(local_receipts.LocalReceiptError, match=expected):
        local_receipts.read_publication(root, expected_root=identity)


def test_verifier_performs_no_mutation_and_all_authority_remains_false(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    before = _tree_snapshot(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    after = _tree_snapshot(root)
    assert after == before

    authority_surfaces = [
        publication.descriptor["authority"],
        publication.head["authority"],
        publication.audit["authority"],
        *(reference["authority"] for reference in publication.references),
    ]
    pinned_authority = dict(local_receipts.AUTHORITY)
    assert pinned_authority == dict(market_memory.AUTHORITY)
    assert all(surface == pinned_authority for surface in authority_surfaces)
    assert all(
        value is False
        for surface in authority_surfaces
        for key, value in surface.items()
        if key.startswith("may_")
    )
    assert all(surface["proposal_weight"] == 0 for surface in authority_surfaces)
    assert options_sparse_selector.SELECTOR_PROPOSALS_ARMED is False
    assert "publish" not in local_receipts.__all__


def test_local_contract_schema_validates_every_persisted_object(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    schema_root = Path(__file__).resolve().parents[1] / "contracts/options"
    schema = _read_json(
        schema_root / "options.market_memory_context_local_receipt_store.v1.schema.json"
    )
    upstream_reference_schema = _read_json(
        schema_root / "options.market_memory_context_reference.v1.schema.json"
    )
    Draft202012Validator.check_schema(schema)
    registry = Registry().with_resource(
        upstream_reference_schema["$id"], Resource.from_contents(upstream_reference_schema)
    )
    validator = Draft202012Validator(schema, registry=registry)
    descriptor_key = (
        f"descriptors/{receipt_store['descriptor_sha256'][:2]}/"
        f"{receipt_store['descriptor_sha256']}.json"
    )
    for value in (
        _read_json(root / local_receipts.ROOT_MARKER),
        _read_json(root / "HEAD.json"),
        _read_json(root / descriptor_key),
        _json_copy(publication.high_water),
    ):
        validator.validate(value)
    fractional = _read_json(root / "HEAD.json")
    fractional["current_published_at"] = "2026-08-12T15:00:00.1Z"
    assert not validator.is_valid(fractional)


def test_returned_publication_is_recursively_immutable(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    publication = local_receipts.read_publication(root, expected_root=identity)
    with pytest.raises(TypeError):
        publication.high_water["sequence"] = 99  # type: ignore[index]
    with pytest.raises(TypeError):
        publication.descriptor["reference_count"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        publication.head["authority"]["may_trade"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        publication.audit["source_artifacts"][0]["sha256"] = "f" * 64  # type: ignore[index]
    with pytest.raises(TypeError):
        publication.references[0]["owner"]["record_sha256"] = "f" * 64  # type: ignore[index]
    bound = local_receipts.read_exact_reference(
        publication,
        owner_schema=receipt_store["reference"]["owner"]["schema"],
        owner_id=receipt_store["reference"]["owner"]["id"],
        requested_as_of=receipt_store["reference"]["owner"]["requested_as_of"],
        source_record_sha256=receipt_store["reference"]["owner"]["record_sha256"],
    )
    with pytest.raises(TypeError):
        bound["owner"]["record_sha256"] = "f" * 64  # type: ignore[index]


def test_caller_constructed_and_mutated_publications_are_not_authenticated(
    receipt_store: dict[str, Any],
) -> None:
    root = receipt_store["local_root"]
    identity = _attest(root)
    authentic = local_receipts.read_publication(root, expected_root=identity)
    reference = receipt_store["reference"]
    exact_kwargs = {
        "owner_schema": reference["owner"]["schema"],
        "owner_id": reference["owner"]["id"],
        "requested_as_of": reference["owner"]["requested_as_of"],
        "source_record_sha256": reference["owner"]["record_sha256"],
    }

    forged_row = _json_copy(authentic.references[0])
    forged_row["owner"]["record_sha256"] = "f" * 64
    forged = local_receipts.VerifiedPublication(
        root_identity=authentic.root_identity,
        high_water=_json_copy(authentic.high_water),
        descriptor=_json_copy(authentic.descriptor),
        head=_json_copy(authentic.head),
        audit=_json_copy(authentic.audit),
        references=(forged_row,),
    )
    assert type(forged) is local_receipts.VerifiedPublication
    with pytest.raises(
        local_receipts.LocalReceiptError,
        match="authenticated historical publication",
    ):
        local_receipts.read_exact_reference(
            forged,
            owner_schema=forged_row["owner"]["schema"],
            owner_id=forged_row["owner"]["id"],
            requested_as_of=forged_row["owner"]["requested_as_of"],
            source_record_sha256="f" * 64,
        )

    consistent = local_receipts.VerifiedPublication(
        root_identity=authentic.root_identity,
        high_water=_json_copy(authentic.high_water),
        descriptor=_json_copy(authentic.descriptor),
        head=_json_copy(authentic.head),
        audit=_json_copy(authentic.audit),
        references=tuple(_json_copy(row) for row in authentic.references),
    )
    with pytest.raises(
        local_receipts.LocalReceiptError,
        match="authenticated historical publication",
    ):
        local_receipts.read_exact_reference(consistent, **exact_kwargs)

    replaced = replace(
        authentic,
        references=(forged_row,),
    )
    with pytest.raises(
        local_receipts.LocalReceiptError,
        match="authenticated historical publication",
    ):
        local_receipts.read_exact_reference(
            replaced,
            owner_schema=forged_row["owner"]["schema"],
            owner_id=forged_row["owner"]["id"],
            requested_as_of=forged_row["owner"]["requested_as_of"],
            source_record_sha256="f" * 64,
        )

    bound = local_receipts.read_exact_reference(authentic, **exact_kwargs)
    assert bound == reference
