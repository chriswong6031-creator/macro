# Bitcoin Vector — Problem Audit for Fable 5

> **Type:** Problem-finding deliverable (problems only — no solutions).
> **Produced:** 2026-07-01 by an Opus deep-reasoning pass (see *Method & provenance* at the end).
> **Audience:** Fable 5, which will (a) deep-reason novel, unique solutions to these problems and (b) design a phased program to execute the fixes. Secondary audience: the owner, who risks real capital off this dashboard.
> **Scope:** `site/vector.html` (Bitcoin Vector) + `vector_allocation.html` + `btc_strategy.html` and the engines behind them (`engine/btc_signals.py`, `btc_regime*.py`, `btc_cycle_thesis.py`, `btc_recommend.py`, `btc_dat.py`, `scripts/build_vector.py`, `scripts/calibrate_vector.py`).

## How to use this document (Fable)

This is a *problem statement*, not a spec. Every problem below carries: a precise statement, **file:line evidence** verified against the current tree, the **real-money failure mode**, and **open questions for you to solve**. Do **not** treat the "open questions" as leading you to a predetermined answer — several plausible fixes conflict with each other and with the genuine strengths listed in *"What is already good and must be preserved."* Your job is to deep-reason the solution space, resolve those tensions, and *then* propose a phased program. The appendices give you (A) the strongest defense of the current design so you don't over-correct, and (B) emergent problem-combinations + a *starting hypothesis* for phasing that you should critique, not adopt wholesale.

## The originating concern (owner's words)

> "BTC's *Cycle Phase Clock* is only n=3 and has a small sample size, but we persist to believe it is one of the core strategies to avoiding BTC's 1-year bear-market drawdowns, and persist to believe not to hold BTC during these 1-year bear markets."

The audit confirms this concern is real and materially understated. The n=3 belief is not merely *displayed* — via the **midterm-election blackout** it is the single rule that forces the live model to **0% BTC for all of 2026**, and (the deeper finding) it was wired into the system in the one place that exempts it from every check the repo built to catch exactly this kind of low-sample discretionary call. What began as "is the clock trustworthy?" resolves into a structural governance problem that contaminates backtests, a sibling asset (ETH), the alert stream, and two dashboard pages.

## Executive summary

