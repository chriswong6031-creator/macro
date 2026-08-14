"""W4 visual gate — browser-driven crops of the REAL per-ticker Intelligence Drawer.

Same discipline as the W2 and W3 harnesses beside it, and the same refusal to stage
anything: every shot renders `templates/watchlist.html.j2` through the builder's own
context, runs the page's OWN scripts against the REAL nightly artifacts in `site/`, and
seeds only a BOOK (and a watchlist) in localStorage — the stores a real visitor's state
lives in. Every sentence in these crops is the page composing over those artifacts.

WHAT THIS WAVE'S HARNESS HAS TO CATCH THAT THE LAST ONE DID NOT. W3 learned that a bare
agent worktree has no `site/stockdata/`, so the page degrades exactly as designed and
photographs as a working page with a thin book. W4's drawer degrades the same way, one
level finer: EVERY SECTION has an honest-absence line, so a drawer with no artifacts
behind it renders thirteen beautifully-worded rows that all say "not covered". That is
the wave's own success criterion rendering as a total data failure — the most persuasive
false green available to this build. So the gate asserts BOTH directions:

  * the rich name's drawer must contain NO absent-branch rows, and
  * the sparse name's drawer must contain SOME — and also some real ones.

A run where every row is honest is a run with no data, and it exits non-zero.

Also asserted rather than eyeballed: no page errors; zero PAGE-level horizontal scroll
at 390px with a drawer open (the drawer is the widest thing on the page); the anonymous
drawer is a lock shell carrying no lane rows at all; and the drawer opens from BOTH
modes' rows, which is the acceptance row a screenshot of one mode cannot prove.

Run:  python3 mockups/refs/psi/workspace/crops/impl/w4/shoot_w4_crops.py
Needs a browser (playwright) and the repo's own site/ artifacts — hand-run, for the
reason recorded in ../IMPLEMENTATION_DELTAS.md: the CI packs install a minimal
dependency set, so a pytest wrapper here would SKIP in CI and report green while proving
nothing. The node-shelled half of this wave's evidence is `tests/test_watchlist_drawer_js.py`,
which DOES run in CI.
"""
import functools
import http.server
import json
import pathlib
import re
import socketserver
import subprocess
import sys
import threading
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve()
# w4 / impl / crops / workspace / psi / refs / mockups / <worktree>
ROOT = HERE.parents[7]
assert (ROOT / "templates" / "watchlist.html.j2").exists(), ROOT
OUT = HERE.parent
SITE = ROOT / "site"
PORT = 8874
BASE = "http://127.0.0.1:%d" % PORT

DESKTOP = (1440, 900)
MOBILE = (390, 844)

VARIANTS = [
    ("desktop_dark_en", DESKTOP, None, None),
    ("desktop_light_en", DESKTOP, "light", None),
    ("desktop_dark_zh", DESKTOP, None, "zh"),
    ("390_dark_en", MOBILE, None, None),
    ("390_dark_zh", MOBILE, None, "zh"),
]

# The twelve-position book the W2/W3 harnesses use, plus a watchlist, because W4's
# acceptance row is that the drawer opens from BOTH modes' rows.
WL = ["AAPL", "NVDA", "MSFT", "AVGO", "LLY", "GLD", "TLT", "XOM"]
SEED = ("window.__W2.clear(); window.__W2.book();"
        "window.__W2.list(%s); window.__W2.seen(%s);" % (json.dumps(WL), json.dumps(WL)))
SEED_ANON = ("window.__W2.clear();"
             "window.__W2.entry('AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, GLD, TLT','equal');")

# The rich name and the sparse one, chosen by READING the artifacts rather than by
# guessing: AAPL carries an options plane, theme memberships and a note trail; TLT
# carries none of the three and does carry macro sensitivity and ownership filings. The
# second is the wave's honest-degradation scene and it must not be a drawer of nothing.
RICH = ("loc-3", "AAPL")
SPARSE = ("loc-11", "TLT")


