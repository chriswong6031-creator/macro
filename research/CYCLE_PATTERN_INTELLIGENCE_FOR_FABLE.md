# Cycle Pattern Intelligence - Research Report For Fable

Date: 2026-07-06
Scope: `cycle.html`, `sector_cycles.html`, `markets.html`, `sector_central.html`, `sector_central_china.html`, Cycle Intelligence, Oracle, Neural Web, and Research Factory integration.
Audience: Fable / Claude implementation review.

## Executive Ruling

Build this, but do not build it as an Oracle subsystem and do not let it remain a hidden extension of the existing page builders. The right object is a Cycle-owned Pattern Intelligence lobe that exports governed artifacts into Neural Web and lets Oracle consume only approved cycle context.

The current repo already has many of the hard pieces: cycle state generation, 15-year sector and basket histories, country cycle histories, live forward logs, central call ledgers, promise scorecards, a hazard model, narrative/DNA files, and the Fable cycle constitution. What it does not yet have is a canonical cross-cycle learning substrate that can:

1. Join all cycle states into one point-in-time feature lake.
2. Search for repeating patterns across sectors, countries, baskets, and macro cycles.
3. Separate true recurrence from data-mined coincidence.
4. Store both positive findings and null findings as durable, versioned "market truth" artifacts.
5. Surface those artifacts to Neural Web, sector central pages, and Oracle without letting them become unearned live scores.

The practical answer is therefore:

- **Yes, this is partly already Cycle.** The measurement spine, promise scorecards, hazard panel, conditional-cell work, forward logs, and sector/country cycle engines are already the beginning of this.
- **No, it is not yet the full learning system.** The data is still stored as islands, and most live ledgers are young. There is no cross-cycle feature lake, no candidate truth registry, no pattern promotion workflow, and no first-class Neural Web cycle lobe.
- **Do not put ownership in Oracle.** Oracle is a rotation/institutional-money lobe. It can consume cycle pattern context later, but it should not own cycle truth discovery.
- **Do not let LLMs create signals.** AI can summarize, cluster narratives, propose hypotheses, and write review packets. Statistical harnesses and forward ledgers must decide whether a candidate survives.
- **Treat "truth" as permanent memory, not permanent authority.** A market truth artifact should be saved forever, including retired/null findings, but its authority must decay, be rechecked, and be revocable.

The build target should be named something like **Cycle Pattern Intelligence** or **Cycle Memory Lobe**. It belongs under `cycle-intelligence`, registers outputs on the Signal Bus, uses Research Factory for candidate lifecycle governance, and gives Neural Web a compact `cycle_pattern_state` lobe.

## Already Covered / Excluded

This report should not re-litigate existing Fable rulings. The important exclusions are:

- No broad "cycle position predicts returns" claim. The W0.4 cycle verdict already found that position-to-forward-return edge does not survive as a general rule.
- No rotation-cycle entry confluence score right now. The rotation/cycle confluence ruling said not to build that entry test until live logs mature.
- No lead-lag interaction engine on the current evidence. The phase-0 lead-lag study found in-sample survivors but no useful out-of-sample lift.
- No LLM-originated live scoring. Existing Neural Web and Oracle rules allow LLMs to compress and de-escalate context, not originate signals, ranks, or escalations.
- No "permanent truth" without a falsifier. The artifact can be permanent; the authority cannot be.

The new work should focus on what is missing: a governed discovery and memory system over the historical cycle substrate.

## Current Cross-Cycle System Map

### `cycle.html`

The flagship cycle page now has engine-backed measured bands plus curated frame bands. The builder emits `site/cycledata/cycle_engine.js`. Measured bands are generated from the proxy registry through the same cycle-recording kernel used elsewhere; frame bands remain non-scalar curated context.

What it is good at:

- Cross-asset cycle orientation.
- Separating measured engine bands from frame/opinion bands.
- Giving a broad macro/cycle context layer.

What it is missing for pattern intelligence:

- No unified row-level feature export for ML across all measured bands.
- No direct linkage to sector/country cycle episodes.
- No market-truth registry attached to discovered cycle patterns.

### `sector_cycles.html`

The US sector cycle page is the richest cycle substrate. The current rendered dataset covers 76 records:

- 11 sector ETFs.
- 46 thematic baskets.
- 8 Nasdaq groups.
- 11 Russell groups.
- 186 visible sector turns and 437 all sector turns.
- 789 visible/all basket turns.
- 136 Nasdaq turns.
- 234 Russell turns.
- Hazard fields present for the 57 primary sector/basket records.

