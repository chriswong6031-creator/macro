# Stock Personality — Adjudication & Build Masterplan (by Fable)

Date: 2026-07-06
Status: ADJUDICATED — build waves W0–W5 chartered (red-teamed: 3-lens Opus panel wf_029126e5; all blocking findings resolved in this revision)
Source paper: Codex `STOCK_PERSONALITY_UNIVERSE_RESEARCH.md` (2026-07-06, external worktree)
Census: workflow `wf_6022c28c` — 10 read-only lanes over engines, stores, NW contract, UI, pipeline (2026-07-06)
Owner program: `stock-personality`

---

## 0. Executive summary

The Codex paper proposes a per-ticker **personality layer**: five slow axes (business
DNA, factor DNA, ownership habitat, microstructure, chart personality) plus a fast
current state, shipped display-only, joined to setup-species fire ledgers to learn
*which setups deserve trust on which kinds of stocks*. The paper is directionally
right and its guardrails are house-law compatible. But roughly **half of its proposed
ontology already exists in this repo under other names**, one axis is partly
unbuildable from data on hand, and its retro-study design silently assumes historical
labels that cannot be reconstructed point-in-time.

This masterplan therefore: (1) rules axis-by-axis what is DUP / PARTIAL / NEW /
CONTRADICTED, (2) re-founds the ontology on the repo's existing taxonomies instead of
parallel ones, (3) charters the genuinely new tissue — a path-feature library, an
ownership-habitat classifier, a microstructure classifier, a fast `current_mode`
mapper, and the unified `stock_personality.v1` artifact, (4) pre-registers the
setup-compatibility study on the constitution axes with an honest PIT boundary and
honest analyzable-n accounting, and (5) slices the build into 7 same-day PRs.

**In plain English:** the paper says "stocks are different animals — label the animal,
then check which trade setups work on which animal." We agree. But the zoo already has
two label systems (fundamentals archetypes and factor DNA) — we reuse those instead of
inventing synonyms. The genuinely new work is measuring *how each stock's chart
actually behaves* (does it grind, snap back, gap, base?), *who owns it* (index funds,
insiders, shorts, retail?), and *how it trades* (liquid absorber vs air-pocket), then
honestly testing whether those labels change setup outcomes — with the labels locked
to what we could have known on the day of each historical trade, and with the sample
sizes we actually have, not the ones we wish we had.

---

## 1. Adjudication of the paper

### 1.1 Axis-by-axis verdicts

| Paper axis / claim | Verdict | Ruling |
|---|---|---|
| `business_dna` closed set (16 labels) | **DUP** | `engine/stock_fundamentals.py` `ARCHETYPES` v2 already ships 13 anchored buckets with EN/ZH labels, deterministic precedence, per-ticker confidence, and a PIT history (`data/archetypes/history.parquet`, 1,331 tickers, FY2009–25, annual grain, `asof_date = period_end + 120d` synthetic filing-lag proxy). Personality reuses `archetype` verbatim (R-SP2). |
| `factor_dna` closed set (11 labels) | **DUP** | Factor panel `dna_class` cascade already implements 8 classes with frozen v1 thresholds (`scripts/build_factor_panel.py:1169–1260`) + `style_regime` weather. Reused verbatim (R-SP3). |
| `unknown_factor` label | **CONTRADICTED** | Repo law distinguishes `None` (not evaluable — inputs missing) from `mixed` (evaluated, nothing matched). The paper's `unknown_*` conflates them. Repo convention wins (R-SP3). |
| Oracle `personality_class` anticipation | **DUP (live)** | Not merely anticipated — `engine/oracle/personality.py` (B1) is **live**: sector-node classes {mean_reverter, trender, rate_proxy, idiosyncratic, mixed} already in `oracle_state.json complexes[].personality`. The new work is a member-level roll-up, additive per the Oracle contract (R-SP19). |
| `chart_personality` per ticker | **NEW** | No per-ticker path classifier exists. Primitives exist scattered (`entry_primitives`, `vol_squeeze`, `coiled`, `stock_technicals`); the summary-rate statistics (trend persistence, pullback distribution, follow-through/failed-breakout rates, gap share, reversal half-life) do not. Chartered as Lane B (R-SP4). |
| `microstructure` per ticker | **NEW, trimmed** | Amihud + Corwin–Schultz spread proxies exist as functions; no classifier. `auction_dominated` unbuildable (zero intraday/auction data). Persistent gamma personality unbuildable today (18 days of GEX chain history). Trimmed set chartered (R-SP5). |
| `ownership_habitat` per ticker | **NEW, trimmed** | Rich ingredients exist (2.3M-row Form-4 panel, FINRA SI + short volume, 13D/G filer typing, 30-ETF holdings, basket membership, wiki attention 966 names, WSB, curated+Quiver 13F). No classifier exists. Broad 13F breadth, borrow data, crowding engine do NOT exist → 3 labels deferred (R-SP6). |
| fast `current_state` | **PARTIAL** | The repo is full of state machines (`vol_squeeze.state`, `ladder.state`, extension grade, COILED, GEX regime, earnings calendar, Oracle episodes, attention z, `time_underwater`). The new work is a *mapping layer* onto one closed vocabulary — renamed `current_mode` to avoid colliding with `ladder.state` (R-SP7). |
| `setup_compatibility` | **PARTIAL** | Species registry already carries `archetype_scope` per species; ledgers already carry nullable `species_id`/`archetype` columns — **both 100% null today** (0 of 55,406 track_record rows), so the retro species arm is impossible (R-SP11/12/18). |
| `stock_personality.v1` unified object | **NEW** | No unified per-ticker object exists. Chartered, with repo-convention storage (R-SP8). |
| `data/stock_personality/latest.parquet` + `history.parquet` | **AMENDED** | Naming pair is not a repo convention. Use monthly-partitioned `panel/YYYY-MM/panel.parquet` like the factor panel (R-SP8). |
| Phase-2 retro compatibility study | **AMENDED** | The paper assumes labels can be attached "as of fire_date" for all axes and cites corpus sizes at face value. Reality: factor-panel partitions reach back only to 2025-06; ownership stores are largely snapshot-grade; the archetype PIT panel starts FY2009 (57% of deep-history fires predate it); the gate-fires store is a regenerable study artifact, not a live store. Retro study restricted to PIT-safe axes with analyzable-n printed per cell; the rest accrues forward (R-SP12, §4). |
| Guardrails 1–10 | **RATIFIED** | All ten adopted; #7 (no LLM-authored labels/confidence) restated under the house LLM law (R-SP15). |

