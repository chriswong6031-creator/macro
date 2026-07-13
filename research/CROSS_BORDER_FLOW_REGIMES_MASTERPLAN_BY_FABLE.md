# Cross-Border Flow Regimes (CBF) — masterplan (by Fable)

**Repo:** Macro Dashboard · **Date:** 2026-07-13 · **Author:** Fable (main loop), from a 10-lane
census + web-research fan-out (6 repo census lanes + 4 field-guide lanes) adjudicated against
`INTL_RISK_DESK_MASTERPLAN_BY_FABLE.md`, `INTL_FIX_MASTERPLAN.md`, `DO_NOT_REBUILD.md`, and the
forex dashboard honesty bars.
**Operator ask:** study and research cross-border flows and forex relationships — how capital
moves between countries through FX/equity relationships; use as context for the international
alert systems (EM weak while US strong + USD rising = outflow; both strong = goldilocks growth);
how regimes affect performance and risk, including contagion from a country's debt/currency/market
blowing up, and the Fed's swap lines.

---

## §0 — Thesis and scope fence

IRD (complete 2026-07-12) answers *"is stress igniting and is it transmitting to US markets?"* —
a one-directional risk-desk read. CBF answers the complementary question the operator asked:
***"which way is capital flowing between the US and the rest of the world, and what does that
regime mean for performance and risk?"*** It is a persistent, bidirectional, flow-direction lens:
goldilocks synchronized growth, US-exceptionalism outflow, EM-rotation inflow, risk-off
convergence — inferred daily from FX × relative-equity × spread observables we already collect.

Scope fence (CBF-R1): **display/context tier only, zero scoring-seam wires.** Nothing here
touches `conditions`, `stock_score`, `name_score`, radar `_LEG_CALIB`/profiles, or `intl_feed`
weights. Promotion of any CBF metric to authority goes through `scripts/intl_phase0.py` as a NEW
pre-registered claim. Per house law the gauntlet is a promotion gate, not a build gate — this
context infrastructure ships freely, nulls printed.

**No true flow data exists free and daily** (TIC lags 6–7 weeks; EPFR/IIF paid; BoP quarterly).
CBF is therefore an *inference* layer over prices — and says so on every surface (CBF-R4).

## §1 — Adjudicated gap map (census 2026-07-13, 6 lanes)

Exists — reuse, do not rebuild:
- `forex_regime.py`: 6 episodic FX **stress scenarios** (carry_unwind, dollar_wrecking_ball,
  em_crisis_capital_flight [illustrative], haven_flight, reflation_risk_on, intervention_risk) —
  event detectors, not a persistent flow regime; display-only.
- `forex_dollar.py`: 7-leg dollar desk + IRD-R10 smile decomposition (rates-driven vs
  safety-driven vs mixed) — the "what kind of dollar move" read. REUSED as a CBF cross-ref.
- `forex_transmission.py`: dollar→asset betas (SPY/EEM/gold/oil/copper/UST10/BTC).
- `intl_performance.py`: USD leaderboard, RRG vs US, pairwise corr matrix, RORO dial.
- `contagion.py` (IRD): DY spillover (frozen basket) + two-tier contagion read
  (contained/watching/transmitting) — owns the "is it reaching US" question.
- `intl_risk.py` (IRD): EM stress composite; swap lines SWPT/WLCFLL in `liquidity_plumbing`
  Phase-5 (confirmation tier, IRD-R5).
- China lane: southbound connect live (northbound DEAD, SLF-050), CNH basis, AH premium (~5wk).
- Data: 23 country ETFs (majors 1996→), ~20 intl indices/FX pairs, DTWEX family (2006→),
  EM OAS ladder (accruing since 2023-06/07, 3y-capped — IRD-R9), IMF WEO (25 countries),
  BIS credit gaps (14).

Missing — the CBF build:

| # | Gap | Confirmed by |
|---|---|---|
| G1 | No persistent cross-border **flow-regime classifier** (goldilocks / exceptionalism / rotation / risk-off) anywhere; forex_regime is episodic stress, RORO is a dial | forex + flow-proxy lanes |
| G2 | No per-bloc **flow-direction gauges** (US↔Europe, US↔Japan, US↔EM…) from the FX×equity×spread triangulation | flow-proxy lane |
| G3 | No per-country **outflow-pressure (partial-EMP)** read; capital flight only exists as an illustrative stress scenario | forex lane |
| G4 | No **idiosyncratic-vs-systemic** discriminator for EM stress (breadth / common-factor / DM-transmission three-filter test) | all lanes |
| G5 | No historical **regime census** — how often each regime occurred, how long it lasts, what performance/risk looked like inside each | research lanes |
| G6 | **ACv2 (Alert Command Center) has zero international sources and its board backdrop context (`_load_context()`) is US-only**; no cross-border context reaches any alert surface | alert-systems lane |
| G7 | Swap-line case-law interpretation (what a drawing *means*, stigma asymmetry) not surfaced anywhere as plain-word context | ird-state lane |

Out of scope (standing kills / walls respected): per-pair FX gating (INTL-43), lead-lag
scanning (ADJ-4), C1–C8 constructions, cross-currency basis lane (IRD-R6 data-blocked),
TIC/EPFR collectors (lagged/paid — structural context only), quad-language bloc comparison
(INTL-39/40), parallel shock classifier (TI-R1), northbound connect (SLF-050).

## §2 — The regime taxonomy (FROZEN at W0; changes require a masterplan edit)

Grounded in the dollar smile (Jen 2001; BIS 2024 EM-flows evidence; Obstfeld-Zhou dollar cycle).
Four core states + `mixed`. All inputs daily, price-derived, already in stores.

**Inputs** (as-of daily close): `SPY` (US); RoW composite = equal-weight USD price return of the
frozen 12-ETF DY basket (EWJ EWG EWU EWC EWA EWL | EWZ EWW INDA EIDO EZA EWY — reusing the
IRD-R4 adjudicated membership for consistency; coverage-weighted before 2012); broad dollar =
`DTWEXBGS` (fallback `DX-Y.NYB` pre-2006); EM FX basket = equal-weight USD-per-local of the
collected EM pairs (MXN BRL ZAR TRY IDR CLP PLN KRW INR TWD; coverage disclosed); `^VIX`.

**Frozen classification rules** (first match wins; anti-flicker hysteresis: a new state must
hold 5 consecutive sessions before the published state switches):

1. `risk_off_convergence` — SPY 20d ≤ −3% AND RoW 20d ≤ −3% AND (broad-dollar 20d ≥ +1.5% OR VIX ≥ 25).
2. `us_exceptionalism_outflow` — (SPY 63d − RoW 63d) ≥ +3pp AND broad-dollar 63d > 0 AND EM-FX 63d ≤ 0.
3. `em_rotation_inflow` — (RoW 63d − SPY 63d) ≥ +3pp AND broad-dollar 63d < 0 AND EM-FX 63d > 0.
4. `goldilocks_synchronized` — SPY 63d ≥ +2% AND RoW 63d ≥ +2% AND |SPY 63d − RoW 63d| < 3pp
   AND broad-dollar 63d ≤ +1% AND VIX < 20.
5. `mixed` — otherwise.

Thresholds are theory-motivated round numbers frozen BEFORE the W1 census runs (no fitting);
W1 prints ±1pp / ±5-VIX sensitivity so the reader sees how labile the labels are (CBF-R3).

**Plain-word glance states** (Design Doctrine Law 1; ZH parity at build):
goldilocks → "Broad global risk-on — supported"; exceptionalism → "Capital favors the US —
overseas headwind"; rotation → "Money rotating overseas — dollar soft"; risk-off → "Global
de-risking — havens bid"; mixed → "No clear flow direction — watch".

**Companion reads** (same artifact, each with its own honest framing):
- **Per-bloc flow gauges** (G2): blocs = Europe (EWG EWU EWL), Japan (EWJ), Commodity-DM
  (EWC EWA), LatAm (EWZ EWW), EM-Asia (INDA EIDO EWY), EMEA (EZA), broad EM (EEM). Per bloc:
  mean z of legs — 20d relative-equity-vs-SPY (USD terms), 20d bloc-FX move, and (where the
  regional EM OAS ladder has ≥1y accrued depth) −1×OAS 20d velocity z. Direction bands:
  inflow ≥ +0.5, outflow ≤ −0.5, else neutral.
