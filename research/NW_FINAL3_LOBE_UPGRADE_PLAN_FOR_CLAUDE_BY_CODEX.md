# Neural Web Final-3 Lobe Upgrade Plan for Claude

Prepared by Codex, 2026-07-06.

Status: research handoff and build plan. Additive document only. No scoring, sizing, or execution authority is granted here.

Audience: Claude/Fable/Sonnet build lanes.

## 0. Boundary and Selection Ruling

This is pass three. It excludes the six lobes already covered by the prior two Codex reports:

1. Oracle / Rotation Intelligence.
2. US Entry Intelligence / Entry Stack.
3. Long-Hold Thesis Layer.
4. Short-Side / Breakdown Intelligence.
5. Options Entry Intelligence.
6. Decision-Quality / Operator Self-Model.

Those are covered in:

- `research/NW_TOP3_LOBE_POWER_UP_ANALYSIS_BY_CODEX.md`
- `research/NW_NEXT3_LOBE_UPGRADE_PLAN_FOR_CLAUDE_BY_CODEX.md`

Selected final three:

| Rank | Lobe | Why this is next | Current repo substrate | Core upgrade theme |
|---|---|---|---|---|
| 7 | Exit & Trim Intelligence | Every entry eventually becomes a hold, trim, exit, or regret problem. The repo now has enough R1 evidence to make this a real lobe. | `EXIT_GRID_1_REPORT`, `exit_grid_v1_summary.json`, exit-crowding prereg/interim, EMA8 survivor, hold(21) anchor. | Build a role-aware exit intelligence layer: time exits, tail flags, thesis breaks, trims, re-entry regret, and false-exit cost. |
| 8 | Dispersion / Selection-Regime Intelligence | It decides when selection should be trusted versus when the whole tape is one macro trade. It should condition every lobe, not just show a chip. | `engine/dispersion.py`, `scripts/build_dispersion_regime.py`, `data/dispersion/regime.json`, `DISP-GATE-1` prereg. | Promote dispersion from display chip to measured trust conditioner, while keeping sizing clamped. |
| 9 | Liquidity & Execution Realism | It decides whether measured edge survives spreads, impact, fills, capacity, tax timing, and options tape limits. This is institutional reality, not decoration. | `engine/validation.py`, `capacity_curve`, ThetaData probe, signing gate, liquidity proxies, S-LQ report, options exit crowding. | Build an execution-realism passport that can attach net-of-cost, capacity, and tax sensitivity to every lobe. |

Near-miss not selected: Cash / Patience opportunity-cost ledger. It is important, but it is better as the first extension after Exit & Trim and Liquidity are upgraded. Waiting one week is an exit/entry counterfactual with cash carry and execution cost. It needs the same R1 replay, cash-yield, cost, and opportunity-cost machinery this report recommends building first.

## 1. Evidence Census

Closest repo evidence used:

| Area | Evidence |
|---|---|
| Lobe taxonomy | `research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md` defines Exit & Trim as L2, Dispersion as L3, Liquidity/Execution as L5, Cash/Patience as L7. |
| R1 replay authority | `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` says R1 is a fire-tape x policy-grid replay with anti-fishing governor and flat `fdr_family='replay'`. |
| Exit-grid result | `research/rule_replay/EXIT_GRID_1_REPORT.md` and `data/rule_experiments/results/exit_grid_v1_summary.json` cover 49,939 fires, 22,295 clusters, 15 policies, descriptive only. |
| Exit-crowding | `research/EXIT_CROWDING_PHASE0_PREREG.md`, `research/EXIT_CROWDING_L4_INTERIM.md`, and `data/options_exit/exit_crowd_l4_interim.json` show options/flow exit evidence is registered but mostly ACCRUE. |
| Dispersion live state | `data/dispersion/regime.json` says as of 2026-07-06: `state=lean_in`, `dispersion_pctile=0.8`, `avg_corr=0.07`, `gross_mult_live=1.0`. |
| Dispersion prereg | `research/dispersion/L3_PREREG.md` freezes `DISP-GATE-1`, basis reconciliation, drawdown confound control, and pass thresholds. |
| Liquidity/cost engine | `engine/validation.py` implements next-bar backtest core, turnover cost, cash yield, ADV, square-root impact, and capacity curve. |
| Tape signing | `research/THETADATA_PROBE.md` and `data/options_flow/signing_gate.json` show ThetaData tape sub-gate passed on one measured session, while root bar-sourced direction remains false. |
| Liquidity hygiene | `research/entry_stack/W2_SLQ_REPORT.md` shows Amihud and Corwin-Schultz proxies exist, but worst-liquidity bands affected too many fires to ship as an entry hygiene filter. |
| Prior institutional roadmap | `research/INSTITUTIONAL_ROADMAP.md` records cost/capacity realism as shipped at the primitive level, not yet generalized into every lobe. |

