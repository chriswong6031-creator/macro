# Neural Web Top-3 Lobe Power-Up Analysis

**Date:** 2026-07-06  
**Author:** Codex  
**Scope:** Pick the three most important lobes already built out, analyze what they are, and define the five highest-leverage build or training moves for each.

## Executive Ruling

I am treating a "lobe" as the repo defines it in the Neural Web future-lobes docket: it owns its own objective function, falsifiers, FDR/trial family, and connects to the Neural Web rails. On that basis I am **not** counting spine, kernel, world_state, cortex, health, confluence graph, or rule replay as lobes. Those are rails and core-brain infrastructure. They matter enormously, but their job is to make every lobe more measurable.

The three most important already-built lobes are:

1. **Oracle / Rotation Intelligence**
   - The market-structure lobe: sectors, themes, subsectors, episodes, routing, regime tags, Time Machine, alerts, reversion tracks.
   - Why top-3: it is the closest thing to the operator's "follow the money" product moat and feeds both dashboard context and Mastermind context.

2. **Entry Intelligence / US Entry Stack**
   - The tactical stock-selection lobe: production entry fires, near-misses, rejections, board lanes, anti-chase shadow, kernel-rank shadow, bottom sensors.
   - Why top-3: it is the direct money-path surface. If this improves, every stock decision improves immediately.

3. **Long-Hold Thesis Layer**
   - The 12-36 month ownership lobe: horizon firewall, long-hold labels, missed-hold kill test, expectation/insider panels, thesis clocks, moat/funnel states.
   - Why top-3: it solves the hardest operator problem the tactical board cannot solve: "which tactical winner should I keep owning?"

Important exclusions:

- **Neural Web core** is the brain/rail system, not one lobe.
- **Short-side / Breakdown** is newly chartered and important, but it is still an avoid/de-risk Phase-0 tape, not yet as built out as the three above.
- **Dispersion** is useful but intentionally small: a regime lens, not a primary decision lobe.
- **Options entry intelligence** is promising connective tissue, but it is not yet as mature as the three selected.

## Evidence Run

I used the current repo artifacts, synapse registry, build docs, and live JSON/parquet outputs. Key checks:

- `config/synapse.yml` / `docs/SIGNAL_BUS.md`
- `research/ORACLE_MASTERPLAN_BY_FABLE.md`
- `research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- `research/long_hold/OBJECTIVE.md`
- `research/long_hold/W1_KILLTEST_RESULTS.md`
- `research/long_hold/EXPECT_DRIFT_RULER_P_RESULTS.md`
- `research/long_hold/LT4_FUNNEL_SHADOW_REPORT.md`
- `site/basketdata/oracle_state.json`
- `site/basketdata/oracle_reversion_state.json`
- `data/oracle/forward_ledger.jsonl`
- `data/oracle/oracle_alerts.jsonl`
- `data/neuralweb/bottom_sensors.parquet`
- `site/factordata/us_standouts.json`
- `data/research/long_hold_labels.parquet`
- `data/research/missed_hold_study_results.parquet`
- `data/research/expect_drift_panel.parquet`
- `data/research/insider_lh_panel.parquet`
- `data/research/thesis_funnel_states.parquet`

One caveat: the giant Entry replay tape under `data/replay/` is intentionally Mac-local / ignored and is not present in this worktree. For Entry Intelligence I used the already-adjudicated reports and current downstream artifacts, not a fresh re-run of that local replay parquet.

## First-Principles Frame

A lobe becomes more powerful only when all six links improve:

1. **Objective clarity:** what exact decision does it improve?
2. **Observation quality:** what state can it see point-in-time?
3. **Label quality:** what outcome proves it was right or wrong?
4. **Counterfactual quality:** what would have happened if we waited, ignored it, entered, exited, or routed elsewhere?
5. **Calibration:** what probability, error bar, base rate, or trust cell does it publish?
6. **Authority discipline:** where is it display-only, shadow, confirmer, or money-path?

Most "more AI" ideas fail because they skip links 2-5. The repo's advantage is not a model architecture. It is the combination of PIT tapes, trial ledgers, FDR discipline, forward ledgers, and a willingness to print nulls.

# 1. Oracle / Rotation Intelligence

## What It Is

Oracle is the rotation lobe. It reconstructs and monitors the history of sector, theme, and subsector relative motion:

- panel: sector/theme/subsector state by date
- graph: co-movement, inverse relationships, lead-lag, complexes
- episodes: onset -> confirmed -> undeniable -> exhaustion
- memory: base rates, analogues, routing candidates
- live bus: `oracle_state.json`
- alerts: `oracle_alerts.jsonl`
- forward audit: `forward_ledger.jsonl`
- reversion sidecar: `oracle_reversion_state.json`
- Time Machine: historical replay product surface

The lobe is explicitly price-implied rotation until true flow layers earn their way in. Its best current use is not "buy the new group blindly." It is:

- see rotation early
- understand who is rolling over and who is catching flow
- route attention
- manage exposure
- feed display/context into Neural Web and Mastermind

## Current State

Synapse shape:

- **23 Oracle artifacts**
- **14 display**, **5 shadow**, **4 infrastructure**
- **18 tactical_entry**, **5 context**

Current live artifact snapshot:

- `site/basketdata/oracle_state.json`: quiet as of 2026-07-06
- 8 complexes in state payload
- 0 active episodes
- 0 onset watchlist entries
- `data/oracle/forward_ledger.jsonl`: 173 keep-first detection rows
- `data/oracle/oracle_alerts.jsonl`: 108 alert rows
- `site/basketdata/oracle_reversion_state.json`: 11 display-level reversion signals
- `data/oracle/memory_base_rates.json`: onset false-start rates are about 38.1% for out episodes and 34.3% for in episodes; onset-to-confirmed conversion is about 99.7%
- `data/oracle/sentinel_log.jsonl`: current warning that the decay monitor has no published baseline for `ep_in_onset_21d` and `ep_out_onset_5d`

Current evidence shape:

- P3 primaries were NULL: confirmed-tier exit and entry were too late / not enough.
- The useful edge lives earlier: onset secondaries were DISPLAY-WITH-EDGE, especially in-onset 21d and out-onset 5d.
- Routing cells are mostly candidates, not authority. Some cells survive display checks, but the registered placebo discipline keeps them capped.
- Reversion signals have attractive backtest stats in the sidecar, but current live matured n is 0 for the displayed signals in the sampled artifact. They are display, not authority.

## First-Principles Diagnosis

Oracle's core problem is **speed versus false-start control**.

Confirmed rotations are clean but late. Onset rotations are useful but noisy. That means the lobe should not try to become a single "rotation score." It should become a calibrated **transition detector**:

- How early is this state?
- What is the historical false-start rate for this type?
- What source/sink relationship is implied?
- Is this cap-weighted, equal-weight, or member-level flow?
- Are leaders extended while laggards are just beginning?
- Does the receiving group have sponsorship breadth or only one megacap?

The healthcare tape note in `data/oracle/operator_tape.jsonl` is exactly the missing abstraction: an ETF can look late while member laggards are early. Oracle currently sees complexes. It needs a stronger member-phase layer.

## Five Priority Builds / Training Moves

### O1. Train an onset-quality calibrator, not a direction oracle

**Build:** `oracle_onset_quality` as a registered display/shadow artifact.

**Train with:**

- historical episode rows from `episodes_s/m`
- onset -> confirmed conversion
- onset +5/+21/+63 direction-adjusted outcomes
- false-start tags
- features at onset only: accel_z trajectory, cohesion_chg, breadth_50, VIX/rates/liquidity regime, source/sink complex, two-sidedness, member dispersion, prior route stability, current personality class

**Output:**

- `p_confirm`
- `p_false_start`
- expected detection lag
- calibrated reliability bucket
- reason vector, e.g. "fast breadth but weak cohesion" or "strong source/sink two-sidedness"

**Acceptance gate:**

- Brier/log-loss improvement versus the current base-rate table
- era-stable calibration
- no score/sizing/gating authority until a forward ledger earns it

**Why this is first:** Oracle's live product is early detection. Accuracy means knowing when early is good enough and when early is just noise.

### O2. Build the Flow-Routing Tensor with stability budgets

**Build:** a source -> sink route table with lag distribution and stability stamp.

**Train with:**

- the daily panel, not just sparse episodes
- source complex outflow windows
- sink complex inflow windows
- 1-15 session lead-lag tensors
- route placebo distributions
- regime-conditioned stability

**Output:**

- route posterior: source_complex -> likely_sink_complex
- median lag
- hit-rate with n and regime
- stability across eras
- FDR family and trial count printed

**Acceptance gate:**

- must beat route placebo
- must remain stable across at least two independent eras
- small-n route cells stay display-accruing

**Why this matters:** the operator's actual question is "where does the money go?" not "is XLV green today?" Oracle needs a structured money-routing memory.

### O3. Add member-phase intelligence inside each complex

**Build:** a member-phase layer for each active complex.

**Train with:**

- cap-weight ETF state
- equal-weight basket state
- member-level trigger state
- leader/laggard split
- within-complex dispersion
- current board lane states
- bottom_sensors fields
- earnings/event calendars

**Output:**

- "leader exhaustion" vs "laggard catch-up" vs "broad sponsorship" vs "single-megacap mirage"
- per-complex member phase map
- candidate members that are early while the ETF is late

**Acceptance gate:**

- show that member-phase tags explain better forward member dispersion or entry success than complex state alone
- no hard group gate without its own gauntlet

**Why this matters:** sector rotation has different meaning for XLV, equal-weight healthcare, and washed-out healthcare members. Collapsing those destroys the operator's edge.

### O4. Harden the reversion promotion track into a sequential evidence engine

**Build:** upgrade Oracle reversion from static display sidecar to a live evidence ladder.

**Train with:**

- `data/oracle/reversion_forward/<compound_id>.jsonl`
- live matured rows
- overlap clusters between related rules
- economic effect sizes, not just win rates
- Wilson lower-bound lift versus base rate
- drawdown / MFE / timing decay

**Output:**

- compound clusters, not just individual rules
- correlated-rule de-dup
- live n, matured n, lift lower bound
- promote / continue accruing / retire queue

**Acceptance gate:**

- sequential monitoring with pre-declared thresholds
- no auto-promotion
- display -> shadow -> confirmer only when live evidence clears the same discipline as the rest of the house

**Why this matters:** Oracle already has promising reversion mechanisms. The bottleneck is not idea generation; it is live proof without double-counting overlapping variants.

### O5. Fix Oracle truth maintenance: sentinels, decay, and schema drift

**Build:** an Oracle truth-maintenance job.

**Train / measure with:**

- sentinel logs
- schema diffs between gauntlet outputs and live readers
- stale base-rate baselines
- live ledger decay
- route-cell misses
- false starts by regime

**Output:**

- "edge still measurable", "edge monitor inert", "edge stale", "schema drift", "needs re-registration"
- automatic hypothesis inbox entries for broken monitors
- no silent green runs when a monitor is blind

**Acceptance gate:**

- sentinel baseline coverage for every published edge cell
- decay monitor emits actionable status for `ep_in_onset_21d` and `ep_out_onset_5d`

**Why this matters:** a learned market memory that cannot forget or detect broken readers becomes dangerous. Oracle's accuracy depends on retiring stale truths as much as finding new ones.

# 2. Entry Intelligence / US Entry Stack

## What It Is

Entry Intelligence is the tactical stock-entry lobe. It answers:

- is this name ready now?
- is it bottoming, continuing, or just watch?
- which gates rejected it?
- what near-misses did we miss?
- which entry species deserve more trust?
- how should the board order candidates?

It is the lobe closest to the operator's daily money path.

## Current State

Core report-derived replay state:

- production replay complete in prior run: **961,656 rows**
- **57,640 fires**
- **49,939 verdict-grade fires**
- **25,783 episodes**
- verdict window: 2022-06-30 -> 2026-07-02
- raw gate report card: about **63% stopped**, **33% clean liftoff**, **4% cushioned**

Current board state:

- `site/factordata/us_standouts.json` as of 2026-07-02
- lane counts: **12 continuation**, **7 bottoming**, **24 watch**
- list rows checked: 55 rows across lists
- current `antichase_shadow_blocked`: false for all sampled rows
- liquidity fields present on only 8 of 55 list rows in this artifact

Current bottom-sensor artifact:

- `data/neuralweb/bottom_sensors.parquet`: **1,722 rows**, US only
- all rows display-only
- state counts:
  - WATCH: 1,666
  - HOLD_LAUNCHED: 28
  - FRESH_FIRE_TACTICAL: 13
  - KNIFE_RISK: 9
  - CHASE_RISK: 5
  - DEAD_MONEY_RISK: 1
- `rs_repair_state`: unavailable for all rows
- `sponsorship_state`: unavailable for all rows
- only 16 rows have `bars_to_cross`

Current evidence shape:

- P1.3 found real signal in anti-chase, washout, and RS-inflection, but with different authority shapes.
- Anti-chase earned hard-gate path because it blocks a small share of fires and reduces stop risk.
- Washout was too blunt as a hard gate and later failed as a production COILED rank-weight; it remains mechanism evidence / future clade material.
- RS-inflection is marginal and parked.
- P2.5 found useful interaction shapes: deep-washout + anti-chase-pass + RS-favorable is the strongest shadow candidate, but it is in-sample-selected and must accrue forward.
- Recall remains the ugly number: fires catch only a tiny fraction of durable lows and only a small fraction of large moves.

## First-Principles Diagnosis

Entry Intelligence is not mainly lacking more indicators. It is lacking **state-complete lifecycle data**.

The current hard trigger is powerful enough to create a clean event tape, but too narrow to catch enough opportunities. The lobe needs to learn from:

- fired names
- near-misses
- rejected names
- names that never triggered but later worked
- names that triggered but became dead money
- names that based after an old trigger
- names that looked extended but still continued

The objective is not "maximize buys." It is:

- lower stop/dead-money rate
- improve recall without flooding the board
- sort bottoming versus continuation honestly
- turn rank from hand formula into posterior outcome distribution

## Five Priority Builds / Training Moves

### E1. Promote replay into a stable, queryable feature mart

**Build:** `entry_replay_feature_mart` as the canonical training store.

**Train with:**

- production fires
- near-misses
- rejections
- never-triggered durable lows
- bottom_sensors
- board lane state
- anti-chase shadow ledger
- kernel-rank cells
- options_entry_state
- Oracle complex/member phase
- liquidity/capacity fields

**Output:**

- one row per ticker-date candidate state
- stable event ids
- PIT feature freeze
- target labels at 5/10/21/63/126d
- row type: fire / near_miss / rejection / never_triggered / old_fire_basing

**Acceptance gate:**

- golden test against current production board
- feature availability and survivorship stamps printed
- R2/R2 storage or Mac-local explicit path, not accidental git data

**Why this is first:** every better model or rule needs a complete event substrate. The local replay already exists; it needs to become a durable training table rather than a one-off study artifact.

### E2. Train a recall-first near-miss and never-triggered learner

**Build:** a recall audit learner that finds useful setups the hard trigger missed.

**Train with:**

- never-triggered durable lows
- never-triggered +20%/60d moves
- rejected names by reason
- old confluence crosses that based instead of launching
- bottom_sensors WATCH rows
- lead-up states 5/10/21 days before the move

**Output:**

- "watch-pre-fire" candidates
- reason why the normal trigger missed it
- expected wait state, not a buy state
- recall contribution by archetype

**Acceptance gate:**

- improves recall at fixed maximum board expansion
- no increase in stop/dead-money beyond a pre-declared cap
- can only surface as watch/pre-fire until forward evidence clears

**Why this matters:** the lobe is already decent at precision. Its biggest weakness is missed opportunity coverage. The missing model is not a new buy signal; it is a detector for "this is approaching the trigger but the trigger is too late."

### E3. Replace hand rank with hierarchical outcome posterior

**Build:** `entry_cell_posterior` / kernel-rank v2.

**Train with:**

- 49,939 verdict-grade fires
- 25,783 episodes
- species id
- board lane
- regime
- weekly phase
- RS quartile
- anti-chase state
- extension
- liquidity
- sector / complex phase
- bottom_sensors state

**Output:**

- shrunk posterior for P(clean_liftoff), P(stopped), P(dead_money), P(cushioned)
- n and effective n
- Wilson lower bound
- "why rank moved" explanation

**Acceptance gate:**

- shadow ranking must beat incumbent board order on episode-clustered forward ledger
- pre-registered flip criterion
- no money-path influence before Article 2 shadow period completes

**Why this matters:** a board rank should be a belief about outcome distribution, not a weighted vibe. This is the route from "good dashboard" to institutional entry engine.

### E4. Fill the bottom-sensor blanks: RS repair and sponsorship states

**Build:** bottom_sensors v2 with real `rs_repair_state` and `sponsorship_state`.

**Train with:**

- relative-strength repair after fire
- sector-relative repair
- insider/ownership/fundamental sponsorship
- SUE / expectation-state context
- Oracle member-phase
- options_entry_state where available
- post-fire hold/basing state
- false-positive traps: knife, chase, dead-money

**Output:**

- RS repair: absent / early / confirmed / failed
- sponsorship: absent / technical-only / fundamental / ownership / sector-sponsored / event-blocked
- trap reason
- display-only confidence bucket

**Acceptance gate:**

- non-null coverage across at least the current 1,722-name universe
- no ranking effect until a registered study shows improvement

**Why this matters:** current bottom_sensors is mostly a label envelope. It needs to become a real observation layer for "bottom is forming" versus "dead bounce."

### E5. Train lifecycle/hazard models instead of static entry labels

**Build:** an entry lifecycle state machine.

**Train with:**

- pre-fire state
- fire date
- post-fire basing
- post-fire launch
- old-fire basing after confluence aged out
- stop/dead-money/cushion/liftoff state
- antichase shadow outcomes
- exit-regret / rule-replay outputs

**Output:**

- state: approaching -> fired -> awaiting_confirmation -> basing -> launched -> failed -> stale
- hazard of launch versus stop by horizon
- "wait", "small starter", "do not chase", "re-arm after base" context

**Acceptance gate:**

- separates "late but still valid continuation" from "chase risk"
- improves timing without reducing recall below the P1.4 floor

**Why this matters:** entry is a time process, not a single point. The lobe will become more accurate when it learns how good setups evolve over days and weeks.

# 3. Long-Hold Thesis Layer

## What It Is

Long-Hold is the ownership-duration lobe. It is intentionally firewalled from tactical entry. It answers:

- after an entry worked, is there evidence to keep owning this beyond the entry clock?
- did the tactical winner become a compounder, cheap trap, multiple-expansion-only winner, sector-laggard winner, or tactical-only name?
- what falsifiers would break the thesis?
- which names are only display-level thesis candidates?

This lobe is not allowed to improve board entries. Its job is hold-thesis context and eventual de-escalation / thesis tracking.

## Current State

Synapse shape:

- **20 long-hold artifacts**
- **18 hold_thesis**
- **19 display**, **1 infrastructure**
- explicit firewall language: hold_thesis artifacts must not feed entry stack z-scores, board ordering, top-setups, alert triage, or push floor

Label substrate:

- `data/research/long_hold_labels.parquet`: **113,542 fires**
- **2,495 tickers**
- fire date range: 2014-08-11 -> 2026-07-02
- price resolved for **113,361** rows; no price for 181
- labels:
  - unlabeled: 65,723
  - tactical_only_fail: 34,604
  - cheap_trap: 4,409
  - tactical_only: 4,406
  - sector_laggard_winner: 3,404
  - multiple_expansion_only: 801
  - compounder: 195
- tactical wins: 15,106

Kill-test state:

- `data/research/missed_hold_study_results.parquet`: 30 rows
- G1 primary honest OOS leg was **DEFERRED_N_FLOOR**
- Fable ruling: **G1 DEFERRED**, neither killed nor survived
- W3/W4 remain locked: no active thesis ledger, no species registration, no committee authority
- retest planned for 2025+ honest cohort when compounder clusters reach the floor, projected around 2027-H2

Supporting feature panels:

- `expect_drift_panel.parquet`: 113,542 rows, display-only
- `insider_lh_panel.parquet`: 113,542 rows, display-only
- expectation-drift Ruler-P: only `sue_streak` has a descriptive pass; effect is small and capped
- insider Ruler-P: all tested insider features are NULL

Thesis funnel:

- `thesis_funnel_states.parquet`: **1,503 tickers**
- state counts:
  - not_eligible: 1,002
  - watch_for_thesis: 255
  - thesis_candidate_shadow: 246
- ceiling is `thesis_candidate_shadow`; no `active_thesis` state exists

## First-Principles Diagnosis

Long-Hold's core problem is **rare labels with delayed truth**.

Only 195 compounders exist in the current label store. The honest OOS window has too few missed-hold clusters. That means the correct path is not to force a model. The correct path is:

- repair label coverage
- pre-register feature families before outcome contact
- accumulate forward honest cohorts
- use display-only screens for now
- build deterministic thesis falsifiers before active thesis claims

This lobe becomes powerful by learning **what breaks ownership**, not by pretending it can rank 36-month compounders today.

## Five Priority Builds / Training Moves

### L1. Repair the honest OOS substrate: dead names, benchmark mapping, per-fire sector benchmark

**Build:** Long-Hold data repair v2.

**Train / repair with:**

- dead-name price histories
- fuller sector-to-ticker map
- per-fire sector benchmark S(f), not winner-selected cohort means
- gap-leg continuity checks
- price-store iteration for A1-to-spec benchmark

**Output:**

- more honest OOS missed-hold clusters
- fewer benchmark artifacts
- less survivorship sign ambiguity

**Acceptance gate:**

- honest OOS `missed_hold` clusters reach the registered floor
- no G1 retest until the cohort is frozen by amendment

**Why this is first:** the lobe cannot train its core question until the label floor exists. More model complexity before label repair is theater.

### L2. Execute the registered multi-family feature roster under one program-level FDR budget

**Build:** a controlled Long-Hold feature battery runner.

**Train with the registered families:**

- F1 fundamental family
- F2 washout-timeframe family
- F3 expectation-drift family
- F4 insider-sponsor family
- future families only inside the LH-R11/LH-R12 ceiling

**Output:**

- program-wide FDR summary
- within-family descriptive tables
- feature provenance stamps
- restricted-range flags
- Ruler-P versus Ruler-H separation

**Acceptance gate:**

- program-wide hypothesis ceiling enforced
- Ruler-P remains display-only
- Ruler-H reserved for the 2025+ OOS retest

**Why this matters:** Long-Hold has many plausible weak signals. Without a program-level budget, it will fool itself through family expansion.

### L3. Build a deterministic thesis-transition ledger

**Build:** `long_hold_thesis_transition_ledger.jsonl`.

**Train / measure with:**

- thesis funnel state
- moat falsifiers
- capital allocation changes
- solvency changes
- expectation-state deterioration
- insider deterioration
- earnings/fundamental update clocks
- operator action outcomes eventually

**Output:**

- watch -> challenged
- challenged -> recovered
- challenged -> falsified
- no active-thesis authority until G1 unlocks
- every transition tied to deterministic tripwire id

**Acceptance gate:**

- append-only ledger
- nightly sole advancer
- LLM may summarize but cannot fire transitions

**Why this matters:** the lobe can become useful before it can pick compounders by teaching the system when a hold thesis is decaying.

### L4. Turn the thesis funnel from snapshot into longitudinal memory

**Build:** append/archive hook for thesis-funnel snapshots.

**Train with:**

- repeated `thesis_funnel_states.parquet` snapshots
- state transitions over time
- coverage changes
- fundamental-period update cadence
- subsequent label changes when matured

**Output:**

- state transition matrix
- stability score by ticker
- "improving evidence" versus "coverage artifact"
- historical state at fire date for future Ruler-H

**Acceptance gate:**

- no overwrite-only history for important display states
- state-proportion drift >5pp triggers coverage audit before interpretation

**Why this matters:** current funnel state is a one-day cross-section. A thesis lobe needs memory of improvement and deterioration.

### L5. Train a compounder/trap analogue explainer, not an authority model

**Build:** Long-Hold analogue explainer.

**Train with:**

- 195 compounders
- 4,409 cheap traps
- 4,406 tactical-only names
- 801 multiple-expansion-only names
- 3,404 sector-laggard winners
- SEC fundamental sequences
- expectation drift
- insider sponsorship
- capital allocation
- moat falsifiers
- entry washout/timeframe once registered

**Output:**

- nearest historical analogues by thesis path
- reasons a name resembles compounder / cheap trap / multiple-expansion winner
- confidence capped by label rarity
- display-only explanation cards

**Acceptance gate:**

- improves Ruler-H feature interpretation after G1 retest
- cannot produce "active_thesis" before the locked unlock condition

**Why this matters:** with rare labels, interpretability and analogue retrieval are safer than a black-box classifier. The right question is "what historical ownership path does this resemble?"

# Cross-Lobe Power Moves

## 1. Make Oracle feed Entry only as context, never a hard gate

Oracle complex/member phase should enrich Entry's feature mart. It should not hard-gate stocks until a registered stock-level study shows it improves stop/dead-money without killing recall. The China group-gate failure remains the warning.

## 2. Let Entry generate candidates; let Long-Hold decide what not to sell

Entry is a 5-126 day lobe. Long-Hold is a 252d+ lobe. The firewall is correct. The connection should be a handoff:

- Entry says: "this was a valid tactical event."
- Long-Hold says: "the entry clock expired; here is whether ownership evidence improved or decayed."

## 3. Use Oracle member-phase as a bridge between the two

The strongest cross-lobe idea is member-phase rotation:

- Oracle sees group flow.
- Entry sees whether a member is tactically ready.
- Long-Hold sees whether the member is a compounder, trap, or multiple-expansion bounce.

This is how the healthcare insight becomes machinery: leaders, laggards, ETF phase, equal-weight phase, and individual thesis quality must stay separate.

## 4. Train every lobe on "missed decisions", not just fired decisions

The most important examples are not only the ones the system acted on:

- Oracle rotations that started but were not alerted
- Entry names that never triggered but later worked
- Long-Hold tactical winners sold too early or held too long

The next accuracy leap comes from counterfactuals.

## 5. Promote from surfaces to ledgers

Every display surface should have a corresponding ledger:

- Oracle: detection -> outcome -> edge decay
- Entry: candidate -> trigger/reject -> terminal state
- Long-Hold: thesis state -> falsifier / recovery -> long-horizon label

Without the ledger, the lobe is a dashboard. With the ledger, it becomes trainable.

# Recommended Build Order

1. **Entry E1: replay feature mart**
   - Highest immediate multiplier. It gives Entry, Long-Hold, and future short-side work one shared event substrate.

2. **Oracle O1 + O5: onset calibrator plus truth maintenance**
   - Oracle already has live alerts and ledgers. Make early alerts calibrated and make monitors unable to go blind silently.

3. **Entry E2 + E4: recall learner plus real bottom-sensor states**
   - Directly attacks the biggest tactical weakness: too many good moves never enter the fire tape.

4. **Long-Hold L1: honest OOS substrate repair**
   - No credible long-hold selection model exists until the missed-hold cluster floor is repaired.

5. **Oracle O3 + Entry E3: member-phase plus outcome posterior**
   - This is the first true cross-lobe intelligence layer: group flow meets stock entry quality.

6. **Long-Hold L3 + L4: thesis ledger and funnel memory**
   - Useful even while G1 remains deferred because it measures evidence decay without granting authority.

# Final Takeaway

The three lobes are already far past "idea" stage:

- Oracle has the rotation organism and live audit rails.
- Entry has the event tape and first shadow upgrades.
- Long-Hold has the firewall, labels, and display thesis substrate.

The next leap is not a bigger LLM. It is **better labels, better counterfactuals, calibrated early-warning states, and longitudinal ledgers**.

If we do this right, the lobes grow into:

- Oracle: a calibrated flow-transition brain
- Entry: a posterior-ranked tactical decision engine
- Long-Hold: a thesis-decay and compounder-analogue engine

That combination is much more powerful than any single master score because each lobe remains honest about its horizon, evidence, and authority.
