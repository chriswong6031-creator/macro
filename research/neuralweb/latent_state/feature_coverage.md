# Neural Web R6.1-lite — Feature Coverage Audit

**Status:** Parked reference artifact. Frozen by RUL-CC-8.
**Built:** 2026-07-06
**Branch:** feat/nw-r6-manifest
**Source charter:** research/NW_CORE_COGNITION_ADJUDICATION_BY_FABLE.md §3

---

> **In plain English**
>
> This document answers one question: "If we were to build a Neural Web latent-state encoder
> today, what data would it actually see for each year from 1962 to 2026?" The answer is that
> coverage is extremely uneven. Seven feature families were enumerated, covering 65 candidate
> features total. But only two of those families have data going back before 2000
> (regime context and spine claim density), and the most interesting families —
> options/factor sensors, kernel reliability, and confluence topology — only exist from 2021
> onwards. This creates a severe era-confound problem: any latent cluster a model learns
> would primarily be encoding "what year is it?" rather than "what market state is this?"
> That is the main reason the encoder is parked until 2027-01-06.

---

## 1. Feature Count by Family

| Family | Feature IDs | Count | Note |
|---|---|---|---|
| Regime and macro context | rmc_001 – rmc_012 | 12 | Deepest history (1971+ for regime_v2_pit) |
| Spine claim density | scd_001 – scd_011 | 11 | 1962+ for counts; scd_011 excluded (forward outcome) |
| Kernel reliability context | krc_001 – krc_009 | 9 | All current_snapshot_backfill (including kernel-decisions, which has no entries yet) |
| Confluence and contradiction topology | cct_001 – cct_009 | 9 | All deployed post-2021 |
| Cycle and hazard context | chc_001 – chc_008 | 8 | Mixed; breadth goes to 1962, hazard live only from 2026 |
| Options / factor / bottom sensors | ofb_001 – ofb_010 | 10 | 2017+ (GEX); 2021+ (options IV/skew/entry); 2026 (bottom sensors) |
| Stock personality and board context | spb_001 – spb_006 | 6 | 2009+ (archetypes); 2026 (personality panel) |
| **Total** | | **65** | (1 excluded: scd_011 forward outcomes) |

---

## 2. Per-Family Coverage Window Table

Columns: first date of meaningful data, last date in local files, PIT basis class used.

