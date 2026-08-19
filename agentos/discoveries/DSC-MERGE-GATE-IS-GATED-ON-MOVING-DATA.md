---
key: MERGE-GATE-IS-GATED-ON-MOVING-DATA
claim: >
  main's own ci.yml is green 44% of the time (44 success / 45 failure / 11
  cancelled over 100 runs, 2026-08-09 to 2026-08-19) because 130 of the 194
  merge-gate legacy jobs assert against the committed data tree that the nightly
  rewrites ~250 commits a day; the pull-request backlog is a consequence of that
  rate, not of a defect in merge-on-green.
falsifier: >
  `python3 scripts/ci_gate_reliability_report.py` reporting a green rate above
  ~90% over a trailing 100 runs while the backlog persists, or a data-coupled
  count near zero — either would mean the pileup has a different cause.
so_what: >
  Stop healing individual reds and stop auditing the sweeper. Per-red healing
  cannot converge because the failing set rotates faster than a ~35 min heal
  cycle. The lever is the coupling COUNT: move data-tree assertions off the
  merge gate into a post-nightly data-health lane that reds an issue. Until that
  lands, treat "my PR is red on a job my diff cannot reach" as the expected
  state, verify against main's own newest run, and wait rather than heal.
kind: architecture
verified_at: 2026-08-19
verified_by: >
  scripts/ci_gate_reliability_report.py (this commit) — green rate 44/100 over
  2026-08-09T15:32Z..2026-08-19T05:46Z; coupling 130/194 jobs, 67% of classified.
  Rotation measured the same morning: main red on capital-structure-intelligence
  at 04:47Z (run 32217049650), healed and merged 05:15Z (#5930), then red on
  market-memory-contract + unrun-prophet-learning-loop + signal-contract at
  05:46Z (run 32220671521) — three different jobs, one hour, no PR involved.
scope:
  - macro
  - .github/ci/legacy-jobs.yml
  - scripts/merge_on_green.py
  - .claude/hooks/ship_loop_guard.py
confidence: verified
---

## The arithmetic

With `N` data-coupled jobs each carrying probability `p` of being wrong-footed by a data change in a given window, `P(all green) ≈ (1-p)^N`. At `N = 130` and `p ≈ 0.6%` that is ~46%, which is the observed rate. Retries, wider tolerances, and faster healing all act on `p` and lose to the exponent. Only `N` moves the number.

## The self-sustaining part

Any pull request touching `scripts/**`, `.github/workflows/**`, `.github/ci/**` or `.claude/hooks/**` sets `authority_changed=true`, which removes the base-inherited excuse entirely. Every CI fix is authority-changing. So the remedy can only land in a fully-green window that the 44% rate makes rare — the fix for the problem is gated on the problem.

## What this is NOT

Not a criticism of any test. A receipt over live data is a legitimate instrument; it is simply not a merge precondition, because a pull request cannot make yesterday's dividend calendar agree with today's parquet. Moving such a job off the gate must keep it running and keep its failure visible — see `research/CI_MERGE_GATE_RELIABILITY_ROOT_CAUSE_2026_08_19.md` §0 gate 3.
