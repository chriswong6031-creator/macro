# Engine Fix Masterplan

**Date:** 2026-07-01 · **Companion:** `research/ENGINE_PROBLEM_AUDIT.md` (46 problems, 8 themes — referenced below as `#N`).
**Role of this doc:** the solution architecture and delegation contract. Every sub-session fixing anything in the audit gets its brief from a workstream section here plus the relevant `#N` entries there.

---

## Mission anchor

Central mission: **high-quality stock-pick signals — highest-potential names, at the right entry time, asymmetric wins.**

Backend translation of that mission, and why the phases are ordered the way they are:

1. **You cannot know which picker works while measurement is contaminated.** Leaked labels, survivor panels, same-bar fills, and revised-finals histories (Themes C, half of A/D) mean every claimed edge is an upper bound of unknown looseness. Measurement integrity is the root of the tree.
2. **Entries can't be trusted while the same signal has N divergent computations.** The Terminal, the dashboard chart, and the bot must emit the same BUY for the same symbol/date (Themes A/F), or "right entry time" is undefined.
3. **Asymmetric wins are a sizing property, not a stock-list property.** Asymmetry comes from sizing up when conviction is *calibrated* and sizing down when it isn't — which requires learning loops that actually learn and conviction badges that mean something (Themes B/E/G).
4. **A silent system rots.** Degrade-safe architecture made "broken" indistinguishable from "building" (Themes D/H). Failures must be loud or every other fix decays back to this state.

---

## The unifying primitive: Signal Passports

One recurring root cause across all 8 themes: **numbers don't carry their provenance.** A hand-set tercile, a leaked backtest edge, a 61-day-stale FRED print, and a genuinely validated IC all render as equally confident numbers, and downstream code cannot tell them apart.

The fix is a typed provenance envelope attached to every decision-facing number:

```
passport = {
  basis:      measured | prior | anecdote,     # how the value was set
  frame:      pit | latest,                    # what data frame validated it
  freshness:  { asof, expected_cadence, state: fresh|slow|stale|dead },
  n:          <graded sample count>,
  validation: { artifact, expiry, trial_budget },
  consumers:  [ ... ]                          # declared, audited for liveness
}
```

Enforcement, not decoration:
- **Gates check passports.** A `basis: prior` constant cannot bind a sizing multiplier beyond a clamp (kills #20, #37 silently over-trusted dials). An expired `validation` reverts the signal to display-only (kills #41's frozen self-certifying gates).
- **Surfaces render passports.** Conviction badges with `n: 0` say so (kills the n=0 badge class).
- **The registry (W4) enforces existence**; the liveness audit walks `consumers` (kills the orphan class, Theme H).

Every workstream below populates passport fields. By Phase 3 a passport is mandatory for anything that sizes real money.

---

## Workstreams

### W0 — Quick strikes (Phase 0 — delegated 2026-07-01)

Verified single-file bugs whose fix needs no new architecture. Rule: **honest demotion is a success outcome** — if fixing a leaked label demotes a leg, the PR reports the before/after and we ship it.

| # | Fix | Agent |
|---|-----|-------|
| #6 | Impulse-radar label window → strictly forward `(t, t+H]`, trigger-disjoint; re-run gate; per-leg min-n floor | A (Opus) |
| #27 | TSF availability-date stamping (additive column; consumers shift to post-release availability) | A |
| #28 | `anticipation.py` netliq → canonical 3-term billions formula + mixed-unit invariant test | A |
| #44 | Alpha-weight basket overlay → rolling PIT weights (or explicit in-sample disclosure if render cost forbids) | A |
| #26 | Thread `buyable`/`sig_verdict` into `entry_signal.assess()` on CN/HK/CA builders (mirror US) | B (Sonnet) |
| #34 | BTC `recommend()` must receive/emit midterm-blackout state; one shared guard, not per-template | B |
| #42 | `entered_book`/`left_book` severity high→low (rank-IC≈0 emitter); TODO→W4 IC-aware severity | B |
| #43 | Analyst convergence channel → validated revision-DELTA construction; whitehouse ticker existence gate | B |
| #18 | Intel bridge: `ai_lean` derived from dashboard decision band via mapping table + freshness gate + path fix + wire into refresh | C (Sonnet, charting-app) |

### W1 — Truth Layer & the Leakage Tax (Phase 1) — `#5 #14 #15 #21 #39 #46` (+ deep halves of #6 #27 #44)

The root. Four moves:

**a) PIT accessor** (`engine/pit.py`): `series(name, as_of, basis='release'|'reference'|'latest')`. Backed by the already-collected ALFRED vintage matrix (`data/fred_vintage/vintages.parquet` — exists, unused). For non-vintaged series: per-series release-lag calendars — static schedule priors now (BLS employment ~first Friday, CPI ~day 10–13, INDPRO ~day 15–17, NBS/PBoC TSF ~day 9–15 → conservative bound), **learned lags going forward** by recording collector fetch timestamps (`{series, fetch_ts, last_obs_date}` append-only log starts immediately, so a first-party release calendar accrues for free).

