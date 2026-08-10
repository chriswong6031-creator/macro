from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pandas as pd
import pytest

from engine import chain_snapshot_completion as bucket_completion
from engine import chain_snapshot_evidence
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
    advance_publication_cursor,
    advance_publication_scan_cursor,
    completion_request,
    discover_roots,
    prepare_bundle,
    publication_ack_path,
    publication_acknowledged,
    publication_cursor_path,
    publication_scan_cursor_path,
    publication_index_receipt_path,
    read_publication_cursor,
    read_publication_scan_cursor,
    publish_bundle,
    validate_complete_meta,
    write_publication_ack,
    write_local_bundle,
)


SESSION = "2026-08-07"
BUCKET = "16:00"
OBSERVED = "2026-08-07T20:02:00Z"
ROOTS = ("QRS", "TST")
REPO_ROOT = Path(__file__).resolve().parent.parent


def _completion_packet(
    tmp_path: Path,
    *,
    data_root: Path | None = None,
    session: str = SESSION,
    bucket: str = BUCKET,
) -> dict:
    local = datetime.fromisoformat(f"{session}T{bucket}:10").replace(
        tzinfo=bucket_completion.ET,
    )
    base = local.astimezone(timezone.utc)
    clocks = iter([
        base.replace(microsecond=100001),
        (base + timedelta(seconds=10)).replace(microsecond=100002),
        (base + timedelta(seconds=50)).replace(microsecond=100003),
        (base + timedelta(seconds=51)).replace(microsecond=100004),
    ])
    results = []
    for root in ROOTS:
        if data_root is None:
            bucket_content_sha256 = "a" * 64
            oi_parquet_sha256 = "c" * 64
        else:
            chain_path = data_root / root / f"{session}.parquet"
            oi_path = data_root / root / f"{session}_oi.parquet"
            target = chain_snapshot_evidence.target_bucket_frame(
                pd.read_parquet(chain_path),
                root,
                bucket,
                dedup_key=chain_snapshot_evidence.CHAIN_SNAPSHOT_DEDUP_KEY,
            )
            bucket_content_sha256 = chain_snapshot_evidence.frame_content_sha256(
                target,
                dedup_key=chain_snapshot_evidence.CHAIN_SNAPSHOT_DEDUP_KEY,
            )
            oi_parquet_sha256 = chain_snapshot_evidence.file_sha256(oi_path)
        results.append({
            "root": root,
            "rows": 2,
            "total_rows": 2,
            "oi_rows": 2,
            "oi_total_rows": 2,
            "error": None,
            "completion_errors": [],
            "bucket_rows": 2,
            "bucket_content_sha256": bucket_content_sha256,
            "parquet_sha256": "b" * 64,
            "oi_parquet_sha256": oi_parquet_sha256,
            "first_vendor_min_at": base.replace(
                second=0, microsecond=1,
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "first_vendor_max_at": base.replace(
                second=0, microsecond=2,
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "first_prebucket_rows": 0,
            "first_at_or_after_bucket_rows": 2,
            "second_clock_matched_rows": 2,
            "second_clock_unmatched_rows": 0,
            "quarantined": [],
            "oi_quarantined": [],
        })
    with bucket_completion.locked_bucket_lease(
        tmp_path / "receipts",
        session_date=session,
        bucket=bucket,
        cadence_min=15,
        roots=list(ROOTS),
        now=local,
        now_fn=lambda: next(clocks),
    ) as lease:
        assert lease.refresh_before_source() is not None
        lease.record_decision(
            bucket_completion.build_completion_summary(ROOTS, results),
        )
        lease.record_availability()
        return lease.packet()


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
        root_dir.mkdir(parents=True, exist_ok=True)
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


def test_completion_packet_cli_binds_exact_receipt_identity_and_clocks(tmp_path) -> None:
    data_root = _source_tree(tmp_path)
    packet = _completion_packet(tmp_path, data_root=data_root)
    request = completion_request(packet)
    assert request.session_date == SESSION
    assert request.snapshot_bucket == BUCKET
    assert request.roots == ROOTS
    assert request.cadence_minutes == 15
    assert request.observed_at == packet["decision"]["decision_at"]
    assert request.available_at == packet["availability"]["availability_at"]

    out_dir = tmp_path / "projection"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_options_structure_intraday.py"),
            "--completion-packet-stdin",
            "--data-root",
            str(data_root),
            "--out-dir",
            str(out_dir),
        ],
        cwd=tmp_path,
        input=bucket_completion.canonical_bytes(packet) + b"\n",
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert "source_bytes=" in result.stderr.decode()
    assert "wall_sec=" in result.stderr.decode()
    assert "peak_rss_bytes=" in result.stderr.decode()
    index = json.loads(
        (out_dir / "options_structure" / "msc_intraday" / "index.json").read_text()
    )
    assert index["session_date"] == SESSION
    assert index["snapshot_bucket"] == BUCKET
    for root in ROOTS:
        body = json.loads(
            (
                out_dir / "options_structure" / "msc_intraday" / root
                / SESSION / "1600.json"
            ).read_text()
        )
        assert body["clocks"]["builder_observed_at"] == request.observed_at
        assert body["clocks"]["available_at"] == request.available_at
        assert all(value is False for value in body["authority"].values())


def test_completion_packet_rejects_override_laundering(tmp_path, monkeypatch) -> None:
    packet = _completion_packet(tmp_path)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(bucket_completion.canonical_bytes(packet))),
    )
    from scripts import build_options_structure_intraday as builder

    assert builder.main([
        "--completion-packet-stdin",
        "--session",
        SESSION,
        "--no-local",
    ]) == 1


