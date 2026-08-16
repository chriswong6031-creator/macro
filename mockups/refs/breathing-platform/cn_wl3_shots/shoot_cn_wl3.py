#!/usr/bin/env python3
"""CN-W-L3 / CN-PR-3 browser acceptance — crop shooter (§9 "Browser acceptance").

    python3 mockups/refs/breathing-platform/cn_wl3_shots/shoot_cn_wl3.py

WHAT IS AND IS NOT SYNTHETIC HERE, because that is the whole value of this proof.

  REAL: ``site/china_stocks.html`` exactly as the last asia bake wrote it — 107 cards, board
  as-of 2026-08-14 — plus every real stylesheet and script the page loads. Nothing about the
  board is mocked. The frozen N−1 render IS half the acceptance.

  SYNTHETIC: (1) the payload, from ``gen_fixtures.py``; (2) the two lines
  ``templates/china.html.j2`` now emits, injected here byte-for-byte as the template renders
  them, because the shipped HTML predates this PR; (3) the browser clock, frozen per case.

WHY THE CLOCK IS FROZEN. Every window in the client is an Asia/Shanghai window, so lunch can
only be photographed at lunch and a close board only after 15:00 CST. Freezing the page's
``Date`` is the only way to shoot six phases in one run — and it is also what makes the
refusal crop a real proof: case (g) runs with the clock at 2026-08-13, where the N−2 payload
passes the schema gate, the same-day gate AND the age gate, and is refused by the feed floor
ALONE. A refusal that could be explained by the calendar would prove nothing about the floor.

NOTHING IS WRITTEN INTO ``site/``. The serving root is a scratch tree of symlinks with three
overrides: the patched page, and a ``live/`` holding the fixture under test.
"""
from __future__ import annotations

import functools
import http.server
import json
import pathlib
import shutil
import socketserver
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SITE = ROOT / "site"
FIX = HERE / "fixtures"

#: Byte-for-byte what templates/china.html.j2 now renders (the anchor's data-session is the
#: board's own as_of, which on this bake is 2026-08-14).
ANCHOR = '<div id="cn-live-board" data-session="2026-08-14" hidden></div>'
ANCHOR_AT = '<div id="st-count-chips" style="display:none"></div>'
SCRIPT = '<script src="cn_prophet_live.js" defer></script>'
SCRIPT_AT = '<script defer src="illus.js'

#: case → (fixture, frozen CST wall time, lang, theme, viewport, note)
CASES = [
    ("a_intraday_en_desktop", "intraday_afternoon",   "2026-08-15T14:14:00", "en", "dark",  (1440, 1000)),
    ("b_intraday_zh_desktop", "intraday_afternoon",   "2026-08-15T14:14:00", "zh", "dark",  (1440, 1000)),
    ("c_close_board_en",      "close_board",          "2026-08-15T15:09:00", "en", "dark",  (1440, 1000)),
    ("d_close_board_zh",      "close_board",          "2026-08-15T15:09:00", "zh", "dark",  (1440, 1000)),
    ("e_mobile_390_en",       "intraday_afternoon",   "2026-08-15T14:14:00", "en", "dark",  (390, 900)),
    ("f_session_break_zh",    "session_break",        "2026-08-15T12:20:00", "zh", "dark",  (1440, 1000)),
    ("g_failclosed_stale_en", "stale_prior_session",  "2026-08-13T14:02:00", "en", "dark",  (1440, 1000)),
    # Light mode is a design target, not a translation (DESIGN_DOCTRINE §5.8) — both the
    # intraday strip and the close banner are judged on white, not merely rendered on it.
    ("h_intraday_en_light",   "intraday_afternoon",   "2026-08-15T14:14:00", "en", "light", (1440, 1000)),
    ("i_close_board_zh_light", "close_board",         "2026-08-15T15:09:00", "zh", "light", (1440, 1000)),
    ("j_close_pending_en",    "close_pending",        "2026-08-15T15:11:00", "en", "dark",  (1440, 1000)),
]


