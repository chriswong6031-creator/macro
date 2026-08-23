#!/usr/bin/env python3
"""R3B1-10 — document-language probe for the R3B.1 candidate.

Asserts that `document.documentElement.lang` tracks the active language through
every path that can change it, and survives the repaints that follow:

  * boot (EN);
  * the artifact's OWN language control (the harness `#ref-lang` select) — the
    path the fresh Mobile/Accessibility critic used, and the one that must work;
  * `REF.setLang()`;
  * a bare `setAttribute('data-lang', …)` by an external driver, which is how
    most QA scripts flip the switch;
  * six view activations and two hash navigations afterwards.

The expected Chinese value is `zh-CN`, not bare `zh` — this mirrors production
rather than inventing a tag: templates/theme.js:600 and :614, and
templates/_public_chrome_js.html.j2:110, all write `zh-CN`.

Usage:
    <playwright-python> lang_probe.py [--out lane_crops_b/LANG_PROBE.txt]
Exit 0 when every assertion holds, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
CANDIDATE = BUILD.parent / "proposal" / "MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html"
VIEWS = ["overview", "map", "moving", "money", "explore", "confluence"]
EXPECT = {"en": "en", "zh": "zh-CN"}


def read(page):
    return page.evaluate(
        "()=>({lang:document.documentElement.lang,"
        " dataLang:document.documentElement.getAttribute('data-lang'),"
        " navLabel:(document.querySelector('nav.si-side')||{}).ariaLabel"
        "  || (document.querySelector('nav.si-side')||{getAttribute:()=>null}).getAttribute('aria-label')})"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BUILD / "lane_crops_b" / "LANG_PROBE.txt"))
    args = ap.parse_args()
    lines: list[str] = []
    ok = True

    def check(label, got, want_lang, want_data):
        nonlocal ok
        good = got["lang"] == want_lang and got["dataLang"] == want_data
        ok = ok and good
        lines.append(f"[{'PASS' if good else 'FAIL'}] {label:<58} "
                     f"lang={got['lang']!r} data-lang={got['dataLang']!r} "
                     f"nav aria-label={got['navLabel']!r}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(CANDIDATE.as_uri(), wait_until="load")
        page.wait_for_timeout(1300)
        lines.append(f"candidate: {CANDIDATE.name}")
        check("boot", read(page), "en", "en")

        # the artifact's own control
        page.click("#ref-harness-head")
        page.select_option("#ref-lang", "zh")
        page.wait_for_timeout(500)
        check("after the page's OWN language control -> zh", read(page), "zh-CN", "zh")

        for v in VIEWS:
            page.evaluate(
                "(v)=>{var b=document.querySelector('.si-view-btn[data-view=\"'+v+'\"]');"
                "if(b)b.click();else location.hash='#'+v;}", v)
            page.wait_for_timeout(450)
        check("after activating all six views", read(page), "zh-CN", "zh")

        page.evaluate("()=>{location.hash='#si-money';}")
        page.wait_for_timeout(700)
        page.evaluate("()=>{location.hash='#overview';}")
        page.wait_for_timeout(700)
        check("after two legacy/canonical hash repaints", read(page), "zh-CN", "zh")

        page.evaluate("()=>{REF.setLang('en');}")
        page.wait_for_timeout(400)
        check("REF.setLang('en')", read(page), "en", "en")

        page.evaluate("()=>{document.documentElement.setAttribute('data-lang','zh');"
                      "document.dispatchEvent(new CustomEvent('langchange'));}")
        page.wait_for_timeout(400)
        check("bare setAttribute('data-lang','zh') by an external driver",
              read(page), "zh-CN", "zh")

        page.reload(wait_until="load")
        page.wait_for_timeout(1300)
        check("after a full reload (back to the EN default)", read(page), "en", "en")
        ctx.close()
        browser.close()

    lines.append("")
    lines.append(f"expected Chinese tag: zh-CN (production parity: templates/theme.js:600, :614; "
                 f"templates/_public_chrome_js.html.j2:110)")
    lines.append(f"RESULT: {'PASS' if ok else 'FAIL'}")
    text = "\n".join(lines)
    print(text)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"\n[lang] → {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
