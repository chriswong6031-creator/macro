# Neural Web Quant Synthesis — Program Masterplan (by Fable)

**Status:** ACTIVE program. Adjudicated 2026-07-05 (Fable main loop); inputs assessed by two Opus red-team passes plus a six-lane repo verification sweep the same day.
**Program slug:** `nw-quant-synthesis` (branches `claude/nwqs-*`).
**Scope:** adjudicate two external ChatGPT research reports and build only the surviving net-new fragments. Everything in this program ships display-only.

## 1. Inputs and verdicts

Two external reports, vendored alongside this file:

1. `INSTITUTIONAL_ALPHA_NEURAL_WEB_BOTTOM_GAP_REPORT.md` — institutional bottom-desk gap map (12 sensor families). Verdict: ~75% redundant with shipped or refuted work. Surviving fragments: dilution/refinancing-wall parsing (§3.6), bottom-survival-quality ratios (§3.7). Its tradeability roll-up (§3.10) is folded per FR-13.
2. `QUANT_FUND_NEURAL_WEB_ALPHA_STUDY.md` — quant-fund research-OS blueprint (15 components). Verdict: 7 already built, 5 partially built, 2 house-law blockers, ~3 net-new. Surviving: alpha grammar + overlap map (§4.1+4.2, coupled), delayed-fill staleness replay (§4.9), research-queue EV-ranker (§4.15).

Both reports independently re-derive standing house doctrine (no master score, no LLM-originated signals, display-only-until-earned) and present it as novel; the doctrine restatements are noted, not adopted as contributions.

## 2. Rulings

- **FR-1** — `utility_router` and `meta_router`-with-sizing: **REJECTED** (R3 "positioning fusion illegal" / RO-2 "fused composites rejected"). `expected_edge − λ·MAE − cost − crowding − uncertainty` feeding an action/size output is the forbidden fused-escalating-composite shape regardless of "shadow-only" framing. A pure take/skip **veto** (de-escalation-only, no sizing output) may be re-proposed as a fresh pre-registered trial after kernel arming (2026-10) — as a new registration, not a revival of this design.
- **FR-2** — The duplicate-of-existing registry in §3 is authoritative. Items listed there are not to be re-proposed without new evidence; future external-report assessments should cite this table first.
- **FR-3** — Build set = items A–E (§4) plus this docs PR. Nothing else from either report is scheduled.
- **FR-4** — Everything ships display-only/context tier; veto-shaped outputs are downgrade-only; zero board rank/size/alert changes anywhere in this program; the word "validated" stays out of user-facing text (CI-enforced).
- **FR-5** — The alpha grammar's first family is `confluence_response_alpha` — formulas over our own tier-fire panels (proprietary state), not generic 101-alpha OHLCV clones. Generic price/volume families get a capped later trial budget.
- **FR-6** — The overlap map emits cluster metadata only, never a combined score. `net_new_info_score` stays research-side. The duplicate-witness board display is deferred until the map survives its own accrual.
- **FR-7** — `failed_breakout` is registered as species **S14** (phase0, display-only) — registration only, no engine build. It is the research queue's first ranked customer.
- **FR-8** — Render budget law: EDGAR crawling and replay sweeps run off the render path. Replay artifacts follow EI R9 (`data/replay/`, Mac-local canonical checkout, never committed to git).
- **FR-9** *(verification amendment)* — The hazard panel (`scripts/build_hazard_panel.py`) is macro/cycle-level (11 SPDR sector + 24 country ETFs + 31 Shenwan codes), not per-stock. Per-stock fundamental features bind into `engine/neuralweb/bottom_sensors.py` (per-stock, display-only) and the `engine/stock_fundamentals.py` multiyear panel — NOT the hazard panel.
- **FR-10** *(verification amendment)* — `net_debt_to_ebitda` is not computable today: D&A is collected nowhere. Item A adds D&A to the `collectors/edgar_facts.py` FLOW dict (accrues via the weekly drip) and ships `net_debt_to_op_income` as an honestly-labeled proxy immediately; the true ratio activates as D&A coverage accrues.
- **FR-11** *(verification amendment)* — Item D's scope is the flat delayed-fill sweep (close fills at t+1…t+5) plus the staleness fitter. After-retest / after-pullback entries are pattern-conditional studies requiring their own prereg — deferred to a future EI wave.
- **FR-12** *(verification amendment)* — Item E artifacts live in `data/research/` **unregistered** (the `gate_fires_*.parquet` precedent) until a family survives its gates. No synapse.yml registration, no site output, no spine claims at research stage.
- **FR-13** — Report 1's tradeability/capacity roll-up (§3.10) is **folded**: it duplicates shipped effective-bets code (`engine/reflexivity.py` N_eff, `engine/foresight_enb.py` ENB). Any future portfolio-level N_eff consumer extends `reflexivity.py`; no new module.