Net assessment: **~45% DUP/PARTIAL (reuse), ~35% genuinely NEW (build), ~20%
unbuildable-now or contradicted (trim/defer)**. The paper's §1 "what this is not"
boundary was honest but incomplete — it missed that its own §6.1/§6.2 closed sets
already exist nearly verbatim.

### 1.2 Rulings (R-SP series)

- **R-SP1 — Charter.** The personality layer is **context infrastructure**:
  tier=display, confidence_class=`descriptive`, `weights: none`, `may_rank/size/gate:
  false` at birth. It explains; it never scores. Promotion only per R-SP13.
- **R-SP2 — Business DNA = archetype.** The `business_dna` axis IS
  `stock_fundamentals._archetype()` output, verbatim keys, no parallel taxonomy. The
  paper's extra labels are killed or rerouted: `biotech_binary` /
  `legal_regulatory_binary` → modeled as `event_override` in `current_mode` (event
  calendar + sector), not business DNA; `serial_acquirer_rollup`,
  `promotional_reflexive_story`, `declining_terminal_value` → NOT classifiable from
  data on hand; parked (no silent proxies).
- **R-SP3 — Factor DNA = dna_class.** The `factor_dna` axis IS the factor panel
  `dna_class` (+ `style_regime` as weather context), verbatim. No `payout_yield` /
  `commodity_factor` / `china_adr_policy_beta` / `mixed_factor` / `unknown_factor`
  renames. `None` ≠ `mixed` convention adopted. Known gap: live partitions predate
  P1-C (52 of 55 columns), so `dna_class` presence must be verified after the next
  panel rebuild; consumers degrade to null if absent (never crash).
- **R-SP4 — Chart personality closed set v1** (measured, deterministic cascade, ≥2
  independent path features per label):
  `smooth_compounder_grind, stair_step_leader, volatile_momentum_vehicle,
  mean_reversion_rubber_band, basing_accumulator, event_gapper, failed_breakout_trap,
  defensive_range_stock, mixed_chart` (+ `None` when coverage insufficient).
  Rerouted from the paper's set: `squeeze_tape`, `air_pocket_derater` → states in
  `current_mode`; `news_attention_rocket` → ownership `retail_attention` × state;
  `commodity_whip` → derived cross (archetype `commodity_sensitive` ×
  `volatile_momentum_vehicle`), never stored as its own label; `turnaround_repair_base`
  → derived cross (archetype `distressed`/`broken_growth` × `basing_accumulator`);
  `post_ipo_supply_unlock` → deferred (no IPO/lockup calendar store).
- **R-SP5 — Microstructure closed set v1** (trimmed to computable):
  `tight_spread_absorber, wide_spread_impact, gap_discontinuity_risk,
  slow_mean_reversion_liquidity, mixed_microstructure` (+ `None`).
  Inputs: dollar ADV, Amihud ILLIQ, Corwin–Schultz spread proxy, gap share,
  extreme-bar frequency (halt *proxy* — no halt feed exists; labeled as proxy),
  reversal half-life (new estimator). **Dropped:** `auction_dominated`
  (CONTRADICTED — `data/intraday/` is empty; no auction data). **Rerouted:**
  `positive_gamma_pin` / `negative_gamma_amplifier` → `current_mode` overlays
  (`options_pin`, `negative_gamma_trend`) for the ~384 GEX-covered names only, using
  *current* chain snapshots; persistent dealer-gamma personality is DEFERRED behind
  the `thetadata_eod` backfill clock (store exists, `completed: {}` — nothing on
  disk) or ≥63 accrued days of `polygon_gex` chains, whichever first.
  `short_borrow_squeeze` → tinderbox is ownership; squeeze is a state.
