# Prophet Cell G — Value of Information / Flagship Measurement Handoff

**Issue:** MAS-123  
**Parent:** MAS-116  
**Date:** 2026-08-22  
**Owner session:** Sol / ChatGPT1  
**PR:** #6276 — `MAS-123: freeze Cell G flagship VOI law + read-only report`  
**Authority:** research + bounded read-only measurement only; no family promotion, rank influence, entry/trade authority, or new evaluation store.

## Read first

1. `research/prophet_v4/CELL_G_FLAGSHIP_VOI_MEASUREMENT_LAW_2026-08-22.md`
2. MAS-123 and MAS-116 in Linear
3. `agentos/workstreams/WS-EVAL-OS-MEASUREMENT-LAW.md`
4. `agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md`
5. `research/prophet_fusion/W3_RACE_PREREG.md`
6. `data/us_prophet_rank/w3/status.json` **status only until its owner gate opens**
7. `engine/qledger_evidence_clock.py` + `data/qledger/evidence_clock_start/`
8. `engine/prophet_voi.py`
9. `engine/prophet_voi_eawc.py`
10. `scripts/prophet_flagship_voi_report.py`

Protected Skillpack used for this operation: `mastermindx-market-intelligence/Mastermind@e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`, `mastermind.sol_skillpack.v1`, v1.0.0, bootstrap major 1.

## Frozen ruling

There is no universal “Prophet got better” scalar. A family can create discovery value, ranking value, path/risk value, or explanation/product value; each has its own subject grain, population, denominator and authority ceiling.

Flagship improvement is a conjunction: preregistered primary benefit + lawful clock/version + dependence/multiplicity control + coverage/effective-N scope + integrity/placebo controls + path guardrails + **lead-time preservation**. Explanation value never substitutes for alpha evidence.

### Load-bearing measurement law

- distinguish `T_eligible` (first lawful admission/retrieval eligibility) from `T_surface` (first actual presentation at the registered surface/K);
- winner/relevance labels, horizon, ruler, K and minimum effect are registered before confirmatory outcome reads;
- retrieval-changing families are discovery experiments first; do not intersect lists and call them paired ranking experiments;
- NDCG IDCG is built from the **full same candidate population**, not only the presented top K;
- recall denominator is the independent fixed reference population, never the challenger’s own surfaced set;
- coverage is `covered_applicable / all_applicable`; blocked/missing/refused applicable rows stay in the denominator; by-design `NOT_APPLICABLE` rows do not;
- default broad-population coverage floor is 70%; sparse families may remain specialist-only and require a coverage-selection audit;
- effective N is a vector, not a magic scalar: raw observations plus inverse-HHI concentration-effective counts by date, economic issuer, theme/species where applicable;
- default cross-issuer promotion estimability floor: at least 50 matured subjects plus `N_eff(date) >= 20` and `N_eff(economic_issuer) >= 20`; broad theme/species claims require `N_eff >= 5` on the claimed axis; one group >50% is explicitly dominated;
- session ranking metrics are computed per decision session and then aggregated with the preregistered dependence treatment; no pooled row correlation masquerading as n;
- one confirmatory primary endpoint; Holm FWER by default for promotion-bearing hypothesis families; BH is exploratory triage only and cannot grant authority;
- fixed-look is default; repeated reads require a preregistered sequential-safe design;
- operational LOFO is not refit LOFO; refitting creates a new model/version/clock;
- negative controls are falsifiers, not positive causal proof;
- probabilistic calibration is reserved for actual probability/distribution heads and uses proper scoring rules;
- correction law separates contemporaneous belief, first legal settlement, and later corrected truth.

### Flagship lead law

For dependence-aware one-sided 95% intervals, where positive lead/actionable is better and positive unusable is worse:

- `LEAD_PASS`: lower(`delta_lead`) >= 0 **and** lower(`delta_actionable`) >= 0 **and** upper(`delta_unusable`) <= 0;
- `LEAD_FAIL`: upper(`delta_lead`) < 0 **or** upper(`delta_actionable`) < 0 **or** lower(`delta_unusable`) > 0;
- otherwise `LEAD_MIXED`.

A precision improvement bought by waiting until the move is substantially complete is a flagship failure when the lead gate fails. It can enter a conservative-confirmation lane only if that lane was separately preregistered before outcome inspection.

## Reconciled protected/current state at pickup

