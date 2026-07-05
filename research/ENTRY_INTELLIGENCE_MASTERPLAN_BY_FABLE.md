# Entry Intelligence (EI) Masterplan — by Fable

**Program:** Entry Intelligence — upgrade the US Top Standout Stocks signal stack into an institutional-grade entry engine that integrates into Neural Web as a stock-level lobe.
**Status:** ACTIVE. Adjudicated 2026-07-04. Phase 0 dispatched same day.
**Provenance:** ChatGPT external upgrade plan → Opus digest + 5-step plan → Fable reassessment (3 of 5 steps corrected). This document supersedes both prior plans.
**Relationship to other programs:** amends/extends Setup Species #1097 (inherits its constitution wholesale); consumes Neural Web qledger/Article-3 machinery (adapter pattern, no schema migration); Oracle unaffected.
**Orchestrator:** Fable. Subagents: Opus (adjudication/audit), Sonnet (build), Haiku (mechanical sweeps in P1+). No Fable-class subagents.

---

## §0 Charter

The current board's hard entry gate is momentum × momentum (MACD-2D × StochRSI-3D — one evidence family sampled at two timeframes). Everything orthogonal that has been *validated* (cohort washout, RS inflection, anti-chase) is display-only or research-only. The board ranks by a hand-asserted formula. Nothing measures recall. The measurement floor is known-non-institutional (survivorship + breadth).

Target end-state:

1. **One replay-derived evidence base** for every claim about the funnel (fires, near-misses, rejections, gates — all graded).
2. **Orthogonal confirmation** promoted into rank/gate only via production-trigger evidence, through the species ladder.
3. **Rank = ledger posterior** (shrunk cell outcome distributions, Wilson lower bound), not a hand formula.
4. **Coverage measured** (recall audit) as the standing counterweight to precision-stacking.
5. **Board = Neural Web money-path surface**: every funnel decision emits an entity claim; species authority accrues under Article 3; the standout page becomes a rendered view over graded beliefs.

Not more alerts. Better alerts — with the evidence shown.

## §1 Grounding facts (verified 2026-07-04, three-explorer sweep)

- Hard gate: T1–T4 confluence cascade — `engine/signal_gate.py` (gate() L154, is_buyable L84), `engine/confluence_tiers.py` (L128+, FRESH_TICKS=2).
- Rank: bottoming-alignment — `engine/cycles.py` mtf_alignment (L2012–2107); quality = 100×[0.42·weekly + 0.30·t3 + 0.28·daily]×(1−0.45·knife); tiers PRIME/ARMED/APPROACHING. ARMED admits "weekly already risen" — some continuation flow may already enter here (P1.5 settles this).
- Within-aligned ranking: residual alpha (`engine/residual_alpha.py`), sole FDR survivor per anticipation-engine adjudication.
- Display-only today (zero rank power): extension grade (`engine/extension.py`, "never touches score"), COILED bonus chip, HOLD, postcross BASED/ARMED/SHAKEN (`engine/postcross.py` L4), GEX, SUE, news_burst, smartmoney, altdata, demand, confluence_votes k-of-n badge.
- Near-miss/rejection capture LIVE since 2026-07-03: closed taxonomy `engine/grading.py` REJECTION_TAXONOMY (L101–112); `engine/track_record.py` log_near_misses (L979+); store `data/signal_archive/track_record.parquet`.
- Two-board divergence: `setups.json` rank_by=alpha vs `us_standouts.json` rank_by=bottoming-alignment (build_stock_library.py L1798 vs L2032).
- Species registry: `data/species/registry.json` — 17 species (6 validated, 11 phase-0); constitution `research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md`; ladder chip→ledger→graded_bonus→gate_weight; flip criteria on safety-net axes (stop-out / dead-money / cushion), Wilson lower bound, episode-clustered n floors. S10/S11 EDGAR gates CLEARED 2026-07-03.
- Bottom backtest (`research/bottom_signal_backtest/`): cohort washout + RS inflection + anti-chase = 82.1 quality (n=315, 64.1% durable-60D, 32.1% stop-out) — **on a weekly-MACD/2W-StochRSI trigger, NOT the production 2D/3D cascade**. Mechanism evidence, not species validation.
- Neural Web: entity claims dominate qledger (7,538/7,937); claim schema in `engine/qledger.py`; Article 3 grant_authority = n≥25 date clusters + Wilson(z=1.645) lift >1.25 + freshness ≤120d; `board_ordering` is a NAMED money-path surface under Article 2. (NW module paths were read from a worktree checkout; program status says W7a merged — re-verify paths against main at P4 kickoff.)
- Oracle gauntlet P8 shows the live validation bar killing things (washout failed BH q≤0.10 at 21d). The bar stays that sharp here.

