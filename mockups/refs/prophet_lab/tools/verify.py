#!/usr/bin/env python3
"""D-LAB-R5 acceptance checks, run against the RENDERED page.

Usage:  python3 tools/verify.py [base_url]
        (a static server must already be serving mockups/refs/prophet_lab)

These are a FLOOR, not the acceptance — the crops are the deliverable. What
they exist to catch is the class of regression a screenshot cannot: a law that
is true in the crop but not in the code, and a law that quietly stops being
enforced.

Every check id is cited from the disposition it proves in DESIGN_NOTES.md, so
undoing a closure item breaks a named check rather than merely looking
different. Run tools/mutation_test.py to confirm the checks actually bite.
"""
import json
import re
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8794/prophet_lab"
LAB_SEG = '.lab-seg button[data-mode="lab"]'
LIVE_SEG = '.lab-seg button[data-mode="live"]'

FAILS: list[str] = []
PASSES: list[str] = []


def ck(cid, ok, msg=""):
    (PASSES if ok else FAILS).append(f"{cid}  {msg}")
    return ok


def enter_lab(page):
    el = page.query_selector(LAB_SEG)
    if el is None:
        raise SystemExit("verify: mode control missing — cannot enter LAB")
    el.click()
    page.wait_for_timeout(300)


def main():                                                    # noqa: C901
    with sync_playwright() as p:
        b = p.chromium.launch()

        # ── D1 · a fresh page ALWAYS defaults LIVE (LAB-0 §6.5, §7) ───────
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        st = pg.evaluate("""() => ({
            mode: document.documentElement.dataset.mode,
            lab: !!document.querySelector('.lab-plane'),
            cards: document.querySelectorAll('.pvcard').length,
            seg: !!document.querySelector('.lab-seg')
        })""")
        ck("D1 fresh-defaults-live", st["mode"] == "live" and not st["lab"] and st["cards"] > 0, str(st))
        ck("D1b control-present-for-operator", st["seg"], "mode control mounted")
        cold_cards = st["cards"]

        # ── D2 · the mode control costs the LIVE composition NOTHING ──────
        #    The Lab may not buy its own affordance with the product's layout
        #    budget, so the control mounts inside the existing status cluster.
        geo = pg.evaluate("""() => {
            const l = document.querySelector('.ladder-block') || document.querySelector('.mx-ladder');
            const s = document.querySelector('.bh-stamp .lab-seg');
            return {ladderTop: l ? Math.round(l.getBoundingClientRect().top) : null,
                    segInStamp: !!s};
        }""")
        ck("D2 control-in-status-cluster", geo["segInStamp"],
           f"ladder top {geo['ladderTop']}px — control adds no row")
        pg.close()

        # ── D3 · operator-only: no entitlement, no affordance, and the page
        #        is the R4 board and nothing else ───────────────────────────
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{BASE}/?chrome=0&op=0", wait_until="networkidle")
        # scoped to #board: the product surface. The mockup harness bar lives
        # outside it and is not part of what a reader is served.
        st = pg.evaluate("""() => ({
            seg: document.querySelectorAll('#board .lab-seg').length,
            lab: document.querySelectorAll('#board [class*="lab-"]').length,
            cards: document.querySelectorAll('.pvcard').length
        })""")
        ck("D3 no-affordance-without-entitlement", st["seg"] == 0 and st["lab"] == 0, str(st))
        ck("D3b board-unchanged-without-entitlement", st["cards"] == cold_cards,
           f"{st['cards']} cards == {cold_cards}")
        pg.close()

        # ── the LAB plane ─────────────────────────────────────────────────
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        enter_lab(pg)
        lab = pg.evaluate("""() => {
            const vis = s => [...document.querySelectorAll(s)].filter(n => n.offsetParent !== null);
            return {
                mode: document.documentElement.dataset.mode,
                eyebrow: vis('.lab-eyebrow').length,
                segs: vis('.lab-seg').length,
                rows: document.querySelectorAll('.lab-row').length,
                seeds: document.querySelectorAll('.lab-row--seed').length,
                pvcards: vis('.pvcard').length,
                ladder: vis('.ladder-block').length,
                stamp: vis('.bh-stamp').length,
                stale: vis('.nb-stale-note').length,
                otherSec: vis('.mx-sec').filter(n => n.id !== 'setups').length,
                text: document.getElementById('board').innerText,
                html: document.getElementById('board').innerHTML
            };
        }""")

        # D4 — the principal grid is the Lab's; no Prophet SETUP CARD may stand
        # under the Lab label. (This is the half of R5's D4 that survives.)
        ck("D4 no-prophet-card-in-lab", lab["pvcards"] == 0, f"{lab['pvcards']} visible")

        # ── R5.1 / VTL-401 — THE MODE IS A REGION, NOT THE PAGE ───────────
        #    R5's D4b/D4c/D4d asserted the OPPOSITE of the law: they required
        #    the ladder, the page stamp and every other section to be HIDDEN,
        #    which is exactly the contract breach the R5 verdict found. They
        #    are replaced, not relaxed — the new checks fail if anything
        #    outside the principal grid disappears on mode entry.
        scope = pg.evaluate("""() => {
            const vis = q => [...document.querySelectorAll(q)].filter(n => n.offsetParent !== null);
            return {
              ladder: vis('.ladder-block').length,
              purpose: vis('.bh-purpose').length,
              stamp: vis('.bh-stamp').length,
              candidates: vis('#candidates').length,
              groups: vis('#groups').length,
              evidence: vis('#evidence, #record').length,
              hiddenSecs: [...document.querySelectorAll('.mx-sec')]
                  .filter(n => n.id !== 'setups' && n.offsetParent === null).map(n => n.id),
              region: vis('.lab-region').length,
              regionEnd: vis('.lab-region-end').length,
              ladhint: vis('.lab-ladhint').length
            };
        }""")
        ck("D4b ladder-survives-the-mode", scope["ladder"] == 1, str(scope))
        ck("D4c page-header-survives-the-mode",
           scope["purpose"] == 1 and scope["stamp"] == 1)
        ck("D4d plan-book-sections-survive-the-mode",
           scope["candidates"] == 1 and scope["groups"] == 1 and scope["evidence"] == 1
           and not scope["hiddenSecs"], f"hidden: {scope['hiddenSecs']}")
        # separation, which is what the ruling asks for INSTEAD of deletion
        ck("D4e lab-is-a-bounded-labelled-region",
           scope["region"] == 1 and scope["regionEnd"] == 1)
        ck("D4f ladder-says-where-a-click-lands", scope["ladhint"] == 1)
        # D5 — one control, one label. A hidden duplicate radiogroup is a defect.
        ck("D5 single-mode-control", lab["segs"] == 1, f"{lab['segs']} visible radiogroups")
        ck("D5b lab-state-announced", lab["eyebrow"] == 1 and lab["mode"] == "lab")

        # ── D6 · the seed law. A retrospective seed may NEVER carry a
        #        measured lead, and may never be missing its class chip. ────
        seed = pg.evaluate("""() => {
            const seeds = [...document.querySelectorAll('.lab-row--seed')];
            const live  = [...document.querySelectorAll('.lab-row--live')];
            return {
              seeds: seeds.length,
              // VISIBLE and non-empty, not merely present in the DOM. A
              // querySelector hit is not a disclosure: `hidden`, `display:none`
              // and an empty label all satisfy "the node exists" while
              // disclosing nothing — the vacuous-guard trap the R4 cycle
              // found twice and told the next cycle to re-check first.
              // R5.1 / VTL-408: the per-row seed chip is gone (23 repeats of a
              // constant below a divider that already said it). What replaces
              // it is the STICKY divider, so the label is present wherever it
              // applies. The check moves with the design: the divider must
              // exist, be sticky, and carry a visible class BADGE — not merely
              // a long string. R5.2 / PR51-1 added the badge requirement,
              // because "innerText is long enough" would have been satisfied by
              // the explanatory sentence alone, and the sentence is exactly the
              // part that is allowed to scroll away.
              markStickyLabelled: (() => {
                  const m = document.querySelector('.lab-mark');
                  if (!m || m.offsetParent === null) return false;
                  const chip = m.querySelector('.lab-cls--seed');
                  return getComputedStyle(m).position === 'sticky'
                      && !!chip && chip.offsetParent !== null
                      && chip.innerText.trim().length > 3
                      && m.innerText.trim().length > 12;
              })(),
              // the four structural channels that remain ON the seed row
              seedsWithAbsenceRail: seeds.filter(r => {
                  const l = r.querySelector('.lab-tl');
                  return l && l.offsetParent !== null && l.innerText.trim().length > 3;
              }).length,
              seedsWithMeasuredLead: seeds.filter(
                  r => r.querySelector('.lab-lead:not(.lab-lead--none)')).length,
              seedsWithClock: seeds.filter(r => /^\\d{1,2}:\\d{2}/.test(
                  (r.querySelector('.lab-t')||{}).textContent||'')).length,
              seedsDashedSpine: seeds.filter(r => getComputedStyle(
                  r.querySelector('.lab-when')).borderRightStyle === 'dashed').length,
              liveWithChip: live.filter(r => {
                  const c = r.querySelector('.lab-cls--live');
                  return c && c.offsetParent !== null && c.innerText.trim().length > 3;
              }).length,
              // a seed must never wear the live treatment, and vice versa
              seedsWearingLiveChip: seeds.filter(r => r.querySelector('.lab-cls--live')).length,
              liveSolidSpine: live.filter(r => getComputedStyle(
                  r.querySelector('.lab-when')).borderRightStyle === 'solid').length,
              live: live.length,
              leadSlots: document.querySelectorAll('.lab-lead').length,
              rows: document.querySelectorAll('.lab-row').length
            };
        }""")
        ck("D6 seed-never-shows-a-measured-lead", seed["seedsWithMeasuredLead"] == 0,
           f"{seed['seedsWithMeasuredLead']} of {seed['seeds']} seeds")
        ck("D6b seed-never-prints-a-sighting-time", seed["seedsWithClock"] == 0,
           f"{seed['seedsWithClock']} seeds printed a clock time")
        ck("D6c sticky-divider-carries-the-class-label", seed["markStickyLabelled"],
           "the divider replaced 23 per-row constants and must stay visible while they apply")
        ck("D6c1 every-seed-prints-its-absent-sighting-time",
           seed["seedsWithAbsenceRail"] == seed["seeds"],
           f"{seed['seedsWithAbsenceRail']}/{seed['seeds']}")
        ck("D6c2 no-seed-wears-the-live-treatment", seed["seedsWearingLiveChip"] == 0,
           f"{seed['seedsWearingLiveChip']} seeds painted as live sightings")
        # D6h — ANTI-VACUITY. Every seed check above measures the set selected by
        # .lab-row--seed, so a change that stopped emitting that class would make
        # all of them pass over an empty set while the honesty encoding silently
        # vanished. The class census is therefore pinned to the PAYLOAD, which is
        # the one thing a rendering bug cannot move. (Added in R5.1 after a
        # mutation aimed at D6c2 revealed the hole.)
        pay = pg.evaluate("""() => {
            const rows = window.PROPHET_LAB.rows;
            const ids = new Set(window.PROPHET_LAB.boards
                .find(b => b.id === 'lab-all-early-v1').rows);
            const sel = rows.filter(r => ids.has(r.id));
            return {seed: sel.filter(r => r.cls === 'seed').length,
                    live: sel.filter(r => r.cls === 'live_forward').length};
        }""")
        ck("D6h seed-live-class-census-matches-the-payload",
           seed["seeds"] == pay["seed"] and seed["live"] == pay["live"],
           f"rendered {seed['seeds']}/{seed['live']} vs payload {pay['seed']}/{pay['live']}")
        ck("D6d every-live-row-carries-its-class-chip",
           seed["liveWithChip"] == seed["live"], f"{seed['liveWithChip']}/{seed['live']}")
        # the distinction is STRUCTURAL, not only a badge: the spine changes
        ck("D6e seed-spine-is-dashed", seed["seedsDashedSpine"] == seed["seeds"],
           f"{seed['seedsDashedSpine']}/{seed['seeds']}")
        ck("D6f live-spine-is-solid", seed["liveSolidSpine"] == seed["live"],
           f"{seed['liveSolidSpine']}/{seed['live']}")
        # D6g — the lead slot is never simply BLANK. An empty slot reads as
        # "zero lead", which is a claim nobody made.
        ck("D6g lead-slot-always-filled", seed["leadSlots"] == seed["rows"],
           f"{seed['leadSlots']} slots / {seed['rows']} rows")

        # ── D6i · R5.2 / R52-D1 — THE CLASS ASSERTION IS PRINTED ONCE ─────
        #    VTL-408 removed the 23 per-row seed chips as a Law 4 violation, and
        #    R5.1 then kept printing "signal date / NOT A SIGHTING" on the same
        #    23 rows — so the constant survived the fix meant to remove it and
        #    only the chip changed. The rails now carry a UNIT LABEL ("signal
        #    date" / "first seen"), which differs by row class and says what the
        #    number above it is; the CLASS ASSERTION lives once, on the divider.
        #    Two halves, because either alone is gameable: the assertion appears
        #    exactly once in the stream, AND no row rail makes one.
        once = pg.evaluate("""() => {
            const stream = document.querySelector('.lab-stream');
            const rails = [...document.querySelectorAll('.lab-row--seed .lab-tl')];
            const claim = /not a sighting|非观测记录|from history|回溯记录/i;
            return {
              badges: stream ? stream.querySelectorAll('.lab-cls--seed').length : -1,
              railsAsserting: rails.filter(n => claim.test(n.innerText)).length,
              rails: rails.length,
              railText: rails.length ? rails[0].innerText.trim() : '',
              liveRail: (document.querySelector('.lab-row--live .lab-tl')||{}).innerText || ''
            };
        }""")
        ck("D6i class-assertion-printed-exactly-once", once["badges"] == 1,
           f"{once['badges']} class badges in the stream — a constant belongs once (Law 4)")
        ck("D6i2 no-row-rail-asserts-its-class", once["railsAsserting"] == 0,
           f"{once['railsAsserting']} of {once['rails']} seed rails repeat the class assertion")
        ck("D6i3 rails-are-unit-labels-that-differ-by-class",
           once["railText"] and once["liveRail"]
           and once["railText"].split("\n")[0] != once["liveRail"].split("\n")[0],
           f"seed rail {once['railText'].splitlines()[:1]} vs live rail "
           f"{once['liveRail'].splitlines()[:1]}")

        # ── D6c3 · BEHAVIOURAL — the divider actually PINS, deep in the region
        #    it governs. This is the check R5.1 needed and did not have.
        #
        #    R5.1 asserted `position: sticky` and shipped it inside
        #    `.lab-stream { overflow: hidden }`. Any overflow other than
        #    `visible` makes an element a scrollport, and a sticky child pins to
        #    its nearest scrollport — here, a list that can never scroll. So the
        #    pin was inert everywhere it mattered while `getComputedStyle(m)
        #    .position === 'sticky'` kept returning true. Measured on the R5.1
        #    artifact: at 1440 the mark sat 716px ABOVE the viewport with nine
        #    seed rows on screen and no worded class label anywhere on it.
        #
        #    A declaration cannot be trusted to describe a layout. This scrolls
        #    1,200px past the divider and reads its rect, so the whole defect
        #    class fails here: a scrollport ancestor, a changed `position`, a
        #    `top` that never resolves, a divider that stops being rendered.
        for vw, vh in ((1440, 900), (390, 844)):
            pgs = b.new_page(viewport={"width": vw, "height": vh})
            pgs.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
            enter_lab(pgs)
            rest = pgs.evaluate("""() => {
                const m = document.querySelector('.lab-mark');
                return m ? Math.round(m.getBoundingClientRect().top + window.scrollY) : null;
            }""")
            if rest is None:
                ck(f"D6c3 divider-pins-in-the-seed-region[{vw}]", False, "no .lab-mark rendered")
                pgs.close()
                continue
            pgs.evaluate(f"() => window.scrollTo(0, {rest} + 1200)")
            pgs.wait_for_timeout(260)
            deep = pgs.evaluate("""() => {
                const m = document.querySelector('.lab-mark');
                const h = window.innerHeight;
                const on = q => [...document.querySelectorAll(q)].filter(n => {
                    const r = n.getBoundingClientRect();
                    return r.bottom > 0 && r.top < h;
                }).length;
                const r = m.getBoundingClientRect();
                return {top: Math.round(r.top), seeds: on('.lab-row--seed'),
                        onScreen: r.bottom > 0 && r.top < h,
                        label: m.innerText.trim().replace(/\\s+/g, ' '),
                        y: Math.round(window.scrollY)};
            }""")
            ck(f"D6c3 divider-pins-in-the-seed-region[{vw}]",
               deep["seeds"] > 0 and deep["onScreen"] and abs(deep["top"]) <= 2
               and len(deep["label"]) > 12,
               f"scrolled to {deep['y']}px (divider rests at {rest}px); mark top "
               f"{deep['top']}px; {deep['seeds']} seed rows on screen; "
               f"label {deep['label'][:64]!r}")
            pgs.close()

        # ── D6c4 · R5.2 / R52-D1 — the pin CLEARS the sticky chrome above it ─
        #    `top: 0` is only correct on a route with no page header, and the
        #    production route ships the shared site nav. The controller measures
        #    the sticky chrome and binds --lab-mark-top, so the same component
        #    is right in both cases. This mockup's harness bar IS a sticky top:0
        #    element, so ?chrome=1 and ?chrome=0 are two different correct
        #    answers and both are asserted — a hardcoded 0 fails the first, a
        #    hardcoded header height fails the second.
        pgh = b.new_page(viewport={"width": 1440, "height": 900})
        pgh.goto(f"{BASE}/?chrome=1", wait_until="networkidle")
        enter_lab(pgh)
        chrome = pgh.evaluate("""() => {
            const bar = document.querySelector('.harness');
            const m = document.querySelector('.lab-mark');
            const restY = Math.round(m.getBoundingClientRect().top + window.scrollY);
            window.scrollTo(0, restY + 1200);
            return new Promise(r => setTimeout(() => r({
                barH: bar ? Math.round(bar.getBoundingClientRect().height) : 0,
                barSticky: bar ? getComputedStyle(bar).position : null,
                markTop: Math.round(document.querySelector('.lab-mark').getBoundingClientRect().top),
                bound: getComputedStyle(document.documentElement)
                        .getPropertyValue('--lab-mark-top').trim()
            }), 220));
        }""")
        ck("D6c4 pin-clears-the-sticky-chrome-above-it",
           chrome["barSticky"] == "sticky" and chrome["barH"] > 0
           and abs(chrome["markTop"] - chrome["barH"]) <= 2,
           f"harness bar {chrome['barH']}px ({chrome['barSticky']}), mark pinned at "
           f"{chrome['markTop']}px, --lab-mark-top={chrome['bound']!r} — a hardcoded "
           f"top:0 would slide the divider under the page header")
        pgh.close()

        # ── D24 · R5.2 / R52-D2 — one COMPLETE observation above the 390 fold ─
        #    R5.1 returned none: the first row began at 1,009px and stands 294px
        #    tall in an 844px viewport. The ladder (R51-M1) and the six wrapped
        #    selectors (C4) are frozen and account for 432px of that, so the
        #    remedy is the Lab's own preamble plus LANDING the region on flip —
        #    which is why this check drives the real control instead of loading
        #    a URL: the landing only happens on a deliberate mode flip, exactly
        #    as the product behaves.
        for lg in ("en", "zh"):
            pgf = b.new_page(viewport={"width": 390, "height": 844})
            pgf.goto(f"{BASE}/?chrome=0&lang={lg}", wait_until="networkidle")
            enter_lab(pgf)
            fold = pgf.evaluate("""() => {
                const vh = window.innerHeight, y = window.scrollY;
                const whole = [...document.querySelectorAll('.lab-row')].filter(n => {
                    const r = n.getBoundingClientRect();
                    return r.top >= -1 && r.bottom <= vh + 1;
                });
                const seg = document.querySelector('.lab-seg');
                const first = document.querySelector('.lab-row');
                return {
                  whole: whole.length,
                  firstH: first ? Math.round(first.getBoundingClientRect().height) : null,
                  firstTop: first ? Math.round(first.getBoundingClientRect().top) : null,
                  controlVisible: seg ? (() => { const r = seg.getBoundingClientRect();
                      return r.bottom > 0 && r.top < vh; })() : false,
                  y: Math.round(y)
                };
            }""")
            ck(f"D24 one-whole-observation-above-the-390-fold[{lg}]", fold["whole"] >= 1,
               f"{fold['whole']} complete rows in view; first row top {fold['firstTop']}px "
               f"h {fold['firstH']}px at scrollY {fold['y']}")
            # landing may not cost the reader the control they just pressed
            ck(f"D24b mode-control-stays-in-view-after-landing[{lg}]", fold["controlVisible"],
               "the flip must not scroll its own control off screen")
            pgf.close()

        # ── D24c · the landing is REVERSIBLE — LAB->LIVE restores the scroll ──
        #    An excursion that moves the page has to put it back, or "flip back
        #    to Live" silently costs the reader their place in the plan book.
        #    The start position is 40px and not something larger for a reason
        #    that is about the PRODUCT, not the test: at 390 the LIVE mode
        #    control sits in the page status cluster at ~47-68px, so a reader
        #    can only press it while the page is near the top. (A first pass at
        #    120px measured nothing — the driver scrolls a click target into
        #    view, so the flip started from 0 and "restored" 0 correctly.)
        pgr = b.new_page(viewport={"width": 390, "height": 844})
        pgr.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        pgr.evaluate("() => window.scrollTo(0, 40)")
        pgr.wait_for_timeout(150)
        before_y = pgr.evaluate("() => Math.round(window.scrollY)")
        pgr.click(LAB_SEG)
        pgr.wait_for_timeout(400)
        lab_y = pgr.evaluate("() => Math.round(window.scrollY)")
        pgr.click(LIVE_SEG)
        pgr.wait_for_timeout(800)
        after_y = pgr.evaluate("() => Math.round(window.scrollY)")
        ck("D24c landing-is-reversible", lab_y > before_y and abs(after_y - before_y) <= 2,
           f"scrollY {before_y} -> LAB {lab_y} -> LIVE {after_y}")
        pgr.close()

        # ── D7 · plain words at the glance tier; exact identity on the
        #        receipt. Both halves, because deleting the slug would also
        #        pass a check that only looked for its absence. ─────────────
        SLUGS = ["G0_GREY_DOT", "C1_1D_LIVE_WASHOUT", "C2_1D_TURN",
                 "c2a_kd_cross", "c2b_k_slope", "c2c_higher_k_low",
                 "c2d_hist_trough", "c2e_hist_curvature", "c2f_rebound_atr",
                 "lab-g0-v1", "lab-c1-v1", "lab-all-early-v1",
                 "retrospective_seed", "live_forward", "evidence_eligible",
                 "signal_known_ts", "observation_class"]
        leaked = [s for s in SLUGS if s in lab["text"]]
        ck("D7 no-machine-identity-at-glance-tier", not leaked, f"leaked: {leaked}")
        rc = pg.evaluate("""() => {
            const a = [...document.querySelectorAll('[data-tip-rc-en]')]
                       .map(n => n.getAttribute('data-tip-rc-en')).join(' | ');
            return a;
        }""")
        for want in ["G0_GREY_DOT@1", "C1_1D_LIVE_WASHOUT@1", "C2_1D_TURN@1",
                     "c2a_kd_cross", "retrospective_seed", "live_forward",
                     "detector_id = null"]:
            ck(f"D7b receipt-preserves[{want}]", want in rc)
        # D7c — the identity must survive ON THE ROW, not merely somewhere on
        # the page. The board selectors also carry detector ids, so a page-wide
        # substring test passes even after every per-row receipt is deleted.
        exrc = pg.evaluate("""() => [...document.querySelectorAll('.lab-ex')]
            .map(n => (n.getAttribute('data-tip-rc-en')||''))""")
        ck("D7c every-reading-carries-its-own-identity",
           exrc and all(("G0_GREY_DOT@1" in s or "C1_1D_LIVE_WASHOUT@1" in s
                         or ("C2_1D_TURN@1" in s and "/" in s)) for s in exrc),
           f"{sum(1 for s in exrc if not s)} of {len(exrc)} chips carry no receipt")

        # ── D8 · expert identities are never flattened
        #        (DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED) ─────────────────
        with open(__file__.rsplit("/tools/", 1)[0] + "/lab-data.js", encoding="utf-8") as fh:
            raw = fh.read()
        DATA = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        by_id = {r["id"]: r for r in DATA["rows"]}
        chips = pg.evaluate("""() => [...document.querySelectorAll('.lab-row')]
            .map(r => [r.dataset.obs, r.querySelectorAll('.lab-ex').length])""")
        bad = [(i, n, len(by_id[i]["ex"])) for i, n in chips if n != len(by_id[i]["ex"])]
        ck("D8 one-chip-per-expert-never-merged", not bad, f"mismatched: {bad[:4]}")
        multi = [i for i, n in chips if n > 1]
        ck("D8b multi-expert-rows-exist", len(multi) >= 3, f"{len(multi)} rows carry >1 reading")

        # ── D9 · the frozen board contract (LAB-0 §3) ─────────────────────
        WANT = ["lab-g0-v1", "lab-c1-v1", "lab-c2a-v1", "lab-c2-variants-v1",
                "lab-g0-c2a-v1", "lab-all-early-v1"]
        got = [x["id"] for x in DATA["boards"]]
        ck("D9 six-boards-exactly-as-frozen", got == WANT, str(got))
        btns = pg.evaluate("""() => [...document.querySelectorAll('[data-lab-board]')]
            .map(b => b.getAttribute('data-lab-board'))""")
        ck("D9b all-six-selectable", btns == WANT, str(btns))
        # C3/C5 are excluded from the union board in V1
        c35 = [e["exp"] for r in DATA["rows"] for e in r["ex"]
               if e["exp"].startswith(("c3", "c5"))]
        ck("D9c c3-c5-excluded-in-v1", not c35, str(c35[:4]))
        # the intersection board mints nothing and declares no detector
        ck("D9d intersection-declares-no-detector",
           "detector_id = null" in rc, "on the board's own receipt")

        # ── D10 · sort law: newest first, one stream ──────────────────────
        order = pg.evaluate("""() => [...document.querySelectorAll('.lab-row')]
            .map(r => r.dataset.obs)""")
        keys = [by_id[i]["sort"] for i in order]
        ck("D10 newest-first", keys == sorted(keys, reverse=True), "sort_ts non-increasing")
        ck("D10b sort-basis-is-stated",
           "Newest first" in lab["text"] or "newest first" in lab["text"])

        # ── D11 · zero authority, disclosed on the surface ────────────────
        ck("D11 authority-block-all-false",
           all(v is False for v in DATA["authority"].values()), str(DATA["authority"]))
        # R5.1 / VTL-412: the stance line and the authority line were merged, so
        # the glance tier carries ONE sentence that does both jobs.
        ck("D11b authority-stated-at-glance",
           "ranks, sizes, or changes a Prophet plan" in lab["text"])

        # ── D12 · house copy law ──────────────────────────────────────────
        #    "validated" is matched with a negative lookbehind: the RULED
        #    lifecycle word "Invalidated" contains it as a substring, and a
        #    naive `in` test flags a word the J9C-J10 ruling requires the page
        #    to print. A check that fires on compliant copy trains people to
        #    ignore it. (Found by the R5.1 LIVE-view sweep, which is the first
        #    time the scan ever ran over a page carrying the lexicon.)
        low = lab["text"].lower()
        for banned in ["falsif", "refut", "证伪", "blocked_data",
                       "prereg", "gauntlet", "k-of-n"]:
            ck(f"D12 no-banned-copy[{banned}]", banned not in low)
        ck("D12 no-banned-copy[validated]",
           re.search(r"(?<!in)validated", low) is None)
        ck("D12b stance-present", "don’t chase" in low or "don't chase" in low)
        pg.close()

        # ── C3 · COPY-LAW COVERAGE — ZH, ALL SIX BOARDS, AND THE LIVE VIEW ─
        #    R5 ran the slug-leak and banned-vocabulary scans on ONE board in
        #    ONE language and never on LIVE, so the checks proved a property of
        #    a single view rather than of the surface. The sweep below is the
        #    correction: 6 boards x 2 languages in LAB, plus both languages in
        #    LIVE, with both scans applied to every one of them.
        BANNED = ["falsif", "refut", "证伪", "blocked_data",
                  "prereg", "gauntlet", "k-of-n"]
        leaks, banned_hits, views = [], [], 0
        for lg in ("en", "zh"):
            # LIVE first — the mode R5 never scanned at all
            pgv = b.new_page(viewport={"width": 1440, "height": 900})
            pgv.goto(f"{BASE}/?chrome=0&lang={lg}", wait_until="networkidle")
            txt = pgv.evaluate("() => document.getElementById('board').innerText")
            views += 1
            leaks += [f"live/{lg}:{s}" for s in SLUGS if s in txt]
            banned_hits += [f"live/{lg}:{w}" for w in BANNED if w in txt.lower()]
            if re.search(r"(?<!in)validated", txt.lower()):
                banned_hits.append(f"live/{lg}:validated")
            for bid in WANT:
                pgv.goto(f"{BASE}/?chrome=0&lang={lg}&board={bid}", wait_until="networkidle")
                el = pgv.query_selector(LAB_SEG)
                if el is None:
                    FAILS.append(f"C3 sweep  {bid}/{lg}: mode control missing")
                    continue
                el.click()
                pgv.wait_for_timeout(260)
                txt = pgv.evaluate("() => document.getElementById('board').innerText")
                views += 1
                leaks += [f"{bid}/{lg}:{s}" for s in SLUGS if s in txt]
                banned_hits += [f"{bid}/{lg}:{w}" for w in BANNED if w in txt.lower()]
                if re.search(r"(?<!in)validated", txt.lower()):
                    banned_hits.append(f"{bid}/{lg}:validated")
            pgv.close()
        ck("C3 no-slug-leak-across-every-view", not leaks, f"{views} views; leaks: {leaks[:6]}")
        ck("C3b no-banned-vocab-across-every-view", not banned_hits,
           f"{views} views; hits: {banned_hits[:6]}")
        ck("C3c sweep-covered-both-modes-both-languages-all-six-boards", views == 14,
           f"{views} views scanned (expected 2 LIVE + 12 LAB)")
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        enter_lab(pg)

        # ── D13 · the Lab spark carries no stance ink ─────────────────────
        ck("D13 no-stance-chip-in-lab", ".pv-chip" not in lab["html"])
        stroke = pg.evaluate("""() => {
            const s = document.querySelector('.lab-spark svg path, .lab-spark svg polyline');
            return s ? getComputedStyle(s).stroke : null;
        }""")
        up = pg.evaluate("() => getComputedStyle(document.body).getPropertyValue('--up').trim()")
        ck("D13b spark-is-not-direction-ink", stroke is not None and up not in (stroke or ""),
           f"stroke {stroke}")
        pg.close()

        # ══ R5.1 CHECKS ══════════════════════════════════════════════════
        # ── D19 · VTL-403 — the lead is symmetric and signed ──────────────
        pg2 = b.new_page(viewport={"width": 1440, "height": 900})
        pg2.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        enter_lab(pg2)
        ld = pg2.evaluate("""() => {
            const rows = [...document.querySelectorAll('.lab-row')];
            const cs = n => n ? getComputedStyle(n) : null;
            const fav = document.querySelector('.lab-lead--measured:not(.lab-lead--adverse)');
            const adv = document.querySelector('.lab-lead--adverse');
            const tk  = document.querySelector('.lab-tk');
            return {
              measured: document.querySelectorAll('.lab-lead--measured').length,
              adverse: document.querySelectorAll('.lab-lead--adverse').length,
              favInk: fav ? cs(fav).color : null,
              advInk: adv ? cs(adv).color : null,
              favBg: fav ? cs(fav).backgroundColor : null,
              favWeight: fav ? cs(fav).fontWeight : null,
              tkWeight: tk ? cs(tk).fontWeight : null,
              advText: adv ? adv.innerText : '',
              slots: document.querySelectorAll('.lab-lead').length,
              rows: rows.length
            };
        }""")
        # the adverse branch must EXIST and carry a magnitude, not a category
        ck("D19 adverse-lead-is-rendered", ld["adverse"] >= 1, str(ld["advText"]))
        ck("D19b adverse-lead-carries-a-magnitude",
           any(c.isdigit() for c in ld["advText"]), ld["advText"])
        # THE SYMMETRY LAW: a measurement is a measurement. Favourable and
        # adverse share one ink; only the sentence changes.
        ck("D19c favourable-and-adverse-share-one-ink",
           ld["favInk"] is not None and ld["favInk"] == ld["advInk"],
           f"{ld['favInk']} vs {ld['advInk']}")
        # and it must not be the loudest thing in the row
        ck("D19d favourable-lead-has-no-fill",
           ld["favBg"] in ("rgba(0, 0, 0, 0)", "transparent"), str(ld["favBg"]))
        ck("D19e favourable-lead-does-not-out-ink-the-ticker",
           int(ld["favWeight"] or 0) < int(ld["tkWeight"] or 0),
           f"lead {ld['favWeight']} vs ticker {ld['tkWeight']}")
        # Math.abs may not stand between the payload and the branch again
        with open(__file__.rsplit("/tools/", 1)[0] + "/lab.js", encoding="utf-8") as fh:
            js_src = fh.read()
        # comments are stripped first: the source COMMENT explains why the call
        # was removed and naming it there is documentation, not a defect. A
        # check that cannot tell code from prose punishes the explanation.
        js_code = re.sub(r"/\*.*?\*/", "", js_src, flags=re.S)
        ck("D19f no-abs-on-the-lead", "Math.abs(r.lead)" not in js_code)
        ck("D19g every-row-still-fills-its-lead-slot",
           ld["slots"] == ld["rows"], f"{ld['slots']}/{ld['rows']}")

        # ── D21 · VTL-407 — count discipline, responsive to the filter ────
        def counts(page):
            return page.evaluate("""() => ({
                showing: (document.querySelector('.lab-showing')||{}).innerText || '',
                split: (document.querySelector('.lab-split')||{}).innerText || '',
                rows: document.querySelectorAll('.lab-row').length
            })""")
        c_all = counts(pg2)
        ck("D21 rendered-count-is-stated", str(c_all["rows"]) in c_all["showing"],
           f"{c_all['showing']!r} vs {c_all['rows']} rows")
        pg2.click('[data-lab-cls="live"]')
        pg2.wait_for_timeout(250)
        c_live = counts(pg2)
        ck("D21b count-follows-the-filter", str(c_live["rows"]) in c_live["showing"]
           and c_live["rows"] < c_all["rows"], f"{c_live['showing']!r} / {c_live['rows']} rows")
        # the split is computed from the FILTERED set, not the whole board
        ck("D21c split-follows-the-filter", "0" in c_live["split"],
           f"{c_live['split']!r} — seeds must read 0 under a live-only filter")
        pg2.click('[data-lab-cls="all"]')
        pg2.wait_for_timeout(250)
        pg2.close()

        # ── D18 · VTL-402 — unknown is not zero ───────────────────────────
        def pills(page):
            return page.evaluate("""() => ({
                nums: [...document.querySelectorAll('.lab-sel .lab-n')].map(n => n.innerText.trim()),
                unk: document.querySelectorAll('.lab-sel .lab-n--unk').length,
                note: !!document.querySelector('.lab-unknote'),
                dashed: [...document.querySelectorAll('.lab-sel .lab-n')]
                        .filter(n => getComputedStyle(n).borderStyle === 'dashed').length
            })""")
        pdn = pdempty = None
        for feed, want in (("down", "unknown"), ("empty", "zero")):
            pg3 = b.new_page(viewport={"width": 1440, "height": 900})
            pg3.goto(f"{BASE}/?chrome=0&feed={feed}", wait_until="networkidle")
            enter_lab(pg3)
            p = pills(pg3)
            if feed == "down":
                pdn = p
                ck("D18 down-prints-no-literal-zero", "0" not in p["nums"], str(p["nums"]))
                ck("D18b down-marks-every-count-unknown",
                   p["unk"] == 6 and p["dashed"] == 6, str(p))
                ck("D18c down-says-what-the-dash-means", p["note"])
            else:
                pdempty = p
                ck("D18d empty-prints-a-real-zero",
                   p["nums"] == ["0"] * 6 and p["unk"] == 0, str(p))
                ck("D18e empty-claims-no-unknown", not p["note"])
            pg3.close()
        # and the two states must not be pixel-identical at the pill row, which
        # is exactly what the R5 defect was
        ck("D18f unknown-and-zero-are-distinguishable",
           pdn["nums"] != pdempty["nums"], f"{pdn['nums']} vs {pdempty['nums']}")

        # ── D20 · VTL-411 (C4) — all six boards reachable at 390 ──────────
        pg4 = b.new_page(viewport={"width": 390, "height": 844})
        pg4.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        enter_lab(pg4)
        sel = pg4.evaluate("""() => {
            const bs = [...document.querySelectorAll('[data-lab-board]')];
            const w = document.documentElement.clientWidth;
            return {
              n: bs.length,
              offscreen: bs.filter(b => { const r = b.getBoundingClientRect();
                  return r.width === 0 || r.right > w + 1 || r.left < -1; })
                  .map(b => b.getAttribute('data-lab-board')),
              clipped: bs.filter(b => { const p = b.parentElement.parentElement;
                  return p.scrollWidth > p.clientWidth + 1; }).length,
              minH: Math.min(...bs.map(b => b.getBoundingClientRect().height))
            };
        }""")
        ck("D20 all-six-boards-onscreen-at-390",
           sel["n"] == 6 and not sel["offscreen"], f"offscreen: {sel['offscreen']}")
        ck("D20b no-hidden-scroller-at-390", sel["clipped"] == 0,
           "the strip must not hide boards behind an unaffordanced scroll")
        ck("D20c lab-selectors-clear-the-touch-floor-at-390", sel["minH"] >= 40,
           f"min height {sel['minH']}px")
        pg4.close()

        # ── D20d · R5.2 / PR51-2 — and JUST ABOVE the retired breakpoint ──
        #    R5.1 scoped the wrap to max-width:980px on the claim that "above
        #    980w all six fit on one line anyway". They clear 981w by 22px, and
        #    the pill widths grow with the COUNTS, which this surface does not
        #    control — so the claim was a measurement of one fixture, not a
        #    property of the layout, and the checks only ever looked at 390.
        #    The wrap is unconditional now; this pins the band that was dark.
        pg4b = b.new_page(viewport={"width": 1000, "height": 900})
        pg4b.goto(f"{BASE}/?chrome=0", wait_until="networkidle")
        enter_lab(pg4b)
        sel2 = pg4b.evaluate("""() => {
            const bs = [...document.querySelectorAll('[data-lab-board]')];
            const w = document.documentElement.clientWidth;
            return {
              n: bs.length,
              offscreen: bs.filter(b => { const r = b.getBoundingClientRect();
                  return r.width === 0 || r.right > w + 1 || r.left < -1; })
                  .map(b => b.getAttribute('data-lab-board')),
              clipped: bs.filter(b => { const p = b.parentElement.parentElement;
                  return p.scrollWidth > p.clientWidth + 1; }).length
            };
        }""")
        ck("D20d all-six-boards-onscreen-at-1000",
           sel2["n"] == 6 and not sel2["offscreen"] and sel2["clipped"] == 0,
           f"offscreen: {sel2['offscreen']}, clipped: {sel2['clipped']}")
        pg4b.close()

        # ── D23 · VTL-409 — the error state retries and dates itself ──────
        pg5 = b.new_page(viewport={"width": 1440, "height": 900})
        pg5.goto(f"{BASE}/?chrome=0&feed=down", wait_until="networkidle")
        enter_lab(pg5)
        err = pg5.evaluate("""() => ({
            retry: !!document.querySelector('[data-lab-retry]'),
            escape: !!document.querySelector('.lab-state-act[data-mode="live"]'),
            asof: (document.querySelector('.lab-stamp .dtp-asof')||{}).innerText || ''
        })""")
        ck("D23 error-offers-retry", err["retry"])
        ck("D23b error-names-what-still-works", err["escape"])
        ck("D23c error-keeps-the-last-known-good-stamp",
           any(c.isdigit() for c in err["asof"]), f"{err['asof']!r}")
        pg5.close()

        # ── D14 · every degraded Lab state stays visibly LAB ──────────────
        for feed in ("empty", "stale", "down"):
            pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.goto(f"{BASE}/?chrome=0&feed={feed}", wait_until="networkidle")
            enter_lab(pg)
            s = pg.evaluate("""() => {
                const vis = q => [...document.querySelectorAll(q)].filter(n => n.offsetParent !== null);
                return {mode: document.documentElement.dataset.mode,
                        eyebrow: vis('.lab-eyebrow').length,
                        pvcards: vis('.pvcard').length,
                        plane: vis('.lab-plane').length,
                        sw: document.documentElement.scrollWidth,
                        cw: document.documentElement.clientWidth};
            }""")
            ck(f"D14 stays-lab[{feed}]",
               s["mode"] == "lab" and s["eyebrow"] == 1 and s["plane"] == 1, str(s))
            ck(f"D14b no-live-fallback[{feed}]", s["pvcards"] == 0,
               f"{s['pvcards']} Prophet cards under a LAB label")
            ck(f"D14c no-h-scroll-390[{feed}]", s["sw"] <= s["cw"], f"{s['sw']}>{s['cw']}")
            pg.close()

        # ── D15 · LAB → LIVE re-derives; it does not restore a snapshot ───
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{BASE}/?chrome=1", wait_until="networkidle")
        n0 = pg.evaluate("() => document.querySelectorAll('.pvcard').length")
        pg.click(LAB_SEG)
        pg.wait_for_timeout(300)
        pg.click(LIVE_SEG)
        pg.wait_for_timeout(700)
        rt = pg.evaluate("""() => ({
            mode: document.documentElement.dataset.mode,
            labNodes: document.querySelectorAll('.lab-plane, .lab-row, .lab-band').length,
            cards: document.querySelectorAll('.pvcard').length,
            ladder: !!document.querySelector('.ladder-block'),
            stamp: !!document.querySelector('.bh-stamp'),
            seg: document.querySelectorAll('.lab-seg').length,
            harness: (document.querySelector('.lab-hstamp')||{}).innerText || ''
        })""")
        ck("D15 round-trip-restores-live-exactly",
           rt["mode"] == "live" and rt["cards"] == n0 and rt["ladder"] and rt["stamp"], str(rt))
        ck("D15b nothing-of-the-lab-survives", rt["labNodes"] == 0, f"{rt['labNodes']} nodes")
        ck("D15c control-survives-the-repaint", rt["seg"] == 1)
        ck("D15d live-was-re-derived-not-restored", "repaints: 1" in rt["harness"],
           rt["harness"].replace("\n", " "))
        pg.close()

        # ── D22 · C1 — RE-DERIVATION, PROVEN INDEPENDENTLY OF THE COUNTER ──
        #    R5 pinned "LAB->LIVE re-derives, never restores" only with the
        #    controller's OWN self-reported repaint counter, and the mutation
        #    that attacked it broke the counter rather than the mechanism. A
        #    self-report is not evidence. This plants a SENTINEL attribute on a
        #    real card before entering LAB: a genuine re-derivation destroys the
        #    node, so the sentinel must be gone afterwards; a cached-and-restored
        #    innerHTML brings it back verbatim. The counter is not consulted.
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(f"{BASE}/?chrome=1", wait_until="networkidle")
        planted = pg.evaluate("""() => {
            const c = document.querySelector('.pvcard');
            if (!c) return false;
            c.setAttribute('data-r51-sentinel', '1');
            return true;
        }""")
        ck("D22a sentinel-planted", planted, "no .pvcard to plant on")
        pg.click(LAB_SEG)
        pg.wait_for_timeout(300)
        ck("D22b sentinel-gone-while-in-lab",
           pg.evaluate("() => document.querySelectorAll('[data-r51-sentinel]').length") == 0)
        pg.click(LIVE_SEG)
        pg.wait_for_timeout(700)
        sent = pg.evaluate("""() => ({
            sentinels: document.querySelectorAll('[data-r51-sentinel]').length,
            cards: document.querySelectorAll('.pvcard').length
        })""")
        ck("D22 live-is-re-derived-sentinel-does-not-return",
           sent["sentinels"] == 0 and sent["cards"] > 0,
           f"{sent} — a returning sentinel means the DOM was restored, not re-derived")
        pg.close()

        # ── D16 · 390w has no horizontal scroll in ANY captured Lab view ──
        for q in ("", "&cls=seed", "&board=lab-c2-variants-v1", "&lang=zh",
                  "&theme=light&lang=zh"):
            pg = b.new_page(viewport={"width": 390, "height": 844})
            pg.goto(f"{BASE}/?chrome=0{q}", wait_until="networkidle")
            enter_lab(pg)
            o = pg.evaluate("() => ({sw: document.documentElement.scrollWidth,"
                            " cw: document.documentElement.clientWidth})")
            ck(f"D16 no-h-scroll-390[{q or 'default'}]", o["sw"] <= o["cw"], str(o))
            pg.close()

        # ── D17 · bilingual parity: both languages ship, neither leaks ────
        #    R5.2 / PR51-5 — THE PROBES WERE DEAD STRINGS. R5.1 scanned the ZH
        #    view for "Live sighting" and "Seed · history", both retired by
        #    VTL-405/VTL-408 in the same revision. A leak test looking for words
        #    the EN page no longer prints cannot fail, and it had been reporting
        #    green over an unguarded surface. Two repairs: the probes are current
        #    vocabulary, and each one is asserted PRESENT in EN before its
        #    absence in ZH is credited — so the next time the vocabulary moves,
        #    the check fails loudly instead of quietly ceasing to measure. This
        #    is the same rot class the R4 README told this cycle to re-check.
        EN_PROBES = ["Seen first-hand", "From history", "Not on the board",
                     "Lead not measurable", "Nothing below this line was seen first-hand",
                     "same day"]
        for lg, probe in (("en", "Watch"), ("zh", "观察")):
            pg = b.new_page(viewport={"width": 1440, "height": 900})
            pg.goto(f"{BASE}/?chrome=0&lang={lg}", wait_until="networkidle")
            enter_lab(pg)
            txt = pg.evaluate("() => document.getElementById('board').innerText")
            ck(f"D17 renders[{lg}]", probe in txt)
            if lg == "en":
                # anti-vacuity: a probe the EN surface never prints proves nothing
                for en_only in EN_PROBES:
                    ck(f"D17c probe-is-live-vocabulary[{en_only}]", en_only in txt,
                       "a retired probe makes the ZH leak test vacuous")
            else:
                # no raw EN state token dropped into ZH copy
                for en_only in EN_PROBES:
                    ck(f"D17b no-en-leak-in-zh[{en_only}]", en_only not in txt)
            pg.close()

        b.close()

    print("\n".join(PASSES))
    if FAILS:
        print("\nFAILED:")
        print("\n".join(FAILS))
    print(f"\n{len(PASSES)}/{len(PASSES) + len(FAILS)} checks pass")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
