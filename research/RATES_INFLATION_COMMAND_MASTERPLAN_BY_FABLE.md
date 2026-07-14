# Rates & Inflation Command (RIC) — Grandmaster Plan

Prepared by Fable (main loop), 2026-07-13. Program: `rates-inflation-command`.
Status: W0 charter — ratified by Fable adjudication 2026-07-13 (status log at foot).
Method: 10-lane repo census (release radar / OPEX rulings / transmission / options data /
risk radar / ledger+loop / momentum / cycles / policy / conventions) + 7-lane web-grounded
domain research with per-claim Opus adversarial verification + first-hand Fable reads of
`OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`, `MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md`,
`RATE_INFLATION_TRANSMISSION.md`, `DO_NOT_REBUILD.md`, `docs/ACTIVE_BUILD_MAP.md`.

**Operator directive (2026-07-13, verbatim intent):** upgrade the release radar (CPI, PPI,
NFP, claims) and OPEX signals for accuracy and robustness; measure OPEX risk from EOD,
intraday, and whole-market options data, including vanna/charm windows across the monthly
cycle, and give OPEX dates a visible risk level; consolidate/deep-wire the release radar
with the `transmission.html` lobes into one rates-&-inflation command surface with forward
path (rates and inflation), policy-condition awareness, and forward sector anticipation;
wire event/OPEX windows into the risk systems as risk elevations that may mark turning
points; enroll everything in forward ledgers and the self-improvement loop; and front-load
the learning with pre-registered historical studies so the system starts smart rather than
learning only from forward mistakes.

---

## 0. Scope fence

**What this program IS:** a display-tier command program that (a) executes the parked
W-OVC options build docket and extends it into a whole-market dealer-surface history and
an OPEX-window risk read; (b) builds the missing macro **event-window engine** (CPI/FOMC/
NFP/claims weeks) on the blessed `engine/opex.py` idiom; (c) builds the missing
**yield-series momentum organ** (the machinery of the operator's 10Y/20Y STOCH-RSI case
study) with confluence tags and a rates→cohort transmission bridge; (d) composes the
existing forecast/path/policy organs into one **Forward Path board**; (e) merges the
user-facing surfaces into a unified Rates & Inflation Command page; (f) enrolls every new
organ in forward ledgers, scorecards, and the metabolism improvement loop; and (g)
front-loads priors via pre-registered historical studies over stores we already own.

**Authority ceiling (program-wide):** display/context. Every new artifact ships with
`{may_rank:false, may_gate:false, may_size:false, may_escalate:false}`, `score_raise=False`,
`hard_gate=False`, tier `display`. Promotion of any leg beyond display happens only through
the pre-registered Lane-(ii) gauntlets named in §7 clocks, each with pre-committed gates and
come-back dates, adjudicated separately. The gauntlet is a promotion gate, not a build gate:
nulls print, accrual continues, non-standalone survivors are retained as confluence inputs.

**What this program is NOT (standing kills honored — see §2):** not a directional OPEX
signal; not a pre-event conviction dampener; not an administration-timing or policy-intent
predictor; not a re-open of killed constructions (signed-charm, charm-intensity narratives,
S-INDEX-PIN, air-pocket, quad-roll seasonal rule, put/call OI ratio, midterm-standalone,
CPI revision-direction, Hindenburg/Titanic/MCO families); not an entry conditioner; not an
LLM-originated anything.

---

## 1. Census — what exists, what is genuinely missing (adjudicated gap map)

### 1.1 What already exists (do not rebuild; wire it)

| Capability | Home | State |
|---|---|---|
| Release forecasts: CPI h/c, NFP, PCE h/c, PPI, claims-benchmark; champion + 3 CPI shadows (`v3_factor`, `cpi_bridge`, `mf_energy`); quantile bands (vol-scaled, MRI-R30); benchmark set incl. Cleveland + Kalshi median; forward ledger + scoreboard + pinball + per-cutoff scoring; quirk flags; print-integrity chip; 5-tab modal + compact cards | MRI program (11 waves closed; `engine/release_forecast*.py`, `scripts/build_release_forecast.py`, macro.html panel) | MATURE. Open comebacks C-1..C-14 |
| OPEX calendar engine: `tag()` (td_since/td_to/in_opex_week/in_post_opex/is_quad_cycle/phase), measured NW-HAC phase seasonality, `snapshot()` | `engine/opex.py` → `site/vol/regime.json['opex']` | LIVE, display-only doctrine baked in |
| Vanna/charm computation: `bs_greeks` vanna/charm; net VEX/CEX, charm_anchor, charm_net_sign; per-expiry vanna_net/charm_net | `engine/greeks.py`, `engine/gex_engine.py`, `engine/options_hub.py` | COMPUTED BUT UNPLUMBED (adjudication §1: "never plumbed to state/tests") |
| Registered OPEX gates: `S-VANNA-RELIEF`, `S-FRONT-CHARM` (BH-FDR family 22→28) + W-OVC build docket | `OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md` §5, `OPTIONS_ALPHA_MASTERPLAN.md` §4 | REGISTERED, **NEVER BUILT** (come-back was 2026-07-20) |
| Options data: ThetaData T1 store — 383 roots incl. SPX/SPXW, EOD+OI 2012→, full greeks (incl. vanna/charm) 2017→, 60 GB, theta-ops-wt local; Polygon GEX per-ticker snapshots; live intraday flow poller (120 s, ~122 roots → R2); massive_options_day whole-market per-contract 2024→; CBOE PCR/VIX curve (shallow) | `collectors/thetadata.py`, `engine/thetadata_store.py`, `scripts/live_flow_poller.py` | T1 store is the crown jewel; **no market-wide gamma/vanna/charm surface is built from it** |
| Transmission leaf: measured driver×asset IC matrix, honest scored-leg gate (ALL legs fail — "repricing flags risk, not return"), transmission chains, conditional scenarios | `engine/rate_inflation_transmission.py`, `scripts/calibrate_rate_inflation.py`, transmission.html | LIVE weekly-calibrated; roadmap items 1–4 unbuilt |
| Fed path/stance: ZQ/SR3 implied path vs FEDTARMD dots, gap_bp, implied_cuts_12m; hawkish/dovish stance; catalyst tone | `engine/fed_path.py`, `engine/fed_stance.py` | LIVE in latest.json, bonds/policy_watch |
| Policy conditions: policy_lever card (verbatim conditions-framing), policy_intent_desk falsifiable theses, Treasury Watch TGA detector, net-liquidity canon, whitehouse sentinel, repricing_coherence + shock de-escalation | PS program (PS-R1..R9), `engine/treasury_watch.py`, `engine/market_drivers.py` | LIVE, display/context-only by law |
| Risk radar: Tier-A/B scares, evidence gate lift_2020≥1.20, context gate, election-cycle modulator (the lawful calendar-modulator pattern), recovery chips C1–C12, forward logs, **#2518 scorecard → improvement-loop lobe → every dashboard card** | `engine/risk_radar*.py`, RRX masterplan | LIVE. The modulator + Tier-B accrual are the only lawful entry paths for new risk channels |
| Momentum machinery: canon RSI-MACD + StochRSI KD; `mtf_snapshot` D/3D/W/M; vectorized cross-series; IHM organ (13 index carriers, display-dark); confluence tiers T1–T4; K-of-N `mtf_upturn`; commodity two-phase 0-100 confluence scorer | `engine/canon.py`, `engine/cycles.py`, `engine/index_momentum.py`, `engine/commodity_confluence.py` | MATURE for equities. **ZERO callers on yield series** |
| Cycles/seasonality: election-cycle modulator (+ XLV/XLP/XLU midterm-H2 sector_bias display), BTC halving thesis monitor w/ falsifiers, sector/country cycle DNA, factor seasonality, TOM research | `engine/election_cycle.py`, `engine/btc_cycle_thesis.py`, `engine/sector_cycles.py` | LIVE. The operator's midterm/healthcare/BTC-cycle context already exists as display organs |
| Forward-ledger + loop chassis: keep-FIRST PIT ledgers, nightly sole advancer, #2518 scorecard pattern, synapse registry, lobe charters + fitness sensors → PROPOSE-eligible, anomaly monitor → insight bus → agenda | `engine/cycle_forward_log.py`, `engine/risk_radar_scorecard.py`, `engine/metabolism/*`, `config/synapse.yml`, `config/lobe_charters.yml` | MATURE. Exact enrollment recipe documented (census lane 6) |

### 1.2 What is genuinely missing (the build surface of this program)

1. **W-OVC execution** — the adjudicated OPEX state columns/stamps/gates exist only on
   paper. `front7_charm_share`, `front7_gex_share`, `signed_vanna_pressure`,
   `vanna_hedge_5d`, `root_class`, `opt_vanna_relief` stamps, gate cells, family_size
   22→28 fix: none built. OPEX shows on 3 surfaces as plain caution chips with **no risk
   level anywhere**.
2. **Whole-market dealer-surface history** — the T1 store contains everything needed
   (per-strike OI + full greeks for SPX/SPXW/SPY/QQQ/IWM + sector ETFs, 2017→) and no
   aggregation script builds the date-series of net GEX/VEX/CEX by root-class. Without it
   there is no historical basis for "how loaded is THIS opex window vs history".
