# XPV2-SC-R3B — Responsive behavior contract (Deliverable 5)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b/COMMISSION.md`
§21 deliverable 5. Written for Sol's four fresh independent critics
(Product Regression, Visual/Taste, Mobile/Accessibility, Data/Authority)
and for a future R3C session. Cold-stranger rule: every claim cites its
source file/line. Sources: `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/shell.html`
(global shell/rail), the six `build/views/*.html` partials (per-view CSS,
grep-verified `@media` blocks), `build/DESIGN_SYSTEM_SPEC.md` §7/§12
(system-level breakpoint law), and `build/QA_ATTACK_REPORT.md` §1/§2/§5
(the measured QA-gate outcomes).

**Breakpoint ladder used throughout** (spec §12): **1440** shell max ·
**1100** rail narrows to 172px, evidence rail collapses to one column ·
**900** (Map only) scroll-hint appears · **820** (44px-floor gap repair
only, `shell.html:606-608`) · **767** grid switcher / ledge goes 2-column ·
**640** row reflow, column legend drops · **359** nav becomes 2×3, ledge
1-column. Per spec §12: *"390 is the design floor; 320 must not overflow."*
Not every view recomposes at every rung in this ladder — the per-view
tables below record exactly which rungs move which view.

---

## 0. Global shell — rail and top-level navigation (`shell.html`)

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤1100px | `--si-rail-w` narrows 200px → 172px; rail padding drops to `9px`; `.si-view-btn` font drops to 12.5px, `min-height:44px` (touch-target floor arrives here, before the 767 grid switch); stage padding compresses; `.r3-stagegrid` collapses to one column | `shell.html:551-560` |
| ≤820px | `.r3-seg button{ min-height:44px; }` — QA2-06 repair: the Map universe segmented control was 40.0px at 768–820 before this rule existed; comment: "a repeated/primary target needs the same floor through 820, not only ≤767" | `shell.html:602-608` |
| ≤767px | Rail becomes a sticky **3×2 grid** (`grid-template-columns:repeat(3,minmax(0,1fr))`), all six destinations visible, no horizontal scroll; `--r3-mnav-h` becomes 104px (the mobile-nav-height CSS var the scroll-offset law consumes, §1 below); eyebrow/footer hidden; ledge grid (global `.r3-ledge-grid`, consumed by both Action views) goes 2-column with "Stand aside" spanning full width via `:last-child{grid-column:1/-1}`; page `<h1>` demoted to one line, budget handed to the answer | `shell.html:561-601` |
| ≤359px | Nav grid becomes **2×3** (`repeat(2,minmax(0,1fr))`); `--r3-mnav-h` becomes 158px; `.r3-ledge-grid` goes 1-column; stage padding compresses further; answer line drops to 17.5px | `shell.html:609-619` |