The engine emits oscillator position, phase, turn records, `pos_v2`, `phase_v2`, stance, divergence, overdue state, trend and relative-strength context, projection fields, and hazard fields. It also has narrative, DNA, and leg-context files that describe the historical episodes in human terms.

What it is good at:

- A broad sector and thematic cycle map.
- A long historical sample of turns and leg narratives.
- A ready substrate for phase, hazard, and analog pattern mining.

What it is missing:

- The narrative/DNA layer is not yet canonical machine-readable hypothesis input.
- Basket membership and construction need frozen identity metadata before being treated as fully point-in-time.
- The live forward log is still very young, so old backtests must be separated from forward authority.

### `sector_central.html`

Sector Central fuses cycle state, macro regime, trend, momentum, heat/crowding, and context into a conviction/reasoning surface. It logs calls through the sector central grader.

What it is good at:

- A practical decision membrane over noisy cycle information.
- Reason traces and call ledgers.
- A conservative hierarchy where cycle/regime/trend matter more than raw momentum.

What it is missing:

- It is a hand-built fuser, not a learned pattern-memory layer.
- The grader is display/research only and is not read back into live scoring.
- There is no explicit "this reasoning step is supported by truth artifact X" linkage.

### `sector_central_china.html`

China Sector Central is similar but adds China-specific regime de-risking and pathway odds for a limited set of sectors. It logs calls through the China central grader.

What it is good at:

- Applying the same central-fuser idea to China sectors.
- Treating China-specific pathway odds separately from generic sector cycle logic.
- Avoiding one-size-fits-all US transfer.

What it is missing:

- Pathway intelligence is limited to a few sectors.
- China basket histories are shorter and need careful sample-size treatment.
- Revision-prone macro/context variables must be tagged before they can become high-authority evidence.

### `markets.html`

Markets is a curated market-cycle overlay. It now maps most markets to the country-cycle engine while keeping some markets as opinion-class frame data.

Current state:

- UK, Japan, Hong Kong, Canada, China, India, and Taiwan are engine-backed through the country-cycle pipeline.
- US and Europe still rely on curated/opinion-class fallback in this surface.
- The app plots `pos_v2` where engine data exists.

What it is good at:

- Bridging country cycles into a market-facing page.
- Displaying engine-backed cycle position where available.
- Keeping stale/curated data visually separated.

What it is missing:

- A single cross-country/cross-sector pattern search layer.
- A canonical way to compare "country cycle state plus sector cycle state plus Oracle rotation state."
- A lobe summary that Neural Web can consume.

## Existing Evidence And Learning Assets

The repo already contains several real learning assets. They should be treated as the starting skeleton, not rebuilt from scratch.

### 1. Forward Logs

Current forward logs exist for US sectors, China sectors, and country cycles. They store daily cycle stamps by id and date, including phase, position, slope, signal/timing state, trend, relative strength, projection fields, basis, and hazard fields.

Current maturity is low:

- US sector forward log: 114 rows, 57 ids, 2 unique dates.
- China sector forward log: 265 rows, 53 ids, 5 unique dates.
- Country cycle forward log: 62 rows, 31 ids, 2 unique dates.

Implication: forward logs are structurally correct, but not old enough to confer live authority. They are the seed for future authority, not the proof today.

### 2. Central Call Ledgers

Central call ledgers exist for the US and China central pages:

- US sector central calls: 282 rows, 57 ids, 5 unique dates.
- China sector central calls: 265 rows, 53 ids, 5 unique dates.

They are useful for future grading of reasoning, labels, tier returns, hit rates, and rank-IC. They should not be used yet as evidence that the fusers have learned an edge.

### 3. Hazard Panel And Hazard Model

The hazard panel is the most mature statistical substrate for cycle prediction. The current panel has:

- 18,619 rows.
- 73 ids.
- 359 monthly dates.
- Date range from 1996-08-31 to 2026-06-30.
- Family labels, direction labels, age features, position/slope features, trend, momentum, relative strength, volatility percentile, censoring, and event labels.

The current hazard model is already a real learning artifact:

- Up 1m turn hazard passes against the Kaplan-Meier baseline.
- Down 1m, 3m, and 6m turn hazards pass.
- Up 3m and 6m remain prior/weak.
- The model is still `revision_optimistic`, so it should remain evidence with caveats, not a free live trading edge.

Implication: the repo already has a working example of what Cycle Pattern Intelligence should produce: an evidence-labeled model artifact with explicit pass/prior cells, not a vague AI conclusion.

### 4. Promise Scorecards