- **R-SP6 — Ownership habitat closed set v1** (proxy-honest):
  `passive_index_magnet, etf_basketed_conduit, long_only_sponsor,
  insider_founder_controlled, short_interest_tinderbox, retail_attention,
  mixed_ownership` (+ `None`). Each label carries its **proxy basis** in the evidence
  block (e.g. `long_only_sponsor` = 13D/G passive-giant filings + curated-13F VIP
  presence + low SI + low attention — explicitly NOT broad-13F breadth, which does not
  exist). **Deferred:** `hedge_fund_crowded` (needs a crowding/comomentum engine —
  candidate future lobe; Quiver 13F is a partial proxy at best),
  `event_specialist_owned` (no data), `forced_seller_repair` (a state + a species
  domain — S2 already owns donor-exhaustion mechanics; rerouted to `current_mode
  forced_liquidation`).
- **R-SP7 — current_mode closed set v1** (fast layer; mapping over existing state
  machines, each mode carries evidence keys + expiry):
  `accumulation, distribution, squeeze, forced_liquidation, options_pin,
  negative_gamma_trend, event_override, sector_rotation_feeder, post_news_attention,
  stale_dead_money, normal` (+ `None`). Sources: `vol_squeeze.state`, `ladder.state`,
  extension grade, COILED/washout, GEX snapshot, earnings/event calendar, Oracle
  active-episode membership (`sector_rotation_feeder`), attention z
  (`post_news_attention`), `time_underwater` + volume drought (`stale_dead_money`),
  FINRA SI × gap-through-resistance (`squeeze`). Named `current_mode`, never `state`
  (vocabulary law R-SP17).
- **R-SP8 — Artifact & storage.** Schema `stock_personality.v1`. Stores:
  `data/stock_personality/panel/YYYY-MM/panel.parquet` (per-(ticker,date) daily
  label snapshot appended nightly; gitignored-local + R2-published — mirrors the
  factor-panel partition convention; NOT latest/history),
  `site/factordata/stock_personality.json` (small cross-sectional aggregate, git),
  and a `personality` block inside `site/stockdata/<TICKER>.json` (existing
  stockdata plane: host-only + R2). Every block carries `as_of`, per-axis coverage,
  proxy notes, and the authority stanza.
- **R-SP9 — Pipeline placement (amended per red-team).** The personality object is
  assembled **inside the engine job's existing `build_stock_library` per-ticker
  loop**, where per-ticker OHLCV, tech blocks, `positioning` (SI/insider),
  `smart_money`, basket membership, GEX, earnings calendar, and `_archetype()` are
  ALREADY loaded — marginal cost is compute-only (no new I/O). The red-team
  established the originally-proposed factor_panel job has **no OHLC on disk**
  (close-only S&P 500 breadth cache), so it cannot host the chart/micro axes; no
  new job is created and the engine render budget is respected by a hard
  **benchmark gate in W2b review: marginal runtime must measure ≤2 min for the
  library universe, printed in the build log** (path features are vectorized
  rolling ops on already-loaded frames; if the gate fails, chart-axis scope shrinks
  until it passes). The `dna_class` reference is produced where percentiles
  actually exist: the factor_panel job emits a tiny `site/factordata/dna_class.json`
  (ticker → {dna_class, style_regime, as_of}), added to that job's narrow git-add
  allowlist; the engine job consumes it **T-1 by design** (engine and factor_panel
  are parallel siblings; the personality block prints the dna_class `as_of`).
  Chart/micro/ownership axes and `current_mode` are therefore T-0; `dna_class` is
  T-1; both facts printed, never hidden.
- **R-SP10 — Registration checklist (same PR as the artifact, CI-enforced):**
  `config/synapse.yml` entries with all 11 required fields and LEGAL enum values —
  cadence `daily-engine` for engine-job artifacts, `nightly-factor-panel` for
  `dna_class.json`, `on-demand` for study outputs; storage from
  {git, r2, gitignored-local, git+r2}; tier=display or infrastructure;
  `horizon_role: context`; `weights: none` — plus `config/dag.yml` step
  declaration, no `forecast/predicted/target/expected_return` substrings in any
  additive Oracle field, no affirmative "validated"/"已验证" in user-facing text
  (`check_validated_claims.py`), tooltips via `data-tip-en/zh` never `title=`
  (`check_title_i18n.py`), fdr_family hard-wired in code.
- **R-SP11 — Compatibility study pre-registration.** See §4. Endpoints route through
  `engine/grading.py` ONLY (the one-grader law; the wave1 1.20/0.97 barrier variant
  is explicitly NOT comparable and must not be mixed). One **binary primary per
  cell** (P(STOPPED)); BH-FDR across the pre-declared family under
  `fdr_family='stock_personality_compat'`; two-way clustered inference; and the
  **disguise kill test** as a regression-with-controls, not a strata grid. Cells
  below the pre-registered minimum n print `insufficient_n` and are not tested.
