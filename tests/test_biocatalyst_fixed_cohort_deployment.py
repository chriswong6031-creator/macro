"""Hostile deployment tests for the B1S2b privileged fixed-cohort lane.

Nothing here performs real network or filesystem-root I/O.  Every manifest,
pointer, receipt, and state root lives under ``tmp_path``; the transport is
always injected; and the trusted owner is the test user rather than root, which
is what lets the production ``root``-only rule be exercised as a *refusal* (a
file owned by the test user is refused when root is the trusted owner).

The lane exists because ``research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md``
cleared the Record History rights gate while recording that no worker or timer
existed to collect anything.  These tests hold the resulting artifacts to the
one promise that matters: they are installable and INERT.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from collectors.biocatalyst.clinicaltrials_discovery import DiscoveryResponse
import engine.biocatalyst.fixed_cohort_runtime as runtime
from engine.biocatalyst.fixed_cohort import build_fixed_cohort
from engine.biocatalyst.fixed_cohort_runtime import (
    B0A_MASKED_PATHS,
    FixedCohortRuntimeError,
    MEMBERSHIP_ENV_PHRASES,
    MEMBERSHIP_ENV_SEGMENTS,
    ROTATION_RECEIPT_CONTRACT_ID,
    ROTATION_RECEIPT_RULING_REF,
    ROTATION_RECORD_KIND,
    RUNTIME_ACTIVE_POINTER_NAME,
    RUNTIME_CONFIG_ROOT,
    RUNTIME_ENV_FILE,
    RUNTIME_IDENTITY,
    active_pointer_matches_receipt,
    active_pointer_path_for,
    assert_environment_carries_no_membership,
    atomic_write_bytes,
    install_manifest,
    load_active_manifest,
    load_manifest_file,
    manifest_content_bytes,
    manifest_content_sha256,
    manifest_filename,
    manifest_path_for,
    membership_environment_offences,
    parse_manifest_bytes,
    read_trusted_file,
    require_operational_store_available,
    rotate_active_manifest,
)
from engine.biocatalyst.operational_store import (
    RECORD_KINDS as OPERATIONAL_RECORD_KINDS,
    OperationalStore,
    OperationalStoreError,
    OperationalStoreUnavailableError,
    provision_operational_store,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    canonical_json_bytes,
)
import scripts.biocatalyst_fixed_cohort_transport as cli


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE_PATH = DEPLOY / "biocatalyst-fixed-cohort.service"
TIMER_PATH = DEPLOY / "biocatalyst-fixed-cohort.timer"
SETUP_PATH = DEPLOY / "biocatalyst-fixed-cohort-setup.sh"
CLI_PATH = ROOT / "scripts" / "biocatalyst_fixed_cohort_transport.py"
RUNTIME_PATH = ROOT / "engine" / "biocatalyst" / "fixed_cohort_runtime.py"
SCHEMA_PATH = (
    ROOT / "contracts" / "biocatalyst" / "biocatalyst_manifest_rotation_receipt.v1.schema.json"
)
LEGACY_JOBS_PATH = ROOT / ".github" / "ci" / "legacy-jobs.yml"

COHORT_A = ["NCT00000001", "NCT00000002", "NCT00000003"]
COHORT_B = ["NCT00000004", "NCT00000005"]
KNOWN_TIME = "2026-08-07T09:15:00.000000Z"
LATER_TIME = "2026-08-07T11:45:00.000000Z"
NOW = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)
REGISTERED_PROVENANCE = {
    "kind": "registered_control",
    "control_registration": "b1s1_fixed_cohort_control",
    "source_registry_ref": "config/biocatalyst_sources.yml",
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def operational_record_kinds() -> tuple[str, ...]:
    return OPERATIONAL_RECORD_KINDS


# ---------------------------------------------------------------------------
# Hermetic lane fixture
# ---------------------------------------------------------------------------


class Lane:
    """One fully hermetic copy of the production path layout, under tmp_path."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.config_root = base / "etc" / "macro-biocatalyst-fixed-cohort"
        self.manifest_root = self.config_root / "manifests"
        self.manifest_root.mkdir(parents=True)
        self.config_root.chmod(0o755)
        self.manifest_root.chmod(0o755)
        self.state_root = base / "var" / "macro-biocatalyst-fixed-cohort"
        self.run_root = self.state_root / "runs"
        self.receipt_root = self.state_root / "receipts"
        self.operational_root = self.state_root / "operational"
        for directory in (self.run_root, self.receipt_root):
            directory.mkdir(parents=True)
            directory.chmod(0o700)
        provision_operational_store(self.operational_root)
        self.uids = frozenset({os.getuid()})
        self.gids = frozenset(
            {
                os.getgid(),
                self.config_root.stat().st_gid,
                self.manifest_root.stat().st_gid,
            }
        )

    @property
    def active(self) -> Path:
        return active_pointer_path_for(self.config_root)

    def store(self) -> OperationalStore:
        return OperationalStore(self.operational_root, repo_root=ROOT)

    def trust(self) -> dict:
        return {"trusted_uids": self.uids, "trusted_gids": self.gids}

    def install(self, document) -> Path:
        return install_manifest(
            document, config_root=self.config_root, repo_root=ROOT, **self.trust()
        )

    def activate(self, document) -> None:
        """Seed an active pointer directly, bypassing the rotation lifecycle."""

        self.install(document)
        atomic_write_bytes(self.active, manifest_content_bytes(document), mode=0o444)


@pytest.fixture()
def lane(tmp_path: Path) -> Lane:
    return Lane(tmp_path)


@pytest.fixture(scope="module")
def cohort_a() -> dict:
    return build_fixed_cohort(COHORT_A, provenance=REGISTERED_PROVENANCE, repo_root=ROOT)


@pytest.fixture(scope="module")
def cohort_b() -> dict:
    return build_fixed_cohort(COHORT_B, provenance=REGISTERED_PROVENANCE, repo_root=ROOT)


class Clock:
    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self) -> datetime:
        value = NOW + timedelta(microseconds=self._ticks)
        self._ticks += 1
        return value


def _json_response(payload: dict) -> DiscoveryResponse:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return DiscoveryResponse(
        status_code=200,
        headers={"content-type": "application/json", "content-length": str(len(body))},
        body=body,
    )


class FakeTransport:
    """An injected transport that cannot reach a network and counts its closes."""

    VERSION = {"apiVersion": "2.0.3", "dataTimestamp": "2026-08-06T12:00:00Z"}

    def __init__(self, nct_ids, *, close_error: BaseException | None = None) -> None:
        self.nct_ids = list(nct_ids)
        self.paths: list[str] = []
        self.closes = 0
        self._close_error = close_error

    def get(self, path: str, *, params, headers) -> DiscoveryResponse:
        self.paths.append(path)
        if path == "/version":
            return _json_response(dict(self.VERSION))
        if path == "/studies":
            return _json_response(
                {
                    "studies": [
                        {
                            "protocolSection": {
                                "identificationModule": {"nctId": nct_id}
                            }
                        }
                        for nct_id in self.nct_ids
                    ],
                    "totalCount": len(self.nct_ids),
                }
            )
        raise AssertionError(f"unexpected source path {path}")

    def close(self) -> None:
        self.closes += 1
        if self._close_error is not None:
            raise self._close_error