| Family | Source Artifact | First Available | Last Local | PIT Basis |
|---|---|---|---|---|
| **Regime / macro** | | | | |
| regime_v2_pit (quad, transition, growth/inflation scores) | regime-v2-pit | 1971-01-04 | 2026-07-02 | recomputed_history |
| regime_history (growth/inflation scores nightly) | regime-history | 1971-01-04 | 2026-07-02 | recomputed_history |
| fed_net_liquidity | fed-net-liquidity | 2002-12-18 | 2026-07-02 | pit_live |
| market_state verdict | market-state-latest | r2_managed_unverified | 2026-07-02 | current_snapshot_backfill |
| risk_radar state | regime-latest | r2_managed_unverified | 2026-07-02 | current_snapshot_backfill |
| **Spine claim density** | | | | |
| spine_index all-engine counts | spine-index | 1962-11-29 | 2026-07-06 | recomputed_history |
| reflex / cortex_attention fires | reflex-firings-pattern | ~2026-01-01 | 2026-07-06 | pit_live |
| **Kernel reliability** | | | | |
| kernel_estimates (n_eff, shrunken_ic, armed) | kernel-estimates | 2026-06-19 | 2026-06-29 | current_snapshot_backfill |
| kernel_families (horizon curves, decay) | kernel-families | 2026-06-19 | 2026-07-06 | current_snapshot_backfill |
| kernel_half_lives | kernel-half-lives | 2026-06-19 | 2026-07-06 | current_snapshot_backfill |
| lagging_signals | lagging-signals | r2_managed_unverified | 2026-07-06 | current_snapshot_backfill |
| covariance_spine (independence) | covariance-spine | 2026-07-06 | 2026-07-06 | current_snapshot_backfill |
| **Confluence / contradiction topology** | | | | |
| confluence_graph (node/edge/contradiction counts) | confluence-graph | r2_managed_unverified | 2026-07-07 | current_snapshot_backfill |
| world_state contradictions | world-state | r2_managed_unverified | 2026-07-06 | current_snapshot_backfill |
| dt_contra_state | dt-contra-state | r2_managed_unverified | 2026-07-06 | current_snapshot_backfill |
| reflexivity n_eff_history | reflexivity-n-eff-history | r2_managed_unverified | 2026-07-02 | pit_live |
| factor_contradictions | factor-contradictions-ledger | r2_managed_unverified | (absent locally) | pit_live |
| **Cycle / hazard** | | | | |
| breadth.parquet (pct_above_50, ad_line) | breadth-breadth | 1962-03-13 | 2026-07-02 | recomputed_history (whole series; post-2002 cleaner via sp1500_pit_membership) |
| sector_breadth | breadth-breadth | 2025-05-28 | 2026-07-02 | current_snapshot_backfill |
| cycle_pattern state_monthly (phase/pos) | cycle-pattern-state-monthly | 2010-12-31 | 2026-06-30 | recomputed_history |
| cycle_pattern state_daily_live (hazard probs) | cycle-pattern-state-daily-live | 2026-06-26 | 2026-07-05 | pit_live |
| cycle_pattern_state JSON summary | cycle-pattern-state | r2_managed_unverified | 2026-07-06 | current_snapshot_backfill |
| **Options / factor / bottom sensors** | | | | |
| GEX state history (SPY/QQQ/DIA/IWM) | gex-state-history | 2017-01-03 | 2026-07-02 | recomputed_history |
| options_entry/state.parquet | options-entry-state | 2026-06-22 | 2026-07-05 | pit_live |
| options_skew/snapshots.parquet | options-skew-snapshots | 2026-06-21 | 2026-07-05 | pit_live |
| options_ivspread/snapshots.parquet | options-ivspread-snapshots | 2026-06-28 | 2026-07-05 | pit_live |
| factor_weather (world_state) | world-state | r2_managed_unverified | 2026-07-06 | current_snapshot_backfill |
| dispersion/regime.json | dispersion-regime | r2_managed_unverified | 2026-07-06 | current_snapshot_backfill |
| bottom_sensors.parquet | bottom-sensors-parquet | 2026-07-02 | 2026-07-02 | current_snapshot_backfill |
| fire_coordinates | fire-coordinates | r2_managed_unverified | (absent locally) | pit_live |
| **Stock personality / board context** | | | | |
| archetypes/history.parquet | archetypes-history | 2009-08-28 | 2026-06-01 | recomputed_history |
| stock_personality panel (R2) | stock-personality-panel | r2_managed_unverified | (R2 only) | pit_live |
| stock_personality forward_ledger | stock-personality-forward-ledger | r2_managed_unverified | (absent locally) | pit_live |
| dna_class.json | dna-class-ref | r2_managed_unverified | r2_managed_unverified (file absent locally) | current_snapshot_backfill |

---

## 3. Era Table

Which feature families provide coverage in each historical era:

| Era | Regime / macro | Spine density | Kernel reliability | Confluence topology | Cycle / hazard | Options / factor / bottom | Stock personality |
|---|---|---|---|---|---|---|---|
| **Pre-2000** (1962–1999) | Partial (regime_v2_pit from 1971; sparse scores) | Yes (track_record spine) | No | No | Breadth only | No | No |
| **2000–2008** | Yes (regime_v2_pit + fed liquidity from 2002-12) | Yes | No | No | Breadth only | No | No |
| **2009–2016** | Yes | Yes | No | No | Breadth + state_monthly (from 2010-12) | No | Archetypes (from 2009-08) |
| **2017–2020** | Yes | Yes | No | No | Breadth + state_monthly | GEX only (from 2017) | Archetypes |
| **2021+** | Yes | Yes | Current snapshot only | Current snapshot only | Yes (state_monthly + breadth) | Yes (options IV/skew/entry from ~2021; bottom sensors from 2026) | Archetypes + personality (from ~2026) |

