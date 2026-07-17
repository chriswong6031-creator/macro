"""Manifest-clobber protection in scripts/publish_r2.py. The manifest is the
authoritative name list bulk mirrors sync AND PRUNE against, so a partial-tree
invocation (checkout holding only a dir's few git-committed files) must never
replace the full one. Pure-helper tests — no boto3/creds needed."""
from __future__ import annotations

import json
import sys

from scripts.publish_r2 import _data_dir_syncable, _manifest_doc, _manifest_ok, main


def test_no_remote_manifest_allows_put():
    ok, _ = _manifest_ok(5000, None)
    assert ok


def test_unparsable_remote_manifest_allows_put():
    assert _manifest_ok(10, {})[0]
    assert _manifest_ok(10, {"count": "garbage"})[0]
    assert _manifest_ok(10, {"count": 0})[0]


def test_same_size_replacement_allows_put():
    ok, _ = _manifest_ok(5000, {"count": 5001})
    assert ok


def test_modest_cull_allows_put():
    # e.g. the THS curation 344 -> 248 (72% kept) must not be blocked
    ok, _ = _manifest_ok(248, {"count": 344})
    assert ok


def test_partial_tree_clobber_blocked():
    # the live 2026-07-02 incident: stock_briefs checkout held only the two
    # git-committed files and replaced the engine job's ~5000-name manifest
    ok, why = _manifest_ok(2, {"count": 5000})
    assert not ok
    assert "5000 -> 2" in why


def test_floor_boundary():
    assert _manifest_ok(50, {"count": 100})[0]        # exactly half: allowed
    assert not _manifest_ok(49, {"count": 100})[0]    # under half: blocked


def test_growth_always_allowed():
    ok, _ = _manifest_ok(6000, {"count": 5000})
    assert ok


def test_partial_data_dir_tree_refused():
    # 2026-07-03 postmortem: a CI runner checkout holds only the two committed JSON
    # stubs of massive_stock_day (parquets are gitignored) — syncing it would clobber
    # the R2 store's full-history objects.
    ok, why = _data_dir_syncable("massive_stock_day", 2)
    assert not ok and "partial checkout" in why


def test_full_data_dir_tree_syncable():
    assert _data_dir_syncable("massive_stock_day", 14906)[0]
    assert _data_dir_syncable("hk_stocks_ext", 380)[0]


def test_site_dirs_never_refused():
    # The guard is data-dir-only: site trees are built fresh each run and may be small.
    assert _data_dir_syncable("stockdata", 2)[0]


def test_manifest_doc_embeds_store_manifest_for_data_dirs(tmp_path):
    store = {"store": "massive_stock_day", "latest_date": "2026-07-02",
             "coverage": {"max_missing_run_weekdays": 0}}
    (tmp_path / "_manifest.json").write_text(json.dumps(store))
    doc = _manifest_doc("massive_stock_day", tmp_path, ["SPY.parquet"])
    assert doc["count"] == 1 and doc["store"] == store


def test_manifest_doc_plain_for_site_dirs(tmp_path):
    doc = _manifest_doc("stockdata", tmp_path, ["SPY.json"])
    assert "store" not in doc


def test_manifest_doc_survives_missing_store_manifest(tmp_path):
    doc = _manifest_doc("massive_stock_day", tmp_path, ["SPY.parquet"])
    assert "store" not in doc and doc["files"] == ["SPY.parquet"]


def test_cli_flags_reach_publish(monkeypatch):
    seen = {}

    def fake_publish(dirs, dry_run=False, workers=32, manifest=True, force_manifest=False):
        seen.update(dirs=dirs, manifest=manifest, force_manifest=force_manifest)
        return 0

    monkeypatch.setattr("scripts.publish_r2.publish", fake_publish)
    monkeypatch.setattr(sys, "argv", ["publish_r2", "--dirs", "stockdata", "--no-manifest"])
    assert main() == 0
    assert seen == {"dirs": ["stockdata"], "manifest": False, "force_manifest": False}

    monkeypatch.setattr(sys, "argv", ["publish_r2", "--force-manifest"])
    main()
    assert seen["manifest"] is True and seen["force_manifest"] is True


