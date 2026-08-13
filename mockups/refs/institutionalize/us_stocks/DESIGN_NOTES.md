# Prophet Board — mockup gate notes (MP-1 / gate G-C)

**Status:** mockup-gate artifact, **G-C correction pass 2026-08-13** (third revision) after the
operator's visual/product audit. Composition approved; five narrow corrections applied.
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
| `state` | `paid` = **canonical reference** (default) · `today` = actual payload · `anon` · `empty` · `episodes` · `fallback` |
| `life` | `watch` `ready` `entered` `delivering` `overtime` `invalidated` `resolved` |
| `view` | `grid` (default) · `table` |
| `chrome` | `1` (default, harness bar) · `0` (clean, used for crops) |

`compare.html` is the three-way card adjudication (production · #5514 v1 · revised).

```bash
python3 tools/gen_fixture.py board-data.js      # regenerate data from origin/main
python3 tools/capture.py  http://localhost:8792 crops
python3 tools/verify.py   http://localhost:8792 # 116/116 acceptance checks
```

**The data is real.** `board-data.js` is a committed extract of `site/prophet/index.json`
(asof 2026-08-12, 179 plan rows) and `site/factordata/us_standouts.json` (as_of 2026-08-10).
`lifecycle_state` is derived by the ruling §6 precedence, verbatim. Counts reconcile:

```
62 ready + 96 entered + 0 delivering + 0 overtime + 4 invalidated = 162 = open_count
162 live + 17 resolved                                           = 179 = active_count
grid: 40 cards + "+122 more"                                     = 162 = headline
```

---

## 0b. The G-C correction pass (operator audit, 2026-08-13)

The composition passed Product/Taste review — ladder, density, card anatomy, Priority placement,
lifecycle treatment, Zone footer and chroma level are settled and are **not** revisited. Five
narrow corrections were applied; no structural redesign.

**1. The canonical reference now shows the intended experience.** `state=paid` is the reference
view and renders only the **33 plan rows whose enrichment contract is met today** — zero no-read
cards. `state=today` is the honesty state showing the actual payload including the 60% awaiting
their entry read, and is the state the count law is verified against. A 60%-`暂无判断` board must
not become the flagship reference. **New spawn gate G-D** (§7) makes coverage a hard production
dependency.

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
- **Zone footer** — `ZONE $70.66–$72.35` with the date pinned right.

### Preserved from #5514
- The whole Board architecture: Setups = the plan book, Candidates as a separate population,
  the seven-cell ladder, lifecycle filtering, `#life=` fragments, honest count reconciliation,
  empty / anonymous / filtered states, Groups / Market context / Evidence organisation.
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
│ HOLD  ⚡Triggered        $74.13  +0.7%  │  stance · trigger · live quote + change
│         compact price chart            │  74px, with its own zone band
├────────────────────────────────────────┤
│ FTI  TechnipFMC          PRIORITY  89  │
│ Energy                                 │
│ ★ Featured  New  Bottoming entry       │  restrained marks, max 3
│ ━━ Entered                             │  ruled lifecycle mark + word, no gloss
├────────────────────────────────────────┤
│ ZONE $70.66–$72.35             Aug 10  │
└────────────────────────────────────────┘
```

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

One printed total (69), decomposed by the **shipped** triage shelves — 28 + 27 + 10 + 2 + 2 = 69.
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
| company name, sector, `lane`, `spark_svg` | **45 / 179 (25%)** |
| SSR price text | 45 / 179 |

**Proposed solution, in two parts:**

1. **The live quote needs no payload work at all.** `live.js` paints `.nb-px[data-sym]` /
   `.nb-chg[data-sym]` client-side every ~60s; the SSR price is only a fallback. Emitting
   `data-sym` + `data-mkt` on every plan card — an attribute, not a field — gives 100% of rows a
   live quote and change. The mockup already emits it.
2. **name / sector / lane / spark need a payload path.** All four already exist tonight inside
   the builders that produce `us_standouts.json`; the gap is only that the join is taken against
   the 69 buy rows instead of the full plan universe (166 tickers). The ask is a per-plan
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
| stance obtainable (`entry_status` present) | **64 of 162 live** |
| **BLOCKED_DATA** | **98 of 162 live (60%)** |

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

### Q9 — APPROVED: ⚡ stays restricted

**Ruled (operator 2026-08-13): the restricted treatment is approved.** `Entered` is durable
lifecycle state; ⚡ means a *recent transition or event*. Putting it on all 96 entered cards would
display the same fact twice and turn a valuable event badge into wallpaper.

⚡ therefore fires only on a recent trigger (≤3 days) or an imminent one — **10 of 179 rows**.

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
and a lifecycle fact added; the lock is the shipped `.mx-tier-gate--prophet`; Groups is the
shipped `.actcol` idiom unchanged.

MP-1 remains gated on **G-A** (PR-0(c) publishing `lifecycle_state` + `lifecycle_counts`) and
**G-B** (DS-PR-0). This artifact satisfies **G-C** only. **No production migration has begun.**

### NEW — spawn gate G-D: plan-book enrichment + actionability coverage

**The Board migration builder may not be commissioned until the plan book publishes, for the full
universe (not the candidate intersection):**

1. **the entry/actionability axis** (`entry_status`) — today 61/179, leaving **60% of live rows
   BLOCKED_DATA**. Without it the Board cannot state a stance on two-thirds of its inventory.
2. **name · sector · lane · spark** — today 45/179. The live quote is *not* part of this gate: it
   needs only `data-sym`.

The reference view (`state=paid`) shows the product once G-D is met; `state=today` and
`state=fallback` show what ships if it is not. Both are committed so the difference is reviewable
rather than argued.

**Overtime (Q2) is a separate hard production blocker** and is not cleared by this pass.

---

## 8. Evidence

`crops/` — 37 views, 54 files, at 1440×900 and 390×844:

- `00-FREEZE-*` the two freeze crops (dark EN + light ZH) — the canonical reference
- `08`–`09` the honesty state (`today`) — the actual payload, no-reads included
- `01`–`07` the required matrix: desktop dark/light × EN/ZH, 390w dark EN/ZH, 390w light EN
- `10`–`12` **missing-enrichment fallback** (dark EN, light ZH, 390w)
- `20`–`27` each ladder filter incl. Ready, Entered, Invalidated, and the zero/absent cells
- `30`–`33` multi-episode, incl. resolved episodes with forward links, and 390w
- `40`–`42` anonymous lock (dark EN, light ZH, 390w)
- `50`–`51` empty board · `60`–`61` table view
- `70`–`73` **the three-way card adjudication** (production · #5514 v1 · revised), dark+light × EN+ZH

**Checks:** `tools/verify.py` — **116/116 passing**, run against the *rendered* page and
mutation-tested (planting "stage"/阶段 and a lifecycle cell word inside Candidates makes it fail
in both languages). Zero horizontal page scroll at every captured width, asserted per shot.

This is a visual gate: green checks are a floor, not the acceptance. The crops are the deliverable.
