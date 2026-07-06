# Long-Hold Thesis Layer — Masterplan (by Fable)

**Ratified:** 2026-07-05
**Source study:** `research/LONG_TERM_COMPOUNDING_NEURAL_WEB_STUDY.md` (external ChatGPT/Codex study, committed as-received for provenance)
**Assessment method:** 6-lane repo census (Sonnet) + 4-lens adversarial review (Opus: statistics, house law, feasibility, alpha realism) + Fable adjudication. All census claims below carry file:line or data-inspection evidence from the assessment run.
**Program status:** CHARTERED — W0 authorized to build immediately; W1+ gated as below.

---

## 0. Verdict on the source study

The study's core insight is correct and load-bearing: **entry signals and hold theses are different species with different clocks, and forcing one score to do both jobs creates exactly the chaos the operator reports.** Its epistemic instincts (moat-as-falsifiers, no megascore, display-only staging, LLM extraction-only) are house-compatible.

But four of its claims failed verification, and its build order is inverted:

| Study element | Verdict | Ruling |
|---|---|---|
| Entry vs hold = different species, separate clocks (§0/§3/§7.1) | **ADOPT + ELEVATE** | Becomes W0's mechanical firewall, not prose |
| Missed-hold study as Phase 6 (§7.5) | **ADOPT + PROMOTE to Wave 1** | It is the program's only kill-test; runs first, on existing data |
| Moat falsifier sensors (§5.4/§7.3) | **ADOPT, reshaped** | Extension of `engine/falsifier_tripwires.py`, never a new system, never a composite "moat score" |
| Compounder feature columns (§5.2/§5.3) | **ADOPT, re-costed** | ~80% computable from existing `statements.parquet`; days not weeks |
| Compounder Admission Test single verdict (§5.1) | **KILL as designed** | Forbidden fused-escalating-composite (Signal Commons R3 / FR-1). Rebuilt as AND-gate of independently registered flags via species ladder |
| 756d (and headline 504d) outcome labels (§6.1) | **KILL as headline labels** | Survivorship-crippled (see §2). Permitted only caveat-stamped |
| "Let the kernel learn 12-36m outcomes" (§10) | **KILL as forward loop** | ~1 obs/name/yr maturing 3y late = decade-scale promise. Replaced by pre-registered pooled historical study |
| "Forward valuation snapshots already exist" (§1) | **FALSE** | No EV/sales, EV/EBIT, P/FCF anywhere in engine outputs; only fwd_pe on ~110 yfinance names |
| Reverse-DCF / valuation-implied expectations (§5.6) | **DEFER to W3, v1 = EV/sales only** | EBITDA-multiple paths data-blocked (depreciation never collected from EDGAR) |
| Theme-cashflow-transmission graph (§5.9) | **CUT** | No supplier/customer graph exists anywhere in the repo; requires paid supply-chain data (SKIP-ALL ruling 2026-07-05); theme momentum rank-IC ≈ 0 |
| Universe-scale KPI registry (§5.8) | **CUT** (MVP deferred behind W3 gate) | High-value sources are the exact paid feeds ruled SKIP-ALL |
| Hold-book risk/overlap view (§6.6) | **CUT** | Belongs to an unchartered portfolio-construction program |
| Thesis ledger (§5.10) | **DEFER to W3, reshaped** | Deterministic tripwire-fired transitions only; "reason to hold" framing killed (Article 1); built only after W1 non-null |
| Live qledger extension to 252/504/756d | **CUT** | `GRADE_HORIZONS=(5,21,63)` stays; multi-year open claims in the nightly grader forbidden; separate off-render research grader instead |

**In plain English:** the study wanted to build a compounder-picking machine. The evidence says we can't measure compounder-picking honestly yet (the dead companies are missing from our data), and our fundamental-quality signals have near-zero measured edge even on the flattering data. What we CAN build honestly, now: (1) a hard wall between "good entry" and "worth owning" so the two never get confused again; (2) machinery that watches a winner we already own and tells us when the evidence for holding it breaks; (3) one rigorous study that tells us whether "worth owning" was ever visible at entry — and if the answer is no, we stop there and print it.

---