def _run_cli(
    lane: Lane,
    *,
    mode: str = "collect",
    transport: FakeTransport | None = None,
    environ: dict | None = None,
    now_fn=None,
    extra: list[str] | None = None,
    transport_factory=None,
    store_factory=None,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    argv = [
        "--mode",
        mode,
        "--manifest",
        str(lane.active),
        "--receipt-root",
        str(lane.receipt_root),
        "--run-root",
        str(lane.run_root),
        "--operational-root",
        str(lane.operational_root),
        *(extra or []),
    ]
    if transport_factory is None:
        holder = transport if transport is not None else FakeTransport(COHORT_A)

        def transport_factory(**_: object):  # noqa: ANN003 - test seam
            return holder

    code = cli.main(
        argv,
        environ={"BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED": "1"}
        if environ is None
        else environ,
        transport_factory=transport_factory,
        store_factory=(
            (lambda root: OperationalStore(root, repo_root=ROOT))
            if store_factory is None
            else store_factory
        ),
        trusted_uids=lane.uids,
        trusted_gids=lane.gids,
        repo_root=ROOT,
        now_fn=Clock() if now_fn is None else now_fn,
        stream=out,
        error_stream=err,
    )
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# 1. The frozen runtime contract
# ---------------------------------------------------------------------------


def test_runtime_paths_match_the_frozen_w1a_deployment_contract():
    assert RUNTIME_IDENTITY == "macro-biocatalyst-fixed-cohort"
    assert RUNTIME_ENV_FILE == "/etc/macro-biocatalyst-fixed-cohort.env"
    assert RUNTIME_CONFIG_ROOT == "/etc/macro-biocatalyst-fixed-cohort"
    assert RUNTIME_ACTIVE_POINTER_NAME == "active.json"
    assert runtime.RUNTIME_STATE_ROOT == "/var/lib/macro-biocatalyst-fixed-cohort"
    assert runtime.RUNTIME_RUN_ROOT == "/var/lib/macro-biocatalyst-fixed-cohort/runs"
    assert runtime.RUNTIME_RECEIPT_ROOT == "/var/lib/macro-biocatalyst-fixed-cohort/receipts"
    # The B0a worker lane is a different lane and must stay a different lane.
    assert B0A_MASKED_PATHS == (
        "/var/lib/macro-biocatalyst",
        "/etc/macro-biocatalyst.env",
        "/etc/macro-biocatalyst-control.env",
    )
    assert runtime.RUNTIME_STATE_ROOT not in B0A_MASKED_PATHS


def test_manifest_filename_is_digest_qualified_over_the_exact_file_bytes(cohort_a):
    name = manifest_filename(cohort_a)
    match = re.fullmatch(
        r"(ctgov_fixed_cohort_[a-f0-9]{24})\.([a-f0-9]{64})\.json", name
    )
    assert match is not None
    assert match.group(1) == cohort_a["cohort_id"]
    assert match.group(2) == hashlib.sha256(manifest_content_bytes(cohort_a)).hexdigest()
    # The filename digest hashes the FILE, not the contract's internal payload
    # digest; conflating the two would let a byte-level edit keep its name.
    assert match.group(2) != cohort_a["cohort_payload_sha256"]


# ---------------------------------------------------------------------------
# 2. Hostile loader tests
# ---------------------------------------------------------------------------


def test_loader_refuses_a_symlinked_active_pointer(lane, cohort_a):
    lane.install(cohort_a)
    real = manifest_path_for(lane.config_root, cohort_a)
    os.symlink(real, lane.active)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert excinfo.value.code == "MANIFEST_SYMLINK_REFUSED"


def test_loader_refuses_a_symlinked_manifest_directory(lane, cohort_a):
    lane.activate(cohort_a)
    elsewhere = lane.base / "elsewhere"
    elsewhere.mkdir()
    for entry in lane.manifest_root.iterdir():
        entry.replace(elsewhere / entry.name)
    lane.manifest_root.rmdir()
    os.symlink(elsewhere, lane.manifest_root)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert excinfo.value.code == "MANIFEST_SYMLINK_REFUSED"


def test_loader_refuses_a_fifo_in_place_of_the_pointer(lane):
    os.mkfifo(lane.active, 0o400)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code == "MANIFEST_NOT_REGULAR_FILE"


def test_loader_refuses_a_directory_in_place_of_the_pointer(lane):
    lane.active.mkdir()
    lane.active.chmod(0o755)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code == "MANIFEST_NOT_REGULAR_FILE"


def test_loader_refuses_a_device_like_special_file(lane, monkeypatch):
    # A real device node needs root; a unix socket is the same class of
    # non-regular node and needs no privilege to create.  AF_UNIX paths are
    # length-capped, so bind relatively from inside the config root.
    monkeypatch.chdir(lane.config_root)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(RUNTIME_ACTIVE_POINTER_NAME)
        with pytest.raises(FixedCohortRuntimeError) as excinfo:
            read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code in {"MANIFEST_NOT_REGULAR_FILE", "MANIFEST_UNREADABLE"}


def test_loader_refuses_a_hardlinked_manifest(lane, cohort_a):
    lane.activate(cohort_a)
    os.link(lane.active, lane.config_root / "alias.json")

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert excinfo.value.code == "MANIFEST_HARDLINKED"


def test_loader_refuses_a_path_swapped_underneath_the_descriptor(lane, cohort_a, monkeypatch):
    lane.activate(cohort_a)
    real_fstat = os.fstat
    calls = {"n": 0}

    def swapping_fstat(fd):
        info = real_fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            # Directory components of the walk are stat'd too; only the file's
            # own post-read confirmation stat is the one under test.
            return info
        calls["n"] += 1
        if calls["n"] == 2:
            return SimpleNamespace(
                st_dev=info.st_dev,
                st_ino=info.st_ino + 1,
                st_mode=info.st_mode,
                st_nlink=info.st_nlink,
                st_uid=info.st_uid,
                st_gid=info.st_gid,
                st_size=info.st_size,
                st_mtime_ns=info.st_mtime_ns,
                st_ctime_ns=info.st_ctime_ns,
            )
        return info

    monkeypatch.setattr(runtime.os, "fstat", swapping_fstat)
    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code == "MANIFEST_CHANGED_DURING_READ"


def test_loader_refuses_a_manifest_that_is_not_root_owned(lane, cohort_a):
    lane.activate(cohort_a)

    # Production trusts uid/gid 0 only; the test user's file is therefore the
    # exact "not root-owned" case an attacker would need.
    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_active_manifest(
            lane.config_root,
            repo_root=ROOT,
            trusted_uids=frozenset({0}),
            trusted_gids=frozenset({0}),
        )
    assert excinfo.value.code == "MANIFEST_OWNER_UNSAFE"


@pytest.mark.parametrize("mode", [0o666, 0o622, 0o606, 0o4444, 0o2444])
def test_loader_refuses_a_group_or_world_writable_manifest(
    lane, cohort_a, mode, monkeypatch
):
    lane.activate(cohort_a)
    if mode & (stat.S_ISUID | stat.S_ISGID):
        real_fstat = os.fstat
        active_stat = lane.active.stat()

        def unsafe_mode_fstat(fd):
            info = real_fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_dev != active_stat.st_dev
                or info.st_ino != active_stat.st_ino
            ):
                return info
            return SimpleNamespace(
                st_dev=info.st_dev,
                st_ino=info.st_ino,
                st_mode=(info.st_mode & ~0o7777) | mode,
                st_nlink=info.st_nlink,
                st_uid=info.st_uid,
                st_gid=info.st_gid,
                st_size=info.st_size,
                st_mtime_ns=info.st_mtime_ns,
                st_ctime_ns=info.st_ctime_ns,
            )

        # The sealed PC services deliberately set RestrictSUIDSGID=true, so
        # constructing a real set-ID fixture returns EPERM there.  Inject only
        # the descriptor metadata the loader consumes; do not weaken the host.
        monkeypatch.setattr(runtime.os, "fstat", unsafe_mode_fstat)
    else:
        lane.active.chmod(mode)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code == "MANIFEST_MODE_UNSAFE"


