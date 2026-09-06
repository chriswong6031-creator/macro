"""Exercise the existing real live painter with explicitly local feed fixtures."""
import functools
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SITE = ROOT / "site"
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/macro.html"
base = json.loads((SITE / "riskdata/risk_envelope.json").read_text())
report = {"classification": "LOCAL_FEED_FIXTURE_NOT_PRODUCTION", "cases": [],
          "html_sha256": hashlib.sha256((SITE / "macro.html").read_bytes()).hexdigest()}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        cases = [(s, "dark", "en") for s in ("healthy", "degraded", "stale")]
        cases += [("pending", t, l) for t in ("dark", "light") for l in ("en", "zh")]
        for scenario, theme, lang in cases:
            now = datetime.now(timezone.utc)
            feed = dict(base, revision="live_provisional", precedence="live", live_active=True,
                        stale_after_min=5, overlays={"settled_bundle_id": base["bundle_id"]})
            feed["built"] = (now - timedelta(minutes=10) if scenario == "stale" else now).isoformat()
            feed["hazard_summary"] = dict(base["hazard_summary"], stage=None if scenario == "degraded" else "FRAGILE")
            feed["live_transition"] = {"candidate_stage": feed["hazard_summary"]["stage"], "stable_stage": "FRAGILE", "pending": None}
            if scenario == "pending":
                feed["live_transition"]["pending"] = {"stage": "TRANSMITTING", "ticks": 2, "needs": 3}
            context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
            context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
            payload = json.dumps(feed)
            context.route("**/live/risk_envelope.json*", lambda route: route.fulfill(status=200, content_type="application/json", body=payload))
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            with page.expect_response("**/live/risk_envelope.json*") as response:
                page.goto(url, wait_until="load")
            response.value.finished()
            page.evaluate("([theme,lang]) => { document.documentElement.dataset.theme=theme; document.documentElement.dataset.lang=lang; document.documentElement.lang=lang; }", [theme, lang])
            page.evaluate("() => new Promise(requestAnimationFrame)")
            if scenario != "stale":
                page.locator("#gde-live-chip").wait_for(state="visible", timeout=5000)
                assert page.locator(".gde-stamp-settled").is_visible()
                if scenario == "degraded":
                    assert "not enough to say" in page.locator("#gde-live-chip").inner_text()
            else:
                assert not page.locator("#gde-live-chip").is_visible()
            assert page.locator(".gde-stamp-settled").is_visible()
            if scenario == "pending":
                assert page.locator("#gde-pending-chip").is_visible()
                assert "2/3" in page.locator("#gde-pending-chip").inner_text()
            facts = {"scenario": scenario, "theme": theme, "language": lang, "clock_visible": page.locator(".gde-stamp-settled").is_visible(),
                     "rail_height": page.locator("#risk-envelope-band").bounding_box()["height"],
                     "overflow": page.evaluate("document.documentElement.scrollWidth>innerWidth+1")}
            assert not facts["overflow"] and facts["rail_height"] <= 140, facts
            facts["page_errors"] = errors
            assert not errors, facts
            report["cases"].append(facts)
            page.screenshot(path=str(OUT / f"live-{scenario}-390-{theme}-{lang}.png"))
            context.unroute_all(behavior="wait")
            context.close()
        browser.close()
    report["status"] = "PASS"
finally:
    server.shutdown()
    (OUT / "live-context-receipt.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