- **Outflow-pressure watch (partial EMP)** (G3): per country with both an FX pair and a country
  ETF: z(20d FX depreciation) + z(20d equity underperformance vs rolling 120d EEM-beta) +
  z(Δ20d FX realized vol). Explicitly labeled *partial* — the reserve/intervention leg of a true
  EMP index is unobservable free+daily (CBF-R4).
- **Idio-vs-systemic discriminator** (G4; computed when any EM outflow pressure is elevated):
  three-filter test — (a) breadth: share of EM FX pairs down >2% over 30d (>50% systemic-leaning);
  (b) common-factor share: mean pairwise 60d corr of EM FX daily moves, percentile vs 2y;
  (c) DM transmission: US HY OAS 20d velocity z ≥ 1. Verdict: 2–3 filters → `systemic`,
  1 → `spreading`, 0 → `isolated`. Forbes-Rigobon caveat printed: correlations are biased UP
  in high-vol windows, so (b) never stands alone.
- **Swap-line confirmation row** (G7): IRD-R5 restated — weekly SWPT level + Δ, graded by the
  4-tier interpretation table (field guide §3): C6 drawing = funding stress CONFIRMED;
  zero drawings ≠ absence of stress (stigma asymmetry). Never a trigger.
- **Cross-refs**: contagion two-tier state (IRD-R3) and dollar-smile regime (IRD-R10) echoed
  as chips so the desk reads flow-direction, transmission, and dollar-kind side by side.

## §3 — Architecture

- **Engine** `engine/flow_regime.py` — pure leaf, fail-open, imports nothing from scoring core;
  DISPLAY-ONLY header per forex_regime.py idiom. Reads: `data/intl_etf/*.parquet`,
  `data/intl/*` FX pairs + forex store pairs, yahoo SPY/EEM/^VIX, FRED DTWEX family,
  `data/forex/latest.json` (smile cross-ref), `data/intl_risk/latest.json` (contagion cross-ref),
  liquidity_plumbing swap-line keys, EM OAS ladder (depth-gated). Emits
  `data/flow_regime/latest.json` + appends `data/flow_regime/history.parquet`.
- **History backfill** (CBF-R10): the classifier is price-derived and deterministic, so full
  history (~1996→, coverage-disclosed) is backfilled ONCE at W2 first build; thereafter nightly
  is the sole advancer (append-only; RC-R2 spirit). Era split at 2010 stored as a column
  (DT-R16).
- **Wiring**: runs inside `build_intl.py` (cl_markets lane — fast leaf on already-loaded
  stores); `dag.yml` declaration + `synapse.yml` registrations (mag7-regime block = template);
  frozen-tail cadence entry for the new artifact.
- **Study** `scripts/cbf_regime_study.py` — one-shot, OFF the render path, `hard_exit()` guarded
  (pyarrow one-shot law). Consumes the same code path as the engine (no parallel
  implementation), writes `research/cbf/REGIME_CENSUS.md` + JSON artifacts.
- **Surfaces (W3)**: intl.html Risk Desk gains a **Cross-border flow** panel (regime chip +
  bloc arrows + outflow watch + swap-line row + discriminator chip); ACv2 `_load_context()`
  gains the flow-regime backdrop chip (display context on the shared board — NOT a new alert
  source, so nothing fires, nothing pushes: A7-safe); world_state gains a thin display lobe
  (`score_raise=False, hard_gate=False`).

## §4 — Rulings (CBF-R1..R12)

- **CBF-R1 · Scope fence.** Display/context tier only; zero scoring-seam wires; promotion only
  through `intl_phase0` pre-registered claims. Restates IRD-R1 / the constitution.
- **CBF-R2 · Flow-direction vocabulary.** CBF states answer "which way is capital flowing" —
  they are NOT a shock classifier (market_drivers stays canonical, TI-R1), NOT the contagion
  transmission read (contagion.py owns contained/watching/transmitting, IRD-R3), and NOT quad
  language (INTL-39/40: bloc quad scores are non-comparable). The three vocabularies ship
  side-by-side as cross-refs, never merged.
