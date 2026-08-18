---
key: COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE
question: >
  `daily.yml`'s concurrency groups are deliberately event-split, so a `workflow_dispatch`
  run and a cron run can execute `collect` concurrently and each commit a full
  `data: daily collection <date>` (measured 2026-08-18). Can that be closed by a mutex in
  the `et_gate` job — the one gate all 19 downstream jobs already honour?
answer: >
  No. A gate-time mutex is architecturally wrong and was withdrawn (PR #5880, closed
  unmerged after being built, tested green, and red-teamed). It fails two independent
  ways. TOO EARLY: the contended resource is `collect`, which starts after an unbounded
  self-hosted queue wait — on 2026-08-18 both `et_gate` jobs ran at 01:01:45Z/01:01:49Z
  while the two `collect` jobs started at 01:07:12Z and 01:27:00Z, so at gate time
  neither `collect` existed and no `collect`-scoped predicate could see them. TOO
  COARSE: the only signal available that early is "an older non-completed run has a job
  in_progress", which blocks on a still-baking PREVIOUS nightly and zero-runs the night.
  A correct guard must sit at the START of `collect`; standing down there cannot use a
  gate output, because every downstream job carries `always() &&` by design, so the only
  mechanism that overrides it is cancelling the run. Choosing among self-cancel,
  serialize-and-wait, and stay-procedural is an OPERATOR decision, not a session call.
  Any new stand-down state must teach `is_et_gate_skip()`/`counts_as_bake()` FIRST.
rationale: >
  The withdrawn implementation was green on every gate it owed (30 tests in
  tests/test_daily_et_gate.py, plus annotation/file-size/timings suites) and would in
  fact have prevented the exact 2026-08-18 pair. It was still wrong, and the way it was
  wrong is the point: verified against live API state at 2026-08-18T08:20Z, runs
  32077948964 and 32084697588 were both still non-completed with `engine` and
  `capital_structure` in_progress while their `collect` jobs had finished hours earlier.
  Tonight's ~22:52Z EDT cron would have read both as older-and-live and stood down —
  losing the authoritative nightly's ledger advance for zero benefit, since neither
  blocker could double-collect. Runs here routinely exceed 24h (31977372592 = 26h,
  31913143619 = 28h), so this is the normal case, not a tail. That is precisely the
  wall-clock window `.github/workflows/daily.yml:22-24` forbids, and it breaks the
  `:27-31` invariant "can double-run a night but can never silently zero-run one" — the
  step's try/except fail-opened only the ERROR path, while the SUCCESS path was a brand
  new zero-run mechanism. Narrowing the predicate to the `collect` job removes the
  zero-run but also removes the fix, because of TOO EARLY above. There is no predicate
  that is both evaluable at gate time and precise enough to distinguish "will collect"
  from "finished collecting six hours ago"; the location, not the predicate, is the
  defect. Recorded rather than retried so the next session does not rebuild it.
alternatives:
  - option: Scope the gate-time liveness test to the `collect` job only
    why_not: >
      Removes the zero-run blocker but also removes the fix. At gate time on 2026-08-18
      neither run's `collect` had started (01:07:12Z / 01:27:00Z vs gates at
      01:01:4xZ), so a collect-scoped predicate sees nothing and both runs proceed.
  - option: Keep the "any job in_progress" liveness test and accept skipped nights
    why_not: >
      Trades one measured concurrent double-collect for a recurring zero-run, and the
      zero-run is the worse failure — a skipped night is invisible to every run-level
      instrument (see the is_et_gate_skip finding in evidence) and violates the file's
      own stated invariant.
  - option: Put `workflow_dispatch` back in the cron concurrency group
    why_not: >
      Reintroduces the 2026-08-14/15 pending-supersede kill — GitHub cancels a PENDING
      run when a group-mate enters even with cancel-in-progress false, which is what ate
      the EDT nightly that night. The event split is load-bearing and stays.
  - option: Job-level `concurrency` on the `collect` job with a constant group
    why_not: >
      Same pending-supersede hazard one level down: a dispatch entering the group would
      CANCEL a pending cron's `collect`, recreating the failure the workflow-level split
      exists to prevent.
  - option: Leave it procedural — the existing "never dispatch over a live run" rule
    why_not: >
      Not rejected; it is one of the three live options handed to the operator. Recorded
      here as the status quo the decision defers to until an operator picks.