The promise scorecards are the first real accountability layer over cycle language. They evaluate cycle promises over backfilled monthly point-in-time stamps and live cohorts.

They matter because they teach the future system a critical habit: every claim should have a promise family, outcome target, sample size, and grade. The Pattern Intelligence layer should reuse this framing instead of inventing a second accountability language.

### 5. Conditional Cells

The phase-by-regime conditional cells are useful but constrained:

- Some cells show confidence intervals that differ from phase baseline.
- The work is revision-optimistic because regime labels use revised macro data.
- It is research surface material until a point-in-time regime spine exists.

Implication: these cells can become candidate truth artifacts, but only with evidence class and revision caveat attached.

### 6. Lead-Lag Phase-0

The lead-lag phase-0 work is a negative truth candidate:

- In-sample relationships existed.
- Out-of-sample Brier lift was effectively zero.
- The correct fallback was a synchronization gauge, not an interaction engine.

Implication: the future truth registry should store negative findings. "Do not build this" is a valuable market truth.

### 7. Narrative, DNA, And Leg Context

The sector and country cycle pages already have narrative and DNA files:

- US sector/basket narrative entries: hundreds of historical legs.
- China sector/basket narrative entries: hundreds of historical legs.
- Country/basket narrative entries: hundreds of historical legs.

These are useful for AI summarization and mechanism labeling, but they are not yet statistical evidence. They can become features after normalization, tag extraction, and versioning.

## Core Diagnosis

The Cycle platform currently has measurement, pages, and some gauntlets. It does not yet have a pattern intelligence loop.

The missing loop is:

1. Canonicalize all cycle states.
2. Join them to outcomes and adjacent context.
3. Generate candidate patterns under a controlled grammar.
4. Run statistical and forward tests.
5. Store promoted, demoted, and killed findings as truth artifacts.
6. Feed only eligible artifacts into Neural Web, Oracle, and central fusers.
7. Keep monitoring them for decay.

Without that loop, "AI found a pattern" is just a nicer way of saying "we mined a chart." With that loop, ML and AI become useful because they operate inside a court system.

## Recommended Architecture

### Ownership

Cycle Pattern Intelligence should be owned by Cycle Intelligence.

Research Factory should own candidate lifecycle state: candidate creation, registration, trial budget, review, challenge, promotion, monitoring, and retirement.

Neural Web should consume the resulting lobe state and truth artifacts.

Oracle should consume only approved cycle context, mostly as rotation context and risk language. Oracle should not own cycle truth discovery, because that would invert the architecture. Oracle describes institutional rotation; Cycle measures cyclical state.

### Proposed Artifacts

Add a new package of persistent artifacts:

```text
data/cycle_pattern/entities.parquet
data/cycle_pattern/state_monthly.parquet
data/cycle_pattern/state_daily_live.parquet
data/cycle_pattern/outcomes.parquet
data/cycle_pattern/pattern_candidates.jsonl
data/cycle_pattern/pattern_trials.jsonl
data/cycle_pattern/truths.jsonl
data/cycle_pattern/reviews.jsonl
data/neuralweb/cycle_pattern_state.json
site/cycledata/cycle_pattern_state.json
```

The exact paths can move during implementation, but the separation matters:

- `entities`: stable id map and metadata.
- `state_monthly`: backfilled point-in-time research panel.
- `state_daily_live`: nightly forward stamps.
- `outcomes`: forward returns, drawdowns, turn events, phase changes, cone hits, and relative outcomes.
- `pattern_candidates`: raw discovered or proposed patterns.
- `pattern_trials`: pre-registered trial definitions and trial budgets.
- `truths`: promoted, demoted, retired, and null findings.
- `reviews`: periodic decay and kill reviews.
- `cycle_pattern_state`: compact current lobe state for Neural Web and site consumers.

## Canonical Feature Lake

The first buildable system is not a model. It is a feature lake.

Each row should represent one entity at one point-in-time date:

```text
as_of_date
entity_id
display_name
family                 # sector, basket, country, market_band, macro_band
region                 # us, china, intl, global
engine                 # sector_cycles, china_sector_cycles, country_cycles, flagship_cycle, markets
kind                   # sector, thematic_basket, index_group, country, macro_proxy
source_artifact
turn_def_version
engine_fingerprint
membership_version
price_asof
basis                  # daily, monthly, measured, frame, proxy, local, usd
pos_osc
pos_v2
phase
phase_v2
stance
osc_slope
age_m
age_bucket
overdue
divergence
projection_date
projection_confidence
hazard_1m_p
hazard_1m_src
hazard_3m_p
hazard_3m_src
hazard_6m_p
hazard_6m_src
trend_pass
above_200d
rs_21d
rs_63d
mom_score
vol_pctile
central_label
central_score
central_direction
central_tier
macro_regime
vol_regime
breadth_regime
oracle_rotation_state
dna_tags
narrative_tags
data_quality_flags
```

