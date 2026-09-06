"""Explicit fixture states through the real dashboard template; no site writes."""
import copy
import functools
import hashlib
import json
import pickle
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from engine import i18n
from lib.seo import SITE_BASE
from scripts.build_site import us_stance_projection
OUT = Path(__file__).resolve().parent
SITE = ROOT / "site"
cache = ROOT / "data/_dev_macro_vm.pkl"  # Created by this session's actual builder.
with cache.open("rb") as source:
    vm = pickle.load(source)["vm"]
env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
env.filters["min"] = min
env.globals.update(td=i18n.td, tr=i18n.tr, t_pctile=i18n.t_pctile, zip=zip, SITE_BASE=SITE_BASE, us_stance_projection=us_stance_projection)

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}/macro.html"
report = {"classification": "EXPLICIT_SETTLED_FIXTURES_NOT_PRODUCTION", "cases": [],
          "template_sha256": hashlib.sha256((ROOT / "templates/_risk_envelope_band.html.j2").read_bytes()).hexdigest()}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for scenario in ("absent", "partial", "stale", "active_policy"):
            payload = copy.deepcopy(vm["risk_envelope"])
            if scenario == "absent": payload = None
            if scenario == "partial":
                payload["data_state"] = "DEGRADED"
                payload["hazard_summary"].update(stage="FRAGILE", unreadable_sources=["missing_required"], unmapped_required_sources=[])
            if scenario == "stale":
                payload["data_state"] = "STALE"
                for source in payload["provenance"]["sources"]:
                    if source["role"] == "measured_state": source["coverage"] = "STALE"
            if scenario == "active_policy": payload["policy_summary"]["policy_count"] = 3
            fixture_vm = dict(vm, risk_envelope=payload)
            html = env.get_template("dashboard.html.j2").render(**fixture_vm, mode="macro")
            for theme, lang in (("dark", "en"), ("light", "en"), ("dark", "zh"), ("light", "zh")):
                context = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
                context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/macro.html", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
                page.goto(url, wait_until="load")
                page.evaluate("([theme,lang]) => { document.documentElement.dataset.theme=theme; document.documentElement.dataset.lang=lang; document.documentElement.lang=lang; }", [theme, lang])
                facts = {"scenario": scenario, "theme": theme, "language": lang}
                disclosure = page.locator("#gde-context-disclosure")
                if scenario == "absent":
                    assert disclosure.count() == 0 and page.locator("#risk-envelope-band").count() == 0
                else:
                    rail = page.locator("#risk-envelope-band")
                    facts["rail_height"] = rail.bounding_box()["height"]
                    facts["rail_text"] = rail.inner_text()
                    if scenario == "partial": assert ("1 source unavailable" if lang == "en" else "1 个来源不可用") in facts["rail_text"]
                    if scenario == "stale": assert ("Trend source older" if lang == "en" else "趋势来源较旧") in facts["rail_text"]
                    if scenario == "active_policy": assert "3" in facts["rail_text"]
                    rail.screenshot(path=str(OUT / f"settled-{scenario}-{theme}-{lang}.png"))
                    rail.click()
                    assert page.locator("#gde-detail").is_visible()
                    assert not page.locator("#dlg-risk").is_visible()
                facts["overflow"] = page.evaluate("document.documentElement.scrollWidth>innerWidth+1")
                assert not facts["overflow"], facts
                facts["page_errors"] = errors
                assert not errors, facts
                report["cases"].append(facts)
                context.close()
        browser.close()
    report["status"] = "PASS"
finally:
    server.shutdown()
    (OUT / "settled-state-receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
