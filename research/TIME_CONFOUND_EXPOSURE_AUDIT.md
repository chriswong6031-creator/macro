# Time-Confound Exposure Audit — Verdict-Grade Results on Cluster-Resampled Inference

**Date:** 2026-07-06
**Authority:** DT-W1a (research/dannytrades/DT_W1_RESULTS.md) + Ruling DT-R14 (research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §7)
**Status:** READ-ONLY exposure inventory. **No verdict is re-run or overturned here.** Items are flagged as re-check candidates for a Fable-tier adjudication session.
**Method:** six audit lanes (five Opus reviewers reading run scripts — not summaries — plus one Sonnet census sweep). Every machinery claim carries a file:line reference from the run code. Spot-checks of the two top-ranked items' load-bearing numbers were re-verified against committed artifacts by the orchestrating session.

> **In plain English:** DT-W1a showed that when a study's events pile up in a few calendar months, resampling *tickers* or *episodes* makes confidence intervals look much tighter than they really are — the true sample size is the number of independent time periods, not the number of names. Three "significant" results died when the clock was controlled. This memo asks: which other shipped promotions/kills rest on the same broken ruler? Answer: the exposure is **not house-wide** — it concentrates in two machinery families (the entry-intel ticker-week episode permutation and the oracle fire/episode-level gauntlets), while the options, china-alpha, entry-stack, and month-block families already control for time correctly.

---

## 1. Rubric (what DT-W1a actually established)

1. **The failure mode.** On a regime-limited panel (2021+), monthly base returns swing −10%..+9.6% across calendar months. If events cluster in particular months, ticker/episode-cluster bootstrap treats ~600 correlated draws as independent when the effective independent N is ~60 months. CIs come out too narrow → false "CI-excludes-zero" verdicts.
2. **Passing negative controls do NOT certify against this.** DT-W1's within-ticker time-permutation control (C1) PASSED even while the raw CIs were anti-conservative. Permutation nulls test *signal existence under a within-unit exchangeability null*; they say nothing about *CI calibration under cross-time correlation*. A study advertising "calibrated permutation machinery with negative/positive controls" is not thereby cleared — the control design must be checked.
3. **Within-unit permutation is structurally powerless for LEVEL tests.** It preserves each unit's value multiset, so high-value units stay selected under the null (DT-W1's H3 permuted "null" was a *positive* selection artifact).
4. **Point estimates move too, not just CIs.** Within-month demeaning changed DT-W1's H1 lift from −3.3pp to −0.6pp. So the confound threatens kills as well as promotions (a kill's point estimate can be month-composition-inflated) — per house law, kills get the same scrutiny.

**Exposure ratings used below:** **LOW** = calendar-time control in primary inference (within-period demeaning, time/month-block resampling, per-date collapse + HAC, year/era-stratified null, time-forward walk-forward), or events well-spread over a multi-regime window. **MEDIUM** = partial control (era splits without time-block resampling; annual-only stratification; excess-vs-index absorption; chronological dev/holdout as the only guard). **HIGH** = pure ticker/episode/fire-cluster CI or within-unit permutation, regime-limited effective window, time-clustered events, verdict rests on CI-excludes-zero or a p-threshold.

---

## 2. Ranked exposure table