Outcome rows should be joined later, never known at stamp time:

```text
as_of_date
entity_id
ret_fwd_21d
ret_fwd_63d
ret_fwd_126d
excess_ret_fwd_21d
excess_ret_fwd_63d
excess_ret_fwd_126d
max_drawdown_fwd_21d
max_drawdown_fwd_63d
max_drawdown_fwd_126d
turn_event_1m
turn_event_3m
turn_event_6m
phase_change_1m
phase_change_3m
cone_hit_1m
cone_hit_3m
cone_hit_6m
central_call_hit
central_rank_next_return
```

This schema lets ML ask much richer questions than "is phase high or low?"

Examples:

- When China cyclicals are in early-cycle repair and US defensives are late-cycle/overdue, what happens to cross-region relative strength?
- When hazard is high but trend remains intact, do turns arrive or does the trend persist?
- When a thematic basket enters trough with improving RS but parent sector remains late-cycle, is the basket signal noise or early leadership?
- When country cycles are synchronized near peak but sector dispersion is wide, does drawdown risk concentrate or rotate?
- When central fuser conviction disagrees with raw cycle phase, which side historically grades better?

## Pattern Discovery Engines

The system should use multiple discovery engines, each constrained by the same candidate registry and promotion rules.

### 1. Deterministic Lattice Scan

Start with controlled statistical scans, not black-box ML.

Candidate dimensions:

- Phase and `phase_v2`.
- Position bins.
- Slope direction.
- Age/overdue buckets.
- Hazard pass/prior cells.
- Trend pass/fail.
- RS strength/weakness.
- Macro/vol/breadth regime.
- Region and family.
- Central label or direction.
- Oracle rotation state, only as context and only where point-in-time.

Allowed targets:

- Forward drawdown.
- Turn arrival hazard.
- Cone miss probability.
- False-turn risk.
- Relative performance versus benchmark.
- Phase persistence.
- Central call grading.

Default excluded target:

- Broad forward absolute return from cycle position alone.

That exclusion is not because returns are uninteresting. It is because the repo already learned that generic position-to-return claims are the weak path.

### 2. Motif And Analogue Retrieval

This is where ML becomes meaningfully useful.

Build shape windows from the last 3, 6, 9, and 12 months of:

- Position.
- Slope.
- Hazard.
- Relative strength.
- Trend state.
- Dispersion or synchronization.
- Macro/vol regime tags.

Then compare current windows to historical windows through simple, auditable methods first:

- Nearest-neighbor distance over standardized vectors.
- Dynamic time warping for shape similarity.
- Shapelet extraction for recurring pre-turn or pre-drawdown paths.
- Cluster labels for recurring episode types.

The output should not be "buy/sell." The first output should be:

- Similar prior episodes.
- What happened afterward.
- How many examples.
- How stable the outcome was by era.
- Whether the analogy is contradicted by a stronger truth artifact.

A page-facing version could show: "Current semiconductors resemble these 8 prior early-repair-with-strong-RS episodes; 5 resolved into continued repair, 2 failed, 1 chopped. Evidence class: display only."

### 3. Supervised Risk Models

The most promising supervised targets are risk and event targets, not raw return targets.

Good model families:

- Turn hazard.
- Drawdown hazard.
- Cone miss risk.
- False repair risk.
- Late-cycle exhaustion risk.
- Phase persistence probability.
- Central fuser disagreement outcome.

Model requirements:

- Point-in-time features only.
- Family-aware blocked splits.
- Date-blocked holdout.
- Era split, especially pre/post-2018.
- Calibration check.
- Null baseline printed.
- Feature importance or rule extraction.
- No direct page consumer until the artifact earns promotion.

Keep the render path light. Richer ML can run offline and write artifacts. Static pages should read JSON/parquet outputs, not train models.

### 4. Association And Context Rules

Some truths will be conditional and qualitative:

- "This pattern only matters when trend is broken."
- "This pattern works in country ETFs but not thematic baskets."
- "This phase is useful for drawdown risk but not return."
- "This China pathway is meaningful only in a policy-easing regime."

Association rules and subgroup scans are appropriate if they are governed by a trial budget and false-discovery control.

