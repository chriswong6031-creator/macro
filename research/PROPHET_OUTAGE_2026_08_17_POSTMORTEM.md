# Prophet outage 2026-08-14 → 08-17 — postmortem and hardening

**Status:** boards healing on dispatch 32081969617 (peer session owns the watch);
hardening PR = this document's PR. Owning workstream: `WS:PROPHET-US-AVAILABILITY`.
Records: `DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP`,
`DSC:RULESET-FREEZE-BLINDS-EVERY-BUILD-INSTRUMENT`,
`DEC:PROPHET-NIGHTLY-WEDGE-HARDENING`.

## What users saw

Every Prophet board frozen, each at its last successful publish: US at 08-13,
China at 08-14, HK at 08-12, Canada at 08-11, International stale. Force-majeure
report filed by the operator 08-17 ~23:30Z.

## Root cause — three independent failures stacked

**1. A repository ruleset froze every push to main (08-15 01:20Z → 08-17 ~23:40Z).**
`ci-recovery-bootstrap-freeze-2026-08-15` (id 20878487, bypass = org admin only,
created with no DEC record) rejected all nightly pushes with GH013. The engine
kept **building boards correctly every night** — then died at the checkpoint:
`12 attempts failed … R2 remains on its prior accepted object, and the final
engine commit is fenced from publishing this uncheckpointed Prophet tree` (run
31913143619, job 95103895599). Blast radius was platform-wide: dashboard-bot
commits/day 251 (08-13) → 192 → 8 → 1 → 0 (08-17). The operator deleted the
ruleset 08-17 ~23:40Z (verified: `GET /rulesets` → empty).

**2. An orphaned runner label turned `collect_tail` into a nightly hostage-taker.**
`collect_tail` was pinned `runs-on: [self-hosted, theta-m1]` (2026-07-26, the
store-bearing M1 host). The M1 runners (mac-builder-1/2) were deregistered
without the label moving — the label lived ONLY in runners-API state, so nothing
in the repo pinned or missed it. Mechanics (`DSC:QUEUED-JOB-HOSTAGE…`):

- a job queued on a label with no live runner can never start; GitHub kills a
  queued job only after **24h**;
- until then the run stays "alive" (`queued`/`in_progress` at run level);
- an alive scheduled run holds its per-cron concurrency group
  (`pipeline-daily-3-cron-30 22 * * *`);
- the NEXT night's real slot goes `pending` with **zero jobs created**, and only
  starts when the predecessor's queued job hits the 24h kill — so each night's
  bake started ~3-6h later than the last (22:49 → 02:35 → ~06:07 projected), a
  self-perpetuating cascade with no red anywhere.

**3. Every watchdog was structurally quiet.**

| Instrument | Why it stayed quiet | Fix (this PR) |
|---|---|---|
| `nightly-liveness` check B | in-flight run → INDETERMINATE with **no age cap**; the hostage was "still baking" for 30h+ | `IN_FLIGHT_MAX_AGE = 14h` → WEDGED IN FLIGHT breach; third daily look (20:00Z) |
| `nightly-liveness` check C | flat `MAX_SESSIONS_BEHIND=1`: a missed **Friday** bake reads "1 behind" all weekend — first possible alarm Tuesday | `STALE_GRACE = 10h`: past boundary+10h with a read run list and nothing fresh alive, 1-behind breaches |
| `prophet-rescue` §0.4a | "never dispatch while a run is alive" read the hostage as a live bake; red runs said *"an operator look is owed"* for two days | §0.4a amendment: a **proven wedge** (jobs-API evidence, fail-closed) no longer blocks dispatch |
| et_gate no-op slot | the EST-cron run concludes `success` in 2s nightly — hollow greens that satisfy "did it run?" glances | already handled by `counts_as_bake` in both watchdogs (kept) |

**Aggravator — runner-pool starvation.** Only mac-builder-5 carried `macstudio`.
The 13F census lane (merged 08-17, crons every 30 min 12-23Z, 180m cap,
`runs-on: macstudio`) plus the filings fast-path saturated it: census runs
superseded each other all afternoon without ever executing, and closing-bell /
codex-research / the daily dispatch queued behind. Not a root cause, but it
removed all headroom the recovery needed.

## Triage actions taken (08-17 23:35Z → 00:45Z, receipts on issue #5742)