**Families that NEVER have long-run PIT-live series:**
- Kernel reliability: all current_snapshot_backfill; zero historical time series of kernel cells
- Confluence topology: deployed post-2021; no backfill
- Bottom sensors: deployed 2026-07-02; only current snapshot
- Stock personality panel: deployed ~2026; R2-managed going forward only

---

## 4. Era-Confound Section (Frozen Law 4)

**Law 4 requirement:** Any cluster whose membership is >80% one coverage era is reported as an era detector, not a state.

### Why any encoder trained today would be an era detector

Mixing the feature families enumerated here into a single panel would produce an era confound by construction. The data-availability profile is:

**Pre-2021 rows** would have:
- regime_v2_pit features: present
- spine claim density (track_record/radar/policy): present but sparse
- kernel reliability: NOT PRESENT (all current_snapshot_backfill, no history)
- confluence topology: NOT PRESENT
- options IV/skew/entry: NOT PRESENT (GEX from 2017 only)
- bottom sensors: NOT PRESENT
- stock personality panel: NOT PRESENT (only archetypes from 2009)

**Post-2021 rows** would have: all families with at least some data.

The consequence: if a model learns latent axes from a mixed panel, the primary axis it discovers would not be "Goldilocks vs stagflation" or "risk-on vs risk-off" — it would be "pre-2021 data desert vs post-2021 full panel." Every cluster with high pre-2021 membership would be a null-pattern cluster (most features masked), not a market-state cluster. Per frozen law 4, these would be reportable as era detectors.

### Which specific pairings create the deepest confound

1. **spine_index (1962+) mixed with options-entry (2021+):** The 288,666 spine rows start in 1962; the 403 options_entry rows start June 2026. Mixing these in one feature vector would create a structural two-class problem: "spine-only era" vs "spine + options era."

2. **regime_v2_pit (1971+) mixed with confluence_graph (post-2021):** Any cluster containing regime labels AND confluence topology features would primarily reflect post-2021 data availability, not regime state.

3. **breadth.parquet (1962+) mixed with bottom_sensors (2026-07-02):** Only 1 distinct as_of day (2026-07-02) of bottom sensor data exists locally. Any latent dimension that uses both would collapse to a 1-bit "bottom sensors exist / do not exist" feature.

### The era confound is structural, not incidental

This is not a problem that can be fixed by imputing zeros for missing features. A zero in "options_entry.gamma_regime" on a 1975 date does not mean "gamma regime was neutral in 1975" — it means the concept did not exist. An encoder must represent this as a mask, and any latent state that reads through the mask would learn that "1975 = mostly masked" rather than "1975 = specific market state." Per DT-R16 (era-split law), the training data must be split by availability era before any latent structure claim is made.

### Conservative assessment

If an encoder were to be built on the current feature panel without era-stratification:
- Roughly 80-85% of available feature-days would be in the "pre-2021 data desert" era (1962-2020 = ~58 years of sparse coverage)
- Roughly 15-20% would be in the post-2021 "full panel" era (5 years)
- Any latent dimension extracted from the combined panel would have high probability of being an era detector rather than a market-state detector

This is the decisive practical argument underlying the park decision (§3 of the charter): the feature manifest makes this concrete and machine-checkable.

---

## 5. PIT Basis Distribution

Across the 65 enumerated features (excluding the 1 explicitly excluded forward-outcome feature, leaving 64 encoder candidates). **These counts are derived programmatically from panel_manifest.json after applying the F2 fix (chc_005 reclassified to recomputed_history):**

