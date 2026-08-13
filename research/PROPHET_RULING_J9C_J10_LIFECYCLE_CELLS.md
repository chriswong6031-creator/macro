# Prophet program ruling — §J.9(c) + §J.10: lifecycle semantics, the cell set, and surface ownership

**Ruling authority:** the Prophet program lane (owner of `scripts/build_prophet.py`,
`engine/prophet_bridge.py`, `engine/prophet_management.py`, and the live card).
**Date:** 2026-08-13 (UTC). **Answers:** PR #5500
(`research/PROPHET_DECISION_PACKET_J9C_J10_STAGE_SEMANTICS.md`) and Sol's §J.9 clause-3
deferral. **Unblocks:** PR-0(c) and the Prophet Board migration (factory docket item 6).
**Verified against:** the live committed payload on `origin/main` as of 2026-08-13 02:45Z
(`site/prophet/index.json` asof 2026-08-10, `site/factordata/us_standouts.json` as_of
2026-08-10, `site/prophet/showcase.json`, `data/us_board_ledger/snapshots.jsonl`
2026-06-30→2026-08-07) and at source on the same head.

---

## §0 The ruling, in six sentences

1. **(i) — ratified:** Bottoming/Turning/Ready/Trend is a **price/entry read** (`lane`),
   not a lifecycle; the two are separate dimensions by construction (packet §1 confirmed
   at source).
2. **(ii) — the lane dimension survives; its rail rendering retires.** `lane` stays
   untouched in the engine, the ledgers, and ranking; the 4-dot progress tracker built on
   it is retired at migration because it renders a progression the engine does not
   compute and **two of its four steps are structurally unreachable** (§1.1 — now
   verified, no longer a lead).
3. **(ii) — the lifecycle survives as a DERIVED projection, not a minted enum.** No new
   engine judgment is created: `lifecycle_state` is a total display-tier function over
   fields already computed and published (`phase`, `closed`, the union watch receipt).
   The six-state enum as literally specified (Early/Confirming/Confirmed/Aging/Extended/
   Invalidated) is **refused**: two of its cells have no producer (§2.4) and it fuses two
   different live axes (§3).
4. **The cell set (the §J.9(c) deliverable) is §6:** Watch 观察 · Ready 就绪 · Entered 入场 ·
   Delivering 达标 · Overtime 超时 · Invalidated 失效 · Resolved 已结 — exhaustive and
   disjoint at a declared unit of account (cells count **plan rows**; `watch` counts
   tickers with no open plan), every cell with a named producer (the watch cell's
   exporter pass-through is a PR-0(c) item — §6 fn.1), the live cells summing to the
   headline total by construction.
