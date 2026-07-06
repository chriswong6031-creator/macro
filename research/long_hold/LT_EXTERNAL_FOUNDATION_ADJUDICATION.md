# LT External Foundation — Adjudication of the Codex Long-Term Thesis Signal paper

**Ratified:** 2026-07-06 (operator + Fable, ultracode build authorization)
**Source paper:** `research/long_hold/LONG_TERM_THESIS_SIGNAL_RESEARCH_FOR_FABLE.md` (external ChatGPT/Codex paper, committed as-received for provenance)
**Assessment method:** 4-lane repo census (Sonnet: program state, data inventory, gauntlet/registry infra, adjacent-program overlap) + Fable adjudication with first-hand verification of contested scorecard facts. Companion to `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`.
**Program status:** LT waves LT-0..LT-4 AUTHORIZED (display/research tier only; zero behavioral surfaces; W3/W4 remain LOCKED per the G1-DEFERRED ruling).

---

## 0. Verdict on the source paper

Epistemically house-compatible and directionally right: staged admission instead of a fused score, falsifiers before conviction, replication before novelty, display-only until gauntleted. Its funnel architecture (Stages A–G) and recommendation R4 (expectation drift, not another quality ratio, is the missing edge) are adopted. But the paper was written blind to (1) what is already shipped/tested/cut in this repo, (2) the FDR economics of LH-R11, and (3) the honest-n calendar (G1-Retest ~2027-H2). Roughly 60–70% of its build list is redundant or already adjudicated; the genuinely new, buildable core is the expectation-drift event family, the capital-allocation/buyback-execution lane, the data repair that unblocks both, and forward-accrual arming for data we cannot buy retroactively.

## 1. Section-by-section adjudication

