# Neural Web Next-3 Lobe Upgrade Plan for Claude

Prepared by Codex, 2026-07-06.

Status: research handoff and build plan. Additive document only. No scoring authority is granted here.

Audience: Claude/Fable/Sonnet build lanes.

## 0. Boundary and Selection Ruling

This is the second-pass lobe plan. It deliberately excludes the prior top-three power-up set:

1. Oracle / Rotation Intelligence.
2. US Entry Intelligence / Entry Stack.
3. Long-Hold Thesis Layer.

Those three already have their own Codex report in `research/NW_TOP3_LOBE_POWER_UP_ANALYSIS_BY_CODEX.md`. This document selects the next three most valuable upgrade targets from what is already present in the repo, then lays out how to make them much more powerful without breaking the house laws.

Selected next three:

| Rank | Lobe | Why this is next | Current status in repo | Core upgrade theme |
|---|---|---|---|---|
| 4 | Short-Side / Breakdown Intelligence | Directly improves drawdown control by finding names the long book should avoid or distrust. | Chartered, Phase-0 summary built, direction-aware short-side grader exists. | Convert Phase-0 avoid evidence into live accruing avoid species, without pretending it is a shorting program. |
| 5 | Options Entry Intelligence | Adds microstructure and pressure-map context to entries the system already likes. | Active state table, gate file, NW wiring, confluence edges, cortex tools, all gates still building history. | Turn display options state into calibrated path-quality and de-escalation evidence. |
| 6 | Decision-Quality / Operator Self-Model | Measures whether the human-machine loop is learning, which can compound every lobe. | Operator action ledger instrumentation exists, local ledger absent, no grader yet. | Build a PM process analytics loop: alert exposure -> action -> outcome -> counterfactual. |

Important non-selection: L3 Dispersion is real and useful, but I do not pick it as a standalone top-three upgrade here. The live artifact is narrow (`data/dispersion/regime.json`, display chip, `gross_mult_live=1.0`) and its highest value is as a shared regime conditioner inside the three selected lobes, not as another isolated build program. Claude should still run `DISP-GATE-1`, but dispersion should become a context axis for short-side, options, and decision-quality outcomes before anyone spends major design bandwidth on a standalone dispersion desk.

## 1. Evidence Census

Closest authority and artifact files read:

| Area | Evidence |
|---|---|
| Future lobe taxonomy | `research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md` defines lobe vs rail vs wave, then ranks short-side, exit/trim, and dispersion as Tier 1 candidates, with decision-quality gated but high ROI. |
| Build authority | `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` charters L1 short-side and L3 dispersion, ships L4 instrumentation only, and records all waves shipped on 2026-07-06. |
| Short-side charter | `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` sets permanent scope: avoid/de-risk lens, not shorting execution. |
| Short-side prereg | `research/short_side/BD_PHASE0_PREREG.md` freezes BD-1/BD-2/BD-3, grading, controls, and interesting-read guide. |
| Short-side current output | `data/research/breakdown_events_summary.json` exists; `data/research/breakdown_events.parquet` is Mac-local and absent in this worktree. |
| Options masterplan | `research/OPTIONS_NW_ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` says options should be entry quality, not direction, and active waves shipped. |
| Options state/gate | `data/options_entry/state.parquet` exists, 403 rows x 28 columns. `data/options_entry/gate.json` exists, 950 stamped ledger rows, all families `building_history`, `scored=false`, `weight=0.0`. |
| Options contracts | `config/synapse.yml` registers `options-entry-state` as display and `options-entry-gate` as shadow; both feed Mastermind context. |
| Decision-quality instrumentation | `admin/actions.py`, `admin/server.py`, `tests/test_admin_actions.py`, `config/synapse.yml`, and `docs/SIGNAL_BUS.md` register `operator-action-ledger` as gitignored local infrastructure. |
| Decision-quality grader template | `engine/btc_override_ledger.py` is the closest working override-grading pattern. |
| Forward-closure reality | `docs/GRADING_CLOSURE.md` says qledger is closed with 9,069 logged and 2,815 graded, while btc override has 5 logged and 0 graded; operator action ledger has no local rows. |

## 2. First-Principles Frame

A lobe is not "a collection of indicators." A real lobe owns:

1. An objective function.
2. A label set.
3. Its own failure modes.
4. A forward accrual plan.
5. A path from display/context to shadow to possible authority.

