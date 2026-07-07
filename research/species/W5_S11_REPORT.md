# W5 S11 Phase-0 Report — Buyback-Floor Washout (US quarterly-EDGAR × baskets panel)

*2026-07-06 · prereg: research/species/W5_S11_PREREG.md (committed before the run,
commit f1dd1e6729) · harness: scripts/s11_buyback_floor_phase0.py · raw:
research/species/_s11_phase0_out.json · trial family `s11_buyback_floor` (m=2,
declared in data/trial_ledger.jsonl before the first spread). Data extension:
scripts/backfill_edgar_quarterly.py re-crawled 2026-07-06 (net_debt columns; 0
fetch failures, 1,502 filers, 62,240 ticker-quarters).*

## Verdict

**S11 is FALSIFIED at phase-0 and CLOSED.** On 9,392 matured washout-at-filing
fires (n ≥ 300 per side in both configs — the power floor was the *only*
pre-registered gate that passed), the clean buyback-floor arm is **statistically
indistinguishable from washout-without-a-buyback**, and the effect is sign-unstable
and name-minority. Per the pre-registered kill path (stop-out spread ≤ 0 **or**
sign-unstable **or** q > 0.10), `validation_status` is transitioned **phase0 →
falsified** (terminal). This is landed directly (a falsification is a
de-escalation); no promotion is proposed.

The registry hypothesis — *a realized share-count decline during a washout provides
a buyback floor that improves entry quality* — does not survive its first honest
test. Realized buybacks into a washout neither reduce stop-outs nor buy cleaner
liftoffs relative to washed-out names that are **not** buying back.

## Primary — clean fire (A) vs control (C) at `clean15_126` (positional)

Stop-out spread is stated as **C − A** (positive = the registered *favourable*
direction: fire stops out less). Requirements to advance were ALL of: spread ≥ +5pp
in both configs, all-three-axes sign-correct, BH q ≤ 0.10, n ≥ 300/side, both halves
sign-stable, per-name majority > 50%.

| config | A (clean) n / stop% | C (control) n / stop% | **stop spread** | cushion@21 spread | episode p | BH q | halves (H1/H2) | per-name majority |
|---|---|---|---|---|---|---|---|---|
| any_decline (<0) | 2,740 / 64.20 | 5,848 / 64.45 | **+0.25pp** | +2.85pp | 0.366 | 0.677 | −2.94 / +3.06 ✗ | 43.6% of 436 ✗ |
| material (≤−1%) | 1,068 / 65.73 | 5,848 / 64.45 | **−1.28pp** | +1.03pp | 0.677 | 0.677 | −5.73 / +2.60 ✗ | 36.7% of 210 ✗ |

**Every discriminating gate fails.** The headline stop-out spread is +0.25pp
(noise) at the loose threshold and turns **adverse (−1.28pp)** at the material
threshold; neither approaches the +5pp floor. The episode-clustered bootstrap CIs
straddle zero ([−3.02, +3.43] and [−6.36, +3.63]); BH q = 0.677 for both. Both
configs flip stop-out-spread sign across time halves, and in both the per-name
majority is a *minority* (43.6% / 36.7% of names with ≥2 fires per side show the
fire stopping out less). Dead-money is ≈0% on both arms (washed-out names are
volatile — they resolve to a ±barrier within 126d), and clean-liftoff is a flat
~33% regardless of the buyback.

## The material-threshold inversion (informative)

Tightening the trigger to *material* declines (≤−1%, i.e. bigger realized
buybacks) makes arm A **worse**, not better — stop-out 65.73% vs 64.20% at the
loose threshold, and vs 64.45% control. The "bigger buyback = stronger floor"
intuition is inverted: aggressive realized share reduction into a washout is, if
anything, a name buying into a decline that keeps declining. This is the same
family of lesson as the graveyard's H1 ("raw washout depth works only through the
cohort lens") — *magnitude of the raw stimulus is not conviction*.

## Secondary / context — the debt-funded rejection rule (its premise holds)

The one place the data separates is exactly where the registry said the failure
mode lives. Arm **B** (debt-funded: net debt rising concurrent with the buyback):

| config | B (debt-funded) stop% | A (clean) stop% | C (control) stop% |
|---|---|---|---|
| any_decline | 64.68 (n=804) | 64.20 | 64.45 |
| **material** | **70.82 (n=377)** | 65.73 | 64.45 |