- **CBF-R3 · Frozen taxonomy.** §2 definitions/thresholds are frozen at W0, before any census
  computes conditional statistics. W1 reports threshold sensitivity; any retune is a masterplan
  edit with a dated ruling, never code drift.
- **CBF-R4 · Proxy honesty.** Price-inferred flows are directional inference, not measured
  flows. Every surface carries "inferred from prices" framing; the partial-EMP read discloses
  its missing reserve/intervention leg; known blind spots printed (FX-hedged flows invisible,
  SWF/OTC flows invisible, managed pegs truncate signals — CNH read stays illustrative-tier).
- **CBF-R5 · Discriminator law.** Idio-vs-systemic uses the three-filter test (breadth,
  common-factor share, DM-credit transmission); correlation-based filter (b) never stands alone
  (Forbes-Rigobon upward bias in vol spikes); the discriminator feeds Tier-1 *origin* framing
  only — Tier-2 US transmission remains owned by contagion.py.
- **CBF-R6 · Swap lines.** IRD-R5 restated: confirmation tier, never a trigger. Copy follows
  the 4-tier interpretation (C6 draw / EM-line draw / announcement-no-draw / FIMA usage);
  zero drawings ≠ no stress (stigma). Bahaj-Reis: swap lines cap funding stress (CIP ceiling)
  but do NOT fix solvency — copy must never say a drawing "resolves" anything.
- **CBF-R7 · No lead-lag, no per-pair gating.** ADJ-4 and INTL-43 restated. Transition-watch
  observables ship as descriptive case-law chips; nothing is scanned for lead, nothing gates
  per-pair. Any future "regime shift predicts X" claim requires its own intl_phase0 prereg.
- **CBF-R8 · Era honesty.** All historical statistics era-split at 2010 (DT-R16); basket
  coverage per era disclosed (INDA/EIDO start ~2012; DTWEXBGS 2006; EM FX pairs vary);
  no pooled-era inference, ever.
- **CBF-R9 · Descriptive statistics law.** W1 conditional tables (per-regime forward behavior
  at 10/20/63d) are DESCRIPTIVE — labeled so, no verdicts, no significance claims, overlap
  acknowledged (regime spells are long; effective N = spells, not days — printed with the
  tables). The word "validated" never appears (CI-enforced).
- **CBF-R10 · Backfill-then-accrue.** Price-derived history may be deterministically backfilled
  once; the history parquet is append-only thereafter with nightly as sole advancer; renders
  never rewrite published history (RC-R2 spirit).
- **CBF-R11 · Routing.** Sonnet builds, Opus reviews, Fable (main loop) adjudicates/merges;
  every spawned stage carries an explicit model; mechanical stages run effort=low. Builders get
  "no git ops" specs; main loop owns git.
- **CBF-R12 · Surface law.** Design Doctrine binds: plain-word stance per state (§2 vocabulary),
  banned vocab (EMP, z, slugs, basket names) demoted to hover receipts; one as-of + one footnote
  per panel; bilingual parity (ZH written via Write/Edit tools only + dedicated ZH review);
  ACv2 integration is board-backdrop context ONLY — no new alert family, no push lane, nothing
  originates or escalates (A7).

## §5 — Field guide (understanding-before-backtest)

Full distilled field guide with sources: `research/cbf/FIELD_GUIDE.md`. Load-bearing facts:

- **Dollar smile** (Jen 2001): USD strong at both extremes (crisis; US exceptionalism), weak in
  synchronized global growth. The smile is the theoretical spine of the §2 taxonomy. The
  2025-era "smirk" (weakened crisis leg) is contested commentary — tail-watch, not a regime.
- **BIS 2024 (qt2409d):** 1σ broad-dollar depreciation ⇒ ≈ +0.29pp EM local-bond flows,
  +0.16pp EM equity flows; dollar's flow influence has RISEN since 2014 while VIX's has fallen —
  the dollar IS the flow thermometer, which is why CBF keys on it.
- **Bruno-Shin (BIS WP695):** 10% dollar appreciation ⇒ ~70–80bp EM credit-spread tightening
  channel via dollar-debt balance sheets — why exceptionalism regimes RAISE blow-up risk in
  dollar-indebted EMs (original sin amplifier).