def test_loader_refuses_a_writable_manifest_directory(lane, cohort_a):
    lane.activate(cohort_a)
    lane.config_root.chmod(0o777)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code == "MANIFEST_MODE_UNSAFE"
    lane.config_root.chmod(0o755)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda raw: raw.rstrip(b"\n"), id="missing_terminal_lf"),
        pytest.param(lambda raw: raw + b"\n", id="second_terminal_lf"),
        pytest.param(lambda raw: b" " + raw, id="leading_whitespace"),
        pytest.param(
            lambda raw: json.dumps(
                json.loads(raw.decode()), indent=2, sort_keys=False
            ).encode()
            + b"\n",
            id="pretty_printed",
        ),
    ],
)
def test_parser_refuses_noncanonical_manifest_bytes(cohort_a, mutate):
    raw = mutate(manifest_content_bytes(cohort_a))

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        parse_manifest_bytes(raw)
    assert excinfo.value.code == "MANIFEST_NONCANONICAL_BYTES"


def test_parser_refuses_duplicate_json_keys(cohort_a):
    raw = manifest_content_bytes(cohort_a)
    injected = raw.replace(b'{"candidate_admission_policy"', b'{"cohort_id":"x","candidate_admission_policy"', 1)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        parse_manifest_bytes(injected)
    assert excinfo.value.code == "MANIFEST_NONCANONICAL_BYTES"


def test_loader_refuses_a_manifest_whose_filename_digest_lies(lane, cohort_a):
    installed = lane.install(cohort_a)
    wrong = lane.manifest_root / f"{cohort_a['cohort_id']}.{'0' * 64}.json"
    installed.replace(wrong)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_manifest_file(wrong, repo_root=ROOT, **lane.trust())
    assert excinfo.value.code == "MANIFEST_DIGEST_MISMATCH"


def test_loader_refuses_a_manifest_without_a_digest_qualified_name(lane, cohort_a):
    plain = lane.manifest_root / "cohort.json"
    atomic_write_bytes(plain, manifest_content_bytes(cohort_a), mode=0o444)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_manifest_file(plain, repo_root=ROOT, **lane.trust())
    assert excinfo.value.code == "MANIFEST_NAME_NOT_DIGEST_QUALIFIED"


def test_loader_refuses_a_hand_edited_membership_list(lane, cohort_a):
    lane.activate(cohort_a)
    tampered = dict(cohort_a)
    tampered["nct_ids"] = COHORT_A + ["NCT00009999"]
    lane.active.chmod(0o644)
    atomic_write_bytes(lane.active, canonical_json_bytes(tampered) + b"\n", mode=0o444)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    # The edit breaks the cohort's own identity digest long before anything
    # could ask the source about the extra identifier.
    assert excinfo.value.code == "MANIFEST_CONTRACT_INVALID"


def test_an_active_pointer_with_no_installed_manifest_fails_closed(lane, cohort_a, cohort_b):
    lane.activate(cohort_a)
    atomic_write_bytes(lane.active, manifest_content_bytes(cohort_b), mode=0o444)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert excinfo.value.code == "MANIFEST_UNREADABLE"


def test_loader_refuses_an_oversized_manifest(lane):
    atomic_write_bytes(lane.active, b"x" * (runtime.MANIFEST_MAX_BYTES + 1), mode=0o444)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file(lane.active, **lane.trust())
    assert excinfo.value.code == "MANIFEST_SIZE_OUT_OF_BOUNDS"


def test_loader_refuses_a_relative_manifest_path():
    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        read_trusted_file("etc/macro-biocatalyst-fixed-cohort/active.json")
    assert excinfo.value.code == "MANIFEST_PATH_UNSAFE"


# ---------------------------------------------------------------------------
# 3. Install and rotation lifecycle
# ---------------------------------------------------------------------------


def test_installed_manifests_are_immutable_and_read_only(lane, cohort_a):
    path = lane.install(cohort_a)

    assert path.name == manifest_filename(cohort_a)
    assert stat.S_IMODE(path.stat().st_mode) == 0o444
    # Re-installing identical bytes is an idempotent no-op, not an overwrite.
    assert lane.install(cohort_a) == path


def test_install_refuses_different_bytes_at_an_occupied_path(lane, cohort_a):
    path = lane.install(cohort_a)
    path.chmod(0o644)
    path.write_bytes(manifest_content_bytes(cohort_a).replace(b"NCT00000001", b"NCT00000009"))
    path.chmod(0o444)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        lane.install(cohort_a)
    assert excinfo.value.code == "MANIFEST_IMMUTABLE_COLLISION"


