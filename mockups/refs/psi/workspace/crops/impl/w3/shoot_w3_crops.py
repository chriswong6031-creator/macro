"""W3 visual gate — browser-driven crops of the REAL Risk Center.

Same discipline as the W2 harness beside it (`../shoot_crops.py`), and the same
refusal to stage anything: every shot renders `templates/watchlist.html.j2` through
the builder's own context, runs the page's OWN scripts against the REAL nightly
artifacts in `site/` (the stockdata index, per-ticker JSON, `factor_betas.json`),
and seeds only a BOOK in localStorage — the store a real visitor's book lives in.
Every figure in these crops is the page computing over that book.

Two differences from the W2 harness, both deliberate:

  1. ROOT is DERIVED from this file's location rather than hardcoded. W2's copy
     pins an absolute path into a worktree that no longer exists, so it cannot be
     re-run by the next session. This one runs from wherever it is checked out.
  2. The Risk Center shots are ELEMENT crops of `#ws_sec_rc`, not full pages. The
     subject of this wave is one panel; a 2x full-page shot of a twelve-position
     workspace buries it and costs ten times the bytes. The one full-page shot is
     `08_empty_watchlist_portfolio`, where the whole page IS the subject.

The 390px horizontal-scroll law is asserted here rather than eyeballed: every tab
is measured at 390 and the run exits non-zero if any of them lets the PAGE scroll
sideways.

Run:  python3 mockups/refs/psi/workspace/crops/impl/w3/shoot_w3_crops.py
Needs a browser (playwright) and the repo's own site/ artifacts — hand-run, for the
reason recorded in ../IMPLEMENTATION_DELTAS.md: the CI packs install a minimal
dependency set, so a pytest wrapper here would SKIP in CI and report green while
proving nothing.
"""
import http.server
import json
import functools
import pathlib
import re
import socketserver
import sys
import threading
import time

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve()
# w3 / impl / crops / workspace / psi / refs / mockups / <worktree>
ROOT = HERE.parents[7]
assert (ROOT / "templates" / "watchlist.html.j2").exists(), ROOT
OUT = HERE.parent
SITE = ROOT / "site"
PORT = 8873
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

# The book: twelve real positions, and NO watchlist. That combination is not an
# arbitrary choice — it is the defect-3 case (a full portfolio with an empty
# watchlist), which is why every Risk Center crop doubles as evidence the factor
# read now reaches the page at all.
SEED_BOOK = "window.__W2.clear(); window.__W2.book();"

TABS = [
    ("01_conc", "conc"),
    ("02_corr", "corr"),
    ("03_fact", "fact"),
    ("04_strs", "strs"),
    ("05_evt", "evt"),
    ("06_weak", "weak"),
]


def link_nightly_artifacts() -> list:
    """Borrow `site/stockdata/` from the main checkout for the duration of the shoot.

    THE TRAP THIS EXISTS FOR. `site/stockdata/` is a nightly artifact directory — 1,630
    per-ticker JSONs, untracked, produced by the pipeline and never committed. A fresh
    agent worktree therefore has NONE of it, and the page degrades exactly as designed:
    no per-ticker JSON means no last close, which means `portfolio.js` can price no
    position, which means no dollar weights, which means the factor read never runs and
    every Risk Center tab renders its honest "not enough covered positions" fallback.

    Nothing is broken in that picture — which is precisely the danger. Crops shot in a
    bare worktree look like a working page with a thin book, so they would have shipped
    as evidence for reads that were never exercised. (This wave caught it: the first run
    produced six perfectly rendered EMPTY tabs.)

    The symlinks are removed in `main`'s finally block, because an untracked symlink left
    in the tree blocks the ship-loop guard.
    """
    import subprocess

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
            print("WARNING: %s not found in the main checkout — the crops will show the "
                  "thin-book fallback, which is NOT evidence for this wave." % src)
            continue
        dst.symlink_to(src)
        made.append(dst)
        print("linked", dst, "->", src, "(%d files)" % len(list(src.iterdir())))
    return made


def render_preview() -> None:
    """Render the template into site/ as a scratch preview (untracked, deleted after)."""
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
    # the page ships hand-authored ?v=N stamps, so a browser that already loaded v=N
    # keeps the stale body across renders — bust them per run. Preview-only.
    tok = str(int(time.time()))
    html = re.sub(r'(src|href)="([a-z_0-9.]+\.(?:js|css))(\?v=\d+)?"',
                  lambda m: '%s="%s?cb=%s"' % (m.group(1), m.group(2), tok), html)
    html = html.replace("<head>", '<head>\n<script src="__w3seed.js"></script>', 1)
    (SITE / "__w3preview.html").write_text(html)
    # the W2 seed helper, reused verbatim rather than forked
    (SITE / "__w3seed.js").write_text((OUT.parent / "preview_seed.js").read_text())
    print("rendered preview ->", SITE / "__w3preview.html")


