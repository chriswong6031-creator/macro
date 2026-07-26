"""Inline-CSS externalization — lift big <style> blocks to cached hash files.

The sweep (scripts/externalize_css.py) must keep rendering byte-identical: the
CSS crosses to the external file verbatim, links replace blocks in place (cascade
+ first-paint profile preserved), tiny blocks stay inline, and orphaned hash
files are pruned — strictly within site/assets/css/. These guard those invariants.

Run: .venv/bin/python -m pytest tests/test_externalize_css.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.pages import externalize_css_text  # noqa: E402
from scripts.externalize_css import MIN_BYTES, externalize  # noqa: E402

_BIG = ".x{color:red}" + "/*" + "p" * (MIN_BYTES + 100) + "*/"  # > MIN_BYTES
_SMALL = ".y{color:blue}"  # < MIN_BYTES


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
