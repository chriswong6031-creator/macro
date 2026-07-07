# PM0 Price-Memory Bundle — PRE-REGISTRATION (phase-0, dispatched-in)

**STATUS: APPROVED — Fable 2026-07-06 (see §APPROVAL at end; original draft-gate text follows). Execution remains gated on §APPROVAL's execution contract (feature-build QA + calibration controls); the run is NOT dispatched by the approval itself.**

*(original draft header:)* DRAFT — pending Fable-tier approval. This document does not authorize execution. No study code runs, no feature artifact is built for verdict purposes, before a §APPROVAL block is appended by Fable and committed.

**Study:** EI-PM0 price-memory bundled phase-0. **Program:** Entry Intelligence (EI). **Masterplan:** `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (dispatched-in lane; see provenance). **Registered:** 2026-07-06 (before any run). **Author:** Fable (main loop) — drafted directly because the bundle is a cross-program dispatch requiring ruling-level scoping; Opus red-team review mandatory before approval.

**Revision r2, 2026-07-06:** Opus red-team round 1 returned BOUNCE; all four blocking findings adjudicated ACCEPTED and fixed in this revision — **B1** primary p-value changed from cluster bootstrap to the family's settled episode-label permutation null (the draft had recycled the exact P1.3 round-1 defect); **B2** grid-B DEAD_MONEY is degenerate on the real substrate (43 events in 49,939 verdict-grade fires) → those trials are UNREGISTERED as a substrate limitation and a run-start event floor now guards every remaining trial; **B3** PM5 shares coverage measured at 50.2% (59.3% ceiling at infinite staleness; 603/992 fire tickers in the statements panel) — below the pre-registered 60% floor — so PM5 is pre-declared `data_blocked` rather than sold as a live test; **B4** shares-denominator sanity fence added. Advisories A1–A7 absorbed. Family m: 30 → **20**.

**Revision r3, 2026-07-06 (pre-approval):** **DT-R14 landed on main mid-registration** (`research/TIME_CONFOUND_EXPOSURE_AUDIT.md`, #1755): on regime-limited replay cohorts, episode (ticker×ISO-week) resampling/permutation without a calendar-time control is anti-conservative — the effective independent N is calendar months, not episodes — and the audit's RR-1 instructs that replay-surface preregs carry month-block resampling or within-period demeaning **before they are written**. PM0's features are calendar-clustered by construction (overhead supply / below-AVWAP concentrate in drawdown months; gap-overhead concentrates post-crash), i.e. the favorable/unfavorable arms draw from different calendar-month mixtures — the exact confound. Primary inference upgraded to a **within-calendar-month contrast with month-block bootstrap** (the P1.2 / BD-ECON1 / S13-class compliant structure); the r2 episode-label permutation is demoted to a labeled non-time-controlled diagnostic. §4.2, §7, §9 amended accordingly.

**Provenance chain (why this study exists and why now):**
1. **Signal Commons R2** (`SIGNAL_COMMONS_MASTERPLAN_BY_FABLE.md` §2, 2026-07-05): the price-memory bundle — AVWAP distance, volume-at-price shelves, gap-fill maps, overhead supply, float turnover — stays parked behind EI P1.3; on P1.3 completion it runs as **ONE bundled phase-0 inside the EI program**, one family, one FDR budget.
2. **EI P1.3 COMPLETE** 2026-07-05 (masterplan §9, round 2 CONFORMANT) — the gate condition is satisfied.
3. **DT-R7** (`DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md` §3, PR #1732, 2026-07-06): the bundle is declared **DISPATCHABLE inside EI** as one family with one FDR budget; the DCA policy object around it is KILLED (authority smuggling); routing come-back 2026-07-20 is satisfied early by this registration.

**Blocking gates (ALL must clear before the study executes):**
1. Fable §APPROVAL block appended to this file and committed (no execution on DRAFT).
2. Feature artifact built and its QA gates pass (§4.4) — the builder never reads outcome columns.
3. Both calibration controls pass (§7) — negative permuted-labels and positive injected-effect.

**Constitution:** EI masterplan §3 (inherited law) → Setup Species constitution (`SETUP_SPECIES_MASTERPLAN_BY_FABLE.md` §1): PREREG before run; capped config grids (this study has NO grid — every window, band, threshold, and anchor is a single frozen choice); any post-hoc variation = new recorded trial; BH q≤0.10 per study family; both-halves sign stability; episode-clustered n floors; fills strictly after signal bar; survivor-bias stamps; verdicts on safety-net axes at the declared rulers.

**Inherited rulings binding on this study:**
- **Signal Commons R2:** one bundle, one family, one FDR budget, inside EI. No sub-component gets its own separate study or its own multiplicity budget.
- **DT-R7 / DT-R2 (hard ceiling, permanent):** every output of this family is **display-only candidate at most**. No artifact of this family may ever emit price-level trade-instruction fields — `nearest_support`, `invalid_if_below`, `no_chase_above`, `max_add`, `invalid_if`, or any key that expresses a price level as an instruction to act. Support/ladder **level values** may only ever appear as display-only context via a separate Fable build ruling; this study emits research verdicts only, zero site artifacts.
- **EI R7 (additive-lanes law):** noted for completeness — this study tests **no gate and no rank weight**; it is pure separability (phase-0). Any gate or rank-weight design for a survivor requires its own PREREG (P2.1-style). Fire-rate impact tables are therefore N/A here by construction.
- **EI R9:** the feature artifact lives in `data/replay/` on the canonical checkout, never committed (R2-eligible later).
- **Era law:** `P0_MEASUREMENT_MEMO.md` v1.1 (§1 era table + §5 checklist + §6 amendments) binds in full (§1 below).
- **DT-R14 (time-confound law, `TIME_CONFOUND_EXPOSURE_AUDIT.md` + DT masterplan §7, 2026-07-06):** passing within-unit permutation controls does not certify CI calibration under cross-time correlation; verdict-grade inference on the 2021+ replay cohort must carry a calendar-time control in the PRIMARY statistic. This study's primary is a within-calendar-month contrast with month-block bootstrap (§4.2) — episode-only machinery appears strictly as a labeled diagnostic.
- **EI R1 (population note):** R1 mandates the PRE-GATE pool for separability of fields used as gates (restriction-of-range). The PM features are not gates and never have been — no restriction-of-range on these axes exists in the fire pool. The deployment question is "among fires, do these features separate outcomes?", so the population is **fires** (§1). A descriptive near-miss context read is printed (§8), not tested.

---

## 0. Plain-English summary

> DannyTrades-style "price memory" says a chart remembers where volume traded: entries above the volume-weighted cost of the recent base, near thick volume shelves, without trapped sellers overhead, without an unfilled breakaway gap looming above, and after the float has churned into fresh hands should stop out less and cushion more. None of that has ever been tested on our production fire tape — it has been parked twice (EI §2, Signal Commons R2) precisely so it would arrive here as one honest, budgeted test instead of five separate fishing trips.
>
> This study computes the price-memory features point-in-time for every verdict-grade production fire and asks one question per feature: do favorable values separate stop-out / dead-money / cushion outcomes at our two declared rulers? Because these features cluster in calendar time by their nature (a market crash puts *every* stock under heavy overhead supply at once), the comparison is made month by month and then averaged — so "this feature works" can never secretly mean "2022 was a bad year" (the DT-R14 lesson, learned the same day this was written). One FDR budget covers the whole family — twenty trials across four features. The fifth feature, float turnover, cannot run yet: our EDGAR shares panel covers only half the fire tape, so it is registered as data-blocked with a printed unblock condition instead of being quietly dropped or dishonestly run. Survivors earn, at most, the right to a display-only chip and a separate promotion prereg. Failures are recorded as falsified and the bundle closes. Nothing here may ever tell anyone a price at which to act.

---

## 1. Population, era, and substrate

**Population:** rows of `data/replay/replay_boarded.parquet` with `verdict_type == 'fire'` and `verdict_grade == True`. No near-misses, no rejections in the verdict population (near-miss context read is §8, descriptive only). Frozen substrate reference (post #1466): 961,656 rows; 57,640 fires, of which **49,939 verdict-grade** in **22,295 episodes** (`episode_id`) — 22,295 is the operative episode count for every floor and half-split in this study (the oft-quoted 25,783 includes non-verdict-grade fires and is NOT the denominator here); universe 1,033 tickers (board ∪ PIT S&P500, delisted ex-members restored per memo §6 item 5).

**Measured state-event counts on this population (verified 2026-07-06, red-team round 1):** grid A `state_8_21` = STOPPED 19,105 / CLEAN_LIFTOFF 15,498 / DEAD_MONEY 8,891 / CUSHIONED 6,445; grid B `state_15_126` = STOPPED 31,372 / CLEAN_LIFTOFF 16,549 / CUSHIONED 1,975 / **DEAD_MONEY 43**. Grid-B DEAD_MONEY is unmeasurable on this substrate (43 events); its trials are **UNREGISTERED** (§5) — a substrate limitation recorded, not a hypothesis tested and failed.

**Era (v1.1 conformance, mandatory):**
- Effective verdict window = **2022-06-30 → 2026-07-02** (memo §6.1; the nominal 2021-07-06 window does not exist in the ledger — the 250-bar Massive warmup consumes it).
- Canonical input = `data/replay/replay_boarded.parquet` **ONLY**. Never the `replay_2*.parquet` parts glob (silently-null `rs_sector_quartile`, memo §6.2).
- `survivor_bias == True` rows excluded from all verdict computation; routed to the labeled context appendix.
- `horizon_censored` rows excluded per-ruler, tracked separately: a trial on grid A (§4.1) uses rows with a non-null `state_8_21`; a trial on grid B uses rows with a non-null `state_15_126`; exclusion counts printed per trial. The exact semantics of the `horizon_censored` flag are logged in the preamble; if the flag and the per-grid state nullness disagree, HALT and report. **Measured note (red-team A1):** on the current substrate, `verdict_grade == True` already implies `horizon_censored == False` and both states non-null for all 49,939 rows — both grids share an identical row set and the exclusion counts will print as zero. The guard is retained for artifact regeneration, not as a live differentiator between grids.
- `board_rank_unresolved` rows: N/A to this study's verdicts (population is fires, not board-stage rejections); stated for conformance (memo §6.3).
- Any concordance citation uses the on-disk 98.5%/12-name value (memo §6.4).
- INSUFFICIENT-POWER is returned honestly wherever a floor is not met (memo §6.6); the 57-ticker pilot ledger is never used.

**§5/§6 conformance checklist** (confirmed in the run preamble):
- [ ] Cites `P0_MEASUREMENT_MEMO.md` v1.1 (2026-07-05) in the preamble.
- [ ] Effective window 2022-06-30 → 2026-07-02; verdict stats on `survivor_bias == False` rows only.
- [ ] Canonical `replay_boarded.parquet` (path + MD5 logged); parts glob untouched.
- [ ] Per-ruler censoring handled and counted; mandatory era stamp text printed.
- [ ] INSUFFICIENT-POWER / INSUFFICIENT-DATA returned where floors fail; no verdict language on failed floors.

**Column-name mapping:** the run script resolves the frozen column list {`ticker`, `signal_date`, `episode_id`, `survivor_bias`, `verdict_type`, `verdict_grade`, `horizon_censored`, `state_8_21`, `state_15_126`, `fwd_ret_21`, `fwd_ret_126`, `ext_z`, `ext_atr`, `dist_to_52wh`, `near_52wh`, `rs_63d_return`, `align_quality`, `washout_proximity`} at startup, logs the mapping and the exact terminal-state enum of both grids to the preamble, and HALTS on any absence or unexpected enum. Name-mapping is fixed pre-run; no post-hoc adjustment.

**Episode-cluster n floor:** a trial whose favorable OR unfavorable group contains fewer than **25 unique `episode_id`** values is labeled **THIN** and cannot ship, regardless of p.

**Event floor (red-team B2 guard, checked at run start before any p-value is computed):** a trial is **INSUFFICIENT-DATA** if its target state has fewer than **50 events** in the trial's analysis population, or fewer than **10 events** in either group. Such trials are removed from the BH family with **m decremented and the decrement logged in the preamble** (P2.5 §3 thin-check-decrement precedent). The cluster floor alone cannot catch this failure mode — a group can hold 25+ episodes and ~0 events of a rare state (grid-B DEAD_MONEY is the proof). On the measured substrate all 20 registered trials clear this floor comfortably (minimum: grid-B CUSHIONED, 1,975 events).

---

## 2. The five sub-components (frozen definitions)

All features are computed **as of the signal bar** (data ≤ signal date only) from the Massive whole-market store (`data/massive_stock_day/<TICKER>.parquet`, raw daily OHLCV, first bar 2021-07-06), split-adjusted by the replay pipeline's own `split_adjust()` (imported from `scripts/replay_standout_pipeline.py`, never reimplemented), with the same inferred per-bar factor applied to open/high/low (÷ factor) and volume (× factor). **Factor derivation (red-team A3):** `split_adjust()` returns the adjusted close series, not the factor; the builder recovers the per-bar factor as `factor_t = raw_close_t / adjusted_close_t` — exact by construction, zero reimplemented detection logic. The reference price for every feature is the **signal-bar adjusted close** `close_s` (entry is the next close per P0.1 fill law, so signal-close features are strictly pre-entry information). Trailing window **W = 250 bars** ending at the signal bar inclusive; rows with fewer than **200 available bars** get NaN for all W-window features (counted in the coverage table). Where a fraction is volume-weighted, the weight is **dollar volume** `tp_t × volume_t` with `tp = (high+low+close)/3` — dollar volume is split-invariant by construction, removing adjustment error from PM2/PM4.

**Split fence (applies to every feature):** `split_adjust()` leaves non-clean jumps (|log return| > threshold, not snapping to a common split ratio) unadjusted by design. Any such unadjusted split-suspect bar inside a row's feature window ⇒ that row's window-dependent features are NaN (fence count printed). This is the cohort-metrics precedent: split-suspect names go honestly missing, never poisoned.

### PM1 — AVWAP distance (anchored at the base low)

*Mechanism:* the anchored VWAP from the major low is the average cost of every share traded since the flush. Price above it = the post-low buyer base is in profit (support below, no trapped-at-higher-prices sellers from the base itself); price below it = the average post-low buyer is under water and supplies rallies.
*Operationalization:* anchor `a` = date of the minimum adjusted close in W (most recent bar if tied). `AVWAP = Σ_{t=a..s}(tp_t·v_t) / Σ_{t=a..s}(v_t)` on adjusted series. `pm1 = close_s / AVWAP − 1`. Degenerate anchor (a = s) yields pm1 ≈ close/tp − 1; accepted as-is.
*Split (binary, frozen):* favorable = `pm1 ≥ 0`.
*Distinction from live surface:* the live `poc_proxy` (`engine/dannytrades.py:174`, dt_contra chip) is a **rolling** 126d VWAP; PM1 is **anchored**. The redundancy fence (§4.3) tests whether the distinction is real: `poc_dist_126 = close_s/poc_proxy(126) − 1` is computed as a reference column, and PM1 is REDUNDANT if |ρ| ≥ 0.8 against it — a rolling-VWAP distance is already live and display-only; a redundant anchored variant has nothing to add. **Weighting note (red-team A5):** `poc_dist_126` uses `poc_proxy` verbatim — **close-weighted** rolling VWAP (live-chip fidelity) — while PM1's AVWAP is **tp-weighted**; the fence deliberately compares information content across the two constructions, not formula identity.

### PM2 — Volume-at-price shelf density

*Mechanism:* a thick volume shelf at the entry price is agreed value — dense prior ownership that absorbs selling (support). Entering in a low-volume air pocket means the nearest dense ownership is elsewhere (often above = supply, or below = far support).
*Operationalization:* `pm2 = Σ dollar-volume of bars in W with |tp_t/close_s − 1| ≤ 0.03` ÷ `Σ dollar-volume over W`. Daily-bar approximation is honest and stated: each day's volume sits at its typical price; no intraday distribution is fabricated.
*Split:* favorable = `pm2 ≥ population median` (median over defined values of the verdict-grade fire population, computed once, logged in the preamble before outcomes are joined). **Disclosure (red-team A7):** a full-era population median lets later fires inform the threshold applied to earlier fires — a mild global-information leak accepted as the family convention (identical to P1.3 F1's approved median split); it affects the threshold constant only, never a per-row feature value.

### PM3 — Gap-fill map (unfilled overhead breakaway gap)

*Mechanism:* an unfilled gap-down overhead is a cohort of holders who never got an exit — resistance that sells into the first rally that reaches it. A clean sky (no unfilled overhead gap within reach) removes that seller.
*Operationalization:* on adjusted O/H/L in W: down-gap at t if `high_t < low_{t−1}`, zone = `[high_t, low_{t−1}]`; the gap is *unfilled at s* if no bar u ∈ (t, s] has `high_u ≥ low_{t−1}` (full traverse). `pm3 = 1` if any unfilled down-gap zone has its lower edge inside `(close_s, close_s × 1.10]` — overhead and within reach.
*Artifact fences:* a candidate gap bar that is itself a split-suspect unadjusted jump ⇒ row NaN (split fence above); a gap whose relative size `low_{t−1}/high_t − 1 > 0.25` is ignored as artifact-suspect on a raw store (count printed — this trims a tail of data-quality events, accepted as a frozen conservative choice, not tunable post-hoc). **Band ownership (red-team A4):** `split_adjust()` only inspects close-to-close jumps beyond log(1.4) (≈ −28.6%), so the 25–40% band is owned by THIS fence — any gap that large is discarded as artifact-suspect rather than trusted. Residual contamination from odd-ratio splits producing gaps ≤ 25% (e.g. 4:3) is accepted and disclosed; such ratios are rare and the affected rows dilute toward null rather than manufacture signal.
*Split (binary, frozen):* favorable = `pm3 == 0`.

### PM4 — Overhead supply

*Mechanism:* the fraction of recent volume that traded above the current price measures trapped holders overhead — everyone who bought higher and is waiting to "get back to even." Light overhead (near highs, or a base that has absorbed its history) = less supply into strength.
*Operationalization:* `pm4 = Σ dollar-volume of bars in W with tp_t > close_s` ÷ `Σ dollar-volume over W`.
*Split:* favorable = `pm4 ≤ population median`.
*Known collision, pre-declared:* PM4 is mechanically related to `dist_to_52wh` (a P1.1 separability survivor). The redundancy fence (§4.3) exists mostly for this row: if PM4 is just 52-week-high distance wearing a volume costume, it is REDUNDANT and cannot promote regardless of its p-values.

### PM5 — Float turnover — **PRE-DECLARED `data_blocked` (red-team B3); registered but SUSPENDED, not in the live family**

*Mechanism:* cumulative volume since the flush relative to shares outstanding measures ownership rotation. A float that has fully churned holds fewer trapped legacy sellers; the register has been rewritten at current prices.
*Operationalization (frozen now for the future run):* `pm5 = Σ_{t=s−62..s}(volume_t, signal-date share units) / SO_pit(s)` — 63-bar share turnover. `SO_pit(s)` = `shares` from the latest `data/edgar/statements_quarterly.parquet` row with `filed ≤ s` and `s − filed ≤ 270d`, converted to signal-date share units via the same inferred split-factor series (a split between `period_end` and s scales SO; both numerator and denominator end in the same units). Any split-suspect unadjusted jump in `(period_end, s]` ⇒ NaN.
*Denominator sanity fence (red-team B4):* the statements panel carries corrupt tails (measured: `shares` min = −8.9e8, max = 5.1e14). `SO_pit` must satisfy `0 < shares < 1e11` or the row is NaN with reason code `so_corrupt` (counted in the §4.4 QA census). The 270d-stale + positive + banded denominator is the only accepted form.
*Denominator honesty:* shares outstanding, not free float — labeled **FLOAT-PROXY** in every output (we have no free-float source; insider/strategic holdings are inside the denominator and bias pm5 downward for closely-held names — direction stated, not hidden).
*Split (frozen for the future run):* favorable = `pm5 ≥ population median` (rotation hypothesis: churn is cleansing).
*Why blocked (measured 2026-07-06, red-team round 1):* coverage of the verdict-grade fire population with a `filed ≤ signal_date`, staleness ≤ 270d shares row = **50.22%** (25,077 / 49,939); the ceiling at infinite staleness is **59.25%**, because only **603 of 992** fire tickers appear in the statements panel at all. The pre-registered 60% floor fails under every staleness reading — running PM5 now would be a coin-flip-coverage study sold as a test of the fire tape.
*Unblock condition (printed clock):* EDGAR statements-panel coverage extended to ≥ 60% of the verdict-grade fire population under the 270d staleness rule (concretely: the panel holds 1,331 tickers but only 603 of the 992 fire-universe tickers are among them — the collector must cover more of the fire universe, mostly delisted/small names outside the current panel). On unblock, PM5's six trials (2 grids × 3 states, grid-B DEAD_MONEY excluded per §1 if still degenerate) run as a **labeled family extension** — their own BH family at q ≤ 0.10, debited to the `price_memory` family ledger, with fresh calibration controls; they are never retro-pooled into the m=20 family below (pooling across run dates would be statistically meaningless and is pre-forbidden).

---

## 3. What is deliberately NOT in this study

- **No thresholds searched.** Every constant above and in §4.2 (250/200 bars, ±3% shelf band, +10% gap reach, 25% gap-size fence, 63-bar turnover, 270d staleness, shares sanity band, 0.8 redundancy bar, median splits, 50/10 event floors, 24-qualifying-month / ≥5-rows-per-group-per-month floors) is a single frozen choice. Alternatives = new recorded trials under species law, each debited against a future family.
- **No gate mode, no rank-weight mode** (unlike P1.3, which ablated already-mechanism-validated factors). Phase-0 separability only. Promotion design is a separate PREREG.
- **No composite.** The five features are never summed, averaged, or fused into a "price-memory score" — that is the forbidden composite shape (Signal Commons R3 analog; DT-R3 precedent).
- **No support-level outputs.** The study prints distributions, deltas, and verdicts. It does not emit per-ticker level values at all.
- **No intraday fabrication.** Daily bars only; the volume-at-price approximation is disclosed wherever pm2/pm4 are reported.

---

## 4. Design

### 4.1 Rulers (verdict grids)

The replay carries two pre-existing terminal-state partitions — the program's declared rulers:
- **Grid A = `state_8_21`** (8% stop / 21-bar horizon — swing ruler), paired diagnostic return `fwd_ret_21`.
- **Grid B = `state_15_126`** (15% stop / 126-bar horizon — position ruler), paired diagnostic return `fwd_ret_126`.

Terminal states per grid: STOPPED / DEAD_MONEY / CUSHIONED / CLEAN_LIFTOFF (exact enum logged at startup; HALT on mismatch). Verdict states per trial: STOPPED, DEAD_MONEY, CUSHIONED (safety-net axes). CLEAN_LIFTOFF deltas are printed as context (§8), not tested — P1.3 convention.

### 4.2 Statistic and test (exact, frozen)

For each trial (feature F, grid G, state S), on the trial's analysis population (verdict-grade, era-clean, non-censored-at-G, feature defined):
- **Statistic (within-calendar-month contrast — DT-R14 primary):** let m index calendar months of `signal_date` in the effective window (~49 months). A month **qualifies** for the trial if both groups (favorable, unfavorable) have ≥ 5 rows in m. Per qualifying month: Δ_m = incidence(S | favorable, m) − incidence(S | unfavorable, m), in percentage points. **Δ̂ = Σ w_m Δ_m / Σ w_m** with w_m = harmonic mean of the two group sizes in m (precision weight for a difference of proportions). Because the contrast is taken within month and then averaged, calendar-composition differences between the arms — the DT-W1a failure mode, and the expected shape of these features — cancel in the point estimate as well as the CI.
- **Month floor (checked at run start with the §1 event floor):** a trial with < 24 qualifying months is INSUFFICIENT-POWER; m decremented and logged in the preamble.
- **Pre-registered favorable direction:** Δ̂ < 0 for STOPPED and DEAD_MONEY; Δ̂ > 0 for CUSHIONED.
- **p-value (primary): month-block bootstrap** — resample qualifying months with replacement (B = 5,000, seed 20260706), each drawn month contributing its (Δ_m, w_m) intact; recompute the weighted Δ*; two-sided add-one p from the null-centered pivot: p = (1 + #{|Δ*_b − Δ̂| ≥ |Δ̂|}) / (B + 1). The resample unit is the **calendar month** — the effective independent N of a regime-limited panel (DT-R14 rubric) — so episode and same-month cross-ticker correlation live inside blocks and are never treated as independent draws. Episodes (ticker×ISO-week) nest within months up to week-straddles; an episode is assigned to the month of its first row (straddle count logged).
- **Supporting diagnostics (never verdict-feeding, both labeled NOT TIME-CONTROLLED — DT-R14):** (a) the r2 episode-label permutation p on the pooled Δ (P1.3-v2 scaffolding — episode-majority labeling, cross-episode shuffle, add-one two-sided p; per-draw Δ-incidence statistic is new code); (b) Mann-Whitney U + rank-biserial r on the grid's paired forward return, parametric p printed beside it (param/perm divergence sanity check). Pooled-vs-within-month Δ divergence is itself printed per trial — it is the direct measure of how much calendar composition was doing the work.
- **Multiplicity:** BH at q ≤ 0.10 across the live family, **m = 20 declared at registration** (§5). m decrements only via the §1 event floor and the month floor at run start, logged before any p-value is computed; it never shrinks after results are visible. PM5's suspended trials are NOT slots in this family (§2/PM5).
- **Both-halves sign stability:** era midpoint pre-registered at **2024-06-30** (calendar midpoint of the effective window); each surviving trial's within-month Δ̂ recomputed on `signal_date ≤ 2024-06-30` vs after; sign(Δ̂) must match in both halves or the trial is labeled UNSTABLE and cannot ship. (Supplementary to, not a substitute for, the month-block machinery — DT-R14 rubric: a sign-only halves guard is not a calendar-time control.)

### 4.3 Redundancy fence (pre-registered, promotion-blocking)

Rank correlations (Spearman; for binary PM features, rank correlation on the underlying continuous value where one exists — pm1 distance, pm2/pm4 fractions, pm5 turnover; pm3 uses the binary) computed on the verdict-grade fire population against the frozen reference set:
`{ext_z, ext_atr, dist_to_52wh, near_52wh, rs_63d_return, align_quality, washout_proximity, poc_dist_126}` (the last is the recomputed live-chip rolling-VWAP distance, §2/PM1).

- **|ρ| ≥ 0.8 vs any reference feature ⇒ REDUNDANT:** the sub-component cannot promote in any form regardless of BH outcome (its information is already captured by a live or already-adjudicated column). Verdict recorded as `redundant_with:<column>`.
- **Within-bundle:** pairwise PM×PM correlations printed; if two PM features are mutually |ρ| ≥ 0.8 and both otherwise survive, only the one with the smaller BH-adjusted p on its best surviving trial is promotable; the other is labeled REDUNDANT-WITHIN-BUNDLE (tie-break pre-registered here, not chosen after looking).
- The full correlation matrix is printed regardless of outcomes.

### 4.4 Feature-build contract (blocking QA)

Builder: `scripts/ei_pm0_price_memory_features.py` (new; research-only; **never** enters `daily.yml` or any render path; runs on the canonical checkout on the Mac Studio host — the Massive store is host-only; reads canonical `data/` by absolute path, writes only the artifact below).
Artifact: `data/replay/pm0_features.parquet` — one row per (ticker, signal_date) of the fire population, columns `pm1..pm5`, `poc_dist_126`, per-feature NaN-reason codes. **Not committed** (EI R9).

**Outcome blindness (hard):** the builder reads only `ticker`/`signal_date`/`episode_id`/flags from the replay — never a state, return, MDD, or MFE column. Median splits are computed and logged by the builder from feature values alone. The analysis runner joins outcomes only after the preamble (thresholds, medians, coverage, mapping) is written.

**QA gates (all blocking, results in preamble):**
1. **PIT spot-audit:** 60 random rows recomputed with the price/volume/shares inputs hard-truncated at `signal_date`; every feature must match the artifact exactly (0 tolerance). Any mismatch = lookahead in the builder = HALT.
2. **Split-fence census:** counts of rows NaN'd by each fence (split-suspect window, gap artifact, SO split-span), per feature.
3. **Coverage table:** defined-fraction per feature on the fire population; PM5 floor per §2.
4. **Anchor sanity (PM1):** distribution of anchor ages (s − a in bars); degenerate-anchor count.
5. **Determinism:** builder rerun on a 200-row sample reproduces byte-identical values.

---

## 5. Trial ledger (complete live family `EI_PM0_price_memory`, m = 20)

Per feature PM1–PM4: grid A (8,21) × {STOPPED, DEAD_MONEY, CUSHIONED} + grid B (15,126) × {STOPPED, CUSHIONED}.

| trial | feature | grid | state | | trial | feature | grid | state |
|---|---|---|---|---|---|---|---|---|
| T01 | PM1 | A (8,21) | STOPPED | | T11 | PM3 | A | STOPPED |
| T02 | PM1 | A | DEAD_MONEY | | T12 | PM3 | A | DEAD_MONEY |
| T03 | PM1 | A | CUSHIONED | | T13 | PM3 | A | CUSHIONED |
| T04 | PM1 | B (15,126) | STOPPED | | T14 | PM3 | B | STOPPED |
| T05 | PM1 | B | CUSHIONED | | T15 | PM3 | B | CUSHIONED |
| T06 | PM2 | A | STOPPED | | T16 | PM4 | A | STOPPED |
| T07 | PM2 | A | DEAD_MONEY | | T17 | PM4 | A | DEAD_MONEY |
| T08 | PM2 | A | CUSHIONED | | T18 | PM4 | A | CUSHIONED |
| T09 | PM2 | B | STOPPED | | T19 | PM4 | B | STOPPED |
| T10 | PM2 | B | CUSHIONED | | T20 | PM4 | B | CUSHIONED |

**m = 20, one BH family, q ≤ 0.10.** DSR does not apply (terminal-state classification study, not a return stream — P1.3 precedent).

**Deliberately absent from the family (pre-registered absences, not post-hoc drops):**
- **Grid-B DEAD_MONEY × PM1–PM4** (would-be 4 trials): UNREGISTERED — 43 events on the whole substrate (§1); a substrate limitation, not a tested-and-failed hypothesis. If a future replay regeneration lifts the count past the §1 event floor, testing it requires a registered family extension.
- **PM5 × 6 trials:** SUSPENDED `data_blocked` per §2/PM5, with a printed unblock condition and a pre-forbidden retro-pool.

Any variation beyond this table = a new recorded trial in the trial ledger and a fresh §9-masterplan entry; it never joins this family retroactively.

---

## 6. Pre-registered verdict criteria (checked in order, after BH)

### 6.1 Per sub-component

A sub-component **SURVIVES phase-0** iff ALL of:
1. ≥ 1 trial with BH-adjusted p ≤ 0.10 **and** Δ in the pre-registered favorable direction;
2. both-halves sign stability holds on every trial counted under (1);
3. the surviving trial(s) are not THIN (≥ 25 episode clusters in each group);
4. not REDUNDANT under §4.3 (including within-bundle).

Otherwise the sub-component is **NO-GO** → species registry records `falsified` (phase-0) and the feature remains unbuilt/unshipped. PM5 records `data_blocked` at registration (§2/PM5) — neither survived nor falsified; its unblock condition is its registry row's clock.

### 6.2 What surviving earns (ceiling restated)

A survivor earns exactly two rights, both requiring separate documents:
1. Eligibility for a **display-only context chip** (separate build PR + Fable ruling; bilingual; plain-English box; DT-R7 forbidden-key law applies verbatim — no level-as-instruction fields, ever);
2. Eligibility for a **promotion PREREG** (P2.1-style rank-weight/gate study with its own family and budget).

Nothing in this study authorizes board wiring, rank influence, gate influence, NW registration, or any site artifact.

### 6.3 Whole-bundle kill

If all four live sub-components (PM1–PM4) are NO-GO, the bundle is **CLOSED (PM5 data_blocked residue)**: registry rows recorded, the Signal Commons §4 parked row resolves as *dispatched → falsified (PM5 data_blocked)*, the DT-R7 routing clock closes, and price-memory does not return except through PM5's unblock clock or a genuinely new mechanism + new PREREG. This outcome blocks nothing else in EI.

---

## 7. Calibration controls (both blocking; run before any real trial is read)

Convention and thresholds per P2.5 §7 (the round-2 law: no EI study reports statistics from an uncalibrated instrument).

### 7.1 Negative control — permuted labels

For each live feature (**4 instruments**: the grid-A STOPPED trial of PM1–PM4; PM5 is data_blocked and has no instrument — red-team B3), 200 draws, seed 777: the favorable/unfavorable assignment is permuted at the episode level **within each calendar month** (episodes shuffle labels only among episodes of the same month; rows inherit their episode's permuted label; an episode's true label = its majority row label; mixed-label episode fraction logged). Within-month permutation is the correct exchangeability class for the §4.2 statistic — it preserves calendar composition exactly, so the null it generates is the one the month-contrast machinery claims to be calibrated against (a full-window permutation would be the P1.3-control mistake DT-R14 rubric point 2 documents: a control that cannot inject the confound it is supposed to guard). Full primary-p machinery (within-month Δ, weights, month-block bootstrap) rerun per draw. PASS requires, per instrument:
- rejection rate at α = 0.05 ≤ **0.12**;
- mean and median p within **0.5 ± 0.1**;
- KS-uniformity p ≥ **0.05**;
- param/perm divergence sanity gate (the P1.3 round-1 defect signature) does not trip.

### 7.2 Positive control — injected effect

On disposable copies (never mixed with real outputs), both must reject:
- **Return instrument:** +0.05 shift injected into the favorable group's `fwd_ret_21`; the supporting MWU/permutation diagnostic must reject at p ≪ 0.05 (P2.5 reference: perm_p ≈ 2e-4).
- **Incidence instrument:** relabel 5pp of the favorable group's STOPPED rows to CLEAN_LIFTOFF (whole episodes, drawn uniformly across qualifying months so the injection is not itself calendar-concentrated, seed 4242) on grid A; the primary within-month Δ + month-block-bootstrap pipeline must detect it with BH-adjusted p ≤ 0.10 inside a synthetic 20-slot family.

Either failure ⇒ the study is INVALID before it starts; blocker report to Fable; no real p-values are examined.

---

## 8. Context-only outputs (printed, never verdict-feeding, never BH'd)

- CLEAN_LIFTOFF deltas per feature per grid; grid-B DEAD_MONEY incidence printed descriptively (43-event substrate limitation, §1 — no test).
- Median MAE/MFE (`fwd_mdd_21`, `fwd_mfe_21`) by favorable/unfavorable group per feature — risk texture.
- Sector composition of favorable vs unfavorable groups per feature (concentration check).
- Full feature distributions (deciles) and the §4.3 correlation matrix.
- **Near-miss context read:** the four live features (plus pm5 where defined, labeled FLOAT-PROXY / PARTIAL-COVERAGE) computed on verdict-grade near-miss rows, distributions printed beside fires (EI R1 courtesy read; no test).
- Survivor-stamped rows: labeled context appendix, "SURVIVOR-STAMPED — CONTEXT ONLY, NOT VERDICT-GRADE."
- DannyTrades provenance box: the anchor's own pullback/DCA-adjacent evidence FAILED its gate (DT-R7: CI includes 0, payoff ≈ 0, tail worse) — printed as the honest prior, labeled "HYPOTHESIS SOURCE — NOT EVIDENCE."

---

## 9. Report contract

Outputs: `research/entry_intel/pm0_runs/EI_PM0_price_memory/` — analysis script + `RESULTS.md` + `results.json` (committed; feature parquet stays uncommitted per R9). Report fails its gate if any section is absent:

1. **Preamble:** artifact paths + MD5s (replay, features, statements_quarterly), column mapping + state enums, era citation (memo v1.1), n fires / clusters (22,295 operative) / survivor-stamped / per-grid censored counts, coverage table (incl. the PM5 blocked-coverage restatement), frozen medians and thresholds, event-floor + month-floor checks + any m decrement, **month census per trial** (qualifying-month count, per-month group sizes, episode week-straddle count), mixed-label episode fractions, §4.4 QA outcomes, §7 calibration outcomes, m = 20 declared.
2. **Per-trial table:** within-month Δ̂pp, month-block-bootstrap p, BH-adjusted p, pooled Δpp + pooled-vs-within-month divergence, episode-permutation p (diagnostic, NOT TIME-CONTROLLED label), MWU r (diagnostic), qualifying months, n and n_clusters per group, THIN flag, sign-stability flag.
3. **Redundancy matrix** + REDUNDANT rulings.
4. **Verdict per sub-component** (SURVIVES / NO-GO / data_blocked / REDUNDANT) with explicit criteria citations.
5. **Whole-bundle verdict** (survivors forwarded / bundle CLOSED).
6. **Context appendix** (§8 items).
7. **Leak-audit section:** signal-close-vs-next-close-fill confirmation, PIT spot-audit result, split-fence census, SO staleness distribution, era boundary confirmation.
8. **Registry + ledger rows:** species registry updates (family `price_memory`, ids EI-PM1-AVWAP / EI-PM2-SHELF / EI-PM3-GAP / EI-PM4-OVERHEAD / EI-PM5-FLOATTURN), masterplan §9 entry text, Signal Commons parked-row resolution text, DT-R7 clock closure note.
9. **Plain-English box** (plain-language law).

Delegation per masterplan §7: Sonnet builds and runs; Opus conformance-reviews the run; Fable renders the verdict. Deviation from this document = new recorded trial; ambiguity = blocker report to Fable, never improvisation.

---

## 10. Downstream routing and standing prohibitions

**If ≥ 1 sub-component survives:** registry `phase0_passed (display-only ceiling, DT-R7)`; eligible for §6.2's two paths only. Any chip build must route level-free context language ("light overhead supply," "unfilled gap overhead") — never levels-as-instructions; any level *value* rendered requires its own Fable display ruling and remains display-only.

**If the bundle closes:** §6.3 applies in full.

**Permanent prohibitions carried by every descendant of this family** (quoted from DT-R2/DT-R7, binding here and on all downstream artifacts): no `nearest_support`, `invalid_if_below`, `no_chase_above`, `max_add`, `invalid_if`, or any price-level trade-instruction field; no DCA policy objects; no fused price-memory composite; LLMs may only ever de-escalate on any calibrated key that eventually ships — never originate or escalate.

---

*Registered 2026-07-06. Immutable after Fable approval commit. Results go to the pm0_runs report only; this document is never edited to accommodate observed outcomes (species README convention).*

---

## §APPROVAL — Fable, 2026-07-06

**STATUS: APPROVED** (supersedes the DRAFT header above). Review of record: Opus red-team round 1 → **BOUNCE** (B1 recycled P1.3-round-1 bootstrap defect; B2 grid-B DEAD_MONEY degenerate, 43 events; B3 PM5 coverage measured 50.2% < 60% floor; B4 corrupt shares tails) → all four blockers + advisories A1–A7 fixed in r2 → Opus fix-verification round 2 → **CLEAN** (residuals NEW-1/2/3 + the reuse-overclaim softening applied before this approval commit) → **r3 pre-approval amendment**: DT-R14 (#1755) landed on main mid-registration; primary inference upgraded to within-calendar-month contrast + month-block bootstrap per the audit's RR-1 instruction, adjudicated and applied by Fable before this approval (the alternative — approving a prereg with the machinery the audit had flagged HIGH that same afternoon — would have manufactured the next re-check-queue entry).

Binding conformance (restated as approved):
1. Era law `P0_MEASUREMENT_MEMO.md` v1.1 in full; effective window **2022-06-30 → 2026-07-02**; canonical input `data/replay/replay_boarded.parquet` ONLY.
2. Live family = **m = 20** (PM1–PM4; §5 table is the complete enumeration). Grid-B DEAD_MONEY unregistered (substrate limitation, 43 events). PM5 `data_blocked` at registration with printed unblock condition; retro-pooling pre-forbidden.
3. Primary statistic + p = within-calendar-month contrast with month-block bootstrap (**DT-R14-compliant**, §4.2); episode-only machinery is diagnostic-only and so labeled; §1 event floor + §4.2 month floor checked pre-p-value; §7 calibration controls blocking (4 negative within-month-permutation instruments + 2 positive injections).
4. Redundancy fence |ρ| ≥ 0.8 (incl. `poc_dist_126` live-chip comparator and the within-bundle tie-break) is promotion-blocking.
5. **Display-only ceiling (DT-R7) and the forbidden-key law (DT-R2/DT-R7) are permanent** on this family and every descendant: no `nearest_support`, `invalid_if_below`, `no_chase_above`, `max_add`, `invalid_if`, or any price-level trade-instruction field, ever. Survivors earn §6.2's two paths only; no board wiring, no site artifact from this study.

Execution contract: Sonnet builds `scripts/ei_pm0_price_memory_features.py` + runs the study on the canonical checkout (Mac Studio host; massive store is host-only; writes only `data/replay/pm0_features.parquet` + `research/entry_intel/pm0_runs/EI_PM0_price_memory/`); Opus conformance-reviews the run; Fable renders the verdict. §4.4 QA gates and §7 calibration controls must PASS before any real trial p-value is examined. Deviation from the registered design = new recorded trial per species law; ambiguity = blocker report to Fable, never improvisation. This approval freezes the document (immutability clause above); it does not itself dispatch the run.
