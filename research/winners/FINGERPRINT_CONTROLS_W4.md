<!-- W4 matched-controls fingerprint study (Layer-3b). DESCRIPTIVE ONLY (WA-R1/R5/R8). -->
<!-- Machine outputs. No registration, no filters, no site surfaces. -->

# Winner Autopsy Lab — W4 Matched-Controls Fingerprint Study (Layer-3b)

**Status:** DESCRIPTIVE ONLY — no hypothesis registration, no verdicts, no filters, no site surfaces.
Rulings WA-R1 / WA-R5 / WA-R8. Spec: `research/winners/W4_CONTROLS_STUDY_SPEC.md`.
Question (Layer-3b): pre-onset, what separated eventual breakaway names from matched
controls sampled the SAME calendar day — the watchlist-formation question. Distinct
from W3 (`FINGERPRINT_CENSUS_W3.md`, WA-R8 null: winners ≈ blow-offs at onset).

**Substrate:** `winner_episodes.parquet` — manifest hash `c1a6a1cbec74a726`, harvest date `2026-07-07` (frozen; no re-harvest — spec §1).
**Run:** seed 20260722, n_boot 50,000, m=36 tests, α_Bonferroni = 0.05/36 = 0.001389.
**Estimator:** matched-set Δ = value(E,t0) − median(value(controls,t0)); month-block bootstrap with the matched set as the resampling atom (spec §4).
**Engine pin:** `engine/winner_autopsy.py` @ `e9324058fa0e2a1f138fad9eee025e0de5871261` (origin/main; control sets re-derived live by `sample_controls` — see Reproducibility).
**Wall time:** 410.3s

## Bottom line

Machine outputs — not adjudications. The main loop appends the ruling below.

**Two modest, genuine pre-onset participation signatures precede breakaway MOTION; nothing pre-onset separates QUALITY — consistent with the W3 null.** After the round-1 robustness grid (below, out of m), the honest reading of the primary (all_matured) contrast is:

- **`realized_vol_63d`** and **`updown_dollar_vol_ratio`** are the two clean separators — both survive gate-matching (α/m [8.77, 15.06] and [0.080, 0.181]) and both hold in `blow_off`. They are **motion-not-quality**: `updown_dollar_vol_ratio` FAILS in `kept_going`, so it marks *that a name breaks away*, not *whether the breakaway holds*.
- **`dollar_vol_z21`** and **`dv_5_60_ratio`** are **ONSET-BAR + GATE ARTIFACTS — NULL pre-onset** (same class as `excess_21d_pp`, not fingerprints): their round-0 separation collapses to NULL once the onset bar is excluded AND controls are gate-matched (α/m [-0.026, 0.374] and [-0.024, 0.136]). The episode median `dollar_vol_z21` is 1.99 at t0 but 0.67 at t0−1 — the elevation lives on the onset bar, and the detector's `dollar_vol_z21≥1 OR dv_5_60_ratio≥1.5` gate admits the episode partly *because* of it.
- **`drawdown_from_252d_high_at_t0m21`** is **SUGGESTIVE — Bonferroni-fragile**: its α/m CI flips to NULL under gate-matching ([-5.81, +0.093]), though the 95% ([-4.64, -1.17]) and cluster ([-4.64, -1.13]) CIs still exclude 0, and it does not mirror across the quality split. Not promotable on this evidence.
- Every 8-K density and RS-turn cell is NULL; `self_funded_at_t0` and `close_location_value` are UNTESTABLE (coverage).

Net: pre-onset t0 geometry marks *participation before a breakaway onset* (volume/vol elevation, a shallower drawdown), but nothing pre-onset cleanly separates the eventual *winners from the blow-offs* — the W3 null carries into the controls frame.

## Population & control pool

- Equity matured episodes considered: **1,213** (crypto segregated — see honesty section).
- Included (≥ 3 eligible controls, bars present): **591**
  - of which kept_going label: 75; blow_off label: 369
- Excluded — < 3 eligible controls: **622**
- Excluded — no bars for episode ticker: **0**
- Unmatured (equity, not in analysis): 1,387
- Crypto matured (excluded from primary): 23

