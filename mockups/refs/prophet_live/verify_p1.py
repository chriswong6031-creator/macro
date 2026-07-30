"""Prophet Live P1 acceptance harness — the PRODUCTION page, not the mockup.

    python3 mockups/refs/prophet_live/verify_p1.py [--out DIR]

What it does, and why each part is not optional:

  1. Renders ``templates/dashboard.html.j2`` with ``mode='stocks'`` through the house
     harness env (``tests/test_dashboard_template_render.py``'s ``_env()`` / ``_base_vm()``)
     but with the REAL ``site/factordata/us_standouts.json`` board — so the crops are
     production-shaped (real cards, real sparklines, real theme.css/theme.js), not a
     fixture in isolation.
  2. Serves ``site/`` over loopback HTTP so the page's own ``fetch('live/prophet_live.json')``
     resolves. A ``file://`` load cannot fetch, and ``page.route()`` does not intercept
     it — the whole point is to drive the REAL JS path, so the payload arrives the way
     production delivers it.
  3. Freezes the clock per specimen (``Date.now`` / ``new Date()`` shim installed at
     document-start) because every window in the component is an EASTERN clock window:
     without a frozen clock ``closed`` mode is unreachable except after 16:20 ET and the
     rail position is not reproducible.
  4. Shoots per-state crops in dark + light + zh via ``element.screenshot`` — which dodges
     the backdrop-filter scroll blackout a full-page shot hits on this page.
  5. Prints the five proofs the spec's §7 demands:
       · HEIGHT INVARIANCE — ``getBoundingClientRect().height`` of ``#prophet-live``
         identical across every mode, SWEPT over :data:`HEIGHT_WIDTHS` × en/zh (not
         sampled at the widths the PR body quotes — see that constant's note). This is the
         no-thrash gate: the strip must not move the board when the counts change every ~5
         minutes, and it must not move it when the MODE changes either.
       · COMPUTED STYLE — the states, hues and visibilities are read back off
         ``getComputedStyle``, never eyeballed off markup (house law). Includes the
         ``.pv-live[hidden]`` trap: a class-level ``display`` out-specifies the UA
         ``[hidden]`` rule, so without that one line every card grows an empty pill.
       · DOM FENCE (§6.5) — two identical loads that differ ONLY in the payload; after
         normalising every ``.pv-live`` slot to a placeholder the board's ``outerHTML``
         must be byte-identical. Anything else means the presentation tier reached into
         the graded board (DNR §1).
       · OVERLAY WRAP — the pre-existing desktop clipping bug: ``.pv-ov.pv-ovl``
         ``flex-wrap`` must be ``wrap`` at every desktop width, not only under the 680px
         query. Swept, and measured against today's 3-chip board as well as the 4-chip one.
       · ROW CELL GEOMETRY — no cell overlaps a neighbour and no row overflows the panel,
         at every breakpoint the component defines.

Exit code is non-zero when any proof fails, so this doubles as a pre-push gate.
"""
from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SITE = ROOT / "site"
PAGE_NAME = "_plv_verify.html"

sys.path.insert(0, str(ROOT))

#: Widths the height sweep must hold at, in BOTH languages and across every mode. Covers
#: each real phone/tablet class plus the component's own breakpoints (560/680) and both
#: sides of them. THIS LIST IS THE GATE: the first version of this harness hardcoded the
#: three configurations the PR body happened to quote, so it could only ever confirm what
#: was already claimed — and it passed while the panel shoved the board by up to 32.75px
#: at 320/340/412/428/440/460/480/500/600. Never trim this back to the widths you measured.
HEIGHT_WIDTHS = (320, 340, 360, 375, 390, 412, 428, 440, 460, 480, 500, 540,
                 560, 600, 640, 680, 700, 768, 900, 1024, 1180, 1440)

# ── Clock anchors (ET) ───────────────────────────────────────────────────────────
# 2026-07-30 is a Thursday. Each specimen pins the ET wall clock that makes its own
# state reachable; the UTC offsets below are EDT (UTC-4).
SESSION = "2026-07-30"
T_1541 = "2026-07-30T19:41:00Z"   # 15:41 ET — the brief's headline case
T_1312 = "2026-07-30T17:12:00Z"   # 13:12 ET — the two fade stories side by side
T_1120 = "2026-07-30T15:20:00Z"   # 11:20 ET — quiet tape
T_1645 = "2026-07-30T20:45:00Z"   # 16:45 ET — post-close, the rule that stops the
#                                   staleness gate lying every single evening


def _states(**names) -> dict:
    return dict(names)


