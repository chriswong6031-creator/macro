# XPV2 Turn-3 R2 — Independent Visual/Taste Critic

- Reviewer: `codex-xpv2-visual-taste-20260820`
- Frozen artifact: `da83976ece01c54d5ab07307e68118693e100a58`
- First pass frozen: `2026-08-20 07:20:49 PDT`
- First-pass verdict: `BLOCK`
- Final verdict after rationale quarantine: `BLOCK`

The reviewer followed the Browser skill, rendered the local references through a static
server, captured desktop/mobile/theme/language states, and read the author rationale only
after freezing the first verdict. The rationale did not resolve the visual blockers and in
several places confirmed the acceptance bar the render misses.

## Findings

### VTC-001 — BLOCKER — Hash routing and sticky chrome clip the page answer

Sector's sticky topbar is defined at `MASTERMIND_SECTOR_CENTRAL...html:40-41` and hash
canonicalization at `:782-822`. Browser evidence at 1440 dark `#overview`: `scrollY=86`, h1
`y=22..69.8`, topbar bottom `58`, visibly chopping “Where leadership is shifting.” At
390/320, `scrollY=149` and the answer sits under both topbar and sticky tab rail.
`#confluence` repeats the defect.

Repair: add explicit scroll-offset discipline for every canonical/legacy hash; prevent
automatic hash scroll under sticky chrome and prove Overview, Moving, Confluence, and legacy
anchors. Second pass: **upheld**.

### VTC-002 — MAJOR (first-pass blocker downgraded) — Mobile action distribution is squeezed

Mobile `.distribution` uses five `minmax(132px,1fr)` columns with local scroll at `:328-329`.
At 390, `clientW=360`, `scrollW=660`; at 320, `clientW=290`, `scrollW=660`. The third lane is
cut and Take profits/Stand aside are hidden without a visible continuation affordance.

Repair: use a mobile state selector/count ladder with clear continuation, active state
visibility, and all five counts legible before selected rows. Second pass: **downgraded**, not
withdrawn; local horizontal scroll is allowed, but this execution is not.

### VTC-003 — BLOCKER — Confluence hides the most important bucket and full state coverage

The proportional spread uses `1fr 16fr 21fr 18fr 9fr` and `overflow:hidden` at `:263-271`.
Desktop's Buy-ready cell was `17.5px` wide while its label was `61.5px`, placing/clipping the
label outside the cell. At 390, `scrollW=480` vs `clientW=360` and Headwind is hidden. At
320, only Buy-ready, Tailwind, and Neutral appear initially.

Repair: separate proportional visual weight from readable fixed labels or use a count strip;
no Confluence label/count may be hidden in the default viewport. Second pass: **upheld**.

### VTC-004 — MAJOR — Mobile Map is a tiny desktop chart in a giant frame

The SVG height is 500 desktop and 400 mobile at `:166-170,352-353`. At 390 it rendered
`330x400`; selected detail began at `y=752`; point/quadrant labels were visually tiny. The
chart dominates the fold without communicating.

Repair: answer and selected object first, reduced annotation density, a readable compact map
or quadrant summary, and a detail sheet/list fallback. Second pass: **upheld**.

### VTC-005 — MAJOR — ZH is incomplete and visually incoherent

Dynamic Overview rows are English-only at `:838-886`; Explore rows are English-only at
`:895-912`. Desktop ZH still shows Gold Miners, Theme, Fresh entry confirmed, Buy now,
Trending, and English metadata. LENS leaves `Entry T2` untranslated at
`MASTERMIND_LENS...html:214`.

Repair: add ZH twins for kind, reason, state, action, placeholder, and support labels; retain
English proper nouns only where product policy explicitly allows. Second pass: **upheld**.

### VTC-006 — MAJOR — Overview remains a compressed dashboard stack on mobile

At 390 Overview `scrollH=1919`; at 320 `scrollH=1995`. After the clipped answer, the state
strip, selected rows, and Almost-ready rail precede the rest, while multiple panels carry
similar visual weight.

Repair: retain the authorized order but establish one primary state object and selected rows;
collapse or visibly demote the Almost-ready rail and early turns on phone. Second pass:
**upheld in weighting**, while accepting the packet's module order.

