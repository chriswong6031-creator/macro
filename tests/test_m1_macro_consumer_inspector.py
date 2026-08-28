"""Hermetic tests for the read-only M1 Macro consumer inspector."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import time

import pytest

from scripts import inspect_m1_macro_consumers as census


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
    )


def _init_repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.name", "Inspector Test")
    _git(path, "config", "user.email", "inspector@example.invalid")
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-m", "initial")


def _write_scope(
    path: Path,
    services: list[dict[str, object]],
    **overrides: object,
) -> bytes:
    payload: dict[str, object] = {
        "schema": "macro.m1_consumer_scope.v1",
        "hostname": socket.gethostname(),
        "services": services,
        "scheduler_surfaces_checked": ["launchd-current-user", "launchd-system"],
        "recent_job_sources_checked": ["declared-launchd-streams"],
    }
    payload.update(overrides)
    raw = json.dumps(payload, sort_keys=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return raw


@pytest.mark.parametrize("state", ("true", "disabled"))
def test_parse_launchctl_disabled_accepts_native_disabled_spellings(state: str) -> None:
    label = "com.macro.live-breadth"
    raw = f'disabled services = {{\n    "{label}" => {state}\n}}\n'
    assert census.parse_launchctl_disabled(raw, label) == (True, state)


@pytest.mark.parametrize(
    "raw",
    (
        '"com.macro.live-breadth" => false\n',
        '"com.macro.live-breadth" => enabled\n',
        '"com.macro.live-breadth-extra" => disabled\n',
        '"com.macro.live-breadth" => disabled extra\n',
        (
            '"com.macro.live-breadth" => disabled\n'
            '"com.macro.live-breadth" => true\n'
        ),
    ),
)
def test_parse_launchctl_disabled_rejects_false_ambiguous_or_inexact_rows(
    raw: str,
) -> None:
    with pytest.raises(
        census.InspectionError,
        match="LAUNCHCTL_DISABLED_STATE_INVALID",
    ):
        census.parse_launchctl_disabled(raw, "com.macro.live-breadth")


def test_service_definition_emits_env_names_and_checkout_candidates_without_values(
    tmp_path: Path,
) -> None:
    plist_path = tmp_path / "com.mastermind.optionshub.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.mastermind.optionshub",
                "ProgramArguments": [
                    "/bin/bash",
                    "/Users/chriswong/hub-ops-wt/scripts/run_optionshub.sh",
                ],
                "WorkingDirectory": "/Users/chriswong/hub-ops-wt",
                "EnvironmentVariables": {
                    "PYTHONPATH": "/Users/chriswong/hub-ops-wt",
                    "SECRET_TOKEN": "must-never-appear",
                },
            }
        )
    )

    label, entrypoint, cwd, env_names, candidates, recent_paths = (
        census.service_definition(plist_path)
    )
    assert label == "com.mastermind.optionshub"
    assert entrypoint == "/Users/chriswong/hub-ops-wt/scripts/run_optionshub.sh"
    assert cwd == "/Users/chriswong/hub-ops-wt"
    assert env_names == ("PYTHONPATH", "SECRET_TOKEN")
    assert Path("/Users/chriswong/hub-ops-wt") in candidates
    assert recent_paths == ()
    rendered = repr((label, entrypoint, cwd, env_names, candidates, recent_paths))
    assert "must-never-appear" not in rendered


def test_service_definition_uses_absolute_script_parent_without_working_directory(
    tmp_path: Path,
) -> None:
    plist_path = tmp_path / "script-only.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.macro.script-only",
                "ProgramArguments": ["/opt/macro/bin/run.sh", "--safe"],
            }
        )
    )

    _, entrypoint, cwd, _, candidates, _ = census.service_definition(plist_path)
    assert entrypoint == "/opt/macro/bin/run.sh"
    assert cwd is None
    assert Path("/opt/macro/bin") in candidates


@pytest.mark.parametrize(
    "working_directory",
    (
        "relative/checkout",
        "https://user:secret-marker@github.com/example/repo",
    ),
)
def test_service_definition_rejects_non_absolute_working_directory_before_rendering(
    tmp_path: Path,
    working_directory: str,
) -> None:
    plist_path = tmp_path / "unsafe-working-directory.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.macro.unsafe-working-directory",
                "ProgramArguments": ["/opt/macro/run"],
                "WorkingDirectory": working_directory,
            }
        )
    )

    with pytest.raises(census.InspectionError, match="PLIST_INVALID") as exc:
        census.service_definition(plist_path)
    assert "secret-marker" not in str(exc.value)


def test_service_definition_accepts_only_absolute_standard_stream_paths(
    tmp_path: Path,
) -> None:
    plist_path = tmp_path / "streams.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.macro.streams",
                "ProgramArguments": ["/opt/macro/run"],
                "StandardOutPath": "/var/tmp/macro.out",
                "StandardErrorPath": "relative.err",
            }
        )
    )

    *_, recent_paths = census.service_definition(plist_path)
    assert recent_paths == (Path("/var/tmp/macro.out"),)


def test_service_definition_rejects_malformed_plist(tmp_path: Path) -> None:
    plist_path = tmp_path / "invalid.plist"
    plist_path.write_bytes(b"not a plist")

    with pytest.raises(census.InspectionError, match="PLIST_INVALID"):
        census.service_definition(plist_path)


@pytest.mark.parametrize(
    "url, expected",
    (
        (
            "git@github.com:mastermindx-market-intelligence/macro.git",
            (True, False, False),
        ),
        (
            "ssh://git@github.com/mastermindx-market-intelligence/macro.git",
            (True, False, False),
        ),
        (
            "https://github.com/mastermindx-market-intelligence/macro.git",
            (True, False, True),
        ),
        (
            "git@github.com:chriswong6031-creator/macro.git",
            (False, True, False),
        ),
        (
            "https://github.com/chriswong6031-creator/macro.git",
            (False, True, True),
        ),
        (
            "https://github.com/MastermindX-Market-Intelligence/Macro.git",
            (True, False, True),
        ),
        (
            "git@github.com:ChrisWong6031-Creator/Macro.git",
            (False, True, False),
        ),
        (
            "git@github.com:mastermindx-market-intelligence/other.git",
            (False, False, False),
        ),
    ),
)
def test_classify_remote(
    url: str,
    expected: tuple[bool, bool, bool],
) -> None:
    assert census.classify_remote(url) == expected


def test_inspect_checkout_is_local_read_only_and_counts_dirty_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", "git@github.com:chriswong6031-creator/macro.git")
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

    observed_commands: list[tuple[str, ...]] = []

    def recording_run_git(path: Path, *suffix: str) -> subprocess.CompletedProcess[str]:
        observed_commands.append(tuple(suffix))
        return census._run_git(path, *suffix)

    evidence = census.inspect_checkout(repo, run_git=recording_run_git)

    assert evidence is not None
    assert evidence.git_identity.wrong_owner is True
    assert evidence.git_identity.anonymous_transport is False
    assert evidence.dirty_tracked_count == 1
    assert evidence.dirty_untracked_count == 1
    flattened = {part for command in observed_commands for part in command}
    assert not ({"fetch", "pull", "reset"} & flattened)
    status_suffix = next(command for command in observed_commands if command[0] == "status")
    assert status_suffix == (
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=all",
    )


@pytest.mark.parametrize(
    "remote",
    (
        "git@GitHub.com:MastermindX-Market-Intelligence/Macro.git",
        "SSH://git@GitHub.com/MastermindX-Market-Intelligence/Macro.git",
    ),
)
def test_inspect_checkout_marks_case_variant_ssh_without_identity_as_ambient(
    tmp_path: Path,
    remote: str,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "remote", "add", "origin", remote)

    evidence = census.inspect_checkout(repo)

    assert evidence is not None
    assert evidence.remote_states == ("canonical_ssh",)
    assert evidence.git_identity.canonical_repo is True
    assert evidence.git_identity.explicit_machine_identity is False
    assert evidence.git_identity.ambient_fallback_possible is True


def test_inspect_checkout_neutralizes_hostile_fsmonitor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    marker = tmp_path / "fsmonitor-executed"
    monitor = tmp_path / "monitor.sh"
    monitor.write_text(
        f"#!/bin/sh\n/usr/bin/touch {marker}\nexit 0\n",
        encoding="utf-8",
    )
    monitor.chmod(0o700)
    _git(repo, "config", "core.fsmonitor", str(monitor))

    evidence = census.inspect_checkout(repo)

    assert evidence is not None
    assert not marker.exists()
    assert census.GIT_SAFETY_PREFIX[:2] == ("--no-optional-locks", "-c")
    assert "core.fsmonitor=false" in census.GIT_SAFETY_PREFIX
    assert "core.hooksPath=/dev/null" in census.GIT_SAFETY_PREFIX


def test_inspect_checkout_discards_remote_and_credential_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    token = "ghp_super_secret_marker"
    remote = f"https://oauth2:{token}@github.com/mastermindx-market-intelligence/macro.git"
    helper = "!printf helper-super-secret"
    _git(repo, "remote", "add", "origin", remote)
    _git(repo, "config", "credential.helper", helper)

    evidence = census.inspect_checkout(repo)
    rendered = repr(evidence)

    assert evidence is not None
    assert token not in rendered
    assert remote not in rendered
    assert helper not in rendered


def test_git_child_environment_does_not_inherit_control_variables(monkeypatch) -> None:
    monkeypatch.setenv("GIT_SSH_COMMAND", "must-not-pass")
    monkeypatch.setenv("SSH_AUTH_SOCK", "must-not-pass")
    monkeypatch.setenv("GIT_ASKPASS", "must-not-pass")
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "must-not-pass")

    assert census._git_environment() == {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def test_scope_manifest_binds_exact_bytes_and_report_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    services: list[dict[str, object]] = []
    for label in ("com.macro.zeta", "com.macro.alpha"):
        plist_path = tmp_path / f"{label}.plist"
        plist_path.write_bytes(
            plistlib.dumps(
                {
                    "Label": label,
                    "ProgramArguments": ["/bin/true"],
                    "WorkingDirectory": str(repo),
                    "EnvironmentVariables": {"SECRET_TOKEN": "never-render"},
                }
            )
        )
        services.append(
            {
                "service_id": label,
                "domain": f"gui/{os.getuid()}",
                "plist_path": str(plist_path),
                "recent_evidence_paths": [],
            }
        )
    manifest_path = tmp_path / "scope.json"
    raw = _write_scope(manifest_path, services)

    scope = census.parse_scope_manifest(manifest_path)
    report = census.build_report(
        scope,
        launchctl_probe=lambda _label, _domain: (True, False, None),
        hostname=socket.gethostname(),
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
    )
    rendered = census.render_json(report)
    payload = json.loads(rendered)

    assert scope.exact_sha256 == census.hashlib.sha256(raw).hexdigest()
    assert payload["schema"] == "macro.m1_consumer_census.v1"
    assert payload["observed_at"].endswith("+00:00")
    assert [row["service_id"] for row in payload["services"]] == [
        "com.macro.alpha",
        "com.macro.zeta",
    ]
    assert "classification" not in rendered
    assert "KEEP_AUTHENTICATE" not in rendered
    assert "never-render" not in rendered
    assert payload["supplied_scope_sha256"] == scope.exact_sha256
    assert payload["complete_for_supplied_scope"] is True
    assert "complete_for_cutover" not in payload
    assert census.render_table(report).splitlines()[0] == (
        "SERVICE | LOADED | DISABLED | CHECKOUT | REMOTE_STATE | "
        "LAST_EXECUTION | HAZARDS"
    )


@pytest.mark.parametrize(
    "mutator",
    (
        lambda payload: payload.update(hostname="wrong-host"),
        lambda payload: payload["services"].append(dict(payload["services"][0])),
        lambda payload: payload["services"][0].update(domain="gui/999999"),
        lambda payload: payload["services"][0].update(plist_path="relative.plist"),
        lambda payload: payload.pop("scheduler_surfaces_checked"),
        lambda payload: payload.pop("recent_job_sources_checked"),
        lambda payload: payload.update(
            scheduler_surfaces_checked=["launchd-current-user"] * 2
        ),
        lambda payload: payload.update(
            recent_job_sources_checked=["declared-launchd-streams"] * 2
        ),
        lambda payload: payload["services"][0].update(
            recent_evidence_paths=["relative.log"]
        ),
    ),
)
def test_scope_manifest_rejects_incomplete_or_ambiguous_input(
    tmp_path: Path,
    mutator,
) -> None:
    plist_path = tmp_path / "service.plist"
    plist_path.write_bytes(
        plistlib.dumps({"Label": "com.macro.test", "ProgramArguments": ["/bin/true"]})
    )
    payload = {
        "schema": "macro.m1_consumer_scope.v1",
        "hostname": socket.gethostname(),
        "services": [
            {
                "service_id": "com.macro.test",
                "domain": f"gui/{os.getuid()}",
                "plist_path": str(plist_path),
                "recent_evidence_paths": [],
            }
        ],
        "scheduler_surfaces_checked": ["launchd-current-user"],
        "recent_job_sources_checked": ["declared-launchd-streams"],
    }
    mutator(payload)
    manifest_path = tmp_path / "invalid-scope.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(census.InspectionError, match="SCOPE_MANIFEST_INVALID"):
        census.parse_scope_manifest(manifest_path)


def test_scope_manifest_rejects_duplicate_recent_evidence_paths(
    tmp_path: Path,
) -> None:
    plist_path = tmp_path / "service.plist"
    plist_path.write_bytes(
        plistlib.dumps({"Label": "com.macro.test", "ProgramArguments": ["/bin/true"]})
    )
    evidence_path = tmp_path / "service.log"
    manifest_path = tmp_path / "invalid-scope.json"
    _write_scope(
        manifest_path,
        [
            {
                "service_id": "com.macro.test",
                "domain": f"gui/{os.getuid()}",
                "plist_path": str(plist_path),
                "recent_evidence_paths": [str(evidence_path), str(evidence_path)],
            }
        ],
    )

    with pytest.raises(census.InspectionError, match="SCOPE_MANIFEST_INVALID"):
        census.parse_scope_manifest(manifest_path)


def test_build_report_retains_retired_breadth_disabled_loaded_state(
    tmp_path: Path,
) -> None:
    plist_path = tmp_path / "live-breadth.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "com.macro.live-breadth",
                "ProgramArguments": ["/bin/true"],
            }
        )
    )
    manifest_path = tmp_path / "scope.json"
    _write_scope(
        manifest_path,
        [
            {
                "service_id": "com.macro.live-breadth",
                "domain": "system",
                "plist_path": str(plist_path),
                "recent_evidence_paths": [],
            }
        ],
    )

    report = census.build_report(
        census.parse_scope_manifest(manifest_path),
        launchctl_probe=lambda _label, _domain: (True, False, False),
        hostname=socket.gethostname(),
        now=datetime.now(timezone.utc),
    )
    service = report.services[0]

    assert service.enabled is False
    assert service.loaded is True
    assert service.active is False
    assert service.disabled_observed_state == "disabled"
    assert "RETIRE_DUPLICATE" not in service.hazards
    assert "PROVEN_LIVE" not in service.hazards


def test_build_report_fails_closed_on_bad_plist_and_missing_evidence(
    tmp_path: Path,
) -> None:
    plist_path = tmp_path / "bad.plist"
    plist_path.write_bytes(b"invalid")
    missing = tmp_path / "missing.log"
    manifest_path = tmp_path / "scope.json"
    _write_scope(
        manifest_path,
        [
            {
                "service_id": "com.macro.bad",
                "domain": f"gui/{os.getuid()}",
                "plist_path": str(plist_path),
                "recent_evidence_paths": [str(missing)],
            }
        ],
    )

    report = census.build_report(
        census.parse_scope_manifest(manifest_path),
        launchctl_probe=lambda _label, _domain: (True, True, None),
        hostname=socket.gethostname(),
        now=datetime.now(timezone.utc),
    )

    assert report.complete_for_supplied_scope is False
    assert "PLIST_INVALID" in report.services[0].inspection_errors
    assert any("RECENT_EVIDENCE_UNAVAILABLE" in item for item in report.scope_coverage_errors)


@pytest.mark.parametrize("domain", (f"gui/{os.getuid()}", "system"))
def test_probe_launchctl_uses_exact_read_only_argv_and_state_mapping(domain: str) -> None:
    calls: list[tuple[str, ...]] = []
    label = "com.macro.test"

    def fake_run(*suffix: str) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(suffix))
        if suffix[0] == "print-disabled":
            return subprocess.CompletedProcess(suffix, 0, f'"{label}" => disabled\n', "")
        return subprocess.CompletedProcess(suffix, 0, "    state = not running\n", "")

    assert census.probe_launchctl(label, domain, run_launchctl=fake_run) == (
        True,
        False,
        False,
    )
    target = f"{domain}/{label}"
    assert calls == [("print-disabled", domain), ("print", target)]


@pytest.mark.parametrize(
    "label, domain",
    (
        ("bad/label", "system"),
        ("bad label", "system"),
        ("com.macro.test", "user/501"),
        ("com.macro.test", "gui/999999"),
    ),
)
def test_probe_launchctl_refuses_invalid_targets_before_child_creation(
    label: str,
    domain: str,
) -> None:
    called = False

    def should_not_run(*_suffix: str) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        raise AssertionError("child must not start")

    with pytest.raises(census.InspectionError, match="READ_ONLY_COMMAND_REFUSED"):
        census.probe_launchctl(label, domain, run_launchctl=should_not_run)
    assert called is False


@pytest.mark.parametrize(
    "state_output",
    (
        "",
        "state = waiting\n",
        "state = running\nstate = not running\n",
    ),
)
def test_probe_launchctl_rejects_missing_ambiguous_or_unknown_state(
    state_output: str,
) -> None:
    def fake_run(*suffix: str) -> subprocess.CompletedProcess[str]:
        if suffix[0] == "print-disabled":
            return subprocess.CompletedProcess(suffix, 0, "", "")
        return subprocess.CompletedProcess(suffix, 0, state_output, "secret-stderr")

    with pytest.raises(census.InspectionError, match="LAUNCHCTL_STATE_INVALID") as exc:
        census.probe_launchctl("com.macro.test", "system", run_launchctl=fake_run)
    assert "secret-stderr" not in str(exc.value)


@pytest.mark.parametrize(
    "suffix",
    (
        ("fetch", "origin"),
        ("pull",),
        ("reset", "--hard"),
        ("clean", "-fd"),
        ("checkout", "main"),
        ("remote", "set-url", "origin", "git@example.invalid:x/y.git"),
        ("config", "--get", "credential.helper"),
        ("status", "--porcelain=v1", "--untracked-files=all"),
    ),
)
def test_git_wrapper_refuses_mutation_or_weakened_suffix_before_child_creation(
    tmp_path: Path,
    monkeypatch,
    suffix: tuple[str, ...],
) -> None:
    called = False

    def should_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("child must not start")

    monkeypatch.setattr(census, "_run_bounded_readonly", should_not_run)
    with pytest.raises(census.InspectionError, match="READ_ONLY_COMMAND_REFUSED"):
        census._run_git(tmp_path, *suffix)
    assert called is False


@pytest.mark.parametrize(
    "suffix",
    (
        ("enable", "system/com.macro.test"),
        ("disable", "system/com.macro.test"),
        ("bootstrap", "system", "/tmp/test.plist"),
        ("bootout", "system/com.macro.test"),
        ("kickstart", "system/com.macro.test"),
    ),
)
def test_launchctl_wrapper_refuses_mutation_before_child_creation(
    monkeypatch,
    suffix: tuple[str, ...],
) -> None:
    called = False

    def should_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("child must not start")

    monkeypatch.setattr(census, "_run_bounded_readonly", should_not_run)
    with pytest.raises(census.InspectionError, match="READ_ONLY_COMMAND_REFUSED"):
        census._run_launchctl(*suffix)
    assert called is False


def test_launchctl_environment_does_not_inherit_loader_or_control_variables(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "must-not-pass")
    monkeypatch.setenv("SSH_AUTH_SOCK", "must-not-pass")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "must-not-pass")
    assert census._launchctl_environment() == {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }


def test_streaming_runner_kills_and_reaps_oversized_child(monkeypatch) -> None:
    real_popen = census.subprocess.Popen
    observed: dict[str, subprocess.Popen[bytes]] = {}

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        observed["process"] = process
        return process

    monkeypatch.setattr(census.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(census, "_MAX_OUTPUT_BYTES", 1024)
    marker = "never-copy-this-marker"
    code = (
        "import os,time;"
        f"os.write(1, b'{marker}' + b'x' * 4096);"
        "time.sleep(30)"
    )
    started = time.monotonic()
    with pytest.raises(census.InspectionError, match="OUTPUT_LIMIT") as exc:
        census._run_bounded_readonly(
            (sys.executable, "-c", code),
            cwd=None,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    assert time.monotonic() - started < 2.0
    assert observed["process"].poll() is not None
    assert marker not in str(exc.value)


def test_streaming_runner_kills_and_reaps_timed_out_child(monkeypatch) -> None:
    real_popen = census.subprocess.Popen
    observed: dict[str, subprocess.Popen[bytes]] = {}

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        observed["process"] = process
        return process

    monkeypatch.setattr(census.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(census, "_COMMAND_TIMEOUT_SECONDS", 0.1)
    started = time.monotonic()
    with pytest.raises(census.InspectionError, match="COMMAND_TIMEOUT"):
        census._run_bounded_readonly(
            ("/bin/sleep", "30"),
            cwd=None,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    assert time.monotonic() - started < 2.0
    assert observed["process"].poll() is not None


def test_streaming_runner_terminates_descendant_process_group(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(census, "_COMMAND_TIMEOUT_SECONDS", 0.2)
    pid_path = tmp_path / "descendant.pid"
    code = (
        "import pathlib,subprocess,time;"
        "child=subprocess.Popen(['/bin/sleep','30']);"
        f"pathlib.Path({str(pid_path)!r}).write_text(str(child.pid));"
        "time.sleep(30)"
    )

    with pytest.raises(census.InspectionError, match="COMMAND_TIMEOUT"):
        census._run_bounded_readonly(
            (sys.executable, "-c", code),
            cwd=None,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )

    descendant_pid = int(pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(descendant_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail(f"descendant process {descendant_pid} survived bounded termination")


def test_main_emits_bounded_json_and_exit_semantics(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    plist_path = tmp_path / "service.plist"
    plist_path.write_bytes(
        plistlib.dumps({"Label": "com.macro.test", "ProgramArguments": ["/bin/true"]})
    )
    manifest_path = tmp_path / "scope.json"
    _write_scope(
        manifest_path,
        [
            {
                "service_id": "com.macro.test",
                "domain": f"gui/{os.getuid()}",
                "plist_path": str(plist_path),
                "recent_evidence_paths": [],
            }
        ],
    )
    monkeypatch.setattr(
        census,
        "probe_launchctl",
        lambda _label, _domain: (True, False, None),
    )

    assert census.main(
        ["--scope-manifest", str(manifest_path), "--format", "json"]
    ) == 0
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["complete_for_supplied_scope"] is True
    assert output.err == ""

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert census.main(
        ["--scope-manifest", str(invalid), "--format", "json"]
    ) == 65
    failure = capsys.readouterr()
    assert failure.out == ""
    assert failure.err.strip() == "INSPECTION_FAILED:SCOPE_MANIFEST_INVALID"


def test_main_maps_missing_required_input_to_sanitized_exit_65(capsys) -> None:
    assert census.main([]) == 65
    failure = capsys.readouterr()
    assert failure.out == ""
    assert failure.err.strip() == "INSPECTION_FAILED:ARGUMENTS_INVALID"


def test_inspector_source_contains_no_mutating_launchctl_or_git_argv() -> None:
    assert not ({"fetch", "pull", "reset", "clean", "checkout"} & {
        suffix[0] for suffix in census.GIT_ALLOWED_SUFFIXES
    })
    for suffix in census.GIT_ALLOWED_SUFFIXES:
        assert suffix[:2] != ("remote", "set-url")
    source = (Path(census.__file__)).read_text(encoding="utf-8")
    assert "subprocess.run(" not in source
    assert ".communicate(" not in source
