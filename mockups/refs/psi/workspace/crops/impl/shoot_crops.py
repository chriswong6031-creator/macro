"""W2 visual gate — browser-driven, full-page crops of the REAL page.

Every shot loads templates/watchlist.html.j2 as rendered by the real builder context,
runs the page's OWN scripts against the REAL nightly artifacts in site/ (stockdata
index + per-ticker JSON, factor_betas.json), and seeds only a BOOK in localStorage —
the same store a visitor's book lives in. No markup is staged and no figure is faked.

The anonymous shots load `__w2preview_anon.html`, which has the four account-gated
scripts REMOVED, reproducing the production wall exactly (config/site_access.yml keeps
stockdata.js / watchlist_risk.js / risk_core.js / factor_exposure.js off the public
plane, so their tags 401 and never execute).
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(
    "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/wp-w2-flagship-shell"
)
OUT = ROOT / "mockups/refs/psi/workspace/crops/impl"
BASE = "http://127.0.0.1:8862"
SIGNED = BASE + "/__w2preview.html"
ANON = BASE + "/__w2preview_anon.html"

DESKTOP = (1440, 900)
MOBILE = (390, 844)

# (stem, url, seed-js, variants)
VARIANTS = [
    ("desktop_dark_en", DESKTOP, None, None),
    ("desktop_light_en", DESKTOP, "light", None),
    ("desktop_dark_zh", DESKTOP, None, "zh"),
    ("390_dark_en", MOBILE, None, None),
    ("390_dark_zh", MOBILE, None, "zh"),
]

SEED_BOOK = "window.__W2.clear(); window.__W2.book();"
SEED_ENTRY = (
    "window.__W2.clear();"
    "window.__W2.entry('AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, GLD, TLT','equal');"
)
SEED_WL55 = (
    "window.__W2.clear(); window.__W2.book();"
    "window.__W2.list(window.__W2.WL55); window.__W2.seen(window.__W2.WL55);"
    "window.__W2.mode('watchlists');"
)
WL100 = (
    "var extra=['SPY','QQQ','IWM','DIA','XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLU',"
    "'XLB','XLRE','SMH','SOXX','ARKK','TSLA','NFLX','DIS','BA','CAT','DE','HON','GE',"
    "'MMM','UPS','FDX','LMT','RTX','NOC','GD','V','MA','JPM','BAC','WFC','GS','MS','C',"
    "'AXP','PYPL','SQ','COIN','HOOD'];"
)
SEED_WL100 = (
    "window.__W2.clear(); window.__W2.book();" + WL100 +
    "var all=window.__W2.WL55.concat(extra).slice(0,100);"
    "window.__W2.list(all); window.__W2.seen(all); window.__W2.mode('watchlists');"
)
SEED_BOOKFILTER = "window.__W2.clear(); window.__W2.bookmix(); window.__W2.book_filter('hk');"

# round 2: a shares-mode book, which must speak SHARE COUNTS in every derived figure
SEED_SHARES = (
    "window.__W2.clear();"
    "window.__W2.entry('BRK-A 1, F 5000, AAPL 100, MSFT 40, NVDA 250, GLD 60','shares');"
)
# round 2: a 100-name anonymous book, the state the seam cap exists for
SEED_SEAM100 = (
    "window.__W2.clear();"
    "window.__W2.entry('NVDA, AMD, AVGO, TSM, ASML, AMAT, LRCX, KLAC, MU, MRVL, ARM, SMCI, DELL, ANET, CIEN, CRDO, ALAB, VRT, ETN, PWR, NVT, MOD, GEV, VST, CEG, NRG, TLN, OKLO, SMR, NNE, PLTR, SNOW, MDB, DDOG, NET, CRWD, ORCL, MSFT, GOOGL, META, AMZN, CRM, NOW, IBM, QCOM, INTC, TXN, ADI, ONTO, NVMI, AEIS, UCTT, ACLS, CLS, FN, SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE, SMH, SOXX, ARKK, TSLA, NFLX, DIS, BA, CAT, DE, HON, GE, MMM, UPS, FDX, LMT, RTX, NOC, GD, V, MA, JPM, BAC, WFC, GS, MS, C, AXP, PYPL, SQ, COIN, HOOD','equal');"
)

SHOTS = [
    ("01_anon_empty", ANON, "window.__W2.clear();", None),
    ("02_anon_analyzed", ANON, SEED_ENTRY, None),
    ("03_portfolio", SIGNED, SEED_BOOK, None),
    ("04_watchlists_55", SIGNED, SEED_WL55, None),
    ("06_watchlists_100", SIGNED, SEED_WL100, None),
    ("07_book_filter", SIGNED, SEED_BOOKFILTER, None),
    ("08_anon_shares", ANON, SEED_SHARES, None),
    ("09_seam_cap_100", ANON, SEED_SEAM100, None),
]

CHIPS = ["saved", "saving", "local", "offline"]


def shoot(page, url, seed, out, size, theme, lang, after=None):
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(url, wait_until="domcontentloaded")
    page.evaluate(seed)
    page.evaluate(
        "([t,l])=>{try{t?localStorage.setItem('theme',t):localStorage.removeItem('theme');"
        "l?localStorage.setItem('lang',l):localStorage.removeItem('lang');}catch(e){}}",
        [theme, lang],
    )
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2600)          # per-name hydration + the settled re-render
    if after:
        page.evaluate(after)
        page.wait_for_timeout(400)
    # the chat launcher is a shared global widget, not this page's design
    page.evaluate(
        "document.querySelectorAll('#mm-brain-launcher,.mm-brain-launcher,#mmb-launcher')"
        ".forEach(function(n){n.style.display='none'})"
    )
    page.screenshot(path=str(out), full_page=True)
    print("  ->", out.name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(device_scale_factor=2)
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        LIMITED = {"08_anon_shares": {"desktop_dark_en", "desktop_dark_zh", "390_dark_en"},
                   "09_seam_cap_100": {"desktop_dark_en", "390_dark_en"}}
        for stem, url, seed, after in SHOTS:
            if only and only not in stem:
                continue
            print(stem)
            for vstem, size, theme, lang in VARIANTS:
                if stem in LIMITED and vstem not in LIMITED[stem]:
                    continue
                shoot(page, url, seed, OUT / f"{stem}_{vstem}.png", size,
                      theme, lang, after)
        # (e) the four save-state chip states, forced through the store's own seam
        if not only or "savechip" in (only or ""):
            print("05_savechip")
            for vstem, size, theme, lang in VARIANTS:
                after = (
                    "(function(){var h=document.querySelector('.ws-headright');"
                    "var wrap=document.createElement('div');"
                    "wrap.style.cssText='display:flex;flex-direction:column;gap:9px;align-items:flex-end';"
                    + "".join(
                        "window.WS.setChip('%s');"
                        "wrap.appendChild(document.getElementById('ws_savechip').cloneNode(true));"
                        % c for c in CHIPS
                    )
                    + "document.getElementById('ws_savechip').style.display='none';"
                    "h.appendChild(wrap);})()"
                )
                shoot(page, SIGNED, SEED_BOOK, OUT / f"05_savechip_{vstem}.png",
                      size, theme, lang, after)
        b.close()
        if errs:
            print("PAGE ERRORS:", errs[:6])
            sys.exit(1)
        print("no page errors")


main()
