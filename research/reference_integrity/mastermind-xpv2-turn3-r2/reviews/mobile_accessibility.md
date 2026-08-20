# Independent Mobile and Accessibility Critic

- Critic identity: `codex-xpv2-mobile-accessibility-20260820`
- Frozen artifact commit: `da83976ece01c54d5ab07307e68118693e100a58`
- Verdict: **BLOCK**
- Review mode: read-only, independent, designer rationale not read

## Findings

### MAC-001 — BLOCK — 200% text zoom breaks core layouts

Repro: apply 200% text-size simulation in the rendered browser, then inspect global overflow and clipped text at the commissioned widths.

Evidence:

- LENS, 320px: document horizontal overflow `53px`; `h1` clipped (`clientWidth 292`, `scrollWidth 359`); `span.score` right edge at `355.9px` on a `320px` viewport.
- Sector Overview, 320px: global overflow `87px`; action labels clipped: `BUY NOW`, `ALMOST READY`, `IN FAVOUR — DON'T CHASE`, `TAKE PROFITS`, `STAND ASIDE`; primary name `AI Agents & Applications Theme` clipped.
- Sector Money, 320px: global overflow `138px`.
- Sector Explore, 390px: global overflow `12px`; `Communication Services Sector` clipped.
- Sector Confluence, 390px: global overflow `54px`; four `TAILWIND` chips clipped; `Open group →` remains only `40px` high.
- Sector Explore, 768px: global overflow `401px`, including topbar/market-nav/compare-row overflow.

Blocker status: BLOCK. The candidates cannot be called accessible/responsive until 200% text zoom reflows without page-level overflow or clipped primary names/states.

### MAC-002 — BLOCK — Sector Central ZH is not a bilingual accessible page

Repro: load Sector candidate, activate `#lang`, inspect `html[lang=zh]`, visible text, placeholders, generated rows, and accessible names.

Evidence:

- `html lang="zh"` is set, but `#search` keeps English placeholder `Search sectors and themes…` and `aria-label="Search sectors and themes"`.
- Explore empty state after query `zzzzzz` remains English: `Nothing matches these filters.`
- Generated product rows remain English in ZH, including `Gold Miners Theme`, `Fresh entry confirmed`, `Theme`, and action/state text.
- Controls still show English mixed into the ZH shell: `Light`, `English`; market navigation remains English (`United States`, `China`, `Hong Kong`, `Canada`, `International`).
- LENS also leaks English accessibility strings in ZH: `#help` keeps `aria-label="How ranking works"` and the close control keeps English labeling.

Blocker status: BLOCK for Sector, major for LENS. ZH must not be translated chrome wrapped around English dynamic content and English assistive labels.

### MAC-003 — BLOCK — Focusable links include broken or placeholder destinations

Repro: inspect visible anchors in each rendered state.

Evidence:

- LENS: `.method-link` has `href="#method"`, but no element with `id="method"` exists. The help/sheet path sends keyboard and screen-reader users to a dead destination.
- Sector Overview: 7 visible/focusable placeholder links with `href="#"`.
- Sector Map: 1 placeholder link (`Open group →`).
- Sector Moving: 3 placeholder links.
- Sector Explore: 3 placeholder links.
- Sector Confluence: 10 placeholder links across group/queue rows.

Blocker status: BLOCK. These are broken journeys, not harmless prototype residue, because they are rendered as active destinations in customer-facing capability surfaces.

### MAC-004 — BLOCK — Charts and dense data views lack accessible equivalents

Repro: activate Map, Moving, and Confluence panels, inspect SVG/table semantics and data alternatives.

Evidence:

- Sector Map: one `svg` has `role="img"` and `aria-label="Sector rotation map"`, but `titleCount=0`, `descCount=0`, no focusable points, and no accessible point table/list. Visual point names include Gold, Silver, Next-Gen Compute, Medicine, Memory, Wireless, AI Software, and Semicap Equipment; those relationships are not exposed as a keyboard/screen-reader data structure.
- Sector Moving: `table.cross-table` has 5 rows and 4 headers inside `.cross-scroll`, but no `<caption>` and no table `aria-label`.
- Sector Confluence: sparkline SVG has `aria-label="Auto Manufacturers sparkline"` but no `role`, no title/desc, no textual data summary, and no focusable/data alternative.

Blocker status: BLOCK for production unless nonvisual alternatives are added or production proves equivalent accessibility elsewhere.

### MAC-005 — MAJOR — Invalid ARIA patterns on secondary controls

Repro: inspect roles in Sector DOM.

Evidence:

- `.panel.distribution` declares `role="tablist"`, but its children are plain buttons with no `role="tab"` or `aria-selected`; labels include BUY NOW, ALMOST READY, and other action lanes.
- `.universe-tabs` declares `role="tablist"`, but children are plain buttons using `aria-pressed`, not tabs.
- Sector `#theme` and `#lang` are stateful controls but lack `aria-pressed`. LENS correctly includes `aria-pressed` for analogous controls.

