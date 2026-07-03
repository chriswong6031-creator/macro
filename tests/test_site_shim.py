"""Data-base shim regression — every site page must carry the R2 fetch shim.

The bug (nearly shipped in #1045): standalone page builders (documented usage
``python -m scripts.build_baskets``) rendered pages WITHOUT the data-base shim —
it was only added by the separate post-render step scripts/inject_data_base.py.
Committing a standalone builder's output silently stripped
``<script data-dbase src="data_base.js">`` and regressed the R2 rerouting of the
heavy per-ticker fetches. Fix: all builders write through lib.pages.write_page,
which injects the depth-aware tag at write time; the post-render sweep stays as
the idempotent safety net.

Three layers here:
  1. unit tests for lib.pages (inject_text / dbase_prefix / write_page)
  2. a repo tripwire — every COMMITTED site/**/*.html carries the marker, so a
     future write path that bypasses write_page fails CI the moment its output
     is committed
  3. a source guard — no scripts/engine module writes a literal *.html target
     with raw write_text

Run: .venv/bin/python -m pytest tests/test_site_shim.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import DBASE_MARKER, dbase_prefix, inject_text, write_page  # noqa: E402

ROOT = config.ROOT


# ---------------------------------------------------------------------------
# 1. lib.pages units
# ---------------------------------------------------------------------------

def test_inject_text_top_of_head_and_idempotent():
    html = "<!doctype html><html><head><meta charset='utf-8'></head><body>x</body></html>"
    out = inject_text(html, "")
    assert out.index(DBASE_MARKER) < out.index("<meta"), "shim must load before anything in <head>"
    assert 'src="data_base.js"' in out
    assert inject_text(out, "") == out, "second injection must be a no-op"


def test_inject_text_prefix_and_headless_fallback():
    assert 'src="../data_base.js"' in inject_text("<head></head>", "../")
    # no <head> -> lands before </body>
    out = inject_text("<html><body>x</body></html>", "")
    assert out.index(DBASE_MARKER) < out.index("</body>")


def test_dbase_prefix_depth(tmp_path):
    site = tmp_path / "site"
    (site / "basket").mkdir(parents=True)
    assert dbase_prefix(site / "baskets.html") == ""
    assert dbase_prefix(site / "basket" / "ai.html") == "../"
    # real repo paths
    assert dbase_prefix(ROOT / "site" / "macro.html") == ""
    assert dbase_prefix(ROOT / "site" / "basket" / "x.html") == "../"


def test_write_page_injects_depth_aware(tmp_path):
    site = tmp_path / "site"
    sub = site / "basket"
    sub.mkdir(parents=True)
    write_page(site / "baskets.html", "<html><head></head><body></body></html>")
    write_page(sub / "ai.html", "<html><head></head><body></body></html>")
    assert '<script data-dbase src="data_base.js">' in (site / "baskets.html").read_text()
    assert '<script data-dbase src="../data_base.js">' in (sub / "ai.html").read_text()


def test_write_page_keeps_existing_marker(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    pre = inject_text("<html><head></head><body></body></html>", "")
    write_page(site / "a.html", pre)
    assert (site / "a.html").read_text().count(DBASE_MARKER) == 1


# ---------------------------------------------------------------------------
# 2. repo tripwire — committed pages must all carry the shim
# ---------------------------------------------------------------------------

def test_every_committed_site_page_has_shim():
    site = ROOT / "site"
    missing = []
    for page in sorted(site.rglob("*.html")):
        try:
            head = page.read_text(errors="ignore")
        except OSError:
            continue
        if DBASE_MARKER not in head:
            missing.append(str(page.relative_to(site)))
    assert not missing, (
        f"{len(missing)} committed site page(s) lack the data-base shim "
        f"(R2 rerouting regression — write via lib.pages.write_page): {missing[:10]}"
    )


# ---------------------------------------------------------------------------
# 3. source guard — no raw write_text on a literal *.html target
# ---------------------------------------------------------------------------

_RAW_HTML_WRITE = re.compile(r"""\.html['")\] ]*\.write_text\(""")
# files that legitimately call write_text on page paths (the sweeps themselves)
_ALLOW = {"scripts/inject_data_base.py", "scripts/inject_wh_banner.py"}


def test_no_raw_write_text_on_html_targets():
    offenders = []
    for py in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "engine").glob("*.py")):
        rel = str(py.relative_to(ROOT))
        if rel in _ALLOW:
            continue
        for i, line in enumerate(py.read_text(errors="ignore").splitlines(), 1):
            if _RAW_HTML_WRITE.search(line):
                offenders.append(f"{rel}:{i}")
    assert not offenders, (
        "site pages must be written via lib.pages.write_page (keeps the data-base "
        f"shim in standalone builder runs): {offenders}"
    )