**Control-pool size distribution** (per episode, over episodes actually sampled):

| n_sampled | min | p25 | median | mean | p75 | max | =20 (capped) | <3 (excluded) |
|---|---|---|---|---|---|---|---|---|
| 1213 | 0 | 0.0 | 1.0 | 8.11 | 20.0 | 20 | 404 | 622 |

### What the excluded and included cohorts actually are (review round 1)

- The **622** episodes excluded for `< 3` controls are **602 (96.8%) sector-unmapped**: their `sector` is empty, and `sample_controls` returns zero controls by construction for an empty sector (an unmapped sector would match every other unmapped ticker — wrong cohort). So the exclusion is overwhelmingly a *sector-map coverage* artifact, not a market fact about those names.
- The **591** included episodes are therefore the **sector-mapped cohort**, and it is concentrated: **264/591 (45%) Information Technology**. Top sectors: Information Technology 264, Industrials 96, Health Care 91, Materials 50, Financials 34, Consumer Discretionary 29, Utilities 15, Communication Services 9.
- **179 distinct tickers** across the 591 included episodes (episodes repeat per ticker over time). Most-recurring: AMD (14), NVDA (14), WDC (14), LRCX (12), TER (11), XYZ (11). The ticker-cluster bootstrap CI (in every results table) is the guard against this recurrence inflating precision — it is printed alongside the month-block CI.

## Parity check (spec §3 — control-side implementation pinned to census definitions)

Episode-side recompute of `excess_21d_pp`, `dollar_vol_z21`, `dv_5_60_ratio` (via the `detect_episodes` code path: bench-aligned common index, value at t0) vs the committed parquet columns, tolerance 1e-06:

- Cells checked: **1,773**
- Pass: **1,773**
- Fail: **0**

**PASS** — recomputed trio is byte-for-value identical to the committed columns within tolerance. The one feature code path applied to controls matches the census's own definitions.

## Per-feature results (matched-set Δ)

Δ = median across episodes of [ value(E,t0) − median(value(controls,t0)) ] (continuous) or [ 1{E} − mean_j 1{C_j} ] (binary). Positive Δ = episode side higher.
CI95 = 95% month-block matched bootstrap; CIbonf = α/m percentile CI of the SAME draws (bonf_survives uses CIbonf, never CI95 — spec §0.1); CIcluster = ticker-cluster bootstrap robustness. `cov` = covered episodes / distinct t0 months.

### Contrast 1 (PRIMARY): all matured episodes vs matched controls

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIclus_lo | CIclus_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 1.8920 | 591 | 194 | 1.7212 | 2.0522 | 1.6467 | 2.1721 | yes | 1.7212 | 2.0459 |  |
| dv_5_60_ratio | continuous | 0.5411 | 591 | 194 | 0.4910 | 0.6011 | 0.4525 | 0.6389 | yes | 0.4928 | 0.5954 |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -2.7489 | 591 | 194 | -4.6908 | -1.2226 | -6.3536 | -0.3581 | yes | -4.7485 | -1.2399 |  |
| days_below_200dma | continuous | 0.0000 | 563 | 192 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| updown_dollar_vol_ratio | continuous | 0.1427 | 591 | 194 | 0.1103 | 0.1547 | 0.0913 | 0.1718 | yes | 0.1103 | 0.1574 |  |
| close_location_value | continuous | 0.0717 | 4 | 4 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 12.6077 | 589 | 194 | 11.4424 | 14.0860 | 10.2909 | 16.0572 | yes | 10.8794 | 15.5939 |  |
| hard_event_count_126d | continuous | 0.0000 | 339 | 107 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| soft_event_count_126d | continuous | 0.0000 | 339 | 107 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| rs_turn_21_63 | binary | 0.0000 | 588 | 193 | -0.1750 | 0.2222 | -0.2500 | 0.2500 | no | -0.1339 | 0.2000 |  |
| trailing_rung_ge2 | binary | -0.1500 | 339 | 107 | -0.2353 | -0.0500 | -0.2941 | 0.0000 | no | -0.2744 | 0.0000 |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |

### Contrast 2: kept_going episodes vs matched controls

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIclus_lo | CIclus_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 2.1603 | 75 | 46 | 1.8103 | 2.6621 | 1.3871 | 3.3661 | yes | 1.8103 | 2.6297 |  |
| dv_5_60_ratio | continuous | 0.5735 | 75 | 46 | 0.5149 | 0.7469 | 0.3595 | 0.9526 | yes | 0.5210 | 0.6988 |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -0.7527 | 75 | 46 | -7.4472 | 3.5372 | -10.6242 | 5.5588 | no | -8.8302 | 3.3695 |  |
| days_below_200dma | continuous | 0.0000 | 73 | 45 | -8.5000 | 0.0000 | -14.0000 | 0.0000 | no | -7.0000 | 0.0000 |  |
| updown_dollar_vol_ratio | continuous | 0.0988 | 75 | 46 | 0.0244 | 0.1485 | -0.0067 | 0.2271 | no | 0.0262 | 0.1491 |  |
| close_location_value | continuous | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 11.4115 | 75 | 46 | 7.7394 | 15.5939 | 4.9249 | 19.8262 | yes | 7.6809 | 15.8958 |  |
| hard_event_count_126d | continuous | 0.0000 | 50 | 27 | 0.0000 | 1.0000 | 0.0000 | 1.0000 | no | 0.0000 | 1.0000 |  |
| soft_event_count_126d | continuous | 0.0000 | 50 | 27 | -1.0000 | 0.0000 | -1.0000 | 0.5000 | no | -1.0000 | 0.0000 |  |
| rs_turn_21_63 | binary | -0.3000 | 74 | 45 | -0.4143 | 0.1000 | -0.4500 | 0.4000 | no | -0.4393 | 0.1000 |  |
| trailing_rung_ge2 | binary | -0.2566 | 50 | 27 | -0.3730 | 0.0000 | -0.5000 | 0.3889 | no | -0.3889 | 0.1500 |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |

### Contrast 3: blow_off episodes vs matched controls

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | CIclus_lo | CIclus_hi | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 1.9016 | 369 | 153 | 1.7128 | 2.0668 | 1.6344 | 2.2205 | yes | 1.7128 | 2.0586 |  |
| dv_5_60_ratio | continuous | 0.4886 | 369 | 153 | 0.4361 | 0.5738 | 0.3998 | 0.6143 | yes | 0.4361 | 0.5662 |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -1.9503 | 369 | 153 | -3.8613 | 0.1085 | -5.2029 | 0.9368 | no | -3.8613 | 0.0489 |  |
| days_below_200dma | continuous | 0.0000 | 351 | 151 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| updown_dollar_vol_ratio | continuous | 0.1428 | 369 | 153 | 0.1096 | 0.1724 | 0.0728 | 0.1920 | yes | 0.1097 | 0.1724 |  |
| close_location_value | continuous | -0.0400 | 1 | 1 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 13.1003 | 367 | 153 | 11.2708 | 14.4915 | 9.5568 | 16.8951 | yes | 10.4063 | 16.8725 |  |
| hard_event_count_126d | continuous | 0.0000 | 196 | 83 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| soft_event_count_126d | continuous | 0.0000 | 196 | 83 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no | 0.0000 | 0.0000 |  |
| rs_turn_21_63 | binary | 0.1667 | 367 | 153 | -0.1000 | 0.2500 | -0.2000 | 0.2857 | no | 0.0000 | 0.2500 |  |
| trailing_rung_ge2 | binary | -0.1303 | 196 | 83 | -0.2500 | 0.0000 | -0.3000 | 0.2105 | no | -0.3000 | 0.1000 |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | — | — | insufficient covered episodes (<5) |

## Robustness grid — the five round-0 SEPARATES, re-matched (OUT OF m)

