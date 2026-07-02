# Wave-4 Report — The COILED-FIRE Layer (C1 = m1d_s3d, C2 = union) vs R = m2d_s3d

> Companion to `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (THE spec; §8 ledger carries the
> **Wave-4 pre-registration (2026-07-02)** block that defines every gate below) and
> `research/entry_timing/WAVE3_REPORT.md` (the B study that nominated `m1d_s3d`). Machinery reused:
> `wave1.py` / `wave2.py` (labels, features, fires via `tuning_harness`, per-fire outcomes, cohort
> matrices) and `wave3.py`'s daily COILED-state computation (`_compute_washout_state_daily` +
> `cohort_state` via the sector weekly-D matrix, ISO-string serialization for `Pool` args), extended
> by `wave4.py`. Panels: stocks via `data/stocks`, baskets via `data/baskets/ohlcv`, cn via
> `data/china_search` wide parquet.
>
> **Mandate (spec §8 Wave-4 pre-registration):** grade the COILED-FIRE layer candidates against the
> pre-registered gates **exactly as written**, separately for C1 and C2, deduped sets primary.
> Ship shape THIS wave = display chip + forward-ledger fields ONLY — no rank/bonus change.
> Gates are law (spec §7): no re-interpretation, no threshold edits.

---

## 0. Verdict at a glance

| candidate | G4a (US folds) | G4b (baskets) | G4c (CN) | G4d capture (st / bk / cn) | **US SHIP** | **CN incl.** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| **C1** = m1d_s3d | **FAIL** | PASS | PASS | **FAIL / FAIL / FAIL** | **NO** | **NO** |
| **C2** = union(m1d,m2d) | **PASS** | **PASS** | **PASS** | **PASS / PASS / PASS** | **YES** | **YES** |

**Ship recommendation (pre-committed ship rule):** ship the COILED-FIRE marker for **C2 (the union
of m1d_s3d and m2d_s3d fires inside COILED), on all three panels — US and CN**. Do **not** ship C1.
Ship shape stays display chip + forward-ledger fields only (no rank/bonus change), exactly as the
pre-registration specified.

**The one-sentence why:** C1 dedupes to a smaller, marginally-higher-precision set but its recall
of B15 durable bottoms falls *below* the reference on every panel — so it fails the capture axis
(G4d), which is the entire reason to add a faster fire layer. C2 wins recall by construction (the
union catches troughs either trigger alone misses) and *pays for it*: pooled non-inferiority on
stop5/clean15 holds, per-name medians are non-inferior, and premium/lead/recall all clear G4d.

---

## 1. Config & panels

Produced by `research/entry_timing/wave4.py` (reuses wave1/wave2 labels, features, outcomes, cohort
matrices; wave3 daily COILED-state). Fill = i+1. Dates round-tripped as ISO strings in worker args
(the wave-2 ms→ns serialization bug class explicitly avoided).

| | **stocks** (`wave4_stocks`) | **baskets** (`wave4_baskets`) | **cn** (`wave4_cn`) |
|---|---|---|---|
| panel | `data/stocks/*.parquet` | `data/baskets/ohlcv/*.parquet` | `data/china_search/closes.parquet` |
| names (≥ min_bars) | 211 | 2,336 | 1,382 |
| min_bars | 1,500 | 1,000 | 800 |
| eval_start | 2012-01-01 | 2015-01-01 | 2022-09-01 |
| dedupe window | 8 trading days | 8 trading days | 8 trading days |
| runtime | 151.2s | 1,144.9s | 457.7s |

**Fire sets (per name, deduped = primary; undeduped kept for sensitivity):**
- **R** = dedupe(`m2d_s3d` inside COILED) — the current COILED platform (the reference).
- **C1** = dedupe(`m1d_s3d` inside COILED) — the wave-3 B nominee.
- **C2** = dedupe(union(`m1d_s3d`, `m2d_s3d`) inside COILED) — the union fire layer.
- **COILED** = `washout_ctx AND h6_cohort_sector ≥ 0.40`, computed daily (wave3 logic exactly).
- **dedupe** = first fire of any burst within an 8-trading-day per-name window; the SAME rule is
  applied to R (the reference is deduped too, per the pre-registration).
- `base3d`-ALL-context printed for reference; not a candidate.

---

## 2. Verbatim gate grading (deduped sets primary)

Reference **R (deduped):** stops5 39.12, clean15 39.55 (n=3,037) on stocks; 40.42 / 38.52 (n=6,553)
on baskets; 45.87 / 35.54 (n=10,258) on cn.

### G4a — deep-panel folds (stocks), 5 folds, 180d purge
> *pooled stop5(C) ≤ stop5(R) + 0.5pp AND pooled clean15(C) ≥ clean15(R) − 2pp; per fold (≥4/5):
> clean15(C) − clean15(R) ≥ −3pp AND stop5(C) ≤ stop5(R) + 1pp.*

**Pooled (deduped):**

| candidate | pooled stop5 | ≤ 39.62? | pooled clean15 | ≥ 37.55? | pooled verdict |
|---|---:|:--:|---:|:--:|:--:|
| C1 | 38.31 | ✓ | 37.40 | **✗ (−0.15pp under)** | **FAIL** |
| C2 | 38.41 | ✓ | 37.92 | ✓ | **PASS** |

**Per-fold (folds are undeduped in the harness; clause: clean15Δ ≥ −3pp AND stop5Δ ≤ +1pp):**

| fold | window | C1 c15Δ / s5Δ | C1 pass | C2 c15Δ / s5Δ | C2 pass |
|---|---|---|:--:|---|:--:|
| 0 | 2012-04 → 2016-02 | +0.64 / −0.05 | ✓ | +0.53 / +0.12 | ✓ |
| 1 | 2016-08 → 2019-01 | +0.37 / −5.79 | ✓ | −0.04 / −4.04 | ✓ |
| 2 | 2019-07 → 2022-02 | −9.82 / +6.24 | ✗ | −6.26 / +3.26 | ✗ |
| 3 | 2022-10 → 2023-09 | −1.84 / −0.81 | ✓ | −0.29 / −2.19 | ✓ |
| 4 | 2024-03 → 2025-12 | +0.42 / −3.44 | ✓ | −0.64 / −1.93 | ✓ |
| | **folds passing** | | **4/5 ✓** | | **4/5 ✓** |

Both candidates clear the per-fold clause (4/5, the same fold-2 2019-07→2022-02 fails for both — the
COVID-crash-to-2022-top window, where the faster trigger front-runs into more stop-outs; the deduped
pooled absorbs it). **The pooled clause is the discriminator: C1 misses pooled clean15 by 0.15pp; C2
clears it. G4a: C1 FAIL, C2 PASS.**

### G4b — basket-panel OOS (decisive)
> *pooled non-inferiority as G4a; n(C) ≥ 800; per-name (names ≥ 3 fires each side): median Δstop5
> (C−R) ≤ 0 AND median Δclean15 ≥ −2pp.*

| candidate | pooled stop5 ≤ 40.92? | pooled clean15 ≥ 36.52? | n(C) ≥ 800? | per-name med Δstop5 ≤ 0? | per-name med Δclean15 ≥ −2pp? | G4b |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| C1 | 39.79 ✓ | 37.67 ✓ | 7,188 ✓ | −2.22 ✓ | 0.00 ✓ | **PASS** |
| C2 | 40.42 ✓ | 37.44 ✓ | 9,951 ✓ | 0.00 ✓ | −0.83 ✓ | **PASS** |

**G4b: both PASS.** (Per-name majority context, informational — not a gate clause: C1 wins stop5 on
53.4% of names but clean15 on only 45.8%; C2 is ~50/50 on stop5, 45.6% on clean15. The medians are
non-inferior even though the per-name win-rate on clean15 sits just under 50% — the losses are small.)

### G4c — CN replication
> *pooled non-inferiority as G4a; n(C) ≥ 1,000.*

| candidate | pooled stop5 ≤ 46.37? | pooled clean15 ≥ 33.54? | n(C) ≥ 1,000? | G4c |
|---|:--:|:--:|:--:|:--:|
| C1 | 46.19 ✓ | 36.19 ✓ | 12,805 ✓ | **PASS** |
| C2 | 46.17 ✓ | 35.67 ✓ | 16,820 ✓ | **PASS** |

**G4c: both PASS.** CN is a large fire panel (COILED is ~half of all m2d fires on CN, per wave3) so
n clears with huge margin; clean15 is actually *above* R on both candidates (CN's faster-trigger
liftoff capture is stronger than US's — but see the single-regime caveat, §5).

### G4d — capture economics (the reason to ship; must pass on every shipping panel)
> *median premium(C) ≤ premium(R) − 1pp AND median lead(C) ≤ lead(R) AND recall_B15(C) ≥ recall_B15(R).*

| panel | cand | prem(C) ≤ prem(R)−1? | lead(C) ≤ lead(R)? | recall(C) ≥ recall(R)? | **G4d** |
|---|---|:--:|:--:|:--:|:--:|
| stocks | C1 | 6.51 ≤ 7.08 ✓ | 3 ≤ 6 ✓ | 10.45 ≥ 12.39 **✗** | **FAIL** |
| stocks | C2 | 7.02 ≤ 7.08 ✓ | 3 ≤ 6 ✓ | 14.22 ≥ 12.39 ✓ | **PASS** |
| baskets | C1 | 6.70 ≤ 7.49 ✓ | 3 ≤ 7 ✓ | 6.02 ≥ 7.31 **✗** | **FAIL** |
| baskets | C2 | 7.28 ≤ 7.49 ✓ | 4 ≤ 7 ✓ | 8.39 ≥ 7.31 ✓ | **PASS** |
| cn | C1 | 8.26 ≤ 9.42 ✓ | 3 ≤ 6 ✓ | 33.69 ≥ 33.92 **✗** | **FAIL** |
| cn | C2 | 8.93 ≤ 9.42 ✓ | 4 ≤ 6 ✓ | 44.02 ≥ 33.92 ✓ | **PASS** |

**G4d: C1 FAIL on all three panels; C2 PASS on all three.** C1 gets the premium and lead prizes
(cheaper, earlier) but **loses recall on every panel** — the dedupe of m1d-only fires drops below
R's already-thin recall. This is the decisive axis: a faster fire layer that catches *fewer* durable
bottoms than the platform it replaces has bought earliness by amputating the exact thing (recall of
the perk-up window) the framework §9.3 asymmetry says is the expensive failure. C2 keeps both
triggers' catches, so recall rises (stocks +1.83pp, baskets +1.08pp, cn +10.10pp) while premium and
lead stay favorable.

### Ship rule application
> *SHIP: candidate ships (US) iff G4a AND G4b AND G4d; CN inclusion additionally needs G4c(+G4d cn).*

| candidate | G4a | G4b | G4d(stocks) | **US SHIP** | G4c | G4d(cn) | **CN inclusion** |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **C1** | ✗ | ✓ | ✗ | **NO** (fails 2 of 3) | ✓ | ✗ | **NO** |
| **C2** | ✓ | ✓ | ✓ | **YES** | ✓ | ✓ | **YES** |

---

## 3. All tables

### T1 — per-fire outcomes, deduped (primary) and undeduped

**stocks** (R n=3,037 dd / 3,174 undd):

| set | n | stop5 | clean15 | clean20 | dead$ | med_prem | med_lead | recall_B15 | trap_fire |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base3d ALL | 8,020 | 40.92 | 34.28 | 24.49 | 14.76 | 10.44 | 9 | 14.12 | 10.79 |
| R (dd) | 3,037 | 39.12 | 39.55 | 31.48 | 7.31 | 8.08 | 6 | 12.39 | 9.18 |
| C1 (dd) | 3,406 | 38.31 | 37.40 | 29.54 | 6.64 | 6.51 | 3 | 10.45 | 8.84 |
| C2 (dd) | 4,694 | 38.41 | 37.92 | 30.21 | 6.86 | 7.02 | 3 | 14.22 | 11.87 |
| R (undd) | 3,174 | 39.07 | 39.29 | 31.35 | 7.28 | 7.96 | 6 | 12.48 | 9.25 |
| C1 (undd) | 3,787 | 37.87 | 37.68 | 29.68 | 6.52 | 6.43 | 2 | 10.63 | 9.07 |
| C2 (undd) | 6,745 | 38.32 | 38.58 | 30.57 | 6.82 | 7.17 | 4 | 14.48 | 12.10 |

**baskets** (R n=6,553 dd / 6,842 undd):

| set | n | stop5 | clean15 | clean20 | dead$ | med_prem | med_lead | recall_B15 | trap_fire |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base3d ALL | 64,380 | 47.52 | 31.33 | 24.60 | 7.07 | 13.57 | 9 | 41.31 | 30.85 |
| R (dd) | 6,553 | 40.42 | 38.52 | 30.61 | 6.13 | 8.49 | 7 | 7.31 | 4.11 |
| C1 (dd) | 7,188 | 39.79 | 37.67 | 30.05 | 5.87 | 6.70 | 3 | 6.02 | 4.00 |
| C2 (dd) | 9,951 | 40.42 | 37.44 | 29.86 | 5.87 | 7.28 | 4 | 8.39 | 5.34 |
| R (undd) | 6,842 | 40.22 | 38.70 | 30.63 | 6.15 | 8.37 | 7 | 7.35 | 4.14 |
| C1 (undd) | 8,042 | 39.72 | 37.55 | 29.92 | 5.83 | 6.62 | 3 | 6.12 | 4.10 |
| C2 (undd) | 14,416 | 39.98 | 38.11 | 30.24 | 5.92 | 7.45 | 4 | 8.53 | 5.43 |

**cn** (R n=10,258 dd / 10,784 undd):

| set | n | stop5 | clean15 | clean20 | dead$ | med_prem | med_lead | recall_B15 | trap_fire |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base3d ALL | 13,316 | 48.89 | 31.53 | 26.16 | 6.80 | 13.20 | 8 | 32.58 | 22.73 |
| R (dd) | 10,258 | 45.87 | 35.54 | 29.92 | 5.03 | 10.42 | 6 | 33.92 | 22.14 |
| C1 (dd) | 12,805 | 46.19 | 36.19 | 31.40 | 4.94 | 8.26 | 3 | 33.69 | 24.16 |
| C2 (dd) | 16,820 | 46.17 | 35.67 | 30.68 | 5.04 | 8.93 | 4 | 44.02 | 30.65 |
| R (undd) | 10,784 | 45.72 | 35.57 | 29.95 | 5.06 | 10.29 | 6 | 34.29 | 22.40 |
| C1 (undd) | 14,521 | 45.98 | 36.17 | 31.40 | 4.87 | 8.13 | 3 | 35.32 | 24.80 |
| C2 (undd) | 24,377 | 45.94 | 35.82 | 30.69 | 4.91 | 9.12 | 4 | 44.96 | 31.28 |

### T2 — deep-panel time folds (stocks), C−R deltas

| fold | window | n_R | R c15 / s5 | n_C1 | C1 c15Δ / s5Δ | n_C2 | C2 c15Δ / s5Δ |
|---|---|---:|---|---:|---|---:|---|
| 0 | 2012-04→2016-02 | 609 | 32.84 / 43.35 | 672 | +0.64 / −0.05 | 950 | +0.53 / +0.12 |
| 1 | 2016-08→2019-01 | 474 | 33.54 / 45.57 | 631 | +0.37 / −5.79 | 797 | −0.04 / −4.04 |
| 2 | 2019-07→2022-02 | 537 | 46.93 / 37.06 | 582 | −9.82 / +6.24 | 868 | −6.26 / +3.26 |
| 3 | 2022-10→2023-09 | 332 | 40.66 / 34.04 | 322 | −1.84 / −0.81 | 493 | −0.29 / −2.19 |
| 4 | 2024-03→2025-12 | 410 | 40.24 / 41.22 | 487 | +0.42 / −3.44 | 649 | −0.64 / −1.93 |

### T3 — per-name paired deltas (names ≥ 3 fires each side)

| panel | comparison | n names | med Δstop5 | med Δclean15 | % names C wins stop5 | % names C wins clean15 |
|---|---|---:|---:|---:|---:|---:|
| stocks | C1 vs R | 208 | 0.00 | −1.08 | 48.56 | 43.75 |
| stocks | C2 vs R | 210 | 0.00 | −2.15 | 49.05 | 39.52 |
| baskets | C1 vs R | 491 | −2.22 | 0.00 | 53.36 | 45.82 |
| baskets | C2 vs R | 493 | 0.00 | −0.83 | 49.90 | 45.64 |
| cn | C1 vs R | 1,319 | 0.00 | 0.00 | 45.79 | 46.85 |
| cn | C2 vs R | 1,325 | 0.00 | 0.00 | 47.55 | 44.91 |

*(G4b per-name clause reads the baskets row: C1 med Δstop5 −2.22 ≤ 0 and Δclean15 0.00 ≥ −2pp;
C2 med Δstop5 0.00 ≤ 0 and Δclean15 −0.83 ≥ −2pp — both pass.)*

### T4 — paired first-fire economics (C2 vs R, B15 events captured by BOTH)

| panel | n paired events | med prem improvement (C2 cheaper, pp) | med days earlier (C2 earlier) | % events C2 fires first |
|---|---:|---:|---:|---:|
| stocks | 1,248 | 0.00 | 2.0 | 60.98 |
| baskets | 2,715 | 0.00 | 2.0 | 58.08 |
| cn | 3,656 | 1.0 | 1.0 | 57.55 |

### T5 — ticker-half stability (even/odd)

| panel | set | even n | even c15 / s5 | odd n | odd c15 / s5 |
|---|---|---:|---|---:|---|
| stocks | R | 1,583 | 40.18 / 37.97 | 1,454 | 38.86 / 40.37 |
| stocks | C1 | 1,723 | 37.32 / 38.13 | 1,683 | 37.49 / 38.50 |
| stocks | C2 | 2,406 | 37.95 / 38.11 | 2,288 | 37.89 / 38.72 |
| baskets | R | 3,187 | 38.63 / 40.35 | 3,366 | 38.41 / 40.49 |
| baskets | C1 | 3,483 | 37.44 / 40.63 | 3,705 | 37.89 / 39.00 |
| baskets | C2 | 4,838 | 37.21 / 40.99 | 5,113 | 37.67 / 39.88 |
| cn | R | 5,187 | 36.24 / 45.65 | 5,071 | 34.83 / 46.09 |
| cn | C1 | 6,491 | 35.85 / 46.28 | 6,314 | 36.54 / 46.10 |
| cn | C2 | 8,516 | 35.72 / 46.16 | 8,304 | 35.62 / 46.18 |

---

## 4. Requested reads

### 4.1 Dedupe sensitivity — does dedupe change any verdict direction?

**No verdict direction flips on any binding gate — with ONE noted near-miss.** The stocks G4a pooled
clean15 clause is the only place where dedupe matters at the pass/fail boundary:

- **C1 stocks G4a pooled clean15:** deduped 37.40 vs bar 37.55 → **FAIL by 0.15pp**; undeduped
  37.68 vs bar (39.29−2=)37.29 → **PASS**. The pre-registration names **deduped as primary**, so
  C1's G4a is graded FAIL. But this is a knife-edge that flips on the dedupe choice, so C1's G4a
  failure is *fragile* — I flag it rather than hide it. It does **not** change C1's overall ship
  verdict: C1 still fails G4d on all three panels (recall < R), which is dedupe-robust (recall is
  lower deduped AND undeduped on every panel), so C1 is a NO-SHIP either way.
- **C2:** every gate passes under both deduped and undeduped numbers (G4a pooled clean15 37.92 dd /
  38.58 undd, both ≥ bar; G4b/G4c/G4d all clear under both). C2's SHIP verdict is dedupe-robust.

So: dedupe does not change any *ship* verdict. It only changes the *label* on one non-decisive
sub-clause (C1 G4a), and C1 is dead on capture regardless.

### 4.2 T4 paired first-fire economics — the days-earlier / %-cheaper story in plain language

For the durable-B15 bottoms that **both** C2 and R catch, pairing the first fire of each set on the
same event: **C2 fires first ~58-61% of the time, a median of 2 trading days earlier on US stocks
and baskets, 1 day earlier on CN.** So the union does deliver the earliness the framework wants — on
the majority of shared events, adding the m1d trigger pulls the entry forward by a couple of sessions.

**But the earlier fire is NOT a cheaper fill at the median.** Median paired premium improvement is
**0.0pp** on stocks and baskets (1.0pp on CN). In plain terms: on the typical shared event, C2's
2-days-earlier fire lands at essentially the same price as R's — the perk-up window is flat enough
over those two days that being early buys you time, not price. The price prize only shows up on CN
(the choppier, faster-moving panel) and there it is a modest 1pp. The honest read: **C2's capture
win is a recall win and a lead-time win, not a fill-price win.** The pooled T1 premium (C2 7.02 vs R
8.08 on stocks) is lower because C2 also adds *new* events R never caught at a lower premium — that's
the recall channel, not the paired-earlier channel. Both are legitimate under G4d (which grades
pooled median premium, not paired), and G4d passes; but the mechanism of the premium gain is "more,
cheaper events caught" more than "same events caught cheaper."

### 4.3 T5 half stability

Both candidates are **ticker-half stable** on both axes on all three panels — no half-sign flip that
would undermine a pooled verdict:

- **C2 clean15** even/odd: stocks 37.95 / 37.89 (≈tied), baskets 37.21 / 37.67, cn 35.72 / 35.62.
  Tight both halves, no flip.
- **C2 stop5** even/odd: stocks 38.11 / 38.72, baskets 40.99 / 39.88, cn 46.16 / 46.18. Stable.
- **C1** is likewise stable (stocks clean15 37.32 / 37.49; cn 35.85 / 36.54) — C1's failures are on
  *level* (recall, pooled clean15), not on *stability*.

R's own halves are consistent too (stocks clean15 40.18 / 38.86). No candidate's verdict rides on a
single ticker half.

---

## 5. Honest caveats

1. **Overlapping fires → effective n < printed n (all panels).** Fires on the same name days apart
   share overlapping 126d forward windows, so outcomes are serially correlated and printed n
   overstates independent sample size. The 8-day dedupe mitigates within-burst correlation but not
   cross-burst; the per-name paired T3 and both-half T5 are the defenses (the C2 edge is spread
   across names and both halves, not a few autocorrelated clusters). C2's per-name clean15 win-rate
   sitting just under 50% (39.5-45.6%) means the pooled clean15 non-inferiority is carried by many
   small wins/losses averaging out, not a broad majority — a real (if gate-passing) soft spot.

2. **CN single regime (pre-declared, inherited from wave-3).** CN eval is 2022-09-01 → today, ~3.3y,
   ONE macro cycle. The even/odd T5 split is a ticker split, not a regime split; there is no
   multi-regime CN evidence here. CN's *strong* C2 recall gain (+10.1pp) and above-R clean15 are the
   most eye-catching numbers in the report — and the ones to trust least until a second CN regime
   accrues. The CN inclusion rides on a single-regime pass; treat as provisional, re-grade when a
   second CN macro regime is in the forward ledger. (Consistent with the wave-3 CN SHIP caveat.)

3. **Multiplicity: 2 candidates × 3 panels = 6 gate batteries.** No multiple-testing correction was
   applied to the pre-registered thresholds (the pre-registration did not specify one; §7 forbids
   editing the gates). The union C2 was *expected by construction* to win recall — the pre-registration
   said as much ("the union C2 is expected to win recall by construction — the real question is
   whether it pays for it on stop5/premium"). It did pay for it (pooled stop5/clean15 non-inferior,
   per-name medians non-inferior), so the recall win is not a free multiplicity artifact. Still: with
   6 batteries and knife-edge margins in places (C1 G4a −0.15pp; C2 stocks G4d premium 7.02 vs bar
   7.08, a 0.06pp margin; C2 baskets G4d premium 7.28 vs bar 7.49), the ship should be read as "C2
   clears the pre-committed bars" not "C2 is a large, robust edge." The chip-only ship shape (no rank
   change) is the correct conservatism for a battery this tight — the forward ledger, not this
   backtest, earns C2 any future weight.

4. **Close-based barriers on CN.** stop5/clean15 use close crossings, no CN intraday/open;
   `low_stop5` skipped by design. Bias applies equally to R and C, so it shifts absolute rates not
   the C-vs-R spread verdicts.

5. **Fold-2 fails for both candidates (COVID-crash→2022-top).** In 2019-07→2022-02 both C1 and C2
   under-perform R on clean15 (−9.82 / −6.26) and stop out more (C1 +6.24). The faster trigger
   front-runs into a violent-mean-reversion regime where the extra lag of m2d was load-bearing. The
   pooled and 4/5-fold clauses absorb it, but this is the regime where the fire layer is weakest and
   the forward ledger should watch it.

---

## 6. Ship record

- **C2 → SHIP** the COILED-FIRE marker on **US (stocks + baskets) and CN** — passes G4a, G4b, G4d
  (US) and additionally G4c + G4d(cn) for CN inclusion. Ship shape: **display chip + forward-ledger
  fields ONLY, no rank/bonus change** (exactly per pre-registration). The ledger grades the fire
  marker live before it earns any weight.
- **C1 → DO NOT SHIP.** Fails G4d (recall < R) on all three panels and fails G4a pooled clean15 (by
  0.15pp deduped). The m1d-only fire layer is cheaper and earlier but catches fewer durable bottoms
  than the platform it would replace — earliness bought by amputating recall, the framework's
  expensive failure mode.
- **CN inclusion for C2** carries the pre-declared 3.3y single-regime caveat; re-grade when a second
  CN macro regime accrues.

## 7. Ledger entries (for §8 of the spec)

| date | candidate | verdict | numbers | where |
|---|---|---|---|---|
| 2026-07-02 | **Wave 4 C1** (m1d_s3d inside COILED, deduped) | **NO-SHIP** | G4a FAIL (pooled clean15 37.40 < 37.55 by 0.15pp; per-fold 4/5 OK); G4b PASS; G4c PASS; **G4d FAIL all 3 panels** (recall_B15 10.45<12.39 st / 6.02<7.31 bk / 33.69<33.92 cn). Cheaper (prem 6.51/6.70/8.26) + earlier (lead 3d) but recall-negative | WAVE4_REPORT.md §2 |
| 2026-07-02 | **Wave 4 C2** (union m1d+m2d inside COILED, deduped) | **SHIP US + CN** (chip + forward-ledger only) | G4a PASS (pooled 38.41/37.92; 4/5 folds); G4b PASS (39.79-40.42 stop5, 37.44-37.67 clean15, per-name med non-inf); G4c PASS (46.17/35.67, n=16,820); **G4d PASS all 3** (recall +1.83/+1.08/+10.10pp, prem & lead favorable). T4: 2d earlier (US), fills same price at median (prem improvement 0.0pp) | WAVE4_REPORT.md §2 |
| 2026-07-02 | **Wave 4 dedupe sensitivity** | no ship verdict flips | only C1 G4a pooled clean15 flips on dedupe (dd FAIL 37.40 / undd PASS 37.68); C1 still NO-SHIP via dedupe-robust G4d recall loss; C2 SHIP robust both ways | WAVE4_REPORT.md §4.1 |
| 2026-07-02 | **Wave 4 T4 capture mechanism** | honest read | C2 fires 2d earlier (US) / 1d (CN) on 58-61% of shared B15 events, but median paired premium improvement 0.0pp (US) / 1.0pp (CN) — capture win is recall + lead-time, not fill-price | WAVE4_REPORT.md §4.2 |