## 2. First-Principles Frame

The first six lobes mostly answer:

- What should I look at?
- What should I buy?
- What should I avoid?
- What should I keep owning?
- What did the operator do?

The final three answer a deeper institutional question:

> Can the system turn signal evidence into realized, executable, after-friction decisions?

That requires three missing intelligences:

1. Exit & Trim: the decision path after entry.
2. Dispersion: the regime in which selection evidence is worth trusting.
3. Liquidity & Execution: the friction layer between paper edge and realizable edge.

The point is not to invent new alpha. The point is to make the existing alpha harder to fool.

An institutional desk would not ask "what is the best signal?" first. It would ask:

1. Did the signal survive realistic fills?
2. Did it survive capacity and spread?
3. Did the exit policy destroy the asymmetry?
4. Did the regime make selection irrelevant?
5. Did taxes and cash carry change the answer?
6. What is the opportunity cost of acting now versus waiting?

These three lobes are the institutional realism layer.

## 3. Lobe 7: Exit & Trim Intelligence

### 3.1 What It Is

Exit & Trim Intelligence answers:

> Once we are in a position or a candidate has worked, what evidence should govern hold, trim, exit, re-entry, or thesis break?

This lobe must not re-litigate the killed "simple exit rule saves everything" idea. The exit grid already says the harder truth:

- Tight stops shave winners.
- Wide stops mostly become hold policies.
- EMA8 is the best signal-driven tail flag in the grid.
- hold(21) is an efficient reversion-capture clock, not a magical inflection.
- Drawdown control is mostly an entry-quality problem.

So the lobe should not be "sell rule optimizer." It should be "position lifecycle intelligence."

### 3.2 Current Repo State

Built:

- R1 rule replay core and governor.
- `exit_grid_v1` registered/reported.
- `research/rule_replay/EXIT_GRID_1_REPORT.md`.
- `data/rule_experiments/results/exit_grid_v1_summary.json`.
- EMA8 tail-flag result.
- hold(21) Oracle anchor result.
- exit crowding prereg and L4 interim.
- `data/options_exit/exit_crowd_l4_interim.json`.

Key exit-grid numbers:

| Policy | WR | Mean return | Median return | Foregone MFE | Avoided MAE | Regret ratio |
|---|---:|---:|---:|---:|---:|---:|
| hold_21 | 0.577 | +1.9% | +1.6% | 0.1492 | 0.0773 | 0.52 |
| hold_63 | 0.585 | +4.3% | +3.1% | 0.0785 | 0.0357 | 0.45 |
| hold_126 | 0.590 | +7.3% | +4.3% | 0.0000 | 0.0000 | reference |
| ema_trail_s8 | 0.623 | +4.4% | +1.5% | 0.1338 | 0.0999 | 0.75 |
| trail_stop_20pct | 0.516 | +4.5% | +0.9% | 0.0216 | 0.0351 | 1.63 |

Exit-crowding current state:

- L4 ETF-flow rolloff interim verdict: ACCRUE.
- Flow history only ~3 months, one era, sector-ETF holdings absent.
- 21d interim sign was opposite the exhaustion hypothesis but not interpretable.
- L1-L3 blocked on ThetaData universe/history completion.

### 3.3 First-Principles Diagnosis

There are at least six exit problems hiding under one word:

1. Loss prevention: get out before drawdown deepens.
2. Winner preservation: do not cut the compounding right tail.
3. Capital recycling: free capital after the reversion window.
4. Thesis invalidation: the original reason to own it broke.
5. Crowding/exhaustion: late buyers have arrived and forward edge decays.
6. Re-entry regret: the exit was right temporarily, but the name repaired.

One exit rule cannot solve all six. A smart lobe needs role classification:

| Role | Question | Example evidence | Failure mode |
|---|---|---|---|
| Time exit | Has the original reversion window played out? | hold(21), Oracle windows | Exits compounders too early. |
| Tail flag | Has momentum genuinely broken? | EMA8 fresh breach | Late after gap breaks. |
| Thesis break | Is the hold reason gone? | long-hold thesis clock, fundamentals, event failure | Slow and sparse. |
| Crowding exit | Is the position now too crowded/chased? | options/ETF flow, call-share, IV blowout | Data-starved or one-era. |
| Trim | Should exposure be reduced, not closed? | overextension + still-valid thesis | All-or-nothing framing. |
| Re-entry | Did the exit create a new better entry? | base repair after exit | Exits become permanent bans. |