**This is a robustness family, NOT part of the m=36 Bonferroni budget** (like the `gap_leg_crossed` stratum rerun below): the α/m column is printed for reference, but a NULL here *demotes* the round-0 primary verdict rather than earning a new test slot. The five features below are the ones whose primary (all_matured) α/m CI excluded 0 in round 0. We re-match under: **(a) gate-matched controls** — only controls that pass the detector's `dollar_vol_z21≥1 OR dv_5_60_ratio≥1.5` gate at t0 (episodes pass it for 100% by construction); **(b) t0−1** — read `dollar_vol_z21`/`dv_5_60_ratio` at the bar BEFORE onset, whose rolling windows exclude the onset volume spike; **(c) the combination.** Baseline (all controls, t0) is repeated per feature so the collapse is visible in one place.

Anchor diagnostics (all machine-recomputed, not pasted): control vol-gate-pass fraction at t0 = **2,693/9,813 = 27.4%** (episodes: 100% by construction); episode median `dollar_vol_z21` = **1.99 at t0** vs **0.67 at t0−1** — the volume elevation is an onset-bar phenomenon.

| Feature | Variant | Δ | n_cov | mo | 95% CI | α/m CI | cluster CI | α/m? | 95%? | clus? |
|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | baseline (all controls, t0) | 1.8920 | 591 | 194 | [1.7212, 2.0522] | [1.6467, 2.1721] | [1.7212, 2.0459] | SEP | SEP | SEP |
| dollar_vol_z21 | gate-matched (t0) | 0.6069 | 539 | 181 | [0.4969, 0.7283] | [0.4072, 0.8299] | [0.4848, 0.7661] | SEP | SEP | SEP |
| dollar_vol_z21 | t0−1 (all controls) | 0.7812 | 591 | 194 | [0.6333, 0.9376] | [0.5302, 1.0386] | [0.6435, 0.9352] | SEP | SEP | SEP |
| dollar_vol_z21 | t0−1 + gate-matched | 0.1447 | 539 | 181 | [0.0488, 0.2754] | [-0.0257, 0.3743] | [0.0380, 0.2798] | NULL | SEP | SEP |
| dv_5_60_ratio | baseline (all controls, t0) | 0.5411 | 591 | 194 | [0.4910, 0.6011] | [0.4525, 0.6389] | [0.4928, 0.5954] | SEP | SEP | SEP |
| dv_5_60_ratio | gate-matched (t0) | 0.2026 | 539 | 181 | [0.1484, 0.2343] | [0.1219, 0.2795] | [0.1486, 0.2325] | SEP | SEP | SEP |
| dv_5_60_ratio | t0−1 (all controls) | 0.2379 | 591 | 194 | [0.1944, 0.2898] | [0.1777, 0.3240] | [0.1942, 0.2870] | SEP | SEP | SEP |
| dv_5_60_ratio | t0−1 + gate-matched | 0.0558 | 539 | 181 | [0.0191, 0.0974] | [-0.0237, 0.1363] | [0.0160, 0.0976] | NULL | SEP | SEP |
| realized_vol_63d | baseline (all controls, t0) | 12.6077 | 589 | 194 | [11.4424, 14.0860] | [10.2909, 16.0572] | [10.8794, 15.5939] | SEP | SEP | SEP |
| realized_vol_63d | gate-matched (t0) | 11.5535 | 535 | 181 | [9.8184, 13.3366] | [8.7668, 15.0634] | [9.4325, 14.5728] | SEP | SEP | SEP |
| updown_dollar_vol_ratio | baseline (all controls, t0) | 0.1427 | 591 | 194 | [0.1103, 0.1547] | [0.0913, 0.1718] | [0.1103, 0.1574] | SEP | SEP | SEP |
| updown_dollar_vol_ratio | gate-matched (t0) | 0.1275 | 539 | 181 | [0.1031, 0.1588] | [0.0804, 0.1813] | [0.1028, 0.1598] | SEP | SEP | SEP |
| drawdown_from_252d_high_at_t0m21 | baseline (all controls, t0) | -2.7489 | 591 | 194 | [-4.6908, -1.2226] | [-6.3536, -0.3581] | [-4.7485, -1.2399] | SEP | SEP | SEP |
| drawdown_from_252d_high_at_t0m21 | gate-matched (t0) | -2.5503 | 539 | 181 | [-4.6351, -1.1736] | [-5.8094, 0.0928] | [-4.6351, -1.1270] | NULL | SEP | SEP |