def test_completion_evidence_binds_bucket_content_and_stable_oi(tmp_path) -> None:
    data_root = _source_tree(tmp_path)
    packet = _completion_packet(tmp_path, data_root=data_root)
    request = completion_request(packet)

    chain_path = data_root / ROOTS[0] / f"{SESSION}.parquet"
    changed = pd.read_parquet(chain_path)
    changed.loc[0, "bid"] = 9.9
    changed.to_parquet(chain_path, index=False)
    with pytest.raises(OptionsStructureIntradayError, match="bucket_content_sha256"):
        prepare_bundle(
            data_root,
            roots=request.roots,
            session_date=request.session_date,
            snapshot_bucket=request.snapshot_bucket,
            observed_at=request.observed_at,
            available_at=request.available_at,
            cadence_minutes=request.cadence_minutes,
            completion_evidence=request.root_evidence,
        )

    data_root = _source_tree(tmp_path, label="oi-drift")
    packet = _completion_packet(tmp_path / "oi-receipts", data_root=data_root)
    request = completion_request(packet)
    oi_path = data_root / ROOTS[0] / f"{SESSION}_oi.parquet"
    changed_oi = pd.read_parquet(oi_path)
    changed_oi.loc[0, "open_interest"] += 1
    changed_oi.to_parquet(oi_path, index=False)
    with pytest.raises(OptionsStructureIntradayError, match="oi_parquet_sha256"):
        prepare_bundle(
            data_root,
            roots=request.roots,
            session_date=request.session_date,
            snapshot_bucket=request.snapshot_bucket,
            observed_at=request.observed_at,
            available_at=request.available_at,
            cadence_minutes=request.cadence_minutes,
            completion_evidence=request.root_evidence,
        )


def test_other_day_bucket_rows_do_not_break_exact_bucket_recovery(tmp_path) -> None:
    data_root = _source_tree(tmp_path)
    packet = _completion_packet(tmp_path, data_root=data_root)
    request = completion_request(packet)
    for root in ROOTS:
        path = data_root / root / f"{SESSION}.parquet"
        other_bucket = _chain(root, bucket="15:45")
        pd.concat([pd.read_parquet(path), other_bucket], ignore_index=True).to_parquet(
            path, index=False,
        )
    bundle = prepare_bundle(
        data_root,
        roots=request.roots,
        session_date=request.session_date,
        snapshot_bucket=request.snapshot_bucket,
        observed_at=request.observed_at,
        available_at=request.available_at,
        cadence_minutes=request.cadence_minutes,
        completion_evidence=request.root_evidence,
    )
    assert sorted(bundle.packets) == list(ROOTS)