| Paper element | Ruling | Evidence / disposition |
|---|---|---|
| §2.1–2.4, 2.5, 2.7, 2.8, 2.9, 2.10 external factor families (QMJ/MSCI/S&P quality, gross profitability, accruals, asset growth, net issuance, shareholder yield) | **ALREADY SHIPPED + ALREADY MEASURED** | Factor legs live in `engine/equity_factors.py`. Deep window (`ic_scorecard.json`, 2011-2025, 60 rebalances, survivorship-biased): all ~null except payout (q=0.0715). Shallow PIT window (`sue_phase0.json`, 2023-2025): quality significantly NEGATIVE (IC −0.0358, q=0.069). No replication wave is built (LH-R13); long-hold-ruler variants enter only via the A2 roster |
| §2.6 Piotroski F | **ALREADY CENTRAL** | W1 kill-test headline feature (RBC 0.75–0.81, q≈0, every floor-met cell; survivorship-caveated). Coverage repairs (op_income, interest_exp) are retest-critical → wave LT-1 |
| §2.11 momentum / RS repair | **CUT** | Species S7 rs_repair phase0: NULL / wrong sign (graveyard). Raw momentum is entry-vocabulary; not a long-hold family |
| §2.12 low-vol / BAB / safety | **CUT as family; display context only** | low_beta q=0.52–0.93 both windows; low_vol null. "Holdability" stays a display annotation, never a roster family |
| §2.13 SUE/PEAD | **ADOPT, reshaped → expect_drift family** | `engine/sue.py` shipped; survives shallow FDR (t=2.78, q=0.059), dead deep (IC 0.0006, survivorship-confounded). Event-behavior features (absorption/hold/drift) are genuinely absent → `EXPECT_DRIFT_FAMILY_PREREG.md` |
| §2.14 analyst revisions | **ACCRUAL-ONLY** | 3 weeks of history; yfinance snapshots are lookahead in backtests; revenue revisions structurally unavailable. Forward accrual continues (started 2026-06-16); earliest testable ~mid-2027. No registered hypotheses now |
| §2.15 insider buying | **ADOPT → insider_sponsor_lh family** | 2.3M Form-4 rows 2006→; `net_usd_mcap` survives BH-FDR in mid/small habitat (IC 0.029, t=2.9, `research/INSIDER_FACTOR.md`). W1 dropped `insider_cmp` for 0% panel coverage — restoration is retest-critical → LT-3. Entry-ruler tests stay with ESX Amendment 2 RUL-26 (no duplication) |
| §3.1 Long-Term Thesis Feature Store (new monolith parquet) | **KILL as monolith** | Violates file-bus convention and duplicates `fundamentals_panel`/`statements`/W2 compounder columns. Per-family panels only (expect_drift panel, insider join), extending existing stores |
| §3.2 expectation ledger | **ADOPT v1 (display)** | Rides the expect_drift feature panel + per-stock display block (LT-2), not a new ledger system |
| §3.3 capital allocation ledger | **ADOPT v1, reshaped** | First consumer of `statements_quarterly.repurchases` (zero readers today) + SBC post-backfill → deterministic `capital_allocation_delta ∈ {accretive, neutral, dilutive, unavailable}` display block (LT-3). No composite |
| §3.4 business-model ontology | **STAYS CUT/DEFERRED** | W3 PR-N already scopes the only sanctioned version (GICS + financial-shape heuristics). No 10-class taxonomy is built |
| §3.5 KPI registry | **STAYS CUT** | Paid-data SKIP-ALL ruling 2026-07-05 unchanged |
| §3.6 valuation-implied expectations engine | **STAYS W3-LOCKED** | Already adjudicated (masterplan W3 PR-N, EV/sales-only v1). Not built early; G1/G2 gates unchanged |
| §3.7 sponsorship/ownership layer | **PARTIAL ADOPT** | Insider (family) + buyback execution (display) in LT-3. 13F stays 17-fund curated context (no broad collector — 45d lag, low ROI). Short interest: FAILED FDR (q=0.375 shallow; one census lane misreported this as a survivor — corrected here); display context + history accrual only |
| §4 admission funnel Stages A–G | **ADOPT as LT-4 shadow funnel** | LH-R2-compliant: transparent AND-gate of independently registered flags; states stop at `thesis_candidate_shadow` (W3 lock). No composite, no behavioral surface |
| §5.1–5.15 novel families (15 proposed) | **ADMIT 2, DEFER the rest** | Only expect_drift (§5.3/5.4 core) and insider sponsorship enter the roster. §5.5 downside-beta-collapse: `downside_asym()` exists unwired, low_beta null — deferred, not registered. §5.8/5.9/5.10/5.13/5.14: mechanism-plausible but data-blocked or Σ-unaffordable now; parked in §5 of this doc's successor queue |
| §6 methodology | **ADOPT where it matches OBJECTIVE.md** | Episode-clustering, PIT stamps, printed nulls already law (LH-R3/R4). Paper's per-family testing menu (7 comparisons/family) is Σ-inflationary → rejected; one ruler-P contrast + one ruler-H contrast per family |
| §7 build plan LT-0..LT-5 | **SUPERSEDED by §3 below** | Paper's LT-0/LT-1 (replication pack/study) collapse into LH-R13 calibration stance + A2 roster; its LT-2..LT-4 map onto our LT-2..LT-4 |
| §9 R1–R7 recommendations | R1 reshaped (no replication wave); R2 ADOPTED (washout_tf separate family — already law via LH-R11); R3 ADOPTED (LT-4 survival gate); R4 ADOPTED (expect_drift is the centerpiece); R5 already law (moat falsifiers shipped); R6 ADOPTED (research DB not buy-list); R7 already law (LH-R3) |

## 2. New rulings (ratified 2026-07-06; appended to masterplan §3)

