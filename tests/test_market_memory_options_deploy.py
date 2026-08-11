"""Deployment, privacy, credential, and CI guards for the W1B.5 canary."""

from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-options.service"
TIMER = DEPLOY / "macro-market-memory-options.timer"
PREREQS = DEPLOY / "market-memory-options-prereqs.sh"
UNIT_BOUNDARY = DEPLOY / "market-memory-options-unit-boundary.sh"
RUNTIME_FENCE = DEPLOY / "market-memory-options-runtime-fence.sh"
DROPIN_MIGRATION = DEPLOY / "market-memory-options-dropin-migration.sh"
API_SERVICE = DEPLOY / "macro-api.service"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"
WRITER = ROOT / "scripts" / "capture_market_memory_option_oi.py"
LEGACY_JOBS = ROOT / ".github" / "ci" / "legacy-jobs.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

STATE_ROOT = "/var/lib/macro-market-memory-options"
STORE_ROOT = f"{STATE_ROOT}/options-v1"
SERVICE_USER = "macro-market-memory-options"
SERVICE_GROUP = "macro-market-memory-options"
OPTION_MODULES = {
    "engine.neuralweb.market_memory_option_oi_observation",
    "engine.neuralweb.market_memory_option_oi_store",
}
OPTION_CLOSURE_PATHS = (
    "scripts/__init__.py",
    "engine/__init__.py",
    "engine/neuralweb/__init__.py",
    "config/market_memory_option_oi_source.v1.json",
    "engine/neuralweb/market_memory_option_oi_observation.py",
    "engine/neuralweb/market_memory_option_oi_store.py",
    "engine/neuralweb/market_memory_pit.py",
    "engine/neuralweb/market_memory.py",
    "contracts/market_memory/option_oi_probe_receipt.v1.schema.json",
    "contracts/market_memory/spy_option_oi_source_observation.v1.schema.json",
    "contracts/market_memory/option_oi_capture_receipt.v1.schema.json",
    "contracts/market_memory/option_oi_store.v1.schema.json",
    "scripts/capture_market_memory_option_oi.py",
    "app/requirements.txt",
    "app/deploy/api-setup.sh",
    "app/deploy/update.sh",
    "app/deploy/macro-api.service",
    "app/deploy/market-memory-options-prereqs.sh",
    "app/deploy/market-memory-options-unit-boundary.sh",
    "app/deploy/market-memory-options-runtime-fence.sh",
    "app/deploy/market-memory-options-dropin-migration.sh",
    "app/deploy/codex-runtime-setup.sh",
    "app/deploy/macro-market-memory-options.service",
    "app/deploy/macro-market-memory-options.timer",
    "app/deploy/macro-market-memory-source.service",
    "app/deploy/macro-market-memory-source.timer",
    "app/deploy/macro-market-memory-context.service",
    "app/deploy/macro-market-memory-context.timer",
    "app/deploy/macro-market-memory-identity.service",
    "app/deploy/macro-market-memory-identity.timer",
    "app/deploy/macro-market-memory-breadth.service",
    "app/deploy/macro-market-memory-breadth.timer",
    "app/deploy/macro-market-memory-technicals.service",
    "app/deploy/macro-market-memory-technicals.timer",
    "app/deploy/macro-market-memory-experience.service",
    "app/deploy/macro-market-memory-experience.timer",
    "app/deploy/README.md",
    "docs/ops/market-memory-option-oi-canary.md",
    "tests/test_market_memory_option_oi_observation.py",
    "tests/test_market_memory_option_oi_store.py",
    "tests/test_capture_market_memory_option_oi.py",
    "tests/test_market_memory_options_deploy.py",
    "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
    "research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _setting_values(unit: str, setting: str) -> list[str]:
    prefix = f"{setting}="
    return [
        line.removeprefix(prefix)
        for line in unit.splitlines()
        if line.startswith(prefix)
    ]


def _legacy_job_body(legacy_jobs: str, job_id: str) -> str:
    job = re.search(
        rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z0-9][a-z0-9-]*:|\Z)",
        legacy_jobs,
        re.MULTILINE | re.DOTALL,
    )
    assert job is not None, f"missing legacy CI job: {job_id}"
    return job.group("body")


