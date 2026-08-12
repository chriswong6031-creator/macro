from __future__ import annotations

import inspect
import fcntl
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine import options_mastermindx_capture as capture

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "contracts"
    / "options"
    / "options.mastermindx_selector_capture_attestation.v1.schema.json"
)
SELECTOR_RECEIPT = (
    ROOT
    / "research"
    / "options_estate"
    / "sparse_selector_preregistration_receipt_v1.json"
)


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [str(capture.GIT_BINARY), "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _clock(*values: str) -> Callable[[], datetime]:
    clocks = iter(
        datetime.fromisoformat(value.replace("Z", "+00:00")) for value in values
    )
    return lambda: next(clocks)


def _file_identity(path: Path) -> tuple[str, int]:
    body = path.read_bytes()
    return sha256(body).hexdigest(), len(body)


@pytest.fixture
def installed_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, capture.CaptureReleasePolicy]:
    if os.geteuid() == 0:
        pytest.skip("the production attestor correctly refuses root")
    root = (tmp_path / "options-nbbo-ops-wt").resolve()
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    for relative in (
        capture.MODULE_RELATIVE_PATH,
        capture.ENGINE_INIT_RELATIVE_PATH,
        capture.SCHEMA_RELATIVE_PATH,
        capture.SESSION_DIGEST_RELATIVE_PATH,
        capture.NYSE_CALENDAR_RELATIVE_PATH,
        capture.LIB_INIT_RELATIVE_PATH,
        capture.SELECTOR_RECEIPT_RELATIVE_PATH,
    ):
        (root / relative.parent).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(capture.__file__), root / capture.MODULE_RELATIVE_PATH)
    shutil.copyfile(
        capture.ENGINE_INIT_PATH,
        root / capture.ENGINE_INIT_RELATIVE_PATH,
    )
    shutil.copyfile(SCHEMA, root / capture.SCHEMA_RELATIVE_PATH)
    shutil.copyfile(
        capture.SESSION_DIGEST_PATH,
        root / capture.SESSION_DIGEST_RELATIVE_PATH,
    )
    shutil.copyfile(
        capture.NYSE_CALENDAR_PATH,
        root / capture.NYSE_CALENDAR_RELATIVE_PATH,
    )
    shutil.copyfile(
        capture.LIB_INIT_PATH,
        root / capture.LIB_INIT_RELATIVE_PATH,
    )
    shutil.copyfile(
        SELECTOR_RECEIPT,
        root / capture.SELECTOR_RECEIPT_RELATIVE_PATH,
    )
    shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
    test_schema = json.loads(
        (root / capture.SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    test_schema["$defs"]["checkout"]["properties"]["path"] = {"const": str(root)}
    (root / capture.SCHEMA_RELATIVE_PATH).write_text(
        json.dumps(test_schema, indent=2) + "\n",
        encoding="utf-8",
    )
    for relative in (
        capture.MODULE_RELATIVE_PATH,
        capture.ENGINE_INIT_RELATIVE_PATH,
        capture.SCHEMA_RELATIVE_PATH,
        capture.SESSION_DIGEST_RELATIVE_PATH,
        capture.NYSE_CALENDAR_RELATIVE_PATH,
        capture.LIB_INIT_RELATIVE_PATH,
        capture.SELECTOR_RECEIPT_RELATIVE_PATH,
    ):
        (root / relative).chmod(0o644)
    (root / ".gitignore").chmod(0o644)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "capture-test@example.invalid")
    _git(root, "config", "user.name", "Capture Test")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "install capture attestor")
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    _git(root, "checkout", "-q", "--detach", head)

    lock_parent = (tmp_path / "private").resolve()
    lock_parent.mkdir(mode=0o700)
    lock_parent.chmod(0o700)
    module_sha, module_bytes = _file_identity(root / capture.MODULE_RELATIVE_PATH)
    engine_init_sha, engine_init_bytes = _file_identity(
        root / capture.ENGINE_INIT_RELATIVE_PATH
    )
    schema_sha, schema_bytes = _file_identity(root / capture.SCHEMA_RELATIVE_PATH)
    session_sha, session_bytes = _file_identity(
        root / capture.SESSION_DIGEST_RELATIVE_PATH
    )
    calendar_sha, calendar_bytes = _file_identity(
        root / capture.NYSE_CALENDAR_RELATIVE_PATH
    )
    lib_init_sha, lib_init_bytes = _file_identity(
        root / capture.LIB_INIT_RELATIVE_PATH
    )
    selector_sha, selector_bytes = _file_identity(
        root / capture.SELECTOR_RECEIPT_RELATIVE_PATH
    )
    policy = capture.CaptureReleasePolicy(
        producer_release_sha=head,
        producer_tree_sha=tree,
        module_sha256=module_sha,
        module_bytes=module_bytes,
        engine_init_sha256=engine_init_sha,
        engine_init_bytes=engine_init_bytes,
        schema_sha256=schema_sha,
        schema_bytes=schema_bytes,
        session_digest_sha256=session_sha,
        session_digest_bytes=session_bytes,
        nyse_calendar_sha256=calendar_sha,
        nyse_calendar_bytes=calendar_bytes,
        lib_init_sha256=lib_init_sha,
        lib_init_bytes=lib_init_bytes,
        selector_receipt_sha256=selector_sha,
        selector_receipt_bytes=selector_bytes,
    )

    monkeypatch.setattr(capture, "OPS_CHECKOUT_ROOT", root)
    monkeypatch.setattr(capture, "MODULE_PATH", root / capture.MODULE_RELATIVE_PATH)
    monkeypatch.setattr(
        capture,
        "ENGINE_INIT_PATH",
        root / capture.ENGINE_INIT_RELATIVE_PATH,
    )
    monkeypatch.setattr(capture, "SCHEMA_PATH", root / capture.SCHEMA_RELATIVE_PATH)
    monkeypatch.setattr(
        capture,
        "SESSION_DIGEST_PATH",
        root / capture.SESSION_DIGEST_RELATIVE_PATH,
    )
    monkeypatch.setattr(
        capture,
        "NYSE_CALENDAR_PATH",
        root / capture.NYSE_CALENDAR_RELATIVE_PATH,
    )
    monkeypatch.setattr(
        capture,
        "LIB_INIT_PATH",
        root / capture.LIB_INIT_RELATIVE_PATH,
    )
    monkeypatch.setattr(capture, "INSTALL_LOCK_PATH", lock_parent / ".install.lock")
    monkeypatch.setattr(capture, "_require_ancestor", lambda *args, **kwargs: None)
    return root, head, policy