- **LH-R11 RATIFIED** as drafted Rev-2 (`AMENDMENT_LH_R11_MULTI_FAMILY.md`): fixed roster + A2-script freeze anchor + DEFERRED window open; program-wide HLZ/BH-FDR q=0.10 over Σ registered hypotheses as sole ratifying correction; per-feature admissibility with `restricted_range`/`feature_provenance` stamps. The washout-timeframe family (#2) is admitted to the roster.
- **LH-R12 (program hypothesis ceiling).** Σ registered hypotheses across all long_hold roster families ≤ **40**. Any addition beyond the ceiling requires dropping registered hypotheses by amendment. Current Σ after A2 registration: **29** (F1 fundamental 9, F2 washout_tf 10, F3 expect_drift 7, F4 insider_sponsor_lh 3).
- **LH-R13 (calibration, not discovery).** External-factor "replication" confers zero authority: the generic cross-sectional IC replication already exists (`ic_scorecard.json`, `sue_phase0.json`) and is not re-run as long-hold work. Externally-validated factor features enter the program only as roster-family features at the long-hold ruler, counted in Σ like any other hypothesis.
- **LH-R14 (two-ruler discipline).** Each roster family declares exactly two rulers: **Ruler-P** (powered, near-term): `cheap_trap` vs `tactical_only` at 252d on fires with fire_date ≤ 2023-12-31 only (no contact with the OOS-2 2025+ cohort), survivorship-stamped, authority ceiling = display; and **Ruler-H** (honest, ratifying): `missed_hold` contrast on OOS-2 at the G1-Retest under program-wide FDR. Ruler-P results may gate display shipping but can never produce SURVIVE/KILL for the selection-alpha thesis.

## 3. Build contract (waves LT-1..LT-4)

All PRs: branch off fresh origin/main, same-day squash-merge, display/research tier, off-render compute, `fdr_family='long_hold'`, survivorship stamps per LH-R3. Model routing: Sonnet builds, Opus reviews, Fable merges/adjudicates.

- **LT-1 Data repair:** (a) collector fixes — `edgar_facts.py` shares extraction bug, `period_end` written per statements row (PIT gate currently fails open), not-yet-filed FY purge; (b) off-render backfill run refreshing `statements.parquet` (populates depreciation/SBC/R&D per shipped PR-H FLOW dict) + coverage report; (c) `fundamentals_panel` retest fields (op_income, interest_exp, capex) + sector map expansion 503→~2,589 via `cik_sic.json` (fixes the `sector_laggard_winner` benchmark artifact, 3,386/3,404 rows unbenchmarked).
- **LT-2 Expectation drift:** (a) PIT feature panel builder per `EXPECT_DRIFT_FAMILY_PREREG.md` → `data/research/expect_drift_panel.parquet`; (b) Ruler-P study (TrialLedger-registered, episode-clustered, reshuffle null, eras, printed nulls) → results doc; (c) per-stock "expectation state" display block (display-only, `hold_thesis`, synapse-registered).
- **LT-3 Sponsorship + capital allocation:** (a) buyback-execution reader on `statements_quarterly` → `capital_allocation_delta` display block; (b) insider fire-date join restoring `insider_cmp` coverage for the retest + Ruler-P run per `INSIDER_SPONSOR_LH_FAMILY_PREREG.md`; (c) forward-accrual arming: `short_interest_history.parquet` population + experiments-registry clock entries.
- **LT-4 Thesis funnel shadow:** `not_eligible → watch_for_thesis → thesis_candidate_shadow` as an AND-gate of independently registered flags (survival gate: no dilution trap, no severe accrual/receivables/inventory falsifier, solvency floor, moat falsifiers clean) + context blocks from W2/LT-2/LT-3. Per-stock chip + counts board. Ceiling `thesis_candidate_shadow` until W3 unlock. BC-2-safe language.

## 4. What was deliberately not built (standing queue)

Downside-beta-collapse family (revisit if `downside_asym` earns wiring elsewhere); competitive-capacity-withdrawal (§5.8 — needs peer capex panels); sector-denominator-collapse (§5.14 — needs full sector revenue panels); founder-recoupling (§5.13 — needs role parsing beyond is_officer); theme-to-cashflow (standing CUT); duration-arbitrage (§5.11 — blocked on revisions accrual); quality-detox (§5.12 — revisit with crowding data at A2). Each may be proposed as a roster amendment under LH-R12's ceiling.
