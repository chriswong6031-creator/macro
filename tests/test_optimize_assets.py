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

import hashlib
import re
import sys
from pathlib import Path
from unittest import mock

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
# plain-copy HTML pairs: the stamp must survive check_template_site_sync --fix
# ---------------------------------------------------------------------------
# site/index.html and site/chat.html are byte-paired plain copies of their
# templates/ source (scripts.check_template_site_sync), and no builder writes the
# site copy — `--fix` re-copying it from templates/ is the ONLY thing that does.
# Every lane runs that `--fix` AFTER this sweep, so a stamp written only site-side
# is reverted before it can reach main: the stamp was not merely stale on these
# pages, it was structurally unreachable. #3573 re-hashed our stamp shape and still
# could not move it here. Live cost (2026-07-26): #3617 fixed onboard.css at the
# origin while every returning browser kept the pre-#3617 stylesheet, because
# site/index.html still linked onboard.css?v=cfdca9e2 and the edge serves versioned
# assets `immutable, max-age=1y`. #3624 hand-bumped that one page; these pin the
# mechanism, so the next asset change does not need a human to notice.


def _pair_tree(tmp_path, page: str):
    """A repo-shaped tree with one byte-identical templates//site plain-copy pair."""
    site, templates = tmp_path / "site", tmp_path / "templates"
    site.mkdir()
    templates.mkdir()
    (site / "theme.js").write_bytes(b"console.log('new bytes')")
    (templates / "index.html").write_text(page)
    (site / "index.html").write_text(page)
    return site, templates


def test_paired_template_is_restamped_so_fix_cannot_revert_it(tmp_path):
    from scripts.check_template_site_sync import check

    site, templates = _pair_tree(
        tmp_path, '<html><head><script src="theme.js?v=deadbeef" defer></script></head></html>'
    )
    # both sides move: templates/ is what --fix will copy back over site/. (The pair pass
    # runs first and syncs the site copy itself, so the later walk finds nothing to do —
    # assert the end state, not the write count.)
    assert optimize(site) >= 1
    assert (site / "index.html").read_text() == (templates / "index.html").read_text()
    fresh = re.search(r'theme\.js\?v=([0-9a-f]{8})', (templates / "index.html").read_text())
    assert fresh and fresh.group(1) != "deadbeef", "templates/ side kept the stale stamp"

    # The lane's next step — this is what used to throw the stamp away. It may well
    # restore the site copy (write_page injects the data-base shim, which templates/
    # must never carry), but what it restores now carries the FRESH stamp.
    check(tmp_path, fix=True)
    out = (site / "index.html").read_text()
    assert out == (templates / "index.html").read_text(), "pair left diverged"
    assert f"theme.js?v={fresh.group(1)}" in out
    assert "v=deadbeef" not in out

    # and the sweep is a true fixed point afterwards (the acceptance condition)
    assert optimize(site) == 0


def test_pair_converges_even_when_a_normalizer_rewrote_the_site_copy(tmp_path):
    """The real lane shape: inject_data_base/externalize_css rewrite the site copy
    before this sweep runs, so the pair is already diverged on entry. It must still
    converge on a fresh stamp — whether the same-pass sync or a later `--fix` is what
    re-copies the template over it."""
    from scripts.check_template_site_sync import check

    site, templates = _pair_tree(
        tmp_path, '<html><head><script src="theme.js?v=deadbeef" defer></script></head></html>'
    )
    (site / "index.html").write_text(  # stand in for the normalizers' rewrite
        '<html><head><style>.a{}</style><script src="theme.js?v=deadbeef" defer></script></head></html>'
    )
    optimize(site)
    check(tmp_path, fix=True)           # the lane's next step, whether or not it has work
    out = (site / "index.html").read_text()
    assert "v=deadbeef" not in out, "the pair converged on the STALE templates/ stamp"
    assert out == (templates / "index.html").read_text(), "pair left diverged"
    assert optimize(site) == 0, "not a fixed point after the pair converged"


