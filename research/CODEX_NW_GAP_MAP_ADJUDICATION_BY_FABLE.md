# Codex NW Gap-Map — Adjudication & Build Program (by Fable)

**Ratified:** 2026-07-06 (post 2-lens Opus red-team; corrections printed in §0.5)
**Input:** Codex memo `NEURAL_WEB_SIGNAL_DISCOVERY_GAP_MAP_BY_CODEX.md` (2026-07-06, written in a Codex worktree; not committed here).
**Method:** Codex memo → 8-lane repo census (Sonnet, file-level evidence) → this adjudication (Fable) → 2-lens Opus red-team → ratified revision → build waves (Sonnet build, Opus review, Fable merge/adjudication). §0 prints census corrections per house law.

---

## §0. Census ground truth (what Codex got right, wrong, and stale)

Codex wrote its memo the same day `NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` shipped all waves (#1545–#1568). Verdicts on its factual spine:

1. **CONFIRMED:** grading closure 7 CLOSED / 16 GRADER-STARVED / 3 LOG-ONLY (`data/governance/grading_closure.json`, 2026-07-06T04:38Z).
2. **CONFIRMED with sharper root cause:** `bottom_sensors.parquet` sponsorship_state = 'unavailable' for all 1,722 rows — but this is a **data-publish gap, not a missing signal family**. The connector (Amendment §C3) is fully implemented (`engine/neuralweb/bottom_sensors.py:263-367`); the blocker is that `data/oracle/panel_s.parquet`/`panel_m.parquet` are built off-render on the Mac (`scripts/build_oracle_panel.py` line 11) and the D5 publishing step never shipped. Sector map already resolves 1,489/1,722 tickers (86.5%).
3. **STALE:** "only a tiny set is scored; turn R1 replay + R2 closure into the default OS" — R1 (governor, flat `fdr_family='replay'`, EXIT-GRID-1, pooled count 15) and R2 (closure audit, end-of-collect) are LIVE. What's missing is *follow-through*: zero post-EXIT-GRID-1 experiments registered (`registry.jsonl` = 1 exp), and the closure audit's findings have no chartered fixes ("fixes are per-program follow-ups").
4. **OVER-IMPLIED:** "16 grader-starved ledgers" reads as 16 builds. Census: **10+ are purely TIME-starved** (graders wired and correct; rows dated 2026-06/07; earliest maturities 2026-07-10 → 2026-08-25). Only the 3 LOG-ONLY ledgers plus edge cases are BUILD-starved.
5. **CONFIRMED:** WAIT_5D / CASH_PATIENCE / abstention experiments exist nowhere (zero repo hits); L7 is docketed, un-chartered, and now substrate-unblocked (R1 shipped; `delay_n` is native — `engine/rule_replay.py:223,639-642`, zero engine change needed).
6. **CONFIRMED:** DISP-GATE-1 prereg exists (`research/dispersion/L3_PREREG.md`, pre-registered 2026-07-05) but is NOT in the rule-experiment registry and its harness (runner-side merge of PIT dispersion state) is unbuilt.
7. **NUANCED:** short-side Phase-0 — BD-2 (+9.66pp long-stop vs control @21d, 19,891 episodes) and BD-3 (+16.81pp @21d, 5,553 episodes) both clear the masterplan's ≥5pp Phase-1 bar with clustered CIs excluding 0. BD-1 fails (+0.58pp). BD-3 is the ONE definition where short-favorable exceeds adverse @21d — i.e. BD-3 is *not* clean "avoid-only" by the masterplan's own taxonomy; BD-2 is. No Phase-1 prereg exists for any BD.
8. **CONFIRMED:** qledger reliability by family×horizon with Wilson CIs already computes nightly (`site/qledger/track_record.json`); chips render on 3 pages; `altdata_brain.article3_actionable_verdict()` is the constitution-compliant consumption template. Gaps: no full table surface; ALL grades are horizon 5d (21/63d = zero); max n_dates = 9 vs GRADED_MIN_DATES=25; 63.7% of claims lack regime stamps. Channel-level cells lack n≥25.
9. **CONFIRMED:** measurement.html surfaces NONE of: grading_closure, trial budgets, rule-experiment registry (all three files committed and cheap to read; marginal render <1s).
10. **CONFIRMED:** L4 capture exists only on the admin Experiments tab; `overrode` is in VALID_ACTIONS but has no button; site/alerts.html has zero capture UI, no machine-readable alert IDs, and a cross-origin + auth wall by design.
11. **CONFIRMED:** Research Factory `awaiting_data` state + come_back clocks exist but the review queue does NOT surface blocked candidates; adapters for alpha_grammar/cortex/cycle_pattern exist and are absent-file-safe; queue is currently empty and Batch A was Oracle-only.
12. **KILLS/GATES Codex missed:** B2_REPAIR_STACK duplicates long-hold G1's registered F1 family (G1-DEFERRED on n-floor to ~2027-H2 — re-testing would double-dip a frozen family); TOP_RISK_DEESCALATION is parked behind the S-TOP_RISK accrual gate (~2026-10-15, RO-3); SLF-001 nulled the FTD-pressure variant only (FINRA daily short volume remains PIT-safe species evidence, needs own prereg); L6 macro games remain gated on a Phase-0 beating the noisy-sector precedent (COT/OFR-FSI/ALFRED stores confirmed deep: 1995→/2000→/1996→).

## §0.5 Red-team corrections to the draft (printed per house law)

The 2-lens Opus red-team (2026-07-06, APPROVE_WITH_EDITS ×2) falsified the following draft claims; all are fixed in this revision:

1. **FALSE (house-law lens B1):** "risk_radar US grader — copy the intl pattern" — the US grader is ALREADY BUILT AND WIRED nightly (`engine/risk_radar_audit.py:148/174/217`, called from `engine/run.py:614`). The LOG-ONLY verdict in `grading_closure.json` is a **hardcoded inventory error** in `scripts/audit_grading_closure.py` (`'grader': None` despite `grade_field='graded'`). The census inherited the audit's error and the draft inherited the census. PR-A2 rescoped: one-line inventory correction; the ledger is TIME-starved (n=8, none matured to h21).
2. **INFEASIBLE AS WRITTEN (house-law lens B2):** "nightly BD-2/BD-3 event stamper, end-of-collect" — BD-2 requires `replay_boarded` STOPPED-fire state and BD detection needs `massive_stock_day` prices; both are Mac-local/R2, absent from CI runner checkouts. PR-C2 split: the stamper+control-sampler runs on the **Mac-side off-render ops lane** (oracle_nightly pattern, single-writer commit path per RUL-P10), and only maturity grading of committed ledger rows may ride a nightly job that has price access. RUL-10 accounting corrected.
3. **FORKING-PATHS VIOLATION (stats lens F1):** the draft required a `derived_from_surface` stamp only for a hypothetical future short-entry prereg — but PR-C2's own avoid-long prereg selects BD-2/BD-3 *because* they cleared the seen Phase-0 surface, which IS the contamination event under RUL-P3. Fixed: the PR-C2 prereg carries `derived_from_surface: bd_phase0` and a compensating gate (verdict on forward OOS only + threshold raised above the selecting reading; §6).
4. **UNDEFINED CONTROL (stats lens F2):** "≥5pp vs matched control" is not evaluable on a forward stream without construction — Phase-0's control was retrospective seeded random-bar sampling; the cited oracle forward-ledger pattern has no control mechanics. Fixed: the stamper writes a parallel PIT random-bar control stream (3 controls/event, same universe + liquidity floor, seeded from event id) so the gate is evaluable forward (§6).
5. **NO CLOCK (stats lens F3):** the draft attached the masterplan's n≥300/side floor to a forward ledger with no maturity clock. Fixed: registered arrival-rate estimate + come-back date in the prereg; no verdict read before floor (§6) — RUL-4's own discipline applied to this program's ledger.
6. **UNDER-DECLARED BUDGET (stats lens F4):** the draft printed "pooled 25" counting only WAIT-GRID-1, but DISP-GATE-1 registers through the same flat `replay` family. Fixed: DISP-GATE-1's grid is enumerated (6 primary cells; §6) and the post-B2 pooled sum is 31. Also noted: `pooled_replay_trial_count()` SUMs declared budgets while `TrialLedger.log_declared_budget` keeps a per-family max() — the two numbers diverge by design; reports print both semantics (descriptive-only batches compute no DSR, so nothing load-bearing rides the max today).
7. **MISSING FEASIBILITY GATE (stats lens F5):** `data/dispersion/regime.json` holds 2 dates of history and `dispersion.assess()` emits one terminal state per call — NO historical PIT states exist for 2022-2026 fires. PR-B2 must recompute the expanding-window basis per fire date from a reconstructed broad-universe returns panel, verify the panel reaches ≥252 bars before the earliest fire (~2022-06 ⇒ panel to ~2021-06), and print the excluded-fire count as a powered-at-all check (§6).
8. **Narrative fixes (non-blocking):** PR-B1 is not "zero engine change" — the runner's `_GRID_BUILDERS` dict must gain a grid builder + registered hashes (`scripts/run_rule_replay.py:155/175`); PR-C4's endpoint/ledger substrate shipped in #1550 and the residue is exactly {Alerts tab, machine-readable alert IDs, overrode button}; the qledger table must print n_dates beside every Wilson CI with a "CI computed on overlapping n_obs, not clusters" flag; oracle panels measured on-host at 6.1MB + 39MB (fresh 2026-07-05) ⇒ RUL-7 resolves to R2, and no prior D5 publish spec exists — PR-C1 defines it (flagged as new spec, named single-writer).

---

## §1. Adjudication table (every Codex item)

| # | Codex item | Verdict | Disposition |
|---|---|---|---|
| P1 | Closed-loop training factory (R1/R2 as OS) | ALREADY-BUILT (rails) | Residue → PR-A1 (evidence panel), PR-A2 (log-only graders), Wave B (experiments) |
| P2 | Sponsorship/fragility data moat | PARTIAL | B0 fix → PR-C1. Fragility lobe → duplicates long-hold F-families + entry-stack; NO new lobe |
| P3 | NW as meta-decision/abstention trainer | RESHAPE | Labels first, model never (this program): Wave B experiments ARE the v1. No meta-model until families hit registered floors |
| A | Bottom sensors → supervised labeled panel | DEFER (accrual) | Panel has ONE as_of date (2026-07-02). Labels need calendar accrual. B0 ships (PR-C1); label joins get a clock, not a build |
| A/B0 | Fix sponsorship connector | **GO** | PR-C1 — publish oracle panels to render path (data gap, zero engine code) |
| A/B1 | Fragility-veto study | DEFER | Needs external joins (earnings/dilution flags not in replay_boarded 66-col surface); batch-3 candidate after PR-B2 lands the runner merge extension |
| A/B2 | Repair-stack study | **DON'T** | Duplicates G1 F1 (registered, DEFERRED ~2027-H2). Re-test = FDR double-dip + re-litigating a deferral |
| B | Replay as imagination engine | ALREADY-BUILT | Rail live. New registrations → Wave B |
| B/WAIT_5D | Delay-entry experiment | **GO** | PR-B1 — `delay_n` native; unconditional delay ladder + existing-column splits. Hostile-flag conditioning deferred to batch-3 (needs joins) |
| B/CASH_PATIENCE | Deploy-vs-wait a week | RESHAPE into PR-B1 | Fire-level deploy-vs-wait IS the delay ladder. Portfolio-level cash counterfactual = book construction = L8/Mastermind (out of scope per docket) |
| B/BOTTOM_SENSOR_ABLATION | Skip fragility-flagged fires | DEFER | Same external-join dependency as B1; bottom_sensors has 1 date of history |
| B/AVOID_LENS (BD) | Remove BD events from longs | **GO (reshaped)** | PR-C2 — L1 Phase-1 forward ledger for BD-2 + BD-3 avoid-long, per masterplan ladder |
| B/TOP_RISK_DEESCALATION | Options top-risk replay | **DON'T (yet)** | Parked behind S-TOP_RISK accrual gate ~2026-10-15 (RO-3). Time-gated, not forgotten |
| B/HOLDABLE_WINNER | Replay on missed_hold vs tactical_only | DEFER | Long-hold program owns this (A2 roster registered, Σ=29); replay variant only after honest-cohort maturity |
| C | grading_closure as unfinished-evidence queue | **GO** | PR-A1 surfaces it; PR-A2 closes the closeable. TIME-starved ledgers get clocks, not graders (RUL-4) |
| C/breadth_divergence grader | | **GO** | PR-A2 — `grade_forward_log()` exists (`engine/basket_breadth_divergence.py:262`), needs nightly wiring only |
| C/risk_radar US grader | | **ALREADY-BUILT** | Grader wired nightly (`engine/risk_radar_audit.py`, `engine/run.py:614`); LOG-ONLY verdict = audit inventory error → PR-A2 one-line fix; ledger is TIME-starved (§0.5.1) |
| C/foresight_policy_calendar | | GO-IF-TRIVIAL | PR-A2 discretionary: date-accuracy pass vs federal_register store; if >half-day, print DEFER in the PR |
| C/oracle ledgers | | NO BUILD | TIME-starved (earliest maturity 2026-07-30); watch, don't overfit early — Codex agrees |
| D | avoid_long/de-risk as first-class output | **GO** | PR-C2 (BD-2+BD-3 forward ledger, avoid-long framing only) |
| D | Short-side panel on committee/measurement | PARTIAL | Accrual row in measurement.html evidence panel only; no board chips until ledger matures (ladder law) |
| E | qledger narrative_reliability lobe | RESHAPE | Data not mature (max n_dates=9 of 25; 5d grades only). Ship descriptive accrual TABLE (PR-A1 sub-panel), not a lobe. Channel-level cells lack n≥25 — printed honestly |
| F | Long-hold as second horizon | ALREADY-BUILT | Long-hold program owns it (G1-DEFERRED, A2 registered, LT-1..4). No action |
| G | Options de-escalation games | **DON'T (yet)** | All behind accrual gates (~2026-10/12); W-F parked. No new options tissue consumption (rails program §10) |
| H | Dispersion trust-conditioner | **GO (close the loop)** | PR-B2 — DISP-GATE-1 registration + harness (already-chartered L3 work, unfinished) |
| I | EDGAR solvency/fragility lobe | **DON'T** | = G1 F1 family (frozen, deferred) + fundamentals buildout (own program). No third lobe (two-lobe cap) |
| J | Short-volume squeeze/informed split | DEFER | SLF-001 killed FTD variant only; FINRA daily SV species need own preregs under L1 ladder — Phase-2, after PR-C2 ledger accrues |
| K | Macro stress/positioning/vintage games | DEFER | L6 gate stands (Phase-0 must beat noisy-sector precedent). Data confirmed deep. Candidate for a future charter, not this program |
| L | altdata/AI/foresight claim-quality lab | PARTIAL | = qledger reliability table (PR-A1) + foresight grader (PR-A2). No new lab |
| M | Research Factory expansion | **GO (scoped)** | PR-C3 — blocked-queue surface + adapter fan-out. Non-Oracle *new* adapters (long_hold/qledger/options) deferred until sources have candidates worth routing |
| N | Operator action capture on alerts | **GO (admin-side)** | PR-C4 — alert IDs + admin Alerts capture + missing `overrode` button. NO public write endpoint (RUL-8) |
| N | Operator grading harness | ALREADY-QUEUED | Post-Fable queue item (rails §2); ledger n far below Wilson floor anyway |
| O | Regional boards | NO BUILD | TIME-starved; accrual working as designed |
| Lobe-1 | Abstention Lobe | RESHAPE | = PR-B1 experiments. No charter (two-lobe cap; taxonomy: these are R1 experiments, not a lobe) |
| Lobe-2 | Sponsorship Repair Lobe | PARTIAL | B0 only (PR-C1). Lifecycle grammar = L10, blocked on PIT short interest ~2027+ |
| Lobe-3 | Avoid-Long Lobe | **GO** | = L1 Phase-1 (PR-C2); L1 already chartered — this is its next wave, not a new lobe |
| Lobe-4 | Claim Reliability Lobe | RESHAPE | Descriptive table now (PR-A1); lobe question re-opens when any family hits n_dates≥25 |
| Lobe-5 | Data Fitness Lobe | FOLD | The useful part IS the evidence-gap panel (PR-A1). run_status/circuit-breaker already exists |
| Lobe-6 | Regime-of-Selection Lobe | DUPLICATE | = chartered L3 + DISP-GATE-1 (PR-B2) |
| Site/measurement | Evidence cockpit | **GO** | PR-A1 |
| Site/committee | Deliberation additions | DEFER | Abstention candidates need PR-B1 evidence first; RF queue lives on its own surface |
| Site/alerts | Feedback capture | **GO (admin-side)** | PR-C4 |
| Site/qa_bottom_sensors | Bottom lobe lab | PARTIAL | Sponsorship column + coverage counts ship with PR-C1; label tables wait for accrual |
| Site/regional | Accrual panels | DEFER | Measurement panel covers ledger clocks centrally first |

**Codex's "What Not To Do" list:** adopted verbatim — it matches standing rulings (no fusion, no LLM origination, no root-gate options direction, no short entries from avoid evidence, vintage-first, display-only ≠ weak-but-usable).

---

## §2. Program rulings

- **RUL-1 (no new lobes):** this program charters ZERO lobes. L1/L3 remain the chartered set (two-lobe cap). Wave B ships as R1 experiment batches; the qledger table and evidence panel are display/governance surfaces.
- **RUL-2 (labels before models):** no meta-model, classifier, or trained router on any surface until its family reaches its registered floors. Codex's meta-labeling task list is adopted as a *labels roadmap*, recorded here for the future, not built.
- **RUL-3 (avoid-long quarantine + contamination stamp):** PR-C2 is avoid-long ONLY. **The PR-C2 prereg is itself written after seeing the Phase-0 descriptive surface and therefore carries `derived_from_surface: bd_phase0` with a compensating gate (verdict on forward OOS accrual only + primary threshold ≥8pp, stricter than the ≥5pp reading that selected BD-2/BD-3; §6).** BD-3's short-favorable>adverse observation stays quarantined as descriptive; any future short-entry prereg is out of program scope and carries its own stamp.
- **RUL-4 (clocks, not busywork):** TIME-starved ledgers get maturity clocks on the evidence panel, never make-work graders. The panel must render the TIME-vs-BUILD distinction so "16 grader-starved" can never again be read as 16 builds.
- **RUL-5 (FDR accounting):** Wave-B experiments pool into flat `fdr_family='replay'` with budgets logged BEFORE runs. Declared budgets: WAIT-GRID-1 = 10 cells (pooled sum 15→25), DISP-GATE-1 = 6 primary cells (pooled sum →31). PR-C2 logs its 2 trials (BD-2, BD-3 forward verdicts) into the existing `short_side` family. Every report prints the cumulative pooled SUM and notes the TrialLedger max()-basis divergence (§0.5.6); descriptive-only batches compute no DSR.
- **RUL-6 (de-escalation shape):** evidence panel + qledger table expose only trust/accrual fields ({family, horizon, n_obs, n_dates, hit_rate, wilson_ci_low, state, clocks}); no escalation-eligible composite; any consuming code routes through `constitution.grant_authority()` at ≤ A3_DE_ESCALATE (the `altdata_brain` template).
- **RUL-7 (sponsorship publish path — RESOLVED):** panels measured on-host: `panel_s.parquet` 6.1MB + `panel_m.parquet` 39MB (both fresh 2026-07-05) ⇒ **R2 publish + download shim** (git rejected at 45MB). No prior D5 publish spec exists (`build_oracle_panel.py:11-14` says only "should eventually be published to R2") — PR-C1 DEFINES the publish path: named single-writer = the Mac-side oracle ops lane (upload step appended where `build_oracle_panel.py` runs), download shim in the nightly before `build_bottom_sensors`; connector's existing 'stale' state handles gaps; no new render-path compute beyond the download.
- **RUL-8 (auth wall stands):** operator capture stays behind admin auth. No public write endpoint, no CORS widening to public origins. Capture UX moves to the operator's authed console, not the public page.
- **RUL-9 (merge sequencing):** PR-B1 → PR-B2 merge strictly in sequence (both append `registry.jsonl` + `trial_ledger.jsonl`). Any PR adding synapse entries regenerates `SIGNAL_BUS.md` in the same PR; parallel PRs rebase-check `synapse.yml` before merge.
- **RUL-10 (nightly budget — corrected per §0.5.2):** CI render-path additions = breadth_divergence grader wiring (seconds) + the <1s evidence panel ONLY. The BD-2/BD-3 stamper + control sampler run on the **Mac-side off-render ops lane** (oracle_nightly pattern; single-writer commit path per RUL-P10); BD maturity grading rides whichever lane has price access (Mac ops lane preferred; never the CI render band). PR-C1's panel upload is Mac-side; its nightly cost is one R2 download.

---

## §3. Wave plan

| Wave | PR | What | Model lane | Risk |
|---|---|---|---|---|
| W0 | PR-0 | This adjudication doc (red-teamed, ratified) | Fable + Opus red-team | — |
| WA | PR-A1 | measurement.html Evidence-Gap panel: grading-closure table (TIME/BUILD split + clocks), trial budgets by family, rule-experiment registry + pooled replay count, qledger reliability accrual table (5d-only + n_dates honesty printed) | Sonnet build, Opus review | LOW |
| WA | PR-A2 | Closure fixes: audit-inventory correction for risk_radar US (grader exists — §0.5.1), breadth_divergence nightly wiring (existing pure fn), foresight policy-calendar date-accuracy IF trivial (else print DEFER) | Sonnet build, Opus review | LOW |
| WB | PR-B1 | WAIT-GRID-1 (§6.1): prereg + `_GRID_BUILDERS` entry + registration + run + report. 10 cells, budget 10 → pooled sum 25 | Fable-frozen spec §6.1, Sonnet build/run, Opus stats review | MED |
| WB | PR-B2 | DISP-GATE-1 (§6.2): PIT regime recomputation per fire date + data-reach gate + registration (6 cells → pooled sum 31) + descriptive run + report | Sonnet build/run, Opus stats review | MED-HIGH |
| WC | PR-C1 | B0 sponsorship (RUL-7): R2 publish path (new spec, Mac-side single-writer) + nightly download shim + verify connector flips + sponsorship column & coverage counts on qa_bottom_sensors | Sonnet | MED |
| WC | PR-C2 | L1 Phase-1 (§6.3): Fable-frozen prereg + Mac-side off-render BD-2/BD-3 stamper + PIT random-bar control stream + maturity grading + clocks. No board chips | Fable-frozen spec §6.3, Sonnet build, Opus review | MED-HIGH |
| WC | PR-C3 | Research Factory: blocked/awaiting_data bucket in review queue + adapter fan-out in research_factory_run + health counts | Sonnet | LOW |
| WC | PR-C4 | Operator capture completion (§0.5.8 scope): admin Alerts tab (authed, POSTs surface=alert_id), machine-readable alert IDs on the alerts feed, `overrode` button on Experiments tab | Sonnet | LOW |

Execution: PR-A1/A2/C3/C4 parallelizable in separate worktrees; PR-B1→PR-B2 sequential (RUL-9); PR-C1 needs Mac-local panel build; PR-C2 merges after its prereg is counter-signed. All PRs branch off fresh origin/main, same-day squash-merge.

## §4. What this program does NOT do (scope fences)

- No new lobes, no meta-models, no fused scores, no sizing changes (gross_mult stays 1.0).
- No options tissue consumption (accrual-gated to ~2026-10/12).
- No macro-transmission Phase-0 (L6 gate stands; noted as future-charter candidate with confirmed-deep data).
- No short entries; no re-tests of G1's frozen F1 family; no supervised bottom-sensor panel until accrual exists.
- No public write endpoints; no CORS widening.
- No re-grading of TIME-starved ledgers.

## §5. Execution mechanics

- Builders work in their own worktrees off **fresh `origin/main`**; PR-B1→PR-B2 merge strictly in sequence (registry.jsonl + trial_ledger.jsonl append race); PR-C2 is the only synapse.yml-touching PR (regenerates SIGNAL_BUS.md in-PR).
- Replay runs execute from any worktree: `scripts/run_rule_replay.py` resolves `_CANONICAL_DATA` to the absolute Mac data path (EXIT-GRID-1 pattern).
- Every study report: plain-language + "In plain English" box; the word "validated" never appears; nulls and censoring rates printed.

## §6. Frozen specs (Fable)

### §6.1 WAIT-GRID-1 (PR-B1)

- **Registered question:** "For the production fire cohort, what does waiting cost or save — how do entry outcomes change as fill delay rises 1→10 bars, at the ratified hold(21) anchor and hold(63)? Grid granularity: the 5-step delay ladder {1,2,3,5,10} traces the decay/improvement curve of fire-edge with waiting; two holds anchor tactical vs positional reads. Splits by tier_cascade and year are DESCRIPTIVE multiplicity, declared here, not verdict cells."
- Grid: `delay_n ∈ {1,2,3,5,10}` × `{hold(21), hold(63)}` = **10 cells**; `log_declared_budget(10, family='replay')` BEFORE the run; cohort `verdict_type='fire' AND verdict_grade=True`.
- Verdict criteria: **descriptive-only** (this is the L7 abstention substrate, not a promotion). Any later prereg on this surface carries `derived_from_surface: wait_grid_v1`.
- Report obligations: MAE/MFE measured **relative to the delayed entry** (cells comparable); per-cell censoring rate printed (censoring rises with delay_n); episode-clustered dispersion (fires cluster; delayed windows overlap — CIs are not independent-n); cumulative pooled replay SUM (25) printed alongside the TrialLedger max()-basis note (§0.5.6).

### §6.2 DISP-GATE-1 (PR-B2)

- Registers the existing `research/dispersion/L3_PREREG.md` design through the R1 governor: **6 primary cells** = regime arm {lean_in, neutral, lean_out} × basis {expanding-window (primary, live parity), trailing-252d (sensitivity)}; SPY-21d contemporaneous drawdown is the registered covariate ADJUSTMENT (tercile split per prereg), not extra verdict cells. `log_declared_budget(6, family='replay')`; post-B2 pooled sum = 31.
- **Feasibility gate (§0.5.7):** no historical PIT states exist — the harness recomputes `dispersion.assess()`'s expanding-window basis per fire date from a reconstructed broad-universe returns panel (same loader construction as `build_dispersion_regime.py`); it MUST verify and record the panel's earliest date, exclude fires lacking ≥252 prior panel bars, and print the exclusion count before any statistic. If exclusions gut the early tape, print that and report on what remains — a thin-cohort DEFER is a valid printed outcome.
- Descriptive-only this batch; the prereg's frozen PASS thresholds are read only at a later verdict batch per L3_PREREG.

### §6.3 BD-AVOID-1 Phase-1 (PR-C2)

- **Prereg doc:** `research/short_side/BD_AVOID1_PHASE1_PREREG.md`, committed BEFORE any ledger write. Carries `derived_from_surface: bd_phase0` (RUL-3).
- **Hypotheses (2 trials in `fdr_family='short_side'`, budget logged):** forward BD-2 and BD-3 events mark names whose LONG-side 21d stop rate exceeds a forward matched control by **≥8pp** (compensating gate: stricter than the ≥5pp Phase-0 reading that selected them), episode-clustered CI excluding 0, BH q≤0.10 within family.
- **Forward control (§0.5.4):** the Mac-side stamper writes a parallel PIT random-bar control stream — 3 controls per event, same universe and liquidity floor, seeded from event id — into the same ledger with `is_control=True`. Same single writer, append-only.
- **Verdict basis (compensation):** forward OOS accrual ONLY — post-registration events; the Phase-0 tape is never re-used for the verdict.
- **Maturity clock (§0.5.5):** prereg registers the retrospective arrival-rate estimate (BD-3 ≈ 1.4k episodes/yr, BD-2 higher) and a come-back date ≥ when n≥300 episodes/side at 21d maturity is projected (~2027-01 for BD-3; stated precisely in the prereg). **No verdict is read before floor**; until then the ledger appears only as an accrual clock row on the evidence panel.
- **Quarantine:** long-side grades only feed the verdict; short-side grades are recorded but carry no verdict criteria (RUL-3). Display: no board chips this wave.
- Grading uses the direction-aware graders from rails PR-5 (`terminal_state` for long-side, existing patterns); artifacts get vintage stamps (PR-1 helper); synapse registration + SIGNAL_BUS.md regen in-PR.

## §7. Status log

- 2026-07-06: 8-lane census complete; adjudication drafted; 2-lens Opus red-team returned APPROVE_WITH_EDITS ×2; all blocking findings folded (§0.5); program ratified; build waves dispatched.
