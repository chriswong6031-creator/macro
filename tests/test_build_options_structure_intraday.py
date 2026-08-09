from __future__ import annotations

import io
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pandas as pd
import pytest

from engine.options_structure_intraday import OptionsStructureIntradayError, canonical_json_bytes, index_key
from scripts.build_options_structure_intraday import (
    EpochCollisionError,
    EpochRegressionError,
    ImmutableCollisionError,
    LocalCommitUncertainError,
    PublicationCommitUncertainError,
    PublicationError,
    PublicationRepairNeededError,
    _atomic_write,
    _remote_object,
    discover_roots,
    prepare_bundle,
    publish_bundle,
    validate_complete_meta,
    write_local_bundle,
)


SESSION = "2026-08-07"
BUCKET = "16:00"
OBSERVED = "2026-08-07T20:02:00Z"
ROOTS = ("QRS", "TST")
REPO_ROOT = Path(__file__).resolve().parent.parent


def _chain(root: str, session: str = SESSION, bucket: str = BUCKET) -> pd.DataFrame:
    frame = pd.DataFrame({
        "root": [root, root],
        "expiration": pd.to_datetime(["2026-09-18", "2026-11-20"]),
        "strike": [110.0, 115.0],
        "right": ["C", "C"],
        "snapshot_ts": pd.to_datetime([f"{session}T{bucket}:00"] * 2),
        "snapshot_bucket": [bucket, bucket],
        "source": ["chain_snapshot", "chain_snapshot"],
        "bid": [2.8, 4.9],
        "ask": [3.2, 5.1],
        "delta": [0.30, 0.20],
        "theta": [-0.04, -0.03],
        "vega": [0.11, 0.14],
        "rho": [0.02, 0.03],
        "epsilon": [0.01, 0.01],
        "lambda": [4.2, 4.0],
        "implied_vol": [0.27, 0.31],
        "iv_error": [0.0, 0.0],
        "underlying_price": [100.0, 100.0],
        "gamma": [0.02, 0.01],
        "vanna": [0.1, 0.1],
        "charm": [-0.2, -0.2],
        "vomma": [1.5, 1.7],
        "veta": [2.5, 2.7],
    })
    return frame


def _oi(root: str, session: str = SESSION) -> pd.DataFrame:
    frame = _chain(root, session)[["root", "expiration", "strike", "right"]].copy()
    frame["snapshot_ts"] = pd.to_datetime([f"{session}T06:30:00"] * len(frame))
    frame["open_interest"] = [1000, 300]
    frame["source"] = "chain_snapshot"
    return frame


def _source_tree(
    tmp_path: Path,
    roots=ROOTS,
    *,
    session: str = SESSION,
    bucket: str = BUCKET,
    label: str = "chain_snapshots",
) -> Path:
    data_root = tmp_path / label
    for root in roots:
        root_dir = data_root / root
        root_dir.mkdir(parents=True)
        _chain(root, session, bucket).to_parquet(root_dir / f"{session}.parquet", index=False)
        _oi(root, session).to_parquet(root_dir / f"{session}_oi.parquet", index=False)
    return data_root


def _bundle(
    tmp_path: Path,
    *,
    session: str = SESSION,
    bucket: str = BUCKET,
    observed: str = OBSERVED,
    label: str = "chain_snapshots",
):
    return prepare_bundle(
        _source_tree(tmp_path, session=session, bucket=bucket, label=label),
        roots=ROOTS,
        session_date=session,
        snapshot_bucket=bucket,
        observed_at=observed,
        available_at=observed,
        cadence_minutes=15,
    )


class _PreconditionFailed(RuntimeError):
    response = {
        "Error": {"Code": "PreconditionFailed"},
        "ResponseMetadata": {"HTTPStatusCode": 412},
    }


