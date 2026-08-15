"""MMX-001 customer-table backup: dump, encrypt, restore, refuse production."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.backup_user_tables import (
    DEFAULT_RETENTION_DAYS,
    EXIT_REFUSED,
    MIN_RETENTION_DAYS,
    PRODUCTION_PROJECT_REFS,
    PROTECTED_TABLES,
    BackupError,
    ProductionRestoreRefused,
    canonical_jsonl,
    decrypt_bytes,
    derive_key,
    dump_tables,
    encrypt_bytes,
    forbid_production_target,
    list_local_backup_ids,
    load_encrypted_backup,
    load_table_dir,
    main,
    make_backup_id,
    prune_backup_ids,
    restore_tables,
    sha256_hex,
    verify_restore,
    write_encrypted_backup,
    write_table_dir,
)

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "app" / "deploy" / "macro-user-backup.service"
TIMER = ROOT / "app" / "deploy" / "macro-user-backup.timer"
SETUP = ROOT / "app" / "deploy" / "user-backup-setup.sh"
RUNBOOK = ROOT / "docs" / "RESTORE_RUNBOOK.md"
SCRIPT = ROOT / "scripts" / "backup_user_tables.py"
WORKFLOW = ROOT / ".github" / "workflows" / "user-backup.yml"

KEY = "test-backup-key-16+"


def _rows(table: str, n: int = 2) -> list[dict]:
    return [{"id": f"{table}-{i}", "n": i, "table": table} for i in range(n)]


def _source_dir(tmp_path: Path, counts: dict[str, int] | None = None) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    for table in PROTECTED_TABLES:
        n = 2 if counts is None else counts.get(table, 2)
        write_table_dir(src, table, _rows(table, n))
    return src


def test_protected_tables_match_the_gate():
    assert PROTECTED_TABLES == (
        "profiles",
        "watchlists",
        "watchlist_symbols",
        "chart_layouts",
        "saved_scripts",
        "alerts",
        "favorites",
        "user_entitlements",
        "stripe_events",
    )
    assert "fsldfzlxyavsuwqbceod" in PRODUCTION_PROJECT_REFS
    assert DEFAULT_RETENTION_DAYS >= 30
    assert MIN_RETENTION_DAYS >= 30


def test_encrypt_roundtrip_and_wrong_key():
    key = derive_key(KEY)
    blob = encrypt_bytes(b"hello-customer-row", key)
    assert blob.startswith(b"MMUB1\n")
    assert decrypt_bytes(blob, key) == b"hello-customer-row"
    with pytest.raises(BackupError):
        decrypt_bytes(blob, derive_key("wrong-backup-key-16"))


def test_short_encryption_key_is_rejected():
    with pytest.raises(BackupError, match="at least 16"):
        derive_key("too-short")


def test_forbid_production_target():
    with pytest.raises(ProductionRestoreRefused):
        forbid_production_target("https://fsldfzlxyavsuwqbceod.supabase.co")
    with pytest.raises(ProductionRestoreRefused):
        forbid_production_target("/tmp/restore-into-fsldfzlxyavsuwqbceod")
    forbid_production_target("https://scratch-xxxx.supabase.co")
    forbid_production_target("file:/tmp/scratch-restore")


def test_dump_restore_verify_integrity(tmp_path: Path):
    src = _source_dir(tmp_path, {"profiles": 3, "stripe_events": 1})
    dumps = dump_tables(PROTECTED_TABLES, lambda table: load_table_dir(src, table))
    assert dumps["profiles"][0]["id"] == "profiles-0"
    key = derive_key(KEY)
    backup_id = "user-tables-20260815T051700Z"
    manifest = write_encrypted_backup(
        tmp_path / "store",
        dumps,
        key=key,
        backup_id=backup_id,
        source=f"file:{src}",
        source_project_ref=None,
        retention_days=30,
        created_at=datetime(2026, 8, 15, 5, 17, tzinfo=timezone.utc),
    )
    assert manifest.backup_id == backup_id
    assert {item.name for item in manifest.tables} == set(PROTECTED_TABLES)
    loaded, reloaded = load_encrypted_backup(tmp_path / "store" / backup_id, key)
    assert loaded.backup_id == backup_id
    dst = tmp_path / "dst"
    restore_tables(
        reloaded,
        lambda table, rows: write_table_dir(dst, table, rows),
        target=f"file:{dst}",
        scratch_confirmed=True,
    )
    report = verify_restore(dumps, {t: load_table_dir(dst, t) for t in PROTECTED_TABLES})
    assert all(item["ok"] is True for item in report.values())
    assert report["profiles"]["source_rows"] == 3
    assert report["stripe_events"]["restored_rows"] == 1


def test_restore_without_scratch_flag_is_refused(tmp_path: Path):
    src = _source_dir(tmp_path)
    dumps = dump_tables(PROTECTED_TABLES, lambda table: load_table_dir(src, table))
    with pytest.raises(BackupError, match="i-am-restoring-into-scratch"):
        restore_tables(
            dumps,
            lambda table, rows: write_table_dir(tmp_path / "dst", table, rows),
            target="file:/tmp/scratch",
            scratch_confirmed=False,
        )


def test_cli_restore_refuses_production_project(tmp_path: Path):
    src = _source_dir(tmp_path)
    store = tmp_path / "store"
    assert main([
        "--encryption-key", KEY,
        "--source-dir", str(src),
        "--output-dir", str(store),
        "--backup-id", "user-tables-20260815T051700Z",
        "backup",
    ]) == 0
    rc = main([
        "--encryption-key", KEY,
        "--input-dir", str(store / "user-tables-20260815T051700Z"),
        "--target-url", "https://fsldfzlxyavsuwqbceod.supabase.co",
        "--i-am-restoring-into-scratch",
        "restore",
    ])
    assert rc == EXIT_REFUSED


def test_cli_end_to_end_with_receipt(tmp_path: Path):
    src = _source_dir(tmp_path)
    store = tmp_path / "store"
    dst = tmp_path / "dst"
    receipt = tmp_path / "receipt.json"
    assert main([
        "--encryption-key", KEY,
        "--source-dir", str(src),
        "--output-dir", str(store),
        "--backup-id", "user-tables-20260815T051700Z",
        "backup",
    ]) == 0
    assert main([
        "--encryption-key", KEY,
        "--input-dir", str(store / "user-tables-20260815T051700Z"),
        "--target-dir", str(dst),
        "--receipt", str(receipt),
        "--i-am-restoring-into-scratch",
        "restore",
    ]) == 0
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["backup_id"] == "user-tables-20260815T051700Z"
    assert payload["integrity_ok"] is True
    assert payload["rpo_seconds"] == 24 * 60 * 60
    assert payload["rto_seconds"] >= 0
    assert set(payload["tables"]) == set(PROTECTED_TABLES)
    assert main([
        "--encryption-key", KEY,
        "--input-dir", str(store / "user-tables-20260815T051700Z"),
        "--target-dir", str(dst),
        "verify",
    ]) == 0


def test_tampered_ciphertext_fails_verify(tmp_path: Path):
    src = _source_dir(tmp_path)
    store = tmp_path / "store"
    backup_id = "user-tables-20260815T051700Z"
    assert main([
        "--encryption-key", KEY,
        "--source-dir", str(src),
        "--output-dir", str(store),
        "--backup-id", backup_id,
        "backup",
    ]) == 0
    blob_path = store / backup_id / "profiles.jsonl.aes"
    blob = bytearray(blob_path.read_bytes())
    blob[-1] ^= 0xFF
    blob_path.write_bytes(bytes(blob))
    with pytest.raises(BackupError):
        load_encrypted_backup(store / backup_id, derive_key(KEY))


def test_prune_keeps_thirty_days(tmp_path: Path):
    now = datetime(2026, 8, 15, 5, 17, tzinfo=timezone.utc)
    keep = make_backup_id(now - timedelta(days=10))
    drop = make_backup_id(now - timedelta(days=45))
    expired = prune_backup_ids([keep, drop], now=now, retention_days=30)
    assert expired == [drop]
    with pytest.raises(BackupError, match=">= 30"):
        prune_backup_ids([keep], now=now, retention_days=7)


def test_cli_prune_deletes_only_expired(tmp_path: Path):
    src = _source_dir(tmp_path)
    store = tmp_path / "store"
    old_id = "user-tables-20260601T051700Z"
    new_id = "user-tables-20260815T051700Z"
    for backup_id in (old_id, new_id):
        assert main([
            "--encryption-key", KEY,
            "--source-dir", str(src),
            "--output-dir", str(store),
            "--backup-id", backup_id,
            "backup",
        ]) == 0
    assert set(list_local_backup_ids(store)) == {old_id, new_id}
    assert main([
        "--output-dir", str(store),
        "--retention-days", "30",
        "prune",
    ]) == 0
    assert list_local_backup_ids(store) == [new_id]


def test_canonical_jsonl_is_order_stable_for_integrity():
    a = [{"b": 1, "a": 2}, {"a": 0, "b": 9}]
    b = [{"a": 2, "b": 1}, {"b": 9, "a": 0}]
    assert canonical_jsonl(a) == canonical_jsonl(b)
    assert sha256_hex(canonical_jsonl(a)) == sha256_hex(canonical_jsonl(b))


def test_service_is_bounded_hardened_oneshot():
    service = SERVICE.read_text(encoding="utf-8")
    assert "Type=oneshot" in service
    assert "RuntimeMaxSec=900" in service
    assert "TimeoutStartSec=900" in service
    assert "PrivateTmp=true" in service
    assert "NoNewPrivileges=true" in service
    assert "UMask=0077" in service
    assert "ProtectSystem=strict" in service
    assert "ConditionPathExists=/etc/macro-user-backup.env" in service
    assert "EnvironmentFile=/etc/macro-user-backup.env" in service
    assert "python -m scripts.backup_user_tables backup --upload-r2 --r2-sse-c --prune" in service
    assert "ExecStart=" in service and "update.sh" not in [
        line for line in service.splitlines() if line.startswith("ExecStart=")
    ][0]
    timeout = int(re.search(r"^TimeoutStartSec=(\d+)$", service, re.MULTILINE).group(1))
    runtime = int(re.search(r"^RuntimeMaxSec=(\d+)$", service, re.MULTILINE).group(1))
    assert 0 < timeout <= 900
    assert 0 < runtime <= 900


def test_timer_is_nightly_and_persistent():
    timer = TIMER.read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 05:17:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "Unit=macro-user-backup.service" in timer


def test_setup_script_is_operator_gated_and_valid_bash():
    setup = SETUP.read_text(encoding="utf-8")
    assert "update.sh" in setup  # names the non-wiring, does not call it
    assert "BACKUP_ENCRYPTION_KEY" in setup
    assert "systemctl enable --now macro-user-backup.timer" in setup
    assert "systemd-analyze verify" in setup
    subprocess.run(["bash", "-n", str(SETUP)], check=True)


def test_runbook_names_exact_commands_and_operator_block():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "OPERATOR-BLOCKED" in text
    assert "python -m scripts.backup_user_tables" in text
    assert "APP_DIR=/opt/macro /opt/macro/app/deploy/user-backup-setup.sh" in text
    assert "--i-am-restoring-into-scratch" in text
    assert "RPO" in text and "RTO" in text
    assert "fsldfzlxyavsuwqbceod" in text
    assert "NEVER restore into production" in text
    for table in PROTECTED_TABLES:
        assert table in text


def test_suite_is_named_in_its_own_workflow():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "tests/test_backup_user_tables.py" in text
    assert "scripts/backup_user_tables.py" in text


def test_script_pins_repo_root_before_any_work():
    src = SCRIPT.read_text(encoding="utf-8")
    pin = src.index("sys.path.insert(0, str(_ROOT))")
    # No repo-package import should precede the pin.
    assert "from lib" not in src[:pin]
    assert "import lib" not in src[:pin]


def test_missing_encryption_key_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    src = _source_dir(tmp_path)
    rc = main([
        "--source-dir", str(src),
        "--output-dir", str(tmp_path / "store"),
        "backup",
    ])
    assert rc == EXIT_REFUSED
    assert list((tmp_path / "store").glob("*/manifest.json")) == []