This lobe becomes smart when it learns which role applies, not when it finds one more stop parameter.

### 3.4 What Institutions Would Do

An institutional PM team would separate:

1. Trade management: where is the tactical trade over?
2. Position management: how much exposure should remain?
3. Thesis management: is the original reason still true?
4. Tax management: is the exit worth the realized tax timing?
5. Capacity management: can the exit be executed without moving the name?

They would build a post-entry event ledger with every decision point stamped:

- entry reason,
- current evidence,
- original horizon,
- current profit/loss path,
- thesis state,
- crowding state,
- liquidity state,
- tax lot state,
- action taken,
- forward outcome.

That is what Claude should build toward.

### 3.5 Five Most Important Upgrades

#### Upgrade 1: Exit Role Classifier

Build:

- `research/exit_trim/EXIT_TRIM_MASTERPLAN_BY_CLAUDE.md`.
- `engine/exit_trim_roles.py`.
- `scripts/build_exit_role_state.py`.
- `data/exit_trim/role_state.parquet`.

Role vocabulary:

- `time_exit_candidate`
- `tail_flag_candidate`
- `thesis_break_candidate`
- `crowding_exit_candidate`
- `partial_trim_candidate`
- `reentry_watch_candidate`
- `do_nothing`

Training data:

- R1 exit grid perfire parquet where available.
- `data/rule_experiments/results/exit_grid_v1_summary.json`.
- `data/research/long_hold_labels.parquet`.
- `data/research/missed_hold_study_results.parquet`.
- `data/options_exit/exit_crowd_l4_interim.json`.
- board ledger path labels from `data/us_board_ledger/retro_grades.parquet`.
- short-side avoid labels once Phase-1 exists.

Labels:

- `exit_helped_21`: exit improved 21d risk-adjusted path versus hold.
- `exit_hurt_126`: exit gave up materially better 126d path.
- `tail_flag_true`: EMA8 exit avoided worse drawdown without major MFE regret.
- `time_exit_efficient`: 21d exit captured most near-term payoff without excessive re-entry regret.
- `thesis_break_true`: post-exit thesis/falsifier evidence worsened.
- `reentry_needed`: name repaired enough to re-enter within a frozen window.

Claude build notes:

- Do not use the classifier to trade.
- First output is a display table and report.
- Role classifier can be rules plus labels at first; model comes later.
- Every role must carry evidence refs and stale/null fields.

Expected improvement:

- Exit decisions become typed, not generic.
- The operator sees why an exit is being discussed.
- Claude can later train role-specific policies instead of one muddled policy.

#### Upgrade 2: Regret Ledger v2

Build:

- `scripts/research/exit_regret_v2.py`.
- `data/exit_trim/regret_v2_summary.json`.
- `research/exit_trim/EXIT_REGRET_V2_REPORT.md`.

Metrics:

- `foregone_mfe`.
- `avoided_mae`.
- `exit_return`.
- `reference_return`.
- `reentry_return_after_exit`.
- `time_in_capital_saved`.
- `false_exit_cost`.
- `late_exit_cost`.
- `tax_drag_estimate` as configurable placeholder.
- `execution_drag_estimate` from Liquidity/Execution lobe.

Segment by:

- entry species,
- board lane,
- sector,
- dispersion state,
- options pressure state,
- short-side avoid state,
- long-hold label,
- Oracle rotation context,
- liquidity band.

Claude build notes:

- Use the existing R1 anti-fishing governor for new experiments.
- If using the already-seen exit grid surface, stamp `derived_from_surface: exit_grid_v1`.
- Keep descriptive vs promotion gates separate.

Expected improvement:

- Turns exit from "did it work on average?" into "where did it help and where did it destroy upside?"

#### Upgrade 3: Partial Trim Simulator

Build:

- Extend R1 RuleSpec or create a registered R1 experiment for partial exposure policies.
- Candidate policies:
  - trim 25% at hold(21), hold rest to EMA8.
  - trim 50% at +15% MFE, hold rest to EMA8.
  - trim 33% on overextension, 33% on EMA8, 34% to 126d.
  - trim only when role classifier says `time_exit_candidate` and long-hold says no thesis upgrade.

Outputs:

- weighted return path,
- weighted drawdown,
- right-tail retention,
- capital freed,
- churn cost,
- tax-lot sensitivity.

Training labels:

- `trim_better_than_exit`.
- `trim_better_than_hold`.
- `all_or_nothing_was_wrong`.
- `right_tail_retained`.

Claude build notes:

- Pre-register the grid. No ad hoc trim recipes.
- Include all null and loser cells.
- Any later promotion must use stricter or fresh OOS gates because exit_grid_v1 has already been seen.

