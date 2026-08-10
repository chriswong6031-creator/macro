"""Deployment and serving-boundary guards for the W1B.1 trusted canary."""

from __future__ import annotations

import ast
import re
import subprocess
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.neuralweb import market_memory_trusted as trusted
from scripts import project_market_memory_context as writer_module

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-context.service"
TIMER = DEPLOY / "macro-market-memory-context.timer"
API_SERVICE = DEPLOY / "macro-api.service"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"
WRITER = ROOT / "scripts" / "project_market_memory_context.py"
API_ROUTER = ROOT / "app" / "market_memory.py"

PUBLIC_ROOT = "/var/lib/macro-market-memory/public/trusted-v1"
PRIVATE_ROOT = "/var/lib/macro-market-memory/state/context-projection"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _setting_values(unit: str, setting: str) -> list[str]:
    prefix = f"{setting}="
    return [
        line.removeprefix(prefix)
        for line in unit.splitlines()
        if line.startswith(prefix)
    ]


def _context_update_block() -> str:
    update = _text(UPDATE)
    start = update.index("# W1B.1 trusted context publisher:")
    end = update.index("# macro-api: restart ONLY", start)
    return update[start:end]


def _api_restart_block() -> str:
    update = _text(UPDATE)
    start = update.index("# macro-api: restart ONLY")
    end = update.index("# Live-plane systemd definitions", start)
    return update[start:end]


