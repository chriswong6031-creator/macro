#!/usr/bin/env python3
"""Capture the D-LAB-R5 crop set.

Usage:  python3 tools/capture.py [base_url] [out_dir]
        (a static server must already be serving mockups/refs/prophet_lab)

        cd mockups/refs && python3 -m http.server 8794
        python3 prophet_lab/tools/capture.py http://localhost:8794/prophet_lab crops

Matrix: 1440 + 390 x dark + light x EN + ZH, for BOTH modes, plus the three
degraded Lab states, the six board selectors, the observation-class filters,
and the LIVE⇄LAB round trip.

THE LAB CROPS ARE CLICKED, NOT URL-ADDRESSED. `?mode=lab` exists as a harness
lens, but a fresh page always defaults LIVE in the product, so the evidence has
to be of the real interaction — R4's own standard, adopted here verbatim
(its `Show all` crops click first for the same reason). Every clicked capture
RAISES if the control is missing or if the resulting state is not the one
claimed, so a regression cannot quietly yield a crop of the wrong state that
photographs as success.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8794/prophet_lab"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "crops")

DESKTOP = (1440, 900)
MOBILE = (390, 844)

LAB_SEG = '.lab-seg button[data-mode="lab"]'
LIVE_SEG = '.lab-seg button[data-mode="live"]'

# ── LIVE mode: the production board with the operator affordance at rest ────
LIVE_SHOTS = [
    ("01-live-desktop-dark-en",   DESKTOP, "theme=dark&lang=en"),
    ("02-live-desktop-light-zh",  DESKTOP, "theme=light&lang=zh"),
    ("03-live-mobile390-dark-en", MOBILE,  "theme=dark&lang=en"),
    # the affordance is OPERATOR-ONLY: with no entitlement the page is the R4
    # board and nothing else — not a disabled control, not a teaser
    ("04-live-no-operator-dark-en",  DESKTOP, "theme=dark&lang=en&op=0"),
    ("05-live-no-operator-light-zh", DESKTOP, "theme=light&lang=zh&op=0"),
]

# ── LAB mode, reached by clicking the control ───────────────────────────────
LAB_SHOTS = [
    ("10-lab-desktop-dark-en",    DESKTOP, "theme=dark&lang=en"),
    ("11-lab-desktop-light-en",   DESKTOP, "theme=light&lang=en"),
    ("12-lab-desktop-dark-zh",    DESKTOP, "theme=dark&lang=zh"),
    ("13-lab-desktop-light-zh",   DESKTOP, "theme=light&lang=zh"),
    ("14-lab-mobile390-dark-en",  MOBILE,  "theme=dark&lang=en"),
    ("15-lab-mobile390-light-en", MOBILE,  "theme=light&lang=en"),
    ("16-lab-mobile390-dark-zh",  MOBILE,  "theme=dark&lang=zh"),
    ("17-lab-mobile390-light-zh", MOBILE,  "theme=light&lang=zh"),
    # the six frozen board selectors (LAB-0 §3)
    ("20-board-earliest-mark",    DESKTOP, "theme=dark&lang=en&board=lab-g0-v1"),
    ("21-board-flush",            DESKTOP, "theme=dark&lang=en&board=lab-c1-v1"),
    ("22-board-turning-up",       DESKTOP, "theme=dark&lang=en&board=lab-c2a-v1"),
    ("23-board-all-readings",     DESKTOP, "theme=dark&lang=en&board=lab-c2-variants-v1"),
    ("24-board-marked-turning",   DESKTOP, "theme=dark&lang=en&board=lab-g0-c2a-v1"),
    ("25-board-all-early",        DESKTOP, "theme=dark&lang=en&board=lab-all-early-v1"),
    ("26-board-all-readings-zh",  DESKTOP, "theme=light&lang=zh&board=lab-c2-variants-v1"),
    ("27-board-flush-390-zh",     MOBILE,  "theme=dark&lang=zh&board=lab-c1-v1"),
    # observation class in isolation — the seed treatment has to survive being
    # looked at on its own, not only next to a live row that flatters it
    ("30-seeds-only-dark-en",     DESKTOP, "theme=dark&lang=en&cls=seed"),
    ("31-seeds-only-light-zh",    DESKTOP, "theme=light&lang=zh&cls=seed"),
    # R5.2 / PR51-13 — `32-live-only-dark-en` is GONE. It shot
    # `theme=dark&lang=en&cls=live`, which is byte-for-byte the shot `35`
    # already takes, so the crop set claimed one more view than it held and two
    # files carried one piece of evidence under two names. 35 keeps the slot
    # because it also ships the full-page frame; the seen-live class in
    # isolation and the lead symmetry are the same view, and saying so once is
    # the honest count.
    ("33-live-only-light-en",     DESKTOP, "theme=light&lang=en&cls=live"),
    ("34-seeds-only-390-dark-en", MOBILE,  "theme=dark&lang=en&cls=seed"),
    # ── R5.1 evidence: the three majors and the elevated conditions ────────
    #    35/36 photograph the LEAD SYMMETRY: the fixture now carries all five
    #    branches (+3, +2, +1, 0, -3) so the adverse and same-day treatments
    #    are visible next to the favourable ones rather than argued about.
    ("35-lead-symmetry-dark-en",  DESKTOP, "theme=dark&lang=en&cls=live"),
    ("36-lead-symmetry-light-zh", DESKTOP, "theme=light&lang=zh&cls=live"),
    ("37-lead-symmetry-390-dark-en", MOBILE, "theme=dark&lang=en&cls=live"),
    # ── the three degraded states. Each must stay VISIBLY LAB. ─────────────
    ("40-lab-empty-dark-en",      DESKTOP, "theme=dark&lang=en&feed=empty"),
    ("41-lab-empty-light-zh",     DESKTOP, "theme=light&lang=zh&feed=empty"),
    ("42-lab-empty-390-dark-en",  MOBILE,  "theme=dark&lang=en&feed=empty"),
    ("43-lab-behind-dark-en",     DESKTOP, "theme=dark&lang=en&feed=stale"),
    ("44-lab-behind-light-zh",    DESKTOP, "theme=light&lang=zh&feed=stale"),
    ("45-lab-behind-390-dark-en", MOBILE,  "theme=dark&lang=en&feed=stale"),
    ("46-lab-down-dark-en",       DESKTOP, "theme=dark&lang=en&feed=down"),
    ("47-lab-down-light-zh",      DESKTOP, "theme=light&lang=zh&feed=down"),
    ("48-lab-down-390-dark-en",   MOBILE,  "theme=dark&lang=en&feed=down"),
    # ── R5.2 / R52-D3 — THE MISSING QUADRANTS ──────────────────────────────
    #    The two states carrying the VTL-402 unknown-vs-zero distinction were
    #    only ever shot dark-EN and light-ZH, so the theme and the language
    #    moved together and neither could be judged on its own. These are the
    #    other two corners: light-EN and dark-ZH, for both `down` and `empty`.
    ("49-lab-down-light-en",      DESKTOP, "theme=light&lang=en&feed=down"),
    ("4a-lab-down-dark-zh",       DESKTOP, "theme=dark&lang=zh&feed=down"),
    ("4b-lab-empty-light-en",     DESKTOP, "theme=light&lang=en&feed=empty"),
    ("4c-lab-empty-dark-zh",      DESKTOP, "theme=dark&lang=zh&feed=empty"),
]

# ── R5.2 / PR51-1 — THE PINNED DIVIDER, SHOT WHERE THE CLAIM LIVES ─────────
# Every R5.1 crop framed the divider at the crossing, which is the one scroll
# position at which a sticky element and a static one are indistinguishable.
# The claim the artifact makes for it is about the position 1,200px later, so
# that is where these are taken. Each asserts the pin before it shoots: a crop
# of a divider that scrolled away would be a picture of the R5.1 defect.
#
# R5.3 / PR52-1 — `55` is the chrome=1 shot, and it exists because the claim
# "the divider pins BELOW the sticky chrome" had been stated three times and
# photographed zero times. It was also FALSE when it was written: the harness
# bar had no travel, so what chrome=1 actually produced was 149px of empty band
# above the pin. Now the bar pins, and the crop has to show BOTH of them on
# screen at once — the block below refuses to shoot unless it does.
SCROLL_SHOTS = [
    ("51-seed-region-pinned-dark-en",      DESKTOP, "theme=dark&lang=en", "0"),
    ("52-seed-region-pinned-light-zh",     DESKTOP, "theme=light&lang=zh", "0"),
    ("53-seed-region-pinned-390-dark-en",  MOBILE,  "theme=dark&lang=en", "0"),
    ("55-seed-region-pinned-chrome1-dark-en", DESKTOP, "theme=dark&lang=en", "1"),
]

# ── R5.3 / VTL52-604 + VTL52-605 — THE LENS, OPEN, AT THE DESIGN FLOOR ──────
# Not one crop in the 63-file R5.2 set photographed a LENS popover anywhere, so
# every <=560 demotion claim was visually unreceipted — and the capture path
# actively parked the cursor to CLOSE any tip before shooting. These two open
# the landing the mobile reader depends on, by TAP under a coarse pointer, and
# refuse to emit unless the popover is on screen carrying the demoted text.
LENS_SHOTS = [
    ("56-lens-open-390-dark-en",  "theme=dark&lang=en",   "en"),
    ("57-lens-open-390-light-zh", "theme=light&lang=zh",  "zh"),
]

FULL_PAGE = {
    "01-live-desktop-dark-en", "02-live-desktop-light-zh",
    "04-live-no-operator-dark-en",
    # the full-page LAB shots are the VTL-401 evidence: every plan-book section
    # that R5 deleted on mode entry has to be visible in them.
    "10-lab-desktop-dark-en", "11-lab-desktop-light-en",
    "12-lab-desktop-dark-zh", "13-lab-desktop-light-zh",
    "14-lab-mobile390-dark-en", "17-lab-mobile390-light-zh",
    "25-board-all-early", "30-seeds-only-dark-en", "31-seeds-only-light-zh",
    "35-lead-symmetry-dark-en", "36-lead-symmetry-light-zh",
    "40-lab-empty-dark-en", "43-lab-behind-dark-en", "46-lab-down-dark-en",
}


def overflow(page):
    o = page.evaluate("() => ({sw: document.documentElement.scrollWidth,"
                      " cw: document.documentElement.clientWidth})")
    return o, ("  << HORIZONTAL SCROLL" if o["sw"] > o["cw"] else "")


def shoot(page, name, made, w, h, extra=""):
    o, flag = overflow(page)
    page.screenshot(path=str(OUT / f"{name}.png"))
    n = 1
    if name in FULL_PAGE:
        page.screenshot(path=str(OUT / f"{name}--full.png"), full_page=True)
        n += 1
    made.append(f"{name}  {w}x{h}  sw={o['sw']} cw={o['cw']}{flag}{extra}")
    return n


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made, files = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch()

        for name, (w, h), q in LIVE_SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            page.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            page.wait_for_timeout(220)
            # a LIVE crop that is not LIVE would be evidence of the wrong thing
            mode = page.evaluate("() => document.documentElement.dataset.mode")
            if mode != "live":
                raise SystemExit(f"::error title=capture::{name}: mode is {mode!r}, expected 'live'")
            has_seg = page.query_selector(".lab-seg") is not None
            want_seg = "op=0" not in q
            if has_seg is not want_seg:
                raise SystemExit(
                    f"::error title=capture::{name}: mode control present={has_seg}, expected {want_seg}")
            files += shoot(page, name, made, w, h,
                           "  operator control: " + ("shown" if has_seg else "absent"))
            page.close()

        for name, (w, h), q in LAB_SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            page.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            page.wait_for_timeout(200)
            el = page.query_selector(LAB_SEG)
            if el is None:
                raise SystemExit(
                    f"::error title=capture::{name}: {LAB_SEG} not found — refusing "
                    "to emit a crop of a state that was never entered")
            # R5.1 / VTL-401 — the survivor test is DIFFERENTIAL, measured
            # against LIVE at THIS viewport rather than against a fixed count.
            # R4 itself hides the page subtitle below 720w ("the h1 already says
            # what this is", board.css:996), so an absolute count would fail at
            # 390 for a reason that has nothing to do with the mode. The law is
            # "the mode takes only the grid", and that is what is measured.
            SURV = ("() => { const v = q => [...document.querySelectorAll(q)]"
                    ".filter(n => n.offsetParent !== null).length;"
                    " return {ladder: v('.ladder-block'), purpose: v('.bh-purpose'),"
                    " stamp: v('.bh-stamp'), candidates: v('#candidates'),"
                    " groups: v('#groups'), evidence: v('#evidence, #record')}; }")
            before = page.evaluate(SURV)
            el.click()
            page.wait_for_timeout(320)
            # R5.2: the flip LANDS the region at 390 (R52-D2), and the virtual
            # cursor stays where it clicked — so content scrolls under it and
            # opens a LENS popover across the crop. Park it in the top-right
            # corner, which after landing is the mode bar's own padding at every
            # width and carries no tip, then let any popover close.
            page.mouse.move(w - 4, 4)
            page.wait_for_timeout(140)
            st = page.evaluate("""() => {
                const vis = q => [...document.querySelectorAll(q)]
                                  .filter(n => n.offsetParent !== null).length;
                return {
                  mode: document.documentElement.dataset.mode,
                  lab: !!document.querySelector('.lab-plane'),
                  eyebrow: !!document.querySelector('.lab-eyebrow'),
                  rows: document.querySelectorAll('.lab-row').length,
                  seeds: document.querySelectorAll('.lab-row--seed').length,
                  pvcards: vis('.pvcard'),
                  // R5.1 / VTL-401: the mode scopes to the grid. A crop that
                  // photographs a page with these missing is evidence of the
                  // very defect the R5 verdict blocked on, so the capture
                  // refuses to produce it.
                  regionEnd: vis('.lab-region-end')
                };
            }""")
            after = page.evaluate(SURV)
            lost = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
            if st["mode"] != "lab" or not st["lab"] or not st["eyebrow"]:
                raise SystemExit(f"::error title=capture::{name}: not in LAB — {st}")
            # NO Prophet setup card may be visible under a LAB label, in any state
            if st["pvcards"]:
                raise SystemExit(
                    f"::error title=capture::{name}: {st['pvcards']} Prophet cards visible in LAB")
            if lost or not st["regionEnd"]:
                raise SystemExit(
                    f"::error title=capture::{name}: the mode took more than the grid — "
                    f"changed on mode entry: {lost}; region-end rule "
                    f"{'present' if st['regionEnd'] else 'MISSING'} (VTL-401)")
            files += shoot(page, name, made, w, h,
                           f"  rows={st['rows']} seeds={st['seeds']}")
            page.close()

        # ── the pinned divider, deep in the region it governs ──────────────
        for name, (w, h), q, chrome_q in SCROLL_SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            page.goto(f"{BASE}/?{q}&chrome={chrome_q}", wait_until="networkidle")
            page.wait_for_timeout(200)
            el = page.query_selector(LAB_SEG)
            if el is None:
                raise SystemExit(f"::error title=capture::{name}: {LAB_SEG} not found")
            el.click()
            page.wait_for_timeout(320)
            # the virtual cursor stays where it clicked, so a scroll drags fresh
            # content under it and opens a LENS popover over the evidence. Park
            # it in the top-right corner, which no tip-bearing node occupies at
            # either width, and let any open popover close.
            page.mouse.move(w - 4, 4)
            page.wait_for_timeout(120)
            rest = page.evaluate("""() => {
                const m = document.querySelector('.lab-mark');
                return m ? Math.round(m.getBoundingClientRect().top + window.scrollY) : null;
            }""")
            if rest is None:
                raise SystemExit(f"::error title=capture::{name}: no .lab-mark to photograph")
            page.evaluate(f"() => window.scrollTo(0, {rest} + 1200)")
            page.wait_for_timeout(280)
            st = page.evaluate("""() => {
                const m = document.querySelector('.lab-mark');
                const bar = document.querySelector('.harness');
                const vh = window.innerHeight;
                const on = q => [...document.querySelectorAll(q)].filter(n => {
                    const r = n.getBoundingClientRect();
                    return r.bottom > 0 && r.top < vh;
                }).length;
                const r = m.getBoundingClientRect();
                const br = bar ? bar.getBoundingClientRect() : null;
                return {top: Math.round(r.top), seeds: on('.lab-row--seed'),
                        live: on('.lab-row--live'), y: Math.round(window.scrollY),
                        off: parseInt(getComputedStyle(document.documentElement)
                               .getPropertyValue('--lab-mark-top'), 10) || 0,
                        barTop: br ? Math.round(br.top) : null,
                        barH: br ? Math.round(br.height) : 0};
            }""")
            # the pin lands at the measured chrome offset — 0 with no chrome,
            # the chrome's own height with it (R5.3 / PR52-1)
            if abs(st["top"] - st["off"]) > 2 or st["seeds"] < 1:
                raise SystemExit(
                    f"::error title=capture::{name}: the divider did not pin — mark top "
                    f"{st['top']}px against a {st['off']}px chrome offset with "
                    f"{st['seeds']} seed rows on screen at scrollY {st['y']}. Refusing "
                    f"to photograph an unpinned divider (PR51-1).")
            if chrome_q == "1" and (st["barH"] < 1 or abs(st["barTop"]) > 1):
                raise SystemExit(
                    f"::error title=capture::{name}: the chrome this crop exists to "
                    f"photograph is not on screen — harness bar top {st['barTop']}px "
                    f"h {st['barH']}px at scrollY {st['y']}. A crop of an empty band "
                    f"above the pin is a picture of the PR52-1 defect, not of the seam.")
            files += shoot(page, name, made, w, h,
                           f"  scrollY={st['y']} mark top={st['top']}px "
                           f"chrome offset={st['off']}px bar top={st['barTop']} "
                           f"seeds on screen={st['seeds']}")
            page.close()

        # ── R5.3 / VTL52-605 — the LENS, open, under a thumb ────────────────
        for name, q, lg in LENS_SHOTS:
            ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                      device_scale_factor=1,
                                      has_touch=True, is_mobile=True)
            page = ctx.new_page()
            page.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            page.wait_for_timeout(200)
            if page.query_selector(LAB_SEG) is None:
                raise SystemExit(f"::error title=capture::{name}: {LAB_SEG} not found")
            page.tap(LAB_SEG)
            page.wait_for_selector(".lab-plane", timeout=8000)
            page.wait_for_timeout(340)
            # the chip that CARRIES the <=560 demotions: the sort basis, the
            # board subtitle and the lead total all land in this one tip
            page.tap(".lab-split")
            page.wait_for_timeout(300)
            st = page.evaluate("""() => {
                const p = document.querySelector('.lens-pop');
                const s = document.querySelector('.lab-split');
                const vh = window.innerHeight, vw = window.innerWidth;
                const r = p ? p.getBoundingClientRect() : null;
                return {
                  open: !!(p && p.classList.contains('open')),
                  inFrame: !!(r && r.top >= 0 && r.bottom <= vh + 1
                              && r.left >= 0 && r.right <= vw + 1),
                  marked: !!(s && s.hasAttribute('data-lens-open')),
                  chars: p ? p.innerText.trim().length : 0,
                  y: Math.round(window.scrollY)
                };
            }""")
            if not (st["open"] and st["inFrame"] and st["marked"]):
                raise SystemExit(
                    f"::error title=capture::{name}: the LENS did not open under a tap, "
                    f"or opened off frame — {st}. This crop exists because the R5.2 set "
                    "photographed no popover at all (VTL52-605); refusing to emit one "
                    "that shows a closed tip.")
            files += shoot(page, name, made, 390, 844,
                           f"  tapped .lab-split, popover {st['chars']} chars in frame "
                           f"at scrollY={st['y']} [{lg}]")
            page.close()
            ctx.close()

        # ── R5.2 / R52-D3 — a 390 crop that actually CONTAINS a signed lead ──
        #    `37-lead-symmetry-390` was named for the lead and photographed only
        #    chrome: at 390 nothing but the preamble was above the fold, so the
        #    M3 evidence at the design floor showed none of what it claimed. The
        #    landing fixes the fold, and this shot additionally scrolls the
        #    ADVERSE chip into view — the branch R5 could not render at all —
        #    and refuses to shoot if it is not on screen.
        page = browser.new_page(viewport={"width": 390, "height": 844},
                                device_scale_factor=1)
        page.goto(f"{BASE}/?theme=dark&lang=en&cls=live&chrome=0", wait_until="networkidle")
        page.wait_for_timeout(200)
        el = page.query_selector(LAB_SEG)
        if el is None:
            raise SystemExit("::error title=capture::54: mode control missing")
        el.click()
        page.wait_for_timeout(320)
        page.mouse.move(386, 4)
        page.wait_for_timeout(120)
        adv = page.evaluate("""() => {
            const a = document.querySelector('.lab-lead--adverse');
            if (!a) return null;
            const r = a.getBoundingClientRect();
            /* park the adverse chip in the lower third, so the row it belongs
               to is on screen with it rather than cropped to a floating chip */
            window.scrollTo(0, Math.round(r.top + window.scrollY - window.innerHeight * 0.62));
            return true;
        }""")
        if not adv:
            raise SystemExit(
                "::error title=capture::54: no .lab-lead--adverse in the fixture — the "
                "adverse branch is the one VTL-403 found unrenderable; refusing to ship "
                "a lead crop without it")
        page.wait_for_timeout(260)
        st = page.evaluate("""() => {
            const vh = window.innerHeight;
            const vis = q => [...document.querySelectorAll(q)].filter(n => {
                const r = n.getBoundingClientRect();
                return r.top >= 0 && r.bottom <= vh;
            });
            /* the adverse chip must be WHOLE in frame; a second measured chip
               only has to be legible, because at 390 a row is ~300px tall and
               the fold holds about two and a half of them */
            const partial = q => [...document.querySelectorAll(q)].filter(n => {
                const r = n.getBoundingClientRect();
                return r.bottom > 0 && r.top < vh;
            });
            return {adverse: vis('.lab-lead--adverse').length,
                    measured: partial('.lab-lead--measured').length,
                    y: Math.round(window.scrollY)};
        }""")
        # The bar is the ADVERSE chip whole in frame — that is the branch R5
        # could not render and the reason this crop exists. A second measured
        # chip is reported, not required: at 390 a row stands ~322px and the
        # adverse row's neighbours can both be "nothing to compare yet", so
        # demanding two would make the check a fact about the fixture's row
        # order rather than about the design.
        if st["adverse"] < 1:
            raise SystemExit(
                f"::error title=capture::54: the adverse lead chip is not whole in frame "
                f"— {st}. This crop exists to show the signed lead at the design floor "
                "(R52-D3); refusing to emit one that does not.")
        files += shoot(page, "54-lead-adverse-390-dark-en", made, 390, 844,
                       f"  scrollY={st['y']} adverse chips in frame={st['adverse']} "
                       f"measured chips in frame={st['measured']}")
        page.close()

        # ── the round trip. LAB → LIVE must RE-DERIVE the live board, not
        #    restore a snapshot, and must leave nothing of the Lab behind. ──
        page = browser.new_page(viewport={"width": 1440, "height": 900},
                                device_scale_factor=1)
        page.goto(f"{BASE}/?theme=dark&lang=en&chrome=0", wait_until="networkidle")
        page.wait_for_timeout(200)
        cold = page.evaluate(
            "() => [...document.querySelectorAll('.pvcard')].filter(c => c.offsetParent !== null).length")
        page.click(LAB_SEG)
        page.wait_for_timeout(320)
        page.click(LIVE_SEG)
        page.wait_for_timeout(600)
        back = page.evaluate("""() => ({
            mode: document.documentElement.dataset.mode,
            lab: !!document.querySelector('.lab-plane'),
            labRows: document.querySelectorAll('.lab-row').length,
            pvcards: [...document.querySelectorAll('.pvcard')].filter(c => c.offsetParent !== null).length,
            ladder: !!document.querySelector('.ladder-block'),
            stamp: !!document.querySelector('.bh-stamp'),
            seg: !!document.querySelector('.lab-seg')
        })""")
        if (back["mode"] != "live" or back["lab"] or back["labRows"]
                or back["pvcards"] != cold or not back["ladder"]
                or not back["stamp"] or not back["seg"]):
            raise SystemExit(
                f"::error title=capture::round trip did not restore LIVE exactly — "
                f"cold pvcards={cold}, after={back}")
        files += shoot(page, "50-roundtrip-live-after-lab", made, 1440, 900,
                       f"  cold={cold} after={back['pvcards']} cards (equal)")
        page.close()

        browser.close()

    print("\n".join(made))
    print(f"\n{len(made)} views -> {files} files in {OUT}/")


if __name__ == "__main__":
    main()
