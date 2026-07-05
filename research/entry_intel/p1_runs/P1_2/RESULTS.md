# P1.2 Gate P&L — RESULTS

**Study ID:** P1_2
**Run timestamp:** 2026-07-05T16:11:34.128725Z
**Era memo:** P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)
**Effective verdict window:** 2022-06-30 → 2026-07-02
**Canonical input:** data/replay/replay_boarded.parquet (961,656 rows)

## In plain English

> Every time the system says "no" to a stock for a specific reason — topped oscillator, 
> too many stocks from the same sector already on the board, knife-catch demotion, and so on —
> we now check: what actually happened to that stock afterwards? We compare those rejected
> names against a matched group of "yes" names from the same sector, same 21-trading-day
> window, and same alignment tier. If the rejected names would have stopped out just as often
> (or more) than the accepted ones, the gate is earning its keep. If the rejected names would
> have been safer and performed better, we flag that gate for loosening or removal. Every
> verdict is pre-committed in the PREREG before looking at a single outcome number — and a
> result only counts if it survives BH correction across all 72 p-values we test.

## Mandatory Stamp Text

**survivor-biased panel: for context-appendix rows (pre-era), 31.3% of member-months lack
price history; delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade.**

Primary results use ONLY unstamped rows (survivor_bias=False) within the effective verdict
window (2022-06-30 → 2026-07-02).

## Era Coverage Statement

- Era memo: P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)
- Effective verdict window: 2022-06-30 → 2026-07-02 (§APPROVAL clause 1)
- verdict_grade=True rows within window (primary): 834,267
- Stamped rows excluded from all computations: 0
- Episode clusters (21-trading-day windows): 44
- Fires in primary era: 49,939
  - board_rank_unresolved fires (DESCRIPTIVE ONLY per §APPROVAL clause 4): 11,069

## Taxonomy Mapping (Data Reality vs PREREG)

The PREREG registered 9 testable reasons. The replay substrate maps as follows:

| PREREG reason | Data column | n (verdict_grade) | Status |
|---|---|---|---|
| not_topped_veto | rejection_reason='not_topped_veto' | 92,715 | TESTABLE |
| board_rank_cutoff | rejection_reason='board_rank_cutoff' | 13,676 | TESTABLE |
| extension_demote | board_reason='extension_demote' on fire rows | 9,638 | TESTABLE (board-level) |
| knife_demote | board_reason='knife_demote' on fire rows | 20,696 | TESTABLE (board-level) |
| sector_cap_displaced | board_reason='sector_cap_displaced' on fire rows | 8,536 | TESTABLE (board-level) |
| freshness_expired | not present in data | 0 | INSUFFICIENT_N |
| tier_cutoff | not present as distinct reason | 0 | INSUFFICIENT_N |
| event_blackout | not present in data | 0 | INSUFFICIENT_N |
| cohort_null | not present in data | 0 | INSUFFICIENT_N |