def _production_calls(function_name: str) -> set[Path]:
    callers: set[Path] = set()
    for parent in (ROOT / "app", ROOT / "engine", ROOT / "scripts"):
        for path in parent.rglob("*.py"):
            tree = ast.parse(_text(path), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                called = node.func
                if (
                    isinstance(called, ast.Name)
                    and called.id == function_name
                    or isinstance(called, ast.Attribute)
                    and called.attr == function_name
                ):
                    callers.add(path.relative_to(ROOT))
    return callers


def test_context_deploy_shell_scripts_have_valid_syntax() -> None:
    subprocess.run(["bash", "-n", str(SETUP)], check=True)
    subprocess.run(["bash", "-n", str(UPDATE)], check=True)


def test_context_service_is_network_dark_credential_free_and_exactly_scoped() -> None:
    service = _text(SERVICE)

    assert "Type=oneshot" in service
    assert "WorkingDirectory=/opt/macro" in service
    assert (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.project_market_memory_context --repository-root /opt/macro "
        f"--public-store-root {PUBLIC_ROOT} "
        f"--private-evidence-root {PRIVATE_ROOT}"
    ) in service
    assert "PrivateNetwork=true" in service
    assert _setting_values(service, "RestrictAddressFamilies") == ["AF_UNIX"]
    assert "AF_INET" not in service
    assert "Environment=" not in service
    assert "EnvironmentFile=" not in service

    assert set(_setting_values(service, "ReadWritePaths")) == {
        PUBLIC_ROOT,
        PRIVATE_ROOT,
    }
    assert _setting_values(service, "ReadOnlyPaths") == ["/opt/macro"]
    assert "ReadWritePaths=/var/lib/macro-market-memory/public\n" not in service
    assert "ReadWritePaths=/var/lib/macro-market-memory/state\n" not in service
    assert "InaccessiblePaths=/var/lib/macro-market-memory/state/sources" in service

    for protected in (
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


def test_context_timer_is_an_explicit_bounded_retry_contract() -> None:
    service = _text(SERVICE)
    timer = _text(TIMER)

    assert "After=local-fs.target" in service
    assert "After=network.target" not in service
    timeout = re.search(r"^TimeoutStartSec=(\d+)$", service, re.MULTILINE)
    assert timeout is not None
    assert 0 < int(timeout.group(1)) <= 180
    assert "WantedBy=multi-user.target" in service

    assert "OnBootSec=9min" in timer
    assert "OnCalendar=*-*-* *:17:00 UTC" in timer
    assert "AccuracySec=1min" in timer
    assert "RandomizedDelaySec=120s" in timer
    assert "Persistent=true" in timer
    assert "Unit=macro-market-memory-context.service" in timer
    assert "WantedBy=timers.target" in timer


def test_api_can_only_read_public_context_and_cannot_see_writer_state() -> None:
    service = _text(API_SERVICE)

    assert (
        "Environment=MARKET_MEMORY_CONTEXT_STORE_DIR="
        "/var/lib/macro-market-memory/public"
    ) in service
    assert "ReadOnlyPaths=/var/lib/macro-market-memory/public" in service
    assert "ReadOnlyPaths=-/var/lib/macro-market-memory/public" not in service
    assert "InaccessiblePaths=/var/lib/macro-market-memory/state" in service
    assert "InaccessiblePaths=-/var/lib/macro-market-memory/state" not in service
    assert "InaccessiblePaths=-/etc/macro-market-memory.env" in service
    assert "ReadWritePaths=/var/lib/macro-market-memory" not in service
    assert "scripts.project_market_memory_context" not in service


def test_setup_provisions_then_initializes_the_context_lane_before_api_start() -> None:
    setup = _text(SETUP)
    required_directories = (
        "/var/lib/macro-market-memory",
        "/var/lib/macro-market-memory/public",
        PUBLIC_ROOT,
        "/var/lib/macro-market-memory/state",
        "/var/lib/macro-market-memory/state/sources",
        PRIVATE_ROOT,
    )
    for directory in required_directories:
        assert f"install -d -m 0700 {directory}" in setup

    service_source = '"$APP_DIR/app/deploy/macro-market-memory-context.service"'
    timer_source = '"$APP_DIR/app/deploy/macro-market-memory-context.timer"'
    assert service_source in setup
    assert timer_source in setup
    assert (
        'install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-context.service" '
        "/etc/systemd/system/macro-market-memory-context.service"
    ) in setup
    assert (
        'install -m 0644 "$APP_DIR/app/deploy/macro-market-memory-context.timer" '
        "/etc/systemd/system/macro-market-memory-context.timer"
    ) in setup
    assert setup.index(f"install -d -m 0700 {PRIVATE_ROOT}") < setup.index(
        "systemd-analyze verify"
    )
    assert setup.index("systemd-analyze verify") < setup.index(
        "systemctl daemon-reload"
    )
    assert setup.index("systemctl daemon-reload") < setup.index(
        "systemctl start macro-market-memory-context.service"
    )
    assert setup.index(
        "systemctl start macro-market-memory-context.service"
    ) < setup.index("systemctl restart macro-api")
    assert "systemctl enable --now macro-market-memory-context.timer" in setup


def test_update_verifies_installs_arms_and_immediately_reprojects() -> None:
    update = _text(UPDATE)
    block = _context_update_block()

    for directory in (PUBLIC_ROOT, PRIVATE_ROOT):
        assert f"install -d -m 0700 {directory}" in update
    assert update.index(f"install -d -m 0700 {PRIVATE_ROOT}") < update.index(
        'systemd-analyze verify "$APP_DIR/app/deploy/macro-api.service"'
    )

    assert "MARKET_MEMORY_CONTEXT_UNIT_SOURCES=(" in block
    assert 'systemd-analyze verify "${MARKET_MEMORY_CONTEXT_UNIT_SOURCES[@]}"' in block
    assert 'install -m 0644 "$UNIT_SOURCE" "/etc/systemd/system/$UNIT"' in block
    assert "systemctl daemon-reload" in block
    assert "systemctl enable --now macro-market-memory-context.timer" in block
    assert "MARKET_MEMORY_CONTEXT_RUN_NEEDED=0" in block
    assert 'if [ "$API_DEPS_OK" -ne 1 ]; then' in block
    assert "systemctl start macro-market-memory-context.service" in block
    assert "systemctl restart macro-market-memory-context.service" not in block

    for trigger in (
        r"scripts/project_market_memory_context\.py",
        r"engine/neuralweb/market_memory(_pit|_identity|_projection|_trusted)?\.py",
        r"macro_regime_snapshot|macro_regime_feature_object|trusted_capture_receipt",
        r"config/market_memory_canary\.v1\.json",
        r"engine/run\.py",
        r"data/regime/latest\.json",
    ):
        assert trigger in block


def test_projector_is_the_only_production_writer_and_uses_canonical_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _text(WRITER)

    assert _production_calls("initialize_trusted_store") == {
        Path("scripts/project_market_memory_context.py")
    }
    assert _production_calls("capture_trusted_regime_context") == {
        Path("scripts/project_market_memory_context.py")
    }
    assert 'root / "data" / "regime" / "latest.json"' in writer
    assert 'root / "config" / "market_memory_canary.v1.json"' in writer
    assert "read_verified_macro_regime_bytes(" in writer
    assert "_repository_commit(root)" in writer

    monkeypatch.delenv("MARKET_MEMORY_TRUSTED_STORE_DIR", raising=False)
    monkeypatch.delenv("MARKET_MEMORY_CONTEXT_PROJECTION_DIR", raising=False)
    assert (
        trusted.default_trusted_store_root("/opt/macro") == Path(PUBLIC_ROOT).resolve()
    )
    assert (
        trusted.default_private_evidence_root("/opt/macro")
        == Path(PRIVATE_ROOT).resolve()
    )


def _stub_writer_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    raw_body: bytes = b"raw",
    config: bytes = b"config",
) -> None:
    monkeypatch.setattr(
        writer_module.market_memory_trusted,
        "initialize_trusted_store",
        lambda _root: {},
    )
    monkeypatch.setattr(
        writer_module.market_memory_projection,
        "build_macro_regime_snapshot",
        lambda _path: {"snapshot": True},
    )
    monkeypatch.setattr(
        writer_module.market_memory_projection,
        "read_verified_macro_regime_bytes",
        lambda _path, _snapshot: raw_body,
    )
    monkeypatch.setattr(
        writer_module.market_memory_identity,
        "build_current_spy_identity",
        lambda **_kwargs: SimpleNamespace(config_sha256=sha256(config).hexdigest()),
    )
    monkeypatch.setattr(
        writer_module.market_memory_trusted,
        "capture_trusted_regime_context",
        lambda *_args, **_kwargs: pytest.fail(
            "capture must not run after checkout provenance failure"
        ),
    )


def test_projector_rejects_checkout_head_change_during_stable_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_writer_inputs(monkeypatch)
    commits = iter(("a" * 40, "b" * 40))
    monkeypatch.setattr(
        writer_module, "_repository_commit", lambda _root: next(commits)
    )

    with pytest.raises(trusted.MarketMemoryTrustedCaptureError, match="changed"):
        writer_module.project_current_context(
            tmp_path,
            public_store_root=tmp_path / "public",
            private_evidence_root=tmp_path / "private",
        )


@pytest.mark.parametrize("mismatch", ["regime", "config"])
def test_projector_rejects_inputs_not_owned_by_the_pinned_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mismatch: str
) -> None:
    raw_body = b"raw"
    config = b"config"
    _stub_writer_inputs(monkeypatch, raw_body=raw_body, config=config)
    monkeypatch.setattr(writer_module, "_repository_commit", lambda _root: "a" * 40)

    def tracked(_root: Path, _commit: str, relative_path: str) -> bytes:
        if relative_path == "data/regime/latest.json":
            return b"wrong" if mismatch == "regime" else raw_body
        return b"wrong" if mismatch == "config" else config

    monkeypatch.setattr(writer_module, "_tracked_bytes", tracked)

    with pytest.raises(trusted.MarketMemoryTrustedCaptureError, match="owned"):
        writer_module.project_current_context(
            tmp_path,
            public_store_root=tmp_path / "public",
            private_evidence_root=tmp_path / "private",
        )


