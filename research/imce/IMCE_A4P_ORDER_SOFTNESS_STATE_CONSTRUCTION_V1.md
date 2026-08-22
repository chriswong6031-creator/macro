# IMCE-A4P — Deterministic `order_softness` State Construction

**Wave:** A4P (preregistration criteria closure). Records-only. No outcome number, model fit, price/return
data, or trial-ledger write appears anywhere below.
**Authority:** amended contract V1.2 §1/§2 Homebuilders (`IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`),
Sol's A4P ruling 1 (2026-08-21), `IMCE_A4G_AMENDMENT_LOG.md` §AP1 (the amendment log records both the A4G
and A4P gates in one append-only file).
**Referenced normatively from:** contract §1 (trial families), §2 Homebuilders (state-vector observability
scoping, AG14/AP1), §15/§15a (registration stop condition — no phase-family target may be registered unless
mapped to a named D5 state with a registered observability class AND, for `order_softness`, a registered
deterministic construction).
**Purpose:** freeze the exact, outcome-independent, deterministic construction of the `order_softness` D5
mechanism-local state, so that the three `imce_phase_v0` targets and `imce_sync_v0` Cell 4 (all now mapped to
`order_softness` per AP1) have a named, reproducible state definition with zero remaining discretionary
choices at actual A4 registration.

---

## 0. Why this document exists

Sol's A4P ruling 1 requires "a deterministic `order_softness` state construction derived from the existing
source/definition crosswalk (HB-0 census + hb0/ estate) — no grid search, no outcome-selected threshold, no
issuer-specific tuning; null/not-reconstructable states remain explicit." The construction below draws
**only** on fields the crosswalk (`IMCE_HB0_METRIC_DEFINITION_CROSSWALK.md`) and the amended contract already
froze as reconstructable, with a per-issuer denominator/formula census already adjudicated (contract §2(b),
condition (4) table; AG10/AG12). It introduces **no new source, no new field, and no fitted parameter** —
every comparison below is a **sign comparison** (direction of change), never a magnitude threshold chosen by
inspection of any outcome.

**No outcome access of any kind occurred in the drafting of this document.** No issuer stock price, ETF
price, or forward return was read, computed, or referenced. The inputs are exclusively: net orders (a sales
volume figure, disclosed by all six roster issuers) and cancellation rate (per the already-frozen per-issuer
denominator table), both mechanism-vector `M_t` fields under contract §4, never `R_t` or a market outcome.

---

## 1. Inputs (verbatim from the already-frozen crosswalk — no new field minted)

| Input | Source | Frozen basis |
|---|---|---|
| **Net orders** (period) | 10-Q/10-K / press release, per issuer | Universally disclosed (contract §2(b); crosswalk §3 X1) — **TOL's "Net Signed Contracts" formula differs structurally** (nets ALL cancellations occurring in the period, including of contracts signed in prior periods, and credits option-adds on old contracts as current-period sales) — this is typed as a **different formula, not a different level**, per crosswalk X1, and is disclosed at every TOL cell citing net orders. |
| **Cancellation rate** (period) | 10-K / press release, per issuer | Canonical per-issuer denominator frozen at contract §2(b) condition (4): DHI = gross orders in period (stated); PHM = gross new orders in period, **FY2016+ only** (stated); KBH = gross orders in period, **FY2008+ only** (stated, footnoted); NVR = gross sales in period (stated), backlog-based alternate disclosed in-source; TOL = gross signed contracts in quarter (primary, AG12), beginning-quarter backlog (mandatory printed sensitivity, AG12); **LEN = no denominator stated anywhere in the disclosure record — cancellation-rate input is `missing` for LEN in every reporting period, never imputed (AG11 ban), consistent with LEN's cell-level exclusion from every v0 historical cell under AP2 below.** |

No third input is used. `completed_inventory_build`, `incentive_support`, and `pace_recovery` are NOT
inputs to this construction — they remain descriptive-only D5 states under AG14/AP1 (§2 below) and are
never imputed into `order_softness`.

---

## 2. Per-issuer-quarter state (deterministic, sign-only, no fitted threshold)

For each issuer *i* and reporting period *t* (issuer fiscal quarter, re-keyed to calendar month per contract
§2(a)):

- `d_orders(i,t)` = sign of the year-over-year change in net orders (positive / negative / zero).
- `d_cancel(i,t)` = sign of the year-over-year change in cancellation rate, **in percentage points**, computed
  only when issuer *i*'s canonical denominator is in force for period *t* per the table above (e.g. PHM only
  from FY2016 onward, KBH only from FY2008 onward); otherwise `missing`.

**State rule (per issuer-quarter) — a lookup table over signs only, no magnitude, no fitted cutoff:**