## 1. Reframed objective (three tiers, in priority order)

1. **Discipline (ships unconditionally, W0):** a mechanical, CI-enforced horizon firewall. Every registered signal/artifact is stamped `tactical_entry | hold_thesis | dual | context`, and a hold-stamped key can never touch an entry surface (or vice versa). This directly resolves the operator's reported entry/hold confusion and has value even if every alpha hypothesis dies.
2. **Duration-extension (W2):** for names the entry stack already caught, separate the entry clock from the thesis clock and surface falsifier evidence on the hold reason. Shaped as de-escalation/annotation only — Article-1-clean by construction. The deliverable is the machine that says: *"your entry reason has expired; here is the state of the evidence for continuing to own this."*
3. **Selection alpha (option, gated by W1):** whether hold quality was visible at entry is an empirical question the missed-hold kill-test answers. Until it prints non-null, no selection machinery is built.

Honest timescale: under Article 2/3 (SHADOW-with-track-record, n≥25 episode-clusters, Wilson-CI gate), no long-horizon key can influence any behavioral surface before ~2028-2029. This program is chartered knowing that.

---

## 2. Census ground truth (load-bearing facts)

**Fire tapes (the study population):**
- `data/research/gate_fires_baskets.parquet` — 113,542 fires, 2,495 tickers, 2014-08-11 → 2026-07-02. **The primary population for per-name labeling.**
- `data/research/gate_fires_deep.parquet` — 38,250 fires but only 220 tickers (mostly ETFs/mega-cap survivors), 85% pre-2021. Secondary/context only.

**Price stores and the survivorship hole:**
- `data/yahoo/` — 690 parquets; dominant SP cohort (229 names) starts 2023-07-03 (753 bars). `close` is dividend-adjusted total return (verified).
- `data/stocks/` — 224 deep-history parquets (some to 1962), all current survivors. Usable only as caveat-stamped mega-cap diagnostic.
- Massive whole-market store — 19,133 tickers, survivorship-correct *per day*, but rolling entitlement anchored 2021-07-06 with a **permanent 1,165-day gap (2021-10-25 → 2025-01-02)** that swallows the 2022 bear.
- **Dead-name prices effectively don't exist:** `data/edgar/dead_name_prices.parquet` absent; coverage 15/1,083 dead names (1.39%). `grading.py` already implements the full dead-name architecture (resolve_series, terminal_state) — only the price file is missing. PIT index membership DOES exist back to 1996 (`data/breadth/sp1500_pit_membership.parquet`, 2,589 tickers, 1,780 exits).
- Consequence: the only survivorship-correct cohorts are **post-2021-07 Massive at ≤252d** and the **2025-2026 cohort** (delisters captured at terminal price). Pre-2021 long-horizon results overstate returns an estimated 200-500 bps/yr.

**Fundamentals:**
- `data/edgar/fundamentals_panel.parquet` — FY2009-2025, 1,331 tickers, PIT via `period_end + 120d` lag (`collectors/edgar.py as_of_cross_section()`). Conservative proxy, not true filing date; restatements invisible.
- `data/edgar/statements.parquet` — FY2015-2027, 1,334 tickers. Has op_income, capex, interest_exp, gross_profit, revenue, debt, cash, shares. **Missing: depreciation, SBC, R&D** (never added to `edgar_facts.py` FLOW dict). Known consequence: `net_debt_to_ebitda` returns None for nearly all names — a live bug.
- ROIC is computed **nowhere** in the codebase. All inputs for a proxy exist in statements.parquet.
- The LIVE dashboard fundamentals path uses latest-FY snapshot with **no PIT awareness**; only backtest asof-mode uses the PIT panel.
- `ic_scorecard.json` (survivorship_biased=True): quality mean_ic=0.0042, SUE=0.0006, composite **anti-predictive** (-0.0072). Only payout survives FDR. Our measured fundamental-quality edge is ~zero.

