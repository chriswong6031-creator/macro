"""`?v=` stamps must stay CURRENT, not merely stable.

`app/deploy/Caddyfile` serves versioned asset requests `Cache-Control: immutable,
max-age=1y`. That is only safe if the stamp moves when the file does — and it did
not: `optimize_assets_text` skipped any ref that already carried a query, so a
stamp committed into a page froze at whatever the asset contained that day. On
2026-07-26 `theme.js` was stamped stale on 1,509 pages across four generations of
hash, and #3560's onboard.css/js changes landed under frozen stamps on the
landing.

These pin the fixed contract: our own stamp is re-hashed, everything else the
author wrote is left alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.pages import optimize_assets_text  # noqa: E402

HASHES = {
    "theme.js": "aaaaaaaa",
    "onboard.css": "bbbbbbbb",
    "../theme.js": "aaaaaaaa",
    "assets/css/deadbeef.css": "cccccccc",
}


def _hash_for(url: str):
    return HASHES.get(url)


def _rw(html: str) -> str:
    return optimize_assets_text(html, _hash_for)


def test_stale_stamp_is_refreshed():
    out = _rw('<script src="theme.js?v=015c6c36" defer></script>')
    assert 'src="theme.js?v=aaaaaaaa"' in out
    assert "015c6c36" not in out


def test_stale_stamp_refreshed_at_any_depth():
    out = _rw('<script src="../theme.js?v=16dc65dc" defer></script>')
    assert 'src="../theme.js?v=aaaaaaaa"' in out


def test_stale_css_stamp_is_refreshed():
    out = _rw('<link rel="stylesheet" href="onboard.css?v=233832f9">')
    assert 'href="onboard.css?v=bbbbbbbb"' in out


def test_current_stamp_is_a_no_op():
    src = '<script src="theme.js?v=aaaaaaaa" defer></script>'
    assert _rw(src) == src


def test_rerun_is_idempotent():
    once = _rw('<script src="theme.js"></script>')
    assert _rw(once) == once


def test_unstamped_ref_still_gets_a_stamp_and_defer():
    out = _rw('<script src="theme.js"></script>')
    assert 'src="theme.js?v=aaaaaaaa"' in out
    assert "defer" in out


def test_hand_written_query_is_left_alone():
    """Only our exact `?v=<8 hex>` shape is ours to rewrite."""
    for src in (
        '<script src="theme.js?v=3" defer></script>',            # not 8 hex
        '<script src="theme.js?v=ZZZZZZZZ" defer></script>',     # not hex
        '<script src="theme.js?foo=bar" defer></script>',        # someone else's query
        '<script src="theme.js?v=aaaaaaaa&x=1" defer></script>',  # more than the stamp
    ):
        assert _rw(src) == src, f"rewrote a ref that was not ours: {src}"


def test_fragment_is_left_alone():
    src = '<link href="theme.js#frag">'
    assert _rw(src) == src


def test_cross_origin_is_left_alone():
    src = '<script src="https://js.stripe.com/v3"></script>'
    assert _rw(src) == src


def test_unhashable_asset_keeps_its_existing_stamp():
    # hash_for() returns None (file missing on disk) — do not strip what is there
    out = _rw('<script src="unknown.js?v=deadbeef"></script>')
    assert "unknown.js?v=deadbeef" in out


def test_data_base_shim_is_never_touched():
    src = '<script data-dbase src="data_base.js?v=012345ab"></script>'
    assert _rw(src) == src


def test_preload_hint_is_never_restamped():
    """A `rel=preload` hint mirrors a URL owned elsewhere — `preload_css_text`
    copies it from the stylesheet, or from an `@import` this sweep never
    rewrites. Bumping the hint alone makes it a second cache key and double-
    fetches the file, and it broke `optimize()` idempotency when it did."""
    for src in (
        '<link rel="preload" as="style" href="onboard.css?v=233832f9">',
        '<link rel="modulepreload" href="theme.js?v=015c6c36">',
        '<link rel="prefetch" href="theme.js?v=015c6c36">',
    ):
        assert _rw(src) == src, f"re-stamped a hint that mirrors someone else's URL: {src}"


def test_stylesheet_link_is_still_restamped():
    out = _rw('<link rel="stylesheet" href="onboard.css?v=233832f9">')
    assert 'href="onboard.css?v=bbbbbbbb"' in out
