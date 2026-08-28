# Theme-Parity TP-1 — Canada acceptance record (2026-08-28)

Carrier: `theme-parity-tp1-canada-20260828-sol-001` (#agent-dispatch C0BSBM78V1N,
parent 1787905313.216539) · Sol merge release + deviation ratification on-thread
2026-08-28 · program architecture
`research/THEME_PARITY_RATCHET_PRESENTATION_CONVERGENCE_ARCHITECTURE.md` (+
Amendment 1). Predecessor: TP-0 governance (PR #6579, merge `6e276232ed31`).
Functional baseline preserved:
`research/STOCK_DASHBOARD_V38_CANADA_ACCEPTANCE_2026-08-27.md` (PROVEN_LIVE).

## Implementation identity

- PR **#6612**, branch `claude/tp1-canada-theme-parity`, base `c819f6428f91`.
- Heads: `40d355bd51f2` (extraction) → `fdcee15baf38` (light art direction) →
  `1e9bacef236a` (evidence) → `5df6fedad697` (review repairs + recapture) →
  **`f6ace49c4da774df530f8d710dd8f23c5b2dae0f`** (released exact head).
- Squash-merge: **`e2091032ad1f53eb8b8cfa3767aa6498f414193e`** (2026-08-28T17:35:28Z,
  merged with `--match-head-commit` pinned to the released head).
- Changed files: `templates/stock-dashboard.css` + `site/stock-dashboard.css`
  (new governed pair, byte-identical), `templates/dashboard-icons.js` +
  `site/dashboard-icons.js` (fail-soft `ensureStockDashCss` loader, bounded
  retry ×3, `?v=20260828`), `site/canada-stock-v36.js` (**only** `injectCss()`
  deletion + mount-class line: 6 insertions / 60 deletions vs base),
  `tests/test_canada_v36_composer.py`, `tests/test_stock_dashboard_css.py`
  (new), `config/runtime_style_injection_allowlist.json` (Canada entry REMOVED —
  runtime style budget 0), `.github/ci/legacy-jobs.yml` (new suite wired into
  the Canada composer step), `mockups/evidence/theme-parity/tp1-canada/**`.

## What shipped (capability delta)

Runtime stylesheet debt to zero: the composer's ~10KB `injectCss()` system is
extracted into one governed presentation pair rooted `.mx-stockdash
.mx-stockdash--ca`, token-clean under the TP-0 gates. Dark remains the V3.8
command center (declared deltas below). Light is a deliberate research-workspace
art direction: Act-Now as ONE white instrument with four hairline-divided
semantic-rail columns; Prophet gallery recessed to canvas with white ringed
cards (ring, not glow); Leadership as an institutional ranked list with a
breadth track; segmented controls with deepened track + raised white selection;
modal on a cool `--text`-derived scrim with white material. The composer loads
only after the governed stylesheet is ready (fail-soft: legacy page stays
visible on CSS failure).

Declared dark deltas (complete 7-item DARK DELTA ledger in the stylesheet
header): near-lane/HOLD ink restored to V3.8 link-blue; modal shadow geometry
restored; segmented selected shadow restored; scrim base token-derived
(sub-perceptual); radius snapped to the §2.2 scale (≤2px); buy/avoid lane inks
aligned to the Prophet stance family (ΔE76 ≈10/≈8, stance-is-not-direction).

## Sol-ratified plan deviations

1. `.near` binds `var(--ink-link, var(--link))`, not the plan's stance family —
   `--pv-near` derives from `--pv-buy` in theme.css and collapsed BUY↔IN-FAVOUR
   (measured ΔE76 76→14 dark / 113→9 light). Architecture over plan.
2. Hand-stamped `?v=20260828` — `scripts/optimize_assets.py` walks HTML only
   and can never stamp a JS-authored href.
3. Modal family rescoped `.mx-stockdash--ca ~ .ca-v36-modal` — the composer
   body-appends the modal; the extraction's descendant scope had orphaned it.

## Reviews

Two independent Opus lanes (design/taste; functional adversarial), neither the
author. Both first returned REQUEST_CHANGES — converging on the stance-hue
collapse as BLOCKER, plus modal dark elevation, weakened moved-test
discriminators, false stamp comment, un-retried CSS gate, specificity-dead
mobile-light reset. All repaired at `5df6fedad697`; both delta passes returned
**PASS** with per-finding RESOLVED tables (near-lane inks measured
byte-identical to the V3.8 baseline; min pairwise lane separation ≥60 ΔE76 both
planes).

## CI (exact released head `f6ace49c4da7`)

Full 206-job suite (the legacy-jobs.yml edit is a global invalidator): all 12
`trusted-executor-pack-*` green, `contract-delta` green (it correctly caught the
new suite unwired first — fixed by wiring, not waiver), `ci-gate` green, fences
green. Sol's release cites fences run `33180457136` SUCCESS and binding CI run
`33180457617` SUCCESS on the exact head. Only red: the known non-binding
`ci-authority/codex/merge-queue-pilot`.

## Evidence matrix (committed, `mockups/evidence/theme-parity/tp1-canada/`)

`mastermind.p0_evidence.v2` manifest: 8/8 cells (dark/light × EN/ZH × 1440/390)
`captured:true` with matching `applied_theme`/`applied_locale`,
`horizontal_overflow:false` both viewports, 0 console errors. Before/after
dark+light EN 1440 pairs captured from pinned-main baseline bytes with the same
harness. Supplementary: `modal-{dark,light}-en-1440.png` (modal open, both
themes), `allcands-{dark,light}-en-1440.png` (pick-vs-non-pick ring positive
control), `mobile-light-lane2-390.png` (mobile-light reset proof).
`EVIDENCE.yml` receipt positive-control-verified against
`check_ui_visual_evidence.py` (gate reds without it, greens with it).

## Asset identity (merged bytes)

- `site/stock-dashboard.css` sha256
  `0fb23098d7201c90d72f7c0ad4573b9566fb955147f86d14dff9c17a4f5b8525` (44,507 B)
- `site/dashboard-icons.js` sha256
  `8a96e10b728fd9bdccd94005671f5b61124235777ce6c9a30754a2adfd13f0d0` (16,780 B)
- `site/canada-stock-v36.js` sha256
  `e135d5f8281099d83474fdc705e2b7b4329df99482c060b9eeeb60c45f58c359` (35,226 B)

## Entitled production proof (www.mastermind-x.com/canada_stocks.html, 2026-08-28, entitled Claude-in-Chrome)

| Item | Result |
|---|---|
| Deploy | **PASS** — VPS served the merged `dashboard-icons.js` within one pull cycle post-merge; byte-identical to repo (direct `diff`, 16,780 B). Post-merge render lane re-stamped assets (`render-public` commit `02c4276bafd5`) |
| Entitled assets | **PASS** — `stock-dashboard.css?v=20260828` 200 `private, no-store` 44,507 B; `canada-stock-v36.js?v=20260823` 200 `private, no-store` 35,226 B (exact merged byte counts; content markers verified: modal sibling scope, near→link rule, light root, DARK DELTA ledger) |
| Stylesheet-before-composer | **PASS** — `#mx-stockdash-css` `data-ready="1"` + parsed sheet with composer mounted; mount class `ca-v36 mx-stockdash mx-stockdash--ca` |
| Theme toggle no-remount | **PASS** — light↔dark: same mount node identity, `__mmCanadaStockV36` stable, exactly one stylesheet link; near-lane ink resolves light `rgb(41,90,234)` / dark `rgb(122,167,224)` — the V3.8 baseline blues — via CSS alone |
| Section order | **PASS** — Act-Now → Prophet → Leadership → Evidence & Record |
| Act-Now | **PASS** — 4 lanes, row caps ≤3, `View all 5`, 4 distinct semantic rails in both themes |
| Top Picks population | **PASS** — 5 visible / 4 hidden / 9 on board; count line honest |
| Sector filter round trip | **PASS** — filter on: `2 shown · 9 on board`, pill on, DOM population unchanged; cleared back to 5 |
| Grid/Table XOR | **PASS** — exact, both directions |
| Modal | **PASS** — `position:fixed` full-viewport overlay opens/closes both themes (the rescoped family, live) |
| ZH | **PASS** — dark ZH full render: 红涨绿跌 flips lane stance hues correctly, 看好 (near) correctly holds non-flipping link-blue; native heads (现在行动/领先与轮动) |
| Quote convention | **PASS at rule level** — served CSS pins `.nb-chg.up`→`var(--ok)`, `.down`→`var(--act)`; no `.up/.down` cells existed at proof hour (pre-market, all changes `—`), so the rendered convention rests on the served rules + tests + committed local evidence |
| LIVE / clocks | **PASS** — LIVE chip Aug 28 beside Board Aug 27 vintage chip; 9 live table cells |
| Track Record | **PASS** — `.trk` chip in Evidence & Record |
| Console | **PASS** — zero errors on a tracked fresh load with composer mounting |
| Overflow | **PASS** — scrollWidth == clientWidth at 1440-class |
| Fail-soft fixture | **PASS (local, merged bytes)** — site served with `stock-dashboard.css` 404: composer never mounts, no composed shell, failed link removed, legacy `#standouts` visible; positive control (same fixture + CSS restored): composer mounts. Production cannot be forced to 404; fixture ran in a real local browser on the exact merged bytes |
| 390 px | **Residual (V3.7/V3.8 class)** — OS ignores automation-tab resize (resize API reports success, viewport unchanged — the exact V3.8 residual); the exact merged bytes passed the full 390 grammar (one lane, segmented selector, no overflow, mobile-light reset) in a local real browser: committed 390 cells + `mobile-light-lane2-390.png` |

## Registry closeout (this PR)

`macro:canada_stocks` → `design_system: {compliant: true, migrated_pr: 6612,
governed_regions: [{template: templates/stock-dashboard.css, region:
.mx-stockdash--ca}], evidence: mockups/evidence/theme-parity/tp1-canada/manifest.json}`;
`archetype: discovery_board` preserved. Canonical registry regenerated by
`scripts/build_product_page_registry.py`. Full `--mode enforce --registry`
verification: the governed pair contributes **zero blocking findings** (3
report-tier `card-class` heuristic hits only), the binding is real (poisoned
`#ff0000` in the governed file → blocking +1, exit 1; removed → baseline), and
the flip+regen strictly REDUCED the estate's bare-enforce blocking baseline
(5,387 → 5,242 — the stale committed registry had been counting
recently-added templates as unknown). The whole-estate bare-enforce red is
pre-existing debt outside this closeout's claim; CI's binding arm remains
`enforce-added`.

## Residuals (reported, not absorbed)

- Inherited page-ambient orb/moon glow in `canada_stocks.html` (predates TP-1,
  pixel-diff-proven on baseline shots): in light it reads as a saturated orange
  sun; at 390 it occludes a data row. Recommend its own follow-up wave.
- Doubled modal caption "Theme Leadership Theme rank" — pre-existing V3.8
  composer copy, visible now that the modal is un-orphaned. Composer-owner lane.
- `ensureStockDashCss` is single-caller by design this wave; before HK joins the
  seam (TP-2), replace the direct load-listener branch with a shared
  pending-callback queue (documented at the seam).

## TP-2 gate

TP-2 HK may start only after THIS closeout merges. It follows the governed
family grammar with HK-native semantics (architecture §7.3) and must resolve the
loader seam's multi-caller queue first. TP-2 remains unauthorized until Sol
issues its own carrier.

**Canada TP-1: implementation PROVEN_LIVE in production; compliance flipped in
this closeout only after that proof (Amendment 1 §A2).**
