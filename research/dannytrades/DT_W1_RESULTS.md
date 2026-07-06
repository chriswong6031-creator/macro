# DT-W1a: Survivorship-Honest Whale Replication — Time-Control Repair

**Authority:** research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md §4.1  
**Run date:** 2026-07-06T23:35:47.331143+00:00  
**Era law:** data/massive_stock_day/ 2021-07-06+ (DT-R12); no pre-2021 volume claims

---

## Amendment DT-W1a — Time-Control Repair After Adversarial Bounce

**What changed and why:**

The original DT-W1 run (2026-07-06) was bounced by an Opus adversarial review
for two structural inference failures:

1. **Calendar-time confound not controlled.** The panel monthly base return ranged
   from -10.0% to +9.6% across calendar months.
   Events are time-clustered (whale_chg events tend to cluster in trending months),
   so the effective independent N is ~60 calendar months, not the
   591 tickers suggested by ticker-cluster bootstrap.
   The raw basis CIs were therefore too narrow.

2. **Within-ticker permutation structurally powerless for level tests (H3/H4).**
   Within-ticker permutation preserves each ticker's whale VALUE multiset, so
   high-whale tickers remain selected under the null. This produces a POSITIVE
   selection artifact (permuted-H3 mean fwd_1m +1.481% vs base +0.598%), not the
   null outcome claimed. The prior MD's 'negative drift' excuse had the sign wrong.

**Fixes applied (fix list from review):**

- **Primary inference:** cross-sectional demeaning of fwd_1m within each calendar
  month + month-block bootstrap (resample months with replacement). Verdicts are
  on this time-controlled basis. Raw (ticker-cluster only) shown as superseded context.
- **Controls:** 4 controls total — C1 within-ticker time permutation (H1/H2 raw),
  C2 within-month cross-ticker whale permutation (H3/H4 — breaks selection channel),
  C3 within-ticker permutation on demeaned series (H1/H2 TC), C4 positive injection.
- **H4:** per-month cross-sectional decile Spearman (mean across months) with
  month-block bootstrap CI. The invented sp<-0.3 threshold is dropped.
  Pooled equal-count and equal-width shown side by side for transparency.
- **p-values:** exact one-sided bootstrap tail fractions (fraction of bootstrap
  replicates on the wrong side). No fabricated CI-ratio approximations.
- **63d companion:** PIT member filter applied; N labeled as membership-filtered.

---

## Coverage Stamps

| Item | Value |
|------|-------|
| Tickers in scope (PIT member-months overlapping 2021-07-06→today) | 607 |
| Tickers with store data | 591 (97.4%) |
| Exited/delisted mid-window (INCLUDED for member months) | 105 |
| Missing store files | 2 (BF-B, BRK-B) |
| Total pool ticker-months | 30009 |
| Pool rows with both whale and fwd_1m | 26396 |
| Calendar months in panel | 60 (effective independent N) |
| Panel fwd_1m range across months | -10.0% to +9.6% |
| Gap-excluded months (calendar-continuity guard) | 0 |
| Store latest date | 2026-07-02 |
| Effective event window start (approx) | 2022-04-30 |
| Warm-up reason | 2021-07-06 + warmup (6mo whale win + 3mo diff = ~9 months warm-up) |

---

## Sign Convention

**lift = P(up|event) − P(up|all)  [on the time-controlled / month-demeaned basis]**  
NEGATIVE lift = event group underperforms the panel base rate after month demean.  
H1 and H3 expect NEGATIVE lift (extended/hot whale → mean-reversion).  
H2 expects POSITIVE lift (whales leaving → bounce).  
H4 expects NEGATIVE Spearman (higher whale decile → lower fwd_1m).

---

## H1–H4 Results — Time-Controlled (Primary Basis)

**Family:** dt_replication | **m=4** | **BH q=0.1** | **Inference:** month-block bootstrap on cross-sectionally demeaned fwd_1m

| Test | Event | N events | N months | Lift (time-ctrl) | 95% CI | Exact p | BH survived | CI excl zero | Verdict |
|------|-------|----------|----------|-----------------|--------|---------|-------------|--------------|---------|
| H1 | whale_chg > +10 | 5596 | 60 | -0.0062 | [-0.0293, +0.0186] | 0.318 | No | No | **FAILED** |
| H2 | whale_chg < -10 | 5279 | 60 | +0.0119 | [-0.0146, +0.0380] | 0.181 | No | No | **FAILED** |
| H3 | whale > 75 | 1102 | 60 | +0.0262 | [-0.0215, +0.0713] | 0.848 | No | No | **FAILED** |
| H4 | whale decile monotonicity | 27947 obs | 56 | Spearman=0.0548 | [-0.1059, +0.2035] | 0.750 | No | No | **FAILED** |

**H4 side-by-side (per-month primary vs pooled comparisons):**

| Method | Spearman | CI 95% |
|--------|----------|--------|
| Per-month mean (PRIMARY) | 0.0548 | [-0.1059, +0.2035] |
| Pooled equal-count | -0.8424 | (not bootstrapped) |
| Pooled equal-width | -0.1152 | (not bootstrapped) |

