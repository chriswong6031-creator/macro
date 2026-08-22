# XPV2 Sector Central R3B — Fresh Mobile / Accessibility Critic

## Review identity and scope

- Reviewer: Codex, GPT-5-based independent review seat (the runtime does not expose a more specific public model identifier).
- Freshness: I did not participate in R3B design, build, internal QA, fix work, or orchestrator adjudication.
- Role: Mobile / Accessibility critic only. This document records a critic verdict; it is not an authority approval or an authorization for R3C or production migration.
- Reference ID: `mastermind-xpv2-sector-r3b`.
- Frozen commit: `dc84f78cddf04d9be90e9249126f9767de5725a6`.
- Candidate: `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`.
- Required and independently verified candidate SHA-256: `19553267d3f51659503fc836da6b6bdaa06afc9cdd607aafb1bb795e46c47dca`.
- Current-main review base: `27c69839b7b0edc12c373c7fd38534bb329db4ab`.

## Frozen-byte and semantic-drift checks

The candidate was hashed both from the frozen commit and from the current review base. Both returned the required SHA-256. The candidate blob is identical at both revisions (`d174ecbc1b5f2539133c95fcc090f5d23b59757c`). `BUILD_MANIFEST.json` was also read at the frozen commit and current main; both copies hash to `a7b9ae8ab3f13f106478f30c7de8b46672662832b09224fb7e182d0cb6b2d396`, and its candidate entry records the required candidate hash.

Relevant current production sources were compared against the frozen commit. The route template, workspace JavaScript, access configuration, Sector Central builder, route/access semantics, schema, producer, and capability surface did not change. The only targeted `config.yml` change is an unrelated notification-origin cutover from the retired GitHub Pages mirror to `https://www.mastermind-x.com`. The R3B reference manifest/proposal changed only to record the frozen SHA and `in_review` status. Verdict: **no relevant semantic drift**.

## Methods

The first pass was conducted under rationale quarantine against a locally served copy of the exact frozen bytes. No candidate or production file was edited. Browser controls temporarily changed viewport metrics, theme, language, hash, entitlement fixture state, reduced-motion media, and synthetic coarse-pointer state in the test page only.

Coverage:

- 126 standard-width cells: all six views at 320, 360, 390, 430, 768, and 820 CSS px in dark EN, light EN, and dark ZH, plus light ZH for Money, Explore, and Confluence.
- 48 200%-zoom/reflow cells: all six views at physical viewport widths 320, 390, 768, and 820 in dark EN and dark ZH, modeled as the corresponding half-width CSS viewport at device scale factor 2.
- Keyboard semantics and focus probes for workspace navigation, Overview action tabs, Map scope/disclosure, Confluence universe/timing tabs, trace disclosure, and sticky-chrome landings.
- Synthetic coarse pointer (`pointer: coarse`, `hover: none`, five touch points) and `prefers-reduced-motion: reduce`.
- Static and rendered-DOM audits for IDs, ARIA references, tab semantics, focusability, target geometry, document language, hash targets, and pointer-only affordances.
- Visual/nonvisual field comparison for the cycle map and heatmap alternatives.
- Flat-background text-contrast calculation using sRGB relative luminance and computed foreground/background colors.
- Gated, hydrated, and ungated Overview behavior.

Standards reference points included WCAG 2.2 target sizing and focus-obscuration guidance and the WAI-ARIA Authoring Practices tab pattern:

- <https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum>
- <https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html>
- <https://www.w3.org/WAI/ARIA/apg/patterns/tabs/>

One quarantine-process limitation is disclosed: while locating the build manifest, a recursive tree listing emitted filenames under `build/qa_findings/`. No QA finding, screenshot, report, contract, adjudication, or other forbidden file content was opened. The findings below were independently reproduced in the rendered candidate before any quarantined material was read.

## First-pass frozen record

- Frozen at: `2026-08-22T14:01:23Z`.
- Verdict: **BLOCK**.
- Meaning: the exact frozen reference contains defects that must be corrected in the reference before it can become production migration law. This is not the final design-authority verdict.

### MAC-001 — BLOCKING — Moving help disclosures are 16 x 16, named only `?`, and expose their explanation only through generated visual content

All three `.r3-tr-help` buttons measure exactly 16 x 16 CSS px. Their accessible name is the literal question mark; they have no `aria-label`, `aria-labelledby`, or `aria-controls`. Activating a control changes `aria-expanded` from `false` to `true` and preserves focus, but the explanation lives in `data-tip-en` / `data-tip-zh` and visual generated content rather than an accessible owned node. A nonvisual user hears an indistinguishable “question mark, button” three times and cannot obtain the Rank fit, Reliability, or scorecard-method explanation. The controls also fail both the product’s repeated-target floor and WCAG 2.2’s 24 x 24 minimum target-size baseline.

