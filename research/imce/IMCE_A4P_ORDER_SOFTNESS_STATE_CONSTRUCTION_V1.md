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
**only** on fields the crosswalk (`research/imce/hb0/IMCE_HB0_METRIC_DEFINITION_CROSSWALK.md` — note the
`hb0/` path prefix, corrected [AP8, n1]) and the amended contract already
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
| **Net orders** (period) | 10-Q/10-K / press release, per issuer | Disclosed by all six roster issuers (contract §2(b); crosswalk §3 X1) — **TOL's "Net Signed Contracts" formula differs structurally** (nets ALL cancellations occurring in the period, including of contracts signed in prior periods, and credits option-adds on old contracts as current-period sales) — this is typed as a **different formula, not a different level**, per crosswalk X1. **Era coverage is receipted per-issuer, not assumed universal [AP8, M7 fix] — see the fail-closed era-coverage rule below.** |
| **Cancellation rate** (period) | 10-K / press release, per issuer | Canonical per-issuer denominator frozen at contract §2(b) condition (4): DHI = gross orders in period (stated); PHM = gross new orders in period, **FY2016+ only** (stated); KBH = gross orders in period, **FY2008+ only** (stated, footnoted); NVR = gross sales in period (stated), backlog-based alternate disclosed in-source; TOL = gross signed contracts in quarter (primary, AG12), beginning-quarter backlog (mandatory printed sensitivity, AG12); **LEN = no denominator stated anywhere in the disclosure record — cancellation-rate input is `missing` for LEN in every reporting period, never imputed (AG11 ban), consistent with LEN's cell-level exclusion from every v0 historical cell under AP2 below.** |

No third input is used. `completed_inventory_build`, `incentive_support`, and `pace_recovery` are NOT
inputs to this construction — they remain descriptive-only D5 states under AG14/AP1 (§2 below) and are
never imputed into `order_softness`.

### 1a. Fail-closed net-orders era-coverage gate [AP8, M7 fix]

**The original draft of this file stated net orders as "universally disclosed" without an era gate — a
genuine gap Fable's red-team caught.** Checking the hb0 evidence census (`research/imce/hb0/evidence/`) for a
*receipted* (not merely inferred) confirmation that each pooled issuer's net-orders disclosure format/
convention was actually in force across the B≤3 window (2014–2023) that matters for the six registered
cells:

| Issuer | Net-orders era coverage in the hb0 evidence census | Verdict for the 2014–2023 window |
|---|---|---|
| PHM | `evidence/L3_defs_PHM_NVR.md` row 24: FY2005 10-K reports a "Total net new orders — units" table, **"reported at least since 2003 comparatives"** — `[VERIFIED]`-grade citation chain | **Receipted, covers 2014–2023 fully.** |
| KBH | `evidence/L4_defs_KBH_TOL.md` row "Net orders / net new orders": **"[VERIFIED] Present at least back to FY2005"** (FY2006 10-K quote: "net orders declined 28% to 30,675 in 2006 from 42,405 in 2005") | **Receipted, covers 2014–2023 fully.** |
| DHI | `evidence/L2_defs_DHI_LEN.md` rows 1–2: net/gross-orders disclosure format is **`INF` (inference) only** — "not verified against a pre-2010 DHI filing in this pass"; explicit table/footnote language confirmed only from the FY2025 10-K reviewed | **NOT receipted for 2014–2023** — inference-grade only, not a positive verification. |
| TOL | `evidence/L4_defs_KBH_TOL.md` row 57: the "Net Signed Contracts" convention (including its distinctive prior-period-cancellation-netting mechanic) is **`[SOURCE CLAIM]`** only — "used across all periods reviewed, **FY2025-FY2026**; earliest year of this exact accounting convention... **NOT independently dated — GAP**" | **NOT receipted for 2014–2023** — source-claim grade only, not a positive verification. |

