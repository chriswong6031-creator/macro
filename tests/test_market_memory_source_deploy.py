"""W1B.0 source-intake CLI and private deployment-boundary guards."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from scripts.ingest_market_memory_sources import ingest_market_memory_sources

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "app/deploy/macro-market-memory-source.service"
TIMER = ROOT / "app/deploy/macro-market-memory-source.timer"
SETUP = ROOT / "app/deploy/api-setup.sh"
UPDATE = ROOT / "app/deploy/update.sh"


def test_intake_cli_is_a_thin_engine_api_wrapper(monkeypatch, tmp_path: Path):
    calls: list[tuple[Path, Path, Path]] = []
    engine_module = ModuleType("engine.neuralweb.market_memory_sources")

    def fake_intake(store_root, *, manifest_path, artifact_path):
        calls.append((Path(store_root), Path(manifest_path), Path(artifact_path)))
        return SimpleNamespace(created=True, generation_id="mmsgen_" + "a" * 64)

    engine_module.intake_alfred_cpiaucsl = fake_intake
    monkeypatch.setitem(
        sys.modules, "engine.neuralweb.market_memory_sources", engine_module
    )

    receipt = ingest_market_memory_sources(
        store_root=tmp_path / "private",
        manifest_path=tmp_path / "manifest.json",
        artifact_path=tmp_path / "CPIAUCSL_all_vintages.parquet",
    )

    assert calls == [
        (
            tmp_path / "private",
            tmp_path / "manifest.json",
            tmp_path / "CPIAUCSL_all_vintages.parquet",
        )
    ]
    assert receipt == {
        "schema": "market_memory.source_intake_run.v1",
        "status": "created",
        "source_id": "fred_alfred:CPIAUCSL",
        "generation_id": "mmsgen_" + "a" * 64,
        "created": True,
    }


def test_source_unit_is_private_network_dark_and_credential_free():
    service = SERVICE.read_text(encoding="utf-8")
    timer = TIMER.read_text(encoding="utf-8")

    assert (
        "ExecStart=/opt/macro-api/.venv/bin/python -m "
        "scripts.ingest_market_memory_sources --store-root "
        "/var/lib/macro-market-memory/state/sources"
    ) in service
    assert "ReadWritePaths=/var/lib/macro-market-memory/state/sources" in service
    assert "InaccessiblePaths=/var/lib/macro-market-memory/public" in service
    assert "PrivateNetwork=true" in service
    assert "RestrictAddressFamilies=AF_UNIX" in service
    assert "EnvironmentFile=" not in service
    assert "MARKET_MEMORY_CONTEXT_STORE_DIR" not in service
    assert "InaccessiblePaths=-/var/lib/macro-codex" in service
    assert "InaccessiblePaths=-/etc/macro-api.env" in service
    assert "OnCalendar=*-*-* *:27:00 UTC" in timer
    assert "Persistent=true" in timer


def test_setup_and_update_reconcile_private_source_lane():
    subprocess.run(["bash", "-n", str(SETUP)], check=True)
    subprocess.run(["bash", "-n", str(UPDATE)], check=True)
    setup = SETUP.read_text(encoding="utf-8")
    update = UPDATE.read_text(encoding="utf-8")

    for script in (setup, update):
        assert "install -d -m 0700 /var/lib/macro-market-memory/state/sources" in script
        assert "macro-market-memory-source.service" in script
        assert "macro-market-memory-source.timer" in script
        assert "systemd-analyze verify" in script
        assert "systemctl enable --now macro-market-memory-source.timer" in script
    assert "engine/neuralweb/market_memory_sources\\.py" in update
    assert "CPIAUCSL_all_vintages\\.parquet" in update
