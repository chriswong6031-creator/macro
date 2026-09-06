"""Real Chromium UI proof over this worktree's canonical page; not deployment."""
from __future__ import annotations
import functools
import hashlib
import json
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
SITE = ROOT / "site"
OUT = Path(__file__).resolve().parent
HOOKS = ("risk-envelope-band", "gde-live-chip", "gde-pending-chip", "gde-live-receipt")

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(SITE)))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = f"http://127.0.0.1:{server.server_port}/macro.html"
report = {"classification": "LOCAL_CANONICAL_PAGE_AND_MEMBER_UI_FIXTURE_NOT_PRODUCTION",
          "html_sha256": hashlib.sha256((SITE / "macro.html").read_bytes()).hexdigest(),
          "observed_at": datetime.now(timezone.utc).isoformat(), "cases": []}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        report["browser"] = browser.version
        for width, height, cap in [(1440, 900, 80), (768, 1024, 96), (390, 844, 118)]:
            for theme in ("dark", "light"):
                for lang in ("en", "zh"):
                    context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
                    context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url, wait_until="load", timeout=60000)
                    page.evaluate("([theme,lang]) => { document.documentElement.dataset.theme=theme; document.documentElement.dataset.lang=lang; document.documentElement.lang=lang; }", [theme, lang])
                    page.locator("#risk-envelope-band").wait_for(state="visible")
                    facts = page.evaluate("""() => {
                        const rail=document.getElementById('risk-envelope-band');
                        const tape=document.getElementById('sx-markets-v2');
                        return {rail_height:rail.getBoundingClientRect().height,
                            tape_top:tape ? tape.getBoundingClientRect().top+scrollY : null,
                            overflow:document.documentElement.scrollWidth>innerWidth+1,
                            rail_text:rail.innerText,
                            inside_hero:!!rail.closest('#regime-radar'),
                            full_band:rail.classList.contains('gde-band')};
                    }""")
                    facts.update(width=width, height=height, theme=theme, language=lang)
                    report["cases"].append(facts)
                    assert facts["inside_hero"] and not facts["full_band"], facts
                    assert not facts["overflow"] and facts["rail_height"] <= cap, facts
                    for hook in HOOKS:
                        assert page.locator(f"#{hook}").count() == 1, hook
                    if width == 1440:
                        assert facts["tape_top"] is not None and facts["tape_top"] < 820, facts
                    page.screenshot(path=str(OUT / f"home-{width}-{theme}-{lang}.png"), full_page=False)
                    # Explicit LOCAL member UI fixture, not an authentication or production claim.
                    page.evaluate("() => { window.MMXAccessPreview = Object.assign({}, window.MMXAccessPreview, {isAnon: () => false}); }")
                    page.locator("#risk-envelope-band").click()
                    page.locator("#dlg-risk").wait_for(state="visible", timeout=5000)
                    facts["dialog_open"] = True
                    disclosure = page.locator("#gde-context-disclosure")
                    assert disclosure.count() == 1
                    assert disclosure.get_attribute("open") is None
                    disclosure.locator(":scope > summary").click()
                    assert page.locator("#gde-detail").is_visible()
                    facts["detail_disclosure"] = True
                    if width in (1440, 390) and lang == "en":
                        page.screenshot(path=str(OUT / f"detail-{width}-{theme}-{lang}.png"), full_page=False)
                    page.keyboard.press("Escape")
                    assert not page.locator("#dlg-risk").is_visible()
                    facts["escape_closes"] = True
                    facts["focus_after_escape"] = page.evaluate("document.activeElement.id")
                    facts["page_errors"] = errors
                    print(json.dumps(facts), flush=True)
                    context.close()
        browser.close()
    report["status"] = "PASS"
finally:
    server.shutdown()
    (OUT / "browser-receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
