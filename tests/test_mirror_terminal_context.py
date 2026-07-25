"""Tests for scripts/mirror_terminal_context_r2 — the Terminal EOD-context R2 mirror.

OEU_MASTERPLAN §4 M-XP(b). The mirror publishes two whole-file JSON artifacts the
Terminal reads instead of waiting for a site deploy:

    site/darkpool_eod.json  →  R2  darkpool/eod.json
    site/vol/regime.json    →  R2  vol/regime.json

Contract under test:
  (a) the key map is exactly the two keys lane T-E consumes (a rename here silently
      404s the Terminal, so the mapping is pinned by test, not by convention);
  (b) never mirror a corrupt file — a half-written artifact must not replace a good
      copy already in R2 (mirror_gex_state_r2 law);
  (c) fail-soft everywhere — absent creds, absent source, and upload errors all exit 0
      and never raise, because this runs as a non-fatal nightly step.
"""
from __future__ import annotations

import json

import scripts.mirror_terminal_context_r2 as mtc


class _FakeS3:
    """Records put_object calls; can be told to fail."""

    def __init__(self, fail=False):
        self.fail = fail
        self.puts: list[tuple[str, bytes]] = []

    def put_object(self, Bucket=None, Key=None, Body=None, ContentType=None):  # noqa: N803
        if self.fail:
            raise RuntimeError("R2 unreachable")
        assert ContentType == "application/json"
        self.puts.append((Key, Body))
        return {}


def _patch_sources(monkeypatch, tmp_path, files: dict):
    """Point every mirror at tmp_path and write the given {name: text} sources."""
    written = {}
    for name in mtc.MIRRORS:
        p = tmp_path / (name + ".json")
        if name in files:
            p.write_text(files[name], encoding="utf-8")
        written[name] = p
    monkeypatch.setattr(mtc, "source_path", lambda n: written[n])
    return written


# ── (a) the key map lane T-E consumes ───────────────────────────────────────────────

def test_key_map_is_pinned():
    assert set(mtc.MIRRORS) == {"darkpool", "vol-regime"}
    assert mtc.MIRRORS["darkpool"] == ("site/darkpool_eod.json", "darkpool/eod.json")
    assert mtc.MIRRORS["vol-regime"] == ("site/vol/regime.json", "vol/regime.json")
    assert mtc.r2_key("darkpool") == "darkpool/eod.json"
    assert mtc.r2_key("vol-regime") == "vol/regime.json"
    # Sources resolve inside the repo, not the cwd.
    assert mtc.source_path("darkpool").name == "darkpool_eod.json"
    assert mtc.source_path("vol-regime").parts[-2:] == ("vol", "regime.json")


def test_uploads_both_artifacts_to_their_keys(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path,
                   {"darkpool": '{"schema":"darkpool_eod.v1"}',
                    "vol-regime": '{"schema":"vol_regime.v1"}'})
    s3 = _FakeS3()
    monkeypatch.setattr(mtc, "_r2_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bkt")

    res = mtc.mirror(list(mtc.MIRRORS))
    assert res == {"ok": 2, "skipped": 0, "failed": 0}
    assert [k for k, _ in s3.puts] == ["darkpool/eod.json", "vol/regime.json"]
    # Bytes go up verbatim — the mirror never re-serializes an artifact.
    assert json.loads(s3.puts[0][1])["schema"] == "darkpool_eod.v1"


def test_only_flag_mirrors_one(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path, {"darkpool": "{}", "vol-regime": "{}"})
    s3 = _FakeS3()
    monkeypatch.setattr(mtc, "_r2_client", lambda: s3)
    assert mtc.mirror(["vol-regime"])["ok"] == 1
    assert [k for k, _ in s3.puts] == ["vol/regime.json"]


# ── (b) never mirror a corrupt file ─────────────────────────────────────────────────

def test_corrupt_source_is_skipped_not_uploaded(monkeypatch, tmp_path):
    # A half-written artifact must NOT replace a good copy already in R2.
    _patch_sources(monkeypatch, tmp_path,
                   {"darkpool": '{"schema": "darkpool_eod.v1", "univer',   # truncated
                    "vol-regime": '{"ok":true}'})
    s3 = _FakeS3()
    monkeypatch.setattr(mtc, "_r2_client", lambda: s3)

    res = mtc.mirror(list(mtc.MIRRORS))
    assert res == {"ok": 1, "skipped": 1, "failed": 0}
    assert [k for k, _ in s3.puts] == ["vol/regime.json"]   # the good one only


def test_absent_source_is_skipped(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path, {"vol-regime": "{}"})   # darkpool never written
    s3 = _FakeS3()
    monkeypatch.setattr(mtc, "_r2_client", lambda: s3)

    res = mtc.mirror(list(mtc.MIRRORS))
    assert res == {"ok": 1, "skipped": 1, "failed": 0}
    assert [k for k, _ in s3.puts] == ["vol/regime.json"]


def test_read_valid_json_bytes(tmp_path):
    good = tmp_path / "g.json"
    good.write_text('{"a":1}')
    assert mtc.read_valid_json_bytes(good) == b'{"a":1}'
    bad = tmp_path / "b.json"
    bad.write_text("{oops")
    assert mtc.read_valid_json_bytes(bad) is None
    assert mtc.read_valid_json_bytes(tmp_path / "missing.json") is None


# ── (c) fail-soft ───────────────────────────────────────────────────────────────────

def test_no_creds_is_a_clean_skip(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path, {"darkpool": "{}", "vol-regime": "{}"})
    monkeypatch.setattr(mtc, "_r2_client", lambda: None)
    res = mtc.mirror(list(mtc.MIRRORS))
    assert res == {"ok": 0, "skipped": 2, "failed": 0}


def test_upload_failure_is_counted_not_raised(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path, {"darkpool": "{}", "vol-regime": "{}"})
    monkeypatch.setattr(mtc, "_r2_client", lambda: _FakeS3(fail=True))
    res = mtc.mirror(list(mtc.MIRRORS))
    assert res == {"ok": 0, "skipped": 0, "failed": 2}


def test_dry_run_validates_but_uploads_nothing(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path, {"darkpool": "{}", "vol-regime": "{oops"})

    def _boom():
        raise AssertionError("dry-run must never build an R2 client")

    monkeypatch.setattr(mtc, "_r2_client", _boom)
    res = mtc.mirror(list(mtc.MIRRORS), dry_run=True)
    assert res == {"ok": 1, "skipped": 1, "failed": 0}   # corrupt one still skipped


def test_main_always_exits_zero(monkeypatch, tmp_path):
    _patch_sources(monkeypatch, tmp_path, {})            # nothing on disk at all
    monkeypatch.setattr(mtc, "_r2_client", lambda: None)
    assert mtc.main([]) == 0
    assert mtc.main(["--dry-run"]) == 0
    assert mtc.main(["--only", "darkpool"]) == 0
