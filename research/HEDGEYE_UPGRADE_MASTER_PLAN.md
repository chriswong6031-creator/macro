# Hedgeye-Informed Master Upgrade Plan — Mastermind-X Signal Suite

*Prepared 2026-06-30. Source inputs: the "Hedgeye, Decoded — And How To Beat It" teardown dossier (`~/Downloads/hedgeye_decoded_and_beaten.md`) + an exhaustive parallel recon of all 16 signal subsystems in this repo, six architect-authored engine specs (Sections A–F below), and two independent adversarial critiques that verified the actual data/dependency substrate. This document is the single source of truth for the program tracked in memory as `hedgeye-informed-suite-overhaul`.*

> **How to read this.** §0–§4 are the synthesis and the decisions. **§2 (Verified Substrate Corrections) overrides the section specs wherever they conflict** — the architects wrote Sections A–F from the recon, then the critics went and checked the environment and found several load-bearing assumptions are false here. Sections A–F (the full engine specs) and the Adversarial Critique follow in full; the per-subsystem recon is appendixed.

---

## 0. Executive summary

**The trigger.** Our Current Macro Regime scorecard reads **Q1 Goldilocks** (growth `+0.20`, confidence `0.125` — a coin flip — while our own WEI is *falling*); Hedgeye reads **Quad 4**. Both can be "right" because they measure different objects. Our `engine/regime.py` classifier is a **coincident, first-derivative, market-proxy consensus** — 6 full-weight equity/commodity ratios + 4 half-weight econ signs, each scored by the sign of a 20-day slope, argmax'd into a 2×2 box. Hedgeye's Quad is a **forward, second-derivative, economic base-effects forecast** of where growth/inflation are *headed*. The disagreement is entirely the growth axis, which we round a `+0.2` coin-flip up to "growth up."

**The systemic finding.** The recon proved this is not a regime-engine problem — it is the **whole suite's methodology**. The same rigor flags recur across all 16 subsystems: `first-derivative-not-second`, `market-proxy-not-econ-nowcast`, `revised-not-point-in-time`, `discrete-argmax`, `point-not-distribution`, `unvalidated-no-DSR-PBO`. Read against our own honest page labels — *"no directional odds forecast," "momentum rank-IC≈0," "the trend gate is drawdown-only, not return alpha"* — the plain conclusion is: **we built the observatory and the risk overlay, but we have no engine that carries return alpha.** That is the entire gap, and it is precise.

**The strategy** (from the dossier, adopted): steal Hedgeye's three real edges — (1) base-effect determinism, (2) USD/cross-asset lead-lag with correlation-break as a transition warning, (3) regime-conditional expected value weighted by intensity — and build the *institutional* version of each: point-in-time honest, distribution-valued, and validated with the López de Prado spine (`engine/validation.py`, already present). Discard the win-rate theater and the single-name product (independently audited at 36% positive / 32% beat SPY — not where the value is).

**The spine (this ordering is forced by dependencies):**
`PIT vintages → base_effect forward projection → axis refactor + re-classify history → regime_hmm P(Quad)+transition matrix → regime_ev conditional-EV ("Hubble" ranker) → drawdown-budgeted portfolio dial.` If we build only one chain this year, it's this one. Everything else hangs off it or runs parallel (the vol/flow track).

**The non-negotiable discipline:** the repo already has a *validate-before-weight* doctrine (`gate.json`, `signal_gate.py`, `trial_ledger.jsonl`). Honor it. Nothing new — a weight, a size, a gross dial — touches a money path until its own validation artifact exists and passes. New engines ship **display-only** first; scored promotion is gated on **matured forward data (calendar months), not engineering time.**

---

## 1. The diagnosis in detail

**The specific case (Goldilocks vs Quad 4).** Both frameworks agree inflation is decelerating (our `inflation_score −0.52`; Hedgeye Q4 = inflation slowing). The entire divergence is growth: our `+0.20` is carried by *beta/liquidity/breadth momentum* (copper/gold, IWM/SPY, breadth) plus *lagging level econ* (payrolls level still rising, IP still above year-ago), while the cleaner *leading* growth-preference signals (XLY/XLP, cyclical/defensive) and the timely *WEI nowcast* all point **down** — a textbook Quad-1-rolling-into-Quad-4 signature that a base-effect second-derivative read catches and our first-derivative market-proxy read misses.

**The systemic pattern (recon rigor-flag tally, 16 subsystems):** `revised-not-point-in-time` and `market-proxy-not-econ-nowcast` appear in **~14/16**; `first-derivative-not-second` and `point-not-distribution` in **~12/16**; `discrete-argmax` and `unvalidated-no-DSR-PBO` in **~10/16**. This is one methodology applied everywhere, so one methodological upgrade — done centrally and consumed by every desk — lifts the whole suite. (Full per-subsystem detail in the recon appendix.)

**Three live correctness/honesty defects the recon surfaced (fix regardless of the big build):**
- **Factors page** shows a *negative-IC* composite (`mean_ic −0.007`) and 7 FDR-failing factors beside the one survivor (`payout`, itself on a *survivorship-biased* panel) with **no visual distinction** — the single most dangerous live misread on the site.
- **GEX gate violation:** `stock_score.py:563` uses GEX at weight `0.10` + a `±0.3` tilt **before `validate_gex.py` passed** — the repo breaking its own validate-before-weight doctrine on a path that touches stock conviction.
- **Cycle-page cone** uses a hardcoded `lerp(1.5,13)` with zero coverage backing — indefensible false precision on a forward projection.

---

## 2. Verified Substrate Corrections — READ FIRST (these override Sections A–F)

Two independent critics stopped reading the plan and *checked the environment*. These are verified facts that reorder the roadmap. **Every one of these was assumed away by at least one section spec.**

| # | Verified fact | Consequence | Override |
|---|---|---|---|
| **S1** | **`data/yahoo/SPY.parquet` has only `close, volume`** — no OHLC. Only `_VIX` has high/low. | Yang-Zhang realized vol (the v2 vol-complex centerpiece) is **impossible** without first backfilling full OHLCV for SPY + every sector ETF + basket member. | OHLCV backfill is its own scoped prerequisite (S/M) in v-1/v0, **or** Yang-Zhang is cut. Section C's "verify OHLC" hedge becomes a hard gate. |
| **S2** | **`hmmlearn`, `statsmodels`, `arch`, `cvxpy` are all `ModuleNotFoundError`.** | The entire v1 spine (HMM), the DFM, GARCH cones, and the v3 optimizer import packages **absent from this env**. Adding them (they pull scipy/BLAS) to a **67-min CPU-bound daily render** is an operational change, not a `pip install`. | Add a v-1 line item: pin the stats stack in `requirements.txt` **and verify the VPS/CI render env has wheels**. See S5 for the compute split. |
| **S3** | **ALFRED vintage store is shallow / incomplete.** WEI PIT starts **2020** (one NBER turn), GDPNow 2016, Sahm 2019, sticky-CPI 2014. **`CPIAUCSL`, `PCEPILFE`, `CPILFESL` are NOT in the vintage store at all** — yet the base-effect spec reads exactly those. | Base-effect on **core PCE — the Fed's target** — has **no point-in-time path today**. Any PIT-validated recession/nowcast backtest is a ≤6-year, ≤2-episode exercise. Sections A and F even disagree on *which* series to vintage. | **The true first task is `scripts/audit_alfred_depth.py`** (read-only API audit). It could invalidate v0 before a day is spent. Series without deep vintages fall back to latest-revision with an explicit `revised=True` flag (defensible for a *deterministic base* — the base period is a settled print — but must be labeled). |
| **S4** | **The roadmap's "silent blocker" F.v1-PRE is a phantom** — `regime_history.parquet` **already** carries `growth_score`/`inflation_score`/confidences for all 14,476 rows back to 1971. | A whole "verify axis-history persistence first" step is a no-op. | Delete F.v1-PRE; go straight to the HMM once L1 is honest. |
| **S5** | **No section budgets compute against the 67-min render.** HMM refit + DFM Kalman + per-asset GARCH + EV bootstraps (B=500–5000) + cvxpy LP, per build. | Naive daily fitting adds plausibly +10–20 min to a render already at CPU saturation. Section C got it right (`har_weights.json` cached); no other section did. | **Mandatory rule:** all fits (HMM transition matrix, HAR βs, DFM state params, EV `μ_{a,k}` tables) run in a **nightly calibration job** writing JSON once (like existing `*_calibration.json`); the render only does the cheap filter/lookup. Section F's dependency table needs a compute column. |
| **S6** | **No engine-level degraded-mode contract for the data-health circuit breaker** (`scripts/collect.py`, `engine/drift.py`, `healthcheck.py`, `run_status.json`). | `hmmlearn` EM non-convergence, empty ALFRED vintage, or an `arch` throw currently has undefined behavior — a convergence failure could take down `macro.html`. And per the `jinja-missing-key` gotcha, every new optional field (`latest.regime_probs`, EV CIs) must use `{% if d.key is defined and d.key is not none %}` or the render dies. | **P0 architecture task:** every new engine returns a typed *degraded* result; every new template field is guarded. This is the difference between "additive leaf" and "broke the macro build." |
| **S7** | **Cross-repo consumer gap.** The Mastermind trading bot's buy-gate (`brain/research_paper.py`) lives in a **separate repo**; the dashboard-side brain is context-only. | Shipping `regime_probs`/`quad_fwd`/`intensity` to `latest.json` is a **cross-repo contract change**. If the bot doesn't read them, "regime-conditional sizing" never reaches a live order — the exact "engine produces a number the consumer ignores" failure the recon flagged for GEX, at system scale. **This is the most important "does it touch real money" question and no section answers it.** | Decide explicitly in v-1: does the live book consume the dashboard's EV/P(Quad), and via what artifact? |
| **S8** | **The small-sample wall is real and shrinkage hides it.** Effective-N for regime-conditional means is **~episodes (~7 recessions / handful of Q4s since 1998), not ~days** — daily rows within one 2008 are not independent draws. Section A's James-Stein shrinkage (τ≈30) with 15–40 obs pulls `μ_{a,k}` **halfway back to the unconditional mean** = halfway back to "no regime effect." | The honest conclusion may be **"we cannot distinguish Q4 sector EV from noise."** The plan must be willing to reach it. Basket/subsector EV is *additionally* survivorship-biased (`consolidated_candle(pit=False)` = today's roster → overstates μ in exactly the Q4 stress cells where dead names cluster). | **Publish the effective-episode-count next to every conditional mean**, show NW/Wilson CIs, suppress ranking contribution when thin, never size off a thin cell. Only clean-ETF (11 SPDR) EV is scoring-eligible; basket EV is display-only with a permanent survivorship banner. |
| **S9** | **Validation gates are calendar-gated, not engineering-gated.** Base-effect inversion, EV rank-IC, cone coverage, corr-break lift all need **matured 63/126-day forward observations** — months to years of accrual. | The v0→v3 sequence *implies* gates pass in a build cycle. They can't. The risk is shortcutting the gate with in-sample "validation" — the exact overfitting the spine exists to prevent. | State explicitly: engines ship **display-only in vN**, become **scoring-eligible in vN+K months**. Decouple the *ship* from the *promotion*. |
| **S10** | **Statistical over-reach to gate before build:** the "68%/80%/70%" base-effect stats are **unverified Hedgeye marketing** (2nd-diff of a YoY series is differenced ~4×; sign near zero is coin-flip). HMM centroid-sort label-switching corrupts the transition matrix when growth/inflation states overlap (the *current* live state). Cone Christoffersen tests are anti-conservative on overlapping windows. Yang-Zhang on dividend-*adjusted* OHLC injects a spurious quarterly ex-div vol spike. DSR `n_trials` is understated system-wide. USD corr-break must beat the **absorption ratio we already compute**, not just a permutation null. | Each is a way a plausible-looking signal ships wrong. | Stratify inversion accuracy by `|d2|` tercile + test stable-vs-breaking momentum separately; use Hungarian assignment for HMM labels + a label-instability test; use non-overlapping forecast origins for coverage; verify what `collectors/yahoo.py` stores before asserting YZ; mandate every `validate_*` logs its full grid and deflate against the **system-wide** trial count; gate corr-break on **incrementality over the absorption ratio**. |

---

## 3. The corrected build sequence

