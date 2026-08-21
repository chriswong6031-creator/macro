#!/usr/bin/env python3
"""Capture the MP-1 mockup-gate crop set.

Usage:  python3 tools/capture.py [base_url] [out_dir]
        (a static server must already be serving this directory)

Produces the factory §0.2 matrix — light + dark x EN + ZH x 1440 + 390w — plus
the forced states the packet requires as review-blocking evidence.
"""
import sys
import pathlib
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8791"
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "crops")

DESKTOP = (1440, 900)
MOBILE = (390, 844)

# name, viewport, query
SHOTS = [
    # ── THE FREEZE CROPS (operator: "one final light-ZH + dark-EN") ────────
    ("00-R3-dark-en",             DESKTOP, "theme=dark&lang=en&state=paid"),
    ("00-R3-light-zh",            DESKTOP, "theme=light&lang=zh&state=paid"),
    ("00-R3-light-en",            DESKTOP, "theme=light&lang=en&state=paid"),
    ("00-R3-dark-zh",             DESKTOP, "theme=dark&lang=zh&state=paid"),
    # ── handoff §12 deliverables 1-5: the required matrix ──────────────────
    ("01-desktop-dark-en",        DESKTOP, "theme=dark&lang=en&state=paid"),
    ("02-desktop-light-en",       DESKTOP, "theme=light&lang=en&state=paid"),
    ("03-desktop-dark-zh",        DESKTOP, "theme=dark&lang=zh&state=paid"),
    ("04-desktop-light-zh",       DESKTOP, "theme=light&lang=zh&state=paid"),
    ("05-mobile390-dark-en",      MOBILE,  "theme=dark&lang=en&state=paid"),
    ("06-mobile390-dark-zh",      MOBILE,  "theme=dark&lang=zh&state=paid"),
    ("07-mobile390-light-en",     MOBILE,  "theme=light&lang=en&state=paid"),
    # ── the honesty state: the ACTUAL payload, no-reads included ───────────
    # ── §12.7: the missing-enrichment fallback ─────────────────────────────
    ("10-fallback-dark-en",       DESKTOP, "theme=dark&lang=en&state=fallback"),
    ("11-fallback-light-zh",      DESKTOP, "theme=light&lang=zh&state=fallback"),
    ("12-fallback-390-dark-en",   MOBILE,  "theme=dark&lang=en&state=fallback"),
    # ── §12.8-10: the named filters ────────────────────────────────────────
    ("20-filter-ready",           DESKTOP, "theme=dark&lang=en&state=paid&life=ready"),
    ("21-filter-entered",         DESKTOP, "theme=dark&lang=en&state=paid&life=entered"),
    ("22-filter-invalidated",     DESKTOP, "theme=dark&lang=en&state=paid&life=invalidated"),
    ("23-filter-invalidated-zh",  DESKTOP, "theme=light&lang=zh&state=paid&life=invalidated"),
    ("24-filter-watch-absent",    DESKTOP, "theme=dark&lang=en&state=paid&life=watch"),
    ("25-filter-delivering-zero", DESKTOP, "theme=dark&lang=en&state=paid&life=delivering"),
    ("26-filter-overtime-zero",   DESKTOP, "theme=dark&lang=en&state=paid&life=overtime"),
    ("27-filter-resolved",        DESKTOP, "theme=dark&lang=en&state=paid&life=resolved"),
    # ── R4.2 / P-K19: the watch key present-and-EMPTY. The frozen fixture has
    #    the key absent (an em dash); production publishes it empty from
    #    2026-08-18 (a literal 0, six published cells, no disclosure line).
    #    Same counts, the other reading — the fixture is not re-baked.
    ("28-watch-present-zero",     DESKTOP, "theme=dark&lang=en&state=paid&watch=present"),
    ("29-watch-present-zero-zh",  DESKTOP, "theme=light&lang=zh&state=paid&watch=present"),
    # ── §12.11: multi-episode ──────────────────────────────────────────────
    ("30-multi-episode-en",       DESKTOP, "theme=dark&lang=en&state=episodes"),
    ("31-multi-episode-zh",       DESKTOP, "theme=light&lang=zh&state=episodes"),
    ("32-multi-episode-resolved", DESKTOP, "theme=dark&lang=en&state=episodes&life=resolved"),
    ("33-multi-episode-390-en",   MOBILE,  "theme=dark&lang=en&state=episodes"),
    # ── R4.2 / P-B2: where the newer-plan link LANDS. The capability was dead
    #    in every state before this round, so it had no picture; a link that
    #    resolves has to be evidenced by the view it resolves to.
    ("34-newer-plan-landing",     DESKTOP, "theme=dark&lang=en&state=paid&focus=FBRT-BULL-20260805"),
    ("35-newer-plan-landing-zh",  DESKTOP, "theme=light&lang=zh&state=paid&focus=ARES-BULL-20260722"),
    # ── §12.12: anonymous / locked ─────────────────────────────────────────
    ("40-anon-locked-dark-en",    DESKTOP, "theme=dark&lang=en&state=anon"),
    ("41-anon-locked-light-zh",   DESKTOP, "theme=light&lang=zh&state=anon"),
    ("42-anon-locked-390-dark",   MOBILE,  "theme=dark&lang=en&state=anon"),
    # ── other required states ──────────────────────────────────────────────
    ("50-empty-dark-en",          DESKTOP, "theme=dark&lang=en&state=empty"),
    ("51-empty-light-zh",         DESKTOP, "theme=light&lang=zh&state=empty"),
    # ── R4.2 / V-B4: the two canonical components the specimen ships and this
    #    reference did not carry. Empty / loading / error are ONE family and
    #    are photographed together, because what they have to prove is that a
    #    reader can tell them apart.
    ("52-loading-dark-en",        DESKTOP, "theme=dark&lang=en&state=loading"),
    ("53-loading-light-zh",       DESKTOP, "theme=light&lang=zh&state=loading"),
    ("54-loading-390-dark-en",    MOBILE,  "theme=dark&lang=en&state=loading"),
    ("55-error-dark-en",          DESKTOP, "theme=dark&lang=en&state=error"),
    ("56-error-light-zh",         DESKTOP, "theme=light&lang=zh&state=error"),
    ("57-error-390-dark-en",      MOBILE,  "theme=dark&lang=en&state=error"),
    ("60-table-invalidated",      DESKTOP, "theme=dark&lang=en&state=paid&life=invalidated&view=table"),
    ("61-table-resolved-zh",      DESKTOP, "theme=light&lang=zh&state=paid&life=resolved&view=table"),
    # ── §12: the three-way card adjudication (its own page) ────────────────
    ("70-compare-dark-en",        DESKTOP, "PAGE:compare.html?theme=dark&lang=en"),
    ("71-compare-light-en",       DESKTOP, "PAGE:compare.html?theme=light&lang=en"),
    ("72-compare-dark-zh",        DESKTOP, "PAGE:compare.html?theme=dark&lang=zh"),
    ("73-compare-light-zh",       DESKTOP, "PAGE:compare.html?theme=light&lang=zh"),
    # ── R4: the behind-the-tape state (PRC-305). Production ships this banner
    #    today; the R3 reference had no stale path at all, which is why it needs
    #    its own committed evidence in both languages.
    ("80-stale-dark-en",          DESKTOP, "theme=dark&lang=en&state=stale"),
    ("81-stale-light-zh",         DESKTOP, "theme=light&lang=zh&state=stale"),
    ("82-stale-390-dark-en",      MOBILE,  "theme=dark&lang=en&state=stale"),
]

