<!-- DO NOT EDIT BY HAND — regenerate with: python3 scripts/build_ruling_graph.py -->
<!-- Source: config/ruling_graph.yml -->
<!-- source_sha256: 8d058e3f5158d6e64440a819d83f169578b66924b745ff233368db304ad7794a -->

# Neural Web Case Law

> This document is a generated reference for all rulings in the ruling graph.
> It is the git-side review surface (all rows, including internal_only).
> The public site JSON at `site/neuralwebdata/ruling_graph.json` carries
> only `public_research` rows.

Total rulings: 500

## Precedence Order

1. `constitution_standing_law`
2. `fable_adjudication_doc`
3. `ratified_pr_body`
4. `synapse_config_law`
5. `code_guard_docstring`
6. `data_row_status_log`
7. `research_packet`

## Vocabulary

### Status

- `active_law`
- `adopted`
- `residue_adopted`
- `deferred`
- `killed`
- `no_build`
- `duplicate`
- `blocked`
- `superseded`

### Object Kind

- `constitution`
- `process`
- `lobe`
- `rail`
- `wave`
- `study`
- `context`
- `data_contract`
- `signal_family`

### Authority

- `A0_OBSERVE`
- `A1_EXPLAIN`
- `A2_ATTEND`
- `A3_DE_ESCALATE`
- `A4_QUARANTINE`
- `A5_GOVERN_TIERS`
- `A6_TUNE`
- `A7_ORIGINATE`

## Index

| ID | Title | Status | Kind | Owner |
|---|---|---|---|---|
| [RUL-CL-1](#rul-cl-1) | config/ruling_graph.yml is the single canonical case-law… | `active_law` | `process` | ruling-graph |
| [RUL-CL-2](#rul-cl-2) | Status and object_kind are separate vocabulary axes | `active_law` | `process` | ruling-graph |
| [RUL-CL-3](#rul-cl-3) | Ruling IDs are globally unique and namespaced | `active_law` | `process` | ruling-graph |
| [RUL-CL-4](#rul-cl-4) | Every row carries a verbatim source quote; source_lines is… | `active_law` | `process` | ruling-graph |
| [RUL-CL-5](#rul-cl-5) | Seven-level precedence order governs ruling conflicts | `active_law` | `process` | ruling-graph |
| [RUL-CL-6](#rul-cl-6) | Conflict checker hard-fails on FDR family and privacy… | `active_law` | `process` | ruling-graph |
| [RUL-CL-7](#rul-cl-7) | Re-proposal detection uses deterministic diff-aware… | `active_law` | `process` | ruling-graph |
| [RUL-CL-8](#rul-cl-8) | Clocked rows must reference experiments registry; no… | `active_law` | `process` | ruling-graph |
| [RUL-CL-9](#rul-cl-9) | Public JSON carries only public_research rows; denylist… | `active_law` | `process` | ruling-graph |
| [RUL-CL-10](#rul-cl-10) | No PR template section in v1; CI checker carries enforcement | `active_law` | `process` | ruling-graph |
| [RUL-CL-11](#rul-cl-11) | v1 ships exactly the YAML, scripts, tests, generated docs,… | `active_law` | `process` | ruling-graph |
| [RUL-CL-12](#rul-cl-12) | The ruling graph is display-only context; it may never… | `active_law` | `context` | ruling-graph |
| [RUL-CL-13](#rul-cl-13) | Post-Fable rows proposed by anyone; accepted only by… | `active_law` | `process` | ruling-graph |
| [RUL-CL-14](#rul-cl-14) | v1 seeds are the verified extraction from 23 canonical… | `active_law` | `process` | ruling-graph |
| [CONST-A6L1](#const-a6l1) | A6 Lane (i) — Bounded Deterministic Auto-Apply with… | `active_law` | `constitution` | neural-web |
| [CONST-A6L2](#const-a6l2) | A6 Lane (ii) — LLM-Proposed Parameter Change must pre-log… | `active_law` | `constitution` | neural-web |
| [CONST-ARM](#const-arm) | Arming-Predicate Doctrine: no env-flag switches; config.yml… | `active_law` | `constitution` | neural-web |
| [CONST-ART1](#const-art1) | Article 1 — Origination Ban: A7/ORIGINATE permanently… | `active_law` | `constitution` | neural-web |
| [CONST-ART2](#const-art2) | Article 2 — Scored-Path Perimeter: money-path surfaces… | `active_law` | `constitution` | neural-web |
| [CONST-ART3](#const-art3) | Article 3 — Evidence Floor: three gates required for… | `active_law` | `constitution` | neural-web |
| [CONST-STALE](#const-stale) | Evidence staleness: grants lapse at max_staleness_days… | `active_law` | `constitution` | neural-web |
| [CONST-LADDER](#const-ladder) | Authority ladder A0-A7: rung meanings and current holders… | `active_law` | `constitution` | neural-web |
| [HOUSE-U1](#house-u1) | Model routing: Fable main-loop only; no fan-out inheritance | `active_law` | `constitution` | house-law |
| [HOUSE-U2](#house-u2) | Model routing hook enforcement: guard denies unrouted spawns | `active_law` | `constitution` | house-law |
| [HOUSE-U3](#house-u3) | Git law: fresh origin/main branch, same-day squash-merge,… | `active_law` | `process` | house-law |
| [HOUSE-U4](#house-u4) | Epistemics: display-only until gauntleted; LLMs de-escalate… | `active_law` | `constitution` | house-law |
| [HOUSE-U5](#house-u5) | Ledger law: nightly is sole advancer of forward ledgers | `active_law` | `data_contract` | house-law |
| [HOUSE-U6](#house-u6) | Render budget is law: ~67 min, 4-core-bound; heavy compute… | `active_law` | `constitution` | house-law |
| [NW-ART1](#nw-art1) | Article 1 — No LLM origination (signal, trade, escalation) | `active_law` | `constitution` | neural-web |
| [NW-ART2](#nw-art2) | Article 2 — Perimeter by surface: DISPLAY-tier may never… | `active_law` | `constitution` | neural-web |
| [NW-ART3](#nw-art3) | Article 3 — Authority gates use CI lower bound, lapse on… | `active_law` | `constitution` | neural-web |
| [NW-U1](#nw-u1) | No hand-weighted return composite — composite law + synapse… | `active_law` | `constitution` | neural-web |
| [NW-U10](#nw-u10) | D8 ruling: cortex pinned to frontier Opus-class model | `adopted` | `constitution` | neural-web |
| [NW-U11](#nw-u11) | Anti-mining law: cortex machine trials graded only on… | `active_law` | `process` | neural-web |
| [NW-U12](#nw-u12) | Reflex JSONL single-writer law; nightly grader folds… | `active_law` | `rail` | neural-web |
| [NW-U14](#nw-u14) | Gauntlet law binds throughout — display-with-null if… | `active_law` | `constitution` | neural-web |
| [NW-U15](#nw-u15) | Scope fence: Neural Web owns… | `active_law` | `constitution` | neural-web |
| [NW-U16](#nw-u16) | Reliability kernel cells are estimates-with-CIs, never… | `active_law` | `process` | neural-web |
| [NW-U17](#nw-u17) | W3 market_state hand-weights: display-first, measured OOS;… | `deferred` | `study` | neural-web |
| [NW-U18](#nw-u18) | In-place envelope — never a wrapper; sidecar for… | `adopted` | `data_contract` | neural-web |
| [NW-U19](#nw-u19) | Synapse registry weights ratchet: only-shrinks on… | `active_law` | `data_contract` | neural-web |
| [NW-U2](#nw-u2) | No cross-engine hard gate without its own gauntlet | `active_law` | `constitution` | neural-web |
| [NW-U20](#nw-u20) | No substrate migration wave — federation with shared axes… | `active_law` | `constitution` | neural-web |
| [NW-U21](#nw-u21) | can_force converted to Wilson CI lower-bound;… | `adopted` | `rail` | neural-web |
| [NW-U22](#nw-u22) | altdata_brain actionable flag refused — insufficient track… | `deferred` | `signal_family` | neural-web |
| [NW-U24](#nw-u24) | Signal gate 3-lane failure semantics | `active_law` | `rail` | neural-web |
| [NW-U28](#nw-u28) | Governance ledger: append-only, evidence attached, every… | `adopted` | `data_contract` | neural-web |
| [NW-U29](#nw-u29) | No universal per-ticker bounce model — species×regime… | `no_build` | `constitution` | neural-web |
| [NW-U3](#nw-u3) | Nightly is sole advancer of forward ledgers; intraday lanes… | `active_law` | `data_contract` | neural-web |
| [NW-U30](#nw-u30) | A2 earn-in refused as of 2026-07-04; cortex attention… | `deferred` | `lobe` | neural-web |
| [NW-U4](#nw-u4) | Cortex earns authority on probation — A2/A4-A6 gated on… | `active_law` | `lobe` | neural-web |
| [NW-U5](#nw-u5) | A6 two-lane ruling: bounded deterministic vs LLM-proposed… | `active_law` | `constitution` | neural-web |
| [NW-U6](#nw-u6) | Oracle is the rotation lobe; Neural Web never re-implements… | `active_law` | `constitution` | neural-web |
| [NW-U7](#nw-u7) | Oracle artifacts consumed read-only by N4; graph library… | `deferred` | `rail` | neural-web |
| [NW-U8](#nw-u8) | D2 ruling: spine = query layer; qledger stays QI-owned;… | `deferred` | `data_contract` | neural-web |
| [NW-U9](#nw-u9) | D3 ruling: two organisms, two brains — dashboard cortex vs… | `adopted` | `constitution` | neural-web |
| [NWP-U10](#nwp-u10) | L1 short-side grader: terminal_state_short() required; no… | `adopted` | `lobe` | neural-web |
| [NWP-U12](#nwp-u12) | R2 grading-closure audit: standing visibility for log-only… | `adopted` | `rail` | neural-web |
| [NWP-U13](#nwp-u13) | R4 contract drift check: schema_version + consumer… | `adopted` | `data_contract` | neural-web |
| [NWP-U15](#nwp-u15) | Long-hold G1 FDR family frozen as 'long_hold'; sub-scope in… | `active_law` | `study` | long-hold |
| [NWP-U16](#nwp-u16) | Long-hold G1 OOS split frozen: 2020-01-01 to 2023-12-31,… | `active_law` | `study` | long-hold |
| [NWP-U18](#nwp-u18) | No held-book/portfolio construction; no gross_mult… | `active_law` | `constitution` | neural-web |
| [NWP-U19](#nwp-u19) | No kernel consumers before 2026-10 FDR batch; no… | `active_law` | `constitution` | neural-web |
| [NWP-U2](#nwp-u2) | ERA LAW: absolute rates only on verdict_grade=True (2021+… | `active_law` | `constitution` | neural-web |
| [NWP-U20](#nwp-u20) | L6 gated on Phase-0 beating noisy-sector precedent; no… | `deferred` | `lobe` | neural-web |
| [NWP-U21](#nwp-u21) | L9 event-playbook lobe remains a Signal Commons wave; not… | `no_build` | `lobe` | signal-commons |
| [NWP-U24](#nwp-u24) | Per-bar forward paths nonexistent pre-computed; all path… | `active_law` | `data_contract` | neural-web |
| [NWP-U3](#nwp-u3) | CohortFilter v1: existing replay_boarded columns only; no… | `active_law` | `rail` | neural-web |
| [NWP-U4](#nwp-u4) | ExitPolicy v1 frozen enum; extending requires program… | `active_law` | `rail` | neural-web |
| [NWP-U5](#nwp-u5) | Flat pooled FDR family='replay': sub-families prohibited | `active_law` | `constitution` | neural-web |
| [NWP-U6](#nwp-u6) | No-adhoc rule: adding --adhoc flag is a house-law violation | `active_law` | `constitution` | neural-web |
| [NWP-U7](#nwp-u7) | EXIT-GRID-1 descriptive-only verdict; forking-paths… | `adopted` | `study` | neural-web |
| [NWP-U9](#nwp-u9) | L1 short-side: AVOID-not-SHORT; no site surface in Phase-0;… | `adopted` | `lobe` | neural-web |
| [RUL-P1](#rul-p1) | Two-lobe cap: only L1 Short-Side and L3 Dispersion chartered | `active_law` | `lobe` | neural-web |
| [RUL-P10](#rul-p10) | New data stores must declare commit path: gitignore,… | `active_law` | `data_contract` | neural-web |
| [RUL-P2](#rul-p2) | R1 shape: fire-tape replay only, no gate re-run, no… | `active_law` | `rail` | neural-web |
| [RUL-P3](#rul-p3) | Governor is law: no unregistered grid, flat… | `active_law` | `constitution` | neural-web |
| [RUL-P4](#rul-p4) | R3 vintage-stamp minimum: 8 fields required for R1… | `active_law` | `data_contract` | neural-web |
| [RUL-P5](#rul-p5) | L3 is promotion not invention: no new math, gross_mult… | `active_law` | `lobe` | neural-web |
| [RUL-P6](#rul-p6) | L1 asymmetry is a question, not a premise; paired… | `active_law` | `lobe` | neural-web |
| [RUL-P7](#rul-p7) | L4 decision-quality lobe NOT chartered;… | `deferred` | `lobe` | neural-web |
| [RUL-P8](#rul-p8) | ESX Amendment-2 T1 studies: no-CHIP cap until eq_band NC-2… | `deferred` | `wave` | entry-stack |
| [NWC-U1](#nwc-u1) | This doc charters no lobe; it is build authority for its… | `active_law` | `constitution` | neural-web |
| [NWC-U10](#nwc-u10) | Spine index has no sector column; join source must be named… | `active_law` | `data_contract` | neural-web |
| [NWC-U12](#nwc-u12) | OFR FSI must be lagged ≥1 business day; frozen publication… | `active_law` | `data_contract` | neural-web |
| [NWC-U13](#nwc-u13) | Episode cluster unit is contiguous hostile window, not… | `active_law` | `study` | neural-web |
| [NWC-U15](#nwc-u15) | All waves shipped same-day 2026-07-06; A1 rates PASS… | `adopted` | `wave` | neural-web |
| [NWC-U16](#nwc-u16) | Codex-6 'not a lobe' — decomposes into rail wave + bridge… | `killed` | `lobe` | neural-web |
| [NWC-U17](#nwc-u17) | Codex-8 / L8: held-book bridge belongs in Mastermind repo,… | `no_build` | `lobe` | neural-web |
| [NWC-U18](#nwc-u18) | Codex-7 is docket L6; gate unchanged, no charter issued | `active_law` | `lobe` | neural-web |
| [NWC-U19](#nwc-u19) | PR-D prereg must be committed BEFORE harness runs | `active_law` | `process` | neural-web |
| [NWC-U2](#nwc-u2) | Lobe cap fully consumed; no additional charters this cycle | `active_law` | `constitution` | neural-web |
| [NWC-U3](#nwc-u3) | No composite macro score; Signal Commons R3 applies to… | `active_law` | `constitution` | neural-web |
| [NWC-U4](#nwc-u4) | No held-book data in this repo; Mastermind two-organisms law | `active_law` | `constitution` | neural-web |
| [NWC-U5](#nwc-u5) | No kernel cells or conditioning before 2026-10 FDR batch | `active_law` | `constitution` | neural-web |
| [NWC-U7](#nwc-u7) | MASTERMIND_NW_CONTEXT bridge stays dark; arming gate… | `deferred` | `context` | neural-web |
| [NWC-U8](#nwc-u8) | L6-P0 budget declared as 12 cells before run; labeling as… | `active_law` | `study` | neural-web |
| [NWC-U9](#nwc-u9) | L6-P0 must control contemporaneous market drawdown as… | `active_law` | `study` | neural-web |
| [RUL-C1](#rul-c1) | No new lobes chartered; two-lobe cap stays at L1+L3 | `active_law` | `constitution` | neural-web |
| [RUL-C10](#rul-c10) | LLM law: no LLM scoring, escalation, or origination in this… | `active_law` | `constitution` | neural-web |
| [RUL-C11](#rul-c11) | L6-P0 FDR family is macro_tx (flat pooled, new family,… | `active_law` | `signal_family` | neural-web |
| [RUL-C2](#rul-c2) | Bridge lobe key must be `claim_reliability`, never… | `active_law` | `data_contract` | neural-web |
| [RUL-C3](#rul-c3) | QI owns qledger grading semantics; NWC is read-only | `active_law` | `constitution` | neural-web |
| [RUL-C4](#rul-c4) | L6-P0 legal shape: per-axis, no fusion, sector grain, PIT,… | `active_law` | `study` | neural-web |
| [RUL-C5](#rul-c5) | NARR-3 narrative-vs-price arbitration: no-build, registered… | `deferred` | `study` | neural-web |
| [RUL-C6](#rul-c6) | NARR-2 story decay curves: calendar-gated, no build,… | `deferred` | `study` | neural-web |
| [RUL-C7](#rul-c7) | Reflexivity wave stays under its existing rulings (R-A,… | `active_law` | `lobe` | neural-web |
| [RUL-C8](#rul-c8) | Bandwidth accounting: zero new lobes, zero new nightly… | `active_law` | `constitution` | neural-web |
| [RUL-C9](#rul-c9) | Registration hygiene: every new artifact registers in… | `active_law` | `process` | neural-web |
| [NWF3-U1](#nwf3-u1) | Trial-budget: TrialLedger per-family max stays 15; pooled… | `active_law` | `constitution` | neural-web |
| [NWF3-U2](#nwf3-u2) | L2 charter spec pre-written; thesis-exit join uses… | `deferred` | `lobe` | neural-web |
| [NWF3-U3](#nwf3-u3) | L5 Execution charter: passport annotate-only, CN/HK spread… | `deferred` | `lobe` | neural-web |
| [NWF3-U4](#nwf3-u4) | NET-REPLAY-1 gross/net always side-by-side; no net figure… | `active_law` | `constitution` | neural-web |
| [NWF3-U5](#nwf3-u5) | No gross_mult unclamp and no dispersion sizing permitted | `active_law` | `constitution` | neural-web |
| [NWF3-U6](#nwf3-u6) | No options root-direction flip; no fused execution score | `active_law` | `constitution` | options-alpha |
| [NWF3-U8](#nwf3-u8) | Dispersion conditioning matrix: every row/column needs own… | `active_law` | `data_contract` | neural-web |
| [RUL-F3.1](#rul-f3.1) | No new lobe charter ships; two-lobe cap remains consumed by… | `active_law` | `lobe` | neural-web |
| [RUL-F3.10](#rul-f3.10) | Tax engine killed; scenario-rate table ships; ST_TAX… | `killed` | `study` | neural-web |
| [RUL-F3.11](#rul-f3.11) | Realized-Decision Passport killed; revisit only after L2… | `killed` | `context` | neural-web |
| [RUL-F3.12](#rul-f3.12) | ThetaData tape calibration: ops-lane only;… | `active_law` | `data_contract` | options-alpha |
| [RUL-F3.13](#rul-f3.13) | Exit-crowding L1-L3 hard-blocked on ThetaData EOD pass;… | `active_law` | `lobe` | neural-web |
| [RUL-F3.15](#rul-f3.15) | Six-exit-problems taxonomy is charter-ready spec for L2… | `deferred` | `lobe` | neural-web |
| [RUL-F3.2](#rul-f3.2) | Exit/trim metrics attach to fire-tape counterfactuals only;… | `active_law` | `rail` | neural-web |
| [RUL-F3.3](#rul-f3.3) | Classifier labels must use pre-outcome state only;… | `active_law` | `constitution` | neural-web |
| [RUL-F3.4](#rul-f3.4) | exit_regret_v2.py killed; re-entry metrics deferred until… | `killed` | `study` | neural-web |
| [RUL-F3.5](#rul-f3.5) | ExitPolicy amended to add 'scaled' composite; TRIM-GRID-1… | `active_law` | `rail` | neural-web |
| [RUL-F3.6](#rul-f3.6) | DISP-GATE-1 build spec: feasibility gate first, fixed… | `active_law` | `study` | neural-web |
| [RUL-F3.7](#rul-f3.7) | Display-only guarantee tested in CI: risk_sizing must… | `active_law` | `constitution` | neural-web |
| [RUL-F3.8](#rul-f3.8) | Dispersion feature store, residual-trust model,… | `deferred` | `data_contract` | neural-web |
| [RUL-F3.9](#rul-f3.9) | NET-REPLAY-1: research-lane descriptive re-pricing only; no… | `active_law` | `study` | neural-web |
| [LIVE-U1](#live-u1) | Six organs all display/ops-tier; zero new trading authority… | `active_law` | `constitution` | neural-web |
| [LIVE-U2](#live-u2) | Degrade-never-raise: cortex job always exits 0; red is… | `active_law` | `rail` | neural-web |
| [LIVE-U3](#live-u3) | qi domain structurally excluded from daily brief (border… | `deferred` | `context` | neural-web |
| [LIVE-U4](#live-u4) | Promotion locks already structural: kernel FDR lock… | `adopted` | `constitution` | neural-web |
| [LIVE-U5](#live-u5) | Conformance rails: wiring tests + health… | `adopted` | `rail` | neural-web |
| [RUL-LIVE1](#rul-live1) | Cortex model calls route through llm_auth waterfall; no… | `active_law` | `rail` | neural-web |
| [RUL-LIVE2](#rul-live2) | Status taxonomy ok/warn/degraded/skipped; zero-tool and… | `active_law` | `constitution` | neural-web |
| [RUL-LIVE3](#rul-live3) | Fail-open: cortex/health/brief failures never block… | `active_law` | `rail` | neural-web |
| [RUL-LIVE4](#rul-live4) | Bottom sensors wired display-only; scored_path_surfaces… | `active_law` | `lobe` | neural-web |
| [RUL-LIVE5](#rul-live5) | health.json derived from synapse.yml + committed artifacts;… | `active_law` | `data_contract` | neural-web |
| [RUL-LIVE6](#rul-live6) | Two-phase finalization: engine builds health/brief cores;… | `active_law` | `process` | neural-web |
| [RUL-LIVE7](#rul-live7) | Daily brief is deterministic: no LLM prose, no trading… | `active_law` | `constitution` | neural-web |
| [RUL-LIVE8](#rul-live8) | context_stale self-detection: cortex flags deliberation… | `active_law` | `rail` | neural-web |
| [RUL-LIVE9](#rul-live9) | No new authority anywhere in the NW live operating layer;… | `active_law` | `constitution` | neural-web |
| [GAP-RUL-1](#gap-rul-1) | No new lobes — two-lobe cap (L1/L3 only) | `active_law` | `lobe` | neural-web |
| [GAP-RUL-2](#gap-rul-2) | Labels before models — no meta-model until floor reached | `active_law` | `constitution` | neural-web |
| [GAP-RUL-3](#gap-rul-3) | Avoid-long quarantine + contamination stamp (BD-AVOID-1) | `active_law` | `study` | neural-web |
| [GAP-RUL-4](#gap-rul-4) | Clocks not busywork — TIME-starved ledgers get clocks only | `active_law` | `process` | neural-web |
| [GAP-RUL-5](#gap-rul-5) | FDR accounting — budgets logged before runs, pooled SUM… | `active_law` | `process` | neural-web |
| [GAP-RUL-6](#gap-rul-6) | De-escalation shape — authority ceiling A3, altdata_brain… | `active_law` | `constitution` | neural-web |
| [GAP-RUL-8](#gap-rul-8) | Auth wall stands — no public write endpoint, no CORS… | `active_law` | `constitution` | neural-web |
| [GAP-U1](#gap-u1) | Scope fence — no fused scores, no sizing changes | `active_law` | `constitution` | neural-web |
| [GAP-U10](#gap-u10) | DISP-GATE-1 feasibility gate — PIT recomputation + >=252… | `active_law` | `study` | neural-web |
| [GAP-U11](#gap-u11) | BD-AVOID-1 maturity clock — no verdict before n>=300/side… | `active_law` | `study` | neural-web |
| [GAP-U12](#gap-u12) | Top-risk de-escalation blocked — S-TOP_RISK accrual gate… | `blocked` | `wave` | neural-web |
| [GAP-U13](#gap-u13) | Holdable-winner replay deferred to long-hold program | `deferred` | `study` | long-hold |
| [GAP-U15](#gap-u15) | Validated word banned from study reports | `active_law` | `process` | neural-web |
| [GAP-U16](#gap-u16) | BD-AVOID-1 long-side only for verdict; short-side… | `active_law` | `study` | neural-web |
| [GAP-U17](#gap-u17) | Fragility-veto study deferred — needs external joins not in… | `deferred` | `study` | neural-web |
| [GAP-U19](#gap-u19) | Short-side panel — accrual row only; no board chips until… | `active_law` | `context` | neural-web |
| [GAP-U2](#gap-u2) | Repair-stack study killed — FDR double-dip on frozen G1 F1 | `killed` | `study` | long-hold |
| [GAP-U22](#gap-u22) | BD-AVOID-1 compensating gate — >=8pp threshold, forward OOS… | `active_law` | `study` | neural-web |
| [GAP-U24](#gap-u24) | Lobe-5 Data Fitness folded — evidence-gap panel is the build | `no_build` | `lobe` | neural-web |
| [GAP-U3](#gap-u3) | EDGAR solvency/fragility lobe killed — two-lobe cap + own… | `killed` | `lobe` | neural-web |
| [GAP-U4](#gap-u4) | Options tissue consumption blocked — accrual gate… | `blocked` | `lobe` | neural-web |
| [GAP-U5](#gap-u5) | L6 macro games deferred — must beat noisy-sector precedent | `deferred` | `lobe` | neural-web |
| [GAP-U6](#gap-u6) | Short-volume FINRA species needs own prereg — SLF-001… | `deferred` | `study` | neural-web |
| [GAP-U7](#gap-u7) | Claim Reliability Lobe deferred — n_dates<25 floor not met | `deferred` | `lobe` | neural-web |
| [GAP-U8](#gap-u8) | Codex What-Not-To-Do list adopted — no fusion, no LLM… | `active_law` | `constitution` | neural-web |
| [GAP-U9](#gap-u9) | WAIT-GRID-1 — descriptive-only; wait_grid_v1 surface stamp… | `active_law` | `study` | neural-web |
| [RUL-T3-1](#rul-t3-1) | Closed proposals require new prereg citing closing evidence… | `active_law` | `process` | top3-lobe-power-up |
| [RUL-T3-2](#rul-t3-2) | Clock-first ordering: ledger-openers outrank capability… | `active_law` | `process` | neural-web |
| [RUL-T3-3](#rul-t3-3) | Truth-maintenance work is RAIL work, not lobe build | `active_law` | `rail` | neural-web |
| [RUL-T3-5](#rul-t3-5) | No confidence number without Wilson/Jeffreys bound; all… | `active_law` | `constitution` | neural-web |
| [TOP3-E2](#top3-e2) | E2 recall-first near-miss learner: KILL — hindsight label +… | `killed` | `study` | entry-stack |
| [TOP3-E3](#top3-e3) | E3 kernel-rank v2: NO BUILD — accruing; extensions only via… | `no_build` | `lobe` | entry-stack |
| [TOP3-E5](#top3-e5) | E5 lifecycle/hazard model: KILL — same tape as E3,… | `killed` | `study` | entry-stack |
| [TOP3-L2](#top3-l2) | L2 multi-family FDR battery: KILL as duplicate; OOS… | `residue_adopted` | `study` | long-hold-thesis |
| [TOP3-L3](#top3-l3) | L3 thesis-transition ledger: DEFER — W3-locked until G1… | `deferred` | `lobe` | long-hold-thesis |
| [TOP3-L5](#top3-l5) | L5 analogue explainer: DEFER post-G1; as written is D-7… | `deferred` | `lobe` | long-hold-thesis |
| [TOP3-M1](#top3-m1) | M1 clock-first ordering: ADOPTED as program ordering… | `adopted` | `process` | neural-web |
| [TOP3-M2](#top3-m2) | M2 contradiction pair-g: annotation-only, severity ≤… | `adopted` | `rail` | neural-web |
| [TOP3-M3](#top3-m3) | M3 regret-context card: QUEUED Phase E-Next; display-only,… | `deferred` | `context` | neural-web |
| [TOP3-M4](#top3-m4) | M4 operator-tape outcome resolution: LLM may never author… | `adopted` | `data_contract` | neural-web |
| [TOP3-M5](#top3-m5) | M5 calibration: all primitives must use grading_stats.py… | `adopted` | `rail` | neural-web |
| [TOP3-M7](#top3-m7) | M7 compounder proxy label: KILL — wrong-ruler, validates… | `killed` | `study` | long-hold-thesis |
| [TOP3-O1](#top3-o1) | O1 onset-quality calibrator: KILL — adjudicated NULL, no… | `killed` | `study` | oracle-rotation |
| [TOP3-O2](#top3-o2) | O2 flow-routing tensor: KILL — built + naming-fraud risk | `killed` | `lobe` | oracle-rotation |
| [TOP3-O3](#top3-o3) | O3 member-phase intelligence: KILL as independent build;… | `killed` | `lobe` | oracle-rotation |
| [TOP3-O4](#top3-o4) | O4 reversion sequential evidence engine: KILL — duplicate… | `killed` | `wave` | oracle-rotation |
| [TOP3-O5](#top3-o5) | O5 truth-maintenance: AMEND to baseline publication +… | `adopted` | `rail` | neural-web |
| [TOP3-U1](#top3-u1) | Two-lobe concurrency cap: no new lobe chartered by this… | `active_law` | `constitution` | neural-web |
| [TOP3-U2](#top3-u2) | Grader-STARVED rows define each lobe's real ledger to-do… | `active_law` | `process` | neural-web |
| [TOP3-U4](#top3-u4) | Printed-NULL O1 ruling: p_confirm is an untrainable target;… | `active_law` | `study` | oracle-rotation |
| [TOP3-U5](#top3-u5) | rs_repair bind blocked until ≥20 trading days accrual +… | `blocked` | `data_contract` | entry-stack |
| [NEXT3-U1](#next3-u1) | BD-ECON-1 NULL law — avoid lens does not transfer to board… | `active_law` | `signal_family` | next3-upgrades |
| [NEXT3-U10](#next3-u10) | 5-U2 outcome-conditioned options report DEFER —… | `deferred` | `study` | next3-upgrades |
| [NEXT3-U11](#next3-u11) | 6-U5 weekly review — must extend deterministic-brief… | `deferred` | `wave` | next3-upgrades |
| [NEXT3-U12](#next3-u12) | 6-U4 lobe impact attribution DEFERRED — requires W-EX and… | `deferred` | `wave` | next3-upgrades |
| [NEXT3-U13](#next3-u13) | 6-U3 reason taxonomy RECOMMEND-ROUTE — blocked on PR-C4 | `deferred` | `wave` | next3-upgrades |
| [NEXT3-U15](#next3-u15) | Scope fence — no short execution, no meta-models, no board… | `active_law` | `constitution` | next3-upgrades |
| [NEXT3-U16](#next3-u16) | 5-U5 analogue library DEFERRED — premature until W-E0… | `deferred` | `study` | next3-upgrades |
| [NEXT3-U19](#next3-u19) | SLF-001 null/no-go standing prior for short-side pressure… | `active_law` | `signal_family` | next3-upgrades |
| [NEXT3-U2](#next3-u2) | Phase-0b species all PARKED — breakdown grammar does not… | `no_build` | `signal_family` | next3-upgrades |
| [NEXT3-U20](#next3-u20) | Exposure date law — artifact as_of, never run date | `active_law` | `data_contract` | next3-upgrades |
| [NEXT3-U3](#next3-u3) | Multi-evidence conditioning report KILL — per-axis… | `killed` | `study` | next3-upgrades |
| [NEXT3-U4](#next3-u4) | DecisionPacket schema REJECT — cross-lobe chain prohibited | `killed` | `data_contract` | next3-upgrades |
| [NEXT3-U5](#next3-u5) | Lobe-cap taxonomy clarification — 'lobes 4/5/6' are not… | `active_law` | `lobe` | next3-upgrades |
| [NEXT3-U6](#next3-u6) | BD-3 sharper fact — partial short-species candidate, not… | `active_law` | `signal_family` | next3-upgrades |
| [NEXT3-U7](#next3-u7) | W-E1 skeptical priors — skew-decel unsupported; DOI dead at… | `active_law` | `signal_family` | options-nw-entry-intelligence |
| [NEXT3-U9](#next3-u9) | 5-U4 top-risk handoff OWNED/BLOCKED — S-TOP_RISK gate… | `blocked` | `wave` | next3-upgrades |
| [RUL-U1](#rul-u1) | Zero lobe charters — cap stays L1+L3 | `active_law` | `lobe` | next3-upgrades |
| [RUL-U10](#rul-u10) | Language law — 'validated' banned; plain-language box… | `active_law` | `constitution` | next3-upgrades |
| [RUL-U2](#rul-u2) | Ownership seniority — sibling programs own touched surfaces | `active_law` | `process` | next3-upgrades |
| [RUL-U3](#rul-u3) | BD-ECON-1 lawful shape — research-only, no live authority | `active_law` | `study` | next3-upgrades |
| [RUL-U3a](#rul-u3a) | Budget semantics: log_declared_budget is per-family max(),… | `active_law` | `constitution` | next3-upgrades |
| [RUL-U4](#rul-u4) | Phase-0b lawful shape — one prereg, three definitions,… | `active_law` | `study` | next3-upgrades |
| [RUL-U6](#rul-u6) | W-EX measurement-substrate-only — no statistics, no… | `active_law` | `data_contract` | next3-upgrades |
| [RUL-U7](#rul-u7) | Analogue-library fences — prereg-first, research artifacts… | `deferred` | `study` | next3-upgrades |
| [RUL-U9](#rul-u9) | LLM law — no LLM origination, scoring, or escalation | `active_law` | `constitution` | next3-upgrades |
| [NEXTL-U1](#nextl-u1) | Long-Term Thesis lobe KILL: duplicates chartered long-hold… | `killed` | `lobe` | long-hold-thesis |
| [NEXTL-U10](#nextl-u10) | Reverse-DCF card routed to long-hold program W3; not built… | `no_build` | `study` | long-hold-thesis |
| [NEXTL-U11](#nextl-u11) | ABS-1 lean_out delay contrast deferred as batch-3 follow-on… | `deferred` | `study` | neural-web |
| [NEXTL-U12](#nextl-u12) | Scope fence: no meta-models, composite scores, sizing… | `active_law` | `constitution` | neural-web |
| [NEXTL-U13](#nextl-u13) | 13F-as-positive-sponsorship: opposite sign to filed phase-0… | `killed` | `signal_family` | entry-stack |
| [NEXTL-U19](#nextl-u19) | Sponsorship lifecycle grammar deferred to docket L10… | `deferred` | `signal_family` | neural-web |
| [NEXTL-U2](#nextl-u2) | Meta-verdict: zero of five proposed lobes clear the docket… | `active_law` | `constitution` | neural-web |
| [NEXTL-U20](#nextl-u20) | rs_repair_state is an explicit stub; owned by… | `deferred` | `data_contract` | entry-intelligence |
| [NEXTL-U4](#nextl-u4) | F-HZ-1 run-gated on dilution_events.parquet materializing… | `deferred` | `study` | neural-web |
| [NEXTL-U7](#nextl-u7) | F-HZ-2 deferred to A2 G1-Retest clock (~2027-H2) | `deferred` | `study` | long-hold-thesis |
| [NEXTL-U8](#nextl-u8) | F-HZ-3 (ev_blackout extension): operative-panel mae21 null… | `deferred` | `study` | entry-stack |
| [NEXTL-U9](#nextl-u9) | Execution realism half (L5) blocked on R4 Mastermind… | `blocked` | `rail` | neural-web |
| [RUL-N1](#rul-n1) | Zero lobes chartered; two-lobe cap (L1/L3) holds | `active_law` | `lobe` | neural-web |
| [RUL-N2](#rul-n2) | Decision-chain operating stack struck; no organ may gate… | `active_law` | `constitution` | neural-web |
| [RUL-N3](#rul-n3) | Sponsorship: only C3 neutral vocabulary; 13F/ownership leg… | `active_law` | `signal_family` | entry-stack |
| [RUL-N5](#rul-n5) | n-before-stat: print fire-n and cluster-n before any… | `active_law` | `process` | neural-web |
| [RUL-N6](#rul-n6) | Abstention prior is wait_costs; foregone upside printed… | `active_law` | `constitution` | neural-web |
| [RUL-N7](#rul-n7) | F-HZ-1 runs standalone as dilution_hazard family; not… | `active_law` | `study` | neural-web |
| [RUL-N8](#rul-n8) | DQ-2 activation floor: n>=25 graded operator actions before… | `active_law` | `rail` | neural-web |
| [RUL-N9](#rul-n9) | No re-litigation of frozen/nulled families or settled… | `active_law` | `constitution` | neural-web |
| [RF-1](#rf-1) | Charter: factory is orchestration layer only; delegates all… | `adopted` | `constitution` | research-factory |
| [RF-10](#rf-10) | Kill-scrutiny symmetry: every kill carries kill_evidence… | `active_law` | `process` | research-factory |
| [RF-11](#rf-11) | Authority mechanism: display_only field + CI gate + synapse… | `adopted` | `constitution` | research-factory |
| [RF-12](#rf-12) | Governance events: factory transitions use… | `active_law` | `data_contract` | research-factory |
| [RF-13](#rf-13) | Domain seams: Oracle two-track fork; cortex never writes… | `active_law` | `process` | research-factory |
| [RF-14](#rf-14) | Dedup law: deterministic-first in fixed order; near-dup… | `active_law` | `process` | research-factory |
| [RF-15](#rf-15) | Respin law: hard cap 2 cycles per lineage; generation 3… | `active_law` | `process` | research-factory |
| [RF-16](#rf-16) | Rejected shapes: no autonomous trading, no LLM codegen, no… | `active_law` | `constitution` | research-factory |
| [RF-2](#rf-2) | Projection law: factory persists spec_ref only; domain… | `active_law` | `data_contract` | research-factory |
| [RF-3](#rf-3) | Naming: candidate_type field; claim_shape reserved for… | `active_law` | `data_contract` | research-factory |
| [RF-4](#rf-4) | State machine: exactly 15 states, no phantoms;… | `active_law` | `process` | research-factory |
| [RF-5](#rf-5) | Actor law: human-gate required for… | `active_law` | `process` | research-factory |
| [RF-6](#rf-6) | Trial accounting: rf.* family regex; screened transition… | `active_law` | `process` | research-factory |
| [RF-7](#rf-7) | Challenger law: advisory-only; outcome-blind; LLM… | `active_law` | `process` | research-factory |
| [RF-8](#rf-8) | Ledger law: append-only transitions; forward ledgers… | `active_law` | `data_contract` | research-factory |
| [RF-9](#rf-9) | Clock law: no bespoke clocks; experiments… | `active_law` | `process` | research-factory |
| [RF-U1](#rf-u1) | Authority ceiling: factory operates at A0-A2 only; Article… | `active_law` | `constitution` | research-factory |
| [RF-U11](#rf-u11) | Reviewer outcome-blind: forbidden from asserting realized… | `active_law` | `process` | research-factory |
| [RF-U2](#rf-u2) | Batch B (cortex) deferred until machine_registry.jsonl has… | `deferred` | `wave` | research-factory |
| [RF-U3](#rf-u3) | W-CODEGEN: separate future program; requires OS/identity… | `no_build` | `wave` | research-factory |
| [RF-U4](#rf-u4) | W-AUTO deferred: scheduled LLM extraction only after Batch… | `deferred` | `wave` | research-factory |
| [RF-U5](#rf-u5) | Committee-page factory metrics: admin-only until further… | `deferred` | `context` | research-factory |
| [RF-U7](#rf-u7) | Factory evaluates nothing; scores nothing; touches no board | `active_law` | `constitution` | research-factory |
| [RF-U8](#rf-u8) | Cortex adapter: never writes machine_registry; respects… | `active_law` | `data_contract` | research-factory |
| [RF-U9](#rf-u9) | promote_eligible is NOT an autonomy rung and NOT a gauntlet… | `active_law` | `constitution` | research-factory |
| [BRIDGE-U1](#bridge-u1) | Bridge is context-only at birth; all authority booleans… | `active_law` | `data_contract` | nw-mastermind-bridge |
| [BRIDGE-U10](#bridge-u10) | Shadow accrual starts at birth, flag-independent | `active_law` | `process` | nw-mastermind-bridge |
| [BRIDGE-U11](#bridge-u11) | NW is not an intake source; cannot add candidates or score | `active_law` | `constitution` | nw-mastermind-bridge |
| [BRIDGE-U12](#bridge-u12) | Candidate context scope rule: restricted to candidate… | `active_law` | `data_contract` | nw-mastermind-bridge |
| [BRIDGE-U14](#bridge-u14) | Reader not added to macro_refresh._ANCHOR_DEFS; advisory… | `active_law` | `rail` | nw-mastermind-bridge |
| [BRIDGE-U17](#bridge-u17) | no new money-path wiring; listed modules must not be… | `active_law` | `constitution` | nw-mastermind-bridge |
| [BRIDGE-U19](#bridge-u19) | W-next dashboard UI panel and promotion gauntlet deferred | `deferred` | `wave` | nw-mastermind-bridge |
| [BRIDGE-U2](#bridge-u2) | MASTERMIND_NW_CONTEXT defaults OFF; dark ship with… | `active_law` | `constitution` | nw-mastermind-bridge |
| [BRIDGE-U20](#bridge-u20) | allowed_behavior for candidate_context rows is annotate_only | `active_law` | `data_contract` | nw-mastermind-bridge |
| [BRIDGE-U21](#bridge-u21) | Candidate feeds stay direct; no big-bang rewiring of intake… | `active_law` | `constitution` | nw-mastermind-bridge |
| [BRIDGE-U25](#bridge-u25) | fdr_cleared must be false while survivors[] is empty | `active_law` | `data_contract` | nw-mastermind-bridge |
| [BRIDGE-U3](#bridge-u3) | Kernel armed re-labeling mandatory; raw armed never crosses… | `active_law` | `data_contract` | nw-mastermind-bridge |
| [BRIDGE-U4](#bridge-u4) | Kernel behavior-facing actions blocked until 2026-10-01 FDR… | `active_law` | `rail` | nw-mastermind-bridge |
| [BRIDGE-U5](#bridge-u5) | Cortex prose excluded from seat prompts; /api/ask never… | `active_law` | `constitution` | nw-mastermind-bridge |
| [BRIDGE-U6](#bridge-u6) | No ticker names beyond candidate universe cross into… | `active_law` | `data_contract` | nw-mastermind-bridge |
| [BRIDGE-U7](#bridge-u7) | regime_frame not touched; NW synthesis rides as advisory… | `active_law` | `rail` | nw-mastermind-bridge |
| [BRIDGE-U8](#bridge-u8) | NW market_view plane must be advisory-status, never in tilt… | `active_law` | `rail` | nw-mastermind-bridge |
| [BRIDGE-U9](#bridge-u9) | Staleness only shrinks; stale/absent context never makes… | `active_law` | `rail` | nw-mastermind-bridge |
| [FACTOR-U1](#factor-u1) | Cross-job artifact writes invisible between jobs; nightly… | `active_law` | `constitution` | factor-intelligence |
| [FACTOR-U2](#factor-u2) | factor_ops dispatch workflow: no push permitted;… | `active_law` | `process` | factor-intelligence |
| [FACTOR-U4](#factor-u4) | kernel_style.py shadow table and validate_factor harnesses… | `deferred` | `wave` | factor-intelligence |
| [FACTOR-U5](#factor-u5) | fire_coordinates.jsonl is PIT by construction; no replay… | `active_law` | `data_contract` | factor-intelligence |
| [FACTOR-U7](#factor-u7) | PREREGISTRATION.md gates are locked; §0 vocabulary and… | `active_law` | `constitution` | factor-intelligence |
| [RUL-NW1](#rul-nw1) | factor_panel job is sole committer of factor-namespace… | `active_law` | `process` | factor-intelligence |
| [RUL-NW10](#rul-nw10) | Three append-only accrual artifacts chartered;… | `adopted` | `data_contract` | factor-intelligence |
| [RUL-NW11](#rul-nw11) | Every factor artifact needs synapse.yml entry; factor… | `active_law` | `process` | factor-intelligence |
| [RUL-NW2](#rul-nw2) | world_state reads factor_intelligence_state.json as… | `adopted` | `lobe` | factor-intelligence |
| [RUL-NW3](#rul-nw3) | Three cortex tools in v1; all read committed artifacts only | `adopted` | `lobe` | factor-intelligence |
| [RUL-NW4](#rul-nw4) | Ask-the-Brain factor path: read-only, directional verbs… | `adopted` | `rail` | factor-intelligence |
| [RUL-NW6](#rul-nw6) | A3 activation floor: 25 episode-clustered events / 3 months… | `active_law` | `constitution` | factor-intelligence |
| [RUL-NW7](#rul-nw7) | factors.html gains NW-integration status panel with… | `adopted` | `context` | factor-intelligence |
| [RUL-NW8](#rul-nw8) | Committee per-ticker factor lane deferred to P4; H status… | `deferred` | `lobe` | factor-intelligence |
| [RUL-NW9](#rul-nw9) | allowed_actions block is descriptive only; must never… | `active_law` | `constitution` | factor-intelligence |
| [ORTH-U1](#orth-u1) | Program-level: display-only, no execution authority granted | `active_law` | `constitution` | nw-rails |
| [ORTH-U12](#orth-u12) | Confluence today applies no independence adjustment;… | `active_law` | `context` | nw-rails |
| [ORTH-U2](#orth-u2) | Core ruling: build a rail, not a lobe; no new PCA trading… | `adopted` | `lobe` | nw-rails |
| [ORTH-U3](#orth-u3) | OOS-decay headline is a noise artifact; Opus review… | `active_law` | `constitution` | nw-rails |
| [ORTH-U5](#orth-u5) | Phase 0: display + explain only; Phase 3: never origination… | `active_law` | `constitution` | nw-rails |
| [ORTH-U6](#orth-u6) | Health band promotion requires >=6 months spine history and… | `deferred` | `process` | nw-rails |
| [ORTH-U7](#orth-u7) | Spine density come-back 2026-10-06: check… | `deferred` | `context` | nw-rails |
| [ORTH-U8](#orth-u8) | Genuine gap: live lobe-to-lobe covariance,… | `active_law` | `constitution` | nw-rails |
| [ORTH-U9](#orth-u9) | Nulls printed not hidden; coverage caveats mandatory on… | `active_law` | `constitution` | nw-rails |
| [RUL-ORTH-1](#rul-orth-1) | R-ORTH is a rail: infrastructure tier, context horizon, no… | `active_law` | `rail` | nw-rails |
| [RUL-ORTH-11](#rul-orth-11) | Committee annotations are deterministic-engine-generated;… | `active_law` | `constitution` | nw-rails |
| [RUL-ORTH-12](#rul-orth-12) | Factor residual layer deferred; factor block limited to… | `deferred` | `wave` | nw-rails |
| [RUL-ORTH-2](#rul-orth-2) | covariance_spine.json registered in synapse.yml as… | `adopted` | `data_contract` | nw-rails |
| [RUL-ORTH-4](#rul-orth-4) | spine_index.parquet is the sole lobe fire/intensity… | `active_law` | `data_contract` | nw-rails |
| [RUL-ORTH-5](#rul-orth-5) | Effective-witness fields visible immediately as… | `active_law` | `rail` | nw-rails |
| [RUL-ORTH-6](#rul-orth-6) | DISP-EIGEN-1 gate activation deferred until DISP-GATE-1… | `deferred` | `signal_family` | nw-rails |
| [RUL-ORTH-7](#rul-orth-7) | Residual RV lobe: no charter, no build until all four… | `no_build` | `lobe` | nw-rails |
| [RUL-ORTH-8](#rul-orth-8) | Null-calibration law: OOS-decay metrics must show… | `active_law` | `constitution` | nw-rails |
| [RUL-ORTH-9](#rul-orth-9) | No recomputation: existing orthogonality engines stay in… | `active_law` | `process` | nw-rails |
| [FR-11](#fr-11) | Item D scope limited to flat delayed-fill sweep;… | `deferred` | `study` | nw-quant-synthesis |
| [FR-12](#fr-12) | Item E artifacts unregistered in data/research/ until a… | `active_law` | `data_contract` | nw-quant-synthesis |
| [FR-13](#fr-13) | Report 1 tradeability/capacity roll-up folded; extend… | `killed` | `lobe` | nw-quant-synthesis |
| [FR-2](#fr-2) | Duplicate-of-existing registry in §3 is authoritative — do… | `active_law` | `process` | nw-quant-synthesis |
| [FR-4](#fr-4) | All program outputs display-only/context tier; zero board… | `active_law` | `constitution` | nw-quant-synthesis |
| [FR-5](#fr-5) | Alpha grammar first family must use tier-fire panels, not… | `active_law` | `signal_family` | nw-quant-synthesis |
| [FR-6](#fr-6) | Overlap map emits cluster metadata only; no combined score;… | `deferred` | `lobe` | nw-quant-synthesis |
| [FR-7](#fr-7) | failed_breakout registered as S14 phase0/display-only —… | `adopted` | `signal_family` | nw-quant-synthesis |
| [FR-8](#fr-8) | Render budget law: EDGAR crawling and replay sweeps off the… | `active_law` | `data_contract` | nw-quant-synthesis |
| [FR-9](#fr-9) | Hazard panel is macro/cycle-level only; per-stock features… | `active_law` | `data_contract` | nw-quant-synthesis |
| [FR-1](#fr-1) | utility_router / meta_router-with-sizing REJECTED —… | `killed` | `lobe` | nw-quant-synthesis |
| [QS-U1](#qs-u1) | House doctrine (no master score, no LLM-originated signals,… | `active_law` | `constitution` | nw-quant-synthesis |
| [QS-U10](#qs-u10) | Paid-data candidates (analyst dispersion, borrow, true fund… | `deferred` | `signal_family` | nw-quant-synthesis |
| [QS-U11](#qs-u11) | Confidence surface (Brier/Wilson/ECE) already built; kernel… | `duplicate` | `lobe` | nw-quant-synthesis |
| [QS-U13](#qs-u13) | Hazard/survival desk is built at macro level; per-stock… | `duplicate` | `lobe` | nw-quant-synthesis |
| [QS-U14](#qs-u14) | Post-event absorption already registered as S9 (bad-news… | `duplicate` | `signal_family` | nw-quant-synthesis |
| [QS-U15](#qs-u15) | Disagreement mining built; dissent study under-powered — do… | `duplicate` | `study` | nw-quant-synthesis |
| [QS-U2](#qs-u2) | Research queue is read-only;… | `active_law` | `process` | nw-quant-synthesis |
| [QS-U4](#qs-u4) | Alpha grammar: TrialLedger.log_grid() must be called BEFORE… | `active_law` | `process` | nw-quant-synthesis |
| [QS-U5](#qs-u5) | Alpha grammar lag must be >= 1 (PIT law); candidate cap v1… | `active_law` | `signal_family` | nw-quant-synthesis |
| [QS-U6](#qs-u6) | Staleness replay: exponential decay fit gate required;… | `active_law` | `study` | nw-quant-synthesis |
| [QS-U7](#qs-u7) | Promotion path inherited unchanged from NW + species… | `active_law` | `constitution` | nw-quant-synthesis |
| [QS-U8](#qs-u8) | Regime specialists (MoE) must not be built… | `blocked` | `lobe` | nw-quant-synthesis |
| [QS-U9](#qs-u9) | Crowding/effective-bets split-half FAIL — do not revive… | `duplicate` | `signal_family` | nw-quant-synthesis |
| [DT-R1](#dt-r1) | Docket disposition: Codex build plan not adopted; no new… | `active_law` | `constitution` | dannytrades |
| [DT-R11a](#dt-r11a) | DannyTrades-derived numbers are display-only; 'validated'… | `active_law` | `constitution` | dannytrades |
| [DT-R11b](#dt-r11b) | Danny composite must never blend into momentum ranker | `active_law` | `constitution` | dannytrades |
| [DT-R12](#dt-r12) | data/massive_stock_day/ is sole sanctioned volume… | `active_law` | `data_contract` | dannytrades |
| [DT-R13](#dt-r13) | Whale directional restoration path: requires month-block… | `killed` | `signal_family` | dannytrades |
| [DT-R14](#dt-r14) | Time-control law: calendar-time control mandatory in… | `active_law` | `constitution` | dannytrades |
| [DT-R15](#dt-r15) | Whale family closed: restoration denied; pooled… | `killed` | `signal_family` | dannytrades |
| [DT-R16](#dt-r16) | Era-split disclosure law: pooled pass must show modern-era… | `active_law` | `constitution` | dannytrades |
| [DT-R2](#dt-r2) | No-chase engine killed as duplicate; invalid_if_below… | `killed` | `signal_family` | dannytrades |
| [DT-R3](#dt-r3) | Sponsorship ensemble illegal under Signal Commons R3 | `killed` | `signal_family` | dannytrades |
| [DT-R5](#dt-r5) | Volatility-void 5-definition family killed; def-4 parked… | `killed` | `signal_family` | entry-stack |
| [DT-R6](#dt-r6) | Big-leader composite gate forbidden; concentration_passport… | `killed` | `lobe` | long-hold |
| [DT-R7](#dt-r7) | DCA policy object killed; price-memory bundle dispatched to… | `residue_adopted` | `study` | entry-intelligence |
| [DT-R8](#dt-r8) | Monthly trim desk deferred to future L2 Exit&Trim charter | `deferred` | `lobe` | neural-web |
| [DT-R9](#dt-r9) | Operator ledger duplicate; behavioral label vocabulary… | `duplicate` | `rail` | neural-web |
| [DT-U1](#dt-u1) | Chip now purely descriptive: all directional claims retired… | `active_law` | `signal_family` | dannytrades |
| [DT-U5](#dt-u5) | concentration/leader-book idea routed to Mastermind repo… | `no_build` | `process` | dannytrades-adjudication |
| [DT-U6](#dt-u6) | Behavioral label vocab parked at L4 DQ-2 n>=25 floor… | `deferred` | `wave` | neural-web |
| [DT-U7](#dt-u7) | Void-box def-4 and retest states parked behind S-SQ phase-0… | `deferred` | `wave` | entry-stack |
| [DT-U8](#dt-u8) | leader_liquidity_pass and survivable_drawdown_capacity only… | `deferred` | `signal_family` | long-hold |
| [DT-U9](#dt-u9) | Monthly sponsorship-decay trim input contingent on DT-W1… | `blocked` | `study` | neural-web |
| [ESX-RUL-1](#esx-rul-1) | Volume-confirmation confirmers permanently dead (H4) | `active_law` | `signal_family` | entry-stack |
| [ESX-RUL-10](#esx-rul-10) | Replay-mismatch handled via legal registry moves only; no… | `active_law` | `process` | entry-stack |
| [ESX-RUL-11](#esx-rul-11) | No fire testifies twice: backfill rows excluded from FDR… | `active_law` | `constitution` | entry-stack |
| [ESX-RUL-12](#esx-rul-12) | R1 estimator fully specified; FE granularity fixed once at… | `active_law` | `process` | entry-stack |
| [ESX-RUL-2](#esx-rul-2) | R1 date-FE estimator mandatory for all stratum studies | `active_law` | `process` | entry-stack |
| [ESX-RUL-3](#esx-rul-3) | Null-competitors NC-1/NC-2 run first; NC-2 marginality… | `active_law` | `process` | entry-stack |
| [ESX-RUL-4](#esx-rul-4) | S-EV only candidate permitted as hard gate (hygiene-only) | `active_law` | `signal_family` | entry-stack |
| [ESX-RUL-5](#esx-rul-5) | Species register before first compute; expect-null… | `active_law` | `process` | entry-stack |
| [ESX-RUL-6](#esx-rul-6) | Derivatives-shape throttle accrue-only until ≥120 skew dates | `deferred` | `signal_family` | entry-stack |
| [ESX-RUL-7](#esx-rul-7) | §5 thresholds frozen at W0 reviewer sign-off; changes need… | `active_law` | `constitution` | entry-stack |
| [ESX-RUL-8](#esx-rul-8) | Backfilled spine rows carry version: backfill-v1 tag;… | `active_law` | `data_contract` | entry-stack |
| [ESX-RUL-9](#esx-rul-9) | One grader per program; wave1 numbers are context only | `active_law` | `constitution` | entry-stack |
| [ESX-U1](#esx-u1) | HK/CA excluded by default from all species tests | `active_law` | `constitution` | entry-stack |
| [ESX-U10](#esx-u10) | S-EV demotes to live-veto-only if 8-K date build fails… | `active_law` | `data_contract` | entry-stack |
| [ESX-U14](#esx-u14) | Species law: monthly review is sole status mover; falsified… | `active_law` | `constitution` | entry-stack |
| [ESX-U15](#esx-u15) | Kernel cells accrue display-first; consumption forbidden… | `deferred` | `lobe` | entry-stack |
| [ESX-U18](#esx-u18) | CHIP promotion floor: n≥400 fires, stop5 FE ≥2pp CI… | `active_law` | `constitution` | entry-stack |
| [ESX-U2](#esx-u2) | Display-only until earned via… | `active_law` | `constitution` | entry-stack |
| [ESX-U3](#esx-u3) | Nightly is sole ledger advancer; intraday lanes never… | `active_law` | `data_contract` | entry-stack |
| [ESX-U4](#esx-u4) | Exit-rule revival is a non-goal; EMA8 is tail-flag only | `killed` | `signal_family` | entry-stack |
| [ESX-U6](#esx-u6) | LLM law: models may de-escalate calibrated keys only; no… | `active_law` | `constitution` | entry-stack |
| [ESX-U7](#esx-u7) | S-SQ 'arming' variant banned from family; release-bar-only… | `active_law` | `signal_family` | entry-stack |
| [ESX-U9](#esx-u9) | S-QL PIT status disclosed: assumed 120d lag;… | `active_law` | `data_contract` | entry-stack |
| [ESX-R2-ADJACENCY](#esx-r2-adjacency) | Adjacency citation required before first compute;… | `active_law` | `process` | entry-stack |
| [ESX-FV-A3m](#esx-fv-a3m) | A3m esx_htf_turn monthly — NULL by non-replication;… | `killed` | `signal_family` | entry-stack |
| [ESX-FV-B](#esx-fv-b) | B esx_htf_turn_dose — NULL/DESCRIPTIVE; proximity gradient,… | `killed` | `signal_family` | entry-stack |
| [ESX-FV-C](#esx-fv-c) | C esx_washout_x_turn — KILLED; depth adds negative marginal… | `killed` | `signal_family` | entry-stack |
| [ESX-FV-E](#esx-fv-e) | E esx_decline_geometry — DISPLAY-CANDIDATE; flush… | `adopted` | `signal_family` | entry-stack |
| [ESX-FV-F](#esx-fv-f) | F esx_underwater — ADVERSE-CONTEXT; shadow only,… | `adopted` | `signal_family` | entry-stack |
| [ESX-FV-G](#esx-fv-g) | G esx_vol_transition — NULL (expect-null confirmed);… | `killed` | `signal_family` | entry-stack |
| [ESX-RUL-27](#esx-rul-27) | A3 identity, scope, marginals-first law — esx_* families,… | `active_law` | `constitution` | entry-stack |
| [ESX-RUL-28](#esx-rul-28) | Verdict-ceiling law — A3 families capped at… | `active_law` | `constitution` | entry-stack |
| [ESX-RUL-29](#esx-rul-29) | Admission-leg law — weekly RSI-MACD families must include… | `active_law` | `constitution` | entry-stack |
| [ESX-RUL-30](#esx-rul-30) | De-confound battery — frozen kill-only diagnostics for A3… | `active_law` | `constitution` | entry-stack |
| [ESX-RUL-31](#esx-rul-31) | HTF PIT + faithful-math law — last completed bar, pinned… | `active_law` | `constitution` | entry-stack |
| [ESXA3-U1](#esxa3-u1) | S6 owns serial-failure / nth-fire constructs — A3 may not… | `active_law` | `signal_family` | entry-stack |
| [ESXA3-U3](#esxa3-u3) | Gate confirm3 already reads weekly state — weekly strata… | `active_law` | `constitution` | entry-stack |
| [ESXA3-U4](#esxa3-u4) | A2 esx_htf_turn 2W — NULL; knife-edge p and mae21… | `killed` | `signal_family` | entry-stack |
| [ESX-U5](#esx-u5) | Non-replication override — adjudication supersedes… | `active_law` | `constitution` | entry-stack |
| [ESXA3-U6](#esxa3-u6) | Interaction/confluence gating — only E-based confluences… | `active_law` | `constitution` | entry-stack |
| [RUL-33-BASEEFF](#rul-33-baseeff) | REJECTED: esx_base_efficiency (Kaufman ER / choppiness) —… | `killed` | `signal_family` | entry-stack |
| [RUL-33-COILRANGE](#rul-33-coilrange) | REJECTED: esx_coil_range_at_fire — banned… | `killed` | `signal_family` | entry-stack |
| [RUL-33-DEGREEALGN](#rul-33-degreealgn) | DEFERRED to A4: esx_degree_alignment —… | `deferred` | `signal_family` | entry-stack |
| [RUL-33-DIVFIRE](#rul-33-divfire) | REJECTED: esx_div_fire (standalone divergence) —… | `killed` | `signal_family` | entry-stack |
| [RUL-33-OSCSPECIES](#rul-33-oscspecies) | DECLINED: new oscillator species… | `killed` | `signal_family` | entry-stack |
| [RUL-33-SECONDTEST](#rul-33-secondtest) | REJECTED: esx_second_test (double-bottom hold) — proximity… | `killed` | `signal_family` | entry-stack |
| [RUL-33-SERIAL](#rul-33-serial) | REJECTED: esx_serial_fuel / nth-fire ordinal — owned by S6… | `killed` | `signal_family` | entry-stack |
| [RUL-33-SUBTICKS](#rul-33-subticks) | REJECTED: esx_sub_x_ticks — unpowered (deep×ticks cell ~740… | `killed` | `signal_family` | entry-stack |
| [LH-R1](#lh-r1) | Horizon firewall: bidirectional CI-enforced entry/hold… | `adopted` | `constitution` | long-hold-thesis |
| [LH-R10](#lh-r10) | Species coordination: expectation-drift coordinates with… | `active_law` | `lobe` | long-hold-thesis |
| [LH-R11](#lh-r11) | Multi-family roster: frozen pre-registered with HLZ/BH-FDR… | `adopted` | `constitution` | long-hold-thesis |
| [LH-R12](#lh-r12) | Program hypothesis ceiling: Σ registered hypotheses ≤ 40… | `active_law` | `constitution` | long-hold-thesis |
| [LH-R14](#lh-r14) | Two-ruler discipline: Ruler-P display-only; Ruler-H is sole… | `active_law` | `constitution` | long-hold-thesis |
| [LH-R2](#lh-r2) | No fused admission: AND-gate of independent flags only | `active_law` | `constitution` | long-hold-thesis |
| [LH-R3](#lh-r3) | Survivorship stamps: 756d refused as headline; UPPER BOUND… | `active_law` | `data_contract` | long-hold-thesis |
| [LH-R4](#lh-r4) | Effective-n discipline: n≥25 episode-clusters;… | `active_law` | `constitution` | long-hold-thesis |
| [LH-R5](#lh-r5) | FDR isolation: long_hold family isolated from entry desk… | `active_law` | `signal_family` | long-hold-thesis |
| [LH-R6](#lh-r6) | LLM law: transitions by tripwires only; LLM is commentary… | `active_law` | `constitution` | long-hold-thesis |
| [LH-R7](#lh-r7) | Ledger law: thesis ledger and label store are forward… | `active_law` | `data_contract` | long-hold-thesis |
| [LH-R8](#lh-r8) | Kernel clock: no long-hold feature on kernel before… | `active_law` | `constitution` | long-hold-thesis |
| [LH-U1](#lh-u1) | Behavioral surface floor: no long-horizon key on behavioral… | `active_law` | `constitution` | long-hold-thesis |
| [LH-U10](#lh-u10) | Deferred: reverse-DCF / valuation expectations to W3; v1… | `deferred` | `lobe` | long-hold-thesis |
| [LH-U11](#lh-u11) | Cut: universe-scale KPI registry — blocked by SKIP-ALL paid… | `no_build` | `lobe` | long-hold-thesis |
| [LH-U12](#lh-u12) | 756d label kill: refused as headline; 504d also caveated | `killed` | `data_contract` | long-hold-thesis |
| [LH-U13](#lh-u13) | Deferred: 504/756d headline base rates pending dead-name… | `deferred` | `study` | long-hold-thesis |
| [LH-U14](#lh-u14) | G1-Retest deferred: W1 non-null gating W3/W4 projected… | `deferred` | `study` | long-hold-thesis |
| [LH-U2](#lh-u2) | Kill: Compounder Admission Test single verdict (fused… | `killed` | `signal_family` | long-hold-thesis |
| [LH-U3](#lh-u3) | Kill: kernel 12-36m outcome learning as forward loop | `killed` | `study` | long-hold-thesis |
| [LH-U4](#lh-u4) | Cut: theme-cashflow-transmission graph — no… | `no_build` | `lobe` | long-hold-thesis |
| [LH-U5](#lh-u5) | Cut: hold-book risk/overlap view — belongs to unchartered… | `no_build` | `lobe` | long-hold-thesis |
| [LH-U6](#lh-u6) | Cut: live qledger multi-year extension — GRADE_HORIZONS… | `no_build` | `data_contract` | long-hold-thesis |
| [LH-U7](#lh-u7) | G1 kill criterion: selection-alpha killed if no family… | `active_law` | `process` | long-hold-thesis |
| [LH-U8](#lh-u8) | W3/W4 locked: both waves locked pending G1-Retest non-null… | `blocked` | `wave` | long-hold-thesis |
| [LH-U9](#lh-u9) | Deferred: thesis ledger to W3 only; 'reason to hold'… | `deferred` | `lobe` | long-hold-thesis |
| [OVC-U1](#ovc-u1) | RO-2 compliance: all OVC columns must be raw fields; no… | `active_law` | `constitution` | options-alpha |
| [OVC-U10](#ovc-u10) | Kill: put/call OI ratio as predictor — sign-unstable across… | `killed` | `signal_family` | options-alpha |
| [OVC-U11](#ovc-u11) | Kill: directional/return use of vanna/charm states (F-21:… | `killed` | `signal_family` | options-alpha |
| [OVC-U12](#ovc-u12) | root_class column mandatory in W-OVC (formal column, not… | `active_law` | `data_contract` | options-alpha |
| [OVC-U15](#ovc-u15) | D1 (methodology defect): phantom ETF slice evidence from… | `killed` | `study` | options-alpha |
| [OVC-U16](#ovc-u16) | D4 ruling: calendar OPEX effects are dead in the modern era… | `active_law` | `constitution` | options-alpha |
| [OVC-U2](#ovc-u2) | RO-3: vanna-relief and OPEX states are caution-only; never… | `active_law` | `constitution` | options-alpha |
| [OVC-U3](#ovc-u3) | A10: S-VANNA-RELIEF gate currency limited to ledger… | `active_law` | `signal_family` | options-alpha |
| [OVC-U5](#ovc-u5) | FDR family enlarged from 22 to 28 tests by S-VANNA-RELIEF… | `active_law` | `constitution` | options-alpha |
| [OVC-U7](#ovc-u7) | NW display of OVC states: stamps must flow first;… | `active_law` | `lobe` | neural-web |
| [OVC-U8](#ovc-u8) | Kill: signed_charm_pressure (F-03) — vol proxy, not… | `killed` | `signal_family` | options-alpha |
| [OVC-U9](#ovc-u9) | Kill: 'total Greek depth is stabilizing' narrative… | `killed` | `context` | options-alpha |
| [RUL-OVC-1](#rul-ovc-1) | S-VANNA-RELIEF registered as… | `active_law` | `signal_family` | options-alpha |
| [RUL-OVC-2](#rul-ovc-2) | Greek intensity is a size/liquidity proxy; no bucket;… | `active_law` | `constitution` | options-alpha |
| [RUL-OVC-3](#rul-ovc-3) | Front-week charm/gamma concentration: display-only +… | `active_law` | `signal_family` | options-alpha |
| [RUL-OVC-4](#rul-ovc-4) | Family D (post-OPEX vol release): watch item only; no… | `deferred` | `study` | options-alpha |
| [RUL-OVC-5](#rul-ovc-5) | Family E (quad/OPEX calendar states): reject; is_quad_cycle… | `killed` | `signal_family` | options-alpha |
| [RUL-OVC-6](#rul-ovc-6) | Family F: pin real but NOT OPEX-specific; S-INDEX-PIN not… | `killed` | `signal_family` | options-alpha |
| [RUL-OVC-7](#rul-ovc-7) | Family G: display/shadow-first + path-based promotion… | `adopted` | `constitution` | options-alpha |
| [CPI-U1](#cpi-u1) | Append-only versioning: old truth lines are never mutated | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U10](#cpi-u10) | superseded truths excluded from active_truths() | `active_law` | `constitution` | cycle-intelligence |
| [CPI-U11](#cpi-u11) | scored gate rule: evidence_refs must contain a… | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U12](#cpi-u12) | Forbidden consumer list for null/structural truths | `active_law` | `constitution` | cycle-intelligence |
| [CPI-U13](#cpi-u13) | Pure numpy/pandas engine rule: no… | `active_law` | `process` | cycle-intelligence |
| [CPI-U14](#cpi-u14) | Bootstrap: month-block, 800 draws, seed=7 (ruling A2) | `active_law` | `process` | cycle-intelligence |
| [CPI-U15](#cpi-u15) | PIT discipline: any stamp is a pure function of tape <= t | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U16](#cpi-u16) | Backfill and live cohorts never blend in one badge | `active_law` | `process` | cycle-intelligence |
| [CPI-U18](#cpi-u18) | promoted_null truths displayed as honest null: still active… | `active_law` | `constitution` | cycle-intelligence |
| [CPI-U2](#cpi-u2) | Evidence-gated: all evidence_refs must exist on disk at… | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U20](#cpi-u20) | pit_class=revision_optimistic: macro/regime data without… | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U22](#cpi-u22) | effect_class null/structural: consumer restriction… | `active_law` | `constitution` | cycle-intelligence |
| [CPI-U3](#cpi-u3) | Falsifier-required: every truth must carry at least one… | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U4](#cpi-u4) | Status is the authority gate: null and retired truths… | `active_law` | `constitution` | cycle-intelligence |
| [CPI-U8](#cpi-u8) | forbidden_consumers must be non-empty for every truth | `active_law` | `data_contract` | cycle-intelligence |
| [CPI-U9](#cpi-u9) | Retired truths excluded from active_truths(): not active | `active_law` | `constitution` | cycle-intelligence |
| [CYC-FR-1](#cyc-fr-1) | Gate FR-1: false-repair classifier AUC ≥ 0.60 +… | `active_law` | `study` | cycle-intelligence |
| [CYC-U1](#cyc-u1) | Ownership split: Cycle owns; RF governs lifecycle; NW… | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U10](#cyc-u10) | Decay alarm: truth artifact auto-downgraded when live skill… | `active_law` | `process` | cycle-intelligence |
| [CYC-U11](#cyc-u11) | RF-6 hard gate: cycle_pattern trial-ledger entries declared… | `active_law` | `process` | cycle-intelligence |
| [CYC-U12](#cyc-u12) | CPI candidates in Research Factory; truths.jsonl is… | `active_law` | `process` | cycle-intelligence |
| [CYC-U13](#cyc-u13) | promoted_null truth blocks future duplicates; reopen only… | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U14](#cyc-u14) | Lattice estimator: partial pooling (James-Stein); FDR only… | `active_law` | `process` | cycle-intelligence |
| [CYC-U15](#cyc-u15) | FT-family gate law: features enter model only on gate pass;… | `active_law` | `process` | cycle-intelligence |
| [CYC-U17](#cyc-u17) | New FDR family cycle_pattern_ft (q=0.10) — one entry per FT… | `active_law` | `process` | cycle-intelligence |
| [CYC-U18](#cyc-u18) | New FDR family cycle_pattern_lattice (q=0.10); shrinkage… | `active_law` | `process` | cycle-intelligence |
| [CYC-U19](#cyc-u19) | Oracle rotation state promoted to Phase-1 context column… | `active_law` | `data_contract` | cycle-intelligence |
| [CYC-U2](#cyc-u2) | LLM role limit: compress/tag/adjudicate only; statistics is… | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U20](#cyc-u20) | Single-equity cycles deferred until sector-level C3/C4 hold… | `deferred` | `lobe` | cycle-intelligence |
| [CYC-U21](#cyc-u21) | DTW/shapelet analogues deferred until NN analogues… | `deferred` | `study` | cycle-intelligence |
| [CYC-U22](#cyc-u22) | Central-fuser disagreement models deferred until call… | `deferred` | `study` | cycle-intelligence |
| [CYC-U23](#cyc-u23) | Analogue engine is display-class only; no analogue output… | `active_law` | `lobe` | cycle-intelligence |
| [CYC-U24](#cyc-u24) | Regime-vintage spine (P-D5-1) scheduled in P4;… | `active_law` | `data_contract` | cycle-intelligence |
| [CYC-U26](#cyc-u26) | Hazard retro-scoring into monthly backfill labeled… | `no_build` | `study` | cycle-intelligence |
| [CYC-U28](#cyc-u28) | NW lobe: cycle_pattern_state.json; envelope-stamped; read… | `active_law` | `lobe` | neural-web |
| [CYC-U29](#cyc-u29) | KG-1 null law: position→return NO-EDGE; stand as seed truth | `active_law` | `study` | cycle-intelligence |
| [CYC-U3](#cyc-u3) | Phase 0 accrual hardening ships before any discovery code | `active_law` | `process` | cycle-intelligence |
| [CYC-U4](#cyc-u4) | Discovery priority: covariate-expansion (FT trials)… | `active_law` | `process` | cycle-intelligence |
| [CYC-U5](#cyc-u5) | Two-cohort discipline: BACKTEST never blends with LIVE | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U6](#cyc-u6) | Null truths are first-class; falsifiers mandatory;… | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U7](#cyc-u7) | Forbidden consumers: board rank, oracle escalation, central… | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U8](#cyc-u8) | Broad forward return from position stays excluded as a… | `active_law` | `constitution` | cycle-intelligence |
| [CYC-U9](#cyc-u9) | Live-cohort visual authority subordinated until n_eff ≥ 40 | `active_law` | `constitution` | cycle-intelligence |
| [CYC-IX-1](#cyc-ix-1) | Gate IX-1: index turn hazard model beats index's own… | `active_law` | `study` | cycle-intelligence |
| [CYC-TR-1](#cyc-tr-1) | Gate TR-1: next-phase model beats empirical transition… | `active_law` | `study` | cycle-intelligence |

## Rulings by Owner Program

### cycle-intelligence

### CPI-U1

**Append-only versioning: old truth lines are never mutated**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** A truth transition writes a NEW line with version+1; old lines are never mutated. Memory is permanent; authority is revocable. This makes the registry an immutable audit log.

**Scope fence:** Applies to all writes to data/cycle_pattern/truths.jsonl.

**Forbidden actions:**
  - mutate existing row
  - overwrite old version

**Source:** `config/cycle_pattern/truth_schema.md`
> A transition writes a NEW line (`version+1`); old lines are never mutated. Memory is permanent; authority is revocable.

*Owner program: cycle-intelligence*

### CPI-U10

**superseded truths excluded from active_truths()**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Truths with status 'superseded' are replaced by a newer truth and do not appear in active_truths(). The old truth remains in the append-only log for audit purposes.

**Scope fence:** Governs superseded-status truths.

**Forbidden actions:**
  - use superseded truth as current signal

**Source:** `config/cycle_pattern/truth_schema.md`
> | `superseded` | Replaced by a newer truth | **no** |

*Owner program: cycle-intelligence*

### CPI-U11

**scored gate rule: evidence_refs must contain a machine-readable verdict artifact**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** status='scored' requires at least one evidence_refs entry ending in .json, containing 'data/' in the path, and having one of 'verdict', 'gate', 'model', or 'calibration' in the filename. This ensures a machine-readable verdict artifact backs the claim.

**Scope fence:** Applies to any truth attempting scored status.

**Forbidden actions:**
  - set status=scored without machine-readable gate artifact
  - score truth with non-data/ evidence path

**Source:** `config/cycle_pattern/truth_schema.md`
> `status = "scored"` requires at least one entry in `evidence_refs` that: - ends in `.json` - contains `data/` in the path - has one of `verdict`, `gate`, `model`, `calibration` in the filename

*Owner program: cycle-intelligence*

### CPI-U12

**Forbidden consumer list for null/structural truths**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Null and structural truths must list board_rank, oracle_escalation, sector_central_direction_score, position_sizing, lead_lag_interaction_layer, ladder_calibration_input, and high_authority_truth_evidence in their forbidden_consumers. These surfaces may not cite null or structural truths.

**Scope fence:** Applies to all truths with effect_class=null or effect_class=structural.

**Forbidden actions:**
  - allow board_rank to cite null truth
  - allow oracle_escalation to cite null truth
  - allow position_sizing to cite null truth
  - allow ladder_calibration_input to cite structural truth
  - allow high_authority_truth_evidence to cite null truth

**Source:** `config/cycle_pattern/truth_schema.md`
> Forbidden (must appear in `forbidden_consumers` for null/structural truths): `board_rank`, `oracle_escalation`, `sector_central_direction_score`, `position_sizing`, `lead_lag_interaction_layer`, `ladder_calibration_input`, `high_authority_truth_evidence`

*Owner program: cycle-intelligence*

### CPI-U13

**Pure numpy/pandas engine rule: no sklearn/statsmodels/scipy.stats**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** All engine code in this module must use only numpy and pandas. The use of sklearn, statsmodels, and scipy.stats is forbidden in engine code. This is a standing house rule.

**Scope fence:** Applies to all code in engine/cycle_pattern/ and related engine modules.

**Forbidden actions:**
  - import sklearn in engine code
  - import statsmodels in engine code
  - import scipy.stats in engine code

**Source:** `config/cycle_pattern/truth_schema.md`
> - Pure `numpy`/`pandas` in all engine code — no `sklearn`/`statsmodels`/`scipy.stats`.

*Owner program: cycle-intelligence*

### CPI-U14

**Bootstrap: month-block, 800 draws, seed=7 (ruling A2)**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The bootstrap standard for this engine is month-block, 800 draws, with seed=7, implemented in engine/grading_stats.py. Wilson-on-raw-n is forbidden per ruling A2. Deviation from these parameters requires a new ruling.

**Scope fence:** Applies to all statistical grading in the cycle-intelligence engine.

**Forbidden actions:**
  - use Wilson-on-raw-n for confidence intervals
  - deviate from month-block bootstrap without new ruling
  - use seed other than 7 without new ruling

**Source:** `config/cycle_pattern/truth_schema.md`
> - Bootstrap: month-block, 800 draws, seed=7 (`engine/grading_stats.py`). - Wilson-on-raw-n is forbidden (ruling A2).

*Owner program: cycle-intelligence*

### CPI-U15

**PIT discipline: any stamp is a pure function of tape <= t**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** Point-in-time discipline requires that any stamp (feature, label, or score) is a pure function of tape at or before time t. No forward-looking data may contaminate any PIT stamp. Revision-optimistic or mixed PIT class must be declared explicitly in pit_class.

**Scope fence:** Applies to all truth records and engine computations.

**Forbidden actions:**
  - use forward-looking data in PIT stamp
  - silently use revised macro data without declaring revision_optimistic pit_class

**Source:** `config/cycle_pattern/truth_schema.md`
> - PIT discipline: any stamp is a pure function of tape ≤ t.

*Owner program: cycle-intelligence*

### CPI-U16

**Backfill and live cohorts never blend in one badge**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Backfill cohort results and live cohort results must not be blended into a single badge or display. Each must be separately attributed. Blending violates the honesty standard of the registry.

**Scope fence:** Applies to all display surfaces citing truths from this registry.

**Forbidden actions:**
  - blend backfill and live cohorts in single badge
  - display combined backfill+live statistic without separation

**Source:** `config/cycle_pattern/truth_schema.md`
> - Backfill and live cohorts never blend in one badge.

*Owner program: cycle-intelligence*

### CPI-U18

**promoted_null truths displayed as honest null: still active in active_truths()**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** promoted_null status means the truth has been adjudicated null and is actively displayed as an honest null. Unlike retired, promoted_null truths DO appear in active_truths(). (Note: the forbidden_consumers fence in the doc is keyed to effect_class null/structural, not to promoted_null status per se.)

**Scope fence:** Applies to truths adjudicated as null: they remain active as honest-null displays.

**Forbidden actions:**
  - hide promoted_null from display
  - treat promoted_null as retired

**Source:** `config/cycle_pattern/truth_schema.md`
> | `promoted_null` | Adjudicated null; actively displayed as honest null | yes |

*Owner program: cycle-intelligence*

### CPI-U2

**Evidence-gated: all evidence_refs must exist on disk at validation time**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** All evidence_refs entries must point to files that exist on disk at validation time. The validate_truth() API enforces this via check_refs_exist=True by default. Truths with broken refs are rejected.

**Scope fence:** Applies to all truth records at validation time.

**Forbidden actions:**
  - accept truth with missing evidence_refs
  - bypass ref existence check

**Source:** `config/cycle_pattern/truth_schema.md`
> **Evidence-gated.** All `evidence_refs` must point to files that exist on disk at validation time.

*Owner program: cycle-intelligence*

### CPI-U20

**pit_class=revision_optimistic: macro/regime data without ALFRED vintages**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** revision_optimistic pit_class declares that some features use revised macro or regime data without ALFRED vintages, per cross-reference P-D5-1. This must be explicitly declared; silent use of revised data is a PIT violation.

**Scope fence:** Applies to any truth whose features include revised macro/regime data.

**Forbidden actions:**
  - silently use revised macro data without declaring revision_optimistic

**Source:** `config/cycle_pattern/truth_schema.md`
> | `revision_optimistic` | Some features use revised macro/regime data without ALFRED vintages (P-D5-1) |

*Owner program: cycle-intelligence*

### CPI-U22

**effect_class null/structural: consumer restriction enforcement via forbidden_consumers**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Truths with effect_class of null or structural must have the full set of positive-consumer surfaces in forbidden_consumers. The registry design principle is that null evidence must not feed ranking, escalation, or sizing decisions even if technically valid via active_truths().

**Scope fence:** Applies to all truths with effect_class=null or effect_class=structural.

**Forbidden actions:**
  - allow null-class truth to feed board_rank
  - allow structural-class truth to feed position_sizing
  - allow null-class truth to feed oracle_escalation

**Source:** `config/cycle_pattern/truth_schema.md`
> Forbidden (must appear in `forbidden_consumers` for null/structural truths): `board_rank`, `oracle_escalation`, `sector_central_direction_score`, `position_sizing`, `lead_lag_interaction_layer`, `ladder_calibration_input`, `high_authority_truth_evidence`

*Owner program: cycle-intelligence*

### CPI-U3

**Falsifier-required: every truth must carry at least one concrete falsifier**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** Every truth must carry at least one concrete falsifier. Unfalsifiable claims are not accepted. The schema enforces min 1 entry in the falsifiers list field.

**Scope fence:** Applies to all truth records submitted to the registry.

**Forbidden actions:**
  - register unfalsifiable claim
  - submit truth with empty falsifiers list

**Source:** `config/cycle_pattern/truth_schema.md`
> **Falsifier-required.** Every truth must carry at least one concrete falsifier; unfalsifiable claims are not accepted.

*Owner program: cycle-intelligence*

### CPI-U4

**Status is the authority gate: null and retired truths cannot feed positive consumers**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** promoted_null and retired truths are excluded from active_truths(). scored status requires a gate artifact in evidence_refs. This is the primary mechanism preventing null/retired signals from feeding positive downstream consumers.

**Scope fence:** Governs all consumer access via active_truths() API.

**Forbidden actions:**
  - serve promoted_null truth to positive consumer
  - serve retired truth to active pipeline
  - mark scored without gate artifact

**Source:** `config/cycle_pattern/truth_schema.md`
> **Status is the authority gate.** `promoted_null` and `retired` truths are excluded from `active_truths()`; `scored` requires a gate artifact in `evidence_refs`.

*Owner program: cycle-intelligence*

### CPI-U8

**forbidden_consumers must be non-empty for every truth**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** The forbidden_consumers list is required and must be non-empty. Every truth must explicitly declare at least one surface that is barred from citing it. This prevents truths from having unconstrained consumer access.

**Scope fence:** Applies to all truth records.

**Forbidden actions:**
  - submit truth with empty forbidden_consumers list

**Source:** `config/cycle_pattern/truth_schema.md`
> | `forbidden_consumers` | list[str] | yes | Surfaces explicitly barred. Must be non-empty. |

*Owner program: cycle-intelligence*

### CPI-U9

**Retired truths excluded from active_truths(): not active**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Truths with status 'retired' are no longer active; memory is preserved but they do not appear in active_truths(). They cannot be served to any pipeline consumer via the standard API.

**Scope fence:** Governs retired-status truths; they remain in the log but are excluded from active queries.

**Forbidden actions:**
  - serve retired truth as active signal
  - reinstate retired truth without new append

**Source:** `config/cycle_pattern/truth_schema.md`
> | `retired` | No longer active; memory preserved | **no** |

*Owner program: cycle-intelligence*

### CYC-FR-1

**Gate FR-1: false-repair classifier AUC ≥ 0.60 + calibrated-Brier beats base with CI**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** FR-1 is a new preregistered gate requiring the false-repair classifier to achieve AUC ≥ 0.60 and calibrated-Brier beating base with CI. Era-split and embargo [2024-01-01, end] are honored. Gate must be declared in PREREGISTRATION.md as an append-only amendment before P3 runs.

**Forbidden actions:**
  - shipping false-repair classifier without FR-1 gate pass

**Unblock condition:** Preregistration amendment appended; P4 model trial run

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> FR-1 (false-repair classifier AUC ≥ 0.60 + calibrated-Brier beats base with CI),

*Owner program: cycle-intelligence*

### CYC-U1

**Ownership split: Cycle owns; RF governs lifecycle; NW consumes; Oracle downstream**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Cycle-pattern intelligence is Cycle-owned. Research Factory owns the candidate lifecycle (no parallel ladder). Neural Web consumes a compact lobe. Oracle is downstream context-only, not a co-owner. LLMs compress, tag, and adjudicate packets; statistics is the court.

**Scope fence:** Oracle may only receive context from cycle-pattern, never escalate or score from it.

**Forbidden actions:**
  - parallel candidate ladder outside Research Factory
  - Oracle originating cycle escalations

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> Ownership as Codex ruled, confirmed: **Cycle-owned; Research Factory owns candidate lifecycle; Neural Web consumes a compact lobe; Oracle is downstream context-only.**

*Owner program: cycle-intelligence*

### CYC-U10

**Decay alarm: truth artifact auto-downgraded when live skill drifts below backtest envelope**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** A rolling live Brier/coverage ledger per family must be maintained for every probability the platform ships (hazard cells, future transition models). A CUSUM-style decay alarm auto-downgrades a truth artifact's status when live skill drifts below its backtest envelope. Decay must be detected by machinery, not by quarterly vibes.

**Forbidden actions:**
  - manually deciding decay by periodic review instead of machinery

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> Decay must be detected by machinery, not by quarterly vibes.

*Owner program: cycle-intelligence*

### CYC-U11

**RF-6 hard gate: cycle_pattern trial-ledger entries declared before first screened candidate**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** CPI candidates must register as domain `cycle_pattern` in the Research Factory. Trial-ledger entries for `rf.cycle_pattern.*` must be declared in data/trial_ledger.jsonl BEFORE the first screened candidate. This is the RF-6 hard gate and is enforced by the factory's IllegalTransition mechanism.

**Forbidden actions:**
  - screening a cycle_pattern candidate before its trial-ledger entry exists

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> declare `rf.cycle_pattern.*` in `data/trial_ledger.jsonl` **before** first screened candidate (RF-6 hard gate)

*Owner program: cycle-intelligence*

### CYC-U12

**CPI candidates in Research Factory; truths.jsonl is separate downstream artifact layer**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** CPI candidates use the Research Factory 15-state machine (no parallel promotion ladder). The CPI promotion ladder maps onto factory states. truths.jsonl is a separate, downstream artifact layer — the adjudicated output memory, written only from human_review/paper decisions and existing verdict docs, never a competing pipeline.

**Forbidden actions:**
  - building a parallel CPI promotion ladder outside Research Factory
  - writing to truths.jsonl from automated pipelines

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **CPI candidates register as domain `cycle_pattern` in the factory; the CPI "promotion ladder" maps onto factory states; `truths.jsonl` is a *separate, downstream* artifact layer** — the adjudicated output memory, written only from human_review/paper decisions and existing verdict docs, never a competing pipeline.

*Owner program: cycle-intelligence*

### CYC-U13

**promoted_null truth blocks future duplicates; reopen only via new preregistered trial**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** A promoted_null truth semantics live in the truth layer (factory has no durable-null state). A null truth blocks future duplicate candidates via the factory's dedup context. A promoted_null truth may be reopened only by a new preregistered trial explicitly naming the null it challenges. Dead stays dead otherwise.

**Forbidden actions:**
  - reopening a promoted_null without a new preregistered trial naming it
  - duplicating a null-blocked candidate

**Unblock condition:** New preregistered trial explicitly naming the null it challenges

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> a `promoted_null` truth may be reopened only by a new preregistered trial naming the null it challenges (dead stays dead otherwise).

*Owner program: cycle-intelligence*

### CYC-U14

**Lattice estimator: partial pooling (James-Stein); FDR only at promotion not exploration**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The default estimator for any lattice cell family is partial pooling (James-Stein toward the phase/family pooled mean, with n_eff on month-blocks). BH-FDR is applied only at promotion, not at exploration. Weak evidence accumulates in shrunken posteriors; authority still requires the frozen gates.

**Forbidden actions:**
  - applying BH-FDR at exploration stage for lattice cells
  - using cell-independent scans as default lattice estimator

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> The default estimator for any cell family is **partial pooling** (James-Stein toward the phase/family pooled mean, exactly the D5 §2.2 machinery, n_eff on month-blocks) with FDR applied only at **promotion**, not at exploration.

*Owner program: cycle-intelligence*

### CYC-U15

**FT-family gate law: features enter model only on gate pass; failures = truth artifacts**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Each FT family is one trial-ledger entry with a declared candidate count. Features enter the shipped model only on gate pass. Failures are recorded as truth artifacts with effect_class: null, scoped to the family. The baseline for each trial is always the current shipped model, not the KM prior.

**Forbidden actions:**
  - entering features into the shipped model without passing the gate
  - using KM prior (not current model) as baseline for FT trials

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> each FT family is ONE trial-ledger entry with a declared candidate count; features enter the shipped model only on gate pass; failures are recorded as truth artifacts (`effect_class: null`, scoped to the family).

*Owner program: cycle-intelligence*

### CYC-U17

**New FDR family cycle_pattern_ft (q=0.10) — one entry per FT family, candidate counts declared**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** A new FDR family cycle_pattern_ft with q=0.10 is preregistered. FT-1 through FT-7 each get one trial-ledger entry with candidate counts declared before evaluation. BH-FDR governs promotion within this family.

**Forbidden actions:**
  - running FT trials without a declared trial-ledger entry per family

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> New FDR family `cycle_pattern_ft` (q=0.10) — FT-1..FT-7, one entry per family, candidate counts declared.

*Owner program: cycle-intelligence*

### CYC-U18

**New FDR family cycle_pattern_lattice (q=0.10); shrinkage exploration exempt; promotion subject to FDR**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** A new FDR family cycle_pattern_lattice with q=0.10 is preregistered, budgeted per candidate_grammar.yml. Shrinkage exploration is exempt from FDR. Promotion is subject to FDR. This distinction must be written into the ledger text.

**Forbidden actions:**
  - applying FDR at exploration stage for lattice candidates
  - promoting lattice candidates without FDR gate

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> New FDR family `cycle_pattern_lattice` (q=0.10) — budgeted per `candidate_grammar.yml`; shrinkage exploration exempt from FDR, **promotion** subject to it (this distinction written into the ledger text).

*Owner program: cycle-intelligence*

### CYC-U19

**Oracle rotation state promoted to Phase-1 context column with pit_class=reconstructed**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Oracle rotation state is promoted from 'maybe someday' to a Phase-1 context column with pit_class=reconstructed. It is reconstructable point-in-time from the episode archive (6,402 episodes, 1999 onward, with onset/confirmed/exhausted dates).

**Scope fence:** Oracle state in cycle_pattern lake is context only (pit_class=reconstructed); not a predictive feature until separately gated.

**Forbidden actions:**
  - using oracle rotation state as a predictive feature before gating

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **Oracle rotation state as context**: Codex said "only where point-in-time" — recon shows it is *reconstructable* point-in-time from the episode archive (6,402 episodes, 1999→, onset/confirmed/exhausted dates). Promote from "maybe someday" to a Phase-1 context column with `pit_class=reconstructed`.

*Owner program: cycle-intelligence*

### CYC-U2

**LLM role limit: compress/tag/adjudicate only; statistics is the court**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** LLMs may compress, tag, and adjudicate packets. Statistics is the court; the preregistration ledger stays frozen. LLMs may not originate scores, signals, or escalations in the cycle-pattern system.

**Scope fence:** LLM-originated scores are constitutionally forbidden.

**Forbidden actions:**
  - LLM originating a score
  - LLM originating a signal
  - LLM originating an escalation

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> LLMs compress, tag, and adjudicate packets; statistics is the court; the preregistration ledger stays frozen.

*Owner program: cycle-intelligence*

### CYC-U20

**Single-equity cycles deferred until sector-level C3/C4 hold live 2+ quarters**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Single-equity cycles are explicitly deferred due to sample explosion and noise. They may only be revisited after sector-level C3 (turn prediction) and C4 (what-comes-next) capabilities hold live for 2 or more quarters. The Terminal's per-stock confluence stack is a different organism.

**Scope fence:** No single-equity cycle modeling until sector-level C3/C4 proven live for 2+ quarters.

**Forbidden actions:**
  - building single-equity cycle models before sector-level C3/C4 are proven

**Unblock condition:** Sector-level C3 (turn prediction) and C4 (what-comes-next) both hold live for 2+ quarters

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **Single-equity cycles** — sample explosion + noise; revisit only after sector-level C3/C4 hold live for 2+ quarters. The Terminal's per-stock confluence stack is a different organism.

*Owner program: cycle-intelligence*

### CYC-U21

**DTW/shapelet analogues deferred until NN analogues demonstrate consumption**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** DTW and shapelet-based analogues are deferred. They may only be built if nearest-neighbor (NN) analogues demonstrate consumption, meaning a display-class feature that nobody opens is not worth a fancier metric.

**Forbidden actions:**
  - building DTW or shapelet analogues before NN analogues are consumed

**Unblock condition:** NN analogues demonstrate consumption by users

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **DTW/shapelet analogues** — after NN proves consumed.

*Owner program: cycle-intelligence*

### CYC-U22

**Central-fuser disagreement models deferred until call ledgers mature (n_eff ≥ 40)**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** Central-fuser disagreement outcome models are deferred — call ledgers have only 5 unique dates and building them now is theater. They become trainable when the ledger matures. The accrual clock will display when n_eff ≥ 40.

**Forbidden actions:**
  - building central-fuser disagreement models before call ledger n_eff ≥ 40

**Unblock condition:** Central call ledger n_eff ≥ 40

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **"Central fuser disagreement outcome" as a near-term model family** — the central call ledgers have 5 unique dates. It stays a *target definition* in the outcomes spine and becomes trainable when the ledger matures (accrual clock says when). Building it now is theater.

*Owner program: cycle-intelligence*

### CYC-U23

**Analogue engine is display-class only; no analogue output can touch a score**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Analogue/episode cards are display-class; no analogue output may touch a score. Every analogue card must show n, dates, era stability, and caveats. LLM-normalized narrative/DNA tags on episodes are display metadata, not features, until separately gated.

**Scope fence:** Analogue engine: display-class only; no score consumption permitted.

**Forbidden actions:**
  - using analogue output in any scoring system
  - using LLM episode tags as model features before separate gating

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> no analogue output can touch a score.

*Owner program: cycle-intelligence*

### CYC-U24

**Regime-vintage spine (P-D5-1) scheduled in P4; regime_v2_pit re-keys 39 revision-optimistic cells**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The regime-vintage spine (P-D5-1) is a Phase-4 long pole that must be started early. Market-price-only regime axes are PIT-pure by construction. The 26-series vintage store covers macro legs. A regime_v2_pit series re-keys the 39 revision-optimistic conditional cells from W4.4 into honest candidates.

**Scope fence:** 39 revision-optimistic cells from W4.4 are invalid as-is; must not be promoted without regime_v2_pit re-keying.

**Forbidden actions:**
  - promoting W4.4 revision-optimistic cells without regime_v2_pit re-keying

**Unblock condition:** regime_v2_pit spine built in P4

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **The regime-vintage spine (P-D5-1) is scheduled, not lamented:** market-price-only regime axes are PIT-pure by construction; the 26-series vintage store covers the macro legs of the business-cycle model; a `regime_v2_pit` series re-keys the 39 revision-optimistic conditional cells (W4.4) into honest candidates.

*Owner program: cycle-intelligence*

### CYC-U26

**Hazard retro-scoring into monthly backfill labeled in-sample-contaminated pre-2024**

- Status: `no_build` | Kind: `study` | Nondelegable: `False`

**Ruling:** Retro-scoring the fitted hazard model over 2010–2026 stamps (back-propagating a 2026-fit model) is a preregistered exercise and must be labeled in-sample-contaminated for any pre-2024 row. It is not lake plumbing and is rejected from v0.

**Scope fence:** Hazard retro-scores pre-2024 must carry in-sample-contaminated label; not part of lake plumbing.

**Forbidden actions:**
  - treating retro-scored hazard values as PIT-pure features
  - including retro-scores in v0 lake without contamination label

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **Hazard columns retro-scored into the monthly backfill in v0** — retro-scoring the fitted model over 2010–2026 stamps is a *preregistered* exercise (it back-propagates a 2026-fit model into history and must be labeled in-sample-contaminated for any pre-2024 row); it is not lake plumbing.

*Owner program: cycle-intelligence*

### CYC-U29

**KG-1 null law: position→return NO-EDGE; stand as seed truth**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** position→return is a standing null for cycle state prediction (KG-1 verdict). This null is seeded into truths.jsonl and the system boots knowing not to believe it. BC-1 confirmed risk-sizing 0/48 cells. These nulls are first-class outputs of the system.

**Forbidden actions:**
  - re-testing position→return edge without a new preregistered trial naming KG-1

**Unblock condition:** New preregistered trial explicitly naming KG-1 null it challenges

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> position→return NO-EDGE (KG-1), ladder inversion inconclusive (KG-3), risk-sizing 0/48 cells (BC-1), lead-lag NO-GO (LL-B)

*Owner program: cycle-intelligence*

### CYC-U3

**Phase 0 accrual hardening ships before any discovery code**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Phase 0 (accrual hardening) must ship before any discovery code. Every un-stamped day is training data lost forever. The accrual fixes include: CN hazard stamping fix, measurement.py wired into daily/render lanes, nightly context archive, nightly sync gauge append.

**Forbidden actions:**
  - deploying discovery code before accrual hardening

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> Every un-stamped day is training data lost forever. **Phase 0 of this plan is accrual hardening, and it ships before any discovery code.**

*Owner program: cycle-intelligence*

### CYC-U4

**Discovery priority: covariate-expansion (FT trials) outranks lattice mining**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** CPI's discovery program must be first a covariate-expansion program (preregistered FT-family trials asking whether joining X lifts OOS Brier), and only second a lattice-mining program. Priority order: FT-families → lattice-with-shrinkage → supervised risk models → motif/analogue (display-class) → association rules last.

**Forbidden actions:**
  - prioritizing lattice mining over covariate-expansion trials

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **CPI's discovery program must be, first, a covariate-expansion program** — preregistered trials asking "does joining X lift out-of-sample Brier on the turn/risk targets?" — and only second a lattice-mining program.

*Owner program: cycle-intelligence*

### CYC-U5

**Two-cohort discipline: BACKTEST never blends with LIVE**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Two-cohort discipline is mandatory and must not be changed: BACKTEST never blends with LIVE. Frozen preregistered criteria, BH-FDR within families, family-stratified KM baselines, and month-block bootstrap are all adopted as-is. The temptation to fix measurement because grades are bad must be refused — the grades are the finding.

**Forbidden actions:**
  - blending BACKTEST with LIVE cohorts
  - changing measurement methodology because results are bad

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> Two-cohort discipline (BACKTEST never blends with LIVE), frozen preregistered criteria, BH-FDR within families, family-stratified KM baselines, month-block bootstrap, the honest display of falsified promises.

*Owner program: cycle-intelligence*

### CYC-U6

**Null truths are first-class; falsifiers mandatory; dead-stays-dead anti-mining law**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Truth artifacts are permanent memory with revocable authority; nulls are first-class outputs, not failures to hide. Falsifiers are mandatory. The anti-mining law requires: trial budgets, printed candidate counts, null baselines, date-blocked holdouts, era splits, sample floors, duplicate collapse, and dead-stays-dead enforcement.

**Forbidden actions:**
  - hiding nulls
  - reviving dead findings without new preregistered trial
  - running candidates without declared budget

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> - Truth artifacts = permanent memory with revocable authority; nulls are first-class; falsifiers mandatory. - Anti-mining law (trial budgets, printed candidate counts, null baselines, date-blocked holdouts, era splits, sample floors, duplicate collapse, dead-stays-dead).

*Owner program: cycle-intelligence*

### CYC-U7

**Forbidden consumers: board rank, oracle escalation, central direction score, position sizing**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Reads of data/cycle_pattern/ from forbidden consumers are a CI failure, not merely a documentation sentence. Forbidden consumers are: board rank, oracle escalation, central direction score, and position sizing. The authority check gate (check_cycle_pattern_authority.py) enforces this.

**Scope fence:** cycle_pattern data is display/infrastructure tier; no ranked-output, no position-sizing consumer.

**Forbidden actions:**
  - board rank consuming cycle_pattern data
  - oracle escalation consuming cycle_pattern data
  - central direction score consuming cycle_pattern data
  - position sizing consuming cycle_pattern data

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> forbidden consumers (board rank, oracle escalation, central direction score, position sizing) become a CI failure, not a doc sentence.

*Owner program: cycle-intelligence*

### CYC-U8

**Broad forward return from position stays excluded as a prediction target**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No target may be 'forward absolute return from cycle state alone' — this is a standing null. Risk/event targets over raw-return targets are adopted. The exclusion is permanent unless overturned by a preregistered trial.

**Forbidden actions:**
  - using broad forward return from position as a prediction target

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> - Risk/event targets over raw-return targets; "broad forward return from position" stays excluded.

*Owner program: cycle-intelligence*

### CYC-U9

**Live-cohort visual authority subordinated until n_eff ≥ 40**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Live-cohort visual authority must stay subordinated until n_eff reaches 40, per the house floor. Central-call grading targets activate automatically when ledgers hit n_eff ≥ 40 (accrual clock displays the date).

**Scope fence:** Live cohort results display only; no authority elevation until n_eff ≥ 40.

**Forbidden actions:**
  - granting authority to live-cohort output before n_eff reaches 40

**Unblock condition:** n_eff ≥ 40 in the relevant ledger

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> **Live-cohort visual authority** must stay subordinated until n_eff ≥ 40 per the house floor (Codex is right).

*Owner program: cycle-intelligence*

### CYC-IX-1

**Gate IX-1: index turn hazard model beats index's own age-only KM**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** IX-1 is a new preregistered gate requiring the index turn hazard model (market-level SPY/country index with constituent-structure covariates from FT-4) to beat the index's own age-only KM baseline. Era-split and embargo [2024-01-01, end] are honored. This is the C5 capability gate.

**Forbidden actions:**
  - shipping index turn hazard model without IX-1 gate pass

**Unblock condition:** Preregistration amendment appended; P4 model trial run; FT-4 pass

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> IX-1 (index hazard beats index KM), each with era-split and embargo [2024-01-01, end] honored.

*Owner program: cycle-intelligence*

### CYC-TR-1

**Gate TR-1: next-phase model beats empirical transition matrix (OOS multiclass Brier)**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** TR-1 is a new preregistered gate requiring the next-phase transition model to beat the empirical transition matrix baseline on OOS multiclass Brier with CI excluding zero. Era-split and embargo [2024-01-01, end] are honored. Gate must be declared in PREREGISTRATION.md as an append-only amendment before P3 runs.

**Forbidden actions:**
  - shipping next-phase model without TR-1 gate pass

**Unblock condition:** Preregistration amendment appended; P4 model trial run

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> TR-1 (next-phase model beats empirical transition matrix, OOS multiclass Brier, CI excludes 0),

*Owner program: cycle-intelligence*


### dannytrades

### DT-R1

**Docket disposition: Codex build plan not adopted; no new charter**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The Codex docket is accepted as narrative synthesis and committed as-received. Its build plan is not adopted. No new DannyTrades engine, lobe, or artifact family is chartered. The useful residue ships as two small display-only builds and three routings.

**Scope fence:** Display-only; no new engine, lobe, or artifact family may be chartered under the DannyTrades namespace.

**Forbidden actions:**
  - charter new DannyTrades engine
  - charter new DannyTrades lobe
  - charter new DannyTrades artifact family

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Its build plan is not adopted. **No new DannyTrades engine, lobe, or artifact family is chartered.**

*Owner program: dannytrades*

### DT-R11a

**DannyTrades-derived numbers are display-only; 'validated' restricted**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Any DannyTrades-derived number is display-only; the word 'validated' only per BC-2 allowlist. This is a standing architecture constraint.

**Scope fence:** Display-only; 'validated' word restricted to BC-2 allowlist.

**Forbidden actions:**
  - use DannyTrades-derived number as ranked output
  - print 'validated' outside BC-2 allowlist

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R11 (architecture constraints).** (a) Any DannyTrades-derived number is display-only; the word "validated" only per BC-2 allowlist.

*Owner program: dannytrades*

### DT-R11b

**Danny composite must never blend into momentum ranker**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The measured momentum-dilution result (danny composite negatively correlated with 12-1 momentum; blending drops mom IC 0.031 to 0.005) is a standing constraint: the composite must never be blended into any momentum ranker. It lives on the caution/extension side only.

**Scope fence:** Danny composite restricted to caution/extension side; never blended into momentum ranker.

**Forbidden actions:**
  - blend danny composite into momentum ranker
  - use danny composite as momentum factor

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> composite must never be blended into any momentum ranker — it lives on the caution/extension side only.

*Owner program: dannytrades*

### DT-R12

**data/massive_stock_day/ is sole sanctioned volume substrate; no pre-2021 claims**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** data/massive_stock_day/ (2021-07-06+, ~19k tickers, store-host/R2 only) is the ONLY sanctioned volume substrate for DannyTrades-family studies. No pre-2021 volume claims. All DT studies carry era-law framing and survivorship/coverage stamps. The phase-0's 1962-2026 yfinance cache was a temporary local artifact and is not citable as a store.

**Scope fence:** Volume substrate for DT studies restricted to massive_stock_day/ (2021-07-06+).

**Forbidden actions:**
  - cite yfinance cache as volume store
  - use pre-2021 volume data for DT claims
  - make volume claims without era-law framing

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R12 (data substrate law).** `data/massive_stock_day/` (2021-07-06+, ~19k tickers, store-host/R2 only) is the ONLY sanctioned volume substrate for DannyTrades-family studies.

*Owner program: dannytrades*

### DT-R13

**Whale directional restoration path: requires month-block time control on 64y panel**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Whale-based directional claims may return only via a new prereg in which the 64-year panel survives month-block time control. Until then, any citation of the t~=-3.9 whale-change result must carry 'computed without time control' alongside the survivorship caveat.

**Forbidden actions:**
  - cite whale-change t=-3.9 without time-control caveat
  - originate directional whale claim without new prereg on 64y panel with month-block time control

**Unblock condition:** New prereg where 64-year panel survives month-block time control.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R13 (restoration path).** Whale-based directional claims may return only via a new prereg in which the 64-year panel survives month-block time control.

*Owner program: dannytrades*

### DT-R14

**Time-control law: calendar-time control mandatory in primary inference**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Every future DannyTrades-family study — and any monthly/level-threshold event study on a regime-limited panel — must include a calendar-time control in its PRIMARY inference (within-month demeaning or month-block resampling) and a control design matched to the test type (time-permutation for change tests, cross-sectional permutation for level tests). Future preregs must pre-declare a DEFERRED/UNDERPOWERED verdict path so a low-power null is distinguishable from a refutation.

**Forbidden actions:**
  - run monthly/level-threshold event study without calendar-time control
  - treat low-power null as refutation without DEFERRED/UNDERPOWERED path in prereg

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R14 (time-control law).** Every future DannyTrades-family study — and any monthly/level-threshold event study on a regime-limited panel — must include a calendar-time control in its PRIMARY inference

*Owner program: dannytrades*

### DT-R15

**Whale family closed: restoration denied; pooled significance insufficient**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** The DT-R13 restoration path is closed. Pooled significance carried by dead eras does not restore a live directional surface. Re-opening requires the effect to clear CI-excludes-zero WITHIN the modern era on a survivorship-honest panel. No clock is set; nothing accrues toward this automatically.

**Forbidden actions:**
  - cite pooled significance as restoring whale directional claims
  - accrue toward whale restoration without modern-era CI-excludes-zero on honest panel

**Unblock condition:** Effect must clear CI-excludes-zero WITHIN modern era on survivorship-honest panel; no clock set.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R15 (restoration DENIED; whale family CLOSED).** Pooled significance carried by dead eras does not restore a live directional surface.

*Owner program: dannytrades*

### DT-R16

**Era-split disclosure law: pooled pass must show modern-era row**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Any multi-decade pooled verdict in this family — and any future restoration attempt — must print an era-split table alongside the pooled statistic; 'SURVIVES (pooled)' may not appear without the modern-era row. A pooled pass on a 60-year panel is a regime-coverage claim, and the claim must show its coverage.

**Forbidden actions:**
  - print SURVIVES (pooled) without modern-era era-split row
  - report multi-decade verdict without era-split table

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R16 (era-split disclosure law).** Any multi-decade pooled verdict in this family — and any future restoration attempt — must print an era-split table alongside the pooled statistic

*Owner program: dannytrades*

### DT-R2

**No-chase engine killed as duplicate; invalid_if_below rejected**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** engine/extension_no_chase.py and its builder/parquet/JSON are KILLED as duplicates (SLF-010 precedent). The legal gap is a thin consolidation surface only, delegated to DT-NW-1. invalid_if_below is rejected as a laundered stop-loss; nearest_support belongs to the price-memory bundle (DT-R7). no_chase_age belongs to the EI program, not to a DannyTrades artifact.

**Forbidden actions:**
  - build extension_no_chase.py
  - use invalid_if_below as display key
  - use nearest_support in DannyTrades artifact

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R2 (no-chase engine).** `engine/extension_no_chase.py` and its builder / parquet / JSON are KILLED as duplicates

*Owner program: dannytrades*

### DT-R3

**Sponsorship ensemble illegal under Signal Commons R3**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** sponsorship_pressure_proxy as an ensemble is the exact fused-escalating-composite shape Signal Commons R3 forbids. Its ingredients are independently dead or fenced: CMF/OBV/volume confirmers killed, ETF-flow alpha killed, signed options flow forbidden (RO-9), 13F context-only. sponsorship_decay, retail_chase_proxy, and sponsorship_uncertainty are not chartered.

**Forbidden actions:**
  - build sponsorship_pressure_proxy ensemble
  - build retail_chase_proxy
  - build sponsorship_decay signal
  - build sponsorship_uncertainty

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R3 (sponsorship ensemble).** `sponsorship_pressure_proxy` as an ensemble is the exact fused-escalating-composite shape Signal Commons R3 forbids.

*Owner program: dannytrades*

### DT-U1

**Chip now purely descriptive: all directional claims retired after H4 failure**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** H4 failed on both panels (DT-W1a and DT-W2), so ALL directional tilt claims are retired: engine/dannytrades_chip.py is now a descriptive positioning readout (extension percentile + accumulation level; state permanently 'neutral'; enum kept for dt_contra_state.json schema stability). The DT-NW-1 synapse artifact inherits the caveat via its single-source import.

**Scope fence:** Chip is descriptive positioning readout only; state permanently neutral; no directional tilt.

**Forbidden actions:**
  - restore directional tilt to chip without new prereg clearing DT-R15
  - print 'Validated' in chip caveat

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> now a descriptive positioning readout (extension percentile + accumulation level; state permanently "neutral"; enum kept for `dt_contra_state.json` schema stability).

*Owner program: dannytrades*


### dannytrades-adjudication

### DT-U5

**concentration/leader-book idea routed to Mastermind repo (out-of-repo)**

- Status: `no_build` | Kind: `process` | Nondelegable: `False`

**Ruling:** The portfolio-level concentration/leader-book idea is routed to the Mastermind repo (portfolio construction is out-of-repo by charter). Context note only; no clock.

**Scope fence:** Portfolio construction is out-of-repo; concentration/leader-book may not be built in this repo.

**Forbidden actions:**
  - build concentration-level portfolio construction in main repo

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> The portfolio-level concentration/leader-book idea is routed to the Mastermind repo (portfolio construction is out-of-repo by charter).

*Owner program: dannytrades-adjudication*


### entry-intelligence

### NEXTL-U20

**rs_repair_state is an explicit stub; owned by entry-intelligence #1302 W0.4**

- Status: `deferred` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** rs_repair_state is an explicit stub (bottom_sensors.py:622-623), owned by entry-intelligence program #1302 W0.4. It is documented here but not fixed. This program does not build the stub resolution.

**Forbidden actions:**
  - fix rs_repair_state stub in this program

**Unblock condition:** entry-intelligence #1302 W0.4 ships rs_repair_state

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **`rs_repair_state`** is an explicit stub (`bottom_sensors.py:622-623`), owned by entry-intelligence #1302 W0.4. Documented, not fixed, here.

*Owner program: entry-intelligence*

### DT-R7

**DCA policy object killed; price-memory bundle dispatched to EI program**

- Status: `residue_adopted` | Kind: `study` | Nondelegable: `True`

**Ruling:** The DCA policy object is KILLED: max_add, no_chase_above, invalid_if are trade instructions (authority smuggling), and the anchor's pullback/DCA-adjacent evidence failed the gate (CI includes 0). The level machinery (AVWAP/POC distance, volume shelves, gap maps, overhead supply, float turnover) stays governed by Signal Commons R2. R2's gate condition (EI P1.3) is now satisfied (2026-07-05); the bundled phase-0 is declared DISPATCHABLE inside the EI program as ONE family with one FDR budget.

**Scope fence:** Price-memory level machinery display-only under Signal Commons R2; DCA policy object forbidden.

**Forbidden actions:**
  - build max_add parameter
  - build no_chase_above parameter
  - build DCA policy object
  - issue trade instructions via display JSON

**Unblock condition:** EI P1.3 completed 2026-07-05; price-memory phase-0 now dispatchable. Come-back 2026-07-20.

**Come back on:** 2026-07-20

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R7 (support ladders / DCA).** The DCA policy object is KILLED: `max_add`, `no_chase_above`, `invalid_if` are trade instructions (authority smuggling)

*Owner program: entry-intelligence*


### entry-stack

### RUL-P8

**ESX Amendment-2 T1 studies: no-CHIP cap until eq_band NC-2 lookup ships**

- Status: `deferred` | Kind: `wave` | Nondelegable: `True`

**Ruling:** ESX Amendment-2 T1 studies (esx_insider_sponsor, esx_macro_release, esx_pos_reset) and W2 S-SQ are authorized to run post-Fable at phase0 for display/context value only, with an explicit no-CHIP cap until the eq_band NC-2 lookup ships. Recorded here so no Fable decision blocks the queue later.

**Scope fence:** Display/context value only; no chip promotion until eq_band NC-2 unblocks.

**Forbidden actions:**
  - promote ESX T1 studies to chip before eq_band NC-2 ships

**Unblock condition:** eq_band NC-2 lookup ships.

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> ESX Amendment-2 T1 studies (`esx_insider_sponsor`, `esx_macro_release`, `esx_pos_reset`) and W2 S-SQ are AUTHORIZED to run post-Fable at phase0 for display/context value with an explicit **no-CHIP cap** until the eq_band NC-2 lookup ships.

*Owner program: entry-stack*

### TOP3-E2

**E2 recall-first near-miss learner: KILL — hindsight label + anti-chase conflict**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** The recall-first near-miss learner is killed. The label is hindsight-defined (not PIT-legal); P1.4 measured the population (never-triggered 7.8-8.9%, all horizon-censored); the ~0.2% base rate makes the 'fixed board expansion' gate vacuous; and it conflicts with the F3 anti-chase HARD GATE verdict. P1.4 stays the standing quarterly census; no learner is to be built.

**Forbidden actions:**
  - build recall-first learner on never-triggered population
  - use hindsight-defined labels for PIT training

**Unblock condition:** Matured, PIT-legal never-triggered population requires a dead-name store that does not currently exist.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **E2** recall-first near-miss learner | **KILL** | Label is hindsight-defined (not PIT-legal); P1.4 already measured the population (never-triggered 7.8-8.9%, ALL horizon-censored — unresolved truth); at a ~0.2% base rate the "fixed board expansion" gate is vacuous; and it pushes against the F3 anti-chase HARD GATE verdict.

*Owner program: entry-stack*

### TOP3-E3

**E3 kernel-rank v2: NO BUILD — accruing; extensions only via new PREREG**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** kernel_rank_shadow is already merged (#1473) with 94 shrunk cells, Wilson bounds, and a registered 300-episode-cluster flip floor (evaluations ≥2026-Q4). No additional build is permitted. Extensions via new species/lane axes are legal only via a new PREREG (P3.1 cell-rollups is the sanctioned path) and stay display/shadow behind Signal Commons R1 until the kernel-FDR clock (2026-10).

**Scope fence:** Display/shadow behind Signal Commons R1 until kernel-FDR 2026-10.

**Forbidden actions:**
  - add species or lane axes to kernel-rank without new PREREG
  - escalate kernel-rank before kernel-FDR clock 2026-10

**Unblock condition:** New PREREG via P3.1 cell-rollup path; kernel-FDR clock 2026-10.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **E3** outcome posterior / kernel-rank v2 | **NO BUILD — already shipped and accruing; let the clock run** | `kernel_rank_shadow` merged #1473: 94 shrunk cells, Wilson bounds, registered 300-episode-cluster flip floor, evaluations ≥2026-Q4.

*Owner program: entry-stack*

### TOP3-E5

**E5 lifecycle/hazard model: KILL — same tape as E3, laundering W-ARM failure**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** The lifecycle/hazard model is killed. It is E3's posterior evaluated per-horizon — one model wearing two names, doubling trials against the same tape. 'Re-arm after base' reopens W-ARM which FAILED promotion (clean15 gate fail deep); rebuilding it without reference is laundering. Any lifecycle variant may only enter later as a state-conditional arm of the SAME entry_stack family.

**Forbidden actions:**
  - build competing-risks hazard over entry stack outcomes
  - re-open W-ARM without citing its FAILED promotion
  - build lifecycle model as independent family

**Unblock condition:** May enter only as a state-conditional arm of entry_stack family if P3.1 shows conditioning value.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **E5** lifecycle/hazard model | **KILL** | A competing-risks hazard over {liftoff, stop, dead_money, cushion} is E3's posterior evaluated per-horizon — one model wearing two names, doubling trials against the same tape. "Re-arm after base" re-opens W-ARM, which FAILED promotion ("clean15 gate fail deep") — rebuilding it unreferenced is laundering.

*Owner program: entry-stack*

### TOP3-U5

**rs_repair bind blocked until ≥20 trading days accrual + Fable ratification**

- Status: `blocked` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** rs_repair_state binding read-only is explicitly blocked until the W0.4 cohort-metrics series has accrued ≥20 trading days (approximately early August 2026) and Fable has ratified the state taxonomy. This is a standing ops constraint from the PR-B3 outcome.

**Forbidden actions:**
  - bind rs_repair_state read-only before 20-day accrual and Fable ratification

**Unblock condition:** W0.4 series ≥20 trading days accrued (~early Aug 2026) + Fable ratification of state taxonomy.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> rs_repair_state half honestly BLOCKED per RUL-15: W0.4 cohort-metrics series began accruing 2026-07-04, needs ≥20 trading days (~early Aug 2026) + Fable ratification of the state taxonomy before binding read-only.

*Owner program: entry-stack*

### NEXTL-U13

**13F-as-positive-sponsorship: opposite sign to filed phase-0 verdict; struck**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Using 13F/ownership data as a positive sponsorship signal proposes the opposite sign to a filed phase-0 verdict. It is struck on three stacked priors: esx_insider_sponsor 3-for-3 refuted/null at 21d, long_hold.insider_sponsor_lh F4 null at 252d, and the smart_money CONTEXT-ONLY/contrarian-crowding ruling.

**Forbidden actions:**
  - propose 13F as positive sponsorship signal
  - use insider/ownership as bullish entry signal

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> The ownership/13F leg is struck on three stacked priors: `esx_insider_sponsor` 3-for-3 refuted/null at 21d (#1566), `long_hold.insider_sponsor_lh` F4 null at 252d, and the standing `smart_money` CONTEXT-ONLY/contrarian-crowding ruling — 13F-as-positive-sponsorship proposes the *opposite sign* to a filed phase-0 verdict.

*Owner program: entry-stack*

### NEXTL-U8

**F-HZ-3 (ev_blackout extension): operative-panel mae21 null + mae63 NOT MET; low priority**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** F-HZ-3's forward-horizon mechanism is unsupported at the operative panels: esx_ev_blackout mae21 co-primary is null (Welch p=0.6525), and the k=3-pooled mae63 hygiene clause is NOT MET. Only the stop5 'absorb-early' effect is robust. Any clean-flag extension must carry derived_from_surface: esx_ev_blackout and is low priority.

**Forbidden actions:**
  - claim esx_ev_blackout supports clean-21 or clean-63 mechanism
  - promote ev_blackout to mae21/mae63-primary signal

**Unblock condition:** Extension registered through esx_ev_blackout extension pattern with derived_from_surface

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> F-HZ-3 = shipped `esx_ev_blackout` (+8.7pp stop5 inside earnings window; mae21 co-primary NULL — Welch p=0.6525, CI incl 0, W1_SEV_REPORT mae21 Addendum; mae63 NOT MET on the operative k=3 pooled hygiene clause

*Owner program: entry-stack*

### RUL-N3

**Sponsorship: only C3 neutral vocabulary; 13F/ownership leg struck**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Only the frozen C3 neutral vocabulary (tailwind/headwind/neutral/stale/unavailable) may surface for sponsorship. The memo's supportive mechanism labels are barred by entry-stack RUL-28 until evidence supports them. The ownership/13F leg is struck on three stacked priors: esx_insider_sponsor 3-for-3 null at 21d, long_hold F4 null at 252d, and the smart_money CONTEXT-ONLY/contrarian-crowding ruling.

**Scope fence:** Sponsorship vocabulary locked to C3 neutral set; no supportive mechanism labels or 13F-as-positive-signal allowed.

**Forbidden actions:**
  - surface forced_flow_reversal label
  - surface ownership_breadth_repair label
  - surface insider_or_management_support label
  - surface short_covering_fuel label
  - use 13F as positive sponsorship signal

**Unblock condition:** Evidence supports supportive vocabulary per entry-stack RUL-28

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N3 (sponsorship vocabulary + sign):** only the frozen C3 neutral vocabulary (`tailwind/headwind/neutral/stale/unavailable`) may surface. The memo's supportive mechanism labels (`forced_flow_reversal`, `ownership_breadth_repair`, `insider_or_management_support`, `short_covering_fuel`) are barred by entry-stack RUL-28 until evidence supports them. The ownership/13F leg is struck on three stacked priors: `esx_insider_sponsor` 3-for-3 refuted/null at 21d (#1566), `long_hold.insider_sponsor_lh` F4 null at 252d, and the standing `smart_money` CONTEXT-ONLY/contrarian-crowding ruling — 13F-as-positive-sponsorship proposes the *opposite sign* to a filed phase-0 verdict.

*Owner program: entry-stack*

### DT-R5

**Volatility-void 5-definition family killed; def-4 parked behind S-SQ**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** The 5-definition volatility-void family is KILLED as proposed: defs 1-2 duplicate vol_squeeze.py; the inside/armed state is the BANNED arming variant (ESX §9); def-3's volume-shelf leg is price-memory (DT-R7 routing); uncounted multiplicity is disqualifying. Def-4 (RV-collapse-after-drawdown conditioning) and retest/false-break states are PARKED as candidate S-SQ variants behind the already-authorized S-SQ phase-0 (RUL-P8).

**Scope fence:** Def-4 variants may only be studied after the authorized S-SQ phase-0 runs.

**Forbidden actions:**
  - build volatility_hole as buy signal
  - build armed/inside state variant
  - launch new vol-void family before S-SQ phase-0

**Unblock condition:** S-SQ phase-0 (RUL-P8) must run first; then def-4 and retest/false-break states may be proposed as S-SQ variants.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R5 (volatility voids).** The 5-definition family is KILLED as proposed: defs 1–2 duplicate `vol_squeeze.py`

*Owner program: entry-stack*

### DT-U7

**Void-box def-4 and retest states parked behind S-SQ phase-0 (RUL-P8)**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** Void-box def-4 (RV-collapse-after-drawdown conditioning) and the retest/false-break state extensions are parked as candidate S-SQ variants behind the already-authorized S-SQ phase-0 (RUL-P8, post-Fable queue). Clock-first: run the authorized study before inventing variants of it.

**Forbidden actions:**
  - build def-4 or retest states before S-SQ phase-0 completes

**Unblock condition:** S-SQ phase-0 (RUL-P8) completes.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Def 4 (RV-collapse-after-drawdown conditioning) and the retest/false-break state extensions are PARKED as candidate S-SQ variants **behind** the already- authorized S-SQ phase-0 (RUL-P8, post-Fable queue)

*Owner program: entry-stack*

### ESX-RUL-1

**Volume-confirmation confirmers permanently dead (H4)**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Volume-confirmation confirmers are permanently killed by H4 falsification. No W1 or W2 family may include them. Volume appears only inside S-SQ's confirmed release bar and D1's pocket-pivot event definition, nowhere else.

**Scope fence:** US entry-stack program; covers all families W1/W2+.

**Forbidden actions:**
  - add volume slope as stratum
  - add OBV as gate or bonus
  - add CMF as filter
  - add RVOL as positive confirmer

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-1:** Volume-confirmation confirmers are DEAD (H4) — no W1/W2 family may include them; volume appears only inside S-SQ release confirmation and D1's event definition.

*Owner program: entry-stack*

### ESX-RUL-10

**Replay-mismatch handled via legal registry moves only; no new lifecycle states**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** When a chip's effect does not replicate on production-fidelity replay shards, handling uses only legal registry moves: validation_status stays 'accruing', deployment_status reverts to 'unshipped', gating.come_back_on is set, and the mismatch recorded in the gating note. No new lifecycle states (e.g. 'frozen') may be invented.

**Scope fence:** Registry lifecycle transitions on replay mismatch.

**Forbidden actions:**
  - invent new validation_status value
  - mark status 'frozen'
  - modify replay_standout_pipeline.py

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-10 ⟦RT⟧:** Replay-mismatch handling uses only legal registry moves (accruing + deployment revert + come_back_on); no new lifecycle states.

*Owner program: entry-stack*

### ESX-RUL-11

**No fire testifies twice: backfill rows excluded from FDR sweeps and confluence edges**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The quarterly FDR sweep and any confluence-lift edge must exclude backfill-v1 rows drawn from a fire-set that already produced a phase0 verdict. The same historical fire may never testify twice — once in a study and once as independent kernel or graph evidence.

**Scope fence:** FDR sweeps, confluence-lift edges, and kernel evidence in Neural Web.

**Forbidden actions:**
  - include phase0-tested fires in FDR sweep
  - use phase0-tested fires as independent confluence edge evidence

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-11 ⟦RT⟧:** No fire testifies twice: FDR sweeps and confluence edges exclude backfill rows whose fire-set already produced a phase0 verdict.

*Owner program: entry-stack*

### ESX-RUL-12

**R1 estimator fully specified; FE granularity fixed once at W0; post-hoc switching banned**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** The R1 estimator is the date-FE stratified difference with episode-clustered SEs and block-bootstrap CIs. FE granularity (date-FE vs era×sector-week FE fallback) is chosen once per family at W0 sign-off and never changed post-hoc. Post-hoc granularity switching is banned.

**Scope fence:** All stratum studies under this program.

**Forbidden actions:**
  - switch FE granularity after seeing results
  - use unblock-bootstrapped CIs
  - change cluster definition mid-study

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-12 ⟦RT⟧:** The R1 estimator is the date-FE stratified difference with episode-clustered SEs and block-bootstrap CIs; FE granularity fixed once per family at W0 sign-off; post-hoc granularity switching is banned.

*Owner program: entry-stack*

### ESX-RUL-2

**R1 date-FE estimator mandatory for all stratum studies**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Every stratum study must run the R1 date-fixed-effects stratified difference estimator and cite the nearest falsified adjacency relative (R2 rule). A study lacking either is invalid regardless of result. Post-hoc switching between FE granularities is banned; granularity is fixed once per family at W0 sign-off.

**Scope fence:** All stratum studies under this program.

**Forbidden actions:**
  - run stratum study without date-FE control
  - switch FE granularity post-hoc
  - omit adjacent_falsified field

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-2:** Every stratum study runs the R1 estimator and cites adjacency (R2); a study lacking either is invalid regardless of result.

*Owner program: entry-stack*

### ESX-RUL-3

**Null-competitors NC-1/NC-2 run first; NC-2 marginality defined**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Null-competitors NC-1 and NC-2 must run before any candidate study and appear as the first table in every W1/W2 report. A candidate 'beats NC-2' only if its stratum coefficient retains a CI-excluding-0 after entry_quality-band fixed effects are added to the R1 model (marginal value test).

**Scope fence:** All W1/W2 candidate verdict reports.

**Forbidden actions:**
  - read candidate verdict before NC table
  - claim NC-2 beat on parallel-model comparison

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-3:** Null-competitors NC-1/NC-2 run first and appear as the first table in every W1/W2 report; NC-2 marginality = coefficient survives entry_quality-band fixed effects.

*Owner program: entry-stack*

### ESX-RUL-4

**S-EV only candidate permitted as hard gate (hygiene-only)**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** S-EV (earnings-blackout veto) is the only candidate in this program that may target a hard entry gate, and only under hygiene semantics with the F1 per-row fail-open staleness rule. All other candidates deploy as chips, bonuses, or strata — never hard gates.

**Scope fence:** All candidates in this program; hygiene-gate lane is S-EV exclusive.

**Forbidden actions:**
  - wire S-UR as hard gate
  - wire S-SQ as hard gate
  - wire S-LQ as hard gate
  - wire S-QL as hard gate

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-4:** S-EV is the only candidate permitted to target a hard gate, and only under hygiene semantics with the F1 per-row fail-open rule.

*Owner program: entry-stack*

### ESX-RUL-5

**Species register before first compute; expect-null pre-declared**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Trigger species must register (with adjacent_falsified field, fixtures, and ledger binding) in engine/species_registry.py BEFORE first compute. Expect-null studies must pre-register the null as the expected outcome; non-null is defined only as a pooled BH-adjusted CI excluding 0.

**Scope fence:** All new trigger species in this program.

**Forbidden actions:**
  - compute before registry entry
  - claim non-null on single-era excursion
  - omit expect-null pre-registration for S-TS

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-5:** Trigger species register (with adjacent_falsified + fixtures) BEFORE first compute; expect-null studies (S-TS) pre-register the null as the expected outcome, with non-null defined as pooled BH-adjusted CI excluding 0 only.

*Owner program: entry-stack*

### ESX-RUL-6

**Derivatives-shape throttle accrue-only until ≥120 skew dates**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** Per-name options-surface throttle (skew/IV-spread/GEX shape) is accrue-only until the skew ledger holds ≥120 dates. The W5 auto-revisit clause is the only sanctioned path back. No study or product deployment is permitted before that threshold.

**Scope fence:** Options-surface throttle species; US per-name only.

**Forbidden actions:**
  - run options-surface stratum study before 120 skew dates
  - ship options-shape chip before threshold

**Unblock condition:** Skew ledger holds ≥120 dates (≈2027-01); W5 auto-revisit is the only path.

**Come back on:** 2027-01-01

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-6:** Derivatives-shape throttle is accrue-only until the skew ledger holds ≥120 dates; the W5 auto-revisit is the only path back.

*Owner program: entry-stack*

### ESX-RUL-7

**§5 thresholds frozen at W0 reviewer sign-off; changes need new ruling**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** All promotion-bar thresholds in §5 are frozen at the W0 opus-stats reviewer sign-off. The reviewer may raise the CHIP floor (≥2pp stop5) but never lower it. Any later change requires a new ruling logged in this document; silent edits to thresholds are forbidden.

**Scope fence:** All §5 promotion bars across this program.

**Forbidden actions:**
  - silently lower chip floor below 2pp
  - change FE granularity post-hoc
  - update threshold without logging a ruling

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-7:** Thresholds in §5 are frozen at W0 review sign-off (the reviewer may RAISE the CHIP floor, never lower it); any later change requires a new ruling logged here, never a silent edit.

*Owner program: entry-stack*

### ESX-RUL-8

**Backfilled spine rows carry version: backfill-v1 tag; excluded from live claims**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** All historical backfill spine rows emitted from W0 fire dumps must carry `version: backfill-v1` metadata tag. These rows are excluded from any live-accrual claim and must be distinguishable from PIT-clean live rows.

**Scope fence:** All spine engine backfill emissions from this program.

**Forbidden actions:**
  - claim live-accrual status for backfill-v1 rows
  - mix backfill rows into live-accrual statistics

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-8:** Backfilled spine rows carry `version: backfill-v1` and are excluded from any live-accrual claim.

*Owner program: entry-stack*

### ESX-RUL-9

**One grader per program; wave1 numbers are context only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** All candidate and incumbent-baseline numbers must be computed under engine.grading definitions (stop5, clean-liftoff 1.15/126, dead_money, mae63, mfe63, days_to_10). Wave1-era numbers (clean15=1.20+durable-hold) are historical context only and may not satisfy any promotion bar. Baselines are recomputed at W0 before bars freeze.

**Scope fence:** All candidate and incumbent comparisons in this program.

**Forbidden actions:**
  - use wave1-era clean15=1.20 numbers to satisfy a promotion bar
  - skip incumbent baseline recompute under program grader

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **RUL-9 ⟦RT⟧:** One grader per program: all candidate AND incumbent-baseline numbers are computed under `engine.grading` definitions; wave1-era numbers are historical context only and may not satisfy a bar.

*Owner program: entry-stack*

### ESX-U1

**HK/CA excluded by default from all species tests**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** HK and CA markets are excluded by default from all species studies in this program. Every US bottom mechanism tested so far inverts or fails in those markets (SETUP_SPECIES §HK doctrine). CN is secondary only where a species pre-registers its own CN test.

**Scope fence:** All species and stratum studies in this program.

**Forbidden actions:**
  - run HK port without separate program mandate
  - run CA port without separate program mandate
  - assume CN result generalizes without pre-registration

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **HK/CA excluded by default** (every US bottom mechanism tested so far inverts or fails there — SETUP_SPECIES §HK doctrine).

*Owner program: entry-stack*

### ESX-U10

**S-EV demotes to live-veto-only if 8-K date build fails coverage gate**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** S-EV's historical backtest anchor must use EDGAR 8-K Item 2.02 filing dates (eps_quarterly.asof_date is void — synthetic +60d constant). If the 8-K date build cannot reach ≥800 names × ≥8y coverage, S-EV demotes to live-veto-only (forward-accrued hygiene) and the artifact must say so explicitly. The old asof_date anchor is permanently void.

**Scope fence:** S-EV historical backtest only; live rule unaffected by demotion.

**Forbidden actions:**
  - use eps_quarterly.asof_date as earnings announcement anchor
  - claim historical S-EV verdict when coverage < 800 names × 8y

**Unblock condition:** 8-K date build reaches ≥800 names × ≥8y; else live-veto-only path.

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> historical anchor = **EDGAR 8-K Item 2.02 dates** built in W1 (reuse guidance_gap.py's 8-K plumbing; keyless). The old plan's `eps_quarterly.asof_date` anchor is VOID (synthetic +60d).

*Owner program: entry-stack*

### ESX-U14

**Species law: monthly review is sole status mover; falsified is terminal**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** All species registrations and transitions must go through engine/species_registry.py APIs. The monthly review is the only mechanism that can move a species status. Falsified is a terminal status — it cannot be revived or reopened under any circumstance.

**Scope fence:** All species in this program registered under #1097.

**Forbidden actions:**
  - move species status outside monthly review
  - revive a falsified species
  - bypass species_registry.py API

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **8.1 #1097 species law:** all registrations/transitions through `engine/species_registry.py` APIs; monthly review is the only status mover; falsified is terminal.

*Owner program: entry-stack*

### ESX-U15

**Kernel cells accrue display-first; consumption forbidden until quarterly FDR sweep passes**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Kernel cells for all surviving sensors accrue display-first. No consumption of shrunken_ic from these cells is permitted until the quarterly FDR sweep passes (standing clock: 2026-10). MIN_FAMILY_N=12 and WILSON_MIN_N=12 are event floor minimums. Rare species may take quarters to arm per-regime cells.

**Scope fence:** Neural Web kernel cells for all ESX-program sensors.

**Forbidden actions:**
  - consume shrunken_ic before quarterly FDR sweep
  - arm kernel cell with fewer than 12 family events

**Unblock condition:** Quarterly FDR sweep passes (2026-10 clock).

**Come back on:** 2026-10-01

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> Kernel cells accrue display-first; nothing consumes `shrunken_ic` until the quarterly FDR sweep passes (PR2 law). Event floors: MIN_FAMILY_N=12 / WILSON_MIN_N=12

*Owner program: entry-stack*

### ESX-U18

**CHIP promotion floor: n≥400 fires, stop5 FE ≥2pp CI excluding 0, sign-stable ≥3/4 eras**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** CHIP/STRATUM promotion requires: n ≥ 400 date-deduped fires per stratum arm, primary endpoint stop5 FE-coefficient ≥ 2pp with block-bootstrap 95% CI excluding 0, supporting MFE/|MAE| delta ≥ 0.10, sign-stable in ≥3/4 eras, survives BH q≤0.10, and beats both null-competitors under marginality test. The reviewer may raise but never lower the 2pp floor at W0 sign-off.

**Scope fence:** All CHIP/STRATUM promotion decisions in this program.

**Forbidden actions:**
  - lower chip floor below 2pp stop5
  - promote chip without NC marginality test
  - count era-excursion as sign-stability

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> CHIP/STRATUM: n ≥ 400 date-deduped fires per stratum arm (pooled; era table reported); primary endpoint stop5 FE-coefficient ≥ 2pp with block-bootstrap 95% CI excluding 0; supporting MFE/|MAE| delta ≥ 0.10; sign-stable in ≥3/4 eras

*Owner program: entry-stack*

### ESX-U2

**Display-only until earned via chip→ledger→graded-bonus→gate-weight ladder**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** All new triggers and sensors deploy display-only; they earn weight via the chip→ledger→graded-bonus→gate-weight ladder. Hard gates are reserved for hygiene only. New signals deploy as bonuses or chips; a signal is never promoted to gate by outperforming a threshold in a single study.

**Scope fence:** All candidates in this program before ledger maturation.

**Forbidden actions:**
  - wire new trigger as gate without hygiene justification
  - skip chip/ledger phase

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> display-only until earned (chip → ledger → graded bonus → gate weight); marker-date/same-bar-fill ban (+5.7pp/10d phantom); comparisons-not-absolutes under survivor bias

*Owner program: entry-stack*

### ESX-U3

**Nightly is sole ledger advancer; intraday lanes never advance ledgers**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The nightly pipeline is the sole advancer of forward ledgers. Intraday lanes must never advance ledger state. Every new data store must be git-added and wired into the sentinel's staging list in the same PR as its creation.

**Scope fence:** All ledger-writing operations in this program.

**Forbidden actions:**
  - advance ledger from intraday lane
  - add store without sentinel staging list update

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> nightly is sole ledger advancer; every new store is git-added and wired into the sentinel's staging list (sentinel-staging-gap incident)

*Owner program: entry-stack*

### ESX-U4

**Exit-rule revival is a non-goal; EMA8 is tail-flag only**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Exit-rule work is permanently NO-GO for this program. EMA8 is a tail-flag only; cut_fwd is positive everywhere. Exit-rule revival is explicitly listed among non-goals and may not be re-opened under this program.

**Scope fence:** This program's scope; original kill from CONFLUENCE_TUNING §8.

**Forbidden actions:**
  - revive exit-rule work under this program
  - use EMA8 as exit signal beyond tail-flag display

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> | Exit-rule work | **NO-GO** stands; EMA8 = tail-flag only; cut_fwd positive everywhere | §1.6 / CONFLUENCE_TUNING §8 |

*Owner program: entry-stack*

### ESX-U6

**LLM law: models may de-escalate calibrated keys only; no LLM originates signals**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** LLM law is unchanged in this program: models may de-escalate calibrated keys only. No LLM may originate any signals, scores, or escalations from the sensors built in this program.

**Scope fence:** All LLM interactions with this program's sensors and outputs.

**Forbidden actions:**
  - LLM originates signal fire
  - LLM originates entry score
  - LLM escalates calibrated key

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> LLM law unchanged: models may de-escalate calibrated keys only; no LLM originates any of these signals.

*Owner program: entry-stack*

### ESX-U7

**S-SQ 'arming' variant banned from family; release-bar-only definition frozen**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** An 'arming' variant of S-SQ that anticipates inside quiet bases is permanently BANNED from the esx_sq_phase0 family and any descendant. S-SQ acts only on the confirmed release bar, direction-signed, volume-checked. The distinction must hold empirically or the species dies. The release-bar-only definition is frozen pre-run.

**Scope fence:** esx_sq_phase0 family and all S-SQ descendants.

**Forbidden actions:**
  - add arming variant to S-SQ family
  - anticipate quiet base in S-SQ trigger
  - test arming-style squeeze entry

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> An "arming" variant is BANNED from the family (§9). The distinction must hold empirically or the species dies.

*Owner program: entry-stack*

### ESX-U9

**S-QL PIT status disclosed: assumed 120d lag; margin-dependent quality defs banned**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** S-QL artifacts must carry pit_basis: assumed-120d-lag in every output because the fundamentals panel asof_date is a synthetic constant (not per-filer filing dates). Facts are usable only ≥120d after FY-end by construction. Interaction arms (quality × washout-depth) are restricted to full-coverage Piotroski/Altman; margin-dependent quality defs are banned due to 32% coverage.

**Scope fence:** esx_ql_overlay family and all S-QL artifacts.

**Forbidden actions:**
  - describe asof_date as real filing date
  - use gross_margin in S-QL interaction arms
  - use Sloan-only without coverage caveat

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> **PIT status: the panel's asof_date is an assumed flat 120d lag, not per-filer filing dates** — every S-QL artifact carries `pit_basis: assumed-120d-lag`; facts usable only ≥120d after FY-end by construction

*Owner program: entry-stack*

### ESX-R2-ADJACENCY

**Adjacency citation required before first compute; re-derivation = wave failure**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Every candidate must name its nearest falsified relative from the graveyard and state the mechanical difference in one sentence in the species registry adjacent_falsified field, BEFORE first compute. Re-derivation of a graveyard idea equals automatic wave failure (standing law).

**Scope fence:** All candidates across this program.

**Forbidden actions:**
  - compute without adjacent_falsified field
  - re-derive graveyard idea under a new name

**Source:** `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
> Re-derivation of a graveyard idea = automatic wave failure (standing law).

*Owner program: entry-stack*

### ESX-FV-A3m

**A3m esx_htf_turn monthly — NULL by non-replication; adjudication overrides mechanical grader**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** A3m wins on deep only (operative -2.40pp, survives nc2 -3.22pp, era 4/4) but fails the larger baskets OOS (era 1/3, one era 0 fires, operative CI incl 0) and was pre-registered expect-weak. Deep-only win on survivor-biased panel failing the decisive OOS is the textbook overfit/survivorship signature. The adjudication non-replication override supersedes the report's mechanical DISPLAY-CANDIDATE. Held as shadow observation; no verdict weight.

**Scope fence:** Shadow observation only; no verdict weight.

**Forbidden actions:**
  - promote A3m monthly-turn based on deep-only win
  - override non-replication ruling with mechanical grader output

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **A3m `esx_htf_turn` monthly** | **NULL (by non-replication)** — overrides the report's mechanical DISPLAY-CANDIDATE | Wins on deep only

*Owner program: entry-stack*

### ESX-FV-B

**B esx_htf_turn_dose — NULL/DESCRIPTIVE; proximity gradient, not mechanism; falsifier logged**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** B (esx_htf_turn_dose) is NULL/DESCRIPTIVE: the ordinal per-unit coef is CI-excl-0 but is NOT proximity-de-confounded and legs are same-source collinear. Most parsimoniously a proximity gradient. Also partially re-measures shipped bottom_confidence tf_score construct. Falsifier logged: re-run ordinal dose with nc2_band (+ rv63) FE kill-arm; prediction is collapse to CI-incl-0.

**Forbidden actions:**
  - use B dose ordinal result as mechanism evidence without nc2 FE kill-arm

**Unblock condition:** Falsifier run: ordinal dose with nc2_band + rv63 FE kill-arm does NOT collapse to CI-incl-0.

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **B `esx_htf_turn_dose`** | **NULL / DESCRIPTIVE** | Monotone gradient real (baskets 23.2→20.6→18.5→**18.7**%; the leg-3 reversal is a confound tell) and the ordinal per-unit coef is CI-excl-0, but it is NOT proximity-de-confounded (no nc2 arm on the ordinal) and the legs are same-source collinear.

*Owner program: entry-stack*

### ESX-FV-C

**C esx_washout_x_turn — KILLED; depth adds negative marginal once proximity removed**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** C (esx_washout_x_turn) is KILLED: nc2 kills contrast-i (-0.29pp CI incl 0) and the marginality interaction is adverse (+0.014 baskets / +0.024 deep). Re-confirms the H1 depth kill fire-conditionally. The operator's literal 2W-washout × turn seed adds NEGATIVE marginal value once proximity is removed.

**Forbidden actions:**
  - re-open esx_washout_x_turn without new kill-overriding evidence

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **C `esx_washout_x_turn`** | **KILLED** | The operator's literal 2W-washout × turn seed adds NEGATIVE marginal value once proximity is removed

*Owner program: entry-stack*

### ESX-FV-E

**E esx_decline_geometry — DISPLAY-CANDIDATE; flush descriptor ships nightly display-only**

- Status: `adopted` | Kind: `signal_family` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** E (esx_decline_geometry) is DISPLAY-CANDIDATE: flush-vs-rest stop5 survives the full RUL-30 battery on both panels, era-sign-stable 4/4, ticker-half agree both panels. Ships as a display-only descriptor field (flush / mixed / grind) on the bottom_sensors envelope plus shadow forward-ledger. Frame as decline-shape read, NOT escalation; is_display_only=True; the word 'validated' must be absent; no rank/bonus change.

**Scope fence:** Display-only; no ranked-output consumer; no CHIP promotion until eq_band lands.

**Forbidden actions:**
  - use decline_geometry as rank or bonus input
  - escalate based on decline_geometry
  - use the word 'validated' in user-facing text for this field

**Unblock condition:** eq_band lands; re-run through real NC-2 marginality FE; CHIP case re-opens.

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **E `esx_decline_geometry` (flush)** | **DISPLAY-CANDIDATE** | The cleanest result in the program. Flush-vs-rest stop5 −1.00pp (deep) / −2.34pp (baskets), both CI-excl-0; survives the FULL RUL-30 battery

*Owner program: entry-stack*

### ESX-FV-F

**F esx_underwater — ADVERSE-CONTEXT; shadow only, de-escalation lane only, never buy signal**

- Status: `adopted` | Kind: `signal_family` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** F (esx_underwater) shows the strongest statistical effect but adverse: long-underwater = stop5 WORSE on both panels; all three co-primaries agree; survives age63 pure-age kill-arm and ¬bear_ctx. It is a caution axis only — de-escalation-eligible under LLM-de-escalation house law. Never used as a buy signal. Ships as shadow-only adverse/caution field feeding de-escalation lane.

**Scope fence:** Shadow only; no user surface; feeds de-escalation lane only.

**Forbidden actions:**
  - use esx_underwater as a buy signal
  - escalate based on esx_underwater
  - surface underwater field to user directly

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **F `esx_underwater`** | **ADVERSE-CONTEXT** (real, AVOID sign) | Statistically the strongest effect, but adverse: long-underwater = stop5 +2.35pp (deep) / +6.31pp (baskets) WORSE; all three co-primaries agree

*Owner program: entry-stack*

### ESX-FV-G

**G esx_vol_transition — NULL (expect-null confirmed); vol-family question settled**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** G (esx_vol_transition) is NULL with expect-null confirmed: deep era 1/4, ticker-half DISAGREE. Vol term-structure motion adds nothing once vol level is controlled. This settles the vol-family question for the program.

**Forbidden actions:**
  - re-open vol term-structure motion families without new evidence

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **G `esx_vol_transition`** | **NULL (expect-null confirmed)** | Vol term-structure MOTION adds nothing once vol LEVEL is controlled: deep era 1/4, ticker-half DISAGREE. Settles the vol-family question.

*Owner program: entry-stack*

### ESX-RUL-27

**A3 identity, scope, marginals-first law — esx_* families, frozen tape, US only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** A3 rides inside Entry-Stack Expansion with esx_* families on frozen fire tapes, RUL-9 grader, RUL-13 21d primaries. US panels only (deep + baskets); delisted-panel arms are struck. A3 registers exactly three interaction families (C, D, and dose ladder B); all further non-momentum × momentum confluence pairings are deferred to a follow-up amendment gated on A3 marginal survivors — interactions of nulls are not purchased.

**Scope fence:** US panels only (deep + baskets); delisted-panel arms struck; no interaction families beyond C, D, B until A3 marginal survivors confirmed.

**Forbidden actions:**
  - run delisted-panel arms in A3
  - add further non-momentum x momentum confluence pairings before A3 marginal survivors confirmed
  - test interactions of nulls

**Unblock condition:** A3 marginal survivors established before follow-up amendment (esx_degree_alignment, A4) can proceed.

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> gated on A3 marginal survivors — interactions of nulls are not purchased.

*Owner program: entry-stack*

### ESX-RUL-28

**Verdict-ceiling law — A3 families capped at DISPLAY-CANDIDATE; CHIP blocked until eq_band**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The 63-bar close-min NC-2-PROXY band-FE arm is mandatory as a KILL-ARM in every A3 primary read. An effect that dies under proxy-FE is a proximity shadow. An effect surviving it is still not CHIP-promotable: CHIP promotion is BLOCKED for all A3 families until the true eq_band lands. A3 verdict vocabulary is capped at DISPLAY-CANDIDATE / NULL / KILLED.

**Scope fence:** All A3 families; CHIP promotion blocked until true eq_band cache lands.

**Forbidden actions:**
  - promote A3 family to CHIP before eq_band lands
  - omit NC-2-PROXY kill-arm from A3 primary read
  - use DISPLAY-CANDIDATE to rank outputs

**Unblock condition:** True eq_band (cand_price/dcl_price pivot) lands; recomputed COILED-FIRE recall clause likewise deferred.

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> CHIP promotion is BLOCKED for all A3 families until the true eq_band (cand_price/dcl_price pivot) lands; the recomputed COILED-FIRE recall clause is likewise deferred. A3 verdict vocabulary is capped at **DISPLAY-CANDIDATE / NULL / KILLED**.

*Owner program: entry-stack*

### ESX-RUL-29

**Admission-leg law — weekly RSI-MACD families must include gate admission-leg FE covariate**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** For any family whose feature is computed on the weekly RSI-MACD series (A1; C's A1-interaction form), the pooled read must include the gate admission-leg (wbull vs fromos3) as an FE covariate. The operative verdict coefficient is the one measured within the ¬wbull (fromos3-admitted) subset. The admission-leg decomposition table is mandatory in every A3 report touching a weekly feature.

**Scope fence:** Applies to A1 and C (A1-interaction form); mandatory in all A3 reports touching weekly features.

**Forbidden actions:**
  - report wbull-admitted subset as operative verdict coefficient for weekly RSI-MACD families
  - omit admission-leg decomposition table from weekly-feature A3 reports

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> the pooled read must include the gate admission-leg (`wbull` vs `fromos3`) as an FE covariate, and the **operative verdict coefficient is the one measured within the ¬wbull (fromos3-admitted) subset** — on the wbull-admitted subset a weekly flag re-reads the gate's own confirm leg.

*Owner program: entry-stack*

### ESX-RUL-30

**De-confound battery — frozen kill-only diagnostics for A3 families**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** A frozen battery of six controls applies to A3 families; each element can only kill or downgrade, never upgrade. Controls are: NC-2-proxy band-FE (all families), realized-vol-LEVEL tercile FE (vol/ATR-adjacent families C/E/G), ¬bear_ctx decomposition (bear-regime-correlated families C/E/F/G), pure-age covariate (F), marginality-vs-A (B/C/D), and admission-leg (A1/C). BH runs over declared family configs; diagnostics are pre-registered kill-arms.

**Scope fence:** All A3 families; diagnostic controls can only kill or downgrade.

**Forbidden actions:**
  - use RUL-30 battery result to upgrade a signal
  - omit applicable battery arm from A3 family report
  - add new controls to battery post-registration

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> Frozen battery; each element can only kill or downgrade, never upgrade ⟦RT: no silent FDR inflation — BH runs over the declared family configs; diagnostics are pre-registered kill-arms⟧:

*Owner program: entry-stack*

### ESX-RUL-31

**HTF PIT + faithful-math law — last completed bar, pinned implementations, no conflation**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Every HTF feature uses the last completed HTF bar whose known-date <= fire date. Math is pinned: RSI-MACD = confluence_tiers._rsi_macd; StochRSI = confluence_tiers._stoch_rsi_kd (14/3/3, K&D, 0-100). cycles.stoch_rsi (K-only) and price macd_parts are forbidden — three co-existing implementations exist; conflation is a build error. Monthly RSI-MACD runs deep-panel-only; registered monthly rung (A3m) is monthly StochRSI. Every per-fire feature requires an explicit compute_*_at_fires step and a leak-audit section.

**Scope fence:** All A3 HTF feature computation; applies to builders and reviewers.

**Forbidden actions:**
  - use cycles.stoch_rsi (K-only) for A3 features
  - use price macd_parts for A3 features
  - include in-progress HTF bar in feature computation
  - re-parameterize the H1 washout convention

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> 0-100). **Never** `cycles.stoch_rsi` (K-only) and never price `macd_parts` — three co-existing implementations exist

*Owner program: entry-stack*

### ESXA3-U1

**S6 owns serial-failure / nth-fire constructs — A3 may not run parallel family**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** S6 Failed-Fire Fuel is a registered species with phase-0 PASSED OOS on baskets in both variants (failed2×COILED). Serial-failure / nth-fire constructs are S6's property and A3 may not run a parallel family per RUL-11 spirit.

**Scope fence:** Property fence: serial-failure construct belongs to S6.

**Forbidden actions:**
  - run A3 parallel family for serial-failure construct
  - run nth-fire ordinal in A3

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> Serial-failure / nth-fire constructs are **S6's property** ⟦RT blocker⟧.

*Owner program: entry-stack*

### ESXA3-U3

**Gate confirm3 already reads weekly state — weekly strata partially re-read gate admission**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** confirm3 = (weekly RSI-MACD bullish) OR (3D stoch recently oversold) is the gate's admission leg (engine/confluence_tiers.py:195). Weekly-state strata partially re-read the gate's own admission structure. This is the reason RUL-29 mandates the admission-leg FE covariate and ¬wbull operative subset.

**Scope fence:** Gate-admission re-read hazard applies to all weekly-feature A3 families.

**Forbidden actions:**
  - report wbull-admitted weekly coefficients as independent evidence

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **The gate already reads weekly STATE.** `confirm3 = (weekly RSI-MACD bullish) OR (3D stoch recently oversold)` (engine/confluence_tiers.py:195) — so weekly-state strata partially re-read the gate's o

*Owner program: entry-stack*

### ESXA3-U4

**A2 esx_htf_turn 2W — NULL; knife-edge p and mae21 co-primary fails; 2W turn catastrophically late**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** A2 (2W StochRSI turn) is NULL: baskets operative -0.73pp is knife-edge (p=0.050) and the mae21 co-primary fails to confirm at the governed horizon (p=0.066); deep NULL. Consistent with pre-registered '2W turn catastrophically late'.

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> **A2 `esx_htf_turn` 2W** | **NULL** | Baskets operative −0.73pp is knife-edge (p=0.050) and the mae21 co-primary fails to confirm at the governed horizon (p=0.066); deep NULL.

*Owner program: entry-stack*

### ESX-U5

**Non-replication override — adjudication supersedes mechanical grader for survivorship/overfit calls**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** When a family wins on the survivor-biased deep panel only and fails the larger baskets OOS, the adjudication may supply a non-replication override that supersedes the report's mechanical DISPLAY-CANDIDATE promotion. This override adopts the overfit lens over the mechanical grader per house law.

**Scope fence:** Applies when report's mechanical grader over-promotes on deep-only win.

**Forbidden actions:**
  - promote deep-only winner to display candidate without baskets OOS replication

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> The report's grader has no non-replication clause; the adjudication supplies it.

*Owner program: entry-stack*

### ESXA3-U6

**Interaction/confluence gating — only E-based confluences eligible in follow-up amendment**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Because only E survived as a clean marginal in A3, only E-based confluences would be eligible in a follow-up amendment. Interactions of nulls are not purchased. esx_degree_alignment (A4) stays deferred. This is a standing gate on follow-up amendment scope.

**Scope fence:** Follow-up amendment scope limited to E-based confluences only.

**Forbidden actions:**
  - open A4 or follow-up amendment with null-based interaction families
  - purchase interactions of nulls

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> rred (RUL-27): only E survived as a clean marginal, so only E-based confluences would be eligible in a follow-up amendment — interactions of nulls are not purchased.**

*Owner program: entry-stack*

### RUL-33-BASEEFF

**REJECTED: esx_base_efficiency (Kaufman ER / choppiness) — killed by name**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** Kaufman ER is killed BY NAME in the masterplan §5b guard kill. Choppiness is CHARTER 'folklore/avoid', collinear with ER. esx_base_efficiency is rejected; the absorbed-vs-trending claim rides partially in E.

**Forbidden actions:**
  - register esx_base_efficiency
  - run Kaufman ER as A3 family feature
  - run choppiness index as standalone family

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_base_efficiency (Kaufman ER / choppiness absorbed-range) | **REJECTED** | Kaufman ER killed BY NAME in the §5b guard kill; choppiness is CHARTER "folklore/avoid", collinear with ER; the absorbed-vs-trending claim rides partially in E

*Owner program: entry-stack*

### RUL-33-COILRANGE

**REJECTED: esx_coil_range_at_fire — banned squeeze-state-at-fire variant**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** esx_coil_range_at_fire is rejected as a banned variant. The masterplan §3 F3 pre-registered the S-SQ family with the arming (state-without-release) variant BANNED; a state-at-fire family is that variant.

**Forbidden actions:**
  - register esx_coil_range_at_fire
  - run any squeeze-state-at-fire family variant

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_coil_range_at_fire (squeeze-state at fire) | **REJECTED — banned variant** | masterplan §3 F3 pre-registered the S-SQ family with the "arming" (state-without-release) variant BANNED; a state-at-fire family is that variant

*Owner program: entry-stack*

### RUL-33-DEGREEALGN

**DEFERRED to A4: esx_degree_alignment — motion-before-structure sequencing gate**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** esx_degree_alignment (weekly/monthly price higher-low structure) is genuinely untested cross-scale structure but has a position-family confound profile. It is deferred to A4 and may only be bought if A (HTF motion) survives, enforcing motion-before-structure sequencing. Post-adjudication update: only E survived, so esx_degree_alignment remains deferred until an E-based follow-up.

**Forbidden actions:**
  - run esx_degree_alignment before A (HTF motion) has a survivor

**Unblock condition:** A (esx_htf_turn) produces at least one surviving marginal AND A4 amendment opened; or E-based follow-up amendment opened.

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_degree_alignment (weekly/monthly price higher-low structure) | **DEFERRED to A4** | genuinely untested cross-scale structure, but position-family confound profile; buy only if A survives (motion-before-structure sequencing)

*Owner program: entry-stack*

### RUL-33-DIVFIRE

**REJECTED: esx_div_fire (standalone divergence) — anti-validated**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** esx_div_fire (standalone divergence without cohort) is rejected as anti-validated: 'div WITHOUT cohort is actively BAD' per DURABLE_BOTTOM:343.

**Forbidden actions:**
  - register standalone divergence family without cohort

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_div_fire (standalone divergence) | REJECTED at census | anti-validated: "div WITHOUT cohort is actively BAD" (DURABLE_BOTTOM:343)

*Owner program: entry-stack*

### RUL-33-OSCSPECIES

**DECLINED: new oscillator species (TSI/W%R/CCI/DeMark/Ichimoku etc.) and price-MACD HTF variants**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** New oscillator species (TSI, W%R, CCI, MFI, UO, Connors, DeMark, Ichimoku, Coppock, Aroon, SAR, Supertrend) are declined per BOTTOM_CONFIDENCE Result 4 and KST collinearity ruling plus the faithful-math law. Price-MACD HTF variants are declined on budget and faithful-math grounds; collinearity at cycle scale is recorded as untested, not falsified.

**Forbidden actions:**
  - register any of the listed oscillator species as A3 families
  - use price-MACD HTF variants in A3

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> New oscillator species (TSI/W%R/CCI/MFI/UO/Connors/DeMark/Ichimoku/Coppock/Aroon/SAR/Supertrend); price-MACD HTF variants | **DECLINED** | BOTTOM_CONFIDENCE Result 4 + KST collinearity ruling + faithful-math law

*Owner program: entry-stack*

### RUL-33-SECONDTEST

**REJECTED: esx_second_test (double-bottom hold) — proximity shadow, closed by reasoning**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** A held-above-prior-low band is a distance-to-low restatement; the NC-2-proxy arm that nullified S-UR's only positive form is the modal outcome. This candidate is rejected as a proximity shadow. The double-bottom hold stratum folklore is closed by reasoning plus the S-UR corpse.

**Forbidden actions:**
  - register esx_second_test as a new family

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_second_test (double-bottom hold stratum) | **REJECTED — proximity shadow** | a held-above-prior-low band is a distance-to-low restatement; the NC-2-proxy arm that nullified S-UR's only positive form is the modal outcome; folklore closed by reasoning + S-UR corpse

*Owner program: entry-stack*

### RUL-33-SERIAL

**REJECTED: esx_serial_fuel / nth-fire ordinal — owned by S6 Failed-Fire Fuel**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Serial-failure constructs (esx_serial_fuel, esx_episode_spacing, nth-fire ordinal) are rejected because S6 Failed-Fire Fuel owns the construct as a registered species with phase0-PASSED OOS. A3 may not run a parallel family per RUL-11 spirit. S6's pre-registered primary is the failed2×COILED interaction.

**Scope fence:** Serial-failure construct ownership vested in S6; no A3 parallel family permitted.

**Forbidden actions:**
  - run esx_serial_fuel in A3
  - run esx_episode_spacing in A3
  - run nth-fire ordinal family in A3

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_serial_fuel / esx_episode_spacing / nth-fire ordinal | **REJECTED — owned** | S6 Failed-Fire Fuel (registered species, phase0-PASSED OOS) owns the serial-failure construct; its pre-registered primary is the failed2×COILED interaction. A3 may not run a parallel family (RUL-11 spirit)

*Owner program: entry-stack*

### RUL-33-SUBTICKS

**REJECTED: esx_sub_x_ticks — unpowered (deep×ticks cell ~740 fires); NC-1 already ruled ticks**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** esx_sub_x_ticks is rejected as unpowered: deep×ticks>=1 cell is approximately 740 fires on deep. NC-1 already ruled the ticks main effect.

**Forbidden actions:**
  - register esx_sub_x_ticks as A3 family

**Source:** `research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md`
> esx_sub_x_ticks | **REJECTED — unpowered** | deep×ticks≥1 cell ≈ 740 fires on deep; NC-1 already ruled the ticks main effect

*Owner program: entry-stack*


### factor-intelligence

### FACTOR-U1

**Cross-job artifact writes invisible between jobs; nightly jobs do NOT share tree state**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Every daily.yml job does a fresh actions/checkout@v4 + git pull origin main. Jobs running in parallel cannot see uncommitted writes from sibling jobs. Runner-local writes are wiped by git clean -ffdx at the next job start. This structural fact makes any design relying on cross-job uncommitted artifact reads physically incoherent.

**Forbidden actions:**
  - design artifact flows that depend on cross-job uncommitted writes
  - assume parallel nightly jobs share filesystem state

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> Nightly jobs do NOT share tree state.** Every daily.yml job does a fresh `actions/checkout@v4` + `git pull origin main`.

*Owner program: factor-intelligence*

### FACTOR-U2

**factor_ops dispatch workflow: no push permitted; registration moved to nightly cortex job**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** After §E.1 diagnosis (all five dispatch registrations were lost due to cross-job hole), registration is moved inside the nightly cortex job. The factor_ops register actions are removed. A narrow factor_ops push was explicitly rejected because the nightly-sole-advancer law (FIX-1) forbids dispatch-workflow pushes. The cortex job runs register_factor_hypotheses before cortex deliberation.

**Forbidden actions:**
  - push from factor_ops dispatch workflow
  - run hypothesis registration outside nightly cortex job

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> **Fix (this PR): registration moved inside the nightly cortex job** — the option that keeps the nightly-sole-advancer law (FIX-1) intact; the factor_ops register actions are removed (a narrow factor_ops push was rejected: FIX-1 explicitly forbids dispatch-workflow pushes).

*Owner program: factor-intelligence*

### FACTOR-U4

**kernel_style.py shadow table and validate_factor harnesses deferred to P3**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** kernel_style.py shadow table is NOT in the current wave — it is a P3 deliverable per masterplan §5.1. validate_factor_h1-5 harnesses are NOT in the current wave — they are P3 and await the replay artifact. Committee per-ticker factor lane is NOT in this wave (deferred to P4 per RUL-NW8).

**Scope fence:** These deliverables are explicitly out of scope for the current (P2) wave.

**Forbidden actions:**
  - build kernel_style.py shadow table before P3
  - build validate_factor_h1-5 harnesses before P3

**Unblock condition:** P3 milestone; replay artifact must exist for validate harnesses.

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> Kernel_style.py shadow table: NOT in this wave (P3 deliverable, masterplan §5.1). validate_factor_h1-5 harnesses: NOT in this wave (P3, awaits replay artifact).

*Owner program: factor-intelligence*

### FACTOR-U5

**fire_coordinates.jsonl is PIT by construction; no replay edits permitted**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** fire_coordinates.jsonl records board-fire coordinates at the exact panel row at fire date. It is PIT by construction and keyed (ticker, date). Kill-list #7 (no replay edits) is respected — the artifact makes the study-time join durable even if the runner-local panel is ever wiped. Behavioral conditioning on this file is banned until the kernel-FDR 2026-10 sweep.

**Scope fence:** Display/analysis only until kernel-FDR 2026-10.

**Forbidden actions:**
  - edit fire_coordinates.jsonl rows retrospectively
  - condition behavior on fire_coordinates before kernel-FDR 2026-10

**Unblock condition:** kernel-FDR 2026-10 verdict.

**Come back on:** 2026-10-01

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> **`data/factordata/fire_coordinates.jsonl`** — for each current board buy-lane fire (all tiers the gate emits): (ticker, date, tier, dna_class, style_regime, alibi_share_20d, twin_bleed_flag, twin_rel_20d, alpha_z_house, top-3 Block-A contrib streams, factor_model:v1). PIT by construction (panel row at fire date).

*Owner program: factor-intelligence*

### FACTOR-U7

**PREREGISTRATION.md gates are locked; §0 vocabulary and thresholds untouchable**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The PREREGISTRATION.md lock clause activated at PR #1357's merge. All gates, §0 vocabulary, and thresholds in PREREGISTRATION.md are locked and may not be edited. This constraint is binding throughout all adjudication.

**Forbidden actions:**
  - edit §0 vocabulary in PREREGISTRATION.md
  - edit thresholds in PREREGISTRATION.md
  - edit gates in PREREGISTRATION.md

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> Constraint honored:** no locked gate moves. PREREGISTRATION.md (locked at PR #1357 merge) and the masterplan kill list are binding throughout.

*Owner program: factor-intelligence*

### RUL-NW1

**factor_panel job is sole committer of factor-namespace artifacts**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The Option A/B binary from the docket is rejected; Option A is physically incoherent (two-run stale, cross-job hole). The factor_panel nightly job builds and commits factor-namespace artifacts via a narrow, path-allowlisted commit/push step. The allowlist is exact: six named paths only. Nothing else may be committed by this step — never world_state.json, never any Article-2 path.

**Scope fence:** factor_panel job only; factor_ops dispatch workflow remains contents:read, no-push.

**Forbidden actions:**
  - commit world_state.json from factor_panel job
  - commit Article-2 paths from factor_panel job
  - push from factor_ops dispatch workflow

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> RULING: the **factor_panel job itself builds and commits the factor-namespace artifacts** via a narrow, path-allowlisted commit/push step. This is Option B, granted as a scoped sole-advancer.

*Owner program: factor-intelligence*

### RUL-NW10

**Three append-only accrual artifacts chartered; display/analysis-only until kernel-FDR 2026-10**

- Status: `adopted` | Kind: `data_contract` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** Three committed append-only factor-job-advanced artifacts are chartered: factor_state_history.jsonl (daily digest tape), fire_coordinates.jsonl (PIT board-fire coordinates keyed ticker×date), and factor_contradictions.jsonl (un-gitignored Pair G ledger). All three are display/analysis-only until the kernel-FDR 2026-10 sweep. Any code conditioning behavior on the pooled history before that verdict is a premature A5 promotion and is banned. Same-day re-runs must not duplicate rows.

**Scope fence:** Display/analysis-only until kernel-FDR 2026-10; no behavioral conditioning on pooled history before that sweep.

**Forbidden actions:**
  - condition behavior on pooled factor history before kernel-FDR 2026-10 verdict
  - promote factor pool artifacts to A5 before kernel-FDR sweep
  - duplicate rows in same-day re-runs

**Unblock condition:** kernel-FDR 2026-10 sweep completed with a verdict.

**Come back on:** 2026-10-01

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> All three are display/analysis-only until the kernel-FDR 2026-10 sweep; any code conditioning behavior on the pooled history before that verdict is a premature A5 promotion and is banned.

*Owner program: factor-intelligence*

### RUL-NW11

**Every factor artifact needs synapse.yml entry; factor modules forbidden from Article-2 paths**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Every new committed factor artifact gets a config/synapse.yml entry (producer = factor job script) and every new workflow step gets a config/dag.yml entry. scripts/check_factor_boundaries.py asserts factor modules never write Article-2 paths (alert_triage, board_ordering, top_setups, attention_queue, push_floor). Freshness/dormancy alerting lives in the admin card, not CI checks on world_state.json.

**Scope fence:** Factor modules may not write Article-2 paths.

**Forbidden actions:**
  - write alert_triage from factor modules
  - write board_ordering from factor modules
  - write top_setups from factor modules
  - write attention_queue from factor modules
  - write push_floor from factor modules
  - add factor artifact without synapse.yml entry

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> `scripts/check_factor_boundaries.py` additionally asserts factor modules never write Article-2 paths (`alert_triage`, `board_ordering`, `top_setups`, `attention_queue`, `push_floor`).

*Owner program: factor-intelligence*

### RUL-NW2

**world_state reads factor_intelligence_state.json as canonical source**

- Status: `adopted` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** _compose_factor_weather() reads data/neuralweb/factor_intelligence_state.json as canonical, with the direct panel read demoted to fallback-when-absent. The lobe gains a factor_state_as_of field so staleness is visible. Single-function-PR discipline per masterplan §6.3 applies.

**Scope fence:** One-run stale is acceptable for a slow de-escalation lobe.

**Forbidden actions:**
  - use runner-local panel as primary source for _compose_factor_weather

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> `_compose_factor_weather()` reads `data/neuralweb/factor_intelligence_state.json` as canonical (present in every fresh checkout, one-run stale — acceptable for a slow de-escalation lobe), with the direct panel read demoted to fallback-when-absent.

*Owner program: factor-intelligence*

### RUL-NW3

**Three cortex tools in v1; all read committed artifacts only**

- Status: `adopted` | Kind: `lobe` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Cortex v1 gets exactly three tools: read_factor_state, list_factor_contradictions, explain_factor_context. query_factor_attention is folded into read_factor_state. All three read COMMITTED artifacts only — never the runner-local panel. Tool outputs are capped and marked is_context_only: true (options-tools RO-7 precedent).

**Scope fence:** Read committed artifacts only; runner-local panel is forbidden as a tool source.

**Forbidden actions:**
  - read runner-local panel from cortex tools
  - add query_factor_attention as a separate tool

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> THREE in v1: `read_factor_state`, `list_factor_contradictions`, `explain_factor_context`. `query_factor_attention` is FOLDED into `read_factor_state` (the state artifact carries the attention track record). All three read COMMITTED artifacts only

*Owner program: factor-intelligence*

### RUL-NW4

**Ask-the-Brain factor path: read-only, directional verbs banned**

- Status: `adopted` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Factor integration into Ask-the-Brain is immediate, read-only, display-only. A string guard bans directional verbs (buy/sell/hold/add/trim and zh equivalents) in the factor-context answer path. Kill-list #6 (no folk regime priors) applies to customer-facing text verbatim.

**Scope fence:** Factor answers in Ask-the-Brain are read-only and display-only; no directional guidance.

**Forbidden actions:**
  - output directional verbs (buy/sell/hold/add/trim) in factor-context answer path
  - output folk regime priors in customer-facing factor text

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> A string guard bans directional verbs (buy/sell/hold/add/trim and zh equivalents) in the factor-context answer path — kill-list #6 (no folk regime priors) applies to customer-facing text verbatim.

*Owner program: factor-intelligence*

### RUL-NW6

**A3 activation floor: 25 episode-clustered events / 3 months + explicit Fable ruling**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** The shadow-ledger floor before any A3 de-escalation clamp wiring is: minimum 25 episode-clustered would-have-fired events spanning at least 3 calendar months (EI R6 convention), graded at the relevant hypothesis's own falsifier, THEN an explicit Fable ruling. Family BH is withheld until H4/H5 floors (~mid-2027) unless a family split is pre-registered before data is seen. Lane E ships as a thin dark scaffold that refuses to run without a GATE-PASSED verdict artifact.

**Scope fence:** No A3 clamp wiring before floor is cleared and Fable has ruled.

**Forbidden actions:**
  - wire A3 clamp before 25 episode-clustered events over 3 months
  - issue GATE-PASSED before family BH floor
  - run Lane E scaffold without GATE-PASSED verdict artifact

**Unblock condition:** 25 episode-clustered would-have-fired events over >=3 calendar months, graded at hypothesis falsifier, plus explicit Fable ruling.

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> Minimum **25 episode-clustered would-have-fired events spanning ≥3 calendar months** (EI R6 convention), graded at the relevant hypothesis's own falsifier, THEN an explicit Fable ruling before any clamp wiring.

*Owner program: factor-intelligence*

### RUL-NW7

**factors.html gains NW-integration status panel with BH-WITHHELD chip mandatory**

- Status: `adopted` | Kind: `context` | Nondelegable: `False`

**Ruling:** factors.html stays the expert research surface and gains a compact NW-integration status panel at the top after the header. Chip vocabulary is fixed: DISPLAY/SHADOW/ACCRUING/GATE-PASSED/NULL/DORMANT/PRE-FDR INTERIM/BH-WITHHELD. BH-WITHHELD chip is mandatory to prevent interim H1/H2 reads from being mistaken as actionable. The CI-sensitive validation word must never appear.

**Scope fence:** Display only; the CI-sensitive validation word is forbidden in factors.html.

**Forbidden actions:**
  - omit BH-WITHHELD chip from factors.html status panel
  - use the CI-sensitive validation word in factors.html

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> Chip vocabulary: `DISPLAY / SHADOW / ACCRUING / GATE-PASSED / NULL / DORMANT / PRE-FDR INTERIM / BH-WITHHELD` — the last one is mandatory (red-team finding: without it, an interim H1/H2 read could be mistaken for actionable before the family BH runs).

*Owner program: factor-intelligence*

### RUL-NW8

**Committee per-ticker factor lane deferred to P4; H status from state artifact only**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** The state artifact is the single source for hypothesis status. factors.html and admin render H status now. The committee per-ticker predictive lane is DEFERRED to P4 (masterplan §5.5). Building a rich predictive surface that renders PRE-FDR INTERIM/NULL for a year is scope theater.

**Scope fence:** Committee per-ticker factor lane: NOT in current wave.

**Forbidden actions:**
  - build committee per-ticker factor predictive lane before P4

**Unblock condition:** P4 milestone reached (masterplan §5.5).

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> **factors.html + admin render it now. The committee per-ticker predictive lane is DEFERRED to P4** (masterplan §5.5 already schedules it; building a rich predictive surface that renders `PRE-FDR INTERIM/NULL` for a year is scope theater).

*Owner program: factor-intelligence*

### RUL-NW9

**allowed_actions block is descriptive only; must never become a behavior wire**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The state artifact's allowed_actions block is DESCRIPTIVE self-documentation only, not a switch. A static guard (scripts/check_factor_boundaries.py) fails CI if any code outside the state builder and render/admin surfaces reads allowed_actions. Authority is granted only by graded probation via constitution.grant_authority — a boolean in JSON must never become a behavior wire.

**Scope fence:** allowed_actions is readable only by state builder and render/admin surfaces.

**Forbidden actions:**
  - wire behavior on allowed_actions boolean
  - read allowed_actions outside state builder and render/admin surfaces
  - grant authority via JSON flag instead of constitution.grant_authority

**Source:** `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`
> A static guard (`scripts/check_factor_boundaries.py`) fails CI if any code outside the state builder and render/admin surfaces reads `allowed_actions`. Authority is granted only by graded probation via `constitution.grant_authority` — a boolean in JSON must never become a behavior wire.

*Owner program: factor-intelligence*


### house-law

### HOUSE-U1

**Model routing: Fable main-loop only; no fan-out inheritance**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The main session may run Fable/Opus, but fan-outs must never inherit the frontier model. Every agent() call or Agent-tool spawn must pass an explicit model: param. Fable is restricted to the main loop for planning, adjudication, rulings, merges, and final synthesis only.

**Scope fence:** Applies to all workflow agent() spawns and Agent-tool invocations repo-wide.

**Forbidden actions:**
  - spawn fable-tier agents
  - let fan-outs inherit session model without explicit model: param
  - use sonnet for final adjudication
  - use haiku for anything needing judgment

**Source:** `CLAUDE.md`
> The main session may run a frontier model (Fable/Opus). **Never let fan-outs inherit it.** Workflow `agent()` calls and Agent-tool spawns inherit the session model unless you pass `model:` explicitly — under ultracode that silently burns frontier tokens on mechanical work. Route every spawn:

*Owner program: house-law*

### HOUSE-U2

**Model routing hook enforcement: guard denies unrouted spawns**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** A PreToolUse hook (model_routing_guard.py) is wired in settings.json and denies Agent/Task spawns without an explicit model, any fable spawn, and Workflow scripts whose agent() calls carry no model:/agentType routing. Model-pinned agent types builder (sonnet) and reviewer (opus) pass the guard without a model: param.

**Scope fence:** Enforced at tool-call boundary via PreToolUse hook for all Agent/Task/Workflow invocations.

**Forbidden actions:**
  - bypass model_routing_guard.py
  - spawn without explicit model or pinned agent type

**Source:** `CLAUDE.md`
> Enforcement: a PreToolUse hook (`.claude/hooks/model_routing_guard.py`, wired in `.claude/settings.json`) denies Agent/Task spawns without an explicit model, any `fable` spawn, and Workflow scripts whose `agent()` calls carry no `model:`/`agentType` routing.

*Owner program: house-law*

### HOUSE-U3

**Git law: fresh origin/main branch, same-day squash-merge, no bare stash**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** All branches must be cut from fresh origin/main; squash-merged branches must never be reused. The complete workflow is commit → push → PR → same-day squash-merge. The stash stack is repo-global so bare git stash/pop is forbidden. Work must be done in worktrees and must never touch the main checkout's git state.

**Scope fence:** Applies to all contributors and agents working in this repo.

**Forbidden actions:**
  - reuse squash-merged branch
  - bare git stash or pop
  - touch main checkout git state
  - work outside worktrees

**Source:** `CLAUDE.md`
> branch off **fresh `origin/main`** (never reuse a squash-merged branch); finish via commit → push → PR → same-day squash-merge. Stash stack is repo-global — never bare `git stash`/`pop`. Main checkout is often occupied by other agents; work in worktrees, never touch main checkout's git state.

*Owner program: house-law*

### HOUSE-U4

**Epistemics: display-only until gauntleted; LLMs de-escalate only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** All signals are display-only until gauntleted. Pre-registered gates are required before claims are published. Nulls must be printed and not hidden. LLMs may only de-escalate calibrated keys and are forbidden from originating signals, scores, or escalations.

**Scope fence:** Display-only until gauntleted; no ranked-output consumer before pre-registered gate passes.

**Forbidden actions:**
  - originate signals
  - originate scores
  - originate escalations
  - hide null results
  - use the word 'validated' in user-facing text without CI-enforced gate

**Unblock condition:** Pass gauntlet; register gate before publishing.

**Source:** `CLAUDE.md`
> display-only until gauntleted; pre-registered gates; nulls are printed, not hidden. The word "validated" in user-facing text is CI-enforced (`scripts/check_validated_claims.py`). LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations.

*Owner program: house-law*

### HOUSE-U5

**Ledger law: nightly is sole advancer of forward ledgers**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** The nightly pipeline is the sole entity permitted to advance forward ledgers. Intraday lanes must discard all data/ writes and are forbidden from persisting ledger state.

**Scope fence:** Applies to all intraday lanes and non-nightly pipeline processes.

**Forbidden actions:**
  - intraday lane writes to data/
  - non-nightly advancement of forward ledgers

**Source:** `CLAUDE.md`
> nightly is the sole advancer of forward ledgers; intraday lanes discard `data/` writes.

*Owner program: house-law*

### HOUSE-U6

**Render budget is law: ~67 min, 4-core-bound; heavy compute off render path**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** The nightly render budget is approximately 67 minutes on a 4-core-bound Mac Studio runner, and this budget is law. Heavy compute must go off the render path with artifacts sent to R2. No compute-heavy additions may be placed on the nightly render path.

**Scope fence:** Applies to all nightly pipeline additions and engine modifications.

**Forbidden actions:**
  - place heavy compute on render path
  - exceed 67-minute render budget

**Source:** `CLAUDE.md`
> render budget is law (~67 min, 4-core-bound) — heavy compute goes off the render path, artifacts to R2.

*Owner program: house-law*


### long-hold

### NWP-U15

**Long-hold G1 FDR family frozen as 'long_hold'; sub-scope in exp_id only**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** BH-FDR across the 9-feature G1 family uses the frozen registered family fdr_family='long_hold' exactly as OBJECTIVE.md §6.1 locks it. The g1_v1 sub-scope lives in the exp_id/reason metadata only, never the family string. TrialLedger keys on exact strings; sub-family strings would create isolated testing islands.

**Scope fence:** Long-hold G1 kill-test study and any future long-hold family study.

**Forbidden actions:**
  - use fdr_family='long_hold.g1_v1' or any sub-family string
  - change registered family string without OBJECTIVE.md amendment

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> BH-FDR across the 9-feature family under the **frozen registered family `fdr_family='long_hold'` exactly as OBJECTIVE.md §6.1 locks it** (the g1_v1 sub-scope lives in the exp_id/reason metadata only, never the family string — TrialLedger keys on exact strings)

*Owner program: long-hold*

### NWP-U16

**Long-hold G1 OOS split frozen: 2020-01-01 to 2023-12-31, opened once**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** The OOS split is the frozen boundary per OBJECTIVE.md §7: fire dates 2020-01-01 through 2023-12-31, opened once. The harness computes and prints the achieved honest-OOS fire and episode-cluster counts BEFORE running any OOS statistic. No sample figures are asserted in advance by this document.

**Scope fence:** Long-hold G1 study; OOS split may not be reopened or re-cut.

**Forbidden actions:**
  - reopen OOS split
  - run OOS statistic before printing achieved honest-OOS fire and cluster counts
  - assert sample figures in advance

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> the OOS split is the **frozen boundary per OBJECTIVE.md §7 — fire dates 2020-01-01 through 2023-12-31, opened once**. The honest-cohort intersection within it (~2021-07-06→2021-10-25, per OBJECTIVE §8) is expected to be thin. **The harness computes and PRINTS the achieved honest-OOS fire and episode-cluster counts BEFORE running any OOS statistic**

*Owner program: long-hold*

### GAP-U13

**Holdable-winner replay deferred to long-hold program**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** B/HOLDABLE_WINNER (replay on missed_hold vs tactical_only) is deferred; the long-hold program owns it (A2 roster registered, 29 families). A replay variant may only be built after honest-cohort maturity of the long-hold A2 register.

**Scope fence:** No holdable-winner replay until long-hold A2 roster matures.

**Forbidden actions:**
  - run holdable-winner replay before long-hold A2 honest-cohort maturity

**Unblock condition:** Long-hold A2 roster reaches honest-cohort maturity.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Long-hold program owns this (A2 roster registered, Σ=29); replay variant only after honest-cohort maturity

*Owner program: long-hold*

### GAP-U2

**Repair-stack study killed — FDR double-dip on frozen G1 F1**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** The B2_REPAIR_STACK study is killed because it duplicates long-hold G1's registered F1 family, which is deferred to ~2027-H2. Re-testing would constitute an FDR double-dip and re-litigate a frozen deferral. This verdict is cross-program.

**Forbidden actions:**
  - run repair-stack study
  - re-test G1 F1 family before 2027-H2

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Duplicates G1 F1 (registered, DEFERRED ~2027-H2). Re-test = FDR double-dip + re-litigating a deferral

*Owner program: long-hold*

### DT-R6

**Big-leader composite gate forbidden; concentration_passport cut**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The big_leader_core_eligible composite gate is FORBIDDEN (LH-R2: no fused admission verdicts). concentration_passport is CUT (hold-book overlap; would be a 4th passport object). right_tail_theme_membership is REJECTED: theme momentum IC≈0 and defining eligibility from past winners formalizes survivorship into a feature. leader_liquidity_pass and survivable_drawdown_capacity may only enter as an LH roster amendment (Sigma<=40 ceiling, before A2 freeze).

**Forbidden actions:**
  - build big_leader_core_eligible composite
  - build concentration_passport
  - build right_tail_theme_membership eligibility
  - fuse admission verdicts

**Unblock condition:** leader_liquidity_pass and survivable_drawdown_capacity only via LH roster amendment with mechanism + prereg, Sigma<=40, before A2 freeze.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R6 (big-leader eligibility).** The composite gate is FORBIDDEN (LH-R2: no fused admission verdicts). `concentration_passport` is already CUT

*Owner program: long-hold*

### DT-U8

**leader_liquidity_pass and survivable_drawdown_capacity only via LH roster amendment**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** leader_liquidity_pass and survivable_drawdown_capacity are NOT registered now; they may only enter as an LH roster amendment (mechanism + prereg, Sigma<=40 ceiling, before the A2 freeze).

**Forbidden actions:**
  - register leader_liquidity_pass outside LH roster amendment process
  - add survivable_drawdown_capacity without mechanism + prereg

**Unblock condition:** LH roster amendment path: mechanism + prereg required; Sigma<=40 ceiling; before A2 freeze.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> `leader_liquidity_pass` / `survivable_drawdown_capacity` are NOT registered now; they may only enter as an LH roster amendment (mechanism + prereg, Σ≤40 ceiling, before the A2 freeze).

*Owner program: long-hold*


### long-hold-thesis

### TOP3-L2

**L2 multi-family FDR battery: KILL as duplicate; OOS freeze-anchor script adopted**

- Status: `residue_adopted` | Kind: `study` | Nondelegable: `True`

**Ruling:** LH-R11 (HLZ/BH q=0.10) and A2 roster (Σ=29 ≤ 40) are already ratified. Running the battery now would violate the A2 §4 contact-freeze. The one missing artifact — the A2 OOS-analysis script — is built now with a hard no-run-until-floor gate; committing it satisfies LH-R11.1 and locks the roster before any outcome contact.

**Forbidden actions:**
  - run FDR battery before honest compounder clusters ≥25
  - contact 2024+ cohort before A2 freeze lifts

**Unblock condition:** Honest compounder clusters ≥25 + operator flag triggers the OOS analysis script run.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **L2** multi-family FDR battery | **KILL as duplicate; salvage one artifact (BUILD NOW)** | LH-R11 (program-wide HLZ/BH q=0.10 as sole ratifying correction) + A2 roster (F1 m=9, F2 m=10, F3 m=7, F4 m=3, Σ=29 ≤ 40) are already ratified — L2 restates them. Running the battery now would VIOLATE the A2 §4 contact-freeze.

*Owner program: long-hold-thesis*

### TOP3-L3

**L3 thesis-transition ledger: DEFER — W3-locked until G1 non-null**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The thesis-transition ledger design is already law (LH-R6 deterministic tripwires only / LH-R7 nightly sole advancer / W3 PR-M) and W3 is LOCKED until G1 non-null. Three amendments are recorded for the unlock: (a) all tripwire thresholds pre-registered outcome-blind; (b) PIT-strict firing with exclusions logged; (c) firewall assertion scored_path_surfaces=[], no confidence numbers on transition stamps.

**Scope fence:** No build, no display surface until G1 non-null (~2027-H2).

**Forbidden actions:**
  - build thesis-transition ledger before G1 non-null
  - use expectation/insider tripwires before outcome-blind pre-registration
  - publish confidence numbers on transition stamps

**Unblock condition:** G1 non-null (honest compounder clusters ≥25, ~2027-H2) unlocks W3.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **L3** thesis-transition ledger | **DEFER — W3-locked; design amendments recorded** | The design is already law (LH-R6 deterministic tripwires only / LH-R7 nightly sole advancer / W3 PR-M) and W3 is LOCKED until G1 non-null.

*Owner program: long-hold-thesis*

### TOP3-L5

**L5 analogue explainer: DEFER post-G1; as written is D-7 violation**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** L5 is deferred to post-G1 (~2027-H2) because as written it violates D-7: 'Confidence capped by label rarity' is a model-authored confidence number. Nearest-neighbor on 195 survivor-tinted positives makes the distance metric an un-gauntleted model choice and constitutes behaviorally potent anchoring. Any pre-G1 work must be research-tier, frozen-metric prereg, deterministic retrieval, no display surface.

**Scope fence:** No display surface pre-G1; any pre-G1 work = research-tier only, no display.

**Forbidden actions:**
  - publish analogue card with confidence number pre-G1
  - use nearest-neighbor distance metric without gauntlet
  - display analogue compounders pre-G1

**Unblock condition:** G1 non-null (~2027-H2) + deterministic retrieval + D-7-compliant design.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **L5** analogue explainer | **DEFER to post-G1 (~2027-H2); as written it is illegal** | "Confidence capped by label rarity" is a model-authored confidence number — the exact D-7 killed pattern (Wilson bounds from graded history or no number).

*Owner program: long-hold-thesis*

### TOP3-M7

**M7 compounder proxy label: KILL — wrong-ruler, validates against same latency-bound store**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** The compounder proxy label is killed as wrong-ruler. The objective wall is absolute: any proxy validates against the same latency-bound 195-label store it claims to bypass. No proxy label build is permitted.

**Forbidden actions:**
  - build compounder proxy label
  - use proxy to bypass 195-label latency-bound store

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **M7 — compounder proxy label: KILL** (wrong-ruler; OBJECTIVE §9 "the wall is absolute"; any proxy validates against the same latency-bound 195-label store it claims to bypass).

*Owner program: long-hold-thesis*

### NEXTL-U1

**Long-Term Thesis lobe KILL: duplicates chartered long-hold program**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Lobe #4 (Long-Term Thesis / Expectations-Drift) is killed as a charter because it duplicates the chartered, mostly-shipped long-hold thesis program. LT-THESIS-1=G1 (run+DEFERRED), LT-THESIS-2=F3 (SUE live), LT-THESIS-3=moat_falsifiers+A2 falsifiers. Nothing here re-tests or re-charters this territory.

**Scope fence:** All thesis-layer work routes to the long-hold program amendment process, not here.

**Forbidden actions:**
  - charter Long-Term Thesis as a new lobe
  - build thesis-lobe waves outside long-hold program
  - re-test G1 or F3 under this program

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> | 4 | Long-Term Thesis / Expectations-Drift | **KILL** (as charter) | existing-program work | Duplicates the chartered, mostly-shipped long-hold thesis program (G1 run+DEFERRED; F3 Ruler-P run; A2 roster frozen Σ=29 of 40 ceiling).

*Owner program: long-hold-thesis*

### NEXTL-U10

**Reverse-DCF card routed to long-hold program W3; not built here**

- Status: `no_build` | Kind: `study` | Nondelegable: `False`

**Ruling:** The reverse-DCF 'what must be true' card is genuinely unbuilt and computable on ~785 names. It is routed as a recommendation to the long-hold program's amendment process (their W3 lock is theirs to lift). It is NOT built in this program.

**Scope fence:** No-build in this program; long-hold program W3 amendment required.

**Forbidden actions:**
  - build reverse-DCF card outside long-hold program
  - treat reverse-DCF as this program's deliverable

**Unblock condition:** Long-hold program W3 lock lifted via amendment process

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> the **reverse-DCF "what must be true" card** (W3 PR-N) is genuinely unbuilt and computable on ~785 names — routed as a recommendation to the long-hold program's amendment process (its W3 lock is theirs to lift), NOT built here.

*Owner program: long-hold-thesis*

### NEXTL-U7

**F-HZ-2 deferred to A2 G1-Retest clock (~2027-H2)**

- Status: `deferred` | Kind: `study` | Nondelegable: `True`

**Ruling:** F-HZ-2 (the A2 G1-Retest arm) is deferred to the frozen A2 G1-Retest clock (~2027-H2). Running it now would double-dip fdr_family='long_hold' (frozen). This program does not build F-HZ-2.

**Forbidden actions:**
  - run F-HZ-2 before A2 G1-Retest clock
  - assign F-HZ-2 to fdr_family='long_hold'

**Unblock condition:** A2 G1-Retest clock reached (~2027-H2)

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> F-HZ-2 = the frozen A2 G1-Retest (~2027-H2) — re-running it would double-dip `fdr_family='long_hold'`.

*Owner program: long-hold-thesis*

### LH-R1

**Horizon firewall: bidirectional CI-enforced entry/hold separation**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** config/synapse.yml gains a horizon_role field stamped on every registered artifact. check_synapse_reads.py hard-fails any hold_thesis artifact consumed by an entry Article-2 surface and vice versa. The firewall is bidirectional and CI-enforced, not documentary.

**Scope fence:** Applies to every registered artifact in config/synapse.yml repo-wide.

**Forbidden actions:**
  - consume hold_thesis artifact on entry board/alert/push surface
  - consume tactical_entry artifact on hold surface

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> The firewall is bidirectional and CI-enforced, not documentary.

*Owner program: long-hold-thesis*

### LH-R10

**Species coordination: expectation-drift coordinates with S9; trap detector is de-escalation only**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** Expectation-drift / bad-news-resilience work must coordinate with already-registered species S9 (post-event absorption) rather than duplicating it. The great-company-trap detector is not new alpha — it is a de-escalation overlay assembled from existing signals (crowding, insider, revisions), display-only, and may only lower conviction.

**Scope fence:** Great-company-trap detector is display-only and de-escalation only; may not raise conviction.

**Forbidden actions:**
  - originate new expectation-drift species duplicating S9
  - allow great-company-trap detector to raise conviction

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> The great-company-trap detector is not new alpha — it is a de-escalation overlay assembled from existing signals (crowding, insider, revisions), display-only, may only lower conviction.

*Owner program: long-hold-thesis*

### LH-R11

**Multi-family roster: frozen pre-registered with HLZ/BH-FDR q=0.10 as sole ratifying correction**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** A fixed pre-registered roster of at-entry families tests missed_hold; the freeze anchor is the commit of the A2 OOS-analysis script. Program-wide HLZ/BH-FDR q=0.10 over all registered hypotheses is the sole ratifying correction (within-family q is descriptive; reshuffle null orthogonal). Per-feature admissibility requires restricted_range and feature_provenance stamps. The washout-timeframe family is admitted as family #2.

**Forbidden actions:**
  - modify roster after freeze-anchor commit without amendment
  - treat within-family q as ratifying correction

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> Fixed pre-registered roster of at-entry families testing `missed_hold`; freeze anchor = the commit of the A2 OOS-analysis script; DEFERRED left the roster window open; program-wide HLZ/BH-FDR q=0.10 over Σ registered hypotheses is the sole ratifying correction

*Owner program: long-hold-thesis*

### LH-R12

**Program hypothesis ceiling: Σ registered hypotheses ≤ 40 across all long_hold families**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Sigma registered hypotheses across all long_hold roster families must not exceed 40. Additions beyond the ceiling require dropping registered hypotheses by formal amendment. After Amendment A2 registration the count is 29.

**Scope fence:** All long_hold FDR family registrations.

**Forbidden actions:**
  - register hypothesis that would push Σ above 40 without dropping another

**Unblock condition:** A registered hypothesis is formally dropped by amendment before adding.

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> Σ registered hypotheses across all long_hold roster families ≤ 40. Additions beyond the ceiling require dropping registered hypotheses by amendment. Σ after Amendment A2 registration: 29.

*Owner program: long-hold-thesis*

### LH-R14

**Two-ruler discipline: Ruler-P display-only; Ruler-H is sole ratifying ruler**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Each roster family declares exactly two rulers: Ruler-P (cheap_trap vs tactical_only at 252d, fires ≤2023-12-31, survivorship-stamped, authority ceiling = display) and Ruler-H (missed_hold on OOS-2 at G1-Retest under program-wide FDR). Ruler-P can never produce SURVIVE/KILL for the selection-alpha thesis.

**Scope fence:** Ruler-P is display-only; Ruler-H is the sole ratifying ruler for selection alpha.

**Forbidden actions:**
  - allow Ruler-P to produce SURVIVE verdict for selection-alpha thesis
  - allow Ruler-P to produce KILL verdict for selection-alpha thesis
  - declare a family with fewer or more than two rulers

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> Ruler-P can never produce SURVIVE/KILL for the selection-alpha thesis.

*Owner program: long-hold-thesis*

### LH-R2

**No fused admission: AND-gate of independent flags only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No single verdict may combine entry state + fundamentals + ownership + expectation drift. Admission to thesis tracking must be a transparent AND-gate of independently registered display flags (S15+). Any future composite must beat equal-weight sector-neutral z-mean OOS before display and clear Article 2 before behavioral use.

**Scope fence:** Applies to all long-hold thesis admission logic.

**Forbidden actions:**
  - combine entry state + fundamentals + ownership + expectation drift in a single verdict
  - display composite before OOS composite_score.py beat
  - use composite for behavioral surface before Article 2 clearance

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> No single verdict may combine entry state + fundamentals + ownership + expectation drift. Admission to thesis tracking is a transparent AND-gate of independently registered display flags, registered as a species (S15+) through the existing PREREG ladder.

*Owner program: long-hold-thesis*

### LH-R3

**Survivorship stamps: 756d refused as headline; UPPER BOUND on survivor-only**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** Every long-horizon artifact carries survivorship_biased and dead-name coverage_frac fields. 756d results are refused as headline numbers until a dead-name price store exists. Survivor-only results ship stamped UPPER BOUND. Honest cohorts are post-2021-07 Massive ≤252d and the 2025-2026 cohort.

**Scope fence:** All long-horizon artifacts and outcome labels.

**Forbidden actions:**
  - publish 756d results as headline without dead-name price store
  - omit survivorship_biased field from long-horizon artifact
  - omit coverage_frac field from long-horizon artifact

**Unblock condition:** dead_name_prices.parquet populated for the 1,083-name dead universe (W1 PR-G feasibility memo first).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> 756d results are **refused as headline numbers** until a dead-name price store exists. Honest cohorts for outcome claims: post-2021-07 Massive ≤252d; 2025-2026 cohort. Survivor-only results ship stamped "UPPER BOUND".

*Owner program: long-hold-thesis*

### LH-R4

**Effective-n discipline: n≥25 episode-clusters; block-bootstrap CIs required**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Raw fire counts are banned as inferential n. Every statistic must carry cluster-robust / block-bootstrap CIs on (name × macro-regime) blocks. Per-horizon minimum floor is n ≥ 25 independent episode-clusters (matches Article-3). Overlapping-window autocorrelation must be handled by episode-blocking, not ignored.

**Scope fence:** All long-hold inferential statistics.

**Forbidden actions:**
  - use raw fire counts as inferential n
  - ignore overlapping-window autocorrelation
  - report statistics without cluster-robust CIs

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> Raw fire counts are banned as inferential n. Every statistic carries cluster-robust / block-bootstrap CIs on (name × macro-regime) blocks; per-horizon minimum floor: **n ≥ 25 independent episode-clusters** (matches Article-3).

*Owner program: long-hold-thesis*

### LH-R5

**FDR isolation: long_hold family isolated from entry desk FDR batches**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** All long-hold claims must register under dedicated fdr_family='long_hold' with its own quarterly batch. A test asserts no long_hold key appears in any entry desk's FDR grouping.

**Forbidden actions:**
  - register long-hold claim under entry desk FDR family
  - mix long_hold keys with cortex or entry FDR batches

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> All long-hold claims register under dedicated `fdr_family='long_hold'` with its own quarterly batch. A test asserts no long_hold key appears in any entry desk's FDR grouping.

*Owner program: long-hold-thesis*

### LH-R6

**LLM law: transitions by tripwires only; LLM is commentary not the transition**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Thesis status transitions (watch → active → challenged → falsified) are fired ONLY by deterministic falsifier tripwires; the transition write is an append-only governance event. LLM output is provenance-stamped commentary bound to the machine event id, never the transition itself, never a hold/trim verdict. 'Reason to hold' framing is dead; the ledger records evidence that would BREAK a thesis.

**Scope fence:** Thesis ledger state machine; LLM role on all long-hold surfaces.

**Forbidden actions:**
  - allow LLM to fire thesis status transition
  - allow LLM to produce a hold verdict
  - allow LLM to produce a trim verdict
  - use 'reason to hold' framing in ledger

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> LLM output is provenance-stamped commentary bound to the machine event id — never the transition itself, never a hold/trim verdict. "Reason to hold" framing is dead; the ledger records evidence that would BREAK a thesis.

*Owner program: long-hold-thesis*

### LH-R7

**Ledger law: thesis ledger and label store are forward ledgers; nightly sole advancer**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The thesis ledger and long-horizon label store are forward ledgers where nightly is sole advancer. The quarterly review scheduler is a workflow_dispatch that writes runner-local and rides the next ENGINE git-add; a workflow-lint check asserts no git push in it. The live qledger's GRADE_HORIZONS are untouched.

**Scope fence:** Thesis ledger, long-horizon label store, and any quarterly review workflow.

**Forbidden actions:**
  - push to git from quarterly review workflow
  - advance forward ledger outside nightly job
  - modify GRADE_HORIZONS in live qledger

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> The thesis ledger and long-horizon label store are forward ledgers → nightly is sole advancer. The quarterly review scheduler is a workflow_dispatch that writes runner-local and rides the next ENGINE git-add; a workflow-lint check asserts no `git push` in it.

*Owner program: long-hold-thesis*

### LH-R8

**Kernel clock: no long-hold feature on kernel before 2026-10-01**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No long-hold feature may condition on kernel estimates before the 2026-10-01 decision batch (Signal Commons R1). This is a hard date fence, not a preference.

**Scope fence:** Any long-hold feature using kernel estimates.

**Forbidden actions:**
  - condition long-hold feature on kernel estimates before 2026-10-01

**Unblock condition:** 2026-10-01 decision batch (Signal Commons R1) passes.

**Come back on:** 2026-10-01 (experiment: `neuralweb-kernel-q1-batch`)

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> No long-hold feature conditions on kernel estimates before the 2026-10-01 decision batch (Signal Commons R1).

*Owner program: long-hold-thesis*

### LH-U1

**Behavioral surface floor: no long-horizon key on behavioral surface before ~2028-2029**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A0_OBSERVE`

**Ruling:** Under Article 2/3 (SHADOW-with-track-record, n≥25 episode-clusters, Wilson-CI gate), no long-horizon key can influence any behavioral surface before ~2028-2029. This program is chartered knowing that.

**Scope fence:** All long-horizon keys are barred from behavioral surfaces until Article 2/3 gates are met.

**Forbidden actions:**
  - allow long-horizon key to influence behavioral surface before Article 2/3 clearance

**Unblock condition:** n≥25 episode-clusters accrued and Wilson-CI gate passes under Article 2/3 (projected ~2028-2029).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> no long-horizon key can influence any behavioral surface before ~2028-2029. This program is chartered knowing that.

*Owner program: long-hold-thesis*

### LH-U10

**Deferred: reverse-DCF / valuation expectations to W3; v1 EV/sales only**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** Reverse-DCF and valuation-implied expectations are deferred to W3 with v1 limited to EV/sales only. EBITDA-multiple paths are data-blocked because depreciation was never collected from EDGAR. Everything needing EBIT/EBITDA multiples or consensus stays deferred.

**Scope fence:** When built: display-only EV/sales implied growth card only.

**Forbidden actions:**
  - build EBITDA-multiple reverse-DCF before depreciation collected from EDGAR
  - use consensus estimates in reverse-DCF card

**Unblock condition:** W3 gate opens AND depreciation added to edgar_facts.py FLOW dict (W2 PR-H).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | Reverse-DCF / valuation-implied expectations (§5.6) | **DEFER to W3, v1 = EV/sales only** | EBITDA-multiple paths data-blocked (depreciation never collected from EDGAR) |

*Owner program: long-hold-thesis*

### LH-U11

**Cut: universe-scale KPI registry — blocked by SKIP-ALL paid feeds**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** The universe-scale KPI registry is cut, MVP deferred behind W3 gate. The highest-value sources are the exact paid feeds ruled SKIP-ALL. It may not be built until paid-data re-buy is approved.

**Forbidden actions:**
  - build universe-scale KPI registry under current SKIP-ALL constraint

**Unblock condition:** Paid-data re-buy trigger approved AND W3 gate opens.

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | Universe-scale KPI registry (§5.8) | **CUT** (MVP deferred behind W3 gate) | High-value sources are the exact paid feeds ruled SKIP-ALL |

*Owner program: long-hold-thesis*

### LH-U12

**756d label kill: refused as headline; 504d also caveated**

- Status: `killed` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** 756d (and headline 504d) outcome labels are killed as headline labels because they are survivorship-crippled. They are permitted only caveat-stamped. This is a Fable-unanimous ratified verdict.

**Scope fence:** No 756d headline labels; 504d only caveat-stamped.

**Forbidden actions:**
  - publish 756d outcome labels as headline results
  - publish 504d outcome labels without survivorship caveat

**Unblock condition:** dead_name_prices.parquet populated with the full 1,083-name dead universe.

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | 756d (and headline 504d) outcome labels (§6.1) | **KILL as headline labels** | Survivorship-crippled (see §2). Permitted only caveat-stamped |

*Owner program: long-hold-thesis*

### LH-U13

**Deferred: 504/756d headline base rates pending dead-name spike**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** Any 504/756d headline base rate, pre-2021 cohort studies, and survivorship-honest cheap-trap rates are deferred behind the dead-name spike (W1 PR-G feasibility memo). They may not be reported until the dead-name price store is populated.

**Forbidden actions:**
  - report 504/756d base rates before dead-name price store exists
  - report pre-2021 cohort studies without survivorship correction

**Unblock condition:** dead_name_prices.parquet populated via ThetaData or Polygon flatfiles (PR-G feasibility memo).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> **Deferred behind the dead-name spike (W1 PR-G):** any 504/756d headline base rate; pre-2021 cohort studies; survivorship-honest cheap-trap rates.

*Owner program: long-hold-thesis*

### LH-U14

**G1-Retest deferred: W1 non-null gating W3/W4 projected ~2027-H2**

- Status: `deferred` | Kind: `study` | Nondelegable: `True`

**Ruling:** G1 was ruled DEFERRED 2026-07-06 due to window-driven n-floor failure (4 honest compounder clusters vs ≥25). G1-Retest uses Amendment A2 with 2025+ honest cohort. W3/W4 remain locked. W2 authorized display-only. PR-H EDGAR FLOW additions are retest-critical.

**Scope fence:** W2 display-only allowed; W3/W4 blocked until retest.

**Forbidden actions:**
  - treat G1 deferred ruling as a pass for W3/W4 purposes

**Unblock condition:** Amendment A2 cohort (2025+ honest data) reaches n≥25 episode-clusters, projected ~2027-H2.

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> G1-RETEST (Amendment A2, 2025+ honest cohort) projected evaluable ~2027-H2. Full ruling: research/long_hold/W1_KILLTEST_RESULTS.md §12.

*Owner program: long-hold-thesis*

### LH-U2

**Kill: Compounder Admission Test single verdict (fused composite) — forbidden**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** The Compounder Admission Test as a single fused verdict is killed as designed. It is a forbidden fused-escalating-composite per Signal Commons R3 / FR-1. It must be rebuilt as an AND-gate of independently registered flags via the species ladder.

**Forbidden actions:**
  - build Compounder Admission Test as a single verdict
  - create fused escalating composite for admission

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | Compounder Admission Test single verdict (§5.1) | **KILL as designed** | Forbidden fused-escalating-composite (Signal Commons R3 / FR-1). Rebuilt as AND-gate of independently registered flags via species ladder |

*Owner program: long-hold-thesis*

### LH-U3

**Kill: kernel 12-36m outcome learning as forward loop**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** "Let the kernel learn 12-36m outcomes" is killed as a forward loop. It yields approximately 1 obs/name/yr maturing 3 years late, a decade-scale promise. It is replaced by a pre-registered pooled historical study.

**Forbidden actions:**
  - add 12-36m outcomes to kernel forward loop
  - train kernel on long-horizon outcomes in near-term

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | "Let the kernel learn 12-36m outcomes" (§10) | **KILL as forward loop** | ~1 obs/name/yr maturing 3y late = decade-scale promise. Replaced by pre-registered pooled historical study |

*Owner program: long-hold-thesis*

### LH-U4

**Cut: theme-cashflow-transmission graph — no supplier/customer graph, SKIP-ALL data**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** The theme-cashflow-transmission per-ticker graph is cut permanently. No supplier/customer graph exists anywhere in the repo; it requires paid supply-chain data ruled SKIP-ALL (2026-07-05); theme momentum rank-IC ≈ 0.

**Forbidden actions:**
  - build theme-cashflow-transmission graph
  - use supply-chain paid data for this feature

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | Theme-cashflow-transmission graph (§5.9) | **CUT** | No supplier/customer graph exists anywhere in the repo; requires paid supply-chain data (SKIP-ALL ruling 2026-07-05); theme momentum rank-IC ≈ 0 |

*Owner program: long-hold-thesis*

### LH-U5

**Cut: hold-book risk/overlap view — belongs to unchartered portfolio-construction program**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** The hold-book risk/overlap view is cut. It belongs to an unchartered portfolio-construction program and may not be built under the long-hold-thesis program.

**Forbidden actions:**
  - build hold-book risk or overlap view under long-hold program

**Unblock condition:** A portfolio-construction program is chartered.

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | Hold-book risk/overlap view (§6.6) | **CUT** | Belongs to an unchartered portfolio-construction program |

*Owner program: long-hold-thesis*

### LH-U6

**Cut: live qledger multi-year extension — GRADE_HORIZONS stays (5,21,63)**

- Status: `no_build` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The live qledger's GRADE_HORIZONS are untouched at (5,21,63). Multi-year open claims in the nightly grader are forbidden. A separate off-render research grader is used instead for 252d+ horizons.

**Scope fence:** Live nightly qledger grader only; off-render research grader may use extended horizons.

**Forbidden actions:**
  - extend GRADE_HORIZONS beyond 63d in live nightly grader
  - add multi-year claims to nightly qledger

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> `GRADE_HORIZONS=(5,21,63)` stays; multi-year open claims in the nightly grader forbidden; separate off-render research grader instead

*Owner program: long-hold-thesis*

### LH-U7

**G1 kill criterion: selection-alpha killed if no family survives FDR on honest cohorts**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** If no at-entry feature family survives FDR on the honest cohorts, the selection-alpha thesis is KILLED; W3/W4 are cancelled; the program collapses to W0 discipline + W2 clocks/falsifiers. A null must be examined for survivorship mechanics before ratification (missing dead names understate the trap class), then printed loudly.

**Forbidden actions:**
  - proceed to W3 or W4 if G1 kill criterion triggers
  - suppress a null G1 result

**Unblock condition:** At-entry feature family survives FDR on honest cohorts (G1-Retest projected ~2027-H2).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> if no at-entry feature family survives FDR on the honest cohorts, the selection-alpha thesis is KILLED; W3/W4 are cancelled; the program collapses to W0 discipline + W2 clocks/falsifiers.

*Owner program: long-hold-thesis*

### LH-U8

**W3/W4 locked: both waves locked pending G1-Retest non-null result**

- Status: `blocked` | Kind: `wave` | Nondelegable: `True`

**Ruling:** W3 (thesis ledger + species) and W4 (committee surface) are LOCKED and may not proceed until G1-Retest returns a non-null result under program-wide FDR. W2 authorized display-only regardless of G1. W3/W4 locks are unchanged even after LT external foundation and A2 registration.

**Scope fence:** W3 and W4 build activity is fully blocked.

**Forbidden actions:**
  - build W3 species S15+ prereg before G1-Retest non-null
  - build W4 committee surface before W3 operates one clean quarter

**Unblock condition:** G1-Retest returns non-null result under program-wide FDR (projected ~2027-H2).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> **G1 RULED: DEFERRED** (window-driven n-floor failure: 4 honest compounder clusters vs ≥25; piotroski_f separation consistent but survivorship-caveated in every floor-met split). W3/W4 LOCKED.

*Owner program: long-hold-thesis*

### LH-U9

**Deferred: thesis ledger to W3 only; 'reason to hold' framing killed**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The thesis ledger is deferred to W3 and reshaped: only deterministic tripwire-fired transitions, 'reason to hold' framing is killed (Article 1), and it is built only after W1 is non-null. Currently W3 is locked, so the ledger is effectively blocked.

**Scope fence:** Display and research tier only when eventually built.

**Forbidden actions:**
  - build thesis ledger before W3 gate opens
  - include 'reason to hold' framing in ledger

**Unblock condition:** W3 gate opens (requires G1-Retest non-null).

**Source:** `research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md`
> | Thesis ledger (§5.10) | **DEFER to W3, reshaped** | Deterministic tripwire-fired transitions only; "reason to hold" framing killed (Article 1); built only after W1 non-null |

*Owner program: long-hold-thesis*


### neural-web

### CONST-A6L1

**A6 Lane (i) — Bounded Deterministic Auto-Apply with quarterly re-audit**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A6_TUNE`

**Ruling:** Clamped, do-no-harm-gated, pre-registered loops (market_state_tune, intl_tune, Engine-Fix arming predicates) are ratified as standing A6 approvals. Each auto-apply must log to the governance ledger (neuralweb.governance.v1) with event_type='a6_auto_apply'. If the last apply is >180 calendar days old, a governance WARNING is emitted and human re-audit is required before the next auto-apply resumes.

**Scope fence:** Auto-apply restricted to clamped, do-no-harm-gated, pre-registered loops only; broader parameter changes must use Lane (ii).

**Forbidden actions:**
  - auto-apply without governance ledger logging
  - auto-apply after >180 days without human re-audit

**Unblock condition:** Human re-audit required if last apply >180 calendar days ago.

**Source:** `engine/neuralweb/constitution.py`
> governance WARNING entry is emitted and human re-audit is required before the

*Owner program: neural-web*

### CONST-A6L2

**A6 Lane (ii) — LLM-Proposed Parameter Change must pre-log gate before apply**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A6_TUNE`

**Ruling:** An Opus model proposes bounded parameter deltas; each proposal must be logged to the governance ledger as event_type='a6_llm_proposed' with the pre-committed gate BEFORE any apply decision. The apply executes only when a do-no-harm backtest confirms improvement. Governance logging is fail-open: a logging failure never aborts the loop.

**Scope fence:** LLM-proposed changes only; deterministic auto-applies use Lane (i). risk_radar_review is the canonical Lane (ii) tenant.

**Forbidden actions:**
  - apply LLM-proposed parameter changes without pre-logging the gate
  - apply without do-no-harm backtest confirmation

**Source:** `engine/neuralweb/constitution.py`
> BEFORE any apply decision. The apply is executed only when a do-no-harm backtest

*Owner program: neural-web*

### CONST-ARM

**Arming-Predicate Doctrine: no env-flag switches; config.yml is operator intent**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A6_TUNE`

**Ruling:** No env-flag safety switches are permitted. Every flag-gated system must declare an arming predicate (evidence-floor + self-gates); systems auto-arm with governance notification when the predicate holds. Arming via config.yml (not _DEFAULTS) is the canonical mechanism — the config file is the operator's committed intent, readable by every run.

**Scope fence:** Applies to all flag-gated systems across the engine; arming through env-vars or _DEFAULTS is forbidden.

**Forbidden actions:**
  - use env-flag safety switches
  - arm via _DEFAULTS instead of config.yml

**Source:** `engine/neuralweb/constitution.py`
> (evidence-floor + self-gates); systems auto-arm with governance notification when the

*Owner program: neural-web*

### CONST-ART1

**Article 1 — Origination Ban: A7/ORIGINATE permanently refused**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A6_TUNE`

**Ruling:** The Neural Web may never originate a signal, trade, escalation, or claim. A7 (ORIGINATE) is hard-coded refused by grant() unconditionally. No amount of evidence, sample size, or Wilson lift can override this refusal. This is a permanent constitutional ban.

**Scope fence:** Neural Web may reach up to A6 (TUNE) but never A7 (ORIGINATE); no signal, trade, escalation, or claim may be invented by the system.

**Forbidden actions:**
  - originate a signal
  - originate a trade
  - originate an escalation
  - originate a claim
  - grant A7_ORIGINATE authority

**Source:** `engine/neuralweb/constitution.py`
> PERMANENTLY BANNED per Article 1. grant() refuses this level unconditionally.

*Owner program: neural-web*

### CONST-ART2

**Article 2 — Scored-Path Perimeter: money-path surfaces require shadow-tier**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Money-path and ranked-output surfaces listed in config/synapse.yml meta.article2_surfaces require at minimum a shadow-with-track-record tier to influence. The synapse.yml file is the single source of truth; the list is not duplicated in the constitution module.

**Scope fence:** Scored-path surfaces may only be influenced by signals that have achieved shadow-with-track-record tier or higher.

**Forbidden actions:**
  - influence money-path surfaces without shadow-tier track record
  - duplicate article2_surfaces list outside synapse.yml

**Source:** `engine/neuralweb/constitution.py`
> in config/synapse.yml meta.article2_surfaces require at minimum a shadow-with-

*Owner program: neural-web*

### CONST-ART3

**Article 3 — Evidence Floor: three gates required for authority grants**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Every authority grant must pass three gates: (a) sample-size floors (n >= min_n AND hits >= min_events), (b) Wilson CI lower-bound lift > 1.25 at z=1.645 (90% one-sided), and (c) evidence freshness within max_staleness_days (default 120). Grants whose evidence has gone stale lapse; authority never persists on silence.

**Scope fence:** Applies to all authority grants up through A6; A7 is refused before evidence evaluation per Article 1.

**Forbidden actions:**
  - grant authority without meeting sample-size floors
  - grant authority with stale evidence
  - grant authority when Wilson CI lift <= 1.25

**Source:** `engine/neuralweb/constitution.py`
> Grants whose evidence has gone stale lapse — authority never persists on silence.

*Owner program: neural-web*

### CONST-STALE

**Evidence staleness: grants lapse at max_staleness_days (default 120d)**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** A grant that previously passed all Article-3 gates but whose evidence has gone stale is refused with granted=False and reason='stale'. The default staleness window is 120 days. lapses_at is returned as an ISO-8601 datetime so callers can track expiry. Authority never persists on silence.

**Forbidden actions:**
  - treat a previously-granted authority as still valid after evidence_asof + 120 days

**Unblock condition:** Fresh evidence (evidence_asof within max_staleness_days) required to re-grant.

**Source:** `engine/neuralweb/constitution.py`
> evidence has gone stale are lapsed (returned with granted=False, reason='stale').

*Owner program: neural-web*

### CONST-LADDER

**Authority ladder A0-A7: rung meanings and current holders are ratified law**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The AuthorityLevel ladder (A0_OBSERVE through A7_ORIGINATE) is the ratified authority vocabulary of the Neural Web. Each rung carries a defined meaning and current holder set; A7_ORIGINATE is permanently banned per Article 1. Any new authority grant must name its rung and clear Article 3.

**Scope fence:** Rung meanings/holders change only by constitution amendment.

**Forbidden actions:**
  - originate

**Source:** `engine/neuralweb/constitution.py`
> PERMANENTLY BANNED per Article 1. grant() refuses this level unconditionally."""

*Owner program: neural-web*

### NW-ART1

**Article 1 — No LLM origination (signal, trade, escalation)**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A7_ORIGINATE`

**Ruling:** No LLM may invent a signal, trade, or escalation. This prohibition is inherited from six live code clamps already in production and may never be renegotiated. It applies permanently across all authority rungs. Classified A7 ORIGINATE — banned.

**Scope fence:** Applies to every LLM surface in the repo; no exception path exists.

**Forbidden actions:**
  - invent a signal
  - invent a trade
  - invent an escalation

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> No LLM may invent a signal, trade, or escalation. Inherited from six live clamps; never renegotiated.

*Owner program: neural-web*

### NW-ART2

**Article 2 — Perimeter by surface: DISPLAY-tier may never rank**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The money-path perimeter is drawn by surface, not by code path. All surfaces that rank or escalate (buy strips, board ordering, top-setups, alert_triage priority inputs, push floors, attention queue) are registered as scored-path surfaces in synapse.yml. DISPLAY-tier signals may annotate but may never rank. Minimum tier to raise an ordering/priority/attention outcome is SHADOW-with-track-record.

**Scope fence:** Any surface that ranks or escalates is a scored-path surface; display-only signals are strictly annotation-only.

**Forbidden actions:**
  - display-tier signal raises ranking
  - display-tier signal raises priority
  - display-tier signal raises attention floor

**Unblock condition:** Signal must reach SHADOW-with-track-record tier before raising any ordering/priority outcome.

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> DISPLAY-tier signals may annotate, never rank.

*Owner program: neural-web*

### NW-ART3

**Article 3 — Authority gates use CI lower bound, lapse on silence**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Every authority gate uses a Wilson CI lower bound (lift lower bound > 1.0 at stated confidence), not a point estimate. At can_force's prior minimums (>=8 alerts) a point-estimate gate false-grants ~36-45% of the time. Each grant's false-grant probability at actual n is printed in the governance ledger entry. When evidence is insufficient or stale, authority lapses — it never persists on absence of evidence.

**Scope fence:** All can_force-style authority gates across the repo must use Wilson CI lower bounds.

**Forbidden actions:**
  - grant authority via point estimate
  - persist authority when evidence is stale or absent

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Every authority gate (can_force-style) uses a **CI lower bound** (Wilson; lift lower bound > 1.0 at stated confidence), not a point estimate — at can_force's current minimums (≥8 alerts) a point-estimate gate false-grants ~36-45% of the time.

*Owner program: neural-web*

### NW-U1

**No hand-weighted return composite — composite law + synapse ratchet**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No hand-weighted return composite has ever validated in this repo. The standing law is equal-weight sector-neutral z-mean as the default; every fancier scheme must beat it out-of-sample. Neural Web ships measured weights or none, enforced via the synapse.yml weights: measured|hand|none field (only-shrinks ratchet). Market_state's existing hand weights get measured (W3), not multiplied.

**Scope fence:** Applies to every composite-scoring surface in the repo; hand-weighted schemes require OOS validation before use.

**Forbidden actions:**
  - ship hand-weighted composite without OOS validation
  - invent master score with invented weights

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> no hand-weighted return composite has EVER validated here

*Owner program: neural-web*

### NW-U10

**D8 ruling: cortex pinned to frontier Opus-class model**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The cortex is pinned to a frontier Opus-class model for its governance role. The third-party default (DeepSeek) is retained for narration fallback only. The governance organ must not think on a third-party discount model.

**Scope fence:** Cortex governance role = Opus-class; narration fallback only = third-party default.

**Forbidden actions:**
  - run cortex governance on third-party discount model

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> frontier Opus-class model pinned for the cortex role

*Owner program: neural-web*

### NW-U11

**Anti-mining law: cortex machine trials graded only on strictly post-registration data**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Machine trials from the cortex's hypothesis metabolism are graded ONLY on data with as_of strictly after registration — zero lookback overlap. The cortex proposes FROM history, so it may never be graded ON it. A hard proposal budget per cycle and retire-one-to-file-one rule apply beyond the budget. Machine trials form their own FDR family so cortex volume can never raise the discovery bar for human programs.

**Scope fence:** All cortex-originated hypotheses must be evaluated strictly on post-registration data.

**Forbidden actions:**
  - grade cortex hypothesis on pre-registration data
  - allow cortex trials to inflate FDR bar for human programs
  - submit hypothesis beyond budget without retiring one

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> **anti-mining rules**: machine trials are graded ONLY on data with as_of strictly after registration

*Owner program: neural-web*

### NW-U12

**Reflex JSONL single-writer law; nightly grader folds firings into spine**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Each reflex appends to its own single-writer JSONL stream (data/reflexes/<name>/firings.jsonl, the whitehouse pattern). The nightly grader folds firings into the spine — no intraday writer ever touches spine parquet. Every reflex firing is graded like any other claim.

**Scope fence:** Reflex firings write only to per-reflex single-writer JSONL; spine parquet is nightly-only.

**Forbidden actions:**
  - intraday writer touches spine parquet
  - multiple writers on reflex firings JSONL
  - ungraded reflex firings

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> each reflex appends to its own single-writer JSONL stream (`data/reflexes/<name>/firings.jsonl`, the whitehouse pattern); the NIGHTLY grader folds firings into the spine — no intraday writer ever touches spine parquet.

*Owner program: neural-web*

### NW-U14

**Gauntlet law binds throughout — display-with-null if gauntlet fails**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Gauntlet law binds throughout the entire Neural Web program. Any Neural Web output that wants to be scored must go through an O6-style pre-registered gauntlet. Failures ship display-with-null rather than being suppressed.

**Scope fence:** All scored Neural Web outputs require pre-registered gauntlets; null results are printed not hidden.

**Forbidden actions:**
  - suppress null gauntlet results
  - score output without pre-registered gauntlet

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Gauntlet law binds throughout:

*Owner program: neural-web*

### NW-U15

**Scope fence: Neural Web owns rails/memory/governance/synthesis only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Neural Web owns rails, memory, governance, and synthesis. Domain programs own their signals. Any Neural Web wave that starts building a domain signal has left the reservation. Applied explicitly three times: sector-pulse restore routed to sector-pulse program; rotation graph routed to Oracle; species calibration routed to setup-species.

**Scope fence:** Neural Web scope = rails, memory, governance, synthesis. Domain signal work belongs to domain programs.

**Forbidden actions:**
  - Neural Web builds domain signal
  - Neural Web implements rotation logic
  - Neural Web runs species calibration

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Neural Web owns *rails, memory, governance, and synthesis*; domain programs own *their signals*.

*Owner program: neural-web*

### NW-U16

**Reliability kernel cells are estimates-with-CIs, never findings; decision rules FDR-fenced quarterly**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Kernel cells are estimates-with-CIs, never findings. Only shrunken posteriors are consumable by any surface. Any cell used to CHANGE behavior (severity cap, demotion) must clear a pre-registered decision rule with a stated error rate and minimum-n floor. The FDR family is defined per engine-family per quarterly batch — no nightly significance-peeking.

**Scope fence:** Kernel estimates are display-only until quarterly FDR batch clears pre-registered decision rules.

**Forbidden actions:**
  - use kernel cell to change behavior before pre-registered decision rule clears
  - nightly significance-peeking on kernel estimates
  - consume unshrunken kernel posterior

**Come back on:** 2026-10-01 (experiment: `neuralweb-kernel-q1-batch`)

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> **cells are estimates-with-CIs, never "findings"**; only shrunken posteriors are consumable by any surface; any cell used to CHANGE behavior (severity cap, demotion) must clear a **pre-registered decision rule with a stated error rate and minimum-n floor**

*Owner program: neural-web*

### NW-U17

**W3 market_state hand-weights: display-first, measured OOS; verdict accruing to ~2027-05**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** The W3 mandate is to measure market_state's hand weights against the equal-weight z-mean baseline per composite law — verdict printed either way. Ships display-first; nothing reweights money until gauntleted. Component logging was patched to accrue nightly from 2026-07-04; measurement pre-registered with come-back ~2027-05.

**Scope fence:** market_state hand weights are display-only until gauntleted OOS comparison clears.

**Forbidden actions:**
  - reweight market_state money path before gauntlet clears

**Unblock condition:** n>=250 days of PIT component history accrued; OOS comparison passes pre-registered gate.

**Come back on:** 2027-05-01 (experiment: `market-state-tune`)

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> W3 line item: measure market_state's hand weights against the equal-weight z-mean baseline per composite law — verdict printed either way.

*Owner program: neural-web*

### NW-U18

**In-place envelope — never a wrapper; sidecar for parquet/JSONL**

- Status: `adopted` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The signal envelope uses in-place sibling keys alongside existing payload keys (schema_version/produced_by/produced_at/inputs_hash/tier), never a wrapper object. A wrapper would silently re-darken the risk_radar feed — the exact 2026-07-02 incident the feeds plane exists to prevent. inputs_hash is computed over payload-ex-envelope so unchanged data stays byte-identical. Parquet/JSONL use a sidecar .envelope.json.

**Scope fence:** All bus artifact envelopes must use in-place sibling keys; wrapper envelopes are forbidden.

**Forbidden actions:**
  - wrap signal payload in outer envelope object
  - envelope that breaks byte-identity of unchanged payload

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Envelope = **in-place sibling keys, never a wrapper**

*Owner program: neural-web*

### NW-U19

**Synapse registry weights ratchet: only-shrinks on hand-weight debt**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The synapse.yml registry carries a weights: measured|hand|none field for every bus artifact so composite-weight debt is tracked by the registry and ratcheted (only-shrinks) rather than policed by culture alone. A unregistered cross-engine read is warn-then-fail under a CI only-shrinks ratchet.

**Scope fence:** All bus artifacts must be registered in synapse.yml; unregistered cross-engine reads fail CI.

**Forbidden actions:**
  - leave hand-weighted composite unregistered in synapse.yml
  - new unregistered cross-engine read

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> weights: measured|hand|none

*Owner program: neural-web*

### NW-U2

**No cross-engine hard gate without its own gauntlet**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Cross-engine hard gating was falsified by the China reversal gated-by-subsector pattern, which hurt in every era. Neural Web must never hard-gate one engine on another without its own pre-registered gauntlet. Confluence states ship as context/annotation under Article 2 and may not raise rankings until they hold SHADOW-with-track-record tier.

**Scope fence:** No engine may gate another engine's output without a separately gauntleted, pre-registered decision rule.

**Forbidden actions:**
  - hard-gate one engine on another without own gauntlet
  - use confluence state to raise ranking before SHADOW tier

**Unblock condition:** Confluence edge must pass own pre-registered gauntlet and reach SHADOW-with-track-record tier.

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> cross-engine confluence NEVER hard-gates a validated edge without its own gauntlet

*Owner program: neural-web*

### NW-U20

**No substrate migration wave — federation with shared axes only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No substrate migration wave is permitted. The architecture is federation with shared axes (the Setup Species Stage B precedent). Market-native fill rules are preserved per-store. Shared vocabulary is threaded through. qledger stays QI-owned. Joint rulings are required for shared substrates.

**Scope fence:** No forced migration of existing ledgers; federation with adapters and shared axes only.

**Forbidden actions:**
  - force ledger migration to a new substrate
  - unilateral shared-substrate change

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> **No substrate migration wave** — federation with shared axes (the Setup Species precedent); qledger stays QI-owned; joint rulings for shared substrates.

*Owner program: neural-web*

### NW-U21

**can_force converted to Wilson CI lower-bound; authority-revoking direction**

- Status: `adopted` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** can_force was converted from point-estimate lift (false-grants ~45% at min n under the null) to Wilson-CI lower-bound lift (<6% under the same null). This change is in the authority-revoking direction. Per-market impact is printed in the PR. A6 lane-(i) tuners now log every auto-apply to the governance ledger.

**Scope fence:** can_force authority grant uses Wilson CI lower bound; point-estimate grant is permanently revoked.

**Forbidden actions:**
  - grant can_force override via point-estimate lift

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> can_force converted from point-estimate lift (false-grants ~45% at min n under the null) to Wilson-CI lower-bound lift

*Owner program: neural-web*

### NW-U22

**altdata_brain actionable flag refused — insufficient track record (n=5 < min_n=25)**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** altdata_brain's grandfathered actionable:True flag was reviewed under Article 3. Today's honest verdict: REFUSED (insufficient-n: n=5 independent date clusters < min_n=25 required). The flag auto-re-grants the night the track record clears (earliest: 2026-08-29). Until then, mastermind.json carries actionable:false/is_context_only:true; feed shape is unchanged (additive fields only).

**Scope fence:** altdata_brain output is context-only until Article-3 Wilson gate clears at n>=25.

**Forbidden actions:**
  - surface altdata_brain as actionable before Article-3 gate clears

**Unblock condition:** n>=25 independent date clusters in qledger; earliest 2026-08-29.

**Come back on:** 2026-08-29

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> REFUSED (insufficient-n: n=5 independent date clusters < min_n=25 required)

*Owner program: neural-web*

### NW-U24

**Signal gate 3-lane failure semantics**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`
- Authority ceiling: `A4_QUARANTINE`

**Ruling:** The Neural Web signal gate has three-lane failure semantics: RED pre-merge (blocks the PR), quarantine-continue nightly (bad signal is frozen to last-good with watermark, pipeline continues), annotate intraday (failure annotated on site, no quarantine). These are the only valid failure modes for registered bus artifacts.

**Scope fence:** All registered bus artifact failures must route through one of the three failure lanes.

**Forbidden actions:**
  - silent failure of registered bus artifact
  - quarantine without serving last-good watermarked output

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> §7 signal gate has 3-lane failure semantics (RED pre-merge / quarantine-continue nightly / annotate intraday)

*Owner program: neural-web*

### NW-U28

**Governance ledger: append-only, evidence attached, every A4-A6 action logged**

- Status: `adopted` | Kind: `data_contract` | Nondelegable: `True`
- Authority ceiling: `A5_GOVERN_TIERS`

**Ruling:** Every A4-A6 action lands in an append-only governance ledger with the evidence attached (the btc-override registry pattern, generalized). The governance ledger uses schema neuralweb.governance.v1. Every A6 lane-(i) auto-apply and every cortex A6 lane-(ii) proposal/apply/reject is logged. The ledger is quarterly re-audited.

**Scope fence:** All A4-A6 actions must be in the governance ledger before taking effect.

**Forbidden actions:**
  - A4-A6 action without governance ledger entry
  - delete or mutate governance ledger entries

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Every A4–A6 action lands in an append-only **governance ledger** with the evidence attached (the btc-override registry pattern, generalized).

*Owner program: neural-web*

### NW-U29

**No universal per-ticker bounce model — species×regime calibration to setup-species**

- Status: `no_build` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No universal per-ticker bounce-probability meta-model is to be built. Momentum is dead everywhere tested; only 7 of 23 anticipation legs are OOS GO. The learnable pattern is state-conditional base rates, species×regime calibration (owned by setup-species), and risk-side composites. Neural Web provides the spine and kernel they read.

**Scope fence:** No Neural Web per-ticker P(bounce) model; species calibration belongs to setup-species program.

**Forbidden actions:**
  - build per-ticker P(bounce) meta-model in Neural Web
  - train universal bounce predictor on all signals

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> **No universal per-ticker bounce model** — species×regime calibration belongs to setup-species; Neural Web provides the spine and kernel they read.

*Owner program: neural-web*

### NW-U3

**Nightly is sole advancer of forward ledgers; intraday lanes discard data/ writes**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The nightly pipeline is the sole advancer of forward ledgers. Intraday lanes deliberately discard data/ writes. Whitehouse is the sole engineered intraday ledger-writer (designed to prevent append races). The cortex's own commit lane is downstream of the engine job and can never gate the deploy.

**Scope fence:** All forward ledger writes must originate from the nightly pipeline; intraday writes to data/ are discarded by design.

**Forbidden actions:**
  - intraday lane writes to forward ledger
  - non-whitehouse intraday ledger write

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> intraday lanes deliberately discard data/ writes

*Owner program: neural-web*

### NW-U30

**A2 earn-in refused as of 2026-07-04; cortex attention accruing; clocks open**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** The cortex A2 authority earn-in evaluation was REFUSED on 2026-07-04 (n=0 < min_n=25; hits=0 < min_events=8). Probation continues. A0/A1 are unconditional. The A2 earn-in is accruing nightly. Standing clock: cortex A2 earn-in requires n>=25 graded attention events, hits>=8, Wilson-LB lift > 1.0.

**Scope fence:** Cortex A2 (attention queue as ranking) is blocked; A0/A1 unconditional.

**Forbidden actions:**
  - surface cortex attention queue as ranking before A2 gate clears

**Unblock condition:** n>=25 graded attention events, hits>=8, Wilson-LB lift>1.0.

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> A2 earn-in evaluation today: REFUSED — empty attention record (n=0 < min_n=25; hits=0 < min_events=8). Probation continues; A0/A1 unconditional.

*Owner program: neural-web*

### NW-U4

**Cortex earns authority on probation — A2/A4-A6 gated on Article-3 track record**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** The cortex runs its first weeks in SHADOW: its attention queue is produced but not surfaced as ranking. Every queue item carries a falsifiable 'this mattered' criterion graded into the spine. A2 and A4-A6 proposal rights arm only when its graded attention/thesis record clears an Article-3 gate. The cortex serves probation on the same terms it will later enforce.

**Scope fence:** Cortex A2/A4-A6 authority is blocked until n>=25 graded attention events and CI lower-bound gate clears.

**Forbidden actions:**
  - surface cortex attention queue as ranking before Article-3 gate clears
  - grant A4-A6 without track record

**Unblock condition:** n>=25 graded attention events, hits>=8, Wilson-LB lift > 1.0.

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> The cortex runs its first weeks in SHADOW: its attention queue is produced but not surfaced as ranking

*Owner program: neural-web*

### NW-U5

**A6 two-lane ruling: bounded deterministic vs LLM-proposed changes**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A6_TUNE`

**Ruling:** A6 (tune) operates in two explicit lanes: (i) bounded deterministic auto-apply — clamped, do-no-harm-gated, pre-registered loops are ratified standing A6 approvals, required only to log every write to the governance ledger with quarterly re-audit; (ii) LLM-proposed changes — must land as machine-registered experiment entries with pre-committed gates and come-back dates, requiring the do-no-harm harness AND a logged promotion event. risk_radar_review arms only after its writes are rewired through lane (ii)'s registration and logging.

**Scope fence:** All parameter/weight changes must flow through one of the two A6 lanes; ad-hoc LLM writes to engine parameters are forbidden.

**Forbidden actions:**
  - LLM proposes parameter change without machine-registered experiment entry
  - auto-apply without governance ledger log
  - LLM-proposed change without pre-committed gate

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> two lanes, explicitly:** (i) *bounded deterministic auto-apply* — clamped, do-no-harm-gated, pre-registered loops (market_state_tune, intl_tune, Engine-Fix arming predicates) are hereby **ratified as standing A6 approvals**

*Owner program: neural-web*

### NW-U6

**Oracle is the rotation lobe; Neural Web never re-implements rotation detection**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Oracle is the rotation lobe producing sector/theme/subsector rotation history, episodes, and Time Machine. Neural Web is the whole brain; Oracle is one signal producer feeding it. Neural Web never re-implements rotation detection. Namespace: engine/neuralweb/ (oracle is taken; cortex was the prior working name, superseded).

**Scope fence:** Rotation detection logic stays in Oracle; Neural Web only consumes Oracle's artifacts read-only.

**Forbidden actions:**
  - Neural Web builds rotation detection logic
  - Neural Web duplicates Oracle's sector rotation analysis

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Neural Web never re-implements rotation detection.

*Owner program: neural-web*

### NW-U7

**Oracle artifacts consumed read-only by N4; graph library extraction deferred to Oracle P7**

- Status: `deferred` | Kind: `rail` | Nondelegable: `True`

**Ruling:** Oracle builds its O1 graph untouched. Neural Web W4 consumes Oracle's edge-stability ledger and routing artifacts READ-ONLY as bus citizens. The graphlib-sharing plan was unilateral and circular. Library extraction is deferred to a joint ruling at Oracle P7. Both programs share the house-wide registered-trial CI (check_trial_registration) as the one-FDR-ledger mechanism.

**Scope fence:** Neural Web W4 reads Oracle artifacts only; no shared graph library until Oracle P7 joint ruling.

**Forbidden actions:**
  - Neural Web writes Oracle graph artifacts
  - shared graph library without Oracle P7 joint ruling

**Unblock condition:** Joint ruling at Oracle P7.

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> Neural Web W4 consumes Oracle's edge-stability ledger and routing artifacts READ-ONLY as bus citizens; library extraction is deferred to a joint ruling at Oracle P7.

*Owner program: neural-web*

### NW-U8

**D2 ruling: spine = query layer; qledger stays QI-owned; substrate ruling open pending QI W6**

- Status: `deferred` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** Federation architecture is ratified. The spine is the query layer — a read-side index/view over all federated ledgers. qledger stays QI-owned; its ladder vocabulary becomes the house tier language (A5). Any substrate ruling is a joint ruling co-signed with the QI program record, sequenced after QI's armed W6 promotion monitor fires or with qledger semantics frozen meanwhile.

**Scope fence:** No unilateral qledger substrate changes; must be co-signed with QI program.

**Forbidden actions:**
  - unilateral qledger substrate change
  - migrate qledger without QI co-sign
  - assume qledger ownership outside QI program

**Unblock condition:** QI W6 promotion monitor fires (earliest projection ~2026-08-29).

**Come back on:** 2026-08-29

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> federation architecture ratified; spine = query layer; qledger stays QI-owned with its ladder becoming the house tier vocabulary.

*Owner program: neural-web*

### NW-U9

**D3 ruling: two organisms, two brains — dashboard cortex vs Mastermind Brain**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** master_brain grows into the cortex governing the dashboard. Mastermind Brain remains the portfolio organism's decision-maker, consuming Neural Web over the registered corpus callosum (feeds-R2 outbound, mastermind_snapshot inbound). This supersedes the CORTEX brainstorm's one-brain lean.

**Scope fence:** Dashboard cortex and Mastermind Brain are separate organisms with separate authority domains.

**Forbidden actions:**
  - merge dashboard cortex with Mastermind Brain decision loop

**Source:** `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`
> two organisms, two brains

*Owner program: neural-web*

### NWP-U10

**L1 short-side grader: terminal_state_short() required; no mult-flip workaround**

- Status: `adopted` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** engine/grading.py's terminal_state() hard-codes long-side inequality directions and cannot be mirrored by flipping mult values (a liftoff_mult<1 fires liftoff immediately). A direction-aware short-side grader terminal_state_short() must be added, reversing the barrier inequalities. Both short-side and long-side grades are published on the same events as a paired within-event contrast only.

**Scope fence:** L1 short-side grading; any study grading short-side breakdown events.

**Forbidden actions:**
  - mirror grading by flipping mult values
  - use terminal_state() for short-side grading
  - analyze short-side and long-side grades as two independent samples

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> `terminal_state()` **hard-codes long-side inequality directions and CANNOT be mirrored by flipping mult values** (a liftoff_mult<1 fires immediately). PR-5 adds a direction-aware short-side grader — `terminal_state_short()` reversing the barrier inequalities

*Owner program: neural-web*

### NWP-U12

**R2 grading-closure audit: standing visibility for log-only and grader-starved ledgers**

- Status: `adopted` | Kind: `rail` | Nondelegable: `False`

**Ruling:** The R2 audit script (audit_grading_closure.py) walks a declared inventory of forward ledgers and classifies each as CLOSED, GRADER-STARVED, or LOG-ONLY. This makes the status standing and visible instead of rediscovered per-program. Fixes are per-program follow-ups, not part of the audit PR.

**Scope fence:** Governance audit only; ledger fixes are separate per-program PRs.

**Forbidden actions:**
  - fix ledger issues in the audit PR itself

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> The audit makes this standing and visible instead of rediscovered per-program. Fixes are per-program follow-ups, not this PR.

*Owner program: neural-web*

### NWP-U13

**R4 contract drift check: schema_version + consumer registry; warn-first then hard-fail**

- Status: `adopted` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** artifact_manifest.json entries must carry schema_version (semver string) and schema_fields (sorted top-level field list). check_contract_drift.py fails when published contract JSON fields diverge from the manifest. It is wired into CI as warn-first, hard-failing after one clean week (ratchet). The consumer registry vocabulary (bot:*, terminal:*) is documented in the manifest header.

**Scope fence:** All entries in artifact_manifest.json; CI enforcement on schema divergence.

**Forbidden actions:**
  - deploy contract JSON without schema_version
  - ship real-money consumers without registered schema handshake

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> extend `site/factordata/contracts/artifact_manifest.json` entries with `schema_version` (semver string) + `schema_fields` (sorted top-level field list, machine-diffable); add `scripts/check_contract_drift.py` that fails when a published contract JSON's actual top-level fields diverge from the manifest

*Owner program: neural-web*

### NWP-U18

**No held-book/portfolio construction; no gross_mult unclamping; L8 → Mastermind**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No held-book/portfolio construction, no sizing changes, and no gross_mult unclamping are permitted in this program. Portfolio-level construction is L8 territory — it belongs to Mastermind, not Neural Web. R4 carries the contract only.

**Scope fence:** All Neural Web program artifacts; portfolio/sizing belongs to Mastermind.

**Forbidden actions:**
  - implement portfolio construction in neural-web
  - unclamp gross_mult
  - add sizing changes in neural-web

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> No held-book/portfolio construction, no sizing changes, no `gross_mult` unclamping (L8 → Mastermind; R4 carries the contract only).

*Owner program: neural-web*

### NWP-U19

**No kernel consumers before 2026-10 FDR batch; no LLM-originated signals**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No kernel consumers are permitted before the 2026-10 FDR batch. No LLM-originated signals anywhere — this is a constitution-level constraint. Both apply across all programs.

**Scope fence:** All programs; kernel consumers and LLM-originated signals blocked.

**Forbidden actions:**
  - create kernel consumers before 2026-10 FDR batch
  - originate signals from LLMs anywhere in the system

**Unblock condition:** Kernel consumers: 2026-10 FDR batch completion.

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> No kernel consumers before the 2026-10 FDR batch; no LLM-originated signals anywhere (constitution).

*Owner program: neural-web*

### NWP-U2

**ERA LAW: absolute rates only on verdict_grade=True (2021+ massive uncensored)**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Rows must be split into verdict_grade=True (2021+ massive, uncensored) vs survivor-biased cohorts. Absolute rates may ONLY be reported on the former. Survivor-biased cohorts appear as within-cohort deltas with survivorship_biased=True stamped. This applies to all replay and study outputs.

**Scope fence:** All rule-replay outputs and study harnesses consuming replay_boarded or long_hold_labels.

**Forbidden actions:**
  - report absolute rates on survivor-biased cohorts
  - omit survivorship_biased=True stamp on biased-cohort deltas

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> ERA LAW: rows split into `verdict_grade=True` (2021+ massive, uncensored) vs survivor-biased cohorts; absolute rates may ONLY be reported on the former; the latter appears as within-cohort deltas with `survivorship_biased=True` stamped.

*Owner program: neural-web*

### NWP-U20

**L6 gated on Phase-0 beating noisy-sector precedent; no macro transmission fingerprints**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** No macro transmission fingerprints are permitted. L6 stays gated on its Phase-0 beating the noisy-sector precedent. This scope fence is standing until L6 Phase-0 delivers.

**Scope fence:** L6 macro transmission fingerprints lobe; gated on Phase-0 evidence.

**Forbidden actions:**
  - build macro transmission fingerprints before L6 Phase-0 clears noisy-sector precedent

**Unblock condition:** L6 Phase-0 beats the noisy-sector precedent.

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> No macro transmission fingerprints (L6 stays gated on its Phase-0 beating the noisy-sector precedent).

*Owner program: neural-web*

### NWP-U24

**Per-bar forward paths nonexistent pre-computed; all path work must use massive_stock_day**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** Per-bar forward paths exist nowhere pre-computed. Every tape (replay_boarded, track_record, long_hold_labels) is endpoint-stats-only. Any exit/hold rule replay must compute paths on demand from massive_stock_day (raw prices — split_adjust() mandatory) within the ERA LAW window.

**Scope fence:** Any study computing exit/hold replay paths; split_adjust() is mandatory.

**Forbidden actions:**
  - assume pre-computed per-bar paths exist
  - compute paths without split_adjust()
  - use endpoint-stats tapes as path sources

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> **CONFIRMED with numbers:** per-bar forward paths exist NOWHERE pre-computed — every tape (replay_boarded, track_record, long_hold_labels) is endpoint-stats-only. Any exit/hold rule replay must compute paths on demand from `massive_stock_day` (raw prices — `split_adjust()` mandatory) within the ERA LAW window.

*Owner program: neural-web*

### NWP-U3

**CohortFilter v1: existing replay_boarded columns only; no derived features**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** CohortFilter v1 is a conjunction of equality/threshold predicates over existing replay_boarded columns ONLY. No derived features in v1 — that is where fishing hides. Grid granularity must be justified in the registry question field.

**Scope fence:** R1 CohortFilter v1; extending to derived features requires a program amendment.

**Forbidden actions:**
  - add derived features to CohortFilter v1
  - omit grid-granularity justification from registry question

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> `CohortFilter` v1: conjunction of equality/threshold predicates over existing replay_boarded columns ONLY (`verdict_type`, `verdict_grade`, `tier_cascade`, `align_tier`, `sector`, `year`, `washout_proximity`, `ext_grade`, …). No derived features in v1 — that is where fishing hides.

*Owner program: neural-web*

### NWP-U4

**ExitPolicy v1 frozen enum; extending requires program amendment**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`

**Ruling:** ExitPolicy v1 is a frozen enum of 6 holds, 1 ema_trail (canonical 3B resampled EMA8 from signal_quality.py), 4 trail_stops, and 4 barriers. Extending it requires a program amendment logged in the program doc. The builder must import signal_quality's own functions and never re-implement the resample grid.

**Scope fence:** R1 v1 ExitPolicy; any extension triggers amendment process.

**Forbidden actions:**
  - extend ExitPolicy v1 without program amendment
  - re-implement EMA8 resample grid instead of importing signal_quality
  - use '3D' resample instead of '3B'

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> `ExitPolicy` v1 (frozen enum — extending it requires a program amendment logged here):

*Owner program: neural-web*

### NWP-U5

**Flat pooled FDR family='replay': sub-families prohibited**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** FDR accounting is pooled and flat; every R1 registration calls TrialLedger.log_declared_budget with family='replay' BEFORE the run. Sub-families (fdr_family='replay.<exp_id>') are prohibited because they create isolated multiple-testing islands that launder the cumulative trial count. Every results summary must print the cumulative pooled trial count to date.

**Scope fence:** All R1 rule-experiment registrations and results summaries.

**Forbidden actions:**
  - create sub-families under fdr_family='replay'
  - omit cumulative pooled trial count from results summary
  - call log_declared_budget after the run

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> **FDR accounting is pooled and flat:** every registration calls `TrialLedger.log_declared_budget(grid_size, family='replay')` BEFORE the run — the docket-mandated single family, so cumulative trials against the tape accumulate across ALL experiments (TrialLedger keys on exact strings; sub-families would create isolated islands and are prohibited).

*Owner program: neural-web*

### NWP-U6

**No-adhoc rule: adding --adhoc flag is a house-law violation**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The runner (scripts/run_rule_replay.py) hard-fails on any mismatch or missing registration. No --adhoc flag exists; adding one is a house-law violation. Every run must reference a pre-registered exp_id with matching content hash.

**Scope fence:** run_rule_replay.py and any future R1 runner variant.

**Forbidden actions:**
  - add --adhoc flag to the runner
  - run without pre-registered exp_id
  - bypass content-hash verification

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> **hard-fails on any mismatch or missing registration**. No `--adhoc` flag exists; adding one is a house-law violation.

*Owner program: neural-web*

### NWP-U7

**EXIT-GRID-1 descriptive-only verdict; forking-paths contamination event**

- Status: `adopted` | Kind: `study` | Nondelegable: `False`

**Ruling:** EXIT-GRID-1 verdict criteria is descriptive-only. The batch's job is to explain the survivors and produce the regret surface, not to promote an exit rule. Per RUL-P3, this descriptive surface is itself a contamination event: any later promotion prereg on this tape must carry derived_from_surface: exit_grid_v1 and a compensating gate.

**Scope fence:** Any promotion prereg on the replay fire tape after EXIT-GRID-1 ran.

**Forbidden actions:**
  - promote an exit rule based on EXIT-GRID-1 without derived_from_surface stamp
  - omit compensating gate on post-descriptive promotion prereg

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> Verdict criteria: **descriptive-only.** This batch carries the settled exit-routing NO-GO honestly (joint DD-AND-capture 37–43% vs 70% floor; "drawdown control is an ENTRY problem"). Its job is to EXPLAIN the survivors and produce the regret surface, not to promote an exit rule.

*Owner program: neural-web*

### NWP-U9

**L1 short-side: AVOID-not-SHORT; no site surface in Phase-0; BD-3 strongest**

- Status: `adopted` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** L1 Phase-0 verdict (shipped #1558): long side stops 20-49pp more than short side achieves favorable, all clustered CIs exclude 0 — this constitutes AVOID-not-SHORT evidence. BD-3 is the strongest arming condition. The objective is an avoid/de-risk lens, NOT a shorting-execution program.

**Scope fence:** L1 short-side lobe; no site surface, no chip until a subsequent phase establishes more than AVOID evidence.

**Forbidden actions:**
  - present short-side as a shorting-execution program
  - add site surface or chip based on Phase-0 alone

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> Phase-0 paired within-event verdict: long side stops 20–49pp more than short side achieves favorable, all clustered CIs exclude 0 → AVOID-not-SHORT evidence; BD-3 strongest arming condition

*Owner program: neural-web*

### RUL-P1

**Two-lobe cap: only L1 Short-Side and L3 Dispersion chartered**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Exactly two lobes are chartered by this program: L1 Short-Side and L3 Dispersion. The exit-regret ledger ships as R1's first registered rule-experiment batch (a rail artifact), NOT as an L2 charter. L2's charter is deferred until the regret evidence exists and a lobe owner can carry it. The two-lobe cap protects review and nightly bandwidth.

**Scope fence:** No additional lobe charters in this program beyond L1 and L3.

**Forbidden actions:**
  - charter L2 before EXIT-GRID-1 evidence exists
  - add nightly graders beyond dispersion JSON

**Unblock condition:** L2 requires EXIT-GRID-1 regret evidence and a named lobe owner.

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> exactly two lobes are chartered by this program: **L1 Short-Side** and **L3 Dispersion**. The exit-regret ledger ships as **R1's first registered rule-experiment batch** (a rail artifact), NOT as an L2 charter. L2's charter is deferred until the regret evidence exists and a lobe owner can carry it.

*Owner program: neural-web*

### RUL-P10

**New data stores must declare commit path: gitignore, single-writer, or R2**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** Every new write path in this program must state, in its PR, one of: (a) explicit .gitignore entry (Mac-local/server-local store), (b) git-committed with a named single-writer, or (c) R2 artifact. Nothing new may ride the nightly blanket 'git add data/' implicitly. This PR-set also retroactively gitignores data/replay/*.parquet.

**Scope fence:** All new data write paths in this program and future programs by extension.

**Forbidden actions:**
  - let new data stores ride nightly blanket git add data/ implicitly
  - omit commit-path declaration from PR

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> every new write path in this program states, in its PR, one of: (a) explicit `.gitignore` entry (Mac-local/server-local store), (b) git-committed with a named single-writer, or (c) R2 artifact. Nothing new may ride the nightly blanket `git add data/` implicitly.

*Owner program: neural-web*

### RUL-P2

**R1 shape: fire-tape replay only, no gate re-run, no portfolio construction**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`

**Ruling:** R1 v1 is a fire-tape x policy-grid replay, not a gate re-run engine. Entry events come from the existing production fire tape; rules parametrize cohort filter, fill delay, exit policy, and per-fire weight only. Re-running the gate itself with modified parameters remains replay_standout_pipeline.py territory (gate_fn injection is R1 v2, post-Fable). Portfolio-level construction (position interaction, cash ledger) is OUT OF SCOPE.

**Scope fence:** R1 v1 processes existing fire tape only; no gate modification, no portfolio construction.

**Forbidden actions:**
  - re-run gate with modified parameters in R1
  - add portfolio construction to R1
  - add position interaction or cash ledger to R1

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> R1 v1 is a **fire-tape × policy-grid replay**, not a gate re-run engine. Entry events come from the existing production fire tape; rules parametrize *cohort filter*, *fill delay*, *exit policy*, and *per-fire weight*. Re-running the gate itself with modified parameters remains `replay_standout_pipeline.py` territory

*Owner program: neural-web*

### RUL-P3

**Governor is law: no unregistered grid, flat fdr_family='replay', forking-paths stamp**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The R1 runner must refuse any policy grid not registered in the rule-experiment registry before the run (content-hash match). No interactive/exploratory mode exists. Every run pools into the flat fdr_family='replay' TrialLedger family. All outputs are display-only; promoting any rule to live behavior requires the standard PREREG gauntlet outside R1. Any promotion prereg written after a descriptive batch must carry a derived_from_surface stamp and a compensating gate.

**Scope fence:** All R1 rule-experiment runs; any promotion prereg that derives from a descriptive surface on the replay tape.

**Forbidden actions:**
  - run unregistered policy grid
  - add --adhoc flag
  - create fdr sub-families under replay
  - promote rule to live without PREREG gauntlet
  - omit derived_from_surface stamp on post-descriptive prereg

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> the R1 runner MUST refuse any policy grid not registered in the rule-experiment registry before the run (content-hash match). No interactive/exploratory mode exists. Every run pools into the flat `fdr_family='replay'` TrialLedger family. All outputs are display-only

*Owner program: neural-web*

### RUL-P4

**R3 vintage-stamp minimum: 8 fields required for R1 serialization**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** R1 outputs refuse to serialize without a vintage stamp containing all 8 fields: price_plane_id, adjustment_mode, universe_as_of, frame (pit basis), survivorship_biased, coverage_frac, dead_name_coverage_pct, era_law_cohort. The stamp helper is a shared engine module usable by any future study. Full vintage-matrix work stays with Signal Commons.

**Scope fence:** All R1 rule-replay result serialization; any harness that consumes vintage_stamp.py.

**Forbidden actions:**
  - serialize R1 results without vintage stamp
  - omit any of the 8 stamp fields

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> R1 outputs refuse to serialize without a **vintage stamp**: `price_plane_id`, `adjustment_mode`, `universe_as_of`, `frame` (pit basis), `survivorship_biased`, `coverage_frac`, `dead_name_coverage_pct`, `era_law_cohort`. The stamp helper is a shared engine module usable by any future study.

*Owner program: neural-web*

### RUL-P5

**L3 is promotion not invention: no new math, gross_mult clamped 1.0**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The dispersion lens promotes the existing engine/dispersion.py output (lean_in/lean_out/neutral, gross_mult clamped 1.0) to a registered nightly artifact and display chip. No new math is introduced. Its shadow-ladder question runs as a registered R1 experiment (DISP-GATE-1), not a bespoke harness.

**Scope fence:** L3 dispersion lobe; gross_mult is display-only and may not be unclamped.

**Forbidden actions:**
  - introduce new math in L3
  - unclamp gross_mult beyond 1.0
  - run DISP-GATE-1 as bespoke harness outside R1

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> the dispersion lens promotes the EXISTING `engine/dispersion.py` output (lean_in/lean_out/neutral, gross_mult clamped 1.0) to a registered nightly artifact + display chip. No new math. Its shadow-ladder question runs as a registered R1 experiment (DISP-GATE-1), not a bespoke harness.

*Owner program: neural-web*

### RUL-P6

**L1 asymmetry is a question, not a premise; paired within-event contrast only**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The short-side charter pre-registers 'do bottoming edges invert?' as a hypothesis, never a premise. Phase-0 builds the breakdown event tape and grades it with a direction-aware short-side grader alongside long-side grades on the same events, analyzed as a paired within-event contrast (never two independent samples). No site surface, no chip, no claims this wave.

**Scope fence:** L1 short-side charter Phase-0 only; no site surface or chip until evidence established.

**Forbidden actions:**
  - assert short-side edge as premise
  - use two independent sample comparison instead of paired contrast
  - publish site surface or chip in Phase-0
  - make claims this wave

**Unblock condition:** Advancement beyond Phase-0 requires paired within-event evidence.

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> the short-side charter pre-registers "do bottoming edges invert?" as a hypothesis, never a premise. Phase-0 builds the breakdown event tape and grades it with a direction-aware short-side grader alongside long-side grades on the same events, analyzed as a **paired within-event contrast** (never two independent samples). No site surface, no chip, no claims this wave.

*Owner program: neural-web*

### RUL-P7

**L4 decision-quality lobe NOT chartered; instrumentation-first only**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The decision-quality lobe is NOT chartered. This program ships only the accrual instrumentation (operator action ledger + admin capture) because calendar time is the binding constraint on grading. The grading harness generalizing btc_override_ledger.py is a post-Fable Opus wave. The ledger must accrue n>=25 graded operator actions before grading can proceed.

**Scope fence:** L4 lobe charter deferred; action_ledger.jsonl instruments only.

**Forbidden actions:**
  - charter L4 before n>=25 graded operator actions
  - build grading harness before ledger accrual

**Unblock condition:** n>=25 graded operator actions in the ledger; post-Fable Opus wave.

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> the decision-quality lobe is NOT chartered. This program ships only the accrual instrumentation (operator action ledger + admin capture) because calendar time is the binding constraint on grading. The grading harness generalizing `btc_override_ledger.py` is a post-Fable Opus wave.

*Owner program: neural-web*

### NWC-U1

**This doc charters no lobe; it is build authority for its waves only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** This document is the build authority for the waves it authorizes. It charters no lobe. Taxonomy authority remains `research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md`; build authority for chartered lobes remains `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`.

**Scope fence:** This document grants wave build authority only; no lobe charters derive from it.

**Forbidden actions:**
  - claim lobe charter authority from this document

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> This document is the build authority for the WAVES it authorizes below — it charters no lobe.

*Owner program: neural-web*

### NWC-U10

**Spine index has no sector column; join source must be named and PIT limitation declared**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** `data/neuralweb/spine_index.parquet` has no sector column and is 99.9% entity-grain. The prereg must name the symbol-to-sector join source, state its PIT limitation (current-date sector map applied to historical fires is an accepted declared limitation), and mandate aggregation to sector/pooled grain before any cell is formed.

**Scope fence:** Sector aggregation must occur before cell formation; no per-name cells.

**Forbidden actions:**
  - assume spine_index has sector column
  - form per-name cells from spine index
  - omit join source from prereg

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> `data/neuralweb/spine_index.parquet` (288,666 rows) has NO sector column and is 99.9% entity-grain (`scope_type='entity'`). The prereg must name the symbol→sector join source

*Owner program: neural-web*

### NWC-U12

**OFR FSI must be lagged ≥1 business day; frozen publication offsets required**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The OFR FSI series (`data/ofr_fsi/fsi_credit.parquet`) carries no publication vintage and publishes at ~1-business-day lag. Axis reads must be lagged by frozen publication offsets committed in the prereg. Market yields/prices are same-day-close safe for nightly fires. Any revisable macro series must either use vintage data or be excluded.

**Forbidden actions:**
  - use OFR FSI same-day without lag
  - omit publication offset from prereg

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> `data/ofr_fsi/fsi_credit.parquet` carries no publication vintage and publishes at ~1-business-day lag — axis reads must be lagged by frozen publication offsets in the prereg

*Owner program: neural-web*

### NWC-U13

**Episode cluster unit is contiguous hostile window, not individual fire**

- Status: `active_law` | Kind: `study` | Nondelegable: `False`

**Ruling:** The cluster unit for episode-clustered CIs is the contiguous hostile macro WINDOW (calendar episode), never the individual fire. Fires across all sectors on the same macro dates are one draw, not hundreds. This is the operationalization required for the L6-P0 verdict gates.

**Forbidden actions:**
  - treat individual fires as independent observations in hostile-window CI
  - cluster by fire instead of by episode window

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> the cluster unit is the contiguous hostile WINDOW (calendar episode), never the fire, because fires across all sectors on the same macro dates are one draw, not hundreds

*Owner program: neural-web*

### NWC-U15

**All waves shipped same-day 2026-07-06; A1 rates PASS re-opens L6 charter question**

- Status: `adopted` | Kind: `wave` | Nondelegable: `True`

**Ruling:** All waves (W-0/W-A/W-B/W-C/W-D) shipped same day 2026-07-06. L6-P0 result: A1 rates PASS → L6 charter question re-opened with conditions C1–C4. A2 (USD), A3 (credit), A4 (liquidity) FAIL, printed. Registry-drift merge races absorbed ×3 (synapse 189→190→191).

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> A1 rates PASS → L6 charter question re-opened with conditions C1–C4; A2/A3/A4 FAIL, printed.

*Owner program: neural-web*

### NWC-U16

**Codex-6 'not a lobe' — decomposes into rail wave + bridge key + accrual experiments**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Claim Reliability / Narrative Truth is NOT a lobe. It decomposes into: already-built (QI's track_record.json), an R2-rail wave (W-A), a bridge wave (W-B), and two accrual-gated future experiments (NARR-2/NARR-3). Misfiling waves as lobes is how program sprawl happens.

**Scope fence:** No lobe charter for Claim Reliability; residue waves authorized separately.

**Forbidden actions:**
  - charter Claim Reliability as a Neural Web lobe

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> Claim Reliability / Narrative Truth | **NOT a lobe** — decomposes into: already-built (QI's `track_record.json`), an R2-rail wave, a bridge wave, and two accrual-gated future experiments

*Owner program: neural-web*

### NWC-U17

**Codex-8 / L8: held-book bridge belongs in Mastermind repo, not this repo**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Portfolio & Thesis-Independence (Codex-8) is docket L8, mostly out-of-scope. The held-book bridge (BOOK-3) is a Mastermind-repo charter, not buildable here. The in-scope slice (reflexivity.py + board chips, ~70% built) is handled by W-D. No new held-book infrastructure is authorized.

**Scope fence:** Held-book bridge is Mastermind repo scope only; this repo handles in-scope residue via W-D only.

**Forbidden actions:**
  - build held-book bridge in this repo
  - authorize BOOK-3 in macro-dashboard

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> Portfolio & Thesis-Independence | **IS docket L8** (mostly out-of-scope; held-book = Mastermind repo). In-scope slice already ~70% built (`reflexivity.py` + board chips)

*Owner program: neural-web*

### NWC-U18

**Codex-7 is docket L6; gate unchanged, no charter issued**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Macro & Policy Transmission (Codex-7) is docket L6 (Tier-2, gated). The gate is unchanged: Phase-0 must beat the noisy-sector precedent OOS. No charter is issued by this program. W-C authorizes only the gate-clearing Phase-0 study.

**Scope fence:** No L6 charter; only gate-clearing study authorized.

**Forbidden actions:**
  - issue L6 charter before P0 passes and cap releases

**Unblock condition:** P0 must beat noisy-sector precedent OOS AND lobe cap must release

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> Macro & Policy Transmission | **IS docket L6** (Tier-2, gated). Gate unchanged: Phase-0 must beat the noisy-sector precedent OOS. No charter.

*Owner program: neural-web*

### NWC-U19

**PR-D prereg must be committed BEFORE harness runs**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The L6-P0 prereg document (`research/macro_tx/L6_PHASE0_PREREG.md`) must be Fable-written and committed before the harness runs (BD_PHASE0 pattern). The prereg is the single numeric authority. The report (`research/macro_tx/L6_PHASE0_REPORT.md`) must print all cells including nulls; the word 'validated' may not appear in it.

**Forbidden actions:**
  - run L6-P0 harness before prereg is committed
  - use word 'validated' in L6 report

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> The prereg is the single numeric authority (BD_PHASE0 pattern — this section deliberately does not restate thresholds it will freeze)

*Owner program: neural-web*

### NWC-U2

**Lobe cap fully consumed; no additional charters this cycle**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The two-lobe concurrency cap is fully consumed by L1 short-side and L3 dispersion. Even if L6-P0 passes all axes, a charter re-opening is subject to the cap and is NOT automatic. A pass only re-opens the L6 charter question at the docket.

**Scope fence:** No additional lobe charters until cap releases.

**Forbidden actions:**
  - auto-charter L6 on P0 pass
  - exceed two-lobe cap

**Unblock condition:** Lobe cap must release before any new charter can be issued

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> two-lobe concurrency cap is fully consumed (L1 short-side + L3 dispersion, both chartered 2026-07-06)

*Owner program: neural-web*

### NWC-U3

**No composite macro score; Signal Commons R3 applies to macro axes**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Signal Commons R3 positioning-fusion ruling applies to macro axes with full force. No composite macro-hostility score may be formed at any grain. Each axis (rates, USD, credit, liquidity) reads out separately. This prohibition extends beyond L6-P0 to the entire scope of this program.

**Scope fence:** No fused macro composite at any stage of this program.

**Forbidden actions:**
  - form composite macro-hostility score
  - fuse macro axes
  - create macro composite index

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> No fused macro composite (Signal Commons R3 stands); no per-name macro fingerprints (L6 gate stands until P0 passes AND a charter is issued).

*Owner program: neural-web*

### NWC-U4

**No held-book data in this repo; Mastermind two-organisms law**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No held-book data, bot.db read path, or held-book bridge is buildable in this repo. `mastermind_context.py` is entirely outbound. BOOK-3 held-book bridge belongs to the Mastermind repo. The two-organisms law means this repo and Mastermind are separate organisms with no bidirectional data flow.

**Scope fence:** No held-book reads, sizing, or gross_mult unclamping permitted here.

**Forbidden actions:**
  - add held-book data read path
  - read bot.db from this repo
  - add sizing logic
  - unclamp gross_mult

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> No held-book anything (L8 → Mastermind repo; two-organisms law); no sizing, no gross_mult unclamping; no CN/HK reflexivity expansion (R-E stands).

*Owner program: neural-web*

### NWC-U5

**No kernel cells or conditioning before 2026-10 FDR batch**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Signal Commons R1 denial of kernel conditioning stands until 2026-10. No kernel cells, no kernel consumers, and no kernel conditioning may be introduced by any wave in this program. The L6-P0 study must leave kernel untouched.

**Scope fence:** Kernel is off-limits until 2026-10 FDR batch clears.

**Forbidden actions:**
  - add kernel cell
  - add kernel consumer
  - condition on kernel output

**Unblock condition:** 2026-10 FDR batch completion

**Come back on:** 2026-10-01 (experiment: `neuralweb-kernel-q1-batch`)

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> No kernel cells, consumers, or conditioning before the 2026-10 FDR batch (Signal Commons R1 denial stands).

*Owner program: neural-web*

### NWC-U7

**MASTERMIND_NW_CONTEXT bridge stays dark; arming gate unchanged at come-back 2026-07-19**

- Status: `deferred` | Kind: `context` | Nondelegable: `False`

**Ruling:** The MASTERMIND_NW_CONTEXT bridge remains dark (defaults OFF). The arming gate is unchanged. W-B PR adding the `claim_reliability` lobe key does not touch arming. Come-back for arming decision is 2026-07-19.

**Scope fence:** Bridge arming not permitted by this program; arming is a separate gate.

**Forbidden actions:**
  - arm MASTERMIND_NW_CONTEXT in W-B PR
  - change arming gate logic

**Unblock condition:** 2026-07-19 arming come-back

**Come back on:** 2026-07-19

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> The bridge remains dark (MASTERMIND_NW_CONTEXT defaults OFF; arming gate unchanged, come-back 2026-07-19 — this PR does not touch arming).

*Owner program: neural-web*

### NWC-U8

**L6-P0 budget declared as 12 cells before run; labeling as descriptive to evade budget is forbidden**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** Declared budget = 12 (4 axes × 3 horizons) and must be logged with `log_declared_budget(12)` BEFORE the run. The h5 and h63 horizons are printed as descriptive but are budget-counted because labeling computed cells 'descriptive' to exempt them from the budget is the forking-paths laundering that RUL-P3 exists to prevent.

**Forbidden actions:**
  - label h5/h63 cells descriptive to avoid budget count
  - run harness before log_declared_budget call
  - set budget below 12

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> `log_declared_budget(12)` BEFORE the run; BH q=0.10 across the 4 primary h21 cells; every results summary prints the cumulative pooled `macro_tx` trial count

*Owner program: neural-web*

### NWC-U9

**L6-P0 must control contemporaneous market drawdown as covariate**

- Status: `active_law` | Kind: `study` | Nondelegable: `False`

**Ruling:** Hostile macro windows correlate mechanically with stressed tapes. The study must control contemporaneous market drawdown exactly as DISP-GATE-1's prereg does, using stratification (not regression residualization) with frozen strata in the prereg. This prevents the study from merely rediscovering that stressed tapes are stressed.

**Forbidden actions:**
  - omit drawdown covariate control
  - use regression residualization instead of stratification

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> drawdown-covariate control** — macro-hostile windows correlate mechanically with stressed tapes; the study must control contemporaneous market drawdown exactly as DISP-GATE-1's prereg does

*Owner program: neural-web*

### RUL-C1

**No new lobes chartered; two-lobe cap stays at L1+L3**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No new lobe is chartered by this program. The two-lobe concurrency cap (docket §6) remains fully consumed by L1 short-side and L3 dispersion, both chartered 2026-07-06. Everything authorized below is a rail wave, an existing-artifact wave, or a registered study — not a charter.

**Scope fence:** No lobe charters may be issued by this program; cap stays L1+L3.

**Forbidden actions:**
  - issue new lobe charter
  - exceed two-lobe concurrency cap

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> The docket's two-lobe concurrency cap is fully consumed (L1 short-side + L3 dispersion, both chartered 2026-07-06)

*Owner program: neural-web*

### RUL-C10

**LLM law: no LLM scoring, escalation, or origination in this program**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Nothing in this program lets an LLM score, escalate, or originate. The W-B bridge carries qledger measured statistics into the bridge at display tier, additively. The cortex may cite these statistics but never adjust them.

**Scope fence:** LLM may only cite measured qledger statistics; it may not score, adjust, or originate from them.

**Forbidden actions:**
  - allow LLM to score claim reliability
  - allow LLM to escalate from qledger stats
  - allow LLM to originate reliability judgments

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> nothing in this program lets an LLM score, escalate, or originate. W-B carries qledger *measured* statistics into the bridge (display tier, additive); the cortex may cite them, never adjust them.

*Owner program: neural-web*

### RUL-C11

**L6-P0 FDR family is macro_tx (flat pooled, new family, sub-scoping prohibited)**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** The flat `fdr_family='replay'` mandated by the docket governs the rule-replay tape; L6-P0 is a conditioning contrast study on a different tape (spine index) with no RuleSpec grid, and the register CLI structurally cannot carry it. Following the standalone-harness precedent, L6-P0 integrates TrialLedger directly under a new flat pooled family `fdr_family='macro_tx'` — the single family for ALL present and future macro-conditioning studies. Sub-scoping is prohibited for the same reason the replay family is flat. Declared budget = 12 (4 axes × 3 horizons); labeling computed cells 'descriptive' to exempt them from the budget is forking-paths laundering.

**Scope fence:** All macro-conditioning studies must use fdr_family='macro_tx'; sub-scoping prohibited.

**Forbidden actions:**
  - sub-scope macro_tx family
  - label computed cells descriptive to avoid budget
  - use fdr_family='replay' for conditioning contrast studies
  - use register_rule_experiment.py for L6-P0

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> L6-P0 integrates `TrialLedger` directly under a NEW flat pooled family **`fdr_family='macro_tx'`** — the single family for ALL present and future macro-conditioning studies, sub-scoping prohibited for exactly the reason the replay family is flat

*Owner program: neural-web*

### RUL-C2

**Bridge lobe key must be `claim_reliability`, never `reliability`**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** The bridge lobe key is `claim_reliability`, never `reliability`. The key `lobes['reliability']` already exists in `mastermind_context.py` with kernel-FDR-governance scope and a test-enforced standing_law string. Clobbering it is forbidden.

**Scope fence:** Key naming is fixed; `lobes['reliability']` must not be overwritten.

**Forbidden actions:**
  - use key name 'reliability' for claim-reliability lobe
  - clobber existing reliability lobe key

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> the bridge lobe key is `claim_reliability`, never `reliability` — `lobes['reliability']` already exists in `mastermind_context.py` with kernel-FDR-governance scope and a test-enforced standing_law string. Clobbering it is forbidden.

*Owner program: neural-web*

### RUL-C3

**QI owns qledger grading semantics; NWC is read-only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Qledger and its grading semantics belong to the QI program (frozen since #1180; joint substrate ruling open). Legal here: read-only coverage/accountability diagnostics (W-A) and read-only NW bridge integration (W-B). Illegal here: any learned source-reliability score, any per-source weighting, any change to grading semantics — that work is QI's deferred keystone (≥500 graded labels) and stays theirs. W-A/W-B PRs must not modify `scripts/grade_qledger.py` or claim schemas.

**Scope fence:** Read-only access to qledger; no semantic or schema changes permitted.

**Forbidden actions:**
  - modify grade_qledger.py
  - change claim schemas
  - create learned source-reliability score
  - add per-source weighting

**Unblock condition:** ≥500 graded labels in QI program before learned source-reliability work is permitted

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> qledger and its grading semantics belong to the QI program (frozen since #1180; joint substrate ruling open). Legal here: read-only coverage/accountability diagnostics (W-A) and read-only NW bridge integration (W-B). ILLEGAL here: any learned source-reliability score, any per-source weighting, any change to grading semantics

*Owner program: neural-web*

### RUL-C4

**L6-P0 legal shape: per-axis, no fusion, sector grain, PIT, governor-registered**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** The L6 Phase-0 is a registered measurement, not a live conditioner. It must be per-axis (never fused — Signal Commons R3 applies), sector/basket/board grain only (no per-name regressions), PIT-flagged at fire date with frozen thresholds committed before any overlap is computed, governor-registered under fdr_family='macro_tx', kernel untouched, and must control contemporaneous market drawdown as a covariate. A pass re-opens the L6 charter question at the docket; a fail prints the null and L6 stays gated.

**Scope fence:** L6-P0 is a measurement study only; no live flag, chip, or world_state key may result from it.

**Forbidden actions:**
  - fuse macro axes into composite score
  - run per-name regressions
  - use kernel cells
  - skip drawdown covariate control
  - form composite macro-hostility score

**Unblock condition:** Sign-stable + episode-clustered CI excluding 0 in both OOS halves per axis — required for L6 charter to re-open

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> per-axis, never fused** — the Signal Commons R3 positioning-fusion ruling applies to macro axes with full force; no composite macro-hostility score may be formed, each axis reads out separately

*Owner program: neural-web*

### RUL-C5

**NARR-3 narrative-vs-price arbitration: no-build, registered come-back**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** The question of when narrative and price disagree is retro-gradeable using committed artifacts (world_state.json, confluence graph) as PIT tape. No new nightly grader ships. Registered as a come-back experiment with earliest useful read ~2026-10-01, requiring ~3 months of contradiction records plus matured 21d qledger grades.

**Scope fence:** No new nightly grader; no build authorized until come-back date.

**Forbidden actions:**
  - build new nightly grader for narrative arbitration
  - ship narrative-price arbitration logic before come-back

**Unblock condition:** ~3 months of contradiction records + matured 21d qledger grades (~2026-10-01)

**Come back on:** 2026-10-01 (experiment: `narr-3-contradiction-arbitration`)

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> when narrative and price disagree, who wins" is retro-gradeable: contradiction records land in committed artifacts (`world_state.json`, confluence graph) whose git history is the PIT tape. No new nightly grader ships (the cap protects nightly/review bandwidth). Registered as a come-back experiment: earliest useful read ~2026-10-01

*Owner program: neural-web*

### RUL-C6

**NARR-2 story decay curves: calendar-gated, no build, registered come-back**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** Family-level decay curves for qledger claims are calendar-gated on 21d/63d grade maturation. Registered as a come-back experiment (~2026-10-01). When grades mature, qledger families join the existing kernel family decay surface (`kernel_families.json`); no parallel apparatus is authorized.

**Scope fence:** No parallel decay apparatus; join kernel_families.json surface only when grades mature.

**Forbidden actions:**
  - build parallel qledger decay apparatus before grade maturation
  - ship story-decay curves before 21d/63d grades exist

**Unblock condition:** 21d/63d qledger grade maturation (~2026-10-01)

**Come back on:** 2026-10-01 (experiment: `narr-2-story-decay`)

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> family-level decay curves for qledger claims are calendar-gated on 21d/63d grade maturation. Registered as a come-back experiment (~2026-10-01). The kernel already ships family decay curves for spine families (`kernel_families.json`); qledger families join that surface when their grades mature, they do not get a parallel apparatus.

*Owner program: neural-web*

### RUL-C7

**Reflexivity wave stays under its existing rulings (R-A, R-E, R-F/R7)**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** Prior rulings R-A (held-agnostic), R-E (US board only), and R-F/R7 (display-only, `is_context_only`, no behavioral consumer) all stand. The earnings-week leg ships only if an earnings-calendar source already exists in-repo; if not, the builder prints the gap and ships the other two legs — no new collector is authorized by this program.

**Scope fence:** Display-only; US board only; no held-book inputs; no behavioral consumer.

**Forbidden actions:**
  - use held-book data in reflexivity
  - expand reflexivity to CN/HK
  - create behavioral consumer of reflexivity output
  - authorize new collector for earnings data

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> R-A (held-agnostic), R-E (US board only), R-F/R7 (display-only, `is_context_only`, no behavioral consumer) all stand. The earnings-week leg ships only if an earnings-calendar source already exists in-repo

*Owner program: neural-web*

### RUL-C8

**Bandwidth accounting: zero new lobes, zero new nightly graders**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Zero new lobes and zero new nightly graders are authorized. W-A rides the existing end-of-collect audit call chain (seconds); W-B is an additive key in an existing nightly compiler; W-D extends the existing reflexivity overlay build which already re-renders us_stocks_v2.html (seconds-scale, not off-render); W-C is an off-render manual study. Net new nightly cost: seconds.

**Scope fence:** No new nightly graders or render-path additions permitted by this program.

**Forbidden actions:**
  - add new nightly grader
  - add new render-path step

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> zero new lobes, zero new nightly graders. W-A rides the existing end-of-collect audit call chain in `scripts/collect.py` (seconds); W-B is an additive key in an existing nightly compiler

*Owner program: neural-web*

### RUL-C9

**Registration hygiene: every new artifact registers in synapse.yml + SIGNAL_BUS**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Every new artifact must register in `config/synapse.yml` (tier, horizon_role, scored_path_surfaces, weights) with `docs/SIGNAL_BUS.md` regenerated in the same PR. Every new write path declares its commit path per RUL-P10 (gitignored / single-writer git / R2). Come-back experiments register in the experiments registry so the admin Experiments tab carries their dates.

**Forbidden actions:**
  - ship artifact without synapse.yml registration
  - omit SIGNAL_BUS.md regeneration from PR
  - skip experiments registry for come-back studies

**Source:** `research/NW_CODEX_THREE_LOBES_ADJUDICATION_BY_FABLE.md`
> every new artifact registers in `config/synapse.yml` (tier, horizon_role, scored_path_surfaces, weights) with `docs/SIGNAL_BUS.md` regenerated in the same PR; every new write path declares its commit path per RUL-P10

*Owner program: neural-web*

### NWF3-U1

**Trial-budget: TrialLedger per-family max stays 15; pooled replay sum must be disclosed**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The TrialLedger per-family max()-basis remains 15 (the largest single declared budget) unless a larger grid registers. Both the per-family max and pooled sum numbers must be disclosed in any future promotion prereg.

**Forbidden actions:**
  - omit per-family max and pooled sum from promotion prereg

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> TrialLedger per-family max()-basis remains 15 (largest single declared budget) unless a larger grid registers; both numbers must be disclosed in any future promotion prereg.

*Owner program: neural-web*

### NWF3-U2

**L2 charter spec pre-written; thesis-exit join uses long-hold falsifier as context only**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The L2 Exit & Trim charter spec is pre-written incorporating RUL-F3.15 roles, arbitration order, and RUL-F3.2/F3.3 laws. The thesis-exit join uses long-hold falsifier tripwires as context, never as authority. L2 is blocked on L1 or L3 completing to free a cap slot.

**Forbidden actions:**
  - use long-hold falsifier tripwires as exit authority
  - charter L2 while cap is consumed

**Unblock condition:** L1 or L3 completing to free a cap slot.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> L2 Exit & Trim charter (role state builder, thesis-exit join, exit-role nightly surface) | L1 or L3 completing → freed cap slot | Charter spec pre-written: RUL-F3.15 roles + arbitration + RUL-F3.2/F3.3 laws; thesis-exit join uses long-hold falsifier tripwires as context, never authority.

*Owner program: neural-web*

### NWF3-U3

**L5 Execution charter: passport annotate-only, CN/HK spread UNKNOWN until calibrated**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The L5 Execution charter requires: tier=infrastructure, annotate-only pinned in schema, a CI check failing any template that joins tradability bands into visibility/rank without a registered gate. Capacity must be at operator sizes only with explicit per-name participation rule. CN/HK spread is UNKNOWN until calibrated (limit-day H==L pathology). L5 is blocked on a freed cap slot plus off-render scheduling decision.

**Scope fence:** Annotate-only; no tradability bands joined into visibility/rank without registered gate.

**Forbidden actions:**
  - join tradability bands into visibility or rank without registered gate
  - claim CN/HK spread estimates before calibration
  - build execution passport without L5 charter

**Unblock condition:** Freed cap slot plus off-render scheduling decision.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> L5 Execution charter (execution passport artifact, capacity curves, universe-segmented cost models) | Freed cap slot + off-render scheduling decision | Passport requires: tier=infrastructure, annotate-only pinned in schema

*Owner program: neural-web*

### NWF3-U4

**NET-REPLAY-1 gross/net always side-by-side; no net figure may replace gross**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Gross and net figures must always appear side-by-side in NET-REPLAY-1 outputs. Net figures never replace gross results. Every assumption must be stamped. This is an explicit guardrail from the Codex §9 guardrails preserved by Fable.

**Scope fence:** Gross and net always paired; net cannot stand alone.

**Forbidden actions:**
  - display net figures without gross
  - allow net to replace gross result
  - omit assumption stamps

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Net-of-friction discipline: never replace the gross result; stamp every assumption.

*Owner program: neural-web*

### NWF3-U5

**No gross_mult unclamp and no dispersion sizing permitted**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No promotion from seen surfaces without a new gate plus contamination stamp. No gross_mult unclamping permitted. No dispersion-based sizing permitted. These are explicitly preserved Codex §9 guardrails.

**Scope fence:** Dispersion output must not affect sizing; gross_mult must remain clamped.

**Forbidden actions:**
  - unclamp gross_mult
  - use dispersion output for sizing
  - promote from seen surface without new gate and contamination stamp

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> no promotion from seen surfaces without new gate + contamination stamp; no gross_mult unclamp; no dispersion sizing

*Owner program: neural-web*

### NWF3-U8

**Dispersion conditioning matrix: every row/column needs own 25-cluster floor**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** Every added row or column in any future dispersion conditioning matrix must clear its own 25-cluster floor independently. derived_from_surface=disp_gate_1 is mandatory for all conditioning matrix work. First surface is ONE row only.

**Scope fence:** Each conditioning matrix cell requires independent 25-cluster floor verification.

**Forbidden actions:**
  - add conditioning matrix row/column without independent 25-cluster floor
  - omit derived_from_surface=disp_gate_1

**Unblock condition:** DISP-GATE-1 readout printed and L3 charter extension.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> every added row/column clears its own 25-cluster floor; `derived_from_surface=disp_gate_1` mandatory.

*Owner program: neural-web*

### RUL-F3.1

**No new lobe charter ships; two-lobe cap remains consumed by L1+L3**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** No new lobe charter ships in the Final-3 program. The two-lobe concurrency cap is fully consumed by L1 (short-side) and L3 (dispersion). All Final-3 work must ship as R1-registered experiments, research-lane derivations, ops harnesses, or docs. L2 and L5 charters queue behind freed cap slots.

**Scope fence:** No lobe charter may ship while L1 and L3 occupy both concurrency cap slots.

**Forbidden actions:**
  - charter a new lobe while cap is consumed
  - ship L2 or L5 builder without freed cap slot

**Unblock condition:** L1 or L3 completing and freeing a cap slot.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> No new lobe charter ships in this program. The two-lobe concurrency cap remains consumed by L1 (short-side) + L3 (dispersion).

*Owner program: neural-web*

### RUL-F3.10

**Tax engine killed; scenario-rate table ships; ST_TAX hard-code fixed**

- Status: `killed` | Kind: `study` | Nondelegable: `False`

**Ruling:** Codex's tax engine (tax_sensitivity.py, tax lots, wash-sale hooks) is KILLED as over-engineering on unknowable inputs. What ships is a scenario-rate table with symbolic rates 0/15/20/35/40% printed as assumptions, not advice. The real tax kink is at ~1 year, so the comparison must reach 252d horizon. The live hard-coded ST_TAX=0.35 in spvector_baseline.py and build_spvector.py becomes a documented scenario parameter.

**Scope fence:** Tax output is scenario assumptions only, not tax advice; no live tax engine.

**Forbidden actions:**
  - build engine/tax_sensitivity.py
  - build tax lot tracking
  - build wash-sale hooks
  - give tax advice from scenario table

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Codex's tax engine (`engine/tax_sensitivity.py`, tax lots, wash-sale hooks, jurisdiction config) is KILLED as over-engineering on unknowable inputs.

*Owner program: neural-web*

### RUL-F3.11

**Realized-Decision Passport killed; revisit only after L2 and L5 charters both live**

- Status: `killed` | Kind: `context` | Nondelegable: `True`

**Ruling:** The Realized-Decision Passport is NOT built. The repo already has three passport-like objects (engine/passport.py badge states, rule-experiment registry provenance, regime.json passport block). Execution context rides existing synapse registration and engine/passport.py provenance chips. Revisit only after both L2 and L5 charters exist. Any future per-decision outcome-carrying object must obey keep-FIRST PIT invariant and nightly-sole-advancer law.

**Forbidden actions:**
  - build Realized-Decision Passport before L2 and L5 charters both live
  - bypass PIT keep-FIRST invariant in any outcome-carrying object
  - bypass nightly-sole-advancer law in passport objects

**Unblock condition:** Both L2 and L5 charters must be live.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> The Realized-Decision Passport is NOT built. The repo already has three passport-like objects (engine/passport.py badge states; the rule-experiment registry provenance from #1681; regime.json's passport block).

*Owner program: neural-web*

### RUL-F3.13

**Exit-crowding L1-L3 hard-blocked on ThetaData EOD pass; BD-AVOID-1 is separate program**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Exit-crowding L1-L3 remain hard-blocked on the ThetaData EOD universe pass (external gate, not a code task). L4 stays ACCRUE with no prereg weakening. BD-AVOID-1 (avoid-long) is a separate program with its own prereg. Codex's conflation of the exit-crowding and avoid-long label streams is rejected.

**Scope fence:** L1-L3 crowding work is externally gated; no code workarounds permitted.

**Forbidden actions:**
  - build exit-crowding L1-L3 without ThetaData EOD universe pass
  - weaken L4 ACCRUE prereg
  - conflate exit-crowding with BD-AVOID-1 label streams

**Unblock condition:** ThetaData EOD universe pass (external gate).

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Exit-crowding L1–L3 remain hard-blocked on the ThetaData EOD universe pass (external gate, not a code task); L4 stays ACCRUE with no prereg weakening. BD-AVOID-1 (avoid-long) is a **separate program** with its own prereg

*Owner program: neural-web*

### RUL-F3.15

**Six-exit-problems taxonomy is charter-ready spec for L2 only; no nightly builder yet**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Codex's six-exit-problems taxonomy is preserved as the future L2 charter's role vocabulary, amended with: pre-outcome role assignment (RUL-F3.3), a deterministic arbitration order (thesis_break > tail_flag > time_exit > trim > do_nothing) plus an explicit multiple_roles_fired honest-null output, and RUL-F3.2's fire-tape framing. No nightly builder ships until an L2 slot frees.

**Scope fence:** Charter-ready spec only; no nightly builder until L2 slot frees.

**Forbidden actions:**
  - build exit-role nightly surface without L2 charter
  - use outcome paths in exit-role assignment

**Unblock condition:** L2 cap slot freed.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Codex's six-exit-problems taxonomy is preserved (§4.4) as the future L2 charter's role vocabulary, amended with: pre-outcome role assignment (RUL-F3.3), a deterministic arbitration order (`thesis_break > tail_flag > time_exit > trim > do_nothing`)

*Owner program: neural-web*

### RUL-F3.2

**Exit/trim metrics attach to fire-tape counterfactuals only; no position-monitor display**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`

**Ruling:** The repo has no held-position ledger; hold_state/hold_days are null and portfolio construction is Mastermind's domain. All Exit and Trim metrics must attach to fire events on the replay tape. Every artifact and report must say 'fire-tape counterfactual'; field names use hypothetical_policy/counterfactual_path semantics. No display may read as a live position monitor.

**Scope fence:** Display of exit metrics must be framed as fire-tape counterfactual, never as live position monitoring.

**Forbidden actions:**
  - display exit metrics as live position state
  - use hold_state/hold_days as if populated
  - omit fire-tape counterfactual label from exit artifacts

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> This repo has **no held-position ledger** (retro_grades `hold_state`/`hold_days` are null; portfolio construction is docket-L8/Mastermind). All Exit & Trim metrics attach to **fire events** on the replay tape.

*Owner program: neural-web*

### RUL-F3.3

**Classifier labels must use pre-outcome state only; look-ahead labels blocked**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Role and classifier labels must be computed from pre-outcome state only: EMA8 breach state, reversion-window elapsed, thesis/falsifier state, and crowding state at fire+k. Outcome paths such as foregone MFE, avoided MAE, and forward returns are held-out targets, never features. exit_helped_21-style look-ahead labels are blocked as classifier targets-cum-features.

**Scope fence:** No classifier may use outcome paths as features; targets are strictly held-out.

**Forbidden actions:**
  - use foregone MFE as a classifier feature
  - use exit_helped_21-style look-ahead labels
  - use forward returns as classifier inputs

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Role/classifier labels must be computed from **pre-outcome state only** (EMA8 breach state, reversion-window elapsed, thesis/falsifier state, crowding state at fire+k). Outcome paths (foregone MFE, avoided MAE, forward returns) are held-out **targets**, never features.

*Owner program: neural-web*

### RUL-F3.4

**exit_regret_v2.py killed; re-entry metrics deferred until pre-outcome trigger registered**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** Standalone exit_regret_v2.py is KILLED as a governor bypass with 4 of its 10 metrics already shipped in EXIT-GRID-1. The computable increments ride TRIM-GRID-1 and NET-REPLAY-1. false_exit_cost, late_exit_cost, and re-entry metrics are deferred until a pre-outcome re-entry trigger is specified and registered.

**Forbidden actions:**
  - build standalone exit_regret_v2.py
  - bypass governor with standalone regret script

**Unblock condition:** Pre-outcome re-entry trigger specified and registered as an experiment.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Standalone `scripts/research/exit_regret_v2.py` is KILLED (governor bypass; 4/10 metrics already shipped in EXIT-GRID-1).

*Owner program: neural-web*

### RUL-F3.5

**ExitPolicy amended to add 'scaled' composite; TRIM-GRID-1 descriptive-only, 6 cells**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`

**Ruling:** The frozen R1 v1 ExitPolicy enum is amended to add scaled(legs=[(fraction, leg_policy),...]) where every leg_policy is drawn from existing frozen v1 vocabulary and fractions sum to 1. TRIM-GRID-1 is exactly 6 pre-registered cells, derived_from_surface=exit_grid_v1, verdict_criteria='descriptive-only', pooled family 'replay'. Any promotion prereg requires a fresh OOS window with fires >= 2026-H2 plus stricter thresholds.

**Scope fence:** TRIM-GRID-1 is descriptive-only; promotion requires fresh OOS window fires >= 2026-H2.

**Forbidden actions:**
  - add leg_policy outside frozen v1 vocabulary
  - promote trim policy from seen surface without fresh OOS window
  - exceed 6 pre-registered cells in TRIM-GRID-1

**Unblock condition:** Fresh OOS window with fires >= 2026-H2 for any promotion prereg.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> TRIM-GRID-1 = exactly 6 pre-registered cells (§4.2), `derived_from_surface=exit_grid_v1`, `verdict_criteria='descriptive-only'`, pooled family `replay`.

*Owner program: neural-web*

### RUL-F3.6

**DISP-GATE-1 build spec: feasibility gate first, fixed universe, vol tercile added**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** DISP-GATE-1 must implement three amendments: feasibility/exclusion gate prints first (exclude fires lacking >=252 prior panel bars, print exclusion count before any statistic); universe construction held fixed across PIT reconstruction with per-date name count printed; realized-vol tercile added as a second printed covariate split (descriptive only, no budget change). DEFER triggers if gap sign + >=5pp magnitude fails on either expanding or trailing-252 basis. PASS enables a display flag only.

**Scope fence:** DISP-GATE-1 PASS enables a display flag only; no ranked-output authority.

**Forbidden actions:**
  - skip feasibility gate
  - allow universe to drift across PIT reconstruction
  - promote from DISP-GATE-1 without fresh gate

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> PASS enables a display flag only.

*Owner program: neural-web*

### RUL-F3.7

**Display-only guarantee tested in CI: risk_sizing must receive regime_gross==1.0**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Before any dispersion enrichment is chartered, the display-only guarantee must be tested: risk_sizing must receive regime_gross==1.0 from the dispersion path, asserted in CI-run unit tests. The guarantee currently rests on a single constant which is insufficient once feature stores exist.

**Scope fence:** CI must assert regime_gross==1.0 at the risk_sizing boundary for any dispersion path.

**Forbidden actions:**
  - charter dispersion enrichment without CI-tested regime_gross==1.0 invariant

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Before any dispersion enrichment is ever chartered, the display-only guarantee gets a test: `risk_sizing` must receive `regime_gross == 1.0` from the dispersion path, asserted in CI-run unit tests.

*Owner program: neural-web*

### RUL-F3.8

**Dispersion feature store, residual-trust model, conditioning matrix deferred**

- Status: `deferred` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** The dispersion feature store, residual selection-trust model, and lobe-conditioning matrix are NOT built now: they are unchartered, forking-paths-contaminating (slicing the same tape DISP-GATE-1 rules on), and n-starved. When eventually chartered, the first conditioning surface is ONE row: {Entry fires} x {lean_in/neutral/lean_out} x {stop5, dead_money}. Every added row/column requires its own 25-cluster floor and derived_from_surface=disp_gate_1.

**Forbidden actions:**
  - build dispersion feature store before DISP-GATE-1 readout
  - add conditioning matrix row/column without 25-cluster floor
  - build residual selection-trust model before L3 charter extension

**Unblock condition:** DISP-GATE-1 readout printed plus L3 charter extension; single powered row first.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Feature store, residual selection-trust model, and the lobe-conditioning matrix are NOT built now: unchartered, forking-paths-contaminating (they slice the same tape DISP-GATE-1 rules on), and n-starved

*Owner program: neural-web*

### RUL-F3.9

**NET-REPLAY-1: research-lane descriptive re-pricing only; no policy preferences without new gate**

- Status: `active_law` | Kind: `study` | Nondelegable: `False`

**Ruling:** NET-REPLAY-1 is a research-lane descriptive derivation re-pricing already-seen replay cells only; no new policy comparisons or new trial cells. Gross and net must always appear side-by-side. Position size grid is per-position {10k, 100k, 1m} to avoid the multi-name participation fallacy. Unmodeled frictions must be printed as not-modeled. Nothing net-based may prefer a policy without a new registered gate.

**Scope fence:** Research-lane descriptive derivation only; no verdict language; no policy preference without registered gate.

**Forbidden actions:**
  - add new trial cells to NET-REPLAY-1
  - make book-level AUM claims
  - prefer a policy from net figures without new registered gate
  - omit unmodeled frictions disclosure

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> Net-of-friction re-pricing of the **already-seen** replay cells (exit_grid_v1 + wait_grid_v1) is a research-lane descriptive derivation: no new policy comparisons, no new trial cells, stamped `derived_from_surface: exit_grid_v1, wait_grid_v1`.

*Owner program: neural-web*

### LIVE-U1

**Six organs all display/ops-tier; zero new trading authority — architectural decree**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** The NW live operating layer consists of exactly six organs (honest cortex, sensory refresh, vitals health.json, morning report daily_brief.json, ops surfaces, conformance rails). All are display/ops-tier. Zero new trading authority is introduced by any of them.

**Scope fence:** Scopes the entire NW live operating layer to display/ops tier only.

**Forbidden actions:**
  - adding trading authority to any of the six organs
  - adding a seventh organ with trading authority

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> Six organs; all display/ops-tier; zero new trading authority.

*Owner program: neural-web*

### LIVE-U2

**Degrade-never-raise: cortex job always exits 0; red is display state not CI gate**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** The cortex job always exits 0 regardless of deliberation outcome. Red is a display state shown to operators, not a CI/deploy gate. This preserved constraint prevents cascading publish failures from cortex quality issues.

**Scope fence:** Cortex job exit behavior only.

**Forbidden actions:**
  - exiting cortex job non-zero on any deliberation failure
  - using cortex run_status as CI gate

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> Degrade-never-raise preserved: the cortex job still always exits 0 — red is a display state, not a deploy gate.

*Owner program: neural-web*

### LIVE-U3

**qi domain structurally excluded from daily brief (border ruling pending)**

- Status: `deferred` | Kind: `context` | Nondelegable: `True`

**Ruling:** The qi (qualitative intelligence) domain is structurally excluded from the daily brief scope. A border ruling is pending to formalize the boundary. No qi content may be included in daily_brief.json until the border ruling is issued.

**Scope fence:** daily_brief.json scope only; does not affect qi domain's own surfaces.

**Forbidden actions:**
  - including qi domain items in daily brief before border ruling

**Unblock condition:** Border ruling issued for qi domain inclusion in daily brief.

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> qi domain structurally excluded (border ruling pending).

*Owner program: neural-web*

### LIVE-U4

**Promotion locks already structural: kernel FDR lock 2026-10-01; cortex probation n≥25 Wilson-LB**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A5_GOVERN_TIERS`

**Ruling:** Promotion locks are confirmed structural (KEEP — nothing to build). kernel_decisions.json holds survivors=[], next_batch_due=2026-10-01, standing_law field. Cortex probation is granted=false with n=0 < min_n=25; promotion requires n≥25 graded attention events and Wilson-LB threshold. No code change required.

**Scope fence:** Kernel FDR family promotion and cortex probation authority earn-in.

**Forbidden actions:**
  - bypassing Wilson-LB gate for cortex promotion
  - modifying next_batch_due without Fable ruling
  - granting cortex probation before n≥25

**Unblock condition:** n≥25 graded attention events, hits≥8 for cortex; 2026-10-01 for kernel FDR next batch.

**Come back on:** 2026-10-01

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> | Promotion locks must hold | KEEP — already structural | kernel_decisions.json: survivors=[], next_batch_due=2026-10-01, standing_law field; cortex probation granted=false, n=0 < min_n=25, Wilson-LB law |

*Owner program: neural-web*

### LIVE-U5

**Conformance rails: wiring tests + health workflow_conformance institutionalize registry/workflow mismatch bug class**

- Status: `adopted` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Wiring tests and health workflow_conformance flags institutionalize the registry/workflow mismatch bug class. Daily-engine producers must appear in daily.yml. The duplicate synapse count pin was de-duplicated to floor+membership so a single pin cannot silently fork.

**Scope fence:** All daily-engine producers in synapse registry; enforcement via CI wiring tests.

**Forbidden actions:**
  - adding daily-engine producer without entry in daily.yml
  - maintaining duplicate synapse count pins that can silently fork

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> **Conformance rails**: wiring tests + health workflow_conformance institutionalize the registry/workflow mismatch bug class;

*Owner program: neural-web*

### RUL-LIVE1

**Cortex model calls route through llm_auth waterfall; no single-provider pinning**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** All cortex model calls must be routed through the llm_auth waterfall (401/403 → mark_dead + next provider; transient → bounded retry then skip; mid-conversation failure → one clean restart on next provider). No single-provider pinning is permitted. Every attempt must be recorded in run_status.provider_attempts with error classes.

**Scope fence:** Cortex job provider routing only; does not govern non-cortex LLM calls.

**Forbidden actions:**
  - single-provider pinning
  - bypassing llm_auth waterfall
  - omitting error classes from provider_attempts

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> Cortex model calls route through the llm_auth waterfall; no single-provider pinning; every attempt recorded in run_status.provider_attempts with error classes.

*Owner program: neural-web*

### RUL-LIVE2

**Status taxonomy ok/warn/degraded/skipped; zero-tool and single-call fallback always degraded**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The cortex status taxonomy is exactly: ok, warn, degraded, skipped. Zero-tool deliberation and the single-call fallback are ALWAYS stamped degraded — no exceptions. Staleness-gate skip preserves the last good memo and is not red while the last successful run is within SLA.

**Scope fence:** Applies to cortex run_status block in every memo; all downstream consumers must respect this taxonomy.

**Forbidden actions:**
  - stamping single-call fallback as warn instead of degraded
  - stamping zero-tool run as non-degraded
  - adding status values outside the four-value taxonomy

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE2**: Status taxonomy ok/warn/degraded/skipped. Zero-tool deliberation and the single-call fallback are ALWAYS degraded.

*Owner program: neural-web*

### RUL-LIVE3

**Fail-open: cortex/health/brief failures never block publish; red is display state only**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Cortex, health, and brief failures must never block the publish pipeline. Red/amber/green status is a display state only, not a deploy gate. The cortex job always exits 0; degraded state is surfaced to the operator via display, not via CI failure.

**Scope fence:** Neural Web operating layer only; does not override CI gates for non-cortex failures.

**Forbidden actions:**
  - blocking publish on cortex failure
  - using red status as deploy gate
  - exiting cortex job non-zero on deliberation failure

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE3**: Fail-open preserved — cortex/health/brief failures never block the publish; red is a display state, not a deploy gate.

*Owner program: neural-web*

### RUL-LIVE4

**Bottom sensors wired display-only; scored_path_surfaces stays empty; benchmark ≤30s law**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** build_bottom_sensors is wired between world state and mastermind context as a display-only surface. The benchmark law is ≤30s (measured 2.29s on 2026-07-06). scored_path_surfaces must remain empty ([]) — no ranked-output consumer is permitted.

**Scope fence:** Display-only; scored_path_surfaces stays []; no ranked-output consumer.

**Forbidden actions:**
  - populating scored_path_surfaces
  - adding ranked output consumer to bottom sensors
  - exceeding 30s benchmark

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE4**: Bottom sensors wired display-only; benchmark law ≤30s recorded (2.29s measured 2026-07-06); scored_path_surfaces stays [].

*Owner program: neural-web*

### RUL-LIVE5

**health.json derived from synapse.yml + committed artifacts; no parallel registry; storage-class aware**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** health.json must be DERIVED from synapse.yml plus committed artifacts — no parallel registry is permitted. The admin consumes the artifact; its in-memory computation is demoted to fallback for older clones only. Storage-class aware: R2 artifacts are marked not_locally_verifiable, never 'missing'. Row counts via sidecar/metadata only on the render path (render-budget safe).

**Scope fence:** Applies to data/neuralweb/health.json and site/neuralwebdata/health.json schema neuralweb.health.v1.

**Forbidden actions:**
  - maintaining parallel health registry
  - marking R2 artifacts as missing
  - full row count scans on render path
  - admin computing health in-memory as primary source

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE5**: health.json is DERIVED from synapse.yml + committed artifacts — no parallel registry; admin consumes it; storage-class aware;

*Owner program: neural-web*

### RUL-LIVE6

**Two-phase finalization: engine builds health/brief cores; cortex refreshes and finalizes via narrow-allowlist commit**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Engine job builds health.json and brief cores with cortex_source=previous_run. Cortex job then runs --refresh-cortex after deliberation and commits exactly the two health paths via its narrow-allowlist commit (RUL-NW1 pattern). History rows are as_of-keyed upserts. The engine phase must never write the history ledger.

**Scope fence:** Governs the two-job (engine→cortex) finalization boundary for health.json and daily_brief.json.

**Forbidden actions:**
  - engine phase writing history ledger
  - single-phase health carrying yesterday's cortex status
  - cortex commit outside narrow allowlist

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE6**: Two-phase finalization — engine job builds health/brief cores (cortex marked previous_run); cortex job refreshes the cortex section (--refresh-cortex) and finalizes the brief + history (--finalize) via its narrow-allowlist commit (RUL-NW1 pattern).

*Owner program: neural-web*

### RUL-LIVE7

**Daily brief is deterministic: no LLM prose, no trading verbs, evidence path per claim; no_longer_present not resolved**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The daily brief must be deterministic — no LLM prose, no trading verbs. Trading verbs are blacklisted by test AND scrubbed at runtime from upstream-sourced strings. Every claim must have an evidence path. Contradiction wording law: 'no_longer_present', never 'resolved'.

**Scope fence:** Applies to daily_brief.json and all rendering surfaces that consume it.

**Forbidden actions:**
  - including LLM prose in brief
  - using trading verbs in brief
  - writing 'resolved' for contradictions
  - omitting evidence path from brief items

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE7**: The brief is deterministic — no LLM prose, no trading verbs (unit blacklist + runtime scrub of upstream-sourced strings), evidence path per claim; "no_longer_present" ≠ "resolved".

*Owner program: neural-web*

### RUL-LIVE8

**context_stale self-detection: cortex flags deliberation over stale world_state as warn + P1**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Cortex must detect and flag deliberation over a world_state older than the run date (context_stale). This serves as a silent engine-push-failure detector since the push loop is best-effort 5-attempt by design. context_stale must surface as warn status plus P1 operator attention in the brief.

**Scope fence:** Cortex job only; applies to world_state freshness checking at deliberation time.

**Forbidden actions:**
  - silently deliberating over stale world_state
  - omitting context_stale from run_status
  - failing to surface stale context as P1 operator attention

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE8**: context_stale self-detection — cortex flags deliberation over a world_state older than the run date (silent engine-push-failure detector;

*Owner program: neural-web*

### RUL-LIVE9

**No new authority anywhere in the NW live operating layer; kernel FDR lock and cortex A2 earn-in untouched**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** No new trading authority is granted anywhere in the NW live operating layer. health tier=infrastructure, brief tier=display, weights=none everywhere. The kernel FDR lock (2026-10-01, structural in kernel_decisions.json) and the cortex A2 earn-in (n≥25 graded attention events, hits≥8, Wilson-LB) are untouched by this program.

**Scope fence:** Entire NW live operating layer (all 6 organs); zero new trading authority.

**Forbidden actions:**
  - granting trading authority in health artifact
  - granting trading authority in daily brief
  - modifying kernel FDR lock date
  - modifying cortex A2 earn-in thresholds

**Source:** `research/NW_LIVE_ACTIVATION_ADJUDICATION_BY_FABLE.md`
> - **RUL-LIVE9**: No new authority anywhere: health tier=infrastructure, brief tier=display, weights none everywhere; kernel FDR lock (2026-10-01, structural in kernel_decisions.json) and cortex A2 earn-in (n≥25 graded attention events, hits≥8, Wilson-LB) untouched.

*Owner program: neural-web*

### GAP-RUL-1

**No new lobes — two-lobe cap (L1/L3 only)**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** This program charters zero lobes. L1/L3 remain the chartered set (two-lobe cap). Wave B ships as R1 experiment batches; the qledger table and evidence panel are display/governance surfaces only. Any proposal to charter a new lobe requires a separate adjudication beyond this program.

**Scope fence:** No new lobes chartered in this or derivative programs without separate Fable adjudication.

**Forbidden actions:**
  - charter new lobe
  - add third lobe beyond L1/L3

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> this program charters ZERO lobes. L1/L3 remain the chartered set (two-lobe cap). Wave B ships as R1 experiment batches; the qledger table and evidence panel are display/governance surfaces.

*Owner program: neural-web*

### GAP-RUL-2

**Labels before models — no meta-model until floor reached**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No meta-model, classifier, or trained router may be placed on any surface until its family reaches its registered floors. Codex's meta-labeling task list is adopted as a labels roadmap only, not a build. This constraint applies across all programs consuming NW outputs.

**Scope fence:** No trained/classifier/router model on any surface before registered family floor.

**Forbidden actions:**
  - train meta-model
  - deploy classifier on unmatured family
  - add trained router

**Unblock condition:** Family reaches its registered floor (n_dates >= GRADED_MIN_DATES).

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> no meta-model, classifier, or trained router on any surface until its family reaches its registered floors. Codex's meta-labeling task list is adopted as a *labels roadmap*, recorded here for the future, not built.

*Owner program: neural-web*

### GAP-RUL-3

**Avoid-long quarantine + contamination stamp (BD-AVOID-1)**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** PR-C2 is avoid-long ONLY. The prereg carries derived_from_surface: bd_phase0 with a compensating gate: verdict on forward OOS accrual only, and primary threshold >=8pp (stricter than the >=5pp Phase-0 reading that selected BD-2/BD-3). BD-3's short-favorable>adverse observation stays quarantined as descriptive. Any future short-entry prereg is out of program scope and carries its own stamp.

**Scope fence:** BD-AVOID-1 verdict: avoid-long only; no short-entry from avoid evidence.

**Forbidden actions:**
  - short entry from BD avoid evidence
  - re-use Phase-0 tape for verdict
  - lower threshold below 8pp

**Unblock condition:** A separate out-of-program prereg with its own derived_from_surface stamp is required for short entries.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> PR-C2 is avoid-long ONLY. **The PR-C2 prereg is itself written after seeing the Phase-0 descriptive surface and therefore carries `derived_from_surface: bd_phase0` with a compensating gate (verdict on forward OOS accrual only + primary threshold ≥8pp, stricter than the ≥5pp reading that selected BD-2/BD-3; §6).**

*Owner program: neural-web*

### GAP-RUL-4

**Clocks not busywork — TIME-starved ledgers get clocks only**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** TIME-starved ledgers receive maturity clocks on the evidence panel and never receive make-work graders. The panel must render the TIME-vs-BUILD distinction so '16 grader-starved' can never again be read as 16 builds. The TIME/BUILD distinction is a required display field.

**Scope fence:** Evidence panel must display TIME-vs-BUILD split for all grading-closure entries.

**Forbidden actions:**
  - add grader to TIME-starved ledger
  - suppress TIME-vs-BUILD distinction

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> TIME-starved ledgers get maturity clocks on the evidence panel, never make-work graders. The panel must render the TIME-vs-BUILD distinction so "16 grader-starved" can never again be read as 16 builds.

*Owner program: neural-web*

### GAP-RUL-5

**FDR accounting — budgets logged before runs, pooled SUM printed**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Wave-B experiments pool into flat fdr_family='replay' with budgets logged BEFORE runs. WAIT-GRID-1=10 cells (pooled sum 25), DISP-GATE-1=6 cells (pooled sum 31). PR-C2 logs 2 trials into existing short_side family. Every report prints the cumulative pooled SUM and notes the TrialLedger max()-basis divergence; descriptive-only batches compute no DSR.

**Scope fence:** Budget logging is mandatory before any replay run; pooled SUM printed on all reports.

**Forbidden actions:**
  - run experiment before logging budget
  - omit pooled sum from report
  - compute DSR for descriptive-only batch

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Wave-B experiments pool into flat `fdr_family='replay'` with budgets logged BEFORE runs. Declared budgets: WAIT-GRID-1 = 10 cells (pooled sum 15→25), DISP-GATE-1 = 6 primary cells (pooled sum →31).

*Owner program: neural-web*

### GAP-RUL-6

**De-escalation shape — authority ceiling A3, altdata_brain template**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** The evidence panel and qledger table expose only trust/accrual fields (family, horizon, n_obs, n_dates, hit_rate, wilson_ci_low, state, clocks); no escalation-eligible composite is allowed. Any consuming code routes through constitution.grant_authority() at <= A3_DE_ESCALATE using the altdata_brain template.

**Scope fence:** Display-only trust/accrual fields; no escalation-eligible composite on qledger/evidence panel.

**Forbidden actions:**
  - escalation composite on evidence panel
  - consume without grant_authority()
  - exceed A3_DE_ESCALATE on qledger consumer

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> evidence panel + qledger table expose only trust/accrual fields ({family, horizon, n_obs, n_dates, hit_rate, wilson_ci_low, state, clocks}); no escalation-eligible composite; any consuming code routes through `constitution.grant_authority()` at ≤ A3_DE_ESCALATE (the `altdata_brain` template).

*Owner program: neural-web*

### GAP-RUL-8

**Auth wall stands — no public write endpoint, no CORS widening**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Operator capture stays behind admin auth. No public write endpoint and no CORS widening to public origins. Capture UX moves to the operator's authed console, not the public page. This is a permanent security boundary.

**Scope fence:** All operator capture behind admin auth; no public-side write.

**Forbidden actions:**
  - add public write endpoint
  - widen CORS to public origins
  - move capture UI to public page

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> operator capture stays behind admin auth. No public write endpoint, no CORS widening to public origins. Capture UX moves to the operator's authed console, not the public page.

*Owner program: neural-web*

### GAP-U1

**Scope fence — no fused scores, no sizing changes**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** This program does not introduce fused scores, no meta-models, no new lobes, and no sizing changes (gross_mult stays 1.0). No options tissue consumption until accrual gates (~2026-10/12) open. No short entries; no re-tests of G1's frozen F1 family; no supervised bottom-sensor panel until accrual exists.

**Scope fence:** No fused scores, no sizing changes, no options tissue consumption, no short entries in this program.

**Forbidden actions:**
  - create fused score
  - change gross_mult
  - add options tissue consumption before gate
  - add short entries

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> No new lobes, no meta-models, no fused scores, no sizing changes (gross_mult stays 1.0).

*Owner program: neural-web*

### GAP-U10

**DISP-GATE-1 feasibility gate — PIT recomputation + >=252 bars required**

- Status: `active_law` | Kind: `study` | Nondelegable: `False`

**Ruling:** DISP-GATE-1 has no historical PIT states; the harness must recompute dispersion.assess()'s expanding-window basis per fire date from a reconstructed broad-universe returns panel. It must verify the panel reaches >=252 bars before the earliest fire, exclude fires lacking this, print the exclusion count, and a thin-cohort DEFER is a valid outcome. Descriptive-only this batch; frozen PASS thresholds read only at a later verdict batch.

**Scope fence:** DISP-GATE-1 descriptive-only; no verdict from this batch.

**Forbidden actions:**
  - read verdict from DISP-GATE-1 this batch
  - skip exclusion count print
  - run without verifying 252-bar panel reach

**Unblock condition:** Later verdict batch with L3_PREREG frozen PASS thresholds applied.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> no historical PIT states exist — the harness recomputes `dispersion.assess()`'s expanding-window basis per fire date from a reconstructed broad-universe returns panel (same loader construction as `build_dispersion_regime.py`); it MUST verify and record the panel's earliest date, exclude fires lacking ≥252 prior panel bars, and print the exclusion count before any statistic.

*Owner program: neural-web*

### GAP-U11

**BD-AVOID-1 maturity clock — no verdict before n>=300/side (~2027-01)**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** The BD-AVOID-1 Phase-1 prereg registers the retrospective arrival-rate estimate (BD-3 ~1.4k episodes/yr) and a come-back date when n>=300 episodes/side at 21d maturity is projected (~2027-01 for BD-3). No verdict is read before floor; until then the ledger appears only as an accrual clock row on the evidence panel.

**Scope fence:** BD-AVOID-1 ledger is accrual-only until n>=300/side.

**Forbidden actions:**
  - read BD-AVOID-1 verdict before n>=300/side floor
  - display BD-AVOID-1 as anything other than accrual clock

**Unblock condition:** n>=300 episodes/side at 21d maturity (~2027-01 for BD-3).

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> prereg registers the retrospective arrival-rate estimate (BD-3 ≈ 1.4k episodes/yr, BD-2 higher) and a come-back date ≥ when n≥300 episodes/side at 21d maturity is projected (~2027-01 for BD-3; stated precisely in the prereg). **No verdict is read before floor**

*Owner program: neural-web*

### GAP-U12

**Top-risk de-escalation blocked — S-TOP_RISK accrual gate ~2026-10-15**

- Status: `blocked` | Kind: `wave` | Nondelegable: `False`

**Ruling:** B/TOP_RISK_DEESCALATION (options top-risk replay) is blocked until the S-TOP_RISK accrual gate opens (~2026-10-15, RO-3). It is time-gated, not forgotten. No options tissue consumption is permitted before the gate.

**Scope fence:** No top-risk de-escalation replay before S-TOP_RISK gate opens.

**Forbidden actions:**
  - run top-risk de-escalation replay before 2026-10-15

**Unblock condition:** S-TOP_RISK accrual gate opens (~2026-10-15, RO-3).

**Come back on:** 2026-10-15

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Parked behind S-TOP_RISK accrual gate ~2026-10-15 (RO-3). Time-gated, not forgotten

*Owner program: neural-web*

### GAP-U15

**Validated word banned from study reports**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Every study report must use plain-language with an 'In plain English' box; the word 'validated' must never appear; nulls and censoring rates must be printed. This is a cross-program standing obligation.

**Forbidden actions:**
  - use the word 'validated' in any report
  - omit null results from report
  - omit censoring rate from report

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Every study report: plain-language + "In plain English" box; the word "validated" never appears; nulls and censoring rates printed.

*Owner program: neural-web*

### GAP-U16

**BD-AVOID-1 long-side only for verdict; short-side quarantined**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** In BD-AVOID-1, long-side grades only feed the verdict; short-side grades are recorded but carry no verdict criteria (per RUL-3). No board chips this wave. This prevents short-entry evidence from piggybacking on the avoid-long ledger.

**Scope fence:** BD-AVOID-1 verdict: long-side grades only.

**Forbidden actions:**
  - use short-side BD grades for verdict criteria
  - add board chips this wave

**Unblock condition:** Out-of-program short-entry prereg with own derived_from_surface stamp.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> **Quarantine:** long-side grades only feed the verdict; short-side grades are recorded but carry no verdict criteria (RUL-3). Display: no board chips this wave.

*Owner program: neural-web*

### GAP-U17

**Fragility-veto study deferred — needs external joins not in surface**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** The A/B1 fragility-veto study is deferred because it requires earnings/dilution flags not present in the replay_boarded 66-col surface. It is a batch-3 candidate after PR-B2 lands the runner merge extension. Bottom_sensors also has only 1 date of history.

**Forbidden actions:**
  - run fragility-veto without external joins

**Unblock condition:** PR-B2 lands runner merge extension; earnings/dilution flags available in surface.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Needs external joins (earnings/dilution flags not in replay_boarded 66-col surface); batch-3 candidate after PR-B2 lands the runner merge extension

*Owner program: neural-web*

### GAP-U19

**Short-side panel — accrual row only; no board chips until maturity**

- Status: `active_law` | Kind: `context` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Short-side (BD) results appear only as an accrual row in measurement.html's evidence panel. No board chips are permitted until the ledger matures per the ladder law. This is the standing display ruling for any avoid-long evidence pending maturity.

**Scope fence:** Display-only accrual row for short-side panel; no board chips before ledger maturity.

**Forbidden actions:**
  - add board chips from avoid-long evidence before maturity
  - display short-side panel as actionable

**Unblock condition:** Ledger matures per ladder law (n>=300/side for BD-AVOID-1).

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Accrual row in measurement.html evidence panel only; no board chips until ledger matures (ladder law)

*Owner program: neural-web*

### GAP-U22

**BD-AVOID-1 compensating gate — >=8pp threshold, forward OOS only**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** The BD-AVOID-1 Phase-1 verdict requires LONG-side 21d stop rate exceeding matched control by >=8pp (stricter than the >=5pp Phase-0 reading that selected BD-2/BD-3), with episode-clustered CI excluding 0 and BH q<=0.10 within family. Verdict basis is forward OOS accrual ONLY — the Phase-0 tape is never re-used for the verdict.

**Forbidden actions:**
  - lower verdict threshold below 8pp
  - use Phase-0 tape for BD-AVOID-1 verdict
  - apply verdict before OOS floor

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> forward BD-2 and BD-3 events mark names whose LONG-side 21d stop rate exceeds a forward matched control by **≥8pp** (compensating gate: stricter than the ≥5pp Phase-0 reading that selected them), episode-clustered CI excluding 0, BH q≤0.10 within family.

*Owner program: neural-web*

### GAP-U24

**Lobe-5 Data Fitness folded — evidence-gap panel is the build**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Codex's Lobe-5 (Data Fitness Lobe) is folded into the existing work: the useful part is the evidence-gap panel (PR-A1), and run_status/circuit-breaker already exists. No separate Data Fitness Lobe is chartered.

**Scope fence:** Evidence-gap panel covers Data Fitness; no separate lobe.

**Forbidden actions:**
  - charter Data Fitness Lobe

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> The useful part IS the evidence-gap panel (PR-A1). run_status/circuit-breaker already exists

*Owner program: neural-web*

### GAP-U3

**EDGAR solvency/fragility lobe killed — two-lobe cap + own program**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The EDGAR solvency/fragility lobe (Codex item I) is killed. It duplicates G1's frozen F1 family and overlaps the existing fundamentals buildout program. No third lobe may be chartered (two-lobe cap). This is cross-program standing law.

**Scope fence:** No fragility/solvency lobe; use fundamentals buildout for EDGAR-based metrics.

**Forbidden actions:**
  - charter EDGAR solvency lobe
  - charter fragility lobe
  - build third lobe beyond L1/L3

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> = G1 F1 family (frozen, deferred) + fundamentals buildout (own program). No third lobe (two-lobe cap)

*Owner program: neural-web*

### GAP-U4

**Options tissue consumption blocked — accrual gate ~2026-10/12**

- Status: `blocked` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** All options de-escalation games (Codex item G) are blocked behind accrual gates (~2026-10/12). W-F is parked. No new options tissue consumption is permitted per rails program §10. Time-gated, not forgotten.

**Scope fence:** No options tissue consumption until accrual gate opens (~2026-10/12).

**Forbidden actions:**
  - consume options tissue before accrual gate
  - start W-F options wave before gate

**Unblock condition:** Options accrual gates open (~2026-10/12).

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> All behind accrual gates (~2026-10/12); W-F parked. No new options tissue consumption (rails program §10)

*Owner program: neural-web*

### GAP-U5

**L6 macro games deferred — must beat noisy-sector precedent**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** L6 macro stress/positioning/vintage games remain gated on a Phase-0 that beats the noisy-sector precedent. Data stores are confirmed deep (COT/OFR-FSI/ALFRED: 1995+/2000+/1996+). L6 is a future charter candidate, not this program.

**Scope fence:** L6 not buildable until Phase-0 beats noisy-sector precedent.

**Forbidden actions:**
  - charter L6 before Phase-0 gate cleared

**Unblock condition:** Phase-0 study beats the noisy-sector precedent with pre-registered criteria.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> L6 gate stands (Phase-0 must beat noisy-sector precedent). Data confirmed deep. Candidate for a future charter, not this program

*Owner program: neural-web*

### GAP-U6

**Short-volume FINRA species needs own prereg — SLF-001 FTD-only**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** SLF-001 killed the FTD-pressure variant only. FINRA daily short volume remains PIT-safe species evidence but needs its own prereg under the L1 ladder. The short-volume squeeze/informed split (item J) is deferred to Phase-2 after PR-C2 ledger accrues.

**Scope fence:** FINRA daily SV requires separate Phase-2 prereg; no inference from SLF-001 FTD null.

**Forbidden actions:**
  - extend SLF-001 null to FINRA daily SV
  - run FINRA SV study without own prereg

**Unblock condition:** PR-C2 ledger accrues (Phase-2).

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> SLF-001 killed FTD variant only; FINRA daily SV species need own preregs under L1 ladder — Phase-2, after PR-C2 ledger accrues

*Owner program: neural-web*

### GAP-U7

**Claim Reliability Lobe deferred — n_dates<25 floor not met**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The qledger narrative_reliability lobe (Lobe-4/item E) is reshaped: data is not mature (max n_dates=9 of 25; 5d grades only). A descriptive accrual table ships as a PR-A1 sub-panel, not a lobe. The lobe question re-opens when any family hits n_dates>=25.

**Scope fence:** Display-only descriptive table until n_dates>=25; no lobe chartered yet.

**Forbidden actions:**
  - charter claim reliability lobe before n_dates>=25
  - use qledger table as escalation source

**Unblock condition:** Any family reaches n_dates >= 25.

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Descriptive table now (PR-A1); lobe question re-opens when any family hits n_dates≥25

*Owner program: neural-web*

### GAP-U8

**Codex What-Not-To-Do list adopted — no fusion, no LLM origination**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Codex's 'What Not To Do' list is adopted verbatim as standing rulings: no fusion, no LLM origination of signals/scores/escalations, no root-gate options direction, no short entries from avoid evidence, vintage-first, and display-only does not mean weak-but-usable.

**Scope fence:** Display-only outputs must not be consumed as weak signals.

**Forbidden actions:**
  - LLM originate signal
  - LLM originate score
  - LLM escalate
  - fuse signals
  - short entry from avoid evidence
  - treat display-only as weak-but-usable

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> adopted verbatim — it matches standing rulings (no fusion, no LLM origination, no root-gate options direction, no short entries from avoid evidence, vintage-first, display-only ≠ weak-but-usable).

*Owner program: neural-web*

### GAP-U9

**WAIT-GRID-1 — descriptive-only; wait_grid_v1 surface stamp required**

- Status: `active_law` | Kind: `study` | Nondelegable: `False`

**Ruling:** WAIT-GRID-1 (10 cells: delay_n in {1,2,3,5,10} x {hold(21), hold(63)}) is verdict-criteria descriptive-only — it is the L7 abstention substrate, not a promotion. Any later prereg built on this surface must carry derived_from_surface: wait_grid_v1. Report requires MAE/MFE relative to delayed entry and episode-clustered CIs.

**Scope fence:** WAIT-GRID-1 results are descriptive-only; no verdict or promotion from this grid.

**Forbidden actions:**
  - use WAIT-GRID-1 results as promotion evidence
  - run later prereg without derived_from_surface stamp

**Source:** `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md`
> Verdict criteria: **descriptive-only** (this is the L7 abstention substrate, not a promotion). Any later prereg on this surface carries `derived_from_surface: wait_grid_v1`.

*Owner program: neural-web*

### RUL-T3-2

**Clock-first ordering: ledger-openers outrank capability builds**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Clock-first ordering is the standing prioritization rule for all lobe power-up work. Ledger-openers with pre-registered gates outrank capability builds. Every build is ranked by days-of-evidence-per-day-deferred.

**Scope fence:** Applies to all Neural Web lobe build sequencing decisions.

**Forbidden actions:**
  - prioritize model-training over ledger-openers
  - ship capability build before clock-opening ledger in same wave

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **RUL-T3-2:** Clock-first ordering is the standing prioritization rule for lobe power-up work: ledger-openers with pre-registered gates outrank capability builds.

*Owner program: neural-web*

### RUL-T3-3

**Truth-maintenance work is RAIL work, not lobe build**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Truth-maintenance work (sentinels, baselines, schema conformance) is classified as RAIL work under the docket taxonomy and lives with the NW rails program. The PR-A1 conformance test is the permanent guard ensuring unpublished-edge-cell blindness is a CI failure.

**Scope fence:** Taxonomy ruling: sentinel/baseline/conformance work files as rails, not lobe builds.

**Forbidden actions:**
  - file truth-maintenance work as a lobe build
  - ship a decay-monitor without published baseline artifact

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **RUL-T3-3:** Truth-maintenance work (sentinels, baselines, schema conformance) is RAIL work under the docket taxonomy and lives with the NW rails program; the PR-A1 conformance test is the permanent guard.

*Owner program: neural-web*

### RUL-T3-5

**No confidence number without Wilson/Jeffreys bound; all calibration via grading_stats.py**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** No new model may publish a confidence number that is not a Wilson or Jeffreys bound computed from graded history (D-7 restated for this program). All calibration primitives must converge on engine/grading_stats.py to prevent bespoke-calibrator drift.

**Scope fence:** Applies to all Neural Web model outputs that publish confidence numbers.

**Forbidden actions:**
  - publish confidence number that is not Wilson/Jeffreys bound from graded history
  - author confidence via LLM
  - create bespoke calibrator outside grading_stats.py

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **RUL-T3-5:** No new model may publish a confidence number that is not a Wilson/Jeffreys bound from graded history (D-7 restated for this program); all calibration primitives converge on `engine/grading_stats.py`.

*Owner program: neural-web*

### TOP3-M1

**M1 clock-first ordering: ADOPTED as program ordering principle**

- Status: `adopted` | Kind: `process` | Nondelegable: `True`

**Ruling:** Rank every build by days-of-evidence-per-day-deferred. Ledger-openers ship first (L4 funnel history, M4 operator outcomes); model-training runs whenever. A ledger only counts if its gate and family are pre-registered at ship time. This is the standing ordering principle ratified as RUL-T3-2.

**Forbidden actions:**
  - ship model-training before clock-opening ledger in same wave

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **M1 — Clock-first ordering (ADOPTED as the program's ordering principle).** Rank every build by days-of-evidence-per-day-deferred. Ledger-openers ship first (L4 funnel history, M4 operator outcomes); model-training runs whenever. A ledger only counts if its gate + family are pre-registered at ship time.

*Owner program: neural-web*

### TOP3-M2

**M2 contradiction pair-g: annotation-only, severity ≤ tension, no winner field**

- Status: `adopted` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Extend contradictions.py with pair-g (Oracle complex out-rotation vs Entry buy-lane member inside that complex). Severity is capped at 'tension', annotation-only. A winner field or suppression output is forbidden: that would constitute a hard gate in disguise requiring a full gauntlet. The contradiction must fail-open.

**Scope fence:** Annotation-only; no winner field; fail-open.

**Forbidden actions:**
  - add winner field to contradiction pair-g
  - suppress output based on contradiction result
  - escalate contradiction severity above 'tension'

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **M2 — Cross-lobe contradiction pair (BUILD NOW).** Extend `engine/neuralweb/contradictions.py` with pair-g: Oracle complex out-rotation vs an Entry buy-lane member inside that complex. Severity capped at 'tension', annotation-only, NO winner field — a resolving output would be a hard gate in disguise requiring a full gauntlet.

*Owner program: neural-web*

### TOP3-M3

**M3 regret-context card: QUEUED Phase E-Next; display-only, overlap-corrected CI**

- Status: `deferred` | Kind: `context` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The regret-context card is queued for Phase E-Next. It must be display-only, sourced from EXIT-GRID-1 by species/cohort, leave-one-out, overlap-corrected CI at 126d. Zero board-order effect is required pre-gauntlet.

**Scope fence:** Display-only; no board-order effect; pre-gauntlet.

**Forbidden actions:**
  - produce board-ordering output from regret card pre-gauntlet

**Unblock condition:** Phase E-Next (2026-Q3/Q4); EXIT-GRID-1 must be populated.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **M3 — regret-context card (QUEUED, Phase E-Next)** — display-only post-fire regret context from EXIT-GRID-1 by species/cohort, leave-one-out, overlap-corrected CI at 126d, zero board-order effect pre-gauntlet.

*Owner program: neural-web*

### TOP3-M4

**M4 operator-tape outcome resolution: LLM may never author outcome or confidence**

- Status: `adopted` | Kind: `data_contract` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** operator_tape.jsonl captures PIT decisions, conviction, and invalidation but lacks outcome fields. Add nightly-resolved system_state_at_stamp, realized_outcome (deterministic price/ledger join only — never LLM-authored), and override_flag, and emit a display-only operator-vs-system scorecard. This is a ledger for calibration, not a training set.

**Scope fence:** Display-only scorecard; append-only; additive-only oracle_nightly END step.

**Forbidden actions:**
  - author realized_outcome via LLM
  - author confidence via LLM
  - use operator tape as training set

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **M4 — Operator-tape outcome resolution (BUILD NOW; the cheapest counterfactual engine in the docket).** `operator_tape.jsonl` already captures PIT decisions + conviction + invalidation but has **no outcome field**. Add nightly-resolved `system_state_at_stamp`, `realized_outcome` (deterministic price/ledger join at the stated invalidation/horizon — never LLM-authored)

*Owner program: neural-web*

### TOP3-M5

**M5 calibration: all primitives must use grading_stats.py with bootstrap mandate**

- Status: `adopted` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Three calibration helpers (reliability_curve/brier_decomposition, era_split_stability, eb_shrink) are built in grading_stats.py. Docstrings must mandate that long-horizon/overlapping rows use the block-bootstrap primitives. This prevents bespoke-calibrator drift and supports RUL-T3-5.

**Scope fence:** Pure additive plumbing; no consumer behavior changes.

**Forbidden actions:**
  - create bespoke calibrator outside grading_stats.py
  - skip block-bootstrap for overlapping long-horizon rows

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **M5 — Converge calibration on `grading_stats.py` (BUILD NOW, small).** Three helpers every future consumer needs: `reliability_curve`/`brier_decomposition`, `era_split_stability`, `eb_shrink` — with loud docstrings that long-horizon/overlapping rows must use the block-bootstrap primitives.

*Owner program: neural-web*

### TOP3-O5

**O5 truth-maintenance: AMEND to baseline publication + conformance test (ADOPTED)**

- Status: `adopted` | Kind: `rail` | Nondelegable: `False`

**Ruling:** The truth-maintenance job already runs. The real defect was that the two onset-edge decay baselines were never published (p3_results.json never committed), leaving the monitor permanently inert. Fix is to publish adjudicated baselines and add a conformance test ensuring every _DISPLAY_WITH_EDGE_COMPOUNDS member resolves to a published stat. This is classified as a rail fix, not a lobe build.

**Forbidden actions:**
  - file truth-maintenance as lobe build
  - leave decay baseline unpublished after edge ships

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> The real defect our census found: the two onset edges' decay baselines were **never published** (`p3_results.json` never committed) → monitor permanently inert. Fix = publish the adjudicated baselines + a conformance test that every `_DISPLAY_WITH_EDGE_COMPOUNDS` member resolves to a published stat

*Owner program: neural-web*

### TOP3-U1

**Two-lobe concurrency cap: no new lobe chartered by this adjudication**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No new lobe is chartered by the Top-3 power-up adjudication. The two-lobe concurrency cap is untouched. O5 and E1 are classified as RAIL work; L4 and M4 are ledger waves. The Future-Lobes Docket taxonomy applies.

**Scope fence:** Applies to all lobe-charter decisions flowing from this adjudication.

**Forbidden actions:**
  - charter a new lobe under this adjudication's authority
  - count E1 or O5 as lobe builds

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> Taxonomy filing per the Future-Lobes Docket: O5 and E1 are RAIL work; L4/M4 are ledger waves; nothing here charters a new lobe (two-lobe concurrency cap untouched).

*Owner program: neural-web*

### TOP3-U2

**Grader-STARVED rows define each lobe's real ledger to-do list**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** The 'surfaces→ledgers' cross-lobe move shipped as the R2 grader-closure audit (#1556: 7 CLOSED / 3 LOG-ONLY / 16 GRADER-STARVED). Each lobe's real ledger to-do list is its GRADER-STARVED rows. The aspiration 'surfaces→ledgers' is struck; the grader-closure audit is the concrete implementation.

**Forbidden actions:**
  - propose 'surfaces to ledgers' as a build without grader-closure audit basis

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> #5 (surfaces→ledgers) — STRIKE as aspiration; it shipped as the R2 grader-closure audit (#1556: 7 CLOSED / 3 LOG-ONLY / 16 GRADER-STARVED). **Each lobe's real ledger to-do list is its GRADER-STARVED rows.**

*Owner program: neural-web*

### NEXTL-U11

**ABS-1 lean_out delay contrast deferred as batch-3 follow-on after B1+B2 land**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** The lean_out-conditioned delay contrast (ABS-1: delay {1,5} x cohort {lean_out} x hold(21)) is recorded as a batch-3 follow-on after #1664 PR-B1+PR-B2 land. Registration is deferred until both parents' surfaces exist. It will carry derived_from_surface: wait_grid_v1 + disp_gate_v1 and consume PR-B2's reconstructed basis so regime labels cannot diverge.

**Forbidden actions:**
  - register ABS-1 before WAIT-GRID-1 and DISP-GATE-1 land
  - build lean_out delay contrast without derived_from_surface anchor

**Unblock condition:** #1664 PR-B1 (WAIT-GRID-1) and PR-B2 (DISP-GATE-1) both merged

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> Batch-3 follow-on (recorded, not registered):** lean_out-conditioned delay contrast (this memo's ABS-1: delay {1,5} × cohort {lean_out} × hold(21)) | next replay batch after B1+B2 land | Registration deferred until both parents' surfaces exist

*Owner program: neural-web*

### NEXTL-U12

**Scope fence: no meta-models, composite scores, sizing changes, or board chips**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** This program permits no new lobes, no meta-models, no fused/composite scores, no sizing changes, and no board chips. No re-tests of frozen or nulled families. No supportive sponsorship vocabulary. No public write endpoints. No touching #1664's owned surfaces. No LLM-originated signals anywhere.

**Scope fence:** Display-only; no ranked-output consumer; no composite scoring; no board chips; no LLM-originated signals.

**Forbidden actions:**
  - build meta-models
  - build composite hazard scores
  - change sizing
  - add board chips
  - originate LLM signals
  - touch #1664 owned surfaces
  - add public write endpoints

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> No new lobes, no meta-models, no fused/composite scores, no sizing changes, no board chips. - No re-tests of frozen or nulled families (RUL-N9). No supportive sponsorship vocabulary (RUL-N3). - No public write endpoints; no touching #1664's owned surfaces (§3). - No LLM-originated signals anywhere; de-escalation-only consumption shape for anything downstream.

*Owner program: neural-web*

### NEXTL-U19

**Sponsorship lifecycle grammar deferred to docket L10 (~2027+)**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** The sponsorship lifecycle grammar and the short-covering leg are deferred to docket L10 (approximately 2027+), pending PIT short interest data availability. This program does not build any sponsorship lifecycle grammar.

**Forbidden actions:**
  - build sponsorship lifecycle grammar before docket L10

**Unblock condition:** Docket L10 reached (~2027+); PIT short interest data available

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> sponsorship lifecycle grammar → docket L10 (~2027+); thesis anything → long-hold program.

*Owner program: neural-web*

### NEXTL-U2

**Meta-verdict: zero of five proposed lobes clear the docket lobe bar**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The institutional framing of the five-lobe memo is sound, but its build content mis-files everything as lobes — zero of five clear the docket §1 lobe bar. The memo's exclusion list omits four active programs that own most of the territory. This constitutes a standing pattern to watch for future lobe proposals from similar framings.

**Forbidden actions:**
  - register institutional-framing documents as lobe charters without docket §1 clearance

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> Meta-verdict on the memo:** the institutional framing (decision-specific organs, consequence, labels, replay, realized-decision attribution) is sound and worth keeping as prose. The build content mis-files everything as lobes: zero of five clear the docket §1 lobe bar

*Owner program: neural-web*

### NEXTL-U4

**F-HZ-1 run-gated on dilution_events.parquet materializing after first nightly sweep**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** F-HZ-1 prereg and harness ship in PR-2 but the run itself is gated on dilution_events.parquet existing with at least one successful sweep. If absent at build time, the PR ships prereg + harness + tests only and the run lands as a follow-up commit/PR once the nightly materializes the file.

**Scope fence:** No run, no report, no output JSON until parquet gate is met.

**Forbidden actions:**
  - run F-HZ-1 before dilution_events.parquet exists
  - publish results without completed nightly sweep

**Unblock condition:** dilution_events.parquet exists with >=1 successful nightly sweep

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **Run gate:** `dilution_events.parquet` exists with ≥1 successful sweep. If absent at build time, the PR ships prereg + harness + tests with the run gated; the run + report land as a follow-up commit/PR once the nightly materializes it.

*Owner program: neural-web*

### NEXTL-U9

**Execution realism half (L5) blocked on R4 Mastermind fills-bridge contract**

- Status: `blocked` | Kind: `rail` | Nondelegable: `False`

**Ruling:** The execution-realism half (fill_slippage/spread/tax-lot vs realized fills) is blocked on a non-existent R4 Mastermind fills-bridge contract. It is deferred with that named unblock. Tax-lot sensitivity stays in the rails queue as an R1 experiment only.

**Forbidden actions:**
  - build execution-realism fills analysis before R4 fills-bridge contract exists

**Unblock condition:** R4 Mastermind fills-bridge contract is created (Mastermind-repo charter)

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> Execution-realism half (fill_slippage/spread/tax-lot vs realized fills) is **blocked on a non-existent R4 Mastermind fills-bridge contract** — deferred with that named unblock; tax-lot sensitivity stays in the rails queue as an R1 experiment.

*Owner program: neural-web*

### RUL-N1

**Zero lobes chartered; two-lobe cap (L1/L3) holds**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** This program charters ZERO new lobes. L1 and L3 remain the only chartered lobes, and the two-lobe concurrency cap (RUL-P1) stands. Both build waves (PR-1, PR-2) are rail-consumers or preregistered descriptive studies, not lobe charters.

**Scope fence:** No new lobes may be chartered under this program; all waves are rail-consumer or descriptive-study shape only.

**Forbidden actions:**
  - charter new lobes
  - exceed two-lobe cap
  - reclassify rail-consumer PRs as lobe charters

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N1 (zero lobes):** this program charters ZERO lobes. L1/L3 remain the chartered set (two-lobe cap, RUL-P1). Both build waves here are rail-consumers: PR-1 executes a rails-queue item; PR-2 is a preregistered descriptive study on existing nwqs-c machinery.

*Owner program: neural-web*

### RUL-N2

**Decision-chain operating stack struck; no organ may gate another**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The memo's operating-stack chain (fire → sponsorship → fragility → abstention → thesis → realized) is the prohibited fused-escalation shape and is struck. Each organ ships as a parallel display column. No organ's output may condition another organ's escalation, gating, or sizing. Any pairwise interaction requires its own prereg naming both parents.

**Scope fence:** Display columns only; no organ-to-organ conditioning pipeline permitted.

**Forbidden actions:**
  - chain organ outputs for escalation
  - use one organ's state to gate another organ
  - build fused composite scoring stack
  - implement fire→sponsorship→fragility decision chain

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N2 (decision chain struck):** the memo's operating-stack chain (`fire → sponsorship → fragility → abstention → thesis → realized`, memo line 570) is the prohibited fused-escalation shape in narrative form — it contradicts the memo's own red-team warning #1. **Struck.** Each organ ships as a parallel display column; no organ's output may condition another organ's escalation, gating, or sizing. Any pairwise interaction requires its own prereg naming both parents (factor-kill-interaction precedent).

*Owner program: neural-web*

### RUL-N5

**n-before-stat: print fire-n and cluster-n before any statistic**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** PR-2 and any successor study in this program must print achieved fire-n and episode-cluster-n BEFORE any statistic. A DEFER outcome on a floor miss is an expected, printed outcome — not a failure. This applies to F-HZ-1 and any follow-on study.

**Forbidden actions:**
  - publish statistics before reporting fire-n and cluster-n
  - treat floor-miss DEFER as a failure

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N5 (n-before-stat):** PR-2 (and any successor study here) prints achieved fire-n and episode-cluster-n BEFORE any statistic; DEFER on a floor miss is an expected, printed outcome, not a failure.

*Owner program: neural-web*

### RUL-N6

**Abstention prior is wait_costs; foregone upside printed symmetrically**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** The prior for all wait/skip studies is wait_costs — EXIT-GRID-1's lesson is that drawdown control is an entry problem and delay most plausibly forfeits MFE. Every abstention-flavored report must print foregone upside symmetric with avoided drawdown. This binding also covers #1664's WAIT-GRID-1 reports.

**Forbidden actions:**
  - report abstention benefits without printing symmetric foregone upside
  - set prior to delay-is-safe without wait_costs basis

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N6 (abstention prior + symmetric cost):** the prior for all wait/skip studies is **wait_costs** — EXIT-GRID-1's lesson is that drawdown control is an ENTRY problem, and delay most plausibly forfeits MFE. Every abstention-flavored report prints foregone upside symmetric with avoided drawdown.

*Owner program: neural-web*

### RUL-N7

**F-HZ-1 runs standalone as dilution_hazard family; not through R1**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** F-HZ-1 runs as a standalone preregistered phase-0 (esx-study pattern), NOT through R1. It registers a new flat fdr_family='dilution_hazard' with declared budget 3, descriptive-first. It must NOT touch fdr_family='long_hold' (frozen) or 'replay' (not a rule replay). The family was renamed from 'hazard' to 'dilution_hazard' to avoid collision with the cycle-hazard survival namespace.

**Scope fence:** F-HZ-1 is display-only this batch; no promotion without separate promotion prereg carrying derived_from_surface: f_hz1.

**Forbidden actions:**
  - run F-HZ-1 through R1 CohortFilter
  - assign to fdr_family='long_hold'
  - assign to fdr_family='replay'
  - use family name 'hazard' (collides with cycle-hazard namespace)

**Unblock condition:** Separate promotion prereg with derived_from_surface: f_hz1 required for any promotion

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N7 (F-HZ-1 lane):** F-HZ-1 runs as a standalone preregistered phase-0 (esx-study pattern), NOT through R1 (its conditioning column is an external join, and the R1 CohortFilter v1 vocabulary is frozen to replay_boarded columns). It registers a **new flat family `fdr_family='dilution_hazard'`** with declared budget 3, descriptive-first. It must NOT touch `fdr_family='long_hold'` (frozen) or `'replay'` (not a rule replay).

*Owner program: neural-web*

### RUL-N8

**DQ-2 activation floor: n>=25 graded operator actions before any stat publishes**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The DQ-2 grading harness is pure after-the-fact measurement. No summary statistic publishes below n>=25 graded operator actions (the cortex A2 Wilson floor). Below floor, the artifact carries {state:'accruing', n} only. Operator overrides are graded, never treated as authority. The output artifact is a git-committed small JSON with a named single writer running on the ops lane.

**Scope fence:** DQ-2 artifact is ops-lane only; no CI render-band execution; no site surface this wave.

**Forbidden actions:**
  - publish Wilson/bootstrap statistics before n>=25 graded actions
  - treat operator overrides as authority
  - run harness in CI render band

**Unblock condition:** n>=25 graded operator actions per contrast

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N8 (DQ-2 shape):** the harness is pure after-the-fact measurement. No summary statistic publishes below **n≥25 graded operator actions** (the cortex A2 Wilson floor); below floor the artifact carries `{state:'accruing', n}` only. Operator overrides are graded, never treated as authority.

*Owner program: neural-web*

### RUL-N9

**No re-litigation of frozen/nulled families or settled verdicts**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Nothing in this program re-tests: G1's frozen family, esx_insider_sponsor's null, esx_ev_blackout's operative-panel mae results (mae21 null; k=3-pooled mae63 NOT MET), the exit-routing NO-GO, or the crowding split-half FAIL. Where the memo proposes any of these, the disposition is the existing clock.

**Forbidden actions:**
  - re-test G1 frozen family
  - re-test esx_insider_sponsor null
  - re-test esx_ev_blackout mae21/mae63 operative panels
  - re-test exit-routing NO-GO
  - re-test crowding split-half FAIL

**Source:** `research/NW_NEXT_LOBES_ADJUDICATION_BY_FABLE.md`
> **RUL-N9 (no re-litigation):** nothing in this program re-tests: G1's frozen family, esx_insider_sponsor's null, esx_ev_blackout's operative-panel mae results (mae21 null; k=3-pooled mae63 NOT MET), the exit-routing NO-GO, or the crowding split-half FAIL. Where the memo proposes any of these, the disposition is the existing clock.

*Owner program: neural-web*

### DT-R8

**Monthly trim desk deferred to future L2 Exit&Trim charter**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Monthly trim desk is DEFERRED in full to the future L2 Exit&Trim charter (two-lobe cap binding; RUL-F3.15 taxonomy is the spec of record; TRIM-GRID-1/EXIT-GRID-1 already cover the policy-replay surface). Monthly-bar sponsorship-decay conditioning is a candidate trim-review input, contingent on DT-W1 replicating, and any such run registers through the R1 governor against the pooled replay family (N=37 minimum) with RUL-F3.3 pre-outcome labels binding.

**Scope fence:** Deferred until L2 Exit&Trim charter opens; two-lobe cap must not be exceeded.

**Forbidden actions:**
  - build monthly trim desk before L2 charter
  - exceed two-lobe cap

**Unblock condition:** L2 Exit&Trim charter opens; DT-W1 must replicate for sponsorship-decay input.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R8 (monthly trim desk).** DEFERRED in full to the future L2 Exit&Trim charter (two-lobe cap binding

*Owner program: neural-web*

### DT-R9

**Operator ledger duplicate; behavioral label vocabulary recorded only**

- Status: `duplicate` | Kind: `rail` | Nondelegable: `True`

**Ruling:** The proposed operator/churn-regret ledger is DUPLICATE of live infrastructure (L4 action ledger, DQ-2 contrasts, W-EX exposure log, EXIT-GRID-1 regret surface, M3 card queued). The behavioral vocabulary (churn-regret/panic-sell/FOMO-chase/conviction-hold) is recorded as candidate label taxonomy for the L4 grading-harness design wave at the n>=25 floor. No LLM may assign behavioral labels as data without that harness's own prereg.

**Scope fence:** No LLM may assign behavioral labels as data without L4 harness prereg.

**Forbidden actions:**
  - assign behavioral labels without L4 prereg
  - build new operator ledger outside existing infrastructure

**Unblock condition:** DQ-2 n>=25 floor reached (~2026-09-15).

**Come back on:** 2026-09-15

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> - **DT-R9 (operator ledger).** DUPLICATE of live infrastructure (L4 action ledger, DQ-2 contrasts, W-EX exposure log, EXIT-GRID-1 regret surface

*Owner program: neural-web*

### DT-U6

**Behavioral label vocab parked at L4 DQ-2 n>=25 floor (~2026-09-15)**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** The behavioral vocabulary (churn/panic/FOMO/conviction) is recorded as candidate label taxonomy for the L4 grading-harness design wave. It becomes actionable only at the DQ-2 n>=25 floor, approximately 2026-09-15 on the exposure-contrast clock.

**Forbidden actions:**
  - use behavioral labels as data without L4 harness prereg

**Unblock condition:** DQ-2 n>=25 floor reached (~2026-09-15).

**Come back on:** 2026-09-15

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> The behavioral vocabulary (churn-regret / panic-sell / FOMO-chase / conviction-hold) is recorded here as candidate label taxonomy for the L4 grading-harness design wave at the n≥25 floor.

*Owner program: neural-web*

### DT-U9

**Monthly sponsorship-decay trim input contingent on DT-W1 replicating**

- Status: `blocked` | Kind: `study` | Nondelegable: `False`

**Ruling:** Monthly-bar sponsorship-decay conditioning (faithful whale metric on the massive store) is a candidate trim-review input, contingent on DT-W1 replicating. Any such run registers through the R1 governor against the pooled replay family (N=37 minimum) with RUL-F3.3 pre-outcome labels binding.

**Forbidden actions:**
  - run sponsorship-decay trim study without DT-W1 replication

**Unblock condition:** DT-W1 must replicate; then route through R1 governor with RUL-F3.3 labels.

**Source:** `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> monthly-bar sponsorship-decay conditioning (faithful whale metric on the massive store) is a candidate trim-review input, **contingent on DT-W1 replicating**

*Owner program: neural-web*

### OVC-U7

**NW display of OVC states: stamps must flow first; caution/de-escalation phrasing only**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `False`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** Neural Web display surfacing of options weather / committee context for OVC states may only occur after stamps flow from the single-writer. Caution/de-escalation phrasing only is permitted (RO-3). This applies to the options_weather lobe and committee context.

**Scope fence:** NW display only after stamps flow; caution/de-escalation phrasing only.

**Forbidden actions:**
  - surface OVC states in NW before stamps flow
  - use non-caution phrasing for OVC states in NW

**Unblock condition:** stamps flow from scripts/stamp_options_state.py

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> NW display surfacing (options_weather lobe / committee context) only after stamps flow — caution/de-escalation phrasing only (RO-3).

*Owner program: neural-web*

### CYC-U28

**NW lobe: cycle_pattern_state.json; envelope-stamped; read tools in cortex**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The Neural Web cycle_pattern lobe consumes a compact state artifact at data/neuralweb/cycle_pattern_state.json. It is implemented via _compose_cycle_pattern() in world_state.py, LOBE_SUMMARIZERS['cycle_pattern'] in mastermind_context.py, and read_cycle_pattern_state in cortex/ask-brain read tools. The artifact must be envelope-stamped.

**Scope fence:** NW lobe consumes cycle_pattern state only at display/context tier; no scoring.

**Forbidden actions:**
  - NW lobe reading raw cycle_pattern lake files directly

**Source:** `research/CYCLE_PATTERN_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
> NW lobe: `_compose_cycle_pattern()` in `world_state.py`, `LOBE_SUMMARIZERS['cycle_pattern']` in `mastermind_context.py`, `read_cycle_pattern_state` in cortex/ask-brain read tools, envelope-stamped.

*Owner program: neural-web*


### next3-upgrades

### NEXT3-U1

**BD-ECON-1 NULL law — avoid lens does not transfer to board fires**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** BD-ECON-1 returned NULL across all 6 cells (C1 +1.9pp stop [CI −5.6,+10.4]; C3 increment ~0). The avoid lens does NOT transfer to board fires at 21d; the entry stack already filters the damage. NO forward skip-prereg is warranted; the pre-committed INCREMENT-NULL branch is taken. BD-2/BD-3 remain the only definitions with avoid evidence.

**Scope fence:** Avoid lens cannot be deployed against board fires at 21d horizon.

**Forbidden actions:**
  - write skip-prereg from BD-ECON-1 null result
  - claim avoid lens transfers to board fires

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> BD-ECON-1 = **NULL across all 6 cells** (C1 +1.9pp stop [CI −5.6,+10.4]; C3 increment ~0) — the avoid lens does NOT transfer to board fires at 21d; the entry stack already filters the damage; NO forward skip-prereg is warranted

*Owner program: next3-upgrades*

### NEXT3-U10

**5-U2 outcome-conditioned options report DEFER — contamination surface**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** All live gate families are building_history (n_cond 0–42); an outcome-conditioned report today is empty or a contamination surface. The readiness half folds into W-OC; the outcome half reads at options-entry-gate-maturation clock (2026-10-15, already registered). No new registration.

**Scope fence:** No outcome-conditioned options report before gate maturation.

**Forbidden actions:**
  - build outcome-conditioned options gate report before 2026-10-15
  - register new clock for this item

**Unblock condition:** options-entry-gate-maturation clock at 2026-10-15

**Come back on:** 2026-10-15

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> All live gate families are building_history (n_cond 0–42); an outcome-conditioned report today is empty or a contamination surface. The *readiness* half folds into W-OC; the *outcome* half reads at `options-entry-gate-maturation` (2026-10-15, already registered — no new registration).

*Owner program: next3-upgrades*

### NEXT3-U11

**6-U5 weekly review — must extend deterministic-brief pattern, never LLM brief**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** Codex misidentified admin/brief.py as the deterministic brief — it reads LLM-generated briefs. The deterministic pattern is engine/neuralweb/daily_brief.py. At come-back (2026-09-15), the weekly review must extend the deterministic-brief pattern, never the LLM brief. Below n≥25 floor, the report is empty.

**Scope fence:** Must use deterministic brief pattern; LLM brief extension forbidden.

**Forbidden actions:**
  - extend admin/brief.py for weekly review
  - run weekly review below n=25 floor

**Unblock condition:** n≥25 operator actions floor reached

**Come back on:** 2026-09-15 (experiment: `next3-weekly-decision-review`)

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> At come-back (2026-09-15), the review extends the deterministic-brief pattern, never the LLM brief.

*Owner program: next3-upgrades*

### NEXT3-U12

**6-U4 lobe impact attribution DEFERRED — requires W-EX and #1669 floor**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** Lobe impact attribution requires exposure accrual (W-EX) AND #1669 past its n≥25 floor. No action now; come-back 2026-09-15.

**Forbidden actions:**
  - build lobe impact attribution before W-EX and #1669 floor

**Unblock condition:** W-EX exposure log accrued AND #1669 past n≥25 floor

**Come back on:** 2026-09-15 (experiment: `next3-lobe-impact-attribution`)

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> Requires exposure accrual (W-EX) AND #1669 past its floor. Come-back 2026-09-15.

*Owner program: next3-upgrades*

### NEXT3-U13

**6-U3 reason taxonomy RECOMMEND-ROUTE — blocked on PR-C4**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** The reason taxonomy is additive and low-risk, but its admin capture UI surface is #1664 PR-C4's territory and C4 has not started. Routed as a recommendation to the #1664 program. Come-back 2026-07-27 to check C4 landed.

**Forbidden actions:**
  - build reason taxonomy UI without #1664 PR-C4 landing first

**Unblock condition:** #1664 PR-C4 ships machine-readable alert IDs

**Come back on:** 2026-07-27 (experiment: `next3-reason-codes-after-c4`)

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> Routed as a recommendation to the #1664 program; come-back 2026-07-27 to check C4 landed and dispatch a small follow-up PR if the C4 builder did not fold it in.

*Owner program: next3-upgrades*

### NEXT3-U15

**Scope fence — no short execution, no meta-models, no board chips from any wave**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** No lobe charters, meta-models, fused/composite scores, sizing changes, or board chips from any wave in this program. No short execution, no borrow/squeeze modeling. No options gate/threshold/stamp changes (W-OVC owns). No kernel anything until Signal Commons R1 (2026-10). No new nightly graders.

**Scope fence:** No board chips, no short execution, no meta-models, no sized output from any wave.

**Forbidden actions:**
  - create board chip from any wave
  - build meta-model
  - build fused/composite score
  - change sizing
  - add new nightly grader
  - build kernel anything before 2026-10

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> No lobe charters (cap stays L1+L3); no meta-models; no fused/composite scores; no sizing changes; no board chips or site surfaces from any wave here.

*Owner program: next3-upgrades*

### NEXT3-U16

**5-U5 analogue library DEFERRED — premature until W-E0 manifest complete**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** The analogue library is genuinely unowned and a good idea in research form, but premature until W-E0 single-name manifest completes and epistemically hazardous as a live surface (retrieval outcome readout is a score in prose). Come-back 2026-08-15 with prereg-first and research-artifact-only fences per RUL-U7.

**Scope fence:** Research artifact only; no live surface before gate passage.

**Forbidden actions:**
  - build live analogue library before W-E0 manifest
  - expose analogue retrieval as scored surface

**Unblock condition:** W-E0 single-name manifest complete

**Come back on:** 2026-08-15 (experiment: `next3-analogue-library`)

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> premature until the W-E0 single-name manifest completes, and epistemically hazardous as a live surface (a retrieval outcome readout is a score in prose). Come-back 2026-08-15 with prereg-first + research-artifact-only fences (§3 RUL-U7).

*Owner program: next3-upgrades*

### NEXT3-U19

**SLF-001 null/no-go standing prior for short-side pressure territory**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** SLF-001 (SEC FTD pressure, merged #1660 the same morning) printed NULL/NO-GO on short-side pressure territory. This is a standing prior that must be carried by any future short-side proposal touching pressure territory.

**Forbidden actions:**
  - propose short-side pressure feature without carrying SLF-001 null prior

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> SLF-001 (SEC FTD pressure, merged #1660 the same morning) printed NULL/NO-GO on short-side pressure territory — a standing prior Codex's short-side section should have carried

*Owner program: next3-upgrades*

### NEXT3-U2

**Phase-0b species all PARKED — breakdown grammar does not widen**

- Status: `no_build` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** All three Phase-0b species are PARKED: BD-4 (−12.45pp stop rate, sign-reversal against hypothesis), BD-5 (−1.69pp), BD-6 (−0.76pp) — none clear ≥5pp; none avoid-only. The breakdown grammar does not widen. BD-2/BD-3 remain the only definitions with avoid evidence and their live question stays with BD-AVOID-1's forward clocks.

**Scope fence:** BD-4/BD-5/BD-6 parked; no forward build without re-prereg.

**Forbidden actions:**
  - promote BD-4/BD-5/BD-6 to Phase-1
  - claim breakdown grammar widened

**Unblock condition:** New prereg with fresh evidence basis

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> Phase-0b = **all three species PARKED** (BD-4 two-clock rollover −12.45pp = stop rate LOWER than control, a sign-reversal against the breakdown hypothesis; BD-5 −1.69pp; BD-6 −0.76pp; none clear ≥5pp; none avoid-only); BD-4×BD-3 near-overlap 37.5%, no redundancy flag. The breakdown grammar does not widen

*Owner program: next3-upgrades*

### NEXT3-U20

**Exposure date law — artifact as_of, never run date**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** Exposure date for the operator exposure log must equal the artifact's as_of field, never the run date. This is verified against the daily.yml collect→engine job split. The git history of committed site artifacts is the PIT tape (the RUL-C5 move).

**Forbidden actions:**
  - use run date as exposure date in exposure log

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> Exposure date = artifact `as_of`, never run date (§2.5 intro, verified against daily.yml job split).

*Owner program: next3-upgrades*

### NEXT3-U3

**Multi-evidence conditioning report KILL — per-axis registered contrasts only**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** The multi-evidence conditioning report ('BD × options × dispersion × froth' in one report) is the prohibited conditioning shape and its dispersion axis has no historical PIT basis until DISP-GATE-1 ships. The legal version is per-axis registered contrasts only. Come-back 2026-10-15 when S-TOP_RISK accrual and B2 basis both resolve.

**Scope fence:** No fused multi-evidence conditioning report.

**Forbidden actions:**
  - build BD × options × dispersion × froth combined report
  - consume dispersion axis before DISP-GATE-1

**Unblock condition:** S-TOP_RISK accrual complete AND DISP-GATE-1 B2 basis shipped; per-axis registered contrasts only

**Come back on:** 2026-10-15 (experiment: `next3-bd-conditioning-census`)

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> As written ("BD × options × dispersion × froth" in one report) it is the prohibited conditioning shape and its dispersion axis has no historical PIT basis until DISP-GATE-1 (PR-B2) ships its reconstruction. The legal version is per-axis registered contrasts.

*Owner program: next3-upgrades*

### NEXT3-U4

**DecisionPacket schema REJECT — cross-lobe chain prohibited**

- Status: `killed` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** A canonical cross-lobe packet routing short-side → options → decision-quality evidence is RUL-N2's prohibited chain in schema form and a parallel event apparatus is prohibited sprawl. The useful residue — stable ids, as_of, surface, artifact refs on every exposure row — folds into W-EX's row schema, flat, with no cross-lobe conditioning fields.

**Scope fence:** No cross-lobe DecisionPacket apparatus; residue fields fold flat into W-EX schema only.

**Forbidden actions:**
  - build DecisionPacket cross-lobe apparatus
  - route short-side→options→DQ in a single schema
  - create parallel event apparatus

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> A canonical cross-lobe packet that routes short-side → options → decision-quality evidence is RUL-N2's prohibited chain in schema form, and a parallel event apparatus is exactly the sprawl the docket warns against.

*Owner program: next3-upgrades*

### NEXT3-U5

**Lobe-cap taxonomy clarification — 'lobes 4/5/6' are not lobes**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Codex's 'lobes 4/5/6' are respectively an operating chartered lobe (L1 short-side), a program's connective tissue (options→NW), and a rail-consumer (DQ instrumentation). None constitutes a new lobe. All upgrades on these organs are waves on existing tissue.

**Scope fence:** Connective tissue and rail-consumers are not lobes.

**Forbidden actions:**
  - designate options→NW connective tissue as a lobe
  - designate DQ rail-consumer as a lobe

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> nothing here charters a lobe. The two-lobe cap stays L1+L3. Codex's "lobes 4/5/6" are respectively an operating chartered lobe (L1 short-side), a program's connective tissue (options→NW), and a rail-consumer (DQ instrumentation) — all upgrades below are waves on existing tissue.

*Owner program: next3-upgrades*

### NEXT3-U6

**BD-3 sharper fact — partial short-species candidate, not avoid-only**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** BD-3 is the ONE definition where 21d short-favorable (37.53%) exceeds short-adverse (34.67%) — not cleanly avoid-only; it is the only latent short-species candidate. BD-AVOID-1 quarantines short-side grades accordingly. Any future short-side study must carry this as a standing prior.

**Forbidden actions:**
  - treat BD-3 as avoid-only without acknowledging short-species candidacy

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> BD-3 is the ONE definition where 21d short-favorable (37.53%) exceeds short-adverse (34.67%) — not cleanly avoid-only; it is the only latent short-species candidate. BD-AVOID-1 quarantines short-side grades accordingly.

*Owner program: next3-upgrades*

### NEXT3-U9

**5-U4 top-risk handoff OWNED/BLOCKED — S-TOP_RISK gate 2026-10-15**

- Status: `blocked` | Kind: `wave` | Nondelegable: `False`

**Ruling:** #1664 verdict 'DON'T (yet)' applies. S-TOP_RISK gate is 2026-10-15. ABS-1b options-hostile arm is already a named deferred item in #1666 §4. No action and no new registration from this program.

**Forbidden actions:**
  - build top-risk → short-side handoff before S-TOP_RISK gate

**Unblock condition:** S-TOP_RISK gate 2026-10-15

**Come back on:** 2026-10-15

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> #1664 verdict "DON'T (yet)"; S-TOP_RISK gate 2026-10-15; ABS-1b options-hostile arm already a named deferred item (#1666 §4). No action, no new registration.

*Owner program: next3-upgrades*

### RUL-U1

**Zero lobe charters — cap stays L1+L3**

- Status: `active_law` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** No lobe is chartered by this program. The two-lobe concurrency cap remains L1+L3. All four builds are waves on existing tissue (L1 tape, options program audit rail, DQ rail). This is the same accounting as RUL-C1/RUL-N1.

**Scope fence:** No new lobes; all builds are waves on existing tissue only.

**Forbidden actions:**
  - charter a new lobe
  - extend lobe count beyond L1+L3

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> no lobe is chartered; the cap stays L1+L3. All four builds are waves on existing tissue (L1 tape, options program audit rail, DQ rail). Same accounting as RUL-C1/RUL-N1.

*Owner program: next3-upgrades*

### RUL-U10

**Language law — 'validated' banned; plain-language box mandatory**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** The word 'validated' must appear nowhere in any artifact this program ships. The terms 'avoid candidate', 'building history', 'descriptive', and 'come-back' are used precisely. Every report carries a plain-language box.

**Forbidden actions:**
  - use the word 'validated' in any artifact
  - omit plain-language box from any report

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> the word "validated" appears nowhere in any artifact this program ships; every report carries a plain-language box.

*Owner program: next3-upgrades*

### RUL-U2

**Ownership seniority — sibling programs own touched surfaces**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Where this program touches a surface owned by #1664/#1666/#1673, the earlier program owns it. Specifically: BD-AVOID-1 and codexgap-c2 are untouchable until PR-C2 merges, PR-C4 capture UI, DISP-GATE-1's dispersion basis, #1669's frozen contrasts, W-OVC's stamp/state fields, and in-flight W-A/W-B PRs. Any future BD×dispersion study must consume B2's reconstruction, never re-derive.

**Scope fence:** Cannot touch BD-AVOID-1, codexgap-c2, PR-C4 scope, DISP-GATE-1 basis, or in-flight sibling surfaces.

**Forbidden actions:**
  - touch codexgap-c2 before PR-C2 merges
  - re-derive dispersion basis without B2 reconstruction
  - modify #1669 frozen contrasts
  - touch W-OVC stamp/state fields

**Unblock condition:** PR-C2 merges for codexgap-c2 access

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> where this program touches a surface owned by #1664/#1666/#1673, the earlier program owns it. Named: BD-AVOID-1 and everything in codexgap-c2 (untouchable until PR-C2 merges)

*Owner program: next3-upgrades*

### RUL-U3

**BD-ECON-1 lawful shape — research-only, no live authority**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** Retro decision-economics on the existing Phase-0 tape is legal because every input is already computed and graded. It must be registered (family 'short_side', declared budget 6, logged BEFORE the run), carry derived_from_surface: bd_phase0, print symmetric costs (avoided drawdown AND missed upside, RUL-N6), and be research-only with no chip, gate, or board consumer. Its verdict changes which forward preregs get written; it grants zero live authority. The co-primary increment contrast C3 is binding.

**Scope fence:** Research-only; no chip, no gate, no board consumer.

**Forbidden actions:**
  - create site surface from BD-ECON-1
  - grant live authority from BD-ECON-1 result
  - run before registering prereg
  - skip symmetric cost printing

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> retro decision-economics on the existing Phase-0 tape is legal now because every input is already computed and graded; it is registered (family `short_side`, declared budget 6, logged BEFORE the run), carries `derived_from_surface: bd_phase0`, prints symmetric costs (avoided drawdown AND missed upside, RUL-N6), and is research-only — no chip, no gate, no board consumer.

*Owner program: next3-upgrades*

### RUL-U3a

**Budget semantics: log_declared_budget is per-family max(), not sum**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** log_declared_budget keeps a per-family max() floor, not a sum. Declared budgets protect only their own BH set; cross-study multiplicity within 'short_side' is NOT captured by the declared budget. Both harnesses must log each verdict cell as a distinct ledger config so literal_n accumulates, and every report prints the family literal count with the max()-basis divergence note. Tolerable only because all family studies are descriptive/research-only.

**Forbidden actions:**
  - add declared budgets cross-study
  - omit literal_n from report
  - skip max()-basis divergence note

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> `log_declared_budget` is a per-family max() floor, not a sum (§2.5.1). Each study's declared budget protects only its own BH set; cross-study multiplicity within `short_side` is NOT captured by the declared budget

*Owner program: next3-upgrades*

### RUL-U4

**Phase-0b lawful shape — one prereg, three definitions, budget 3**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** Phase-0b is a descriptive tape extension under the Phase-0 apparatus: same universe, liquidity floor, era window, episode collapse, paired two-sided grading, seeded random-bar controls, survivorship stamps. One prereg, three frozen definitions, declared budget 3 (max()-floor semantics). BD-6 requires a cross-sectional sector-panel pre-pass. Any Phase-1 forward prereg from Phase-0b must carry a compensating gate at least as strict as BD-AVOID-1's ≥8pp. S7⁻ is excluded; EDGAR/news-gated species stay parked; no cross-definition selection statistic is computed.

**Scope fence:** Descriptive only; no cross-definition selection statistic; no EDGAR/news-gated species.

**Forbidden actions:**
  - include S7⁻ in Phase-0b
  - build EDGAR-gated species
  - compute cross-definition selection statistic
  - Phase-1 prereg without ≥8pp compensating gate

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> ONE prereg, three frozen definitions, declared budget 3 (RUL-U3a semantics), `derived_from_surface: bd_phase0_tape` stamped. The §6 reading guide of BD_PHASE0_PREREG applies unchanged, with one amendment inherited from #1664 RUL-3: any Phase-1 forward prereg arising from Phase-0b must carry a compensating gate at least as strict as BD-AVOID-1's ≥8pp.

*Owner program: next3-upgrades*

### RUL-U6

**W-EX measurement-substrate-only — no statistics, no contrasts**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The exposure log computes NO statistics, NO contrasts, and registers NO trials. The three #1669 contrasts stay frozen; any exposure-conditioned contrast requires a future prereg (come-back 2026-09-15). Storage: row log gitignored host-local, committed summary bounded 90 days, single-writer. Exposure date equals artifact as_of, never run date.

**Scope fence:** Measurement substrate only; no statistics, no contrasts, no trials.

**Forbidden actions:**
  - compute statistics in exposure log
  - register trials in W-EX
  - use run date as exposure date
  - modify #1669 frozen contrasts

**Come back on:** 2026-09-15

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> the exposure log computes NO statistics, NO contrasts, registers NO trials. #1669's three contrasts stay frozen; any exposure-conditioned contrast is a future prereg (come-back 2026-09-15 registered).

*Owner program: next3-upgrades*

### RUL-U7

**Analogue-library fences — prereg-first, research artifacts only**

- Status: `deferred` | Kind: `study` | Nondelegable: `True`

**Ruling:** Any analogue library must prereg BEFORE any neighbor search, be era-partitioned with ETF/sector roots first, and output only research artifacts in research/options/ — never a live per-candidate surface. Any conditional-outcome table it prints is a declared contamination surface. A live analogue chip requires its own gate passage.

**Scope fence:** Research artifacts only; no live per-candidate surface; no live analogue chip without gate passage.

**Forbidden actions:**
  - run neighbor search before prereg
  - expose analogue output as live surface
  - ship live analogue chip without gate passage

**Unblock condition:** W-E0 single-name manifest complete; prereg registered

**Come back on:** 2026-08-15 (experiment: `next3-analogue-library`)

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> prereg BEFORE any neighbor search; era-partitioned; ETF/sector roots first; outputs are research artifacts only (`research/options/`), never a live per-candidate surface; any conditional-outcome table it prints is a declared contamination surface.

*Owner program: next3-upgrades*

### RUL-U9

**LLM law — no LLM origination, scoring, or escalation**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Nothing in this program lets an LLM originate, score, or escalate. W-EX rows are deterministic joins of committed artifacts; BD studies are arithmetic on frozen tapes.

**Forbidden actions:**
  - LLM originate signal
  - LLM score exposure row
  - LLM escalate verdict

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> nothing in this program lets an LLM originate, score, or escalate. W-EX rows are deterministic joins of committed artifacts; BD studies are arithmetic on frozen tapes.

*Owner program: next3-upgrades*


### nw-mastermind-bridge

### BRIDGE-U1

**Bridge is context-only at birth; all authority booleans false**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`
- Authority ceiling: `A0_OBSERVE`

**Ruling:** Every field in the bridge artifact is context-only at birth with all five authority booleans set to false. Promotions are shrink-only and require pre-registered shadow definitions, accrued shadow evidence, Fable review, and a registry come-back date. The artifact carries `is_context_only: true` and may never raise size, loosen a cap, or act on cortex prose.

**Scope fence:** Context-only; no authority booleans may be set true without Fable review and pre-registered shadow evidence.

**Forbidden actions:**
  - add a candidate
  - raise size
  - loosen a cap
  - act on cortex prose
  - set authority booleans true

**Unblock condition:** Pre-registered shadow definitions + accrued shadow evidence + Fable review + registry come-back date

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> Every field is context-only at birth. Authority booleans all false. Promotions (shrink-only) require: pre-registered shadow definitions, accrued shadow evidence, Fable review, registry come-back date. Never add a candidate, never raise size, never loosen a cap, never act on cortex prose.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U10

**Shadow accrual starts at birth, flag-independent**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Shadow accrual starts at birth via runlog perception rows and `nw_context` in shadow inputs, flag-independent. The would-have-blocked/shrunk policy replay is a later pre-registered wave. Shadow accrual must not be gated behind `MASTERMIND_NW_CONTEXT`.

**Scope fence:** Runlog perception rows and shadow input keys always active; policy replay wave is deferred.

**Forbidden actions:**
  - gate shadow accrual behind MASTERMIND_NW_CONTEXT flag
  - skip runlog perception rows

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> Shadow accrual starts at birth (runlog perception rows + `nw_context` in shadow inputs), flag-independent. The would-have-blocked/shrunk policy replay is a later, pre-registered wave.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U11

**NW is not an intake source; cannot add candidates or score**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A0_OBSERVE`

**Ruling:** Neural Web is not an intake source and cannot add candidates or score. `_LOADERS`/`_SIMPLE_SOURCES` remain untouched. Candidate feeds (us_standouts, altdata, radar) stay as direct reads and are the bot's registered anchor contracts.

**Scope fence:** NW may annotate candidates but may not originate, add, or score them.

**Forbidden actions:**
  - add NW as intake source
  - allow NW to originate candidates
  - allow NW to score candidates
  - modify _LOADERS or _SIMPLE_SOURCES

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> NW is not an intake source and cannot add candidates or score).

*Owner program: nw-mastermind-bridge*

### BRIDGE-U12

**Candidate context scope rule: restricted to candidate universe + actionable NW context**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** `candidate_context` = all tickers named on `us_standouts` (buy/watch/laggards) union `altdata/mastermind` (signals/broken_signals), plus `radar_ticker` tickers ONLY where actionable NW context exists (bottom_state != WATCH or trigger_tier non-null or an options row exists). Hard row cap 250 with gap_notes entry on truncation. Hard test cap 200 KB.

**Scope fence:** candidate_context is bounded to known intake surfaces + actionable NW context; radar-only tickers excluded unless NW context is actionable.

**Forbidden actions:**
  - include radar tickers without actionable NW context
  - exceed 250 row cap without gap_notes
  - exceed 200 KB artifact size

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> Scope rule: `candidate_context` = ALL tickers named on `us_standouts` (buy/watch/laggards) ∪ `altdata/mastermind` (signals/broken_signals), plus `radar_ticker` tickers ONLY where actionable NW context exists (bottom_state ≠ WATCH or trigger_tier non-null or an options row exists). Rows are sparse (null fields omitted). Hard row cap 250 with `gap_notes` entry on truncation. Budget: hard test cap 200 KB; expected ~60–120 KB.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U14

**Reader not added to macro_refresh._ANCHOR_DEFS; advisory artifact must not stale the vendor**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** The bridge reader is NOT added to `macro_refresh._ANCHOR_DEFS`. An advisory artifact must not be able to mark the whole macro vendor stale. Reader is fail-soft everywhere: absent/malformed/stale results in stable empty context + audit row; never raises into a build.

**Scope fence:** Bridge reader is advisory-only; failure path is always empty context, never a build-breaking raise.

**Forbidden actions:**
  - add bridge artifact to _ANCHOR_DEFS
  - raise exception from reader on stale/absent/malformed
  - allow advisory artifact to mark macro vendor stale

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> NOT added to `macro_refresh._ANCHOR_DEFS` — an advisory artifact must not be able to mark the whole macro vendor stale.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U17

**no new money-path wiring; listed modules must not be connected to NW**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A0_OBSERVE`

**Ruling:** The bridge is not wired into: `portfolio/risk_sizing.apply`, `brain/regime_frame.budget`, `portfolio/sleeves.enforce_book_caps`, `portfolio/firm_exposure.clamp_book`, `portfolio/cluster_config.load`, `portfolio/position_log.*`, `brain/ledger.close`, `detectors.d5_dead_capital`, `brain/risk_officer`, `brain/macro_risk`, `brain/posture_decider`. These form a reviewer grep list and must remain unwired.

**Scope fence:** NW bridge output is forbidden from all money-path and position-management modules.

**Forbidden actions:**
  - wire NW context into risk_sizing.apply
  - wire NW context into sleeves.enforce_book_caps
  - wire NW context into firm_exposure.clamp_book
  - wire NW context into position_log
  - wire NW context into ledger.close
  - wire NW context into risk_officer
  - wire NW context into macro_risk
  - wire NW context into posture_decider

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> Not wired into (reviewer grep list): `portfolio/risk_sizing.apply`, `brain/regime_frame.budget`, `portfolio/sleeves.enforce_book_caps`, `portfolio/firm_exposure.clamp_book`, `portfolio/cluster_config.load`, `portfolio/position_log.*`, `brain/ledger.close`, `detectors.d5_dead_capital`, `brain/risk_officer`, `brain/macro_risk`, `brain/posture_decider`

*Owner program: nw-mastermind-bridge*

### BRIDGE-U19

**W-next dashboard UI panel and promotion gauntlet deferred**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** Dashboard UI panel, the shrink-only promotion gauntlet off the shadow ledger, and the world-model convergence study are all deferred to W-next. `mastermind:context` tagging sweep of additional lobes is also deferred.

**Unblock condition:** Shadow ledger sufficient for promotion gauntlet; Fable review required for promotion

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> **W-next (deferred):** dashboard UI panel; shrink-only promotion gauntlet off the shadow ledger; world-model convergence study; `mastermind:context` tagging sweep of additional lobes.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U2

**MASTERMIND_NW_CONTEXT defaults OFF; dark ship with pre-registered arming condition**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** `MASTERMIND_NW_CONTEXT` defaults OFF. The reader, runlog audit rows, and shadow-input accrual run from day one regardless of the flag; only prompt and plane injection are gated. The pre-registered arming condition is: after >=5 consecutive builds with `nw_context status=present` (fresh, no reader errors) in the runlog, the operator may set `MASTERMIND_NW_CONTEXT=1` without further Fable review. Come-back 2026-07-19.

**Scope fence:** Prompt and plane injection gated behind flag; reader/audit/shadow always-on.

**Forbidden actions:**
  - enable prompt injection before arming condition met
  - skip shadow accrual

**Unblock condition:** >=5 consecutive builds with nw_context status=present (fresh, no reader errors) in the runlog

**Come back on:** 2026-07-19

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> **Pre-registered arming condition:** after ≥5 consecutive builds with `nw_context status=present` (fresh, no reader errors) in the runlog, the operator may set `MASTERMIND_NW_CONTEXT=1` without further Fable review — this ruling IS the review for the prompt-text-only promotion. Come-back 2026-07-19.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U20

**allowed_behavior for candidate_context rows is annotate_only**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Every candidate context row carries `allowed_behavior: annotate_only`. This is a data contract field enforcing that NW context may only annotate candidates, not change their intake disposition.

**Scope fence:** candidate_context rows are annotation-only; no sizing or intake disposition changes permitted.

**Forbidden actions:**
  - allow candidate_context rows to change intake disposition
  - allow candidate_context rows to affect sizing

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> `candidate_context{TICKER}` (bottom row, options row, graph_conflicts, kernel caveat, `allowed_behavior: annotate_only`)

*Owner program: nw-mastermind-bridge*

### BRIDGE-U21

**Candidate feeds stay direct; no big-bang rewiring of intake to flow through NW**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Candidate-level intake (us_standouts, altdata, radar) must keep direct reads as the bot's registered anchor contracts. NW does not and must not originate candidates. Target state: market synthesis flows engines → NW → bridge → Mastermind; candidate feeds stay direct. No big-bang rewiring.

**Scope fence:** Intake anchor contracts (us_standouts, altdata, radar) remain direct reads; NW is an annotation layer only.

**Forbidden actions:**
  - route candidate intake through NW
  - replace direct intake reads with NW-mediated reads

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> For candidate-level intake (us_standouts, altdata, radar): keep the direct reads — they are the bot's registered anchor contracts and NW does not (and must not) originate candidates. Target state: **market synthesis flows engines → NW → bridge → Mastermind; candidate feeds stay direct; NW adds per-candidate context (bottom sensors, options context, graph conflicts) on top of the direct feeds.** No big-bang rewiring.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U25

**fdr_cleared must be false while survivors[] is empty**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** `fdr_cleared` must be false for any kernel family while `kernel_decisions.survivors[]` is currently empty (first FDR batch due 2026-10-01). This is a CI-enforced test in W1.

**Scope fence:** fdr_cleared=true is prohibited until FDR survivors are declared.

**Forbidden actions:**
  - set fdr_cleared=true before FDR batch 2026-10-01
  - emit fdr_cleared=true while survivors[] empty

**Unblock condition:** survivors[] populated by 2026-10-01 FDR batch

**Come back on:** 2026-10-01

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> `fdr_cleared` false while `survivors[]` empty

*Owner program: nw-mastermind-bridge*

### BRIDGE-U3

**Kernel armed re-labeling mandatory; raw armed never crosses bridge**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** `kernel_families.json` `armed=true` means only 'enough history to display', NOT FDR-cleared. The bridge must emit `display_armed` plus `fdr_cleared` (membership in `kernel_decisions.survivors[]`, currently empty; first batch due 2026-10-01) and carry the standing law string. Raw `armed` may never cross the bridge.

**Scope fence:** Kernel armed status must be re-labeled before crossing the bridge; raw value forbidden.

**Forbidden actions:**
  - pass raw armed=true across bridge
  - treat display_armed as fdr_cleared

**Come back on:** 2026-10-01

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> **Kernel `armed` re-labeling is mandatory.** `kernel_families.json` `armed=true` means "enough history to display", NOT FDR-cleared. The bridge emits `display_armed` plus `fdr_cleared` (membership in `kernel_decisions.survivors[]`, currently empty; first batch due 2026-10-01) and carries the standing law string. Raw `armed` never crosses the bridge.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U4

**Kernel behavior-facing actions blocked until 2026-10-01 FDR batch**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A0_OBSERVE`

**Ruling:** Nothing behavior-facing may use kernel data before the 2026-10-01 FDR batch. After that batch, only `survivors[]` cells may be used for behavior-facing purposes. The standing law travels inside the artifact.

**Scope fence:** Kernel influence is display/context only until FDR survivors declared 2026-10-01.

**Forbidden actions:**
  - use kernel families for behavior-facing actions before 2026-10-01 FDR batch

**Unblock condition:** 2026-10-01 FDR batch completed and survivors[] populated

**Come back on:** 2026-10-01

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> Kernel: nothing behavior-facing before the 2026-10-01 FDR batch, and then only `survivors[]` cells (standing law travels inside the artifact).

*Owner program: nw-mastermind-bridge*

### BRIDGE-U5

**Cortex prose excluded from seat prompts; /api/ask never called by Mastermind**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Cortex prose may not appear in seat prompt output. `seat_prompt_block()` must exclude it and W2 carries a sentinel test proving memo text can never appear in seat-prompt output. `/api/ask` is never called by Mastermind builds.

**Scope fence:** Cortex prose rides artifact for operator/UI use only; never in seat prompts.

**Forbidden actions:**
  - include cortex prose in seat_prompt_block output
  - call /api/ask from Mastermind builds

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> **Cortex prose stays out of seat prompts.** The memo rides the artifact for operator/UI use; `seat_prompt_block()` excludes it, and W2 carries a sentinel test proving memo text can never appear in seat-prompt output. `/api/ask` is never called by Mastermind builds.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U6

**No ticker names beyond candidate universe cross into prompts; CI-enforced**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** `candidate_context` covers only tickers already on Mastermind-facing surfaces per §3.1 scope rule. `book_context` is counts and macro-level contradiction records only. A CI-enforced test asserts no bottom-sensors symbol outside the intake union appears anywhere in the serialized `book_context`; the invariant must not be summarizer-honor-system.

**Scope fence:** Ticker names in prompts restricted to candidate universe; book_context is counts-only, no ticker lists.

**Forbidden actions:**
  - include ticker names outside candidate universe in prompts
  - include ticker lists in book_context
  - rely on summarizer honor system for name containment

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> **No names beyond the candidate universe cross into prompts — CI-enforced on BOTH blocks.** `candidate_context` covers only tickers already on Mastermind-facing surfaces (§3.1 scope rule). `book_context` is counts and macro-level contradiction records only, and W1 carries a test asserting no bottom-sensors symbol outside the intake union appears anywhere in the serialized `book_context`

*Owner program: nw-mastermind-bridge*

### BRIDGE-U7

**regime_frame not touched; NW synthesis rides as advisory plane only**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** `regime_frame` is not touched by the bridge. NW market synthesis rides as one advisory `market_view` plane. The bridge does NOT replace `regime_frame` (money-path reader, needs full file). Convergence of the two world models is a separate future wave, if ever.

**Scope fence:** NW synthesis is advisory context only; regime_frame remains the sole money-path regime reader.

**Forbidden actions:**
  - replace regime_frame with NW synthesis
  - wire NW output into regime_frame.budget

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> **`regime_frame` is not touched.** `world_state.regime` is a strict subset distillation of `data/regime/latest.json` (`_compose_regime`, world_state.py:162-189, pure `reg.get()` — no recomputation); the bot's `budget()` needs fields the subset lacks. NW market synthesis rides as one advisory `market_view` plane; convergence of the two world models is a separate future wave, if ever.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U8

**NW market_view plane must be advisory-status, never in tilt contributors**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** `_adapt_neural_web()` must pass `validated=False` to `_plane_record`. The tilt guard is status-based, not `_VALIDATED_PLANES`-based; omitting validated=False would allow the plane to sign the tilt. W2 carries an acceptance test that a present+fresh NW plane has `status='advisory'` and never appears in tilt contributors.

**Scope fence:** neural_web market_view plane is advisory; it may never contribute to posture tilt.

**Forbidden actions:**
  - set validated=True on neural_web plane record
  - allow NW plane to appear in tilt contributors

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> `_adapt_neural_web()` MUST pass `validated=False` to `_plane_record` (or use `_absent_record`): the tilt guard is `status`-based, not `_VALIDATED_PLANES`-based, so omitting it would let the plane sign the tilt — W2 carries an acceptance test that a present+fresh NW plane has `status='advisory'` and never appears in tilt contributors.

*Owner program: nw-mastermind-bridge*

### BRIDGE-U9

**Staleness only shrinks; stale/absent context never makes book more aggressive**

- Status: `active_law` | Kind: `rail` | Nondelegable: `False`

**Ruling:** Stale or absent context disappears from prompts and planes; it can never make a book more aggressive. `_net_posture_tilt` counts only `status=='validated'` planes; absent/None-direction planes cannot create or lower a disagreement.

**Scope fence:** Staleness is always conservative; no stale/absent context path leads to increased aggressiveness.

**Forbidden actions:**
  - allow stale context to increase book aggressiveness
  - allow absent context to create tilt disagreement

**Source:** `research/NW_MASTERMIND_BRIDGE_PROGRAM.md`
> Staleness only shrinks: stale/absent context disappears from prompts and planes; it can never make a book more aggressive. (Verified: `_net_posture_tilt` counts only `status=='validated'` planes; absent/None-direction planes cannot create or lower a disagreement.)

*Owner program: nw-mastermind-bridge*


### nw-quant-synthesis

### FR-11

**Item D scope limited to flat delayed-fill sweep; after-retest/pullback patterns deferred to future EI wave**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** Item D's scope is strictly limited to the flat delayed-fill sweep (close fills at t+1 through t+5) plus the staleness fitter. After-retest and after-pullback entries are pattern-conditional studies that require their own preregistration and are deferred to a future EI wave; they are not in scope for this program.

**Scope fence:** Delayed-fill sweep only; after-retest/after-pullback patterns out of scope for this program.

**Forbidden actions:**
  - build after-retest entry patterns in this program
  - build after-pullback entry patterns in this program without separate prereg

**Unblock condition:** Own preregistration in a future EI wave.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Item D's scope is the flat delayed-fill sweep (close fills at t+1…t+5) plus the staleness fitter. After-retest / after-pullback entries are pattern-conditional studies requiring their own prereg — deferred to a future EI wave.

*Owner program: nw-quant-synthesis*

### FR-12

**Item E artifacts unregistered in data/research/ until a family survives gates; no synapse.yml, no site output**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** Item E (alpha grammar) artifacts live in data/research/ unregistered, following the gate_fires_*.parquet precedent, until a family survives its gates. No synapse.yml registration, no site output, and no spine claims are permitted at the research stage.

**Scope fence:** Research-stage artifacts only; no registration, no site output, no spine claims until gate survival.

**Forbidden actions:**
  - register alpha grammar artifacts in synapse.yml before gate survival
  - produce site output from unregistered alpha grammar artifacts
  - make spine claims from research-stage artifacts

**Unblock condition:** A family survives its gates.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Item E artifacts live in `data/research/` **unregistered** (the `gate_fires_*.parquet` precedent) until a family survives its gates. No synapse.yml registration, no site output, no spine claims at research stage.

*Owner program: nw-quant-synthesis*

### FR-13

**Report 1 tradeability/capacity roll-up folded; extend reflexivity.py for N_eff consumers, no new module**

- Status: `killed` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** Report 1's tradeability/capacity roll-up (§3.10) is folded because it duplicates shipped effective-bets code in engine/reflexivity.py (N_eff) and engine/foresight_enb.py (ENB). Any future portfolio-level N_eff consumer must extend reflexivity.py; no new module may be created for this purpose.

**Scope fence:** N_eff logic must live in reflexivity.py; no new effective-bets module.

**Forbidden actions:**
  - create new module for portfolio-level N_eff
  - build tradeability roll-up separate from reflexivity.py

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Report 1's tradeability/capacity roll-up (§3.10) is **folded**: it duplicates shipped effective-bets code (`engine/reflexivity.py` N_eff, `engine/foresight_enb.py` ENB). Any future portfolio-level N_eff consumer extends `reflexivity.py`; no new module.

*Owner program: nw-quant-synthesis*

### FR-2

**Duplicate-of-existing registry in §3 is authoritative — do not re-propose listed items**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The duplicate-of-existing registry in §3 is authoritative. Items listed there are not to be re-proposed without new evidence. Future external-report assessments must cite this table first before proposing any item that might overlap with it.

**Scope fence:** Applies to all future external-report assessments touching the listed sensor families.

**Forbidden actions:**
  - re-propose registry items without new evidence
  - skip registry check in external report assessment

**Unblock condition:** New evidence not present at time of registration.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> The duplicate-of-existing registry in §3 is authoritative. Items listed there are not to be re-proposed without new evidence; future external-report assessments should cite this table first.

*Owner program: nw-quant-synthesis*

### FR-4

**All program outputs display-only/context tier; zero board rank/size/alert changes**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Everything in this program ships display-only at the context tier; veto-shaped outputs are downgrade-only. Zero board rank, size, or alert changes are permitted anywhere in this program. The word 'validated' must stay out of user-facing text and is CI-enforced.

**Scope fence:** Display-only context tier; no ranked-output consumer; no alert generation.

**Forbidden actions:**
  - change board rank from program outputs
  - change size from program outputs
  - generate alerts from program outputs
  - use the word 'validated' in user-facing text

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Everything ships display-only/context tier; veto-shaped outputs are downgrade-only; zero board rank/size/alert changes anywhere in this program; the word "validated" stays out of user-facing text (CI-enforced).

*Owner program: nw-quant-synthesis*

### FR-5

**Alpha grammar first family must use tier-fire panels, not generic OHLCV clones**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** The alpha grammar's first family is confluence_response_alpha — formulas over the repo's own tier-fire panels (proprietary state), not generic 101-alpha OHLCV clones. Generic price/volume families are permitted only a capped later trial budget, not the first family slot.

**Scope fence:** First alpha grammar family must use proprietary tier-fire panel state.

**Forbidden actions:**
  - build generic OHLCV clones as first alpha grammar family
  - run generic price/volume families without a capped trial budget allocation

**Unblock condition:** Generic families may trial only in a capped later budget after the first family.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> The alpha grammar's first family is `confluence_response_alpha` — formulas over our own tier-fire panels (proprietary state), not generic 101-alpha OHLCV clones. Generic price/volume families get a capped later trial budget.

*Owner program: nw-quant-synthesis*

### FR-6

**Overlap map emits cluster metadata only; no combined score; board display deferred until accrual**

- Status: `deferred` | Kind: `lobe` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The overlap map emits cluster metadata only, never a combined score. The net_new_info_score must stay on the research side and must not be surfaced to the board. The duplicate-witness board display is deferred until the map survives its own accrual period.

**Scope fence:** Research-side only; no combined score output; no board display until accrual passes.

**Forbidden actions:**
  - emit combined score from overlap map
  - surface net_new_info_score to board
  - display duplicate-witness board before map accrual

**Unblock condition:** Overlap map survives its own accrual period.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> The overlap map emits cluster metadata only, never a combined score. `net_new_info_score` stays research-side. The duplicate-witness board display is deferred until the map survives its own accrual.

*Owner program: nw-quant-synthesis*

### FR-7

**failed_breakout registered as S14 phase0/display-only — registration only, no engine build**

- Status: `adopted` | Kind: `signal_family` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The failed_breakout pattern is registered as species S14 at phase0, display-only. This is registration only; no engine build is authorized in this program. It is assigned as the research queue's first ranked customer.

**Scope fence:** Registration only; display-only; no engine build in this program.

**Forbidden actions:**
  - build engine for failed_breakout in this program
  - promote S14 beyond phase0 without independent accrual

**Unblock condition:** Independent accrual through standard species promotion path.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> `failed_breakout` is registered as species **S14** (phase0, display-only) — registration only, no engine build. It is the research queue's first ranked customer.

*Owner program: nw-quant-synthesis*

### FR-8

**Render budget law: EDGAR crawling and replay sweeps off the render path**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** EDGAR crawling and replay sweeps must run off the render path. Replay artifacts follow EI R9: stored in data/replay/, canonical on Mac-local checkout, and must never be committed to git.

**Scope fence:** Off-render-path only; no git commits for replay artifacts.

**Forbidden actions:**
  - run EDGAR crawling on the render path
  - run replay sweeps on the render path
  - commit replay artifacts to git

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Render budget law: EDGAR crawling and replay sweeps run off the render path. Replay artifacts follow EI R9 (`data/replay/`, Mac-local canonical checkout, never committed to git).

*Owner program: nw-quant-synthesis*

### FR-9

**Hazard panel is macro/cycle-level only; per-stock features bind to bottom_sensors, not hazard panel**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The hazard panel (scripts/build_hazard_panel.py) is macro/cycle-level covering 11 SPDR sectors, 24 country ETFs, and 31 Shenwan codes only — it is not per-stock. Per-stock fundamental features must bind into engine/neuralweb/bottom_sensors.py and the engine/stock_fundamentals.py multiyear panel, and must NOT bind into the hazard panel.

**Scope fence:** Hazard panel scope is strictly macro/cycle-level ETFs and sectors; per-stock is excluded.

**Forbidden actions:**
  - add per-stock features to hazard panel
  - use hazard panel for per-stock fundamental scores

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> The hazard panel (`scripts/build_hazard_panel.py`) is macro/cycle-level (11 SPDR sector + 24 country ETFs + 31 Shenwan codes), not per-stock. Per-stock fundamental features bind into `engine/neuralweb/bottom_sensors.py` (per-stock, display-only) and the `engine/stock_fundamentals.py` multiyear panel — NOT the hazard panel.

*Owner program: nw-quant-synthesis*

### FR-1

**utility_router / meta_router-with-sizing REJECTED — positioning fusion illegal**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** The utility_router and meta_router-with-sizing designs are rejected under R3 (positioning fusion illegal) and RO-2 (fused composites rejected). Any formula of the shape expected_edge minus lambda-MAE minus cost minus crowding minus uncertainty feeding an action or size output is the forbidden fused-escalating-composite pattern regardless of shadow-only framing. A pure take/skip veto (de-escalation-only, no sizing output) may be re-proposed only as a fresh pre-registered trial after kernel arming (2026-10), not as a revival of this design.

**Scope fence:** No action or sizing output permitted; veto (de-escalation-only) is the maximum permissible shape.

**Forbidden actions:**
  - build utility_router
  - build meta_router with sizing
  - revive this design without fresh preregistration
  - use fused composite score as action/size output

**Unblock condition:** Fresh pre-registered trial after kernel arming (2026-10); must be a new registration, not a revival of this design.

**Come back on:** 2026-10-01

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> utility_router` and `meta_router`-with-sizing: **REJECTED** (R3 "positioning fusion illegal" / RO-2 "fused composites rejected"). `expected_edge − λ·MAE − cost − crowding − uncertainty` feeding an action/size output is the forbidden fused-escalating-composite shape regardless of "shadow-only" framing.

*Owner program: nw-quant-synthesis*

### QS-U1

**House doctrine (no master score, no LLM-originated signals, display-only-until-earned) is not a contribution from external reports**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A7_ORIGINATE`

**Ruling:** Both external reports independently re-derive standing house doctrine — no master score, no LLM-originated signals, display-only-until-earned — and present it as novel. This doctrine is noted, not adopted as a contribution from those reports; it was already standing law.

**Scope fence:** No LLM-originated signals; no master score; no promotion beyond display-only without earning.

**Forbidden actions:**
  - allow LLM to originate signals
  - allow LLM to originate scores
  - allow LLM to escalate authority
  - build master score output

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> no master score, no LLM-originated signals, display-only-until-earned) and present it as novel; the doctrine restatements are noted, not adopted as contributions.

*Owner program: nw-quant-synthesis*

### QS-U10

**Paid-data candidates (analyst dispersion, borrow, true fund flows) are Phase-4 watchlist only**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** Analyst dispersion, borrow, and true fund flows are paid-data candidates and are Phase-4 watchlist only. They must not be built in the current program or proposed as buildable-now items.

**Scope fence:** Phase-4 watchlist only; not buildable now.

**Forbidden actions:**
  - build analyst dispersion features before Phase 4
  - build borrow-rate features before Phase 4
  - build true fund flow features before Phase 4

**Unblock condition:** Phase 4 decision with data access confirmed.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Analyst dispersion / borrow / true fund flows | paid-data candidates | Phase-4 watchlist only

*Owner program: nw-quant-synthesis*

### QS-U11

**Confidence surface (Brier/Wilson/ECE) already built; kernel arms 2026-10**

- Status: `duplicate` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** The confidence surface using Brier reliability, ECE, Platt scaling (validation.py), Wilson bounds (qledger), and NW kernel is already built. It is not to be re-proposed. The kernel arms in 2026-10.

**Scope fence:** Built; kernel arms 2026-10; no re-proposal without new evidence.

**Forbidden actions:**
  - re-propose confidence surface without new evidence
  - build separate Brier/ECE/Platt module outside validation.py

**Unblock condition:** Kernel arming (2026-10) for kernel-side extensions only.

**Come back on:** 2026-10-01

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Confidence surface (Brier/Wilson/ECE) | `validation.py` brier_reliability/ECE/platt; qledger Wilson; NW kernel | built; kernel arms 2026-10

*Owner program: nw-quant-synthesis*

### QS-U13

**Hazard/survival desk is built at macro level; per-stock hazard is n-starved — do not build**

- Status: `duplicate` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** The hazard/survival desk (hazard_score.py, fit_cycle_hazard.py) is built at the macro level. Per-stock hazard scoring is n-starved and must not be built. This is a do-not-re-propose item in the registry.

**Scope fence:** Macro-level hazard built; per-stock hazard blocked due to n-starvation.

**Forbidden actions:**
  - build per-stock hazard scoring
  - re-propose per-stock survival desk without n-count evidence

**Unblock condition:** Sufficient per-stock n-count demonstrated.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Hazard/survival desk | `hazard_score.py`, `fit_cycle_hazard.py` (macro-level) | built (macro); per-stock n-starved

*Owner program: nw-quant-synthesis*

### QS-U14

**Post-event absorption already registered as S9 (bad-news immunity); queued for W3**

- Status: `duplicate` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** Post-event absorption is already registered as setup species S9 (bad-news immunity) and is queued for Wave 3. It is a do-not-re-propose item. Any new work on post-event absorption must go through the existing S9 pathway.

**Scope fence:** Covered by S9 registration; no separate post-event absorption build.

**Forbidden actions:**
  - re-propose post-event absorption outside S9 pathway

**Unblock condition:** S9 Wave 3 queue reached.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Post-event absorption | SETUP_SPECIES **S9** (bad-news immunity), queued W3 | registered

*Owner program: nw-quant-synthesis*

### QS-U15

**Disagreement mining built; dissent study under-powered — do not re-propose without new evidence**

- Status: `duplicate` | Kind: `study` | Nondelegable: `False`

**Ruling:** Disagreement mining is already built in contradictions.py and factor_contradictions.py, with a Wave 5A dissent study completed but found under-powered. It is a do-not-re-propose item in the registry.

**Scope fence:** Existing built code only; no new disagreement mining module without new evidence.

**Forbidden actions:**
  - re-propose disagreement mining without new evidence
  - build new dissent module outside contradictions.py

**Unblock condition:** New evidence or new data source not present at time of W5A study.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Disagreement mining | `contradictions.py`, `factor_contradictions.py`; W5A dissent study | built; study under-powered

*Owner program: nw-quant-synthesis*

### QS-U2

**Research queue is read-only; metabolism.register_hypothesis() is the sole budget chokepoint**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The research_queue.py engine is a read-only deterministic prioritizer — it NEVER writes machine_registry.jsonl. The metabolism.register_hypothesis() function remains the sole budget chokepoint. No other pathway may register hypotheses or write to the machine registry.

**Scope fence:** research_queue.py is read-only; all hypothesis registration must go through metabolism.register_hypothesis().

**Forbidden actions:**
  - write machine_registry.jsonl from research_queue
  - register hypotheses outside metabolism.register_hypothesis()
  - bypass budget chokepoint

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> It NEVER writes `machine_registry.jsonl`; `metabolism.register_hypothesis()` remains the sole budget chokepoint.

*Owner program: nw-quant-synthesis*

### QS-U4

**Alpha grammar: TrialLedger.log_grid() must be called BEFORE grading; DSR never uses literal n_trials**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** The alpha grammar compilation script must call TrialLedger.log_grid() BEFORE grading, not after. DSR (deflated Sharpe ratio) must be computed via deflated_sharpe(ledger=, family=) — never using literal n_trials. Within-family BH-FDR is applied; honest nulls are printed.

**Scope fence:** Alpha grammar research pipeline only.

**Forbidden actions:**
  - grade alpha candidates before logging to TrialLedger
  - use literal n_trials in DSR computation
  - suppress null results from alpha grammar output

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> `TrialLedger.log_grid()` BEFORE grading; rank IC via `validation.py` numpy paths; DSR via `deflated_sharpe(ledger=, family=)` — never literal `n_trials`; within-family BH-FDR; honest nulls printed

*Owner program: nw-quant-synthesis*

### QS-U5

**Alpha grammar lag must be >= 1 (PIT law); candidate cap v1 is 200 declared**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** The alpha grammar formula enumeration must enforce lag >= 1 as a point-in-time law — no contemporaneous features are permitted as inputs. The candidate cap at v1 is 200 declared candidates. Survivorship stamps must be carried and era filtering must follow the entry-stack W0 convention.

**Scope fence:** Alpha grammar pipeline; enforced at enumeration time.

**Forbidden actions:**
  - use lag=0 (contemporaneous) features in alpha grammar
  - exceed 200 declared candidates in v1
  - omit survivorship stamps from alpha candidates

**Unblock condition:** Candidate cap may be revised in a future version with new preregistration.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> deterministic enumeration, lag≥1 PIT law)

*Owner program: nw-quant-synthesis*

### QS-U6

**Staleness replay: exponential decay fit gate required; honest null per family if gate fails**

- Status: `active_law` | Kind: `study` | Nondelegable: `False`

**Ruling:** The staleness_delay_v1 preregistration requires an exponential decay fit with negative slope and HAC-t significance as the gate for the staleness fitter. If the gate fails for a family, a per-family honest null must be printed — no strategy claim is made or permitted from this study.

**Scope fence:** Descriptive decay measurement only; no strategy claim permitted.

**Forbidden actions:**
  - make strategy claims from staleness delay study
  - suppress null results from staleness fitter
  - use staleness decay result as a trading signal

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Gate: exponential decay fit with negative slope, HAC-t significant; else a per-family honest null. This is a descriptive decay measurement — no strategy claim is made or permitted.

*Owner program: nw-quant-synthesis*

### QS-U7

**Promotion path inherited unchanged from NW + species constitution; hard-gate authority downgrade-only**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** The promotion path is inherited unchanged from the NW constitution and species constitution: display-only to confirmer to scored, with incremental lift, minimum event counts, and regime stability or explicit regime scoping at each gate. Hard-gate authority requires gauntleted fragility vetoes, and even those start downgrade-only.

**Scope fence:** All signals in this program follow standard NW promotion path; no shortcuts.

**Forbidden actions:**
  - promote signals outside the standard NW promotion path
  - use hard-gate authority for escalation rather than downgrade

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Hard-gate authority only via gauntleted fragility vetoes, and even those start downgrade-only.

*Owner program: nw-quant-synthesis*

### QS-U8

**Regime specialists (MoE) must not be built pre-kernel-arming; n-starved**

- Status: `blocked` | Kind: `lobe` | Nondelegable: `False`

**Ruling:** Regime specialists (Mixture of Experts / MoE) must not be built now because they are n-starved pre-kernel-arming. Regime gates exist; the MoE shape requires kernel arming before having sufficient data.

**Scope fence:** MoE blocked until kernel arming; regime gates already exist as a permissible substitute.

**Forbidden actions:**
  - build Mixture of Experts regime specialists before kernel arming

**Unblock condition:** Kernel arming (2026-10).

**Come back on:** 2026-10-01

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Regime specialists (MoE) | regime gates exist; MoE is n-starved pre-kernel-arming | do not build now

*Owner program: nw-quant-synthesis*

### QS-U9

**Crowding/effective-bets split-half FAIL — do not revive crowding composite**

- Status: `duplicate` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** The crowding/effective-bets family (crowding.py, theme_crowding.py, froth_fragility.py, factor_exposure.py, fund_crowding.py; N_eff in reflexivity.py/foresight_enb.py) is built but its split-half validation failed. The family is listed in the do-not-re-propose registry.

**Scope fence:** Existing built code only; no new crowding composite or split re-test without new evidence.

**Forbidden actions:**
  - re-propose crowding composite without new evidence
  - re-run split-half on crowding family without new evidence

**Unblock condition:** New evidence not present at time of initial failure.

**Source:** `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md`
> Crowding / effective bets | `crowding.py`, `theme_crowding.py`, `froth_fragility.py`, `factor_exposure.py`, `fund_crowding.py`; N_eff in `reflexivity.py`, `foresight_enb.py` | built; split-half FAIL

*Owner program: nw-quant-synthesis*


### nw-rails

### ORTH-U1

**Program-level: display-only, no execution authority granted**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The entire R-ORTH program is display-only. No scoring, sizing, or execution authority is granted anywhere in this document. All artifacts carry display_only: true and forbidden_actions covering score, size, originate_trade, gate, rank.

**Scope fence:** Display-only; no ranked-output or execution consumer permitted.

**Forbidden actions:**
  - score
  - size
  - originate_trade
  - gate
  - rank

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Status: RATIFIED masterplan. Display-only program; no scoring, sizing, or execution authority is granted anywhere in this document.

*Owner program: nw-rails*

### ORTH-U12

**Confluence today applies no independence adjustment; confirmed co-fire is raw mean difference**

- Status: `active_law` | Kind: `context` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Per census, the committee's current confluence logic applies no independence adjustment — the 'confirms' lift is a raw co-fire mean difference. That is the descriptive committee gap R-ORTH fills. R-ORTH may not silently change this behavior; any behavioral change requires the Phase 2 unblock.

**Scope fence:** Descriptive gap identification only; no behavioral change to confluence until Phase 2.

**Forbidden actions:**
  - silently change confluence co-fire logic
  - apply independence adjustment to confirms lift before Phase 2

**Unblock condition:** Phase 2: R1 replay lift in flat replay FDR family.

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Confluence today applies **no independence adjustment** — `confirms` lift is a raw co-fire mean difference. That is the committee gap R-ORTH fills descriptively.

*Owner program: nw-rails*

### ORTH-U2

**Core ruling: build a rail, not a lobe; no new PCA trading lobe**

- Status: `adopted` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Codex's core ruling is ADOPTED: build a rail, not a lobe. No new PCA trading lobe is chartered. The rail's job is honest independence accounting only.

**Scope fence:** No lobe charter; no trading authority.

**Forbidden actions:**
  - create PCA trading lobe
  - charter new lobe

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Codex's core ruling is **ADOPTED**: build a rail, not a lobe. No new PCA trading lobe. The rail's job is honest independence accounting.

*Owner program: nw-rails*

### ORTH-U3

**OOS-decay headline is a noise artifact; Opus review reproduced from pure sampling error**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** The OOS-orthogonality-decay headline from Codex is a noise artifact, not evidence. At n=21, the max-|off-diagonal| PC correlation statistic has a finite-sample floor of ~0.40-0.71; a contiguous 21-day slice drawn from inside the training window already yields a median of 0.477 against the observed 0.5425. Consequence: every OOS-orthogonality metric MUST be reported as a percentile against its within-window null, never as a raw threshold.

**Forbidden actions:**
  - report OOS orthogonality as raw threshold without null comparison
  - treat OOS decay as evidence of true non-stationarity without null calibration

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> The OOS-orthogonality-decay headline is a noise artifact, not evidence.** Opus review (2026-07-06) reproduced the diagnostic exactly, then constructed the null: at n=21, the max-|off-diagonal| PC correlation statistic has a finite-sample floor of ~0.40–0.71

*Owner program: nw-rails*

### ORTH-U5

**Phase 0: display + explain only; Phase 3: never origination — permanently**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** Phase 0 (current program): display and explain only; all artifacts carry display_only: true and forbidden_actions covering score/size/originate_trade/gate/rank. Phase 1 unlocks de-escalation annotations after 3 months accrual + operator review. Phase 2 unlocks bounded trust conditioning after R1 replay lift in flat replay FDR family. Phase 3 never originates — permanently.

**Scope fence:** Phase 0 is A1_EXPLAIN only; Phase 1 allows A3_DE_ESCALATE; origination is permanently forbidden.

**Forbidden actions:**
  - originate signals at any phase
  - skip phase ladder
  - advance phase without operator review

**Unblock condition:** Phase 1: 3 months accrual + operator review. Phase 2: R1 replay lift in flat replay FDR family.

**Come back on:** 2027-01-06

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> - **Phase 0 (this program):** display + explain only. All artifacts carry `display_only: true`, `forbidden_actions: ["score","size","originate_trade","gate","rank"]`.

*Owner program: nw-rails*

### ORTH-U6

**Health band promotion requires >=6 months spine history and R1 replay**

- Status: `deferred` | Kind: `process` | Nondelegable: `False`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Health bands may be promoted to advisory only after at least 6 months of accrued spine history and an R1 replay. Until then, health metrics are descriptive-only with no advisory or action-triggering status.

**Scope fence:** Health bands are descriptive-only until the 6-month + R1 replay gate is cleared.

**Forbidden actions:**
  - promote health bands to advisory before 6 months history
  - use health bands to trigger action without R1 replay

**Unblock condition:** >=6 months of accrued covariance_spine history and R1 replay demonstrating lift.

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Bands may be promoted to advisory only after ≥6 months of accrued spine history and an R1 replay.

*Owner program: nw-rails*

### ORTH-U7

**Spine density come-back 2026-10-06: check n_lobes_measurable >= 6**

- Status: `deferred` | Kind: `context` | Nondelegable: `False`

**Ruling:** On 2026-10-06, re-check spine density: is n_lobes_measurable >= 6? If not, evaluate weekly-aggregation or endorsement-panel substrate as alternative. Most engines have fewer than 15 active days since 2024; only track_record is dense (638 active days).

**Unblock condition:** n_lobes_measurable >= 6 verified at 2026-10-06 check.

**Come back on:** 2026-10-06

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> 2026-10-06: spine density re-check — is `n_lobes_measurable` ≥ 6? If not, evaluate weekly-aggregation or endorsement-panel substrate.

*Owner program: nw-rails*

### ORTH-U8

**Genuine gap: live lobe-to-lobe covariance, effective-witness accounting, cross-block concentration summary**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** After census, the non-duplicative gap is exactly: live lobe-to-lobe evidence covariance, committee effective-witness accounting, and a cross-block concentration summary. R-ORTH computes only those. It reads existing systems' outputs for its cross-block summary and never recomputes them.

**Scope fence:** Scope is strictly the three identified gaps; R-ORTH must not extend beyond them without separate adjudication.

**Forbidden actions:**
  - extend R-ORTH scope beyond lobe covariance, effective-witness, and cross-block concentration without adjudication

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> The non-duplicative gap is exactly: **live lobe-to-lobe evidence covariance, committee effective-witness accounting, and a cross-block concentration summary**. R-ORTH computes only those; it READS the existing systems' outputs for its cross-block summary and never recomputes them.

*Owner program: nw-rails*

### ORTH-U9

**Nulls printed not hidden; coverage caveats mandatory on sparse spine fields**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Where spine density is insufficient for correlation-based lobe independence measurement, the artifact prints coverage fields (n_lobes_total, n_lobes_measurable, per-pair floors) and emits nulls. Nulls are printed, not hidden. The field accrues value as spine density accrues.

**Forbidden actions:**
  - hide nulls from sparse spine
  - omit coverage fields from covariance spine output

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> The artifact prints coverage (`n_lobes_total`, `n_lobes_measurable`, per-pair floors) and emits nulls where density is insufficient — nulls are printed, not hidden.

*Owner program: nw-rails*

### RUL-ORTH-1

**R-ORTH is a rail: infrastructure tier, context horizon, no scored surfaces**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** R-ORTH is a rail with tier: infrastructure (JSON state) / tier: display (rendered surface), horizon_role: context, owner_program: nw-rails, scored_path_surfaces: []. It never originates a trade, never gates, never ranks, never moves sizing.

**Scope fence:** scored_path_surfaces must remain empty; no gating or ranking permitted.

**Forbidden actions:**
  - originate trade
  - gate
  - rank
  - move sizing

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> R-ORTH is a rail: `tier: infrastructure` (JSON state) / `tier: display` (any rendered surface), `horizon_role: context`, `owner_program: nw-rails`, `scored_path_surfaces: []`. It never originates a trade, never gates, never ranks, never moves sizing.

*Owner program: nw-rails*

### RUL-ORTH-11

**Committee annotations are deterministic-engine-generated; LLMs may explain but never originate or escalate**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** All committee annotations (same_bet_warning, dominant_overlap_cluster, concentration warnings) are generated by deterministic rules in the engine. LLM surfaces (Ask/cortex) may quote and explain them; they may never originate or escalate them. Consistent with the LLM de-escalation-only house law.

**Scope fence:** LLM surfaces are explain-only; deterministic engine is the sole originator of annotations.

**Forbidden actions:**
  - LLM originate same_bet_warning
  - LLM originate dominant_overlap_cluster
  - LLM escalate concentration warning

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> All committee annotations (`same_bet_warning`, `dominant_overlap_cluster`, concentration warnings) are generated by deterministic rules in the engine. LLM surfaces (Ask/cortex) may quote and explain them; they may never originate or escalate them.

*Owner program: nw-rails*

### RUL-ORTH-12

**Factor residual layer deferred; factor block limited to correlation-PCA with 3y-history caveat**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** Codex §9's per-name residual factor coordinates are DEFERRED because the substrate is weak (factor series history ~3y, annual fundamentals, zero FDR survivors) and borrowed_strength/alibi_share_20d already covers the borrowed-signal question. The factor block in the covariance spine is limited to correlation-PCA over existing L/S factor return series with an explicit 3y-history caveat field.

**Scope fence:** Factor block limited to correlation-PCA with explicit 3y-history caveat; no per-name residual coordinates.

**Forbidden actions:**
  - build per-name residual factor coordinates in covariance spine

**Unblock condition:** Sufficient factor series history and FDR survivors.

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Codex §9's per-name residual factor coordinates are DEFERRED: the substrate is weak (factor series history ~3y, annual fundamentals, zero FDR survivors) and `borrowed_strength`/`alibi_share_20d` already covers the borrowed-signal question.

*Owner program: nw-rails*

### RUL-ORTH-2

**covariance_spine.json registered in synapse.yml as context-only**

- Status: `adopted` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** data/neuralweb/covariance_spine.json (+ compact history parquet) is registered in config/synapse.yml as context-only. docs/SIGNAL_BUS.md must be regenerated via scripts/gen_signal_bus_doc. Storage is git-tracked.

**Scope fence:** Registered as context-only; no authority consumer may read it for decisions.

**Forbidden actions:**
  - register as non-context signal

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> `data/neuralweb/covariance_spine.json` (+ compact history parquet) is registered in `config/synapse.yml` as context-only, with `docs/SIGNAL_BUS.md` regenerated via `scripts/gen_signal_bus_doc`.

*Owner program: nw-rails*

### RUL-ORTH-4

**spine_index.parquet is the sole lobe fire/intensity substrate; no new fire ledger**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** data/neuralweb/spine_index.parquet is the sole lobe fire/intensity substrate. R-ORTH derives per-engine evidence vectors from it using engine-week direction-weighted fire aggregation to maximize density. No new fire ledger is created.

**Forbidden actions:**
  - create new fire ledger

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> `data/neuralweb/spine_index.parquet` is the sole lobe fire/intensity substrate. R-ORTH derives per-engine evidence vectors from it (engine-week direction-weighted fire aggregation to maximize density); no new fire ledger is created.

*Owner program: nw-rails*

### RUL-ORTH-5

**Effective-witness fields visible immediately as display-only; no trust conditioning until R1 replay**

- Status: `active_law` | Kind: `rail` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Effective-witness fields are visible on committee/admin surfaces immediately as display-only descriptive context with an explicit 'descriptive — not gauntleted' label. No trust conditioning, confluence boost/penalty, or committee behavior change is permitted until an R1 replay shows lift.

**Scope fence:** Display-only with 'descriptive — not gauntleted' label; no committee behavior change permitted.

**Forbidden actions:**
  - apply trust conditioning
  - boost confluence
  - penalize confluence
  - change committee behavior before R1 replay

**Unblock condition:** R1 replay showing lift in flat replay FDR family.

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Effective-witness fields ARE visible on committee/admin surfaces immediately, as display-only descriptive context with an explicit "descriptive — not gauntleted" label, consistent with the confluence display law (`display_only=true` on every edge). NO trust conditioning, confluence boost/penalty, or committee behavior change until an R1 replay shows lift.

*Owner program: nw-rails*

### RUL-ORTH-6

**DISP-EIGEN-1 gate activation deferred until DISP-GATE-1 basis fix; eigen fields ship descriptive trailing-252d only**

- Status: `deferred` | Kind: `signal_family` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** DISP-EIGEN-1 is a separate prereg family, not an extension of DISP-GATE-1, but its gate activation is DEFERRED until DISP-GATE-1's basis non-stationarity blocker (34.8% expanding-vs-trailing flip rate) is resolved. Descriptive eigen fields ship on fixed trailing-252d basis only — no expanding-window percentiles. gross_mult_live stays 1.0 regardless.

**Scope fence:** Fixed trailing-252d basis only; no expanding-window percentiles; gross_mult_live locked at 1.0.

**Forbidden actions:**
  - activate DISP-EIGEN-1 gate before DISP-GATE-1 basis fix
  - use expanding-window percentiles
  - change gross_mult_live from 1.0

**Unblock condition:** DISP-GATE-1 basis non-stationarity blocker resolved (34.8% flip rate corrected).

**Come back on:** 2026-10-06

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Separate prereg family, NOT an extension of DISP-GATE-1 — but its gate activation is **DEFERRED** until DISP-GATE-1's basis non-stationarity blocker (34.8% expanding-vs-trailing flip rate) is resolved, since any percentile-typed eigen field inherits the same trap.

*Owner program: nw-rails*

### RUL-ORTH-7

**Residual RV lobe: no charter, no build until all four RORTH-RV-* experiments pass bar**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** A Residual RV lobe charter is drafted only if ALL FOUR RORTH-RV-* experiments show net-of-cost lift that (a) survives the flat replay FDR family, (b) is incremental to existing Oracle/Entry/Factor evidence, and (c) persists outside crisis windows. Until then: no lobe, no build.

**Scope fence:** No lobe, no build until all four RORTH-RV-* experiments clear the bar.

**Forbidden actions:**
  - charter Residual RV lobe before RORTH-RV-* experiments pass

**Unblock condition:** All four RORTH-RV-* experiments show net-of-cost lift surviving replay FDR family, incremental to Oracle/Entry/Factor, and persisting outside crisis windows.

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Charter is drafted only if ALL FOUR `RORTH-RV-*` experiments (registered in the prereg, runs deferred) show net-of-cost lift that (a) survives the flat `replay` FDR family, (b) is incremental to existing Oracle/Entry/Factor evidence, and (c) persists outside crisis windows. Until then: no lobe, no build.

*Owner program: nw-rails*

### RUL-ORTH-8

**Null-calibration law: OOS-decay metrics must show percentile vs within-window null; raw thresholds illegal**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Any orthogonality/stability/decay metric published by this program must carry its within-window null (contiguous-block resample, >=200 draws) and be displayed as a percentile vs that null. Raw-threshold health bands on small-sample correlation statistics are illegal in this program. This replaces Codex §13.5 health bands as written.

**Forbidden actions:**
  - publish raw-threshold health bands on small-sample correlation statistics
  - omit within-window null from OOS metric display

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Any orthogonality/stability/decay metric published by this program must carry its within-window null (contiguous-block resample, ≥200 draws) and be displayed as a percentile vs that null. Raw-threshold health bands on small-sample correlation statistics are illegal in this program.

*Owner program: nw-rails*

### RUL-ORTH-9

**No recomputation: existing orthogonality engines stay in their modules; R-ORTH only reads outputs**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Board-candidate breadth stays in reflexivity.py; theme ENB stays in foresight_enb.py; alpha-candidate overlap stays in alpha_overlap.py; factor decorrelation stays in factor_orthogonal.py. R-ORTH reads their outputs as declared consumers for its cross-block summary only. Any future consolidation is a separate adjudication.

**Scope fence:** R-ORTH is a consumer only; it must not recompute breadth, ENB, overlap, or decorrelation.

**Forbidden actions:**
  - recompute board breadth in R-ORTH
  - recompute ENB in R-ORTH
  - recompute factor decorrelation in R-ORTH
  - consolidate orthogonality engines without separate adjudication

**Source:** `research/pca_factor_orthogonality/R_ORTH_MASTERPLAN_BY_FABLE.md`
> Board-candidate breadth stays in `reflexivity.py`; theme ENB stays in `foresight_enb.py`; alpha-candidate overlap stays in `alpha_overlap.py`; factor decorrelation stays in `factor_orthogonal.py`. R-ORTH reads their outputs (declared consumers) for its cross-block summary. Any future consolidation is a separate adjudication.

*Owner program: nw-rails*


### options-alpha

### NWF3-U6

**No options root-direction flip; no fused execution score**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Options root-direction flip is prohibited. No fused execution score may be built. These are explicitly preserved Codex §9 guardrails ratified by Fable.

**Forbidden actions:**
  - flip options root direction signal
  - build fused execution score

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> no options root-direction flip; gross/net side-by-side; no fused execution score; no tax advice.

*Owner program: options-alpha*

### RUL-F3.12

**ThetaData tape calibration: ops-lane only; direction_reliable stays false for bar sources**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** The multi-session calibration harness ships as ops-lane Mac-side tooling, never on the render path. Sessions log is append-only JSONL. The updater writes only the thetadata_tape sub-key of signing_gate.json. Root direction_reliable stays false for bar sources permanently. Any session with per-trade agreement < 0.75 suspends direction_reliable_tape pending review. Production consumption of tape-signed features requires >=5 sessions spanning high-VIX and calm, multiple roots/expiries/moneyness.

**Scope fence:** Ops-lane Mac-side only; never on the render path.

**Forbidden actions:**
  - run tape calibration on the render path
  - update root direction_reliable for bar sources
  - consume tape-signed features with fewer than 5 calibration sessions
  - write outside thetadata_tape sub-key

**Unblock condition:** >=5 sessions spanning high-VIX and calm, multiple roots/expiries/moneyness required for production consumption.

**Source:** `research/NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
> root `direction_reliable` stays false for bar sources permanently; any measured session with per-trade agreement < 0.75 **suspends** `direction_reliable_tape` pending review

*Owner program: options-alpha*

### OVC-U1

**RO-2 compliance: all OVC columns must be raw fields; no fused composites**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Every column proposed in W-OVC must be a raw field. No `options_entry_quality_shadow` resurrection or composite construction is permitted. This is a standing house-law constraint (RO-2) confirmed in this adjudication.

**Forbidden actions:**
  - ship fused composite options column
  - resurrect options_entry_quality_shadow

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> - **RO-2 (no fused composites):** every proposed column is a raw field; no `options_entry_quality_shadow` resurrection. ✓

*Owner program: options-alpha*

### OVC-U10

**Kill: put/call OI ratio as predictor — sign-unstable across eras**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** Put/call OI ratio is not internalized in any form. Sign flips across eras in both the full universe and the ETF slice. The F-12 conclusion ('not a fear gauge') is reinforced; it stays dead.

**Forbidden actions:**
  - use put/call OI ratio as gate or predictor

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> Put/call OI ratio as anything (sign flips across eras in the ETF slice too).

*Owner program: options-alpha*

### OVC-U11

**Kill: directional/return use of vanna/charm states (F-21: vol >> direction)**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Any directional or return use of vanna/charm states is forbidden. F-21 doctrine 'vol >> direction' is agreed. ETF-slice rel-ret survivors are uncontrolled and contradict the residualized full universe; they are not internalized.

**Forbidden actions:**
  - use vanna or charm state for directional prediction
  - use etf-slice rel-ret survivors as evidence for directional charm edge

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> Any directional/return use of vanna/charm states (F-21: vol >> direction — agreed; the ETF-slice rel-ret survivors are uncontrolled and contradict the residualized full universe).

*Owner program: options-alpha*

### OVC-U12

**root_class column mandatory in W-OVC (formal column, not binary is_index_product)**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** W-OVC must build a formal `root_class` column with values {index_etf, sector_etf, industry_etf, single_name}. The existing binary `is_index_product` is insufficient. This is required because front-week concentration shows era-level sign instability within root classes; states must not be interpreted without root_class.

**Forbidden actions:**
  - interpret front7 concentration without root_class
  - substitute is_index_product binary for root_class

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> F-17's root-class recommendation is upgraded to a formal `root_class` column in W-OVC — now with a real artifact behind it (front-week concentration sign-flips by era inside the ETF class).

*Owner program: options-alpha*

### OVC-U15

**D1 (methodology defect): phantom ETF slice evidence from Codex F-15/16/17/20 is not internalized**

- Status: `killed` | Kind: `study` | Nondelegable: `False`

**Ruling:** Findings F-15, F-16, F-17, and F-20 cited ETF-only robustness slice output that does not exist in the shipped script or JSON. These findings are not internalized as stated; they are replaced by the real slice run in §3.2. Any agent re-proposing these findings must use the §3.2 artifact.

**Forbidden actions:**
  - internalize F-15/F-16/F-17/F-20 as originally stated from phantom ETF slice

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> **D1 (fatal for Family F): phantom ETF slice.** The script invokes the cross-section and state tests exactly once each, on the full panel (`main()`, single `run_cross_section_tests` / `run_state_tests` call); the JSON has no slice key. F-15/16/17/20 and the proposed `S-INDEX-PIN` bucket cite output that does not exist.

*Owner program: options-alpha*

### OVC-U16

**D4 ruling: calendar OPEX effects are dead in the modern era (2017+)**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** The calendar quad-week 'edge' of +0.57% exists only in 2005-2016 and reverses sign in 2017-2022 (−1.15%). Per house OOS doctrine this is the regime-death signature. Calendar-only OPEX effects are treated as dead in the modern era; this is read into F-01's verdict.

**Forbidden actions:**
  - rely on pre-2017 calendar OPEX returns as a live edge

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> **D4: calendar quad survivor is a dead regime, not an edge.** +0.57% (t=4.4) exists only in 2005-2016 and the point estimate **reverses sign in 2017-2022** (−1.15%, unadjusted p≈0.013). Per house OOS doctrine this is the regime-death signature.

*Owner program: options-alpha*

### OVC-U2

**RO-3: vanna-relief and OPEX states are caution-only; never short signal or score origination**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** Vanna-relief and any OPEX state may only inform holdability, de-escalation, and stop-width. Using them as a short signal or for score origination is forbidden. This standing house-law constraint (RO-3) applies to all W-OVC outputs.

**Scope fence:** Caution/de-escalation phrasing only in NW display; never short signal, never score origination.

**Forbidden actions:**
  - use vanna-relief as short signal
  - use OPEX state for score origination
  - exceed A3_DE_ESCALATE authority with OPEX states

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> - **RO-3 (caution-only):** vanna-relief and any OPEX state may only inform holdability / de-escalation / stop-width; never a short signal, never score origination. ✓

*Owner program: options-alpha*

### OVC-U3

**A10: S-VANNA-RELIEF gate currency limited to ledger primitives only**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** The S-VANNA-RELIEF gate may only speak in terms of ledger primitives: `post_cushion_breach`, `terminal_state_clean8_21`, and `fwd_mfe_21`. No other gate currency is permitted for this signal.

**Forbidden actions:**
  - gate S-VANNA-RELIEF using non-ledger primitive metrics

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> - **A10 (ledger primitives are the only gate currency):** S-VANNA-RELIEF gate speaks `post_cushion_breach` / `terminal_state_clean8_21` / `fwd_mfe_21` only. ✓

*Owner program: options-alpha*

### OVC-U5

**FDR family enlarged from 22 to 28 tests by S-VANNA-RELIEF and S-FRONT-CHARM registrations**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`

**Ruling:** Registering S-VANNA-RELIEF and S-FRONT-CHARM enlarges the options BH-FDR family statement from 22 to 28 tests. All future options wave registrations must account for this updated family size.

**Forbidden actions:**
  - register new options signal against the old 22-test family

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> pre-registered gates, primitives, and the enlarged BH-FDR family statement (22 → 28 tests).

*Owner program: options-alpha*

### OVC-U8

**Kill: signed_charm_pressure (F-03) — vol proxy, not internalized**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** `signed_charm_pressure` (F-03) is explicitly not internalized as a predictor. Under vol/size residualization, partial IC ≈ 0 and sign flips in 4 of 6 cells. The claim of being the 'strongest cross-sectional volatility predictor' was the confound speaking.

**Forbidden actions:**
  - internalize signed_charm_pressure as volatility predictor
  - use signed_charm_pressure in gate

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> `signed_charm_pressure` as a predictor (F-03) — partial IC ≈ 0 under vol/size control; the study's "strongest volatility predictor" was the confound.

*Owner program: options-alpha*

### OVC-U9

**Kill: 'total Greek depth is stabilizing' narrative (F-04/F-09) — size artifact**

- Status: `killed` | Kind: `context` | Nondelegable: `False`

**Ruling:** The 'total Greek depth is stabilizing' narrative is rejected. `charm_intensity`'s negative-vol relation reverses sign under vol/size control, exposing it as a size artifact. The raw finding was upside-down. No narrative adopted; no feature; no bucket for Family B intensity.

**Forbidden actions:**
  - adopt total Greek depth stabilizing narrative
  - use charm_intensity as negative-vol predictor

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> The "total Greek depth is stabilizing" narrative (F-04/F-09) — charm_intensity's sign *reverses* under control; the raw relation was a size artifact.

*Owner program: options-alpha*

### RUL-OVC-1

**S-VANNA-RELIEF registered as holdability/de-escalation/stop-width state**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`
- Authority ceiling: `A3_DE_ESCALATE`

**Ruling:** `vanna_relief_buy_pressure` (IV falling 5d x top-tercile vanna-hedge pressure) is a real vol-compression state confirmed all three eras (t approx -7.3 to -7.7, 27k-40k condition-obs, PIT-clean, sign-agnostic). It is a holdability / de-escalation / stop-width state only — not an entry originator (no robust rel-ret edge). `S-VANNA-RELIEF` is formally registered per §5.

**Scope fence:** Holdability/de-escalation/stop-width only; no entry origination, no short signal.

**Forbidden actions:**
  - use as entry originator
  - use as short signal
  - use for score origination

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> `vanna_relief_buy_pressure` (IV falling 5d × top-tercile vanna-hedge pressure) is a real vol-compression state: all three eras same sign, t ≈ −7.3 to −7.7, 27k–40k condition-obs, PIT-clean, sign-agnostic. It is a **holdability / de-escalation / stop-width** state, not an entry originator (no robust rel-ret edge — F-08 honest). Register `S-VANNA-RELIEF` per §5.

*Owner program: options-alpha*

### RUL-OVC-2

**Greek intensity is a size/liquidity proxy; no bucket; depth-cushions narrative rejected**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** Un-normalized Greek intensity is a size/liquidity proxy and must not ship as a feature without normalization. The doctrine distinction worth keeping: total-Greek intensity and front-expiry concentration are different objects (depth cushions vs. concentration exposes). No feature ships without normalization; no bucket registered for Family B.

**Scope fence:** Context-only; depth-cushions narrative rejected; no feature, no bucket.

**Forbidden actions:**
  - ship un-normalized greek intensity as feature
  - register bucket for greek intensity family
  - adopt depth-cushions narrative

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> total-Greek intensity and front-expiry concentration are different objects — depth cushions, concentration exposes** (F-27). No feature ships without normalization; no bucket.

*Owner program: options-alpha*

### RUL-OVC-3

**Front-week charm/gamma concentration: display-only + S-FRONT-CHARM gate (root_class mandatory)**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** Front-week charm/gamma concentration carries genuine incremental future-vol info (partial IC 0.05-0.13, sign-stable all eras, BH-clean) but ~two-thirds of headline IC was confound, and ETF slice shows era-level sign instability by root class. Therefore `front7_abs_charm_share` / `front7_abs_gex_share` ship as display-only state columns with `root_class` mandatory alongside, and `S-FRONT-CHARM` is registered as a caution-family gate. `signed_charm_pressure` (F-03) is explicitly NOT internalized.

**Scope fence:** Display-only columns with root_class mandatory; S-FRONT-CHARM is caution-family gate only.

**Forbidden actions:**
  - use headline IC (0.335) as expected magnitude
  - internalize signed_charm_pressure as predictor
  - interpret front7 states without root_class

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> `front7_abs_charm_share` / `front7_abs_gex_share` ship as display-only state columns in W-OVC **with `root_class` mandatory alongside**, and `S-FRONT-CHARM` is registered as a caution-family gate (§5). The honest expected magnitude is the partial IC, not the raw one. `signed_charm_pressure` (F-03) is explicitly NOT internalized — it is a vol proxy that dies under residualization.

*Owner program: options-alpha*

### RUL-OVC-4

**Family D (post-OPEX vol release): watch item only; no bucket; no registration**

- Status: `deferred` | Kind: `study` | Nondelegable: `False`

**Ruling:** Post-OPEX vol release is Era3-only with ~4 roots/date and a stale-carry construction (ffill up to a week). Nothing is registered. The finding may be revisited if/when a fourth era boundary or a historical-fire reconstruction provides a second independent sample.

**Scope fence:** Watch item in program doc only; no bucket, no signal registration.

**Forbidden actions:**
  - register S-POST-OPEX-RELEASE
  - use post_opex_prior_gamma_loaded as gate

**Unblock condition:** Fourth era boundary or historical-fire reconstruction giving a second independent sample

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> **RUL-OVC-4 (Family D — no bucket).** Era3-only, ~4 roots/date, stale-carry construction. Watch item in the program doc; nothing registered. Re-look if/when a fourth era boundary or a historical-fire reconstruction gives it a second independent sample.

*Owner program: options-alpha*

### RUL-OVC-5

**Family E (quad/OPEX calendar states): reject; is_quad_cycle stays context flag only**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** Quad states are sign-unstable across eras. The lone calendar survivor is a dead 2005-16 regime (sign-reversed in Modern era). `is_quad_cycle` remains a context flag; no gate, no state, no seasonal rule is permitted.

**Scope fence:** `is_quad_cycle` context flag only; no gate, no state, no seasonal rule.

**Forbidden actions:**
  - register S-QUAD-ROLL
  - use is_quad_cycle as gate
  - build seasonal OPEX rule from quad state

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> **RUL-OVC-5 (Family E — reject).** Quad states are sign-unstable across eras (the study says so itself, F-14); the lone calendar survivor is a dead 2005-16 regime (§2 D4). `is_quad_cycle` remains a context flag; no gate, no state, no seasonal rule.

*Owner program: options-alpha*

### RUL-OVC-6

**Family F: pin real but NOT OPEX-specific; S-INDEX-PIN not registered; air-pocket dead**

- Status: `killed` | Kind: `signal_family` | Nondelegable: `True`

**Ruling:** ETF long-gamma+high-charm vol suppression is real in all three eras but the non-OPEX placebo suppresses at least as strongly — this is dealer-positioning vol context (GEXR doctrine), not an expiry mechanism. `S-INDEX-PIN` is not registered. Air-pocket (F-16) is dead (1 weak era, sign-unstable). F-17's root-class recommendation is upgraded to a formal `root_class` column in W-OVC.

**Scope fence:** Pin suppression folds into GEXR doctrine; supportive prior for S-PIN_RISK stratification only.

**Forbidden actions:**
  - register S-INDEX-PIN bucket
  - register air-pocket state
  - treat ETF pin suppression as expiry mechanism

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> `S-INDEX-PIN` is **not** registered: no new bucket for a mechanism already covered by GEXR context + S-PIN_RISK's wall-proximity test. F-17's root-class recommendation is upgraded to a formal `root_class` column in W-OVC — now with a real artifact behind it (front-week concentration sign-flips by era inside the ETF class).

*Owner program: options-alpha*

### RUL-OVC-7

**Family G: display/shadow-first + path-based promotion doctrine adopted as house law**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `False`

**Ruling:** F-29/F-30 are restatements of house law: display/shadow until earned; path-based promotion via stop-out, liftoff, MFE, RV forecast — not directional return. Adopted as written; they bind all future options waves to the same yardstick.

**Forbidden actions:**
  - promote options signal via directional return alone
  - skip display/shadow phase for options states

**Source:** `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`
> **RUL-OVC-7 (Family G — accept).** F-29/F-30 are restatements of house law (display/shadow until earned; path-based promotion: stop-out, liftoff, MFE, RV forecast — not directional return). Adopted as written; they cost nothing and bind future options waves to the same yardstick.

*Owner program: options-alpha*


### options-nw-entry-intelligence

### NEXT3-U7

**W-E1 skeptical priors — skew-decel unsupported; DOI dead at sector level**

- Status: `active_law` | Kind: `signal_family` | Nondelegable: `False`

**Ruling:** W-E1 historical verdicts exist: skew-decel is UNSUPPORTED (lone survivor points the wrong way); DOI is dead at sector level. Any future handoff study proposing 'rising skew' or DOI-adjacent context must carry these skeptical priors. GEXR is era-dependent sign (vol-context only); CWIV Era3 is alive.

**Forbidden actions:**
  - propose skew-decel as a positive ingredient without skeptical prior
  - propose DOI context at sector level without skeptical prior

**Source:** `research/NW_NEXT3_UPGRADES_ADJUDICATION_BY_FABLE.md`
> **skew-decel UNSUPPORTED (lone survivor points the wrong way); DOI dead at sector level**. Codex's 5-U4 handoff feature list ("rising skew", DOI-adjacent context) proposes ingredients the gauntlet already demoted; any future handoff study must carry those skeptical priors.

*Owner program: options-nw-entry-intelligence*


### oracle-rotation

### TOP3-O1

**O1 onset-quality calibrator: KILL — adjudicated NULL, no re-run**

- Status: `killed` | Kind: `study` | Nondelegable: `True`

**Ruling:** The onset-quality calibrator (oracle_onset_quality_w1.py) was run twice and printed NULL (LOEO AUC 0.4887/0.4836, shuffled-null p≈0.7). p_confirm is a degenerate untrainable target at 99.7%. No re-run is permitted without a new pre-registered spec plus a population-expansion argument. The stratified base-rate table already exists in memory_base_rates.json.

**Forbidden actions:**
  - re-run oracle onset-quality model without new prereg
  - use p_confirm as training target

**Unblock condition:** New pre-registered spec + population-expansion argument that distinguishes from W1/W1b closing evidence.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **O1** onset-quality calibrator | **KILL — duplicate of an adjudicated NULL** | `scripts/oracle_onset_quality_w1.py` (1,713 lines) IS this proposal; run twice (W1 pos63, W1b reversion21): LOEO AUC 0.4887/0.4836, shuffled-null p≈0.7, Fable-countersigned "NOTHING SHIPS."

*Owner program: oracle-rotation*

### TOP3-O2

**O2 flow-routing tensor: KILL — built + naming-fraud risk**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** The lead-lag tensor and flow-routing matrix already ship in engine/oracle/graph.py; P3b placebo adjudicated 6/90 surviving cells. An open-tensor extension would cause an ~840-1,650-cell FDR explosion on a zero-sum rs identity. 'Money routing' is unidentifiable from price-implied rotation and carries naming-fraud risk under truth-in-labeling.

**Scope fence:** Display-with-edge, watermark-capped at 6/90 surviving cells.

**Forbidden actions:**
  - extend flow-routing tensor beyond adjudicated cells
  - label outputs as 'money routing'
  - add new cells without FDR correction

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **O2** flow-routing tensor | **KILL — already built + illegal as specified** | `engine/oracle/graph.py` ships the lead-lag tensor + flow-routing matrix; P3b placebo adjudicated 6/90 surviving cells (display-with-edge, watermark-capped).

*Owner program: oracle-rotation*

### TOP3-O3

**O3 member-phase intelligence: KILL as independent build; extend R-3 only**

- Status: `killed` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** Member-phase intelligence as an independent build is killed. R-1 printed a NULL and R-4 is DON'T-TEST (rs zero-sum tautology). Member cohorts cannot be built PIT (holdings are latest-only; R-2b dormant to ~2027-07). The only live positive (W2 member-transmission, display-only) already has R-3 washout-strata continuation scheduled at Q4-2026 effective-n; extend that, build nothing new now.

**Forbidden actions:**
  - build member-phase intelligence as independent artifact
  - build member cohorts PIT from latest-only holdings

**Unblock condition:** R-3 washout-strata at effective-n ~Q4-2026; R-2b requires dated holdings ~2027-07.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **O3** member-phase intelligence | **KILL as independent build; the thread is already scheduled** | Its testable premise (member dispersion/leader-laggard predicts forward member outcomes) is the construction_divergence family: R-1 printed a NULL, R-4 is DON'T-TEST (rs zero-sum tautology).

*Owner program: oracle-rotation*

### TOP3-O4

**O4 reversion sequential evidence engine: KILL — duplicate of frozen PREREG**

- Status: `killed` | Kind: `wave` | Nondelegable: `True`

**Ruling:** The reversion sequential evidence engine is a near-verbatim duplicate of the shipped, frozen design (ORACLE_REVERSION_PROMOTION_TRACK_DESIGN.md + PREREG + oracle_reversion_forward_ledger.py). Changing frozen thresholds now constitutes p-hacking by the prereg's own text. The cluster de-dup contribution is already the PREREG's open ruling, deferred to P3 adjudication when live n exists.

**Scope fence:** Frozen L2→L4 Wilson gates: lift_lb>1.25 & n≥25; n≥60 & asym≥1.3; 90-session lapse.

**Forbidden actions:**
  - change frozen reversion promotion thresholds
  - re-propose reversion sequential engine without new spec

**Unblock condition:** P3 adjudication when live matured n crosses the frozen floors (cluster-level, ~7 bets not 10).

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **O4** reversion sequential evidence engine | **KILL — near-verbatim duplicate of the shipped, frozen design** | `ORACLE_REVERSION_PROMOTION_TRACK_DESIGN.md` + PREREG (frozen L2→L4 Wilson gates: lift_lb>1.25 & n≥25; n≥60 & asym≥1.3; 90-session lapse)

*Owner program: oracle-rotation*

### TOP3-U4

**Printed-NULL O1 ruling: p_confirm is an untrainable target; no re-run without new spec**

- Status: `active_law` | Kind: `study` | Nondelegable: `True`

**Ruling:** The near-degenerate 99.7% onset→confirmed rate means p_confirm is an untrainable target. This result from the O1 adjudication is printed as a standing law: no re-run of any onset-quality model using p_confirm as a training target is permitted. This law is anchored by the C7 corrections-ledger entry.

**Forbidden actions:**
  - use p_confirm as training target for any oracle model

**Unblock condition:** New population that does not have the near-degenerate p_confirm distribution.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> The near-degenerate 99.7% means **p_confirm is an untrainable target** (see O1 ruling).

*Owner program: oracle-rotation*


### research-factory

### RF-1

**Charter: factory is orchestration layer only; delegates all evaluation**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** Build `engine/research_factory/` (cross-domain, NOT under `neuralweb/`) as a repo-native orchestration layer. It owns candidate identity/state/transitions/challenges/review packets/monitor metadata/retirement, and delegates ALL evaluation to existing engines. Everything it emits is display-only context; ceiling A0-A2. `promote_eligible` is explicitly NOT an autonomy rung and NOT a gauntlet registration.

**Scope fence:** Display-only; no ranked-output consumer; no evaluation logic inside the factory.

**Forbidden actions:**
  - evaluate candidates internally
  - score candidates
  - touch board
  - promote to gauntlet autonomously

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-1 — Charter.** Build `engine/research_factory/` (cross-domain, NOT under `neuralweb/`) as a repo-native orchestration layer. It owns candidate identity/state/transitions/challenges/review packets/monitor metadata/retirement. It delegates ALL evaluation to existing engines. Everything it emits is display-only context; ceiling A0–A2.

*Owner program: research-factory*

### RF-10

**Kill-scrutiny symmetry: every kill carries kill_evidence block; requeue for underpowered kills**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Every kill transition carries a `kill_evidence` block with `{n_at_kill, regime_split, mde_at_n, kill_class}` where `kill_class ∈ {falsified, underpowered_accruing, regime_change_suspect, duplicate, decayed, budget_withdrawn}`. `underpowered_accruing` and `regime_change_suspect` kills write a requeue pointer (requeue at 2× n_at_kill); re-arm is an explicit human decision, never automatic. Retirement writes a transition; history is never deleted.

**Forbidden actions:**
  - kill without kill_evidence block
  - auto-requeue without human decision
  - delete retirement history

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-10 — Kill-scrutiny symmetry.** Every kill transition (`numeric_rejected`, `rejected`, `retired`) carries a `kill_evidence` block: `{n_at_kill, regime_split, mde_at_n (when computable), kill_class}` with `kill_class ∈ {falsified, underpowered_accruing, regime_change_suspect, duplicate, decayed, budget_withdrawn}`.

*Owner program: research-factory*

### RF-11

**Authority mechanism: display_only field + CI gate + synapse registration in W1**

- Status: `adopted` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** Ships in W1 (not later): (a) required top-level `"authority": "display_only"` on every factory artifact row; (b) `check_research_factory_authority.py` CI gate that fails if any Article-2 perimeter module reads `data/research_factory/` or imports `engine.research_factory`; (c) `ci.yml` paths globs for factory paths; (d) `synapse.yml` registration of three durable ledgers at W1 with `tier: display`. Registration is what arms the existing read-gate.

**Scope fence:** Article-2 perimeter surfaces (alert_triage, board_ordering, top_setups, attention_queue, push_floor) must not read factory data.

**Forbidden actions:**
  - defer synapse registration past W1
  - omit authority field from artifact rows
  - article-2 surface read factory data

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-11 — Authority mechanism (not doctrine).** Ships in W1, not later: (a) required top-level field `"authority": "display_only"` on every factory artifact row; (b) `scripts/check_research_factory_authority.py` — a `check_validated_claims.py`-pattern grep gate that fails CI if any module on the Article-2 perimeter

*Owner program: research-factory*

### RF-12

**Governance events: factory transitions use research_factory_* prefix; article: null**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** Human-gate transitions and challenger completions append to `data/neuralweb/governance.jsonl` via `governance.append_event()` with `event_type` prefixed `research_factory_*` and `article: null` explicitly, so factory decisions are never mistaken for Article-3 authority grants.

**Forbidden actions:**
  - omit article: null from factory governance events
  - use event_type without research_factory_ prefix

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-12 — Governance events.** Human-gate transitions and challenger completions append to `data/neuralweb/governance.jsonl` via the existing `governance.append_event()` signature, with `event_type` prefixed `research_factory_*` and `article: null` explicitly, so factory decisions are never mistaken for Article-3 authority grants.

*Owner program: research-factory*

### RF-13

**Domain seams: Oracle two-track fork; cortex never writes machine_registry; alpha grammar parquet only**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Oracle ingest seam is `oracle_ingest_brainstorm.py` scratch-registry output only (never raw inbox JSON). Runner forks by track: reversion→read-only, 63d→counted (requires explicit `--count`). Factory cortex adapter NEVER registers or writes `machine_registry.jsonl`, never bypasses the 3/week metabolism chokepoint. Alpha grammar adapter reads only BH-FDR survivors parquet, not formula noise. Factory never auto-invokes any extraction pack.

**Forbidden actions:**
  - ingest raw oracle inbox JSON
  - write machine_registry.jsonl from factory
  - bypass metabolism chokepoint
  - auto-invoke extraction pack
  - commit scratch registry to live compounds registry

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **Oracle:** ingest seam is `oracle_ingest_brainstorm.py` scratch-registry OUTPUT (never raw inbox JSON — inbox is gitignored scratch); mechanism text is captured from the original inbox JSON before the 8-field strip. The runner FORKS by track: reversion → `oracle_reversion_screen.screen_compound(gauntlet=True)` (read-only); 63d → `oracle_screen` (counted) then `oracle_gauntlet_compound`.

*Owner program: research-factory*

### RF-14

**Dedup law: deterministic-first in fixed order; near-dup flag not auto-reject**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Dedup is deterministic-first at ingest in fixed order: (1) oracle compounds registry, (2) species registry, (3) machine registry (absent-safe), (4) trial-ledger family strings. The NW_QUANT_SYNTHESIS §3 duplicate table is prose embedded as TEXT in prompts, never machine-parsed. Structural near-dup (common-subtree) produces a `near_dup_review` FLAG — not an auto-reject.

**Forbidden actions:**
  - auto-reject on near_dup_review flag
  - machine-parse NW_QUANT_SYNTHESIS duplicate table
  - dedup out of fixed order

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-14 — Dedup law.** Deterministic-first, at ingest, in fixed order: (1) `data/oracle/compounds/registry.jsonl` (canonical rule-hash via `oracle_ingest_brainstorm._canonical`), (2) `data/species/registry.json` via `species_registry.load()`, (3) `data/neuralweb/machine_registry.jsonl` (absent-safe), (4) trial-ledger family strings.

*Owner program: research-factory*

### RF-15

**Respin law: hard cap 2 cycles per lineage; generation 3 forces terminal rejected**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Lineage fields `respin_of`/`superseded_by` + `refinement_generation` live in the candidate schema from W1. Hard cap: 2 challenge→fix→re-screen cycles per lineage, cross-domain; generation 3 forces terminal `rejected`. A respin reuses the parent's trial family unless the entry-rule column set changes (material change), which requires a new `rf.*` family citing the parent. Every re-screen is a new counted trial. Human-gate registration is required for every respin candidate.

**Forbidden actions:**
  - allow generation 3+ re-screen
  - auto-register respin without human gate
  - reuse trial family without material-change check

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-15 — Respin law.** Lineage fields `respin_of`/`superseded_by` + `refinement_generation` live in the candidate schema from W1. Hard cap: **2** challenge→fix→re-screen cycles per lineage, cross-domain; generation 3 forces terminal `rejected`.

*Owner program: research-factory*

### RF-16

**Rejected shapes: no autonomous trading, no LLM codegen, no board influence, no factory score**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** Standing forbidden shapes: no autonomous trading; no LLM confidence scores; no arbitrary LLM codegen in this program (codegen lane is a SEPARATE future program behind OS/identity boundary); no agent edits to `engine/validation.py`/gates/challenger prompts; no factory influence on board rank/size/alert priority; no utility router; no fused 'factory score'; no cortex budget raise; no treating external posts as fact; no chat-state as ledger.

**Scope fence:** Factory has zero influence on board rank, alert size, or alert priority.

**Forbidden actions:**
  - autonomous trading
  - LLM confidence scores
  - arbitrary LLM codegen in factory
  - edit engine/validation.py as factory operation
  - fused factory score
  - cortex budget raise
  - chat-state as ledger
  - treat external posts as fact

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-16 — Rejected shapes (standing).** Inherited from the study §9 and prior rulings, all still binding: no autonomous trading; no LLM confidence scores; no arbitrary LLM codegen in this program

*Owner program: research-factory*

### RF-2

**Projection law: factory persists spec_ref only; domain registry wins on conflict**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `True`

**Ruling:** For candidates homed in an authoritative registry, the factory persists ONLY `spec_ref` (the domain id) plus factory-orchestration state. Domain status is re-read and projected at read time via a fixed mapping; it is never copied into a persisted factory field. On conflict the domain registry wins, always.

**Scope fence:** Factory state fields are orchestration-only; no second source of truth for domain status.

**Forbidden actions:**
  - copy domain status into persisted factory field
  - override domain registry on conflict
  - duplicate compound lifecycle state

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-2 — Projection law.** For candidates homed in an authoritative registry (Oracle compounds registry, machine registry, species registry), the factory persists ONLY `spec_ref` (the domain id) plus factory-orchestration state. Domain status is re-read and PROJECTED at read time via a fixed mapping

*Owner program: research-factory*

### RF-3

**Naming: candidate_type field; claim_shape reserved for metabolism enum**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The factory taxonomy field is `candidate_type` (oracle_compound|cortex_hypothesis|alpha_family|species|external_idea). `claim_shape` is RESERVED for the metabolism enum, copied verbatim from the metabolism-issued row when present, never invented by the factory.

**Forbidden actions:**
  - invent claim_shape value
  - use claim_shape as factory taxonomy

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-3 — Naming.** The factory taxonomy field is **`candidate_type`** (`oracle_compound|cortex_hypothesis|alpha_family|species|external_idea`). `claim_shape` is RESERVED for the metabolism enum, copied verbatim from the metabolism-issued row when present, never invented by the factory.

*Owner program: research-factory*

### RF-4

**State machine: exactly 15 states, no phantoms; awaiting_data/deferred need come_back_on**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** Exactly the 15 states of §4, all defined, no phantoms. `implemented`/`implementation_rejected` are dropped. `awaiting_data` and `deferred` are first-class non-terminal states with a mandatory `come_back_on`. `scoped_build` is terminal-to-factory and must reference a new `*_BY_FABLE.md` program doc.

**Forbidden actions:**
  - add phantom states
  - use awaiting_data without come_back_on
  - use deferred without come_back_on
  - use implemented state

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-4 — State machine.** Exactly the 15 states of §4, all defined, no phantoms. `implemented`/`implementation_rejected` are dropped (grammar validation is part of ingest; failures are `schema_rejected` with `reason_code='grammar_invalid'`). `awaiting_data` and `deferred` are first-class non-terminal states with a mandatory `come_back_on`.

*Owner program: research-factory*

### RF-5

**Actor law: human-gate required for paper/rejected/retired/scoped_build/deferred**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** Transitions are classed: mechanical (script/codex/sonnet) can perform ingest and screening transitions, but human-gate (fable/operator, with session/PR ref) is REQUIRED for `→paper`, `→deferred`, `→rejected`, `→scoped_build`, `→retired`, and registration of any respin candidate. Clock resurfacing is mechanical A2 attention-routing; counted screens remain gated by the operator-explicit `--count`. The transition helper enforces this allowlist; violations raise.

**Forbidden actions:**
  - script actor transitions to paper
  - script actor transitions to rejected
  - script actor transitions to retired
  - LLM drives challenged→rejected without human

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> Human-gate (actor ∈ {`fable`,`operator`} with session/PR ref, REQUIRED): `→paper`, `→deferred`, `→rejected`, `→scoped_build`, `→retired`, and the registration of any respin candidate (`lineage.respin_of` set) — that is where kill-requeue and challenger-fix re-arms re-spend trials (RF-10/RF-15).

*Owner program: research-factory*

### RF-6

**Trial accounting: rf.* family regex; screened transition refuses without declared budget**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** `rf_family` names MUST match `^rf\.[a-z_]+\.[a-z0-9_]+$`, be <40 chars, never equal an existing production family, and be declared via `TrialLedger.log_declared_budget()`/`log_grid()` BEFORE any screening run — the `screened` transition REFUSES otherwise. The literal `n_trials=` path is forbidden (ratchet-enforced). BH-FDR runs ONCE per screening batch per domain — never per-candidate. Factory must never re-screen an already-screened compound.

**Forbidden actions:**
  - use literal n_trials=
  - run BH-FDR per-candidate
  - re-screen already-screened compound
  - declare rf family without log_declared_budget

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-6 — Trial accounting.** Every candidate carries `trial_accounting` = `{mode: 'rf_family'|'cortex_shared'|'oracle_screen'|'read_only', family: str|null}`. `rf_family` names MUST match `^rf\.[a-z_]+\.[a-z0-9_]+$`, be <40 chars, never equal an existing production family, and be declared via `TrialLedger.log_declared_budget()`/`log_grid()` BEFORE any screening run

*Owner program: research-factory*

### RF-7

**Challenger law: advisory-only; outcome-blind; LLM confidence scores forbidden**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The challenger is ADVISORY-ONLY; its output never selects a branch — every challenged candidate flows unconditionally to `human_review`. Two layers: (a) deterministic mechanical probes (no LLM), (b) Opus reviewer packet (spawned as agentType='reviewer', outcome-blind, FORBIDDEN from asserting known realized outcomes — `parametric_lookahead` is a blocker category). Categorical findings only; LLM-authored confidence scores are forbidden. Reviewer write scope: `data/research_factory/challenges/` ONLY.

**Scope fence:** Challenger writes to data/research_factory/challenges/ only; cannot advance any transition.

**Forbidden actions:**
  - challenger selects branch
  - challenger auto-kills candidate
  - LLM confidence score in review
  - reviewer asserts realized outcomes
  - bare model spawn for reviewer

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-7 — Challenger law.** The challenger is ADVISORY-ONLY. Its output never selects a branch: every challenged candidate flows to `human_review` with the packet attached; kills are human-authored.

*Owner program: research-factory*

### RF-8

**Ledger law: append-only transitions; forward ledgers nightly-only; git-tracked from row 1**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** All factory ledgers live in `data/research_factory/` and are git-tracked from the FIRST row. `transitions.jsonl` is append-only and is the audit history. `paper_monitor.jsonl` and `health.jsonl` are FORWARD LEDGERS: advanced only by the nightly engine job; intraday/manual invocations run `--dry-run` and write nothing under `data/`. Keep-first per `(candidate_id, as_of)`.

**Forbidden actions:**
  - edit transitions.jsonl non-append
  - manual write to paper_monitor.jsonl outside dry-run
  - manual write to health.jsonl outside dry-run
  - delete ledger history

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-8 — Ledger law.** `candidates.jsonl`, `transitions.jsonl`, `challenges/*.json`, `review/*.json|.md`, `health.jsonl`, `paper_monitor.jsonl` all live in `data/research_factory/` and are git-tracked from the FIRST row (explicit `.gitignore` negation pattern; bulk/replay parquet is the only gitignore'd class). `transitions.jsonl` is append-only and is the audit history.

*Owner program: research-factory*

### RF-9

**Clock law: no bespoke clocks; experiments registry_seed.json is the sole clock**

- Status: `active_law` | Kind: `process` | Nondelegable: `False`

**Ruling:** No bespoke clocks. Every candidate entering `paper`/`deferred`/`awaiting_data` gets an entry in `data/experiments/registry_seed.json` with `come_back_on`, `hook='track_record'`, and `track_json` pointing at the factory's per-candidate artifact. Paper entries stamp regime-at-entry for decay review. `expected_half_life_d` declared at human review with per-domain default prior (reversion ≈ 250 trading days), operator-overridable, recorded with `defaulted: true|false`.

**Forbidden actions:**
  - create bespoke factory clock
  - omit registry_seed entry for paper/deferred/awaiting_data
  - omit come_back_on

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **RF-9 — Clock law.** No bespoke clocks. Every candidate entering `paper`/`deferred`/`awaiting_data` gets an entry in `data/experiments/registry_seed.json` (kind `track_record`/`phase0`/`data_collection` as appropriate) with `come_back_on`, `hook='track_record'`, and `track_json` pointing at the factory's per-candidate artifact

*Owner program: research-factory*

### RF-U1

**Authority ceiling: factory operates at A0-A2 only; Article 1 origination ban**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** The research factory operates at constitution rungs A0-A2 only (observe/explain/attend). No factory output — LLM or script — may originate a signal, trade, escalation, or claim. `grant_authority()` refuses A7 unconditionally and the factory inherits that refusal by construction. Challenge packets are A1-EXPLAIN artifacts; the review queue is A2-ATTEND.

**Scope fence:** Display-only context only; no scored-path, no board influence, no autonomy rungs beyond A2.

**Forbidden actions:**
  - originate signal
  - originate trade
  - originate escalation
  - originate claim
  - grant A7 authority

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> **Authority ceiling (binding):** the factory operates at constitution rungs **A0–A2 only** (observe / explain / attend — `engine/neuralweb/constitution.py`). Challenge packets are A1-EXPLAIN artifacts. The review queue is A2-ATTEND. Article 1 (origination ban) is the hard ceiling: no factory output — LLM or script — may originate a signal, trade, escalation, or claim.

*Owner program: research-factory*

### RF-U11

**Reviewer outcome-blind: forbidden from asserting realized outcomes; parametric_lookahead is blocker**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The Opus reviewer is outcome-blind: explicitly FORBIDDEN from asserting known realized outcomes for named tickers/periods. `parametric_lookahead` is a blocker category the reviewer must self-police and flag. Reviewer receives aggregate metrics + leg verdicts but no per-fire outcome narrative. Categorical findings only; confidence scores are forbidden.

**Scope fence:** Reviewer write scope: data/research_factory/challenges/ ONLY.

**Forbidden actions:**
  - reviewer asserts named-ticker realized outcomes
  - reviewer assigns confidence score
  - reviewer write outside challenges/

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> outcome-blind prompting — the reviewer critiques mechanism and construction, is explicitly FORBIDDEN from asserting known realized outcomes for named tickers/periods (`parametric_lookahead` is a blocker category it must self-police and flag), receives aggregate metrics + leg verdicts but no per-fire outcome narrative.

*Owner program: research-factory*

### RF-U2

**Batch B (cortex) deferred until machine_registry.jsonl has real rows**

- Status: `deferred` | Kind: `wave` | Nondelegable: `False`

**Ruling:** Batch B (cortex adapter) is DEFERRED until `machine_registry.jsonl` has real rows. There is nothing to wrap today; the cortex adapter in W3 will be wired but the first batch is Oracle-only.

**Forbidden actions:**
  - run cortex batch before machine_registry has real rows

**Unblock condition:** machine_registry.jsonl has real rows (cortex registrations exist)

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> Batch B (cortex) is DEFERRED until `machine_registry.jsonl` has real rows — there is nothing to wrap today.

*Owner program: research-factory*

### RF-U3

**W-CODEGEN: separate future program; requires OS/identity boundary — no-build in this program**

- Status: `no_build` | Kind: `wave` | Nondelegable: `True`

**Ruling:** Arbitrary strategy codegen is a SEPARATE future program requiring its own ruling. It requires an OS/identity-level boundary: contents:read PR-only runner, branch protection, CODEOWNERS on `engine/validation.py` and gates. No codegen lane may be built inside the research factory program.

**Scope fence:** Codegen requires separate program with OS/identity boundary; forbidden inside this program.

**Forbidden actions:**
  - build codegen lane inside research factory
  - LLM edit engine/validation.py without separate program boundary

**Unblock condition:** Separate future program with OS/identity boundary, branch protection, CODEOWNERS on validators

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> W-CODEGEN: arbitrary strategy codegen behind an OS/identity boundary (contents:read PR-only runner, branch protection, CODEOWNERS on `engine/validation.py` and gates).

*Owner program: research-factory*

### RF-U4

**W-AUTO deferred: scheduled LLM extraction only after Batch A proof + service-key identity**

- Status: `deferred` | Kind: `wave` | Nondelegable: `True`

**Ruling:** Scheduled LLM extraction/challenge batches (W-AUTO) are DEFERRED until Batch A proves the loop, and then only via service-key (not user-OAuth) identity. This is a separate future program requiring its own ruling.

**Forbidden actions:**
  - schedule autonomous LLM extraction before Batch A proof
  - use user-OAuth for automated extraction

**Unblock condition:** Batch A proves the loop; service-key identity established; separate program ruling required

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> W-AUTO: scheduled LLM extraction/challenge batches + cost telemetry — only after Batch A proves the loop and only via service-key (not user-OAuth) identity.

*Owner program: research-factory*

### RF-U5

**Committee-page factory metrics: admin-only until further ruling; extend validated_claims if surfaced**

- Status: `deferred` | Kind: `context` | Nondelegable: `True`
- Authority ceiling: `A0_OBSERVE`

**Ruling:** Paper monitor metrics are admin-only until a separate ruling permits broader surfacing. If ever surfaced publicly, `scripts/check_validated_claims.py` SCAN_GLOBS must be extended to those templates. No committee-page visibility in this program scope.

**Scope fence:** Paper metrics display confined to admin console; any public surfacing requires extending validated_claims CI guard.

**Forbidden actions:**
  - surface paper metrics outside admin without extending check_validated_claims

**Unblock condition:** Separate ruling extending check_validated_claims.py SCAN_GLOBS to new templates

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> Committee-page visibility for paper metrics (admin-only until then; if ever surfaced, extend `check_validated_claims.py` SCAN_GLOBS to those templates).

*Owner program: research-factory*

### RF-U7

**Factory evaluates nothing; scores nothing; touches no board**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** The factory owns candidate identity, state, transition reasons, challenge packets, review packets, paper-monitor metadata, and retirement. It evaluates nothing, scores nothing, and touches no board. This is the core scope fence separating it from all existing evaluators (Oracle screens/gauntlets, cortex metabolism, alpha grammar runner).

**Scope fence:** Factory does not evaluate, score, or influence board output; delegates ALL evaluation to existing engines.

**Forbidden actions:**
  - factory scores candidate
  - factory influences board
  - factory runs evaluation logic

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> The factory owns candidate identity, state, transition reasons, challenge packets, review packets, paper-monitor metadata, and retirement. It evaluates nothing, scores nothing, and touches no board.

*Owner program: research-factory*

### RF-U8

**Cortex adapter: never writes machine_registry; respects 3/week metabolism chokepoint**

- Status: `active_law` | Kind: `data_contract` | Nondelegable: `False`

**Ruling:** The factory NEVER registers, never writes `machine_registry.jsonl`, and never bypasses the 3/week metabolism chokepoint. `source='cortex'` rows must carry the metabolism-issued id as `spec_ref` with registration timestamp ≥ metabolism's `registered_at`. The three-layer self-grading exclusion (`cortex_attention` refs) is re-checked before attaching any firings evidence. One-night cross-job lag is accepted and documented.

**Scope fence:** Cortex adapter is read/projection only; no writes to machine_registry.jsonl.

**Forbidden actions:**
  - write machine_registry.jsonl
  - bypass 3/week metabolism chokepoint
  - skip self-grading exclusion re-check

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> - **Cortex:** the factory NEVER registers, never writes `machine_registry.jsonl`, never bypasses the 3/week metabolism chokepoint. `source='cortex'` rows must carry the metabolism-issued id as `spec_ref` with registration timestamp ≥ metabolism's `registered_at`.

*Owner program: research-factory*

### RF-U9

**promote_eligible is NOT an autonomy rung and NOT a gauntlet registration**

- Status: `active_law` | Kind: `constitution` | Nondelegable: `True`
- Authority ceiling: `A2_ATTEND`

**Ruling:** `promote_eligible` means 'eligible to PROPOSE a separate program ruling' — explicitly NOT an autonomy rung and NOT a gauntlet registration. Any gauntlet registration and any autonomy ladder advancement requires a separate human-authored program ruling.

**Scope fence:** promote_eligible state does not confer any board or scoring rights.

**Forbidden actions:**
  - treat promote_eligible as gauntlet registration
  - treat promote_eligible as autonomy advancement

**Source:** `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`
> `promote_eligible` = "eligible to PROPOSE a separate program ruling" — explicitly NOT an autonomy rung and NOT a gauntlet registration.

*Owner program: research-factory*


### ruling-graph

### RUL-CL-1

**config/ruling_graph.yml is the single canonical case-law store**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** `config/ruling_graph.yml` is the single canonical store of case-law rows; `site/neuralwebdata/ruling_graph.json` and `docs/NEURAL_WEB_CASE_LAW.md` are deterministic build products of it, and no `data/` JSONL ledger exists in v1.

**Forbidden actions:**
  - create a data/ JSONL ledger for rulings
  - edit site/neuralwebdata/ruling_graph.json by hand
  - edit docs/NEURAL_WEB_CASE_LAW.md by hand

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> `config/ruling_graph.yml` is the single canonical store of case-law rows; `site/neuralwebdata/ruling_graph.json` and `docs/NEURAL_WEB_CASE_LAW.md` are deterministic build products of it, and no `data/` JSONL ledger exists in v1.

*Owner program: ruling-graph*

### RUL-CL-2

**Status and object_kind are separate vocabulary axes**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Codex's single 12-class list conflates disposition with object kind; the frozen vocabulary is two axes: `status` ∈ {active_law, adopted, residue_adopted, deferred, killed, no_build, duplicate, blocked, superseded} and `object_kind` ∈ {constitution, process, lobe, rail, wave, study, context, data_contract, signal_family}.

**Forbidden actions:**
  - use a single combined status/kind field
  - add new status or object_kind values without an adjudication amendment

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> Codex's single 12-class list conflates disposition with object kind; the frozen vocabulary is two axes: `status` ∈ {active_law, adopted, residue_adopted, deferred, killed, no_build, duplicate, blocked, superseded} and `object_kind` ∈ {constitution, process, lobe, rail, wave, study, context, data_contract, signal_family}.

*Owner program: ruling-graph*

### RUL-CL-3

**Ruling IDs are globally unique and namespaced**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Bare in-doc labels collide across programs (RUL-7 exists in entry-stack and elsewhere; RUL-27..34 overlap nontech numbering), so graph `ruling_id`s are globally unique — already-unique house labels (RUL-F3.8, DT-R14, LH-R11, RF-6, RUL-ORTH-8) are kept verbatim, and colliding plain-numbered labels get a program prefix (ESX-RUL-7, NW-RUL-3) with the bare label preserved in `aliases`.

**Forbidden actions:**
  - add a row with a bare generic ruling_id that may collide with another program
  - remove program prefix from a namespaced id

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> Bare in-doc labels collide across programs (RUL-7 exists in entry-stack and elsewhere; RUL-27..34 overlap nontech numbering), so graph `ruling_id`s are globally unique — already-unique house labels (RUL-F3.8, DT-R14, LH-R11, RF-6, RUL-ORTH-8) are kept verbatim, and colliding plain-numbered labels get a program prefix (ESX-RUL-7, NW-RUL-3) with the bare label preserved in `aliases`.

*Owner program: ruling-graph*

### RUL-CL-4

**Every row carries a verbatim source quote; source_lines is dropped**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Every row MUST carry `source_quote`, a verbatim contiguous excerpt (40–400 chars) from `source_doc`, and CI verifies byte-presence of every quote in its source; `source_lines` is dropped from the schema.

**Forbidden actions:**
  - omit source_quote from any row
  - use source_lines instead of source_quote
  - write a source_quote that is not a verbatim substring of source_doc
  - originate ruling text from LLM memory without a verifiable source

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> Every row MUST carry `source_quote`, a verbatim contiguous excerpt (40–400 chars) from `source_doc`, and CI verifies byte-presence of every quote in its source; `source_lines` is dropped from the schema.

*Owner program: ruling-graph*

### RUL-CL-5

**Seven-level precedence order governs ruling conflicts**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Precedence: (1) Constitution / CLAUDE standing law, (2) Fable masterplan or adjudication doc, (3) ratified PR body, (4) synapse/config law, (5) code guard/docstring, (6) data row or status log, (7) Codex/Fable-exit research packet; on conflict the lower-precedence row must cite `superseded_by`.

**Forbidden actions:**
  - allow a lower-precedence row to override a higher-precedence row without citing superseded_by

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> Precedence: (1) Constitution / CLAUDE standing law, (2) Fable masterplan or adjudication doc, (3) ratified PR body, (4) synapse/config law, (5) code guard/docstring, (6) data row or status log, (7) Codex/Fable-exit research packet; on conflict the lower-precedence row must cite `superseded_by`.

*Owner program: ruling-graph*

### RUL-CL-6

**Conflict checker hard-fails on FDR family and privacy tokens only (v1)**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The v1 checker hard-fails on exactly two crisp classes — (a) a new `fdr_family` token not present in the graph's known-families set, and (b) held-book/fill/position tokens appearing under public `site/` paths — and everything else (killed-idea re-proposal without citation, deferred-before-clock, lobe-charter language, quote drift, expired clocks) is WARN in v1.

**Scope fence:** WARN-to-HARD ratchet for killed-idea re-proposal and lobe-charter language is registered as W5 come-back wave; do not escalate until the graph has two clean weeks.

**Forbidden actions:**
  - add new HARD checks to check_ruling_conflicts.py without an adjudication amendment
  - hard-fail lobe-charter language before graph becomes the charter registry

**Unblock condition:** Two clean weeks with graph as charter registry (W5 come-back).

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> The v1 checker hard-fails on exactly two crisp classes — (a) a new `fdr_family` token not present in the graph's known-families set, and (b) held-book/fill/position tokens appearing under public `site/` paths — and everything else (killed-idea re-proposal without citation, deferred-before-clock, lobe-charter language, quote drift, expired clocks) is WARN in v1.

*Owner program: ruling-graph*

### RUL-CL-7

**Re-proposal detection uses deterministic diff-aware substring scan only**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Re-proposal detection is a deterministic, diff-aware substring scan of each row's curated `match_terms` against changed research/config files, requiring the ruling_id string to appear in the changed file to clear; no LLM matching runs in CI.

**Forbidden actions:**
  - use LLM or fuzzy/semantic matching in CI re-proposal detection
  - skip the ruling_id citation requirement for clearing a match

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> Re-proposal detection is a deterministic, diff-aware substring scan of each row's curated `match_terms` against changed research/config files, requiring the ruling_id string to appear in the changed file to clear; no LLM matching runs in CI.

*Owner program: ruling-graph*

### RUL-CL-8

**Clocked rows must reference experiments registry; no bespoke clock stores**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** A row with `come_back_on` must carry `experiment_ref` pointing at an experiments-registry id when a matching registry entry exists; the checker WARNs on clocked rows with no ref.

**Forbidden actions:**
  - create a second bespoke clock store separate from data/experiments/registry_seed.json
  - allow come_back_on rows to drift without experiment_ref when a registry entry exists

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> A row with `come_back_on` must carry `experiment_ref` pointing at an experiments-registry id when a matching registry entry exists; the checker WARNs on clocked rows with no ref.

*Owner program: ruling-graph*

### RUL-CL-9

**Public JSON carries only public_research rows; denylist tokens hard-fail**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** `site/neuralwebdata/ruling_graph.json` carries only rows with `privacy_class: public_research`, and the build hard-fails if a public row contains a denylisted token (competitor/source names and held-book vocabulary); rows from personality-source adjudications default to `privacy_class: internal_only`.

**Scope fence:** Public site JSON: public_research rows only. No held-book, fill, position, or competitor-name tokens in any public row's serialized content.

**Forbidden actions:**
  - expose internal_only rows in site/neuralwebdata/ruling_graph.json
  - include meta.public_token_denylist tokens in any public row serialized content
  - include held-book/fill/position vocabulary in public rows

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> `site/neuralwebdata/ruling_graph.json` carries only rows with `privacy_class: public_research`, and the build hard-fails if a public row contains a denylisted token (competitor/source names and held-book vocabulary); rows from personality-source adjudications default to `privacy_class: internal_only`.

*Owner program: ruling-graph*

### RUL-CL-10

**No PR template section in v1; CI checker carries enforcement**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** The Codex-proposed PR-template YAML section is DROPPED: no PR template exists in this repo and `gh pr create` (the only PR path agents use) does not apply templates non-interactively, so the CI checker carries the enforcement instead.

**Forbidden actions:**
  - add a ruling_graph_checked YAML PR template to the repo in v1

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> The Codex-proposed PR-template YAML section is DROPPED: no PR template exists in this repo and `gh pr create` (the only PR path agents use) does not apply templates non-interactively, so the CI checker carries the enforcement instead.

*Owner program: ruling-graph*

### RUL-CL-11

**v1 ships exactly the YAML, scripts, tests, generated docs, synapse, and CI job**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** v1 ships exactly: the curated YAML, `scripts/build_ruling_graph.py`, `scripts/check_ruling_conflicts.py`, `tests/test_ruling_graph.py`, the generated `docs/NEURAL_WEB_CASE_LAW.md` + site JSON, synapse registration, and the CI job; the admin panel tab, cortex read-only tools (`read_ruling_graph` et al.), and the Research Factory packet hook are registered come-back waves, not v1.

**Scope fence:** v1 only: YAML + build script + conflict checker + tests + generated docs + synapse entry + CI job. Admin tab, cortex tools, and Research Factory hook are W2-W4.

**Forbidden actions:**
  - add admin panel tab in v1
  - add cortex read_ruling_graph tools in v1
  - add Research Factory packet hook in v1

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> v1 ships exactly: the curated YAML, `scripts/build_ruling_graph.py`, `scripts/check_ruling_conflicts.py`, `tests/test_ruling_graph.py`, the generated `docs/NEURAL_WEB_CASE_LAW.md` + site JSON, synapse registration, and the CI job; the admin panel tab, cortex read-only tools (`read_ruling_graph` et al.), and the Research Factory packet hook are registered come-back waves, not v1.

*Owner program: ruling-graph*

### RUL-CL-12

**The ruling graph is display-only context; it may never gate, rank, or score**

- Status: `active_law` | Kind: `context` | Nondelegable: `True`
- Authority ceiling: `A1_EXPLAIN`

**Ruling:** The ruling graph is itself `object_kind: context`, `authority_ceiling: A1_EXPLAIN`, display-only, all authority booleans false; it may never gate, rank, score, or block a build by itself — its CI checker enforces *citation*, not *permission*, and only Fable/operator change law.

**Scope fence:** The graph is context-only. All authority booleans false. The CI checker enforces citation (did the PR cite the relevant ruling?), never permission (is this action allowed?). Only Fable or the operator may change law.

**Forbidden actions:**
  - use the ruling graph to gate a build or deployment
  - use the ruling graph to rank or score signals
  - let the CI checker block work based on authority rather than citation

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> The ruling graph is itself `object_kind: context`, `authority_ceiling: A1_EXPLAIN`, display-only, all authority booleans false; it may never gate, rank, score, or block a build by itself — its CI checker enforces *citation*, not *permission*, and only Fable/operator change law.

*Owner program: ruling-graph*

### RUL-CL-13

**Post-Fable rows proposed by anyone; accepted only by operator; nondelegable classes blocked**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** Fable seed rows are canonical; post-Fable rows may be *proposed* by any actor but *accepted* only by the operator, and rows touching authority, privacy, FDR families, lobe charters, or reviving a `killed` row are nondelegable — they stay blocked absent a frozen replacement adjudication procedure.

**Scope fence:** Nondelegable classes: authority changes, privacy class changes, new FDR family additions, lobe charter changes, killed-row revivals. All require Fable/operator adjudication. Proposals by Opus/Sonnet packets are permitted; acceptance is not.

**Forbidden actions:**
  - accept a new ruling row touching authority/privacy/FDR/lobe without operator approval
  - revive a killed row without a frozen replacement adjudication procedure
  - allow script actors to accept rows in any state

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> Fable seed rows are canonical; post-Fable rows may be *proposed* by any actor but *accepted* only by the operator, and rows touching authority, privacy, FDR families, lobe charters, or reviving a `killed` row are nondelegable — they stay blocked absent a frozen replacement adjudication procedure.

*Owner program: ruling-graph*

### RUL-CL-14

**v1 seeds are the verified extraction from 23 canonical sources curated by Fable**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** v1 seeds are the full verified extraction from the 23 canonical sources listed below (constitution, CLAUDE.md, the NW masterplan + rails + all seven NW adjudications, Research Factory, bridge, factor, R-ORTH, DannyTrades, live-activation, gap-map, OVC, entry-stack masterplan + amendment 3, cycle-pattern truth schema, quant-synthesis, long-hold, cycle-pattern masterplan), curated by Fable to rows with standing or cross-program force; program-internal micro-verdicts ride later waves.

**Scope fence:** Seed set covers the 23 listed canonical sources only. Program-internal micro-verdicts are not in v1 scope; they ride later backfill waves.

**Forbidden actions:**
  - treat program-internal micro-verdicts as mandatory v1 seeds
  - add seed rows without machine-quote-verification and Opus audit

**Source:** `research/RULING_GRAPH_ADJUDICATION_BY_FABLE.md`
> v1 seeds are the full verified extraction from the 23 canonical sources listed below (constitution, CLAUDE.md, the NW masterplan + rails + all seven NW adjudications, Research Factory, bridge, factor, R-ORTH, DannyTrades, live-activation, gap-map, OVC, entry-stack masterplan + amendment 3, cycle-pattern truth schema, quant-synthesis, long-hold, cycle-pattern masterplan), curated by Fable to rows with standing or cross-program force; program-internal micro-verdicts ride later waves.

*Owner program: ruling-graph*


### signal-commons

### NWP-U21

**L9 event-playbook lobe remains a Signal Commons wave; not this program**

- Status: `no_build` | Kind: `lobe` | Nondelegable: `True`

**Ruling:** No event-playbook lobe is built in this program. L9 remains a Signal Commons wave. This is a standing scope fence.

**Scope fence:** L9 event-playbook belongs to Signal Commons; not buildable under neural-web program.

**Forbidden actions:**
  - charter L9 event-playbook lobe under neural-web
  - build event-playbook outside Signal Commons program

**Source:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md`
> No event-playbook lobe (L9 remains a Signal Commons wave).

*Owner program: signal-commons*


### top3-lobe-power-up

### RUL-T3-1

**Closed proposals require new prereg citing closing evidence to reopen**

- Status: `active_law` | Kind: `process` | Nondelegable: `True`

**Ruling:** O1, O2, O3, O4, E2, E5, and M7 are closed as proposed (duplicate, null, locked, or illegal). Re-opening any of them requires a new pre-registered spec that cites and distinguishes the closing evidence. No re-run on any closed item without that prerequisite.

**Scope fence:** Applies to all seven closed proposals from this adjudication.

**Forbidden actions:**
  - reopen O1 without new prereg and population-expansion argument
  - reopen O2 O3 O4 E2 E5 M7 without new prereg citing closing evidence

**Unblock condition:** New pre-registered spec that cites and distinguishes the specific closing evidence for the target proposal.

**Source:** `research/NW_TOP3_LOBE_POWER_UP_ADJUDICATION_BY_FABLE.md`
> **RUL-T3-1:** O1/O2/O3/O4/E2/E5/M7 are closed as proposed (duplicate, null, locked, or illegal). Re-opening any of them requires a new prereg that cites and distinguishes the closing evidence above.

*Owner program: top3-lobe-power-up*

