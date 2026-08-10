# Transmission Intelligence ACTIVATION — the learning loop, the quiet half, and the last mile (by Fable)

**Date:** 2026-08-05 · **Status:** CHARTER + W-A SHIPPED IN THIS PR · **Parent:**
`TRANSMISSION_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (TXI — all its rulings inherited),
`NEURAL_WEB_MASTERPLAN_BY_FABLE.md` (constitution A0–A7),
`PROPHET_US_MISSED_IGNITIONS_MASTERPLAN_BY_FABLE.md` (the same failure class, sector grain, same day).

**Trigger:** operator escalation 2026-08-05 — oil cratered intraday, yields fell with
breakevens, DFII10 printed its first weekly down-tick from a 2.48 spike ("real rates may
have peaked → risk-on, precious metals, perhaps crypto"), and the operator asked why a
system holding all of this data cannot recognize it, act on it, learn from history, know
its own accuracy, alert on triggers/detriggers, and feed the read to Prophet / macro /
commodity / BTC / sector surfaces. Verbatim standard: *"it needs to understand the whole
step by step process of how things work … the accuracy rate, what could lead things to
change, and when things do change how does it detrigger."*

---

## §0 ACCEPTANCE GATES (inline in every build prompt spawned from this plan)

- **G0.1 (tier law).** Everything here ships `display`/`context` tier. No chain output
  ranks, gates, sizes, or escalates anything (DNR row 45, TXI Article 1/2). Authority
  for any single chain comes only through `engine/promotion_gate.py` + its own prereg,
  entering as a CONFLUENCE input, never standalone.
- **G0.2 (case receipts).** Every wave reproduces the 2026-08-05 rates case from shipped
  artifacts in its PR body: the three W-A chains' states, and after W-B their printed
  base rates.
- **G0.3 (ledger law).** `data/transmission/chain_episodes.jsonl` stays nightly-advanced
  only. The W-B miner writes calibration artifacts (R2/background lanes), never ledger
  rows; backfilled history is stored SEPARATELY from forward accrual with an era stamp
  (#4579 pattern) — a mined episode may never masquerade as a forward-graded one.
- **G0.4 (honest nulls).** Hypothesis-tier chains print "untested"; mined base rates
  print with n and regime-cell coverage; a hop with no historical activations prints
  that. RIC's standing null is quoted wherever rates context appears on a scored
  surface's page: repricing flags RISK/context, not return.
- **G0.5 (bilingual + design law).** All user-facing strings EN/zh; glance-tier word
  budgets; falsifier/refutation vocabulary never front-facing (operator 2026-07-27) —
  chains surface as "watching / propagating / expressed / no longer active", with
  "changes this read: <condition>" phrasing; DESIGN_DOCTRINE + frontend-design skill
  before any surface work; no new page, no third header family.
- **G0.6 (era honesty).** The W-A library addition is an era event for the episodes
  ledger (new chain ids accrue from 2026-08-05); the W-B calibration backfill stamps its
  own era break. Pre-activation emptiness may not be cited as a null.

## §1 The ask, adjudicated honestly

"Upgrade the Neural Web into a true superintelligence" decomposes into six concrete
capabilities. Five already exist in this estate — scattered, partially dark, or pointed
one direction. One (the historical learning loop for transmission chains) was chartered
thirteen days ago and never built. Nothing needed is fundamentally new; everything
needed is activation, completion, and assembly:

| Operator ask | Estate today (receipts) | Gap |
|---|---|---|
| "understand the step-by-step process / logical pathways" | TXI chain library: versioned YAML, observable nodes, staged hops, mechanism prose, falsifiers, blast screens (`knowledge/transmission/`, compiler `engine/transmission_chains.py`, state machine live — dollar chain ran `arming→propagating→expressed` 07-31→08-03) | library had 4 chains, ALL tightening-direction — the easing/risk-on half did not exist (§2.1) |
| "learn from historical examples of how things unfolded" | the miner ITSELF is built and wired (`engine/transmission_calibration.py`, weekly.yml) — plus the wider substrate: `brain_analogues.py` (10-dim retrieval to 1927), HAR cycle analogs, Oracle episode atlas, 34-ledger grading-closure registry, trial ledger (1,319 rows), `promotion_gate.py` | **the miner had never once run to completion** — its home weekly lane cancelled; every hop read `base_rate: null` until this PR ran it (§2.2, W-B) |
| "know the accuracy rate" | qledger Wilson CIs, track_scoring three rules, per-desk hit rates, kernel shrunken posteriors | chains carry no measured rates; `chain_episodes.jsonl` is not even DECLARED in `data/governance/grading_closure.json` (34 ledgers, zero transmission rows) |
| "alerted when triggers occur / how does it detrigger" | reflex registry + alert_triage push spine LIVE (NW W6a/b); falsifier tripwires with sticky FIRED states + Telegram dispatch (`falsifier_tripwires.py`, 24 entries); chain state machine has `failed`/`expired` detrigger states with structured falsifier checks | chain transitions are not registered reflexes; no push, no operator-brief line, no surface chip on arm/express/fail (§2.3) |
| "record learnings into a database" | the chain library IS the knowledge store (TXI-R10: versioned, PR-reviewed, kills move to `killed/`); calibration artifacts; CXI indexes rulings/docs | calibration store empty; ObsidianBrain is a VIEW (CXI-R12 forbids a second hand-maintained KB — nothing new needed) |
| "find its own truths systematically" | CHF brainstorm loop LIVE + autonomous (`auto_loop: true`, operator OAuth); TXI W5 proposal lane SHIPPED; cortex hypothesis metabolism (3/week, anti-mining); metabolism build loop (hourly, two-key adjudication) | TXI proposal sub-flag ships OFF by design (`config/transmission_proposals.yml: enabled=false`) — arming it is a one-line operator PR (§6 D2) |

**The honest reframe (TXI §1 stands):** no system becomes "superintelligent." What is
buildable — and is the actual moat — is the compounding, self-auditing causal-context
organ: chains proposed cheaply, killed honestly, survivors retained with calibrated,
regime-conditional evidence nobody else maintains. The house already ruled this; this
plan finishes building it and wires it to the surfaces the operator reads.

**What this plan will NOT promise (standing law, receipts on file):**
- No scored rates signal. RIC measured it: every rate/inflation driver's OOS-R² for
  forward return is negative — *"repricing flags risk, not return."* Chains narrate
  state and print conditional history; they do not predict returns.
- No LLM-originated signals, scores, or escalations (A7; six clamps in code).
- No fused composite (DNR row 45), no new NW lobe (two-lobe cap; this is a program),
  no full-graph causal learners (CHF-R14, Phase-3 clock 2027-01-15), no second brain,
  no parallel knowledge base (CXI-R12).

## §2 Ground truth — the two structural holes and the unfinished mile (audit receipts, 2026-08-05)

The Missed Ignitions postmortem (same day, sector grain) names the house failure class:
**assembly, not detection** — five postmortems in six weeks all reduce to "the engines
saw it; nothing the operator looks at said so." At macro grain the same class shows up
as three specific holes:

**2.1 — The library only knew one direction.** All 4 seed chains encode tightening
(oil SHOCK→derate, dollar SPIKE, credit WIDEN, vol EXPANSION). On 2026-08-05's tape —
oil cratering, breakevens falling, real 10y first down-tick from p99 — the oil chain sat
correctly `dormant` and nothing could arm, because the easing direction was never
authored. The `one-directional-guard-leaves-the-quiet-half-open` trap, at the knowledge
grain. Meanwhile the rate engine's own hero line could only say "headwind building —
watch": it has LEVEL and DIRECTION grammar (`real_10y_pctile: 0.99, regime:
restrictive, direction: rising`) but no PEAK/TURN grammar. The system tracks pressure
building and is mute on pressure releasing.

**2.2 — The learning loop was BUILT and has never once run to completion.** TXI W3
(episode miner + regime-conditional hop calibration, `engine/transmission_calibration.py`)
shipped 2026-07-25 (#3536, episode-counting fix #3557), wired into weekly.yml, with the
tracker's merge path (`transmission_chains.py:1199 _merge_calibration`) ready to fill
`base_rate` and promote the display tier the moment `chain_calibration.json` exists.
Receipts of darkness: that artifact has NO git history anywhere; the only weekly run
since the miner merged (08-01) was CANCELLED — 3 of the last 6 weeklies cancelled
(the ~15%-cron-delivery class, known); so every hop in `chain_state.json` reads
`base_rate: null` and every chain sits at `tier: hypothesis` thirteen days after the
machinery to change that was finished. `chain_episodes.jsonl` is also absent from the
grading-closure registry (34 ledgers declared, zero transmission) and TXI-R4's
Brier-tracking of forward episodes exists in no module — the ledger is a diary, not a
graded record. The substrate was never the problem (DFII10/T10YIE/DGS10/DCOILWTICO in
`data/fred/` to 2003, oil to 1986; `regime_history.parquet` to 1927).

**2.3 — The last mile is unwired.** `chain_state.json` reaches world_state, mastermind
chat context, portfolio_ctx, and the transmission.html Cascade Monitor — and stops.
Nothing on macro.html's glance tier, no Prophet context chip, no sector-board dual-read
line, no commodity/BTC surface, no reflex/push on a transition, no operator-brief line.
An `expressed` verdict on the dollar chain (08-03) was visible only to someone opening
transmission.html or asking the chat.

## §3 Rulings (TXA-R1..R9; TXI-R1..R10 inherited unchanged)

- **TXA-R1 (two-sided library law).** Every transmission chain declares its inverse:
  either the inverse chain exists in the library, or the chain carries an explicit
  `inverse_of: none — <reason>` disclosure in provenance. A CI check (W-C) enumerates
  pairs and fails on an undeclared quiet half. Rationale: §2.1; the trap class is
  measured and recurrent.
- **TXA-R2 (turn grammar).** Extreme-state chains arm on the EXTREME (percentile +
  regime from the owning engine's published state, per TXI-R8) and stage the TURN as a
  raw-series hop confirm (the state adapters' windowed direction keys certify turns
  last, by construction — documented in each chain's validator_note). The peak is never
  an LLM call and never a level threshold alone.
- **TXA-R3 (chains join the grading commons).** `chain_episodes.jsonl` gets a grader
  (W-B): terminal states graded (expressed → did the terminal cohort move within the
  declared windows; failed/expired → recorded as the falsifier/timeout outcome), rows
  federate into the NW spine via an adapter (`ledger='transmission_chains'`), and the
  ledger is DECLARED in `data/governance/grading_closure.json`. An ungraded forward
  ledger is a diary, not a learning loop.
- **TXA-R4 (miner idiom).** The W-B episode miner follows the shipped analog-engine
  idioms: frozen, pre-registered thresholds (the chains' own YAML node tests ARE the
  detection rules — no fitting at mine time), walk-forward stamping only, era-capped
  episode lists, per-regime-cell conditionals with honest n, nulls printed. Heavy
  compute off the render path (background lane, artifacts to R2 if heavy); the nightly
  only reads the calibration file.
- **TXA-R5 (calibration display form).** A calibrated hop prints, everywhere it
  surfaces: `P(next hop within lag | this hop, regime cell)` with n, the marginal
  (all-regime) rate beside the conditional, and the coverage caveat when a cell is
  thin. Tier ladder: `hypothesis` (untested) → `probe` (≥1 quarter forward episodes,
  TXI tier law) → `calibrated` (gauntlet). Mined-history rates NEVER advance tier by
  themselves (G0.3/G0.6): tiers advance on FORWARD evidence.
- **TXA-R6 (assembly rule).** Chain states join decision surfaces as CONTEXT CHIPS in
  watch vocabulary — never a lane re-ordering, never a score input, never a gate. Where
  a chain state and a surface's own read disagree, BOTH print (the Missed-Ignitions
  dual-read law, P3). Chip copy budget: ≤9 words EN glance + hover receipt (Tier-2).
- **TXA-R7 (alerting).** Chain transitions register in `config/reflexes.yml` and push
  through `alert_triage` ops lanes with priority floors + dedup (the shipped W6b
  spine). Push tiers: `expressed`/`failed` = ops-priority; `arming` = daily-brief line
  only (no push — arming is common, expression is rare). Detrigger pushes are the SAME
  priority as trigger pushes: a read that quietly stops being true is the operator's
  named failure mode.
- **TXA-R8 (proposal lane arming is an operator decision).** The self-extending
  library (CHF brainstorm → chain proposals → auto-compile → auto-backtest) is built
  and OFF (`config/transmission_proposals.yml: enabled=false`, sole remaining lock
  given CHF `auto_loop: true`). This plan RECOMMENDS arming (§6 D2) and does not arm.
- **TXA-R9 (scope fence).** This program composes existing organs (TXI's charter
  posture). It builds no new detector families beyond chain YAML + the miner + chips +
  reflex rows. Cycle tripwires (`falsifier_tripwires.py`) remain the per-claim kill
  system; chains remain the staged-cascade system; neither absorbs the other. Sector/
  name-grain assembly belongs to Missed Ignitions (shares no file with this plan).

## §4 The program

### W-A — The easing library seed (SHIPPED IN THIS PR; fable main loop — knowledge judgment work)

Three chains authored, validated strict, dry-run against live artifacts:

| Chain | Nodes | State on tonight's store |
|---|---|---|
| `oil_slide_disinflation_duration_rerate` | oil slide (20d −12% ∨ 60d −18%, MA50 down) → T10YIE −12bp/22td → DFII10 −12bp/22td → QQQ/SPY RS>0 | **ARMING** (oil 60d −19.9%) |
| `real_rate_peak_gold_rerate` | real 10y ≥p90 ∧ restrictive → DFII10 −12bp/22td → gold +4%/22td | **ARMING** (pctile 0.99; watching the rolldown) |
| `real_rate_peak_crypto_rerate` | same trigger → BTC +10%/22td (separate terminal = separate base rate; thin 2-episode provenance printed as thin) | **ARMING** |

Design receipts: thresholds measured on the stores before authoring (extreme+rolldown
joint = 4.7% of days since 2003, 275 days ≈ the 2006/2008/2011-12/2018-19/2022-24
peaks; oil slide legs 8.6%/9.3% of days since 1986). The demand-crash discriminator
(2008/2020 must NOT read as a disinflation glut) is a structured HYG/LQD falsifier, not
prose. The crypto leg is quarantined into its own chain so its weak evidence base can
die alone. All hypothesis tier, display only. The operator's 2026-08-05 thesis is now
engine state that tonight's nightly begins to stage, confirm, falsify, or expire.

### W-B — The learning loop lit and finished (part SHIPPED IN THIS PR; remainder builder/opus)

**Shipped in this PR (first light):** state-node proxies for the peak chains'
`real_rate_extreme` trigger added to `engine/transmission_calibration.py` (faithful by
construction: the live test IS the 1260d DFII10 percentile the engine computes;
provenance comment in-module), the miner RUN for the first time in its existence, and
`data/transmission/chain_calibration.json` committed — 7 chains, first measured base
rates in the system's history, mined spans landing exactly on the named historical
peaks (extreme→rolldown span 2008-10-08→2025-06-13, n=33). Tonight's nightly tracker
merges these into `chain_state.json` via the already-shipped `_merge_calibration`. The
era-pinned smoke test (`base_rates is None` forever) healed to era-honest form.

**Remaining (builder/opus):**
1. **Grader** (`scripts/grade_transmission_chains.py`, nightly after the tracker):
   grades matured episodes (expressed → terminal-cohort outcome at +21/+63d; failed/
   expired recorded), Brier-tracks per TXI-R4 (currently in no module), appends a
   grades sidecar, federates into the NW spine (`ledger='transmission_chains'`), and
   DECLARES the ledger in `data/governance/grading_closure.json` (TXA-R3).
2. **Unconditional baseline column**: beside every hop's P(confirm | upstream, regime)
   print the same event's unconditional base rate on the full history, so a generous
   lag window can never dress an easy event as an edge (each chain's `null_model`
   made visible; the gold chain's own cohort event-study already shows the honest
   anchor — unconditional forward gold excess at terminal firings is ~0).
3. **Weekly-lane reliability**: the calibration step's home lane cancelled 3 of its
   last 6 runs — diagnose the cancellation class (concurrency supersession vs cron
   delivery) and either harden the lane or move the step to a surviving one; a
   learning loop that runs 50% of Sundays is not a loop (G0.2 receipt: two
   consecutive weekly artifacts with advancing asof).
   Acceptance: era separation pinned by test (a mined row can never enter the forward
   grade path); a hop with zero activations prints "no historical activations".

### W-C — Inverse completion + seed library v1 (builder/opus for CI check; fable for chain authorship)

The two-sided law made mechanical: CI check enumerating chains without a declared
inverse (TXA-R1). Author the priority inverses/pairs from the TXI §7 seed list, easing
side first: `dollar_rolldown_em_multinational_tailwind`, `credit_spread_compression_
refi_relief`, `vol_compression_rerisking`, `real_rate_ramp_duration_derate` (the
tightening half of the peak chains, so the peak family is itself two-sided), and the
liquidity pair (TGA/RRP drain→build) once its node series are verified resolvable.
Each chain: measured thresholds, structured falsifiers, provenance episodes, validator
notes — the W-A bar.

### W-D — The last mile: assembly to the surfaces the operator reads (designer/opus for surface form; builder/opus for wiring)

The precedent exists: `watchlist_risk.js` already renders a per-name "sits downstream
of the X cascade" chip off `site/transmission_chains.json`. Extend the same artifact
to the remaining glance surfaces (TXA-R6 vocabulary, EN/zh, dual-read where local
state disagrees):
1. **macro.html hero region**: active-episode chip when any chain ≥ propagating
   ("Rates-relief cascade: 2 of 3 confirmed — watch" / 降息传导：3步已确认2步——观察).
2. **Prophet US/CN context rail**: chain-state context line on the board header (not
   rows, not ordering — context only; the graded population fence untouched;
   grep-verified absent today despite TXI-R7 naming Prophet a consumer).
3. **Sector boards**: blast-radius dual-read on affected rows (gold_miners row gains
   "real-rate peak chain propagating" beside its own trend read when active).
4. **Commodities + crypto surfaces**: the PM/crypto chains' states on their asset
   pages, with the base-rate hover now that W-B has rates to print.
5. **Mastermind chat**: `_summarize_transmission_chains` already rides the bridge;
   the market packet's WATCH line gains active-episode one-liners with base rates.
   Acceptance: computed-style visual verification per house law; no new page; chips
   render nothing when no chain is active (honest empty state); every chip's hover
   carries the receipt (hop states + windows + base rate or "untested"); the site
   JSON's one-nightly lag_note is preserved on every new consumer.

### W-E — Alerting + detrigger (builder/opus)

Chain transitions currently reach NO alert lane (grep-verified: zero references in
`engine/alerts.py`, `alert_triage.py`, `notify_turn_events.py`). The sanctioned path
is the `falsifier_tripwires` precedent: register a chain-transition rule through
`engine.alerts.log_and_dedup` so `alert_triage` aggregates it, push expressed/failed
through the existing priority-floor lanes, and register the reflex rows (TXA-R7). The
deterministic daily brief gains a "cascades" line (what armed, what confirmed, what
stopped being true); detrigger surfaces as "no longer active — <which leg went
false>" in the same voice everywhere (never refutation-register, G0.5). Ops note for
the operator: Actions carries no TELEGRAM secrets today, so every "Telegram+Discord"
sender is Discord-only in practice — alert delivery inherits that until the secret
lands (surfaced here, owned by ops).

### W-F — Activation checklist (small PRs; each independently shippable)

Dark-organ sweep found by this audit, each a one-line-to-small fix with its owner:
`transmission_proposals` arming decision (§6 D2, operator); NW→Mastermind bridge flag
(arming condition passed 2026-07-19, ruling unrecorded — surface to operator, §6 D3);
`data/qledger/falsifier_evaluations.jsonl` wired-but-absent output (investigate: no
due claims vs. dark grader); `chain_state` synapse consumers list updated for the new
chips as they land.

### W-G — Promotion path (long clock; no build now)

After ≥1 quarter of forward episodes (TXI-R4): probe-tier review per chain. Any
authority ask goes through `promotion_gate.py` + its own prereg with trial-ledger
honest-N — and enters each consumer ONLY through that consumer's own precedented
channel (the consumer census, verified 2026-08-05):
- **Prophet US**: a zero-authority recorded column in `engine/us_context_vector.py`
  first, then the roadmap §3 bounded-authority ladder — never a hidden blend. (The
  live macro precedent is `prophet_management.py`'s `macro_stance` overlay term.)
- **BTC**: a named driver key in `macro_overlay()`'s config-weighted dict — with the
  `curve_score`/`fed_score` staged-not-folded precedent as the mandatory first step.
  The Override-Registry stays closed (BTC audit D1–D5).
- **Commodities**: a `factors[key]` merged post-panel with a calibrated weight (the
  `cycle`/`mtf` precedent) or a confidence-only `cmult` — never a direction flip.
- **Theme scoring**: a fifth `_macro_context` axis + `_MACRO_PRIOR` rows.
- **Sizing/PSI: never** — NWP-U18 forbids NW-side sizing influence outright.
Come-back: first probe reads ~2026-11 (one quarter from W-A activation).

## §5 What this plan does NOT do

No scored authority anywhere (G0.1); no revival of killed constructions (xsec commodity
momentum, calendar-gated risk legs, shock→shelter maps, fused regime scorecards — all
standing kills); no new NW lobe; no second LLM loop (CHF's is THE loop); no intraday
chain evaluation v1 (nightly + the live overlays; the packet's FLAGS already carry
same-day tape anomalies to chat); no parallel tripwire system (TXA-R9); no Obsidian
write-path (it is a view; CXI-R12); no per-name rate beta fitting (macro-context rail
ruling: insufficient regime history — sector-level inheritance stands).

## §6 Operator decisions (STOP list)

- **D1 — Ratify this charter** (W-B..W-E dispatch order as written; W-A is already in
  this PR under standing display-tier law). *Recommended: yes.*
- **D2 — Arm the self-extending library**: flip `config/transmission_proposals.yml:
  enabled` to true (one-line PR; weekly cadence; CHF gate + schema firewall + human PR
  review all stand). This is the "find its own truths systematically" switch.
  *Recommended: yes — the fences held for CHF for a month; proposals land as
  hypothesis-tier YAML needing human merge.*
- **D3 — NW→Mastermind bridge flag** (`MASTERMIND_NW_CONTEXT`): the pre-registered
  arming condition (≥5 clean builds) passed 2026-07-19; no ruling recorded since.
  Chain states would reach the trading bot's advisory plane through it. *Recommended:
  arm, advisory-only as designed.*
- **D4 — W-D surface priority**: macro.html chip first (glance tier for the exact
  next event) vs Prophet context rail first. *Recommended: macro.html — it is where
  the operator watched this event happen.*

## §7 Success metrics (baselines = this audit, 2026-08-05)

| Metric | Baseline (pre-PR) | After this PR | Target |
|---|---|---|---|
| Easing-direction chains in library | 0 | 3 | ≥6 (W-C) |
| Chains with mined hop base rates | 0/4 | 6/7 (vol chain honestly "untested" — positioning series not historized) | 7/7 or honest reason per hop |
| `chain_episodes` in grading_closure | undeclared | undeclared | DECLARED + CLOSED once first episode matures (W-B) |
| Chain state on operator glance surfaces | watchlist chip only | watchlist chip only | + macro hero, Prophet rail, affected sector rows (W-D) |
| Transition → operator latency | open transmission.html or ask chat | unchanged | push (expressed/failed) ≤1 nightly; brief line next morning (W-E) |
| Detrigger visibility | none | state machine only | "no longer active" on every surface a trigger reached (W-E) |
| 2026-08-05 case, end-to-end | invisible (no easing chains existed) | 3 chains ARMING on tonight's store; measured context: rolldown→gold p=0.92 (n=269; 0.89/0.94 by growth cell), rolldown→BTC p=0.44 pooled but 0.67 liquidity-contracting vs 0.17 liquidity-neutral/draining (n=268) — the operator's "perhaps crypto" hedge, quantified | forward-graded from here; probe review ~2026-11 |

## §8 Status log

- 2026-08-05 — Charter authored (Fable main loop) from operator escalation + 5-scout
  estate audit (NW engine, consumers, learning infra, transmission+alerting, prior-art
  digest of 12 programs). Shipped in the same PR: **W-A** — three easing-direction
  chains authored (dry-run receipts: oil-slide ARMING on the 60d leg; both
  real-rate-peak chains ARMING on the p99 extreme, staging the rolldown); **W-B first
  light** — `real_rate_extreme` proxies added to the miner, the calibration run for
  the first time in its existence, `chain_calibration.json` committed (7 chains; mined
  spans land on the named peaks: extreme→rolldown 2008-10-08→2025-06-13 n=33 p=1.0;
  rolldown→gold p=0.92 n=269 split 0.89/0.94 by growth cell; rolldown→BTC p=0.44
  pooled, 0.67/0.53/0.17 by liquidity cell — regime-conditionality doing exactly what
  TXI-R6 said it would); era-pinned smoke test healed to era-honest form. Full
  transmission suite green. Two structural holes named with receipts (§2.1
  one-directional library; §2.2 built-but-starved learning loop) and the last-mile map
  drawn (§2.3). Operator decisions D1–D4 open.
- 2026-08-09 — **Peak-chain rev 1** (operator escalation: the engine narrated "no peak;
  restriction still building" nightly through the 2026-07-31 DFII10 plateau while the
  operator's real-rate-peak call was already paying). Falsifier gated on a new
  `off_high_bp` grammar metric (fires only while pressing 10-session highs — measured on
  the 5 named peaks, 2003→), arming vetoed while a falsifier is live (kills the
  arm→fail same-night churn), `stall` turn-watch annotation added to both peak chains
  (0.96 rolldown-within-60s under the stall shape vs 0.85 armed baseline, n printed),
  "failed" label moved off the refutation register (en "Halted" / zh "已中止"),
  calibration re-mined at rev 1. Full anatomy + Neural-Web design seed:
  `research/CASE_STUDY_GOLD_REAL_RATE_PEAK_2026_08.md` (case-file confluence board,
  terminal-leading evidence, condition-prose bindings, operator-conviction ledger).
