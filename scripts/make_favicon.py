#!/usr/bin/env python3
"""Rasterise the Mastermind logomark (templates/favicon.svg) into the binary
favicon assets the site links: site/favicon.ico (16/32/48) and
site/apple-touch-icon.png (180, full-bleed for iOS home-screen).

One-off asset generator — NOT wired into the render pipeline (it needs a Chrome
binary + Pillow, neither guaranteed in CI). Run it by hand whenever the "M" mark
changes, then commit the regenerated site/favicon.ico + site/apple-touch-icon.png
alongside the edited templates/favicon.svg. favicon.svg itself is copied to site/
by build_site.py's asset loop, so modern browsers get the crisp vector directly;
the .ico/.png are the legacy + iOS fallbacks.

    python3 scripts/make_favicon.py

Rasteriser = headless Chrome (a dependable SVG renderer; cairosvg/rsvg aren't
installed here). Pillow packs the .ico and writes the PNG.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "templates" / "favicon.svg"
SITE = ROOT / "site"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("chrome") or "",
]

# Full-bleed variant for apple-touch-icon: iOS masks the icon to a rounded square
# itself and shows the app on an opaque tile, so we drop the rounded corners +
# transparency and let the gradient fill the whole square (the M scaled to match).
APPLE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="180" height="180">
  <defs>
    <linearGradient id="t" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#5b9dff"/><stop offset=".42" stop-color="#3b82f6"/>
      <stop offset=".74" stop-color="#6366f1"/><stop offset="1" stop-color="#7c5cff"/></linearGradient>
    <radialGradient id="g" cx=".5" cy=".38" r=".7">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".20"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>
    <linearGradient id="ink" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dbe7ff"/></linearGradient>
  </defs>
  <rect width="40" height="40" fill="url(#t)"/>
  <rect width="40" height="40" fill="url(#g)"/>
  <g transform="translate(20,20) scale(1.18) translate(-20,-20)"
     fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="3.3">
    <path d="M13 28 L13 14.5 L20 22 L27 12.5 L27 28" stroke="#15205a" stroke-opacity=".30" transform="translate(0,1.1)"/>
    <path d="M13 28 L13 14.5 L20 22 L27 12.5 L27 28" stroke="url(#ink)"/>
  </g>
</svg>"""


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    sys.exit("No Chrome/Chromium binary found — install one or edit CHROME_CANDIDATES.")


def render_png(chrome: str, svg_markup: str, size: int, out: Path, transparent: bool) -> None:
    """Render an SVG string to a size×size PNG via headless Chrome."""
    with tempfile.TemporaryDirectory() as td:
        wrapper = Path(td) / "w.html"
        wrapper.write_text(
            "<!doctype html><meta charset=utf-8>"
            "<style>html,body{margin:0;padding:0;background:transparent}"
            "svg{display:block;width:%dpx;height:%dpx}</style>%s" % (size, size, svg_markup)
        )
        bg = "00000000" if transparent else "ffffffff"
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--force-device-scale-factor=1",
            "--virtual-time-budget=2000", "--default-background-color=" + bg,
            "--screenshot=" + str(out), "--window-size=%d,%d" % (size, size),
            "--user-data-dir=" + str(Path(td) / "cr"),
            wrapper.as_uri(),
        ]
        # Chrome writes the screenshot BEFORE it (sometimes) hangs on exit, so we
        # cap the wait and then check for the file rather than trusting a clean exit.
        try:
            subprocess.run(cmd, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-9", "-f", str(Path(td) / "cr")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not out.exists():
            sys.exit("Chrome produced no screenshot for size %d" % size)


def main() -> None:
    if not SVG.exists():
        sys.exit("missing %s" % SVG)
    chrome = find_chrome()
    svg_markup = SVG.read_text()
    # strip the XML/HTML comment header so the wrapper holds a clean <svg>
    svg_markup = svg_markup[svg_markup.index("<svg"):]

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # Render one crisp high-res base, then let Pillow pack the classic ICO
        # sizes by downscaling (Pillow only *downscales* from the base, so the
        # base must be >= the largest requested size).
        base = tdp / "f256.png"
        render_png(chrome, svg_markup, 256, base, transparent=True)
        ico_path = SITE / "favicon.ico"
        Image.open(base).convert("RGBA").save(
            ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
        print("wrote", ico_path)

        # apple-touch-icon.png — 180, full-bleed, opaque
        apple = tdp / "apple.png"
        render_png(chrome, APPLE_SVG, 180, apple, transparent=False)
        apple_path = SITE / "apple-touch-icon.png"
        Image.open(apple).convert("RGB").save(apple_path, format="PNG")
        print("wrote", apple_path)

    # keep site/favicon.svg in sync with the source (build_site.py also copies it)
    shutil.copyfile(SVG, SITE / "favicon.svg")
    print("wrote", SITE / "favicon.svg")


if __name__ == "__main__":
    main()
