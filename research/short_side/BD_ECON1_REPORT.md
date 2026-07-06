# BD-ECON-1 — Avoided-Loss / Missed-Upside Counterfactual

**Generated:** 2026-07-06T14:31:54.145451+00:00
**Derived from surface:** `bd_phase0`
**Authority:** `research/short_side/BD_ECON1_PREREG.md` (FROZEN)
**Status:** research-only; no live authority, no board/chip/gate consumer

## In plain English

When our breakdown-event detector (BD-2 or BD-3) fires on a stock, it opens a 21-trading-bar 'avoid window'. This study asks: of all the board fires (entries) our system recorded during those avoid windows, how many ended badly — and of the ones we would have skipped, how much upside would we have missed? Both sides are printed with equal prominence because a skip policy that avoids some losses also misses some gains.

**Three contrasts were pre-registered:**
- **C1**: BD-2-flagged fires vs all unflagged fires
- **C2**: BD-3-flagged fires vs all unflagged fires
- **C3 (co-primary)**: BD-2-flagged fires vs fires following a recent stop *without* an active BD-2 window — isolates BD-2's increment over generic post-stop damage.

A C1 delta that vanishes in C3 means BD-2's board value is **redundant with recent-stop** — that null is a first-class printed outcome.

## Sample sizes (printed before statistics, per prereg)

| Source | Count |
|---|---|
| BD-2 episodes in events tape | 19,891 |
| BD-3 episodes in events tape | 5,553 |
| ERA-LAW fires (verdict_type=fire, verdict_grade=True) | 49,939 |
| Fires flagged by both BD-2 and BD-3 (overlap) | 1,772 |

## Trial ledger (RUL-U3a)

- Family: `short_side`
- Declared budget: 6 (within-study BH floor; max()-semantics per RUL-U3a)
- Literal n (cross-study): 6
- **max()-basis divergence note:** declared_budget is a per-family max() floor; literal_n accumulates all BD-family study cells cross-study. Both are printed here per the #1664 §0.5.6 convention.

## Feasibility-peek disclosure (prereg §Amendments)

Feasibility peek disclosed in BD_ECON1_PREREG.md §Amendments: coarse floors-feasibility join run before commit confirmed floors met and revealed coarse pooled magnitudes; no gate/threshold was changed.
No gate, threshold, or endpoint in the prereg was changed in response.

## BD-2 Results

- Flagged fires: 25,275
- Contributing episodes: 7,228
- Unflagged fires (contrast arm): 24,664

### C1 — Flagged vs All Unflagged

**Endpoint (a) — Stop-rate delta at h21:**
- Flagged stop rate: 39.2%
- Unflagged stop rate: 37.3%
- Delta (flagged − unflagged): 0.0190
- 95% CI: [-0.0557, 0.1041]
- CI excludes zero: False
- n flagged: 25,275 | n unflagged: 24,664
- Censored (NaN state): flagged=0 unflagged=0

**Endpoint (b) — fwd_ret_21 delta (economics endpoint):**
- Mean fwd_ret_21 flagged: 0.02094
- Mean fwd_ret_21 unflagged: 0.01754
- Delta (flagged − unflagged): 0.00339
- 95% CI: [-0.01870, 0.02503]
- CI excludes zero: False
- Censored (NaN fwd_ret_21): flagged=0 unflagged=0

### C3 (co-primary) — BD-2 Flagged vs Recent-Stop-Without-BD

- Recent-stop cohort size: 1,966
**Endpoint (a) — Stop-rate delta:**
- Delta (BD-2 flagged − recent-stop): 0.0171
- 95% CI: [-0.0781, 0.1166]
- CI excludes zero: False
**Endpoint (b) — fwd_ret_21 delta:**
- Delta (BD-2 flagged − recent-stop): -0.00072
- 95% CI: [-0.02848, 0.02780]
- CI excludes zero: False

**C3 interpretation**: if C1 delta is real but C3 delta ~0, BD-2 adds nothing beyond 'the name just stopped' (INCREMENT-NULL). If C3 also real, BD-2 has board value beyond generic post-stop damage.

### Economics block (§4 — arithmetic on flagged cohort)

*n flagged stopped: 9907 | n flagged clean: 8178*