**Infrastructure:**
- `engine/grading.py forward_metrics()` is horizon-agnostic — extending to (126, 252, 504) is a call-site change. `scripts/research/entry_strata_phase0.py` is the harness template. SPINE_HORIZONS today max out at 126d; no 252d+ column exists anywhere (verified exhaustively) — these labels are genuinely net-new.
- Off-render pattern: `factor_ops.yml` workflow_dispatch on the self-hosted runner; **never pushes to main**; data rides the next ENGINE job's git add (nightly-sole-advancer law).
- `engine/species_registry.py` enforces `horizon_class ∈ {rotational, positional}` with version-bump-on-change — the exact firewall precedent, missing a hold class.
- `engine/falsifier_tripwires.py` already extended with per-ticker scope/results (NW quant-synthesis item C) — the moat-falsifier host.
- `engine/neuralweb/metabolism.py` hard-wires `fdr_family='cortex'`; qledger claims default to desk families. **A dedicated `fdr_family='long_hold'` must be carved** or long-horizon claims silently contaminate entry FDR batches.
- committee.html is vertical `.panel.section-lazy` blocks (not tabs), built inline in `scripts/build_site.py:3497-3527`. BC-2 'validated' gate scans templates/ + site/ — it WOULD scan a new panel. `config/synapse.yml` + `config/dag.yml` registration are hard CI gates for any new artifact/builder.
- Paid-data blocked under SKIP-ALL (2026-07-05): earnings-call transcripts, consensus revenue-revision direction, per-analyst accuracy, supply-chain data. The existing analyst-revision block is recommendation-COUNT delta, not revenue revisions (and its Finnhub feed is production-machine-only).

---

## 3. Rulings (LH-R1 … LH-R10)

- **LH-R1 (horizon firewall, mechanical).** `config/synapse.yml` gains a `horizon_role` field (`tactical_entry | hold_thesis | dual | context`); every registered artifact is stamped; `check_synapse_reads.py` is extended to hard-fail any hold_thesis artifact consumed by an entry Article-2 surface (board ordering / top setups / alert triage / push floor) and any tactical_entry artifact consumed by a hold surface. The species `horizon_class` enum gains a hold value when the first hold species registers. The firewall is bidirectional and CI-enforced, not documentary.
- **LH-R2 (no fused admission).** No single verdict may combine entry state + fundamentals + ownership + expectation drift. Admission to thesis tracking is a transparent AND-gate of independently registered display flags, registered as a species (S15+) through the existing PREREG ladder. Any future composite must beat equal-weight sector-neutral z-mean OOS (composite_score.py law) before display, and clear Article 2 before behavioral use.
- **LH-R3 (survivorship stamps).** Every long-horizon artifact carries `survivorship_biased` + dead-name `coverage_frac` fields (ic_scorecard precedent). 756d results are **refused as headline numbers** until a dead-name price store exists. Honest cohorts for outcome claims: post-2021-07 Massive ≤252d; 2025-2026 cohort. Survivor-only results ship stamped "UPPER BOUND".
- **LH-R4 (effective-n discipline).** Raw fire counts are banned as inferential n. Every statistic carries cluster-robust / block-bootstrap CIs on (name × macro-regime) blocks; per-horizon minimum floor: **n ≥ 25 independent episode-clusters** (matches Article-3). Overlapping-window autocorrelation must be handled by episode-blocking, not ignored.
- **LH-R5 (FDR isolation).** All long-hold claims register under dedicated `fdr_family='long_hold'` with its own quarterly batch. A test asserts no long_hold key appears in any entry desk's FDR grouping.
- **LH-R6 (LLM law application).** Thesis status transitions (watch → active → challenged → falsified) are fired ONLY by deterministic falsifier tripwires; the transition write is an append-only governance event. LLM output is provenance-stamped commentary bound to the machine event id — never the transition itself, never a hold/trim verdict. "Reason to hold" framing is dead; the ledger records evidence that would BREAK a thesis.
- **LH-R7 (ledger law application).** The thesis ledger and long-horizon label store are forward ledgers → nightly is sole advancer. The quarterly review scheduler is a workflow_dispatch that writes runner-local and rides the next ENGINE git-add; a workflow-lint check asserts no `git push` in it. The live qledger's GRADE_HORIZONS are untouched.
- **LH-R8 (kernel clock).** No long-hold feature conditions on kernel estimates before the 2026-10-01 decision batch (Signal Commons R1).
- **LH-R9 (paid-data respect).** No wave depends on transcripts, consensus revenue revisions, per-analyst accuracy, or supply-chain feeds. Features needing them are listed in §5 as deferred behind the re-buy trigger, not silently assumed.
- **LH-R10 (species coordination).** Expectation-drift / bad-news-resilience work coordinates with already-registered species S9 (post-event absorption) rather than duplicating it. The great-company-trap detector is not new alpha — it is a de-escalation overlay assembled from existing signals (crowding, insider, revisions), display-only, may only lower conviction.

