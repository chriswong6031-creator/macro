# IMCE-00 — Issuer Mechanism Cycle Extension: Architecture Freeze
## Fable Round 3 adjudication of the ten binding decisions, worker evidence, and authorized research waves

**Adjudicator:** Fable, COO / principal orchestrator
**Commissioned by:** Sol (AI CEO), `FABLE_IMCE_ROUND3_ORCHESTRATOR_HANDOFF_BY_SOL.md`; Chairman: Chris
**Date:** 2026-08-20
**Status:** **ACCEPTED ARCHITECTURE FREEZE — records only.** No runtime, schema grant, collector, model, score, screener, page, Radar/Prophet/sizing path, or trading authority is created by this document. All authority flags are false at birth.
**Merge state:** review-ready for Sol/Chairman per handoff §13. **HOLD-FOR-SOL — do not merge without Sol/Chairman release.**
**Main pins:** Sol observed `e186f9f4` then `b38c6134`; this session re-pinned `origin/main` at `9dcd4c24a547` (ff-only into the designated local root) and authored this freeze from a fresh worktree based at `a36e5e70f069` (descendant of the session pin — main moved forward during the pass; verified `git merge-base --is-ancestor`).

---

# 0. Outcome

**GO — IMCE is accepted as a bounded, records-only research extension under Cycle Pattern Intelligence (CPI), with the federated owner map frozen below and a measurement contract whose historical-arm statuses are predetermined by census before any outcome is computed.**

The single most important finding of the whole round, and the reason this freeze is safe to accept:

> **No pilot family can reach the preregistration's 40-effective-block promotion floor from historical data — not homebuilders (~5–7 blocks), not memory (2 completed + 1 open), not banks (~3, and 0 PIT-clean).** Every historical trial cell's status outcome is therefore fixed *now*, invariant to the data: `underpowered_accruing`. The historical arm is instrumentation and design validation, never a promotion path. The program's honest posture is **descriptive research + prospective accrual**, and this freeze writes that down before any number exists to tempt anyone otherwise.

A records-only CELH Cycle Autopsy, a homebuilder source/definition census, a CPI truth-contract audit, and an amended preregistration candidate are the authorized next waves (§13) — **after Sol accepts this freeze**. Nothing auto-rolls.

## Acceptance gates for this freeze (per Sol handoff §12)

| Gate | State |
|---|---|
| Current-main SHA + open-PR audit | §1 — done, receipts inline |
| No duplicate system | §2 D1/D3, §3 — zero collisions found (G0) |
| Exact owner/port matrix | §3 |
| Episode anchor resolved or refused | §4 — composed binding, no new ID; `identity_epoch` typed `not_yet_built` |
| Architecture/capability/source-rights ledgers | §11, §8 |
| Four-pilot dispositions | §7 |
| Executable preregistration draft, no outcome run | `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` + `.yaml` (amended per §9; no run performed) |
| AgentOS validation | `python3 scripts/agentos.py validate` exit 0 (run before PR) |
| Changed-path proof: no runtime/data/UI/workflow changes | §14 |
| Explicit all-false authority | §12 |
| Red-team verdict and dispositions | §10 (G8 row) |
| Exact next authorized wave and stop | §13 |

---

# 1. Reconciliation ledger — estate movement verified this session

| Claim in Round 3 packet | Verified state (this session, receipts) |
|---|---|
| Stock Identity W2 merged; workstream stale | CONFIRMED. PR #5643 `MERGED 2026-08-16T18:48:33Z` (`gh pr view`), yet `agentos/workstreams/WS-STOCK-IDENTITY.md:53` still read `status: in_progress` with two pre-merge `next_action` fields. **Healed in this PR** (W2 → `done`; next_action updated; W3–W7 untouched — no evidence they started). |
| FIF-2A "accepted, not landed" | MOVED SINCE SOL'S PASS. PR #5983 `MERGED 2026-08-20T05:28:35Z`. Fixture-proven query bridge (`app/forensics.py`, `engine/fundamental_forensics/query_service.py`; tests reference `fip1_fixture_dataset` only) — **not** a production issuer feed. Capability ledger updated (§11). |
| Earnings Macro dossier #6021 held/draft | CONFIRMED. `OPEN`, `isDraft: true`, title carries `[HOLD]`. A recorded hold is a merge barrier; treated as not-landed; untouched by this session. |
| No `rf.cycle_pattern.imce*` family | CONFIRMED. `data/trial_ledger.jsonl` (1,665 rows) has zero `imce` occurrences; existing cycle_pattern families: `cycle_pattern_analog`, `cycle_pattern_ft`, `rf.cycle_pattern.{ft_v0,ft_v1,ix_v0,lattice_v0,lattice_v1,tr_v0}`. |
| No IMCE naming collision | CONFIRMED. Zero hits for `IMCE`/`issuer_mechanism_cycle` across `research/`, `agentos/`, `docs/`, `config/`. The only adjacent "Cycle Intelligence"-branded lane is #5821 (Biopharma Cycle Intelligence OS, DRAFT) — domain-scoped, no overlap. |
| HAR-1 analogue null binding | CONFIRMED AND LOCATED. `CPI-017` in `data/cycle_pattern/truths.jsonl` is `promoted_null` — "HAR-1: Historical-analog kNN retrieval over normalized completed half-cycles." Standing prior against generic analogues; Market Memory remains the generic-retrieval owner. |
| CPI truth-schema vocabulary defect | CONFIRMED, with the characterization corrected by the red team [G8-M1]: the schema-doc list and the matrix are NOT disjoint (they agree on `research_factory` and on all four money-path forbidden names) — the real defect is **at least FOUR coexisting consumer vocabularies across the 29 registry rows**, split by naming family rather than age (CPI-017, the newest CPI-nnn row, carries the schema-doc vocabulary), including orphan tokens registered in NEITHER authority (`display_descriptive` CPI-013, `research_factory_intake` CPI-015, `display`/`display_only` CPI-016). The guard (`scripts/check_cycle_pattern_authority.py:34-38`) is a literal-path scan that cannot catch any of this. D-4 audit — re-scoped to full token enumeration over all 29 rows (§13 A2) — is mandatory before any issuer truth is appended (§2 D1 condition c). |

