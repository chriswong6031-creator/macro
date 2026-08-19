# Prophet Operator Lab — D-LAB-R5 reference candidate

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
| `chrome` | `1` (default) · `0` | harness bar; crops are `chrome=0` |

```bash
python3 prophet_lab/tools/gen_lab_fixture.py                                   # rebuild the fixture
python3 prophet_lab/tools/capture.py  http://localhost:8794/prophet_lab crops   # 36 views / 49 files
python3 prophet_lab/tools/verify.py   http://localhost:8794/prophet_lab         # 72/72
python3 prophet_lab/tools/mutation_test.py http://localhost:8794/prophet_lab    # 13/13 caught
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
   §4 forbids reconstructing it, so the slot prints the signal's own date and the label says
   `signal date · not a sighting`. The absence is *printed*, not padded. **D6b** asserts no seed
   ever prints a clock time.
2. **The spine goes dashed** and the node goes hollow. **D6e / D6f**.
3. **A hatched, dashed class chip** — `Seed · history, not a sighting` / 「回溯样本 · 非实时观测」
   — reads as a different *kind* of object before a word is read. **D6c**, and **D6c2** asserts no
   seed ever wears the live treatment.
4. **The lead is impossible, and the row says so**: `Lead not measurable`, with a LENS receipt
   explaining that the feed never supplied a first-observation time and we do not invent one.
   **D6** asserts no seed ever carries a measured lead.
5. **The ink drops** — seed rows render in muted ink with a quieter spark.

**Why one stream and not two groups.** Grouping seeds below a rule would be easier to draw and
weaker as a design: LAB-0 §3 freezes the default sort as newest-first, and a class partition
changes what the top of the board is. Keeping one stream forces the distinction to survive
*adjacency*, which is the case that actually matters — and the `All / Live only / Seeds only`
filter (default All) still gives the operator the partitioned view on demand. The seeds-only
crop (`30`, `31`, `34`) exists so the seed treatment can be judged on its own rather than only
next to a live row that flatters it.

**A deliberate deviation from Law 4 (no per-row repetition of a constant).** In the `Seeds only`
view every row carries the same class chip, which the doctrine's word-budget law would normally
send to a footer. It stays, because the constant-in-the-footer rule assumes the constant is
decoration, and here the row's class is the row's single most load-bearing fact: the row must be
self-describing when seen alone, mid-scroll, out of the header's context. This is the same
argument R4 already accepted for the episode chip — *"the chip must disambiguate on a card seen
alone"* (R4 DESIGN_NOTES §4). Recorded here rather than left for a critic to find.

### 2.5 The lead slot always says something

Three states, and all three are real results the fixture exhibits (§4):

| Case | Row reads |
|---|---|
| Lab saw it first | `Seen 3 days before Prophet` |
| Prophet had a plan open already | `No lead — Prophet was first` |
| Prophet has no plan on the name | `Nothing to compare yet` |
| Retrospective seed | `Lead not measurable` |

The slot is **never blank**. An empty slot reads as "zero lead", which is a claim nobody made.
**D6g** asserts one lead slot per row; mutation **M13** (blank it on seeds) is caught.

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

- **Empty** — *"Nothing early on this board right now. The feed is reporting and it is reporting
  nothing. That is a real zero, not a gap."* A real zero, said as one.
- **Behind** — the Lab's own disclosure, deliberately **not** production's behind-the-tape
  banner: that one describes the plan book's *price* vintage, and reusing its words for a
  different producer would tell the reader the wrong thing is late. The spine grows a dashed
  head segment labelled `nothing since 11:36 ET` — an absence of observations drawn on the
  instrument that measures it.
- **Unavailable** — *"The Lab feed is not answering… Prophet's live board is unaffected — switch
  back to Live to use it."* with the switch inline. Names what failed **and** what still works.

**D14 / D14b / D14c** assert each state keeps `data-mode=lab`, keeps the eyebrow, shows zero
Prophet cards, and does not scroll horizontally at 390. Mutation **M11** (leave the live grid
painted when the feed is down) is caught by both.

### 2.10 Responsive, motion, accessibility

- **390w is the design floor** and the spine survives to it, because it is the signature *and*
  the honesty carrier. Chart → identity → Prophet stack inside one gutter, in the same reading
  order as desktop left-to-right. Selector chips scroll inside their own container. **D16**
  asserts zero horizontal page scroll across five Lab views at 390.
- **The mobile reduction is a re-composition, not a squeeze** (§15): the band tightens and the
  sort-basis sentence **demotes to the count chip's LENS** rather than being cut — demotion with
  a landing, never silent removal.
- **Motion is a status channel.** Exactly one thing animates: the feed dot, and only while the
  feed is reporting; `behind` and `unavailable` rest (the shipped `.dtp-dot` law). The mode flip
  is one 140ms fade on the board region. `prefers-reduced-motion` kills both **by name**,
  pseudo-elements included.
- **Toggles never move on hover.** Rows take the table row-hover tint; only clickable containers
  lift, and a row is not a container. Focus rings derive from `--link`. The mode control is a
  real `role="radiogroup"` with arrow-key traversal.

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
29 observations · 6 live-forward · 23 retrospective seeds
   lab-g0-v1 14 · lab-c1-v1 6 · lab-c2a-v1 9 · lab-c2-variants-v1 27
   lab-g0-c2a-v1 7 · lab-all-early-v1 29
```