def test_api_uses_the_composite_reader_and_updater_restarts_its_import_closure() -> (
    None
):
    router = _text(API_ROUTER)
    restart = _api_restart_block()

    for module in (
        "market_memory",
        "market_memory_pit",
        "market_memory_playback",
        "market_memory_trusted",
    ):
        assert module in router
    pit_reader = router.split("def _pit_reader()", 1)[1].split("\n\n", 1)[0]
    assert "market_memory_trusted.CompositeAsKnownAtReader(" in pit_reader
    assert "market_memory_pit.default_store_root(repository)" in pit_reader
    assert "market_memory_trusted.default_trusted_store_root(repository)" in pit_reader

    restart_predicate = next(
        line
        for line in restart.splitlines()
        if line.startswith('if [ "$API_UNIT_UPDATED"')
    )
    assert "market_memory_trusted" in restart_predicate
    assert "market_memory_playback" in restart_predicate
    assert "market_memory_projection" in restart_predicate


def test_public_router_has_no_raw_source_or_evidence_route() -> None:
    tree = ast.parse(_text(API_ROUTER), filename=str(API_ROUTER))
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(
                decorator.func, ast.Attribute
            ):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "router" or not decorator.args:
                continue
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str):
                routes.add((decorator.func.attr, path.value))

    assert routes == {
        ("get", "/as-known-at"),
        ("get", "/context/{context_id}"),
        ("get", "/macro"),
        ("get", "/playback/catalog"),
        ("get", "/symbol/{ticker}"),
    }
    forbidden = ("source", "artifact", "evidence", "raw", "snapshot")
    assert not any(
        token in route.lower() for _method, route in routes for token in forbidden
    )