| PIT Basis | Feature Count | Families |
|---|---|---|
| pit_live | 13 | Reflex firings, fed_net_liquidity, options data (collected live), reflexivity n_eff, factor fire coordinates, stock personality panel + forward ledger, cycle state_daily_live (chc_002/chc_004/chc_008) |
| recomputed_history | 22 | regime_v2_pit series (rmc_001–rmc_005, rmc_007, rmc_008, rmc_012), spine_index (scd_001–scd_007, scd_009, scd_010), archetypes_history (spb_001, spb_005), GEX history (ofb_004), cycle state_monthly (chc_001), breadth.parquet whole-series (chc_005) |
| current_snapshot_backfill | 29 | All world_state blocks, confluence_graph, kernel snapshots (krc_001–krc_009), dispersion, sector breadth (chc_006), bottom sensors (ofb_007), most JSON outputs |
| vintage | 0 | No features available in rolling-vintage format today |
| display_only | 0 | No features assigned display_only (display-only artifacts are used as sources for aggregated features, not listed as display-only features themselves) |
| **Total** | **64** | |

The dominance of `current_snapshot_backfill` (29 features = 45%) reflects that most Neural Web infrastructure artifacts are daily rebuilds with no maintained history series — a direct consequence of the architecture being deployed recently. This reinforces the park decision: nearly half of proposed encoder inputs have no historical time series beyond the current run.

---

## 6. Ambiguous PIT Basis Calls

The following features required the conservative call rather than being clearly categorized:

| Feature ID | Artifact | Conservative Call | Alternative | Why Conservative |
|---|---|---|---|---|
| rmc_006 | regime-latest (liquidity_overlay) | current_snapshot_backfill | Could use regime_history.parquet back to 1971 | regime_history itself is a nightly rebuild using current code; calling it pit_live would overstate historical accuracy |
| rmc_010 | market-state-latest | current_snapshot_backfill | forward_log provides append-only record | forward_log starts at deployment, not 1962; calling it pit_live misleads about history depth |
| rmc_011 | risk_radar state | current_snapshot_backfill | Same as rmc_010 | Same rationale |
| ofb_004 | gex-state-history | recomputed_history | Could argue pit_live for post-2021 live collection period | Synapse notes confirm reconstruction for the whole series; no clean boundary between reconstructed and collected periods |
| chc_005 | breadth.parquet | recomputed_history (whole series) | Could claim pit_live for post-2002 portion | sp1500_pit_membership only covers 2002+; pre-2002 breadth uses survivorship-affected current membership. Conservative class applied to whole series to avoid misleading the encoder about the pre-2002 span. |

---

## 7. Features Where Charter Frozen Laws Made Classification Impossible

**Frozen law 2** (forward outcomes excluded): This was directly applicable to scd_011 (outcome_excess, outcome_graded, fwd_mfe_* from spine_index). All 8 forward outcome columns are categorically excluded regardless of their PIT basis. They are listed in the manifest with excluded_from_encoder=true for machine-checkable enforcement.

**Frozen law 4** (era detector disclosure): This law cannot be applied at the individual feature level — it applies at the cluster level after model training. The coverage audit in §3-4 above is the pre-model discharge of this law's intent: we have documented which feature combinations produce era-detector risk before any model is trained.

**Frozen law 3** (cluster naming stability): Not applicable at manifest stage (no model yet). Documented for future enforcement.

---

## 8. Re-open Conditions and Come-back Clock

Re-open the R6 encoder when **either**:

(a) The kernel has real quad-conditioned cells for ≥ 3 engines with n_eff ≥ 30 each via forward accrual, **or**

(a') The kernel program adopts recomputed_history quad backfill (printed caveat) giving the conditioning baseline;

**and in both cases:**

(b) At least one kernel decision batch has run (first due 2026-10-01).

**Come-back clock: 2027-01-06.**

The intent: the decisive evaluation (does latent state condition kernel calibration better than quad labels) cannot be run until the kernel has real quad-conditioned cells. Condition (a) gets there via live accrual; condition (a') gets there faster via the recomputed_history regime_v2_pit backfill already in hand. The kernel program's first decision batch (2026-10-01) is a prerequisite in both paths because it is the first moment the kernel has processed enough evidence to produce meaningful conditioned cells.

---

*No content here uses the CI-guarded word (per house law). This is a frozen reference artifact: no nightly step, no synapse/dag entry, no model output.*