def test_local_publication_ack_is_deterministic_and_collision_closed(tmp_path) -> None:
    data_root = _source_tree(tmp_path)
    packet = _completion_packet(tmp_path, data_root=data_root)
    request = completion_request(packet)
    bundle = prepare_bundle(
        data_root,
        roots=request.roots,
        session_date=request.session_date,
        snapshot_bucket=request.snapshot_bucket,
        observed_at=request.observed_at,
        available_at=request.available_at,
        cadence_minutes=request.cadence_minutes,
        completion_evidence=request.root_evidence,
    )
    out_dir = tmp_path / "projection-ack"
    assert publication_acknowledged(out_dir, packet) is False
    write_local_bundle(bundle, out_dir)
    assert publication_acknowledged(out_dir, packet) is False
    target = write_publication_ack(out_dir, packet, bundle)
    assert target == publication_ack_path(out_dir, packet)
    index_receipt = publication_index_receipt_path(out_dir, packet)
    assert index_receipt.read_bytes() == bundle.index.body
    assert publication_acknowledged(out_dir, packet) is True
    assert write_publication_ack(out_dir, packet, bundle) == target
    assert read_publication_cursor(out_dir) is None
    cursor_path = advance_publication_cursor(
        out_dir, packet, prefix_packets=[packet], activation_session=SESSION,
    )
    cursor = read_publication_cursor(out_dir)
    assert cursor_path == publication_cursor_path(out_dir)
    assert cursor["complete_prefix_count"] == 1
    assert advance_publication_cursor(
        out_dir, packet, prefix_packets=[packet], activation_session=SESSION,
    ) == cursor_path
    with pytest.raises(PublicationError, match="activation cannot change"):
        advance_publication_cursor(
            out_dir,
            packet,
            prefix_packets=[packet],
            activation_session="2026-08-06",
        )

    exact_cursor = cursor_path.read_bytes()
    cursor_payload = json.loads(exact_cursor)
    cursor_payload["ack_sha256"] = "0" * 64
    cursor_path.write_bytes(canonical_json_bytes(cursor_payload))
    with pytest.raises(PublicationError, match="cursor ack hash drifted"):
        read_publication_cursor(out_dir)
    cursor_path.write_bytes(exact_cursor)

    cursor_path.write_text(json.dumps(json.loads(exact_cursor), indent=2))
    with pytest.raises(PublicationError, match="cursor is not canonical"):
        read_publication_cursor(out_dir)
    cursor_path.write_bytes(exact_cursor)

    scan_path = advance_publication_scan_cursor(
        out_dir,
        activation_session=SESSION,
        from_session=SESSION,
        to_session="2026-08-10",
        sealed_session=SESSION,
        sealed_ledger_sha256="1" * 64,
        sealed_packets=[packet],
    )
    assert scan_path == publication_scan_cursor_path(out_dir)
    scan_cursor = read_publication_scan_cursor(out_dir)
    assert scan_cursor["sealed_complete_count"] == 1
    assert advance_publication_scan_cursor(
        out_dir,
        activation_session=SESSION,
        from_session=SESSION,
        to_session="2026-08-10",
        sealed_session=SESSION,
        sealed_ledger_sha256="1" * 64,
        sealed_packets=[packet],
    ) == scan_path
    exact_scan_cursor = scan_path.read_bytes()
    scan_payload = json.loads(exact_scan_cursor)
    scan_payload["sealed_last_ack_sha256"] = "0" * 64
    scan_path.write_bytes(canonical_json_bytes(scan_payload))
    with pytest.raises(PublicationError, match="acknowledgement hash drifted"):
        read_publication_scan_cursor(out_dir)
    scan_path.write_bytes(exact_scan_cursor)
    scan_path.write_text(json.dumps(json.loads(exact_scan_cursor), indent=2))
    with pytest.raises(PublicationError, match="scan cursor is not canonical"):
        read_publication_scan_cursor(out_dir)
    scan_path.write_bytes(exact_scan_cursor)

    exact_ack = target.read_bytes()
    target.write_text(json.dumps(json.loads(exact_ack), indent=2))
    with pytest.raises(PublicationError, match="acknowledgement is not canonical"):
        publication_acknowledged(out_dir, packet)
    target.write_bytes(exact_ack)

    exact_index_receipt = index_receipt.read_bytes()
    index_receipt.write_bytes(exact_index_receipt + b"drift")
    with pytest.raises(PublicationError, match="index receipt hash drifted"):
        publication_acknowledged(out_dir, packet)
    index_receipt.unlink()
    with pytest.raises(LocalCommitUncertainError, match="local artifact durability"):
        publication_acknowledged(out_dir, packet)
    index_receipt.write_bytes(exact_index_receipt)
    assert publication_acknowledged(out_dir, packet) is True

    immutable = out_dir / bundle.immutable[ROOTS[0]].key
    exact_body = immutable.read_bytes()
    immutable.write_bytes(exact_body + b"drift")
    with pytest.raises(PublicationError, match="local immutable object drift"):
        publication_acknowledged(out_dir, packet)
    immutable.write_bytes(exact_body)
    assert publication_acknowledged(out_dir, packet) is True

    payload = json.loads(target.read_text())
    payload["completion_packet_sha256"] = "0" * 64
    target.write_text(json.dumps(payload))
    with pytest.raises(PublicationError, match="completion_packet_sha256 mismatch"):
        publication_acknowledged(out_dir, packet)
    with pytest.raises(ImmutableCollisionError, match="acknowledgement collision"):
        write_publication_ack(out_dir, packet, bundle)
    target.write_bytes(b'{"schema":')
    with pytest.raises(PublicationError, match="invalid local publication"):
        publication_acknowledged(out_dir, packet)