## 3. Duplicate-of-existing registry (do not re-propose)

| External proposal | Existing home | Status |
|---|---|---|
| Ownership-pressure map / 13F breadth | `engine/beneficial_ownership.py`, `collectors/edgar_13f.py` | built, display-only |
| ETF/fund-flow pressure | `engine/etf_flows.py`, `engine/group_flow.py`, exit-crowding phase0 | built / phase0 |
| Short-interest split | `engine/short_volume.py`; crowding phase0 null; no PIT SI history | built; split not backtestable |
| Options panic / dealer positioning | `gex_engine.py`, `gex_model.py`, `options_skew.py`, `options_ivspread.py`, `market_gamma.py` | built; RO-2 bars composites |
| Event calendar (macro) | `engine/event_calendar.py`, `engine/event_risk.py` | built |
| Crowding / effective bets | `crowding.py`, `theme_crowding.py`, `froth_fragility.py`, `factor_exposure.py`, `fund_crowding.py`; N_eff in `reflexivity.py`, `foresight_enb.py` | built; split-half FAIL |
| Post-event absorption | SETUP_SPECIES **S9** (bad-news immunity), queued W3 | registered |
| Confidence surface (Brier/Wilson/ECE) | `validation.py` brier_reliability/ECE/platt; qledger Wilson; NW kernel | built; kernel arms 2026-10 |
| Hazard/survival desk | `hazard_score.py`, `fit_cycle_hazard.py` (macro-level) | built (macro); per-stock n-starved |
| Analogue retrieval | `engine/oracle/memory.py::find_analogues` | built |
| Falsifier generation | `engine/falsifier_tripwires.py` (+ per-ticker scope in item C) | built |
| Retirement state machine | `engine/species_registry.py`, `experiments_registry.py` | built |
| Disagreement mining | `contradictions.py`, `factor_contradictions.py`; W5A dissent study | built; study under-powered |
| Regime specialists (MoE) | regime gates exist; MoE is n-starved pre-kernel-arming | do not build now |
| Analyst dispersion / borrow / true fund flows | paid-data candidates | Phase-4 watchlist only |

## 4. Build items

### A — Bottom-survival-quality ratios (branch `claude/nwqs-a-survival-quality`)
`interest_coverage = op_income / interest_exp`; `net_debt = debt_lt + debt_cur − cash`; `net_debt_to_op_income` proxy (true `net_debt_to_ebitda` as D&A accrues per FR-10). Source: `data/edgar/statements.parquet` (all inputs already collected except D&A). New `_leverage_ratios()` helper in `stock_fundamentals.py` following the `_altman()`/`_piotroski()` pattern with the fy≤panel-fy PIT filter; bound into the multiyear panel and `bottom_sensors.py` per-ticker rows. None-safe throughout (Financial-sector names will mostly be None); weekly-drip partial coverage is acceptable for display-only.

### B — Research-queue EV-ranker + S14 registration (branch `claude/nwqs-b-research-queue`)
`engine/neuralweb/research_queue.py`: read-only deterministic prioritizer over the cortex hypothesis inbox, `machine_registry.jsonl` (absent-file-safe), the species registry, and the trial ledger. Output categories: `high_ev_build_now` / `blocked_by_data` / `too_sparse` / `duplicate_of_existing`, plus `next_best_experiment`. Feasibility scoring accounts for the server-side min_n=25 clamp. It NEVER writes `machine_registry.jsonl`; `metabolism.register_hypothesis()` remains the sole budget chokepoint. Artifact `data/neuralweb/research_queue.json`, registered in `config/synapse.yml` (tier: infrastructure) and envelope-stamped. S14 `failed_breakout` registered via the `species_registry` API (phase0/unshipped; `adjacent_falsified` cites the Wave-5 retest_hold falsification).

