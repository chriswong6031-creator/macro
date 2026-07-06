# NW Rails & Tier-1 Lobes — Build Program (by Fable)

**Ratified:** 2026-07-06
**Status:** ACTIVE program. This charters what `research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md` docketed. The docket remains the taxonomy authority; this document is the build authority.
**Context:** Fable access ends ~2026-07-08. This program front-loads the three genuinely frontier-design artifacts (R1 governor, L1 charter, long-hold W1 PR-F inference harness) and locks full implementation specs so every remaining wave is executable by Opus/Sonnet without frontier design input.
**Method:** docket (Fable, red-teamed) → 8-lane repo census (Sonnet, file-level evidence) → program draft (Fable) → 3-lens Opus red-team (house-law/feasibility; stats/anti-fishing; build-executability) → this ratified revision (Fable adjudication). §0.5 prints what the red-team falsified in the draft, per house law.

---

## §0. Census corrections to the docket (printed per house law)

The 8-lane census (2026-07-06) verified the docket's §7 corrections and found three more status drifts:

1. **STALE (docket §2/R1):** "Both replay harnesses can only replay the production gate" is right, but the substrate is better than the docket implies: `data/replay/replay_boarded.parquet` (57,640 fires / 961,656 rows, 2022-06-30→2026-07-02, endpoint MAE/MFE/ret at 5/10/21/63/126d) already exists Mac-local, 100% of its 1,002 fire tickers are covered by `massive_stock_day`, and `run_delay_sweep()` (replay_standout_pipeline.py:1347) already demonstrates the fire-tape-regrade pattern R1 needs. R1 is a smaller build than the docket costed.
2. **STALE (census lane 6, corrected here):** the Oracle reversion promotion P0 forward ledger is **already built and wired** (`scripts/oracle_reversion_forward_ledger.py`, invoked from `scripts/oracle_nightly.py:825`). Accrual starts with the next nightly; `data/oracle/reversion_forward/` materializes then. Nothing to build; do not re-dispatch.
3. **CONFIRMED with numbers:** per-bar forward paths exist NOWHERE pre-computed — every tape (replay_boarded, track_record, long_hold_labels) is endpoint-stats-only. Any exit/hold rule replay must compute paths on demand from `massive_stock_day` (raw prices — `split_adjust()` mandatory) within the ERA LAW window.

## §0.5 Red-team corrections to the draft (printed per house law)

The 3-lens Opus red-team (2026-07-06) falsified the following draft claims; all are fixed in this revision:

1. **FALSE:** "`data/rule_experiments/results/*_perfire.parquet` — gitignored Mac-local (like `data/replay/*`)." `data/replay/*` is NOT gitignored — it stays out of the repo only because runners never generate it, while the nightly does blanket `git add data/`. Every new data store in this program now ships an explicit `.gitignore` entry or a declared single-writer commit path (§3.5, §6, §7).
2. **FALSE:** "EMA8 exit reuses signal_quality math verbatim: 3D resample." The canonical construction resamples on **'3B'** (3 business days; signal_quality.py:87/115/126) — '3D' is only a display label. The spec now mandates importing `signal_quality`'s own functions, never re-implementing the grid (§3.1).
3. **DEFEATED THE DOCKET:** the draft sub-scoped `fdr_family='replay.<exp_id>'`, which — since `TrialLedger.effective_n()` keys on the exact family string with no prefix pooling — would have made every experiment an isolated multiple-testing island, exactly the laundering the docket's flat `fdr_family='replay'` was designed to prevent. Restored to the flat pooled family (§3.3).
4. **VIOLATED A FROZEN PREREG:** the draft renamed long-hold's registered family to `long_hold.g1_v1` and asserted unsourced sample figures ("n=720 fires / 700 clusters") and stale Label-G counts (3,386/3,404 vs the registered 3,391/3,409), and conflated the frozen OOS split (2020-01-01→2023-12-31, OBJECTIVE.md §7) with the honest-cohort intersection window. All corrected in §8; the harness computes and prints achieved counts before any OOS statistic.
5. **MISLEADING:** "grade breakdown events with the same grading.py primitives, mirror barriers." `terminal_state()` hard-codes long-side inequality directions; flipping mult values fires liftoff immediately. PR-5 must add a direction-aware short-side grader (§6).
6. **UNBUILDABLE AS WRITTEN:** PR-9's "9 pre-registered at-entry features" — only `piotroski_f` is a column of the label parquet; the other 8 must be PIT-joined from `data/edgar/fundamentals_panel.parquet` via `collectors.edgar.as_of_cross_section()` (§8).