### 5. AI/LLM Digest Layer

LLMs should do the work humans are bad at and machines can audit afterward:

- Summarize clusters.
- Normalize leg narratives into tags.
- Detect duplicate candidate rules written with different wording.
- Generate review packets for Fable.
- Explain why a candidate might be mechanistically plausible.
- Identify contradictions between new candidates and existing truth artifacts.

LLMs should not:

- Create live scores.
- Upgrade authority class.
- Invent outcome labels.
- Rewrite point-in-time data.
- Make a candidate eligible without a statistical trial.

## Candidate Pattern Registry

Every discovered pattern should become a candidate before it becomes a truth.

Proposed candidate schema:

```json
{
  "candidate_id": "cycle_candidate_2026_07_06_001",
  "created_at": "2026-07-06",
  "created_by": "cycle_pattern_scan_v0",
  "owner_program": "cycle-intelligence",
  "candidate_type": "risk_hazard",
  "statement": "Late-cycle country clusters with high down-turn hazard have elevated 63d drawdown risk versus their own phase baseline.",
  "scope": {
    "families": ["country"],
    "regions": ["global"],
    "entities": "all_engine_backed"
  },
  "features": ["phase_v2", "hazard_3m_p", "trend_pass", "vol_regime"],
  "target": "max_drawdown_fwd_63d",
  "excluded_consumers": ["board_rank", "oracle_escalation", "position_sizing"],
  "trial_family": "cycle_pattern_v0",
  "prereg_ref": "data/cycle_pattern/pattern_trials.jsonl#trial_001",
  "status": "candidate",
  "notes": "Generated by lattice scan; not yet reviewed."
}
```

The registry should contain AI-proposed, human-proposed, and scan-proposed candidates, but all candidates go through the same evidence gates.

## Market Truth Artifact

The phrase "market truth" should mean a versioned proposition with evidence, allowed use, and falsifiers.

Proposed truth schema:

```json
{
  "truth_id": "cycle_truth_position_return_null_v1",
  "status": "promoted_null",
  "owner_program": "cycle-intelligence",
  "statement": "Generic cycle position does not provide a durable forward-return edge across the tested sector and country universe.",
  "effect_class": "null",
  "scope": {
    "families": ["sector", "country"],
    "regions": ["us", "global"],
    "sample": "monthly_point_in_time_backfill"
  },
  "target": "ret_fwd_21d_63d_126d",
  "evidence_ref": "research/cycle_masterplan/W04_KEYSTONE_VERDICT.md",
  "n_eff": "see evidence_ref",
  "ci_summary": "no stable return edge after PIT controls",
  "era_stability": "weak / decayed",
  "allowed_consumers": ["neuralweb_context", "cycle_docs", "research_factory"],
  "forbidden_consumers": ["board_rank", "oracle_escalation", "sector_central_direction_score"],
  "falsifiers": [
    "Fresh forward ledger shows stable OOS return edge with preregistered target and CI excluding null.",
    "Era split shows durable post-2018 lift with adequate breadth."
  ],
  "last_reviewed": "2026-07-06",
  "next_review_due": "2026-10-01"
}
```

Truth artifacts should include:

- Positive truths.
- Risk-only truths.
- Negative/null truths.
- Retired truths.
- Revision-optimistic truths.
- Display-only truths.
- Scored truths, if any earn that class.

This is how Neural Web becomes more intelligent without becoming more reckless. It remembers what not to believe.

## Promotion Ladder

Suggested statuses:

```text
candidate
registered
backtest_pass
backtest_fail
shadow
display
confirmer
scored
promoted_null
retired
superseded
```

Promotion requirements:

- `candidate`: generated by scan, AI, human, or cortex.
- `registered`: trial spec exists before evaluation.
- `backtest_pass`: passes preregistered historical test with caveats printed.
- `shadow`: live forward ledger starts; no page authority beyond research display.
- `display`: enough evidence to show as context.
- `confirmer`: may modify language, caution, or risk context, but not originate direction.
- `scored`: may enter a scored model only after Fable gates, calibration, and Signal Bus registration.
- `promoted_null`: a negative finding is durable enough to block future redundant builds.
- `retired`: evidence decayed or failed forward monitoring.
- `superseded`: replaced by a better scoped artifact.

The most important statuses are `promoted_null` and `retired`. A self-improving intelligence system needs memory of failed ideas, not just winners.

## How Neural Web Should Consume It

Neural Web needs a compact lobe output, not the whole feature lake.

Proposed `data/neuralweb/cycle_pattern_state.json`:

```json
{
  "as_of": "2026-07-06",
  "lobe": "cycle_pattern",
  "status": "display",
  "summary": {
    "cycle_sync": "moderate",
    "cycle_dispersion": "high",
    "hazard_bias": "down_hazard_pass_cells_elevated",
    "truth_conflicts": 1,
    "new_candidates": 4,
    "retired_candidates": 0
  },
  "active_truths": [
    {
      "truth_id": "cycle_truth_position_return_null_v1",
      "consumer_level": "context",
      "message": "Generic cycle position should not be treated as a return signal."
    }
  ],
  "current_pattern_firings": [
    {
      "pattern_id": "cycle_pattern_country_late_hazard_display_v0",
      "evidence_class": "display",
      "scope": "country_cycles",
      "message": "Several country cycles are late/overdue with elevated turn hazard; risk lens only."
    }
  ],
  "forbidden_actions": [
    "Do not originate Oracle escalations.",
    "Do not change board rank.",
    "Do not create entry signals from cycle position alone."
  ]
}
```

Then add a small summarizer in Neural Web / Mastermind context that can say:

- What cycle pattern truths are currently active.
- What they are allowed to influence.
- Which current page signals contradict them.
- Which candidate patterns are still only in shadow.

This creates a real Cycle lobe in Neural Web without letting it become another ungoverned signal stack.

## How Oracle Should Consume It

Oracle should be downstream of Cycle Pattern Intelligence.

Allowed Oracle uses:

- Annotate rotation episodes with cycle-context caveats.
- Show when institutional rotation is happening inside a historically risky cycle context.
- De-escalate language when a cycle truth says the pattern is unearned.
- Add "cycle context" to review packets for Fable.
- Use approved risk/hazard truths as context for rotation persistence, not as independent entry signals.

Forbidden Oracle uses:

- Oracle should not create or promote cycle truths.
- Oracle should not convert cycle position into entry timing.
- Oracle should not override Cycle truth artifacts.
- Oracle should not use unregistered pattern candidates in live state.

This is especially important because Oracle already handles institutional-money rotation. If Oracle also owns cycle truth discovery, every confluence will look tempting. That is how the system quietly rebuilds the ruled-down rotation-cycle entry confluence idea.

## How Sector Central Should Consume It

Sector Central should be the first practical UI consumer, but only through bounded permissions.

Near-term use:

- Add a Pattern Memory line to reasoning traces.
- Show active truth badges.
- Show analogue episodes on click.
- Use promoted risk truths to cap conviction or add caution language.
- Use promoted null truths to block misleading explanations.

Do not allow at first:

- Direction score upgrades.
- Board rank changes.
- Automatic overweight/underweight changes.
- Entry or exit triggers.

Example reasoning trace:

```text
Cycle: early repair, pos_v2 rising.
Pattern Memory: similar early-repair-with-strong-RS episodes historically had mixed return outcomes but lower false-turn risk when trend_pass=true. Evidence class: display.
Truth Guard: generic cycle position is not a return edge; do not upgrade direction from cycle alone.
```

That style makes the system smarter and humbler at the same time.

## How Page UX Could Evolve

### `sector_cycles.html`

Add a "Pattern Memory" drawer per sector/basket:

- Similar historical episodes.
- What happened after.
- Current active truth artifacts.
- Candidate pattern firings.
- Evidence class.
- Falsifiers.

Keep it behind progressive disclosure. The base page should remain readable.

### `sector_central.html`

Add cycle truth rows inside the existing reasoning stack:

- "Supports caution."
- "Blocks return-edge claim."
- "Analogue cluster: mixed."
- "Hazard artifact: pass/prior."

### `sector_central_china.html`

Add China-specific truth badges:

- Pathway-specific only where sample supports it.
- Policy/regime revision caveats.
- China-sector family boundaries.

### `markets.html`

Add a cross-market cycle memory view:

- Country cycle synchronization.
- Late-cycle clustering.
- Divergence between country cycle and sector/thematic cycles.
- Engine-backed versus curated status.

### `cycle.html`

Add a small "Cycle Truths" module:

- Current lobe status.
- Active broad cycle truths.
- Retired/null truths that prevent overclaiming.
- Link to Fable evidence files.

## Build Program

### W0 - Ruling And Scope Freeze

Deliverables:

- Fable ruling on ownership: Cycle-owned, Neural Web-consumed, Oracle-downstream.
- Named program: `cycle-pattern-intelligence`.
- Signal Bus draft entries.
- Consumer permissions matrix.

