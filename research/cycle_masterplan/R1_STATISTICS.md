# R1 — Adversarial Statistical Red-Team of the Cycle-Platform Masterplan

Reviewer lens: **statistical soundness** — hazard overfit, PIT leakage, binding-calibration reflexivity,
shrinkage/pooling errors, whether the reliability machinery can reach significance, and quiet
reintroduction of the audit's sins (overlapping windows, tiny-n point estimates, in-sample fitting).

All claims below verified against `/tmp/macro-cycle-fable-main/` this session unless noted.

---

## HEADLINE FINDINGS (the load-bearing ones)

### F1 — [FATAL] D5 cond_forward `n_eff = n/h` reintroduces the audit's #1 sin (cross-sectional clustering)

**Target:** D5 §2.2 (cell_table / conditional forward-return shrinkage) and §2.4 (sector_central tilt).

The audit's single most-repeated finding is "CIs ~2.4–6× too narrow from overlapping windows." D5's
conditional-cell estimator sets `n_eff = n / h` where `n` counts **instrument-months pooled across ~30
instruments**. `n/h` deflates for the *time* overlap of h-month windows but does **nothing** for the
**cross-sectional correlation** of ~30 country/sector ETFs that share the same regime quad, liquidity
state, and market beta in any given month.

Measured this session (31 US-sector + country ETFs, 14% ZigZag): in **2008-11 alone, 30 instruments
peaked in the same month**; 57 months had ≥5 simultaneous peaks; all 1,670 turns fall in only **273
distinct calendar months** (823 peaks in 207 months). Cross-sectional correlation of same-family ETF
returns is ≈0.6–0.8.

Numerically: a phase×quad×family cell with 300 instrument-months (10 instruments × 30 months, ρ≈0.7,
h=3) has:
- D5 `n_eff = n/h = 100`
- true `n_eff ≈ 14` (cross-sectional effective count 1.37/month × 10 months)
- **CI too narrow by √(100/14) ≈ 2.7×** — squarely back inside the audit's condemned 2.4–6× band.

This is the exact estimator that feeds the `sector_central` conviction tilt (`tilt = clip(12·shrunk_lift/0.10,
±12)` at "n_eff≥30"). The n_eff≥30 gate is trivially cleared by the inflated count, so tilts fire on cells
that are effectively n≈5.