**Fail-closed rule, applied mechanically, never by silent assumption:** an issuer-period whose net-orders
disclosure format has not been positively receipted (a `[VERIFIED]` or equivalent evidence-census grade) for
the reporting period in question contributes `d_orders(i,t) = missing` ⇒ `order_softness(i,t) =
NOT_RECONSTRUCTABLE` for that issuer-period (§2 lookup table, `missing`/any row), **regardless of whether the
disclosure plausibly existed** — plausibility is not a receipt. Concretely, for the entire 2014–2023 window:
**DHI and TOL contribute `NOT_RECONSTRUCTABLE` on the orders-side input; only PHM and KBH have receipted
orders-side coverage.** This is a period-specific gate, not a permanent exclusion — DHI and TOL both have
`[VERIFIED]`-grade net-orders disclosure for FY2025-era periods, so they re-enter the eligible pool once (and
only once) a future census pass receipts their FY2014–FY2024 disclosure format. **Coverage consequence for
§3's ≥2-issuer floor:** until that receipting work is done, the pooled contributor set for the B≤3 window is
effectively **{PHM, KBH} — exactly the ≥2 floor, not comfortably above it.** See
`IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 for the disposition-level disclosure of this coverage impact, and this
wave's return packet GAPS for the escalation to Sol.

**Named-subset labelling, not cohort labelling, until DHI/TOL receipts exist [AP8, F2(a)]:** because the
historically-eligible roster is {PHM, KBH} — a strict two-issuer subset of the nominal four-issuer roster —
every HISTORICAL `order_softness` read (2014–2023) is a **NAMED-SUBSET claim, `named_subset_basis: [PHM,
KBH]`**, under the same discipline contract §2 AG14 already applies to `completed_inventory_build`'s
three-issuer subset. **It may NOT be presented as a full-cohort claim** until DHI's and TOL's era coverage is
receipted. The **PROSPECTIVE** arm is different in kind, not merely in degree: every roster issuer's
*current-format* disclosure is already receipted (contract §2, AG14, as scoped by the F2(b) note above), so a
PROSPECTIVE `order_softness` read retains the genuine four-issuer cohort basis and the cohort label — the
named-subset restriction is a HISTORICAL-reconstruction-only consequence of the era-coverage gate, not a
permanent property of the construction. **Two distinct thresholds — never conflated [AP8, F2(c)]:** the ≥2-
issuer floor (§3.1) is the AG14-derived MINIMUM contributor count for minting any pooled state at all; whether
a state minted at exactly that floor may carry the stronger COHORT label (vs. named-subset) is a separate,
stricter, currently-unruled question. **Escalated to Sol [AP8, F2(d)]:** whether a ≥2-contributor
`order_softness` read may ever bear the cohort label — until Sol rules, named-subset labelling governs every
historical read.

**Unstated consequences, named explicitly for Sol's ratification review [AP8, F3]:**

1. **The grind block yields ZERO cohort states before FY2016.** Composing the §1a orders-side gate ({PHM, KBH}
   only, 2014–2023) with §1's cancellation-rate eras (PHM stated FY2016+ only; KBH stated FY2008+ only): a
   per-issuer `order_softness(i,t)` state requires BOTH `d_orders` and `d_cancel` non-`missing` (§2). For
   2014-01 through FY2015, PHM's cancellation-rate input is `missing` (its stated-denominator era has not yet
   begun), so PHM cannot contribute a per-issuer state in that span — leaving KBH as the **sole** contributor.
   A single contributor is below the ≥2-issuer floor (§3.1) ⇒ `NOT_RECONSTRUCTABLE` for every period in that
   span. **The grind block's genuinely usable window for minting any `order_softness` cohort state (named-
   subset or otherwise) is FY2016–2019 only** — roughly the back half of the nominally 2014–2019 block, not
   the full block.
2. **Every historical non-null, non-`MIXED` cohort state is, by construction, a PHM–KBH AGREEMENT indicator.**
   With exactly two eligible historical contributors, the modal-state rule (§3.1) collapses to three cases:
   either issuer missing an input ⇒ single contributor or fewer ⇒ `NOT_RECONSTRUCTABLE`; both present and
   disagree ⇒ `MIXED`; both present and agree ⇒ that shared label is the cohort state. **There is no case in
   which a historical non-null, non-`MIXED` `order_softness` read reflects anything broader than "PHM and KBH
   independently reported the same direction this period."** This is stated as an honest-N fact, not a defect
   to be silently worked around — the predetermined `underpowered_accruing` status (contract §12, unaffected
   by this) already anticipates a thin historical read; this consequence sharpens exactly how thin.

### 1b. TOL alternate-basis sensitivity is a mandatory diagnostic, never silently absorbed [AP8, m3 fix]

Per AG12 (contract §2 Homebuilders, "TOL cancellation-rate denominator"), TOL's cancellation-rate input to
this construction uses the **primary convention (gross signed contracts in the period)** — matching the §1
table above — with the **beginning-quarter-backlog convention as a mandatory printed sensitivity**, not an
optional alternate. This construction registers that obligation concretely: **a sensitivity variant of
`d_cancel(TOL, t)` is computed under the beginning-quarter-backlog denominator and published alongside the
primary-basis `order_softness(TOL, t)` state, for every period, as a mandatory diagnostic.** Every registered
verdict (cohort state, false-repair/relapse observation, any future promotion-bearing use) is computed and
graded on the **primary basis only** — the sensitivity variant carries no verdict authority of its own,
mirroring contract §2(b)'s standing "a result that flips under the alternate convention is not a pass" rule.
**If the primary-basis and sensitivity-basis states disagree for a given period, that disagreement is
disclosed explicitly** (e.g. "TOL: `SOFTENING` on primary basis, `TIGHTENING` on backlog-sensitivity basis")
— never silently absorbed into a single reported number, and never used to select whichever basis is more
convenient for a given readout.

---

## 2. Per-issuer-quarter state (deterministic, sign-only, no fitted threshold)

For each issuer *i* and reporting period *t* (issuer fiscal quarter, re-keyed to calendar month per contract
§2(a)):

- `d_orders(i,t)` = sign of the year-over-year change in net orders (positive / negative / zero), computed only
  when BOTH (a) issuer *i*'s net-orders figure is captured for period *t* (a historical-snapshot question,
  contract §6 item 10) AND (b) issuer *i*'s net-orders disclosure format/convention is receipted for period
  *t*'s era, per §1a's fail-closed gate — **not** a denominator ambiguity (net orders carries no denominator
  ambiguity per crosswalk §3 X1), but a distinct disclosure-format-verification question DHI and TOL currently
  fail for the 2014–2023 window; otherwise `missing`.
- `d_cancel(i,t)` = sign of the year-over-year change in cancellation rate, **in percentage points**, computed
  only when issuer *i*'s canonical denominator is in force for period *t* per the table above (e.g. PHM only
  from FY2016 onward, KBH only from FY2008 onward); otherwise `missing`.

**State rule (per issuer-quarter) — a lookup table over signs only, no magnitude, no fitted cutoff. [AP8, m2
fix] The table now enumerates BOTH missing-input cases explicitly — a missing orders-side input was
previously folded into the same "any / missing" row as a missing cancel-side input without saying so; the log
text and the table now agree:**

| `d_orders` | `d_cancel` | `order_softness(i,t)` |
|---|---|---|
| `+` (orders growing) | `-` or `0` (cancellations flat/falling) | `TIGHTENING` |
| `-` (orders declining) | `+` or `0` (cancellations flat/rising) | `SOFTENING` |
| `+` | `+` | `MIXED` — orders growing but cancellations also rising; genuine ambiguity, never collapsed to a side |
| `-` | `-` | `MIXED` — orders declining but cancellations also falling; genuine ambiguity, never collapsed to a side |
| `0` | any (not `missing`) | `MIXED` — no order-growth signal; typed ambiguous rather than defaulted to a direction |
| `missing` | any | `NOT_RECONSTRUCTABLE` — **[AP8, m2]** missing orders-side input (net orders not captured for that cutoff, contract §6 item 10) — never imputed, never backfilled |
| any (not `missing`) | `missing` | `NOT_RECONSTRUCTABLE` — issuer/period predates that issuer's stated-denominator era, or the cancellation field lacks a captured historical snapshot (contract §6 item 10) |
| `missing` | `missing` | `NOT_RECONSTRUCTABLE` — both inputs unavailable |

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

### 3.0 Block admissibility is governed by the contract, not by this construction [AP8, B2 fix]

**This construction computes per-issuer-quarter and cohort STATES. It never admits, selects, or determines
which historical BLOCK a period counts toward.** Block admissibility for all six registered v0 historical
cells is governed exclusively by the contract's registered block list (§3 "Frozen historical block list," as
hardened by AG5/AG6 and uniformed across all six cells by AP2): **B≤3, cancellation-scoped — only the
2014–2019 grind (partial FY2016+ PHM/NVR coverage), 2020–2021 pandemic boom, and 2022–2023 rate shock blocks
count toward `n_effective_blocks` for any of the six registered cells. GFC bust and GFC recovery (blocks #1
and #2) remain unusable for every registered cell, per AP2(3), REGARDLESS of whether this construction can
technically compute a per-issuer-quarter state inside those blocks.**

This distinction is load-bearing: KBH's cancellation denominator is stated from FY2008 onward (§1 above),
which sits astride the tail end of the GFC-bust block (#1, 2006–2009) — §2's per-issuer-quarter rule would
happily compute a non-`NOT_RECONSTRUCTABLE` `order_softness(KBH, t)` for a 2008 or 2009 reporting period on
input-availability grounds alone. **That computed state may never be counted toward `n_effective_blocks` or
treated as contributing to a v0 historical cell** — the contract's block list, not this construction's
input-availability test, is the sole admissibility gate. A period whose block is inadmissible under the
contract is excluded from cell-level accounting even when this construction can compute a state for it;
conversely, a period inside an admissible block that this construction types `NOT_RECONSTRUCTABLE` is simply
absent from that block's episode count (§10, missing is never zero) — the two gates are independent and both
apply.

### 3.1 Pooling and the cohort state

Per contract §1, the phase and sync-Cell-4 targets are declared over a **pooled homebuilder stratum**.
Per AP2 (all six v0 historical cells are cancellation-scoped, B≤3, LEN excluded cell-level), the **nominal**
pooled roster for `order_softness` is **{DHI, PHM, KBH, TOL}** — LEN excluded (§2 above; AP2), **NVR held out
as its own stratum and never pooled** (contract §2 NVR bullet, AG13, unchanged). **The nominal roster and the
actually-eligible-per-period roster are not the same thing [AP8, M7 cross-reference]:** §1a's fail-closed
era-coverage gate currently disqualifies DHI and TOL from the orders-side input across the entire 2014–2023
window, so the roster that is actually eligible to contribute a per-issuer state in that window is **{PHM,
KBH}** — two issuers, not four — until a future census pass receipts DHI's and TOL's pre-FY2025 net-orders
disclosure format. **Labelling consequence [AP8, F2(a)]:** every HISTORICAL cohort state minted from this
narrower eligible roster carries `named_subset_basis: [PHM, KBH]` and is a named-subset claim, never a
full-cohort claim — see the labelling discussion immediately following §1a above for the full rule and the
open Sol escalation on whether a ≥2-contributor read may ever bear the cohort label. The PROSPECTIVE arm is
unaffected — the nominal four-issuer roster is the genuine cohort basis there.

**Cohort state at period *t* = the modal (most frequent) per-issuer state among the non-`NOT_RECONSTRUCTABLE`
issuers in {DHI, PHM, KBH, TOL} at *t*, subject to a minimum-contributor floor:**

- **A cohort state is minted only when ≥2 roster issuers contribute a reconstructable (non-`NOT_RECONSTRUCTABLE`)
  per-issuer state at *t* [AP8, B2 fix].** This floor is **not a new tuned parameter** — it applies AG14's
  existing bar on a single disclosing issuer's reading wearing a cohort-level label (contract §2 Homebuilders,
  AG14: `incentive_support`/`pace_recovery` "rest on a single disclosing issuer today... may NOT be imputed
  into any cohort cell" because doing so would present one issuer's fact as a cohort fact). A single
  contributing issuer at *t* is exactly that same defect in a different D5 state, so the same bar applies:
  **exactly one contributing issuer ⇒ `NOT_RECONSTRUCTABLE`** for the cohort at *t* (that issuer's own state is
  still printed as a per-issuer diagnostic, contract §7, but never promoted to the cohort label).
- **Two contributing issuers that disagree ⇒ a tie ⇒ `MIXED`** (not broken toward either issuer).
- **Any modal tie — two-way or three-way — is `MIXED` [AP8, m4 fix, extends the original two-way statement]:**
  e.g. two issuers `TIGHTENING` and two `SOFTENING` (a two-way tie among all four contributors), or one
  `TIGHTENING`, one `SOFTENING`, one `MIXED` with the fourth issuer `NOT_RECONSTRUCTABLE` (a three-way tie
  among the three contributors) — every tie shape is typed `MIXED`, never broken by an arbitrary tiebreak
  rule, consistent with contract §8 item 4's "sign must survive... every leave-one-issuer-out refit"
  discipline (a tiebreak rule would itself be a fitted choice).
- If **zero or one** of the four issuers has a reconstructable state at *t* (e.g. an early period before any
  issuer's cancellation-denominator era began, or before the block itself is admissible under §3.0), the
  cohort state is `NOT_RECONSTRUCTABLE` for *t*, and *t* is excluded from the episode population for that
  reporting period — never imputed, never backfilled (contract §10).
- The count of non-`NOT_RECONSTRUCTABLE` issuers contributing to each period's cohort state is **printed**
  alongside the state (population transparency, contract §7: "every fold prints population, missingness,
  class balance, and source coverage") — this is how the ≥2 floor itself is auditable, not merely asserted.

---

## 4. Target mapping (settles AP1 / the AG14 open item)

Per AP1 (contract §1, §2, §15/§15a):

| `rf.cycle_pattern.imce_phase_v0` target slot | D5 state tracked | Construction |
|---|---|---|
| next family-local state, 1 reporting period | `order_softness`, next-period cohort state (§3) | this document |
| next family-local state, 3 reporting periods | `order_softness`, +3-reporting-period cohort state (§3) | this document |
| false repair / relapse within 3 reporting periods | `order_softness` transition `SOFTENING → TIGHTENING` (a "repair") that reverts to `SOFTENING` within 3 reporting periods (a "relapse") | this document, §3 cohort state sequence, precise rule below [AP8, m1] |

`rf.cycle_pattern.imce_sync_v0` Cell 4 (`next_local_state_1rp`) targets the **same** `order_softness`
next-period cohort state as the phase family's 1-reporting-period target (contract §1, AP1) — it is not a
second, independently-constructed state.

**False-repair/relapse rule, frozen exactly [AP8, m1 fix — the prior text left "TIGHTENING" and "within the
window" ambiguous against the `MIXED`/`NOT_RECONSTRUCTABLE` states]:**

1. **Anchor:** the cohort state at reporting period *t* is `SOFTENING`.
2. **Repair:** the cohort state at some period *t+k* (1 ≤ k ≤ 3) is **observed `TIGHTENING`** — exactly that
   label, not `MIXED`. **`MIXED` never counts as a repair, by construction** (it is not `TIGHTENING`; treating
   an ambiguous read as a repair would smuggle a fitted judgment call back into a sign-only rule).
3. **Relapse:** the cohort state at some period *t+k+j* (1 ≤ j ≤ 3, and *t+k+j* itself within 3 reporting
   periods of the *original* anchor *t* — the window does not reset on the repair) is again `SOFTENING`. A
   confirmed repair-then-relapse sequence is the false-repair/relapse observation.
4. **Void on gap:** if the cohort state at ANY period between the anchor and the candidate relapse (inclusive
   of the repair period itself) is `NOT_RECONSTRUCTABLE`, **the entire observation is voided — null, explicit**
   (contract §10, "missing is never zero" — a gap in the sequence is never bridged by assuming what the
   missing state "probably" was). A voided window is recorded as `NOT_RECONSTRUCTABLE` for that anchor, not
   silently dropped and not counted as a non-event.
5. **`MIXED` inside the window (not at the repair slot):** a `MIXED` cohort state at a period other than the
   candidate repair slot does not itself void the window (it is a valid, non-missing observation — genuine
   ambiguity, not absence) — but it also cannot itself serve as the repair (step 2) or the relapse (step 3),
   both of which require the specific `SOFTENING`/`TIGHTENING` labels.

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