| `d_orders` | `d_cancel` | `order_softness(i,t)` |
|---|---|---|
| `+` (orders growing) | `-` or `0` (cancellations flat/falling) | `TIGHTENING` |
| `-` (orders declining) | `+` or `0` (cancellations flat/rising) | `SOFTENING` |
| `+` | `+` | `MIXED` — orders growing but cancellations also rising; genuine ambiguity, never collapsed to a side |
| `-` | `-` | `MIXED` — orders declining but cancellations also falling; genuine ambiguity, never collapsed to a side |
| `0` | any | `MIXED` — no order-growth signal; typed ambiguous rather than defaulted to a direction |
| any | `missing` | `NOT_RECONSTRUCTABLE` — issuer/period predates that issuer's stated-denominator era, or the field lacks a captured historical snapshot per contract §6 item 10 ("current-snapshot-backfill exclusion" — absence of a captured snapshot ⇒ `not_reconstructable`, dropped, never backfilled) |

**LEN is always `NOT_RECONSTRUCTABLE` on this construction** (no cancellation denominator, ever) — consistent
with, not a new instance of, LEN's cell-level exclusion under AP2 (§3.2 of the amendment log). LEN's net-orders
figure is disclosed and reconstructable on its own, but `order_softness` requires both inputs, so a
single-sided reconstruction is never attempted (contract §10: "missing is never zero," and a one-input proxy
would be exactly the kind of invented denominator crosswalk §1 headline result forbids).

**No threshold is fitted, chosen, or tuned.** The rule above is a pure sign lookup — it would be computed
identically whether the true YoY change was +0.1pp or +9pp. This is what makes the construction
outcome-independent: no inspection of any forward return, drawdown, or Brier outcome informed the choice of
`+`/`-`/`0` as the only distinguishing feature, nor the shape of the lookup table.

---

## 3. Cohort (pooled) state — the `imce_phase_v0`/`imce_sync_v0` target population

Per contract §1, the phase and sync-Cell-4 targets are declared over a **pooled homebuilder stratum**.
Per AP2 (all six v0 historical cells are cancellation-scoped, B≤3, LEN excluded cell-level), the pooled
population for `order_softness` is exactly **{DHI, PHM, KBH, TOL}** — LEN excluded (§2 above; AP2), **NVR
held out as its own stratum and never pooled** (contract §2 NVR bullet, AG13, unchanged).

**Cohort state at period *t* = the modal (most frequent) per-issuer state among the non-`NOT_RECONSTRUCTABLE`
issuers in {DHI, PHM, KBH, TOL} at *t*.**

- A tie between two states (e.g. two issuers `TIGHTENING`, two `SOFTENING`) is typed `MIXED` — never
  broken by an arbitrary tiebreak rule, consistent with contract §8 item 4's "sign must survive... every
  leave-one-issuer-out refit" discipline (a tiebreak rule would itself be a fitted choice).
- If **zero** of the four issuers have a reconstructable state at *t* (e.g. an early period before any
  issuer's cancellation-denominator era began), the cohort state is `NOT_RECONSTRUCTABLE` for *t*, and *t*
  is excluded from the episode population for that reporting period — never imputed, never backfilled
  (contract §10).
- The count of non-`NOT_RECONSTRUCTABLE` issuers contributing to each period's cohort state is **printed**
  alongside the state (population transparency, contract §7: "every fold prints population, missingness,
  class balance, and source coverage").

---

## 4. Target mapping (settles AP1 / the AG14 open item)

Per AP1 (contract §1, §2, §15/§15a):

| `rf.cycle_pattern.imce_phase_v0` target slot | D5 state tracked | Construction |
|---|---|---|
| next family-local state, 1 reporting period | `order_softness`, next-period cohort state (§3) | this document |
| next family-local state, 3 reporting periods | `order_softness`, +3-reporting-period cohort state (§3) | this document |
| false repair / relapse within 3 reporting periods | `order_softness` transition `SOFTENING → TIGHTENING` (a "repair") that reverts to `SOFTENING` within 3 reporting periods (a "relapse") | this document, §3 cohort state sequence |

`rf.cycle_pattern.imce_sync_v0` Cell 4 (`next_local_state_1rp`) targets the **same** `order_softness`
next-period cohort state as the phase family's 1-reporting-period target (contract §1, AP1) — it is not a
second, independently-constructed state.

**`completed_inventory_build` is explicitly NOT mapped to any of the 3 declared phase-family targets** (AP1)
— it remains a named DHI/LEN/PHM three-issuer descriptive/subset research object (AG14, unchanged), never a
v0 cohort inferential target. `incentive_support` and `pace_recovery` remain descriptive only (AG14,
unchanged) and are not mapped to any declared target.

---

## 5. What this document does NOT do

- Does not compute a single actual state value for any historical or prospective period — no `M_t` field was
  read from any issuer filing to produce a number; only the **rule** (the lookup table and pooling logic) is
  frozen here.
- Does not access, read, or reference any price, return, drawdown, or other market-outcome series.
- Does not itself register the `imce_phase_v0`/`imce_sync_v0` families — registration remains a separate,
  future A4/IMCE-03 act (`IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`, as regenerated by AP7).
- Does not alter the frozen 6-cell budget (contract §1, A5) or the B≤3 block-basis law (AG6, hardened to all
  six cells by AP2).

---

**This document authorizes nothing beyond itself.** It is a deterministic construction freeze, cited
normatively by the amended contract (§1, §2, §15/§15a) and by `IMCE_A4G_SIX_CELL_DISPOSITION.md`. The next
authorized act on this family is actual A4 registration.
