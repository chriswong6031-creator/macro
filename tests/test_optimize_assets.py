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

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import css_imports, optimize_assets_text, preload_css_text  # noqa: E402
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
    # shim intact & blocking — inlined, so no src to version or defer
    assert "data-dbase" in out and "window.DATA_BASE" in out
    assert "data_base.js" not in out
    # second sweep is a no-op (idempotent)
    assert optimize(site) == 0


# ---------------------------------------------------------------------------
# head preload hints for late-discovered CSS (lib.pages.preload_css_text)
# ---------------------------------------------------------------------------
# Every stylesheet on these pages is render-blocking, so first paint waits for the
# LAST one — which makes *when the browser learns the URL* as costly as the bytes.
# Two structural delays put discovery late: externalize_css leaves the big sheets
# in the body (macro.html's biggest sit ~48KB into a 582KB document, past what has
# arrived on a cold mobile connection), and theme.css reaches product-nav-icons.css
# by @import, which cannot be seen until theme.css itself has downloaded — a
# guaranteed extra round-trip. The hints move discovery only; the real <link> stays
# put, so the cascade is untouched.

_IMPORTS = {"theme.css": ["product-nav-icons.css?v=7b0290e9"]}


def _imports_for(href: str):
    # mirrors the real resolver: the query is stripped before the file is read
    return _IMPORTS.get(href.split("?", 1)[0].split("/")[-1], [])


def _head_of(html: str) -> str:
    return html[: html.lower().index("</head>")]


def test_preloads_body_stylesheet_from_head():
    page = (
        '<html><head><link rel="stylesheet" href="theme.css?v=1"></head>'
        '<body><link rel="stylesheet" href="assets/css/deep.css?v=2"></body></html>'
    )
    out = preload_css_text(page, _imports_for)
    assert '<link rel="preload" as="style" href="assets/css/deep.css?v=2">' in _head_of(out)
    # the body <link> itself must NOT move — that is what preserves the cascade
    assert '<link rel="stylesheet" href="assets/css/deep.css?v=2">' in out[out.lower().index("</head>"):]
    assert out.count('rel="stylesheet"') == 2


def test_preloads_css_import_target():
    """@import is invisible until its parent sheet has downloaded AND parsed."""
    out = preload_css_text('<html><head><link rel="stylesheet" href="theme.css?v=1">'
                           "</head><body></body></html>", _imports_for)
    assert '<link rel="preload" as="style" href="product-nav-icons.css?v=7b0290e9">' in _head_of(out)


def test_preload_url_matches_stylesheet_url_exactly():
    """A hint whose URL differs by so much as a query is a second cache key — it
    would double-fetch instead of dedupe. Guards the stamp-before-preload order."""
    page = ('<html><head><link rel="stylesheet" href="theme.css?v=1"></head>'
            '<body><link rel="stylesheet" href="a.css?v=abc12345"></body></html>')
    out = preload_css_text(page, lambda h: [])
    assert 'as="style" href="a.css?v=abc12345"' in out
    assert 'href="a.css"' not in out  # never the unstamped form


def test_preload_hint_keeps_head_css_priority_and_is_idempotent():
    page = ('<html><head><link rel="stylesheet" href="theme.css?v=1"></head>'
            '<body><link rel="stylesheet" href="b.css?v=2"></body></html>')
    out = preload_css_text(page, _imports_for)
    assert out.index('href="theme.css?v=1"') < out.index('rel="preload"')
    assert preload_css_text(out, _imports_for) == out


def test_no_preload_for_sheet_already_linked_in_head():
    page = ('<html><head><link rel="stylesheet" href="theme.css?v=1">'
            '<link rel="stylesheet" href="product-nav-icons.css?v=7b0290e9">'
            "</head><body></body></html>")
    assert 'rel="preload"' not in preload_css_text(page, _imports_for)


def test_never_preloads_svg_internal_link():
    """A <link> inside inline <svg> parses as an inert SVG element and is never
    fetched — hinting it would be a pure wasted request."""
    page = ('<html><head><link rel="stylesheet" href="theme.css?v=1"></head>'
            '<body><svg><link rel="stylesheet" href="inert.css?v=9"></svg></body></html>')
    assert "inert.css" not in _head_of(preload_css_text(page, lambda h: []))


def test_preload_skips_remote_and_headless_pages():
    page = ('<html><head><link rel="stylesheet" href="theme.css?v=1"></head><body>'
            '<link rel="stylesheet" href="https://cdn.example.com/x.css"></body></html>')
    assert "cdn.example.com" not in _head_of(preload_css_text(page, lambda h: []))
    assert preload_css_text("<p>no head</p>", lambda h: []) == "<p>no head</p>"


def test_css_imports_parsing():
    assert css_imports('@import url("a.css?v=1");body{}') == ["a.css?v=1"]
    assert css_imports("@import 'b.css';") == ["b.css"]
    assert css_imports("@import url(https://x.com/c.css);") == []  # remote: not ours
    assert css_imports("body{color:red}") == []


def test_preload_sweep_end_to_end(tmp_path):
    """The real sweep: stamping must run BEFORE the hints so the URLs match."""
    site = tmp_path / "site"
    (site / "assets" / "css").mkdir(parents=True)
    (site / "theme.css").write_text('@import url("product-nav-icons.css?v=7b0290e9");\nbody{color:red}')
    (site / "product-nav-icons.css").write_text(".i{color:blue}")
    (site / "assets" / "css" / "deep.css").write_text(".d{color:green}")
    (site / "macro.html").write_text(
        '<html><head><link rel="stylesheet" href="theme.css"></head>'
        '<body><link rel="stylesheet" href="assets/css/deep.css?v=deadbeef"></body></html>'
    )
    assert optimize(site) == 1
    out = (site / "macro.html").read_text()
    head = _head_of(out)
    # theme.css got stamped, and its hint carries that same stamped URL
    assert 'href="theme.css?v=' in head
    assert '<link rel="preload" as="style" href="product-nav-icons.css?v=7b0290e9">' in head
    # deep.css arrived wearing a STALE stamp of our own shape (?v=<8 hex>). It is
    # re-hashed — a frozen stamp plus the edge's `immutable, max-age=1y` pins
    # visitors to the old bytes — and the preload hint tracks the new URL, which
    # is the invariant this test exists to protect.
    deep = re.search(r'<link rel="stylesheet" href="(assets/css/deep\.css\?v=[0-9a-f]{8})">', out)
    assert deep, out
    assert deep.group(1) != "assets/css/deep.css?v=deadbeef", "stale stamp was not refreshed"
    assert f'<link rel="preload" as="style" href="{deep.group(1)}">' in head
    assert optimize(site) == 0  # idempotent once the stamps are current