def link_nightly_artifacts() -> list:
    """Borrow `site/stockdata/` from the main checkout for the duration of the shoot.

    THE TRAP THIS EXISTS FOR, restated for W4 because it bites harder here. `site/
    stockdata/` is an untracked nightly artifact directory; a fresh agent worktree has
    none of it. The drawer then composes over `null` for every name and renders its
    honest-absence line in every section — thirteen well-written rows saying nothing is
    covered. Photographed, that is indistinguishable from a working drawer on a quiet
    name, and it is the exact evidence this wave is supposed to produce. The assertions
    in `main` exist because the picture cannot tell you which one you got.

    Removed in `main`'s finally block: an untracked symlink left in the tree blocks the
    ship-loop guard.
    """
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.strip()
    primary = pathlib.Path(common).parent
    made = []
    for name in ("stockdata",):
        src, dst = primary / "site" / name, SITE / name
        if dst.exists() or dst.is_symlink():
            continue
        if not src.is_dir():
            print("WARNING: %s not found in the main checkout — every drawer row will be "
                  "the honest-absence line, which is NOT evidence for this wave." % src)
            continue
        dst.symlink_to(src)
        made.append(dst)
        print("linked", dst, "->", src, "(%d files)" % len(list(src.iterdir())))
    return made


def render_preview() -> None:
    sys.path.insert(0, str(ROOT))
    from jinja2 import Environment, FileSystemLoader
    from engine.cycles import STATE_DISPLAY

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    html = env.get_template("watchlist.html.j2").render(
        generated_utc="2026-08-13 09:00",
        state_display_json=json.dumps(STATE_DISPLAY),
        supabase_cfg_json="null",
        wri_regime_json=json.dumps({
            "state": "calm",
            "dominant_label_en": "Liquidity easing",
            "dominant_label_zh": "流动性宽松",
            "asof": "2026-08-13",
        }),
        starters_json=json.dumps(["NVDA", "MSFT", "GLD", "TLT"]),
    )
    # hand-authored ?v=N stamps mean a browser that already loaded v=N keeps the stale
    # body across renders — bust them per run. Preview-only.
    tok = str(int(time.time()))
    html = re.sub(r'(src|href)="([a-z_0-9.]+\.(?:js|css))(\?v=\d+)?"',
                  lambda m: '%s="%s?cb=%s"' % (m.group(1), m.group(2), tok), html)
    html = html.replace("<head>", '<head>\n<script src="__w4seed.js"></script>', 1)
    (SITE / "__w4preview.html").write_text(html)
    (SITE / "__w4seed.js").write_text((OUT.parent / "preview_seed.js").read_text())
    print("rendered preview ->", SITE / "__w4preview.html")

    # ANONYMOUS variant — the four account-gated scripts are REMOVED, not disabled,
    # which is what production does (they 401 behind the wall and never execute). The
    # drawer's anonymous branch is reached by their ABSENCE, so simulating the wall with
    # a flag would test a different code path from the one that ships.
    anon = html
    for g in ("stockdata.js", "watchlist_risk.js", "risk_core.js", "factor_exposure.js"):
        anon = re.sub(r'<script src="%s[^"]*"></script>\n?' % re.escape(g), "", anon)
        assert ('src="%s' % g) not in anon, g
    (SITE / "__w4preview_anon.html").write_text(anon)
    print("rendered anon preview ->", SITE / "__w4preview_anon.html")


