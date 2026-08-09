"""W-L1 board-state acceptance harness — the PRODUCTION page, not the mockup.

    python3 mockups/refs/breathing-platform/verify_wl1.py [--out DIR]

The pinned spec's §0 gates are mostly things a screenshot cannot prove, so this harness
shoots the crops AND reads back the proofs, on the real ``templates/dashboard.html.j2``
render against the real ``site/factordata/us_standouts.json`` board. It is the sibling of
``mockups/refs/prophet_live/verify_p1.py`` and follows the same shape for the same reasons:

  1. The template renders through the house harness env
     (``tests/test_dashboard_template_render.py``'s ``_env()`` / ``_base_vm()``) with the
     REAL board, so the crops are production-shaped — real cards, real sparklines, real
     theme.css/theme.js — rather than a fixture in isolation.
  2. ``site/`` is served over loopback so the page's own ``fetch('live/prophet_live.json')``
     resolves. A ``file://`` load cannot fetch and ``page.route()`` does not intercept it —
     the whole point is to drive the REAL client path with the payload arriving the way
     production delivers it.
  3. The clock is frozen at document-start, because the payload's ``valid_until`` is
     compared against it and because the strip above the board is an ET-windowed component.
  4. Crops are ``element.screenshot`` of ``#us-standouts`` — which also dodges the
     backdrop-filter scroll blackout a full-page shot hits on this page.

The proofs, and why each one is not optional:

  · IDENTITY (§0-2) — the gate. A payload describing a DIFFERENT board is served to the
    real client and the ``ahead`` stamp must be absent. This is the one failure that would
    actively lie to the reader, so it is proved in the browser as well as under node
    (tests/test_wl1_board_state_surface.py runs the pure decision's truth table).
  · CONTRAST (§0-3) — every new ink/fill pair measured after compositing, in BOTH themes,
    against WCAG AA for small text. The routine is imported from ``shoot_wl1.py`` rather
    than re-typed: its ``_rgb`` ``color(srgb …)`` branch is the difference between
    measuring the design and measuring the parser (Chromium serialises every
    ``color-mix()`` result as 0..1 floats, and read naively EVERY pair measures ~1.00:1).
  · HEADER HEIGHT (§0-4) — ``.nbgrid``'s offset from the panel top, swept across all four
    states × {desktop, 680} × {en, zh}. The provisional→confirmed flip happens under a
    reader who is looking at the board; it must not shove the grid.
  · STAMP EXCLUSIVITY (§0-5) — never two, and none at all on the confirmed board. Absence
    is a state, so absence is asserted rather than assumed.
  · PERFORATED EDGE — read off ``getComputedStyle(panel, '::before')``, not off the markup.
  · NO MOTION (§8-6) — the design is deliberately static, so there is no reduced-motion
    kill block to keep in sync; this pins that it stays that way.
  · GLANCE VOCABULARY (§0-7/§0-8) — the visible text of the stamp and the note carries no
    program name, internal state name or falsifier word, in either language.

Exit code is non-zero when any proof fails, so this doubles as a pre-push gate.
"""
from __future__ import annotations

import argparse
import copy
import http.server
import json
import socketserver
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SITE = ROOT / "site"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from shoot_wl1 import _over, _rgb, ratio  # noqa: E402 — the contrast routine, reused not retyped

#: The four states, in spec §3 order, and the crop slug each one is compared against.
STATES = ("provisional", "confirmed", "stale", "closed")

#: 2026-08-09T21:40Z = 17:40 ET on a Thursday — inside the evening publish window, which is
#: when a reader first meets the provisional board. Frozen so `valid_until` and the strip's
#: ET windows are reproducible.
NOW = datetime(2026, 8, 9, 21, 40, tzinfo=timezone.utc)

#: Widths the height sweep is MEASURED at. 1280 is the desktop case and 680 is the
#: component's own breakpoint — the two the spec's §0-4 gate names — plus 390, the phone
#: width, which is measured and printed but NOT gated. See GATED_WIDTHS.
WIDTHS = (1280, 680, 390)

#: Where a spread above 4px FAILS the run. Deliberately the two widths §0-4 names, and not
#: 390: at a phone width the four notes are genuinely different lengths (`note.closed` is
#: three times `note.ahead`), so holding them to one height means reserving the longest
#: note's box on every page view, permanently, to prevent a shove that can happen at most
#: twice a day. That is a layout trade-off the spec scoped on purpose, so this harness
#: reports the phone number rather than quietly re-deciding it.
GATED_WIDTHS = (1280, 680)

