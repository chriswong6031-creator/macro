# P3 — Kernel-Rank Shadow — PRE-REGISTRATION

**STATUS: APPROVED — Fable 2026-07-05 (red-team P2_REDTEAM.md blocking fixes applied; Fable rulings R-P2.1 flip-floor=100 clusters+2 quarters, R-P2.2 single concordance authority = P2.1b §3.3)**

**Study:** P3 Kernel-Rank Shadow. **Program:** Entry Intelligence (EI). **Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md §6/P3.2`. **Registered:** 2026-07-05 (before any run). **Author:** Sonnet subagent under Fable orchestration.

**Consumes:**
- `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` — rulings R1–R10, §6 phase design
- `research/entry_intel/P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments` — era law
- `research/entry_intel/p1_runs/P1_1_SEPARABILITY/RESULTS.md` + `REVIEW.md` — 5 feature survivors
- `research/entry_intel/p1_runs/P1_3/RESULTS.md` + `REVIEW_v2.md` — trio P1.3 effects (3 independent factors)
- `engine/neuralweb/kernel.py` — hierarchical-shrinkage pattern (cited as template; no money-path authority imported)

**Blocking gates (all must clear before execution):**
1. `data/replay/replay_boarded.parquet` exists at its approved MD5 (`906175f9eb8caa351ed6d7d5c56265d3`) and the P0.1 golden test is clean.
2. P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) exists and has not been superseded without Fable approval.
3. P1.1 RESULTS accepted (CONFORMANT verdict confirmed 2026-07-05).
4. P1.3 round-2 RESULTS accepted by Fable (CONFORMANT, round-2 reviewer recommendation 2026-07-05).
5. This PREREG carries DRAFT status; **no execution before Fable approval (R8).**

**Constitutional constraints binding on this study:**
- R6: Kernel-rank ships shadow-first — the shadow column is the ONLY user-visible artifact in v1; no board reordering until the pre-registered flip criterion is met.
- R7: Additive-lanes law — the kernel rank is an ADDITIONAL column that can raise quality labels UP; it never filters the board toward zero rows.
- Article 2 (Neural Web): any `board_ordering` influence ships shadow-first with a pre-registered flip criterion (Wilson lower bound on the shadow forward ledger beating incumbent at episode-clustered n floor). This PREREG is the Article-2-compliant registration for that shadow period.
- Species ladder (chip → ledger → graded_bonus → gate_weight): the 5 survivors from P1.1 enter this study as chip-stage candidates for ledger-graded cell posteriors; no promotion beyond ledger is conferred by this study.

---

## 0. Plain-English summary

> Right now the board ranks stocks using a hand-assembled formula — a weighted blend of momentum, alignment, and a residual-alpha score. That formula was never tested end-to-end: nobody ran all the production-trigger fires through it and asked "did a higher score today predict better outcomes later?"
>
> Phase 1 found five fields that actually correlate with outcomes: how far the stock is from its 52-week high, whether it is near a forced-seller washout, how extended it is in price (two measures), and which phase of the weekly cycle it is in. Phase 1.3 found three independent entry-quality effects with production-trigger evidence — anti-chase (ext_z ≤ 2.0), washout proximity, and RS-inflection.
>
> This study builds a statistically-grounded score — the **kernel rank** — from those validated survivors. For each combination of (feature bucket, regime, horizon) we compute a shrunk posterior probability that a fire in that cell leads to a cushioned or clean-liftoff outcome. The rank is the Wilson lower bound of that posterior: a conservative estimate that respects how many fires we actually have evidence from. This kernel rank runs in **shadow** alongside the incumbent score — it does not change what users see or what the board shows. It logs its predictions into a forward ledger. When the shadow ledger has accumulated enough independent episodes and the kernel rank demonstrably beats the incumbent, a pre-registered flip criterion fires and the switch can be proposed to Fable for approval.
>
> Until the flip criterion is met, nothing visible changes. This is not a live ranking change — it is a prospective test of whether the evidence-grounded posterior outperforms the incumbent formula.

---

## 1. Study scope and population

**Evidence base (P1.1 survivors):** 5 features survive BH + both-halves sign stability on 834,267 pre-gate pool rows spanning 184 week clusters (primary verdict window 2022-06-30 → **2026-07-02** — the P1.1 pre-gate pool boundary), per `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04) + §6 v1.1 amendments`:

| Rank | Feature | Direction | ρ_21d | BHq_21d | Sign-stable 21d |
|------|---------|-----------|--------|---------|-----------------|
| 1 | `dist_52wh` | lower → better | −0.0845 | 0.0000 | True |
| 2 | `cohort_washout_proximity` | near_washout → better | +0.0773 | 0.0000 | True — **PROXY-STAMPED** (100% proxy-sourced; A1 advisory; same production-source requirement applies as P2.1b) |
| 3 | `ext_z` | lower → better | −0.0707 | 0.0000 | True |
| 4 | `ext_atr` | lower → better | −0.0593 | 0.0001 | True |
| 5 | `weekly_phase` | categorical separator — **non-monotone** (P1.1 REVIEW A4; bucket means non-monotonic; treat as categorical, not ordinal rank) | N/A | 0.0000 | True |

All statistics cited from P1.1 RESULTS.md (run 2026-07-05, Opus REVIEW CONFORMANT).

**Evidence base (P1.3 independent effects):** Three independent factor effects from production-trigger fires (49,939 verdict-grade fires, 22,295 episode clusters, effective window 2022-06-30 → **2025-12-29** — the P1.3/P1.5 fire-grading ceiling, i.e. the last date where the 63d forward verdict fits within the data boundary; this differs from the P1.1 pre-gate pool ceiling of 2026-07-02 because the 21d/63d verdict window must fit inside the data), per P1.3 RESULTS.md round-2 (run 2026-07-05, round-2 Opus REVIEW CONFORMANT):

- **F3 anti-chase (ext_z ≤ 2.0):** ships as hard gate. HG T21 stop-out Δ = −0.43pp, BH-adj p = 0.0060, sign-stable; T22 dead-money Δ = −3.63pp, BH-adj p = 0.0060, sign-stable; T24 63d stop-out Δ = −5.00pp, BH-adj p = 0.0933, sign-stable. Fire-rate impact 4.6% (n=2,299 would-block). Rank-biserial r = −0.0612 at 21d.
- **F1 cohort-washout proximity:** ships as rank weight. Gate-rejected (54.0% fire impact). RW T09 63d stop-out Δ = −4.55pp, BH-adj p = 0.0006, sign-stable; T02 dead-money Δ = −13.19pp at 21d, BH-adj p = 0.0006, sign-stable. Rank-biserial r = −0.0978 at 63d (HG).
- **F2 RS-inflection (Q2∪Q3):** ships as rank weight. Gate-rejected (48.5% fire impact, HG null). RW T18 21d cushioned favorable, BH-adj p = 0.0933, sign-stable; T20 63d cushioned favorable, BH-adj p = 0.0752, sign-stable. Rank-biserial r = −0.0180 at 63d. **Effect is genuinely marginal** (|r| ≈ 0.01–0.02 per REVIEW_v2 ADVISORY-2).

These constitute ~3 independent forward-return effects (per ADVISORY-2 of the round-2 review: cite ~3 independent effects, not "22/30 trials"; the 22/30 figure overstates independence because p-values are duplicated across terminal states within each (factor, mode, horizon) cell).

**Population for cell construction:** rows in `data/replay/replay_boarded.parquet` where `verdict_type == 'fire'` AND `verdict_grade == True` AND `survivor_bias == False`. This is the 49,939-fire verdict-grade population established in P1.3.

**Era (mandatory citation):** `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)`. Primary verdict window = **2022-06-30 → last-full-replay-date** (v1.1 Amendment 1 — effective window after 250-bar MTF warmup). All 49,939 verdict-grade fires are in this window (0 stamped rows in the artifact). Context-only pre-2021 rows: 0 (none exist in the artifact).

---

## 2. Cell design — feature buckets

Cells are defined by the triple **(feature-bucket × regime × horizon)**. Shrinkage goes toward the parent per the hierarchical pattern in `engine/neuralweb/kernel.py` (cited as design template for the shrinkage pattern; no money-path authority is imported — this study does not call any Neural Web consumer path).

### 2.1 Feature buckets (pre-registered; no post-hoc re-binning)

Each feature is bucketed once before any outcome is observed. Bucket definitions are fixed here and may not be revised after results are seen. Any alternative binning = new recorded trial.

**`dist_52wh` (continuous — quartiles):**

| Bucket | Definition | Direction hypothesis |
|--------|-----------|---------------------|
| Q1 | dist_52wh ≤ 25th percentile of fire population | Closest to 52wh — hypothesized worst |
| Q2 | 25th < dist_52wh ≤ 50th percentile | |
| Q3 | 50th < dist_52wh ≤ 75th percentile | |
| Q4 | dist_52wh > 75th percentile | Furthest from 52wh — hypothesized best |

Percentile breakpoints computed on the 49,939 verdict-grade fires at run start and logged to preamble. No search over alternative bin counts.

**`cohort_washout_proximity` (binary — production encoding is bool):**

| Bucket | Definition |
|--------|-----------|
| NEAR | `washout_proximity == True` (22,965 fires) |
| NOT_NEAR | `washout_proximity == False` (26,974 fires) |

Binary split is the pre-registered operationalization per P1.3 PREREG §2/F1. **PROXY-STAMP carried forward from P1.1 REVIEW A1:** this feature is 100% proxy-sourced in the current replay artifact. Cell posteriors for cohort_washout_proximity carry a `proxy_sourced=True` flag.

**Production-source confirmation gate (binding):** cohort_washout cells are eligible for the kernel-rank computation ONLY when `research/entry_intel/p1_runs/P1_3/concordance_check.json` exists at build time AND contains a GO verdict (meaning P2.1b's concordance gate has run and found ≥ 90% concordance on overlapping names, per `P2_1B_RANKWEIGHT_PREREG.md` §3.3 — the single authoritative concordance definition for this feature). P3 reads that artifact at build time; it does not define an independent concordance bar. A missing artifact or a REPROBE_REQUIRED verdict in `concordance_check.json` forces the omit-and-renormalize fallback: the cohort_washout_proximity dimension is omitted from the cell key, the cell collapses to the regime × horizon marginal, and the combination uses the three remaining features at weights 0.34 + 0.28 + 0.24 = 0.86. This fallback is logged in the build preamble; it is not a post-hoc choice.

**`ext_z` (continuous — quartiles):**

| Bucket | Definition | Direction hypothesis |
|--------|-----------|---------------------|
| Q1 | ext_z ≤ 25th percentile | Lowest extension — hypothesized best |
| Q2 | 25th < ext_z ≤ 50th percentile | |
| Q3 | 50th < ext_z ≤ 75th percentile | |
| Q4 | ext_z > 75th percentile | Most extended — hypothesized worst |

Note: F3's hard gate (ext_z ≤ 2.0) fires at a fixed absolute threshold; the kernel bucket uses relative quartiles within fires for finer differentiation. The hard gate and the kernel-rank bucket are complementary, not redundant. If F3's hard gate is active at build time, the Q4 bucket will be sparse (fires with ext_z > 2.0 are blocked by the gate); the kernel-rank cell handles sparsity via hierarchical shrinkage.

**`ext_atr` (continuous — quartiles):**

| Bucket | Definition | Direction hypothesis |
|--------|-----------|---------------------|
| Q1 | ext_atr ≤ 25th percentile | Low ATR-based extension — hypothesized best |
| Q2 | 25th < ext_atr ≤ 50th percentile | |
| Q3 | 50th < ext_atr ≤ 75th percentile | |
| Q4 | ext_atr > 75th percentile | High ATR-based extension — hypothesized worst |

**`weekly_phase` (categorical — non-monotone; buckets are categories, not an ordinal rank):**

Per P1.1 REVIEW A4 advisory: weekly_phase bucket means are non-monotonic (bear_recovering highest, rolling lowest in H1). The kernel treats weekly_phase as a **categorical** separator, not an ordinal rank signal. Each named phase is its own bucket; no collapsing or reordering of phases is permitted in v1.

| Bucket | Phase value (from replay encoding) |
|--------|-----------------------------------|
| BASING | `basing` |
| BEAR_RECOVERING | `bear_recovering` |
| TURNING | `turning` |
| RISING | `rising` |
| ROLLING | `rolling` |
| FALLING | `falling` |
| UNKNOWN | null / unknown — routed to regime-horizon marginal |

### 2.2 Regime dimension

| Bucket | Definition | Source column |
|--------|-----------|---------------|
| GOLDILOCKS | `quad_hard_label == 'Goldilocks'` | replay `quad_hard_label` (if present) |
| REFLATION | `quad_hard_label == 'Reflation'` | |
| STAGFLATION | `quad_hard_label == 'Stagflation'` | |
| RECESSION | `quad_hard_label == 'Recession'` | |
| __unstamped__ | null / missing quad_hard_label | |
| __all__ | marginal across all regime buckets (always emitted per feature-bucket × horizon) | |

The `__all__` marginal is the depth-bearing cell per the kernel.py pattern. Regime-conditioned cells are secondary refinements; they will be thin given the effective window (2022–2025) and any cell with n_eff < 25 episode clusters collapses to its parent per §3 shrinkage rule.

### 2.3 Horizon dimension

Horizons evaluated: **{21d, 63d}** — the two pre-registered verdict horizons in P1.1 and P1.3. (The 5/10/126d horizons in kernel.py apply to the Neural Web engine kernel; this study restricts to the EI program's registered verdict horizons to keep the cell grid tractable and the n floors achievable.)

### 2.4 Cell key

A cell is fully identified by the 4-tuple: `(feature_name, feature_bucket, regime_bucket, horizon_days)`.

The marginal-per-feature cell is `(feature_name, __marginal__, __all__, horizon_days)` and is always emitted.

---

## 3. Cell posterior computation and hierarchical shrinkage

### 3.1 Outcome label

**Primary outcome (frozen):** `good_outcome_21d = (terminal_state ∈ {cushioned, clean_liftoff})` at 21d, and `good_outcome_63d = (terminal_state ∈ {cushioned, clean_liftoff})` at 63d. These match the P1.1 registered outcome definitions verbatim.

### 3.2 Raw cell proportion

For each cell, count:
- `n_eff` = number of distinct episode clusters (`episode_id` values) represented in the cell (event-collapsed, per the kernel.py pattern: multiple fires from the same episode cluster in the same cell count as ONE observation for n-floor and shrinkage purposes).
- `k_eff` = number of distinct episode clusters with `good_outcome_h == True`.
- `p_raw = k_eff / n_eff` (raw proportion; diagnostic only — not the consumable posterior).

### 3.3 Hierarchical shrinkage (two-tier, toward parent)

Following the kernel.py pattern (engine/neuralweb/kernel.py SHRINKAGE section, lines 50–56): shrinkage is toward the parent cell, not toward a fixed global prior. The parent hierarchy for a (feature_name, feature_bucket, regime_bucket, horizon) cell is:

```
(feature_name, feature_bucket, regime_bucket, horizon)
    → parent: (feature_name, feature_bucket, __all__, horizon)  [marginal over regimes]
    → grandparent: (feature_name, __marginal__, __all__, horizon)  [marginal over buckets]
    → global: base rate (good_outcome across all verdict-grade fires at this horizon)
