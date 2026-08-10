"""Deployment, privacy, credential, and CI guards for the W1B.5 canary."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-options.service"
TIMER = DEPLOY / "macro-market-memory-options.timer"
PREREQS = DEPLOY / "market-memory-options-prereqs.sh"
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
    "config/market_memory_option_oi_source.v1.json",
    "engine/neuralweb/market_memory_option_oi_observation.py",
    "engine/neuralweb/market_memory_option_oi_store.py",
    "contracts/market_memory/option_oi_probe_receipt.v1.schema.json",
    "contracts/market_memory/spy_option_oi_source_observation.v1.schema.json",
    "contracts/market_memory/option_oi_capture_receipt.v1.schema.json",
    "contracts/market_memory/option_oi_store.v1.schema.json",
    "scripts/capture_market_memory_option_oi.py",
    "app/deploy/api-setup.sh",
    "app/deploy/update.sh",
    "app/deploy/macro-api.service",
    "app/deploy/market-memory-options-prereqs.sh",
    "app/deploy/macro-market-memory-options.service",
    "app/deploy/macro-market-memory-options.timer",
    "app/deploy/macro-market-memory-source.service",
    "app/deploy/macro-market-memory-context.service",
    "app/deploy/macro-market-memory-identity.service",
    "app/deploy/macro-market-memory-breadth.service",
    "app/deploy/macro-market-memory-technicals.service",
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
    for script in (PREREQS, SETUP, UPDATE):
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
    assert "OnBootSec=" not in timer
    assert "OnCalendar=Mon..Fri *-*-* 08:20:00 America/New_York" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=false" in timer
    assert "market session" in timer
    assert "measurement date" in timer


def test_prereqs_create_disjoint_dac_root_without_exporting_or_logging_key() -> None:
    prereqs = _text(PREREQS)
    assert f"SERVICE_USER={SERVICE_USER}" in prereqs
    assert f"SERVICE_GROUP={SERVICE_GROUP}" in prereqs
    assert f"STATE_ROOT={STATE_ROOT}" in prereqs
    assert "useradd --system" in prereqs
    assert "--no-create-home --shell /usr/sbin/nologin" in prereqs
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


def test_setup_provisions_before_api_and_conditionally_arms_option_lane() -> None:
    setup = _text(SETUP)
    identity_prereq = (
        'bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" --identity-only'
    )
    full_prereq = 'if bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh"; then'
    assert identity_prereq in setup
    assert full_prereq in setup
    verify = setup.index("systemd-analyze verify")
    assert setup.index(identity_prereq) < verify
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
    fence_marker = setup.index(
        "install -m 0644 /dev/null /run/macro-api-market-memory-options-deny.ready"
    )
    timer_enable = setup.index(
        "systemctl enable --now macro-market-memory-options.timer"
    )
    assert (
        api_restart < fence_marker < setup.index(full_prereq) < immediate < timer_enable
    )
    assert "POST_API_PID" in setup
    assert 'if [ "$OPTIONS_CREDENTIAL_READY" -eq 1 ]' in setup


def test_updater_reconciles_disarms_and_runs_exact_option_closure() -> None:
    update = _text(UPDATE)
    identity_prereq = (
        'bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh" --identity-only'
    )
    full_prereq = 'if bash "$APP_DIR/app/deploy/market-memory-options-prereqs.sh"; then'
    assert update.index(identity_prereq) < update.index("API_UNIT_UPDATED=0")
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
    for path in (
        "scripts/capture_market_memory_option_oi.py",
        "engine/neuralweb/market_memory_option_oi_observation.py",
        "engine/neuralweb/market_memory_option_oi_store.py",
        "contracts/market_memory/option_oi_probe_receipt.v1.schema.json",
        "contracts/market_memory/spy_option_oi_source_observation.v1.schema.json",
        "contracts/market_memory/option_oi_capture_receipt.v1.schema.json",
        "contracts/market_memory/option_oi_store.v1.schema.json",
        "config/market_memory_option_oi_source.v1.json",
        "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md",
    ):
        basename = Path(path).name.replace(".", r"\.")
        assert basename in block, f"missing updater trigger for {path}"

    api_restart = update.index("systemctl restart macro-api", end)
    marker = update.index(
        'install -m 0644 /dev/null "$OPTIONS_API_FENCE_MARKER"', api_restart
    )
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
    assert '[ ! -f "$OPTIONS_API_FENCE_MARKER" ]' in update
    assert "API_RESTART_CONFIRMED" in update
    assert "OPTIONS_BOUNDARY_READY" in update
    assert "OPTIONS_API_FENCE_READY" in update
    assert "systemctl disable --now macro-market-memory-options.timer" in update


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
