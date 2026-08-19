# Prophet Operator Lab — D-LAB-R5.1 reference candidate (R5.3 fix round)

**Status: NOT APPROVED. No `approval.yml` exists and none may be written by this author.**
This artifact produces a SHA and stops. It inherits the unapproved status of the R4 Prophet
Board reference it extends (`mockups/refs/institutionalize/us_stocks/DESIGN_NOTES.md:7`), so the
RIG R5 cycle has to adjudicate **both**: R4's ratified-but-unreviewed composition and the Lab
additions in this directory. The independent critique is owed and is a different session's work
(RIG §6 — the author never judges the author).

**No production file is touched by this directory.** No template, no `site/`, no engine path, no
`data/` write, no `theme.css` token, no new header family.

**Binding authority, in precedence order**

1. `research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md` §1–§7 (PR #5924) — the frozen
   product contract. On any conflict about *what the Lab is*, it wins.
2. `docs/DESIGN_DOCTRINE.md` — content law. On any conflict about *what the words may say*, it
   wins.
3. `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` — visual/composition law (archetype, tokens,
   reserved hue, surface hierarchy, density, motion, responsive).
4. The frozen R4 reference and its `DESIGN_NOTES.md` — the composition this extends.
5. `research/migration_packets/MP-1-prophet-board.md` — the shell wave that will execute later.

---

## 0c. R5.3 — the final composition-touching round (C12 verdict `REVISE`)

The C12 cycle returned **`PASS_WITH_CONDITIONS` from both seats** and **`REVISE` from the
authority**, on the ground that three of the conditions were not forward-ridable: a thrice-stated
false premise underpinning a booked disposition, a ratified-law placement breach on the mobile
honesty surface, and a Law 4 breach the harness had been scoped around. All six blocking rulings
are closed here, with the takeable minors. Nothing is redesigned; no scope moves.

**PR52-1 · the round's own discipline, not applied to its own axis. The seam was imaginary.**
R5.2 wrote, in three places, that the mockup *"exercises the seam rather than dodging it: its own
harness bar is a real `position: sticky; top: 0` element, so with `?chrome=1` the divider pins BELOW
it"*, and booked `R52-D1(b)` as `RESOLVED_BY_CHANGE` on it. Measured at 1440 with `?chrome=1`,
scrolled 1,200px past the divider:

```
barTop −2637px   barH 149px   markTop 149px   --lab-mark-top 149px
```

The bar was **2,637px off the top of the screen** while the divider pinned 149px down, so what
`chrome=1` produced was a 149px **empty band** above the pin. `.harness` declares `sticky` inside
`<div id="harness">`, whose height is exactly the bar's own height, and a sticky box cannot leave
its containing block — a containing block the same size as the box gives it nowhere to go. This is
the **same defect class as PR51-1** (`overflow: hidden` on `.lab-stream`), one axis over: a true
declaration made inert by the layout around it. `D6c4` could not see it because it asserted the
bar's **height**, which reads the same whether or not the bar is on screen.

Four repairs, and the fourth is the one that stops it recurring:

1. **The bar gets a containing block with travel.** `#harness { display: contents }` removes the
   wrapper's box, so `.harness`'s containing block becomes `<body>` and it pins for the length of
   the document. `board.css` is untouched; `board.js` still writes into `#harness`; `?chrome=0`
   still hides the bar.
2. **The bar is capped at the design floor.** Un-capped it stands **385px at 390w** — 46% of the
   viewport — and a permanent band that size is not a seam any production header presents. Capped
   to **72px** (with internal scroll, so nothing in it becomes unreachable) it behaves like the site
   nav it stands in for. 72 is measured, not rounded to: the landed band sits at the offset and the
   first complete observation stands 322px tall 422px below it, so the fold holds a whole row for
   any offset up to **100px** — 28px of margin against a row that grows.
3. **The check asserts POSITION, not height.** `D6c4` now requires the chrome to be **at** the top
   of the viewport at the pin moment (`barTop ≈ 0`); `D6c4b` requires the divider to sit at the
   chrome's **bottom edge**; `D6c4c` requires the bound offset to equal the chrome's height. `M25`
   (hardcode `top: 0`) is caught by `D6c4b`; `M27` (take the travel away again — *the defect that
   shipped*) is caught by `D6c4`.
4. **The three false statements are corrected where they were made** — `lab.js`'s `syncMarkOffset`
   comment, this file's R5.2 §R52-D1 bullet, and `continuity.yml`'s `r52` rows, which are re-booked
   with an `r53_correction` naming what was asserted and what was measured. And **`55` photographs
   it**: a chrome=1 deep-scroll crop that refuses to emit unless the bar and the pin are both on
   screen at once.

Post-fix, same probe: `barTop 0px · barH 149px · markTop 149px` at 1440, and `barTop 0px ·
barH 72px · markTop 72px` at 390. Two different correct answers from one rule, for the first time.

**VTL52-601 · the aggregate had no subject and no unit.** R5.2's new lead total printed
`Lead on 5: 3 earlier · 1 same day · 1 later` — and 350px below it a row chip read
`Prophet was 3 days earlier`. Same word, same numeral, opposite meaning, one counting **rows** and
the other **days**, with the subject living only in the LENS body. The line now states both:
**`Lead measured on 5 rows: we were earlier on 3 · same day on 1 · Prophet earlier on 1`** /
「提前量已测 5 行：我们更早 3 · 同日 1 · Prophet 更早 1」. The sign is carried by the **subject**,
which is the rule VTL-403 already applies one tier down — never by ink. `D26` requires a subject on
every count and the unit on the line; `D26b` requires the aggregate not to speak the row chip's
phrase (`days earlier` / 领先我们) in either language; `M28` restores the R5.2 wording verbatim.

**VTL52-602 · the last per-row constant, printed 23 times.** *"Lead not measurable"* stood on all
23 seed rows below a divider that governs every one of them — the **third** form of one Law 4
defect (the chip at R5.1, the rail at R5.2, this slot at R5.3), and R5.2 shipped it with both gates
drawn around it: `D6g` counted *filled* slots, `D6i` counted *badges*, and a sentence repeated 23
times was invisible to both. The critics' convergent cure, taken as given:

- **The slot prints the artifact's own null glyph** — an em dash in a dashed outline, the same
  shape `.lab-n--unk` uses one component up for *"we hold no answer"* and never the shape a real
  measurement wears. The element, the LENS and the accessible name all stay: this is a change of
  register, not a deletion. `D6g` still forbids a blank slot and `D6g2` requires the name.
- **The statement moves to the PINNED strip**, merged into the sentence already there rather than
  stacked beside it: *"Nothing below this line was seen first-hand, so no row below can show a
  lead."* The pin (`D6c3`) guarantees it is on screen whenever a row it governs is, so the dash
  points at a stated fact rather than standing in for one. `.lab-mark-why` drops the consequence it
  was duplicating and keeps only the mechanism.
- **`D6i4` widens the gate from one selector to the whole seed region.** It reads every visible
  leaf string on every seed row and fails on any that appears on **all** of them with a weight of
  ≥12 (CJK counted 2, so one threshold serves both languages). That threshold is what makes it
  true rather than merely strict: a **label** names the value beside it and is legitimately
  constant — the `PROPHET` eyebrow scores 7, the `signal date` rail 11 — while a **claim** asserts
  a fact about the row and belongs once, on the structure that governs the region. The removed
  constant scored 19 (EN) / 14 (ZH); the dash scores 1. `M29` puts the sentence back.

**VTL52-603 + PR52-4 · the mobile honesty surface, reached independently by both seats.**
Two halves.

- **The caveat comes back to the glance tier.** At 390 the six pills read `14/6/10/28/7/30` — sum
  65 against a population of 30, with `28` two chips from `30` — and R5.2 demoted the only line
  that reconciles them. That inverts the ratified caveat exception (MPDS §7–8), which exists
  precisely so a caveat *without which the visible integers mislead* is the last thing to leave,
  not the first. It does not come back as the same 55-word footnote, because that is vertical the
  fold cannot spare: what returns is the **clause** — *"Boards overlap — these do not add up."* /
  「各板块互有重叠 —— 数字不能相加。」 — with the full sentence still on every pill's own tip. The
  **explanation** demotes; the **warning** never does. `D27` checks it VISIBLE (not merely present)
  at 390 in both languages, alongside all six integers; `M32` re-hides it.
- **The LENS gets a touch path and a visible door.** `board.js` binds `mouseover`/`focusin` only,
  and R5.2 hung three ≤560 demotions off it — so at the design floor the landings existed in the
  DOM and could be opened by no gesture the reader has. `board.js` is frozen R4 and may not be
  edited, so the path is added in `lab.js`, additively, over the **same** `.lens-pop` element and
  the same `data-tip-*` attributes: one popover, one vocabulary, no second tooltip system. Tap
  opens; tapping the carrier again, tapping elsewhere, `Escape`, scrolling, or flipping the mode
  closes it. `.lab-split` and `.lab-agg` take `.lab-auth`'s dotted underline — the artifact's own
  LENS affordance, applied where its promise is load-bearing — and `[data-lens-open]` marks the
  open carrier, because a touch reader gets no hover to tell them which chip they are reading.
  `D28` drives a real **tap** under `any-pointer: coarse` in both languages, `D28c` checks the
  dismissal, and `M30` removes the path.
- **And it is photographed.** VTL52-605 was right that not one crop in 63 files showed a popover
  open — the capture path actively parked the cursor to *close* tips before shooting. `56` and `57`
  open the mobile landing by tap, EN and ZH, and refuse to emit unless the popover is on screen.

**PR52-2 · the landing owed the same offset the pin does.** `landRegion` scrolled to `bandTop`
flat while `syncMarkOffset` two functions above was already measuring the chrome. On any route
whose header pins — after PR52-1 that includes this mockup at `chrome=1` — the reader pressed a
control and the surface scrolled it **behind the header**, which is exactly what `D24b` forbids, in
the one configuration `D24b` never entered. One measurement now serves both, so a route cannot be
right for one and wrong for the other. `D24`/`D24b` run at `chrome=1` as well as `chrome=0`, and
count the fold from the offset rather than from 0. Measured after the fix at 390×844:

| | offset | band top | first row | complete rows in fold | control visible |
|---|---|---|---|---|---|
| `chrome=0` EN | 0px | 0px | 422px (h 322) | 1 | yes (top 12px) |
| `chrome=1` EN | 72px | 72px | 494px (h 322) | 1 | yes (top 84px) |
| `chrome=0` ZH | 0px | 0px | 394px (h 296) | 1 | yes |
| `chrome=1` ZH | 72px | 72px | 466px (h 296) | 1 | yes |

`M33` lands without the offset and is caught by `D24b`.

**PR52-3 · LAB→LIVE dropped focus to `<body>`.** `paintLive()` destroys the subtree the mode
control is mounted in, so a keyboard operator who pressed *Live* had to re-tab the whole page to
reach the only control this surface has — LAB→LIVE was measurably harder to operate than
LIVE→LAB, while the notes claimed arrow-key traversal. The flip now reads whether focus was **in**
the control before the teardown and returns it to the **re-mounted** control inside `sc.onload`,
with `preventScroll` so it does not fight the scroll restore (`D24c`). Scoped to that case on
purpose: a reader focused elsewhere must not have focus yanked into the modebar. `D25` drives the
flip from the **keyboard** and asserts the landed element is the checked mode radio; `M31` removes
it. *(Worth recording because it cost a debugging cycle: the first draft read `activeElement`
two lines too late — after `.lab-plane` was removed — and the control lives inside that plane, so
the read could only ever answer "nobody had it". D25 caught it immediately.)*

**The minors.** `PR52-6` — `.lab-agg` gets `D26`/`D26b`/`D26c` and `M28`, closing a component that
shipped with no check and no mutation. `PR52-7` — the 390 landing carries the exclusion clause, so
the demoted aggregate arrives complete (`D28d`). `PR52-8` — `D21c` asserts the actual filtered
split string built from the rendered row count, not `"0" in text`, which passed on any string
containing a zero. `VTL52-606` — the pinned gutter cell takes the spine's own two-line shape,
`Aug 8` over *"and earlier"* / 「及更早」, so the pinned date keeps its reading. `VTL52-607` — the
meta strip's five statements each take a hairline **marker**, because every statement already uses
`·` **inside** itself and whitespace could not tell the two levels apart. *The first draft drew the
rule into the flex gap between items, as a separator. `D29` was written to measure that and
immediately killed it: across ten widths in the responsive ladder the gap rule landed at the
**start** of a wrapped line at six of them — 1180/1000/860/768 (`.lab-agg`), 640/561 (`.lab-split`
too) — where a separator separates nothing and reads as a stray mark, and CSS has no selector for
"first on its line". (The ≤560 pair did not orphan only because that draft carried a hand-written
`display: none` exception for the member that leads the line once `.lab-sub` hides — a per-
breakpoint exception is the same evidence, one step earlier.) Keying the rule to each statement
instead makes wrapping a non-event: every rule belongs to the text immediately right of it, so a
statement carries its own marker to the new line and needs no exceptions at all. The check stayed,
inverted: every visible statement is keyed, no control is (`M34` removes the markers).*
`VTL52-608` — the
keep/remove criterion is repaired, not the eyebrow: R5.2 wrote that a rail earns its place by
*differing between adjacent rows*, which the `PROPHET` eyebrow disproves. The real test is
**label vs claim** — a label names the value beside it and is read *with* it; a claim asserts a
fact about the row, and once a structure states that fact for a region every per-row copy is the
repetition. `PR52-10` — the divider's own spine segment now changes state where the crossing
happens: **solid to the midline, dashed from it down**, instead of running the LIVE idiom full
height across the element that announces the end of LIVE. Both halves are treatments the rows above
and below already wear; no new device.

**Declined: none.** All three judgment-call minors (`VTL52-606`, `607`, `608`) are taken.

---

## 0b. R5.2 — the fix round on the R5.1 `product_regression` BLOCK

The R5.1 artifact (frozen `f889d5eb35f3`) drew **BLOCK** on one finding plus a set of
cheap minors. This round fixes them and re-freezes; nothing is redesigned and no scope moves.

**PR51-1 · the blocker: a capability was booked on a mechanism that had never fired.**
R5.1 withdrew the 23 per-row seed chips (VTL-408) and paid for them with a sticky divider —
`.lab-mark { position: sticky; top: 0 }`. That divider sat inside `.lab-stream { overflow: hidden }`,
and any `overflow` other than `visible` makes an element a **scrollport**; a sticky child pins to
its nearest scrollport, which here was a list that can never scroll. So the pin was inert exactly
where it was supposed to work. The critic measured it: 2,000px into the seed region at 390×844,
**four seed rows on screen and zero worded class labels** — while the packet booked
`add.sticky_class_divider`, marked `lab.observation_class` IMPROVE, and minted BETTER on *"the same
guarantee, one constant instead of 23."* None of that was true of the bytes.

Three things changed, and the third is the one that matters most:

1. **The clip moved off the list.** `.lab-stream` drops `overflow: hidden`; the rounded plane is
   clipped by its end members' own radius instead. Nothing in the list paints outside its own box,
   so the clip cost nothing and the pin became real.
2. **The divider split along the tier line.** What pins is the **constant** — the date, the class
   name in the seed treatment, and *"Nothing below this line was seen first-hand."* *(R5.3 /
   VTL52-602: the pinned sentence now also carries the consequence — "…, so no row below can show
   a lead." — because that clause is what the 23 lead slots stopped printing. §0c.)* What does
   **not** pin is the *lesson* — the mechanism, why no first-sighting time exists — which is stated
   once where the stream crosses the date and scrolls away with it. Pinning R5.1's 25-word sentence would have spent ~12%
   of a 390 viewport permanently re-teaching a rule the reader learned on the way in. The doctrine's
   demotion rule cuts the same way here as it does for the sort basis at 390 (§2.10).
3. **The check became behavioural.** `D6c3` scrolls 1,200px past the divider at 1440 **and** 390 and
   reads `getBoundingClientRect().top`, so a declaration that cannot fire fails. `M22` re-adds the
   `overflow: hidden` and is caught **only** by `D6c3`; `M18` (make it `static`) is caught by `D6c`
   *and* `D6c3`. Receipts: at 390, scrolled to 4,203px, mark top **0px**, four seed rows on screen,
   label `Aug 8 From history Nothing below this line was seen first-hand.`

The orphan is closed in the same act: `.lab-cls--seed` had zero references after VTL-408 — a dead
treatment for the one distinction this surface exists to carry. The divider's class badge now wears
it, so the hatched-dashed idiom still names the class and does it **once**, from the only position
that stays on screen for as long as the class applies.

**Why this round did not simply restore the chips.** The critic's finding is that the artifact
over-claimed, not that the divider was the wrong device. Per-row repetition of a constant is a Law 4
defect on its own terms, and the encoding is unchanged: four structural channels on the row (dashed
spine, hollow node, the *"signal date"* rail, the lead slot — *"Lead not measurable"* at R5.2, an
em dash in the null idiom from **R5.3 / VTL52-602**, §0c) plus
a class name that is now genuinely present wherever it applies. The disposition therefore stays
IMPROVE — but the packet records now say *what was wrong at R5.1*, and the BETTER on
`task.tell_live_from_history` is re-earned against a measured pin rather than against a declaration.

**The minors, in one table.**

| Finding | What changed |
|---|---|
| **PR51-2** | `lab.css`'s *"above 980w all six fit on one line anyway"* was false — the strip clears 981w by 22px, and pill widths grow with counts the Lab does not control. The wrap is **unconditional** now: same behaviour, no threshold to be wrong about, and **D20d** pins 1000w — the band no check had ever looked at. |
| **PR51-3** | VTL-401 shipped six checks and one mutation. **M20** (hide the ladder) and **M21** (hide the page header) now attack `D4b` and `D4c`, which were asserted but never proven to bite. |
| **PR51-5** | `D17b` probed `"Live sighting"` and `"Seed · history"` — strings *the same revision retired*. A leak test scanning for words the EN page no longer prints cannot fail. Probes repointed to live vocabulary, and **D17c** now asserts each probe is PRESENT in EN before its absence in ZH is credited, so the rot fails loudly next time. |
| **PR51-6** | The empty state told the reader to *"try another board"* while six pills read a confident `0`. The two facts get two sentences: nothing anywhere → point at the next pass; nothing on **this** board while the feed reports → point at the counts, which already say which boards have rows. |
| **PR51-7** | The ZH lead pair was 「比 Prophet 早 N 天看到」 vs 「Prophet 早 N 天」 — same polarity character, same numeral, in a column the symmetry law deliberately makes identically quiet. The adverse case is now 「Prophet 领先我们 N 天」: shares no character with 早, names the subject, and reads as a measurement rather than a fragment. |
| **PR51-10** | The harness said *"Live only" / "Seeds only"* — the pre-VTL-405 words. It now speaks the surface's own vocabulary, so the mockup stops re-teaching retired words to every reviewer who drives it. |
| **PR51-12** | §2.4 item 3 still advertised the withdrawn seed chip as a shipped channel and §6 Q2 still asked a question R5.1 had already answered. Both rewritten to the shipped truth. |
| **PR51-13** | `32-live-only-dark-en` was **byte-identical** to `35-lead-symmetry-dark-en` — the same URL under two names, so the crop set claimed a view it did not hold. The duplicate is deleted and §5's counts are recomputed from the capture run. |

Everything R51-M1/M2/M3 closed is untouched: the grid-scoped mode (D4b–D4f), unknown-not-zero
(D18–D18f) and lead symmetry (D19–D19g) all still pass, and `M7`/`M14`/`M15`/`M16` still bite.

### 0b.1 — the visual-taste first pass, folded into the same round

The `visual_taste` critic's first pass returned **PASS_WITH_CONDITIONS** over two further majors.
They are answered here rather than deferred, because both bear on the same device this round exists
to repair.

**R52-D1 · the constant VTL-408 targeted was still printing.** Withdrawing the chip closed one of
its two homes. Every seed row kept `signal date / not a sighting` in the rail, so the *class
assertion* was still repeated 23 times and Law 4 was not closed — only relocated. The rail is now
`signal date` alone, and the line that survives is doing a different job:

> `signal date` and `first seen` are **unit labels**. They say what the number directly above them
> is, they **differ between adjacent rows**, and without them the stream prints two kinds of
> timestamp in one column with nothing saying which is which. That is the ratified
> self-labelling-token pattern (doctrine §3), and it is the closest thing a single interleaved
> stream has to a column header — a table would spend one header cell on it, and this stream
> cannot, because the two kinds alternate. `not a sighting` was the other thing: an assertion of
> class membership, identical on every row, which is exactly what the pinned divider carries once.

**D6i** pins the split in three parts, because any one alone is gameable: the class assertion
appears **exactly once** in the stream, **no** row rail makes one, and the two rails **differ**.
`M23` puts the per-row constant back and is caught by `D6i2`.

Two smaller halves of the same finding:

- **The pin is header-aware.** `top: 0` encodes *"this route has no page header"*, and the
  production route ships the shared site nav. The controller now measures the sticky chrome above
  the grid and binds `--lab-mark-top`. ~~This mockup's own harness bar is a real `position: sticky;
  top: 0` element, so it **exercises** the seam instead of dodging it: `?chrome=1` pins the divider
  at 149px and `?chrome=0` pins it at 0 — two correct answers from one rule, both asserted by
  **D6c4**.~~ **FALSE AS WRITTEN AT R5.2 — corrected at R5.3 / PR52-1.** The bar declared `sticky`
  inside a wrapper exactly its own height, so it had no travel and never pinned: measured, its top
  was **−2,637px** while the divider pinned at 149px, i.e. `?chrome=1` produced an empty 149px band
  and `D6c4` asserted the bar's *height*, which reads the same either way. The seam is real from
  R5.3 (`#harness { display: contents }`, bar capped at the design floor) and `D6c4` now asserts the
  bar's **position** at the pin moment. See §0c. `M25` hardcodes `top: 0` and is caught by `D6c4b`;
  `M27` takes the travel away again and is caught by `D6c4`.
- **The empty `.lab-lead--adverse { }` hook is deleted.** R5.1 shipped it reasoning that an explicit
  empty block would deter a future edit. It does the opposite — an empty rule under a comment
  addressed to future editors is a labelled slot, and filling it is the cheapest possible way to
  reintroduce the VTL-403 asymmetry. What actually holds the law is **D19c**, which compares
  *computed* colour and therefore fails whether the divergence arrives by this selector, a follower
  stylesheet, or an inline style — none of which the empty rule could have stopped.

**R52-D2 · one complete observation above the 390 fold.** Measured first, because the answer turned
on the numbers: the first row began at **1,009px** and stands **294px** tall, so it had to start by
**550px**. The ladder (**295px**, frozen by R51-M1) and the six wrapped selectors (**137px**, frozen
by C4) account for 432px of that budget — *compression cannot reach 550 while both stand*, even if
the Lab's entire preamble were deleted, which would also cost Law 1 its stance line. So the remedy
is two-part:

1. **Three preamble lines demote, each to a landing that already existed or was made for it** — the
   board subtitle (printed verbatim as every selector pill's own tip body: two copies of one
   sentence, 12px apart), ~~the boards-overlap footnote (a fact *about* the pill row, now riding on
   the pill tips)~~, and the new lead total (into the split chip's LENS, the demotion `.lab-basis`
   already takes here). Nothing is deleted and nothing is compressed into denser jargon.
   **REVERSED at R5.3 / VTL52-603 (§0c):** the overlap caveat is a caveat without which the six
   visible integers mislead, so the ratified exception forbids demoting it. Its *clause* is back on
   the glance tier at 390 and only its *explanation* demotes. Two lines demote here now, not three.
2. **The region is landed on flip.** The rule is self-scoping rather than breakpoint-scoped: land
   only when the first observation would otherwise fall below the fold, so at 1440 nothing ever
   moves.

**Why this is a navigation and not the viewport hijack the standing veto forbids.** It fires only on
a deliberate mode flip — never on load, never on a board or filter change, never ambiently. The
control the reader just pressed **re-mounts into the Lab modebar**, which is precisely what lands at
the top, so their eye does not lose it (**D24b**). And flipping back to LIVE **restores the scroll
position they flipped from** (**D24c**), so the excursion leaves the page where it found it. The
scroll is instant, so there is no motion to suppress. Result at 390×844: one complete observation in
view in **both** languages (**D24**), with `M24` and `M26` attacking the landing and the return.

**R52-D3 · the receipts.** `49`/`4a`/`4b`/`4c` add the missing theme × language corners for the two
states that carry the unknown-vs-zero distinction — until now theme and language had only ever moved
together, so neither could be judged alone. `54` is a 390 crop that **contains** a signed lead: the
shot named for the lead symmetry at the design floor had been photographing only chrome, because
nothing but the preamble was above the fold. It scrolls the **adverse** chip — the branch R5 could
not render at all — whole into frame and refuses to shoot if it is not there.

**VTL51-506 · "Live" now means the mode, in both languages.** VTL-405 de-overloaded it once by
making the class a *phrase*; the residue was that the phrase still contained the word, so the page
carried LIVE (mode), "Seen live" (row class) and "Seen live" (filter) — 实时 / 实时观测 / 实时观测.
The class is now **"Seen first-hand" / 「第一手观测」**. This is not a rename for its own sake: the
axis the class measures is **provenance**, not timing — did we watch it arrive, or are we reading it
back out of the record — and it makes the pair internally consistent, because the opposite of
*"From history"* is *"seen first-hand"* and never was *"live"*. The divider and the baseline copy
drop "live" with it (*"Continuous watching began Aug 8"*).

**VTL51-505 · the lead, totalled once.** Taken. The lead is the one thing this surface measures
about *itself*, and reading it meant counting chips down 4,681px of stream. One line beside the
count — ~~`Lead on 5: 3 earlier · 1 same day · 1 later` / 「已测 5 条：更早 3 · 同日 1 · 更晚 1」~~
— computed from the **filtered** set like the split, printing all three outcomes even at zero so it
cannot become one-sided by omission the way the R5 lead chip did. It demotes into the split's LENS
at 390. ~~**Note the deliberate inconsistency with PR51-7**: a two-glyph ZH opposition (更早/更晚) is
fine *here* and was not fine on the row chips, because here the outcomes sit adjacent in one
parallel construction and there they are separated by hundreds of pixels and never seen together.~~
**RE-WORDED at R5.3 / VTL52-601 (§0c).** That wording had no subject and no unit, so its "3 earlier"
collided with a row chip's "Prophet was 3 days earlier" — same word, same numeral, one counting rows
and the other days. The line now reads `Lead measured on 5 rows: we were earlier on 3 · same day on
1 · Prophet earlier on 1` / 「提前量已测 5 行：我们更早 3 · 同日 1 · Prophet 更早 1」, and the sign
is carried by the **subject** in both languages rather than by a 更早/更晚 opposition — which also
retires the PR51-7 exception above, since the two glyphs no longer do the work.

---

## 0a. R5.1 — closing the RIG R5 `REVISE` verdict

R5 (frozen `6ee8f34480ce`) returned **REVISE** over three majors and fifteen conditions. Both
critics independently praised the core devices — the five-channel seed/live encoding, the dated
divider, the designed stale state, the achromatic `--prov` discipline, the anti-vacuity harness —
and **none of them is touched here.** This is a closure pass, not a redesign.

**The three majors.**

**R51-M1 · VTL-401 — the mode is a REGION, not the page.** R5 read LAB-0 §6.5 as a page mode and
hid the page subtitle, the ladder, Candidates, Groups, Evidence & Record and the footer — two of
them core baseline capabilities. The verdict ruled that a contract breach: *"the principal Prophet
grid"* is a narrowing clause naming one region of a page that demonstrably has others.
R5.1 paints `#setups` **and nothing else**. Every other section survives the mode, including the
plan book's own as-of and its behind-the-tape banner — they date the plan book, and the plan book
is still on the page. The authority-hygiene worry that motivated the over-reach was real, and the
ruling names its own remedy: **separation, not deletion.** So the Lab renders inside a bounded,
labelled region with an accent boundary, its own eyebrow and feed stamp, and an explicit
end-of-region rule — *"End of Lab observations — everything below is Prophet's own book."* The
ladder stays rendered **and operable**: one line says a cell click returns to Live, so nothing is
inert and nothing is deleted. `verify.py` **D4b–D4f** now fail if anything outside the grid
disappears; **M7** mutates the deletion back in and is caught.

**R51-M2 · VTL-402 — unknown is not zero.** R5 collapsed "the feed is not answering" and "the feed
answered with nothing" into one `return []`, so six pills asserted a literal `0` sourced from a
feed that had said nothing — a null printed **as a zero**, one flip away from copy that explicitly
teaches the reader these zeros are trustworthy. The two states are now separate facts everywhere
they surface. Unavailable prints an **em dash in a dashed box** (R4's own key-absence idiom) plus
the line that turns the glyph into a statement: *"— means we do not know… A zero here would be a
number we never received."* Empty keeps its confident tabular `0` and its real-zero copy.
**D18–D18f** pin all of it, including that the two states are not pixel-identical at the pill row;
**M14** re-conflates them and is caught.

**R51-M3 · VTL-403 — the lead is symmetric and signed.** Two defects pointed the same way.
`Math.abs(r.lead)` ran *before* the sign was ever inspected, so a signed −2 would have printed
"Seen 2 days before Prophet" in accent ink — the only thing preventing it was the generator's
habit of writing `null` for adverse cases, a convention standing in for a guard. And a measured
**adverse** result wore the same muted dashed idiom as a genuinely **unmeasurable** one.
Now: the sign is the branch, `Math.abs` is gone, and the fixture emits signed leads so the adverse
and same-day branches are real and photographed (`−3`, `0`, `+1`, `+2`, `+3` all render).
**A measurement is a measurement**: favourable, adverse and same-day share one ink and one
treatment, distinguished by the word and the number, never by loudness — the favourable chip lost
its accent fill and no longer out-inks the ticker. Only genuine absences keep the dashed null
idiom. **D19–D19g** pin the symmetry (including a computed-style equality between the favourable
and adverse inks); **M15** and **M16** attack each half and are both caught.

**The conditions.**

| Condition | What changed |
|---|---|
| **C1** re-derivation proof | **M17** now caches `#board.innerHTML` on LAB entry and re-inserts it on LIVE *while leaving the repaint counter intact* — and **D15d passes while D22 fails**. That is the proof: the counter was never evidence. **D22** plants a sentinel attribute on a real card before LAB and requires it gone after the return. |
| **C3** copy-law coverage | The slug-leak and banned-vocabulary scans ran on one board, in EN, never on LIVE. The sweep now covers **6 boards × 2 languages in LAB + both languages in LIVE = 14 views**. It immediately found a defect in the check itself: `"validated" in text` fires on the **ruled** lifecycle word *Invalidated*, so the scan is now a negative-lookbehind regex. A check that fires on compliant copy trains people to ignore it. |
| **C4 / VTL-411** 390 selectors | The scroller is **removed** rather than decorated — the pills wrap, so all six frozen boards are on screen with no gesture to discover. **D20–D20c** pin it; **M19** puts the scroller back and is caught. *(R5.1 scoped this to below 980w; R5.2 / PR51-2 made it unconditional and added **D20d** at 1000w — see §0b.)* |
| **R51-C13 / VTL-409** error state | Adds **Try again** beside Back to Live, and prints the **last known-good** pass stamp (R5 returned early before the as-of, so the one state where staleness matters most was the only one without it). **D23–D23c**. |
| **R51-C14 / VTL-407** counts | A **"Showing N of M"** line, and the live/history split now computes from the **filtered** set. Pagination deliberately not adopted — see §2.11. **D21–D21c**. |
| **R51-C15 / VTL-405** vocabulary | "Live" now means the **mode** only. The observation class and its filter share one phrase, and the EN `seeds` enum-shorthand is gone; EN and ZH are now equally plain, which is what the finding was really about. *(R5.2 / VTL51-506: R5.1's phrase was "Seen live" / 「实时观测」, which still contained the mode word in both languages. It is now **"Seen first-hand" / 「第一手观测」** — §0b.1.)* |
| **C10** token policy | The single `#fff` literal is deleted — it was also redundant (light `--panel` is already white). The file's stated policy is now true. |
| **C11** bilingual aria | The three group labels bind to the language like every other string. |
| **C5** re-census citations | Both corrected in `D_LAB_R5_BLOCKER_RECENSUS.md`, each with the receipt: `--up` is at `theme.css:72`/`:148` while `--pv-buy` is at `:80`/`:152` (the comparison needs both), and `444f80d62774` touches no file under `engine/prophet_bridge.py` — `plan_clock_date()` came from `242aafda0dc7` (#4684). The §0 headline now matches §2.12. |

**Minors taken (author's judgment, per the verdict's invitation).**

- **VTL-408** — the 23 repeated per-row seed chips are gone, and the reason they existed is
  answered rather than dismissed: **the divider is now sticky.** It pins while any row below it is
  on screen, so the sentence that licenses the whole seed treatment is present wherever it applies
  — printed once instead of 23 times. Four structural channels remain on the row itself (dashed
  spine, hollow node, the "signal date / not a sighting" rail, the lead slot). This reverses the
  R5 §2.4 argument, and the reversal is the right call: the critic was correct that the divider
  already established the fact, and making it sticky is what makes that true *mid-scroll*.
- **VTL-412** — the stance and authority lines were two sentences asserting the same absence.
  Merged into one; three lines above the first observation became two.
- **VTL-406** — the pill row now says once that boards overlap and do not sum.
- **VTL-413** — the 390 rail gutter widens to 76px so *"not a sighting"* stops breaking mid-phrase;
  the chip-row wrap it also named is resolved by VTL-408.
- **VTL-410** (partial) — the controls R5 itself introduced clear the 40px touch floor at 390.
  The R4-inherited sub-40 targets elsewhere are a platform gap and are named, not silently forked.

**Not taken:** VTL-404 (the control relocates and resizes between states). It was downgraded by
its own critic on the reasoning R5 gave in-source, nothing is lost, and the alternative costs the
production board vertical space it should not pay — see §1.2.

**Not this cycle's to close:** C2, C6, C7 bind P-LAB-API / P-LAB-UI; C8 blocks P-MP1-SHELL until
R4's composition gets its own critic pass; C9 records the amendment guard rails; **C12 is the R5.1
cycle's own obligation** — two quarantined first passes frozen before any reveal, then genuine
amendment passes. This author cannot discharge it.

---

## 0. How to run it

```bash
cd mockups/refs && python3 -m http.server 8794
open http://localhost:8794/prophet_lab/index.html
```

| Parameter | Values | Notes |
|---|---|---|
| `theme` | `dark` (default) · `light` | R4's own |
| `lang` | `en` (default) · `zh` | R4's own |
| `state`, `life`, `view` | *(all of R4's)* | the LIVE board is unchanged, so its harness still works |
| `mode` | `live` (default) · `lab` | **harness lens only** — see §1.4 |
| `op` | `1` (default) · `0` | operator entitlement; `0` proves the page is the R4 board |
| `board` | the six ids of LAB-0 §3 | |
| `cls` | `all` (default) · `live` · `seed` | observation class filter |
| `feed` | `ok` (default) · `stale` · `down` · `empty` | the Lab source's own health |
| `chrome` | `1` (default) · `0` | harness bar. Crops are `chrome=0` except `55`, which exists to photograph the `chrome=1` seam. At `chrome=1` the bar is a genuinely pinning sticky element (R5.3 / PR52-1) capped to 72px at ≤560, so it stands in for a production site nav and `--lab-mark-top` binds to its real height |

```bash
python3 prophet_lab/tools/gen_lab_fixture.py                                   # rebuild the fixture
python3 prophet_lab/tools/capture.py  http://localhost:8794/prophet_lab crops   # 49 views / 66 files
python3 prophet_lab/tools/verify.py   http://localhost:8794/prophet_lab         # 162/162
python3 prophet_lab/tools/mutation_test.py http://localhost:8794/prophet_lab    # 34/34 caught
```

---

## 1. What R5 is, structurally

### 1.1 R5 is R4 plus a layer — and that is enforced by the file list, not asserted

`index.html` loads `../institutionalize/us_stocks/board.css`, `board-data.js` and `board.js`
**unmodified**. Every byte in this directory is additive. The diff between R4 and R5 is therefore
*exactly the Lab*, which is what makes "no broad redesign" a reviewable claim rather than a
promise. A reviewer who wants to know what changed reads `lab.css` + `lab.js` + `lab-data.js`
and nothing else.

The one consequence to be honest about: `lab.js` mutates the rendered DOM after `board.js`
paints it, because `board.js` is a self-executing IIFE with no exposed mount API. In production
the same behaviour is a single `ProphetBoardController` that owns the grid from the start
(LAB-0 §6.5). The mock's post-render takeover is a fidelity gap in *mechanism*, not in
*behaviour* — §7 lists it as a known limit.

### 1.2 The mode control costs the production board nothing

The affordance mounts **inside the page's existing status cluster** (`.bh-stamp`, beside the
freshness token and the as-of), not as a new row. The ladder, the cards above the fold, and the
390w composition are all exactly where R4 puts them, at both widths. This is a deliberate rule,
not a placement preference: the Lab may not buy its own affordance out of the product's layout
budget. `verify.py` **D2** pins the control into that cluster and mutation **M9** proves the
check bites — moving it to its own row is caught.

In LAB the status cluster belongs to a different producer and is replaced, so the control
re-mounts into the Lab band with the mode eyebrow. The inline copy is **removed**, not hidden:
two radiogroups with the same label, one invisible, is an assistive-technology defect and is
also exactly the kind of node an automated check clicks by accident and reports as a pass.

### 1.3 Quiet at rest, loud when engaged

On the LIVE board the control is a small `OPERATOR VIEW · LIVE | LAB` toggle in the corner. It
does not announce a mode the reader is not in. Engaged, three signals fire at once and none of
them is subtle: a 2px accent rule across the head of the plane, a `LAB · READ-ONLY` eyebrow, and
the LAB segment filled. That asymmetry is the position: a production board must not shout about
a research instrument, and a research instrument must never be mistaken for the production board.

### 1.4 A fresh page always defaults LIVE

`desiredMode` is in memory. The control never writes the URL or storage, so a reload is LIVE
(LAB-0 §6.5, §7). `?mode=lab` exists only so a hand inspector can land in LAB; **the committed
LAB crops are produced by CLICKING the control**, and `capture.py` raises if the control is
missing or if the resulting state is not the one claimed. That is R4's own standard, adopted
verbatim — its `Show all` crops click first for the same reason: a capability that only exists
after a click cannot be evidenced by a URL.

### 1.5 LAB → LIVE re-derives; it never restores a snapshot

`paintLive()` destroys the board subtree and **re-executes `board.js`**, so the LIVE page after a
Lab excursion is produced by the same code path as a cold load. There is no cached DOM that
could have gone stale while the operator was in LAB — the law LAB-0 §6.5 states as "LAB→LIVE
selects the best lawful LIVE board **now**, never a pre-LAB snapshot".

The mock makes this *observable* rather than merely true: the harness bar prints a repaint
counter, and a cold load deliberately does **not** repaint (`apply(true)`), so the counter only
ever counts real re-derivations. `verify.py` **D15d** asserts the counter reads 1 after one round
trip; mutation **M8** (reuse the old script URL instead of re-deriving) is caught by it.

---

## 2. The design decisions

### 2.1 The Lab is a different *material*, not a different colour

The largest risk on this surface is not ugliness — it is a Lab row reading as a Prophet call.
Three separations do the work, and none of them spends a new hue:

| Axis | Prophet (LIVE) | Lab |
|---|---|---|
| Form | a grid of tiles | a stream of wide rows on a time spine |
| Vocabulary | stance verbs (Buy / Near / Wait / Hold / Avoid) | observations (what fired, when, first seen) |
| Chroma | the stance chip and the chart | **none** — see below |

The form split is the R4 Candidates precedent applied one level up: *different noun, different
form, non-adjacent*. A Lab row cannot be confused with a Prophet card at any zoom, because it is
not shaped like one.

### 2.2 The hue decision — the Lab is achromatic, and its one token is `--prov`

The reserved-hue law (design system §1) permits colour only where it means direction, health,
wayfinding, epistemic tier, or lock. A Lab observation states no direction, no health and no
verdict, so:

- **No stance ink anywhere on a Lab row.** Stance ink is Prophet's vocabulary; borrowing it would
  make an observation read as a call. `verify.py` **D13** asserts no `.pv-chip` exists in the Lab.
- **No violet.** Violet is lock-only (packet §0).
- **The spark is achromatic.** On the Prophet card the spark takes the stance hue by the shipped
  recolour law; a Lab row has no stance, so it paints in a neutral text-derived ink. **D13b**
  asserts the spark stroke is not `--up`.
- **Direction ink survives in exactly one place** — the signed live change — which is the same
  single place R4 confines it to, and it still flips under zh.

The Lab plane itself takes `--prov`, the system's own token for *provisional / epistemic tier*.
That is not a decorative choice: it is the one meaning in the reserved list that describes what
the Lab is. Everything separating a live sighting from a retrospective seed is therefore
**structural** — geometry, dash, fill, contrast — and survives all four theme × language
quadrants without a second palette.

`--lab-*` tokens are page-local derivations bound at one scope root, the compliant `--pv-*` /
`--ms-*` pattern (design system §2). No new `:root` family, no hex literal, no `theme.css` edit.

### 2.3 The signature: the observation spine

The Lab's whole job is *what fired, on what, **when**, and is that a real sighting*. So time is
the structure, not a field. One newest-first stream hangs off a continuous vertical spine, and
the class distinction is carried by the spine itself:

```
   live sighting        solid spine · filled node · a CLOCK TIME
   retrospective seed   dashed spine · hollow node · a DATE, and a label saying
                        the sighting time does not exist
```

The device does two jobs with one form, and both are true. It is the reason the row padding
lives on the content cells and not on the row: a row's own vertical padding opens a gap in the
line at every boundary, and a "continuous spine" that is actually a broken ladder of dashes
communicates nothing. (That was the first build's bug; it is why `.lab-when` carries the padding.)

**The baseline marker.** LAB-0 §4 makes the live/seed split a function of one date — the moment
continuous live watching began. So that date is drawn *on the spine*, where the stream crosses
it: `Aug 8 · Continuous live watching began here. Everything below is history we already had.`
A reader never has to infer from a badge why one row can be evidence and the next one cannot;
the rule is visible as a reading of the data rather than as a caption.

### 2.4 Retrospective seed vs live-forward — the honesty is structural

This is the requirement the whole reference exists to satisfy, so it is carried five times over,
in ways that fail independently:

1. **The time slot cannot be filled by a seed.** `signal_known_ts` was never supplied and LAB-0
   §4 forbids reconstructing it, so the slot prints the signal's own date under the rail label
   `signal date` — against `first seen` on a row we watched arrive. The absence is *printed*, not
   padded. **D6b** asserts no seed ever prints a clock time; **D6i3** asserts the two rails differ,
   which is what makes them unit labels rather than decoration. *(R5.2 / R52-D1: the rail's second
   line, `not a sighting`, is gone — that one was an assertion of class membership repeated 23
   times, and the pinned divider carries it once. See §0b.1.)*
2. **The spine goes dashed** and the node goes hollow. **D6e / D6f**.
3. **A pinned class label in the hatched, dashed seed treatment** — `From history` / 「回溯记录」,
   with *"Nothing below this line was seen first-hand."* beside it. It is one object, on the divider, and
   it stays at the top of the viewport for exactly as long as the rows it governs are on screen, so
   the class is present wherever it applies without being printed 23 times. **D6c** requires the
   badge to be visible and non-empty; **D6c3** proves the pin by scrolling 1,200px past it and
   reading its rect at 1440 and 390; **D6c2** asserts no seed ever wears the live treatment.
   *(R5.1 shipped this as a per-row chip and then as an inert `position: sticky`; §0b is the
   history and the repair.)*
4. **The lead is impossible, and the surface says so once**: the row slot prints an em dash in the
   null idiom (`—`, dashed outline, the `.lab-n--unk` shape), keeping its accessible name and a
   LENS receipt explaining that the feed never supplied a first-observation time and we do not
   invent one; the *statement* rides the pinned strip, which is on screen for as long as it applies.
   **D6** asserts no seed ever carries a measured lead, **D6g/D6g2** that the slot is never blank
   and never nameless, **D6i4** that no clause repeats on every seed row.
   *(R5.1–R5.2 printed the sentence on all 23 rows; R5.3 / VTL52-602, §0c.)*
5. **The ink drops** — seed rows render in muted ink with a quieter spark.

**Why one stream and not two groups.** Grouping seeds below a rule would be easier to draw and
weaker as a design: LAB-0 §3 freezes the default sort as newest-first, and a class partition
changes what the top of the board is. Keeping one stream forces the distinction to survive
*adjacency*, which is the case that actually matters — and the `All / Live only / Seeds only`
filter (default All) still gives the operator the partitioned view on demand. The seeds-only
crop (`30`, `31`, `34`) exists so the seed treatment can be judged on its own rather than only
next to a live row that flatters it.

**~~A deliberate deviation from Law 4~~ — WITHDRAWN at R5.1 under VTL-408.** R5 kept the same
class chip on all 23 seed rows and argued the constant-in-the-footer rule did not apply, because
"the row must be self-describing when seen alone, mid-scroll". The critic's counter was right on
both halves: the divider had *already* established the fact for everything below it, and the
encoding is strong enough that the chip was the most droppable of the five channels.

What survives from the R5 argument is the *mid-scroll* worry, and it is answered instead of
overruled: **the divider pins**, so it is on screen for exactly as long as the rows it
governs. The fact is stated once, and it is stated wherever it applies — which is strictly better
than 23 repeats, because a chip 2,000px below the divider was never actually explaining the rule,
only asserting membership. Four structural channels remain on the row itself.

**R5.2 correction.** That paragraph was true of the design and false of the artifact for one
revision: `.lab-stream { overflow: hidden }` made the pin inert, so the chips were withdrawn against
a mechanism that never fired, and the packet booked BETTER on it. §0b is the repair. Read the claim
above as binding **only** because `D6c3` now measures it after a scroll — that is the difference
between this paragraph and the one R5.1 shipped.

### 2.5 The lead slot is symmetric, signed, and always says something

*(Rewritten at R5.1 under VTL-403 — see §0a.)*

| Case | Row reads (EN · ZH) | Treatment |
|---|---|---|
| Lab saw it first | `Seen 3 days before Prophet` · 「比 Prophet 早 **3** 天看到」 | **measurement** |
| Same day | `Same day as Prophet` · 「与 Prophet 同一天」 | **measurement** |
| Prophet's plan opened first | `Prophet was 3 days earlier` · 「Prophet 领先我们 **3** 天」 | **measurement** |
| Prophet has no plan on the name | `Nothing to compare yet` | absence |
| Retrospective seed | `—` in the null idiom, named `Lead not measurable`; the sentence pins on the strip (R5.3) | absence |

**The law: a measurement is a measurement.** The three measured outcomes share one ink and one
treatment — quiet, unfilled, lighter than the ticker — and are told apart by the word and the
number, never by loudness. R5 painted the favourable case in accent ink on a tinted fill and
routed the adverse case into the *absence* idiom, so the board's aggregate glance was a column of
credit badges and the one number the Lab prints about itself was one-sided: you learned exactly
how early it was and never how late.

Only genuine absences keep the dashed null idiom, and the slot is **never blank** — an empty slot
reads as "zero lead", a claim nobody made.

**One ink is a design law, and it has a bilingual cost that R5.1 did not pay** *(R5.2 / PR51-7).*
Making the three measured outcomes identically quiet means the **word** is the entire signal — so
the word has to be legible at a glance in both languages, not just in English. EN gets it free:
`Seen … before Prophet` and `Prophet was … earlier` flip the subject *and* the verb. The R5.1 ZH
pair did not: 「比 Prophet 早 **N** 天看到」 against 「Prophet 早 **N** 天」 shared the polarity
character 早 and the numeral, and differed only by word order and one 比 — in a column of
deliberately identical chips, that is a sign the eye can miss. The adverse case is now
「Prophet 领先我们 **N** 天」, which shares no character with 早, names Prophet as the subject and
我们 as the reference, and reads as a measurement rather than a fragment.

The sign is now the branch. `Math.abs` is gone (**D19f** greps the source with comments stripped,
so the explanation is not punished), and the fixture emits **signed** leads rather than writing
`null` for every adverse case — a generator convention had been standing in for a guard, and it
also left two of the five branches unphotographed. **D19c** pins the favourable and adverse inks
to computed-style equality; **M15** (route adverse back through the favourable branch) and **M16**
(re-amplify the favourable chip) are both caught.

### 2.6 The card composition — chart, then readings, then Prophet

Left to right at desktop, top to bottom at 390: exactly the order LAB-0 asks for. The row reuses
R4's skeleton with different tenants — chart hero, identity block, footer band — which is what
makes it belong to the family without being mistakable for a member of it.

- **Chart first**, at 72px, with R4's own printed-null law inherited verbatim: a ticker the
  payload carries no spark for renders `No chart yet` at the *same height*, never a collapsed
  strip (R4's VTC-301 closure, adopted rather than re-litigated).
- **The live quote is unconditional and keyed on `data-sym`**, exactly as the R4 card is — in
  production `live.js` paints it for 100% of rows regardless of the enrichment join. Un-hydrated
  it reads em dashes for price *and* change together, never one without the other.
- **One chip per expert.** Identities are never merged into "3 signals"
  (`DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED`). **D8** asserts the chip count equals `experts[]`
  per row; **M6** (collapse to the first) is caught.
- **The Prophet comparison is quoted, not restated.** It sits on its own recessed plane behind a
  rule with its own `PROPHET` eyebrow, and it speaks R4's ruled lifecycle lexicon *verbatim*
  (Watch / Ready / Entered / Delivering / Overtime / Invalidated / Resolved · 观察/就绪/入场/达标/
  超时/失效/已结). Weight-only, never hued — a second vocabulary for one referent would be the
  defect the one-referent-per-page law exists to stop.
- **Event markers inside the spark are explicitly out of scope for V1** and are not drawn.

### 2.7 Plain words at the glance tier; exact identity on the receipt

No raw detector or expert slug appears above the fold (doctrine §2 Law 2). The projection:

| Board (LAB-0 §3) | Glance EN / ZH | Receipt (LENS) |
|---|---|---|
| `lab-g0-v1` | Earliest mark / 最早标记 | `G0_GREY_DOT@1` |
| `lab-c1-v1` | Flush in progress / 急跌进行中 | `C1_1D_LIVE_WASHOUT@1`, current non-terminal episode |
| `lab-c2a-v1` | Turning up / 开始转强 | `C2_1D_TURN@1 / c2a_kd_cross` |
| `lab-c2-variants-v1` | Turning up — all readings / 开始转强 · 全部读数 | the six experts, identities never merged |
| `lab-g0-c2a-v1` | Marked and turning / 已标记且转强 | display set intersection; `detector_id = null`; mints nothing |
| `lab-all-early-v1` | All early signs / 全部早期迹象 | union G0 + C1 + C2a–f; C3/C5 excluded in V1 |

Readings read as ordinary English and ordinary Chinese — `crossed up`, `slope turned up`,
`low held higher`, `momentum bottomed`, `momentum curling up`, `bounce big enough` — with the
exact expert id on each chip's own receipt line.

**Both halves are checked, and that matters.** **D7** asserts no machine identity leaks to the
glance tier; **D7b** asserts the identities survive on receipts; **D7c** asserts each reading
carries *its own* identity, because the board selectors also carry detector ids and a page-wide
substring test passes even after every per-row receipt is deleted. Mutation **M5** was written
against **D7b**, survived it, and is the reason **D7c** exists.

### 2.8 Stance, and zero authority, at the glance tier

Law 1 is answered once, in plain words, in the band: **"Watch — don't chase. Nothing here is a
Prophet call."** Beneath it, the authority disclosure — *"Observation only — nothing here ranks,
sizes, or changes a plan."* — with the all-false authority block on its receipt. **D11** asserts
the payload block is all-false and **D11b** that the sentence is on the surface.

No falsifier or refutation language appears anywhere (operator ruling #3821); **D12** bans
`falsif` / `refut` / `证伪` / `validated` / `blocked_data` / `prereg` / `gauntlet` / `k-of-n` from
the rendered text.

### 2.9 The three degraded states stay visibly LAB

There is no code path from a degraded Lab feed to LIVE content under a LAB label — the single
failure LAB-0 §6.5 names by name.

- **Empty** — a real zero, said as one, and the pills print a real `0` to match. *(R5.2 / PR51-6:
  it is now TWO states, not one sentence for both.* Nothing anywhere — *"Nothing early on any board
  right now. The feed is reporting and it is reporting nothing — every board reads 0. That is a real
  zero, not a gap. Check back after the next pass."* Nothing on **this** board while the feed
  reports — *"…the counts above show which boards do have rows."* R5.1 said *"try another board"* in
  both cases, which under a globally empty feed is advice the reader can already see is useless: six
  pills reading a confident `0` and a sentence sending them to check six things it had just told
  them were zero. An empty screen is an invitation to act, and an invitation to a dead end is worse
  than none.*)
- **Behind** — the Lab's own disclosure, deliberately **not** production's behind-the-tape
  banner: that one describes the plan book's *price* vintage, and reusing its words for a
  different producer would tell the reader the wrong thing is late. The spine grows a dashed
  head segment labelled `nothing since 11:36 ET` — an absence of observations drawn on the
  instrument that measures it.
- **Unavailable** — *"The Lab feed is not answering… Prophet's live board is unaffected — switch
  back to Live to use it."* Names what failed **and** what still works, and at R5.1 (VTL-409) it
  also offers **Try again** and keeps printing the **last known-good** pass stamp. Its pills print
  em dashes, never zeros (§0a, R51-M2) — the one state where a confident integer would be a number
  we never received.

**D14 / D14b / D14c** assert each state keeps `data-mode=lab`, keeps the eyebrow, shows zero
Prophet cards, and does not scroll horizontally at 390. Mutation **M11** (leave the live grid
painted when the feed is down) is caught by both.

### 2.10 Responsive, motion, accessibility

- **390w is the design floor** and the spine survives to it, because it is the signature *and*
  the honesty carrier. Chart → identity → Prophet stack inside one gutter, in the same reading
  order as desktop left-to-right. **D16** asserts zero horizontal page scroll across five Lab
  views at 390.
- **The selector strip never scrolls, at any width** *(R5.1 / VTL-411; unconditional at R5.2 /
  PR51-2 — R5.1 scoped the wrap to `max-width: 980px` and asserted "above 980w all six fit on one
  line anyway". Measured, they clear 981w by **22px**, and pill widths grow with the counts, which
  this surface does not control: a three-digit count on any board reopens VTL-411 in a band no check
  ever looked at. A width the layout merely happens to survive is not a guarantee. Wrapping
  everywhere is the same behaviour with no threshold to be wrong about — at 1440 nothing wraps and
  nothing changed — and **D20d** now pins 1000w.)* R5 put six frozen
  product-contract boards in an `overflow-x:auto` strip with no edge fade and no chevron, so three
  of them were off-screen with nothing to say they existed — while the empty state's own copy told
  the reader to "try another board". The page-level overflow checks were structurally blind to it,
  because an inner scroller keeps `documentElement.scrollWidth` clean. The fix removes the
  mechanism rather than affording it: the pills wrap. It costs one row of vertical space and buys
  back a product contract. **D20** requires all six on screen at 390; **D20b** forbids a hidden
  scroller; **M19** puts it back and is caught.
- **The mobile reduction is a re-composition, not a squeeze** (§15). Three lines demote at ≤560w,
  each to a landing, and never by being cut: the **sort basis** to the count chip's LENS; the
  **board subtitle** to the selector pills' own tips, where it was already printed verbatim — two
  copies of one sentence 12px apart, so hiding one removes a duplicate rather than a fact; and
  the **lead total** to the split chip's LENS. *(The test for a legitimate demotion is that the
  reader can still reach the fact by the obvious gesture on the element the fact is about — not
  merely that the fact exists somewhere in the DOM. R5.3 made that test true rather than assumed:
  before PR52-4 there was no gesture at all under a coarse pointer.)* The **boards-overlap caveat**
  was a fourth at R5.2 and is **not** one any more — R5.3 / VTL52-603 returns its clause to the
  glance tier, because a caveat without which the visible integers mislead is the one thing the
  ratified exception forbids demoting.
- **~~A cost R5.1 created at 390, stated rather than hidden.~~ PAID at R5.2 (R52-D2).** R51-M1
  restores the ladder above the Lab region and C4 wraps the six selectors into three rows, and R5.1
  disclosed the consequence — at 390×844 **no observation row was above the fold** — as the
  unavoidable bill for two capabilities the verdict ruled non-negotiable. Disclosure was the right
  thing to do and the wrong place to stop: an operator-only surface still owes its reader one
  complete answer on arrival, and *"they scroll"* is what every surface says about its own fold.
  The measurement decided the remedy. The first row began at **1,009px** and stands **294px** tall,
  so it needed to start by **550px**; the ladder (295px) and the selectors (137px) account for
  432px, which means **no amount of compression reaches 550 while both stand** — even deleting the
  Lab's entire preamble leaves the row 181px past the fold, and deleting it would cost Law 1 its
  stance. So the demotable preamble lines go to landings and the region is **landed on flip**,
  which is the only lever left once the frozen structures are respected. Neither R51-M1 nor C4 is
  reopened: the ladder is where it was and all six boards are still on screen. **D24** now requires
  one complete observation above the fold in both languages **at `chrome=0` and `chrome=1`** (R5.3
  / PR52-2), and crops `14`–`17`, `27`, `34`, `42`, `45`, `48` show it. §0b.1 carries the argument
  that the landing is a navigation and not the viewport hijack the standing veto forbids.
  *(R5.3 / VTL52-603: it was three lines at R5.2 and is two now — the overlap caveat's clause is
  not demotable, because the six integers it reconciles stay on screen. §0c.)*
- **Motion is a status channel.** Exactly one thing animates: the feed dot, and only while the
  feed is reporting; `behind` and `unavailable` rest (the shipped `.dtp-dot` law). The mode flip
  is one 140ms fade on the board region. `prefers-reduced-motion` kills both **by name**,
  pseudo-elements included.
- **Toggles never move on hover.** Rows take the table row-hover tint; only clickable containers
  lift, and a row is not a container. Focus rings derive from `--link`. The mode control is a
  real `role="radiogroup"` with arrow-key traversal.

### 2.11 Count discipline, and one place R4 is deliberately not followed

*(Added at R5.1 under VTL-407 / R51-C14.)*

R5 printed a live/seed split computed from the **whole** board while rendering a filtered subset,
so "Live only" showed *"6 live · 23 seeds"* above six rows — no integer on screen equalled what was
on screen. R4 states its row count three separate ways; the Lab stated it none. Both halves are
fixed: a **"Showing N of M"** line whose N is the rendered count, and a split computed from the
**filtered** set. **D21–D21c** pin the count, the filter response, and that the split follows.

**What is deliberately not adopted: pagination.** R4 pages (`Show 15 more` / `Show all 159`)
because 159 cards is a scanning problem. Thirty observations is not, and this surface exists so
that every early sighting is visible — putting observations behind a control would trade a real
capability for a scroll. Stated here rather than left to look like an oversight; if the real feed
ever produces a stream where the scroll is the problem, the R4 expansion bar is the idiom to
adopt, not a new one.

---

## 3. What the Lab does NOT do

Read as a list of deliberate absences, because an absence and an oversight look identical:

- It does not rank, gate, size, originate, or mutate anything (LAB-0 §1). There is no code path.
- It does not rename, re-split, merge or reorder the six boards or the observation classes.
- `lab-g0-c2a-v1` is a **display set intersection**: `detector_id = null`, zero events, episodes
  or scores minted (`DNR:KILL-WASHOUT-TURN` confronted by name). **D9d** asserts the surface says
  so on its own receipt.
- It does not touch the graded-board population, `us_standouts.json`, or `us_board_ledger`
  (`DNR:KILL-PROPHET-POP-MERGE`).
- It reads no forward outcomes for ranking (`DNR:KILL-OUTCOME-AUDITION`).
- It draws no event markers inside the spark (out of scope for V1).
- It shows no Research Priority ordering (optional and non-blocking; not a launch dependency).
- It adds no second header family, no new `theme.css` token, no third page header.

---

## 4. The fixture, and exactly which parts of it are real

**This is the artifact's biggest honesty exposure and it is stated first.** The R4 board fixture
is a real extract of a committed payload. **The Lab half of this one cannot be.**

Radar's live transport (R-LAB-1 / W4.1) has not landed, so no canonical
`mastermind.entry_event.v1` stream exists to extract; there is no store to read and no honest way
to obtain a real first-observation time. Therefore:

| Fact | Real? |
|---|---|
| ticker · company name · sector | **real** — from the committed R4 payload |
| the spark SVG | **real**, and only ever attached to the ticker the payload drew it for |
| the Prophet comparison (lifecycle state, plan-open date) | **real** — the same plan rows the R4 board renders |
| which detector fired · when · first-observation time · observation class | **synthetic** |
| the `% change` on each row | **synthetic**, exactly as R4 marks its own |

Synthetic facts are marked `data-mock-lab` / `data-mock-live` in the DOM and disclosed on the
harness bar. **No chart is fabricated**: a Lab row whose ticker carries no spark in the payload
renders the printed null, so the enrichment gap is visible in the Lab too rather than papered
over with a drawn line.

Shape, and why it is this shape (`tools/gen_lab_fixture.py`):

```
30 observations · 7 live-forward · 23 retrospective seeds        (R5.1)
   lab-g0-v1 14 · lab-c1-v1 6 · lab-c2a-v1 10 · lab-c2-variants-v1 28
   lab-g0-c2a-v1 7 · lab-all-early-v1 30
   leads: +3  +2  +1  0  −3  ·  2 rows with no plan to compare against
```

- **Seeds dominate, on purpose.** At commissioning almost everything is history (LAB-0 §4). A
  design that only worked when seeds were rare would fail on its first day.
- **The seven live-forward rows exhibit every lead branch** — favourable (+3 / +2 / +1), same-day
  (0), **adverse (−3)**, and two rows with no plan to compare against. *R5.1 / VTL-403: the R5
  fixture wrote `null` for every adverse case, so the asymmetry was invisible in the artifact and
  two of five branches were never photographed. A generator convention was standing in for a
  guard. Leads are now signed and emitted whenever measurable — a fixture that only ever flatters
  the system it measures is a brochure, not a fixture.*
- **Two live rows and four seeds carry no spark**, so the printed null is photographed in both
  observation classes rather than only in the flattering one.
- **Three seeds sit on names Prophet has already graded out**, so `Resolved` appears in the
  comparison column.
- The generator raises rather than silently substituting if a named ticker loses its spark in a
  future rebake.

---

## 5. Evidence

`crops/` — **49 views, 66 files**, at 1440×900 and 390×844, produced by `tools/capture.py`.
Every crop is re-shot at the R5.3 SHA.

| Range | What |
|---|---|
| `01`–`05` | **LIVE**: the R4 board with the affordance at rest, dark EN + light ZH + 390w, and `op=0` proving the page is the R4 board with no Lab bytes at all |
| `10`–`17` | **LAB**, the full matrix: 1440 + 390 × dark + light × EN + ZH |
| `20`–`27` | the six frozen board selectors, plus one in light ZH and one at 390 ZH |
| `30`–`34` | observation class in isolation — history only and first-hand only, both languages, plus 390w |
| `35`–`37` | **the lead symmetry** — all five branches in one view (+3 / +2 / +1 / same day / −3), dark EN, light ZH and 390w |
| `40`–`4c` | the three degraded states — empty · behind · unavailable — with **all four theme × language corners** on the two that carry the unknown-vs-zero distinction *(R5.2 / R52-D3: `49`/`4a`/`4b`/`4c`. Until now theme and language only ever moved together, so neither could be judged alone.)* |
| `50` | the **round trip**: LIVE after a Lab excursion, with the card count proven equal to a cold load |
| `51`–`53` | *(R5.2 / PR51-1)* **the pinned divider, 1,200px into the seed region** — dark EN, light ZH and 390 — the scroll position the claim is actually about. Every R5.1 crop framed the divider at the crossing, which is the one place a pinned and an unpinned divider look identical. |
| `54` | *(R5.2 / R52-D3)* **a 390 crop that contains a signed lead** — the adverse chip, whole in frame. The shot named for the lead symmetry at the design floor had been photographing only chrome. |
| `55` | *(R5.3 / PR52-1)* **the chrome=1 seam, photographed** — the harness bar pinned at the viewport top with the divider immediately below it, 1,200px into the seed region. R5.2 asserted this seam three times and shot it zero times, and it was false when it was written; the capture refuses to emit unless bar **and** pin are on screen together. |
| `56`–`57` | *(R5.3 / VTL52-604 · 605)* **the LENS open at 390, EN and ZH**, taken by TAP in a touch context. No crop in the R5.2 set photographed a popover anywhere, so every ≤560 demotion claim was visually unreceipted — and the capture path actively parked the cursor to close tips before shooting. |

**Retired at R5.2:** `32-live-only-dark-en.png`. It shot the same URL as `35-lead-symmetry-dark-en`
and was byte-identical to it (`md5 9df1a63e…`), so the set claimed a view it did not hold. `35`
keeps the slot because it also ships the full-page frame.

Every capture asserts its own state before it shoots and **raises** otherwise: a LAB crop that is
not in LAB, a LIVE crop whose affordance presence disagrees with the entitlement, a Lab view with
a Prophet card visible, or a round trip that did not restore LIVE exactly, all fail the run
rather than producing a picture of the wrong thing. Zero horizontal page scroll is asserted per
shot at every width.

**Checks (R5.3).** `tools/verify.py` — **162/162**, run against the rendered page across both
themes, both languages, both modes, all six boards, both viewports, `chrome=0` **and** `chrome=1`,
and — for the LENS — a real touch context under `any-pointer: coarse`. `tools/mutation_test.py` —
**34/34 caught**, each with a distinct killer and no two mutations sharing a sole catcher.
(R5.1 shipped 104/104 and 19/19 at `f889d5eb35f3`; R5.2 shipped 125/125 and 26/26 at
`f40ae70ac989`. R5.3 adds **fourteen new check ids** — `D6c4b`, `D6c4c`, `D6g2`, `D6i4`, `D25`,
`D26`, `D26b`, `D26c`, `D27`, `D28`, `D28b`, `D28c`, `D28d`, `D29` — and rewrites `D6c4`; the
count rises by 37 rather than 14 because most of them run per language, per width, or per
`chrome` value. Eight new mutations: `M27`–`M34`. All are mapped to their rulings in §0c.)

### R5.1 — what the new mutations bought, and the one that mattered most

**M17 is the C1 mutation the verdict asked for by name, and it earned its place immediately.**
It caches `#board.innerHTML` on LAB entry and re-inserts it on LIVE — a genuine snapshot restore —
*while leaving the repaint counter incrementing*. Result: **D15d passed and D22 failed.** That is
the proof the condition was after: the counter was a self-report, not evidence, and the sentinel
attribute is the thing that actually observes re-derivation. R5's own M8 had attacked the counter
rather than the mechanism, so the law had never been tested.

Two more found real holes rather than confirming intent:

| Mutation | What it exposed |
|---|---|
| **M1** (label every row a live sighting) | Every seed check selected on `.lab-row--seed`, so a change that stopped emitting that class would have made all of them pass **over an empty set** while the honesty encoding vanished — the exact vacuity trap R4 warned the next cycle about, in a third shape. **D6h** now pins the rendered class census to the payload. |
| **C3's own sweep** | The banned-vocabulary scan fired on the **ruled** lifecycle word *Invalidated*, because `"validated" in text` matches it as a substring. The first time the scan ever ran over the LIVE view it flagged compliant copy. Now a negative-lookbehind regex — a check that fires on correct copy trains people to ignore it. |

### R5 — what writing the mutations bought

Four of the first thirteen mutations **survived** the first harness, and each exposed a real hole
rather than a stylistic one:

| Mutation | Why it survived | Repair |
|---|---|---|
| paint a seed with the live treatment | `D6c` asked only whether a node *matched a selector* — `hidden`, `display:none` and an empty label all satisfy that while disclosing nothing | `D6c` now requires the chip to be **visible with non-empty text**; `D6c2` added |
| drop the per-reading identity receipt | `D7b` tested the page-wide receipt string, and the **board selectors** carry detector ids too — so the check passed with every row receipt deleted | `D7c` added: each reading must carry **its own** identity |
| silent LIVE fallback on a dead feed | the mutation was mis-aimed at the ladder, which contains no card | re-aimed at the real defect (skip the plane repaint), now caught by `D14` and `D14b` |
| blank the seed lead slot | the mutation produced JS the harness could not drive at all, and a **crashed** verify returned no failures — which read as "the guard is fine" | mutation rewritten to valid JS; `mutation_test.py` now treats a non-zero exit with no parsed failures as an **error**, never a survival |

That last one is the R4 README's own warning coming true in a new form: R4 found two guards that
had stopped measuring while still reporting green, and told the next cycle to re-check that class
first. This cycle found a third shape of it — a harness that cannot run reports nothing, and
"nothing" is indistinguishable from "clean" unless the runner is told otherwise.

---

## 6. Open questions for the R5 reviewers

Named here so they are adjudicated rather than discovered.

**Q1 — the fixture's Lab plane is synthetic, and cannot not be.** Everything in §4 is honest, but
a reviewer cannot verify a design against data that does not exist yet. The reference is
therefore a claim about *composition and disclosure*, not about how the real distribution will
look. If R-LAB-1 lands before the R5 verdict, a rebake against real Radar output is the stronger
evidence — and per R4's own frozen-payload rule, a rebake would then need its own SHA rather than
silently replacing the population a critic reviewed.

**Q2 — is a pinned divider the right price for the per-row chip?** *(Rewritten at R5.2 —
the R5.1 text still asked whether the 23 per-row chips were a Law-4 violation, which VTL-408 had
already answered and R5.1 had already acted on.)* The chip is gone and the class label lives on a
divider that occupies the top of the viewport for as long as the seed region is on screen. That is
a permanent ~34px at 390 traded against a constant on 23 rows, and the split in §0b keeps the
*lesson* out of the pinned half so the bill stays at the label. A reviewer may reasonably hold that
a research surface should never spend fixed viewport, in which case the lever is the divider's
height, not the encoding — the four structural channels on the row are unaffected either way.

**Q3 — the identity column carries visible air at ≥1180w.** The chips are short, so roughly a
third of that column is empty. Nothing was invented to fill it (the removal test cuts before it
adds), but a reviewer may reasonably prefer a narrower measure or a wider chart.

**Q4 — the mock's controller is a post-render takeover, not the production controller.** §1.1.
The behaviour is right; the mechanism is not the one P-LAB-UI will build. A reviewer judging
"is this implementable as ONE controller" should read LAB-0 §6.5, not this file's `lab.js`.

**Q5 — `stock.html#TICKER` is the row's destination**, following R4's ruled card-link convention.
It is a dead link inside the mockup directory, exactly as it is in the R4 reference.

**Q6 — R4 itself has never been independently reviewed.** R5 inherits that. The R5 cycle is the
first opportunity to adjudicate R4's composition, and a verdict that approves the Lab while
leaving R4's own composition unadjudicated would leave the reference stack in the state that
created this footnote.

---

## 7. Known limits of this artifact

- The controller is a post-render takeover (§1.1, Q4).
- Re-executing `board.js` on each LAB→LIVE flip re-registers its document-level listeners, so a
  long session accumulates duplicates. Harmless here (ladder clicks navigate; detached LENS
  popovers are removed first) and absent in production, where one controller owns the grid.
- The Lab plane's data is synthetic (§4, Q1).
- **The divider pins to `top: 0` because this mockup has no site header.** The production route
  loads the shared `_site_nav` family, and if that header is itself sticky the divider will pin
  underneath it. The seam is named rather than left to be discovered: `.lab-mark` reads
  `top: var(--lab-mark-top, 0px)`, so P-LAB-UI binds one value at the page scope instead of forking
  the component. The mockup cannot choose that number, because the mockup does not render the
  header it would have to clear.
- No event markers in the spark (out of scope for V1, §3).
- Research Priority ordering is not implemented (optional and non-blocking by LAB-0 §1).

---

## 8. Scope

No production file is touched. The additions live entirely in `mockups/refs/prophet_lab/`. The
R4 reference directory is **read-only to this cycle** and is byte-unchanged. The RIG packet for
this candidate is `research/reference_integrity/prophet-board-lab-r5/`, and it deliberately
contains **no `approval.yml`**.
