"""Inline-asset externalization — lift big <style>/<script> to cached hash files.

The sweep (scripts/externalize_css.py) must keep rendering byte-identical: the
CSS crosses to the external file verbatim, links replace blocks in place (cascade
+ first-paint profile preserved), tiny blocks stay inline, and orphaned hash
files are pruned — strictly within site/assets/css/. These guard those invariants.

The same sweep also lifts OPT-IN inline JS (`<script data-externalize>`) into
site/assets/js/<hash>.js under the same rules. JS is opt-in where CSS is
automatic because an inline script here routinely carries render-time data, and
a content-hashed file is served `immutable, max-age=1y` — the one place a
nightly bake must never land. The JS half of this file pins BOTH directions:
a marked block lifts, and an unmarked one never does.

Run: .venv/bin/python -m pytest tests/test_externalize_css.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import externalize_css_text, externalize_js_text  # noqa: E402
from scripts.externalize_css import MIN_BYTES, externalize  # noqa: E402

_BIG = ".x{color:red}" + "/*" + "p" * (MIN_BYTES + 100) + "*/"  # > MIN_BYTES
_SMALL = ".y{color:blue}"  # < MIN_BYTES
_BIG_JS = "(function(){var a=1;/*" + "j" * (MIN_BYTES + 100) + "*/})();"  # > MIN_BYTES
_SMALL_JS = "var y = 1;"  # < MIN_BYTES


def _href_for(recorder):
    def make_href(css, index, media):
        recorder.append((css, index, media))
        return f"assets/css/blk{index}.css?v=abc"
    return make_href


def test_big_block_becomes_link_small_stays_inline():
    rec = []
    html = f"<head><style>{_BIG}</style></head><body><style>{_SMALL}</style></body>"
    # emulate the threshold in the callback (scripts side does this)
    def make_href(css, index, media):
        if len(css.encode()) < MIN_BYTES:
            return None
        return f"assets/css/blk{index}.css?v=abc"
    out = externalize_css_text(html, make_href)
    assert '<link rel="stylesheet" href="assets/css/blk1.css?v=abc">' in out
    assert f"<style>{_SMALL}</style>" in out  # small block untouched


def test_media_attribute_carried_to_link():
    html = f'<style media="print">{_BIG}</style>'
    out = externalize_css_text(html, lambda css, i, media: f"x.css?v=1" if media is None else f"p.css?v=1")
    # media should be detected and passed through
    out2 = externalize_css_text(html, _href_for([]))
    assert 'media="print"' in out2 and out2.startswith('<link rel="stylesheet" media="print"')


def test_css_crosses_over_byte_for_byte():
    seen = []
    externalize_css_text(f"<style>{_BIG}</style>", _href_for(seen))
    assert seen[0][0] == _BIG  # exact CSS handed to writer, no mutation


def test_idempotent_no_style_blocks():
    already = '<link rel="stylesheet" href="assets/css/deadbeef.css?v=deadbeef">'
    assert externalize_css_text(already, _href_for([])) == already


def test_none_href_leaves_block_inline():
    html = f"<style>{_BIG}</style>"
    assert externalize_css_text(html, lambda *a: None) == html


def test_svg_internal_style_never_lifted():
    # A <link rel=stylesheet> inside inline SVG parses as an inert SVG-namespace
    # element (sheet never loads) — report figures rendered blank (2026-07-21).
    html = f'<figure><svg viewBox="0 0 10 10"><style>{_BIG}</style><rect/></svg></figure>'
    assert externalize_css_text(html, _href_for([])) == html


def test_svg_internal_stays_while_html_block_lifts():
    html = (
        f"<head><style>{_BIG}</style></head>"
        f"<body><svg><style>{_BIG}</style></svg></body>"
    )
    out = externalize_css_text(html, _href_for([]))
    assert out.count("<style>") == 1  # svg block kept
    assert "<svg><style>" in out  # kept exactly where it was
    assert '<link rel="stylesheet"' in out  # head block lifted


def test_nested_svg_style_stays_inline():
    inner = f"<svg><g><svg><style>{_BIG}</style></svg></g></svg>"
    assert externalize_css_text(inner, _href_for([])) == inner


def test_unclosed_svg_treated_as_svg_to_eof():
    # malformed page: opened svg never closes — err on the safe (inline) side
    html = f"<svg><style>{_BIG}</style>"
    assert externalize_css_text(html, _href_for([])) == html


# ---- end-to-end sweep (real files) ----------------------------------------

def test_sweep_externalizes_and_is_byte_identical(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    page = f"<html><head><style>{_BIG}</style></head><body>hi<style>{_SMALL}</style></body></html>"
    (site / "macro.html").write_text(page, encoding="utf-8")
    assert externalize(site) == 1
    out = (site / "macro.html").read_text()
    # big block linked, small block inline
    assert 'href="assets/css/' in out and f"<style>{_SMALL}</style>" in out
    # the external file holds the CSS verbatim
    css_files = list((site / "assets" / "css").glob("*.css"))
    assert len(css_files) == 1 and css_files[0].read_text() == _BIG
    # data-base shim survived (written via write_page)
    assert "data-dbase" in out
    # second run is a no-op (idempotent)
    assert externalize(site) == 0


def test_sweep_depth_relative_href(tmp_path):
    site = tmp_path / "site"
    sub = site / "stocks"
    sub.mkdir(parents=True)
    (sub / "AAPL.html").write_text(f"<head><style>{_BIG}</style></head><body></body>", encoding="utf-8")
    externalize(site)
    out = (sub / "AAPL.html").read_text()
    assert 'href="../assets/css/' in out  # depth-aware prefix for the sub-dir page


def test_sweep_dedupes_identical_blocks(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    for name in ("macro.html", "china.html"):
        (site / name).write_text(f"<head><style>{_BIG}</style></head><body></body>", encoding="utf-8")
    externalize(site)
    # identical CSS on both pages -> a single shared hash file
    assert len(list((site / "assets" / "css").glob("*.css"))) == 1


def test_sweep_prunes_orphans(tmp_path):
    site = tmp_path / "site"
    css = site / "assets" / "css"
    css.mkdir(parents=True)
    orphan = css / "00000000.css"
    orphan.write_text("/* nobody links me */", encoding="utf-8")
    (site / "macro.html").write_text(f"<head><style>{_BIG}</style></head><body></body>", encoding="utf-8")
    externalize(site)
    assert not orphan.exists()  # unreferenced hash file pruned
    assert list(css.glob("*.css"))  # the real (referenced) file remains


# ---- plain-copy PAIRS are excluded (ui.template_site_sync) ------------------
# templates/<name>.html shipping byte-identically as site/<name>.html cannot be
# externalized by this sweep: the render lanes run `check_template_site_sync
# --fix` after it and before `git add site/`, re-copying the site page FROM
# templates/, so a site-only lift is reverted every render — while still minting
# the hash file, which _prune_orphans can never reclaim (it looks referenced in
# the same run that creates the link). Writing THROUGH to templates/ is not the
# fix either: it would leave the hand-edited source holding only a <link> to a
# hash-named file in the derived tree. See scripts.externalize_css docstrings.

def _pair(tmp_path, name, body):
    """Create a byte-identical templates/<name> + site/<name> pair."""
    (tmp_path / "templates").mkdir(exist_ok=True)
    (tmp_path / "site").mkdir(exist_ok=True)
    for side in ("templates", "site"):
        (tmp_path / side / name).write_text(body, encoding="utf-8")


def test_sweep_skips_paired_pages_but_sweeps_the_rest(tmp_path):
    site = tmp_path / "site"
    page = f"<html><head><style>{_BIG}</style></head><body>hi</body></html>"
    _pair(tmp_path, "index.html", page)
    (site / "macro.html").write_text(page, encoding="utf-8")

    assert externalize(site) == 1  # macro only — the pair is not counted
    assert f"<style>{_BIG}</style>" in (site / "index.html").read_text()  # still inline
    assert 'href="assets/css/' in (site / "macro.html").read_text()  # unpaired lifted


def test_paired_page_stays_byte_identical_to_its_template(tmp_path):
    # The invariant the sync guard enforces, and the reason a site-only lift is
    # silently reverted: after the sweep the pair must still match byte-for-byte.
    site = tmp_path / "site"
    page = f"<html><head><style>{_BIG}</style></head><body>hi</body></html>"
    _pair(tmp_path, "chat.html", page)
    externalize(site)
    assert (site / "chat.html").read_bytes() == (tmp_path / "templates" / "chat.html").read_bytes()


def test_paired_page_css_is_never_minted_as_an_unprunable_orphan(tmp_path):
    # The measured cost of the old behaviour: 3 hash files (92,412 bytes) sat
    # committed and shipped, linked by zero pages, unprunable forever.
    site = tmp_path / "site"
    _pair(tmp_path, "index.html", f"<html><head><style>{_BIG}</style></head><body></body></html>")
    externalize(site)
    css_dir = site / "assets" / "css"
    assert not css_dir.is_dir() or not list(css_dir.glob("*.css"))


def test_subdir_page_sharing_a_pair_name_is_still_swept(tmp_path):
    # Pairs only ever ship at the site ROOT, so the skip matches the full path —
    # site/stocks/index.html is an ordinary page and must still be externalized.
    site = tmp_path / "site"
    _pair(tmp_path, "index.html", "<html><head></head><body></body></html>")
    sub = site / "stocks"
    sub.mkdir(parents=True)
    (sub / "index.html").write_text(f"<head><style>{_BIG}</style></head><body></body>", encoding="utf-8")
    externalize(site)
    assert 'href="../assets/css/' in (sub / "index.html").read_text()


def test_pair_set_comes_from_the_guard_that_enforces_it(tmp_path):
    # Imported from scripts.check_template_site_sync so the two can never drift;
    # a templates/ file with no site copy is NOT a pair and must not skip anything.
    from scripts.externalize_css import _paired_page_names

    (tmp_path / "templates").mkdir()
    (tmp_path / "site").mkdir()
    _pair(tmp_path, "index.html", "<html></html>")
    (tmp_path / "templates" / "unshipped.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "templates" / "theme.css").write_text("a{}", encoding="utf-8")
    (tmp_path / "site" / "theme.css").write_text("a{}", encoding="utf-8")

    assert _paired_page_names(tmp_path / "site") == {"index.html"}  # no .css, no unshipped


# ---- hand-authored SOURCE pages are excluded (lib.pages.HAND_AUTHORED_PAGES) --
# The flagship product pages stopped being generator output on 2026-07-28: their
# committed bytes are hand-edited source. This sweep would otherwise lift their
# large inline <style> into a hash file on the NEXT render after merge, silently
# rewriting a human's file and leaving them holding a <link> into the derived
# tree — the same objection that excluded the plain-copy pairs, arriving by a
# different route (a sub-dir page, so the pair's basename rule cannot reach it).


def _flagship_rels() -> list:
    from lib.pages import HAND_AUTHORED_PAGES
    return sorted(HAND_AUTHORED_PAGES)


def test_hand_authored_pages_keep_their_inline_style(tmp_path):
    site = tmp_path / "site"
    page = f"<html><head><style>{_BIG}</style></head><body>hi</body></html>"
    for rel in _flagship_rels():
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(page, encoding="utf-8")
    (site / "macro.html").write_text(page, encoding="utf-8")

    assert externalize(site) == 1  # macro only — the flagships are not counted
    for rel in _flagship_rels():
        text = (site / rel).read_text()
        assert f"<style>{_BIG}</style>" in text, f"{rel} was externalized"
        assert 'href="../assets/css/' not in text, f"{rel} gained a hash <link>"
    assert 'href="assets/css/' in (site / "macro.html").read_text()


def test_hand_authored_page_bytes_are_untouched(tmp_path):
    """Not merely 'still inline' — byte-identical. The sweep writes through
    write_page(), which would also inject the data-base shim into a page whose
    author deliberately laid out its <head>."""
    site = tmp_path / "site"
    page = f"<html><head><style>{_BIG}</style></head><body>hi</body></html>"
    rel = _flagship_rels()[0]
    dst = site / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(page, encoding="utf-8")
    before = dst.read_bytes()

    externalize(site)

    assert dst.read_bytes() == before, f"{rel} was rewritten by the sweep"


def test_hand_authored_page_mints_no_unprunable_orphan(tmp_path):
    """The pair lesson, re-applied: a skipped page must not leave a hash file
    behind that no page links and _prune_orphans can never reclaim."""
    site = tmp_path / "site"
    rel = _flagship_rels()[0]
    dst = site / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(f"<html><head><style>{_BIG}</style></head><body></body></html>",
                   encoding="utf-8")

    externalize(site)

    css_dir = site / "assets" / "css"
    assert not css_dir.is_dir() or not list(css_dir.glob("*.css"))


def test_hash_file_linked_only_by_hand_authored_pages_is_not_pruned(tmp_path):
    """The regression the exclusion nearly shipped.

    The committed flagships link site/assets/css/43592e0a.css TODAY — they were
    generator output until this carve-out. `referenced` is what _prune_orphans
    spares, so if excluding a page also dropped it from the reference scan, the
    very first render after merge would delete a stylesheet three live pages
    still link and ship them unstyled. Excluded means not-rewritten, never
    not-read.
    """
    site = tmp_path / "site"
    css = site / "assets" / "css"
    css.mkdir(parents=True)
    sheet = css / "43592e0a.css"
    sheet.write_text(".flagship{color:red}", encoding="utf-8")
    for rel in _flagship_rels():
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(
            '<html><head><link rel="stylesheet" '
            'href="../assets/css/43592e0a.css?v=43592e0a"></head></html>',
            encoding="utf-8")

    externalize(site)

    assert sheet.exists(), (
        "a stylesheet still linked by the hand-authored pages was pruned — "
        "excluded pages must stay in the reference scan"
    )


def test_ordinary_subdir_product_page_is_still_swept(tmp_path):
    """The exclusion is a path allowlist, not a /products/ blanket: any other
    page under products/ is ordinary output and must still be externalized."""
    site = tmp_path / "site"
    ordinary = site / "products" / "index.html"
    ordinary.parent.mkdir(parents=True, exist_ok=True)
    ordinary.write_text(f"<head><style>{_BIG}</style></head><body></body>",
                        encoding="utf-8")

    externalize(site)

    assert 'href="../assets/css/' in ordinary.read_text()


def test_exclusion_list_is_shared_with_the_estate_builder():
    """One source of truth: the sweep and build_free_content read the SAME set.

    A duplicated literal is what this pins against — the sweep skipping a page
    the builder still writes (or vice versa) is silent in both directions.
    build_free_content is imported lazily HERE, not in the sweep, precisely
    because it pulls jinja2 and the CI pack that runs this file does not
    install it; skip rather than fail if that is the venv we are in.
    """
    import pytest

    from lib.pages import HAND_AUTHORED_PAGES

    pytest.importorskip("jinja2")
    pytest.importorskip("yaml")
    from scripts.build_free_content import HAND_AUTHORED

    assert HAND_AUTHORED is HAND_AUTHORED_PAGES, (
        "build_free_content.HAND_AUTHORED must BE lib.pages.HAND_AUTHORED_PAGES, "
        "not a copy of it"
    )


def test_sweep_module_imports_without_jinja2(tmp_path):
    """The sweep must not acquire build_free_content's jinja2 dependency.

    tests/test_externalize_css.py runs in ci-main-heartbeat's
    template-site-sync pack, which installs only `pyyaml pytest`. A module-level
    `from scripts.build_free_content import HAND_AUTHORED` here would fail
    collection of this whole file in that venv while staying green locally —
    the exact shape the pack's own jinja2 comment was written about.
    """
    import subprocess

    root = Path(__file__).resolve().parent.parent
    probe = (
        "import sys;"
        "sys.modules['jinja2'] = None;"
        "import scripts.externalize_css as m;"
        "print(sorted(m.HAND_AUTHORED_PAGES))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe], cwd=root,
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"externalize_css cannot import without jinja2:\n{proc.stderr}"
    )
    assert "products/market-terminal.html" in proc.stdout


# ---------------------------------------------------------------------------
# committed-tree tripwire: a paired stylesheet must never be linked by zero pages
# ---------------------------------------------------------------------------
# #3676 lifted the landing's and chat's inline CSS into HUMAN-authored paired
# sheets (templates/chat.css, chat_nav.css, landing.css). The render lane then
# reverted part of it and NOTHING went red: scope=all render 3db5cbddb40 checked
# out main at 886fe25d89e — before #3676 merged — and its push-loop
# `git pull --rebase -X theirs` resolved the <head> hunk toward the run's
# checkout-time copy, so chat.html's 17,951-char block went back inline and
# `<link rel="stylesheet" href="chat.css">` disappeared. #3724 restored it by hand.
#
# Every existing gate stayed green through that, by construction:
#   * check_template_site_sync — the clobber hit BOTH sides identically, so the
#     pair stayed byte-identical and the sync law had nothing to say;
#   * externalize_css — it SKIPS the pairs (#3650), so nothing re-lifted the block;
#   * the orphan prune — it only reclaims site/assets/css/ hash files, never a
#     hand-authored templates/ sheet.
# What was actually observable was chat.css sitting linked by zero pages. That is
# the signal this pins, and #3724 shipped the repair without it.


def _referenced_css_names(site: Path) -> set:
    """Basenames of every stylesheet a shipped page can actually reach.

    Both hops count: a `<link href=>` on any page, and an `@import` inside any
    shipped sheet — theme.css reaches product-nav-icons.css only that way, so a
    link-only scan would call it an orphan.
    """
    import re as _re
    refs = set()
    for html in site.rglob("*.html"):
        try:
            text = html.read_text(errors="ignore")
        except OSError:
            continue
        refs.update(u.split("?")[0].split("/")[-1]
                    for u in _re.findall(r'href="([^"]+\.css[^"]*)"', text))
    for css in site.rglob("*.css"):
        try:
            text = css.read_text(errors="ignore")
        except OSError:
            continue
        refs.update(u.split("?")[0].split("/")[-1]
                    for u in _re.findall(r'@import\s+url\(\s*["\']?([^"\')]+)', text))
        refs.update(u.split("?")[0].split("/")[-1]
                    for u in _re.findall(r'@import\s+["\']([^"\']+)', text))
    return refs


def _orphaned_paired_stylesheets(root: Path) -> list:
    """Paired stylesheets (templates/<n>.css shipping as site/<n>.css) reached by nothing."""
    site, templates = root / "site", root / "templates"
    if not site.is_dir() or not templates.is_dir():
        return []
    paired = sorted(p.name for p in templates.glob("*.css") if (site / p.name).is_file())
    refs = _referenced_css_names(site)
    return [n for n in paired if n not in refs]


def test_committed_paired_stylesheets_are_never_orphaned():
    """The real tree: every hand-authored paired sheet is still reached by a page."""
    root = Path(__file__).resolve().parent.parent
    orphans = _orphaned_paired_stylesheets(root)
    assert orphans == [], (
        "paired stylesheet(s) linked by ZERO pages — a render lane's `-X theirs` "
        "most likely re-inlined the block and dropped the <link> (2026-07-26 "
        f"3db5cbddb40 did exactly this to chat.css, repaired in #3724): {orphans}"
    )


def test_orphan_tripwire_fires_when_a_page_stops_linking_its_sheet(tmp_path):
    """Guard the guard: reconstruct the #3724 shape and prove it goes red.

    Without this the scan could silently stop matching and read as green forever —
    the same failure mode that let the clobber ship unnoticed in the first place.
    """
    (tmp_path / "templates").mkdir()
    (tmp_path / "site").mkdir()
    for side in ("templates", "site"):
        (tmp_path / side / "chat.css").write_text(".c{color:red}", encoding="utf-8")
    (tmp_path / "site" / "chat.html").write_text(
        '<html><head><link rel="stylesheet" href="chat.css?v=0340e5d9"></head></html>',
        encoding="utf-8")
    assert _orphaned_paired_stylesheets(tmp_path) == []

    # the clobber: block goes back inline, the <link> disappears
    (tmp_path / "site" / "chat.html").write_text(
        "<html><head><style>.c{color:red}</style></head></html>", encoding="utf-8")
    assert _orphaned_paired_stylesheets(tmp_path) == ["chat.css"]


def test_import_only_sheet_is_not_an_orphan(tmp_path):
    """product-nav-icons.css is reached by an @import inside theme.css, never a <link>."""
    (tmp_path / "templates").mkdir()
    (tmp_path / "site").mkdir()
    for name in ("theme.css", "product-nav-icons.css"):
        for side in ("templates", "site"):
            (tmp_path / side / name).write_text("a{}", encoding="utf-8")
    (tmp_path / "site" / "theme.css").write_text(
        '@import url("product-nav-icons.css?v=7b0290e9");\nbody{color:red}', encoding="utf-8")
    (tmp_path / "site" / "p.html").write_text(
        '<html><head><link rel="stylesheet" href="theme.css"></head></html>', encoding="utf-8")
    assert _orphaned_paired_stylesheets(tmp_path) == []


# ── prune must respect pages this checkout cannot see ─────────────────────────
# _prune_orphans reads orphanhood off the pages on disk. In a partial checkout
# (sparse cone, scoped render, interrupted sync) that set is smaller than what
# actually ships, so a stylesheet a missing page still links looks unreferenced
# and is deleted — the page keeps its <link> and 404s. That is the shape behind
# us_stocks.html -> 21f5c251.css (#3988) and the start-page panel sheet (#4042).


def _git(repo, *args):
    import subprocess
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path / "site"


def test_prune_spares_a_sheet_only_an_absent_committed_page_links(tmp_path):
    site = _init_repo(tmp_path)
    css = site / "assets" / "css"
    css.mkdir(parents=True)
    (css / "abcd1234.css").write_text("/* linked by the absent page */", encoding="utf-8")
    (site / "gone.html").write_text(
        '<html><head><link rel="stylesheet" href="assets/css/abcd1234.css?v=abcd1234">'
        "</head></html>", encoding="utf-8")
    (site / "here.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "seed")

    (site / "gone.html").unlink()  # simulate the partial checkout
    externalize(site)

    assert (css / "abcd1234.css").exists(), (
        "pruned a stylesheet that a committed-but-absent page still links")


def test_prune_still_reclaims_a_truly_unreferenced_sheet_in_a_repo(tmp_path):
    """The guard must not disable pruning wholesale — no page links this one."""
    site = _init_repo(tmp_path)
    css = site / "assets" / "css"
    css.mkdir(parents=True)
    orphan = css / "00000000.css"
    orphan.write_text("/* nobody links me */", encoding="utf-8")
    (site / "macro.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "seed")

    externalize(site)
    assert not orphan.exists()


def test_absent_page_that_dropped_its_link_does_not_pin_the_sheet_forever(tmp_path):
    """Refs come from the COMMITTED bytes, so a sheet stays only while some
    committed page still links it — reclaim lags a partial checkout by one
    render, it does not stall."""
    site = _init_repo(tmp_path)
    css = site / "assets" / "css"
    css.mkdir(parents=True)
    (css / "abcd1234.css").write_text("/* stale */", encoding="utf-8")
    (site / "gone.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "seed")

    (site / "gone.html").unlink()
    externalize(site)
    assert not (css / "abcd1234.css").exists()


# ═════════════════════════════════════════════════════════════════════════════
# OPT-IN inline-JS externalization  (lib.pages.externalize_js_text)
# ═════════════════════════════════════════════════════════════════════════════
# The workspace IIFE on options.html is 68KB of static code riding in a
# short-TTL document, so it can never be cached. Lifting it to a content-hashed
# file makes it `immutable, max-age=1y` at the edge — but ONLY the static half
# may go: options.html.j2 keeps `window.OEW_TICKER_MANIFEST` in its own inline
# script precisely because a nightly-baked value inside the hash file would be
# replayed at returning visitors until some unrelated edit re-minted the hash.
# That is why the transform is opt-in, and why the tests below pin the
# not-lifted direction as hard as the lifted one.


def _src_for(recorder):
    def make_src(js, index):
        recorder.append((js, index))
        return f"assets/js/blk{index}.js?v=abc"
    return make_src


def test_marked_big_script_becomes_external_and_js_crosses_byte_for_byte():
    seen = []
    html = f"<body><script data-externalize>{_BIG_JS}</script></body>"
    out = externalize_js_text(html, _src_for(seen))
    assert out == '<body><script src="assets/js/blk1.js?v=abc"></script></body>'
    assert seen == [(_BIG_JS, 1)]  # exact JS handed to the writer, no mutation


def test_unmarked_big_script_is_never_lifted():
    """The default is INLINE. Every other inline script on this site mixes
    render-time data into its code; lifting one blind would freeze it."""
    html = f"<body><script>{_BIG_JS}</script></body>"
    assert externalize_js_text(html, _src_for([])) == html


def test_marked_small_script_stays_inline_with_its_marker():
    """Below the threshold a request costs more than the bytes save — and the
    marker survives, so the block is re-offered once it grows."""
    html = f"<body><script data-externalize>{_SMALL_JS}</script></body>"

    def make_src(js, index):
        return None if len(js.encode()) < MIN_BYTES else f"assets/js/{index}.js"

    out = externalize_js_text(html, make_src)
    assert out == html
    assert "data-externalize" in out


def test_marked_tag_that_already_has_src_is_untouched():
    """Nothing inline to lift; rewriting it would drop the real src."""
    html = '<script data-externalize src="theme.js"></script>'
    assert externalize_js_text(html, _src_for([])) == html


def test_svg_internal_marked_script_never_lifted():
    """A <script src> inside inline SVG is foreign content, not an HTML script —
    the same class of inertness that kept SVG <style> blocks inline."""
    html = f'<figure><svg viewBox="0 0 10 10"><script data-externalize>{_BIG_JS}</script></svg></figure>'
    assert externalize_js_text(html, _src_for([])) == html


def test_svg_internal_stays_while_marked_html_script_lifts():
    html = (
        f"<body><script data-externalize>{_BIG_JS}</script>"
        f"<svg><script data-externalize>{_BIG_JS}</script></svg></body>"
    )
    out = externalize_js_text(html, _src_for([]))
    assert out.count("<script data-externalize>") == 1  # svg block kept
    assert "<svg><script data-externalize>" in out
    assert '<script src="assets/js/blk1.js?v=abc"></script>' in out


def test_none_src_leaves_marked_block_inline():
    html = f"<script data-externalize>{_BIG_JS}</script>"
    assert externalize_js_text(html, lambda *a: None) == html


def test_idempotent_when_no_marked_blocks_remain():
    """The emitted tag carries no marker, so a swept page comes back untouched."""
    already = '<script src="assets/js/deadbeef.js?v=deadbeef"></script>'
    assert externalize_js_text(already, _src_for([])) == already


def test_marker_match_is_not_a_word_boundary():
    """`\\b` before an attribute NAME also matches a longer `-`-joined attribute,
    which is how a guard silently starts matching data- variants it never meant
    to. Both directions must miss."""
    for attrs in ("data-externalized", "data-externalize-off", "x-data-externalize"):
        html = f"<script {attrs}>{_BIG_JS}</script>"
        assert externalize_js_text(html, _src_for([])) == html, f"{attrs} matched the marker"


def test_index_counts_marked_candidates_only():
    seen = []
    html = (
        f"<script>{_BIG_JS}</script>"                      # unmarked — not a candidate
        f"<script data-externalize>{_BIG_JS}a</script>"    # candidate 1
        f'<script data-externalize src="x.js"></script>'   # already external
        f"<script data-externalize>{_BIG_JS}b</script>"    # candidate 2
    )
    externalize_js_text(html, _src_for(seen))
    assert [i for _js, i in seen] == [1, 2]


# ---- end-to-end sweep, JS side (real files) ---------------------------------

def test_sweep_externalizes_marked_js_and_is_byte_identical(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    page = (f"<html><head></head><body><script data-externalize>{_BIG_JS}</script>"
            f"<script data-externalize>{_SMALL_JS}</script></body></html>")
    (site / "options.html").write_text(page, encoding="utf-8")

    assert externalize(site) == 1
    out = (site / "options.html").read_text()
    assert 'src="assets/js/' in out
    assert f"<script data-externalize>{_SMALL_JS}</script>" in out  # small stays inline
    js_files = list((site / "assets" / "js").glob("*.js"))
    assert len(js_files) == 1 and js_files[0].read_text() == _BIG_JS
    assert "data-dbase" in out  # written via write_page
    assert externalize(site) == 0  # idempotent


def test_sweep_js_depth_relative_src(tmp_path):
    site = tmp_path / "site"
    sub = site / "stocks"
    sub.mkdir(parents=True)
    (sub / "AAPL.html").write_text(
        f"<head></head><body><script data-externalize>{_BIG_JS}</script></body>",
        encoding="utf-8")
    externalize(site)
    assert 'src="../assets/js/' in (sub / "AAPL.html").read_text()


def test_sweep_dedupes_identical_marked_blocks(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    for name in ("options.html", "options_screener.html"):
        (site / name).write_text(
            f"<head></head><body><script data-externalize>{_BIG_JS}</script></body>",
            encoding="utf-8")
    externalize(site)
    assert len(list((site / "assets" / "js").glob("*.js"))) == 1


def test_sweep_prunes_js_orphans_independently_of_css(tmp_path):
    """Two hash trees, two reference sets. A page that links only CSS must not
    make every JS file look referenced, and vice versa."""
    site = tmp_path / "site"
    css, js = site / "assets" / "css", site / "assets" / "js"
    css.mkdir(parents=True)
    js.mkdir(parents=True)
    (css / "11111111.css").write_text("/* linked below */", encoding="utf-8")
    (css / "00000000.css").write_text("/* nobody links me */", encoding="utf-8")
    (js / "22222222.js").write_text("/* loaded below */", encoding="utf-8")
    (js / "00000000.js").write_text("/* nobody loads me */", encoding="utf-8")
    (site / "macro.html").write_text(
        '<html><head><link rel="stylesheet" href="assets/css/11111111.css?v=11111111">'
        '</head><body><script src="assets/js/22222222.js?v=22222222"></script>'
        "</body></html>", encoding="utf-8")

    externalize(site)

    assert (css / "11111111.css").exists() and (js / "22222222.js").exists()
    assert not (css / "00000000.css").exists()
    assert not (js / "00000000.js").exists()


def test_sweep_never_prunes_named_product_assets(tmp_path):
    """Only content-addressed sweep output is eligible for orphan pruning.

    A named asset can be committed beside a template before the render lane has
    emitted the first page that references it.  Treating every ``*.js`` or
    ``*.css`` file as sweep-owned lets an unrelated fast render delete that
    product asset before its heavier page render runs.
    """
    site = tmp_path / "site"
    css, js = site / "assets" / "css", site / "assets" / "js"
    css.mkdir(parents=True)
    js.mkdir(parents=True)
    named_css = css / "earnings-wire.css"
    named_js = js / "company-intelligence-dossier.js"
    named_css.write_text("/* product-owned */", encoding="utf-8")
    named_js.write_text("/* product-owned */", encoding="utf-8")
    (site / "macro.html").write_text("<html><body></body></html>", encoding="utf-8")

    externalize(site)

    assert named_css.exists()
    assert named_js.exists()


def test_prune_spares_a_script_only_an_absent_committed_page_loads(tmp_path):
    """The #3988/#4042 shape, JS side: in a partial checkout the pages on disk
    are not the pages that ship, so orphanhood cannot be decided from them."""
    site = _init_repo(tmp_path)
    js = site / "assets" / "js"
    js.mkdir(parents=True)
    (js / "abcd1234.js").write_text("/* loaded by the absent page */", encoding="utf-8")
    (site / "gone.html").write_text(
        '<html><body><script src="assets/js/abcd1234.js?v=abcd1234"></script></body></html>',
        encoding="utf-8")
    (site / "here.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "seed")

    (site / "gone.html").unlink()  # simulate the partial checkout
    externalize(site)

    assert (js / "abcd1234.js").exists(), (
        "pruned a script that a committed-but-absent page still loads")


def test_unenumerable_checkout_skips_both_prunes(tmp_path, monkeypatch):
    """None means 'cannot prove orphanhood' — fail closed on BOTH trees, not
    just the one the guard was originally written for."""
    import scripts.externalize_css as mod

    site = tmp_path / "site"
    css, js = site / "assets" / "css", site / "assets" / "js"
    css.mkdir(parents=True)
    js.mkdir(parents=True)
    (css / "00000000.css").write_text("/* orphan */", encoding="utf-8")
    (js / "00000000.js").write_text("/* orphan */", encoding="utf-8")
    (site / "macro.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")

    monkeypatch.setattr(mod, "_committed_refs_for_absent_pages", lambda _site: None)
    externalize(site)

    assert (css / "00000000.css").exists() and (js / "00000000.js").exists()