## §2 Rulings ledger

| # | Ruling | Rationale |
|---|--------|-----------|
| R1 | **Separability study runs on the PRE-GATE pool** (fires + near-misses + rejections from replay), never on shipped-board survivors alone. | Restriction of range: fields used as gates show zero separability within survivors even when they work. |
| R2 | **Gate P&L computed by historical replay first**, live Appendix-A ledger as confirmation set. | Gates are deterministic price functions; live accrual to n≥25 clusters takes months. |
| R3 | **Trio promotion BLOCKED until re-ablation on production-trigger fires** (P1.3). Backtest evidence from a different trigger transfers as hypothesis, not validation. | Trigger mismatch. Promoting on foreign-trigger evidence = laundering — the sin the species constitution exists to prevent. |
| R4 | **No pre-commitment to gate-ification.** Each trio member tested as hard gate AND as rank weight; safety-net-axis deltas decide. | CN-REVERSAL law: gates kill edges; China subsector gate falsified. Precedent favors weights/bonuses. |
| R5 | **Species↔qledger integration is an ADAPTER, not a migration.** Species ledger stays source of truth; emits conformant entity claims. | qledger grade schema is poorer than species axes (terminal-state partition, MAE/MFE, episode clustering); W7b schema churn live. |
| R6 | **Kernel-rank ships shadow-first** with a pre-registered flip criterion (shadow forward ledger beats incumbent at episode-clustered n floor). | Rank change = money-path change → Article 2 shadow period. |
| R7 | **Additive-lanes law:** confirmation stacking labels quality UP (A+ lanes); it never filters the board toward zero rows. Recall audit (P1.4) is the standing counterweight. | Fire-rate protection; institutional pattern is label quality, don't hide candidates. |
| R8 | **PREREGs are DRAFT until Fable approval. No P1 study executes before replay golden test + PIT audit are clean.** Subagent PRs merge only after Fable review; the replay harness additionally gates on the Opus PIT audit. | The replay is load-bearing for five studies; a lookahead bug poisons everything downstream. |
| R9 | Replay outputs live in `data/replay/` (canonical checkout), never committed to git (R2-eligible later). | r2-data-plane law. |
| R10 | P0.3 liquidity fields are hygiene/display only — no rank power, ever, without their own PREREG. | Hygiene ≠ alpha. |

Kill list (standing, from ChatGPT-plan adjudication): hand-asserted weights; 12-sector × 8-class backtest matrix; options-flow layer (parked; ThetaData program at STOP); overhead-supply/volume-profile (parked behind trio); macro as separate score (it is a conditioning axis — regime cells — not evidence); redundant momentum oscillators.

## §3 Inherited law

- **Species constitution** (SETUP_SPECIES_MASTERPLAN §1) applies to every EI study: PREREG before run; capped config grids; any post-hoc variation = new recorded trial; BH q≤0.10 per study family; both-halves sign stability; episode-clustered n floors; fills strictly-after signal bar (never same-bar); survivor-bias stamps where delisted coverage absent; verdicts on safety-net axes at declared horizon class.
- **Neural Web Articles 2–3** apply to anything touching board_ordering: shadow-with-track-record before money-path influence; Wilson-gated authority grants; governance ledger entries.
- **Plain-language law**: every shipped surface carries an "In plain English" rendering of its evidence.

## §4 Phase 0 — Measurement floor + replay foundation

### P0.1 Production replay harness (Sonnet build → Opus PIT audit → Fable merge)

**Deliverable:** `scripts/replay_standout_pipeline.py` + `data/replay/standout_replay.parquet` (+ per-year part files) + summary stats.