evidence:
  - "PR #5880 — built, 30 tests green, red-teamed, disarmed and CLOSED unmerged; full reasoning in its closing comment"
  - "branch claude/daily-double-collect-mutex — the withdrawn implementation, retained unmerged"
  - "commit attribution: 59ccb9c774c8 @04:01:49Z inside run 32077948964 collect step 28 (04:01:25→04:01:52Z, mac-builder-light); 93ab221b81dd @04:21:53Z inside run 32084697588 step 28 (04:21:26→04:21:55Z, mac-builder-5)"
  - "collect job overlap: 32077948964 01:07:12Z→04:08:26Z; 32084697588 01:27:00Z→04:28:57Z"
  - "gh api repos/{o}/{r}/actions/runs/32077948964/jobs @2026-08-18T08:20Z — engine in_progress, factor_panel queued, collect completed; run-level status still 'queued'"
  - "gh api repos/{o}/{r}/actions/runs/32084697588/jobs @2026-08-18T08:20Z — capital_structure in_progress, collect completed"
  - ".github/workflows/daily.yml:22-24 (no wall-clock window) and :27-31 (never silently zero-run) — the contract the withdrawn design violated"
  - ".github/workflows/daily.yml:65 — the event-split concurrency group expression"
  - "scripts/prophet_rescue.py:360-395 and scripts/check_nightly_liveness.py:413-427,:708 — is_et_gate_skip() keys on the OFF-regime cron, so an IN-regime stand-down is counted as a healthy bake by counts_as_bake() and the only bounded auto-redispatcher does not rescue"
  - "GitHub stamps started_at == created_at on QUEUED jobs, so 'has no started job' is not a test for 'has not begun executing' and any job-stamp age window measures queue-entry"
  - "long-run frequency: run 31977372592 non-completed 26h (08-16T22:48:50Z→08-18T01:01:43Z); run 31913143619 28h"
  - "wedge origin: 31977372592's collect_tail targets self-hosted,theta-m1, which had no runner during the 08-17 outage — see DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP"
affects:
  - ".github/workflows/daily.yml"
  - "scripts/prophet_rescue.py"
  - "scripts/check_nightly_liveness.py"
confidence: high
reversibility: easy
decided_by: session claude/daily-collect-mutex-decision
decided_at: 2026-08-18
---

## What is still open

The double-collect vector is **not closed**. `concurrency:` cannot close it — each DST
cron and every `workflow_dispatch` occupy disjoint groups by design — and `et_gate`
cannot close it for the reasons above. Three options remain, all requiring an operator
call because each changes production nightly behaviour:

1. **Self-cancel at `collect` start.** First `collect` to start wins; the loser POSTs to
   its own `runs/{id}/cancel`. Precise, and the only mechanism that overrides the
   `always() &&` on every downstream job. Cuts against the standing "never cancel
   production runs" posture, and needs the watchdog fix below or the cancelled night
   reads as a wedge.
2. **Serialize rather than abort.** The later `collect` waits for the earlier to finish.
   Preserves both runs, but holds a self-hosted runner for hours and risks the 185m cap.
3. **Stay procedural.** Keep the existing rule (never dispatch while a `daily.yml` run is
   queued or in progress) plus preflight. That rule already existed on 2026-08-18 and was
   not followed; measured frequency of the concurrent shape is one occurrence.

Whichever is chosen, `is_et_gate_skip()` / `counts_as_bake()` must learn the new
stand-down state **first**, or a correct stand-down is indistinguishable from a healthy
bake and `prophet_rescue.py` will not rescue the night it skipped.

The complementary half of the 2026-08-18 incident — the orphaned `theta-m1` label that
wedged run 31977372592 for 26 hours and started the chain — is addressed separately by
PR #5867's checked-in runner-label registry.
