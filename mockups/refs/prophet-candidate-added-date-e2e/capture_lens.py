#!/usr/bin/env python3
"""Tier-2 evidence for the "Added date" chip: the LENS popover it opens.

The chip is quiet metadata at rest; "what does this date mean, and what resets
it" is Tier 2 per docs/DESIGN_DOCTRINE.md §1. This captures the popover in both
themes and both languages, and records the TOUCH outcome for the new chip
beside the SHIPPED `.pv-mk-i` chip idiom on the same card — because both live
inside `a.pvcard`, so any link-versus-tip contention is a property of the card,
not of this chip.

Usage: <venv-with-playwright>/bin/python capture_lens.py <page-stem>
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SITE = HERE.parents[2] / "site"

LENS_STATE = """() => {
  const l = document.querySelector('.lens-pop,.lensp,[class*=lens-pop]');
  return {shown: !!l && getComputedStyle(l).display !== 'none',
          text: l ? (l.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 120) : null,
          html: document.documentElement.className,
          overlay: !!document.querySelector('.mm-terminal-lock,[class*=terminal-lock]')};
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def open_page(browser, port, stem, theme, lang, touch):
    ctx = browser.new_context(
        viewport={"width": 390 if touch else 1440, "height": 844 if touch else 900},
        device_scale_factor=2, has_touch=touch, is_mobile=touch,
        reduced_motion="reduce")
    ctx.add_init_script(
        "try{localStorage.setItem('theme',%r);localStorage.removeItem('themeAuto');"
        "localStorage.setItem('lang',%r);}catch(e){}" % (theme, lang))
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}/{stem}.html", wait_until="load", timeout=120000)
    try:
        pg.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass
    pg.wait_for_timeout(4000)
    return ctx, pg


def run(stem: str) -> None:
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(SITE)))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in ("dark", "light"):
            for lang in ("en", "zh"):
                # Tier-2 popover, desktop hover.
                ctx, pg = open_page(browser, port, stem, theme, lang, touch=False)
                chip = pg.locator("a.pvcard .pv-added").first
                chip.hover()
                pg.wait_for_timeout(1400)
                # Frame the popover together with the chip that opened it —
                # the popover is placed above the chip, so a fixed offset
                # around the chip alone crops the evidence away.
                box = pg.evaluate("""() => {
                  const c = document.querySelector('a.pvcard .pv-added');
                  const l = document.querySelector('.lens-pop,.lensp,[class*=lens-pop]');
                  const r = e => { const b = e.getBoundingClientRect();
                    return {x: b.x + scrollX, y: b.y + scrollY, w: b.width, h: b.height}; };
                  const a = r(c), b = l ? r(l) : a;
                  const x0 = Math.min(a.x, b.x), y0 = Math.min(a.y, b.y);
                  return {x: x0, y: y0,
                          w: Math.max(a.x + a.w, b.x + b.w) - x0,
                          h: Math.max(a.y + a.h, b.y + b.h) - y0};
                }""")
                pg.screenshot(
                    path=str(HERE / f"{stem}_{theme}_{lang}_1440_lens_hover.png"),
                    full_page=True,
                    clip={"x": max(0, box["x"] - 18), "y": max(0, box["y"] - 18),
                          "width": box["w"] + 36, "height": box["h"] + 36})
                st = pg.evaluate(LENS_STATE)
                print(f"{stem} {theme} {lang} HOVER shown={st['shown']} "
                      f"text={st['text']!r}")
                ctx.close()

        # Touch parity, once: the new chip vs the shipped chip idiom on the
        # same card. Anything true of both is the card's behaviour, not this
        # chip's.
        for sel, label in ((".pv-added", "NEW .pv-added"),
                           (".pv-mk-i[data-tip-en]", "SHIPPED .pv-mk-i")):
            ctx, pg = open_page(browser, port, stem, "dark", "en", touch=True)
            url0 = pg.url
            try:
                pg.locator(f"a.pvcard {sel}").first.tap(timeout=15000)
            except Exception as e:
                print(f"{label} tap error: {e}")
                ctx.close()
                continue
            pg.wait_for_timeout(1500)
            st = pg.evaluate(LENS_STATE)
            pg.screenshot(path=str(HERE / f"{stem}_touch_tap_{label.split()[0].lower()}.png"))
            print(f"{label} TAP lensShown={st['shown']} terminalOverlay={st['overlay']} "
                  f"navigated={pg.url != url0} html={st['html']!r}")
            ctx.close()
        browser.close()


if __name__ == "__main__":
    run(sys.argv[1])