**Reading the grid:**

- `dollar_vol_z21` / `dv_5_60_ratio`: baseline SEP → **t0−1 + gate-matched NULL** (α/m CI contains 0). The separation was the onset-bar spike admitted by the volume gate — an **onset-bar + gate artifact**, same class as `excess_21d_pp`. Gate-matched alone or t0−1 alone still separates; it takes BOTH corrections to reveal the null, because either alone leaves one channel of the selection linkage intact.
- `realized_vol_63d` / `updown_dollar_vol_ratio`: **hold gate-matched** (α/m still excludes 0). Neither is in the volume-confirm gate, and neither is an onset-bar window feature, so gate-matching is the relevant robustness check — they pass it. These are the two genuine pre-onset separators (motion, per the quality-split table).
- `drawdown_from_252d_high_at_t0m21`: **α/m flips to NULL under gate-matching** (upper bound crosses 0), while the 95% and cluster CIs still exclude 0 — Bonferroni-fragile, not promotable.

## Contrast 2 / 3 vs Contrast 1 (motion vs quality)

Spec §2: if Contrasts 2/3 mirror Contrast 1 (expected under the W3 null), that is itself the finding — pre-onset structure predicts *motion* (any breakaway onset), not *quality* (kept_going vs blow_off).

| Feature | C1 Δ | C1 bonf | C2 Δ | C2 bonf | C3 Δ | C3 bonf | mirrors C1? |
|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | 1.8920 | yes | 2.1603 | yes | 1.9016 | yes | yes |
| dv_5_60_ratio | 0.5411 | yes | 0.5735 | yes | 0.4886 | yes | yes |
| drawdown_from_252d_high_at_t0m21 | -2.7489 | yes | -0.7527 | no | -1.9503 | no | NO |
| days_below_200dma | 0.0000 | no | 0.0000 | no | 0.0000 | no | yes |
| updown_dollar_vol_ratio | 0.1427 | yes | 0.0988 | no | 0.1428 | yes | NO |
| close_location_value | 0.0717 | — | — | — | -0.0400 | — | yes |
| realized_vol_63d | 12.6077 | yes | 11.4115 | yes | 13.1003 | yes | yes |
| hard_event_count_126d | 0.0000 | no | 0.0000 | no | 0.0000 | no | yes |
| soft_event_count_126d | 0.0000 | no | 0.0000 | no | 0.0000 | no | yes |
| rs_turn_21_63 | 0.0000 | no | -0.3000 | no | 0.1667 | no | yes |
| trailing_rung_ge2 | -0.1500 | no | -0.2566 | no | -0.1303 | no | yes |
| self_funded_at_t0 | — | — | — | — | — | — | yes |

**Contrasts 2/3 do NOT fully mirror Contrast 1** — at least one feature's bonf verdict differs across the quality split. See the differing rows above.

## excess_21d_pp — tautology disclosure (parity-only, NOT a fingerprint)

`excess_21d_pp` is the detector's primary selection variable (breakaway onset ≡ excess crossing ≥20pp, or 42d ≥25pp). Controls are sampled to NOT be in candidate state within ±21td of t0. Comparing episode-vs-control excess is therefore guaranteed-positive by construction — TAUTOLOGICAL (spec §3 exclusion / §0.2), not a market regularity. It is recomputed above only to pin the parity check; it earns no fingerprint slot and is excluded from m.

Descriptive (all matured, matched-set Δ, n=591): median Δ = 19.8100 pp (episode side higher by construction).

### Volume-confirm selection linkage (construction note, NOT an adjudication)