Binding DNR rows found (G0): `DNR:KILL-ROTATION-CYCLE-CONFLUENCE` (no rotation × cycle-position entry confluence) and `DNR:KILL-OUTCOME-AUDITION` (TWO-RULER; no per-name best-of-grid selection — restated as pilot law in §7 and contract law in the prereg). No DNR row kills issuer-mechanism research itself.

---

# 2. The ten decisions

## D1 — Parent and scope: **CPI/cycle-pattern is the parent. Research-only single-equity exception RATIFIED.**

IMCE extends the existing cycle-pattern research and truth-governance plane. G0's census found no newer or more specific owner (zero `WS-CYCLE-PATTERN*` records; CPI is the only cycle-branded owner with a truth registry, consumer matrix, and CI authority guard), and CPI's schema carries issuer/family scope without modification (`truth_schema.md:24` — `scope.families` + `sample`). The research-only single-equity exception does **not** reopen broad CPI runtime: no broad lake ingestion, no public issuer-cycle probabilities, no screener, no money-path consumers.

Conditions: (a) any future IMCE reader module path must be added to `check_cycle_pattern_authority.py`'s `_ALLOWED_READER_PREFIXES` — mechanical, deferred to the first wave that writes a reader (IMCE-04+); (b) `DNR:KILL-ROTATION-CYCLE-CONFLUENCE`, `DNR:KILL-OUTCOME-AUDITION`, **and `DNR:KILL-CAUSAL-DAG-ALPHA` [G8-M3]** (causal graph → alpha score → trade is FORBIDDEN; hand-curated mechanism graphs do not escape the kill — proposal/audit tier only) bind on construction; (c) **no issuer truth is appended to the CPI registry until the D-4 vocabulary audit (§13 wave A2) lands** — the registry's rows carry at least four consumer vocabularies including orphan tokens (§1).

## D2 — Canonical episode anchor: **Composed binding. No new episode ID. `identity_epoch` typed `not_yet_built`.**

An IMCE research case is a dossier record binding existing owners' keys, with one amendment to Sol's composition forced by repo truth (G0): no single `episode_id` field exists anywhere on disk, and Stock Identity's identity-epoch proper is **unbuilt** — W4 "Epoch detector v1" is `status: todo`; `engine/stock_identity/fingerprint.py:291-292` carries only a provisional `epoch_key: "epoch_0"` placeholder.

```text
Data OS company_id + security_id            (engine/company_intelligence/identity.py, context_only, typed refusals)
  + Stock Identity identity_epoch            → typed not_yet_built until W4 ships
  + 0..n Stock Identity path-episode refs    (engine/stock_identity/episodes.py Episode rows — no single id field; cite the tuple)
  + 0..n canonical source_event / event_workspace IDs
  + 0..n FIF packet/cell IDs
  + 1..n Market Memory as_known_at context IDs
  + exact mechanism observation/evidence references
```

**Episode-citation hardening [G8-M4]:** the `Episode` dataclass is keyed by `symbol` (plus `price_plane_id`, dates, type) and carries no `company_id`/`security_id`, while §3 bans ticker-as-identity — so every IMCE Episode citation MUST carry the resolving `security_id` from `identity.py` alongside the tuple. And because the episode catalog is regenerated (rows carry `resolution="censored"` and mutate as episodes resolve), every citation MUST carry a `catalog_as_of` stamp; the missingness vocabulary gains `superseded_by_recompute` for a cited row whose referent has since changed.

**Mechanism epochs are a distinct record class, not a rival identity-epoch stack [G8-M5]:** an IMCE *mechanism epoch* is a structural-business partition drawn from corporate events (distribution agreements, acquisitions, accounting regimes) on the operating/translation clocks; Stock Identity's *identity epoch* (W4, unbuilt) is a behavioral-tape partition. They are different objects with different sources, are recorded under different names, and are never conflated or substituted; when W4 ships, any crosswalk between them is a separately registered question. This is the explicit non-overlap statement §3's "no rival epoch stack" row requires.

Typed missingness per reference: `present | not_yet_built | not_available_for_date | not_applicable | unresolved_identity | rights_blocked | reconstructed_not_operational_pit | superseded_by_recompute`. A human-readable `case_ref` (e.g. `IMCE-CASE:CELH:2024Q3:DISTRIBUTOR-DESTOCK`) is a document locator only — never a join key for Radar, Prophet, Market Memory, Stock Identity, or any durable store.

## D3 — Artifact model: **The five research artifacts are APPROVED as records-only candidates, with a construction-naming law added.**

Mechanism Passport, Mechanism Case Tape (rebuildable, deletable, references canonical receipts), Mechanism State Claim (family-local, supporting/contradicting recorded separately), Recognition Snapshot, and Research Factory candidate / CPI truth records — as specified in Sol Round 3 §4.2, with these amendments:

1. **Construction-naming law (new, from G2):** the house holds TWO canonical 2W MACD constructions — classic 12-26-9 (`engine/technicals.macd_hist`, used by stock snapshots) and the RSI-MACD inside the confluence contract (`engine/canon.py` `w2_bull`, params 14/14/60/5, `.shift(1)` completed-bar semantics). Every Recognition Snapshot field MUST name which construction it binds to. Minting a third implementation violates the canon's one-implementation-per-concept invariant and is forbidden.
2. **Mechanism observations and read-through stay with their owners** (Earnings / Economic Propagation): `earnings_mechanism_observation/v1` is SPEC_ONLY and event-scoped; `read-through hypothesis` is a reserved record class needing its own DEC (`research/economic_propagation/D0_OWNERSHIP_AND_GRAPH_CENSUS.md:76,102,121,238`). IMCE composes and cites; it never creates a graph or a generalized mechanism-observation contract.
3. **Canonical paths:** masterplan-tier docs under `research/` as `research/IMCE_*` (this file), program detail under `research/imce/`. No `data/` writes in IMCE-00 (records-only); when a later accepted wave writes derived research views, they live under `data/cycle_pattern/` per CPI convention with the reader-allowlist extension of D1(a).

No new runtime schema is granted by these approvals.