# ── R4: states that only exist AFTER an interaction. PRC-306's expansion cannot
#    be evidenced by a URL, so the shot is defined by the control it clicks.
#    Without this the reference would ship a capability with no picture of it.
CLICK_SHOTS = [
    ("90-expanded-dark-en",  DESKTOP, "theme=dark&lang=en&state=paid",
     ".sm-bar .sm-btn.sm-ghost"),
    ("91-expanded-light-zh", DESKTOP, "theme=light&lang=zh&state=paid",
     ".sm-bar .sm-btn.sm-ghost"),
]


# full-page captures are opt-in: a full-page 390w shot is ~4000px tall, and the
# gate is reviewed on the above-fold composition. These are the views where the
# whole-page rhythm (three count-bearing devices, §G.2) is the thing being judged.
FULL_PAGE = {
    "00-R3-dark-en", "00-R3-light-zh", "00-R3-light-en", "00-R3-dark-zh",
    "01-desktop-dark-en", "02-desktop-light-en", "03-desktop-dark-zh",
    "04-desktop-light-zh", "05-mobile390-dark-en", "06-mobile390-dark-zh",
    "10-fallback-dark-en", "30-multi-episode-en", "40-anon-locked-dark-en",
    "50-empty-dark-en",
    # R4.2: the new states are judged on the WHOLE page — loading and error both
    # make a claim about what is unaffected below them, and an above-fold crop
    # cannot show whether that claim is true.
    "28-watch-present-zero", "34-newer-plan-landing",
    "52-loading-dark-en", "55-error-dark-en",
    "70-compare-dark-en", "71-compare-light-en", "72-compare-dark-zh", "73-compare-light-zh",
}


