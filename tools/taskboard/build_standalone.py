#!/usr/bin/env python3
"""Bundle Slate into a single double-clickable HTML file (Slate.html).

Inlines css/*.css and js/*.js referenced by index.html, in order.
Usage: python3 build_standalone.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Slate.html"


def main() -> None:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    def inline_css(m: re.Match) -> str:
        href = m.group(1)
        css = (ROOT / href).read_text(encoding="utf-8")
        return "<style>\n" + css + "\n</style>"

    def inline_js(m: re.Match) -> str:
        src = m.group(1)
        js = (ROOT / src).read_text(encoding="utf-8")
        return "<script>\n" + js + "\n</script>"

    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">', inline_css, html)
    html = re.sub(r'<script src="([^"]+)"></script>', inline_js, html)
    assert 'rel="stylesheet"' not in html and "<script src=" not in html, "unresolved refs remain"
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
