# Prophet Arena — policy registration

**Status:** registered, accruing. **Tier:** display / shadow. **Authority:** none. C2 retired 2026-08-09 → C7 (§C2, §C7).
**Engine:** `engine/prophet_arena.py` · **Tests:** `tests/test_prophet_arena*.py`
**Active ledgers:** `data/prophet_arena/price_basis_trigger_v2/<policy>.jsonl` · **Scoreboard:** `data/prophet_arena/scoreboard.json`, `site/stockdata/prophet_arena.json`
**Registered:** 2026-08-06. **Temporal v2 boundary:** 2026-08-08; v2 starts empty and has no backfill. The top-level v1 ledgers are sealed audit evidence and are excluded from every active grade and summary.

---

## §0 The standing line

> **Shadow record — the live policy changes only by operator ratification.**

Nothing in this document, and nothing any of these policies ever produces, changes a live
Prophet plan. A policy that wins here produces a scoreboard packet for the operator. The
change, if any, ships afterwards as its own PR. See §Promotion.

---

## §1 Why this exists

The closed-plan record says **intake policy is the binding accuracy constraint** — not
geometry, not management. As of 2026-08-05, `data/prophet/ledger.jsonl` holds 16 closed
plans:

| measure | value |
|---|---|
| closed plans | 16 |
| win rate (positive stock result) | 12.5% (2 of 16) |
| mean `stock_result_pct` | −5.03% |
| median `stock_result_pct` | −5.51% |
| outcomes | EXPIRED 9 · INVALIDATED 6 · T1_HIT 1 |
| mean result of the 9 EXPIRED | −4.44% |
| days held by the 9 EXPIRED | 45, 45, 45, 45, 45, 45, 45, 46, 47 |

Nine of sixteen plans rode the full horizon without ever hitting invalidation and finished
down. That is a *policy* signature, not a *geometry* one.

House law forbids changing the live pick rule without measured evidence plus operator
ratification, and a one-off backtest of a re-slice is not that evidence: the champion's own
record accrues prospectively, so its challengers must accrue the same way — on the same
nights, from the same artifact, against the same ruler.

**The Arena manufactures that evidence continuously.** Every night, each frozen challenger
re-slices the SAME in-memory candidate artifact the live path just used into a shadow plan
set; each shadow plan is graded by the SAME closure rules the champion's forward ledger
uses; each policy accrues onto its own prospective ledger.

---

## §2 The ruler

**`engine.prophet_arena.replay_closure` is the only grader**, and the champion (C0) is
graded by it too — so a champion-versus-challenger difference can never be a difference of
rulers.

It mirrors `scripts/build_prophet.py::_determine_outcome` (L484-625). Conventions pinned,
with the line each one mirrors:

| # | Convention | Champion line |
|---|---|---|
| 1 | **Close-based, never touch-based.** An intraday spike through T1 that closes below it does not close the plan. | L519 ("conservative (may miss intraday crosses)") |
| 2 | **Strictly after `price_basis_date`** — the close whose price became `entry` is excluded. `signal_date` remains causal event provenance, not the grading clock. | live `plan_clock_date` |
| 3 | **Same-day precedence is worst-case-first**: invalidation → T2 → T1. A bar both below invalidation and above T2 records INVALIDATED. | L566-581 |
| 4 | **First-trigger-closes.** T1 then later T2 is recorded T1_HIT forever. | L502-506 |
| 5 | **No position before entry trigger confirmation.** If the horizon arrives without confirmation, the outcome is `NO_ENTRY` with null P&L. | live P2 contract |
| 6 | **Expiry checked last within the bar, on CALENDAR days**: `(ts - clock_ts).days >= horizon_days`. Not sessions. | live P1 contract |
| 7 | `stock_result_pct = (close_price / entry - 1) * 100`, rounded to 4. | live ruler |
| 8 | `days_held = close_date - price_basis_date`, calendar days. A frame ending before that clock plus the horizon remains **open**. | live P1 contract |

**Pin 9 is the one convention with no champion line to mirror** (C6 only): the 21-session
time stop is evaluated **after** the three price triggers and **before** the calendar
expiry check. "21st session" counts post-entry-clock **bars** in the frame the replay walks
(1-based), not calendar days — the rule is about how long dead money is held, and sessions
are the unit a holder experiences. On a bar that is both the 21st session and past the
calendar horizon, `time_stopped` records; by construction that collision is rare (21
sessions ≈ 29-31 calendar days against a 45-day horizon).

