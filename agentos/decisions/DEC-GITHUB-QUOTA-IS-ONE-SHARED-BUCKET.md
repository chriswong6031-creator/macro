---
key: GITHUB-QUOTA-IS-ONE-SHARED-BUCKET
question: >
  How do parallel sessions, hooks, and background lanes treat GitHub REST quota — a
  per-session resource to poll freely, or a shared one to budget?
answer: >
  As ONE shared, exhaustible resource: `gh` authenticates as a single account token, so
  REST's 5,000/hr `core` pool is shared by every parallel session, the babysitter lane,
  and the hooks. A PreToolUse hook (`gh_quota_guard.py`) denies the three shapes that
  have emptied it: `gh run watch` at its default 3-second interval (use `--interval`
  60+), any `gh` call in a loop sleeping under 90 seconds, and `--paginate` over
  check-runs/jobs. Preflight `gh api rate_limit --jq '.resources.core.remaining'`
  before a long watch; ONE watcher per endpoint; an empty or 403 response is never a
  green result. REST and GraphQL are separate pools — `gh pr view` working does not
  mean `gh api` will.
rationale: >
  On 2026-07-26 the pool was emptied by polling: two watchers on one endpoint at 45s
  took the pool 4,488 → 0 in under an hour. Exhaustion 403s EVERYTHING on the token for
  up to an hour — including `ship_loop_guard.py`, which spends up to four REST calls per
  Stop evaluation and FAILS CLOSED when rate-limited, so over-polling blocks the very
  Stop the polling was meant to reach. The default-interval trap is why this is a hook
  rather than a convention: nothing on the command line says "3 seconds", which is
  exactly why it passed review. Pacing belongs to the job being watched — a ci.yml run
  takes 30–34 minutes, so there is no reason to poll it faster than about once a minute.
alternatives:
  - option: Polling etiquette by convention, no hook
    why_not: >
      Convention already failed — the 3-second default passed review because it was
      invisible. The three denied shapes are the measured 2026-07-26 causes, made
      structural.
  - option: "(none other considered in the standing law)"
    why_not: >
      Recorded for honesty: fleet law documents the incident and the hook, not a wider
      alternatives survey. Per-session tokens would change the economics but are not
      discussed in any cited source, so no rationale is reconstructed for or against.
evidence:
  - "Macro CLAUDE.md §House laws — 'GitHub quota is ONE shared bucket (hook-enforced)', 2026-07-26 receipts"
  - "Macro AGENTS.md §Waiting on CI without jamming every other session — 4,488→0 measurement, fail-closed Stop"
  - ".claude/hooks/gh_quota_guard.py — added 2026-07-27 (git log --diff-filter=A)"
affects: [".claude/hooks/gh_quota_guard.py", ".claude/hooks/ship_loop_guard.py"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-07-27
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1). Dated to the guard's first commit, the day
after the measured exhaustion. Attribution: incident-derived fleet law → coo-fable.

## What would reopen this

Per-session or per-lane tokens (separate buckets), or GitHub quota-model changes. Until
then this record is the WHY behind every denied `gh run watch` a session sees — the
denial is protecting that session's own Stop.