# ── thetadata_eod registration ────────────────────────────────────────────────

def test_thetadata_eod_in_default_dirs():
    """thetadata_eod must appear in DEFAULT_DIRS (ruling A4: raw vendor pulls → R2)."""
    from scripts.publish_r2 import DEFAULT_DIRS
    assert "thetadata_eod" in DEFAULT_DIRS, (
        "thetadata_eod not registered in publish_r2.DEFAULT_DIRS — "
        "Options Alpha masterplan ruling A4 requires it"
    )


def test_thetadata_eod_in_data_dirs():
    """thetadata_eod is a data-dir store (lives under data/, not site/)."""
    from scripts.publish_r2 import _DATA_DIRS
    assert "thetadata_eod" in _DATA_DIRS


def test_thetadata_eod_partial_tree_refused():
    """Partial checkout of thetadata_eod (just the committed JSON stubs) must be refused."""
    ok, why = _data_dir_syncable("thetadata_eod", 2)
    assert not ok and "partial checkout" in why


def test_thetadata_eod_full_tree_syncable():
    """A materialised thetadata_eod store (many parquets) must be accepted."""
    from scripts.publish_r2 import _DATA_DIR_MIN_FILES
    assert _data_dir_syncable("thetadata_eod", _DATA_DIR_MIN_FILES + 1)[0]


# ── attention append-only registration (SLF-048 deep-history store) ──────────

def test_attention_in_data_dirs_not_default():
    """attention is a data-dir store (data/attention/*.parquet, gitignored; R2 holds
    2015-07→ deep history) — never a nightly DEFAULT: only the collect job's gated
    lane (or a host-side ATTENTION_STORE publish) may touch it."""
    from scripts.publish_r2 import DEFAULT_DIRS, _DATA_DIRS
    assert "attention" in _DATA_DIRS
    assert "attention" not in DEFAULT_DIRS


def test_attention_rebuilt_window_passes_min_files():
    # A restore-failed collector run recreates all ~966 filenames as real-but-short
    # files, so the min-files partial-checkout guard can NOT protect this dir —
    # that's the job of the append-only guard + the total-bytes floor.
    assert _data_dir_syncable("attention", 966)[0]


def test_append_only_guard_blocks_shorter_local():
    # shallow ~120d rebuild (≈5 KB/file) vs R2 deep-history object (≈50 KB)
    from scripts.publish_r2 import _append_only_guarded
    assert _append_only_guarded("attention", 5_000, 50_000)


def test_append_only_guard_allows_growth_equal_and_new():
    from scripts.publish_r2 import _append_only_guarded
    assert not _append_only_guarded("attention", 50_100, 50_000)  # host append: bigger
    assert not _append_only_guarded("attention", 50_000, 50_000)  # byte-equal rewrite
    assert not _append_only_guarded("attention", 5_000, None)     # no remote object yet


def test_append_only_guard_scoped_to_registered_dirs():
    # ohlc JSON legitimately shrinks between renders — must never be guarded
    from scripts.publish_r2 import _append_only_guarded
    assert not _append_only_guarded("ohlc", 5_000, 50_000)


def test_attention_shallow_rebuild_refused():
    """The per-dir bytes floor: a from-scratch collector rebuild has the deep store's
    file COUNT but ~1/6 of its bytes. It also covers the empty-remote case the
    per-file append-only guard can't compare against (fresh/wiped bucket)."""
    ok, why = _data_dir_syncable("attention", 966, total_bytes=7_400_000)
    assert not ok and "shallow rebuild" in why


def test_attention_deep_store_syncable():
    assert _data_dir_syncable("attention", 966, total_bytes=31_500_000)[0]