- **Forbes-Warnock (2012):** episode taxonomy surge/stop/flight/retrenchment — gross, not net;
  global risk (VIX) drives stops. Quarterly-only; our daily read is a proxy of the same object.
- **EMP indices (Girton-Roper 1977; Goldberg-Krogstrup 2018):** true EMP = FX move + reserve
  drain + rate defense; only the FX leg is observable daily ⇒ CBF ships *partial* EMP with
  disclosure.
- **Contagion channels:** common-creditor/banking (dominant, Kaminsky-Reinhart 2000), portfolio
  rebalancing/margin, funding/dollar-shortage (fastest; Rey's global financial cycle), trade
  (slow), wake-up-call (spreads on *similarity*, not linkage). Forbes-Rigobon: crisis
  correlations are biased up — "no contagion, only interdependence" is the null to beat.
- **Idio-vs-systemic case law:** Turkey/Argentina 2018 = idiosyncratic (breadth narrow, DM
  credit quiet → fade); taper 2013 phase-1 = systemic then differentiated by fundamentals;
  CNY 2015 + COVID 2020 = systemic (breadth + DM transmission). The three-filter test (§2)
  operationalizes exactly this.
- **Swap lines:** GFC peak $583B (Dec-2008); COVID $449B (May-2020); Mar-2023 just $590M —
  announcement was the signal, stress was solvency-not-funding. Bahaj-Reis (2022): drawings cap
  CIP deviations (funding ceiling), no effect on CDS/solvency. Stigma ⇒ under-drawing;
  non-zero draw = confirmed stress, zero draw ≠ calm.
- **Desk playbooks per regime** (field guide §4): exceptionalism → underweight EM, watch
  dollar-debt names; goldilocks → broad risk-on, carry works; risk-off → havens, don't chase
  rebounds until vol settles; rotation → overseas/commodity exposure benefits, dollar reversal
  is THE risk. These become the panel stances verbatim (plain words).

## §6 — Waves (each = one PR, branch off fresh origin/main, same-day squash-merge)

- **W0 (this PR)** — masterplan + rulings + field guide (`research/cbf/FIELD_GUIDE.md`).
- **W1 · Regime census (study)** — `scripts/cbf_regime_study.py` (one-shot, off-render,
  hard_exit) classifying full history under §2 frozen rules; outputs
  `research/cbf/REGIME_CENSUS.md`: per-era regime base rates, spell duration distributions,
  transition matrix, DESCRIPTIVE per-regime forward behavior (SPY, RoW, EM FX, USD; 10/20/63d),
  threshold sensitivity, and case-law episode alignment check (does the classifier see 2013,
  2015, 2017, 2020, 2022 the way the literature does?). *Sonnet builds, Opus reviews stats.*
- **W2 · Engine** — `engine/flow_regime.py` + history backfill + build_intl wiring + dag/synapse
  registrations + tests (causality: no future data in any window; fail-open; null-honesty;
  determinism; Monday/T-1 join guard per calendar-day law). New test files added to ci.yml
  whitelist. *Sonnet builds, Opus reviews.*
- **W3 · Surfaces + alert context** — intl.html Cross-border flow panel (doctrine §5 checklist),
  ACv2 backdrop chip, world_state display lobe, bilingual, vm-harness render + browser
  verification with prod-shaped data. *Sonnet builds, Opus reviews design+ZH.*

Acceptance: the intl desk answers, at a glance and in plain words — *Which way is capital
flowing? Is it one country's problem or everyone's? Is the dollar move rates-driven or fear-driven?
Did the Fed's swap lines confirm funding stress?* — with every number carrying its meaning,
every null printed, and nothing wired into any score.

## §7 — Clocks

- 2026-08-15 — CBF review alongside the IRD review: regime-flicker check (hysteresis working?),
  EM OAS depth check for the bloc spread leg, panel copy audit.
- 2026-10-15 — promotion review alongside IRD's: if the forward-accrued regime history shows
  apparent conditional edge, draft an intl_phase0 claim (new declared family; no scan before
  declaration).

### Status log
- 2026-07-13 — Masterplan authored (Fable) from 10-lane census+research fan-out; W1 dispatch next.
