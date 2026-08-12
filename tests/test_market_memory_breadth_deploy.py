"""Deployment, CI, and serving-boundary guards for W1B.3A breadth capture."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from tests import market_memory_repo_scan as repo_scan

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-breadth.service"
TIMER = DEPLOY / "macro-market-memory-breadth.timer"
API_SERVICE = DEPLOY / "macro-api.service"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"
WRITER = ROOT / "scripts" / "capture_market_memory_breadth.py"
LEGACY_JOBS = ROOT / ".github" / "ci" / "legacy-jobs.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

STORE_ROOT = "/var/lib/macro-market-memory/state/breadth-v1"
WRITER_MODULES = {
    "engine.neuralweb.market_memory_actual_output_store",
    "engine.neuralweb.market_memory_breadth_observation",
}
BREADTH_CLOSURE_PATHS = (
    "scripts/capture_market_memory_breadth.py",
    "engine/neuralweb/market_memory_actual_output_store.py",
    "engine/neuralweb/market_memory_breadth_observation.py",
    "contracts/market_memory/breadth_source_observation.v1.schema.json",
    "contracts/market_memory/breadth_factors_snapshot.v1.schema.json",
    "contracts/market_memory/breadth_actual_output_capture_receipt.v1.schema.json",
    "contracts/market_memory/breadth_actual_output_store.v1.schema.json",
    "data/breadth/breadth.parquet",
    "data/breadth/constituents.parquet",
    "config/market_memory_canary.v1.json",
    "lib/nyse_calendar.py",
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


def _breadth_update_block() -> str:
    update = _text(UPDATE)
    start = update.index("MARKET_MEMORY_BREADTH_UNIT_UPDATED=0")
    end = min(
        update.index(marker, start)
        for marker in (
            "# W2C private prospective experience accrual",
            "# First admitted production-record writer",
        )
    )
    return update[start:end]


def _production_calls(function_name: str) -> set[Path]:
    callers: set[Path] = set()
    for path in repo_scan.production_python_paths():
        called = repo_scan.callee_names(path)
        is_named_call = function_name in called.direct
        is_attribute_call = function_name in called.attribute
        if is_named_call or is_attribute_call:
            callers.add(path.relative_to(ROOT))
    return callers


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


def _legacy_job_body(legacy_jobs: str, job_id: str) -> str:
    job = re.search(
        rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-z0-9][a-z0-9-]*:|\Z)",
        legacy_jobs,
        re.MULTILINE | re.DOTALL,
    )
    assert job is not None, f"missing legacy CI job: {job_id}"
    return job.group("body")


def test_breadth_deploy_shell_scripts_have_valid_syntax() -> None:
    subprocess.run(["bash", "-n", str(SETUP)], check=True)
    subprocess.run(["bash", "-n", str(UPDATE)], check=True)


def test_breadth_service_is_network_dark_credential_free_and_exactly_scoped() -> None:
    service = _text(SERVICE)

    assert "Type=oneshot" in service
    assert "WorkingDirectory=/opt/macro" in service
    assert (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.capture_market_memory_breadth --repository-root /opt/macro "
        f"--store-root {STORE_ROOT}"
    ) in service
    assert "PrivateNetwork=true" in service
    assert _setting_values(service, "RestrictAddressFamilies") == ["AF_UNIX"]
    assert "AF_INET" not in service
    assert "Environment=" not in service
    assert "EnvironmentFile=" not in service
    assert _setting_values(service, "ReadOnlyPaths") == ["/opt/macro"]
    assert _setting_values(service, "ReadWritePaths") == [STORE_ROOT]
    assert "ReadWritePaths=/var/lib/macro-market-memory/state\n" not in service
    assert "ReadWritePaths=/var/lib/macro-market-memory\n" not in service

    for protected in (
        "/var/lib/macro-market-memory/public",
        "/var/lib/macro-market-memory/state/sources",
        "/var/lib/macro-market-memory/state/context-projection",
        "/var/lib/macro-market-memory/state/identity-v1",
        "/var/lib/macro-api",
        "/var/lib/macro-biocatalyst",
        "/var/lib/macro-codex",
        "/var/lib/macro-codex-2",
        "/var/lib/macro-codex-3",
        "/var/lib/macro-live",
        "/etc/macro-admin.env",
        "/etc/macro-api.env",
        "/etc/macro-biocatalyst.env",
        "/etc/macro-biocatalyst-control.env",
        "/etc/macro-live.env",
        "/etc/macro-market-memory.env",
        "/etc/macro-sentinel.env",
    ):
        assert re.search(
            rf"^InaccessiblePaths=-?{re.escape(protected)}$",
            service,
            re.MULTILINE,
        )

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
    assert "StateDirectory=" not in service
    assert "Restart=always" not in service


def test_breadth_timer_is_an_explicit_bounded_retry_contract() -> None:
    service = _text(SERVICE)
    timer = _text(TIMER)

    assert "After=local-fs.target" in service
    assert "After=network.target" not in service
    assert "TimeoutStartSec=180" in service
    assert "WantedBy=multi-user.target" in service
    assert "OnBootSec=17min" in timer
    assert "OnCalendar=*-*-* *:43:00 UTC" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=true" in timer
    assert "Unit=macro-market-memory-breadth.service" in timer
    assert "WantedBy=timers.target" in timer


def test_api_cannot_read_import_or_route_the_private_breadth_store() -> None:
    service = _text(API_SERVICE)

    assert "InaccessiblePaths=/var/lib/macro-market-memory/state" in service
    assert "InaccessiblePaths=-/var/lib/macro-market-memory/state" not in service
    assert STORE_ROOT not in service
    assert "MARKET_MEMORY_BREADTH_STORE_DIR" not in service

    for path in (ROOT / "app").rglob("*.py"):
        source = _text(path)
        tree = ast.parse(source, filename=str(path))
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
                imported_modules.update(
                    f"{node.module}.{alias.name}" for alias in node.names
                )
        assert not (imported_modules & WRITER_MODULES)
        assert "market_memory_actual_output_store" not in source
        assert "market_memory_breadth_observation" not in source
        assert "MARKET_MEMORY_BREADTH_STORE_DIR" not in source

    assert all("breadth" not in route.lower() for route in _app_route_paths())


def test_setup_provisions_verifies_installs_runs_and_arms_breadth_lane() -> None:
    setup = _text(SETUP)

    assert f"install -d -m 0700 {STORE_ROOT}" in setup
    verify = setup.index("systemd-analyze verify")
    assert setup.index(f"install -d -m 0700 {STORE_ROOT}") < verify

    install_positions: list[int] = []
    for name in (
        "macro-market-memory-breadth.service",
        "macro-market-memory-breadth.timer",
    ):
        assert (
            f'"$APP_DIR/app/deploy/{name}"' in setup[: setup.index("install -m 0644")]
        )
        install_line = (
            f'install -m 0644 "$APP_DIR/app/deploy/{name}" /etc/systemd/system/{name}'
        )
        assert install_line in setup
        install_positions.append(setup.index(install_line))
    daemon_reload = setup.index("systemctl daemon-reload")
    immediate_run = setup.index("systemctl start macro-market-memory-breadth.service")
    timer_enable = setup.index(
        "systemctl enable --now macro-market-memory-breadth.timer"
    )
    assert verify < min(install_positions)
    assert max(install_positions) < daemon_reload < immediate_run < timer_enable
    assert "systemctl restart macro-market-memory-breadth.service" not in setup


def test_update_reconciles_and_immediately_runs_complete_breadth_closure() -> None:
    update = _text(UPDATE)
    block = _breadth_update_block()

    assert f"install -d -m 0700 {STORE_ROOT}" in update
    assert update.index(f"install -d -m 0700 {STORE_ROOT}") < update.index(
        "MARKET_MEMORY_BREADTH_UNIT_UPDATED=0"
    )
    assert "MARKET_MEMORY_BREADTH_UNIT_SOURCES=(" in block
    assert '"$APP_DIR/app/deploy/macro-market-memory-breadth.service"' in block
    assert '"$APP_DIR/app/deploy/macro-market-memory-breadth.timer"' in block
    verify = block.index(
        'systemd-analyze verify "${MARKET_MEMORY_BREADTH_UNIT_SOURCES[@]}"'
    )
    install = block.index('install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"')
    daemon_reload = block.index("systemctl daemon-reload")
    timer_enable = block.index(
        "systemctl enable --now macro-market-memory-breadth.timer"
    )
    immediate_run = block.index("systemctl start macro-market-memory-breadth.service")
    assert verify < install < daemon_reload < timer_enable < immediate_run
    assert "systemctl restart macro-market-memory-breadth.timer" in block
    assert "MARKET_MEMORY_BREADTH_RUN_NEEDED=0" in block
    assert 'if [ "$API_DEPS_OK" -ne 1 ]; then' in block
    assert "systemctl restart macro-market-memory-breadth.service" not in block

    trigger_matches = re.findall(r"grep -qE '([^']+)'", block)
    assert len(trigger_matches) == 1
    trigger = re.compile(trigger_matches[0])
    for path in BREADTH_CLOSURE_PATHS:
        assert trigger.fullmatch(path), f"breadth updater misses {path}"
    for unrelated in (
        "app/market_memory.py",
        "engine/neuralweb/market_memory_trusted.py",
        "contracts/market_memory/trusted_capture_receipt.v1.schema.json",
        "data/regime/latest.json",
        "data/breadth/archive/2025.parquet",
    ):
        assert not trigger.fullmatch(unrelated), (
            f"breadth updater trigger is overbroad for {unrelated}"
        )


def test_capture_cli_is_the_only_production_breadth_writer() -> None:
    assert _production_calls("capture_breadth_actual_output") == {
        Path("scripts/capture_market_memory_breadth.py")
    }
    assert _production_calls("build_current_breadth_snapshot") == {
        Path("scripts/capture_market_memory_breadth.py")
    }

    writer = _text(WRITER)
    assert "commit = _repository_commit(root)" in writer
    assert (
        "breadth.build_current_breadth_snapshot(root, pinned_commit=commit)" in writer
    )
    assert "actual_output_store.capture_breadth_actual_output(" in writer
    for forbidden_override in (
        "--pinned-commit",
        "--first-observed-at",
        "--available-at",
        "--session",
        "--snapshot-id",
        "--authority",
    ):
        assert forbidden_override not in writer


def test_breadth_contract_and_inputs_are_owned_by_market_memory_ci() -> None:
    legacy_jobs = _text(LEGACY_JOBS)
    workflow = _text(CI_WORKFLOW)
    job = _legacy_job_body(legacy_jobs, "market-memory-contract")

    for test_path in (
        "tests/test_market_memory_breadth_observation.py",
        "tests/test_market_memory_breadth_store.py",
        "tests/test_market_memory_breadth_deploy.py",
    ):
        assert test_path in job
        assert f'"{test_path}"' in workflow
    for production_path in BREADTH_CLOSURE_PATHS:
        assert f'"{production_path}"' in workflow