def test_empty_terminal_scan_cursor_is_canonical_and_idempotent(tmp_path) -> None:
    out_dir = tmp_path / "empty-scan-cursor"
    target = advance_publication_scan_cursor(
        out_dir,
        activation_session=SESSION,
        from_session=SESSION,
        to_session="2026-08-10",
        sealed_session=SESSION,
        sealed_ledger_sha256="2" * 64,
        sealed_packets=[],
    )
    payload = read_publication_scan_cursor(out_dir)
    assert payload["sealed_complete_count"] == 0
    assert payload["sealed_last_bucket"] is None
    assert advance_publication_scan_cursor(
        out_dir,
        activation_session=SESSION,
        from_session=SESSION,
        to_session="2026-08-10",
        sealed_session=SESSION,
        sealed_ledger_sha256="2" * 64,
        sealed_packets=[],
    ) == target


def test_scan_cursor_refuses_missing_non_tail_ack_in_sealed_session(
    tmp_path,
) -> None:
    first_bucket = "15:45"
    data_root = _source_tree(tmp_path, bucket=first_bucket)
    for root in ROOTS:
        path = data_root / root / f"{SESSION}.parquet"
        pd.concat(
            [pd.read_parquet(path), _chain(root, bucket=BUCKET)],
            ignore_index=True,
        ).to_parquet(path, index=False)
    producer_root = tmp_path / "two-bucket-producer"
    first = _completion_packet(
        producer_root,
        data_root=data_root,
        bucket=first_bucket,
    )
    last = _completion_packet(
        producer_root,
        data_root=data_root,
        bucket=BUCKET,
    )
    out_dir = tmp_path / "two-bucket-projection"
    for packet in (first, last):
        request = completion_request(packet)
        bundle = prepare_bundle(
            data_root,
            roots=request.roots,
            session_date=request.session_date,
            snapshot_bucket=request.snapshot_bucket,
            observed_at=request.observed_at,
            available_at=request.available_at,
            cadence_minutes=request.cadence_minutes,
            completion_evidence=request.root_evidence,
        )
        write_local_bundle(bundle, out_dir)
        write_publication_ack(out_dir, packet, bundle)
    advance_publication_cursor(
        out_dir,
        first,
        prefix_packets=[first],
        activation_session=SESSION,
    )
    advance_publication_cursor(
        out_dir,
        last,
        prefix_packets=[first, last],
        activation_session=SESSION,
    )
    publication_ack_path(out_dir, first).unlink()
    with pytest.raises(PublicationError, match="15:45"):
        advance_publication_scan_cursor(
            out_dir,
            activation_session=SESSION,
            from_session=SESSION,
            to_session="2026-08-10",
            sealed_session=SESSION,
            sealed_ledger_sha256="3" * 64,
            sealed_packets=[first, last],
        )