- **R-SP12 — PIT boundary for the retro study (amended per red-team).**
  Retro-attachable axes ONLY:
  (a) `archetype` from `data/archetypes/history.parquet` — **FY2009+ only, annual
  grain, 187/220 deep-history names covered; join rule: attach the row with the
  greatest `asof_date ≤ fire_date`** (`asof_date = period_end + 120d`, the
  conservative synthetic filing-lag proxy consistent with the EDGAR PIT law); fires
  before the first attachable row carry `archetype = null`. This drops ~57% of
  deep-history fires (~9.7k of 26.4k buy/rebuy fires attachable) — the analyzable n
  is printed per cell, and the pre-2009 exclusion is a first-class watermark.
  (b) `chart_personality` and `microstructure` — recomputed point-in-time from
  OHLCV with causal rolling windows via `path_personality.feature_series` (fully
  retro-attachable on the deep 220-name corpus; 2021+ on the massive universe).
  (c) OHLCV-derived `current_mode` components.
  NOT retro-attachable: factor `dna_class` — **because stored factor-panel
  partitions begin 2025-06** (the factor program's R3 percentile construction is
  itself PIT-correct; the constraint is partition history depth, not a PIT
  prohibition); ownership habitat — FINRA SI is a single settlement snapshot, short
  volume a ~30-day window, Quiver 13F 2020+ usable only as a secondary with its own
  as-of lag. These enter the **forward ledger**; retro results are reported only
  where a PIT-safe sub-proxy exists (insider panel 2006+, attention 2015+, FTD
  2009+). Fire-time stamping law: the join uses PIT recomputation at `fire_date`,
  NEVER today's labels copied backwards. (The existing `track_record.archetype` /
  `species_id` columns are 100% null today — there is no existing stamp to lean on.)
- **R-SP13 — Authority ladder.** display block → species-card context chip →
  compatibility context printed beside species entries → (earned, per forward ledger
  + monthly species review) display ordering *within equal baseline rank bands*.
  Never a gate, never size, never a hard filter default-on. Any promotion requires
  printed base rates + CIs and survives the disguise kill test.
- **R-SP14 — Markets.** v1 = US only (stock-library universe ~1,600 names for the
  nightly block; deep-history 220-name corpus + replay corpus for the retro study).
  CN/HK/CA deferred to v2 with the census feasibility matrix (CN: chart + ownership
  proxies OK, no single-name options; HK: 159 names, thin fundamentals,
  survivorship-flagged; CA: 2021+ prices only, no short history, no options). No
  cross-market parity claims; per-market coverage printed when v2 ships.
- **R-SP15 — LLM law.** Deterministic code assigns every label and confidence;
  ledgers assign edge; the LLM (cortex) may summarize personality context and may
  only de-escalate — it never originates or escalates labels.
- **R-SP16 — Registry hygiene fix (amended per red-team: TWO invalid entries).**
  `tests/test_species_registry.py::TestSeedRegistryValid::test_all_seed_entries_valid`
  is red on main today because of two schema-invalid entries:
  (a) `F3_ANTICHASE`: sole defect is `validation_status: "phase0_passed"` (illegal
  enum — the entry already carries `trial_count: 3`; nothing else missing). Fix:
  status → `accruing` (phase-0 complete ⇒ ledger accruing) + `_lifecycle_log` entry.
  (b) `EI-F1D-RW`: `validation_status: "shadow"` and `deployment_status:
  "shadow_ledger"` are illegal enums, and `archetype_scope` / `market_scope` /
  `regime_scope` / `trial_count` are missing. Fix (semantics preserved, custom
  fields like `primary_config`/`tracked_variants` untouched): status → `accruing`
  (its shadow forward ledger is live since 2026-07-05), deployment →
  `ledger_fields` (it IS additive ledger columns), `market_scope: ["US"]`,
  `trial_count: 8` (the P2.5 grid tried eight configs), honest `archetype_scope`
  and `regime_scope` blocks citing EI masterplan P2.5 (in-sample-selected grid —
  shadow rung only; forward ledger is the true OOS), + `_lifecycle_log` entry.
  W0 builder must re-verify both defects still exist at build time (a concurrent
  agent may have fixed them) and must leave the seed test green.
- **R-SP17 — Vocabulary law.** "personality" is now two objects:
  `oracle_personality.v1` (sector-node) and `stock_personality.v1` (per-ticker) —
  never interchanged. Axis keys reuse existing vocabulary: `archetype` (not
  business_dna), `dna_class` (not factor_dna). The fast layer is `current_mode`
  (never `state`). New closed-set values never collide with existing enum strings.
- **R-SP18 — Species inverse-compat map.** `setup_compatibility` (ticker →
  favored/caution species) is DERIVED display: species-registry `archetype_scope` ×
  the ticker's axes. It is recomputed, never stored as truth, and never edits
  `archetype_scope` automatically — scope changes only via the monthly species
  review consuming forward-ledger evidence.
