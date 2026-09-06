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
report = {"classification": "LOCAL_CANONICAL_PAGE_ANONYMOUS_NATIVE_DISCLOSURE_NOT_PRODUCTION",
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
                    if theme == "light":
                        contrast = page.evaluate("""() => {
                            const node=document.querySelector('.gde-seg-break .gde-v');
                            const rail=document.getElementById('risk-envelope-band');
                            const fg=getComputedStyle(node).color, bg=getComputedStyle(rail).backgroundColor;
                            const cv=document.createElement('canvas'); cv.width=cv.height=1;
                            const ctx=cv.getContext('2d');
                            function parse(s){ctx.clearRect(0,0,1,1);ctx.fillStyle=s;ctx.fillRect(0,0,1,1);return Array.from(ctx.getImageData(0,0,1,1).data);}
                            function lum(c){const rgb=c.slice(0,3).map(x=>{x/=255;return x<=0.04045 ? x/12.92 : ((x+0.055)/1.055)**2.4;});return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722;}
                            const f=parse(fg), b=parse(bg), lf=lum(f), lb=lum(b);
                            return {foreground:fg, background:bg, opaque:b[3]===255 && f[3]===255, ratio:(Math.max(lf,lb)+0.05)/(Math.min(lf,lb)+0.05)};
                        }""")
                        facts["light_hazard_contrast"] = contrast
                        assert contrast["opaque"] and contrast["ratio"] >= 4.5, contrast

                    report["cases"].append(facts)
                    assert facts["inside_hero"] and not facts["full_band"], facts
                    assert not facts["overflow"] and facts["rail_height"] <= cap, facts
                    for hook in HOOKS:
                        assert page.locator(f"#{hook}").count() == 1, hook
                    if width == 1440:
                        assert facts["tape_top"] is not None and facts["tape_top"] < 820, facts
                    page.screenshot(path=str(OUT / f"home-{width}-{theme}-{lang}.png"), full_page=False)
                    # Fresh browser context, with the actual anonymous preview logic intact.
                    facts["anonymous"] = page.evaluate("!window.MMXAccessPreview || window.MMXAccessPreview.isAnon()")
                    assert facts["anonymous"], facts
                    disclosure = page.locator("#gde-context-disclosure")
                    rail = page.locator("#risk-envelope-band")
                    assert disclosure.get_attribute("open") is None
                    rail.focus()
                    page.keyboard.press("Enter")
                    assert disclosure.get_attribute("open") is not None
                    assert page.locator("#gde-detail").is_visible()
                    assert not page.locator("#dlg-risk").is_visible()
                    facts["public_keyboard_open"] = True
                    facts["detail_overflow"] = page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
                    assert not facts["detail_overflow"]
                    if width in (1440, 390):
                        disclosure.screenshot(path=str(OUT / f"detail-{width}-{theme}-{lang}.png"))
                    page.locator("#gde-detail .gde-disc > summary").click()
                    assert page.locator("#gde-detail .gde-tbl").is_visible()
                    facts["public_evidence_accessible"] = True
                    assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
                    rail.focus()
                    page.keyboard.press("Enter")
                    assert disclosure.get_attribute("open") is None
                    facts["focus_after_close"] = page.evaluate("document.activeElement.id")
                    assert facts["focus_after_close"] == "risk-envelope-band"
                    if width == 1440 and lang == "en":
                        rail.screenshot(path=str(OUT / f"focus-{theme}.png"))
                        rail.hover()
                        rail.screenshot(path=str(OUT / f"hover-{theme}.png"))
                    # The separately registered member-only Risk Detail remains gated.
                    page.evaluate("window.mx5OpenDlg('dlg-risk')")
                    assert not page.locator("#dlg-risk").is_visible()
                    facts["member_risk_detail_still_gated"] = True
                    facts["page_errors"] = errors
                    print(json.dumps(facts), flush=True)
                    context.close()
        browser.close()
    report["status"] = "PASS"
finally:
    server.shutdown()
    (OUT / "browser-receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
