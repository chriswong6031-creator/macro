"""Read-only public production observation; no member fixture or auth changes."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parent
phase = sys.argv[1] if len(sys.argv) > 1 else "before"
assert phase in ("before", "after")
now = datetime.now(timezone.utc)
url = "https://www.mastermind-x.com/macro.html?sol_observe=" + now.strftime("%Y%m%dT%H%M%SZ")
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto(url, wait_until="load", timeout=60000)
    assert response is not None
    body = response.body()
    receipt = {"phase": phase, "observed_at": now.isoformat(), "url": page.url,
               "classification": "PUBLIC_LIVE_BROWSER_NOT_MEMBER_SESSION",
               "status": response.status, "html_sha256": hashlib.sha256(body).hexdigest()}
    receipt.update(page.evaluate("""() => {
        const band=document.getElementById('risk-envelope-band');
        const tape=document.getElementById('sx-markets-v2');
        return {title:document.title, band_exists:!!band,
            band_inside_hero:!!(band && band.closest('#regime-radar')),
            band_text:band ? band.innerText : null,
            band_height:band ? band.getBoundingClientRect().height : null,
            bundle:band ? band.dataset.bundleId : null,
            settled_session:band ? band.dataset.settledSession : null,
            tape_top:tape ? tape.getBoundingClientRect().top+scrollY : null,
            overflow:document.documentElement.scrollWidth>innerWidth+1};
    }"""))
    receipt["page_errors"] = errors
    page.screenshot(path=str(out / f"production-{phase}-1440.png"))
    (out / f"production-{phase}.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
    context.close()
    browser.close()