---

## 4. Wave plan

### W0 — Horizon Charter + firewall (ships unconditionally; no gate)
The discipline tier. Immediate relief for the entry/hold confusion.
1. **PR-B: `research/long_hold/OBJECTIVE.md`** — the pre-registration. Locks: objective tiers (§1), label definitions (compounder / multiple_expansion_only / cheap_trap / tactical_only / missed_hold), horizon set (126/252 primary; 504 caveated; 756 refused), honest cohorts, fdr_family='long_hold', episode-cluster n-floors, temporal split (fit ≤2019 / OOS 2020-2023 on the baskets tape), within-regime label-reshuffle null, and the W1 kill criterion — all BEFORE any label is computed.
2. **PR-C: horizon_role in synapse.yml** — schema addition + stamp all ~101 registered artifacts (census pass per artifact; anything ambiguous stamps `context` and is queued for review).
3. **PR-D: firewall CI gate** — extend `check_synapse_reads.py` per LH-R1, with tests; assert entry harnesses (`entry_strata_phase0.py`, keystone) never read `data/research/long_hold_*`.

### W1 — Missed-Hold Kill-Test (gate: pre-registered; decides the program)
1. **PR-E: label harness** — entry_strata-pattern script `scripts/research/long_hold_label_panel.py`, off-render (factor_ops pattern), horizons (126, 252, 504) + max-DD + time-underwater + sector-relative, over `gate_fires_baskets.parquet`; per-cohort survivorship stamps per LH-R3; output `data/research/long_hold_labels.parquet` (synapse-registered).
2. **PR-F: the study** — at-entry features (EXISTING fields only: Piotroski F, quality/profitability z, SUE, insider CMP, leverage, dilution, gross-margin trend, archetype) tested for missed-hold vs fader separation under BH-FDR across the family, name×regime clustering, temporal split, reshuffle null. Verdict doc printed either way.
3. **PR-G: dead-name spike** — investigate whether ThetaData (history since 2012-06) or Polygon flatfiles can populate `dead_name_prices.parquet` for the 1,083-name dead universe. The `grading.py` machinery already exists; this is a data-acquisition feasibility memo, not a build.

**G1 kill criterion (pre-registered in W0):** if no at-entry feature family survives FDR on the honest cohorts, the selection-alpha thesis is KILLED; W3/W4 are cancelled; the program collapses to W0 discipline + W2 clocks/falsifiers. A null is examined for survivorship mechanics before ratification (missing dead names understate the trap class), then printed loudly.

### W2 — Hold-maintenance tooling (duration tier; W2 clocks/falsifiers proceed regardless of G1; W2 feature-columns require W1 evidence review)
1. **PR-H: EDGAR FLOW additions** — depreciation, SBC, R&D added to `edgar_facts.py`; fixes the `net_debt_to_ebitda` None bug; unblocks EBITDA and capital-allocation features.
2. **PR-I: compounder feature columns** — additive to existing panels (~20 lines in `_multiyear()`): ROIC proxy series (documented tax assumption) + 5y median/stability, gross_margin_5y_stability, FCF conversion, reinvestment_rate (capex/CFO), incremental revenue per reinvestment dollar, asset_light_scaling. Display-only; PIT via fundamentals_panel on BOTH display and backtest paths; per-feature coverage stamps.
3. **PR-J: two clocks** — `entry_clock` (days since tactical signal, half-life from existing staleness work) and `thesis_clock` (days since last fundamental confirmation) as display fields on existing per-stock panels.
4. **PR-K: moat falsifier sensors** — extension of `falsifier_tripwires.py`: each falsifier a single measurable series (margin-compression-despite-revenue-growth, receivables-stretch, churn-proxy deterioration…) with a pre-registered matched-control base rate (falsifiers fire constantly in normal cyclicals; a falsifier is informative only vs controls). Plus the great-company-trap de-escalation overlay per LH-R10.