def serve() -> socketserver.TCPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def hide_launcher(page):
    """The chat launcher is a shared global widget, not this page's design, and it is
    position:fixed so it lands inside an ELEMENT crop too. A style RULE, not per-node
    inline display: the launcher mounts asynchronously and re-mounts on re-render.

    THE ID IS `#mmb-launch`, VERIFIED IN THE PAGE. The W2/W3 harnesses hide
    `#mm-brain-launcher, .mm-brain-launcher, #mmb-launcher, [class*="brain-launcher"]` —
    four selectors, none of which the widget actually carries — so that rule has been a
    no-op in every crop those harnesses ever took, and the launcher is simply absent
    from most of them by luck of where it lands. Derived here by enumerating every
    position:fixed element on the rendered page rather than by copying the list forward.
    The scrim and panel are named too: they are siblings of the same widget and a
    mid-shoot mount of either would tint a whole crop."""
    page.evaluate(
        "()=>{if(document.getElementById('__nolauncher'))return;"
        "var s=document.createElement('style');s.id='__nolauncher';"
        "s.textContent='#mmb-launch,#mmb-scrim,#mmb-panel,#mm-brain-launcher,"
        ".mm-brain-launcher,#mmb-launcher,[class*=\"brain-launcher\"]"
        "{display:none !important}';"
        "document.head.appendChild(s);}"
    )
    # and prove it worked, rather than assuming the selector matched — the whole reason
    # this function needed rewriting is that nobody checked
    left = page.evaluate(
        "()=>{var n=document.getElementById('mmb-launch');"
        "return n?getComputedStyle(n).display:'absent';}")
    assert left in ("none", "absent"), "the chat launcher is still visible: %r" % left


def prepare(page, size, theme, lang, seed=None, url=None):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(url or (BASE + "/__w4preview.html"), wait_until="domcontentloaded")
    page.evaluate(seed or SEED)
    page.evaluate(
        "([t,l])=>{try{t?localStorage.setItem('theme',t):localStorage.removeItem('theme');"
        "l?localStorage.setItem('lang',l):localStorage.removeItem('lang');}catch(e){}}",
        [theme, lang],
    )
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(3000)      # per-name hydration + the settled re-render
    hide_launcher(page)


def open_holding(page, row_id):
    page.evaluate("(id)=>{var b=document.querySelector('.hold [data-row-exp=\"'+id+'\"]');"
                  "if(b)b.click();}", row_id)
    page.wait_for_timeout(420)


def open_watch(page, ticker):
    page.evaluate("(t)=>{var b=document.querySelector('#tbl_wl [data-exp=\"'+t+'\"]');"
                  "if(b)b.click();}", ticker)
    page.wait_for_timeout(420)


def drawer_stats(page):
    """What the open drawer actually contains — the numbers the gate is made of."""
    return page.evaluate(
        "()=>{var d=document.querySelector('tr.row-drawer');"
        "if(!d)return {found:false};"
        "var rows=d.querySelectorAll('.wri-lrow');"
        "var na=d.querySelectorAll('.wri-lrow .st.na');"
        "var blank=0;"
        "rows.forEach(function(r){var s=r.querySelector('.rs');"
        "if(!s||!(s.innerText||'').trim())blank++;});"
        "return {found:true, rows:rows.length, na:na.length, blank:blank,"
        " lock:d.querySelectorAll('.lockshell').length,"
        " t1:d.querySelectorAll('.drw-t1').length,"
        " text:(d.innerText||'').slice(0,4000)};}")


def hscroll(page):
    return page.evaluate("()=>{var d=document.documentElement;return d.scrollWidth-d.clientWidth;}")


def shoot(page, name):
    # re-asserted per shot, not once per scene: the launcher mounts asynchronously and
    # RE-mounts, and it is position:fixed, so it lands inside an element crop of a
    # drawer near the bottom of the viewport. W3 recorded the same leak; a rule injected
    # at prepare() time is not enough when the widget re-mounts after it.
    hide_launcher(page)
    d = page.locator("tr.row-drawer").first
    d.screenshot(path=str(OUT / (name + ".png")))
    print("  ->", name + ".png")