def test_rotation_records_a_receipt_then_moves_the_pointer(lane, cohort_a, cohort_b):
    store = lane.store()
    first = rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=store,
        repo_root=ROOT,
        **lane.trust(),
    )
    assert first["previous_cohort_id"] is None
    assert first["ruling_ref"] == ROTATION_RECEIPT_RULING_REF

    second = rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_b,
        actor="operator",
        known_time=LATER_TIME,
        store=store,
        repo_root=ROOT,
        **lane.trust(),
    )
    assert second["previous_cohort_id"] == cohort_a["cohort_id"]
    assert second["previous_manifest_sha256"] == manifest_content_sha256(cohort_a)
    assert second["next_cohort_id"] == cohort_b["cohort_id"]
    assert second["actor"] == "operator"

    active = load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert active.cohort_id == cohort_b["cohort_id"]
    assert active.raw_bytes == manifest_content_bytes(cohort_b)
    assert active_pointer_matches_receipt(
        lane.config_root, second, repo_root=ROOT, **lane.trust()
    )

    # The prior immutable manifest and BOTH receipts survive the rotation.
    assert manifest_path_for(lane.config_root, cohort_a).is_file()
    for receipt in (first, second):
        path = runtime.rotation_receipt_path(lane.receipt_root, receipt)
        assert path.is_file()
        assert json.loads(path.read_text()) == receipt
        assert stat.S_IMODE(path.stat().st_mode) == 0o400

    page = store.read(ROTATION_RECORD_KIND, limit=10)
    recorded = [record["payload"] for record in page.records]
    assert [entry["queue_item_id"] for entry in recorded] == [
        f"fixed_cohort_membership.{cohort_a['cohort_id']}",
        f"fixed_cohort_membership.{cohort_b['cohort_id']}",
    ]
    # The ledger entry points at the immutable receipt by content address, so
    # the full old/new binding is one deterministic hop away.
    assert recorded[1]["rationale_ref"] == f"internal:{runtime.rotation_receipt_id(second)}"


def test_rollback_uses_the_same_validated_copy_path_and_never_edits_in_place(
    lane, cohort_a, cohort_b
):
    store = lane.store()
    for document, when in ((cohort_a, KNOWN_TIME), (cohort_b, LATER_TIME)):
        rotate_active_manifest(
            config_root=lane.config_root,
            receipt_root=lane.receipt_root,
            document=document,
            actor="operator",
            known_time=when,
            store=store,
            repo_root=ROOT,
            **lane.trust(),
        )
    before = manifest_path_for(lane.config_root, cohort_a).read_bytes()

    receipt = rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time="2026-08-07T13:00:00.000000Z",
        store=store,
        rotation_kind="rollback",
        repo_root=ROOT,
        **lane.trust(),
    )

    assert receipt["rotation_kind"] == "rollback"
    assert receipt["previous_cohort_id"] == cohort_b["cohort_id"]
    assert receipt["next_cohort_id"] == cohort_a["cohort_id"]
    assert manifest_path_for(lane.config_root, cohort_a).read_bytes() == before
    active = load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert active.raw_bytes == before


def test_stale_rollback_to_an_uninstalled_manifest_is_refused(lane, cohort_a, cohort_b):
    store = lane.store()
    rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=store,
        repo_root=ROOT,
        **lane.trust(),
    )

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        rotate_active_manifest(
            config_root=lane.config_root,
            receipt_root=lane.receipt_root,
            document=cohort_b,
            actor="operator",
            known_time=LATER_TIME,
            store=store,
            rotation_kind="rollback",
            repo_root=ROOT,
            **lane.trust(),
        )
    assert excinfo.value.code == "ROLLBACK_TARGET_NOT_INSTALLED"
    active = load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert active.cohort_id == cohort_a["cohort_id"]


def test_a_partial_rotation_leaves_the_pointer_untouched(lane, cohort_a, cohort_b):
    store = lane.store()
    rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=store,
        repo_root=ROOT,
        **lane.trust(),
    )

    class RefusingStore(OperationalStore):
        def append(self, *args, **kwargs):  # noqa: ANN002 - test seam
            raise OperationalStoreUnavailableError("OPERATIONAL_STATE_ROOT_UNWRITABLE")

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        rotate_active_manifest(
            config_root=lane.config_root,
            receipt_root=lane.receipt_root,
            document=cohort_b,
            actor="operator",
            known_time=LATER_TIME,
            store=RefusingStore(lane.operational_root, repo_root=ROOT),
            repo_root=ROOT,
            **lane.trust(),
        )
    assert excinfo.value.code == "ROTATION_RECEIPT_REFUSED"
    active = load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert active.cohort_id == cohort_a["cohort_id"]


def test_a_rotation_interrupted_before_the_swap_is_detectable_not_silent(
    lane, cohort_a, cohort_b, monkeypatch
):
    store = lane.store()
    rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=store,
        repo_root=ROOT,
        **lane.trust(),
    )
    real_replace = os.replace

    def crash_on_the_pointer_swap(src, dst, *args, **kwargs):
        # Crash at step 4 only: the receipt has landed, the pointer has not.
        if Path(dst).name == RUNTIME_ACTIVE_POINTER_NAME:
            raise OSError(errno.EIO, "crash between fsync and rename")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(runtime.os, "replace", crash_on_the_pointer_swap)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        rotate_active_manifest(
            config_root=lane.config_root,
            receipt_root=lane.receipt_root,
            document=cohort_b,
            actor="operator",
            known_time=LATER_TIME,
            store=store,
            repo_root=ROOT,
            **lane.trust(),
        )
    assert excinfo.value.code == "RUNTIME_WRITE_FAILED"
    monkeypatch.undo()
    active = load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust())
    assert active.cohort_id == cohort_a["cohort_id"]

    # The receipt precedes the swap by design, so the surviving evidence must
    # not be able to claim a rotation that did not take effect.
    receipts = sorted(lane.receipt_root.rglob("fixed_cohort_rotation.*.json"))
    assert len(receipts) == 2
    stranded = [
        json.loads(path.read_text())
        for path in receipts
        if json.loads(path.read_text())["next_cohort_id"] == cohort_b["cohort_id"]
    ]
    assert len(stranded) == 1
    assert not active_pointer_matches_receipt(
        lane.config_root, stranded[0], repo_root=ROOT, **lane.trust()
    )
    assert len(store.read(ROTATION_RECORD_KIND, limit=10).records) == 2
    assert not list(lane.config_root.glob("*.tmp"))


def test_concurrent_rotations_are_refused_and_a_reader_sees_only_complete_bytes(
    lane, cohort_a, cohort_b
):
    store = lane.store()
    rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=store,
        repo_root=ROOT,
        **lane.trust(),
    )
    observed: list[str] = []
    refused: list[str] = []

    class ReentrantStore(OperationalStore):
        def append(self, *args, **kwargs):  # noqa: ANN002 - test seam
            # Mid-rotation, before the pointer moves: a concurrent reader must
            # still see the complete OLD membership, and a concurrent rotation
            # must be refused rather than interleaved.
            observed.append(
                load_active_manifest(
                    lane.config_root, repo_root=ROOT, **lane.trust()
                ).cohort_id
            )
            try:
                rotate_active_manifest(
                    config_root=lane.config_root,
                    receipt_root=lane.receipt_root,
                    document=cohort_b,
                    actor="operator",
                    known_time="2026-08-07T12:00:00.000000Z",
                    store=lane.store(),
                    repo_root=ROOT,
                    **lane.trust(),
                )
            except FixedCohortRuntimeError as exc:
                refused.append(exc.code)
            return super().append(*args, **kwargs)

    rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_b,
        actor="operator",
        known_time=LATER_TIME,
        store=ReentrantStore(lane.operational_root, repo_root=ROOT),
        repo_root=ROOT,
        **lane.trust(),
    )

    assert observed == [cohort_a["cohort_id"]]
    assert refused == ["ROTATION_IN_PROGRESS"]
    assert (
        load_active_manifest(lane.config_root, repo_root=ROOT, **lane.trust()).cohort_id
        == cohort_b["cohort_id"]
    )


