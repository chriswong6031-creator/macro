# Prophet Board — mockup gate notes (MP-1 / gate G-C)

**Status:** **R3 — the RIG R2 revise mandate.** G-C is FROZEN / ACCEPTED at `8d5df856095`; that
SHA stands as an immutable checkpoint. The work below is authorized by the R2 REVISE verdict and
produces a **new SHA for a fresh RIG cycle**. It does not reopen G-C.

**Not self-approved.** No `approval.yml`. The new SHA is returned for review.
Frozen visual reference for the `us_stocks.html` migration.
**No production file is touched by this directory.**

**Binding authority, in precedence order**
1. `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md` (PR #5504, merged) — on any conflict it wins
2. the operator's G-C revision handoff (2026-08-13) — card philosophy and the keep/drop list
3. `research/migration_packets/MP-1-prophet-board.md` (PR #5505)
4. `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` §0 + §B as amended 2026-08-13
5. shipped design-system primitives (`theme.css`, `tier_preview.css`, `_prophet_card.html.j2`, LENS, `.actcol/.acth`)

---

## 0. How to run it

```bash
python3 -m http.server 8792 --directory mockups/refs/institutionalize/us_stocks
```

| Parameter | Values |
|---|---|
| `theme` | `dark` (default) · `light` |
| `lang` | `en` (default) · `zh` |
| `state` | `paid` (default) · `today` (alias — same universe) · `anon` · `empty` · `episodes` · `fallback` (diagnostic) |
| `life` | `watch` `ready` `entered` `delivering` `overtime` `invalidated` `resolved` |
| `view` | `grid` (default) · `table` |
| `chrome` | `1` (default, harness bar) · `0` (clean, used for crops) |

`compare.html` is the three-way card adjudication (production · #5514 v1 · revised).

```bash
python3 tools/gen_fixture.py board-data.js      # regenerate data from origin/main
python3 tools/capture.py  http://localhost:8792 crops
python3 tools/verify.py   http://localhost:8792 # 136/136 acceptance checks
```

**The data is real.** `board-data.js` is a committed extract of `site/prophet/index.json`
(asof 2026-08-13, 179 plan rows) and `site/factordata/us_standouts.json` (as_of 2026-08-12).
`lifecycle_state` is derived by the ruling §6 precedence, verbatim. Counts reconcile:

```
62 ready + 95 entered + 0 delivering + 0 overtime + 2 invalidated = 159 = open_count
159 live + 20 resolved                          = 179 = active_count
grid: 40 cards + "+119 more"                             = 159 = headline
```

*(payload re-baked to asof 2026-08-13 during R3; the invariants re-derived and still hold)*

---

## 0a. R3 — satisfying the RIG R2 revise verdict

Accepted architecture preserved unchanged: chart-first card, unconditional live quote/change,
the ruled stance projection, Priority, zone-not-levels, the lifecycle ladder, Setups/Candidates
separation, plan-row identity, bilingual structure, table view, anonymous state, and the
lifecycle weight grammar.

**A · Risk ledger carrier — restored.** The ⚠ capability was deleted outright in the first pass.
It is back as the shipped `.pv-cau` component (verbatim CSS): a counted pill at glance tier, the
sentences one hover/focus deeper. Rows are bound to real candidate fields — blow-off/burst mover,
`ext_z > 2`, anti-chase shadow, and the earnings window — never authored. It sits in the marks row
rather than the chart overlay, because the overlay is capped and already carries the stance and ⚡;
a third chip there collided with the live quote. 18 rows carry cautions today.

**B · Zone is geography again.** The shipped `zone_kind` split was flattened in the first pass, so
every card rendered its zone in the active buy treatment — an implicit instruction on a Wait card.
Restored to the shipped derivation (`dashboard.html.j2:16183`): **active** only for Buy/Near,
**Re-add** for Hold, **muted** for Wait/Avoid, and the confirm/none prose when there is no band.
The zone is still shown in every case; only its treatment changes. Today: active 19 ·
re-add 7 · muted 35 · no band 118.

**C · One universe, no view exemption.** The reference-only subset is gone. `paid` and `today`
render the same population — the whole plan book — so the headline, the ladder cells, the rendered
cards, the expansion bar, the filters and the table view all describe one universe. The earlier
"reference renders 33, headline says 162" split was itself the count-law contradiction; enrichment
coverage now shows honestly on the cards instead of being filtered away.

*Amended at R4 under PRC-306.* The overflow is no longer a `+N more` link routing to the table.
The grid holds the whole partition and reveals it in place via the shipped `.sm-*` expansion bar
(`Showing N of M` · `Show N more` · `Show all M`), so **every plan row is reachable as a CARD** —
159 visible after one click, evidenced in crops `90`/`91`. The table is now an alternate
representation, never the only route to the tail.

**D · No producer-less market assertions.** The regime / breadth / posture chips are **deleted** —
they asserted a market call with no producer behind them. Groups is no longer five authored lanes
of invented sectors: it is bound to `us_standouts.themes_in_favour`, a canonical artifact, and
renders recommendation, run length and member count straight from the payload with its
as-of printed on the surface. If the key is absent the section says so rather than inventing a
call to keep the composition full.

*Amended at R4 under PRC-316/PRC-317.* Two corrections. The `RECO` map was five values and the
payload ships `enter`, which fell through to the raw slug — leaking the English token `enter` into
Chinese copy; the map now covers every slug and an unmapped one renders nothing rather than its
identifier. And **rank is no longer printed**: the eight themes carry ranks 1, 5, 6, 7, 9, 11, 12,
19 — non-contiguous, i.e. filtered out of a larger ranking whose size the payload does not carry.
An ordinal without its denominator is not a fact, so the list is sorted by rank and sequence
carries the ordering. If a `themes_total` ever publishes, the ordinal comes back.

**E · Visual conditions.** Featured is the operator-ratified aura again — a `--pv-buy` pinned ring
plus glow plus lift, and the lit rail — not the bare inset ring the first pass reduced it to
(verbatim from `_prophet_card.html.j2:109-130`). Stance inks are now a deliberate tone off the
direction inks (`theme.css` ships `--pv-buy` *identical* to `--up`, so a Buy chip and a positive
tick were the same colour); they still derive from `--up`/`--down`, so the zh flip is intact.
Light mode gives cards a white plane against the tinted canvas so they sit **on** the page. At
390w the page head and chart tighten to production's own small-screen height, putting whole
opportunity cards above the fold with the 4+3 ladder and every count untouched.

**G-D display defect — repaired.** `enriched` was declared **twice in one function scope** with two
different formulas — spark-only (45) and spark-plus-stance (33) — so the second silently shadowed
the first and every sentence that printed it showed 33 while describing the 45-row join. Both
declarations are gone; coverage arithmetic is computed once, here in the notes. `verify.py` R-GD1/2
pin that no variable is declared twice inside `setups()` again.

**Open constraint, not papered over:** at 390w the first *actionable* (Buy/Near) card cannot be
guaranteed above the fold. The board sorts by the engine's priority rank, and tonight the #1 and
#3 priority rows are no-read cards — the G-D coverage gap surfacing. Guaranteeing a Buy above the
fold would require re-sorting by stance, which contradicts the stated sort rule; that is an
operator ruling, not a layout fix. Once G-D lands, the top rows carry stances.

---

## 0c. R4 — closing the RIG R3 REVISE verdict (#5552)

R3 returned **REVISE** over `6ad6b51b`. This pass closes it. The full disposition of all 41 rows
of that record — every blocking finding, both authority-delta rows, all three task-matrix rows,
12 carried majors, 13 carried minors and 1 withdrawn — lives in
`research/reference_integrity/prophet-board-5514-r4/R4_CLOSURE_LEDGER.md`, which is **generated**
by joining the frozen record against the disposition table and hard-fails if any finding lacks a
disposition. A finding cannot be dropped here by forgetting it.

**The four capability-shaped findings that had survived three revisions are the point of this
pass.** R3's own strongest argument against approval was that the previous cycle "fixed everything
its rationale discussed and moved nothing that appeared on no list" — the code-shaped conditions
got closed while a link, a stale banner, a proof number and a route to 43% of the book stayed
invisible. All four now exist: the card routes to `stock.html#TICKER`; the behind-the-tape banner
is bound to production's `_compute_board_staleness()`; Evidence carries the real track record with
its confidence interval; and every plan row is reachable as a card.

**What did NOT change, deliberately.** The R3 verdict recorded nine preserved strengths and none is
touched: the one-universe count law, producer-bound Groups, the ⚠N caution carrier, the
stance-branched zone, the light-mode card plane, the empty-vs-absent state writing, the ruled
seven-cell ladder, the withhold-by-absence anonymous gate, and the artifact's own harness. This was
a closure pass, not a redesign.

**Two deliberate deviations from the brief, both proven before adoption:**

1. **The stance ramp's light value is 54%, not the critic's 62%.** The critic's ramp reproduces
   exactly and its central insight is load-bearing — on a dark panel no *deepening* mix of `--up`
   can out-contrast amber, so the free parameter is the *direction* of the distinctness mix, toward
   `--text`. But at light 62% `--pv-buy` resolves byte-identical to `--ink-up`, because light
   `--ink-mix-up` is also 62% — so the BUY badge and the live +N% change on one card would paint one
   value, which is the DA-002 defect repeating in the other theme. At 54% the ordering holds in all
   four quadrants, light contrast *rises* (7.12 vs 6.29 en; 8.75 vs 7.85 zh), and the chip separates
   from the tape ink in four quadrants instead of two.
2. **The fixture is NOT rebaked.** `gen_fixture.py` read `git show origin/main:<path>` — a moving
   ref taking ~24 nightly commits every two hours — so a rebake would have silently replaced the
   population the verdict was issued over, and could have made VTC-301 read as "fixed" merely
   because a different night had more sparks. `board-data.js` is additive-only (`staleness` and
   `track` appended, every other key byte-identical); `gen_fixture.py` is repaired to a
   repo-relative path and a pinned SHA. The stale numbers in *this document* were stale against the
   already-frozen payload, and the prose is what moved.

**Not waived.** G-D (#5541) and the overtime producer contradiction (#5540) remain open production
blockers. Closing a visual reference closes neither, and neither is a reason to weaken it.

**This pass self-approves nothing.** It produces a SHA and stops; approval requires a fresh
independent RIG cycle with new critic receipts, because receipts go stale the moment the frozen SHA
moves (RIG §3).

---

## 0b. The G-C correction pass (operator audit, 2026-08-13)

The composition passed Product/Taste review — ladder, density, card anatomy, Priority placement,
lifecycle treatment, Zone footer and chroma level are settled and are **not** revisited. Five
narrow corrections were applied; no structural redesign.

**1. ~~The canonical reference now shows the intended experience.~~ — SUPERSEDED at R3 by
PRC-203; struck at R4 under DA-001. DO NOT REBUILD.**

> **Repealed text, retained only so the repeal is legible.** *"`state=paid` renders the plan rows
> the fixture can draw at full fidelity (33 today — an internal fixture fact, never surfaced), and
> states the canonical product population: 162 live · the Prophet book… `state=today` is the
> honesty state showing the actual payload including the 60% awaiting their entry read, and is the
> state the count law is verified against. A 60%-`暂无判断` board must not become the flagship
> reference."*

**What is law instead.** The design authority's blocker **PRC-203** ruled that a view rendering a
different population than the one its integers describe *is* the count-law contradiction. The
`state=paid` exemption and the full-fidelity subset it selected are **withdrawn**. There is now
**one universe, no view exemption** (§0a.C): `paid` and `today` render the same population — the
whole plan book — and the count law closes over it arithmetically (62+95+0+0+2 = 159 = `live_total`;
159 + 20 resolved = 179 = `active_count`; 40 rendered + "+119 more" = 159). `board.js` implements
exactly this; `isRef` survives as a declared-and-never-read vestige of the repealed rule.

**And the mechanism the repealed rule justified is withdrawn with it.** "A 60%-`暂无判断` board must
not become the flagship reference" was the stated reason for filtering the reference view down to
the enriched subset. That trade is no longer available: an unflattering board that counts honestly
outranks a flattering one that does not. A reference is not permitted to improve its own composition
by choosing its population.

**How full fidelity actually catches up: G-D, not a filter.** The coverage gap is real — the
entry/actionability axis reaches 61/179 and enrichment 45/179 — and it is closed by **spawn gate
G-D** (§7, PR #5541), which makes coverage a hard *production* dependency. G-D is a data gate on
what ships to production; it is **not** a licence for a frozen reference to hide the rows it has
not enriched yet. Coverage is disclosed on the cards and sized honestly in §6 Q1, never filtered
away.

*Amendment record: DA-001 (authority-originated, corroborated by both R3 critics at pass 2). The
R3 artifact shipped this paragraph and §7's `state=paid` description as current law while the code
implemented their repeal — two contradictory positions, unmarked, in a document that becomes law.
A migration builder could not tell which paragraph to follow. §7 is corrected in the same pass.*

**2. The live-quote slot now actually renders on every card.** The previous pass put `data-sym` on
every card and claimed `live.js` could therefore paint every quote — but only created the quote
DOM when an SSR price existed, so un-enriched rows had no `.nb-px`/`.nb-chg` node to hydrate. The
slot is now unconditional; un-hydrated it reads an em dash in muted ink, exactly as the shipped
card server-renders it.

**3. Two pieces of shipped visual grammar were restored.**
- **Stance chip hierarchy** (`_prophet_card.html.j2:174,178`): only **Buy** is a solid badge;
  every other verb is a 13% tint + coloured text + a 40%-alpha border. The previous pass made all
  five solid white-on-hue, which read as five equally loud calls.
- **The spark-recolour law** (`:162-163`): `.pv-chart svg * { stroke: var(--pvh) !important }`
  plus the `[fill]` rule recolour the whole spark *and its baked zone band* to the stance hue.
  Without it, DAR rendered a red 买入 chip beside an amber chart — two stance colours on one card.
  Restored, a Buy card in Chinese is one coherent red system while the daily negative change stays
  independently green.

**4. Three badges are now SOURCED, not approximated.** This mattered more than the CSS:

| Badge | Was (approximated) | Now (sourced) | Rows |
|---|---|---|---|
| ★ Featured | `coiled.star` | `row["featured"]` — the Priority Engine's own gated cohort flag (`featured_shortfalls`) | 10 |
| New | `age_days <= 1` | `row["new"]` — the shipped contract `sig_date == board_date` (`us_board_rank.py:1109`) | 40 |
| ⚡ Triggered / Imminent | plan age ≤3d / `Ready + buy_now` | membership in `setups.json.buy`; `signal.tier_cascade == "T3"` is Imminent (`dashboard.html.j2:16187-16189`) | 8 / **0 today** |

Imminent is **0 today** because no row carries T3 — an honest zero from a real producer, rather
than four cards inferred from a nearby field. Trigger recency is not derivable from plan age.

**5. Native zh pass + PR-body refresh.** The operator's wordings adopted verbatim
(`跟踪中计划`, `下方 6 个状态合计`, `「观察」将在下一次收盘更新后发布`,
`今日变化 · 过去 24 小时新增 N`) plus a wider pass over the same register — build-system
vocabulary (`夜间构建`, `档位`) and literal translations (`在场计划`, `计划簿`) removed
throughout. The GitHub PR body has been rewritten to describe the current contract.

---

## 1. What changed at this revision

The first mockup fixed the Board's architecture and lifecycle semantics, then **over-corrected
the card**: it rebuilt the card around only the fields the plan book carries on every row, which
let a data-join gap redefine the flagship UX. That decision is reversed.

The revision keeps the Board from #5514 and restores the shipped card's DNA.

### Preserved from the current production Prophet card
- **Chart-first hero** at its shipped height (74px). The spark already carries its own
  relevant-zone band and paints in `var(--up)`, so it flips correctly under zh for free.
- **Live quote + change**, overlaid top-right of the chart. The change is the one place a
  direction ink belongs on this card, and it flips with the zh convention.
- **One-word stance chip** top-left — Buy / Near / Wait / Hold / Avoid · 买入 / 临近 / 等待 / 持有 / 回避.
  Its producer is now ruled (§6 Q7): the entry/actionability axis only, factored from the engine.
- **Compact identity** — ticker · company name · sector, in the shipped geometry.
- **⚡ trigger chip** and **restrained marks** (★ Featured · New · Bottoming/Continuation entry).
- **Zone footer** — `ZONE $70.66–$72.35` with the date pinned right. *(R4 / PRC-318: a zone whose
  endpoints are equal now prints as a single price, not a range with identical ends — 4 rows.)*

### Preserved from #5514
- The whole Board architecture: Setups = the plan book, Candidates as a separate population,
  the seven-cell ladder, lifecycle filtering, `#life=` fragments, honest count reconciliation,
  empty / anonymous / filtered states, Groups / Evidence organisation.
  *(R4 / VTC-307: the Market context section is **deleted**. It rendered a header and five tab
  anchors bound to no producer — a header retained over content that had already been removed.
  Evidence now closes the page with real quantities from `us_track_ledger.json` instead of four
  bare links: win rate WITH its confidence interval, the matured n against the in-flight n, and
  the number of boards the record covers. A win rate printed without its interval would be the
  overclaim this whole review cycle exists to catch.)*
- The ruled **hue-neutral lifecycle grammar**, now compact on the card: mark + word, nothing else.
- One card per plan `id`, dated episode chips, Resolved outside the live total.
- Retirement of the four-dot Bottoming → Turning → Ready → Trend rail.

### Removed from production
- The four-dot rail (two of its four steps are structurally unreachable).
- The full-card verb wash: the `::before` accent bar and the verb-tinted border are gone.
  Chroma is now spent on the stance chip and the chart, nowhere else.

### Removed from #5514 v1
- Plan-clock telemetry (`day 2 of 45`, `past its 45-day window`) — the horizon is an internal
  pacing parameter, and showing it reads as a holding-period promise.
- Paragraph `what_to_do_now` copy in the grid.
- The `Entry / T1 / Void` three-number footer — it framed Prophet as an order-execution oracle.
  Zone returns as the glance-tier abstraction; exact levels live in plan detail.
- The card's top weight cap (the ladder↔card link is now carried by the inline mark instead,
  so the cap does not compete with the chart for the card's head).

### Added
- **Priority** — the numeric readiness rank, restored per the Chairman override and already ruled
  by the Priority Engine masterplan §3.8. Quiet by design: visible for scanning, never louder than
  ticker, stance or price, and **never hued**, because it is not a win probability.
- **A disclosed no-read chip** for plans where the entry/actionability axis has not published —
  BLOCKED_DATA, never a guessed Wait (§6 Q7b). It carries no stance hue.

---

## 2. Card anatomy

```
┌────────────────────────────────────────┐
│ ENTRY WAIT ⚡Triggered   $74.13  +0.7%  │  axis · stance · trigger · live quote
│         compact price chart            │  74px, with its own zone band
├────────────────────────────────────────┤
│ FTI  TechnipFMC          PRIORITY  89  │  ← ticker+name is the LINK to detail
│ Energy                                 │
│ ★ Featured  New  Bottoming entry       │  restrained marks, max 3
│ ━━ Entered                             │  ruled lifecycle mark + word, no gloss
├────────────────────────────────────────┤
│ ZONE $70.66–$72.35             Aug 10  │
└────────────────────────────────────────┘

   …and when the chart has not published (116 of 159 live rows):

┌────────────────────────────────────────┐
│ ENTRY  No read yet              —   —  │
│           No chart yet                 │  74px — the SAME height, null PRINTED
├────────────────────────────────────────┤
```

*Amended at R4.* Three changes to the anatomy above:

- **PRC-312 — the stance slot names its axis.** `ENTRY` precedes the verb, because 27 rows are
  `life=entered` carrying `stance=wait` and "Entered / Wait" otherwise reads as a verdict that the
  open position should not exist. It is an entry read: *do not add here*. Ready's gloss also moved
  off "plan armed, trigger not fired" — which contradicted a sourced ⚡Triggered — to the lifecycle
  fact, `plan armed, not yet entered`.
- **PRC-301 — the card routes to the name.** Ticker + company name is an `a.pv-open` →
  `stock.html#TICKER` (the cross-market house convention), stretched over the card by `::after`
  while the caution / trigger / priority / lane controls are raised above it. A sibling anchor, not
  a wrapper: `.pv-newer` is itself an `<a>`, and an `<a>` inside an `<a>` is illegal.
- **VTC-301 / PRC-309 — the chartless hero is the SAME height and states its absence.** It was a
  24px strip stretched by the grid into a ~97px void beside a 74px neighbour, on 20 of the 40
  canonical cards. It is now 74px with `No chart yet` / `暂无图表` printed in it. The R3 artifact
  disproved its own data excuse — the identical rows already rendered as clean cards in the
  fallback lens and at 390w; only the canonical grid read as broken.

Everything a reader needs is answerable without opening the card, and **no paragraph is
required for any of it**: what it is, what Prophet thinks, the price, how it is moving, the
recent chart, its priority, whether it is featured or new, what setup type found it, where the
plan sits in its lifecycle, and which price area matters.

When the entry read has not published, the stance slot carries a dashed, hue-free **"No read yet"**
chip instead of a verb — an absent read, never a cautious one.

**Colour budget.** Chroma is spent on the stance chip and the chart. Direction ink appears only
on the live change. Lifecycle is weight-only and never hued. Violet remains lock-only. Featured
is a **ring**, never a container wash.

---

## 3. How the ladder grammar maps to the ruling

| Cell | EN / ZH | Weight |
|---|---|---|
| `watch` | Watch / 观察 | dashed hairline |
| `ready` | Ready / 就绪 | half filled |
| `entered` | Entered / 入场 | solid |
| `delivering` | Delivering / 达标 | solid |
| `overtime` | Overtime / 超时 | solid muted |
| `invalidated` | Invalidated / 失效 | hollow, struck |
| `resolved` | Resolved / 已结 | neutral outline |

Entered and Delivering are **deliberately identical**: the grammar encodes *commitment class*,
not per-cell identity, and the partition law guarantees label and count tell them apart.

**Direction-neutrality is structural.** No lifecycle mark references `--up`/`--down`/`--q*`.
`verify.py` G1 resolves computed styles against the live token values in both languages rather
than trusting the CSS.

**Identity and selection cannot collide.** The ruling warns that selection (fill + heavier rule)
and cell identity (also rules) must never collide. They sit on different geometric channels:
identity is the weight cap on the cell's **top** edge, always present; selection is background
fill plus a **bottom** rule, only when pressed.

**Resolved is outside the live count three ways:** outside the enclosure past a divider, labelled
"not in today's count", and absent from the default grid. The empty state proves it — headline 0,
six live cells 0, **Resolved still 17**.

**Key-absence is not zero.** `early_turn_watch` is genuinely absent from the payload, so the Watch
cell renders an em dash plus a disclosure line, never a silent `0`.

**Vertical footprint** was reduced per the handoff: the headline drops 40px→30px and the header,
ladder and section paddings tighten, so three card rows are visible above the fold instead of two.
No semantics, count or click target was reduced — only leading, type size and padding.

---

## 4. Duplicate ticker episodes

One card per plan `id`. 12 tickers carry more than one row; FBRT is the ruling's own exemplar and
is live: `FBRT-BULL-20260713` (opened 07-17, since resolved) and `FBRT-BULL-20260805` (opened
08-10, entered). ARES and PI are the same shape — PI carries three.

Cards **stand alone** under the global sort — never stacked or grouped. Every card of a multi-row
name carries a dated episode chip (`Episode 1 of 2 · Jul 17`), neutral ink, counted in nothing.
"N of M" was chosen over the draft "Episode 2" because the chip must disambiguate on a card seen
*alone*. A resolved episode links forward only when a live row exists — HLI and QCOM have two
resolved episodes each and correctly show no link.

---

## 5. How Candidates stays a second population

One printed total (**70**), decomposed by the **shipped** triage shelves —
**22 + 35 + 12 + 1 = 70** across four rendered shelves. The fifth shelf (`blocked`) is 0 today
and renders no chip at all, which is why four shelves account for the whole total.

*Corrected at R4 under PRC-320 (R3 receipt NEW-E). This line previously read
"69 … 28 + 27 + 10 + 2 + 2 = 69", which matched no state of the committed payload; the page has
been printing 70 throughout. The page was internally consistent and the rationale was not — the
failure mode this whole document is most exposed to, since a number in prose has no producer
checking it.*

Different noun, different form (pills, no weight marks), non-adjacent.

Two **shipped** sub-lines collided with lifecycle cell words and were relabelled under the
one-referent-per-page law:

| Shelf | Shipped sub-line | Collided with | Now reads |
|---|---|---|---|
| `live` | 入场窗口已打开 | **入场** = Entered | 买入窗口已打开 / "buy window is open" |
| `basing` | 尚无入场信号 — 观察，勿追高 | **入场**, **观察** | 尚无买入信号 — 勿追高 / "no buy signal yet — don't chase" |

"Buy" is also the honest word — these are buy rows. Shelf headings were untouched; none collided.

---

## 6. Open questions and doctrine tensions

### Q1 — the enrichment gap (HARD dependency before MP-1 production migration)

Five card fields arrive through the candidate join and are partial on plan rows:

| Field | Coverage |
|---|---|
| company name, sector, `lane`, `spark_svg` | **45 / 179** |
| SSR price text | 45 / 179 |

**Proposed solution, in two parts:**

1. **The live quote needs no payload work at all.** `live.js` paints `.nb-px[data-sym]` /
   `.nb-chg[data-sym]` client-side every ~60s; the SSR price is only a fallback. Emitting
   `data-sym` + `data-mkt` on every plan card — an attribute, not a field — gives 100% of rows a
   live quote and change. The mockup already emits it.
2. **name / sector / lane / spark need a payload path.** All four already exist tonight inside
   the builders that produce `us_standouts.json`; the gap is only that the join is taken against
   the **70** screened candidate rows instead of the full plan universe (166 tickers). The ask is a per-plan
   enrichment block on `index.json.plans[]`, keyed by ticker over the whole book. This is
   PR-0(c)'s neighbourhood but explicitly **not** authorised by MP-1, so it needs its own
   packet line before the migration builder is commissioned.

**Ruled (operator 2026-08-13):** this becomes a **hard implementation dependency before the MP-1
production migration**, not another reason to weaken the reference. The revised finding — that the
live quote needs only `data-sym` — materially simplifies it: name / sector / lane / spark are what
remain, and they need full-plan-book enrichment.

The `state=fallback` lens renders the 134 un-enriched rows so the degraded card can be judged on
its own: it still answers ticker, stance, priority, lifecycle, zone and date. It is quiet and
deliberate rather than broken — but it is a gap to close, not the target.

### Q2 — UNRESOLVED: the Overtime cell's gloss and its producer disagree

- `overtime` = **0**; open rows past their **own declared horizon** = **16** (PINS at day 166 of 45).
- Those rows sit in `ready` (7) and `entered` (9).

Either `phase=overtime` means something narrower than "past its declared window without
resolving" (then the ruled gloss overclaims), or the phase is not firing (then Overtime is a
de-facto producer-less cell — the stage=4 defect reborn).

**Ruled (operator 2026-08-13): this remains UNRESOLVED and blocks production.** Removing
`day X of 45` fixed the user-facing card problem; it did **not** cure the underlying contradiction.
The ladder still carries an Overtime semantic whose producer disagrees with current plan
arithmetic, and a producer defect must not be considered closed merely because the redesigned card
no longer exposes it. This needs a **Prophet / data-lane resolution before the production
migration** — either the phase begins firing, or the ruled gloss is re-worded by the lane that owns
it. It is not the designer's to reword.

### Q3 — "What changed today" has no producer

P0 §B specifies new / entered / resolved transitions. The payload carries no transition dates,
only `age_days`. Only the derivable figure is printed.

### Q4 — the per-ticker projection's sort key is mostly null

`recorded_at` is null on **83 / 179** rows, including one of the two FBRT rows the ruling cites.
`entry_date` is present on 179/179. PR-0(c) should sort on `entry_date` or pin the null path.

### Q5 — three primitives here are not shipped yet

`.mx-ladder`, `.mx-sec`, `.mx-empty` are DS-PR-0 deliverables (gate G-B).
`mockups/design_system/specimen.html`, cited normatively by the design-system masterplan,
**does not exist on disk**.

### Q6 — zh copy needing a native pass

The seven cell words are ruled and untouched. What needs a native eye is the connective copy:
the episode chip (`第 1 轮（共 2 轮）· 7月17日` — is 轮 the right measure word for a trade episode,
or 次?), 「观察档自下一次夜间构建起发布。」 (档 for "tier"; "夜间构建" is arguably build-system
vocabulary leaking to a user), 「个在场计划」 as the headline unit, 「不计入今日总数」, the two
§5 relabels, and the stance words 临近 / 回避.

### Q7 — RULED: the stance projection (operator 2026-08-13)

**The mockup's first mapping was rejected and is replaced.** It fell through to the management
engine's `recommended_action` — an engine that describes itself as trade-management-only and whose
action carries display/narrative authority, not order authority — and it defaulted an unobtainable
stance to `wait`, originating a signal the engine never stated.

The stance now comes from **Prophet's entry/actionability axis only**, and the grouping is
**factored from the shipped engine logic** rather than re-mapped template-side.
`engine/us_board_rank.py:365-368` already partitions the twelve-value domain into four buckets;
this projects those same buckets onto the five shipped verbs:

| Engine bucket (`us_board_rank.py`) | Statuses | Verb |
|---|---|---|
| `_LIVE_STATUSES` | `buy_now`, `partial` / `buy_soon` | **Buy** / **Near** |
| `_SETTING_UP_STATUSES` | `await_confluence`, `bounce_wait`, `watch` | **Wait** |
| `_RAN_STATUSES` | `extended`, `topping`, `hold` | **Hold** |
| `_BLOCKED_STATUSES` | `blocked`, `exit`, `avoid` | **Avoid** |

`wait_pullback`, `later` and `await` carry an `_ENTRY_VALUE` but sit in no bucket; `stage_for()`
routes `wait_pullback` to `setting_up` (`:393`), so they join **Wait**. There is **no sixth verb**
— TRIM does not exist on the Board.

**Drift is mechanically prevented.** `gen_fixture.py` refuses to regenerate if any engine bucket
gains an unmapped status or projects outside its expected verb set; `verify.py` M1–M4 pin the same
invariants plus "no live read of `recommended_action`". Both are mutation-tested.

### Q7b — BLOCKED_DATA is 60% of the live book, and that is the finding

A plan that cannot obtain the axis is **BLOCKED_DATA**, rendered as a disclosed no-read chip —
never a guessed Wait. Measured on the committed payload:

| | rows |
|---|---|
| stance obtainable (`entry_status` present) | **62 of 159 live** |
| **BLOCKED_DATA** | **97 of 159 live (61%)** |

The previous mapping hid this: falling through to `recommended_action` covered 174/179 rows and
made the board look complete while sourcing its primary answer from an engine that disclaims order
authority. With the ruled projection the gap is visible and measurable.

**This is the second hard implementation dependency** (with Q1). `entry_status` is native to the
plan row but published on only 61/179; the candidate join is worse (44). Production needs the
actionability axis published for the full plan book before the Board can answer "what does Prophet
think?" on more than a third of its inventory.

The no-read chip takes **no stance hue** — an unavailable read is not a cautious read — carries a
dashed border and sentence case so it never reads as a verdict, and its LENS says: *"The entry read
that produces Buy / Near / Wait / Hold / Avoid has not published for this plan. The stance is
unavailable — that is not the same as neutral, and not a hold."* The internal token `BLOCKED_DATA`
never reaches a user (`verify.py` L4).

### Q8 — CLOSED: Priority vs Edge was already ruled

I reopened a settled decision. `research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md`
**§3.8** already rules it: *"when `row.prophet.score` exists, the pv_card number slot shows
**Priority** (0–100) with the honest formula tooltip; legacy `score_edge` 'Edge' display is the
fail-soft for old artifacts."*

Priority stays in the slot, `score_edge` is retained as the fail-soft for legacy artifacts, and
**Edge does not need a second glance-tier slot** — it survives in payload, plan detail and LENS.
The Board card carries one number, not both. No change to the mockup; the question should not have
been raised.

### Q9 — CLOSED: ⚡ is sourced from the trigger producer

**Ruled and implemented.** ⚡ carries a real trigger fact, from the producer the shipped board
already reads (`dashboard.html.j2:16187-16189`):

| Chip | Source | Today |
|---|---|---|
| ⚡ **Triggered** | membership in `site/factordata/setups.json` → `buy` | **8** rows |
| ⚡ **Imminent** | that row's `signal.tier_cascade == "T3"` | **0** rows |

There is **no plan-age proxy**. The earlier pass approximated Triggered from `age_days <= 3` and
Imminent from `Ready + buy_now`; both were removed. Imminent is 0 because nothing carries `T3`
tonight — an honest zero from a real producer, not four cards inferred from a neighbouring field.

The restriction the operator approved holds by construction rather than by a rule: `Entered` is
durable lifecycle state, ⚡ is a recent transition/event, and only 8 of 179 rows have one. Putting
⚡ on all 96 entered cards would state the same fact twice and turn an event badge into wallpaper.

Coverage caveat: `setups.json` is a 12-row artifact and intersects the plan book at 8, so ⚡ is
join-limited like the other enrichments (§6 Q1). Sourced-or-absent, never approximated.

### Q10 — NEW: the change values in the crops are simulated

No committed artifact carries per-ticker intraday change (`quotes.json` holds 27 index/futures
symbols). The change slot is filled from a deterministic per-ticker demo overlay purely to show
the direction inks and their zh flip. These are **the only fabricated numbers** on the page; they
are marked `data-mock-live` in the DOM. In production the value is real and client-painted.

**Fidelity bug found and fixed while doing this:** the first mockup omitted the `--pv-*` stance
token family from its copy of `theme.css`, so all five stance colours were resolving by accident
and the Buy chip did **not** flip red under zh. `verify.py` G2–G4 now pin the family's existence
and the zh flip, so it cannot regress silently.

---

## 7. Scope

No production file is touched. No template, no `site/`, no engine path, no `data/` write, no new
`theme.css` token, no new header family. The card is the shipped `.pvcard` with its rail removed
and a lifecycle fact added; the lock is the shipped `.mx-tier-gate--prophet`.

~~Groups is the shipped `.actcol` idiom unchanged.~~ — **corrected at R4 (VTC-310 / R3 receipt
NEW-C).** This was false at the R3 SHA: `groups()` emits `.grp-grid` / `.grp`, and `.actcol` was
never rendered. The rationale asserted a dead ~35-line stylesheet block was the live component.
The dead block is deleted and this sentence corrected together, because a claim that unused code is
normative is how the unused code gets rebuilt.

MP-1 remains gated on **G-A** (PR-0(c) publishing `lifecycle_state` + `lifecycle_counts`) and
**G-B** (DS-PR-0). This artifact satisfies **G-C** only. **No production migration has begun.**

### NEW — spawn gate G-D: plan-book enrichment + actionability coverage

**The Board migration builder may not be commissioned until the plan book publishes, for the full
universe (not the candidate intersection):**

1. **the entry/actionability axis** (`entry_status`) — today 61/179, leaving **60% of live rows
   BLOCKED_DATA**. Without it the Board cannot state a stance on two-thirds of its inventory.
2. **name · sector · lane · spark** — today 45/179. The live quote is *not* part of this gate: it
   needs only `data-sym`.

~~The reference view (`state=paid`) shows the product once G-D is met; `state=today` and
`state=fallback` show what ships if it is not.~~ — **struck at R4 under DA-001.** This is the same
repealed `state=paid` exemption struck in §0b.1; see that section for what is law instead. `paid`
and `today` are one universe and render the same population.

What G-D actually governs: **what may ship to PRODUCTION**, not what a frozen reference is allowed
to show. `state=fallback` remains a committed diagnostic lens isolating the un-enriched rows for
inspection, so the coverage gap stays reviewable rather than argued — but it is a lens, never a
population the product surface may substitute for the book.

**Overtime (Q2) is a separate hard production blocker** and is not cleared by this pass.

---

## 8. Evidence

`crops/` — 42 views, 62 files, at 1440×900 and 390×844:

- `00-R3-*` the R3 matrix: dark+light x EN+ZH
- `01`–`07` the required matrix: desktop dark/light × EN/ZH, 390w dark EN/ZH, 390w light EN
- `10`–`12` **missing-enrichment fallback** (dark EN, light ZH, 390w)
- `20`–`27` each ladder filter incl. Ready, Entered, Invalidated, and the zero/absent cells
- `30`–`33` multi-episode, incl. resolved episodes with forward links, and 390w
- `40`–`42` anonymous lock (dark EN, light ZH, 390w)
- `50`–`51` empty board · `60`–`61` table view
- `70`–`73` **the three-way card adjudication** (production · #5514 v1 · revised), dark+light × EN+ZH
- `80`–`82` **R4 / PRC-305 — behind the tape** (dark EN, light ZH, 390w). Production ships this
  banner today and the R3 reference had no stale path at all, so it needs its own committed
  evidence in both languages.
- `90`–`91` **R4 / PRC-306 — the expanded grid** (dark EN, light ZH). These are *post-interaction*
  states: `capture.py` clicks `Show all` and then shoots, because a capability that only exists
  after a click cannot be evidenced by a URL. Both show **159 visible cards** — every live plan row
  reachable as a card. The capture RAISES rather than skipping if the control is missing, so a
  regression cannot quietly yield a crop of the un-expanded grid that photographs as success.

### Honest screenshot gaps — states the real payload cannot exhibit (PRC-319)

Three of the seven ruled lifecycle cells have **no card rendering anywhere in the crop set**, and
no crop can be produced for them from the committed payload. Recorded here rather than left as an
implied-but-missing capture, because an absent screenshot and an unphotographable state look
identical in a crop index:

| Cell | Rows in payload | Why no card crop exists | What IS captured |
|---|---|---|---|
| **Watch** | 0 — key **absent**, not zero | The producer has not published the tier; `watch_key_present: false`, `watch_n: null`. A card cannot be drawn for a row that does not exist. | `24-filter-watch-absent` — the em-dash + disclosure state, which is the honest rendering of key-absence |
| **Delivering** | 0 — key present, genuinely zero | No plan is at or past its first target tonight. A real zero, not a gap. | `25-filter-delivering-zero` — the empty-cell copy |
| **Overtime** | 0 — key present, genuinely zero | Compounded by the Q2 producer contradiction (`age_days` anchored to `signal_date` vs `plan_clock_date()`), a **separate open production blocker** (#5540) not cured here. | `26-filter-overtime-zero` |

So the lifecycle card treatment is photographed for **4 of 7** cells (Ready, Entered, Invalidated,
Resolved). The remaining three are evidenced by their empty/absent states only. This is a real
coverage limit of the frozen fixture, and it is **not** closed by this pass — it closes when the
producers publish, not when the reference is re-shot.

### Enrichment coverage, stated as a number (PRC-308)

The company name and sector are absent on **134 of 179 rows** — the same 134 that carry no spark;
the lane mark is absent on 146. The enrichment join therefore reaches **45/179**, exactly the
figure gate **G-D** (#5541) is written against. This is **accepted as a data dependency**, not
cured here and not a design regression: the card renders it as a printed absence rather than a
hidden row. What the R3 cycle owed and this one pays is the *layout* consequence (VTC-301), which
is a design choice and is fixed — the data gap itself is G-D's and stays open.

**Checks:** `tools/verify.py`, run against the *rendered* page, plus `tools/mutation_test.py`,
which asserts the harness can SEE the closure work missing — a different claim from asserting it
is present, and the only one that makes the harness evidence rather than decoration. It treats a
mutation whose pattern does not match as an ERROR (a silently no-op mutation makes a decorative
guard look green), reports any mutation the harness survives, and rejects two guards sharing one
observable kill. Zero horizontal page scroll at every captured width, asserted per shot.

This is a visual gate: green checks are a floor, not the acceptance. The crops are the deliverable.
