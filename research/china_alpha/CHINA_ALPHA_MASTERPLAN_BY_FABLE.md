# China Alpha Masterplan — by Fable (2026-07-03)

*The solution document for the China Alpha Program. Inputs: `PROGRAM.md` (charter),
`OWNER_RATIONALE.md` (ground truth, spec S1-S5), `phase1/*.md` (10 investigation reports),
`phase1/_SYNTHESIS.md` (rulings R1-R6, reconciliations), and three inline probes run 2026-07-03
06:35-07:00 (owner-read reproduction, board git-history, #1054 narrative-radar assessment).
Companion problem docs: `CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md`,
`CHINA_ENGINE_PROBLEM_BRAINSTORM.md` (§8 tensions), `CHINA_ENGINE_REASSESSMENT.md`.*

---

## 0. Mission and acceptance gate

**Owner mission:** a board full of *outstanding stocks at outstanding entries* — names about to run
(sector about to run / post-washout mean reversion / catalyst), not extended leaders — with a
ranking and UI a user can actually trust.

**Acceptance gate (the exit question):** *"Does the dashboard genuinely provide incredible stock
picks at great entries?"* — answered by forward-graded, fill-realistic evidence (§5), not vibes.

---

## 1. The diagnosis, in one causal chain

> The system **already contains the owner's playbook in pieces** — COILED detects the base at the
> low, `cycles._tf_state` computes the 2W/1W washout+turn states the owner reads by eye (verified:
> all three exemplar chart reads reproduce exactly from production primitives), the T3/T4 cascade
> projects imminent crosses, THS narrative heat exists in data, and a daily sector first-tick-up
> filter already runs in `forward_log.parquet`. But the pieces are assembled backwards: the
> **latest-firing signal (washout_2w) carries the biggest rank bonus (+0.50) and acts as the
> gatekeeper of visibility**, while the earliest (COILED, at the base low) carries half and the
> W-tier states are consumed by nothing; the **rank and the displayed card are two unreconciled
> organs** (Spearman −0.19; 77/110 cards wear "extended" chips); the **freshness cliff makes names
> flicker on/off the board** (603129: #69→gone→#1→gone→#2; 688306: #24→gone→#5→#8→#4→gone→#3)
> instead of transitioning between honest stages; the page **advertises an edge (quarterly reversal
> basket) that is a different product from what it surfaces** (rev_z is negative on 2 of the
> owner's 3 exemplars); the **older forward grader is structurally dead** (0/120 board tickers
> resolve) so nothing is ever learned; and the **volume plane — full OHLCV to 2011 on ~1,500
> names — is used by zero signals.**

The consequence measured on the owner's own exemplars: run-capture of 21% / ~42% / ≤0%, surfacing
4-6 days after the system's own gates fired, into a page whose every loud field told the user not
to act.

**Corollary that reframes everything:** on the 2026-07-03 render, the board's top three are
*exactly* the owner's three exemplars, in order. Selection is approximately right. The program is
therefore NOT "find a new edge" first — it is **capture earlier, rank coherently, display honestly,
grade everything, and only then extend the signal set.**

---

## 2. Design rulings

Each ruling states the decision, the evidence, and what would overturn it.

### F1 — The board's spine becomes a three-shelf LIFECYCLE, not one flat list
**Decision.** Every name the screens admit is assigned exactly one stage, which is the loudest
element on the card and the partition of the board:
- **RIPENING** (the new shelf): W-tier setup forming — 2W washout state and/or 1W StochRSI bullish
  cross from a washout zone and/or 2W-MACD `approaching_up` with `bars_to_cross` ≤ threshold —
  entry cascade NOT yet fired. This is where 688306 lives before its cross, and where the owner
  front-runs. Explicitly labeled "setup forming — not an entry signal."
- **ENTRY** (the actionable shelf): fresh T1-T4 cascade fire (existing machinery) inside a live
  W-tier setup, low extension. This is the only shelf allowed to say BUY-family words.
- **RAN / LATE** (the honesty shelf): crossed and extended/rolled-off — rendered with the entry
  timestamp and the delta: *"signal fired N days ago, +X% since — late; wait for pullback or next
  base."* 603129-today lives here. HOLD-tracker basing names that haven't launched get re-promoted
  to ENTRY via the ported HOLD machinery (W6-C semantics), which is the validated re-admission path.
**Evidence.** Owner spec S1/S2 verbatim; the flicker history (names vanish at ticks=3 instead of
transitioning); 603129 surfaced on its last eligible bar; the three probes.
**Overturned if.** Forward grades show RIPENING names systematically fail to convert (stage
conversion rate ≈ base rate) — then RIPENING demotes to a chip and the shelf is cut.

### F2 — A W-tier SETUP layer computed from existing primitives
**Decision.** Per name, compute from `cycles._tf_state` on 2W/1W resamples + `confluence_tiers`
internals: 2W washout state, 1W k/d + bars-since-bullish-cross + zone-at-cross, 2W RSI-MACD
confirmed/`approaching_up`/`bars_to_cross`, base age and range position. This is spec S1. **No new
math is invented** — the probe reproduced all three owner reads with these exact calls (300725: 1W
cross 06-26 from d=9.3; 688306: 2W cross projected ~0.2 bars; 603129: 3D rolled off, 83% of range).
**Guardrails.** (a) The 2W-Friday staleness issue (washout-2w-lag) must be addressed at resample
time (partial-bucket handling) — the leakage harness's plane/bucket taxes extend to the W-tier.
(b) The falsified-H2 fixture from `BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md` §4 carries
over: pre-cross calm ≠ post-cross basing; the RIPENING shelf must be graded separately from HOLD
re-admission.
**Overturned if.** PIT replay shows the W-tier states repaint so badly they are untradeable
(bucket-completeness tax ≫ the 2D/3D equivalent).

### F3 — Fix the earliness inversion — but through the ledger, not by fiat
**Decision.** Stand up **stage- and tier-stratified forward grading first** (extend
`china_standout_track.append_board`/`grade`: tier is already logged, never stratified; add stage,
ticks, ext-since-cross, washout/coiled/hold flags, sector state). Bonus weights (washout +0.50 vs
COILED +0.25 vs FIRE 0) are then recalibrated from accrued grades; the specific hypotheses to
grade: (i) COILED deserves ≥ washout's weight, (ii) washout's bonus should decay by bars-since-fire
(it fires post-run — 06-29 on 603129, after +14.6%), (iii) ENTRY-shelf names beat RAN-shelf names
on 21d CSI300-relative excess. First grades mature ~2026-07-29 (ledger began 06-30).
**Why not recalibrate now:** the owner's exemplars are n=3; the repo's discipline (bonus/chip first,
gate power earned) exists precisely for this.
**Overturned if.** The ledger matures and shows the current weights are already optimal (unlikely
given the firing-order evidence, but the ledger decides).

### F4 — Narrative confluence as a CONFIRMER layer, seeded from #1054
**Decision.** Wire per-name narrative tags into the board (log-first, display chip + ledger
column): (a) THS concept membership + concept heat (20d rel, breadth) — fixing the dead TWD join
(300725 showed "no data" inside a +18.9% theme) and the membership hole (603129 has zero THS
concepts); (b) the shipped `china_narrative_radar` (#1054) per-basket state incl. the validated
global-AI confirmer with its honesty tags; (c) later, a general global-sector→CN read-through leg
(healthcare-worldwide→CN-pharma) modeled on the validated AI-semis→CPO precedent (t=3.27).
Owner doctrine (OWNER_RATIONALE §2) is the design law: **technicals detect, narrative confirms —
never the reverse.** Narrative heat never creates admission; it tiers conviction (S4: A-tier =
technical setup × narrative heat).
**Overturned if.** Ledger shows narrative-tagged ENTRY names don't outperform untagged ones
(then it stays a context chip, costing nothing).

### F5 — Rebrand the product to its true archetype; give reversal its own honest home
**Decision.** The board's copy, headline metaphors, and trust text describe the **washout→base→
turn** playbook (which is both what the machinery surfaces and what the owner trades). The
validated **quarterly within-sector reversal** becomes a separate, honestly-framed sleeve page
("periodically rebalanced contrarian basket — size small, high variance, NOT act-now picks"),
resolving the §8.1/§8.2 tensions of the brainstorm: don't gate the board on rev_z, don't shrink
the basket to 5 names. The board-vs-edge overlap (1/110) stops being a contradiction when they are
two products.
**Evidence.** rev_z negative on 2/3 exemplars; every reversal refinement falsified; the edge's
validated unit is basket/monthly, not name/day.

### F6 — Display reconciliation: one loud field, one truth
**Decision.** (a) The lifecycle stage is the card's single loud field; (b) a **"why ranked here"
chip renders the actual blend terms** (tier, washout, coiled, ext — the formula is exactly
reproduced, so this is cheap and truthful); (c) contradiction invariants at build time: no
BUY-family wording outside the ENTRY shelf; no green banding on a name whose entry gauge says
hold; the extended-chip (77/110) collapses into the stage; (d) the per-stock JSON cadence bug
(lookup page showed 77/"constructive" vs card 26/"Watch" for 603129) fixed by same-build stamping
or an explicit as-of banner on click-through.

### F7 — The volume program (the biggest untapped asset)
**Decision.** Phase-0s, in EV × buildability order from the signal-research ledger: (1) **abnormal
turnover / turnover-shape** (documented A-share long leg +1.24%/mo t=3.35; build off
`china_stocks_raw` — append-only, survivorship-clean — NOT the trimmed `china_search` panel);
(2) **MAX/lottery AVOID screen** (cheap, defensive); (3) **margin-velocity** risk leg after a daily
backfill starts accruing; (4) volume-price divergence at bottoms (guarded: adjacent "volume
dry-up" is FALSIFIED-H4 — the test is divergence, not dry-up). Orthogonality vs reversal is the
first gate for each (the bounce-timing latent factor is shared).
**Also surface, don't re-derive:** deep-discount block trades (+3.45%/21d, accruing) and
earnings-guidance drift — validated/validating legs with no board presence.

### F8 — Feeder wiring (sector → picker), display-first
**Decision.** (a) Ship the 3-line **sector first-tick-up** read (forward_log: phase==Trough &
osc_slope>0 — flags Agriculture + Pharma today, corroborating the owner's healthcare call) as a
per-name sector chip + ledger column; (b) call the fully-built-never-called
`compute_china_ths_confluence` in a build script → THS concept T3/T4 states as theme context;
(c) **diagnose gate_factor stuck at 0.2** (212/212 calls — Accumulate unreachable; bug vs honest
perma-risk-off decides whether sector_central needs repair or relabeling); (d) rank influence
(a sector-state bonus in `_cn_bonus`) only AFTER the ledger grades the chip (F3 discipline).
Regime stays at sleeve/sizing level, never a per-name veto (§8.3 tension honored).

### F9 — Substrate repairs are prerequisites, not chores
The specific rot that poisons everything downstream, each with a named fix in W0/W1:
dead validation grader (0/120 tickers resolve — fix store-group resolution) · freshness contract
(`as_of` 07-03 board shipping `signal.asof` 07-02 signals; live recompute says 603129 ineligible
while the board says T1 ticks=2) · tier_stream-vs-scalar-cascade label discrepancy · board-width
flapping (n=110→46→11→110 across 06-25..06-30 renders — coverage-drop guard needed) · THS
membership coverage (603129 in zero concepts) · adjusted-close seams (raw+adjusted plane contract)
· LHB historical backfill (~21k events available, enables LHB phase-0) · QVIX 5-day staleness.

### What I explicitly REJECT (the adversarial layer)
- **rev_z as the inclusion gate** — the exemplars prove the archetype isn't reversal; F5 gives
  reversal its own home instead.
- **Shrinking the board to a top-5** — breadth is load-bearing for a weak-edge product; shelves +
  tiers (F1) deliver the "small high-confidence surface" without destroying breadth.
- **A hard shared-regime veto at name level** — the dip archetype is strongest in risk-off; regime
  gates sizing and banners only.
- **Recalibrating bonuses by fiat now** — n=3 exemplars; the ledger (F3) decides.
- **Limit-up/lianban continuation as a buy signal, volume dry-up filters, turn-confirmation
  quality floors on reversal** — all falsified; they stay dead (do-not-rerun ledger,
  `phase1/phase0-verdicts.md`).

---

## 3. Wave plan

Ship-shape for every wave: chip/log first → tests → verify → PR (standing approval), PROGRAM.md
status log updated. Model routing: Fable orchestrates; Opus designs/reviews; Sonnet executes.

**W0 — Repair + honesty (no research; recipes complete).**
1. HOLD port CN (exact insertion points in `us-port-mechanics.md`; CROSS_MAX_AGE suspension caveat).
2. Tier+stage-stratified grading: extend `append_board`/`grade`; add tier to US grader's record too.
3. Fix the dead validation grader (store-group resolution).
4. gate_factor diagnosis + fix (or honest relabel).
5. TWD/THS theme-join fix + membership coverage audit.
6. Freshness contract: one as-of for board + signals; reconcile tier_stream vs scalar cascade.
7. Board-width guard: refuse to publish a render whose row count collapses >40% day-over-day
   without an explicit data-outage banner.
8. Per-stock JSON cadence sync or click-through as-of banner.
9. Page copy rewrite to the true archetype (F5, copy only in W0).
10. Sector first-tick-up chip + ledger column (F8a).

**W1 — The W-tier setup layer + lifecycle shelves (the flagship).**
`engine/setup_tier.py` (W-tier states from `_tf_state` on 2W/1W + base-age/range) → stage
assignment (RIPENING/ENTRY/RAN-LATE) → board partition + card redesign (F6: stage loud, why-ranked
chip, invariants) → every stage logged in the ledger. PIT bucket-tax measured for W-tier states.
Test fixtures: 688306 must appear on RIPENING before its cross; 603129-today must read RAN/LATE
with "entry was 06-24/+X%"; 300725 must read ENTRY. Regression: a JNJ-style blasted-off name must
never reach ENTRY.

**W2 — Narrative confluence layer (F4).** Per-name narrative tags from THS heat + #1054 radar;
A/B conviction tiers (S4); healthcare read-through phase-0 (global XLV state → CN pharma names) as
the second read-through leg.

**W3 — Volume program phase-0s (F7).** Abnormal turnover → MAX screen → margin backfill + LHB
backfill; orthogonality harness vs reversal; registry entries for every verdict.

**W4 — Feeder fusion.** Sector-state and THS-confluence chips (accrued by now) evaluated for rank
bonuses; empirical-Bayes pooling across the tiny-n graders (brainstorm §7) if grades are too thin.

**W5 — The reversal sleeve page (F5).** Honest basket product: monthly rebalance, EW-relative,
size-small framing, fill-realistic grades on its own ledger.

**W6 — Ledger-driven recalibration (F3).** Bonus weights, washout decay, stage weights, board-width
regime modulation — all from ≥21d matured grades (earliest ~07-29).

**W7 — Cross-market port.** The validated pieces of W1-W6 evaluated for HK/Canada per the port map
(HK failed COILED — do not force; Canada is momentum-led — weights re-derived, never copied).

---

## 4. Measurement constitution

- **Benchmark:** CSI300-relative excess, always. **Fill realism:** T+1 (H+L)/2 entry, locked-limit
  exclusion (already in `china_standout_track` — extend, don't rebuild). Close-to-close overstates
  by ~0.9-1.1pp/entry (measured); report both.
- **Stratification:** stage × tier × washout/coiled/hold × narrative-tag × sector-state. Count-fair,
  per-fire; stop-out / clean-liftoff / dead-money axes for anything durable-bottom-adjacent
  (COILED's constitution), return axes for shelf performance.
- **Survivorship:** all new backtests on `china_stocks_raw` (append-only); `china_search`-derived
  stats are labeled UPPER BOUNDS.
- **Leakage:** shadow_pit harness extended to W-tier states and cascade freshness (the known gap).
- **The acceptance-gate readout (how the owner's exit question gets answered):** (1) ENTRY-shelf
  21d hit rate + excess vs board base rate; (2) run-capture % on future exemplar-grade names
  (baseline measured: 21%/42%/0%); (3) RIPENING→ENTRY conversion rate; (4) RAN/LATE demotion
  honesty (does the late shelf underperform ENTRY — if not, the freshness doctrine itself is
  wrong and gets revisited); (5) zero build-time contradiction-invariant violations.

## 5. Open items ledger
- O1: 2W partial-bucket repaint tax — measure in W1 before trusting RIPENING intraweek.
- O2: which grader is the dead one (validation vs name_score) — W0.3 diagnosis names it precisely.
- O3: COILED-CN citation: validated on liftoff/stop axes (n=10,784), NOT forward returns — keep
  grading on those axes; do not quote it as return alpha.
- O4: reversal 0.58 Sharpe unreproducible (closes_deep absent) — the sleeve page (W5) re-derives
  on the raw plane before advertising any number.
- O5: owner exemplars are n=3 ground truth for *design*, not *validation* — the ledger validates.

## 6. Execution protocol
Fable = orchestrator + adjudicator. Each wave: one workflow (Opus design/review, Sonnet build),
tests + verify + PR per standing approval, PROGRAM.md status log append, memory update at phase
boundaries. Any wave whose forward grades refute its premise is rolled back, and the refutation is
recorded in the phase-0 verdict ledger — refutations are deliverables, not failures.