#: Crop height — the header plus the first row of cards, matching the reference shots. The
#: whole panel is ~3,000px tall, which makes the one thing under review a detail in the
#: corner of the evidence.
CROP_H = 780

BANNED = ("W-L1", "close-pass", "close pass", "provisional", "armed", "reconciler",
          "admission", "gauntlet", "prereg", "display-tier", "expected-null",
          "falsifier", "falsified", "refuted", "invalidated", "证伪")

PAGE = "_wl1_verify_%s.html"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── The pages ────────────────────────────────────────────────────────────────────

def render_pages() -> "tuple[dict, list]":
    """One rendered page per SSR variant, held IN MEMORY and served from the site root.

    Never written into ``site/``: a temp page there is picked up by the repo guards that
    scan ``site/**`` — ``check_validated_claims`` reported 21 unearned claims off the P1
    harness's own scratch file, because the page is a copy of the real board and inherits
    every phrase on it.

    Two variants, because the four states do not share one SSR:
      · ``plain``    — the board with no board-state payload at all. This is what the
                       nightly render emits on an ordinary night, and it is the page the
                       ahead / behind / closed states hydrate INTO.
      · ``receipt``  — the same board carrying the confirmation receipt and one adjusted
                       name. The receipt is server-side by ruling: it is the record's own
                       build stamping its own receipt.
    """
    from lib.board_state import board_state_view
    from tests.test_dashboard_template_render import _base_vm, _env

    board = json.loads((SITE / "factordata" / "us_standouts.json").read_text())
    tickers = [r["ticker"] for r in board["buy"]]

    # The `behind` stamp's date must be the date the CARDS carry. A crop whose stamp reads
    # "last confirmed Aug 7" over cards dated Aug 5 teaches the reader — and the next
    # builder — a contradiction the spec calls out by name (§3 state 3), so the label is
    # derived from the board's own as-of rather than invented.
    asof = datetime.strptime(board["as_of"][:10], "%Y-%m-%d")
    _Pages.label = {"en": asof.strftime("%b ") + str(asof.day),
                    "zh": asof.strftime("%m-%d")}

    plain_vm = _base_vm()
    plain_vm["us_standouts"] = board

    receipt_board = copy.deepcopy(board)
    n_total = len(receipt_board["buy"])
    # one adjusted, one dropped, the rest confirmed — the arithmetic has to reconcile or
    # the surface emits no receipt at all, which is the point of the invariant
    receipt_board["buy"][2]["adjusted"] = True
    dropped = ["TSLA"]
    receipt_board["board_state_view"] = board_state_view({
        "note": "confirmed", "n_total": n_total, "n_confirmed": n_total - 2,
        "n_adjusted": 1, "n_dropped": 1, "dropped": dropped,
    })
    assert receipt_board["board_state_view"], "the receipt fixture must reconcile"
    receipt_vm = _base_vm()
    receipt_vm["us_standouts"] = receipt_board

    env = _env().get_template("dashboard.html.j2")
    return ({
        "plain": env.render(**plain_vm, mode="stocks").encode(),
        "receipt": env.render(**receipt_vm, mode="stocks").encode(),
    }, tickers)


def payload(tickers: list, *, rel: str, note: str, label: "dict | None" = None,
            valid_h: int = 6, born_h: int = 1) -> bytes:
    """A ``prophet_live.states/v1`` artifact carrying the optional ``board_state`` key.

    The board-state object rides on the artifact this component already fetches — one
    artifact, one poll, one client, no second hydration path.
    """
    doc = {
        "schema": "prophet_live.states/v1",
        "status": "dark",
        "reason": "post_close",
        "states": {},
        "meta": {"pass_ts": _iso(NOW), "session_et": "2026-08-09",
                 "session_phase": "post", "delay_min": 15},
        "board_state": {
            "rel": rel,
            "note": note,
            "generated_at": _iso(NOW - timedelta(hours=born_h)),
            "valid_until": _iso(NOW + timedelta(hours=valid_h)),
            "board": {"as_of": "2026-08-09", "tickers": tickers},
        },
    }
    if label:
        doc["board_state"]["confirmed_label"] = label
    return json.dumps(doc).encode()


class _Payload:
    body: "bytes | None" = None


class _Pages:
    bodies: dict = {}
    label: dict = {"en": "Aug 7", "zh": "08-07"}