def _live(pass_ts: str, states: dict, *, evaluated_n: int = 62, phase: str = "rth",
          dark_counts: dict | None = None, session: str = SESSION) -> dict:
    """A ``prophet_live.states/v1`` live artifact, shaped exactly like the producer's."""
    counts: dict[str, int] = {}
    for st in states.values():
        counts[st["state"]] = counts.get(st["state"], 0) + 1
    return {
        "schema": "prophet_live.states/v1",
        "status": "live",
        "states": states,
        "meta": {
            "pass_ts": pass_ts,
            "session_et": session,
            "session_phase": phase,
            "quote_asof": pass_ts,
            "delay_min": 15,
            "pack_as_of": "2026-07-29",
            "expected_session": "2026-07-29",
            "quotes_n": 1987,
            "evaluated_n": evaluated_n,
            "states": counts,
            "dark_counts": dark_counts or {},
            "unprobed": {"not_probed": 1516},
            "unprobed_n": 1516,
            "events_n": 0,
        },
    }


def _dark(pass_ts: str, reason: str, *, carry: dict | None = None,
          session: str = SESSION) -> dict:
    """A whole-artifact dark payload — no states, because a guessed state IS the failure."""
    return {
        "schema": "prophet_live.states/v1",
        "status": "dark",
        "reason": reason,
        "states": {},
        "prev_states": carry or {},
        "meta": {
            "pass_ts": pass_ts,
            "session_et": session,
            "session_phase": "rth",
            "pack_as_of": "2026-07-28",
            "expected_session": "2026-07-29",
            "quote_asof": pass_ts,
            "delay_min": 15,
            "dark_counts": {reason: 1},
        },
    }


def _cross(state: str, px: float, lvl: float | None, since: str | None, *,
           via: str | None = None, close: bool = False, passes: int = 3) -> dict:
    """One cross row.

    ``lvl``/``since`` are passed as ``None`` by the bare specimen so the em-dash
    degradation path is exercised by a real render rather than only asserted by a
    substring grep. The level key is ``cross_level_px`` — the pack's own name for the
    lower edge of the buyable interval. There is deliberately no ``cross_px`` anywhere:
    the forward ledger's ``cross_px`` is a fill price, a different quantity, and printing
    it under a "Cross level" heading would put one number under another's label.
    """
    st: dict = {"state": state, "entered": "cross", "price": px,
                "quote_age_min": 3.2, "passes": passes}
    if lvl is not None:
        st["cross_level_px"] = lvl
    if since is not None:
        st["since_ts"] = since
    if via:
        st["via"] = via
    if close:
        st["confirming_into_close"] = True
    return st


def _board(state: str, px: float, *, via: str | None = None, close: bool = False,
           fade_px: float | None = None) -> dict:
    """One board row. A board name's level is ``fade_px``, not ``cross_level_px`` — the
    key that is present IS which quantity it is, so the consumer reads them by name."""
    st: dict = {"state": state, "entered": "board", "price": px, "quote_age_min": 2.8,
                "passes": 4, "fails": 0, "since_ts": "2026-07-30T18:10:00Z"}
    if fade_px is not None:
        st["fade_px"] = fade_px
    if via:
        st["via"] = via
    if close:
        st["confirming_into_close"] = True
    return st


