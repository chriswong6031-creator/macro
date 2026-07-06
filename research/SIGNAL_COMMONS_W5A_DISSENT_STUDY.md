# W5a — Committee-Dissent Study (Signal Commons)

**Wave:** W5(a) of the Signal Commons program. **Status:** SHIPPED as a research memo (display-only). **Epistemics:** pre-registered before outcomes examined; nulls printed; no result is "validated" (CI-enforced word). Adversarially stats-checked (full pipeline independently reproduced from spine_index.parquet); two descriptive figures corrected post-check, listed under Deviations. No inference-bearing number changed on correction.

---

## Part A — Pre-registration (locked before outcome analysis)

PRE-REGISTRATION — "Committee Dissent: do unanimous co-firing calls grade differently from contested ones?" (locked BEFORE any outcome/outcome_excess analysis; only direction, engine, as_of, symbol, horizon, size_binding, graded/coverage counts were inspected while designing).

DATA: data/neuralweb/spine_index.parquet (main checkout), 287,004 rows.

UNIT DEFINITIONS
- A "call" = one directional engine's signal on one (symbol, as_of), collapsed across horizon rows (a call keeps a single sign; 6/3601 calls have horizon-varying sign and are dropped as ambiguous).
- Directional-engine universe = all rows with engine != 'track_record' AND direction != 0. RATIONALE (pre-registered exclusions, justified from structure not outcomes): (a) 'track_record' is the outcome-grading ledger, not a firing engine — 277,030 rows, direction always coded +1, families buy/sell/cut/rebuy, spanning 1962→2026; it does not represent a committee vote and would swamp the sample. (b) Non-directional engines (china_news, us_importance_v0[_pit], cn_importance_v0[_pit], placebo, and the 812/342 direction==0 rows) carry direction==0 and cannot contribute to a direction-agreement metric per the task spec ("agreement over direction among direction!=0 rows").

CO-FIRING WINDOW
- Window = 0 trading days (same as_of). JUSTIFICATION: the directional-engine corpus spans only 2026-06-15 → 2026-07-03 (19 calendar days); engines stamp on a shared daily as_of grid, so same-day is the natural co-firing key and avoids double-counting a single engine across adjacent dates. A pre-registered robustness widen to ±5 calendar days is permitted for the co-firing COUNT diagnostic ONLY (not for a second inference pass).

AGREEMENT METRIC
- Over a co-firing cell (symbol, as_of) with k>=2 directional calls: agreement = |sum(sign(direction))| / k  (1.0 = unanimous, 0 = even split). Direction==0 rows already excluded.

BUCKETS (declared from the FEASIBLE distribution actually inspected)
- Inspected distinct-directional-engines-per-(symbol,as_of): {1: 3471, 2: 65}. MAXIMUM is 2. No cell has >=3 directional engines at window=0 (and only 1 cell reaches 3 even at ±5 days). Therefore the task's requested "unanimous n>=3 / majority / split" buckets are INFEASIBLE — n>=3 is empty. The only feasible partition is:
    * UNANIMOUS = k==2 co-firing cells with agreement==1  (both engines same sign).
    * CONTESTED = k==2 co-firing cells with agreement==0  (opposite signs).
  Inspected counts: 55 unanimous cells, 10 contested cells (65 total co-firing cells). No majority bucket exists (impossible at k==2).

OUTCOME
- Graded outcome_excess, restricted to rows with outcome_graded==True. Grading is mature ONLY at horizon==5 (h5 87% graded; h10 41%; h21/63/126 ~0% because data is <=19 days old). Therefore outcome analysis is horizon==5 ONLY. Feasible gradeable pool: 102 h5 rows over 52 symbol-dates (45 unanimous, 7 contested).

INFERENCE
- Primary estimand: mean(outcome_excess | unanimous) − mean(outcome_excess | contested) at horizon 5.
- Uncertainty: cluster bootstrap resampling CLUSTERS = (symbol, as_of) cells (not rows), 10,000 resamples, 95% percentile CI. Point estimate + CI reported for each bucket mean and the difference.

PRE-STATED CUTS (the ONLY subgroups that may be reported; no others)
1. By horizon class: DEGENERATE — only horizon==5 is gradeable, so this cut collapses to a single cell and is reported as "not evaluable (single horizon)".
2. By size_binding: inspected split on gradeable co-firing rows = {False: 83, True: 19}. Report unanimous−contested within size_binding==False only IF n-floors met; size_binding==True (19 rows) is below floor and reported as null/undefined.

N-FLOORS (pre-committed)
- Minimum per bucket for a reported difference: >=20 clustered symbol-dates per bucket AND >=8 clusters in the smaller bucket. Contested bucket has 7 graded clusters — BELOW FLOOR. Consequence: the primary difference is reported as UNDER-POWERED / display-only-with-null; no point estimate is escalated, no CI is interpreted as evidence. Every subgroup below floor prints "undefined (n<floor)".

