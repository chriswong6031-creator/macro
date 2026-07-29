# W4 sheet — Motion & consistency sweep (final build wave)

Scope (whole page, no new sections):
1. **h2 type-scale unification** (deferred from W2/W3): one heading system across .sec-title/.feat-title/every band h2 — pick the SMALLER coherent scale (do not inflate): target `clamp(32px,3.2vw,48px)/800/-.018em` for section heads; verify no band's headline wraps worse than before at 1440/1024/390. Hero h1 FROZEN (operator ruling — untouched).
2. **Motion doctrine sweep (§7)**: every reveal on --ease-out/--dur-rev with --d stagger steps ≤.28s per cluster; entrance re-times for the JS-driven loops ONLY where CSS classes already control them; hover physics per §5 on every interactive card (verify none missing: tier cards, belt cards, lane chips, filings rows, capability chips, footer links, nav items); links arrow-nudge 2px; focus-visible ring on every interactive element (2px --blue, 2px offset).
3. **Retire .rv-rule** (W1 utility, provably inert — W2's report): delete the utility + its CAUTION comment; confirm zero consumers; .bandrule is the standing device.
4. **Receipt-bar completion**: every vignette carries exactly one .dm-rcpt (state tag + as-of from EXISTING words only). Bands still missing one after W3: check terminal (the mock itself is the receipt — skip), hero cards (kickers carry as-of — skip), rotations/filings/sits/funds/beyond/ai (W2/W3 added — verify), belt cards (ZONE+date lines are the receipt — verify mono). No inventions.
5. **Spacing-grid audit**: every touched band's vertical padding on the clamp system; inter-element gaps on the 8px grid; kill any margin-collapse surprises found in shots.
6. **Copy-budget trim (DESIGN_DOCTRINE §5)**: ledes ≤2 lines at 1440; bullets ≤3 with bold lead ≤4 words; NO meaning changes, NO new claims, data-zh twins updated for any trim. If a trim changes meaning, don't trim.
7. **CSS trim mandate**: net-negative preferred; ceiling 110,000 bytes; collapse duplicate comment banners; merge selectors where safe (grep every consumer before merging).

Gates: §0 set + the W2/W3 report format. Shots: full-page 1440 EN+ZH ?still, 390 EN, PLUS a live (no ?still) 1440 EN full-page after 5s for entrance end-state. Tests: 8-file set; only tolerated red = landing.css stamp lag. Commit "landing W4: motion & consistency sweep — heading unification, focus states, receipt completion" — no push/PR.

OPERATOR RULINGS (standing): hero copy block frozen; headlines plain ink/white; no two-tone/gradient beyond the hero identity; 390 stacks copy-first; receipt bars = existing words only.