**Design note for board-level demotions:** extension_demote, knife_demote, and sector_cap_displaced
appear as labels on FIRE rows (verdict_type='fire', board_verdict='board_rejection') rather than
rejection rows. The 'rejection cohort' for these reasons = fires that passed the signal gate but
were demoted at the board stage. The 'matched fired cohort' = fires with align_tier + sector
non-null from the same episode cluster/sector/tier, regardless of board_reason. This design
follows the PREREG Step 4 instruction ('all fire rows sharing the same episode_cluster_id,
gics_sector, alignment_tier').

**align_tier=NaN issue:** A large fraction of all cohorts have align_tier=NaN. These rows are
excluded from the matching design per the PREREG's exact-matching requirement. Gate-level
rejection rows with align_tier non-null: not_topped_veto=4,342 (4.7%), board_rank_cutoff=3,404
(24.9%). Board-level demotion rows with align_tier non-null: extension_demote=1,262 (13.1%),
knife_demote=5,175 (25.0%), sector_cap_displaced=1,457 (17.1%).

## Coverage Table

| Reason | n_total | n_matchable | n_survived (Step 3) | prune_rate | n_fire_matched |
|---|---|---|---|---|---|
| freshness_expired | 0 | 0 | 0 | 0.0% | 0 |
| not_topped_veto | 92,715 | 4,342 | 3,503 | 19.3% | 7,225 |
| tier_cutoff | 0 | 0 | 0 | 0.0% | 0 |
| extension_demote | 9,638 | 1,262 | 1,090 | 13.6% | 4,521 |
| knife_demote | 20,696 | 5,175 | 4,790 | 7.4% | 8,826 |
| sector_cap_displaced | 8,536 | 1,457 | 1,404 | 3.6% | 6,536 |
| board_rank_cutoff | 13,676 | 3,404 | 2,676 | 21.4% | 7,341 |
| event_blackout | 0 | 0 | 0 | 0.0% | 0 |
| cohort_null | 0 | 0 | 0 | 0.0% | 0 |

## Primary Verdict Table

BH correction: m=72, q≤0.10. All rates = proportion of cohort.
Wilson LB = one-sided 95% Wilson lower bound on rate.
Δ = rejection cohort rate − matched fired cohort rate.

### freshness_expired — **INCONCLUSIVE**
*Reason not present in replay data (0 rows)*

Reason not present in replay data. Counted in BH family (m=72) as INCONCLUSIVE.

### not_topped_veto — **KEEP**
*No significant axis at q≤0.10 (KEEP by default)*

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.394 (0.381) | 0.184 | 0.134 | 0.287 (0.275) | 3,503 |
| 21d | Fired (matched) | 0.393 (0.384) | 0.176 | 0.135 | 0.296 (0.287) | 7,225 |
| 63d | Rejection | 0.562 (0.548) | 0.013 | 0.156 | 0.269 (0.257) | 3,503 |
| 63d | Fired (matched) | 0.570 (0.560) | 0.008 | 0.153 | 0.269 (0.261) | 7,225 |

**Deltas and p-values:**

| Horizon | Axis | Δ | raw_p | BH_q | Significant |
|---|---|---|---|---|---|
| 21d | stop_out | +0.001 | 0.9658 | 1.0000 | no |
| 21d | dead_money | +0.008 | 0.5361 | 1.0000 | no |
| 21d | cushion | -0.001 | 0.9155 | 1.0000 | no |
| 21d | clean_lift | -0.008 | 0.6896 | 1.0000 | no |
| 63d | stop_out | -0.008 | 0.7062 | 1.0000 | no |
| 63d | dead_money | +0.005 | 0.5071 | 1.0000 | no |
| 63d | cushion | +0.003 | 0.8012 | 1.0000 | no |
| 63d | clean_lift | +0.000 | 0.9935 | 1.0000 | no |

**Sign stability:** UNSTABLE or THIN
  - h1: n_rej=1107, n_fire=2764, Δ_stop=-0.0050, Δ_cushion=0.0118
  - h2: n_rej=2396, n_fire=4461, Δ_stop=-0.0013, Δ_cushion=-0.0065

**126d Context** (not verdict-grade; n_rej=3,503, n_fire=7,225):
  Rejection: STOP=0.613, DEAD=0.001, CUSH=0.041, LIFT=0.346
  Fired:     STOP=0.629, DEAD=0.001, CUSH=0.042, LIFT=0.329

### tier_cutoff — **INCONCLUSIVE**
*Reason not present in replay data (0 rows)*

Reason not present in replay data. Counted in BH family (m=72) as INCONCLUSIVE.

### extension_demote — **KEEP**
*No significant axis at q≤0.10 (KEEP by default)*

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.418 (0.394) | 0.196 | 0.133 | 0.252 (0.231) | 1,090 |
| 21d | Fired (matched) | 0.393 (0.381) | 0.165 | 0.132 | 0.310 (0.298) | 4,521 |
| 63d | Rejection | 0.628 (0.603) | 0.008 | 0.149 | 0.216 (0.196) | 1,090 |
| 63d | Fired (matched) | 0.579 (0.567) | 0.007 | 0.139 | 0.274 (0.264) | 4,521 |

**Deltas and p-values:**

| Horizon | Axis | Δ | raw_p | BH_q | Significant |
|---|---|---|---|---|---|
| 21d | stop_out | +0.025 | 0.4948 | 1.0000 | no |
| 21d | dead_money | +0.031 | 0.4799 | 1.0000 | no |
| 21d | cushion | +0.001 | 0.8772 | 1.0000 | no |
| 21d | clean_lift | -0.057 | 0.4836 | 1.0000 | no |
| 63d | stop_out | +0.048 | 0.4878 | 1.0000 | no |
| 63d | dead_money | +0.001 | 0.7337 | 1.0000 | no |
| 63d | cushion | +0.009 | 0.6404 | 1.0000 | no |
| 63d | clean_lift | -0.059 | 0.4842 | 1.0000 | no |

**Sign stability:** UNSTABLE or THIN
  - h1: n_rej=634, n_fire=2194, Δ_stop=0.0308, Δ_cushion=0.0191
  - h2: n_rej=456, n_fire=2327, Δ_stop=0.0297, Δ_cushion=-0.0200

**126d Context** (not verdict-grade; n_rej=1,090, n_fire=4,521):
  Rejection: STOP=0.681, DEAD=0.000, CUSH=0.032, LIFT=0.287
  Fired:     STOP=0.633, DEAD=0.000, CUSH=0.035, LIFT=0.332

### knife_demote — **KEEP**
*No significant axis at q≤0.10 (KEEP by default)*

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.382 (0.370) | 0.143 | 0.118 | 0.358 (0.347) | 4,790 |
| 21d | Fired (matched) | 0.387 (0.379) | 0.168 | 0.127 | 0.317 (0.309) | 8,826 |
| 63d | Rejection | 0.539 (0.528) | 0.006 | 0.136 | 0.318 (0.307) | 4,790 |
| 63d | Fired (matched) | 0.559 (0.550) | 0.007 | 0.150 | 0.284 (0.276) | 8,826 |

**Deltas and p-values:**

| Horizon | Axis | Δ | raw_p | BH_q | Significant |
|---|---|---|---|---|---|
| 21d | stop_out | -0.006 | 0.5694 | 1.0000 | no |
| 21d | dead_money | -0.025 | 0.4763 | 1.0000 | no |
| 21d | cushion | -0.010 | 0.4854 | 1.0000 | no |
| 21d | clean_lift | +0.041 | 0.4864 | 1.0000 | no |
| 63d | stop_out | -0.019 | 0.5008 | 1.0000 | no |
| 63d | dead_money | -0.001 | 0.5025 | 1.0000 | no |
| 63d | cushion | -0.014 | 0.4818 | 1.0000 | no |
| 63d | clean_lift | +0.034 | 0.4906 | 1.0000 | no |

**Sign stability:** STABLE
  - h1: n_rej=2215, n_fire=3839, Δ_stop=-0.0012, Δ_cushion=-0.0188
  - h2: n_rej=2575, n_fire=4987, Δ_stop=-0.0055, Δ_cushion=-0.0016

**126d Context** (not verdict-grade; n_rej=4,790, n_fire=8,826):
  Rejection: STOP=0.595, DEAD=0.000, CUSH=0.038, LIFT=0.368
  Fired:     STOP=0.616, DEAD=0.000, CUSH=0.042, LIFT=0.342

### sector_cap_displaced — **KEEP**
*No significant axis at q≤0.10 (KEEP by default)*

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.346 (0.326) | 0.202 | 0.158 | 0.293 (0.274) | 1,404 |
| 21d | Fired (matched) | 0.366 (0.356) | 0.164 | 0.133 | 0.338 (0.328) | 6,536 |
| 63d | Rejection | 0.525 (0.503) | 0.009 | 0.184 | 0.282 (0.263) | 1,404 |
| 63d | Fired (matched) | 0.542 (0.532) | 0.006 | 0.146 | 0.306 (0.297) | 6,536 |

**Deltas and p-values:**

| Horizon | Axis | Δ | raw_p | BH_q | Significant |
|---|---|---|---|---|---|
| 21d | stop_out | -0.019 | 0.4884 | 1.0000 | no |
| 21d | dead_money | +0.038 | 0.4789 | 1.0000 | no |
| 21d | cushion | +0.025 | 0.4973 | 1.0000 | no |
| 21d | clean_lift | -0.045 | 0.4964 | 1.0000 | no |
| 63d | stop_out | -0.017 | 0.5065 | 1.0000 | no |
| 63d | dead_money | +0.002 | 0.5237 | 1.0000 | no |
| 63d | cushion | +0.039 | 0.4895 | 1.0000 | no |
| 63d | clean_lift | -0.024 | 0.4929 | 1.0000 | no |

**Sign stability:** STABLE
  - h1: n_rej=514, n_fire=2741, Δ_stop=-0.0549, Δ_cushion=0.0610
  - h2: n_rej=890, n_fire=3795, Δ_stop=-0.0086, Δ_cushion=0.0051

**126d Context** (not verdict-grade; n_rej=1,404, n_fire=6,536):
  Rejection: STOP=0.589, DEAD=0.001, CUSH=0.051, LIFT=0.359
  Fired:     STOP=0.598, DEAD=0.001, CUSH=0.040, LIFT=0.361

### board_rank_cutoff — **KEEP**
*No significant axis at q≤0.10 (KEEP by default)*

| Horizon | Cohort | STOP | DEAD | CUSH | LIFT | n |
|---|---|---|---|---|---|---|
| 21d | Rejection | 0.399 (0.383) | 0.153 | 0.107 | 0.341 (0.326) | 2,676 |
| 21d | Fired (matched) | 0.387 (0.378) | 0.164 | 0.127 | 0.322 (0.313) | 7,341 |
| 63d | Rejection | 0.558 (0.542) | 0.010 | 0.121 | 0.311 (0.297) | 2,676 |
| 63d | Fired (matched) | 0.558 (0.548) | 0.007 | 0.144 | 0.291 (0.283) | 7,341 |

**Deltas and p-values:**

| Horizon | Axis | Δ | raw_p | BH_q | Significant |
|---|---|---|---|---|---|
| 21d | stop_out | +0.011 | 0.7510 | 1.0000 | no |
| 21d | dead_money | -0.011 | 0.5671 | 1.0000 | no |
| 21d | cushion | -0.020 | 0.4749 | 1.0000 | no |
| 21d | clean_lift | +0.020 | 0.7670 | 1.0000 | no |
| 63d | stop_out | -0.000 | 0.9940 | 1.0000 | no |
| 63d | dead_money | +0.003 | 0.5084 | 1.0000 | no |
| 63d | cushion | -0.023 | 0.4821 | 1.0000 | no |
| 63d | clean_lift | +0.020 | 0.7437 | 1.0000 | no |

**Sign stability:** UNSTABLE or THIN
  - h1: n_rej=1278, n_fire=3341, Δ_stop=0.0760, Δ_cushion=-0.0135
  - h2: n_rej=1398, n_fire=4000, Δ_stop=-0.0439, Δ_cushion=-0.0257

**126d Context** (not verdict-grade; n_rej=2,676, n_fire=7,341):
  Rejection: STOP=0.595, DEAD=0.000, CUSH=0.031, LIFT=0.373
  Fired:     STOP=0.610, DEAD=0.001, CUSH=0.039, LIFT=0.350

### event_blackout — **INCONCLUSIVE**
*Reason not present in replay data (0 rows)*

Reason not present in replay data. Counted in BH family (m=72) as INCONCLUSIVE.

### cohort_null — **INCONCLUSIVE**
*Reason not present in replay data (0 rows)*

Reason not present in replay data. Counted in BH family (m=72) as INCONCLUSIVE.

## board_rank_unresolved — DESCRIPTIVE ONLY

Per §APPROVAL clause 4, board_rank_unresolved rows (11,069 fires) receive
descriptive treatment only. No keep/demote/flip verdict is issued for this reason.

| Metric | Value |
|---|---|
| n (verdict_grade fires) | 11,069 |
| STOPPED rate (state_15_126) | 0.663 |
| CLEAN_LIFTOFF rate | 0.291 |
| CUSHIONED rate | 0.045 |
| DEAD_MONEY rate | 0.001 |

## Survivor-Stamped Context Appendix

**PRE-2021 / SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE.**

survivor-biased panel: 31.3% of member-months lack price history for this era;
delisted-name recall is unverified; results are CONTEXT-ONLY, not verdict-grade.

All rows in replay_boarded.parquet have survivor_bias=False (unstamped), so there are
no stamped rows to route to this appendix from the canonical input. The effective verdict
window starts 2022-06-30 (after the 250-bar MTF warmup from the 2021-07-06 Massive boundary).

## P2.2 Candidate List

No gates reached DEMOTE-TO-PENALTY or FLIP verdict. All testable gates: KEEP or INCONCLUSIVE.

## BH Family Audit

| Parameter | Value |
|---|---|
| m (registered before run) | 72 |
| Valid p-values computed | 40 |
| Significant at q≤0.1 | 0 |
| q threshold | 0.1 |
| Bootstrap draws B | 10,000 |

Top 20 most significant raw p-values:

| raw_p | trial |
|---|---|
| 0.4749 | board_rank_cutoff/21d/cushion |
| 0.4763 | knife_demote/21d/dead_money |
| 0.4789 | sector_cap_displaced/21d/dead_money |
| 0.4799 | extension_demote/21d/dead_money |
| 0.4818 | knife_demote/63d/cushion |
| 0.4821 | board_rank_cutoff/63d/cushion |
| 0.4836 | extension_demote/21d/clean_lift |
| 0.4842 | extension_demote/63d/clean_lift |
| 0.4854 | knife_demote/21d/cushion |
| 0.4864 | knife_demote/21d/clean_lift |
| 0.4878 | extension_demote/63d/stop_out |
| 0.4884 | sector_cap_displaced/21d/stop_out |
| 0.4895 | sector_cap_displaced/63d/cushion |
| 0.4906 | knife_demote/63d/clean_lift |
| 0.4929 | sector_cap_displaced/63d/clean_lift |
| 0.4948 | extension_demote/21d/stop_out |
| 0.4964 | sector_cap_displaced/21d/clean_lift |
| 0.4973 | sector_cap_displaced/21d/cushion |
| 0.5008 | knife_demote/63d/stop_out |
| 0.5025 | knife_demote/63d/dead_money |

## Leak Audit

- **Fill rule:** entry = first close strictly after signal_date (next-bar convention, T+1).
- **Date mapping:** signal_date = signal bar T; fill bar = T+1.
- **No forward-looking features:** all features (align_tier, sector, rejection_reason,
  board_reason, state_*) are frozen to replay columns stamped at T, not T+1 or later.
- **Episode cluster window:** 21 trading days, non-overlapping, from ERA_START (2022-06-30).
- **gics_sector (sector column) disclosure:** used as a matching key; the sector value is the
  replay-frozen signal-time sector label. GICS reclassifications are historically non-PIT in
  many stores; this disclosure confirms the sector label is the replay-frozen signal-time value.
  Any post-signal GICS reclassification that silently re-pools cohorts would constitute a
  matching-key leak.
- **board_rank_unresolved:** these fires are included in the fired matching pool for board-level
  demotion comparisons (extension_demote / knife_demote / sector_cap_displaced), but they
  never receive a keep/demote/flip verdict themselves (§APPROVAL clause 4).
