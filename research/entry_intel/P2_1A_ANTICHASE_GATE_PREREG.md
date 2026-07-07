# P2.1a — F3 Anti-Chase Hard-Gate Promotion — PRE-REGISTRATION

**STATUS: APPROVED — Fable 2026-07-05 (red-team P2_REDTEAM.md blocking fixes applied; Fable rulings R-P2.1 flip-floor=100 clusters+2 quarters, R-P2.2 single concordance authority = P2.1b §3.3)**

> **AMENDED FLIP TERMS (2026-07-07, RC-RUL-1 — research/TIME_CONFOUND_RECHECK_ADJUDICATION.md).**
> The upstream P1.3 warrant (T24/T21) did not survive DT-R14 time-controlled re-inference
> (EI-RC-1, PR #1866): the in-sample hard-gate evidence is withdrawn. This prereg's shadow
> accrual continues unchanged, but the R-P2.1 floors (100 blocked episode-clusters +
> 2 quarters) are now necessary-not-sufficient: **any flip decision must additionally
> include a within-period-demeaned, calendar-block-resampled read of the accumulated
> shadow-ledger data.** The forward ledger must earn the flip on its own.

**Study:** P2.1a — F3 Anti-Chase (ext_z) Hard-Gate, Shadow-First Promotion
**Program:** Entry Intelligence (EI) — Phase 2
**Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §6/P2.1`
**Registered:** 2026-07-05 (before any live-board wiring)
**Author:** Sonnet subagent under Fable orchestration
**Upstream evidence:** P1.3 Trio Ablation round-2 (`research/entry_intel/p1_runs/P1_3/RESULTS.md`,
`REVIEW_v2.md`), reviewed and accepted by Opus conformance subagent 2026-07-05.
**Constitutional law:** EI masterplan §3 (inherited), Setup Species constitution §1 (ladder,
shadow-first, flip criteria, Wilson lower bound, episode-clustered n floors); Neural Web
Articles 2 & 3 (board_ordering is a named money-path surface — shadow before flip);
R7 additive-lanes law; P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1 amendments.

---

## 0. Plain-English Summary

> The live board already shows an "extension grade" for every stock — a label that flags
> names whose price has climbed far above what is normal for them. Until now, that label
> only showed up as a warning chip; it never blocked a name from appearing on the board.
>
> P1.3 tested whether a hard block on the most-extended names (those with an extension
> z-score above 2.0, meaning they are priced more than 2 standard deviations beyond their
> own one-year normal distance from the 200-day average) would have improved outcomes on
> actual production-trigger fires — and found that it would: stop-outs fall by **0.43
> percentage points at 21 days** and by **5.0 percentage points at 63 days**, while
> dead-money occurrences fall by **3.6 percentage points at 21 days**, all surviving
> multiple-testing correction. Critically, the gate only ever touches about **5% of board
> fires** (2,299 of 49,939 in the study window) — far below the 40% threshold that would
> make a gate too blunt.
>
> This document registers the plan to bring that gate into the live board. It ships
> **shadow-first**: the gate will compute every night and flag which names it would have
> blocked, but those names will still appear — clearly labeled — in a dedicated lane. The
> gate only flips to enforcing (actual block) after live forward-ledger evidence meets a
> pre-specified criterion: enough independent episode clusters have accrued (n ≥ 100,
> the program's K1 floor, AND at least 2 calendar quarters of accrual) and the Wilson lower
> bound on stop-out improvement (D = blocked minus unblocked) in the blocked group exceeds
> zero at the 63d horizon. Until
> that criterion is met, visitors to the board see exactly what they see today; the shadow
> column is the only change.

---

## 1. Evidence Base and Promotion Eligibility

### 1.1 Three independent P1.3 effects cited (reviewer advisory compliance)

The REVIEW_v2.md advisory-2 specifies that P2.1 documents must cite **the ~3 independent
forward-return effects** (approximately 10 independent continuous forward-return tests
underlying the 30-trial grid), not the "22/30 trial" survival count. The three independent
effects relevant to F3's hard-gate promotion are:

| Effect | Trials | Δpp | BH-adj p | Sign-stable |
|--------|--------|-----|----------|-------------|
| **21d stop-out reduction** | T21 (HG, 21d, STOPPED) | **−0.43pp** | **0.0060** | YES (H1: −0.87pp, H2: −0.55pp) |
| **21d dead-money reduction** | T22 (HG, 21d, DEAD_MONEY) | **−3.63pp** | **0.0060** | YES (H1: −3.76pp, H2: −3.66pp) |
| **63d stop-out reduction** | T24 (HG, 63d, STOPPED) | **−5.00pp** | **0.0933** | YES (H1: −8.75pp, H2: −1.55pp) |

These three trials share a single underlying forward-return distribution test (perm_p
independently computed per (factor, mode, horizon) cell); they constitute three independent
safety-net-axis reads at two horizons. T23 (21d cushioned, Δ = −0.97pp) and T25/T26 (63d
dead-money and cushioned) are recorded for context but are not the promotion basis.

**RW mode does NOT ship.** T27–T30 (F3 rank-weight trials) all fail both-halves sign
stability. The registered ship-path is hard gate only, per PREREG §6.3.

### 1.2 Fire-rate eligibility (R7 + §6.2 compliance)

| Metric | Value | Threshold | Pass |
|--------|-------|-----------|------|
| n_fires_total (verdict-grade) | 49,939 | — | — |
| n_would_block (ext_z > 2.0) | **2,299** | — | — |
| gate_fire_rate_impact_pct | **4.6%** | < 40% | YES |
| n_clusters_would_block | **1,270** | ≥ 25 | YES |

Gate impact is 4.6%, well below the 40% cap in PREREG §6.2. The GATE-REJECT condition
does not apply. F3 ships as hard gate per §6.3.

### 1.3 ext_z threshold — exact, from P1.3 encoding

The hard-gate threshold is **ext_z > 2.0**, encoded as `PARABOLIC_Z = 2.0` in
`engine/extension.py` (L36). This is the pre-registered threshold from PREREG §2/F3
("fires with `ext_z > +2.0` are classified as extended/chase"). It is not tuned here;
it is read from the registered design. The production computation of `ext_z` is
`(price/SMA200 − 1)` z-scored against the name's own trailing 252-day history
(minimum 120 bars), implemented in `engine/extension.py` L92.

**In plain English:** a stock is "extended" for this gate when today's distance above its
200-day moving average is more than 2 standard deviations above what is normal for that
specific stock over the past year — not just high in absolute terms.

---

## 2. Design: Shadow-First Gate

### 2.1 What shadow-first means

Per Article 2 (Neural Web) and Ruling R6 (EI masterplan), `board_ordering` is a named
money-path surface. Any change to which names appear on the board — even a gate that
affects only ~5% of rows — must undergo a shadow period before it enforces.

**Shadow period definition:** The gate computes on the live board nightly and writes:
- `antichase_shadow_blocked` (bool): True if the name has `ext_z > 2.0` at signal time.
- `antichase_shadow_chip`: a visible "Would-block: anti-chase" label rendered on the card.

During the shadow period, no name is removed from the board and no rank position changes.
The blocked names appear in a dedicated labeled lane — "Anti-Chase Watch" — per R7
additive-lanes law (§2.4 below). The shadow forward ledger accrues independently.

### 2.2 The flip criterion (pre-registered; immutable after Fable approval)

The gate flips from shadow to enforcing when **all three of the following hold**,
evaluated at the monthly species review:

**C1 — Episode-clustered n floor (gate_weight rung):**
The shadow forward ledger has accrued ≥ **100 independent episode clusters** of
would-have-blocked events (i.e., names where `antichase_shadow_blocked = True` at their
live signal date) AND at least **2 calendar quarters** of accrual have elapsed since the
shadow ledger first wrote a row. The 100-cluster floor is the program's established
INSUFFICIENT-POWER halt threshold for this class of study, per the P1.5 PREREG K1 floor
as instantiated in `p1_runs/p1_5_continuation/RESULTS.md` L136
("ARMED-continuation episode clusters: 1,322 (K1 floor 100 — PASS)") and confirmed by
`p1_runs/p1_5_continuation/REVIEW_v2.md` L94. The 2-quarter requirement ensures seasonal
coverage; neither criterion alone is sufficient.

**Signed quantity definition (used in C2, RB1, and §6):**
Define **D = stop_out_rate(blocked) − stop_out_rate(unblocked)**. The favorable direction
is D > 0 (names the gate would have blocked had higher stop-out incidence — confirming the
gate correctly identifies the worse-outcome group). All bounds below are Wilson 95%
episode-clustered bootstrap (N=1,000 resamples) on this single D.

**C2 — Wilson lower bound on D positive (at 63d):**
The **Wilson 95% lower bound on D** — computed on the shadow ledger's would-have-blocked
episodes vs the unblocked episodes — must be **> 0** at the **63d horizon** (where the P1.3
effect is largest: T24 −5.00pp). Additionally evaluated at 21d; 63d is the primary
criterion. Episode-clustered bootstrap (N=1,000 resamples) provides the interval.

In plain terms: even the conservative lower confidence bound on the stop-out gap confirms
that blocked names had higher stop-out incidence, not lower.

**C3 — Sign-consistency (both halves of the live ledger):**
The live shadow ledger is split at its temporal midpoint. The stop-out improvement
(blocked > unblocked) must hold with the same sign in both halves.

If any criterion fails at the monthly review, the gate remains in shadow. The criteria
are re-evaluated monthly until met or until the rollback trigger fires (§5).

**No discretionary flip.** Only the pre-registered criteria above authorize a flip.
A Fable ruling is required to change these criteria; changing them constitutes a new
PREREG, new species version, and a new trial-ledger entry.

---

## 3. Interaction with the Existing extension_demote Board Stage

### 3.1 Current extension_demote behavior

The production board already applies an extension penalty via `engine/stock_score.py`:

```python
_EXT_PENALTY = {"parabolic": -1.0, "stretched": -0.3}
# ...
if grade in _EXT_PENALTY:               # own-history extension PENALTY (never a positive add)
    hard.append(_EXT_PENALTY[grade]); present.append("extension")
```

A "parabolic" grade (ext_z ≥ 2.0) applies a `−1.0` score penalty. This penalty is
classified as `extension_demote` in `engine/grading.py` (L105: "extension_demote —
anti-chase EXT_PENALTY / extension-since-cross"). The penalty lowers the name's conviction
score but does NOT remove it from the board (the board applies a `min(z, _ENTRY_CAP_Z)`
cap for blocked states, not a removal).

### 3.2 Precedence rule: no double-counting

The F3 anti-chase gate and the existing `extension_demote` penalty operate on the same
axis (`ext_z > 2.0` = "parabolic") but at different layers:

| Layer | Mechanism | Effect | Scope |
|-------|-----------|--------|-------|
| `extension_demote` (existing) | `−1.0` score penalty in `stock_score._axis_entry` | Lowers rank score; name remains on board | Applied within the scoring function |
| F3 anti-chase shadow gate (new) | `antichase_shadow_blocked` flag | During shadow: labeled lane only; no score change | Applied at the board-render stage, after scoring |
| F3 anti-chase enforcing gate (post-flip) | Hard removal from main board | Moves name to labeled lane | Applied at the board-render stage, after scoring |

**Precedence specification:**

1. The `extension_demote` score penalty applies first, within `stock_score.py`. This is
   unchanged regardless of the gate's shadow or enforcing state.
2. The F3 gate then reads `ext_z` directly from the per-name extension payload (not the
   score). It does NOT re-read or modify the score; it reads the same `ext_z` value that
   the score function already consumed.
3. During the shadow period, the F3 gate adds only the chip label. The `extension_demote`
   penalty has already lowered the name's rank, so the name is likely to appear lower in
   the main board ordering — the shadow chip is additive information, not a score change.
4. In the enforcing state, the F3 gate moves the name to the "Anti-Chase Watch" lane
   (§3.3 below), which is logically downstream of scoring. The `extension_demote` score
   penalty still runs (it affects the name's internal score for that lane's ordering), but
   the name no longer appears in the main board lane.

**Double-counting is therefore impossible by construction:** `extension_demote` operates
on the score; the F3 gate operates on board-lane membership. They read the same `ext_z`
but write to different outputs. There is no path where the same `ext_z > 2.0` fact is
used to both penalize the score AND count as a gate removal in the same pipeline pass.

### 3.3 R7 Additive-Lanes Compliance

Per Ruling R7, confirmation stacking labels quality UP — it never filters the board toward
zero rows. Names that the F3 gate would block (or does block, post-flip) remain visible
in a dedicated labeled lane.

**Shadow-period lane:** "Anti-Chase Watch" — a clearly labeled section below the main
board that shows `antichase_shadow_blocked = True` names with the chip
"Extension caution: ext_z > 2.0 (anti-chase gate shadowing)". The names are fully
rendered; all signal details, scores, and cards remain visible. The lane is additive —
it does not replace any existing board row.

**Post-flip enforcing lane:** The same "Anti-Chase Watch" lane becomes the permanent home
for blocked names. They are removed from the main board candidates list but appear in the
labeled lane with: (a) their full card, (b) the chip "Anti-chase gate: would-block at
today's ext_z", and (c) the shadow ledger's accrued stop-out differential. This is the
standard EI additive-lanes pattern for a gate: visibility is preserved, not destroyed.

**Recall audit integration:** The P1.4 Recall audit (running independently) receives the
"blocked" verdict from the anti-chase gate as a labeled rejection reason. The funnel
audit includes blocked-by-F3 names in its denominator and reports them as a distinct
rejection category. This ensures recall is measured through the gate, not obscured by it.

---

## 4. Species Registry Entry

### 4.1 Registry fields (new entry created at PREREG approval)

```json
{
  "species_id": "F3_ANTICHASE",
  "version": "1.0",
  "name": "Anti-Chase Hard Gate (F3 ext_z)",
  "validation_status": "phase0_passed",
  "deployment_status": "chip",
  "mechanism": "Names with ext_z > 2.0 are in the PARABOLIC tail: priced more than 2 own-history σ above their 200-day average. P1.3 established this cohort has higher stop-out (+0.43pp at 21d, +5.0pp at 63d) and dead-money (+3.6pp at 21d) incidence vs the unblocked population on production-trigger fires. The mechanism is forced-buyer exhaustion: a parabolic extension means every short-term buyer has already bought; when momentum stalls, there is no marginal buyer to absorb the first seller. The gate does not predict when the reversal happens — only that it stops the board from confirming a chase entry.",
  "horizon_class": "positional",
  "evidence_stack": [
    {"condition": "ext_z > 2.0 at signal time", "tag": "gate"},
    {"condition": "ext_z computed from engine/extension.py PARABOLIC_Z = 2.0", "tag": "arming"},
    {"condition": "production-trigger fires only (P1.3 population)", "tag": "context"}
  ],
  "rejection_rules": [
    {"rule": "ext_z ≤ 2.0: not blocked", "expected_failure": "non-extended names pass through uninhibited"},
    {"rule": "RW mode did not ship (sign-unstable T27–T30): no rank-weight variant authorized", "expected_failure": "sign flip across halves in RW prevented rank-weight path"}
  ],
  "archetype_scope": {
    "applies": "all archetypes — the parabolic tail is archetype-agnostic (extension is own-history relative, not absolute)",
    "hostile": "none identified; the 4.6% impact means virtually no archetype is disproportionately affected"
  },
  "regime_scope": {
    "hypothesized_supportive": "risk-off / breadth-narrow (extended names most exposed to liquidity withdrawal)",
    "hypothesized_hostile": "strong-breadth melt-up (extension persists without mean-reversion)",
    "learnable_projection": "two axes max: regime_one RISK_STATE × breadth_z quintile; pre-registered at P3.1"
  },
  "market_scope": ["US"],
  "adjacent_falsified": [
    {"id": "extension_as_return_alpha", "source": "SETUP_SPECIES_MASTERPLAN §1.6", "mechanical_difference": "This gate acts on the safety-net axes (stop-out / dead-money), not return-alpha. The graveyard entry falsified extension as a return predictor; P1.3 tests it as a stop-out reducer — a different claim on a different axis."},
    {"id": "cn_reversal_gate", "source": "china-subsector-gate-falsified memory", "mechanical_difference": "CN reversal gate hurt because it gated a mean-reversion edge. This gate targets the ~5% parabolic tail on momentum-confirmed fires, not the reversal sleeve. CN is explicitly out of scope."}
  ],
  "fixtures": [
    {"name": "JNJ_chase_exclusion", "expectation": "any parabolic fire on JNJ at peak valuation must appear in would-block"},
    {"name": "NVDA_persistent_leader", "expectation": "NVDA in normal strong-trend periods reads ext_z < 2 (it IS above 200dma but not 2σ above its own normal), and is NOT blocked — the own-history z-scoring is the key distinction", "status": "UNVERIFIED — no artifact confirms NVDA ext_z distribution; convert to a computable assertion (NVDA ext_z from engine/extension.py L92 on its own 252-bar history; fixture passes iff a specific dated snapshot yields ext_z < 2) before PR merge"}
  ],
  "ledger_binding": {
    "ledger": "data/signal_archive/antichase_shadow_ledger.parquet",
    "since": "shadow-start date (set at PREREG flip to chip)",
    "flip_criteria": {
      "C1_n_floor": "≥ 100 independent episode clusters of would-have-blocked events in the shadow ledger AND ≥ 2 calendar quarters of accrual elapsed since first ledger row (P1.5 PREREG K1 floor — p1_runs/p1_5_continuation/RESULTS.md L136)",
      "C2_wilson": "Wilson 95% lower bound of stop-out improvement (blocked > unblocked) > 0, episode-clustered bootstrap N=1000",
      "C3_sign_stability": "stop-out improvement sign holds in both temporal halves of the shadow ledger"
    }
  },
  "gating": {
    "come_back_on": "monthly species review",
    "cadence": "monthly",
    "maturation": "shadow ledger accrual to C1 n-floor (≥ 100 episode clusters AND ≥ 2 calendar quarters); at ~5% board coverage the episode-cluster count is the binding constraint"
  },
  "trial_count": 3,
  "p1_3_trials": ["T21", "T22", "T24"],
  "context_trials": ["T25_context_only"],
  "deployment_status_path": "chip → ledger_fields → gate_weight (shadow) → gate_weight (enforcing)"
}
```

### 4.2 Ladder rung at approval

At PREREG approval (this document): the species is created at the **chip** rung
(`deployment_status: chip`). The shadow gate column and labeled lane constitute the chip
artifact. The ledger_fields rung is entered when the shadow ledger has accrued its first
30 episode clusters (enough to print a live stop-out differential with CI). The
gate_weight rung — shadow — is entered when C1 + C2 + C3 all clear. The gate_weight
rung — enforcing — is entered after a Fable ruling authorizing the flip, supported by the
met criteria.

The species constitution ladder is: **chip → ledger_fields → graded_bonus → gate_weight**.
This species skips the graded_bonus rung because it ships as a hard gate (not a rank
weight); the graded_bonus rung is for rank-weight species. The enforcing gate is the
`gate_weight` rung top state.

---

## 5. Rollback Trigger

The enforcing gate (post-flip) must roll back to shadow if any of the following occur at
a monthly review:

**RB1 — Stop-out reversal:** the live enforcing ledger accumulates a new cohort of
≥ 200 episode clusters (post-flip) in which the **Wilson 95% upper bound on D** (the same
D = stop_out_rate(blocked) − stop_out_rate(unblocked) defined in §2.2) is **< 0** at
either the 21d or 63d horizon — i.e., even the upper confidence bound on the stop-out gap
is negative, confirming the gate is now blocking better-than-average outcomes.

**RB2 — Fire-rate breach:** the live board fires count shows the gate is blocking > 15%
of weekly fires over any consecutive 4-week window. This indicates a regime shift where
the ext_z > 2.0 condition has become much more common — the gate is no longer a tail
filter.

**RB3 — P1.4 recall failure:** the quarterly recall audit shows that blocked-by-F3 names
have a durable-60D outcome rate ≥ 15 percentage points above the main-board-fire rate
(i.e., the gate is systematically blocking the better outcomes). 15pp is three times the
largest signed P1.3 effect and is a strong signal of regime change.
**[PENDING P1.4 column confirmation]:** As of PREREG registration (2026-07-05),
`p1_runs/P1_4/results.json` does not emit a per-rejection-reason durable-60D outcome rate
column for blocked-by-F3 names — P1.4 measures funnel recall against durable-low
denominators (Denominator A/B), not per-gate-reason outcome rates. RB3 is therefore
contingent on P1.4 being extended to emit this per-reason column. Until that extension is
confirmed, RB3 is recorded as a design intent, not an operational criterion.

**Rollback procedure:** gate reverts to shadow immediately upon a Fable ruling triggered
by any RB condition. The rollback is logged in the masterplan §9 status log and in the
species registry's `deployment_status` field. A new flip attempt requires re-meeting C1,
C2, and C3 from the rollback date forward (old accrual does not count).

---

## 6. Acceptance Criteria (Falsifiable)

This document ships a shadow gate, not a validated claim. The falsifiable acceptance
criterion for the flip (gate_weight promotion) is the conjunction of C1, C2, and C3 in
§2.2. The falsifiable acceptance criterion for the gate_weight rung itself (retaining the
enforcing gate beyond the first 3-month enforcing window) is:

> **The Wilson 95% lower bound on D** (D = stop_out_rate(blocked) − stop_out_rate(unblocked),
> episode-clustered, at the **63d horizon**) must remain **> 0** at the 3-month and 6-month
> enforcing reviews. This is the same D and the same bound direction as the C2 flip
> criterion — the retention criterion is C2 re-evaluated on the enforcing-ledger cohort.

If this bound crosses zero at either review, the gate is demoted to shadow and a new PREREG
is required to re-promote it.

---

## 7. Out-of-Scope Declarations

The following are explicitly NOT authorized by this PREREG:

- Any rank-weight variant of F3 (T27–T30 were sign-unstable; RW does not ship without a
  new PREREG showing sign-stable RW evidence).
- Any change to the `extension_demote` score penalty in `stock_score.py` (that is a
  separate lever; this PREREG does not touch it).
- Application of the F3 gate to CN, HK, or CA boards (market_scope = US only; other
  markets require their own phase-0 runs).
- Use of the shadow-ledger evidence to authorize any other species promotion (the ledger
  is specific to F3's gate_weight claim and may not be borrowed for F1, F2, or any other
  EI study as confirmatory evidence).
- Board-ordering influence beyond the lane membership decision. The gate makes a binary
  board-lane decision (main vs Anti-Chase Watch); it does not affect the rank ordering
  within either lane. Rank ordering within the Anti-Chase Watch lane follows the same
  incumbent rank logic.

---

## 8. Constitutional Compliance Summary

| Requirement | Satisfied by |
|-------------|--------------|
| R6 shadow-first | §2.1–2.2: gate computes nightly, labels only, until flip criteria met |
| Article 2 (board_ordering) | §2.1: shadow with track record before any money-path influence |
| R7 additive-lanes | §3.3: blocked names remain visible in "Anti-Chase Watch" lane |
| Species ladder (chip→ledger→graded_bonus→gate_weight) | §4.2: chip at approval; gate_weight via C1+C2+C3; graded_bonus skipped (gate-only species) |
| Wilson lower bound | §2.2/C2: Wilson 95% lower bound on stop-out improvement > 0 required for flip |
| Episode-clustered n floor | §2.2/C1: n ≥ 100 independent clusters (P1.5 PREREG K1 program floor) AND ≥ 2 calendar quarters of accrual |
| R4 (no pre-commitment to gate form) | Honored: gate design was chosen because fire-rate = 4.6% < 40% AND BH-adj p survives; RW was rejected because sign-unstable |
| No double-counting with extension_demote | §3.2: precedence rule separates score-penalty (existing) from lane-membership (new gate) |
| Plain-language law | §0 plain-English summary present; §3 precedence rule has plain-English characterization |
| Reviewer advisory-2 (cite ~3 effects, not 22/30) | §1.1: three independent effects cited with exact pp and BH-adj p values |
| Falsifiable acceptance criteria | §6: Wilson lower bound > 0 at 3m and 6m enforcing reviews |
| PREREG before run | This document is DRAFT before any live board wiring |

---

## 9. Execution Contract

At Fable approval of this PREREG:

1. A Sonnet subagent implements `antichase_shadow_blocked` column and "Anti-Chase Watch"
   lane in the board render pipeline (exact files: to be determined at build-time; no
   modification to `stock_score.py` or `engine/extension.py` — reads their outputs only).
2. The sentinel commit step's git-add set is updated to include the shadow ledger store
   path (`data/signal_archive/antichase_shadow_ledger.parquet`), per the sentinel-commit-
   step-staging-gap law in memory.
3. The species registry (`data/species/registry.json`) receives the §4.1 entry.
4. The monthly species review checklist gains an F3 anti-chase row with C1/C2/C3 as the
   tracked metrics.
5. P1.4 Recall audit receives the blocked-by-F3 rejection reason as a named taxonomy
   entry in `engine/grading.py`'s REJECTION_TAXONOMY.

**No live board modification ships without Fable review of the Sonnet PR.**

---

*Registered 2026-07-05. This document is immutable after Fable approval. Results of the
shadow ledger are appended to a SHADOW_LEDGER_REPORT.md file only; this PREREG is never
edited to accommodate live observations. Any deviation from the registered grid is a new
trial in the engine/trial_ledger.*

*2026-07-05 — red-team blocking fixes applied (P2_REDTEAM.md) incl. Fable rulings R-P2.1 (flip floor 100 clusters + 2 quarters) and R-P2.2 (single concordance authority).*