def serve() -> "tuple[socketserver.TCPServer, int]":
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(SITE), **kw)

        def _send(self, body: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0].lstrip("/")
            for key, body in _Pages.bodies.items():
                if path == PAGE % key:
                    self._send(body, "text/html; charset=utf-8")
                    return
            if path == "live/prophet_live.json":
                if _Payload.body is None:
                    self.send_error(404)
                    return
                self._send(_Payload.body, "application/json")
                return
            if path == "api/me":
                # tier_preview.js blurs every card past the first for an ANONYMOUS visitor,
                # and past the third on the free tier — which frosts the very cards these
                # crops exist to photograph. It grants no data the page had not rendered.
                self._send(b'{"tier":"pro"}', "application/json")
                return
            super().do_GET()

        def log_message(self, *a):
            return

    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


TIER_SHIM = """
(function(){
  window.MDXAuth = { client: function(){ return Promise.resolve({ auth: { getSession:
    function(){ return Promise.resolve({data:{session:{access_token:'harness'}}}); } } }); } };
  try{ document.cookie='sb-harness-auth-token=1;path=/';
       sessionStorage.setItem('mm.me', JSON.stringify({me:{tier:'pro'},t:Date.now()})); }catch(e){}
})();
"""

CLOCK_SHIM = """
(function(){
  var FIXED = Date.parse(%r);
  var _D = Date;
  function D(){
    if(arguments.length===0) return new _D(FIXED);
    return new (Function.prototype.bind.apply(_D,[null].concat([].slice.call(arguments))));
  }
  D.prototype = _D.prototype;
  D.now = function(){ return FIXED; };
  D.parse = _D.parse; D.UTC = _D.UTC;
  Object.setPrototypeOf(D, _D);
  window.Date = D;
})();
"""

#: Read back off getComputedStyle, never off the markup.
EDGE_JS = """
() => { const p = document.getElementById('us-standouts');
        const s = getComputedStyle(p, '::before');
        return (s.content !== 'none' && s.height !== 'auto' && parseFloat(s.height) > 0)
               ? s.backgroundImage : ''; }
"""

STAMPS_JS = """
() => [...document.querySelectorAll('#us-standouts .pbs')]
        .filter(e => !e.hidden && getComputedStyle(e).display !== 'none')
        .map(e => e.className + '|' + e.innerText.replace(/\\s+/g,' ').trim())
"""

NOTE_JS = """
() => { const v = document.querySelectorAll('#us-standouts .pbs-nv:not([hidden])');
        return [...v].map(e => e.getAttribute('data-bs-note') + '|'
                               + e.innerText.replace(/\\s+/g,' ').trim()); }
"""

OFFSET_JS = """
() => { const p = document.getElementById('us-standouts');
        const g = p.querySelector('.nbgrid');
        return g.getBoundingClientRect().top - p.getBoundingClientRect().top; }
"""

MOTION_JS = """
() => ['.pbs:not([hidden])', '.pbs-note', '.pv-mk-adj']
        .map(s => { const e = document.querySelector('#us-standouts ' + s);
                    if (!e) return s + '|absent';
                    const c = getComputedStyle(e);
                    return s + '|' + c.animationName + '|' + c.transitionProperty; })
"""

CONTRAST_JS = """
s => { const e = document.querySelector('#us-standouts ' + s); if (!e) return null;
       const stack = []; let n = e;
       while (n) { const c = getComputedStyle(n).backgroundColor;
         const a = /rgba?\\([^)]*?,\\s*([\\d.]+)\\s*\\)$/.exec(c);
         const a2 = /\\/\\s*([\\d.]+)\\s*\\)$/.exec(c);
         const al = a ? parseFloat(a[1]) : (a2 ? parseFloat(a2[1]) : 1);
         if (al > 0) stack.push(c);
         if (al >= 1) break;
         n = n.parentElement; }
       return [getComputedStyle(e).color, stack]; }
"""


def _browser(p):
    shell = Path.home() / ("Library/Caches/ms-playwright/chromium_headless_shell-1228/"
                           "chrome-headless-shell-mac-arm64/chrome-headless-shell")
    if shell.exists():
        return p.chromium.launch(executable_path=str(shell))
    return p.chromium.launch()