Design contract:
- Replays the **actual production code path** per (ticker, date): signal_gate → confluence cascade → mtf_alignment → entry_z → cycle-block → extension/knife → sector-cap context. No reimplementation of indicator logic — import and call the production functions on point-in-time slices.
- **Candidate prefilter** for tractability: a vectorized cross-detector marks (ticker, date) pairs with any relevant cross within trailing ~10 bars; full cascade evaluated only on candidates. **Prefilter soundness check (positive control):** on a random sample of non-candidate pairs (≥500), the production gate must return non-fire for all; any fire = prefilter bug, halt.
- Logs EVERY verdict per candidate: fire (tier, sub, weight), near-miss (reason), rejection (taxonomy reason), plus frozen study features at signal time: ext_z, ext_atr, knife_z, alignment tier + quality, weekly phase, 200DMA side, RS-vs-sector quartile, sector, distance-to-52wh, ADV$ 21d, cohort-washout proximity where computable.
- **Grading:** every logged row graded under species law — terminal-state partition (stopped / dead-money / cushioned / clean-liftoff), MAE/MFE, horizons 5/10/21/63/126d, entry = first close strictly after signal date, episode-cluster ids attached.
- **Windows:** primary 2012→present first pass (compute-bounded), then extend backward in per-year chunks toward 2002 as panel depth allows; per-name coverage stamped; pre-2015 rows carry survivor-bias stamp until P0.2 says otherwise.
- **Golden test (hard gate):** for the latest date in the price store, run the production gate directly per ticker and diff against the replay's logged verdicts for that date — must match ticker-by-ticker exactly. Secondary soft sanity: compare against committed `site/factordata/us_standouts.json` (drift allowed only with explanation, since the store rolls forward).
- Chunked + resumable execution (per-year parts); long runs in background with progress logs.

**Done-criteria:** golden test passes; prefilter soundness sample clean; summary printed (fires/year by tier, near-miss counts by reason, verdict row counts); PR open (NOT merged); structured report returned.

### P0.2 Survivorship census (Sonnet) → P0 Measurement memo (Opus)

- Census: quantify delisted-name absence — PIT member-months (`data/breadth/sp500_pit_membership.parquet`) without prices in the panel; broader board universe vs store coverage; probe the Massive whole-market store for delisted-ticker coverage within its rolling-5y entitlement (sample known 2021–2026 delistings). Memo: `research/entry_intel/P0_2_SURVIVORSHIP_CENSUS.md`.
- Measurement memo (Opus, consumes census): `research/entry_intel/P0_MEASUREMENT_MEMO.md` — bias-bound stamps per era (which windows support verdict-grade claims vs context-only), backfill recommendation, and the era table every P1 PREREG must cite.

### P0.3 Liquidity/capacity hygiene (Sonnet)

- Verify whether any ADV/liquidity screen exists in the board pipeline today; report either way.
- Add per-row hygiene fields: `adv_dollar_21d`, `days_to_exit_at_10pct_adv`. Display/hygiene only (R10). Small PR, not merged without review.

## §5 Phase 1 — Study battery (five PREREGs, parallel, all reading the replay artifact)

All five PREREG drafts live in `research/entry_intel/`, marked DRAFT until Fable approval; one BH family per study; trials capped in the PREREG; features frozen to replay columns.

- **P1.1 Separability** (`P1_1_SEPARABILITY_PREREG.md`): on the pre-gate pool, do existing captured fields separate terminal states? Rank-based association per feature vs P(cushioned ∪ clean-liftoff), BH across the frozen feature list. Output: ranked survivors → re-rank candidates for P3.
- **P1.2 Gate P&L** (`P1_2_GATE_PNL_PREREG.md`): per rejection reason, counterfactual outcome distribution vs matched fired cohort (match on date-cluster + sector + alignment tier). Pre-registered verdict thresholds per gate: keep / demote-to-penalty / flip. Safety-net axes decide.
- **P1.3 Trio ablation** (`P1_3_TRIO_ABLATION_PREREG.md`): washout-proximity, RS-inflection, anti-chase on **production-trigger fires** — each as (a) hard gate, (b) rank weight. Deltas on stop-out / dead-money / cushion at 21/63d; BH q≤0.10; both-halves stability. Survivors → §6 P2.1 promotion.
- **P1.4 Recall audit** (`P1_4_RECALL_PREREG.md`): denominators = all in-universe durable-low events and +20%/60d moves in the window; partition each by funnel verdict at event time (fired / near-missed / rejected-by-reason / never-triggered). Descriptive census with CIs — the program's first coverage metric; becomes a standing quarterly number.
- **P1.5 Continuation partition** (`P1_5_CONTINUATION_PREREG.md`): fires partitioned by weekly phase / RS quartile / 200DMA side; grade differentials answer **exclude vs mislabel vs underrank** for continuation setups; decision rule maps each answer to its fix (new clade PREREGs / relabel / re-rank).

