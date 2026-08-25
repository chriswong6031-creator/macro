#!/usr/bin/env python3
"""Capture the Sol-commissioned pre-final emoji reconciliation evidence.

Writes ten new screenshots without overwriting the historical 6a evidence:
six-view 1440/dark/EN first-viewport smoke plus the repaired Moving
track-record panel at 1440 and 390 in both EN and ZH. A fresh Chromium context
is used for every capture cell.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
EVIDENCE = BUILD.parent / "evidence"
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]


def capture(
    browser,
    *,
    view: str,
    width: int,
    lang: str,
    filename: str,
    selector: str | None = None,
) -> None:
    context = browser.new_context(
        viewport={"width": width, "height": 1000},
        color_scheme="dark",
        device_scale_factor=1,
    )
    page = context.new_page()
    page.goto(CANDIDATE.as_uri(), wait_until="load")
    page.wait_for_timeout(1200)
    page.evaluate(
        "([v,l])=>{document.documentElement.setAttribute('data-theme','dark');"
        "if(window.REF&&REF.setLang)REF.setLang(l);"
        "else document.documentElement.setAttribute('data-lang',l);"
        "var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
        "if(b)b.click();else location.hash='#'+v;}",
        [view, lang],
    )
    page.wait_for_timeout(900)
    out = EVIDENCE / filename
    if selector:
        target = page.locator(selector).first
        target.wait_for(state="visible")
        target.scroll_into_view_if_needed()
        page.wait_for_timeout(250)
        target.screenshot(path=str(out))
    else:
        page.screenshot(path=str(out), full_page=False)
    print(
        f"[capture] {view} {width} dark {lang}"
        f"{' ' + selector if selector else ' first-viewport'} -> {out.name}"
    )
    context.close()


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for view in VIEWS:
            capture(
                browser,
                view=view,
                width=1440,
                lang="en",
                filename=f"7a_smoke-{view}-1440-dark-en.png",
            )
        for width in (1440, 390):
            for lang in ("en", "zh"):
                capture(
                    browser,
                    view="moving",
                    width=width,
                    lang=lang,
                    filename=f"7b_moving-{width}-dark-{lang}.png",
                    selector='[data-view="moving"] .r3-tr',
                )
        browser.close()
    print("[capture] complete: 10 pre-final reconciliation screenshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