def test_a_rotation_needs_a_named_actor_and_a_known_time(lane, cohort_a):
    for actor, when, code in (
        ("", KNOWN_TIME, "ROTATION_ACTOR_INVALID"),
        ("Operator Name", KNOWN_TIME, "ROTATION_ACTOR_INVALID"),
        ("operator", "2026-08-07", "ROTATION_KNOWN_TIME_INVALID"),
    ):
        with pytest.raises(FixedCohortRuntimeError) as excinfo:
            rotate_active_manifest(
                config_root=lane.config_root,
                receipt_root=lane.receipt_root,
                document=cohort_a,
                actor=actor,
                known_time=when,
                store=lane.store(),
                repo_root=ROOT,
                **lane.trust(),
            )
        assert excinfo.value.code == code
    assert not lane.active.exists()


def test_rotation_receipt_is_registered_and_semantically_guarded(lane, cohort_a):
    receipt = rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=lane.store(),
        repo_root=ROOT,
        **lane.trust(),
    )
    assert ROTATION_RECEIPT_CONTRACT_ID in ContractRegistry(ROOT).contract_ids

    tampered = dict(receipt)
    tampered["next_manifest_sha256"] = "0" * 64
    with pytest.raises(ContractValidationError):
        runtime.validate_manifest_rotation_receipt(tampered, repo_root=ROOT)

    no_op = dict(receipt)
    no_op["previous_cohort_id"] = no_op["next_cohort_id"]
    no_op["previous_manifest_sha256"] = no_op["next_manifest_sha256"]
    codes = {
        issue.code
        for issue in runtime.manifest_rotation_receipt_semantic_issues(no_op)
    }
    assert "manifest_rotation.no_op" in codes


def test_the_rotation_ledger_entry_satisfies_the_o1a_authority_fence(lane, cohort_a):
    """BC-O1a must accept the ledger entry on its own closed terms."""

    receipt = rotate_active_manifest(
        config_root=lane.config_root,
        receipt_root=lane.receipt_root,
        document=cohort_a,
        actor="operator",
        known_time=KNOWN_TIME,
        store=lane.store(),
        repo_root=ROOT,
        **lane.trust(),
    )
    stored = lane.store().read(ROTATION_RECORD_KIND, limit=1).records[0]

    assert stored["payload"] == runtime.rotation_ledger_payload(receipt)
    assert stored["authority"] == "facts_and_context_only"
    assert stored["corrects_record_id"] is None
    # This projection exists only because BC-O1a has no membership-rotation
    # kind.  If one is ever added, this assertion fails and the projection
    # should be replaced by it rather than quietly kept.
    assert "membership_rotation_receipt" not in operational_record_kinds()
    assert ROTATION_RECORD_KIND in operational_record_kinds()
    assert set(stored["payload"]) == {
        "decision_id",
        "queue_item_id",
        "decision_state",
        "decided_by_kind",
        "rationale_ref",
    }


# ---------------------------------------------------------------------------
# 4. Environment fence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "BIOCATALYST_FIXED_COHORT_NCTS",
        "BIOCATALYST_CANARY_NCTS",
        "BIOCATALYST_COHORT_ID",
        "SOME_ALLOWLIST",
        "COHORT_MEMBERSHIP",
        "BIOCATALYST_NCT_IDS",
    ],
)
def test_environment_membership_names_are_refused(name):
    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        assert_environment_carries_no_membership({name: "anything"})
    assert excinfo.value.code == "ENVIRONMENT_MEMBERSHIP_ATTEMPT"


def test_environment_values_naming_a_trial_are_refused():
    with pytest.raises(FixedCohortRuntimeError):
        assert_environment_carries_no_membership({"HARMLESS_NAME": "NCT00000001"})


def test_the_fence_does_not_fire_on_innocent_or_lane_owned_names():
    innocent = {
        "BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED": "1",
        "BIOCATALYST_FIXED_COHORT_USER_AGENT": "MastermindX contact@example.invalid",
        # "FUNCTION" contains the substring "NCT"; a substring rule would refuse
        # this and get itself disabled by the first operator it inconvenienced.
        "AWS_LAMBDA_FUNCTION_NAME": "unrelated",
        "PATH": "/usr/bin:/bin",
    }
    assert membership_environment_offences(innocent) == ()
    assert_environment_carries_no_membership(innocent)


def test_the_membership_fence_tokens_are_declared_in_both_the_runtime_and_the_installer():
    setup = _text(SETUP_PATH)
    for segment in MEMBERSHIP_ENV_SEGMENTS:
        assert re.search(rf"^\t{segment}$", setup, re.MULTILINE), segment
    for phrase in MEMBERSHIP_ENV_PHRASES:
        assert re.search(rf"^\t{phrase}$", setup, re.MULTILINE), phrase


# ---------------------------------------------------------------------------
# 5. The runtime CLI
# ---------------------------------------------------------------------------


def test_the_cli_exposes_no_membership_argument():
    parser = cli.build_parser()
    options = {
        option
        for action in parser._actions  # noqa: SLF001 - argparse has no public view
        for option in action.option_strings
    }
    assert "--manifest" in options
    assert "--receipt-root" in options
    for token in cli.FORBIDDEN_ARGUMENT_TOKENS:
        assert f"--{token}" not in options
    # Even an abbreviation must not become a membership door.
    assert parser.allow_abbrev is False

    # Read the declared options out of the source itself, so a future option
    # added anywhere in this module is caught, not just the ones parsed above.
    declared = {
        argument.value
        for node in ast.walk(ast.parse(_text(CLI_PATH)))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }
    assert declared, "the parser must declare its options as literals"
    for option in declared:
        stem = option.lstrip("-").replace("-", "_").lower()
        for token in cli.FORBIDDEN_ARGUMENT_TOKENS:
            assert token.replace("-", "_") not in stem, option


def test_a_collect_run_binds_the_active_manifest_and_appends_the_o1a_receipt(
    lane, cohort_a
):
    lane.activate(cohort_a)
    transport = FakeTransport(COHORT_A)

    code, out, err = _run_cli(lane, transport=transport)

    assert code == cli.EXIT_OK, err
    summary = json.loads(out)
    assert summary["run_state"] == "complete"
    assert summary["cohort_id"] == cohort_a["cohort_id"]
    assert summary["active_manifest_sha256"] == manifest_content_sha256(cohort_a)
    assert transport.paths == ["/version", "/studies", "/version"]
    assert transport.closes == 1

    run_id = summary["run_id"]
    evidence = lane.run_root / run_id
    assert (evidence / "run.json").is_file()
    binding = json.loads((evidence / "active_manifest.json").read_text())
    assert binding["active_manifest_sha256"] == manifest_content_sha256(cohort_a)
    assert binding["ruling_ref"] == ROTATION_RECEIPT_RULING_REF
    receipt_file = Path(summary["receipt_path"])
    assert receipt_file.is_file()
    assert receipt_file.parent.name == "08" and receipt_file.parent.parent.name == "2026"

    stored = lane.store().read(runtime.RUN_RECORD_KIND, limit=5).records
    assert len(stored) == 1
    payload = stored[0]["payload"]
    assert payload["run_id"] == run_id
    assert payload["source_id"] == runtime.RUN_RECEIPT_SOURCE_ID
    assert payload["run_state"] == "complete"
    # BC-O1a's source_run_receipt payload is closed, so the NCT-level
    # reconciliation stays private and is bound by content instead.
    assert set(payload) == {
        "source_id",
        "run_id",
        "started_at",
        "finished_at",
        "run_state",
        "evidence_sha256",
    }
    assert payload["evidence_sha256"] == hashlib.sha256(
        (evidence / "run.json").read_bytes()
        + (evidence / "active_manifest.json").read_bytes()
    ).hexdigest()


