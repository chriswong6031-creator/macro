#!/usr/bin/env python3
"""Build step for Slate.

1. Stamps sw.js VERSION with a hash of the app sources, so any change rolls the
   service-worker cache for the served (PWA) form.
2. Bundles everything into a single double-clickable HTML file (Slate.html),
   stripping the served-only pieces (manifest link, apple-touch icon, SW
   registration) that don't apply on file://.

Usage: python3 build_standalone.py
"""
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Slate.html"


def sw_assets() -> list[str]:
    """The SW's own ASSETS list is the single source of truth for what gets cached —
    derive the version hash from it so the two can never drift."""
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    block = re.search(r"const ASSETS = \[(.*?)\];", sw, re.DOTALL)
    assert block, "could not locate ASSETS in sw.js"
    rels = [r for r in re.findall(r"'\./([^']*)'", block.group(1)) if r]
    assert rels, "ASSETS parsed empty"
    for rel in rels:
        assert (ROOT / rel).is_file(), f"sw.js precaches missing file: {rel}"
    return sorted(set(rels))


def stamp_service_worker() -> str:
    digest = hashlib.md5()
    for rel in sw_assets():
        digest.update(rel.encode())
        digest.update((ROOT / rel).read_bytes())
    stamp = digest.hexdigest()[:10]
    sw_path = ROOT / "sw.js"
    sw = sw_path.read_text(encoding="utf-8")
    new_sw = re.sub(r"const VERSION = 'slate-[^']*';", f"const VERSION = 'slate-{stamp}';", sw)
    assert f"slate-{stamp}" in new_sw, "VERSION stamp failed"
    if new_sw != sw:
        sw_path.write_text(new_sw, encoding="utf-8")
    return stamp


def build_single_file() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    def inline_css(m: re.Match) -> str:
        css = (ROOT / m.group(1)).read_text(encoding="utf-8")
        return "<style>\n" + css + "\n</style>"

    def inline_js(m: re.Match) -> str:
        js = (ROOT / m.group(1)).read_text(encoding="utf-8")
        return "<script>\n" + js + "\n</script>"

    # served-only pieces have no meaning on file://
    html = re.sub(r'<link rel="manifest"[^>]*>\n?', "", html)
    html = re.sub(r'<link rel="apple-touch-icon"[^>]*>\n?', "", html)
    html = re.sub(r'<script id="sw-register">.*?</script>\n?', "", html, flags=re.DOTALL)

    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">', inline_css, html)
    html = re.sub(r'<script src="([^"]+)"></script>', inline_js, html)
    assert 'rel="stylesheet"' not in html and "<script src=" not in html, "unresolved refs remain"
    assert "sw-register" not in html and 'rel="manifest"' not in html, "served-only refs remain"
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    stamp = stamp_service_worker()
    print(f"sw.js cache version: slate-{stamp}")
    build_single_file()