---

## §1. Program-level rulings (Fable)

- **RUL-P1 (guardrail compliance):** exactly two lobes are chartered by this program: **L1 Short-Side** and **L3 Dispersion**. The exit-regret ledger ships as **R1's first registered rule-experiment batch** (a rail artifact), NOT as an L2 charter. L2's charter is deferred until the regret evidence exists and a lobe owner can carry it. The docket's two-lobe cap protects *review and nightly bandwidth*; on that accounting this program adds one nightly artifact (dispersion JSON, seconds) and zero new nightly graders — L4 instrumentation (RUL-P7) and the R1 rail are off-render and review-light by construction, so they do not draw on the budget the cap protects.
- **RUL-P2 (R1 shape):** R1 v1 is a **fire-tape × policy-grid replay**, not a gate re-run engine. Entry events come from the existing production fire tape; rules parametrize *cohort filter*, *fill delay*, *exit policy*, and *per-fire weight*. Re-running the gate itself with modified parameters remains `replay_standout_pipeline.py` territory (a `gate_fn` injection extension is docketed as R1 v2, post-Fable). Portfolio-level construction (position interaction, cash ledger) is OUT OF SCOPE (docket L8 → Mastermind).
- **RUL-P3 (governor is law):** the R1 runner MUST refuse any policy grid not registered in the rule-experiment registry before the run (content-hash match). No interactive/exploratory mode exists. Every run pools into the flat `fdr_family='replay'` TrialLedger family. All outputs are display-only; promoting any rule to live behavior requires the standard PREREG gauntlet outside R1. **Forking-paths law:** a descriptive surface, once seen, contaminates later preregs on the same tape — any promotion prereg written after a descriptive batch must carry a `derived_from_surface: <exp_id>` stamp and state how its gate compensates (stricter threshold or fresh OOS). Note: `scripts/check_trial_registration.py` name-patterns do NOT match `run_rule_replay.py` — the governor itself is the enforcement layer here, not the CI lint.
- **RUL-P4 (R3 minimum):** R1 outputs refuse to serialize without a **vintage stamp**: `price_plane_id`, `adjustment_mode`, `universe_as_of`, `frame` (pit basis), `survivorship_biased`, `coverage_frac`, `dead_name_coverage_pct`, `era_law_cohort`. The stamp helper is a shared engine module usable by any future study. Full vintage-matrix work (e.g. FINRA true vintages) stays with Signal Commons — not this program.
- **RUL-P5 (L3 is promotion, not invention):** the dispersion lens promotes the EXISTING `engine/dispersion.py` output (lean_in/lean_out/neutral, gross_mult clamped 1.0) to a registered nightly artifact + display chip. No new math. Its shadow-ladder question runs as a registered R1 experiment (DISP-GATE-1), not a bespoke harness.
- **RUL-P6 (L1 asymmetry is a question):** the short-side charter pre-registers "do bottoming edges invert?" as a hypothesis, never a premise. Phase-0 builds the breakdown event tape and grades it with a direction-aware short-side grader alongside long-side grades on the same events, analyzed as a **paired within-event contrast** (never two independent samples). No site surface, no chip, no claims this wave.
- **RUL-P7 (L4 is instrumentation-first):** the decision-quality lobe is NOT chartered. This program ships only the accrual instrumentation (operator action ledger + admin capture) because calendar time is the binding constraint on grading. The grading harness generalizing `btc_override_ledger.py` is a post-Fable Opus wave.
- **RUL-P8 (ESX under NC-2 deferral):** ESX Amendment-2 T1 studies (`esx_insider_sponsor`, `esx_macro_release`, `esx_pos_reset`) and W2 S-SQ are AUTHORIZED to run post-Fable at phase0 for display/context value with an explicit **no-CHIP cap** until the eq_band NC-2 lookup ships. Recorded here so no Fable decision blocks the queue later.
- **RUL-P9 (bandwidth):** nightly additions in this program: dispersion lens JSON (≪30s) and the operator action ledger (server-side, zero render cost). Everything else is off-render (manual/ops lane). No new nightly compute beyond these.
- **RUL-P10 (new data stores must declare their commit path):** every new write path in this program states, in its PR, one of: (a) explicit `.gitignore` entry (Mac-local/server-local store), (b) git-committed with a named single-writer, or (c) R2 artifact. Nothing new may ride the nightly blanket `git add data/` implicitly. This PR-set also retroactively gitignores `data/replay/*.parquet` to make the existing convention explicit.