### Conditional Fusion W3

At the lawful status read used by Cell G:

- `comparison_surface=forbidden`;
- `outcome_blind=true`;
- 5 paired sessions accrued;
- 0 matured H=10 sessions;
- first lawful comparison floor = 20 matured H=10 sessions.

**No W3 comparative outcome file was opened.** The report v1 has no W3 comparative outcome loader at all. When the owner gate eventually opens, v1 reports `OPEN_OWNER_GATE_ADAPTER_ABSENT`; adding a comparison adapter is a separate reviewed operation.

### QLedger evidence clocks

At reconciliation, the canonical forward-clock directory contained `demand_chain` only:

- declared horizon 126 trading days;
- first prospective registration 2026-08-19;
- write-once clock owner remains Eval OS / QLedger.

`stock_desk` and `thematic_desk` did not have corresponding current clock files, and no matched-control clock directory existed. Do not infer missing clocks.

### Current board / V4 substrate

The committed US board grade ledger can support already-lawful descriptive return/rank/path/coverage telemetry. It does **not** provide canonical V4 episode first-surface truth at the target grain. Therefore the first report refuses rather than fabricates:

- `T_eligible`;
- `T_surface`;
- first-surface actionability;
- paired lead versus champion;
- economic-issuer concentration when issuer identity is absent;
- R when initial risk is absent;
- payoff-time / time-underwater when the path series is absent.

Board `(as_of,lane,ticker,horizon)` observations are never relabelled as V4 episodes. The board ledger also spans explicit price-basis/correction eras, including the 2026-08-06 adjusted-price era boundary. Its pooled board telemetry is therefore **descriptive only**; basis/ranker provenance is surfaced and it cannot become confirmatory family evidence without a homogeneous preregistered cohort/ruler.

## First bounded implementation

### `engine/prophet_voi.py`

Pure common metric/report primitives. Important terminal states are explicit: `MEASURED`, `NOT_MATURE`, `PROTECTED_OUTCOME`, `UNAVAILABLE_FIELD`, `UNESTIMABLE`, `NOT_APPLICABLE`, `DESCRIPTIVE_ONLY`, `HOLD_INTEGRITY`.

It pins:

- concentration-effective counts;
- NDCG/precision/recall denominator law;
- ES tail floor;
- lead PASS/MIXED/FAIL classification;
- fail-closed W3 status gating;
- board coverage/refusal semantics;
- per-session rather than pooled rank diagnostics;
- native path basis and loud unavailable fields.

### `engine/prophet_voi_eawc.py`

Pure executable EAWC/path primitives that consume **owner-resolved** fields only. They never search the repository, reconstruct candidate identity, infer trading calendars, or read outcomes.

Implemented and synthetic-tested:

- paired `T_eligible` / `T_surface` lead using owner-resolved session ordinals, with challenger-only/champion-only/neither cells and **no one-sided lead imputation**;
- early actionable capture recall with all registered positives in the denominator, including misses and blocked actionability;
- first-surface actionability rate with missing/blocked actionability retained in the applicable denominator;
- unusable-or-unknown guardrail where missing owner actionability is conservatively bad rather than favorable;
- realized R requiring frozen initial invalidation/risk, never a retrospective stop;
- strictly-forward time-to-payoff with right censoring for non-hits;
- eventual-move-consumed fraction explicitly `DESCRIPTIVE_ONLY` because it uses an ex-post future-MFE denominator.

Current V4/board truth still does not populate the first-surface inputs, so the report correctly refuses those current metrics even though the formulas themselves are executable.

### `scripts/prophet_flagship_voi_report.py`

Stdout-only. It is **source-pinned** and cannot accept arbitrary W3/Qledger/board paths. It reads only:

- `data/us_prophet_rank/w3/status.json`;
- `data/qledger/evidence_clock_start/*.json`;
- `data/us_board_ledger/retro_grades.parquet` unless `--no-board`.

There is no output writer and no promotion consumer.

### tests

- `tests/test_prophet_voi.py`: formulas, denominator law, W3 fail-closed gating, null/applicability behavior, board refusal behavior.
- `tests/test_prophet_voi_eawc.py`: executable EAWC/lead/actionability/chase/R/censoring semantics.
- `tests/test_prophet_flagship_voi_report.py`: source-pinning plus real committed metadata/board smoke tests that assert zero authority.

