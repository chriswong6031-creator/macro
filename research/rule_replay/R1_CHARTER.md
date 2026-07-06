# R1 Rail — Charter

**Ratified:** 2026-07-06
**Program authority:** `research/NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md` §2–§3
**Status:** ACTIVE. PR-1 core merged; PR-2 runner ships in this PR.

---

## Purpose

R1 is the **fire-tape × policy-grid replay rail**. It answers questions of the form: "given the production fire tape, what did each frozen exit policy cost or save?" Entry events come from the existing production fire tape (`data/replay/replay_boarded.parquet`); rules parametrize cohort filter, fill delay, exit policy, and per-fire weight. R1 does NOT re-run the production gate (that remains `replay_standout_pipeline.py`). Portfolio-level construction is OUT OF SCOPE (docket L8 → Mastermind).

---

## Governor law — RUL-P3 (verbatim)

> **The R1 runner MUST refuse any policy grid not registered in the rule-experiment registry before the run (content-hash match). No interactive/exploratory mode exists. Every run pools into the flat `fdr_family='replay'` TrialLedger family. All outputs are display-only; promoting any rule to live behavior requires the standard PREREG gauntlet outside R1.**
>
> **Forking-paths law:** a descriptive surface, once seen, contaminates later preregs on the same tape — any promotion prereg written after a descriptive batch must carry a `derived_from_surface: <exp_id>` stamp and state how its gate compensates (stricter threshold or fresh OOS).

Enforcement: `scripts/run_rule_replay.py` enforces this on every call. There is no `--adhoc` flag; adding one is a house-law violation. `scripts/check_trial_registration.py` name-patterns do NOT match `run_rule_replay.py` — the governor itself is the enforcement layer.

---

## Frozen v1 policy vocabulary

| Policy | Parameters | Notes |
|---|---|---|
| `hold(H)` | H ∈ {5, 10, 21, 42, 63, 126} | Time exit at H bars. `hold(21)` = Oracle-ratified anchor. |
| `ema_trail(span=8, resample='3B')` | span=8, resample='3B' | EMA8 tail-flag. MUST import `engine.signal_quality` — never re-implement. |
| `trail_stop(pct)` | pct ∈ {8, 12, 15, 20} | High-watermark trailing stop. |
| `barrier(stop_pct, target_pct)` | stop<0, target>0 | Close-only bracket; first-touch on close (conservative). |
| `scaled(legs=[(fraction, leg_policy), ...])` | fractions > 0, sum to 1.0; each leg from v1 vocabulary or `profit_take(pct)` | **Amendment: RUL-F3.5** (Final-3 masterplan, 2026-07-06) + **PR-F3.3**. Composite policy: each leg exits its fraction per its own policy; fire return = Σ fraction × leg_return. Never-triggered legs included at reference return (EXIT-GRID-1 aggregation-bug-class prevention). |
| `profit_take(pct)` | pct = 15 (frozen) | **Amendment: RUL-F3.5 + PR-F3.3**. Exit at first CLOSE >= +pct% from entry (close basis, conservative). ONLY valid as a leg inside `scaled()`; rejected as a standalone policy. If never touched, holds to reference (included at reference return). |

Extending the enum requires a program amendment logged in the program doc.

All policies use close-to-close execution, next-bar-after-signal fill at `delay_n=1` (conservative). Exits fill on the close of the triggering bar.

---

## Storage map

| Artifact | Path | Commit path | Writer |
|---|---|---|---|
| Registry | `data/rule_experiments/registry.jsonl` | Git (single-writer) | `scripts/register_rule_experiment.py` |
| Summary JSON | `data/rule_experiments/results/<exp_id>_summary.json` | Git (single-writer) | `scripts/run_rule_replay.py` |
| Perfire parquet | `data/rule_experiments/results/<exp_id>_perfire.parquet` | Gitignored (Mac-local) | `scripts/run_rule_replay.py` |
| Trial ledger | `data/trial_ledger.jsonl` | Git | `engine/rule_experiments.py` via `TrialLedger` |

The `.gitignore` explicitly lists `data/rule_experiments/results/*_perfire.parquet` (shipped in PR-1, RUL-P10).

---

## Promotion boundary

R1 outputs are **display-only**. The promotion path is:

1. Descriptive batch via R1 (displays regret surface, labeled `verdict_criteria: descriptive-only`)
2. Any promotion prereg that follows must carry `derived_from_surface: <exp_id>` and state how its gate compensates for forking-paths contamination (stricter threshold or fresh OOS)
3. Full PREREG gauntlet (separate program, outside R1): episode-clustered bootstrap, BH-FDR q≤0.10, n≥300/side fires and n≥25 episode-clusters per arm, OOS split declared and opened once

No R1 output may be interpreted as a promotion verdict. The word "validated" must not appear in any R1 report.
