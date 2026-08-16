from __future__ import annotations

import ast
import copy
import fcntl
import hashlib
import json
import os
import stat
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_options_sparse_selector as runner


UTC = timezone.utc
NOW = datetime(2026, 8, 14, 14, 0, 0, tzinfo=UTC)
REPOSITORY = runner.RepositoryState(
    head_commit="a" * 40,
    origin_main_commit="b" * 40,
    origin_main_committed_at="2026-08-14T13:55:00.000000Z",
)
BODIES = {
    runner.CAMPAIGNS_PATH: b"campaigns\n",
    runner.EPISODES_PATH: b"episodes\n",
    runner.CHECKPOINT_PATH: b"checkpoint\n",
}
OIDS = {path: runner._git_blob_oid(body) for path, body in BODIES.items()}
OPERATIONAL_PROOF = {
    "host": {
        "model": "Mac13,1",
        "machine": "arm64",
        "theta": {"host": "127.0.0.1", "port": 25503, "reachable": True},
    },
    "runtime": {
        "manifest_path": str(runner.RUNTIME_MANIFEST),
        "manifest_sha256": "1" * 64,
        "manifest_bytes": 100,
        "file_count": 3,
        "file_bytes": 30,
        "native_file_count": 1,
        "release_sha": REPOSITORY.head_commit,
    },
    "evidence_roots": {
        "w1a": None,
        "mark": {
            "path": str(runner.MARK_ROOT),
            "device": 1,
            "inode": 2,
            "uid": os.getuid(),
            "mode": 0o700,
        },
        "lifecycle": {
            "path": str(runner.LIFECYCLE_ROOT),
            "device": 1,
            "inode": 3,
            "uid": os.getuid(),
            "mode": 0o700,
        },
    },
    "launchd": {
        "repo_path": str(runner.REPO_PLIST),
        "installed_path": str(runner.INSTALLED_PLIST),
        "sha256": "2" * 64,
        "bytes": 100,
        "exact_release_match": True,
    },
    "private_disk_free_bytes": runner.MIN_FREE_DISK_BYTES,
}


@dataclass(frozen=True)
class FakeInputs:
    w1a_receipt_root: Path | None = None
    mark_root: Path | None = None
    lifecycle_root: Path | None = None


def test_runtime_v2_marker_body_and_digest_are_exact() -> None:
    assert runner.RUNTIME_MARKER_BODY == (
        b"options.sparse_selector.persistent_runtime_root/v2\n"
    )
    assert runner.RUNTIME_MARKER_SHA256 == hashlib.sha256(
        runner.RUNTIME_MARKER_BODY
    ).hexdigest()
    assert runner.RUNTIME_ROOT.name == "options_sparse_selector_runtime_v2"
    assert runner.OPS_ROOT.name == "options_sparse_selector_ops_v2"


class FakeCore:
    SELECTOR_RUNTIME_ARMED = True
    SELECTOR_PROPOSALS_ARMED = False
    EvidenceInputs = FakeInputs

    def __init__(
        self,
        *,
        head: dict | None = None,
        decisions: list[dict] | None = None,
        after_head: dict | None = None,
        recovery_intent: bool = False,
        recovery_head: dict | None = None,
    ) -> None:
        self.head = copy.deepcopy(head)
        self.decisions = copy.deepcopy(decisions or [])
        self.after_head = copy.deepcopy(after_head)
        self.recovery_intent = recovery_intent
        self.recovery_head = copy.deepcopy(recovery_head or after_head)
        self.advance_calls: list[dict] = []
        self.source_snapshots: list[dict] = []

    def SourceSnapshot(self, **kwargs):  # noqa: N802 - mirrors engine dataclass
        self.source_snapshots.append(copy.deepcopy(kwargs))
        return SimpleNamespace(**kwargs)

    def status(self, private_root: Path, *, evidence_inputs: FakeInputs) -> dict:
        del private_root, evidence_inputs
        value = {
            "runtime_armed": True,
            "proposals_armed": False,
            "initialized": self.head is not None,
            "head": copy.deepcopy(self.head),
            "recovery_intent": self.recovery_intent,
        }
        if self.recovery_intent:
            value["initialized"] = True
            value["intent_next_head"] = copy.deepcopy(self.recovery_head)
            value["intent_next_head_id"] = self.recovery_head["head_id"]
        return value

    def authenticate_store(
        self,
        private_root: Path,
        *,
        evidence_inputs: FakeInputs,
        _allow_durable_intent: bool = False,
    ) -> tuple[dict | None, list[dict], bytes]:
        del private_root, evidence_inputs, _allow_durable_intent
        return copy.deepcopy(self.head), copy.deepcopy(self.decisions), b""

    def advance(self, **kwargs) -> dict:
        self.advance_calls.append(kwargs)
        if self.after_head is None:
            raise AssertionError("fake advance lacks an after HEAD")
        self.head = copy.deepcopy(self.after_head)
        self.decisions = [
            {"action": "abstain"} for _ in range(self.head["decision_count"])
        ]
        self.recovery_intent = False
        return copy.deepcopy(self.head)


