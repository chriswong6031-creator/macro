# LIVE ENTRY RADAR — PR-0 FROZEN RESEARCH CONTRACT

**Program:** Live Entry Radar — real-time tactical entry intelligence for U.S. equities
**Route (future):** `entry_radar.html` · **Workstream:** `WS:LIVE-ENTRY-RADAR` · **Parent program:** `market-timing-intelligence` (`config/mastermind_programs.yml`)
**Authority:** operator/CEO commissioned research + build (execution handoff received 2026-08-13; operator design directive same day)
**Status of this document:** FROZEN at PR-0 merge. Post-freeze changes happen only as numbered, dated, append-only amendments in §18 — never in-place edits — and any amendment made after first replay results exist must state what results its author had seen.
**Freeze date:** 2026-08-13 (all pre-registered thresholds in §10–§11 were fixed before any replay, backtest, or live result of any Radar detector existed).

---

## §0. ACCEPTANCE GATES (program-level, binding on every later PR)

**Product gates** (from the commissioning handoff, condensed; each later PR names which it discharges):

- [ ] Radar exists separately from Prophet; Prophet's selection/gating behavior is byte-identical (P-1)
- [ ] Grey Dot exact identity confirmed AND parity-tested against Terminal before any G0 result is claimed (P-2)
- [ ] 1D live/provisional values visibly and structurally distinguishable from closed-bar values (P-3)
- [ ] Pre-candidates and candidates can appear, promote, invalidate, and expire intraday (P-4)
- [ ] Same ticker can occupy multiple detector lanes simultaneously (P-5)
- [ ] Every lobe nomination can force a ticker into the Probe Set; IPO/small caps not rejected for index non-membership (P-6)
- [ ] Every candidate states why it entered the universe and why it became a candidate; ranking provenance inspectable (P-7)
- [ ] Every reading carries freshness; stale data never masquerades as current (P-8; see stale-frame precedent PR #5555)
- [ ] Detector score and Priority/Opportunity score are separate objects (P-9)
- [ ] False starts remain recorded forever; no silent deletion of failed signals (P-10)
- [ ] Dark + light intentional; EN + ZH; mobile works; no auto-trading anywhere (P-11)

**Research gates:**

- [ ] Point-in-time universe and features wherever replay is claimed; survivorship limitations disclosed in every result doc (R-1)
- [ ] No completed 1D/4H/2D/3D bar leaks backward into an earlier observation; mutation tests prove it (R-2)
- [ ] Signal price = price observable at decision time; costs/slippage modeled for ranked outcomes (R-3)
- [ ] IPO cohort calibrated separately; cap/liquidity cohorts reported (R-4)
- [ ] G0 vs C1 vs C2 compared independently; depth vs turn separated (R-5)
- [ ] False-start definition frozen (§10) before the main comparison was read (R-6)
- [ ] Matched-control performance present in every comparison read (R-7)
- [ ] MFE and MAE present; ranking monotonicity reported (R-8)
- [ ] Look count / multiple-testing disclosure in every result doc; look ledger append-only (R-9)
- [ ] Live-forward ledger running before any claim of measured edge; "validated"/probability language only after Evaluation OS promotion (R-10)

**Sequencing gates:**

- [ ] G0-VIS: glyph identity confirmation (§3.3) closed before PR-2's parity freeze
- [ ] Parity fixtures green before any cross-repo G0 claim
- [ ] Look ledger exists before the first replay read (PR-5 entry criterion)

---

## §1. EXECUTIVE DECISION AND SEPARATION DOCTRINE

Build a **new, separate real-time U.S. tactical entry system**. Do **not** modify existing U.S. Prophet selection/gating logic anywhere in this program.

The system's job: **continuously search the U.S. equity market for stocks where a temporary washout or dislocation is creating unusually favorable entry asymmetry, then rank the opportunities by the quality of their forward upside/downside distribution.**

Three questions stay separate, permanently:

| Layer | Question |
|---|---|
| Prophet / Own-It | Is this an opportunity worthy of conviction? |
| Existing entry gauge (`engine/entry_signal.py`) | Has enough confluence arrived to make entry timing relatively safe? |
| **Live Entry Radar** | Is an unusually attractive early entry **forming right now**, before full confirmation? |

Radar deliberately trades confirmation for earlier timing, greater potential asymmetry, more false starts, and more reliance on operator judgment. If Radar proves incremental value, it may later become a nullable Prophet input or a new validated entry lane — a future promotion decision, not part of this program.

**Non-interference proof obligation:** every Radar PR that touches `engine/` must show `git diff --stat` clean on `engine/entry_signal.py`, `engine/prophet_*.py`, and the Prophet gate configuration; Radar imports from those modules are read-only library uses, never edits. (Sibling workstream `WS:PROPHET-US-ENTRY-TIMING` owns Prophet-side timing diagnosis; `owns_paths: engine/prophet_*.py` — Radar must never claim those paths.)

**Core trade archetype:** structural strength → temporary weakness → selling exhaustion → observable turn → renewed demand. *Buy weakness beginning to fail inside something worth owning.* The central object is **washout → turn**, never "oversold" as a state. The system does not call bottoms; it detects the earliest observable change from "selling is still winning" to "selling is no longer winning" inside names whose structure implies renewed demand could matter.

---

## §2. PRIOR ART AND KILL-REGISTRY COMPLIANCE

This program starts display-tier/accruing (free to build under house epistemics); the gauntlet applies at promotion. But it must be built citing what the house already killed, and every promotion attempt must confront these by name:

- **`DNR:KILL-WASHOUT-TURN`** — "Washout × turn (2W operator seed)" KILLED in entry-stack Amendment-3 (#1747).
  > PENDING(TRACK-B/E): exact killed construction, test, and ruling context (RUL-27..34); contract-level distinction statement will be completed here before freeze.
  Standing position: the kill closes the specific 2W construction tested inside the Prophet entry stack. Radar's detectors differ in timeframe (1D live / 4H / Terminal 3D×2D confluence), in role (standalone discovery + ranking product, not a Prophet gate input), and in evaluation (PSS §7-style timing ruler with matched controls). None of that excuses a future promotion from clearing the original kill's falsifier territory explicitly.
- **`DNR:KILL-PSS-F1-DOWNVOL`, `KILL-PSS-F2-OVERNIGHT`, `KILL-PSS-F3-RESIDUAL`, `KILL-PSS-F4-SEMIVAR`** — four standalone entry-*timing* families killed 2026-07 under the PSS §7 timing ruler. None are Radar detectors. Inherited obligations: (a) reuse that ruler's discipline (per-name-first aggregation, matched-construction placebos, incumbent benchmark) rather than invent a new one (§11); (b) semivariance asymmetry stays available as a *confluence descriptor* only, per its own kill row; (c) the incumbent benchmark those kills reference (Stoch-RSI cross at −2td) is Radar's natural "existing gauge" comparator.
- **`DNR:KILL-MCO-THRUST`** — breadth washout *bounce* legs rejected as radar legs (market-level). Radar is single-name; no breadth-thrust detector may enter the arena via this program.
- **Entry Stack expansion finding** — higher-timeframe StochRSI *depth* behind fires failed and raised stop burden; *turn/motion* features were the interesting ones. Frozen consequence: **2D/3D depth is context, never authority** in any Radar detector or score; turns are the object (§4).
  > PENDING(TRACK-B): doc path + exact quotes.
- **Adjacent implementation roots** (`market-timing-intelligence` program): `engine/ignition_radar.py`, `engine/setups.py`, `engine/stock_personality.py`.
  > PENDING(TRACK-B): what ignition_radar/setups detect today and the explicit boundary (overlap, reuse, or clear).
- **DRL (dislocation-recovery) program** — shipped 2026-08-10, prereg R4 registered.
  > PENDING(TRACK-E): crisp boundary statement (both touch "dislocation/recovery"; where they do not overlap) + its prereg format adopted as precedent.

---

## §3. CHAMPION G0 — TERMINAL GREY DOT (exact, not approximate)

**Identity hypothesis (to be confirmed, not assumed):** the operator's "grey dot" = Terminal's early anticipation dot in `charting-app/signal_layer/confluence_v2.py` — 3D StochRSI bullish cross from oversold AND 2D RSI-MACD histogram rising before the main cross, with point-in-time handling of 2D bar availability and a docstring claiming ~4.6 days of lead; the current emitter renders it as the amber EARLY marker and removes the old gray side-channel dot underneath.

### 3.1 Exact specification

> PENDING(TRACK-A): constant-by-constant spec — StochRSI implementation (RSI period/source, stoch window, K/D smoothing, NaN policy), 2D/3D bar construction and anchor, oversold definition, cross/turn definition, RSI-MACD histogram parameters and "rising" definition, known_at mapping rule — each with file:line receipts. This subsection becomes the locked spec text from which `spec_hash` is computed.

### 3.2 Parity strategy

> PENDING(TRACK-A recommendation; orchestrator decision recorded here): consume versioned Terminal artifact vs shared pure implementation vs Macro reproduction under locked spec + known-answer fixtures + `spec_hash` + parity tests. Whatever is chosen: **no silent drift** — two implementations may exist only under fixture-enforced equality, and the fixtures are committed known-answer cases extracted from Terminal data.

### 3.3 Glyph confirmation (gate G0-VIS)

Code-identity evidence this session, plus:
> PENDING(TRACK-A): emitter/glyph trace (marker shape/color, gray→amber history), fired-date list for NVDA/NFLX/TSLA 2025–2026 if cheaply computable.
Closure of G0-VIS = operator confirms the fired-date/glyph evidence matches the dots they have been trading off ("these are the dots I mean"). G0-VIS must close before PR-2 freezes the parity fixtures. This is the only gate in the program that requires operator input rather than code evidence.

### 3.4 C5 — Terminal Bottom Watch

Adopted as a research lane exactly as implemented in Terminal (deep-washout watch/display events, never scored entries).
> PENDING(TRACK-A): exact factors, thresholds, emission semantics.

---

## §4. CHALLENGER FAMILY — WASHOUT AS MEASUREMENT, TURN AS EVENT

A low oscillator is a **state**; the tradable object is the **transition out of it**. Every detector consumes the shared washout-episode feature vector (computed per episode, availability-stamped):

depth (min K, min D), floor-touch flag (min K ≤ 2), time from K=20 to minimum, velocity into washout, sessions below 20, failed-turn count while oversold, K−D relationship, first derivative of K during recovery, rebound velocity, RSI-MACD histogram level/slope/curvature, histogram local-trough location and age, price rebound from episode low in ATR units, volume/relative-volume response, and the structural context vector (§8).

**No detector may require a zero print.** A leader refusing to reach the floor ("partial washout": min K in (2, 20], short dwell, early turn) is a first-class cohort, potentially showing *more* relative strength — never penalized for insufficient depth.

Frozen arena (detector IDs are versioned; `spec_hash` per version; a spec change = new version = new detector for evaluation purposes):

| ID | Definition (frozen intent; exact constants locked in PR-2/PR-3 specs) |
|---|---|
| `G0_GREY_DOT@1` | Terminal implementation, exact (§3) |
| `C1_1D_LIVE_WASHOUT@1` | Pre-candidate arms when **1D LIVE** StochRSI K < 20 (provisional value; full intraday path recorded, including round trips like 35→8→0→24) |
| `C2_1D_TURN@1` | C1 state + registered turn evidence: small pre-declared variant family over {K slope > 0, K×D cross, higher oscillator low, histogram local trough with positive slope, positive histogram curvature, rebound ≥ 0.5×ATR from session/episode low}. Variants enumerated in the PR-3 spec and look-counted; no post-hoc variant additions |
| `C3_1D_4H_RECOVERY@1` | 1D washout state + **completed** 4H RSI-MACD histogram turn. A live/partial-4H form, if ever wanted, is a separate detector version, default off. Completed and incomplete 4H bars never mix inside one detector |
| `C4_MTF_TURN@1` | Multi-timeframe turn family: 1D turn while 2D/3D still washed; 1D+2D turns; 3D turn; all-timeframe recovery count. Depth enters as context features only, never as a requirement or monotone bonus |
| `C5_BOTTOM_WATCH@1` | Terminal bottom-watch port (§3.4) |
| `F1_FUSION` | **Not in V1.** Registered only after individual detector results exist; never champion by definition |

**Indicator-soup prohibition:** no new indicator families (Bollinger, VWAP votes, oscillators beyond the above) may join the arena until G0/C1/C2/C3/C5 have independent-information results, and then only via a registered amendment (§18).

A ticker can occupy several lanes simultaneously; lanes are never blended behind one number without per-lane provenance (§9).

---

## §5. PROVISIONAL-BAR AND POINT-IN-TIME LAW (non-negotiable)

Every input carries an availability state: `confirmed | provisional | stale | unavailable`. Every signal stores: `observed_at, market_session, source_bar_time, source_bar_known_at, bar_state, data_vintage`.

The engine distinguishes, as different inputs: **1D LIVE** (current partial daily bar), **1D CONFIRMED** (last completed daily), **4H LIVE** (only if a detector version explicitly enables it), **4H CONFIRMED**, **2D/3D** (mapped by real information-availability date, following Terminal's point-in-time discipline).

**Replay rule:** historical replay of any LIVE-state input requires intraday (minute) reconstruction of what the indicator showed at the decision timestamp. If minute data cannot support that for some period/name, that detector×period is **live-forward only** — never backfilled from EOD values.

**Leakage matrix** (every row must have a contamination test before PR-5's first read):

| Input | known_at rule | Replay source | Live source | Contamination test |
|---|---|---|---|---|
| 1D LIVE StochRSI/hist | continuously; value provisional until session close | minute aggs → provisional daily bar | live plane (§7) | EOD-mutation test: perturb the final close after decision timestamp → all features observed before it must be bit-identical |
| 1D CONFIRMED | next session open (conservative: close + T+0 evening bake time) | daily bars | nightly artifacts | same-day-use test: confirmed value never cited with `source_bar_time == observed_at` session |
| 4H CONFIRMED | at 4H bar close per session calendar | minute aggs aggregated | live plane | bar-boundary test around session irregularities |
| 2D/3D | completion date of the underlying aggregation window | daily bars + Terminal-parity mapping | same | PENDING(TRACK-A): exact mapping; test = no future completed bar mapped backward |
| Universe stats (ranks, RVOL, caps) | as-published artifact asof | archived artifacts / recomputation with PIT inputs | current artifacts | rank-vintage test: replay rank uses only data ≤ decision date |
| Lobe nominations | `source_asof` + `observed_at` at bus ingestion | archived producer artifacts | live bus | nomination postdate test: no nomination consumed before its producer artifact existed |
| Risk geometry (ATR, swing lows, spreads) | derived from bars ≤ observed_at | same | same | recompute-at-vintage test |

> PENDING(TRACK-B/D): replay-source column finalized after minute-history depth is confirmed.

---

## §6. UNIVERSE — DYNAMIC PROBE SET, NOT A CONSTANT

Funnel (all admissions carry machine-readable **admission reasons**; hotness admits, it never scores — §9):

- **Layer A — broad eligibility:** every supported tradable U.S. operating equity/ADR with sufficient data. Leveraged/inverse ETFs, ETNs, warrants/rights/units, and decaying derivative wrappers are excluded-or-separately-classified, never silently dropped. Small caps are not excluded for size.
- **Layer B — core:** S&P 500, major Nasdaq leaders, liquid large/mids, operator watchlists/holdings, names already under first-class single-stock coverage.
- **Layer C — dynamic hot:** admission on measured attention — dollar-volume rank, relative volume, share turnover, unusual realized range, large gap, short-term momentum, theme leadership, news/catalyst intensity, options activity. Thresholds are PR-1 budget knobs (measured against compute/data budget), not constitutional numbers.
- **Layer D — lobe nominations:** any ticker surfaced by an eligible single-name intelligence producer is auto-admitted with provenance, regardless of rank.

**Probe Set operating target:** ~500–1500 names, floating with measured budget. If 1,700 deserve probing, 1,700 are probed and the budget question is escalated, not silently truncated.

**IPO/young-history lane:** `history_age_sessions` on every name; young cohort (< 252 sessions) uses compatible short-history features, lower model certainty, liquidity/spread checks, halt/gap risk flags, and **separate calibration**. Young history is not low-quality data.

### 6.1 Nomination bus contract (frozen)

`mastermind.entry_probe_nomination.v1`: `ticker, source_id, source_family, reason_code, reason_text, observed_at, source_asof, source_rank, source_value, source_horizon, ttl_until, evidence_ref, data_quality`.

One ticker may carry many nominations; all provenance preserved. Producers group into source families (market/price, theme/sector, fund/ETF flow, smart money, options, off-exchange/dark-pool, news/catalyst, fundamental, special situation) so correlated producers cannot be double-counted: **nomination guarantees probing; predictive weight must be earned independently per family (§11). No "+5 points per page."** Nominations come from producer artifacts only — **never from scraping HTML pages.**

> PENDING(TRACK-C): producer census table (module, artifact, ticker field, cadence, asof semantics, family, shared-cause notes) + universe-machinery census + gaps.

---

## §7. LIVE ARCHITECTURE AND CADENCE (decision)

**Decision (criteria frozen now; mechanics ratified against Track D findings):**

- **Cadence:** ~5-minute decision refresh during RTH for the Probe Set. One-minute cadence is not pursued until research proves 5 minutes materially misses the turn — the signal is daily/4H/2D/3D; refreshing a daily oscillator 60× more often is not intelligence.
- **Plane:** VPS-primary timer (the `prophet-live.yml` pattern: VPS primary, GitHub backstop, live state artifact, event spool, **no intraday durable-ledger writes**, nightly reconciliation). GitHub cron is never the product cadence.
- **Market data:** reuse the estate's existing entitlement and integration plan (Massive: real-time trades/NBBO, second aggregates, snapshots, deep minute history). **No second market-data plane; no second stock WebSocket owner.** If the shared real-time plane is not production-ready, a bounded real-time REST/snapshot poller for the active Probe Set is acceptable only after the data lane demonstrates cadence/vendor constraints/load — and it must be built to be replaced by the shared plane.
- **Sessions:** actual NYSE calendar (holidays, early closes, DST, halts) — never wall-clock arithmetic. Extended-hours data never contaminates RTH-parity daily oscillators; an extended-hours detector would be a separate, explicitly-labeled construction.
- **Single-writer law:** the intraday lane publishes ephemeral state (probe universe, detector states, candidate states, ranking, live page payload, event spool). The nightly reconciler is the **only** writer of durable evidence (episodes, outcomes, evaluation). No git commits of state every 5 minutes; no second forward ledger; live and nightly evaluators never race on one durable store.
- **Stale behavior:** stale inputs demote to `STALE` presentation with age (§13); a kill switch exists from PR-4 onward; liveness is watchdogged (precedents: #5487 dead-man switch, #5571 rescue lane, #5555 stale-frame action safety).

> PENDING(TRACK-D): exact reuse points (VPS timer home, live artifact ladder, payload serving path for the page, minute-history depth for replay, WebSocket ownership answer, Breathing Platform status) + the ratified cheapest-correct-path.

---

## §8. STRUCTURE / LEADERSHIP MODEL (context vector, not a gate)

Structural feature vector (no binary gates):

- **Prior leadership:** 20/60/120-session returns; RS vs QQQ/SPY and vs sector; proximity to prior high; prior breakout behavior; trend persistence.
- **Current damage:** pullback from high (raw and ATR-normalized); 20/50/200DMA relationships; whether defined structure failed; gap/catalyst classification.
- **Relative resilience:** stock pullback vs sector pullback; stock washout vs market washout; oscillator reset with price structurally intact (the partial-washout-with-resilient-price case is explicitly valuable).

These features feed cohort assignment (§12), ranking research (§9), and the NVDA/NFLX/TSLA archetype separation: leader reset must be distinguishable from damaged-trend rebound even when the damaged name's oscillator looks prettier; gap/catalyst episodes are their own context, never pooled blindly.

**Rebound quality** (measured after arm; marginal contribution researched, never all required): first rebound from local low in ATR; rebound vs QQQ/sector; volume participation/RVOL; VWAP-reclaim or other already-sanctioned structure; repeated-failure vs clean-first-turn; histogram acceleration.

---

## §9. SCORING DOCTRINE — TWO SCORE TYPES, NO HAND-AUTHORED EDGE

- **Detector Score** (per detector, immediate): descriptive recipe-match strength. Versioned formula, published subcomponents. **Not a probability.**
- **Research Priority** (cross-detector ordering, PR-6): deterministic, transparent composite for operator use, labeled **ACCRUING / RESEARCH PRIORITY**. Subcomponents and provenance always inspectable ("TSLA 91" must decompose on click). No 30/20/20-style hand weights presented as edge.
- **Opportunity Score** (PR-7 only, after honest sample): outcome-calibrated estimates — P(positive at H), P(target before invalidation), E[return_H], E[MFE_H], E[MAE_H], tail MAE, E[cost] — ranked through an explicit utility: expected favorable outcome − downside burden − execution cost − uncertainty penalty. Coefficients set at PR-7 pre-registration, not retrofitted. **Uncertainty shrinkage mandatory** (empirical-Bayes toward cohort mean): 4 spectacular small-cap observations must not outrank 400 moderately strong ones on fake certainty.
- **Language law:** no user-facing "validated", no probabilities, no "92% winner" until Evaluation OS promotion gates clear. Hotness admits; it never adds bullish points (attention-chasing evidence cuts both ways). Lobe badges (OPTIONS / DARK POOL / ETF FLOW / THEME / SMART MONEY) display with provenance; five badges ≠ +25 — incremental value per family must be demonstrated conditional on the technical setup before any weight is granted.
- **Asymmetry definition:** attractive probability × magnitude of favorable excursion, constrained adverse excursion, nearby falsifiable invalidation, acceptable execution cost — measured on the §10 outcome set. **Never drawdown magnitude.** A −50% broken name is not asymmetric; a −12% leader accelerating off valid support may be.

---

## §10. FORWARD OUTCOMES, FALSE START, COSTS (pre-registered, frozen 2026-08-13)

**Outcome attachment per episode:** forward return; MFE; MAE; time-to-positive; time-to-MFE; target-before-invalidation probability; gap-through-invalidation frequency. Granularity: session closes always; intraday minute path where minute data exists (flagged per-episode).

**Risk geometry per candidate:** support/invalidation distance; ATR-normalized risk; prior swing low; nearby resistance; prior high; realistic spread/slippage.

**Horizons:** primary **H = 10 trading sessions**; secondary diagnostics {3, 5, 21}. All detectors graded at the same primary H for comparability; per-detector "intended horizon" may be registered additionally at PR-3 (before replay).

**Reference units:** signal price P0 = last trade observable at decision timestamp; A0 = ATR(14, Wilder) on confirmed daily bars as of the prior close.

**False start (frozen):** an episode that reached CANDIDATE is a false start iff, within H=10 sessions of `candidate_at`:
`MAE ≥ 1.25×A0 before MFE ≥ 1.00×A0`, **or** the 1D confirmed StochRSI re-enters K < 20 with a price low below the episode's washout low.
Reported: false-start rate; median MAE on false starts; time-to-failure. A 27-cell sensitivity grid {favorable 0.75/1.00/1.50×A0} × {adverse 1.00/1.25/1.50×A0} × {H 5/10/15} is declared now as diagnostic-only and pre-counted in the look ledger.

**Episode hygiene (frozen):** one live episode per (ticker, detector_id); episodes end only via INVALIDATED / EXPIRED / RESOLVED and are never deleted. Re-arm eligibility after an episode ends: 1D confirmed K > 50 for 2 consecutive sessions, or 15 sessions elapsed, whichever first. ARMED/TURNING without candidate-promotion expires after 15 sessions. CANDIDATE resolves at H.

**Costs (frozen for the primary read):** per-side cost = max(measured median half-spread at signal timestamp when NBBO is available, liquidity-tier floor); tier floors 5 bps (median daily dollar volume ≥ $50M), 15 bps ($5–50M), 40 bps (< $5M); round-trip applied to net outcome metrics. Implementation mechanics (spread measurement window etc.) are pre-registered in PR-5 **before** any outcome is read; deviations logged PSS-style (pre-outcome, in the prereg commit).

---

## §11. COMPARISON DESIGN — CONTROLS, RANKING VALIDATION, OVERFITTING

**Ruler reuse:** the evaluation reuses the Evaluation OS (registration, claim tiers, append-only assertions, own-ruler grading) and the PSS §7 timing-ruler discipline (per-name-first aggregation, matched-construction placebos, incumbent benchmarking) rather than inventing a new doctrine.
> PENDING(TRACK-E): exact registration format + ruler deltas declared.

**"The stock went up" is not edge.** Every candidate event gets matched controls drawn from probe-set members that did **not** fire that detector within ±5 sessions, matched on: session date; sector; market-cap bucket (>$200B / $10–200B / $2–10B / <$2B); dollar-volume decile; trailing-60d return quintile; realized-20d-vol quintile; hotness tier (admitted-not-fired). Primary read = excess vs control mean, per-name-first. The matching variable set is frozen; mechanical details (k, distance metric) pre-register in PR-5 before outcomes are read.

**Primary registered questions (the confirmatory family, FDR-controlled at BH q=0.10; everything else is exploratory and labeled so):**
1. Do G0 candidates outperform matched controls at H=10 (net of §10 costs)?
2. Does C2 (turn) beat C1 (washout state alone)?
3. Does C3 (4H recovery) beat C2 on false-start rate without giving up excess?
4. Do lobe-enlisted G0 candidates beat G0-alone candidates?
5. Does G0 beat the existing entry gauge (incumbent Stoch-RSI cross benchmark) on earliness at equal-or-better false-start burden?

**Ranking validation (the product is a ranking engine):** top-5/top-10/top-decile outcomes; score-decile monotonicity; rank IC where appropriate; top-k MFE/MAE and expected utility; ranking stability; false-start rate by score bucket. If score 90 performs like score 40, the score is decoration and PR-7 does not ship.

**Overfitting controls:** append-only **look ledger** (every parameterized family enumerated with cell counts before running; every executed look recorded); pre-registered comparison families above; walk-forward for anything fitted; **untouched holdout** = the most recent 6 months of replayable history at first replay, plus everything after the live-forward start; kill-registry discipline for dead constructions; prospective champion/challenger comparison is the decisive evidence. No 700-combination sweeps publishing the prettiest curve.

**Evidence ladder:** register → historical replay (PIT) → walk-forward → shadow live (every candidate recorded before outcome) → live-forward (decisive; required for promotion per house law).

---

## §12. COHORTS (same UI, separate calibration)

Minimum cohort set: leader reset; partial/shallow washout; full daily washout; deep multi-timeframe washout; gap/catalyst repair; damaged-trend rebound; IPO/young; small-cap/high-vol momentum. Cohort assignment from §4/§8 features. Cohorts share the interface, never blindly share calibration. Regime tagging (market-level washout vs quiet tape) recorded on every episode for later conditioning.

---

## §13. LIFECYCLE ≠ PRIORITY, AND THE EPISODE CONTRACT

Machine lifecycle per (ticker, detector): `PROBING → ARMED → TURNING → CANDIDATE → INVALIDATED | EXPIRED | RESOLVED` (append/history-preserving; user-facing simplification: Probing / Pre-candidate / Candidate). `detector_state`, `priority_score`, and `manual_state` are independent dimensions — a priority move from 91 to 63 changes no lifecycle fact.

**Episode contract (frozen):** `mastermind.live_entry_episode.v1`: `episode_id, ticker, detector_id, detector_version, detector_spec_hash, state, first_armed_at, candidate_at, last_observed_at, market_session, bar_availability, feature_snapshot, universe_admission, lobe_nominations, price_at_signal, risk_geometry, detector_score, research_priority, opportunity_score, data_quality, freshness, evidence_refs` — plus the §5 availability block on every stored reading. A candidate leaving today's board still exists in the ledger forever.

**Manual disposition (V1 or immediately after):** `Watch / Pass / Took / Rejected` + short reason tags (broken structure, earnings risk, too extended, great leader, bad liquidity, theme weak), timestamped. Not trained on in V1; first used to answer "what does the operator see that the model misses?"

---

## §14. UI DIRECTIVE (operator, 2026-08-13) AND PAGE CONTRACT

**Operator directive (supersedes the handoff's softer §33 language):** *take yesterday's new Prophet Board as the direct design reference — Live Entry Radar should look like a sister product built from that exact card/layout language, with only the information architecture changed.*

Frozen consequences for PR-8/PR-9:

- **Reference artifacts:** `templates/_prophet_card.html.j2` + `templates/_prophet_receipts.html.j2` and the Prophet Board reference-integrity evidence chain (`research/reference_integrity/prophet-board-5514-*`; R3 verdict REVISE, R4 closure PR #5560). PR-8 pins against the **then-current R4-resolved** reference — sister product in that exact card/layout language; IA changes only; known R3/R4 defects are not inherited; the RIG process runs on the Radar reference before migration.
- **Not inherited:** Prophet's seven-cell plan lifecycle and Prophet product semantics. Same design language; different information model.
- **Page hierarchy:** header (LIVE ENTRY RADAR; "Early asymmetric entry opportunities across the U.S. market."; Probe Set count / Pre-candidates / Candidates / source freshness / session state; no prose wall). Lanes: Best · Grey Dot · 1D Washout · 1D Turn · Deep Washout · Intelligence · All — detectors visually comparable, never blended behind one score.
- **Card anatomy (glance tier):** ticker/name; live price/change; Priority N; lifecycle badge; detector lane chips; cohort line; component states (1D Stoch / MACD-RSI / Structure / Lobe evidence); zone + invalidation footer; freshness stamp with bar state (`5m ago · 1D LIVE`).
- **Expanded drawer answers, in order:** why is it here (admission); why now (detector evidence); what is recovering (oscillator/momentum); still structurally strong? (context); what makes it asymmetric (risk geometry + conditional history); what else sees it (lobes); how trustworthy is this number (sample support, calibration status, freshness); where did it fire (mini chart: arm, trough, turn, promotion).
- **Provisional visual language:** `1D LIVE · provisional` never masquerades as `Daily confirmed`; stale readings demote visibly (`STALE · last usable reading 14m ago`) and never retain a green candidate look (stale-frame law, #5555 precedent).
- **Why-now copy is mechanical** ("Daily washout is reversing; 4H momentum turned higher"), never promotional ("huge upside", "92% likely", "AI says buy"). Falsifier/refutation vocabulary never front-facing (house law); glance tier uses plain-word stance within the design-system word budgets; EN + ZH first-class; dark + light intentional; mobile works.
- **Required PR-8 crops:** desktop dark/light EN, desktop dark/light ZH, mobile dark EN/ZH, no-candidates, stale, partial-data, many-candidates, multi-detector ticker, lobe-only probe, IPO candidate, anonymous/premium state if applicable — committed under `mockups/refs/entry_radar/`.

---

## §15. PR SEQUENCE (build order is law; each PR names its §0 gates)

| PR | Scope | Not done unless |
|---|---|---|
| **PR-0** | This contract + Track A–E censuses + workstream records. No production behavior | All eleven PR-0 deliverables present; kill-registry compliance section complete; PENDING slots resolved or explicitly gated (only G0-VIS may remain open) |
| **PR-1** | Probe universe + enlistment bus (broad eligibility, hot universe, core, lobe nominations, IPO handling, dedupe/provenance, active Probe Set) | A lobe-nominated small cap outside the hot universe appears in the Probe Set at the next eligible refresh with source evidence intact |
| **PR-2** | Detector framework + G0 exact (interface, independent detector state, Grey Dot implementation/adapter, parity tests, detector event schema). No score fusion | Parity fixtures green; G0-VIS closed; `spec_hash` stable; zero diffs on Prophet paths |
| **PR-3** | 1D/4H challenger family (live provisional reconstruction, confirmed versions, turn features, 4H variant, MTF context, strict availability timestamps) | EOD-mutation test proves a final close cannot leak into an earlier intraday observation; every §5 matrix row for used inputs has its test |
| **PR-4** | Live evaluator on the existing VPS plane (RTH evaluator, state transitions, ephemeral payload, event spool, stale behavior, kill switch, backstop if appropriate). No automatic trading | 5-min cadence measured across a full RTH session; single-writer law intact; stale demotion observed |
| **PR-5** | Forward evidence + replay (nightly reconciliation, immutable event history, outcomes, MFE/MAE, false starts, matched controls, detector comparisons, cohort cuts) — Evaluation OS conventions, no bespoke ledger | Look ledger operating; §11 registration filed before first read; holdout untouched |
| **PR-6** | Deterministic Research Priority for operator use, marked ACCRUING | Provenance decomposition on click; no probability language |
| **PR-7** | Outcome-calibrated Opportunity model (only after honest sample) | Calibration + uncertainty + top-k evidence + monotonicity report + champion/challenger results; promotion language only per house law |
| **PR-8** | UI reference + RIG for `entry_radar.html` per §14 | All §14 crops; independent product + visual critique run |
| **PR-9** | Production UI + live verification during an RTH session | Source→evaluator→payload→page latency measured; promotion/invalidation/stale observed live |

Backend does not wait for design; PR-1..PR-5 proceed while the Prophet Board R4 cycle resolves.

---

## §16. PATH / COLLISION PLAN

**Radar owns (new paths only):** `engine/entry_radar/**`, `scripts/entry_radar_*.py`, `templates/entry_radar.html.j2`, `site/entry_radar.html`, `data/entry_radar/**` (durable, nightly-written), live ephemeral state under the existing live-artifact ladder (exact home per Track D), `research/LIVE_ENTRY_RADAR_*.md`, `research/live_entry_radar/**`, `mockups/refs/entry_radar/**`.

**Radar never touches:** `engine/entry_signal.py`, `engine/prophet_*.py` (WS:PROPHET-US-ENTRY-TIMING territory), Prophet templates/payloads (read-only design reference), Terminal repo internals (parity via artifact/fixtures only), Mastermind control plane.

Verified this session: no open PR, no worktree, no tracked file, and no Agent OS workstream claims any of the owned paths (collision check 2026-08-13: `git worktree list`, open-PR sweep, `git ls-files`, `agentos/workstreams/` grep).

**Do-not-build list (binding):** no StochRSI-only buy engine; no Prophet gate changes; no deepest-drawdown ranking; no zero-print requirement; no depth-as-positive assumption; no hotness-as-bullish; no per-page mention points; no HTML scraping for nominations; no mixed StochRSI implementations without parity; no EOD-faked intraday history; no GitHub-cron product cadence; no second WebSocket owner; no second durable evaluation ledger; no arbitrary 100-point "AI score" sold as edge; no silent signal deletion; no auto-trading; no full-3D-confirmation-everywhere rebuild of the problem this program exists to solve.

---

## §17. SUCCESS SHAPE (operating definition)

At 11:35 ET the operator opens Live Entry Radar: ~900 probed, ~30 in washout, ~11 pre-candidates, ~5 turning; the board ranks them with detector chips, cohort lines, lobe badges, zone/invalidation, freshness (`1D LIVE · 5m`); clicking a name yields the mechanical why-now trail (fired 10:55; K bottomed 6.3 → 18.7; histogram trough + three rising observations; +1.1 ATR off the session low; 60d RS high; two independent lobes; reading provisional; sample accruing). The operator decides: buy, watch, or ignore. That is the product.

---

## §18. AMENDMENTS (append-only)

*(none yet)*