**G2 gate:** compounder features must improve missed-hold separation OOS vs the W1 existing-field baseline to justify W3.

### W3 — Thesis ledger + species (only if G1 non-null AND G2 passes)
1. **PR-L: species S15+ prereg** — admission categories as AND-gate flags through the species ladder; horizon_class hold value added.
2. **PR-M: thesis ledger** — `data/neuralweb/long_thesis_registry.jsonl` + reviews.jsonl per LH-R6/R7; quarterly review dispatchable; synapse+dag registered.
3. **PR-N: market-implied growth card v1** — EV/sales-only implied revenue CAGR (mkt_cap + net_debt + revenue all exist for ~785 covered names) against a conservative fixed terminal-margin template per deterministic business-model class (GICS + financial-shape heuristics — no LLM classification, no 12-class hand taxonomy). Output is a "what must be true" display block. Everything needing EBIT/EBITDA multiples or consensus stays deferred.

### W4 — Committee surface (only after W3 operates one clean quarter)
1. **PR-O:** new `.panel.section-lazy` Long-Thesis section in `committee.html.j2` + JSON copy in build_site.py + loader in the page IIFE; role-context chips reused; display-only language (BC-2-safe: no 'validated'); i18n via data-tip-en/zh.

---

## 5. Cut and deferred

**Cut (do not build under any wave):** theme-cashflow-transmission per-ticker graph (§5.9); universe-scale KPI registry (§5.8); hold-book risk/overlap view (§6.6); live-qledger multi-year extension; reverse-DCF beyond the EV/sales v1 card; any fused admission or "moat score" composite.

**Deferred behind the paid-data re-buy trigger:** earnings-call transcript KPI extraction; consensus revenue-revision direction; per-analyst accuracy; segment fundamentals; supply-chain entity graph. Highest-value theme if re-bought remains **expectation drift** (study §9 priority map adopted as-is).

**Deferred behind the dead-name spike (W1 PR-G):** any 504/756d headline base rate; pre-2021 cohort studies; survivorship-honest cheap-trap rates.

---

## 6. Assessment provenance

- Census lanes (Sonnet ×6): fundamentals-stack, masterplan-constraints, outcome-infra, data-depth-survivorship, ownership-options-theme, site-committee-gov.
- Adversarial reviews (Opus ×4): statistical validity, house-law conformance, build feasibility/sequencing, alpha realism.
- Unanimous panel findings ratified by Fable: fused-admission kill; 756d kill; W1 promotion of missed-hold study; kernel-timescale kill; objective reframe to discipline/duration/alpha-option.
- Notable census discoveries beyond the study: `net_debt_to_ebitda` None bug (depreciation never collected); dead-name architecture already coded in grading.py (only data missing); species horizon_class as firewall precedent; metabolism fdr_family hard-wired to 'cortex' (isolation required).

## 7. Status log

- 2026-07-05 — Program chartered. Source study committed as-received. W0 build authorized (PR-B/C/D). W1 authorized to begin after W0 merges; G1 kill criterion locked in OBJECTIVE.md before any label computation.
- 2026-07-06 — W0 SHIPPED (#1508 prereg, #1510 horizon_role stamps, #1514 firewall gate). W1 SHIPPED (#1517 label panel, #1519 dead-name spike, #1520 Amendment A1, #1528 dead-name Phase-1 build + gap-crossing fix, #1540 kill-test). **G1 RULED: DEFERRED** (window-driven n-floor failure: 4 honest compounder clusters vs ≥25; piotroski_f separation consistent but survivorship-caveated in every floor-met split). W3/W4 LOCKED. W2 authorized display-only; PR-H EDGAR FLOW additions now retest-critical. G1-RETEST (Amendment A2, 2025+ honest cohort) projected evaluable ~2027-H2. Full ruling: research/long_hold/W1_KILLTEST_RESULTS.md §12.