**Headline read:** withheld until a policy has **20 closed shadow plans**. Below that the
scoreboard prints the count and says it is too early. Nulls are printed, not hidden.

---

## §3 The policies (FROZEN)

All seven are frozen as of the registration date. Changing any definition means a new
policy key and a fresh ledger — never an edit in place, which would silently mix two rules
in one record.

Every policy inherits the champion's admission filter, sort key, geometry, and plan id by
**calling `engine.prophet_bridge` with modified inputs** (`select_candidates(standouts,
n=None)` yields the complete admitted population in champion order).
Nothing is re-implemented.

**Frozen keys.** These strings are the ledger filenames and the scoreboard's policy ids.
They are part of the registration: a key never changes meaning, and a changed rule takes a
new key.

| key | grain | differs from the champion in |
|---|---|---|
| `C0_champion_mirror` | selection | nothing — it *is* the champion (control + validity pin) |
| `C1_buy_soon_first` | selection | ordering: `act_level == 2` lifted above `act_level == 3` |
| `C2_stage_ran_preferred` | selection | **RETIRED 2026-08-09 → C7** (act-level widening; see §C2) |
| `C3_door_w_union` | selection | the candidate pool (Door W union, 4 reserved slots) |
| `C4_dispersion_cap` | selection | the nightly cap (12 or 6, by dispersion state) |
| `C5_align2_gate` | selection | admission (restricted to fully-aligned names) |
| `C6_time_stop_21` | **closure** | the exit rule only — the plan set equals C0's |
| `C7_buy_soon_admitted` | selection | admission (one leg relaxed: the status class) |

### C0 `champion_mirror` — CONTROL and validity pin

Exactly the live `select_candidates` on the night's artifact, with the same duplicate-id
and open-plan suppression the live path applies. C0 and C6 consume the full lossless
population; they have no positional or sector cap.

**Also the harness-validity pin.** C0's plan ids must match the live origination's ids
exactly. A mismatch means the harness is reading a different world than the champion did;
the scoreboard raises `harness_validity.harness_ok = false` and says every number on the
page is suspect. It never diverges quietly.

### C1 `buy_soon_first`

Same admission, same champion sort — but `act_level == 2` rows are lifted above
`act_level == 3` rows before it (champion order preserved within each group).

**Rationale (measured).** The #4547 entry-ladder cells
(`research/prophet_us_audit/label_grading_battery_results.json`) put **buy_soon at +3.19pp**
per-name median excess at H=10 on n=31 — the best **non-thin** cell, and #1 in the file's
own `ranked_non_thin_by_per_name_median`. **buy_now read −0.48pp at H=10 on a THIN n=9
cell.** The champion's `act_level`-descending tie-break prefers the more imminent entry —
the cell that measured worse, on the thinner evidence.

> **Citation correction.** The commissioning brief described this as "buy_now negative at
> H=21". It is not: at H=21 the raw buy_now reading is **+0.53pp on n=1**, and the only
> negative H=21 buy_now figure is the date-demeaned column, which that artifact explicitly
> disclaims at H=21 ("ALL rows share ONE admission date … Read raw"). The negative buy_now
> reading is real but lives at **H=10**. This policy is registered on the corrected
> citation.

### C2 `stage_ran_preferred` — REGISTERED DEVIATION

Rows the board stages as `ran` (`us_board_rank.STAGE_RAN`; entry status ∈ {extended,
topping, hold}) are **admitted** and lifted above the rest, then champion sort, then cap.

**Rationale (measured).** `label_grading_battery_results.json:1945-2037`: the STAGE_RAN
shelf graded a **14.5% loser rate (n=55, 47 names)** against **27.6% for the rest of the
buy lane (n=348, 213 names)**, with **no half-split sign flip** (first half 14.7% on n=34,
second half 14.3% on n=21). The board's own stage order nonetheless ranks `ran` *below*
`live` and `setting_up`.

**The deviation, and why.** The brief specified "same filters; rows carrying the stage-ran
evidence sort first" — a pure re-ordering. Measured on the 2026-07-31 artifact, that
construction is **vacuous by definition**:

- the champion's admitted pool was 25 rows, **all** of stage `live`;
- **all 17** stage-ran buy rows carried `act_level` 0 or 1, so none cleared the
  `act_level >= 2` gate;
- none reached the caution-mode `score >= 60` escape;
- 12 of the 17 were band `low` and hard-excluded anyway.