---

## H1–H4 Results — Raw Basis (Ticker-Cluster Only, Superseded)

Shown for continuity with original DT-W1 run. **Do not use for verdict purposes.**
Calendar-time confound not removed; CIs are too narrow (effective N ~600 tickers
but ~60 independent months).

| Test | N events | Lift (raw) | 95% CI (raw) |
|------|----------|-----------|--------------|
| H1 | 5596 | -0.0333 | [-0.0453, -0.0219] |
| H2 | 5279 | +0.0445 | [+0.0329, +0.0552] |
| H3 | 1102 | -0.0092 | [-0.0411, +0.0200] |

---

## Calibration Controls (4 Total)

### C1: Within-Ticker Time Permutation (H1/H2, raw basis)

Shuffles temporal order of whale within each ticker. Appropriate for change tests
(H1/H2) — destroys temporal signal, preserves per-ticker distribution.

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H1 (permuted) | 6517 | -0.0042 | [-0.0147, +0.0062] | PASS |
| H2 (permuted) | 6450 | -0.0050 | [-0.0161, +0.0051] | PASS |

### C2: Within-Month Cross-Ticker Whale Permutation (H3/H4, level tests)

Shuffles whale values across tickers WITHIN each calendar month. This breaks the
ticker-selection channel for level tests. The prior within-ticker permutation
was structurally powerless for level thresholds: each ticker's whale VALUE
multiset is preserved, so high-whale tickers stay selected under the null,
producing a POSITIVE cross-sectional selection artifact (not null behaviour).

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H3 (cross-ticker permuted) | 1102 | -0.0192 | [-0.0472, +0.0102] | PASS |

### C3: Within-Ticker Time Permutation on Demeaned Series (H1/H2, TC basis)

Validates the time-controlled bootstrap machinery. Permuted whale on demeaned
fwd_1m should produce lifts near zero with CIs spanning zero.

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H1 (demeaned, permuted) | 6509 | +0.0099 | [-0.0032, +0.0240] | PASS |
| H2 (demeaned, permuted) | 6471 | -0.0035 | [-0.0154, +0.0084] | PASS |

### C4: Positive Injection (H2, +2pp injected into fwd_1m on H2-mask rows)

H2 must detect the injected signal (CI excludes zero above).

| Test | N events | Lift | 95% CI | Pass? |
|------|----------|------|--------|-------|
| H2 (+2pp injected) | 5279 | +0.1050 | [+0.0776, +0.1339] | PASS |

---

## Scope Note

This study covers 2021-07-06 to 2026-07-06 — a predominantly bullish US equity
regime. The effective independent sample is approximately
60 calendar months, not 591 tickers.

A FAIL here means: **the whale signal does not replicate on a time-controlled
basis within this 5-year bull-market window.**

It does NOT by itself overturn the 64-year original DannyTrades evidence base.
The original evidence carries its own caveat (survivorship of profitable strategies
over 64 years). See research/DANNYTRADES_PHASE0.md for the original evidence
summary and its scope conditions.

---

## Descriptive Companion: Composite-Score Deciles at 63d (PIT-Filtered)

**DESCRIPTIVE-ONLY: composite-score deciles at 63d (overlapping, PIT-filtered, not in FDR family)**

N observations (overlapping, PIT-member months only): 573861  
Spearman(decile, mean_fwd_63d): -0.9758

| Decile | Mean fwd_63d (%) |
|--------|-----------------|
| 0 | +3.3335 |
| 1 | +2.6641 |
| 2 | +2.2404 |
| 3 | +1.6973 |
| 4 | +1.2790 |
| 5 | +0.8613 |
| 6 | +0.9427 |
| 7 | +0.3782 |
| 8 | +0.6481 |
| 9 | +0.2905 |

---

## Implementation Notes

- **Amendment DT-W1a:** time-control repair applied after Opus adversarial bounce.
  Events/thresholds/universe frozen per prereg §4.1. Only inference machinery changed.
- **Time control:** cross-sectional monthly demeaning removes the calendar-time confound.
  Month-block bootstrap (resample months with replacement) reflects ~60-month effective N.
- **Calendar-continuity guard:** months with any daily gap > 14 calendar days excluded.
- **BH p-values:** exact one-sided bootstrap tail fractions (no CI-ratio approximation).
- **H4:** per-month cross-sectional decile Spearman (mean across months) is primary.
  Verdict by CI from month-block bootstrap on the per-month Spearman series.
  No sp<-0.3 invented threshold.
- **H3/H4 control:** within-month cross-ticker permutation (C2) is the correct null
  for level tests. Within-ticker permutation (C1) is structurally powerless for H3/H4
  because it preserves per-ticker whale value multisets (high-whale tickers stay selected).
- **63d companion:** PIT member filter applied; N is membership-agnostic daily rows
  restricted to member periods.
- **Missing tickers BF-B, BRK-B:** excluded, counted in coverage stamps.
- **Thresholds:** all frozen at prereg values (entering=10, leaving=-10, hot=75,
  win=6, diff=3, BH q=0.10, n_boot=1000, seed=11). Nothing tuned.