Expected improvement:

- Stops the system from treating exit as binary.
- Preserves more compounding while still reducing exposure when the tactical edge has decayed.

#### Upgrade 4: Thesis-Clock and Exit-Reason Unification

Build:

- Join Long-Hold thesis clocks with exit roles.
- `data/exit_trim/thesis_exit_join.parquet`.
- `research/exit_trim/THESIS_EXIT_JOIN_REPORT.md`.

Core idea:

- Entry reason and hold reason are different objects.
- If entry reason expires but hold reason appears, exit should become trim/hold review.
- If entry reason expires and no hold reason appears, time exit is cleaner.
- If hold reason breaks, thesis exit outranks time exit.

Labels:

- `entry_reason_expired`.
- `hold_reason_appeared`.
- `hold_reason_broke`.
- `exit_reason_valid`.
- `exit_reason_invalid`.

Claude build notes:

- Use Long-Hold labels as context, not authority.
- Do not let long-hold override tactical risk until its own gates mature.
- Print cases where long-hold would have saved a premature exit.

Expected improvement:

- Prevents tactical exits from cutting the small set of true long-hold winners.
- Gives Claude a way to explain "sell the trade, keep the thesis" versus "sell the thesis."

#### Upgrade 5: Exit-Crowding Completion and Repair

Build:

- Complete the blocked L1-L3 options exit-crowding lanes after ThetaData universe pass.
- Add sector-ETF holdings coverage or replace lossy theme-to-sector mapping with member GICS rollup.
- `research/exit_trim/EXIT_CROWDING_COMPLETION_REPORT.md`.

Needed repairs from current interim:

- sector-ETF holdings absent,
- one-era flow history,
- lossy theme-to-sector mapping,
- no FDR until full family completes,
- L4 sign currently not interpretable.

Training labels:

- `crowding_exit_helped`.
- `crowding_exit_false_alarm`.
- `flow_rolloff_true`.
- `call_share_exhaustion_true`.
- `iv_blowout_true`.
- `pcoi_complacency_true`.

Claude build notes:

- Do not weaken the prereg to make history fit.
- If history remains too thin, keep ACCRUE.
- A pass earns display annotation only, not a hard exit gate.

Expected improvement:

- Adds institutional exhaustion evidence to exit roles without turning it into a brittle sell score.

## 4. Lobe 8: Dispersion / Selection-Regime Intelligence

### 4.1 What It Is

Dispersion answers:

> Is this a stock-picker's tape, or a one-factor macro tape where individual selection evidence collapses?

Current implementation is intentionally small: a live display state with `lean_in`, `neutral`, or `lean_out`. The upgrade is not to uncap sizing. The upgrade is to make dispersion a measured trust conditioner across every lobe.

### 4.2 Current Repo State

Built:

- `engine/dispersion.py`.
- `scripts/build_dispersion_regime.py`.
- `data/dispersion/regime.json`.
- `research/dispersion/L3_PREREG.md`.
- Synapse registration: `dispersion-regime`.
- Site display chip.

Current live artifact:

- `as_of`: 2026-07-06.
- `state`: lean_in.
- `dispersion_pctile`: 0.80.
- `avg_corr`: 0.07.
- `shadow_gross_mult`: 1.2.
- `gross_mult_live`: 1.0.
- history length in this worktree: 2 days.

Hard constraints:

- `gross_mult_live` stays 1.0.
- No sizing or rank power.
- `DISP-GATE-1` harness not built yet.
- Must reconcile expanding-window basis versus trailing-252 basis.
- Must control for market drawdown confound.

### 4.3 First-Principles Diagnosis

Selection alpha needs dispersion. If all stocks move together, name selection has less room to matter. But raw dispersion can mean different things:

1. Healthy dispersion: winners and losers separate because fundamentals matter.
2. Stress dispersion: panic creates large single-name moves but selection may still be fragile.
3. Low-dispersion macro tape: all names follow rates, dollar, or index flow.
4. Post-shock compression: names stabilize together after a panic.
5. Crowded leadership dispersion: one group carries the tape while breadth decays.

Current `lean_in` / `lean_out` is too coarse to separate these. The upgrade is to decompose dispersion into trust-relevant components.

### 4.4 What Institutions Would Do

An institutional quant desk would not simply gross up when dispersion is high. It would ask:

1. Is dispersion idiosyncratic or macro-driven?
2. Is selection breadth broad or concentrated in one theme?
3. Is dispersion helping entries, exits, short-side avoids, or only after the fact?
4. Does the regime retain effect after controlling for market drawdown and volatility?
5. Does the regime improve decision utility, not just returns?