---

## §2. Wave plan

| Wave | PR | What | Model lane | Risk |
|---|---|---|---|---|
| W0 | PR-0 | This program doc + docket cross-stamp | Fable + Opus red-team | — |
| W1 | PR-1 | R1 core: `engine/rule_replay.py` + `engine/vintage_stamp.py` + rule-experiment registry + governor + tests | Sonnet build, Opus review | HIGH — keystone |
| W1 | PR-2 | R1 runner + charter/prereg docs + synapse registration | Sonnet | MED |
| W1 | PR-3 | EXIT-GRID-1: first registered experiment batch (the exit-regret ledger) + report | Sonnet run, Opus stats review, Fable adjudication | MED |
| W2 | PR-4 | L3 dispersion lens: registered nightly artifact + chip + prereg + DISP-GATE-1 registration | Sonnet | LOW |
| W2 | PR-5 | L1 short-side charter + breakdown event tape (Phase-0) | Fable charter, Sonnet build | MED |
| W3 | PR-6 | R2 grading-closure audit script + governance artifact | Sonnet | LOW |
| W3 | PR-7 | R4 contract governance: schema_version + consumer registry + drift check | Sonnet | LOW |
| W3 | PR-8 | L4 instrumentation: operator action ledger + admin capture endpoint | Sonnet | LOW |
| W4 | PR-9 | Long-hold W1 PR-F kill-test study harness + first run (expect DEFER; print it) | Fable spec, Sonnet build, Opus stats review | HIGH |
| W4 | PR-10 | OTA W2 formal prereg: Opus red-team + Fable counter-sign (adjudication only, no build) | Opus + Fable | LOW |

**Merge sequencing law:** W1 PRs merge strictly in sequence (PR-1 → PR-2 → PR-3), never in parallel — `registry.jsonl`, `synapse.yml`, and `SIGNAL_BUS.md` are append-only git files subject to the known registry-drift merge race; regenerate SIGNAL_BUS.md on the trailing merge. PR-4/5/6/7/8 may run in parallel worktrees but must rebase-check synapse.yml before merge.

Post-Fable queue (mechanical, specs locked, listed for the Opus era): Factor P3 H1–H5 harnesses; ESX S-SQ + Amendment-2 T1 studies (under RUL-P8); L4 grading harness; R1 v2 `gate_fn` injection; L2 charter (once EXIT-GRID-1 evidence exists); tax-lot sensitivity experiment on the Oracle 21d exit (register through R1); ThetaData signing sessions (ops, market-calendar-gated); Options Q4-26 verdicts (time-gated); kernel FDR batch 2026-10 (time-gated).

---

## §3. PR-1 spec — R1 core (`engine/rule_replay.py`, `engine/vintage_stamp.py`, `engine/rule_experiments.py`)

### 3.1 Rule spec (frozen v1 vocabulary)

A **RuleSpec** is a frozen dataclass serialized to JSON with a stable content hash (sha256 of canonical-JSON, sorted keys):

```
RuleSpec:
  spec_id: str            # human slug, e.g. "exit_grid_v1/hold_21"
  cohort: CohortFilter    # which fires
  delay_n: int            # fill offset in bars (default 1 = production next-bar fill)
  exit: ExitPolicy        # one of the frozen v1 policies below
  weight: "full"          # v1: constant weight only; sizing variants are v2
  horizons_ref: [126]     # reference horizon(s) for regret metrics
```

`CohortFilter` v1: conjunction of equality/threshold predicates over existing replay_boarded columns ONLY (`verdict_type`, `verdict_grade`, `tier_cascade`, `align_tier`, `sector`, `year`, `washout_proximity`, `ext_grade`, …). No derived features in v1 — that is where fishing hides. Grid granularity must be justified in the registry `question` field.