The detector's candidate condition is `liquid & rel_breakaway & new_high & vol_confirm`, where `vol_confirm = (dollar_vol_z21 ≥ 1) OR (dv_5_60_ratio ≥ 1.5)`. That gate holds for 100% of episodes by construction, while controls are NOT gated on volume (only on excess / candidate-state). So the SEPARATES verdicts on `dollar_vol_z21` and `dv_5_60_ratio` are SELECTION-LINKED in the same way `excess_21d_pp` is — an episode is admitted partly *because* one of these was elevated at t0. Read them as detector-gate echoes, not discovered fingerprints; the main-loop ruling should weigh them accordingly. `updown_dollar_vol_ratio` and `realized_vol_63d` are NOT in the candidate condition, so their separation is not a direct gate echo (though volume/vol elevation is correlated with the excess move that IS gated). **The robustness grid above now demonstrates this quantitatively:** `dollar_vol_z21` and `dv_5_60_ratio` go NULL once controls are gate-matched AND the onset bar is excluded (t0−1), while `updown_dollar_vol_ratio` and `realized_vol_63d` hold gate-matched — so the round-1 verdict demotes the two gate features to artifacts and keeps the other two as genuine (motion) separators.

## Honesty section

### Survivor-only (spec §0.5)

The census and its control pool are survivor-lean: the `survivorship_biased` column is an unpopulated constant (False), and no dead-name price source is present in this parquet's `price_source` (yahoo/massive only). No survivorship stratum is tested or claimed — the gap is stated, not resolved.

### Per-feature coverage (episode-side AND control-side)

| Feature | ep covered | ep total | ep % | ctrl covered | ctrl total | ctrl % |
|---|---|---|---|---|---|---|
| dollar_vol_z21 | 591 | 591 | 100% | 9793 | 9813 | 100% |
| dv_5_60_ratio | 591 | 591 | 100% | 9732 | 9813 | 99% |
| drawdown_from_252d_high_at_t0m21 | 591 | 591 | 100% | 9746 | 9813 | 99% |
| days_below_200dma | 564 | 591 | 95% | 9076 | 9813 | 92% |
| updown_dollar_vol_ratio | 591 | 591 | 100% | 9746 | 9813 | 99% |
| close_location_value | 4 | 591 | 1% | 2938 | 9813 | 30% |
| realized_vol_63d | 590 | 591 | 100% | 9586 | 9813 | 98% |
| hard_event_count_126d | 340 | 591 | 58% | 6517 | 9813 | 66% |
| soft_event_count_126d | 340 | 591 | 58% | 6517 | 9813 | 66% |
| rs_turn_21_63 | 589 | 591 | 100% | 9581 | 9813 | 98% |
| trailing_rung_ge2 | 340 | 591 | 58% | 6517 | 9813 | 66% |
| self_funded_at_t0 | 254 | 591 | 43% | 0 | 9813 | 0% |

**NON-COMPARABLE:** `self_funded_at_t0` (B2 fundamentals) coverage is below 30% on at least one side — printed in the tables but must not be interpreted as representative. Control-side B2 is not joined at census scale here (statements panel + A2 firewall), so this feature is UNTESTABLE for the contrast.

### Excluded-episode counts

- < 3 eligible controls: 622
- no bars for episode ticker: 0
- crypto (7-day calendar + SPY benchmark category error): 23 matured
- unmatured (forward windows not closed): 1,387

### gap_leg_crossed == False stratum (Contrast 1 rerun) — robustness family, OUT OF m

Like the robustness grid above, this stratum rerun is a robustness family **outside the m=36 Bonferroni budget** — its α/m column is a reference tail, not an additional test slot. A change here re-weights confidence in the primary verdict; it does not add to m.

| Feature | Type | Δ | n_cov | mo | CI95_lo | CI95_hi | CIbonf_lo | CIbonf_hi | Bonf | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| dollar_vol_z21 | continuous | 1.9217 | 369 | 157 | 1.7194 | 2.1362 | 1.6247 | 2.2723 | yes |  |
| dv_5_60_ratio | continuous | 0.5018 | 369 | 157 | 0.4516 | 0.5827 | 0.4153 | 0.6277 | yes |  |
| drawdown_from_252d_high_at_t0m21 | continuous | -2.0273 | 369 | 157 | -3.6799 | 0.0791 | -4.9412 | 0.9435 | no |  |
| days_below_200dma | continuous | 0.0000 | 360 | 155 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |  |
| updown_dollar_vol_ratio | continuous | 0.1268 | 369 | 157 | 0.0767 | 0.1505 | 0.0605 | 0.1825 | yes |  |
| close_location_value | continuous | -0.0400 | 1 | 1 | — | — | — | — | — | insufficient covered episodes (<5) |
| realized_vol_63d | continuous | 11.4850 | 368 | 157 | 9.4220 | 12.9971 | 7.6809 | 14.2179 | yes |  |
| hard_event_count_126d | continuous | 0.0000 | 176 | 71 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |  |
| soft_event_count_126d | continuous | 0.0000 | 176 | 71 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | no |  |
| rs_turn_21_63 | binary | 0.0000 | 367 | 156 | -0.2000 | 0.2000 | -0.2857 | 0.2500 | no |  |
| trailing_rung_ge2 | binary | -0.1500 | 176 | 71 | -0.2500 | -0.0526 | -0.3158 | 0.0000 | no |  |
| self_funded_at_t0 | binary | — | 0 | 0 | — | — | — | — | — | insufficient covered episodes (<5) |