### C — Dilution / refinancing-wall collector (branch `claude/nwqs-c-dilution`)
`collectors/edgar_dilution.py`: daily-index sweep (the `beneficial_ownership.py` pattern — S-3 is absent from EFTS full-text search) for S-3/S-3ASR and 424B1–B5; UA via `edgar._cfg()['user_agent']`; 0.12s pacing; append-only `data/edgar/dilution_events.parquet` keyed by accession with `filing_date` (PIT) + `_first_seen` stamps; registered in `scripts/collect.py` ('sec' host group + `_SLOW`) so it runs nightly-only, never on the render path. Per-ticker display flags (`days_since_shelf`, `days_since_takedown`, `dilution_events_365d`) bound into `bottom_sensors.py` (None-safe, parquet-absent-safe for render). `falsifier_tripwires.py` gets an additive scope extension: `TripwireResult` gains `scope`/`tickers`; `results_summary()` excludes `scope='ticker'` entries from cycle grouping (cycle-page UI unaffected); new `results_by_ticker()` helper; an `edgar_dilution:<TICKER>` series-group resolver for future DSL legs. No mass tripwire generation in this program.

### D — Delayed-fill staleness replay (branch `claude/nwqs-d-staleness`)
`scripts/replay_standout_pipeline.py --delay-sweep`: grades already-logged fire rows at close fills t+1…t+5 (`fill_index + 0..4`), re-evaluating `horizon_censored` per delay; long-format `data/replay/replay_delay.parquet` (EI R9: Mac-local, never git; atomic tmp+rename write). No PIT-gate changes; no recall re-run. `engine/neuralweb/half_life.py` gains the `decay_kind='staleness'` fitter (per family: mean outcome vs delay, exponential fit with HAC-t gate, honest null otherwise); honesty header updated; degrades gracefully when the artifact is absent (CI runners). This unblocks the SIGNAL_COMMONS parked item ("staleness half-life — replay harness accrues delayed-fill variants").

### E — Alpha grammar + overlap map (branch `claude/nwqs-e-alpha-grammar`)
`engine/neuralweb/alpha_grammar.py` (formula AST, constrained primitive set, deterministic enumeration, lag≥1 PIT law), `scripts/research/compile_alpha_candidates.py` (family `alpha_grammar_confluence_v1` over the `gate_fires_deep`/`gate_fires_baskets` panels; `TrialLedger.log_grid()` BEFORE grading; rank IC via `validation.py` numpy paths; DSR via `deflated_sharpe(ledger=, family=)` — never literal `n_trials`; within-family BH-FDR; honest nulls printed), `engine/neuralweb/alpha_overlap.py` (forecast_corr, fire_jaccard, outcome_corr, correlation clustering, cluster_representative, net-new-info via incremental IC). Artifacts to `data/research/` unregistered (FR-12). Candidate cap v1: 200 declared. Survivorship stamps carried; era filtering per the entry-stack W0 convention.

## 5. Preregistrations

- **staleness_delay_v1** (item D): grid = {t+1…t+5} × replay fire families, logged to the trial ledger before fitting. Measurement: mean `fwd_ret_21` (and MAE) by delay per family. Gate: exponential decay fit with negative slope, HAC-t significant; else a per-family honest null. This is a descriptive decay measurement — no strategy claim is made or permitted.
- **alpha_grammar_confluence_v1** (item E): ≤200 candidates enumerated over pre-fire state features predicting post-fire outcomes on the tier-fire panels; ledger-logged before grading; DSR + within-family BH-FDR (α=0.10). Expected outcome: mostly or entirely null — the nulls are the product (they prune the space and prove the pipeline end-to-end).

## 6. Promotion

Inherited unchanged from the NW constitution and species constitution: display-only → (incremental lift on the same-computable subset, minimum event counts, regime stability or explicit regime scoping) → confirmer → (baseline-beating after costs, FDR within family, live-forward evidence) → scored. Hard-gate authority only via gauntleted fragility vetoes, and even those start downgrade-only.
