# International System — Fix Masterplan (by Fable)

**Repo:** Macro Dashboard
**Date:** 2026-07-02
**Author:** Fable, solutioning the Opus problem audit `research/INTL_ENGINE_PROBLEM_AUDIT_FOR_FABLE.md` (INTL-1..35).
**Inputs:** the Opus audit (76 verified findings) · a Fable supplementary pass (6 seam-hunters + 3-lens adversarial judge panel, 9 agents) · the three pre-existing intl phase-0 reports · on-disk adjudication against **origin/main** (the audit ran on a checkout 363 commits behind main — see ADJ-1).
**North star:** upgrade the international system to institutional grade **specifically so it measurably improves US & China stock-signal accuracy and directional capacity** — better, quicker, honest signals; never noise theater.

---

## §0 — Executive thesis

Every intl/global edge this repo has **ever** validated is **drawdown-side, not return-side**:

| Validated result | Where | Shape of the edge |
|---|---|---|
| Intl macro de-risk sleeve (curve+Sahm+tightening, pooled JP/EZ/GB/KR) | `reports/intl-macro-sleeve-phase0.md` | **DSR 0.9978, split-half PASS**, MaxDD −39.2% vs −55.4% B&H — the strongest intl result in the repo, "closest to SCORED" |
| Price-index trend basket | `reports/intl-trend-overlay-phase0.md` | MaxDD −18.5% vs −57.0%; Sharpe edge FAILS split-half — DD-cut kept, return edge refuted |
| Total-return ETF overlays (sma200/tsmom/macro × EWJ/EWG/EWU/EWY/EWA) | `reports/intl-tr-trend-phase0.md` | ALL "no" — trend on tradeable TR intl is dead, same as the US kill |
| HK global-risk transmission | `engine/hk_global_beta.py` | ~2x global beta, per-name risk EXPOSURE — explicitly NOT selection alpha |
| China external-driver radar (breadth collapse, US rate shocks, US–CN differential, USD/CNH) | `engine/risk_radar_intl.py` (main, #711/#718) | Composite ≥10%/42d drawdown lift **2.07×** (p=0.01, 2016+ 2.53×), confirmed on CSI300; self-auditing, `can_force`-gated |
| Cross-market lead/lag screen (150 pairs × 5 lags, HAC + FDR) | `reports/cross-asset-leadlag-phase0.md` | All surviving intl→US/CN links are **timezone lag-1 artifacts** — naive read-through is NOT tradeable |

So the institutional destiny of this system is **not** a competing intl stock-picking desk. It is:

1. **A risk-transmission early-warning layer** for the US/China books — generalizing the already-shipped `risk_radar_intl` pattern (profile → forward log → graded audit → bounded auto-tune → `can_force`) into the scoring seams that actually size positions.
2. **A small set of pre-registered aggregate read-through sensors** (ETF/basket-level, never 50-name grids) held at context tier until they clear the lead-lag kernel.
3. **The comparative macro display, kept, honest** — with its data reservoir repaired so it stops lying by omission.

The Opus audit's centerpiece (the silo) is confirmed **on main**: zero `intl_*`/`forex_*`/`global_liquidity` imports in `stock_score.py`, `conditions.py`, `cycles.py`, `build_stock_library.py`, `build_china_library.py`. The bridge must be built — but built **into the seams that score**, with the validation constitution below, or it just launders decorative data into real-money trades.

---

## §1 — Adjudications & corrections to the audit

The audit is the problem record; these corrections govern how Fable reads it. **None of them weaken the central silo finding — they redirect the solution.**

- **ADJ-1 · STALE-TREE CAVEAT (governs everything).** The audit and the supplementary hunts ran on `redesign/risk-radar`, **363 commits behind origin/main**. Materially: `engine/risk_radar_intl.py`, `risk_radar_intl_audit.py`, `risk_radar_intl_tune.py` exist on main; `market_state_cn.py` on main wires `radar_override=_radar_override_intl` ("validated external-driver radar"). Any audit claim about *absence* must be re-checked against main before acting. The silo grep, the MRS-has-no-intl-leg claim, and the per-stock gap were re-verified on main and **hold**.
- **ADJ-2 · China external drawdown edge EXISTS and is validated** (contradicting the hunter, whose `china-conditions-calibration.md` citation covers only the old China-INTERNAL legs). The validated legs (2026-06-28, #711): breadth collapse lift 1.97–3.13×, US 2y/real-10y rate shocks 1.5–3.3×, US–CN 10y differential widening 1.61–2.78×, USD/CNH depreciation 1.9–2.6×; composite 2.07× (p=0.01), CSI300-confirmed. It runs **display-only until `can_force`** (≥30 graded, ≥8 alerts, realized lift ≥1.25×) — forward logs are committed and accruing (`data/risk_radar_intl/{cn,hk,ca}_forward_log.jsonl`). **Consequence:** the China side of the bridge does not need a new composite; it needs (a) maturation of this one, and (b) a per-stock consumption path.
- **ADJ-3 · "No validation exists" (INTL-9/10/12/16) is overstated.** Three phase-0 harnesses ran; all landed CONFIRMER. The *pooled macro sleeve* passed split-half + DSR and is promotion-adjacent. What's missing is validation for the *specific gauges the pages display* (recession score, equity-risk, basket momentum) — that part of the audit stands.
- **ADJ-4 · The sensor-array idea has a standing refutation prior.** `cross-asset-leadlag-phase0.md` screened 150 pairs × 5 lags with HAC-t + BH-FDR + split-half: the survivors are timezone lag-1 artifacts. And `narrative_crossmarket.py` already concluded thematic momentum is "NOT tradeable as a lead-lag signal." Any read-through channel therefore ships as **one pre-registered aggregate per mechanism** (not name grids), context-tier until it clears that same kernel.
- **ADJ-5 · Seam correction.** `market_state.py` is DISPLAY-ONLY by its own docstring — it is *not* the integration target. The real scoring seams (verified on main): `conditions._macro_risk_legs` (`conditions.py:851`) → `macro_risk_series × sector_macro_beta` (`playbook.py:547`) → master_brain macro-risk posture; `stock_score._edge_weights` calm master-switch (residual-momentum weight 0.28 calm → 0.04 stress, validated regime-switch IC ±0.03); `stock_score._axis_tailwind` (weight 0.10, spotlight tilt hook); `china_name_score._tailwind` (bounded [0.85, 1.15]); `conviction_profile` ctx (`risk_overlay`, `regime.calm` — the HK template injects here). A **display-vs-scoring manifest** is a W1 deliverable so "integrated" can never again mean "rendered."
- **ADJ-6 · Data-staleness numbers conflate two failure modes.** Genuine series-death (JP CPI 2021, KR CPI 2023, EZ unemployment 2023 — dead FRED-OECD ids) vs. checkout-staleness artifacts (closes "13d stale" partly reflects the stale worktree). W0 re-measures freshness on a current main checkout; fixes target the series-death class.

---

## §2 — Root causes (35 audit items + 17 supplementary → 6 causes)

- **RC-1 · Quarantine-as-honesty.** "Don't claim edge" was implemented as "don't export at all" (INTL-1/2/3/4/14/15/30/35). Fix = a *governed* export layer with the validation constitution (§4), not bare wires.
- **RC-2 · Dead-reservoir decay.** FRED-OECD died; collectors fail open; 200-OK-frozen-tail is invisible to `is_connection_error` (INTL-5/8/11/13/18/29/31/33). Fix = substrate-first data plan (§4.4) + frozen-tail detector in `run_status.json`.
- **RC-3 · Validation vacuum with an exception.** Page gauges unvalidated (INTL-7/9/10/12/25/28/34), yet the repo owns exemplary harness patterns (`calibrate_forex` verdict grammar, `risk_radar_intl_audit` forward-grading, `trial_ledger.py`, the leadlag kernel). Fix = ONE pluggable `scripts/intl_phase0.py` reusing those patterns.
- **RC-4 · Comparability illusion.** Renormalization drift, uniform hysteresis, own-history extension (INTL-17/19/21/22/23/27) — and deeper: the five bloc regime engines share `regime.raw_quad` **code** but feed it non-comparable axis inputs (US market-slope-z vs intl monthly econ-signs vs China PMI-levels), so "JP Goldilocks" ≠ "US Goldilocks" on any common scale (INTL-39).
- **RC-5 · Asymmetric desk depth → wrong mission.** The intl board mimics the US board it cannot be (INTL-7/16/20/33/34). Fix = reposition per §0; stop pretending to per-name intl alpha the repo's own 40y HK panel refutes.
- **RC-6 · Regime-dialect fork.** Six incompatible regime vocabularies (quad ×5 blocs / forex scenarios / vol risk-on-off / snap 0-1 / narrative NDI); no continuous P(Quad) exists anywhere (the Hedgeye program is documentation-only so far); `regime_snap_veto` vetoes nothing (INTL-40/41). Spillover is blocked on this *and* on data — sequence both before any regime bridge.

---

## §3 — Supplementary problem ledger (Fable pass; INTL-36..52)

Severity-ordered within tier. Every item verified with file:line by the hunt agents; ADJ-1 caveat applies (re-verify line numbers on main when executing).

- **INTL-36 (HIGH · feedback-gap)** — `risk_radar` (the repo's only evidence-gated leading-risk engine, ~1.5–2× conditional lift) dead-ends at page level: consumed by `market_state._radar_override` (page score ceiling), the baskets risk strip, and nothing per-stock. `build_stock_library` uses a SEPARATE `current_risk_overlay` (VIX pctile + conditions + OFR FSI + FOMC; `build_stock_library.py:214-261`) that never reads it.
- **INTL-37 (HIGH · feedback-gap)** — MRS has no intl leg: `conditions._macro_risk_legs` = {recession, drawdown, nfci, liquidity, transition}, all US-only. A validated intl macro crisis cannot veto US/CN buys through ANY code path. This is the single cheapest high-value wire in the whole program (C2).
- **INTL-38 (HIGH · coverage-gap)** — US `risk_radar` has ZERO global/USD legs (`risk_radar.py:201-247`: HY OAS, MOVE, SPY/SMH, XLU/XLY/XLP, VIX term — all domestic). The US book is blind to the global breadth/dollar channel even as a Tier-B candidate.
- **INTL-39 (HIGH · methodology)** — Shared quad NAME masks non-comparable axis SCORES across blocs (`axes.py:39-62` market slope-z vs `intl_regime.py:54-68` monthly econ signs vs `china_axes.py:52-66` PMI levels). Any bloc-spillover leg reading quad labels today mixes scales silently.
- **INTL-40 (HIGH · missing-feature)** — No continuous P(Quad)/base-effect forward regime exists anywhere (`playbook.py:170-185` is a discrete count Markov matrix; grep for softmax/logistic-quad returns nothing). The Hedgeye program direction is unbuilt; spillover conditioning has no probabilistic substrate.
- **INTL-41 (MEDIUM · naming/ux)** — `regime_snap_veto.py` vetoes nothing: display-only LLM durability annotation, US-RORO-only inputs. Rename or make it veto; don't route intl into it.
- **INTL-42 (HIGH · data/reproducibility)** — `data/intl/_etf_scratch/` was never committed → the tr-trend phase-0 is not reproducible; and NO country-ETF collector exists in the live pipeline (only FXI anywhere in `data/yahoo/`). 22 iShares country ETFs with 20y+ keyless USD total-return OHLCV history are available — the best substrate in the entire program, uncollected.
- **INTL-43 (MEDIUM · methodology/honesty)** — The forex 60-trial family: every pair fails DSR (best USDCAD 0.86 < 0.90); the broad-dollar REER value factor is CONFIRMED in both halves (IC +0.065/+0.077/+0.060) but killed by the family-wide DSR budget. Correct response: **pre-register REER as an N=1 hypothesis**, not quietly promote it.
- **INTL-44 (MEDIUM · no-validation)** — USDCNH: all 8 factors UNMEASURED (history too short for the standard split); `cnh_basis_bps` never calibrated against CSI300 forward returns despite `cny_shock` being an established China driver fingerprint (`china_market_drivers.py:72-82`) and a raw usdcnh leg already sitting in the China RORO (`china_conditions.py:161-163`).
- **INTL-45 (MEDIUM · feedback-gap)** — `forex_dollar.py:310-352` computes a full broad-dollar lean (real-rate regime + trend stack + liquidity + Fed path) → written to `data/forex/latest.json` for display only; no US small-cap/cyclical context flag consumes it.
- **INTL-46 (MEDIUM · feedback-gap)** — `cross_asset_confirm` is LIVE in `run.py` (verdict + caution flags) but its two leading legs (credit, curve — the ones with literature-backed lead) are never consumed upstream of stock scoring; `to_brain` feeds narrative text only.
- **INTL-47 (HIGH · data-rot)** — `site/markets_data.js` is fully static (asOf 2026-06-25, single commit, zero pipeline references): 9 markets' "now" blocks (levels, %-off-ATH, valuations) decay silently on a live page.
- **INTL-48 (MEDIUM · data-quality)** — Polymarket `recession` event key has matched 0 rows across all collection runs (`config.yml` match substring wrong); only fed_next/fed_cuts accrue. Also snapshots 4d stale vs `stale_after_days=3`.
- **INTL-49 (HIGH · data-quality)** — Sensor-grade data inadequacy: bellwethers exist in `intl_search` but only 5y deep, frozen-2021 origin, survivor-biased, close-only; ADR coverage is TSM-only (28y!) — ASML/BHP/RIO/HSBC/LVMUY/Samsung-proxies all missing; zero earnings-date awareness (read-through spikes around prints would be miscoded as trend).
- **INTL-50 (MEDIUM · methodology)** — The uniform macro gate HARMS Korea: EWY macro-gated MaxDD −79.3% vs B&H −74.1%. Per-market leg fitness must be measured, never assumed uniform (this is the intl echo of "hysteresis tuned on US data," INTL-27).
- **INTL-51 (LOW · data-quality)** — `global_liquidity` BoJ leg 2 months stale (JPNASSETS 2026-05-01 vs WALCL 2026-06-24) with no per-bank as-of surfaced; BoE/PBoC omitted entirely.
- **INTL-52 (MEDIUM · process/meta)** — Stale-worktree research hazard: this very program produced a false "China edge refuted" claim by auditing a 363-commits-stale checkout. Institutional-grade research requires an as-of-main gate: every problem-audit/hunt agent must record `git rev-parse origin/main` vs HEAD and re-verify absence-claims against main.

---

## §4 — Target architecture v2 (post-judge)

Three judges (quant-methodology, data/platform, institutional-PM) each returned **sound-with-modifications**. This section is the architecture with all accepted modifications folded in.

### 4.1 The governance machinery: generalize `risk_radar_intl`, don't invent a registry

The repo already ships the full governance pattern on main: **profile-driven signal → committed forward log → deterministic grading vs realized outcomes → bounded do-no-harm auto-tune → `can_force` maturation gate (display-only until the signal's own graded track record clears thresholds)**. That is the Bridge Registry, already battle-tested. The bridge generalizes it:

- `engine/intl_feed.py` — a stateless leaf (imports nothing from the scoring core) that reads the phase-0 ledger + upstream outputs and emits **features with contracts**: `{feature, source_series[], last_asof, data_age_risk, verdict, IC, DSR, effective_n_crises, weight_cap, direction_constraint, kill}`.
- The ledger is **emitted by the validation harness** (`scripts/intl_phase0.py`, §4.2) as machine-readable JSON — Layer 1. `intl_feed.py` is a thin consume-time reader that zeroes anything stale/unvalidated — Layer 2. **No standing service, no hand-maintained sync** (platform judge must-have).
- **Verdict grammar** (ported from `calibrate_forex`): CONFIRMED / DIRECTIONAL / CONTEXT / INVERTED. **Three-state weight policy** (PM judge): CONFIRMED → full measured weight; DIRECTIONAL → half weight, de-risk-direction-only; CONTEXT/INVERTED-unresolved/STALE → exactly zero + display flag.
- **Conflict arbitration, first-class registry field** (PM judge must-have): **de-risk legs strictly dominate add/tilt legs.** An add-tilt fires only if CONFIRMED *and* no de-risk leg is firing on the same book. This resolves "dollar gate says de-risk, semi sensor says add" by construction — consistent with the fact that every validated edge here is drawdown-side.
- **Per-leg kill switch + forward outcome log**: every fired veto/tilt is graded vs realized US/CN forward returns and drawdowns (the `risk_radar_intl_audit.snapshot_and_grade` pattern), feeding the admin Experiments tracker. The system must be able to demonstrate, out of its own logs, that it helped.

### 4.2 The validation constitution (one harness, one budget, hard gates)

`scripts/intl_phase0.py` — pluggable claims, standard gates, ledger output. Non-negotiables (quant judge must-haves):

1. **One pre-registered trial-budget family** in `engine/trial_ledger.py`, declared at kickoff over the FULL claim × horizon × target grid — the forex declared-N=60 discipline. No post-hoc horizon/name selection, ever.
2. **Incremental-IC / orthogonality gate**: every candidate leg is partialed against the existing MRS legs + RORO + `hk_global_beta`; it must show statistically significant RESIDUAL forward-DD-reduction. Fails → weight 0 (kill switch), so nothing double-counts into sizing.
3. **Honest effective-N accounting**: DD-side edges rest on ~3–5 independent crises, not thousands of rows. The ledger stores BOTH the daily-row CI and the block-bootstrap-by-crisis/LOCO result; **weight caps scale with independent-bear count**; user-facing surfaces must say "crisis-count tail insurance," never imply daily-n Sharpe.
4. **Crisis-independent expected-shortfall test** (PM judge): a de-risk leg must show positive ES reduction after row-deleting the top-3 drawdown windows, OR ship explicitly labeled a crisis-only circuit-breaker.
5. **The lead-lag kernel** for any cross-market claim: HAC-t + BH-FDR across the entire declared grid + split-half same-sign-and-|t|≥2 (`cross-asset-leadlag-phase0` pattern). Standing prior: survivors are timezone lag-1 → default outcome is "transmission read," not tradeable lead.
6. **Fail-closed freshness**: per-leg `data_age_risk`; any stale critical component (CPI>365d, unemployment>180d, price>3d) forces the dependent feature to zero — never a silent ffill. Verified by a test that a 13-day-old print zeroes the leg.
7. **`intl_phase0` CONFIRMED + DSR ≥ 0.90 is the ONLY door** from a feature into any position-sizing seam. Measured-weights-never-priors.

### 4.3 The display-vs-scoring manifest

A committed doc + machine-readable map naming which seams are badge-only vs which change size/gates. Initial map (verified on main): **scoring** = `conditions._macro_risk_legs` → `macro_risk_series × sector_macro_beta` (`playbook.py:547`) → master_brain posture; `stock_score._edge_weights` calm switch; `stock_score._axis_tailwind`; `china_name_score._tailwind`; `conviction_profile` ctx; the China board entry gate; `risk_radar_intl` post-`can_force`. **Display** = `market_state.py` (all markets), intl pages, forex pages, cross-asset page. Every wire in §5 names its seam from this manifest.

### 4.4 The data plan: substrate-first, aggregator-last

- **Country-ETF total-return substrate FIRST** (v1/v2 backbone): ~22 iShares country ETFs + the 6 phase-0 tickers, keyless yfinance, 20y+ USD OHLCV, survivorship-free, already local in kind. **All net-new collection lives OUTSIDE the daily 100-min critical path** (weekly workflow or dedicated intl workflow; macro is monthly-cadence anyway). Commit the store (fixes INTL-42 reproducibility).
- **ADR mini-set, not 50 locals**: ~10 US-listed sensor proxies (TSM exists with 28y; add ASML, LVMUY, BHP, RIO, HSBC, plus 2-3 more) — deep history, US-session timing (kills the lag-1 ambiguity), tiny yfinance surface growth.
- **Frozen-tail detector before any new macro leg** (platform judge must-have): on every fetch, assert the last observation advances within the series' expected cadence; a 200-OK frozen tail trips a NAMED `stale_series` failure in `run_status.json` (the exact failure mode that silently killed JP/KR/EZ macro).
- **Macro spine repair**: re-map dead FRED-OECD ids to live equivalents where they exist; **DBnomics only as a v3 spike**, raw-REST through `collectors/base.py` `http_get` (no new pip dependency — the akshare scar, `requirements.txt:18`), gated on a point-in-time/first-print-vs-revised integrity test. National scrapers are a last resort (highest-maintenance class; solo maintainer).
- **Deprecate honestly**: dead M2 series removed from display; every intl surface renders per-leg freshness + verdict badges (extend the `intl_inputs.macro_freshness` greying pattern).

---

## §5 — The channel book (pre-registered; verdict-tier capped)

Each channel: mechanism → prior evidence → pre-registered spec → gate → wire seam. **The full grid below is declared as one trial family in `trial_ledger.py` before any scan runs.**

- **C1 · Global-beta size-dampener (the v1 flagship).** Port `hk_global_beta` (causal rolling beta to lagged S&P factor, Vasicek-shrunk) to the China book (and evaluate for US high-beta names). De-risk direction ONLY: high-global-beta names get size/stop dampening when the global risk state deteriorates. Prior: HK validated in-shape (~2x transmission); note China A couples less than HK (~2x ratio, `china_global_factors`) — measure, don't assume. Gate: incremental over the existing CN RORO. Seam: `china_name_score._tailwind` (bounded) + `conviction_profile` ctx.
- **C2 · MRS intl macro-sleeve leg (the cheapest honest wire).** The pooled sleeve (curve-inv + Sahm + short-tightening across JP/EZ/GB/KR, ≥2 legs firing) is the repo's strongest intl result (DSR 0.9978, split-half PASS). Add as a sixth `_macro_risk_legs` leg with **measured** weight; drop KR from the pooled gate pending INTL-50 re-fit. Gates: orthogonality vs the 5 US legs (the growth-scare information may partially overlap NFCI/liquidity), crisis-independent ES test, freshness-gated on the repaired macro spine legs it needs (curve/short rates are LIVE — `AU/JP/KR_yield_10y` current through 2026-05; it does NOT need the dead CPI series). Seam: `conditions._macro_risk_legs` → flows automatically into `macro_risk_series × sector_macro_beta` and the master_brain posture.
- **C3 · Global ETF breadth barometer.** % of 22 country ETFs > 200dma (+ 63d slope). Pre-registered hypothesis: breadth < threshold leads SPX/CSI300 ≥5% drawdowns at 21–42d. Prior: breadth-collapse is the STRONGEST leg inside `risk_radar_intl.CN` (lift 1.97–3.13×) — this is its global analog. Gate: full constitution; orthogonality vs US radar's domestic legs. Seams: US `risk_radar` Tier-B candidate leg (fixes INTL-38) + a `risk_radar_intl` profile leg.
- **C4 · Dollar channel, three prongs.** (a) REER broad-dollar value factor, **pre-registered N=1** (it already CONFIRMED both halves; the 60-trial budget killed it — this is the honest resurrection path). (b) `dollar_desk` lean → CONTEXT flags on IWM/cyclical baskets (display first; promotion only through the harness). (c) `cnh_basis_bps` calibrated vs CSI300 63d forward → China RORO second leg beside the existing raw usdcnh leg. Prior: every per-pair forex conviction FAILS DSR — so no pair-level gating, ever (INTL-43 discipline).
- **C5 · Global-rates leaf.** `avg_10y` + `us_premium_bp` already computed in `bond_health.json` (INTL-15). Leaf module + orthogonality vs existing US curve/credit legs; duration/growth-beta headwind read. Seam: MRS candidate leg or sector-tilt context; BTC duration channel as a side consumer.
- **C6 · Asia-semi aggregate read-through.** ONE pre-registered equal-weight Asia-semi sensor basket (ADR-preferred: TSM + Samsung-proxy + SK Hynix local + Tokyo Electron/Advantest locals + ASML) vs SMH at ONE pre-registered horizon, earnings-print windows excised (the `calibrate_forex` peg-excision pattern). Context tier until it clears the lead-lag kernel; if only lag-1 survives → it becomes a *transmission read* (overnight risk carry-in), which is still useful as a de-risk confirmer, honestly labeled. Seam if promoted: `stock_score._axis_tailwind` bounded leg, DOWNGRADE-capable only.
- **C7 · Luxury→China-consumer aggregate.** Same discipline: one EW basket (LVMUY + Richemont/Hermès locals) vs a CN consumer target basket. The unique value: a *policy-undistorted* read on the Chinese consumer. Same kernel, same context-tier default, de-risk grain first (luxury rolling over → trim CN-consumer conviction).
- **C8 · Cross-asset leading votes → fractional MRS booster.** `cross_asset_confirm.to_brain.leading_caution_votes ≥ 2` while verdict=diverge → small MRS bump. Already computed live (INTL-46); needs only the orthogonality gate + measured weight.
- **C9 · Regime spillover — LAST.** Blocked on (i) macro spine repair, (ii) quad-dialect unification: a continuous P(Quad) substrate (softmax over axis distances) + comparable axis construction + component-availability persistence (INTL-17/39/40), built jointly with the Hedgeye program so there is ONE quad language. Only then: bloc aggregation → lagged spillover phase-0. Highest potential, lowest readiness; do not let it block C1–C8.

---

## §6 — Waves

Model routing per the standing tier rule: Opus = design/judgment, Sonnet = implementation, Haiku = mechanical chores. Every wave: branch off **main**, PR, squash-merge same-day. Every code deliverable lands with its test and its ledger entry.

### W0 — Substrate & hygiene (unblocks everything; Sonnet + Haiku)
1. Country-ETF collector (22 tickers + EWQ etc.), weekly workflow, committed store `data/intl_etf/` (INTL-42). *Sonnet*
2. Frozen-tail `stale_series` detector wired into `run_status.json` + per-leg freshness badges on intl pages (RC-2). *Sonnet*
3. Macro spine triage: re-map JP/KR CPI + EZ unemployment to live FRED ids where they exist; kill dead M2 from display; re-measure all freshness on current main (ADJ-6). *Sonnet*
4. ADR mini-collector (~10 sensor proxies) into the existing `yahoo` group, weekly. *Sonnet*
5. Chores: `markets_data.js` "now"-stanza refresher + staleness banner (INTL-47); Polymarket recession match fix (INTL-48); BoJ per-bank as-of surfacing (INTL-51). *Haiku/Sonnet*

### W1 — The constitution (Opus design, Sonnet implementation)
1. `scripts/intl_phase0.py` harness: pluggable claims, gates 1–7 of §4.2, JSON ledger emission; declare the FULL C1–C8 trial family in `trial_ledger.py` **before any scan runs**.
2. `engine/intl_feed.py` stateless reader + feature contract + three-state weights + arbitration field.
3. Display-vs-scoring manifest (committed doc + map used by tests).
4. Backfill the ledger with the already-run evidence (3 phase-0 reports, forex calibration, leadlag screen, risk_radar_intl validation) so the registry starts truthful, not empty.

### W2 — First validated wires (the program's proof of value)
1. **C2** MRS intl-sleeve leg: orthogonality + ES gates → measured weight → `_macro_risk_legs`. *Opus validates, Sonnet wires*
2. **C1** China global-beta: measure transmission on CN names; if it clears, wire the size-dampener. *Opus + Sonnet*
3. **C3** global breadth phase-0 on the W0 ETF store. *Sonnet harness run, Opus verdict*

### W3 — Dollar & rates channels
**C4** (REER N=1 pre-registration; dollar-lean context flags; CNH-basis China calibration) + **C5** (global-rates leaf + orthogonality) + **C8** (leading-votes MRS booster).

### W4 — Read-through aggregates (context tier)
**C6** Asia-semi + **C7** luxury→CN-consumer through the lead-lag kernel with print-window excision; ship as display confirmers with forward logs; promotion only on kernel clearance. Also: `risk_radar_intl` maturation review (are CN/HK/CA logs approaching `can_force`?) and US radar Tier-B global-breadth leg from C3 if validated.

### W5 — Regime unification & spillover (**C9**; joint with the Hedgeye program)
Continuous P(Quad) substrate → comparable axes → component persistence → DBnomics vintage-tested spike → bloc spillover phase-0. Explicitly LAST; explicitly allowed to conclude "no edge."

**Program-level acceptance:** by end of W3 the system must demonstrate, from its own forward logs, at least one intl-sourced leg that measurably improved US or China de-risk timing (graded TP/FP vs realized drawdowns) — or the masterplan's §0 thesis gets revisited in public, in this file.

### Status log
- 2026-07-02 — Masterplan authored (Fable), from the Opus audit + 9-agent hunt/judge pass + on-main adjudication. W0 delegation next.
- 2026-07-02 — W0 items 1+4 shipped (macro#910). **Country-ETF substrate**: `collectors/intl_etf.py` → `data/intl_etf/`, 23/23 tickers verified (EW* family + INDA/EIDO/EZA), full OHLCV total-return, cold-start max history + 45d incremental overlap, coverage gate ≥80% FAILS CLOSED (reverses INTL-29), weekly `intl_etf.yml` workflow in the pipeline-batch lane (daily 100-min path untouched). **ADR sensor mini-set**: ASML/LVMUY/BHP/RIO/VALE/HSBC/SONY added to the yahoo group (TSM already present, 28y) — the C6/C7 deep-history substrate. 13 tests.
- 2026-07-02 — W0 item 5 shipped (macro#915). **markets_data.js rot** (INTL-47): staleness banner (>5d, bilingual) + `scripts/refresh_markets_now.py` now-stanza refresher wired fail-soft into the build (7/9 markets on first run). **Polymarket recession key** (INTL-48): root cause = Gamma API caps 100 events/page; `_fetch_active` now paginates ×8 — recession event lands (prob 0.115). **global_liquidity per-bank as-of** (INTL-51): `asof_by_bank` in the snapshot + inline dates on the cross-asset page; BoJ 2-month staleness now visible.
- 2026-07-02 — W0 items 2+3 shipped (macro#912). **Frozen-tail detector** wired into `collectors/base.py::run_adapter` — after every successful fetch, `detect_stale_series` compares per-series last-obs against `cadence_days × 3` and writes named `stale_series` entries to `run_status.json` (non-fatal; reusable by any adapter). **Macro spine triage** (on-disk freshness measured against origin/main as of 2026-07-02): KR_cpi_yoy re-mapped `CPALTT01KRM659N` (frozen 2023-11) → `KORCPICORMINMEI` (OECD core CPI index, live 2025-04; auto-YoY via existing `is_index` path). JP_cpi_yoy (`CPALTT01JPM659N`, frozen 2021-06) and EZ_unemployment (`LRHUTTTTEZM156S`, frozen 2023-01) confirmed dead — no live keyless FRED replacement exists; both removed (engine already gates real_yield on CPI freshness; unemployment shows N/A). Dead M2 series (JP/KR/EZ frozen 2017; GB frozen 2023) removed from config — M2 is not rendered in the intl template so removal is an honest deprecation, not data loss. **Remaining dead/stale on-disk** (pre-next-collect): JP_cpi_yoy last 2021-06, EZ_unemployment last 2023-01, JP/KR/EZ/GB_m2 last 2017 — these are now absent from the collection plan so the detector will no longer flag them; they remain in parquet for historical reference. AU_cpi_yoy (quarterly, last 2025-01) and GB_cpi_yoy (last 2025-03) are stale-but-live (FRED publishing lag). 12 tests added in `tests/test_stale_series_detector.py`.
- 2026-07-02 — **W1 item 1 shipped** (the validation constitution — harness + trial-family + backfill). `scripts/intl_phase0.py`: a pluggable CLAIM harness that COMPOSES the anti-overfit stack (`trial_ledger` family **intl_bridge**, `promotion_gate` dsr_min=0.90, `validation.py` primitives) and adds only the intl-specific gates — orthogonality (residual forward-DD vs US MRS/RORO/hk_global_beta legs via `resid_z`), crisis-count effective-N (block-bootstrap-by-crisis + LOCO, weight_cap scales with independent-bear count), crisis-independent expected-shortfall (top-3 DD windows row-deleted → `crisis_only` flag), the lead-lag kernel (HAC-t + BH-FDR across the whole grid + split-half), and fail-closed freshness (per-series SLA on disk). `engine/intl_claims.py` declares the **17-config** C1-C8 claim×horizon grid as data (`--declare` logs it at generation; idempotent — re-runs don't inflate N). Verdict grammar CONFIRMED/DIRECTIONAL/CONTEXT/INVERTED/PENDING with the three-state weight policy (CONFIRMED → measured cap; DIRECTIONAL → half, de-risk-only; else 0). `--backfill` writes `data/intl_bridge/ledger.json` (the exact schema the sibling `engine/intl_feed.py` reads) with **7** truthful evidence rows: c2_intl_macro_sleeve PENDING (DSR 0.9978 + split-half PASS, but orthogonality + ES gates not yet run), intl_trend_overlay + intl_tr_trend + forex_per_pair_conviction + crossmarket_leadlag + cn_external_radar all CONTEXT, c4_reer_value PENDING (N=1 resurrection). All caps 0 (nothing wired into scorers — that is W2). Mirrored into `engine/signal_lab.py` (5 rows: 2 pending, 3 display) so the intl graveyard is published. 14 harness tests + 1 signal_lab graveyard test; trial-registration lint clean. Does NOT touch the scoring core.
- 2026-07-02 — **W0 COMPLETE** (#910/#912/#915, all squash-merged same-day). W1 (the constitution) dispatched: `scripts/intl_phase0.py` claim harness + `engine/intl_feed.py` Layer-2 reader + display-vs-scoring manifest + ledger backfill. Design refinement from on-main recon: the harness COMPOSES the existing anti-overfit stack — `engine/promotion_gate.py` (DSR+PBO+CPCV+drift+holdout, advisory), `engine/trial_ledger.py` (family `intl_bridge`, logged at generation), `engine/validation.py` primitives — and adds only the intl-specific gates (orthogonality vs MRS/RORO/hk_global_beta, crisis-count effective-N, crisis-independent ES, lead-lag kernel, freshness SLA). Ledger entries mirror into `engine/signal_lab.py` tiers so the intl graveyard is published like every other signal family.

---

## §7 — Refuted / dropped during solutioning (so nobody chases them)

- "Wire the China divergence radar (`china_radar.py`) or the china_conditions drawdown gauge into entry gates" — both self-declared no-edge; the validated China vehicle is `risk_radar_intl.CN` (ADJ-2).
- "50-name sensor lead/lag scanning" — refuted by the standing leadlag kernel result; replaced by pre-registered aggregates (ADJ-4).
- "Route intl through `market_state` / `regime_snap_veto`" — display-only / vetoes-nothing respectively (ADJ-5, INTL-41).
- "Per-pair FX conviction gating on equities" — every pair fails DSR (INTL-43).
- "DBnomics as the immediate macro spine" — demoted to a v3 vintage-tested spike; substrate-first instead (§4.4).
- "The hunter's claim that China has no validated external drawdown edge" — stale-tree artifact; `risk_radar_intl` exists on main with committed forward logs (ADJ-1/2).
