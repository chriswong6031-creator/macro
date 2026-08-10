"""Deployment and ownership guards for the private W1B.2 identity lane."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-identity.service"
TIMER = DEPLOY / "macro-market-memory-identity.timer"
API_SERVICE = DEPLOY / "macro-api.service"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"

STORE_ROOT = "/var/lib/macro-market-memory/state/identity-v1"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _setting_values(unit: str, setting: str) -> list[str]:
    prefix = f"{setting}="
    return [
        line.removeprefix(prefix)
        for line in unit.splitlines()
        if line.startswith(prefix)
    ]


def _identity_update_block() -> str:
    update = _text(UPDATE)
    start = update.index("# W1B.2 private identity-observation publisher:")
    end = update.index("# macro-api: restart ONLY", start)
    return update[start:end]


def test_identity_deploy_shell_scripts_have_valid_syntax() -> None:
    subprocess.run(["bash", "-n", str(SETUP)], check=True)
    subprocess.run(["bash", "-n", str(UPDATE)], check=True)


def test_identity_service_is_network_dark_private_and_exactly_scoped() -> None:
    service = _text(SERVICE)

    assert "Type=oneshot" in service
    assert "WorkingDirectory=/opt/macro" in service
    assert (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.ingest_market_memory_identity --repository-root /opt/macro "
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
    assert "InaccessiblePaths=/var/lib/macro-market-memory/public" in service
    assert (
        "InaccessiblePaths=/var/lib/macro-market-memory/state/context-projection"
        in service
    )
    assert "InaccessiblePaths=/var/lib/macro-market-memory/state/sources" in service

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


def test_identity_timer_is_an_explicit_bounded_retry_contract() -> None:
    service = _text(SERVICE)
    timer = _text(TIMER)

    assert "After=local-fs.target" in service
    assert "After=network.target" not in service
    assert "TimeoutStartSec=180" in service
    assert "OnBootSec=11min" in timer
    assert "OnCalendar=*-*-* *:29:00 UTC" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=true" in timer
    assert "Unit=macro-market-memory-identity.service" in timer


def test_api_cannot_read_the_private_identity_store() -> None:
    service = _text(API_SERVICE)

    assert "InaccessiblePaths=/var/lib/macro-market-memory/state" in service
    assert "InaccessiblePaths=-/var/lib/macro-market-memory/state" not in service
    assert STORE_ROOT not in service

    for path in (ROOT / "app").rglob("*.py"):
        source = _text(path)
        assert "market_memory_identity_store" not in source
        assert "market_memory_identity_observation" not in source


def test_setup_provisions_verifies_installs_and_arms_identity_lane() -> None:
    setup = _text(SETUP)

    assert f"install -d -m 0700 {STORE_ROOT}" in setup
    assert setup.index(f"install -d -m 0700 {STORE_ROOT}") < setup.index(
        "systemd-analyze verify"
    )
    for name in (
        "macro-market-memory-identity.service",
        "macro-market-memory-identity.timer",
    ):
        assert f'"$APP_DIR/app/deploy/{name}"' in setup
        assert (
            f'install -m 0644 "$APP_DIR/app/deploy/{name}" /etc/systemd/system/{name}'
        ) in setup
    assert setup.index("systemd-analyze verify") < setup.index(
        "systemctl daemon-reload"
    )
    assert setup.index("systemctl daemon-reload") < setup.index(
        "systemctl start macro-market-memory-identity.service"
    )
    assert "systemctl enable --now macro-market-memory-identity.timer" in setup


def test_update_reconciles_and_immediately_runs_the_complete_identity_closure() -> None:
    update = _text(UPDATE)
    block = _identity_update_block()

    assert f"install -d -m 0700 {STORE_ROOT}" in update
    assert "MARKET_MEMORY_IDENTITY_UNIT_SOURCES=(" in block
    assert 'systemd-analyze verify "${MARKET_MEMORY_IDENTITY_UNIT_SOURCES[@]}"' in block
    assert 'install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"' in block
    assert "systemctl daemon-reload" in block
    assert "systemctl enable --now macro-market-memory-identity.timer" in block
    assert "systemctl start macro-market-memory-identity.service" in block
    assert "systemctl restart macro-market-memory-identity.service" not in block
    assert 'if [ "$API_DEPS_OK" -ne 1 ]; then' in block

    for trigger in (
        r"scripts/ingest_market_memory_identity\.py",
        r"market_memory_identity_(observation|store)\.py",
        r"lib/symbol_directory_receipts\.py",
        r"collectors/symbol_directory\.py",
        r"spy_listing_(object|observation)",
        r"identity_observation_(prepared|capture_receipt|store_receipts)",
        r"symbol_directory_completion_receipt\.v1\.schema\.json",
        r"data/symbol_directory/(snapshots|cik_map|receipts)/.*",
    ):
        assert trigger in block


def test_identity_lane_has_no_public_or_trading_authority_surface() -> None:
    service = _text(SERVICE)
    update_block = _identity_update_block()

    forbidden = (
        "market_memory_trusted",
        "capture_trusted_regime_context",
        "options_signal_episode",
        "outcomes_h60",
        "prophet",
        "may_trade",
        "may_gate",
        "may_size",
    )
    for token in forbidden:
        assert token not in service
        assert token not in update_block
