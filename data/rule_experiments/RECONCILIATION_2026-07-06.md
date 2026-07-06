# Replay-budget accounting reconciliation — 2026-07-06

One-time correction record for drift reviewers flagged in the R1 rule-replay
bookkeeping. Append-only semantics respected: **nothing was removed or
rewritten** in `data/trial_ledger.jsonl` or `data/rule_experiments/registry.jsonl`;
this document plus one appended ledger row are the entire data change.

## Canonical arithmetic (NW_FINAL3_LOBES_ADJUDICATION_AND_MASTERPLAN §7)

| exp_id | declared_budget | pooled `replay` SUM after |
|---|---|---|
| exit_grid_v1 | 15 | 15 |
| wait_grid_v1 | 10 | 25 |
| disp_gate_1 | 6 | 31 |
| trim_grid_v1 | 6 | 37 |

Registry SUM basis (`pooled_replay_trial_count`): **37**.
TrialLedger per-family max()-basis DSR floor: **15** (largest single declared budget).
Both numbers must be disclosed in any future promotion prereg on this tape.

## Findings and dispositions

1. **exit_grid_v1 ledger row MISSING** (`data/trial_ledger.jsonl` had no
   `replay` `declared_budget` row for it, despite the registry `registered`
   row at `2026-07-06T05:31:35Z`). Root cause: `register_experiment` writes
   the ledger row before the registry row, but the registration ran in an
   agent worktree (`agent-a0a9b305853978846`) whose `data/` writes were only
   partially merged back. **Not inert**: the family max()-basis floor read 10
   (wait_grid_v1) instead of 15, under-flooring the DSR haircut.
   → **Corrected**: one `declared_budget` row (n=15, reason stamped
   `exp_id=exit_grid_v1; RECONCILIATION 2026-07-06: ...`,
   `config_hash=70b63bb2a39caf29`) appended via
   `TrialLedger.log_declared_budget`. Floor restored to 15.

2. **wait_grid_v1 ledger row DUPLICATED** (`2026-07-06T13:17:24Z` and
   `13:25:28Z`, both n=10). Root cause: two registration attempts with
   reworded question text — the ledger dedup hashes `(family, n, reason)` and
   the `question[:80]` truncation differed, so the second attempt wrote a new
   row (its registry row did not survive the merge). → **Left in place**
   (append-only). Inert under both disclosure bases: max()-basis takes the
   max, and the SUM basis (`replay_ledger_budgets`) collapses per-exp_id
   duplicates via max() before summing. CI now asserts the collapsed
   ledger-derived SUM equals the registry SUM
   (`tests/test_replay_accounting_reconciliation.py`).

3. **disp_gate_1 double `registered` rows in the registry**
   (`13:51:10Z` and `13:54:36Z`, both budget=6). The second row is a
   legitimate content **amendment** — it added `base_cohort_predicates` —
   and `load_experiment`'s field-union later-wins merge handles it by design.
   Only the first registration wrote a ledger row (the ledger reason hash
   deduped the second). → **Left in place**. `pooled_replay_trial_count`
   dedups by exp_id (latest wins), so the SUM counts disp_gate_1 once.

4. **exit_grid_v1 / disp_gate_1 duplicate `executed`/`reported` rows**
   (2 and 3 run-churn pairs respectively). These are BY-DESIGN idempotent
   lifecycle re-run records (§3.3 permits timestamped regrade). → **Left in
   place**; do not "clean" these in the future either.

## Guards added with this reconciliation (PR of same date)

- `engine/rule_experiments.py::register_experiment` — idempotent dedup guard:
  re-registration with an identical `registration_content_hash` (semantic
  fields only) appends nothing and burns no ledger row; genuine amendments
  still append.
- `engine/rule_experiments.py::replay_ledger_budgets` /
  `reconcile_replay_accounting` — canonical ledger-side SUM derivation
  (per-exp_id max, unattributed rows flagged) and registry cross-check.
- `scripts/register_rule_experiment.py trial-count` — now prints both
  disclosure bases and exits non-zero on drift.
- `tests/test_replay_accounting_reconciliation.py` — CI asserts the real
  files stay consistent (ledger SUM == registry SUM == 37 as of this date;
  floor == 15; §7 per-exp budgets frozen).

If a future registration's ledger row goes missing again (the worktree
`data/`-discard class), repair the same way: append a single
`declared_budget` row via `TrialLedger.log_declared_budget` with the
`exp_id=<id>; RECONCILIATION <date>: ...` reason stamp, and record it in a
dated file like this one. Never rewrite history.