def test_real_two_session_catchup_ack_cursor_scan_and_retry(
    tmp_path, monkeypatch,
) -> None:
    from scripts import chain_snapshot_poller as poller

    second_session = "2026-08-10"
    data_root = _source_tree(tmp_path)
    _source_tree(tmp_path, session=second_session)
    producer_root = tmp_path / "producer"
    first = _completion_packet(
        producer_root, data_root=data_root, session=SESSION,
    )
    second = _completion_packet(
        producer_root, data_root=data_root, session=second_session,
    )
    receipt_root = producer_root / "receipts"
    out_dir = tmp_path / "projection-real-catchup"
    fake = FakeR2()
    publish_calls: list[tuple[str, str]] = []

    def publish(packet: dict) -> None:
        request = completion_request(packet)
        bundle = prepare_bundle(
            data_root,
            roots=request.roots,
            session_date=request.session_date,
            snapshot_bucket=request.snapshot_bucket,
            observed_at=request.observed_at,
            available_at=request.available_at,
            cadence_minutes=request.cadence_minutes,
            completion_evidence=request.root_evidence,
        )
        publish_bundle(bundle, client=fake, bucket="bucket")
        write_local_bundle(bundle, out_dir)
        write_publication_ack(out_dir, packet, bundle)
        publish_calls.append((request.session_date, request.snapshot_bucket))

    monkeypatch.setattr(poller, "_receipt_root_path", lambda: receipt_root)
    monkeypatch.setattr(poller, "_options_structure_out_dir_path", lambda: out_dir)

    # Crash boundary: durable remote/local acknowledgement exists, but no
    # delivery cursor was advanced yet.
    publish(first)
    assert read_publication_cursor(out_dir) is None
    recovered = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert recovered["attempted"] == 0
    assert recovered["acknowledged"] == 1
    assert read_publication_cursor(out_dir)["session_date"] == SESSION

    delivered = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert delivered["attempted"] == 1
    assert delivered["acknowledged"] == 1
    assert delivered["scan_advanced"] == 1
    assert delivered["remaining"] == 0
    assert read_publication_cursor(out_dir)["session_date"] == second_session
    assert read_publication_scan_cursor(out_dir)["scan_session"] == second_session

    replay = poller._retry_unacknowledged_publications(
        publish, activation_session=SESSION,
    )
    assert replay["attempted"] == 0
    assert replay["remaining"] == 0
    assert replay["errors"] == []
    assert publish_calls == [(SESSION, BUCKET), (second_session, BUCKET)]


def test_receipt_mode_ack_follows_verified_remote_and_local_success(
    tmp_path, monkeypatch,
) -> None:
    from scripts import build_options_structure_intraday as builder

    data_root = _source_tree(tmp_path)
    packet = _completion_packet(tmp_path, data_root=data_root)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(bucket_completion.canonical_bytes(packet))),
    )
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    monkeypatch.setattr(builder, "_r2_client", lambda: object())
    order: list[str] = []
    monkeypatch.setattr(
        builder,
        "publish_bundle",
        lambda *_args, **_kwargs: order.append("remote_verified"),
    )
    monkeypatch.setattr(
        builder,
        "write_local_bundle",
        lambda *_args, **_kwargs: order.append("local_verified"),
    )
    monkeypatch.setattr(
        builder,
        "write_publication_ack",
        lambda *_args, **_kwargs: order.append("ack_durable"),
    )

    assert builder.main([
        "--completion-packet-stdin",
        "--data-root",
        str(data_root),
        "--out-dir",
        str(tmp_path / "projection-order"),
        "--publish",
    ]) == 0
    assert order == ["remote_verified", "local_verified", "ack_durable"]

    order.clear()
    monkeypatch.setattr(
        sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(bucket_completion.canonical_bytes(packet))),
    )

    def remote_failure(*_args, **_kwargs):
        order.append("remote_failed")
        raise PublicationError("R2 unavailable")

    monkeypatch.setattr(builder, "publish_bundle", remote_failure)
    assert builder.main([
        "--completion-packet-stdin",
        "--data-root",
        str(data_root),
        "--out-dir",
        str(tmp_path / "projection-order"),
        "--publish",
    ]) == 1
    assert order == ["remote_failed"]


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