## D4 — Clock law: **RATIFIED.** Operating, accounting-translation, and market-recognition clocks; every observation stamped with the Market Memory temporal law (`event_time`, `measurement_end`, `available_at`, `observed_at`, `as_known_at`/`knowledge_cutoff`). Family-local extra clocks permitted as local fields; no fourth global ontology. The canonical cautionary exhibit is now on the record (G1): CELH's Q1 2023 ~$25M pipeline-fill was disclosed only in the 2024-05-07 release — a **13-month retro-disclosure lag** — so a decision-time read of 2023 growth structurally could not net it. `available_at` is not decoration; it is the difference between history and hindsight.

## D5 — Phase law: **RATIFIED with a coupling flag.** Mechanism-local descriptive state vectors per family (CELH: `channel_destocking`/`shipment_rebalance`/`assortment_reset`/`distribution_ramp`; memory: `customer_destocking`/`supply_curtailment`/`legacy_price_recovery`/`HBM_constraint`; homebuilders: `order_softness`/`completed_inventory_build`/`incentive_support`/`pace_recovery`; banks: `deposit_repricing`/`NIM_compression`/`reserve_build`/`credit_normalization`). The CPI five-phase wheel remains the only market-cycle ontology; any crosswalk is display/context until separately measured. **Memory amendment (G3):** the legacy and HBM axes are causally coupled from 2025 (HBM buildout itself created legacy scarcity) — they are neither two strata nor two independent blocks; the coupling date is registered in the contract (§9, A15).

## D6 — Pilot order and cohorts: **Appendix-A order ADOPTED, now census-backed.**

1. **CELH Cycle Autopsy** (records-only, first product/research specimen) — GO (§7.1).
2. **Homebuilder source/definition census → first quantitative family** — CONDITIONAL_GO (§7.2).
3. **Memory two-axis grammar** — records-only; REGISTERED-only, zero historical inferential cells (§7.3).
4. **Banks** — regulatory-entity feasibility GO; stock bridge DEFER (§7.4).

Roster changes are frozen pre-outcome and never after outcome inspection.

## D7 — Source and procurement: **RATIFIED as adversarially verified (G6): GO_LIMITED, zero decision reversals across all 22 rows.**

Public-source-first survives review. Binding constraints, in order: **FRED = DO_NOT_INGEST**, and for a stronger reason than Round 3 stated — Prohibition (q) bars storing/caching/archiving FRED content or incorporating it in any database, independent of the AI-training clause (p), so even display-tier ingest-and-store is barred and the underlying-source replacement path (`UNDERLYING_MACRO_OWNERS`) is mandatory. **Circana direct = HOLD** (enterprise contract, confidentiality-bound; issuer-disclosed aggregates remain GO_LIMITED as `issuer_claim_numeric` with exact footnotes). **SEMI EMDS = CONDITIONAL_BUY** only after written multi-user/storage/derived-output/ML rights (store page prices $3,350/$7,050 per-user and publishes no license text). **WSTS / TrendForce = NO_BUY_NOW** (verified redistribution/scraping bans; WSTS's cost is quote-gated via SIA — the matrix's $30,000 is unverifiable publicly). Two evidence-only amendments recorded (WSTS URL moved to `wsts.org/61/SUBSCRIPTION`; Lennar host is `investors.lennar.com`). The two repo REUSE_LIMITED rows (equity revisions, IBKR borrow) are prospective-from-capture by construction — any study leg needing their history is prospective by definition.

## D8 — Measurement and trial families: **Names reserved; Evaluation OS/QLedger is the measurement owner; the amended contract is the freeze candidate.**

- `rf.cycle_pattern.imce_phase_v0`, `rf.cycle_pattern.imce_sync_v0`, `rf.cycle_pattern.imce_risk_v0` verified collision-free and legal under RF-6 (`^rf\.[a-z_]+\.[a-z0-9_]+$`, <40 chars; lengths 30/29/29). **Reserved by this record only** — the `declared_budget` trial-ledger row is IMCE-03 work (a `data/` write, out of IMCE-00 scope by design).
- Market grading: QLedger 63-trading-day rung, no substrate extension (`engine/qledger.py:114` `GRADE_HORIZONS = (5, 21, 63)`; exchange-calendar resolution `_calendar_for`/`resolve_horizon_window`). 5d/21d grade rows exist automatically for a 63d claim and are **non-claim diagnostics** — outside the FDR partition, never verdict-bearing. A genuine 21d claim needs its own declared, budgeted cell. **126d may never be a LIVE-GRADER QLedger claim [G8-m6]** — `config/ruling_graph.yml` LH-U6 fences `GRADE_HORIZONS` at 63d in the live nightly grader (its scope_fence explicitly permits an off-render research grader to use extended horizons), and a 126d claim filed in the live ladder would grade only at 5/21/63 while its check_by sits ungraded — a queryable condition (`check_by_is_a_graded_exit()`), not merely a docstring. 126d exists for IMCE only as off-render descriptive material.
- **The 40-block floor's provenance is now on the record and ruled on:** it was imported from BC-1, where the unit was *monthly panel stamps* — re-denominating it in macro-cycle blocks made it vastly more stringent than any house precedent. RULING: **keep 40 for `PROMOTE_ELIGIBLE`** (it is the correct bar for cycle-level edge authority); add a bounded, non-promoting rung with a hard authority ceiling; and publish the come-back arithmetic as the program's honest headline (homebuilders reach 40 blocks around **~2145** at the census accrual rate; memory and banks later still).
- **Claim-class taxonomy (adopted, split per red team [G8-B5]):** (i) cycle-block claims (forecast/edge) — unreachable from history, prospective-only; (ii) **transcription/reproduction-fidelity claims** (passport field reproduction, denominator-crosswalk fidelity) — legitimately row-denominated, honest n in the hundreds, reachable now, zero forecast authority; (iii) **coverage and abstention-calibration claims** — block-dependent by construction (a source outage hits every issuer in a quarter simultaneously), so the DEFF/independent-shock rule applies and "n in the hundreds" is struck for this sub-class. Only (ii) is the near-term measured-output path at row denomination.
- **All 26 G7 amendments to the preregistration candidate are ADOPTED** and applied in `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` (+ YAML lossless projection; the MD binds), then further amended per the G8 red team (§10a). The load-bearing ones: predetermined `underpowered_accruing` for every historical cell (statuses fixed pre-outcome; a sub-floor nominal "pass" can never reach display or a truth statement, **and its point estimate carries no prior into any prospective cell [G8-B7]**); the frozen literal block list; the independent-shock-realization unit law with the DEFF rule; single BH partition `imce_hist_v0` (6 cells: phase 3, sync 2, risk 1) at q=0.10 (inoperative on the historical arm — disclosed, §9); **`R_t` is frozen NOW, in this freeze, before A1** — fields as enumerated in contract §4 with each telemetry field bound to a NAMED canon construction chosen a priori by house default, and the G2 tape disclosed as prior-produced unregistered evidence (the unreachable "frozen before autopsy OR provenance note + out-of-cohort validation" disjunction is replaced by this executed freeze + disclosure [G8-M10]); banks feasibility-only with a PIT self-archival lane precondition; the era-correlated-missing-indicator ban (LEN); NVR as stratum/transfer-test only; homebuilder survivorship condition (5) mirrored [G8-B4]; the `mechanism_hypothesis` evidence class for causal attributions [G8-M8]; every "where feasible / preferably / optional" analyst-choice seam closed.
- **`underpowered_accruing` is a Research-Factory/trial-ledger status ONLY [G8-M7]:** it exists in the RF operating runbook's kill classes and is NOT a CPI truth status (`truth_schema.md` enum: candidate/display/confirmer/scored/promoted_null/retired/superseded) — no IMCE row may enter the CPI registry under that status without an explicit schema + consumer-matrix amendment, because an unknown status would fence no surface. Nulls-printed reconciliation: house law prints earned nulls (promoted_null, Tier-2 receipts); a sub-floor historical readout is not an earned null and is not printed as one — "no display" here means no product-surface authority for sub-floor historical results, not hiding an adjudicated null.

