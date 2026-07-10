# data/signal_foundry/ — Signal Foundry artifacts

**Write fence (SF-R10):** the Foundry writes ONLY to files under this directory.
It never edits `engine/`, `config/`, `scripts/`, workflows, or any ledger it
does not own.  Narrow commits only.

## Directory layout

```
data/signal_foundry/
  README.md                      — this file
  candidates.jsonl               — registered spec records (written by brainstorm scripts)
  promotions.jsonl               — human adjudication log (written by Fable/operator only)
  results/
    SF-NNNN.json                 — full battery result per spec id
  forward/
    SF-NNNN.jsonl                — daily accrual of (feature, target_raw) after registered_at
  specs/
    SF-NNNN.json                 — frozen spec JSON at registration time (optional mirror)
```

## File descriptions

### candidates.jsonl
Append-only JSONL of registered spec records.  Each row has at minimum:
```json
{
  "id": "SF-0001",
  "status": "registered",
  "registered_at": "2026-07-10",
  "construction_hash": "...",
  "gates_hash": "...",
  ... (full spec fields)
}
```

**This file is ABSENT until the first cohort is filed (PR-E).**
All readers in `engine/signal_foundry/` tolerate its absence gracefully.

### promotions.jsonl
Human-only adjudication log.  Written by Fable/operator after reviewing the
promotion docket.  Each row has: `{spec_id, decision, reason, adjudicated_by, ts}`.
A spec_id in this file is excluded from `promotion_docket()` results.

### results/SF-NNNN.json
Full battery result written by `engine.signal_foundry.harness.run_spec()`.
Schema:
```json
{
  "spec": { ... },
  "stats": {
    "n_obs": int,
    "effective_months": int,
    "full_ic": float,
    "hac": { "mean": float, "se": float, "t": float, "p": float, "n": int },
    "split_half": { "h1_ic": float, "h2_ic": float, "split_half_sign_flip": bool },
    "era_split": { "pre_ic": float, "post_ic": float, "sign_flip": bool, ... },
    "block_bootstrap_ci": { "ci_2p5": float, "ci_97p5": float, "ci_straddles_0": bool, ... },
    "dsr": { "dsr": float, "n_trials": int, ... }
  },
  "placebos": {
    "time_shift": { "shift_pctile": float, "obs_ic": float, "n_draws": int },
    "negative_lag": { "neg_lag_ic": float, "obs_ic_same_window": float, "neg_dominates": bool }
  },
  "backtest": { "net_sharpe": float, "gross_sharpe": float, "max_dd": float, ... },
  "verdict": "pass_candidate | null | era_specific | unstable | insufficient_power | insufficient_history | data_missing | forbidden | error",
  "verdict_reasons": [ "..." ],
  "battery_version": "sf-battery-1",
  "ran_at": "YYYY-MM-DD",
  "ledger_n_at_run": int
}
```

**Verdict grammar is CLOSED (SF-R9):** the word "validated" never appears.
Nulls are retained as confluence inputs — the graveyard is content, not embarrassment.

### forward/SF-NNNN.jsonl
Daily accrual written by `engine.signal_foundry.results.accrue_forward()` as a
nightly engine-job step (PR-D).  Each row:
```json
{ "date": "YYYY-MM-DD", "spec_id": "SF-NNNN", "feature": float, "target_raw": float, "registered_at": "YYYY-MM-DD" }
```

**Idempotent per (spec_id, date):** re-running accrue_forward does not duplicate rows.
Evidence for dates <= registered_at is never appended (SF-R4: forward evidence only).

Forward evidence is the ONLY admissible basis at promotion — the in-sample battery
is screening-tier only.

## Ruling references

- **SF-R4** — pre-registration + forward evidence only
- **SF-R9** — closed verdict grammar
- **SF-R10** — write fence (this directory is the entire Foundry output surface)
- **SF-R11** — panel specs use time-preserving nulls (within-date demeaning, episode-label permutation, effective-N in months)
- **DT-R14** — time-preserving placebo / bootstrap law
- **DT-R16** — era split at 2010-01-01