def _app_route_paths() -> set[str]:
    paths: set[str] = set()
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(_text(path), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if decorator.func.attr not in {"get", "post", "put", "patch", "delete"}:
                    continue
                route = decorator.args[0]
                if isinstance(route, ast.Constant) and isinstance(route.value, str):
                    paths.add(route.value)
    return paths


def test_option_canary_deploy_shells_have_valid_syntax() -> None:
    for script in (
        PREREQS,
        UNIT_BOUNDARY,
        RUNTIME_FENCE,
        DROPIN_MIGRATION,
        SETUP,
        UPDATE,
        DEPLOY / "codex-runtime-setup.sh",
    ):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_option_service_uses_static_identity_and_only_a_systemd_credential() -> None:
    service = _text(SERVICE)

    assert "Type=oneshot" in service
    assert f"User={SERVICE_USER}" in service
    assert f"Group={SERVICE_GROUP}" in service
    assert "WorkingDirectory=/opt/macro" in service
    assert (
        "LoadCredential=massive-option-oi-api-key:"
        "/etc/macro-market-memory-options/massive-option-oi-api-key"
    ) in service
    assert (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.capture_market_memory_option_oi --repository-root /opt/macro "
        f"--store-root {STORE_ROOT}"
    ) in service
    assert (
        "ExecCondition=/usr/bin/bash /opt/macro/app/deploy/"
        "market-memory-options-runtime-fence.sh --check"
    ) in service
    assert _setting_values(service, "ReadOnlyPaths") == ["/opt/macro"]
    assert _setting_values(service, "ReadWritePaths") == [STORE_ROOT]
    assert "InaccessiblePaths=/var/lib/macro-market-memory\n" in service
    assert "Environment=" not in service
    assert "EnvironmentFile=" not in service
    assert "--api-key" not in service
    assert "apiKey=" not in service
    assert _setting_values(service, "RestrictAddressFamilies") == [
        "AF_UNIX AF_INET AF_INET6"
    ]

    for setting in (
        "UMask=0077",
        "LimitCORE=0",
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
    ):
        assert setting in service
    assert re.search(r"^CapabilityBoundingSet=$", service, re.MULTILINE)
    assert re.search(r"^AmbientCapabilities=$", service, re.MULTILINE)
    reciprocal_services = {
        "macro-market-memory-source.service",
        "macro-market-memory-context.service",
        "macro-market-memory-identity.service",
        "macro-market-memory-breadth.service",
        "macro-market-memory-technicals.service",
        "macro-market-memory-experience.service",
    }
    assert set(_setting_values(service, "Conflicts")[0].split()) == reciprocal_services
    assert reciprocal_services <= set(_setting_values(service, "After")[0].split())
    runtime_fence = _text(RUNTIME_FENCE)
    assert "mm_unit_inactive_without_process" in runtime_fence
    assert "MainPID" in runtime_fence and "ControlPID" in runtime_fence


def test_networked_option_writer_masks_every_other_known_secret_path() -> None:
    service = _text(SERVICE)
    known_secret_paths: set[str] = set()
    for path in DEPLOY.rglob("*"):
        if not path.is_file() or path == SERVICE:
            continue
        known_secret_paths.update(
            re.findall(r"/etc/[A-Za-z0-9_./-]+(?:\.env|\.key)", _text(path))
        )
    assert known_secret_paths
    for protected in sorted(known_secret_paths):
        assert re.search(
            rf"^InaccessiblePaths=-?{re.escape(protected)}$",
            service,
            re.MULTILINE,
        ), f"credentialed writer can read unrelated secret path: {protected}"
    assert "InaccessiblePaths=/etc/macro-market-memory-options" in service


def test_option_timer_is_cadence_only_and_cannot_backfill_missed_runs() -> None:
    timer = _text(TIMER)
    service = _text(SERVICE)
    assert "OnBootSec=" not in timer
    assert "OnCalendar=Mon..Fri *-*-* 08:20:00 America/New_York" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=false" in timer
    assert "market session" in timer
    assert "measurement date" in timer
    marker = "ConditionPathExists=/run/macro-api-market-memory-options-deny.ready"
    assert marker in timer
    assert marker in service
    reciprocal_marker = (
        "ConditionPathExists=/run/macro-market-memory-options-reciprocal-deny.ready"
    )
    assert reciprocal_marker in timer
    assert reciprocal_marker in service


def test_runtime_fence_binds_exact_api_process_and_reciprocal_receipt(
    tmp_path: Path,
) -> None:
    api_marker = tmp_path / "api.ready"
    reciprocal_marker = tmp_path / "reciprocal.ready"
    script = tmp_path / "runtime-fence-harness.sh"
    script.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
APP_DIR={shlex.quote(str(ROOT))}
source {shlex.quote(str(RUNTIME_FENCE))}
OPTIONS_API_FENCE_MARKER={shlex.quote(str(api_marker))}
OPTIONS_RECIPROCAL_FENCE_MARKER={shlex.quote(str(reciprocal_marker))}
CURRENT_PID=41
CURRENT_INVOCATION=0123456789abcdef0123456789abcdef
systemctl() {{
  [ "$1" = show ]
  case "$3" in
    MainPID) printf '%s\\n' "$CURRENT_PID" ;;
    InvocationID) printf '%s\\n' "$CURRENT_INVOCATION" ;;
    *) return 1 ;;
  esac
}}
stat() {{ printf '%s\\n' root:root:644; }}
chown() {{ return 0; }}
chmod() {{ command chmod "$@"; }}
mktemp() {{ command mktemp {shlex.quote(str(tmp_path / "fence.XXXXXX"))}; }}
mm_write_api_fence_marker
mm_write_reciprocal_fence_marker
mm_api_fence_marker_ready
mm_reciprocal_fence_marker_ready
CURRENT_PID=42
! mm_api_fence_marker_ready
CURRENT_PID=41
CURRENT_INVOCATION=fedcba9876543210fedcba9876543210
! mm_api_fence_marker_ready
""",
        encoding="utf-8",
    )

    subprocess.run(["bash", str(script)], check=True)
    assert api_marker.read_text(encoding="utf-8") == (
        "41 0123456789abcdef0123456789abcdef\n"
    )
    assert reciprocal_marker.read_text(encoding="utf-8") == (
        "market-memory-options-reciprocal-deny.v1\n"
    )


def test_prereqs_create_disjoint_dac_root_without_exporting_or_logging_key() -> None:
    prereqs = _text(PREREQS)
    assert f"SERVICE_USER={SERVICE_USER}" in prereqs
    assert f"SERVICE_GROUP={SERVICE_GROUP}" in prereqs
    assert f"STATE_ROOT={STATE_ROOT}" in prereqs
    assert "useradd --system" in prereqs
    assert "--no-create-home --shell /usr/sbin/nologin" in prereqs
    assert 'account_uid=$(id -u "$SERVICE_USER")' in prereqs
    assert 'account_gid=$(id -g "$SERVICE_USER")' in prereqs
    assert '[ "$account_uid" -ne 0 ]' in prereqs
    assert '[ "$account_gid" -ne 0 ]' in prereqs
    assert 'all_groups=$(id -G "$SERVICE_USER")' in prereqs
    assert '[ "$all_groups" = "$account_gid" ]' in prereqs
    assert 'install -d -o root -g "$SERVICE_GROUP" -m 0710 "$STATE_ROOT"' in prereqs
    assert (
        'install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0700 "$STORE_ROOT"'
        in prereqs
    )
    assert '[ ! -L "$STATE_ROOT" ]' in prereqs
    assert '[ ! -L "$STORE_ROOT" ]' in prereqs
    assert "state parent must be root-owned mode 0710" in prereqs
    assert "options-v1 root must be service-owned mode 0700" in prereqs
    assert "CREDENTIAL_FILE=$CREDENTIAL_ROOT/massive-option-oi-api-key" in prereqs
    assert "ensure_deny_anchors()" in prereqs
    assert "validate_service_identity()" in prereqs
    assert "validate_deny_anchors()" in prereqs
    assert "--check-identity-only" in prereqs
    assert "--check-ready" in prereqs
    assert "check_full_ready()" in prereqs
    assert 'install -d -o root -g root -m 0700 "$STATE_ROOT"' in prereqs
    assert 'install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT"' in prereqs
    identity_branch = prereqs.index("if [ \"${1:-}\" = '--identity-only' ]")
    assert (
        prereqs.index("ensure_deny_anchors", prereqs.index("main()")) < identity_branch
    )
    assert prereqs.index("provision_state_root", identity_branch) > identity_branch
    assert '[ ! -L "$CREDENTIAL_ROOT" ]' in prereqs
    assert "credential root must be root:root mode 0700" in prereqs
    assert '[ -f "$source" ] && [ ! -L "$source" ]' in prereqs
    assert "stat -c '%U' \"$source\"" in prereqs
    assert '[ "${mode: -2}" = 00 ]' in prereqs
    assert 'chmod 0400 "$tmp"' in prereqs
    assert "MASSIVE_API_KEY" in prereqs
    assert "POLYGON_API_KEY" in prereqs
    assert not re.search(r"^\s*source\s+", prereqs, re.MULTILINE)
    assert "export " not in prereqs
    assert "eval " not in prereqs
    assert "set -x" not in prereqs
    assert "printf '%s\\n' \"$candidate\"" in prereqs
    assert "credential ready" in prereqs
    assert "credential absent" in prereqs
    missing_destination = prereqs.index('if [ ! -e "$CREDENTIAL_FILE" ]; then')
    compare = prereqs.index('cmp -s "$tmp" "$CREDENTIAL_FILE"')
    assert missing_destination < compare
    assert 'rm -f "$CREDENTIAL_FILE"' in prereqs
    assert "final credential has invalid byte shape" in prereqs
    assert "final credential contains invalid bytes" in prereqs
    for command in (
        'install -d -o root -g root -m 0700 "$CREDENTIAL_ROOT"',
        'tmp=$(mktemp "$CREDENTIAL_ROOT/.massive-option-oi-api-key.XXXXXX")',
        'chown root:root "$tmp"',
        'chmod 0400 "$tmp"',
        'mv -f "$tmp" "$CREDENTIAL_FILE"',
        'chown root:root "$CREDENTIAL_FILE"',
        'chmod 0400 "$CREDENTIAL_FILE"',
    ):
        command_at = prereqs.index(command)
        assert "||" in prereqs[command_at : command_at + len(command) + 120]
    assert "extract_status" in prereqs
    assert 'elif [ "$extract_status" -ne 2 ]' in prereqs


def test_prereq_executable_credential_state_machine(tmp_path: Path) -> None:
    state_root = tmp_path / "state-parent"
    credential_root = tmp_path / "credential-root"
    canonical = tmp_path / "operator.env"
    fallback = tmp_path / "fallback.env"
    live = tmp_path / "live.env"
    harness = tmp_path / "prereqs.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    source = _text(PREREQS)
    source = (
        source.replace(
            "STATE_ROOT=/var/lib/macro-market-memory-options",
            f"STATE_ROOT={shlex.quote(str(state_root))}",
        )
        .replace(
            "CREDENTIAL_ROOT=/etc/macro-market-memory-options",
            f"CREDENTIAL_ROOT={shlex.quote(str(credential_root))}",
        )
        .replace(
            "for source in /opt/macro/.env /etc/macro-api.env /etc/macro-live.env; do",
            f"for source in {shlex.quote(str(canonical))} "
            f"{shlex.quote(str(fallback))} {shlex.quote(str(live))}; do",
        )
    )
    harness.write_text(source, encoding="utf-8")

    fake_commands = {
        "id": f"""#!/usr/bin/env bash
