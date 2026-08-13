#!/usr/bin/env python3
"""Capture the MP-1 mockup-gate crop set.

Usage:  python3 tools/capture.py [base_url] [out_dir]
        (a static server must already be serving this directory)

Produces the factory §0.2 matrix — light + dark x EN + ZH x 1440 + 390w — plus
the forced states the packet requires as review-blocking evidence.
"""
import sys
import pathlib
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8791"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "crops")

DESKTOP = (1440, 900)
MOBILE = (390, 844)

# name, viewport, query
SHOTS = [
    # ── the required matrix ────────────────────────────────────────────────
    ("01-desktop-dark-en",        DESKTOP, "theme=dark&lang=en&state=paid"),
    ("02-desktop-light-en",       DESKTOP, "theme=light&lang=en&state=paid"),
    ("03-desktop-dark-zh",        DESKTOP, "theme=dark&lang=zh&state=paid"),
    ("04-mobile390-dark-en",      MOBILE,  "theme=dark&lang=en&state=paid"),
    ("05-mobile390-dark-zh",      MOBILE,  "theme=dark&lang=zh&state=paid"),
    # ── completing the light/zh corners of the matrix ──────────────────────
    ("06-desktop-light-zh",       DESKTOP, "theme=light&lang=zh&state=paid"),
    ("07-mobile390-light-en",     MOBILE,  "theme=light&lang=en&state=paid"),
    # ── required states ────────────────────────────────────────────────────
    ("10-anon-locked-dark-en",    DESKTOP, "theme=dark&lang=en&state=anon"),
    ("11-anon-locked-light-zh",   DESKTOP, "theme=light&lang=zh&state=anon"),
    ("12-filtered-invalidated",   DESKTOP, "theme=dark&lang=en&state=paid&life=invalidated"),
    ("13-filtered-invalidated-zh", DESKTOP, "theme=light&lang=zh&state=paid&life=invalidated"),
    ("14-empty-dark-en",          DESKTOP, "theme=dark&lang=en&state=empty"),
    ("15-empty-light-zh",         DESKTOP, "theme=light&lang=zh&state=empty"),
    ("16-multi-episode-en",       DESKTOP, "theme=dark&lang=en&state=episodes"),
    ("17-multi-episode-zh",       DESKTOP, "theme=light&lang=zh&state=episodes"),
    ("18-multi-episode-resolved", DESKTOP, "theme=dark&lang=en&state=episodes&life=resolved"),
    ("19-multi-episode-390-en",   MOBILE,  "theme=dark&lang=en&state=episodes"),
    # ── per-cell ladder filters (packet §11: each of the seven active) ─────
    ("20-life-watch",             DESKTOP, "theme=dark&lang=en&state=paid&life=watch"),
    ("21-life-ready",             DESKTOP, "theme=dark&lang=en&state=paid&life=ready"),
    ("22-life-entered",           DESKTOP, "theme=dark&lang=en&state=paid&life=entered"),
    ("23-life-delivering",        DESKTOP, "theme=dark&lang=en&state=paid&life=delivering"),
    ("24-life-overtime",          DESKTOP, "theme=dark&lang=en&state=paid&life=overtime"),
    ("25-life-invalidated",       DESKTOP, "theme=dark&lang=en&state=paid&life=invalidated"),
    ("26-life-resolved",          DESKTOP, "theme=dark&lang=en&state=paid&life=resolved"),
    # ── table view: rendered rows == cell count, no remainder ─────────────
    ("30-table-invalidated",      DESKTOP, "theme=dark&lang=en&state=paid&life=invalidated&view=table"),
    ("31-table-resolved-zh",      DESKTOP, "theme=light&lang=zh&state=paid&life=resolved&view=table"),
]


# full-page captures are opt-in: a full-page 390w shot is ~4000px tall, and the
# gate is reviewed on the above-fold composition. These are the views where the
# whole-page rhythm (three count-bearing devices, §G.2) is the thing being judged.
FULL_PAGE = {
    "01-desktop-dark-en", "02-desktop-light-en", "03-desktop-dark-zh",
    "04-mobile390-dark-en", "05-mobile390-dark-zh",
    "10-anon-locked-dark-en", "14-empty-dark-en", "16-multi-episode-en",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    n_files = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (w, h), q in SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            page.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            page.wait_for_timeout(220)

            # a horizontal page scroll is an acceptance failure, not a nit
            over = page.evaluate(
                "() => ({sw: document.documentElement.scrollWidth,"
                " cw: document.documentElement.clientWidth})")
            flag = "  << HORIZONTAL SCROLL" if over["sw"] > over["cw"] else ""

            page.screenshot(path=str(OUT / f"{name}.png"))                 # above-fold
            n_files += 1
            if name in FULL_PAGE:
                page.screenshot(path=str(OUT / f"{name}--full.png"), full_page=True)
                n_files += 1
            made.append(f"{name}  {w}x{h}  sw={over['sw']} cw={over['cw']}{flag}")
            page.close()
        browser.close()
    print("\n".join(made))
    print(f"\n{len(made)} views -> {n_files} files in {OUT}/")


if __name__ == "__main__":
    main()