def test_collect_uses_the_root_owned_environment_contact(lane, cohort_a):
    lane.activate(cohort_a)
    captured = {}

    def transport_factory(**kwargs):
        captured.update(kwargs)
        return FakeTransport(COHORT_A)

    code, _, err = _run_cli(
        lane,
        environ={
            "BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED": "1",
            "BIOCATALYST_FIXED_COHORT_USER_AGENT": (
                "MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)"
            ),
        },
        transport_factory=transport_factory,
    )

    assert code == cli.EXIT_OK, err
    assert captured["user_agent"] == (
        "MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)"
    )


def test_explicit_user_agent_overrides_the_environment_contact(lane, cohort_a):
    lane.activate(cohort_a)
    captured = {}

    def transport_factory(**kwargs):
        captured.update(kwargs)
        return FakeTransport(COHORT_A)

    code, _, err = _run_cli(
        lane,
        environ={
            "BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED": "1",
            "BIOCATALYST_FIXED_COHORT_USER_AGENT": "environment contact",
        },
        extra=["--user-agent", "explicit contact"],
        transport_factory=transport_factory,
    )

    assert code == cli.EXIT_OK, err
    assert captured["user_agent"] == "explicit contact"


def test_an_invalid_environment_contact_fails_before_transport(lane, cohort_a):
    lane.activate(cohort_a)
    constructed = False

    def transport_factory(**_):
        nonlocal constructed
        constructed = True
        return FakeTransport(COHORT_A)

    code, _, err = _run_cli(
        lane,
        environ={
            "BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED": "1",
            "BIOCATALYST_FIXED_COHORT_USER_AGENT": "",
        },
        transport_factory=transport_factory,
    )

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "USER_AGENT_INVALID"
    assert constructed is False


def test_a_receipt_store_outage_fails_closed_before_any_collection(lane, cohort_a):
    lane.activate(cohort_a)
    (lane.operational_root / "store_meta.json").unlink()
    transport = FakeTransport(COHORT_A)

    code, _, err = _run_cli(lane, transport=transport)

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "OPERATIONAL_STORE_UNAVAILABLE"
    # The decisive assertion: the source was never contacted.
    assert transport.paths == []


def test_a_receipt_refusal_after_collection_is_reported_not_swallowed(lane, cohort_a):
    lane.activate(cohort_a)

    class RefusingStore(OperationalStore):
        def append(self, *args, **kwargs):  # noqa: ANN002 - test seam
            raise OperationalStoreError("OPERATIONAL_STATE_ROOT_UNWRITABLE")

    code, _, err = _run_cli(
        lane,
        transport=FakeTransport(COHORT_A),
        store_factory=lambda root: RefusingStore(root, repo_root=ROOT),
    )

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "OPERATIONAL_RECEIPT_REFUSED"


def test_a_replayed_run_is_idempotent_and_a_conflicting_one_is_refused(lane, cohort_a):
    lane.activate(cohort_a)
    first_code, first_out, _ = _run_cli(lane, transport=FakeTransport(COHORT_A))
    assert first_code == cli.EXIT_OK
    run_id = json.loads(first_out)["run_id"]

    replay_code, replay_out, replay_err = _run_cli(lane, transport=FakeTransport(COHORT_A))
    assert replay_code == cli.EXIT_OK, replay_err
    assert json.loads(replay_out)["run_id"] == run_id
    assert len(lane.store().read(runtime.RUN_RECORD_KIND, limit=5).records) == 1

    evidence = lane.run_root / run_id / "run.json"
    evidence.chmod(0o644)
    evidence.write_bytes(b'{"tampered":true}\n')
    conflict_code, _, conflict_err = _run_cli(lane, transport=FakeTransport(COHORT_A))
    assert conflict_code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(conflict_err)["error_code"] == "DUPLICATE_RUN_ID"


def test_a_disk_full_write_leaves_no_partial_evidence(lane, cohort_a, monkeypatch):
    lane.activate(cohort_a)
    real_fsync = os.fsync

    def full_disk(fd):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(runtime.os, "fsync", full_disk)
    code, _, err = _run_cli(lane, transport=FakeTransport(COHORT_A))
    monkeypatch.setattr(runtime.os, "fsync", real_fsync)

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "RUNTIME_DISK_FULL"
    assert list(lane.run_root.rglob("run.json")) == []
    assert list(lane.run_root.rglob("*.tmp")) == []


def test_a_crash_between_write_and_rename_leaves_no_visible_file(lane, cohort_a, monkeypatch):
    lane.activate(cohort_a)
    monkeypatch.setattr(
        runtime.os,
        "replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError(errno.EIO, "crash")),
    )

    code, _, err = _run_cli(lane, transport=FakeTransport(COHORT_A))

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "RUNTIME_WRITE_FAILED"
    assert list(lane.run_root.rglob("run.json")) == []
    assert list(lane.run_root.rglob("*.tmp")) == []


def test_an_environment_that_names_a_trial_stops_the_run_before_the_transport(lane, cohort_a):
    lane.activate(cohort_a)
    transport = FakeTransport(COHORT_A)

    code, _, err = _run_cli(
        lane,
        transport=transport,
        environ={
            "BIOCATALYST_FIXED_COHORT_TRANSPORT_ENABLED": "1",
            "BIOCATALYST_FIXED_COHORT_NCTS": "NCT00009999",
        },
    )

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "ENVIRONMENT_MEMBERSHIP_ATTEMPT"
    assert transport.paths == []


def test_a_close_failure_never_replaces_a_propagating_primary_error(
    lane, cohort_a, monkeypatch
):
    lane.activate(cohort_a)

    class ExplodingRun:
        def __init__(self, **_: object) -> None:
            raise cli.FixedCohortTransportError(
                "INVALID_FIXED_COHORT", "the primary failure"
            )

    monkeypatch.setattr(cli, "ClinicalTrialsFixedCohortTransportRun", ExplodingRun)
    transport = FakeTransport(COHORT_A, close_error=OSError("close failed second"))

    code, _, err = _run_cli(lane, transport=transport)

    assert transport.closes == 1
    assert code == cli.EXIT_PRECONDITION_FAILED
    # The cleanup failure is strictly less informative than the cause that was
    # already propagating, so the cause stays authoritative.
    assert json.loads(err)["error_code"] == "INVALID_FIXED_COHORT"


