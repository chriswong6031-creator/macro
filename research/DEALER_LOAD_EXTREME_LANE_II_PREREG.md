# dealer_load_extreme — Lane-(ii) Pre-registration Addendum (P2 / RIC Program)

**Program:** Rates-Inflation-Command (RIC). **Wave:** W4 EVW addendum.
**Pre-reg PR:** feat/ric-w4-evw. **Status:** PRE-REGISTERED — committed BEFORE any attempt.
**Author:** quant research agent. **Date:** 2026-07-17.

**Governing law:** RIC §2 (no calendar/event-window-gated risk-radar legs — FORBIDDEN outright,
DO_NOT_REBUILD.md §4), RIC-R3 (no-dampener law), masterplan §6.2 (Lane-(ii) pre-reg protocol).

---

## 1. Background and legal context

The P3 event-window engine (W4) surfaces calendar phases as **display context only** (RIC-R6,
`is_context_only=True` throughout). The judge-panel ruling of 2026-07-13 STRUCK the originally-
drafted event_window Tier-B `_SCARES` leg: any calendar-gated leg at any tier advances radar STATE
via `_gross_for`, making event proximity a contributor to sizing — the exact mechanism MRI-R3 and
DATA_SIGNAL_EXPANSION_2026 #11 forbid. Therefore NO event or OPEX proximity signal may ever enter
`_SCARES`.

The one **lawful future risk-channel candidate** identified by the panel is `dealer_load_extreme`:
a **CALENDAR-AGNOSTIC** signal that fires whenever dealer books are at an extreme — OPEX week or not.
Because it is agnostic to the calendar, it is not a laundered version of the forbidden calendar-gated
leg. Its pre-registration is required under masterplan §3 (Lane-(ii) attempts need a frozen prereg)
before any evidence is examined.

---

## 2. Signal definition (exact, calendar-agnostic)

`dealer_load_extreme` fires when the magnitude of the dealer-load composite is at or above the 90th
percentile of its own history, regardless of the calendar position. Formally:

```
dealer_load_extreme = True  iff  max(|net_vex|, |net_cex|) >= P90(history)
```

where:
- `|net_vex|` = absolute net vanna exposure (dealer sign: long_call_short_put, unobservable —
  printed in every consumer per W2 passport)
- `|net_cex|` = absolute net charm exposure
- `P90(history)` = 90th percentile computed over the rolling or full options-surface history
  (data/options_surface/index_etf.parquet, index_etf root class: SPX, SPXW, SPY)
- **Sign-agnostic**: the magnitude is used — both extremes (large positive AND large negative
  dealer exposure) qualify. This preserves the non-directional spirit.
- **Calendar-agnostic**: the firing condition has no reference to the day of the week, FOMC dates,
  CPI dates, OPEX cycle position, or any other calendar marker.

---

## 3. Attempt window and data requirement

**Earliest attempt date:** ~2027-07 (when >= 12 months of options surface history exists
continuously from the W2 theta-ops launch, ~2026-07-17).

**Binding prerequisite:** `data/options_surface/index_etf.parquet` must have >= 252 trading days
of continuous coverage (verified via the accrual audit: `data/quality/options_surface_accrual_audit.json`
LIVE status required). The 2026-10-15 MRC review (masterplan §7 clock) is a readiness checkpoint
only; it does NOT advance the attempt without the surface-history prerequisite.

---

## 4. Lane-(ii) pre-registered protocol (frozen)

### 4.1 Hypothesis (primary, one-sided)

**H1 (forward RV lift).** Days when `dealer_load_extreme=True` are followed by materially higher
realized volatility over the next 5 trading days than the base rate:

```
E[RV_5d | extreme] > E[RV_5d | ~extreme]
```

**Primary metric:** forward 5-day SPY realized vol (annualized %). Direction: positive lift.
One-sided t-test with Newey-West HAC (lags=5).

**Primary gate:** `lift_2020 >= 1.20` — the ratio of RV_5d in extreme episodes vs non-extreme
episodes, measured on the 2020+ holdout slice only (not the construction window). The 1.20
threshold (20% RV lift) is PRE-REGISTERED here and may not be adjusted post-hoc.

### 4.2 Holdout and construction split

