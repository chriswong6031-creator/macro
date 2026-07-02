# Cycle Intelligence Masterplan — by Fable

**As of 2026-07-02.** The solution half of the cycle-intelligence program. The problem half is
`research/CYCLE_INTELLIGENCE_PROBLEM_AUDIT_FOR_FABLE.md` (89 verified findings, macro#890). This document
is the arbitrated, red-teamed, dependency-ordered plan to turn the cycle platform into an institutional-grade,
evergreen, *measured* prediction system — and the delegation contract for the wave sub-sessions that will
build it.

> **Provenance.** Produced by a 14-agent design fleet against canonical `main`: 5 feasibility scouts
> (ground-truthed data bases, PIT-reconstructability, calibration state, FX availability, reusable infra),
> 5 pillar designers (D1 ontology, D2 measurement, D3 flagships, D4 substrate, D5 prediction), and a 4-agent
> adversarial red team (statistics, architecture/ops, product honesty, completeness) that attacked the
> combined designs. Every fatal/serious attack is arbitrated below with a ruling. Full pillar designs,
> red-team reports, and scout ground truth are committed under `research/cycle_masterplan/` — wave
> sub-sessions read those, not this summary.

---

## 0 · The doctrine — what "institutional grade" means here

Ten operating principles. Every wave either enforces one of these or it doesn't ship.

1. **The engine owns every plotted number.** Narrative may annotate; it may never set a position, phase,
   turn date, or cone. Enforced by build-time assertion, not convention.
2. **Every claim carries its evidence class.** `MEASURED` (graded, n + CI shown) / `EXPERIMENTAL` (accruing,
   registered in the Experiments tracker with a come-back date) / `FRAME` (structural clock, never graded,
   falsifier-monitored) / `OPINION` (dated, TTL'd, staleness-badged). The UI renders the class; nothing
   ships unclassified. **User-facing vocabulary is exactly two words — MEASURED and FRAME** (red-team
   ruling R3-F1: the intermediate tiers live in a hover "how computed" line, never as competing chips).
3. **A probability is a promise.** Anything expressed as odds or a cone gets reliability-tracked (Brier vs
   base rate, coverage vs nominal). If we won't grade it, we don't express it as a probability.
4. **Calibration binds or it lies.** A calibration artifact that doesn't feed the shipped score is a rigor
   costume. Scores, tier cuts, stance mappings and cone widths are *fit*, versioned, diffed-and-alerted on
   refresh.
5. **"Validated" is a file, not a word.** The label requires a stored verdict artifact (window, n_eff, CI,
   exact claim tested); a grep gate (EN + zh + generated JS) blocks unearned uses.
6. **One ontology, compiled.** Position/phase/turn defined once in Python, *generated* into JS. Two pages
   can disagree only because the world's data disagrees, never about definitions.
7. **Point-in-time or it didn't happen.** Every stamp reconstructable from tape ≤ t. Mutable state
   (membership, narratives, live scrapes) is frozen at stamp time (hash) or excluded from grading.
   **Backtest and live cohorts never blend in one badge** — `BACKTEST n=…` flips to `LIVE n=…` only when
   the prospective cohort matures (R3 ruling).
8. **Small n is a disclosure, not a shame.** Pool cross-sectionally (hazard pooling, shrinkage) to earn n
   where legitimate; where impossible (18-yr cycles), say FRAME and monitor falsifiers instead of
   pretending to grade.
9. **Risk levers are not return levers.** Gates validated only for drawdown reduction size positions; they
   never vote direction.
10. **Evergreen means zero hand-edits to stay true.** Wall-clock TODAY, auto-refreshed reads, TTL'd prose,
    tripwires that alert. A page that needs a human to remain honest will eventually be dishonest.

## 0.5 · The collapse map — 89 findings → 7 systems (+ the input pillar the net caught)

| # | System | Kills which findings | Pillar |
|---|---|---|---|
| S1 | **Ontology contract** — canonical position `100·Φ(z)`, master 5-phase wheel + crosswalk, ONE turn primitive with `confirmed_at`, `resolve_state()` state machine | all position/phase/turn incompatibilities; contradictory cards; 4-detector fragmentation | D1 |
| S2 | **Data-substrate contract** — dual-basis store (`close_price` split-adj/div-unadj + `close_tr`), FX decomposition, basis-matched benchmarks, frozen basket levels | every TR-mislabeled-as-price finding; FX conflation; grader benchmark bias; basket survivorship | D4 |
| S3 | **Measurement engine** — PIT backfill (the `asof=` hook already exists), `grading_stats` shared library, turn P/R + cone coverage + reliability, binding calibration | empty graders; no-CI/tiny-n/overlap findings; decorative + inverted calibration | D2 |
| S4 | **Prediction layer** — pooled discrete-time hazard (two direction models, ~2,400–2,600 confirmed turns verified on disk), shrunken conditional cells, regime-prior service | median-half-cycle projections; magic cones; hand-typed regime blocks; FWER-failing pathway pretense | D5 |
| S5 | **Flagship re-platform** — proxy registry (14 MEASURED / 2 proxy / 1 monthly / 4 FRAME / 4 DUAL), `record_series()` monthly+invert+abs-ZigZag kernel, engine-backed cycle.html, markets.html re-pointed at the country engine | every hand-curated flagship finding; frozen TODAY; drawdown-exponential position; fake convergence bands; duplicate coverage | D3 |
| S6 | **Honesty surface** — falsifier tripwire compiler (18/23 at least partially machine-evaluable), narrative TTL + tolerance assertions, MEASURED/FRAME badges, provenance-of-revision | decorative falsifiers; stale narrative overrides; "Live read" mislabeling | D3/D2 |
| S7 | **Interaction layer** — pre-registered lead-lag phase-0 with a hard STOP rule; sync gauge if it fails | isolated clocks; fake synchronized-inflection bands | D5 |
| S8 | **Input repair** (added by the completeness net) — China setup-composite era-stabilization, business_cycle OOS recalibration + ALFRED vintages, pathway HARD-gate refit, DC/IC bands fit from measured trough spacing | china-sector-cycles-1 (CRITICAL, previously unowned), macro-regime-2/-5/-6, cycles-core-2, country PIT residuals | **D6 (new)** |

Dependency spine: **S2 → S1 → S3 → (S8) → S4 → (S5, S6) → S7.**

Scout ground truth that reshaped the plan (full notes in `research/cycle_masterplan/S*.md`):
`sector_cycles.compute(asof=…)` **already slices PIT-correctly** — the backfill is a loop, not a new engine;
**Shenwan sectors are already price-basis** (China spine needs *no* destructive re-key — the audit
over-scoped); yfinance `auto_adjust=False` returns both `Close` (split-adj, div-unadj — exactly what ZigZag
needs) and `Adj Close` (byte-identical to today's stored close) so the substrate fix is **purely additive**;
1,883 confirmed turns already exist on the 35 US+country ETFs alone (hazard model is estimable); the repo
has zero sklearn/statsmodels — all stats hand-rolled numpy (already house style in the china grader).

---

## 1 · Arbitration record — red-team rulings

The red team raised 4 fatals, ~14 serious. Rulings (full attack text in `research/cycle_masterplan/R*.md`):

| # | Attack (severity) | Ruling |
|---|---|---|
| A1 | **Basis-ordering contradiction** — D4 forbade grading on TR; D2/D5 backfill TR-first (fatal) | **TR-first, dev-only.** The TR-v0 backfill runs immediately but is *research-facing only* (feeds the keystone gate W0.4); no user-facing badge is ever computed on TR. First badge cohort = price basis after W2.2. D4's gate re-scoped from global to **per-epoch** (no mixing within one grade run; archived epochs coexist). |
| A2 | **`n_eff = n/h` ignores cross-sectional correlation** of ~30 co-moving ETFs (fatal) | **Delete the n/h Wilson path.** All cell inference via whole-month block bootstrap; W4.1 estimates ρ̂ (within-month cross-sectional correlation) as a first-class artifact; every cell reports n_months, not n_rows. |
| A3 | **Tier taxonomy metastasized** to 5 tiers + 6 chips (fatal, product) | **Two words: MEASURED / FRAME.** proxy/monthly/dual/prior demoted to hover-line. DUAL = a MEASURED card with a thin secular-context strip. |
| A4 | **China setup composite unowned** — the audit's only China-critical finding had no design (fatal, completeness) | **New pillar D6** (input repair): composite era-stabilization, pathway HARD-gate walk-forward refit, business_cycle LORO+ALFRED recalibration, DC/IC band fitting, country PIT residuals. |
| A5 | **Four incompatible re-key schemes** across D1/D2/D3/D4 (serious) | **D1 owns turn identity.** One `turn_id = series:kind:YYYY-MM`, one half-cycle-scaled tolerance, one file scheme `narratives.<epoch>.json`. The three version keys collapse to **one `turn_epoch` = hash(basis, zz_params, detector_version)** — an epoch bump atomically re-keys narratives, re-runs backfill, re-fits hazard, re-stamps the experiments registry. |
| A6 | **Backfill badge is synthetic self-consistency; turn-P/R is circular** (same detector as ground truth) (serious) | Badges say `BACKTEST n=` until live cohort matures. Turn-P/R gets an **independent turn truth** (realized-extrema definition: argmin/argmax within ±window of ≥X% moves, spec'd in W2.4) so the detector isn't graded against itself. |
| A7 | **Hazard/conditional stack = biggest build, weakest decision-linkage** (serious) | Pre-registration (W0.4 deliverable) names the *decision* each D5 output must move (e.g. hazard cone replaces IQR band only if walk-forward entry-sizing on it improves drawdown-adjusted outcomes). Conditional cells ship as a research surface until they clear it. D5-W8 (novel features) **cut** to research backlog. |
| A8 | **Age-dial = n≈2 false precision** inside the tier built to forbid it (serious) | Dial deleted. FRAME cards show the curated turn timeline + "last major turn {date} ({N}y ago); prior up-legs ran {list}" + tripwire strip. Nothing on a FRAME resolves to a scalar position. |
| A9 | **markets.html burial** — both nav identities are live; folding to a tab buries 9 curated market narratives (serious) | Keep the page + nav identity; **re-point its data** at the country_cycles engine; kill the duplicate engine + posFromDrawdown + convergence bands. D1's adoption ledger targets the re-pointed page. |
| A10 | **Ops fantasy** — "cron is free" vs a serialized 120-min 2-core weekly lane; no wave owned `.github/workflows`; resilient `run_py` makes fail-closed gates fail-open (serious) | New ops wave W1.5: dedicated `cycle-calibration.yml` (own concurrency group), measured wall-times summed against the lane budget, every gate declares **abort-lane vs log-and-skip**, load-bearing gates (validated-grep, epoch homogeneity, stale-tape) run in `ci.yml` as hard steps. |
| A11 | **Runtime `fetch()` assumed; platform is 100% script-tag** (serious) | All new artifacts ship as `window.X = {…}` data-JS via `<script src>`, like every existing page. |
| A12 | **Flag-day axis flip can ship half-applied** across 3 builder scripts (serious) | Flip gated on one committed constant (`ONTOLOGY_AXIS`) read by ALL builders; `gen_ontology_js.py` runs as the FIRST weekly-lane step + a `--check` ci step. |
| A13 | **`cone_coverage` defined twice; `_project_next` edited by two pillars; `grading_stats` triple-owned** (serious) | Ownership table (§3): D2 owns `grading_stats` (one `cone_coverage`, nominal 80%); D1 owns `_project_next` overdue rewrite (fixing lo/hi edges too — the *whole cone* currently re-anchors daily); D5 consumes both. `cycles.analyze(price=)` kwarg owned by D4 with D1 review. |
| A14 | **Regime features under-powered + revision-leaky** (quad has no vintages) (serious) | Blocs dropped from the hazard panel entirely; month-block-bootstrap SEs; each regime feature must clear its own CI or is dropped; lagged-quad robustness refit is a gate; quad-conditioned skill labeled *revision-optimistic* until D6-W3 lands vintage handling. |
| A15 | **Skill-gate power + no program-level multiple-testing budget** (~20 pre-registered gates ⇒ ~2 pass by luck) (serious) | One **pre-registration ledger** (`research/cycle_masterplan/PREREGISTRATION.md`, created in W0.4) lists every gate with success criteria + expected pass rates; BH-FDR applied within gate families; family-stratified KM baseline (anti-gaming). |
| A16 | Monthly-only stamping silences the one *daily*-granularity product (ladder) (minor) | Phase wheel graded monthly; ladder/timing states graded at native daily cadence *with* the overlap deflator built for exactly this. |
| A17 | FIRED-latch strands a recovered thesis; proxy cards show the proxy's position as the cycle's (minor×2) | FIRED shows current-leg state beside the latch; proxy cards show validated turn *timing* only — position gauge suppressed. |
| A18 | i18n: 9 stance tones × zh color-flip undefined for direction-less stances; number-interpolated dual-spans; nav guard for measurement.html (minor) | Ontology declares `tone: bullish|bearish|neutral` per stance (neutral = no flip); FRAME strings avoid number-in-span interpolation; `check_nav_mega`/`check_nav_gap` run in W3.7's acceptance. |

---

## 2 · The pillars (condensed — full designs in `research/cycle_masterplan/D*.md`)

**D1 · Ontology** — `engine/cycle_ontology.py`; canonical position `100·Φ(z)` with z = EMA-detrended log
residual / EWMA vol (causal vol floor), per-frequency params D(252)/W(52)/M(36); refutes both the
range-stochastic (peaks span 17.6–99.7) and drawdown-as-position (conflates cycle with secular regime).
5×8 phase×ladder crosswalk → 9 stances with explicit `divergence` flag ("clocks disagree" is a state, not a
contradiction); Peak×BOTTOM WATCH ⇒ COUNTERTREND ONLY, never a naked buy. ZigZag = THE turn detector,
extended with `confirmed_at`/`confirm_lag_bars` (exists nowhere today — without it every turn grade and
hazard fit leaks); `find_troughs` demoted to declared timing sub-detector. Stable month-quantized
`turn_id` + tolerance migrator defuses the re-key bomb and finally unfreezes the 14% threshold. Generated
JS is data + lookups only — no logic twice.

**D2 · Measurement** — backfill is a loop over the existing `compute(asof=…)`; parallel
`backfill.parquet` + provenance column (live ledger stays append-only keep-FIRST); scope-honest (only the 3
membership-free families backfill; baskets/sector_central overlays excluded as non-PIT per scout S2).
`engine/grading_stats.py` extracted from the china grader (library-not-copy). Three promise-graders: turn
P/R (independent truth per A6), cone coverage (recalibrates half-width from realized error — killing
`lerp(1.5,13)`), reliability/Brier vs per-instrument base rate. Binding calibration on the drawdown-lens
walk-forward; `cycles.py:1038` reads the artifact, static dict becomes fallback. Discovered en route:
**cone edges were never logged anywhere** — prospective cone coverage was unmeasurable until W0.2 adds
`proj_lo/hi` columns.

**D3 · Flagships** — proxy registry census: **14 MEASURED** (mostly by *series substitution* — GC=F, HG=F,
SI=F, DCOILWTICO, BAMLH0A0HYM2, VIXCLS, DGS30, BTC-USD carry no dividend adjustment, sidestepping the TR
problem entirely — a stronger move than dual columns for flagships), 2 MEASURED-proxy behind an earned
turn-match fitness gate (MU→DRAM, CCJ→U₃O₈; Wilson-bounded per A6/R1), 1 MEASURED-monthly (ISM), 4
honestly-FRAME (paywalled or n≈2), 4 DUAL (gold/dollar/japan/bitcoin genuinely carry a gradeable
intermediate cycle *and* an ungradeable secular frame). `record_series(freq, invert, zz_abs)` kernel
wrapper — credit/vol/bonds cycle on inverted series; regression gate = byte-identical rebuild of the three
existing engine pages. Falsifier DSL compiles 10/23 fully + 8 partially; the 5 non-compilable get a
first-class manual state with TTL + overdue digest. Traps caught: `PL` parquet is Planet Labs, not
platinum; FRED's 3-year default window means new monthly series need a one-time deep-history seed.

**D4 · Substrate** — verified: `auto_adjust=False` yields both columns; `Adj Close`→`close` is
basis-preserving so the store change is **purely additive** (no existing number moves; real cost ~8MB, the
designer's 96MB estimate was 12× high per R2). Per-engine atomic flips (read-flip + narratives-v2 +
log-archive in one commit); existing single-date logs discarded and re-stamped (nothing matured = nothing
lost). China spine exempt (already price-basis). Countries: local-currency series (native index where
history permits, else synthetic ETF/FX), FX as a separate graded leg with per-turn `fx_share`; default card
shows the local cycle + a flag when FX drove >60% of a USD turn (full leg in a drawer, per R3). Frozen
daily basket levels + membership hash; truncation ⇒ grade invalidation, never silent re-score.
`scripts/audit_price_basis.py` joins the audit-gate family (AST scan authoritative; `.attrs` demoted to
dev aid per R2).

**D5 · Prediction** — two discrete-time logistic hazards (peak/trough — cycle asymmetry is first-order) on
an instrument-month person-period panel; ~2,400–2,600 confirmed turns verified; family dummies +
own-history-normalized age (k=6 blend) instead of hierarchical Bayes (zero new deps); hand-rolled numpy
logistic + PAV isotonic. **The skill bar is the age-only Kaplan-Meier hazard** (the median-half-cycle prior
formalized), not a coin flip: a (direction,horizon) cell ships model output only if OOS Brier beats KM with
a block-bootstrap CI excluding zero — else the KM prior ships, badged PRIOR. Conditional phase×quad cells
with James-Stein shrinkage (whole-month bootstrap inference per A2). `regime_prior.js` single conditioning
artifact + reconciliation banners; `market_state` is display-prior only (no PIT history — it cannot be a
feature until snapshots accrue, a new problem D5 found). Lead-lag: two-stage pre-registered phase-0
(FDR-screened cross-correlation on ≤2017 train → frozen top-20 pairs → OOS Brier-lift ≥2% pooled with CI
excluding 0) with a **hard STOP to a sync gauge** on failure.

**D6 · Input repair (new, from the completeness net)** — the China setup composite silently averages 2
legs pre-2017 vs 4 post-2019 (the audit's only China CRITICAL): fixed constituent set + availability
masking + composition-version stamp. Pathway HARD gate refit walk-forward (currently a full-sample
look-ahead percentile on 3–4 turns). business_cycle: leave-one-recession-out calibration + ALFRED vintages
+ symmetric publication lags + remove the silent threshold override + `cl_ratio` rebase fix. DC/IC bands
fit from the measured trough-spacing census (replacing cycle-theory numerology). Country live-builder PIT
residuals (RS window re-slice on asof; thin-market flag). China spine truncation guard.

### New problems found while designing (beyond the audit's 89)

The design + red-team pass surfaced **~30 additional problems**. The load-bearing ones:

- **`confirmed_at` exists nowhere** — no consumer records when a turn became knowable; any turn grading or
  hazard fit keyed on pivot dates leaks knowledge backwards (D1; feeds A6).
- **The engine's own projection re-anchors daily** — `_project_next`'s `max(0.05, med−since)` floor makes an
  overdue cycle perpetually "imminent" and unmissable-by-construction; the lo/hi cone edges walk forward too
  (D1/D5, verified by R2).
- **Cone edges never logged** — cone coverage was retroactively unmeasurable (D2).
- **`market_state` has no PIT history** — the site-wide SSOT verdict cannot be a model feature or be graded
  until daily snapshots accrue (D5).
- **Live drift proof** — sector_cycles claims its phase hues are "identical" to cycle_data.js; 3 of 5
  differ today. Hand-mirroring has already failed (D1).
- **Phase wheel has zero hysteresis** — a one-week MACD wobble flips Expansion↔Downturn, resetting
  `phase_age` and polluting the hazard's age covariate (D1; handled in W1.2).
- **Ticker collision trap** — `PL.parquet` is Planet Labs; a naive platinum add plots a satellite company
  as a metals cycle (D3).
- **FRED 3-year truncation** — newly added monthly series are useless for cycle work without a one-time
  deep-history seed (D3).
- **Turn-count heterogeneity** — confirmed turns range 7 (XLC) to 112 (EWZ); per-instrument stats on thin
  names are noise; every per-instrument surface needs a pooled fallback (D5).
- **Backfill re-runs orphan experiment come-back dates** unless the epoch bump auto-re-stamps the registry
  (R2 second-order; fixed in W4.8).
- Basket FRAME-not-graded is **permanent** for the pre-freeze span (no per-member add/remove dates) —
  declared, not hidden (D4/R1).

---

## 3 · Ownership table (the seam contract)

| Object | Owner | Consumers |
|---|---|---|
| `turn_id`, `turn_epoch`, `match_turns` re-keyer | **D1** (W2.1) | D2, D3, D4 import — no local schemes |
| `_project_next` overdue rewrite (incl. lo/hi edges) | **D1** (W1.6) | D5 consumes `overdue`/`overdue_frac` |
| `engine/grading_stats.py` (incl. the ONE `cone_coverage`, nominal 80%) | **D2** (W1.1) | all graders, D5 |
| `cycles.analyze(price=)` kwarg | **D4** (W2.2, D1 reviews) | all engines |
| Proxy registry (`bands:[]` schema — tier attaches to a band, not a cycle) | **D3** (W3.1) | D1 ontology, D5 panel |
| `regime_prior.js` | **D5** (W4.5) | all cycle pages |
| `.github/workflows/*` (lane budget, gate semantics) | **W1.5** | everyone |
| Pre-registration ledger + FDR budget | **W0.4** (created), **W4.2** (enforced) | every gate |

---

## 4 · The program — waves, tiers, acceptance

~34 waves in 6 phases. **The bolded 15 waves are the Minimum Viable Spine** — the subset that captures
~80% of the value (per R3's scope attack); everything else can trail. Each wave = one sub-session, one
branch off main, one PR, squash-merged same day. Wave prompts must link the relevant
`research/cycle_masterplan/D*.md` section — the sub-session implements a spec, it does not re-derive
design.

### Phase 0 — Stop the rot + the keystone question (week 1)

| Wave | Tier | Scope | Acceptance |
|---|---|---|---|
| **W0.1** | sonnet | Wall-clock TODAY on cycle.html/markets.html; explicit elapsed-turn state (dimmed cone + "window passed" chip); staleness banners; delete the `Math.max` push-forward. D3 §7. | Pages render correctly with system date mocked ±1yr; elapsed turns show the chip, never a fresh cone; i18n dual-span. |
| **W0.2** | sonnet | Forward-log writers for US sector_cycles + country_cycles (missing entirely today); add `proj_lo/hi/cone_pct` columns to ALL writers. D2-W2. | Next weekly run stamps all three families incl. cone edges; keep-FIRST invariant tested. |
| **W0.3** | sonnet | Benchmark basis-match in the China graders; flip `sector_cycles.js:1001` so the engine read wins (narrative demoted to labeled overlay). Audit Phase-0 + D4-W2. | Excess computed same-basis (test with synthetic dividend series); narrative renders as dated overlay. |
| **W0.4** | opus | **THE KEYSTONE GATE**: TR-v0 dev-only backfill over the membership-free universes + the minimal "does position/phase predict forward drawdown-adjusted returns" walk-forward study (R3-M4). Creates `PREREGISTRATION.md` with every downstream gate + FDR budget. | A verdict artifact: per-decile forward outcomes with block-bootstrap CIs. **This is the audit's biggest open question answered in one wave** — and it steers W4 scope. |

### Phase 1 — Foundations (parallel tracks)

| Wave | Tier | Scope |
|---|---|---|
| **W1.1** | sonnet | `engine/grading_stats.py` extraction + china-grader refactor to import it (one implementation; one `cone_coverage`). |
| **W1.2** | sonnet | `engine/cycle_ontology.py` + `gen_ontology_js.py` (+ `--check` ci step): position `100·Φ(z)`, crosswalk matrix, 9 stances with zh tone mapping, phase hysteresis, coherence tests. Stance matrix registered as a bindable artifact from day one (A17/R3). |
| **W1.3** | sonnet | Dual-basis store: collector flag, `close_price` column, `yahoo_closes(basis=)`, full-history backfill; **hard gate**: byte-safety (`close≡AdjClose`) verified on ≥1 non-US ETF + 1 index before any flip. |
| W1.4 | haiku | Collection gaps: FX pairs, local indices, FRED deep-history seeds (CSUSHPISA, HOUST, DCOILWTICO, DHHNGSP…), futures proxies (`PL=F`/`PA=F` pinned — never `PL`). |
| **W1.5** | sonnet | Ops: `cycle-calibration.yml` (own concurrency group), measured wall-times vs the 120-min lane, every gate declared abort-lane vs log-and-skip, hard gates into `ci.yml`. |
| **W1.6** | sonnet | Kernel integration: `resolve_state()` live in `_record_core` (data-only, UI unchanged); `_project_next` overdue rewrite (D1 owns; lo/hi edges included). |

### Phase 2 — Migration + measurement

| Wave | Tier | Scope |
|---|---|---|
| **W2.1** | opus | The `turn_epoch` primitive + the ONE re-key migrator (`match_turns`, `narratives.<epoch>.json`, orphan quarantine — curated turns never deleted). |
| **W2.2** | sonnet | Per-engine atomic basis flips (US sectors, countries; China spine exempt) + log archive + `audit_price_basis.py`. |
| **W2.3** | sonnet | Price-basis PIT backfill → `backfill.parquet` + provenance + `engine_fingerprint`; monthly cadence for the phase wheel, daily for the ladder (with overlap deflator, A16). |
| **W2.4** | opus | The three promise-graders: turn P/R with **independent realized-extrema truth** (A6), cone coverage → cone recalibration, reliability/Brier. `BACKTEST n=` vs `LIVE n=` badge discipline. |
| W2.5 | sonnet | Collinearity phase-0: correlation/VIF of state/trend/RS/hazard features on backfilled history — **gates W4.2 and W4.6** (R4's hard precondition). |
| **W2.6** | opus | D6: China setup-composite era-stabilization + pathway HARD-gate walk-forward refit. |
| W2.7 | opus | D6: business_cycle LORO recalibration + ALFRED vintages + publication-lag symmetry + threshold-override + `cl_ratio` fixes. |
| W2.8 | sonnet | D6: DC/IC bands fit from trough-spacing census; `cand_depth` preset parametrization; country RS PIT re-slice + thin-market flag; China spine truncation guard. |

### Phase 3 — Product surfaces

| Wave | Tier | Scope |
|---|---|---|
| **W3.1** | opus | Proxy registry (`bands:[]`) + `record_series()` kernel (monthly, invert, abs-ZigZag); byte-identical regression gate on the three existing engine pages. |
| **W3.2** | sonnet | Engine-backed cycle.html: MEASURED/FRAME two-word taxonomy, DUAL = measured card + secular strip, FRAME = curated timeline + leg-length list (no dial), hover "how computed". |
| **W3.3** | sonnet | Falsifier tripwire compiler + alert wiring + FIRED UX (latched + current-leg state) + manual-falsifier TTL for the 5 NONE cycles. |
| W3.4 | sonnet | Narrative overlay hardening: TTL, tolerance assertion, archetype mechanism-checks, provenance-of-revision changelog (R3-M1/M2). |
| W3.5 | sonnet | markets.html re-pointed at the country engine (page + nav identity kept; duplicate engine, posFromDrawdown, convergence bands deleted). |
| W3.6 | sonnet | Ontology page adoption + divergence UX + **cross-page consistency assertion** (same instrument agrees across pages within tolerance or shows a declared basis label — R3-M3). |
| **W3.7** | sonnet | `site/measurement.html` hub (script-tag data) + per-card badges; nav guards (`check_nav_mega`/`check_nav_gap`) in acceptance. |
| W3.8 | sonnet | Frozen basket levels + membership hash + truncation invalidation. |
| W3.9 | sonnet | FX decomposition UX: local-currency country cycles, `fx_share` flag >60%, full FX leg in drawer. |

### Phase 4 — Prediction + binding

| Wave | Tier | Scope |
|---|---|---|
| W4.1 | sonnet | Hazard panel + family-stratified KM baselines + ρ̂ estimation; blocs dropped. |
| W4.2 | opus | Hazard fit: month-block bootstrap SEs, isotonic calibration, per-cell skill gates vs KM with BH-FDR, decision-linkage gates from PREREGISTRATION.md; regime features clear own CI or drop; lagged-quad robustness. |
| W4.3 | sonnet | Wire hazard into records/cones (PRIOR fallback badged; overdue consumed from D1) + i18n. |
| W4.4 | sonnet | Conditional phase×quad cells (whole-month bootstrap only; James-Stein shrinkage) — ships as research surface until its decision gate passes (A7). |
| W4.5 | sonnet | `regime_prior.js` service + reconciliation banners (display-prior until D6-W3 vintages); begin persisting daily `market_state` snapshots so it can *become* a feature. |
| **W4.6** | opus | Binding calibration: LADDER_SCORE / tier cuts / stance matrix fit from the walk-forward (drawdown lens); artifact diff-and-alert; validated-grep gate (EN+zh+generated JS). |
| W4.7 | opus | Position-v2 acceptance study + `ONTOLOGY_AXIS` committed-constant flip across all builders. |
| W4.8 | haiku | Experiments-registry registration for every accruing measurement; epoch bumps auto-re-stamp come-back dates. |

### Phase 5 — Interaction (gated)

| Wave | Tier | Scope |
|---|---|---|
| W5.1 | opus | Lead-lag phase-0 exactly as pre-registered (two-commit discipline: criteria commit, then results). |
| W5.2 | sonnet | Conditional on W5.1: interaction feature into hazard, OR the measured sync gauge + STOP. |

---

## 5 · Delegation playbook

- **One wave = one sub-session** (Opus for judgment-heavy waves, Sonnet for well-specified implementation,
  Haiku for collection), one branch off canonical `main` (never the stale local branch — verify with
  `git fetch origin main` first), one PR, squash-merged same day.
- **The wave prompt contains:** the wave row above, the linked design-doc section(s) under
  `research/cycle_masterplan/`, the ownership-table rows it touches, and its executable acceptance gate.
  Sub-sessions implement; they do not re-litigate arbitrated rulings.
- **Every gate is executable** (pytest target / audit script / artifact diff). A wave without a runnable
  gate doesn't ship. Gates declare abort-lane vs log-and-skip semantics (A10).
- **Measurement waves register in the admin Experiments tracker** with come-back dates; epoch bumps
  re-stamp them (W4.8).
- **UI waves obey the house gotchas:** dual-span l-en/l-zh (never `t()` in attributes), zh up/down color
  flip driven by declared stance `tone`, mobile-fit at 375px, `preview_screenshot` scroll-0 only,
  nav-guard scripts on any nav change.
- **Status log** lives at the bottom of this file — every merged wave appends one line (PR#, date, gate
  result), same convention as the engine/mastermind masterplans.

## 6 · Risks & standing tensions (told straight)

1. **The keystone gate may return "no edge."** If W0.4 finds position/phase deciles carry no forward
   drawdown-adjusted signal, phases 3–5 shrink drastically and the honest product is tripwires + regime
   context + measurement — the doctrine survives even if the prediction thesis doesn't. This is a feature
   of the plan, not a failure mode. **→ FIRED 2026-07-02: see §6.5.**
2. **Most hazard cells will likely ship PRIOR initially** (R1's power analysis: absolute Brier gaps ~0.011
   at ~90 effective blocks). The plan says so up front; the KM prior is itself a large upgrade over the
   re-anchoring median projection.
3. **China/baskets/monthly cycles trail in v1** — "all assets" is delivered for US/country daily tapes
   first; the ledger declares what's excluded and why rather than papering over it (R4's "shrinking scope"
   attack, accepted and disclosed).
4. **New surfaces can rot like the old ones** — every new surface ships with its own staleness tripwire
   (SO1); provenance-of-revision (computed_on + epoch) is mandatory on every badge (SO2).
5. **Reflexivity** — once calibration binds, refits change live behavior with no code diff; the
   diff-and-alert + permanently-embargoed holdout (R1) is the containment.

---

## 6.5 · Post-keystone re-steer (2026-07-02 — BINDING on all downstream waves)

W0.4 ran on 8,344 leak-free PIT stamps (11 US sectors + 24 countries, month-end 2005–2026, spanning
2008/2020/2022). Full verdict: `research/cycle_masterplan/W04_KEYSTONE_VERDICT.md`. Findings:

- **Position → forward RETURN: NO-EDGE.** Every decile's gap-vs-base CI straddles 0 at 21/63/126d.
- **The only reproducible signal is RISK-ONLY and phase-keyed — with an inverted sign:** Peak phases →
  *shallower* forward drawdowns (63d p10-DD gap CI [+1.2%, +5.0%]), Trough → *deeper* ([−10.0%, −1.9%]).
  This is a vol-clustering fact (troughs live in high-vol regimes), not a timing signal — and it decays
  post-2018. Per doctrine #9 it may inform *risk sizing only*, never direction.
- **The audit's LADDER-inversion headline did NOT survive PIT + month-block bootstrap** — inconclusive on
  all 9 era×horizon cells. The true finding stands as the audit's other observation: *no ladder state
  separates from its base rate.* Treat the china `ladder_calibration.json` ordering as a point-estimate
  artifact.

**Scope consequences (binding):**
1. **W4.1–W4.4 (hazard + conditional cells) are demoted to a decision-gated research track** (DL-1/DL-2
   in `PREREGISTRATION.md`) — not a v1 sizing/cone engine. They may still ship as MEASURED research
   surfaces if their pre-registered gates pass; nothing they produce touches a card until then.
2. **W4.6 binding calibration is re-scoped to the risk channel** — there is no return-channel ordering to
   bind. The `mean_fwd/|dd_p10|` metric is denominator-dominated (ranks states by ambient vol);
   vol-residualize or fit risk/return channels separately. Expect pre-registered gate BC-1 to FAIL — that
   is the correct outcome; wave prompts must not assume it passes.
3. **W1.2's phase-hysteresis fix must land before W2.4** grades any phase-conditioned promise, or the
   graders inherit the phase-wobble noise the keystone study had to average through.
4. **Phases 0–3 are unchanged and now carry the product:** ontology coherence, honest measurement,
   engine-backed flagships, tripwires, MEASURED/FRAME, regime context. The platform's value proposition
   is *disciplined honesty + risk context*, with prediction claims earned cell-by-cell through the ledger
   — exactly what §6.1 pre-committed to.

---

## Status log

- 2026-07-02 — Masterplan authored (14-agent design fleet + 4-agent red team; arbitration §1). Supporting
  docs committed under `research/cycle_masterplan/`.
- 2026-07-02 — **W0.2+W0.3 SHIPPED** (#913): `engine/cycle_forward_log.py`; US sector + country forward
  logs stamp for the first time (56+31 rows day-one) incl. `proj_lo/hi` cone edges; China grader
  basis-declared excess (`benchmark_close_price()`; NB: for the 000001.SS *index* TR≡price — the basis bug
  is real for ETF benchmarks only); engine-owned "read" primary, narrative demoted to dated Analyst note.
  36/36 tests.
- 2026-07-02 — **W0.1 SHIPPED** (#914): wall-clock TODAY on both flagships; `Math.max` push-forward
  deleted; elapsed turns render "window passed" chip + dimmed cone; staleness banners (amber 14d/red 60d);
  "Live read" → "Curated read".
- 2026-07-02 — **W0.4 SHIPPED** (#929): keystone gate run — verdict + re-steer in §6.5;
  `PREREGISTRATION.md` frozen (28 downstream gates with E[pass|null] + BH-FDR families);
  `data/research/keystone_tr0/` (basis:tr, epoch:tr_v0, research-only per ruling A1).
- 2026-07-02 — **W0.4 (keystone gate) SHIPPED.** TR-v0 PIT backfill (8,344 month-end stamps, 11 US sectors +
  24 country ETFs, 2005–2026) + walk-forward position/phase predictive-power study; PIT invariance verified.
  **VERDICT: position deciles = NO-EDGE (return channel); phase = risk-only, regime-fragile drawdown signal
  whose sign INVERTS the intuitive mapping (Peak→shallower DD, Trough→deeper); the LADDER inversion is NOT
  confirmed (INCONCLUSIVE on all 9 era×horizon cells).** Program steer (§6.1 branch): REFINE toward
  risk-lens + measurement + regime context; carry the hazard/conditional stack as a decision-gated research
  surface (DL-1/DL-2), NOT a v1 position-return sizing engine. Deliverables:
  `scripts/keystone_position_gate_phase0.py`, `research/cycle_masterplan/W04_KEYSTONE_VERDICT.md`,
  `research/cycle_masterplan/PREREGISTRATION.md` (all downstream gates + BH-FDR budget, frozen),
  `data/research/keystone_tr0/` (backfill + study tables). Runtime ~15–17 min.