def test_a_close_failure_is_reported_but_never_costs_the_run_its_receipt(lane, cohort_a):
    lane.activate(cohort_a)
    transport = FakeTransport(COHORT_A, close_error=OSError("close failed"))

    code, _, err = _run_cli(lane, transport=transport)

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "TRANSPORT_CLOSE_FAILED"
    # The decisive assertion: the run that actually happened is still recorded.
    assert len(lane.store().read(runtime.RUN_RECORD_KIND, limit=5).records) == 1
    assert list(lane.run_root.rglob("run.json"))


def test_verify_mode_reads_the_lane_without_touching_the_source(lane, cohort_a):
    lane.activate(cohort_a)

    def exploding_factory(**_: object):
        raise AssertionError("verify must never construct a transport")

    code, out, err = _run_cli(
        lane, mode="verify", transport_factory=exploding_factory
    )

    assert code == cli.EXIT_OK, err
    summary = json.loads(out)
    assert summary["member_count"] == len(COHORT_A)
    assert summary["operational_store_available"] is True
    assert list(lane.run_root.iterdir()) == []


def test_the_cli_rotates_and_rolls_back_through_the_validated_path(lane, cohort_a, cohort_b):
    lane.activate(cohort_a)
    staged = lane.base / "staged.json"
    atomic_write_bytes(staged, manifest_content_bytes(cohort_b), mode=0o444)

    code, out, err = _run_cli(
        lane,
        mode="rotate",
        extra=[
            "--incoming-manifest",
            str(staged),
            "--actor",
            "operator",
            "--known-time",
            LATER_TIME,
        ],
        transport_factory=lambda **_: (_ for _ in ()).throw(
            AssertionError("rotation must never construct a transport")
        ),
    )
    assert code == cli.EXIT_OK, err
    assert json.loads(out)["next_cohort_id"] == cohort_b["cohort_id"]

    code, out, err = _run_cli(
        lane,
        mode="rollback",
        extra=[
            "--incoming-manifest",
            str(manifest_path_for(lane.config_root, cohort_a)),
            "--actor",
            "operator",
            "--known-time",
            "2026-08-07T14:00:00.000000Z",
        ],
        transport_factory=lambda **_: (_ for _ in ()).throw(
            AssertionError("rollback must never construct a transport")
        ),
    )
    assert code == cli.EXIT_OK, err
    assert json.loads(out)["next_cohort_id"] == cohort_a["cohort_id"]


def test_the_cli_refuses_an_unattributed_rotation(lane, cohort_a, cohort_b):
    lane.activate(cohort_a)
    staged = lane.base / "staged.json"
    atomic_write_bytes(staged, manifest_content_bytes(cohort_b), mode=0o444)

    code, _, err = _run_cli(
        lane,
        mode="rotate",
        extra=["--incoming-manifest", str(staged)],
        transport_factory=lambda **_: None,
    )

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err)["error_code"] == "ROTATION_ARGUMENT_MISSING"


def test_the_manifest_argument_must_name_the_active_pointer(lane, cohort_a):
    lane.activate(cohort_a)
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        [
            "--mode",
            "verify",
            "--manifest",
            str(manifest_path_for(lane.config_root, cohort_a)),
            "--receipt-root",
            str(lane.receipt_root),
            "--operational-root",
            str(lane.operational_root),
        ],
        environ={},
        store_factory=lambda root: OperationalStore(root, repo_root=ROOT),
        trusted_uids=lane.uids,
        trusted_gids=lane.gids,
        repo_root=ROOT,
        stream=out,
        error_stream=err,
    )

    assert code == cli.EXIT_PRECONDITION_FAILED
    assert json.loads(err.getvalue())["error_code"] == "MANIFEST_ARGUMENT_INVALID"


# ---------------------------------------------------------------------------
# 6. Deployment artifacts: installable and inert
# ---------------------------------------------------------------------------