**Fix:** effective-n for pooled cross-sectional cells must dedup BOTH axes: `n_eff ≈ (#distinct months / h)
× k_eff` where `k_eff = k/(1+(k-1)·ρ̂)` and ρ̂ is the estimated within-cell cross-sectional return
correlation. Better: abandon the closed-form n_eff for the cells entirely and take ALL inference from the
date-block bootstrap that resamples whole months (which D2's `block_bootstrap_ci` already does correctly) —
report the block-bootstrap CI as the only interval and delete the analytic `n/h` Wilson path. Add a
same-day cross-sectional dedup to any cell that pools instruments.

---

### F2 — [FATAL] D4↔D5 direct contradiction: D5 fits and ships a hazard model on the exact basis D4 forbids

**Target:** D4 §(inter-pillar contract, ~line 591) vs D5 §1.10 / §7 (T5 verdict).

- **D4** encodes a HARD gate: *"D5 must not backfill any engine's log until that engine's D4 basis-flip +
  re-key has merged (else it backfills worthless wrong-basis grades — the audit's explicit warning)."*
  Enforced by `basis_version_homogeneous`.
- **D5** explicitly does the opposite: *"v0 panel on TR closes with basis:'tr' stamped … Refusing to start
  until the dual-basis collector ships would idle the highest-value work for no honesty gain."* D5-W1→W3
  fit the hazard, gate it, and **ship the cone behind the skill gate** on `zz14tr-v0`.

The turn-detection basis is not cosmetic here: `_detect_swings` runs a 14% ZigZag on the price series, and
TR (dividend-reinvested) vs price closes **re-date turns** — which is the entire premise of D2/N2's
re-keying bomb. So D5's v0 events, leg durations, age features, and KM baseline are all computed on the
basis D4 says produces worthless grades, then shown to users behind a "skill-validated" badge.

D5's defense ("the version key preserves honesty") is a labeling argument, not a validity argument: a
model whose *training labels* (turn dates) are on the wrong basis is not "honest but superseded," it is
**mis-specified**, and a skill-gate PASS on that basis is not evidence the price-basis model will pass.
D4's own §super-warning applies verbatim.

**Fix:** one of two must give. Either (a) D4 relaxes the gate for the hazard *panel* specifically (the
panel is buildable from tapes and is not a graded forward-log stamp — D4's gate is arguably about graded
logs), and D5 explicitly marks v0 hazard cones as `basis:'tr' — NOT the shippable model, dev-only, no
user surface`; or (b) D5-W3 (the wire-to-UI wave) is hard-blocked on D4's per-engine basis flip. The
masterplan MUST pick one; as written the two pillars issue opposite instructions to the same sub-session.
Recommend (b): no hazard cone reaches a user surface until close_price lands. v0 is a dev artifact only.

---

### F3 — [SERIOUS] D5 hazard EPV is overstated ~15×; the *feature* budget, not the raw event count, is the constraint

**Target:** D5 §0 / §1.6 (EPV≈80, ~15 features, "comfortably estimable").

D5 claims 1,883 turns → ~1,200 events/direction-model → EPV≈80 against ~15 features. Two problems:

1. **Raw count is lower than claimed.** My measurement across the 11 US sectors + 22 countries at 14%:
   **1,670 confirmed turns** (420 US + 1,250 country), 835/direction — not 1,200. D5's 1,883 assumed a
   larger country+bloc set; blocs (EFA/EEM) are composites that mechanically co-turn with members and
   should be excluded from the pool (D5 itself excludes them from lead-lag but keeps them in the hazard
   panel — inconsistent).

2. **EPV is the wrong sufficiency statistic here.** Events-per-variable governs *overfit of the
   coefficient vector*, but the binding constraint for the **regime coefficients** (quad_Q2/Q3/Q4,
   liquidity — the features that carry the entire "conditioned on regime" thesis, the reason to prefer
   this over KM) is the number of **independent regime-months**, not events. Those coefficients see
   ≈273 distinct months total, ≈90 months/quad. The quad-coefficient standard errors are governed by
   ~90 effective observations, not 835. So the model can estimate the age/amplitude terms fine (those
   vary within-instrument) but the **regime tilt — the actual upgrade — is thin and will have wide,
   often-insignificant coefficients.** The person-period logistic's naive SEs will understate this
   unless fit with month-clustered / block-bootstrap SEs.

**Fix:** (a) drop blocs from the hazard pool; (b) report quad/liquidity coefficient SEs from a
**month-block bootstrap** (resample whole months, refit), not the Hessian; (c) pre-register that the
regime features must clear their own block-bootstrap CI or be dropped — otherwise the model is age+amplitude
(≈KM) wearing a regime costume. This also tempers D1's claim (§623) that the Φ(z) position was chosen to
be a "cross-asset-comparable hazard covariate": per-instrument vol-standardization equalizes the marginal
distribution but not the conditional turn-hazard, which is exactly why family dummies are still needed —
the covariate is comparable in *scale*, not in *meaning*.

---

### F4 — [SERIOUS] D2's "monthly cadence makes n_eff≈n by construction" is false at the horizons that matter

**Target:** D2 §1.4 + §2.2 (monthly cadence "kills the 2.4–6× inflation at the source").

D2's load-bearing justification for month-end stamping is that H=21 trading-day windows on monthly stamps
don't overlap, so `n_eff≈n`. Verified: true only for **H ≤ 1 month**. But D2 §4.4 and N3 *require* phase
and hazard channels to be graded at **time-to-turn / 3m / 6m** horizons. At those horizons monthly stamps
overlap:
- H=3mo → consecutive monthly windows share 2/3 → n_eff = n/3
- H=6mo → share 5/6 → n_eff = n/6

So for exactly the phase-appropriate horizons the design is built around, monthly cadence does **not** kill
the inflation "at the source"; the deflator D2 wanted to avoid is still required, AND it must also carry
the cross-sectional correction from F1. The "monthly ⇒ n_eff≈n by construction" sentence is only true for
the fast (signal/ladder) 21d channels, and should be scoped to them.

**Fix:** state explicitly that n_eff≈n holds only for H≤21d channels; the phase/hazard/cone channels retain
the full time+cross-section deflator. Do not let the cadence choice be sold as a substitute for the
effective-n machinery for the slow channels.

---

### F5 — [SERIOUS] regime_history quad leak contaminates the backfill's most important features (deeper than D5's P-D5-1)

**Target:** D5 §1.4 P-D5-1 (rated "medium"); affects D2 backfill grades and D5 hazard.

Verified: `data/regime/regime_history.parquet` (1971→2026, 14,478 rows, quad Q1–Q4) is built by
`engine/regime.py` from `growth_score`/`inflation_score` composites of **revised** series (payrolls/indpro
trends). `grep` for `alfred|vintage|realtime` in `engine/regime.py`/`conditions.py` returns **nothing** —
there is no vintage path. So the historical quad label at month t embeds data revised long after t.

D5 rates this "medium" and proposes a "+1-month lag sensitivity check." That undersells it: quad is a
top-tier feature in BOTH the hazard model AND every cond_forward cell AND the regime_prior conditioning
context. A revision leak in the conditioning variable inflates apparent skill of *anything* conditioned on
it, and the walk-forward split does NOT remove it (the leak is within-vintage, not across-time). The
lagged-quad sensitivity check is necessary but the honest v1 posture is stronger: **the regime-conditioned
skill number is an upper bound until an ALFRED-vintage quad exists.** D2's backfill inherits the same leak
in any grade that strats by quad.

**Fix:** (a) label every quad-conditioned OOS skill number `revision-optimistic` in the ledger; (b) make
the lagged-quad refit a GATE not a diagnostic — if lagging quad by 1–2 months materially moves skill, the
quad feature is dropped from the shippable model until vintaged; (c) D2 must stratify its "validated"
gate so a cell whose edge depends on quad cannot emit `validated:true` on leaked labels.

---

### F6 — [SERIOUS] D5 skill gate is likely underpowered → the "core predictive upgrade" mostly ships as the KM prior

**Target:** D5 §1.7 (skill gate) + §0 (T3 as "the core predictive upgrade").

D5's own example ledger shows model Brier 0.148 vs KM 0.159 — an **absolute** gap of 0.011. The paired
date-block-bootstrap CI must exclude 0 per (direction, horizon) = 6 cells. Rough power: with ~90 independent
test date-blocks (2018→ minus embargo) and a plausible paired-diff sd of 0.05–0.08, z≈1.0–2.1 — i.e. the
gate is on the *edge* of detectability for a genuinely-better model, and the 3m/6m compounded horizons have
*fewer* independent blocks (longer windows), so they are weaker still.

This is not a fatal flaw — it is the honest fallback working as designed — but the masterplan headlines T3
as "the core predictive upgrade," and the realistic outcome is that **most (direction,horizon) cells fail
the gate and ship the age-only KM prior**, i.e. repackaged median-half-cycle. Fable should set expectations
accordingly and pre-register that "hazard model shipped" may mean "KM prior shipped in 4 of 6 cells."

**Fix:** (a) state the expected pass-rate honestly in the design; (b) consider pooling direction×horizon
skill into a single family-level test (more power) rather than 6 independent CI-excludes-0 gates that
invite a multiple-comparisons pass by luck; (c) apply FDR across the 6 cells (D5 applies FDR to lead-lag
but not to its own skill gate — asymmetric rigor).

---

## SECONDARY FINDINGS

### F7 — [SERIOUS] D3 MEASURED-proxy fitness gate has no statistical power (n≈2–5 hand turns)

**Target:** D3 §1.5 (match_rate≥0.7 AND median_offset≤6mo for MU/DRAM, CCJ/uranium).

The gate matches hand-researched turns to engine turns. But DRAM ASP and uranium spot hand-turn sets are
n≈2–5 turns (these are secular cycles — that is *why* they are proxies). `match_rate≥0.7` on 3 hand turns
is: 2/3=0.67 FAIL, 3/3=1.0 PASS — a binary coin-flip with no confidence interval. A gate that can only
read {fail, pass} on n=3 is decoration, not validation, and calling the artifact "proxy-validated" (T4
language) overstates it.

**Fix:** report the gate with an explicit Wilson CI on match_rate and require the LOWER bound (not the
point estimate) to clear a threshold; with n=3 the lower bound will essentially never clear 0.7, which is
the honest answer — MU/CCJ proxies should render as `proxy (unvalidated, n too small)`, a labeled overlay,
not MEASURED-proxy with a graded badge.

### F8 — [MINOR] Binding-calibration quarterly-refit in-sample creep (D2 §4)

`LADDER_SCORE` refit is NOT reflexive (verified: ladder STATE is price-only, so recalibrating the numeric
score doesn't change which state a bar is in → grading substrate is stable). Good. BUT `tier_cuts` (§4.2
item 2) are decision boundaries fit to maximize walk-forward separation, then used as LIVE thresholds, and
refit quarterly on an **expanding** window. Each refit re-consumes the window that generated the live calls,
so the "holdout rank-corr>0.5" gate is not a clean OOS test of the boundaries actually deployed — mild
in-sample creep accumulates across refits.

**Fix:** keep a permanently-embargoed final holdout (never folded into any refit) for the `validated` gate,
and grade the LIVE tier_cuts only on data strictly after they were set (a true forward ledger), separate
from the fit-time holdout.

### F9 — [MINOR] D5 cond_forward James-Stein τ² method-of-moments can go negative / unstable with few cells

**Target:** D5 §2.2 shrinkage (`tau2 = max(0, Var_c(m_c) − mean(s2_c/n_eff_c))`).

The `max(0,·)` truncation is standard but when between-cell variance is small (common for forward returns
across quads within a phase, which differ little) τ² collapses to 0 → full shrinkage to the pooled mean →
every cell shows the pooled row. That's a *safe* failure, but it means the "conditional" layer will often
be non-conditional, which the presentation contract should admit rather than implying per-cell signal.
Combined with F1 (inflated n_eff feeding s2_c/n_eff_c too small → τ² too large → *under*-shrinkage), the
two errors push in opposite directions and the net shrink weight is unreliable. Fix F1 first, then the
shrinkage behaves.

### F10 — [MINOR] D2 provisional-projection repaint makes prospective cone-coverage grades non-stationary

**Target:** D2 N-D2-2 + D5 P-D5-4 (both flag it; neither fully resolves).

`_project_next` anchors at `base_x = _yf(last_ts)` = today, and the last ZigZag swing is the running extreme
(provisional). So the *prospective* `proj_central` logged today differs from the same date's stamp tomorrow
if the leg extends — the keep-FIRST rule freezes the first value, but that first value was drawn from an
unconfirmed pivot. Grading cone-coverage against a repainting projection mixes two error sources
(projection error + pivot-confirmation lag). D5-W3 removes the `max(0.05)` floor (good) but the provisional
anchor remains.

**Fix:** log `provisional_last=True` on the stamp (D2 proposes this) AND grade cone-coverage stratified by
provisional/confirmed-at-stamp so the two error sources are separable; do not pool them into one coverage
number.

---

## CONTRADICTIONS BETWEEN DESIGNS

1. **Basis timing (F2):** D4 forbids D5 from building on TR; D5 builds on TR. Opposite instructions to
   sub-sessions. Must be resolved before either ships.
2. **Two incompatible effective-n implementations:** D2 ships `grading_stats.effective_n` (time-overlap,
   Newey-West-style on stamp dates). D5 ships `cond_forward n_eff = n/h` (cruder, and wrong for pooled
   cross-section — F1). Both operate on overlapping-window forward returns. There must be ONE effective-n
   function in `grading_stats.py` and D5 must call it, not a private `n/h`. As written, the shared-library
   thesis (T4) is violated by D5 re-implementing the very statistic D2 extracts.
3. **Bloc handling:** D5 keeps blocs (EFA/EEM) in the hazard pool but excludes them from lead-lag; D3/D2
   country scope doesn't address blocs' mechanical co-turning. Inconsistent treatment of composites.
4. **`turn_def_version` vs `basis_version` vs `zz_version`:** D2 stamps `basis_version` + `zz_version`; D5
   stamps a single `turn_def_version` hash of `{detector,pct,basis,min_bars}`; D1 stamps a
   detector-version. Three overlapping version keys for the same underlying "which turns" question. They
   must be reconciled into one canonical key or the re-key migration (N2) will have three triggers that can
   disagree.

## SECOND-ORDER PROBLEMS THE DESIGNS CREATE

- **Skill-gate multiplicity:** D5 runs 6 hazard skill gates + K lead-lag Stage-B gates + 2 novel-feature
  gates + D2's per-cell FDR + D3's proxy gates. Nowhere is there a *global* multiple-testing budget across
  all these pre-registered gates. With ~20+ CI-excludes-0 tests at 90%, ~2 pass by luck. The masterplan
  needs one experiments-registry-level FDR/family-wise accounting, not per-pillar FDR.
- **Calibration artifacts become a new drift surface:** D2 binds `cycles.py:1038` to read
  `ladder_score.json`; D5 binds `sector_central` tilt to `tilt_config.json`; hazard reads `model.json`.
  Three fitted artifacts now silently govern live behavior. If a quarterly refit ships a bad fit, the site
  changes with no code diff. Needs a diff-and-alert on every refit (the audit's whole complaint was
  hand-tuned constants; fitted-but-unmonitored constants are the same failure mode one level up).
- **Backfill re-runs on every basis/threshold bump** (D2 §1.6) — but the hazard model, cond_forward cells,
  tier_cuts, and lead-lag verdict are ALL keyed to the turn set. One basis flip cascades a full refit of
  every downstream artifact. The masterplan should sequence a single "turn-set epoch" bump that
  re-runs everything atomically, or the artifacts will silently key to different turn versions.

## MISSING (statistical gaps no pillar owns)

- **No cross-sectional correlation estimate anywhere.** Every pooled statistic (hazard regime coeffs,
  cond_forward cells, lead-lag) needs ρ̂ within family/month. No pillar computes it; F1/F3 both depend on it.
- **No power analysis for any gate.** F6 (hazard skill), F7 (proxy fitness), lead-lag Stage B — none state
  the minimum detectable effect at the available effective-n. Pre-registering a gate without a power
  calc invites "we ran it, it failed, inconclusive forever."
- **KM baseline construction is under-specified for cross-sectional pooling.** D5's KM age-hazard pools all
  instruments' age buckets; if EWZ (112 turns) dominates a bucket, the "baseline" is EWZ's hazard, and a
  model that just learns family effects beats it trivially — a spurious skill pass. The KM baseline must be
  family-stratified or the skill gate is gameable.
- **Basket cold-start survivorship (D4 new-problem) bounds what D2 can grade, but no pillar states the
  resulting basket grade coverage** — baskets are excluded from backfill AND from hazard AND their pre-freeze
  history is unhealable, so the basket cycle pages will carry `FRAME · not graded` indefinitely. That's
  honest but should be stated as a permanent limitation, not a temporary accrual.
