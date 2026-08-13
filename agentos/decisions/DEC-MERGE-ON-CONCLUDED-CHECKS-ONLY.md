---
key: MERGE-ON-CONCLUDED-CHECKS-ONLY
question: >
  May a session squash-merge its pull request while the PR's CI packs are still running —
  or arm GitHub native auto-merge to do the same thing on its behalf?
answer: >
  No. Merge only on CONCLUDED checks — green, or a red that is only the known-spurious
  "Workers Builds: macro" X. Never `--admin` past in-flight packs, and never arm
  `gh pr merge --auto` in Macro: main carries no branch protection, so native auto-merge
  has no required checks to gate on and merges immediately.
rationale: >
  An `--admin` squash-merge while the packs were still running fired a
  `pull_request: closed` event into the PR's live concurrency group and cancelled the PR's
  own proof run: PR #3867 merged at +3 minutes, its packs died `cancelled`, and the merged
  head stayed unproven forever. Unproven merges stacked up red on main and every ship-loop
  session pinned on the next full-CI dispatch — measured 2026-07-28: 100 ci.yml runs in 8
  hours with 6 successes. Native auto-merge was tried as the safe wait and is not one:
  with no branch protection on main it merged PR #3889 about one minute after arming,
  packs still pending. ci.yml has since fenced merged-close events into their own
  concurrency group, so a fast merge no longer destroys its own evidence — but the
  discipline stands because a merge without a concluded proof still lands an unproven head.
alternatives:
  - option: "`--admin` merge to outrun CI once the diff 'looks safe'"
    why_not: >
      The closed event cancelled the PR's own proof run (#3867); the head merged unproven
      and main went red with no attributable check. "Looks safe" is exactly the state the
      packs exist to test.
  - option: Arm GitHub native auto-merge (`gh pr merge --auto --squash`) as the wait
    why_not: >
      main has no branch protection, so auto-merge has no required checks and merges
      IMMEDIATELY — verified on PR #3889, 2026-07-28, merged ~1 minute after arming with
      packs still pending. It is a disguised mid-flight merge, not a wait.
evidence:
  - "Macro CLAUDE.md §Shared workspace + completion — 'Merge on CONCLUDED checks, never mid-flight (operator 2026-07-28)'"
  - "Macro AGENTS.md §Definition of done, same-titled block with the #3867/#3889 receipts"
  - "PR #3867 (merged mid-flight, packs cancelled) and PR #3889 (auto-merge fired in ~1 min)"
  - ".github/workflows/ci.yml concurrency group — merged-close events fenced into their own group ('-merged' suffix)"
affects: [".github/workflows/ci.yml", ".github/workflows/merge-on-green.yml", "macro merge practice fleet-wide"]
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-07-28
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1) from the standing fleet law in Macro
`CLAUDE.md`/`AGENTS.md`, which carries the operator date and both PR receipts inline. The
rationale above restates that prose; nothing here is reconstructed from recollection.

## What would reopen this

Main gaining branch protection with the CI packs as required checks. At that point native
auto-merge becomes a genuine gated wait, the #3889 failure mode disappears, and this record
should be superseded rather than silently ignored. Until then, the concluded-checks
discipline is what `merge-on-green.yml` automates — see
`DEC:DEFAULT-FINISH-HANDS-WAIT-TO-SWEEPER` for who does the waiting.
