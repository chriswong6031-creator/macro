"""CLI, deployment, isolation, and CI guards for W2C experience accrual."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from scripts import accrue_market_memory_spy_experience as cli
from tests import market_memory_repo_scan as repo_scan

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-experience.service"
TIMER = DEPLOY / "macro-market-memory-experience.timer"
OPTIONS_SERVICE = DEPLOY / "macro-market-memory-options.service"
RUNTIME_FENCE = DEPLOY / "market-memory-options-runtime-fence.sh"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"
LEGACY_JOBS = ROOT / ".github" / "ci" / "legacy-jobs.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

EXPERIENCE_ROOT = "/var/lib/macro-market-memory/state/experience-v1"
TRUSTED_ROOT = "/var/lib/macro-market-memory/public/trusted-v1"
TECHNICAL_ROOT = "/var/lib/macro-market-memory/state/technicals-v1"
NAMESPACE_ROOT = "/var/lib/macro-market-memory"
MASKED_MARKET_MEMORY_SIBLINGS = {
    "/var/lib/macro-market-memory/public/generations",
    "/var/lib/macro-market-memory/public/objects",
    "/var/lib/macro-market-memory/public/contexts",
    "/var/lib/macro-market-memory/public/queries",
    "/var/lib/macro-market-memory/public/HEAD.json",
    "/var/lib/macro-market-memory/public/store_manifest.json",
    "/var/lib/macro-market-memory/state/sources",
    "/var/lib/macro-market-memory/state/context-projection",
    "/var/lib/macro-market-memory/state/identity-v1",
    "/var/lib/macro-market-memory/state/breadth-v1",
    "/var/lib/macro-market-memory/state/production-record-options-episode-v1",
}
SIBLING_PROFILES = ("source", "context", "identity", "breadth", "technicals")


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
    assert job is not None
    return job.group("body")


def _marked_shell(path: Path, marker: str) -> str:
    source = _text(path)
    begin = f"# BEGIN {marker}\n"
    end = f"# END {marker}"
    assert source.count(begin) == 1
    assert source.count(end) == 1
    return source.split(begin, 1)[1].split(end, 1)[0]


def _run_shell(source: str, *, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", source],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **environment},
    )


_SYSTEMCTL_HARNESS = r"""
systemctl() {
  printf '%s\n' "$*" >> "$EVENT_LOG"
  case "$1" in
    start)
      if [ "$2" = "${FAIL_UNIT:-}" ]; then
        return 23
      fi
      if [ "$2" = macro-market-memory-experience.service ] && \
         [ "${PUBLISH_RECEIPT:-0}" -eq 1 ]; then
        : > "$MARKET_MEMORY_EXPERIENCE_INSTALLATION"
      fi
      ;;
    enable)
      W2C_TIMER_ENABLED=1
      W2C_TIMER_ACTIVE=1
      ;;
    disable)
      W2C_TIMER_ENABLED=0
      W2C_TIMER_ACTIVE=0
      ;;
    is-enabled)
      [ "${W2C_TIMER_ENABLED:-0}" -eq 1 ]
      return
      ;;
    is-active)
      [ "${W2C_TIMER_ACTIVE:-0}" -eq 1 ]
      return
      ;;
  esac
}
"""


def test_experience_cli_authenticates_every_tracked_runtime_input(tmp_path: Path, monkeypatch) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    relative = Path("config/reviewed.json")
    (repository / relative.parent).mkdir()
    (repository / relative).write_text('{"reviewed":true}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "w2c@example.test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "W2C test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", str(relative)], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-qm", "reviewed"], check=True
    )
    monkeypatch.setattr(cli, "_TRACKED_RUNTIME_CLOSURE", (relative.as_posix(),))

    commit = cli._verified_repository_commit(repository)
    assert re.fullmatch(r"[a-f0-9]{40,64}", commit)

    (repository / relative).write_text('{"reviewed":false}\n', encoding="utf-8")
    with pytest.raises(cli.MarketMemoryExperienceCliError, match="differs"):
        cli._verified_repository_commit(repository)

    subprocess.run(
        ["git", "-C", str(repository), "restore", "--source=HEAD", str(relative)],
        check=True,
    )
    alternate = repository / "alternate.json"
    alternate.write_text('{"reviewed":true}\n', encoding="utf-8")
    (repository / relative).unlink()
    (repository / relative).symlink_to(alternate)
    with pytest.raises(cli.MarketMemoryExperienceCliError, match="regular file"):
        cli._verified_repository_commit(repository)


def test_experience_cli_is_the_only_production_writer_and_passes_no_clock(
    monkeypatch, tmp_path: Path
) -> None:
    commit = "a" * 40
    calls: list[tuple[Path, dict[str, object]]] = []
    fake = ModuleType("engine.neuralweb.market_memory_experience_accrual")

    def fake_accrue(repository_root, **kwargs):
        calls.append((Path(repository_root), kwargs))
        return SimpleNamespace(
            registration_id="mmspyexpreg_" + "b" * 64,
            opportunity_ids=("mmspyexpopp_" + "c" * 64,),
            outcome_revision_ids=("mmspyexpout_" + "d" * 64,),
            population_receipt_id="mmspyexppop_" + "e" * 64,
        )

    fake.accrue_spy_experience = fake_accrue
    monkeypatch.setattr(cli, "_verified_repository_commit", lambda root: commit)
    monkeypatch.setitem(
        sys.modules, "engine.neuralweb.market_memory_experience_accrual", fake
    )
    import engine.neuralweb as neuralweb

    monkeypatch.setattr(
        neuralweb, "market_memory_experience_accrual", fake, raising=False
    )
    result = cli.accrue_registered_spy_experience(
        tmp_path,
        experience_root=tmp_path / "experience",
        trusted_root=tmp_path / "trusted",
        technical_root=tmp_path / "technical",
    )

    assert calls == [
        (
            tmp_path.resolve(),
            {
                "experience_root": tmp_path / "experience",
                "trusted_root": tmp_path / "trusted",
                "technical_root": tmp_path / "technical",
                "writer_commit": commit,
            },
        )
    ]
    assert "clock" not in calls[0][1]
    assert result["deployed_commit"] == commit
    assert result["opportunity_ids"] == ["mmspyexpopp_" + "c" * 64]

    production_callers: set[Path] = set()
    for path in repo_scan.production_python_paths():
        called = repo_scan.callee_names(path)
        if (
            "accrue_spy_experience" in called.direct
            or "accrue_spy_experience" in called.attribute
        ):
            production_callers.add(path.relative_to(ROOT))
    assert production_callers == {
        Path("scripts/accrue_market_memory_spy_experience.py")
    }


def test_experience_cli_exposes_credential_free_read_only_attestations(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    commit = "a" * 40
    calls: list[tuple[str, Path, dict[str, object]]] = []
    fake = ModuleType("engine.neuralweb.market_memory_experience_accrual")

    def verify_installation(repository_root, **kwargs):
        calls.append(("installation", Path(repository_root), kwargs))
        return {"installation_id": "mmspyexpinstall_" + "b" * 64}

    def verify_terminal(repository_root, **kwargs):
        calls.append(("terminal", Path(repository_root), kwargs))
        return {"schema": "market_memory.spy_experience_terminal_marker.v1"}

    fake.verify_experience_installation = verify_installation
    fake.verify_terminal_ledger = verify_terminal
    monkeypatch.setattr(cli, "_verified_repository_commit", lambda root: commit)
    monkeypatch.setitem(
        sys.modules, "engine.neuralweb.market_memory_experience_accrual", fake
    )
    import engine.neuralweb as neuralweb

    monkeypatch.setattr(
        neuralweb, "market_memory_experience_accrual", fake, raising=False
    )
    experience_root = tmp_path / "experience"
    installation = cli.verify_registered_spy_experience_installation(
        tmp_path, experience_root=experience_root
    )
    terminal = cli.verify_registered_spy_experience_terminal(
        tmp_path, experience_root=experience_root
    )

    assert calls == [
        (
            "installation",
            tmp_path.resolve(),
            {
                "experience_root": experience_root,
                "expected_writer_commit": None,
            },
        ),
        (
            "terminal",
            tmp_path.resolve(),
            {
                "experience_root": experience_root,
                "expected_writer_commit": None,
            },
        ),
    ]
    assert installation["deployed_commit"] == commit
    assert terminal is not None and terminal["deployed_commit"] == commit

    monkeypatch.setattr(
        cli, "verify_registered_spy_experience_terminal", lambda *args, **kwargs: None
    )
    assert (
        cli.main(
            [
                "--repository-root",
                str(tmp_path),
                "--experience-root",
                str(experience_root),
                "--verify-terminal",
            ]
        )
        == 3
    )

    def forged(*args, **kwargs):
        raise RuntimeError("forged terminal census")

    monkeypatch.setattr(cli, "verify_registered_spy_experience_terminal", forged)
    assert (
        cli.main(
            [
                "--repository-root",
                str(tmp_path),
                "--experience-root",
                str(experience_root),
                "--verify-terminal",
            ]
        )
        == 2
    )
    assert "forged terminal census" in capsys.readouterr().err


def test_experience_cli_reports_a_fresh_store_as_open_without_mutation(
    monkeypatch, tmp_path: Path
) -> None:
    experience_root = tmp_path / "state" / "experience-v1"
    experience_root.mkdir(parents=True)
    monkeypatch.setattr(
        cli, "_verified_repository_commit", lambda root: "a" * 40
    )

    assert (
        cli.verify_registered_spy_experience_terminal(
            ROOT, experience_root=experience_root
        )
        is None
    )
    assert list(experience_root.iterdir()) == []
    assert (
        cli.main(
            [
                "--repository-root",
                str(ROOT),
                "--experience-root",
                str(experience_root),
                "--verify-terminal",
            ]
        )
        == 3
    )
    assert list(experience_root.iterdir()) == []


def test_experience_cli_closure_binds_contracts_config_calendar_and_owner_readers() -> None:
    closure = set(cli._TRACKED_RUNTIME_CLOSURE)
    assert {
        "app/requirements.txt",
        "scripts/__init__.py",
        "engine/neuralweb/market_memory_experience_accrual.py",
        "engine/neuralweb/market_memory_trusted.py",
        "engine/neuralweb/market_memory_technical_store.py",
        "engine/__init__.py",
        "engine/neuralweb/__init__.py",
        "config/market_memory_spy_experience_registration.v1.json",
        "contracts/market_memory/spy_experience_registration.v1.schema.json",
        "contracts/market_memory/spy_experience_opportunity.v1.schema.json",
        "contracts/market_memory/spy_experience_outcome_revision.v1.schema.json",
        "contracts/market_memory/spy_experience_population_receipt.v1.schema.json",
        "lib/__init__.py",
        "lib/nyse_calendar.py",
    } <= closure


def test_experience_service_is_network_dark_credential_free_and_path_exact() -> None:
    service = _text(SERVICE)
    expected_exec = (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.accrue_market_memory_spy_experience --repository-root /opt/macro "
        f"--experience-root {EXPERIENCE_ROOT} --trusted-root {TRUSTED_ROOT} "
        f"--technical-root {TECHNICAL_ROOT}"
    )
    assert "Type=oneshot" in service
    assert expected_exec in service
    assert "PrivateNetwork=true" in service
    assert _setting_values(service, "RestrictAddressFamilies") == ["AF_UNIX"]
    assert _setting_values(service, "TemporaryFileSystem") == [
        "/var/lib/macro-market-memory:ro"
    ]
    assert _setting_values(service, "BindReadOnlyPaths") == [
        TRUSTED_ROOT,
        TECHNICAL_ROOT,
    ]
    assert _setting_values(service, "BindPaths") == [EXPERIENCE_ROOT]
    assert "Environment=" not in service
    assert "EnvironmentFile=" not in service
    assert "LoadCredential=" not in service
    assert _setting_values(service, "ReadOnlyPaths") == [
        "/opt/macro",
        TRUSTED_ROOT,
        TECHNICAL_ROOT,
    ]
    assert _setting_values(service, "ReadWritePaths") == [EXPERIENCE_ROOT]
    assert "AF_INET" not in service
    assert "Wants=network-online.target" not in service
    for protected in (
        "/var/lib/macro-market-memory-options",
        "/etc/macro-market-memory-options",
        "/var/lib/macro-market-memory/state/sources",
        "/var/lib/macro-market-memory/state/context-projection",
        "/var/lib/macro-market-memory/state/identity-v1",
        "/var/lib/macro-market-memory/state/breadth-v1",
        "/var/lib/macro-api",
        "/var/lib/macro-biocatalyst",
        "/var/lib/macro-codex",
        "/var/lib/macro-live",
        "/etc/macro-api.env",
        "/etc/macro-live.env",
        "/etc/macro-market-memory.env",
        "/etc/ssl/cf-origin.key",
    ):
        assert re.search(
            rf"^InaccessiblePaths=-?{re.escape(protected)}$", service, re.MULTILINE
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
    timeout = int(_setting_values(service, "TimeoutStartSec")[0])
    assert timeout > 15 * 60
    assert timeout >= 31 * 30 + 120
    assert _setting_values(service, "ConditionPathExists") == []

    for path in (ROOT / "app").rglob("*.py"):
        source = _text(path)
        assert "market_memory_experience_accrual" not in source
        assert "MARKET_MEMORY_EXPERIENCE" not in source


def test_experience_namespace_tolerates_exact_masked_siblings() -> None:
    service = _text(SERVICE)
    inaccessible = _setting_values(service, "InaccessiblePaths")

    # systemd applies the root tmpfs before its sorted nested path masks.  Every
    # unbound sibling is therefore intentionally absent at namespace setup.
    # Leading "-" tolerates that absence but still masks a target when present.
    nested_masks = {
        value
        for value in inaccessible
        if value.removeprefix("-").startswith("/var/lib/macro-market-memory/")
    }
    assert nested_masks == {
        f"-{path}" for path in MASKED_MARKET_MEMORY_SIBLINGS
    }

    # The authenticated owner roots remain mandatory bind inputs, and the
    # empty hierarchy mount remains the default deny for every unbound sibling.
    assert _setting_values(service, "TemporaryFileSystem") == [
        "/var/lib/macro-market-memory:ro"
    ]
    assert _setting_values(service, "BindReadOnlyPaths") == [
        TRUSTED_ROOT,
        TECHNICAL_ROOT,
    ]
    assert _setting_values(service, "BindPaths") == [EXPERIENCE_ROOT]
    assert not any(
        value.startswith("-")
        for setting in ("BindReadOnlyPaths", "BindPaths")
        for value in _setting_values(service, setting)
    )

    # External deny anchors are real, preprovisioned directories and remain
    # mandatory.  Optionalizing them would weaken deployment drift detection.
    assert "/var/lib/macro-market-memory-options" in inaccessible
    assert "/etc/macro-market-memory-options" in inaccessible
    assert "-/var/lib/macro-market-memory-options" not in inaccessible
    assert "-/etc/macro-market-memory-options" not in inaccessible

    # Audit all related units too: none combines the empty-tree namespace with
    # nested path masks, so none needs the same missing-target treatment.
    for profile in (*SIBLING_PROFILES, "production-records", "options"):
        sibling = _text(DEPLOY / f"macro-market-memory-{profile}.service")
        assert _setting_values(sibling, "TemporaryFileSystem") == []


def test_experience_timer_is_exact_and_calendar_is_not_the_denominator() -> None:
    timer = _text(TIMER)
    assert _setting_values(timer, "ConditionPathExists") == []
    assert "OnCalendar=*-*-* 04:30:00 UTC" in timer
    assert "AccuracySec=1s" in timer
    assert "RandomizedDelaySec=0" in timer
    assert "Persistent=true" in timer
    assert "OnBootSec=" not in timer
    assert "Unit=macro-market-memory-experience.service" in timer
    assert "never this timer" in timer


def test_only_option_writer_is_mutually_exclusive_with_experience() -> None:
    experience = _text(SERVICE)
    options = _text(OPTIONS_SERVICE)
    expected_owners = {
        f"macro-market-memory-{profile}.service" for profile in SIBLING_PROFILES
    }
    assert _setting_values(experience, "Conflicts") == [
        "macro-market-memory-options.service"
    ]
    assert expected_owners <= set(_setting_values(experience, "After")[0].split())
    assert "macro-market-memory-options.service" not in _setting_values(
        experience, "After"
    )[0].split()
    assert "macro-market-memory-experience.service" in _setting_values(
        options, "Conflicts"
    )[0].split()
    assert "macro-market-memory-experience.service" in _setting_values(
        options, "After"
    )[0].split()
    assert "source context identity breadth technicals experience" in _text(
        RUNTIME_FENCE
    )

    for profile in (*SIBLING_PROFILES, "production-records"):
        sibling = _text(DEPLOY / f"macro-market-memory-{profile}.service")
        sibling_conflicts = set(
            " ".join(_setting_values(sibling, "Conflicts")).split()
        )
        assert "macro-market-memory-experience.service" not in sibling_conflicts

    for profile in SIBLING_PROFILES:
        sibling = _text(DEPLOY / f"macro-market-memory-{profile}.service")
        assert f"InaccessiblePaths={EXPERIENCE_ROOT}" in sibling
    assert f"InaccessiblePaths={EXPERIENCE_ROOT}" in options


def test_setup_and_updater_install_attest_run_and_arm_experience_lane() -> None:
    for script in (SETUP, UPDATE, RUNTIME_FENCE):
        subprocess.run(["bash", "-n", str(script)], check=True)
    setup = _text(SETUP)
    update = _text(UPDATE)

    setup_verify = setup.index("systemd-analyze verify")
    required_namespace_paths = (
        NAMESPACE_ROOT,
        TRUSTED_ROOT,
        TECHNICAL_ROOT,
        EXPERIENCE_ROOT,
    )
    for path in required_namespace_paths:
        assert setup.index(f"install -d -m 0700 {path}\n") < setup_verify
    for name in (
        "macro-market-memory-experience.service",
        "macro-market-memory-experience.timer",
    ):
        assert name in setup[:setup_verify]
        assert f'"$APP_DIR/app/deploy/{name}"' in setup[setup_verify:]
        assert (
            f'install -m 0644 "$APP_DIR/app/deploy/{name}" '
            f"/etc/systemd/system/{name}"
        ) in setup
    assert "for boundary_profile in source context identity breadth technicals experience" in setup
    assert "systemctl start macro-market-memory-experience.service" in setup
    assert "systemctl enable --now macro-market-memory-experience.timer" in setup
    assert "--verify-installation" in setup
    assert "--verify-terminal" in setup
    assert "mm_loaded_unit_ready" in setup
    assert "NeedDaemonReload" in setup

    update_verify = update.index(
        'systemd-analyze verify "$APP_DIR/app/deploy/macro-api.service"'
    )
    block_start = update.index("MARKET_MEMORY_EXPERIENCE_UNIT_UPDATED=0")
    block_end = update.index("# W1B.5 private", block_start)
    block = update[block_start:block_end]
    for path in required_namespace_paths:
        assert (
            update.index(f"install -d -m 0700 {path}\n")
            < update_verify
            < block_start
        )
    for token in (
        "macro-market-memory-experience.service",
        "macro-market-memory-experience.timer",
        "mm_reviewed_unit_file_ready",
        "systemd-analyze verify",
        "systemctl daemon-reload",
        "w2c_reconcile_timer",
        "systemctl start macro-market-memory-experience.service",
        "MARKET_MEMORY_EXPERIENCE_RUN_NEEDED",
        "w2c_verify_installation",
        "w2c_terminal_ledger_state",
    ):
        assert token in block
    assert "systemctl restart macro-market-memory-experience.timer" not in block
    assert "for profile in source context identity breadth technicals experience" in update
    assert "for RECIPROCAL_PROFILE in source context identity breadth technicals" in update
    finalization = update.split("# BEGIN W1B5_TIMER_FINALIZATION\n", 1)[1].split(
        "# END W1B5_TIMER_FINALIZATION", 1
    )[0]
    assert "MARKET_MEMORY_EXPERIENCE_RUN_NEEDED" in finalization
    assert "systemctl start macro-market-memory-experience.service" in finalization
    assert "w2c_reconcile_timer" in finalization
    assert "MARKET_MEMORY_EXPERIENCE_ATTESTED" in finalization
    reciprocal = re.search(r"OPTIONS_RECIPROCAL_CLOSURE_REGEX='([^']+)'", update)
    assert reciprocal is not None
    trigger = re.compile(reciprocal.group(1))
    for path in cli._TRACKED_RUNTIME_CLOSURE:
        assert trigger.fullmatch(path), f"pre-reset stop closure misses {path}"

    runtime = re.search(
        r"MARKET_MEMORY_EXPERIENCE_RUNTIME_REGEX='([^']+)'", update
    )
    assert runtime is not None
    runtime_trigger = re.compile(runtime.group(1))
    for path in cli._TRACKED_RUNTIME_CLOSURE:
        assert runtime_trigger.fullmatch(path), f"W2C run trigger misses {path}"


@pytest.mark.parametrize(
    ("fail_unit", "publish_receipt", "expected_status", "expected_units"),
    (
        (
            "",
            "1",
            0,
            (
                "macro-market-memory-source.service",
                "macro-market-memory-context.service",
                "macro-market-memory-technicals.service",
                "macro-market-memory-experience.service",
            ),
        ),
        (
            "macro-market-memory-context.service",
            "1",
            1,
            (
                "macro-market-memory-source.service",
                "macro-market-memory-context.service",
            ),
        ),
        (
            "",
            "0",
            1,
            (
                "macro-market-memory-source.service",
                "macro-market-memory-context.service",
                "macro-market-memory-technicals.service",
                "macro-market-memory-experience.service",
            ),
        ),
    ),
)
def test_setup_executes_owner_chain_before_critical_preactivation_installation(
    tmp_path: Path,
    fail_unit: str,
    publish_receipt: str,
    expected_status: int,
    expected_units: tuple[str, ...],
) -> None:
    state = tmp_path / "experience"
    state.mkdir()
    event_log = tmp_path / "events"
    source = f"""