### VTC-007 — MAJOR — Hand-built local chrome must not become production law

The candidate hand-authors topbar, brand, market nav, and controls at `:392-400`, omitting
real search/Terminal affordances while looking like product chrome. It contributes to the
sticky clipping and risks a third header idiom.

Repair: frame the reference as content inside the canonical shell or render canonical chrome;
production must not port this topbar. Second pass: **upheld as a condition**.

### VTC-008 — MAJOR — Glyph-based sci-fi styling undercuts the institutional tone

Sidebar glyphs `✦ ◎ ↻ ≈ ⌕ ⌁` appear at `:404-409`; LENS uses a lightning badge at `:214`
and arrow tile at `:237`. In an otherwise calm design these read as mockup shorthand.

Repair: use sanctioned monoline icons or remove redundant decoration. Second pass:
**upheld**; the packet itself says instrumentation, not ornament.

### VTC-009 — MAJOR/CONDITION — LENS has accidental page-level emptiness

At 1440x1000 dark EN, LENS rendered one 360px card and footnote in a 980px region; product
height was `434px` and most of the viewport was unused canvas. It feels like a component
floating on a page rather than a full Intelligence Hub reference.

Repair: classify it explicitly as a component/interaction specimen or place it in realistic
Hub context. Second pass: **downgraded to a condition** because the rationale frames LENS as a
semantic foundation/first consumer.

### VTC-010 — MINOR — LENS mobile sheet's title focus looks browser-default

The sheet focuses `#explainTitle` at `MASTERMIND_LENS...html:324`. At 320 dark EN the two-line
title showed a rectangular blue default-looking outline.

Repair: preserve focus on static titled content but style it with a deliberate house focus
ring on the sheet/title block. Second pass: **downgraded** to polish only.

## Strongest adverse state

`MASTERMIND_SECTOR_CENTRAL...html#confluence`, 320px, dark EN, initial load: the answer is
hidden under sticky chrome; universe controls consume a tall block; the distribution exposes
only three buckets; Headwind/Late are offscreen; and Auto Manufacturers wraps heavily. It
looks like squeezed desktop, not a native phone product.

## Vibe-coded / childish risks

- Vibe-coded: proportional Confluence spread, mobile Map SVG, hand-built reference topbar,
  Unicode sidebar icons, isolated LENS page shell.
- Childish sci-fi risk: lightning badge, magic-star tab icon, arcane nav symbols, and LENS
  arrow tile. Desktop quadrant map itself is not childish; it weakens only when shrunk.

## Strengths

- R2 is materially calmer than baseline production.
- Desktop Moving is aligned, restrained, and task-clear.
- Desktop light Overview is credible as a research workspace.
- LENS copy and modal structure are concise; the desktop popover feels premium when treated
  as a component.
- R2 removes much of the baseline mobile noise and persistent-chrome interruption.

## Exact repairs

1. Fix sticky chrome/hash scroll occlusion.
2. Redesign mobile action and Confluence distributions so no state/count/label is hidden by
   default and continuation is explicit.
3. Create a true mobile Map reduction.
4. Complete ZH dynamic-row and placeholder twins.
5. Treat fake chrome and the empty LENS shell as non-canonical, or replace them with canonical
   context.
6. Replace glyph/emoji shorthand with sanctioned iconography.
7. Style LENS mobile focus deliberately.

## Return packet

- **STATUS:** complete, read-only, browser-rendered independent review.
- **RESULT:** `BLOCK`, with surviving blockers `VTC-001` and `VTC-003`.
- **EVIDENCE:** local server `127.0.0.1:8876`; 1440x1000 dark/light EN/ZH; 390x844;
  320x844; Overview, Moving, Confluence, Map, LENS open/closed; provided baselines; rationale
  only after first verdict.
- **GAPS:** no authenticated production or real-payload verification; static candidates do
  not expose loading/empty/stale/partial/error states.
- **DEVIATIONS:** no repo mutations and no child agents. The unavailable legacy
  `frontend-design` skill was replaced by binding doctrine/design-system docs plus Browser.
