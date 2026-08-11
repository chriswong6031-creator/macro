"""Deployment and serving-boundary guards for the W1B.1 trusted canary."""

from __future__ import annotations

import ast
import json
import os
import re
import stat
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import options_market_memory_receipt_store as options_receipt_store
from engine.neuralweb import market_memory_pit as pit
from engine.neuralweb import market_memory_trusted as trusted
from scripts import audit_options_market_memory_context as options_context_audit
from scripts import initialize_market_memory_w1a as w1a_initializer
from scripts import project_market_memory_context as writer_module
from tests.test_market_memory_pit import CAPTURED_AT, _packet

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-market-memory-context.service"
TIMER = DEPLOY / "macro-market-memory-context.timer"
API_SERVICE = DEPLOY / "macro-api.service"
SETUP = DEPLOY / "api-setup.sh"
UPDATE = DEPLOY / "update.sh"
WRITER = ROOT / "scripts" / "project_market_memory_context.py"
API_ROUTER = ROOT / "app" / "market_memory.py"
W1A_INITIALIZER = ROOT / "scripts" / "initialize_market_memory_w1a.py"
OPTIONS_AUDITOR = ROOT / "scripts" / "audit_options_market_memory_context.py"

W1A_ROOT = "/var/lib/macro-market-memory/public"
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
    initializer = (
        '"$VENV/bin/python" "$APP_DIR/scripts/initialize_market_memory_w1a.py" '
        '\\\n  --repository-root "$APP_DIR" '
        f"\\\n  --store {W1A_ROOT}"
    )
    assert initializer in setup
    assert setup.index(initializer) < setup.index("systemctl restart macro-api")
    assert "refusing API readiness" in setup
    assert "systemctl enable --now macro-market-memory-context.timer" in setup


def test_update_verifies_installs_arms_and_immediately_reprojects() -> None:
    update = _text(UPDATE)
    block = _context_update_block()

    for directory in (PUBLIC_ROOT, PRIVATE_ROOT):
        assert f"install -d -m 0700 {directory}" in update
    assert update.index(f"install -d -m 0700 {PRIVATE_ROOT}") < update.index(
        'systemd-analyze verify "$APP_DIR/app/deploy/macro-api.service"'
    )
    initializer = '/opt/macro-api/.venv/bin/python "$APP_DIR/scripts/initialize_market_memory_w1a.py"'
    assert initializer in update
    assert update.index(initializer) < update.index(
        'systemd-analyze verify "$APP_DIR/app/deploy/macro-api.service"'
    )
    assert "W1A public generation initialization failed" in update

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
    assert "run_projection_cycle(" in writer
    assert "options_context_audit.publish_live_audit(" in writer

    monkeypatch.delenv("MARKET_MEMORY_TRUSTED_STORE_DIR", raising=False)
    monkeypatch.delenv("MARKET_MEMORY_CONTEXT_PROJECTION_DIR", raising=False)
    assert (
        trusted.default_trusted_store_root("/opt/macro") == Path(PUBLIC_ROOT).resolve()
    )
    assert (
        trusted.default_private_evidence_root("/opt/macro")
        == Path(PRIVATE_ROOT).resolve()
    )


