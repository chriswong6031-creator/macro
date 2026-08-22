# XPV2-SC-R3B — Design notes (Deliverable 2)

Commission: `research/reference_integrity/mastermind-xpv2-sector-r3b/COMMISSION.md`
§21 deliverable 2. Written for Sol's four fresh independent critics (§27:
Product Regression, Visual/Taste, Mobile/Accessibility, Data/Authority) and
for a future R3C session. Cold-stranger rule: every claim below cites its
source file; nothing here assumes memory of the R3B conversation.

Primary sources consumed: `COMMISSION.md`; `ORCHESTRATOR_ADJUDICATIONS.md`;
`mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b/build/DESIGN_SYSTEM_SPEC.md`
("the spec"); `build/QA_ATTACK_REPORT.md` ("QA report");
`research/reference_integrity/mastermind-xpv2-sector-r3b/capability_crosscheck.md`
("the cross-check"); the six `build/views/*.html` partials and `build/shell.html`
(read directly, grep-verified — see §5 for exact citations).

---

## 1. North star — "Quiet Conviction", and how the spec makes it structural

Commission §5 states the north star in prose: *"Sector Central should feel
like an institutional research terminal that has already decided what
deserves attention"* — less prose, fewer boxes, fewer repeated badges,
stronger names, stronger relationships, clearer hierarchy, deeper evidence
one step away (§5). The Principal Design Lead's answer to that prose brief
is spec §0, "The design thesis — Quiet Conviction, made structural": R2 was
blocked because *"every view looked like an action board. A label saying
'context only' does not fix that; a reader absorbs weight before words."*
Four structural devices carry the thesis, not annotation:

1. **The State Ledge is the tier signal** (spec §0.1) — Overview and
   Confluence open with a five-cell graded board directly under the answer;
   the four context views have nothing in that slot. Presence/absence reads
   pre-linguistically at every width.
2. **Colour is rationed by tier** (spec §0.2) — solid `--fill-*` chips,
   state ink above `--fs-sm`, and the 3px state rail are reserved to Action
   views; a context view is achromatic apart from signed directional
   numbers at ≤12.5px.
3. **Names outrank verdicts on context views** (spec §0.3) — the heaviest
   ink on Map/Moving/Money/Explore is the object's name, never a state word.
4. **The Answer Thread** (spec §0.4) — one 3px `--r3-thread` left rail marks
   exactly two things on the whole product: the active nav item and the
   view answer. Lineage: production already draws it on `.si-view-read`
   (`sector_central.html.j2:1162` per the spec); R3 completes the idea
   rather than inventing one.

The one deliberate risk the spec names: **a primary name never ellipsizes —
it wraps; numbers compress instead** (`overflow-wrap:anywhere` on
`.r3-name`, no `text-overflow` on any primary name — spec §0). Cost: taller
rows. Return, in the spec's own words: *"'Semiconductors & Semiconductor
Equipment' is legible at 320px in both languages, which is the whole point
of 'stronger names'."*

## 2. The State Ledge — authority grammar and token-level colour rationing

