---
workstream_key: PROPHET-US-V4-RECOVERY
recorded_at: "2026-08-23T01:16:00Z"
changed_at: "2026-08-23T01:16:00Z"
wave: CELL-G
state: in_progress
after:
  - "3049b6f9785e7a08f03d746e0ca909cc425fdbde"
---

# Prophet Cell G — Value of Information / Flagship Measurement Handoff

**Issue:** MAS-123  
**Parent:** MAS-116  
**Owner:** Sol / ChatGPT1  
**PR:** #6276 — `MAS-123: freeze Cell G flagship VOI law + read-only report`  
**Authority:** research + bounded read-only measurement only. No family promotion, rank influence, entry/trade authority, new evaluation store, or new evidence clock.

## Canonical read order

1. `research/prophet_v4/CELL_G_FLAGSHIP_VOI_MEASUREMENT_LAW_2026-08-22.md`
2. MAS-123 / MAS-116
3. `agentos/workstreams/WS-EVAL-OS-MEASUREMENT-LAW.md`
4. `agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md`
5. `research/prophet_fusion/W3_RACE_PREREG.md`
6. `data/us_prophet_rank/w3/status.json` — status only until owner gate opens
7. `engine/qledger_evidence_clock.py` + `data/qledger/evidence_clock_start/`
8. `engine/prophet_voi.py`
9. `engine/prophet_voi_eawc.py`
10. `scripts/prophet_flagship_voi_report.py`

Protected Skillpack used: `mastermindx-market-intelligence/Mastermind@e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`, schema `mastermind.sol_skillpack.v1`, v1.0.0, bootstrap major 1. Refresh before final merge.

## Frozen ruling

There is no universal “Prophet got better” scalar. Discovery value, ranking value, path/risk value, and explanation/product value are separate estimands with separate grains, populations, denominators and authority ceilings. Explanation value never substitutes for alpha.

Load-bearing law:

- `T_eligible` and `T_surface` are distinct clocks.
- Retrieval-changing families are discovery experiments first; never intersect lists and call the result a paired rank study.
- Winner/relevance label, horizon/ruler, K, primary endpoint, minimum effect, multiplicity family and look plan freeze before confirmatory reads.
- NDCG IDCG uses the full fixed candidate population, not only presented top-K.
- Recall uses an independent fixed reference-population denominator.
- Coverage is `covered_applicable / all_applicable`; blocked/missing/refused applicable rows remain in the denominator; true `NOT_APPLICABLE` rows do not.
- Broad-population coverage floor defaults to 70%; sparse families require specialist scope + coverage-selection audit.
- Effective N is a vector: raw subjects plus inverse-HHI concentration-effective counts by decision date, economic issuer, and claimed theme/species axes. It is never substituted as synthetic statistical degrees of freedom.
- Default cross-issuer promotability floor: >=50 matured subjects, `N_eff(date)>=20`, `N_eff(economic_issuer)>=20`; broad theme/species claims require `N_eff>=5`; one group >50% is explicitly dominated.
- Rank metrics are computed per decision session, then aggregated with preregistered dependence treatment; no pooled row pseudo-N.
- One confirmatory primary endpoint. Holm FWER by default for promotion-bearing families; BH is exploratory triage only.
- Fixed-look is default. Repeated reads require preregistered sequential-safe inference.
- Operational LOFO is distinct from refit LOFO; refit creates a new version/clock.
- Negative controls are falsifiers, not positive causal proof.
- Probability calibration is reserved for probability/distribution heads and proper scoring rules.
- Contemporaneous belief, first legal settlement and later corrected truth remain separate vintages.

### Flagship lead gate

With dependence-aware one-sided 95% intervals, positive lead/actionable is better and positive unusable is worse:

- `LEAD_PASS`: LCB(delta lead)>=0 AND LCB(delta actionable)>=0 AND UCB(delta unusable)<=0.
- `LEAD_FAIL`: UCB(delta lead)<0 OR UCB(delta actionable)<0 OR LCB(delta unusable)>0.
- otherwise `LEAD_MIXED`.

Precision gained by waiting until the move is mostly complete is a flagship failure when this lead gate fails. It can only become a separately named conservative-confirmation lane if that lane was preregistered before outcome inspection.

## Reconciled owner state

### Conditional Fusion W3

Lawful status read:
- `comparison_surface=forbidden`
- `structural.outcome_blind=true`
- `paired_sessions_accrued=5`
- `matured_h10_sessions=0`
- `honest_n_floor=20`

**No W3 comparative outcome file was opened.** Report v1 has no comparative outcome loader. If the owner gate later opens, v1 reports `OPEN_OWNER_GATE_ADAPTER_ABSENT`; adding an adapter is a separate reviewed operation.

### QLedger evidence clocks

At reconciliation the canonical forward-clock directory contained `demand_chain` only:
- horizon 126 trading days
- first prospective registration 2026-08-19