**Avoided drawdown (§4a) — fwd_mdd_21 among flagged fires that STOPPED:**
- n: 9,907 | mean: -0.1102 | median: -0.0912 | p90: -0.0566

**Missed upside (§4b) — fwd_ret_21 among flagged fires that ended CLEAN:**
- n: 8,178 | mean: 0.1117 | median: 0.1009 | p10: 0.0275

**Missed MFE (§4b) — fwd_mfe_21 among flagged fires that ended CLEAN:**
- n: 8,178 | mean: 0.1532 | median: 0.1308 | p10: 0.0879

Avoided drawdown (§4a) and missed upside (§4b) printed with equal prominence per RUL-N6 symmetric-cost law.

**Skip-policy net read (§4c) — re-presents budgeted ep_b CI:**
- Re-presentation of budgeted endpoint-(b) CI: mean fwd_ret_21(unflagged) minus mean fwd_ret_21(flagged). Positive = unflagged fires had higher forward return; negative = flagged fires did better. No new test computed.
- Delta (flagged − unflagged): 0.00339
- 95% CI: [-0.01870, 0.02503]

## BD-3 Results

- Flagged fires: 3,457
- Contributing episodes: 1,152
- Unflagged fires (contrast arm): 46,482

### C2 — Flagged vs All Unflagged

**Endpoint (a) — Stop-rate delta at h21:**
- Flagged stop rate: 42.1%
- Unflagged stop rate: 38.0%
- Delta (flagged − unflagged): 0.0412
- 95% CI: [-0.0570, 0.1449]
- CI excludes zero: False
- n flagged: 3,457 | n unflagged: 46,482
- Censored (NaN state): flagged=0 unflagged=0

**Endpoint (b) — fwd_ret_21 delta (economics endpoint):**
- Mean fwd_ret_21 flagged: 0.01273
- Mean fwd_ret_21 unflagged: 0.01975
- Delta (flagged − unflagged): -0.00702
- 95% CI: [-0.03293, 0.01491]
- CI excludes zero: False
- Censored (NaN fwd_ret_21): flagged=0 unflagged=0

### Economics block (§4 — arithmetic on flagged cohort)

*n flagged stopped: 1455 | n flagged clean: 1023*

**Avoided drawdown (§4a) — fwd_mdd_21 among flagged fires that STOPPED:**
- n: 1,455 | mean: -0.1092 | median: -0.0862 | p90: -0.0556

**Missed upside (§4b) — fwd_ret_21 among flagged fires that ended CLEAN:**
- n: 1,023 | mean: 0.1000 | median: 0.0933 | p10: 0.0130

**Missed MFE (§4b) — fwd_mfe_21 among flagged fires that ended CLEAN:**
- n: 1,023 | mean: 0.1491 | median: 0.1251 | p10: 0.0869

Avoided drawdown (§4a) and missed upside (§4b) printed with equal prominence per RUL-N6 symmetric-cost law.

**Skip-policy net read (§4c) — re-presents budgeted ep_b CI:**
- Re-presentation of budgeted endpoint-(b) CI: mean fwd_ret_21(unflagged) minus mean fwd_ret_21(flagged). Positive = unflagged fires had higher forward return; negative = flagged fires did better. No new test computed.
- Delta (flagged − unflagged): -0.00702
- 95% CI: [-0.03293, 0.01491]

## BH correction (declared 6-cell set, q=0.10)

| Cell | p (approx) | BH threshold | Reject H0 |
|---|---|---|---|
| BD-3_C2_ep_a | 0.4241 | 0.0167 | No |
| BD-3_C2_ep_b | 0.5651 | 0.0333 | No |
| BD-2_C1_ep_a | 0.6404 | 0.0500 | No |
| BD-2_C3_ep_a | 0.7306 | 0.0667 | No |
| BD-2_C1_ep_b | 0.7612 | 0.0833 | No |
| BD-2_C3_ep_b | 0.9600 | 0.1000 | No |

*Approximate BH correction; p estimated from CI half-width assuming normal approximation. CI-excludes-zero is the primary verdict; this BH table is supplemental.*

## What this does NOT show (prereg §6)

No live tradability claim; no forward verdict (BD-AVOID-1 owns the forward question); no short-side claim of any kind; no per-name signal; nothing feeds any board, gate, chip, alert, or score.

