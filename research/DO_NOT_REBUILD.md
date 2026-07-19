# DO NOT REBUILD — standing kills, forbidden designs, refuted theses

Status: CURATED REGISTRY (append-only by adjudication). Established by ABM-R5,
`research/ACTIVE_BUILD_MAP_ADJUDICATION_BY_FABLE.md` (2026-07-07).

Purpose: every external-intake adjudication (Codex dockets, vendor reports, new-session
proposals) has found 55–80% of proposals duplicate work that is already built, in flight,
killed, or forbidden. The temporal half of that problem is covered by the generated
`docs/ACTIVE_BUILD_MAP.md` (open PRs / collisions / recent merges). This file covers the
permanent half: topics that are dead by ruling and must not be re-proposed without NEW
evidence and an explicit Fable/operator ruling.

**Authority (mirrors FR-2):** future external-report assessments and adjudications must
cite this registry first. An entry here is grounds for summary REJECT-REDUNDANT.

**Append convention:** any PR whose adjudication kills, forbids, or indefinitely defers a
topic appends one row to the matching section *in the same PR*. One line per entry:
topic | verdict | ruling/source. Keep grounds in the source doc, not here.
Rows are machine-compiled from sections 1–4 ONLY — a row anywhere else is invisible to
enforcement and hard-fails CI. Commit the regenerated `config/compiled_kill_registry.yml`
and `config/signal_foundry_blocklist.yml` with the row (harness edits auto-regen via the
`blocklist_regen_guard` hook; manual heal: `python3 scripts/check_blocklist_drift.py --fix`).

Verdict formats across `research/` are too inconsistent to auto-extract (three dominant
patterns + ~15% freeform prose over 492 docs — census 2026-07-07), so this registry is
curated, not generated. Do not build an extractor.

## 1. Forbidden by ruling (design-level — no phase-0 may test these)