class FakeR2:
    """Coherent-GET fake with conditional-PUT and fault injection."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str], str]] = {}
        self.puts: list[str] = []
        self.delete_calls = 0
        self.failures: dict[str, tuple[str, int]] = {}
        self.corrupt_reads: set[str] = set()
        self.before_conditional_put = None
        self.before_get = None
        self.fail_next_get: set[str] = set()
        self._etag_n = 0

    def seed(self, key: str, body: bytes, metadata: dict[str, str] | None = None) -> None:
        self._etag_n += 1
        self.objects[key] = (body, dict(metadata or {}), f'"etag-{self._etag_n}"')

    def fail_once(self, key: str, *, mode: str = "before") -> None:
        self.failures[key] = (mode, 1)

    def _consume_failure(self, key: str, mode: str) -> bool:
        configured = self.failures.get(key)
        if configured is None or configured[0] != mode or configured[1] <= 0:
            return False
        self.failures[key] = (mode, configured[1] - 1)
        return True

    def head_object(self, *, Bucket, Key):
        raise AssertionError("publisher must use one coherent GET, never HEAD+GET")

    def get_object(self, *, Bucket, Key):
        if self.before_get is not None:
            self.before_get(Key)
        if Key not in self.objects:
            raise RuntimeError("missing")
        if Key in self.fail_next_get:
            self.fail_next_get.remove(Key)
            raise RuntimeError("injected post-write verification failure")
        body, metadata, etag = self.objects[Key]
        if Key in self.corrupt_reads:
            body = body + b"corrupt"
        return {
            "Body": io.BytesIO(body),
            "ContentLength": len(self.objects[Key][0]),
            "Metadata": dict(metadata),
            "ETag": etag,
        }

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if self._consume_failure(key, "before"):
            raise RuntimeError("injected pre-write failure")
        if (
            ("IfMatch" in kwargs or "IfNoneMatch" in kwargs)
            and self.before_conditional_put is not None
        ):
            self.before_conditional_put(kwargs)
        current = self.objects.get(key)
        if kwargs.get("IfNoneMatch") == "*" and current is not None:
            raise _PreconditionFailed()
        if "IfMatch" in kwargs:
            if current is None or current[2] != kwargs["IfMatch"]:
                raise _PreconditionFailed()
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.puts.append(key)
        self.seed(key, body, dict(kwargs.get("Metadata") or {}))
        if self._consume_failure(key, "verify"):
            self.fail_next_get.add(key)
        if self._consume_failure(key, "after"):
            raise RuntimeError("injected post-write failure")
        return {"ETag": self.objects[key][2]}

    def delete_object(self, **kwargs):
        self.delete_calls += 1
        raise AssertionError("publisher must never call DeleteObject")


def test_prepare_bundle_reads_private_parquet_and_emits_exact_key_family(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    assert sorted(bundle.packets) == list(ROOTS)
    assert {artifact.key for artifact in bundle.immutable.values()} == {
        f"options_structure/msc_intraday/{root}/{SESSION}/1600.json" for root in ROOTS
    }
    assert {artifact.key for artifact in bundle.currents.values()} == {
        f"options_structure/msc_intraday/{root}/current.json" for root in ROOTS
    }
    assert bundle.index.key == "options_structure/msc_intraday/index.json"
    index = json.loads(bundle.index.body)
    assert index["complete_bucket"] is True
    assert index["root_count"] == len(ROOTS)
    assert all(
        packet["source_receipt"]["private_raw_parquet_published"] is False
        for packet in bundle.packets.values()
    )


def test_bare_script_help_pins_this_repo_ahead_of_hostile_pythonpath(tmp_path) -> None:
    decoy = tmp_path / "decoy" / "engine"
    decoy.mkdir(parents=True)
    (decoy / "options_structure_intraday.py").write_text(
        'raise RuntimeError("hostile import won")\n', encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_options_structure_intraday.py"), "--help"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(decoy.parent)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "hostile import won" not in result.stderr


def test_meta_attestation_rejects_partial_or_unbound_root_sets(tmp_path) -> None:
    data_root = _source_tree(tmp_path)
    roots = discover_roots(data_root, SESSION)
    meta = {
        "schema": "chain_snapshots.meta/v1",
        "session_date": SESSION,
        "bucket": BUCKET,
        "universe_n": 2,
        "roots_ok": 2,
        "roots_failed": 0,
        "cadence_min": 15,
        "asof": OBSERVED,
        "roots": list(ROOTS),
    }
    assert validate_complete_meta(meta, session_date=SESSION, snapshot_bucket=BUCKET, roots=roots) == 15
    with pytest.raises(OptionsStructureIntradayError, match="incomplete"):
        validate_complete_meta(
            {**meta, "roots_ok": 1, "roots_failed": 1},
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            roots=roots,
        )
    with pytest.raises(OptionsStructureIntradayError, match="root set"):
        validate_complete_meta(
            meta,
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            roots=["TST"],
        )
    with pytest.raises(OptionsStructureIntradayError, match="exact requested root set"):
        validate_complete_meta(
            {**meta, "roots": ["BAD", "TST"]},
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            roots=roots,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("universe_n", 2.9),
        ("roots_ok", "2"),
        ("roots_failed", False),
        ("cadence_min", 15.9),
    ],
)
def test_meta_control_counters_are_exact_integers(field, value) -> None:
    meta = {
        "schema": "chain_snapshots.meta/v1",
        "session_date": SESSION,
        "bucket": BUCKET,
        "universe_n": 2,
        "roots_ok": 2,
        "roots_failed": 0,
        "cadence_min": 15,
        "asof": OBSERVED,
        "roots": list(ROOTS),
        field: value,
    }
    with pytest.raises(OptionsStructureIntradayError, match="must be an integer"):
        validate_complete_meta(
            meta,
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            roots=ROOTS,
        )


@pytest.mark.parametrize("asof", ["2026-08-07T20:02:00", f"{OBSERVED}JUNK", True])
def test_meta_clock_is_canonical_and_timezone_aware(asof) -> None:
    meta = {
        "schema": "chain_snapshots.meta/v1",
        "session_date": SESSION,
        "bucket": BUCKET,
        "universe_n": 2,
        "roots_ok": 2,
        "roots_failed": 0,
        "cadence_min": 15,
        "asof": asof,
        "roots": list(ROOTS),
    }
    with pytest.raises(OptionsStructureIntradayError, match="canonical aware timestamp"):
        validate_complete_meta(
            meta,
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            roots=ROOTS,
        )


def test_missing_or_malformed_root_fails_before_any_local_discovery_write(monkeypatch, tmp_path) -> None:
    data_root = _source_tree(tmp_path)
    (data_root / "QRS" / f"{SESSION}.parquet").write_bytes(b"torn parquet")
    writes: list[str] = []
    monkeypatch.setattr(
        "scripts.build_options_structure_intraday._atomic_write",
        lambda path, body: writes.append(str(path)),
    )
    with pytest.raises(OptionsStructureIntradayError, match="malformed parquet"):
        prepare_bundle(
            data_root,
            roots=ROOTS,
            session_date=SESSION,
            snapshot_bucket=BUCKET,
            observed_at=OBSERVED,
        )
    assert writes == []


def test_local_write_orders_immutable_then_authoritative_index_then_currents(monkeypatch, tmp_path) -> None:
    bundle = _bundle(tmp_path)
    writes: list[str] = []
    monkeypatch.setattr(
        "scripts.build_options_structure_intraday._atomic_write",
        lambda path, body: writes.append(str(path.relative_to(tmp_path / "out"))),
    )
    write_local_bundle(bundle, tmp_path / "out")
    assert writes[:2] == [bundle.immutable[root].key for root in sorted(ROOTS)]
    assert writes[2] == index_key()
    assert writes[3:] == [bundle.currents[root].key for root in sorted(ROOTS)]


def test_atomic_write_fsyncs_file_before_replace_and_parent_after_nested_creation(
    monkeypatch, tmp_path
) -> None:
    target = tmp_path / "first" / "nested" / "artifact.json"
    events: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def observed_fsync(descriptor):
        kind = "dir_fsync" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file_fsync"
        events.append(kind)
        return real_fsync(descriptor)

    def observed_replace(source, destination):
        events.append("replace")
        return real_replace(source, destination)

    monkeypatch.setattr("scripts.build_options_structure_intraday.os.fsync", observed_fsync)
    monkeypatch.setattr("scripts.build_options_structure_intraday.os.replace", observed_replace)
    _atomic_write(target, b"durable\n")

    assert target.read_bytes() == b"durable\n"
    replace_at = events.index("replace")
    assert "file_fsync" in events[:replace_at]
    assert events[replace_at + 1] == "dir_fsync"
    # Existing ancestor confirmation plus each new parent entry is fenced.
    assert events[:replace_at].count("dir_fsync") >= 3


def test_atomic_write_file_fsync_failure_is_loud_and_exact_retry_recovers(
    monkeypatch, tmp_path
) -> None:
    target = tmp_path / "file-fsync" / "artifact.json"
    real_fsync = os.fsync
    failed = False

    def fail_first_file_fsync(descriptor):
        nonlocal failed
        if not failed and not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            failed = True
            raise OSError("injected file fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr("scripts.build_options_structure_intraday.os.fsync", fail_first_file_fsync)
    with pytest.raises(LocalCommitUncertainError, match="atomic commit is uncertain"):
        _atomic_write(target, b"durable\n")
    assert not target.exists()

    _atomic_write(target, b"durable\n")
    assert target.read_bytes() == b"durable\n"


def test_post_replace_directory_fsync_failure_is_reproved_by_idempotent_retry(
    monkeypatch, tmp_path
) -> None:
    bundle = _bundle(tmp_path)
    out = tmp_path / "out"
    real_fsync = os.fsync
    real_replace = os.replace
    replaced = False
    failed = False
    file_fsyncs_after_failure = 0

    def observed_replace(source, destination):
        nonlocal replaced
        result = real_replace(source, destination)
        replaced = True
        return result

    def fail_first_post_replace_directory_fsync(descriptor):
        nonlocal failed, file_fsyncs_after_failure
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        if replaced and not failed and is_directory:
            failed = True
            raise OSError("injected post-replace directory fsync failure")
        if failed and not is_directory:
            file_fsyncs_after_failure += 1
        return real_fsync(descriptor)

    monkeypatch.setattr("scripts.build_options_structure_intraday.os.replace", observed_replace)
    monkeypatch.setattr(
        "scripts.build_options_structure_intraday.os.fsync",
        fail_first_post_replace_directory_fsync,
    )
    with pytest.raises(LocalCommitUncertainError, match="directory durability is uncertain"):
        write_local_bundle(bundle, out)

    first = bundle.immutable[sorted(ROOTS)[0]]
    assert (out / first.key).read_bytes() == first.body
    # The exact retry re-opens and fsyncs the existing bytes plus their parent,
    # then safely completes the remaining manifest and derivative pointers.
    write_local_bundle(bundle, out)
    assert file_fsyncs_after_failure > 0
    assert (out / bundle.index.key).read_bytes() == bundle.index.body
    assert all((out / artifact.key).read_bytes() == artifact.body for artifact in bundle.currents.values())


def test_local_mirror_rejects_delayed_older_epoch_without_regression(tmp_path) -> None:
    newer = _bundle(tmp_path, label="local-newer")
    older = _bundle(
        tmp_path,
        session="2026-08-06",
        observed="2026-08-06T20:02:00Z",
        label="local-older",
    )
    out = tmp_path / "out"
    write_local_bundle(newer, out)
    index_before = (out / newer.index.key).read_bytes()
    currents_before = {
        root: (out / newer.currents[root].key).read_bytes() for root in ROOTS
    }
    with pytest.raises(EpochRegressionError, match="local authoritative index"):
        write_local_bundle(older, out)
    assert (out / newer.index.key).read_bytes() == index_before
    assert {
        root: (out / newer.currents[root].key).read_bytes() for root in ROOTS
    } == currents_before


def test_r2_success_is_immutable_first_index_commit_then_derivative_currents(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    fake = FakeR2()
    result = publish_bundle(bundle, client=fake, bucket="bucket")
    immutable_keys = [bundle.immutable[root].key for root in sorted(ROOTS)]
    current_keys = [bundle.currents[root].key for root in sorted(ROOTS)]
    assert fake.puts == immutable_keys + [bundle.index.key] + current_keys
    assert result.index_status == "committed"
    assert result.currents_repaired == tuple(sorted(ROOTS))
    assert result.currents_idempotent == ()
    assert result.currents_superseded == ()
    for artifact in list(bundle.immutable.values()) + list(bundle.currents.values()) + [bundle.index]:
        body, metadata, _etag = fake.objects[artifact.key]
        assert body == artifact.body
        assert metadata == {"sha256": artifact.sha256}
    index = json.loads(bundle.index.body)
    assert index["authoritative_discovery"] is True
    assert index["commit_role"] == "sole_authoritative_global_index"
    assert all("object" in row and "derivative_current_key" in row for row in index["roots"])
    for artifact in bundle.currents.values():
        pointer = json.loads(artifact.body)
        assert pointer["authoritative_discovery"] is False
        assert pointer["derived_from_index"]["index_id"] == index["index_id"]
    fake.puts.clear()
    result = publish_bundle(bundle, client=fake, bucket="bucket")
    assert fake.puts == []
    assert result.index_status == "idempotent"
    assert result.currents_idempotent == tuple(sorted(ROOTS))
    assert fake.delete_calls == 0


def test_immutable_collision_or_failed_verification_never_touches_discovery(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    first_root = sorted(ROOTS)[0]
    first = bundle.immutable[first_root]
    fake = FakeR2()
    fake.seed(first.key, b"different", {"sha256": first.sha256})
    with pytest.raises(ImmutableCollisionError):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert all(artifact.key not in fake.objects for artifact in bundle.currents.values())
    assert bundle.index.key not in fake.objects

    fake = FakeR2()
    second = bundle.immutable[sorted(ROOTS)[1]]
    fake.corrupt_reads.add(second.key)
    with pytest.raises(PublicationError, match="length mismatch|verification failed"):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert all(artifact.key not in fake.objects for artifact in bundle.currents.values())
    assert bundle.index.key not in fake.objects


def test_index_failure_leaves_all_derivative_currents_untouched(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    fake = FakeR2()
    fake.fail_once(bundle.index.key, mode="before")
    with pytest.raises(PublicationCommitUncertainError, match="outcome is uncertain"):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert bundle.index.key not in fake.objects
    assert all(artifact.key not in fake.objects for artifact in bundle.currents.values())
    assert fake.delete_calls == 0


def test_post_write_index_uncertainty_never_rolls_back_and_retry_repairs(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    fake = FakeR2()
    fake.fail_once(bundle.index.key, mode="verify")
    with pytest.raises(PublicationCommitUncertainError, match="could not be verified"):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert fake.objects[bundle.index.key][0] == bundle.index.body
    assert all(artifact.key not in fake.objects for artifact in bundle.currents.values())
    assert fake.delete_calls == 0

    result = publish_bundle(bundle, client=fake, bucket="bucket")
    assert result.index_status == "idempotent"
    assert result.currents_repaired == tuple(sorted(ROOTS))
    assert fake.delete_calls == 0


def test_partial_pointer_failure_is_committed_then_retry_heals(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    fake = FakeR2()
    first, second = sorted(ROOTS)
    fake.fail_once(bundle.currents[second].key, mode="before")
    with pytest.raises(PublicationRepairNeededError, match="global index committed"):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert fake.objects[bundle.index.key][0] == bundle.index.body
    assert fake.objects[bundle.currents[first].key][0] == bundle.currents[first].body
    assert bundle.currents[second].key not in fake.objects

    result = publish_bundle(bundle, client=fake, bucket="bucket")
    assert result.index_status == "idempotent"
    assert result.currents_idempotent == (first,)
    assert result.currents_repaired == (second,)


def test_newer_then_delayed_older_can_never_regress_index_or_currents(tmp_path) -> None:
    newer = _bundle(tmp_path, label="newer")
    older = _bundle(
        tmp_path,
        session="2026-08-06",
        observed="2026-08-06T20:02:00Z",
        label="older",
    )
    fake = FakeR2()
    publish_bundle(newer, client=fake, bucket="bucket")
    before_index = fake.objects[newer.index.key]
    before_currents = {
        root: fake.objects[newer.currents[root].key] for root in ROOTS
    }
    with pytest.raises(EpochRegressionError, match="newer epoch"):
        publish_bundle(older, client=fake, bucket="bucket")
    assert fake.objects[newer.index.key] == before_index
    assert {
        root: fake.objects[newer.currents[root].key] for root in ROOTS
    } == before_currents
    assert fake.delete_calls == 0


def test_same_epoch_different_index_bytes_is_a_collision(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    fake = FakeR2()
    drift = json.loads(bundle.index.body)
    drift["profile_ordering"] = "foreign_same_epoch"
    body = canonical_json_bytes(drift)
    fake.seed(bundle.index.key, body, {"sha256": sha256(body).hexdigest()})
    with pytest.raises(EpochCollisionError, match="same discovery epoch"):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert all(artifact.key not in fake.objects for artifact in bundle.currents.values())


def test_same_epoch_different_current_bytes_is_repair_needed_not_overwritten(tmp_path) -> None:
    bundle = _bundle(tmp_path)
    fake = FakeR2()
    root = sorted(ROOTS)[0]
    artifact = bundle.currents[root]
    drift = json.loads(artifact.body)
    drift["available_at"] = "2026-08-07T20:03:00.000000Z"
    body = canonical_json_bytes(drift)
    digest = sha256(body).hexdigest()
    fake.seed(artifact.key, body, {"sha256": digest})
    with pytest.raises(PublicationRepairNeededError, match="same discovery epoch"):
        publish_bundle(bundle, client=fake, bucket="bucket")
    assert fake.objects[bundle.index.key][0] == bundle.index.body
    assert fake.objects[artifact.key][0] == body
    assert fake.delete_calls == 0


def test_concurrent_newer_current_is_preserved_as_safe_supersession(tmp_path) -> None:
    desired = _bundle(tmp_path, label="desired")
    future = _bundle(
        tmp_path,
        session="2026-08-10",
        observed="2026-08-10T20:02:00Z",
        label="future",
    )
    fake = FakeR2()
    target_root = sorted(ROOTS)[0]
    target_key = desired.currents[target_root].key
    future_artifact = future.currents[target_root]

    def interleave(kwargs):
        if kwargs["Key"] == target_key and kwargs.get("IfNoneMatch") == "*":
            fake.seed(target_key, future_artifact.body, {"sha256": future_artifact.sha256})

    fake.before_conditional_put = interleave
    result = publish_bundle(desired, client=fake, bucket="bucket")
    assert result.currents_superseded == (target_root,)
    assert fake.objects[target_key][0] == future_artifact.body
    assert fake.delete_calls == 0


def test_same_length_interleaving_get_returns_one_coherent_version() -> None:
    fake = FakeR2()
    key = "coherent.json"
    old = b'{"a":1}\n'
    new = b'{"b":2}\n'
    assert len(old) == len(new)
    fake.seed(key, old, {"sha256": "old"})

    def interleave(read_key):
        if read_key == key:
            fake.seed(key, new, {"sha256": "new"})
            fake.before_get = None

    fake.before_get = interleave
    remote = _remote_object(fake, "bucket", key)
    assert remote is not None
    assert remote.body == new
    assert remote.metadata == {"sha256": "new"}
    assert remote.content_length == len(new)
    assert remote.etag == fake.objects[key][2]