Institutional upgrade pattern:

1. Define the decision being improved.
2. Define the event population before seeing results.
3. Attach all evidence at the event timestamp.
4. Grade path outcomes with the same function used in backtest and live accrual.
5. Keep the decision right separate from the measurement right.

That matters here because the next leap is not a cleverer headline score. It is to build event-level training records where the system can learn:

- Which longs should be avoided.
- Which entries have cleaner paths.
- Which alerts actually change good decisions.
- Which lobe warnings create false negatives.
- Which evidence improves drawdown without killing upside.

## 3. Lobe 4: Short-Side / Breakdown Intelligence

### 3.1 What It Is

Short-Side / Breakdown Intelligence is the mirror discipline for a long-biased reversal system. Its real objective is not "find shorts." Its objective is:

> Find distribution, failed-rally, and topping conditions that make a long entry lower quality, or make an existing long deserve less trust.

This lobe improves the system by saying "do not be long here" before it ever says "be short here." The repo already encodes that distinction in `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md`: a species may earn as AVOID without earning as SHORT.

### 3.2 Current Repo State

Built:

- Charter: `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md`.
- Prereg: `research/short_side/BD_PHASE0_PREREG.md`.
- Builder: `scripts/research/dump_breakdown_events.py`.
- Direction-aware short grader: `engine/grading.py` exposes `terminal_state_short`.
- Summary: `data/research/breakdown_events_summary.json`.

Not built or not present here:

- Live forward ledger for breakdown species.
- Site chip or board consumer.
- Phase-1 prereg for any specific avoid species.
- Mac-local parquet in this worktree (`data/research/breakdown_events.parquet` absent here).
- Short execution, borrow, locate, squeeze, or hedge machinery. That absence is correct.

### 3.3 What The Phase-0 Summary Actually Says

`data/research/breakdown_events_summary.json`:

| Definition | Episodes | 21d long stop | 21d matched control stop | Long stop gap | 21d short favorable | Paired read |
|---|---:|---:|---:|---:|---:|---|
| BD-1 | 1,330 | 42.38% | 41.80% | +0.58pp | 21.51% | Weak avoid evidence, not a short case. |
| BD-2 | 19,891 | 51.46% | 41.80% | +9.66pp | 31.31% | Strong avoid evidence, not symmetric short evidence. |
| BD-3 | 5,553 | 58.61% | 41.80% | +16.81pp | 37.53% | Strongest avoid evidence; still avoid-first. |

At 126d:

- BD-2 long stop rate is 70.68% vs 65.38% control, +5.30pp.
- BD-3 long stop rate is 74.07% vs 65.38% control, +8.69pp.
- Short favorable rates at 126d are near 26%, while long stop rates are above 70%.

Interpretation:

- The lobe has evidence that some breakdown definitions mark bad long conditions.
- The same evidence does not justify a shorting program.
- The institutional move is to build an avoid/de-risk lobe, not a short-alpha lobe.

### 3.4 First-Principles Diagnosis

The system already has a powerful long-entry bias. A reversal system tends to get hurt in three places:

1. It buys a real washout inside a broader distribution regime.
2. It buys a failed rally because the first bounce looks like repair.
3. It lets a long thesis survive after the path has turned into supply absorption.

Short-side intelligence should therefore label "long path quality deteriorates" rather than "stock goes down." That is a different target:

- Bad-long label: higher stop rate, lower liftoff rate, more dead money, worse post-entry path.
- Short label: favorable downside path after entry, net of adverse squeeze.
- Hedge label: improves book-level drawdown after costs, borrow, and squeeze risk.

The current repo already implies the correct split. BD-2 and BD-3 look like bad-long detectors. They do not look like clean short execution signals.

### 3.5 What Institutions Would Do

An institutional risk desk would not let the alpha team invert a bottom signal and call it a short model. They would:

1. Run a separate avoid-long book.
2. Measure false avoids as opportunity cost.
3. Measure true avoids as drawdown saved.
4. Separate distribution signals from borrow/short execution signals.
5. Add squeeze, borrow, locate, and liquidity only after the avoid model earns a separate shorting mandate.

They would also put this lobe upstream of sizing and entry trust, not directly into short exposure.

### 3.6 Five Most Important Upgrades