| Topic | Verdict | Ruling / source |
|---|---|---|
| Fused shield / meta-router over buy-decision vetoes | FORBIDDEN | FR-1/R3; Codex buy-decision docket adjudication (#1781) |
| Kernel conditioning before NW clocks arm (kernel-FDR 2026-10) | FORBIDDEN | Signal Commons rulings (2026-07-05) |
| Positioning fusion (positioning keys fused into signal scores) | ILLEGAL | Signal Commons rulings (2026-07-05) |
| LLM-originated signals, scores, or escalations | FORBIDDEN — LLMs may only de-escalate calibrated keys | House law (CLAUDE.md §Epistemics) |
| New human-override gates laundered into `allocation()` (pattern: midterm-blackout gate) | FORBIDDEN pattern | BTC vector override audit D1–D5 |
| Rotation × cycle-position entry-confluence | DON'T-TEST | Rotation×cycle confluence ruling (cycle intelligence program) |
| rs-based member-dispersion gates | DON'T-TEST — rs is zero-sum tautology (R-4) | Healthcare member-dispersion adjudication |
| Short-side lobe as directional shorting | FORBIDDEN — L1 is AVOID-not-SHORT evidence only | NW rails+lobes program (2026-07-06) |
| Signal-engine verdicts at non-pre-declared horizons | FORBIDDEN — verdicts only at registered `horizon_role` ruler | Backtest-horizon ladder law |
| Parallel shock-vector classifier beside `market_drivers` (12-type re-vocabulary) | REJECT-REDUNDANT — `snapshot()` is the canonical shock read; crosswalk printed | TI-R1, `TECH_INTERNALS_CODEX_ADJUDICATION_BY_FABLE.md` |
| Shock→archetype beneficiary/casualty ("shelter") map as an NW/brain feed | KILLED — laundered directional escalation on nulled continuation claims | TI-R5, `TECH_INTERNALS_CODEX_ADJUDICATION_BY_FABLE.md` |
| LLM classification of narrative-only shock types (tariff/regulatory/cyber/edge/consumer) into calibrated keys | FORBIDDEN — no deterministic price basis; A7 ORIGINATE ban | TI-R1, `TECH_INTERNALS_CODEX_ADJUDICATION_BY_FABLE.md` |
| Fused per-position composite risk number (any grain) in watchlist/portfolio surfaces | FORBIDDEN — aggregates are printed lane counts + named role ladders only. (PRD-R1 placement exclusivity struck by operator override 2026-07-18, PRD Amendment 1 — user-facing display-tier watchlist+portfolio surface now allowed in this repo under UWP rulings) | PRD-R2 + Amendment 1, `PORTFOLIO_RISK_DESK_MASTERPLAN_BY_FABLE.md`; UWP-R1..R7, `UNIFIED_WATCHLIST_PORTFOLIO_MASTERPLAN_BY_FABLE.md` |
| Causal DAG → alpha score → trade / portfolio construction from discovered graphs | FORBIDDEN — CHF is proposal/audit tier only; Article 1/2 | CHF-R14, `CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md` |
| Administration-timing predictor / policy-intent classifier (forecasting WHEN a policy lever fires; LLM-emitted geopolitical re-escalation probabilities) | FORBIDDEN — intent unfalsifiable; conditions-framing only | PS-R1/PS-R4, `POLICY_SHOCK_REGIME_MASTERPLAN_BY_FABLE.md` |
| LLM numeric confidence anywhere in CHF surfaces | FORBIDDEN — RF-16 extension | CHF-R14, `CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md` |
| Runtime LLM frame-tag / narrative-frame classification feeding any organ state or escalation-eligible key | FORBIDDEN — TI-R1/CONST-ART1 restated; char-span receipts validate the quote, not the classification; frame annotation is display-only | NAR-R4, `NARRATIVE_IGNITION_MASTERPLAN_BY_FABLE.md` |
| Chatter-only promotion to a narrative candidate state (source-credibility-alone escalation without the cross-modal tape veto) | FORBIDDEN — single credible flare earns salience, never authority; veto unconditional | NAR-R2, `NARRATIVE_IGNITION_MASTERPLAN_BY_FABLE.md` |
| Hypothesis-slot pre-reservation via standalone coverage census (bypassing WA-R8's ≥8-cases + Opus fingerprint + explicit-ruling gate) | FORBIDDEN — a census proves testability, never entitlement; second attempted end-run (LR docket round 1, LH brainstorm round 2) | LHB-R5, `LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md`; precedent LR-R9 |
| Calendar/event-window-gated risk-radar `_SCARES` legs (any tier — Tier-B advances state, state sets gross) | FORBIDDEN — laundered pre-event conviction dampener; event/OPEX windows are display context only; risk channels must be calendar-agnostic constructions | RIC-R3, `RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md` judge-panel ruling (2026-07-13) |
| `sector_rotation_schedule.v1` display artifact (parallel rotation-schedule surface) | DO NOT BUILD — duplicates shipped Turn Desk (#1541); macro conditioners, if wanted, fold into Turn Desk / `oracle_state.json` as Family-D columns, not a parallel uncalibrated surface | `ORACLE_ROTATION_TM_CODEX_ADJUDICATION.md` (2026-07-06, #1750); RL-R10(e), `RATIO_LENS_MASTERPLAN_BY_FABLE.md` |
| Hard-gating nightly downstream jobs on the collect job's result (skip engine/publish when collect cancels) | FORBIDDEN — reverts the ratified `if: always()` resilience law (partial output beats shipping nothing; salvage-push covers the push-race). Staleness is handled by disclosure (CSP-W5) + heartbeat detection (CSP-W6), never by fail-dark | CSP-R1, `CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md` (2026-07-17) |
| Composite market-regime scorecard fusing gamma/vol/flow/breadth into a regime verdict + tactical ETF allocation surface (Ivory Hill Gamma Report intake §17, SPLV/SPHB/SPXL grid) | REJECT-REDUNDANT + FORBIDDEN fusion path — duplicates the risk_radar→market_state→regime_vector authority chain and the strategies allocation layer (SPVector); fusing positioning keys into a regime score restates Signal-Commons positioning-fusion ILLEGAL | MSP-R2, `IVORY_HILL_MARKET_STRUCTURE_MASTERPLAN_BY_FABLE.md` (2026-07-18) |
| Second hand-maintained knowledge base / wiki / RAG memory service parallel to canonical sources (agents required to write session knowledge into a separate database) | FORBIDDEN — knowledge retrieval is the Macro Context Index (derived, rebuildable, canonical-sources-keep-truth); a hand-curated parallel store is the ratified program's named degenerate form | CXI-R12, `MACRO_CONTEXT_INDEX_ADJUDICATION_BY_FABLE.md` (2026-07-18) |

## 2. Killed / refuted signal families and theses

| Topic | Verdict | Ruling / source |
|---|---|---|
| Cross-organ flip-counter (conjunction-of-transitions deterioration meter) as a standalone organ | KILLED — double-counts the cascade meter's intl leg, log-birth FP (07-07 artifact), count-conjunction class (RISK_RADAR_TUNING line 93 governs any authority path) | RSR-R6a, `RISK_SCORING_REVAMP_MASTERPLAN_BY_FABLE.md` (2026-07-17) |
| "4-of-4 defensive-lean floor bundle" v1 (radar-caution × ≥3-intl-alerts × rotation-bottom × weekly-roll → display 35) | KILLED — claimed 1–2d lead collapsed on verification (only CN+HK alerted pre-07-16, TW log born 07-16 → zero lead); count-conjunction class. Floor QUESTION stays open via RSR-W5 prereg | RSR-R6b, `RISK_SCORING_REVAMP_MASTERPLAN_BY_FABLE.md` (2026-07-17) |
| 1-tick asymmetric escalation flips of the live risk-band debounce | KILLED — a single noisy print flips the authoritative band (whipsaw → operator mutes). Lawful form is the pending-escalation badge: band keeps the 2-tick debounce, in-progress escalation surfaced the same tick | CSP-R2, `CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md` (2026-07-17) |
| News-intel / thematic-desk LLM contagion tagging of theme rows | KILLED — NAR-R4-adjacent surface with near-zero marginal value; engine-originated contagion key (CSP-W1) + glance chip (CSP-W4) supersede | CSP-R3, `CONTAGION_SENSING_PROPAGATION_MASTERPLAN_BY_FABLE.md` (2026-07-17) |
| Insider × T2 interaction | KILLED | Codex buy-decision docket adjudication (#1781) |
| Washout × turn (2W operator seed) | KILLED — operator seed dies in test | Entry-stack Amendment-3 adjudication (#1747) |
| Signed-charm / charm-intensity narratives | KILLED — vol/size confound, trail-RV IC .5–.6 | OPEX vanna/charm adjudication (2026-07-06) |
| DOI (options delta-OI family) | DEAD | Options→NW entry-intelligence W-E1 gauntlet |
| Skew-deceleration | UNSUPPORTED | Options→NW entry-intelligence W-E1 gauntlet |
| DannyTrades directional chip reads (all) | RETIRED — chip is descriptive only; H1 pooled effect was pre-2010-only | DT-R15/DT-R16; DANNYTRADES adjudication + DT-W2 (#1751) |
| Entry-time thesis at 21d (insider / macro / positioning) | REFUTED 3-for-3 — T2 ceded to long-hold LT-3a | Nontech-bottom program (RUL-18..29) |
| Election / midterm cycle as standalone signal | REFUTED — survives only as US-only Risk-Radar modulator | Election-cycle modulator study |
| Gating A-share reversal by subsector state | FALSIFIED — hurts vs flat | China subsector-gate study (#791 era) |
| Label-faltering B1/B3 | NO-GO | Phase-0 verdicts (#1031) |
| PM1 AVWAP-from-base-low distance (standalone, as-constructed) | FALSIFIED phase-0 — nulls + unfavorable dead-money read; retained as display-tier confluence input | EI-PM0 run (2026-07-10, r4) |
| PM3 unfilled-overhead-gap map (as-constructed, incl. sign-flip revival) | FALSIFIED phase-0 — DIRECTION-CONTRADICTED (clean-sky fires stop MORE, BH 0.0031); inverse reading needs a new PREREG | EI-PM0 run (2026-07-10, r4) |
| PM4 overhead-supply fraction (any promotion path) | REDUNDANT — \|ρ\| 0.95/0.88/0.875 vs ext_atr / poc_dist_126 / dist_to_52wh (§4.3 fence) | EI-PM0 run (2026-07-10, r4) |
| Codex rotation Time Machine KEEPs (A18/A19/A24 same-complex) | REJECT-REDUNDANT / INVALID — complex already screened dead | `ORACLE_ROTATION_TM_CODEX_ADJUDICATION` (#1750) |
| "Thesis lobe" | KILL — duplicate of long-hold program | NW next-lobes adjudication (#1666/#1669/#1671) |
| BD-4 species | PARKED — sign-reversed in Phase-0b | Next3-upgrades program (#1710 era) |
| BD-ECON-1 | ALL-NULL — avoid lens ≠ board fires | Next3-upgrades program |
| FRESH BUY as a buy edge on the Act-Now board | REFUTED — worst state on the board; reduce-gate is the only board edge | Act-Now board ruling (#1513) |
| Codex OOS-decay orthogonality claim | NOISE ARTIFACT — null law | RUL-ORTH-8, R-ORTH program (#1739) |
| Staleness alpha t+1..t+5 | HONEST NULL | NW quant synthesis (#1455–1465) |
| Measured signal half-lives; dissent signal | ALL-NULL | Signal Commons W3/W5 (2026-07-05) |
| construction_divergence (healthcare R-1) | LOCKED DESCRIPTIVE — null held | Healthcare member-dispersion adjudication |
| CPI-020 | RETIRED — re-test FAIL | CPI lattice batch 2 (#1754) |
| CPI IX-1 index-transfer down cells | KILLED by sign-stability leg (0/4 PASS) | CPI IX-1 §17 (#1779) |
| Buyback-floor washout (S11) | FALSIFIED | S11 phase-0 (#1782) |
| Margin-inflection reclaim (S10 v1.0, strict-sign single-quarter turn as-constructed) | FALSIFIED phase-0 — construction-scoped kill (predicate anti-persistent, EDGAR Q4-gap row-adjacency, episode MDE ≈6–8pp vs 5pp floor); margin-direction retained as confluence input; revival needs a NEW species version + fresh prereg (durability-gated, calendar-adjacent, prefix-matched comparator) | S10 phase-0 adjudication (#2396), research/species/W5_S10_REPORT.md §12 |
| Fused 100-point "sponsorship breakaway" score (Codex Moderna docket §5.2) | STRUCK — positioning-fusion illegal + Signal Commons R3; replaced by per-axis AND-gate | WA-R1, `WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md` |
| 13F/ownership as a POSITIVE breakaway signal (Codex Moderna docket §4.1 ownership_pressure) | STRUCK — restates NEXTL-U13 (opposite sign to 3 filed verdicts); survives as context/crowding-hazard only | WA-R2, `WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md` |
| `cn_supply_absorption` family (incl. D4-01b staged re-entry) | CLOSED — Stage-0 falsifier dead in both 减持新规 regimes at the frozen ruler (EW +1.1pp/21d, t_NW 1.91/1.77 < 2; overlap-lag sensitivity confirms); construct kill (price-only absorption ≡ momentum) stands per #1944. Close-call POSITIVE null retained as confluence context; re-entry needs a fresh operator-ratified prereg (post-规 cell ~doubles by ~2028) | D4-01b Stage 0, `reports/d4-cn-supply-absorption-d401b-stage0.md`; Day-4 adjudication §D4-01 reassessment |
| Hindenburg Omen / Titanic Syndrome as Risk-Radar inputs | REJECT-DATA/STAT — needs uncollected NYSE full-universe NH/NL; N~20–30 clusters/40y; ~40% 1y WR (≤ random) | RRX-R10, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §6 |
| IBD distribution-day count as a radar leg | REJECT-REDUNDANT — coincident down-day counter; froth_fragility owns distribution physics | RRX-R10, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §6 |
| McClellan MCO thrust / MCO-oversold+MSI-washout *bounce* as radar legs | REJECT-KILLED — coincident-by-construction (SIGNAL_AUDIT); display homes (advanced_breadth, fear_greed) stand; rare Summation low→high *upswing* adjudicated separately as recovery chip | RRX-R4/R10, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §6 |
| Absolute-VIX spike-and-fade thresholds | REJECT-STAT — non-stationary absolute anchors (R-SP21); <10 episodes in >50 bucket | RRX-R10, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §6 |
| Lumber/gold ratio (daily growth filter) | REJECT-DATA — FRED monthly-only, LBS=F thin, supply-shock contaminated; use copper/gold | RRX-R10, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §6 |
| Dow Theory transports non-confirmation as a radar leg | REJECT — lagging (2007 signal fired post-peak), oil-confounded; rotation physics covered by validated XLY/XLP + XLU legs | RRX-R10, `RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §6 |
| CPI revision-direction model (first→latest MoM revision prediction) | KILLED before attempt — CPI revisions are annual seasonal-recalc only, tiny magnitude; empirics on our own vintage store show no exploitable structure | MRI-R38, `MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md` §12.3 |

## 3. Wrong-ruler / estimator laws (methodology — using these invalidates the study)

| Topic | Verdict | Ruling / source |
|---|---|---|
| Ticker-cluster bootstrap CIs without time control | FORBIDDEN estimator — anti-conservative, effective N = months | DT-R14; `TIME_CONFOUND_EXPOSURE_AUDIT` (#1755) |
| 63d factor apparatus applied to Oracle reversion signals | WRONG RULER — score as reversion-capture (~20–25d time-exit, absolute) | Oracle reversion metric reframe (#1458) |
| Era-pooled inference across the 2010 regime break | FORBIDDEN without era split | DT-R16 era-split law (#1751) |
| Closing a factor family on a single-factor kill | INCOMPLETE — diagnose mechanism + pre-registered pairlets first | Factor-kill interaction feedback law |
| R1-M estimator shortcuts | Constrained per R1-M estimator law | Nontech-bottom program |

## 4. Held / suspended — do not revive without explicit ruling

| Topic | State | Ruling / source |
|---|---|---|
| Ontology W4.7 pos_v2 acceptance | HOLD — peak gate IQR 48.8 > 25 | Open PR #1639 (do not accidentally revive) |
| Theta tape | SUSPENDED | Final3-lobes program (2026-07-06) |
| DISP-GATE-1 | DEFER ×2-replicated | Final3-lobes program (#1696) |
| PM5 × 6 price-memory trials | SUSPENDED `data_blocked` (pre-declared; coverage measured 55.3% < 60% floor at execution) | PM0 prereg (#1761) + EI-PM0 run (2026-07-10) |
| G1 | DEFERRED | Long-hold thesis program (#1507/#1588) |
| W-F (options) | PARKED until preconditions (1)+(2) | Options→NW masterplan |
| CODEOWNERS / branch protection | DEFERRED to RF codegen lane scope | ABM-R3; `RF_CODEGEN_LANE_FOR_FABLE.md` |
| Per-ticker multi-label business-model exposure tags (tech) | DEFERRED — group-level taxonomy only; revive needs revenue-geography ingestion + own adjudication | TI-R2, `TECH_INTERNALS_CODEX_ADJUDICATION_BY_FABLE.md` |
| Public "Breakaway Desk" site page (Codex Moderna docket §7.1) | DEFERRED — W0 ships admin-panel surface only; public copy needs its own wave | `WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md` §8 |
| Winner-autopsy short-interest / squeeze-fuel legs (Codex Moderna docket §4.3) | DEFERRED with L10 — no PIT short-interest history (single FINRA settlement date) | WA-R (docket adjudication), aligns NEXTL-U19 |
| Full-graph causal structure learners (NOTEARS/DAG-GNN/LoRAM/CMIN-class) + weekly full-DAG re-estimation | KILLED for v1 / REJECTED (churn) — small-universe NOTEARS-with-priors is a Phase-3 question behind the 2027-01-15 clock | CHF-R14, `CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md` |
| Dedicated CHF machine-registration family through metabolism | DEFERRED — Phase-2 clock 2026-10-15, needs ≥8 matured exit-(a)/(b) candidates + fresh ruling; cortex 3/week chokepoint stands (QS-U2) | CHF-R2, `CAUSAL_HYPOTHESIS_FACTORY_MASTERPLAN_BY_FABLE.md` |

## 5. Incorporated by reference

- `research/NW_QUANT_SYNTHESIS_MASTERPLAN_BY_FABLE.md` §3 — duplicate-of-existing registry
  (FR-2, 15 entries mapping external proposals to existing homes). Cite before assessing any
  external quant report.
- Per-program ruling tables: DANNYTRADES DT-R1..R16, entry-stack Amendment-3 RUL-27..34,
  Signal Commons rulings, R-ORTH RUL-ORTH-1..8, nontech-bottom RUL-18..29.
- `docs/ACTIVE_BUILD_MAP.md` — the generated temporal complement (open PRs, collisions,
  recent merges). Regenerate: `python scripts/build_active_build_map.py`.
