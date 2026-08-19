# GD-4A Commission — CN/HK forward-ledger liveness repair

**Commissioned by:** Sol continuation ruling 2026-08-19 → Fable COO
**Wave:** `WS:GREY-DEER-RISK-INTELLIGENCE` GD-4A · **One PR.** Separate from GD-2.
**Scope class:** operational truth repair only. No new sensors, no schema changes, no
history rewrites.

## Root cause (confirmed 2026-08-19 census — do not re-diagnose, do verify before edit)

`engine/risk_radar_intl_audit.py:61-71 ledger_lane_armed()` requires
`COLLECT_LANE=nightly` (or `US_LANE`) before `snapshot_and_grade()`
(`scripts/build_china.py:1445-1447`, `scripts/build_hk.py:1365-1367`) will append to
`data/risk_radar_intl/{cn,hk}_forward_log.jsonl`. The canonical settled Asia lane
(`.github/workflows/asia-close.yml`) deliberately sets NO job-wide COLLECT_LANE (its own
comment at ~line 667: arming job-wide would un-gate other ledger writers) and its
build_china/build_hk steps carry no per-step arm; daily.yml sets the variable but never
runs those builders. Result: both ledgers frozen at asof 2026-07-16 (last advance commit
0a140c6db64f) while the lane runs green daily. The 08-15→17 ruleset freeze is REFUTED as
the cause (gap predates it ~30 days).

## §0 Acceptance gates (not done unless)

1. **`COLLECT_LANE=nightly` is applied ONLY on the exact settled forward-ledger
   advancement steps in asia-close.yml — never job-wide.** Follow the existing narrow
   per-step arm pattern already in that workflow (per-step `env:` blocks around lines
   ~520/533/534 for rotation_events/baskets). If the advancing calls are embedded inside
   broader build_china/build_hk steps that also run un-gated writers, split the
   advancement into its own minimal step (or an explicitly scoped invocation) rather than
   arming the whole step's other writers — the workflow's own line-667 warning is the
   law here.
2. **Prospective resume only.** The July–August gap is NOT backfilled into the canonical
   forward log — no synthetic/retro rows, no history rewrite; the gap remains visible.
3. Duplicate-date idempotence proven by test: the existing keep-first-by-asof guard
   (`engine/risk_radar_intl_audit.py:131-133 log_snapshot`) holds — a rerun of the same
   settled session appends nothing (note the write is a full-file rewrite despite the
   "append" wording; assert row-count stability, not file-append semantics).
4. Zero intraday advancement proven by test: with COLLECT_LANE unset (intraday/preview
   lanes), no append occurs on either ledger.
5. A ledger-stall visibility gap exists (census: no heartbeat found on these ledgers).
   IF a small guard fits this PR (e.g., a staleness `::warning` printed with a bare
   `print(..., flush=True)` at line start — never through a logger — in the advancing
   step), add it; if it grows the PR beyond the repair, name it in the handoff as the
   follow-up instead. Do not build a new monitoring plane.
6. **Production proof (closes the wave, not the PR):** the next real settled Asia-close
   run on production substrate advances each ledger EXACTLY once — one current CN row and
   one current HK row, committed/served, with the run link and row receipts recorded in
   the workstream/handoff. The PR merges on tests; the wave stays open until this proof.

## Non-goals / stop conditions

Do not touch daily.yml's COLLECT_LANE. Do not arm any other `ledger_lane_armed()` caller
(`engine/market_state_audit.py`, `engine/risk_radar_audit.py`, `engine/ignition_audit.py`,
`engine/opex_risk.py`, `engine/event_window.py`, `engine/top_maturation.py`,
`engine/risk_radar_intl_audit.py` siblings) — this PR arms CN/HK forward-log advancement
and nothing else. No cascade/scorecard changes (they read the fresh row on their own).
No `.github/ci/legacy-jobs.yml` edits. If reproduction contradicts the root cause above,
STOP and return the evidence — do not patch the env var blindly (packet §11 GD-4A stop
condition). Workflow + `scripts/**` edits make this authority-changing: verify main's
latest ci baseline is green before merging. Never cancel asia-close/daily runs
(hook-enforced).

## Worktree law

Full checkout before reading `data/risk_radar_intl/`: `python3 scripts/worktree_sparse.py full`.
Tests asserting over those ledgers must use fixtures, not the live files.
