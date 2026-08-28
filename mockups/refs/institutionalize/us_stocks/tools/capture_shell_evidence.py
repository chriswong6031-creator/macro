#!/usr/bin/env python3
"""Capture the P-MP1-SHELL §11 crop set — the SHIPPED shell, not the mockup.

Companion to gen_shell_evidence.py (same directory) and capture.py's own
convention in this directory. Requires Playwright with Chromium installed
(`pip install playwright && playwright install chromium`) — not a repo
dependency, matching capture.py's own external-tooling assumption.

Usage:
    python3 gen_shell_evidence.py default   /tmp/shell_ev
    python3 gen_shell_evidence.py empty     /tmp/shell_ev
    python3 gen_shell_evidence.py loading   /tmp/shell_ev
    python3 gen_shell_evidence.py error     /tmp/shell_ev
    python3 gen_shell_evidence.py watch-absent    /tmp/shell_ev
    python3 gen_shell_evidence.py overtime-synth  /tmp/shell_ev
    python3 gen_shell_evidence.py watch-row-synth /tmp/shell_ev
    cd /tmp/shell_ev && python3 -m http.server 8946 &
    python3 capture_shell_evidence.py http://localhost:8946 mockups/refs/institutionalize/us_stocks/shell_evidence
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8946"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "shell_evidence")
OUT.mkdir(parents=True, exist_ok=True)


def setup(page, theme="dark", lang="en"):
    page.evaluate(
        "(t,l) => { document.documentElement.setAttribute('data-theme', t); "
        "document.documentElement.setAttribute('data-lang', l); }",
        [theme, lang],
    )


def scroll_to_board(page):
    page.evaluate(
        "() => { var el = document.getElementById('us-standouts'); "
        "if (el) window.scrollTo(0, el.offsetTop - 12); }"
    )


def shoot(page, name, url, theme="dark", lang="en", width=1440, height=1400, wait=200):
    page.set_viewport_size({"width": width, "height": height})
    page.goto(url, wait_until="load")
    setup(page, theme, lang)
    scroll_to_board(page)
    page.wait_for_timeout(wait)
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("shot", name)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for theme in ("dark", "light"):
            for lang in ("en", "zh"):
                for width, tag in ((1440, "1440"), (390, "390")):
                    shoot(page, f"01-main-{theme}-{lang}-{tag}", f"{BASE}/default.html",
                          theme=theme, lang=lang, width=width)

        shoot(page, "10-empty", f"{BASE}/empty.html")
        shoot(page, "11-loading", f"{BASE}/loading.html")
        shoot(page, "12-error", f"{BASE}/error.html")
        shoot(page, "13-watch-key-absence", f"{BASE}/watch-absent.html")
        shoot(page, "14-watch-present-at-zero", f"{BASE}/default.html")

        for cell in ("ready", "entered", "delivering", "invalidated", "resolved"):
            shoot(page, f"20-filter-{cell}", f"{BASE}/default.html?life={cell}")
        shoot(page, "20-filter-watch-SYNTH", f"{BASE}/watch-row-synth.html?life=watch")
        shoot(page, "20-filter-overtime-SYNTH", f"{BASE}/overtime-synth.html?life=overtime")

        # anonymous lock (no fixture needed — the page's default state)
        shoot(page, "41-anon-lock", f"{BASE}/default.html")

        # free-tier lock — simulated via the session-storage/cookie fixture
        # tier_preview.js's own real resolveTier() consumes; no product code
        # is touched to produce this shot.
        ctx2 = browser.new_context()
        ctx2.add_cookies([{"name": "sb-fake-auth-token", "value": "x", "url": BASE}])
        page2 = ctx2.new_page()
        page2.add_init_script(
            "try { sessionStorage.setItem('mm.me', "
            "JSON.stringify({me: {tier: 'free'}, t: Date.now()})); } catch(e) {}"
        )
        shoot(page2, "40-free-tier-lock", f"{BASE}/default.html")
        ctx2.close()

        # two-episode ticker — needs the grid fully expanded and the tier
        # lock/show-more collapse neutralized for JUST this shot (an
        # `!important` CSS override, not a class-list fight against
        # tier_preview.js's own MutationObserver, which re-applies its
        # classes on any DOM mutation this shot's own unlock would trigger).
        page.goto(f"{BASE}/default.html", wait_until="load")
        setup(page)
        page.add_style_tag(content=(
            ".mx-tier-hidden,.mx-tier-blurred,.sm-hidden{display:revert!important;"
            "filter:none!important;pointer-events:auto!important;}"
            "[data-mx-tier-gate]{display:none!important;}"
        ))
        page.evaluate(
            "() => { var bs=document.querySelectorAll('#us-standouts button,#us-standouts a'); "
            "for (var b of bs) { if (/show all/i.test(b.textContent||'')) { b.click(); break; } } }"
        )
        page.wait_for_timeout(500)
        tk = page.evaluate(
            "() => { var cs=Array.from(document.querySelectorAll('#us-life-grid > .pvcard')); "
            "var byTk={}; cs.forEach(c=>{var t=c.getAttribute('data-ticker'); "
            "(byTk[t]=byTk[t]||[]).push(c);}); "
            "for (var t in byTk) if (byTk[t].length>1) return t; return null; }"
        )
        if tk:
            loc = page.locator(f'#us-life-grid > .pvcard[data-ticker="{tk}"]').first
            loc.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(200)
            page.mouse.wheel(0, -100)
            page.wait_for_timeout(150)
            page.screenshot(path=str(OUT / "30-two-episode-ticker.png"))
            print("shot 30-two-episode-ticker (ticker:", tk, ")")
        else:
            print("WARNING: no multi-episode ticker found in the current payload")

        browser.close()


if __name__ == "__main__":
    main()