## D9 — Authority: **ALL FALSE AT BIRTH, and closed against the discovered escape.** No rank, gate, size, escalate, trade, or originate authority exists anywhere in IMCE. CELH is descriptive forever — it may never enter an inferential sample nor be cited as evidence of issuer-specific forecast skill. No Radar/Prophet/size path appears in this architecture; a future consumer requires matured prospective evidence, its own architecture review, and separate promotion. The one promotion-adjacent escape found in the Round 3 text (sub-floor partial-pass → "display-only" — reachable at B=6 where a bootstrap pass is more likely artifact than effect) is **closed** (D8; contract A3).

## D10 — Durable memory: **Minted in this PR; no new lifecycle store.**

- `agentos/decisions/DEC-CPI-ISSUER-MECHANISM-RESEARCH-EXTENSION-NOT-NEW-ENGINE.md` — this freeze's why.
- `agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md` — program record, waves = §13.
- `agentos/handoffs/CYCLE-PATTERN-ISSUER-MECHANISM-2026-08-20.md` — session handoff (cold-stranger test).
- `agentos/workstreams/WS-STOCK-IDENTITY.md` — stale-record heal (§1).
- Capability and source-rights ledgers live in this document (§8, §11); the amended preregistration candidate lives in `research/imce/`. Nothing else. Account-local memory is not company memory.

---

# 3. Owner/port matrix (frozen)