At the material threshold, **debt-funded buybacks stop out 6.4pp more than control
and 5.1pp more than clean buybacks** — the "leveraging up to buy back shares in
distress" failure mode is real and directionally confirmed. But this *validates the
demotion, not the species*: removing arm B does not lift arm A above control. The
`net_debt`-confirmed-clean sensitivity (Δnet_debt ≤ 0 *observed*) tells the same
story (any: 63.90% n=795; material: 64.92% n=248 — no edge). **"Buyback in washout"
ranges from neutral (clean) to harmful (debt-funded); it is never a floor.**

## Honesty / caveats

- **This is a null, not a thin sample.** 9,392 graded fires; A and C both clear
  300/side comfortably in both configs. The kill is powered, not undecided.
- **`net_debt` coverage bounds the demotion to the observable subset.** EDGAR
  yields `net_debt` for 51.0% of ticker-quarters (cash 90.6%, long_term_debt 44.0%,
  current_debt 40.2%); the debt-funded demotion therefore fires only where both
  quarters' net debt is tagged (~40% of decline fires). Per the literal rule, a
  fire is demoted **only** on observed rising net debt — so arm A still contains
  net-debt-unknown fires; the confirmed-clean sensitivity above isolates the
  observable subset and shows no edge either. `net_debt` uses cash =
  `CashAndCashEquivalentsAtCarryingValue` (equivalents only, not marketable
  securities) — a conservative proxy that can over-flag "net debt rising" for a
  name shifting cash into securities; that error only *purifies* arm A, so it does
  not manufacture the null.
- **Q4 balance data is ~absent in EDGAR** (10-Ks tag fiscal-year, not Q4): the
  store carries 54 Q4 rows vs ~18k each for Q1–Q3. QoQ Δshares is therefore the
  within-year Q1→Q2 / Q2→Q3 transitions (consecutive `period_end` gap ∈ [60,130]d);
  Q3→Q1 and Q4 buybacks are not graded. A coverage bound, printed.
- **Survivorship:** the baskets panel carries the current-membership bias of every
  basket study — delisted names that washed out and never recovered are
  under-represented, which if anything flatters the liftoff side. Printed, not fixed
  (phase-0 is display-only).
- **`shares` coverage = 60.2%** of ticker-quarters (37,475/62,240); stable across
  recent years (~63% in 2024–26 — the "NaN on newest filings" is name-specific to
  dei-only filers, not a temporal cliff, and is immaterial here since the latest
  ~126 trading days of fires are dropped for non-maturity regardless).

## Leak audit

- **PIT fire date = `filed`** — the share-count and net-debt are public only at the
  filing; washout arming is evaluated on `close[:filed]` (causal, `coiled.washout_ctx`,
  ≥308 bars); the fill is the first close **strictly after** `filed`
  (`grading.fill_index`, next-bar — never same-bar, never a §7 marker date).
- **126-day maturity is enforced by the grader** — `terminal_state` returns None
  without 126 forward bars, so unmatured recent fires are dropped (no look-ahead).
- **Wait-cost (§1.2):** arms A, B, C all fire at the identical filed-date /
  next-bar convention *inside* the washout, so the confirmation wait is symmetric —
  the A−C marginal is wait-priced by construction; C is the wait-matched baseline.
- **Multiplicity:** m=2 declared in the trial ledger before the first spread;
  episode-clustered p over 6-calendar-month blocks (≥ the 126-day forward window,
  §1.2 — wider than S6's monthly blocks, 22 blocks); BH-FDR across the family.

## Registry / gating updates shipped with this report

- **S11 `validation_status`: `phase0` → `falsified`** (terminal; `deployment_status`
  stays `unshipped`). `gating.maturation` records the kill with the numbers and PR.
- **§1.6 graveyard** gains the construction (binding; re-derivation = automatic wave
  failure): *realized share-count decline as a within-washout entry-quality
  stratifier — null (stop-out spread +0.25/−1.28pp, sign-unstable, name-minority,
  q=0.68); debt-funded variant confirmed adverse.*
- **§8 status row** added (FALSIFIED verdict, this PR).

## In plain English

We asked: when a washed-out stock is *actually shrinking its share count* (real
buybacks, not press releases), is that a floor — does it get stopped out less or
lift off cleaner than washed-out stocks that aren't buying back? Across ~9,400
signals over a decade: **no.** The buyers-back and the non-buyers-back stop out at
the same ~64% rate and lift off at the same ~33% rate; the tiny gap flips sign
between the first and second halves of the period and disagrees across most
individual names. Buying back *harder* (bigger reductions) is slightly worse, not
better. The one thing that *is* true is the warning the registry already carried:
companies that borrow money to buy back shares while they're washing out stop out
the most (71% vs 64%) — but cutting those out doesn't rescue the rest. So the idea
is closed: a realized buyback into a washout is not a floor. We keep the debt-funded
lesson and the data plumbing; the species is retired.