- **Seeds dominate, on purpose.** At commissioning almost everything is history (LAB-0 §4). A
  design that only worked when seeds were rare would fail on its first day.
- **The six live-forward rows exhibit all three lead states** — a measured lead (3 / 2 / 1 days),
  `Prophet was first`, and `nothing to compare`. A fixture that only ever produced flattering
  leads would have designed the slot for one case and left the other two for a builder to invent.
- **Two live rows and four seeds carry no spark**, so the printed null is photographed in both
  observation classes rather than only in the flattering one.
- **Three seeds sit on names Prophet has already graded out**, so `Resolved` appears in the
  comparison column.
- The generator raises rather than silently substituting if a named ticker loses its spark in a
  future rebake.

---

## 5. Evidence

`crops/` — **36 views, 49 files**, at 1440×900 and 390×844, produced by `tools/capture.py`.

| Range | What |
|---|---|
| `01`–`05` | **LIVE**: the R4 board with the affordance at rest, dark EN + light ZH + 390w, and `op=0` proving the page is the R4 board with no Lab bytes at all |
| `10`–`17` | **LAB**, the full matrix: 1440 + 390 × dark + light × EN + ZH |
| `20`–`27` | the six frozen board selectors, plus one in light ZH and one at 390 ZH |
| `30`–`34` | observation class in isolation — seeds only and live only, both languages, plus 390w |
| `40`–`48` | the three degraded states — empty · behind · unavailable — each in dark EN, light ZH and 390w |
| `50` | the **round trip**: LIVE after a Lab excursion, with the card count proven equal to a cold load |

Every capture asserts its own state before it shoots and **raises** otherwise: a LAB crop that is
not in LAB, a LIVE crop whose affordance presence disagrees with the entitlement, a Lab view with
a Prophet card visible, or a round trip that did not restore LIVE exactly, all fail the run
rather than producing a picture of the wrong thing. Zero horizontal page scroll is asserted per
shot at every width.

**Checks.** `tools/verify.py` — **72/72**, run against the rendered page in both themes and both
languages. `tools/mutation_test.py` — **13/13 caught**, each with a distinct killer and no two
mutations sharing a sole catcher.

### What writing the mutations bought

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

**Q2 — is the seed chip on every row a Law-4 violation?** §2.4 argues it is not, on the R4
episode-chip precedent. It is a design-authority call and it is put on the record rather than
assumed.

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
- No event markers in the spark (out of scope for V1, §3).
- Research Priority ordering is not implemented (optional and non-blocking by LAB-0 §1).

---

## 8. Scope

No production file is touched. The additions live entirely in `mockups/refs/prophet_lab/`. The
R4 reference directory is **read-only to this cycle** and is byte-unchanged. The RIG packet for
this candidate is `research/reference_integrity/prophet-board-lab-r5/`, and it deliberately
contains **no `approval.yml`**.
