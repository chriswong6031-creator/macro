# CN PROPHET v4 — intelligence-ranked, entry-gated (SPEC)

**Status:** LIVE from 2026-08-15 (operator commission "Handoff B").
**Definition:** `cn_prophet_v4` · **Displaced ordering shadow:** `cn_prophet_v3_shadow`
**Decision record:** `DEC:CN-PROPHET-RANKS-BY-BOARD-INDEPENDENT-INTELLIGENCE`
**Predecessor:** `research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (v3 R1–R3)

---

## §0 ACCEPTANCE GATES ("not done unless")

1. The v3 **score** is bit-identical with and without intelligence — no intelligence
   term enters `SCORE_WEIGHTS`. *(pinned: `test_intel_adds_no_score`)*
2. Every v3 **admission gate** is preserved and order-independent — an unfillable name
   stays out no matter how interesting. *(pinned: `test_admission_gates_are_order_independent`)*
3. The interest composite is **board-independent by construction** — the four
   board-derived Hub terms are never computed. *(pinned structurally:
   `test_module_never_reads_the_board_or_the_hub_composite`, AST read-scan,
   mutation-checked)*
4. A name with no measurable intelligence keeps its **v3 priority**, never a fabricated
   zero. *(pinned: `test_unavailable_intel_keeps_its_v3_priority_rather_than_sinking_to_zero`)*
5. Total evidence failure degrades to **exactly v3 ordering**, never dark or random.
   *(pinned: `test_missing_intel_map_leaves_board_order_identical_to_v3_order`)*
6. The displaced v3 order accrues as a labelled shadow with a **named tripwire and a
   revert action**. *(G0.8; `cn_v3_tripwires` R4)*
7. An **operator-readable side-by-side** of the resulting names exists before merge.
   *(`research/cn_prophet_v4/V4_VS_V3_BOARD_PROOF_<date>.md`)*

---

## §1 The one-line architecture

> **Rank by interestingness. Gate by entry.**

v3 conflated the two: `prophet_score` both ranked names and, through the featured caps,
decided which names reached the shelf. A name with a beautiful entry oscillator and
nothing interesting about it could take a shelf slot from a name the intelligence desks
were actively accumulating.

v4 splits them:

| Decision | Owner | Changed in v4? |
|---|---|---|
| Is this name *interesting*? | `intel_interest_score` (`engine/china_intel_interest.py`) | **NEW** |
| Is this name *scoreable*, and how highly? | `prophet_score`, `SCORE_WEIGHTS` | no |
| May this name be *featured now*? | v3 execution/admission machinery | no |
| Which lane does it live in? | v3 lifecycle lanes | no |
| Who arbitrates all of it? | `engine/china_board_rank.py` | no — still the sole authority |

Ordering key, within every existing lane:

```
(-intel_interest_score if measured else -prophet_score,  -prophet_score,  ticker)
```

The featured and sector caps iterate in this order, which is what gives interest real
authority: it decides the last shelf slot. It can never *admit* a name — the caps only
choose among names v3's gates already cleared.

---

## §2 Why not just read the Intelligence Hub's `opportunity_score`

Because **the Prophet board is one of the Hub's five desks.** `china_intel_hub` carries
the board's own output back into its composite through four separate terms:

| Hub term | Where | What it imports |
|---|---|---|
| `board_row` direction | `_dirs` | board membership read as a bullish desk |
| board label → edge | `_edge_remaining` (`_LABEL_EDGE`) | the board's own lifecycle label |
| board-ABSENT bonus | `_edge_remaining` | +0.75 for "not on the buy board" |
| board in `lag_up` | `_leading_gap` | the board as a lagging desk |

Ranking the board by that number would close a loop: names would rank highly partly
*because they already rank highly*. `china_intel_interest` re-derives the composite with
all four **structurally absent** — not zeroed, not down-weighted, never computed and
never available to compute — and declares them in `BOARD_DERIVED_TERMS_EXCLUDED`.

**What survives** (upstream evidence, not Prophet's own output): altdata convergence /
conviction (the signal core), divergence-radar strength, price trajectory (off-high
room, RS vs CSI300, 20d extension), special-situation overhang penalties, altdata
crowding penalty, falsifier penalty, leading-desk information.

```
interest = 100 × signal_core × falsifier_penalty × edge_remaining × gap_mult
```

### §2.1 One deliberate deviation from the Hub: direction

The Hub takes `abs(convergence)` because it ranks a **two-sided command list** where
direction is carried separately by `lean`/`stage`. The Prophet board is a **one-sided
BUY shelf**, so magnitude-without-direction is the wrong core.

Measured 2026-08-15 on the live 116-row board: **60 rows read `distribute`**, and an
unsigned core placed the three most strongly-distributed names in the top three slots —
the desk's own verdict inverted. v4 credits the accumulate side only; a distribute read
is a *measured zero*, and `conviction100` (an unsigned magnitude) is credited only when
the side agrees. Pinned by `test_distribute_never_outranks_accumulate_at_equal_magnitude`.

### §2.2 One deliberate deviation from the Hub: no default edge

The Hub awards a 0.4 default when its edge-component list is empty. Here an empty list
is *genuinely* empty (the board legs that could have filled it are excluded), so the row
takes the `no_edge_evidence` fallback instead of a middling constant nobody measured.

---

## §3 Nulls are not zeros

Two states, and the difference is load-bearing:

| State | Meaning | Ordering |
|---|---|---|
| `basis: measured`, score `0.0` | the desks looked and had nothing bullish to say | bottom of the measured block |
| `basis: fallback_v3`, score `None` | no desk has ever seen this name (`no_desk_evidence`), or no edge evidence could be formed (`no_edge_evidence`) | **keeps its v3 priority** |

Fabricating a zero for the second case would sink every uncovered name beneath every
covered one on evidence that was never gathered. The basis is stamped on every row, and
`china_intel_interest.coverage()` publishes the split into the board's
`ranking.input_coverage.intel_interest` receipt — so a board where everything fell back
is *visibly* a v3-ordered board rather than a silently v3-ordered one.

---

## §4 Where the evidence comes from (and a trap)

**Trap, measured 2026-08-15:** `site/chinaaltdata/by_ticker.json` is a **top-30 /
bottom-30 / triple-30 DISPLAY slice** — 89 tickers, of which **0** were on the 116-row
board. It is also written by a builder that runs *after* `build_china` in
`asia-close.yml`, so reading it would give the board a stale 30-name sample of itself.

v4 therefore calls `china_altdata.full_rows()` — the full per-ticker universe,
recomputed in process: **5,346 names in ~1.8s, covering 116/116 board rows.** Radar and
special-sits flags are read through the Hub's own INPUT loaders (reused, not copied, so
the two scorers can never disagree about what a desk said); price trajectories cost
~0.7 ms/name and are computed only for names a desk actually saw. Total added render
cost ≈ 3s.

Degradation is total-loss-safe: any failure returns every row as `fallback_v3`, which
orders the board exactly as v3 ordered it, and logs a line-start `::warning`.

---

## §5 Versioning, shadow, and era bookkeeping

- `cn_prophet_v4` is live and accrues **prospectively**.
- `cn_prophet_v3_shadow` re-runs the displaced v3 ORDER on the same scored rows with the
  same admission rule and caps — isolating the one thing v4 changed. It is registered in
  `china_standout_track.WATCH_DEFINITIONS`, so it can never own a headline grade. This
  reuses the existing mechanism v2 is already preserved under; no second grader was
  invented.
- `cn_prophet_v2_shadow` is untouched and keeps ordering by `score_rank`, so the v2-vs-v3
  **admission** race is not confounded by the v4 **ordering** change.
- `cn_prophet_v3` joined `_CN_SUPERSEDED_ERA_STAMPS` in the same PR. **Historical v3 rows
  are unchanged** and stay a closed era, graded as `prior_record`, never pooled with v4's.
  (The repo's era-partition tripwire caught this omission during the build — the same
  omission that once dropped 72 v2 rows out of every cohort, #4509.)

---

## §6 What this is NOT

- **Not a promotion.** No gauntlet was run, none is claimed, and the R4 tripwire's
  evidence field says so in as many words: *"NO forward evidence — this wiring ships on a
  first-principles argument and an operator's read of the resulting names."* The ordering
  claim has **n=0** and the shadow race is the whole test of it.
- **Not a score change.** `SCORE_WEIGHTS` is untouched.
- **Not an admission change.** No name is admitted or vetoed by intelligence.
- **Not a research pickup.** Nothing under `research/cn_prophet_audit/` is read; the
  P-B2/P-B3/P-C fences are unmodified (annotated, not amended).

---

## §7 Revert path (single field)

`partition_board_rows(..., rank_field="score_rank")` restores v3 ordering; moving
`BOARD_DEFINITION` back to `cn_prophet_v3` restores the stamp. Historical rows are
untouched under either. That is the G0.8 clean revert.

## §8 Next checkpoints

1. **First nightly under v4** — confirm `ranking.input_coverage.intel_interest` shows a
   healthy measured rate and that `cn_prophet_v3_shadow` rows land in the board store.
2. **R4 at n≥60 matured** (`cn_v4_vs_v3_order_shadow_excess`) — the first real evidence
   on whether interest-first ordering beats score-first. Until then the honest statement
   is "this is how we think the board should be ordered", not "this orders better".
3. Any FURTHER authority for intelligence (gate, size, score) is a separate
   pre-registered question and is not opened by this spec.
