"""Regression guards for the isolated, operator-armed BioCatalyst B1 lane."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE_PATH = DEPLOY / "macro-biocatalyst.service"
MACRO_API_SERVICE_PATH = DEPLOY / "macro-api.service"
TIMER_PATH = DEPLOY / "macro-biocatalyst.timer"
HEARTBEAT_SERVICE_PATH = DEPLOY / "macro-biocatalyst-activation-heartbeat.service"
HEARTBEAT_TIMER_PATH = DEPLOY / "macro-biocatalyst-activation-heartbeat.timer"
HEARTBEAT_RUNNER_PATH = DEPLOY / "biocatalyst-activation-heartbeat.sh"
SETUP_PATH = DEPLOY / "biocatalyst-setup.sh"
RUNTIME_PATH = DEPLOY / "biocatalyst-runtime.sh"
SECURE_PATHS_PATH = DEPLOY / "biocatalyst-secure-paths.py"
REQUIREMENTS_PATH = DEPLOY / "biocatalyst-requirements.txt"
API_REQUIREMENTS_PATH = ROOT / "app" / "requirements.txt"
UPDATE_PATH = DEPLOY / "update.sh"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
LEGACY_JOBS_PATH = ROOT / ".github" / "ci" / "legacy-jobs.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _biocatalyst_update_block() -> str:
    update = _text(UPDATE_PATH)
    start = update.index("# BioCatalyst B1 is a separate source-canonical lane.")
    end = update.index("# The daemon imports these modules", start)
    return update[start:end]


def _legacy_job_body(legacy_jobs: str, job_id: str) -> str:
    job = re.search(
        rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z0-9][a-z0-9-]*:|\Z)",
        legacy_jobs,
        re.MULTILINE | re.DOTALL,
    )
    assert job is not None, f"missing legacy CI job: {job_id}"
    return job.group("body")


def _lane_test_paths(job_body: str) -> set[str]:
    """Extract only paths from the YAML folded pytest command, not comments."""

    return set(
        re.findall(
            r"^          (tests/test_[a-z0-9_]+\.py)(?:\s+-q)?$",
            job_body,
            re.MULTILINE,
        )
    )


def test_biocatalyst_deploy_shell_scripts_have_valid_syntax():
    for script in (RUNTIME_PATH, SETUP_PATH, HEARTBEAT_RUNNER_PATH, UPDATE_PATH):
        subprocess.run(["bash", "-n", str(script)], check=True)
    subprocess.run([sys.executable, "-m", "py_compile", str(SECURE_PATHS_PATH)], check=True)


def test_record_history_collector_tests_are_owned_by_the_biocatalyst_ci_lane():
    workflow = _text(CI_WORKFLOW_PATH)
    legacy_jobs = _text(LEGACY_JOBS_PATH)

    assert '"tests/test_clinicaltrials_history.py"' in workflow
    assert "tests/test_clinicaltrials_history.py" in _legacy_job_body(
        legacy_jobs, "biocatalyst-history"
    )


def test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file():
    legacy_jobs = _text(LEGACY_JOBS_PATH)
    # The former aggregate suite exceeded its 20-minute process cap.  The pack
    # runner gives each logical job its own cap, so make ownership and both
    # lower/upper timeout bounds explicit.  A new test_biocatalyst_*.py must
    # therefore be assigned here before it can merge.
    expected_lanes = {
        "biocatalyst-serving": 8,
        "biocatalyst-evidence": 8,
        "biocatalyst-worker": 12,
        "biocatalyst-history": 12,
        "biocatalyst-contracts": 10,
        "biocatalyst-deploy-integration": 12,
        "biocatalyst-regulatory": 12,
    }
    assert "\n  biocatalyst:\n" not in legacy_jobs
    seen_paths: set[str] = set()
    for job_id, expected_timeout in expected_lanes.items():
        body = _legacy_job_body(legacy_jobs, job_id)
        timeout = re.search(r"^    timeout-minutes: (\d+)$", body, re.MULTILINE)
        assert timeout is not None
        assert int(timeout.group(1)) == expected_timeout
        # All subjobs remain intentionally bounded; an arbitrary timeout hike
        # would conceal a regression instead of identifying its contract lane.
        assert 5 <= int(timeout.group(1)) <= 12

        paths = _lane_test_paths(body)
        assert paths, f"{job_id} must run an explicit BioCatalyst test set"
        assert not (seen_paths & paths), (
            f"duplicate BioCatalyst CI ownership: {seen_paths & paths}"
        )
        seen_paths.update(paths)

    expected_paths = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "tests").glob("test_biocatalyst_*.py")
    }
    expected_paths |= {
        "tests/test_clinicaltrials_biocatalyst.py",
        "tests/test_clinicaltrials_history.py",
        "tests/test_sector_intelligence_contracts.py",
        "tests/test_sector_intelligence_ownership.py",
        "tests/test_deploy_update_self_heal.py",
    }
    assert seen_paths == expected_paths


def test_service_is_a_bounded_hardened_oneshot_with_worker_owned_locking():
    service = _text(SERVICE_PATH)

    assert "Type=oneshot" in service
    assert "User=macro-biocatalyst" in service
    assert "Group=macro-biocatalyst" in service
    assert "ConditionPathExists=/etc/macro-biocatalyst.env" in service
    assert "EnvironmentFile=/etc/macro-biocatalyst.env" in service
    assert "Environment=BIOCATALYST_STATE_ROOT=/var/lib/macro-biocatalyst/state" in service
    assert "Environment=BIOCATALYST_PUBLIC_ROOT=/var/lib/macro-biocatalyst/public" in service
    assert "Environment=BIOCATALYST_ACTIVATION_ROOT=/var/lib/macro-biocatalyst/activation" in service
    assert (
        "Environment=BIOCATALYST_R2_ACTIVATION_GATE_PATH="
        "/var/lib/macro-biocatalyst/activation/gate.json"
    ) in service
    assert (
        "Environment=BIOCATALYST_R2_ACTIVATION_HEARTBEAT_PATH="
        "/var/lib/macro-biocatalyst/activation/heartbeat.json"
    ) in service
    assert (
        "ExecStart=/opt/macro-biocatalyst/current/bin/python -m scripts.biocatalyst_worker "
        "--mode canary_poll"
    ) in service
    timeout = int(re.search(r"^TimeoutStartSec=(\d+)$", service, re.MULTILINE).group(1))
    assert 0 < timeout < 60 * 60

    for setting in (
        "UMask=0077",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ReadWritePaths=/var/lib/macro-biocatalyst/state",
        "ReadWritePaths=/var/lib/macro-biocatalyst/public",
        "ReadOnlyPaths=/var/lib/macro-biocatalyst/activation",
        "InaccessiblePaths=/etc/macro-biocatalyst.env",
        "InaccessiblePaths=/etc/macro-biocatalyst-control.env",
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
        assert setting in service

    assert re.search(r"^CapabilityBoundingSet=$", service, re.MULTILINE)
    assert re.search(r"^AmbientCapabilities=$", service, re.MULTILINE)
    assert "StateDirectory=" not in service
    assert "DynamicUser=" not in service

    # The worker, not the systemd unit, owns the non-blocking overlap guard.
    assert "worker owns its non-blocking lock" in service
    assert "flock" not in service
    assert "Restart=always" not in service
    assert "EnvironmentFile=/etc/macro-biocatalyst-control.env" not in service
    assert "BIOCATALYST_R2_CONTROL_" not in service


def test_macro_api_can_read_only_the_public_projection_and_cannot_see_worker_state():
    service = _text(MACRO_API_SERVICE_PATH)

    assert "Environment=BIOCATALYST_PUBLIC_ROOT=/var/lib/macro-biocatalyst/public" in service
    assert "ReadOnlyPaths=-/var/lib/macro-biocatalyst/public" in service
    assert "InaccessiblePaths=-/var/lib/macro-biocatalyst/state" in service
    assert "InaccessiblePaths=-/var/lib/macro-biocatalyst/activation" in service
    assert "InaccessiblePaths=-/etc/macro-biocatalyst.env" in service
    assert "InaccessiblePaths=-/etc/macro-biocatalyst-control.env" in service
    assert "BIOCATALYST_R2_" not in service
    assert "ReadWritePaths=/var/lib/macro-biocatalyst" not in service


def test_macro_api_declares_projection_validation_dependencies():
    requirements = _text(API_REQUIREMENTS_PATH)

    assert re.search(r"^jsonschema==4\.26\.0$", requirements, re.MULTILINE)
    assert re.search(r"^referencing>=0\.30,<1\.0$", requirements, re.MULTILINE)


def test_biocatalyst_router_mount_is_not_silently_optional():
    main_source = _text(ROOT / "app" / "main.py")
    route_source = _text(ROOT / "app" / "biocatalyst.py")

    mount = "from app.biocatalyst import router as biocatalyst_router"
    assert main_source.count(mount) == 1
    assert 'log.warning("BioCatalyst router not mounted:' not in main_source
    assert "if _PUBLIC_ROOT.exists():" in route_source
    assert "_verify_serving_runtime()" in route_source
    assert "def _publication_runtime()" in route_source
    assert "from engine.biocatalyst.publication import" not in route_source.split(
        "router = APIRouter()", 1
    )[0]


def test_unprovisioned_app_import_defers_biocatalyst_contract_runtime(tmp_path: Path):
    probe = """
