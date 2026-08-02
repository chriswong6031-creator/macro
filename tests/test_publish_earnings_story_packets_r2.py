from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from engine.earnings_narrative.contracts import canonical_json_bytes, sha256_bytes
from scripts import publish_earnings_story_packets_r2 as publisher


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


class _FakeR2:
    def __init__(self, *, marker: dict | None = None, marker_etag: str = "prior", race_marker: bool = False) -> None:
        self.marker = marker
        self.marker_body = canonical_json_bytes(marker) if marker is not None else None
        self.marker_etag = marker_etag
        self.race_marker = race_marker
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.puts: list[tuple[str, dict]] = []
        self.fail_commit_once = False

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key == f"{publisher.PREFIX}/manifest.json" and self.marker_body is not None:
            return {"Body": io.BytesIO(self.marker_body), "ETag": self.marker_etag}
        if Key in self.objects:
            return {"Body": io.BytesIO(self.objects[Key])}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key in self.objects:
            return {"ContentLength": len(self.objects[Key]), "Metadata": self.metadata.get(Key, {})}
        raise RuntimeError("missing")

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):  # noqa: N803
        assert ContinuationToken is None
        return {
            "IsTruncated": False,
            "Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)],
        }

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if self.fail_commit_once and key.startswith(f"{publisher.JOURNAL_PREFIX}/commits/"):
            self.fail_commit_once = False
            raise RuntimeError("commit receipt transport failed")
        if key == f"{publisher.PREFIX}/manifest.json" and self.race_marker:
            raise _PreconditionFailed()
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _PreconditionFailed()
        self.puts.append((key, kwargs))
        self.objects[key] = kwargs["Body"]
        self.metadata[key] = dict(kwargs.get("Metadata") or {})
        if key == f"{publisher.PREFIX}/manifest.json":
            self.marker_body = kwargs["Body"]
            self.marker = json.loads(kwargs["Body"].decode("utf-8"))


def _manifest_is_valid(payload: object) -> None:
    if not isinstance(payload, dict):
        raise ValueError("manifest must be object")
    required = {"schema", "generation_id", "parent_generation_id", "status", "packets", "files"}
    if set(payload) != required or payload["schema"] != "earnings.story_packet_catalog/v1":
        raise ValueError("manifest fields")
    if payload["status"] != "ready" or not isinstance(payload["packets"], dict) or not payload["packets"]:
        raise ValueError("manifest catalog")
    if not isinstance(payload["files"], dict) or not payload["files"]:
        raise ValueError("manifest files")


def _verify_store(out_dir: Path, *, manifest: dict) -> dict[str, int | str]:
    _manifest_is_valid(manifest)
    root = Path(out_dir)
    if (root / "manifest.json").read_bytes() != canonical_json_bytes(manifest):
        raise ValueError("root receipt")
    if (root / "generations" / manifest["generation_id"] / "manifest.json").read_bytes() != canonical_json_bytes(manifest):
        raise ValueError("generation receipt")
    for receipt in manifest["files"].values():
        body = (root / receipt["object_key"]).read_bytes()
        if len(body) != receipt["bytes"] or sha256_bytes(body) != receipt["sha256"]:
            raise ValueError("object receipt")
    return {"status": "ready", "packet_count": len(manifest["packets"])}


@pytest.fixture(autouse=True)
def _projection_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publisher, "_story_contracts", lambda: (_manifest_is_valid, _verify_store))
    monkeypatch.setattr(publisher, "_audit_bound_evidence", lambda *args, **kwargs: None)