def test_pair_is_stamped_before_the_site_walk(tmp_path):
    """Ordering is load-bearing: the pair must be done BEFORE the 3.2k-page site walk.

    Historically the lane committed on cancellation, so a kill during this sweep could
    land a half-done tree. The publish gate now rejects that state, while pair-first keeps
    the normalizer itself interruption-safe for every caller.
    """
    site, templates = _pair_tree(
        tmp_path, '<html><head><script src="theme.js?v=deadbeef" defer></script></head></html>'
    )
    # a site page that sorts AFTER index.html, so the walk would reach it late
    (site / "zzz.html").write_text('<html><head><script src="theme.js?v=deadbeef"></script></head></html>')

    order = []
    real = Path.write_text

    def spy(self, data, *a, **kw):
        order.append(str(self.relative_to(tmp_path)))
        return real(self, data, *a, **kw)

    with mock.patch.object(Path, "write_text", spy):
        optimize(site)

    tpl_writes = [i for i, p in enumerate(order) if p.startswith("templates/")]
    walk_writes = [i for i, p in enumerate(order) if p == "site/zzz.html"]
    assert tpl_writes, "the paired template was never written"
    assert walk_writes, "the site walk never ran (fixture broken)"
    assert min(tpl_writes) < min(walk_writes), (
        f"the site walk started before the pair was stamped (order={order}) — a "
        "cancellation mid-walk would commit a DIVERGED pair that --fix cannot repair")


def test_unpaired_template_is_never_written(tmp_path):
    """A templates/ file with no site/ counterpart is a source, not a shipped pair."""
    site, templates = _pair_tree(tmp_path, "<html><head></head></html>")
    lone = templates / "unshipped.html"
    lone.write_text('<html><head><script src="theme.js?v=deadbeef"></script></head></html>')
    j2 = templates / "page.html.j2"
    j2.write_text('<script src="theme.js?v=deadbeef"></script>')
    optimize(site)
    assert "v=deadbeef" in lone.read_text(), "wrote a template that does not ship as site/"
    assert "v=deadbeef" in j2.read_text(), "wrote a .j2 render input"


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


def test_existing_stale_preload_tracks_the_real_stylesheet_url():
    """A pre-existing hint is a mirror, not an independently frozen cache key.

    PR #4015's fast lane advanced the real navigation stylesheet on every page
    but left the old preload URL in place, so browsers fetched both versions.
    """
    page = (
        '<html><head><link rel="preload" as="style" href="navigation-refresh.css?v=deadbeef">'
        '</head><body><link rel="stylesheet" '
        'href="navigation-refresh.css?v=f38c6288"></body></html>'
    )
    out = preload_css_text(page, lambda h: [])
    assert "navigation-refresh.css?v=deadbeef" not in out
    assert out.count("navigation-refresh.css?v=f38c6288") == 2
    assert preload_css_text(out, lambda h: []) == out


def test_preload_refresh_never_rewrites_a_non_style_hint():
    page = (
        '<html><head><link rel="preload" as="script" href="app.css?v=deadbeef">'
        '</head><body><link rel="stylesheet" href="app.css?v=f38c6288"></body></html>'
    )
    out = preload_css_text(page, lambda h: [])
    assert 'as="script" href="app.css?v=deadbeef"' in out
    assert 'as="style" href="app.css?v=f38c6288"' in out


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


# ---------------------------------------------------------------------------
# `--fix` heals in ONE direction, so it must know when that direction is wrong
# ---------------------------------------------------------------------------
# The pair law's repair is templates/ -> site/, which is right for the case it was
# written for (a PR edits a template one-sidedly) and wrong for the case a render
# lane produces: 2026-07-26 push 886fe25d89e advanced site/chat.html to
# theme.js?v=c094a665 plus the product-nav-icons preload and left
# templates/chat.html at ?v=16dc65dc. No PR was involved, so no PR gate could see
# it; `--fix` then offered to "heal" the pair by re-pinning every returning browser
# to bytes theme.js no longer had, under `immutable, max-age=1y` at the edge. It
# printed FIXED either way — a clobber and a heal were indistinguishable, which is
# how the wrong direction stayed invisible. #3676 healed it by hand the other way.
# These pin the asymmetric evidence rule: refuse only on a stamp that PROVABLY
# contradicts the file it names, never on absence.