### What W4 cannot see

Per-ticker options positioning, analyst-revision breadth, and PIT short-interest are still forward-accruing (joins began ~2026-06 per the masterplan clock; first answerable ~2027-06). W4 tests only t0 price/volume geometry and trailing 8-K density — the substrates that exist today. A null here closes the tested constructions, not the search space (house epistemics: 'not found yet' ≠ 'does not exist').

### Reproducibility pin (review round 1)

- **Engine SHA:** `engine/winner_autopsy.py` @ `e9324058fa0e2a1f138fad9eee025e0de5871261` (origin/main, last commit touching that file — the read-only import surface).
- **Control sets are re-derived LIVE** by `sample_controls` at run time (deterministic: sorted, no RNG), NOT read from the committed parquet. The committed `n_controls` column **diverges from live sampling**: spot-checked on the first 40 included episodes, **11/40** differed. Consequently the committed-column inclusion count (`n_controls >= 3` = **585**) does not equal the live included count (**591**). Population counts in this report reproduce only at the pinned engine SHA (a later change to `sample_controls` would shift them).

### 8-K item-parser scope (review round 1)

This script's `_parse_items_list` is more permissive than the engine's (`engine/winner_autopsy.py:_parse_items_list`, a plain comma-split): the script also handles `[...]`-style list reprs (`ast.literal_eval`) and normalizes `;`→`,`. The committed `material_8k_events` store currently contains **zero** rows that would parse differently between the two (no `items` value starts with `[` or contains `;`), so on today's data the two produce identical output. The 'one feature code path' claim is therefore scoped to the current store contents — it is NOT a byte-identical reimplementation of the engine parser, and a future store row using bracket/semicolon syntax could diverge.

## Per-feature verdicts (SEPARATES / NULL / UNTESTABLE)

SEPARATES = α/m CI excludes 0 (mechanical, all-controls at t0); NULL = α/m CI contains 0 with adequate coverage; UNTESTABLE = insufficient coverage / degenerate (no CI) / NON-COMPARABLE. On the **primary (all_matured)** contrast, the round-1 relabel (`→ **…**`) is the honest verdict after the out-of-m robustness grid: the mechanical cell describes the round-0 all-controls-at-t0 fit; the relabel records whether it survives gate-matching / onset-bar exclusion.

**Contrast 1 (PRIMARY): all matured episodes vs matched controls**