def _write_tree(
    root: Path,
    *,
    generation: str = "packet_one",
    parent: str | None = None,
    packets: tuple[str, ...] = ("earnings:AAPL/2026Q1",),
) -> dict:
    files: dict[str, dict] = {}
    for packet in packets:
        body = canonical_json_bytes({"packet": packet, "generation": generation})
        digest = sha256_bytes(body)
        object_key = f"objects/{digest}.json"
        path = root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        files[f"packets/{packet}.json"] = {"object_key": object_key, "sha256": digest, "bytes": len(body)}
    manifest = {
        "schema": "earnings.story_packet_catalog/v1",
        "generation_id": generation,
        "parent_generation_id": parent,
        "status": "ready",
        "packets": {packet: {"object": f"packets/{packet}.json"} for packet in packets},
        "files": files,
    }
    (root / "generations" / generation).mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    (root / "generations" / generation / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


def _legacy_root_without_journal(tmp_path: Path) -> tuple[dict, _FakeR2]:
    """Publish a valid historical root, then remove only its journal anchor."""
    manifest = _write_tree(tmp_path, generation="a" * 32)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    for key in list(fake.objects):
        if key.startswith(f"{publisher.JOURNAL_PREFIX}/"):
            del fake.objects[key]
            fake.metadata.pop(key, None)
    fake.puts.clear()
    return manifest, fake


def test_r2_uploads_immutable_objects_then_generation_then_root(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _kwargs in fake.puts]
    assert keys[-3:] == [
        f"{publisher.PREFIX}/generations/{manifest['generation_id']}/manifest.json",
        publisher._journal_key("anchors", manifest["generation_id"]),
        f"{publisher.PREFIX}/manifest.json",
    ]
    assert set(keys[:-3]) == {f"{publisher.PREFIX}/{row['object_key']}" for row in manifest["files"].values()}
    assert fake.puts[-1][1]["IfNoneMatch"] == "*"
    assert fake.puts[-1][1]["Metadata"]["generation-id"] == manifest["generation_id"]


def test_existing_immutable_collision_cannot_advance_root(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    receipt = next(iter(manifest["files"].values()))
    key = f"{publisher.PREFIX}/{receipt['object_key']}"
    fake = _FakeR2()
    fake.objects[key] = b"forged collision"
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert f"{publisher.PREFIX}/manifest.json" not in [key for key, _kwargs in fake.puts]


def test_marker_compare_and_swap_loss_is_safe_and_reported(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    assert publisher.publish(tmp_path, s3=_FakeR2(race_marker=True), bucket="bucket") == publisher.PUBLISH_CONFLICT


def test_first_root_cas_loss_allows_an_exact_retry(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2(race_marker=True)

    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    assert fake.marker is None
    assert publisher._journal_key("anchors", manifest["generation_id"]) in fake.objects

    fake.race_marker = False
    fake.puts.clear()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert fake.marker == manifest
    assert [key for key, _kwargs in fake.puts] == [f"{publisher.PREFIX}/manifest.json"]


def test_concurrent_first_root_candidate_cannot_create_a_second_anchor(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    first = _write_tree(first_dir, generation="a" * 32)
    sibling_dir = tmp_path / "sibling"
    sibling = _write_tree(sibling_dir, generation="b" * 32)

    class _InterleavingR2(_FakeR2):
        def __init__(self) -> None:
            super().__init__()
            self.interleaved = False
            self.sibling_result: int | None = None

        def put_object(self, **kwargs):
            if kwargs["Key"] == publisher.JOURNAL_ANCHOR_KEY and not self.interleaved:
                self.interleaved = True
                self.sibling_result = publisher.publish(sibling_dir, s3=self, bucket="bucket")
            return super().put_object(**kwargs)

    fake = _InterleavingR2()
    assert publisher.publish(first_dir, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    assert fake.sibling_result == 0
    assert fake.marker == sibling
    assert fake.marker != first
    journal_keys = [key for key in fake.objects if key.startswith(f"{publisher.JOURNAL_PREFIX}/")]
    assert journal_keys == [publisher.JOURNAL_ANCHOR_KEY]
    assert publisher.audit_remote_generation(s3=fake, bucket="bucket")["status"] == "ready"


def test_existing_root_without_journal_fails_closed_before_any_write(tmp_path: Path) -> None:
    _manifest, fake = _legacy_root_without_journal(tmp_path)

    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert fake.puts == []


def test_initialize_publication_journal_anchors_exact_legacy_root(tmp_path: Path) -> None:
    manifest, fake = _legacy_root_without_journal(tmp_path)
    expected_sha256 = sha256_bytes(canonical_json_bytes(manifest))

    assert publisher.initialize_publication_journal(
        expected_generation_id=manifest["generation_id"],
        expected_manifest_sha256=expected_sha256,
        s3=fake,
        bucket="bucket",
    ) == {"status": "ready", "packet_count": 1, "journal": "initialized"}
    anchor_key = publisher._journal_key("anchors", manifest["generation_id"])
    assert json.loads(fake.objects[anchor_key].decode("utf-8")) == {
        "schema": publisher.ANCHOR_SCHEMA,
        "generation_id": manifest["generation_id"],
        "generation_manifest_sha256": expected_sha256,
    }


@pytest.mark.parametrize(
    ("expected_generation_id", "expected_manifest_sha256"),
    [
        ("b" * 32, None),
        (None, "0" * 64),
    ],
)
def test_initialize_publication_journal_rejects_wrong_expected_anchor_without_writing(
    tmp_path: Path,
    expected_generation_id: str | None,
    expected_manifest_sha256: str | None,
) -> None:
    manifest, fake = _legacy_root_without_journal(tmp_path)
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="differs from requested journal anchor"):
        publisher.initialize_publication_journal(
            expected_generation_id=expected_generation_id or manifest["generation_id"],
            expected_manifest_sha256=expected_manifest_sha256 or sha256_bytes(canonical_json_bytes(manifest)),
            s3=fake,
            bucket="bucket",
        )
    assert fake.puts == []
    assert not any(key.startswith(f"{publisher.JOURNAL_PREFIX}/") for key in fake.objects)


def test_initialize_publication_journal_is_idempotent_for_exact_repeat(tmp_path: Path) -> None:
    manifest, fake = _legacy_root_without_journal(tmp_path)
    expected_sha256 = sha256_bytes(canonical_json_bytes(manifest))
    args = {
        "expected_generation_id": manifest["generation_id"],
        "expected_manifest_sha256": expected_sha256,
        "s3": fake,
        "bucket": "bucket",
    }

    assert publisher.initialize_publication_journal(**args)["journal"] == "initialized"
    fake.puts.clear()
    assert publisher.initialize_publication_journal(**args)["journal"] == "already_initialized"
    assert fake.puts == []


def test_exact_candidate_retry_recovers_a_stranded_root_cas(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0

    next_dir = tmp_path / "next"
    _write_tree(
        next_dir,
        generation="packet_two",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"),
    )
    fake.race_marker = True
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    transition_key = publisher._journal_key("transitions", base["generation_id"])
    assert transition_key in fake.objects
    assert publisher._journal_key("commits", "packet_two") not in fake.objects
    assert fake.marker == base

    fake.race_marker = False
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == 0
    assert fake.marker["generation_id"] == "packet_two"
    assert publisher._journal_key("commits", "packet_two") in fake.objects
    assert publisher.audit_remote_generation(s3=fake, bucket="bucket")["status"] == "ready"


def test_retry_repairs_commit_after_root_cas_succeeded(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    next_dir = tmp_path / "next"
    current = _write_tree(
        next_dir,
        generation="packet_two",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"),
    )
    fake.fail_commit_once = True
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == 1
    assert fake.marker == current
    assert publisher._journal_key("commits", "packet_two") not in fake.objects
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="unresolved"):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")

    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == 0
    assert publisher._journal_key("commits", "packet_two") in fake.objects
    assert publisher.audit_remote_generation(s3=fake, bucket="bucket")["status"] == "ready"


def test_parent_reservation_rejects_a_concurrent_sibling_then_allows_winner_retry(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0

    winner_dir = tmp_path / "winner"
    _write_tree(
        winner_dir,
        generation="packet_two",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"),
    )
    sibling_dir = tmp_path / "sibling"
    _write_tree(
        sibling_dir,
        generation="packet_sibling",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:NVDA/2026Q1"),
    )
    fake.race_marker = True
    assert publisher.publish(winner_dir, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    fake.race_marker = False
    assert publisher.publish(sibling_dir, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    assert fake.marker == base
    assert publisher.publish(winner_dir, s3=fake, bucket="bucket") == 0
    assert fake.marker["generation_id"] == "packet_two"


def test_first_publish_requires_list_permission_before_any_write(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    fake = _FakeR2()

    class _NoList:
        def get_object(self, **kwargs):
            return fake.get_object(**kwargs)

        def head_object(self, **kwargs):
            return fake.head_object(**kwargs)

        def put_object(self, **kwargs):
            return fake.put_object(**kwargs)

        def list_objects_v2(self, **_kwargs):
            raise PermissionError("list denied")

    assert publisher.publish(tmp_path, s3=_NoList(), bucket="bucket") == 1
    assert fake.puts == []


def test_existing_root_without_etag_fails_before_journal_or_generation_write(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2(marker=manifest, marker_etag="")
    fake.objects[
        f"{publisher.PREFIX}/generations/{manifest['generation_id']}/manifest.json"
    ] = canonical_json_bytes(manifest)
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 1
    assert fake.puts == []


def test_journal_listing_follows_every_page_exactly_once() -> None:
    prefix = f"{publisher.JOURNAL_PREFIX}/"

    class _Pages:
        def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):  # noqa: N803
            assert Prefix == prefix
            pages = {
                None: {"IsTruncated": True, "NextContinuationToken": "p2", "Contents": [{"Key": prefix + "a"}]},
                "p2": {"IsTruncated": True, "NextContinuationToken": "p3", "Contents": [{"Key": prefix + "b"}]},
                "p3": {"IsTruncated": False, "Contents": [{"Key": prefix + "c"}]},
            }
            return pages[ContinuationToken]

    assert publisher._listed_keys(_Pages(), "bucket", prefix=prefix) == [
        prefix + "a", prefix + "b", prefix + "c",
    ]


@pytest.mark.parametrize(
    "pages",
    [
        {None: {"Contents": []}},
        {None: {"IsTruncated": "false", "Contents": []}},
        {None: {"IsTruncated": True, "Contents": []}},
        {None: {"IsTruncated": False, "NextContinuationToken": "extra", "Contents": []}},
        {
            None: {"IsTruncated": True, "NextContinuationToken": "again", "Contents": [{"Key": "P/a"}]},
            "again": {"IsTruncated": True, "NextContinuationToken": "again", "Contents": [{"Key": "P/b"}]},
        },
        {
            None: {"IsTruncated": True, "NextContinuationToken": "p2", "Contents": [{"Key": "P/a"}]},
            "p2": {"IsTruncated": False, "Contents": [{"Key": "P/a"}]},
        },
    ],
)
def test_journal_listing_rejects_ambiguous_pagination(pages: dict) -> None:
    class _Pages:
        def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):  # noqa: N803
            return pages[ContinuationToken]

    with pytest.raises(publisher.ImmutableAddressIntegrityError):
        publisher._listed_keys(_Pages(), "bucket", prefix="P/")


def test_publication_journal_rejects_candidate_keyed_legacy_anchor(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path, generation="a" * 32)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    second_generation = "b" * 32
    fake.objects[f"{publisher.JOURNAL_PREFIX}/anchors/{second_generation}.json"] = canonical_json_bytes({
        "schema": publisher.ANCHOR_SCHEMA,
        "generation_id": second_generation,
        "generation_manifest_sha256": "0" * 64,
    })

    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="unexpected publication journal object"):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_publication_journal_rejects_commit_without_transition(tmp_path: Path) -> None:
    _write_tree(tmp_path, generation="a" * 32)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    orphan_generation = "b" * 32
    fake.objects[publisher._journal_key("commits", orphan_generation)] = canonical_json_bytes({
        "schema": publisher.COMMIT_SCHEMA,
        "generation_id": orphan_generation,
        "transition_sha256": "0" * 64,
    })

    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="lacks its exact transition"):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_publication_journal_rejects_unexpected_nested_key(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path, generation="a" * 32)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    fake.objects[
        f"{publisher.JOURNAL_PREFIX}/anchors/{manifest['generation_id']}/unexpected.json"
    ] = canonical_json_bytes({"unexpected": True})

    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="unexpected publication journal object"):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_absent_credentials_is_deliberate_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_tree(tmp_path)
    monkeypatch.setattr(publisher, "_client", lambda: None)
    assert publisher.publish(tmp_path) == 0


def test_stale_parent_cannot_replace_current_catalog(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    next_dir = tmp_path / "next"
    _write_tree(next_dir, generation="packet_two", parent="some_other_parent", packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"))
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == publisher.PUBLISH_CONFLICT
    assert fake.marker == base


def test_ready_root_may_not_shrink_packet_catalog(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir, packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"))
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    shrink_dir = tmp_path / "shrink"
    _write_tree(shrink_dir, generation="packet_two", parent=base["generation_id"])
    assert publisher.publish(shrink_dir, s3=fake, bucket="bucket") == 1
    assert fake.marker == base


def test_unchanged_root_is_a_true_noop_and_public_audit_replays_every_receipt(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    fake.puts.clear()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    assert fake.puts == []
    health = publisher.audit_remote_generation(s3=fake, bucket="bucket")
    assert health == {"status": "ready", "packet_count": 1}


def test_public_audit_rejects_a_tampered_referenced_object(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0
    receipt = next(iter(manifest["files"].values()))
    fake.objects[f"{publisher.PREFIX}/{receipt['object_key']}"] = b'{"forged":true}\n'
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="public earnings story packet audit failed"):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_public_audit_materializes_and_replays_parent_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0
    next_dir = tmp_path / "next"
    _write_tree(
        next_dir,
        generation="packet_two",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"),
    )
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == 0

    def verify_with_lineage(out_dir: Path, *, manifest: dict) -> dict[str, int | str]:
        health = _verify_store(out_dir, manifest=manifest)
        cursor = manifest
        while cursor["parent_generation_id"] is not None:
            parent_path = Path(out_dir) / "generations" / cursor["parent_generation_id"] / "manifest.json"
            parent = json.loads(parent_path.read_text(encoding="utf-8"))
            _manifest_is_valid(parent)
            if parent["generation_id"] != cursor["parent_generation_id"]:
                raise ValueError("parent receipt")
            cursor = parent
        return health

    monkeypatch.setattr(publisher, "_story_contracts", lambda: (_manifest_is_valid, verify_with_lineage))
    assert publisher.audit_remote_generation(s3=fake, bucket="bucket") == {
        "status": "ready",
        "packet_count": 2,
    }


def test_public_audit_rejects_byte_valid_historical_root_rollback(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base = _write_tree(base_dir)
    fake = _FakeR2()
    assert publisher.publish(base_dir, s3=fake, bucket="bucket") == 0

    next_dir = tmp_path / "next"
    current = _write_tree(
        next_dir,
        generation="packet_two",
        parent=base["generation_id"],
        packets=("earnings:AAPL/2026Q1", "earnings:MSFT/2026Q1"),
    )
    assert publisher.publish(next_dir, s3=fake, bucket="bucket") == 0
    assert fake.marker == current

    # Replacing only the mutable pointer with its exact historical bytes used
    # to pass every manifest, ETag, ancestry, and evidence replay check.  The
    # immutable generation listing is the independent high-water witness.
    fake.marker = base
    fake.marker_body = canonical_json_bytes(base)
    fake.marker_etag = '"rolled-back"'
    with pytest.raises(
        publisher.ImmutableAddressIntegrityError,
        match="behind or outside|not the finalized publication journal tip",
    ):
        publisher.audit_remote_generation(s3=fake, bucket="bucket")


def test_public_audit_requires_generation_list_permission(tmp_path: Path) -> None:
    manifest = _write_tree(tmp_path)
    fake = _FakeR2()
    assert publisher.publish(tmp_path, s3=fake, bucket="bucket") == 0

    class _GetOnly:
        def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
            return fake.get_object(Bucket=Bucket, Key=Key)

    with pytest.raises(
        publisher.ImmutableAddressIntegrityError,
        match="ListObjects permission is required",
    ):
        publisher.audit_remote_generation(s3=_GetOnly(), bucket="bucket")


def test_remote_marker_contract_failure_cannot_supply_lineage() -> None:
    fake = _FakeR2(marker={"schema": "untrusted"})
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="fails its contract"):
        publisher.load_remote_root_marker(s3=fake, bucket="bucket")