Acceptance:

- No live score path exists.
- Oracle cannot consume candidates.
- Cycle truth artifacts have allowed and forbidden consumers.

### W1 - Entity Registry And PIT Feature Lake

Deliverables:

- `data/cycle_pattern/entities.parquet`.
- `data/cycle_pattern/state_monthly.parquet`.
- `data/cycle_pattern/state_daily_live.parquet`.
- Stable entity ids across US sectors, US baskets, Nasdaq/Russell groups, China sectors, China baskets, country cycles, markets engine records, and flagship measured bands.
- Point-in-time version fields: `turn_def_version`, `engine_fingerprint`, `membership_version`, `source_artifact`, `basis`.

Acceptance:

- One query can return all engine-backed cycle states for a date.
- Curated/frame/opinion records are explicitly marked and excluded from model training by default.
- Baskets with unfrozen membership are flagged.

### W2 - Outcome Joiner

Deliverables:

- `data/cycle_pattern/outcomes.parquet`.
- Forward returns, excess returns, drawdowns, turn events, phase changes, cone hits, central call outcomes.
- Separate train/backfill outcomes from forward-ledger outcomes.

Acceptance:

- No outcome column exists in state rows.
- Date-blocked outcome joins are reproducible.
- Known W0.4 null can be reproduced from the lake.

### W3 - Candidate Grammar And Trial Budget

Deliverables:

- `config/cycle_pattern/candidate_grammar.yml`.
- `data/cycle_pattern/pattern_trials.jsonl`.
- Candidate generator for lattice scans.
- Duplicate/near-duplicate detector.

Acceptance:

- Every scan has a trial family and trial budget.
- Candidate count is printed before evaluation.
- False-discovery plan is attached before results.

### W4 - First Discovery Batch

Run only low-complexity discovery first.

Targets:

- Drawdown risk.
- Turn hazard.
- Cone miss risk.
- False repair risk.
- Phase persistence.

Do not optimize broad forward returns.

Deliverables:

- First candidate batch.
- Pass/fail/kill packet.
- Truth artifacts for known nulls and known pass/prior hazard cells.

Acceptance:

- The system rediscovers the W0.4 null instead of contradicting it.
- The system rediscovers hazard pass/prior distinctions.
- At least one negative/null truth artifact is stored.

### W5 - Motif And Analogue Engine

Deliverables:

- Shape-window builder for 3m/6m/9m/12m histories.
- Nearest-neighbor analogue retrieval.
- Episode cards for current pattern firings.
- Cluster summary generator.

Acceptance:

- Analogue output includes n, dates, outcomes, era split, evidence class, and caveats.
- No analogue output can change live scores.
- AI summaries cite machine-produced evidence ids.

### W6 - Research Factory Adapter

Deliverables:

- Adapter that registers cycle pattern candidates into Research Factory.
- Review queue for Fable.
- Challenge queue for contradiction/null testing.
- Retirement monitor.

Acceptance:

- Candidate lifecycle is not owned by a page builder.
- Promotions and retirements leave durable artifacts.
- Failed candidates remain queryable.

### W7 - Neural Web Lobe

Deliverables:

- `data/neuralweb/cycle_pattern_state.json`.
- Mastermind context summarizer.
- Signal Bus registration.
- Spine index entry for cycle truth artifacts and pattern firings.

Acceptance:

- Neural Web can summarize active cycle truths and current pattern firings.
- Neural Web cannot originate new cycle truths.
- Forbidden consumers are enforced in the adapter.

### W8 - Page Consumers

Deliverables:

- `sector_cycles.html`: Pattern Memory drawer.
- `sector_central.html`: truth badges and caution/context rows.
- `sector_central_china.html`: China-specific truth/pathway badges.
- `markets.html`: cross-market cycle pattern summary.
- `cycle.html`: broad cycle truth module.

Acceptance:

- Every visible claim has evidence class.
- Pattern Memory is progressive disclosure, not a new wall of text.
- Null truths are displayed as guardrails where relevant.

## First Candidate Truth Seed List

These should be encoded as seed truths or candidate truths on day one:

1. Generic cycle position is not a durable forward-return signal across the tested sector/country universe.
2. Cycle phase is more defensible as a risk/context lens than a return forecast.
3. Phase-keyed drawdown behavior exists but has unintuitive/inverted structure and possible era decay, so it needs careful scoping.
4. Up 1m turn hazard has stronger evidence than up 3m/6m in the current hazard model.
5. Down 1m/3m/6m turn hazard has stronger evidence in the current hazard model.
6. Conditional phase-by-regime cells are useful research candidates but revision-optimistic until regime inputs are point-in-time.
7. Lead-lag phase interactions should remain a synchronization display, not an interaction engine.
8. Rotation-cycle entry confluence should remain blocked until live forward logs mature.
9. Central fuser calls are useful future outcomes but are not yet learned truth.
10. Narrative/DNA files are mechanism material, not statistical evidence until normalized and linked to outcomes.