import builtins

real_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.', 1)[0] in {'jsonschema', 'referencing'}:
        raise ModuleNotFoundError(name)
    return real_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import app.main
"""
    environment = os.environ.copy()
    environment["BIOCATALYST_PUBLIC_ROOT"] = str(tmp_path / "not-provisioned")
    unprovisioned = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert unprovisioned.returncode == 0, unprovisioned.stderr

    provisioned_root = tmp_path / "provisioned"
    provisioned_root.mkdir()
    environment["BIOCATALYST_PUBLIC_ROOT"] = str(provisioned_root)
    provisioned = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert provisioned.returncode != 0
    assert "jsonschema" in provisioned.stderr


def test_timer_is_hourly_jittered_and_operator_armable():
    timer = _text(TIMER_PATH)

    assert "OnCalendar=hourly" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=false" in timer
    assert "Unit=macro-biocatalyst.service" in timer
    assert "WantedBy=timers.target" in timer
    assert "operator-armed" in timer


def test_root_heartbeat_is_read_only_hardened_and_disabled_by_default():
    service = _text(HEARTBEAT_SERVICE_PATH)
    timer = _text(HEARTBEAT_TIMER_PATH)
    runner = _text(HEARTBEAT_RUNNER_PATH)

    assert "Type=oneshot" in service
    assert "User=root" in service
    assert "Group=macro-biocatalyst" in service
    assert "ConditionPathExists=/etc/macro-biocatalyst.env" in service
    assert "ConditionPathExists=/etc/macro-biocatalyst-control.env" in service
    assert "ConditionPathExists=/var/lib/macro-biocatalyst/activation/gate.json" in service
    assert "EnvironmentFile=/etc/macro-biocatalyst.env" in service
    assert "EnvironmentFile=/etc/macro-biocatalyst-control.env" in service
    assert "ExecStart=/usr/bin/env bash /opt/macro/app/deploy/biocatalyst-activation-heartbeat.sh" in service
    assert "ReadWritePaths=/var/lib/macro-biocatalyst/activation" in service
    assert "InaccessiblePaths=/var/lib/macro-biocatalyst/state" in service
    assert "InaccessiblePaths=/var/lib/macro-biocatalyst/public" in service
    for setting in (
        "UMask=0077",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
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
        assert setting in service
    assert re.search(r"^CapabilityBoundingSet=$", service, re.MULTILINE)
    assert re.search(r"^AmbientCapabilities=$", service, re.MULTILINE)

    assert "OnCalendar=hourly" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=false" in timer
    assert "Unit=macro-biocatalyst-activation-heartbeat.service" in timer
    assert "WantedBy=timers.target" in timer
    assert "operator-armed" in timer

    assert '-m scripts.biocatalyst_activation --mode heartbeat' in runner
    assert '--gate-file "$ACTIVATION_GATE"' in runner
    assert 'mktemp "$ACTIVATION_ROOT/.heartbeat.XXXXXX"' in runner
    assert 'mv -f -- "$temporary_heartbeat" "$HEARTBEAT_FILE"' in runner
    assert 'stat -c \'%g\' "$temporary_heartbeat"' in runner
    assert 'chmod 0440 "$temporary_heartbeat"' in runner
    assert "BIOCATALYST_R2_CONTROL_API_TOKEN" not in runner
    assert "curl" not in runner


def test_setup_keeps_environment_root_only_and_requires_explicit_prereq_check():
    setup = _text(SETUP_PATH)

    assert '[ "$(id -u)" -eq 0 ] || die "must run as root"' in setup
    assert 'getent group "$SERVICE_GROUP"' in setup
    assert 'groupadd --system "$SERVICE_GROUP"' in setup
    assert 'id -u "$SERVICE_USER"' in setup
    assert 'useradd --system --gid "$SERVICE_GROUP"' in setup
    assert '--no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"' in setup
    assert 'getent passwd "$SERVICE_USER"' in setup
    assert '[ "$account_home" = "$STATE_ROOT" ]' in setup
    assert '*/nologin|*/false' in setup
    assert 'python3 "$SECURE_PATH_HELPER" provision-state' in setup
    assert '--state-root "$STATE_ROOT"' in setup
    assert '--env-file "$ENV_FILE"' in setup
    assert '--control-env-file "$CONTROL_ENV_FILE"' in setup
    assert '--activation-root "$ACTIVATION_ROOT"' in setup
    assert '--activation-gate "$ACTIVATION_GATE"' in setup
    assert '--activation-heartbeat "$ACTIVATION_HEARTBEAT"' in setup
    assert '--service-uid "$SERVICE_UID"' in setup
    assert '--service-gid "$SERVICE_GID"' in setup
    assert '--root-uid "$ROOT_UID"' in setup
    assert '--root-gid "$ROOT_GID"' in setup
    assert '--env-uid "$ROOT_UID"' in setup
    assert '--env-gid "$ROOT_GID"' in setup
    assert 'install -d -o "$SERVICE_USER"' not in setup
    assert 'chmod 0600 "$ENV_FILE"' not in setup
    assert 'chown root:root "$ENV_FILE"' not in setup
    assert "--verify-prereqs" in setup
    assert "systemd-analyze verify" in setup
    assert "systemctl daemon-reload" in setup
    assert "units installed, but intentionally left disabled" in setup
    assert 'BIOCATALYST_CURRENT="$RUNTIME_ROOT/current"' in setup
    assert "biocatalyst-requirements.txt" in setup
    assert 'bash "$RUNTIME_INSTALLER" --install "$REQUIREMENTS_SOURCE"' in setup
    assert 'bash "$RUNTIME_INSTALLER" --verify' in setup
    assert "install_runtime" in setup
    assert "verify_runtime" in setup
    assert setup.index("install_runtime\n\tverify_units") < setup.index("systemctl daemon-reload")

    for key in (
        "BIOCATALYST_ENABLED",
        "BIOCATALYST_HISTORY_ENABLED=0",
        "BIOCATALYST_PROSPECTIVE_ENABLED=0",
        "BIOCATALYST_R2_ACTIVATION_ID",
        "BIOCATALYST_R2_ACCOUNT_ID",
        "BIOCATALYST_R2_JURISDICTION=default",
        "BIOCATALYST_R2_RETENTION_CONFIRMED=0",
        "BIOCATALYST_CANARY_NCTS",
        "BIOCATALYST_USER_AGENT",
        "BIOCATALYST_R2_ENDPOINT",
        "BIOCATALYST_R2_BUCKET",
        "BIOCATALYST_R2_ACCESS_KEY_ID",
        "BIOCATALYST_R2_SECRET_ACCESS_KEY",
    ):
        assert key in setup

    assert "deprecated evidence only; never authorizes collection" in setup
    assert "BIOCATALYST_PROSPECTIVE_ENABLED must equal 0 or 1" in setup
    assert "BIOCATALYST_R2_RETENTION_CONFIRMED must equal 0 or 1" in setup
    assert "BIOCATALYST_R2_ACTIVATION_ID must match activation gate" in setup
    assert "BIOCATALYST_R2_ACCOUNT_ID must match the root-only control account" in setup
    assert "BIOCATALYST_R2_JURISDICTION must be default, eu, or fedramp" in setup
    assert "BIOCATALYST_R2_CONTROL_API_TOKEN" in setup
    assert "BIOCATALYST_R2_CONTROL_ACCOUNT_ID" in setup
    assert "BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS=86400" in setup
    assert "BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS=7200" in setup
    assert "BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS must equal 86400" in setup
    assert "BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS must equal 7200" in setup
    assert "validate_activation_artifacts" in setup
    assert '"--mode",\n        "validate"' in setup
    assert '"--heartbeat-file"' in setup
    assert "verify-activation" in setup
    assert 'install -m 0644 "$HEARTBEAT_SERVICE_SOURCE" "$HEARTBEAT_SERVICE_DEST"' in setup
    assert 'install -m 0644 "$HEARTBEAT_TIMER_SOURCE" "$HEARTBEAT_TIMER_DEST"' in setup

    executable_lines = [
        line.strip() for line in setup.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any(line.startswith("systemctl enable") for line in executable_lines)
    assert not any(line.startswith("systemctl start") for line in executable_lines)


def test_runtime_is_built_verified_and_atomically_swapped_without_mutating_current():
    runtime = _text(RUNTIME_PATH)

    build = 'staging_runtime="$(mktemp -d "$RUNTIMES_ROOT/.build-${requirements_hash}.XXXXXX")"'
    create = 'python3 -m venv --copies "$staging_runtime"'
    install = '"$staging_runtime/bin/pip" install --disable-pip-version-check -r "$requirements_source"'
    verify = 'verify_runtime_path "$staging_runtime"'
    freeze = 'mv -T "$staging_runtime" "$final_runtime"'
    prepare_pointer = 'ln -s "$final_runtime" "$next_link"'
    commit_pointer = 'mv -Tf "$next_link" "$CURRENT_LINK"'

    for operation in (build, create, install, verify, freeze, prepare_pointer, commit_pointer):
        assert operation in runtime
    assert runtime.index(build) < runtime.index(create) < runtime.index(install)
    assert runtime.index(install) < runtime.index(verify) < runtime.index(freeze)
    assert runtime.index(freeze) < runtime.index(prepare_pointer) < runtime.index(commit_pointer)

    assert 'printf \'%s\\n\' "$requirements_hash" >"$staging_runtime/.requirements.sha256"' in runtime
    assert 'chown -hR root:"$SERVICE_GROUP" "$staging_runtime"' in runtime
    assert 'chmod -R g+rX,o-rwx "$staging_runtime"' in runtime
    assert 'rm -rf -- "$staging_runtime"' in runtime
    assert 'rm -f -- "$CURRENT_LINK"' not in runtime
    assert 'ln -sfn' not in runtime
    assert '"$CURRENT_LINK/bin/pip"' not in runtime
    assert 'exec 9>"$RUNTIME_LOCK"' in runtime
    assert "flock -x 9" in runtime
    assert 'python3 "$SECURE_PATH_HELPER" provision-runtime' in runtime
    assert 'python3 "$SECURE_PATH_HELPER" "${verify_args[@]}"' in runtime
    assert runtime.index('chown -hR root:"$SERVICE_GROUP" "$staging_runtime"') < runtime.index(verify)
    assert 'if [ -L "$CURRENT_LINK" ] && runtime_path="$(resolve_runtime)"; then' in runtime


def _provision_state(tmp_path: Path, state_root: Path, env_file: Path) -> subprocess.CompletedProcess[str]:
    current_uid = os.getuid()
    current_gid = os.getgid()
    return subprocess.run(
        [
            sys.executable,
            str(SECURE_PATHS_PATH),
            "provision-state",
            "--state-root",
            str(state_root),
            "--env-file",
            str(env_file),
            "--control-env-file",
            str(tmp_path / "macro-biocatalyst-control.env"),
            "--activation-root",
            str(state_root / "activation"),
            "--activation-gate",
            str(state_root / "activation" / "gate.json"),
            "--activation-heartbeat",
            str(state_root / "activation" / "heartbeat.json"),
            "--service-uid",
            str(current_uid),
            "--service-gid",
            str(current_gid),
            "--root-uid",
            str(current_uid),
            "--root-gid",
            str(current_gid),
            "--env-uid",
            str(current_uid),
            "--env-gid",
            str(current_gid),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def _mode_owner(path: Path) -> tuple[int, int, int]:
    metadata = path.stat()
    return stat.S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid


def test_secure_provisioner_creates_exact_no_follow_layout(tmp_path: Path):
    state_root = tmp_path / "macro-biocatalyst"
    env_file = tmp_path / "macro-biocatalyst.env"

    result = _provision_state(tmp_path, state_root, env_file)
    assert result.returncode == 0, result.stderr

    current_uid = os.getuid()
    current_gid = os.getgid()
    assert _mode_owner(state_root) == (0o750, current_uid, current_gid)
    for managed in (
        state_root / "state",
        state_root / "public",
        state_root / "state" / "staging",
        state_root / "state" / "committed",
        state_root / "state" / "dead-letter",
    ):
        assert _mode_owner(managed) == (0o700, current_uid, current_gid)
        assert not managed.is_symlink()
    assert _mode_owner(env_file) == (0o600, current_uid, current_gid)
    assert env_file.is_file() and not env_file.is_symlink()
    control_env = tmp_path / "macro-biocatalyst-control.env"
    assert _mode_owner(control_env) == (0o600, current_uid, current_gid)
    assert control_env.is_file() and not control_env.is_symlink()
    activation_root = state_root / "activation"
    assert _mode_owner(activation_root) == (0o750, current_uid, current_gid)
    assert activation_root.is_dir() and not activation_root.is_symlink()
    for artifact in (activation_root / "gate.json", activation_root / "heartbeat.json"):
        assert _mode_owner(artifact) == (0o440, current_uid, current_gid)
        assert artifact.is_file() and not artifact.is_symlink()


_MANAGED_ANCHORS = (
    "root",
    "state",
    "public",
    "staging",
    "committed",
    "dead-letter",
    "env",
    "control_env",
    "activation",
    "gate",
    "heartbeat",
)


@pytest.mark.parametrize("anchor", _MANAGED_ANCHORS)
@pytest.mark.parametrize("hostile_kind", ("symlink", "nonregular"))
def test_secure_provisioner_rejects_hostile_anchor_without_touching_target(
    tmp_path: Path,
    anchor: str,
    hostile_kind: str,
):
    state_root = tmp_path / "macro-biocatalyst"
    env_file = tmp_path / "macro-biocatalyst.env"
    anchor_paths = {
        "root": state_root,
        "state": state_root / "state",
        "public": state_root / "public",
        "staging": state_root / "state" / "staging",
        "committed": state_root / "state" / "committed",
        "dead-letter": state_root / "state" / "dead-letter",
        "env": env_file,
        "control_env": tmp_path / "macro-biocatalyst-control.env",
        "activation": state_root / "activation",
        "gate": state_root / "activation" / "gate.json",
        "heartbeat": state_root / "activation" / "heartbeat.json",
    }
    blocker = anchor_paths[anchor]
    blocker.parent.mkdir(parents=True, exist_ok=True)

    if hostile_kind == "symlink":
        if anchor in {"env", "control_env", "gate", "heartbeat"}:
            protected = tmp_path / "protected-secret"
            protected.write_text("do-not-touch", encoding="utf-8")
            protected.chmod(0o640)
            blocker.symlink_to(protected)
            sentinel = protected
        else:
            protected = tmp_path / "protected-directory"
            protected.mkdir(mode=0o751)
            sentinel = protected / "sentinel.txt"
            sentinel.write_text("do-not-touch", encoding="utf-8")
            blocker.symlink_to(protected, target_is_directory=True)
    elif anchor in {"env", "control_env", "gate", "heartbeat"}:
        blocker.mkdir(mode=0o751)
        sentinel = blocker / "sentinel.txt"
        sentinel.write_text("do-not-touch", encoding="utf-8")
        protected = blocker
    else:
        blocker.write_text("do-not-touch", encoding="utf-8")
        blocker.chmod(0o640)
        protected = blocker
        sentinel = blocker

    before = _mode_owner(protected)
    before_content = sentinel.read_text(encoding="utf-8")
    result = _provision_state(tmp_path, state_root, env_file)

    assert result.returncode != 0
    assert _mode_owner(protected) == before
    assert sentinel.read_text(encoding="utf-8") == before_content


@pytest.mark.parametrize("anchor", ("env", "control_env", "gate", "heartbeat"))
def test_secure_provisioner_rejects_hard_linked_control_files(tmp_path: Path, anchor: str):
    state_root = tmp_path / "macro-biocatalyst"
    env_file = tmp_path / "macro-biocatalyst.env"
    control_env = tmp_path / "macro-biocatalyst-control.env"
    activation_root = state_root / "activation"
    anchor_paths = {
        "env": env_file,
        "control_env": control_env,
        "gate": activation_root / "gate.json",
        "heartbeat": activation_root / "heartbeat.json",
    }
    target = anchor_paths[anchor]
    target.parent.mkdir(parents=True, exist_ok=True)
    protected = tmp_path / "protected-secret"
    protected.write_text("do-not-touch", encoding="utf-8")
    protected.chmod(0o640)
    os.link(protected, target)
    before = _mode_owner(protected)

    result = _provision_state(tmp_path, state_root, env_file)

    assert result.returncode != 0
    assert _mode_owner(protected) == before
    assert protected.read_text(encoding="utf-8") == "do-not-touch"


def _verify_activation(tmp_path: Path, state_root: Path) -> subprocess.CompletedProcess[str]:
    current_uid = os.getuid()
    current_gid = os.getgid()
    return subprocess.run(
        [
            sys.executable,
            str(SECURE_PATHS_PATH),
            "verify-activation",
            "--state-root",
            str(state_root),
            "--activation-root",
            str(state_root / "activation"),
            "--activation-gate",
            str(state_root / "activation" / "gate.json"),
            "--activation-heartbeat",
            str(state_root / "activation" / "heartbeat.json"),
            "--control-env-file",
            str(tmp_path / "macro-biocatalyst-control.env"),
            "--root-uid",
            str(current_uid),
            "--root-gid",
            str(current_gid),
            "--service-gid",
            str(current_gid),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_activation_verifier_rejects_nonimmutable_gate_and_heartbeat(tmp_path: Path):
    state_root = tmp_path / "macro-biocatalyst"
    result = _provision_state(tmp_path, state_root, tmp_path / "macro-biocatalyst.env")
    assert result.returncode == 0, result.stderr
    assert _verify_activation(tmp_path, state_root).returncode == 0

    gate = state_root / "activation" / "gate.json"
    gate.chmod(0o640)
    assert _verify_activation(tmp_path, state_root).returncode != 0
    gate.chmod(0o440)

    heartbeat = state_root / "activation" / "heartbeat.json"
    protected = tmp_path / "protected-heartbeat"
    heartbeat.rename(protected)
    heartbeat.symlink_to(protected)
    assert _verify_activation(tmp_path, state_root).returncode != 0


def _fake_runtime(tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime_root = tmp_path / "runtime-root"
    runtimes_root = runtime_root / "runtimes"
    runtime_path = runtimes_root / "runtime-v1"
    bin_dir = runtime_path / "bin"
    bin_dir.mkdir(parents=True)
    python_path = bin_dir / "python"
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stamp = runtime_path / ".requirements.sha256"
    stamp.write_text("0" * 64 + "\n", encoding="utf-8")
    for directory in (runtime_root, runtimes_root, runtime_path, bin_dir):
        directory.chmod(0o750)
    python_path.chmod(0o750)
    stamp.chmod(0o640)
    current_link = runtime_root / "current"
    current_link.symlink_to(runtime_path)
    return runtime_root, runtime_path, current_link


def _verify_fake_runtime(
    tmp_path: Path,
    runtime_root: Path,
    runtime_path: Path,
    current_link: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SECURE_PATHS_PATH),
            "verify-runtime",
            "--runtime-root",
            str(runtime_root),
            "--runtime-path",
            str(runtime_path),
            "--current-link",
            str(current_link),
            "--owner-uid",
            str(os.getuid()),
            "--service-gid",
            str(os.getgid()),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_runtime_trust_verifier_rejects_writable_or_symlinked_targets(tmp_path: Path):
    runtime_root, runtime_path, current_link = _fake_runtime(tmp_path)
    valid = _verify_fake_runtime(tmp_path, runtime_root, runtime_path, current_link)
    assert valid.returncode == 0, valid.stderr

    runtime_root.chmod(0o770)
    unsafe_ancestor = _verify_fake_runtime(tmp_path, runtime_root, runtime_path, current_link)
    assert unsafe_ancestor.returncode != 0
    assert stat.S_IMODE(runtime_root.stat().st_mode) == 0o770
    runtime_root.chmod(0o750)

    python_path = runtime_path / "bin" / "python"
    python_path.chmod(0o770)
    unsafe_mode = _verify_fake_runtime(tmp_path, runtime_root, runtime_path, current_link)
    assert unsafe_mode.returncode != 0
    assert stat.S_IMODE(python_path.stat().st_mode) == 0o770

    python_path.chmod(0o750)
    protected_runtime = tmp_path / "protected-runtime"
    runtime_path.rename(protected_runtime)
    runtime_path.symlink_to(protected_runtime, target_is_directory=True)
    before = _mode_owner(protected_runtime)
    hostile_link = _verify_fake_runtime(tmp_path, runtime_root, runtime_path, current_link)
    assert hostile_link.returncode != 0
    assert _mode_owner(protected_runtime) == before


def test_requirements_pin_the_dedicated_r2_sdk_floor():
    requirements = _text(REQUIREMENTS_PATH)

    assert "boto3>=1.37.32,<2.0" in requirements
    assert "requests>=2.31,<3.0" in requirements
    assert "PyYAML>=6.0,<7.0" in requirements


def test_update_reconciles_only_a_fully_operator_installed_lane_without_arming_it():
    block = _biocatalyst_update_block()

    assert "[ -f /etc/systemd/system/macro-biocatalyst.service ]" in block
    assert "[ -f /etc/systemd/system/macro-biocatalyst.timer ]" in block
    assert 'cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.service"' in block
    assert 'cmp -s "$APP_DIR/app/deploy/macro-biocatalyst.timer"' in block
    assert 'cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.service"' in block
    assert 'cmp -s "$APP_DIR/app/deploy/macro-biocatalyst-activation-heartbeat.timer"' in block
    assert "systemd-analyze verify" in block
    assert "systemctl daemon-reload" in block
    assert "BIOCATALYST_TIMER_WAS_ENABLED=0" in block
    assert "BIOCATALYST_HEARTBEAT_TIMER_WAS_ENABLED=0" in block
    assert "[ -f /etc/systemd/system/macro-biocatalyst.timer ]" in block
    assert "[ -f /etc/systemd/system/macro-biocatalyst-activation-heartbeat.timer ]" in block
    assert "systemctl is-enabled --quiet macro-biocatalyst.timer" in block
    assert "systemctl restart macro-biocatalyst.timer" in block
    assert "systemctl is-enabled --quiet macro-biocatalyst-activation-heartbeat.timer" in block
    assert "systemctl restart macro-biocatalyst-activation-heartbeat.timer" in block
    assert "BIOCATALYST_UNIT_UPDATED=1" in block
    assert "BIOCATALYST_RUNTIME_UPDATED=0" in block
    assert "BIOCATALYST_RUNTIME_READY=0" in block
    assert 'bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --verify' in block
    assert 'bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --install' in block
    assert '[ "$BIOCATALYST_RUNTIME_READY" -ne 1 ]' in block
    assert block.index('bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --verify') < block.index(
        'BIOCATALYST_INSTALLED_HASH="$(awk'
    )
    assert block.index('bash "$APP_DIR/app/deploy/biocatalyst-runtime.sh" --install') < block.index("BIOCATALYST_UNIT_UPDATED=0")
    assert "/opt/macro-biocatalyst/current/bin/pip" not in block
    assert "/opt/macro-biocatalyst/.venv/bin/pip" not in block
    assert "biocatalyst-requirements.txt" in block
    assert "previous runtime remains selected" in block

    executable_lines = [
        line.strip() for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not any(line.startswith("systemctl enable") for line in executable_lines)
    assert not any(line.startswith("systemctl start") for line in executable_lines)
