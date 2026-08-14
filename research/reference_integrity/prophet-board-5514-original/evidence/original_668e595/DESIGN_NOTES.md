# Prophet Board — mockup gate notes (MP-1 / gate G-C)

**Status:** mockup-gate artifact. Frozen visual reference for the `us_stocks.html`
migration. **No production file is touched by this directory.**
**Date:** 2026-08-13 · **Author:** design authority (mockup lane)

**Binding authority, in precedence order**
1. `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md` (PR #5504, merged) — on any conflict it wins
2. `research/migration_packets/MP-1-prophet-board.md` (PR #5505)
3. `research/P0_REFERENCE_EXPERIENCE_DESIGN_PACKET.md` §0 + §B as amended 2026-08-13
4. shipped design-system primitives (`theme.css`, `tier_preview.css`, LENS, `.actcol/.acth`)

---

## 0. How to run it

```bash
python3 -m http.server 8792 --directory mockups/refs/institutionalize/us_stocks
```

| Parameter | Values |
|---|---|
| `theme` | `dark` (default) · `light` |
| `lang` | `en` (default) · `zh` |
| `state` | `paid` (default) · `anon` · `empty` · `episodes` |
| `life` | `watch` `ready` `entered` `delivering` `overtime` `invalidated` `resolved` |
| `view` | `grid` (default) · `table` |
| `chrome` | `1` (default, shows the harness bar) · `0` (clean, used for crops) |

```bash
python3 tools/gen_fixture.py board-data.js      # regenerate data from origin/main
python3 tools/capture.py  http://localhost:8792 crops
python3 tools/verify.py   http://localhost:8792 # 60/60 acceptance checks
```

**The data is real.** `board-data.js` is a committed extract of
`site/prophet/index.json` (asof 2026-08-12, 179 plan rows) and
`site/factordata/us_standouts.json` (as_of 2026-08-10, 69 buy rows) off
`origin/main`. `lifecycle_state` is derived by the ruling §6 precedence, verbatim.
Every number on the page reconciles to that payload:

```
62 ready + 96 entered + 0 delivering + 0 overtime + 4 invalidated  = 162 = open_count
162 live + 17 resolved                                            = 179 = active_count
grid: 40 cards + "+122 more"                                      = 162 = headline
```

`tools/verify.py` asserts this against the **rendered** page, not the source, and is
mutation-tested (deliberately reintroducing "stage"/阶段 vocabulary and a cell word
inside Candidates makes it fail in both languages).

---

## 1. Why the page structure works

The live page put its flagship sixth. Six sections now, in the order a user actually
works: **what am I tracking → what stands out tonight → where is money rotating →
what's the weather → does this machine work.**

The Board answers one question — *"which setups matter most right now, where in
their lifecycle, and which am I allowed to act on today?"* — and the first screen
answers all three clauses: the headline says how many, the ladder says where they
stand, and the grid says which ones.

**The count ladder is the page's one signature** (P0 §0), spent deliberately: it is
simultaneously the headline statistic and the filter control. That fusion is a real
risk, and it is justified by exactly one property — it forces every setup quantity on
the page to be a value from `lifecycle_counts` or a difference of them. A number that
can be filtered against is a number that can be caught lying.

**The three count-bearing devices stay apart by form, not by discipline** (§G.2 — the
packet's most fragile decision). They never look alike:

| Population | Noun | Form | Total |
|---|---|---|---|
| Setups | Setups / 在场计划 | counted cells carrying weight caps | `162 live setups today` |
| Candidates | Candidates / 候选 | pill shelves, no marks, no caps | `69 screened tonight` |
| Groups | Groups / 板块 | icon-headed stance columns, hue-accented | `22 sectors & themes moving` |

They are non-adjacent (sections 2, 3, 4), use disjoint nouns in both languages, and no
Setups integer ever renders beside a Candidates integer.

---

## 2. How the ladder grammar maps to the ruling

### 2.1 The weight grammar (ruling §10.6, P0 §0 re-issued)

| Cell | EN / ZH | Weight | What the weight says |
|---|---|---|---|
| `watch` | Watch / 观察 | dashed hairline | a signal fired, nothing is committed |
| `ready` | Ready / 就绪 | half filled | the plan is armed, the trigger has not fired |
| `entered` | Entered / 入场 | solid | a live commitment |
| `delivering` | Delivering / 达标 | solid | a live commitment |
| `overtime` | Overtime / 超时 | solid muted | the declared window expired, still open |
| `invalidated` | Invalidated / 失效 | hollow, struck | the plan's own void level was hit |
| `resolved` | Resolved / 已结 | neutral outline | graded out — archive weight |

Entered and Delivering are **deliberately identical**. The grammar encodes *commitment
class*, not per-cell identity; §0 says so outright, and the partition law guarantees the
label and count tell them apart. Making them differ would have been the easy wrong move.

**Direction-neutrality is structural, not observed.** No lifecycle mark references
`--up`/`--down`/`--q*`; every weight is `currentColor` or `--muted`. The encoding is
therefore byte-identical under the zh flip. `verify.py` G1 asserts this by resolving
computed styles against the live token values in both languages — it does not take the
CSS's word for it.

### 2.2 Identity and selection cannot collide

The ruling warns that selection state (solid fill + heavier rule) and cell identity
(also rules) must never collide — *"no cell identity may use the heavier rule."*
Keeping both as "rules" and hoping they read differently would be fragile.

They are put on **different geometric channels** instead:

```
┌═══════════════┐  ← IDENTITY: the weight cap. Top edge, full bleed, 3px.
│  62           │
│  Ready        │
└───────────────┘  ← SELECTION: background fill + bottom rule, only when pressed.
```

Top edge vs bottom edge; always present vs only when pressed; weight vs fill. A selected
Watch cell still reads dashed; an unselected Entered cell still reads solid. There is no
state in which the two can be confused.

### 2.3 The ladder and the grid are one population

Acceptance 2 asks that the ladder and the visible Setups feel like the same thing.
The mechanism is literal: **the card's top edge carries the same `.mx-cap`, in the same
geometry, as the ladder cell's.** One CSS definition serves both. Filtering to
*Invalidated* shows four cards whose caps are the same hollow-struck rule as the cell
you pressed. That is why the card does **not** get a verb hue bar — a saturated colour
at the card's head, on a card whose primary classification is hue-free by law, would
invite exactly the "lifecycle by colour" misread the ruling forbids.

### 2.4 Resolved is outside the live count, three times over

1. It sits outside the live enclosure, past a divider, on a dashed outline.
2. It is labelled *"not in today's count"* / 「不计入今日总数」.
3. **It is not in the default grid.** Filtering is how you reach it. This is the one
   that actually bites: leaving resolved rows in the unfiltered grid made the section
   total (162 live) disagree with the grid population (179) and broke the `+N`
   difference. Caught at this gate — see §6.

The empty state proves the law visibly: headline `0`, six live cells `0`, **Resolved
still 17**. A quiet day empties the inventory, not the record.

### 2.5 Key-absence is not zero

`early_turn_watch` is genuinely absent from the committed payload's `intake` block —
the ruling's §6 fn.1 condition is today's live state, not a hypothetical. The Watch
cell therefore renders an **em dash**, never `0`, plus a disclosed-absence line:
*"Watch tier publishes from the next nightly."* Filtering to Watch gives its own copy
("This tier has a producer, but tonight's build did not publish it yet"), distinct from
a producing cell that is merely empty today.

---

## 3. Duplicate ticker episodes

The board renders **one card per plan `id`**. 12 tickers carry more than one row today;
FBRT is the ruling's own exemplar and is live in the data: `FBRT-BULL-20260713`, opened
07-17 and since closed (`resolved`), and `FBRT-BULL-20260805`, opened 08-10 and live
(`entered`). ARES and PI are the same shape — PI carries three episodes.

- **Cards stand alone.** Same-ticker cards are never stacked, merged, or carouselled —
  they sort by priority like everything else, so FBRT's two episodes land far apart.
  That is the honest rendering: they are two separate commitments, not one name with a
  history.
- **Every card of a multi-row name carries a dated episode chip**, neutral ink, dashed
  border, no hue: `Episode 1 of 2 · opened Jul 17`. I chose **"N of M"** over the
  packet's draft "Episode 2" because the disambiguation has to work on a card seen
  *alone* — "Episode 2" raises the question, "2 of 2" answers it. Dated, as the packet
  binds.
- **The chip is counted in nothing.** It appears in no total.
- **A resolved episode links forward** — "Newer plan on this name →" — but only when a
  live row actually exists. HLI and QCOM have two resolved episodes each and correctly
  show no link.
- Resolved cards carry archive weight: dashed border, recessed panel, muted ticker.

Ticker-keyed surfaces elsewhere (landing showcase, dossier chip) use the ruling's
per-ticker projection instead; the board is the only surface showing row-granular truth.

---

## 4. How Candidates stays a second population

The section leads with the distinction in plain words:

> Names tonight's screen surfaced. **A candidate is not a setup:** it becomes one only
> when a plan is written for it, which is what the board above counts.

One printed total (69), decomposed by the **shipped** triage shelves —
28 + 27 + 10 + 2 + 2 = 69. Different form (pills), no weight caps, no ladder geometry.

### 4.1 Two shipped strings had to be relabelled (one-referent-per-page law)

The ruling delegates this to the designer within a hard constraint: a lifecycle cell word
may carry only one meaning per page. Auditing the shipped triage copy
(`dashboard.html.j2:15907-15911`) found **two live collisions** that the ruling's own
census did not name:

| Shelf | Shipped sub-line | Collides with | Now reads |
|---|---|---|---|
| `live` | 入场窗口已打开 | **入场** = the Entered cell | 买入窗口已打开 / "buy window is open" |
| `basing` | 尚无入场信号 — 观察，勿追高 | **入场** and **观察** = Entered, Watch | 尚无买入信号 — 勿追高 / "no buy signal yet — don't chase" |

"Buy" is also the more honest word: these are buy rows. EN `setting_up`'s
"not there yet — get ready" became "— prepare" to keep clear of the *Ready* cell.
Shelf **headings** are untouched — none of them collided.

`verify.py` F1 sweeps the rendered Candidates section for all seven cell words in both
languages and is mutation-tested against a planted violation.

---

## 5. Lane, stage, and the old rail

- **Lane is a mark, not a device.** One static chip per card at most, neutral ink, no
  fill states, no ordering, no sequence: "Bottoming entry / 底部入场" ·
  "Continuation entry / 顺势入场". **No recovery chip** — its producer is structurally
  empty, and a producer-less chip is the exact defect the rail died of. Its LENS tip
  says what it is: *"a mark of which construction found it, not a stage it advances
  through."*
- **The four-dot rail is absent.** No `.pv-stp`, no `.pv-dot`, no ordered lane sequence
  anywhere. Nothing on the page reads as progress except the lifecycle itself.
- **"Stage / 阶段" appears nowhere user-facing**, in either language — no labels, no
  column, no chips, no fragment. The URL vocabulary is `#life=<cell>`; `#stage=` occurs
  nowhere in markup or JS. The stocktable's Stage column is simply not rendered.

---

## 6. Open questions and doctrine tensions

These are the gate's findings. Each one is a decision for the Prophet program lane or
PR-0(c), **not** something a builder should improvise around.

### Q1 — BLOCKING for the card spec: five card fields die with the re-sourcing

Re-sourcing Setups from candidates to the plan book is the migration's structural act
(ruling §10.4). Measured consequence on the committed payload:

| Card field | Source | Coverage on plan rows |
|---|---|---|
| company name, sector, last price | `us_standouts.json` buy rows | **45 / 179 (25%)** |
| `lane` (the `.pv-mark` chip) | `us_standouts.json` buy rows | **44 / 179 (25%)** |
| `spark_svg` (the chart hero) | `us_standouts.json` buy rows | **45 / 179 (25%)** |

All five are candidate-join fields. 166 plan tickers vs 69 buy rows, intersection 44.
MP-1 §12.5 specifies `.pv-mark` "from `lane` ∈ {bottoming, continuation} only" without
saying what happens to the other 75% — because the packet was written before anyone
rendered it.

**What the mockup does:** builds the card spine from fields the plan book carries on
*every* row (ticker · lifecycle · why · window position · entry/T1/void) and treats
name/sector/lane as enrichments that never carry structure — a card without them is the
same shape as a card with them. The chart hero is dropped entirely rather than shown on
a quarter of cards; P0 §B's card depth ladder ("ticker + lifecycle + why + freshness")
does not include it.

**Decision needed:** either PR-0(c) passes `lane` (and optionally name/sector/spark)
through onto plan rows, or the lane chip is accepted as join-conditional and the packet
says so. The mockup assumes the latter.

### Q2 — BLOCKING for the Overtime cell: its gloss and its producer disagree

Ruling §6 fn.2 argues Overtime is honest inventory at zero because it has a real
producer. On the committed payload:

- `overtime` = **0**
- open plan rows past their **own declared horizon** (`age_days > horizon_days`) = **16**
- worst: PINS at day **166 of 45**; GPK 127/45; RH 117/45

Those 16 rows sit in `ready` (7) and `entered` (9). So a card can read *"past its 45-day
window"* while the ladder cell defined as *"past its declared window without resolving"*
reads 0 — a live contradiction on one page.

Either `phase=overtime` means something narrower than the cell's plain-word gloss (then
the gloss overclaims and must be re-worded by the ruling lane), or the phase is not
firing (then Overtime is a de-facto producer-less cell — the stage=4 defect, reborn).

**What the mockup does:** states the plan's own arithmetic ("past its 45-day window")
and never claims the cell. It does not hide the discrepancy; the ruled gloss is
unchanged, because relabelling a ruled cell is not the designer's call.

### Q3 — "What changed today" has no producer

P0 §B specifies a strip of *new / entered / resolved* transitions. The payload carries
no transition or phase-change dates — only `age_days`, from which "opened in the last
day" is derivable. The other two are not.

The mockup prints **only the derivable figure**. Shipping the full strip needs a
`lifecycle_transitions` producer that PR-0(c) does not currently specify. A three-part
strip where two parts have no source is the defect this whole ruling exists to prevent.

### Q4 — the per-ticker projection's sort key is null on most rows

Ruling §6 defines the ticker projection as "the newest open plan row by `recorded_at`,
tie-break `id`". `recorded_at` is **null on 83 of 179 rows (46%)**, and null on one of
the two FBRT rows the ruling cites as its exemplar — so the tie-break, not the sort key,
decides a large share of cases. It happens to work, because `id` embeds a date
(`FBRT-BULL-20260805`), but that is an accident of the id format rather than a designed
ordering. `entry_date` is present on **179 of 179**. PR-0(c) should either sort on
`entry_date` or pin the null-`recorded_at` path explicitly in its §9.6e test. The mockup
sorts on `entry_date` with an `id` tie-break.

### Q5 — three primitives in this mockup are not shipped yet

`.mx-ladder`, `.mx-sec`, `.mx-empty`/`.mx-empty-why` exist only in the design-system
research docs; they are **DS-PR-0 deliverables** (gate G-B). `mockups/design_system/
specimen.html`, cited normatively by the design-system masterplan, **does not exist on
disk** — worth knowing before another packet cites it as the component registry.
Everything else here is lifted verbatim from shipped CSS: `theme.css` tokens (including
that dark is the bare `:root` plane, not `html[data-theme="dark"]`), `.mx-tier-gate--prophet`,
`.mx-tier-blurred` with the light-mode ghost, `.actcol/.acth`, `.dtp-*`, `.pbs`,
`.st-view-toggle`, the LENS popover, and the `.l-en`/`.l-zh` bilingual switch.

### Q6 — zh copy needing a native pass

The seven **cell words** are ruled and native-verified (ruling §6) and are untouched.
What needs a native speaker's eye is my new connective copy:

| String | Note |
|---|---|
| 「第 1 轮（共 2 轮）· 7月17日启动」 | episode chip — is 轮 the right measure word for a trade episode? 次 is the alternative |
| 「观察档自下一次夜间构建起发布。」 | 档 for "tier"; "夜间构建" is arguably build-system vocabulary leaking to a user |
| 「个在场计划」 | headline unit — 在场 for "live/open" is my choice; 持仓中 is warmer but implies a filled position, which `ready` rows are not |
| 「已超出 45 天窗口期」 | past-window phrasing |
| 「不计入今日总数」 | terminal-cell note |
| 「买入窗口已打开」·「尚无买入信号 — 勿追高」 | my two §4.1 relabels |
| the seven gloss lines | e.g. 「计划就位，尚未触发」 |

Per the zh copy law these must read as native Chinese, not English-shaped Chinese.
Flagging rather than asserting: I can check idiom, not register.

---

## 7. Scope — what this deliberately is not

No production file is touched. No template, no `site/`, no engine path, no `data/`
write, no token added to `theme.css`, no new header family, no new card system. The
`.pvcard` is the shipped card with its rail removed and a fact column added; the lock is
the shipped `.mx-tier-gate--prophet`; Groups is the shipped `.actcol` idiom unchanged.

The migration itself (MP-1) stays gated on **G-A** (PR-0(c) merged and publishing
`lifecycle_state` + `lifecycle_counts`) and **G-B** (DS-PR-0). This artifact satisfies
**G-C** only.

---

## 8. Evidence

`crops/` — 26 views, 34 files, captured at 1440×900 and 390×844:

- `01`–`07` the required matrix: desktop dark/light × EN/ZH, 390w dark EN/ZH, 390w light EN
- `10`–`11` anonymous lock (dark EN, light ZH)
- `12`–`13` filtered (Invalidated: 4 cells, 4 cards, exact agreement)
- `14`–`15` empty board — headline 0, Resolved still 17
- `16`–`19` multi-episode, incl. resolved episodes with forward links, and 390w
- `20`–`26` each of the seven ladder filters active
- `30`–`31` table view — rendered rows equal the cell count with no remainder

`--full.png` variants are full-page for the eight views where whole-page rhythm is the
thing being judged.

**Checks:** `tools/verify.py` — 60/60 passing, mutation-tested. Zero horizontal page
scroll at every captured width, asserted per shot at capture time.