def _head(
    *,
    generation: int = 1,
    cycle_count: int = 0,
    phase: str = "AUDITING",
    candidate_count: int = 0,
    decision_count: int = 0,
    commit: str = "b" * 40,
    observed_at: str = "2026-08-14T13:59:00.000000Z",
    pending: dict | None = None,
    oids: dict[str, str] | None = None,
) -> dict:
    source_oids = OIDS if oids is None else oids
    return {
        "head_id": "ossh_" + f"{generation:064x}",
        "previous_head_id": None
        if generation == 1
        else "ossh_" + f"{generation - 1:064x}",
        "generation": generation,
        "advanced_at": "2026-08-14T14:00:00.000000Z",
        "cycle_count": cycle_count,
        "source_phase": phase,
        "source_commit": commit,
        "source_observed_at": observed_at,
        "source_campaign_prefix": {
            "git_blob_oid": source_oids[runner.CAMPAIGNS_PATH]
        },
        "source_episode_prefix": {
            "git_blob_oid": source_oids[runner.EPISODES_PATH]
        },
        "source_checkpoint": {"git_blob_oid": source_oids[runner.CHECKPOINT_PATH]},
        "candidate_count": candidate_count,
        "decision_count": decision_count,
        "pending_manifest": pending,
        "proposal_session_count": 0,
    }


def _runtime(core: FakeCore, *, session: bool = True) -> runner.RuntimeBindings:
    def window(session_date: str) -> tuple[datetime, datetime]:
        parsed = date.fromisoformat(session_date)
        return (
            datetime.combine(parsed, time(9, 30), tzinfo=runner.ET),
            datetime.combine(parsed, time(16, 0), tzinfo=runner.ET),
        )

    return runner.RuntimeBindings(
        core=core,  # type: ignore[arg-type]
        session_window_et=window,
        is_session=lambda _date: session,
    )