def serve() -> socketserver.TCPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def prepare(page, size, theme, lang):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(BASE + "/__w3preview.html", wait_until="domcontentloaded")
    page.evaluate(SEED_BOOK)
    page.evaluate(
        "([t,l])=>{try{t?localStorage.setItem('theme',t):localStorage.removeItem('theme');"
        "l?localStorage.setItem('lang',l):localStorage.removeItem('lang');}catch(e){}}",
        [theme, lang],
    )
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2800)          # per-name hydration + the settled re-render
    page.evaluate(
        "document.querySelectorAll('#mm-brain-launcher,.mm-brain-launcher,#mmb-launcher')"
        ".forEach(function(n){n.style.display='none'})"
    )


def hide_launcher(page):
    """The chat launcher is a shared global widget, not this page's design — and it is
    position:fixed, so it lands inside an ELEMENT crop too. It re-mounts on re-render,
    so this runs before every shot rather than once per variant."""
    page.evaluate(
        "document.querySelectorAll('#mm-brain-launcher,.mm-brain-launcher,#mmb-launcher')"
        ".forEach(function(n){n.style.display='none'})"
    )


def select_tab(page, key):
    page.evaluate(
        "(k)=>{var b=document.querySelector('#rc_tabs .rc-tab[data-rc=\"'+k+'\"]');"
        "if(b)b.click();}", key)
    page.wait_for_timeout(320)


def hscroll(page):
    return page.evaluate(
        "()=>{var d=document.documentElement;return d.scrollWidth-d.clientWidth;}")


def main():
    linked = link_nightly_artifacts()
    render_preview()
    srv = serve()
    overflow = []
    errs = []
    thin = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ctx = b.new_context(device_scale_factor=2)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errs.append(str(e)))

            for vstem, size, theme, lang in VARIANTS:
                print(vstem)
                prepare(page, size, theme, lang)

                for stem, key in TABS:
                    select_tab(page, key)
                    if size == MOBILE:
                        over = hscroll(page)
                        if over > 0:
                            overflow.append((vstem, key, over))
                    # A crop of the "not enough covered positions" fallback is not
                    # evidence for a read — it is evidence the harness had no data.
                    # The first run of this script produced six of them (see
                    # link_nightly_artifacts), so the check is part of the gate.
                    if page.locator("#rc_body .rc-soon").count() > 0:
                        thin.append((vstem, key))
                    hide_launcher(page)
                    page.locator("#ws_sec_rc").screenshot(
                        path=str(OUT / f"{stem}_{vstem}.png"))
                    print("  ->", f"{stem}_{vstem}.png")

                # 07 — the Scenario Lab, open, with a real comparison run through it
                select_tab(page, "conc")
                page.evaluate("()=>{document.querySelector('details.lab').open=true;}")
                page.wait_for_timeout(200)
                page.fill("#rc_lab_t", "PLTR")
                page.click("#rc_lab_go")
                page.wait_for_timeout(420)
                if size == MOBILE:
                    over = hscroll(page)
                    if over > 0:
                        overflow.append((vstem, "lab", over))
                hide_launcher(page)
                page.locator("#ws_sec_rc").screenshot(
                    path=str(OUT / f"07_lab_{vstem}.png"))
                print("  ->", f"07_lab_{vstem}.png")

                # 08 — the defect-3 state, whole page: a full portfolio, empty watchlist
                page.evaluate("()=>{document.querySelector('details.lab').open=false;}")
                page.wait_for_timeout(150)
                hide_launcher(page)
                page.screenshot(path=str(OUT / f"08_empty_watchlist_portfolio_{vstem}.png"),
                                full_page=True)
                print("  ->", f"08_empty_watchlist_portfolio_{vstem}.png")
            b.close()
    finally:
        srv.shutdown()
        for f in ("__w3preview.html", "__w3seed.js"):
            p = SITE / f
            if p.exists():
                p.unlink()
        # an untracked symlink left behind blocks the ship-loop guard
        for p in linked:
            if p.is_symlink():
                p.unlink()

    ok = True
    if errs:
        print("PAGE ERRORS:", errs[:6])
        ok = False
    else:
        print("no page errors")
    if thin:
        print("TABS RENDERED THE THIN-BOOK FALLBACK (no data reached them):", thin)
        ok = False
    else:
        print("every tab rendered a real read in every variant")
    if overflow:
        print("PAGE-LEVEL HORIZONTAL SCROLL at 390px:", overflow)
        ok = False
    else:
        print("zero page-level horizontal scroll at 390px on every tab")
    sys.exit(0 if ok else 1)


main()
