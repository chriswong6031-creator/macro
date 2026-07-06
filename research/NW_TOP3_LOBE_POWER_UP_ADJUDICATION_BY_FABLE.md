# Neural Web Top-3 Lobe Power-Up — Fable Adjudication & Build Program

**Date:** 2026-07-06
**Author:** Fable (main loop), adjudicating `research/NW_TOP3_LOBE_POWER_UP_ANALYSIS_BY_CODEX.md`
**Method:** 7-lane Sonnet census (every quantitative claim + every proposal swept against artifacts, registries, rulings, git history) → 5-lens Opus adversarial review (frame, per-lobe statistics/feasibility, gap-hunt) → Fable adjudication. ~1.1M subagent tokens, 382 tool calls. Corrections printed per house law.
**Status:** RATIFIED. §8 is the build authority for the same-day waves; §7 is the standing phased plan per lobe.

---

## 0. Verdict on the Codex paper

The paper's instincts are good and its frame is publishable: the six-link chain (objective → observation → label → counterfactual → calibration → authority) is a sound scaffold, "promote from surfaces to ledgers" is the right principle, and the three-lobe selection (Oracle / Entry / Long-Hold) is a defensible reading of "most built-out." Its best sentence — *"Without the ledger, the lobe is a dashboard. With the ledger, it becomes trainable."* — is house doctrine.

But the paper fails adjudication as a build docket, for one disqualifying reason with three faces:

1. **It is rail-blind and stale-by-a-day.** It cites none of the NW rails program that shipped on its own date (R1 rule-replay rail + governor, EXIT-GRID-1 regret ledger, R2 grader-closure audit, L4 operator-action instrumentation, vintage stamps, dispersion lens). Grep-verified: zero references. As a result it re-proposes shipped machinery as novel builds.
2. **It is census-free.** Of its 15 proposals, **6 are already built** (O2, O4, E1, E3, L2 — and O1 was built AND adjudicated as a printed NULL twice), **2 are hard-locked** by standing rulings (L3, L5 behind the W3 lock), and **1 re-opens a printed null + a DON'T-TEST ruling** (O3). Executing this docket as written would have burned weeks rebuilding closed work and would have violated the A2 contact-freeze.
3. **It is clock-blind.** It ranks builds by engineering multiplier (feature mart first) and never by **time-to-evidence**. Under the sole-advancer law, forward-ledger calendar time is the binding resource: every night a ledger-opener is not shipped is irrecoverable evidence lost, while model-training can run any day. The correct ordering is clock-first.

The genuinely novel, legal, buildable-now residue of the paper is small and valuable — roughly: the sentinel baseline gap (O5, misdiagnosed but real), the funnel longitudinal store (L4), the per-fire S(f) benchmark (inside L1), and the rs_repair/sponsorship observation fields (inside E4). §8 builds all of it, plus four higher-leverage moves the paper missed (§6).

## 1. Corrections ledger (factual errors in the paper, printed per house law)