Evidence:

- Rank fit: 16 x 16; name `?`; no controlled element.
- Reliability: 16 x 16; name `?`; no controlled element.
- Track-record methodology: 16 x 16; name `?`; no controlled element.

Required correction: use a >=44 x 44 effective hit region, give each button a distinct localized accessible name, render the disclosed explanation in a real DOM node with a stable ID, connect it with `aria-controls` and an appropriate description/relationship, and verify keyboard, coarse-pointer, and accessibility-tree exposure in EN and ZH.

### MAC-002 — BLOCKING — 200% zoom at the 320px physical test axis overflows and clips customer meaning

At the required 200% zoom axis for a 320px physical viewport (160 CSS px reflow width), the page overflows horizontally in Moving (1px EN), Money (8px EN), and Explore (7px EN / 4px ZH). More importantly, Money clips semantic content inside fixed/hidden-overflow bands: `.mny-verdict` has a 119px client width against 147px scroll width, and `.r3-band.mny-flowfrag` has a 119px client width against 134px scroll width. The clipped verdict/flow text is customer meaning, not decorative geometry.

No page-level overflow was measured at standard zoom in any of the 126 cells, nor at the 200% 390/768/820 physical-width axes. That narrower success does not cure the commissioned 320/200% failure.

Required correction: make the Money verdict/flow bands wrap or recompose without hidden semantic clipping at 160 CSS px; remove the remaining Moving and Explore reflow overflow; rerun all six views at every commissioned zoom axis in EN/ZH and both themes.

### MAC-003 — BLOCKING — Chinese mode leaves the document language as English

Changing the rendered language control to Chinese updates visible copy and several component ARIA labels, but the root remains `<html lang="en">`. Assistive technology therefore receives an English document-language declaration while reading Chinese content, which can cause incorrect pronunciation and language rules across the entire page.

Required correction: synchronize the root `lang` value with the active language (`zh` or the repository’s more precise chosen Chinese language tag), including initial state and runtime language changes; verify that the value persists through view repaint and deep-link navigation.

### MAC-004 — BLOCKING — Workspace navigation does not meet the commissioned 3 x 2 mobile or roving-focus behavior at 320px

At 320px the six workspace links render as two columns by three rows, with x positions 0/161 and y positions 45/99/153. The commissioned audit requires a 3 x 2 mobile arrangement. All six links also remain `tabIndex=0`; ArrowRight from the focused Overview link neither moves focus nor changes the active view/hash. The links otherwise have useful `nav` semantics, a localized navigation label, `aria-current="page"` on the active view, >=53px height, and visible 2px focus outlines.

Required correction: make the 320px composition a deliberate, unclipped 3 x 2 arrangement and implement/document the commissioned roving-focus behavior with localized semantics and stable hash navigation. If design authority instead intends ordinary navigation-link semantics with all links in the tab sequence, the reference contract and critic commission must be reconciled explicitly before acceptance; the frozen candidate cannot silently diverge.

### MAC-005 — MAJOR — Light-theme “Still measuring” status text misses normal-text contrast

In Moving’s light theme, the localized status text “Still measuring” / “测量中” computes to `rgb(185, 121, 26)` at 10px, weight 700, on white. The measured contrast ratio is 3.61:1, below the 4.5:1 requirement for normal text. The status communicates whether a track-record horizon has enough evidence, so it is substantive rather than decorative.

Required correction: use a light-theme token that reaches at least 4.5:1 on its rendered background and recheck all track-record states in both languages. Heatmap text over color fields requires a separate human/automated contrast verification during repair; the flat-background probe deliberately does not claim those gradient/color-field cases.

### MAC-006 — MINOR — The document repeats `id="ref-data"` 22 times

The static/rendered DOM contains 22 embedded script/fragment nodes with the same `ref-data` ID. No invalid `aria-controls`, `aria-labelledby`, or `aria-describedby` references were found, and no ARIA relationship targets these scripts, so this was not independently blocking. It nevertheless violates ID uniqueness and makes ID-based DOM/tool behavior ambiguous.

Required correction: remove the repeated ID or generate unique IDs while retaining `data-path` as the registry key; rerun duplicate-ID and ARIA-reference checks.

## First-pass strengths