case "${{1:-}}:${{2:-}}" in
  -u:) printf '%s\\n' 0 ;;
  -u:{SERVICE_USER}) printf '%s\\n' 1234 ;;
  -g:{SERVICE_USER}|-G:{SERVICE_USER}) printf '%s\\n' 1234 ;;
  *) exit 1 ;;
esac
""",
        "getent": f"""#!/usr/bin/env bash
case "$1:$2" in
  group:{SERVICE_GROUP}) printf '%s\\n' '{SERVICE_GROUP}:x:1234:' ;;
  passwd:{SERVICE_USER}) printf '%s\\n' '{SERVICE_USER}:x:1234:1234::{state_root}:/usr/sbin/nologin' ;;
  *) exit 2 ;;
esac
""",
        "install": """#!/usr/bin/env bash
[ "${FAIL_INSTALL:-0}" -eq 0 ] || exit 73
mode=755
while [ "$#" -gt 1 ]; do
  case "$1" in
    -d) shift ;;
    -m) mode=$2; shift 2 ;;
    -o|-g) shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$1"
chmod "$mode" "$1"
""",
        "chown": "#!/usr/bin/env bash\nexit 0\n",
        "groupadd": "#!/usr/bin/env bash\nexit 91\n",
        "useradd": "#!/usr/bin/env bash\nexit 92\n",
        "stat": f"""#!/usr/bin/env bash
[ "$1" = -c ] || exit 2
format=$2
path=$3
if mode=$(/usr/bin/stat -c '%a' "$path" 2>/dev/null); then
  size=$(/usr/bin/stat -c '%s' "$path") || exit 1
else
  mode=$(/usr/bin/stat -f '%Lp' "$path") || exit 1
  size=$(/usr/bin/stat -f '%z' "$path") || exit 1
fi
owner=root
group=root
case "$path" in
  {shlex.quote(str(state_root))}) [ "$mode" = 710 ] && group={SERVICE_GROUP} ;;
  {shlex.quote(str(state_root / "options-v1"))}) owner={SERVICE_USER}; group={SERVICE_GROUP} ;;
esac
case "$format" in
  %U:%G:%a) printf '%s:%s:%s\\n' "$owner" "$group" "$mode" ;;
  %U) printf '%s\\n' "$owner" ;;
  %a) printf '%s\\n' "$mode" ;;
  %s) printf '%s\\n' "$size" ;;
  *) exit 2 ;;