def build_specimens(cross_tickers: list[str], buy_tk: str, other_tk: str) -> dict:
    """The five strip states + the card-chip specimen, keyed by shot name.

    Strip rows use tickers that are in the near-decision population but NOT on the
    board — which is exactly the population the strip exists to surface. The
    ``Below range`` chip is deliberately placed on a card the board rendered as a
    **Buy**, because that is what makes the one-hue-law exception visible: an amber
    caution chip sitting on a green card. Painting it with the card hue would render
    the caution GREEN, i.e. claim it is part of the confirmed verdict.
    """
    c1, c2, c3, c4 = (cross_tickers + ["ONTO", "MLI", "CRS", "LFUS"])[:4]
    cards_payload = _live(T_1541, _states(**{
        buy_tk: _board("at_risk", 144.10, via="drop", fade_px=146.60),
        other_tk: _board("forming", 47.95, close=True, fade_px=47.08),
    }))
    return {
        "strip_live": (T_1541, _live(T_1541, _states(**{
            c1: _cross("forming", 224.60, 222.85, "2026-07-30T17:20:00Z"),
            c2: _cross("forming", 88.15, 87.40, "2026-07-30T19:05:00Z"),
            c3: _cross("forming", 286.40, 283.10, "2026-07-30T15:05:00Z", close=True),
        }))),
        # The two fade stories side by side — they must never share a word: a drop came
        # back TOWARD the entry, an overrun ran PAST it. Exactly 3 rows, so nothing is cut.
        "strip_faded": (T_1312, _live(T_1312, _states(**{
            c1: _cross("forming", 224.60, 222.85, "2026-07-30T15:40:00Z"),
            c2: _cross("faded", 86.62, 87.40, "2026-07-30T16:40:00Z", via="drop"),
            c3: _cross("faded", 301.75, 283.10, "2026-07-30T16:55:00Z", via="overrun"),
        }))),
        # 5 qualifying rows into 3 slots: proves the cap AND the reserved faded slot —
        # a faded row is never the silent cut, so 2 actives + the most recent faded show
        # and the overflow goes to the +N button.
        "strip_overflow": (T_1312, _live(T_1312, _states(**{
            c1: _cross("forming", 224.60, 222.85, "2026-07-30T15:40:00Z"),
            c2: _cross("faded", 86.62, 87.40, "2026-07-30T16:40:00Z", via="drop"),
            c3: _cross("faded", 301.75, 283.10, "2026-07-30T16:55:00Z", via="overrun"),
            c4: _cross("forming", 41.20, 40.85, "2026-07-30T16:10:00Z"),
            "AAPL": _cross("forming", 232.10, 230.90, "2026-07-30T17:00:00Z"),
        }))),
        # Neither optional field present — the em-dash path for BOTH the Cross level and
        # the SINCE column, rendered rather than merely asserted by a substring grep.
        "strip_bare": (T_1541, _live(T_1541, _states(**{
            c1: _cross("forming", 224.60, None, None),
            c2: _cross("faded", 86.62, None, None, via="drop"),
            c3: _cross("forming", 286.40, None, None, close=True),
        }))),
        "strip_quiet": (T_1120, _live(T_1120, _states())),
        # Producer-ATTESTED dark: it says stale_pack, so the strip may relay that cause.
        "strip_dark": (T_1120, _dark(T_1120, "stale_pack")),
        # No pass has run for today at all — the shape of every market holiday, and of a
        # down lane. The strip must NOT guess a cause here (m1): yesterday's file is simply
        # the newest one, which is not evidence of a stale watch list.
        "strip_noread": (T_1120, _live("2026-07-29T20:15:00Z", _states(), session="2026-07-29")),
        # Post-close. The pass_ts must be near the close or the strip stays dark rather
        # than laundering a producer that died hours earlier (m2).
        "strip_closed": (T_1645, _live("2026-07-30T20:15:00Z", _states(**{
            c1: _cross("forming", 224.60, 222.85, "2026-07-30T17:20:00Z", close=True),
            c2: _cross("faded", 86.62, 87.40, "2026-07-30T16:40:00Z", via="drop"),
        }))),
        "cards": (T_1541, cards_payload),
    }


# ── The page ─────────────────────────────────────────────────────────────────────

def render_page() -> tuple[list[str], list[str]]:
    """Render the real template and return (⚡ tickers, candidate cross tickers).

    The HTML is held IN MEMORY and served by the handler below, never written into
    ``site/``. A temp page there is picked up by the repo guards that scan ``site/**`` —
    ``check_validated_claims`` reported 21 unearned claims off this harness's own scratch
    file, because the page is a copy of the real board and inherits every phrase on it.
    Serving it from the server root keeps all the relative asset paths (theme.css,
    theme.js, factordata/…) resolving exactly as they do in production, with nothing on
    disk to leak into a guard, a commit, or a crashed run's leftovers.
    """
    from tests.test_dashboard_template_render import _base_vm, _env

    board = json.loads((SITE / "factordata" / "us_standouts.json").read_text())
    vm = _base_vm()
    vm["us_standouts"] = board
    # A ⚡ nightly trigger chip on the leading board cards, so the overlay actually
    # carries verb + ⚡ + ◐ (+ ⚠N) — the 4-chip row whose desktop clipping this PR fixes.
    trg = [r["ticker"] for r in board["buy"][:6]]
    vm["top_setups"] = {"buy": [{"ticker": t, "signal": {"tier_cascade": "T2"}} for t in trg]}

    _Page.body = _env().get_template("dashboard.html.j2").render(
        **vm, mode="stocks").encode()

    on_board = {r["ticker"] for r in board["buy"]}
    crosses = [r["ticker"] for r in (board.get("watch") or []) if r["ticker"] not in on_board]
    return trg, crosses[:4]


class _Payload:
    """The fixture the served live/prophet_live.json returns; swapped per specimen."""

    body: bytes | None = None
    hits = 0


class _Page:
    """The rendered us_stocks page, served from memory (see render_page)."""

    body: bytes | None = None


def serve() -> tuple[socketserver.TCPServer, int]:
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(SITE), **kw)

        def _json(self, body: bytes):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/" + PAGE_NAME and _Page.body is not None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(_Page.body)))
                self.end_headers()
                self.wfile.write(_Page.body)
                return
            if path == "/live/prophet_live.json":
                if _Payload.body is None:
                    self.send_error(404)
                    return
                _Payload.hits += 1
                self._json(_Payload.body)
                return
            if path == "/api/me":
                # tier_preview.js blurs every card past the first for an ANONYMOUS visitor
                # (anon cap = 1), which hides the very chips this harness has to
                # photograph. With the session cookie + this endpoint the harness resolves
                # as registered-free (cap 3) — three ungated cards, exactly the run the
                # card crop needs, and the tier most readers of this board are on. It
                # grants no data the page had not already rendered.
                self._json(b'{"tier":"free"}')
                return
            super().do_GET()

        def log_message(self, *a):  # silence
            return

    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# tier_preview.js resolves the visitor tier through MDXAuth + /api/me. Stubbing the