`ExitPolicy` v1 (frozen enum — extending it requires a program amendment logged here):
- `hold(H)` — time exit at H bars, H ∈ {5, 10, 21, 42, 63, 126}. `hold(21)` is the Oracle-ratified anchor.
- `ema_trail(span=8, resample='3B')` — exit on the canonical EMA8 tail-flag. The canonical construction is the `ema_trail` column produced by `engine.signal_quality` on the **3B** (3-business-day) resampled close (span=8, min_periods=8), with the fresh-breach mask per `signal_quality.analyze()` (`below & ~prev_below & rising_into`). The builder MUST import and call `signal_quality`'s functions on the bare close series — never re-implement the resample grid. The parity test compares against `signal_quality` output, not a hand-rolled grid.
- `trail_stop(pct)` — high-watermark trailing stop, pct ∈ {8, 12, 15, 20}.
- `barrier(stop_pct, target_pct)` — bracket exit, first-touch on close (no intraday assumption; close-only law).
- All policies are evaluated close-to-close with next-bar-after-signal execution at `delay_n`; exits fill on the close of the triggering bar (conservative; stated in every report).

### 3.2 Path computation

- Price plane: `massive_stock_day` per ticker, `split_adjust()` applied — import it from `scripts.replay_standout_pipeline` (module-level function behind an `__main__` guard; importable directly, though it pulls the full pipeline import graph — acceptable for a Mac-local off-render runner).
- For each fire: forward close path from fill bar to `fill + max(horizons_ref)` (126 bars v1). Compute per-policy: `exit_bar_offset`, `exit_ret`, `mae_to_exit`, `mfe_to_exit`, `holding_days`, `censored` (path shorter than policy needs), and regret metrics vs reference: `foregone_mfe = max(0, fwd_mfe_126 − mfe_to_exit)` and `avoided_mae = max(0, |fwd_mdd_126| − |mae_to_exit|)`.
- ERA LAW: rows split into `verdict_grade=True` (2021+ massive, uncensored) vs survivor-biased cohorts; absolute rates may ONLY be reported on the former; the latter appears as within-cohort deltas with `survivorship_biased=True` stamped.
- Performance envelope: 57,640 fires × ≤15 policies × ≤126 bars is minutes-scale vectorized work; the runner is Mac-local, off-render, and must not be wired into daily.yml.

### 3.3 Governor (`engine/rule_experiments.py` + `data/rule_experiments/registry.jsonl`)

