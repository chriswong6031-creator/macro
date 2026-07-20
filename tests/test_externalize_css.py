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