That is the right path for this lobe: trust calibration, not exposure.

### 4.5 Five Most Important Upgrades

#### Upgrade 1: Build and Run DISP-GATE-1 Harness

Build:

- `scripts/research/run_disp_gate_1.py`.
- `data/dispersion/disp_gate_1_summary.json`.
- `research/dispersion/DISP_GATE_1_REPORT.md`.

Must implement:

- PIT expanding-window regime reconstruction.
- trailing-252 sensitivity.
- assignment-flip rate.
- SPY 21d drawdown tercile control.
- episode-clustered bootstrap.
- lean_out vs lean_in stop5 and dead-money gap.
- explicit excluded fire count.

Labels:

- `fire_regime_state`.
- `stop5_21`.
- `dead_money_21`.
- `clean_liftoff_21`.
- `spy_21d_drawdown_tercile`.
- `basis_flip`.
- `non_stationary_basis_flag`.

Claude build notes:

- If >15% of fires flip regime assignment between bases, flag non-stationarity and stop at descriptive.
- If drawdown control absorbs the gap, do not claim independent dispersion trust.
- PASS can only enable a display flag, not sizing.

Expected improvement:

- Turns dispersion from a good-sounding chip into a measured trust lens.

#### Upgrade 2: Dispersion Feature Store

Build:

- `engine/dispersion_features.py`.
- `scripts/build_dispersion_features.py`.
- `data/dispersion/features.parquet`.

Features:

- cross-sectional dispersion percentile.
- average correlation proxy.
- equal-weight vs cap-weight divergence.
- sector dispersion.
- within-sector dispersion.
- leader concentration.
- breadth-adjusted dispersion.
- idiosyncratic residual dispersion after SPY/sector beta.
- dispersion acceleration.
- dispersion half-life.
- N-effective names (`N_eff`) for candidate sets.

Training labels:

- Entry path labels from US board ledger.
- short-side avoid labels.
- exit regret labels.
- options pressure labels.
- operator action labels later.

Claude build notes:

- Keep raw fields; no fused score.
- Store as daily context with as-of and universe stamp.
- Include coverage and dead-name coverage where applicable.

Expected improvement:

- Gives every lobe a richer regime context than one state string.

#### Upgrade 3: Residual Selection Trust Model

Build:

- `scripts/research/dispersion_selection_trust.py`.
- `research/dispersion/SELECTION_TRUST_REPORT.md`.

Question:

> After controlling for market drawdown, volatility, and liquidity, does dispersion state change whether selection signals work?

Controls:

- SPY 21d return.
- VIX/vol regime if available.
- liquidity/ADV/spread bands.
- sector concentration.
- macro regime quad.
- rate/dollar stress.

Outputs:

- raw gap.
- controlled gap.
- residual selection trust.
- per-lobe trust table:
  - Entry.
  - Short-side.
  - Options.
  - Exit.
  - Oracle.

Claude build notes:

- Do not fit a complex model first. Start with stratified tables and paired deltas.
- The null is useful: if dispersion is just drawdown proxy, say so.

Expected improvement:

- Prevents the system from double-counting macro stress as selection regime.

#### Upgrade 4: Lobe Conditioning Matrix

Build:

- `data/dispersion/lobe_conditioning_matrix.json`.
- `research/dispersion/LOBE_CONDITIONING_MATRIX.md`.

Rows:

- Entry fires.
- Short-side BD events.
- Options top-risk flags.
- Exit roles.
- Oracle onset routes.
- Long-hold candidates.
- Decision-quality warnings.

Columns:

- lean_in.
- neutral.
- lean_out.
- residual high/low dispersion.
- high concentration.
- within-sector high dispersion.

Metrics:

- stop5.
- clean liftoff.
- dead money.
- avoid success.
- exit regret.
- false caution.
- decision utility.

Claude build notes:

- This is a matrix, not a score.
- Only rows with enough n get CIs.
- Sparse cells stay sparse.

Expected improvement:

- The Neural Web can learn "which lobe to trust in which tape."

#### Upgrade 5: Display and Alert Vocabulary Upgrade

Build:

- Better candidate context fields:
  - `selection_regime`.
  - `selection_trust_note`.
  - `basis_nonstationary`.
  - `drawdown_confounded`.
  - `candidate_set_n_eff`.
- Optional board display after DISP-GATE-1:
  - "selection pays",
  - "macro tape",
  - "trust flag pending",
  - "dispersion basis unstable."

Claude build notes:

- No "gross up" language.
- No hidden rank multipliers.
- Every display state should say whether it is measured, descriptive, or pending.

Expected improvement:

- Makes dispersion useful to the operator without granting it power it has not earned.