- Append-only JSONL registry, git-committed (single-writer: the registration CLI; never written by the nightly). Each entry: `exp_id`, `registered_at` (server-side stamp, never caller-supplied), `question` (one sentence, including grid-granularity justification), `spec_hashes` (the full enumerated grid — every RuleSpec hash), `n_floor` (minimum verdict-grade **fires** per cell; default 300 — note this is a raw-fire floor, distinct from the episode-CLUSTER floors (n≥25 clusters) used by PR-9/PR-8; inferential reporting must additionally state the episode-cluster count per cell), `declared_budget` (= grid size), `verdict_criteria` (frozen text, or the literal string `"descriptive-only"`), `derived_from_surface` (null, or the exp_id of a previously seen descriptive surface — mandatory honesty stamp per RUL-P3), `status` (`registered → executed → reported`).
- **FDR accounting is pooled and flat:** every registration calls `TrialLedger.log_declared_budget(grid_size, family='replay')` BEFORE the run — the docket-mandated single family, so cumulative trials against the tape accumulate across ALL experiments (TrialLedger keys on exact strings; sub-families would create isolated islands and are prohibited). Per-experiment BH panels may be computed for readability, but any `deflated_sharpe`/effective-n arithmetic uses `family='replay'`. Every results summary MUST print the cumulative pooled trial count to date (the docket's "force the number to be stated" requirement).
- The runner (`scripts/run_rule_replay.py`) takes `--exp-id`, loads the registry entry, recomputes every spec hash from its own grid construction, and **hard-fails on any mismatch or missing registration**. No `--adhoc` flag exists; adding one is a house-law violation.
- Re-running an executed experiment is allowed (idempotent regrade) but appends a new `executed` event; results files are keyed by `exp_id` + run date.
- Nulls are printed: the results summary always includes every cell in the declared grid, including empty/failed cells.

### 3.4 Vintage stamp (`engine/vintage_stamp.py`, R3 v1)

`vintage_stamp(price_plane_id, adjustment_mode, universe_as_of, frame, survivorship_biased, coverage_frac, dead_name_coverage_pct, era_law_cohort) -> dict` — a tiny, dependency-free helper producing the 8-field stamp. `rule_replay` results refuse to serialize without one. `dead_name_coverage_pct` reads `data/edgar/_dead_name_coverage.json` when present (currently 38.3%), else `null` with a `stamp_degraded=True` flag. Designed for reuse by any study harness (long-hold PR-F consumes it too).

### 3.5 Storage & CI

- `data/rule_experiments/registry.jsonl` — git-committed, single-writer registration CLI (RUL-P10 path b).
- `data/rule_experiments/results/<exp_id>_summary.json` — git-committed, written by the runner, small, stamped (path b).
- `data/rule_experiments/results/<exp_id>_perfire.parquet` — Mac-local; **explicit `.gitignore` entry ships in PR-1** (path a). PR-1 also adds `data/replay/*.parquet` to `.gitignore` retroactively (RUL-P10).
- Synapse registration: `rule-experiment-registry` + `rule-experiment-summaries` as `infrastructure`/`display` tier, `horizon_role: context`, `scored_path_surfaces: []`, producer `scripts/run_rule_replay.py`, cadence `manual`.
- Tests: synthetic-fixture-only (no dependence on Mac-local data): governor refusal paths, hash mismatch, EMA8-parity against `signal_quality` on a synthetic series, barrier/trailing correctness on hand-computed paths, censoring, era-law splitting, stamp-refusal, pooled-family assertion (registration writes family='replay' exactly).
- `docs/SIGNAL_BUS.md` regenerated in the same PR (synapse-count drift law).

---

## §4. PR-3 spec — EXIT-GRID-1 (the exit-regret ledger)

**Registered question:** "For the production fire cohort, what did each frozen exit policy cost in foregone MFE versus save in avoided MAE, relative to hold(126) — and why did the two historical survivors (EMA8 tail-flag as display, 21-session time-exit on Oracle) survive?"

- Cohort: `verdict_type='fire' AND verdict_grade=True` (n≈49,939). Secondary descriptive split by `tier_cascade` and `year`.
- Grid: the full v1 ExitPolicy enum = 6 holds + 1 ema_trail + 4 trail_stops + 4 barriers ({-5,+8},{-5,+15},{-8,+15},{-8,+25}) = **15 cells**; `log_declared_budget(15, family='replay')`.
- Verdict criteria: **descriptive-only.** This batch carries the settled exit-routing NO-GO honestly (joint DD-AND-capture 37–43% vs 70% floor; "drawdown control is an ENTRY problem"). Its job is to EXPLAIN the survivors and produce the regret surface, not to promote an exit rule. Per RUL-P3, this descriptive surface is itself a contamination event: any later promotion prereg on this tape carries `derived_from_surface: exit_grid_v1` and a compensating gate.
- Outputs: summary JSON (per-cell WR, mean/median exit_ret, mean foregone_mfe, mean avoided_mae, regret ratio, n fires, episode-cluster count, censoring rate; era-law + tier splits; cumulative pooled replay trial count) + `research/rule_replay/EXIT_GRID_1_REPORT.md` (plain-language, "In plain English" box per house style; the word "validated" must not appear — per epistemics house law; note `check_validated_claims.py` does not scan research/*.md, so this is discipline, not CI).
- Opus stats review required before the report merges (overlap/clustering honesty: fires cluster in episodes; report episode-clustered dispersion or state clearly that CIs are not independent-n).

---

## §5. PR-4 spec — L3 dispersion lens (chartered lobe, smallest)

- `scripts/build_dispersion_regime.py`: the broad-universe returns panel is NOT exported by `build_stock_library.py` (it is a local `_ext_closes` inside `main()`, call site line ~1249) — reconstruct it the same way: load the same ext-universe closes source and call `dispersion.assess(closes.pct_change(fill_method=None).tail(280))`, naming the loader so state parity with the board is preserved. Emit `data/dispersion/regime.json` with **field names mirroring `assess()` output verbatim**: `{as_of, state: lean_in|neutral|lean_out, dispersion_pctile, avg_corr, shadow_gross_mult, gross_mult_live: 1.0, passport: <assess()'s passport block carried through — basis/verdict/survives provenance must travel with the artifact>, history: [last 252 states]}`.
- Synapse: `dispersion-regime` display tier, `horizon_role: context`, `scored_path_surfaces: []`.
- Display: one chip on the US board/macro page ("Selection regime: dispersion 72nd pctile — selection pays / one-macro-trade tape"), EN/ZH, no `title=` translation (CI law).
- PREREG (`research/dispersion/L3_PREREG.md`): the shadow-ladder question — "conditioning entry TRUST (not sizing) on lean_out regimes: do fires opened in lean_out show worse stop5/dead-money than lean_in at 21d?" — registered as R1 experiment **DISP-GATE-1** (cohort split by historical regime state; descriptive first, gates frozen in the prereg for a later verdict batch). Two design obligations the prereg must carry: (1) **basis reconciliation** — live `assess()` uses an expanding-window percentile, so the study reconstructs the LIVE expanding-window basis as primary (flagging its non-stationarity) plus a trailing-252d sensitivity, both printed; (2) **regime-as-outcome confound** — dispersion/correlation regimes correlate mechanically with drawdowns, so regime is measured strictly at/before fire_date and the prereg registers a contemporaneous-market-drawdown covariate control, so "lean_out fires do worse" is not just re-discovering that stressed tapes are stressed.
- HARD CONSTRAINT: `gross_mult` stays clamped 1.0 (US_BOARD_MEASUREMENT §Study-3 precedent: no measured selection-IR edge). This wave changes display and measurement only.

---

## §6. PR-5 spec — L1 short-side charter + Phase-0 tape

**Charter doc:** `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` (Fable-written). Contents: objective (avoid/de-risk lens for a drawdown-identity operator; NOT a shorting-execution program), the asymmetry-is-a-question ruling, species-inversion hypothesis space (each of the 13 entry species' mirror image listed with mechanism sketch and which are testable on current data), evidence constraints (no PIT short interest — FINRA daily short-volume panel and froth legs only), PREREG ladder identical to entry species (display-chip → shadow → confirmer; ≥5pp on constitution axes, episode-clustered bootstrap, BH-FDR q≤0.10, n≥300/side), forward-ledger plan, and a graveyard section seeded with the known priors (EMA8 = tail-flag only; exit-routing NO-GO; GEXR era-sign flip means options tissue is vol-context only; single-name gamma_regime structurally constant).

**Phase-0 build (`scripts/research/dump_breakdown_events.py`):** an event tape, not a signal.
- Universe: replay_boarded fire tickers ∪ current board universe (bounded, ~1-2k names), massive store, split-adjusted.
- Three breakdown event definitions (BD-1 distribution-under-pinned-index; BD-2 failed-reclaim after stopped fire; BD-3 EMA8-breach + defensive bid). **The numeric freeze authority is `research/short_side/BD_PHASE0_PREREG.md`, committed BEFORE the dump runs** — this program doc deliberately does not restate the thresholds (two sources drift; the prereg is the single source of truth). The prereg must freeze every window, threshold, and sigma before execution.
- Grading: `engine/grading.py`'s `terminal_state()` **hard-codes long-side inequality directions and CANNOT be mirrored by flipping mult values** (a liftoff_mult<1 fires immediately). PR-5 adds a direction-aware short-side grader — `terminal_state_short()` reversing the barrier inequalities (adverse = close≥entry·stop_mult, favorable = close≤entry·liftoff_mult), reusing `fill_index`/`forward_metrics` — and publishes BOTH short-side and long-side grades on the same events. The asymmetry readout is a **paired within-event contrast**: CIs computed on paired differences, never treated as two independent samples.
- Output: `data/research/breakdown_events.parquet` (Mac-local; **explicit `.gitignore` entry ships in PR-5**) + committed summary JSON with vintage stamp. NO site surface, NO chip, NO synapse consumer this wave. n and base rates printed; nulls printed.

---

## §7. PR-6/7/8 specs — governance rails + L4 instrumentation

**PR-6 (R2 audit):** `scripts/audit_grading_closure.py` — walks a declared inventory of forward ledgers (seeded from the census: qledger, board_ledger, china_board, sector_cycles, china_sector_cycles, country_cycles, breadth_divergence, risk_radar{,_intl}, market_state, oracle forward/live, reversion_forward, override_ledger, foresight, froth log, species ledgers), and for each reports: grader wired (Y/N + module), n_logged, n_graded, last_graded_at, tune step (Y/N), verdict `CLOSED / GRADER-STARVED / LOG-ONLY`. Emits `data/governance/grading_closure.json` + a markdown table appended to `docs/GRADING_CLOSURE.md`. Runs as an end-of-collect audit step (seconds). The census already found the shape: risk_radar_intl = only complete loop (0 graded, data-starved); breadth_divergence/risk_radar-US/market_state = LOG-ONLY. The audit makes this standing and visible instead of rediscovered per-program. Fixes are per-program follow-ups, not this PR.

**PR-7 (R4 contracts):** extend `site/factordata/contracts/artifact_manifest.json` entries with `schema_version` (semver string) + `schema_fields` (sorted top-level field list, machine-diffable); add `scripts/check_contract_drift.py` that fails when a published contract JSON's actual top-level fields diverge from the manifest (catches the "34-field china_standouts consumed by a real-money bot with no handshake" hazard). Wire into CI as a warn-first tier (hard-fail after one clean week — ratchet note in the script). Document the consumer registry vocabulary (`bot:*`, `terminal:*`) in the manifest header.

**PR-8 (L4 instrumentation):** `data/operator/action_ledger.jsonl` — **gitignored server-local ledger** (RUL-P10 path a; the admin server is the single intraday writer, and the ledger must NEVER be staged by the nightly blanket `git add data/` — this is the same intraday-writer isolation the whitehouse ledger law exists for; off-band backup rides the admin host's existing backup path). Schema: `ts` (server-stamped), `actor='operator'`, `surface` (alert id / experiment id / board name), `action` ∈ {acted, dismissed, overrode, snoozed}, `direction_note` (free text ≤280), `latency_s` (server-computed vs alert emit ts when known). Endpoint: `admin/server.py` is a stdlib `BaseHTTPRequestHandler` (NOT FastAPI) — add an `if path == '/api/actions'` branch in `do_POST`, calling `self._guard(write=True)` first (session cookie + CSRF double-submit + origin/host check, same as `/api/flags/toggle`), body via `self._body()`, server-stamped ts. Minimal capture buttons on the admin Experiments/Alerts tabs. Registered in synapse as infrastructure tier (path stated as gitignored-local storage). Grading harness = post-Fable wave (template: `btc_override_ledger.py` Wilson/bootstrap pattern; qledger claims as the counterfactual source). The point of shipping NOW: the ledger accrues only in calendar time, and n≥25 graded operator actions is the same Wilson floor the cortex A2 gate uses.

---

## §8. PR-9 spec — Long-hold W1 PR-F kill-test harness (other-program, Fable-critical)

**Why in this program:** it is the one active-program critical-path item that genuinely needs frontier-design inference discipline before Fable access ends (census lane 6 verdict). The label substrate is DONE (W1-PR-E-r3: 113,542 fires labeled; manifest honest). The study has never run.

**`scripts/research/long_hold_study.py` (spec frozen here; Sonnet builds; Opus reviews stats). The frozen prereg `research/long_hold/OBJECTIVE.md` is the design authority — where this section and OBJECTIVE.md could ever diverge, OBJECTIVE.md wins.**
- Question (OBJECTIVE.md, G1): do at-entry features separate `missed_hold` (tactical win that kept going) from `tactical_only` (win that faded) — i.e., is there any entry-time signal for "this one is a keeper"?
- Features: the 9 pre-registered at-entry features from OBJECTIVE.md §5 ONLY. **Availability note (census-verified):** only `piotroski_f` is a column of `long_hold_labels.parquet`; the other 8 (quality_z, profitability_z, sue, insider_cmp, interest_coverage, dilution_flag, gross_margin_trend, archetype) are read PIT from `data/edgar/fundamentals_panel.parquet` via `collectors.edgar.as_of_cross_section(fire_date, panel=...)` at each fire date. Per OBJECTIVE §5: drop (and document) any feature with <20% non-null coverage in the honest cohort; do not error.
- Design: episode-clustered comparison per feature; BH-FDR across the 9-feature family under the **frozen registered family `fdr_family='long_hold'` exactly as OBJECTIVE.md §6.1 locks it** (the g1_v1 sub-scope lives in the exp_id/reason metadata only, never the family string — TrialLedger keys on exact strings); declared budget 9 logged before the run; label-reshuffle null within cohort-year strata (preserves base-rate drift); episode-cluster floor n≥25 clusters per arm (OBJECTIVE §6.3).
- OOS discipline: the OOS split is the **frozen boundary per OBJECTIVE.md §7 — fire dates 2020-01-01 through 2023-12-31, opened once**. The honest-cohort intersection within it (~2021-07-06→2021-10-25, per OBJECTIVE §8) is expected to be thin. **The harness computes and PRINTS the achieved honest-OOS fire and episode-cluster counts BEFORE running any OOS statistic** (OBJECTIVE §8 requirement); no sample figures are asserted in advance by this document.
- Survivorship routing: consume the manifest's `survivorship_biased`/`gap_leg_crossed` fields; verdict-grade inference on honest cohorts only; survivor-biased cohorts reported as descriptive deltas. Vintage-stamp the output (PR-1's helper).
- Label-G caveat: `sector_laggard_winner` is ~99.5% missing-benchmark artifact (**3,391/3,409 per OBJECTIVE.md Amendment A1** — the registered figures) — the study MUST run the pre-registered market-benchmark sensitivity (Amendment A1) and print both, and must not silently drop Label-G fires.
- Pre-committed branches: G1-SURVIVE / G1-KILL / **G1-DEFER on n-floor** (expected: the honest OOS intersection is ~3.5 months; a DEFER routes to dead-name/benchmark remediation per masterplan, and W2 clocks/falsifiers proceed regardless — already authorized).
- Output: `research/long_hold/W1_PRF_REPORT.md` + committed summary JSON. The word "validated" may not appear (epistemics house law; research/*.md is not CI-scanned — discipline, not automation).

---

## §9. PR-10 spec — OTA W2 formal prereg adjudication

`research/oracle_asymmetry/W2_FORMAL_PREREG.md` exists (#1525). Action: Opus red-team (house-law lens + stats lens: hindsight membership, sector drift, n=31 windows, leave-one-out sensitivity, modern-track boundary 2022-06-30) → Fable counter-sign appended to the doc with any conditions → status flips from draft to REGISTERED. No harness build; the run exists. Scoring-tier promotion still requires the registered gates to pass on the registered run — this adjudication only closes the "display-only pending registration" loop.

---

## §10. What this program does NOT do (scope fences)

- No held-book/portfolio construction, no sizing changes, no `gross_mult` unclamping (L8 → Mastermind; R4 carries the contract only).
- No new options tissue consumption beyond documented priors (GEXR = vol-context, era-sign; W-F parked behind its accrual gate).
- No kernel consumers before the 2026-10 FDR batch; no LLM-originated signals anywhere (constitution).
- No macro transmission fingerprints (L6 stays gated on its Phase-0 beating the noisy-sector precedent).
- No event-playbook lobe (L9 remains a Signal Commons wave).
- The docket's L5 liquidity/execution: tax-lot sensitivity on the Oracle 21d exit is CHEAP and REGISTERABLE as a future R1 experiment, but it is post-Fable queue, not this window (it needs holding-period tax-boundary spec work that shouldn't be rushed).

## §11. Status log

- 2026-07-06: Program drafted; 8-lane census complete; 3-lens Opus red-team returned APPROVE_WITH_EDITS ×3; all blocking findings adjudicated and folded in (§0.5); program ratified; W0 PR-0 opened.
- 2026-07-06 (same day): **BUILD COMPLETE — all waves shipped.** PR-0 #1545 (program). W1: #1553 (R1 core + governor + vintage stamps; 3 review blockers fixed pre-merge: pooled-sum trial count, lifecycle governor merge, full-history EMA anchor), #1568 (runner + EXIT-GRID-1; post-review correction: never-triggered stops are held-to-reference policy outcomes, not censored — trail-stop cells sign-flipped, correction printed in the report). W2: #1552 (L3 dispersion lens live), #1558 (L1 chartered; Phase-0 paired within-event verdict: long side stops 20–49pp more than short side achieves favorable, all clustered CIs exclude 0 → AVOID-not-SHORT evidence; BD-3 strongest arming condition). W3: #1556 (R2 closure audit first run: 7 CLOSED / 3 LOG-ONLY / 16 GRADER-STARVED), #1547 (R4 contract drift check, warn→hard 2026-07-13), #1550 (L4 operator action ledger accruing). W4: PR-9 ABORTED — a concurrent session shipped the G1 kill-test first (#1544, G1-DEFERRED); #1551 (OTA W2 prereg counter-signed REGISTERED-WITH-CONDITIONS C1–C9). EXIT-GRID-1 survivors verdict: EMA8 tail-flag is the only signal-driven exit beating every hold on WR (0.623, regret ratio 0.75); hold(21) is the shortest hold within ~1.3pp of the WR maximum — efficiency, not an inflection. Cumulative pooled replay trials: 15. Ops incident log: three main-red episodes absorbed mid-program (synapse drift 135→136, read-gate undeclared readers ×2) — the moving-trunk merge protocol in §2 held.
