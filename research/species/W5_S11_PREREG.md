# W5 S11 Phase-0 Pre-Registration — Buyback-Floor Washout (US quarterly-EDGAR × baskets panel)

*2026-07-06 · Setup-Species program §4 Tier C S11, §7 W5+ · registered BEFORE the
run (this file's commit precedes the harness run and the report). Expectations are
held open — the registry ships S11 at `phase0/unshipped`, and a clean kill is
acceptable and pre-authorized (§1.2: failed = permanently closed in §8).*

## Species under test

**S11 v1.0 — Buyback-Floor Washout.** Horizon class **positional** (frozen at
registration; promotion keys on `clean15_126`, +15% before −5% within 126 trading
days). Mechanism (registry, verbatim intent): a name that is *actually shrinking
its share count* while in a washout provides a **buyback floor** — realized
buyback (not an announcement) is management deploying capital at a price it deems
cheap. Keys on **realized QoQ share-count decline** from the EDGAR quarterly store;
never on announcements. **Debt-funded buybacks are the named failure mode** — the
registry rejection rule demotes to *context only* any fire where net debt is rising
concurrent with the buyback (leveraging up to buy back shares in distress).

## Adjacent-falsified (nearest dead neighbours, why S11 differs)

- **Raw washout depth as a boost (H1) — "works only through the cohort lens"**
  (§1.6 WAVE1 §2). S11 does **not** claim the washout; the washout is the
  *population/arming context*, identical across both arms. The **signal** is a
  corporate action (realized net share reduction) used as a **within-washout
  stratifier** — mechanically the S6 design (a marker evaluated *inside* the
  washed-out set), not a depth boost.
- **52w-high×volume breakout alpha** (§1.6 NOVEL_IDEAS §3) — S11 is a washout
  *bottom* species, opposite side of the tape.
- **Timing as return-alpha** (§1.6 ENGINE_FIX) — S11's verdict is the §1.1
  terminal-state safety partition, never a return series; returns are printed as
  context only.

## Construction (fixed — nothing re-tuned after seeing outcomes)

- **Fundamentals:** `data/edgar/statements_quarterly.parquet` (re-crawled 2026-07-06
  to add `long_term_debt`, `current_debt`, `cash`, `net_debt`; FY2009–2027,
  1,331 names). `shares` = us-gaap `CommonStockSharesOutstanding` (quarter-end
  instant); `net_debt` = `long_term_debt + current_debt − cash` (cash =
  `CashAndCashEquivalentsAtCarryingValue`; None only when no debt tag is present).
- **Price panel:** `data/baskets/ohlcv/{ticker}.parquet` — split-adjusted daily
  OHLCV, ~2014→2026, covering 1,036 of the 1,331 EDGAR names (the same store S6
  used). Carries the current-membership survivorship bias of every basket study;
  **printed, not fixed here** (phase-0 is display-only).
- **PIT fire date = the `filed` date.** A quarter's share-count and net-debt are
  only public when the 10-Q/10-K is filed; both the trigger and the debt-funded
  test are evaluated as of `filed`. This is the *only* look-ahead-free anchor.
  Washout is evaluated on `close[:filed]`; the fill is the first close **strictly
  after** `filed` (`engine.grading.fill_index`, next-bar convention, §1.2 — never
  same-bar, never a §7 marker date).
- **Washout arming state** = `engine.coiled.washout_ctx(close[:filed])` — the
  validated wave-1 multi-TF washout (True iff a ≥15% capitulation trough occurred
  in the trailing 91 bars vs its prior-126-day high; needs ≥308 bars, else None).
  Unchanged; no new knob.
- **Trigger = realized QoQ share-count decline.** `Δshares = shares[Q]/shares[Q−1] − 1`
  using consecutive fiscal quarters for the same ticker (Q−1 is the immediately
  prior fiscal quarter present in the store). Both must be non-null. Announcements
  are never used.
- **Debt-funded demotion (the rejection rule).** `Δnet_debt = net_debt[Q] − net_debt[Q−1]`.
  A fire with `Δnet_debt > 0` (net debt rising concurrent with the buyback) is
  **demoted to a context bucket** and excluded from the primary fire arm. Per the
  literal rule, a fire is demoted **only when rising net debt is observed**; a fire
  with `Δnet_debt ≤ 0` **or** with net_debt unavailable is *not* demoted (a
  net_debt-confirmed-clean sensitivity is reported alongside).
- **Outcomes:** `engine.grading.terminal_state` at `clean15_126` (positional
  primary, shared one-grader constants) + `engine.grading.cushion_incidence`
  (competing-risk cumulative cushion at k∈{5,10,21}). A fire grades only when 126
  forward bars exist (unmatured recent fires return None and are dropped — this
  auto-enforces no-look-ahead maturity). The full both-class grid (clean8_21 too)
  is printed as context per §1.1; **promotion keys only on the declared positional
  class.**

### The three-way partition of washout-at-`filed` fires (per config)

| arm | definition | role |
|---|---|---|
| **A — clean buyback fire** | washout ∧ (share decline) ∧ ¬(Δnet_debt > 0) | **primary fire arm** |
| **B — debt-funded (demoted)** | washout ∧ (share decline) ∧ (Δnet_debt > 0) | context only |
| **C — control** | washout ∧ (Δshares ≥ 0) | **primary control arm** |

## Registered trials (family `s11_buyback_floor`, m = 2)

One knob — the share-decline threshold — at two pre-declared values. No threshold
search; any third value is a new §8-recorded trial. Control C = washout ∧ Δshares ≥ 0
is **fixed** across both.

| trial | `share_decline` threshold (defines arm A/B) |
|---|---|
| 1 | `any_decline` — Δshares < 0 |
| 2 | `material_decline` — Δshares ≤ −0.01 (−1%) |

Proportion primary → **no DSR** (§1.2: proportions cannot be DSR'd). The multiplicity
controls are the episode-clustered p-value + BH-FDR across the registered family
(m=2, taken from the trial ledger via `register_trials("s11_buyback_floor", budget=2)`,
logged before the first spread is computed). The wave-level BH roll-up folding S10's
concurrent trials is an orchestrator/monthly-review step (padding unknown siblings at
p=1.0 only *tightens* the threshold — noted, not pre-empted here).

## Primary verdict (registered) — A vs C at `clean15_126`

The §1.1 safety-net partition; the §1.3 flip axes are **stop-out** (STOPPED %),
**dead-money** (DEAD_MONEY %), and **cushion incidence** (cumulative, k=21d). To
call S11 REAL (→ *propose* advancement; never self-advanced):

1. **Sign:** in BOTH configs, arm A beats arm C on **stop-out** (A lower) AND
   **dead-money** (A lower) AND **cushion incidence @21d** (A higher).
2. **Magnitude:** the headline **stop-out spread** (C − A, favourable) ≥ **5pp** in
   both configs (the §1.2 promotion floor, applied to the safety headline).
3. **Significance:** one-sided episode-clustered p on the stop-out spread (circular
   block bootstrap over **6-calendar-month** episode blocks — blocks ≥ the 126-day
   forward window per §1.2, B=2000) with **BH-FDR q ≤ 0.10** across the family.
4. **Power floor:** n ≥ **300 per side** (A and C) in both configs.
5. **Stability:** both time halves sign-stable on the stop-out spread.
6. **Per-name majority:** > 50% of names with ≥2 fires on each side agree in sign
   (A stop-out < C stop-out) per name.

Wilson 95% lower bounds are printed on every A/C rate (`engine.grading_stats.wilson_ci`);
the §1.3 flip is credited only where A's advantage survives the Wilson LB at the
episode-clustered n floor. Multi-horizon benchmark-relative returns and `ret_at_read`
are **context, never the verdict** (§1.1 banned-verdict list).

## Secondary / context (cannot promote)

- **Debt-funded rule check:** arm **B** (debt-funded) vs arm **A** (clean) on the
  same axes — expectation B underperforms A (worse stop-out), which *validates* the
  demotion. If B ≈ A or B beats A, the rejection rule earns a §8 caveat.
- **net_debt-confirmed-clean sensitivity:** A restricted to fires with `Δnet_debt ≤ 0`
  *observed* (drops net_debt-unavailable fires) — bounds the demotion's coverage cost.
- **Archetype/sector context:** a financials-excluded cut and a GICS-sector split
  printed as context (S11's triggers are raw balance-sheet levels, not the margin
  *ratios* behind the registry's "financials hostile" note — so financials are a
  context stratum here, not a hard primary filter; deviation surfaced per §5.2).

## Pre-registered outcome paths

- **All six requirements met in both configs** → S11 clears the pre-registered
  gate. Per house law (LLMs may only de-escalate; promotions pass human review) the
  run **PROPOSES `phase0 → accruing`** in the report and leaves `validation_status`
  unchanged for the owner to ratify. Nothing ranks, sizes, or gates from this run.
- **Stop-out spread ≤ 0, or sign-unstable across halves/configs, or q > 0.10** →
  **S11 CLOSED / falsified**, recorded permanently in §8 (a clean kill, landed with
  this PR; the graveyard gains the construction).
- **n < 300 per side** (either arm, either config) → **UNDECIDABLE at the registered
  floor**: S11 stays `phase0`, `come_back_on` keyed to forward ledger accrual. No
  threshold loosening — the floor is the floor.

## What this phase-0 does NOT do

No gates (§1.5 assert-no-gate — S11 is a *stratifier* candidate, not a gate). No
board wiring, no sizing, no return-axis verdict. No self-advance of
`validation_status`. Survivorship (current-membership basket bias) and the
`net_debt` proxy limitation (cash = equivalents only, so a name shifting cash into
marketable securities can spuriously read as "net debt rising" and be demoted — a
*conservative* error that only purifies arm A) are **printed, not fixed here.**