**b) Dual-frame shadow re-scoring — the "leakage tax."** Do **not** migrate 404 engines. One harness recomputes each registered signal's historical edge on the PIT frame *in shadow* and publishes `calibration/leakage_tax.json`: `edge_latest − edge_pit` per engine (for the regime: quad-label agreement %, flip-date drift, split-half edge delta). Engines whose PIT edge collapses get their passport flipped (`frame: latest` → demoted). Live paths change only when explicitly migrated. This converts an intractable migration into a measurement product, and sidesteps the partial-PIT hazard (#14's "mixing vintaged and revised legs is worse than consistent bias") because the live frame stays internally consistent until a full migration.

**c) Grading rebuild — one grader for all track records.** Next-bar fills (`FixedForwardWindowIndexer` conventions), survivorship via `universe_history.as_of_members` (**exists, imported by nothing** — wire it), dual price-return + total-return columns, delisting terminal values via the existing 8-K Item 1.03 bankruptcy imputation. Every forward logger (dashboard track_record, desk graders, bot spine in W4) routes through it. Re-issue the headline claims (e.g. the −23.7%→−15.5% drawdown improvement) on the corrected panel, whatever the answer.

**d) Trial budgets with teeth.** Harness runner requires `@register_trials(family, budget)`; `walk_forward._mt_bump` sources `n_trials` from the ledger instead of defaulting to 1; CI fails any `validate_*`/`*_phase0` script that never registered. Make registering cheaper than skipping.

**Acceptance:** `leakage_tax.json` exists with regime axes as first client; drawdown headline re-measured survivor-aware/next-bar; every DSR quote sources ledger `n_trials`; release-lag log accruing.

### W2 — Regime One (Phase 2) — `#1 #3 #4 #16 #32` (+ #29 demotion, #40 beta canon)

One canonical regime artifact with an **honest decomposition** instead of a false forward badge:

```
regime_one = {
  tape:    coincident market-proxy read (the current quad legs, honestly labeled "prices already turned"),
  macro:   PIT econ legs, release-date stamped, per-leg freshness attached,
  forward: causal (filtered, non-smoothed) base-effect/HMM probabilities + their grading ledger,
  fused_risk: { label (5-state), gross_factor, confidence }
}
```