esac
""",
    }
    for name, body in fake_commands.items():
        command = fake_bin / name
        command.write_text(body, encoding="utf-8")
        command.chmod(0o755)

    environment = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}

    def run(*args: str, **env_overrides: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(harness), *args],
            text=True,
            capture_output=True,
            check=False,
            env={**environment, **env_overrides},
        )

    first = run("--identity-only")
    assert first.returncode == 0, first.stderr
    assert state_root.is_dir() and credential_root.is_dir()
    assert not (state_root / "options-v1").exists()
    credential = credential_root / "massive-option-oi-api-key"
    assert not credential.exists()

    canonical.write_text(
        "MASSIVE_API_KEY=first-private-token-123456\n", encoding="utf-8"
    )
    canonical.chmod(0o600)
    provisioned = run()
    assert provisioned.returncode == 0, provisioned.stderr
    assert credential.read_text(encoding="utf-8") == "first-private-token-123456\n"
    original_inode = credential.stat().st_ino
    unchanged = run()
    assert unchanged.returncode == 0, unchanged.stderr
    assert credential.stat().st_ino == original_inode

    canonical.write_text(
        "MASSIVE_API_KEY=rotated-private-token-7890\n", encoding="utf-8"
    )
    canonical.chmod(0o600)
    rotated = run()
    assert rotated.returncode == 0, rotated.stderr
    assert credential.read_text(encoding="utf-8") == "rotated-private-token-7890\n"

    orphan = credential_root / ".massive-option-oi-api-key.ABC123"
    orphan.write_text("orphan-private-token-123456\n", encoding="utf-8")
    orphan.chmod(0o600)
    assert run("--check-ready").returncode == 2
    cleaned = run()
    assert cleaned.returncode == 0, cleaned.stderr
    assert not orphan.exists()

    canonical.unlink()
    live.write_text("MASSIVE_API_KEY=live-private-token-246810\n", encoding="utf-8")
    live.chmod(0o600)
    live_source = run()
    assert live_source.returncode == 0, live_source.stderr
    assert credential.read_text(encoding="utf-8") == "live-private-token-246810\n"

    live.unlink()
    absent = run()
    assert absent.returncode == 2
    assert not credential.exists()

    canonical.write_text("MASSIVE_API_KEY=short\n", encoding="utf-8")
    canonical.chmod(0o600)
    malformed = run()
    assert malformed.returncode == 2
    assert not credential.exists()

    credential_root.rmdir()
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    credential_root.symlink_to(redirected, target_is_directory=True)
    symlinked = run("--identity-only")
    assert symlinked.returncode != 0
    credential_root.unlink()
    (state_root / "options-v1").rmdir()
    state_root.rmdir()
    failed_install = run("--identity-only", FAIL_INSTALL="1")
    assert failed_install.returncode != 0
    assert not state_root.exists()


def test_setup_provisions_before_api_and_conditionally_arms_option_lane() -> None:
    setup = _text(SETUP)
    identity_prereq = (
        'bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" --identity-only'
    )
    full_prereq = 'if bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh"; then'
    assert identity_prereq in setup
    assert full_prereq in setup
    verify = setup.index("systemd-analyze verify")
    early_disarm = setup.index(
        "systemctl disable --now macro-market-memory-options.timer"
    )
    assert setup.index("flock 9") < early_disarm
    marker_remove = setup.index('rm -f "$OPTIONS_API_FENCE_MARKER"')
    legacy_migration = setup.index(
        "if ! mm_remove_exact_legacy_api_ollama_dropin", marker_remove
    )
    api_install = setup.index(
        'install -m 0644 "$APP_DIR/app/deploy/macro-api.service" '
        "/etc/systemd/system/macro-api.service"
    )
    assert early_disarm < setup.index('log "[1/5]')
    assert marker_remove < early_disarm
    assert (
        early_disarm
        < setup.index(identity_prereq)
        < verify
        < api_install
        < legacy_migration
    )
    for name in (
        "macro-market-memory-options.service",
        "macro-market-memory-options.timer",
    ):
        assert (
            f'"$APP_DIR/app/deploy/{name}"' in setup[: setup.index("install -m 0644")]
        )
        assert (
            f'install -m 0644 "$APP_DIR/app/deploy/{name}" /etc/systemd/system/{name}'
        ) in setup
    immediate = setup.index("systemctl start macro-market-memory-options.service")
    api_restart = setup.index("systemctl restart macro-api")
    fence_marker = setup.index("mm_write_api_fence_marker")
    timer_enable = setup.index(
        "systemctl enable --now macro-market-memory-options.timer"
    )
    assert (
        api_restart < fence_marker < setup.index(full_prereq) < immediate < timer_enable
    )
    assert "POST_API_PID" in setup
    assert 'if [ "$OPTIONS_CREDENTIAL_READY" -eq 1 ]' in setup
    assert "NeedDaemonReload" in setup
    assert "systemctl is-enabled macro-market-memory-options.timer" in setup
    assert "systemctl is-active macro-market-memory-options.timer" in setup
    assert "disarm_option_lane" in setup
    assert "mm_loaded_unit_ready" in setup
    assert "reciprocal Market Memory unit is not reviewed/current" in setup


def test_predecessor_updater_bridge_creates_deny_anchors_before_api_reconcile() -> None:
    update = _text(UPDATE)
    codex = _text(DEPLOY / "codex-runtime-setup.sh")
    codex_call = 'bash "$APP_DIR/app/deploy/codex-runtime-setup.sh" --quiet'
    api_install = (
        'install -m 0644 "$APP_DIR/app/deploy/macro-api.service" '
        "/etc/systemd/system/macro-api.service"
    )
    assert update.index(codex_call) < update.index(api_install)
    bootstrap = 'bash "$DEPLOY_DIR/market-memory-options-prereqs.sh" --identity-only'
    assert bootstrap in codex
    assert "OPTIONS_BOOTSTRAP_ONLY" in codex
    assert codex.index(bootstrap) < codex.index("IFS=: read -r -a STATE_DIRS")
    assert codex.index(bootstrap) < codex.index("npm install --global")
    steady_state = codex.split('if [ "$OPTIONS_BOOTSTRAP_ONLY" -eq 1 ]; then', 1)[1]
    assert "--identity-only" not in steady_state.split("fi", 1)[0].split("else", 1)[1]


def test_updater_reconciles_disarms_and_runs_exact_option_closure() -> None:
    update = _text(UPDATE)
    identity_prereq = (
        'bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" --identity-only'
    )
    full_prereq = 'if bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh"; then'
    disarm_definition = update.index("disarm_options_timer()")
    identity_check = update.index("--check-identity-only")
    assert update.index("OPTIONS_TIMER_WAS_ENABLED=0") < disarm_definition
    assert disarm_definition < identity_check < update.index(identity_prereq)
    assert (
        update.count("systemctl disable --now macro-market-memory-options.timer") == 1
    )
    assert "trap options_fail_closed_on_exit EXIT" in update
    assert "OPTIONS_RECONCILIATION_COMPLETE=1" in update
    start = update.index("MARKET_MEMORY_OPTIONS_UNIT_UPDATED=0")
    end = update.index("# macro-api: restart ONLY", start)
    block = update[start:end]
    for token in (
        "macro-market-memory-options.service",
        "macro-market-memory-options.timer",
        "systemd-analyze verify",
        "systemctl daemon-reload",
        "MARKET_MEMORY_OPTIONS_RUN_NEEDED",
        "OPTIONS_UNITS_READY",
    ):
        assert token in block
    for forbidden in (
        "systemctl enable --now macro-market-memory-options.timer",
        "systemctl start macro-market-memory-options.service",
        "HEAD.json",
    ):
        assert forbidden not in block
    runtime_regex = re.search(r"OPTIONS_RUNTIME_CLOSURE_REGEX='([^']+)'", update)
    assert runtime_regex is not None
    runtime_trigger = re.compile(runtime_regex.group(1))
    for path in (
        "app/requirements.txt",
        "app/deploy/update.sh",
        "app/deploy/market-memory-options-runtime-fence.sh",
        "app/deploy/market-memory-options-dropin-migration.sh",
        "app/deploy/macro-market-memory-source.timer",
        "app/deploy/macro-market-memory-experience.service",
        "scripts/capture_market_memory_option_oi.py",
        "scripts/__init__.py",
        "engine/__init__.py",
        "engine/neuralweb/__init__.py",
        "engine/neuralweb/market_memory_option_oi_observation.py",
        "engine/neuralweb/market_memory_option_oi_store.py",
        "engine/neuralweb/market_memory_pit.py",
        "engine/neuralweb/market_memory.py",
        "contracts/market_memory/option_oi_probe_receipt.v1.schema.json",
        "contracts/market_memory/spy_option_oi_source_observation.v1.schema.json",
        "contracts/market_memory/option_oi_capture_receipt.v1.schema.json",
        "contracts/market_memory/option_oi_store.v1.schema.json",
        "config/market_memory_option_oi_source.v1.json",
        "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
    ):
        assert runtime_trigger.fullmatch(path), f"missing updater trigger for {path}"

    api_restart = update.index("systemctl restart macro-api", end)
    marker = update.index("mm_write_api_fence_marker", api_restart)
    immediate = update.index(
        "systemctl start macro-market-memory-options.service", marker
    )
    timer_enable = update.index(
        "systemctl enable --now macro-market-memory-options.timer", immediate
    )
    assert (
        api_restart
        < marker
        < update.index(full_prereq, marker)
        < immediate
        < timer_enable
    )
    assert "! mm_api_fence_marker_ready" in update
    assert "API_RESTART_CONFIRMED" in update
    assert "OPTIONS_BOUNDARY_READY" in update
    assert "OPTIONS_API_FENCE_READY" in update
    assert "API_UNIT_READY" in update
    assert "NeedDaemonReload" in update
    assert "RECIPROCAL_UNITS_READY" in update
    assert "mm_loaded_unit_ready" in update
    assert "DropInPaths" in _text(UNIT_BOUNDARY)
    assert "systemctl disable --now macro-market-memory-options.timer" in update
    conditional_enable = update.index(
        'if [ "$OPTIONS_TIMER_WAS_ENABLED" -eq 0 ]', immediate
    )
    assert conditional_enable < timer_enable
    assert update.count("--check-ready") == 1
    assert update.index("--check-ready") < update.index(full_prereq, marker)
    deps_drift = update.index('if [ "$API_REQ_HASH" != "$API_INSTALLED_REQ_HASH" ]')
    deps_disarm = update.index("disarm_options_timer", deps_drift)
    deps_pip = update.index("/opt/macro-api/.venv/bin/pip install", deps_drift)
    assert deps_drift < deps_disarm < deps_pip


def test_option_timer_guard_has_executable_clean_and_fail_closed_traces(
    tmp_path: Path,
) -> None:
    update = _text(UPDATE)
    stop_helpers = update.split("# BEGIN W1B5_UNIT_STOP_HELPERS\n", 1)[1].split(
        "# END W1B5_UNIT_STOP_HELPERS", 1
    )[0]
    disarm = update.split("# BEGIN W1B5_TIMER_DISARM\n", 1)[1].split(
        "# END W1B5_TIMER_DISARM", 1
    )[0]
    exit_guard = update.split("# BEGIN W1B5_TIMER_EXIT_GUARD\n", 1)[1].split(
        "# END W1B5_TIMER_EXIT_GUARD", 1
    )[0]
    guard = stop_helpers + disarm + exit_guard
    finalization = update.split("# BEGIN W1B5_TIMER_FINALIZATION\n", 1)[1].split(
        "# END W1B5_TIMER_FINALIZATION", 1
    )[0]

    def run_case(
        *,
        boundary_ready: int,
        was_enabled: int,
        was_active: int,
        fatal: bool = False,
        partial_enable: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        trace = tmp_path / (
            f"trace-{boundary_ready}-{was_enabled}-{was_active}-{int(fatal)}-"
            f"{int(partial_enable)}"
        )
        state = tmp_path / (
            f"state-{boundary_ready}-{was_enabled}-{was_active}-{int(fatal)}-"
            f"{int(partial_enable)}"
        )
        script = tmp_path / (
            f"case-{boundary_ready}-{was_enabled}-{was_active}-{int(fatal)}-"
            f"{int(partial_enable)}.sh"
        )
        body = f"""#!/usr/bin/env bash
