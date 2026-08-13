# Prophet Board — mockup gate notes (MP-1 / gate G-C)

**Status:** mockup-gate artifact, **revised 2026-08-13** after the operator's card ruling.
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
| `state` | `paid` (default) · `anon` · `empty` · `episodes` · `fallback` |
| `life` | `watch` `ready` `entered` `delivering` `overtime` `invalidated` `resolved` |
| `view` | `grid` (default) · `table` |
| `chrome` | `1` (default, harness bar) · `0` (clean, used for crops) |

`compare.html` is the three-way card adjudication (production · #5514 v1 · revised).

```bash
python3 tools/gen_fixture.py board-data.js      # regenerate data from origin/main
python3 tools/capture.py  http://localhost:8792 crops
python3 tools/verify.py   http://localhost:8792 # 80/80 acceptance checks
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
- **Priority** — the numeric readiness rank, restored per the Chairman override. Quiet by
  design: visible for scanning, never louder than ticker, stance or price, and **never hued**,
  because it is not a win probability.

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

### Q1 — the enrichment gap (BLOCKING implementation dependency, no longer a design constraint)

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

The `state=fallback` lens renders the 134 un-enriched rows so the degraded card can be judged on
its own: it still answers ticker, stance, priority, lifecycle, zone and date. It is quiet and
deliberate rather than broken — but it is a gap to close, not the target.

### Q2 — the Overtime cell's gloss and its producer disagree

- `overtime` = **0**; open rows past their **own declared horizon** = **16** (PINS at day 166 of 45).
- Those rows sit in `ready` (7) and `entered` (9).

Either `phase=overtime` means something narrower than "past its declared window without
resolving" (then the ruled gloss overclaims), or the phase is not firing (then Overtime is a
de-facto producer-less cell — the stage=4 defect reborn). Note the revision **removed** the card
copy that exposed this, so the contradiction is no longer visible to a user — but it is still
there in the data, and the ladder cell still carries the gloss.

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

### Q7 — NEW: there is no stance producer for plan rows

The shipped card receives `verb` from its **caller**; for candidates that is
`dossier.action.verb`. Plan rows have no such field. The mockup projects a stance from
`entry_status` → `entry_zone.stance` → `recommended_action`, first-match-wins, never escalating
above what a field states (unknown → `wait`, the cautious lane). It originates nothing, but **it
is a proposal, not a ruling** — the Prophet lane owns whether that mapping is the right one, and
whether `TRIM ONLY` needs a sixth word.

### Q8 — NEW: Priority displaced Edge, and Edge now has no home

The shipped card's top-right slot is **Edge** (`score_edge`). The handoff restores **Priority**
(`_priority_score`) into that geometry. They are different statistics. Priority is the right call
for a board sorted by readiness — but Edge is now absent from the card entirely, and nobody has
ruled that it should be. Flagging rather than deciding.

### Q9 — NEW: ⚡ Triggered and "Entered" state nearly the same fact

The operator's target anatomy shows both on one card. To avoid a one-referent collision and chip
spam across 96 entered rows, ⚡ is restricted to a **recent** trigger (≤3 days) or an imminent
one — 10 of 179 rows. If the operator wants ⚡ on every entered card, that is a one-line change,
but the redundancy is worth a decision.

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
**G-B** (DS-PR-0), plus the enrichment dependency in Q1. This artifact satisfies **G-C** only.
**No production migration has begun.**

---

## 8. Evidence

`crops/` — 33 views, 47 files, at 1440×900 and 390×844:

- `01`–`07` the required matrix: desktop dark/light × EN/ZH, 390w dark EN/ZH, 390w light EN
- `10`–`12` **missing-enrichment fallback** (dark EN, light ZH, 390w)
- `20`–`27` each ladder filter incl. Ready, Entered, Invalidated, and the zero/absent cells
- `30`–`33` multi-episode, incl. resolved episodes with forward links, and 390w
- `40`–`42` anonymous lock (dark EN, light ZH, 390w)
- `50`–`51` empty board · `60`–`61` table view
- `70`–`73` **the three-way card adjudication** (production · #5514 v1 · revised), dark+light × EN+ZH

**Checks:** `tools/verify.py` — **80/80 passing**, run against the *rendered* page and
mutation-tested (planting "stage"/阶段 and a lifecycle cell word inside Candidates makes it fail
in both languages). Zero horizontal page scroll at every captured width, asserted per shot.

This is a visual gate: green checks are a floor, not the acceptance. The crops are the deliverable.