Blocker status: MAJOR. This may produce misleading screen-reader interaction models and needs repair before accessibility signoff.

### MAC-006 — MAJOR — Normal-size responsive states still clip/overflow important Sector content

Repro: inspect Sector candidate at commissioned widths without text zoom.

Evidence:

- Sector Overview 320/360/390/430: no page-level overflow, but `span.state-name` for `IN FAVOUR — DON'T CHASE` clips at all four widths (`clientWidth 105`, `scrollWidth 168` in the captured 320px case).
- Sector Overview 768: global overflow `33px`; clipped labels include `ALMOST READY`, `IN FAVOUR — DON'T CHASE`, and `TAKE PROFITS`.
- Sector Moving 768: global overflow `24px`.
- Sector Money 320/390: global overflow `138px` / `68px`.
- Sector Explore 768/820: global overflow `93px` / `43px`.

Blocker status: MAJOR, rising to BLOCK if these panels are required mobile/tablet customer journeys.

### MAC-007 — MAJOR — Actual touch path and focus trap are not production-proven

Repro: emulate coarse pointer/touch and mobile sheet; use keyboard-only checks where the browser backend allows.

Evidence:

- Coarse pointer emulation succeeded: `matchMedia('(any-pointer: coarse)')`, `(pointer: coarse)`, and `(hover:none)` all matched.
- In-app browser did not support CDP `Input.dispatchTouchEvent`; actual touch dispatch is therefore NOT_EVALUABLE.
- LENS mobile sheet at 390px opens with `aria-modal="true"`, focus moves to `#explainTitle`, scrim appears, body overflow locks, `.shell` gets `aria-hidden="true"` and `inert`, and Escape returns focus to `#help`.
- Browser Tab traversal was unreliable, so focus-trap cycling and Shift+Tab behavior are NOT_EVALUABLE rather than proven.
- With the sheet open, background focusable elements still appear in DOM queries; inert behavior needs real-browser proof/fallback verification.

Blocker status: MAJOR / production-proof required. The modal implementation has good signs, but actual keyboard trapping and touch are not proven.

### MAC-008 — MAJOR — Touch targets are below 44px in repeated primary controls

Repro: measure rendered button/link rectangles.

Evidence:

- LENS at normal widths has three undersized controls: `#themeBtn` about `65.8 × 40`, `#langBtn` about `60.6 × 40`, and `#help` at `40 × 40`.
- Sector small widths have 9–10 undersized controls depending on viewport/language, including `#theme`, `#lang`, and main tab buttons at 40px height.
- Sector Confluence at 390px and 200% text zoom leaves `Open group →` at 40px high.

Blocker status: MAJOR. Raise target size to at least 44 CSS px or provide compliant spacing/justification.

## Per-width and state evidence matrix

| Candidate / state | 320 | 360 | 390 | 430 | 768 | 820 |
|---|---:|---:|---:|---:|---:|---:|
| LENS normal EN/ZH | No global overflow; 3 small targets; ZH leaks English aria/text | Same | Same | Same | Same | Same |
| LENS 200% text | Overflow `53`; `h1` clipped; score off viewport | NOT_EVALUATED | No overflow found; `#help` still 40px | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED |
| LENS explain desktop | N/A | N/A | N/A | N/A | Popover opened, `aria-modal=false`, focus remained on trigger, Escape returned focus; `#method` target missing | Same class of desktop evidence |
| LENS explain mobile | Modal sheet opened; scrim/body lock/aria-hidden/inert set; focus to title; Escape returned focus | NOT_EVALUATED | Same evidence at 390 | NOT_EVALUATED | N/A | N/A |
| Sector Overview normal | No global overflow; `IN FAVOUR — DON'T CHASE` clipped; 7 placeholders; ZH leaks English | Same | Same | Same | Overflow `33`; multiple labels clipped | No global overflow; labels still clipped |
| Sector Map normal | No global overflow; SVG lacks data alternative; 1 placeholder; inner scrollers | NOT_EVALUATED | No global overflow; same semantic issue | NOT_EVALUATED | No global overflow captured | No global overflow captured |
| Sector Moving normal | No global overflow; table has no caption/aria label; 3 placeholders | NOT_EVALUATED | Same | NOT_EVALUATED | Overflow `24`; same table issue | No global overflow captured |
| Sector Money normal | Overflow `138` | NOT_EVALUATED | Overflow `68` | NOT_EVALUATED | No overflow captured | No overflow captured |
| Sector Explore normal | No global overflow; 3 placeholders | NOT_EVALUATED | No global overflow; ZH empty/search strings fail | NOT_EVALUATED | Overflow `93` | Overflow `43` |
| Sector Confluence normal | No global overflow; 10 placeholders; sparkline lacks robust alt/data equivalent | NOT_EVALUATED | Same | NOT_EVALUATED | No overflow captured | No overflow captured |
| Sector 200% text | Overview overflow `87`; Money overflow `138` | NOT_EVALUATED | Explore overflow `12`; Confluence overflow `54` | NOT_EVALUATED | Explore overflow `401` | NOT_EVALUATED |
| Sector hash routing | Canonical and legacy hashes passed; active mobile tab scrolled into view | NOT_EVALUATED | In-page Open Confluence link switched to Confluence | NOT_EVALUATED | Keyboard-seeded Arrow/Enter tab activation passed | Same desktop evidence |
| Loading/stale/partial/error | NOT_EVALUABLE: static candidate did not expose these states | Same | Same | Same | Same | Same |