5. **(iii) — surfaces:** the count ladder and the card/detail lifecycle vocabulary belong
   to `lifecycle_state`; the price read demotes to a mark chip + LENS receipt; the
   candidate screener keeps its triage buckets under a different noun; `phase` stays the
   engine truth and never renders as slugs; the word **"stage" retires from all
   user-facing Prophet vocabulary** (§7, Sol's naming law).
6. **No lane recut → no ledger migration.** `lifecycle_state` is additive
   (optional-fields path); fossils are never rewritten; the only ledger touch is a
   stale-comment heal (§8).

---

## §1 Packet verification (PR #5500) — what I confirmed, what I amend

The packet was prepared by the design lane, explicitly unreviewed by this lane (its §8).
Every load-bearing claim was re-verified at source and against the live payload:

| Packet claim | Verdict | Receipt |
|---|---|---|
| `stage` int = lane lookup, conviction never feeds it | **CONFIRMED** | `build_prophet.py:237,312`; `score_edge` fills the Edge slot at `:364,382` |
| §4 lead: `stage=4` unreachable | **CONFIRMED — upgraded from lead to fact, and extended: `stage=2` is unreachable too** | §1.1 below: source + live payload + full ledger history |
| four stage-like taxonomies | **AMENDED: there are seven**, and four of them ship under the literal field name `stage` | §2 census |
| `stage_key` vocabulary is `live·setting_up·ran·blocked` | **AMENDED: five values** — `basing` was added by the D18 bottom-watch shelf (`engine/us_board_rank.py:725-780`) | `stage_for()` docstring; labels at `dashboard.html.j2:15907-15911` |
| lane recut = data migration | **CONFIRMED**, and this ruling avoids it entirely | §8 |
| `grade_us_board.py:756` comment stale | **CONFIRMED** — comment says `'trend' \| 'recovery' \| None`; live domain is `bottoming/continuation/watch(/leader/recovery)` | §8 heal rides PR-0(c) |

### §1.1 The stage=4 verdict (packet §4, closed)

Three independent proofs, strongest first:

- **Source:** v2 `_lane_for()` (`build_stock_library.py:1407-1441`) returns only
  `bottoming`/`continuation`. The trend rows are tagged with **no lane override**
  (`:4815-4818` — deliberately, per its own comment, "so the continuation branch
  fires"). **No code path assigns `lane="trend"`.** And `lane="recovery"` (`:4811`)
  iterates `_recovery_cands`, which is **hardcoded structurally empty** —
  `build_stock_library.py:4528-4535` says it outright: "The W8-C scan is structurally
  empty: recovery candidates live on the trend lane already. Retain the variable names
  so all downstream references … compile." No append exists in scope; the only
  reassignment is a filter that cannot add. **`stage=2` is as unreachable as `stage=4`.**
- **Live payload:** `us_standouts.json` (as_of 2026-08-10), 69 buy rows:
  `bottoming` 45 · `continuation` 23 · `watch` 1. Zero `trend`, zero `recovery`.
- **History:** the entire v1 board ledger (`snapshots.jsonl`, 18 snapshot dates,
  2026-06-30→2026-08-07, 828 buy-row observations): `bottoming` 351 · `continuation` 325 ·
  `watch` 55 · `None` 97 (the three pre-P2.4 dates). **Zero `trend` and zero `recovery`
  rows have ever been written.**

So on the shipped US board: dot 4 ("Trend / 趋势") and dot 2 ("Turning / 转向")
**cannot light** (US scope — `china.html.j2:3551` hardcodes `'stage': 4` onto a CN
shelf, §10.2), and `watch`/`leader` rows fall through to `stage=0`, rendering an
all-grey rail with **no label lit** (live example: UEC today; 2 of 12 cards on the
anonymous landing showcase; 55 historical ledger rows). US users have been shown a
four-step journey where half the steps are impossible and some cards are on no step
at all.

### §1.2 The deeper defect the packet circled but did not name

`lane` is not a progression. It is an **entry-door classification** — which construction
admitted the name (bottoming-reversal vs continuation-pullback vs recovery). A name does
not move bottoming → turning → ready → trend; it is admitted through one door and stays
(nightly recomputation can flip a label, but nothing tracks or promises advancement).
Rendering a categorical origin as a 4-step progress tracker asserts a journey the engine
never computes. That — not the unreachable dot — is why the rail retires rather than
gets relabeled: **any relabel would still be a progress bar over a category.**

---

## §2 The full census — seven stage-like vocabularies, four shipping under the name `stage`

| # | Field (machine) | Values | Semantic axis | Producer | Shipped where |
|---|---|---|---|---|---|
| 1 | `stage` (int, card) | 0–4 via `_STAGE_BY_LANE` | price/entry lane, re-rendered as progress | `build_prophet.py:237,312` **and an inline duplicate of the map** at `dashboard.html.j2:16016` | 4-dot rail + labels on every `pv_card` (`_prophet_card.html.j2:418-419`); landing showcase |
| 2 | `stage` (str, board row) | `live·setting_up·ran·basing·blocked` | **triage/actionability** of tonight's candidates (entry status + cycle gate) | `us_board_rank.py:1092` (`stage_for`, `:724`) | board grouping + `data-stage` filter rail, shipped EN/ZH (`dashboard.html.j2:15907-15911`, `hk.html.j2:378-395`) |
| 3 | `phase` (plan) | `pre_trigger·triggered_pre_t1·at_t1·between_t1_t2·at_t2·overtime·invalidated` (internal superset adds `post_t1_failed_hold`, `post_t2`) | **plan-management lifecycle** post-origination | `engine/prophet_management.py:41-62`; humanised `:1074-1111`; published `build_prophet.py:1298,1932` | every plan in `site/prophet/index.json` (140/140 rows carry it); `pulse` strings |
| 4 | `early_turn.stage` | `EARLY` (only) | **admission-lane fact column** (operator-ratified 2026-08-11: which lane a row reads from) | `us_early_turn.py:959,1213`; ridden onto rows at `prophet_bridge.py:4386` | deck-admitted rows; Terminal deck |
| 5 | `stage` (str, stocktable) | `ENTRY·RIPENING·RAN_LATE·KNIFE` | a **fourth** lane re-map, with its own user-facing label **"Stage / 阶段"**, filter, and rendered count chips | `dashboard.html.j2:15785` (a second inline lane map) → `templates/stocktable.js:137,331,784,1145-1157` | the US stock table (`#us-stocktable-data`); its `RIPENING` chip keys on `recovery`, so it can never fire (§1.1) — a dead chip already shipping |
| 6 | `stage_detailed` (Weinstein) | classic 1–4 | Weinstein stage | `engine/weinstein_stage.py` | never rendered |
| 7 | `stage_tilt` (plan) | tilt claim | separate program | plans payload | `DNR:HOLD-PSQ-TILT-CLOCK` stands; out of scope here |

Also found in passing (documented, no action ordered here): (a) `retro_grades.parquet`
has a column named `lane` whose domain is `buy/watch/laggards/leaders` — **board-list
membership**, not the row's entry lane; (b) the current v2 ledger
(`snapshots_v2.jsonl`) keys a `lanes` block on `entry_open`/`setting_up` — a third
vocabulary under `lane`; (c) the key `early_turn_watch` is itself overloaded —
`engine/basket_score.py:372,426` publishes one of shape `list[dict]` (consumed by
`basket_detail.html.j2:1132`) while the bridge's intake receipt is `list[str]`; the
PR-0(c) exporter item (§9.1a) must pass through the bridge's, not the basket's.

### §2.4 The dead constants — why the literal six-state enum is refused

`STAGE_CONFIRMING` and `STAGE_CONFIRMED` (`us_early_turn.py:960-961`) are **defined and
never assigned anywhere** (repo-wide: the only assignment is `STAGE_EARLY` at `:1213`;
the only test import is `STAGE_EARLY`). This is deliberate on the confirmed lane — the
bridge documents absence-as-design (`prophet_bridge.py:4354-4357`: "a confirmed-lane row
has no stage… because none of those are statements about it"). A ladder cell named
**Confirming would be born with no producer — the stage=4 defect reborn on day one** —
and **Confirmed would need new engine semantics minted just to fill a display cell.**
The proposal's back half (Aging/Extended/Invalidated) meanwhile duplicates taxonomy 3
(`overtime` / `at_t2`-texture / `invalidated`), which is already computed, published, and
graded. The six-state enum as specified fuses the front half of one live axis (admission
lane) onto the back half of another (management phase) and adds two producer-less cells.
Refused. What ships instead is §6.

**Rider (no dead vocabulary):** PR-0(c) deletes the two never-assigned constants. A
vocabulary value with no producer is how the estate got an unlightable dot; we do not
keep two more in stock.

---

## §3 Ruling (i) — two dimensions, ratified; and what the "lifecycle" actually is

Packet §1 is ratified: `lane` (price/entry read) and conviction/lifecycle are separate
axes; settled by construction.

Sharper than the packet: the proposed lifecycle is **the Prophet funnel position** — one
chronological axis a tracked name moves along:

```
union early signal (watch deck) → plan armed (pre_trigger) → entered
(triggered_pre_t1) → delivering (at_t1/between_t1_t2/at_t2) → overtime |
invalidated → resolved (closed, graded)
```

Every segment of that arc **already has a computed, published producer**: the deck half
is #5370's union admission (`intake.early_turn_watch`, `deck_admitted`), the plan half is
taxonomy 3 (`phase`), and the terminal is `closed` + the graded ledger. Nothing needs to
be invented; the lifecycle needs to be **projected**, not minted.

The **admission lane** (EARLY vs confirmed; operator scoring ruling 2026-08-11) is a
*different* axis — which door and which score family a row belongs to — and stays a fact
column/chip. It never becomes ladder cells: one axis per control (Sol clause 2's
partition law), and its own contract forbids blending.

---

## §4 Ruling (ii) — what survives, what retires

| Construct | Verdict | Grounds |
|---|---|---|
| `lane` (engine field, ledger rows, ranking input) | **SURVIVES UNCHANGED** | it is a real classification with a real job; recutting it would be a data migration with zero display need (§8) |
| 4-dot rail + `_STAGE_BY_LANE` + int `stage` | **RETIRES at board migration** | §1.1–§1.2: two structurally unreachable steps, unlabeled 0-state, and categorically-false progression framing. Not hot-fixed before migration: any interim relabel mints vocabulary #8 and re-breaks Sol's law |
| `phase` (taxonomy 3) | **SURVIVES as engine truth** | already the management contract; slugs remain forbidden at glance tier; `lifecycle_state` is its only public face |
| triage buckets (taxonomy 2) | **SURVIVE on the candidate screener** | they partition a different universe (tonight's candidates, not the Prophet book) and already carry ratified plain-word EN/ZH labels that never say "stage" |
| `early_turn.stage` fact column | **SURVIVES** (EARLY chip/badge + deck sort context) | operator-ratified 2026-08-11; renders as a badge, never as ladder cells |
| `STAGE_CONFIRMING` / `STAGE_CONFIRMED` | **DELETED** (PR-0(c) rider) | never assigned; §2.4 |
| six-state `lifecycle_state` enum as literally specified | **REFUSED** | §2.4; replaced by the derived projection in §6 |
| Weinstein `stage_detailed`, `stage_tilt` | untouched | internal / separate program (`DNR:HOLD-PSQ-TILT-CLOCK`) |

---

## §5 Ruling (iii) — surface ownership

| Surface | Owner dimension | Form |
|---|---|---|
| **Prophet Board count ladder** (docket item 6) | `lifecycle_state` | the §6 cells; canonical total printed once; ladder filters on `data-life`; URL fragment `#life=<cell>` — **this supersedes P0 §B acceptance 3's literal `#stage=confirming` on both counts** (no `#stage=` fragment, no `confirming` cell) |
| **Prophet card lifecycle vocabulary** (§G.1) | `lifecycle_state` | the lifecycle word/fact column on cards; the dated lifecycle rail at detail scale. **§G.1 concurrence: GRANTED**, conditions in §10 |
| **Price/entry read** | `lane` | demotes to a mark chip ("Bottoming entry / 底部入场" · "Continuation entry / 顺势入场" — final chip copy is the designer's within these facts; **no recovery chip** — `recovery` has no producer (§1.1) and a producer-less chip is the §2.4 defect) + LENS receipt; never a progress control |
| **Candidate screener** (us-standouts section, wherever the migration keeps it) | triage buckets | shelf grouping + filter as today; its counts are a different noun (**Candidates / 候选**) and must never visually merge with the ladder's Setups total (Sol clause 2) |
| **Plan detail / LENS** | `phase` + `human_state`/`pulse` | receipts tier; Extended-type texture (e.g. "Extended — Watch Giveback") lives here and at hover, never as a ladder cell (it is a thresholded judgment inside `at_t2`, not a fact) |
| **Terminal deck** | admission lane (`EARLY`) + geometry | unchanged; its own contract |

---

## §6 THE CELL SET — `lifecycle_state` (the §J.9(c) deliverable)

**Unit of account (declared, binding):** a lifecycle cell counts **plan rows** — the
plan is Prophet's unit of inventory (each row is a separate tracked commitment with its
own entry, invalidation, and grade; `id` is unique 140/140 on the live payload) — except
`watch`, which counts **tickers with no open plan row** (a watch state precedes any
plan, so it has no plan row to count). One ticker can honestly occupy two cells at row
granularity (live example: FBRT — one closed 07-13 plan in `resolved`, one open 08-05
plan in `ready`; 13 of 127 tickers carry two rows today). Consequences, both binding:
- **The migrated Prophet Board renders one card per PLAN ROW** (keyed by plan `id`;
  `data-ticker` stays an attribute for the live-quote JS). Two FBRT cards — one resolved
  episode, one live plan — is the honest rendering of two separate commitments, and it
  is the only rendering under which ladder counts, `data-life` filters, and visible
  cards agree exactly (the chip-count law, `dashboard.html.j2:15962-15965`).
- **Ticker-keyed surfaces** (the landing showcase, stock-detail and dossier Prophet
  chips — one card/chip per name) use the per-ticker projection: **the cell of the
  newest open plan row (by `recorded_at`, tie-break `id`); else `watch` if the ticker
  is in the watch set (a live fire outranks a finished episode); else `resolved`** —
  single-valued per ticker, test-pinned (§9).

**Universe** = the published Prophet book: every row in `site/prophet/index.json.plans`
(the active book, `active_count`) **plus** every deck-only watch ticker. Archived plans
(`plan_count` − `active_count`; 162 − 140 = 22 today) are ledger population, quoted by
the track-record surfaces, never ladder-counted.

**Derivation** — total by construction at each unit:

```
per plan row (first match wins → disjoint; terminal else-arm → exhaustive):
  1. closed == True                             → resolved
  2. phase == "invalidated"                     → invalidated
  3. phase == "overtime"                        → overtime
  4. phase in {"at_t1","between_t1_t2","at_t2"} → delivering
  5. phase == "triggered_pre_t1"                → entered
  6. phase == "pre_trigger"                     → ready
  7. anything else (unknown/absent phase)       → ready  + ::warning receipt
     (an unknown state is never advertised as further along — the same rule
      stage_for() applies to unknown triage states)

watch set (ticker-granular, disjoint from the open book by construction):
  intake.early_turn_watch  MINUS  {ticker of any OPEN plan row}
     (minus OPEN — not any — rows: a fresh union fire on a name whose only
      plans are closed is a live watch state, not a resolved one)
```

**The cells** (funnel order, left → right on the ladder):

| # | Key | EN | ZH | Fact it states | Producer (all live today) | Count on the 2026-08-10 payload |
|---|---|---|---|---|---|---|
| 1 | `watch` | **Watch** | **观察** | early signal fired on a scored candidate; no open plan | `intake.early_turn_watch` (#5370) minus open-plan tickers | 0¹ |
| 2 | `ready` | **Ready** | **就绪** | plan is live; entry trigger has not fired | `phase=pre_trigger`, open | 56 |
| 3 | `entered` | **Entered** | **入场** | trigger fired; in the entry window, pre-T1 | `phase=triggered_pre_t1`, open | 65 |
| 4 | `delivering` | **Delivering** | **达标** | at or past the first target | `phase∈{at_t1, between_t1_t2, at_t2}`, open | 1 |
| 5 | `overtime` | **Overtime** | **超时** | past its declared window without resolving | `phase=overtime`, open | 0² |
| 6 | `invalidated` | **Invalidated** | **失效** | invalidation level hit; thesis void | `phase=invalidated`, open | 2 |
| 7 | `resolved` | **Resolved** | **已结** | closed — graded out (win, loss, or expired) | `closed=True` | 16 |

Check against the live payload — **two invariants, both binding**:
- **live total** (the P0 headline "N setups today", the answer to "live setups"):
  watch+ready+entered+delivering+overtime+invalidated = 0+56+65+1+0+2 = **124 =
  `open_count`** ✓ — `resolved` is deliberately **outside** the headline total, because
  `active_count` is a documented misnomer (`build_prophet.py:2120-2125`: it "count[s]
  every plan the management engine could state, INCLUDING forward-ledger-closed ones")
  and a headline that counts 16 graded-out plans as inventory sells non-actionable
  states (P0 §B red-team #6).
- **grand total**: all seven cells = 140 + watch = `active_count` + watch ✓ (phase ×
  closed cross-census: `pre_trigger` 56/2, `triggered_pre_t1` 65/2, `at_t1` 0/1,
  `between_t1_t2` 1/5, `invalidated` 2/6, open/closed respectively).

¹ `watch` is 0 on this payload because `build_prophet.py`'s intake export is a **closed
key-by-key whitelist** (`:2137-2230`) that does not yet pass `early_turn_watch` through
— the bridge computes it (`prophet_bridge.py:4752`) and no bake can publish it until the
exporter names it. That pass-through is PR-0(c) item 1a (§9); the bridge-side producer
is merged and live (#5370). **Builder rule:** on a payload with no `early_turn_watch`
key, the watch cell renders as a disclosed absence ("watch tier publishes from the next
nightly"), never as a silent 0 — key-absence and zero are different facts.
² `overtime` and `at_t2` are zero today but have real producers in the management engine
(`_VALID_PHASES`, phase weights) — a producing cell at zero is honest inventory; a cell
with no producer is forbidden (that is exactly the stage=4 defect, §2.4).

**Label rationale (binding):**
- ZH is a native two-character arc — 观察 · 就绪 · 入场 · 达标 · 超时 · 失效 · 已结 — not
  translated English. 失效 converges with the shipped invalidation vocabulary (失效价:
  "Base broken — thesis void level hit" / "筑底破位 — 失效价已触发",
  `build_prophet.py:345`); 已结 converges with the shipped pulse terminal ("closed ·
  stopped out" / "已结 · 止损离场", `build_prophet.py:1350-1354`); 超时 converges with the
  shipped phase word (`:1151`); 入场 is the estate's standard word for entry (513
  template hits vs 19 for 进场 — the ladder must not mint the minority form); 就绪 is
  reused from the retiring rail and 观察 collides with the retiring lane-heading label —
  both made safe only by the §10 sequencing conditions.
- "Invalidated/失效" complies with the falsifier-language law (operator 2026-07-27,
  #3821): it names the plan's own stated invalidation level being hit — a fact about the
  plan the user was shown — and both words already ship on the card. "Falsifier fired /
  证伪" remain banned.
- "Extended" is deliberately **not** a cell: it is `p1 ≥ 1.5` texture inside `at_t2`
  (`_human_state`, `prophet_management.py:1090-1091`) — a thresholded judgment, and the
  ladder is a fact partition. It stays hover/receipt tier, alongside the existing `ext_z`
  chase flags.
- "Aging" (the proposal's word) is rejected for `overtime`: the fact is a declared
  window expiring, not gradual decay; the management engine's own shipped word is
  Overtime ("Overtime Stall").

**Count law (Sol clause 2, made mechanical):** `build_prophet.py` publishes a
`lifecycle_counts` block (`{watch, ready, entered, delivering, overtime, invalidated,
resolved}` + `lifecycle_live_total` + `lifecycle_grand_total`) computed in the same
pass that stamps per-row `lifecycle_state`. **`lifecycle_live_total` (the six live
cells) binds the P0 headline** ("N setups today"); `resolved` renders as the ladder's
terminal cell or an adjacent quoted count — either satisfies clause 2 because both read
from the same block; that choice is the designer's. Every rendered quantity quotes the
block or a difference of its values. CI mutates one row's state (flip `closed`) and
asserts the block moves — the counts may not be derivable-but-unchecked (the
receipt-from-the-same-variable trap).

---

## §7 Naming-law compliance (Sol: two concepts may never ship under `stage`)

Today the estate ships **four different concepts under the literal field name `stage`**
(census rows 1, 2, 4, 5) — and one of them (row 5) renders the word **"Stage / 阶段"**
directly to users with its own count chips. Disposition:

| Concept | Machine name today | Ruling |
|---|---|---|
| public lifecycle | — | **`lifecycle_state`**, DOM `data-life`, URL `#life=` — the only vocabulary ever *called* a lifecycle on Prophet surfaces |
| card int rail | `stage` (int) | field + rail retire at migration; the inline map duplicate at `dashboard.html.j2:16016` dies with it |
| candidate triage | `stage` (str) / `data-stage` | labels already never say "stage" to users; machine rename `data-stage` → `data-triage` rides the board-migration PR (fossilized snapshots are NOT rewritten — §8); until then it is an internal name, not a shipped semantic |
| stocktable lane re-map | `stage` (str, `ENTRY/RIPENING/RAN_LATE/KNIFE`) + label "Stage / 阶段" | **retires at the board migration** (§10.6): the label is the law's directest violation, its chips are counts outside the count law, and its `RIPENING` arm is producer-less (§1.1) |
| admission lane | `early_turn.stage` | survives (operator-ratified fact column); rename to `admission_stage` is a **non-blocking rider** on the next bridge-touching PR, coordinated with the Terminal (it consumes the payload — `charting-app lib/flowSource.ts` maps `prophet_idx` → `prophet/index.json`) |
| Weinstein | `stage_detailed` | internal, never rendered — outside the law's shipping scope |

**The word "stage" retires from all user-facing Prophet vocabulary** — labels, URLs,
aria, marketing copy. The glance-tier words are the cell labels themselves.

---

## §8 Migration and ledger constraints

- **No lane recut.** This ruling deliberately leaves `lane`'s values untouched, so the
  board ledger (`snapshots.jsonl` per-row `lane`, one row per as_of×lane×ticker×horizon
  in the grade parquets) needs **no migration**. Any future lane recut remains a data
  migration per the packet's §3 constraint — unchanged, just not triggered.
- **Fossils are never rewritten.** Historical snapshots keep the int `stage` and old
  labels as written; consumers of history read era-appropriately (house law).
- **`lifecycle_state` is additive** and display-tier: it enters the plan exporter via
  the **optional-fields path with a schema version bump and manifest regen** — the
  exporter's own documented law for additive keys (the #5395 J-15 lesson: putting an
  additive key in required fields ships a contract violation that reads green only while
  the manifest is stale).
- **Comment heals:** `grade_us_board.py:756`'s domain comment (`'trend' | 'recovery' |
  None`) is corrected to the real domain (`bottoming | continuation | watch | leader |
  ran | None` — `recovery` retained only if its producer is ever un-stubbed;
  `us_board_rank.py:2134` writes `lane="ran"`), and `_prophet_card.html.j2:55-56`'s
  `stage_key` comment gains the missing `basing` value — both in PR-0(c).
- **Documented, not touched:** `retro_grades.parquet`'s `lane` column is board-list
  membership (`buy/watch/laggards/leaders`), a different vocabulary from the row's entry
  lane under the same name. Recorded here so no consumer conflates them; renaming a
  parquet column is a migration this ruling does not order.

---

## §9 PR-0(c) — the implementable spec this ruling unblocks

Scope (all in `scripts/build_prophet.py` + `engine/us_early_turn.py` + tests; display
tier; no engine judgment changes):

1. Emit `lifecycle_state` per plan row per the §6 derivation (precedence order verbatim;
   unknown-phase arm emits a `::warning` line — bare `print(..., flush=True)` at line
   start per the annotation law).
   **1a.** Add `early_turn_watch` to the intake exporter's whitelist
   (`build_prophet.py:2137-2230` currently drops it — §6 fn.1), sourcing the BRIDGE's
   `list[str]` (never `basket_score`'s same-named `list[dict]`, §2 note c), with a
   pass-through test — the closed whitelist is exactly the silent-sibling shape that
   kept the watch producer dark.
2. Emit the `lifecycle_counts` block + `lifecycle_live_total` + `lifecycle_grand_total`
   on the index (optional-fields + version bump + manifest regen).
3. Ship the EN/ZH lexicon as paired constants (the §6 table verbatim; both languages
   all-or-nothing).
4. Delete `STAGE_CONFIRMING` / `STAGE_CONFIRMED` (§2.4 rider).
5. Heal the two stale domain comments (§8: `grade_us_board.py:756`,
   `_prophet_card.html.j2:55-56`).
6. Tests: (a) partition law — every plan row maps to exactly one cell,
   `lifecycle_live_total == open_count + watch_count`, and
   `lifecycle_grand_total == active_count + watch_count`, mutation-checked (flip one
   row's `closed`, assert the block moves); (b) no-dead-cell law — every non-`watch`
   cell's phase set is a subset of `prophet_management._VALID_PHASES` (pins the cells to
   producing values; if a phase is ever removed, the cell census goes red rather than
   silently zero); (c) key-absence vs zero for `watch` (§6 footnote 1); (d) lexicon
   pairing (no EN without ZH); (e) per-ticker projection is single-valued (§6 unit of
   account — FBRT-shaped fixtures: one open + one closed row).

Explicitly **not** in PR-0(c): any template/rail change, any `data-stage` rename, any
lane change, any Terminal change. The field ships dark; surfaces adopt at migration.

## §10 Board-migration gates (§G.1 concurrence — granted with conditions)

The design packet's §G.1 default (the lifecycle lexicon re-cuts the card rail; the price
read demotes to a LENS receipt) is **concurred**, with binding conditions:

1. **Same-PR retire:** any surface that gains the ladder or lifecycle labels retires the
   old 4-dot rail *in the same PR*. Two lifecycle vocabularies may never co-render on
   one card (§G.1's own law) — and 就绪 is reused by §6, so an old rail saying 就绪
   (=continuation lane) beside a ladder saying 就绪 (=armed plan) would be a live
   contradiction during any split rollout.
2. **Scope:** this ruling governs the US Prophet estate. `pv_card`'s int-rail contract is
   shared by `hk/china/canada/intl` templates (e.g. `china.html.j2:3551` hardcodes
   `'stage': 4`), so the macro grows a lifecycle variant behind a parameter; other
   markets keep the legacy rail until their own program lanes adopt this cell set —
   convergence is the default expectation, divergence needs its own ruling.
3. **The ladder counts the book, not the screener — and the board must therefore RENDER
   the book.** These are inseparable: on the live estate the us_stocks card grid is
   built from candidates (`dashboard.html.j2:15842-15862` reads `_su.buy`), the plan
   book is rendered by **no macro template at all**, and the two populations barely
   overlap (127 plan tickers vs 69 buy rows, intersection 35). A ladder that counts
   plans while filtering candidate cards would put ~75% of its counted population
   off-page and ~50% of visible cards outside its count — violating P0 §B acceptance 1
   and the board's own standing law that "a filter chip whose number disagrees with
   what filtering shows is a defect" (`dashboard.html.j2:15962-15965`).
4. **Gate (the migration's structural act): the Prophet Board's card grid re-sources
   from the plan book** (`site/prophet/index.json.plans`, one card per plan row per §6)
   in the same PR that introduces the ladder; the candidate screener (us_standouts buy
   rows, triage shelves, lane headings) moves to its own clearly-labeled section or
   page under the noun **Candidates / 候选** with its own printed-once total. **P0 §B
   acceptance 1 is amended accordingly:** Setups (ladder), Groups, and Candidates are
   three governed populations, each with one canonical total; acceptance 3's
   `#stage=confirming` is superseded by `#life=<cell>` (§5). One-referent-per-page word
   law: 观察 (and any other cell word) may carry only one meaning per page — the
   screener's watch-lane heading relabels or lives strictly inside the 候选 section
   (designer's choice within that constraint).
5. **The stocktable "Stage / 阶段" column** (§2 row 5) retires from the US board in the
   same migration — its label is the naming law's directest violation and its chips are
   counts outside the count law (§7).
6. **The P0 §0 weight-encoding law re-maps.** Its visual grammar (dashed → half-filled →
   solid → muted → hollow/struck) was written against the refused six-state enum; the
   designer re-issues it over the §6 cells (a natural mapping exists — watch dashed,
   ready half, entered/delivering solid, overtime muted, invalidated hollow/struck,
   resolved neutral — but the visual call is design's, not this lane's).
7. **Interim defect disposition:** the shipped rail's unreachable dots stand as a
   documented defect until migration — an interim relabel is refused (it would mint
   vocabulary #8). This is a scheduling argument for docket item 6, not a hotfix ticket.

## §11 Out of scope / follow-ups

- `stage_tilt` (`DNR:HOLD-PSQ-TILT-CLOCK`) and the two-track-record discrepancy — Sol's
  J-queue, untouched.
- `early_turn.stage` → `admission_stage` rename — non-blocking rider (§7).
- CN/HK/Canada rail adoption — per-market program lanes (§10.2).
- Full-universe intake (deck beyond `union ∩ candidates`) — separately chartered (#5370).
- Archived-plan surfacing (162 vs 140) — track-record surfaces own it.

## §12 Panel completeness and red-team record

Prepared by the Prophet program lane (the deciding party) with source + live-payload
verification of every claim above. Red-teamed by an independent Opus reviewer before
publication (adjudication coverage gate); verdict SHIP-WITH-FIXES, all findings
incorporated: 3 blockers (the watch cell's exporter gap — the whitelist drops
`early_turn_watch`, fixed as §9.1a; unit-of-account ambiguity — 140 plan rows vs 127
tickers, 13 duplicated, fixed by the declared unit + per-ticker projection in §6; the
board-renders-candidates / ladder-counts-plans mismatch, fixed by §10.3-4), 6 material
findings (stage=2 also structurally unreachable; the seventh vocabulary — the
stocktable "Stage / 阶段" column; `active_count`'s documented misnomer → the two-total
law; the 失效价 receipt mis-cited; 进场→入场 convergence; the 观察 lane-heading
collision), and 8 minor/nit corrections (citation drift, comment-heal scope, P0
acceptance supersessions, weight-encoding re-map, CN stage-4 hardcode scoping). The
reviewer's independent census reproduced the ledger history (828 buy rows, zero
trend/recovery), the phase×closed cross-census, and the dead-constant claim exactly.

The motivating exemplars were run: the live board (69 rows), the live book (140 plans,
127 tickers), the anonymous landing showcase (12 cards), and the full v1 ledger history
(18 snapshots) — the cell set covers all of them with zero unmapped rows at the declared
units.