def _measure_contrast(pg, page_bg, label: str, sel: str, notes: list, fails: list,
                      lang: str, theme: str):
    got = pg.evaluate(CONTRAST_JS, sel)
    if not got:
        fails.append(f"MISSING {sel} in {lang}/{theme}")
        return
    fg = _rgb(got[0])
    layers = [_rgb(c) for c in got[1]]
    opaque = bool(layers) and layers[-1][3] >= 1
    base = layers[-1][:3] if opaque else page_bg[:3]
    for lay in reversed(layers[:-1] if opaque else layers):
        base = _over(lay, base)
    r = ratio(_over(fg, base), base)
    notes.append(f"contrast {label:<16} {lang}/{theme}: {r:.2f}:1")
    if r < 4.5:
        fails.append(f"CONTRAST FAIL {label} {lang}/{theme}: {r:.2f} < 4.5")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "wl1_shots"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed: pip install playwright && playwright install")
        return 1

    _Pages.bodies, tickers = render_pages()
    srv, port = serve()
    base = f"http://127.0.0.1:{port}/"
    fails: list = []
    notes: list = []

    label = _Pages.label
    # state -> (which SSR page, payload or None)
    specimens = {
        "provisional": ("plain", payload(tickers, rel="ahead", note="ahead")),
        "confirmed": ("receipt", None),
        "stale": ("plain", payload(tickers, rel="behind", note="behind", label=label)),
        "closed": ("plain", payload(tickers, rel="behind", note="closed", label=label)),
    }

    with sync_playwright() as p:
        b = _browser(p)
        for lang in ("en", "zh"):
            for theme in ("dark", "light"):
                offsets: dict = {}
                for state, (page_key, body) in specimens.items():
                    _Payload.body = body
                    ctx = b.new_context(viewport={"width": WIDTHS[0], "height": 1400},
                                        device_scale_factor=2)
                    ctx.add_init_script(TIER_SHIM)
                    ctx.add_init_script(CLOCK_SHIM % _iso(NOW))
                    ctx.add_init_script(
                        "document.addEventListener('DOMContentLoaded',function(){"
                        "document.documentElement.setAttribute('data-theme',%r);"
                        "document.documentElement.setAttribute('data-lang',%r);});"
                        % (theme, lang))
                    pg = ctx.new_page()
                    pg.goto(base + PAGE % page_key, wait_until="load")
                    pg.wait_for_timeout(900)          # first fetch + paint

                    panel = pg.query_selector("#us-standouts")
                    if panel is None:
                        fails.append(f"NO PANEL {state} {lang}/{theme}")
                        ctx.close()
                        continue

                    # ── stamp exclusivity (§0-5): never two, none on the confirmed board
                    stamps = pg.evaluate(STAMPS_JS)
                    want = 0 if state == "confirmed" else 1
                    if len(stamps) != want:
                        fails.append(f"STAMP COUNT {state} {lang}/{theme}: "
                                     f"{len(stamps)} != {want} — {stamps}")
                    notes.append(f"stamp {state:<12} {lang}/{theme}: {stamps}")

                    # ── one note, and the right one
                    shown = pg.evaluate(NOTE_JS)
                    kind = {"provisional": "ahead", "confirmed": "confirmed",
                            "stale": "behind", "closed": "closed"}[state]
                    if len(shown) != 1 or not shown[0].startswith(kind + "|"):
                        fails.append(f"NOTE {state} {lang}/{theme}: {shown}")
                    notes.append(f"note  {state:<12} {lang}/{theme}: {shown[0][:110] if shown else '—'}")

                    # ── perforated edge only on the provisional panel
                    edge = pg.evaluate(EDGE_JS)
                    has = edge.startswith("repeating-linear-gradient")
                    if has != (state == "provisional"):
                        fails.append(f"EDGE {state} {lang}/{theme}: {edge[:60]!r}")

                    # ── glance-tier vocabulary, scoped to the new surface
                    text = pg.evaluate(
                        "() => [...document.querySelectorAll('#us-standouts .pbs:not([hidden]),"
                        " #us-standouts .pbs-nv:not([hidden])')].map(e=>e.innerText).join(' ')")
                    for word in BANNED:
                        if word.lower() in text.lower():
                            fails.append(f"BANNED VOCAB {word!r} on {state} {lang}/{theme}")

                    # ── no motion introduced
                    for m in pg.evaluate(MOTION_JS):
                        if "|absent" in m:
                            continue
                        if "|none|" not in m:
                            fails.append(f"UNEXPECTED ANIMATION {state} {lang}/{theme}: {m}")

                    # ── contrast, measured after compositing, in both themes
                    if state in ("provisional", "confirmed", "stale"):
                        page_bg = _rgb(pg.evaluate(
                            "getComputedStyle(document.body).backgroundColor"))
                        pairs = [("note line", ".pbs-note .pbs-nv:not([hidden])")]
                        if state == "provisional":
                            pairs += [("stamp ahead", ".pbs-ahead:not([hidden])"),
                                      ("note stance", ".pbs-nv:not([hidden]) b")]
                        if state == "stale":
                            pairs += [("stamp behind", ".pbs-behind:not([hidden])")]
                        if state == "confirmed":
                            pairs += [("mark adjusted", ".pv-mk-adj"),
                                      ("receipt figure", ".pbs-fig")]
                        for lbl, sel in pairs:
                            _measure_contrast(pg, page_bg, lbl, sel, notes, fails,
                                              lang, theme)

                    # ── crops + the height sweep
                    for w in WIDTHS:
                        pg.set_viewport_size({"width": w, "height": 1400})
                        pg.wait_for_timeout(140)
                        offsets.setdefault(w, {})[state] = pg.evaluate(OFFSET_JS)
                        if w == WIDTHS[0]:
                            box = panel.bounding_box()
                            pg.screenshot(
                                path=str(out / f"wl1_{state}_{lang}_{theme}.png"),
                                clip={"x": box["x"], "y": box["y"], "width": box["width"],
                                      "height": min(box["height"], CROP_H)})
                    ctx.close()

                # ── header height invariance (§0-4): the flip must not shove the grid
                for w, per_state in offsets.items():
                    vals = list(per_state.values())
                    spread = max(vals) - min(vals)
                    notes.append(
                        f"header→grid {lang}/{theme} @{w}px"
                        + ("" if w in GATED_WIDTHS else " (measured, not gated)") + ": "
                        + ", ".join(f"{k}={v:.1f}" for k, v in per_state.items())
                        + f"  (spread {spread:.2f}px)")
                    if spread > 4 and w in GATED_WIDTHS:
                        fails.append(f"HEADER SHOVE {lang}/{theme} @{w}px: "
                                     f"spread {spread:.2f}px > 4")

        # ── §0-2: the gate. A payload describing a DIFFERENT board paints no stamp.
        for name, body in (
            ("other board", payload(["ZZZZ"] + tickers[1:], rel="ahead", note="ahead")),
            ("reordered board", payload(list(reversed(tickers)), rel="ahead", note="ahead")),
            ("expired", payload(tickers, rel="ahead", note="ahead", valid_h=-1)),
            ("ancient", payload(tickers, rel="ahead", note="ahead",
                                born_h=200, valid_h=1000)),
            ("no payload", None),
        ):
            _Payload.body = body
            ctx = b.new_context(viewport={"width": 1280, "height": 1400})
            ctx.add_init_script(TIER_SHIM)
            ctx.add_init_script(CLOCK_SHIM % _iso(NOW))
            pg = ctx.new_page()
            pg.goto(base + PAGE % "plain", wait_until="load")
            pg.wait_for_timeout(900)
            stamps = pg.evaluate(STAMPS_JS)
            notes.append(f"identity refusal [{name}]: stamps={stamps}")
            if stamps:
                fails.append(f"LIED TO THE READER [{name}]: painted {stamps}")
            ctx.close()

        # …and the matching board DOES paint, or the refusals above prove nothing.
        _Payload.body = payload(tickers, rel="ahead", note="ahead")
        ctx = b.new_context(viewport={"width": 1280, "height": 1400})
        ctx.add_init_script(TIER_SHIM)
        ctx.add_init_script(CLOCK_SHIM % _iso(NOW))
        pg = ctx.new_page()
        pg.goto(base + PAGE % "plain", wait_until="load")
        pg.wait_for_timeout(900)
        matching = pg.evaluate(STAMPS_JS)
        notes.append(f"identity match: stamps={matching}")
        if len(matching) != 1:
            fails.append("CONTROL FAILED: a matching board did not paint its stamp — "
                         "the refusals above prove nothing")
        ctx.close()
        b.close()

    srv.shutdown()
    print("\n".join(notes))
    print()
    if fails:
        print("FAILED:")
        for f in fails:
            print("  ·", f)
        return 1
    print(f"ALL PROOFS PASS — 16 crops written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