def test_options_receipt_auditor_entrypoint_is_cwd_independent_and_durable(
    tmp_path: Path,
) -> None:
    w1a = tmp_path / "w1a"
    trusted_root = tmp_path / "trusted"
    receipt_root = tmp_path / "private-receipts"
    w1a_initializer.initialize_w1a_store(w1a)
    trusted.initialize_trusted_store(trusted_root)
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }

    result = subprocess.run(
        [
            str(OPTIONS_AUDITOR),
            "--repository-root",
            str(ROOT),
            "--w1a-store-root",
            str(w1a),
            "--trusted-store-root",
            str(trusted_root),
            "--publish-root",
            str(receipt_root),
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    head = json.loads(result.stdout)
    publication = options_receipt_store.read_current_publication(
        receipt_root, repository_root=ROOT
    )

    assert publication["head"] == head
    assert head["reference_count"] == len(publication["references"])
    assert head["reference_count"] > 0
    assert head["reference_set_sha256"] == publication["audit"][
        "reference_set_sha256"
    ]


def test_projection_cycle_uses_the_hourly_owner_to_publish_private_receipts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deployed_commit = "a" * 40
    public = tmp_path / "public"
    private = tmp_path / "private"
    w1a = tmp_path / "w1a"
    receipt_root = private / "options-context-receipts"
    trusted_result = {
        "schema": "market_memory.trusted_projection_result.v1",
        "deployed_commit": deployed_commit,
    }
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        writer_module,
        "project_current_context",
        lambda *_args, **_kwargs: trusted_result,
    )
    monkeypatch.setattr(
        writer_module, "_repository_commit", lambda _root: deployed_commit
    )

    def publish(**kwargs: object) -> dict[str, str]:
        observed.update(kwargs)
        return {"publication_id": "omctxpub_" + "b" * 64}

    monkeypatch.setattr(options_context_audit, "publish_live_audit", publish)
    result = writer_module.run_projection_cycle(
        tmp_path,
        public_store_root=public,
        private_evidence_root=private,
        w1a_store_root=w1a,
    )

    assert result["trusted_projection"] == trusted_result
    assert result["options_context_receipt"] == {
        "publication_id": "omctxpub_" + "b" * 64
    }
    assert observed["repository_root"] == tmp_path.resolve()
    assert observed["w1a_store_root"] == w1a
    assert observed["trusted_store_root"] == public
    assert observed["publication_root"] == receipt_root
    assert observed["expected_deployed_commit"] == deployed_commit


def test_w1a_initializer_is_the_only_production_genesis_owner() -> None:
    assert _production_calls("initialize_w1a_store") == {
        Path("scripts/initialize_market_memory_w1a.py")
    }
    source = _text(W1A_INITIALIZER)
    assert "capture_context" not in source
    assert "request" not in source
    assert "initialize_w1a_store" in source


def test_w1a_initializer_entrypoint_is_cwd_independent(tmp_path: Path) -> None:
    store = tmp_path / "public"
    result = subprocess.run(
        [
            sys.executable,
            str(W1A_INITIALIZER),
            "--repository-root",
            str(ROOT),
            "--store",
            str(store),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    assert payload["capture_count"] == 0
    assert pit.FileAsKnownAtReader(store).read_pinned_generation().captures == ()


def test_w1a_initializer_creates_only_idempotent_empty_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "public"

    assert w1a_initializer.main(["--store", str(store)]) == 0
    first = json.loads(capsys.readouterr().out)
    first_files = {
        path.relative_to(store): path.read_bytes()
        for path in store.rglob("*")
        if path.is_file()
    }
    assert first["profile"] == pit.STORE_PROFILE
    assert first["capture_count"] == 0
    assert set(first_files) == {
        Path("store_manifest.json"),
        Path("HEAD.json"),
        next(path for path in first_files if path.parts[0] == "generations"),
    }
    assert not any(
        (store / name).exists() for name in ("objects", "contexts", "queries")
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in (store, *(path for path in store.rglob("*") if path.is_dir()))
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in store.rglob("*")
        if path.is_file()
    )

    assert w1a_initializer.main(["--store", str(store)]) == 0
    second = json.loads(capsys.readouterr().out)
    second_files = {
        path.relative_to(store): path.read_bytes()
        for path in store.rglob("*")
        if path.is_file()
    }
    assert second == first
    assert second_files == first_files


def test_w1a_initializer_authenticates_existing_capture_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = tmp_path / "public"
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURED_AT)
    stored = pit.capture_context(store, _packet())
    before = {
        path.relative_to(store): path.read_bytes()
        for path in store.rglob("*")
        if path.is_file()
    }

    result = w1a_initializer.initialize_w1a_store(store)

    after = {
        path.relative_to(store): path.read_bytes()
        for path in store.rglob("*")
        if path.is_file()
    }
    assert result["capture_count"] == 1
    assert (
        result["generation_id"]
        == pit.FileAsKnownAtReader(store).read_pinned_generation().generation_id
    )
    assert stored.capture_receipt["query_id"] in {
        row.query_id
        for row in pit.FileAsKnownAtReader(store).read_pinned_generation().captures
    }
    assert after == before


def test_w1a_initializer_readiness_is_current_head_bounded_at_4096(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = tmp_path / "cap-public"
    rows = []
    for index in range(pit._MAX_GENERATION_CAPTURES):
        digest = f"{index:064x}"
        rows.append(
            {
                "query_id": "mmquery_" + digest,
                "context_id": "mmctx_" + digest,
                "capture_id": "mmcapture_" + digest,
                "packet_sha256": digest,
            }
        )
    manifest = pit._new_store_manifest()
    generation = pit._new_generation(
        store_id=manifest["store_id"],
        previous_generation_id="mmgeneration_" + "b" * 64,
        captures=rows,
    )
    generation_body = pit._canonical_bytes(generation)
    pit._mkdir_durable(store)
    pit._write_create_once(
        store,
        pit._store_manifest_path(store),
        pit._canonical_bytes(manifest),
        label="cap store manifest",
    )
    pit._write_create_once(
        store,
        pit._generation_path(store, generation["generation_id"]),
        generation_body,
        label="cap active generation",
    )
    pit._replace_head(
        store, pit._new_head(generation, generation_body=generation_body)
    )
    monkeypatch.setattr(
        pit,
        "_read_pinned_generation_from_state",
        lambda *_args, **_kwargs: pytest.fail(
            "initializer readiness must not replay cumulative ancestry"
        ),
    )
    observed: dict[str, object] = {}

    def bounded_namespace_audit(_store: Path, **kwargs: object) -> None:
        observed.update(kwargs)

    monkeypatch.setattr(
        w1a_initializer, "_audit_namespace", bounded_namespace_audit
    )

    result = w1a_initializer.initialize_w1a_store(store)

    assert result["capture_count"] == pit._MAX_GENERATION_CAPTURES
    assert observed["expected_generation_files"] == 4_097
    assert len(observed["expected_files"]) == 3 * 4_096 + 3


def test_w1a_initializer_rejects_extra_complete_store_generation_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = tmp_path / "orphan-complete"
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURED_AT)
    pit.capture_context(store, _packet())
    orphan_id = "mmgeneration_" + "f" * 64
    orphan = pit._generation_path(store, orphan_id)
    pit._mkdir_durable(orphan.parent)
    orphan.write_bytes(b"{}")
    orphan.chmod(0o600)

    with pytest.raises(
        pit.MarketMemoryStoreError,
        match="generation archive count differs",
    ):
        w1a_initializer.initialize_w1a_store(store)


def test_w1a_initializer_rejects_symlink_permission_and_tamper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "public"
    alias.symlink_to(target, target_is_directory=True)
    assert w1a_initializer.main(["--store", str(alias)]) == 2
    assert "symlink" in capsys.readouterr().err
    assert list(target.iterdir()) == []

    denied = tmp_path / "denied"
    original_mkdir = pit._mkdir_durable

    def permission_denied(_path: Path) -> None:
        raise PermissionError("injected permission denial")

    monkeypatch.setattr(pit, "_mkdir_durable", permission_denied)
    assert w1a_initializer.main(["--store", str(denied)]) == 2
    assert "cannot be initialized safely" in capsys.readouterr().err
    monkeypatch.setattr(pit, "_mkdir_durable", original_mkdir)

    partial = tmp_path / "interrupted"
    original_write = pit._write_create_once
    interrupted = False

    def interrupt_empty_generation(
        root: Path, path: Path, body: bytes, *, label: str
    ) -> bool:
        nonlocal interrupted
        if label == "empty store generation" and not interrupted:
            interrupted = True
            raise pit.MarketMemoryStoreError("injected empty-init interruption")
        return original_write(root, path, body, label=label)

    monkeypatch.setattr(pit, "_write_create_once", interrupt_empty_generation)
    assert w1a_initializer.main(["--store", str(partial)]) == 2
    assert "interruption" in capsys.readouterr().err
    assert (partial / "store_manifest.json").is_file()
    assert not (partial / "HEAD.json").exists()
    monkeypatch.setattr(pit, "_write_create_once", original_write)
    assert w1a_initializer.main(["--store", str(partial)]) == 0
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["capture_count"] == 0
    assert not any(
        (partial / name).exists() for name in ("objects", "contexts", "queries")
    )

    store = tmp_path / "tampered"
    assert w1a_initializer.main(["--store", str(store)]) == 0
    capsys.readouterr()
    head = store / "HEAD.json"
    head.write_text("{}", encoding="utf-8")
    before = head.read_bytes()
    assert w1a_initializer.main(["--store", str(store)]) == 2
    assert "HEAD" in capsys.readouterr().err
    assert head.read_bytes() == before


def test_w1a_initializer_rejects_unowned_namespace_hardlinks_and_mode_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unknown_root = tmp_path / "unknown"
    unknown_root.mkdir(mode=0o700)
    unknown = unknown_root / "unexpected"
    unknown.write_bytes(b"unowned")
    unknown.chmod(0o600)
    before = unknown.read_bytes()
    assert w1a_initializer.main(["--store", str(unknown_root)]) == 2
    assert "unowned file" in capsys.readouterr().err
    assert unknown.read_bytes() == before

    orphan_root = tmp_path / "orphan"
    assert w1a_initializer.main(["--store", str(orphan_root)]) == 0
    capsys.readouterr()
    (orphan_root / "HEAD.json").unlink()
    orphan = orphan_root / "generations" / "ff" / f"mmgeneration_{'f' * 64}.json"
    orphan.parent.mkdir(mode=0o700)
    orphan.write_bytes(b"{}")
    orphan.chmod(0o600)
    before_orphan = orphan.read_bytes()
    assert w1a_initializer.main(["--store", str(orphan_root)]) == 2
    assert "unowned" in capsys.readouterr().err
    assert orphan.read_bytes() == before_orphan
    assert not (orphan_root / "HEAD.json").exists()

    hardlink_root = tmp_path / "hardlink"
    assert w1a_initializer.main(["--store", str(hardlink_root)]) == 0
    capsys.readouterr()
    hardlink = tmp_path / "HEAD.hardlink"
    os.link(hardlink_root / "HEAD.json", hardlink)
    assert w1a_initializer.main(["--store", str(hardlink_root)]) == 2
    assert "hardlinked" in capsys.readouterr().err

    mode_root = tmp_path / "mode"
    assert w1a_initializer.main(["--store", str(mode_root)]) == 0
    capsys.readouterr()
    generation = next((mode_root / "generations").rglob("*.json"))
    generation.chmod(0o666)
    assert w1a_initializer.main(["--store", str(mode_root)]) == 2
    assert "mode is not 0600" in capsys.readouterr().err


def test_w1a_initializer_rejects_symlinked_ancestor_and_preserves_trusted_child(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real_parent = tmp_path / "real"
    real_parent.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)
    assert w1a_initializer.main(["--store", str(alias / "public")]) == 2
    assert "symlinked ancestor" in capsys.readouterr().err
    assert list(real_parent.iterdir()) == []

    store = tmp_path / "with-trusted"
    store.mkdir(mode=0o700)
    trusted_root = store / "trusted-v1"
    trusted_root.mkdir(mode=0o700)
    sentinel = trusted_root / "separate-owner-sentinel"
    sentinel.write_bytes(b"trusted owner bytes")
    sentinel.chmod(0o600)
    before = sentinel.read_bytes()
    assert w1a_initializer.main(["--store", str(store)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["capture_count"] == 0
    assert sentinel.read_bytes() == before


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
