---
key: ADOPT-A-LIVE-CARRIER-NEVER-DUPLICATE-IT
question: >
  When a commissioned session's mandated collision census finds the lane already held by a
  LIVE worker from another vendor - unpushed, no PR, mid-flight - and the commissioning
  authority has granted end-to-end delivery authority, what does the session do?
answer: >
  ADOPT the in-flight work rather than duplicate or discard it, and make the adoption visible
  in the same act. Concretely: cherry-pick the other carrier's commit with `-x` so authorship
  and provenance survive; open your own branch rather than writing into the other worker's
  worktree (never race a live tree); post a claim comment on the issue naming the collision,
  the adopted SHA and what you are adding; carry the superset to merge; and when the duplicate
  PR appears, close it with a VERIFIED containment statement - file-by-file proof that the
  adopted work is present - rather than an assertion.
rationale: >
  The three obvious moves are all worse. Stopping wastes a granted authority and leaves a real
  production bug live. Racing produces two PRs conflicting on every owned file, and house law
  already forbids two partial fixes of one gate. Restarting from scratch discards correct work -
  the observed Codex carrier's producer fix was RIGHT, and covered a second `gen_fund_us.py`
  site the issue text never mentioned. Adoption keeps the good work, ends the race with one
  visible act, and puts a single carrier in front of CI. The containment proof is the part that
  makes closing the duplicate legitimate rather than territorial: for #475 all six consumer
  sources were byte-identical to the adopted commit and the four differing files were
  extensions, which is checkable by anyone later.
alternatives:
  - option: "Stop and return a collision packet (the commission's default stop condition)"
    why_not: >
      Correct BEFORE authority is granted, and it is what the session did first. Once the
      operator grants end-to-end authority it becomes an abandoned deliverable: the bug stays
      live and the carrier was blocked on a review that never arrived.
  - option: "Work in parallel on the same issue from a second branch"
    why_not: >
      Guarantees two PRs conflicting on all ten owned files, and neither can be reviewed as the
      whole fix. This is the deadlock the one-PR-per-gate rule exists to prevent.
  - option: "Take over the other worker's worktree and push its branch"
    why_not: >
      Races a live process - the carrier amended its commit twice during the census - and any
      push could be clobbered by its next amend. Cherry-picking to a fresh branch is race-free.
  - option: "Re-implement from scratch, ignoring the in-flight work"
    why_not: >
      Discards a correct fix and its authorship, and would have lost the `build_estimates`
      site that carrier had already found.
evidence:
  - "mastermind-terminal#474 (issue), #475 (duplicate carrier, closed), #477 (adopting carrier)"
  - "adopted commit 34902467 cherry-picked -x; containment verified per-file with `git diff --quiet 34902467 HEAD -- <path>` across all ten files"
  - "collision located via ~/.codex/sessions rollout 01a03bcc-6a5b-7283-8285-e54a162892ea, mtime live at census time - see DSC:CODEX-CARRIERS-INVISIBLE-TO-CLAUDE-CENSUS"
  - "superset added: two further producers, the HK collect-time truncation, two unguarded consumers, and a script-mode import that would have taken the nightly down - see DSC:FUND-NEXT-DATE-HAS-THREE-PRODUCERS and DSC:TERMINAL-INGEST-EMITTERS-RUN-AS-SCRIPTS"
affects:
  - mastermind-terminal
  - macro
  - Mastermind
confidence: high
reversibility: easy
decided_by: "session d81c69f1 (Opus builder) under operator-granted end-to-end authority, 2026-08-26"
decided_at: 2026-08-26
---

Scope note: this decision governs what to do AFTER a collision is found and delivery authority
exists. It does not weaken the standing stop condition — a commissioned session that finds a
live carrier and has NOT been granted authority still stops and returns a collision packet.
The adoption path additionally assumes the other carrier has not yet merged; a merged sibling
is ordinary base movement, not a collision.