- Standard-responsive matrix: no document-level horizontal overflow across all 126 standard cells.
- Reduced motion: the reduce media query matched, no active Web Animations remained, and computed animation/transition durations were reduced to one microsecond.
- Synthetic coarse-pointer state matched `pointer: coarse` and `hover: none`; required interaction content had click/keyboard paths except MAC-001’s inaccessible explanation.
- Overview: all five action states are present. Required active targets are >=44px. Gated mode exposes three real rows plus an honest sign-in disclosure; hydrated/ungated modes expose the complete board and Show more semantics. Row/Watch links are real `href`s. Trace deep linking opens the source row, updates `aria-expanded`, preserves focus, and retains the Overview view.
- Map: scope buttons preserve focus across repaint. Its accessible rotation table uses the same group records and exposes Rank, Group, Where it sits, Strength, 20d vs S&P, Rank move 5d, and Noted. Show all expands from 10 to all 38 records while preserving focus. The cycle-clock table exposes every sector’s phase, position, last confirmed turn, and next window from the chart data.
- Money: the accessible browse-names path exposes all 503 names with ticker, name, sector, one-day move, and a real Terminal destination link; it does not recompute ranking. The sector table exposes all sectors/time windows. This meets or exceeds the visual map’s customer fields, subject to the zoom defect in MAC-002.
- Explore: filters are real pressed buttons; the numeric window input has an explicit localized label; table/list headers, Show all, selected performance, and a keyboard-operable Time Machine disclosure are present. The sole model-originated `ai_watch` field is null in the frozen fixture, so no unlabeled model prose is rendered; the code path provides the localized “Model analysis / 模型分析” label when data exists. No free-text search was counted as a missing capability because the governing R3A capability ledger records that production has none.
- Confluence: universe and timing tablists implement Arrow/Home/End movement, update selected state, and retain focus after repaint.
- Hash/sticky checks: the available legacy targets landed below sticky chrome. `#actnow-section`, `#si-map`, `#rotmap-section`, `#si-money`, `#explore-section`, `#table-section`, and `#sc-app` settled at the sticky offset; `#grader` and `#tm-mount` remained visible at scroll ceiling. No focused tested control was hidden beneath sticky chrome.
- Static semantics: exactly one `h1`; no broken ARIA ID references, `href="#"`, click-only noninteractive elements, focusable descendants under `aria-hidden`, or lost focus in the tested repaint paths.

## Second-pass amendments

Completed at `2026-08-22T14:08:19Z` after reading, in full, the responsive contract, accessible-alternative contract, fix verification, QA attack report, orchestrator adjudications, and evidence index. The following overlapping author claims were independently rerun against the exact required candidate bytes:

- The final 200%-zoom repairs were re-probed after a full navigation/reload with metrics reapplied and no screenshot in the measurement loop.
- Map universe targets measured exactly 44.0px high at 768 and 820 in EN and ZH.
- Overview and both Confluence tablists use one `tabIndex=0` selected tab and `-1` on the rest; Arrow/Home/End behavior and focus-after-repaint passed.
- The four reference-authored component labels become Chinese when the candidate’s actual language control is used.
- All ten Moving connector arrows are `aria-hidden="true"` with no image role.
- Hydrated Overview contains the full 4/5/5/3/27 rows, working reveal controls, and an honest gated/fetch-fail baseline.
- Hash targets remain visible rather than buried after the bounded settle/re-scroll behavior.

### MAC-001 — UPHELD, BLOCKING

Nothing in the author contracts or fix verification addresses the final candidate’s three 16 x 16 `.r3-tr-help` controls. The historical Gate-5 sweep says its only sub-44px failures were Map segments, but that report attacked an earlier 5,431,707-byte candidate; the required frozen candidate is 5,442,009 bytes. The exact final bytes still render all three help controls at 16 x 16 with the indistinguishable name `?`, no controlled DOM explanation, and explanatory prose only in data attributes/generated visual content. This is an independently reproduced final-byte defect.

### MAC-002 — UPHELD BUT NARROWED, BLOCKING

The author’s QA2-01 through QA2-05 repair claims are substantially correct. On a clean rerun of the exact final bytes at a 160 CSS px layout viewport (the commissioned 320px physical / 200% axis), Moving and Explore now have zero document overflow in EN/ZH, and Money also has zero page-level overflow. The first-pass page-overflow magnitudes and the `.mny-flowfrag` characterization are therefore withdrawn from the final finding; the historical fix wave closed those cases.

A narrower defect remains in Money. `.mny-verdict` computes to 134px client width, 147px scroll width, and `overflow:hidden`. The final EN leaf `Volatility: calm` paints from x=36.0 to x=150.3 while the clipping container ends at x=147.0, cutting approximately 3.3px from a substantive status label. The responsive contract’s own Money rule does not grant semantic clipping, and the critic commission explicitly requires no fixed-height clipping at 200%. Required correction remains: reflow/wrap that label within the 160px layout viewport and rerun the full commissioned zoom matrix with both document-overflow and clipped-leaf gates.