## §6 Phases 2–4 (condensed; each gated on prior verdicts)

- **P2.1** Promote P1.3 survivors via the ladder; production-trigger replay evidence qualifies for the pre-validated seeding precedent (same evidence class that seeded S1/T1-T4); ships shadow-first.
- **P2.2** Gate demotions/promotions per P1.2 verdicts.
- **P2.3** Continuation clade IF P1.5 shows a real gap: PREREG 2–3 species (Leader Reload, Compression Breakout); phase-0 runs immediately on the replay artifact.
- **P2.4** Board contract v2: unify two-board divergence; one product, explicit lanes (bottoming / continuation / watch); rows carry species_id, cell outcome distribution, invalidation, capacity. Additive-lanes law applies.
- **P3.1** Cell rollups species×archetype×regime×horizon with hierarchical shrinkage (extend kernel math).
- **P3.2** Shadow kernel-rank = Wilson lower bound of P(cushioned ∪ clean-liftoff) from shrunk cell posterior; side-by-side with incumbent; pre-registered flip (R6).
- **P3.3** Card redesign: render the outcome distribution, not a score ("fires like this: 58% cushioned / 22% stopped, MFE/MAE 1.8, n=41") + plain-English boxes.
- **P4.1** Species-desk adapter → qledger entity claims (falsifier = stop/dead-money bound). **P4.2** Article 3 authority per species family; board_ordering flows through the constitutional perimeter. **P4.3** New species PREREGs register through W7b machine-registration when it lands (loose coupling — nothing blocks on W7b). **P4.4** Board summary becomes a stock-level lobe in world_state.

## §7 Delegation & escalation

- Fable: orchestrator, PREREG approvals, phase gates, merges, red-team rulings. Never delegated.
- Opus: PIT audit (P0.1), measurement memo, PREREG red-team, study verdict reviews.
- Sonnet: all build (harness, census, hygiene fields, studies, adapters, UI).
- Haiku: P1+ mechanical sweeps, batch grading runs, golden-diff triage.
- Escalation: a blocked subagent stops after two distinct failed approaches and returns a structured blocker report → Fable re-scopes or retries at a higher tier → if still blocked, Fable does it directly.

## §8 Risks

Replay infidelity (→ golden test hard-gates); PIT lookahead (→ dedicated Opus audit; the golden test cannot catch historical leaks); thin cells (→ shrinkage + n-floor printing rules); confirmation-stacking starves board (→ R7 + P1.4); study multiplicity (→ five pre-registered families, capped trials); worktree/data coupling (→ replay reads canonical `data/` by absolute path, writes only to `data/replay/`).

## §9 Status log (append-only)