# client (and serving /api/me above) puts the harness on the paid tier, so no card is
# blurred out of the crop. Installed at document-start, before tier_preview.js runs.
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

BOARD_SIG = """
() => {
  var b = document.getElementById('us-standouts');
  if(!b) return null;
  var c = b.cloneNode(true), sl = c.querySelectorAll('.pv-live'), i;
  for(i=sl.length-1;i>=0;i--) sl[i].replaceWith(document.createComment('PLV-SLOT'));
  return c.outerHTML;
}
"""


def _browser(p):
    """Launch whatever Chromium this host can actually drive."""
    import os
    shell = Path(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium_headless_shell-1228/"
        "chrome-headless-shell-mac-arm64/chrome-headless-shell"))
    if shell.exists():
        return p.chromium.launch(executable_path=str(shell))
    return p.chromium.launch()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "p1_shots"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed: pip install playwright && playwright install")
        return 1

    trg_tks, cross_tks = render_page()
    srv, port = serve()
    base = f"http://127.0.0.1:{port}/{PAGE_NAME}"
    fails: list[str] = []
    specimens: dict = {}

    with sync_playwright() as p:
        browser = _browser(p)

        # Which of the ⚡-bearing cards did the board render as a BUY? The hue-exception
        # crop is only a proof if the amber ◐ chip lands on a GREEN card, and the verb is
        # derived inside the template from the row's own zone/price — not something this
        # harness may assume. So: read it off the rendered DOM first.
        _Payload.body = None
        ctx = browser.new_context(viewport={"width": 1180, "height": 1200})
        pg = ctx.new_page()
        pg.add_init_script(TIER_SHIM)
        pg.goto(base, wait_until="domcontentloaded")
        pg.wait_for_timeout(600)
        cards = pg.evaluate("""
        () => { const grids = [];
          return [...document.querySelectorAll('#us-standouts a.pvcard[data-ticker]')]
            .filter(c => c.offsetParent && !c.classList.contains('mx-tier-blurred')
                         && !c.classList.contains('mx-tier-hidden'))
            .map(c => { let g = grids.indexOf(c.parentElement);
                        if (g < 0) { g = grids.length; grids.push(c.parentElement); }
                        return {tk: c.getAttribute('data-ticker'),
                                buy: c.classList.contains('pv-buy'),
                                trg: !!c.querySelector('.pv-trg'), grid: g}; }); }
        """)
        ctx.close()
        # A contiguous run of three ungated cards in one grid holding at least one Buy and
        # one non-Buy: the Buy card carries the amber ◐ (the hue exception), the non-Buy
        # carries ◐ Holding into close, and the third is the untouched control.
        pick = None
        for i in range(len(cards) - 2):
            run = cards[i:i + 3]
            if len({c["grid"] for c in run}) != 1:
                continue
            buys = [c for c in run if c["buy"]]
            others = [c for c in run if not c["buy"]]
            if buys and others:
                pick = (buys[0]["tk"], others[0]["tk"], run)
                break
        if pick is None:
            print(f"  no contiguous Buy + non-Buy run among ungated cards: {cards[:9]}")
            return 1
        buy_tk, other_tk, crop_run = pick
        crop_tks = [c["tk"] for c in crop_run]
        specimens.update(build_specimens(cross_tks, buy_tk, other_tk))
        print(f"⚡ cards: {trg_tks}   ◐ Below range on BUY card {buy_tk}   "
              f"◐ Holding into close on {other_tk}   control card "
              f"{[t for t in crop_tks if t not in (buy_tk, other_tk)]}\n"
              f"   strip rows: {cross_tks}")

        def load(page, shot, theme, lang):
            ts, payload = specimens[shot]
            _Payload.body = json.dumps(payload).encode()
            page.add_init_script(CLOCK_SHIM % ts)
            page.add_init_script(TIER_SHIM)
            # Theme/language go through localStorage, NOT the attribute: the page's own
            # <head> boot script sets data-theme/data-lang from storage before paint and
            # would overwrite an attribute set here (it did — every zh crop came out in
            # English). Each specimen gets a fresh context, so nothing bleeds between shots.
            page.add_init_script(
                "(function(){try{localStorage.setItem('theme',%r);"
                "localStorage.removeItem('themeAuto');"
                "localStorage.setItem('lang',%r);}catch(e){}"
                "var h=document.documentElement;h.setAttribute('data-theme',%r);"
                "if(%r==='zh'){h.setAttribute('data-lang','zh')}"
                "})();" % (theme, lang, theme, lang))
            page.goto(base, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("#prophet-live.visible", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(260)

        # ── 1. Acceptance crops ──────────────────────────────────────────────
        print("\n── CROPS ──────────────────────────────────────────────────────")
        plan = [("strip_live", ("dark", "en")), ("strip_live", ("light", "en")),
                ("strip_live", ("dark", "zh")),
                ("strip_faded", ("dark", "en")), ("strip_faded", ("light", "en")),
                ("strip_faded", ("dark", "zh")),
                ("strip_overflow", ("dark", "en")), ("strip_overflow", ("dark", "zh")),
                ("strip_bare", ("dark", "en")),
                ("strip_quiet", ("dark", "en")), ("strip_quiet", ("light", "en")),
                ("strip_dark", ("dark", "en")), ("strip_dark", ("light", "en")),
                ("strip_dark", ("dark", "zh")),
                ("strip_noread", ("dark", "en")), ("strip_noread", ("dark", "zh")),
                ("strip_closed", ("dark", "en")), ("strip_closed", ("light", "en")),
                ("cards", ("dark", "en")), ("cards", ("light", "en")),
                ("cards", ("dark", "zh"))]
        for shot, (theme, lang) in plan:
            ctx = browser.new_context(viewport={"width": 1180, "height": 1500},
                                      device_scale_factor=2)
            page = ctx.new_page()
            load(page, shot, theme, lang)
            dest = out / f"{shot}_{theme}_{lang}.png"
            if shot == "cards":
                # Clip to the three cards of interest rather than shooting the whole
                # panel. The viewport stays 1180px so the component's own ≤680px queries
                # do NOT fire — the crop is narrow, the layout is desktop. (The committed
                # reference crops could not do this: their rasterizer resolved media
                # queries against the crop width, which is why they are panel-wide.)
                box = page.evaluate("""
                (tks) => { const r = tks.map(t => document.querySelector(
                    '.pvcard[data-ticker="'+t+'"]').getBoundingClientRect());
                  const P = 14;
                  return {x: Math.min(...r.map(b=>b.left))-P, y: Math.min(...r.map(b=>b.top))-P,
                          width: Math.max(...r.map(b=>b.right))-Math.min(...r.map(b=>b.left))+2*P,
                          height: Math.max(...r.map(b=>b.bottom))-Math.min(...r.map(b=>b.top))+2*P}; }
                """, crop_tks)
                page.screenshot(path=str(dest), clip=box)
                print(f"  {dest.name}  (cards {crop_tks})")
                ctx.close()
                continue
            el = page.query_selector("#prophet-live")
            if el is None:
                fails.append(f"crop {dest.name}: #prophet-live not in the DOM")
            else:
                el.screenshot(path=str(dest))
                print(f"  {dest.name}")
            ctx.close()

        # mobile
        for shot in ("strip_live", "strip_overflow"):
            ctx = browser.new_context(viewport={"width": 375, "height": 1100},
                                      device_scale_factor=2)
            page = ctx.new_page()
            load(page, shot, "dark", "en")
            el = page.query_selector("#prophet-live")
            if el:
                dest = out / f"{shot}_mobile_dark_en.png"
                el.screenshot(path=str(dest))
                print(f"  {dest.name}")
            ctx.close()

        # ── 2. Height invariance ─────────────────────────────────────────────
        # SWEPT, not sampled. The first version of this loop hardcoded
        # ((1180,"en"),(1180,"zh"),(375,"en")) — the three configurations the PR body
        # happened to report — so the gate could only ever confirm what was already
        # claimed. It passed while the panel shoved the board by up to 32.75px at nine
        # other widths. A gate that can only agree with you is not a gate.
        print("\n── HEIGHT INVARIANCE (spec §6.4 rule 1) — swept ───────────────")
        # EVERY strip specimen, derived — never a hand-written subset. The first sweep
        # listed the modes by hand and omitted `strip_noread`, the one mode added that
        # round, which was also the one still shoving (17.00px at 320/340 en, because the
        # as-of box had no line reservation). A specimen that exists but is not swept is a
        # crop that lies: it ships a picture with no proof behind it.
        # (derived, so a new specimen joins the sweep automatically — that IS the fix; a
        # follow-up "is every specimen covered?" check against the same source would be
        # vacuous by construction and prove nothing)
        modes = tuple(s for s in specimens if s != "cards")
        print(f"   modes swept ({len(modes)}): {', '.join(m.replace('strip_','') for m in modes)}")
        print(f"   widths swept ({len(HEIGHT_WIDTHS)}): "
              f"{', '.join(str(w) for w in HEIGHT_WIDTHS)}")
        print("   width lang | " + " ".join(f"{m.replace('strip_',''):>8}" for m in modes)
              + " |   variance")
        for lang in ("en", "zh"):
            for width in HEIGHT_WIDTHS:
                heights = {}
                for shot in modes:
                    ctx = browser.new_context(viewport={"width": width, "height": 1600})
                    page = ctx.new_page()
                    load(page, shot, "dark", lang)
                    heights[shot] = page.evaluate(
                        "() => {var e=document.getElementById('prophet-live');"
                        "return (e && !e.hidden) ? "
                        "+e.getBoundingClientRect().height.toFixed(2) : null;}")
                    ctx.close()
                vals = [h for h in heights.values() if h is not None]
                missing = [k for k, v in heights.items() if v is None]
                var = (max(vals) - min(vals)) if vals else 0.0
                ok = not missing and var <= 0.01
                print(f"  {width:6d} {lang}   | "
                      + " ".join(f"{heights[m]:8.2f}" if heights[m] is not None
                                 else "  HIDDEN" for m in modes)
                      + f" | {var:7.2f}  {'OK' if ok else 'SHOVE'}")
                if missing:
                    fails.append(f"height invariance {width}px {lang}: "
                                 f"panel hidden in {missing}")
                elif var > 0.01:
                    fails.append(f"height invariance {width}px {lang}: {var:.2f}px shove "
                                 f"({heights})")

        # ── 3. Computed style ────────────────────────────────────────────────
        print("\n── COMPUTED STYLE (house law: verify orders, don't eyeball) ────")
        probe = """
        () => {
          const cs = (el, p) => el ? getComputedStyle(el).getPropertyValue(p).trim() : null;
          // Read only the VISIBLE variant. The token / stance / footer boxes stack every
          // mode's text in one grid cell so the box reserves the worst case at this width;
          // textContent on the container would concatenate all of them and hide which one
          // is actually showing. This must read what the reader sees.
          const shown = id => { const e = document.getElementById(id); if (!e) return null;
            const on = e.querySelector('.plv-v.is-on');
            return ((on || e).textContent || '').trim(); };
          const nVis = id => { const e = document.getElementById(id);
            return e ? e.querySelectorAll('.plv-v').length : 0; };
          const panel = document.getElementById('prophet-live');
          const rows = [...document.querySelectorAll('#plv-body .plv-row')];
          const chip = k => document.querySelector('#plv-body .plv-chip--'+k);
          const slot = [...document.querySelectorAll('.pvcard .pv-live')];
          const hid = slot.filter(e => e.hasAttribute('hidden'));
          const vis = slot.filter(e => !e.hasAttribute('hidden'));
          return {
            panelDisplay: cs(panel,'display'),
            panelClasses: panel ? panel.className : null,
            rowCount: rows.length,
            tickers: rows.map(r => r.getAttribute('data-plv-tk')),
            token: shown('plv-token'), reserved: [nVis('plv-token'), nVis('plv-sub'), nVis('plv-fn')],
            asof: (document.getElementById('plv-asof')||{}).textContent,
            sub: shown('plv-sub'),
            body: (document.getElementById('plv-body')||{}).textContent,
            footer: shown('plv-fn'),
            more: (() => { const m=document.getElementById('plv-more');
                           return m ? {hidden:m.hidden, txt:m.textContent,
                                       exp:m.getAttribute('aria-expanded')} : null; })(),
            railFill: cs(document.getElementById('plv-rail-fill'),'width'),
            railNowDisplay: cs(document.getElementById('plv-rail-now'),'display'),
            colsVisibility: cs(document.querySelector('#plv-cols .plv-c2'),'visibility'),
            chipForming: cs(chip('forming'),'color'),
            chipClose:   { color: cs(chip('close'),'color'),
                           bg: cs(chip('close'),'background-color') },
            chipDrop:    cs(chip('drop'),'color'),
            chipOver:    cs(chip('over'),'color'),
            hiddenSlots: hid.length,
            hiddenSlotDisplay: hid.length ? cs(hid[0],'display') : null,
            hiddenSlotWidth:   hid.length ? cs(hid[0],'width') : null,
            visibleSlots: vis.map(e => ({tk: e.closest('.pvcard').getAttribute('data-ticker'),
                                         cls: e.className, txt: e.textContent.trim(),
                                         color: getComputedStyle(e).color,
                                         cardHue: getComputedStyle(
                                           e.closest('.pvcard').querySelector('.pv-chip')).color})),
            overlayWrap: cs(document.querySelector('.pvcard .pv-ov.pv-ovl'),'flex-wrap')
          };
        }
        """

        # The pre-existing DESKTOP bug this PR fixes in passing: .pv-ov.pv-ovl's
        # flex-wrap lived only inside @media (max-width:680px), so at desktop width a
        # left overlay wider than .pv-ov{max-width:70%} did not wrap — the excess chip
        # ran UNDER the price pill. Measured both ways on the widest overlay on the
        # board: `wrap` (shipped) vs `nowrap` (the old behaviour, forced back).
        OVERLAY_PROBE = """
        (force) => {
          const cards = [...document.querySelectorAll('.pvcard[data-ticker]')];
          let best = null;
          // VISIBLE children only — the reserved .pv-live slot is [hidden] on most cards
          // and counting it would overstate the chip count in the table below.
          const vis = o => [...o.querySelectorAll(':scope > *')]
            .filter(e => e.getBoundingClientRect().width > 0);
          for (const c of cards) {
            const o = c.querySelector('.pv-ov.pv-ovl'), px = c.querySelector('.pv-ov.pv-ovr');
            if (!o || !px) continue;
            const n = vis(o).length;
            if (!best || n > best.n) best = {c, o, px, n};
          }
          if (!best) return null;
          if (force) best.o.style.flexWrap = force;
          const b = best.px.getBoundingClientRect();
          // Measure the CHIPS, not the container: .pv-ov{max-width:70%} clamps the box,
          // so the box never reports the overflow — the chips run past it and under the
          // price pill, which is exactly why the bug was invisible to a box measurement.
          const kids = vis(best.o).map(e => e.getBoundingClientRect());
          const right = Math.max(...kids.map(r => r.right));
          const lines = new Set(kids.map(r => Math.round(r.top))).size === 1 ? 1
                      : Math.round(best.o.getBoundingClientRect().height /
                                   Math.max(...kids.map(r => r.height)));
          return {tk: best.c.getAttribute('data-ticker'), chips: best.n,
                  lines: Math.max(1, lines),
                  wrap: getComputedStyle(best.o).flexWrap,
                  chipsRight: +right.toFixed(1), pillLeft: +b.left.toFixed(1),
                  overlapPx: +(right - b.left).toFixed(1),
                  clipped: right > b.left,
                  cardH: +best.c.getBoundingClientRect().height.toFixed(2)};
        }
        """
        for shot in ("strip_live", "strip_faded", "strip_overflow", "strip_bare",
                     "strip_quiet", "strip_dark", "strip_noread", "strip_closed", "cards"):
            ctx = browser.new_context(viewport={"width": 1180, "height": 1500})
            page = ctx.new_page()
            load(page, shot, "dark", "en")
            r = page.evaluate(probe)
            print(f"\n  [{shot}] display={r['panelDisplay']} classes={r['panelClasses']!r}")
            print(f"    token={r['token']!r} asof={r['asof']!r}  "
                  f"(stacked variants token/sub/footer={r['reserved']})")
            print(f"    sub={r['sub']!r}")
            print(f"    rows={r['rowCount']} {r['tickers']} more={r['more']}")
            print(f"    body={r['body']!r}")
            print(f"    footer={r['footer']!r}")
            print(f"    rail fill={r['railFill']} nowDisplay={r['railNowDisplay']} "
                  f"colsVis={r['colsVisibility']}")
            print(f"    chips forming={r['chipForming']} close={r['chipClose']} "
                  f"drop={r['chipDrop']} over={r['chipOver']}")
            print(f"    card slots hidden={r['hiddenSlots']} display={r['hiddenSlotDisplay']} "
                  f"width={r['hiddenSlotWidth']}")
            for v in r["visibleSlots"]:
                print(f"      LIVE CHIP {v['tk']}: {v['txt']!r} cls={v['cls']!r} "
                      f"chip={v['color']} vs card verb hue={v['cardHue']}")
            print(f"    overlay flex-wrap={r['overlayWrap']}")
            if r["panelDisplay"] != "block":
                fails.append(f"{shot}: panel display={r['panelDisplay']}")
            if r["hiddenSlots"] and r["hiddenSlotDisplay"] != "none":
                fails.append(f"{shot}: .pv-live[hidden] display={r['hiddenSlotDisplay']} "
                             "— the empty mystery pill is back")
            if r["overlayWrap"] != "wrap":
                fails.append(f"{shot}: .pv-ov.pv-ovl flex-wrap={r['overlayWrap']} at 1180px")
            ctx.close()

        # ── 3b. Overlay wrap at DESKTOP widths (pre-existing bug, fixed in passing) ──
        # Swept across every desktop width ABOVE the 680px query, because the card grid is
        # auto-fill minmax(246px,1fr): the narrower the container, the closer a card sits
        # to its 246px floor and the less room the left overlay has. A single 1180px
        # measurement would miss the widths where the old rule actually clipped.
        print("\n── OVERLAY WRAP above 680px (pre-existing desktop clipping bug) ──")
        # Two payloads on purpose. `strip_quiet` puts NO live chip on any card, so the
        # board is byte-for-byte what production renders TODAY (verb + ⚡ + ⚠N) — that run
        # is the evidence for calling this a PRE-EXISTING bug rather than one P1 created.
        # `cards` adds the ◐ chip, i.e. the 4-chip overlay P1 makes routine.
        for label, shot in (("TODAY  (verb+⚡+⚠N, no ◐)", "strip_quiet"),
                            ("WITH ◐ (verb+⚡+◐+⚠N)   ", "cards")):
            print(f"  {label}   width | chips | SHIPPED wrap | OLD nowrap")
            worst_fixed, worst_buggy = None, None
            for w in (700, 760, 820, 900, 1000, 1180, 1400):
                ctx = browser.new_context(viewport={"width": w, "height": 1500})
                page = ctx.new_page()
                load(page, shot, "dark", "en")
                fx = page.evaluate(OVERLAY_PROBE, None)
                bg = page.evaluate(OVERLAY_PROBE, "nowrap")
                ctx.close()
                if fx is None:
                    continue
                fmark = "CLIPS" if fx["clipped"] else "clear"
                bmark = "CLIPS" if bg["clipped"] else "clear"
                print(f"      {w:6d} | {fx['chips']:5d} | {fx['lines']} line, "
                      f"{-fx['overlapPx']:+7.1f}px {fmark:5s} | {-bg['overlapPx']:+7.1f}px "
                      f"{bmark:5s}  [{fx['tk']}, card h={fx['cardH']}px both ways]")
                if fx["clipped"]:
                    fails.append(f"overlay still clips behind the price pill at {w}px ({shot})")
                if worst_buggy is None or bg["overlapPx"] > worst_buggy:
                    worst_buggy, worst_fixed = bg["overlapPx"], fx["overlapPx"]
            print(f"      worst: old rule {-worst_buggy:+.1f}px from the price pill, "
                  f"shipped rule {-worst_fixed:+.1f}px "
                  "(overlay is absolutely positioned — card height identical either way)")
        ctx = browser.new_context(viewport={"width": 1180, "height": 1500})

        # ── 3c. Row-cell geometry at narrow widths ───────────────────────────
        # A grid whose cells are auto-placed reshuffles when a middle cell is hidden, and
        # the symptom is two figures printed on top of each other rather than an error.
        # So: assert the cells are in ascending x with no horizontal overlap, and that the
        # row does not overflow the panel, at every breakpoint the component defines.
        print("\n── ROW CELL GEOMETRY (no overlap, no overflow) ─────────────────")
        CELL_PROBE = """
        () => {
          const rows = [...document.querySelectorAll('#plv-body .plv-row')];
          const body = document.getElementById('plv-body');
          const out = [];
          for (const r of rows) {
            const cells = [...r.children].filter(c => getComputedStyle(c).display !== 'none')
              .map(c => ({cls: c.className.replace('plv-','').split(' ')[0],
                          l: +c.getBoundingClientRect().left.toFixed(1),
                          rt: +c.getBoundingClientRect().right.toFixed(1)}));
            let bad = null;
            for (let i = 1; i < cells.length; i++) {
              if (cells[i].l < cells[i-1].rt - 0.6) { bad = cells[i-1].cls+'/'+cells[i].cls; break; }
            }
            out.push({tk: r.getAttribute('data-plv-tk'), n: cells.length, overlap: bad,
                      over: +(r.getBoundingClientRect().right -
                              body.getBoundingClientRect().right).toFixed(1)});
          }
          return out;
        }
        """
        for width in (1180, 680, 560, 375, 320):
            ctx = browser.new_context(viewport={"width": width, "height": 1400})
            page = ctx.new_page()
            load(page, "strip_live", "dark", "en")
            cells = page.evaluate(CELL_PROBE)
            ctx.close()
            worst = max((c["over"] for c in cells), default=0.0)
            olap = [c for c in cells if c["overlap"]]
            print(f"  {width:5d}px: {len(cells)} rows, {cells[0]['n'] if cells else 0} visible "
                  f"cells/row, widest row overflows panel by {worst:+.1f}px, "
                  f"overlaps={[c['overlap'] for c in olap] or 'none'}")
            if olap:
                fails.append(f"{width}px: row cells overlap {[c['overlap'] for c in olap]}")
            if worst > 0.6:
                fails.append(f"{width}px: row overflows the panel by {worst:+.1f}px")

        # ── 4. DOM fence (§6.5) ──────────────────────────────────────────────
        print("\n── DOM FENCE (§6.5 — presentation tier may not touch the board) ")
        sigs = {}
        for shot in ("strip_quiet", "cards", "strip_live"):
            ctx = browser.new_context(viewport={"width": 1180, "height": 1500})
            page = ctx.new_page()
            load(page, shot, "dark", "en")
            sigs[shot] = page.evaluate(BOARD_SIG)
            ctx.close()
        base_sig = sigs["strip_quiet"]
        for shot, sig in sigs.items():
            same = sig == base_sig
            print(f"  payload={shot:12s} board signature {'IDENTICAL' if same else 'DIFFERS'} "
                  f"({len(sig or '')} chars, .pv-live slots normalised)")
            if not same:
                fails.append(f"DOM fence: payload {shot} changed the board outside .pv-live")

        browser.close()
    srv.shutdown()
    # nothing to clean up: the page was never written to disk (see render_page)

    print("\n── VERDICT ────────────────────────────────────────────────────")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        return 1
    print("  all proofs pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