Legacy hash routing tested as PASS for `#overview`, `#map`, `#moving`, `#money`, `#explore`, `#confluence`, plus `#actnow-section`, `#si-map`, `#si-movement`, `#si-money`, `#explore-section`, `#si-confluence`, and `#read-health`.

Reduced motion passed for exposed motion. LENS `#explain` and `#scrim` transition durations became `0s` under `prefers-reduced-motion: reduce`; both candidates disable smooth scrolling under reduced motion.

Touch/coarse pointer is PARTIAL / NOT_EVALUABLE for actual touch events. Media emulation worked, but CDP touch dispatch was unsupported.

Keyboard-only is PARTIAL. Sector main tabs worked after seeded focus/click: Arrow moved focus, Enter activated and updated hash/panel. LENS Escape/focus return worked. Actual Tab traversal/focus-trap cycling was NOT_EVALUABLE due browser backend behavior.

## Exact required repairs

1. Rework both candidates for real 200% text zoom: no document-level horizontal overflow, clipped primary names, clipped state chips, or off-viewport scores/actions at 320–820px.
2. Complete ZH, including JS-generated rows, empty states, placeholders, accessible names, chart labels, state/action labels, controls, and correction/freshness/help text.
3. Replace visible `href="#"` anchors with real destinations or non-link disabled controls. Add the real LENS `#method` target or remove the dead method link.
4. Add accessible chart/data alternatives: a point list/table for Map; caption or `aria-label` and sane horizontal-scroll semantics for Moving; role/title/desc plus textual numeric trend summary or data table for Confluence.
5. Fix ARIA semantics: use real tabs under tablists, or use group/toolbar semantics with `aria-pressed`; add `aria-pressed` to Sector theme/language controls.
6. Raise primary touch targets to at least 44 CSS px.
7. Prove sheet behavior in production browsers: Tab/Shift+Tab trap, Escape, focus return, background inert/fallback, and screen-reader role/name.
8. Add and test loading, empty, stale, partial, and error states across EN/ZH and mobile/tablet widths.

## Strengths

- LENS base responsive layout is clean at 320–820px without text zoom; no document-level overflow was found.
- LENS mobile explain sheet has several correct modal signs: `aria-modal=true`, title focus, scrim, body lock, shell aria-hidden/inert, Escape close, and focus return.
- LENS reduced-motion behavior is correct for exposed transitions.
- Sector canonical and legacy hash routing works, including active-tab visibility in the 320px horizontal rail.
- Sector main-tab keyboard behavior is directionally sound after focus is seeded.
- Sector normal 320/390 layouts often contain overflow inside intended internal scrollers rather than the whole page, though several panels still fail.

## What must be production-proven

- Real browser 200% zoom/text zoom across Safari/Chrome-class engines.
- Actual touch behavior on iOS/Android/coarse-pointer devices.
- Real Tab/Shift+Tab traversal, focus trap, outlines, and focus return.
- Accessibility-tree behavior for modal, tabs, segmented controls, charts, tables, and SVGs.
- Complete EN/ZH parity after production data rendering.
- Real data-backed loading, empty, stale, partial, and error states.
- Real destinations for every focusable action/link, including correction/freshness/help journeys.
- Primary-name truncation against live payloads with long names.

## Evidence, gaps, and deviations

Both freeze candidates were rendered from frozen commit `da83976ece01c54d5ab07307e68118693e100a58` through the local browser at 320, 360, 390, 430, 768, and 820 widths. The critic tested EN/ZH toggles, LENS explain popover/sheet, Sector canonical and legacy hashes, reduced motion, coarse-pointer media emulation, 200% text-size simulation, visible placeholder links, SVG/table semantics, and the empty Explore search state.

Designer rationale was not read. Static candidates did not expose loading/stale/partial/error states, so those are NOT_EVALUABLE. Actual CDP touch dispatch was unsupported. Actual Tab traversal/focus-trap cycling was unreliable and is marked NOT_EVALUABLE. The 200% pass used temporary browser-side computed font-size inflation; production must prove real browser zoom/text zoom.

No material deviations: unsupported axes were marked NOT_EVALUABLE, not inferred. No files were edited by the critic and no implementation or repair was performed.
