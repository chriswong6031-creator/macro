"""B2 proof — the OLD-HTML + NEW-JS window, against LIVE production markup.

site/watchlist.html is baked by the render lane; the plain-copy JS pairs go live on the
VPS's 3-minute pull. The HTML empirically lags by more than an hour, so production WILL
serve the current live markup with this branch's scripts. That window is what resurrects
the #5463 husk, and it produces no console error to notice it by.

Method: fetch the live page, serve it locally, and swap files one at a time between the
`origin/main` copy (what is live now) and this branch's copy. Assert the OLD page still
renders its list, empty state, auth box and sync pill under the NEW JS.

  python3 verify_b2_old_html_new_js.py      # run the matrix

Needs network (it fetches the live page once and caches it) and a browser.
"""
import http.server
import json
import pathlib
import re
import socketserver
import subprocess
import sys
import threading
import urllib.request

BRANCH = pathlib.Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/wp-w2-flagship-shell"
)
WORK = pathlib.Path("/private/tmp/claude-501/wsprev/b2")
OLD = WORK / "old"
LIVE_URL = "https://www.mastermind-x.com/watchlist.html"
CACHE = WORK / "live_watchlist.html"
PORT = 8871
JS = ["watchlist.js", "watchstore.js", "market_books.js", "portfolio.js", "mtf.js"]


def setup():
    (OLD).mkdir(parents=True, exist_ok=True)
    for f in JS:
        blob = subprocess.run(
            ["git", "-C", str(BRANCH), "show", "origin/main:templates/%s" % f],
            capture_output=True, text=True, check=True).stdout
        (OLD / f).write_text(blob)
    if not (CACHE.exists() and CACHE.stat().st_size > 5000):
        req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "Mozilla/5.0 (W2 gate)"})
        CACHE.write_text(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
    return CACHE.read_text()


class Handler(http.server.SimpleHTTPRequestHandler):
    swap: set = set()          # files served from the BRANCH; the rest come from OLD
    html: str = ""

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def do_GET(self):
        path = self.path.split("?")[0].lstrip("/")
        if path in ("", "watchlist.html"):
            return self._send(self.html.encode(), "text/html; charset=utf-8")
        if path in JS:
            src = (BRANCH / "site" / path) if path in self.swap else (OLD / path)
            return self._send(src.read_bytes(), "application/javascript")
        f = BRANCH / "site" / path
        if not f.exists():
            self.send_error(404)
            return
        ctype = ("application/javascript" if path.endswith(".js")
                 else "text/css" if path.endswith(".css")
                 else "application/json" if path.endswith(".json")
                 else "application/octet-stream")
        self._send(f.read_bytes(), ctype)

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


PROBE = """()=>({
  cards: document.querySelectorAll('#wl_list .wl-card').length,
  listFilled: !!(document.getElementById('wl_list')||{}).innerHTML,
  emptyShown: (function(){var e=document.getElementById('wl_empty');
    return e ? getComputedStyle(e).display !== 'none' : null;})(),
  authShown: (function(){var e=document.getElementById('wl_auth');
    return e ? getComputedStyle(e).display !== 'none' : null;})(),
  signinShown: (function(){var e=document.getElementById('wl_signin');
    return e ? getComputedStyle(e).display !== 'none' : null;})(),
  pill: ((document.getElementById('wl_syncpill')||{}).textContent||'').trim(),
  controls: (function(){var e=document.getElementById('wl_controls');
    return e ? getComputedStyle(e).display !== 'none' : null;})()
})"""

SEED = """()=>{localStorage.setItem('mdash.watchlist.v1', JSON.stringify({v:1,
  updated:'2026-08-01T00:00:00.000Z',
  items:['NVDA','MSFT','AAPL','GLD'].map(function(t){return {t:t,added:'2026-07-01T00:00:00Z',note:''}}),
  order:['NVDA','MSFT','AAPL','GLD'], settings:{sort:'order',buySoonOnly:false}}));}"""


def run_case(b, label, swap, url, seeded=True):
    """One case. `networkidle` + a settle window, because the first pass on a cold
    asset cache under-reports: the very first run measured 0 cards purely because the
    index fetch had not resolved yet, which would have read as a regression in the
    control. A measurement that depends on cache temperature is not evidence."""
    Handler.swap = set(swap)
    page = b.new_context().new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)[:110]))
    page.goto(url, wait_until="domcontentloaded")
    if seeded:
        page.evaluate(SEED)
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(3000)
    got = page.evaluate(PROBE)
    got["pageerrors"] = errs
    page.close()
    return label, got


def main():
    html = setup()
    print("live html: %d bytes | #ws_modes present: %s | #wl_list: %s | #wl_auth: %s"
          % (len(html), "ws_modes" in html, 'id="wl_list"' in html, 'id="wl_auth"' in html))
    print("live scripts:", ", ".join(sorted(set(re.findall(r'src="([a-z_]+\.js)', html)))))
    print("#wl_auth inline style:",
          (re.search(r'id="wl_auth"[^>]*', html) or [""])[0][:90])

    Handler.html = html
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/watchlist.html" % PORT

    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        run_case(b, "warm-up (discarded)", [], url)      # prime the asset cache
        results.append(run_case(b, "ALL-OLD (control)", [], url))
        for f in JS:
            results.append(run_case(b, "NEW " + f, [f], url))
        results.append(run_case(b, "ALL-NEW", JS, url))
        # the EMPTY state is the husk's actual signature: #5463 shipped a page with no
        # rows AND no empty state, so an unseeded pass is the case that matters most
        results.append(run_case(b, "empty ALL-OLD", [], url, seeded=False))
        results.append(run_case(b, "empty ALL-NEW", JS, url, seeded=False))
        b.close()
    srv.shutdown()

    ctrl = dict(results[0][1])
    empty_ctrl = dict(results[-2][1])
    print("\n%-22s %6s %6s %6s %7s %-14s %s" %
          ("case", "cards", "empty", "auth", "signin", "pill", "errors"))
    bad = []
    for label, r in results:
        print("%-22s %6s %6s %6s %7s %-14s %s" %
              (label, r["cards"], r["emptyShown"], r["authShown"], r["signinShown"],
               (r["pill"] or "-")[:14], r["pageerrors"] or ""))
        if label.startswith("ALL-OLD") or label == "empty ALL-OLD":
            continue
        if label.startswith("empty "):
            for k in ("cards", "emptyShown", "authShown", "signinShown"):
                if r[k] != empty_ctrl[k]:
                    bad.append("%s: %s %r != empty control %r" % (label, k, r[k], empty_ctrl[k]))
            if r["pageerrors"]:
                bad.append("%s: page errors %s" % (label, r["pageerrors"]))
            continue
        for k in ("cards", "authShown", "signinShown", "controls"):
            if r[k] != ctrl[k]:
                bad.append("%s: %s %r != control %r" % (label, k, r[k], ctrl[k]))
        if not r["pill"] and ctrl["pill"]:
            bad.append("%s: sync pill went blank" % label)
        if r["pageerrors"]:
            bad.append("%s: page errors %s" % (label, r["pageerrors"]))

    print("\ncontrol rendered %d cards, auth=%s, pill=%r"
          % (ctrl["cards"], ctrl["authShown"], ctrl["pill"]))
    if bad:
        print("\nB2 REGRESSIONS:")
        for x in bad:
            print("  -", x)
        return 1
    print("\nB2 PASS — every swap matches the all-old control on the LIVE markup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