1. 23:47Z `theta-m1` label → mac-builder-3 (runner 35, runners API). collect_tail
   assigned within minutes; the hostage run began draining. Safe by the job's own
   design: tape_flow probes and self-skips (#3644), W11 witness rides
   keep-last-real. KEPT.
2. 23:54Z `macstudio` label → mac-builder-4 (runner 29) — **REVERTED-AND-HARMFUL
   (removed 00:44Z; do not re-apply).** mac-builder-4 is the merge-control
   runner: merge-on-green.yml checks out a NON-CONE SPARSE 3-path tree
   (scripts/merge_on_green.py, scripts/gh_path_filter.py, .github/workflows)
   into the SHARED workspace `actions-runner/_work/macro/macro`, and whichever
   lane touched the workspace last wins. Recovery dispatch 32081969617's engine
   (job 95550650855) landed there and died in 2.5 min at
   `pip install -r requirements.txt` — file absent in the thin tree — with
   every later `if: always()` step cascading. Diagnosed on-host by the peer
   session (sparse-checkout list read directly; the 3-path pattern block
   appears ~7×, evidence the workspace state is CUMULATIVE across runs, which
   is the property that makes the collision possible). Lesson: build labels and
   the merge-control runner must never mix while lanes share a work dir — a
   slow bake beats a fast failure.
3. 23:48Z peer session dispatched daily run **32081969617** (dispatch group is
   separate from the cron groups, so it bypassed the deadlock; 1 of 2 budget).
   It FAILED per (2); the peer re-dispatched **32084697588** (00:29Z, slot
   2 of 2) after the de-label and owns the new run to conclusion + first-pass
   US verification. Both dispatch slots are now spent — any further dispatch
   is the operator's.
3b. 00:5xZ `macstudio` label → **mac-builder-light** (runner 28) — KEPT, and
   this time the workspace was verified READ-ONLY BEFORE the label (the check
   mac-builder-4 failed): core.sparseCheckout=false, no sparse file,
   requirements.txt present, full 40-entry tree. Restores the pool to two
   verified-full-checkout hosts (mac-builder-5 + mac-builder-light) so the
   ~13 serialized queued nightly jobs drain at double rate. Tradeoff: renders
   (render-heavy shares this runner) queue behind nightly jobs while boards
   are stale — accepted; renders coalesce by design.
4. Operator asked (issue #5742) to cancel debris run 32077948964 once the
   dispatch is green — sessions correctly cannot cancel daily.yml runs
   (`gh_quota_guard` shape 6). With mac-builder-4 de-labeled, the debris run no
   longer carries the sparse-workspace exposure either.

## Hardening shipped in this PR

- **daily.yml `collect_tail`** unpinned to `macstudio` — the hostage class dies
  at the root; re-pin rule documented for the `m1-theta` canary graduation
  (.github/runner-policy.yml).
- **check_nightly_liveness.py**: in-flight age cap (14h) + weekend grace (10h) +
  new selftest vectors; third daily look 20:00Z in nightly-liveness.yml.
- **prophet_rescue.py**: `wedged_run` classifier (run ≥6h old, zero jobs in
  progress, every live job queued ≥3h — every input fail-closed) lets the lane
  dispatch THROUGH a hostage; budget and floor still bind; never stops anything.
  One extra jobs read, alarm path only.
- **CLAUDE.md / AGENTS.md**: the "main carries no branch protection" law is
  annotated as externally violable; ruleset check added to push-failure triage;
  deliberate freezes owe a DEC record + expiry plan.
- **config/dag.yml**: W11 witness provenance comment updated to the unpin.

## Deliberately NOT done, and why

- **No `cancel-in-progress` flip on the cron groups.** A same-slot refire 24h
  later would guillotine a slow-but-alive bake; the house law is explicit that
  the acceptable failure mode is *a double-run, never a zero-run*
  (daily.yml concurrency comment; tests/test_daily_et_gate.py delay-tolerance
  vector: a firing queued 5h must still proceed).
- **No wall-clock stand-down in et_gate.** Same design vector — a late real
  firing may be the only bake the night gets.
- **No session-side cancellation of the debris runs.** Operator-only by standing
  law; the ask is filed with receipts.

## Open follow-ups (chipped)

1. Per-market board freshness in nightly-liveness (CA froze 08-11 with zero
   noise — US `source_asof` is the only graded stamp today).
2. 13F census lane cadence/runner budget (owner: FF-1 program) — 30-min crons ×
   180m cap on the nightly's runner is a standing starvation source.
3. Label registry with a live-pool audit (labels referenced by workflows must
   have ≥1 online runner; needs an admin-scoped token — `ADMIN_GH_TOKEN`?).
4. close-pass.yml POOL model still names mac-builder-1/2 (tests/test_close_pass_lane.py).
5. M1/theta host revival re-pins collect_tail (runner-policy `m1-theta` canary).
6. Ledger audit for 08-17 double-advance if debris run 32077948964 fully re-baked.
7. **Workspace isolation for merge-control (from the 00:20Z regression):** the
   merge-on-green runner must never be eligible for build labels while lanes
   share `_work/macro/macro` — either pin that invariant (runner-policy +
   a check), give merge-on-green its own work directory, or make its checkout
   restore a full tree on exit. Also: its non-cone sparse pattern block
   appends (~7 copies observed) instead of replacing — the workspace is
   cumulative, not reset per run. **Verification recipe (peer-measured):**
   judge a runner workspace by CONFIG, never by `ls` — `git config --get
   core.sparseCheckout` + the pattern file are stable host properties (they
   even survive actions/checkout's `sparse-checkout disable`, measured), while
   file presence is racy: mac-builder-light's tree was observed re-cloning
   mid-read (requirements.txt present → absent seconds apart, HEAD flipping
   main → unborn master) — a file check samples a moving target and misleads
   in BOTH directions.
