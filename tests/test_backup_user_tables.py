"""MMX-001 / GATE-1 — customer-table backup + restore guards.

These tests prove the repo-side machinery. They do NOT claim a scratch-Supabase
restore happened; that gate stays OPERATOR-BLOCKED until a real scratch project
is used. See docs/RESTORE_RUNBOOK.md.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.backup_user_tables as bak

ROOT = Path(__file__).resolve().parents[1]
KEY = "test-backup-key-16+"


def _rows(n: int, prefix: str) -> list[dict]:
    return [{"id": f"{prefix}-{i}", "n": i} for i in range(n)]


def _fixture_tables() -> dict[str, bak.TableDump]:
    counts = {
        "profiles": 3,
        "watchlists": 2,
        "watchlist_symbols": 4,
        "chart_layouts": 1,
        "saved_scripts": 1,
        "alerts": 2,
        "favorites": 5,
        "user_entitlements": 3,
        "stripe_events": 6,
    }
    return {name: bak.dump_table(name, _rows(n, name)) for name, n in counts.items()}


def test_protected_tables_match_gate1_exactly():
    assert bak.PROTECTED_TABLES == (
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
    assert set(bak.RESTORE_ORDER) == set(bak.PROTECTED_TABLES)


def test_dump_table_refuses_non_allowlisted_name():
    with pytest.raises(bak.BackupError, match="non-protected"):
        bak.dump_table("auth.users", [{"id": 1}])


def test_encrypt_decrypt_roundtrip_is_not_plaintext():
    plaintext = b"secret-customer-rows\n" * 20
    ciphertext = bak.encrypt_payload(plaintext, KEY)
    assert ciphertext != plaintext
    assert b"secret-customer-rows" not in ciphertext
    assert bak.decrypt_payload(ciphertext, KEY) == plaintext


def test_encrypt_fail_closed_on_short_or_missing_key():
    with pytest.raises(bak.BackupError, match="required"):
        bak.encrypt_payload(b"x", "")
    with pytest.raises(bak.BackupError, match="16"):
        bak.encrypt_payload(b"x", "short")


def test_publish_writes_ciphertext_and_sidecar_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    tables = _fixture_tables()
    artifact = bak.make_artifact(
        tables,
        mode="rest",
        source={"as_of": "2026-08-15T05:17:00Z", "project_ref": "scratch"},
        key=KEY,
        now=datetime(2026, 8, 15, 5, 17, tzinfo=timezone.utc),
    )
    store = bak.LocalDirStore(tmp_path)
    bak.publish_artifact(store, artifact, bak.DEFAULT_PREFIX)
    enc_key, man_key = bak.object_keys(artifact.backup_id, bak.DEFAULT_PREFIX)
    ciphertext = store.get(enc_key)
    assert ciphertext == artifact.ciphertext
    assert b"user_entitlements" not in ciphertext
    sidecar = json.loads(store.get(man_key))
    assert sidecar["schema"] == bak.SCHEMA
    assert sidecar["encrypted"] is True
    assert sidecar["retention_days"] >= 30
    for name in bak.PROTECTED_TABLES:
        assert name in sidecar["tables"]
        assert sidecar["tables"][name]["rows"] == len(tables[name].rows)


def test_verify_detects_count_mismatch():
    expected = {name: {"rows": 2} for name in bak.PROTECTED_TABLES}
    actual = {name: 2 for name in bak.PROTECTED_TABLES}
    actual["stripe_events"] = 1
    report = bak.verify_tables(expected, actual)
    assert report["ok"] is False
    assert report["integrity"] == "fail"
    assert report["tables"]["stripe_events"]["ok"] is False


def test_restore_roundtrip_memory_store_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    tables = _fixture_tables()
    artifact = bak.make_artifact(
        tables,
        mode="memory",
        source={"as_of": "2026-08-15T04:00:00Z", "project_ref": "fixture"},
        key=KEY,
        now=datetime(2026, 8, 15, 5, 17, tzinfo=timezone.utc),
    )
    store = bak.LocalDirStore(tmp_path / "store")
    bak.publish_artifact(store, artifact, bak.DEFAULT_PREFIX)
    dest: dict[str, list[dict]] = {name: [] for name in bak.PROTECTED_TABLES}

    def writer(name: str, rows: list[dict]) -> int:
        dest[name] = list(rows)
        return len(rows)

    loaded = bak.load_artifact(store, artifact.backup_id, bak.DEFAULT_PREFIX, KEY)
    started = datetime(2026, 8, 15, 5, 20, tzinfo=timezone.utc)
    actual = bak.restore_via_writer(loaded.tables, writer)
    ended = datetime(2026, 8, 15, 5, 20, 8, tzinfo=timezone.utc)
    report = bak.verify_tables(loaded.manifest["tables"], actual)
    assert report["ok"] is True
    assert dest["user_entitlements"] == tables["user_entitlements"].rows
    receipt = bak.build_receipt(
        backup_id=artifact.backup_id,
        dest="postgresql://u:p@scratch.invalid/postgres",
        started=started,
        ended=ended,
        source_as_of=datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc),
        verification=report,
        commands=["python -m scripts.backup_user_tables restore --backup-id "
                  f"{artifact.backup_id} --i-am-restoring-into-scratch "
                  "--dest-db-url \"$SCRATCH_DB_URL\""],
        environment="in-process-fixture",
    )
    assert receipt["rto_seconds"] == 8
    assert receipt["rpo_seconds"] == 80 * 60
    assert receipt["gate1_scratch_supabase"] is False
    (tmp_path / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def test_restore_refuses_without_scratch_flag(monkeypatch):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    rc = bak.main([
        "restore",
        "--backup-id", "user-tables-19700101T000000Z",
        "--dest-db-url", "postgresql://u:p@scratch.invalid/postgres",
        "--local-dir", "/tmp/does-not-matter",
    ])
    assert rc == bak.EXIT_USAGE


def test_restore_refuses_production_project_ref(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    dest = "postgresql://postgres.fsldfzlxyavsuwqbceod:x@aws-0-us.pooler.supabase.com:6543/postgres"
    assert bak.dest_is_production(dest)
    rc = bak.main([
        "restore",
        "--backup-id", "user-tables-19700101T000000Z",
        "--dest-db-url", dest,
        "--i-am-restoring-into-scratch",
        "--local-dir", str(tmp_path),
    ])
    assert rc == bak.EXIT_USAGE


def test_restore_refuses_exact_production_url(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co")
    dest = "https://fsldfzlxyavsuwqbceod.supabase.co"
    assert bak.dest_is_production(dest) == "project ref fsldfzlxyavsuwqbceod"


def test_retention_prunes_only_older_than_30_days():
    store = bak.MemoryStore()
    now = datetime(2026, 8, 15, 5, 17, tzinfo=timezone.utc)
    store.put("private/user-table-backups/old.tar.enc", b"old")
    store.mtime["private/user-table-backups/old.tar.enc"] = now - timedelta(days=31)
    store.put("private/user-table-backups/new.tar.enc", b"new")
    store.mtime["private/user-table-backups/new.tar.enc"] = now - timedelta(days=2)
    deleted = bak.prune_expired(store, bak.DEFAULT_PREFIX, now=now, retention_days=30)
    assert deleted == ["private/user-table-backups/old.tar.enc"]
    assert "private/user-table-backups/new.tar.enc" in store.objects


def test_retention_refuses_below_30_days():
    with pytest.raises(bak.BackupError, match=">= 30"):
        bak.prune_expired(bak.MemoryStore(), bak.DEFAULT_PREFIX, retention_days=7)


def test_dump_fail_closed_without_encryption_key(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")
    rc = bak.main(["dump", "--local-dir", str(tmp_path), "--mode", "rest"])
    assert rc == bak.EXIT_USAGE


def test_dump_fail_closed_without_source(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    rc = bak.main(["dump", "--local-dir", str(tmp_path)])
    assert rc == bak.EXIT_USAGE


def test_cli_dump_via_injected_fetcher(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", KEY)
    monkeypatch.setenv("SUPABASE_URL", "https://scratch.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")
    tables = _fixture_tables()

    def fake_fetch(name, **kwargs):
        return tables[name].rows

    monkeypatch.setattr(bak, "fetch_via_rest", fake_fetch)
    rc = bak.main(["dump", "--local-dir", str(tmp_path), "--mode", "rest"])
    assert rc == 0
    manifests = list((tmp_path / "private" / "user-table-backups").glob("*.manifest.json"))
    assert len(manifests) == 1
    enc = list((tmp_path / "private" / "user-table-backups").glob("*.tar.enc"))
    assert len(enc) == 1
    assert b"stripe_events" not in enc[0].read_bytes()


def test_redact_url_strips_password():
    url = "postgresql://postgres:supersecret@db.example.com:5432/postgres"
    redacted = bak.redact_url(url)
    assert "supersecret" not in redacted
    assert "postgres:***@db.example.com" in redacted


def test_units_are_oneshot_nightly_and_bounded():
    service = (ROOT / "app/deploy/macro-user-backup.service").read_text()
    timer = (ROOT / "app/deploy/macro-user-backup.timer").read_text()
    assert "Type=oneshot" in service
    assert "ExecStart=/opt/macro/.venv/bin/python -m scripts.backup_user_tables dump" in service
    assert "EnvironmentFile=-/etc/macro-api.env" in service
    assert "EnvironmentFile=-/etc/macro-user-backup.env" in service
    assert "RuntimeMaxSec=900" in service
    assert "TimeoutStartSec=900" in service
    assert "PrivateTmp=true" in service
    assert "OnCalendar=*-*-* 05:17:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "Unit=macro-user-backup.service" in timer


def test_update_sh_self_arms_the_backup_lane():
    script = (ROOT / "app/deploy/update.sh").read_text()
    assert '[ ! -f /etc/systemd/system/macro-user-backup.timer ]' in script
    assert 'systemd-analyze verify "${USER_BACKUP_UNIT_SOURCES[@]}"' in script
    assert "systemctl restart macro-user-backup.timer" in script
    assert "systemctl restart macro-user-backup.service" not in script
    assert "systemctl enable --now macro-user-backup.timer" in script
    assert "systemctl is-enabled macro-api.service" in script


def test_runbook_names_exact_commands_and_marks_operator_blocked():
    runbook = (ROOT / "docs/RESTORE_RUNBOOK.md").read_text()
    assert "python -m scripts.backup_user_tables dump" in runbook
    assert "python -m scripts.backup_user_tables restore" in runbook
    assert "--i-am-restoring-into-scratch" in runbook
    assert "--dest-db-url" in runbook
    assert "OPERATOR-BLOCKED" in runbook
    assert "RPO" in runbook and "RTO" in runbook
    assert "NEVER restore into production" in runbook
    assert "fsldfzlxyavsuwqbceod" in runbook
    # Gate-1 must not be papered over.
    assert "scratch-supabase restore: OPERATOR-BLOCKED" in runbook
    assert "Supabase plan / PITR: OPERATOR-BLOCKED" in runbook