def _material(*, commit: str = "b" * 40, observed_at: str | None = None):
    return runner.SourceMaterial(
        commit=commit,
        observed_at=observed_at or runner._utc_text(NOW),
        bodies=BODIES,
        blob_oids=OIDS,
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    core: FakeCore,
    *,
    runtime: runner.RuntimeBindings | None = None,
    source: runner.SourceMaterial | None = None,
    source_mode: str = "FRESH_SOURCE_EPOCH",
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    ops = private / "ops"
    monkeypatch.setattr(runner, "OPS_ROOT", ops)
    monkeypatch.setattr(runner, "SELECTOR_ROOT", private / "selector")
    monkeypatch.setattr(runner, "MARK_ROOT", private / "marks")
    monkeypatch.setattr(runner, "LIFECYCLE_ROOT", private / "lifecycle")
    bindings = runtime or _runtime(core)
    monkeypatch.setattr(
        runner,
        "_static_preflight",
        lambda: (REPOSITORY, bindings, copy.deepcopy(OPERATIONAL_PROOF)),
    )
    monkeypatch.setattr(runner, "_deadline", nullcontext)
    selected = source or _material()
    monkeypatch.setattr(
        runner,
        "_select_source",
        lambda **_kwargs: (selected, source_mode),
    )
    if core.head is not None and not core.recovery_intent:
        _write_slot_claim(
            commit=core.head["source_commit"], resulting_head=core.head
        )


def _write_slot_claim(
    *,
    commit: str,
    scheduled_at: datetime = NOW,
    resulting_head: dict | None = None,
) -> dict:
    runner._ensure_ops_root()
    claim = {
        "schema": runner.SLOT_CLAIM_SCHEMA,
        "mode": runner.MODE,
        "slot_id": runner._slot_id(scheduled_at),
        "scheduled_at": runner._utc_text(scheduled_at),
        "claimed_at": runner._utc_text(scheduled_at),
        "source_commit": commit,
        "parent_head_id": None
        if resulting_head is None
        else resulting_head["previous_head_id"],
        "parent_generation": 0
        if resulting_head is None
        else resulting_head["generation"] - 1,
        "authority": dict(runner.FALSE_AUTHORITY),
    }
    runner._atomic_receipt(runner.SLOT_CLAIM_NAME, claim)
    return claim


def _runtime_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[runner.RepositoryState, Path, Path]:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    runtime_root = private / "runtime-root"
    runtime_root.mkdir(mode=0o700)
    runtime_tree = runtime_root / "runtime"
    python = runtime_tree / "bin/python3.12"
    timezone_file = runtime_tree / "share/zoneinfo/America/New_York"
    dependency = runtime_tree / "lib/python3.12/site-packages/dependency.py"
    readonly_native = runtime_tree / "lib/python3.12/site-packages/libfixture.dylib"
    for path, body, mode in (
        (python, b"sealed-python", 0o555),
        (timezone_file, b"TZif", 0o444),
        (dependency, b"sealed-dependency", 0o444),
        (readonly_native, b"sealed-native", 0o444),
    ):
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        path.write_bytes(body)
        path.chmod(mode)
    for directory in sorted(
        (path for path in runtime_tree.rglob("*") if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    runtime_tree.chmod(0o555)

    repo = tmp_path / "repo"
    repo.mkdir(mode=0o755)
    carrier_source = Path(
        runner.__file__
    ).parents[1] / "ops/launchd/run_options_sparse_selector_verified.py"
    import_hashes: dict[str, str] = {}
    for relative in runner.RECEIPTED_IMPORT_PATHS:
        destination = repo / relative
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        body = (
            carrier_source.read_bytes()
            if relative.endswith("run_options_sparse_selector_verified.py")
            else f"fixture:{relative}".encode()
        )
        destination.write_bytes(body)
        destination.chmod(0o644)
        import_hashes[relative] = hashlib.sha256(body).hexdigest()

    deploy_key = tmp_path / "deploy-key"
    deploy_key.write_bytes(b"fixture-deploy-key")
    deploy_key.chmod(0o600)
    marker = runtime_root / runner.RUNTIME_MARKER.name
    marker.write_bytes(runner.RUNTIME_MARKER_BODY)
    marker.chmod(0o600)
    files = []
    for path in sorted(item for item in runtime_tree.rglob("*") if item.is_file()):
        body = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(runtime_tree).as_posix(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "mode": stat.S_IMODE(os.lstat(path).st_mode),
            }
        )
    repository = runner.RepositoryState(
        head_commit="a" * 40,
        origin_main_commit="b" * 40,
        origin_main_committed_at="2026-08-14T13:55:00.000000Z",
    )
    manifest = {
        "schema": "options.sparse_selector_runtime_carrier/v2",
        "authority": False,
        "training": False,
        "profile": {
            "model": runner.EXPECTED_HOST_MODEL,
            "machine": runner.EXPECTED_MACHINE,
            "theta": f"{runner.THETA_HOST}:{runner.THETA_PORT}",
            "python": str(runner.EXPECTED_RUNTIME_SOURCE / "bin/python3.12"),
        },
        "source_runtime": str(runner.EXPECTED_RUNTIME_SOURCE),
        "runtime": "runtime",
        "timezone_database": "share/zoneinfo",
        "repo_import_source_sha256": import_hashes,
        "files": files,
        "imports": list(runner.EXPECTED_RUNTIME_IMPORTS),
        "native_signature": "adhoc",
        "native_dyld_loaded": 1,
        "native_files": [
            "bin/python3.12",
            "lib/python3.12/site-packages/libfixture.dylib",
        ],
        "installation": {
            "kind": "persistent",
            "target_root": str(runtime_root),
            "repo_root": str(repo),
            "origin_url": runner.CANONICAL_ORIGIN_URL,
            "deploy_key": str(deploy_key),
            "deploy_key_sha256": hashlib.sha256(deploy_key.read_bytes()).hexdigest(),
            "marker": marker.name,
            "marker_sha256": runner.RUNTIME_MARKER_SHA256,
            "expected_release_sha": repository.head_commit,
            "release_sha": repository.head_commit,
        },
    }
    manifest_path = runtime_root / "runtime_closure.json"
    manifest_path.write_bytes(runner._canonical_json(manifest))
    manifest_path.chmod(0o600)

    monkeypatch.setattr(runner, "EXPECTED_REPO_ROOT", repo)
    monkeypatch.setattr(runner, "VERIFIED_CARRIER_PATH", repo / runner.RECEIPTED_IMPORT_PATHS[-1])
    monkeypatch.setattr(runner, "DEPLOY_KEY", deploy_key)
    monkeypatch.setattr(runner, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(runner, "RUNTIME_MANIFEST", manifest_path)
    monkeypatch.setattr(runner, "RUNTIME_MARKER", marker)
    monkeypatch.setattr(runner, "RUNTIME_PYTHON", python)
    monkeypatch.setattr(
        runner,
        "RUNTIME_SITE_PACKAGES",
        runtime_tree / "lib/python3.12/site-packages",
    )
    monkeypatch.setattr(runner.sys, "executable", str(python))
    return repository, dependency, manifest_path


def test_runner_boundary_is_stdlib_only_and_proposals_are_structurally_absent() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    # Delayed imports live inside _load_runtime, never at module import.
    top_level_imports = {
        node.module or ""
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "engine" not in top_level_imports
    assert not any(name.startswith("engine.") for name in top_level_imports)
    assert "pandas" not in imported
    assert runner.W1A_RECEIPT_ROOT is None
    assert runner.PROPOSALS_ARMED is False
    assert runner.EXPECTED_REPO_ROOT == Path(runner.__file__).resolve().parents[1]
    assert runner.MAX_HEAD_GENERATIONS == 128
    inputs = runner._evidence_inputs(FakeCore())
    assert inputs.w1a_receipt_root is None
    assert inputs.mark_root == runner.MARK_ROOT
    assert inputs.lifecycle_root == runner.LIFECYCLE_ROOT


def test_dirty_checkout_refuses_before_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_attest_directory", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "_read_regular", lambda *_args, **_kwargs: b"key")
    calls: list[tuple[str, ...]] = []

    def fake_git(arguments, **_kwargs):
        args = tuple(arguments)
        calls.append(args)
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return SimpleNamespace(
                returncode=0,
                stdout=(str(runner.EXPECTED_REPO_ROOT) + "\n").encode(),
            )
        if args[:3] == ("remote", "get-url", "origin"):
            return SimpleNamespace(
                returncode=0,
                stdout=(runner.CANONICAL_ORIGIN_URL + "\n").encode(),
            )
        if args and args[0] == "status":
            return SimpleNamespace(returncode=0, stdout=b"?? forged-source.json\n")
        raise AssertionError(args)

    monkeypatch.setattr(runner, "_git", fake_git)
    with pytest.raises(runner.RunnerError, match="dirty"):
        runner._attest_repository()
    assert not any(call and call[0] == "fetch" for call in calls)


def test_source_blob_bytes_must_match_exact_tree_oid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = runner._git_blob_oid(b"registered")

    def fake_git(arguments, **_kwargs):
        args = list(arguments)
        if args[0] == "ls-tree":
            path = args[-1]
            return SimpleNamespace(
                returncode=0,
                stdout=f"100644 blob {claimed}\t{path}\0".encode(),
            )
        if args[:2] == ["cat-file", "blob"]:
            return SimpleNamespace(returncode=0, stdout=b"forged")
        raise AssertionError(args)

    monkeypatch.setattr(runner, "_git", fake_git)
    with pytest.raises(runner.RunnerError, match="differs from its tree OID"):
        runner._read_source_blobs("a" * 40)


def test_invalid_preflight_never_creates_selector_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    selector = tmp_path / "must-not-exist"
    monkeypatch.setattr(runner, "SELECTOR_ROOT", selector)
    monkeypatch.setattr(
        runner,
        "_static_preflight",
        lambda: (_ for _ in ()).throw(runner.RunnerError("wrong target host")),
    )
    monkeypatch.setattr(runner, "_ops_lock", nullcontext)
    monkeypatch.setattr(runner, "_deadline", nullcontext)
    with pytest.raises(runner.RunnerError, match="wrong target host"):
        runner.run_once(clock=lambda: NOW)
    assert not selector.exists()


def test_git_commands_hard_pin_ssh_deploy_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_run(command, **_kwargs):
        captured.append(command)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner._git(["status"])
    assert captured == [
        [
            str(runner.GIT),
            "-C",
            str(runner.EXPECTED_REPO_ROOT),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "protocol.file.allow=never",
            "-c",
            f"core.sshCommand={runner.GIT_SSH_COMMAND}",
            "status",
        ]
    ]
    assert str(runner.DEPLOY_KEY) in runner.GIT_SSH_COMMAND
    assert "IdentitiesOnly=yes" in runner.GIT_SSH_COMMAND
    assert "BatchMode=yes" in runner.GIT_SSH_COMMAND


def test_static_preflight_is_inside_singleton_and_watchdog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    core = FakeCore(after_head=_head())
    state = {"lock": False, "deadline": False}

    class Fence:
        def __init__(self, key: str) -> None:
            self.key = key

        def __enter__(self):
            state[self.key] = True

        def __exit__(self, *_args):
            state[self.key] = False

    monkeypatch.setattr(runner, "_ops_lock", lambda: Fence("lock"))
    monkeypatch.setattr(runner, "_deadline", lambda: Fence("deadline"))

    def preflight():
        assert state == {"lock": True, "deadline": True}
        raise runner.RunnerError("stop after fence proof")

    monkeypatch.setattr(runner, "_static_preflight", preflight)
    with pytest.raises(runner.RunnerError, match="fence proof"):
        runner.run_once(clock=lambda: NOW)


def test_rth_skip_makes_no_slot_claim_and_never_advances(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    core = FakeCore(after_head=_head())
    closed = _runtime(core, session=False)
    _wire(monkeypatch, tmp_path, core, runtime=closed)
    receipt = runner.run_once(clock=lambda: NOW)
    assert receipt["outcome"] == "SKIPPED"
    assert receipt["reason"] == "NON_NYSE_SESSION"
    assert core.advance_calls == []
    assert not (runner.OPS_ROOT / runner.SLOT_CLAIM_NAME).exists()
    assert not runner.SELECTOR_ROOT.exists()


def test_late_rth_watchdog_crossing_close_is_skipped() -> None:
    core = FakeCore()
    value = datetime(2026, 8, 14, 19, 58, 0, tzinfo=UTC)  # 15:58 ET
    gate = runner._session_gate(value, _runtime(core))
    assert gate.allowed is False
    assert gate.reason == "WATCHDOG_CROSSES_NYSE_RTH_CLOSE"


def test_authenticated_proposal_poison_refuses_before_advance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    head = _head(decision_count=1, candidate_count=1)
    core = FakeCore(
        head=head,
        decisions=[{"action": "propose"}],
        after_head=_head(generation=2),
    )
    _wire(monkeypatch, tmp_path, core)
    with pytest.raises(runner.RunnerError, match="propose action"):
        runner.run_once(clock=lambda: NOW)
    assert core.advance_calls == []


@pytest.mark.parametrize(
    ("head", "now", "reason"),
    [
        (_head(generation=128), NOW, "generation_cap_reached"),
        (_head(candidate_count=2, decision_count=2), NOW, "first_settled_manifest"),
        (_head(), datetime(2026, 8, 21, 20, 0, tzinfo=UTC), "activation_expired"),
    ],
)
def test_generation_settlement_and_expiry_publish_durable_halt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    head: dict,
    now: datetime,
    reason: str,
) -> None:
    decisions = [{"action": "abstain"} for _ in range(head["decision_count"])]
    core = FakeCore(head=head, decisions=decisions, after_head=_head(generation=2))
    _wire(monkeypatch, tmp_path, core)
    receipt = runner.run_once(clock=lambda: now)
    halt = runner._read_canonical_receipt(
        runner.HALT_NAME, schema=runner.HALT_SCHEMA
    )
    assert receipt["outcome"] == "HALTED"
    assert receipt["reason"] == reason
    assert halt is not None and halt["reason"] == reason
    assert core.advance_calls == []


def test_outer_ops_lock_is_nonblocking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    ops = private / "ops"
    ops.mkdir(mode=0o700)
    monkeypatch.setattr(runner, "OPS_ROOT", ops)
    descriptor = os.open(ops / runner.LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(runner.RunnerBusy, match="already active"):
            with runner._ops_lock():
                raise AssertionError("contended lock entered")
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def test_one_launch_claims_one_slot_and_calls_advance_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    after = _head(generation=1, cycle_count=0)
    core = FakeCore(after_head=after)
    _wire(monkeypatch, tmp_path, core)
    receipt = runner.run_once(clock=lambda: NOW)
    assert receipt["outcome"] == "ADVANCED"
    assert receipt["reason"] == "one_transition_committed"
    assert len(core.advance_calls) == 1
    invocation = core.advance_calls[0]
    assert invocation["private_root"] == runner.SELECTOR_ROOT
    assert invocation["evidence_inputs"].w1a_receipt_root is None
    assert invocation["scheduled_at"] == runner._utc_text(NOW)
    assert receipt["slot_claim"]["slot_id"] == runner._slot_id(NOW)
    assert (runner.OPS_ROOT / runner.STATUS_NAME).read_bytes() == runner._canonical_json(receipt)


def test_first_sealed_intent_without_parent_head_recovers_exact_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recovery_commit = "c" * 40
    recovery_head = _head(generation=1, commit=recovery_commit)
    core = FakeCore(
        head=None,
        after_head=recovery_head,
        recovery_intent=True,
        recovery_head=recovery_head,
    )
    material = _material(commit=recovery_commit)
    _wire(
        monkeypatch,
        tmp_path,
        core,
        source=material,
        source_mode="PINNED_ACTIVE_EPOCH",
    )
    claim = _write_slot_claim(commit=recovery_commit)
    before = runner._selector_snapshot(core, runner._evidence_inputs(core))
    assert before["head"] is None
    assert before["recovery_head"] == recovery_head

    receipt = runner.run_once(clock=lambda: NOW)

    assert receipt["outcome"] == "RECOVERED"
    assert receipt["source"]["commit"] == recovery_commit
    assert receipt["selector"]["head_id"] == recovery_head["head_id"]
    assert len(core.advance_calls) == 1
    assert core.advance_calls[0]["scheduled_at"] == claim["scheduled_at"]


def test_sealed_intent_recovery_uses_original_claim_outside_current_rth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recovery_commit = "c" * 40
    recovery_head = _head(generation=2, commit=recovery_commit)
    core = FakeCore(
        head=_head(commit="b" * 40),
        after_head=recovery_head,
        recovery_intent=True,
        recovery_head=recovery_head,
    )
    _wire(
        monkeypatch,
        tmp_path,
        core,
        source=_material(commit=recovery_commit),
        source_mode="PINNED_ACTIVE_EPOCH",
    )
    claim = _write_slot_claim(
        commit=recovery_commit,
        scheduled_at=NOW,
        resulting_head=recovery_head,
    )
    outside_rth = datetime(2026, 8, 14, 23, 0, tzinfo=UTC)
    receipt = runner.run_once(clock=lambda: outside_rth)
    assert receipt["outcome"] == "RECOVERED"
    assert core.advance_calls[0]["scheduled_at"] == claim["scheduled_at"]
    assert receipt["session"]["allowed"] is True
    assert receipt["slot_claim"] == claim


@pytest.mark.parametrize("claim_commit", [None, "d" * 40])
def test_sealed_intent_recovery_requires_matching_original_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    claim_commit: str | None,
) -> None:
    recovery_commit = "c" * 40
    recovery_head = _head(generation=2, commit=recovery_commit)
    core = FakeCore(
        head=_head(),
        after_head=recovery_head,
        recovery_intent=True,
        recovery_head=recovery_head,
    )
    _wire(
        monkeypatch,
        tmp_path,
        core,
        source=_material(commit=recovery_commit),
        source_mode="PINNED_ACTIVE_EPOCH",
    )
    if claim_commit is not None:
        _write_slot_claim(commit=claim_commit, resulting_head=recovery_head)
    with pytest.raises(
        runner.RunnerError, match="original slot claim|slot source differs"
    ):
        runner.run_once(clock=lambda: NOW)
    assert core.advance_calls == []


def test_same_slot_replay_is_skipped_even_when_head_has_no_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Source/evidence audit HEADs can have cycle_count=0; engine-level scheduled
    # dedupe does not cover them, so the outer durable claim must.
    audit_head = _head(generation=1, cycle_count=0, phase="AUDITING")
    core = FakeCore(after_head=audit_head)
    _wire(monkeypatch, tmp_path, core)
    first = runner.run_once(clock=lambda: NOW)
    second = runner.run_once(clock=lambda: NOW + runner.timedelta(seconds=30))
    assert first["outcome"] == "ADVANCED"
    assert second["outcome"] == "SKIPPED"
    assert second["reason"] == "SLOT_ALREADY_CLAIMED"
    assert len(core.advance_calls) == 1
    assert second["slot_claim"] == first["slot_claim"]


def test_active_epoch_reuses_exact_head_commit_clock_and_blob_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pinned_oids = {key: value[::-1] for key, value in OIDS.items()}
    head = _head(
        phase="READY",
        commit="c" * 40,
        observed_at="2026-08-13T15:00:00.000000Z",
        oids=pinned_oids,
    )
    snapshot = {
        "head": head,
        "public": {"recovery_intent": False},
        "decisions": [],
    }
    seen: list[str] = []

    def fake_git(arguments, **kwargs):
        del kwargs
        assert arguments[0] == "merge-base"
        return SimpleNamespace(returncode=0, stdout=b"")

    def fake_read(commit: str):
        seen.append(commit)
        return BODIES, pinned_oids

    monkeypatch.setattr(runner, "_git", fake_git)
    monkeypatch.setattr(runner, "_read_source_blobs", fake_read)
    source, mode = runner._select_source(
        repository=REPOSITORY,
        snapshot=snapshot,
        clock=lambda: (_ for _ in ()).throw(AssertionError("clock sampled")),
    )
    assert source is not None
    assert seen == ["c" * 40]
    assert source.commit == "c" * 40
    assert source.observed_at == head["source_observed_at"]
    assert mode == "PINNED_ACTIVE_EPOCH"


def test_drained_unchanged_source_skips_without_fresh_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = _head(phase="DRAINED")
    snapshot = {
        "head": head,
        "public": {"recovery_intent": False},
        "decisions": [],
    }

    def fake_git(arguments, **kwargs):
        del kwargs
        assert arguments[:2] == ["rev-parse", "--verify"]
        return SimpleNamespace(returncode=0, stdout=(REPOSITORY.origin_main_commit + "\n").encode())

    monkeypatch.setattr(runner, "_git", fake_git)
    monkeypatch.setattr(runner, "_read_source_blobs", lambda _commit: (BODIES, OIDS))
    source, mode = runner._select_source(
        repository=REPOSITORY,
        snapshot=snapshot,
        clock=lambda: (_ for _ in ()).throw(AssertionError("clock sampled")),
    )
    assert source is None
    assert mode == "DRAINED_SOURCE_UNCHANGED"


def test_drained_changed_source_gets_post_read_real_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_oids = {key: "0" * 40 for key in OIDS}
    head = _head(phase="DRAINED", oids=old_oids)
    snapshot = {
        "head": head,
        "public": {"recovery_intent": False},
        "decisions": [],
    }

    def fake_git(arguments, **kwargs):
        del kwargs
        assert arguments[:2] == ["rev-parse", "--verify"]
        return SimpleNamespace(returncode=0, stdout=(REPOSITORY.origin_main_commit + "\n").encode())

    monkeypatch.setattr(runner, "_git", fake_git)
    monkeypatch.setattr(runner, "_read_source_blobs", lambda _commit: (BODIES, OIDS))
    observed = NOW.replace(microsecond=123456)
    source, mode = runner._select_source(
        repository=REPOSITORY,
        snapshot=snapshot,
        clock=lambda: observed,
    )
    assert source is not None
    assert source.observed_at == "2026-08-14T14:00:00.123456Z"
    assert mode == "FRESH_SOURCE_EPOCH"


def test_status_authenticates_but_never_advances(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    core = FakeCore(head=_head(), after_head=_head(generation=2))
    _wire(monkeypatch, tmp_path, core)
    receipt = runner.report_status(clock=lambda: NOW)
    assert receipt["outcome"] == "STATUS"
    assert receipt["selector"]["generation"] == 1
    assert receipt["source"]["mode"] == "AUTHENTICATED_HEAD"
    assert receipt["source"]["blob_oids"] == OIDS
    assert receipt["source"]["prefixes"]["campaigns"] == core.head[
        "source_campaign_prefix"
    ]
    assert receipt["operational_proof"] == OPERATIONAL_PROOF
    assert receipt["operational_proof"]["runtime"]["manifest_sha256"] == "1" * 64
    assert receipt["operational_proof"]["launchd"]["exact_release_match"] is True
    assert core.advance_calls == []


def test_full_runtime_manifest_is_reauthenticated_before_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository, dependency, _manifest_path = _runtime_fixture(
        monkeypatch, tmp_path
    )
    receipt = runner._attest_runtime_carrier(repository)
    assert receipt["file_count"] == 4
    assert receipt["native_file_count"] == 2
    assert receipt["file_bytes"] > 0
    dependency.chmod(0o644)
    dependency.write_bytes(b"tampered-dependency")
    dependency.chmod(0o444)
    with pytest.raises(runner.RunnerError, match="full manifest"):
        runner._attest_runtime_carrier(repository)


def test_runtime_native_receipts_reject_unsafe_modes_and_v1_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository, _dependency, manifest_path = _runtime_fixture(monkeypatch, tmp_path)
    manifest = json.loads(manifest_path.read_bytes())
    native = next(
        item
        for item in manifest["files"]
        if item["path"].endswith("libfixture.dylib")
    )
    native["mode"] = 0o644
    manifest_path.chmod(0o600)
    manifest_path.write_bytes(runner._canonical_json(manifest))
    with pytest.raises(runner.RunnerError, match="file receipt fields drifted"):
        runner._attest_runtime_carrier(repository)

    v1_fixture = tmp_path / "v1"
    v1_fixture.mkdir()
    _repository, _dependency, manifest_path = _runtime_fixture(monkeypatch, v1_fixture)
    runner.RUNTIME_MARKER.write_bytes(
        b"options.sparse_selector.persistent_runtime_root/v1\n"
    )
    with pytest.raises(runner.RunnerError, match="runtime marker drifted"):
        runner._attest_runtime_carrier(_repository)


def test_runtime_native_actual_mode_and_python_execute_mode_are_enforced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    native_fixture = tmp_path / "native"
    native_fixture.mkdir()
    repository, _dependency, _manifest_path = _runtime_fixture(
        monkeypatch, native_fixture
    )
    native = (
        runner.RUNTIME_ROOT
        / "runtime/lib/python3.12/site-packages/libfixture.dylib"
    )
    native.chmod(0o644)
    with pytest.raises(runner.RunnerError, match="full manifest"):
        runner._attest_runtime_carrier(repository)

    python_fixture = tmp_path / "python"
    python_fixture.mkdir()
    repository, _dependency, _manifest_path = _runtime_fixture(
        monkeypatch, python_fixture
    )
    runner.RUNTIME_PYTHON.chmod(0o444)
    with pytest.raises(runner.RunnerError, match="full manifest"):
        runner._attest_runtime_carrier(repository)


def test_immutable_transition_survives_status_overwrite_and_conflict_refuses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    after = _head(generation=1)
    core = FakeCore(after_head=after)
    _wire(monkeypatch, tmp_path, core)
    advanced = runner.run_once(clock=lambda: NOW)
    relative = advanced["immutable_transition_receipt"]
    assert relative == f"transitions/{after['head_id']}.json"
    immutable = runner.OPS_ROOT / relative
    before = immutable.read_bytes()
    changed_proof = copy.deepcopy(OPERATIONAL_PROOF)
    changed_proof["private_disk_free_bytes"] += 12345
    monkeypatch.setattr(
        runner,
        "_static_preflight",
        lambda: (REPOSITORY, _runtime(core), changed_proof),
    )
    status = runner.report_status(clock=lambda: NOW + runner.timedelta(minutes=5))
    assert status["outcome"] == "STATUS"
    assert immutable.read_bytes() == before
    parsed = json.loads(before)
    assert parsed["schema"] == runner.TRANSITION_SCHEMA
    assert parsed["resulting_head"]["head_id"] == after["head_id"]
    assert parsed["source"]["prefixes"]["checkpoint"] == after[
        "source_checkpoint"
    ]
    immutable.chmod(0o600)
    immutable.write_bytes(b"{}")
    with pytest.raises(runner.RunnerError, match="conflicts"):
        runner._publish_transition_status(
            recorded_at=NOW,
            outcome="ADVANCED",
            reason="one_transition_committed",
            repository=REPOSITORY,
            snapshot={"head": after, "recovery_head": None},
            source=_material(),
            source_mode="FRESH_SOURCE_EPOCH",
            session=runner._session_gate(NOW, _runtime(core)),
            slot_claim=advanced["slot_claim"],
            halted=False,
            operational_proof=OPERATIONAL_PROOF,
        )


@pytest.mark.parametrize(
    ("decision_count", "expected_outcome"),
    [(0, "SKIPPED"), (1, "HALTED")],
)
def test_post_head_receipt_failure_repairs_first_and_halt_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    decision_count: int,
    expected_outcome: str,
) -> None:
    after = _head(
        generation=1,
        candidate_count=decision_count,
        decision_count=decision_count,
    )
    core = FakeCore(after_head=after)
    _wire(monkeypatch, tmp_path, core)
    real_publish = runner._publish_transition_status

    def fail_after_head(**_kwargs):
        raise runner.RunnerError("injected post-HEAD receipt failure")

    monkeypatch.setattr(runner, "_publish_transition_status", fail_after_head)
    with pytest.raises(runner.RunnerError, match="post-HEAD"):
        runner.run_once(clock=lambda: NOW)
    assert core.head == after
    assert not (runner.OPS_ROOT / runner.TRANSITION_RECEIPT_DIRECTORY).exists()

    monkeypatch.setattr(runner, "_publish_transition_status", real_publish)
    repaired = runner.run_once(
        clock=lambda: NOW + runner.timedelta(seconds=30)
    )
    target = (
        runner.OPS_ROOT
        / runner.TRANSITION_RECEIPT_DIRECTORY
        / f"{after['head_id']}.json"
    )
    assert target.is_file()
    assert repaired["outcome"] == expected_outcome
    assert repaired["immutable_transition_receipt"] == (
        f"transitions/{after['head_id']}.json"
    )


def test_crash_after_new_claim_before_core_does_not_rebind_current_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    current = _head(generation=1)
    core = FakeCore(head=current, after_head=_head(generation=2))
    _wire(monkeypatch, tmp_path, core)
    initial = runner.report_status(clock=lambda: NOW)
    immutable = runner.OPS_ROOT / initial["immutable_transition_receipt"]
    before = immutable.read_bytes()

    def crash_before_core(**_kwargs):
        raise runner.RunnerError("injected before core WAL")

    monkeypatch.setattr(core, "advance", crash_before_core)
    next_slot = NOW + runner.timedelta(minutes=5)
    with pytest.raises(runner.RunnerError, match="before core WAL"):
        runner.run_once(clock=lambda: next_slot)
    newer_claim = runner._read_slot_claim()
    assert newer_claim is not None
    assert newer_claim["parent_head_id"] == current["head_id"]
    assert core.head == current

    retry = runner.run_once(
        clock=lambda: next_slot + runner.timedelta(seconds=30)
    )
    assert retry["outcome"] == "SKIPPED"
    assert retry["reason"] == "SLOT_ALREADY_CLAIMED"
    assert immutable.read_bytes() == before


def test_existing_transition_rejects_self_consistent_forged_embedded_claim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    after = _head(generation=1)
    core = FakeCore(after_head=after)
    _wire(monkeypatch, tmp_path, core)
    advanced = runner.run_once(clock=lambda: NOW)
    immutable = runner.OPS_ROOT / advanced["immutable_transition_receipt"]
    forged = json.loads(immutable.read_bytes())
    forged["slot_claim"]["source_commit"] = "d" * 40
    immutable.write_bytes(runner._canonical_json(forged))
    with pytest.raises(runner.RunnerError, match="does not bind"):
        runner.report_status(clock=lambda: NOW + runner.timedelta(minutes=5))


def test_stranded_hardlink_temp_is_exactly_repaired(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    after = _head(generation=1)
    core = FakeCore(after_head=after)
    _wire(monkeypatch, tmp_path, core)
    advanced = runner.run_once(clock=lambda: NOW)
    immutable = runner.OPS_ROOT / advanced["immutable_transition_receipt"]
    stranded = (
        runner.OPS_ROOT
        / f".transition.{after['head_id']}.99999.tmp"
    )
    os.link(immutable, stranded)
    assert os.lstat(immutable).st_nlink == 2
    status = runner.report_status(clock=lambda: NOW + runner.timedelta(minutes=5))
    assert status["outcome"] == "STATUS"
    assert not stranded.exists()
    assert os.lstat(immutable).st_nlink == 1