| Truth / capability | Canonical owner (repo anchor) | IMCE port | Prohibited |
|---|---|---|---|
| Exact issuer/security/listing identity | Data OS — `engine/company_intelligence/identity.py` (`company_identity.v1`, context_only, typed refusals) | read `company_id`/`security_id`/aliases/refusals | second allocator; ticker-as-identity |
| Tape grammar, identity epochs, path episodes | Stock Identity — `engine/stock_identity/{episodes,fingerprint}.py` | cite Episode tuples; `identity_epoch` typed `not_yet_built` until W4 | rival personality/epoch stack; per-name outcome audition (`DNR:KILL-OUTCOME-AUDITION`) |
| Market/sector/country cycle state + truth/null lifecycle | CPI — `engine/cycle_pattern/`, `config/cycle_pattern/`, `data/cycle_pattern/truths.jsonl` | truth rows via `scope.families` after D-4 audit; context-only wheel crosswalk | new phase wheel; issuer truths before audit; broad single-equity lake |
| Decision-time envelope + general replay/analogues | Market Memory — `contracts/market_memory/as_known_at.v1.schema.json` | cite `context_id`s; temporal law adopted wholesale | second as-known-at contract; analogue engine — and note the construction line [G8-m7]: `CPI-017` killed normalized-half-cycle kNN price-shape retrieval as a construction; IMCE's mechanism-signature *comparison* (source-backed state matching in prose) is a different construction, but ANY retrieval-armed analogue — mechanism-keyed or not — still requires Market Memory's separately validated port plus a new preregistered trial that names CPI-017 |
| Accounting facts/revisions/receipts | FIF — `contracts/financial_intelligence_packet.schema.json`, FIF-2A bridge (#5983, fixture-proven) | consume packets/query receipts as coverage arrives | second accounting engine; stretching FIF to non-filing facts (distributor inventory, scanner aggregates → mechanism observations with typed provenance instead) |
| Earnings events/facts/claims | Earnings — `event_workspace.v1` (AAPL golden path live; #6021 dossier OPEN/DRAFT/HOLD) | cite event IDs, claims, typed absences | second workspace/event identity |
| Event mechanism observation + read-through | Earnings + Economic Propagation (D0 census rulings) | consume/propose source-backed observations | any graph store; peer-transfer score |
| Causal frontier cells (discovered-graph proposals) | Causal Hypothesis Factory — `neuralweb.causal_lab_state.v1`, research_only [G8-M3] | none — IMCE mechanism hypotheses are issuer-internal, hand-curated, source-backed; they never enter CHF's discovered-graph plane | duplicating CHF; any causal-graph→alpha path (`DNR:KILL-CAUSAL-DAG-ALPHA`) |
| Macro policy transmission chains (chain-hop episode states) | Policy Transmission Intelligence — `transmission_chains.v1`, display_only [G8-M3] | none — IMCE state vectors are issuer-local mechanism conditions, not cross-entity macro transmission hops; no chain-hop state machine is duplicated | duplicating TXI's dormant→arming→propagating machine for issuers |
| Fixed market telemetry constructions | Canon — `engine/canon.py`, `engine/confluence_tiers.py`, `engine/technicals.py` | reference NAMED constructions (D3.1) | third weekly-state/MACD implementation |
| Short interest / borrow / revisions | Positioning + revisions owners (`engine/short_pressure.py` knowable-date law; `collectors/{ibkr_borrow,equity_revisions}.py`) | consume `asof_slice` on `knowable_date`; prospective-from-capture | settlement-date joins; synthetic backfill; invisible fusion |
| Emergence / opportunity / sizing | Radar / Prophet | none in this architecture | any detector, rank, gate, size, escalation |
| Market-claim grading + promotion | Evaluation OS / QLedger / Research Factory | 63d rung; declared families; `underpowered_accruing` kill class | second grader; retroactive registration; off-horizon verdicts |
| Mechanism hypothesis, clock join, local state evidence, case read model | **IMCE under CPI** (this freeze) | the missing capability | everything in §12 |

---

# 4–6. Episode binding, artifacts, and data/time law

Frozen as ruled in D2–D5 above. The evidence-class vocabulary (`observed_numeric`, `issuer_claim_numeric`, `issuer_claim_directional`, `accounting_identity`, `derived_deterministic`, `statistical_estimate`, `model_generated`, `missing`, `not_licensed`, `not_reconstructable`, `not_applicable`) and structural-break law (epochs frozen **before any outcome inspection** — strengthened from "before fitting" [G8-M2]; no cross-epoch transfer without a registered test) are ratified as Round 3 §4.4–4.5 with these amendments from census and red-team evidence:

- **`mechanism_hypothesis` evidence class added [G8-M8]:** a causal attribution ("the 2024 revenue decline was caused by distributor destocking") is neither an issuer claim nor a deterministic derivation — it gets its own explicit low-authority class carrying a MANDATORY named falsifier and a competing-explanation field. Every D5 state-vector assignment (`channel_destocking`, `order_softness`, …) is an `mechanism_hypothesis`-class record, never `derived_deterministic`, and an issuer's own causal narrative filed as `issuer_claim_directional` may not be silently upgraded.
- **Ordinal sensors stay ordinal (G3):** Samsung/SK hynix wafer starts and ASP are directional-only; a directional field entering a cardinal model is a missingness event, never an imputation.
- **Deterministic/statistical/model-generated boundary** ratified per handoff §9; model-generated output may never create source facts, scores, probabilities, candidates, or authority (CPI doctrine A7 unchanged).

---

# 7. Four-pilot dispositions

## 7.1 CELH — **GO: records-only Cycle Autopsy + prospective observation ledger. NO GO: any fitted model, probability, or per-name rule — permanent.**

Census-backed: all six structural epochs receipted with two boundary amendments (E2 dated to measurement start 2024-01-01 on the OPERATING clock; E1 ends at 2023-12-31). **Epochs are clock-stamped [G8-M2]:** these are operating-clock boundaries, valid for describing the business system; any partition of a RECOGNITION-outcome statistic must instead use recognition-clock (`available_at`) boundaries — an epoch dated to a date no market participant could know (E2's 2024-01-01 vs its 2024-05-07 disclosure) is look-ahead if used to block outcome statistics. Sell-through-vs-sell-in wedge has both legs in comparable 13-week windows for **E2–E5** (per-brand from Q2 2025); E0/E1 cannot support wedge measurement — typed absence, not backfillable. Earliest quantified distributor-inventory disclosure: Q1 2024 release. Seven contradiction/counterexample rows are on record, including the Q3 2024 sign-flip wedge (retail +7.1% vs revenue −31.0%), the failed bounce (Q3 2025 +44% base-effect → Q2 2026 core −11.7%), and the Alani Q1 2026 load-in — an `mechanism_hypothesis`-class attribution (§4–6), not an observed fact — that the 2022 pipeline-fill signature repeated. Recognition tape (G2, unregistered descriptive evidence — see §9): 16 completed-bar 2W bullish crosses 2011–2025 on the single CELH price plane of the canonical store (2007→present; no events before ~2010 is MACD warm-up, not a gap [G8-v5]), 1 two-bar whipsaw, 7/16 non-positive at +63td, +63 mean carried entirely by two outliers. **This record is preserved as research material for the future, separately-authorized product wave (IMCE-07); no display of it is mandated or permitted by this freeze [G8-B2].** CELH's descriptive-forever status (D9) is unconditional.

## 7.2 Homebuilders — **CONDITIONAL_GO: first quantitative family, after the HB-0 census freeze, under four conditions.**

(1) **LEN** is excluded from cancellation-rate cells (no press-release cancellation rate; its missingness is era-correlated by construction — a missing-indicator would be an era proxy) and carries a Feb-2025 Millrose break flag. (2) **NVR** is a mechanism outlier (100%-option land model) — separate stratum or designated transfer test, never pooled to raise n. (3) Episodes re-key on **calendar month** (fiscal year-ends span Sept 30 → Dec 31); the fiscal→calendar crosswalk freezes pre-outcome. (4) One canonical **cancellation-rate denominator per issuer** is frozen with a printed conversion and a mandatory alternate-convention sensitivity re-run — a result that flips under the alternate convention is not a pass. (5) **Survivorship [G8-B4]: the roster is a 2026-survivor roster over a window containing the 2006–2011 sector mortality event, and the ported Stock Identity episode substrate is itself survivor-stamped (W1 census "survivor-only stamped").** IMCE-HB-0 must produce a named census of delisted/bankrupt/acquired homebuilders for the study window with an explicit inclusion decision; until then, every homebuilder cell readout carries a mandatory survivorship-bias disclosure, and no cohort mean is quoted without it. Honest effective-N: **5–7 macro blocks** (n_eff ≈ 6–10 under any defensible cross-issuer correlation) — measured status is unreachable from history; the family's historical arm runs with predetermined `underpowered_accruing` status. Fully public-source (confirmed).

## 7.3 Memory — **Records-only two-axis grammar; REGISTERED-only; ZERO historical inferential cells.**

Honest effective-N = 2 completed blocks + 1 open episode; the open HBM/AI episode has no closing disposition and is not a unit — counting it is a unit violation. `leave_cycle_out` is undefined at B=2, so memory cannot even be REPLAYED as an inferential cell. The two axes are causally coupled from 2025 (D5) — coupling registered, never smoothed. Paid-gap ledger confirms the SEMI/WSTS/TrendForce holds; a purchase decision waits for a registered public-source gap named by a preregistered trial, per D7.

## 7.4 Banks — **GO: regulatory-entity mechanism-panel feasibility + identity-bridge design. DEFER: any stock-bridge work.**

The charter→listed-security chain (CERT → RSSD → NIC relationships → NY Fed CRSP-FRB link) terminates in a hand-curated, irregularly-updated crosswalk whose live coverage is unverified (fetch 403). Real multi-charter landmines are documented (Banc One: 88 charters; Glacier: 11; Zions is the inverse trap — multi-brand, single charter): multi-charter BHCs get typed refusals, not allocations. **The decisive constraint: public Call Report/UBPR data is current-revised, not PIT** — FFIEC recalculates trailing quarters and holds only current-best values, so any historical bank panel is a restatement-survivor panel. Banks are feasibility-only until a prospective **self-archival lane** (dated, hash-pinned vintage snapshots) exists with a start date — and bank PIT-clean history therefore starts at zero. CECL epoch flags (2020 large-filer / 2023 remainder waves + 3-year phase-in + purchase-accounting resets) are a design deliverable of the feasibility wave. First vertical slice when authorized: deposit-repricing/NIM-compression, 2021–2024, single-dominant-charter cohort — provable without the security join. Honest effective-N ≈ 3 system-wide episodes.

---

# 8. Source-rights ledger (adversarially verified 2026-08-20)

**PIT/vintage disposition rider [G8-M6]:** rights-GO does not mean vintage-clean. The mandated FRED replacement removes ALFRED-style vintage access (ALFRED sits inside the prohibited FRED estate — the repo's own truth schema flags `revision_optimistic` for "revised macro/regime data without ALFRED vintages"), and underlying agencies publish largely current-revised series: Census NRS in particular is revised for three subsequent months plus annual benchmarking (its own historical-release archive partially mitigates). RULE: IMCE-HB-0 must add a per-source vintage audit for every GO macro/homebuilder source; any leg without retrievable vintages is declared `revision_optimistic` in the contract's `pit_class` and disclosed in every readout that uses it — the same PIT rigor §7.4 applies to banks, applied to the family this freeze promotes.

All 22 rows of the Round 3 matrix verified or explicitly dispositioned; **zero decision reversals**; two evidence-only amendments (WSTS live URL; Lennar host). Verdicts: GO — SEC_EDGAR (10 req/s, declared UA), CELH_IR, MICRON_IR, SAMSUNG_SKHYNIX_IR, CENSUS_NRS, DHI_IR, PEER_BUILDER_IR, FDIC_BANKFIND, FFIEC_CDR, FDIC_QBP, UNDERLYING_MACRO_OWNERS (per-source audit still required), CANONICAL_PRICE_TAPE (REUSE; yfinance exposure documented in-repo), FINRA_SHORT_INTEREST (REUSE; knowable-date law). GO_LIMITED — CIRCANA_ISSUER_DISCLOSED (issuer-claim citation lane only), SEMI_PUBLIC. REUSE_LIMITED — EQUITY_REVISIONS, IBKR_BORROW (prospective-from-capture). HOLD — CIRCANA_DIRECT. CONDITIONAL_BUY — SEMI_EMDS (written rights precondition). NO_BUY_NOW — WSTS, TRENDFORCE. DO_NOT_INGEST — FRED_API_SITE (clause (q): no store/cache/archive/database incorporation; binds all use classes). Full verdict table with quoted operative language: G6 worker packet, preserved in the handoff record.

---

# 9. Measurement freeze

The amended preregistration candidate (`research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`, MD binds; `IMCE_PREREGISTRATION_CANDIDATE_V1.yaml` is its lossless projection) applies all 26 adopted amendments (D8). The predetermined-status table it now carries:

| Cohort | Honest historical blocks | Max ladder rung on history | Historical cells |
|---|---|---|---|
| CELH | barred by rule | `DESCRIPTIVE` | 0 |
| Homebuilders | 5–7 | `REGISTERED`→`REPLAYED` (estimation-only readout; never DISPLAY, never PROMOTE_ELIGIBLE) | 6 (one BH partition `imce_hist_v0`, q=0.10) |
| Memory | 2 (+1 open, ungradeable) | `REGISTERED` only | 0 |
| Banks | ~3, 0 PIT-clean | `DESCRIPTIVE`/feasibility | 0 |

Power truth at the honest Ns (preregistered as an expectation, so a null cannot be reinterpreted afterwards): at B=6 blocks the minimum detectable paired effect is ≈1.2 SD of the between-block improvement distribution; a nominal bootstrap pass at that N is more likely a coverage artifact plus winner's curse (4–6× magnitude inflation; up to ~14.5% sign-error risk at small true effects) than a real effect, and any pass would near-certainly violate the "not carried by one cycle" conjunction anyway. **The BH-FDR partition is registered for the prospective arm; at n_eff ≈ 6 the historical FDR machinery is statistically inoperative and is disclosed as such — harmless only because the historical statuses are predetermined [G8-M9].** Time-to-floor at census accrual rates: homebuilders ~2145; memory and banks next century or later. **The come-back arithmetic is the program's honest headline.**

**Outcome-evidence disclosure [G8-B3]:** no *registered trial* outcome run has been performed. The G2 census lane DID produce an unregistered, descriptive recognition tape on CELH (event dates with +21/+63-trading-day path fields) under its commission; that tape is design-contaminating evidence now in hand. It is quarantined as follows: archived as census evidence only; no truth statement, display, or registered cell may cite it; and the `R_t` design-provenance rule (D8) treats it as prior-produced context whose construction (classic 12-26-9, the house stock-technicals default) was fixed by canon before any outcome inspection. The criteria commit still strictly precedes any *registered* runner/outcome commit (two-commit discipline), and A1 is fenced to zero outcome computation (§13). **The sub-floor "prospective PRIOR" carry-path flagged by the red team is DELETED — a sub-floor historical point estimate is archived as a descriptive number only and plays no role, prior or otherwise, in any prospective cell; prospective cells are graded prior-free [G8-B7].**

---

# 10. Worker verdict table

| Lane | Route/model | Verdict | One-line result |
|---|---|---|---|
| G0 owner/collision census | census/sonnet | **CONDITIONAL_GO** | CPI is the legal parent; zero collisions; trial names legal; vocabulary defect CONFIRMED with quotes; stale WS ledger produced; composed-anchor evidence |
| G1 CELH source evidence | research/sonnet | **PASS** | Six epochs receipted (2 boundary amendments); wedge legs E2–E5; 13-month retro-disclosure exhibit; 7 contradiction rows; typed gaps G1–G8 |
| G2 CELH recognition tape | research/sonnet | **PASS** | Canonical store has CELH 2007→08-12; 16 completed-bar 2W crosses, 1 whipsaw, 7/16 negative +63td; TWO canonical MACD constructions — naming law required; short-interest knowable-date law confirmed |
| G3 memory census | research/sonnet | **CONDITIONAL_GO** | Effective-N = 2+1 open; axes causally coupled from 2025; Samsung/SKH directional-only on the load-bearing sensors; paid gaps confirmed unrecoverable first-party |
| G4 homebuilder census | research/sonnet | **CONDITIONAL_GO** | Keep DHI/PHM/KBH/TOL; LEN adjusted; NVR outlier; 5–7 honest blocks; three cancellation denominators; 3-month fiscal band; fully free-source |
| G5 bank census | research/sonnet | **GO_FEASIBILITY / DEFER stock** | Bridge designable but terminal hop unverified; Call Report/UBPR current-revised (no public PIT); CECL epochs; ~3 episodes; NIM slice named |
| G6 rights verification | research/sonnet | **GO_LIMITED** | 22/22 dispositioned, zero reversals; FRED (q) strengthens DO_NOT_INGEST; SEMI prices confirmed; 2 evidence-only URL amendments |
| G7 prereg/power | analysis/opus | **PASS** | Historical statuses predetermined; 40-floor provenance surfaced; 26 amendments; MDE/Type-M arithmetic; 126d QLedger trap; MD↔YAML divergence |
| G8 red team | review/opus | **REVISE → amendments applied** | 7 blockers + 10 majors + 7 minors; 4 blocker-grade internal contradictions and 1 live leak path found; all blockers and majors accepted and amended in this document (§10a); repo-checkable claims otherwise verified exactly |

## 10a. Red-team dispositions

Verdict as returned: **REVISE** — "the architecture's core posture (records-only, all-authority-false, predetermined underpowered_accruing) is sound," with 7 blockers, 10 majors, 7 minors. Disposition of every blocker/major (minors m2/m4 carried as timing notes; m1/m3/m5/m6/m7 fixed):

| Finding | Disposition |
|---|---|
| B1 wave order ran outcomes before criteria | ACCEPTED — A1 re-fenced to zero forward-return/outcome computation; outcome fields attach only after the A4 criteria commit (§13) |
| B2 display mandate to a nonexistent "Cycle Lab" surface | ACCEPTED — mandate deleted; the counterexample record is research material for the separately-authorized IMCE-07 product wave (§7.1) |
| B3 "no outcome run" false vs the G2 tape | ACCEPTED — restated as "no registered trial outcome run"; G2's unregistered descriptive tape disclosed and quarantined (§9) |
| B4 homebuilder survivorship untreated | ACCEPTED — §7.2 condition (5): named delisted/bankrupt/acquired census in HB-0 + mandatory disclosure until then; mirrored into the contract |
| B5 observation-claim n inflated | ACCEPTED — class split: row-denominated transcription-fidelity vs block-denominated coverage/abstention with DEFF; "hundreds" struck for the latter (D8) |
| B6 §14 unverifiable pre-commit; handoff missing | ACCEPTED — work committed, handoff written, §14 restated in commit-relative terms (§14) |
| B7 sub-floor "prospective PRIOR" laundering path | ACCEPTED — prior-carry DELETED outright; prospective cells graded prior-free (§9; contract) |
| M1 vocabulary claim wrong; A2 under-scoped | ACCEPTED — §1/§11 restated with overlap facts + four-vocabulary/orphan-token enumeration; A2 re-scoped to all 29 rows (§13) |
| M2 epoch clocks / E2 un-knowable boundary | ACCEPTED — epochs clock-stamped; recognition-outcome partitions must use `available_at` boundaries; "before fitting" strengthened to "before any outcome inspection" (§7.1, §4–6) |
| M3 CHF/TXI owners + KILL-CAUSAL-DAG-ALPHA missing | ACCEPTED — two owner rows added with non-overlap statements (§3); DNR row bound in D1(b) |
| M4 ticker-keyed mutating episode anchor | ACCEPTED — `security_id` + `catalog_as_of` required on every Episode citation; `superseded_by_recompute` missingness type added (D2) |
| M5 rival epoch stack | ACCEPTED-AS-DEFINITION — mechanism epoch defined as a distinct non-identity record class with explicit non-overlap; crosswalk to W4 identity epochs is a separately registered future question (D2) |
| M6 FRED (q) → vintage/PIT hole for promoted family | ACCEPTED — §8 PIT/vintage rider: per-source vintage audit in HB-0; vintage-less legs declared `revision_optimistic` and disclosed |
| M7 `underpowered_accruing` ungoverned in CPI | ACCEPTED — declared an RF/trial-ledger status only; CPI registry entry under it forbidden without schema+matrix amendment; nulls-printed tension reconciled (D8) |
| M8 no evidence class for causal attribution | ACCEPTED — `mechanism_hypothesis` class added with mandatory falsifier + competing-explanation field; all D5 state assignments carry it (§4–6) |
| M9 BH partition decorative at n_eff≈6 | ACCEPTED-AND-DISCLOSED — historical FDR machinery stated inoperative; registered for the prospective arm (§9) |
| M10 R_t provenance disjunction unexecutable | ACCEPTED — `R_t` frozen NOW in this freeze, before A1, constructions named a priori; unreachable disjunction replaced (D8) |
| v5 splice note (2011 vs 2007 store) | ACCEPTED — warm-up disclosure + single-price-plane statement added (§7.1) |
| m1 two program names | FIXED-BY-NOTE — WS carries `program: market-regime-risk` (registry parent); CPI truth rows will carry `owner_program: cycle-intelligence` (truth-schema requirement); both name one subprogram per the `mastermind_programs.yml` alias table |
| m5 heal scope creep into sibling record | ACCEPTED — WS-STOCK-IDENTITY note trimmed to its own facts; the IMCE typing rule lives in IMCE records |
| m6/m7 conservative overstatements; HAR-1 construction line | ACCEPTED — 126d wording corrected to live-grader scope; HAR-1 construction-vs-scope sentence added (§3, D8) |

Reversal conditions 1–8 of the REVISE verdict are each satisfied by the amendments above; condition 9's M9/M10 are dispositioned (M9 disclosed, M10 executed).

---

# 11. Capability ledger (post-census)

| Capability | State | Delta vs Round 3 packet |
|---|---|---|
| Macro/sector/country cycle ontology + CPI live projection | `PROVEN_LIVE` | unchanged |
| CPI truth/null lifecycle for issuer scope | `BUILT_NOT_PROVEN` | audit now MANDATORY pre-issuer-truths: registry rows split across two consumer vocabularies |
| CPI authority guard | `PARTIAL` | literal-path scan confirmed by docstring; vocabulary defect is not CI-caught |
| Stock Identity episode substrate | `BUILT_NOT_PROVEN` | W2 MERGED (was "workstream stale"); `identity_epoch` = provisional placeholder, W4 todo |
| Market Memory as-known-at contract | `BUILT_NOT_PROVEN` broadly; contract canonical | unchanged |
| FIF packet + query bridge | `BUILT_NOT_PROVEN` beyond fixtures | FIF-2A now MERGED (#5983, 2026-08-20) |
| Earnings event workspace | `PROVEN_LIVE` (AAPL golden path) | #6021 dossier remains OPEN/DRAFT/HOLD |
| CELH source chronology | `PARTIAL` → **census complete for autopsy** | six epochs + wedge legs + counterexamples receipted |
| CELH recognition telemetry | **`PROVEN_SOURCE_AVAILABLE`** | canonical store covers 2007→present; event table computed read-only |
| Memory family public evidence | `PARTIAL_BUT_FEASIBLE` (descriptive only) | effective-N 2+1 open; coupling flag; ordinal-sensor law |
| Homebuilder family stocks/flows | `PARTIAL_BUT_FEASIBLE` | crosswalk mapped; 5–7 blocks; free-source confirmed |
| Bank regulatory panel | `PROVEN_SOURCE_AVAILABLE` / `NOT_JOINED_TO_SECURITY` | **plus: public data is current-revised — PIT requires self-archival from a start date** |
| Issuer mechanism passport / case tape / state claim / recognition snapshot | `NOT_BUILT` — approved as records-only candidates | construction-naming law added |
| Mechanism-conditioned recognition trial | `NOT_BUILT` | historical statuses predetermined; prospective-first |
| General analogue engine | `REJECTED_BY_DESIGN` | HAR-1 null located: `CPI-017` `promoted_null` |
| Broad screener / Cycle Score / Prophet authority | `REJECTED_BY_DESIGN` / `DEFERRED` | unchanged; partial-pass display escape closed |

---

# 12. Explicit non-goals (unchanged and re-affirmed)

No collector; no new data plane; no API or page; no model; no broad ingestion; no paid purchase; no single-equity CPI live lake; no analogue engine; no score/screener; no Radar/Prophet/Portfolio path; no second episode identity; no graph store; no LLM-originated numeric confidence; no merge by any worker; and — added by this freeze — no third telemetry construction, no issuer truths before the D-4 audit, no bank panel before the self-archival lane, no historical cell ever reaching display.

---

# 13. Authorized next waves and stop

**This freeze authorizes nothing to start until Sol/Chairman accept it.** Upon acceptance, the authorized waves are, in order (A1/A2/A3 may run in parallel — none writes runtime state):

- **A1 — IMCE-CELH-1, CELH Cycle Autopsy** (records-only): 2018–2026 source chronology + three-clock timeline + epochs + fixed-telemetry EVENT record (dates and completed-bar states only) under ONE named construction + prospective observation registration. No model, no score, no p-value, **and no forward-return/outcome computation of any kind** — outcome fields attach to events only after the A4 criteria commit, preserving the two-commit discipline [G8-B1]. (G2's already-produced descriptive tape is quarantined as unregistered design-context evidence — §9.)
- **A2 — CPI truth-contract audit** (D-4; CPI-owned heal): enumerate **every distinct `allowed_consumers`/`forbidden_consumers` token across all 29 registry rows** and disposition each against `consumer_matrix.yml` `surfaces:` — the defect is not a two-way schema/matrix mismatch but at least FOUR coexisting vocabularies including orphan tokens (`display_descriptive`, `research_factory_intake`, `display`/`display_only`) registered in NEITHER authority [G8-M1]; then reconcile `truth_schema.md`'s prose list and state what the authority guard does and does not check. Precondition for any issuer truth.
- **A3 — IMCE-HB-0, homebuilder source/definition census freeze** (records-only): fixed roster, denominator crosswalk, fiscal→calendar re-key, structural-break ledger, frozen block list, cell budget confirmation. Stop before any fitting.
- **A4 — IMCE-03 preregistration finalization**: `declared_budget` trial-ledger rows for the three reserved families (first `data/` write; needs its own wave approval), criteria commit strictly before any outcome access.

**Stop:** this session stops at the review-ready PR. No merge without Sol/Chairman release of the HOLD. No CELH implementation, ingestion, model fitting, or next wave has started. A DEFER/NO_GO by Sol preserves every census packet and this document as durable research.

---

# 14. No-runtime proof

This PR's full changed-path set is exactly [G8-B6 — stated commit-relative, verifiable on the PR itself via `git diff --stat <merge-base>...HEAD` and the PR "Files changed" tab]:

- `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` (this file)
- `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`
- `research/imce/IMCE_PREREGISTRATION_CANDIDATE_V1.yaml`
- `agentos/decisions/DEC-CPI-ISSUER-MECHANISM-RESEARCH-EXTENSION-NOT-NEW-ENGINE.md`
- `agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md`
- `agentos/workstreams/WS-STOCK-IDENTITY.md` (stale-field heal only)
- `agentos/handoffs/CYCLE-PATTERN-ISSUER-MECHANISM-2026-08-20.md`

No `engine/`, `scripts/`, `app/`, `collectors/`, `site/`, `templates/`, `data/`, `.github/`, or test paths are touched. Session pins (`9dcd4c24` observed at re-pin; worktree base `a36e5e70`) are observations at their stated times — main advances continuously, and the PR's merge-base diff is the binding proof, not any frozen pin [G8-m4].