- **R-SP19 — Oracle additive wave.** Member-level personality roll-up
  (`personality_context`: dominant member archetypes/chart classes, tinderbox share,
  event-override share, coverage) added to `oracle_state.json` as minor-version
  additive fields per the Additive Extension Protocol, `confidence_class:
  "descriptive"` + lineage anchor to this document. Field names avoid the banned
  substrings.
- **R-SP20 — NW registration.** New artifacts registered in `config/synapse.yml`
  under `owner_program: stock-personality`; `world_state.json` gains a fail-open
  `stock_personality_summary` sub-block; a spine adapter
  (`adapt_personality_context`) joins labels onto spine rows by ticker. Cortex may
  cite personality context in memos (de-escalation only).
- **R-SP21 — v1.1 chart-threshold re-anchor (2026-07-07).** The first production
  print (1,722 tickers, as_of 2026-07-06) showed two degenerate chart labels:
  `failed_breakout_trap` fired on 82% of the universe and
  `mean_reversion_rubber_band` on 38% — because the v1 anchors sat below the
  universe's natural base rates (deep-corpus calibration, n=219:
  `failed_breakout_rate_63` p10=0.71 / p50=0.81 / p90=0.92; `trend_persist_60`
  p10=−0.19 / p25=−0.085). Both labels also fired on a single feature, violating
  R-SP4's ≥2-features-per-label law. Amendment (frequency-only calibration — no
  outcome data read; the §4 study was unregistered at amendment time):
  `failed_breakout_trap` = rate ≥ 0.92 AND `breakout_ft_rate_63` ≤ 0.45;
  `mean_reversion_rubber_band` = `trend_persist_60` ≤ −0.19 AND
  `trend_persist_126` ≤ 0. Projected v1.1 rates on the calibration sample: 6%
  and 10% respectively. All other thresholds unchanged; next re-anchor requires
  a new ruling.

---

## 2. Ontology v1 (frozen closed sets)

The unified per-ticker object (axes reference existing taxonomies; nothing here
invents a parallel label for an existing concept):

```json
{
  "schema": "stock_personality.v1",
  "as_of": "YYYY-MM-DD",
  "ticker": "XYZ",
  "base": {
    "archetype":         {"key": "quality_compounder", "source": "stock_fundamentals.v2", "confidence": 0.62},
    "dna_class":         {"key": "quality_growth", "source": "site/factordata/dna_class.json", "as_of": "T-1", "style_regime": "growth_momentum"},
    "ownership_habitat": {"labels": ["long_only_sponsor", "passive_index_magnet"], "proxy_basis": ["13dg_passive", "vip_13f", "low_si"]},
    "microstructure":    {"labels": ["tight_spread_absorber"], "adv_usd_21d": 0.0, "amihud_pct": 0.0, "cs_spread_pct": 0.0},
    "chart_personality": {"labels": ["smooth_compounder_grind", "stair_step_leader"], "features": {}}
  },
  "current_mode": {
    "modes": ["accumulation"],
    "evidence": {"vol_squeeze": "COILED", "ladder": "BOTTOM WATCH"},
    "expires_after_days": 21
  },
  "setup_compatibility": {
    "favored_species": ["S1", "S15"],
    "caution_species": ["S14"],
    "derived_from": "species_registry.archetype_scope × axes — display-only"
  },
  "evidence": {"coverage": {"archetype": 1.0, "dna_class": 1.0, "ownership": 0.7, "micro": 1.0, "chart": 0.9},
               "missing": [], "as_of_by_axis": {}, "lineage": "research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md"},
  "authority": {"tier": "display", "confidence_class": "descriptive", "weights": "none",
                "may_rank": false, "may_size": false, "may_gate": false}
}
```

Closed sets (frozen v1; additions require a version bump + adjudication):

- `archetype`: the existing 13 keys of `stock_fundamentals.ARCHETYPES` (unchanged).
- `dna_class`: the existing 8 classes of the factor-panel cascade (unchanged).
- `ownership_habitat`: `passive_index_magnet | etf_basketed_conduit |
  long_only_sponsor | insider_founder_controlled | short_interest_tinderbox |
  retail_attention | mixed_ownership` (multi-label, max 3, precedence-ordered).
- `microstructure`: `tight_spread_absorber | wide_spread_impact |
  gap_discontinuity_risk | slow_mean_reversion_liquidity | mixed_microstructure`
  (primary + optional secondary).
- `chart_personality`: `smooth_compounder_grind | stair_step_leader |
  volatile_momentum_vehicle | mean_reversion_rubber_band | basing_accumulator |
  event_gapper | failed_breakout_trap | defensive_range_stock | mixed_chart`
  (multi-label, max 2, precedence-ordered).
- `current_mode`: `accumulation | distribution | squeeze | forced_liquidation |
  options_pin | negative_gamma_trend | event_override | sector_rotation_feeder |
  post_news_attention | stale_dead_money | normal` (multi-label, max 3).
- Everywhere: absent inputs ⇒ axis value `null` + `evidence.missing` entry. `mixed_*`
  means *evaluated, nothing dominated*. These are different facts and never conflated.