- 2026-07-04 — Program adjudicated; masterplan merged; Phase 0 + PREREG drafting dispatched (Sonnet×8, Opus×4). — Fable
- 2026-07-05 — P0 COMPLETE. Harness v1 BOUNCED by PIT audit (F1 prefilter recall / F2 vacuous golden); Opus repair → re-audit CLEAN → merged #1312 + universe PIT-union patch #1381 (927→1,033 tickers, delisted ex-members restored). Liquidity hygiene merged #1304 (finding: zero liquidity screens existed). Measurement memo v1.1 = LAW: effective verdict window ≈2022-06-30+, canonical input replay_boarded.parquet, board_rank_unresolved residual labeled. Five P1 PREREGs drafted, red-teamed (5 blocking fixed), era law absorbed — DRAFT pending Fable approval at P1 dispatch. Full-universe replay (6 year-shards) launched. — Fable
- 2026-07-05 — P1 UNLOCKED. Full-universe replay complete: 961,656 rows / 57,640 fires (49,939 verdict-grade) / 25,783 episodes, window 2022-06-30→2026-07-02 (AF3 exact). Baseline verdict-grade fire outcomes: 63% STOPPED / 33% CLEAN_LIFTOFF / 4% CUSHIONED — the raw gate's honest report card. Sector map widened #1466 (rs_sector_quartile 5%→92% on fires). Five PREREGs APPROVED with §APPROVAL v1.1-conformance blocks; P1 study battery dispatched (5× Sonnet runner → Opus conformance review). — Fable
- 2026-07-05 — P1 BATTERY ROUND 1 ADJUDICATED. P1.1 CONFORMANT: 5 separability survivors {dist_52wh, cohort_washout_proximity(PROXY), ext_z, ext_atr, weekly_phase(categorical)} → P3 re-rank candidates. P1.2 honest null (KEEP all gates, 0/72) + structural finding: replay taxonomy must carve freshness_expired/tier_cutoff distinctly (harness work item, enables P1.2b). P1.3/P1.4/P1.5 BOUNCED by Opus reviews (broken bootstrap centering at observed U; censored-row contamination; tier_cascade≠align_tier arm mis-specification) — re-running at Opus tier with mandatory positive/negative statistic-calibration controls. All round-1 artifacts committed incl. bounced runs per species trial-recording law. — Fable
- 2026-07-05 — P1 COMPLETE (round 2, all five CONFORMANT). P1.3 OVERTURNS round-1 artifact: valid permutation null + passing calibration controls → ~3 independent effects: F3 anti-chase SHIPS-AS-HARD-GATE (4.6% fire cost; stop −0.43pp@21d/−5.00pp@63d), F1 washout GATE-REJECTED (54% fire cost — CN gates-kill-edges law confirmed in US data) but SHIPS-AS-RANK-WEIGHT (dead-money −13.19pp@21d, stop −5.21pp@63d), F2 RS-inflection rank-weight only. P1.4 corrected: fires on 0.24% of durable lows / 5.12% of large moves; never-triggered 7.8–8.9% (all horizon-censored); ESC-1 stands. P1.5 H-MISLABEL on correct align_tier arms (Δ−2.79pp): continuation setups mislabeled, not excluded → P2.4 lane relabel; P2.3 continuation clade CLOSED by evidence. Below-200DMA fires materially outperform (T4 q≈0). PHASE 2 SCOPE: P2.1a F3 hard-gate PREREG, P2.1b F1/F2 rank-weight PREREG (F1 needs production washout source), P2.4 lane relabel + board contract v2, P1.2b taxonomy extension, P3 kernel-rank PREREG from P1.1 survivors. All shadow-first per Article 2. — Fable
- 2026-07-05 — PHASE 2 LAW APPROVED. Five docs drafted, xhigh-red-teamed (9 BLOCKING caught incl. fabricated flip-floor citation, backwards flip inequality, silent lane no-op vs live vocab ['None','aligned']), all fixes applied + verified. Fable rulings: R-P2.1 anti-chase flip floor = 100 blocked episode-clusters + 2 quarters live accrual (P1.5 K1 precedent); R-P2.2 P2.1b §3.3 = single concordance authority (90% floor, GO artifact), P3 consumes verdict. Builds dispatched: board stack serialized (P2.4→P2.1a→P2.1b w/ concordance-first) ∥ P1.2b re-tag ∥ P3 kernel-rank shadow. — Fable
- 2026-07-05 — P2 BUILD ADJUDICATION ROUND 1. P3 kernel-rank shadow MERGED #1473 (CLEAN; concordance-absent fallback Σw=0.86 applied; 94 cells; flip floor 300 = §5.2, R-P2.1 scoped to P2.1a only — amendment). P1.2b MERGED #1471 after verdict-of-record correction (tier_cutoff = INSUFFICIENT-POWER under registered no-overwrite rule, n=37<50; builder's 121-row override re-labeled post-hoc exploratory INCONCLUSIVE-THIN; freshness_expired KEEP n=872 stands). P2.4 ratified (ADVISORY-1: conviction.alignment.tier = canonical lane source — spec's registered source could never fire on live vocab ['None','aligned']; template ref corrected to dashboard.html.j2). Board stack RESUMED with inserted real-build verification stage (two builds same data, baseline-vs-v2 row-set identity, signal_archive copy-protected) → P2.1a → P2.1b. — Fable