def test_bytes_floor_scoped_to_registered_dirs():
    """Dirs without a _DATA_DIR_MIN_BYTES entry are unaffected by tiny trees."""
    assert _data_dir_syncable("massive_stock_day", 14906, total_bytes=1)[0]
    assert _data_dir_syncable("stockdata", 2, total_bytes=1)[0]


# ── per-file upload failure tolerance ─────────────────────────────────────────
# 2026-07-16 incident: a transient network blip exhausted boto's retries on ONE
# file of the 60 GB thetadata_eod bulk sync and the whole process died. The fake
# below raises synchronously — i.e. it models the TERMINAL failure surface after
# boto's own retry loop has given up (the retry count itself is covered by
# test_client_retry_config). A single file's terminal failure must be logged/
# counted, not abort the remaining uploads — the md5/ETag delta pass self-heals
# the miss next run.

class _FakeS3:
    """Just enough boto3-client surface for publish(): empty remote listing,
    upload_file raising on selected keys, manifest get/put recording."""

    def __init__(self, fail_keys=()):
        self.fail_keys = set(fail_keys)
        self.uploaded: list[str] = []
        self.manifest_puts: list[str] = []

    def list_objects_v2(self, **kw):
        return {"Contents": [], "IsTruncated": False}

    def get_object(self, **kw):
        raise Exception("no remote manifest")

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        if key in self.fail_keys:
            raise ConnectionError(f"simulated terminal failure: {key}")
        self.uploaded.append(key)

    def put_object(self, **kw):
        self.manifest_puts.append(kw["Key"])


def _wire_fake_tree(tmp_path, monkeypatch, s3, names):
    import lib.config as config
    import scripts.publish_r2 as pr2
    d = tmp_path / "site" / "stockdata"
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_text("{}")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "load",
                        lambda: {"storage": {"site_dir": "site", "data_dir": "data"}})
    monkeypatch.setattr(pr2, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    return pr2


def test_upload_failure_does_not_abort_remaining(tmp_path, monkeypatch):
    s3 = _FakeS3(fail_keys={"stockdata/B.json"})
    pr2 = _wire_fake_tree(tmp_path, monkeypatch, s3, ["A.json", "B.json", "C.json"])
    rc = pr2.publish(["stockdata"])
    assert sorted(s3.uploaded) == ["stockdata/A.json", "stockdata/C.json"]
    assert rc == 1                    # the miss still surfaces to the lane
    assert s3.manifest_puts == []     # manifest never lists files not in place


def test_clean_publish_exits_zero_and_puts_manifest(tmp_path, monkeypatch):
    s3 = _FakeS3()
    pr2 = _wire_fake_tree(tmp_path, monkeypatch, s3, ["A.json", "B.json"])
    assert pr2.publish(["stockdata"]) == 0
    assert sorted(s3.uploaded) == ["stockdata/A.json", "stockdata/B.json"]
    assert s3.manifest_puts == ["stockdata/_manifest.json"]


def test_client_retry_config(monkeypatch):
    """The shared client (fetch_r2 reuses it) must carry the bulk-lane retry
    posture: 10 adaptive attempts, not the 4/standard that died 2026-07-16."""
    import pytest
    pytest.importorskip("boto3")
    from scripts.publish_r2 import _client
    monkeypatch.setenv("R2_ENDPOINT", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "y")
    cfg = _client().meta.config
    assert cfg.retries["mode"] == "adaptive"
    # botocore normalizes max_attempts=10 into total_max_attempts=11 (initial + 10)
    assert cfg.retries.get("total_max_attempts") == 11 or cfg.retries.get("max_attempts") == 10
    # fail-fast connect bounds the hard-down worst case (serial dir lists inside
    # daily.yml's 150-min engine job) — 10 retries must not mean 10 x 60s hangs
    assert cfg.connect_timeout == 15 and cfg.read_timeout == 60