**In plain English:** one card per stock. Top half: what the company is (existing
archetype), what return stream it rides (existing factor DNA), who owns it, how it
trades, and what its chart habitually does. Bottom half: what's happening *right now*
(accumulating? squeezed? pinned by options? dead money?), which of our named trade
setups historically fit this kind of stock — and an honesty footer saying what we
couldn't measure.

---

## 3. Architecture

### 3.1 New code

| File | What | Notes |
|---|---|---|
| `engine/path_personality.py` | Pure path-feature library (Lane B) | Causal rolling features from OHLCV: trend persistence (sign-autocorr + slope stability 20/60/126d), pullback-depth distribution (median/p90 from rolling local highs), breakout follow-through rate (fwd return after 20/63/252d highs), failed-breakout rate (high reversed below level within k days), gap share (|open−prior close| contribution to total |move|), reversal half-life (post-shock decay fit), wick share, base compression (delegates to `vol_squeeze`), event-day discontinuity. Two APIs: `features(ohlcv) -> dict` (snapshot, cheap — used nightly) and `feature_series(ohlcv) -> DataFrame` (PIT series — used by the retro study only). Reuses `entry_primitives` (`amihud_series`, `corwin_schultz_spread_series`, `undercut_rally_events`); `gap_hold_events` stays appendix-locked DORMANT — the library implements its own gap-share math internally (W1 review confirms no dormancy-law breach). |
| `engine/stock_personality.py` | Classifier cascades + object assembly | Deterministic threshold cascades for chart/microstructure/ownership axes; `current_mode` mapper; references `archetype` + `dna_class` (read-only); emits the §2 object per ticker; every cascade first-match-wins with printed precedence like `ARCHETYPE_PRECEDENCE`. Pure — takes already-computed inputs (rec dict, path features, positioning, smart_money, GEX, calendar); no I/O. |
| `scripts/build_stock_personality.py` | On-demand CLI only | Full-history PIT series builder (retro backfill for W3) + panel rebuild + standalone re-run. NOT a nightly job — the nightly path is the `build_stock_library` loop (R-SP9). |
| `scripts/personality_compat_phase0.py` | On-demand retro study (W3) | §4; regenerates the gate-fires corpus via `scripts/research/dump_gate_fires.py` first; routes ALL outcome grading through `engine/grading.py`. |

### 3.2 Stores & registration

| Artifact | Path | storage (legal enum) | tier | cadence (legal enum) | producer job |
|---|---|---|---|---|---|
| personality panel | `data/stock_personality/panel/YYYY-MM/panel.parquet` | gitignored-local (+ R2 via `publish_r2.py` DEFAULT_DIRS `stock_personality`) | infrastructure | daily-engine | engine (inside build_stock_library pass) |
| site aggregate | `site/factordata/stock_personality.json` | git | display | daily-engine | engine (build_site; picked up by the existing engine commit) |
| stockdata block | `personality` key in `site/stockdata/<T>.json` | r2 (existing stockdata plane) | display | daily-engine | engine |
| dna_class reference | `site/factordata/dna_class.json` | git | infrastructure | nightly-factor-panel | factor_panel (added to its narrow git-add allowlist — no blanket adds) |
| forward ledger | `data/stock_personality/forward_ledger.parquet` | git | shadow | daily-engine | engine — appended in the same nightly pass that stamps track_record (single-writer, engine-commit lane; same discipline/precedent as `track_record.parquet`). Intraday lanes discard `data/` writes per house law — no COLLECT_LANE machinery is borrowed (that sentinel exists only inside the collect job). |
| compat retro results | `data/research/personality_compat_phase0.parquet` + `research/STOCK_PERSONALITY_SETUP_COMPAT_PHASE0.md` | git | display | on-demand | host-side W3 run |

All registered in `config/synapse.yml` (`owner_program: stock-personality`,
`horizon_role: context`, `weights: none`); any workflow-step change declared in
`config/dag.yml`.

### 3.3 Budget

Nothing new lands on the render critical path as a separate step. The personality
assembly rides the existing `build_stock_library` per-ticker loop where OHLCV is
already in memory; the marginal cost is vectorized rolling computation only.
**Hard gate (W2b review): measured marginal runtime ≤2 min over the full library
universe, printed in the build log** — if exceeded, chart-axis feature set shrinks
until it passes (the snapshot API computes only tail windows, never full-history
series, in the nightly path). The W3 retro backfill (full `feature_series` over the
deep corpus) is on-demand host-side — hours are fine, off the render path entirely.

---

## 4. Pre-registered setup-compatibility study (Phase 0/2)

**Question (frozen):** does the personality cell of the ticker *as of the fire date*
shift the safety-net outcome of a board/gate fire vs. the proper control?

