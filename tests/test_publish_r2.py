"""Manifest-clobber protection in scripts/publish_r2.py. The manifest is the
authoritative name list bulk mirrors sync AND PRUNE against, so a partial-tree
invocation (checkout holding only a dir's few git-committed files) must never
replace the full one. Pure-helper tests — no boto3/creds needed."""
from __future__ import annotations

import sys

from scripts.publish_r2 import _manifest_ok, main


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
