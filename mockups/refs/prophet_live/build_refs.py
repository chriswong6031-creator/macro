"""Shoot the Prophet Live P1 reference crops from strip.html.

    python3 mockups/refs/prophet_live/build_refs.py

Playwright PYTHON API + ``domcontentloaded`` deliberately (the CLI screenshot path
hangs waiting for load on heavy pages — house trap). Theme and language are set by
attribute, never through localStorage, so no language state bleeds between shots.

Also prints the HEIGHT-INVARIANCE proof the spec's §6.4 rule 1 demands: the strip's
outer height must be identical in live / faded / quiet / dark, so nothing below it
moves when the counts change every 5 minutes.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "strip.html").as_uri()
OUT = HERE / "shots"

# Panel-width crops only. A crop narrower than 680px re-triggers the component's own
# mobile media queries (chips collapse to the bare glyph), so a per-card crop taken in
# isolation misrepresents the desktop design — shoot the board panel instead.
SHOTS = ("strip_live", "strip_faded", "strip_quiet", "strip_dark", "cards")
VARIANTS = (("dark", "en"), ("light", "en"), ("dark", "zh"))
STRIPS = ("strip_live", "strip_faded", "strip_quiet", "strip_dark")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed: pip install playwright && playwright install chromium")
        return 1

    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1180, "height": 1400},
                                device_scale_factor=2)
        page.goto(SRC, wait_until="domcontentloaded")

        for theme, lang in VARIANTS:
            page.evaluate(
                "([t,l])=>{const h=document.documentElement;h.setAttribute('data-theme',t);"
                "if(l==='zh'){h.setAttribute('data-lang','zh')}else{h.removeAttribute('data-lang')}}",
                [theme, lang],
            )
            page.wait_for_timeout(140)
            for shot in SHOTS:
                el = page.query_selector(f'[data-shot="{shot}"]')
                if el is None:
                    print(f"  MISSING [data-shot={shot}]")
                    continue
                dest = OUT / f"{shot}_{theme}_{lang}.png"
                el.screenshot(path=str(dest))
                print(f"  {dest.relative_to(HERE.parents[2])}")

        # height invariance (spec §6.4 rule 1)
        page.evaluate("()=>{const h=document.documentElement;h.setAttribute('data-theme','dark');"
                      "h.removeAttribute('data-lang')}")
        heights = {
            s: page.evaluate(
                f"()=>document.querySelector('[data-shot=\"{s}\"]').getBoundingClientRect().height")
            for s in STRIPS
        }
        print("\nheight invariance (spec §6.4 rule 1):")
        for name, value in heights.items():
            print(f"  {name:<12} {value:.1f}px")
        distinct = {round(v, 1) for v in heights.values()}
        print(f"  => {'PASS — one height in every mode' if len(distinct) == 1 else f'FAIL — {distinct}'}")

        # mobile crops (375px): SINCE + company name demote, height unchanged, and the
        # +N button must NOT push the header onto a third line (that was a 21px shove).
        page.set_viewport_size({"width": 375, "height": 900})
        page.wait_for_timeout(160)
        for shot in ("strip_live", "strip_faded", "cards"):
            page.query_selector(f'[data-shot="{shot}"]').screenshot(
                path=str(OUT / f"{shot}_mobile_dark_en.png"))
            print(f"\n  shots/{shot}_mobile_dark_en.png (375px)")
        mob = {s: page.evaluate(
            f"()=>document.querySelector('[data-shot=\"{s}\"]').getBoundingClientRect().height")
            for s in STRIPS}
        print("  mobile heights: " + ", ".join(f"{k}={v:.1f}" for k, v in mob.items()))
        if len({round(v, 1) for v in mob.values()}) != 1:
            print("  => FAIL: mobile height is not invariant")
            distinct = {0, 1}

        browser.close()
    return 0 if len(distinct) == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