## 5. Lobe 9: Liquidity & Execution Realism

### 5.1 What It Is

Liquidity & Execution Realism answers:

> Does the edge still exist after fills, spreads, impact, capacity, cash carry, tax timing, and data-source signing limits?

This lobe is not a signal lobe in the normal sense. It is a realism lobe. It should attach an execution passport to every other lobe.

### 5.2 Current Repo State

Built:

- `engine/validation.py`:
  - next-bar backtest core,
  - turnover cost,
  - cash yield,
  - ADV,
  - square-root impact,
  - capacity curve.
- Tests for capacity model.
- Entry liquidity proxies:
  - Amihud.
  - Corwin-Schultz.
- `research/entry_stack/W2_SLQ_REPORT.md`.
- ThetaData Professional tier probe.
- `data/options_flow/signing_gate.json`.

Current important facts:

- Root options flow direction remains false for bar/minute sources.
- ThetaData tape sub-gate has one measured pass:
  - n_trades 16,366.
  - n_contracts 15.
  - agreement 0.8848.
  - net-sign recovery 0.80.
- Continuous validation still required across at least 5 additional sessions, high-VIX and calm.
- Entry liquidity hygiene study did not ship a filter: worst-liquidity bands affected too much volume and did not meet the hygiene bar.

### 5.3 First-Principles Diagnosis

The repo has many gross edges. Real deployment asks:

1. What is the expected fill?
2. What spread is paid?
3. How much market impact comes from participation?
4. Does the name have enough capacity?
5. Does the signal decay before execution?
6. Does tax timing reverse the apparent benefit?
7. Does cash carry make waiting better than acting?
8. Are options-signed features truly signed for this source and time?

The system should not wait until live trading to discover that a signal only works in illiquid names or only gross of tax/cost.

### 5.4 What Institutions Would Do

An institutional platform would attach a transaction-cost model to every simulation. It would have:

1. Pre-trade liquidity passport.
2. Realistic fill model.
3. Capacity curve by strategy.
4. Slippage attribution.
5. Tax-lot optimizer.
6. Cash-carry accounting.
7. Source-specific data authority.

The strongest version here is not to block every thin name. The strongest version is to show expected realization quality:

- clean enough to act,
- tradable but size-limited,
- display-only because fill risk dominates,
- research-only because signing/source authority is weak.

### 5.5 Five Most Important Upgrades

#### Upgrade 1: Execution Passport Feature Store

Build:

- `engine/execution_passport.py`.
- `scripts/build_execution_passports.py`.
- `data/execution/passports.parquet`.

Fields:

- ticker.
- as_of.
- price.
- dollar ADV 21d / 63d.
- volume volatility.
- Amihud illiquidity.
- Corwin-Schultz spread.
- high-low range proxy.
- close-to-open gap risk.
- options bid/ask spread where available.
- borrow/shortability placeholder where available.
- event day liquidity shock flag.
- capacity bucket.
- data coverage.

Labels:

- `tradability_band`: deep, normal, thin, research-only.
- `expected_spread_bps`.
- `expected_impact_bps_at_aum_grid`.
- `capacity_usd_estimate`.
- `execution_confidence`.

Claude build notes:

- Use existing `engine.validation.dollar_adv` and liquidity primitives.
- Start with equities and ETFs.
- Nulls must degrade to unknown, not safe.
- Do not filter entries automatically.

Expected improvement:

- Every lobe can know whether its signal is realistically tradable.

#### Upgrade 2: Net-of-Friction Replay Adapter

Build:

- Extend R1 rule replay reports with optional execution model.
- `scripts/research/net_replay_adapter.py`.
- `data/execution/net_replay_summaries/<EXP_ID>.json`.

Apply to:

- exit_grid_v1.
- future exit/trim partial policies.
- short-side avoid counterfactuals.
- entry replay cohorts.
- cash/patience wait rules.

Cost components:

- one-way spread estimate.
- fixed bps fallback.
- square-root impact using ADV and AUM grid.
- cash carry on flat sleeve.
- optional tax placeholder.

Claude build notes:

- Keep gross and net side-by-side.
- Do not replace the original R1 result.
- Every net replay must stamp assumptions:
  - cost model,
  - AUM grid,
  - spread proxy,
  - cash series,
  - missing-data policy.

Expected improvement:

- Prevents paper-only results from becoming decision inputs.
- Lets Claude answer "does this still work after friction?"

#### Upgrade 3: Capacity Curves for Lobe Outputs

Build:

- `scripts/build_lobe_capacity_curves.py`.
- `data/execution/lobe_capacity_curves.json`.
- `research/execution/LOBE_CAPACITY_REPORT.md`.

Run for:

- entry cohorts,
- exit/trim policies,
- Oracle route baskets,
- long-hold candidate baskets,
- options pressure cohorts,
- short-side avoid cohorts if ever used to hedge,
- special sleeves if present.

Use:

- `engine.validation.capacity_curve`.
- AUM grid configurable:
  - 10k,
  - 50k,
  - 100k,
  - 500k,
  - 1m,
  - 5m,
  - 10m,
  - 50m,
  - 100m.

Outputs:

- gross Sharpe / return.
- net Sharpe / return.
- capacity verdict.
- mean participation.
- annual cost drag.
- names driving capacity bottleneck.

Claude build notes:

- This can be a research report first.
- Do not imply the user has those AUM levels.
- This is scale sensitivity, not advice.

Expected improvement:

- The system knows which edges are robust only at small size.
- Prevents thin-name alpha from being over-ranked.

#### Upgrade 4: Tax-Lot and Holding-Period Sensitivity

Build:

- `engine/tax_sensitivity.py`.
- `scripts/research/oracle_exit_tax_sensitivity.py`.
- `research/execution/ORACLE_21D_TAX_SENSITIVITY.md`.

Question:

> Does the 21-session Oracle exit create after-tax drag large enough to change the apparent edge?

Configurable assumptions:

- short-term rate,
- long-term rate,
- tax-advantaged flag,
- loss-harvest rules disabled by default,
- wash-sale modeling off unless explicitly implemented,
- jurisdiction config, no hard-coded advice.

Apply to:

- hold(21),
- EMA8,
- hold(63),
- hold(126),
- partial trims.

Labels:

- `after_tax_return`.
- `tax_drag`.
- `tax_timing_penalty`.
- `tax_sensitive_rank_flip`.
- `defer_better_than_exit`.

Claude build notes:

- This is not tax advice.
- Keep assumptions configurable and printed.
- Do not use current tax rates as hard-coded constants in research docs.
- The first run can use symbolic or scenario rates.

Expected improvement:

- Exit & Trim becomes economically honest.
- The system can distinguish pre-tax edge from after-tax edge.

#### Upgrade 5: ThetaData Tape Production Calibration

Build:

- `scripts/calibrate_thetadata_tape_sessions.py`.
- `data/options_flow/tape_signing_sessions.jsonl`.
- `data/options_flow/tape_signing_gate.json`.
- `research/execution/THETADATA_TAPE_CONTINUOUS_CALIBRATION.md`.

Requirements:

- at least 5 additional sessions,
- high-VIX and calm sessions,
- multiple roots,
- multiple expiries,
- multiple moneyness buckets,
- enough trades per session,
- pass/fail by source and condition.

Outputs:

- agreement by root,
- recovery by root,
- agreement by moneyness,
- recovery by time-of-day,
- stale/suspended flag,
- source-specific authority.

Claude build notes:

- Root `direction_reliable` remains false for bar sources.
- Tape authority is source-specific.
- If any required session fails, tape ratification suspends pending review.
- This supports options execution/flow realism, not automatic buy/sell direction.

Expected improvement:

- Options-derived execution and flow features become source-aware and auditable.
- The system stops mixing bar-derived soft direction with tape-derived stronger direction.

## 6. Cross-Lobe Architecture: Realized-Decision Passport

These three lobes should share one compact passport object.

Proposed schema:

```json
{
  "passport_id": "string",
  "as_of": "YYYY-MM-DD",
  "ticker": "string|null",
  "lobe": "exit_trim|dispersion|execution",
  "decision_type": "hold|trim|exit|wait|enter|avoid|review",
  "gross_evidence": {},
  "dispersion_context": {},
  "execution_context": {},
  "tax_context": {},
  "cash_context": {},
  "expected_friction_bps": null,
  "capacity_bucket": "unknown|deep|normal|thin|research_only",
  "regime_trust": "unknown|higher|neutral|lower",
  "authority_level": "display|shadow|infrastructure",
  "allowed_action": "annotate_only",
  "outcome_status": "unresolved|graded",
  "outcome": {}
}
```

Purpose:

- Exit & Trim can ask whether an exit is gross-good but tax/cost-bad.
- Dispersion can ask whether selection evidence is likely to transfer.
- Liquidity can ask whether a signal is actually executable.
- Cash/Patience can be added later as the next dependent lobe.

Non-goal:

- This passport does not trade, rank, size, or override any lobe.

## 7. Claude Build Plan

### PR-A: Exit & Trim Charter

Files:

- `research/exit_trim/EXIT_TRIM_MASTERPLAN_BY_CLAUDE.md`.
- Maybe update `config/synapse.yml` only if adding artifact placeholders.