This seed list matters because the system should begin with humility. It should first encode what it already knows not to overclaim.

## Anti-Mining Law

Cycle Pattern Intelligence will be tempting because the search space is enormous. The law should be explicit:

- Every search family gets a preregistered trial budget.
- Every batch prints number of candidates tested.
- Every result has a null baseline.
- Date-blocked holdouts are mandatory.
- Entity-family holdouts should be used where feasible.
- Era splits are mandatory for any artifact that wants authority.
- Revised macro labels must carry revision caveats.
- LLM summaries cannot be evidence.
- Sample-size floors apply before display.
- Duplicate patterns collapse into one family.
- Dead patterns stay dead unless a new preregistered trial reopens them.

If this law is not built first, AI will find patterns that look amazing and teach the system the wrong lessons.

## Thematic Basket Caveat

Thematic baskets are a valuable edge surface, but also the easiest place to fool the system.

Before treating basket history as high-authority:

- Freeze basket membership versions.
- Store basket construction rules.
- Mark whether current membership was applied backward.
- Distinguish investable ETF/proxy series from synthetic baskets.
- Separate broad sector ETFs from hand-curated themes.
- Require sample-size floors by basket family.

Until then, basket patterns can be display/research candidates, but should not become high-authority truth artifacts.

## China Caveat

China cycles deserve their own family rules.

Reasons:

- Policy and liquidity regimes can dominate sector cycle mechanics.
- Pathway odds are available only for limited sectors.
- Data histories and sector definitions differ from US ETFs.
- Revision and availability constraints can be more severe.

China Sector Central should therefore consume China-specific truth artifacts, not generic US sector truths unless a transfer test explicitly passes.

## ML And AI Role Split

ML is for candidate scoring and recurrence detection.

AI is for compression, explanation, tag extraction, and review packet generation.

Statistics is the court.

Fable is the judge.

Neural Web is the memory and context surface.

Oracle is a downstream rotation consumer.

Cycle remains the owner of cycle measurement and cycle truth artifacts.

## Practical Implementation Notes

Implementation should reuse existing builders rather than create a second cycle engine.

Likely files to extend or add:

- `engine/sector_cycles.py`: expose a stable state-row export helper if needed.
- `engine/china_sector_cycles.py`: same for China.
- `engine/country_cycles.py`: same for country cycles.
- `scripts/build_cycle.py`: export measured flagship band rows.
- `scripts/build_markets.py`: mark engine-backed versus curated market rows.
- `engine/cycle_forward_log.py`: keep live stamps flowing.
- `scripts/grade_promises.py`: reuse promise family concepts.
- `scripts/fit_cycle_hazard.py`: reuse hazard panel/model conventions.
- `config/synapse.yml`: register CPI artifacts.
- `docs/SIGNAL_BUS.md`: document artifact ownership and consumers.
- `engine/neuralweb/world_state.py`: add cycle pattern lobe input.
- `engine/neuralweb/mastermind_context.py`: add cycle pattern summarizer.
- `research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md`: connect candidate lifecycle.

Do not put training code on the static page render path. The pages should consume artifacts.

## What Fable Should Decide

Fable should decide five things:

1. Approve Cycle Pattern Intelligence as a Cycle-owned lobe, not Oracle-owned.
2. Approve the feature-lake-first sequence before any new ML model.
3. Approve truth artifacts as durable memory with revocable authority.
4. Approve Research Factory as the candidate lifecycle owner.
5. Approve page consumers only after the lobe can attach evidence class and forbidden-consumer rules.

## Bottom Line

The opportunity is real. The current cycle system already contains enough historical structure that humans will miss relationships that statistical and ML methods can surface.

But the breakthrough is not "let AI read all the charts." The breakthrough is to give AI and ML a governed substrate:

- one canonical cycle state lake,
- one outcome spine,
- one candidate registry,
- one truth artifact format,
- one promotion ladder,
- one Neural Web lobe,
- and strict consumer permissions.

That turns cycle history into institutional memory. It lets the system learn patterns, remember nulls, prune weak ideas, and present market truths without pretending that every recurring shape is an edge.