def main():
    linked = link_nightly_artifacts()
    render_preview()
    srv = serve()
    errs, overflow, problems = [], [], []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ctx = b.new_context(device_scale_factor=2)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errs.append(str(e)))

            for vstem, size, theme, lang in VARIANTS:
                print(vstem)
                prepare(page, size, theme, lang)

                # ---- 01/02 the RICH name, from a HOLDINGS row --------------
                open_holding(page, RICH[0])
                st = drawer_stats(page)
                if not st["found"]:
                    problems.append((vstem, "rich drawer did not open"))
                else:
                    # the whole drawer: Tier 1 + every Tier-2 section
                    shoot(page, "02_tier2_expanded_%s_%s" % (RICH[1], vstem))
                    # Tier 1 alone — the glance read, which is a different claim
                    hide_launcher(page)
                    page.locator("tr.row-drawer .drw-t1").first.screenshot(
                        path=str(OUT / ("01_tier1_%s_%s.png" % (RICH[1], vstem))))
                    print("  ->", "01_tier1_%s_%s.png" % (RICH[1], vstem))
                    if st["rows"] < 12:
                        problems.append((vstem, "rich drawer had %d rows, expected >=12" % st["rows"]))
                    if st["blank"]:
                        problems.append((vstem, "%d drawer rows rendered an EMPTY read" % st["blank"]))
                    # THE FALSE-GREEN GATE. With no artifacts every section renders its
                    # honest-absence line and the drawer photographs as a working one.
                    if st["na"] > 3:
                        problems.append((vstem, "rich drawer rendered %d not-covered rows — "
                                                "this run had no data behind it" % st["na"]))
                    if st["t1"] != 1:
                        problems.append((vstem, "Tier 1 block count = %d" % st["t1"]))
                if size == MOBILE and hscroll(page) > 0:
                    overflow.append((vstem, "rich-drawer", hscroll(page)))
                open_holding(page, RICH[0])          # close

                # ---- 03 a name whose artifacts are genuinely thin -----------
                open_holding(page, SPARSE[0])
                st = drawer_stats(page)
                if not st["found"]:
                    problems.append((vstem, "sparse drawer did not open"))
                else:
                    shoot(page, "03_degraded_%s_%s" % (SPARSE[1], vstem))
                    if st["blank"]:
                        problems.append((vstem, "%d sparse rows rendered EMPTY" % st["blank"]))
                    # both halves of honest degradation, in one drawer
                    if st["na"] < 1:
                        problems.append((vstem, "the sparse name reported no gaps at all"))
                    if st["na"] >= st["rows"]:
                        problems.append((vstem, "the sparse drawer was ENTIRELY gaps — no data"))
                if size == MOBILE and hscroll(page) > 0:
                    overflow.append((vstem, "sparse-drawer", hscroll(page)))
                open_holding(page, SPARSE[0])

                # ---- 04 the same composer, from a WATCHLIST row ------------
                page.evaluate("()=>{window.__W2.mode('watchlists');}")
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(3000)
                hide_launcher(page)
                open_watch(page, RICH[1])
                st = drawer_stats(page)
                if not st["found"]:
                    problems.append((vstem, "watchlist drawer did not open"))
                else:
                    shoot(page, "04_watchlist_mode_%s_%s" % (RICH[1], vstem))
                    if st["rows"] < 12:
                        problems.append((vstem, "watchlist drawer had %d rows" % st["rows"]))
                    # a watched name is not a position, and the drawer says so rather
                    # than inventing a weight for it
                    if "watchlist" not in st["text"] and "自选" not in st["text"]:
                        problems.append((vstem, "the watchlist drawer did not say the name is not held"))
                if size == MOBILE and hscroll(page) > 0:
                    overflow.append((vstem, "watchlist-drawer", hscroll(page)))
                page.evaluate("()=>{window.__W2.mode('portfolio');}")

                # ---- 05 the ANONYMOUS drawer -------------------------------
                prepare(page, size, theme, lang, seed=SEED_ANON,
                        url=BASE + "/__w4preview_anon.html")
                page.evaluate("()=>{var b=document.querySelector('.hold [data-exp],"
                              ".hold [data-row-exp]');if(b)b.click();}")
                page.wait_for_timeout(420)
                st = drawer_stats(page)
                if not st["found"]:
                    problems.append((vstem, "anonymous drawer did not open"))
                else:
                    shoot(page, "05_anon_locked_%s" % vstem)
                    if not st["lock"]:
                        problems.append((vstem, "the anonymous drawer is not a lock shell"))
                    # zero gated signal, of any kind, anywhere in it
                    if st["rows"]:
                        problems.append((vstem, "the anonymous drawer rendered %d lane rows"
                                                % st["rows"]))
                if size == MOBILE and hscroll(page) > 0:
                    overflow.append((vstem, "anon-drawer", hscroll(page)))

            # ---- the large-list law, measured once (no crop) ---------------
            # "Opening and closing drawers across a 100-name list does not degrade the
            # table." Asserted rather than assumed, because the failure is gradual: the
            # drawer is rendered by the row renderer, so every toggle re-renders the
            # whole table, and a composition that got expensive would show up as a
            # table that slowly loses rows or a page that grinds. Both are measured.
            print("100-name list — drawer open/close")
            prepare(page, DESKTOP, None, None, seed=(
                "window.__W2.clear(); window.__W2.book();"
                "var all=window.__W2.WL55.concat(['SPY','QQQ','IWM','DIA','XLK','XLF',"
                "'XLE','XLV','XLI','XLY','XLP','XLU','XLB','XLRE','SMH','SOXX','ARKK',"
                "'TSLA','NFLX','DIS','BA','CAT','DE','HON','GE','MMM','UPS','FDX','LMT',"
                "'RTX','NOC','GD','V','MA','JPM','BAC','WFC','GS','MS','C','AXP','PYPL',"
                "'COIN','HOOD','ORLY']).slice(0,100);"
                "window.__W2.list(all); window.__W2.seen(all);"
                "window.__W2.mode('watchlists');"))
            n0 = page.evaluate("()=>document.querySelectorAll('#tbl_wl tbody tr[data-t]').length")
            t0 = time.time()
            syms = page.evaluate(
                "()=>Array.from(document.querySelectorAll('#tbl_wl tbody tr[data-t]'))"
                ".slice(0,20).map(function(n){return n.getAttribute('data-t');})")
            for s in syms:                      # open twenty, then close them again
                open_watch(page, s)
            openn = page.evaluate("()=>document.querySelectorAll('tr.row-drawer').length")
            for s in syms:
                open_watch(page, s)
            elapsed = time.time() - t0
            n1 = page.evaluate("()=>document.querySelectorAll('#tbl_wl tbody tr[data-t]').length")
            left = page.evaluate("()=>document.querySelectorAll('tr.row-drawer').length")
            print("   rows %d -> %d · %d drawers opened · %d left after closing · %.1fs"
                  % (n0, n1, openn, left, elapsed))
            if n0 < 100:
                problems.append(("large-list", "seeded 100 names, table rendered %d" % n0))
            if n1 != n0:
                problems.append(("large-list", "table lost rows across drawer toggles: "
                                               "%d -> %d" % (n0, n1)))
            if openn != len(syms):
                problems.append(("large-list", "%d drawers opened, expected %d"
                                 % (openn, len(syms))))
            if left:
                problems.append(("large-list", "%d drawers survived their own close" % left))
            b.close()
    finally:
        srv.shutdown()
        for f in ("__w4preview.html", "__w4preview_anon.html", "__w4seed.js"):
            p = SITE / f
            if p.exists():
                p.unlink()
        for p in linked:
            if p.is_symlink():
                p.unlink()

    ok = True
    if errs:
        print("PAGE ERRORS:", errs[:6]); ok = False
    else:
        print("no page errors")
    if problems:
        print("DRAWER PROBLEMS:")
        for p in problems:
            print("   ", p)
        ok = False
    else:
        print("every drawer opened, rendered real reads, and disclosed its own gaps")
    if overflow:
        print("PAGE-LEVEL HORIZONTAL SCROLL at 390px:", overflow); ok = False
    else:
        print("zero page-level horizontal scroll at 390px with a drawer open")
    sys.exit(0 if ok else 1)


main()
