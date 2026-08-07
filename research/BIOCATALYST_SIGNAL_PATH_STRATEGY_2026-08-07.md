# BioCatalyst — the signal path: why the program is stuck, and the four moves that unstick it

| Field | Value |
|---|---|
| Status | Strategy ruling. Authorizes nothing; activates nothing; promotes nothing |
| Written | 2026-08-07, Claude/Fable commissioning session |
| Companion | `research/BIOCATALYST_CONTINUATION_HANDOFF_2026-08-06_CLAUDE.md` (operational state), `research/BIOCATALYST_PARITY_LEDGER_2026-08-06.md` (the 32-row denominator) |
| Question answered | "Can we derive signals from BioCatalyst, or use it as a contextual layer, to help pharma picks?" |

## 1. The answer in three lines

- **A contextual layer already exists and is already live — but it is NOT BioCatalyst.** It is
  `engine/theme_clinical.py`, and it already reaches Neural Web and Mastermind.
- **There is no authorized signal, deliberately.** That layer is `is_context_only: True`,
  display-tier, "never scored", and explicitly forbidden from folding into `fused_obs_z`.
- **The blocker is not a missing feature. It is that the two clinical planes in this repo have
  exactly complementary defects and have never been connected.**

## 2. The two planes

### Plane A — `theme_clinical` (live, shipped, flowing to the brain)

```
collectors/clinicaltrials_themes.py → engine/theme_clinical.py
  config/clinical_modalities.yml   5 modality queries, AREA[LeadSponsorClass]INDUSTRY,
                                   precision-capped < ~2,000 studies/query
  → theme_id → config/theme_crosswalk.yml → basket_ids → data/baskets/membership.json
  → consumed by engine/neuralweb/{cortex,ask_brain,brain_gateway}.py
```

Computes registration YoY, enrollment YoY, magnitude band, velocity read, phase distribution —
a **capital-commitment read** per theme. It joins to price **without any per-company identity**,
by aggregating to a theme that maps to baskets.

Authority, from `engine/theme_clinical.py` itself:

- line 5 — `is_context_only=true`
- line 21 — "Never fold into `fused_obs_z` — separate display leg only."
- line 59 — "Authority block (display-tier; never scored)"

**Its defect is the store.** Per `DNR:KILL-PHASE3-START-WEIGHT` and the config's own header:
top-100-per-sponsor by last-update, **look-ahead-selected pre-2019**, phase recorded
*as-of-ingest* rather than point-in-time, and "cross-cohort phase delta is confounded."

### Plane B — BioCatalyst

Per-trial, NCT-keyed, evidence-grade: exact field diffs, effective vs known-at time, correction
lineage, replay, fail-closed unavailable states. **Its defects are reach and identity** — a
1–25 NCT fixed cohort against ~500,000 registered studies, transport still dark, and no eligible
issuer/security bridge (2 of 6 shared-plane adapters eligible).

### The synthesis

| | Price join | Scale | PIT integrity |
|---|---|---|---|
| `theme_clinical` | **yes**, via baskets | **yes** | **no** — look-ahead, non-PIT |
| BioCatalyst | no | no | **yes** |

**Neither can produce an authorized signal alone.** Plane A can never be gauntleted on its own
history, because look-ahead selection is baked into the store and cannot be cleaned
retroactively. Plane B has the apparatus that would make a clinical signal *testable* and has
been built in isolation from the pipeline that has the price join.

## 3. Why there is no signal today, on evidence

`DNR:KILL-PHASE3-START-WEIGHT` killed Phase-3 START as a scored catalyst leg, twice,
independently. The 2026-08-03 replication is the decisive one: on 1,156 ticker-date cells the
**day-0 abnormal return is −0.9bp, t = −0.17**. A public registry posting with no same-day
reaction is not information. A random-date placebo reproduced **~70%** of the apparent
XLV-benchmark effect (empirical p = 0.186), and 36% of the CAAR accrued *before* the event.

The kill is construction-scoped, and two doors are explicitly left open:

1. **The HALT channel** — halt / suspension / termination is a different event class from START
   (rarer, negative-direction, less anticipated). Blocked on ClinicalTrials.gov **Record
   History** for a true halt-onset date; Record History production ingest is not allowed.
2. **Any re-test** requires collector pagination first (to fix the look-ahead store) **and** a
   fresh pre-registration. Neither exists.

## 4. The four moves, ranked

### CORRECTION (2026-08-07, from the built evidence) — Move 1 IS blocked, on a SOURCE

