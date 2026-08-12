"""Deployment and isolation guards for the first production-record lane."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-production-records.service"
TIMER = DEPLOY / "macro-market-memory-production-records.timer"
API_SERVICE = DEPLOY / "macro-api.service"
OPTIONS_SERVICE = DEPLOY / "macro-market-memory-options.service"
RUNTIME_FENCE = DEPLOY / "market-memory-options-runtime-fence.sh"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"

STORE_ROOT = "/var/lib/macro-market-memory/state/production-record-options-episode-v1"
RECIPROCAL_PROFILES = (
    "source",
    "context",
    "identity",
    "breadth",
    "technicals",
    "experience",
    "production-records",
)
CAPTURE_CLOSURE = (
    "scripts/capture_market_memory_options_episodes.py",
    "engine/options_signal_episode.py",
    "engine/neuralweb/market_memory_production_records.py",
    "contracts/market_memory/options_signal_episode_production_record.v1.schema.json",
    "contracts/options/options.signal_episode.v1.schema.json",
    "lib/nyse_calendar.py",
    "data/options_signal_episode/episodes.jsonl",
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


def _update_block() -> str:
    update = _text(UPDATE)
    start = update.index("MARKET_MEMORY_PRODUCTION_RECORDS_UNIT_UPDATED=0")
    end = update.index("# W1B.5 private, future-only option-OI", start)
    return update[start:end]


def test_production_record_deploy_shells_have_valid_syntax() -> None:
    for script in (SETUP, UPDATE, RUNTIME_FENCE):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_service_is_network_dark_credential_free_and_exactly_scoped() -> None:
    service = _text(SERVICE)

    assert "Type=oneshot" in service
    assert "After=local-fs.target" in service
    assert "network" not in _setting_values(service, "After")[0].lower()
    assert "WorkingDirectory=/opt/macro" in service
    assert (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.capture_market_memory_options_episodes "
        "--repository-root /opt/macro "
        f"--store-root {STORE_ROOT}"
    ) in service
    assert "PrivateNetwork=true" in service
    assert "TimeoutStartSec=300" in service
    assert "MemoryHigh=1G" in service
    assert "MemoryMax=2G" in service
    assert _setting_values(service, "RestrictAddressFamilies") == ["AF_UNIX"]
    assert "AF_INET" not in service
    assert "Environment=" not in service
    assert "EnvironmentFile=" not in service
    assert "LoadCredential=" not in service
    assert _setting_values(service, "ReadOnlyPaths") == ["/opt/macro"]
    assert _setting_values(service, "ReadWritePaths") == [STORE_ROOT]
    assert "ReadWritePaths=/var/lib/macro-market-memory/state\n" not in service

    for protected in (
        "/var/lib/macro-market-memory-options",
        "/etc/macro-market-memory-options",
        "/var/lib/macro-market-memory/public",
        "/var/lib/macro-market-memory/state/sources",
        "/var/lib/macro-market-memory/state/context-projection",
        "/var/lib/macro-market-memory/state/identity-v1",
        "/var/lib/macro-market-memory/state/breadth-v1",
        "/var/lib/macro-market-memory/state/technicals-v1",
        "/opt/macro/.env",
        "/var/lib/macro-api",
        "/var/lib/macro-live",
        "/etc/macro-api.env",
        "/etc/macro-live.env",
        "/etc/macro-market-memory.env",
        "/etc/macro-ollama.env",
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
    assert "Restart=always" not in service


def test_timer_is_a_bounded_nightly_persistent_retry_contract() -> None:
    timer = _text(TIMER)

    assert "OnBootSec=19min" in timer
    assert "OnCalendar=*-*-* 06:47:00 UTC" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=true" in timer
    assert "Unit=macro-market-memory-production-records.service" in timer
    assert "WantedBy=timers.target" in timer


def test_setup_provisions_verifies_installs_runs_and_arms_lane() -> None:
    setup = _text(SETUP)
    service_name = "macro-market-memory-production-records.service"
    timer_name = "macro-market-memory-production-records.timer"

    provision = setup.index(f"install -d -m 0700 {STORE_ROOT}")
    verify = setup.index("systemd-analyze verify")
    service_install = setup.index(
        f'install -m 0644 "$APP_DIR/app/deploy/{service_name}" '
        f"/etc/systemd/system/{service_name}"
    )
    timer_install = setup.index(
        f'install -m 0644 "$APP_DIR/app/deploy/{timer_name}" '
        f"/etc/systemd/system/{timer_name}"
    )
    reload = setup.index("systemctl daemon-reload")
    run = setup.index(f"systemctl start {service_name}")
    arm = setup.index(f"systemctl enable --now {timer_name}")
    assert provision < verify < service_install < reload < run < arm
    assert f'"$APP_DIR/app/deploy/{service_name}"' in setup[verify:service_install]
    assert f'"$APP_DIR/app/deploy/{timer_name}"' in setup[verify:timer_install]
    assert "source context identity breadth technicals experience production-records" in setup


def test_updater_reconciles_exact_capture_closure_and_retries() -> None:
    update = _text(UPDATE)
    block = _update_block()

    assert f"install -d -m 0700 {STORE_ROOT}" in update
    assert "MARKET_MEMORY_PRODUCTION_RECORDS_UNIT_SOURCES=(" in block
    assert (
        'systemd-analyze verify "${MARKET_MEMORY_PRODUCTION_RECORDS_UNIT_SOURCES[@]}"'
        in block
    )
    assert 'install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"' in block
    assert "systemctl daemon-reload" in block
    assert (
        "systemctl enable --now macro-market-memory-production-records.timer" in block
    )
    assert "systemctl start macro-market-memory-production-records.service" in block
    assert "nightly timer will retry" in block
    assert 'if [ "$API_DEPS_OK" -ne 1 ]; then' in block

    finalization = update[update.index("# BEGIN W1B5_TIMER_FINALIZATION") :]
    rearm = finalization.index(
        'systemctl enable --now "macro-market-memory-$RECIPROCAL_PROFILE.timer"'
    )
    deferred_run = finalization.index(
        'if [ "$MARKET_MEMORY_PRODUCTION_RECORDS_RUN_NEEDED" -eq 1 ]; then'
    )
    assert rearm < deferred_run

    trigger_matches = re.findall(r"grep -qE '([^']+)'", block)
    assert len(trigger_matches) == 1
    trigger = re.compile(trigger_matches[0])
    for path in CAPTURE_CLOSURE:
        assert trigger.fullmatch(path), f"production-record updater misses {path}"

    reciprocal_match = re.search(r"OPTIONS_RECIPROCAL_CLOSURE_REGEX='([^']+)'", update)
    assert reciprocal_match is not None
    reciprocal_trigger = re.compile(reciprocal_match.group(1))
    for path in CAPTURE_CLOSURE:
        assert reciprocal_trigger.fullmatch(path), (
            f"pre-reset reciprocal stop misses production-record dependency {path}"
        )
    for unrelated in (
        "data/options_signal_episode/session_outcomes.jsonl",
        "data/options_signal_episode/campaigns.jsonl",
        "engine/neuralweb/cortex_retrieval.py",
        "app/market_memory.py",
    ):
        assert not trigger.fullmatch(unrelated)


def test_expanded_reciprocal_boundary_is_exact_and_invalidates_old_receipt() -> None:
    profiles = "source context identity breadth technicals experience production-records"
    setup = _text(SETUP)
    update = _text(UPDATE)
    fence = _text(RUNTIME_FENCE)
    options = _text(OPTIONS_SERVICE)

    assert f"for reciprocal_profile in {profiles}; do" in setup
    assert f"for boundary_profile in {profiles}; do" in setup
    assert f"for profile in {profiles}; do" in update
    assert f"for profile in {profiles}; do" in fence
    assert "RECIPROCAL_MARKER_BODY=market-memory-options-reciprocal-deny.v2" in fence

    expected_services = {
        f"macro-market-memory-{profile}.service" for profile in RECIPROCAL_PROFILES
    }
    assert set(_setting_values(options, "Conflicts")[0].split()) == expected_services
    assert expected_services <= set(_setting_values(options, "After")[0].split())


def test_private_store_is_hidden_from_api_and_every_other_writer() -> None:
    assert "InaccessiblePaths=/var/lib/macro-market-memory/state" in _text(API_SERVICE)
    for profile in RECIPROCAL_PROFILES[:-1]:
        service = _text(DEPLOY / f"macro-market-memory-{profile}.service")
        optional = "-" if profile == "experience" else ""
        assert f"InaccessiblePaths={optional}{STORE_ROOT}" in service

    production_records = _text(SERVICE)
    assert (
        "InaccessiblePaths=/var/lib/macro-market-memory/state/experience-v1"
        in production_records
    )

    # The credentialed option writer denies the entire Market Memory tree.
    assert "InaccessiblePaths=/var/lib/macro-market-memory" in _text(OPTIONS_SERVICE)
