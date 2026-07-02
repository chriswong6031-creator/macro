# R4 — COMPLETENESS CRITIC: what the five designs do NOT cover

**Role:** the net. Cross-checked all 89 audit findings (`/tmp/cycle_audit_result.json`), the 7 Fable theses (T1–T7) + 4 new problems (N1–N4), every page/engine in scope, and the stated user goal against the UNION of D1–D5.

**Method note / caveat:** the designs address findings *thematically*, almost never by finding-id (only 3 IDs appear literally across all five docs). Coverage below is therefore judged by substance-mapping, not citation. Where a design's mechanism plausibly *sweeps up* a finding but never names it, I mark **IMPLICIT** — these are the highest-risk items because no wave's acceptance test guarantees them.

---

## A. FINDINGS NO DESIGN ADDRESSES (true gaps — the net catch)

### FATAL / SERIOUS gaps

**G1 — The China setup-composite era-break is completely unaddressed (china-sector-cycles-1 CRITICAL, china-sector-cycles-6 MEDIUM, china-sector-cycles-3 HIGH, china-sector-cycles-miss LOW).**
The single CRITICAL China finding — "Setup composite silently changes which legs it averages across eras" (a `skipna` mean over a constituent set that grows as series come online, so the composite's *meaning* changes mid-history) — is touched by NO design. D2 backfills and grades `china_sector_cycles.compute()` *as-is*; D5 conditions on it; D1 re-defines the *position oscillator* but not the multi-leg **setup composite** that feeds the evidence gate. Grading a composite whose definition drifts across eras (D2) just produces a rigorously-measured artifact of a broken input. china-sector-cycles-3 (credit + mean-reversion legs dark for most of history; headline Shenwan starts 2014 not 1999) and china-sector-cycles-6 (consumption composite changes constituent count mid-series) are the same disease and equally untouched. **This is the largest single hole: an entire CRITICAL-severity construction defect in the one engine that already has a working grader.**

**G2 — macro-regime engine internals are explicitly PUNTED to a pillar that does not exist (macro-regime-2 HIGH, macro-regime-6 HIGH, predictive-power-6 MEDIUM, macro-regime-miss MEDIUM, macro-regime-5 LOW).**
D5 builds `regime_prior.py` (a merge/freshness/reconciliation service) and fixes the *display* reconciliation (macro-regime-1) and market_state staleness (macro-regime-4). But it explicitly writes "Full vintage fix belongs to the macro-regime pillar" — **there is no macro-regime pillar among D1–D5.** Uncovered:
  - macro-regime-2 / predictive-power-6: `business_cycle` recession calibration is fit AND scored on the same window (in-sample "3/3 caught"); the roadmap Phase-4 demands leave-one-recession-out / walk-forward OOS with ALFRED vintages. No design does this. D5 even *consumes* `business_cycle_snapshot()` in `regime_prior` — importing the leak as a conditioning prior.
  - macro-regime-6: asymmetric/unverified publication-lag handling across daily/weekly/monthly legs. Untouched.
  - macro-regime-miss: live recession signal silently overrides the config threshold with the in-sample-tuned calibration JSON operating point, no fallback validation. Untouched.
  - macro-regime-5: `cl_ratio` rebased to full-history first value = global-normalization look-ahead. Untouched (it is a PIT leak of exactly the class D2/D4 police elsewhere, but in an engine no wave opens).

**G3 — The China pathway HARD CI gate look-ahead is unaddressed (china-sector-cycles-5 MEDIUM, china-sector-cycles-miss LOW).**
"HARD CI gate uses a full-sample look-ahead percentile rank on only 3–4 turns per sector." D5 re-routes the pathway's *conditional-return cells* through `cond_forward` with shrinkage + honest intervals, and D5 §2.2 kills the "bespoke Wilson-on-raw-n path." That addresses china-sector-cycles-2 (overlapping-window CI). But the **evidence GATE itself** — the full-sample percentile-rank threshold that decides whether a leg is "validated," computed with look-ahead over 3–4 turns — is a different mechanism inside `china_sector_pathway`, and no design refits or removes it. china-sector-cycles-miss (the gate "validates the distorted series against itself") compounds G1 + this.

### MINOR gaps

**G4 — `cand_depth` fixed 15-bar swing-high lookback ignores the preset (cycles-core-miss#2 LOW).** Hardcoded even for crypto/FX where the cycle clock is stretched. D1 rebuilds the turn primitive (ZigZag/`find_troughs`) but this is a separate `cand_depth` path in `cycles.py` for swing-high detection; no design mentions it. Bitcoin/DXY flagships (D3 DUAL cards) inherit it.

**G5 — cycles-core-6 "+early nudge" outside calibration (MEDIUM) only half-covered.** D2 moves trend/regime overlay penalties out of the directional sum into a size cap (addresses the overlay-penalty half). But the finding also flags the `+early` nudge that alters the score *outside* the calibrated lattice; D2's binding-calibration wave does not enumerate the early-nudge term, so "no shipped number is the calibrated number" is only partially resolved. **IMPLICIT-at-best.**

**G6 — sector-central-china-6 truncation defense on the CYCLE SPINE (MEDIUM) is only half-covered.** D4-W6 wires THS/akshare-truncation → basket-grade *invalidation* (basket layer). But this finding is about the **central engine inheriting the cycle spine's signature/RS with no staleness/truncation defense** — a truncated scrape silently corrupts the spine's signature, not just baskets. No design adds a staleness/truncation guard on the `china_sector_cycles` spine signature/RS read that `china_sector_central` consumes. **IMPLICIT via D4's audit skeleton at best, not wired.**

---

## B. FINDINGS COVERED ONLY IMPLICITLY (no wave acceptance-test guarantees them)

These are not "uncovered" but no design *names* them, so they can silently fall through a wave's acceptance gate:

- **cycle-flagship-7 (LOW)** dead `turns[].v` / `confidence` fields + ignored TR-proxy note → D3 re-homes `turns[].v` as "curated level" tooltip and owns the proxy registry, but the dead `confidence` field cleanup is not called out.
- **sector-cycles-us-miss#2 (LOW)** `_classify_phase` ignores its own `above200` arg and RS leadership → D1 replaces `_classify_phase` wholesale with the crosswalk, so this *should* die, but D1's NP-5 lists "above200 dead parameter" as a NEW problem it found — good — yet the RS-leadership-contradiction half is not explicitly reconciled in the crosswalk spec.
- **sector-cycles-us-miss (LOW)** early-window osc instability (first ~year under-ranged, min_periods 84 on a 252 window) → D1's `100·Φ(z)` with causal expanding-median vol floor plausibly fixes it, but D1 never states the early-window-warmup acceptance criterion. IMPLICIT.
- **country-cycles-miss#2 (LOW)** asof back-slicing does not re-slice the RS benchmark window (leadership always uses full-panel tail) — a live PIT leak in `country_cycles`. D2/D4 make `country_cycles` PIT for the *backfill*, but this specific RS-benchmark-window re-slice bug in the live builder is not named. IMPLICIT.
- **country-cycles-miss (LOW)** RS rank silently drops markets with <210 rows, no flag → not named anywhere.
- **sector-central-us-1 (MEDIUM)** "confluence is ONE price signal triple-counted (state/trend/RS all from same TR close)" → D2 moves trend-gate to a size cap and D5 adds non-price axes (regime/flows), which *reduces* the triple-count, but no design measures the collinearity the audit's Part V rigor-lens explicitly demanded ("the correlation structure among confluence legs needs to be measured on history before any agreement count is trustworthy"). The **measure-collinearity-first** step is absent. IMPLICIT + a missing prerequisite (see G-user below).
- **china-sector-cycles-7 (MEDIUM)** baskets carry sector-grade badges on TR-adjusted hindsight-curated members → D2/D4 exclude baskets from backfill and freeze levels going forward, and D4 flags the cold-start survivorship hole. The *display* fix — stripping/qualifying the sector-grade badge currently shown on hindsight baskets — is IMPLICIT (D2's MEASURED/FRAME badge layer should catch it, but baskets aren't in the badge taxonomy explicitly).

---

## C. FABLE THESES — engagement audit

All seven theses are ADOPTED (mostly ADOPT+REFINE) across the union; none is left unhandled. But two have coverage seams:

- **T1 (two-tier honesty).** Fully owned by D1 (proxy-registry `tier` field) + D3 (band-level tiers, DUAL cards) + D2 (badge layer). **Seam:** the falsifier-DSL "tripwire" half of T1 lives ONLY in D3 (flagship falsifiers). The *China* structural composites and *country* structural frames have no tripwire DSL — T1's "hand-written falsifiers become machine-evaluated tripwires" is delivered for cycle.html flagships only, not platform-wide. If China/country ever ship a STRUCTURAL frame, they inherit no tripwire mechanism.
- **T7 (interaction only after lead-lag measured).** Owned by D5 (pre-registered phase-0 + STOP rule). Consistent. No gap.
- **N1 (mixed-frequency kernel + proxy registry).** D3 (monthly kernel `record_series` + proxy registry) + D1 (freq params). But **D5 explicitly DEFERS monthly-frequency cycles to hazard-v2** — so the flagship monthly cycles (business, housing) get a *position* and *grading* but NO hazard projection in v1. That is a deliberate, disclosed deferral, not a gap, but it means N1's predictive payoff is partial in wave-1.
- **N2, N3, N4** — all answered redundantly across designs (good).

**No thesis is unengaged.** The designs argue with them (D3 refines T1 to band-level; D4 corrects T5's "raw close" to `auto_adjust=False Close`; D5 refines T3 to two direction-models). This is healthy.

---

## D. PAGES / ENGINES IN SCOPE — coverage census

Audit scope = cycle.html, markets.html, country_cycles.html, sector_cycles(_china), sector_central(_china), + shared engines (cycles.py, business_cycle.py, market_state.py).

| Surface | Covered by | Gap |
|---|---|---|
| cycle.html | D1, D3 (engine-backed), D5 (hazard) | — |
| markets.html | D3 (folded into country_cycles) | — (redirect handled) |
| country_cycles.html | D1, D4 (local-ccy + FX leg), D5 | **live RS-benchmark re-slice PIT bug (country-cycles-miss#2) + <210-row silent drop (country-cycles-miss) untouched** |
| sector_cycles (US) | D1, D2, D4, D5 | — (well covered) |
| sector_cycles (China) | D2 (backfill/grade), D5 (condition) | **setup-composite era-break (G1) — the CRITICAL finding — untouched; NO design opens `china_sector_cycles` composite construction** |
| sector_central (US) | D2, D5 | collinearity-measurement prerequisite absent (G-user) |
| sector_central (China) | D2, D5, D4 | **spine signature/RS truncation defense (G6) not wired** |
| cycles.py (shared core) | D1 (turn primitive), D2 (LADDER_SCORE bind), D3 (`record_series`), D4 (basis) | **cand_depth 15-bar (G4); +early nudge (G5); DC_BAND/IC_BAND periodicity — see below** |
| business_cycle.py | D5 consumes it | **in-sample calibration + ALFRED vintages + publication-lag (G2) — no wave FIXES it, only reads it** |
| market_state.py | D5 (regime_prior, staleness banner, not_a_model_input) | archiving-for-PIT deferred (disclosed) |

**cycles-core-2 (DC_BAND/IC_BAND asserted periodicities never fit to the instrument's actual troughs, HIGH):** No design fits these bands. D1 declares IC-phase a "sub-read" and D5 replaces the *median-half-cycle projection* with a hazard model, but the DC_BAND/IC_BAND_W *band widths* that drive the timing ladder remain asserted cycle-theory constants. **PARTIAL** — the ladder's role is demoted (D1) and its LADDER_SCORE recalibrated (D2), but the underlying periodicity assumption is never validated against measured trough spacing. Given D5's `_detect_swings` per-instrument turn census (XLC 7 … EWZ 112 turns), the data to fit these exists and is computed but not used for the bands. **Escalate to SERIOUS: a HIGH finding with only tangential coverage.**

---

## E. USER GOAL — "improve accuracy and directional capacity across all assets"

The designs advance this substantially (hazard model, calibrated cones, PIT backfill, binding calibration). Two goal-level shortfalls:

- **U1 — "across all assets" has a China-shaped hole.** The one engine with a working grader (China) has its CRITICAL input-construction defect (G1) ungraded-around, and its evidence gate look-ahead (G3) unrefit. The predictive-accuracy upgrade (D5 hazard) *excludes baskets entirely* (pit=False) and defers monthly cycles — so "all assets" in v1 = US/country ETF daily tapes + China sectors-on-a-broken-composite. Directional capacity for baskets and macro-frequency cycles is roadmapped, not delivered.
- **U2 — The collinearity prerequisite the audit's rigor lens made a hard precondition is skipped.** Part V: "the correlation structure among the confluence legs needs to be measured on history *before* any agreement count is trustworthy." No wave measures it before rebuilding fusion (D2-W6 fits fusion weights, D5 adds axes, but neither runs the collinearity study first). If state/trend/RS are near-collinear (audit asserts they are), the fused "confluence" and any hazard feature set built on them carries redundant covariates — degrading, not improving, directional accuracy. This is a sequencing gap that touches the core goal.

---

## F. SEVERITY ROLL-UP OF UNCOVERED / UNDER-COVERED

| Sev in this critique | Items |
|---|---|
| FATAL | G1 (China setup-composite era-break, incl. 1 CRITICAL finding) |
| SERIOUS | G2 (macro-regime internals: 2×HIGH + punted-to-nonexistent-pillar), G3 (China pathway gate look-ahead), cycles-core-2 (DC/IC bands never fit, HIGH), U2 (collinearity prerequisite skipped) |
| MINOR | G4 (cand_depth), G5 (+early nudge), G6 (spine truncation defense), all Section-B implicit LOWs, U1 (China/basket goal hole) |

**Contradiction between designs:** D5 *consumes* `business_cycle_snapshot()` and `regime_history` quads as conditioning priors (its own P-D5-1 flags the revision leak) while the audit (macro-regime-2) says those are in-sample/leaky — and NO design fixes the source. So D5's conditioning layer is built on an input two designs acknowledge is leaky but none repairs. Not a design-vs-design logical contradiction, but a **shared unowned dependency**: every design assumes "the macro-regime pillar" handles it; it is nobody's wave.

---

## G. BOTTOM LINE

Five designs, 40 waves, and the union genuinely covers ~78 of 89 findings well. The net catches **one FATAL hole (G1: the China setup-composite CRITICAL is entirely unowned), four SERIOUS holes (G2 macro-regime engine internals punted to a phantom pillar; G3 China gate look-ahead; cycles-core-2 DC/IC bands never fit; U2 collinearity-first skipped), and ~8 minor/implicit items.** The through-line of the misses: **the designs re-plumbed the position/turn/hazard/basis machinery brilliantly but left the two "input-construction" engines that feed it — the China setup composite and the business_cycle/regime priors — unopened, then built graded, calibrated, hazard-projected superstructure on top of them.** A rigorously-graded artifact of a mis-constructed composite is still wrong; a hazard model conditioned on an in-sample-leaky quad inherits the leak. Recommend a 6th pillar (or explicit wave adds) owning: (1) China setup-composite era-stabilization, (2) business_cycle/regime OOS-recalibration + ALFRED vintages + publication-lag, (3) confluence-collinearity phase-0 study gating fusion, (4) the residual cycles.py constants (cand_depth, +early nudge, DC/IC band fitting).