This section originally said Move 1 was "not blocked", reasoning that trial outcome families
are NCT-keyed and therefore need no ticker. **The identity half was right and the conclusion
was wrong.** The `BC-O1b` build (PR #4944) evaluated every family's entry gate against the real
registry and found that **no family clock can open today**, for a reason I had not checked:

- Every trial family's gate names **`clinicaltrials_gov_record_history`**, which carries
  `production_ingest_allowed: false` and `rights_state: operator_review_required_before_enable`.
- `timing_slip` and `enrollment_site_change` require **only** that source.
  `trial_progression_termination` and `endpoint_readout` require it alongside `clinicaltrials_gov_v2`.
- Measured on `origin/main`: **exactly 1 of 8** registered BioCatalyst sources is
  production-ingest-allowed.

I checked the identity gate, found it clear, and stopped — naming the first gate I checked
rather than the one that actually binds. The corrected statement is:

> **Forward accrual is blocked on a SOURCE ACTIVATION decision, not on identity.** The clock
> cannot start until an operator completes a rights review and enables Record History ingest.

**One operator act unblocks three families.** Flipping `production_ingest_allowed: true` on
`clinicaltrials_gov_record_history` opens `trial_progression_termination`, `timing_slip` and
`enrollment_site_change` on the next evaluation **with no code change**. That is pinned by
`tests/test_biocatalyst_m0a_clock_activation.py::test_the_trial_families_would_open_once_their_source_is_eligible`,
which runs the evaluator against a widened registry and asserts `clock_state == opened` with
zero blockers. `endpoint_readout` stays closed even then, on a second declared blocker
(`endpoint_alignment_review_queue_not_drained`).

**Why nothing was opened anyway.** Opening a clock over an un-ingestable source would accrue
nothing while later reading as "accruing since 2026-08-07" — precisely the fabrication this
program exists to prevent. The machinery is built, tested, and inert; the receipt is the
authority, not the config file, so no edit can claim an open clock.

**Consequence for the ranking below:** Move 1 remains the highest-value move and its *code* is
now done, but its clock is an **operator decision**, and that decision is the single highest-value
action available to this program. Everything downstream — calibration, promotion, any clinical
signal at all — is gated behind it, and every day it waits is a day of forward evidence never
recorded.

### Move 1 — START THE FORWARD CLOCK (`BC-O1b` + `M0a` family activation). Do this first.

Highest time-value and **not blocked**. Trial-level outcome families — progression/termination,
timing slips, enrollment/site changes, endpoint readouts — are **NCT-keyed and need no ticker**.

The argument is forcing: the retrospective store's look-ahead selection cannot be undone, so
**forward accrual is the only clean evidence this program will ever have**. Every day not
accruing pushes the earliest possible promotion date out by exactly one day. `BC-O1a` shipped
(#4814) and is the substrate; `M0a` policy shipped with it. `O1b` extends `O1a` with append-only
homes for feature snapshots, forecasts, outcomes, model registrations, evaluation manifests and
contribution traces — reusing `O1a`'s single-writer, idempotency, correction and replay
semantics. Open each family's clock the moment its policy + inputs + writer exist. Record
nothing retrospectively; never backfill a "first seen".

### Move 2 — FEED `theme_clinical` FROM BioCatalyst's PIT PLANE. Cheapest real win.

Needs **no identity work at all** — theme rollups are counts, phase distributions and YoY
velocities, aggregated to a theme. Replacing a confounded store with a point-in-time,
correction-aware one is what makes the *existing live layer* gauntlet-able. This is the first
piece of work in this program that improves a shipped surface instead of adding a new one.
Keep the authority block exactly as it is (`is_context_only`, never scored) — this move improves
the evidence, it does not promote anything.

### Move 3 — `B1S4` COVERAGE EXPANSION with recorded denominators.

25 trials → theme scale, in measured epochs, each binding one `discovery_scope.v1` policy,
immutable run + coverage-epoch receipts, exact pagination/termination behavior, and a recorded
coverage denominator with known exclusions. Prerequisite for Move 2 at scale. A coverage claim is
earned by the recorded denominator, never by the breadth of a query string.

### Move 4 — A REVIEWED SPONSOR → TICKER MAP, scoped to the 70 healthcare names.

**Not** a general PIT identity service. The tradeable healthcare universe is small and countable:

| basket | names |
|---|---:|
| `us_sector_health` | 59 |
| `obesity_glp1` | 14 |
| `big_pharma` | 10 |
| `managed_care` | 9 |
| **distinct** | **70** |

A bounded, curated, PR-reviewed lookup with effective intervals, provenance and an ambiguity
review queue is **lawful under W3-C** ("LLM-suggested links remain candidates until deterministic
or reviewed admission") in a way that an inferred join is not. It unlocks `BC-P1` post-selection
context: Prophet picks a name, BioCatalyst explains that name's trial and regulatory state
*after* selection, never originating or reordering a candidate. 70 names is a day of curation.

## 5. What NOT to do

**Do not build more Wave 4/5/6 product surfaces.** The parity ledger already records six rows
with shipped, tested backends and no user-reachable surface. More dossiers, lenses and calendars
against a plane with ~0 coverage and no forward evidence add surface, not capability. Every hour
spent there is an hour the forward clock is not running.

## 6. Honest timeline

A **gauntleted** clinical signal is a **2027+ prospect at the earliest**, and only if the clock
starts now: matured, censored, correction-aware outcomes need roughly 12–24 months of forward
accrual before a pre-registered test is even possible. Anyone promising sooner is proposing to
test on the contaminated store.

What is usable **today** is the theme layer as basket-level capital-commitment context — already
flowing to Mastermind, already honestly labelled as context rather than a buy signal. That is a
real product capability and it should be described as exactly what it is.