Key mechanisms:
- **Flip attribution** — every quad/label change is decomposed into *data Δ vs renormalization Δ vs revision Δ*. A flip whose majority cause is renormalization (a dead feed vanishing from the weighted sum, `axes.py:79`) is **vetoed**: label freezes, confidence degrades, a loud `degraded` state is published. Outage-driven portfolio rebuilds (#3) become structurally impossible, without giving up graceful degradation.
- **Risk vocabulary unification** — one versioned mapping `risk_state(5) → gross_factor`. MRS is retired from the `sector_central` conviction gate via a shadow A/B: run both gates, log divergence days, replay 2026-06-23, switch only when the new gate demonstrably catches it (#4). The bot consumes `fused_risk` as its prior and may override — but every override logs `(override, delta, reason)` and lands in an admin reconciliation report. Independence-by-design survives; *silent* divergence doesn't.
- **Freshness ledger** — per-component freshness persisted alongside regime history (compact bitmask, not full `c_` columns, answering the parquet-size objection in #32) so every historical regime call is forever auditable as full-data vs price-only-proxy.
- **HMM honesty** — filtered (causal) probabilities for anything displayed as history; smoothed exists only in a research view explicitly labeled hindsight (#16). The forward suite gets the grading protocol it was always supposed to have (`validate_regime_fwd` — actually written this time), with accrual-aware interim uncertainty.

**Acceptance:** one gross number traceable end-to-end (page banner = sector gate = bot prior); 06-23 replay shows banner/gate/bot agreeing; FRED-outage chaos test freezes the label with a degraded badge instead of flipping the quad.

### W3 — Concept Canon + contracts-as-data (Phase 2) — `#7 #9 #12 #18 #28 #40 #45` (+ #3 freshness contracts)

- **`engine/canon.py`** — single implementations with golden test vectors: `net_liquidity` (3-term, billions), `credit_impulse_level` and `credit_impulse_accel` (two *names*, ending the label collision), `vix_term`, `sector_macro_beta` (shrunken measured⊕prior; retires XLC=1.0-predates-XLC). Every consumer imports it or validates against its golden vectors.
- **Cross-repo contracts as data, not code** (respects the deliberate three-repo isolation): the dashboard exports (a) **golden signal vectors** per symbol — input hash → expected BUY/SELL sequence from the *corrected* math — and (b) an **artifact manifest** `{name, expected_max_age in trading-calendar terms}`. Terminal and bot run a conformance check at startup/refresh: signal mismatch → hard fail; stale artifact per calendar-aware cadence → abstain + flag. This *inverts* `golden_gate` (#7): the oracle becomes exported corrected data, so a stale fork **fails** instead of being blessed, and it fixes the fail-open handoffs (#9) without halting on benign weekend lag (cadence is trading-calendar-aware).
- **Bridge contract** (#18 durable form): the Terminal's directional lean must be a pure function of the dashboard's composite decision band (mapping table shipped in the export). No re-derivation from single scalars, ever.

**Acceptance:** NVDA + one A-share + one HK golden vector passing in all three repos; the three divergent netliq/credit/VIX computations deleted in favor of canon; a deliberately-staled vendor file makes the bot abstain with a logged reason.

### W4 — Outcome Spine, partial-pooling learning, arm-by-evidence (Phase 3) — `#8 #10 #13 #17 #19 #23 #25 #29 #30 #31 #41` (+ #2's arming half, #11's loop half, #42 durable form)

- **The Spine:** every decision-facing signal writes a prediction row `{signal_id, engine@version, as_of, symbol, horizon, score, size_binding}`; W1's grader matures all rows. One contract across all three repos — this is the shared signal-id→outcome substrate that #13 says exists nowhere.
- **Partial pooling breaks the cold-start deadlock.** Replace every `min_n=20 else 1.0` cliff with hierarchical shrinkage: per-desk/channel/lens weights shrink toward family means (empirical-Bayes), with trust-region caps per update. Everything learns *a little* immediately; nothing swings on n=5. This is the structural answer to #19 (starvation), #11 (multipliers frozen at 1.0), and it converts #23's "high tier = hand-set prior" into an accrual-aware confidence. Convergence scoring additionally penalizes correlated same-event channels (co-firing structure estimated from the spine) instead of counting them as independent.
- **Counterfactual credit for veto seats.** A WITHHOLD/OPPOSE is graded on the avoided name's forward return, **sign-inverted** — attribution and calibration then agree in sign, and SENTINEL/Risk-Officer/Gate earn positive credit for correctly avoiding losers (#17), *before* the reputation loop is ever armed.
- **Arm-by-evidence.** No more env-flag safety. Every flag-gated system declares an **arming predicate** (e.g. derisk stack: ≥K shadow triggers with measured false-positive rate ≤ X on the spine); an "armory" report shows distance-to-arming; systems auto-arm with notification when the predicate holds. Fixes the process failure behind #2 (defense stack OFF), #11 (reputation/self-mirror OFF with no activation criterion).
- **Liveness contracts.** Manifest `{artifact, producer, expected cadence, consumers}`; nightly audit walks the import graph + runtime touch-files. Missing input file (#8 `_closes_deep.parquet`), zero-caller engine (#10 `net_exposure`, #31 `attribution.persist`/`heavyweight_outcomes`), false docstring, spec'd-veto-that-only-flags (#31 D1/D2/D4 vs DOCTRINE.md — compile doctrine clauses to assertions) → **loud failure**. "Building" and "broken" become distinguishable forever.
- **Registry firewall (validate-before-weight).** Anything failing its own gate is *automatically* display-only with a passport badge until it passes: regime-caution haircut + crowding trim (#30), negative-IC composite legs in ranking paths (#25), zero-scored convergence tiers (#23), assumption-signed single-name GEX (#29). And `promotion_gate`+`walk_forward`+`holdout_vault` (#10) finally gate real promotions through a shadow→canary→live state machine.

**Acceptance:** first deterministic weight moved by measured outcomes; `net_exposure` armed via evidence; bot predictions ledger resolving rows; zero registered-but-orphaned engines; alert severity = f(measured IC).

### W5 — Sizing & discipline rebuild (Phase 3–4) — `#2 #24 #38`

- **Reserve-preserving sizing:** initial-size discipline cash is a hard reserve; renormalization operates only within the deployable budget; cap overflow redistributes via water-filling instead of leaking to cash (#24).
- **Correlation:** wire the existing, unused `book_forecast_vol_ann` equicorrelation using the `avg_corr` already in the snapshot; book-level vol target so a correlated AI-buildout book de-grosses — the direct structural remedy for the 06-23 cause (#24).
- **Research gate with actual rejection power:** CI-enforced orthogonality test — the gate's marginal score must be provably non-collinear with confluence (bounded `corr(research_score − f(confluence), confluence)`), and the gate must demonstrate on synthetic fixtures that it *can* reject a sized name (#2).
- **Bandit → EV:** Thompson sampling on posterior mean `avg_rel_return`, not binary hit-rate (#38).
- **Autonomous book:** receives `fused_risk` in its brief by default; leaderboard uses fair cross-book attribution (gated vs ungated graded on the shared spine, risk-adjusted) (#38).

### W6 — Entry Integrity (Phase 4 — the mission workstream) — `#20 #22 #25 #36 #37`

This is the workstream closest to the mission: right entry, asymmetric wins.

- **Provisional-basis replay** (#22): rebuild the historical tier stream by replaying each historical day through the *same partial-bucket code path* the live board uses — producing the provisional-lane history the validation never saw. Measure the repaint rate and the provisional lane's true edge. Then run two lanes: **confirmed** (completed buckets — the validated basis) and **provisional** (badged, with measured repaint stats). The not-topped veto gets hysteresis/2-bar confirmation with measured precision/recall instead of a single noisy bar.
- **Calibrate the knobs that define "buyable now"** (#36): `FRESH_TICKS`, CN blend constants, `EXT_PENALTY` swept on the existing stop-out-vs-lead harness (held out), not two-name anecdotes; the anti-chase demote's live magnitude becomes contingent on its own ledger maturing.
- **Board hygiene** (#25): ranking paths can only consume registry-passing legs; composite = IC-weighted with sign constraints; FDR-failers cannot tiebreak a board a trader sizes from.
- **Dispersion dial** (#20): measure-or-demote — test whether dispersion state conditions selection-IR on this universe; resolve the up-gross-in-high-VIX contradiction against the de-gross mandate; until measured, clamp to display-only via the passport rule.
- **China Masterminds** (#37): uncertainty-banded presentation; prior-basis weights cannot advertise concrete Sharpe (passport rule again); fix CN/HK-vs-US session as-of alignment feeding conviction.

### W7 — LLM determinism & committee diversity (Phase 4) — `#11 #33 #35`

- **Determinism kit:** temperature=0 + seed where supported; prompt+input content-hash caching; ensemble-of-3 majority with abstention for anything graded or binding; event/GDELT inputs snapshotted before scoring. Applied to every graded LLM ledger (they currently measure sampling noise, #33).
- **Committee diversity that's real:** SENTINEL must not share FORGE's weights — different vendor/model via config; measure FORGE↔SENTINEL vote correlation on the spine; surface a "same-model adversary" warning at the decision layer until fixed (#11).
- **Brain input decorrelation** (#35): factor-attribute `gather_state` inputs (most share the tape); present the synthesis LLM with orthogonalized evidence and per-input lead/lag labels, so one root cause can't masquerade as 5-engine consensus.
- **spvector veto** (#33): either wire `on_stress_day` with a defined stress classifier + the determinism kit, or delete the dead "LLM oversight" UI claim. No third option.

---

## Phase map

| Phase | Workstreams | Gate to next phase |
|-------|-------------|--------------------|
| **0** (now) | W0 quick strikes | PRs merged, before/after reported |
| **1** | W1 Truth Layer | leakage_tax live; grading rebuilt; trial budgets enforced |
| **2** | W2 Regime One + W3 Canon/contracts | 06-23 replay passes; golden vectors pass in 3 repos |
| **3** | W4 Spine/learning/arming + W5 sizing | first outcome-moved weight; net_exposure armed; correlation-aware sizing live |
| **4** | W6 Entry Integrity + W7 LLM/committee | provisional lane validated; knobs swept; committee correlation measured |

**Standing guardrails for every phase:**
- Shadow-first: nothing touching live sizing flips without an A/B window.
- Honest demotion is success, not failure.
- No new env-flag safety switches — arm-by-evidence only.
- Every behavioral PR carries before/after artifact diffs in its body.
- New decision surfaces must emit passports.

---

## Delegation protocol

- Every sub-session brief carries: audit `#N` refs, masterplan workstream §, acceptance criteria, and a verify-in-code-first requirement (the audit is evidence-grounded but code moves daily).
- **Models:** Sonnet for well-specified code; Opus for judgment-heavy work (re-validation, demotions, architecture); ultracode sub-sessions permitted for orchestration-heavy builds (W1, W4).
- **Git:** branch off `origin/main`, PR, squash-merge same day (standing approval). Worktree isolation for anything mutating the dashboard repo; never edit shared checkouts concurrently.
- Cross-repo work (Terminal, bot) commits on branches in those repos; push/PR where a remote exists, otherwise local commit + report.

## Coverage matrix (all 46 → workstreams)

| # | WS | # | WS | # | WS | # | WS |
|---|----|---|----|---|----|---|----|
| 1 | W2 | 13 | W4 | 25 | W4+W6 | 37 | W6 |
| 2 | W4+W5 | 14 | W1 | 26 | W0 | 38 | W5 |
| 3 | W2+W3 | 15 | W1 | 27 | W0+W1 | 39 | W1 |
| 4 | W2 | 16 | W2+W1 | 28 | W0+W3 | 40 | W3+W2 |
| 5 | W1 | 17 | W4 | 29 | W4+W2 | 41 | W4 |
| 6 | W0+W1 | 18 | W0+W3 | 30 | W4 | 42 | W0+W4 |
| 7 | W3 | 19 | W4 | 31 | W4 | 43 | W0 |
| 8 | W4 | 20 | W6 | 32 | W2 | 44 | W0+W1 |
| 9 | W3 | 21 | W1 | 33 | W7 | 45 | W3 |
| 10 | W4+W1 | 22 | W6 | 34 | W0 | 46 | W1 |
| 11 | W7+W4 | 23 | W4 | 35 | W7 | | |
| 12 | W3 | 24 | W5 | 36 | W6 | | |

## Status log

- **2026-07-01** — Audit + masterplan committed. Phase 0 delegated: Agent A (Opus — #6 #27 #28 #44), Agent B (Sonnet — #26 #34 #42 #43), Agent C (Sonnet, charting-app — #18). Phase 1 foundation delegated: Agent D (Opus, background — W1a/b PIT accessor + leakage-tax shadow harness, regime axes first client).
