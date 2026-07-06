# NW Final-3 Lobes — Adjudication of the Codex Plan + Fable Masterplan

**Date:** 2026-07-06 (final Fable window)
**Source under adjudication:** `research/NW_FINAL3_LOBE_UPGRADE_PLAN_FOR_CLAUDE_BY_CODEX.md` (imported this PR)
**Method:** 6 Sonnet census lanes (repo-verified every factual claim) + 4 Opus red-team critics (per-lobe stats/methodology + architecture) + Fable adjudication.
**Program authority consumed:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` (rails + L1/L3 charters), `research/NW_FUTURE_LOBES_DOCKET_BY_FABLE.md` (taxonomy + two-lobe cap), `research/CODEX_NW_GAP_MAP_ADJUDICATION_BY_FABLE.md` (DISP-GATE-1 GO), `research/dispersion/L3_PREREG.md` (frozen), `research/rule_replay/R1_CHARTER.md` (governor law).

> **In plain English:** Codex wrote a third paper proposing upgrades to the last three "institutional realism" layers of the Neural Web: how we exit positions, when stock-picking should be trusted at all, and whether our edges survive real-world trading costs. We checked every factual claim against the repo and had adversarial reviewers attack the plan. The verdict: Codex read our numbers correctly and its safety guardrails are good, but over half its build plan either duplicates things that already shipped, was written before yesterday's merges, or violates our own research laws (it would have chartered a lobe our own cap forbids, and bypassed the anti-data-mining governor). We kept the good ideas, killed the illegal ones, fixed real statistical flaws its plan missed, and turned the remainder into a phased build plan that starts shipping today.

---

## 1. Overall verdict on the Codex doc

| Dimension | Grade | Notes |
|---|---|---|
| Factual accuracy of numbers | **A** | Every exit-grid WR/return/regret figure matched `exit_grid_v1_summary.json` to 3dp; regime.json and signing-gate numbers correct. |
| Currency | **C–** | Written blind to 2026-07-06 merges: WAIT-GRID-1 (pooled trials now 25, not 15), #1672 chip hide, #1681 rule-experiment registry/Evidence-Gap panel, gap-map charters. |
| House-law conformance | **D** | PR-A charters L2 (cap violation); PR-B is a governor bypass; standalone scripts where R1 registration is mandatory; §6 passport ignores PIT/forward-ledger law. |
| Statistical soundness | **C** | Misses: circular classifier labels, PIT reconstruction infeasibility, CSD universe-drift non-comparability, confound-set self-contradiction (§4.5 U1 vs U3), n-starved 294-cell matrix, uncalibrated cost model, overlap-corrected stats for long horizons. |
| Novel value | **B** | The six-exit-problems taxonomy, net-of-friction discipline, ThetaData session spec, residual-trust null-first framing, and tiered realization-quality vocabulary are genuinely useful. |

**Duplicate/stale/forbidden fraction of the PR-A..G plan: ~55–65%.** The one clean, authorized, correctly-sequenced item is PR-C (DISP-GATE-1) — Codex's own "best first branch" pick, which contradicts its own A→G ordering.

### 1.1 Claim-grid highlights (full census in provenance §8)

- **WRONG:** §0 cites two prior Codex docs by filenames that do not exist (`NW_TOP3_LOBE_POWER_UP_ANALYSIS_BY_CODEX.md`, `NW_NEXT3_LOBE_UPGRADE_PLAN_FOR_CLAUDE_BY_CODEX.md`). Actual lineage: `NEURAL_WEB_ADDITIONAL_CRUCIAL_LOBES_BY_CODEX.md` + the two Fable adjudications.
- **WRONG (implicit):** "exit_grid_v1 is the only replay experiment" — `wait_grid_v1` (10 cells) shipped 2026-07-06 in #1681; pooled `fdr_family='replay'` SUM is **25**.
- **STALE:** "Site display chip" as live state — the macro.html selection-regime chip was gated off in #1672 (UI orphan; artifact still builds; us_stocks board chip unaffected).
- **STALE:** §0's Cash/Patience deferral rationale ("needs the same R1 replay machinery built first") — WAIT-GRID-1 **is** that substrate; L7 is blocked only on the two-lobe cap and a charter owner.
- **PARTIAL:** Amihud/Corwin-Schultz live in `engine/entry_primitives.py` (lines ~311/~357), **not** `engine/validation.py`. A builder following §5.5 U1's import instruction gets an ImportError.
- **PARTIAL:** the ThetaData numbers quoted (agreement 0.8848, n=16,366) are the tape ratification (#1292) — a **different instrument** from `signing_gate.json`'s root gate (bar-source, agreement 0.777, `direction_reliable=false` permanently).
- **TRUE and load-bearing:** DISP-GATE-1 harness genuinely unbuilt; regime.json history = 2 days; exit-crowding L1–L3 hard-blocked on ThetaData EOD universe (`n_roots=0`); L4 verdict ACCRUE.

---

## 2. Rulings (RUL-F3.x)

**RUL-F3.1 (scope/cap).** No new lobe charter ships in this program. The two-lobe concurrency cap remains consumed by L1 (short-side) + L3 (dispersion). All Final-3 work ships as: R1-registered experiments (rail artifacts), research-lane derivations, ops harnesses, or docs. The L2 and L5 charters queue behind freed cap slots (§6).

**RUL-F3.2 (exit referent honesty).** This repo has **no held-position ledger** (retro_grades `hold_state`/`hold_days` are null; portfolio construction is docket-L8/Mastermind). All Exit & Trim metrics attach to **fire events** on the replay tape. Every artifact and report must say "fire-tape counterfactual"; field names use `hypothetical_policy` / `counterfactual_path` semantics. No display may read as a live position monitor.

**RUL-F3.3 (label law).** Role/classifier labels must be computed from **pre-outcome state only** (EMA8 breach state, reversion-window elapsed, thesis/falsifier state, crowding state at fire+k). Outcome paths (foregone MFE, avoided MAE, forward returns) are held-out **targets**, never features. Codex's `exit_helped_21`-style labels are look-ahead tautologies and are blocked as classifier targets-cum-features.

**RUL-F3.4 (regret v2 reshaped).** Standalone `scripts/research/exit_regret_v2.py` is KILLED (governor bypass; 4/10 metrics already shipped in EXIT-GRID-1). The computable increments ride TRIM-GRID-1 (capital-freed, right-tail retention) and NET-REPLAY-1 (cash-carry monetization of capital freed = `time_in_capital_saved`). `false_exit_cost` / `late_exit_cost` / re-entry metrics defer until a **pre-outcome** re-entry trigger is specified and registered.

**RUL-F3.5 (ExitPolicy amendment + TRIM-GRID-1).** The frozen R1 v1 ExitPolicy enum is formally amended (logged here per charter law) to add one composite kind: `scaled(legs=[(fraction, leg_policy), ...])` where every `leg_policy` is drawn from the existing frozen v1 vocabulary and fractions sum to 1. TRIM-GRID-1 = exactly 6 pre-registered cells (§4.2), `derived_from_surface=exit_grid_v1`, `verdict_criteria='descriptive-only'`, pooled family `replay`. Compensation for contamination: descriptive-only now; any promotion prereg requires a fresh OOS window (fires ≥ 2026-H2) plus stricter thresholds.

**RUL-F3.6 (DISP-GATE-1 build spec).** Build to the gap-map §6.2 spec + `L3_PREREG.md`, with three amendments ratified here: (a) the **feasibility/exclusion gate prints first** — record panel earliest date, exclude fires lacking ≥252 prior panel bars, print the exclusion count before any statistic; thin-cohort DEFER is a valid printed outcome; (b) **universe construction held fixed** across the PIT reconstruction (same tier priority-dedup at every historical date) with per-date name count printed as a data-quality column; (c) a **realized-vol tercile** added as a second printed covariate split (descriptive column, not a verdict cell, zero budget change) to close the Codex U1/U3 confound-set contradiction. Flip-rate between bases is printed as a continuous number; DEFER triggers if the primary conclusion (gap sign + ≥5pp magnitude) fails on either basis — the frozen >15% flag is also printed. 6 cells; pooled 25→31. PASS enables a display flag only.

**RUL-F3.7 (display-only mechanization).** Before any dispersion enrichment is ever chartered, the display-only guarantee gets a test: `risk_sizing` must receive `regime_gross == 1.0` from the dispersion path, asserted in CI-run unit tests. The guarantee currently rests on a single constant; that is not enough once feature stores exist.

**RUL-F3.8 (dispersion upgrades 2–4 deferred).** Feature store, residual selection-trust model, and the lobe-conditioning matrix are NOT built now: unchartered, forking-paths-contaminating (they slice the same tape DISP-GATE-1 rules on), and n-starved (a 7×6×7 matrix against a 25-episode-cluster floor is mostly empty cells inviting eyeball fishing). Deferred with unblock conditions in §6. First conditioning surface, when chartered, is ONE row: {Entry fires} × {lean_in/neutral/lean_out} × {stop5, dead_money} — exactly the DISP-GATE-1 output.

**RUL-F3.9 (NET-REPLAY-1).** Net-of-friction re-pricing of the **already-seen** replay cells (exit_grid_v1 + wait_grid_v1) is a research-lane descriptive derivation: no new policy comparisons, no new trial cells, stamped `derived_from_surface: exit_grid_v1, wait_grid_v1`. Gross and net always side-by-side. Per-**position** size grid {10k, 100k, 1m} (avoids the multi-name participation fallacy — no book-level AUM claims). Spread = max(Corwin-Schultz proxy at fire date, ADV-banded floor); impact = square-root model charged on entry+exit; cash carry credited on capital-freed days at DTB3. Unmodeled frictions (overnight gaps on fills, halts/limit days, borrow) are **printed as not-modeled** in every output. No verdict language; nothing net-based may prefer a policy without a new registered gate.

**RUL-F3.10 (tax).** Codex's tax engine (`engine/tax_sensitivity.py`, tax lots, wash-sale hooks, jurisdiction config) is KILLED as over-engineering on unknowable inputs. What ships: a **scenario-rate table** (symbolic rates 0/15/20/35/40%, printed as assumptions, not advice) answering the one honest question — does short-term-rate churn at hold(21)-recycling erase its edge vs deferring into long-term treatment at 252d+ holds (long-hold endpoint returns, survivorship split printed)? Note the real kink is at ~1 year: every exit-grid cell (≤126 bars) is short-term, so the within-grid "tax kink" is zero by construction — the comparison must reach the 252d horizon to mean anything. Also fixes the live hard-coded `ST_TAX=0.35` in `scripts/spvector_baseline.py` / `scripts/build_spvector.py` (becomes a documented scenario parameter).

**RUL-F3.11 (§6 passport killed).** The Realized-Decision Passport is NOT built. The repo already has three passport-like objects (engine/passport.py badge states; the rule-experiment registry provenance from #1681; regime.json's passport block). Execution context rides existing synapse registration + engine/passport.py provenance chips. Revisit only after both an L2 and an L5 charter exist; any future per-decision outcome-carrying object must obey the keep-FIRST PIT invariant and the nightly-sole-advancer law.

**RUL-F3.12 (ThetaData tape calibration).** The multi-session calibration harness ships now as **ops-lane, Mac-side** tooling (never on the render path): sessions log is append-only JSONL; the updater writes only the `thetadata_tape` sub-key of `signing_gate.json`; root `direction_reliable` stays false for bar sources permanently; any measured session with per-trade agreement < 0.75 **suspends** `direction_reliable_tape` pending review; production consumption of tape-signed features remains gated on ≥5 sessions spanning high-VIX and calm, multiple roots/expiries/moneyness.

**RUL-F3.13 (crowding separation).** Exit-crowding L1–L3 remain hard-blocked on the ThetaData EOD universe pass (external gate, not a code task); L4 stays ACCRUE with no prereg weakening. BD-AVOID-1 (avoid-long) is a **separate program** with its own prereg — Codex's conflation of the two label streams is rejected.

**RUL-F3.14 (L7 dependency corrected).** Cash/Patience is not blocked on machinery — WAIT-GRID-1 is its descriptive substrate and NET-REPLAY-1 adds the cash-carry leg. It is blocked only on the two-lobe cap and a charter owner.

**RUL-F3.15 (exit-role taxonomy = charter-ready spec, not a build).** Codex's six-exit-problems taxonomy is preserved (§4.4) as the future L2 charter's role vocabulary, amended with: pre-outcome role assignment (RUL-F3.3), a deterministic arbitration order (`thesis_break > tail_flag > time_exit > trim > do_nothing`) plus an explicit `multiple_roles_fired` honest-null output, and RUL-F3.2's fire-tape framing. No nightly builder until an L2 slot frees.

---

## 3. What was genuinely right in the Codex doc (kept)

1. The **six exit problems under one word** decomposition (loss-prevention, winner-preservation, capital-recycling, thesis-invalidation, crowding/exhaustion, re-entry regret) and the refusal to re-litigate the exit-routing NO-GO.
2. §9 guardrails: no promotion from seen surfaces without new gate + contamination stamp; no gross_mult unclamp; no dispersion sizing; no options root-direction flip; gross/net side-by-side; no fused execution score; no tax advice.
3. DISP-GATE-1 as the first build (its §10 pick, contradicting its own §7 ordering).
4. Net-of-friction discipline: never replace the gross result; stamp every assumption.
5. The ThetaData session requirements (≥5 sessions, high-VIX + calm, multi-root/expiry/moneyness, suspend-on-fail, source-specific authority).
6. "Nulls degrade to unknown, not safe" for execution context.
7. The null-first residual-trust question ("is dispersion just a drawdown proxy?") — folded into DISP-GATE-1's confound design rather than a separate model.
8. "Sell the trade, keep the thesis" (entry-reason vs hold-reason separation) — preserved for the L2 charter spec.

## 4. Phase 0 — build waves shipping now (this session)

All PRs branch off fresh `origin/main`, same-day squash-merge. Sonnet builds, Opus reviews stats/code, Fable merges. Registry-touching PRs are **sequenced** (registry.jsonl/trial_ledger.jsonl append conflicts): PR-F3.2 before PR-F3.3.

### PR-F3.1 (this PR) — adjudication + rulings + amendment
This document; the imported Codex source doc; the ExitPolicy `scaled` amendment (RUL-F3.5) which formally amends `research/rule_replay/R1_CHARTER.md`'s frozen vocabulary (cross-referenced there in PR-F3.3 when the enum lands).

### PR-F3.2 — DISP-GATE-1 harness, registration, run, report
- `scripts/research/run_disp_gate_1.py` per RUL-F3.6 (feasibility gate first; fixed universe construction; per-date N printed; expanding + trailing-252 bases; SPY-21d drawdown terciles + realized-vol terciles; episode-clustered bootstrap where ≥25 clusters/arm; flip-rate continuous; DEFER honest).
- Registration via `scripts/register_rule_experiment.py` (6 cells → pooled 31, `derived_from_surface=None`).
- `data/dispersion/disp_gate_1_summary.json` (git) + `research/dispersion/DISP_GATE_1_REPORT.md`.
- `tests/`: regime_gross==1.0 invariant at the risk_sizing boundary (RUL-F3.7) + harness unit tests on synthetic panels.
- Expected honest outcome given the deep-store 2021-10→2025-01 gap: a large printed exclusion count and possibly DEFER — that is a valid result, not a failure. Builder must verify the gap empirically (count store dates per year) before concluding.

### PR-F3.3 — TRIM-GRID-1 (ExitPolicy amendment + 6-cell partial-trim experiment)
- `engine/rule_replay.py`: add `scaled` composite policy kind per RUL-F3.5 (legs from frozen v1 vocabulary only; fractions sum to 1; construction-time validation).
- Frozen cells (exactly these 6):
  1. `trim50_h21_ema8` — exit 50% at hold(21), remainder ema_trail_s8
  2. `trim50_h21_h126` — exit 50% at hold(21), remainder hold(126)
  3. `trim25_h21_ema8` — exit 25% at hold(21), remainder ema_trail_s8
  4. `trim33_h21_h63_h126` — thirds at hold(21)/hold(63)/hold(126)
  5. `trim50_ema8_h126` — exit 50% at EMA8 signal, remainder hold(126)
  6. `trim50_mfe15_ema8` — exit 50% at first close ≥ +15% from entry, remainder ema_trail_s8
- Metrics per cell: weighted WR / mean / median return, weighted foregone-MFE / avoided-MAE vs hold(126), regret ratio, **right-tail retention** (fraction of hold(126) top-decile mean captured — printed with the survivorship caveat), **capital-freed profile** (weighted mean holding days), churn (mean exit events per fire).
- Registration `derived_from_surface=exit_grid_v1` (pooled 31→37), descriptive-only, report per R1 house style (NO-GO prior stated first; contamination note; "validated" never appears).

### PR-F3.4 — NET-REPLAY-1 + tax scenario table
- `scripts/research/net_replay_v1.py` per RUL-F3.9 → `data/execution/net_replay_v1_summary.json` + `research/execution/NET_REPLAY_V1_REPORT.md` (new dirs; artifacts registered in synapse only if any engine surface consumes them — research-lane by default).
- `scripts/research/exit_tax_scenarios.py` per RUL-F3.10 → `data/execution/exit_tax_scenarios.json` + `research/execution/EXIT_TAX_SCENARIOS_REPORT.md`.
- Fix hard-coded `ST_TAX=0.35` → configurable scenario param (documented default preserved).

### PR-F3.5 — ThetaData multi-session tape calibration harness
- `scripts/calibrate_thetadata_tape_sessions.py` per RUL-F3.12; `data/options_flow/tape_signing_sessions.jsonl` (append-only); gate-updater logic writing only the `thetadata_tape` sub-key with suspend-on-fail.
- `research/execution/THETADATA_TAPE_CONTINUOUS_CALIBRATION.md` documenting the session plan (≥5 sessions, conditions, per-root/moneyness/time-of-day breakdowns).
- Session capture attempts are ops-lane (ThetaTerminal must be running); the harness ships regardless, with a dry-run mode tested on the archived #1292 session data if present.

## 5. Phase 1 — accrual & ops (no Fable required)

- ThetaData sessions 2–6 (market-calendar-gated; at least one high-VIX day; suspend-on-fail active).
- Exit-crowding L4 come-back clock (2+ eras of flow history AND ≥60 distinct date×sector-ETF windows @21d); L1–L3 unblock = ThetaData EOD universe pass (external).
- DISP-GATE-1 verdict batch (separate registered run citing the prereg) once the descriptive readout exists and the basis/history judgment is made.
- TRIM-GRID-1 fresh-OOS accrual window opens for fires ≥ 2026-H2 (promotion prereg needs it per RUL-F3.5).
- Nightly regime.json history accrues (2 days → the expanding-basis percentile slowly stabilizes).

## 6. Phase 2 — charter-gated queue (unblock conditions explicit)

| Item | Blocked on | Notes |
|---|---|---|
| L2 Exit & Trim charter (role state builder, thesis-exit join, exit-role nightly surface) | L1 or L3 completing → freed cap slot | Charter spec pre-written: RUL-F3.15 roles + arbitration + RUL-F3.2/F3.3 laws; thesis-exit join uses long-hold falsifier tripwires as context, never authority. |
| L5 Execution charter (execution passport artifact, capacity curves, universe-segmented cost models) | Freed cap slot + off-render scheduling decision | Passport requires: tier=infrastructure, annotate-only pinned in schema, a CI check (mirror `check_badge_passport.py`) failing any template that joins tradability bands into visibility/rank without a registered gate; capacity at operator sizes only with an explicit per-name participation rule; CN/HK spread = UNKNOWN until calibrated (limit-day H==L pathology). |
| Dispersion feature store + conditioning matrix | DISP-GATE-1 readout printed + L3 charter extension | Single powered row first (RUL-F3.8); every added row/column clears its own 25-cluster floor; `derived_from_surface=disp_gate_1` mandatory. |
| Re-entry / false-exit / late-exit metrics | Pre-outcome re-entry trigger spec + registered experiment | RUL-F3.4. |
| L7 Cash/Patience charter | Freed cap slot + owner | Substrate exists (WAIT-GRID-1 + NET-REPLAY-1 carry leg) — RUL-F3.14. |
| §6-style joint decision passport | L2 AND L5 charters both live | RUL-F3.11; PIT keep-FIRST + nightly-sole-advancer laws apply. |

## 7. Trial-budget ledger (running, per RUL-5 conventions)

| Event | Cells | Pooled `replay` SUM after |
|---|---|---|
| exit_grid_v1 (2026-07-05) | 15 | 15 |
| wait_grid_v1 (2026-07-06, #1681) | 10 | 25 |
| disp_gate_v1 (PR-F3.2) | 6 | 31 |
| trim_grid_v1 (PR-F3.3) | 6 | 37 |
| NET-REPLAY-1 / tax scenarios | 0 (re-pricing seen cells) | 37 |

TrialLedger per-family max()-basis remains 15 (largest single declared budget) unless a larger grid registers; both numbers must be disclosed in any future promotion prereg.

## 8. Provenance

- **Census (Sonnet ×6):** exit/trim substrate, dispersion substrate (incl. deep-store gap discovery), execution primitives (incl. Amihud/CS module-location correction and the two-layer signing-gate structure), rails/registry integration contracts, 40+ claim checks, recent-merges reconciliation (WAIT-GRID-1/#1672/#1681/gap-map).
- **Red-team (Opus ×4):** exit-trim critique (no-portfolio referent, circular labels, governor bypass); dispersion critique (PIT infeasibility, CSD N-comparability, confound contradiction, n-starvation); execution critique (uncalibrated cost model, participation fallacy, tax over-engineering, gap/halt silence, auto-filter risk); architecture critique (third-passport redundancy, sequencing inversion, integration burden, budget accounting).
- **Fable:** rulings RUL-F3.1–15, phasing, this document.

> **In plain English (what ships today):** Five pull requests. (1) This ruling document. (2) The dispersion gate study — finally measuring whether "macro tape" regimes really hurt stock-picking, with honest exclusions where our history has holes. (3) A partial-selling experiment — testing whether selling half at the 21-day mark and letting the rest ride beats all-or-nothing exits. (4) A costs-and-taxes reality check that re-prices every exit rule net of spreads, market impact, and scenario tax rates — printed next to the gross numbers, never replacing them. (5) A calibration harness that keeps our options-tape data source honest across many trading sessions. Everything is measurement, not authority: nothing here changes live sizing or signals.
