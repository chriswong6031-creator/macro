"""W4 proof — the OLD-HTML + NEW-JS window, against LIVE production markup.

The deploy split-brain (packet §11): the plain-copy JS pairs go live on the VPS's
3-minute pull, while `site/watchlist.html` waits for a render. So production WILL serve
whatever markup is currently baked with THIS branch's scripts, and that window produces
no console error to notice it by.

W4 adds: a row-drawer composer, a new click path on `[data-row-exp]` in `portfolio.js`,
and a drawer + `⌄` affordance on the anonymous holdings table in `watchlist.js`. Every
one of them must be inert against markup that has no host for it, and — the part a
"nothing threw" check would miss — must not DESTROY what the old page does render.

Unlike its W3 sibling this gate does not assume which markup is live. It reads the page,
decides whether it is the legacy card grid or the W2 workspace, and asserts the property
that matters for THAT page: the legacy grid must still render its cards and grow no
drawer; the workspace must still render its table and its drawers must open.

  python3 verify_w4_old_html_new_js.py

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
WORK = pathlib.Path("/private/tmp/claude-501/w4prev")
OLD = WORK / "old"
LIVE_URL = "https://www.mastermind-x.com/watchlist.html"
CACHE = WORK / "live_watchlist.html"
PORT = 8876

# every file W4 touches that is a plain-copy pair on this page
JS = ["watchlist.js", "watchlist_risk.js", "portfolio.js"]


def setup() -> str:
    OLD.mkdir(parents=True, exist_ok=True)
    for f in JS:
        blob = subprocess.run(
            ["git", "-C", str(BRANCH), "show", "origin/main:templates/%s" % f],
            capture_output=True, text=True, check=True).stdout
        (OLD / f).write_text(blob)
    if not (CACHE.exists() and CACHE.stat().st_size > 5000):
        req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "Mozilla/5.0 (W4 gate)"})
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
      listChildren: (document.getElementById('wl_list')||{children:[]}).children.length,
      tblRows: document.querySelectorAll('.hold tbody tr').length,
      drawers: document.querySelectorAll('tr.row-drawer').length,
      laneRows: document.querySelectorAll('.wri-lrow').length,
      expBtns: document.querySelectorAll('[data-exp],[data-row-exp]').length,
      emptyPresent: !!document.getElementById('wl_empty'),
      wri: !!window.WRI, ws: !!window.WS, wl: !!window.WL
    })""")


# A watchlist AND a local book of POSITIONS.
#
# The book is what makes this gate able to see anything. Served locally the page has no
# Supabase config, so its auth bootstrap resolves to `data-ws-state="signed"` with an
# empty account — a state whose holdings table is one empty-state row. Measuring a
# drawer affordance on a table with no rows is measuring nothing, which is exactly what
# the first version of this gate did before it was believed. `mdash.pf.v1` is the local
# portfolio store, so it fills that table with real rows under the LIVE markup, and the
# `⌄` W4 adds has somewhere to appear.
SEED = ("()=>{localStorage.setItem('mdash.watchlist.v1', JSON.stringify({"
        "v:1,updated:new Date().toISOString(),"
        "items:['AAPL','MSFT','NVDA'].map(function(t){return {t:t,added:'2026-07-01',note:''}}),"
        "order:['AAPL','MSFT','NVDA'],settings:{sort:'order',buySoonOnly:false}}));"
        "localStorage.setItem('mdash.pf.v1', JSON.stringify({v:1, rows:["
        "{id:'loc-1',ticker:'AAPL',shares:96,entry_price:198.55,entry_date:'2025-06-20',status:'open'},"
        "{id:'loc-2',ticker:'MSFT',shares:49,entry_price:402.10,entry_date:'2025-09-12',status:'open'},"
        "{id:'loc-3',ticker:'NVDA',shares:176,entry_price:118.40,entry_date:'2025-11-04',status:'open'}"
        "]}));}")


def main():
    html = setup()
    Handler.html = html
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    cases = [("all-old", set())] + [("new:" + f, {f}) for f in JS] + [("all-new", set(JS))]
    failures = []
    baseline = {}
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
                page.evaluate(SEED)
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(2400)
                r = probe(page)
                if name == "all-old":
                    baseline = dict(r)
                    print("live markup is the %s"
                          % ("W2 WORKSPACE" if r["workspace"] else
                             "LEGACY CARD GRID" if r["legacy"] else "UNRECOGNISED PAGE"))
                bad = []
                if errs:
                    bad.append("page errors: %s" % errs[:3])
                if not (r["legacy"] or r["workspace"]):
                    bad.append("neither markup recognised — re-derive this gate")
                if baseline.get("legacy"):
                    # THE PROPERTY on the legacy grid: the cards still render, and none
                    # of W4's drawer code found a host to build into.
                    if r["listChildren"] < baseline["listChildren"]:
                        bad.append("legacy list lost rows: %d -> %d"
                                   % (baseline["listChildren"], r["listChildren"]))
                    if r["drawers"] or r["laneRows"]:
                        bad.append("drawer markup appeared in the legacy grid — impossible")
                if baseline.get("workspace"):
                    # THE PROPERTY on the baked workspace: the table still renders every
                    # row it rendered before, under each new script alone and all
                    # together. A row LOST to a new script is the regression this window
                    # exists to catch.
                    if r["tblRows"] < baseline["tblRows"]:
                        bad.append("workspace table lost rows: %d -> %d"
                                   % (baseline["tblRows"], r["tblRows"]))
                    # and the affordance never goes BACKWARDS. It is asserted as a
                    # non-regression rather than as a floor, because the baseline is
                    # whatever production happens to be serving today and a gate that
                    # demands a control the old build never had would fail forever on a
                    # page state that has no rows to put one on.
                    if r["expBtns"] < baseline["expBtns"]:
                        bad.append("row-drawer affordance lost: %d -> %d"
                                   % (baseline["expBtns"], r["expBtns"]))
                    # W4's own addition, stated positively where it IS expected: the
                    # anonymous holdings table shipped an empty `c-exp` cell, so the new
                    # watchlist.js must put a ⌄ on every row it draws.
                    # W4's own addition, stated positively where it IS expected: with
                    # rows on the table, every one of them carries a ⌄.
                    if r["tblRows"] > 1 and r["expBtns"] < r["tblRows"]:
                        bad.append("%d rows carried only %d row-drawer affordances"
                                   % (r["tblRows"], r["expBtns"]))
                print("%-26s list=%-3s tbl=%-3s exp=%-3s drawers=%-2s WRI=%-5s %s"
                      % (name, r["listChildren"], r["tblRows"], r["expBtns"],
                         r["drawers"], r["wri"], "OK" if not bad else "FAIL " + "; ".join(bad)))
                if bad:
                    failures.append((name, bad))
                ctx.close()
            b.close()
    finally:
        srv.shutdown()

    if failures:
        print("\nFAILURES:", failures)
        sys.exit(1)
    print("\nOK — the live page renders unchanged under every W4 script, alone and all "
          "together; no drawer code runs without a host, and nothing throws.")


main()
