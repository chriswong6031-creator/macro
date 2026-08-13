"""W2 workspace gate — browser-driven assertions over the real page.

WHEN THIS RUNS: BY HAND, not in CI — and that is deliberate, not a gap.

The CI packs install a minimal dependency set, not requirements.txt, so a
`pytest.importorskip("playwright")` here would SKIP in CI and report green while
proving nothing (house trap: ci-packs-install-minimal-deps-not-requirements). Following
the precedent set by mockups/refs/breathing-platform/verify_wl1.py, the measurements
that genuinely need a browser live here and are run by hand; everything mechanically
checkable without one is asserted against the rendered template and the shipped source
in tests/test_watchlist_workspace_js.py, which IS wired into the packs.

  # 1. render the preview pair (signed-in + the anonymous wall reproduction)
  python3 render_preview.py
  # 2. serve site/ on 127.0.0.1:8862, then:
  python3 verify_w2_workspace.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8862"
SIGNED = BASE + "/__w2preview.html"
ANON = BASE + "/__w2preview_anon.html"

# glance-tier vocabulary that must never reach a user-facing surface
BANNED = ["ENB", "MCTR", "WRI", "effective number of bets", "idio", "lane ",
          "validated", "falsifier", "证伪", "risk_core", "mctrShare"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(device_scale_factor=1)
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))

        # ---------- large-list law: 55 and 100 names ----------
        for n, seed_extra in ((55, ""), (100, "EXTRA")):
            for w, h, label in ((1440, 900, "desktop"), (390, 844, "390")):
                page.set_viewport_size({"width": w, "height": h})
                page.goto(SIGNED, wait_until="domcontentloaded")
                page.evaluate(
                    """(n)=>{window.__W2.clear();window.__W2.book();
                    var extra=['SPY','QQQ','IWM','DIA','XLK','XLF','XLE','XLV','XLI','XLY',
                    'XLP','XLU','XLB','XLRE','SMH','SOXX','ARKK','TSLA','NFLX','DIS','BA',
                    'CAT','DE','HON','GE','MMM','UPS','FDX','LMT','RTX','NOC','GD','V','MA',
                    'JPM','BAC','WFC','GS','MS','C','AXP','PYPL','SQ','COIN','HOOD'];
                    var all=window.__W2.WL55.concat(extra).slice(0,n);
                    window.__W2.list(all);window.__W2.seen(all);window.__W2.mode('watchlists');}""",
                    n,
                )
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(3000)
                got = page.evaluate(
                    "()=>document.querySelectorAll('#tbl_wl tbody tr:not(.row-drawer)').length"
                )
                check(f"{n} names @{label}: DOM rows == list count", got == n, f"{got}/{n}")
                overflow = page.evaluate(
                    "()=>document.documentElement.scrollWidth - document.documentElement.clientWidth"
                )
                check(f"{n} names @{label}: zero page horizontal scroll", overflow <= 0,
                      f"overflow={overflow}px")
                # a filter keystroke must narrow the table
                page.evaluate(
                    "()=>{var f=document.getElementById('wl_filter');f.value='NV';"
                    "f.dispatchEvent(new Event('input',{bubbles:true}));}"
                )
                page.wait_for_timeout(400)
                filt = page.evaluate(
                    "()=>document.querySelectorAll('#tbl_wl tbody tr:not(.row-drawer)').length"
                )
                check(f"{n} names @{label}: filter narrows the table", 0 < filt < n,
                      f"{filt} rows for 'NV'")
                scope = page.evaluate(
                    "()=>document.getElementById('wl_scope').textContent"
                )
                check(f"{n} names @{label}: filtered scope line discloses the reduction",
                      str(filt) in scope and str(n) in scope, scope.strip()[:60])
                if label == "390" and n == 100:
                    # progressive hydration must have reached the rows, not just the shell
                    hyd = page.evaluate(
                        "()=>document.querySelectorAll('#tbl_wl .stg').length"
                    )
                    check("100 names @390: per-name detail hydrated into rows", hyd > 0,
                          f"{hyd} stage cells")

        # ---------- the SEAM states, at both widths (round-2 item 5) ----------
        # The earlier claim's own evidence did not cover this path: the 100-name crop was
        # Watchlists mode, which draws no seam at all, so a seam that forced 86px of page
        # scroll at 390 sat behind a gate row that read green.
        NAMES = ("NVDA,AMD,AVGO,TSM,ASML,AMAT,LRCX,KLAC,MU,MRVL,ARM,SMCI,DELL,ANET,CIEN,"
                 "CRDO,ALAB,VRT,ETN,PWR,NVT,MOD,GEV,VST,CEG,NRG,TLN,OKLO,SMR,NNE,PLTR,"
                 "SNOW,MDB,DDOG,NET,CRWD,ORCL,MSFT,GOOGL,META,AMZN,CRM,NOW,IBM,QCOM,"
                 "INTC,TXN,ADI,ONTO,NVMI,AEIS,UCTT,ACLS,CLS,FN,SPY,QQQ,IWM,DIA,XLK,XLF,"
                 "XLE,XLV,XLI,XLY,XLP,XLU,XLB,XLRE,SMH,SOXX,ARKK,TSLA,NFLX,DIS,BA,CAT,"
                 "DE,HON,GE,MMM,UPS,FDX,LMT,RTX,NOC,GD,V,MA,JPM,BAC,WFC,GS,MS,C,AXP,"
                 "PYPL,SQ,COIN,HOOD").split(",")
        for n in (55, 100):
            for w, h, label in ((1440, 900, "desktop"), (390, 844, "390")):
                page.set_viewport_size({"width": w, "height": h})
                page.goto(ANON, wait_until="domcontentloaded")
                page.evaluate("(t)=>{window.__W2.clear(); window.__W2.entry(t,'equal');}",
                              ", ".join(NAMES[:n]))
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(1800)
                r = page.evaluate(
                    "()=>({segs: document.querySelectorAll('#ws_seam .seam-rail')[0].children.length,"
                    " tail: document.querySelectorAll('#ws_seam .is-tail').length,"
                    " rows: document.querySelectorAll('#tbl_pf tbody tr').length,"
                    " overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth})")
                check("seam @%d names @%s: zero page horizontal scroll" % (n, label),
                      r["overflow"] <= 0, "overflow=%spx segs=%s" % (r["overflow"], r["segs"]))
                check("seam @%d names @%s: segments capped, table NOT capped" % (n, label),
                      r["segs"] <= 24 and r["rows"] == n, json.dumps(r))
                check("seam @%d names @%s: the fold is disclosed" % (n, label),
                      r["tail"] == 1, "tail segments=%s" % r["tail"])

        # the SIGNED-IN book read draws the same seam from real positions
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(SIGNED, wait_until="domcontentloaded")
        page.evaluate("()=>{window.__W2.clear(); window.__W2.book();}")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(3000)
        r = page.evaluate(
            "()=>({segs: (document.querySelectorAll('#ws_seam .seam-rail')[0]||{children:[]}).children.length,"
            " overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth})")
        check("signed-in book read @390: zero page horizontal scroll", r["overflow"] <= 0,
              json.dumps(r))

        # ---------- one failed ticker degrades exactly one row ----------
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(SIGNED, wait_until="domcontentloaded")
        page.evaluate(
            "()=>{window.__W2.clear();window.__W2.book();"
            "window.__W2.list(['NVDA','MSFT','ZZZZNOTREAL','AAPL','GLD']);"
            "window.__W2.mode('watchlists');}"
        )
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2500)
        rows = page.evaluate(
            "()=>document.querySelectorAll('#tbl_wl tbody tr:not(.row-drawer)').length"
        )
        bad = page.evaluate(
            "()=>{var r=document.querySelector('#tbl_wl tr[data-t=\"ZZZZNOTREAL\"]');"
            "return r?r.textContent.replace(/\\s+/g,' ').trim():null}"
        )
        check("one unreadable ticker keeps its row", rows == 5 and bad is not None,
              f"{rows} rows; bad row={'present' if bad else 'MISSING'}")

        # ---------- book filter disclosure ----------
        page.goto(SIGNED, wait_until="domcontentloaded")
        page.evaluate(
            "()=>{window.__W2.clear();window.__W2.bookmix();window.__W2.book_filter('hk');}"
        )
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2500)
        scope = page.evaluate("()=>document.getElementById('pf_scope').textContent")
        shown = page.evaluate(
            "()=>document.querySelectorAll('#tbl_pf tbody tr:not(.row-drawer)').length"
        )
        chips = page.evaluate("()=>document.querySelectorAll('#bk_strip .bookchip').length")
        check("multi-market book renders the chip strip", chips >= 3, f"{chips} chips")
        check("persisted book filter is disclosed, never silent",
              "15" in scope and str(shown) in scope and 0 < shown < 15, scope.strip()[:80])

        # ---------- save-state chip: four states, truthful text ----------
        page.goto(SIGNED, wait_until="domcontentloaded")
        page.evaluate("()=>{window.__W2.clear();window.__W2.book();}")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        chips = page.evaluate(
            """()=>{var out={};['saved','saving','local','offline'].forEach(function(s){
              window.WS.setChip(s);var c=document.getElementById('ws_savechip');
              out[s]={cls:c.className,en:c.querySelector('.l-en').textContent,
                      zh:c.querySelector('.l-zh').textContent,
                      tip:!!c.getAttribute('data-tip-en')};});return out;}"""
        )
        ok = all(
            chips[s]["cls"].endswith("is-" + s) and chips[s]["en"] and chips[s]["zh"]
            and chips[s]["tip"] for s in ("saved", "saving", "local", "offline")
        )
        check("save chip: all four states reachable, bilingual, with a receipt", ok,
              json.dumps({k: v["en"] for k, v in chips.items()}))

        # ---------- the Account Sync panel is gone ----------
        gone = page.evaluate(
            "()=>['wl_auth','wl_syncpill','wl_signin','wl_signout','wl_account',"
            "'wl_authbox','wl_who'].every(function(i){return !document.getElementById(i)})"
        )
        check("Account Sync panel deleted; the header chip is the only sync disclosure", gone)

        # ---------- zero title= attributes (i18n law) ----------
        # Scoped to THIS page's own markup. #fx_panel (factor_exposure.js, hidden here
        # and owned by the W3 Factors tab) and the shared chat widget both emit their
        # own title= and are pre-existing, cross-page surfaces — reported, not silently
        # absorbed into this page's gate.
        titles = page.evaluate(
            "()=>[].slice.call(document.querySelectorAll('main.ws [title], header [title]'))"
            ".map(function(n){return n.tagName+':'+n.getAttribute('title')})"
        )
        check("zero title= attributes in the workspace markup", len(titles) == 0, str(titles[:3]))
        foreign = page.evaluate(
            "()=>[].slice.call(document.querySelectorAll('[title]')).filter(function(n){"
            "return !n.closest('main.ws')}).map(function(n){return n.tagName})"
        )
        print("      (note) title= outside the workspace, pre-existing: %d node(s)" % len(foreign))

        # ---------- copy law ----------
        text = page.evaluate("()=>document.body.innerText")
        hits = [w for w in BANNED if w.lower() in text.lower()]
        check("no banned glance-tier vocabulary in rendered copy", not hits, str(hits))

        # ---------- anonymous boundary ----------
        page.goto(ANON, wait_until="domcontentloaded")
        page.evaluate(
            "()=>{window.__W2.clear();"
            "window.__W2.entry('AAPL, MSFT, NVDA, AVGO, GOOGL, AMZN, GLD, TLT','equal');}"
        )
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)
        anon = page.evaluate(
            """()=>({SD:!!window.SD,RiskCore:!!window.RiskCore,WRI:!!window.WRI,FX:!!window.FX,
              state:document.documentElement.getAttribute('data-ws-state'),
              rows:document.querySelectorAll('#tbl_pf tbody tr').length,
              money:document.querySelectorAll('#ws_seam .seam-rail')[0]
                    ?document.querySelectorAll('#ws_seam .seam-rail')[0].children.length:0,
              lockedRisk:!!document.querySelector('#ws_seam .seam-rail.is-locked'),
              hatched:document.querySelectorAll('#ws_seam .seam-seg.is-uncovered').length,
              lockCells:document.querySelectorAll('#tbl_pf .lockcell').length,
              gate:!!document.querySelector('#ws_gate_signal .mx-tier-primary'),
              rcLock:!!document.querySelector('#rc_body .lockshell'),
              betsClaim:/move like about/.test(document.body.innerText)})"""
        )
        check("anonymous: the four gated scripts never execute",
              not (anon["SD"] or anon["RiskCore"] or anon["WRI"] or anon["FX"]), json.dumps(anon))
        check("anonymous: real structure renders (8 money segments)", anon["money"] == 8)
        check("anonymous: risk rail is a lock shell, money rail is NOT hatched",
              anon["lockedRisk"] and anon["hatched"] == 0)
        check("anonymous: every signal cell is a lock, not a stage read",
              anon["lockCells"] == 8)
        check("anonymous: free-account CTA present", anon["gate"])
        check("anonymous: Risk Center is a lock shell", anon["rcLock"])
        check("anonymous: the effective-bets claim is NOT made", not anon["betsClaim"])

        # local session persists a refresh
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        again = page.evaluate(
            "()=>({state:document.documentElement.getAttribute('data-ws-state'),"
            "rows:document.querySelectorAll('#tbl_pf tbody tr').length})"
        )
        check("anonymous: the analysis survives a refresh (local session)",
              again["state"] == "anon-analyzed" and again["rows"] == 8, json.dumps(again))

        b.close()
        if errs:
            check("no page errors across the gate run", False, str(errs[:4]))
        else:
            check("no page errors across the gate run", True)

    bad = [r for r in results if not r[1]]
    print("\n%d/%d gate assertions passed" % (len(results) - len(bad), len(results)))
    sys.exit(1 if bad else 0)


main()