| # | Study / verdict | Shipped as | Resample unit | Time control | Exposure | Flip plausibility |
|---|---|---|---|---|---|---|
| 1 | **EI P1.3 trio ablation** — F3 anti-chase gate warrant (+ F1/F2 rank-weights) | hard-gate designation; P2.1a implements shadow-first | ticker×ISO-week `episode_id` label permutation | NO (sign-only halves guard) | **HIGH** | **HIGH** — T24 (the F3 63d ship trial): Δ=−5.00pp, half1=−8.75/half2=−1.55, bh_adj_p=0.0933 |
| 2 | **Oracle W2 member-transmission** — CONFIRMED, display-with-edge (#1533) | Turn Desk / display chip | armed window (31 IN), OUT arm fixed | PARTIAL (placebo re-places windows in time; cluster boot + R3 do not) | **HIGH** | **MEDIUM** — drop-quarter Δ=0.0823 < formal placebo p95 0.1013; likely CONFIRMED→PARTIAL |
| 3 | **SEQ_TLT_RELIEF_WASHOUT** — REGISTERED new signal (#1576) | registry `screened` (display ceiling intact) | member fire (n=745), no CI on gauntlet legs | NO (only Leg-5 temporal split; Leg-6 placebo assumes fire independence) | **HIGH** | **MEDIUM** — registered→marginal/FAIL under episode-block null |
| 4 | **Oracle Compound Gauntlet R1** — A15/A9 PASS; A17 modern-regime PASS | compound registry; A15 → research-factory paper | per-node episode-pool index draws | NO (G2 era-persistence gate only, not in the null) | **HIGH** | **MEDIUM-HIGH** for A17 (n=73, 2021+); MEDIUM for A15/A9 |
| 5 | **Oracle Gauntlet P3/P8** — `ep_in_onset_21d` sole BH-rejected secondary | pending-adjudication context in P8 | 21-consecutive-episode blocks in *detection order* | NO (blocks are not calendar blocks) | **HIGH** | MEDIUM — primaries are NULL (safe); only the positive secondary is exposed |
| 6 | **bottom_signal_backtest tuned combos** (PR #1207 provenance) | quarantined as test-leaked by S7 SPEC | none — point-estimate combo-max, no CI/multiplicity | PARTIAL (coarse 3-block split) | **HIGH** (contained) | HIGH for the combo claims; the *actual* verdicts were re-adjudicated by the time-controlled S7 re-run |
| 7 | **Long-hold expect_drift ED-2 `sue_streak`** — DESCRIPTIVE_PASS | display-tier upper bound; Ruler-H ~2027-H2 | iid Mann-Whitney p (BH gate) over deduped fires | PARTIAL (annual reshuffle co-gate; 2014-23 window) | **MEDIUM** | MODERATE — q=0.068 borderline, pass concentrated in 2022-23 |
| 8 | **EI P1.5 continuation** — H-MISLABEL, clade CLOSED | UI relabel + clade closure | ticker-week episode bootstrap | NO | **MEDIUM** | MEDIUM — magnitude/CI exposed; direction more robust; possible false-negative clade close |
| 9 | **EI P2.1b F1 reprobe** — rank-weight KILL | kill (sign reversal) | ticker-week episode permutation | NO | **MEDIUM** | LOW-MED false-kill — kill rests on a sign flip (robust), but both original and reversal magnitudes are time-uncontrolled |
| 10 | **EI P2.5 interaction** — PARTIAL_SHIP (6/8 configs) | shadow ledger only | ticker-week episode permutation | NO (baseline-free halves partial) | **MEDIUM** (shadow-quarantined) | deferred to forward ledger; in-sample perm_p optimistic |
| 11 | **Healthcare R-1 construction divergence** — "null held" → LOCK, no key ships | descriptive lock | iid unpaired t-test; ablations all within-unit | NO (promised block-collapse is decorative + index-broken) | **MEDIUM** (apparatus HIGH) | **false-NULL direction**: DD63 (89.8th pctile) is a live candidate to flip toward a real effect under stress-stratified/calendar-block inference |
| 12 | **S7 RS-repair cohort dev-PASS** — held at phase0 | phase0 (holdout already failed to replicate) | calendar-month paired delta (compliant) | YES | **MEDIUM** (window 2021+, thin subset) | LOW-MOD — already self-corrected; the two S7 kills are harmful-side significant (safe) |

Everything else audited rates **LOW** — see §6.

---

## 3. HIGH-exposure detail (ranked)

### 3.1 EI P1.3 trio ablation — the F3 anti-chase gate warrant

The lane-wide root cause: `episode_id` is defined at `scripts/replay_standout_pipeline.py:739` as `ticker × ISO-week`. Its design purpose (comment at L737-738) is to avoid double-counting the *same ticker's* correlated entries within a week — it is **not** a calendar-time control: different tickers in the same market week are treated as independent draws. 49,939 fires → 22,295 "independent" episodes over ~208 calendar weeks (~48 months), 2022-06-30→2025-12-29.

- **Machinery:** episode-level label permutation Mann-Whitney (`research/entry_intel/p1_runs/P1_3/run_P1_3.py:209-291`), N_PERM=5000, BH q≤0.10 over m=30, plus a both-halves **sign-only** guard (L446-451). No demeaning, no calendar stratification.
- **Time-clustering is verdict-defining, not incidental:** F3 sorts on price extension (would-block group concentrates in melt-up months); F1 sorts on washout proximity (concentrates in drawdown months). The would-pass/would-block arms draw from *different calendar-month mixtures*, so market-time effects do not cancel.
- **The controls could not catch it (rubric point 2, verbatim):** the negative control (L342-381) draws null labels via the *same* full-window episode permutation the test uses — it certifies uniform p under within-window exchangeability and injects no calendar-clustered confound. The P1.3 red-team review (`REVIEW.md:38-44`) also never raised calendar clustering.
- **Quantified fragility (verified against `P1_3/results.json`):** T24 (F3 hard-gate, 63d stop) Δ=−5.00pp with half1=−8.75pp / half2=−1.55pp (5.6× swing, effect concentrated in the 2022-23 half) and bh_adj_p=0.0933 — barely under the q=0.10 bar. A month-block bootstrap would widen this CI substantially; BH survival is fragile. T09 (F1 rank-weight 63d): Δ=−4.55pp, half1=−7.81/half2=−0.78 (10× swing) — a single-half phenomenon, later independently killed by P2.1b. T21 (F3, 21d) is sign-stable but trivially small (−0.43pp). **T02 (F1 dead-money, Δ=−13.19pp, half1=−14.0/half2=−12.3) is the one large, half-stable effect — low flip risk.**
- **Stakes & mitigation:** this is the only audited study whose verdict designated a *production gate* (F3 anti-chase). The P2.1a implementation runs shadow-first with a forward flip floor (100 blocked episode-clusters + 2 quarters), so live money-path exposure is mitigated — but the statistical warrant behind the gate candidacy is the single most exposed positive in this audit.

### 3.2 Oracle W2 member-transmission CONFIRMED (#1533)

The one lane where a *real* DT-R14-class control exists — and it is exactly why the residual exposure is visible.

- **Machinery:** WR computed at member-fire row level; independence handled solely by resampling the 31 IN armed windows (`scripts/oracle_member_transmission_w2.py:402-448`); the delta CI (`cluster_bootstrap_delta_ci`, :715-776) resamples *only* the 31 IN windows — the OUT arm (369,475 rows) is computed once as a fixed point (:747), contributing zero uncertainty. The R1/R2 placebo (:488-577) genuinely re-places windows at random VIX-matched calendar locations — a legitimate event-date-shift time control — but it scatters windows *independently*, under-representing their real joint clustering into macro episodes.
- **Clustering:** the 31 IN windows collapse to 16 distinct calendar months and ~6-7 macro episodes (2022-07/10, 2023-08→11, 2024-04/05, 2024-12→2025-05, 2025-11/12); windows are merged only *within* a node (:264-275), so XLF/XLI/XLK windows in the same October-2023 episode count as independent clusters. True independent time-N ≈ 6-7 episodes.
- **The study's own probes expose the margin (verified):** drop-most-favorable-window Δ=0.1040 vs formal symmetric-placebo p95=0.1013 — a ~1.5pp cushion, stated honestly in `W2_FORMAL_PREREG.md:50` (C9). Drop-most-favorable-**quarter** Δ=0.0823 clears only the *older* W2-era placebo bar (0.0565, `W2_REPORT.md:178`); it sits **below** the corrected formal p95 (0.1013) that the CONFIRMED verdict itself used. An episode-block null (N≈6-7) would widen the bar further.
- **Weakest link:** R3 holdout — n=15 windows (~3-4 episodes), MDE@80% = 39.3pp for an 11pp effect, compared against a **full-history** OUT baseline rather than a holdout-period-matched one (`:1551`; admitted in prereg C3).
- **Plausible outcome of a re-check:** R1/R2 survive with narrowed margin; R3 fails under a period-matched OUT + episode-block CI → **CONFIRMED downgrades to PARTIAL**. The program's §5 forward ledger is already the designated decisive arbiter, which is the right posture.

### 3.3 SEQ_TLT_RELIEF_WASHOUT registered (#1576)

- **Machinery:** all six reversion-gauntlet legs operate on the member-fire row (n=745) with **no CI on any leg** (`scripts/oracle_reversion_screen.py:920-1083`; `_agg_stats` :434-455). Leg 6's timing placebo draws count-matched outcomes *independently with replacement* from each node's pool (:734) — a null whose variance is ~σ/√745, i.e. it assumes fire independence by construction, the exact anti-conservative pattern. Grep confirms no block bootstrap / demeaning / overlap purge / HAC anywhere in the screen.
- **Clustering:** the signal is sequence(TLT 10d relief → sector washout) — both legs fire in discrete macro episodes by construction. Mitigants: full 1998-2026 window (holdout 267/745 fires; feature coverage is deep here, not 2021+), and a passing temporal dev/holdout split (Leg 5) — though the holdout WR≥0.58 gate is itself un-CI'd on clustered fires.
- **Flip:** an episode-block placebo raises the Leg-6 p95 (currently +1.16% vs observed +2.37%); episode-clustered CIs on Legs 2/5 push the WR lower bounds toward the 0.62/0.58 bars. Point estimates are healthy, so hard kill is not the base case — **registered→marginal/FAIL is plausible**. Registry status is already `screened` (display ceiling intact).
- Secondary (non-time) finding: Leg-5 split uses `entry_date` for dev but `trigger_date` for holdout (:1025-1026) — asymmetric boundary; minor.

### 3.4 Oracle Compound Gauntlet R1 — A15/A9/A17 PASS

- **Machinery:** G3 placebo draws count-matched pseudo-onset indices from each node's realizable pool with no calendar structuring (`scripts/oracle_gauntlet_compound.py:281-298`). G2 era-persistence (≥3/4 eras) is a real but *external* stratification — it never enters the null distribution.
- **Exposure peaks at A17:** the corrected modern-regime PASS rests on n=73 events, all 2021+ — few effective calendar months, episode-indexed draws. A15/A9 use the full 27y pool (more episodes) but the same independence-assuming null. **A15 has been forwarded to a research-factory paper**, which raises the cost of a spurious PASS propagating.

### 3.5 Oracle Gauntlet P3/P8 — the one positive among nulls

- **Machinery:** `block_bootstrap_ci` (`scripts/oracle_gauntlet_p3.py:316-355`) blocks 21 *consecutive episodes in detection order* — not calendar months. On a regime-concentrated panel, adjacent detection-order episodes can share the same few months, so blocks under-represent cross-time correlation. The placebo (:1789-1913) draws random date indices with no calendar structure. P8 imports the same machinery.
- **Exposure is asymmetric:** P-EXIT/P-ENTRY/P-W1 primaries are NULL — anti-conservative machinery makes nulls *more* credible, not less. The exposed result is the sole BH-rejected secondary `ep_in_onset_21d` (raw p=0.0075) and the P8 "standout accruing" framing it feeds. Any future promotion citing it should require calendar-block inference first.

### 3.6 bottom_signal_backtest tuned combos (contained)

Zero inference machinery anywhere (`metrics.py`, `tune_combinations.py:202-209` — point-estimate guardrails over hundreds of combos, no CI/p/multiplicity), on a panel whose base 20d median swings ~5.2pp across calendar years with 16% of fires in 2022 alone. Meets every HIGH clause. **Contained** because `research/species/s7_rs_repair_phase0/SPEC.md:8` already forbids citing the tuned CSVs as evidence (test-leaked), and the actual PR #1207 verdicts were re-adjudicated by the time-controlled S7 re-run. The residual risk is *citation leakage*: any downstream surface quoting `final_report.md` / `tuning_report.md` headline combos ("cut stop-outs ~half") as evidence would be a house-law violation.

---

## 4. Structural findings — frozen gates and broken controls (latent, act BEFORE next verdict batch)

These don't flip a shipped verdict today; they guarantee a future DT-W1a repeat if used as written.

- **RR-1 (replay promotion gate).** `research/rule_replay/R1_CHARTER.md:61` mandates "episode-clustered bootstrap, BH-FDR q≤0.10, n≥300/side, ≥25 episode-clusters" for any promotion off the replay surfaces — episode-cluster resampling with **no calendar-time control**, on a cohort that is 100% 2021+ (49,939 fires; ~41 calendar blocks under a strict ±30d reading). Amend the charter to require month-block resampling or within-period demeaning before any replay-surface promotion prereg is written.
- **DG-1 (dispersion gate).** `research/dispersion/L3_PREREG.md:106-107` criterion 4 = "episode-clustered bootstrap 90% CI for the stop5 gap excludes 0" — same non-compliant construction, plus an internal ambiguity: Standing Notes define clusters as ±30d contiguous blocks, but the shipped DISP-GATE-1 run clustered on granular `episode_id` (thousands of clusters vs ~17-20 ±30d blocks per arm — below the report's own 25-cluster floor). The trailing-252 lean_out +9.1pp gap is a prime candidate to clear a naive episode CI and vanish under month-blocks. Also: the "DEFER ×2-replicated" descriptor is sign-and-flip-rate concordance across two panels, not a replicated inferential result — do not read it as corroboration.
- **CD-1/2/3 (R-1 construction divergence apparatus).** Three code-level defects in `scripts/study_construction_divergence.py`: (CD-1) `bootstrap_effective_t` at :708 is fed a **non-chronologically-ordered** list (events concatenated sector-pair by sector-pair at :954-975), so the reported effective-t ratios (~0.91/0.83) measure autocorrelation of an arbitrary ordering, not calendar time — independence is overstated; (CD-2) the prereg-promised ±7-day co-firing block collapse exists (`_block_collapse`) but feeds only `block_counts` reporting (:1102-1105), never any statistic — and it is keyed on per-sector-pair positional `bar_i` (:442 vs :296/:361), so cross-sector collapse would be meaningless even if used; the shipped SE is a plain iid unpaired t-test (:712-716); (CD-3) all three ablations are within-unit permutations that preserve calendar composition — DT-R14-powerless. Consequence in §5 below.

---

## 5. MEDIUM-exposure detail

- **Long-hold expect_drift ED-2 `sue_streak` DESCRIPTIVE_PASS.** The pass-gate hard-ANDs an **uncontrolled iid Mann-Whitney p** (`scripts/research/expect_drift_ruler_p_study.py:279-285, 696-709`); the genuinely time-blocked CI (:360-397, ~88-day blocks) is computed but **not in the verdict gate**. Reshuffle co-gate is stratified only annually (cohort_year × regime); returns are absolute, not excess-vs-index; 252d windows overlap across tickers uncorrected. Mitigants: 2014-2023 multi-regime window; within-cohort-year tercile outcome removes annual means. The pass is thin (full q=0.068) and carried by the 2022-23 sub-window (SUE features are wrong-signed in the 2020-21 cell). Moderate positive→null flip risk; display-only today, so no product consequence — but the "family's only pass" headline is fragile. Sibling studies insider_lh (all NULL) and W1 kill-test (verdict = n-floor DEFERRAL) share the machinery but their outcomes are confound-robust directions.
- **EI P1.5 continuation (clade CLOSED).** Same ticker-week bootstrap; the −2.79pp mislabel magnitude and p are exposed; the directional conclusion is more robust. The risk is a **false-negative clade closure** if month composition inflated the ARMED-vs-PRIME gap.
- **EI P2.1b F1 kill.** The kill rests primarily on a proxy→production **sign reversal** (−4.55pp→+3.34pp), which is structural and survives time controls; but the original T09 promotion evidence was itself a single-half artifact, so both sides of this story were measured on the broken ruler. Kill probably correct, partly for the wrong reason.
- **EI P2.5 PARTIAL_SHIP.** Correctly quarantined to a shadow rung (masterplan flags the in-sample-selected grid); its in-sample perm_p values are time-confounded and likely optimistic — expect the forward ledger to underperform them.
- **Healthcare R-1 "null held" lock — the one false-NULL candidate.** Given CD-1/2/3, the lock's null cannot distinguish "no effect" from "effect masked by systemic-stress mixing": confirmed events concentrate in market-wide stress (2×2: 74 confirmed-stress vs 42 divergent-stress), which dampens the pooled contrast, and the report's own stress-stratified table shows divergent shallower **within both strata** (calm −2.84 vs −2.97; stress −4.76 vs −5.54). DD21 likely stays null (effect tiny); **DD63 (already 89.8th percentile, div p10 −12.35 vs con −15.12) is the live candidate to flip toward a real divergent-shallower separation** under stress-stratified or genuine calendar-block inference. A missed de-escalation key is the cost of leaving this unexamined.
- **S7 RS-repair dev-PASS.** Machinery is actually compliant (calendar-month paired-delta bootstrap, `research/species/s7_rs_repair_phase0/analyze.py:154-173`, plus chronological holdout) — the MEDIUM comes from the 2021+ P1 window, the thin mapped subset, and a provenance gap (§8). The system already worked as designed: dev-PASS failed to replicate on holdout and S7 stayed at phase0. The two S7 kills (RS-vs-SPY REFUTED, triple-lock NO-GO) are holdout-significant on the *harmful* side — time controls cannot rescue them; safe.

---

## 6. Cleared / LOW-exposure inventory (nulls printed, per house law)

| Study | Why LOW |
|---|---|
| EI P1.2 / P1.2b gate-P&L | genuine time-block machinery: `episode_cluster_id` overwritten with shared 21-trading-day calendar blocks (`run_P1_2.py:278-287,534`), contrasts matched *within* block — DT-R14-compliant; verdicts are nulls besides |
| EI P1.1 separability | CR1 cluster-robust SE on **calendar-week** (ticker stripped, `run_P1_1_SEPARABILITY.py:136-138`) — the effective time-N is respected (LOW-MED: no demeaning, borderline BH survivors worth a glance) |
| EI P1.4 recall; P3 kernel-rank | no CI-based verdicts (Wilson coverage census; shadow parquet with pre-registered forward flip) |
| A2 esx_insider (entry_stack) | within-date FE demeaning + sector×±14d time-block bootstrap in primary inference (`entry_strata_phase0.py:628-651,662-716`) — the reference-compliant design |
| A2 esx_macro/pos_reset (R1-M) | date-only ±14d time-block bootstrap + Frisch-Waugh VIX/drawdown controls; the one borderline adverse finding (q=0.096) was already not wired |
| Long-hold insider_lh; W1 kill-test | all-NULL / n-floor DEFERRAL — confound-robust directions; machinery caveats noted in §5 |
| Species S6 | calendar-month block bootstrap (`w1_s6_analysis.py:73-92`); base3d leg self-disclosed fragile (CI touches zero), m2d_s3d robust |
| Species S13 | monthly return-series unit, HAC-t + deflated Sharpe + 3-month block bootstrap, N=358 months printed — arguably the house reference implementation of DT-R14 |
| Options W-E1 gauntlet (corrected) | per-date cross-sectional collapse + HAC with lag ≥ 2×horizon; the anti-conservative pooled-MWU version is quarantined in an appendix |
| Options opex vanna/charm | per-date IC + HAC + era splits + placebo weeks; the signed-charm kill rests on residualization (IC→0), not a clustered CI |
| entry_stack W0/W1/W2 (incl. NC-2 positive) | sector×±14-calendar-day blocks + date FE inside the bootstrap; era splits 2012-2026 |
| LABEL_FALTERING B1/B3 NO-GO | whole-date-bar resampling + Newey-West HAC + chronological split-half, 1998-2026 |
| china_alpha W3A (NO-GO) / W5A (CONFIRM-on-plane) | HAC t on monthly rebalance series (n=349); within-rebalance permutation preserves temporal structure; survivorship caveat separately stamped |
| short_side BD-ECON1 (all NULL) | pre-registered **month×ticker two-way bootstrap** (`bd_econ1_counterfactual.py:277-356`) — months drawn first; canonical DT-R14 structure |
| short_side BD-Phase0b (3× NO-GO) | episode-clustered on 2021+ (non-compliant machinery) but all outcomes are NO-GO with wrong-direction deltas — confound-robust direction; note for any revival |
| Signal Commons W5A / W2 half-lives / W3 event study | W5A: display-only underpowered null on a 19-day window (moot); W2: structural gate null; W3: per-date collapse + HAC primary (fixed lags=4 is slightly light for long horizons — minor) |
| Oracle W1/W1B onset-quality; P3/P8 primaries | printed NULLs — anti-conservative machinery only strengthens a null |
| Oracle P2 promotion scan (#1563) | queue-only thresholder, no origination; inherits upstream 63d-screener bias, which the reversion-metric reframe already deprecates |
| rule_replay EXIT/TRIM/WAIT grids; DISP-GATE-1 cells | descriptive-only by charter, no CIs computed — exposure is latent via the gates (§4) |
| validate_provisional_replay FRESH_TICKS ship gate | purged/embargoed time-forward walk-forward OOS margin — strongest time discipline in the replay family |
| factor_intelligence prereg | month-block bootstrap pre-registered; no results yet |

---

## 7. Recommended targeted re-checks (queue for Fable-tier adjudication — none executed here)

Ordered by stakes × exposure × cheapness. Each is a bounded re-run of *inference only* (events/thresholds frozen), mirroring the DT-W1a repair pattern.

1. **EI-RC-1:** P1.3 T24/T21 (and T18) under within-month demeaning + month-block bootstrap on the frozen episode panel. Decides whether the F3 anti-chase hard-gate warrant stands or the gate stays shadow-pending-forward-ledger. T02 expected to survive; include it as the internal positive control.
2. **GATE-AMEND:** amend `R1_CHARTER.md:61` and `L3_PREREG.md` criterion 4 to require a calendar-time control (month-block or within-period demeaning) + resolve the L3 cluster-definition ambiguity. Zero re-run cost; prevents two future false-PASS factories. Highest value-per-token in this memo.
3. **OTA-RC-1:** W2 member-transmission with (i) episode-level clustering (merge cross-node windows in the same macro episode), (ii) holdout-period-matched OUT baseline for R3. Expected outcome per the study's own probes: CONFIRMED→PARTIAL, forward ledger remains arbiter.
4. **OTA-RC-2:** re-run the reversion gauntlet Leg-6 placebo with episode-block draws + episode-clustered CIs on Legs 2/5 for SEQ_TLT_RELIEF_WASHOUT (and, cheaply, the rest of the registered compound family — same screen, same fix).
5. **ORC-RC-1:** compound gauntlet G3 placebo with calendar-block structure; priority on A17 (n=73, 2021+) since A15 feeds an external paper. Also re-express P3's `ep_in_onset_21d` secondary under calendar-block CI before it is cited anywhere.
6. **HC-RC-1:** R-1 construction divergence — fix CD-1/CD-2 (globally date-sorted events, real ±7d cross-sector block collapse into the SE) and read DD63 stress-stratified. This is the audit's one *false-null* candidate; a real de-escalation key may be sitting under a broken control.
7. **LH-RC-1 (low priority):** promote expect_drift's existing 88-day-block CI from decorative to gate for ED-2, or simply attach a "BH gate not time-controlled; pass concentrated 2022-23" caveat to the display tier until Ruler-H (~2027-H2).
8. **Citation guard:** add an explicit "no inference / test-leaked — do not cite" banner to `research/bottom_signal_backtest/results/final_report.md` and `tuning_report.md` at next touch (matches the S7 SPEC ruling).

Deliberately **not** queued: all printed nulls and n-floor deferrals (anti-conservative machinery only makes them more null); the S7 kills (harmful-side significant); everything in §6.

---

## 8. Provenance gaps noticed in passing (lower audit confidence where flagged)

- **S7:** the within-month permutation placebo + hand-recompute cited as the integrity control in `s7_rs_repair_phase0/REPORT.md §4` are **not in any committed .py** — not reproducible from the repo. The verdict-grade delta CIs are reproducible (`analyze.py`).
- **S6:** the raw fire panel lives at `/tmp/s6_wave2_baskets` (`w1_s6_analysis.py:23`) — only the JSON output is committed; CI numbers not reproducible from committed artifacts.
- **BD-Phase0b:** no explicit run script named in the report; machinery inferred from the Phase-0 prereg.
- **Signal Commons W2 half-lives:** run script not separately identified; audited from the masterplan row (gate is structural, so low impact).

---

*Audit lanes: entry_intel (Opus), long_hold (Opus), species+bottom-backtest (Opus), oracle turn-asymmetry (Opus), rule_replay+dispersion (Opus), cross-repo sweep (Sonnet census). Synthesis and ranking: Fable main loop. No `data/` writes, no script executions, no verdict changes.*