Cuts applied up front (both critics, independently): **DFM → research-spike only** (XL, can't be validated on ≤2 episodes of WEI PIT, and the HMM works fine on axis scores without it); **Black-Litterman → deferred** until EV views clear a DSR gate (until then BL is "an expensive equal-weighter"); **net-short → cut from the gross/net dial for v1–v3** (account-ending on a diffuse `conf=0.125` read; long-only gross dial gets ~90% of the risk benefit at ~10% of the blow-up risk); **USD corr-break → display-only** until it beats the absorption ratio (no triple-wiring into HMM+dial+MRS).

- **v-1 — Substrate audit & safety (days, all P0, zero modeling).** `audit_alfred_depth.py`; pin+verify the stats stack (S2); define the engine degraded-mode contract + jinja guards (S6); write the nightly-calibration/cheap-render compute-split rule (S5); make the cross-repo schema decision (S7); confirm what OHLC `collectors/yahoo.py` stores (S1). **This gates v0** — if core-PCE vintages are absent/shallow, v0's base-effect set shrinks and we learn it now.
- **v0 — Base-effect core + honesty UI (~2–3 wk).** ALFRED PIT wired into `build_features()` (with static `LEG_LAGS` fallback) + **re-run the legacy quad on PIT to measure how much current backtest performance was look-ahead**; `engine/base_effect.py` deterministic forward projection (display-only, `weight=0`, forward-grading log from day one); the **MEASURED / MODELED / NO-EDGE badge system** and the forward-quarter base-effect strip on `macro.html` — with the *deterministic base level path* (honest arithmetic) visually separated from the *2nd-derivative directional claim* (unvalidated, badged `MODELED`).
- **v1 — Probabilistic regime + conditional-EV (display-then-scored).** Axis refactor first (remove `us2y` from growth, add explicit liquidity/policy axes) **and re-classify history**, *then* `regime_hmm.py` (P(Quad)+transition matrix+hazard, Hungarian label assignment, nightly-calibrated) → `regime_ev.py` conditional-EV ranker with effective-episode-counts and thin-cell suppression. Wire as **display columns** beside the existing conviction score in Sector Central and baskets; the *scored blend* waits for `validate_regime_fwd.py` to pass on matured data.
- **v2 — Vol complex + mechanical flow + corr-break (parallel track, price/CBOE data, no FRED/HMM dependency).** OHLCV backfill → Yang-Zhang + fitted HAR-RV → re-run the closed `vol_regime` gate (human-reviewed); persist the IV surface **now** (unbackfillable); `mechanical_flow.py` (vol-control roll-off, CTA flip, dealer gamma-flip) + `collectors/cot.py` E-mini COT + persist `rr_25d`; `usd_correlation_break.py` display-only.
- **v3 — LdP spine live + portfolio construction + intl.** `monitor_signal_ic.py` daily drift alerts; switch factors to the de-biased scorecard; DSR/PBO on every scored strategy broken out by regime + VIX bucket; `portfolio_construction.py` = **HRP + vol-target + CVaR + a P(Q4) long-only gross dial** (BL deferred), with a **single gross-reconciliation owner** so the three de-risk levers can't multiplicatively flatten the book when they all fire together (i.e. in a crash — S per critic 3.5); then port the central engines to China (deepest history) → HK/Canada.

---

## 4. The lowest-regret first moves (do these regardless of how far the program goes)

All are correctness/honesty fixes or orthogonal new alpha; **none depend on the missing packages or deep vintages.**

1. **`scripts/audit_alfred_depth.py`** — the true P0. Read-only API audit of vintage depth/first-date/revision-magnitude for every base-effect & DFM series. Could invalidate v0 before a day is spent (S3).
2. **Factors page: composite-split + mandatory `validation_chip`** — reads only existing `ic_scorecard.json`. Stops the worst live misread (a negative-IC composite shown as if it were signal). Highest honesty-per-hour on the site.
3. **Fix the GEX validate-before-weight violation** — a real correctness bug on a live money path (`stock_score.py:563`). Pass `validate_gex.py` or demote to display. No third option.
4. **`engine/vol_surface.py` Yang-Zhang + persist the IV surface** — orthogonal to the entire regime spine; **every day the IV surface isn't persisted is a permanently lost day of skew/dispersion history.** Improves the physical VRP leg regardless of whether the regime revamp succeeds. (Gated on confirming/backfilling OHLC per S1.)
5. **`engine/mechanical_flow.py` vol-control roll-off + E-mini COT** — the genuinely *new* orthogonal alpha the suite lacks; PIT-clean by construction, free CFTC/CBOE data, zero dependency on the regime stack.
6. **Wire ALFRED PIT + re-run the legacy quad on it** — measures how overstated today's regime backtest is; the honest-numbers foundation for everything downstream.
7. **Build the MEASURED / MODELED / NO-EDGE badge system early** — the cheapest, highest-trust component in the whole plan and the actual product differentiator versus Hedgeye's confident-point UI.

**Recommended immediate start:** #1 (ALFRED audit) + #2/#3 (the two live-defect fixes) can proceed today in parallel with zero new dependencies. I'd green-light those first, let the audit result shape whether v0's base-effect leg reads core-PCE PIT or falls back to `revised=True`, then commit to v0.

---

## 5. The engine specs, critique, and recon appendix

What follows is the full detail: Sections **A–F** (the architect-authored engine specs — the crown-jewel forward-regime engine, the validation spine, the vol/flow layer, cross-asset + portfolio construction, the UX redesign, and the integrated roadmap), then the **Adversarial Critique** in full, then the **per-subsystem recon appendix**. Where a section conflicts with §2 above, **§2 wins** — those corrections are the verified ground truth.

---

# PART I — ENGINE SPECIFICATIONS (A-F)

## A. The Forward-Regime Engine (Layers 1–3) — the crown-jewel revamp

### A.0 Thesis and the design decision that governs everything below

The current Quad (`engine/regime.py::raw_quad` + `apply_hysteresis`, fed by `engine/axes.py::score_axis`) is a **coincident, first-derivative, market-proxy consensus** dressed as a macro regime. It computes the sign of a 20d slope z-scored against a 60d window (`engine/indicators.py::slope_z`), maps `|z|>0.45` to ±1, weight-averages ~6 market ratios plus a few binary econ signs, then argmaxes over four boxes with a 7-day hysteresis debounce. Live output today: `growth=+0.20 conf=0.125` (coin-flip), `inflation=-0.52 conf=0.416`, WEI and XLY/XLP *contradicting* the growth axis. There is no forward content, no probability, no point-in-time honesty, and no conditional return.

Hedgeye's disclosed edge is not "rate of change." It is a **comparative base-effects forecast**: a YoY reading has a denominator known exactly 12 months in advance, so holding sequential momentum at normal, the forward path of the YoY rate is *deterministically* bent by the base. Disclosed statistics on their data: the forward 2nd-derivative sign is the **inverse of the base-period 2nd-derivative ~68%** of the time; first-difference of the trailing 2yr base explains growth/inflation inflections ~80%/~70%. Everything downstream (Quad → gross/net dial, EV weighting by intensity) hangs off getting that forward sign right *before* the market prices it.

**Governing design decision.** We do **not** rip out the current engine. We invert the dependency: the base-effect forward projection (L1) becomes the *leading* axis input, the existing market-ratio slope-z legs become **confirmers** (they carry the price-discovery lead the base-effect math lacks intra-quarter), and the argmax+hysteresis is replaced by a Markov-switching posterior (L2) whose *state features include the forward 2nd-derivative signs*. The existing cycle-lead philosophy (`engine/cycles.py` daily-cycle ladder) and the validated drawdown-gate (`engine/equity_alloc.py` `RISK_WEIGHTS`, `LEG_LAGS`, the "forward DRAWDOWN is the house rule" doctrine) are **preserved verbatim** and consume the new `P(Quad)` instead of the argmax label. Rationale: those are the two things in the repo that actually validated out-of-sample; the new engine adds the return-alpha and forward-timing content they lack, it does not replace their risk discipline.

Trade-off I am taking a side on: **build L1+L2+L3 as a parallel `regime_fwd` pipeline that runs alongside the legacy quad for a full forward-grading period, gated behind a config flag, before it drives a single dollar.** The alternative (swap in place) is faster but violates the repo's own validate-before-weight gate and destroys the ability to A/B the two Quad paths on identical dates. Parallel-run costs ~1 extra pipeline branch in `engine/run.py` and one extra parquet; it is worth it.

---

### A.1 — L1a: Comparative base-effect forward projection (the real kernel)

**New file: `engine/base_effect.py`.** Pure, stateless, no lookahead. This is the highest-priority deliverable in the entire blueprint.

#### The exact math

For a monthly index level series `L` (seasonally adjusted level, e.g. CPI level `CPIAUCSL`, core PCE level `PCEPILFE`, INDPRO level `INDPRO`, payrolls level `PAYEMS`, WEI is already a rate — handle separately, see below):

1. **Known base path.** The YoY rate at future month `t+h` is
   `YoY_{t+h} = L_{t+h} / L_{t-12+h} − 1`.
   The denominator `L_{t-12+h}` is **fully known today for all h ∈ [1, 12]** — it is history. This is the deterministic spine.

2. **Sequential momentum estimate.** Let the trailing MoM log-change be `g_m = ln(L_m / L_{m-1})`. Estimate forward momentum three ways and carry all three (the spread *is* the uncertainty):
   - **flat / normal:** `ĝ = mean(g_{m-5..m})` (trailing 6m average MoM, deseasonalized — series are already SA).
   - **AR(1):** fit `g_m = c + φ·g_{m-1} + ε` causally (expanding window, min 60 obs), project `ĝ_{t+h} = c + φ·ĝ_{t+h-1}`.
   - **±0.5σ scenarios:** `ĝ ± 0.5·σ(g_{m-5..m})` for a fan.

3. **Projected level and YoY.** `L̂_{t+h} = L_t · exp(Σ_{k=1..h} ĝ_{t+k})`, then `ŶoY_{t+h} = L̂_{t+h} / L_{t-12+h} − 1`.

4. **Forward 2nd-derivative sign — the signal.**
   `d2_{t+h} = ŶoY_{t+h+1} − 2·ŶoY_{t+h} + ŶoY_{t+h-1}`.
   The published edge is that `sign(d2_forward)` is dominated by the base, i.e. it equals `−sign(d2_base)` where `d2_base` is the 2nd-difference of the *base-period* YoY path `{L_{t-12+h}}`. Emit the **base-forced sign** directly as the primary output because it is the piece that is momentum-independent and therefore honest:
   `base_forcing_h = −sign( YoY^{base}_{t+h+1} − 2·YoY^{base}_{t+h} + YoY^{base}_{t+h-1} )`
   where `YoY^{base}` is built from the known historical levels alone. Also emit the momentum-blended `ŶoY` fan for display.

5. **Aggregate to axis feed.** For each of the next 1/2/3 quarters, take the modal `base_forcing` sign across the months in that quarter. Output columns to be joined into the feature frame:
   - `be_infl_2d_q1, be_infl_2d_q2, be_infl_2d_q3` ∈ {−1,0,+1} (from core PCE + core CPI, averaged; PPI optional)
   - `be_growth_2d_q1..q3` ∈ {−1,0,+1} (from INDPRO + PAYEMS)
   - `be_infl_yoy_path`, `be_growth_yoy_path` (float arrays, display)
   - `be_forcing_intensity` = |ŶoY_{t+3q} − YoY_t| in the flat-momentum scenario (how hard the base is pushing) — feeds L2 intensity and L3 weighting.

**WEI handling.** WEI is already a YoY-style weekly growth index, not a level. Do not YoY it. Instead treat WEI's own trailing 13-week 2nd-difference as a fast coincident cross-check on `be_growth_2d_q1` and log agreement, but do not double-count it in the base-effect leg.

#### Point-in-time is mandatory here

The base-effect math is only honest on **vintage** data — using today's *revised* `PAYEMS`/`INDPRO` back-populates knowledge the market did not have. The repo already has the infrastructure and does not use it live: `collectors/fred.py::fetch_vintages / as_of_series / load_vintages`, and `data/fred_vintage/vintages.parquet` exists but is consumed **only** in offline scripts (`calibrate_regime.py`, `validate_claims_recession_pit.py`). The live path (`engine/inputs.py`, `engine/conditions.py`, `engine/axes.py`) reads latest revision exclusively.

- **Data source (flag PIT):** ALFRED vintages via the existing FRED key — `https://api.stlouisfed.org/fred/series/observations?series_id=PCEPILFE&realtime_start=…&realtime_end=…`. Series to vintage: `CPIAUCSL, PCEPILFE, CPILFESL, INDPRO, PAYEMS, PPIFIS`. WEI/GDPNOW are already near-real-time; register vintages but the intra-week revision is second order. **NFCI is explicitly excluded** (whole-history re-revision — already known in the repo).
- **New data artifact:** `data/fred_vintage/base_effect_vintages.parquet` keyed `(series_id, vintage_date, obs_date, value)`, refreshed nightly by extending `collect.py`'s vintage step.
- `base_effect.py` takes an `as_of: pd.Timestamp | None`. When `as_of` is set it calls `as_of_series(sid, as_of, vintages)` for every input; when `None` it falls through to latest-revision (so a display run without a key still works but is tagged `revised=True`).

**Effort L. Priority P0. Deps:** FRED_API_KEY; extend `collect.py` vintage step; the vintage helpers already exist.

**Forward-grading log (mandatory, ship day one):** append `data/regime/base_effect_fwd.jsonl` on every build: `{asof, be_growth_2d_q1, be_infl_2d_q1, realized_growth_2d_at_+63d(pending), realized_infl_2d_at_+63d(pending)}`. This is what lets us later answer "does our base-effect Quad reproduce the ~68% inversion stat on *our* data" (see A.4).

---

### A.2 — L1b: Mixed-frequency Dynamic Factor Model nowcast (distribution + variance)

The base-effect leg gives the deterministic *forward* bend but says nothing about *where the level is right now* with uncertainty. The current engine answers that with four independent binary `monthly_sign()` confirmers (`payrolls_trend`, `indpro_trend`, `wei_trend`, `gdpnow_trend`) at half weight each — no covariance, no state, no variance. Replace them with a proper mixed-frequency nowcast.

**New file: `engine/dfm_nowcast.py`.** Simplified two-step Giannone–Reichlin–Small DFM:

1. Standardize each series (monthly: INDPRO, PAYEMS, real income, mfg/trade sales, core PCE, sticky CPI; weekly: WEI, claims 4wk-MA; daily: GDPNow, ADS) causally (expanding mean/std).
2. Balanced-panel PCA at monthly frequency → extract two factors; orthogonalize the second to isolate an **inflation factor** vs a **growth factor**.
3. Kalman filter forward to *today* on the unbalanced daily/weekly observations (state = [growth_factor, inflation_factor], AR(1) transition), producing a **daily filtered state with posterior variance** `Σ_t`.
4. Output: `dfm_growth (mean, var)`, `dfm_infl (mean, var)`, on a daily index.

**ADS cross-check.** Ingest Philadelphia Fed ADS (`GADSBPTN6SVENY`, daily) and NY Fed WECI as an independent coincident anchor — low-effort FRED pull + `put('ads_index', …, ffill_limit=5)` in `engine/inputs.py`. Log ADS-vs-DFM growth agreement; do not blend in v1.

**How the two L1 legs feed the axes.** In `engine/axes.py::_component_scores`, **remove** the four `monthly_sign` growth confirmers and `sticky_cpi_direction`, and add:
- growth axis: `dfm_growth_z` (the DFM growth factor, z-scored, weight 1.0 replacing the 4 removed halves) + `be_growth_2d_q1` (weight 0.5, display-scored in v1 → validated-scored in v2).
- inflation axis: `dfm_infl_z` (weight 1.0) + `be_infl_2d_q1` (weight 0.5).
The market-ratio legs (`copper_gold, xly_xlp, iwm_spy, cyc_def, breadth_direction`, and the breakeven/oil/energy inflation legs) **stay as-is** — they are the intra-quarter confirmers. The DFM **posterior variance feeds regime confidence** (A.3) as an additive uncertainty term, killing the meaningless `|score|·agreement` heuristic.

**Effort XL. Priority P2 (after L1a base-effect and the PIT fix — those unblock it and are higher-edge).** Deps: L1a PIT (to avoid contaminating the factor); `statsmodels` or a small custom Kalman (no heavy dep).

**Trade-off / recommendation:** Do **not** gate L1a behind L1b. The base-effect determinism is the disclosed 68/80/70% edge and needs only vintage FRED data already available; the DFM is a better nowcast but is a supporting cast member. Ship base-effect first, run it forward-graded for a quarter, then add the DFM.

---

### A.3 — L2: Continuous regime probabilities via Markov-switching (replace argmax + hysteresis)

**New file: `engine/regime_hmm.py`.** Replace `raw_quad` + `apply_hysteresis` with a **4-state Gaussian Markov-switching model** (Hamilton 1989 filter / hmmlearn `GaussianHMM(n_components=4, covariance_type="full")` or `statsmodels MarkovRegression`).

#### State feature vector (this is the important design choice)

The blueprint says model over `[growth 2nd-deriv, inflation 2nd-deriv, liquidity impulse, policy stance]`. Concretely, the daily observation vector fed to the HMM:

```
x_t = [ dfm_growth_z_t,                # L1b nowcast level state
        dfm_infl_z_t,
        be_growth_2d_q1_t,             # L1a forward base-effect sign, growth
        be_infl_2d_q1_t,               # L1a forward base-effect sign, inflation
        liquidity_impulse_z_t,         # NEW axis, below
        policy_stance_z_t ]            # NEW axis, below
```

Including the **forward base-effect signs as HMM inputs** is what makes this a *forward* regime engine rather than a smoothed coincident one — the transition dynamics learn that a base-forced inflation deceleration precedes Q3→Q1 rotations. This is the single most important line in the section.

**Liquidity and policy become explicit scored axes**, not the current post-hoc string overlays (`regime.py::liquidity_overlay` returns `expanding/neutral/contracting`; policy is nowhere). Extend `engine/axes.py` with two new axes computed identically to growth/inflation:
- `liquidity_impulse`: components = net-liquidity (WALCL−RRP−TGA) 20d RoC z, NFCI z, HY-OAS 20d-change z, A2P2 CP-spread z. **Remove `us2y_direction` from the growth axis** and relocate rate signals here/policy — it is a rates leg, not a growth leg, and its presence in growth is a known contradiction source.
- `policy_stance`: components = fed_funds vs us2y spread direction, GDPNow−fed_funds gap sign, ZQ-implied 12m repricing, real-rate (DFII10) direction.

#### Outputs (new schema)

Fit on expanding window, **re-estimate quarterly** (causal; never re-fit on future data). Emit daily to a new artifact `data/regime/hmm_history.parquet` and `data/regime/hmm_latest.json`:
- `P(Q1), P(Q2), P(Q3), P(Q4)` — proper posterior, sums to 1.
- `A[i,j]` = fitted 4×4 transition matrix → `next_quad_probs` = row for current modal state.
- `time_in_regime` and **hazard** = `1 − A[i,i]` (per-day flip probability) plus a Weibull/KM dwell-time overlay from historical run lengths for the "P(regime ends in next N days | age)" read.
- `regime_confidence_bayes` = `max_k P(Q_k)` **and** a bootstrap CI on the axis scores (block bootstrap, block=20d, B=500) — this replaces the `|score|·agreement` scalar with something that means something. Feed DFM `Σ_t` in as an additive widening term.
- `intensity_k` = `P(Q_k) · (|dfm_growth_z|+|dfm_infl_z|)/2 · be_forcing_intensity` — the "delta into the quad" the backtests are supposed to be weighted by, and which the current engine discards at argmax.

#### Coexistence with the legacy quad and the existing cycle/drawdown philosophy

- Keep `raw_quad` + `apply_hysteresis` running in `engine/regime.py` unchanged, tagged `quad_legacy`. `argmax_k P(Q_k)` becomes `quad_fwd`. Both are written to `latest.json`. The 2×2 UI locator (`templates/dashboard.html.j2:1493`) switches to **cell opacity = P(Q_k)**, current cell outlined — no more binary lit cell.
- The **drawdown gate stays sovereign.** `engine/equity_alloc.py`'s pre-registered `RISK_WEIGHTS` / `LEG_LAGS` glide path and the `risk_radar`/`risk_state` context gate are *not* touched. They now read `P(Q3)+P(Q4)` and `hazard` as additional legs where useful, but the "forward DRAWDOWN is the house rule, subtract-only, no fabricated alpha" doctrine is unchanged. The HMM adds return-alpha (L3); it does not get to relax risk.
- The **cycle-lead ladder** (`engine/cycles.py`) keeps its daily/investor-cycle timing; where it currently applies a fixed liquidity tailwind/headwind scalar on FRESH BUY/TURN SIGNALED, it now reads `liquidity_impulse` continuous z and `hazard` (widen/de-emphasize mean-reversion when `hazard` is high — the blueprint's L4 instruction, cheaply implemented here).

**Effort L. Priority P1** (P0 is base-effect + PIT; the HMM is worthless without honest L1 inputs). Deps: L1a, L1b, `hmmlearn`/`statsmodels`. **Validation gate:** fixed train ≤2019, evaluate 2020–2026 hold-out; the posterior must cluster tightly in the 2008/2020/2022 episodes and the transition matrix's Q2→Q3 and Q1→Q4 probabilities must be non-trivial. No `--write` of the scored path until this passes.

---

### A.4 — L3: Regime-conditional expected-value engine (the "Hubble" ranker)

**New file: `engine/regime_ev.py`.** This is the missing return-alpha driver — the current system has *zero* `E[r|regime]` anywhere; `config.yml sector_preferences` is a textbook prior, not a measured estimate.

#### The math

For each asset/sleeve `a` in a configured universe (11 SPDR sectors + IWM + LQD + HYG + GLD + factor ETFs) and each quad `k`, using **point-in-time regime labels**:

1. `mu_{a,k}` = mean forward N-day return `| quad==k`, for N ∈ {21, 63, 126}. **Leak control:** shift the regime label by `hysteresis_days` (or the HMM's re-fit embargo) so the label's own confirmation window cannot overlap the forward return; estimate on an **expanding window**.
2. `CVaR_{a,k}` = mean of the worst 10% of forward returns in quad `k` (the drawdown-budget denominator — consistent with the repo's forward-DD house rule).
3. Integrate over the posterior and weight by intensity:
   `E[r_a] = Σ_k P(Q_k) · mu_{a,k} · intensity_k`
   `CVaR_a = Σ_k P(Q_k) · CVaR_{a,k}`
4. **Rank all `a` by `E[r_a] / |CVaR_a|`** → the cross-sectional Hubble ranker = (regime-fit) × (timing/vol-band state, joined from `engine/vol_forecast.py` / cycle ladder), sized to a drawdown budget downstream in L7.

Fallback when the HMM is not yet promoted: `P(Q_k)` degenerates to the argmax `{0,1}` (legacy quad), so L3 produces a defensible ranking on day one and improves continuously as L2 matures.

#### Outputs and wiring

- New artifact `data/regime/ev_ranker.json`: per-asset `{mu_21/63/126, cvar, E_r, cvar_int, ev_cvar_ratio, n_obs_per_quad, thin_flag(n<30), newey_west_t}`.
- Feed into the playbook sector heat table (`engine/playbook.py`) as a **second column** beside the existing RS/stage score — do not overwrite the validated stage logic; present EV alongside it and let the user see divergences.
- Log every day's `mu` estimates to `data/regime/ev_fwd.jsonl` for forward grading.

**Effort L. Priority P1** (can start immediately with the argmax fallback; upgrades free when L2 lands). Deps: `regime_history.parquet` (exists), L2 for the proper posterior, `engine/validation.py` (`purged_folds`, `newey_west_tstat`, `deflated_sharpe` all already implemented and tested).

**Trade-off / recommendation:** thin-cell honesty is non-negotiable. With ~14k daily rows but only a handful of true regime episodes, several `(a,k)` cells will have `n_obs < 30`. **Display `n_obs` and Wilson/NW CIs on every cell, suppress ranking contribution when thin, and never size off a thin cell.** The temptation to smooth thin cells with a shrinkage prior toward the sector's unconditional mean is acceptable *only* if the shrinkage weight is a function of `n_obs` and disclosed — I recommend James-Stein shrinkage of `mu_{a,k}` toward `mu_a` (unconditional) with intensity `n_obs/(n_obs+τ)`, τ≈30.

---

### A.5 — Files to change / create, exact manifest

**Extend (do not rewrite):**
- `engine/inputs.py::build_features` — add `as_of` param; PIT vintage reads for the base-effect series; add `ads_index`; join `base_effect.py` and `dfm_nowcast.py` outputs into the daily frame.
- `engine/axes.py::_component_scores` — remove 4 growth `monthly_sign` legs + `sticky_cpi_direction`; add `dfm_growth_z`, `dfm_infl_z`, `be_growth_2d_q1`, `be_infl_2d_q1`; **move `us2y_direction` out of growth**; add `score_axis(f,"liquidity_impulse")` and `score_axis(f,"policy_stance")`.
- `engine/regime.py` — keep `raw_quad`/`apply_hysteresis` as `quad_legacy`; import `regime_hmm` for `quad_fwd`/`P(Q_k)`; liquidity/policy overlays become thin readers of the new scored axes.
- `engine/conditions.py` — MRS liquidity leg goes from binary to the continuous `liquidity_impulse` z; MRS transition leg reads HMM `1 − P(same quad | t+21)` instead of the heuristic `WEAKENING/TRANSITIONING` map.
- `engine/run.py` — branch: build features (PIT) → `base_effect` → `dfm_nowcast` → legacy `classify` **and** `regime_hmm.fit_filter` → `regime_ev` → transition flags → write `regime_history.parquet` + `hmm_history.parquet` + `ev_ranker.json` + the three `*_fwd.jsonl` grading logs. Gate the `_fwd` pipeline behind `config: engine.regime_fwd.enabled`.
- `config.yml` — new blocks: `engine.base_effect` (momentum window, scenarios), `engine.dfm` (n_factors, refit_days), `engine.regime_hmm` (n_states=4, refit_days=63, embargo), `engine.liquidity_impulse.components`, `engine.policy_stance.components`, `engine.regime_ev` (horizons, min_obs_per_quad, shrinkage τ). Remove the four deleted axis component weights.
- `templates/dashboard.html.j2` — 2×2 locator → probability heat; add `next_quad_probs` bars (the `.prob` CSS already exists, just unused) and a `hazard`/`P(transition 21d)` chip; activate the dead `trendword()/nchart()` sparkline macros on the base-effect YoY forward path.

**Create:**
- `engine/base_effect.py`, `engine/dfm_nowcast.py`, `engine/regime_hmm.py`, `engine/regime_ev.py`
- `scripts/validate_regime_fwd.py` (see A.6)
- Data: `data/fred_vintage/base_effect_vintages.parquet`, `data/regime/hmm_history.parquet`, `data/regime/hmm_latest.json`, `data/regime/ev_ranker.json`, `data/regime/{base_effect,dfm,ev}_fwd.jsonl`

**data/regime schema additions to `latest.json`:** `quad_legacy`, `quad_fwd`, `regime_probs{Q1..Q4}`, `transition_matrix`, `next_quad_probs`, `time_in_regime`, `hazard`, `regime_confidence_bayes`, `regime_conf_ci{lo,hi}`, `intensity{Q1..Q4}`, `base_effect{growth_2d_q1..q3, infl_2d_q1..q3, growth_yoy_path, infl_yoy_path, forcing_intensity}`, `dfm{growth_mean,growth_var,infl_mean,infl_var}`, `revised:bool`.

---

### A.6 — Validation, fallback, and the acid test

**`scripts/validate_regime_fwd.py` — this is the go/no-go gate and must exist before any scored promotion.** Three parts:

1. **Reproduce the disclosed inversion stat on our data.** Using the base-effect forward-grading log once matured: compute the fraction of months where `sign(realized 2nd-deriv of YoY at +1q) == −sign(base-period 2nd-deriv)`. **Target: ≥60% for growth and inflation** (Hedgeye claims ~68% growth-inflection / ~80% / ~70% on their data; on point-in-time free FRED with our momentum assumption I expect 60–68%). Also regress the realized YoY inflection on the trailing 2yr base first-difference and report R². **If growth inversion < 55% on our PIT data, the base-effect leg does NOT get scored weight — it stays display-only and the HMM drops those two state features.** That is the honest fallback: the market-ratio confirmers + DFM nowcast still give a defensible coincident Quad, just without the disclosed forward edge, and we say so.

2. **Purged K-fold + Deflated Sharpe on the Quad labels vs forward asset returns.** Reuse `engine/validation.py`: `purged_folds(K=6, embargo=21d)`; rank-IC (Spearman, Newey-West t) of `growth_score`→fwd-63d equity return and `inflation_score`→fwd-63d TIP return; **DSR accounting for the tuning trials** — pass the real `n_trials` from `scripts/tune.py`'s grid (the current 36-combo in-sample grid search with no hold-out is the single worst overfitting risk in the crown jewel). Break the scorecard out by realized regime **and** VIX bucket (<15/15–25/>25). Also fix `scripts/tune.py` itself: fixed train ≤2014, evaluate 2015–2026 hold-out, block-bootstrap CI on each episode-fidelity criterion, print a DSR<0.90 warning.

3. **A/B the two Quad paths.** On identical dates, compare `quad_legacy` vs `quad_fwd` on: (a) forward-63d drawdown avoidance (the house rule), (b) L3 EV-ranker rank-IC. `quad_fwd` must beat `quad_legacy` on the *forward* metric on the 2015–2026 hold-out, or it does not get promoted — parallel-run makes this a clean, honest comparison.

**Promotion policy:** the `regime_fwd` scored path is enabled (`config.engine.regime_fwd.enabled: true` driving live sizing) **only** after: base-effect inversion ≥55% PIT (part 1), Quad rank-IC DSR ≥ ~0.9 with the honest `n_trials` (part 2), and `quad_fwd` beats `quad_legacy` on forward-DD out-of-sample (part 3). Until then it renders display-only alongside the legacy quad — exactly the discipline the repo already applies to `vol_regime` and `gex` gates.

**One-line verdict for this section:** replace the coincident first-derivative argmax with a *forward* engine — base-effect determinism on ALFRED vintages (L1a) + a mixed-frequency DFM state with variance (L1b) feeding a Markov-switching posterior with a real transition matrix and hazard (L2) that drives an intensity-weighted, point-in-time-labelled, drawdown-budgeted conditional-EV ranker (L3) — while preserving verbatim the two things that actually validated (the cycle-lead ladder and the subtract-only forward-drawdown gate), and refusing to score any of it until it reproduces the disclosed inversion statistic on our own data.
## B. The Validation & Honest-Accounting Spine (Layer 6)

**Thesis.** Hedgeye sells win-rate theater: "36% positive / 32% beat SPY on 148 trades," no expectancy, no Deflated Sharpe, no Probability of Backtest Overfitting, backtests on *revised* data. We already own the machinery to be categorically better — `engine/validation.py` is a complete, tested López de Prado primitive suite. The gap is **wiring and governance, not math**: the primitives run in offline research scripts, but nothing forces a *displayed recommendation* to have passed them, the crown-jewel scorecard (`signal_lab.py` REGISTRY) is hand-curated numbers quoted from report `.md` files, and the one true validity gate we ship (`validate_signals.py`) only checks JSON shape. This section makes LdP validation a **non-negotiable, machine-enforced admission gate** — nothing influences a rendered recommendation until it clears the gate, and the gate output is the honest-accounting scorecard the user sees.

The design principle is a **hard firewall**: a signal has exactly two states, `DISPLAY_ONLY` (may be shown with a red "unvalidated" caveat, may not size or gate anything) and `SCORED` (may enter allocation / conviction / buy-gate). The transition between them is a single function call whose inputs are point-in-time only. This mirrors the pattern the vol stack already uses (`data/vol_regime/gate.json`, `scored_score()` returns `None` when the gate is absent) — we generalize it to the whole system.

---

### B.0 What exists today vs. what is missing

| Capability | Where it lives now | Status | Action |
|---|---|---|---|
| Deflated Sharpe (Bailey–LdP) | `engine/validation.py:deflated_sharpe()` (ledger-honest N path + `dsr_verdict`) | ✅ implemented, tested | Wire into every scored strategy |
| PBO / CSCV | `engine/validation.py:prob_backtest_overfitting()` (16-split CSCV) | ✅ implemented | Wire into gate |
| Purged K-fold + embargo | `engine/validation.py:purged_folds()`, `cpcv_paths()` | ✅ implemented | Wire into gate |
| Triple-barrier labels | `engine/meta_label.py:triple_barrier_labels()` | ⚠️ **BTC-only, default-OFF, KILLED** | Generalize to US equity + macro strategies |
| Meta-labeling (size/skip) | `engine/meta_label.py:purged_oof_proba()` + `meta_size()` | ⚠️ BTC-only, not wired to US confluence buy-filter | Apply to `signal_gate`/`walk_forward` entries |
| Rank-IC + Newey-West HAC | `engine/validation.py:rank_ic()`, `newey_west_tstat()`, `ic_summary()` | ✅ implemented; used in `factor_ic_scorecard.py` | Extend to all cross-sectional engines |
| Block-bootstrap CI | `engine/validation.py:block_bootstrap_ci()` | ✅ implemented | Wire into every Sharpe/MaxDD display |
| Calibration (Brier/Platt/ECE/isotonic) | `engine/validation.py` (5 fns) | ✅ implemented | Mandatory for any signal emitting a probability |
| OOS-R² / Clark-West | `engine/validation.py:oos_r2()`, `clark_west()` | ✅ implemented, **UNUSED on any live signal** | Mandatory for any return-forecast signal |
| Trial Ledger (multiple-testing N) | `engine/trial_ledger.py` (append-only, `effective_n()`) | ✅ implemented + `test_no_literal_ntrials.py` ratchet | Make it the *only* N source in the gate |
| Signal contract gate | `scripts/validate_signals.py` | ✅ ships in `daily.yml` — but it's a **JSON-schema/marker-order check, NOT a validity check** | Keep as-is; add a *separate* validity gate |
| Scorecard registry | `engine/signal_lab.py` REGISTRY (40+ hand-curated rows) | ⚠️ numbers manually quoted from `reports/*.md`; not recomputed | Replace curated numerics with a machine-read ledger |
| Regime × VIX breakout | — | ❌ **does not exist anywhere** | Build |
| Automated IC-decay monitor | `engine/drift.py:rolling_ic_drift()` wired into `promotion_gate.py` only | ⚠️ exists but no daily CI step; SUE demotion was found *manually* | Add daily monitor step |
| Point-in-time enforcement | ALFRED infra in `collectors/edgar.py` / `collectors/fred.py`; used only in offline audits | ⚠️ live engines read latest-revision | Gate must *refuse to score* on non-PIT data |

**Bottom line:** ~80% of the primitives exist and are tested. The missing 20% is (a) a single acceptance-gate function, (b) a machine-written scorecard artifact that replaces hand-curated REGISTRY numbers, (c) the regime×VIX breakout, (d) generalized triple-barrier/meta-labeling beyond BTC, and (e) a daily decay monitor + PIT enforcement. That is a **weeks-not-months** program because we are assembling, not inventing.

---

### B.1 The canonical strategy record and the acceptance gate

Every candidate — a factor, a regime-conditional EV cell, a buy-gate tier, a GTAA sleeve, a risk-radar leg — must produce a **uniform evidence record** and be judged by **one function**. No engine gets its own bespoke pass/fail logic.

**New file: `engine/validation_gate.py`** (effort **M**, priority **P0**, deps: `engine/validation.py`, `engine/trial_ledger.py`, `engine/meta_label.py`).

```python
# engine/validation_gate.py
from dataclasses import dataclass, asdict

@dataclass
class StrategyEvidence:
    strategy_id: str          # stable key, e.g. "sector_ev.XLK.Q1.63d"
    family: str               # Trial-Ledger family for the multiple-testing N
    universe_pit: bool        # True iff every input series is point-in-time
    n_obs: int
    # --- return-following accounting (the anti-Hedgeye block) ---
    expectancy: float         # mean per-signal P&L (see B.2)
    profit_factor: float      # gross win / gross loss
    maxdd_following: float    # worst DD of the signal-FOLLOWING equity curve
    rank_ic: float | None     # cross-sectional signals only
    rank_ic_t_hac: float | None
    # --- LdP validation block ---
    dsr: float                # deflated_sharpe(...)["dsr"] via ledger path
    pbo: float                # prob_backtest_overfitting(...)["pbo"]
    cpcv_path_sign_frac: float# fraction of CPCV paths with correct-sign edge
    sharpe_ci: tuple          # block_bootstrap_ci -> (lo, mid, hi)
    # --- calibration (probability-emitting signals only) ---
    brier_skill: float | None
    platt_a: float | None
    # --- regime honesty (B.4) ---
    ic_by_quad: dict          # {"Q1": ic, "Q2": ..., "Q3": ..., "Q4": ...}
    ic_by_vix: dict           # {"lt15": ic, "15_25": ..., "gt25": ...}
    worst_regime_ic: float    # min over quad cells with n>=MIN_CELL

# --- acceptance thresholds (single source of truth; overridable in config.yml) ---
GATE = dict(
    dsr_min          = 0.95,   # SURVIVES multiple-testing
    pbo_max          = 0.50,   # LdP: PBO>0.5 means IS-best is OOS-coin-flip
    cpcv_sign_min    = 0.80,   # edge sign holds on >=80% of purged paths
    profit_factor_min= 1.15,   # expectancy positive with margin
    ic_t_hac_min     = 2.0,    # cross-sectional signals
    worst_regime_ic_min = -0.02,# no regime where the signal is actively harmful
    require_pit       = True,   # non-PIT -> DISPLAY_ONLY, full stop
    require_calibration = True, # if it emits a probability: Brier skill>0 AND 0.3<=platt_a<=2.0
)

def admit(ev: StrategyEvidence, cfg=GATE) -> dict:
    """Return {'state': 'SCORED'|'DISPLAY_ONLY', 'blocking': [...], 'ev': asdict(ev)}."""
    block = []
    if cfg["require_pit"] and not ev.universe_pit:      block.append("not-point-in-time")
    if ev.dsr  < cfg["dsr_min"]:                        block.append(f"dsr {ev.dsr:.3f}<{cfg['dsr_min']}")
    if ev.pbo  > cfg["pbo_max"]:                        block.append(f"pbo {ev.pbo:.2f}>{cfg['pbo_max']}")
    if ev.cpcv_path_sign_frac < cfg["cpcv_sign_min"]:   block.append("cpcv-sign")
    if ev.profit_factor < cfg["profit_factor_min"]:     block.append("profit-factor")
    if ev.worst_regime_ic < cfg["worst_regime_ic_min"]: block.append("harmful-in-a-regime")
    if ev.rank_ic is not None and (ev.rank_ic_t_hac or 0) < cfg["ic_t_hac_min"]:
        block.append("ic-t-hac")
    if cfg["require_calibration"] and ev.brier_skill is not None:
        if ev.brier_skill <= 0 or not (0.3 <= (ev.platt_a or 0) <= 2.0):
            block.append("uncalibrated")
    return {"state": "SCORED" if not block else "DISPLAY_ONLY",
            "blocking": block, "ev": asdict(ev)}
```

**The firewall rule (system-wide invariant):** any code path that turns a signal into a *size, a gate, or a ranked recommendation* must first read that strategy's `state` from `data/quality/strategy_ledger.json` (B.3) and treat `DISPLAY_ONLY` as "compute and show, but multiply its allocation contribution by zero." This is enforceable with a single lint (`tests/test_scored_reads_gate.py`, effort **S**) that greps for the allocation-write call sites (`masterminds._weights`, `signal_gate.is_buyable`, `sector_central._fuse`, `narrative_rotation.allocate`, `regime_ev.rank`) and asserts each imports and checks the ledger.

**Design choice — DSR threshold 0.95, not 0.90.** `dsr_verdict()` already bands at ≥0.95 SURVIVES / ≥0.90 MARGINAL. **Recommendation: SCORED requires ≥0.95; MARGINAL (0.90–0.95) is displayable but not scorable.** Trade-off: this will keep several currently-scored objects out of allocation until re-validated (e.g. any factor whose DSR was quoted at deep-panel survivorship-biased numbers). That is the correct outcome — the user risks real money; a coin-flip-adjacent DSR sizing a book is exactly the Hedgeye failure mode we are eliminating.

**Design choice — N comes only from the Trial Ledger.** `deflated_sharpe()` already supports the honest `ledger=`+`family=` path and the `test_no_literal_ntrials.py` ratchet blocks new `n_trials=` literals. The gate passes `ledger=TrialLedger()` unconditionally. Trade-off: every engine author must `log_grid()` their parameter search at generation time. This is friction, and it is the point — it is the single defense against the p-hacking that makes published win-rates meaningless.

---

### B.2 Anti-Hedgeye accounting: expectancy, profit-factor, MaxDD-of-following, rank-IC

Hedgeye reports hit-rate. We report the full return distribution of *following the signal*. Add to `engine/validation.py` (effort **S**, priority **P0**):

```python
def signal_accounting(per_signal_pnl: pd.Series) -> dict:
    """per_signal_pnl = realized return of each triggered trade (triple-barrier exit)."""
    w = per_signal_pnl[per_signal_pnl > 0]; l = per_signal_pnl[per_signal_pnl < 0]
    gross_win, gross_loss = w.sum(), -l.sum()
    expectancy   = per_signal_pnl.mean()                       # E[r] per signal
    profit_factor= gross_win / gross_loss if gross_loss > 0 else np.inf
    hit          = (per_signal_pnl > 0).mean()
    payoff       = (w.mean() / -l.mean()) if len(l) else np.inf # avg win / avg loss
    return dict(expectancy=expectancy, profit_factor=profit_factor,
                hit=hit, payoff=payoff, n=len(per_signal_pnl))

def maxdd_following(equity_of_signal_strategy: pd.Series) -> float:
    e = equity_of_signal_strategy
    return float((e / e.cummax() - 1.0).min())
```

**MaxDD-of-signal-following** is the metric Hedgeye never shows and the one the user actually feels: not the max drawdown of the underlying, but of the *equity curve you'd have riding this signal at the sizes it prescribes*. `walk_forward.py` already simulates as-traded-with-stop equity per trial — expose its equity series and feed it here.

Expectancy is the honest headline: **`expectancy = hit × avg_win − (1−hit) × avg_loss`**. A 40%-hit signal with a 3:1 payoff has positive expectancy; a 60%-hit signal with a 1:2 payoff is a slow bleed. Publishing hit alone (as Hedgeye does) is the lie; expectancy + profit-factor is the correction.

For cross-sectional engines (factors, sector EV, subsector emerging_score), the analog is **rank-IC with Newey-West HAC t** — already in `validation.py`, already used in `factor_ic_scorecard.py`. The gate requires `t_hac ≥ 2.0` on overlapping-window ICs (HAC is mandatory because 63d-forward ICs sampled daily are massively autocorrelated; a naive t-stat overstates significance by ~3–4×).

---

### B.3 The machine-written scorecard ledger (replacing hand-curated REGISTRY)

**The single biggest integrity flaw in the current spine:** `engine/signal_lab.py` REGISTRY hard-codes numbers quoted from `reports/*.md` (`dsr=0.9994`, `sharpe=0.58`, etc.). These are frozen at the moment the report was written and drift silently — the SUE demotion (IC collapsed from meaningful to 0.0006 on the deep panel) was caught by a *manual* re-validation, not by the system.

**Fix:** every gate run appends to an **append-only JSONL ledger**, and `signal_lab.build_scorecard()` reads *that* instead of literals.

- **New artifact: `data/quality/strategy_ledger.jsonl`** — one row per `admit()` call: `{asof, strategy_id, family, state, blocking, ev:{...full StrategyEvidence...}}`. Append-only (never overwritten) so decay is visible as a time series.
- **New artifact: `data/quality/strategy_ledger.json`** — the *latest* row per `strategy_id` (the live snapshot the page reads).
- **Modify `engine/signal_lab.py`** (effort **M**, priority **P0**): `_row()` keeps human `why`/`why_zh` prose (irreplaceable context) but every numeric field (`dsr`, `sharpe`, `ic`, `hit`, `n`, tier) is looked up by `strategy_id` from `strategy_ledger.json` at build time. If a strategy is in REGISTRY but has no ledger row → render it greyed with `"NEVER VALIDATED"`. If its latest ledger row is >45 days stale → render an amber "STALE" badge. This makes it *impossible* to display a validated-looking number that no longer reflects a live computation.

**Trade-off:** this couples the page render to the gate having run. Recommendation: run the gate battery as a `daily.yml` step *before* `build_site.py` (it is cheap for already-computed signals; the expensive part — CPCV, bootstraps — runs weekly and caches). Accept a one-build lag on freshly-added strategies; that is strictly safer than showing a stale literal.

---

### B.4 Scorecard broken out by realized regime AND VIX bucket

This does not exist anywhere and is the highest-value honesty upgrade for a real-money user: *a signal that works only in calm Q1 and inverts in Q4 is a liability disguised as an edge.*

**New file: `scripts/validate_regime_vix_breakout.py`** (effort **M**, priority **P0**, deps: `data/regime/regime_history.parquet` (quad labels, 1971→now), `data/yahoo/_VIX.parquet`, `engine/validation.py`).

For any strategy exposing a per-date signal series and forward returns:

1. **Regime label at each date** — join `regime_history.parquet` on the quad column, **shifted by `hysteresis_days` (7)** so the label used at date *t* is one that was *confirmed* by *t* (no peeking at the confirmation window). This is the same PIT discipline `regime_ev` must use.
2. **VIX bucket** — `<15` / `15–25` / `>25` from `_VIX` close at *t*.
3. Per (quad × vix) cell with `n ≥ MIN_CELL=30`: compute `rank_ic` (cross-sectional) or `expectancy`+`profit_factor` (time-series), each with `block_bootstrap_ci`.
4. Emit `ic_by_quad`, `ic_by_vix`, and `worst_regime_ic = min over cells` into the `StrategyEvidence`.

The gate rejects (`worst-regime-harmful`) any strategy with `worst_regime_ic < −0.02` in a populated cell — i.e., we refuse to *score* a signal that is actively wrong somewhere, even if its pooled IC is positive. It may still be `DISPLAY_ONLY` with the breakout table shown so the user sees exactly where it fails.

**Render:** a 4×3 heat table (quad rows × VIX columns), green/red by cell IC, greyed where `n<30`, on the strategy's `signal_lab` detail row.

---

### B.5 Triple-barrier + meta-labeling beyond BTC

`engine/meta_label.py` is architecturally complete (triple-barrier, purged OOF probabilities via CPCV *and* walk-forward, meta-size schemes, `dsr_floor=0.90`) but hard-scoped to the BTC vector and default-off — and there it was correctly **KILLED** (ΔSharpe −0.43, negative Brier skill). The infrastructure is sound; the application is narrow.

**Two extensions (effort L each, priority P1):**

1. **Generalize `run_meta_label()` to accept any (close, primary-signal) pair.** The US confluence buy-filter (`engine/signal_gate.py` T1–T4 cascade, driven by `research/signal_engine/walk_forward.py`) currently optimizes `stop_out_rate` and publishes **no P(trade-correct)** — it selects better entries but never quantifies or calibrates the win probability. Apply triple-barrier labels to its entries (`triple_barrier_labels(close, primary_events(...), horizon, mult=vol_scaled)`), fit `purged_oof_proba`, and emit a **calibrated P(win | context)** via `platt_fit`. Then meta-size: skip trades below a probability floor, scale size linearly above it (`meta_size(scheme="prob_linear")`). This is the missing bridge between the stop-out-rate harness and honest sizing.

2. **Wire meta-labeling as the sizing layer for the L3 conditional-EV driver** (B.6). The EV ranker gives *direction and magnitude* (`E[r]/CVaR`); meta-labeling gives *confidence to skip/size* on top. `meta_size` scales the EV-implied weight by calibrated P(win).

**Recommendation:** triple-barrier `mult` is vol-scaled per LdP (barriers at `p0·(1 ± mult·σ·√horizon)`), and the time-barrier fallback = sign of forward return (already implemented). Keep the default-OFF stance until each application clears `dsr_floor` *and* calibration on its own holdout — do not repeat the BTC mistake of shipping a plausible architecture that loses 20/20 configs.

---

### B.6 The acceptance gate for the L3 conditional-EV driver (the critical case)

The blueprint's core return-alpha engine is L3: `E[r_a] = Σ_k P(Quad_k)·μ_{a,k}·intensity_k`, ranked by `E[r]/CVaR`. It appears in the recon as a proposed upgrade in *six* subsystems (`sector_regime_ev`, `basket_regime_ev`, `factor_regime_ev`, `china_regime_ev`, `regime_ev` cross-asset, `btc_conditional_ev`). **This is the single most dangerous thing to ship unvalidated**, because it directly proposes cross-asset weights from small-N regime cells. It gets the strictest, most explicit gate.

An L3 EV strategy is `SCORED` **only if all hold** (deps: L2 regime probabilities, `regime_history.parquet`, `engine/validation.py`, `scripts/validate_regime_vix_breakout.py`; effort **L**; priority **P0** as a *precondition* — L3 may be built and displayed before this passes, but may not size):

1. **PIT labels.** `μ_{a,k}` estimated on regime labels shifted by `hysteresis_days`; forward returns non-overlapping with the label's confirmation window. Non-PIT ⇒ `DISPLAY_ONLY`, no exceptions.
2. **Minimum cell count.** Every `(asset, quad)` cell used in the live `E[r]` sum has `n ≥ 30` matured observations. Thin cells (`n<30`) fall back to the pooled marginal and the strategy is flagged `thin` — **thin ⇒ DISPLAY_ONLY** for that asset. (Regime cells are brutally small: ~10–40 obs is common. This is the binding constraint, not the math.)
3. **Purged K-fold rank-IC of the *ranker*.** Cross-sectional rank-IC of `E[r]/CVaR` vs realized forward return, via `purged_folds(k=6, embargo=horizon_d)`, `t_hac ≥ 2.0`.
4. **DSR ≥ 0.95 and PBO ≤ 0.50** on the long-top / short-bottom EV-rotation portfolio, N from the Trial Ledger family `regime_ev.<region>`.
5. **CPCV path-sign ≥ 0.80** — the EV ranking's sign edge holds on ≥80% of combinatorial purged paths.
6. **Regime×VIX breakout non-harmful** — `worst_regime_ic ≥ −0.02` (B.4). An EV engine that inverts in the very regime it's conditioning on is disqualified.
7. **Bootstrap CI excludes zero** — `block_bootstrap_ci` Sharpe lower bound > 0.

**Recommendation on intensity weighting:** `intensity_k` should be `P(Quad_k)` from the L2 Markov-switching model (continuous), *not* the current heuristic `confidence = |score|·agreement`. Until L2 ships, fall back to argmax `P=1` and flag the strategy `intensity=argmax_fallback` — this is honest and the gate still applies. Do **not** let the coin-flip confidence (the recon notes live `growth conf=0.125`) silently weight EV; that manufactures false precision.

**Trade-off stated plainly:** cells will be thin, so most L3 assets will *start* `DISPLAY_ONLY`. That is correct. The value of L3 accrues as observations mature; shipping it as a sized allocator on 15-obs cells is precisely the over-fit the whole spine exists to prevent. The user sees the ranked table with honest `n` and wide CIs, and it earns the right to size over time.

---

### B.7 Point-in-time enforcement (the data-integrity precondition)

Every gate above is a lie if computed on revised data — revised series are systematically smoother in crises, inflating every crisis-conditional edge. The recon confirms ALFRED/vintage infra exists (`collectors/edgar.py:as_of_cross_section`, `collectors/fred.py:as_of_series`/`load_vintages`) but the **live engines read latest-revision**.

**The gate makes PIT non-optional for SCORED status** (`require_pit=True`). Concretely (effort **M**, priority **P0**, deps: FRED/ALFRED key already in env):

- **New helper `lib/pit.py:is_pit(series_id) -> bool`** — returns True iff the series was read through a vintage-aware path (`as_of_series`) for the dates in the evaluation window. Engines tag each input; the gate ANDs them into `universe_pit`.
- **Priority vintage set** (highest revision impact): `PAYEMS`, `INDPRO`, `WEI`, `GDPNOW`, `STICKCPIM157SFRBATL`, `RECPROUSM156N`, `NFCI` (caveat: NFCI re-revises whole history — flag `pit_partial`, use latest with an explicit "revised-data" tag rather than claiming PIT).
- **De-biased factor panel** (`scripts/factor_ic_scorecard.py --debiased` → `ic_scorecard_debiased.json`): the live `signal_lab` must prefer the de-biased scorecard once dead-name price coverage ≥ 30%. Survivorship bias is the factor-desk analog of revised data — the currently-live `payout q=0.0715` was measured on a survivor-biased panel and is an optimistic bound the gate must not treat as PIT-clean.

Market-price series (Yahoo close) are inherently PIT for their own values (a close is a close); the PIT requirement bites on *economic* legs, which is exactly where the recon flags the exposure.

---

### B.8 The upgraded `signal_lab.html` panel

The page becomes the honest-accounting spine's public face — the direct, itemized rebuttal to win-rate theater. Modify `templates/signal_lab.html.j2` + `engine/signal_lab.py` (effort **M**, priority **P1**, deps: B.3 ledger, B.4 breakout).

Per strategy row, rendered **from the machine ledger, never from literals**:

- **State badge** — `SCORED` (green, "sizes the book") / `DISPLAY_ONLY` (amber, "shown, does not size") / `NEVER VALIDATED` (grey) / `STALE >45d` (amber outline). Clicking `DISPLAY_ONLY` expands the `blocking` list verbatim (`["dsr 0.91<0.95", "harmful-in-a-regime"]`) — we *show why it failed*, which no vendor does.
- **The honest-accounting strip** — expectancy, profit-factor, hit, payoff, MaxDD-of-following, N. Hit-rate is present but visually subordinate to expectancy, with a tooltip: "hit-rate alone is what vendors publish; expectancy is what determines P&L."
- **DSR / PBO / CPCV-sign** with `n_trials` (from the ledger, not a caller literal) shown inline — "DSR 0.96 at N=30 trials (Trial-Ledger counted)."
- **Sharpe as a CI, not a point** — `[lo, mid, hi]` from `block_bootstrap_ci`, rendered as a range bar. A single Sharpe number is itself a form of theater.
- **Regime × VIX heat table** (B.4) — the 4×3 grid, greyed where `n<30`.
- **Calibration reliability** — for probability-emitting signals, a 10-bin reliability diagram (`brier_reliability`) + Platt `a`; flag over-confident bins (the recon caught the BTC meta-label predicting 0.935 where realized was 0.655 — that exact failure must be visible).
- **Decay sparkline** — rolling rank-IC / DSR over time from the append-only JSONL (`strategy_ledger.jsonl`), so the user watches an edge erode in real time instead of trusting a frozen number.

Header banner (bilingual, matching the `t()`/`td()` i18n convention): *"Every number on this page is machine-recomputed each build from point-in-time data and deflated for the number of strategies we tried. Nothing here is a hand-typed backtest figure. A strategy sizes the book only after clearing Deflated-Sharpe ≥ 0.95, PBO ≤ 0.50, and non-harmful in all regime/VIX cells."* This is the sentence Hedgeye cannot write.

---

### B.9 Daily decay monitor + the contract gate's proper scope

- **New `scripts/monitor_signal_ic.py`** (effort **M**, priority **P0**, deps: `engine/drift.py:rolling_ic_drift()` already exists and is already wired into `promotion_gate.py`): for every `SCORED` strategy, compute rolling 63d rank-IC on the live universe, feed `rolling_ic_drift(threshold=0.05, delta=0.005)`, write `data/quality/signal_ic_monitor.json`, and fire a `PushNotification` if any `SCORED` strategy flips `drift_flag`. Wire as a `daily.yml` step. The SUE demotion must never again require a human to notice.
- **Auto-demotion:** if a `SCORED` strategy's rolling IC drops below the gate threshold for `N=8` consecutive quarters (or `drift_flag` persists 21 sessions), the monitor writes `state=DISPLAY_ONLY` to the ledger automatically — the firewall then zeroes its allocation on the next build. Demotion is mechanical; promotion still requires a full gate pass (asymmetric on purpose — cheap to protect capital, expensive to risk it).
- **`scripts/validate_signals.py` stays as-is** — it is a *contract* gate (JSON shape, marker ordering, quality-field placement) and correctly belongs in `daily.yml` after `build_signal_quality.py`. It is orthogonal to and complementary with the new *validity* gate (`validation_gate.py`). Do not conflate them: one guarantees the render won't break, the other guarantees the recommendation is earned.

---

### B.10 Implementation order (dependency-correct)

| # | Item | File(s) | Effort | Priority |
|---|---|---|---|---|
| 1 | `signal_accounting()` + `maxdd_following()` | `engine/validation.py` | S | P0 |
| 2 | `validation_gate.py` (`StrategyEvidence`, `admit`, thresholds) | new | M | P0 |
| 3 | `strategy_ledger.jsonl` + `.json` writers; `admit()` appends | in #2 | S | P0 |
| 4 | Regime×VIX breakout | `scripts/validate_regime_vix_breakout.py` | M | P0 |
| 5 | PIT helper + `require_pit` enforcement | `lib/pit.py`, `collectors/*` tags | M | P0 |
| 6 | `signal_lab.build_scorecard()` reads ledger, not literals | `engine/signal_lab.py` | M | P0 |
| 7 | Firewall lint (scored paths must check ledger) | `tests/test_scored_reads_gate.py` | S | P0 |
| 8 | Daily IC-decay monitor + auto-demote | `scripts/monitor_signal_ic.py` + `daily.yml` | M | P0 |
| 9 | L3 EV acceptance gate (7-condition, thin-cell fallback) | consumes #2, #4 | L | P0 (precondition) |
| 10 | Generalize triple-barrier + meta-labeling off BTC | `engine/meta_label.py`, `engine/signal_gate.py` | L | P1 |
| 11 | Upgraded `signal_lab.html` panel | `templates/signal_lab.html.j2` | M | P1 |
| 12 | De-biased factor scorecard as live default | `scripts/factor_ic_scorecard.py --debiased` | M | P1 |
| 13 | OOS-R²/Clark-West mandatory for return-forecast signals | wire `validation.py:oos_r2`/`clark_west` | S | P2 |

**The one non-negotiable:** items 1–7 ship as a unit. Until the firewall lint (#7) passes and the gate ledger (#2, #3, #6) is the authoritative source for every displayed number, we have primitives without a spine. After it passes, the claim "institutional quality" is *auditable*: every recommendation on the site traces to a machine record showing its Deflated Sharpe, its PBO, its regime breakout, and its point-in-time provenance — the exact accounting Hedgeye replaces with a 36%-positive headline.
## C. The Volatility Complex + Mechanical-Flow Layer (Layers 4-5)

This is where the dashboard's single most-cited product concept — a "Risk Range" forward band — gets rebuilt from a heuristic into a measured, coverage-tested object, and where the fastest orthogonal alpha (front-running mechanical flows) gets built for the first time. The current vol stack is architecturally honest (validate-first firewall, causal windows, forward-outcome logs) but covers roughly **2.5 of the 6 vol-surface dimensions**, runs its physical-vol leg on **close-to-close returns only**, and has **zero** of the four L5 mechanical-flow signals wired to anything.

### C.0 — Ground truth (verified against the tree, not the recon)

Before any spec, five facts I confirmed by reading the files, because they change the plan:

1. **`data/yahoo/*.parquet` for the macro indices (SPY, sector ETFs) store `close` + `volume` ONLY.** No OHLC. `engine/vol_forecast.py:realized_vol()` and `engine/vol_regime.py` line ~174 both use `close.pct_change().rolling().std()`. Yang-Zhang is **impossible today** for the macro book without a collector change.
2. **The Yahoo collector already fetches HLCV** for the "volatility group" (`collectors/yahoo.py:54`, `want = ["High","Low","Close","Volume"]`) and **`yf.download(auto_adjust=True)` returns Open** — the collector drops it at the `want`-filter. So full OHLC (incl. Open) for SPY + sector ETFs is a **one-line collector change**, near-zero cost.
3. **`data/stocks/*.parquet` (223 US single names) already have `high, low, close, volume`** — but **no `open`**. So single-name realized vol can use Garman-Klass/Rogers-Satchell today; full Yang-Zhang needs Open added there too.
4. **`data/vol_regime/gate.json` does NOT exist.** Only `basket_overlay_gate.json` (asof 2026-06-21): `live_overlay_helps=false`, `scored_marginal=false`, `dsr=0.9943`, but `live_dd_reduction_pp=10.3` with CI `[10.3, 18.9, 30.5]`. **The scored composite is null in production; only the mechanical vol-target scalar acts.** The DSR of 0.9943 is suspiciously near 1.0 — consistent with the physical VRP leg being noisy close-to-close, killing incremental edge.
5. **`data/cboe/gex.parquet` has only 20 rows** (2026-06-10 → 06-30), columns `[net_gex_bn, flip_strike, spot, spot_vs_flip_pct]` — **no `rr_25d`, no `iv30`**. `data/polygon_gex/chains/` is **16 days deep**. There is **no time series of the vol surface**; it is rebuilt daily and thrown away. Any IV-surface, skew-change, or dispersion signal is blocked on persistence, not math.

The through-line: **L4 is blocked on close-to-close vol + non-persisted surface; L5 doesn't exist. Both are cheap to unblock.**

---

### C.1 — L4.1: Yang-Zhang OHLC realized vol (the physical leg fix)

**Problem.** The VRP physical leg (`VIX − cone_vol_ann(SPY)`) uses close-to-close RV. Close-to-close throws away the overnight gap and the intraday range — the two components that carry independent information — and is the noisiest of all standard estimators. In gap-open regimes it *understates* realized vol (VRP looks too high → false risk-on); in quiet-intraday sessions it *overstates* VRP. This noise is the most likely reason `scored_marginal=false`.

**Data prerequisite (P0, do FIRST).** In `collectors/yahoo.py:54`, add SPY + the 11 SPDR sector ETFs (and IWM, QQQ, HYG, TLT, GLD) to the `ohlc` set and add `"Open"` to the `want` list so the store persists `open, high, low, close, volume`. Backfill is free — `yf.download(period="max")` returns full OHLC history. **Flag: this is adjusted OHLC** (auto_adjust=True → dividend/split-adjusted). Yang-Zhang assumes the O/H/L/C are consistently adjusted; auto_adjust satisfies this. Do NOT mix adjusted close with raw high/low.

**Math.** Add to `engine/vol_forecast.py`:

```
def yang_zhang(o, h, l, c, win, trading_year=252):
    # log components
    co = np.log(o / c.shift(1))          # overnight (close-to-open)
    oc = np.log(c / o)                   # intraday (open-to-close)
    rs = np.log(h/c)*np.log(h/o) + np.log(l/c)*np.log(l/o)   # Rogers-Satchell
    n  = win
    k  = 0.34 / (1.34 + (n + 1) / (n - 1))
    v_o  = co.rolling(n).var(ddof=1)     # overnight variance
    v_oc = oc.rolling(n).var(ddof=1)     # open-to-close variance
    v_rs = rs.rolling(n).mean()          # RS is already a variance estimator
    yz   = v_o + k * v_oc + (1 - k) * v_rs
    return np.sqrt(yz.clip(lower=0)) * np.sqrt(trading_year)   # annualized
```

Yang-Zhang is minimum-variance among drift-independent, opening-jump-robust estimators — its efficiency is ~7–14× close-to-close for daily data. Rogers-Satchell is the drift-robust intraday core; the `k`-weighted blend of overnight + RS is the YZ construction.

**Wire.** In `vol_regime.py`, replace `realized_vol(sp, 21)` (the VRP physical leg *and* the vol-target denominator `rv_ann`) with `yang_zhang(o,h,l,c, cf["realized_window_d"])`, falling back to close-to-close when OHLC is absent (backward-compat for series still close-only). Update `vol_forecast.har_vol` to accept OHLC and build the HAR predictor set from YZ RV instead of close-to-close.

**Design choice — YZ vs Garman-Klass.** GK is simpler and needs no Open, but it assumes zero overnight jump and zero drift — false for equity indices with large overnight moves (the exact regime we care about). **Recommendation: Yang-Zhang for anything with Open (macro book after the collector fix); Rogers-Satchell for the single-name book until Open is added there.** Do not use Parkinson (range-only) — it ignores the overnight gap that dominates crisis vol.

- **Files:** `collectors/yahoo.py` (add OHLC), `engine/vol_forecast.py` (add `yang_zhang`, YZ-aware `har_vol`), `engine/vol_regime.py` (swap the two RV call sites), `engine/froth_fragility.py` (`_rho_dispersion` uses close RV — upgrade to YZ σ̄).
- **Effort:** S (math is ~15 lines; collector change is 1 line; backfill is free).
- **Priority:** **P0.** Everything downstream (VRP, cone width, vol-target sizing, dispersion) improves at once, and it unblocks C.2.

---

### C.2 — L4.2: Fitted HAR-RV + GARCH forward vol (replace the equal-weight blend)

**Problem.** `cone_vol_ann` is an **equal-weight mean of RV at lags (2,5,22,66)** with the docstring admitting "without a fitted regression (equal-scale blend)." There are no coefficients. This is not HAR-RV — it is a 4-point moving-average of RV. Corsi's actual HAR-RV fits OLS weights on daily/weekly/monthly RV and is the workhorse forward-vol model; the equal-weight version leaves R² on the table and — worse — the recon's claim that "the Phase-0 harness reports its forward-RV R²" appears **aspirational** (no harness output exists for `vol_forecast` itself).

**Math — fitted HAR-RV (Corsi 2009), expanding-window OLS.** On log-RV (YZ from C.1):

```
RV_d(t) = YZ(t)                          # 1-day
RV_w(t) = mean(YZ[t-4 : t])              # weekly
RV_m(t) = mean(YZ[t-21 : t])             # monthly
# target: forward h-day realized vol (h in {5,21,63})
y(t+h)  = mean(YZ[t+1 : t+h])
# fit  log y = β0 + βd·log RV_d + βw·log RV_w + βm·log RV_m
```

Fit on a **rolling 5-year expanding window, refit weekly**, log-space (RV is right-skew; log stabilizes and prevents negative forecasts). Persist `β` to `data/vol_regime/har_weights.json` keyed by `(asof, horizon)`. Add `har_vol_fitted(ohlc, weights_path, horizon)`; equal-weight remains the fallback when weights are absent (cold start).

**GARCH layer (for the tail / uncertainty band, not the point).** HAR-RV gives the *conditional mean* of forward vol. For the forward *range* (C.4) you need the *distribution* of returns, which requires the vol-of-vol and fat tails HAR alone misses. Fit a **GJR-GARCH(1,1) with skewed-t innovations** (`arch` package — confirm it's installed; it's a standard dep for vol work) on SPY daily returns, expanding, refit weekly. GJR captures the leverage asymmetry (down-moves raise vol more); skewed-t captures the left-tail. Output the h-step conditional vol forecast + the standardized-residual quantiles.

**Design choice — HAR vs GARCH as the point forecast.** HAR-RV on high-quality RV (YZ) beats GARCH-on-returns for the *point* forecast of realized vol at 5–63d horizons in most published horse-races (RV carries more information than squared daily returns). GARCH wins on *tail/distribution*. **Recommendation: HAR-RV(YZ) for the point (cone center + width), GJR-skewed-t GARCH for the conditional quantiles (cone shape/asymmetry). Do not pick one — they answer different questions.** Blend: cone center = HAR-RV point; cone left/right widths = HAR-RV × GARCH quantile ratios.

**Validation.** In `scripts/validate_vol_regime.py`, add `_fit_har_weights` + report **out-of-sample forward-RV R²** (Mincer-Zarnowitz) and **Clark-West** vs the equal-weight benchmark and vs a random-walk (`RV_forward ≈ RV_trailing`) benchmark. Promote fitted weights only if OOS R² beats both at HAC t > 2.

- **Files:** `engine/vol_forecast.py` (`har_vol_fitted`, GARCH wrapper), `scripts/validate_vol_regime.py` (fit + score), new `data/vol_regime/har_weights.json`.
- **Effort:** M (HAR is numpy-only OLS; GARCH is `arch` boilerplate).
- **Deps:** C.1 (YZ RV as the input), `arch` package.
- **Priority:** **P1.**

---

### C.3 — L4.3: Promote the vol_regime composite to scored (procedural, high-leverage)

**Problem.** The scored composite is dead in production (`gate.json` absent). The gate infrastructure is complete (`vol_regime.py:270-328`); the only blocker is (a) the noisy close-to-close VRP leg and (b) the deliberate human `--write-gate` step. `basket_overlay_gate.json` already shows `live_dd_reduction_pp=10.3` with a CI whose **lower bound is +10.3pp** — i.e. the overlay *is* cutting drawdown, but `scored_marginal=false` says the *scored deepener* adds nothing beyond mechanical vol-target.

**Spec.** After C.1 (YZ) and C.2 (fitted HAR) land, re-run `python -m scripts.validate_vol_regime --write-gate`. The hypothesis: cleaner VRP (YZ physical leg) will let `ts_slope` and/or `move` clear HAC t > 2.5 on forward-vol predictability. If either clears, a **separate reviewed PR** calls `--write-gate` to open the scored deepener channel. Keep `vrp` gate-closed unless YZ specifically rescues it — the recon is right that SKEW-as-timer and VRP-as-timer are perverse at the wrong sign.

**Trade-off / recommendation.** Do NOT force-open the gate to "use the code you built." The firewall is the crown jewel of this stack's honesty. **Recommendation: open only legs that clear the HAC bar post-YZ; if none clear, publish the negative result and leave the mechanical vol-target as the sole live lever.** A gate that stays shut on honest evidence is a feature.

- **Files:** `scripts/validate_vol_regime.py` (re-run), new `data/vol_regime/gate.json` (only if a leg clears).
- **Effort:** S (procedural; the code exists).
- **Deps:** C.1, C.2, human review.
- **Priority:** **P0** (it's the money channel; but gated on C.1/C.2 landing first).

---

### C.4 — L4.4: The forward range as a conditional-quantile forecast with MEASURABLE coverage

This is the honest rebuild of the Hedgeye "Risk Range." Everything above feeds it.

**Problem.** Today's cone (`engine/forward_dist.multi_horizon_cone`, `anticipation.py`) is either (a) an empirical quantile lookup on a state band, or (b) `HAR_vol × sqrt(h)` Gaussian scaling. Neither is coverage-tested. Gaussian √t scaling ignores vol-of-vol and jumps at short horizons and is symmetric — wrong for equities (left tail fatter). No Christoffersen / Kupiec coverage test exists anywhere in the vol stack.

**Math — two-track, pick per horizon.**

- **Track A (parametric, GARCH-driven):** forward h-day return quantile `q_τ(t,h) = μ_h + σ_h(t) · F⁻¹_skt(τ)` where `σ_h(t)` is the GJR-GARCH h-step conditional vol from C.2 and `F⁻¹_skt` is the fitted skewed-t inverse CDF (Hansen 1994 parameterization → asymmetric left/right widths for free). `μ_h ≈ 0` at daily-to-monthly horizons (drift is unforecastable; do not pretend otherwise).
- **Track B (semi-parametric, quantile regression):** fit `QuantReg(fwd_h_return ~ har_rv_forecast + regime_confidence + vrp_pctile)` at τ ∈ {0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95} (`sklearn.QuantileRegressor`, pinball loss, rolling 5y). This lets the *band width* respond to regime state, not just vol level.

**Coverage — the mandatory gate.** Compute, on a rolling 252d OOS window:
- **Unconditional coverage (Kupiec POF):** fraction of realized fwd-h returns inside `[q_0.10, q_0.90]` should be ≈ 0.80. LR test.
- **Conditional coverage (Christoffersen):** independence of exceedances (no clustering of breaches — a cone that breaches in clusters is mis-specified even if the average is right). Joint LR.
- **Pinball loss** vs a Gaussian-√t benchmark and an empirical-quantile benchmark.

Persist to `data/vol_regime/cone_coverage.json` and **flag the cone `miscalibrated=true` in the output JSON when 80% interval coverage falls outside [0.72, 0.88] or Christoffersen p<0.05.** The UI must show the *measured* coverage number next to the band ("80% band, realized coverage 78% over trailing 252d"), not an unverified claim.

**Gate by P(regime transition) — the Hedgeye "widen when transitioning" rule.** When `P(regime transition in next h days) > threshold` (from Section B's Markov-switching model — this is a hard cross-dependency), **widen the band and down-weight mean-reversion**: multiply the quantile spread by `(1 + λ · P_trans)` with λ≈0.5, and disable any mean-reversion tilt in the cone center. Rationale: at regime breaks the conditional distribution's variance and skew jump; a stationary quantile model under-covers exactly when it matters. If Section B's HMM isn't built yet, use a proxy: `P_trans ≈ transition_state ∈ {WEAKENING, TRANSITIONING}` from `engine/transition.py` mapped to {0.3, 0.6}.

**Design choice — Track A vs B.** **Recommendation: Track A (GARCH-skewed-t) as the primary cone because it gives a coherent, coverage-testable, asymmetric distribution with no lookup-table sparsity; Track B (quantile-reg) as a regime-conditional width modifier layered on top.** Pure empirical-quantile lookup (current) fails at exactly the sparse cells (crisis states with n<40) where you most need the band — that's the worst possible failure mode for real money.

- **Files:** new `engine/vol_cone.py` (Track A + coverage tests), extend `engine/forward_dist.py` (replace `multi_horizon_cone` internals), `scripts/validate_anticipation.py` (coverage harness), new `data/vol_regime/cone_coverage.json`. Template: replace the heuristic cone render with the measured band + coverage chip.
- **Effort:** L.
- **Deps:** C.1, C.2, and **Section B's P(regime transition)** (soft — degrade to transition_state proxy if absent).
- **Priority:** **P1** (this is the flagship deliverable; but it's only honest once C.1/C.2 land).

---

### C.5 — L4.5: The IV surface (the missing 3.5 dimensions) — blocked on PERSISTENCE, not math

The system computes IV30, front-expiry 25Δ risk-reversal, and a per-strike smile *on each build and discards them*. There is **no time series**, so nothing can be percentiled, and skew-*change* (the actionable signal) is unavailable. Map to Hedgeye's 6 surface dims:

| Dim | Status today | Fix |
|---|---|---|
| Level (VIX/DVOL) | ✅ used | — |
| IV-RV premium (VRP) | ⚠️ close-to-close physical | C.1 fixes |
| 25Δ skew | ⚠️ computed, not persisted | C.5.1 |
| Term slope | ⚠️ VIX/VIX3M only (2 pts) | C.5.2 |
| Skew term-structure | ❌ absent | C.5.1 (multi-tenor) |
| Dispersion (index vs single-name IV) | ❌ absent (price-dispersion only) | C.5.3 |

**C.5.1 — Persist the surface daily (P0, unblocks everything else).** In `collectors/cboe.py:GexAdapter._row()`, add to the 1-row/day keep tuple: `iv30, iv60, iv90` (linear-interp ATM IV at 30/60/90 calendar days from the chain), `rr_25d` (already computed in `gex_model.risk_reversal_25d` — just pass through), `skew_10d` (10Δ put IV − ATM), and `oi_pc_ratio`. This is a **~5-line change** that starts the time series accruing. `rr_change = rr_25d(t) − rr_25d(t−1)` becomes reliably available in `gex_confirm.py` by reading the parquet tail instead of requiring two in-process build passes. **Without this, no skew signal is possible; with it, the signal accrues from day 1.**

**C.5.2 — Multi-tenor VRP + term slope.** With `iv30/60/90` persisted, compute `iv_rv_premium_N = iv_N − yang_zhang(SPY, N)` per tenor and a fitted term slope (`iv90 − iv30` scaled). Add the 3-tenor VRP block to `vol_regime.build_frame` (equal-weight mean, replacing the single scalar VRP). This is a genuine curve vs the current 2-point VIX/VIX3M.

**C.5.3 — IV dispersion (the vol-selling-complex fragility signal).** This is the cleanest mechanical signal in the literature and is **absent**: `froth_fragility._rho_dispersion` computes *price* dispersion (Solnik correlation among mega-caps), not *implied* dispersion. Add `_f_iv_dispersion` to `vol_shock_scorecard.py`:

```
iv_dispersion = mean(ATM_30d_IV over single-name underlyings) / VIX
# > 1 normally; compression toward 1.0 = correlation-spike / crash-vol risk
sub_score = clip((1 - pctile_252d(iv_dispersion)) * 100)
```

**Blocker (state it plainly):** `data/polygon_gex/chains/` is **16 days deep** and covers ~10 mega-caps. IV dispersion needs ≥30 trading days and ≥15 underlyings to percentile. **Flag as young/display-only until coverage matures; do NOT score it before ~30 dates.** The fix is *persistence + patience*, not code. Add weight=0.6 in `vol_shock_scorecard` DEFAULTS but gate to display until `n_dates ≥ 30 AND n_underlyings ≥ 15`.

**Point-in-time note:** all IV data is EOD, 15-min-delayed on the Polygon Standard plan (per `live_data_polygon_standard` memory). The causal z-score windows already respect this; the only PIT hazard is if a build re-reads a *revised* chain snapshot — persist snapshots immutably (write-once by date) to prevent look-ahead.

- **Files:** `collectors/cboe.py` (persist surface — P0), `engine/vol_regime.py` (multi-tenor VRP), `engine/vol_shock_scorecard.py` (`_f_iv_dispersion`), `engine/gex_confirm.py` (reliable `rr_change`).
- **Effort:** S for C.5.1 (persistence), M for C.5.2/C.5.3.
- **Priority:** **P0 for C.5.1** (start accruing the series *now* — every day of delay is a lost day of history), P2 for the scored consumers (gated on coverage).

---

### C.6 — L5.1: Vol-control roll-off schedule (the fastest orthogonal alpha)

**This is the single highest-value new build in the section and it does not exist.** Vol-target funds (risk-parity, vol-control annuities, managed-vol) mechanically rebalance to a target vol using a trailing window. When a **high-vol day ages out of the trailing window**, measured trailing vol drops, the target/vol ratio rises, and they **mechanically buy** — regardless of price, news, or fundamentals. This is deterministic and knowable *days in advance* because you know exactly which historical day will exit the window and when.

**Math.** New `engine/vol_control.py`:

```
def rolloff_schedule(ret, win=21, target_vol=0.10, aum_bn=500):
    rv_now      = ret.rolling(win).std() * sqrt(252)
    rv_dropmax  = ret.rolling(win).apply(lambda w: std(sort(w)[:-1]))*sqrt(252)  # window minus its worst day
    # mechanical buy pressure when the worst day is about to exit
    mech_buy    = (target_vol/rv_dropmax) - (target_vol/rv_now)   # Δ exposure fraction
    est_notional_bn = mech_buy * aum_bn
    # days until the current max-vol day exits the trailing window:
    days_to_exit = win - (t - argmax(|ret[t-win:t]|))
    return dict(mech_buy_signal = rv_now >= target_vol,
                days_to_exit    = days_to_exit,
                est_buy_bn      = est_notional_bn)
```

`days_to_exit < 5` **and** recent vol high ⇒ imminent mechanical bid. This is PIT by construction (uses only `ret[t-win:t]`).

**Wire.** Add as a scored `vol_control` leg (weight 0.6 — the most mechanical and fastest of all L5 flows) in `vol_shock_scorecard.py`, and as a Tier-B escalator in `risk_radar.py` adjacent to the currently-INERT `vol_putcall`/`vol_gex` legs. Keep INERT/display until the Opus loop or a forward log validates a positive hit-rate — but the signal is so mechanical (it's arithmetic on the fund's own rule) that it should validate fast.

**AUM assumption — the one soft parameter.** `aum_bn` (total vol-target AUM front-running SPX) is unobservable; estimates range $200–800bn. Make it config-overridable and report the signal as a *z-score of mech_buy* (scale-free) rather than a dollar figure for scoring — the *timing* (days_to_exit) is exact even if the *magnitude* is fuzzy.

- **Files:** new `engine/vol_control.py`, `engine/vol_shock_scorecard.py` (new leg), `engine/risk_radar.py` (Tier-B escalator).
- **Effort:** M.
- **Deps:** SPY closes (already in store); C.1 YZ improves the RV estimate but close-to-close is acceptable here since it's a *relative* age-out signal.
- **Priority:** **P0.** Fastest orthogonal alpha, cheap, PIT-clean, and currently a total gap.

---

### C.7 — L5.2: CTA trend-flip levels

**Problem.** Systematic CTAs flip long↔short at momentum-lookback thresholds; when spot crosses these, they mechanically reverse — estimated >90% of some days' volume. **Not computed anywhere.** No equity-index COT is even collected (`collectors/cot.py` covers commodities/FX/BTC, not E-mini).

**Math.** New `engine/cta_positioning.py`:

```
for L in (20, 50, 100, 200):
    sig[L] = sign(close - close.shift(L))         # per-lookback trend signal
flip_level[L] = close.shift(L)                    # price at which sig[L] flips
exposure   = weighted_mean(sig[L])                # net CTA lean, [-1, +1]
dist_to_nearest_flip_pct = min over L of |close - flip_level[L]| / close
regime = "all_long" if all sig>0 else "all_short" if all sig<0 else "mixed"
```

Flag `cta_flip_pending` when `dist_to_nearest_flip_pct < 1%`. **Cross-check with real positioning:** add **CME E-mini S&P (CFTC code 13874+) and E-mini NASDAQ (20974+)** to the `cot.py` markets config — the 1995+ Socrata history is **free**. Use the COT net-spec %OI z-score as an independent validator of the theoretical exposure curve; divergence (theory says all-long, COT says spec already max-long) = exhaustion.

- **Files:** new `engine/cta_positioning.py`, `collectors/cot.py` + `config.yml` (add equity_futures markets), `engine/vol_shock_scorecard.py` (`cta_flip` leg, weight 0.7), `engine/gex_confirm.py` (context note when spot within 1% of 50d flip).
- **Effort:** S for E-mini COT, M for the CTA model.
- **Priority:** **P1.**

---

### C.8 — L5.3: Dealer gamma-flip level (mostly built — fix the gating inconsistency)

**Status.** Best-developed L5 signal. `gex_engine.py`/`gex_model.py` compute the gamma-flip via a ±25% spot grid (101 pts), magnet strikes, charm anchor. `market_gamma.py` gives the whole-market regime. This is genuinely good.

**Two fixes, not a rebuild:**

**C.8.1 — Continuous P(gamma regime flip) (P1).** Today the regime is a discrete argmax (long/short gamma) with `dist_to_flip_pct` computed but **not used in scoring**. Add an analytic crossing probability:

```
P_flip_Nd = 2 * Φ( -|dist_to_flip_pct| / (daily_vol_pct * sqrt(N)) )   # Brownian first-passage, drift 0
```

with `daily_vol_pct` from C.1 YZ. Surface `p_flip_5d`; in `gex_confirm.assess()` widen OPEX suppression to any day with `p_flip_5d > 0.35`; down-weight the dealer-gamma regime read in `vol_shock` when the flip is imminent (the regime label is unreliable near the boundary). This is the L2 "transition probability" idea applied cheaply at the gamma level without an HMM.

**C.8.2 — Resolve the validate-before-weight VIOLATION (P0).** `scripts/validate_gex.py` exists (MIN_PER_BUCKET=30, forward-accumulating), but **`stock_score.py:563` already uses GEX at weight 0.10 in `_risk_idio` and ±0.3 in `_axis_entry` before the gate has passed.** This violates the repo's own doctrine. **Decision required, do not leave both active:** either (a) run `validate_gex.py`; if short-gamma days precede higher RV at 5d/10d with bootstrap 95% CI excluding 0, write `gex_gate.json scored=true` and keep the usage; or (b) if it fails, **remove GEX from the scored `stock_score` paths** and make it display-only. **Recommendation: run the gate; the dealer-sign convention (long-call/short-put) is an unverified assumption, so I'd bias toward demoting to display until `options_flow.measured_dealer` (real signed flow) can replace the assumed sign — but the empirical RV-lift gate is the honest arbiter.**

- **Files:** `engine/gex_engine.py` (`regime_probability`), `engine/gex_confirm.py`, `scripts/validate_gex.py` (run), `engine/stock_score.py` (gate or demote), new `data/vol_regime/gex_gate.json`.
- **Effort:** S.
- **Priority:** **P0 for C.8.2** (it's a live doctrine violation on a real-money score), P1 for C.8.1.

---

### C.9 — L5.4: Positioning extremes (COT z, put/call, ETF create/redeem)

**COT z-scores:** delivered by C.7's E-mini addition — surface net-spec %OI percentile (rolling 252d) as a positioning-extreme leg in `conditions.py` risk_appetite and `vol_shock`.

**Put/call — the young-series problem:** the official CBOE market-stats CSV went behind a SPA in 2025/26; the current proxy (SPX+SPY+QQQ+IWM volume) only accrues forward. `_FLOW_MIN_HISTORY=252` guards exist. **Do not score put/call until 252 rows accrue; display only.** The E-mini COT is a better positioning signal in the interim precisely because it has 30 years of history.

**ETF create/redeem (P2, new source):** new `collectors/etf_flows.py` — Polygon `/v2/reference/financials` shares-outstanding change as a create/redeem proxy for the 11 SPDR sectors + 4 factor ETFs (MTUM/QUAL/USMV/VLUE). Weekly Δshares-outstanding as % of trailing average → z-score → flow-demand context chip. Do NOT score (new source, unvalidated). This is the only genuinely new data dependency in the section and the lowest priority.

- **Files:** `collectors/cot.py` (done in C.7), `engine/conditions.py`, new `collectors/etf_flows.py`.
- **Effort:** S (COT/putcall), L (ETF flows).
- **Priority:** P1 (COT), P2 (ETF flows).

---

### C.10 — L6 honesty for the vol/flow layer (do not skip)

The `vol_shock_scorecard` forward log (`append/resolve/track_record`) is the most complete validation loop in the subsystem but reports **hit-rate only** — no expectancy, no profit-factor, no PBO. Add to `track_record()`:

```
expectancy    = mean(mae|hit)*hit_rate + mean(mae|miss)*(1-hit_rate)
profit_factor = sum(|mae| hits) / sum(|mae| misses)
pbo           = combinatorial-symmetric-CV overfit prob on the band thresholds (≥30 matured rows)
```

Every new scored leg in this section (vol_control, cta_flip, iv_dispersion, gamma p_flip) must pass through `validate_vol_regime.py` / `validate_gex.py` with **HAC t > 2.5 on purged K-fold (embargo = horizon) AND DSR p < 0.10** before it moves money. **Win-rate is theater; expectancy is the number.**

- **Files:** `engine/vol_shock_scorecard.py` (`track_record` expectancy/PF/PBO), `scripts/validate_vol_regime.py`, `scripts/validate_gex.py`.
- **Effort:** S.
- **Priority:** **P0** (it's the gate every other item in this section flows through).

---

### C.11 — Build order (dependency-sorted, so nothing is blocked on itself)

| # | Item | Layer | Eff | Pri | Blocks |
|---|---|---|---|---|---|
| 1 | Add OHLC to yahoo collector + backfill | L4 | S | **P0** | 2,3,4,6 |
| 2 | Persist IV surface daily (`rr_25d, iv30/60/90`) in `cboe.py` | L4 | S | **P0** | C.5.2/.3, skew-change |
| 3 | Vol-control roll-off schedule (`vol_control.py`) | L5 | M | **P0** | — |
| 4 | Resolve GEX validate-before-weight violation | L5/L6 | S | **P0** | — |
| 5 | Expectancy/PF/PBO in vol_shock track_record | L6 | S | **P0** | all scored legs |
| 6 | Yang-Zhang RV → VRP + vol-target denominator | L4 | S | **P0** | 7,8,9 |
| 7 | Fitted HAR-RV + GJR-skewed-t GARCH | L4 | M | **P1** | 9 |
| 8 | E-mini COT + CTA flip levels | L5 | S/M | **P1** | — |
| 9 | Conditional-quantile forward range + coverage tests | L4 | L | **P1** | Section B P(trans) |
| 10 | Re-run gate; promote scored composite if it clears | L4/L6 | S | **P0** | 6,7 |
| 11 | Gamma p_flip + multi-tenor VRP + IV dispersion | L4/L5 | M | **P2** | 2 (coverage) |
| 12 | ETF create/redeem flows | L5 | L | **P2** | — |

**The critical path is 1 → 6 → 7 → 9** (OHLC → YZ → fitted HAR/GARCH → coverage-tested cone). Ship **1, 2, 3, 4, 5 on day one** — they are all Small, all P0, all independent, and items 2 and 3 start accruing the two time series (IV surface, and the mechanical-flow forward log) that everything else in L5/L4.5 waits on. **Every day of delay on item 2 is a permanently lost day of vol-surface history you can never backfill.**

**One-line section verdict:** the vol stack's honesty scaffolding is excellent but it forecasts on close-to-close returns, never persists the surface it computes, runs a scored composite that's dead in production, and has none of the four mechanical-flow signals wired — fixing this is mostly *cheap plumbing* (add OHLC, persist the surface, compute the roll-off arithmetic) plus one genuinely hard build (the coverage-tested conditional-quantile cone), and it converts a heuristic "Risk Range" into a measured one and adds the fastest orthogonal alpha the system currently lacks entirely.
## D. Cross-Asset Lead-Lag + Portfolio Construction (Edge #2 + Layer 7)

This section specifies two engines that together deliver blueprint Edge #2 (USD North Star + rolling-correlation regime-break) and Layer 7 (drawdown-budgeted portfolio construction with a P(Quad)-driven gross/net dial). They are deliberately sequenced: the correlation-break detector is a **transition detector** whose output (a scalar `break_intensity` and a per-pair fracture map) feeds *both* the L2 regime-probability engine (Section B) as an exogenous transition-hazard covariate *and* the L7 gross dial as a de-risk multiplier. L7 sits at the very top of the stack and consumes L2's `P(Quad_k)` and L3's `mu_{a,k}` as inputs; it is the last thing that runs and the only thing that emits a position vector.

A note on ground truth from the recon: the recon's cross-asset upgrade proposals put `erc_weights` in `active_alloc.py`. **It is not there** — `erc_weights(cov, iters, tol, damp)` lives in `engine/portfolio.py:66` and is currently additive/display-only (written to `latest.json["portfolio"]`, imported by nothing in the scoring path). `active_alloc.py` has `vol_target_size` (`:65`) and `backtest_portfolio` (`:104`) but no risk-parity solver. Any spec that says "call `active_alloc.erc_weights`" is wrong; the L7 base must import from `portfolio.py`. This matters because it's the single biggest piece of already-built, already-damped, crypto-safe machinery we get to reuse for free.

---

### D.1 — USD North Star Lead-Lag + Rolling-Correlation Regime-Break Detector (Edge #2)

**The edge, stated precisely.** Hedgeye's second real edge is *not* "the dollar predicts everything." At daily frequency the dollar move usually *is* the same risk/tightening impulse (the `forex_transmission.py` docstring is correct and honest about this — do not undo that honesty). The actual edge is the **second-order signal**: when a *stable* cross-asset correlation structure **fractures** — a pair whose sign and magnitude held for months suddenly flips or decouples — that break is a leading transition warning, because it means the single risk factor that was pricing all assets has stopped being the marginal driver. The USD is the cleanest hub to watch this on because it is the master price for global liquidity. So we build two things: (1) a **directed lead-lag graph** (which already half-exists in `cross_asset.py`), hardened and made point-in-time honest; (2) a **correlation regime-break detector** — the genuinely missing piece — that fires on structural breaks in the USD↔asset rolling correlation.

#### D.1.a — What exists and what to reuse

- `engine/cross_asset.py:snapshot()` already computes: Kritzman-Page absorption ratio (`_absorption_ratio`, `:79`) with a 5y percentile, PC1 loadings/cluster, and — critically — a **HAC-t + BH-FDR lead-lag scanner** over lags `[1,2,3,5,10]d` on a 252d rolling window (`_cfg()` keys `ll_window_d`, `ll_lags`, `ll_hac_lags=10`, `ll_alpha=0.10`, `ll_min_abs_r=0.06`, `ll_top=8`). It even has a stability check (re-test top link in prior 252d, require `|t|≥2` and same sign). This is a solid foundation and is more rigorous than most retail imitations. **Reuse it wholesale.**
- `engine/forex_transmission.py:transmission()` (`:88`) computes fast(63d)/slow(252d) rolling beta + correlation of each asset return on broad-USD return, plus a calm-vs-stress `_regime_split` (`:75`) keyed on the dollar-smile risk-off composite. `_ret()` (`:52`) already handles the WTI-negative-price and yield-level (`-Δyield`) sign conventions. **Reuse `_ret` and `_beta_corr` (`:63`) verbatim.**
- `engine/validation.py` has `newey_west_tstat` (`:632`), `rank_ic` (`:622`), `block_bootstrap_ci` (`:402`), `deflated_sharpe` (`:218`) — the whole break-validation battery.

#### D.1.b — New engine: `engine/usd_corr_break.py` (the missing detector)

**Universe.** Reuse `forex_transmission._ASSET_META` hub set — SPY, EEM, GC=F, CL=F, HG=F, UST10 (as `-Δyield`), BTC — all against **broad-USD** (DTWEXBGS from FRED, not DX-Y.NYB — DXY is 58% EUR and misses the EM/CNH channel that carries the transition signal; DXY stays as a display fallback only). Recommendation: **broad-USD as the hub, no hedge.** Trade-off: broad-USD is published with a 1-day lag and revised; DXY is real-time and unrevised. For a *break detector* (which needs a clean structural series, not tick latency) the revision on DTWEXBGS is immaterial to the correlation sign — use it, and pull it point-in-time via ALFRED only for backtest honesty (below).

**Core math — the break statistic.** For each asset `a`, let `ρ_a(t)` be the rolling Pearson correlation of `r_a` to `r_USD` over a short window `w_s=63d`, and `ρ̄_a(t)` the long-baseline correlation over `w_l=252d`. Define three break signals, computed causally:

1. **Sign-flip / magnitude break (fast vs slow divergence):**
   `d_a(t) = ρ_a(t) − ρ̄_a(t)`. A break is *armed* when `|d_a(t)| > κ` (recommend `κ=0.35`) **and** persists ≥ `p=5` consecutive days **and** the sign of `ρ_a` differs from the sign of `ρ̄_a`, OR `|ρ_a|` collapses below `0.15` from a baseline `|ρ̄_a| > 0.45` (decoupling). This is the `forex_transmission` stability flag promoted from a display boolean to an armed event with a magnitude and a direction.

2. **Structural-break test (the rigorous leg):** run a **Bai-Perron / binary-segmentation single-break test** on the `ρ_a` series over the trailing 252d — or, cheaper and sufficient, a **rolling CUSUM of recursive residuals** on the regression `r_a = α + β·r_USD + ε` with a `w=126d` window. Fire `struct_break_a=True` when the standardized CUSUM crosses the 5% Brownian-bridge boundary `±0.948·√(1 + 2t/T)`. Rationale: the ρ-difference (signal 1) catches gradual drift; CUSUM catches a genuine parameter break in β even when the correlation magnitude is stable. **Recommendation: ship signal 1 (P0) first — it's O(n) and interpretable — and add CUSUM (P1) as the confirming leg.** Require *both* for the highest-confidence `NEW_BREAK` state.

3. **Absorption-shift confirmer (already have the input):** `cross_asset.snapshot()['absorption']['pctile']` rising sharply (Δ over 10d > 0.20) means "everything is becoming one bet" — a break *into* correlation. Falling sharply means a break *out of* correlation (diversification returning). Tag each fracture with `absorption_direction ∈ {converging, diverging}`.

**Aggregate output → `data/forex/usd_corr_break.json`:**
```
{
  "asof": "...",
  "break_count": int,                 # of hub assets in an armed break state
  "break_intensity": float in [0,1],  # = mean over assets of clip(|d_a|/0.6, 0, 1),
                                       #   gated to 0 unless armed (persistence+sign)
  "per_asset": { "SPY": {"rho_63": .., "rho_252": .., "d": .., "sign_flip": bool,
                         "struct_break": bool, "state": "STABLE|ARMED|NEW_BREAK",
                         "days_in_break": int}, ... },
  "absorption_direction": "converging|diverging|flat",
  "headline": "..."                    # bilingual, e.g. "SPY↔USD correlation flipped
                                       #  positive (2y baseline −0.55): risk+dollar
                                       #  falling together — a Q4/de-risk transition tell"
}
```

The **canonical transition signal** is `break_intensity` (continuous) plus `break_count` (discrete). The single most informative event historically: **SPY↔USD correlation flipping from its typical negative baseline to positive** (equities and the dollar falling *together*) — the "sell everything / dollar-as-haven" regime that precedes Q4 stress. Hard-code a named flag `dollar_haven_flip` when `ρ_SPY(t) > 0` while `ρ̄_SPY < −0.30`.

#### D.1.c — Directed lead-lag hardening (in `cross_asset.py`)

The existing scanner is undirected-ish and uses *revised* data. Two changes:

- **Point-in-time inputs (P1).** The lead-lag `mean(z_F(t)·z_L(t−k))` on macro-adjacent series (UST10, anything FRED-derived) is spuriously "predictive" under look-ahead because macro prints are revised. Add an `as_of` parameter to `returns_frame()` (`cross_asset.py:63`) that, when set, pulls FRED-sourced legs via an ALFRED vintage read (`lib/alfred.py`, shared with Section A/B) rather than latest revision. Pure-price legs (yahoo closes) are unrevised and unaffected. **This is the honest-backtest gate; the live path can stay latest-revision since same-day price co-movement is what's measured.**
- **Break-conditioned lead-lag (P2).** Split the lead-lag scan into two regimes — `break_intensity` high vs low — and report the top links per regime. The thesis (worth measuring, not asserting): USD→EM and USD→copper leads *lengthen and strengthen* precisely when the correlation structure is fracturing. If the split-sample HAC-t survives BH-FDR in both halves, that's a genuine conditional edge; if not, it's display-only. Do not wire it to sizing until it clears `deflated_sharpe` (Section D.2's gate).

#### D.1.d — Wiring the break signal into existing engines

1. **→ Section B L2 regime engine (primary consumer).** `break_intensity` becomes an **exogenous regressor in the Markov-switching transition** (the `regime_hmm.py` / `regime_ms.py` the other sections spec). Concretely: inflate the off-diagonal transition probabilities `P(Quad_j | Quad_i)` by a factor `(1 + λ·break_intensity)` (recommend `λ=1.0`, renormalize rows) so a fracturing correlation structure raises the modeled hazard of leaving the current quad. This is the mechanistically-correct place for it: a correlation break *is* evidence of regime transition, and the HMM should update its hazard accordingly.
2. **→ `engine/cross_asset_confirm.py` (display, immediate).** Add a caution flag: `"USD transmission fracturing — N of 6 hub correlations broke from 2y baseline"`, tagged **leading** (this is one of the few genuinely leading flags in that file — most are coincident). Include the `dollar_haven_flip` named alert with a red badge.
3. **→ L7 gross dial (Section D.2).** `break_intensity` is a direct multiplicative de-risk term on gross exposure (formula in D.2.e). This is the "cut before the print" behavior.
4. **→ macro-risk overlay (`conditions.py` MRS).** Replace the current binary `transition` MRS leg (`_mrs_weights`, `:693`; currently `TRANSITIONING=1.0/WEAKENING=0.5/else 0`) with `max(existing_transition_val, break_intensity)`. This removes a heuristic knob and makes the MRS transition leg proportional to a measured structural break. Effort here is trivial (one line in `_macro_risk_legs`, `:787`).

#### D.1.e — Validation (do not skip; real money)

- Label historical "regime transitions" as the ±10d window around confirmed Quad changes in `regime_history.parquet`. Compute **lift**: `P(transition within 21d | break_intensity in top decile) / base rate`. Target ≥ 1.5× with a permutation null (frequency-matched, 2000 draws), matching the `risk_radar_backtest` bar.
- Run **purged K-fold** (`validation.purged_folds`, embargo=21d) on the `break_intensity → forward transition` relationship; report `rank_ic` and Newey-West t.
- Compute **DSR** treating the "de-gross on break" rule as a return stream (`deflated_sharpe`, `validation.py:218`) with `n_trials` = number of `(κ, w_s, w_l, p)` combinations tried, sourced from the Trial Ledger (`ledger=`/`family=` path, NOT a literal). **Gate: the break signal may only touch the *gross dial* (subtract-only) if lift ≥ 1.5 AND DSR ≥ 0.90.** Until then it is a display-only caution flag. This is consistent with the repo's validate-before-weight doctrine.

| Item | Effort | Priority | Deps |
|---|---|---|---|
| `usd_corr_break.py` signal 1 (ρ-divergence + persistence + sign-flip) | M | **P0** | reuse `forex_transmission._ret/_beta_corr` |
| broad-USD (DTWEXBGS) collector + ALFRED vintage read | S | P0 | `lib/alfred.py` (shared) |
| CUSUM structural-break confirming leg | M | P1 | signal 1 |
| PIT `as_of` param on `cross_asset.returns_frame` | S | P1 | ALFRED |
| Wire `break_intensity` into HMM transition hazard | M | P1 | Section B HMM |
| MRS transition-leg replacement + `cross_asset_confirm` flag | S | P0 | signal 1 |
| Break-conditioned lead-lag split + DSR gate | L | P2 | HMM, Trial Ledger |

---

### D.2 — Layer 7: Drawdown-Budgeted Portfolio Construction (HRP + Black-Litterman + CVaR + P(Quad) Gross/Net Dial)

This is the layer retail imitators drop entirely. The current `masterminds.py` book is an *inverse-vol × conviction × vol-target* heuristic (`_weights`, `:216`) — a risk-parity *approximation*, not risk parity, with a **static** per-profile leverage cap (`PROFILES`, `:46`: conservative 7%/1.2x, moderate 12%/1.6x, aggressive 22%/2.5x) that never moves with the regime. We replace the weight construction with a principled 5-stage pipeline. **Critical design decision: build this as a NEW engine `engine/portfolio_l7.py` that produces an alternative weight matrix, run side-by-side with the existing `masterminds._weights` in the backtest harness, and only promote it if it beats the incumbent on DSR-adjusted Sharpe AND max-DD across both split halves.** Do not rip out `_weights` on faith. The existing `backtest_portfolio` (`active_alloc.py:104`), which correctly handles leverage financing (`gross-1` and short notional pay `bill+borrow_spread`), is the shared evaluator for both.

#### D.2.a — Stage 1: HRP base weights

Replace inverse-vol with **Hierarchical Risk Parity** (López de Prado 2016) over the 9-asset masterminds universe (SPY/QQQ, IEF/TLT, LQD/HYG, GC=F/HG=F, BTC-USD). HRP > naive risk parity here specifically because the universe has **strong block structure** (two equity legs, two duration legs, two credit legs) that a flat inverse-vol or even ERC ignores — HRP's quasi-diagonalization allocates *across* clusters first, so a single stacked bet (e.g. QQQ+SPY as "one equity bet") can't dominate. New function in `portfolio_l7.py`:

```
def hrp_weights(cov: np.ndarray, corr: np.ndarray) -> np.ndarray:
    # 1. dist = sqrt(0.5*(1-corr));  2. scipy.cluster.hierarchy.linkage(dist, 'single')
    # 3. quasi-diagonalize (recover leaf order);  4. recursive bisection:
    #    each split allocates inverse-variance-weighted between the two sub-clusters
    #    using cluster variance w_cluster' Σ w_cluster.
```
Covariance from a **126d trailing** window (matches `portfolio.py:_cfg` `window_d=126`), **Ledoit-Wolf shrunk** (`sklearn.covariance.LedoitWolf`) — the raw 126×9 sample covariance is rank-deficient-adjacent and HRP's cluster-variance step is sensitive to it. Trade-off vs ERC: HRP is not provably risk-equalizing and depends on the linkage choice. **Recommendation: HRP as the base, but keep `portfolio.erc_weights` (`:66`, already damped and crypto-safe) as a fallback and as a diagnostic — report both, size on HRP.** ERC's damped fixed point is battle-tested for the crypto leg; if HRP's recursive bisection ever produces a degenerate weight (>60% single asset), fall back to `erc_weights`.

#### D.2.b — Stage 2: Black-Litterman blend (L3 conditional-EV as views)

This is the return-alpha injection. The HRP weights are risk-structure-only (return-agnostic). Black-Litterman blends them with the **L3 regime-conditional expected-value** `E[r_a] = Σ_k P(Quad_k)·μ_{a,k}·intensity_k` (from Section C's `regime_ev.py` / the sector-EV engines) as *views*.

- **Prior (equilibrium) returns** via reverse optimization: `Π = δ·Σ·w_mkt`, where `w_mkt` = the HRP weights (using HRP as the neutral prior is the honest choice — we don't have true market-cap weights across a 9-asset cross-asset book, and cap-weighting BTC vs Treasuries is meaningless), `δ` = risk-aversion `≈ (E[r_mkt]−r_f)/σ²_mkt` (calibrate to ~2.5), `Σ` = the shrunk covariance.
- **Views**: `P = I` (absolute views, one per asset), `Q = E[r_a]` from L3. **View uncertainty `Ω` is the load-bearing choice and where retail BL implementations die.** Set `Ω = diag(P·(τΣ)·Pᵀ) / confidence_a`, where `confidence_a` scales with the L3 estimate's `n_obs_per_quad` and the current `regime_confidence` (a coin-flip regime → near-infinite Ω → view ignored → book collapses to HRP prior). **This is the correct behavior and the whole point:** when `P(Quad)` is diffuse (the live regime is `confidence=0.125`, per Section A), the conditional-EV views are down-weighted automatically and the book leans on HRP risk-structure. `τ ≈ 0.05`.
- **Posterior**: `E[r]_BL = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ · [(τΣ)⁻¹Π + PᵀΩ⁻¹Q]`. Then **one mean-variance step**: `w_BL = (δΣ)⁻¹·E[r]_BL`, normalized.

**Recommendation:** BL over naive "tilt HRP by conviction sign" (what `masterminds._conviction` does today) because BL's Ω mechanism gives you *principled, uncertainty-scaled* tilting for free — the conviction magnitude and the regime confidence both flow into position size through one coherent Bayesian update, instead of the current three separate ad-hoc clips (`W_TREND=0.45` etc. at `masterminds.py:72`). The masterminds 4-factor conviction (trend/carry/regime/xmom) does **not** disappear — it becomes an *additional* view block in `P`/`Q` (trend as a momentum view, carry as a carry view) with its own Ω, so the two systems merge cleanly rather than compete.

#### D.2.c — Stage 3: Vol-target overlay

Reuse the existing machinery. After BL produces target weights, scale the book so realized 63d portfolio vol hits the profile target (`prof["target_vol"]`), exactly as `masterminds._weights:230-231` does now:
`W = w_BL · clip(target_vol / port_vol_63d, 0, 3.0)`. No change needed — this stage already works.

#### D.2.d — Stage 4: CVaR drawdown-budget constraint

The missing hard risk gate. Vol-targeting controls *dispersion*, not *left-tail depth*; a fat-tailed book (crypto, credit) can hit its vol target and still blow the drawdown budget. Add a **CVaR@95 constraint** as a final scaling step:

- Estimate book CVaR@95 over a 252d window: `CVaR_95 = mean( book_ret | book_ret ≤ q_05 )`, where `book_ret` is the *historical* return of the current target weights (not a parametric normal — use the empirical left tail; the whole reason for CVaR over VaR is tail shape).
- Per-profile annualized DD budget: conservative `−8%`, moderate `−15%`, aggressive `−28%` (roughly `2.5×` the vol target — a fair rule of thumb for a diversified book's expected 1y max-DD). Convert to a 21d-horizon CVaR budget `cvar_budget = dd_budget · √(21/252)`.
- If `|CVaR_95_21d| > cvar_budget`, scale **all** weights by `cvar_budget / |CVaR_95_21d|` (uniform de-gross) *before* the leverage cap. This binds independently of vol-targeting and catches the case where vol is quiet but tails are fat.

**Recommendation:** empirical CVaR over a cvxpy LP-optimized CVaR (Rockafellar-Uryasev). The LP is "more correct" but adds a heavyweight solver dependency, is slow in the daily build, and its precision is illusory on 252 daily obs. A uniform de-gross to the CVaR budget is 95% of the benefit at 5% of the complexity and has no solver risk. Ship the scalar version (P1); the LP is a P3 "if we ever have intraday capacity" item.

#### D.2.e — Stage 5: P(Quad)-driven GROSS/NET dial (the piece retail drops)

Replace the **static** `prof["max_lev"]` leverage cap (`masterminds.py:233`) with a **regime-conditional** gross target and add a **net** dial. This is the blueprint's "min-gross/net-short in high-P(Q4), max-gross/tight-net in high-P(Q1)."

Let `p1..p4 = P(Quad_k)` from Section B's HMM, `intensity = regime_confidence`, `break_intensity` from D.1.

- **Gross target:**
  `gross_target = prof["max_lev"] · g(P(Quad)) · (1 − 0.5·break_intensity) · (1 − 0.4·MRS)`
  where `g(P) = 1.0·p1 + 0.85·p2 + 0.70·p3 + 0.45·p4` (a P-weighted blend of per-quad gross multipliers — continuous, no argmax cliff). The `break_intensity` term is the "cut before the transition confirms" behavior; the `MRS` term (from `conditions.macro_risk_score`, `:750`) is the existing macro-risk overlay, now made a *gross* input instead of a display-only heat penalty.
- **Net dial (long/short bias):**
  `net_floor = 0.85·p1 + 0.60·p2 + 0.35·p3 + 0.10·p4`.
  In high-P(Q4), `net_floor → 0.10`, permitting the book to run near market-neutral or net-short (allocate the freed gross to GC=F/IEF/TLT — the `SAFE` set already defined in `masterminds`). Implement net-short via the *existing* `backtest_portfolio` short-financing path (`active_alloc.py:104` already charges `bill+borrow_spread` on `-pos`) — so the machinery is present; we're just permitting negative equity-leg weights when `p4` dominates. **Start conservative: cap max short at −0.20 gross per leg (P2), long-only elsewhere (P1).** Trade-off: net-short is where you can actually lose money fast if the regime read is wrong. Recommendation: ship the *gross* dial first (P1, high value, symmetric-safe), gate the *net-short* extension behind a separate DSR validation (P2), because a bad short in a diffuse-regime whipsaw is the failure mode that ends accounts.

Final: `W_final = W_cvar · clip(gross_target / gross_now, 0, 1)` (subtract-only relative to the vol-targeted book — the dial can *cut* gross but the vol-target sets the ceiling).

#### D.2.f — Files, artifacts, wiring

- **New `engine/portfolio_l7.py`**: `hrp_weights`, `black_litterman`, `cvar_constraint`, `gross_net_dial`, and `l7_weights(P, prof, regime_probs, ev_views, break_json, mrs)` orchestrator returning a weight matrix shaped like `masterminds._weights` output (so `active_alloc.backtest_portfolio` consumes it unchanged).
- **New `data/portfolio_l7/weights.json`** (live target book) + `backtest.json` (scorecard, split-half OOS, DSR, gross/net path).
- **Reuse:** `portfolio.erc_weights`/`_risk_contrib` (fallback + diagnostics), `active_alloc.backtest_portfolio` (evaluator, unchanged), `active_alloc.split_half_oos`, `validation.deflated_sharpe`/`block_bootstrap_ci`/`purged_folds`.
- **Consumes:** Section B `regime_probs.json` (P(Quad) + transition matrix), Section C `regime_ev.json` (`μ_{a,k}` views), D.1 `usd_corr_break.json` (`break_intensity`), `conditions.macro_risk_score` (MRS).
- **Render:** the allocation page gains a **gross/net dial gauge** (current `gross_target` vs `max_lev` ceiling, net bias), a HRP-vs-BL weight-delta table (shows how much the conditional-EV views moved the book off the risk-structure prior), and the CVaR-budget utilization bar. The transition-break flag from D.1 appears as a red "de-grossing: correlation structure fracturing" banner when active.

#### D.2.g — Validation gate before it touches a live weight

Non-negotiable for real money, and the reason for the side-by-side build:

1. Backtest `l7_weights` vs incumbent `masterminds._weights` on the **same** `backtest_portfolio` evaluator, same costs (`cost_bps=3.0`), same 60/40 and SPY benchmarks.
2. **`split_half_oos`** (already built, `active_alloc.py:180`) — L7 must beat the incumbent in *both* halves on Sharpe *and* max-DD, not just full-sample.
3. **`deflated_sharpe`** with `n_trials` from the Trial Ledger `family="portfolio_l7"` (the honest `ledger=` path, `validation.py:218` — the `n_trials` literal path is ratchet-blocked). Count every `(HRP-linkage, τ, δ, CVaR-budget, gross-blend)` combination tried. **Gate: promote to live only if DSR ≥ 0.95 AND both-half OOS beat.**
4. Scorecard **broken out by realized Quad and by VIX bucket** — the L7 book's entire thesis is regime-conditional behavior; if it doesn't outperform *specifically in Q3/Q4 and high-VIX*, the gross/net dial is adding complexity without the tail protection it promises.
5. Until it clears, `portfolio_l7` outputs are **display-only** ("proposed L7 book") alongside the live incumbent — same doctrine as every other engine in this repo.

| Item | Effort | Priority | Deps |
|---|---|---|---|
| `hrp_weights` (linkage + quasi-diag + recursive bisection) + LW shrinkage | M | **P0** | scipy, sklearn |
| Black-Litterman blend w/ confidence-scaled Ω | L | **P0** | Section C `regime_ev.json`, Section B `regime_probs.json` |
| CVaR@95 scalar drawdown-budget constraint | S | P1 | — |
| P(Quad) gross dial (long-only) | M | **P0** | Section B P(Quad), D.1 break_intensity, MRS |
| Net-short extension (Q4) | M | P2 | gross dial + separate DSR gate |
| Side-by-side backtest + DSR/OOS/regime-bucket gate | M | **P0** | `validation.py`, Trial Ledger |
| Allocation-page dial gauge + HRP/BL delta + CVaR bar | M | P2 | live weights JSON |

---

### D.3 — Sequencing and the one dependency that gates everything

The hard dependency chain: **L7 Black-Litterman is worthless without L3 `μ_{a,k}` views, which are worthless without L2 `P(Quad)` probabilities.** If Sections B (continuous regime probabilities) and C (conditional-EV) are not built, L7 degrades to HRP + vol-target + CVaR + a *static* gross dial — still a strict upgrade over the current heuristic `_weights` (adds HRP block-awareness and a hard CVaR tail gate), and worth shipping as a **P0 standalone** even before the regime machinery lands. Build order:

1. **D.1 signal-1 break detector** (P0, self-contained, feeds MRS + display immediately, no L2/L3 dep).
2. **D.2 HRP + CVaR + vol-target** with a *placeholder* gross dial keyed on the existing argmax quad and MRS (P0, no L2/L3 dep) — ship as the display-only proposed book.
3. Once Section B ships `regime_probs.json`: swap the placeholder for the **P(Quad) continuous gross/net dial** and inflate the HMM transition hazard with `break_intensity`.
4. Once Section C ships `regime_ev.json`: turn on **Black-Litterman views**, run the full DSR/OOS/regime-bucket gate, and promote from display-only to live on pass.

The single highest-value, lowest-dependency deliverable in this whole section is **D.1's `dollar_haven_flip` detector** — it's O(n), depends on nothing, and catches the exact "equities and the dollar fall together" transition that the current first-derivative RORO composite (`conditions.py:241`) is structurally blind to. Ship it first.
## E. Front-End & UX Presentation Redesign

### E.0 Design thesis (the differentiator, stated once)

Hedgeye sells a **point**: one Quad label, one price range, one leadership rank. That is legible and wrong most of the time — it hides the fact that the forward path is a distribution and the regime label is a coin-flip when confidence is low (the live state today is exactly this: `growth_score=+0.20, conf=0.125`). Our edge in the UI is **honest uncertainty as a product surface**: we show P(Quad) not argmax, a cone fed by *real* DFM/GARCH variance not a lerp, calibrated probabilities with n and CI, and — critically — a **"no forecast"** state that renders explicitly when a cell is thin or a gate is closed, instead of fabricating a number.

**Design choice / recommendation (do not hedge):** Every forward-looking number on the site must carry one of three provenance badges, rendered as a small pill next to the value:

- **`MEASURED`** (green) — validated forward stat with DSR-passed / FDR-survived / coverage-verified backing.
- **`MODELED`** (amber) — a model output (DFM state, HMM posterior, HAR cone) that is internally consistent but not yet forward-graded live.
- **`NO EDGE`** (grey) — display-only / thin cell / gate-closed. Renders the word, not a fake number.

This badge system is the single most important cross-cutting component. Build it first (E.1). Everything else consumes it.

**Trade-off accepted:** A trader glancing at the page will see more grey than a Hedgeye deck shows confidence. That is the point — grey is trust. The alternative (dressing modeled outputs as measured) is how the incumbent loses credibility the first time a Quad call blows up.

---

### E.1 Cross-cutting primitives (build once, reuse everywhere)

New shared partials and JS. These are the foundation; nothing below works without them.

#### E.1.1 Provenance badge macro — `templates/_prov.html.j2` (NEW)

```jinja
{% macro prov(kind, n=none, extra='') -%}
{# kind in {measured, modeled, noedge} #}
<span class="prov prov-{{ kind }}"
      title="{{ {'measured':'Forward-validated (DSR/FDR/coverage passed). See methodology.',
                 'modeled':'Model output, not yet forward-graded live.',
                 'noedge':'Display-only or insufficient sample. Not a forecast.'}[kind] }}">
  {{ {'measured': t('measured','已验证'),
      'modeled':  t('modeled','建模'),
      'noedge':   t('no forecast','无预测')}[kind] }}
  {%- if n is not none %} <em class="prov-n">n={{ n }}</em>{% endif %}
</span>
{%- endmacro %}
```

CSS in `templates/theme.css` (reuse existing `color-mix` pill pattern at L207-209):
```css
.prov { --c: var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:.04em;
        padding:1px 6px; border-radius:6px; font-weight:700;
        background: color-mix(in srgb, var(--c) 12%, var(--panel));
        color: color-mix(in srgb, var(--c) 86%, var(--text));
        border:1px solid color-mix(in srgb, var(--c) 30%, transparent); }
.prov-measured { --c: var(--up); }
.prov-modeled  { --c: var(--orange); }
.prov-noedge   { --c: var(--muted); }
.prov-n { font-style:normal; opacity:.7; font-weight:500; }
```

**i18n gotcha (from memory `t-macro-not-in-attributes`, `zh-updown-token-flip`):** the `title=` string above is built from a Python-side dict, NOT the `t()` dual-span — `t()` MUST NOT go in attributes. Pre-resolve tooltip strings server-side per active lang and pass as a string. Also: `--up/--down` flip red↔green in zh (theme.css L82-88), but `prov-measured` deliberately binds to `--up`, so "measured" is green in en and **red** in zh. That's wrong semantically. **Fix:** give `prov-measured` its own token `--ok: #2e9e4f` that does NOT flip, defined in `:root` and NOT overridden in the zh block. Same for `prov-modeled` (bind to a non-flipping `--attn`).

- **Effort:** S · **Priority:** P0 · **Deps:** none · **Data:** none (pure presentation)

#### E.1.2 Distribution strip component — `templates/_diststrip.html.j2` + `templates/distviz.js` (NEW)

A single reusable inline-SVG component that renders a **fan of quantiles** (p05/p25/p50/p75/p95) as a horizontal violin-lite, used by every forward-return / forward-range surface (cones, conditional-EV, factor premiums). Contract: a JS function `renderDistStrip(el, {q05,q25,q50,q75,q95, ref, coverage, kind})` where `ref` is the zero/benchmark line and `coverage` (0–1, or null) drives a small "cov 71%" caption when the interval has a measured coverage stat.

Rendering rules (the honesty logic lives here):
- If `q05..q95` all present and `coverage != null` → **solid** fan + `MEASURED` badge + coverage caption.
- If quantiles present but `coverage == null` → **hatched** fan (CSS `stroke-dasharray`) + `MODELED` badge, no false precision on the tails.
- If fewer than the required n → render a flat grey bar with the literal text **"no forecast (n=X)"** + `NO EDGE`.

**Trade-off:** one component for all distributions means a consistent visual grammar (a trader learns to read one shape). The cost is it must handle both return-space (symmetric-ish, benchmark=0) and price-range-space (asymmetric, benchmark=spot). Solve with a `kind` param that only changes axis labeling, not geometry. **Recommendation:** build the one component; do not fork per page.

- **Effort:** M · **Priority:** P0 · **Deps:** E.1.1 · **Data:** consumes `data/**/dist.json` artifacts produced by the L3/L4 engines

#### E.1.3 Uncertainty-scaled color — global rule

The current 2x2 quad locator lights exactly one cell at full `--qN` saturation (dashboard.html.j2 L868, `.on` class). This is the argmax lie made visual. **Replace with opacity = P(Quadₖ)** everywhere the quad appears. New CSS custom property per cell: `style="--p:{{ probs['Q1'] }}"` and `background: color-mix(in srgb, var(--q1) calc(var(--p)*100%), var(--panel))`. The confirmed/argmax cell keeps a 2px `--text` outline so "current label" is still readable at a glance.

**Recommendation:** ship this to macro.html first, then propagate the identical macro to china/hk/canada/intl quad cards. Make it a shared macro `quadgrid(probs, current)` in a new `templates/_quadgrid.html.j2` so all six regime pages render identically.

- **Effort:** S · **Priority:** P0 · **Deps:** L2 `regime_probs` in latest.json · **Data:** `data/regime/regime_probs.json` (point-in-time HMM posterior)

---

### E.2 macro.html — head of the system (the flagship redesign)

File: `templates/dashboard.html.j2` (shared with us_stocks.html; gate macro-only blocks behind the existing `body.page-macro` class, e.g. L818/L858).

The macro page is where all six blueprint edges land in one viewport. Proposed top-to-bottom layout, each a card in the existing card grammar:

#### Card 1 — Regime Locator (replace the static 2x2)
- **Left:** the `quadgrid(probs, current)` from E.1.3 — 2x2 with cell opacity = P(Quadₖ), argmax outlined.
- **Right of the grid, NEW:** a **forward base-effect strip** — 4 mini quad cells labeled +1Q…+4Q showing the *deterministic* projected path from `engine/base_effect.py`. Each future cell shows an arrow (↗ accel / ↘ decel) driven by `sign(2nd-derivative of projected YoY)`. Caption: "Base comps through Q3 force inflation *down* regardless of momentum." Badge: `MEASURED` if the base-effect forward-log has matured directional accuracy ≥ its own threshold, else `MODELED`.
  - **Math surfaced in hover:** `fwd_yoy[t+k] = level_t·(1+m)^k / level_{t−12+k} − 1`, 2nd-deriv sign shown. Point-in-time flag required: the base denominator is a *historical* print (no revision risk) — this is the one forward signal that is genuinely PIT-clean, and the UI should *say so* ("base is a locked historical print — no revision risk"). That honesty is a selling point Hedgeye can't match.
- **Below the grid:** the AGREEMENT vital (currently L1575-area) is **replaced** by a bootstrap CI readout: `growth +0.20 [−0.05, +0.42]` with the `.prob`-style bar showing the CI width, not a single agreement %. When CI straddles 0 (as today), render the label in `--muted` and append the literal phrase **"regime indeterminate — trend-following preferred"**. This directly kills the false-confidence problem where conf=0.125 is currently shown as a single number.

- **Effort:** M · **Priority:** P0 · **Deps:** E.1.3, base_effect engine, `growth_score_ci_lo/hi` from axes bootstrap · **Data:** `data/regime/base_effect.json`, `data/regime/regime_probs.json`

#### Card 2 — Transition Radar (upgrade the existing TRANSITION chip)
The current `transition_state` chip (L1575) is a label string. Replace with:
- A **4x4 transition-matrix heatmap** (P(Quadⱼ next | Quadᵢ now)) rendered as a 4x4 grid of `color-mix` cells keyed on `--qN`, current row outlined. Small, ~180px.
- A **time-in-regime hazard gauge**: reuse the existing `.dial`/gauge grammar. Shows `P(regime change ≤ 21d)` as a filled arc, with `age {{age_d}}d · median {{median_d}}d` caption (the playbook progress bar data already exists at pb.progress). Badge `MODELED` (HMM posterior, not forward-graded).
- **Activate the dead `.prob` bars (L319, currently CSS-only):** render `next_list` as visible probability bars *below* the matrix, not as the hover text at L1684. Each bar: quad short-name + `--qN` fill + %. The hover-only rendering is the current waste; the CSS is already there.

- **Effort:** M · **Priority:** P0 · **Deps:** L2 transition matrix · **Data:** `data/regime/regime_probs.json` (must carry `transition_matrix` + `hazard`)

#### Card 3 — Conditional-EV cross-asset ranker ("the Hubble", macro edition)
The blueprint L3 output rendered as a ranked table (reuse `.tbl-scroll`, L440):

| Asset | E[r] 63d | CVaR₉₅ | E[r]/CVaR | dominant quad | prov |
|---|---|---|---|---|---|

- `E[r_a] = Σₖ P(Quadₖ)·μ_{a,k}` with `μ` from PIT regime labels. Each row's E[r] cell is a **distribution strip** (E.1.2), not a number — the point estimate is the p50, the fan shows μ±σ across quads.
- CVaR column colored on `--down`.
- **Thin-cell honesty:** any asset where the min-n-per-quad gate fails renders `NO EDGE` for the whole row and is sorted to the bottom, greyed. Do not silently backfill with all-history means.
- Sort by E[r]/CVaR descending = the cross-sectional ranker.

- **Effort:** L · **Priority:** P1 · **Deps:** E.1.2, L2 P(Quad), L3 `engine/regime_ev.py` · **Data:** `data/regime/ev_ranker.json` (PIT labels mandatory — flag prominently)

#### Card 4 — Index forward cone (wire the existing `forward_dist.py` that's currently unused at macro level)
The infra exists (`engine/forward_dist.multi_horizon_cone`) but is only wired to single stocks. Add a collapsible "Forward risk cone" card with three horizon distribution strips (1m/3m/6m) for SPY, driven by `growth_score` as the conditioning state. **Critical upgrade:** the cone width must come from the **DFM posterior variance** (L1) + **HAR/YZ realized vol** (L4), NOT the current `lerp(1.5,13)` heuristic. Coverage caption is mandatory: "80% band covered 74% of the last 252 forecasts" → this earns the `MEASURED` badge only when coverage ∈ [nominal ± 5pp]; otherwise `MODELED`.

- **Effort:** M · **Priority:** P1 · **Deps:** E.1.2, forward_dist wiring, DFM variance · **Data:** `data/regime/index_cone.json`

#### Card 5 — Gross/Net dial (L7 sizing guidance, display-only but load-bearing)
Extend the existing posture `.dial` strip (L1666-1690) with a **second row**: a GROSS EXPOSURE dial (MIN…MAX) whose fill is driven by the regime intensity, mapping `{high P(Q4)→MIN, high P(Q1)→MAX}`, plus a NET bias chip. Formula surfaced in hover: `gross_dial = Σₖ P(Quadₖ)·gross_k`, `net_floor = f(P(Q1)−P(Q4))`. Label it explicitly **"sizing guidance, not an order"** to stay consistent with the display-only doctrine. The trade-off vs a full HRP/BL weight vector: showing a dial (not weights) is honest about what's validated — we have a regime→gross mapping with some backing, not a validated optimizer. **Recommendation:** dial now, weights only after L7 CVaR harness passes DSR.

- **Effort:** S · **Priority:** P2 · **Deps:** P(Quad) · **Data:** none new (derives from regime_probs + playbook)

#### Card 6 — Wire the dead nowcast sparklines
`trendword()` (L44) and `nchart()` (L48) are defined and never called. Activate them in the vitals strip for WEI / GDPNow / core-CPI, fed by the DFM daily growth/inflation **state with variance** — the sparkline gets a shaded ±1σ band (the DFM posterior sd), which is the visual proof that we have a *distribution* where Hedgeye has a point. `NO EDGE`→`MODELED` badge until the DFM leads NBER turns on holdout.

- **Effort:** S (template) + depends on DFM engine · **Priority:** P1 · **Deps:** L1 DFM · **Data:** `data/regime/nowcast_hist.json` with `{svg, band_lo, band_hi}`

---

### E.3 sector_central (US Sector Central hub)

File: the sector board template consumed by `scripts/build_sector_central.py` → `subsectors`/sector desk render. Current output is a 0-100 conviction label with reasoning trace.

- **Add a regime-context banner** at the top (shared `quadgrid` mini + P(Quad) + growth/infl CI) so the sector board is visibly *conditioned* on the same regime head the macro page shows. Currently the desks are siloed; this banner is the visual tie.
- **New column `E[r|regime]`** per sector, a distribution strip (E.1.2) from `engine/sector_regime_ev.py`. Place it *beside* the existing conviction score, not replacing it — conviction is the timing/gate composite (`MODELED`/in-sample), E[r|regime] is the return expectation (`MEASURED` once purged-CV passes). Two columns, two provenance badges, is the honest presentation: "this name is well-timed (conviction 72) but regime-expensive (E[r] p50 −1.1%)".
- **Regime-transition de-emphasis (visual):** when `P(transition ≤21d) > 0.35`, wash the whole board with a subtle top-border `--orange` and a caption "regime transition risk elevated — mean-reversion signals down-weighted." This mirrors the L2 engine behavior in the UI.

- **Effort:** M · **Priority:** P1 · **Deps:** E.1.2, sector_regime_ev, L2 · **Data:** `data/sector_central/regime_ev.json` (PIT labels)

---

### E.4 Cycle pages (cycle.html, sector_cycles, country_cycles, china_sector_cycles)

Files: `templates/cycle.html.j2`, `templates/sector_cycles.js`, `site/cycle_app.js`, `templates/country_cycles.html.j2`. Current cone is the `lerp(1.5,13)` heuristic (cycle_app.js L105-112) — the single most dishonest visual on the site (a hardwired ramp masquerading as uncertainty).

- **Replace the heuristic cone with an empirical forecast-error band.** `sector_cycles.js` renders `_project_next`'s IQR today; feed it instead the `timing_mae_25/50/75` from `_projection_error_stats` (measured miss distances of past median-half-cycle predictions). The cone gets a **coverage caption**: "IQR band contained the actual turn 61% of the time (n=14 swings)." Badge `MEASURED` if coverage tracked, else the projection renders `NO EDGE` and shows only the rhythm estimate greyed with the literal caption "rhythm estimate — never backtested" (which is the honest current state of `_project_next`).
- **Add a hazard ramp on the projection line** (Kaplan-Meier survival of half-cycle durations): the dashed forward line darkens as instantaneous hazard peaks. Caption "X% of past cycles have ended by this date." This is L2-lite without an HMM.
- **cycle.html hand-curated projections** (`site/cycle_data.js`): keep them but stamp each with `MODELED` and surface the falsifiers already in the data (`falsifiers` field) as a visible "invalidates if" line — turn the hand-thesis into a falsifiable card, not an oracle.

- **Effort:** M · **Priority:** P0 (the lerp cone is actively misleading) · **Deps:** `_projection_error_stats` in sector_cycles.py · **Data:** none new (uses existing swing history)

---

### E.5 subsectors.html — the "Hubble" board (flagship cross-sectional ranker)

File: `templates/subsectors.html.j2`, `scripts/build_subsector_confluence.py`, `engine/index_leadership.py`. Currently `emerging_score` (heuristic 0.5/0.8/0.3 weights) is `accruing` after 3 days — its provenance is honestly `NO EDGE` today and the UI must say so.

This is the page where the blueprint's cross-sectional E[r]/CVaR ranker should be most visible. Proposed layout:

- **Regime banner** (same shared component as E.3) — because the current desk is completely decoupled from the quad, and the whole point of "Hubble" is `(regime-fit) × (timing/vol-band state)`.
- **Primary board = two-axis sort**: rows are subsectors, with two scored columns rendered side by side:
  - `regime_fit` = E[r|Quad] distribution strip (`MEASURED` once `subsector_regime_ev` matures; **`NO EDGE` today** — and the UI renders the words, not a fake rank).
  - `timing` = the existing emerging_score / entry-gate tier (`MODELED`).
- **The composite "Hubble score" column is gated:** it only computes and displays when *both* inputs are non-`NO EDGE`. Until subsector_regime_ev accrues, the composite column shows `NO EDGE` for every row. **This is the single most important honest-UX decision on the site:** do not ship a "Hubble ranking" that is secretly just the 3-day heuristic dressed in blueprint language. Ship the skeleton with the columns visibly empty-and-labeled until the data earns them.
- **Running/Coiling lists:** keep, but add the LAS-weights validation state chip (`MEASURED`/`MODELED`) from `validate_index_leadership.py`; if LAS weights aren't beaten vs equal-weight, say so inline.

- **Effort:** L · **Priority:** P1 (skeleton P0, data P2) · **Deps:** E.1.2, subsector_regime_ev, L2 · **Data:** `data/subsector_rotation/regime_ev.json`

---

### E.6 baskets.html / allocation.html

Files: `templates/baskets.html.j2`, `templates/allocation.html.j2`, `_baskets_desk.html.j2`. The engine honestly finds rank-IC≈0; the UI must not oversell.

- **Composite-score honesty:** the theme composite (weights 0.26/0.18/…) has never been validated as a return predictor. Render its column with `MODELED` and, next to the allocation, surface the phase-0 verdict verbatim: "rank-IC ≈ 0; the one validated edge is drawdown avoidance via the trend gate." A permanent, non-dismissable caption. This is a *differentiator* — a trader who sees a vendor admit rank-IC≈0 trusts the rest.
- **Regime-conditional basket E[r]** column (distribution strip) from `basket_regime_returns.json`, `NO EDGE` until cells accrue (many will be thin — bootstrap CI, wide bands, honestly rendered).
- **Allocation weights:** show the EW 1/N weight AND the CVaR-sized weight side by side (the engine upgrade proposes both) so the trader sees the gap. Gross dial (shared component from E.2 Card 5) at the top.
- **Survivorship banner:** membership is hindsight-curated — a `--orange` banner "basket history is survivorship-tinted; performance is descriptive, not OOS" until membership_history lands.

- **Effort:** M · **Priority:** P2 · **Deps:** E.1.2, E.2 gross dial · **Data:** `data/strategies/basket_regime_returns.json`

---

### E.7 factors.html

File: `templates/factors.html.j2`, `_load_ic_scorecard` in build_site.py. This page has the best honest backing (PIT IC scorecard) and the worst dilution risk (a negative-IC composite shown as actionable).

- **Split the composite visibly:** render TWO composites — "Research composite (8 factors, most fail FDR)" greyed `NO EDGE`, and "FDR-validated composite (payout only)" `MEASURED`. The current single composite (mean_ic = −0.007) must never be the primary read.
- **Per-quad IC heatmap:** a factor × quad grid (`color-mix` on `--up/--down` — remembering the zh flip) showing `mean_ic` per (factor, quad) with `n` in each cell. This is the L3 skeleton and answers "does value flip sign in Q3?" at a glance.
- **Provenance per factor row:** payout → `MEASURED`, value → `MODELED` (borderline q=0.247), low-vol/low-beta → `NO EDGE` (fail FDR). **Short-interest row must show `NO EDGE — IC unmeasured (no PIT history)`** since it's dropped from every backtest but shown live — the current silent mismatch is a trust bug.
- **VIX-bucket IC columns** (calm/med/stress) to expose factor-crash conditionality.

- **Effort:** M · **Priority:** P1 · **Deps:** per-quad IC in scorecard · **Data:** `ic_scorecard.json` (prefer `_debiased` once dead-name coverage ≥ 0.30 — surface the coverage fraction in a banner)

---

### E.8 signal_lab (the honesty spine, made legible)

File: `engine/signal_lab.py` REGISTRY → its render template. Already 5-tier (scored/confirmer/display/killed/pending). Map the tiers onto the provenance badges directly and add:

- **A live DSR/PBO/expectancy column** per signal (currently DSR/IC/t/q shown; add expectancy + profit-factor from the walk-forward harness — these exist in code but aren't surfaced). Expectancy is what a real-money trader reads; win-rate is theater (and the recon flags `win-rate-not-expectancy` repeatedly).
- **Rolling-IC decay sparkline** per scored signal (from the daily IC monitor), so a factor's live decay is visible before a manual re-validation catches it (the SUE demotion was caught by hand — surface it).
- **The KILLED tier is a feature, not shame:** render the BTC-GBT meta-label (DSR 0.95 but Brier skill −0.207, "DO NOT WIRE LIVE") prominently. A vendor that shows what it *killed* is the anti-Hedgeye. Give it a visible "graveyard" section.

- **Effort:** M · **Priority:** P1 · **Deps:** daily IC monitor, walk-forward expectancy surfaced · **Data:** `data/quality/signal_ic_monitor.json`

---

### E.9 gex.html (mechanical flow, L5)

File: `templates/gex.html.j2`, `engine/gex_engine.py`, `gex_model.py`. Already has gamma-flip, vol-hole, 25Δ RR.

- **Expected-move as a distribution strip** (E.1.2), replacing the single point `IV30·√(T/252)`. Feed with the HAR-GARCH forward quantile once built; until then `MODELED` hatched fan.
- **P(gamma regime flip ≤5d) gauge** (Brownian-crossing approx `2·Φ(−|dist|/(σ√N))`) as a small dial — the one continuous-probability read the GEX desk can produce cheaply.
- **Gating-inconsistency fix, surfaced:** GEX currently feeds per-stock scores while its validation gate is still accruing. The UI must show a `NO EDGE — gate accruing (n/30)` badge wherever a GEX-derived tilt is displayed, so the trader knows the weight isn't earned yet. (This is a data-integrity honesty item, not cosmetic.)
- **L5 mechanical-flow strip:** when `cta_flip_level` / `vol_control_rolloff` land, render them as a compact "machine flow" row (CTA flip proximity %, days-to-vol-rolloff) with `MODELED` until forward-graded.

- **Effort:** M · **Priority:** P2 · **Deps:** E.1.2, HAR-GARCH cone, GEX gate resolution · **Data:** `data/cboe/gex*.parquet` (persist `rr_25d`, `p_flip_5d`)

---

### E.10 crossasset.html (USD North Star, correlation-break)

File: `templates/crossasset.html.j2`, `engine/cross_asset.py`, `forex_transmission.py`.

- **USD↔asset correlation-break panel** (the blueprint's edge #2, currently absent as a detector): a small multiples grid — for each of {SPY, EEM, GLD, HG=F, CL=F} a rolling-corr sparkline (63d vs 252d) with a **break flag** when the sign flips and |Δ| > 0.3 for ≥5d. A lit `--orange` badge "USD transmission unstable — N/5 assets sign-flipped" is a genuine transition warning Hedgeye markets but never shows. `MODELED`.
- **Absorption-ratio gauge** (already computed) reuse the `.dial` grammar; concentrated ≥0.80 pctile lights `--down`.
- **Lead-lag pairs table** (HAC+FDR already computed): render only pairs passing FDR q<0.10 with the stability-check chip; everything else `NO EDGE`. Do not show spurious leads — and flag that macro-data leads are revision-contaminated until ALFRED vintages land (a `--orange` "revised data" pill).

- **Effort:** M · **Priority:** P2 · **Deps:** `usd_correlation_break.py` · **Data:** `data/forex/usd_corr_break.json`

---

### E.11 Nav & i18n integration (respect existing architecture)

- **Nav (memory `nav-chrome-architecture`):** no new top-level nav items. The provenance-badge legend and a one-line "how to read uncertainty here" gets a slot in the existing Research mega-menu as a "Methodology / How we show uncertainty" link → the existing `methodology.html.j2`. Run `check_nav_gap.py` after (the nav-ctrls are hand-duplicated per memory).
- **i18n (memory `t-macro-not-in-attributes`, `zh-updown-token-flip`, `theme-js-tbl-scroll-wrapping`):** every new label uses `t()/td()` dual-span in body text only; all tooltip/`title=` strings are pre-resolved server-side per lang. All new tables get the `.tbl-scroll` wrapper (theme.js auto-wraps, but new inline-SVG strips must set `min-width:0` per memory `mobile-overflow-audit-and-fix`). The provenance color tokens (`--ok`, `--attn`) must be added to BOTH the vector-family and standard nav CSS blocks and must NOT participate in the zh up/down flip.
- **Asset source (memory `theme-assets-source-is-templates`):** all CSS/JS edits go in `templates/` (render overwrites `site/`). New JS files (`distviz.js`, plus per-page consumers) live in `templates/` and are copied by the render step.
- **Mobile:** the distribution strips and heatmaps must degrade to a single-column stack < 420px; the 4x4 transition matrix collapses to a "most-likely-next: Q3 (38%)" text line on mobile (audit at 375px per memory).

- **Effort:** S · **Priority:** P0 (do alongside E.1) · **Deps:** E.1.1 · **Data:** none

---

### E.12 Build order (dependency-correct)

1. **P0, first:** E.1.1 provenance badges + E.1.2 distribution strip + E.1.3 quadgrid opacity + E.11 i18n/token plumbing. Nothing renders honestly without these.
2. **P0:** E.4 cycle cone replacement (kills the actively-misleading `lerp` cone with a measured-coverage band — highest harm-reduction per unit effort) and E.2 Card 1/2 (regime locator + transition radar) once L2 `regime_probs.json` exists.
3. **P1:** E.2 Cards 3/4/6 (conditional-EV ranker, index cone, DFM sparklines), E.3 sector_central banner+E[r] column, E.5 Hubble skeleton (columns visible, data gated), E.7 factors split-composite + per-quad heatmap, E.8 signal_lab expectancy/decay.
4. **P2:** E.2 Card 5 gross dial, E.6 baskets, E.9 gex, E.10 crossasset break panel.

**The one non-negotiable across all of it:** wherever a cell is thin, a gate is closed, or a signal is `accruing`, the UI renders the literal words **"no forecast"** with n, never a fabricated number. That single rule — distributions and abstentions where Hedgeye shows confident points — is the entire front-end differentiator, and it is cheap to enforce once E.1 exists.

---

New data artifacts this section requires (all must carry a `pit: true|false` field and, where forward-looking, an `n` and `coverage`): `data/regime/regime_probs.json` (PIT), `data/regime/base_effect.json` (PIT-clean by construction), `data/regime/ev_ranker.json` (PIT), `data/regime/index_cone.json`, `data/regime/nowcast_hist.json`, `data/sector_central/regime_ev.json` (PIT), `data/subsector_rotation/regime_ev.json` (PIT), `data/strategies/basket_regime_returns.json` (PIT), `ic_scorecard.json` per-quad+VIX-bucket extension, `data/quality/signal_ic_monitor.json`, `data/forex/usd_corr_break.json`. Templates to change: `dashboard.html.j2`, `theme.css`, `theme.js`, `factors.html.j2`, `subsectors.html.j2`, `baskets.html.j2`, `allocation.html.j2`, `cycle.html.j2`, `sector_cycles.js`, `site/cycle_app.js`, `country_cycles.html.j2`, `gex.html.j2`, `crossasset.html.j2`. New templates: `_prov.html.j2`, `_diststrip.html.j2`, `distviz.js`, `_quadgrid.html.j2`.
## F. Master Build Sequence & Page-by-Page Roadmap (v0->v3)

This is the integrated execution plan across all twelve audited subsystems. The organizing principle is **conceptual leverage per unit of engineering risk**: ship Hedgeye's actual kernel (base-effect determinism) first because it is cheap, deterministic, and needs zero new statistical machinery; defer the machine-learning-heavy layers (DFM/HMM) until the deterministic spine is proven and the data plumbing (ALFRED PIT) is closed. Every version ends at a **hard validation gate** — nothing that touches money or a headline label ships without passing it.

A note on reconciling the recon set: nine of the twelve subsystems independently proposed nearly identical upgrades (`base_effect.py`, `regime_hmm.py`, `regime_ev.py`, Yang-Zhang RV, DSR/PBO gates). **These must be built once, centrally, and consumed everywhere** — not re-implemented per page. The single biggest failure mode in this roadmap is twelve teams each writing their own HMM. The build sequence below enforces one canonical engine per capability with explicit fan-out.

---

### Design decisions made up front (stated, not hedged)

1. **Base-effect first, DFM later.** The recon repeatedly pairs "base-effect projection (L1)" with "mixed-frequency DFM (L1)". These are *not* the same effort class. Base-effect is deterministic arithmetic on a known denominator — S/M effort, no fitting, no new dependency. The DFM is an XL Kalman/PCA state-space model. **Ship base-effect in v0; ship DFM in v1.** Do not gate the conceptual core on the hardest component.

2. **ALFRED PIT is a v0 blocker, not a "Phase 3" deferral.** Every subsystem flags `revised-not-point-in-time` and every one defers it. `collectors/fred.py` *already has* `as_of_series()` and `load_vintages()` — the infrastructure exists and is used in offline audits. The live path ignoring it is the single largest source of overstated backtest performance across the entire system. Wiring it into `engine/inputs.py::build_features()` is M effort and is a **v0 deliverable**, because the base-effect forecast is worthless if computed on revised comps that weren't knowable at the time.

3. **One HMM, one EV engine, one vol surface — canonical modules with region/asset parameters.** China/HK/Canada/Intl/US/BTC all want regime probabilities. Build `engine/regime_hmm.py` once with a `scores: pd.DataFrame` input contract (columns `[growth_score, inflation_score]`) and call it per region. Same for `engine/regime_ev.py` and `engine/vol_surface.py`.

4. **`hmmlearn` over `statsmodels.MarkovRegression`.** `hmmlearn.GaussianHMM` gives a clean 4-state posterior + transition matrix + `predict_proba` in one object and is trivial to refit on a rolling window. `statsmodels` MS-AR is finickier to get the 4-quad mapping out of. Trade-off: `hmmlearn` is an added dependency and its EM can label-switch between refits — pin states to quads by sorting on the `(growth_mean, inflation_mean)` centroid at each refit. Recommendation: `hmmlearn`, with a deterministic centroid-to-quad assignment step.

5. **Argmax path is never deleted.** Every probabilistic upgrade ships behind an `enabled` flag with the discrete argmax as the always-available fallback. `P(Quad)` is *added* to `latest.json`, `raw_quad` stays as `current_quad`. This protects the live site during the transition and gives a permanent A/B baseline.

6. **Display-only until the gate passes.** The repo's own doctrine (vol_regime gate.json, GEX validate-before-weight) is correct and must be enforced on every new signal. New engines emit to JSON and render as display *before* they touch a weight. The one existing violation — GEX at `weight=0.10` in `stock_score._risk_idio` before its gate passed — gets fixed in v2 (either open the gate or demote to display).

---

### Dependency graph (what blocks what)

```
                          ┌─────────────────────────────────────────────┐
   v0 FOUNDATION          │  ALFRED PIT wiring (inputs.py)  ── BLOCKS ──► │ everything downstream that
                          │  collectors/fred.as_of_series already exists  │ claims honest backtest numbers
                          └───────────────┬─────────────────────────────┘
                                          │
                    ┌─────────────────────┴──────────────────┐
                    ▼                                          ▼
        engine/base_effect.py                     scripts/validate_regime_quad.py
        (2nd-deriv sign, deterministic)           (DSR/PBO on the EXISTING quad)
                    │                                          │
                    │  ships display-only on macro.html        │  honest scorecard = v0 gate
                    │                                          │
   ─────────────────┼──────────────────────────────────────────┼───────────────────────────
                    ▼                                          ▼
   v1 PROBABILITIES  engine/dfm_nowcast.py ──► engine/regime_hmm.py ──► engine/regime_ev.py
                    (Kalman growth/infl state)   (P(Quad)+transition)     (mu_{a,k}, E[r], CVaR)
                              │                        │                       │
                              │                        │        ┌──────────────┼───────────────┐
                              │                        │        ▼              ▼               ▼
                              │                        │   Sector Central   Baskets        Subsectors
                              │                        │   regime_ev col    regime_ev sort  regime reweight
   ─────────────────┼────────┼────────────────────────┼─────────────────────────────────────────────
                    ▼        ▼                        ▼
   v2 VOL+FLOW   engine/vol_surface.py (Yang-Zhang, HAR-fit, quantile cone, coverage)
                 engine/mechanical_flow.py (vol-control roll-off, CTA flip, equity COT)
                 engine/corr_break.py (USD North Star correlation-break detector)
                              │
   ─────────────────┼────────┼──────────────────────────────────────────────────────────────
                    ▼        ▼
   v3 PORTFOLIO  engine/portfolio_construction.py (HRP → BL → vol-target → CVaR → gross/net dial)
                 + full LdP spine wired live (triple-barrier, meta-label, purged-CV in build)
                 + intl extension (China/HK/Canada regime_hmm + regime_ev)
```

**Critical path:** `ALFRED PIT → base_effect → validate_regime_quad` is v0 and unblocks the honest-numbers claim for everything. `DFM → HMM → EV` is the v1 spine and every consumer page hangs off `regime_ev.json`. Vol/flow (v2) is **orthogonal** — it can be built in parallel with v1 by a second person and does not block the EV spine. Portfolio construction (v3) is the only thing that consumes *all* of L2/L3/L4 and therefore ships last.

**Highest-leverage-first recommendation:** if you have one engineer and one week, build v0 in this exact order — (1) ALFRED wiring, (2) `base_effect.py` display-only on macro.html, (3) `validate_regime_quad.py`. That sequence delivers Hedgeye's actual conceptual edge (deterministic forward 2nd-derivative), removes the worst look-ahead bias in the whole system, and produces the first honest DSR/PBO scorecard on the crown-jewel quad — all with zero new statistical modeling and zero new heavy dependencies.

---

### v0 — Deterministic Base-Effect Quad on PIT data (macro.html)

**Goal:** ship Hedgeye's conceptual core — the forward 2nd-derivative sign of YoY growth/inflation, deterministically forced by a base period fully known 12 months ahead — and put the crown-jewel quad on honest, point-in-time data with a real DSR/PBO scorecard. No ML, no new heavy deps.

**Deliverable 1 — ALFRED point-in-time wiring (the blocker).**
Files touched: `engine/inputs.py` (`build_features`), `config.yml` (new `engine.scoring.pit` block), `collectors/fred.py` (already has `as_of_series`, `load_vintages` — no change needed to the collector).
Mechanism: add an optional `as_of: pd.Timestamp | None = None` param to `build_features()`. When set and `load_vintages()` returns non-None, replace the ffill-carried FRED reads with `as_of_series(sid, as_of, vintages)` for the vintage-registered series: `WEI, GDPNOW, PAYEMS, INDPRO, ICSA, IC4WSA, STICKCPIM157SFRBATL, FLEXCPIM157SFRBATL, RECPROUSM156N, SAHMREALTIME`. Default `as_of=None` falls through to the existing latest-revision path — **zero change to default live behavior**. Tag each output series in `latest.json` with `"revised": true|false`. For series ALFRED excludes because they re-revise their whole history (NFCI family), keep latest-revision and carry an explicit `revised:true` flag rather than faking a vintage.
Also apply the conservative static publication lags already proven in `engine/equity_alloc.py::LEG_LAGS` (payrolls `.shift(22)`, INDPRO `.shift(30)`, WEI `.shift(5)`, sticky CPI `.shift(30)`) inside `build_features` for the near-zero-cost look-ahead removal, independent of ALFRED availability.
Data source: FRED/ALFRED (same free key). PIT-required: **yes, this IS the PIT fix.**
Effort: **M.** Priority: **P0.** Depends on: nothing.

**Deliverable 2 — `engine/base_effect.py` (the kernel), display-only.**
New file. Consumed by: `engine/axes.py` (display columns), rendered on `macro.html` via `templates/dashboard.html.j2`.
Math — for each monthly series `x` in `{INDPRO, core_cpi (CPIAUCSL core), core_pce (PCEPILFE), sticky_cpi}`:
- Base path known: `b[t+k] = x[t-12+k]` for `k = 1..12` (next 4 quarters), fully deterministic today.
- Sequential-momentum projection under three scenarios `m ∈ {flat=0, +0.5σ, −0.5σ}` where `σ` = std of trailing-6m MoM log-changes: `x_hat[t+k] = x[t] · (1+m)^k`.
- Projected YoY: `yoy_hat[t+k] = x_hat[t+k] / b[t+k] − 1`.
- **The signal:** `base_effect_2nd_deriv = sign( (yoy_hat[t+1] − yoy_hat[t]) − (yoy_hat[t] − yoy_hat[t−1]) )` under the flat-momentum scenario, in `{−1, 0, +1}`. This is the deterministic forced accel/decel that dominates the forward path when sequential momentum is normal.
- Output: `{growth_2nd_deriv, inflation_2nd_deriv, growth_base_path:[q1..q4], inflation_base_path:[q1..q4], base_forcing_note}` (e.g. "easy comps through Q3 → forced acceleration").
Wire into `axes.py` as **weight-0 display columns** `growth_accel`, `inflation_accel` (validated to non-zero weight in v1, gated behind forward-grading). Append a forward-grading log `data/regime/base_effect_fwd.jsonl` recording `(asof, growth_2nd_deriv, inflation_2nd_deriv)` for later directional-accuracy measurement at +63/+126d.
Render: replace the *static* 2×2 quad locator (`dashboard.html.j2:1493-1500`) with a **4-quarter forward strip** — four faded mini-quad cells with a projected-path arrow driven by `base_path`. Activate the dead `trendword()`/`nchart()` macros (`dashboard.html.j2:43-52`) to surface WEI/CPI nowcast sparklines while you're in the template.
Data source: FRED series already in `build_features()`. PIT-required: **yes — must run on ALFRED vintages (Deliverable 1) or the projected comps aren't the comps that were knowable.** This is why D1 blocks D2.
Effort: **M.** Priority: **P0.** Depends on: D1.

**Deliverable 3 — `scripts/validate_regime_quad.py` (the honest scorecard = the v0 gate).**
New file. Uses the *existing* primitives confirmed present in `engine/validation.py`: `purged_folds`, `cpcv_paths`, `prob_backtest_overfitting`, `deflated_sharpe`, `newey_west_tstat`, `rank_ic`, `block_bootstrap_ci`.
Mechanism: load `data/regime/regime_history.parquet` (confirmed present, 14,476 rows 1971→2026). For each of 11 SPDR sectors + IWM + LQD: compute quad-conditional forward-63d returns using **PIT regime labels shifted by `hysteresis_days` to kill confirmation-window overlap**. Run:
- `rank_ic(growth_score, fwd63d_equity)` and `rank_ic(inflation_score, fwd63d_TIP)` per purged fold (`k=6, embargo=21`).
- Newey-West HAC t-stat on the IC series.
- `deflated_sharpe(...)` on a go-long-Q1/short-Q4 sector strategy with **`n_trials` set from the actual tuning grid** (`scripts/tune.py` = 36 combos) plus the profile variants — do not lowball this.
- `prob_backtest_overfitting(perf, n_splits=16)` (CSCV/PBO).
- Break out every metric **by realized VIX bucket (<15 / 15-25 / >25) AND by realized quad.**
Also fix `scripts/tune.py`: add a fixed train (1971-2014) / hold-out (2015-2026) split and a `block_bootstrap_ci` (block=504) on the winning combo; print a loud warning if hold-out DSR < 0.90. This converts a known-overfit 36-cell in-sample grid into an honest validation.
Output: `reports/regime_quad_validation.json`.
Effort: **M.** Priority: **P0.** Depends on: D1 (labels must be PIT).

**v0 validation gate (must pass before macro.html ships the new strip):**
1. `regime_quad_validation.json` exists and shows the growth/inflation IC t-stat, DSR, and PBO on PIT data.
2. Base-effect 2nd-deriv directional accuracy is *logged* (not yet required to clear a bar — it's display-only and accrues forward).
3. ALFRED PIT path produces a `latest.json` where every FRED-sourced field carries a `revised` flag, and the 2008-Q4 / 2022-Q3 episode shares are **not materially worse** with lags applied (sanity check that we didn't break the classifier).
4. `raw_quad` argmax path unchanged and still the live `current_quad`.

**v0 risks:** (a) ALFRED vintage coverage is thin pre-2000 for some series → the honest scorecard's early history reverts to revised with a flag; accept and document. (b) Base-effect forcing is weakest exactly when sequential momentum is abnormal (regime breaks) — this is *expected* and is why it's a context signal, not a standalone timer. Do not oversell it in the UI copy.

---

### v1 — DFM Nowcast + Continuous P(Quad) + Conditional-EV tables (Sector Central, baskets, subsectors)

**Goal:** replace the discrete argmax and the binary econ confirmers with (a) a mixed-frequency dynamic-factor nowcast producing a daily growth/inflation state *with variance*, (b) continuous regime probabilities + a transition matrix + time-in-regime hazard, and (c) the missing return-alpha driver — regime-conditional expected-value tables per asset — wired into the three cross-sectional desks.

**Deliverable 4 — `engine/dfm_nowcast.py` (mixed-frequency Kalman state).**
New file. Two-step Giannone-Reichlin-Small DFM: standardize the monthly/weekly panel (`INDPRO, PAYEMS, sticky_cpi, WEI@month-end`), estimate one latent factor via PCA on the balanced sub-panel, then run a Kalman filter forward on the unbalanced daily observations to today. Output `factor_growth`, `factor_inflation` (2nd factor, orthogonalized) as **continuous scores with posterior variance**. These replace the four binary `monthly_sign()` components in `axes.py` at weight 1.0 each; the posterior variance feeds regime confidence as an additive uncertainty term (finally making "confidence" mean something).
Data source: monthly FRED already in `build_features`. PIT-required: **yes — must run on the D1 ALFRED path or the factor is contaminated by revisions.** This is the ordering constraint the recon flagged: PIT fix precedes DFM.
Effort: **XL.** Priority: **P2** within v1 (see trade-off below).
**Trade-off / recommendation:** the DFM is the single riskiest component in the whole roadmap (XL, new state-space code, hard to validate on ~7 recessions). **Do not let it block the HMM or EV work.** Ship the HMM (D5) on the *existing* `[growth_score, inflation_score]` series first; swap in the DFM factors as the HMM's input later once the DFM clears its own gate (filtered growth factor must lead NBER turns by 1-3 months on a 2015+ hold-out). If the DFM fails to lead, keep the axis scores as the HMM input — the probabilistic layer is still a strict upgrade over argmax without it.

**Deliverable 5 — `engine/regime_hmm.py` (the canonical probability engine).**
New file, **built once, consumed by every region.** `hmmlearn.GaussianHMM(n_components=4, covariance_type='full', n_iter=200)` fit on `[growth_score, inflation_score]` (or DFM factors when D4 lands). Rolling refit every 63 trading days on an expanding window (causal). Deterministic state→quad assignment: at each refit, sort the four state means by `(growth_mean sign, inflation_mean sign)` and map to Q1-Q4 to defeat `hmmlearn` label-switching.
Output per day: `P(Q1..Q4)` posterior, 4×4 transition matrix `A`, `time_in_regime = 1/(1−A[i,i])`, `hazard_21d = 1 − P(same quad in 21d)`. Persist `data/regime/regime_probs.parquet` + append `regime_probs` dict to `latest.json`. Gate behind `config.regime_hmm.enabled`; argmax stays as fallback.
Contract: `regime_hmm.fit_probs(scores: pd.DataFrame) -> ProbResult`. China/HK/Canada call the identical function with their own axis scores in v3.
Render: convert the 2×2 locator cells to **heat-intensity by `P(Quad_k)`** (cell opacity = probability, current cell outlined). Surface `hazard_21d` beside the TRANSITION vital and activate the styled-but-unrendered `.prob` bars (`dashboard.html.j2:319`) for the next-quad distribution.
Validation: fixed train-through-2019 / evaluate-2020-2026 split; posterior must cluster tightly in the 2008 and 2022 episodes.
Effort: **L.** Priority: **P0** within v1. Depends on: D1 (PIT scores). Does *not* depend on D4.

**Deliverable 6 — `engine/regime_ev.py` (the Hubble cross-sectional ranker — canonical).**
New file, **built once, consumed by Sector Central + baskets + subsectors.** For each asset `a` (11 SPDRs + IWM + LQD + GLD + the ~30 baskets + Shenwan sectors in v3) and each quad `k`:
- `mu_{a,k} = mean(fwd_Nd_return | PIT_quad==k)` for `N ∈ {21,63,126}`, labels shifted by `hysteresis_days` (no overlap).
- `CVaR_{a,k} = mean(worst 10% of fwd returns in quad k)`.
- `E[r_a] = Σ_k P(Quad_k) · mu_{a,k} · intensity_k` where `intensity_k` = the D5 posterior confidence (or `|axis_score|` fallback), and `P` from D5 (argmax `P=1` fallback if HMM disabled).
- Rank by `E[r_a] / |CVaR_{a,k}|` — the Hubble ranker.
Flag any cell with `n_obs < 20` as `thin` and suppress from ranking. Output `data/regime/ev_ranker.json` (SPDRs) + `data/regime/basket_regime_ev.json` (baskets). Log each build's `mu` estimates for forward grading.
**Reconciling the recon conflict:** Sector Central's recon proposes `engine/sector_regime_ev.py`, baskets proposes `engine/basket_regime_returns.py`, subsectors proposes `engine/subsector_regime_ev.py`, factors proposes `engine/factor_regime_ev.py` — **collapse all four into `regime_ev.py` with an asset-universe parameter.** One estimation kernel, four output JSONs. This is the most important consolidation in the whole plan.
Effort: **L.** Priority: **P1** within v1. Depends on: D5 (for the P-weighted version; can ship argmax-fallback the day D5 lands).

**Deliverable 7 — wire EV into the three desks.**
- **Sector Central** (`engine/sector_central.py::_fuse`): add `ev` field to each sector row from `ev_ranker.json`; add a secondary sort "Regime-adjusted score" = `E[r]/CVaR` *within* the trend-eligible set (preserves the validated trend/regime gate, only re-sorts survivors). Add `transition_hazard_21d > 0.35 → conviction ×0.85` continuous de-emphasis.
- **Baskets** (`engine/narrative_rotation.py::allocate`): replace flat EW `1/N` with inverse-CVaR sizing over eligible baskets when `basket_regime_ev.json` cells are thick (`n≥15`), degrade to EW when thin. This directly acts on the honest Phase-0 finding (rank-IC≈0) by shifting the edge to drawdown-budgeted sizing rather than fabricated directional alpha.
- **Subsectors** (`engine/subsector_rotation.py`, `engine/subsector_confluence.py`): multiply `emerging_score` by a per-quad sector multiplier; log the confirmed quad into `subsector_track_record` snapshots so IC can later be broken out by realized regime.
Files touched: the three engines above + their build scripts + `templates/subsectors.html.j2` (regime banner + sort toggle).
Effort: **M** each (L total). Priority: **P1.** Depends on: D6.

**v1 validation gate:**
1. HMM posterior clusters correctly in 2008/2022 on the 2020+ hold-out; transition matrix is row-stochastic and stable across refits (no label-switching in the persisted series).
2. `regime_ev.py` produces `rank-IC` of `E[r]` vs realized fwd-63d returns with a Newey-West t-stat reported per fold; **thin cells (`n<20`) are excluded, not silently zero-filled.**
3. DFM (if shipped) leads NBER turns 1-3m on hold-out; if it fails, HMM runs on axis scores and DFM stays display-only — **v1 still ships.**
4. Every desk change is behind a sort toggle / display column first; no basket weight moves until the EV rank-IC clears zero on hold-out.

**v1 risks:** (a) `n_obs` per (asset × quad) is genuinely small (Q4 has few episodes) — this is the fundamental sample-size wall the recon honestly flags; mitigate with `intensity`-weighting and wide Wilson/bootstrap CIs on `mu_{a,k}`, and **never** display a thin cell as if it were precise. (b) HMM refit instability — mitigated by the centroid-sort assignment. (c) Baskets survivorship bias (hindsight-curated membership) inflates `mu_{basket,k}` — carry a `survivorship_bias:true` flag on every basket EV and treat basket EV as strictly lower-confidence than SPDR EV.

---

### v2 — Vol complex + Mechanical-flow + Correlation-break (orthogonal, parallelizable)

**Goal:** build out Hedgeye's vol *surface* (currently ~2.5 of 6 dimensions), the L5 mechanical-flow front-running that is today fragmentary, and the USD North Star correlation-break detector. **This entire version is orthogonal to the v1 EV spine and can be built in parallel by a second engineer.**

**Deliverable 8 — `engine/vol_surface.py` (canonical vol engine).**
Consolidates the vol upgrades scattered across vol_regime/vol_forecast/froth/GEX recons into one module.
- **Yang-Zhang OHLC RV:** `yz = sqrt(σ_open² + k·σ_close² + (1−k)·σ_rs²)`, `k = 0.34/(1.34 + (n+1)/(n−1))`, from SPY/sector OHLC (confirmed available — `inputs.py` already loads VIX OHLC, SPY OHLC is a one-line extension). Replaces the close-to-close RV in `vol_forecast.py` and `vol_regime.py:173`.
- **Fitted HAR-RV:** expanding-window OLS `RV_{t+h} = α + β_d·RV_d + β_w·RV_w + β_m·RV_m` (Corsi), replacing the equal-weight `(2,5,22,66)` blend. Persist `data/vol_regime/har_weights.json`.
- **Quantile-regression forward cone with measured coverage:** pinball-loss quantile reg of fwd-h return on `[HAR-RV, regime confidence]` at `q∈{0.1,0.25,0.5,0.75,0.9}`; add a Christoffersen conditional-coverage test and publish empirical coverage vs nominal. This replaces the heuristic `amp=lerp(1.5,13,...)` cone in `cycle_app.js` and the symmetric `√t` cones everywhere with a **coverage-validated** interval.
- **IV surface (where chains exist):** IV-RV premium by tenor (30/60/90d), 25Δ risk-reversal persisted daily (fix: add `rr_25d` to the `GexAdapter._row` keep-tuple — it's already computed), IV dispersion = `iv30_SPX − mean(iv30_single_names)`.
Files: `engine/vol_forecast.py`, `engine/vol_regime.py`, `collectors/cboe.py`, `templates/sector_cycles.js`, `site/cycle_app.js`.
Effort: **L.** Priority: **P1.** Depends on: nothing (parallel to v1).
**Gate action:** after Yang-Zhang lands, **re-run `scripts/validate_vol_regime.py --write-gate`.** The recon shows the vol_regime scored gate is currently *closed for all legs* with DSR=0.9943 — the most likely cause is the noisy close-to-close VRP physical leg. Cleaner RV may push `ts_slope`/`move` past the HAC t>2.5 bar and finally open the money channel. This is a **procedural** unlock, not new modeling.

**Deliverable 9 — `engine/mechanical_flow.py` (L5, canonical).**
- **Vol-control roll-off schedule:** compute trailing-21d RV daily; identify high-vol days aging out of the window; `days_to_high_vol_exit`; when a shock day exits and recent vol was high → mechanical buying pressure flag. This is the *fastest orthogonal alpha* per the blueprint and is entirely absent today.
- **CTA trend-flip levels:** sign of `[21,63,126,252]d` MA crossovers; `flip_proximity_pct` = distance to the MA that would flip the majority sign.
- **Equity-index COT:** add `equity_futures` to `collectors/cot.py` (CME E-mini S&P 13874+, E-mini NASDAQ 20974+) — free CFTC Socrata history back to the 1990s. This fills the glaring gap that the COT collector covers commodities but not equity index positioning.
Consume as **Tier-B display/escalator legs** in `risk_radar.py` (adjacent to the currently-inert `vol_putcall`/`vol_gex`), INERT until the Opus/validation loop clears them.
Effort: **M.** Priority: **P1.** Depends on: nothing.

**Deliverable 10 — `engine/corr_break.py` (USD North Star edge #2).**
For broad-USD vs `{SPY, EEM, GLD, HG=F, CL=F}`: rolling 63d and 252d correlation; CUSUM-style break detector flagging when the sign flips and `|corr_63d − corr_252d| > 0.3` for ≥5 consecutive days (e.g. SPY going from negative-to-USD to positive = the "sell everything" regime). Emit `regime_break_count` (of 5). Wire into `cross_asset_confirm.py` as a new caution flag and — critically — as an **L2 transition-warning input**: a USD correlation regime break is exactly the "rolling-correlation regime BREAK = transition warning" the blueprint names, and it should nudge `hazard_21d` in the HMM consumer layer.
Effort: **M.** Priority: **P1.** Depends on: `forex_transmission.py` rolling-beta math (reuse).

**Deliverable 11 — fix the GEX validate-before-weight violation.**
Run `scripts/validate_gex.py` on accumulated history. If it passes → write `scored=true` and keep GEX in `stock_score._risk_idio` (w=0.10) and `_gex_confirm_tilt` (±0.3). If it fails → **remove GEX from those scored paths and demote to display.** Leaving both active violates the repo's own doctrine and this must be resolved, not carried forward.
Effort: **S.** Priority: **P0** (correctness/consistency).

**v2 validation gate:**
1. Yang-Zhang RV lowers forward-RV RMSE vs close-to-close on hold-out (measured, not assumed); HAR fitted weights beat equal-weight on Clark-West.
2. Quantile cone empirical coverage within ±5pp of nominal on 252d OOS (Christoffersen conditional-coverage not rejected).
3. `mechanical_flow` and `corr_break` ship **display-only**; no leg touches a weight until it clears purged-CV lift ≥1.20 AND DSR p<0.10 (D14 gate).
4. GEX scoring inconsistency resolved one way or the other.

**v2 risks:** IV surface depends on chain coverage that is narrow (~10 mega-caps) and partly paywalled (MASSIVE OPRA) — scope IV dispersion to "young/display-only until >30 dates × >15 underlyings" and do not score it. Vol-control roll-off requires an assumed fund-AUM proxy — expose it as config and treat the output as directional, not a dollar estimate.

---

### v3 — Full LdP spine live + HRP/BL/vol-target/CVaR + gross/net dial + Intl extension

**Goal:** close the honest-accounting spine into the *live* build (not just research scripts), replace the heuristic sizing with a proper drawdown-budgeted optimizer that consumes the v1 EV views, add the regime-driven gross/net dial, and fan the v1 probability+EV machinery out to China/HK/Canada.

**Deliverable 12 — `engine/portfolio_construction.py` (L7).**
- **HRP base:** `scipy.cluster.hierarchy` linkage on the 252d correlation matrix → recursive bisection weights. (Reuse the existing ERC in `active_alloc.py` as a cross-check, but HRP is the base.)
- **Black-Litterman:** blend v1 `regime_ev.py` conditional-`E[r]` as *views* with a market-cap prior (SPY/IWM/QQQ weights as proxy), view uncertainty `Ω` from the `CVaR`/`n_obs` of each EV cell — thin cells get wide `Ω` and barely move the prior. This is the principled fix for the "regime factor is a hardcoded 0.20 weight with no uncertainty" gap.
- **Vol-target + CVaR constraint:** scale to target vol, then solve a small `cvxpy` LP enforcing `Σ w_a·CVaR_a ≤ dd_budget` (config `portfolio.dd_budget_pct`).
- **Regime gross/net dial:** `P(Q4)>0.4 → cap gross 0.6`; `P(Q1)>0.5 → gross up to 1.2`. Replaces the static per-profile `max_lev` constants in `masterminds.py` with a `P(Quad)`-driven dial — the exact blueprint L7 behavior.
Also wire the display-only ERC leaf (`portfolio.py`) into `masterminds.py::_weights` as the risk-parity base instead of the current inv-vol approximation.
Files: new engine module + `engine/masterminds.py`, `engine/china_masterminds.py`, `engine/narrative_rotation.py`.
Effort: **XL.** Priority: **P2.** Depends on: D5 (P(Quad)), D6 (EV views), D8 (vol surface for CVaR).

**Deliverable 13 — Intl extension (canonical fan-out).**
Call `regime_hmm.fit_probs()` and `regime_ev.py` with China/HK/Canada axis scores and their deep sector histories (Shenwan L1 back to 1999 is the richest non-US sample). Replace the static `china_masterminds` `W_REGIME=0.40` prior with a `regime_confidence`-scaled dynamic weight. Link `country_cycles` phase to `intl_regime` quad (currently fully decoupled) so each country chip carries a regime badge. **No new engine code — pure fan-out of the v1 canonical modules**, which is the entire payoff of building them once.
Effort: **L.** Priority: **P2.** Depends on: D5, D6.

**Deliverable 14 — LdP spine into the live build (L6).**
Move the research-only harnesses into the daily pipeline: `scripts/monitor_signal_ic.py` (rolling-IC decay alerts via `engine/drift.py`, push-notify on scored-signal drift), triple-barrier + meta-labeling calibration on the US confluence buy-filter (currently only BTC, which was KILLED — apply the same honest test to equities), and switch `factors.html` to the **de-biased** `ic_scorecard_debiased.json` once dead-name price coverage >30%. Add `oos_r2`/`clark_west` (already in `validation.py`, currently unused) to every live timed signal vs the Goyal-Welch expanding-mean benchmark.
Files: `.github/workflows/daily.yml`, `scripts/factor_ic_scorecard.py`, `engine/signal_lab.py`, new `scripts/monitor_signal_ic.py`.
Effort: **L.** Priority: **P1** (this is honesty infrastructure — arguably should creep earlier if a factor is being sized).

**v3 validation gate:**
1. Portfolio construction backtested with `deflated_sharpe` (n_trials = full profile/parameter count, no lowballing) and `prob_backtest_overfitting`; **HRP-BL-CVaR must beat the current inv-vol GTAA on hold-out Sharpe net of the existing cost model, or it does not replace it.**
2. Gross/net dial validated: max-DD reduction in high-`P(Q4)` periods on hold-out, no Sharpe destruction in `P(Q1)`.
3. Intl HMM/EV pass the same 2020+ hold-out cluster test as US; thin-cell suppression enforced (China Q4 cells will be thin).
4. Daily IC monitor live and alerting; de-biased factor scorecard is the page default.

**v3 risks:** `cvxpy` adds a heavyweight dependency and LP infeasibility on degenerate covariance — add a fallback to vol-target-only when the LP fails. BL view-uncertainty calibration is the subtle part; get `Ω` wrong and thin EV cells dominate the prior — hence the `Ω ∝ CVaR/n_obs` rule and a hard cap on any single view's weight.

---

### Effort/priority summary

| Ver | Deliverable | Effort | Prio | Blocks |
|-----|-------------|--------|------|--------|
| v0 | D1 ALFRED PIT wiring | M | P0 | everything honest |
| v0 | D2 base_effect.py (display) | M | P0 | v1 axis re-weight |
| v0 | D3 validate_regime_quad + tune fix | M | P0 | v0 ship gate |
| v1 | D4 dfm_nowcast.py | XL | P2* | (does NOT block D5) |
| v1 | D5 regime_hmm.py (canonical) | L | P0 | D6, all consumers |
| v1 | D6 regime_ev.py (canonical Hubble) | L | P1 | D7, D12, D13 |
| v1 | D7 wire EV → 3 desks | L | P1 | — |
| v2 | D8 vol_surface.py (canonical) | L | P1 | D12 CVaR |
| v2 | D9 mechanical_flow.py | M | P1 | — |
| v2 | D10 corr_break.py | M | P1 | hazard input |
| v2 | D11 fix GEX gate violation | S | P0 | correctness |
| v3 | D12 portfolio_construction.py | XL | P2 | — |
| v3 | D13 intl fan-out | L | P2 | — |
| v3 | D14 LdP spine live | L | P1 | sizing honesty |

\*D4 is P2 *within* v1 and explicitly must not block D5/D6 — ship the HMM on axis scores if the DFM slips.

**Single highest-leverage action:** D1 → D2 → D3, in that order. It delivers the Hedgeye kernel, removes the worst look-ahead in the system, and produces the first honest DSR/PBO on the crown-jewel quad — all in v0, all without ML or heavy dependencies. Everything else is a strict extension of that spine.

---

Files verified against the live tree while writing this section:
- `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/bold-visvesvaraya-ba72be/engine/validation.py` — confirmed `deflated_sharpe`, `purged_folds`, `cpcv_paths`, `prob_backtest_overfitting`, `block_bootstrap_ci`, `rank_ic`, `newey_west_tstat`, `oos_r2`, `clark_west` all present (v0/v1/v3 gates depend on these existing).
- `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/bold-visvesvaraya-ba72be/collectors/fred.py` — confirmed `fetch_vintages`, `load_vintages`, `as_of_series` present (D1 ALFRED wiring is plumbing, not new infra).
- `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/bold-visvesvaraya-ba72be/engine/forward_dist.py` — confirmed `multi_horizon_cone`, `conditional_distribution` present (reusable for v2 cones).
- `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/bold-visvesvaraya-ba72be/engine/axes.py` / `engine/regime.py` — confirmed `score_axis`, `raw_quad`, `apply_hysteresis` signatures (D2/D5 integration points).
- `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/bold-visvesvaraya-ba72be/data/regime/regime_history.parquet` and `data/sector_central/calls.parquet` — confirmed present (D3/D6 inputs).

---

# PART II — ADVERSARIAL CRITIQUE

## 1. Missing Subsystems, Data Realities, and Failure Modes

### 1.1 ALFRED vintage availability is asserted, never verified — and it is the load-bearing assumption of v0

Every section treats `collectors/fred.py::as_of_series` + `data/fred_vintage/vintages.parquet` as if turning it on for the live path is free plumbing. **Nobody checked which series actually have usable vintage depth, and the base-effect kernel is worthless without deep vintages on the exact series it consumes.**

Concrete problems the plan ignores:
- **`STICKCPIM157SFRBATL`, `FLEXCPIM157SFRBATL`, `WEI`, `GDPNOW` have shallow or no ALFRED vintage history.** Sticky/flex CPI are Atlanta Fed constructs that re-derive on methodology changes; WEI's vintage series began ~2020; GDPNow is a nowcast that ALFRED does not archive as clean point-in-time observations the way it archives `PAYEMS`. Section A.1 hard-lists these as base-effect inputs. Section F says "ALFRED vintages via the existing FRED key" and lists `PCEPILFE, CPIAUCSL, CPILFESL, INDPRO, PAYEMS, PPIFIS` — a *different* set than Section A/Conditions. **The two sections don't even agree on which series get vintaged, and neither verified depth.**
- **The recon itself already states NFCI re-revises whole history and is excluded.** Good. But nobody audited the base-effect set the same way. **Build a `scripts/audit_alfred_depth.py` that pulls vintage_dates per candidate series and reports first-vintage-date + revision magnitude, and run it BEFORE committing to D1→D2.** If `PCEPILFE` vintages only go back to 2019, the base-effect "68% inversion on our data" test in A.6 has ~5 years of non-overlapping quarters = statistically dead on arrival.

**This is the single biggest unverified claim in the entire plan.** The whole v0 conceptual-edge story collapses if the vintages aren't deep enough, and no section gated on checking.

### 1.2 Render-time / compute budget is completely unaddressed — and the plan adds an HMM refit, a DFM Kalman, a GARCH, and per-asset×quad EV bootstraps to a 67-minute render

Memory says render is ~67min, 4-core CPU-bound. The plan adds, per build:
- `regime_hmm.py`: rolling refit every 63d, `covariance_type='full'`, 4 states — fine if fit once, but Section A says "re-estimate quarterly" while Section F says "rolling refit every 63 trading days on an expanding window." **On a 14,476-row daily history, an expanding-window EM refit at every historical rebalance for the backtest is O(n²) in fit calls.** If done naively in the daily build it's minutes-to-tens-of-minutes.
- `dfm_nowcast.py`: Kalman filter over the full panel.
- `vol_surface.py`: expanding-window OLS HAR fit + quantile regression + GARCH refit weekly, **per asset** (11 sectors + SPY + baskets).
- `regime_ev.py`: `mu_{a,k}` + CVaR + Newey-West + Wilson CI over ~30 assets × 4 quads × 3 horizons, plus `block_bootstrap_ci` (B=500–5000).
- `portfolio_construction.py`: HRP linkage + BL matrix inversions + **cvxpy LP** every rebalance.

**No section budgets this.** cvxpy alone can add seconds-per-rebalance × hundreds of rebalances. **The plan needs an explicit "fit offline, cache coefficients, load in render" split** — HMM transition matrix, HAR βs, DFM state-space params, and EV `mu_{a,k}` tables should be computed in a nightly *calibration* job (like `ladder_calibration.json`, `business_cycle_calibration.json` already are) and the render only does the cheap filter/lookup step. Section C.2 gets this right for HAR weights (`har_weights.json`); **no other section does, and Section F's dependency table has no compute column.**

### 1.3 The data-health circuit breaker and `run_status.json` are never mentioned

Memory `data-health-circuit-breaker` and `data-signal-expansion` describe a half-open circuit breaker that kills the build when sources fail. **Every new engine (base_effect, dfm, hmm, ev, vol_surface, corr_break) is a new failure surface with no defined behavior when its input feed is stale or its fit fails to converge.** What does `latest.json` render when:
- `hmmlearn` EM fails to converge (happens on near-degenerate covariance in quiet regimes)?
- ALFRED returns empty for a vintage date (holidays, API hiccup)?
- The GARCH `arch` fit throws (it does, on short windows)?

The plan's UX section (E) invents a `NO EDGE` badge for thin cells but **never specifies the engine-level fallback contract.** Each engine must return a typed "degraded" result that the circuit breaker and the renderer both understand, or the first convergence failure takes down macro.html. **This is a P0 architecture gap, not a nicety.**

### 1.4 i18n and mobile obligations are handled only in Section E, but the new JSON artifacts break the existing bilingual/render contract

- Section E correctly flags `t()`-not-in-attributes and the zh up/down token flip. But **Sections A–D emit `headline`/`base_forcing_note`/`break_headline` as English strings baked into JSON** (e.g. A.1 "easy comps through Q3 → forced acceleration", D.1 "SPY↔USD correlation flipped positive…"). These are natural-language, generated server-side, and **have no zh counterpart.** The repo is bilingual (`i18n-language-toggle`). Either every generated note needs a `_zh` sibling produced at emit time, or the UI shows English strings to Chinese users. **No section budgets the translation path for dynamically generated prose.**
- Mobile: the 4×4 transition matrix, the distribution strips, and the factor×quad heatmap are all new dense visualizations. Section E says "collapse to a text line on mobile" for the matrix but says nothing for the EV distribution strips or the Hubble two-axis board. The `mobile-overflow-audit` memory shows this repo has a recurring 375px overflow problem. **New SVG components need explicit `min-width:0` + a mobile fallback each, and that's real template work not counted in the effort tables.**

### 1.5 The `master_brain` / LLM synthesis layer and the `research_paper.py` buy-gate are orphaned

The recon's portfolio section notes the Mastermind buy-gate (`brain/research_paper.py`) lives in a *separate repo* and the dashboard-side brain is context-only. **The plan proposes P(Quad), EV tables, and a gross/net dial but never says how the actual trading brain (separate repo) consumes them.** If the real money is deployed by the Mastermind bot reading `latest.json`, then the schema additions in A.5 (`quad_fwd`, `regime_probs`, `intensity`) are a **cross-repo contract change** that the plan doesn't flag. Someone ships `regime_probs` to `latest.json`, the bot repo doesn't read it, and the "regime-conditional sizing" never reaches a live order. **This is the "engine produces a number the consumer ignores" failure the recon flagged for GEX — and the plan reproduces it at the whole-system level.**

### 1.6 Survivorship bias in the EV tables is acknowledged for baskets but ignored for the SPDR/sector EV — and it's present there too

Section F/A treat the 11 SPDR sector EV as clean because "SPDR ETFs have full history." True for the *ETFs*. But `regime_ev.py` for **subsectors and Sector Central** uses `basket_index.consolidated_candle(pit=False)` — **today's S&P 500 roster** — as the return series. The recon's subsector section is explicit: `pit=False`, survivorship-tinted, no membership history. **The EV `mu_{a,k}` for any synthetic sub-industry index is computed on survivors and will overstate `mu` in exactly the Q4/stress cells where dead names cluster.** Section A/D never carry this caveat into the EV engine's SPDR-adjacent consumers. The plan flags basket survivorship but not the structurally identical subsector/sector-synthetic survivorship.

### 1.7 No plan for the forward-grading latency gap

Every "validate before scoring" gate (base-effect inversion, EV rank-IC, cone coverage, corr-break lift) requires **matured forward observations** — 63d/126d horizons. The plan ships v0 display-only and says "accrues forward." But:
- The base-effect inversion test needs ≥1q-ahead realized 2nd-derivatives → **minimum 3-4 months before the first honest read, and years before the ~60% target has tight enough CI to trust.**
- The cone coverage test needs 252 forecasts.
- The EV forward-grading log needs quarters.

**Section F's v0→v3 sequence implies these gates can be passed in a build cycle. They cannot — they're gated on calendar time, not engineering time.** The roadmap needs an explicit "these engines ship display-only in vN and become eligible for scoring in vN+K *months*, not versions" statement. Otherwise the org will either (a) wait forever, or worse (b) shortcut the gate with in-sample backtested "validation" — the exact overfitting the spine exists to prevent.

---

## 2. Unverified / Risky Statistical Claims Needing a Gate Before Build

### 2.1 The "68% / 80% / 70%" base-effect inversion stats are Hedgeye marketing, restated as if they're our target

Section A states "the forward 2nd-derivative sign is the inverse of the base-period 2nd-derivative ~68%" and A.6 sets "Target: ≥60%." **This number is a vendor claim with no cited methodology.** It is almost certainly computed on *revised* data, on a favorable series set, with an undisclosed momentum assumption. Risks:
- **The 2nd-difference of a YoY series is extremely noisy.** `d2 = yoy[t+1] − 2yoy[t] + yoy[t-1]` on monthly data is a 2nd difference of a 12-month difference — you're differencing four times. The sign near zero is coin-flip by construction; the "68%" is dominated by the large-|d2| tail. **The honest test must condition on |d2_base| magnitude and report accuracy in the top tercile, or it will report ~55% pooled and someone will call the edge dead when it's actually real in the tail.** A.6 doesn't specify this stratification. Add it.
- **"Sequential momentum held at normal" is doing enormous work.** In the exact moments that matter (regime breaks), momentum is *not* normal, and that's when the base-effect sign is most wrong. The plan admits this in a throwaway line but sizes it as a scored axis input in v1. **Recommendation: the inversion test must be run separately on stable-momentum vs breaking-momentum months; if it only works when momentum is stable it's a confirmer, not a leading signal, and must never enter the HMM state vector at nonzero weight.**

### 2.2 Regime-conditional EV cells will be fatally thin, and James-Stein shrinkage toward the unconditional mean quietly destroys the entire edge

Section A.4 proposes James-Stein shrinkage of `mu_{a,k}` toward `mu_a` with weight `n/(n+τ)`, τ≈30. **Think about what this does.** The whole thesis of L3 is that `mu_{a,k}` *differs* from `mu_a` (the sector behaves differently in Q4 than unconditionally). With Q4 having maybe 15–40 observations and τ=30, shrinkage pulls the estimate **halfway back to the unconditional mean — i.e. halfway back to "no regime effect."** You will have built an elaborate machine whose output, after honest shrinkage, is ~indistinguishable from the unconditional sector rank. **The plan needs to confront the sample-size wall head-on:** with ~7 true recessions and a handful of Q4 episodes since 1998, `mu_{a,·,Q4}` is estimated on single-digit *independent* episodes regardless of daily row count (daily obs within one 2008 are not independent draws). **The Newey-West / block-bootstrap CIs will be enormous, and the honest conclusion may be "we cannot distinguish Q4 sector EV from noise."** That is a legitimate finding and the plan must be willing to reach it — but it currently presents EV as a shippable ranker in v1 without acknowledging the effective-N is ~episodes, not ~days.

### 2.3 Deflated Sharpe `n_trials` is systematically understated across the whole plan

Section B and F both invoke `deflated_sharpe(..., ledger=)` with `n_trials` from the Trial Ledger. **But the plan itself is a giant multiple-testing exercise that nobody is logging.** Twelve subsystems, each proposing the same 4-5 upgrades, each with tunable windows (slope_window, baseline_window, z_threshold, hysteresis, HMM n_states, HAR lags, EV horizons, shrinkage τ, cone quantiles, HRP linkage method...). The true `n_trials` for "did we find a regime edge" is **hundreds to thousands** once you count every parameter grid explored across every engine. The Trial Ledger only captures trials that authors remember to `log_grid()`. **Recommendation: the DSR threshold of 0.95 is meaningless unless the ledger is populated adversarially — mandate that every `validate_*` script logs its full grid, and treat the *system-wide* trial count as the deflation N for any cross-engine claim like "the forward-regime engine beats the legacy quad."** As written, each engine deflates only against its own local grid and the system-level overfitting is invisible.

### 2.4 The HMM label-switching fix (centroid-sort) is fragile and can silently corrupt the transition matrix time series

Section F proposes pinning HMM states to quads by sorting on `(growth_mean, inflation_mean)` centroids at each refit. **In a regime where growth and inflation states overlap (the current live state: growth conf=0.125, near zero), the centroid sort is unstable — two states can swap between refits, flipping `P(Q1)↔P(Q2)` discontinuously.** The persisted `regime_probs.parquet` then has phantom transitions that are pure relabeling artifacts, and the transition matrix `A` — which feeds the hazard and the gross dial — is contaminated. **The plan needs a hysteresis/Hungarian-assignment step matching new states to prior-refit states by parameter distance, not a naive sort, and a test that flags refit-to-refit label instability.** Section E even renders these probabilities as heat cells — a relabeling flicker becomes a visible "regime change" the user acts on.

### 2.5 Cone coverage tests need the right null and the right sample independence

Section C.4 mandates Christoffersen conditional-coverage. Good. But it computes coverage on "the last 252 day-ahead forecasts" — **overlapping h-day-forward windows are not independent, so the Kupiec/Christoffersen LR tests are anti-conservative (they'll pass a miscalibrated cone).** The coverage harness must use non-overlapping forecast origins or block-adjust the test, exactly the same overlapping-window problem the plan correctly flags for rank-IC HAC elsewhere but forgets here.

### 2.6 Yang-Zhang on dividend-*adjusted* OHLC is subtly wrong on ex-div days

Section C.1 says use `auto_adjust=True` OHLC and flags that O/H/L/C must be consistently adjusted. **They aren't consistently adjustable.** `yfinance auto_adjust` back-adjusts Close for dividends/splits but the intraday High/Low relative to that adjusted Close on the ex-dividend day encodes a discontinuity — the overnight `ln(O/C_prev)` term in Yang-Zhang picks up the dividend drop as "overnight volatility." For SPY (quarterly ~1.5% div) this injects a spurious vol spike 4×/year. **Minor, but the plan claims YZ is the clean estimator; on adjusted data it has a known quarterly artifact. Either use split-adjusted-only OHLC (raw div) or mask ex-div dates in the overnight term.** Verify which adjustment `collectors/yahoo.py` actually stores before asserting YZ correctness.

### 2.7 The USD correlation-break detector will fire constantly and its "lift" is untested against a trivially strong null

Section D.1's break signal (`|ρ_63 − ρ_252| > 0.35` for 5 days) will fire routinely — 63d vs 252d correlations diverge by 0.35 all the time in noisy assets like BTC and copper. **The claimed edge (break → regime transition) is tested against a "frequency-matched permutation null" (D.1.e), but the more dangerous null is "does break_intensity beat simply using VIX or the existing absorption ratio?"** The absorption ratio (already computed) captures "everything becoming one bet" more robustly than pairwise sign-flips. **The gate must show corr-break adds incremental lift *over the absorption ratio the system already has*, or it's a redundant, noisier restatement of an existing signal.** D.1 wires break_intensity into the HMM hazard *and* the gross dial *and* the MRS — triple-counting a signal that may not survive an incrementality test.

---

## 3. Sequencing and Dependency Errors

### 3.1 Section F's v0 ships `base_effect` display-only on macro.html BEFORE the inversion validation exists as matured data — so v0's own gate can't pass in v0

F's v0 gate item 2 says base-effect accuracy is "logged (not yet required to clear a bar)." Fine. But then **base_effect is rendered on macro.html as a forward-path arrow with a directional claim to a real-money user in v0, with zero validation.** That's shipping an unvalidated forward signal to the front page. It contradicts the plan's own display-only-until-gated doctrine. **Either render it with a loud `MODELED`/`UNVALIDATED` badge and no directional arrow (just the deterministic base path, which is a fact), or don't render the forcing direction until the inversion test matures.** The deterministic base *level* path is honest (it's arithmetic on known history); the *2nd-derivative directional claim* is the unvalidated part and must be visually separated.

### 3.2 DFM is P2-within-v1 but `regime_hmm` (P0) is specced to consume DFM factors — the fallback is stated but the wiring order isn't clean

Section F correctly says "ship HMM on axis scores first, swap DFM later." But Section A.3's HMM state vector **hard-lists `dfm_growth_z, dfm_infl_z` as the first two components.** If DFM slips, the HMM runs on `[growth_score, inflation_score]` (the axis scores) — which is fine — **but A.3 also removed `us2y_direction` from growth and added the liquidity/policy axes, meaning the "axis scores" the HMM falls back to are themselves mid-refactor.** The dependency is: axis refactor (remove monthly_sign legs, move us2y, add liquidity/policy axes) must land and be validated *before* the HMM consumes axis scores, or the HMM trains on a moving target. **Section F's D5 says "fit on `[growth_score, inflation_score]`" as if those are stable, but Section A is simultaneously rewriting what those scores contain.** Order: (1) axis refactor + revalidate legacy quad unchanged-enough, (2) then HMM. F doesn't sequence the axis surgery as a discrete gated step.

### 3.3 The gross/net dial (D.2.e / Section D) consumes `P(Quad)` from the HMM, but the HMM's promotion gate (beat legacy quad on forward-DD out-of-sample) is calendar-gated — so v3's dial can't be validated until the v1 HMM has matured months of forward data

Section D ships the gross dial in v3 "keyed on P(Quad)." Section F's v1 gate requires the HMM beat the legacy quad on *forward* metrics on 2015–2026 hold-out. That hold-out is historical, so it *can* be computed at build time — **but the plan elsewhere insists the forward-DD comparison be prospective (parallel-run A/B).** These conflict: is the HMM validated on historical hold-out (fast, in-sample-ish since 2015–2026 overlaps tuning) or prospective forward-grading (honest, slow)? **A.6 part 3 explicitly demands prospective A/B ("parallel-run makes this a clean comparison"). If so, the gross dial that depends on a *promoted* HMM cannot ship live in v3 — it must wait for the prospective window.** The roadmap treats HMM promotion as a v1 event; the honest version makes it a v1+K-months event, which pushes the entire portfolio-construction payoff out. **State this explicitly or the whole L7 layer ships on an unpromoted HMM.**

### 3.4 `regime_ev` is specced to consume PIT regime labels from `regime_history.parquet`, but that history was generated by the *legacy revised-data argmax* engine

Section A.4 / F's D6: `mu_{a,k}` uses "point-in-time regime labels from `regime_history.parquet`." **But that parquet's quad labels were computed by the current engine on latest-revision data** — they are neither PIT nor from the new forward engine. So the EV tables are conditioned on the *old, revised-data, argmax* regime, then presented as the forward engine's EV. **You must regenerate the historical regime labels with the PIT + new-axis engine before computing EV**, which means D1 (PIT) + axis refactor + a full historical re-classification must complete before D6 produces trustworthy `mu_{a,k}`. F's dependency table shows D6 depending on D5 but not on "regenerate PIT regime history," which is a real, expensive prerequisite (re-run classify over 1971–2026 on vintage data).

### 3.5 Vol-surface gate re-run (C.3) is sequenced correctly, but promoting the scored vol_regime deepener changes live sizing while the L7 portfolio layer isn't built yet

C.3 opens the vol_regime scored gate in v2 if Yang-Zhang rescues it. That immediately affects the **existing** `masterminds`/`equity_alloc` sizing (the deepener is subtract-only gross). Meanwhile L7 (which is supposed to own gross sizing) lands in v3. **So in v2 you have two gross-sizing mechanisms partially live (the newly-opened vol deepener + the legacy static profile caps) and in v3 a third (the P(Quad) dial) — with no section defining precedence.** Which multiplier wins? Do they compound (0.7 × 0.6 × 0.5 = over-degrossed to 0.21)? **The plan needs a single "gross reconciliation" owner that composes all subtract-only levers, or the book gets accidentally flattened when three de-risk signals coincide (exactly when they all fire together — a crash).** This is the same multiplicative-compounding hazard the risk_radar recon already noted, now spread across three versions.

---

## 4. The 5 Highest-Leverage, Lowest-Regret First Moves — and What to Cut

### The 5 first moves

1. **`scripts/audit_alfred_depth.py` — verify vintage depth on every base-effect/DFM series BEFORE writing a line of `base_effect.py`.** (S effort, zero modeling.) This is the true P0. If `PCEPILFE`/`INDPRO` vintages are deep (they are, back to ~1997+ for the majors) the plan proceeds; if the CPI-sticky/WEI/GDPNow vintages are shallow, you learn *now* that those legs are revised-data-only and the base-effect set shrinks to core CPI/PCE/INDPRO/PAYEMS. Everything in v0–v1 hinges on this and no section did it. **Lowest-regret possible: it's a read-only API audit.**

2. **Wire ALFRED PIT into `build_features()` with the static `LEG_LAGS` shifts (D1), and re-run the *existing* legacy quad on PIT data to measure how much current backtest performance was look-ahead.** (M effort.) This delivers value even if every other upgrade is cancelled: it tells you how overstated today's regime backtest is. It's the honest-numbers foundation and it de-risks all downstream EV/HMM work by giving them clean labels.

3. **`scripts/validate_regime_quad.py` (D3) + fix `tune.py`'s in-sample grid — produce the first honest DSR/PBO on the crown jewel, with the system-wide `n_trials` from the Trial Ledger.** (M effort.) This is the accountability document that tells you whether the existing quad has *any* forward edge before you build a probabilistic superstructure on top of it. If the legacy quad's rank-IC is insignificant on PIT hold-out, that's a five-alarm finding that reshapes the whole plan — better to know in week 1.

4. **`engine/vol_surface.py` Yang-Zhang + persist the IV surface (C.1 + C.5.1) — because C.5.1 starts a time series you can never backfill.** (S/M.) Every day the IV surface isn't persisted is a permanently lost day of skew/dispersion history. This is orthogonal to the entire regime spine (no dependency on ALFRED/HMM/EV), so it parallelizes, and it unblocks the vol-gate re-run that may finally open a money channel that's currently dead. **Zero-regret: it improves the physical VRP leg and the cone width regardless of whether the regime revamp succeeds.**

5. **`engine/mechanical_flow.py` vol-control roll-off schedule + E-mini COT (D9/C.6/C.7).** (M.) This is the genuinely *new* orthogonal alpha the whole system lacks, it's PIT-clean by construction (arithmetic on the fund's own trailing window), free data (CFTC Socrata), and depends on nothing in the regime stack. It's the highest expected-value *new* signal per unit effort and cannot be contaminated by the ALFRED/HMM risks above.

### What to CUT or defer as theater

- **CUT the DFM (`dfm_nowcast.py`) from the committed roadmap; make it research-only.** XL effort, hardest to validate (≤7 recessions), and the plan *already admits* the HMM works fine on axis scores without it. The DFM is the kind of impressive-sounding component that consumes a quarter and produces a factor indistinguishable from the axis scores it replaces. Build it as a research spike; promote only if it demonstrably leads NBER turns on hold-out. Do not put it on the critical path.

- **CUT the Black-Litterman layer (D.2.b) until the EV views are proven non-thin.** BL is mathematically elegant theater when the views (`E[r_a]`) have `Ω` so wide (from single-digit-episode Q4 cells) that the posterior ≈ the HRP prior. You'll have written a full BL implementation whose output is "basically HRP." Ship HRP + vol-target + CVaR (which are honest and validate-able) in v3; add BL only after the EV forward-grading log shows the views have real, tight-CI signal. Otherwise it's complexity that a code reviewer can't distinguish from HRP-alone.

- **CUT net-short from the gross/net dial (D.2.e) entirely for v1–v3.** Net-short on a diffuse-regime read (current conf=0.125) in a whipsaw is the account-ending failure mode, and it's gated on the *least* reliable output (P(Q4) from a small-sample HMM). The long-only gross dial captures ~90% of the risk-management benefit with ~10% of the blow-up risk.

- **DOWNGRADE the corr-break triple-wiring (D.1.d).** Until it passes an *incrementality-over-absorption-ratio* test, wire it to **display only** — not into the HMM hazard, not the gross dial, not the MRS. Triple-counting an unvalidated, high-firing signal is the definition of overfitting the risk overlay.

- **The `MEASURED/MODELED/NO EDGE` badge system (E.1) is the opposite of theater — keep it, build it first.** It's the cheapest, highest-trust component in the plan and it's the actual product differentiator versus Hedgeye's confident-point UI.

---

**Bottom line:** The plan's conceptual spine (base-effect determinism → probabilistic regime → conditional EV → drawdown-budgeted sizing) is correct and the reuse of existing `validation.py`/ALFRED/`forward_dist.py` infrastructure is real. But it has **one unverified load-bearing assumption (ALFRED vintage depth) that no section checked**, a **sample-size wall on regime-conditional EV that shrinkage quietly papers over into a null result**, **no compute budget against a 67-minute render**, **no engine-level degraded-mode contract for the circuit breaker**, and **a cross-repo consumer gap** where the Mastermind bot may never read the new schema. Do the five first moves — starting with the ALFRED depth audit, which could invalidate v0 before a day is spent — cut the DFM and BL as premature, and force every regime-conditional mean to publish its effective-episode-count next to its value so the sample-size wall is visible rather than hidden.

---

# PART III — PER-SUBSYSTEM RECON APPENDIX

Sixteen subsystems, each read against the 7-layer blueprint. Rigor flags, P0 upgrades and one-line verdicts below; full `current_method`, gaps and per-upgrade specs are in `research/_hedgeye_wf/recon.json`.

### Macro Regime / Quad Classifier (engine/regime.py + engine/axes.py)
- **Rigor flags:** `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `no-transition-probability`, `point-not-distribution`, `levels-not-ROC`
- **Upgrades proposed:** 11 (4 P0)
  - **[L1 / M] Base-effect deterministic forward projection for growth and inflation axes** - Add engine/base_effect.py. For each monthly series (INDPRO, sticky_cpi_3m, core_cpi, core_pce): (a) compute the trailing 12-month base path (already stored); (b) project the YoY rate at +1, +2, +3 quarters assuming flat sequential momentum (zero monthly change
  - **[L1 / S] Replace latest-revision FRED with publication-lag offsets in the regime classifier** - In engine/inputs.py:build_features(), apply the same LEG_LAGS pattern already proven in engine/equity_alloc.py:223. Specifically: (1) payrolls: shift 22 bdays after the 'reference month last day' stamp (use a mapping table indexed by PAYEMS vintage date, or co
  - **[L6 / M] Purged K-fold + episode-locked backtest with Deflated Sharpe on quad labels** - Add scripts/validate_regime_quad.py. (1) Load regime_history.parquet; (2) for each of the 11 SPDR sectors + IWM + LQD, compute quad-conditional forward 63d returns; (3) run purged K-fold (K=6, embargo=21d matching hmmlearn gap) using the existing engine/valida
  - **[L6 / S] Tune.py: add hold-out split and block-bootstrap CI to prevent tuning overfit** - Modify scripts/tune.py: (1) fix train window to 1971-2014; evaluate scoring criteria ONLY on 2015-2026 hold-out; (2) for the winning combo, add a block bootstrap CI (500 draws, block=504 days = ~2yr) on each criterion using the pattern from engine/validation.p
- **Verdict:** The quad classifier is a well-engineered first-derivative market-proxy consensus engine with honest hysteresis and additive overlays, but it lacks the three real Hedgeye edges — base-effect forward projection, continuous regime probabilities, and regime-conditional expected-value weighting — and its tuning is done in-sample with no deflated Sharpe, making the crown jewel analytically sound but strategically incomplete.

### Economic Nowcast / Conditions Layer
- **Rigor flags:** `revised-not-point-in-time`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `no-forward-projection`, `point-not-distribution`, `discrete-argmax`, `no-transition-probability`, `no-conditional-return`, `no-uncertainty`, `heuristic-cone`, `unvalidated-no-DSR-PBO`
- **Upgrades proposed:** 12 (2 P0)
  - **[L1 / M] Base-effect forward path for growth & inflation (L1)** - Add engine/base_effect.py. Inputs: monthly YoY series for WEI, GDPNow (or CPIAUCSL as proxy), STICKCPIM, FLEXCPIM — read from the ALFRED store (as_of_series from collectors/fred.py already exists). Algorithm: (1) Compute the known 12-month base sequence b_t = 
  - **[L2 / L] Continuous regime probabilities via Markov-switching (L2)** - Add engine/regime_ms.py using statsmodels MarkovRegression (already a dep candidate) or a pure-numpy 2-state Hamilton filter. State vector: [growth_score, inflation_score] from engine/axes.py (already computed daily). Model: 2-dimensional 4-state MS-AR(1) over
- **Verdict:** The conditions layer is a well-engineered coincident/lagging macro dashboard with validated recession components and honest lead-lag labeling, but it is missing the three real edges from the blueprint: no base-effect 2nd-derivative forward projection (L1), no continuous regime probabilities or transition matrix (L2), and no regime-conditional expected-return engine (L3) — making it a risk thermometer rather than a return-generating nowcast.

### Cycle-Position Pages Family: cycle.html (Cycle Intelligence), sector_cycles.html, sector_cycles_china.html, country_cycles.html — oscillators, ZigZag pivots, projection cones, lead-gate philosophy
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `close-to-close-vol-only`, `no-uncertainty`, `heuristic-cone`, `win-rate-not-expectancy`, `no-transition-probability`
- **Upgrades proposed:** 10 (3 P0)
  - **[L4 / M] Replace heuristic cone with empirical forecast-error bands** - In engine/sector_cycles.py, add _projection_error_stats(swings_all) that computes, for each historical confirmed pivot, the error between the median-half-cycle prediction (made at the prior pivot) and the actual arrival date. Store the 25th/50th/75th percentil
  - **[L3 / M] Regime-conditional return distribution per ladder state** - Extend calibrate_ladder() in cycles.py to bucket observations by (ladder_state × regime × liquidity_regime) — 8×3×3=72 cells, many thin but computable with N≥20 threshold. Emit mu_{a,k}, sigma_{a,k}, hit_pct, dd_p10 per cell. Store in data/regime/ladder_calibr
  - **[L6 / M] Grade China forward_log: attach realized returns and measure cycle signal accuracy** - In scripts/grade_china_cycles.py (new), join data/china_sector_cycles/forward_log.parquet (keyed by date+id) with realized forward returns at 21d, 63d, 126d from the Shenwan L1 and basket level series (engine/china_sector_index.sw_close + engine/baskets_china)
- **Verdict:** All four cycle pages derive phase and projection from a price-only first-derivative momentum oscillator with a hardwired heuristic cone — no regime-transition probabilities, no empirical cone coverage validation, no conditional return distribution, no PIT data, and barely above coin-flip win rates across all ladder states; the system is honest about its limitations but delivers display-level cycle-position reads rather than the regime-conditional expected-value engine the blueprint requires.

### Risk Radar (engine/risk_radar.py) + Risk State (engine/risk_state.py) + Macro-Risk Overlay (engine/conditions.py MRS + sector_macro_beta) + Vol-Shock Scorecard (engine/vol_shock_scorecard.py) + Risk Brain (engine/risk_brain.py) + De-escalation panel (engine/risk_radar_recovery.py) + Market State radar-override (engine/market_state.py)
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `no-uncertainty`, `heuristic-cone`, `win-rate-not-expectancy`, `no-transition-probability`
- **Upgrades proposed:** 11 (3 P0)
  - **[L1 / M] Add point-in-time FRED vintages via ALFRED for MRS and HY OAS** - Add lib/alfred.py: fetch ALFRED vintage-at-date for BAMLH0A0HYM2, DFII10, WALCL, RRPONTSYD, WTREGEN using the ALFRED API (free, same key as FRED). In engine/risk_radar.py _s() and engine/conditions.py _macro_risk_legs(), pass as_of= to the read call so trainin
  - **[L1 / M] Add base-effect determinism — forward 2nd-derivative sign from known comp path** - In engine/conditions.py or a new engine/base_effect.py: for each monthly FRED series already collected (CPIAUCSL, PCE, PAYEMS), compute the 12m YoY series. Then compute the forward comp path: the denominator for the next 4 quarters is already known. Forward 2n
  - **[L6 / M] Add purged K-fold + Deflated Sharpe validation gate to risk_radar_backtest** - In engine/risk_radar_backtest.py, add: (1) purged_kfold_lift(pct, onsets, k=5, embargo_d=21): split signal history into k folds, embargo 21 trading days around each fold boundary, compute lift in each hold-out fold, report mean+std. (2) deflated_sharpe(strateg
- **Verdict:** The risk radar stack has a genuine validated core (5 legs with 1.2-2.3x 2020+ lift, context gate, Opus self-correction, accountability ledger) but lacks the blueprint's three real edges — base-effect determinism is absent, the quad is a discrete argmax with no transition probabilities, and the gross dial is a lookup table not an intensity-weighted conditional-EV ranker — making it a well-engineered COINCIDENT risk flag rather than a leading drawdown forecaster.

### Volatility Engines (vol_regime, vol_shock_scorecard, froth_fragility, vol_forecast, vol_managed, vol_sentiment, vol_squeeze) vs Hedgeye 6-part vol surface
- **Rigor flags:** `close-to-close-vol-only`, `heuristic-cone`, `no-uncertainty`, `levels-not-ROC`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`
- **Upgrades proposed:** 10 (1 P0)
  - **[L6 / S] Promote vol_regime composite to scored via --write-gate after re-run** - The basket_overlay_gate.json (2026-06-21) shows live_overlay_helps=false and scored_marginal=false, but the DSR is 0.9943 (nearly 1.0). The most likely cause is the VRP physical leg being noisy close-to-close. After implementing Yang-Zhang RV (upgrade 1), re-r
- **Verdict:** The vol stack has solid architecture (validate-first firewall, causal windows, forward-outcome logs) but the core VRP physical leg is close-to-close only (no Yang-Zhang), the validation gate is currently closed for all scored legs (scored_score=null live), there is no IV surface (skew/dispersion/term-structure-of-skew all absent or display-only), and the forward cone is a heuristic equal-weight HAR width with no formal coverage test — covering roughly 2.5 of Hedgeye's 6 vol-surface dimensions.

### GEX / Options / Mechanical-Flow Desk (L5)
- **Rigor flags:** `levels-not-ROC`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-transition-probability`, `close-to-close-vol-only`, `no-uncertainty`, `heuristic-cone`, `win-rate-not-expectancy`, `no-conditional-return`, `no-forward-projection`, `other`
- **Upgrades proposed:** 11 (4 P0)
  - **[L5 / S] Collect E-mini/NQ equity-index COT** - Add an 'equity_futures' market key to the cot.py COT collector config (config.yml cot.markets) covering CME E-mini S&P 500 (CFTC code 13874+) and E-mini NASDAQ (code 20974+). Persist net non-commercial % OI as cot_equity_index. In commodity_signals.positioning
  - **[L5 / S] Persist rr_25d daily in GEX summary parquet** - In collectors/cboe.py GexAdapter._row(), add 'rr_25d' to the keep tuple (line 134). It is already computed by gex_engine (via gex_model.risk_reversal_25d) — just pass it through to the 1-row/day frame. In gex_confirm.assess(), compute rr_change = today_rr - pr
  - **[L5 / M] Vol-control roll-off schedule estimator** - New file engine/vol_control.py. Inputs: daily VIX series (already in vol_regime.py). Method: for each trailing window length W in {21, 63} days, compute trailing realized vol as RV_W(t) and RV_W_dropone(t) = RV excluding the highest-vol day in the window. When
  - **[L6 / S] Run the GEX validation gate and fix the scoring inconsistency** - scripts/validate_gex.py already exists and MIN_PER_BUCKET=30. Run it against the accumulated data/cboe/gex*.parquet history. If the gate passes (bootstrap 95% CI excludes 0 for short > long RV at 5d and 10d for SPX), update data/vol_regime/gex_gate.json with s
- **Verdict:** The GEX / options desk is architecturally honest and mechanically sound — gamma-flip, vol-hole, 25Δ RR, measured dealer flow, OPEX tagger, vol-regime sizing overlay all exist — but L5 is critically incomplete: no vol-control roll-off schedule, no CTA flip-level estimator, no equity-index COT, no ETF create/redeem, the put/call series is too young to be reliable, and GEX is already feeding per-stock scores in violation of the repo's own validate-before-weight gate.

### US Sector Central + Gated-Confluence Pipeline
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-conditional-return`, `close-to-close-vol-only`, `no-uncertainty`, `heuristic-cone`, `no-transition-probability`, `other`
- **Upgrades proposed:** 10 (2 P0)
  - **[L3 / L] Regime-conditional sector E[r] table (L3 core engine)** - New file engine/sector_regime_ev.py. For each of the 11 SPDR ETFs, estimate mu_{sector,quad} = mean forward-63d excess-vs-SPY conditioned on PIT quad label using the existing sector_central_grader call log (once accrued) OR a bootstrap from the 27y phase0 clos
  - **[L2 / M] Continuous regime probabilities via Markov-switching (L2)** - New file engine/regime_hmm.py. Fit a 4-state Gaussian HMM (statsmodels.tsa.regime_switching.MarkovRegression) on the daily (growth_score, inflation_score) series from data/regime/latest.json history (or rebuild from engine/axes.py scores). Output P(Quad_k) dai
- **Verdict:** The pipeline is a rigorous, honestly-documented state+gate machine (cycle rhythm → validated trend drawdown gate → MRS regime gate → momentum confirm) that correctly avoids fabricating directional alpha it doesn't have, but it produces only a 0-100 conviction label with zero regime-conditional expected-return content (no E[r|Quad], no P(Quad) weighting, no transition probabilities, no vol surface, no portfolio sizing) — it is a well-built dashboard display, not an expected-value ranker.

### Signal Engines + Validation Spine (L6 equivalent): signal_lab curated registry, validate_signals contract gate, walk_forward stop-aware harness, factor_ic_scorecard PIT cross-section, engine/validation.py primitive suite, engine/meta_label.py, engine/promotion_gate.py, engine/trial_ledger.py, engine/drift.py, engine/forward_dist.py, engine/vol_forecast.py, engine/anticipation.py
- **Rigor flags:** `levels-not-ROC`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-transition-probability`, `no-conditional-return`, `close-to-close-vol-only`, `heuristic-cone`, `win-rate-not-expectancy`, `no-forward-projection`
- **Upgrades proposed:** 10 (2 P0)
  - **[L6 / M] Daily rolling IC monitor + auto-decay alerts** - Add scripts/monitor_signal_ic.py: for each REGISTRY signal with IC > 0 and a data source (momentum, insider, payout factor), compute rolling 63-day rank-IC on the live universe using the most recent 252 rebalance dates. Feed the IC stream to engine/drift.py ro
  - **[L6 / M] Survivorship-corrected factor IC scorecard as the live page default** - Switch the live signal_lab page to read ic_scorecard_debiased.json when available (engine/signal_lab.py line 734: change path to prefer _debiased.json). In scripts/factor_ic_scorecard.py --debiased mode, the dead-name price panel (data/edgar/_dead_name_prices.
- **Verdict:** The validation spine is institutionally credible and complete as a RESEARCH harness (DSR, PBO, CPCV, purged-CV, BH-FDR, Brier calibration, meta-labeling, Trial Ledger are all implemented and used in phase-0 scripts), but live production is missing: continuous regime probabilities (discrete argmax only), regime-conditional expected-value ranker, daily IC-decay monitoring, base-effect forward projection, survivorship-corrected factor scorecard as the default, and OOS R2 benchmarking — the four gaps that separate a research-graded scorecard from a live edge-measurement system.

### Theme Baskets + Narrative Rotation
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `close-to-close-vol-only`, `no-uncertainty`, `heuristic-cone`, `win-rate-not-expectancy`, `no-transition-probability`
- **Upgrades proposed:** 10 (1 P0)
  - **[L3 / M] Regime-conditional basket return table (L3 core)** - Add engine/basket_regime_returns.py. For each basket in membership.json, load the EW level series via _ew_level (engine/baskets.py:67). Load the historical regime label series from data/regime/regime_history.parquet (or compute it daily from the axes history).
- **Verdict:** A well-engineered, honestly documented trend-following/crowding-throttled basket allocator that correctly admits rank-IC ~0 and grounds its one validated edge in drawdown avoidance, but entirely lacks regime-conditional expected-return estimation (L3), Markov-switching transition probabilities (L2), point-in-time data for historical calibration (L6), and any forward distributional output beyond heuristic composite scores — the subsystem is rigorous about what it is but missing the core edges the blueprint requires.

### Subsector Rotation / Subsectors Confluence Desks (RRG + Velocity + Index Leadership Rising Star + Running/Coiling)
- **Rigor flags:** `levels-not-ROC`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `no-uncertainty`, `heuristic-cone`, `win-rate-not-expectancy`, `no-transition-probability`
- **Upgrades proposed:** 10 (1 P0)
  - **[L3 / M] Regime-conditional emerging_score reweighting (L3 hookup)** - In engine/subsector_rotation.py _rotation_metrics() and engine/subsector_confluence.py score_group(), import engine.regime_snap.load_latest() to get the current confirmed quad + growth_score + inflation_score. Add a per-quad weight table (e.g., Q1: lift cyclic
- **Verdict:** The subsector desks are a well-constructed relative-strength + technical-entry timing system, but they are entirely decoupled from the macro regime engine — no quad conditioning, no P(Q1..Q4) probabilities, no conditional expected-value weighting, no drawdown-budget sizing — making the 'Hubble cross-sectional ranker' concept a display-only skeleton that needs L2/L3 wiring before it carries any forward-return expectation beyond heuristic emerging_score weights that are still in 'accruing' validation status after 3 days of logged calls.

### Factors Desk — cross-sectional equity factor engine, IC scorecard, factor series, factor exposure, and regime-conditional table
- **Rigor flags:** `levels-not-ROC`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-conditional-return`, `no-transition-probability`, `no-uncertainty`, `win-rate-not-expectancy`, `no-forward-projection`
- **Upgrades proposed:** 10 (2 P0)
  - **[L3 / M] Compute per-quad IC stratification table in factor_ic_scorecard.py** - In scripts/factor_ic_scorecard.py, after building the quarter grid, attach the realized regime label at each rebalance date by loading data/regime/regime_history.parquet (or data/regime_snap/ archive). For each (factor, quad_k) cell compute mean_ic, ic_ir, n_o
  - **[L6 / S] Run factor_ic_scorecard on de-biased (dead-name recovered) universe and make it the live scorecard** - Run scripts/factor_ic_scorecard.py --debiased to produce ic_scorecard_debiased.json once collectors/edgar_deadname_prices.py has accrued sufficient coverage (check _dead_name_price_coverage.json). In scripts/build_site.py _load_ic_scorecard(), prefer the debia
- **Verdict:** The factors desk has honest PIT IC accounting, solid factor construction, and a single validated regime-momentum lever in stock_score — but the L3 regime-conditional factor expected-value table (the blueprint's core alpha driver) is entirely absent: factors are never stratified by quad, regime probabilities are a hard argmax, and the one FDR-surviving factor (payout, IC=0.025) is diluted inside a negative-IC composite that no trader should size off.

### Cross-asset / transmission / forex / bonds — RORO, USD North Star, rate/inflation transmission, yield curve, forex regime scenarios, correlation-break detector, lead-lag
- **Rigor flags:** `market-proxy-not-econ-nowcast`, `first-deriv-not-second-deriv`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `no-transition-probability`, `heuristic-cone`, `no-uncertainty`
- **Upgrades proposed:** 13 (3 P0)
  - **[L2 / M] USD↔asset rolling-correlation BREAK detector (USD North Star edge #2)** - Add engine/usd_correlation_break.py. Inputs: broad-USD daily returns (drivers['broad_dollar']), per-asset daily returns (SPY, EEM, GC=F, HG=F, CL=F from yahoo store). For each asset: (a) compute rolling 63d and 252d Pearson correlation to USD return; (b) apply
  - **[L2 / L] Continuous regime probabilities P(Quad_k) with transition matrix (replace RORO argmax)** - Add engine/regime_hmm.py. Use hmmlearn (or statsmodels MS-ARIMA) to fit a 4-state Gaussian HMM on the daily [growth_score, inflation_score] from axes.py outputs (stored in data/regime/axes_history.parquet or reconstructed from conditions frame). States corresp
  - **[L1 / M] Base-effect 2nd-derivative forward projection for growth and inflation** - Add engine/base_effect.py. Inputs: FRED series (ALFRED vintage-keyed via Alfred API — use ALFRED observation_start + realtime_start to get point-in-time vintages; free API, no key required for vintage downloads of WEI, INDPRO, PCE). Method: (1) load the curren
- **Verdict:** The cross-asset/forex/bonds subsystem is architecturally honest and technically competent (absorption ratio, HAC/FDR lead-lag, Wilson-CI scenario probabilities, calibrated IC matrix, Newey-West MOVE-leads-VIX gating) but is entirely display-only with every scored-leg gate failing, runs exclusively on latest-revision data with zero vintage-awareness, uses a first-derivative market-proxy RORO with no distributional regime probabilities or transition matrix, and has no base-effect 2nd-derivative projection, no conditional expected-value ranker, no forward vol surface, and no structural correlation-break detector — the three real Hedgeye edges are all absent.

### BTC Vector regime scorecard — halving-cycle basis, macro composite, midterm gate, impulse radar, cycle thesis monitor, forward cones, recommend engine
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-transition-probability`, `heuristic-cone`, `no-uncertainty`, `no-conditional-return`, `win-rate-not-expectancy`
- **Upgrades proposed:** 12 (2 P0)
  - **[L2 / L] L2: Markov-switching regime probabilities — replace discrete argmax** - Add engine/btc_regime_hmm.py. Fit a 4-state Hamilton (1989) or Kim-Nelson regime-switching model on [net_liq_slope_z, real_yield_slope_z, mvrv_z, dxy_slope_z] daily series (2015->). States map to (liq_expand/contract) x (on-chain_cheap/rich) — BTC's 2-axis gri
  - **[L3 / M] L3: Regime-conditional expected-value ranker integrated with P(state)** - Add engine/btc_conditional_ev.py. For each composite_state label (ACCUMULATE/RISK-ON/NEUTRAL/RISK-OFF/DISTRIBUTE), compute mu_{a,k} = empirical mean 30d/90d forward return from calibration.json forward_paths conditioned on that state. Integrate: E[r] = sum_k P
- **Verdict:** The engine is honest and structurally sound (CONFIRMED risk_index drawdown read, measured valuation extremes, no overfit composite, documented coin-flip direction) but operates at L1-first-derivative with a hard argmax regime, no transition probabilities, no regime-conditional EV sizing, and no point-in-time macro data — all four of the blueprint's real edges are missing or only partially approximated.

### China/HK/Canada/Intl Regime & Sector Engines
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `no-transition-probability`, `no-uncertainty`, `heuristic-cone`
- **Upgrades proposed:** 12 (3 P0)
  - **[L2 / L] Regime probability distribution via Markov-switching (China primary, intl secondary)** - Add engine/china_regime_msm.py using statsmodels.tsa.regime_switching.markov_switching.MarkovRegression (or hmmlearn GaussianHMM) fit on the daily [growth_score, inflation_score] bivariate series from china_axes. 4-state model (Q1-Q4). Emit: P(Quad_k) for each
  - **[L3 / L] Regime-conditional forward return distributions for China sector allocation** - Add engine/china_regime_ev.py. For each Shenwan L1 sector and each quad (Q1-Q4): estimate mu_{sector, quad} = mean 21d and 63d forward return conditional on being in that quad, using the existing Shenwan deep history (data/china_sectors/ back to 1999). Use poi
  - **[L6 / M] Point-in-time regime labels for China split-half and walk-forward validation** - In scripts/calibrate_china.py, replace the current split-half with a walk-forward that generates regime labels using only data available as of the scoring date. Concretely: for each date t in the validation window, refit axis scores and quad classification usi
- **Verdict:** All four intl engines (China/HK/Canada/Intl) share the same first-derivative argmax quad template — no base-effect projection, no regime probability distribution, no conditional expected-value engine, no forward vol, no point-in-time validation — making them coincident market-proxy classifiers rather than forward economic forecasts; the HK global-risk overlay and China pathway Wilson-CI are the two genuinely differentiated elements, and both are explicitly display-only.

### User-facing presentation layer: macro regime / cycle / risk / nowcast UI (macro.html, us_stocks.html, dashboard.html.j2, engine/regime.py, engine/axes.py, engine/playbook.py)
- **Rigor flags:** `levels-not-ROC`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `point-not-distribution`, `revised-not-point-in-time`, `discrete-argmax`, `unvalidated-no-DSR-PBO`, `no-forward-projection`, `no-conditional-return`, `heuristic-cone`, `no-transition-probability`, `no-uncertainty`
- **Upgrades proposed:** 10 (3 P0)
  - **[L1 / M] Compute and display YoY base-effect forward path for growth and inflation axes** - Add engine/base_effect.py. For WEI (weekly, YoY-scaled) and sticky CPI (monthly YoY): (1) compute the known base denominator 4 quarters forward; (2) assuming sequential momentum holds at the trailing 13-week average, project the forward YoY path as a determini
  - **[L1 / M] Replace FRED latest-revision pulls with ALFRED real-time vintages for econ confirmers** - In collectors/fred_collector.py (or equivalent), switch payrolls (PAYEMS), INDPRO, and sticky CPI to ALFRED vintage-dated API: `https://alfred.stlouisfed.org/graph/fredgraph.csv?id=PAYEMS&vintage_date=YYYY-MM-DD` (keyless, same host). At build time, use today'
  - **[L6 / M] Surface regime confidence as a bootstrap CI instead of a heuristic scalar** - In engine/axes.py score_axis(), add bootstrap_ci(): resample the component score matrix 500 times with replacement across time (block bootstrap, block_size=20 trading days to respect autocorrelation), compute the distribution of axis_score, return p05/p95. Sto
- **Verdict:** The presentation layer is well-structured and honest about its limits, but it shows a first-derivative market-proxy argmax with a single point label and historical base-rate hover — missing base-effect forward projection (L1), continuous P(Quad) replacing the {0,1} locator (L2), conditional expected-value per asset (L3), index-level forward distribution cones (L4 — the infrastructure exists in forward_dist.py but is not wired), and a bootstrap CI instead of the heuristic agreement ratio (L6); the two highest-effort/highest-impact gaps for a real-money trader are revised-not-point-in-time data and the absence of any forward uncertainty surface.

### Portfolio construction / allocation — engine/portfolio.py, engine/masterminds.py, engine/active_alloc.py, engine/equity_alloc.py, engine/master_brain.py, engine/risk_sizing.py, engine/net_exposure.py, engine/vol_forecast.py
- **Rigor flags:** `close-to-close-vol-only`, `discrete-argmax`, `first-deriv-not-second-deriv`, `market-proxy-not-econ-nowcast`, `revised-not-point-in-time`, `heuristic-cone`, `no-conditional-return`, `no-transition-probability`, `unvalidated-no-DSR-PBO`, `point-not-distribution`, `no-forward-projection`, `win-rate-not-expectancy`
- **Upgrades proposed:** 10 (2 P0)
  - **[L6 / S] DSR + PBO gate on the full mastermind backtest scorecard** - In scripts/build_masterminds.py _detail_vm() (line 43), after computing bt = M.backtest(pk, P), call engine.validation.deflated_sharpe(bt['scorecard']['sharpe'], skew, kurt, T, n_trials=N_VARIANTS) where N_VARIANTS = number of profile variants ever tried (trac
  - **[L1 / M] ALFRED point-in-time lag fix for FRED macro carry inputs** - In engine/masterminds.py _conviction() carry block (lines 184-191): add per-series release lags matching equity_alloc.LEG_LAGS: DGS10 -> lag 2d (market rate, daily), BAMLH0A0HYM2 -> lag 2d, DFII10 -> lag 2d. These are already market-traded series so the lag is
- **Verdict:** The portfolio construction layer has a working, honestly-scored conviction-weighted vol-targeted GTAA engine with a clean cost model and split-half OOS, but it is missing the three specific L7 blueprint ingredients — HRP base (ERC exists but is display-only), Black-Litterman view-blending (no BL anywhere), and a regime-conditional CVaR drawdown budget — while the regime dial is static per-profile knobs rather than P(Quad)-driven gross/net; close-to-close vol only; no DSR on the live mastermind scorecard; and all macro carry inputs use latest-revision FRED data without ALFRED point-in-time vintages.

