---
key: DAILY-CRON-SLOT-CONCURRENCY-GROUPS
question: >
  How should daily.yml stop a gate-skip EST-guard (or any off-regime cron) from
  cancelling a queued or running EDT-correct nightly, without weakening the
  EST-guard's purpose?
answer: >
  Give each schedule cron its own concurrency group keyed on
  github.event.schedule; keep cancel-in-progress false; leave workflow_dispatch
  on a third group so manuals serialize with each other, never with a cron.
  et_gate still decides which slot runs the real jobs. Watchdogs must not treat
  a gate-skip success as "the nightly ran".
rationale: >
  GitHub replaces the one PENDING run per group regardless of cancel-in-progress
  (DSC:GITHUB-CONCURRENCY-SUPERSEDES-PENDING). The 2026-08-14/15 kill was exactly
  that: queued EDT 31848262472 superseded by EST-guard 31851452961. Distinct
  groups are the only lever that keeps a no-op from eating a queued real slot.
  et_gate is unchanged, so the EST-guard still fires the real nightly in winter.
  A gate outage can now double-run in parallel rather than serialize; push steps
  already rebase-retry, which is the accepted fail-open cost.
alternatives:
  - option: Event-conditional cancel-in-progress (mirror fences.yml 2026-08-09)
    why_not: >
      fences.yml's problem was cancel-in-progress true killing RUNNING main-push
      proofs. daily.yml already had the flag false. The killed run was queued,
      and pending-supersede ignores the flag.
  - option: Resolve the ET regime before entering the shared group
    why_not: >
      Workflow-level concurrency is assigned before any job runs. GitHub
      expressions cannot call zoneinfo. A wrapper workflow that gates then
      dispatches would work but rewrites the nightly for no extra invariant.
  - option: Keep one group and disable pending-supersede
    why_not: >
      GitHub has no such flag. cancel-in-progress false is the entire published
      control surface, and it does not cover pending.
evidence:
  - "daily.yml runs 31848262472 (cancelled superseded) and 31851452961 (success, et_gate skip)"
  - "fences.yml concurrency comment 2026-08-09 — pending-supersede measured on main"
  - "DSC:GITHUB-CONCURRENCY-SUPERSEDES-PENDING"
  - ".github/workflows/daily.yml et_gate — regime-match, fail-open, both crons still scheduled"
affects:
  - WS:PROPHET-US-AVAILABILITY
  - .github/workflows/daily.yml
  - scripts/prophet_rescue.py
  - scripts/check_nightly_liveness.py
confidence: high
reversibility: easy
decided_by: cursor-cloud-daily-cron-sibling
decided_at: 2026-08-15
---