def _setup_executable_lines() -> str:
    """Return only the installer's executable lines.

    Comments and the operator-facing ``unmask_note`` heredoc are prose: they may
    legitimately *name* the arming command that this script must never run.
    """

    setup = _text(SETUP_PATH)
    start = setup.index("unmask_note() {")
    end = setup.index("\n}\n", start)
    without_note = setup[:start] + setup[end:]
    return "\n".join(
        line
        for line in without_note.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


def test_deployment_scripts_have_valid_syntax():
    subprocess.run(["bash", "-n", str(SETUP_PATH)], check=True)
    subprocess.run([sys.executable, "-m", "py_compile", str(CLI_PATH)], check=True)


def test_the_installer_never_enables_starts_or_unmasks_the_unit():
    executable = _setup_executable_lines()

    for forbidden in (
        "systemctl enable",
        "systemctl start",
        "systemctl unmask",
        "--now",
    ):
        assert forbidden not in executable, forbidden
    assert "systemctl daemon-reload" in executable
    assert "systemctl mask" in executable
    assert 'die "must run as root"' in executable
    # The operator-facing note is allowed to *print* the arming command; it must
    # remain the only executable line that mentions it, and it only echoes text.
    note = _text(SETUP_PATH)
    note = note[note.index("unmask_note() {") : note.index("\n}\n", note.index("unmask_note() {"))]
    assert "systemctl enable --now macro-biocatalyst-fixed-cohort.timer" in note
    assert "systemctl" not in note.split("NOTE", 1)[0]


def test_reconciliation_only_touches_already_installed_units():
    setup = _text(SETUP_PATH)
    body = setup.split("reconcile_units() {", 1)[1].split("\n}\n", 1)[0]

    assert 'if [ ! -f "$SERVICE_DEST" ] || [ ! -f "$TIMER_DEST" ]; then' in body
    assert "nothing to reconcile" in body
    assert "systemctl enable" not in body
    assert "systemctl start" not in body
    # Arming state is preserved, never created.
    assert 'if systemctl is-enabled --quiet "$TIMER_UNIT"' in body
    assert 'systemctl restart "$TIMER_UNIT"' in body


def test_the_installer_provisions_least_privilege_ownership_and_modes():
    setup = _text(SETUP_PATH)

    assert 'install -d -o root -g root -m 0755 "$CONFIG_ROOT"' in setup
    assert 'install -d -o root -g root -m 0755 "$MANIFEST_ROOT"' in setup
    for private in ("RUN_ROOT", "RECEIPT_ROOT", "OPERATIONAL_ROOT"):
        assert (
            f'install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "${private}"'
            in setup
        ), private
    assert 'chown root:root "$ENV_FILE"' in setup
    assert 'chmod 0600 "$ENV_FILE"' in setup
    assert '[ "$mode" = "600" ]' in setup
    assert '[ "$owner" = "root:root" ]' in setup
    assert "must set a non-empty BIOCATALYST_FIXED_COHORT_USER_AGENT" in setup
    assert 'bash "$RUNTIME_INSTALLER" --install-fixed-cohort "$REQUIREMENTS_SOURCE"' in setup
    assert 'bash "$RUNTIME_INSTALLER" --verify-fixed-cohort' in setup
    assert 'runuser -u "$SERVICE_USER" -- "$RUNTIME_CURRENT/bin/python"' in setup
    assert "provision_operational_store(root)" in setup
    assert "OperationalStore(root)" in setup
    assert "operational_store provision" in setup
    assert "operational_store verify" in setup
    assert setup.index("ensure_service_identity") < setup.index("ensure_runtime")
    # The active pointer is a real file. A symlink is a membership bypass.
    assert 'die "$ACTIVE_POINTER must never be a symlink"' in setup
    # Least privilege: this identity must not inherit the B0a lane's group.
    assert "must not be a member of the B0a macro-biocatalyst group" in setup


def test_the_fixed_cohort_runtime_is_transactional_and_separately_owned():
    runtime = _text(ROOT / "app" / "deploy" / "biocatalyst-runtime.sh")

    for token in (
        "--install-fixed-cohort",
        "--verify-fixed-cohort",
        "SERVICE_USER=macro-biocatalyst-fixed-cohort",
        "SERVICE_GROUP=macro-biocatalyst-fixed-cohort",
        "RUNTIME_ROOT=/opt/macro-biocatalyst-fixed-cohort",
        "SETUP_SCRIPT=biocatalyst-fixed-cohort-setup.sh",
    ):
        assert token in runtime
    assert 'mv -Tf "$next_link" "$CURRENT_LINK"' in runtime
    assert 'chown -hR root:"$SERVICE_GROUP" "$staging_runtime"' in runtime
    assert 'rm -f -- "$CURRENT_LINK"' not in runtime


def test_the_installer_and_unit_do_not_overlap_the_b0a_worker_lane():
    setup = _text(SETUP_PATH)
    service = _text(SERVICE_PATH)

    assert "assert_b0a_untouched" in setup
    for masked in B0A_MASKED_PATHS:
        assert f"InaccessiblePaths={masked}" in service
    assert "install -m 0644" in setup
    # The installer must never write into the B0a state root.
    assert 'install -d -o root -g root -m 0755 "$B0A_STATE_ROOT"' not in setup


def test_the_unit_is_a_bounded_hardened_oneshot_with_no_publication_credentials():
    service = _text(SERVICE_PATH)

    assert "Type=oneshot" in service
    assert f"User={RUNTIME_IDENTITY}" in service
    assert f"Group={RUNTIME_IDENTITY}" in service
    assert f"ConditionPathExists={RUNTIME_ENV_FILE}" in service
    assert f"EnvironmentFile={RUNTIME_ENV_FILE}" in service
    assert (
        "--manifest /etc/macro-biocatalyst-fixed-cohort/active.json" in service
    )
    assert "-m scripts.biocatalyst_fixed_cohort_transport --mode collect" in service
    timeout = int(re.search(r"^TimeoutStartSec=(\d+)$", service, re.MULTILINE).group(1))
    assert 0 < timeout <= 900

    for setting in (
        "UMask=0077",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        f"ReadOnlyPaths={RUNTIME_CONFIG_ROOT}",
        "ReadWritePaths=/var/lib/macro-biocatalyst-fixed-cohort/runs",
        "ReadWritePaths=/var/lib/macro-biocatalyst-fixed-cohort/receipts",
        "ReadWritePaths=/var/lib/macro-biocatalyst-fixed-cohort/operational",
        "ProtectKernelTunables=true",
        "ProtectKernelModules=true",
        "ProtectControlGroups=true",
        "ProtectKernelLogs=true",
        "ProtectClock=true",
        "ProtectHostname=true",
        "ProtectProc=invisible",
        "ProcSubset=pid",
        "RestrictSUIDSGID=true",
        "RestrictNamespaces=true",
        "RestrictRealtime=true",
        "LockPersonality=true",
        "SystemCallArchitectures=native",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
    ):
        assert setting in service, setting
    assert re.search(r"^CapabilityBoundingSet=$", service, re.MULTILINE)
    assert re.search(r"^AmbientCapabilities=$", service, re.MULTILINE)

    # This runtime holds no R2 credentials and cannot write the public
    # projection, so a later lane cannot quietly inherit publication rights.
    assert "BIOCATALYST_R2_" not in service
    assert "ReadWritePaths=/var/lib/macro-biocatalyst/public" not in service
    assert "DynamicUser=" not in service
    assert "Restart=always" not in service
    assert "[Install]" not in service


def test_the_timer_is_installed_disabled_and_names_this_service_only():
    timer = _text(TIMER_PATH)

    assert "Unit=macro-biocatalyst-fixed-cohort.service" in timer
    assert "WantedBy=timers.target" in timer
    assert "Persistent=false" in timer
    assert "operator-armed only" in timer
    assert "macro-biocatalyst.service" not in timer.replace(
        "macro-biocatalyst-fixed-cohort.service", ""
    )


def test_the_lane_adds_no_http_route_and_imports_no_web_framework():
    source = _text(CLI_PATH) + _text(RUNTIME_PATH)

    for forbidden in ("fastapi", "APIRouter", "add_api_route", "@router", "@app."):
        assert forbidden not in source, forbidden
    # Nothing in the deployment artifacts serves anything.
    for path in (SERVICE_PATH, TIMER_PATH, SETUP_PATH):
        assert "Caddyfile" not in _text(path)


def test_the_lane_opens_no_outcome_family_clock_and_cites_the_ruling():
    """The ruling is explicit: no clock opens through a config or code edit."""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert (
        schema["properties"]["ruling_ref"]["const"]
        == "research/BIOCATALYST_OPERATOR_RULING_2026-08-07.md"
    )
    for path in (RUNTIME_PATH, CLI_PATH, SETUP_PATH):
        assert "BIOCATALYST_OPERATOR_RULING_2026-08-07" in _text(path), path
    corpus = _text(RUNTIME_PATH) + _text(CLI_PATH) + _text(SETUP_PATH)
    for forbidden in (
        "outcome_family",
        "accruing_since",
        "first_seen_clock",
        "clock_opened",
    ):
        assert forbidden not in corpus, forbidden


def test_the_new_test_module_is_owned_by_a_bounded_ci_lane():
    legacy_jobs = _text(LEGACY_JOBS_PATH)
    assert "tests/test_biocatalyst_fixed_cohort_deployment.py" in legacy_jobs


def test_require_operational_store_available_reports_a_missing_root(tmp_path):
    store = OperationalStore(tmp_path / "absent", repo_root=ROOT)

    with pytest.raises(FixedCohortRuntimeError) as excinfo:
        require_operational_store_available(store)
    assert excinfo.value.code == "OPERATIONAL_STORE_UNAVAILABLE"