No `stock_desk` or `thematic_desk` clock and no matched-control clock directory were found. Do not infer them.

### Current board / V4 substrate

`data/us_board_ledger/retro_grades.parquet` supports lawful descriptive rank/path/coverage telemetry at `(as_of,lane,ticker,horizon)` but not canonical V4 first-surface episode truth. The report therefore refuses rather than fabricates current:
- `T_eligible`
- `T_surface`
- first-surface actionability
- paired lead vs champion
- economic-issuer concentration when identity is absent
- R when frozen initial risk is absent
- payoff/time-underwater when path series is absent

Board observations are never relabelled as V4 episodes. The board ledger spans explicit price/correction eras, including the 2026-08-06 price-basis boundary; pooled board outputs remain `DESCRIPTIVE_ONLY` and cannot become confirmatory family evidence without a homogeneous preregistered cohort/ruler.

### Other prospective owner lanes

Live Entry Radar remains a separate system by `DEC:LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE`. Its W5 preregistration/TrialLedger/look budget and holdout are owner-controlled. Cell G did not open Radar outcome/result artifacts and does not duplicate that gate.

## Bounded implementation

### `engine/prophet_voi.py`
Pure common metric/report primitives: terminal measurement states; effective-N diagnostics; NDCG/precision/recall denominator law; tail ES floor; lead PASS/MIXED/FAIL classifier; fail-closed W3 status; board coverage/refusal semantics; per-session rank diagnostics; path basis/refusal states.

### `engine/prophet_voi_eawc.py`
Pure owner-input EAWC/path primitives, with no repository search or I/O:
- paired `T_eligible`/`T_surface` lead without one-sided lead imputation;
- early actionable capture with all registered positives retained in the denominator;
- first-surface actionability with missing/blocked applicable rows retained;
- unusable-or-unknown guardrail;
- R requiring frozen initial risk/invalidation, never a retrospective stop;
- censored payoff time;
- ex-post move-consumed fraction explicitly descriptive because it uses future-MFE denominator.

### `scripts/prophet_flagship_voi_report.py`
Stdout-only and source-pinned to canonical W3 status, QLedger evidence-clock metadata, and board ledger. No arbitrary input paths, output writer, or promotion consumer.

### Tests
- `tests/test_prophet_voi.py`
- `tests/test_prophet_voi_eawc.py`
- `tests/test_prophet_flagship_voi_report.py`

Synthetic tests pin formulas and refusals; real committed-data smoke asserts zero authority.

## Adversarial defects found and repaired

1. Top-K-only IDCG could erase a better item below K -> IDCG now uses full fixed population.
2. Arbitrary `--w3-status` could read an outcome-bearing JSON before schema rejection -> source-path overrides removed.
3. Pooled rank correlation created pseudo-N across dates -> session-level Spearman only.
4. Coverage applicability mask had Pandas index-alignment defect -> repaired.
5. `(as_of,ticker)` observations were called episodes -> renamed board observations.
6. Missing #1 outcome could distort P@K -> published occupancy, outcome coverage and precision separated; no survivor backfill.
7. `lane_not_stamped` was treated as generic N/A -> excluded only on canonical RAN lane.
8. Lead law existed only at classifier level -> pure EAWC subject-level primitives added.
9. First exact-head semantic CI correctly found three mechanical ownership defects: new test suites were not wired to a CI job, file-path CLI execution lacked the repository-root import pin, and this handoff lacked compiler-visible YAML frontmatter. The latter two are repaired on the branch; CI wiring is the remaining bounded mechanical repair before a fresh exact-head run. A separate missing-blob error occurred during base replay after base tests passed and must not be classified until the owned failures are cleared.

## No-rebuild / no-authority boundary

Do not create a Cell G result ledger, scoreboard, evidence clock, promotion registry, ranker, Availability state, candidate-episode store, correction store or second lifecycle. No family receives predictive/rank authority from this PR. Existing Eval/Fusion prospective promotion remains the only authority path.

## Exact continuation

1. Wire the three Cell G suites into the existing canonical semantic CI job; do not create a parallel workflow.
2. Require fresh exact-head `ci` + `fences` on PR #6276.
3. Review real committed-data smoke and every semantic/fence failure. Do not waive a Cell-G defect as test-only.
4. If only the prior base-replay missing-blob infrastructure error remains, verify the head is unchanged and retry that failed proof once; do not blind-retry ambiguous modifications.
5. Reconcile fresh `main` and current Eval/Fusion/Prophet owners immediately before merge.
6. Refresh protected Skillpack compatibility.
7. Only if all blockers are closed may Sol release the draft hold and merge this zero-authority vertical under the Chairman’s explicit MAS-123 authorization.
8. After merge, future V4/Cell F/A/B owner fields may supply missing first-surface/economic-issuer/path truth. Cell G consumes owner fields; it does not invent substitutes.
9. W3 comparative outcomes remain protected until its existing owner status gate opens; a future adapter is a new reviewed change.