#### Upgrade 1: Phase-1 Avoid Species Ledger for BD-2 and BD-3

Build:

- `research/short_side/BD_PHASE1_AVOID_PREREG.md`.
- `scripts/short_side_forward_ledger.py` or equivalent nightly-safe writer.
- `data/short_side/bd_avoid_forward.jsonl` or per-species JSONL under a declared single-writer path.
- `scripts/grade_short_side_forward.py` using the same long and short terminal-state functions as Phase-0.

Training labels:

- `avoid_success_21`: event long stop or dead-money worse than matched baseline.
- `avoid_false_positive_21`: event would have clean-liftoffed if avoided.
- `short_success_21`: short favorable before adverse.
- `avoid_only`: bad-long label true while short-success false.

Claude build notes:

- Start only with BD-2 and BD-3. BD-1 is too weak as currently summarized.
- The first live artifact should say "avoid/de-risk candidate," not "short."
- Include matched controls by ticker/year or ticker/regime.
- Do not add a board chip until the first forward rows exist and the display vocabulary is reviewed.

Expected improvement:

- Fewer bad long entries.
- Cleaner separation between "bounce worth taking" and "bounce is a failed reclaim."
- More honest drawdown control than another after-the-fact exit rule.

#### Upgrade 2: Species Expansion From The Inverted Entry Ladder

Build:

- Phase-1 preregs for the next 4 cheap species:
  - S4-minus Two-Clock Rollover.
  - S5-minus Coiled Breakdown.
  - S7-minus RS Deterioration Before Price.
  - S13-minus Within-Sector Leader Fade.
- Each should have one frozen threshold set, one label family, and one control method.

Training labels:

- Same avoid labels as Upgrade 1.
- Add `species_id`, `evidence_family`, `mechanism`, and `horizon_class`.

Claude build notes:

- Do not bulk-register all 13 inverted species at once.
- Use BD-2/BD-3 as calibration anchors.
- Let underpowered species park without shame.
- Keep EDGAR-gated species out until their PIT joins are cheap and clean.

Expected improvement:

- The lobe stops being three hard-coded definitions and becomes an organized breakdown grammar.
- Claude can compare mechanisms instead of comparing indicator variants.

#### Upgrade 3: Multi-Evidence Conditioning Without Composite Fusion

Build:

- A conditioning report, not a score:
  - BD event x options top-risk.
  - BD event x dispersion state.
  - BD event x froth/fragility.
  - BD event x sector relative weakness.
  - BD event x defensive-bid regime.
- Output: `research/short_side/BD_CONDITIONING_REPORT.md` plus summary JSON.

Training data:

- `data/research/breakdown_events_summary.json` and Mac-local event parquet.
- `data/options_entry/state.parquet`.
- `data/dispersion/regime.json` for live, reconstructed historical dispersion for study.
- `site/basketdata/oracle_state.json` or sector-relative artifacts only as read-only context.

Claude build notes:

- No fused score.
- No "BD + options = stronger short" claim.
- Report condition-specific base rates and false-avoid costs.
- If dispersion is unavailable historically, flag the basis gap instead of filling it with current state.

Expected improvement:

- Turns short-side from a price-only lobe into a context-aware de-risk system.
- Finds the exact conditions where avoid warnings are most useful.

#### Upgrade 4: Avoided-Loss and Missed-Upside Counterfactual Ledger

Build:

- `scripts/research/short_side_avoid_counterfactual.py`.
- For every BD event that overlaps a historical buy/watch/fire, compute:
  - entry that would have been taken,
  - path if taken,
  - path if skipped,
  - next eligible re-entry date,
  - missed clean-liftoff rate,
  - max drawdown avoided,
  - opportunity cost.

Training labels:

- `avoidable_loss`.
- `missed_upside`.
- `reentry_quality_after_skip`.
- `avoid_net_utility` under a frozen utility function.

Claude build notes:

- Utility should be conservative and published before run.
- The point is not to make the lobe look good. The point is to price the tradeoff.
- Print nulls and missed opportunities.

Expected improvement:

- Claude can decide whether avoid warnings are actually worth obeying.
- The lobe becomes decision-economic, not just statistically interesting.

#### Upgrade 5: Short Execution Firewall and Later Hedge Lab

Build now:

- A constitution note in the short-side docs:
  - AVOID permission.
  - TRIM permission.
  - HEDGE research permission.
  - SHORT execution forbidden until new charter.

Build later:

- If avoid rows earn enough live evidence, a separate hedge lab with:
  - borrow/locate availability,
  - squeeze risk,
  - option-implied borrow/put spread cost,
  - gap risk,
  - portfolio hedge effect,
  - execution cost.

Training labels later:

- `hedge_helped_book_drawdown`.
- `short_squeeze_adverse`.
- `borrow_cost_exceeded_edge`.

Expected improvement:

- Prevents the most dangerous failure mode: turning a good avoid lens into a bad short book.
- Gives the system a clean future route if the evidence ever supports hedging.

## 4. Lobe 5: Options Entry Intelligence

### 4.1 What It Is

Options Entry Intelligence is not a buy signal. Its real objective is:

> Given that price, setup, or Neural Web already likes an entry, does options state make the path cleaner or more fragile?

The repo already says this in `research/OPTIONS_NW_ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`: options should improve durability first, confidence second, and direction-from-flow stays constrained until the tape pipeline earns it.

### 4.2 Current Repo State

Built:

- State fusion: `engine/options_entry_state.py`.
- Builder: `scripts/build_options_entry_state.py`.
- Gate: `scripts/validate_options_entry.py`.
- State artifact: `data/options_entry/state.parquet`.
- Gate artifact: `data/options_entry/gate.json`.
- NW adapter and context:
  - `engine/neuralweb/query.py`.
  - `engine/neuralweb/confluence.py`.
  - `engine/neuralweb/world_state.py`.
  - `engine/neuralweb/mastermind_context.py`.
- Synapse registrations for options state, gate, skew, ivspread, flow.

Current data:

- State parquet: 403 rows x 28 columns.
- Gate JSON: 950 stamped rows, all families `building_history`, `scored=false`, `weight=0.0`.
- `iv_rank_252` and `iv_rank_5d_chg`: 0 non-null, explicitly structural until IV backfill.
- `pin_risk`: 0 non-null in the current state output.
- `ivspread_rel`: 355 non-null.
- `skew`: 386 non-null.
- `net_doi`: 348 non-null.
- `fresh_premium_mn`: 310 non-null.
- `gamma_regime`: 385 non-null but structurally constant per-name caveat.
- S-VOI currently has 42 condition rows and 4 base rows, not ready.
- S-IVR, S-DOI, S-IVSPREAD-F, S-SKEW_DECEL, S-TOP_RISK, S-PIN_RISK, S-VOI2 are all building history.

### 4.3 First-Principles Diagnosis

Options data is a pressure map. It tells us:

1. Where the crowd has paid for upside or downside.
2. Where dealers may pin, accelerate, or dampen spot.
3. Whether fear is rising or decelerating.
4. Whether an entry is likely to chop, stop-run, or lift cleanly.
5. Whether a long setup is contradicted by crash/put demand.

It does not naturally tell us "buy." The correct target label is path quality:

- stop-out probability,
- clean liftoff probability,
- dead-money probability,
- post-entry max favorable excursion,
- wall-touch behavior,
- OPEX pin/chop risk.

The repo has most of the plumbing but not enough time/history or stamp completeness to grant authority.

### 4.4 What Institutions Would Do

An institutional volatility desk would not let a raw GEX board steer stock selection. It would build:

1. A point-in-time options feature store.
2. Open/close and buyer/seller signing where licensed and measured.
3. A volatility-surface quality audit.
4. Barrier and wall-aware path simulations.
5. Outcome joins against the actual entry ledger.
6. Separate de-escalation rights from positive selection rights.

The desk would also rank "do not enter here" higher than "this option flow is bullish," because the former is easier to measure and less vulnerable to signing error.

### 4.5 Five Most Important Upgrades

#### Upgrade 1: Complete Stamp Coverage and Historical Backfill

Build:

- Finish the IV-rank backfill path so `iv_rank_252` and `iv_rank_5d_chg` become usable.
- Populate `pin_risk` from OPEX plus long gamma plus near-wall/max-pain distances.
- Ensure `opt_ivspread_rel`, `opt_skew`, `opt_skew_5d_chg`, wall distance, and OPEX fields are present on the exact board ledger rows the gate reads.
- Extend ThetaData single-name history where already chartered, with manifest and R2 storage.

Training labels:

- No new target labels yet. This upgrade improves feature completeness.

Claude build notes:

- Do not build a score.
- Do not flip root flow-direction authority.
- Add a coverage audit:
  - feature non-null by date,
  - feature non-null by ticker,
  - stale source count,
  - bucket readiness forecast.

Expected improvement:

- Converts options from "interesting but sparse" into a usable feature store.
- Shortens time to first meaningful gate read.

#### Upgrade 2: Path-Quality Harness v2

Build:

- Extend `scripts/validate_options_entry.py` into a cleaner harness report:
  - bucket readiness,
  - path outcomes,
  - false caution,
  - false confirmation,
  - ticker/sector cluster awareness,
  - OPEX period splits,
  - dispersion state splits.
- Output:
  - `data/options_entry/gate.json` remains the machine gate.
  - Add `research/options/OPTIONS_ENTRY_PATH_QUALITY_REPORT.md`.

Training labels:

- `post_cushion_breach`.
- `terminal_state_clean8_21`.
- `fwd_mfe_5`, `fwd_mfe_21`.
- `fwd_ret_5`, `fwd_ret_21`.
- `dead_money_21`.
- `wall_touch_before_fixed_stop`.

Claude build notes:

- Use A10 ledger primitives where they exist.
- If a label is not already in the ledger, either compute it from raw closes under a frozen method or leave it out.
- Print bucket sample sizes even when not ready.
- The report can be descriptive; the gate JSON remains strict.

Expected improvement:

- Options evidence becomes legible to Claude and the operator.
- The system can learn which options states reduce stop-outs rather than merely displaying them.

#### Upgrade 3: Pressure-Map Entry Cards

Build:

- Add a compact pressure-map block to candidate context and, later, the relevant board card:
  - nearest put wall,
  - nearest call wall,
  - gamma flip distance,
  - OPEX days,
  - pin risk,
  - IV rank / IV change,
  - skew direction,
  - ivspread direction.

Allowed verbs:

- confirms,
- contradicts,
- cautions,
- context.

Forbidden:

- buy,
- rank,
- amplify,
- size,
- short.

Training or calibration:

- Track whether pressure-map cautions would have avoided stop-outs or merely scared away winners.

Claude build notes:

- Start in Mastermind context and cortex read tools before making heavier UI.
- For each field, include evidence quality and as-of.
- If `pin_risk` is null, say unavailable rather than neutral.

Expected improvement:

- Better stop placement.
- Fewer entries directly into walls or OPEX pin zones.
- More explainable entry timing.

#### Upgrade 4: Options Top-Risk Handoff to Short-Side

Build:

- A context-only join between options top-risk buckets and short-side BD events:
  - rising skew,
  - puts-rich ivspread,
  - near call wall with fading call demand,
  - high 0DTE/short-dated premium concentration,
  - negative or fragile gamma context where reliable.
- Output a report, not a score:
  - `research/options/OPTIONS_SHORT_SIDE_HANDOFF_REPORT.md`.

Training labels:

- For BD events: avoid-success and false-avoid.
- For board fires: stop-out and clean liftoff.
- For options top-risk: flagged vs unflagged path quality.

Claude build notes:

- The handoff should strengthen de-escalation only.
- Never let options originate a short.
- If skew-decel has skeptical prior, preserve that skepticism in the readout.

Expected improvement:

- Short-side gets better context.
- Options gets a clearer job: find fragility around long setups.

#### Upgrade 5: Options Analogue Library

Build:

- A historical nearest-neighbor research artifact over options states:
  - features: IV rank, skew, skew change, ivspread, OI slope, wall distances, OPEX days, gamma/flip context, dispersion state.
  - outcomes: 5d/21d return, MFE, stop breach, wall touch, clean liftoff.
- Output:
  - `data/options_entry/analogues_summary.json`.
  - `research/options/OPTIONS_ANALOGUE_LIBRARY.md`.

Training/calibration:

- This is not a model at first.
- It is retrieval: "when entries looked like this, what happened?"
- Later, a simple calibrated hazard model can be tested against the same labels.

Claude build notes:

- Start on ETF/sector roots where historical options data is already stronger.
- Only move to single-name cross-section when W-E0 history is complete enough.
- Keep retrieval display-only.

Expected improvement:

- Claude can reason from precedent instead of isolated feature values.
- Operator trust improves because the system can show analogues and base rates.

## 5. Lobe 6: Decision-Quality / Operator Self-Model

### 5.1 What It Is

Decision-Quality / Operator Self-Model is the lobe that measures the human-system loop.

Objective:

> When the system surfaced evidence and the operator acted, dismissed, overrode, or snoozed it, did that decision improve outcomes?

This is not a market alpha lobe at first. It is an accuracy and governance lobe. It tells the system which warnings matter, which surfaces change decisions, and where the operator adds or subtracts value.

### 5.2 Current Repo State

Built:

- `admin/actions.py` appends rows to `data/operator/action_ledger.jsonl`.
- `admin/server.py` has `/api/actions`.
- `admin/static/app.js` posts actions from the admin UI.
- `tests/test_admin_actions.py` covers append behavior and HTTP route.
- `config/synapse.yml` registers `operator-action-ledger`.
- `docs/SIGNAL_BUS.md` lists the artifact.
- `engine/btc_override_ledger.py` is a grading template.

Current reality:

- `data/operator/action_ledger.jsonl` is absent in this worktree, which is expected for gitignored server-local data.
- There are no synapse consumers.
- There is no general grading harness.
- There is no action exposure joiner.
- The repo has useful counterfactual material nearby:
  - qledger: 9,069 claims, 2,815 graded.
  - US board ledger: 950 logged and graded.
  - btc override ledger: 5 logged, 0 graded, but useful template.

### 5.3 First-Principles Diagnosis

Every lobe has two accuracy questions:

1. Did the lobe predict the outcome?
2. Did the lobe improve the actual decision?

Most systems only measure the first. Institutions measure the second because capital is allocated by people, processes, and constraints. A warning that is statistically decent but never changes a decision has low operational value. A warning that prevents one large bad entry may have high value even if it is rare.

The missing object is the DecisionPacket:

```text
DecisionPacket =
  timestamp
  surface
  candidate / ticker / lobe
  evidence shown to operator
  system recommendation / context
  operator action
  operator reason
  latency
  outcome horizon
  counterfactual
```

Once this exists, the system can ask:

- Which lobe warnings are acted on?
- Which warnings are ignored but later proved useful?
- Which overrides saved money?
- Which overrides were costly?
- Which surfaces create alert fatigue?
- Which evidence should be shown earlier, later, smaller, or not at all?

### 5.4 What Institutions Would Do

An institutional PM platform would build this as process analytics, not surveillance. The strongest version is blame-free and decision-economic:

1. Log every decision opportunity, not just actions taken.
2. Tie each action to the exact evidence visible at the time.
3. Grade acted and dismissed paths.
4. Separate operator skill from signal quality.
5. Use the results to improve process, not to produce another noisy alpha score.

This is how a real desk gets better: not by remembering anecdotes, but by measuring which decision protocols work.

### 5.5 Five Most Important Upgrades

#### Upgrade 1: Action Exposure Joiner

Build:

- `scripts/build_operator_exposure_log.py`.
- Output:
  - `data/operator/exposure_log.jsonl` or `data/operator/exposure_summary.json`.
- Join:
  - alerts emitted,
  - board candidates,
  - experiment surfaces,
  - operator action rows,
  - evidence snapshot IDs,
  - lobe context available at the time.

Training labels:

- `seen_no_action`.
- `acted`.
- `dismissed`.
- `overrode`.
- `snoozed`.
- `latency_bucket`.

Claude build notes:

- The action ledger only logs actions. The exposure log must also know what the operator could have acted on.
- Without exposures, "dismissed" is undercounted and action-rate metrics are biased.
- Start with admin alerts and experiments, then expand to board candidates.

Expected improvement:

- Turns sparse action rows into a denominator-aware behavioral dataset.

#### Upgrade 2: Counterfactual Action Grader

Build:

- `engine/operator_action_grader.py`.
- `scripts/grade_operator_actions.py`.
- Output:
  - `data/operator/action_grades.json`.
  - `research/operator/OPERATOR_ACTION_GRADING_REPORT.md`.

Grade:

- acted vs not acted,
- override vs system default,
- dismissed vs later outcome,
- snoozed vs latency cost,
- lobe warning present vs absent.

Training labels:

- `decision_helped`.
- `decision_hurt`.
- `decision_neutral`.
- `override_saved`.
- `override_cost`.
- `missed_warning`.
- `alert_noise`.

Claude build notes:

- Reuse the Wilson/bootstrap style from `engine/btc_override_ledger.py`.
- Do not grade rows before their horizon matures.
- Use conservative horizons:
  - 5d for tactical alerts,
  - 21d for entries,
  - 63d or 126d for thesis/process decisions.
- Store unresolved rows explicitly.

Expected improvement:

- The operator gets a real feedback loop.
- The system learns which warnings deserve attention budget.

#### Upgrade 3: Structured Reason Taxonomy

Build:

- Extend action capture with optional structured reason codes:
  - price_action,
  - macro_regime,
  - options_contradiction,
  - short_side_warning,
  - thesis_break,
  - position_risk,
  - data_quality,
  - timing,
  - other.
- Keep `direction_note` as free text, but add `reason_codes`.

Training labels:

- `reason_code`.
- `reason_outcome`.
- `reason_lobe_alignment`.

Claude build notes:

- Do not use an LLM to invent the reason.
- If using an LLM later, it may classify the operator's written note into the taxonomy for review, but the raw note remains source of truth.
- Keep note cap and privacy constraints.

Expected improvement:

- Makes decision review faster.
- Shows whether specific reasoning patterns help or hurt.

#### Upgrade 4: Lobe Impact Attribution

Build:

- `scripts/research/lobe_decision_impact.py`.
- Report per lobe:
  - how often it appeared in a decision packet,
  - how often it changed action,
  - outcomes when followed,
  - outcomes when ignored,
  - false-positive burden,
  - stale or missing evidence rate.

Training labels:

- `lobe_present`.
- `lobe_followed`.
- `lobe_ignored`.
- `lobe_helped_decision`.
- `lobe_hurt_decision`.

Claude build notes:

- Start with short-side and options because they have explicit caution/de-escalation roles.
- Do not compare lobes by raw return. Compare by decision utility and drawdown avoided.
- Include display-only status in every row.

Expected improvement:

- The repo can prioritize upgrades based on actual decision impact.
- Weak but noisy surfaces can be retired or made quieter.

#### Upgrade 5: Decision Protocol and Weekly Review Artifact

Build:

- `research/operator/DECISION_QUALITY_PROTOCOL.md`.
- `scripts/render_operator_weekly_review.py`.
- Output:
  - top helpful warnings,
  - top missed warnings,
  - costly overrides,
  - valuable overrides,
  - stale/noisy surfaces,
  - action latency summary,
  - next-week process rule.

Training/calibration:

- This is process training, not model training.
- The weekly review creates human feedback and a stable loop for later model calibration.

Claude build notes:

- Keep it short enough to be read weekly.
- Avoid shaming language.
- Use decision packets, not anecdotes.

Expected improvement:

- Makes learning continuous.
- Converts the operator from memory-driven to ledger-driven.

## 6. Cross-Lobe Upgrade: DecisionPacket Schema

The strongest shared build is a canonical event schema that all three lobes can emit or join.

Proposed minimal schema:

```json
{
  "packet_id": "string",
  "ts": "ISO-8601",
  "as_of": "YYYY-MM-DD",
  "ticker": "string|null",
  "surface": "string",
  "lobe": "short_side|options_entry|decision_quality|...",
  "event_type": "string",
  "evidence_refs": ["artifact:path#key"],
  "display_only": true,
  "authority_level": "display|shadow|infrastructure",
  "operator_action": "acted|dismissed|overrode|snoozed|null",
  "operator_reason_codes": [],
  "outcome_horizon_d": 21,
  "outcome_status": "unresolved|graded",
  "outcome": {}
}
```

Why this matters:

- Short-side can emit avoid events.
- Options can emit pressure-map contradictions.
- Decision-quality can join what was shown and what the operator did.
- Claude can later analyze lobe interactions without bespoke joins each time.

Non-goal:

- This is not a score and not a trading action. It is a measurement substrate.

## 7. Claude Build Plan

Recommended sequencing:

### PR-A: Short-Side Phase-1 Avoid Prereg

Files:

- `research/short_side/BD_PHASE1_AVOID_PREREG.md`.
- Maybe update `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` status log.

Deliverable:

- Freeze BD-2 and BD-3 avoid-only live accrual definitions.
- Define labels, controls, and false-avoid utility.