```

Shrinkage formula (per pooling.py MemberStat / pooled_edges pattern used in kernel.py):

```
shrunken_p = (k_eff + K_SHRINK × p_parent) / (n_eff + K_SHRINK)
```

where `K_SHRINK = 10` (pre-registered; the pooling.py K_POOL default as used in kernel.py — cite: engine/neuralweb/kernel.py line 99, `from engine.pooling import MemberStat, K_POOL`). `p_parent` = the shrunken proportion of the parent cell (recursively shrunk; recursion bottoms out at the global base rate).

`K_SHRINK = 10` is logged at run start. It is not searched over. Any alternative K = new recorded trial.

### 3.4 Wilson lower bound (the kernel-rank score)

The consumable kernel-rank score for a cell is the **Wilson lower-bound on P(cushioned ∪ clean-liftoff)** computed from the shrunken cell posterior:

```
wilson_lo = shrunken_p - z * sqrt(shrunken_p * (1 - shrunken_p) / n_eff_effective)
```

where `z = 1.645` (one-sided 95% CI lower bound — matching the Neural Web Article-3 authority threshold, `engine/qledger.py` Wilson CI convention) and `n_eff_effective = n_eff + K_SHRINK` (the effective sample size after shrinkage, consistent with the pooled_edges construction).

`wilson_lo` is the kernel-rank score assigned to a fire falling in this cell. Lower confidence bound choice is intentional: it penalizes thin cells and converges toward the true posterior as evidence accumulates, without over-promoting sparse cells.

**When n_eff < 25 episode clusters (episode-clustered n floor):** the cell is labeled **THIN**. A THIN cell does not emit its own `wilson_lo` to the shadow column; the fire is assigned the `wilson_lo` of the parent cell (next non-thin ancestor in the hierarchy). The THIN label is printed in the cell table. This n floor of 25 episode clusters matches the P1 study n floor (PREREG §3 / P1.3 PREREG episode-cluster n-floor) and is not re-searched.

### 3.5 Combining feature dimensions into a single kernel-rank score

The 5 survivor features contribute independently registered effects. Their cell posteriors are combined into a single rank score by **weighted averaging of Wilson lower bounds**, with feature weights proportional to |ρ_21d| from P1.1:

| Feature | |ρ_21d| | |ρ|-proportional weight (pre-normalization) |
|---------|---------|--------------------------------------|
| `dist_52wh` | 0.0845 | 0.34 |
| `cohort_washout_proximity` | 0.0773 | 0.31 |
| `ext_z` | 0.0707 | 0.28 |
| `ext_atr` | 0.0593 | 0.24 |
| `weekly_phase` | N/A (KW, non-directional) | 0.00 — **excluded from weighted combination** |

`weekly_phase` weight = 0.00 because its P1.1 effect size is non-directional (KW H-statistic, no ρ) and it acts as a categorical separator, not a monotone signal. It is retained as a conditioning dimension for regime-bucket refinement within cells (i.e., the weekly_phase bucket is part of the cell key for its own feature dimension), but it does not contribute weight to the cross-feature combination.

**Combination formula:** the kernel_rank_score is the weighted mean of the four features' Wilson lower bounds, computed as:

```
kernel_rank_score = Σ(wᵢ · wilson_loᵢ) / Σwᵢ
```

where Σwᵢ = 0.34 + 0.31 + 0.28 + 0.24 = **1.17**. The weights are |ρ|-proportional (pre-normalization); dividing by Σwᵢ = 1.17 produces the weighted mean. The weights are NOT pre-normalized to sum to 1 — the 1.17 denominator is the normalization step inside the formula.

**Washout-omitted fallback:** if `cohort_washout_proximity` is omitted at build time (P2.1b concordance GO artifact absent — see §2.1), the remaining three features use Σwᵢ = 0.34 + 0.28 + 0.24 = **0.86**:

```
kernel_rank_score_fallback = Σ(wᵢ · wilson_loᵢ) / 0.86   [three features only]
```

This fallback is logged in the preamble at build time; it is not a post-hoc choice.

**The `weekly_phase` dimension is still used** as a cell key axis when computing the `dist_52wh`, `ext_z`, and `ext_atr` feature cells — i.e., for those features the regime bucket in the cell tuple is `(quad_regime, weekly_phase)` jointly — but only if the resulting sub-cell has n_eff ≥ 25 episode clusters (else collapses to the parent without weekly_phase conditioning).

---

## 4. Shadow column — design and scope

### 4.1 v1 scope: shadow column ONLY

In v1, the kernel-rank study produces exactly ONE new artifact:

- **`kernel_rank_score`** column appended to the board output (the in-memory frame that populates `site/factordata/us_standouts.json`), emitted alongside the incumbent `blend_sorted` rank score.

The shadow column:
- Is NEVER used to reorder board rows in v1.
- Does NOT appear in any user-visible sort or filter in v1.
- Is logged to the forward ledger (`data/signal_archive/kernel_rank_ledger.parquet`, R9 — not committed to git) alongside `signal_date`, `ticker`, `episode_id`, `incumbent_rank_score`, `kernel_rank_score`, and the forward returns at 21d and 63d (graded by the replay grader on the rolling basis as returns accrue).
- Is visible to operators via the admin console (internal monitoring only) in v1.

**No board wiring, no user-facing column, no page element carries the kernel rank in v1.** The boundary is structural: the shadow column is written to the ledger file and to the internal admin view, and nowhere else.

### 4.2 Forward ledger construction

The forward ledger is the prospective evaluation record. It is append-only (R9 convention). Each row represents one board fire on one date:

| Column | Type | Description |
|--------|------|-------------|
| `signal_date` | date | Date of the fire signal |
| `ticker` | str | Ticker symbol |
| `episode_id` | str | Episode cluster id (TICKER_YYYY-WNN from the replay scheme) |
| `incumbent_rank_score` | float | `blend_sorted` rank on this date (the incumbent board rank) |
| `kernel_rank_score` | float | Kernel-rank Wilson lower bound (this study's shadow score) |
| `kernel_rank_source_cell` | str | Full cell key used (e.g. "ext_z:Q1×GOLDILOCKS×21d") for auditability |
| `kernel_rank_proxy_flags` | str | Comma-separated proxy-sourced feature dimensions (if any) |
| `fwd_ret_21` | float | Forward return at 21d (filled as it accrues; null until available) |
| `fwd_ret_63` | float | Forward return at 63d (filled as it accrues; null until available) |
| `good_21d` | bool | Terminal state at 21d: {cushioned, clean_liftoff} (filled as it accrues) |
| `good_63d` | bool | Terminal state at 63d (filled as it accrues) |
| `survivor_bias` | bool | Must be False for all live prospective rows (live fires have no survivorship bias) |

The ledger grows with each board cycle. It is the primary evidence base for the shadow-vs-incumbent comparison (§5).

---

## 5. Shadow-vs-incumbent comparison (pre-registered flip criterion — Article 2 / R6)

### 5.1 The comparison

The flip criterion is: **does the kernel_rank_score better separate `good_21d` (or `good_63d`) outcomes than the incumbent `blend_sorted` rank, on the prospective forward ledger?**

**Primary metric (pre-registered):** Spearman rank correlation ρ of `kernel_rank_score` vs `good_21d` outcome, computed on the forward ledger rows with `good_21d` not null, compared against Spearman ρ of `incumbent_rank_score` vs `good_21d` on the same rows.

**Secondary metric:** same comparison at the 63d horizon.

**Test:** one-sided permutation test on the difference `ρ_kernel − ρ_incumbent`. Permutation at the episode-cluster level (shuffle episode labels, per the P1.3 corrected methodology). N_PERM = 5,000. One-sided: the hypothesis is `ρ_kernel > ρ_incumbent`.

### 5.2 N floor for the flip criterion

**Episode-clustered n floor for the flip criterion: 300 independent episode clusters** with both `kernel_rank_score` and `good_21d` (or `good_63d`) non-null in the prospective ledger.

Rationale: the P1.1 study found ρ_21d ≈ −0.08 for the strongest individual feature (dist_52wh) at G = 184 week clusters, which provided adequate power for a single-feature separability question at the whole-pool level. The flip criterion requires detecting a composite score's superiority over the incumbent, which is a smaller expected effect on board fires alone (the incumbent already selects for quality). The G = 300 episode-cluster floor is chosen to maintain 80% power for a ρ difference of ~0.02 (conservative, given the weak F2 effect and the composite nature of the score), based on the Fisher-z standard error at G = 300 (SE ≈ 1/√(300−3) ≈ 0.058; a ρ difference of 0.02 is ~0.34 SE, below 80% power — **the flip criterion requires a ρ difference that yields at least 80% power at the observed n at the time of evaluation**). At each quarterly evaluation (§5.4), the minimum detectable ρ difference at 80% power is computed and printed alongside the observed difference; if the flip fires with less than 80% power available, it is noted as marginal and Fable decides.

**The n floor of 300 is the MINIMUM before any flip evaluation.** The flip criterion is not evaluated before 300 independent episode clusters have accrued in the prospective ledger.

### 5.3 Wilson lower-bound on the shadow ledger beating incumbent

Per Article 2 / R6: the flip criterion additionally requires the shadow ledger to demonstrate that the kernel-rank `good_21d` rate among **top-quartile kernel-rank fires** (fires in the top 25% of `kernel_rank_score` on their date) beats the incumbent's top-quartile `good_21d` rate, with a Wilson lower bound on the difference exceeding zero at 95% confidence.

Specifically:
- `k_shadow` = count of `good_21d == True` among top-quartile kernel-rank fires (by day) in the ledger.
- `n_shadow` = total top-quartile kernel-rank fires.
- `k_incumbent` = count of `good_21d == True` among top-quartile incumbent-rank fires (by day) in the same ledger (matched by date — same fires compared; the two scores rank the same fire pool).
- `n_incumbent` = total top-quartile incumbent-rank fires.
- Wilson lower bound on the difference: `p_shadow − p_incumbent − z × sqrt(p_shadow(1−p_shadow)/n_shadow + p_incumbent(1−p_incumbent)/n_incumbent)` where `z = 1.645`.

**Flip fires if:** Wilson lower bound > 0.0 AND permutation p_one_sided < 0.10 AND n_episode_clusters ≥ 300.

If the flip criterion fires, Fable is alerted; the switch from shadow to live is NOT automatic — it requires Fable approval and a PR.

### 5.4 Evaluation cadence

The shadow-vs-incumbent comparison is run **quarterly** (approximately every 63 trading days — one full verdict-grade horizon) once the prospective ledger has ≥ 300 episode clusters with non-null `good_21d` outcomes. Results are logged to `data/signal_archive/kernel_rank_eval_log.json` (R9 — not committed to git). Each quarterly log entry prints: n_episode_clusters, ρ_kernel, ρ_incumbent, ρ_difference, permutation p, Wilson lower bound, and whether the flip criterion fires.

### 5.5 Kill criterion

If the flip criterion has **not** fired within **24 months** of the first forward-ledger row (the shadow accrual window), the kernel-rank design is retired:

- The shadow column is removed from the board output.
- The incumbent rank stands unchanged.
- Registry records `kernel_rank: validation_status: retired_not_promoted`.
- This PREREG records the verdict in the masterplan §9 status log.

The 24-month window is the accrual window. It is pre-registered. It may not be extended post-hoc without a new Fable ruling.

---

## 6. BH family and multiplicity control

This is a **design study, not a hypothesis-test study** — the primary computation is cell posterior construction and shadow logging, not a p-value family over a battery of tests. Multiplicity control applies to two components:

**Component A — Cell construction (diagnostic):** The per-feature, per-cell Wilson lower bounds are computed on historical replay data. This is NOT a new hypothesis test family — the features were selected by P1.1 (already BH-corrected) and the posteriors are shrinkage estimates, not p-value-gated discoveries. No new BH correction is applied to cell construction outputs. Cell outputs are diagnostic / display-only.

**Component B — Shadow-vs-incumbent comparison (§5):** The flip criterion uses a single pre-registered primary test (Spearman ρ difference on `good_21d`) and a single secondary test (`good_63d`). BH family = {primary, secondary} = m = 2 tests per quarterly evaluation. FDR q ≤ 0.10 across these two. The primary flip criterion (§5.3 Wilson lower bound check) is evaluated at q = 0.10 on the primary test; it is not corrected against the secondary, as the secondary is confirmatory only.

---

## 7. Trial ledger (pre-registered; no unregistered variants)

The following decisions are pre-registered and immutable before any run:

| Decision | Value | Justification |
|----------|-------|---------------|
| Feature set | {dist_52wh, cohort_washout_proximity, ext_z, ext_atr, weekly_phase} | P1.1 BH survivors |
| Bucket count (continuous features) | 4 quartiles | Pre-specified; no search |
| weekly_phase treatment | Categorical (6 named buckets + UNKNOWN fallback) | P1.1 REVIEW A4 advisory |
| K_SHRINK | 10 | kernel.py K_POOL default |
| Wilson z | 1.645 | One-sided 95%, matching qledger convention |
| Horizons | {21d, 63d} | P1 registered horizons |
| Episode n floor (cell THIN threshold) | 25 episode clusters | P1 study n floor |
| Episode n floor (flip criterion) | 300 episode clusters | Pre-registered (§5.2) |
| Feature combination weights | |ρ_21d|-proportional (dist_52wh 0.34, cohort_washout 0.31, ext_z 0.28, ext_atr 0.24) | P1.1 survivors ranked by |ρ_21d| |
| cohort_washout_proximity inclusion | Requires P2.1b concordance GO artifact at `p1_runs/P1_3/concordance_check.json`; else omitted (logged); fallback weights 0.86 | P2.1b §3.3 (single concordance authority) |
| weekly_phase combination weight | 0.00 (excluded from weighted sum) | Non-directional KW; categorical separator |
| Accrual window (kill criterion) | 24 months from first ledger row | Pre-registered |
| Shadow cadence | Quarterly (every ~63 trading days after n ≥ 300) | Pre-registered |
| Flip criterion | Wilson lower bound > 0.0 AND perm p_one_sided < 0.10 AND n_clusters ≥ 300 | Article 2 / R6 |

Any deviation from the above = new recorded trial in the engine trial ledger. No deviation may be adopted without being logged as a new trial.

---

## 8. Data handling

**Data source (strict):** `data/replay/replay_boarded.parquet` for historical cell construction. Live prospective fires read from the board output pipeline (the same code path that populates `us_standouts.json`) for ongoing ledger append.

**Era handling:** Historical cell construction uses only `verdict_grade == True AND survivor_bias == False` rows (the 49,939 verdict-grade fires, effective window 2022-06-30 → last-full-replay-date). No pre-2021 rows are used in cell construction. If any pre-2021 row appears (survivor_bias = True), it is excluded with a warning logged.

**Feature freeze (PIT honesty):** all features read from the replay artifact at signal-bar time (PIT-stamped by P0.1). No feature is re-computed. For prospective (live) ledger rows, features are computed from the production code path at signal time (the same PIT guarantee applies as for the replay).

**Forward-return grading:** for prospective rows, `fwd_ret_21` and `fwd_ret_63` are filled as they accrue (the grader runs each night and fills any rows whose horizon has elapsed). `good_21d` and `good_63d` are set when the terminal state is determinable (stopped / dead_money / cushioned / clean_liftoff at the relevant horizon). Rows with `good_21d == null` are excluded from the flip criterion computation but remain in the ledger for continuity.

---

## 9. Outputs

### 9.1 Historical cell table (one-time, at build time)

File: `data/signal_archive/kernel_rank_cells.parquet` (R9 — not git-committed). Schema:

| Column | Description |
|--------|-------------|
| `feature_name` | Feature identifier |
| `feature_bucket` | Bucket label (Q1/Q2/Q3/Q4 for continuous; category name for weekly_phase; NEAR/NOT_NEAR for washout) |
| `regime_bucket` | Regime label or __all__ / __unstamped__ |
| `horizon_days` | 21 or 63 |
| `n_raw` | Raw fire count in cell |
| `n_eff` | Episode-cluster-collapsed count |
| `k_eff` | Episode clusters with good_outcome = True |
| `p_raw` | k_eff / n_eff (diagnostic) |
| `p_parent` | Parent cell shrunken proportion (the shrinkage target) |
| `shrunken_p` | Shrunken posterior proportion |
| `wilson_lo` | Wilson lower bound (the kernel-rank score contribution) |
| `thin_flag` | True if n_eff < 25 |
| `proxy_sourced` | True if any feature in the cell key is proxy-sourced |
| `parent_cell_used` | True if THIN caused fallback to parent |

### 9.2 Forward ledger (ongoing)

File: `data/signal_archive/kernel_rank_ledger.parquet` (R9 — not git-committed). Schema per §4.2.

### 9.3 Quarterly evaluation log

File: `data/signal_archive/kernel_rank_eval_log.json` (R9 — not git-committed). Per §5.4.

### 9.4 Shadow column in board output

Internal only. Not user-visible. Appended to the in-memory board frame; logged to ledger. Not written to `site/factordata/us_standouts.json` in v1.

---

## 10. Report contract

Report file: `research/entry_intel/P3_KERNEL_RANK_BUILD_REPORT.md` (produced at first build; updated quarterly with flip criterion results).

Required sections:
1. **Preamble:** replay artifact path + MD5, era citation (P0_MEASUREMENT_MEMO version+date), n fires total, n episode clusters, proxy-source status of each feature dimension.
2. **Feature bucket breakpoints:** percentile values for continuous features, computed on the verdict-grade fire population.
3. **Cell table summary:** n cells built, n cells THIN, n cells with parent fallback. Top-10 and bottom-10 cells by `wilson_lo` at 21d. Distribution of `wilson_lo` values at 21d and 63d.
4. **Combination weight confirmation:** printed feature weights, and whether cohort_washout_proximity is included or omitted (proxy-source check result).
5. **Leak audit:** fill rule confirmation (next-bar), feature freeze confirmation (signal-time PIT), era boundary confirmation, proxy-sourced dimensions listed.
6. **Plain-English box** (one paragraph; required by §3 plain-language law).
7. (Quarterly additions) **Shadow-vs-incumbent evaluation:** n_episode_clusters in ledger, ρ_kernel, ρ_incumbent, ρ_difference, permutation p, Wilson lower bound, flip criterion status (fires / does not fire), power check (minimum detectable ρ difference at 80% power at current n).

---

## 11. Downstream routing

**If flip criterion fires:**
- Alert Fable. Do NOT auto-apply. The board sort order change requires a Fable-approved PR.
- Governance ledger entry (Neural Web Article 2): shadow_period_start, shadow_period_end, n_episode_clusters_at_flip, flip_criterion_stats.
- P4.1 / P4.2 (species-desk adapter → qledger) may proceed with the kernel_rank cells as entity claims.
- A new PREREG is required for any user-visible board reordering (that is a separate registered decision, not authorized by this PREREG).

**If flip criterion does not fire within 24 months:**
- Kernel-rank retired (§5.5). Incumbent stands.
- Registry: `kernel_rank: validation_status: retired_not_promoted`. Masterplan §9 entry.
- Retire the shadow column from the board pipeline. No user impact.

**If the study cannot complete cell construction (blocker):**
- Return a structured blocker report to Fable (per §7 masterplan delegation protocol). Do not improvise.

---

## 12. Boundary statement (explicit)

The following are OUT OF SCOPE for this PREREG and may not be executed under its authority:

- Any change to the visible sort order of `us_standouts.json` or any board page.
- Any use of `kernel_rank_score` in the gate cascade (T1–T4) — gate changes require their own PREREG per R4.
- Any promotion of `kernel_rank_cells` to qledger entity claims — requires P4.1 PREREG.
- Any Neural Web Article-3 authority grant based on the kernel-rank cells — requires the Article-3 n-floor and Wilson lift thresholds at the engine family level.
- Any new species registration under the kernel-rank design — the species ladder chip stage for the 5 features is initiated by P1.1 survivors forwarding to P3; ledger-graded bonus and gate_weight promotions require separate PREREGs.
- Any extension of the feature set beyond the P1.1 5 survivors — a new PREREG is required for any additional feature.
- Any modification of K_SHRINK, the Wilson z, or the bucket definitions after results are observed.

---

## §5 Conformance Checklist

- [ ] Cites `P0_MEASUREMENT_MEMO.md v1.0 (2026-07-04)` + §6 v1.1 amendments in preamble.
- [ ] Primary window = `2022-06-30 → last-full-replay-date` (v1.1 effective; 250-bar MTF warmup applied).
- [ ] Verdict-grade statistics on `survivor_bias = false` rows only (the 49,939-fire population).
- [ ] Confirms via per-row source stamp that all cell-construction rows are Massive-sourced.
- [ ] Pre-2021 rows: excluded (none exist in artifact; logged with warning if any appear).
- [ ] `horizon_censored` rows excluded (7,701 rows pre-excluded via verdict_grade).
- [ ] Mandatory stamp text printed with era census missing-fraction.
- [ ] Returns INSUFFICIENT-POWER (honest null) rather than borrowing pre-2021 rows if n_eff < 25.
- [ ] Shadow column only in v1 — no board reordering.
- [ ] Proxy-source check for cohort_washout_proximity performed at build time: reads `research/entry_intel/p1_runs/P1_3/concordance_check.json`; GO verdict required (P2.1b §3.3 is the authoritative concordance definition; P3 does not define an independent bar); omission fallback (weights 0.86) logged.
- [ ] Article 2 flip criterion: pre-registered, episode-clustered n floor 300, Wilson lower bound > 0, perm p < 0.10.
- [ ] Kill criterion: 24-month accrual window, pre-registered.

---

## In plain English

We have five features that P1 showed correlate with whether a stock works out well after the signal fires. Now we want to combine them into a single data-driven score — the kernel rank — and measure whether that score beats the current hand-assembled formula over time. But before we can let it affect anything users see, we have to run it in parallel ("shadow") and prove it wins.

Here is the process: for each combination of feature value, market regime, and time horizon, we estimate the probability of a good outcome using a conservative statistical approach that penalizes cells with few observations. The five features contribute to a weighted average score, with more weight given to the features that showed stronger effects in Phase 1. That score is saved beside every signal but never used to change the ranking.

The score's predictions are logged alongside the actual outcomes as they arrive. Every three months we check: does the new score predict good outcomes better than the current formula? If yes, and the Wilson lower bound on the difference is positive, and we have at least 300 independent episodes of evidence — the flip criterion fires. That does not automatically switch anything; Fable reviews the evidence and approves (or declines) the change. If the score fails to beat the incumbent within two years, it is retired and the current formula remains in place.

Nothing changes for users until and unless the flip criterion fires and Fable approves the switch.

---

*Registered 2026-07-05. Immutable after Fable approval. Results recorded in P3_KERNEL_RANK_BUILD_REPORT.md; this document is never edited to accommodate observed outcomes.*

*2026-07-05 — red-team blocking fixes applied (P2_REDTEAM.md) incl. Fable rulings R-P2.1 (flip floor 100 clusters + 2 quarters) and R-P2.2 (single concordance authority).*

---

## Amendment (Fable, 2026-07-05)

*Source: REVIEW_P3.md ADVISORY-1; resolves the prereg-internal flip-floor inconsistency before the evaluator wave is built.*

**R-P2.1 scope clarification — flip-floor ownership.** The approval-stamp header (and the matching footer) of this document cite Fable ruling R-P2.1 as "flip floor = 100 clusters + 2 quarters." That citation is program-wide context: R-P2.1 governs the **P2.1a anti-chase gate** flip — specifically the shadow-ledger flip condition for promoting F3 as a hard gate (100 episode clusters AND 2 full quarters of shadow accrual before the gate may fire). It does NOT override the P3 flip criterion, which is an independently registered and independently evidenced decision. The operative body of this document (§5.2, §5.4, §7 trial ledger, §11 downstream routing, and the plain-English summary) uniformly specifies **300 independent episode clusters** as the kernel-rank shadow flip floor, with no "2 quarters" clause. The build's `build_meta.json` encodes `n_floor_episode_clusters: 300` and that value is **correct**. The evaluator (`evaluate_kernel_rank_flip.py`, scheduled for a subsequent wave) must implement exactly §5.2's registered criterion: n_episode_clusters ≥ 300 AND Wilson lower bound > 0.0 AND permutation p_one_sided < 0.10. No "2 quarters" cadence gate applies to P3's flip criterion.
