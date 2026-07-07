# Construction-Divergence R-1 TC Re-Check

**RE-CHECK (descriptive/accrual) — the R-1 lock stands as shipped; adjudication pending (Fable). No key ships from this document.**

**Generated:** 2026-07-07T11:52:00.387802+00:00  
**Git SHA:** edb745d18a959d00c4416cffa33428a9367b8dc0  
**Script:** scripts/study_construction_divergence_tc.py  
**Original script (unchanged):** scripts/study_construction_divergence.py  
**Registration:** research/HEALTHCARE_MEMBER_DISPERSION_ROTATION_NOTE.md §12 (LOCKED)  
**Audit authority:** research/TIME_CONFOUND_EXPOSURE_AUDIT.md §7 item 6 (HC-RC-1)

---

## Repairs Applied (CD-1/CD-2/CD-3)

| Defect | Original | This script |
|---|---|---|
| CD-1: event ordering | Concatenated sector-pair by sector-pair (positional) | Globally sorted by real calendar date |
| CD-2: block collapse | Keyed on per-sector `bar_i`; block_counts reported only, never fed to any statistic | Real calendar-date proximity (±7 calendar days, transitive chaining); blocks used as resampling unit |
| CD-3: ablations | Within-unit permutations (powerless vs time confound) | Retained as reference only; primary inference is now block-cluster bootstrap |

## Reproduction Gate

| Field | This run | Target | Tolerance | OK |
|---|---|---|---|---|
| n_div | 315 | 315 | ±6 | YES |
| n_con | 485 | 485 | ±6 | YES |
| div DD21 median | -2.324% | -2.32% | ±0.15pp | YES |
| con DD21 median | -2.559% | -2.56% | ±0.15pp | YES |
| **Overall gate** | | | | **PASS** |

## Block Structure (CD-2 repaired)

Events were sorted by real date then grouped into ±7 calendar-day co-firing blocks (transitive chain anchored at block's first event).

| Metric | Value |
|---|---|
| Total blocks | 419 |
| Mean events/block | 1.91 |
| Max events in one block | 6 |
| Blocks with 1 event (singleton) | 171 |
| Blocks with >1 event | 248 |
| Block size histogram | {"size_1": 171, "size_2": 148, "size_3": 76, "size_4": 17, "size_5": 5, "size_6": 2} |

## Raw Cohort Statistics (unchanged from original)

### DD 21d

| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |
|---|---|---|---|---|---|---|
| divergent | 314 | -3.1 | -2.32 | -8.23 | -4.25 | 0.105 |
| confirmed | 483 | -3.37 | -2.56 | -8.16 | -4.92 | 0.112 |

### DD 63d

| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |
|---|---|---|---|---|---|---|
| divergent | 312 | -5.31 | -3.48 | -12.35 | -6.9 | 0.224 |
| confirmed | 480 | -6.17 | -4.19 | -15.12 | -8.51 | 0.265 |

## Side-by-Side: Original vs TC-Repaired (Primary Contrast)

| | Original (pooled iid t) | TC-Repaired (block-cluster bootstrap) |
|---|---|---|
| DD21 raw contrast (div−con mean) | 0.27% | 0.267% |
| DD21 t-raw | 0.947 | n/a (bootstrap CI reported) |
| DD21 95% CI | n/a (iid SE only) | [-0.26%, 0.831%] |
| DD21 two-sided p (block-boot) | n/a | 0.339 |
| DD21 shuffle percentile | 72.7th | n/a (different test) |
| DD63 raw contrast (div−con mean) | 0.85% | 0.852% |
| DD63 95% CI | n/a | [-0.074%, 1.836%] |
| DD63 two-sided p (block-boot) | n/a | 0.072 |
| DD63 shuffle percentile | 89.8th | n/a (different test) |
| n blocks used | (decorative only, CD-2) | 419 |

## Stress-Stratified Block-Bootstrap Contrast (the load-bearing readout)

> The audit flagged DD63-under-stratification as the live false-null candidate.
> Original report showed div p10 −12.35 vs con −15.12 at 63d.

### DD 21d — by Stress Stratum

| Stratum | n_div | n_con | n_blocks | div mean | con mean | contrast | 95% CI | p |
|---|---|---|---|---|---|---|---|---|
| stress | 42 | 74 | 74 | -4.761% | -5.542% | 0.782% | [-1.376%, 2.928%] | 0.466 |
| calm | 272 | 409 | 356 | -2.844% | -2.973% | 0.129% | [-0.396%, 0.657%] | 0.606 |

### DD 63d — by Stress Stratum

| Stratum | n_div | n_con | n_blocks | div mean | con mean | contrast | 95% CI | p |
|---|---|---|---|---|---|---|---|---|
| stress | 42 | 74 | 74 | -8.373% | -8.818% | 0.445% | [-3.069%, 3.804%] | 0.774 |
| calm | 270 | 406 | 356 | -4.837% | -5.682% | 0.845% | [-0.126%, 1.851%] | 0.103 |

### Tail Contrasts (p10 of DD within cohort, block-bootstrap CIs)

| Horizon | obs div p10 | 95% CI | obs con p10 | 95% CI | obs contrast |
|---|---|---|---|---|---|
| DD21 | -8.227% | [-9.232%, -6.387%] | -8.158% | [-9.315%, -7.43%] | -0.069% |
| DD63 | -12.353% | [-15.88%, -10.276%] | -15.122% | [-16.753%, -13.215%] | 2.769% |

## Nulls and Caveats

- All results are descriptive. The R-1 lock (no de-escalation key) stands until Fable adjudicates.
- 'Positive contrast' = divergent has SHALLOWER DD than confirmed (early-exit direction).
- Block-bootstrap CIs that include zero indicate the contrast is within the noise of co-firing macro episodes.
- Stress stratum has limited blocks; treat stress-stratum CIs with caution if n_blocks < 15.
- DD63 tail numbers for calm stratum carry the most events; stress-stratum DD63 is the hypothesized signal.
- The word 'signal' is used descriptively. No promotion or de-escalation key is implied.

---

*Run by scripts/study_construction_divergence_tc.py | SHA edb745d18a959d00c4416cffa33428a9367b8dc0 | 2026-07-07*