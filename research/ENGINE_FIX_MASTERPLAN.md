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

### W6-US — Buy Board 2.0 (`us_stocks.html`) — merged from the targeted US-stocks audit (2026-07-01)

**Source:** `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md` (targeted audit: 9 readers → 53 raw problems → 6 clusters + contrarian pass). Its root cause is the product-level synthesis our engine-level audit circled but didn't name: **a fixed-width imperative board (34 BUYs, "act now") is irreconcilable with a measured cross-sectional selection edge of ~0** (deep+PIT 2008–2025: rank-IC +0.008..+0.021, every composite fails DSR/FDR except insider — present on 2/34 live rows). Every downstream pathology is fill-pressure compensation: `bottoming-alignment` as gate (loose enough to admit 34), `potential_score` overwriting the honest edge percentile (`corr(score, alpha) = −0.31`), `entry_open_first` picking slot #1, missing sector cap (19/34 from 2 sectors), unreachable DSR≥0.90 gate making `validation_status` a constant.

**Cross-references into the main audit:** their thread 1 (fill pressure) ↔ #36/#25; thread 2 (two decoupled code paths) ↔ Theme F at card level; thread 3 (missingness-as-neutrality) ↔ Theme D per-name; thread 4 (validation orthogonal to shipped artifact) ↔ #10/#16; thread 5 (regime-blindness) ↔ #20. New and US-specific: the validated confluence gate protects the *wrong artifact* (`setups.json`, the table nobody reads) while the wide board the user acts on bypasses it; the live rank key was never fed to the validation harness at all; `cand_depth_pct` designed+documented+never wired; dead template sort at `dashboard.html.j2:2397`.

**Product spec (user-set, 2026-07-01):** the buy board lists names that are BOTH (a) **good to buy** — near+medium-term trajectory up — AND (b) **good entry, not chasing** — hard-gated by the validated MACD-2D×StochRSI-3D confluence (T1–T4) crossed bullish in the last few days *or about to cross*. Rotation context (sector_central.html, baskets.html, subsectors.html, subsector_rotation.html) informs **priority** for leading sectors/subsectors/themes and cross-surfaces names those pages flagged. Those cycle pages are pending their own improvement session — couple defensively.

