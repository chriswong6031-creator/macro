#!/usr/bin/env python3
"""R4 closure harness — the proof handles named in the R4 closure ledger.

Deliberately a SEPARATE file from verify.py, and deliberately written against the
pinned class/markup contract rather than against the delivered implementation:
the author of a fix should not also author its only guard. If the build deviated
from the contract, these checks fail and surface the deviation — which is the
point. verify.py's 136 checks continue to assert the R3 properties did not regress.

Colour checks sample RENDERED PIXELS rather than getComputedStyle, because
getComputedStyle does not reliably resolve color-mix() on this path (it produced a
spurious rgb(0,1,0) for --pv-buy during the R3 cycle).

Usage: python3 tools/verify_r4.py [base_url]
Exit 0 = every check passed.
"""
import hashlib
import io
import json
import pathlib
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8792"
ART = pathlib.Path(__file__).resolve().parent.parent

fails, checks = [], []


def ok(name, cond, detail=""):
    checks.append((bool(cond), name, detail))
    if not cond:
        fails.append(f"{name} — {detail}")


def lum(rgb):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [f(x) for x in rgb[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    l1, l2 = lum(a), lum(b)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def px_of(pg, selector, dx=0.5, dy=0.5):
    """Sample the rendered pixel at a fractional offset inside an element."""
    from PIL import Image
    el = pg.query_selector(selector)
    if el is None:
        return None
    box = el.bounding_box()
    if not box or box["width"] < 1 or box["height"] < 1:
        return None
    shot = pg.screenshot(clip={"x": box["x"] + box["width"] * dx - 1,
                               "y": box["y"] + box["height"] * dy - 1,
                               "width": 2, "height": 2})
    im = Image.open(io.BytesIO(shot)).convert("RGB")
    return im.getpixel((1, 1))


def strip_css_comments(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def strip_js_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", s)


REPO = ART.parents[3]          # …/mockups/refs/institutionalize/us_stocks -> repo root


def _git(*args):
    """git, from the repo root, returning bytes or None. Never raises."""
    try:
        out = subprocess.run(("git",) + args, cwd=str(REPO), check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return out.stdout
    except Exception:
        return None


def read_from_head(relpath):
    """Read a repo file from DISK, falling back to HEAD.

    N1's whole defect was declaring a committed file non-existent because a
    sparse worktree had not checked out mockups/. A guard that asks the
    filesystem inherits that bug; git still holds the bytes, so ask git.
    """
    p = REPO / relpath
    if p.exists():
        return p.read_text()
    blob = _git("show", "HEAD:" + relpath)
    return blob.decode("utf-8", "replace") if blob else None


def crop_blobs(cropdir):
    """{filename: content-hash} for the crop set, from disk or from HEAD.

    Content identity, not filename identity: the point of the check is that two
    differently-named crops can be the SAME render, which is how a manifest ends
    up claiming coverage it does not have.
    """
    if cropdir.is_dir() and any(cropdir.glob("*.png")):
        return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                for f in sorted(cropdir.glob("*.png"))}
    rel = cropdir.relative_to(REPO).as_posix()
    listing = _git("ls-tree", "HEAD", rel + "/")
    if not listing:
        return {}
    out = {}
    for line in listing.decode().splitlines():
        meta, name = line.split("\t", 1)
        if not name.endswith(".png"):
            continue
        out[pathlib.PurePosixPath(name).name] = meta.split()[2]   # the blob sha
    return out


def main():
    css_raw = (ART / "board.css").read_text()
    js_raw = (ART / "board.js").read_text()
    # Source checks run over CODE, never over prose. A comment recording that a
    # block was deleted must not read as the block still being present — that
    # would punish the documentation this cycle explicitly asks for.
    css = strip_css_comments(css_raw)
    js = strip_js_comments(js_raw)
    notes = (ART / "DESIGN_NOTES.md").read_text()
    cmp_html = (ART / "compare.html").read_text()
    fixture = (ART / "board-data.js").read_text()

    with sync_playwright() as p:
        br = p.chromium.launch()

        def page_at(q, w=1440, h=900):
            pg = br.new_page(viewport={"width": w, "height": h})
            pg.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            pg.wait_for_timeout(150)
            return pg

        # ══ PRC-301 — card routes to the name's detail surface ═════════════
        pg = page_at("theme=dark&lang=en&state=paid")
        nav = pg.evaluate("""() => {
          const cards=[...document.querySelectorAll('.pvcard')];
          const withLink=cards.filter(c=>c.querySelector('a.pv-open[href^="stock.html#"]'));
          const hrefs=withLink.map(c=>c.querySelector('a.pv-open').getAttribute('href'));
          const tks=withLink.map(c=>c.dataset.ticker);
          const matched=hrefs.filter((h,i)=>h==='stock.html#'+tks[i]).length;
          // illegal nesting: an interactive element INSIDE the anchor
          const nested=cards.filter(c=>{
            const a=c.querySelector('a.pv-open'); if(!a) return false;
            return !!a.querySelector('a,button,[tabindex],[role="button"]');
          }).length;
          // anchor must carry a non-empty accessible name
          const unnamed=withLink.filter(c=>{
            const a=c.querySelector('a.pv-open');
            return !((a.getAttribute('aria-label')||a.textContent||'').trim());
          }).length;
          // controls must remain reachable (not buried under the stretched hit area)
          const ctrlSel='.pv-cau,.pv-trg,.pv-pri,.pv-chip--noread,.pv-mk-lane';
          const ctrls=[...document.querySelectorAll('.pvcard '+ctrlSel)];
          const buried=ctrls.filter(e=>{
            const cs=getComputedStyle(e);
            return cs.position==='static' || cs.zIndex==='auto';
          }).length;
          return {cards:cards.length, linked:withLink.length, matched, nested, unnamed,
                  ctrls:ctrls.length, buried};
        }""")
        ok("R1 card-link — every rendered card routes to stock.html#TICKER",
           nav["cards"] > 0 and nav["linked"] == nav["cards"] and nav["matched"] == nav["cards"],
           f"{nav['linked']}/{nav['cards']} linked, {nav['matched']} href==ticker")
        ok("R1b card-link-a11y — the route anchor carries an accessible name",
           nav["linked"] > 0 and nav["unnamed"] == 0, f"{nav['unnamed']} unnamed")
        ok("R1c card-link-no-nesting — no interactive element inside the anchor",
           nav["nested"] == 0, f"{nav['nested']} cards nest interactive content in a.pv-open")
        ok("R1d card-controls-reachable — internal controls sit above the stretched hit area",
           nav["ctrls"] > 0 and nav["buried"] == 0, f"{nav['buried']}/{nav['ctrls']} buried")
        pg.close()

        # ══ PRC-302 / VTC-306 — anonymous gate tells the truth ═════════════
        for lang in ("en", "zh"):
            pg = page_at(f"theme=dark&lang={lang}&state=anon")
            g = pg.evaluate("""() => {
              const gate=document.querySelector('.mx-tier-gate');
              const card=document.querySelector('.pvcard');
              return {copy: gate ? gate.innerText : '',
                      specimen: card ? card.innerText : '', has: !!gate};
            }""")
            ok(f"R2[{lang}] anon-gate-truth — no entry/target/void promise on the card tier",
               g["has"] and not re.search(
                   r"entry, target and void|入场价、目标价与失效价|entry,\s*target", g["copy"], re.I),
               g["copy"][:120])
            ok(f"R2b[{lang}] anon-specimen-reconciled — the shop-window card is not a no-read husk",
               g["specimen"] and not re.search(r"No read yet|暂无判断", g["specimen"]),
               g["specimen"][:80].replace("\n", " "))
            pg.close()

        # ══ PRC-305 — freshness: fresh AND behind, both languages ══════════
        pg = page_at("theme=dark&lang=en&state=paid")
        fresh = pg.evaluate("""() => {
          const el=document.querySelector('.pv-fresh');
          return {has:!!el, behind: !!document.querySelector('.pv-fresh--behind'),
                  text: el?el.innerText:''};
        }""")
        ok("R3 freshness-fresh — the fresh state renders a freshness slot, not a behind banner",
           fresh["has"] and not fresh["behind"], f"has={fresh['has']} behind={fresh['behind']}")
        pg.close()

        # Production discloses staleness in TWO parts and the build mirrors that:
        # a header pill (.stk-status.is-delayed -> .pv-fresh--behind, "Delayed"/"延迟")
        # and the amber sentence banner (.nb-stale-note). Assert the SYSTEM, not one
        # node — an earlier version of this check looked only at the pill and called
        # a correct two-part implementation a missing disclosure.
        for lang, needles in (("en", [r"session", r"behind", r"live quote"]),
                              ("zh", [r"个交易日", r"落后", r"实时报价"])):
            pg = page_at(f"theme=dark&lang={lang}&state=stale")
            st = pg.evaluate("""() => {
              const q=s=>{const e=document.querySelector(s);return e?e.innerText:''};
              return {pill:!!document.querySelector('.pv-fresh--behind'),
                      pillText:q('.pv-fresh--behind'),
                      note:!!document.querySelector('.nb-stale-note'),
                      noteText:q('.nb-stale-note')};
            }""")
            missing = [n for n in needles if not re.search(n, st["noteText"], re.I)]
            ok(f"R3b[{lang}] freshness-behind — discloses vintage, sessions behind, verify-live-price",
               st["pill"] and st["note"] and not missing,
               f"pill={st['pill']} note={st['note']} missing={missing} "
               f"text={st['noteText'][:90]}")
            ok(f"R3c[{lang}] freshness-behind prints a sessions-behind NUMBER and a vintage date",
               bool(re.search(r"\d", st["noteText"]))
               and bool(re.search(r"\d{4}-\d{2}-\d{2}", st["noteText"])),
               st["noteText"][:80])
            pg.close()

        # ══ PRC-306 — full-book reachability by progressive expansion ══════
        # The grid renders EVERY row and hides the overflow, so counting .pvcard
        # nodes would count hidden cards and make this pass vacuously. Count only
        # cards that are actually laid out.
        VIS = ("[...document.querySelectorAll('.pvcard')]"
               ".filter(c => c.offsetParent !== null).length")
        pg = page_at("theme=dark&lang=en&state=paid")
        exp = pg.evaluate("""() => {
          const bar=document.querySelector('.sm-bar');
          const vis=[...document.querySelectorAll('.pvcard')].filter(c=>c.offsetParent!==null).length;
          return {has:!!bar, visible:vis, inDom:document.querySelectorAll('.pvcard').length,
                  more: !!document.querySelector('.sm-bar .sm-btn[data-sm="more"]'),
                  all: !!document.querySelector('.sm-bar .sm-btn.sm-ghost'),
                  live: window.BOARD.live_total};
        }""")
        ok("R4 expand-more — a progressive expansion bar exists with a Show-more control",
           exp["has"] and exp["more"], f"bar={exp['has']} more={exp['more']}")
        ok("R4a expand-initial-cap — the initial VISIBLE viewport is still the 40-card budget",
           exp["visible"] <= 41, f"{exp['visible']} visible of {exp['inDom']} in DOM")
        if exp["all"]:
            pg.click(".sm-bar .sm-btn.sm-ghost")
            pg.wait_for_timeout(400)
            after = pg.evaluate(f"() => {VIS}")
            ok("R4b expand-all — Show-all reveals every row of the live partition as a VISIBLE card",
               after >= exp["live"], f"{after} visible after expand vs live_total {exp['live']}")
        else:
            ok("R4b expand-all — Show-all reveals every row of the live partition as a VISIBLE card",
               False, "no .sm-btn.sm-ghost control found")
        pg.close()

        # every lifecycle partition must be fully card-reachable
        unreachable = []
        for cell in ("ready", "entered", "invalidated", "resolved"):
            pg = page_at(f"theme=dark&lang=en&state=paid&life={cell}")
            gh = pg.query_selector(".sm-bar .sm-btn.sm-ghost")
            if gh:
                gh.click()
                pg.wait_for_timeout(350)
            r = pg.evaluate("""(c) => ({
                shown: [...document.querySelectorAll('.pvcard')].filter(e=>e.offsetParent!==null).length,
                want: window.BOARD.counts[c]||0})""", cell)
            if r["shown"] < r["want"]:
                unreachable.append(f"{cell} {r['shown']}/{r['want']}")
            pg.close()
        ok("R4c full-book-card-reachable — every lifecycle partition expands to its full count",
           not unreachable, str(unreachable))

        # ══ VTC-301 / PRC-309 — mixed-grid geometry + printed null ═════════
        pg = page_at("theme=dark&lang=en&state=paid")
        # Only VISIBLE cards: the grid renders the whole partition and hides the
        # overflow, and a display:none card reports a zero-height box that would
        # corrupt both the max and the spread.
        geo = pg.evaluate("""() => {
          const vis = e => e.offsetParent !== null;
          const cards=[...document.querySelectorAll('.pvcard')].filter(vis);
          const ch=cards.flatMap(c=>[...c.querySelectorAll('.pv-chart svg')])
                        .map(e=>e.getBoundingClientRect().height);
          const ncEls=cards.flatMap(c=>[...c.querySelectorAll('.pv-nochart')]);
          const nc=ncEls.map(e=>e.getBoundingClientRect().height);
          const lab=ncEls.filter(e=>e.querySelector('.pv-nochart-l')).length;
          // compare like with like: full-form cards only, since the compact form
          // is DELIBERATELY shorter (VTC-308) and would read as a false spread
          const heights=cards.filter(c=>!c.classList.contains('pvcard--compact'))
                             .map(c=>c.getBoundingClientRect().height);
          return {chart: ch.length?Math.round(Math.max(...ch)):0,
                  nochart: nc.length?Math.round(Math.max(...nc)):0,
                  nNoChart: ncEls.length, labelled: lab,
                  spread: heights.length?Math.round(Math.max(...heights)-Math.min(...heights)):0};
        }""")
        ok("R5 nochart-geometry — the chartless hero matches the chart height at desktop",
           geo["nNoChart"] > 0 and abs(geo["chart"] - geo["nochart"]) <= 2,
           f"chart {geo['chart']}px vs nochart {geo['nochart']}px")
        ok("R5b nochart-intentional-null — the absent chart is PRINTED, not an empty stretch",
           geo["nNoChart"] > 0 and geo["labelled"] == geo["nNoChart"],
           f"{geo['labelled']}/{geo['nNoChart']} carry .pv-nochart-l")
        ok("R5c grid-no-stretched-void — card heights in the canonical grid are near-uniform",
           geo["spread"] <= 24, f"height spread {geo['spread']}px")
        pg.close()

        # ══ VTC-302 / DA-002 / VTC-304 / VTC-311 — stance ramp, 4 quadrants ═
        for theme, lang in (("dark", "en"), ("dark", "zh"), ("light", "en"), ("light", "zh")):
            pg = page_at(f"theme={theme}&lang={lang}&state=paid")
            probe = pg.evaluate("""() => {
              const g=(n)=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
              const d=document.createElement('div');
              d.style.cssText='position:fixed;left:0;top:0;width:40px;height:40px;z-index:99999';
              d.id='__probe'; document.body.appendChild(d);
              return {surface:g('--panel2')};
            }""")

            def sample(varname):
                pg.evaluate("""(v) => { document.getElementById('__probe').style.background =
                    'var('+v+')'; }""", varname)
                pg.wait_for_timeout(30)
                return px_of(pg, "#__probe")

            buy, wait, nor = sample("--pv-buy"), sample("--pv-wait"), sample("--pv-noread")
            pg.evaluate("""() => { const c=document.querySelector('.pvcard'); const cs=c?getComputedStyle(c):null;
                document.getElementById('__probe').style.background = cs?cs.backgroundColor:'#000'; }""")
            pg.wait_for_timeout(30)
            surf = px_of(pg, "#__probe")
            if buy and wait and nor and surf:
                cb, cw, cn = contrast(buy, surf), contrast(wait, surf), contrast(nor, surf)
                ok(f"R7[{theme}+{lang}] stance-ramp-order — BUY > WAIT > NO-READ",
                   cb > cw > cn, f"BUY {cb:.2f} WAIT {cw:.2f} NO-READ {cn:.2f}")
                ok(f"R7b[{theme}+{lang}] stance-ramp clears the WCAG 3:1 graphical floor",
                   min(cb, cw, cn) >= 3.0, f"min {min(cb,cw,cn):.2f}")
            else:
                ok(f"R7[{theme}+{lang}] stance-ramp-order — BUY > WAIT > NO-READ", False,
                   "could not sample ramp tokens")

            # DA-002: the stance chip must not be byte-identical to the tape ink
            pg.evaluate("""() => { document.getElementById('__probe').style.background='var(--pv-buy)'; }""")
            pg.wait_for_timeout(30)
            chip = px_of(pg, "#__probe")
            pg.evaluate("""() => { document.getElementById('__probe').style.background='var(--ink-up)'; }""")
            pg.wait_for_timeout(30)
            tape = px_of(pg, "#__probe")
            ok(f"R9[{theme}+{lang}] stance-chip-not-direction-ink — --pv-buy != --ink-up",
               chip and tape and chip != tape, f"chip {chip} tape {tape}")
            pg.close()

        # VTC-311 — light+zh authored explicitly, not inherited by cascade order
        ok("R32 light-zh-explicit — the light+zh stance quadrant is authored, not a cascade accident",
           re.search(r'html\[data-theme="light"\]\[data-lang="zh"\][^{]*\{[^}]*--pv-', css, re.S)
           is not None,
           "no explicit light+zh stance block in board.css")

        # ══ VTC-303 / VTC-304 — featured rail + amber disambiguation ═══════
        ok("R17 featured-rail-cohort — the Featured rail is pinned to --pv-buy, not --pvh",
           re.search(r"\.pvcard\.pv-featured::before\s*\{[^}]*--pv-buy", css, re.S) is not None
           and not re.search(r"\.pvcard\.pv-featured::before\s*\{[^}]*linear-gradient\(90deg,\s*var\(--pvh\)",
                             css, re.S),
           "rail still draws from --pvh")
        ok("R18 trigger-verb-hue — .pv-trg takes the verb/stance hue, not --warn",
           re.search(r"\.pv-trg\s*\{[^}]*--pvh", css, re.S) is not None
           and not re.search(r"\.pv-trg\s*\{[^}]*color:\s*var\(--ink-warn\)", css, re.S),
           "Triggered still pinned to the caution amber")
        ok("R18b wait-not-caution-ink — --pv-wait is decoupled from --warn",
           not re.search(r"--pv-wait:\s*var\(--warn\)", css)
           and re.search(r"--pv-wait:\s*#", css) is not None,
           "--pv-wait still equals --warn")
        ok("R29 lifecycle-mark-distinct — entered and delivering do not render from one rule",
           not re.search(r"\.mx-mark--entered::before\s*,\s*\.mx-mark--delivering::before", css),
           "the two marks still share a single rule")
        ok("R31 no-dead-actcol-css — the dead .actcol/actiongrid RULES are gone",
           re.search(r"\.(actcol|actiongrid|acth|act-buy)\b[^{;]*\{", css) is None,
           "a dead action-grid rule is still declared")

        # ══ PRC-311 / PRC-310 / VTC-312 — board-level facts stay board-level ═
        pg = page_at("theme=dark&lang=en&state=paid")
        unf = pg.query_selector(".chg-strip") is not None
        pg.close()
        pg = page_at("theme=dark&lang=en&state=paid&life=ready")
        filt = pg.query_selector(".chg-strip") is not None
        pg.close()
        ok("R13 chgstrip-unfiltered-only — 'what changed today' shows unfiltered and hides under a filter",
           unf and not filt, f"unfiltered={unf} filtered={filt}")

        pg = page_at("theme=dark&lang=en&state=paid&life=ready")
        claim = pg.evaluate("""() => {
          const s=document.querySelector('.ladder-sub');
          return {sub: s?s.innerText:'', cells: document.querySelectorAll('.mx-cell').length};
        }""")
        ok("R12 headline-claim-scope — the six-cells-add-up claim only appears where the cells are",
           claim["cells"] >= 6 or not re.search(r"add up|合计", claim["sub"]),
           f"cells={claim['cells']} sub={claim['sub'][:60]}")
        pg.close()

        # ══ PRC-312 — entry stance vs lifecycle ════════════════════════════
        pg = page_at("theme=dark&lang=en&state=paid&life=entered")
        ax = pg.evaluate("""() => {
          const cards=[...document.querySelectorAll('.pvcard')];
          const wait=cards.filter(c=>c.classList.contains('pv-wait'));
          return {entered:cards.length, wait:wait.length,
                  axis: wait.filter(c=>c.querySelector('.pv-axis')).length};
        }""")
        ok("R14 stance-axis-explicit — an entered card carrying WAIT names the entry axis",
           ax["wait"] == 0 or ax["axis"] == ax["wait"],
           f"{ax['axis']}/{ax['wait']} entered+wait cards carry .pv-axis")
        # Scoped to the LEX.ready entry rather than the whole file: "尚未触发" is
        # legitimate copy elsewhere (the ⚡ imminent tooltip says the trigger has
        # not fired, which is true there). Only Ready's own gloss is the defect.
        ready_gloss = re.search(r"ready:\s*\{.*?\}", js, re.S)
        ok("R14b ready-gloss-no-trigger-contradiction — Ready's gloss states the lifecycle fact",
           ready_gloss is not None
           and not re.search(r"trigger not fired|尚未触发", ready_gloss.group(0)),
           (ready_gloss.group(0)[:110] if ready_gloss else "LEX.ready not found"))
        pg.close()

        # ══ PRC-313 / auth.table_levels — the table carries decision fields ═
        pg = page_at("theme=dark&lang=en&state=paid&view=table")
        tb = pg.evaluate("""() => {
          const th=[...document.querySelectorAll('.st-table thead th')].map(t=>t.innerText.trim());
          return {th, rows: document.querySelectorAll('.st-table tbody tr').length};
        }""")
        # Compare COLUMNS, not substrings. The stance column ships as "Entry read"
        # (PRC-312 names the axis), which contains the substring "entry" — a naive
        # `"entry" not in head` test therefore reads a correctly-named DECISION
        # field as a surviving EXECUTION level, and the obvious way to "fix" that
        # is to rename the column back to something less honest.
        cols = [c.strip().lower() for c in tb["th"]]
        has_stance = any(c in ("stance", "entry read", "entry stance") for c in cols)
        exec_cols = [c for c in cols
                     if c in ("entry", "void", "invalidation", "first target", "t1", "target")]
        ok("R15 table-decision-fields — the table carries the stance axis, Priority and Zone",
           has_stance and any("priority" in c for c in cols) and any("zone" in c for c in cols),
           " | ".join(cols))
        ok("R15b table-no-execution-levels — Entry / T1 / Void are gone from the Board table",
           not exec_cols, f"execution columns still present: {exec_cols} in {' | '.join(cols)}")
        pg.close()

        # ══ PRC-314 — Resolved wins precedence ════════════════════════════
        pg = page_at("theme=dark&lang=en&state=paid&life=resolved")
        rs = pg.evaluate("""() => {
          const cards=[...document.querySelectorAll('.pvcard')];
          return {n:cards.length,
                  activeZone: cards.filter(c=>c.querySelector('.pv-znr')).length,
                  livePri:    cards.filter(c=>c.querySelector('.pv-prin:not(.pv-prin--na)')).length,
                  liveChg:    cards.filter(c=>c.querySelector('.pv-chg.up,.pv-chg.down')).length,
                  compact:    cards.filter(c=>c.classList.contains('pvcard--compact')).length};
        }""")
        ok("R16 resolved-precedence — no resolved card renders an active zone, live change or live Priority",
           rs["n"] > 0 and rs["activeZone"] == 0 and rs["liveChg"] == 0 and rs["livePri"] == 0,
           f"n={rs['n']} zone={rs['activeZone']} chg={rs['liveChg']} pri={rs['livePri']}")
        ok("R20 sparse-compact-form — resolved rows use the compact form, not full-card husks",
           rs["n"] > 0 and rs["compact"] == rs["n"], f"{rs['compact']}/{rs['n']} compact")
        pg.close()

        # ══ PRC-303 — no-read / zone / caution coherence ══════════════════
        pg = page_at("theme=dark&lang=en&state=paid")
        coh = pg.evaluate("""() => {
          const bad=[]; let trg=0;
          document.querySelectorAll('.pvcard.pv-noread').forEach(c=>{
            const zn=(c.querySelector('.pv-zn')||{}).innerText||'';
            const noZone=/No zone|无买区/.test(zn);
            const cau=(c.querySelector('.pv-cau-pop')||{}).innerText||'';
            if(noZone && /buy zone|买区/i.test(cau)) bad.push(c.dataset.ticker);
            if(c.querySelector('.pv-trg')) trg++;
          });
          return {bad, trg};
        }""")
        ok("R6 noread-caution-coherence — no card cites a buy zone it says does not exist",
           not coh["bad"], str(coh["bad"][:6]))
        ok("R6b noread-keeps-trigger — a sourced trigger survives on a no-read card",
           coh["trg"] > 0, "no no-read card retains its ⚡ trigger — the event was suppressed")
        pg.close()

        # ══ PRC-307 / VTC-307 — evidence, not furniture ═══════════════════
        pg = page_at("theme=dark&lang=en&state=paid")
        ev = pg.evaluate("""() => {
          const ev=document.querySelector('#evidence');
          const ctx=document.querySelector('#context');
          const txt=ev?ev.innerText:'';
          return {txt, hasNum: /\\d/.test(txt),
                  ctxEmpty: !!ctx && !/\\d/.test(ctx.innerText||'')};
        }""")
        ok("R11 track-record-numbers — the evidence section carries real quantities",
           ev["hasNum"] and re.search(r"\d+(\.\d+)?\s*%", ev["txt"]) is not None,
           ev["txt"][:120].replace("\n", " "))
        ok("R19 no-empty-section-shell — no section header survives over deleted content",
           not ev["ctxEmpty"], "#context renders a header with no bound content")
        pg.close()

        # ══ hygiene ═══════════════════════════════════════════════════════
        pg = page_at("theme=dark&lang=zh&state=paid")
        hy = pg.evaluate("""() => {
          const g=document.querySelector('#groups');
          const gt=g?g.innerText:'';
          const setups=new Set([...document.querySelectorAll('.pvcard')].map(c=>c.dataset.ticker));
          const cands=[...document.querySelectorAll('.cand-tk')].map(e=>e.textContent.trim());
          return {slugLeak: /\\b(enter|accumulate|trim|avoid|watch|hold)\\b/.test(gt),
                  rank: !!(g && g.querySelector('.grp-rank')),
                  dupes: cands.filter(t=>setups.has(t)).length, nCand: cands.length};
        }""")
        ok("R23 groups-slug-mapped — no raw payload slug leaks into ZH copy",
           not hy["slugLeak"], "a raw English reco slug is rendering inside Chinese copy")
        ok("R24 groups-rank-denominator — rank is hidden while its denominator is unknown",
           not hy["rank"], "Groups prints an ordinal rank from an undisclosed population")
        ok("R30 candidates-sample-distinct — the sample does not merely restate visible Setups",
           hy["nCand"] == 0 or hy["dupes"] < hy["nCand"],
           f"{hy['dupes']}/{hy['nCand']} candidate rows duplicate a rendered Setup")
        pg.close()

        pg = page_at("theme=dark&lang=en&state=paid")
        zw = pg.evaluate("""() => {
          const bad=[];
          document.querySelectorAll('.pvcard').forEach(c=>{
            const t=(c.querySelector('.pv-znr,.pv-znm')||{}).textContent||'';
            const m=t.match(/\\$([\\d.]+)\\s*[–-]\\s*\\$([\\d.]+)/);
            if(m && m[1]===m[2]) bad.push(c.dataset.ticker);
          });
          return bad;
        }""")
        ok("R25 zero-width-zone — a zero-width zone prints as one price, not an equal-endpoint range",
           not zw, str(zw[:6]))
        mock = pg.evaluate("""() => ({marked: document.querySelectorAll('[data-mock-live]').length,
                                      disclosed: /simulat|demo|模拟|示意/i.test(document.body.innerText)})""")
        ok("R21 mock-live-disclosed — simulated change values are disclosed on the surface",
           mock["marked"] == 0 or mock["disclosed"],
           f"{mock['marked']} mock values, disclosed={mock['disclosed']}")
        pg.close()

        # 390px — Resolved stays outside the live partition
        pg = page_at("theme=dark&lang=en&state=paid", 390, 844)
        sep = pg.evaluate("""() => {
          const gap=document.querySelector('.mx-ladder-gap');
          const term=document.querySelector('.mx-cell--term');
          if(!gap||!term) return {ok:false, why:'missing gap or terminal cell'};
          const g=gap.getBoundingClientRect(), t=term.getBoundingClientRect();
          return {ok: t.top >= g.top - 1, why:`gap.top=${Math.round(g.top)} term.top=${Math.round(t.top)}`};
        }""")
        ok("R28 mobile-resolved-separation — Resolved sits outside the live partition at 390w",
           sep["ok"], sep.get("why", ""))
        pg.close()

        # ══ R4.2 / V-N2 — MEASUREMENTS the prose-vs-artifact class asserts on ══
        # Each of these lands in FACTS below and is joined against a sentence
        # some law-bearing document states in its own voice. Measured here so a
        # claim is checked against the ARTIFACT, never against another sentence.
        pg = page_at("theme=dark&lang=en&state=paid")
        caps = pg.evaluate("""() => {
          const all=[...document.querySelectorAll('.mx-cap')];
          return {total: all.length,
                  inLadder: all.filter(e=>e.closest('.mx-cell')).length,
                  onCard: all.filter(e=>e.closest('.pvcard')).length};
        }""")
        ok("R29a cap-is-ladder-only — .mx-cap is emitted on ladder cells and nowhere else",
           caps["total"] > 0 and caps["onCard"] == 0 and caps["inLadder"] == caps["total"],
           f"{caps['onCard']} caps on cards, {caps['inLadder']}/{caps['total']} in ladder cells")
        # VTC-305 separated Delivering from Entered; §3 used to call them identical.
        deliv = pg.evaluate("""() => {
          const st=[...document.styleSheets].flatMap(s=>{try{return [...s.cssRules]}catch(e){return []}});
          const txt=st.map(r=>r.cssText||'').join('\\n');
          const ent=(txt.match(/\\.mx-cap--entered[^{]*\\{[^}]*\\}/g)||[]).join('');
          const del=(txt.match(/\\.mx-cap--delivering[^{]*\\{[^}]*\\}/g)||[]).join('');
          return {entRules:(txt.match(/\\.mx-cap--entered/g)||[]).length,
                  delRules:(txt.match(/\\.mx-cap--delivering/g)||[]).length,
                  identical: ent.replace(/entered/g,'X')===del.replace(/delivering/g,'X')};
        }""")
        DELIVERING_IDENTICAL = bool(deliv["identical"])
        ok("R29b delivering-measured — the Entered/Delivering weight rules are compared, not assumed",
           deliv["entRules"] > 0 and deliv["delRules"] > 0,
           f"entered rules={deliv['entRules']} delivering rules={deliv['delRules']}")
        # the ZH sector twin (V-B3): no card may print an un-twinned sector line
        pgz = page_at("theme=dark&lang=zh&state=paid")
        sec = pgz.evaluate("""() => {
          const inds=[...document.querySelectorAll('.pvcard .pv-ind')];
          return {n: inds.length,
                  twinned: inds.filter(e=>e.querySelector('.l-en')&&e.querySelector('.l-zh')).length,
                  latinVisible: inds.filter(e=>{
                    const zh=e.querySelector('.l-zh');
                    return zh && /[A-Za-z]/.test(zh.textContent) && !zh.classList.contains('pv-ind--raw');
                  }).length};
        }""")
        ok("R31 sector-zh-twin — every rendered sector line carries its zh twin",
           sec["n"] > 0 and sec["twinned"] == sec["n"] and sec["latinVisible"] == 0,
           f"{sec['twinned']}/{sec['n']} twinned, {sec['latinVisible']} untwinned latin in zh")
        pgz.close()
        pg.close()

        # ── V-B4: the two states the specimen ships ─────────────────────────
        pg = page_at("theme=dark&lang=en&state=loading")
        load = pg.evaluate("""() => ({
          skel: document.querySelectorAll('.pv-skcard').length,
          chartH: (document.querySelector('.sk-chart')||{}).clientHeight,
          words: [...document.querySelectorAll('.mx-cell-l')].length,
          counts: document.querySelectorAll('.mx-cell .mx-cell-n').length,
          skelCounts: document.querySelectorAll('.mx-cell .sk-n').length,
          dashes: (document.querySelector('.mx-ladder')||{textContent:''}).textContent.indexOf('\\u2014'),
          busy: document.querySelectorAll('[aria-busy="true"]').length
        })""")
        ok("R32 loading-state — skeleton cards at the shipped 74px hero geometry, ladder words kept",
           load["skel"] >= 6 and load["chartH"] == 74 and load["words"] == 7
           and load["skelCounts"] == 7 and load["counts"] == 0 and load["busy"] >= 1,
           f"skel={load['skel']} chartH={load['chartH']} words={load['words']} "
           f"skelCounts={load['skelCounts']} liveCounts={load['counts']} busy={load['busy']}")
        ok("R32b loading-dash-free — the em dash keeps its single meaning (key-absent), never 'loading'",
           load["dashes"] == -1, "an em dash appears in the loading ladder")
        pg.close()
        for lang, retry in (("en", "Retry"), ("zh", "重试")):
            pg = page_at("theme=dark&lang=" + lang + "&state=error")
            err = pg.evaluate("""() => {
              const e=document.querySelector('.mx-error');
              const b=document.querySelector('.mx-error-retry');
              const r=b?b.getBoundingClientRect():null;
              return {present:!!e, role:e?e.getAttribute('role'):'',
                      text:e?e.innerText:'', btnH:r?Math.round(r.height):0,
                      ladder: document.querySelectorAll('.mx-cell').length,
                      setups: document.querySelectorAll('#setups').length,
                      below: document.querySelectorAll('#candidates,#groups,#evidence').length};
            }""")
            ok(f"R33-{lang} error-state — names the failure, keeps the rest, offers a >=40px Retry",
               err["present"] and err["role"] == "alert" and retry in err["text"]
               and err["btnH"] >= 40 and err["ladder"] == 0 and err["setups"] == 0
               and err["below"] == 3,
               f"present={err['present']} btn={err['btnH']}px ladder={err['ladder']} "
               f"setups={err['setups']} below={err['below']}")
            pg.close()

        # ── P-K19: the watch key present-and-empty ──────────────────────────
        pg = page_at("theme=dark&lang=en&state=paid&watch=present")
        wp = pg.evaluate("""() => {
          const cells=[...document.querySelectorAll('.mx-ladder .mx-cell')];
          const live=cells.slice(0,6);
          const n=e=>{const v=(e.querySelector('.mx-cell-n')||{}).textContent||'';return v.trim();};
          return {watch:n(live[0]),
                  sum: live.reduce((a,e)=>a+(parseInt(n(e),10)||0),0),
                  head: parseInt((document.querySelector('.ladder-n')||{}).textContent,10),
                  sub: (document.querySelector('.ladder-sub .l-en')||{}).textContent||'',
                  absence: document.querySelectorAll('.ladder-absence').length,
                  absentAttr: document.querySelectorAll('.mx-cell[data-absent]').length,
                  lens: /2026-08-18/.test(document.body.innerText)};
        }""")
        ok("R34 watch-present-zero — a published-and-empty watch key prints 0 inside the sum",
           wp["watch"] == "0" and wp["sum"] == wp["head"] and wp["absence"] == 0
           and wp["absentAttr"] == 0 and "six published cells" in wp["sub"] and wp["lens"],
           f"watch={wp['watch']!r} sum={wp['sum']} head={wp['head']} absence={wp['absence']} "
           f"absentAttr={wp['absentAttr']} sub={wp['sub']!r} lens={wp['lens']}")
        pg.close()
        # and the frozen fixture's own state still reads as key-ABSENT
        pg = page_at("theme=dark&lang=en&state=paid")
        wa = pg.evaluate("""() => ({
          watch: ((document.querySelector('.mx-ladder .mx-cell .mx-cell-n')||{}).textContent||'').trim(),
          absence: document.querySelectorAll('.ladder-absence').length,
          sub: (document.querySelector('.ladder-sub .l-en')||{}).textContent||''})""")
        ok("R34b watch-absent-unchanged — the frozen fixture still renders key-absence, not zero",
           wa["watch"] == "—" and wa["absence"] == 1 and "five published cells" in wa["sub"],
           f"watch={wa['watch']!r} absence={wa['absence']} sub={wa['sub']!r}")
        pg.close()

        # ── P-B2: the newer-plan link resolves ──────────────────────────────
        pg = page_at("theme=dark&lang=en&state=paid&life=resolved")
        nl = pg.evaluate("""() => {
          const links=[...document.querySelectorAll('.pv-newer')];
          return {n: links.length,
                  anchors: links.filter(a=>a.tagName==='A').length,
                  hashOnly: links.filter(a=>(a.getAttribute('href')||'').indexOf('#id=')===0).length,
                  targets: links.filter(a=>a.tagName==='A')
                                .map(a=>new URLSearchParams((a.getAttribute('href')||'').slice(1)).get('focus'))};
        }""")
        ok("R35 newer-link-shape — the newer-plan affordance is a query-string link, never a dead #id=",
           nl["n"] > 0 and nl["hashOnly"] == 0 and nl["anchors"] == nl["n"]
           and all(nl["targets"]),
           f"links={nl['n']} anchors={nl['anchors']} hash={nl['hashOnly']} targets={nl['targets']}")
        # A link with no resolvable target must FAIL this check, not crash it:
        # a harness that throws stops every later check and reads as breakage
        # rather than as the finding it just caught.
        first = next((t for t in nl["targets"] if t), None)
        pg.close()
        pg = page_at("theme=dark&lang=en&state=paid&focus=" + (first or "NO-TARGET"))
        land = pg.evaluate("""(id) => {
          const c=document.querySelector('.pvcard[data-id="'+id+'"]');
          if(!c) return {found:false};
          const r=c.getBoundingClientRect();
          return {found:true, ringed:c.classList.contains('pv-landed'),
                  hidden:c.classList.contains('sm-hidden'),
                  note: document.querySelectorAll('.pv-landnote').length,
                  noteHasTicker: (document.querySelector('.pv-landnote')||{innerText:''})
                                   .innerText.indexOf(c.dataset.ticker)>=0,
                  noteHasSlug: (document.querySelector('.pv-landnote')||{innerText:''})
                                   .innerText.indexOf(id)>=0,
                  onScreen: r.top < window.innerHeight && r.bottom > 0};
        }""", first)
        ok("R35b newer-link-lands — the target card is revealed, ringed and named by ticker",
           first is not None
           and land.get("found") and land["ringed"] and not land["hidden"] and land["note"] == 1
           and land["noteHasTicker"] and not land["noteHasSlug"] and land["onScreen"],
           str(land))
        pg.close()
        # a focus id with no row must SAY so rather than silently doing nothing
        pg = page_at("theme=dark&lang=en&state=paid&focus=NO-SUCH-PLAN")
        miss = pg.evaluate("""() => ({note: document.querySelectorAll('.pv-landnote').length,
                                      ringed: document.querySelectorAll('.pv-landed').length,
                                      text: (document.querySelector('.pv-landnote')||{innerText:''}).innerText})""")
        ok("R35c newer-link-miss — an unresolvable focus id is disclosed, never a silent no-op",
           miss["note"] == 1 and miss["ringed"] == 0 and "not on" in miss["text"],
           str(miss))
        pg.close()

        # ── P-B6: the expectancy interval sits at the strip's own tier ──────
        for lang in ("en", "zh"):
            pg = page_at("theme=dark&lang=" + lang + "&state=paid")
            band = pg.evaluate("""() => {
              const strip=document.querySelector('.trd-btn');
              const bands=[...strip.querySelectorAll('.trd-band')]
                            .filter(e=>e.offsetParent!==null);
              const fig=strip.querySelector('.trd-stat b');
              const fs=e=>parseFloat(getComputedStyle(e).fontSize);
              return {n: bands.length, text: strip.innerText.replace(/\\s+/g,' '),
                      sameSize: bands.every(b=>fs(b)===fs(fig))};
            }""")
            ok(f"R36-{lang} expectancy-interval-at-tier — both strip figures carry their interval, same type size",
               band["n"] == 2 and band["sameSize"]
               and "-0.61" in band["text"] and "1.25" in band["text"]
               and "50.4" in band["text"],
               f"bands={band['n']} sameSize={band['sameSize']} strip={band['text']!r}")
            pg.close()
        # and the plain-word straddle is translated in BOTH languages
        for lang, phrase in (("en", "crosses zero"), ("zh", "跨过 0")):
            pg = page_at("theme=dark&lang=" + lang + "&state=paid")
            note = pg.evaluate("""() => [...document.querySelectorAll('.trk-note')]
                                        .map(p=>p.innerText).join(' ')""")
            ok(f"R36b-{lang} expectancy-straddle-in-words — the zero crossing is stated in plain words",
               phrase in note, f"missing {phrase!r}")
            pg.close()

        br.close()

    # ══ static-document checks ════════════════════════════════════════════
    # DA-001 is about an UNMARKED contradiction, so the test is whether the
    # repealed claim still stands as an assertion — not whether its words appear.
    # The repeal is recorded by quoting the repealed text, so a check that forbids
    # the string fails on the very documentation the finding demands, and the
    # obvious "fix" is to delete the record of the repeal.
    def asserting_text(md):
        """The document speaking in its OWN voice.

        Filters by PARAGRAPH, not by line: a repeal is written as prose that
        quotes the repealed rule, and that quotation routinely spans a line
        break, so a line-scoped filter sees the second half of the quote naked
        and calls it an assertion. Markdown's unit of assertion is the paragraph.

        A paragraph is not asserting if it is blockquoted, struck through, or
        anywhere declares itself a repeal/correction.
        """
        MARKERS = ("~~", "superseded", "struck at r4", "corrected at r4",
                   "repealed", "withdrawn", "amendment record")
        keep = []
        for para in re.split(r"\n\s*\n", md):
            low = para.lower()
            if all(ln.strip().startswith(">") for ln in para.splitlines() if ln.strip()):
                continue                      # entirely blockquoted
            if any(m in low for m in MARKERS):
                continue                      # declares itself a repeal/correction
            keep.append(para)
        return "\n\n".join(keep)

    live_notes = asserting_text(notes)
    ok("R8 design-notes-no-contradiction — the repealed state=paid exemption no longer ASSERTS",
       ("SUPERSEDED" in notes or "struck at R4" in notes)
       and not re.search(r"must\s+not become the flagship reference", live_notes)
       and not re.search(r"reference view \(`state=paid`\) shows the product once G-D", live_notes),
       "DESIGN_NOTES still asserts the repealed state=paid exemption in its own voice")
    ok("R26 screenshot-gaps-recorded — states the payload cannot exhibit are declared",
       "Honest screenshot gaps" in notes, "no recorded screenshot-gap section")
    # Same shape as R8: the stale arithmetic is quoted inside the correction that
    # replaces it, so its presence is evidence of the fix, not of the defect.
    ok("R27 design-notes-numbers-fresh — the stale candidate arithmetic no longer ASSERTS",
       "22 + 35 + 12 + 1" in notes and "28 + 27 + 10 + 2 + 2" not in live_notes,
       "DESIGN_NOTES still asserts 69 = 28+27+10+2+2 in its own voice")
    ok("R22 enrichment-gap-disclosed — the coverage gap is stated as a number",
       re.search(r"134\s*(of|/)\s*179", notes) is not None, "no 134/179 coverage disclosure")

    # ══ R4.2 / V-N2 — the PROSE-vs-ARTIFACT class ═════════════════════════
    # R8 and R27 each pinned ONE hard-coded string. That is not a guard, it is
    # two guards, and the finding is a CLASS: a law-bearing document asserting,
    # in its own voice, something the artifact contradicts. What follows is the
    # class. Each row pairs a claim the document may make with a fact MEASURED
    # from the artifact (never from another sentence), so adding a claim without
    # a measurement, or letting a measurement drift away from its claim, fails.
    #
    # Deliberately NOT a banned-string list: a repeal is recorded by quoting the
    # repealed text, and a string ban punishes exactly the documentation this
    # cycle demands. asserting_text() above supplies the document's own voice;
    # FACTS supplies the artifact's.
    fixture_json = json.loads(
        fixture[fixture.index("{", fixture.index("window")):fixture.rindex("}") + 1])
    C = fixture_json["counts"]
    live_addends = [C["ready"], C["entered"], C["delivering"], C["overtime"], C["invalidated"]]

    crops = crop_blobs(ART / "crops")
    crop_files = len(crops)
    crop_views = len({n[:-len("--full.png")] if n.endswith("--full.png") else n[:-4]
                      for n in crops})
    crop_distinct = len(set(crops.values()))
    alias_pairs = {}
    for name, blob in crops.items():
        if name.startswith("00-R3-"):
            twins = [n for n, b in crops.items() if b == blob and not n.startswith("00-R3-")]
            if twins:
                alias_pairs[name] = sorted(twins)
    r3_alias_views = len({n[:-len("--full.png")] if n.endswith("--full.png") else n[:-4]
                          for n in alias_pairs})

    specimen = read_from_head("mockups/design_system/specimen.html")
    # The overtime question is closed by a RULING, so the artifact it is joined
    # against is the ruling record — read from HEAD like the specimen, for the
    # same reason.
    c8 = read_from_head("research/reference_integrity/"
                        "prophet-board-5514-r4-composition/verdict.yml") or ""
    OVERTIME_STILL_OPEN = not ("b8_overtime_clock" in c8 and "CLOSED BY CITATION" in c8)

    FACTS = {
        # claim pattern (in the doc's own voice)          -> (holds?, why)
        r"Entered and Delivering are \*\*deliberately identical\*\*":
            (DELIVERING_IDENTICAL,
             "board.css separates them at VTC-305 — Delivering carries a terminal "
             "marker Entered does not, so the two rules are NOT identical"),
        r"Resolved still 17":
            (C["resolved"] == 17,
             f"the payload's resolved count is {C['resolved']}"),
        r"\*\*does not exist on disk\*\*":
            (specimen is None,
             "mockups/design_system/specimen.html exists (landed 2026-08-12 in "
             "#5459) — read it from HEAD rather than off a sparse-tree ls"),
        r"42 views, 62 files":
            (crop_views == 42 and crop_files == 62 and crop_distinct == crop_files,
             f"crops/ holds {crop_views} view stems and {crop_files} files, but only "
             f"{crop_distinct} are distinct — a manifest that counts aliases as "
             f"coverage overstates it"),
        r"`00-R3-\*` the R3 matrix":
            (r3_alias_views == 0,
             f"{r3_alias_views} 00-R3-* views are byte-identical to their 01-04 "
             f"twins — they are freeze aliases of R4 renders, not an R3 matrix"),
        r"the card cap": (False, "the card's top cap was removed at #5514 v1"),
        r"remains UNRESOLVED and blocks production":
            (OVERTIME_STILL_OPEN,
             "the C8 verdict's b8_overtime_clock ruling closed the overtime clock "
             "question by citation (SEA #4684 + the #5540 closure re-census)"),
        # §0b.5 quotes the operator's verbatim zh wording 「下方 6 个状态合计」.
        # The frozen fixture renders FIVE (watch key-absent); production's
        # present-and-empty key renders six. The quote is true in exactly one
        # state, so the document may only carry it while naming that state.
        r"下方 6 个状态合计":
            ("watch=present" in notes and "present-and-empty" in notes,
             "the frozen fixture renders five published cells — a verbatim quote "
             "of the six-cell wording must name the watch=present state it "
             "belongs to (P-K19)"),
    }
    live_notes_l = live_notes
    for pat, (holds, why) in FACTS.items():
        m = re.search(pat, live_notes_l)
        ok(f"R29 prose-vs-artifact — DESIGN_NOTES does not assert: {pat[:44]}",
           (m is None) or holds,
           f"asserted in the document's own voice, but {why}")

    # The crop manifest must state the coverage it actually has. All four
    # figures are joined to the DIRECTORY, and content identity is what counts:
    # two differently-named files holding one render are one render.
    ev = notes[notes.index("## 8. Evidence"):]
    ev = ev[:ev.index("### Honest screenshot gaps")]
    want = {"files on disk": crop_files,
            "view stems": crop_views,
            "distinct renders": crop_distinct,
            "distinct views": crop_views - r3_alias_views}
    missing = [f"{k}={v}" for k, v in want.items()
               if re.search(re.escape(k) + r"[^|]*\|[^|]*\b" + str(v) + r"\b", ev) is None]
    ok("R29g crop-manifest-arithmetic — §8's four counts are the directory's own",
       not missing,
       f"§8 does not state {missing}; crops/ measures {want} "
       f"({r3_alias_views} alias views)")
    ok("R29h crop-alias-declared — the 00-R3-* stems are declared as aliases, not as coverage",
       r3_alias_views == 0 or "aliases" in ev,
       f"{r3_alias_views} 00-R3-* views duplicate an 01-04 render and §8 must say so")
    ok("R29e specimen-exists — the canonical component sheet is read from HEAD, not from an ls",
       specimen is not None and ".mx-error" in specimen and "@keyframes skel" in specimen,
       "specimen.html unreadable from disk or HEAD, or missing its error/skeleton components")

    # ── R30: the widened stale-number sweep (P-B5) ─────────────────────────
    # R27 swept DESIGN_NOTES while index.html's reconciliation header sat unswept
    # one file away, carrying three wrong addends and two wrong dates. The sweep
    # now covers BOTH documents, and the numbers are joined against the fixture
    # rather than against each other.
    idx = (ART / "index.html").read_text()
    idx_nums = re.search(
        r"(\d+)\s*ready\s*\+\s*(\d+)\s*entered\s*\+\s*(\d+)\s*delivering\s*\+\s*"
        r"(\d+)\s*overtime\s*\+\s*(\d+)\s*invalidated\s*=\s*(\d+)\s*=\s*open_count",
        idx, re.I | re.S)
    ok("R30a index-checksum-addends — the reconciliation block's five addends are the fixture's",
       idx_nums is not None
       and [int(g) for g in idx_nums.groups()[:5]] == live_addends
       and int(idx_nums.group(6)) == fixture_json["open_count"],
       f"index.html says {idx_nums.groups() if idx_nums else None}; "
       f"fixture says {live_addends} = {fixture_json['open_count']}")
    idx_tot = re.search(r"(\d+)\s*live\s*\+\s*(\d+)\s*resolved\s*=\s*(\d+)\s*=\s*active_count",
                        idx, re.I | re.S)
    ok("R30b index-checksum-totals — the two-total law is stated with the fixture's totals",
       idx_tot is not None
       and int(idx_tot.group(1)) == fixture_json["live_total"]
       and int(idx_tot.group(2)) == C["resolved"]
       and int(idx_tot.group(3)) == fixture_json["active_count"] == fixture_json["grand_total"],
       f"index.html says {idx_tot.groups() if idx_tot else None}; fixture says "
       f"{fixture_json['live_total']} + {C['resolved']} = {fixture_json['active_count']}")
    ok("R30c index-checksum-dates — both as-of dates are the fixture's, not a previous bake's",
       re.search(r"index\.json\s+asof\s+" + re.escape(fixture_json["asof"]), idx) is not None
       and re.search(r"us_standouts\.json\s*\n?\s*as_of\s+" + re.escape(fixture_json["cand_asof"]),
                     idx) is not None,
       f"index.html must state asof {fixture_json['asof']} and as_of {fixture_json['cand_asof']}")
    # every harness state the renderer accepts must be documented in the header
    js_states = set(re.findall(r'S\.state\s*===\s*"([a-z]+)"', js))
    documented = set("|".join(re.findall(r"\?state=([a-z|]+)", idx)).split("|"))
    ok("R30d index-states-complete — the header documents every state the renderer implements",
       js_states <= documented,
       f"undocumented states: {sorted(js_states - documented)}")
    # …and so does the rationale's own run table. K17 counted index.html's four
    # of seven; a second document listing a different subset is the same defect
    # one file over, which is how P-B5 happened in the first place.
    notes_states = set(re.findall(r"`([a-z]+)`", notes[notes.index("| `state` |"):]
                                  .split("\n")[0]))
    ok("R30e notes-states-complete — §0's run table documents every state too",
       js_states <= notes_states,
       f"undocumented in DESIGN_NOTES §0: {sorted(js_states - notes_states)}")

    # ── R31b: the sector lexicon covers the payload it is joined against ────
    lex = set(re.findall(r'"([A-Za-z][A-Za-z &]+)":\s*"[^"]+"',
                         js[js.index("var SECTOR"):js.index("var LANE")]))
    payload_secs = {r["sec"] for r in fixture_json["rows"] if r.get("sec")}
    payload_secs |= {r["sec"] for r in fixture_json.get("cand_rows", []) if r.get("sec")}
    ok("R31b sector-lexicon-covers-payload — every sector the fixture publishes has a zh term",
       payload_secs and payload_secs <= lex,
       f"unmapped: {sorted(payload_secs - lex)}")
    ok("R31c sector-fallback-exists — an unmapped sector has a disclosed, non-silent path",
       "pv-ind--raw" in js and "pv-ind--raw" in css,
       "no marked fallback for a sector the lexicon does not carry")

    # compare page (DA-003)
    ok("R10 compare-true-stance — the specimen is not hardcoded to a neutral stance",
       "pv-hold" not in cmp_html or "R.stance" in cmp_html,
       "compare.html still hardcodes pv-hold")
    ok("R10b compare-scoped-prod — divergent classes are scoped into .cmp-prod",
       cmp_html.count(".cmp-prod") >= 5 and ".cmp-prod .pv-trg" in cmp_html,
       "production column still renders in the challenger's stylesheet")
    ok("R10c compare-revised-costs — the revised column carries a cost list",
       cmp_html.count("What it costs") >= 3 or cmp_html.count("代价是什么") >= 3,
       "the revised column has no cost list")
    ok("R10d compare-nochart-specimen — a chartless/no-read specimen is drawn",
       "pv-nochart" in cmp_html and re.search(r"modal", cmp_html, re.I) is not None,
       "no modal chartless specimen in the comparison")

    width = max(len(n) for _, n, _ in checks)
    for good, name, detail in checks:
        print(f"{'PASS' if good else 'FAIL'}  {name.ljust(width)}  {detail if not good else ''}".rstrip())
    print(f"\n{sum(1 for g, _, _ in checks if g)}/{len(checks)} R4 closure checks passed")
    if fails:
        print("\nFAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