**44px touch-target floor implementation** (spec §12, "Repeated/primary
mobile targets ≥44 CSS px"): bought three separate ways depending on
component, all grep-confirmed:
1. **Padding + min-height** on the component itself — rail cells 52px
   (`.si-view-btn{ min-height:52px }`, `shell.html:572`), ledge cells 56px
   (`.r3-ledge-cell{ min-height:56px }`, `shell.html:586`), rows 64px
   (spec §2 skeleton table).
2. **A dedicated breakpoint-gap repair** rather than a floor baked into the
   base rule — `.r3-seg button` at `shell.html:606-608`, added specifically
   to close the 768–820px iPad-portrait gap QA2-06 measured (§4 below).
3. **Explicit `min-height`/`min-width` pairs on tablet** (1100px rung, not
   767px) for Explore's segmented/filter controls —
   `.r3-seg button, .exp-legbtns button, .tm-years button{ min-height:44px;
   min-width:44px; }` (`explore.html:404-406`), justified inline: "768–1100
   is the iPad range the shell already treats separately, and a finger is a
   finger at 820 as much as at 390."

## 1. Scroll-offset law (commission §14) — the mechanism, once, for all six views

`si_workspace.js` lands legacy anchors with `scrollIntoView({block:'start'})`,
which honours CSS `scroll-margin-top` (spec §7, "Scroll-offset law"). The
shell wires one property, consumed by every view via a single selector:

```
.si-view [id], .si-view[id]{
  scroll-margin-top: calc(var(--ref-sticky-offset) + var(--r3-mnav-h) + 16px);
}
```

`--r3-chrome-h:40px` is the sticky top-bar height; `--ref-sticky-offset`
defaults to it (`shell.html:169,184`) but is meant to be overwritten by a
runtime measurement of the actual sticky-bar height (`wireStickyOffset()`,
per `shell.html:180-184`'s comment). `--r3-mnav-h` is 0px on desktop, 104px
≤767px, 158px ≤359px (§0 above) — the mobile nav strip's own height, added
to the sticky offset so a phone anchor is never buried under **both** bars.

**A shipped specificity bug, and its fix.** Each view partial's own
`<style>` block (loaded *after* `shell.html`'s in the assembled document,
per `README_BUILD.md`'s assembly order) originally repeated this same rule
with a **static** fallback instead of consuming the measured
`--ref-sticky-offset` — equal specificity, later source order, so the
per-view rule silently won and the runtime measurement was discarded. The
fix (grep-confirmed at `explore.html:88-95`, `money.html:84`) reorders the
`calc()` to consume `--ref-sticky-offset` first and only fall back to the
static token when the partial is loaded standalone. See `design_notes.md`
§5 for the load-bearing caveat: **this repairs only the value-consumption
half of the historically-recorded F-6 defect. The landing-overshoot half —
`scrollIntoView` firing before async-mounted organs above the target finish
growing — has no fix-site citation anywhere in the codebase as of this
drafting session** (grep for `requestAnimationFrame`/`re-scroll`/`settle`/
`overshoot` across `build/views/*.html` and `build/shell.html`: zero
matches). Treat `#tm-mount` and `#grader` deep-link landings as an open
risk, not a closed gate, until re-measured.

## 2. Per-view breakpoints, phone composition order, and in-container scroll

### Overview (`overview.html`)

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤1100px | `.r3-ov-grid` (the leadership-context grid) collapses to one column | `overview.html:201-203` |
| ≤767px | **Phone recomposition, explicit order via CSS `order`**: answer (1) → `#actnow-section` action board (2) → `#regime` leadership context (3) → `#ov-watch-band` Bottoming Watch (4) → `#grader` (5). Inline comment: "On the desk the leadership context reads as a quiet preamble between the answer and the board; on a phone that preamble costs a whole swipe before the reader reaches the thing the view is FOR." `.r3-ov-hand` (the hand-off card) drops to one column, its arrow rotates 90°; `.r3-gr` (grader grid) drops to one column | `overview.html:204-220` |
| ≤359px | `.r3-watch-cell > strong` wraps rather than clips | `overview.html:221-223` |

**Phone composition order**: answer → 5-lane action board → leadership
context → Bottoming Watch → grader. This is a genuine reorder (leadership
context moves from position 2 on desktop to position 3 on phone), not a
narrowed desktop stack.

**In-container scroll surfaces**: none identified specific to Overview —
the action board's fold/reveal mechanism (`FOLD_CAP=3`, `overview.html:457`)
is a DOM insert/remove, not a scroll container.

**44px floor**: Overview's five action-lane tab targets measured 294×56px
at 320px in QA report Gate 1 — above floor with margin (§4 below).

### The Map (`map.html`)

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤900px | `.r3-scrollhint` becomes visible (`display:inline`) — "Scroll the table sideways for every column" / "左右滑动表格查看全部列" appears next to the accessible ranked-list table's as-of stamp | `map.html:88,314-315` |
| ≤767px | **Phone recomposition via CSS Grid `grid-template-areas`**: `"summary" "detail" "list" "figure"` — quadrant summary, then selected-object detail, then the accessible ranked table, then the chart figure last, collapsed behind a disclosure. Chart container is clipped via `max-height:0; overflow:hidden; visibility:hidden` when collapsed — **never `display:none`** (spec §8.1 mount-width law, explicit inline citation). Quadrant tiles go 2-column; the rotation table gets a `min-width:520px` floor (forcing its own horizontal scroll, not the page's); the cycle-clock reasoning-chain disclosure summary drops its chevron and reflows to two rows | `map.html:406-421` |
| ≥768px (min-width) | The phone disclosure toggle button is hidden — "the disclosure is a phone affordance only; on the desk the map is simply there" | `map.html:422-427` |
| ≤359px | Quadrant tiles go 1-column; the cycle-clock SVG height drops to 180px | `map.html:428-431` |

**Phone composition order** (QA report Gate 2, measured live at 390px,
`top` = document-space paint order): answer (top 212) → quadrant summary
(536) → selected-object card (805) → accessible `table#rvx-board` behind
`overflow-x:auto` → full chart plot behind an explicit disclosure
(`aria-expanded`, top 2054). Desktop order differs meaningfully: the SVG
sits at top 322, *above* the quadrants at 871 — QA report's own framing:
"the mobile order is a genuine re-composition, not a CSS shrink of the
desktop stack."

**In-container scroll surfaces**:
- `table#rvx-board` (the accessible rotation-map equivalent) — scrolls
  inside `overflow-x:auto` parent at phone widths (`parentW 358` vs
  `table 606.2` measured at 390px, QA report Gate 2); visible hint = the
  `.r3-scrollhint` text at ≤900px (`map.html:88,314-315`).

**44px floor — the one confirmed FAIL in the whole width sweep.** QA
report Gate 5/QA2-06: the Map universe segmented control ("Themes N" /
"Sectors N") measured **40.0px** (not 44px) at 768 and 820, both languages,
before the `shell.html:602-608` repair existed. That repair (`.r3-seg
button{ min-height:44px }` at ≤820px) is grep-confirmed present in the
current shell; **this drafting session did not re-run the QA harness to
confirm the fix is measured-clean** — see `design_notes.md` §5.

### What's Moving (`moving.html`)

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤1100px | `.r3-vel` (velocity/leg grid) drops to 3 columns; `.r3-wm` (whole-market map + lists grid) collapses to one column, `grid-template-areas:"plot" "lists"` | `moving.html:260-263` |
| ≤767px | Transition rows stack: two legs on their own lines with the CSS-drawn source→destination mark between them, day-count and reason underneath — "never a squeezed three-column grid" (inline comment). `.r3-vel` drops to 2 columns; `.r3-cross` (crosscurrents) drops to one column. **Whole-market plot follows its lists**, `grid-template-areas` flips to `"lists" "plot"` — the plot is collapsed via `max-height:0; overflow:hidden; visibility:hidden`, explicitly never `display:none` (spec §8.1 citation repeated inline) | `moving.html:264-283` |
| ≥768px (min-width) | Phone whole-market-plot toggle button hidden | `moving.html:286-287` |
| ≤359px | `.r3-vel` drops to 1 column; `.r3-deskgrid` (Desk Watch grid) drops to 1 column | `moving.html:288-292` |

**Phone composition order**: transition rows and lists first, whole-market
plot last (behind disclosure) — the same "lists before the visualization,
plot collapsible not removed" pattern as Map, applied to Moving's own
`#rotation-app` mount.

**In-container scroll surfaces**: `.r3-tr-body` (the track-record table
body, `moving.html:150`) is `overflow-x:auto` — the one explicitly
scrolling container inside Moving; no separate visible "scroll sideways"
hint text was located for it in this session's grep (**verify at
freeze** — Map's `.r3-scrollhint` pattern was not found reused here).

**44px floor**: no Moving-specific target-size finding in QA report §1.5
(Gate 5's 4 failing cells were all Map, §4 below); Moving's disclosure
buttons (`Hide the full map` analogue, "Show the whole-market map") were
counted among QA report §2's phone-only additive disclosures, all passing
the width sweep at 216/216.

### Money & Breadth (`money.html`)

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤1100px | `.mny-verdict` grid drops to one column; `.mny-tm` (Time Machine mount, shared class name with Explore's) gets `min-height:320px`; `.r3-disc summary{ min-height:48px }` — the touch-band note explicitly cross-references Explore's twin comment | `money.html:380-385` |
| ≤767px | `.mny-legs`, `.mny-measures` drop to one column; the measure rows (`.mny-m`) become an explicit 2-column grid (label left, value right-aligned, sub-line spanning both, `grid-column:1/-1`); `.lead-hero` (leadership hero) drops to one column; driver-leg rows (`.drv`) reflow to name + trailing column with the reason spanning full width; `.mny-tm` grows to `min-height:380px`; disclosure summaries stay at 48px | `money.html:386-403` |
| ≤359px | Verdict cells, measure rows, and leadership cells drop padding to `12px 13px`; heatmap box padding drops to `12px` | `money.html:404-409` |

**Phone composition order**: no explicit `order:` reassignment was found
for Money (unlike Overview/Map/Moving) — the DOM's own source order (answer
→ verdict card → breadth → flows → heatmap → leadership) is preserved at
every width; the recomposition here is entirely **grid-to-stack**, not
**reorder**. **Verify at freeze**: confirm this against the live rendered
DOM if a critic needs an authoritative phone reading order, since this
session inferred "no reorder" from the absence of `order:` rules rather
than from a live paint-order measurement (contrast Map/Moving, where QA
report Gate 2 measured live paint order directly).

**In-container scroll surfaces**:
- `.r3-tblbox{ overflow-x:auto }` (`money.html:128`) — the heatmap
  text-equivalent table's own scroll box.
- `.mny-flowfrag .scf-wrap{ overflow-x:auto }` (`money.html:263`) — the
  extracted `#sc-flows` fragment's three embedded tables scroll inside this
  wrapper, not the page.

No dedicated visible "scroll sideways" hint text was located for either
Money scroll container in this session's grep (**verify at freeze**).

**44px floor / zoom findings**: QA2-01 (`.r3-tag{white-space:nowrap}` zoom
overflow) and QA2-05 (clipped "Consumer Defensive" sector name at css820
zoom, zero document overflow) are Money-specific findings — see §4 below.
Both have grep-confirmed fix-site comments (`money.html:372`, `money.html:298`)
per `design_notes.md` §5; neither was independently re-measured by this
session.

### Explore (`explore.html`)

Explore's own comment block states its responsive law most explicitly of
any view (`explore.html:395-398`, quoted verbatim):

> "≥1101 the full table, every column / 768–1100 / 820 the table scrolls
> INSIDE its own box — the page never does (§9) / ≤767 the table RECOMPOSES
> into labelled rows: no horizontal scroll on a phone, nothing dropped, the
> name is the card title and the six windows form a grid."

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤1100px | `#chart{ min-height:320px }`; **44px/44px min-height+min-width floor** on `.r3-seg button`, `.exp-legbtns button`, `.tm-years button`, plus `min-height:44px` on `.lchip`, `.ne-tk`, `.bnm`, `.rangeN` — the "touch band" applied at tablet width, not just phone; `#btable th` padding grows to `14px 12px`; `.exp-leglist` and `.tm-years` scroll containers get `max-height` caps (220px / 140px) | `explore.html:399-414` |
| ≤767px | **`#btable` recomposes from a table to labelled cards**: `overflow-x:visible` on the box (the horizontal-scroll affordance is deliberately turned OFF here, replaced by the card layout); `thead` hidden; each `tbody > tr` becomes a `display:grid` 3-column card with `td.bname` and `td.spark-td` spanning the full row width, numeric cells left-aligned and bold, a `.clab` label injected before each value. Filter/mode/year buttons get `min-height:44px`; `.ne-legs` (Forming Narratives leg grid) drops to 3 columns; `.ne-grid` drops to 1 column; `#chart{ min-height:280px }` | `explore.html:416-445` |
| ≤359px | Table cards drop to a 2-column grid; Forming Narratives cards/legs drop padding and columns further | `explore.html:447-450+` (block continues past the read window) |

**Phone composition order**: `#btable`'s row-to-card recomposition is the
single most structurally significant per-view change in the whole
artifact — a table element genuinely becomes a card list at ≤767px via
`display:block`/`display:grid` on `thead`/`tbody`/`tr`/`td`, not merely
CSS-hidden columns.

**In-container scroll surfaces**:
- `.r3-tblbox{ overflow-x:auto }` (`explore.html:136`) — the comparison
  table's own scroll box, active at 768–1100/820 per the view's own stated
  law; turned off (`overflow-x:visible`) at ≤767 because the table has
  already recomposed into cards by then.
- `.exp-leglist` (`max-height:220px`, `explore.html:412-413,439`) and
  `.tm-years` (`max-height:140px`, `explore.html:413`) — vertically
  scrolling selector lists, capped at both tablet and phone widths.

No dedicated visible "scroll sideways" hint text located for
`.r3-tblbox` in Explore (**verify at freeze** — same gap as Money's
scroll boxes above; Map is the only view confirmed to carry an explicit
scroll-hint string).

**44px/zoom findings**: QA2-02 (Forming Narratives ticker rows, EN and ZH
at css320/390), QA2-03 (mode segment no-wrap) are Explore-specific — §4
below. Both have grep-confirmed fix-site comments
(`explore.html:336`, `explore.html:187,203`); neither independently
re-measured.

### Confluence (`confluence.html`)

| Breakpoint | What changes | Citation |
|---|---|---|
| ≤767px | **Sol §13 amendment, cited inline**: "all four universe selectors stay visible — two rows of two rather than a strip that scrolls the last one off the right edge." `.r3-uni` becomes a 2-column grid; member/cell/card grids (`.r3-mem`, `.cf-cells`, `.cf-cards`) switch to `auto-fill` with per-component minimums (140px/146px/190px) | `confluence.html:301-310` |
| ≤359px | Universe selector, member grid, and cell/card grids all drop to a single column | `confluence.html:311-316` |

**Phone composition order** (commission §13): selected/Entry-now focus
object → Tailwind queue → Late/Headwind compact list → deeper group/member
detail — this ordering is a commission requirement rather than a `.r3-*`
CSS reorder observed by this session; **verify at freeze** — this session
did not independently confirm live phone paint order for Confluence the
way QA report Gate 2/3 did for Map (Gate 3 confirms state-label/count
legibility and universe-selector visibility at 320/390 but does not record
a full section-by-section paint-order table the way Gate 2 does for Map).

**In-container scroll surfaces**: `[data-view="confluence"] .cf-divs
.r3-tbl{ min-width:340px }` (`confluence.html:297`) forces the divergence
table into its own scroll box rather than the page; the main comparison
table's own `.r3-tblbox` scroll pattern (shared class name/mechanism with
Explore/Money, per spec §9 component vocabulary — "the box scrolls, the
page never does") applies here too, though this session did not grep a
Confluence-specific `.r3-tblbox` occurrence separately from the shared
class definition.

**44px floor**: QA report Gate 3 confirms all four universe selectors at
44px height at 320px and 390px in both languages; no Confluence-specific
Gate 5 finding was recorded.

## 3. Measured QA-gate outcomes (`QA_ATTACK_REPORT.md`)

This section states the gate-by-gate **measured** result as of the QA
report's own testing pass; per `design_notes.md` §5, this drafting session
did not re-run these probes, so these are cited as the most recent
available evidence, not re-verified facts.

| Gate | Scope | Verdict | Evidence |
|---|---|---|---|
| Gate 1 | Overview phone, five action-state labels + counts at 320px, no h-scroll, no hidden state, ≥44px targets | **PASS** | 5 tabs measured 294×56px, all visible, document overflow 0, visible-control count constant across all 9 swept widths (`QA_ATTACK_REPORT.md` §1.1) |
| Gate 2 | Map phone composition — full map reachable, not a shrunken desktop SVG | **PASS** | Measured paint order (§2 above); desktop places the plot above the quadrants, phone places it last behind a disclosure — "a genuine re-composition, not a CSS shrink" (§1.2) |
| Gate 3 | Confluence — five state names + counts legible at every width, no population-scaled label containers, four universes on phone | **PASS** | 5 states visible 320→1440px; `.r3-state` label widths track string length only (byte-identical across widths); 4/4 universe tabs at 44px on 320/390 (§1.3) |
| Gate 4 | 200% zoom, all six views × 320/390/768/820 | **FAIL — 6 of 48 cells** | +60px (Money, css320 EN), +36px (Explore, css320 EN), +32px (Explore, css320 ZH), +25/26px (Money, css390 EN), +4px (Overview, css320 EN), +1px (Explore, css390 EN), plus one clipped-primary-name cell at css820 Money with zero document overflow (QA2-01 through QA2-05) (§1.4) |
| Gate 5 | ≥44 CSS px repeated/primary mobile targets, six views, ≤820px | **FAIL — 4 of 72 cells** | Map universe segment buttons measured 40.0px at 768px and 820px, both languages (QA2-06) (§1.5) |
| Gate 6 | Scroll-offset law — 6 canonical + 21 legacy anchors + `#read-<id>` + empty/unknown hash | **PASS — 32 landings measured** | Every resolved target landed 159.5–671.7px against a 148.8px sticky-chrome bottom at 390px; `#sc-top` no-op is the recorded production seam, not a finding (§1.6) |
| Width sweep | 9 widths × 2 themes × 2 langs × 6 views = 216 cells, 100% zoom | **PASS — 216/216 clean** | Zero document overflow, zero off-screen leaf nodes, zero clipped state labels, zero clipped primary names, in every cell; zero capabilities lost on phone (set-difference of visible controls, 1440 vs 390, per view+lang) (§2) |

**Gate 4 and Gate 5 failures both have grep-confirmed fix-site comments**
in the current `build/views/*.html` (QA2-01 through QA2-06, listed in
`design_notes.md` §5's fix-history table) — but neither gate's re-run
result exists on disk. Treat both as **open until re-measured**, per this
document's cold-stranger rule and `design_notes.md` §5.

## 4. Summary — what a fresh critic should re-measure first

1. Gate 4 (200% zoom overflow, 6 cells) and Gate 5 (44px floor, 4 cells) —
   fix-site comments exist, no re-probe evidence exists.
2. The F-6 landing-overshoot half at `#tm-mount` and `#grader` — no fix-site
   comment exists at all (§1 above).
3. Confluence's phone paint order (commission §13's required sequence) —
   never measured live the way Map's was (Gate 2).
4. The two unlabelled scroll containers (Money's `.r3-tblbox`/`.scf-wrap`,
   Explore's `.r3-tblbox`) — confirm whether a visible scroll-sideways hint
   analogous to Map's `.r3-scrollhint` exists or is owed.