- **Corpora (counts frozen by the W3 script at registration time from the actual
  stores; figures below are census estimates, not registered n's):**
  (a) `data/signal_archive/track_record.parquet` buy/rebuy fires with graded
  terminal states (~26.4k fires, 220 deep-history names, 1962→ —
  survivorship-flagged, watermark printed on every table; archetype-attachable
  subset ~9.7k per R-SP12);
  (b) the gate-fires corpus **regenerated at study time** via
  `scripts/research/dump_gate_fires.py --panel deep` (+ `--panel baskets`
  optional) — it is a transient study artifact, not a live store;
  (c) the replay corpus 2022–2026 fire-verdict subset (host-only per R9; results
  publish as aggregates only; outcome columns `state_15_126`/`state_8_21` are used
  where present and re-graded through `engine/grading.py` where absent).
  HK/CA/CN ledgers are too young — excluded from retro, included in the forward
  ledger.
- **Species arm: retro-DROPPED.** `species_id` is 100% null in every historical
  store — the paper's species-interaction questions CANNOT be evaluated
  retrospectively. They are forward-only (the forward ledger stamps species_id via
  the live registry bindings). The retro study may stratify by gate tier (T1/T2/T3)
  — a mechanism family, honestly labeled as not-species.
- **Labels at fire date:** per R-SP12 — archetype via greatest-`asof_date ≤
  fire_date` join (FY2009+); chart/micro features recomputed causally at fire_date
  via `path_personality.feature_series`; PIT-safe ownership sub-proxies only
  (insider 2006+, attention 2015+, FTD 2009+); no snapshot laundering.
- **Primary endpoint (ONE per cell, binary):** P(STOPPED) at the pre-declared
  horizon-ruler (`clean15_126` positional / `clean8_21` rotational) via
  `engine/grading.py` ONLY. **Secondary:** P(DEAD_MONEY), P(CLEAN_LIFTOFF), MAE/MFE
  at spine horizons, post-cushion breach. **Exploratory:** full 4-state multinomial
  shift. This keeps the FDR family ~4× smaller than a per-state family and matches
  the safety-net intent.
- **Cell family (pre-declared, FDR-bound):** chart labels (9) + microstructure (5)
  + a **pre-registered archetype collapse map** — the 13 archetypes collapse to the
  buckets with adequate attachable-n, decided by label counts BEFORE any outcome is
  examined (collapse by n only; expected ~6 buckets) — each × the single primary,
  per corpus. `fdr_family='stock_personality_compat'`; BH-FDR over the whole
  family; trial-ledger rows registered BEFORE the run. **Minimum-cell-n
  pre-registration: cells with n < 50 print `insufficient_n` and are not tested.**
- **Inference:** two-way cluster-robust (ticker × quarter) — fires cluster by name
  across time, not merely by sector; the effective number of independent clusters
  is printed. Sector joins from `data/breadth/ticker_sectors.parquet`.
- **Disguise kill test (pre-committed, regression form):** for every surviving
  cell, fit `outcome ~ label + sector FE + log(mktcap) + era FE` with two-way
  clustered SEs. If the label coefficient does not survive controls, the cell is
  stamped `redundant_with_sector_size` — printed, and barred from chips that imply
  differentiation. (The paper's §13-Q10, made mandatory; the strata-grid version
  was rejected as underpowered — ~8 fires/cell.)
- **Pre-committed contingency:** expected outcome is *mostly nulls with a few
  survivors*. Nulls are printed in the Phase-0 report and the layer stays a
  descriptive card. That outcome is a success (the conviction-profile precedent).
- **Forward ledger:** every new fire gets stamped with the contemporaneous
  personality vector (all axes, including the non-retro-attachable ones) into
  `data/stock_personality/forward_ledger.parquet` — engine-nightly single-writer.
  **Clocks (amended per red-team — reachable):** re-look at n≥50 per collapsed
  cell; promotion-eligible at n≥150 per collapsed cell AND ≥2 quarters of accrual;
  calendar re-look 2026-12-15 — **whichever comes FIRST triggers a review** (the
  original n≥300-AND-later formulation was unreachable at observed fire rates).
  The promotion track is restricted to the collapsed high-population cells; the
  long tail pools hierarchically and never promotes per-cell.

---

## 5. Integration map

- **Species (§R-SP18):** species cards show personality-compat context; monthly
  species review may amend `archetype_scope` citing forward evidence; the
  inverse-compat map renders on stock surfaces.
- **Oracle (§R-SP19):** additive `personality_context` roll-up per complex;
  descriptive; tolerant-reader safe.
- **Neural Web (§R-SP20):** synapse registration; `world_state` fail-open
  sub-block; spine adapter; admin Experiments entries with come-back clocks; lobe
  visible in the admin NW Observatory (synapse-sourced — automatic once registered).
- **UI (W4):** `stock.html.j2` — "How this stock trades / 这只股票的交易个性" panel
  (chips per axis + current_mode + compat lines + honesty footer). `dashboard.html.j2`
  us_stocks cards — up to 2 personality chips inside the existing `.nb-more`
  expander (at-rest card stays two-glyph per the board-declutter ruling).
  `basket_detail.html.j2` — slim per-member personality slice. All EN/ZH via the
  `t()` / `B()` dual-span pattern; tooltips via `data-tip-en/zh`; no new at-rest
  clutter; no board filter in v1 (no filter infra exists — revisit after the
  forward ledger says which labels are real).

---

## 6. Build waves (7 PRs, same-day cadence)

| Wave | PR | Contents | Depends |
|---|---|---|---|
| W0 | PR-A | This masterplan + R-SP16 two-entry registry fix (seed test green) | — |
| W1 | PR-B | `engine/path_personality.py` + unit tests (golden fixtures on synthetic paths + 2 real tickers) | — |
| W2a | PR-C | `engine/stock_personality.py` cascades + object assembly + tests | W1 |
| W2b | PR-D | `build_stock_library` personality pass (benchmark gate ≤2 min printed) + panel append + site aggregate + forward-ledger stamper + `dna_class.json` emit in factor_panel job (narrow-add) + `publish_r2.py` dir + synapse/dag registration + tests | W2a |
| W3 | PR-E | `scripts/personality_compat_phase0.py` + `scripts/build_stock_personality.py` (backfill CLI) + trial-ledger registrations + Phase-0 report (printed nulls, analyzable-n tables) + experiments-registry entry | W2a (library); consumes W2b outputs where available |
| W4 | PR-F | UI: stock page panel + board expander chips + basket slice (EN/ZH) | W2b |
| W5 | PR-G | Oracle `personality_context` additive + NW `world_state` sub-block + spine adapter + come-back clocks | W2b |

Builders: Sonnet (`builder` agent type), one isolated worktree each, branch off fresh
`origin/main`, same-day squash-merge. Reviewers: Opus (`reviewer` agent type) on every
PR — correctness, house-law conformance (display-only, PIT, i18n, synapse/dag, budget
gate), and stats review on PR-E. Fable (main loop) adjudicates and merges.

---

## 7. Guardrails (ratified, with amendments)

Paper guardrails 1–10 RATIFIED. Amendments and additions:

11. **PIT or forward — never in between** (R-SP12). A label may join a historical
    fire only if recomputable from data knowable at fire date.
12. **No parallel taxonomies** (R-SP2/3/17). Existing enum = the enum.
13. **Disguise kill test is mandatory** before any label chips imply differentiation.
14. **Coverage is a first-class output**: every axis prints coverage + proxy basis;
    GEX-derived modes print their ~384-name universe; SI-derived labels print
    settlement as-of; archetype retro cells print the FY2009+ watermark.
15. **Engine-job budget is untouchable**: the nightly personality pass rides an
    existing loop under a measured ≤2-min gate; heavy history compute is on-demand
    host-side only.
16. **Board at-rest surface stays two-glyph** — personality renders only inside
    expanders/detail pages until earned otherwise.
17. **Analyzable-n honesty**: study tables print attachable/tested n per cell;
    `insufficient_n` cells are never silently dropped or silently tested.

---

## 8. Come-back clocks

| Clock | When | What |
|---|---|---|
| dna_class presence check | first factor_panel rebuild post-merge | verify 55-col partitions + dna_class.json emit; consumers null until then |
| GEX persistence | ≥63 accrued days of polygon_gex chains (~2026-09-15) or thetadata_eod backfill | charter persistent gamma personality |
| FINRA SI accrual | ~2026-10-01 (≥8 settlement snapshots) | tinderbox label gains time-series basis; re-check disguise test |
| Forward-ledger review | n≥50 per collapsed cell OR 2026-12-15, whichever FIRST | first compat review; promotion needs n≥150 + ≥2 quarters + R-SP13 |
| CN/HK/CA v2 | after forward ledger matures + census matrix re-check | market-by-market charter, no parity claims |
| Crowding engine charter question | 2026-Q4 | `hedge_fund_crowded` habitat unlock |

---

## 9. Adjudication log

| Date | Event |
|---|---|
| 2026-07-06 | Census wf_6022c28c (10 lanes) complete; paper adjudicated; R-SP1–R-SP20 issued; waves W0–W5 chartered. |
| 2026-07-06 | Red-team panel wf_029126e5 (house-law / architecture / stats, Opus ×3): 7 blocking + 9 amendment findings adjudicated. Major corrections: factor_panel job has no OHLC (architecture moved into the engine job's stock-library pass under a measured budget gate); registry has TWO invalid entries (R-SP16 broadened); dna_class retro exclusion re-justified (partition depth, not R3); archetype retro coverage collapse surfaced (~37% attachable); species retro arm dropped (species_id 100% null); primary endpoint reduced to binary P(STOPPED); disguise test recast as regression-with-controls; forward clocks made reachable; synapse cadence/storage enums corrected to legal values; gate_fires corpus marked regenerate-at-study-time. |
| 2026-07-07 | W1–W5 all shipped (#1730 path lib, #1737 cascades, #1759 nightly wiring, #1853 UI, #1854 Oracle/NW). First production print (1,722 tickers): archetype coverage 0.86, chart 0.76, dna_class 0.0 (pre-P1-C, clock 07-13). R-SP21 issued: v1.1 re-anchor of the two degenerate chart labels (82%→~6%, 38%→~10%) + second-feature conditions per R-SP4. Forward ledger produced no rows on 07-06 (zero buy/rebuy fires that day — consistent, unverified until the next fire day). |
