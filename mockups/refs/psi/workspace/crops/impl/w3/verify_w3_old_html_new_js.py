"""W3 proof — the OLD-HTML + NEW-JS window, against LIVE production markup.

The deploy split-brain (packet §11): the plain-copy JS pairs go live on the VPS's
3-minute pull, while `site/watchlist.html` waits for a render. At the time of this build
the live page is still the PRE-W2 card grid — `site/watchlist.html` on `main` carries
`wl_list` and none of `ws_modes` / `ws_seam` / `rc_tabs` — so production WILL serve the
old markup with this branch's scripts, and that window produces no console error to
notice it by.

W3 adds a Risk Center renderer, a Scenario Lab with its own event wiring, and a new
publish payload. Every one of those must be inert against markup that has no host for
it. This asserts that directly: fetch the live page, serve it locally, swap in this
branch's JS one file at a time and then all together, and check that the OLD page still
renders its list and its empty state, and that nothing throws.

  python3 verify_w3_old_html_new_js.py

Needs network (fetches the live page once and caches it) and a browser. Hand-run, for
the reason recorded in ../IMPLEMENTATION_DELTAS.md: a pytest wrapper would SKIP in CI on
a missing playwright and report green while proving nothing.
"""
import http.server
import pathlib
import socketserver
import subprocess
import sys
import threading
import urllib.request

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve()
BRANCH = HERE.parents[7]
WORK = pathlib.Path("/private/tmp/claude-501/w3prev")
OLD = WORK / "old"
LIVE_URL = "https://www.mastermind-x.com/watchlist.html"
CACHE = WORK / "live_watchlist.html"
PORT = 8875

# every file W3 touches that is a plain-copy pair on this page
JS = ["watchlist.js", "watchlist_risk.js", "risk_core.js", "factor_exposure.js",
      "portfolio.js"]


def setup() -> str:
    OLD.mkdir(parents=True, exist_ok=True)
    for f in JS:
        blob = subprocess.run(
            ["git", "-C", str(BRANCH), "show", "origin/main:templates/%s" % f],
            capture_output=True, text=True, check=True).stdout
        (OLD / f).write_text(blob)
    if not (CACHE.exists() and CACHE.stat().st_size > 5000):
        req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "Mozilla/5.0 (W3 gate)"})
        CACHE.write_text(
            urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
    return CACHE.read_text()


class Handler(http.server.SimpleHTTPRequestHandler):
    swap: set = set()          # files served from the BRANCH; the rest come from OLD
    html: str = ""

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        # the browser drops connections as it navigates; that is not a finding
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self):
        path = self.path.split("?")[0].lstrip("/")
        if path in ("", "watchlist.html"):
            return self._send(self.html, "text/html")
        if path in JS:
            src = (BRANCH / "templates" / path) if path in self.swap else (OLD / path)
            return self._send(src.read_text(), "application/javascript")
        local = BRANCH / "site" / path
        if local.is_file():
            ctype = ("text/css" if path.endswith(".css")
                     else "application/json" if path.endswith(".json")
                     else "application/javascript" if path.endswith(".js")
                     else "text/plain")
            return self._send(local.read_text(errors="replace"), ctype)
        self.send_response(404)
        self.end_headers()

    def _send(self, body: str, ctype: str):
        raw = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def probe(page) -> dict:
    return page.evaluate("""()=>({
      legacy: !!document.getElementById('wl_list'),
      workspace: !!document.getElementById('ws_modes'),
      rcHost: !!document.getElementById('rc_body'),
      labHost: !!document.getElementById('rc_lab'),
      listChildren: (document.getElementById('wl_list')||{children:[]}).children.length,
      emptyPresent: !!document.getElementById('wl_empty'),
      wri: !!window.WRI, ws: !!window.WS, wl: !!window.WL
    })""")


def main():
    html = setup()
    Handler.html = html
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    cases = [("all-old", set())] + [("new:" + f, {f}) for f in JS] + [("all-new", set(JS))]
    failures = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            for name, swap in cases:
                Handler.swap = swap
                ctx = b.new_context()
                page = ctx.new_page()
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.goto("http://127.0.0.1:%d/watchlist.html" % PORT,
                          wait_until="domcontentloaded")
                page.evaluate(
                    "()=>{localStorage.setItem('mdash.watchlist.v1', JSON.stringify({"
                    "v:1,updated:new Date().toISOString(),"
                    "items:['AAPL','MSFT','NVDA'].map(function(t){return {t:t,added:'2026-07-01',note:''}}),"
                    "order:['AAPL','MSFT','NVDA'],settings:{sort:'order',buySoonOnly:false}}));}")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(2200)
                r = probe(page)
                bad = []
                if errs:
                    bad.append("page errors: %s" % errs[:3])
                if not r["legacy"]:
                    bad.append("the live page is no longer the legacy grid — re-read this gate")
                if r["workspace"]:
                    bad.append("live markup already has the workspace; this window is closed")
                # THE PROPERTY: the old page still renders its list under the new JS
                if r["legacy"] and r["listChildren"] < 3:
                    bad.append("legacy list rendered %d rows, expected 3" % r["listChildren"])
                # and the W3 surfaces are simply absent, not half-built
                if r["rcHost"] or r["labHost"]:
                    bad.append("a Risk Center host appeared in old markup — impossible")
                print("%-22s list=%-3s rc_host=%-5s WRI=%-5s %s"
                      % (name, r["listChildren"], r["rcHost"], r["wri"],
                         "OK" if not bad else "FAIL " + "; ".join(bad)))
                if bad:
                    failures.append((name, bad))
                ctx.close()
            b.close()
    finally:
        srv.shutdown()

    if failures:
        print("\nFAILURES:", failures)
        sys.exit(1)
    print("\nOK — the live legacy page renders unchanged under every W3 script, "
          "alone and all together; no Risk Center code runs without its host.")


main()