set -euo pipefail
TRACE={shlex.quote(str(trace))}
STATE={shlex.quote(str(state))}
TIMER_ENABLED={was_enabled}
TIMER_ACTIVE={was_active}
SERVICE_ACTIVE=0
PARTIAL_ENABLE={int(partial_enable)}
systemctl() {{
  printf '%s\\n' "$*" >>"$TRACE"
  case "$1 $2" in
    "disable --now") TIMER_ENABLED=0; TIMER_ACTIVE=0; return 0 ;;
    "stop macro-market-memory-options.service") SERVICE_ACTIVE=0; return 0 ;;
    "enable --now")
      TIMER_ENABLED=1; TIMER_ACTIVE=1
      [ "$PARTIAL_ENABLE" -eq 0 ]
      return
      ;;
  esac
  case "$1" in
    is-enabled) [ "$TIMER_ENABLED" -eq 1 ]; return ;;
    is-active)
      if [ "$2" = macro-market-memory-options.service ]; then
        [ "$SERVICE_ACTIVE" -eq 1 ]
      else
        [ "$TIMER_ACTIVE" -eq 1 ]
      fi
      return
      ;;
    show)
      case "$3" in
        ActiveState)
          if [ "$5" = macro-market-memory-options.service ]; then
            [ "$SERVICE_ACTIVE" -eq 1 ] && printf '%s\n' active || printf '%s\n' inactive
          else
            [ "$TIMER_ACTIVE" -eq 1 ] && printf '%s\n' active || printf '%s\n' inactive
          fi
          ;;
        MainPID|ControlPID)
          case "$5" in
            *.timer) printf '\n' ;;
            *) printf '%s\n' 0 ;;
          esac
          ;;
        UnitFileState)
          [ "$TIMER_ENABLED" -eq 1 ] && printf '%s\n' enabled || printf '%s\n' disabled
          ;;
        LoadState) printf '%s\n' loaded ;;
      esac
      return 0
      ;;
  esac
  return 0
}}
OPTIONS_TIMER_WAS_ENABLED={was_enabled}
OPTIONS_TIMER_WAS_ACTIVE={was_active}
OPTIONS_TIMER_DISARMED=0
OPTIONS_RECONCILIATION_COMPLETE=0
OPTIONS_API_FENCE_MARKER={shlex.quote(str(tmp_path / "marker"))}
OPTIONS_RECIPROCAL_FENCE_MARKER={shlex.quote(str(tmp_path / "reciprocal-marker"))}
OPTIONS_BOUNDARY_READY={boundary_ready}
MARKET_MEMORY_OPTIONS_RUN_NEEDED=0
API_DEPS_OK=1
RECIPROCAL_TIMERS_PAUSED=0
RECIPROCAL_UNITS_READY=1
{guard}
"""
        if fatal:
            body += "false\n"
        else:
            body += finalization
            body += 'printf "%s:%s\\n" "$TIMER_ENABLED" "$TIMER_ACTIVE" >"$STATE"\n'
        script.write_text(body, encoding="utf-8")
        return subprocess.run(
            ["bash", str(script)], text=True, capture_output=True, check=False
        )

    clean = run_case(boundary_ready=1, was_enabled=1, was_active=1)
    assert clean.returncode == 0, clean.stderr
    assert not (tmp_path / "trace-1-1-1-0-0").exists()

    arm = run_case(boundary_ready=1, was_enabled=0, was_active=0)
    assert arm.returncode == 0, arm.stderr
    assert (tmp_path / "trace-1-0-0-0-0").read_text(encoding="utf-8").splitlines() == [
        "enable --now macro-market-memory-options.timer",
        "is-enabled macro-market-memory-options.timer",
        "is-active macro-market-memory-options.timer",
    ]

    boundary_failure = run_case(boundary_ready=0, was_enabled=1, was_active=1)
    assert boundary_failure.returncode == 0, boundary_failure.stderr
    assert "disable --now macro-market-memory-options.timer" in (
        tmp_path / "trace-0-1-1-0-0"
    ).read_text(encoding="utf-8")

    fatal = run_case(boundary_ready=1, was_enabled=1, was_active=1, fatal=True)
    assert fatal.returncode != 0
    assert "disable --now macro-market-memory-options.timer" in (
        tmp_path / "trace-1-1-1-1-0"
    ).read_text(encoding="utf-8")

    partial = run_case(
        boundary_ready=1,
        was_enabled=0,
        was_active=0,
        partial_enable=True,
    )
    assert partial.returncode == 0, partial.stderr
    assert (tmp_path / "state-1-0-0-0-1").read_text(encoding="utf-8") == "0:0\n"
    partial_trace = (tmp_path / "trace-1-0-0-0-1").read_text(encoding="utf-8")
    assert "disable --now macro-market-memory-options.timer" in partial_trace
    assert "stop macro-market-memory-options.service" in partial_trace


def test_option_runtime_drift_disarms_before_git_reset_without_touching_unrelated(
    tmp_path: Path,
) -> None:
    update = _text(UPDATE)
    stop_helpers = update.split("# BEGIN W1B5_UNIT_STOP_HELPERS\n", 1)[1].split(
        "# END W1B5_UNIT_STOP_HELPERS", 1
    )[0]
    reciprocal_stop = update.split("# BEGIN W1B5_RECIPROCAL_STOP\n", 1)[1].split(
        "# END W1B5_RECIPROCAL_STOP", 1
    )[0]
    disarm = update.split("# BEGIN W1B5_TIMER_DISARM\n", 1)[1].split(
        "# END W1B5_TIMER_DISARM", 1
    )[0]
    pre_reset = update.split("# BEGIN W1B5_PRE_RESET_GUARD\n", 1)[1].split(
        "# END W1B5_PRE_RESET_GUARD", 1
    )[0]
    runtime_regex = re.search(r"OPTIONS_RUNTIME_CLOSURE_REGEX='([^']+)'", update)
    reciprocal_regex = re.search(r"OPTIONS_RECIPROCAL_CLOSURE_REGEX='([^']+)'", update)
    assert runtime_regex is not None
    assert reciprocal_regex is not None
    assert update.index("# BEGIN W1B5_PRE_RESET_GUARD") < update.index(
        'git -C "$APP_DIR" reset --hard -q FETCH_HEAD'
    )

    def trace_for(changed: str) -> list[str]:
        trace = tmp_path / changed.replace("/", "-").replace(".", "-")
        marker = tmp_path / "marker"
        marker.touch()
        script = tmp_path / f"pre-reset-{len(list(tmp_path.iterdir()))}.sh"
        script.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
TRACE={shlex.quote(str(trace))}
OPTIONS_TIMER_DISARMED=0
OPTIONS_API_FENCE_MARKER={shlex.quote(str(marker))}
OPTIONS_RECIPROCAL_FENCE_MARKER={shlex.quote(str(tmp_path / "reciprocal-marker"))}
OPTIONS_RUNTIME_CLOSURE_REGEX={shlex.quote(runtime_regex.group(1))}
OPTIONS_RECIPROCAL_CLOSURE_REGEX={shlex.quote(reciprocal_regex.group(1))}
OPTIONS_DEFER_REARM_FOR_SELF_UPDATE=0
RECIPROCAL_TIMERS_PAUSED=0
CHANGED={shlex.quote(changed)}
    systemctl() {{
      printf '%s\\n' "$*" >>"$TRACE"
      if [ "$1" = show ]; then
        case "$3" in
          ActiveState) printf '%s\\n' inactive ;;
          MainPID|ControlPID)
            case "$5" in
              *.timer) printf '\\n' ;;
              *) printf '%s\\n' 0 ;;
            esac
            ;;
          UnitFileState) printf '%s\\n' disabled ;;
          LoadState) printf '%s\\n' loaded ;;
        esac
      fi
      return 0
    }}
{stop_helpers}
{disarm}
{reciprocal_stop}
{pre_reset}
""",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["bash", str(script)], text=True, capture_output=True, check=False
        )
        assert result.returncode == 0, result.stderr
        return trace.read_text(encoding="utf-8").splitlines() if trace.exists() else []

    option_trace = trace_for("engine/neuralweb/market_memory_pit.py")
    assert "disable --now macro-market-memory-options.timer" in option_trace
    assert "stop macro-market-memory-options.service" in option_trace
    self_update_trace = trace_for("app/deploy/update.sh")
    assert "stop macro-market-memory-source.timer" in self_update_trace
    assert "stop macro-market-memory-source.service" in self_update_trace
    timer_trace = trace_for("app/deploy/macro-market-memory-source.timer")
    assert "stop macro-market-memory-source.timer" in timer_trace
    experience_trace = trace_for(
        "engine/neuralweb/market_memory_experience_accrual.py"
    )
    assert "stop macro-market-memory-experience.timer" in experience_trace
    assert "stop macro-market-memory-experience.service" in experience_trace
    scripts_init_trace = trace_for("scripts/__init__.py")
    assert "stop macro-market-memory-options.service" in scripts_init_trace
    assert "stop macro-market-memory-source.service" in scripts_init_trace
    engine_init_trace = trace_for("engine/__init__.py")
    assert "stop macro-market-memory-options.service" in engine_init_trace
    assert "stop macro-market-memory-source.service" in engine_init_trace
    neuralweb_init_trace = trace_for("engine/neuralweb/__init__.py")
    assert "stop macro-market-memory-options.service" in neuralweb_init_trace
    assert "stop macro-market-memory-source.service" in neuralweb_init_trace
    dropin_migration_trace = trace_for(
        "app/deploy/market-memory-options-dropin-migration.sh"
    )
    assert "stop macro-market-memory-options.service" in dropin_migration_trace
    assert "stop macro-market-memory-source.service" in dropin_migration_trace
    assert trace_for("data/marketing/hot_tape_ring.jsonl") == []


