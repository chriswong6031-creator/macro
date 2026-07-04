# W1 S13 Phase-0 Pre-Registration — US Within-Sector Reversal Sleeve

*2026-07-04 · Setup-Species program (research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md §4 S13,
§7 W1) · registered BEFORE first run (this file's merge commit precedes the report).*

## Species under test

**S13 v1.0** — US Within-Sector Reversal Sleeve. Horizon class **rotational**
(frozen at registration; promotion keys on `clean8_21`, the positional grid prints
as context only). Product-unit species: a monthly EW portfolio, NOT a per-name
act-now overlay (the same carve-out the CN sleeve enjoys — adjacent-falsified
"timing as return-alpha" does not apply to portfolio units).

**Mechanism story (registered):** within-sector overreaction. The deepest
within-sector losers over a short formation window mean-revert; sector-neutrality
removes the industry-momentum component (Moskowitz–Grinblatt) that makes RAW
losers momentum-shorts. CN precedent: the validated CN sleeve (+0.56%/mo) DIED
under every timing/confirmation gate → `assert_no_gate` is an invariant here, and
this phase-0 tests whether the no-gate law holds for US rather than assuming it.

**In-repo seed (why this is registered at all):** sector-neutral 1M reversal
IC −0.046 (t −9.5) full-history on the deep panel
(research/RESIDUAL_ALPHA_MOMENTUM.md), WITH the two decay signals carried as kill
criteria below.

## Data (all existing; no new fetches)

- Prices: `data/breadth/_closes_deep.parquet` (1,498 names, 1962→2026-06)
  UNION `data/breadth/_closes_delisted.parquet` (the recovered delisted names).
- Membership: `data/breadth/sp500_pit_membership.parquet` (PIT intervals, 1996→).
  Each rebalance restricts to actual members THEN (`--pit` semantics of the seed
  study). **Primary window = the PIT era (1996-07 → last full month).**
  Pre-1996 has no PIT membership: any pre-1996 numbers print as
  SURVIVORSHIP-BIASED CONTEXT only, never the verdict.
- Sector map: `equity_factors._names_sectors()` — **current** GICS sectors
  applied to history (non-PIT; same construction as the seed study). Disclosed
  limitation, carried into the report's leak-audit section.
- Benchmark: SPY total-return close (yahoo store / broad cache).
- Survivorship honesty (§1.2): per-rebalance member-price coverage % printed;
  the known bound — catastrophic losers Yahoo no longer serves (LEHMQ, ENRNQ,
  WAMUQ, BSC) are ABSENT, so results are optimistic — is restated in the report.

## Construction (FIXED except the registered grid)

Monthly rebalance at month-end close **t**. Universe: PIT members at t with a
price at t and at t − formation. Formation return = close_t / close_{t−f} − 1.
Within each GICS sector with ≥ 5 eligible names: rank by formation return;
**sleeve = deepest quintile** (lowest formation return), equal-weight.
**Fills honor §1.2 (never same-bar): entry = first close STRICTLY AFTER t;
exit = first close strictly after the next rebalance t′.** A name with no exit
print grades at its last available close (delisting = the honest loss).
Hygiene-only eligibility (price coverage). **assert_no_gate:** the harness
enforces (hard assert) that no timing/confirmation/regime key exists in the
config — the §1.5 law.

## Registered config grid (trial ledger family `s13_reversal_sleeve`)

| trial | formation f | everything else |
|---|---|---|
| 1 | 21 trading days (1M — the US-evidence frame) | fixed as above |
| 2 | 63 trading days (3M — the CN-construction frame) | fixed as above |

m = 2 configs. Logged to `engine/trial_ledger` BEFORE the run; `deflated_sharpe`
uses n_trials = 2. No other knob is searched; any post-hoc variation is a new
§8-recorded trial.

## Primary verdict metric (registered)

**Sleeve monthly excess return vs SPY over the PIT era**, per formation config:
- mean monthly excess, Newey-West HAC t, **deflated Sharpe (n_trials=2)** with
  `dsr_verdict`, and `block_bootstrap_ci` (episode blocks ≥ the 1-month forward
  window). Effective-n = # rebalance dates (episodes), printed beside every rate.
- Safety-net axes printed beside it (context + flip-criteria basis, §1.1): the
  per-fire terminal-state partition at **clean8_21** (primary class) and
  clean15_126 (context grid), stop-out / dead-money / cushion incidence with the
  all-fires denominator.

## Pre-registered kill criteria (from the species registry, checked in order)

- **K1 (modern-era decay):** modern era = 2002-01 → 2026-06. If the sleeve's
  modern-era mean monthly excess ≤ 0, or its DSR verdict fails, for BOTH
  formation configs → **NO-GO** (species closed in §8; registry →
  `validation_status: falsified`).
- **K2 (2024–26 mega-cap sign flip):** if K1 passes but the 2024-01 → 2026-06
  sub-window excess is negative while the pre-2024 modern era is positive, the
  species does NOT die — it is REGIME-SCOPED: `mega-cap-dominance` recorded as a
  hostile cell (already hypothesized in the registry), and any shipping surface
  must carry the regime caveat. Recorded either way.
- **K3 (Tencent-trap concentration):** if any single name contributes > 50% of
  the PIT-era cumulative sleeve excess → flag; the sleeve cannot promote past
  display until an anti-concentration rule is separately registered.
- **K4 (sign sanity):** within-sector monthly rank-IC of formation return vs
  forward month must be NEGATIVE over the PIT era (reversal, not momentum). A
  positive full-era IC with a "profitable" sleeve = construction bug, not edge.

## What this phase-0 does NOT do

No gates tested (banned). No promotion — a passing phase-0 leaves S13 at
`validation_status: phase0` with the evidence attached; promotion runs the §1.3
ladder separately (display chip first). No board wiring. No sizing. Returns are
context beside the safety-net axes per §1.1 — but per §1.2(5) the sleeve is a
legitimate return-series leg, so DSR applies to it (this is the CN-2 pattern).

## Report contract

`research/species/W1_S13_REPORT.md` with: per-config primary table, era splits,
all four K-criteria verdicts, the full both-class horizon grid, coverage/
survivorship lines, leak-audit section (fill rule, sector-map non-PIT, known-date
mapping), and the §8 row. Registry updates: `gating.come_back_on` cleared or
re-set; `trial_count` unchanged (grid within the registered budget).