**Design:**
1. **Three-layer conjunctive architecture.** WHAT-gate (trajectory): verdict ∉ {Lagging}, composite_z > floor, medium-term structure intact. WHEN-gate (entry): `is_buyable` confluence as hard admission — the same validated gate that already guards `setups.json` finally guards the board people read — plus freshness window, not-topped, extension guard. PRIORITY (rotation context): ordering only, never a gate.
2. **Borrow strength from the hierarchy level where edge exists.** Name-level selection IC ≈ 0, but group-level rotation signals are validated/tracked (subsectors LAS Running/Coiling carries a forward track record; sector_central is a gated-confluence merge of 4 engines). New `engine/group_context.py`: name → sector/subsector/theme states → leadership score used for (a) ordering, (b) edge-floor modulation (leading group lowers the name-level bar, washed-out group raises it), (c) "surfaced by subsectors" chips. This is W4's partial-pooling logic applied to conviction. **Hard-gating by group state is forbidden until the ledger proves it** — the China falsification (subsector-state gates *hurt* A-share reversal) is the standing caution.
3. **Two lanes, variable width.** **ENTRY OPEN** (both gates pass, fresh cross) and **SETTING UP** (trajectory passes, cross imminent — the "about to crossover" lane). Width = however many qualify, 0..N. Kill fill pressure: no `ALIGN_MIN_KEEP` backfill, no `entry_open_first` terminal sort, no `potential_score` overwrite. An empty ENTRY OPEN lane is honest; SETTING UP keeps the surface alive. "About to cross" detection is provisional-bar-flagged until the W6 replay validates it (#22).
4. **Two glyphs, not one fused number.** EDGE grade (group+name percentile, colored by verdict — never green on a Lagging name) × ENTRY state (tier badge + freshness). This answers the audit's Q6 with the user's own mental model: they already think in two dimensions ("good to buy" AND "good entry"), so render exactly those two. The single 0–100 that anti-correlates with alpha dies.
5. **Concentration surfaced, softly capped.** Soft per-sector cap + dual-class dedup + an "effective bets" banner ("19/34 from 2 sectors ≈ 2 bets"). Leadership-driven concentration is intentional rotation-following; co-washout concentration was the bug, and removing the bottoming gate removes its cause.
6. **Track record first — via git archaeology.** `site/factordata/us_standouts.json` is committed daily (91 revisions to 2026-06-16 and accruing): reconstruct past boards from git history and grade them retroactively **now** (precision@k, per-band/lane hit rate, median excess, MAE) instead of waiting months for a ledger to mature. The contrarian warning stands: rank_by=alpha is NOT assumed — the MAE study (aligned entries vs alpha entries) decides gate/rank knobs on measured drawdown, not vibes.
7. **Shadow A/B.** v2 ships as `us_standouts_v2.json` + an unlinked preview page, graded in parallel with the live board; the live board flips only when v2's measured precision@k ≥ live.
8. **Honesty guards** (their Q10 = our passports): build fails when band contradicts verdict, when BUY renders with `signal.last.quality=="block"`, when a confirmer chip renders for a `scored:false` gate; plus a **born-dead-field linter** — an emitted honesty-critical field with zero template/code consumers fails CI (would have caught `validation_status`, `cand_depth_pct`, `rank_pctile`, and the dead template sort).

**Decisions on the audit's open questions:** Q1 variable width + two lanes (empty actionable lane is acceptable because SETTING UP shows the pipeline). Q2 timing gates and badges, never sorts. Q3 yes — precision@k and P(fwd>0|top-5) are the product-correct yardsticks; compute them. Q4 event-stack sparse signals via OR/max (insider/PEAD-real-dates/8-K) as a bonus layer instead of a weighted average that dilutes a mostly-absent leg; main answer is hierarchical borrow-strength. Q5 covered by W1c survivorship rebuild. Q7 shrink toward group prior + completeness passport chip; abstain only when entry-gate data itself is thin. Q8 precision@k with Wilson CI per lane/band, plus median excess and median MAE. Q9 compose: regime hostility (dispersion/breadth/risk-off via Regime One) modulates the edge floor; model confidence (live trailing precision) modulates label loudness. Q10 the guards in point 8.

**Delegation:** US-1 display honesty on the live board (Sonnet), US-2 measurement — ledger + git-archaeology grading + MAE/precision@k/dispersion studies (Opus), US-3 shadow v2 build (Opus). Defensive coupling: `group_context` reads the cycle pages' artifacts through tolerant readers (missing/changed → neutral + degraded passport) so the pending cycle-page improvements propagate without rewiring.

### W6-CN — China suite: match product units to validated edges (merged 2026-07-01)

**Sources:** `research/CHINA_ENGINE_PROBLEM_BRAINSTORM.md` (91 problems, 8 root causes, adversarial §8) + `research/CHINA_ENGINE_REASSESSMENT.md` (10-agent verification/gap-hunt/measurement delta: all 8 root causes CONFIRMED on current code, 17 new problems, all 10 §8 questions answered with data). Read both before any CN fix work.

**The evidence-locked architecture — each validated edge ships at its own unit; nothing crosses units:**
- **Selection (name unit): within-sector 3M reversal only** (Sharpe 0.58 upper-bound, 388 rebalances). Phase-0 verified: EVERY confirmation-style gate flips it negative (turn-confirmation → −0.29%/mo, maxDD −78.9%) — so it ships as a **Reversal Sleeve**: monthly-rebalanced, no-gate, EW, wide, small-per-name basket product ("this is a portfolio, not stock tips"), never per-name confirmation-gated. The ~10σ pairwise-correlation elevation on the current board confirms a 5-name cut would be one bet.
- **Sleeve sizing (market unit): `risk_radar_intl` CN gross_factor** — validated forward-drawdown composite on EXTERNAL drivers (doesn't cancel the contrarian edge), runs the suite's ONLY closed grade→tune→can_force loop, currently wired to ZERO CN consumers (live caution/87 while boards run ungated). Thread as a sleeve-size chip on all five pages; replace the unvalidated QVIX-only stress overlay. **Its closed loop is the template for closing every other loop.** (Name hazard: `risk_radar_intl.CN_PROFILE`, NOT the display-only `china_radar.py`.)
- **Slice confirmer (theme unit): #773 AI-semis→CN-CPO weekly confirmer** (t=3.27, survives horse-race, fully orphaned) → wire onto AI-supply THS concepts.
- **Demotions (free precision, measured):** raw hot-money LHB flag (−1.43%/21d fill-realistic) and block-trade PREMIUM flag (−0.60%/5d) are wired with the WRONG SIGN today (`china_altdata.py:33` weights lhb +0.10) — flip both to demotions. zt/连板 = chase-veto and froth-breadth only, never positive rank.
- **Probationary confirmers (forward ledger, not scored):** deep-DISCOUNT blocks ≤−15% (+3.45%/21d, t≈3.4 — best northbound replacement found), inst-seat LHB net-buy, per-name margin velocity (untested — backfill next). Availability correction: LHB/seats/blocks/AH are deeply akshare-backfillable (verified live) — upgrade drip collectors from snapshot-overwrite to range-backfill+accrue.
- **Context only:** washout signature (now ONE formula; residual = input-plane contract), low-vol tilt, A/H premium (≈0 IC as timing).
- **Act-now lane: currently EMPTY by honesty** — no signal is validated at the name/day unit. The daily board becomes Edge-vs-Timing split (US pattern) with the timing lane explicitly labeled; a signal earns act-now status only through the fill-realistic ledger.

**Grader-first sequencing (§8's own warning, now mandatory):**
1. **Un-dead the ledger:** `china_standout_track.py:82` reads store group `'china'` (30 ETFs) — 0/120 board tickers resolve; n_graded=0 FOREVER. Fix group + land CSI300-relative + fill-realism in the SAME pass so the first published number is unbiased.
2. **Fill-realistic grading (measured haircut ~1pp/entry, ~2-3pp hit — survivable, §8.7's fear unsupported):** grade T+1 (H+L)/2 (Open is NOT collected — add to `_OHLC` + backfill first), exclude locked-limit (0.22%), flag pinned refs (4-5%, bias doubles), CSI300-relative, and NEVER grade from §7 marker dates (+5.7pp/10d look-ahead via resolved 'take' labels — `signal_quality.py:163`).
3. **W1-CN leakage client:** W1 covers ZERO of the china board path. Build the truncated-replay harness (template: `tests/test_vector_pit.py`): features replay on their OWN price plane (5% row-flip tax if wrong plane), persist `bucket_end` (washout-2W flips 8.3%/day on completed-vs-live buckets), git-committed panels = free vintage matrix (0.7%/2d revisions), session guard (refuse boards whose panel row was collected <07:00 UTC — ledger integrity currently rests on a keep-first accident), gate ledger appends to the asia lane explicitly.
4. **THEN close loops** via the `risk_radar_intl` bounded-tuner pattern; partial pooling **shrinks toward ZERO, not optimism** (two proposed legs measured wrong-sign), with leakage-tax flip-rates as measurement-error inflation; AND-gates forbidden (dark for ~90% of the universe).

**Data-plane contract (new problems, all measured):** NO raw A-share price plane exists (both stores `auto_adjust=True`) → new raw+adjusted collector plane, raw for level/limit logic; `china_universe.py:306` retroactively DELETES dropped names' history columns (worse than survivorship — deletes reversal's own failure cases; all china_search-based stats are upper bounds) → append-only + dropped-date markers; `combine_first` adjustment seams (5.7% of names >0.4% basis step, May-clustered, seasonally biasing rev_z) → full-overwrite for adjusted series; Tushare plane frozen 2026-06-21 yet PREFERRED over fresh free fallbacks on file-presence → asof-aware preference + run_status registration; 46% placeholder mktcaps (==30.0亿) feed Altman-Z/PS → sentinel→None + tushare `total_mv_yi`; ST screen matches zero names — run one adversarial known-ST check; lane split: baskets_china(_ths) build one CN session behind siblings ~19.5h/day → move the build_vector hook to the asia lane (the TODO exists).

**Cross-repo blast radius (the doc's biggest blind spot):** `china_standouts.json` is a CONTRACT — the autonomous Opus PM converts `conviction.score` (= timing-only potential_score, edge_mult=1) directly to its funnel score and the MCP tool sells it as "the desks' best ideas" (used on 7/8 China turns; today's row 1: score 32, band Watch, on a BUY list). The bot re-encodes R2 (`china_intake.py:146` caps reversal at 0.5 while momentum scores 1.0) and R6 (+0.08 per "independent desk" across three same-close legs). Fixes: correct the MCP copy now; publish `data_through` distinct from `as_of` + per-leg as_of; china-anchored `is_stale()` block-by-default; trigger the bot's china turn on the asia commit (currently fires 08:00 UTC before the 12-13 UTC build → every decision reads the previous session, ~2 sessions signal-to-fill); downstream-consumer checklist so the funnel doesn't re-invert the Edge-vs-Timing fix.
**A/H crosswalk:** twin chip on both boards + coherence assert; persist the ~190-pair spot table long-form (currently mean/median only — per-pair columns discarded); compute premium from raw closes with fixed Asia-close FX.
**Coherence rule:** canonical computation, plural interpretation — ONE `china_leads` module (collapse playbook's triple-counted M2/M1−M2/TSF monetary legs to one vote, symmetric bands), ONE published regime object carrying quad + tilt + radar gross_factor + per-leg as_of + data_through with disagreement EXPLICIT; kill `china_conviction`'s cosmetic band unification; per-leg `can_force` arbitration once ledgers mature (~2 months post store-group fix).

**Delegation:** CN-1 grader/ledger truth pass (Opus — the keystone), CN-2 W1-CN leakage client + data-plane integrity (Opus), CN-3 validated-edge wiring + sign flips + lane unification (Sonnet, dashboard), CN-4 bot seam (Sonnet, Mastermind repo). The Reversal Sleeve product build follows once CN-1's ledger conventions land (measurement before redesign, as with US).

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

- **2026-07-02 (F3 complete — #39 calibration-frame reconciliation)** — Both legs reconciled honestly on the PIT machinery from W1. **recession_risk / drawdown_risk (chose: RE-CALIBRATE on the live frame + composition):** re-ran the forward-drawdown band hit-rate on the leak-free PIT ('release') frame with the LIVE claims composition (`scripts/validate_drawdown_risk_pit.py` → `data/regime/drawdown_risk_pit.json`, trial-safe: Wilson CIs not Sharpe-deflation). The stale `~8%→26%→36%→38%` table (Sahm-era, revised frame, implicitly a point-to-point return) reproduced **neither** the live frame nor the max-drawdown definition its label claims. Re-issued monotone table (max-drawdown, 1993–2026, 95% Wilson): **base 19% · low 11% · elevated 28% · high 36% · extreme 49%** (PIT/'release'); latest-frame bands sit within CI (extreme 51%). Wired into `conditions.drawdown` (reads the artifact live, pinned fallback), the `drawdown_risk_high` alert, config + equity_alloc comments, QUANT_FACTOR_EXPANSION §6; stamped `stat_passport {basis:measured, frame:pit, labor_leg:claims, n, span}`. The 45%/8% number is display-only → landed directly. **business_cycle (chose: MOVE the live path onto the calibrated frame, lag_m=1):** live ran at lag_m=0 (leaked a month of look-ahead on monthly legs + a future-month-end artifact) while its 5.7m-lead/3-FP stats were calibrated at lag_m=1. Ran validate_business_cycle at BOTH: lag_m=1 → thr −1.25/3m, 5.7m mean/7.0m median, 3 FP (the shipped, honest); lag_m=0 re-fit → thr −1.5/1m, 7.0m/8.0m "lead" but that extra lead is the leak (fired on unpublished data). Chose lag_m=1 (removes the leak, matches the advertised stats, costs 1mo latency on monthly legs only — daily SPY/curve/HY legs unaffected). New config `live_lag_m:1`/`shadow_lag_m:0`; snapshot carries `lag_passport` + a MARKED shadow of the legacy lag-0 reading (phase flips contraction→recovery on the live store), surfaced on macro_signals; retire after one nightly cycle. `calibration_lag_m` stamped in the calibration JSON; grid budget registered (`business_cycle_recession_signal`, 45 configs). Tests: `tests/test_calibration_frame.py` (PIT as-of invariance + live-lag==calibrated-lag + shadow/passport + harness-bypass). 90 tests pass (82 relevant suites + 8 new), trial-registration lint green. **Flip criterion:** retire the lag-0 shadow + note the flip once one nightly cycle confirms the lag-1 phase clock is stable.

- **2026-07-02 (W5 complete — every workstream W0-W7 now has its core landed)** — Bot local merge (fix/w5-sizing-rebuild → checked-out branch, other session's files untouched; bot restarted 4th): **#24a** initial-size discounts now create a HARD cash reserve (renorm/water-fill only on deployable budget; byte-identical absent 'initial' names); **#24c** water-filling cap redistribution; **#24b** equicorrelation book-vol targeting SHADOW (armory-registered, arms at 20 turns + bounded adjustment; today's 39-name avg_corr-0.17 book correctly needs 0% de-gross, synthetic 6-name concentrated book de-grosses 44-62% — the 06-23 remedy proven); **#2-half** research gate rejection power proven (anchor+lens_delta separable, orthogonality corr −0.02 CI-tested, sized-but-lens-negative name REJECTED end-to-end, research_score → spine-compatible ledger for forward Brier); **#38** EV bandit (Thompson on posterior-mean return; hit-rate display-only) + autonomous book gets fused_risk in its brief by default + `gated:false` leaderboard label. 138 tests, zero new failures. **Final cleanup wave launched:** F1 (bot US-side staleness #9-residual), F2 (#45 hk_regime as-of + tz defaults, #37 masterminds honest banding), F3 (#39 recession/business-cycle calibration-frame reconciliation). Remaining after that: committee vendor diversity (#11 real fix — needs a user routing decision, e.g. SENTINEL→DeepSeek), the accrual dates, and the written flip criteria.

- **2026-07-02 (W6 follow-up — T3 provisional badge + opt-in veto hysteresis)** — macro#878: the K5 replay's recommended emit change shipped (see `research/PROVISIONAL_TIER_REPLAY.md` §Shipped follow-up). `confluence_tiers.cascade` now emits `provisional: true` on **T3 fresh fires only** (the tier above the flip criterion at 23.8% US / 15.1% CN; T1/T2 measured 5.3%/8.8%, unflagged), flowing through `signal_gate` verdict/`compact`/`buy_signal` into every board artifact; rendered as a small dashed "provisional — may repaint" pill with the measured stat in the tooltip on `_sig_badge` (all standout grids), the Top-setups strip, the discovery chip, and Buy Board 2.0 (ENTRY-OPEN T3 now flagged, not just SETTING-UP). Display-only — `is_buyable`/weights/ranking untouched. The not-topped veto hysteresis is wired config-gated: `VETO_HYSTERESIS_CONFIRM=2` debounces the cascade's daily veto stream (measured flicker 1.6%→0.0%, recall 97.7%); unset/1 = byte-identical single-bar incumbent (pinned by test). 8 new tests (`tests/test_provisional_badge.py`).

- **2026-07-02 (K-wave complete, 5/5 — Phase 3 substantially landed)** — **K1** macro#862 (validate-before-weight firewall): crowding trim was leaking 22.5pp of the US book to cash EVERY run → now fully deployed; dispersion dial clamped 1.0 across all 4 books (shadow value + passport kept); vol_shock dealer-gamma weight 1.0→0 while unscored + `gex_products_disagree` surfaced; board rank IC-weighted over positive-IC legs only (top-25 churns 32%; guard test: no mean_ic≤0 leg can rank); field-level reliability contract + CI guard (#20 #25 #29 #30 #46 closed). **K2** macro#855 (Outcome Spine): `engine/spine.py` live with 651 rows/531 graded (us_board IC +0.021 n=437, desks, altdata_conv honestly n=0); `engine/pooling.py` shrink-to-zero hierarchical pooling with trust regions — correctly REFUSED to arm (2/12 effective events; predicate: ≥12 + pooled-beats-equal held-out); alert severity IC-capped; convergence co-firing penalty; passport build ratchet (#13 #19 #23 #41 #42 closed). **K3** (bot, local): prediction ledger resolved 497 rows from 0 (survivor-frame stamped, PIT hook ready, loud liveness); veto seats get sign-inverted counterfactual credit (proven both directions) + attribution.persist first caller; D1/D2/D4 doctrine vetoes behind evidence auto-arm (FP≤35%/n≥20); heavyweight_outcomes wired, zombie panel.adjudicate deleted; armory report + `adversary_diversity: same-model` stamp (#2-half #8 #11-half #17 #31 closed). Bot restarted (3rd) — all active. **K4** macro#853 (determinism): temp=0/seed/content-hash cache/GDELT pre-snapshot on all 3 graded LLM paths; spvector veto wired-shadow to capitulation_score≥2 (#33 closed, #35 labeled). **K5** macro#872 (salvaged after session-limit interruption): provisional-basis replay — US repaint 8.1% (T1 5.3/T2 8.8/**T3 23.8** — flip criterion MET for T3 only → provisional badge recommended), no US edge sign-flip (provisional BETTER at 10/21d), CN 5d zero-baseline technicality = watch item; hysteresis kills veto flicker (0.0%) at 97.7% recall; FRESH_TICKS sweep honest null (incumbent stays, stamped); CN blend knobs ledger-immature (#22 #36 closed). **Remaining open:** W5 sizing rebuild (#24 #38 + #2's gate-orthogonality half), #9 US-side staleness, #37 #39, hk_regime as-of leak (#45 residual), committee vendor diversity (#11 real fix) — plus the time-blocked accruals and written flip criteria.

- **2026-07-02 (coordination)** — `CHINA_LEADERSHIP_PREEMPTIVE_FOR_FABLE.md` is being executed by ANOTHER Fable session on another account. This program must NOT execute it or touch its scope (china leadership/preemptive engines) without checking main for that session's landed work first; expect concurrent PRs from another account — rebase before merging, keep file ownership disjoint. (A stray untracked copy sits in Mastermind/vendor/macro_src/research/ — harmless, not canonical.) Also: P2-B′ macro#844 landed — 06-23 replay gate BLOCKED the MRS flip (fused gate misses the event: positioning legs only exist from 06-24, and flipping would LOOSEN 75% of history); shipped the structural layer instead (single versioned gross table max_gap 0.0, directives' first consumer, coherence assert catching a live banner-vs-gate residual, permanent replay regression test that signals when to re-litigate). Bot restarted on vendored #844 (regime_one visible; risk_prior + override ledger live). Tushare TRUE root cause fixed (macro#847): collectors were never in any collect lane (asia = china*/hk* prefix match) — ChinaTushareAdapter added, plane live-refreshed 2026-06-21 → 2026-07-02 (margin 1,980→4,372 rows), daily via asia lane from now on.

- **2026-07-02 (Phase 2 wave 1 complete + ops)** — **Ops:** Mastermind restarted (china_daily 13:30 / hk_daily 13:45 UTC confirmed in jobstore; stale Jun-20 dev instance on :8050 killed); TUSHARE_TOKEN verified live + set in Mastermind .env + repo secret + injected into asia-close/daily collect lanes (macro#825); asia-close dispatched to unfreeze the plane. **P2-A** macro#828: `regime_one.json` shadow artifact (tape/macro/forward decomposition, passports, versioned RISK_STATE_GROSS, freshness bitmask #32, `validate_regime_fwd.py` #16, base_effect revised=False on shadow path); **chaos test: simulated FRED outage flips legacy quad Q1→Q4 but regime_one vetoes (100% renorm share), freezes, publishes degraded, caps gross 0.90 — #3 structurally fixed in the canonical artifact.** **P2-B** macro#831 + charting-app 5038d07: `engine/canon.py` (netliq/credit_impulse_level·accel/vix_term, byte-matched migrations; forex_dollar TGA-drop confirmed real bug and fixed; sector beta shadow blend, XLC prior retired; playbook flip deferred #40); golden signal vectors exported; **Terminal stale fork fixed + golden_gate INVERTED — NVDA 106 moved dates→0, Moutai 108→0, Tencent 102→0; stale fork now FAILS, correct engine PASSES (#7, #12 closed). Terminal NOT yet deployed to VPS.** **P2-C** macro#834: `engine/grading.py` (next-bar, survivorship via as_of_members first consumer, delisted→loss, dual return basis); **headline −23.7→−15.5 claim SURVIVES honest re-grading and strengthens (−24.0→−14.5, 91%, n=219)** — bias lived only in the live marker logger, now aligned; trial ledger 0→34 declared budgets, `_mt_bump` ledger-sourced (floor 8), CI lint, spvector DSR stamped frozen-quote w/ expiry (#15, #21 closed). **Next: P2-B′ risk unification (launched) — RISK_STATE_GROSS single source, MRS retirement shadow A/B w/ 06-23 replay gate, bot consumes fused_risk + blocks on degraded.**

- **2026-07-01** — Audit + masterplan committed (macro#805). Phase 0 delegated: Agent A (Opus — #6 #27 #28 #44), Agent B (Sonnet — #26 #34 #42 #43), Agent C (Sonnet, charting-app — #18). Phase 1 foundation delegated: Agent D (Opus — W1a/b).
- **2026-07-01 (later)** — All four landed. **C**: charting-app `master` 508a6f3 — intel bridge contract (mapping table, staleness abstention, wired into refresh; 51/51 tests). **B**: macro#806 — #26 CN/HK/CA entry gate threaded, #34 shared blackout flag, #42 severity low, #43 delta-basis + ticker existence gate (109 tests). **D**: macro#807 — `engine/pit.py`, PIT-parameterized `build_features`, release-lag recorder, leakage tax live: **quad PIT-vs-latest agreement 84.2%** (2001: 57%, 2025: 63%, 2020: 78% — disagreement concentrates at inflections, inflation axis), flip-date drift median 0d (tape legs dominate flips), split-half ΔSharpe CI straddles 0 (edge not a revision artifact; no demotion). Blocker found: vintage store missing the official-inflation block (core CPI/PCE, PPI, ECI, claims) — backfill agent dispatched. **A**: macro#808 — #6 clean labels **demote all three BTC impulse act-tier legs** (d2 holdout lift 4.368→1.813 p 0.43; d3 2.677→1.111 p 0.46; u1 insufficient_n), #27 TSF availability-date stamping (+12-16d honest lag; credit-leg Sharpe ~unchanged), #28 netliq canonical 3-term (corr with −RRP 1.000→0.437), #44 alpha overlay true PIT (~114ms/basket). Chip spawned for 4 pre-existing test_regime_snap failures on main.
- **2026-07-01 (vintage backfill)** — macro#809: ALFRED vintages 15/26 → **26/26** (10,103 rows). Quad agreement unchanged at 84.2% with true CPI/PCE vintages → the Q1↔Q2 inflation-axis confusion is **market-leg hysteresis, not the vintage gap**. True lags measured: ECI ~120d (largest leak, prior massively optimistic), CPI 45d (prior ~11), core PCE 59d (prior ~28) — `DEFAULT_RELEASE_LAGS` needs these in W1c. **#16 unblocked**: base_effect can run `revised=False` on CPI (1997+), PCE (2000+), PPI (2014+).
- **2026-07-01 (US wave complete)** — US-2 macro#812: git-archaeology retro grading (buy-lane 65.7% vs SPY / 57.9% vs sector, n=437; board-order P@1 0.20 vs alpha-reordered 0.60 — top slots anti-selected; top-5 lift −13.7pts), MAE study: timing does NOT reduce drawdown → order by edge, gate by timing (anti-chase only); dispersion display-only. US-3 macro#814: shadow `us_standouts_v2.json` + `group_context.py` live — **0 of the live 34 buys survive the dual gate**; 10 entry_open names all from setups.json; flip criterion = v2 precision@k ≥ live. US-1 macro#815: display honesty shipped (score_edge/score_timing split, verdict-anchored bands, blocked-label downgrades, sector cap 19→5, entry_open_first demoted — REZI replaces ETN at #1, invariants added).
- **2026-07-01 (China reassessment)** — 10-agent workflow verified the China doc (all 8 root causes STAND, 15 corrections, 17 new problems) + resolved all §8 questions empirically: #791 ledger dead on arrival (wrong store group, n_graded=0 forever); board∩reversal-watch = 1/110, ∩low-vol = 0/110; fill haircut measured survivable (~1pp/entry, ~2-3pp hit); LHB/premium-block legs measured WRONG-SIGN as wired (+0.10 weight on a −1.43%/21d drain); deep-discount blocks +3.45%/21d t≈3.4 = best northbound replacement; risk_radar_intl = validated-but-unwired sleeve dial AND the repo's only closed learning loop; china_search retroactively deletes dropped names' history; W1 covers zero of the CN board path (washout flips 8.3%/day on bucket completeness); bot consumes the edge-less score as "best ideas" on 7/8 China turns. Delta report: `research/CHINA_ENGINE_REASSESSMENT.md`. §W6-CN added; CN-1..CN-4 delegated.
- **2026-07-02 (CN wave complete, 4/4)** — **CN-1** macro#820 (keystone): ledger store-group fixed 0/89→89/89 tickers resolving; grading conventions locked before first maturity (CSI300-relative, T+1 (H+L)/2 fill → true open as backfill lands, locked-limit excluded, pinned graded-from-fill, marker-date grading forbidden + leak test); Open column + backfill script; append-only PIT drips; partial-session refusal + CN_LANE=asia gate; track record rendered on china_stocks.html; first maturities ~2026-07-29. **CN-2** macro#821: `shadow_pit_china.py` leakage client live (plane tax 5.1%, bucket 8.3%/day, vintage 5.1%>0.4%); retroactive universe deletion killed (append-only + dropped.parquet); combine_first seams killed (overwrite_overlap); raw price plane collector (ICBC raw/adj divergence +36.8% @5y); tushare root cause = **no TUSHARE_TOKEN in CI** (plane dead 13d, asof-aware preference + health badge shipped); ST screen matched 0/1494 (Sina strips prefix) → re-sourced from tushare (512 ST names), fail-closed; mktcap 30.0亿 sentinel → None + tushare total_mv. **CN-3** macro#819: risk_radar_intl sleeve chip on all 5 pages (×0.90 caution live); LHB +0.10→−0.10 + block-premium demoted (measured drains); deep-discount blocks + inst-seat LHB probationary chips; #773 AI-semis confirmer wired (ON, +15.2% 4w); basket lane unified to asia; playbook monetary vote collapsed + symmetrized; crowding legs de-proxied. **CN-4** (Mastermind, local merge to feat/china-book): MCP copy honesty; china-anchored block-by-default freshness gate (verified: HK turn defers on stale board); data_through gating; turns moved 08:00→13:30/13:45 UTC; CHINA_FUNNEL_PROFILE=edge-led shadow profile + always-on same_tape_note. **USER ACTIONS PENDING:** (1) restart the Mastermind app to activate the new schedule + gate; (2) add TUSHARE_TOKEN to macro CI secrets to unfreeze the tushare plane. **CN-5** macro#823: Reversal Sleeve LIVE as shadow (site/cn_reversal_sleeve.html, unlinked): 291 members/12 sectors, EW, no-gate invariant enforced, sleeve x0.90 radar-sized, forward ledger seeded day-1 (CN-1 conventions); 24mo backcast +0.94%/mo Sharpe 0.88 labeled UPPER BOUND vs validated +0.56%/mo/0.58; promotion criteria: matured fill-realistic forward ledger beats baskets on CSI300-relative hit + Sharpe (Wilson lower bound) with no slippage widening (~2 months, >=4 graded rebalances).
- **2026-07-01 (US-stocks merge)** — Targeted US-stocks audit imported (`research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md`), merged as §W6-US with user's dual-gate + rotation-priority product spec. Delegated: US-1 (Sonnet — display honesty + degenerate-mechanism removal on live board), US-2 (Opus — board ledger + git-archaeology retro-grading + MAE/precision@k/dispersion studies), US-3 (Opus — shadow `us_standouts_v2` build: dual gates, two lanes, group_context rotation priority).