def _stale_pair(tmp_path, tpl: str, site_page: str):
    """A tree whose site/ carries a real app.js the pages' stamps can be judged against."""
    site, templates = tmp_path / "site", tmp_path / "templates"
    site.mkdir()
    templates.mkdir()
    (site / "app.js").write_text("var live = 1;\n")
    live = hashlib.sha256((site / "app.js").read_bytes()).hexdigest()[:8]
    (templates / "page.html").write_text(tpl.replace("{LIVE}", live))
    (site / "page.html").write_text(site_page.replace("{LIVE}", live))
    return site, templates, live


def test_fix_refuses_to_clobber_a_site_copy_whose_stamps_are_current(tmp_path):
    """The render-lane shape: site/ is the fresher side, so the copy must not run."""
    from scripts.check_template_site_sync import check

    site, _templates, live = _stale_pair(
        tmp_path,
        '<script src="app.js?v=deadbeef" defer></script>\n',
        '<script src="app.js?v={LIVE}" defer></script>\n<link rel="preload" href="app.js?v={LIVE}">\n',
    )
    before = (site / "page.html").read_bytes()

    assert check(tmp_path, fix=True) == ["page.html"]
    assert check.refused == ["page.html"], "wrong-direction --fix was not refused"
    assert (site / "page.html").read_bytes() == before, "--fix clobbered the current site copy"
    assert f"app.js?v={live}" in (site / "page.html").read_text()
    # and it stays loud: a refused pair is still diverged, never reported as healed
    assert check(tmp_path) == ["page.html"]


def test_fix_still_heals_a_template_that_is_legitimately_ahead(tmp_path):
    """A one-sided PR reword — every stamp current on both sides — must still copy."""
    from scripts.check_template_site_sync import check

    site, _templates, live = _stale_pair(
        tmp_path,
        '<script src="app.js?v={LIVE}" defer></script>\n<p>calibration-gated</p>\n',
        '<script src="app.js?v={LIVE}" defer></script>\n<p>validated</p>\n',
    )
    assert check(tmp_path, fix=True) == ["page.html"]
    assert check.refused == [], "refused an ordinary one-sided template edit"
    assert "calibration-gated" in (site / "page.html").read_text()
    assert check(tmp_path) == []


def test_a_ref_the_template_dropped_is_not_evidence_of_staleness(tmp_path):
    """Deleting a <link> in templates/ is a legitimate edit, not a stale stamp."""
    from scripts.check_template_site_sync import check

    site, _templates, _live = _stale_pair(
        tmp_path,
        '<script src="app.js?v={LIVE}" defer></script>\n',
        '<script src="app.js?v={LIVE}" defer></script>\n<link rel="preload" href="app.js?v={LIVE}">\n',
    )
    assert check(tmp_path, fix=True) == ["page.html"]
    assert check.refused == [], "absence of a ref was treated as staleness"
    assert "preload" not in (site / "page.html").read_text(), "the deletion did not propagate"


def test_a_hand_written_query_is_never_judged(tmp_path):
    """Only OUR ?v=<8 hex> stamp is audited — `?v=3` is authored, not derived."""
    from scripts.check_template_site_sync import check

    _site, _templates, _live = _stale_pair(
        tmp_path,
        '<script src="app.js?v=3" defer></script>\n<p>a</p>\n',
        '<script src="app.js?v=3" defer></script>\n<p>b</p>\n',
    )
    assert check(tmp_path, fix=True) == ["page.html"]
    assert check.refused == [], "a hand-written query was audited as our stamp"