Review:

- Opus stats review before any live ledger code.

### PR-B: Short-Side Live Ledger and Grader

Files:

- `scripts/short_side_forward_ledger.py`.
- `scripts/grade_short_side_forward.py`.
- `engine/grading.py` only if needed, but prefer existing functions.
- `config/synapse.yml`.
- `docs/SIGNAL_BUS.md`.
- Tests with synthetic paths.

Deliverable:

- Forward JSONL or summary artifact.
- No site chip yet.

### PR-C: Options Coverage Audit and Stamp Completion

Files:

- `scripts/audit_options_entry_coverage.py`.
- `scripts/stamp_options_state.py` if stamp fields are missing.
- `scripts/build_options_entry_state.py` if state table needs null-handling improvements.
- `data/options_entry/coverage.json`.

Deliverable:

- Coverage by feature/date/ticker.
- Readiness forecast for each gate family.

### PR-D: Options Path-Quality Report

Files:

- `scripts/research/options_entry_path_quality.py` or an extension of `scripts/validate_options_entry.py`.
- `research/options/OPTIONS_ENTRY_PATH_QUALITY_REPORT.md`.

Deliverable:

- Descriptive path-quality report with all bucket sizes and nulls printed.
- Gate JSON remains strict and unchanged unless the existing gate logic requires bug fixes.

### PR-E: Operator Exposure Log

Files:

- `scripts/build_operator_exposure_log.py`.
- `config/synapse.yml`.
- `docs/SIGNAL_BUS.md`.
- Tests for absent local ledger.

Deliverable:

- Exposure denominator exists even when action ledger is sparse.

### PR-F: Operator Action Grader and Weekly Review

Files:

- `engine/operator_action_grader.py`.
- `scripts/grade_operator_actions.py`.
- `scripts/render_operator_weekly_review.py`.
- `research/operator/DECISION_QUALITY_PROTOCOL.md`.

Deliverable:

- First unresolved/graded action report.
- Weekly review artifact.

## 8. What Improving These Lobes Would Do

Short-Side:

- Reduces bad long entries.
- Gives the entry stack a real "not here" discipline.
- Improves drawdown control without overfitting exits.
- Builds a future hedge path only if evidence earns it.

Options:

- Improves stop placement and timing.
- Reduces entries into pin, wall, or rising-crash-risk conditions.
- Gives Claude and Mastermind richer context for candidates already liked by price/setup.
- Converts raw options data into path-quality evidence.

Decision-Quality:

- Measures whether the system is useful in actual decisions.
- Identifies ignored warnings that deserved action.
- Identifies alerts that create noise.
- Turns operator learning into a ledger, not memory.
- Helps decide which lobes deserve more engineering time.

Combined:

- The Neural Web becomes less of a signal library and more of a learning institution.
- The system can learn which evidence improves decisions, not just which feature correlates with returns.
- Claude gets a stable substrate for future research: events, contexts, actions, outcomes, and counterfactuals.

## 9. Guardrails

Hard guardrails:

- No short execution from short-side evidence.
- No options-originated buys.
- No fused options score before gates.
- No decision-quality grading without exposure denominators.
- No display chip that implies authority before the relevant live ledger exists.
- No LLM-originated signals.
- Heavy research runs stay off render path.
- Nulls and underpowered buckets are printed.

Language guardrails:

- Use "display", "shadow", "context", "avoid candidate", "building history", and "gate-passed" precisely.
- Avoid authority language where the repo has not earned it.

## 10. Claude Checklist

Before building:

- Read `CLAUDE.md`.
- Read this document.
- Read the closest lobe masterplan/prereg.
- Confirm current artifact existence with `docs/SIGNAL_BUS.md` and `config/synapse.yml`.

For every PR:

- State storage path and writer.
- State whether artifact is git, gitignored local, or R2.
- Add tests for missing local stores.
- Regenerate `docs/SIGNAL_BUS.md` if synapse changes.
- Preserve display/shadow status.
- Print sample sizes and nulls.

Best first branch:

`codex/short-side-phase1-avoid-prereg`

Reason:

Short-side has the strongest immediate evidence from the next-three set. BD-2 and BD-3 already show large bad-long gaps vs controls. A prereg is cheap, safe, and unlocks a live accrual path without granting any trading authority.
