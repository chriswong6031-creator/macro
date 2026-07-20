"""Asset optimization — content-hash cache-busting + defer for local js/css.

The post-render sweep (scripts/optimize_assets.py) rewrites every same-origin
``.js``/``.css`` ref to carry ``?v=<hash>`` and marks non-critical ``<script>``
tags ``defer`` so the edge can cache them ``immutable`` (app/deploy/Caddyfile)
and the browser stops blocking the main thread on synchronous execution. These
guard the invariants that keep that safe: the data-base shim stays blocking,
external/CDN refs are untouched, and re-runs are no-ops.

Run: .venv/bin/python -m pytest tests/test_optimize_assets.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import optimize_assets_text  # noqa: E402
from scripts.optimize_assets import optimize  # noqa: E402

# a stub hasher: pretend theme.js/heatmap.js/theme.css exist, nothing else
_PRESENT = {"theme.js": "aaaa1111", "heatmap.js": "bbbb2222", "theme.css": "cccc3333"}


def _hash_for(url: str):
    return _PRESENT.get(url.split("?", 1)[0].split("#", 1)[0].lstrip("./"))


def test_versions_and_defers_local_script():
    out = optimize_assets_text('<script src="theme.js"></script>', _hash_for)
    assert out == '<script src="theme.js?v=aaaa1111" defer></script>'


def test_versions_local_stylesheet_no_defer():
    out = optimize_assets_text('<link rel="stylesheet" href="theme.css">', _hash_for)
    assert 'href="theme.css?v=cccc3333"' in out
    assert "defer" not in out  # defer is a <script>-only concept


def test_data_base_shim_untouched():
    tag = '<script data-dbase src="data_base.js"></script>'
    assert optimize_assets_text(tag, _hash_for) == tag  # must stay blocking, unversioned


def test_external_and_protocol_relative_untouched():
    for tag in (
        '<script src="https://cdn.example.com/x.js"></script>',
        '<script src="//cdn.example.com/x.js"></script>',
        '<link rel="canonical" href="https://mastermind-x.com/macro.html">',
    ):
        assert optimize_assets_text(tag, _hash_for) == tag


def test_inline_script_untouched():
    tag = "<script>var x = 1;</script>"
    assert optimize_assets_text(tag, _hash_for) == tag


def test_async_and_module_not_redeferred():
    a = optimize_assets_text('<script async src="theme.js"></script>', _hash_for)
    assert a.count("async") == 1 and "defer" not in a
    m = optimize_assets_text('<script type="module" src="theme.js"></script>', _hash_for)
    assert "defer" not in m


def test_already_queried_ref_left_alone():
    # a manual ?v=2 (or a prior run) is skipped — no double version, no re-defer
    tag = '<script src="theme.js?v=2"></script>'
    assert optimize_assets_text(tag, _hash_for) == tag


def test_missing_asset_gets_defer_but_no_version():
    out = optimize_assets_text('<script src="unknown.js"></script>', _hash_for)
    assert out == '<script src="unknown.js" defer></script>'  # defer safe; no hash to add


def test_idempotent():
    once = optimize_assets_text('<script src="theme.js"></script>', _hash_for)
    assert optimize_assets_text(once, _hash_for) == once


def test_optimize_sweep_end_to_end(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "theme.js").write_bytes(b"console.log(1)")
    (site / "heatmap.js").write_bytes(b"console.log(2)")
    page = (
        "<html><head></head><body>"
        '<script data-dbase src="data_base.js"></script>'
        '<script src="theme.js"></script>'
        '<script src="heatmap.js"></script>'
        "</body></html>"
    )
    (site / "macro.html").write_text(page)
    assert optimize(site) == 1
    out = (site / "macro.html").read_text()
    assert 'src="theme.js?v=' in out and 'src="heatmap.js?v=' in out
    assert out.count(" defer") == 2  # theme + heatmap, not the shim
    assert '<script data-dbase src="data_base.js">' in out  # shim intact & blocking
    # second sweep is a no-op (idempotent)
    assert optimize(site) == 0