3. **Event-window engine** — `engine/opex.py` is the house-blessed template for macro
   event-cycle windows (census: "the correct template for any new macro event-cycle window
   (CPI week, FOMC week) — tag + measure + display, never a scored dampener") and no
   CPI/FOMC/NFP equivalent exists. No event-collision detection (CPI-in-OPEX-week,
   FOMC+CPI same week). No ex-ante release-risk read (implied event move is computable
   from T1 near-dated SPY straddles; never computed).
4. **Yield-series momentum** — `stoch_rsi()`/`macd_parts()`/`mtf_snapshot()` are generic
   but have zero callers on yield series. No DGS20 series (the operator's 20Y case study
   is uncomputable today). No yield-turn confluence tags, no yield-turn forward ledger, no
   historical yield-turn event study.
5. **Rates→cohort bridge** — the transmission matrix stops at broad ETFs. No measured
   cohort map for rate-transmission groups (exchanges CME/ICE/CBOE/NDAQ, banks, insurers,
   builders, gold miners, REITs, duration growth) that a yield-turn event can light up.
   (`engine/stock_macro_sensitivity.py` exists as the single-name substrate.)
6. **Forward Path board** — fed_path, MRI projections, breakevens, Cleveland, transmission
   state, TGA/net-liquidity, policy conditions all exist and are never composed into one
   forward-path read with divergence flags.
7. **Unified surface** — transmission.html (495-line template) and the macro.html Release
   Radar panel do not reference each other at all.
8. **Loop enrollment** — none of the above (existing OR new) rates/inflation organs are
   charter-enrolled with fitness sensors; transmission has an artifact-level synapse
   entry (`transmission-latest`) but no lobe charter / fitness-sensor enrollment — the
   W9 gap is the charter layer, not the registration.
9. **Front-loaded priors** — no pattern library for event-window/yield-turn behavior;
   the existing `release_playbook` (surprise→asset reaction) is descriptive v1 with no
   regime conditioning; the 33-episode surprise-anatomy catalog is UI-only reference.

### 1.3 Collisions declared (ACTIVE_BUILD_MAP 2026-07-13, 0 open PRs)

No open PRs at charter time. Standing adjacent programs whose territory this program
touches read-only or extends by amendment: MRI (extend via §6 W10 amendment under MRI
law), OPTIONS_ALPHA / OPTIONS_NW (W1 executes their registered docket verbatim; W-F stays
PARKED — its preconditions are NOT satisfied by this program and nothing here claims them),
RLT (rebalance/liquidity — boundary: RIC owns rate/inflation/event-window state; RLT owns
rebalance-flow and TGA-impulse mechanics; the Forward Path board consumes RLT artifacts
read-only), RRX (risk radar — RIC registers new legs/chips only through RRX's documented
three-tier path), IHM (index momentum — RIC's yield organ is a sibling, not a modification;
shared canon math), PS (policy — consumed read-only, conditions-framing preserved).

---

## 2. Standing law compliance (kills honored, laws restated)

Every row here was read first-hand from `research/DO_NOT_REBUILD.md` and the source
adjudications before design. Constructions this program must NOT contain:

- **Signed-charm / charm-intensity narratives** — KILLED (vol/size confound; partial IC ≈ 0;
  "the study's strongest volatility predictor was the confound"). RIC ships |·|-share and
  magnitude constructions only, per RUL-OVC-3.
- **Any directional/return use of vanna/charm/OPEX states** — killed (F-21: "vol >>
  direction"). OPEX risk levels are vol/holdability/de-escalation context (RO-3).
- **Calendar quad-week edge, S-QUAD-ROLL** — dead 2005-16 regime. `is_quad_cycle` stays a
  context flag.
- **S-INDEX-PIN, air-pocket, put/call OI ratio, post-OPEX-release bucket** — killed/parked
  per RUL-OVC-4/5/6; post-OPEX "window of weakness" remains a WATCH item printed with its
  honest Era3-only status, never an authority claim.
- **Pre-event conviction dampener** — FORBIDDEN (DATA_SIGNAL_EXPANSION #11, MRI-R3,
  D-vec-CAT: "pre-FOMC drift died after 2016 and the announcement premium is positive, so
  a dampener is wrong-signed"). Event windows NEVER multiply any score. Judge-panel
  extension (2026-07-13, adopted): because a risk-radar Tier-B leg at/above caution
  ADVANCES radar state and state sets gross (`engine/risk_radar.py` armed+confirm
  escalation + `_gross_for`), a **calendar-gated leg at ANY radar tier is the same
  forbidden mechanism laundered** — so NO calendar/event-window-gated construction may
  register in `_SCARES` at all. Event/OPEX window states are display context in the risk
  radar. The only future risk-channel path is a CALENDAR-AGNOSTIC construction (e.g. the
  dealer-load state, which fires whenever dealer books are extreme, OPEX or not) with its
  own Lane-(ii) phase-0 lift; a band-nudge modulator variant would additionally require
  its own evidence + separate adjudication (election-cycle precedent).
- **Administration-timing predictors / policy-intent classifiers / LLM geopolitical
  probabilities** — FORBIDDEN (PS-R1/PS-R4 verbatim honored). Policy enters as measured
  conditions + falsifiable theses ("Conditions under which violent reversals are more
  likely — not intent, not timing").
- **Midterm/election cycle standalone** — REFUTED; survives only as the US risk-radar
  modulator + display sector_bias. RIC consumes, never re-tests, never extends to intl.
- **CPI revision-direction model** — KILLED before attempt (MRI-R38). Not revisited.
- **Scored macro surprise / entry conditioning / consensus fakery** — MRI-R1/R2/R5 honored;
  "benchmark" never "consensus"; nothing conditions entries.
- **Positioning fusion; LLM origination; kernel conditioning before NW clocks; fused
  composite scores (RO-2)** — all honored. The OPEX window read is a K-of-N stack of raw
  states (commodity-confluence idiom), not a fused score.
- **Estimator laws** — ticker-cluster bootstrap w/o time control forbidden; era split at
  2010 mandatory + 2021+ slice; episode-unit / within-month permutation primary;
  month-block bootstrap known anti-conservative; verdicts only at pre-declared
  `horizon_role` rulers; Wilson-on-raw-n forbidden.
- **Two-lobe cap (RUL-P1/NWC-U2)** — scoped to the NW rails program (L1/L3); RIC charters
  no L-series lobe. New display organs register via synapse + lobe_charters under the
  roster governor (66/5 caps), which has capacity.
- **RUL-P10** — every new store in this program declares its commit path in its PR (§6
  wave table carries the declaration).

---

## 3. Architecture — seven pillars

The program is one organ family with seven pillars. Data flows left to right; every box
that emits state also stamps a forward ledger; every ledger feeds a scorecard; every
scorecard feeds the metabolism loop.

```
                       ┌──────────────────────────────────────────────────────────┐
                       │            RATES & INFLATION COMMAND (display)           │
                       │                                                          │
 T1 options store ───▶ │ P2 OPEX risk engine ──┐                                  │
 polygon gex / live ─▶ │  (dealer surfaces,    │                                  │
                       │   window risk read)   ├─▶ P3 Event-window engine ──┐     │
 event_calendar ─────▶ │                       │   (CPI/FOMC/NFP/OPEX tags, │     │
 ALFRED vintages ────▶ │                       │    collisions, ex-ante     │     │
                       │                       │    release risk)           │     │
 MRI release radar ══▶ │  P1 accuracy waves    │                            ├──▶ P6 unified surface
 (existing, amended)   │                       │                            │    (transmission.html
                       │                       │                            │     rebuilt; macro.html
 FRED yields ────────▶ │ P4 yield momentum ────┤                            │     cards deep-wired)
 (DGS2..30 + new 20)   │  organ + confluence   ├─▶ P5 Forward Path board ───┘     │
 fed_path / MRI /      │  tags                 │   (rate path, inflation          │
 breakevens / policy ▶ │                       │    path, divergence flags,       │
 conditions / RLT ───▶ │ P4b cohort bridge ────┘    policy conditions)            │
                       │                                                          │
                       │ P7 ledgers → scorecards → charters → improvement loop    │
                       │    + pre-registered historical pattern-miner             │
                       └──────────────────────────────────────────────────────────┘
   Risk-radar entry: event/OPEX window legs go ONLY through RRX Tier-B accrual or the
   modulator pattern, each behind its own pre-registered gauntlet (§7 clocks).
```

### P1 — Release radar accuracy (MRI Wave-12 amendment)

Executed **under MRI law** (attempt caps, frozen specs, strongest-naive kill benchmarks,
MRI-R28..R39a all binding). Chartered tracks, each frozen before any backtest:

- **C-2 market-implied distribution**: wire the Kalshi full distribution (not just median)
  as a `benchmark_set` member with its own basis tag; TTL ≤5d staleness law stands.
- **C-4 retail sales activation**: RSAFS ALFRED vintages + release calendar wiring; the
  scaffold already exists; attempt-1 clock starts at wiring.
- **C-10 CPI sub-index vintaging**: add SASLE/OER/rent sub-indices to `vintage_series`
  (ALFRED output_type=2); then and only then decide whether to spend `cpi_bridge` attempt
  #2 on the PIT-clean scope-fixed re-run (MRI-R29 gate).
- **C-12 NY Fed SCE collector** (keyless) as a fourth expectations source — also unblocks
  transmission roadmap item 3.
- **C-13 DOL state-claims breadth** (keyless) as a claims-quality context series.
- **Claims model attempt-1**: claims is benchmark-only today. Freeze a spec (holiday/
  seasonal-artifact-aware AR + state-breadth features from C-13) with kill rule vs
  strongest naive on the weekly block-aware ruler (MRI-R9). One attempt.
- **W11-G wiring verification**: census flagged that `release_integrity.py`'s header says
  the nightly wiring "is not yet called" while §12.6 says shipped — verify against the
  producer; fix or correct the doc.

Explicitly NOT in scope: re-opening Track R (NFP revision-direction — killed at Wilson LB
50.6% ≤ 54.7% base), any CPI revision model, any consensus purchase decision.

### P2 — OPEX risk engine (three layers)

**Layer 1 — W-OVC execution (adjudicated docket, verbatim).** New raw columns on
`options_entry_state` (`front7_charm_share`, `front7_gex_share`, `signed_vanna_pressure`,
`vanna_hedge_5d`, `root_class` ∈ {index_etf, sector_etf, industry_etf, single_name});
stamps via the A9 single-writer (`opt_vanna_relief`, `opt_front7_charm_share`,
`opt_root_class`); gate cells for `S-VANNA-RELIEF` + `S-FRONT-CHARM`
(`scored=false, building_history`); family_size 22→28 fix; RUL-OVC-8 naming harmonization
(`opex_days` calendar vs `td_to_opex` trading — one canonical pair, documented).

**Layer 2 — whole-market dealer-surface history (the new data unlock).** A new builder
reads the T1 store per (date, root) for a FROZEN roster — SPX, SPXW, SPY, QQQ, IWM, DIA +
11 SPDRs + SMH/XBI/KRE (the robustness-addendum slice, extended by SPX/SPXW which Polygon
cannot serve; host-verified 2026-07-13: greeks parquets 2017→2026 present for every
roster root, QQQ from 2012, 380 roots / 60 GB total) — and writes a date-series
2017→present of per-root and per-root-class aggregates: `net_gex_bn`, `net_vex`,
`net_cex`, `front7_abs_charm_share`, `front7_abs_gex_share`, `total_abs_gamma_notional`,
`oi_notional`, plus expiry-bucketed breakdowns (front-week / front-month / back).
**Scope fence: the surface covers index_etf / sector_etf / industry_etf classes ONLY —
single_name is deliberately out of scope for Layer-2 aggregates** (sparse per-name OI,
unreliable dealer sign per the SqueezeMetrics single-name caveat); the `root_class` enum
still carries single_name for W1's per-ticker state, which has its own producer. Laws
baked in: OI[t−1] (OPRA timing law, `shift(1)` as in `thetadata_store.doi_series`),
dealer-sign printed as an unobservable assumption on every consumer, |·|-magnitude
constructions preferred (sign-robust), root_class mandatory alongside any front7 read
(RUL-OVC-3). **Ops profile (judge-panel corrected):** the T1 store is HOST-LOCAL
(`/Users/chriswong/theta-ops-wt/data/thetadata_eod`) and NOT visible to the self-hosted
Actions runners (isolated FS; daily.yml documents this verbatim) — so BOTH the one-shot
backfill AND the nightly forward accrual run on the **theta-ops launchd lane**,
co-located with `com.macro.thetadata-backfill` (after its nightly pass), committing
`data/options_surface/*.parquet` via that lane's narrow git commit (the
`_backfill_state.json` pattern). Nothing surface-related runs in daily.yml. W2 opens
with a **coverage-audit precursor**: per-root first/last greeks date + per-year row
counts printed BEFORE the builder is written; the roster freezes over roots passing a
coverage floor, and an accrual-liveness audit artifact (the `audit_thetadata_accrual`
pattern) makes a dead accrual loud instead of an empty green ledger. `hard_exit()`
guarded (pyarrow one-shot law). Store: `data/options_surface/{root_class}.parquet` —
committed (small aggregates, ~single-digit MB), single-writer, synapse-registered.

**Layer 3 — the OPEX window risk read (what the operator asked to SEE).** A new leaf
`engine/opex_risk.py` composes a **literal unweighted state count** — `n_hot /
n_applicable`, the `mtf_upturn` K-of-N idiom, NOT the commodity-confluence weighted
0-100 score (judge-panel correction: `commodity_confluence.score_side` is weighted and
citing it left an unfrozen degree of freedom; no per-state weights exist here, frozen at
W0):

| state | source | construction |
|---|---|---|
| `concentration_hot` | Layer 2 | front7_abs_charm/gex_share percentile vs own root-class history ≥ P80 |
| `dealer_load_extreme` | Layer 2 | \|net_vex\| or \|net_cex\| percentile ≥ P90 (magnitude, sign-agnostic) |
| `gamma_regime` | existing gex board | long/short/flip-proximity (context) |
| `pin_proximity` | existing pin_risk | opex_days ≤5 + long gamma + wall ≤2% |
| `vanna_relief_active` / `vanna_drag` | Layer 1 | RUL-OVC-1 state (holdability read; symmetry caveat printed) |
| `event_collision` | P3 | CPI/FOMC/NFP inside the OPEX week; quad + quarter-end stacking |
| `window_phase` | engine/opex.py | opex_week / post_opex / mid_cycle + is_quad (context flags) |

Output: a plain-word window state per the design doctrine. **Tier-1 copy spec (frozen
per Design Doctrine Laws 1–3):** the glance line MUST carry a stance verb and plain
words — e.g. "OPEX Friday in 3 days — heavy dealer load, CPI lands the same week.
Expect sticky tape into Friday, thin cushion after. **Watch, don't chase.**" (EN/ZH) —
with the raw state count, each underlying state, and its measured, era-split RV/drawdown
stats demoted to hover/Tier-2. The **risk level** is the count of hot states (0–2 quiet /
3–4 elevated / 5+ heavy), `n_hot/n_applicable` availability-normalized — a state stack,
not a score. Framing is vol/holdability/turn-WATCH only; the post-OPEX weakness watch
item prints its honest Era3-only status. The W3 mockup must pass the doctrine 5-second
test with the stance verb before build (not just the banned-token grep). Surfaces: vol
regime page, the calendar strips (event_calendar OPEX rows gain the level chip),
intraday flow desk `dealer_context` extension, and the unified page (P6). Intraday: the
live_flow poller's tide artifacts gain the current window state as pass-through context
(no new polling; max_concurrent=2 law untouched).

**Forward ledger:** `data/opex_windows/forward_log.jsonl` — one row per monthly window
stamped at T−5 before expiration (keep-FIRST): the full state stack + level; graded when
mature on pre-declared rulers — forward 5d/10d realized vol vs trailing, max drawdown in
the post-window 10d, and range-compression into expiry (pin behavior). Grading targets are
VOL/PATH objects, never directional return (RO-3 / F-21 law).

### P3 — Event-window engine

New leaf `engine/event_window.py`, cloned from the `engine/opex.py` idiom (155 lines:
tag → measure → snapshot), covering the macro release calendar:

- **`tag(dates)`** — per trading day: `td_to_cpi`, `td_to_fomc`, `td_to_nfp`, `td_to_ppi`,
  `claims_day`, plus phase labels frozen at W0: {`cpi_day`, `cpi_week`, `fomc_day`,
  `fomc_week`, `post_fomc_3d`, `nfp_day`, `quiet`} and **collision states**
  {`cpi_fomc_same_week`, `cpi_in_opex_week`, `fomc_in_opex_week`, `triple_stack`
  (release + FOMC + OPEX)}. Historical date spines: ALFRED `realtime_start` for release
  dates (the vintage store already carries them), a static FOMC meeting list 1994→
  (announcement era) checked against the Fed's published archive, `engine/opex.py` for
  expiration days.
- **`seasonality(close)`** — measured forward return AND forward realized vol per phase,
  Newey-West HAC t, era split at 2010 + 2021+ slice, sub-period sign check — the exact
  opex.py measurement contract. The Lucca-Moench pre-FOMC drift is measured and expected
  to print DEAD post-2016 (that's the honest display; the house already ruled on it).
- **`snapshot()`** — current phase + measured stats + the collision read.
- **Ex-ante release-risk read (night before a print):** deterministic composition —
  MRI surprise-dispersion (predicted vs benchmark spread in σ-surprise units), the
  **implied event move** extracted from T1 near-dated SPY straddles (front-expiry ATM
  straddle spanning the release, computable EOD from the store; printed vs the trailing
  realized event-move distribution), current gamma regime + window phase (P2), and the
  print-integrity chip. Renders as a display chip on the MRI release cards' CONTEXT tab
  and the unified page. It annotates uncertainty; it never shifts a projection value
  (MRI-R20 law) and never scales any score (no-dampener law).

**Risk-system wiring (judge-panel corrected — display-only, no `_SCARES` entry):** the
originally-drafted event_window Tier-B leg is STRUCK. The panel's house-law lens proved
it unlawful: a Tier-B scare at/above caution advances radar STATE one level
(armed+confirm conjunction), and state sets gross via `_gross_for` — so a calendar-gated
leg makes event proximity a contributor to a sizing change, the exact mechanism MRI-R3 /
DATA_SIGNAL_EXPANSION #11 forbids, regardless of sign or tier. Therefore: **event/OPEX
window states enter the risk radar surfaces as display context only** (a context chip on
the radar card and recovery panel, like the cycle_context chip — rendered, never read by
`compute()`). The one lawful future risk-channel candidate is pre-registered instead:
**`dealer_load_extreme` (P2), a CALENDAR-AGNOSTIC construction** — it fires whenever
dealer books are extreme, OPEX week or not — which may attempt the standard Lane-(ii)
phase-0 (lift_2020 ≥ 1.20, frequency-matched permutation, 2020+ holdout) once ≥ 12
months of surface history exist; a null lands at display confluence, printed. Any
modulator-pattern variant (band nudge on watch/caution) would require that evidence PLUS
a separate operator-ratified adjudication (election-cycle precedent). No calendar
construction may ever enter `_SCARES` (see §2).

**Forward ledger:** `data/event_windows/forward_log.jsonl` — one row per release event
stamped at T−1 (ex-ante read frozen) — graded on realized event-day move vs implied,
realized vol vs phase base rate, and (descriptively) direction-of-surprise × reaction sign
by regime. Keep-FIRST; nightly sole advancer.

### P4 — Yield momentum organ + confluence (the case-study machinery)

New organ `engine/yield_momentum.py` (`yield_momentum.v1`), sibling of IHM, canon math
only (IHM-R8):

- **Roster (frozen at W0):** DGS2, DGS5, DGS10, **DGS20 (new FRED collector — exists at
  FRED, absent locally)**, DGS30, DFII10 (10Y real), T10Y2Y (2s10s), plus the MOVE index
  and TLT close (the price-side mirror so every yield read has its inverted price twin —
  sign discipline enforced structurally: yield-up = bond-price-down is printed on every
  surface).
- **Grids:** D / 2B / 3B / W-FRI (the operator's "3D" = house 3B; "2D" = 2B), canon
  RSI-MACD + StochRSI KD per grid, cross events with quality tags (washout_turn ≤20,
  deep_cross, standard_cross) — the IHM event vocabulary, so downstream consumers speak
  one language. A `rates` entry is added to `CYCLE_PRESETS` documenting that DC/IC band
  detection is NOT enabled for yields (bands are equity-fitted); only the oscillator/
  cross layer runs.
- **Confluence tags (pre-declared, K-of-N idiom):** `long_end_turn` (≥2 of {10Y, 20Y,
  30Y} fire same-direction cross within 5 sessions on 3B) — the operator's June-30 case
  is the archetype; `curve_turn` (2s10s cross), `real_turn` (DFII10 cross — feeds the
  gold/duration channel), `broad_rates_turn` (long_end + MOVE regime agreement). Tags are
  display states with fade base-rate context printed (mtf_upturn law).
- **Forward ledger:** `data/yield_momentum/forward_log.jsonl` — one row per cross/
  confluence event (keep-FIRST, PIT); graded at pre-declared horizons h21/h63 on (a) yield
  direction hit, (b) yield move magnitude in bp, (c) the P4b cohort follow-through
  (descriptive). The **ruler is frozen here, before the first stamp**: primary = h21
  direction hit vs a same-side-of-200dma base rate; secondary = h63; era split; episode
  permutation at read time; first read at §7 clock.
- **Historical study (proactive learning, pre-registered in §5.3):** one-shot backfill
  replay of the full cross/confluence event history 1990→2026 from FRED daily series —
  the event catalog + per-regime hit rates land in the pattern library BEFORE the organ
  goes live, so the display can say "this construction fired N times since 1990; h21
  direction hit X% (era-split table)" from day one. Display-tier honesty: backfill and
  live cohorts never blend in one badge (truth-schema law).

### P4b — Rates→cohort transmission bridge

Extends `scripts/calibrate_rate_inflation.py` with a **cohort matrix**: a frozen roster of
rate-transmission cohorts — exchanges (CME, ICE, CBOE, NDAQ), banks (KRE, KBE), insurers
(IAK), homebuilders (XHB, ITB), gold complex (GLD, GDX), REITs (IYR), utilities (XLU),
duration growth (QQQ/ARKK), small caps (IWM), regional detail via existing ETFs — versus
the existing drivers PLUS two new ones: `us10y_chg21` (fast leg) and `move_level`
(rates-vol; unblocks transmission roadmap item 4 by collecting ^MOVE into the CI cache).
Same leakage-free split-half Spearman method, same era discipline, single-name betas carry
the standing "secondary betas are noisy" caveat. Output feeds a **"who responds"** display
panel: when a P4 confluence tag fires, the panel shows the cohort map's measured,
era-split responses at h21/h63 with CIs — plain words ("Exchanges and banks historically
firmed when long yields turned up; utilities/REITs lagged"), never a recommendation verb.
The operator's CME/ICE case study is the archetype row and ships as a worked example in
the pattern library with its honest caveat (n, era, the "narrative at the time said
otherwise" context note).

### P5 — Forward Path board

New leaf `engine/rates_inflation_command.py`: a deterministic read-only composition —
no new model, no LLM origination:

- **Rate path row:** ZQ/SR3 implied path (m1/m3/m6/m12) vs FEDTARMD dots (`fed_path.gap`),
  implied cuts/hikes, next FOMC + SEP flag, EFFR/corridor state. Divergence flag when
  |gap| > threshold (frozen).
- **Inflation path row:** MRI next-print projections (CPI h/c, PCE when in cycle) +
  Cleveland nowcast + breakevens (1y proxy via swaps absent → BE5Y/BE10Y + 5y5y) + the
  expectations triangle (market/model/survey) with the anchoring read — vs the 2% target.
  Divergence flags: projection-vs-breakeven wedge, re-acceleration state (existing
  transmission fields).
- **Risk row:** real-rate SPEED percentile (the honest strongest leg — "flags risk, not
  return" printed), MOVE regime, bear/bull-steepener tag (constructed here; the RRX W4
  docket names it — coordinate, don't duplicate: RIC builds the tag as display context and
  RRX consumes it for its W4 wave), term-premium state. **Series labeling (judge-panel
  corrected):** FRED `THREEFYTP10` is the **Kim-Wright** model (the config.yml comment
  calling it ACM is wrong and gets fixed in W7); the true ACM series (NY Fed ACMTP10,
  keyless CSV from the NY Fed term-premia page) is collected nowhere today — **W7 adds
  the ACM collector**, after which the board's term-premium read is the **ACM-vs-KW
  divergence itself** (§5.2: a 47bp structural disagreement on the same 2023 move —
  model-dependence IS the signal). Until the collector lands, the board prints KW-only
  with an honest "KW model; ACM pending" note.
- **Policy conditions row:** policy_lever state, TGA watch episode, net-liquidity 4wk ROC,
  next QRA window (static calendar), jawboning counts — all read-only joins, verbatim
  conditions-framing disclaimer.
- **Stance sentence (glance tier):** deterministic template over the rows — e.g. "Market
  prices two cuts by December while inflation prints sit above what breakevens imply —
  long yields have room to stay heavy; fast repricing is the risk to watch" — generated
  from calibrated fields only, LLM may narrate/de-escalate downstream (master_brain), not
  originate here.

Forward ledger: `data/rates_command/forward_log.jsonl` stamps the board's divergence
flags nightly (keep-FIRST); graded descriptively (did the market path converge to dots or
vice versa; did the wedge resolve print-ward or market-ward) — this is the substrate for
the improvement loop to learn WHICH divergence reads carry information, without any
authority claim.

### P6 — Unified surface (the merge)

`transmission.html` is rebuilt as **the Rates & Inflation Command page** (working title;
final name at mockup ratification): Forward Path board (P5) on top → Release Radar block
(the full existing panel, mounted from the same `site/macrodata/release_forecast.json`
data as macro.html; the 5-tab modal and MRI-R39a card laws apply unchanged) → yield
momentum + confluence panel with the "who responds" bridge (P4/P4b) → event/OPEX window
strip (P3/P2 risk levels on the calendar) → the existing transmission chains + scenarios
(retained, restyled). macro.html keeps its cards and gains deep links ("Full rates &
inflation command →"). **Zero-fork reality check (judge-panel corrected):** the radar
today is NOT a shared component — its shell is Jinja inside `templates/dashboard.html.j2`
and its render logic is an INLINE `<script>` in macro.html, with page-scoped CSS keyed
on `body.page-macro #release-radar`. W8 therefore includes explicit sub-steps BEFORE the
second mount: (a) externalize the radar render JS into a shared site asset, (b) re-scope
the radar CSS from `body.page-macro` to a component class, (c) verify zero-fork with a
post-build grep for divergent radar markup across both pages, and (d) honor the
template/site byte-sync law (`check_template_site_sync`) for every paired asset touched.
Mockup-first + operator ratification + Playwright browser verification at 1280/375,
light/dark, EN/ZH (house UI law); design-doctrine §5 checklist; banned Tier-1 vocabulary
enforced (no "vanna", "charm", "GEX", "confluence", "prereg" at glance tier — plain
words with technicals in hover/detail).

### P7 — Self-improvement + proactive learning

- **Ledgers:** every pillar's ledger above (opex_windows, event_windows, yield_momentum,
  rates_command) + the existing MRI/transmission artifacts, all keep-FIRST PIT, nightly
  sole advancer, RUL-P10 commit-path declarations.
- **Scorecard:** `engine/ric_scorecard.py` on the #2518 pattern — per-organ hit/coverage/
  freshness blocks, min-n floor 5, atomic write to `data/rates_command/scorecard.json` +
  `site/ricdata/scorecard.json`, glance-tier track-record lines on every RIC card (the
  #2518 card idiom), "validated" banned from copy.
- **Charters:** synapse registration for every artifact (full field set; display tier;
  `external_consumers: [mastermind:context]` where the brief should see it), then
  `config/lobe_charters.yml` entries with **structured fitness_sensors** (e.g.
  yield_momentum: h21_direction_hit_rate, ledger_freshness, coverage; opex_risk:
  window_grade_rate, rv_forecast_skill vs base; event_window: implied-vs-realized event
  move calibration; forward_path: divergence-resolution tally) — each with
  `maturity_date` + `accruing: true` (accrual-honesty law) so the metabolism loop can
  PROPOSE improvements once sensors mature. Anomaly-monitor thresholds registered in
  `config/metabolism_anomaly.yml` (staleness, band-break on hit rates).
- **Autonomy ceiling (stated plainly — judge-panel addition).** The metabolism loop is
  AUTONOMY_PAUSED by default and its propose/adjudicate lanes are not fully armed: the
  honest deliverable of loop enrollment is that matured sensors generate **shadow
  draft-PR proposals which a human adjudicates and merges** — no RIC weight, model, or
  surface self-modifies. The operator's "grows on its own" ask is delivered as "notices
  its own decay/opportunities and PROPOSES the fix, with receipts" — which is also what
  house law permits.
- **Lawful action space for matured sensors (frozen).** A matured RIC fitness sensor may
  cause the loop to PROPOSE exactly three kinds of change, each human-adjudicated:
  (1) **display graduation/demotion** — elevate a pattern-library entry to a glance-tier
  card or demote a decayed one (display reordering, zero authority); (2) **kill/WATCH
  dockets** — flag a construction whose ledger says it decayed for an adjudicated
  registry row; (3) **gauntlet preregs** — when a display sensor clears its
  pre-committed threshold, propose the Lane-(ii) promotion attempt. Weight/rank/gate
  changes are structurally outside the loop's reach (they require the §7 gauntlets +
  operator ruling). Without this enumeration the "improvement loop" would collapse to a
  dashboard of hit rates; with it, the loop's job is triage + pre-registration.
- **Pattern library (the front-loaded brain):** `data/rates_command/pattern_library.json`
  — the cycle-DNA idiom applied to macro events: one entry per pattern with {construction,
  mechanism note, era-split stats, n, provenance: historical_study | forward_ledger |
  external_research(cited), caveats, kill/watch status}. Seeded at W5/W11 from §5;
  advanced thereafter ONLY by ledger grading and adjudicated studies. Display surfaces
  read the library; the LLM brief may cite entries verbatim (numbers must exist in the
  artifact — ADB epistemics law).
- **Pattern-miner (pre-registered, §5.3):** a frozen lattice study over
  {event-window phase × dealer-load state × yield-momentum state} → forward RV / drawdown
  / rebound cells, BH-FDR within pre-declared families, era split, within-month episode
  permutation, embargo 2024-01-01 for estimation with 2024→ as the honest OOS print.
  Survivors land in the pattern library as display context with their stats; NOTHING
  promotes without a separate forward gauntlet. This is the "learn from history now"
  engine, run as an ops one-shot, repeatable quarterly.

---

## 4. Ruling table

- **RIC-R1 (scope + ceiling).** Program is display/context tier end-to-end. All five
  authority booleans false on every artifact; promotion only via the pre-registered
  gauntlets in §7. The gauntlet is a promotion gate, not a build gate; nulls print and
  accrue as confluence context.
- **RIC-R2 (OPEX risk framing law).** OPEX/dealer states inform vol expectation,
  holdability, stop-width, de-escalation, and turn-WATCH only (RO-3 restated). No
  directional claim, no short signal, no score origination. Sign-dependent constructions
  print the dealer-sign-assumption caveat; |·|-magnitude constructions are preferred.
  The window "risk level" is an availability-normalized K-of-N state stack (no fused
  score — RO-2 honored).
- **RIC-R3 (no-dampener law, panel-hardened).** Event/OPEX proximity never multiplies,
  scales, or dampens any score, rank, or size anywhere — and because Tier-B radar legs
  advance state and state sets gross, **no calendar/event-gated construction may
  register in `_SCARES` at any tier**. Event/OPEX window states are display context in
  risk surfaces (rendered, never read by `compute()`). The only risk-channel path is a
  calendar-AGNOSTIC construction (dealer_load_extreme) through its own Lane-(ii)
  phase-0; any modulator variant needs that evidence plus a separate operator-ratified
  adjudication, watch/caution bands only, never manufacturing a loud banner.
- **RIC-R4 (W-OVC fidelity).** W1 executes the OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION §5
  docket as written; RUL-OVC-1..8 bind; that adjudication's §7 kill list is not
  re-litigated here. W-F (Oracle sector lane) stays PARKED; nothing in RIC claims its
  preconditions.
- **RIC-R5 (dealer-surface laws, panel-corrected).** The options_surface store computes
  under OI[t−1]; roster and constructions frozen at W0 (§3 P2 L2); index/sector/industry
  ETF classes only (single_name out of Layer-2 scope); root_class mandatory alongside any
  front-expiry concentration read; per-root-class percentiles only (no cross-class
  pooling); **backfill AND nightly accrual both run on the theta-ops launchd lane**
  (store is host-local, invisible to Actions runners — nothing surface-related in
  daily.yml), with a W2-precursor coverage audit freezing the roster over passing roots
  and an accrual-liveness audit artifact; store committed with named single-writer
  (RUL-P10).
- **RIC-R6 (event-window laws).** Phase taxonomy + collision states frozen at W0 before
  any measurement; measurement contract = opex.py idiom (NW-HAC, era split at 2010 +
  2021+ slice, sub-period sign check); measured stats are display context; the ex-ante
  release-risk read annotates uncertainty and never shifts a projection (MRI-R20) or a
  score (RIC-R3). Implied-event-move extraction is deterministic from the T1 store EOD;
  its method is frozen in the W4 PR before first publication.
- **RIC-R7 (yield organ laws).** Canon implementations only (IHM-R8); roster + grids +
  confluence tags frozen at W0 (§3 P4); no DC/IC band detection on yields; grading rulers
  frozen before the first ledger stamp; backfill and live cohorts never blend in one
  badge; display copy carries fade base rates; nothing conditions entries.
- **RIC-R8 (cohort bridge laws).** Cohort roster frozen at W0; measured-beta panel with
  era split; single-name rows carry the noisy-beta caveat; the "who responds" panel uses
  historical-response language only — no recommendation verbs, no ranks, no sizes.
- **RIC-R9 (forward-path laws).** The board is a deterministic join of existing calibrated
  artifacts; "benchmark" never "consensus" (MRI-R5); conditions never intent (PS-R1/PS-R4
  verbatim); LLM narrates/de-escalates only (MRI-R4); divergence thresholds frozen in the
  W7 PR; the stance sentence is template-generated from calibrated fields.
- **RIC-R10 (ledger + loop law).** Every new organ ships: keep-FIRST PIT forward ledger
  advanced only by nightly; synapse registration (full field set); charter with structured
  fitness_sensors carrying maturity dates (accrual-honesty); scorecard block in the RIC
  scorecard; anomaly-monitor enrollment. Ledger primitives and grading rulers are frozen
  in each organ's build PR before first stamp.
- **RIC-R11 (proactive-learning law).** Historical studies and the pattern-miner run only
  from specs frozen in this document or in a prereg addendum committed BEFORE computation;
  episode-unit permutation primary; era split mandatory; BH-FDR within pre-declared
  families; estimation embargo 2024-01-01 with 2024→ printed as OOS; survivors are
  display-tier pattern-library entries with provenance tags; promotion requires a separate
  forward gauntlet. External-research claims enter the library only with citations and
  only after the adversarial-verification pass (§5 provenance).
- **RIC-R12 (surface-merge law, panel-extended).** transmission.html rebuild is
  mockup-first with operator ratification; the Release Radar mounts from the SAME data +
  a SHARED render asset on both pages — which requires W8's explicit refactor sub-steps
  (externalize the inline macro.html radar JS; re-scope `body.page-macro` radar CSS to a
  component class; zero-fork verified by post-build grep; template/site byte-sync law
  honored). MRI-R39/R39a laws apply on both mounts. Design-doctrine §5 + bilingual
  parity + browser verification before merge; banned Tier-1 vocabulary enforced
  (vanna/charm/GEX/gamma-regime stay in hover/detail tiers); every RIC glance chip
  carries a stance verb (P2-L3 copy spec pattern).
- **RIC-R13 (MRI amendment law).** P1 executes under MRI's own masterplan law; this
  program may not alter MRI verdicts, attempt counts, or benchmarks; the W10 PR appends
  its tracks to the MRI masterplan §13 (Wave-12) with frozen specs and kill rules.
- **RIC-R14 (model routing).** Fable (main loop) plans/adjudicates/merges; Opus reviews
  every wave (adversarial, incl. running the full downstream suite of every touched
  module); Sonnet builds; effort low on mechanical stages. No spawned Fable. Builders get
  explicit "no git ops" specs; the main loop owns git.
- **RIC-R15 (store commit paths — RUL-P10 table).** `data/options_surface/*` committed,
  single-writer build_options_surface; `data/opex_windows/`, `data/event_windows/`,
  `data/yield_momentum/`, `data/rates_command/` committed JSONL/JSON, single-writer each,
  nightly-only; T1 raw store stays theta-ops-wt gitignored; any artifact >30 MB moves to
  R2 with a publish_r2 registration in the same PR.

---

## 5. Field guide — seeded priors (research-verified) and pre-registered studies

*Provenance discipline (RIC-R11): every entry below is tagged. `[V]` = claim survived the
Opus adversarial-verification pass (7-lane web research, 2026-07-13); `[W]` = weakened —
directionally supported but stated with its correction; `[H]` = to be established from our
own stores by the pre-registered studies in §5.3 (the honest default for anything our own
data can measure). Verification verdicts and corrected statements are recorded here so the
pattern library can cite them verbatim. This section seeds the library; the ledgers own it
thereafter.*

### 5.1 Domain priors — options/OPEX (full corrected statements: `RIC_DOMAIN_RESEARCH_PACK_2026-07-13.md`, lanes opex-mechanics + event-window-risk)

Library-seed digests. Every magnitude below is the CORRECTED post-verification form.

- **[W] Pinning is real but conditional, not constant.** Strike-clustering on monthly
  expiration is replicated (Ni-Pearson-Poteshman 2005: ≥16.5 bps lower-bound alteration,
  ~1996-2002 sample; Golez-Jackwerth 2012: futures pinning ~11 bps lower bound, sample
  ends 2009) — but magnitudes are regime-contingent, sign flips with dealer net-gamma,
  weekly-option replication failed, and NO post-2012/post-0DTE peer replication exists.
  Encode: pin-proximity as a conditional state near high-OI monthly strikes (which is
  exactly what the existing `pin_risk`/S-PIN_RISK construction does), never a fixed bps
  prior. Consistent with our own adjudication (§3.2: ETF vol-suppression real 3/3 eras
  but NOT OPEX-specific).
- **[W] Gamma-sign → intraday behavior is real but asymmetric and index-validated only.**
  Negative aggregate dealer gamma → last-30-min momentum (Baltussen et al 2021, JFE,
  1974-2020, OOS R²≈2.9%); positive gamma shows ABSENCE of momentum, not reliable
  mean-reversion (the mean-reversion leg is single-stock + illiquidity-conditioned,
  Barbon-Buraschi WP). Sample ends 2020 — pre-0DTE. Encode sign as context (matches our
  GEXR doctrine "vol >> direction"); the −20 bps/SD magnitude has ~nil incremental power
  over VIX+ATM-IV controls and must NOT ship as a calibrated number.
- **[W] Post-OPEX "window of weakness" is folklore-tier.** The −0.9% post-OPEX week
  average (Quantifiable Edges, 1960-2024) has no published t-stat, conflates pre-options
  eras, and the "March/June/September worst" claim is WRONG (post-March-OPEX is
  historically positive; the bearish concentration is post-quarterly Sep ≈ −0.94%, Jun
  ≈ −0.8%). The OPEX-week strength effect (Stivers-Sun 2013, 1988-2010) decayed
  post-publication. Both match our own RUL-OVC-5/D verdicts. Encode: measured on OUR
  data in HS-3 with era splits; display only what survives, with the Era3-only watch-item
  status we already carry.
- **[W] 0DTE changed the field.** ~half or more of SPX volume is 0DTE by 2025; average
  effect is vol-DAMPENING (~60 annualized bps lower RV on 0DTE days, Dim-Eraker-Vilkov)
  because dealers average net-long gamma — but state-dependent: negative-gamma states
  amplify (up to +3.3pp annualized). Monthly-OPEX gamma concentration is structurally
  diluted; quarterly retains ~2-3× MONTHLY magnitude (not "×daily" — that folklore
  number was refuted). Encode: window states must be gamma-sign-gated, never
  calendar-only — which is why the P2 risk read composes dealer-load states with the
  calendar instead of shipping calendar seasonality (RUL-OVC-5 restated by the evidence).
- **[W] CHEX/VEX are computable EOD; only vanna's realized SIGN needs the IV direction.**
  Charm flow direction is knowable ex-ante (time passes); vanna exposure is computable
  but its realized flow sign requires the IV move — so `vanna_hedge = −net_vanna × ΔIV`
  (our existing Family-C construction) is the correct form and a pure calendar-vanna
  signal is not. Dealer sign (+call/−put) is more reliable for index than single names —
  root_class stratification (RUL-OVC-3) is independently confirmed.
- **[V] Announcement-day premium is real; the pre-FOMC drift is conditionally dormant.**
  Savor-Wilson holds out-of-sample (~55-60% of equity premium on ~10-13% of days; Fed
  2023-2025 sample: CPI 45/FOMC 49/NFP 53 annualized bps of priced event premium,
  concentrated in the tightening era) — and it is CONTESTED (Ghaderi-Seo: partly
  small-sample + policy-surprise artifact). The Lucca-Moench drift is dead post-2016 in
  low-vol regimes but is better encoded VIX-gated-dormant than extinct. Both support the
  standing no-dampener law: the premium is positive — de-risking into events is
  wrong-signed on average.
- **[W] Implied event move is extractable and premium-inflated.** Variance additivity
  (σ²_term·N = σ²_regular·(N−1) + σ²_event) yields the event-day implied move
  (× 0.8 MAD factor); it is risk-neutral bookkeeping that systematically OVERSTATES
  realized moves (FOMC implied 1.0-1.2% vs realized 0.7-0.9%) and under-identifies under
  multi-event clustering. Encode as display transform vs the trailing realized event-move
  distribution (P3 spec), never a forecast. NFP event risk is often NOT separable from
  the surface (33% identification vs CPI 80%) — print per-release identifiability.
- **[V] Kalshi dispersion predicts surprise magnitude, not direction.** Implied IQR →
  |surprise| slope 0.75, R²=0.20, n=45, concentrated in the high-inflation subperiod;
  implied median direction hit 57% ≈ chance. Directly supports MRI C-2 wiring the FULL
  distribution as a dispersion/uncertainty input (magnitude channel), and killing any
  direction read from it.
- **[W] Event × OPEX interaction is mechanism-credible and UNMEASURED.** High-gamma weeks
  muting event reactions is practitioner consensus with no peer-reviewed effect size.
  This is precisely HS-4's job on our own store — the plan encodes NO prior here beyond
  "worth measuring."

### 5.2 Domain priors — releases, rate path, regimes, transmission (full text: research pack, lanes release-forecasting / rate-path-modeling / regime-patterns / transmission-channels / self-learning-systems)

**Releases (feeds P1/MRI-W12 and P3):**
- **[W] Cleveland nowcast beats consensus on headline, regime-dependently** (0.41pp RMSE
  vs SPF long-sample; edge reversed at the 2022 disinflation turn; core ≈ parity but
  daily). Supports keeping it a benchmark, not a champion.
- **[V] New-tenant rents lead OER ~4 quarters** (NTRR/ZORI ρ≈0.93; house-price→OER peak
  corr ~0.75 at 16-month lag) — but state-dependent, heavily revised, and with an
  irreducible ~2-quarter structural OER smoothing floor. Our champion's ZORI shelter leg
  is on the right variable; the LAG is the improvable part (MRI-W12 scope).
- **[V] ADP is not an NFP predictor** (changes-basis R² ≈ 0.13 ex-COVID, ≈ −0.03
  2021-22; the 0.98 figure is a levels artifact). Anti-prior: do not add ADP to the
  bridge.
- **[W] Claims-based labor models are the productive lane** (claims+JOLTS construct cut
  U-rate RMSFE >22% vs RW in one unreplicated KC-Fed WP; treat as hypothesis for the
  claims-model attempt-1 spec, not settled). Holiday weeks + the March-2024 SA
  methodology break + frozen pandemic adjustments are hard PIT hazards for any claims
  spec (backtest windows must not cross 2024-03 without re-estimation).
- **[W] Benchmark-revision sign is regime-dependently anticipable from the QCEW-CES gap**
  (called 2024 −818k/2025 −911k in advance; direction WRONG in 2020/2021; magnitude
  understated by >100k). Supports the existing nfp_preliminary_benchmark quirk flag +
  a QCEW-gap context field, NOT a revision model (Track R stays dead).
- **[V] Print-reaction regime law:** the CPI×rate-uncertainty yield response was ~zero
  pre-COVID and flipped positive+significant post-2021 (BIS WP 1361, permutation-clean);
  the equity "good news = bad news" sign is regime-gated and its hot-print leg is
  statistically weak. HS-2 must therefore be regime-bucketed (hiking/cutting/pause) and
  never pool eras — reinforces MRI-R9.
- **[W] Fed-surprise endogeneity (Bauer-Swanson):** high-frequency policy surprises are
  ~16-19% predictable from pre-meeting data; correction needed for macro-effect
  estimation, NOT for asset-price event studies. Constrains any future reaction-function
  study design in HS-2.

**Rate path (feeds P5):**
- **[V] FedWatch-style ZQ math is a risk-neutral proxy, not a probability.** Day-weighted
  meeting extraction is correct mechanics (our fed_path approach is sound); premia
  ~35-61bp/yr, consecutive-meeting months inflate noise ~9×, multi-meeting horizons
  unreliable. The premium is SIGN-SWITCHING by regime (positive/countercyclical
  pre-2010, ~−1 to −2 bp/month recently) — encode as regime-conditioned adjustment, not
  the folklore "+36-72bp hike-bias."
- **[V] Term-premium attribution is model-dependent by construction** (2023 tantrum:
  ACM said 116/115bp premium, KW said 69/44 split — a 47bp structural disagreement).
  P5 must show the ACM-vs-KW divergence itself as the signal, never one model as truth.
  ACM series = NY Fed ACMTP10; FRED THREEFYTP10 is Kim-Wright — do not mislabel.
- **[W] Yields are near-RW at short horizons; the exception is trend.** DNS/affine
  12-month edges are fragile; time-series momentum on bond futures is the century-
  documented exception (MOP 2012; profitable since ~1880; whipsaw risk at pivots). This
  is the evidence line under P4: momentum-on-rates is the one construction with a
  literature behind it, and our TSMOM bond-compass leg already embodies it — P4 adds the
  oscillator/turn layer with its own forward ledger rather than claiming the literature
  covers it.
- **[W] Supply/plumbing now matter more:** post-2010 auction demand ~5× more inelastic
  (~9bp per 1% of same-tenor outstanding vs ~2bp pre-2010); repo issuance-sensitivity is
  QT-state-dependent; QRA surprises are a confluence input on term premium (the Nov-2023
  "89bp QRA rally" is 3-6× overattributed — FOMC + soft CPIs landed the same week).
  Deficit-projection → long-yield prior belongs at ~10-25bp/pp (not fixed 25).
- **[W] Breakevens are three things:** expected inflation + sign-unstable risk premium
  (−20..+50bp era-dependent) + liquidity premium that blows out 100-300bp exactly in
  stress. P5 uses the Cleveland decomposition and prints raw-breakeven distrust in
  stress states.
- **[W] Dot-plot regime risk is live:** Warsh withheld his dot (June 2026) and chartered
  a communications review — SEP-based fields in fed_path must carry a structural-break
  flag until the year-end review resolves (and hawk-dove NLP priors trained pre-2026 are
  suspect).

**Regimes & cycles (feeds P4/P7 pattern library):**
- **[V] 2023 top anatomy (the archetype for turn context):** ~5.02% Oct-2023 top; the
  RISE was term-premium-driven (QT + issuance + uncertainty), the FALL was
  expectations-driven (soft Oct/Nov CPIs + refunding shift). n=1 descriptive
  decomposition — a library narrative entry, not a rule.
- **[W] Curve-shape rules need the driver, not the shape:** bull-steepening ≈ bearish
  only WHEN recession-driven (insurance-cut steepeners 1995/1998/2024-25 were bullish);
  the 2022-24 inversion was a 783-793-day false positive for recession. Encode
  steepening-TYPE (bear/bull decomposition by leg) as the state, never the slope alone.
- **[W] Sector-by-regime folklore, corrected:** 2022 utilities OUTPERFORMED (+1.4% abs,
  +19pp rel) — "bond proxies always lose in rising rates" is false when growth fear
  co-moves; REIT/growth duration damage is real but regime-conditional (growth-vs-value
  2022 spread ~24pp, third-largest since 1975, reversed 2023). Bank NIM sensitivity
  FLIPPED SIGN across cycles (negative 1994-2006 asset-weighted, positive 2015-18,
  non-durable 2022-23; deposit-beta ~40% crossing marks the compression inflection).
  All cohort-map entries in P4b carry era-split betas because of exactly this.
- **[V] Gold×real-yields regime break is durable-so-far:** −0.73 avg correlation
  2003-2021 → ~0 post-2022 on >1,000t/yr central-bank buying; the P4 `real_turn` tag
  must carry the CB-demand regime flag (rolling-corr gate) or it will misfire on gold.
- **[W] Calendar anomalies decayed:** FOMC even-week cycle insignificant post-2004
  (single-manuscript decay evidence — medium confidence "dead"); pre-FOMC drift dormant
  (above). Midterm/presidential-cycle stats are n≈15-24 — weak priors only; healthcare
  midterm outperformance (~17% avg, 1994-2024, n≈8) stays a display-tier
  `sector_bias`-style note, which is exactly its existing home.
- **[REFUTED→corrected] The CME float folklore:** CME's rate-level float benefit is the
  NET ~$54M→$356M retained spread (2021→2023), not the $5.1B gross pass-through; and
  CME rate-volume co-moves with MOVE at DAILY frequency but weakly at monthly (BIS 2003:
  no significant monthly vol-turnover link; the Apr-2026 "-45% on MOVE collapse" was
  mostly quarterly-roll seasonality). The operator's CME/ICE case study encodes as:
  fast channel = rate VOLATILITY→volume (daily, weak monthly), slow channel = rate
  LEVEL→net float spread (~low-hundreds-$M/yr, quarterly lag untested), plus the
  volume-response nonlinearity (extreme sustained vol → deleveraging → volume DOWN).
  This is the flagship example of why the pattern library requires verified corrected
  magnitudes: the folklore version overstates the float channel ~10×.
- **Transmission speed map [W, various]:** same-day channels = homebuilders (mortgage-
  rate direction, level-nonlinear above ~7%), duration equities (unprofitable growth
  fastest), gold (pre-2022 regime only); lagged-quarters channels = bank NIM
  (deposit-beta dependent), exchange float income, insurer reinvestment (multi-year,
  muted by duration gaps). The P4b panel prints the SPEED class per cohort — a same-day
  cohort lights on the turn signal; a lagged cohort lights with "responds over quarters."

**Methodology (binds P7/HS specs; lane self-learning-systems):**
- **[V] DSR + PBO/CSCV are the multiple-testing spine** (effective-trial-count is the
  fragile input — correlated variants inflate N); **[W]** White/SPA correct for the
  tested set only (SPA power = studentization + sample-dependent null); **[V]**
  Beta-Binomial pseudocounts are the prior-encoding idiom (α+β = ESS; needs discounted/
  rolling ESS under non-stationarity — matches our prior-as-provenance design); **[W]**
  James-Stein/hierarchical pooling justifies pooling across SIMILAR event types only
  (expected aggregate risk, componentwise degradation possible — pool CPI with PPI,
  not with OPEX); **[W]** AND-gate confluence: independence-product is a lower bound
  (correlated signals fire together more often) but effective-N collapse is real —
  HS-4's per-cell n is printed for exactly this reason.

### 5.3 Pre-registered historical studies (frozen specs)

- **HS-1 Yield-turn event catalog (P4).** Universe: roster series (§3 P4), daily FRED,
  1990-01-01→2026-06-30 estimation window, 2024-01-01→ printed as OOS slice (embargo per
  RIC-R11 for any threshold fitting; the cross constructions themselves are parameter-
  frozen canon math, so the full window is reportable descriptively). Events: 3B StochRSI
  bullish/bearish crossovers under/over 20/80; 3B RSI-MACD crosses; the §3 P4 confluence
  tags. Measures per event class: n, h21/h63 yield-direction hit vs same-side-of-200dma
  base, median bp move, MAE/MFE in bp, era split (pre/post-2010, 2021+), within-month
  episode permutation p at read. Output: pattern-library entries + the organ's display
  base rates.
- **HS-2 Event-day reaction library (P3).** Universe: CPI/NFP/FOMC/PPI/claims dates from
  ALFRED realtime_start + FOMC archive, 1998→ (matching the surprise-anatomy catalog era),
  SPY/TLT/DXY/GLD daily. Measures: per phase (§3 P3 taxonomy) forward 1d/5d return + RV,
  NW-HAC, era split; surprise-direction × reaction sign by regime bucket (hiking/cutting/
  pause per fed_path history; "good news = bad news" regime flags) — descriptive, feeds
  the library and the release cards' CONTEXT tab. Extends `release_playbook` v1 with
  regime conditioning; does not alter MRI models.
- **HS-3 OPEX-window dealer-load study (P2).** Once Layer-2 history exists (2017→):
  per-window (n≈114 monthly windows) ex-ante state stack vs forward 5d/10d RV, drawdown,
  and pin range-compression — the exact rulers the forward ledger will grade on, measured
  retrospectively first so the display ships with honest base rates. Era partition per
  OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT (greeks eras 2017-19/2020-22/2023→). The
  robustness addendum's partial-IC discipline applies: every "predicts vol" claim is
  residualized on trailing RV20 + size before it may be described as incremental.
- **HS-4 Pattern-miner lattice (P7).** Frozen cell space: event-window phase (7) ×
  dealer-load tercile (3) × long-end momentum state (3: washout-turn/neutral/overbought-
  roll) = 63 cells × 3 targets (fwd 5d RV, fwd 10d max drawdown, fwd 21d SPY return-sign
  base-rate delta) = 189 tests in ONE BH-FDR family, q=0.10; within-month episode
  permutation; era split; estimation embargo 2024-01-01, 2024→ OOS printed. Cells that
  survive land in the library as display context (with the standing warning that AND-gate
  cells have small n — printed per cell). One run at W11; re-run quarterly by ops; NO
  promotion from mined cells without a separate forward gauntlet (RIC-R11).

### 5.4 The operator case study, encoded honestly

The June-2026 sequence (10Y 4.36% low → 3B StochRSI bullish crossover under 20 on
~Jun-30 → 4.66% by Jul-13; CME/ICE bottoming with the yield low; 20Y 3B MACD-RSI cross
confirming) ships in the pattern library as the archetype `long_end_turn` worked example:
the P4 organ detects exactly this construction; the P4b bridge surfaces the measured
exchange-cohort response; HS-1 establishes how often that construction resolved this way
since 1990 (era-split). The library entry carries the operator's own caveat verbatim: "we
cannot say yields will move higher from every such bottom — we say the base rate and the
cohort map, and we watch." Display copy follows suit (design-doctrine Law 1: stance in
plain words, even when the stance is "watch — don't chase").

---

## 6. Wave plan (each wave = one PR; branch off fresh origin/main; same-day squash-merge; Sonnet builds, Opus reviews, Fable gates)

| Wave | Deliverable | Key files (new ✚ / edited ✎) | Store commit path (RUL-P10) |
|---|---|---|---|
| **W0** | This charter | ✚ research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md | — |
| **W1 OVC** | Execute W-OVC docket: state columns, stamps, gate cells, family 22→28, RUL-OVC-8 naming | ✎ engine/options_entry_state.py, engine/options_stamp.py, scripts/stamp_options_state.py, scripts/validate_options_entry.py | existing stores |
| **W2 SURFACE** | Coverage-audit precursor → whole-market dealer-surface history: theta-ops backfill 2017→ + theta-ops nightly accrual + accrual-liveness audit | ✚ scripts/build_options_surface.py, engine/options_surface.py, coverage/liveness audit artifacts; ✎ theta-ops launchd lane (NOT daily.yml), config/synapse.yml, config/dag.yml | data/options_surface/*.parquet committed from theta-ops-wt, single-writer |
| **W3 OPEXRISK** | Window risk read (unweighted n_hot/n_applicable) + stance-verb level chips + forward ledger | ✚ engine/opex_risk.py, data/opex_windows/; ✎ build_vol_regime.py, event_calendar strip, intraday_flow dealer_context, templates | data/opex_windows/forward_log.jsonl committed, nightly-only |
| **W4 EVW** | Event-window engine + collisions + ex-ante release-risk read + ledger — display-only (NO _SCARES edit, RIC-R3); dealer_load_extreme Lane-(ii) prereg doc | ✚ engine/event_window.py, data/event_windows/, prereg addendum; ✎ release radar CONTEXT tab, macro strip, radar-card context chip (render-only) | data/event_windows/forward_log.jsonl committed, nightly-only |
| **W5 YIELD** | DGS20 collector, yield organ (display-dark), HS-1 study, ledger, pattern-library seed | ✚ engine/yield_momentum.py, scripts/build_yield_momentum.py, scripts/research/hs1_yield_turn_catalog.py, data/yield_momentum/, data/rates_command/pattern_library.json; ✎ collectors/fred config, engine/cycles.py (rates preset note) | both committed, nightly-only / one-shot research artifact |
| **W6 BRIDGE** | Cohort matrix calibration + "who responds" panel data + wire EXISTING yahoo/_MOVE into the transmission CI cache as move_level driver (collector already exists — engine/risk_radar.py reads it) | ✎ scripts/calibrate_rate_inflation.py, engine/rate_inflation_transmission.py, weekly.yml | data/transmission/* existing pattern |
| **W7 PATH** | Forward Path board engine + divergence flags + ledger + ACM collector (NY Fed ACMTP10, keyless) + fix config.yml THREEFYTP10 mislabel (it is Kim-Wright) | ✚ engine/rates_inflation_command.py, collectors/nyfed_acm.py, data/rates_command/forward_log.jsonl; ✎ engine/run.py join, config.yml, synapse | committed, nightly-only |
| **W8 PAGE** | Unified page: mockup → operator ratification → build (bilingual, browser-verified) incl. radar-JS externalization + CSS re-scope + zero-fork grep + template/site sync | ✎ templates/transmission.html.j2 (rebuild), templates/dashboard.html.j2 + site/macro.html (radar component extraction), macro.html deep links | site artifacts |
| **W9 LOOP** | Charters + fitness sensors + RIC scorecard + anomaly enrollment + card track-record lines | ✚ engine/ric_scorecard.py; ✎ config/lobe_charters.yml, config/synapse.yml, config/metabolism_anomaly.yml, card templates | data/rates_command/scorecard.json + site/ricdata/ committed |
| **W10 MRI-W12** | MRI accuracy amendment: C-2 distribution, C-4 retail, C-10 vintaging, C-12 SCE, C-13 claims breadth, claims-model attempt-1, W11-G wiring verification — **parallel, non-blocking, MRI-governed: W10 slippage does not gate W3–W9** (each track carries MRI's own attempt caps/clocks; may split into multiple PRs under MRI law) | ✎ MRI masterplan §13 + MRI engine/collectors per its own law | MRI stores |
| **W11 MINER** | HS-2/HS-3/HS-4 runs + pattern-library population + quarterly ops recipe | ✚ scripts/research/hs2_event_reactions.py, hs3_opex_windows.py, hs4_pattern_lattice.py | research artifacts + library JSON |

Sequencing: W1→W2→W3 serial (data dependency); W4 after W2 (needs dealer-load states);
W5 independent (can run parallel to W1-W3); W6 after W5; W7 after W4+W6; W8 after W7
(needs all panel data); W9 after W3/W4/W5/W7 ledgers exist; W10, W11 independent of the
UI chain and non-blocking. New test files ride the ci.yml whitelist in their own PRs.
Every wave PR: regenerate ACTIVE_BUILD_MAP awareness, run the downstream suites of every
touched module (review-must-run-downstream-suite law), template/site sync where
applicable.

**Nightly-budget note (judge-panel addition):** the deterministic composers (opex_risk,
event_window snapshot, rates_command board, yield_momentum organ) are cheap read-only
joins and land in the ENGINE job's build cluster; the only store-reading heavy step (the
dealer surface) lives on the theta-ops launchd lane entirely. The collect job (150m cap,
already near-saturated) gains nothing from this program except the DGS20/ACM FRED pulls
(seconds). Each wave PR states its measured step cost (measure, don't code-read-estimate
— asia-lane lesson) and confirms its job stays under cap before the commit step.

---

## 7. Clocks

| Date | Event |
|---|---|
| 2026-07-20 | W1 (W-OVC) lands — honors the original adjudication come-back date |
| 2026-08-15 | W2 surface backfill verified complete on the theta-ops lane (2017→; coverage + accrual-liveness audits green — an empty ledger fails loudly); W3/W4 ledgers accruing check |
| 2026-09-30 | First OPEX-window ledger review (≥2 graded windows); event-window ledger ≥8 release rows; HS-2/HS-3 complete |
| 2026-10-15 | RRX Tier-B batch come-back: **dealer_load_extreme** (calendar-agnostic) Lane-(ii) prereg readiness check (with jpy_carry/nh_contraction batch) — needs ≥12mo surface history so realistic attempt is 2027; MRI C-9 challenger-promotion adjudication window opens (n≥6 CPI prints) |
| 2026-12-15 | Yield-momentum ledger first read (≥1 quarter of events); pattern-miner re-run #1; fitness sensors maturity review → loop PROPOSE eligibility |
| 2027-01-15 | First significance reads (episode permutation) across RIC ledgers, aligned with the RRX recovery-chip read; promotion adjudications (if any gates pass) — separate ruling required |

---

## 8. Key sources

- `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md` + `_FINDINGS.md` (RUL-OVC-1..8, W-OVC docket, kill list)
- `research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md` (MRI-R1..R39a, comebacks C-1..C-14)
- `research/RATE_INFLATION_TRANSMISSION.md` (measured matrix; "risk, not return")
- `research/RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` (RRX-R1..R10; three-tier leg path)
- `research/POLICY_SHOCK_REGIME_MASTERPLAN_BY_FABLE.md` (PS-R1..R9; conditions framing)
- `research/OPTIONS_ALPHA_MASTERPLAN.md` §4 + `OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md` (gate registry; era partitions)
- `research/LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md` (T1/T2 tiers; OI timing law; signing provenance)
- `engine/opex.py` (the event-window idiom), `engine/election_cycle.py` (the modulator pattern), `engine/risk_radar_scorecard.py` (#2518 scorecard pattern), `engine/commodity_confluence.py` (K-of-N stack idiom)
- `research/RIC_DOMAIN_RESEARCH_PACK_2026-07-13.md` — the 7-lane adversarially-verified domain research pack behind every §5 provenance tag (full corrected claims, constructs, data sources, pitfalls)

### Status log

- 2026-07-13 — W0 charter drafted and adjudicated by Fable (main loop); census (10 lanes)
  and domain research (7 lanes + Opus verification) completed same day; §5.1/5.2 seeded
  from the verified research pack.
- 2026-07-13 — Three-lens Opus judge panel (house-law / feasibility / operator-fidelity):
  all three verdicts ship_with_fixes; two blockers fixed (event_window Tier-B leg STRUCK
  — calendar-gated `_SCARES` entries banned outright, RIC-R3 hardened; W2 accrual moved
  to the theta-ops launchd lane — store invisible to Actions runners) plus seven
  majors/minors (unweighted-count freeze on the risk level; KW/ACM series correction +
  ACM collector in W7; radar-JS externalization sub-steps in W8; autonomy ceiling +
  lawful sensor action space in P7; MOVE rewording; transmission-registration wording;
  W10 de-coupled non-blocking; Tier-1 stance-verb copy spec). T1 store coverage
  host-verified same day (roster greeks 2017→2026 present; 380 roots, 60 GB).