set -euo pipefail
MARKET_MEMORY_EXPERIENCE_ROOT="$W2C_TEST_ROOT"
MARKET_MEMORY_EXPERIENCE_INSTALLATION="$MARKET_MEMORY_EXPERIENCE_ROOT/registration_installation.json"
MARKET_MEMORY_EXPERIENCE_TERMINAL="$MARKET_MEMORY_EXPERIENCE_ROOT/TERMINAL.json"
log() {{ printf '%s\n' "$*" >&2; }}
{_SYSTEMCTL_HARNESS}
{_marked_shell(SETUP, "W2C_DEPLOY_HELPERS")}
w2c_terminal_ledger_state() {{ return "${{W2C_TERMINAL_VERIFY_STATUS:-3}}"; }}
w2c_verify_installation() {{
  [ -f "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ] &&
    [ ! -L "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ]
}}
{_marked_shell(SETUP, "W2C_PREACTIVATION_INSTALLATION")}
"""
    result = _run_shell(
        source,
        environment={
            "W2C_TEST_ROOT": str(state),
            "EVENT_LOG": str(event_log),
            "FAIL_UNIT": fail_unit,
            "PUBLISH_RECEIPT": publish_receipt,
            "W2C_TERMINAL_VERIFY_STATUS": "3",
        },
    )
    assert result.returncode == expected_status, result.stderr
    events = event_log.read_text(encoding="utf-8").splitlines()
    assert events == [f"start {unit}" for unit in expected_units]
    if fail_unit:
        assert "macro-market-memory-experience.service" not in "\n".join(events)
    if publish_receipt == "0":
        assert "authentic preactivation installation receipt" in result.stderr


def test_updater_deferred_replay_is_ordered_and_owner_failure_suppresses_w2c(
    tmp_path: Path,
) -> None:
    helpers = _marked_shell(UPDATE, "W2C_DEPLOY_HELPERS")
    replay = _marked_shell(UPDATE, "W2C_DEFERRED_REPLAY")

    def run(*, fail_unit: str, installation_required: int, publish: str):
        state = tmp_path / f"run-{fail_unit or 'ok'}-{installation_required}-{publish}"
        state.mkdir()
        event_log = state / "events"
        source = f"""
set -euo pipefail
MARKET_MEMORY_EXPERIENCE_ROOT="$W2C_TEST_ROOT"
MARKET_MEMORY_EXPERIENCE_INSTALLATION="$MARKET_MEMORY_EXPERIENCE_ROOT/registration_installation.json"
MARKET_MEMORY_EXPERIENCE_TERMINAL="$MARKET_MEMORY_EXPERIENCE_ROOT/TERMINAL.json"
API_DEPS_OK=1
MARKET_MEMORY_EXPERIENCE_RUN_NEEDED=1
MARKET_MEMORY_EXPERIENCE_INSTALLATION_REQUIRED={installation_required}
MARKET_MEMORY_EXPERIENCE_TERMINAL_STATE=3
{_SYSTEMCTL_HARNESS}
{helpers}
w2c_terminal_ledger_state() {{ return 3; }}
w2c_verify_installation() {{
  [ -f "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ] &&
    [ ! -L "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ]
}}
{replay}
"""
        result = _run_shell(
            source,
            environment={
                "W2C_TEST_ROOT": str(state),
                "EVENT_LOG": str(event_log),
                "FAIL_UNIT": fail_unit,
                "PUBLISH_RECEIPT": publish,
            },
        )
        return result, event_log.read_text(encoding="utf-8").splitlines()

    success, success_events = run(
        fail_unit="", installation_required=1, publish="1"
    )
    assert success.returncode == 0, success.stderr
    assert success_events == [
        "start macro-market-memory-source.service",
        "start macro-market-memory-context.service",
        "start macro-market-memory-technicals.service",
        "start macro-market-memory-experience.service",
    ]

    failed, failed_events = run(
        fail_unit="macro-market-memory-context.service",
        installation_required=0,
        publish="1",
    )
    assert failed.returncode == 1, failed.stderr
    assert failed_events == [
        "start macro-market-memory-source.service",
        "start macro-market-memory-context.service",
    ]
    assert all("experience.service" not in event for event in failed_events)

    missing, _ = run(fail_unit="", installation_required=1, publish="0")
    assert missing.returncode == 1
    assert "installation attestation failed" in missing.stderr


def test_updater_no_diff_attests_and_rearm_requires_synchronous_owner_replay(
    tmp_path: Path,
) -> None:
    helpers = _marked_shell(UPDATE, "W2C_DEPLOY_HELPERS")
    attestation = _marked_shell(UPDATE, "W2C_RUNTIME_ATTESTATION")

    def run(
        name: str,
        *,
        terminal_status: int,
        installation_valid: int,
        enabled: int,
        active: int,
        unit_updated: int = 0,
    ) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        state = tmp_path / name
        state.mkdir()
        (state / "registration_installation.json").write_text(
            "{}\n", encoding="utf-8"
        )
        event_log = state / "events"
        source = f"""
set -euo pipefail
MARKET_MEMORY_EXPERIENCE_ROOT="$W2C_TEST_ROOT"
MARKET_MEMORY_EXPERIENCE_INSTALLATION="$MARKET_MEMORY_EXPERIENCE_ROOT/registration_installation.json"
MARKET_MEMORY_EXPERIENCE_TERMINAL="$MARKET_MEMORY_EXPERIENCE_ROOT/TERMINAL.json"
MARKET_MEMORY_EXPERIENCE_RUNTIME_REGEX='^runtime-change$'
MARKET_MEMORY_EXPERIENCE_UNIT_UPDATED={unit_updated}
RECIPROCAL_TIMERS_PAUSED=0
API_DEPS_OK=1
CHANGED=''
W2C_TIMER_ENABLED={enabled}
W2C_TIMER_ACTIVE={active}
{_SYSTEMCTL_HARNESS}
{helpers}
w2c_terminal_ledger_state() {{
  printf '%s\n' verify-terminal >> "$EVENT_LOG"
  return {terminal_status}
}}
w2c_verify_installation() {{
  printf '%s\n' verify-installation >> "$EVENT_LOG"
  [ {installation_valid} -eq 1 ]
}}
{attestation}
"""
        result = _run_shell(
            source,
            environment={"W2C_TEST_ROOT": str(state), "EVENT_LOG": str(event_log)},
        )
        events = event_log.read_text(encoding="utf-8").splitlines()
        return result, events

    no_diff, no_diff_events = run(
        "no-diff",
        terminal_status=3,
        installation_valid=1,
        enabled=1,
        active=1,
    )
    assert no_diff.returncode == 0, no_diff.stderr
    assert "verify-installation" in no_diff_events
    assert not any(event.startswith(("start ", "enable ", "disable ")) for event in no_diff_events)

    rearm, rearm_events = run(
        "rearm",
        terminal_status=3,
        installation_valid=1,
        enabled=0,
        active=0,
    )
    assert rearm.returncode == 0, rearm.stderr
    owner_events = [
        "start macro-market-memory-source.service",
        "start macro-market-memory-context.service",
        "start macro-market-memory-technicals.service",
    ]
    for event in owner_events:
        assert event in rearm_events
    enable = "enable --now macro-market-memory-experience.timer"
    assert enable in rearm_events
    assert rearm_events.index(owner_events[-1]) < rearm_events.index(enable)
    assert "start macro-market-memory-experience.service" not in rearm_events

    unit_repair, unit_repair_events = run(
        "unit-repair",
        terminal_status=3,
        installation_valid=1,
        enabled=1,
        active=1,
        unit_updated=1,
    )
    assert unit_repair.returncode == 0, unit_repair.stderr
    writer = "start macro-market-memory-experience.service"
    assert writer in unit_repair_events
    assert unit_repair_events.index(owner_events[-1]) < unit_repair_events.index(
        writer
    )
    assert unit_repair_events.index(writer) < len(unit_repair_events) - 1
    assert "verify-installation" in unit_repair_events[
        unit_repair_events.index(writer) + 1 :
    ]

    invalid, invalid_events = run(
        "invalid-terminal",
        terminal_status=2,
        installation_valid=1,
        enabled=1,
        active=1,
    )
    assert invalid.returncode == 1
    assert invalid_events == ["verify-terminal"]

    forged, forged_events = run(
        "forged-terminal",
        terminal_status=0,
        installation_valid=0,
        enabled=1,
        active=1,
    )
    assert forged.returncode == 1
    assert not any(event.startswith("disable ") for event in forged_events)

    sealed, sealed_events = run(
        "sealed",
        terminal_status=0,
        installation_valid=1,
        enabled=1,
        active=1,
    )
    assert sealed.returncode == 0, sealed.stderr
    assert "disable --now macro-market-memory-experience.timer" in sealed_events
    assert not any(event.startswith("start ") for event in sealed_events)


def test_terminal_installation_path_never_restarts_owners_or_w2c(
    tmp_path: Path,
) -> None:
    state = tmp_path / "experience"
    state.mkdir()
    (state / "registration_installation.json").write_text("{}\n", encoding="utf-8")
    (state / "TERMINAL.json").write_text("{}\n", encoding="utf-8")
    event_log = tmp_path / "events"
    source = f"""
set -euo pipefail
MARKET_MEMORY_EXPERIENCE_ROOT="$W2C_TEST_ROOT"
MARKET_MEMORY_EXPERIENCE_INSTALLATION="$MARKET_MEMORY_EXPERIENCE_ROOT/registration_installation.json"
MARKET_MEMORY_EXPERIENCE_TERMINAL="$MARKET_MEMORY_EXPERIENCE_ROOT/TERMINAL.json"
log() {{ printf '%s\n' "$*" >&2; }}
{_SYSTEMCTL_HARNESS}
{_marked_shell(SETUP, "W2C_DEPLOY_HELPERS")}
w2c_terminal_ledger_state() {{ return 0; }}
w2c_verify_installation() {{
  [ -f "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ] &&
    [ ! -L "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ]
}}
{_marked_shell(SETUP, "W2C_PREACTIVATION_INSTALLATION")}
"""
    result = _run_shell(
        source,
        environment={"W2C_TEST_ROOT": str(state), "EVENT_LOG": str(event_log)},
    )
    assert result.returncode == 0, result.stderr
    assert not event_log.exists()


def test_terminal_marker_executable_timer_reconciliation_is_fail_closed(
    tmp_path: Path,
) -> None:
    helpers = _marked_shell(UPDATE, "W2C_DEPLOY_HELPERS")

    def run(
        state: Path, *, enabled: int, active: int, terminal_status: int
    ):
        event_log = state / "events"
        source = f"""
set -euo pipefail
MARKET_MEMORY_EXPERIENCE_ROOT="$W2C_TEST_ROOT"
MARKET_MEMORY_EXPERIENCE_INSTALLATION="$MARKET_MEMORY_EXPERIENCE_ROOT/registration_installation.json"
MARKET_MEMORY_EXPERIENCE_TERMINAL="$MARKET_MEMORY_EXPERIENCE_ROOT/TERMINAL.json"
W2C_TIMER_ENABLED={enabled}
W2C_TIMER_ACTIVE={active}
W2C_OWNER_REPLAY_READY=1
{_SYSTEMCTL_HARNESS}
{helpers}
w2c_terminal_ledger_state() {{ return {terminal_status}; }}
w2c_verify_installation() {{
  [ -f "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ] &&
    [ ! -L "$MARKET_MEMORY_EXPERIENCE_INSTALLATION" ]
}}
w2c_reconcile_timer
"""
        result = _run_shell(
            source,
            environment={
                "W2C_TEST_ROOT": str(state),
                "EVENT_LOG": str(event_log),
            },
        )
        events = (
            event_log.read_text(encoding="utf-8").splitlines()
            if event_log.exists()
            else []
        )
        return result, events

    sealed = tmp_path / "sealed"
    sealed.mkdir()
    (sealed / "TERMINAL.json").write_text("{}\n", encoding="utf-8")
    sealed_result, sealed_events = run(
        sealed, enabled=1, active=1, terminal_status=0
    )
    assert sealed_result.returncode == 0, sealed_result.stderr
    assert sealed_events[0] == "disable --now macro-market-memory-experience.timer"
    assert not any(event.startswith("enable ") for event in sealed_events)

    open_state = tmp_path / "open"
    open_state.mkdir()
    (open_state / "registration_installation.json").write_text(
        "{}\n", encoding="utf-8"
    )
    open_result, open_events = run(
        open_state, enabled=0, active=0, terminal_status=3
    )
    assert open_result.returncode == 0, open_result.stderr
    assert "enable --now macro-market-memory-experience.timer" in open_events

    forged = tmp_path / "forged"
    forged.mkdir()
    target = forged / "target"
    target.write_text("{}\n", encoding="utf-8")
    (forged / "TERMINAL.json").symlink_to(target)
    forged_result, forged_events = run(
        forged, enabled=1, active=1, terminal_status=2
    )
    assert forged_result.returncode != 0
    assert forged_events == []
    assert "terminal state is invalid" in forged_result.stderr


def test_market_memory_ci_owns_every_experience_contract_and_trigger() -> None:
    body = _legacy_job_body(_text(LEGACY_JOBS), "market-memory-contract")
    workflow = _text(CI_WORKFLOW)
    assert re.findall(
        r"^    timeout-minutes: ([0-9]+)$", body, re.MULTILINE
    ) == ["15"]
    for test in (
        "tests/test_market_memory_experience_accrual.py",
        "tests/test_market_memory_experience_deploy.py",
    ):
        assert test in body
        assert f'      - "{test}"' in workflow
    for path in (
        "engine/neuralweb/market_memory_experience_accrual.py",
        "scripts/accrue_market_memory_spy_experience.py",
        "config/market_memory_spy_experience_registration.v1.json",
        "contracts/market_memory/spy_experience_registration.v1.schema.json",
        "contracts/market_memory/spy_experience_opportunity.v1.schema.json",
        "contracts/market_memory/spy_experience_outcome_revision.v1.schema.json",
        "contracts/market_memory/spy_experience_population_receipt.v1.schema.json",
        "app/deploy/macro-market-memory-experience.service",
        "app/deploy/macro-market-memory-experience.timer",
    ):
        assert f'      - "{path}"' in workflow