Deliverable:

- Role taxonomy.
- Labels.
- Non-goals.
- Relationship to R1 and long-hold.
- First registered experiments to run.

### PR-B: Exit Regret v2

Files:

- `scripts/research/exit_regret_v2.py`.
- `data/exit_trim/regret_v2_summary.json`.
- `research/exit_trim/EXIT_REGRET_V2_REPORT.md`.

Deliverable:

- Segmented regret surface with false-exit, late-exit, and re-entry labels.

### PR-C: DISP-GATE-1 Harness

Files:

- `scripts/research/run_disp_gate_1.py`.
- `data/dispersion/disp_gate_1_summary.json`.
- `research/dispersion/DISP_GATE_1_REPORT.md`.

Deliverable:

- Historical PIT dispersion assignment and confound-controlled entry trust report.

### PR-D: Dispersion Feature Store

Files:

- `engine/dispersion_features.py`.
- `scripts/build_dispersion_features.py`.
- `data/dispersion/features.parquet`.
- `config/synapse.yml`.
- `docs/SIGNAL_BUS.md`.

Deliverable:

- Daily raw dispersion features, no composite score.

### PR-E: Execution Passport

Files:

- `engine/execution_passport.py`.
- `scripts/build_execution_passports.py`.
- `data/execution/passports.parquet`.
- tests for null stores and proxy math.

Deliverable:

- Per-name execution realism context.

### PR-F: Net Replay and Tax Sensitivity

Files:

- `scripts/research/net_replay_adapter.py`.
- `engine/tax_sensitivity.py`.
- `scripts/research/oracle_exit_tax_sensitivity.py`.
- `research/execution/ORACLE_21D_TAX_SENSITIVITY.md`.

Deliverable:

- Gross vs net vs after-tax scenarios for existing exit policies.

### PR-G: ThetaData Continuous Calibration

Files:

- `scripts/calibrate_thetadata_tape_sessions.py`.
- `data/options_flow/tape_signing_sessions.jsonl`.
- `data/options_flow/tape_signing_gate.json`.
- `research/execution/THETADATA_TAPE_CONTINUOUS_CALIBRATION.md`.

Deliverable:

- Multi-session tape signing authority audit.

## 8. What Improving These Lobes Would Do

Exit & Trim:

- Reduces premature exits.
- Reduces late exits.
- Preserves long-hold winners.
- Converts stop-rule debate into role-specific lifecycle decisions.
- Makes re-entry and false-exit cost visible.

Dispersion:

- Tells the system when selection evidence should be trusted less or more.
- Prevents macro-stress double counting.
- Adds regime context to every lobe without touching sizing.
- Makes "selection pays" a measured statement, not a slogan.

Liquidity & Execution:

- Converts gross alpha into more realistic net alpha.
- Exposes thin-name and capacity fragility.
- Adds cash carry and tax timing to exit decisions.
- Keeps options-source authority honest.
- Makes the repo behave more like an institutional research platform.

Combined:

- The Neural Web becomes harder to fool by backtest artifacts.
- Claude can evaluate ideas in terms of realized decision quality.
- The next natural lobe, Cash / Patience, becomes straightforward to build on top of the same passport.

## 9. Guardrails

Hard guardrails:

- No exit policy promotion from `exit_grid_v1` without a new registered gate and contamination stamp.
- No `gross_mult_live` unclamp from dispersion work.
- No dispersion-derived sizing.
- No options root direction flip from ThetaData tape work.
- No tax advice. Use configurable scenarios.
- No hard liquidity filter from S-LQ without a new gate.
- No hidden netting: gross and net must always print side-by-side.
- No fused execution score that can be mistaken for alpha.

Language guardrails:

- Use "display", "shadow", "descriptive", "ACCRUE", "gate-passed", and "context" precisely.
- Do not imply production authority.

## 10. Claude Checklist

Before building:

- Read `CLAUDE.md`.
- Read this document.
- Read the nearest existing lobe/prereg/report.
- Check `docs/SIGNAL_BUS.md` and `config/synapse.yml`.
- Confirm local data availability. Many full parquets are Mac-local or gitignored.

For every PR:

- Declare storage path and writer.
- Declare whether artifact is git, gitignored local, or R2.
- Add missing-store tests.
- Print nulls and sample sizes.
- Preserve gross and net side-by-side.
- Regenerate `docs/SIGNAL_BUS.md` if synapse changes.

Best first branch:

`codex/disp-gate-1-harness`

Reason:

DISP-GATE-1 is already pre-registered, narrow, and directly useful to every lobe. It is the cleanest first build in this final-pass set because it upgrades a live artifact without opening a new authority surface.