- dollar_vol_z21 [all_matured]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=1.8920, α/m [1.6467, 2.1721]) → **ONSET-BAR + GATE ARTIFACT — NULL pre-onset (α/m [-0.026, 0.374] at t0−1 + gate-matched; same class as excess_21d_pp, NOT a fingerprint)**
- dv_5_60_ratio [all_matured]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=0.5411, α/m [0.4525, 0.6389]) → **ONSET-BAR + GATE ARTIFACT — NULL pre-onset (α/m [-0.024, 0.136] at t0−1 + gate-matched; same class as excess_21d_pp, NOT a fingerprint)**
- drawdown_from_252d_high_at_t0m21 [all_matured]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (lower in episodes; Δ=-2.7489, α/m [-6.3536, -0.3581]) → **SUGGESTIVE — Bonferroni-fragile (α/m flips to NULL under gate-matching [-5.81, +0.093]; 95% [-4.64, -1.17] and cluster [-4.64, -1.13] still exclude 0; non-mirror across the quality split)**
- days_below_200dma [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- updown_dollar_vol_ratio [all_matured]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=0.1427, α/m [0.0913, 0.1718]) → **CLEAN SEPARATOR — motion-not-quality (holds gate-matched α/m [0.080, 0.181]; holds in blow_off, FAILS in kept_going — motion, not quality)**
- close_location_value [all_matured]: UNTESTABLE (insufficient covered episodes (<5))
- realized_vol_63d [all_matured]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=12.6077, α/m [10.2909, 16.0572]) → **CLEAN SEPARATOR — motion-not-quality (holds gate-matched α/m [8.77, 15.06]; holds in blow_off; a pre-onset participation/vol signature, not a quality mark)**
- hard_event_count_126d [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- soft_event_count_126d [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- rs_turn_21_63 [all_matured]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [-0.1750, 0.2222])
- trailing_rung_ge2 [all_matured]: NULL — α/m CI contains 0 (Δ=-0.1500, 95% [-0.2353, -0.0500])
- self_funded_at_t0 [all_matured]: UNTESTABLE (insufficient covered episodes (<5))

**Contrast 2: kept_going episodes vs matched controls**

- dollar_vol_z21 [kept_going]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=2.1603, α/m [1.3871, 3.3661])
- dv_5_60_ratio [kept_going]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=0.5735, α/m [0.3595, 0.9526])
- drawdown_from_252d_high_at_t0m21 [kept_going]: NULL — α/m CI contains 0 (Δ=-0.7527, 95% [-7.4472, 3.5372])
- days_below_200dma [kept_going]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [-8.5000, 0.0000])
- updown_dollar_vol_ratio [kept_going]: NULL — α/m CI contains 0 (Δ=0.0988, 95% [0.0244, 0.1485])
- close_location_value [kept_going]: UNTESTABLE (insufficient covered episodes (<5))
- realized_vol_63d [kept_going]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=11.4115, α/m [4.9249, 19.8262])
- hard_event_count_126d [kept_going]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 1.0000])
- soft_event_count_126d [kept_going]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [-1.0000, 0.0000])
- rs_turn_21_63 [kept_going]: NULL — α/m CI contains 0 (Δ=-0.3000, 95% [-0.4143, 0.1000])
- trailing_rung_ge2 [kept_going]: NULL — α/m CI contains 0 (Δ=-0.2566, 95% [-0.3730, 0.0000])
- self_funded_at_t0 [kept_going]: UNTESTABLE (insufficient covered episodes (<5))

**Contrast 3: blow_off episodes vs matched controls**

- dollar_vol_z21 [blow_off]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=1.9016, α/m [1.6344, 2.2205])
- dv_5_60_ratio [blow_off]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=0.4886, α/m [0.3998, 0.6143])
- drawdown_from_252d_high_at_t0m21 [blow_off]: NULL — α/m CI contains 0 (Δ=-1.9503, 95% [-3.8613, 0.1085])
- days_below_200dma [blow_off]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- updown_dollar_vol_ratio [blow_off]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=0.1428, α/m [0.0728, 0.1920])
- close_location_value [blow_off]: UNTESTABLE (insufficient covered episodes (<5))
- realized_vol_63d [blow_off]: SEPARATES (mechanical, all-controls@t0) — α/m CI excludes 0 (higher in episodes; Δ=13.1003, α/m [9.5568, 16.8951])
- hard_event_count_126d [blow_off]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- soft_event_count_126d [blow_off]: NULL — α/m CI contains 0 (Δ=0.0000, 95% [0.0000, 0.0000])
- rs_turn_21_63 [blow_off]: NULL — α/m CI contains 0 (Δ=0.1667, 95% [-0.1000, 0.2500])
- trailing_rung_ge2 [blow_off]: NULL — α/m CI contains 0 (Δ=-0.1303, 95% [-0.2500, 0.0000])
- self_funded_at_t0 [blow_off]: UNTESTABLE (insufficient covered episodes (<5))

## Adjudication (main loop)

PENDING