def _clock_shim(iso_cst: str) -> str:
    """Freeze the page's wall clock at an Asia/Shanghai instant.

    Only ``Date.now()`` and the no-argument ``new Date()`` are frozen — ``Date.parse``,
    ``new Date(x)`` and ``Intl`` stay real, so the client's own Shanghai conversions are
    still doing the work they do in production. CST is UTC+8 year-round (no DST), which is
    why the epoch is arithmetic rather than a timezone lookup."""
    import datetime as _dt
    naive = _dt.datetime.fromisoformat(iso_cst)
    epoch_ms = int((naive - _dt.timedelta(hours=8)).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
    return """(function(){var F=%d,_D=Date;
function D(a,b,c,d,e,f,g){if(arguments.length===0)return new _D(F);
if(arguments.length===1)return new _D(a);return new _D(a,b,c,d,e,f,g);}
D.prototype=_D.prototype;D.now=function(){return F;};D.parse=_D.parse;D.UTC=_D.UTC;
window.Date=D;})();""" % epoch_ms


def build_root(tmp: pathlib.Path, fixture: str) -> None:
    """Symlink the real site tree, then override the page and live/."""
    tmp.mkdir(parents=True, exist_ok=True)
    for child in SITE.iterdir():
        if child.name in ("china_stocks.html", "live"):
            continue
        (tmp / child.name).symlink_to(child)
    live = tmp / "live"
    live.mkdir()
    for child in (SITE / "live").iterdir():
        (live / child.name).symlink_to(child)
    shutil.copy(FIX / f"{fixture}.json", live / "cn_prophet_live.json")

    html = (SITE / "china_stocks.html").read_text()
    assert ANCHOR_AT in html, "anchor insertion point vanished from the rendered page"
    assert SCRIPT_AT in html, "script insertion point vanished from the rendered page"
    html = html.replace(ANCHOR_AT, ANCHOR + ANCHOR_AT, 1)
    i = html.index(SCRIPT_AT)
    html = html[:i] + SCRIPT + html[i:]
    (tmp / "china_stocks.html").write_text(html)


def serve(root: pathlib.Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not (FIX / "intraday_afternoon.json").exists():
        print("fixtures missing — run gen_fixtures.py first", file=sys.stderr)
        return 2

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, fixture, when, lang, theme, (vw, vh) in CASES:
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="cnwl3-"))
            root = tmp / "root"
            build_root(root, fixture)
            httpd, port = serve(root)
            try:
                ctx = browser.new_context(viewport={"width": vw, "height": vh},
                                          device_scale_factor=2,
                                          locale="zh-CN" if lang == "zh" else "en-US")
                page = ctx.new_page()
                page.add_init_script(_clock_shim(when))
                # Language and theme are page state the site persists itself; set them
                # before first paint so nothing is captured mid-swap.
                page.add_init_script(
                    "try{localStorage.setItem('lang',%s);localStorage.setItem('theme',%s);}catch(e){}"
                    % (json.dumps(lang), json.dumps(theme)))
                page.goto(f"http://127.0.0.1:{port}/china_stocks.html", wait_until="load")
                page.evaluate(
                    "([l,t])=>{document.documentElement.setAttribute('data-lang',l);"
                    "document.documentElement.setAttribute('data-theme',t);}", [lang, theme])
                page.wait_for_timeout(1400)

                host = page.query_selector("#cn-live-board")
                painted = bool(host) and not host.get_attribute("hidden") is not None
                strip_txt = (host.inner_text() if host else "") or ""
                chips = page.eval_on_selector_all(
                    ".pvcard[data-ticker] .pv-ov.pv-ovl > .pv-live:not([hidden])",
                    "els=>els.map(e=>e.closest('.pvcard').getAttribute('data-ticker')+'='+e.innerText.replace(/\\s+/g,' ').trim())")

                # Scroll the board panel into frame and crop it, not the whole page: the
                # proof is about the strip and the cards under it.
                page.eval_on_selector("#standouts", "e=>e.scrollIntoView({block:'start'})")
                page.wait_for_timeout(250)
                box = page.query_selector("#standouts").bounding_box()
                clip = {"x": max(box["x"] - 4, 0), "y": max(box["y"] - 4, 0),
                        "width": min(box["width"] + 8, vw),
                        "height": min(box["height"] + 8, 2600 if vw < 700 else 900)}
                out = HERE / f"{name}.png"
                page.screenshot(path=str(out), clip=clip)
                results.append((name, fixture, painted, strip_txt.replace("\n", " | "), chips))
                ctx.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                shutil.rmtree(tmp, ignore_errors=True)
        browser.close()

    print("\n=== CN-W-L3 crop run ===")
    for name, fixture, painted, strip, chips in results:
        print(f"\n[{name}]  fixture={fixture}  strip_painted={painted}")
        print(f"  strip: {strip[:220] or '(none — SSR board untouched)'}")
        print(f"  chips ({len(chips)}): {chips if len(chips) <= 12 else chips[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