| # | Paper claim | Ground truth (verified against artifacts) |
|---|---|---|
| C1 | `oracle_state.json`: "quiet as of 2026-07-06, 0 active episodes, 0 onset watchlist" | asof=2026-07-01; **173 active episodes**; onset_watchlist=`[XLC, XLY]`; regime tag = **rotation** (4 sources / 3 sinks). The paper read absent keys and reported the misses as zeros. |
| C2 | `oracle_alerts.jsonl`: 108 alert rows | **1 row**. (alerts_state.json has 174 state keys — a dict, not an alert count.) |
| C3 | `oracle_reversion_state.json`: 11 display reversion signals | **n_signals=0, signals=[]** (asof 2026-07-06). |
| C4 | us_standouts: "55 list rows", "liquidity fields on 8 of 55" | 60 rows (24 buy + 24 watch + 12 laggards); **zero** rows carry liquidity fields. Lane counts 12/7/24 are real but live in `antichase_shadow_ledger.parquet`, not the standout JSON. |
| C5 | `data/oracle/sentinel_log.jsonl` / `operator_tape.jsonl` cited as live data-plane artifacts | Both are git-tracked and real, but the sentinel warning's root cause is misdiagnosed: **`data/oracle/gauntlet/p3_results.json` was never committed** (only p3_trial_ledger.json + p3b_routing_placebo.json exist). The decay monitor for the program's only two onset edges is inert because its baseline artifact does not exist — a data-publication gap, not a missing "truth-maintenance lobe." |
| C6 | `data/oracle/reversion_forward/<id>.jsonl` implied populated | Directory absent on origin/main; registry has 0 reversion blocks materialized. The ledger script is built and wired (`oracle_nightly.py` step); accrual has **not yet materialized** — an ops follow-up (§8 W-OPS), not a build. |
| C7 | "38.1% false-start but 99.7% onset→confirmed" presented without reconciliation | Both correct, measuring different things: false-start = direction-adjusted +5d price adversity; onset→confirmed = the state machine's structural advancement. The near-degenerate 99.7% means **p_confirm is an untrainable target** (see O1 ruling). |
| C8 | 25,783 episodes (implied verdict-grade) | 25,783 = episodes across ALL 57,640 fires; verdict-grade-only = 22,295. |
| C9 | rs_repair_state and sponsorship_state "both unavailable" (implied same defect) | Different defects: rs_repair_state is a **declared stub** (EI #1302 W0.4 never shipped); sponsorship_state is **implemented but starved** (its `panel_s.parquet` lookup resolves for 0/1,722 tickers). The fix paths are entirely different (§8 PR-B3). |
| C10 | L1 framing: dead-name repair → "more honest OOS missed_hold clusters" | **False premise.** G1's deferral is WINDOW-driven (3.5-month honest window → 4 clusters vs ≥25 floor); all 140 dead names in that window already have full Polygon coverage. No data repair moves the G1 clock — only calendar accrual to ~2027-H2. Also: 665 of 1,083 dead names are outside the Polygon entitlement entirely (pre-2021 rolling window); "dead-name price histories" for 2014-2021 is not obtainable clean. |

Codex's core numbers that DID verify: synapse counts (23 oracle / 20 long-hold artifacts, tiers, firewall text), replay substrate (961,656 / 57,640 / 49,939 / 62.8-33.1-4.0%), long-hold label counts (113,542 fires, 195 compounders, all label cells exact), G1 DEFERRED + ~2027-H2, funnel states (1,503 = 1,002/255/246), Ruler-P results (sue_streak only pass; insider all NULL), P1.3/P2.5 verdict characterizations, P1.4 recall (0.24% of durable lows).

## 2. Per-proposal rulings — Oracle

| ID | Ruling | Reason (one line each; full evidence in census/critique record) |
|---|---|---|
| **O1** onset-quality calibrator | **KILL — duplicate of an adjudicated NULL** | `scripts/oracle_onset_quality_w1.py` (1,713 lines) IS this proposal; run twice (W1 pos63, W1b reversion21): LOEO AUC 0.4887/0.4836, shuffled-null p≈0.7, Fable-countersigned "NOTHING SHIPS." p_confirm head is degenerate (99.7%). No re-run without a new pre-registered spec + population-expansion argument (standing W1 ruling). The stratified base-rate table Codex wants already exists (`memory_base_rates.json`). |
| **O2** flow-routing tensor | **KILL — already built + illegal as specified** | `engine/oracle/graph.py` ships the lead-lag tensor + flow-routing matrix; P3b placebo adjudicated 6/90 surviving cells (display-with-edge, watermark-capped). The open-tensor extension is an ~840-1,650-cell FDR explosion on a zero-sum rs identity, and "money routing" is unidentifiable from price-implied rotation (naming-fraud risk under truth-in-labeling). The real gap is live route-cell forward accrual — an ops/data question folded into W-OPS. |
| **O3** member-phase intelligence | **KILL as independent build; the thread is already scheduled** | Its testable premise (member dispersion/leader-laggard predicts forward member outcomes) is the construction_divergence family: R-1 printed a NULL, R-4 is DON'T-TEST (rs zero-sum tautology). Member cohorts can't be built PIT (holdings are latest-only; R-2b dormant to ~2027-07). The one live positive — W2 member-transmission (#1533, WR21 65% vs 54%, display-only) — already has R-3 washout-strata continuation scheduled at ~Q4-2026 effective-n. Extend that; build nothing new now. |
| **O4** reversion sequential evidence engine | **KILL — near-verbatim duplicate of the shipped, frozen design** | `ORACLE_REVERSION_PROMOTION_TRACK_DESIGN.md` + PREREG (frozen L2→L4 Wilson gates: lift_lb>1.25 & n≥25; n≥60 & asym≥1.3; 90-session lapse) + `oracle_reversion_forward_ledger.py` (wired) + promotion_scan (never auto-promotes) = the whole proposal. Codex's headline "cluster de-dup" contribution is verbatim the PREREG's open ruling, deferred to P3 adjudication when live n exists. Changing frozen thresholds now = p-hacking by the prereg's own text. |
| **O5** truth maintenance | **AMEND → two concrete fixes (BUILD NOW)** | The truth-maintenance *job* already runs (sentinels.py step 13 + hypothesis_inbox SENTINEL_MIRROR step 14). The real defect our census found: the two onset edges' decay baselines were **never published** (`p3_results.json` never committed) → monitor permanently inert. Fix = publish the adjudicated baselines + a conformance test that every `_DISPLAY_WITH_EDGE_COMPOUNDS` member resolves to a published stat (so this class of blindness becomes CI-impossible). Taxonomy note: this is a **rail** fix, not a lobe build — the paper's own §Executive Ruling misfiles it. → §8 PR-A1. |

## 3. Per-proposal rulings — Entry

| ID | Ruling | Reason |
|---|---|---|
| **E1** replay feature mart | **AMEND → R1-rail enrichment, queued (Phase E-Next)** | The mart exists (`replay_boarded.parquet`, PIT-audited, golden-tested). A parallel mart would duplicate the R1 rail and evade its anti-fishing governor. The legal residue: PIT as-of enrichment joins of the 2026-era stores (bottom_sensors, anti-chase ledger, kernel-rank cells) with **per-feature first_available_date / coverage-by-year stamps** (era-leakage guard), Mac-local, off-render, `fdr_family='replay'`. Drop "never_triggered durable lows" as a labeled row type (hindsight label + dead-name coverage 1.4%). |
| **E2** recall-first near-miss learner | **KILL** | Label is hindsight-defined (not PIT-legal); P1.4 already measured the population (never-triggered 7.8-8.9%, ALL horizon-censored — unresolved truth); at a ~0.2% base rate the "fixed board expansion" gate is vacuous; and it pushes against the F3 anti-chase HARD GATE verdict. P1.4 stays the standing quarterly census; no learner. |
| **E3** outcome posterior / kernel-rank v2 | **NO BUILD — already shipped and accruing; let the clock run** | `kernel_rank_shadow` merged #1473: 94 shrunk cells, Wilson bounds, registered 300-episode-cluster flip floor, evaluations ≥2026-Q4. Extensions (species/lane axes) are legal only via a new PREREG (P3.1 cell-rollups is the sanctioned path) and stay display/shadow behind Signal Commons R1 until the kernel-FDR clock (2026-10). Adding axes now multiplies 22k cells over 22k independent episodes — the shrunk posterior becomes the global base rate wearing cell labels. |
| **E4** bottom_sensors v2 | **SPLIT → diagnose + build the buildable half (BUILD NOW)** | (a) sponsorship_state: implemented but starved — diagnose the panel_s ticker-mapping gap and fix the wiring (RUL-16/B2 lane already carries a ratified trial budget). (b) rs_repair_state: stub pending EI W0.4; S7 phase0 (PASS dev/holdout) provides frozen definitions; build the W0.4 series and bind read-only per RUL-15 — if the spec turns out thin, report back for prereg rather than inventing thresholds. (c) insider/ownership sponsorship buckets: **vapor** (insider = measured NULL; no PIT ownership panel exists) — printed as explicit null-substrate, deferred. → §8 PR-B3. |
| **E5** lifecycle/hazard model | **KILL** | A competing-risks hazard over {liftoff, stop, dead_money, cushion} is E3's posterior evaluated per-horizon — one model wearing two names, doubling trials against the same tape. "Re-arm after base" re-opens W-ARM, which FAILED promotion ("clean15 gate fail deep") — rebuilding it unreferenced is laundering. Per-bar paths exist nowhere pre-computed; a true survival object is off-render heavy compute with no budget line. Any lifecycle variant enters later as a state-conditional arm of the SAME entry_stack family. |

## 4. Per-proposal rulings — Long-Hold

| ID | Ruling | Reason |
|---|---|---|
| **L1** substrate repair | **RESCOPE → execute A2 §3 retest-prep items (BUILD NOW, clock-honest)** | LT-1a/b/c + dead-name Phase-1 already shipped (#1592/#1619/#1633/#1528). The real residuals are already-registered A2 §3 items: the **A1-to-spec per-fire S(f) benchmark** (the winner-selected cohort-mean is the documented artifact that inflated compounders 4→132) and the committed dead-name **coverage probe script** with era-stratified measured coverage. State plainly: none of this moves the G1 clock (window-bound, ~2027-H2); pre-2012 dead names are stamped UNREACHABLE. → §8 PR-B1. |
| **L2** multi-family FDR battery | **KILL as duplicate; salvage one artifact (BUILD NOW)** | LH-R11 (program-wide HLZ/BH q=0.10 as sole ratifying correction) + A2 roster (F1 m=9, F2 m=10, F3 m=7, F4 m=3, Σ=29 ≤ 40) are already ratified — L2 restates them. Running the battery now would VIOLATE the A2 §4 contact-freeze. The one missing, high-leverage artifact: **the A2 OOS-analysis script itself** — LH-R11.1 makes its commit the roster freeze anchor. Author it now with a hard no-run-until-floor gate; committing it locks the roster years before outcome contact. → §8 PR-B2. |
| **L3** thesis-transition ledger | **DEFER — W3-locked; design amendments recorded** | The design is already law (LH-R6 deterministic tripwires only / LH-R7 nightly sole advancer / W3 PR-M) and W3 is LOCKED until G1 non-null. Recorded for the unlock: (a) every tripwire threshold pre-registered outcome-blind — expectation/insider tripwires INADMISSIBLE until then; (b) PIT-strict firing — override `moat_falsifiers`' keep-on-NaT fail-open for ledger use (period_end+120d ≤ transition_date or no fire, exclusions logged); (c) firewall assertion: `scored_path_surfaces=[]`, no confidence numbers on transition stamps. |
| **L4** funnel longitudinal memory | **AMEND → BUILD NOW (clock-opener)** | LT-4's own report flags exactly this gap ("no longitudinal store yet… wire an append/archive hook into nightly first"). Every night not appended is a permanently lost cross-section. Gates added: nightly-only writes (sole advancer; on-demand runs never persist to the store), append-only keyed (ticker, snapshot_date), LT-1/period_end coverage deltas printed next to any >5pp drift (coverage-artifact confounder), survivorship caveat stamped (delisted names exit the panel). Historical state-at-fire must NOT be joined to 2024+ outcomes before the A2 freeze. → §8 PR-A2. |
| **L5** analogue explainer | **DEFER to post-G1 (~2027-H2); as written it is illegal** | "Confidence capped by label rarity" is a model-authored confidence number — the exact D-7 killed pattern (Wilson bounds from graded history or no number). Nearest-neighbor on 195 survivor-tinted positives makes the distance metric an un-gauntleted model choice; an analogue card naming famous compounders is behaviorally potent anchoring for an operator who trades conviction on low-n theses. If any pre-G1 work happens it is a research-tier frozen-metric prereg, deterministic retrieval, no display surface. |

## 5. Cross-lobe moves — rulings

Codex's five cross-lobe "power moves" are mostly slogans (no artifact, no gate, no tier). Dispositions: #1 (Oracle context-not-gate) — correct, already law; cite China falsification. #2 (Entry→Long-Hold handoff) — already the CI-enforced LH-R1 firewall; cite, don't restate. #3 (member-phase bridge) — carries the O3 rulings; no artifact until R-3/R-2b clear. #4 (train on missed decisions) — correct instinct, wrong price: the cheap version is M4 below, not new learners. #5 (surfaces→ledgers) — STRIKE as aspiration; it shipped as the R2 grader-closure audit (#1556: 7 CLOSED / 3 LOG-ONLY / 16 GRADER-STARVED). **Each lobe's real ledger to-do list is its GRADER-STARVED rows.**

## 6. What Codex missed (adopted moves)

- **M1 — Clock-first ordering (ADOPTED as the program's ordering principle).** Rank every build by days-of-evidence-per-day-deferred. Ledger-openers ship first (L4 funnel history, M4 operator outcomes); model-training runs whenever. A ledger only counts if its gate + family are pre-registered at ship time.
- **M2 — Cross-lobe contradiction pair (BUILD NOW).** Extend `engine/neuralweb/contradictions.py` with pair-g: Oracle complex out-rotation vs an Entry buy-lane member inside that complex. Severity capped at 'tension', annotation-only, NO winner field — a resolving output would be a hard gate in disguise requiring a full gauntlet. → §8 PR-A4.
- **M4 — Operator-tape outcome resolution (BUILD NOW; the cheapest counterfactual engine in the docket).** `operator_tape.jsonl` already captures PIT decisions + conviction + invalidation but has **no outcome field**. Add nightly-resolved `system_state_at_stamp`, `realized_outcome` (deterministic price/ledger join at the stated invalidation/horizon — never LLM-authored), `override_flag`; emit a display-only operator-vs-system scorecard. This produces the counterfactual labels Codex wanted from new learners, at the cost of a join. Sparse-n: it is a ledger for calibration, not a training set. → §8 PR-A3.
- **M5 — Converge calibration on `grading_stats.py` (BUILD NOW, small).** Three helpers every future consumer needs: `reliability_curve`/`brier_decomposition`, `era_split_stability`, `eb_shrink` — with loud docstrings that long-horizon/overlapping rows must use the block-bootstrap primitives. Prevents the three-bespoke-calibrator drift the paper would have caused. → §8 PR-B4.
- **M3 — regret-context card (QUEUED, Phase E-Next)** — display-only post-fire regret context from EXIT-GRID-1 by species/cohort, leave-one-out, overlap-corrected CI at 126d, zero board-order effect pre-gauntlet.
- **M6 — data adds (PARTIAL)** — FINRA wiring folds into PR-B3's sponsorship diagnosis; dead-name expansion DEFERRED (entitlement-blocked; probe script ships in PR-B1). **M7 — compounder proxy label: KILL** (wrong-ruler; OBJECTIVE §9 "the wall is absolute"; any proxy validates against the same latency-bound 195-label store it claims to bypass).

**Frame upgrades adopted:** links 7-10 added to the six-link chain — (7) capacity/liquidity survival, (8) label/data latency (the binding Long-Hold constraint), (9) operator trust/UX (a signal nobody reads is dead), (10) regime robustness (era-stability as a named link, not a buried gate clause). Taxonomy filing per the Future-Lobes Docket: O5 and E1 are RAIL work; L4/M4 are ledger waves; nothing here charters a new lobe (two-lobe concurrency cap untouched).

## 7. Phased build-out plan per lobe

Ordering principle everywhere: **clock-first** (M1). Every item carries its gate + clock; nothing display-tier may escalate itself.

### 7.1 Oracle / Rotation
- **Phase O-NOW (this session):** PR-A1 baseline publication + sentinel conformance test (unblinds the decay monitor for the only two live edges); PR-A3 operator-tape outcomes; PR-A4 contradiction pair-g. W-OPS: verify reversion_forward materializes on next nightly; verify oracle nightly freshness (asof 2026-07-01 vs staleness contract).
- **Phase O-NEXT (accrual-gated, ~2026-Q4):** R-3 washout-strata on the confirmed W2 member-transmission harness at effective-n ≈ 31 armed windows; reversion promotion P3 adjudication when live matured n crosses the frozen floors (cluster-level authority ruled THERE, ~7 bets not 10); route-cell forward-accrual detector if route cells are to stay published.
- **Phase O-LATER (2027+):** R-2b member-level construction divergence when dated holdings accrue (~2027-07); Tier-M watermark expansion as survivorship-clean coverage grows. No onset-quality model re-run without a new population argument (W1 ruling stands).

### 7.2 Entry Intelligence / US Entry Stack
- **Phase E-NOW:** PR-B3 (sponsorship starvation fix + W0.4 rs_repair series bound read-only); PR-B4 shared calibration helpers.
- **Phase E-NEXT (2026-Q3/Q4):** E1-amended replay enrichment (PIT as-of joins + first_available_date stamps, off-render, `fdr_family='replay'`); M3 regret-context display card; kernel-rank flip evaluations at the registered 300-cluster floor (≥2026-Q4); P3.1 cell-rollup PREREG as the sanctioned posterior extension — display/shadow behind Signal Commons R1 until kernel-FDR 2026-10.
- **Phase E-LATER:** lifecycle state-conditional arm inside the entry_stack family only if P3.1 shows conditioning value; recall work stays a P1.4 quarterly census unless a matured, PIT-legal never-triggered population emerges (needs dead-name store that doesn't currently exist).

### 7.3 Long-Hold Thesis
- **Phase L-NOW:** PR-A2 funnel longitudinal store (clock-opener); PR-B1 per-fire S(f) benchmark + dead-name probe script (A2 §3 execution); PR-B2 A2 freeze-anchor script with no-run gate (locks the Σ=29 roster before any outcome contact).
- **Phase L-NEXT (come-back 2026-10-01):** funnel drift audit on the new longitudinal store (>5pp gate with coverage-delta print); Ruler-P display work continues within the Σ=29 ceiling; nothing touches the 2024+ cohort.
- **Phase L-LATER (~2027-H2, G1-Retest):** run the frozen A2 analysis script when honest compounder clusters ≥25; on G1 non-null → W3 unlocks → L3 thesis-transition ledger builds under the three recorded amendments (§4); L5 analogue work only post-G1, deterministic-retrieval, D-7-compliant.

## 8. Ratified same-day build docket (waves A/B)

Routing: Sonnet builders in isolated worktrees, Opus reviewers, Fable merges serially (synapse.yml/SIGNAL_BUS.md are shared surfaces — registry-drift discipline applies). All artifacts display/infrastructure tier; no scored-path surfaces; nightly remains sole advancer of every new ledger.

| PR | Scope | Gate |
|---|---|---|
| **PR-0** | This document + the Codex paper committed side-by-side | — |
| **PR-A1** | Publish onset-edge decay baselines (reconstruct `data/oracle/gauntlet/p3_results.json` from the adjudicated P3 stats, code ids not prose names) + pytest: every `_DISPLAY_WITH_EDGE_COMPOUNDS` member resolves in `_load_published_stats` | sentinel run flips ep_in_onset_21d / ep_out_onset_5d from monitor_inert to active; test fails on any future unpublished edge cell |
| **PR-A2** | Thesis-funnel longitudinal store: nightly append-only history keyed (ticker, snapshot_date) + synapse/SIGNAL_BUS/dag registration | nightly-only writes; append-only; coverage-delta printed beside any >5pp drift; survivorship caveat stamped; <30s in engine job else separate narrow-allowlist job (granted here as the required program amendment) |
| **PR-A3** | Operator-tape outcome resolution: nightly deterministic join adding system_state_at_stamp / realized_outcome / override_flag + display-only scorecard artifact | outcome = deterministic price/ledger join only; LLM may never author outcome or confidence; additive-only oracle_nightly END step; append-only |
| **PR-A4** | contradictions.py pair-g (Oracle complex-out vs Entry member buy-lane) | severity ≤ 'tension'; annotation-only; no winner/suppression field; fail-open |
| **PR-B1** | Per-fire S(f) sector benchmark (A1-to-spec) + committed dead-name coverage probe with era-stratified measured coverage | coverage % printed per era; pre-2012 stamped UNREACHABLE; emits NO missed_hold re-scoring (A2 §4 contact-freeze respected) |
| **PR-B2** | A2 OOS-analysis freeze-anchor script (program-wide HLZ/BH machinery per LH-R11.2, provenance + restricted_range stamps) | script REFUSES to run until floor trigger (honest compounder clusters ≥25 + operator flag); tests prove the refusal; commit = roster freeze per LH-R11.1 |
| **PR-B3** | E4 split: diagnose+fix sponsorship_state starvation (panel_s ticker mapping); build EI W0.4 rs_repair series from the S7 frozen definitions and bind rs_repair_state read-only (RUL-15) | display-only; if W0.4 spec is not frozen anywhere, builder STOPS and reports (no invented thresholds); null-substrate buckets (insider/ownership) printed as explicit nulls |
| **PR-B4** | grading_stats.py: reliability_curve / brier_decomposition, era_split_stability, eb_shrink + tests | pure additive plumbing; docstrings mandate block-bootstrap for overlapping long-horizon rows; no consumer behavior changes |

**W-OPS (no PR):** verify reversion_forward/ materializes on next nightly and oracle_state freshness; if not, open a targeted fix.

## 9. Standing rulings from this adjudication

- **RUL-T3-1:** O1/O2/O3/O4/E2/E5/M7 are closed as proposed (duplicate, null, locked, or illegal). Re-opening any of them requires a new prereg that cites and distinguishes the closing evidence above.
- **RUL-T3-2:** Clock-first ordering is the standing prioritization rule for lobe power-up work: ledger-openers with pre-registered gates outrank capability builds.
- **RUL-T3-3:** Truth-maintenance work (sentinels, baselines, schema conformance) is RAIL work under the docket taxonomy and lives with the NW rails program; the PR-A1 conformance test is the permanent guard.
- **RUL-T3-4:** The PR-A2 nightly step is granted as the explicit program amendment RUL-P9 requires, conditional on its benchmark gate.
- **RUL-T3-5:** No new model may publish a confidence number that is not a Wilson/Jeffreys bound from graded history (D-7 restated for this program); all calibration primitives converge on `engine/grading_stats.py`.

## 10. Provenance

- Census lanes (Sonnet ×7): claim verification vs live artifacts + git history (long-hold parquets recovered from commits 948d9aa1fc / c2a171c95c / 90d9c8fc89), redundancy sweeps vs masterplans/amendments/preregs, rails inventory.
- Adversarial lanes (Opus ×5): frame + build-order critique, per-lobe statistical review (episode counts, cell-explosion arithmetic, degenerate targets, PIT legality), gap-hunt (M1-M7).
- Fable: rulings, corrections ledger, phased plans, docket ratification.

---

## 8.1 Outcome log (same-day execution, 2026-07-06)

All docket items shipped or resolved same-day. Fleet: 8 Sonnet builders (isolated worktrees) + 8 Opus reviewers + 5 Sonnet fixers; Fable merged serially against a fast-moving main (4 parallel-session PRs landed mid-program).

| PR | Item | Outcome |
|---|---|---|
| #1684 | PR-0 docs | MERGED |
| #1687 | PR-A1 onset baselines | MERGED (review APPROVE). Root cause was sharper than the docket text: p3_results.json was explicitly gitignored ("regenerate via script") and never committed — the decay monitor for the program's only two live onset edges was blind since P3 shipped. Baselines transcribed with provenance; conformance test now makes unpublished-edge-cell blindness a CI failure. |
| #1691 | PR-A2 funnel longitudinal history | MERGED (review APPROVE + 2 minors fixed: --smoke × --write-history rejected; bool() drift flag). Clock opened: nightly append-only store live. |
| #1692 | PR-A3 operator-tape outcomes | MERGED after FIX round (synapse notes-block corruption repaired; duplicate-pending append fixed — one pending row per tape_id, one final row at maturation; resolver now prefers the write-time system_state_snapshot with system_state_source recorded). Clock opened. |
| #1688 | PR-A4 contradiction pair-g | MERGED (review APPROVE; 3 minors noted for future hygiene: stale 6-pair consumer note, mutable-attribute plumbing, as_of 'unknown' lexicographic edge). |
| #1694 | PR-B1 S(f) benchmark + dead-name probe | MERGED after FIX round (calendar-continuity guard now matches long_hold_label_panel._total_return per LH-W1-3; A2 §4 contact-freeze enforced with fire_date ≤ 2023-12-31 hard filter + exclusion counts printed; sample runs write to _SAMPLE path). Full S(f) run is a Mac-local on-demand job — script shipped, run pending operator window. |
| #1689 | PR-B2 A2 freeze-anchor script | MERGED after FIX round (program_fdr_marginal = within-family-pass AND program-fail per LH-R11.2; roster SHA-256 pinned literally: b52165f8…30bcbc; no-run gate enforced inside the contact function; refusal tests assert specific reasons). **Roster freeze anchor is committed — LH-R11.1 satisfied.** |
| #1690 | PR-B4 grading_stats calibration helpers | MERGED after FIX round (zero-variance era comparison no longer forced 'consistent'; eb_shrink validates k ≤ n; brier length-check ordering). |
| #1697 | PR-B3 bottom_sensors split | **CLOSED — superseded by #1682** (parallel session's PR-C1 R2 panel publish/fetch path; sponsorship_state now live on main: 886 tailwind / 392 neutral / 301 headwind / 143 unavailable). rs_repair_state half honestly BLOCKED per RUL-15: W0.4 cohort-metrics series began accruing 2026-07-04, needs ≥20 trading days (~early Aug 2026) + Fable ratification of the state taxonomy before binding read-only. |

Open ops (W-OPS): verify `data/oracle/reversion_forward/` materializes on the next nightly and oracle_state freshness (asof was 2026-07-01 across the long weekend); rs_repair bind clock ~2026-08.
