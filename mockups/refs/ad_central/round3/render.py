#!/usr/bin/env python3
"""Render round-3 ad creatives to PNG at exact placement sizes.

Enforces AD_MASTER_PAPER §0 AG-2 mechanically: every export's pixel size is read
back from the PNG header and must equal the canvas in the filename × scale.
Also asserts Inter actually loaded (a fallback face would silently change every
measurement that AG-3 depends on).

Usage:
    python3 render.py                 # all ads/*.html → renders/*.png @1x
    python3 render.py --scale 2       # hi-res export for upload/retina review
    python3 render.py --only desk     # substring filter
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADS = HERE / "ads"
OUT = HERE / "renders"
NAME_RE = re.compile(r"--(\d+)x(\d+)\.html$")


def png_dims(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:26]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    w, h = struct.unpack(">II", head[16:24])
    return int(w), int(h)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed — pip install playwright && playwright install chromium")
        return 2

    files = sorted(p for p in ADS.glob("*.html") if args.only in p.name)
    if not files:
        print(f"no ad files matched under {ADS}")
        return 2
    OUT.mkdir(exist_ok=True)

    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for f in files:
            m = NAME_RE.search(f.name)
            if not m:
                failures.append(f"{f.name}: filename must end --<W>x<H>.html")
                continue
            w, h = int(m.group(1)), int(m.group(2))
            page = browser.new_page(
                viewport={"width": w, "height": h}, device_scale_factor=args.scale
            )
            page.goto(f.as_uri())
            page.evaluate("document.fonts.ready.then(() => {})")
            page.wait_for_timeout(250)
            if not page.evaluate("document.fonts.check('800 20px Inter')"):
                failures.append(f"{f.name}: Inter did not load — export would ship a fallback face")
            suffix = f"@{args.scale}x" if args.scale != 1 else ""
            out = OUT / f"{f.stem}{suffix}.png"
            page.screenshot(path=str(out))
            page.close()
            pw_, ph_ = png_dims(out)
            want = (w * args.scale, h * args.scale)
            status = "ok" if (pw_, ph_) == want else "SIZE MISMATCH"
            if status != "ok":
                failures.append(f"{out.name}: {pw_}x{ph_} != {want[0]}x{want[1]}")
            print(f"{status:>13}  {out.name}  {pw_}x{ph_}  {out.stat().st_size // 1024}KB")
        browser.close()

    if failures:
        print("\nFAILED:")
        for line in failures:
            print(" -", line)
        return 1
    print(f"\n{len(files)} renders verified at exact placement size.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
