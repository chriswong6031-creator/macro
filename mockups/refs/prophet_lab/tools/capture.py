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
    ("32-live-only-dark-en",      DESKTOP, "theme=dark&lang=en&cls=live"),
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