## Adversarial defects found and repaired during Sol review

These are important discoveries, not incidental code churn:

1. **Top-K-only IDCG bug:** the first NDCG implementation built its ideal ranking from the presented top K, which could erase a better item below K and overstate quality. Repaired to use the full fixed candidate population; regression test added.
2. **Arbitrary-path outcome-read hole:** an early CLI accepted `--w3-status <path>`. An operator could redirect it to outcome JSON and cause a read before schema rejection. All source-path overrides were removed; source pinning is now tested.
3. **Pooled pseudo-N rank correlation:** an early board diagnostic pooled rows across dates. Replaced with one Spearman value per decision session and unweighted session aggregation; underpowered sessions refuse rather than pool.
4. **Applicability-mask alignment defect:** the first by-design `NOT_APPLICABLE` exclusion could misalign Pandas indexes when enumerating missing reasons. Repaired with aligned indexes.
5. **Board observation semantic inflation:** the early name `n_subject_episodes` was rejected because `(as_of,ticker)` rows are not canonical episodes. Renamed to `n_board_subject_observations`.
6. **Outcome-missing top-K laundering:** published occupancy, outcome coverage and precision are separate. A missing #1 grade cannot promote #2 into P@1 or silently become a loss.
7. **RAN-only null leaked into generic coverage law:** `lane_not_stamped` is a by-design null only for the RAN lane. The first generic exclusion could have hidden a malformed buy row carrying that reason. It is now excluded only when `lane == ran`; on buy/laggard it remains a missing applicable observation.
8. **Law executable only on paper:** the first implementation had the lead gate classifier but not the EAWC subject-level primitives. Added pure owner-input EAWC functions so future V4/Cell F fields can be consumed without redefining denominators later.

## External method anchors

- Järvelin & Kekäläinen (2002): graded relevance and discounted/normalized rank evaluation.
- White (2000): model/specification search on reused data can create chance winners.
- Harvey, Liu & Zhu: finance multiple-testing/search burden requires higher evidentiary discipline than naive t>2.
- Cameron, Gelbach & Miller: multi-way clustered dependence.
- Lipsitch, Tchetgen Tchetgen & Cohen: negative controls detect classes of bias but are not themselves positive causal proof.
- Gneiting & Raftery: strictly proper scoring rules for honest probabilistic forecasts.
- Holm: confirmatory family-wise multiplicity control.
- Howard, Ramdas, McAuliffe & Sekhon / Lan-DeMets: repeated looks require a time-uniform or preregistered spending design.
- Kaplan & Meier: non-hitters stay in the censored risk set rather than being dropped from time-to-payoff analysis.
- Hill (1973): inverse-concentration diversity can be interpreted as an effective number; Cell G uses this only as a concentration/scope diagnostic, not an inferential sample-size substitute.

## No-rebuild / no-authority boundary

Do not create a Cell G result ledger, scoreboard, evidence clock, promotion registry, ranker, Availability state, candidate-episode store, correction store or second lifecycle. The read-only report is a projection over existing owner truth.

No family receives predictive/rank authority from this PR. Existing Eval/Fusion prospective promotion remains the only authority path.

## Exact continuation

1. Require exact-head `ci` + `fences` on PR #6276.
2. Review the actual committed-data smoke result and all semantic/fence failures; do not waive a Cell-G-owned defect as “test-only.”
3. Reconcile fresh `main` immediately before merge; if a material Eval/Fusion/Prophet-owner collision appeared, stop and reconcile instead of blind rebasing/failing over.
4. If green and collision-free, Sol may release the draft hold and merge this bounded zero-authority vertical under the Chairman’s explicit MAS-123 authorization.
5. After merge, future Cells A/F/B and the V4 canonical episode/Availability owners may supply missing first-surface/economic-issuer/path fields. Cell G consumes those owner fields; it does not invent substitutes.
6. W3 outcomes remain protected until the existing status gate opens. A future comparison adapter must bind the frozen Cell G law and then undergo a fresh reviewed change.
7. Any future family experiment must register its exact version, claim type, population, clock, horizon/ruler, K/label, minimum effect, multiplicity family and look plan **before** the confirmatory clock/result read.

**Current stop condition:** if exact-head CI is not green or the real-data smoke exposes a denominator/clock/authority defect, keep #6276 draft and repair only within this bounded measurement surface. Do not promote anything as a workaround.