The Bitcoin Vector product is architecturally sound in its measurement stack but is compromised by a single design decision: the midterm-election blackout gate (a discretionary, n=3, calendar-only rule forcing 0% BTC for all of 2026) was baked inside the shared allocation() primitive as the final overriding mask. This one placement contaminates every downstream artifact — the DSR "SURVIVES 0.9947" verdict is computed on the gated series while the gate itself is absent from the degrees-of-freedom count; the ETH sleeve inherited the poisoned benchmark by reusing the same allocation() function; the alert stream actively misattributes the gate's 0% to the "momentum × risk grid"; and two dashboard pages relabel the override as a "Proprietary cycle timer" after deleting the pre-committed n=3 caveats. Compounding the statistics, the gate is decoupled from all four of the system's own pre-committed falsifiers (dampening/timing/desync/structure), which fire only into a display color and cannot lift the gate — several of which are structurally incapable of firing during the very window the gate is active. On the decision-theory side, the acknowledged amplitude-dampening trend (-84% → -77% → -52%) is trending the fixed-cost/shrinking-benefit blackout toward negative expected value, yet no breakeven-vs-bear-depth or gate-off-but-brake-on counterfactual exists anywhere. The genuinely strong design choices — the KEEP-HEURISTIC honesty (the fancy ensemble lost OOS and the system shipped the loser's verdict), the display-only regime firewall, the measured MVRV-Z edge, the disciplined ±5pp soft path, and the config-toggle legibility of the override — must be preserved through any fix. Note for de-duplication: roughly a third of the raised findings are the same "gate not in DSR" fact counted seven ways, one refutes its own title, and three are already mitigated; this deliverable merges them into single load-bearing problems. The strongest true finding is narrow and singular: the gate sits in the numerator of the certified backtest but outside the denominator of every overfitting control, with no evidence-driven off-ramp.

---

# Problem inventory (problems only — solutions are Fable's job)

## The meta-problem (root cause)

**A human conviction override was laundered through the engine's own validation, display, and falsification machinery so that it reads as a validated proprietary edge everywhere while being structurally exempt from every check the system applies to everything else.**

The midterm-election blackout — the single rule that forces 0% BTC for a full calendar year (currently all of 2026) — was placed at the one position that maximizes contamination and minimizes auditability: the final in-place mask inside the shared `allocation()` primitive (`engine/btc_signals.py` L545-546). From there it silently rewrites every backtest, alert, sibling-asset validation, and dashboard page that consumes the allocation series, while remaining invisible to the DSR, the trial ledger, the cross-validation folds, and the forward-grading ledger — the four instruments the repo built precisely to catch discretionary overfitting. It is *inside* everything it should be measured by, and *outside* everything that should measure it. The corollary the fix program must internalize: **the engine has no concept that a rule which sizes money must also be graded like one.** Sizing authority (the gate) and falsification authority (the ledger/DSR/thesis monitor) are wired to different objects. Fix the coupling, not the ~40 symptoms.

A note on this inventory: the raw finding set contained heavy duplication (the "gate absent from the DSR" fact appears in at least seven separate high/critical entries, two of which admit the overlap in their own text), one finding whose body refutes its own title, and three already-mitigated items. Those are merged, demoted, or moved to the "preserve" section below so the true structure is legible.

---

## Theme A — Circular validation & the invisible degree of freedom

### A1. The gate is baked inside `allocation()`, so it is in the numerator of every certified backtest but the denominator of no overfitting control
**Severity: critical**

The midterm gate is applied as `raw = raw.mask(gate, 0.0)` — the final, unconditional transform inside `allocation()` (btc_signals.py L545-546), masking all four variants. Every equity curve, scorecard, and the DSR-certified backtest that `compute_all()` → `alloc_*` feeds is therefore gate-baked (calibrate_vector.py L416, L619-622; build_vector.py L2226/L2230). Yet the degrees-of-freedom deflation that stamps the engine "SURVIVES" (DSR 0.9947, n_trials=50) counts only 4 grid variants + 32 signal families + a declared budget of 50; a full-text grep of `calibrate_vector.py`, `trial_log.json`, and `calibration.json` for midterm/blackout/election/gate returns zero hits. Because the gate is a single binary rule applied identically to all variants, it contributes no cross-variant Sharpe dispersion and is thus doubly invisible to the DSR. The result is a closed loop: the most consequential discretionary rule improves the reported Sharpe, those numbers are shown as the edge, and the certificate designed to catch exactly this never penalizes it.

**Evidence:** btc_signals.py L527-528, L545-546 (gate inside allocation); config.yml L3315-3317 `midterm_gate.enabled=true`; calibrate_vector.py L416, L619-622 (backtest on gated `alloc_*`); calibration.json L5112-5124 (dsr 0.9947, sr_annual 1.41, n_trials 50, verdict SURVIVES); trial_log.json (32 families, n_trials_declared 50, zero gate references).

**Failure mode:** In 2026 the gate forces 0%. If BTC rises through the midterm window the strategy badly underperforms HODL, but calibration.json still reads "Sharpe 1.44, SURVIVES" because those numbers were baked from 2015/2019/2023 history where the gate helped. The owner (or a subscriber) cites "DSR 0.9947" as proof the 0%-for-a-year call is validated, when the DSR never tested it.

**Open questions for Fable:**
1. How should the gate be re-expressed so the certified backtest and the DoF-haircut see the *same* object — e.g. an ungated `alloc_optimal_raw` twin plus the gate as an explicit, counted trial?
2. What is the honest number of degrees of freedom the gate consumes (the decision-to-gate, the year%4==2 selector, the Jan-1→vote window shape), and how should it enter `n_trials`?
3. Is the correct headline "gated vs ungated A/B, both reported," and if so what governs which one is the default the UI shows?

### A2. The ETH sleeve inherited the poisoned benchmark by reusing the same `allocation()`
**Severity: high**

The circularity is not BTC-only. The ETH Vector was validated by *reusing* `btc_signals.allocation()` (eth_vector_phase0.py L121/L257; `source="…engine/btc_signals.py allocation()"` at signal_lab.py L643), so every ETH gate — its DSR, split-half, leave-one-crisis-out, and brake-matched-200dma comparison — runs through the same gate-masking `allocation()`. The signal_lab record even quotes "DSR 0.9965" as BTC's SCORED benchmark that ETH "fails to clear" (signal_lab.py L625). The single most-cited robustness number in the entire crypto suite is a gate-baked figure, and ETH's whole comparison frame ("aligned with the scored BTC Vector") inherits the contamination.

**Evidence:** eth_vector_phase0.py L121, L257; signal_lab.py L625 (DSR 0.9965 quoted as scored benchmark), L643 (source pointer to btc_signals allocation).

**Failure mode:** A fix to the BTC DSR that does not re-run ETH leaves the sibling silently pointing at the stale, gate-baked benchmark, and the two-asset crypto sleeve continues to read as a portfolio-level validated system built on one laundered number.

**Open questions for Fable:**
1. Should ETH be re-validated against the *ungated* BTC benchmark, and does any ETH-specific gate even make sense (ETH has no halving/midterm mechanism)?
2. How do we prevent future shared-primitive reuse from silently propagating a discretionary BTC rule into unrelated assets?

### A3. The alert stream and home hub *fabricate* a "grid" attribution for the gate
**Severity: high**

`btc_alerts.py` L274-284 reads the *gated* `sig["alloc_optimal"]` and, on the Jan-1-2026 transition to 0%, emits "Allocation changed to 0% BTC / Optimal strategy moved X% → 0% BTC **(momentum × risk grid)**." This is an active misattribution: the alert names the momentum×risk grid as the cause of a move the calendar gate produced, and it fires into `alerts.jsonl` (consumed by the home hub). The UX-honesty findings covered the *page* headline but missed that a second surface with its own audience propagates a false causal story, and the alert `id` dedups across sentinel + daily recompute so it is durable.

**Evidence:** btc_alerts.py L274-284 (reads gated alloc_optimal, attributes to grid); alert dedup id persists across recompute.

**Failure mode:** During a 2026 rally the home hub surfaces "Optimal strategy moved to 0% (momentum × risk grid)" — telling the user the *measured* signals demanded cash, when in fact the calendar override did. The user cannot even locate the true cause.

**Open questions for Fable:**
1. What is the correct attribution vocabulary when a gate overrides the grid — how should the alert name a *discretionary override* vs a *measured signal*?
2. Should the alert stream carry the same gated-vs-ungated dual read the pages should?

### A4. The shipped DSR artifact is stale vs config (n_trials 50 vs 65) — but this is a reproducibility nit, not a fragility signal
**Severity: low**

The shipped calibration.json / trial_log.json record n_trials=50 while config.yml was later bumped to 65 (config.yml L3665) and the artifact never regenerated. Importantly, the finding's own reconstruction shows regenerating at 65 — or even at a defensibly larger ~200 — does *not* flip SURVIVES (DSR stays >0.95 until N is well past 500, because annual Sharpe ~1.41 over 4182 days dominates the haircut), and the DSR is not rendered to subscribers. This belongs here only to be explicitly *de-escalated*: it is artifact-vs-config drift worth a one-line reproducibility fix, and is evidence the edge is *robust* to plausible DoF counts, not that it is fragile.

**Evidence:** config.yml L3665 n_trials:65; calibrate_vector.py L617 default 50; calibration.json L5118 n_trials:50; trial_log.json L3 n_trials_declared:50.

**Failure mode:** Minimal — internal reproducibility only. Flagged so Fable does not spend critical-path effort on it.

**Open question for Fable:** Only "regenerate on config change" as a hygiene process — not a decision problem.

---

## Theme B — The self-contradicting double standard (gate vs prior)

### B1. The same class of low-n cycle belief is a capped ±5pp "never a trigger" prior in one path and an uncapped 100%→0% override in another
**Severity: critical**

The system encodes sibling calendar-cycle convictions under two logically incompatible disciplines in one engine. The 1064/364 phase enters as a deliberately gentle prior (build_vector.py L263-274): fixed ±5pp, sign-fades toward the opposite direction inside the reversal zone, output hard-clamped to [0.30,0.70], commented "never a trigger." Its sibling belief — midterm capitulation — enters `allocation()` (btc_signals.py L545-546) as `raw.mask(gate,0.0)`: uncapped, unfaded, non-shrunk, and applied as the FINAL word over grid/conviction/brake/overlay for every variant. There is no attenuation lever for the hard path (config exposes only `enabled` + `buy_lead_days`, which shifts the release date, not the strength), whereas the soft path carries floor/ceil/tilt/zone guardrails. In any year%4==2 the entire calibrated stack is silently zeroed by an uncapped fiat override, in the single place the marketed anti-overfit machinery is switched off.

**Evidence:** build_vector.py L263-274 (soft: capped, ±5pp, fades, "never a trigger"); btc_signals.py L525-546 (hard: uncapped final mask); config.yml L3553 `cycle_tilt_pp:5` vs L3315-3317 `midterm_gate.enabled:true` with no attenuation parameter.

**Failure mode:** In any midterm year the momentum grid, conviction sizing, brake, bottom overlay, and MVRV-Z accumulate are all silently zeroed; the user believes a rigorously-capped model is running when an uncapped fiat override is running.

**Open questions for Fable:**
1. Should the hard path be re-expressed in the soft path's grammar (a large-but-capped, evidence-fading tilt) rather than a binary mask — and what cap/fade preserves the owner's conviction while restoring auditability?
2. If a genuine hard override is retained, what attenuation lever (partial cash, confidence-scaled) belongs in config alongside `enabled`?

### B2. The gate masks to zero the ONE both-halves-validated ACCUMULATE edge (MVRV-Z<0)
**Severity: high**

The gate is applied after and over the deep-value accumulation floor (btc_signals.py L534, MVRV-Z<0 → ≥0.5), the drawdown brake (L540), and the additive bottom overlay (L544). So an n=3 rule absent from the DSR trial ledger silently overrides `mvrv_z` — the single best-validated signal in the stack (best_single, IC 0.188; template L1084: +40%/90d at 72% hit, longest-history accumulation signal). If a genuine cycle bottom with MVRV-Z<0 forms during a midterm year (plausible given dampening), the model sits in 100% cash through the exact accumulation window it was built to catch, on the authority of the *least*-evidenced rule in the system.

**Evidence:** btc_signals.py L533-534 (deep_value floor ≥0.5), L544 (overlay), L540 (brake), L545-546 (gate zeroes all); calibration.json best_single=mvrv_z IC 0.188; template L1084 (MVRV-Z<0 → +40%/90d, 72% hit).

**Failure mode:** MVRV-Z prints -0.5 in mid-2026, the floor sets 0.5, the overlay adds more — and the midterm mask zeroes every bit of it. The owner misses the buy the engine's best signal explicitly flagged.

**Open questions for Fable:**
1. Should the gate carry a deep-value / capitulation *exception* (evidence can veto the calendar veto), and how is the priority between an unvalidated calendar rule and a validated on-chain signal adjudicated?
2. What is the intended precedence ordering among floor, brake, overlay, and gate — and should it be data-driven rather than execution-order?

### B3. Latent two-source-of-truth: decomposition panels computed gate-blind, suppressed only by hand-duplicated Jinja
**Severity: medium**

The Kelly and bottom-overlay decomposition panels are fed by `sizing`/`alloc_sizing` dicts computed gate-blind in build_vector.py (`alloc_sizing()` L194-221 never references the gate). Fix #34 built a centralized `suppressed_by_blackout` flag but applied it only to the rec card; the two sizing panels are suppressed solely by hand-duplicated `and not (midterm and midterm.active)` clauses (template L813/L817). Any future panel added without the clause, or any clause dropped in an edit, prints pre-gate internals (e.g. "Pressure 70/100 · +28%") beneath a 0%-cash allocation.

**Evidence:** build_vector.py L194-219 (gate-blind sizing); template L813/L817 (hand-duplicated suppression); L458 (rec card via the centralized flag).

**Failure mode:** A refactor adds a fourth mini-panel without the midterm clause; the page shows "+28% bottom overlay adding" beneath 0% cash.

**Open question for Fable:** Should the gate state be stamped onto the *data* (one source of truth consumed by all panels) rather than re-checked per-template-block?

---

## Theme C — Falsification without authority

### C1. All four pre-committed falsifiers fire only into a display color — none can soften, release, or grade the gate
**Severity: high**

The cycle-thesis monitor (`btc_cycle_thesis.monitor`, flags dampening/timing/desync/structure; thesis_status intact/watch/breaking) is computed AFTER allocation is finalized and feeds only the template (build_vector.py L2247/L2654; color map at vector.html.j2 L1350-1355). The hard gate is driven exclusively by `midterm_blackout()`, a pure calendar function (btc_signals.py L461) that never receives `cphase_status` or the thesis object. If the thesis flips to BREAKING/invalidated in 2026 (e.g. a new-ATH bull rip), the card turns red while the allocation stays 0% "Proprietary cycle timer." The monitor self-narrates but cannot self-correct — the falsifiers fire into a void. This subsumes several separately-filed findings (d1-gate-decoupled, d-thesis-breaking-is-cosmetic, gov-gate-decoupled).

**Evidence:** btc_cycle_thesis.py L189-235 (status derivation); btc_signals.py L461, L527, L545-546 (calendar-only gate); build_vector.py L2247 (monitor computed for display only); vector.html.j2 L1350-1355 (only consumer).

**Failure mode:** In 2026 the structure falsifier flips to "invalidated" on a new-ATH bull rip; the card says "the 1064/364 count is off this cycle," while the allocation card next to it shows 0% "holding cash." The user either overrides manually (defeating the engine) or trusts the 0% and misses the entire up-leg the monitor just flagged.

**Open questions for Fable:**
1. What is the correct control authority for a falsifier — full release, partial softening, or a required human re-confirmation — and how do we avoid re-introducing overfitting by wiring a display composite (that lost OOS) into sizing?
2. Which falsifier states should be able to touch the gate, and with what latency/hysteresis to avoid whipsaw?

### C2. The "structure invalidated" signal is the exact bull off-ramp — computed, then discarded into a color; and it never re-engages allocation
**Severity: high**

`cycle_phase_clock()` computes, point-in-time, the exact bull-thesis-kill signal: during the 2026 markdown (anchored at the 2025-10-06 top), status flips to `invalidated` the moment price closes above that reference (effectively a new ATH). This escalates to `thesis_status='breaking'`, but it is routed only to display JSON. No allocation path consumes it — the hard gate is calendar-only, and even the SOFT tilt (`_cond_up_prob` L261-270) reads only `cphase_phase`/`cphase_pct`, never `cphase_status`, so an invalidated markdown still tilts DOWN. The engine manufactures the definitive off-ramp for its own 0%-for-2026 stance and discards it.

**Evidence:** btc_signals.py L940-948 (invalidated on close above anchor top; anchor 2025-10-06 from config); btc_cycle_thesis.py L197-202 (maps to 'alert'); build_vector.py L261-270 (soft tilt ignores cphase_status).

**Failure mode:** BTC makes a new ATH in mid-2026; cphase_status='invalidated', thesis_status='breaking'; the card screams the thesis is dead; the allocation sits at 0% through a new-ATH bull leg the engine printed the invalidation for months earlier.

**Open questions for Fable:**
1. Should `cphase_status=='invalidated'` be a first-class re-engagement trigger, and if so how does it interact with the *separate* midterm-calendar gate (they test different rules)?
2. Even the disciplined soft path ignores `cphase_status` — should the tilt sign flip (or zero) on invalidation rather than continue tilting down?

### C3. Two falsifiers are structurally incapable of firing during the gate window; the desync detector doesn't test the mechanism it names
**Severity: medium (desync) / high (temporal blind spot)**

Two distinct structural defects: (a) The desync falsifier computes `proj_bottom = observed_top + 364d` and compares to the nearest midterm November — the halving date is **never referenced** (btc_cycle_thesis.py L213-218; verified: `peak_date + Timedelta(down_days)`, not any halving date). Because a fixed 364d offset from any Q4 top lands ~12mo later near the snapped midterm date, all three real cycles print 0.1-1.3mo (always green); the flag can only trip on a ~5+ month top migration, never on halving-to-election decoupling. It is an *imperfect proxy* for the named mechanism (top-migration IS the observable symptom of time-compression), so "cosmetic" overstates it — but it does not test the causal decoupling it claims to guard. (b) The timing falsifier's only escalating state (OVERDUE) is reachable only after `now > peak+430d ≈ 2026-12-10`, ~37 days AFTER the calendar gate releases itself on ~2026-11-03 — so the one falsifier explicitly about the timing bet being wrong is temporally incapable of firing during the gate's active window.

**Evidence:** btc_cycle_thesis.py L213 `proj_bottom = peak_date + pd.Timedelta(days=int(down_days))`, L215-218 (midterm from proj_bottom.year, never halving); L183-192 (overdue requires now>win_end=peak+430d ≈ 2026-12-10); btc_signals.py L478 (release ~2026-11-03).

**Failure mode:** The halving clock genuinely drifts earlier and the true bottom migrates toward the post-election year, but the desync detector keeps printing "aligned" (it keys off top+364, not the halving); meanwhile through all of 2026 the timing flag reads "in the projected window / early" and never escalates during the cash period even if the clock is visibly slipping.

**Open questions for Fable:**
1. Should the desync detector reference the *actual halving date* (the causal anchor) rather than top+constant, and what would a real halving-to-election-decoupling test look like?
2. How should the falsifier windows be aligned so the timing check can escalate *inside* the gate window rather than after it releases?

### C4. No forward-grading ledger exists for the gate, though the machinery ships for everything else
**Severity: high**

The repo has a forward-outcome logging discipline (`regime_ledger.jsonl`, `impulse_ledger.jsonl`, us_board_ledger, the signal track-record logger) that grades live calls against realized outcomes and auto-demotes. The *regime* ledger's demotion power is by construction confined to the DISPLAY-only tiers (btc_regime_ledger.py L1-21 header, L649-652 "Nothing in sizing or allocation reads this"). The gate — the one rule sizing real money — has zero forward-ledger row anywhere (`trial_ledger.jsonl` has 20 rows, none vector/midterm). So the gate is uniquely exempt from *both* the ex-ante DSR *and* the ex-post forward-grading ledger; it can never accrue a track record that would falsify it.

**Evidence:** btc_regime_ledger.py L1-21, L523-525 (FRAGILE→demote 0.0 for display tiers only), L649-652; trial_ledger.jsonl 20 rows, no vector/midterm; grep for a gate-grading row returns nothing.

**Failure mode:** The ledger dutifully demotes a display curve no one trades on, while the calendar gate that zeroed the book for a year is never graded, never demoted, and never questioned by any automated falsifier.

**Open questions for Fable:**
1. What does a forward-grading ledger row for a *binary calendar gate* look like (what outcome does it score — avoided-drawdown minus foregone-return, per cycle)?
2. Given n=3 accrues one row per 4 years, what interim/decomposed metric can grade the gate faster than waiting for whole cycles?

---

## Theme D — Regime mutation the gate cannot see

### D1. Both clocks and the gate assume fixed cycle length/timing while the halving cycle is lengthening and dampening
**Severity: high**

The hard gate is anchored to a rigid US-election calendar (year%4==2, fixed November via `_us_election_date`) and is structurally decoupled from both cycle clocks, whose parameters are static (`cycle_len_d=1458`; `up_days=1064`/`down_days=364`, read with no recalibration). Observed halving gaps are lengthening (1319→1402→1440d) with the halving month drifting earlier (Nov→Jul→May→Apr). The thesis monitor even measures this drift and a projected bottom window — but that projection never feeds the gate. If the cycle stretches and the true bottom migrates out of the midterm year (e.g. into 2027), the gate cashes out the wrong (recovery) year and re-engages into the real drawdown, with no live mechanism to detect or correct the drift. The 1064/364 fit that would anchor a drift-aware alternative is itself in-sample (n=3 up / n=2 down, 2 free params, MAE 7.2d).

**Evidence:** config.yml L3567 cycle_len_d=1458, L3580-3581 up_days=1064/down_days=364; halving gaps 1319/1402/1440d from config halving_dates; btc_signals.py L454-458 (November hard-coded), L461-480 (calendar-only), L884/L917 (static param reads).

**Failure mode:** Cycle lengthens (institutional dampening also tends to stretch cycles); the real bottom slips into 2027; the gate cashes out all of midterm-2026 (a recovery year) and is fully invested through the real 2027 drawdown.

**Open questions for Fable:**
1. Should the gate anchor to the *halving-projected bottom window* (drift-tracking) rather than the fixed political calendar — and how is that reconciled with the fiscal-tightening amplifier premise?
2. How can any of the three ~4yr projections recalibrate as leg-lengths mutate without re-introducing look-ahead?

### D2. The bear-bottom mechanism is mutating (marginal-holder shift) — including a NEW reflexive fat tail the clocks cannot see
**Severity: high**

The year-in-cash decision rests on the historical microstructure (deep, slow capitulation into midterms), while the engine's own display factors flag the microstructure is shifting: spot-ETF/treasury/DAT flows are marginal-holder evidence tagged context-tier and refused entry to the validation gate (btc_regime.py L20-22). Reading `btc_dat.py` reveals two additional gaps beyond "flows don't feed the gate": (a) it computes `forced_sell_distance_pct` — how far BTC is above MSTR's ~`avg_cost × 0.78` margin-call level — i.e. the code *knows* a leveraged marginal holder can be force-liquidated, a NEW reflexive down-leg that did not exist in the 2014/2018/2022 cycles the gate is fit to; and (b) it is DISPLAY-ONLY, DEGRADE-NEVER-RAISE, reading a manually-maintained JSON (data/dat_holdings.json). So the dampening thesis is fragile in *both* directions: a DAT unwind could deepen, not dampen, a drawdown — and the gate is fit to a bear shape that may be simultaneously shallowing on average AND occasionally fat-tailing.

**Evidence:** btc_regime.py L20-22 (ETF context-tier, "structurally ineligible for the validation gate"); btc_dat.py header (mNAV, forced_sell_distance_pct, margin_haircut 0.78, manual JSON); build_vector.py L2350-2355 (wired display-only); cycle_phase_clock reads price+config only (btc_signals.py L899-963).

**Failure mode:** Spot-ETF/treasury bid absorbs supply through 2026 → no midterm capitulation at all (gate sits 100% cash waiting for a washout the new structure won't produce); OR a leveraged DAT unwind triggers a reflexive fast crash the calendar gate can neither predict nor exit. The gate is maximally wrong for both halves of the new distribution.

**Open questions for Fable:**
1. How should marginal-holder / forced-sell evidence couple to the down-leg TIMING and the gate's washout premise (not just to depth)?
2. Should the gate's premise be conditioned on the *presence* of a capitulation regime rather than assumed by calendar — and how is the DAT fat-tail priced into that?

---

## Theme E — Instrument design: the binary override vs the graded stack

### E1. The binary calendar mask deletes the engine's own bottom-buyer during exactly the washout it was built to buy
**Severity: critical**

Within a single function, `allocation()` computes the deep-value floor and the market-aware bottom overlay (adds up to +0.40 when multi-timeframe StochRSI-oversold washout confluence fires — the ~4x bottom-odds tell), plus the drawdown brake (0.40 core floor, never all-cash), then unconditionally overwrites the result to 0.0 via the calendar-only mask (btc_signals.py L541-546) that has no visibility into bottom_pressure, brake state, momentum, risk, or valuation. With `buy_lead_days=0` it does not release until election day. Two enabled subsystems are in direct, silent conflict and the market-blind one always wins. This is by design (code-labeled "the FINAL word"), which is precisely the instrument-design flaw: a discretionary calendar rule wired to veto the engine's best entry with no conditioning or partial retention.

**Evidence:** btc_signals.py L541-546 (overlay `raw = (raw + b_boost*b_strength).clip(...)` immediately followed by `raw.mask(gate,0.0)`); config.yml L3336 dd_floor=0.40, L3344-3345 bottom_boost=0.40; L3317 buy_lead_days=0.

**Failure mode:** A midterm-year bottom forms (as the thesis itself predicts "BTC capitulates into midterms"); the overlay flags a high-conviction washout buy; the calendar gate zeroes it; the strategy re-enters months later at the vote, near or above the low it was forbidden from buying.

**Open questions for Fable:**
1. What is the right composition operator between the graded stack and the override — partial retention (e.g. keep the brake's 40% floor), evidence-conditioned release, or precedence by validation strength?
2. If the thesis predicts the bottom *inside* the gated window, is a full-cash gate ever coherent with a bottom-buying overlay in the same function?

### E2. 10-month all-cash on a single calendar boolean with no live-signal AND-gate and no downside-optionality alternative
**Severity: high**

`midterm_blackout()` zeroes allocation for ~306-311 days on the sole predicate year%4==2, with no AND-gate on any live signal — its signature `(index, cfg)` makes consulting momentum, the Risk Index, composite_state, the regime composite, or the falsifier flags structurally impossible. The only knob shifts the END date, not the strength. Separately, the dashboard's only response to a feared drawdown is 100% cash: `allocation()` is strictly long-or-cash (clipped [0, cap]), and no downside-optionality alternative — protective put, collar, partial-long, staged re-entry — is ever constructed or backtested (calibration.json has zero hedge/put/tail/collar keys), *even though* the pipeline already ingests Deribit options data (DVOL, 25d skew, put/call OI) that could price a put-overlay's carry drag. The binary all-cash choice was never *compared* against a hedged or brake-only alternative.

**Evidence:** btc_signals.py L461-480 (no live signal read), L545-546 (final mask over everything); config.yml L3316-3317; calibration.json (no hedge/put/tail/collar keys anywhere); Deribit feed present but unused for optionality.

**Failure mode:** BTC institutionalization decouples price from the electoral calendar; BTC rallies through 2026; the gate holds 0% the entire time on a rule that no longer applies, and no live signal can override it — when a collar or partial-long would have participated for a small carry cost.

**Open questions for Fable:**
1. What live-signal AND-gate (risk_index band, composite_state, confirmed-bear detector) should be *required* before the calendar gate can zero exposure?
2. Should the "feared window" instrument be a hedged/collar/partial-long alternative priced off the existing Deribit feed rather than binary cash — and what is the fair comparison to run?

### E3. `buy_lead_days=0` structurally guarantees the re-entry is late relative to the engine's own bottom projection
**Severity: medium**

The thesis monitor's projected accumulation window opens ~Oct (lead 360d), yet the gate's release is pinned to election day (~Nov 3). Even taking the thesis at face value, the gate is mis-tuned against the engine's own bottom estimate: it holds cash through the front of the projected accumulation window and re-enters after. The one tunable knob is set to the value that maximizes the miss.

**Evidence:** config.yml L3317 buy_lead_days:0; btc_cycle_thesis.py L38-39 window lead 360d; btc_signals.py L478 release ~2026-11-03; overlap Oct→Nov 2026.

**Failure mode:** The projected accumulation window opens in October; the gate holds cash until the November vote; the owner re-enters after the front of the very window the engine projected as the bottom.

**Open question for Fable:** Should the release date be tied to the thesis's projected bottom window (or a live bottom signal) rather than a fixed calendar offset — and what lead value is defensible given n=3?

---

## Theme F — Decision theory: objective, EV & the missing counterfactual

### F1. Under the documented dampening trend the blackout is trending toward negative EV, with no breakeven or gate-off-but-brake-on counterfactual
**Severity: critical**

The blackout is structurally asymmetric — constant ~10.5-month opportunity cost against a benefit (avoided drawdown) that the code's own dampening series (-84% → -77% → -52%) says is compressing. Yet no breakeven-dampening or EV-vs-bear-depth sensitivity exists in calibrate_vector.py or calibration.json, and the one counterfactual that would justify the rule — gate-ON vs gate-OFF-but-brake-ON — is never run (all backtested variants share the same gate). The defense metrics (moderate CAGR 65.5 vs HODL 59.0; the real edge is DD -39 vs -84) are drawdown-driven and drawn almost entirely from the two deep bears the code says are ending, and are circular (gate baked into the graded series). The single missing number — the bear depth at which cash-for-~10.5-months turns negative-EV, net of the brake that already caps a shallow bear — is the crux and it is absent.

**Evidence:** btc_cycle_thesis.py L13-16, L40-42 (dampening -84/-77/-52, _DAMPEN_GAP); config.yml L3333-3336 (brake dd_floor 0.40 already de-risks without zeroing); calibrate_vector.py L619-622 (only gate-sharing variants); calibration.json allocation block (no breakeven/EV sensitivity, no brake-vs-blackout head-to-head).

**Failure mode:** 2026 delivers a shallow -30% wobble then recovers; the brake would have cut it to ~-15% while holding a compounding position; the blackout sits in cash and surrenders the entire annual drift and the recovery — a multi-thousand-bps regret, on a rule whose measured benefit is shrinking each cycle.

**Open questions for Fable:**
1. At what bear depth does the ~10.5-month all-cash bet break even against the brake-only alternative — and where does the dampening trend put the *next* bear relative to that threshold?
2. What is the correct counterfactual battery (gate-off-but-brake-on, per-cycle EV decomposition, EV-vs-bear-depth curve) that must exist before the gate can be defended?

### F2. The gate optimizes an unstated objective and gets a 100→0 cliff while every other lever is graded — no utility/regret framing
**Severity: high**

The codebase never writes down the owner's objective function. The one risk-preference knob (Kelly `dd_budget=0.25` / brake floors) governs a sizing path the gate bypasses. The scorecard reports return metrics (cagr, total_return, final_vs_hodl) and risk metrics (maxdd, sortino) side by side with no stated target, so the 0% call can be defended by whichever family it wins on, with no regret comparison or certainty-equivalent to adjudicate. The blackout is the only discontinuous lever (a binary mask) sitting atop an otherwise fully-graded stack (conviction multiplier + brake + overlay), with no utility curve justifying why this single rule gets a cliff. Separately, the gate acts on P(bear | calendar) alone while the engine already estimates P(bear | momentum, risk, valuation) — the textbook base-rate error, mis-firing most expensively in a bullish/low-risk/ETF-inflow midterm year (exactly the 0% forced for 2026).

**Evidence:** build_vector.py L185-191 (return+risk metrics, no objective); config.yml L3307-3314 (gate justified only by narrative "hostile"); btc_signals.py L545-546 (hard discontinuity); L476-479 (calendar-only, ignores CONFIRMED risk_index 0-25 band = +28%/90d).

**Failure mode:** The owner, believing he is return-maximizing, follows a stance only defensible under strong drawdown-aversion; over a dampened cycle he realizes large regret and cannot reconstruct which objective the rule served. Or: momentum is strongly bullish and risk_index is in the 0-25 band during a midterm year, and the gate forces cash anyway, converting a high-probability-up state into a guaranteed zero.

**Open questions for Fable:**
1. What is the owner's actual objective (CAGR? drawdown-constrained growth? certainty-equivalent under a stated risk aversion?), and should the gate route through the *same* dd_budget/utility that already governs sizing rather than as an independent binary override?
2. Why should the highest-conviction rule be the *only* discontinuous one — is a graded, evidence-conditioned de-risk more consistent with the rest of the stack?
3. What regret / certainty-equivalent view makes the "worst-case foregone gain vs avoided loss" tradeoff auditable?

### F3. No per-cycle attribution — the headline blends a clean win and a wash into one flattering number
**Severity: medium**

(De-escalated from its filed title "in-sample backtest inflates the gate benefit," which the body itself refutes: the 2026 truncation is only ~3.9% of the 4,182-row sample and 2022's recovery is already scored.) The real, narrower defect is that no artifact decomposes the gate's contribution PER CYCLE (drop-avoided minus recovery-missed, total-return basis). Such a view would show 2018 a clean win but 2022 roughly a wash-to-loss, and would make explicit that the live 0%-for-2026 call rests on one-sided evidence (a -27% decline banked, recovery leg unobservable). The aggregate defense figures blend the clean and the wash cycles into one number.

**Evidence:** calibration.json meta.span ends 2026-06-13 (mid-blackout); cross_validation folds end 2026-03-15 (also mid-blackout); calibrate_vector.py backtest on gate-baked series with no per-cycle decomposition.

**Failure mode:** The backtest shows the gate "helping" in aggregate; the owner keeps the cash stance; BTC rallies post-election into 2027 — a recovery the aggregate never disaggregated as a cost.

**Open question for Fable:** What per-cycle attribution table (drop-avoided vs recovery-missed, total-return) should replace the blended headline, and how should the un-observable 2026 leg be represented (as pending, not banked)?

---

## Theme G — UX honesty at the point of decision

### G1. The scrub deleted previously-published pre-committed caveats and relabeled the override as validated "Proprietary" IP
**Severity: critical**

Commit c7531d232d ("hide cycle-timer internals", #637) affirmatively deleted the pre-committed fragility disclosures that previously accompanied the Cycle Phase Clock card and replaced the entire body with "Proprietary cycle timer." (templates/vector.html.j2 L1343 → site/vector.html:2161). The deleted lines contained exactly the caveats a subscriber needs to temper conviction on the 0%-for-2026 call: in-sample fit / ~7d MAE / n=3 cycles, and "timing only — NOT amplitude (2025 ~240% vs >1000% prior), no $37.5K bottom-target endorsement, 4-year cycle may be mutating as ETFs/institutions decouple BTC." None survives in the rendered UI. Withholding a previously-published, pre-committed risk disclosure is a stronger honesty failure than never writing it — and it degrades the tool for its *primary* user: the memory profile says the owner "trades conviction on low-n mechanism theses," so the scrub removes his own future-self guardrail against the exact failure mode he is prone to.

**Evidence:** `git show c7531d232d -- templates/vector.html.j2` (removed "1064 days up / 364 days down … ~7 days, but only n=3 cycles (in-sample)" and "Timing only — NOT amplitude … we do NOT endorse the $37.5K bottom target … 4-year cycle may be mutating"); replaced by templates/vector.html.j2 L1343 "Proprietary cycle timer."; memory `user-trades-conviction-low-n`.

**Failure mode:** The owner (or a subscriber) sizes a durable-bottom entry to the "Proprietary cycle timer" expecting a validated edge, unaware the pivot dates carry ~7d MAE only in-sample over 3 cycles and amplitude has collapsed >1000%→~240% — then the cycle mutates in time and the 0%/re-entry timing is wrong.

**Open questions for Fable:**
1. What is the minimum honesty payload that must sit *adjacent to the 0% headline* (n=3, in-sample MAE, amplitude dampening, decoupling risk, discretionary-override status) — and how is that reconciled with the commercial desire not to publish the raw day-counts?
2. Can "subscription value" be preserved without hiding the fragility of the highest-stakes call — e.g. disclose the uncertainty while keeping the parameters proprietary?

### G2. The confident 0% headline and its only real caveat are ~690 rendered lines apart — and the caveat is about a different mechanism
**Severity: critical**

The confident 0% Optimal/Proprietary headline (site/vector.html:1497-1501) sits ~690 lines and 10+ cards from the only fragility caveat (:2191), which discloses the *thesis monitor* (btc_cycle_thesis) — NOT the `midterm_blackout` gate that actually forces the 0%. The gate's own n=3 basis and human-override status are disclosed nowhere near the decision; the banner carries no sample-size, no falsifier, and a passive-voice "overridden" that hides its discretionary nature, in the same "Proprietary cycle timer" register as the quantitative factors.

**Evidence:** headline templates/vector.html.j2 L449/L799/L802-803 → site/vector.html:1497-1501; caveat site/vector.html:2191 (belongs to btc_cycle_thesis.py L263, a different mechanism than midterm_blackout btc_signals.py L461); no midterm/blackout n-disclosure near the banner.

**Failure mode:** Owner/subscriber reads "0% — Optimal strategy, Proprietary cycle timer," treats it as an engine-validated all-cash edge, and forgoes upside or over-trusts the re-entry date, never realizing the single most consequential rule is an n=3 calendar heuristic plus a human conviction override.

**Open questions for Fable:**
1. What co-located disclosure belongs on the *gate's own* banner (distinct from the thesis-monitor caveat), and how should "the words 'Optimal' and 'Proprietary' vs the evidence" be reframed?
2. How should the UI honestly name a variant label ("optimal" is one of four grid names, config.yml L3305) so it does not read as "solved optimization"?

### G3. Ungated display signals + the alert stream + a second page = a self-contradicting product, worst during a rally
**Severity: high**

The hero Stance (composite_state), the bull-probability needle (`_cond_up_prob`), and the MTF confluence verdict are all computed from the *ungated* frame and carry no blackout guard, while the allocation banner reads 0%. During a 2026 rally the page can headline ACCUMULATE / 60-40 bull / BUY-THE-DIP directly beside "Model allocation 0% — holding cash." This is partly *correct behavior* — the ungated read is the product's most honest market surface, and demanding it "reconcile to the mandated cash position" would delete that honesty. But there is a real, narrow gap: the *accumulate badge* (vector.html.j2 L1356) is the only buy-side thesis output NOT gated on midterm.active (the rec card and both sizing cards already are), so it can render an unqualified "ACCUMULATION ZONE" during blackout. Compounding: `vector_allocation.html` is a full second decision surface with its *own* hand-duplicated gate guard (L153) and a third copy of the "Proprietary cycle timer" label (L143), replicating the same contradiction un-audited; and the alert stream (A3) actively blames the grid. Every surface the user touches can tell a different story about *why* they are in cash.

**Evidence:** build_vector.py L2475 (ungated stance), L224-275 (ungated needle), btc_mtf confluence_verdict (no gate); vector.html.j2 L1356 (accumulate badge un-suppressed); vector_allocation.html.j2 L143/L153 (parallel page, hand-duplicated guard); btc_alerts.py L274-284 (grid misattribution).

**Failure mode:** October 2026: drawdown ~-50%, in the projected window → accumulate badge shows; gate still active → 0%; the alert says "grid moved to 0%"; the second page mirrors 0%. The user must choose which engine output to believe, and the "Proprietary" label makes the 0% look most authoritative, so they likely miss the accumulation the thesis just endorsed.

**Open questions for Fable:**
1. What is the right *reconciliation surface* — a single explicit line ("market read is constructive; the discretionary cycle timer overrides to 0% this year") — that preserves the honest ungated read without letting it silently contradict the mandated position?
2. Should the accumulate badge and both pages consume ONE `suppressed_by_blackout`/gated-state flag stamped on the data rather than hand-duplicated Jinja across two templates?
3. Should the falsifier status (overdue/invalidated) — currently rendered only when not on_track, and never near the 0% headline — propagate a shared thesis-health caveat to every surface carrying the "Proprietary cycle timer" label?

---

## Theme H — Sample-independence & multiplicity across the whole suite

### H1. Overlapping forward returns and autocorrelated daily P&L are treated as independent; per-signal band verdicts carry no family-wise control
**Severity: high**

The DSR uses T=4182 daily strategy returns as if independent (validation.py L263, `sqrt(T-1)`), but those are the daily P&L of a slow allocation grid — strongly autocorrelated — so the effective independent sample is a small fraction of 4182; the only corrections are skew and kurtosis, zero autocorrelation deflation. The per-signal band tables that motivate the thresholds are built on OVERLAPPING 7/30/90d forward returns and report band n in the thousands with no overlap discount (e.g. mvrv_z pre-2021 <0 shows hit_90d 92.1% on n=177 overlapping windows ≈ 2 non-overlapping 90d episodes; the full 90d column has ~46 non-overlapping windows across 2015-2026). Separately, the 32 signal families are each binned into ~5 hand-chosen bands and tail-characterized across 2 tails × 3 horizons on both split-halves with NO family-wise / FDR control, and the same hand-picked band EDGES are then hard-wired as the live valuation-overlay thresholds (deep_value_z=0.0, overvalued_mayer=2.4, overvalued_rr=0.02) that floor/cap real-money exposure — while only 7/31 CV'd signals survive purged folds.

**Evidence:** validation.py L263 (sqrt(T-1), no autocorr); calibration.json multiple_testing T=4182; calibrate_vector.py L55-56 (overlapping close.shift(-h)), config.yml L3661 forward_days [7,30,90]; calibrate_vector.py L123-139 (_extremes_verdict, no FDR), L469-542 (hand-set bands); config.yml L3321-3325 (overlay thresholds = calibration band edges); calibration.json cross_validation n_robust 7/31; thin tails puell>4 n=23, funding_z>2 n=39.

**Failure mode:** The DSR and per-band hit-rates read as high-confidence, but with ~3 independent cycles and ~46 non-overlapping 90d windows, any single new cycle that behaves differently (the dampening trend) can overturn conclusions presented as settled; and a tail band that fired on n=23-40 observations (or a post-2021-only half) is trusted as a TOP/BOTTOM trigger that floors/caps exposure precisely when the rare tail recurs out of sample.

**Open questions for Fable:**
1. What effective-N / block-bootstrap / autocorrelation deflation should replace the raw `sqrt(T-1)` in the DSR and the band-table n's?
2. What family-wise or FDR control belongs on the 32-family × bands × horizons × split-half search that seeds the live overlay thresholds — and should the live thresholds decouple from the searched band edges?

---

## What is already good and must be preserved

These are genuine strengths the fix program must not steamroll:

- **The KEEP-HEURISTIC honesty.** The elaborate ensemble (Sharpe 0.31 post-2021) LOST to the hand-tuned `composite_state` (0.65) OOS, and the system *shipped the loser's verdict* rather than the fancier model (calibration.json ensemble_promotion; btc_regime.py header). Any re-promotion of ML sizing must clear the same bar.
- **The display-only regime firewall.** `btc_regime.py` / `btc_regime_ledger.py` carry hard headers that they never size money (btc_regime_ledger.py L1-21, L649-652). This architectural guarantee — a rejected-OOS composite cannot leak into sizing — is an asset. Do NOT dissolve it in the name of "wire the falsifiers into the gate"; give the falsifiers teeth *without* routing a display composite into sizing.
- **The measured MVRV-Z edge and its overlay mechanics.** `best_single = mvrv_z` (IC 0.188), both-halves validated, longest history. The deep-value floor (L533-534) and overvalued cap (L535) are grounded instruments; the legitimate critique is that the gate *masks* them, not that they are wrong.
- **The disciplined soft path.** `_cond_up_prob` (build_vector.py L263-274) — fixed ±5pp, sign-fades toward the reversal, hard-clamped [0.30,0.70], empirical-Bayes shrunk toward the momentum marginal, "never a trigger" — is the template any gate-softening should imitate.
- **The pre-committed falsifier monitor as a concept.** `btc_cycle_thesis.py` writes down four ex-ante falsifiers before the outcome is known. The fix should give it control authority, not delete it.
- **The config-toggle legibility of the override.** The most consequential decision is one boolean (`midterm_gate.enabled`), not a buried fitted parameter. Whatever replaces the binary mask should retain "the human override is one legible, flippable line."
- **Correctly-scoped low-severity / already-mitigated items** (do not re-open as defects): the M2 publication-lag look-ahead reaches only the display-only regime gauge (PIT-tested in the live path); the regime-index-vs-0% contradiction is already de-emphasized with a "DISPLAY-ONLY · does not size" chip; the brake/overlay marginals were measured pre-gate (no triple-count), needing only a re-measure on the post-gate curve; the stale n_trials=50-vs-65 artifact does not flip SURVIVES at any plausible count.

---

## Prioritized problem ranking

| Rank | Problem | Severity | Theme |
|------|---------|----------|-------|
| 1 | A1 — Gate baked inside allocation(): numerator of every backtest, denominator of no overfitting control | critical | Circular validation & invisible DoF |
| 2 | F1 — Dampening trends the fixed-cost blackout toward negative EV; no breakeven / gate-off-brake-on counterfactual | critical | Decision theory |
| 3 | E1 — Binary mask deletes the engine's own bottom-buyer during exactly the washout it was built to buy | critical | Instrument design |
| 4 | B1 — Same belief: capped ±5pp "never a trigger" vs uncapped 100%→0% override; anti-overfit switched off where capital is largest | critical | Self-contradicting double standard |
| 5 | G1 — Scrub deleted pre-committed n=3/MAE/amplitude/decoupling caveats; relabeled override as validated "Proprietary" IP | critical | UX honesty |
| 6 | G2 — Confident 0% headline and its only caveat ~690 lines apart; caveat is about a different mechanism | critical | UX honesty |
| 7 | C1 — All four falsifiers fire into a display color; none can soften/release/grade the gate | high | Falsification without authority |
| 8 | A2 — ETH sleeve reused allocation() so "SCORED DSR 0.9965" is BTC's gated number | high | Circular validation & invisible DoF |
| 9 | A3 — Alert stream fabricates a "momentum × grid" attribution for the gate's 0% | high | Circular validation & invisible DoF |
| 10 | C2 — "Structure invalidated" is the exact bull off-ramp, computed then discarded; never re-engages | high | Falsification without authority |
| 11 | C4 — No forward-grading ledger for the gate though machinery ships for everything else | high | Falsification without authority |
| 12 | D1 — Static clocks + calendar gate vs lengthening/dampening halving cycle; cannot track the drift | high | Regime mutation |
| 13 | D2 — Marginal-holder shift (incl. new DAT forced-sell fat tail) invalidates the bear premise both ways | high | Regime mutation |
| 14 | E2 — 10-month all-cash on one calendar boolean, no live-signal AND-gate, no downside-optionality alternative | high | Instrument design |
| 15 | B2 — Gate masks to zero the one both-halves-validated ACCUMULATE edge (MVRV-Z<0) | high | Double standard |
| 16 | F2 — Unstated objective; gate gets a 100→0 cliff while every other lever is graded; base-rate error | high | Decision theory |
| 17 | G3 — Ungated display + alerts + second page = self-contradicting product, worst during a rally | high | UX honesty |
| 18 | H1 — Overlapping/autocorrelated samples treated as independent; no family-wise control on band-edge selection | high | Sample-independence & multiplicity |
| 19 | C3 — Desync doesn't test the halving decoupling it names; timing OVERDUE unreachable inside the gate window | medium/high | Falsification without authority |
| 20 | E3 — buy_lead_days=0 guarantees re-entry is late vs the engine's own projected bottom window | medium | Instrument design |
| 21 | B3 — Decomposition panels computed gate-blind, suppressed only by hand-duplicated Jinja (latent drift) | medium | Double standard |
| 22 | F3 — No per-cycle attribution; headline blends a clean win (2018) and a wash (2022) into one number | medium | Decision theory |
| 23 | A4 — Shipped DSR artifact stale vs config (n_trials 50 vs 65); reproducibility nit, does not flip verdict | low | Circular validation & invisible DoF |

**Files most load-bearing for the fix program:** `engine/btc_signals.py` (L461-480 gate def, L525-546 application — the single point to refactor), `scripts/calibrate_vector.py` + `data/vector/{calibration.json,trial_log.json}` (the blind certificate), `engine/btc_alerts.py` L274-284 (the false-attribution alert), `scripts/eth_vector_phase0.py` + `engine/signal_lab.py` L625/L643 (the contaminated sibling), `templates/vector_allocation.html.j2` L143-153 (the parallel page), `engine/btc_dat.py` (the unmodeled marginal-holder tail), `engine/btc_cycle_thesis.py` L183-238 (the falsifiers with no authority), `build_vector.py` L224-275 (the disciplined soft path to preserve/imitate).

---

# Appendix A — Devil's advocate: the strongest case FOR the current design (do not over-correct)

*This is a deliberate steelman produced by an independent agent, to keep the fix program from steamrolling genuine strengths. Weigh it against the problems above.*

## (1) The steelman for the current design

The critic panel treats the midterm blackout as if it were a quant signal masquerading as validated edge. That framing is the panel's weakest move. Read the code and the honesty headers together and a coherent, *defensible* design philosophy emerges — one that several critics actively misread.

**The gate is correctly located in the discretionary layer, not the statistical layer.** `midterm_blackout()` (btc_signals.py:461-480) takes `(index, cfg)` and nothing else — no price, no signal. Critics call this a defect ("calendar-only," "immune to evidence"). But that signature is the *tell* that it is an owner conviction override, not a fitted feature. The memory record and `config.yml` comments say so explicitly: the engine wanted to ramp 3%→19% in 2026, the owner disagreed, and the gate encodes that disagreement. For a person risking real money on a low-n mechanism thesis, encoding a conviction as a hard, legible, config-toggleable calendar rule (`enabled: true`, one line to flip) is *more* honest and *more* auditable than smuggling the same belief into a fitted threshold. The soft path proves the author knows how to do the "disciplined tilt" version (build_vector.py:263-274: ±5pp, sign-fades near turns, clamped [0.30,0.70], commented "never a trigger"). Choosing NOT to route the highest-conviction call through that machinery is a deliberate separation of "what the model measures" from "what the human overrides," which is exactly the discipline you want when the two disagree.

**The mechanism is genuinely stronger than "n=3 calendar coincidence."** The critics repeatedly reduce the thesis to `year % 4 == 2` fit to three points. The engine's own header (btc_cycle_thesis.py:4-10) states the real causal chain: the *halving* lands in every US election year (2012/2016/2020/2024), so the +12-18mo bull peak lands in the post-election year and the ~12mo bear bottom lands in the midterm year. The political calendar is an *amplifier* (midterm-year fiscal/monetary tightening) that currently rhymes with a halving-driven supply clock. That is not one n=3 observation — it is two independently-motivated ~4yr clocks that happen to phase-lock, which is a materially stronger prior than either alone. The gate keys on the calendar because the calendar is the fixed, look-ahead-free proxy for a bottom window the halving clock also points at.

**The "circularity" is real but its severity is overstated because the direction is known and adverse-to-the-owner.** Yes, the gate is baked into `allocation()` and therefore into the DSR series (this part is true and worth fixing). But the gate is *exposure-reducing and long-only-clipped*. A rule that can only move you toward cash cannot manufacture a spurious high Sharpe out of nothing the way a fitted long/short signal can — the worst it can do is dodge drawdowns that actually happened. Several critics themselves concede the DSR "would still likely clear 0.95 after correctly counting the gate" (gov-dsr-blind, d5). So the honest statement is "the robustness stamp doesn't *cover* the gate," not "the gate would fail the stamp." That is a labeling/coverage defect, not a validity collapse.

**Preemptive de-risk on a calendar is defensible precisely because reactive de-risk is too slow at BTC's crash speed.** Critics (d1-objective, decision-theory) demand the counterfactual "gate-off but brake-on." Fair — that A/B should exist. But the design's implicit answer is not stupid: a drawdown brake is *reactive* (it needs the equity curve to already be underwater to cut), and BTC's historical bear onsets are fast and gap-heavy. A calendar rule that goes flat *before* the window front-runs exactly the drawdowns a reactive brake enters late. The `dd_floor=0.40` brake also never reaches cash by construction — so in a true -70% bear the brake still holds 40% into the teeth of it. The blackout's "give up upside to guarantee zero exposure in the historically-worst window" is a coherent ruin-aversion stance, not an oversight.

## (2) The critic problems that are weakest, double-counted, or would make things worse if "fixed"

**The DSR/degrees-of-freedom cluster is massively double-counted.** At least *seven* separate findings assert the same single fact — that the midterm gate is absent from `n_trials` and baked into the deflated series: `dsr-baked-in-midterm-gate-circular`, `midterm-gate-not-in-trial-count`, `d-hardgate-05-gate-invisible-to-backtest-and-dsr`, `gov-circular-validation`, `gov-dsr-blind-to-the-gate`, `d3-midterm-gate-uncounted-in-dsr`, `d5-gate-uncounted-in-dsr-and-cv`. Two of them (gov-dsr-blind, decision d5) even admit the overlap in their own text. This is ONE governance finding ("the gate is in the numerator of the certified backtest but not in the denominator of the DoF haircut"), and inflating it to seven high/critical entries manufactures the impression of pervasive rot where there is a single, well-understood, direction-known coverage gap.

**`shipped-dsr-artifact-stale-vs-config` (n_trials=50 vs 65) is near-noise and the finding says so.** It states outright that regenerating at 65, or even at ~200, does not flip SURVIVES, that the DSR stays >0.95 until N is "well past 500," and that the artifact is not even rendered to subscribers. This is artifact-vs-config drift worth a one-line reproducibility fix, correctly graded low — but it should not be in a problem inventory presented as evidence the statistical defense is fragile. It is evidence of the *opposite*: the edge is robust to plausible DoF counts.

**`d2-desync-detector-structurally-cannot-fire` overstates "cosmetic."** The critique is technically correct that `proj_bottom = peak + 364d` never references the halving date, so the desync flag keys off top-migration, not halving-to-election decoupling (btc_cycle_thesis.py:212-218). But calling the axis "cosmetic for its stated purpose" misses that top-migration *is* the observable symptom of the exact failure mode that matters: if the cycle compresses in time (the dampening thesis), the top prints earlier, `proj_bottom` moves earlier, and the divergence from the fixed November midterm date grows — which is what would fire it. It is an imperfect proxy for the named mechanism, not a detector that "cannot flag the desync it guards." Fixing it by wiring in the actual halving date is reasonable, but the "it's decorative" framing is too strong.

**The "bull-stance-next-to-0%" contradiction findings (d-hardgate-02, d-accumulate-contradicts, ux-*) partly describe correct behavior, and "fixing" them naively would corrupt the display firewall.** The whole point of the design is that the *display* signals (composite_state, bull needle, MTF verdict, regime scorecard) are computed on the ungated series and are *honest reads of market state*, while the *allocation* reflects the owner's override. A user seeing "market looks constructive BUT I'm choosing cash on the cycle timer" is being shown MORE information than one who sees a single reconciled number. The genuine defect is narrow — the *accumulate badge* and *sizing panels* should carry the same `suppressed_by_blackout` treatment the rec card already has (this is a real 1-line consistency gap, correctly noted in d-hardgate-04/d-accumulate). But the broader demand to make the stance/needle/verdict "reconcile to the mandated cash position" would be *actively harmful*: it would delete the ungated market read that is the product's most honest surface and collapse the very display/decision separation the critics praise elsewhere.

**`d4-partial-2026-inflates-gate-benefit` refutes its own headline.** The finding's body concedes the truncation is only ~3.9% of the sample, that 2018/2022 recoveries are fully scored, and that 2022 already books its recovery cost — then concludes the real issue is *per-cycle decomposition opacity*, not truncation bias. The title ("inflates the gate benefit") contradicts the analysis. This is a request for a nicer attribution table, mis-filed as a bias.

**`d-hardgate-06`, `d1-regime-index-contradicts`, `d2-m2-lookahead` are already flagged `already_mitigated: true` — they belong in a "preserve these mitigations" list, not the problem set.** The M2 look-ahead in particular is explicitly display-only and PIT-tested in the live path; carrying it as a defect risks a "fix" that adds publication-lag machinery to a leg that never sizes money.

**The "no downside-optionality instrument exists" finding (d4-instrument) is a feature request dressed as a defect.** "Build a collar/put-overlay backtest" is a legitimate future direction, but its *absence* is not a flaw in the current instrument — it is scope. And a naive "fix" (adding options overlays priced off the Deribit feed) introduces execution, carry-modeling, and roll complexity that could easily degrade a product whose current virtue is legibility.

## (3) Merits that must be preserved through any fix

These are the genuinely good decisions the panel is at risk of steamrolling:

- **The KEEP-HEURISTIC honesty.** The calibration record shows the elaborate ensemble (Sharpe 0.31 post-2021) LOST to the hand-tuned `composite_state` (0.65) OOS, and the system *shipped the loser's verdict* rather than the fancier model. That is exactly the anti-overfit discipline you want. Any "fix" that re-promotes ML sizing must clear the same bar.

- **The display-only regime firewall.** `btc_regime.py` and `btc_regime_ledger.py` carry explicit headers that they never size money (btc_regime_ledger.py:1-21, 649-652). The auto-demotion ledger polices display tiers without any wire into allocation. Critics fault the ledger for "grading the wrong object," but the firewall itself — a hard architectural guarantee that a rejected-OOS composite cannot leak into sizing — is a real asset. Do not dissolve it in the name of "wire the falsifiers into the gate."

- **The measured MVRV-Z edge and the valuation overlay it seeds.** `best_single = mvrv_z` (IC 0.188) is the one signal with both-halves validation and the longest history. The deep-value floor (L533-534) and overvalued cap (L535) are grounded, sensible instruments. The legitimate critique is that the gate *masks* them during a midterm year (d-hardgate-03) — but the overlay/floor mechanics themselves are worth keeping.

- **The disciplined soft path.** `_cond_up_prob` (build_vector.py:263-274) is a model of how to encode a low-n cyclical prior responsibly: fixed small magnitude, sign-fades toward the reversal, hard-clamped, empirical-Bayes shrunk toward the momentum marginal, commented "never a trigger." This is the template any future gate-softening should imitate — not discard.

- **The pre-committed falsifier monitor as a concept.** Even though it is display-only, `btc_cycle_thesis.py` writes down four *ex-ante* falsifiers (dampening/timing/desync/structure) before the outcome is known. That is real intellectual honesty about a low-n thesis. The fix should give it teeth (feed it back to the gate), not delete it.

- **The config-toggle legibility of the override itself.** The single most consequential decision is one boolean (`midterm_gate.enabled`) in `config.yml`, not buried in fitted parameters. Whatever replaces the binary mask should retain that "the human override is one legible, flippable line" property.

**Net verdict for the solution designer:** the strongest true finding is narrow and singular — the gate sits in the *numerator* of the certified backtest but outside the *denominator* of every overfitting control, and it has no evidence-driven off-ramp while its own falsifiers fire into a display void. That is worth fixing (count the gate as a DoF; report ungated-vs-gated A/B; wire `thesis_status`/`cphase_status` to at least *soften or release* the gate; extend `suppressed_by_blackout` to the accumulate badge). But roughly a third of the inventory is the same DSR fact counted seven times, two entries are already-mitigated, one refutes its own title, and one is a feature request. And the design's core instinct — separating a legible human conviction override from a rigorously-capped measurement stack, with an honest ungated display read — is a *strength to preserve*, not the disease.

---

# Appendix B — Emergent problem-combinations + a starting hypothesis for phasing

*The problems above are individually real; some become more dangerous in combination. This appendix also contains a **starting hypothesis** for a fix ordering — it is INPUT for Fable to critique and improve, NOT a mandate. Fable owns the final phased program.*

## (1) Genuinely missing problems

**M1 — The circular, gate-baked backtest CONTAMINATED THE ETH SLEEVE, and ETH's own "SCORED DSR 0.9965" is BTC's gated number.** The panel treated the circularity as a BTC-only stat-validity problem. It is worse: the ETH Vector was validated by *reusing `btc_signals.allocation()`* (`scripts/eth_vector_phase0.py` L121/L257, `source="…engine/btc_signals.py allocation()"` at `engine/signal_lab.py:643`). Every ETH gate — the DSR, the split-half, the leave-one-crisis-out, the brake-matched-200dma comparison — runs through the same `allocation()` that masks midterm years to 0 (`btc_signals.py L546`). The signal_lab record even quotes "**DSR 0.9965**" as BTC's SCORED benchmark that ETH "fails to clear" (`signal_lab.py:625`). So the single most-cited robustness number in the *entire crypto suite* is a gate-baked figure, and the ETH sleeve's whole comparison frame ("aligned with the scored BTC Vector") inherits the contamination. Any fix to the BTC DSR must re-run ETH too or the sibling silently keeps the poisoned benchmark. **Evidence:** `eth_vector_phase0.py:121,257`; `signal_lab.py:625,643`.

**M2 — The alert engine will FABRICATE a "grid" attribution for the gate.** `btc_alerts.py:274-284` reads `sig["alloc_optimal"]` (the *gated* series) and, on the Jan-1-2026 transition to 0%, emits: *"Allocation changed to 0% BTC / Optimal strategy moved X% → 0% BTC **(momentum × risk grid)**."* This is an *active misattribution*, not a passive omission: the alert names the momentum×risk grid as the cause of a move that the calendar gate produced, and it fires into `alerts.jsonl` (newest-first, consumed by the home hub which normalizes vector + macro feeds). The panel's UX-honesty findings covered the *page* headline but missed that the *alert stream and the home hub* propagate the false "grid" causal story to a second surface with its own audience. **Evidence:** `btc_alerts.py:274-284`; alert `id` dedups across sentinel + daily recompute, so it is durable.

**M3 — The marginal-holder mechanism (DAT/treasury demand) is not just absent from the gate — it is a DISPLAY-ONLY, DEGRADE-NEVER-RAISE gauge that also introduces an unmodeled correlated tail.** The panel flagged (d6) that ETF/treasury flows don't feed the gate. Reading `btc_dat.py` reveals two additional gaps: (a) the engine explicitly computes `forced_sell_distance_pct` = how far BTC is above MSTR's ~`avg_cost × 0.78` margin-call level — i.e., the code *knows* a leveraged marginal holder can be force-liquidated, a NEW reflexive down-leg mechanism that did not exist in the 2014/2018/2022 cycles the gate is fit to. This simultaneously (i) makes the *dampening* thesis fragile in the other direction (a DAT unwind could deepen, not dampen, a drawdown) and (ii) is a fresh source the cycle clocks cannot see. (b) It is `DISPLAY-ONLY, DEGRADE-NEVER-RAISE` and reads a *manually-maintained* JSON (`data/dat_holdings.json`) — a staleness/liveness hole identical in spirit to the hardcoded cycle pivots (d6-engine), on a metric that is one of the most decision-relevant new structural facts. **Evidence:** `btc_dat.py` header (mNAV, `forced_sell_distance_pct`, `margin_haircut:0.78`, manual JSON); wired at `build_vector.py:2350-2355` display-only.

**M4 — `vector_allocation.html` is a full second decision surface with its OWN hand-duplicated gate guard.** The panel's d-hardgate-04 noted the two-source-of-truth risk *within* vector.html. But `vector_allocation.html.j2:153` carries an *independent* `and not (midterm and midterm.active)` belt-and-suspenders clause (the comment itself admits "the two pages … cannot drift" is only *aspirational* — enforced by hand, not structure). This is a *third* copy of the blackout label ("Proprietary cycle timer · holding cash", `vector_allocation.html.j2:143`) and a second page where the ungated stance/needle/verdict can contradict the 0% (the gate-vs-prior d-hardgate-02 failure mode replicates here, un-audited). The panel analyzed vector.html's internal drift but never established that the sibling *page* is a parallel, separately-rendered attack surface with the same latent contradictions. **Evidence:** `vector_allocation.html.j2:143,153`; `build_vector.py:2136-2137`.

**M5 — No forward-grading ledger exists for the gate, even though the machinery to build one is already shipped for everything else.** The panel (d-ledger-cannot-falsify) noted the *regime* ledger can't touch the gate. The stronger, missing point: the repo has a *forward outcome logging* discipline (`data/vector/regime_ledger.jsonl`, `impulse_ledger.jsonl`, `us_board_ledger`, `signal track record logger` per memory) that grades live calls against realized outcomes and auto-demotes. The gate — the one rule sizing real money — has *zero* forward ledger row anywhere (`trial_ledger.jsonl` has 20 rows, none vector/midterm). So the gate is uniquely exempt from *both* the ex-ante DSR *and* the ex-post forward-grading ledger. It can never accrue a track record that would falsify it, by construction. This is a governance gap distinct from "it's not in the DSR."

**M6 — `buy_lead_days=0` means the gate releases AT the vote, structurally guaranteeing the re-entry is late relative to the thesis's own bottom projection.** Multiple findings mention this in passing, but none names it as a self-inflicted timing defect: the *thesis monitor's* projected accumulation window opens ~Oct (lead 360d), yet the gate's own release is pinned to election day (~Nov 3). Even taking the thesis at face value, the gate is *mis-tuned against the engine's own bottom estimate* — it holds cash through the front of the projected accumulation window and re-enters after. The one tunable knob is set to the value that maximizes the miss. **Evidence:** `config.yml:3317` `buy_lead_days:0`; `btc_cycle_thesis.py:38-39` window lead 360d; overlap Oct→Nov.

**M7 — The owner's stated utility is nowhere encoded, and the memory says the owner "trades conviction on low-n mechanism theses."** d6-decision-theory noted no utility function. The missing second-order point: the *product itself* is the owner's decision aid, and the memory profile (`user-trades-conviction-low-n`) says the owner acts on exactly this kind of thesis with real money. So the UX-honesty scrub (relabeling to "Proprietary cycle timer," deleting the n=3 caveat) doesn't just mislead *subscribers* — it removes the owner's *own* future-self guardrail against the exact failure mode the memory says he's prone to. The scrub degrades the tool's fitness for its primary user, not just its paying users.

---

## (2) Dangerous problem-combinations (emergent, not visible in any single finding)

**C1 — Circularity × ETH contamination × "SURVIVES" stamp = a self-reinforcing validation cartel.** M1 + the DSR-circularity cluster: BTC's gated Sharpe produces DSR 0.9965 → that number becomes the *benchmark ETH is measured against* → ETH "aligns with the scored BTC Vector" → the crypto sleeve as a whole reads as a two-asset validated system. One gate-baked number launders itself into a *portfolio-level* credibility claim across assets. A reviewer correcting only BTC would leave ETH pointing at the stale benchmark.

**C2 — Ungated display signals (d-hardgate-02) × the alert stream (M2) × two pages (M4) = a coordinated contradiction the user cannot escape.** During a 2026 rally: vector.html hero says ACCUMULATE, the needle says 60/40 bull, the alert feed says "Optimal strategy moved to 0% (momentum × risk grid)," vector_allocation.html mirrors the 0%, and the home hub surfaces the alert. Every surface the user touches tells a *different* story about *why* they're in cash, and one of them (the alert) actively blames the grid. This is not one self-contradicting screen — it's a self-contradicting *product*, and the inconsistency is worst precisely in the scenario (rally) where the cost of trusting the 0% is highest.

**C3 — Dampening (d4) × DAT forced-sell mechanism (M3) = the gate is fit to a bear shape that may be simultaneously shallowing AND fat-tailing.** The gate assumes deep, slow, capitulation-into-midterm bears. New market structure could make bears *both* shallower on average (dampening → gate save shrinks) *and* occasionally deeper/faster via a reflexive DAT/leverage unwind (a tail the calendar gate can neither predict nor exit). The gate is maximally wrong for *both* halves of the new distribution: negative-EV in the modal shallow case, and blind to the new fat tail. No single finding captures this bimodal mutation.

**C4 — Hardcoded 2025-10-06 top (d6) × calendar-only gate × invalidation-doesn't-reengage = a stale-anchor that can strand the book.** If the true top prints *after* the stale config date, the phase clock flips to "invalidated" (bull), the thesis card goes red — and *nothing re-engages* while the calendar gate still holds 0%. The manual-config staleness and the missing off-ramp compound: a data-entry lag becomes a year of missed upside with the engine's own monitor screaming into a color.

---

## (3) The single META-PROBLEM (root cause)

**A human conviction override was laundered through the engine's own validation, display, and falsification machinery so that it reads as a validated proprietary edge everywhere while being structurally exempt from every check the system applies to everything else.**

Concretely: the midterm gate is (a) *baked inside* `allocation()` so it silently rewrites every backtest, alert, sibling asset, and page that consumes the allocation series; (b) *invisible* to the DSR, the trial ledger, the cross-validation, and the forward-grading ledger — the four instruments the repo built precisely to catch discretionary overfitting; (c) *decoupled* from every falsifier the system computes to police its own thesis; and (d) *relabeled* to hide its n=3/discretionary provenance at the point of decision. Every one of the 40+ findings is a *symptom* of one architectural choice: **the most consequential rule was placed in the one position — the final in-place mask inside the shared allocation primitive — where it maximizes downstream contamination and minimizes auditability.** It is inside everything it should be measured *by*, and outside everything that should measure it.

The corollary root cause the fix program must internalize: **the engine has no concept of "a rule that sizes money must also be graded like one."** Sizing authority and falsification authority are wired to *different* objects (gate sizes; ledger/DSR/thesis grade the display tiers). Fix the *coupling*, not the individual symptoms.

---

## (4) Suggested priority ordering for the fix program

**Phase 0 — Stop the contamination at the source (decouple, don't yet re-decide).**
1. Move the gate *out* of `allocation()`; emit an **ungated `alloc_optimal_raw` twin** alongside the gated series (mirror `risk_radar.py:484 state_ungated`). This single change de-poisons the backtest, DSR, ETH sleeve, alerts, and both pages at once. Nothing else can be honestly measured until this exists.

**Phase 1 — Make the gate visible to every check it currently escapes.**
2. Rerun DSR/CV on the *ungated* series; report gated-vs-ungated side by side; count the gate as ≥2 degrees of freedom in `n_trials`. **Re-run ETH phase0 and fix the `signal_lab.py:625` benchmark (M1/C1).**
3. Create a forward-grading ledger row for the gate (M5) so it accrues a falsifiable track record.

**Phase 2 — Fix the active misattribution and cross-surface contradictions.**
4. Fix the alert copy (M2) — never attribute a gated move to the "momentum × risk grid."
5. Gate the ungated display signals (stance, needle, verdict, accumulate badge) OR add a single reconciliation line, on *both* vector.html and vector_allocation.html (C2/M4), via one shared `suppressed_by_blackout` flag stamped on the data, not hand-duplicated Jinja.

**Phase 3 — Restore honesty at the point of decision (owner + subscriber).**
6. Restore the deleted n=3 / in-sample-MAE / amplitude-dampening / decoupling caveats *adjacent to the 0% headline* (ux-scrub, ux-headline-separation) — this protects the owner's own low-n-conviction failure mode (M7), not just subscribers.

**Phase 4 — Re-decide the instrument itself (only now that it can be measured honestly).**
7. Wire the gate to live evidence / the thesis falsifiers (regime-mutation cluster); tune `buy_lead_days` against the thesis's own projected window (M6); build and backtest a partial/hedged/brake-only alternative and a per-cycle EV-vs-bear-depth breakeven (decision-theory cluster); ingest the DAT forced-sell + dampening signals as gate inputs (M3/C3).

**Files most load-bearing for the program:** `engine/btc_signals.py` (L461-480 gate def, L525-546 application — the single point to refactor), `scripts/calibrate_vector.py` + `data/vector/{calibration.json,trial_log.json}` (the blind certificate), `engine/btc_alerts.py:274-284` (the false-attribution alert), `scripts/eth_vector_phase0.py` + `engine/signal_lab.py:643` (the contaminated sibling), `templates/vector_allocation.html.j2:143-153` (the parallel page), `engine/btc_dat.py` (the unmodeled marginal-holder tail).

---

# Appendix C — Method & provenance (how much to trust this)

**How it was produced.** A single Opus reconnaissance pass first read the live engines, config, calibration artifacts, and templates to establish ground truth (confirming, among other things, that the midterm gate is applied inside `allocation()`, is absent from `trial_log.json`/`calibrate_vector.py`, and that the live allocation is 0%). A 66-agent deep-reasoning workflow then ran: **9 problem-finders** (each assigned a distinct dimension — statistics, regime-mutation, gate-vs-prior, falsification, governance, UX, instrument design, engine integrity, decision theory — and required to cite file:line), **per-problem adversarial verification** (each claimed problem re-checked against the code by a skeptic instructed to demote weak claims), a **devil's-advocate steelman** and a **completeness critic**, then a **synthesis** pass that merged, de-duplicated, and de-escalated.

**Confidence calibration.**
- 54 problems were surfaced; 53 survived adversarial verification; the synthesis then **merged heavy duplication** (the "gate absent from the DSR" fact had been filed ~7 times), **demoted 3 already-mitigated items**, and **de-escalated 2 self-refuting ones** (A4 stale n_trials; F3 truncation-bias) into their honest, narrower form. Treat the *de-escalations as load-bearing*: they tell you where NOT to spend effort.
- The three most surprising cross-cutting claims were **independently spot-verified against the code** by the reconnaissance pass: ETH's reuse of `btc_signals.allocation()` (`eth_vector_phase0.py:121,257`), the alert grid-misattribution (`btc_alerts.py:274-281`), and the DAT forced-sell tail (`btc_dat.py`, `margin_haircut:0.78`). All three hold.
- Line numbers were accurate at 2026-07-01 on branch `claude/zen-volhard-77003f`. Re-grep before editing; the tree churns via daily rebuilds.

**What this deliverable deliberately does NOT do.** It proposes no solutions, writes no code, and picks no phasing. That is Fable's charter.