# R4.2: the loading skeleton is the first ANIMATED thing in the crop set, and an
# animation makes a screenshot non-reproducible — every re-capture would land at
# a different sweep phase and churn bytes that mean nothing. Pinned to a fixed
# phase (not disabled: a paused sweep is the same paint, frozen), so a crop diff
# still means a design change.
# Pausing a RUNNING animation is not reproducible — the phase depends on when
# the style landed. The animation is removed and the sweep pinned to an explicit
# mid-travel position instead, which is one exact frame of the same paint.
FREEZE_CSS = ("*, *::before, *::after { animation: none !important }"
              ".skel { background-position: -100% 0 !important }")


def freeze(page):
    page.add_style_tag(content=FREEZE_CSS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    n_files = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (w, h), q in SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            url = (f"{BASE}/{q[5:]}" if q.startswith("PAGE:")
                   else f"{BASE}/?{q}&chrome=0")
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(220)
            freeze(page)

            # a horizontal page scroll is an acceptance failure, not a nit
            over = page.evaluate(
                "() => ({sw: document.documentElement.scrollWidth,"
                " cw: document.documentElement.clientWidth})")
            flag = "  << HORIZONTAL SCROLL" if over["sw"] > over["cw"] else ""

            page.screenshot(path=str(OUT / f"{name}.png"))                 # above-fold
            n_files += 1
            if name in FULL_PAGE:
                page.screenshot(path=str(OUT / f"{name}--full.png"), full_page=True)
                n_files += 1
            made.append(f"{name}  {w}x{h}  sw={over['sw']} cw={over['cw']}{flag}")
            page.close()

        # post-interaction states (PRC-306): click, then shoot
        for name, (w, h), q, sel in CLICK_SHOTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            page.goto(f"{BASE}/?{q}&chrome=0", wait_until="networkidle")
            page.wait_for_timeout(220)
            freeze(page)
            el = page.query_selector(sel)
            if el is None:
                # FAIL LOUD. A missing control must not quietly yield a crop of
                # the un-expanded grid that photographs as though it worked.
                raise SystemExit(
                    f"::error title=capture::{name}: control {sel} not found — "
                    "refusing to emit a crop that would misrepresent the state")
            el.click()
            page.wait_for_timeout(500)
            vis = page.evaluate(
                "() => [...document.querySelectorAll('.pvcard')]"
                ".filter(c => c.offsetParent !== null).length")
            page.screenshot(path=str(OUT / f"{name}.png"))
            page.screenshot(path=str(OUT / f"{name}--full.png"), full_page=True)
            n_files += 2
            made.append(f"{name}  {w}x{h}  after click {sel} -> {vis} visible cards")
            page.close()

        browser.close()
    print("\n".join(made))
    print(f"\n{len(made)} views -> {n_files} files in {OUT}/")


if __name__ == "__main__":
    main()