### MAC-003 — UPHELD, BLOCKING

The author’s QA2-10 fix works for component-level labels: using the actual page language selector changes them to `板块情报视图`, `操作分组`, `切换轮动图的主题或板块`, `范围`, `时机状态`, and `筛选子行业或板块`. It does not change the document language. `document.documentElement.dataset.lang` becomes `zh`, while `document.documentElement.lang` remains `en`. The component-label repair therefore does not cure the page-wide AT language defect.

### MAC-004 — DOWNGRADED TO DESIGN-AUTHORITY CONTRACT CONFLICT

The first-pass ARIA framing is narrowed. Workspace destinations are ordinary navigation links inside a named `nav`, not tabs; keeping each link in the sequential tab order and not implementing APG tab-arrow behavior is semantically defensible. The lack of arrow-key roving is therefore withdrawn as an independent accessibility defect.

The geometry conflict remains. The fresh-critic commission explicitly names a 3 x 2 mobile arrangement, while the subsequently read responsive contract explicitly changes the navigation to 2 x 3 at `<=359px`. The frozen candidate follows the latter at 320px and is unclipped, legible, and >=53px high. This is not a demonstrated usability failure; it is an unresolved authority conflict between the critic commission and author contract. Sol must choose one rule before reference acceptance. If 3 x 2 is binding at 320, the candidate must change; if 2 x 3 is ratified, the critic commission/contract record must be reconciled so migration law is unambiguous.

### MAC-005 — UPHELD, MAJOR

The author QA report expressly left color contrast out of scope, and none of the second-pass records supplies a contrary measurement. The exact final bytes still compute “Still measuring” / “测量中” at 3.61:1 in the light theme, 10px/700 on white. The repair remains required.

### MAC-006 — UPHELD, MINOR

The final document still repeats `id="ref-data"` 22 times. The author material neither relies on those IDs for ARIA nor closes the uniqueness issue. Keep the finding at Minor because `data-path`, rather than the duplicate ID, drives the embedded registry and no broken ARIA relationship was found.

### Second-pass evidence limitation

`evidence/EVIDENCE_INDEX.md` names a pre-final candidate hash (`0812bf7f…8610b5ce2`), while the frozen candidate required by this review hashes to `19553267…46c47dca`. Its screenshots can illustrate intended states but cannot, as indexed, prove the exact final bytes. The fix-verification prose likewise records reruns but does not repair that stale evidence binding. This does not weaken the independent browser/DOM measurements above; it means Sol should not treat the existing screenshot index as exact-hash evidence without a corrected binding.

## Final critic verdict

**BLOCK — exact frozen reference requires correction before production migration law.**

The blocking basis is MAC-001, MAC-002, and MAC-003; MAC-005 is an additional standards-level defect that also requires correction. MAC-004 requires Sol’s explicit authority reconciliation, and MAC-006 is non-blocking hygiene. This critic verdict is advisory to Sol and is not an authority approval, a production-migration authorization, or permission to start R3C.

Minimum reference-correction packet before re-review:

1. Replace the three Moving question-mark disclosures with >=44 x 44 effective targets, distinct localized accessible names, and real DOM explanations linked to their controls.
2. Remove the residual Money 320/200% clipping and rerun all 48 commissioned zoom cells with both page-overflow and clipped-semantic-leaf assertions.
3. Synchronize `<html lang>` with initial and runtime EN/ZH state, then verify through actual page controls and view repaints.
4. Raise the light-theme “Still measuring” token to >=4.5:1 and run a complete contrast audit, including heatmap text over generated color fields.
5. Obtain Sol’s explicit 320px workspace-nav ruling (3 x 2 versus 2 x 3) and make the candidate plus governing contracts agree.
6. Make embedded registry IDs unique and correct the evidence index so every claimed screenshot/re-probe is bound to the exact reviewed candidate hash.

## NOT_EVALUABLE axes

- Real physical touch hardware and platform gesture behavior: NOT_EVALUABLE in this session.
- Real iOS/Android browser chrome, safe areas, and dynamic viewport behavior: NOT_EVALUABLE in this session.
- Real screen-reader behavior (VoiceOver, TalkBack, NVDA, or JAWS): NOT_EVALUABLE. DOM/ARIA and browser accessibility semantics were inspected, but those are not a substitute for a real assistive-technology run.
- Native browser text-only zoom distinct from browser/page zoom: NOT_EVALUABLE; the commissioned browser-zoom/reflow axes were evaluated.
