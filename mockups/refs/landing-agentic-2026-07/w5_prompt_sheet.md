# W5 sheet — Voice & polish (post-program follow-up wave)

Scope = exactly the three W4 leftovers (PROGRAM_STATUS.md). No new sections, no new
design decisions beyond this sheet. Branch `claude/landing-w5-voice-5faeec` (fresh off
post-#3970 main) is checked out.

## 1. `.mk` size ramp
The mono micro-label recipe (`font-family:var(--mono);font-weight:600;font-size:Npx;
letter-spacing:.0Nem`) is inlined ~20× at 9-11px. Add size steps on the existing `.mk`
base (e.g. `.mk-9/.mk-10/.mk-11` — smallest change that unifies; reuse `.mk` itself for
the 11px step), replace every inline recipe with base+step, snapping to the NEAREST step.
Gates: enumerate every converted site with before→after px (shifts ≤1px only); computed
spot-check one ZONE line, one receipt, one kicker; expected net saving ~600 B; zero
consumers left on the inline recipe (grep proof: `font-family:var(--mono)` count in
component rules → only the ramp definitions remain).

## 2. Lede tightening (facts are load-bearing — NO claim may drop)
Budget: ≤2 rendered lines at 1440 in EN. Drafts below are the direction; you own final
words + zh twins (match the page's existing zh register). If a lede cannot reach 2 lines
without dropping a fact, KEEP CURRENT and report declined-with-evidence (measured px).
- **#f-filings `.feat-sub`** (now 3 lines): draft — `From senators to CEOs, <b>every
  disclosure</b> read — and scored for what's worth copying.` Facts kept: span of filers
  (political↔corporate; full enumeration lives in the INSIDER & CONGRESS eyebrow + rows),
  every-disclosure coverage, copy-worthiness scoring.
- **#f-funds `.feat-sub`** (now 3 lines): draft — `356 tracked funds, every quarter —
  <b>adds, trims, fresh stakes</b> mapped onto your names.` Facts kept: 356, tracked,
  quarterly, the three flow kinds, your-names mapping. (Filing-vs-talk angle carried by
  the h2 "What funds did — not what they said.")
- **#ai `.sec-sub`** (now 3 lines at the 504px column): draft — `It reads every desk
  before it answers — signals, filings, flow, regime. <b>It explains; the engines
  decide.</b>` All four desks + the division of labor stay; "cross-checked" may drop ONLY
  because the four-desk read + explain/decide split carries the epistemics — if you
  disagree, decline instead.
Every accepted trim updates `data-zh` in the same edit; bold leads stay ≤4 words.

## 3. 390 headroom (ai + pricing heads at ~11px slack)
Recommended: micro-tracking at small viewports — in the ≤420/390 block, tighten
`.sec-title` tracking one notch (target −.022em; pick by measurement). Gates: measure the
two tight heads before/after at 390 (report px slack; target ≥15px), AND re-verify every
h2 at 390 EN+ZH for zero new wraps. Fallback: document-and-accept with measurements.

## Standing gates (unchanged from W1-W4 — violating any fails the wave)
Hero copy block + .cov-copy h1 + .live-pill + gradient @supports FROZEN. Section heads
plain ink/white. Honesty labels byte-identical (SCRIPTED DEMO/脚本演示/REAL CALLS ·
2-WEEK DELAYED/PREVIEW/rebuilt nightly/demo/free forever). No "validated", no
falsifier-family vocabulary. Contracts untouched: nav DOM, footer anchors, #pricing-matrix,
applyPricing, #mm-adtest + data-adtest-slot, #ph-data, .psc-stages aria, phDrift 95s/60s,
live-quote selectors, all JS loops. landing.css ceiling 110,000 B (this wave should be
net-negative via §1). Edit templates/* only; `python3 -m scripts.check_template_site_sync
--fix`; never hand-edit stamps; do NOT touch site/whitehouse.html even if a sweep offers it.
Test set green at handoff: `python3 -m pytest tests/test_landing_navigation.py
tests/test_public_chrome.py tests/test_onboard_compare_matrix.py tests/test_landing_pricing_cta.py
tests/test_prophet_showcase.py tests/test_check_font_ui_defined.py
tests/test_marketing_ad_plane_o.py tests/test_asset_stamp_lane_order.py -q`
(stamp-lag red mid-work only; you clear it in commit 2).

## Environment (hard-won)
Serve synced site/ on 8854; Playwright Python API, `channel="chrome"`, launches host-flaky
→ 4-attempt retry, foreground Bash with sandbox disabled; `domcontentloaded` + sleeps,
never `load`; fresh context per language (localStorage lang bleeds); `?still` freezes motion.

## Shots → shots/w5/
1440 EN full ?still · 1440 ZH full ?still · 390 EN full ?still · one 1440 crop per touched
lede (before/after not required — W4 fulls are the before) · one 390 crop of the two
tightened heads.

## Commits (two, then stop — NO push/PR; commissioning session ships)
1. `landing W5: voice & polish — mk ramp, lede tightening, 390 headroom`
2. `landing W5: re-cut asset stamps post-CSS` (optimize_assets + sync + full-green suite)

## Report
Per-item verdict + evidence (§1 site-by-site table, §2 accepted/declined per lede with
rendered line counts, §3 measured slack), byte delta, test tail, shot paths, deviations.