The relationship is structural, not incidental: `stage_for` returns STAGE_RAN only for
entry statuses extended/topping/hold, and `act_level` derives from urgency
(`entry_signal._ACT_LEVEL`), where only "now" (3) and "imminent" (2) clear the gate. So a
re-ordering policy would sort a set that **cannot contain the thing it re-orders** — and
would report "no effect" when the truth is "never tested". The measurement C2 exists to
probe is *defined on the excluded rows*.

**Frozen construction:** C2 relaxes exactly ONE admission leg — the `act_level` gate, and
only for stage-ran rows — by handing `select_candidates` a copy of the artifact in which
those rows' `act_level` is lifted to the threshold. Band, direction, entry-signal presence
and the gate_go mode remain the champion's own code. The rows carried forward are the
original, unpatched dicts. On the 2026-07-31 artifact this admits 5 names (TJX, STRA, DLB,
BCPC, VIRT — all band neutral/constructive) and displaces the champion's tail 5.

> **RETIRED 2026-08-09 — superseded by the champion it was probing.** ANTICIPATION A1
> (#5105) replaced the champion's act-level gate with status-class admission
> (`{bounce_wait, wait_pullback, hold, buy_now, partial}`), which retires this
> construction twice over. Mechanically: the frozen widening lifts `act_level`, an input
> admission no longer reads, so it can no longer admit anything — the #5105 test suite
> pinned that inertness on merge day, and a frozen key must not quietly go on accruing
> as a different de-facto rule (re-ordering only) under an admission-widening charter.
> On the evidence: the battery's per-status split
> (`section_3_ran_lane.a_stage_ran_from_ledger.H10.per_status`) puts 47 of the shelf's
> 55 rows on `hold` — which A1 now admits champion-side, absorbing the bulk of the
> thesis this policy existed to test. The residue it cannot reach (`extended` n=8, a
> thin directional read the artifact itself flags; `topping` n=0) is too thin to
> re-register today. That residue stays OPEN as ore, not killed: if the extended/topping
> cells fatten, an admission probe for them is a legitimate future registration under a
> new key. The v2 ledger file is sealed in place exactly like the v1 era — kept on
> disk and in the scoreboard's `retired_policies` disclosure with its accrued open
> stamps (5 as of retirement day, none ever graded), never advanced again. Successor:
> §C7, which carries the one-leg-relaxation idiom to the status leg and the
> best-measured cell the new gate refuses.

### C3 `door_w_union` — REGISTERED CONSTRUCTION CHOICE

Candidate pool = champion admitted pool **∪** Door W candidates
(`engine.prophet_doors.door_w_candidates`), deduped by ticker with the champion's row
winning any collision.

**Rationale (measured).** `engine/prophet_doors.py:29-33` and
`research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md:35-39`: on **2026-07-31**, of the 117
names in WASHOUT_TURN/TURN_WATCH, 0 were on the board and 109 were invisible to Prophet;
the highest-conviction sub-class — WASHOUT_TURN with 2D+3D+W all bullish — held **65 names
of which 61 were invisible**. This is a **single-date census, not a rolling statistic**.
These names carry no entry signal at all, which is exactly why no amount of re-ordering can
ever reach them.

**Mapping (the one manufactured field, disclosed).** Door W receipts become candidate-shaped
rows with a **synthesized `entry_signal` carrying `act_level = 2`** — without it they cannot
clear admission, which is the whole point. Nothing else is invented:

- `entry.spot` = the last close from the **same price frame the replay grades on**, so entry
  and exit are quoted from one source;
- `atr_pct` = null, so geometry falls back to the champion's 20-day swing low;
- conviction score and band are null — `select_candidates` reads a null score as 0 and a null
  band as not-"low", so these rows are *admitted* rather than *scored*, and never borrow a
  champion rank they did not earn.

**Slot reservation (frozen).** Door W rows carry no `prophet.score`, so under the champion
sort they land in the legacy tier *below every scored row* and the 12-cap would cut all of
them — vacuous again. C3 therefore reserves **4 of the 12 slots** for Door W names when Door
W supplies that many, ranking them among themselves by depth percentile ascending (deepest
washout first — Door W's own key, never a champion score). The champion's top 8 are
untouched. Both sides backfill if the other underfills, so the book is always 12.

Reserving 4 of 12 keeps the book size constant across policies (which is what makes a
portfolio-grain comparison meaningful) while giving the invisible class a third of it. A
Door W name whose price frame is unreadable, or whose geometry resolves to a null
invalidation, is **skipped and counted** (`skipped_door_w_no_geometry`) — a synthesized row
with no invalidation is a ticker, not a plan.

### C4 `dispersion_cap`

Champion selection and champion order, re-sliced into C4's frozen challenger book: the
challenger cap is **12** when
`data/dispersion/regime.json` reads state `lean_in`, else **6** (the pre-2026-07-28 cap).

**Fail-open to C4's registered 12-row cap** when the artifact is absent, unreadable, undatable,
null-stated, or **staler than 5 sessions**; the mode that fired is always recorded, so "the
cap was 12" is never ambiguous between "lean_in fired" and "the dial was missing".

Staleness unit: business days between the artifact's `as_of` and the run's asof
(`numpy.busday_count`). Market holidays are business days but not sessions, so this
slightly **over**-counts elapsed sessions and declares staleness slightly early — failing
open sooner, the safe direction for a policy that must never quietly size a book off a dead
dial.

**Rationale (measured).** The dial prints `state: "lean_in"`, label *"Selection pays — high
dispersion"*, every night, and has **zero pick-chain consumers**: `engine/prophet_bridge.py`
(including `select_candidates`), `scripts/build_prophet.py` and `engine/us_board_rank.py`
contain **no reference to dispersion at all**. Its consumers are display chips, macro
snapshots, retro-grading, schema declarations, and one portfolio gross-sizing lever that
`engine/dispersion.py` hard-clamps to a no-op in production (`_LIVE_CLAMP = 1.0`; only the
logged `shadow_gross_mult` varies). `docs/SIGNAL_BUS.md:825` catalogues it as display tier.

**Expected null.** On a `lean_in` night C4's cap equals the champion's, so C4's plan set
equals C0's. That is by design: C4 only differs on non-`lean_in` nights, and until one
occurs its record is C0's record. The scoreboard records the mode nightly so the operator
can see how often the arm was actually live.

### C5 `align2_gate`

Champion selection restricted to names whose event-atlas weekly alignment reads **fully
aligned**, then champion sort, then C5's registered challenger cap. The gate is measured
inside the full lossless champion population; C0 itself is not capped.

**The two alignment measures are not interchangeable, and the gate must not treat them as
one.** `event_atlas.live_state` returns:

- per-grid **`align_class`** — how many of the **other two** grids were bull at that grid's
  latest event. **Maximum 2; fully aligned = 2.** This is the SEA taxonomy axis
  (`SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md:97`) and the same leg Door W's W3 uses.
- top-level **`align_now`** — how many of **all three** grids are bull right now.
  **Maximum 3; fully aligned = 3.**

Comparing both to the literal 2 would silently admit a 2-of-3 name as "fully aligned". The
frozen gate is therefore: **primary** = weekly `align_class == 2`; **fallback**, only when
the name has no weekly event on record, = `align_now == 3`, counted separately as
`admitted_via_fallback` because it is a live-state proxy for an at-event measure, not the
same quantity. A name the atlas cannot read is **excluded and counted** in
`excluded_unreadable` — the gate never admits on ignorance.

**Rationale, with its evidence status stated honestly.** The SEA first read calls
misalignment a negative marker against a pooled washout edge of **+0.23pp (13w excess)**.

> **Evidence provenance.** The phrases "misalignment is a negative marker" and "+0.23pp 13w
> excess" are verbatim from the SEA feature's **merge commit message** (`46ae6332c81`), not
> from a committed file. The **−1.33pp** figure quoted in the commissioning brief appears
> **nowhere in the repository as text**. It is reproducible: filtering
> `data/stock_events/` to `grid == "W" ∧ direction == "bull" ∧ depth_class == "washout"`
> and grouping matured `exc_13w` by alignment gives **median −1.3286pp on n=106 for
> `align_class == 0`** (fully misaligned), which rounds to −1.33pp. That is
> **reproducible-but-unpublished**, not a citation. C5 is registered on that basis, and the
> Arena's own prospective record — not this retrospective number — is what the promotion
> decision will rest on.

### C6 `time_stop_21` — CLOSURE grain

The **same plan set as C0 by construction**, with one added closure rule: a shadow plan
still **below its entry** at the close of its **21st post-entry-clock session** closes there with
outcome `time_stopped`. Everything else — T1, T2, invalidation, expiry — is identical to the
champion (Pin 9 governs ordering).

**Rationale (measured).** 9 of the champion's 16 closed plans EXPIRED, riding the full
horizon to a **−4.44%** mean, at 45-47 days held; the whole closed book averages **−5.03%**.
A no-progress time stop is the direct counterfactual: *does cutting dead money at 21
sessions beat riding to the 45-day horizon?*

> **Figure correction.** The commissioning amendment attributed **−5.03%** to the 9 EXPIRED
> plans. −5.03% is the mean of **all 16** closed plans; the 9 EXPIRED average **−4.44%**.
> Both are stated above and the policy is registered on the corrected figures.

**Comparison is PER-PLAN PAIRED, never cohort-level.** Because C6 holds the same plan ids
with the same entries as C0, the two records differ *only in where each plan exited*.
Averaging them as two cohorts would discard that pairing. The scoreboard differences each
plan against itself and reports `n_paired`, `avg_diff_pp`, `median_diff_pp`, and
better/worse/same counts.

**Validity pin:** C6's selection must equal C0's selection. It is a closure experiment; any
selection difference is a harness bug.

### C7 `buy_soon_admitted` — SUCCESSOR to C2 (registered 2026-08-09)

The champion's admitted pool WITH `buy_soon` rows admitted — champion order, C7's
registered 12-row cap. The probe relaxes exactly ONE admission leg, the way C2 did
against the act-level gate: a copy of the artifact is built in which only the
`buy_soon` rows' entry status is lifted to an admitted value, `select_candidates`
judges the copy, and the rows carried forward are the original, unpatched dicts. Tone,
band, tier-cascade, entry-signal presence and the champion's own sort stay the
champion's code. Admission-only by design: no preference lift, so a `buy_soon` row
must EARN its slot under the champion's own ranking, and the record measures admission
rather than admission-plus-reordering.

**The probe value is mechanically irrelevant, and that claim is pinned.** Selection
never reads status beyond the admission class, and class feeds receipts only; the
probe patches to `hold` and a test asserts the selection is identical under a
`buy_now` probe — so a future class-dependent selection change re-opens this
registration loudly instead of silently bending it.

**Rationale (measured, both sides stated).** A1 refuses `buy_soon` deliberately,
citing the CN loser ledger — CN entry statuses graded worst-first: `buy_soon` 46.7%
loser rate, `partial` 41.4%, `buy_now` 30.0%
(`research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §measured; quoted
by the A1 constants block: "it graded WORST of the CN entry statuses; admitting it
imports the chase without the evidence"). The US battery reads the same cell the other
way: `buy_soon` is the BEST non-thin US cell — +3.19pp per-name median excess at H=10,
n=31, 9.7% loser rate, #1 in `ranked_non_thin_by_per_name_median`
(`label_grading_battery_results.json`, the same artifact C1 was registered on). Two
retrospective reads, one cell, opposite verdicts, and the live rule now enforces the
CN side on the US board. C7 accrues the prospective US record that can adjudicate it.
Promotion stays §5: the Arena never flips anything.

**Relation to C1.** C1 tests where `buy_soon`-urgency rows RANK inside the pool; C7
tests whether `buy_soon`-status rows should be IN the pool at all. Under A1 the two
questions decoupled: `buy_soon` status can no longer enter the pool, so C1's lift leg
is expected near-empty (its nightly `act_level_2` receipt is the dial — see §7) while C7
carries the admission question. Same cell, different grains; neither substitutes for
the other.

**Expected shape of the null.** On a night with no `buy_soon` row clearing the other
champion legs, or none scoring into the cap, C7's book equals C0's and the receipts
say so (`buy_soon_admitted_by_widening`, `buy_soon_selected`); like C4's lean_in
nights, an equal-book night is a recorded null, not a silent one.

---

## §4 Ledgers

`data/prophet_arena/price_basis_trigger_v2/<policy>.jsonl` — one file per policy,
schema `prophet_arena.ledger/v2`, **append-only, keep-first**,
**nightly is the sole advancer** (`engine.ledger_lane.nightly_advance_enabled()`,
`COLLECT_LANE=nightly`). A non-nightly run computes everything and writes nothing.

Keep-first is keyed on **`(policy, plan_id, kind)`** where `kind ∈ {open, close}` — one
origination stamp and at most one closure row per shadow plan per policy. Keying on
`(policy, plan_id)` alone would make a closure unrecordable, since the origination row
already holds that key; within each kind the dedup is exactly `(policy, plan_id)`.

**NO BACKFILL.** The v2 ledgers start empty at the temporal-contract boundary and fill one
night at a time. Each open stamp persists formation/event/confirmation/observation dates,
`price_basis_date`, `entry_date`, `recorded_at`, and `trigger`. The 125 top-level v1 opens
and their 30 closes lack that evidence; those files remain byte-for-byte audit-visible but
are sealed and never advanced, graded, or summarized. A small active `n` means *young*,
not *weak*, and the scoreboard discloses both eras.

`price_basis_date` is accepted only from `staleness.price_through` when
`staleness.basis == "panel_majority"`, `delayed == false`, `unknown == false`, and the
panel is not mixed-vintage. A current wrapper `as_of` or `basis == "board_asof"` cannot
launder an older or unproven ranked-price source; all policies fail closed together.

Shadow plans carry **no option contract and no thesis prose**. The live forward ledger's
`option_result_pct` is null on all 16 closed rows — options are not part of the ruler — and
thesis strings cannot change an outcome. Resolving either for every policy plan would
spend render budget on fields the measurement never reads.

---

## §5 Promotion protocol

1. A policy accrues to **≥ 20 closed shadow plans**. Below that the scoreboard prints the
   count and withholds the headline.
2. `harness_validity.harness_ok` must be **true** — C0's ids matched the live run's. A
   flagged harness invalidates the whole page, not just C0.
3. The scoreboard packet goes to the **operator**: per-policy record, the same-cohort (or,
   for a closure policy, per-plan paired) comparison against C0, the nights count, and the
   nulls.
4. **The operator ratifies. The Arena never flips anything.**
5. If ratified, the change to the live rule ships as **its own PR** against
   `engine/prophet_bridge.py`, with its own tests. The Arena keeps running the old policy as
   a new challenger so the swap itself accrues a record.

---

## §6 Fences

- **No pick-chain import of Arena output.** `engine/prophet_bridge.py` and
  `engine/us_board_rank.py` contain no reference to `prophet_arena` at all;
  `scripts/build_prophet.py` may **call** the hook but may not read any Arena output path,
  ledger, or scoreboard. Test-pinned in `tests/test_prophet_arena.py::TestImportFence`,
  both by AST inspection of the module's runtime strings and behaviourally (a nightly run
  on a temporary root creates files **only** under `data/prophet_arena/` and
  `site/stockdata/prophet_arena.json`).
- **Display tier, authority all false.** The scoreboard carries
  `may_rank / may_gate / may_size / may_escalate = false`.
- **No banned vocabulary.** Test-pinned against "validated", "已验证", and the
  falsifier/refutation family (operator 2026-07-27) in the whole payload.

### DO-NOT-REBUILD note

**This is POLICY comparison at portfolio grain on prospective data. It is NOT
outcome-audition per name.** The Arena never asks "was this pick good" and never re-scores,
re-ranks, or auditions an individual name against its own outcome. It asks "does this frozen
*rule* produce a better book than the frozen champion *rule*, over the same nights, under
one ruler". No per-name score, gate, or escalation originates here, and no fused composite
is constructed.

---

## §7 Known limitations, stated up front

- **C4 is dormant on `lean_in` nights** (§C4). Its record equals C0's until a non-`lean_in`
  night occurs.
- **C1's lift leg is expected near-empty under A1.** act_level 2 maps to urgency
  "imminent", whose status (`buy_soon`) the status class refuses — so the rows C1 exists to
  lift can rarely (via transformed statuses) or never be in the pool. Its nightly
  `act_level_2` receipt is the dormancy dial; its reckoning is a separate ruling once that
  receipt has a record.
- **C3 ⊃ C0 in part** — C3 keeps the champion's top 8, so its record partly overlaps C0's.
  The Door W increment is separately countable (`door_w_selected`) and is the arm's real
  signal.
- **C5's primary gate is often unavailable.** On the 2026-07-31 artifact, 9 of 13 admitted
  names cleared via the `align_now` fallback rather than the weekly `align_class` primary,
  because most names have no weekly event on record. The counts are reported nightly; a
  record dominated by the fallback is a record about a proxy, and must be read as one.
- **Door W dominates the Arena's runtime.** `door_w_candidates` evaluates the organ
  universe itself rather than reading an artifact (the nightly `emit_prophet_doors` writes
  only newly-flagged *entries*, not tonight's full candidate list, so there is nothing
  cheaper to read). Measured on the 2026-07-31 tape: **16.9 s warm** for 702 names
  evaluated → 91 in WASHOUT_TURN → 26 fresh → 25 aligned. A cold parquet cache pushes the
  first call past 120 s. Everything else in the Arena is sub-second.
- **The champion's own record (n=16) is small.** Every comparison against it inherits that
  thinness until both sides accrue.