def _successful_attestation(
    monkeypatch: pytest.MonkeyPatch,
    policy: capture.CaptureReleasePolicy,
) -> dict:
    monkeypatch.setattr(
        capture,
        "_runtime_now",
        _clock(
            "2026-08-12T14:01:01.000001Z",
            "2026-08-12T14:01:02.000002Z",
            "2026-08-12T14:01:03.000003Z",
            "2026-08-12T14:01:04.000004Z",
        ),
    )
    return capture.build_mastermindx_capture_attestation(release_policy=policy)


@pytest.fixture(autouse=True)
def bounded_tracked_tree_verifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit fixtures are tiny; dedicated tests execute the fresh-index verifier."""

    monkeypatch.setattr(
        capture,
        "_ORIGINAL_TRACKED_TREE_VERIFIER",
        capture._verify_all_tracked_worktree_bytes,
        raising=False,
    )
    monkeypatch.setattr(
        capture,
        "_verify_all_tracked_worktree_bytes",
        lambda root, *, head: None,
    )


def test_capture_attestation_is_closed_schema_same_slot_and_zero_authority(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, head, policy = installed_checkout
    payload = _successful_attestation(monkeypatch, policy)
    schema = json.loads(
        (root / capture.SCHEMA_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    assert payload["attestation_id"].startswith("mxcap_")
    assert payload["scheduled_at"] == "2026-08-12T14:00:00.000000Z"
    assert payload["checkout"]["path"] == str(root)
    assert payload["checkout"]["head_sha"] == head
    assert payload["checkout"]["producer_release_sha"] == head
    assert payload["checkout"]["tree_sha"] == policy.producer_tree_sha
    assert payload["checkout"]["tracked_worktree_matches_head"] is True
    assert payload["checkout"]["ordinary_untracked_absent"] is True
    assert payload["checkout"]["ignored_cache_policy"] == (
        "bounded_owned_nonexecutable_pytest_cache_only"
    )
    assert payload["checkout"]["detached_head"] is True
    assert payload["disposition"] == "registered_selector_inactive"
    assert payload["emitted_enrollment_event_count"] == 0
    assert payload["emitted_enrollment_event_ids"] == []
    assert payload["observation"]["candidate_source_examined"] is False
    assert payload["observation"]["candidate_events_inferred"] is False
    assert payload["observation"]["event_producer_armed"] is False
    assert payload["observation"]["candidate_count_known"] is False
    assert payload["observation"]["candidate_count"] is None
    assert (
        payload["selector_registration"]["current_slot_reason_code"]
        == "REGISTERED_SELECTOR_INACTIVE"
    )
    assert payload["selector_registration"]["current_candidate_count_known"] is False
    assert payload["occurrence_trust"]["standalone_replay_proves_host_occurrence"] is False
    assert not any(payload["authority"].values())
    assert not any(payload["claim_boundary"].values())
    assert (
        capture.validate_attestation(payload, release_policy=policy) == payload
    )
    assert capture.strict_json_object(
        capture.canonical_json_bytes(payload), label="capture attestation"
    ) == payload


def test_runtime_reads_only_reviewed_files_and_never_candidate_data(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _head, policy = installed_checkout
    read_paths: list[Path] = []
    original = capture._read_owned_regular

    def recording_read(path: Path, *, label: str) -> tuple[bytes, os.stat_result]:
        read_paths.append(path)
        return original(path, label=label)

    monkeypatch.setattr(capture, "_read_owned_regular", recording_read)
    _successful_attestation(monkeypatch, policy)
    assert set(read_paths) == {
        root / capture.MODULE_RELATIVE_PATH,
        root / capture.ENGINE_INIT_RELATIVE_PATH,
        root / capture.SCHEMA_RELATIVE_PATH,
        root / capture.SESSION_DIGEST_RELATIVE_PATH,
        root / capture.NYSE_CALENDAR_RELATIVE_PATH,
        root / capture.LIB_INIT_RELATIVE_PATH,
        root / capture.SELECTOR_RECEIPT_RELATIVE_PATH,
    }
    assert len(read_paths) == 29
    assert all("/data/" not in path.as_posix() for path in read_paths)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("dirty", "ordinary untracked"),
        ("attached", "not detached"),
        ("root_mode", "mode must be 0700"),
        ("module_drift", "exact reviewed producer release"),
        ("schema_drift", "exact reviewed producer release"),
        ("receipt_drift", "exact reviewed producer release"),
        ("receipt_symlink", "exact reviewed producer release"),
    ],
)
def test_checkout_falsifiers_fail_closed_before_a_success_claim(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    root, _head, policy = installed_checkout
    target: Path | None = None
    if mutation == "dirty":
        (root / "untracked.txt").write_text("not clean", encoding="utf-8")
    elif mutation == "attached":
        assert _git(root, "branch", "--show-current") == ""
        _git(root, "switch", "-q", "-c", "attached-test")
    elif mutation == "root_mode":
        root.chmod(0o755)
    elif mutation == "module_drift":
        target = root / capture.MODULE_RELATIVE_PATH
        target.write_bytes(target.read_bytes() + b"\n")
    elif mutation == "schema_drift":
        target = root / capture.SCHEMA_RELATIVE_PATH
        target.write_bytes(target.read_bytes() + b" ")
    elif mutation == "receipt_drift":
        target = root / capture.SELECTOR_RECEIPT_RELATIVE_PATH
        target.write_bytes(
            target.read_bytes().replace(
                b'"registered_at":"2026-08-11T22:43:53Z"',
                b'"registered_at":"2026-08-11T22:43:54Z"',
                1,
            )
        )
    elif mutation == "receipt_symlink":
        target = root / capture.SELECTOR_RECEIPT_RELATIVE_PATH
        original = root / "selector-receipt-copy.json"
        target.rename(original)
        target.symlink_to(original)
    else:  # pragma: no cover - exhaustive test table
        raise AssertionError(mutation)
    if target is not None:
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"apply {mutation}")

    with pytest.raises(capture.MastermindXCaptureError, match=message):
        _successful_attestation(monkeypatch, policy)


def test_reviewed_release_policy_is_required_and_exact(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    missing = replace(policy, producer_release_sha="0" * 40)
    monkeypatch.setattr(
        capture,
        "_runtime_now",
        _clock("2026-08-12T14:01:01Z"),
    )
    with pytest.raises(capture.MastermindXCaptureError, match="exact reviewed"):
        capture.build_mastermindx_capture_attestation(release_policy=missing)


@pytest.mark.parametrize(
    ("clocks", "message"),
    [
        (("2026-08-15T14:01:01Z",), "not an NYSE session"),
        (("2026-08-12T13:29:59Z",), "outside NYSE RTH"),
        (
            (
                "2026-08-12T14:01:01Z",
                "2026-08-12T14:00:59Z",
                "2026-08-12T14:01:03Z",
            ),
            "not causal",
        ),
        (
            (
                "2026-08-12T14:01:01Z",
                "2026-08-12T14:01:02Z",
                "2026-08-12T14:05:00Z",
            ),
            "inside its slot",
        ),
    ],
)
def test_runtime_clock_falsifiers_fail_closed(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
    clocks: tuple[str, ...],
    message: str,
) -> None:
    _root, _head, policy = installed_checkout
    monkeypatch.setattr(capture, "_runtime_now", _clock(*clocks))
    with pytest.raises(capture.MastermindXCaptureError, match=message):
        capture.build_mastermindx_capture_attestation(release_policy=policy)


def test_public_builder_exposes_no_backdated_slot_or_clock_override() -> None:
    parameters = inspect.signature(
        capture.build_mastermindx_capture_attestation
    ).parameters
    assert set(parameters) == {"release_policy"}


def test_terminal_clock_after_fourth_snapshot_must_remain_in_same_slot(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    original_checkout = capture._checkout_attestation
    snapshot_calls = 0
    clock_calls = 0
    clocks = iter(
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in (
            "2026-08-12T14:04:58.000000Z",
            "2026-08-12T14:04:59.000000Z",
            "2026-08-12T14:04:59.500000Z",
            "2026-08-12T14:05:00.000000Z",
        )
    )

    def counted_checkout(*args: object, **kwargs: object) -> tuple[dict, dict, dict]:
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_checkout(*args, **kwargs)

    def ordered_clock() -> datetime:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 4:
            assert snapshot_calls == 4
        return next(clocks)

    monkeypatch.setattr(capture, "_checkout_attestation", counted_checkout)
    monkeypatch.setattr(
        capture,
        "_runtime_now",
        ordered_clock,
    )
    with pytest.raises(capture.MastermindXCaptureError, match="terminal clock left"):
        capture.build_mastermindx_capture_attestation(release_policy=policy)
    assert snapshot_calls == 4
    assert clock_calls == 4


def test_double_snapshot_rejects_checkout_change_across_capture_event(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    original = capture._checkout_attestation
    calls = 0

    def changing_snapshot(
        root: Path, release_policy: capture.CaptureReleasePolicy
    ) -> tuple[dict, dict, dict]:
        nonlocal calls
        calls += 1
        checkout, selector, metadata = original(root, release_policy)
        if calls == 2:
            checkout = dict(checkout)
            checkout["head_sha"] = "f" * 40
        return checkout, selector, metadata

    monkeypatch.setattr(capture, "_checkout_attestation", changing_snapshot)
    monkeypatch.setattr(
        capture,
        "_runtime_now",
        _clock("2026-08-12T14:01:01Z", "2026-08-12T14:01:02Z"),
    )
    with pytest.raises(capture.MastermindXCaptureError, match="changed across"):
        capture.build_mastermindx_capture_attestation(release_policy=policy)


def test_replay_rejects_tamper_policy_drift_and_static_coverage_claim(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    payload = _successful_attestation(monkeypatch, policy)
    tampered = json.loads(json.dumps(payload))
    tampered["claim_boundary"]["static_registration_is_slot_coverage"] = True
    with pytest.raises(capture.MastermindXCaptureError, match="governance drifted"):
        capture.validate_attestation(tampered, release_policy=policy)

    wrong_policy = replace(policy, module_sha256="f" * 64)
    with pytest.raises(capture.MastermindXCaptureError, match="governance drifted"):
        capture.validate_attestation(payload, release_policy=wrong_policy)

    tampered = json.loads(json.dumps(payload))
    tampered["checkout"]["head_sha"] = "f" * 40
    with pytest.raises(capture.MastermindXCaptureError, match="checkout receipt"):
        capture.validate_attestation(tampered, release_policy=policy)


def test_strict_json_rejects_duplicate_and_nonfinite_registration_bytes() -> None:
    with pytest.raises(capture.MastermindXCaptureError, match="duplicate key"):
        capture.strict_json_object(b'{"a":1,"a":2}', label="duplicate")
    with pytest.raises(capture.MastermindXCaptureError, match="non-finite"):
        capture.strict_json_object(b'{"a":NaN}', label="nonfinite")


def test_producer_rule_is_release_bound_capture_only_without_runtime_arming(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    _root, _head, policy = installed_checkout
    digest = capture.producer_rule_sha256(policy)
    assert len(digest) == 64
    assert digest == capture.producer_rule_sha256(policy)
    assert capture.OPS_CHECKOUT_ROOT.is_absolute()
    source = Path(capture.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "data/options_signal_episode",
        "campaigns.jsonl",
        "EVENT_PRODUCER_REGISTRY",
        "CAPTURE_PRODUCER_REGISTRY",
        "os.environ",
    ):
        assert forbidden not in source


def test_exact_release_tree_and_every_authority_byte_are_externally_frozen(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, head, policy = installed_checkout
    source_paths = {
        "module_sha256": capture.MODULE_RELATIVE_PATH,
        "engine_init_sha256": capture.ENGINE_INIT_RELATIVE_PATH,
        "schema_sha256": capture.SCHEMA_RELATIVE_PATH,
        "session_digest_sha256": capture.SESSION_DIGEST_RELATIVE_PATH,
        "nyse_calendar_sha256": capture.NYSE_CALENDAR_RELATIVE_PATH,
        "lib_init_sha256": capture.LIB_INIT_RELATIVE_PATH,
    }
    assert set(capture.AUTHORITY_SOURCE_PATHS) == {
        "capture_module",
        "engine_package_init",
        "schema_contract",
        "session_window_source",
        "nyse_calendar_source",
        "lib_package_init",
    }
    for field, relative in source_paths.items():
        wrong = replace(policy, **{field: "f" * 64})
        with pytest.raises(capture.MastermindXCaptureError, match="binding drifted"):
            _successful_attestation(monkeypatch, wrong)

    wrong_tree = replace(policy, producer_tree_sha="f" * 40)
    with pytest.raises(capture.MastermindXCaptureError, match="exact reviewed producer tree"):
        _successful_attestation(monkeypatch, wrong_tree)

    (root / "unrelated.py").write_text("ACTIVE_SELECTOR = True\n", encoding="utf-8")
    _git(root, "add", "unrelated.py")
    _git(root, "commit", "-q", "-m", "descendant can arm unrelated selector")
    descendant = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "--detach", descendant)
    assert _git(root, "merge-base", "--is-ancestor", head, descendant) == ""
    with pytest.raises(capture.MastermindXCaptureError, match="exact reviewed producer release"):
        _successful_attestation(monkeypatch, policy)


def test_production_clock_and_calendar_sources_are_non_overridable_and_pinned(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    _root, _head, policy = installed_checkout
    assert set(inspect.signature(capture.build_mastermindx_capture_attestation).parameters) == {
        "release_policy"
    }
    assert "datetime.now(timezone.utc)" in inspect.getsource(capture._runtime_now)
    receipts = capture._policy_authority_receipts(policy)
    assert receipts["session_window_source"]["path"] == "engine/session_digest.py"
    assert receipts["nyse_calendar_source"]["path"] == "lib/nyse_calendar.py"


def test_install_lock_is_nonfollowing_owned_exact_and_times_out(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, _policy = installed_checkout
    original_flock = capture.fcntl.flock

    def always_busy(descriptor: int, operation: int) -> None:
        if operation & fcntl.LOCK_NB:
            raise BlockingIOError(capture.errno.EAGAIN, "busy")
        original_flock(descriptor, operation)

    monkeypatch.setattr(capture, "INSTALL_LOCK_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(capture.fcntl, "flock", always_busy)
    started = time.monotonic()
    with pytest.raises(capture.MastermindXCaptureError, match="timed out"):
        with capture._shared_install_lock():
            raise AssertionError("lock must not be acquired")
    assert time.monotonic() - started < 0.5


def test_install_lock_rejects_symlink_path(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    _root, _head, _policy = installed_checkout
    real = capture.INSTALL_LOCK_PATH.parent / "real.lock"
    real.write_bytes(b"")
    real.chmod(0o600)
    capture.INSTALL_LOCK_PATH.symlink_to(real)
    with pytest.raises(capture.MastermindXCaptureError, match="install lock failed"):
        with capture._shared_install_lock():
            raise AssertionError("symlink lock must not be followed")


def test_install_lock_rejects_path_swap_during_flock_wait(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, _policy = installed_checkout
    descriptor = os.open(capture.INSTALL_LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    waiting = threading.Event()
    failures: list[BaseException] = []
    original_acquire = capture._acquire_flock_with_timeout

    def announced_acquire(*args: object, **kwargs: object) -> None:
        waiting.set()
        original_acquire(*args, **kwargs)

    def contender() -> None:
        try:
            with capture._shared_install_lock():
                raise AssertionError("swapped lock path must not be accepted")
        except BaseException as exc:  # captured for assertion in the main thread
            failures.append(exc)

    monkeypatch.setattr(capture, "INSTALL_LOCK_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(capture, "_acquire_flock_with_timeout", announced_acquire)
    thread = threading.Thread(target=contender)
    thread.start()
    assert waiting.wait(timeout=1)
    parked = capture.INSTALL_LOCK_PATH.with_name("parked.lock")
    capture.INSTALL_LOCK_PATH.rename(parked)
    capture.INSTALL_LOCK_PATH.write_bytes(b"")
    capture.INSTALL_LOCK_PATH.chmod(0o600)
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], capture.MastermindXCaptureError)
    assert "path changed after acquisition" in str(failures[0])


def test_install_lock_rejects_path_swap_before_release(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    _root, _head, _policy = installed_checkout
    with pytest.raises(capture.MastermindXCaptureError, match="before release"):
        with capture._shared_install_lock():
            parked = capture.INSTALL_LOCK_PATH.with_name("parked.lock")
            capture.INSTALL_LOCK_PATH.rename(parked)
            capture.INSTALL_LOCK_PATH.write_bytes(b"")
            capture.INSTALL_LOCK_PATH.chmod(0o600)


def test_future_installer_and_launcher_hard_dependencies_are_executable_contracts() -> None:
    assert capture.FUTURE_INSTALLER_HARD_REQUIREMENTS == (
        "exclusive_same_lock_before_and_through_adjacent_swap",
        "bounded_lock_wait_fail_closed",
        "exact_detached_clean_release_and_tree_from_external_policy",
        "no_in_place_checkout_mutation",
        "rollback_checkout_preserved",
        "launcher_policy_and_checkout_cut_over_as_one_governed_release",
        "purge_in_checkout_python_bytecode_caches_before_cutover",
    )
    assert capture.FUTURE_LAUNCHER_HARD_REQUIREMENTS == (
        "literal_external_policy_not_runtime_derived",
        "public_builder_current_slot_only_no_clock_or_schedule_input",
        "same_effective_user_as_owned_checkout_and_lock",
        "outer_private_append_receipt_for_durable_host_occurrence",
        "external_owned_0700_pythonpycacheprefix_outside_checkout",
        "python_started_without_in_checkout_bytecode_cache",
    )
    seen_ops: list[int] = []
    original = capture._install_lock

    @capture.contextmanager
    def record_lock(operation: int):
        seen_ops.append(operation)
        yield

    capture._install_lock = record_lock
    try:
        with capture._shared_install_lock():
            pass
        with capture._exclusive_install_lock():
            pass
    finally:
        capture._install_lock = original
    assert seen_ops == [fcntl.LOCK_SH, fcntl.LOCK_EX]


def test_owned_file_open_is_nofollow_fstat_bound_and_final_rechecked(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _head, policy = installed_checkout
    target = root / capture.SESSION_DIGEST_RELATIVE_PATH
    original_checkout = capture._checkout_attestation
    calls = 0

    def replace_same_bytes(
        checkout_root: Path, release_policy: capture.CaptureReleasePolicy
    ) -> tuple[dict, dict, dict]:
        nonlocal calls
        result = original_checkout(checkout_root, release_policy)
        calls += 1
        if calls == 3:
            body = target.read_bytes()
            replacement = target.with_suffix(".replacement")
            replacement.write_bytes(body)
            replacement.chmod(0o644)
            replacement.replace(target)
        return result

    monkeypatch.setattr(capture, "_checkout_attestation", replace_same_bytes)
    with pytest.raises(capture.MastermindXCaptureError, match="changed during final validation"):
        _successful_attestation(monkeypatch, policy)

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    assert nofollow
    seen_flags: list[int] = []
    original_open = capture.os.open

    def recording_open(
        path: Path,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        if Path(path) == root / capture.MODULE_RELATIVE_PATH:
            seen_flags.append(flags)
        return original_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as local:
        local.setattr(capture.os, "open", recording_open)
        capture._read_owned_regular(
            root / capture.MODULE_RELATIVE_PATH, label="module"
        )
    assert seen_flags and all(flags & nofollow for flags in seen_flags)


def test_final_snapshot_rejects_same_release_root_inode_swap(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _head, policy = installed_checkout
    original_checkout = capture._checkout_attestation
    calls = 0

    def swap_root_after_final_snapshot(
        checkout_root: Path, release_policy: capture.CaptureReleasePolicy
    ) -> tuple[dict, dict, dict]:
        nonlocal calls
        result = original_checkout(checkout_root, release_policy)
        calls += 1
        if calls == 3:
            parked = root.with_name(root.name + "-parked")
            root.rename(parked)
            shutil.copytree(parked, root, symlinks=True)
            root.chmod(0o700)
        return result

    monkeypatch.setattr(
        capture, "_checkout_attestation", swap_root_after_final_snapshot
    )
    with pytest.raises(capture.MastermindXCaptureError, match="changed during final validation"):
        _successful_attestation(monkeypatch, policy)


def test_constants_and_built_payload_are_deeply_isolated(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    assert isinstance(capture.FALSE_AUTHORITY, MappingProxyType)
    assert isinstance(capture.CLAIM_BOUNDARY, MappingProxyType)
    assert isinstance(capture.OBSERVATION, MappingProxyType)
    with pytest.raises(TypeError):
        capture.FALSE_AUTHORITY["may_trade"] = True  # type: ignore[index]
    first = _successful_attestation(monkeypatch, policy)
    first["observation"]["emitted_enrollment_event_ids"].append("forged")
    first["authority"]["may_trade"] = True
    second = _successful_attestation(monkeypatch, policy)
    assert second["observation"]["emitted_enrollment_event_ids"] == []
    assert second["authority"]["may_trade"] is False


def test_source_schema_validator_runs_in_build_and_replay_and_is_closed(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    original = capture._validate_source_schema
    calls = 0

    def counting_validator(payload: dict, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        original(payload, **kwargs)

    monkeypatch.setattr(capture, "_validate_source_schema", counting_validator)
    payload = _successful_attestation(monkeypatch, policy)
    assert calls == 1
    capture.validate_attestation(payload, release_policy=policy)
    assert calls == 2
    payload["unexpected"] = True
    with pytest.raises(capture.MastermindXCaptureError, match="fields are not exact"):
        capture.validate_attestation(payload, release_policy=policy)


def test_replay_requires_exact_externally_pinned_schema_bytes(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    payload = _successful_attestation(monkeypatch, policy)
    capture.SCHEMA_PATH.write_bytes(capture.SCHEMA_PATH.read_bytes() + b" ")
    with pytest.raises(capture.MastermindXCaptureError, match="schema release binding drifted"):
        capture.validate_attestation(payload, release_policy=policy)


def test_shared_lock_spans_schema_validation_and_final_checkout_recheck(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    held = False
    validations = 0
    snapshots = 0
    original_validator = capture.validate_attestation
    original_checkout = capture._checkout_attestation

    @capture.contextmanager
    def marked_lock():
        nonlocal held
        held = True
        try:
            yield
        finally:
            held = False

    def checked_validator(*args: object, **kwargs: object) -> dict:
        nonlocal validations
        assert held
        validations += 1
        return original_validator(*args, **kwargs)

    def checked_checkout(*args: object, **kwargs: object) -> tuple[dict, dict, dict]:
        nonlocal snapshots
        assert held
        snapshots += 1
        return original_checkout(*args, **kwargs)

    monkeypatch.setattr(capture, "_shared_install_lock", marked_lock)
    monkeypatch.setattr(capture, "validate_attestation", checked_validator)
    monkeypatch.setattr(capture, "_checkout_attestation", checked_checkout)
    _successful_attestation(monkeypatch, policy)
    assert validations == 1
    assert snapshots == 4
    assert held is False


def test_occurrence_limit_precise_abstention_and_byte_cap_alignment(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _head, policy = installed_checkout
    payload = _successful_attestation(monkeypatch, policy)
    assert payload["occurrence_trust"] == {
        "basis": "same_process_host_clock_only",
        "host_clock_cryptographically_attested": False,
        "platform_and_tzdata_attested": False,
        "standalone_replay_proves_host_occurrence": False,
        "outer_private_append_receipt_required": True,
    }
    assert payload["disposition"] == "registered_selector_inactive"
    assert payload["selector_registration"]["current_slot_reason_code"] == (
        "REGISTERED_SELECTOR_INACTIVE"
    )
    assert payload["claim_boundary"]["current_candidate_absence_observed"] is False
    schema = json.loads(capture.SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$defs"]["fileReceipt"]["properties"]["object_bytes"]["maximum"] == (
        capture.MAX_ATTESTED_FILE_BYTES
    )


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_index_hiding_flags_fail_closed_without_mutating_index(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
) -> None:
    root, _head, policy = installed_checkout
    target = capture.SESSION_DIGEST_RELATIVE_PATH.as_posix()
    _git(root, "update-index", flag, target)
    before = (root / ".git" / "index").read_bytes()
    with pytest.raises(capture.MastermindXCaptureError, match="index contains"):
        _successful_attestation(monkeypatch, policy)
    assert (root / ".git" / "index").read_bytes() == before


def test_staged_index_blob_or_mode_drift_fails_exact_tuple_gate(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _head, policy = installed_checkout
    target = root / capture.SESSION_DIGEST_RELATIVE_PATH
    target.write_bytes(target.read_bytes() + b"\n")
    _git(root, "add", capture.SESSION_DIGEST_RELATIVE_PATH.as_posix())
    target.write_bytes(
        subprocess.run(
            [
                str(capture.GIT_BINARY),
                "-C",
                str(root),
                "show",
                "HEAD:engine/session_digest.py",
            ],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
    )
    with pytest.raises(capture.MastermindXCaptureError, match="mode/object/stage"):
        _successful_attestation(monkeypatch, policy)


def test_raw_tracked_tree_verifier_is_bounded_and_uses_one_inventory_call(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, head, _policy = installed_checkout
    tracked_count = len(_git(root, "ls-files").splitlines())
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
    original = capture._git

    def recording_git(
        checkout: Path, *arguments: str, **kwargs: object
    ) -> tuple[int, bytes]:
        calls.append((arguments, kwargs))
        return original(checkout, *arguments, **kwargs)

    monkeypatch.setattr(capture, "_git", recording_git)
    started = time.monotonic()
    scan_sha256, file_count, total_bytes = (
        capture._ORIGINAL_TRACKED_TREE_VERIFIER(root, head=head)
    )
    assert time.monotonic() - started < 5
    assert len(scan_sha256) == 64
    assert file_count == tracked_count
    assert total_bytes > 0
    assert [arguments for arguments, _kwargs in calls] == [
        ("ls-tree", "-r", "-l", "-z", head),
    ]


def test_raw_tree_verifier_detects_worktree_byte_drift_despite_installed_index(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, head, _policy = installed_checkout
    target = root / capture.SESSION_DIGEST_RELATIVE_PATH
    _git(root, "update-index", "--assume-unchanged", target.relative_to(root).as_posix())
    target.write_bytes(target.read_bytes() + b"\n")
    original = capture._ORIGINAL_TRACKED_TREE_VERIFIER
    with pytest.raises(
        capture.MastermindXCaptureError,
        match="metadata differs|raw bytes differ",
    ):
        original(root, head=head)


def test_raw_tree_verifier_bypasses_clean_filter_and_attributes(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _head, policy = installed_checkout
    filter_script = capture.INSTALL_LOCK_PATH.parent / "clean_filter.py"
    filter_script.write_text(
        "import sys\nsys.stdout.write(sys.stdin.read().replace('worktree', 'canonxxx'))\n",
        encoding="utf-8",
    )
    filter_script.chmod(0o644)
    _git(root, "config", "filter.capture-mask.clean", f"python3 {filter_script}")
    _git(root, "config", "filter.capture-mask.smudge", "cat")
    _git(root, "config", "filter.capture-mask.required", "true")
    (root / ".gitattributes").write_text(
        "filtered.txt filter=capture-mask\n", encoding="utf-8"
    )
    filtered = root / "filtered.txt"
    filtered.write_text("worktree\n", encoding="utf-8")
    filtered.chmod(0o644)
    _git(root, "add", ".gitattributes", "filtered.txt")
    _git(root, "commit", "-q", "-m", "add clean-filtered fixture")
    head = _git(root, "rev-parse", "HEAD")
    policy = replace(
        policy,
        producer_release_sha=head,
        producer_tree_sha=_git(root, "rev-parse", "HEAD^{tree}"),
    )
    assert subprocess.run(
        [str(capture.GIT_BINARY), "-C", str(root), "diff", "--quiet", "--", "filtered.txt"],
        check=False,
    ).returncode == 0
    monkeypatch.setattr(
        capture,
        "_verify_all_tracked_worktree_bytes",
        capture._ORIGINAL_TRACKED_TREE_VERIFIER,
    )
    with pytest.raises(capture.MastermindXCaptureError, match="raw bytes differ"):
        _successful_attestation(monkeypatch, policy)


def test_raw_tree_verifier_rejects_mode_drift_hidden_by_local_config(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    root, head, _policy = installed_checkout
    target = root / capture.SESSION_DIGEST_RELATIVE_PATH
    _git(root, "config", "core.filemode", "false")
    target.chmod(0o755)
    assert _git(root, "status", "--porcelain=v1") == ""
    with pytest.raises(capture.MastermindXCaptureError, match="metadata differs"):
        capture._ORIGINAL_TRACKED_TREE_VERIFIER(root, head=head)


def test_raw_tree_verifier_rejects_intermediate_directory_symlink(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    root, head, _policy = installed_checkout
    engine = root / "engine"
    parked = root / "engine-real"
    engine.rename(parked)
    engine.symlink_to(parked.name)
    with pytest.raises(capture.MastermindXCaptureError, match="tracked directory engine is unsafe"):
        capture._ORIGINAL_TRACKED_TREE_VERIFIER(root, head=head)


def test_ci_manifest_and_release_policy_pin_import_package_initializers() -> None:
    manifest = (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    job = manifest.split("  mastermindx-selector-capture-attestation:", 1)[1]
    assert "      - engine/__init__.py\n" in job
    assert "      - lib/__init__.py\n" in job
    assert capture.AUTHORITY_SOURCE_PATHS["engine_package_init"] == Path(
        "engine/__init__.py"
    )
    assert capture.AUTHORITY_SOURCE_PATHS["lib_package_init"] == Path(
        "lib/__init__.py"
    )


def test_ignored_cache_allowlist_is_bounded_owned_inert_and_python_refused(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
) -> None:
    root, _head, _policy = installed_checkout
    pytest_cache = root / ".pytest_cache"
    pytest_cache.mkdir(mode=0o700)
    cache_file = pytest_cache / "CACHEDIR.TAG"
    cache_file.write_text("cache", encoding="utf-8")
    cache_file.chmod(0o600)
    capture._verify_ignored_caches(root)

    (root / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n",
        encoding="utf-8",
    )
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-q", "-m", "ignore test caches")
    bytecode = root / "engine" / "__pycache__"
    bytecode.mkdir(mode=0o700)
    forged = bytecode / "options_mastermindx_capture.cpython-312.pyc"
    forged.write_bytes(b"forged executable bytecode")
    forged.chmod(0o600)
    with pytest.raises(capture.MastermindXCaptureError, match="unsafe ignored path"):
        capture._verify_ignored_caches(root)


@pytest.mark.parametrize("mutation", ["executable", "hardlink", "symlink", "oversize"])
def test_ignored_pytest_cache_file_metadata_is_strict(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    tmp_path: Path,
    mutation: str,
) -> None:
    root, _head, _policy = installed_checkout
    cache = root / ".pytest_cache"
    cache.mkdir(mode=0o700)
    target = cache / "CACHEDIR.TAG"
    target.write_bytes(b"cache")
    target.chmod(0o600)
    if mutation == "executable":
        target.chmod(0o700)
    elif mutation == "hardlink":
        os.link(target, tmp_path / "cache-hardlink")
    elif mutation == "symlink":
        external = tmp_path / "cache-target"
        target.replace(external)
        target.symlink_to(external)
    elif mutation == "oversize":
        target.write_bytes(b"x" * (capture.MAX_IGNORED_CACHE_FILE_BYTES + 1))
    with pytest.raises(capture.MastermindXCaptureError, match="cache file .* is unsafe"):
        capture._verify_ignored_caches(root)


def test_ignored_cache_entry_cap_is_checked_before_traversal(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _head, _policy = installed_checkout
    raw = b"\0".join(
        f".pytest_cache/v/cache/{index}".encode()
        for index in range(capture.MAX_IGNORED_CACHE_ENTRIES + 1)
    ) + b"\0"
    monkeypatch.setattr(capture, "_git", lambda *args, **kwargs: (0, raw))
    with pytest.raises(capture.MastermindXCaptureError, match="entry cap exceeded"):
        capture._verify_ignored_caches(root)


@pytest.mark.parametrize(
    "relative",
    [Path("engine/forged_runtime.py"), Path("config/forged_runtime.yml")],
)
def test_ignored_python_or_config_path_is_never_an_allowed_cache(
    installed_checkout: tuple[Path, str, capture.CaptureReleasePolicy],
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
) -> None:
    root, _head, _policy = installed_checkout
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("forged", encoding="utf-8")
    target.chmod(0o600)
    monkeypatch.setattr(
        capture,
        "_git",
        lambda *args, **kwargs: (0, relative.as_posix().encode() + b"\0"),
    )
    with pytest.raises(capture.MastermindXCaptureError, match="unsafe ignored path"):
        capture._verify_ignored_caches(root)