def test_all_existing_market_memory_services_reciprocally_hide_option_root() -> None:
    units = [API_SERVICE]
    units.extend(
        path for path in DEPLOY.glob("macro-market-memory-*.service") if path != SERVICE
    )
    assert len(units) >= 6
    for unit in units:
        unit_text = _text(unit)
        assert f"InaccessiblePaths={STATE_ROOT}" in unit_text, (
            f"{unit.name} can see the disjoint credentialed store"
        )
        assert "InaccessiblePaths=/etc/macro-market-memory-options" in unit_text, (
            f"{unit.name} can see the process-specific credential source"
        )
        if unit != API_SERVICE:
            assert "InaccessiblePaths=-/etc/macro-ollama.env" in unit_text, (
                f"{unit.name} can read the unrelated local-model environment"
            )
    option_service = _text(SERVICE)
    assert "InaccessiblePaths=-/opt/macro/.env" in option_service
    assert "InaccessiblePaths=-/etc/macro-api.env" in option_service
    assert "InaccessiblePaths=-/etc/macro-live.env" in option_service


def test_loaded_unit_attestor_rejects_symlinks_metadata_drift_and_dropins() -> None:
    boundary = _text(UNIT_BOUNDARY)
    assert '[ -f "$installed" ] && [ ! -L "$installed" ]' in boundary
    assert "stat -c '%U:%G:%a'" in boundary
    assert "root:root:644" in boundary
    assert "FragmentPath" in boundary
    assert "DropInPaths" in boundary
    assert "NeedDaemonReload" in boundary
    assert '[ "$fragment" = "$installed" ]' in boundary
    assert '[ -z "$dropins" ]' in boundary


