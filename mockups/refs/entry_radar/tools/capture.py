#!/usr/bin/env python3
"""Capture the W8 Radar reference crop matrix.

Usage: python3 tools/capture.py [base_url] [out_dir]
A static server must already be serving mockups/refs/entry_radar.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8793"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "crops")

DESKTOP = (1440, 900)
MOBILE = (390, 844)

SHOTS = [
    ("01-desktop-dark-en", DESKTOP, "theme=dark&lang=en&state=board"),
    ("02-desktop-light-en", DESKTOP, "theme=light&lang=en&state=board"),
    ("03-desktop-dark-zh", DESKTOP, "theme=dark&lang=zh&state=board"),
    ("04-desktop-light-zh", DESKTOP, "theme=light&lang=zh&state=board"),
    ("05-mobile390-dark-en", MOBILE, "theme=dark&lang=en&state=board"),
    ("06-mobile390-dark-zh", MOBILE, "theme=dark&lang=zh&state=board"),
    ("07-mobile390-light-en", MOBILE, "theme=light&lang=en&state=board"),
    ("08-mobile390-light-zh", MOBILE, "theme=light&lang=zh&state=board"),
    ("10-quiet-dark-en", DESKTOP, "theme=dark&lang=en&state=quiet"),
    ("11-quiet-light-zh", DESKTOP, "theme=light&lang=zh&state=quiet"),
    ("20-stale-dark-en", DESKTOP, "theme=dark&lang=en&state=stale"),
    ("21-degraded-dark-en", DESKTOP, "theme=dark&lang=en&state=degraded"),
    ("30-multi-dark-en", DESKTOP, "theme=dark&lang=en&state=multi"),
    ("31-multi-light-zh", DESKTOP, "theme=light&lang=zh&state=multi"),
    ("40-invalidated-dark-en", DESKTOP, "theme=dark&lang=en&state=invalidated"),
    ("41-history-dark-en", DESKTOP, "theme=dark&lang=en&state=history"),
    ("50-unavailable-dark-en", DESKTOP, "theme=dark&lang=en&state=unavailable"),
    ("51-partial-dark-en", DESKTOP, "theme=dark&lang=en&state=partial"),
    ("52-raw-dark-en", DESKTOP, "theme=dark&lang=en&state=raw"),
    ("60-c1-provisional-dark-en", DESKTOP, "theme=dark&lang=en&state=c1&drawer=1"),
    ("61-c2-variant-dark-en", DESKTOP, "theme=dark&lang=en&state=c2&drawer=1"),
    ("70-anon-dark-en", DESKTOP, "theme=dark&lang=en&state=anon"),
    ("80-ipo-dark-en", DESKTOP, "theme=dark&lang=en&state=ipo"),
    ("81-lobe-dark-en", DESKTOP, "theme=dark&lang=en&state=lobe"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (w, h), q in SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            page.wait_for_timeout(150)
            dest = OUT / f"{name}.png"
            page.screenshot(path=str(dest), full_page=True)
            print(f"wrote {dest}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
