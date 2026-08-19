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

        # D4 — no LIVE content may stand under a LAB label
        ck("D4 no-prophet-card-in-lab", lab["pvcards"] == 0, f"{lab['pvcards']} visible")
        ck("D4b no-plan-book-ladder-in-lab", lab["ladder"] == 0)
        ck("D4c no-plan-book-stamp-in-lab", lab["stamp"] == 0 and lab["stale"] == 0)
        ck("D4d no-other-live-sections-in-lab", lab["otherSec"] == 0, f"{lab['otherSec']} sections")
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
              seedsWithChip: seeds.filter(r => {
                  const c = r.querySelector('.lab-cls--seed');
                  return c && c.offsetParent !== null && c.innerText.trim().length > 3;
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
        ck("D6c every-seed-carries-its-class-chip",
           seed["seedsWithChip"] == seed["seeds"], f"{seed['seedsWithChip']}/{seed['seeds']}")
        ck("D6c2 no-seed-wears-the-live-treatment", seed["seedsWearingLiveChip"] == 0,
           f"{seed['seedsWearingLiveChip']} seeds painted as live sightings")
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
        ck("D11b authority-stated-at-glance",
           "Observation only" in lab["text"])

        # ── D12 · house copy law ──────────────────────────────────────────
        low = lab["text"].lower()
        for banned in ["falsif", "refut", "证伪", "validated", "blocked_data",
                       "prereg", "gauntlet", "k-of-n"]:
            ck(f"D12 no-banned-copy[{banned}]", banned not in low)
        ck("D12b stance-present", "don’t chase" in low or "don't chase" in low)

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
        for lg, probe in (("en", "Watch"), ("zh", "观察")):
            pg = b.new_page(viewport={"width": 1440, "height": 900})
            pg.goto(f"{BASE}/?chrome=0&lang={lg}", wait_until="networkidle")
            enter_lab(pg)
            txt = pg.evaluate("() => document.getElementById('board').innerText")
            ck(f"D17 renders[{lg}]", probe in txt)
            if lg == "zh":
                # no raw EN state token dropped into ZH copy
                for en_only in ["Live sighting", "Seed · history", "Not on the board"]:
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