def test_legacy_api_dropin_migration_is_exact_and_fail_closed(tmp_path: Path) -> None:
    api_service = _text(API_SERVICE)
    setup = _text(SETUP)
    update = _text(UPDATE)
    source_line = (
        'source "$APP_DIR/app/deploy/market-memory-options-dropin-migration.sh"'
    )
    assert api_service.count("EnvironmentFile=-/etc/macro-ollama.env") == 1
    assert source_line in setup and source_line in update
    update_migration = update.index("if ! mm_remove_exact_legacy_api_ollama_dropin")
    update_install = update.index(
        'install -m 0644 "$APP_DIR/app/deploy/macro-api.service" '
        "/etc/systemd/system/macro-api.service"
    )
    assert update_install < update_migration

    dropin_dir = tmp_path / "macro-api.service.d"
    dropin = dropin_dir / "ollama.conf"
    source_unit = tmp_path / "macro-api.service"
    installed_unit = tmp_path / "installed-macro-api.service"
    source_unit.write_text(
        "[Service]\nEnvironmentFile=-/etc/macro-ollama.env\n",
        encoding="utf-8",
    )
    installed_unit.write_bytes(source_unit.read_bytes())
    source_unit.chmod(0o644)
    installed_unit.chmod(0o644)
    helper = _text(DROPIN_MIGRATION).replace(
        "MM_LEGACY_API_DROPIN_DIR=/etc/systemd/system/macro-api.service.d",
        f"MM_LEGACY_API_DROPIN_DIR={shlex.quote(str(dropin_dir))}",
    )
    harness = tmp_path / "dropin-migration.sh"
    harness.write_text(
        f"source {shlex.quote(str(UNIT_BOUNDARY))}\n"
        + helper
        + "\nmm_remove_exact_legacy_api_ollama_dropin "
        + f"{shlex.quote(str(source_unit))} "
        + f"{shlex.quote(str(installed_unit))}\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_stat = fake_bin / "stat"
    fake_stat.write_text(
        """#!/usr/bin/env python3
import os
import sys

if len(sys.argv) != 4 or sys.argv[1] != "-c":
    raise SystemExit(2)
format_string = sys.argv[2]
value = sys.argv[3]
info = os.stat(value, follow_symlinks=False)
if format_string == "%s":
    print(info.st_size)
elif format_string == "%U:%G:%a":
    print(f"root:root:{info.st_mode & 0o777:o}")
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    fake_stat.chmod(0o755)

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(harness)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )

    dropin_dir.mkdir(mode=0o755)
    dropin.write_text(
        "[Service]\nEnvironmentFile=-/etc/macro-ollama.env\n", encoding="utf-8"
    )
    dropin.chmod(0o644)
    migrated = run()
    assert migrated.returncode == 0, migrated.stderr
    assert not dropin_dir.exists()

    dropin_dir.mkdir(mode=0o755)
    dropin.write_text(
        "[Service]\nEnvironmentFile=-/etc/macro-ollama.env\n", encoding="utf-8"
    )
    dropin.chmod(0o644)
    installed_unit.write_text("[Service]\n", encoding="utf-8")
    rejected_noncanonical = run()
    assert rejected_noncanonical.returncode != 0
    assert dropin.exists()
    installed_unit.write_bytes(source_unit.read_bytes())

    dropin.write_text("[Service]\nEnvironment=UNREVIEWED=1\n", encoding="utf-8")
    dropin.chmod(0o644)
    rejected = run()
    assert rejected.returncode != 0
    assert dropin.exists()

    dropin.write_text(
        "[Service]\nEnvironmentFile=-/etc/macro-ollama.env\n", encoding="utf-8"
    )
    sibling = dropin_dir / "unknown.conf"
    sibling.write_text("[Service]\nEnvironment=UNREVIEWED=1\n", encoding="utf-8")
    sibling.chmod(0o644)
    rejected_sibling = run()
    assert rejected_sibling.returncode != 0
    assert dropin.exists() and sibling.exists()


def test_loaded_unit_attestor_executably_rejects_timer_dropin(tmp_path: Path) -> None:
    source = tmp_path / "reviewed.timer"
    installed = tmp_path / "installed.timer"
    source.write_text("[Timer]\nOnCalendar=daily\n", encoding="utf-8")
    installed.write_bytes(source.read_bytes())
    harness = tmp_path / "unit-boundary-harness.sh"
    harness.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
source {shlex.quote(str(UNIT_BOUNDARY))}
SOURCE={shlex.quote(str(source))}
INSTALLED={shlex.quote(str(installed))}
DROPINS=''
stat() {{ printf '%s\\n' root:root:644; }}
systemctl() {{
  [ "$1" = show ]
  case "$3" in
    FragmentPath) printf '%s\\n' "$INSTALLED" ;;
    DropInPaths) printf '%s\\n' "$DROPINS" ;;
    NeedDaemonReload) printf '%s\\n' no ;;
    *) return 1 ;;
  esac
}}
mm_loaded_unit_ready "$SOURCE" "$INSTALLED" reciprocal.timer
DROPINS=/etc/systemd/system/reciprocal.timer.d/override.conf
! mm_loaded_unit_ready "$SOURCE" "$INSTALLED" reciprocal.timer
""",
        encoding="utf-8",
    )

    subprocess.run(["bash", str(harness)], check=True)


def test_api_cannot_import_route_or_configure_option_evidence() -> None:
    api_service = _text(API_SERVICE)
    assert f"InaccessiblePaths={STATE_ROOT}" in api_service
    assert STORE_ROOT not in api_service
    for path in (ROOT / "app").rglob("*.py"):
        source = _text(path)
        tree = ast.parse(source, filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)
        assert not imported.intersection(OPTION_MODULES)
        assert "market_memory_option_oi" not in source
        assert "MARKET_MEMORY_OPTION_OI_STORE_DIR" not in source
    for route in _app_route_paths():
        normalized = route.lower().replace("_", "-")
        assert "option-oi" not in normalized
        assert "open-interest" not in normalized


def test_market_memory_ci_owns_every_option_contract_and_trigger() -> None:
    body = _legacy_job_body(_text(LEGACY_JOBS), "market-memory-contract")
    workflow = _text(CI_WORKFLOW)
    for test in (
        "tests/test_market_memory_option_oi_observation.py",
        "tests/test_market_memory_option_oi_store.py",
        "tests/test_capture_market_memory_option_oi.py",
        "tests/test_market_memory_options_deploy.py",
    ):
        assert test in body
    for path in OPTION_CLOSURE_PATHS:
        assert f'      - "{path}"' in workflow, f"missing CI trigger: {path}"


def test_production_writer_is_single_narrow_cli_and_not_an_existing_gex_lane() -> None:
    assert WRITER.is_file()
    source = _text(WRITER)
    for forbidden in (
        "build_polygon_gex",
        "polygon_options",
        "market_memory_replay",
        "--api-key",
        "POLYGON_API_KEY",
        "MASSIVE_API_KEY",
        "--session",
        "--measurement-date",
        "--next-url",
        "--limit",
    ):
        assert forbidden not in source
