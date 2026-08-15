#!/usr/bin/env python3
"""W8 Radar reference-integrity checks.

Static source checks always run. Playwright checks run when --url is given
(or RADAR_REF_URL is set) and playwright is importable.

Exit 0 only if every armed check passed.
A check that cannot detect its mutation is not evidence — see mutation_test.py.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]

fails: list[str] = []
checks: list[tuple[bool, str, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    checks.append((bool(cond), name, detail))
    if not cond:
        fails.append(f"{name} — {detail}")


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def static_checks() -> None:
    html = _read("index.html")
    css = _read("radar.css")
    js = _read("radar.js")
    data = _read("radar-data.js")
    notes = _read("DESIGN_NOTES.md")
    pin = _read("PINNED_PROPHET_REFERENCE.md")

    # R1 — reference assets must not be production UI
    prod_j2 = REPO / "templates" / "entry_radar.html.j2"
    prod_site = REPO / "site" / "entry_radar.html"
    ok("R1 no-production-j2", not prod_j2.exists(), str(prod_j2))
    ok("R1b no-production-site", not prod_site.exists(), str(prod_site))
    ok("R1c reference-banner-html", 'data-reference-banner="1"' in html, "banner hook missing")
    ok("R1d not-production-copy", "NOT PRODUCTION" in html and "REFERENCE" in html, "banner copy")

    # R2 — pinned Prophet SHA recorded (the actual current R4 pin)
    ok("R2 pin-merge", "168a9be006914441051cff393927ce465e39138e" in pin, "R4 merge SHA")
    ok("R2b pin-tree", "d540f493a097cb37f3f91e4c7bc81a39b876d069" in pin, "ref tree SHA")
    ok("R2c pin-in-data", "168a9be006914441051cff393927ce465e39138e" in data, "data pin")

    # R3 — expert identities not flattened
    for ex in ("G0", "C1", "C2", "C3", "C5"):
        ok(f"R3 expert-{ex}-data", f'id: "{ex}_' in data or f'"{ex}_' in data, ex)
        ok(f"R3b expert-{ex}-chip", f'data-expert="' in js and ex in data, ex)
    ok("R3h g0-map-key", re.search(r'\bG0:\s*\{\s*id:\s*"G0_GREY_DOT@1"', data) is not None,
       "G0 must remain a named expert in RADAR_EXPERTS")
    ok("R3c no-generic-entry-signal",
       not re.search(r"entry_signal\s*=\s*true", data + js),
       "flattened boolean")
    ok("R3d no-golden-oracle", "Golden Oracle" not in data + js + html, "generic category")
    ok("R3e one-card-per-expert", "one card per (ticker, expert)" in notes.lower() or "siblings" in js,
       "multi-expert law")
    ok("R3f multi-fixture", "multi_g0" in data and "multi_c1" in data and "multi_c2" in data,
       "FIX.MANY three lanes")
    ok("R3g multi-state-three",
       '["multi_g0","multi_c1","multi_c2"]' in data.replace(" ", ""),
       "state=multi keeps three lanes")

    # R4 — C4 is context / stratification only
    ok("R4 c4-not-firing", 'firing: false' in data and "stratification_only" in data, "C4 spec")
    ok("R4b c4-lane-disabled", "er-lane--c4" in css and "stratification_only" in js, "lane")
    ok("R4c c4-cannot-be-row-expert", 'if (r.expert === "C4") throw' in js, "throw")
    ok("R4d c4-chip-copy", "context only" in data.lower() or "仅语境" in data, "copy")

    # R5 — provisional vs confirmed
    ok("R5 provisional-label", "1D LIVE · provisional" in data, "EN")
    ok("R5b provisional-zh", "1D LIVE · 临时" in data, "ZH")
    ok("R5c confirmed-4h", "confirmed 4H" in data and "已确认4小时" in data, "C3")
    ok("R5d nightly-confirmed", "nightly · confirmed" in data, "G0")
    ok("R5e c1-not-confirmed-copy",
       "Not a confirmed daily close" in data or "不是已确认日线收盘" in data,
       "C1 honesty")
    ok("R5f no-daily-confirmed-masquerade", "Daily confirmed" not in data,
       "provisional must not be labelled Daily confirmed")

    # R6 — stale is not live
    ok("R6 stale-treatment-css",
       ".pvcard.er-stale,\n.pvcard.er-unav" in css or ".pvcard.er-stale,\r\n.pvcard.er-unav" in css,
       "demotion block")
    ok("R6b stale-kills-featured",
       "er-stale.pv-featured::before" in css and "display: none" in css,
       "featured killed")
    ok("R6c stale-no-hover-lift", ".pvcard.er-stale:hover" in css and "transform: none" in css, "hover")
    ok("R6d stale-label", "STALE · last usable reading" in data, "label")

    # R7 — unavailable is not a non-fire
    ok("R7 unavailable-null", "condition is null, not a non-fire" in data, "EN")
    ok("R7b raw-basis", "raw/adjusted basis mismatch" in data, "raw")
    ok("R7c unav-lifecycle-probing", 'id: "ep-unav"' in data and 'lifecycle: "probing"' in data, "not candidate")

    # R8 — false-start history cannot disappear
    ok("R8 history-field", "false_starts" in data and "false_starts" in js, "field")
    ok("R8b history-on-card", "data-false-starts" in js, "card hook")
    ok("R8c history-fixture", "ep-hist-fs1" in data and "ep-hist-fs2" in data, "two priors")
    ok("R8d reads-false-starts", js.count("r.false_starts") >= 2,
       "renderer must read history on the card and in the drawer")

    # R9 — no fabricated Priority / Opportunity / probability
    ok("R9 priority-accruing", 'data-priority="accruing"' in js, "hook")
    ok("R9b no-priority-number", "research_priority: { state: \"ACCRUING\", value: null" in data, "null")
    ok("R9c opportunity-slot", "NOT_YET_MEASURED" in data and "not_yet_measured" in js, "opp")
    ui = data + js + html
    ok("R9d no-validated-edge", not re.search(r"\bvalidated edge\b", ui, re.I), "validated")
    ok("R9e no-win-prob", "win probability" in data.lower() or "获胜概率" in data,
       "anon copy may mention the refusal — required")
    # The anon gate must refuse win probability, not print one.
    # DESIGN_NOTES may cite the forbidden phrase as a ban; only UI bytes count.
    ok("R9f no-percent-likely", not re.search(r"\d{2}% likely", ui, re.I), "fake odds")

    # R10 — EN/ZH hierarchy, not string-only
    ok("R10 bilingual-switch", "html[data-lang=\"zh\"] .l-en { display: none; }" in css, "css")
    ok("R10b both-langs-inline", 'class="l-en"' in js and 'class="l-zh"' in js, "js both")
    ok("R10c zh-life-words", "预候选" in data and "候选" in data and "探测中" in data, "life ZH")
    ok("R10d zh-purpose", "可观察的入场" in data, "purpose ZH")

    # R11 — no Prophet plan semantics
    ok("R11 no-own-it", "Own-It" not in js and "Own-It" not in html, "Own-It")
    # Ladder cells must be Radar words, not Watch/Ready/Entered/Delivering
    ok("R11b radar-life-keys",
       all(k in js for k in ("probing", "pre_candidate", "candidate", "invalidated", "expired")),
       "keys")
    ok("R11c no-delivering-cell", "data-life=\"delivering\"" not in js, "Prophet cell")
    ok("R11d sister-line", "not_prophet" in data or "Sister look" in data, "distinction")

    # R12 — dark/light + reduced motion + focus
    ok("R12 light-tokens", "html[data-theme=\"light\"]" in css, "light")
    ok("R12b zh-flip", "html[data-lang=\"zh\"]" in css and "--up: #e06464" in css, "zh up")
    ok("R12c reduced-motion", "prefers-reduced-motion" in css, "motion")
    ok("R12d focus-visible", ":focus-visible" in css, "focus")
    ok("R12e no-emoji-icon", "⚠️" not in js and "⚡" not in js, "emoji icons")
    # Candidate lifecycle must not inherit Prophet Buy (--pv-buy flips red in ZH).
    ok("R12f cand-not-pv-buy",
       ".er-cand   { --pvh: var(--ok);" in css or "--pvh: var(--ok)" in css,
       "candidate hue is direction-neutral --ok, not --pv-buy")
    ok("R12g cand-not-up-derived",
       ".er-cand" in css and "--pvh: var(--pv-buy)" not in css.split(".er-cand")[1][:80],
       "er-cand must not bind --pv-buy")

    # R13 — 390px single column
    ok("R13 mobile-one-col", ".pv-grid { grid-template-columns: 1fr;" in css.replace("\n", " ").replace("  ", " "),
       "390 grid")
    ok("R13b overflow-x-hidden", "overflow-x: hidden" in css, "page")

    # R14 — fixtures unmistakably synthetic
    ok("R14 synthetic-meta", "synthetic: true" in data, "meta")
    ok("R14b ref-tickers", "REF.DOT" in data and "FIX.WASH" in data, "tickers")
    ok("R14c every-row-flag", "synthetic: true" in data and "data-synthetic=\"true\"" in js, "row")

    # R15 — required fixture states exist
    for st in ("quiet", "g0", "c1", "c2", "c3", "c5", "multi", "expired",
               "invalidated", "history", "stale", "unavailable", "raw",
               "degraded", "partial", "board", "ipo", "lobe"):
        ok(f"R15 state-{st}", f"{st}:" in data or f'"{st}"' in data, st)


def playwright_checks(url: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        ok("P0 playwright-available", False, "playwright not installed — visual checks skipped")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def page_at(q: str, w: int = 1440, h: int = 900):
            pg = browser.new_page(viewport={"width": w, "height": h})
            pg.goto(f"{url}/?{q}&chrome=0", wait_until="networkidle")
            pg.wait_for_timeout(120)
            return pg

        pg = page_at("theme=dark&lang=en&state=board")
        ok("P1 banner-visible", pg.locator("[data-reference-banner]").count() == 1, "banner")
        n = pg.locator(".pvcard").count()
        ok("P1b many-cards", n >= 8, f"got {n}")
        experts = pg.evaluate(
            "() => [...new Set([...document.querySelectorAll('.pvcard')].map(c => c.dataset.expert))]")
        ok("P1c experts-unflat", set(experts) >= {"G0", "C1", "C2", "C3", "C5"}, str(experts))
        c4_cards = pg.evaluate(
            "() => [...document.querySelectorAll('.pvcard')].filter(c => c.dataset.expert==='C4').length")
        ok("P1d no-c4-card-expert", c4_cards == 0, str(c4_cards))
        pri = pg.evaluate(
            "() => [...document.querySelectorAll('[data-priority]')].map(n => n.textContent.trim())")
        ok("P1e no-priority-digits", all(not re.search(r"\d", t) for t in pri), str(pri))

        pgq = page_at("theme=dark&lang=en&state=quiet")
        ok("P2 quiet-empty", pgq.locator("[data-empty]").count() == 1, "empty well")
        ok("P2b quiet-no-cards", pgq.locator(".pvcard").count() == 0, "cards")

        pgm = page_at("theme=dark&lang=en&state=multi")
        many = pgm.evaluate(
            "() => [...document.querySelectorAll('.pvcard')].filter(c => c.dataset.ticker==='FIX.MANY').map(c => c.dataset.expert)")
        ok("P3 multi-three-lanes", sorted(many) == ["C1", "C2", "G0"], str(many))

        pgs = page_at("theme=dark&lang=en&state=stale")
        ok("P4 stale-class", pgs.locator(".pvcard.er-stale").count() >= 1, "class")
        ok("P4b stale-not-featured-look",
           pgs.evaluate("() => getComputedStyle(document.querySelector('.pvcard')).borderStyle") == "dashed",
           "dashed")

        pgu = page_at("theme=dark&lang=en&state=unavailable")
        ok("P5 unav-not-candidate",
           pgu.locator('.pvcard[data-life="candidate"]').count() == 0, "candidate")
        ok("P5b unav-flag", pgu.locator('.pvcard[data-unavailable="1"]').count() >= 1, "flag")

        pgh = page_at("theme=dark&lang=en&state=history")
        ok("P6 history-visible", pgh.locator("[data-false-starts]").count() >= 1, "history")

        pgz = page_at("theme=dark&lang=zh&state=board")
        hidden_en = pgz.evaluate(
            "() => getComputedStyle(document.querySelector('.l-en')).display")
        ok("P7 zh-hides-en", hidden_en == "none", hidden_en)
        ok("P7b zh-title", "实时入场雷达" in pgz.inner_text("h1"), "title")

        pg390 = page_at("theme=dark&lang=en&state=board", 390, 844)
        overflow = pg390.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        ok("P8 no-hscroll-390", overflow <= 1, f"overflow {overflow}px")

        pgl = page_at("theme=light&lang=en&state=board")
        bg = pgl.evaluate("() => getComputedStyle(document.querySelector('.pvcard')).backgroundColor")
        ok("P9 light-card-not-grey", "255" in bg or "rgb(255" in bg, bg)

        pga = page_at("theme=dark&lang=en&state=anon")
        body = pga.inner_text("body")
        ok("P10 anon-no-levels", "void levels" not in body.lower() or "does not print" in body.lower(),
           "honest gate")
        ok("P10b anon-no-prob-number", not re.search(r"\b\d{2}%\b", body), body[:200])

        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("RADAR_REF_URL", ""))
    args = ap.parse_args()
    static_checks()
    if args.url:
        playwright_checks(args.url.rstrip("/"))
    for passed, name, detail in checks:
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark}  {name}" + (f"  ({detail})" if detail and not passed else ""))
    print(f"\n{sum(1 for p, _, _ in checks if p)}/{len(checks)} passed")
    if fails:
        print("FAILURES:")
        for f in fails:
            print(" ", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
