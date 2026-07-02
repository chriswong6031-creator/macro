# BTC Vector Fix Masterplan — the Override-Registry Program

> **Produced:** 2026-07-02 by Fable 5, from: [BTC_VECTOR_PROBLEM_AUDIT_FOR_FABLE.md](BTC_VECTOR_PROBLEM_AUDIT_FOR_FABLE.md) (66-agent problem audit) → Fable takeover judgment → an 8-agent expansion + red-team pass (5 expansion finders; 3 Opus adversarial judges: overfit-hawk / execution-risk / owner's-advocate) → **4 owner decisions recorded 2026-07-02**.
> **Hard deadline:** the thesis monitor's projected bottom window opens **2026-10-01** (~90 days out). W0–W4 must be merged and running before then.
> **Execution model routing:** Fable/Opus = design + review; Sonnet = build; Haiku = mechanical. Every wave: fresh branch off `origin/main`, logic commit separated from artifact churn, squash-merge same day.

---

## 0. The meta-problem being fixed (one paragraph)

The midterm-election blackout — the rule forcing the live model to **0% BTC through 2026** — is a human conviction override applied as the final in-place mask inside the shared `allocation()` primitive ([btc_signals.py:525-546](../engine/btc_signals.py)). From there it silently rewrites every backtest, the ETH sleeve, the alert stream, the AI Daily Brief, the meta-label training set, and three dashboard pages, while remaining invisible to the DSR, the trial ledger, and every falsifier built to police it. The cure is **not** to delete the override (it is a deliberate, legible owner decision) — it is to make conviction a **first-class, declared, graded instrument**: sizing authority and falsification authority wired to the same object. *A rule that sizes money must be graded like one.*

## 1. Owner decisions (recorded 2026-07-02 — these ARE the approval acts)

| # | Decision | Owner's choice |
|---|---|---|
| D1 | Off-ramp when the thesis's own falsifier trips (new-ATH close during the claimed markdown) | **FULL AUTO-RELEASE** — steps the gate down to the engine's raw allocation after the pre-committed confirm window. Ships enabled. |
| D2 | Subscriber-facing wording next to the 0% headline | **Keep current scrub** ("Proprietary cycle timer"). Full honesty payload (n=3, dampening, discretionary status, falsifier health) goes to the **owner view only**. |
| D3 | Live shadow counterfactual (gated-vs-ungated equity) | **Owner-only**, always both-sides framed (regret number + what the gate saved at the same point in prior cycles), no action affordances. |
| D4 | Re-entry when the bottom window opens (~Oct 2026) | **Staged tranches, AUTO** — 2-3 pre-sized tranches fill automatically as validated triggers confirm; owner can halt any time. |

| D5 | Pre-window deep-value sleeve (Class-2): if MVRV-Z prints <0 before the Oct-1 window opens | **NO PRE-WINDOW SLEEVE** (decided 2026-07-02 with the W1 evidence attached: breakeven ≈−30/−35%, 2014 gate-loss on the shallow bear, 2022 MVRV fire 5mo early at −30% further MAE, live shadow shows gate winning). 100% cash until the calendar spine takes over Oct 1; a pre-window MVRV-Z<0 fire raises an OWNER ALERT only. Class-2 remains shadow-graded for future cycles. |

All five owner decisions are now closed. No further sizing-authority changes without a new recorded decision.

## 2. Live state at plan time (2026-07-01)

- BTC **$58,964**, −53% from the 2025-10-06 top ($126k). Thesis monitor **INTACT**, 4/4 falsifiers green (2 of which are structurally unable to fire in-window — fixed in W2).
- Gated allocation **0%** on all four variants. **Ungated engine wants 22.7%** (all variants; entirely from the bottom-pressure washout overlay — grid itself is 0 in bear/high-risk). 2026 ungated mean 16%, >0 on 101/182 days.
- Projected bottom window **2026-10-01 → 2026-12-10**; gate self-releases ~2026-11-03 (`buy_lead_days=0`).
- MVRV-Z 0.171 (cheap, not <0); bottom_pressure 0.698 (overlay firing); composite DISTRIBUTE; momentum bear; risk high.

## 3. Contamination map (what W0 must wire, verified file:line)

| Consumer | Reads | Effect today | W0 action |
|---|---|---|---|
| `scripts/calibrate_vector.py:620` | gated `alloc_*` | future recalibrations bake the gate into the certificate | recompute DUAL (raw + final) in W1 |
| `engine/btc_alerts.py:274-281` | gated `alloc_optimal` | **fabricates** "(momentum × risk grid)" attribution for gate moves | attribute from `override_id`; fix copy |
| `engine/master_brain.py:529-530,565` | gated `alloc_optimal` | AI Daily Brief narrates 0% as the engine's read | feed BOTH (`alloc_optimal` + `_raw` + `override_active`) so the LLM narrates the override honestly |
| `engine/btc_recommend.py:135` | gated `alloc_optimal` | kpct anchors bands at 0 all year | anchor on `_raw` (display already suppressed by blackout flag — unchanged UX) |
| `engine/meta_label.py:385` | gated `alloc_optimal` | training events erased for gated windows | repoint to `_raw` (leaf is OFF; co-commit with W1 stats rerun) |
| `scripts/eth_vector_phase0.py:119-122` | copies `midterm_gate.enabled=true` | ETH validated with a BTC political-calendar rule (no ETH basis) | explicit `midterm_gate={'enabled':False}` + note; rerun in W1 |
| `scripts/integration_lab.py:120,129,135` | gated base + gate-defeating floors | **spurious ELIGIBLE verdicts** (floor beats a cash base in 2026) | base on `_raw`; mask `override_active` bars from footprint/Sharpe |
| `scripts/btc_vector_optimal_phase0.py:85` | `compute_all()` (gate-inheriting) | future SCORED reruns silently gate-baked | assert/disable gate for the scored run; W1 |
| `scripts/build_btc_strategy.py:197-211` | applies gate to both strategies | 441×/Sharpe 1.29 marketing numbers are gate-baked | W1 relabel + dual numbers |
| `site/vector_timeline.json` / Time Machine | gated history | scrubber shows gated 0% as organic engine output | W5 label gated spans |
| `engine/commodity_signals.py` | own allocation | **gate-clean** (verified) | none |

**Provenance verdicts (forensics):** `signal_lab.py` SCORED row (DSR 0.9965) and `data/vector/calibration.json` are **pre-gate → stale-but-clean** — they certify a strategy that no longer exists; the live gated strategy has **never been graded**. `btc_strategy.html` numbers are **gate-baked**. W1 fixes both directions (relabel + dual recompute).

## 4. Final architecture (post-red-team)

### N1 — Override Registry (the spine) — SHIP
- **Declarations in `config.yml`** under `vector.overrides:` (input=config, matching the existing `midterm_gate` home — NOT `data/` which is build output). Each override: `{id, thesis, basis_n (machine-read), scope, release_rules[], falsifier_authority, grading_spec, dof_cost}`. `dof_cost` **must** feed `n_trials` the moment the override is *written* (registry = the thing that makes DOF more expensive, not cheaper).
- `allocation()` becomes pure engine; a separate `engine/btc_overrides.py::apply(alloc_df, cfg, ctx)` emits **both** `alloc_<name>` (final; live behavior unchanged) and `alloc_<name>_raw`, plus `override_active` / `override_id` columns. Consumers are whitelist-based (verified) → additive is safe; attribution requires the deliberate per-consumer wiring in §3.
- Grading ledger **output** in `data/vector/override_ledger.jsonl`.

### N2 — Evidence authority classes — SHIP-MODIFIED
- **Class 1 (auto-release, owner-approved D1):** invalidation redefined **anchor-independent** — a **new all-time-high daily close** (`close > running ATH`) during the claimed markdown, NOT `close > close.asof(config_anchor)` (the hawk's kill: the anchor date is hand-set, single-day `asof` is fragile). Confirm window **N=5 consecutive daily closes** above the prior ATH — pre-committed here, registered as 1 DOF, never re-tuned. Release target = **the engine's raw allocation** (brake/conviction stack then governs), not a hand-set number. Also wires `_cond_up_prob` to zero its markdown tilt when invalidated.
- **Class 2 (deep-value softening): earns authority from the shadow.** NOT wired in this program's W2. The raw series already carries the deep-value floor; the owner-only shadow (D3) accrues out-of-sample evidence; D5 is asked with the W1 breakeven evidence attached; if approved → single pre-committed cap, registered DOF. (Hawk: MVRV n=356 is overlap-inflated ≈ ~46 independent windows; `bottom_pressure` is a ~16-DOF hand-set composite — neither may modulate live sizing on in-sample credentials.)
- **Class 3 (display regime composite): permanent zero authority.** The firewall stays.

### N3 — Measurement artifacts — SHIP (constrained)
- **Per-cycle attribution table:** 2014/2018/2022 gate P&L decomposed (drop-avoided vs recovery-missed, total-return basis); 2026 shown as PENDING, never banked.
- **Bear-depth breakeven:** block-bootstrapped **CI fan only**, labeled "n=3 path shapes; illustrative, not calibrated" — never a point D* trigger.
- **Live shadow strip (owner-only, D3):** cumulative gated-vs-raw equity since gate engagement, ALWAYS paired with "at this point in 2018/2022 the gate trailed by Y% before the drawdown it dodged." No buttons.

### N4 — Sub-claim decomposition ledger — SHIP (constrained, deferable)
Frozen, pre-committed sub-claim set (registered in the registry, no post-hoc additions); family-wise/FDR-corrected flags; **monitoring only, never authority**.

### N5 — Staged auto re-entry (owner-approved D4) — SHIP (**REDESIGNED 2026-07-02 after the W1 trigger eval**)
**W1 eval (research/BTC_REENTRY_TRIGGER_EVAL.md): ALL SIX candidate evidence triggers FAILED the pre-registered bar** (hit_180d≥70% ∧ MAE<−25% ≤30% ∧ n≥4): MVRV-Z<0 67%/33%/n=3 · 20w-MA reclaim 56%/40%/n=9 (two 2022 false reclaims; fired again 2026-05-08 and failed — it is a validated REGIME spine, NOT an entry trigger) · BP≥0.45 64%/29%/n=18 (closest; ~16 hand-set DOF) · combos add nothing. **No evidence signal may hold tranche AUTHORITY.** Redesign:
- **Calendar-scheduled tranche spine (the authority):** window opens at the thesis monitor's projected window (2026-10-01), replacing `buy_lead_days=0`; tranches fill on schedule — T1 40% at window open, T2 30% +30d, T3 30% +60d — deterministic, zero evidence DOF, same evidential class as the window commitment itself.
- **Evidence ACCELERATORS only (never blockers/vetoes):** ONE registered rule — a fresh MVRV-Z<0 print OR fresh BP≥0.45 cross pulls the NEXT scheduled tranche forward to that day. Bounded loss by construction (can only move a fill earlier inside an already-committed window). dof_cost registered.
- **Soft-alert hypothesis (zero authority):** "20w-MA reclaim gated by MVRV-Z<0 within prior 180d" (would have filtered both 2022 false reclaims) — born from this data, so it can be validated ONLY by the 2026 bottom itself (true OOS); logged as a pre-registered W5 hypothesis.
- **DAT forced-sell proximity = advisory chip, not a veto** (feed exists in `engine/btc_dat.py` but is a hand-maintained JSON; add staleness flag; hard-block only if/when the feed is automated).
- Class-1 auto-release (N2) and calendar re-entry compose: earliest wins; owner halt switch on everything.
**⚠️ Any W4 session started from the ORIGINAL chip spec ("validated triggers only") must adopt THIS revision — the original trigger list is void.**

### N6 — Two-audience honesty (owner decision D2) — SHIP-MODIFIED
- **Subscriber surfaces: unchanged** ("Proprietary cycle timer" scrub stays).
- **Owner view:** full payload — n=3, in-sample MAE, dampening −84→−77→−52, discretionary-override status, falsifier health with **evaluability** ("2/4 evaluable" when 2 cannot structurally fire — never a false "4/4 green"), the shadow strip, the ungated counterfactual (22.7% today). Home: **admin console panel** (admin.mastermind-x.com) fed by a new `data/vector/override_shadow.json` build artifact; interim fallback = unlisted noindex page.

### N7 — Stats hardening = the governance gate — SHIP
Dual DSR/CV (raw + final) with registry `dof_cost` counted; block-bootstrap effective-N replacing raw `sqrt(T-1)`; ETH phase0 rerun ungated; signal_lab SCORED row corrected (stale-pre-gate relabel + fresh dual numbers); `btc_strategy.html` dual/relabeled. **Rule: no authority flip (Class-2, new triggers) without deflated-DSR passage + shadow OOS evidence.**

### N8 — Falsifier repair — SHIP (pulled ahead of the off-ramp)
Desync detector anchored to the **actual halving date** (currently `peak+364d` — never references the halving it names); timing-OVERDUE window derived from halving structure so it can fire inside the gate window (pre-committed, not tuned-to-fire); ATH-based invalidation (shared with N2); pivot-staleness alarm (config top vs live running extreme — nothing today detects a stale hand-set anchor).

## 5. Waves

### W0 — Decouple + de-lie (Sonnet build → Opus review; target: days)
Registry v1 in config.yml (midterm gate re-declared as `vector.overrides[0]`, back-compat kept); `btc_overrides.py` apply-layer; dual series + `override_active`/`override_id` through `compute_all` → signals.parquet; deliberate consumer wiring per §3 (alerts attribution fix; recommend kpct→raw; master_brain dual feed; meta_label repoint; ETH decontamination flag; integration_lab base/mask); test updates (`test_allocation_midterm_gate_forces_flat` → assert non-raw columns only; NEW parity tests: gated==raw outside windows, raw ungated inside, attribution columns correct). **No live behavior change.**
**Acceptance:** full test suite green; `signals.parquet` carries both series; a rendered alert about a gate move names the override, not the grid.

### W1 — Measure (Sonnet; Opus judges the artifacts)
Shadow artifacts + owner JSON (`override_shadow.json`) + admin panel (or unlisted page); per-cycle attribution table; breakeven CI fan; dual DSR/CV rerun with override DOF; ETH phase0 rerun; signal_lab + btc_strategy corrections; **bottom_pressure & MVRV/washout fire-conditional BTC backtest** (oracle ceiling / stop-out floor — feeds W4 trigger eligibility).
**Acceptance:** calibration artifacts carry raw+final; every stale/gate-baked number in §3 relabeled or recomputed.

### W2 — Falsifier repair + AUTO off-ramp (Opus design-review → Sonnet; owner-approved D1)
N8 first (halving-anchored desync, timing window, ATH invalidation, staleness alarm), then Class-1 auto-release wired: new-ATH×5-closes → staged step-down to raw allocation; high-priority alert narrates it; `_cond_up_prob` tilt zeroing.
**Acceptance:** simulated new-ATH scenario releases the gate in backtest replay; falsifiers can fire in-window; DOF registered.

### W3 — Honesty surfaces (Sonnet + Haiku; owner decision D2/D3 baked)
Owner view (admin panel): full payload + shadow strip (both-sides framing, no buttons) + falsifier evaluability. Subscriber surfaces untouched. Accumulate-badge blackout guard (the one unguarded buy-side badge); single stamped flag consumed by all three pages (kill hand-duplicated Jinja).
**Acceptance:** subscriber pages byte-identical except the badge guard; owner panel renders live.

### W4 — Staged auto re-entry (Fable/Opus design → Sonnet; owner-approved D4)
Calendar-scheduled tranche spine + evidence accelerators per the REVISED N5 (the original "validated triggers" list is void — all failed the W1 pre-registered bar) + halt switch + DAT advisory chip + dat_holdings staleness flag. Composes with Class-1.
**Acceptance:** replay of 2018-12 and 2022-11 bottoms fills tranches inside the historical windows; 2026 dry-run arms correctly; DOF registered.

### W5 — Grading + deepening (Haiku/Sonnet; deferable pieces last)
Override forward-ledger rows + frozen FDR-corrected sub-claims; block-bootstrap effective-N in DSR; Time-Machine gated-span labeling; timeline honesty.

**Designated cuts if the deadline squeezes:** DAT anything → N4 sub-claims → block-bootstrap refinement. **Never cut:** W0, W1's dual-DSR + shadow, W2's Class-1, W4's calendar+trigger core.

## 6. Status log

- 2026-07-02 — Masterplan committed. Audit: macro#816. Expansion+red-team: 8-agent workflow (this doc §4 constraints). Owner decisions D1-D4 recorded. W0 delegated to Sonnet (Opus review) — branch `btc-vector/w0-decouple`.
- 2026-07-02 — **W0 MERGED** (macro#832): `engine/btc_overrides.py` apply layer, dual `alloc/_raw` series, honest alert attribution, ETH/meta_label/integration_lab decontaminated. Parity bit-identical; 87 tests.
- 2026-07-02 — **W5 shipped (out of order)** — branch `btc-vector/w5-grading`. Delivered: override forward-grading ledger (`engine/btc_override_ledger.py` → `data/vector/override_ledger.jsonl` + `override_scored.json`; FROZEN v1 sub-claim family of 4, PIT circular block-bootstrap null on strictly pre-gate returns, BH step-up q=0.10 with m=4 fixed, significance on adjusted p; MONITORING ONLY, stamped daily from build_vector); block-bootstrap effective-N in the DSR (`engine/validation.bootstrap_effective_t` + opt-in `t_eff=` — commodity/forex callers bit-for-bit unchanged); registry `dof_cost` counted into the declared trial budget (legacy fallback midterm_blackout=3 until `vector.overrides` lands; registry precedence, no double count); `trial_log.json` surgically refreshed 50→65 config (+3 dof = 68 declared) WITHOUT a recalibration — a full calibrate rerun today would gate-bake `calibration.json`, which stays W1's dual-recompute job; 32-family band-edge FDR note added; Time-Machine tape carries a `gated` array (2018/2022/2026 spans) and the scrubber labels them "cycle timer active" (D2 subscriber-safe wording) so the override's 0% never reads as organic engine output. First live score: all 4 sub-claims PENDING, etas 2026-12-10 / 2026-11-03 / 2027-03-10 / 2027-05-02.
- 2026-07-02 — **Prerequisite discrepancy recorded:** W5 was commissioned as "W0–W2 merged"; at execution time W0 was mid-flight (uncommitted, branch `btc-vector/w0-decouple`) and W1/W2 had not started. W5 was therefore scoped to the W0-independent + forward-compatible subset: no config.yml edits (W0 owns the registry declaration; `grading_spec` for the frozen 4 should be added to the `midterm_blackout` registry entry when W0 lands — the ledger reads it and warns on drift), and the ledger accrues forward rows from today rather than waiting (each day of delay = lost forward evidence before the 2026-10-01 window). **Program NOT closed:** W0 merge remains the spine; W1 dual DSR + shadow, W2 Class-1 auto-release, W3 owner view, W4 staged re-entry all outstanding against the 2026-10-01 deadline.
- 2026-07-02 — **W3 (honesty surfaces) shipped (macro#838)** — executed concurrently with W0 (#832) + W5 (#837) landing; rebased onto both before merge. The owner artifact consumes W0's dual series (`alloc_*_raw`) with the pre-W0 local gate-off recompute kept as a parity-checked fallback (`parity_ok`); falsifier evaluability is the pre-W2 structural read (2/4 — timing + desync cannot fire in-window; W2 repairs them). Shipped: `btc_signals.gate_state()` = the ONE stamped gated-state flag (vector.html.j2 + vector_allocation.html.j2 + btc_strategy ctx; hand-copied `and not (midterm and midterm.active)` guards killed); accumulate badge gated via the rec card's stamped suppression key (was the one unguarded buy-side badge — would have flashed "ACCUMULATION ZONE" beside a forced 0% Oct 1–Nov 3); `data/vector/override_shadow.json` owner artifact (n=3 provenance, in-sample pivot MAE 7.2d, dampening −84→−77→−53, ungated 22.7% vs gated 0%, falsifier health×evaluability, both-sides shadow strip per D3) + admin-console **BTC Override** tab (owner-only per D2; zero action affordances). Acceptance verified: A/B render old-vs-new templates on the same live context → both subscriber pages BYTE-IDENTICAL (badge dormant today, `ct.accumulate=False`); owner panel renders live. VPS `admin.service` restart required to pick up the new tab. Outstanding: W1 dual DSR + measured shadow artifacts, W2 falsifier repair + Class-1 auto-release, W4 staged re-entry.
- 2026-07-02 — **D5 DECIDED: no pre-window sleeve** — pure calendar until 2026-10-01; pre-window MVRV-Z<0 fire = owner alert only (W2 should wire that alert). Class-2 stays shadow-graded.
- 2026-07-02 — **W1 built** (this commit): dual-track calibration (gated Sharpe 1.56 / DSR 0.9986 vs raw 1.43 / 0.9945; effective-N companion dsr_effN 0.9622/0.9236; n_declared 65+3=68 — reconciled onto W5's block-bootstrap t_eff + n_declared schema, double-count fixed), signal_lab SCORED row provenance-corrected (pre-gate 0.9965 retired), ETH decontaminated rerun (DSR 0.5345, still confirmer), btc_strategy dual render, owner-only shadow artifact (`data/vector/override_shadow.json`: raw −6.2% vs cash @181d, vs −13.3%/−20.0% same-point 2018/2022), per-cycle gate attribution (2014 **−4.2% gate LOST** · 2018 +24.8% · 2022 +17.9% · 2026 PENDING), breakeven fan (**gate edge dies below ~−30/−35% window drawdown**; 2026 window ≈−33% so far = ON the line), trigger eval (**all 6 failed the pre-registered bar → N5 REDESIGNED** to calendar-spine + accelerators, see §4). D5 evidence package ready for the owner.
