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
8. `engine/prophet_voi.py` + `scripts/prophet_flagship_voi_report.py`

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

Board `(as_of,lane,ticker,horizon)` observations are never relabelled as V4 episodes.

## First bounded implementation

### `engine/prophet_voi.py`

Pure formulas and derived summaries only. Important terminal states are explicit: `MEASURED`, `NOT_MATURE`, `PROTECTED_OUTCOME`, `UNAVAILABLE_FIELD`, `UNESTIMABLE`, `NOT_APPLICABLE`, `DESCRIPTIVE_ONLY`, `HOLD_INTEGRITY`.

### `scripts/prophet_flagship_voi_report.py`

Stdout-only. It is **source-pinned** and cannot accept arbitrary W3/Qledger/board paths. It reads only:

- `data/us_prophet_rank/w3/status.json`;
- `data/qledger/evidence_clock_start/*.json`;
- `data/us_board_ledger/retro_grades.parquet` unless `--no-board`.

There is no output writer and no promotion consumer.

### tests

Synthetic tests pin formulas/denominators/refusals, and real-data smoke tests execute the report over the currently committed owner surfaces while asserting zero authority.

## Adversarial defects found and repaired during Sol review

These are important discoveries, not incidental code churn:

1. **Top-K-only IDCG bug:** the first NDCG implementation built its ideal ranking from the presented top K, which could erase a better item below K and overstate quality. Repaired to use the full fixed candidate population; regression test added.
2. **Arbitrary-path outcome-read hole:** an early CLI accepted `--w3-status <path>`. An operator could redirect it to outcome JSON and cause a read before schema rejection. All source-path overrides were removed; source pinning is now tested.
3. **Pooled pseudo-N rank correlation:** an early board diagnostic pooled rows across dates. Replaced with one Spearman value per decision session and unweighted session aggregation; underpowered sessions refuse rather than pool.
4. **Applicability-mask alignment defect:** the first by-design `NOT_APPLICABLE` exclusion could misalign Pandas indexes when enumerating missing reasons. Repaired and pinned with a `lane_not_stamped` denominator test.
5. **Board observation semantic inflation:** the early name `n_subject_episodes` was rejected because `(as_of,ticker)` rows are not canonical episodes. Renamed to `n_board_subject_observations`.
6. **Outcome-missing top-K laundering:** published occupancy, outcome coverage and precision are separate. A missing #1 grade cannot promote #2 into P@1 or silently become a loss.

## External method anchors

- Järvelin & Kekäläinen (2002): graded relevance and discounted/normalized rank evaluation.
- White (2000): model/specification search on reused data can create chance winners.
- Harvey, Liu & Zhu: finance multiple-testing/search burden requires higher evidentiary discipline than naive t>2.
- Cameron, Gelbach & Miller: multi-way clustered dependence.
- Lipsitch, Tchetgen Tchetgen & Cohen: negative controls detect classes of bias but are not themselves positive causal proof.
- Gneiting & Raftery: strictly proper scoring rules for honest probabilistic forecasts.
- Holm: confirmatory family-wise multiplicity control.
- Lan-DeMets / modern confidence-sequence methods: repeated looks require a design valid under sequential monitoring.

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

**Current stop condition:** if exact-head CI is not green or the real-data smoke exposes a denominator/clock/authority defect, keep #6276 draft and repair only within this bounded measurement surface. Do not promote anything as a workaround.