This is spec §6, written (per the spec's own framing) as *"the section that
answers last cycle's #1 kill reason... rules a reviewer can check by
grepping the CSS."* The table is reproduced here because it is the
single load-bearing artifact of the whole authority system:

| Channel | Action tier (Overview, Confluence) | Context tier (Map, Moving, Money, Explore) |
|---|---|---|
| State ledge | required | **forbidden** |
| Solid `--fill-*` chip, white text | permitted | **forbidden** |
| State ink as text | any size | **only ≤12.5px, only on a signed numeric move, always with a sign character** |
| ≥10% state tint on a surface | permitted (ledge cell, 8%) | **forbidden** |
| 3px state rail | permitted (board top, selected cell) | **forbidden** |
| Filled control (`.r3-cta`) | one per view | **zero** |
| Heaviest ink on the page | the graded call (22/800 count) | the object name (15/700) |
| L1 section budget | 5 | 4 |
| L1 section gap | 32px | 44px |

Reserved-token rule, spec's own words: *"`--fill-*`, `.st-*`, `.r3-board`,
`.r3-cta` may appear only inside a `.r3-view--action` section... A grep that
finds `.st-` or `--fill-` inside a context view is a design defect, not a
preference."* The five graded-call inks are bound only inside `.r3-board`
and an Action-view row stance (spec §3): `st-buy → --ink-up`,
`st-soon → --ink-info`, `st-run → --ink-link`, `st-trim → --ink-warn`,
`st-aside → --muted`. `--ink-up`/`--ink-down` flip under
`html[data-lang="zh"]` (红涨绿跌) "by construction" (spec §3) — no second
palette; `--ink-warn` never flips.

The Map `reco` field is the system's one deliberately CONFLICT-tagged
surface (R3A binding: `CONFLICT (context surface rendering action
vocabulary)`, commission §9). Spec §6 makes it the system's floor, not an
exception: `.r3-tag` is 10px (smallest step on the ramp), no hue, no fill,
no pill, no icon, sits in the **last** table column, and the plain-word
disclaimer sits **after** the table in DOM order — "deliberately below even
the context baseline." D2's own ruling (adjudications §5) additionally
withheld the RVX_Q stance-text half of the same conflict ("Hold / add",
"Take profits") from ever rendering, calling it de-amplification under this
same do-not-amplify law, and flagged it explicitly for the fresh
Data/Authority critic (§4 below).

## 3. Per-view composition rationale

Each view's composition follows the density-budget table (spec §10) and the
page grammar (spec §5): view answer → [State Ledge, Action tier only] →
dominant object → evidence → one deeper path. What follows is what each
partial actually does with that grammar, cited to the partial and to the
gate evidence that exercised it.

**Overview** (Action tier, L1 budget 5, §8 desktop order: contextual answer
→ ledge (`.r3-board`, five lanes `overview.html:434-456`) → Bottoming Watch
strip (`#ov-watch-band`) → grader (`#grader`); order confirmed live —
`overview.html`'s `section[data-view=overview]` child order
`#regime, #actnow-section, #ov-watch-band, #grader`, cross-check row #23).
The leadership-context hero and the Act-Now board are drawn as
structurally independent systems per commission §7.3: no arrow, no shared
hue, no causal prose between them (spec §6, "Overview dual-read"); `HND`
(the hero's own data source) is never referenced by any lane-rendering
function (cross-check row #26). Mobile recomposes order rather than
shrinking it: `overview.html:204-220` reorders to answer → board → context
→ watch → grader (`order:1..5`), with the comment *"Nothing is removed, and
the ledge itself never moves off the top of the object."*

**The Map** (Context tier, no ledge, no primary CTA). Desktop: the rotation
chart (`#rvx-rmap`) is the dominant object; the accessible
`table#rvx-board` sits beneath it with a caption; quadrant legend and the
tertiary `.r3-tag` reco chips sit under their own disclaimer
(`map.html:74-104`, cross-check row #42). Phone composition is a genuine
re-order, not a shrink: QA report Gate 2 measured DOM/paint order at 390 as
answer (top 212) → quadrant summary (536) → selected object (805) →
accessible table (behind `overflow-x:auto`) → the full plot behind an
explicit disclosure (`aria-expanded`) at top 2054 — contrasted against
desktop 1440 where the SVG sits at top 322, *above* the quadrants at 871
(QA report §1.2). The plot itself is never `display:none` when collapsed
(spec §8.1 mount-width law); it is clipped via `max-height:0;
visibility:hidden` (`map.html:410-414`).

**What's Moving** (Context tier). Consumes exactly the five commission-named
artifacts — `rotation_events.json`, `sector_fragmentation.json`,
`subsector_rotation.json`, `oracle_turn_desk.json`, `oracle_tape_onset.json`
— confirmed live by the fetch recorder (cross-check row #47:
`basketdata/si_handoff.json` does **not** appear in the Moving fetch set).
Composition: compact transition rows (`#rc-events-mount`), a whole-market
map + its two text equivalents (`#rotation-app`, `drawStrip()` and
`drawTrackRecord()` per `moving.html:137,585,593`), and Desk Watch
(`#desk-watch-mount`). No action language; the STANCE vocabulary is bound
verbatim from `rotation_events.js:181-201` and hoisted to a shared header
line when every active event carries the same stance (`sharedStance`,
`moving.html:313-357`) rather than repeated per row — the "a constant never
repeats per row" doctrine law applied to a Moving-specific mechanic.

**Money & Breadth** (Dense-research tier). Desktop: one verdict card
(server regime headline + achromatic client chips), breadth object
(`#mkt-breadth`), flows fragment (`#sc-flows`, extracted server-rendered
bytes), heatmap-scorecard, and index-leadership organ
(`#scc-leadership`) — cross-check rows #48-53. Tinted verdict bars from
production are replaced by achromatic measures with printed thresholds
(adjudications §6) — the context-color law this reference exists to prove
applied to its own dense-research tier, not just to Map/Moving.

**Explore** (Dense-research tier). Desktop: search/filter chrome in a
`<details>` category filter (`summary` always names the active state,
adjudications §6) → comparison table (top-8/bottom-8 default + "Show all",
cross-check row #56) → selected-detail performance chart (inline SVG,
adjudications §6) → Time Machine / Forming Narratives / Track Record
grouped behind `.r3-disc` disclosures (spec §13, D3 "may decide"). Mobile:
the table recomposes into labelled cards (`explore.html:416-434`, `#btable
> tbody > tr{display:grid}`) rather than scrolling sideways — the page never
overflows (spec's own note at `explore.html:395-398`: "≥1101 the full
table... 768–1100/820 the table scrolls INSIDE its own box... ≤767 the table
RECOMPOSES into labelled rows").

**Confluence** (Action tier, second ledge view). Universe order preserved
(S&P → Nasdaq → Russell → Baskets, cross-check row #64); state vocabulary
(`entry_now/tailwind/neutral/late/headwind`) rendered as fixed, never
proportional, cells (Sol amendment, commission §13, spec §5.2: *"Grid
`repeat(5, minmax(0,1fr))` — equal, never proportional... Text labels and
counts are never scaled by population"*), confirmed by QA report Gate 3 —
`.r3-state` label widths track string length only, byte-identical across
320/390/768/1440, independent of population counts (1/16/21/18/9 in the
measured S&P set). Full table defaults to 8 rows with counted reveal, a
disclosed composition delta from production's larger default
(adjudications §4). Confluence's own supporting organs (Leadership
running-&-coiling, sector backdrop rollup, Nasdaq internals) return behind
`.r3-disc` disclosures per the D1 follow-up ruling (adjudications §7):
*"capability preservation outranks the L1 budget."*

## 4. Approved divergences and composition deltas

Restated verbatim-in-substance from `ORCHESTRATOR_ADJUDICATIONS.md` §3–§7,
with cites. Nothing here is softened from the source record.

### §3 — Principal Design Lead, two disclosed chrome divergences

Both CSS-only, both inside the R3A design brief §5 mobile grant, both
described by the adjudication record as "repairing the VTC-002
hidden-offscreen defect class":

- **(a)** View labels kept on the 768–1100px rail, where production
  collapses to a 56px icon-only rail with hover tooltips
  (`sector_central.html.j2:1177-1184` per spec §7). The spec's own
  justification: an icon-only rail is a hover-only affordance (master design
  system §14 forbids hover-only paths) and its tooltips are unusable at
  200% zoom.
- **(b)** The ≤767px six-tab horizontal scroller is replaced by a 3×2 grid.
  Production's `overflow-x:auto` strip (`:1189-1191`) pushes Explore and
  Confluence off the right edge at 320–390px — and Confluence is an
  **Action** view, so per the adjudication record this is "a hidden
  capability, not a layout nicety."

**"R3C must adjudicate both for production"** — the adjudication record's
own verbatim instruction (§3). Neither is a silent carry-forward.

Also recorded in §3, not divergences from production but binding lane law:
the State Ledge grammar and token-level colour rationing (§2 above); the
tertiary `.r3-tag` for the Map `reco` CONFLICT field; the names-never-
ellipsize law; skeleton-free loading (reserved geometry, no shimmer,
reconciling commission "skeleton-free" against master §9.12 "skeleton at
true geometry" — spec §9.1); `--fs-display` (46px) deliberately unused
(spec §1: "Sector Central has six answers, not one verdict"); shell
integration drops (specimen self-bootstrap toggles, placeholder banner,
fake as-of stamp) — each approved because it "avoided introducing a dual
source of truth or misrepresenting real data/freshness."

### §4 — D1 (Overview + Confluence)

- Scoped `.st-head` sixth state ink (existing `--ink-down` rung; Headwind
  needs a negative rung).
- Confluence full table default-capped at 8 with counted reveal and a
  per-selected-lane 8-cap — **production default renders more; this is a
  disclosed composition delta, journeys preserved**.
- CSS-drawn marks replacing production's Unicode `▾ ▴ ↗ →` (wording
  verbatim).
- Board legend truncated to its two live sentences — "a legend describing
  undrawn marks is false."
- `dispshort()` retained; `sc-top` id **not** minted (A7 seam (c) recorded,
  not repaired).
- `+N more` resolves to in-page `#actnow-section` (its production target).
- Capture-phase trace handler + `REF.nav` fallback (quarantine-lawful).
- Bottoming Watch constant-chip dedup to the strip foot with honest
  "All N rows:" scope.
- 44px targets bought with padding + negative margin.
- New display copy → the thin-data dot ZH twin (production's is an EN-only
  `title=`, banned by house law) and empty-lane copy for the four
  Confluence buckets production ships no list copy for (§5 below,
  copy_ledger.md).
- Cap findings bound and cited: `forming.slice(0,4)` (`subsectors.js:302`),
  `avoid.slice(0,8)` (`:307`), `PICKS_CAP=12` (`:318`).

### §5 — D2 (Map + Moving)

- **RVX_Q stance strings not rendered** (production tooltip's "Hold / add",
  "Take profits", "Watch", "Avoid" halves) — approved as de-amplification
  under A3's do-not-amplify law: action vocabulary on a context surface, not
  an enumerated ledger row; quadrant names/subtitles stay verbatim.
  **Explicitly flagged for the fresh Data/Authority critic; trivially
  revertible.**
- Ranked list defaults to production's `slice(0,10)` over the spec's
  suggested ≤8 — approved: "observed production behavior outranks a
  composition guideline."
- Desk Watch absent-vs-empty distinction — approved: uses only production's
  own recorded strings, makes the binding matrix's own failure state
  reachable, answers commission §24 "null→zero collapse." **Production's
  conflation (outage reads as calm) is filed for R3C as a recommended
  repair, not fixed here.**
- Axis domain widened only beyond production's clamp floor (no value/rank/
  quadrant change); `SECTOR_CYCLES` action-register fields (`signal`,
  `timing_state`, `action`, `stance`, `hazard`) **never** rendered.
- Rank-note clarifier approved and added ("Rank across all groups /
  排名范围：全部分组") — copy ledger entry, `map.html:104`.

### §6 — D3 (Money + Explore)

- Achromatic measures with printed thresholds, replacing production's
  tinted verdict bars — "the context color law this reference exists to
  prove."
- Style-tilt legs and leadership drivers as named lists (chip-budget law).
- Production's decorative emoji dropped (§18).
- "N% stretched" chip dropped — "the producer's own caveat states it in
  plain words — one fact, said once."
- Time Machine tier labels from manifest date ranges (no Unicode arrow).
- Category filter in a labelled `<details>` (summary always names the
  active state).
- Inert `@layer` fallback; two achromatic literals mirroring heatmap.js.
- 4×4 stroke identity replacing 14 hardcoded hexes — "the legend doubles
  as the chart's text equivalent."
- Refetch-on-activation only after failure; sync registry reads vs fetched
  heatmap ("matches production boot semantics").
- **Inline-SVG chart chosen over embedding `lightweight-charts.js`** — same
  data, production's own rebase transform cited, theme-token-native,
  200%-zoom-safe.
- New ZH copy (manifest notes, section subs, empty-state why lines) →
  copy ledger.
- `ai_watch` is `null` in the fixture: production's absence path renders;
  the A8 "Model analysis / 模型分析" branch is live code — a fixture
  carrying the field is the only way to show it visually (recorded in the
  state matrix).

### §7 — D1 follow-up (Confluence supporting organs)

Ruling that triggered it: "capability preservation outranks the L1 budget";
the three un-composed RETAIN organs (Leadership running-&-coiling, sector
backdrop rollup, Nasdaq internals) return behind `.r3-disc` disclosures in
the grammar's own EVIDENCE slot. Approved on delivery, including two
disclosed never-fires-on-this-fixture fallback upgrades (ZH label falls
back to EN instead of a raw slug; unmapped enum prints the raw producer
value instead of a bare em-dash) — "both doctrine-driven, both dead code on
this fixture, both disclosed rather than silent." Nasdaq internals
initially rendered nowhere (artifact absent from fixture+supplement); ruled
a lawful supplement extension since `marketdata/nasdaq_internals.json`
exists at the epoch commit (4,004 bytes).

## 5. QA / cross-check fix history

`QA_ATTACK_REPORT.md` (§8) recorded **1 CRITICAL, 6 MAJOR, 5 MINOR, 2 NOTE**
findings against the candidate. `capability_crosscheck.md` recorded **7
FINDING rows over 6 distinct defects (F-1 through F-6)** against the R3A
capability ledger, none approved in `ORCHESTRATOR_ADJUDICATIONS.md` at the
time that document was written.

**As of this drafting session, the on-disk `build/views/*.html` partials
carry an inline code comment citing every one of those finding IDs at its
fix site**, grep-confirmed:

| Finding | Fix-site citation (file:line, comment) |
|---|---|
| F-1 (extra `__siRoute()` double-opens the trace) | `overview.html:784` (stopPropagation half), `overview.html:1078` ("production does NOT re-run the router here... no second router pass is needed or correct") |
| F-2 (Bottoming-Watch rows lost their `<a>`) | `overview.html:929` ("production renders each watch row as a real link to its basket") |
| F-3 / QA2-07 (hydrate never fetches the premium payload) | `overview.html:710` ("QA2-07 / F-3: production's real flow FETCHES"); confirmed live — `overview.html:727` now calls `REF.fetchJSON('premiumdata/sector_central.json')` where the cross-check's era read a bare synchronous `reg()` call |
| F-4 (untranslated Map `reasoning[]` chain + Money driver legs) | `map.html:446-457` (`LAYER_ZH`, `TIER_ZH`); `money.html:904-913` (`LEG_ZH`) |
| F-5 (Moving `drawTrackRecord()` missing) | `moving.html:137`, `moving.html:593` ("whole-market track-record / calibration scorecard — production..."); confirmed live — `moving.html:585,601,624` now render `trackRecordHtml()`, the verdict ladder, and a "Track record / 跟踪记录" heading |
| F-6 (deep-link `#tm-mount`/`#grader` overshoot; sticky-offset value mismatch) | `explore.html:88-95`, `money.html:84` (identical fix cited as shared) |
| QA2-01 (Money `.r3-tag` nowrap zoom overflow) | `money.html:372` |
| QA2-02 (Forming Narratives ticker no-wrap) | `explore.html:336` |
| QA2-03 (Explore mode segment no-wrap) | `explore.html:187,203` |
| QA2-04 (answer lede overflow at zoom) | `overview.html:23` |
| QA2-05 (clipped sector name, Money, css820) | `money.html:298` |
| QA2-06 (Map universe segment <44px at 768/820) | `shell.html:602-608` (`@media (max-width:820px){ .r3-seg button{ min-height:44px; } }`) |
| QA2-08 (Confluence Universe tablist: no arrow keys, `aria-controls` non-panel) | `confluence.html:542-544` |
| QA2-09 (Timing-states tablist ejects focus) | `confluence.html:1092,1101` |
| QA2-10 (authored ARIA labels English-only in ZH) | `overview.html:525,1052`; `map.html:871`; `confluence.html:1031` |
| QA2-11 (`aria-label="moved to"` fragment) | `moving.html:304`; confirmed live — `moving.html:308` now emits `aria-hidden="true"` in place of the `role="img"`/`aria-label` pair |
| QA2-12 (no roving tabindex) | `overview.html:535,1044`; `confluence.html:546,558,1077` |
| QA2-13 (Validated allowlist, migration-only) | `map.html:454` (cross-reference note only — this item is a migration precondition, not a reference defect) |

**This drafting session did not itself re-run the QA/cross-check probe
harnesses.** The table above is grep/read evidence that a code change citing
each finding ID exists at a plausible fix site and, for the five defects
checked by direct reading (F-1, F-3, F-5, QA2-06, QA2-11), that the described
mechanism is now present in the rendered logic. It is **not** independent
re-verification, and no standalone re-probe report exists on disk under
`build/` or `research/reference_integrity/mastermind-xpv2-sector-r3b/` (grep
swept for `re-probe`, `REPAIR`, `QA_FIX`, `re-verified` — no hits). **Mark
for verify-at-freeze**: a fresh critic should re-run the QA harness (or an
equivalent probe) against the current artifact before treating any finding
above as closed.

**F-6 residual note.** The fix cited at `explore.html:88-95` /
`money.html:84` repairs only the *value-consumption* half of F-6: a
specificity bug where each view partial's own fallback `scroll-margin-top`
rule (loaded after `shell.html`'s in the assembled document) silently won
over the shim-measured `--ref-sticky-offset`, so every anchor on that view
consumed a static 40px/56px token instead of the real measurement. **The
second, independent half of F-6 — the anchor's `scrollIntoView` firing
*before* async-mounted organs above it finish rendering, so `#tm-mount` and
`#grader` still land far below the fold once those organs grow — has no
fix-site citation anywhere in `build/views/*.html` or `build/shell.html`**
(grep for `requestAnimationFrame`, `re-scroll`, `settle`, `overshoot`
returned no matches in either directory). The cross-check's own suggested
repair — "re-run the anchor scroll after the activated view's mounts
settle" — does not appear to have been implemented. **This is a residual,
unrepaired page-length/landing defect** that a fresh Product Regression or
Mobile/Accessibility critic should re-measure at `#tm-mount` and `#grader`
specifically before accepting Gate 6 as clean.

## 6. Commission §25 acceptance — dimension by dimension

Per commission §25, the Principal Design Lead's own review (spec §16)
already answers each dimension at system level; restated here in 1–2
sentences each, cited:

- **First-screen hierarchy** — one answer at 22px/500 weight, then exactly
  one dominant object per view; page title demoted to 15px chrome. Measured:
  3 L1 sections visible at 1440×900 (spec §16).
- **Panel count** — L1 budget 5 (action) / 4 (context), hard ceiling 7; the
  ledge and its selected list count as one object, not two (spec §16, §10).
- **Whitespace** — 32px (action) / 44px (context) between L1 sections;
  24/32px answer-to-first-section; 62ch answer measure (spec §16, §2).
- **Full-name readability** — 15px/700/−.008em, `overflow-wrap:anywhere`,
  no ellipsis on any primary name at any width in either language (spec
  §0, §16).
- **Chart prominence** — the chart is the dominant object on Map only;
  elsewhere it sits in a reserved-geometry mount, never full-bleed, never
  bordered inside a panel (spec §16).
- **Repeated caveats** — one as-of per panel, one page stamp, one merged
  footnote per panel; a constant never repeats per row (spec §16; the
  Moving `sharedStance` hoist in §3 above is the concrete mechanism).
- **Excessive chips** — ≤2 chip-class elements per L1 section at rest,
  ≤6 per view; the Map `reco` treatment is a 10px hairline tag, not a chip
  (spec §9.2, §16).
- **Authority-weight differentiation** — §6 above: the ledge's
  presence/absence plus a grep-checkable token-level reservation table.
- **Mobile independence** — phone recomposes rather than shrinks in all six
  views (§3 above); QA report §2 measured **zero capabilities lost on
  phone** in a set-difference of visible controls between 1440 and 390
  across all six views.
- **Dark/light quality** — two distinct art directions, not a token swap:
  dark separates by luminance, light by tinted rail + firmer hairline +
  softened accent (spec §4). A recorded trap: a light-mode edge override
  first written as `border-color:` (four-side shorthand) silently repainted
  the board's 3px state rail as a hairline in light only — corrected by
  restoring `border-top-color` by name (spec §4).
- **Institutional versus playful styling** — one type family across an
  extreme weight range, tabular numerals everywhere, achromatic by default
  with hue rationed to five meanings, zero breathing elements, zero emoji,
  CSS-drawn chevrons, no gradients, no glow (spec §16).

No view is claimed to pass "merely for being cleaner than production"
(commission §25) — every dimension above is answered against a specific,
checkable artifact property, not a comparative impression.

## 7. What this document does not claim

This document restates the design record; it does not re-adjudicate it. Any
item marked "verify at freeze" above (the QA/cross-check re-probe state, the
F-6 residual) is a genuine open question for the fresh critics, not a
resolved fact softened for presentation. Two items outside the design
record proper but load-bearing for a Visual/Taste or Data/Authority critic's
read of this document: (1) the RVX_Q de-amplification (§4, adjudications
§5) is explicitly still open for the Data/Authority critic — it is not
being presented here as settled; (2) commission §18's iconography law and
the spec's §9.3 sanctioned icon set were read but not independently
re-swept against the current artifact by this drafting session — the QA
report's §7 authority-masquerade pass (PASS, no forbidden vocabulary/hue
found) is the most recent evidence and is cited, not re-verified, here.