NULL-PRINT RULE
- All results printed regardless of sign or significance; nulls and below-floor cells are printed, never hidden. as_of == today (and any as_of whose horizon-5 window has not fully matured) grades to UNDEFINED, not to a value. No result may use the CI-enforced word "validated". LLM/agent may only de-escalate; this prereg originates no score or escalation.
---

## Part B — Executed study (final, post stats-check)

## Committee Dissent Study — UNDER-POWERED (contested n=7, below pre-registered floor of 8 clusters)

**Pre-registration status:** Analysis executed per locked pre-registration with one corrected figure noted under Deviations. All numbers reported regardless of sign or magnitude. No result is "validated" (CI-enforced restriction).

---

### Setup and Data

Source: `data/neuralweb/spine_index.parquet`, 287,004 rows (main checkout, read-only).

**Exclusions applied (pre-registered):**
- `engine == 'track_record'` removed: 277,030 rows. This ledger is the outcome-grading layer, not a directional vote; its direction is always +1 regardless of the actual call.
- `direction == 0` removed: 5,306 rows (china_news, us_importance_v0, us_importance_v0_pit, cn_importance_v0, cn_importance_v0_pit, placebo, policy [4 of 13 policy rows have direction==0 and are removed here; the remaining 9 policy rows with direction!=0 are retained in the directional universe], and miscellaneous).

**Remaining directional-engine rows:** 4,668 rows across 9 engines (radar, cn_board, us_board, altdata, ca_board, hk_board, policy, desk:ai_desk, altdata_conv). as_of range: 2026-06-15 → 2026-07-03 (19 calendar days).

---

### Step 1 — Calls (collapse to one sign per engine × symbol × as_of)

**Ambiguous calls (horizon-varying sign within one engine):** 6 calls dropped.
- XLP 2026-06-30 (radar), XLP 2026-07-02 (radar), XLU 2026-06-30 (radar), XLV 2026-06-28/29/30 (radar).

**Clean calls retained:** 3,595 (engine × symbol × as_of triples with a single unambiguous direction).

---

### Step 2 — Co-Firing Cells (window = 0 trading days, same as_of)

| k (distinct engines per symbol-date) | Cells |
|---|---|
| 1 | 3,465 |
| 2 | 65 |

**Maximum k = 2.** The pre-registered "unanimous n≥3 / majority / split" three-bucket design is **INFEASIBLE** — no cell reaches k≥3 at window=0. Only the two-bucket partition is possible.

**Robustness diagnostic at ±5 calendar days (count only, no inference):** maximum k rises to 3; the adversarial reproduction gives **37 anchor-rows / 10 distinct symbols** reaching k≥3 within ±5 calendar days (both units stated because the count is unit-definition-dependent: anchor-cell-level vs. symbol-level give different numbers). See Deviations from Pre-Registration for correction of the pre-registered figure. This confirms the co-firing corpus is very thin at same-day resolution.

**Feasible buckets (all 65 co-firing cells):**

| Bucket | Definition | Cells |
|---|---|---|
| UNANIMOUS | k=2, agreement=1.0 (both engines same direction) | 55 |
| CONTESTED | k=2, agreement=0.0 (engines opposite direction) | 10 |

---

### Step 3 — Outcome Availability (horizon=5 only)

Horizon grading rates in the directional subset:
- h5: 87.2% graded (1,846 / 2,117 rows) — **used for outcome analysis**
- h10: 41.5% graded — excluded per pre-registration
- h21/63: 0% / ~0% graded — excluded per pre-registration

**Gradeable co-firing pool (after joining co-firing cells with directional h5 graded rows):**

| Bucket | Rows (engine-level) | Clusters (symbol-date cells) |
|---|---|---|
| UNANIMOUS | 89 | 45 |
| CONTESTED | 13 | 7 |
| **Total** | **102** | **52** |

**size_binding attribution within gradeable co-firing clusters:**

size_binding varies within 18 of 52 gradeable clusters, so a clean cluster-level split is ill-defined. Reported under two attribution rules for auditability:

| Attribution rule | Unanimous clusters | Contested clusters |
|---|---|---|
| All-False (cluster's rows are all size_binding=False) | 45 | 7 |
| Any-True (cluster has at least one size_binding=True row) | 17 | 2 |

The row-level split is unambiguous and reproduces exactly: size_binding=False: 83 rows; size_binding=True: 19 rows.

Both size_binding subgroups are below the n-floor regardless of attribution rule (see Step 4).

---

### Step 4 — N-Floor Check (pre-committed: ≥20 clusters per bucket AND ≥8 clusters in the smaller bucket)

| Check | Unanimous | Contested |
|---|---|---|
| Clusters | 45 ✓ | 7 **✗ (below floor of 8)** |
| Floor passed? | Yes | **No** |

**Consequence (pre-registered):** The primary difference is **UNDER-POWERED / display-only**. No point estimate is escalated. No CI is interpreted as evidence.

size_binding=False subgroup: contested n=7 — also **BELOW FLOOR → undefined (n<floor)**.

size_binding=True subgroup: contested n=2 (any-True rule) or n=0 (all-True rule) — **undefined (n<floor)** under either attribution.

---

### Step 5 — Descriptive Results (display-only; no inferential weight)

**Cluster-level outcome_excess (mean outcome_excess per symbol-date cell, horizon=5):**

| Bucket | n clusters | Mean outcome_excess | Std |
|---|---|---|---|
| UNANIMOUS | 45 | −0.0021 | 0.0671 |
| CONTESTED | 7 | −0.0233 | 0.0799 |

**Point estimate (unanimous − contested):** +0.0211 (display-only; contested n<floor)

**Cluster bootstrap (10,000 resamples, 95% percentile CI):**

| Quantity | Estimate | 95% CI |
|---|---|---|
| Unanimous mean | −0.0021 | [−0.0216, +0.0169] |
| Contested mean | −0.0233 | [−0.0791, +0.0297] |
| Difference (U−C) | +0.0211 | [−0.0346, +0.0804] |

**The CI for the difference spans zero and is anchored to 7 contested clusters. It is display-only and carries no inferential weight per the pre-registered floor rule.**

**Contested cell inventory (all 7 graded clusters):**

| Symbol | as_of | outcome_excess | size_binding |
|---|---|---|---|
| ACLS | 2026-06-22 | +0.026 | False |
| ASPI | 2026-06-26 | −0.023 | False |
| CLSK | 2026-06-22 | −0.108 | False |
| CLSK | 2026-06-24 | −0.142 | False |
| UROY | 2026-06-22 | −0.039 | False |
| VRTX | 2026-06-24 | +0.062 | False |
| YOU | 2026-06-22 | +0.061 | False |

Note: both unanimous and contested bucket means are negative (−0.0021 and −0.0233 respectively), indicating the h5 co-firing cohort had mild negative excess return on average over this 19-day window. This is a display-only observation with no inferential claim attached.

---

### Pre-Stated Cuts

1. **By horizon class:** DEGENERATE — only h5 is gradeable. Reported as "not evaluable (single horizon)."
2. **By size_binding=False:** contested n=7 → **undefined (n<floor)**.
3. **By size_binding=True:** contested n=2 (any-True) or n=0 (all-True) → **undefined (n<floor)** under either attribution rule.

---

### Deviations from Pre-Registration

1. **Corrected pre-registered figure — ±5-day robustness count:** The locked pre-registration (CO-FIRING WINDOW + BUCKETS sections) stated "only 1 cell reaches 3 even at ±5 days." The original memo draft reported "33 cells reach k≥3." These are mutually exclusive and neither is reproducible as stated. The adversarial reproduction gives the authoritative count: **37 anchor-rows / 10 distinct symbols** reach k≥3 within ±5 calendar days. Both units are stated explicitly because the count is unit-definition-dependent (anchor-cell-level vs. symbol-level produce different numbers). This is a count-only diagnostic; no inference depends on it. The pre-registered figure is hereby corrected to the reproduced value.

---

### In Plain English

The dashboard's directional engines almost never fire on the same stock on the same day — only 65 out of 3,530 stock-date combinations had two engines co-fire, and none had three. Of those 65 pairs, 55 agreed (both engines pointed the same way) and 10 disagreed. When we look at five-day forward returns for the subset that had mature outcomes, the unanimous pairs showed near-zero average excess return (−0.2%) and the contested pairs showed slightly more negative returns (−2.3%), giving a raw gap of about +2.1 percentage points in favour of unanimity. However, there were only 7 contested clusters — one below the pre-registered threshold of 8 required to report a finding — so by the study's own rules this gap is display-only and carries no evidential weight. The confidence interval runs from −3.5% to +8.0%, straddling zero comfortably. The honest answer is: we do not yet have enough contested co-firings in the system to test this hypothesis. The corpus needs more time (or more engines) before a powered study is possible.

---

### Re-run Condition (pre-registered)

This study re-runs, under the same pre-registration without modification, once the contested bucket reaches **≥8 graded clusters** at horizon=5. At current accrual (7 contested graded clusters over 19 calendar days of directional-engine data), one additional graded contested cluster is needed. As directional co-firing accrues, this threshold is expected to be crossed; the exact timing depends on the rate at which new contested co-firing cells mature through the h5 grading window. No new pre-registration is required — the existing locked pre-registration governs the re-run in full.