- **Construction window:** all surface data up to 2026-12-31 (used for P90 threshold fitting only).
- **2020+ holdout:** all surface data from 2020-01-01 onward where `dealer_load_extreme` fires.
  Since the store starts ~2017, this gives ~3 years of construction + ~3 years of holdout when
  the attempt window opens.
- If the store starts later (post-2017 confirmed coverage), the split is recalculated proportionally
  at attempt time — but the holdout is always the LATER half.

### 4.3 Frequency-matched permutation

To control for the possibility that `dealer_load_extreme` simply tags high-vol days (a tautology),
a frequency-matched permutation test is required:

1. Draw 10,000 random samples of the same size and day-of-week distribution as the `extreme` set.
2. Compute the RV lift for each permuted sample.
3. p-value = fraction of permuted lifts >= observed lift.
4. Gate: p < 0.05 (one-sided).

Both the HAC t-test gate AND the permutation p-value gate must pass.

### 4.4 Outcome classes

| Outcome | Condition | Action |
|---------|-----------|--------|
| GO | lift_2020 >= 1.20 AND HAC |t| >= 2.0 AND permutation p < 0.05 | Proceed to Lane-(iii) display-confluence per RIC-R3 |
| NO-GO | lift_2020 < 1.20 OR fails HAC/permutation gate | Remains display confluence; no risk-channel attempt |
| ACCRUE | < 12 months of surface history at attempt time | Defer; accrue ledger rows |
| KILL | Signal is time-varying and the 2020+ slice reverses sign | Close construction; register in DO_NOT_REBUILD.md |

### 4.5 Modulator-variant addendum

Any variant that would produce a band-nudge (modulate WATCH or CAUTION state instead of a raw
ACCRUE/NO-GO verdict) requires:
1. The Lane-(ii) base evidence above (all gates pass).
2. A **separate operator-ratified adjudication** (following the election-cycle precedent, masterplan §2.4).
3. The adjudication must be committed in the same PR as any modulator code.
4. Without the adjudication, the modulator variant is FORBIDDEN regardless of the Lane-(ii) result.

This is not a relaxation of RIC-R3 — it is the narrowly lawful path for calendar-agnostic
constructions that clear the evidence bar, per the masterplan §3 P3 ruling.

---

## 5. Forward ledger accrual (pre-declared rulers)

The `data/event_windows/forward_log.jsonl` ledger stamps each T-1 ex-ante read with the current
`dealer_load_extreme` state (via the gamma_regime field and the active_collisions list). This
enables the descriptive ruler ("surprise-direction × reaction sign by dealer-load regime") to be
populated as prints accrue, without any pre-registration violation — description is not gating.

The `dealer_load_extreme` state is added to each ledger row under the `gamma_regime` field (or
as a separate `dealer_load_state` field if available at stamp time). Ruler frozen here:

| Ruler | Metric | Horizon |
|-------|--------|---------|
| Primary | realized event-day |move| vs implied move | event day (1d) |
| Secondary | realized fwd-vol vs phase base-rate fwd-vol | 5d |
| Descriptive | surprise-direction × reaction-sign by dealer_load_extreme state | event day |

First read: when >= 8 graded rows exist (expected ~2027-Q1, assuming monthly major prints).

---

## 6. What this prereg does NOT authorize

- **NO** calendar-gated `_SCARES` entry (FORBIDDEN, DO_NOT_REBUILD.md §4, permanent).
- **NO** automatic GO if the lift is marginal (threshold is 1.20, not "approximately 1.2").
- **NO** modulator without the explicit separate adjudication.
- **NO** scoring or dampening from `dealer_load_extreme` before Lane-(ii) gates are cleared.
- **NO** use of the pre-FOMC drift concept (measured DEAD post-2016 in the event_window
  seasonality display; that null is the correct honest output and is not a gap to fill).

---

## 7. Registration and precedent

This addendum is pre-registered in the same PR as the W4 EVW engine. The `dealer_load_extreme`
signal identifier is registered in config/synapse.yml under the event-windows group (display tier,
scored_path_surfaces=[]). Any future attempt that deviates from this pre-reg must open a new
pre-reg document rather than modifying this one.

Precedent for calendar-agnostic Lane-(ii) pre-regs: CCW-W3 credit-momentum, RRI Stage-A
construction (rri_crash_antifire_preregs.md). The Lane-(ii) process is described in
masterplan §6.2.
