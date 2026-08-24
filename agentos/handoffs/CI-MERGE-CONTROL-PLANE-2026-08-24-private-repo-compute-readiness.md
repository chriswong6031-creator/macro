---
workstream: WS:CI-MERGE-CONTROL-PLANE
session: private-repo-compute-readiness-coordination-2026-08-24
model: codex
ended_because: blocked

mission: >
  Make Macro compute-ready for a future PUBLIC-to-PRIVATE visibility cutover without
  exhausting the GitHub Enterprise Cloud hosted-minute allowance, overloading the M2
  Ultra, or recruiting the M4 Pro / three M4 minis without measured post-optimization
  need. Preserve GitHub Actions as scheduler, the existing runner policy as declaration,
  current semantic CI proof and merge control as authority, and the two existing Agent OS
  workstreams as durable state. Stop before repository visibility mutation.

state_before: >
  The content/authentication cutover packet already described the repository-side
  anonymous-dependency migration, but the repository remained PUBLIC and its private-repo
  Actions cost/capacity was not accepted. Ordinary PR CI remained GitHub-hosted. PC Wave
  B/C infrastructure from merged PR #5722 existed but had no current one-slot or 3+1
  acceptance. Runner Fleet W2 still named its 12-hour M1 soak outstanding and W4 was not
  admitted. PR #6286 was the sole ci.yml carrier, OPEN/DRAFT/HOLD-FOR-SOL, and ordered by
  Sol to reconcile current main on the same branch before any downstream CI route wave.

changed:
  - path: agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-24-private-repo-compute-readiness.md
    what: >
      Records the coordinator's fail-closed compute-readiness ledger, frozen trusted-CI
      cutover sequence, hosted-minute measurement, hardware/resource receipts, blockers,
      and exact continuation. It changes no workflow, route, label, runner, policy,
      scheduler, merge authority, or repository setting.
  - path: agentos/discoveries/DSC-PRIVATE-CI-PACK-OFFLOAD-DOES-NOT-CLOSE-HOSTED-BUDGET.md
    what: >
      Makes the measured post-pack budget gap and candidate/execution amplification a
      falsifiable cross-session constraint, while keeping the hosted trust/control plane
      and M4 admission outside its authority.
  - path: agentos/workstreams/WS-RUNNER-FLEET-RESILIENCE.md
    what: >
      Accepts the terminal W2 listener soak while keeping W2 in progress; records the
      scratch-only TerraMaster receipt, reversible partial storage recovery and red guard;
      and keeps W4 held with zero generic macstudio or other production-lane admission.

verified:
  - claim: Current protected procedure was reloaded before packet modification.
    command: >
      git ls-remote mastermindx-market-intelligence/Mastermind refs/heads/master;
      read docs/sol_skills/INDEX.md plus COLD_START, COMMISSION_WAVE, RECONCILE_STATE,
      REVIEW_RETURN and CLOSEOUT from the same protected commit.
    result: >
      Protected Mastermind master 12117ca576cec2c4f054664dd62c4e0809f27e75;
      schema mastermind.sol_skillpack.v1; version 1.0.0; minimum bootstrap major 1.
  - claim: The packet carrier began from a clean current Macro main.
    command: git rev-parse HEAD in a standalone sparse clone after fetching origin/main.
    result: >
      Final packet base 6ae25606059c7b144fc907dfc4841e8fab403c24. Main is volatile and must be
      re-read immediately before review, merge, or any later production action.
  - claim: Repository visibility was not mutated.
    command: gh api repos/mastermindx-market-intelligence/macro --jq visibility/private.
    result: PUBLIC / private=false at 2026-08-24T07:53:35Z.
  - claim: The authoritative organization billing ledger was not available to this operator.
    command: gh api orgs/mastermindx-market-intelligence/settings/billing/actions.
    result: >
      HTTP 410 moved endpoint followed by an admin:org requirement. No credential scope
      was expanded. All minute figures below are explicit run/job-duration projections,
      not a billed-usage receipt.
  - claim: The current CI estate would materially exceed the 50,000-minute private allowance.
    command: >
      Sample the latest 100 completed ci.yml runs and every job through the GitHub Actions
      API; round each hosted job up to a whole minute; separately sample the latest 100
      fences runs and the preceding 24 hours of other hosted workflows.
    result: >
      The 100 CI runs span 19.5125 hours and contain 1,182 hosted jobs / 10,854 rounded
      job-minutes: 896 pack jobs / 9,782 minutes and 286 control jobs / 1,072 minutes.
      The same sample contains 92 PR events and 8 dispatches, only 11 distinct associated
      PRs, 100 distinct heads, 28 cancelled runs, 67 successes and 5 failures. The latest
      100 fences runs add 100 rounded minutes over 17.925 hours. The top ten other hosted
      workflows used 2,271 rounded minutes in the measured 24-hour window; sampled long
      tail brings the non-CI estimate to approximately 2,424 minutes/day. Straight-line
      raw-job-minute projection is therefore approximately 477,000 minutes/month before
      any private billing multiplier or organization-wide use. This is a capacity signal,
      not the unavailable billing ledger.
  - claim: Moving only the expensive CI packs is insufficient.
    command: >
      Replace the sampled 477 ci-plan minutes with 98 minutes (one rounded minute for each
      observed planner job, matching PR #6286's below-60-second target), remove the 9,782
      sampled pack minutes from hosted execution, retain hosted contract-delta/ci-gate,
      fences and non-CI workflows, then normalize to 30 days.
    result: >
      Projected controls approximately 25,600 minutes/month, fences approximately 4,000,
      and other hosted workflows approximately 72,700: approximately 102,000 raw rounded
      hosted job-minutes/month after the first pack cutover. The first production route
      wave therefore cannot claim private readiness or meaningful allowance headroom.
  - claim: PR #6286 remains the sole ci.yml carrier and retains Sol's barrier.
    command: gh pr view 6286 plus current remote-head and changed-path census.
    result: >
      Existing branch codex/ci-plan-working-tree-containment-w3-20260822; OPEN; DRAFT;
      HOLD-FOR-SOL; no merge-on-green or native auto-merge; remote head remains
      7fe2a5604f4938161b2630f6f6c15d8d436a3822. No replacement branch or PR was created.
      An unpublished public-safe reconciliation candidate 22c8bfef3d6dbc25fbc240e4d65cab34d6779ca2
      was preserved but not pushed after fresh main ba44b49b0d97e00b25635db2d92a25aec2147a06
      changed canonical input .github/ci/legacy-jobs.yml by 24 additions. A new current-main
      same-carrier merge plus exact current-manifest proof is required before release.
  - claim: The W3 full physical oracle was recovered without competing with production work.
    command: >
      Incrementally fetch the existing sole carrier and main history into the retained
      non-sparse oracle, then hold all parity and owning tests behind an all-idle M2 guard.
    result: >
      The retained oracle contains 3,205,788 packed objects in two packs totaling
      22,823,579,787 bytes (21.36 GiB). Fetch completed successfully. The bounded final
      window remained red at load 21.88/23.79/23.88 with a production Runner.Worker,
      unrelated pytest and heavy Git activity, so exact current-manifest parity and the
      owning suite were not started. No foreign job was paused or cancelled.
  - claim: PC Wave B/C was drained and its configured capacity already matched the runbook target.
    command: >
      Direct WSL/Windows resource census plus GitHub repo-runner census before the single
      authorized WSL restart.
    result: >
      No Runner.Worker or active pc-* job; Ubuntu-24.04; 16 CPUs; 46,285,840,384 bytes
      WSL memory; 8,589,934,592 bytes swap; 902,687,125,504 bytes disk available;
      approximately 23.9 GiB Windows physical memory free; no NVIDIA compute process.
      .wslconfig was not edited because the target was already present.
  - claim: PC registrations and isolation substrate existed, but current canary acceptance did not.
    command: >
      Read host service/config identities and systemd properties; compare with current
      runner policy and Wave B/C runbook; query GitHub repo runner state.
    result: >
      Intended macro-home-canary registrations existed as pc-ci-1/2/3 agent IDs 12/13/14
      and pc-render-1 agent ID 15, with sealed macroci service isolation, read-only shared
      cache and one-job listener behavior. Organization runner-group server state could
      not be independently read because the current credential lacks runner-group/admin
      permission. Legacy repo listeners pc-render-2/3/4 (IDs 32/33/34) still existed and
      prevented a unique pc-render-1 reservation claim.
  - claim: PC graduation correctly stopped before spending a canary on a known-broken substrate.
    command: >
      Test WSL resolver/HTTPS/broker reachability and cache update before dispatch.
    result: >
      Windows DNS worked, but WSL nameserver 10.255.255.254 could not resolve github.com;
      intended listeners reported broker.actions.githubusercontent.com connection errors;
      the root cache updater failed 128; shared cache main remained
      52fc5ce3ac872e7a4958f1e2d763626ef7d917e7 and lacked the then-current candidate with
      lazy fetching disabled. No canary was dispatched.
  - claim: The single bounded PC restart did not recover and no blind retry occurred.
    command: >
      After drain, issue one ordinary wsl.exe shutdown/restart attempt and poll the existing
      SSH/Tailscale channel a bounded number of times.
    result: >
      The detached Windows relaunch helper had malformed PowerShell quoting and failed before
      shutdown; shutdown then severed the only reachable WSL channel. winpc-wsl last seen
      2026-08-24T07:40:00.1Z; all bounded recovery polls failed; native Windows Tailscale was
      already offline since 2026-08-06. The operator owns this error. No second restart,
      network edit, listener deletion, workflow dispatch, or route change was attempted.
  - claim: TerraMaster is qualified only for a narrow non-secret scratch role.
    command: >
      Interface/device/SMART/APFS census; 8 GiB sequential write/read; 5,000-file metadata
      test; SHA comparison across controlled unmount/remount; negative failure path.
    result: >
      USB4 40 Gb/s TDAS with a Lexar 4 TB NVMe and approximately 4 TB free; SMART verified;
      1.27 GB/s write and 1.69 GB/s read; 5,000 creates in 0.28 seconds; exact UUID and
      content hash persisted. Volume ownership remains disabled and needs a native admin
      action, so secrets, runner workspaces and canonical state remain forbidden there.
  - claim: The outstanding M1 W2 12-hour listener soak is terminal and positive.
    command: >
      Reduce the existing W2 monitor ledger and reconcile live listener/service identity.
    result: >
      73 samples from 2026-08-21T08:07:28Z through 20:07:56Z; three distinct guarded
      listener PIDs in every sample; 219 guard lines; lightweight_allowed=true throughout;
      no ENOSPC recurrence; no monitor remains alive. This proves guarded diagnostic
      listener continuity, not full-work storage safety or W4 production admission.
  - claim: M1 recovery remained reversible and W4 remained unadmitted under the red guard.
    command: >
      Fixed-set Chrome clone census, open-handle exclusion, guarded single-purpose copy,
      M2 listener/resource monitoring, M1 disk guard and workflow-consumer census.
    result: >
      The active 2,132,104-KiB clone was excluded. Scratch holds 72,218,204 KiB of the
      fixed 153,192,948-KiB inactive set; source is untouched and resumable. M1 finished
      with approximately 110.8 GiB free, below the 200-GiB full-work floor. W4 found 50
      generic macstudio jobs across 33 workflows plus 18 macstudio-light jobs and admitted
      zero production lanes, labels or routes; generic macstudio remains forbidden.
  - claim: The records-only packet validates on its exact fresh-main carrier.
    command: python3 scripts/agentos.py validate; git diff --check.
    result: >
      675 Agent OS records; 0 errors; 351 warnings from the existing sparse estate;
      whitespace check passed. Changed scope is exactly one existing workstream plus one
      handoff and one discovery under agentos/.

unresolved:
  - >
    PR #6286 must create a new public-safe same-carrier merge from unchanged remote
    7fe2a560... to a freshly observed main because the canonical legacy-job manifest moved.
    Reuse the retained 21.36-GiB oracle, then run exact full/sparse parity, hostile mutations,
    the owning suite, three successful same-head ci-plan observations below 60 seconds and
    binding ci/fences/ci-authority before returning OPEN/DRAFT/HOLD-FOR-SOL to Sol.
  - >
    The PC host requires one native Windows-side launch of Ubuntu-24.04. Until WSL is back,
    DNS/broker/cache recovery, legacy-listener disablement, one-slot parity, second-tree
    contamination isolation, cache-negative refusal and 3-CI-plus-1-render acceptance are
    unproved. Production trusted-CI route work is forbidden.
  - >
    M1 storage recovery is paused with a resumable 72,218,204-KiB partial copy of the fixed
    inactive Chrome code-sign clone set on Terra scratch; source is untouched and the active
    2.03-GiB clone is preserved. Resume one low-priority parent-level hardlink-preserving
    stream only after a fresh all-idle guard. W4 remains held until exact parity/recovery,
    at least 200 GiB free and below 85% use, durable W2 reconciliation and a separate
    Sol-accepted capability-specific lane.
  - >
    A billed Actions usage receipt and current organization runner-group configuration
    require organization-owner/read permission. Missing read authority is not permission
    to refresh credentials or weaken the trust boundary.

unverified:
  - >
    The exact billed Actions usage for the current enterprise billing cycle, including
    organization-wide consumers and any platform billing adjustment. An organization owner
    must read the current Actions usage ledger; this packet deliberately does not infer it
    from public-repository run durations.
  - >
    Current server-side macro-home-canary selected-workflow and repository access settings.
    Verification requires the organization runners/runner-groups read permission that this
    operator does not hold.
  - >
    Every acceptance step after native PC recovery: DNS/broker/cache health, one-slot
    exact-tree parity, second-tree contamination isolation, cache-negative refusal,
    three-plus-one resource/reservation proof, trusted production route behavior and its
    natural post-cutover queue/cost impact.
  - >
    The final M1 storage floor and W4 route receipt. The large inactive-clone recovery is
    intentionally reversible until copy parity is complete; no guard or production claim
    may be advanced from transfer progress alone.

next_actions:
  - >
    Chairman/operator at the native Windows console: run
    `wsl.exe -d Ubuntu-24.04 --exec /bin/true` or open Ubuntu-24.04 once. This is recovery,
    not a route change.
  - >
    PC operator then re-pins fresh main; proves WSL DNS, HTTPS, Actions broker, Tailscale,
    mounts and resources; advances the root-owned read-only cache to exact main; confirms
    zero jobs; disables without deleting/deregistering pc-render-2/3/4; proves pc-render-1
    unique; executes one-slot acceptance on two exact trees; then executes three CI slots
    plus one independent render reservation. Stop and return the receipt with no production
    route change.
  - >
    In the next independently clean M2 window, continue the same #6286 branch from remote
    7fe2a560...: reconcile directly to then-current main, incrementally update the retained
    oracle at /tmp/w3-pr6286-full-b390-35f64da0, run exact current-manifest parity and owning
    proof, push once non-force only after a fresh carrier/main CAS, collect three same-head
    ci-plan runs below 60 seconds, and return OPEN/DRAFT/HOLD-FOR-SOL.
  - >
    Resume the existing M1 recovery only after W3 releases the heavy window and M2 is freshly
    all-idle. Use one low-priority parent-level hardlink-preserving stream, prove checksum and
    metadata parity, recover only verified inactive explicit paths, and require at least
    200 GiB free plus below 85 percent use before closing W2. Keep W4 held.
  - >
    Sol reviews the eventual exact head of PR #6286 and the independent PC capacity packet.
    Both must be accepted before any trusted-CI production cutover carrier is commissioned.
  - >
    First cutover capability: add one main-defined reusable trusted-pack executor pinned by
    full repository path to refs/heads/main and selected in macro-home-canary. Its interface
    accepts only bounded candidate/plan identities; no caller-supplied command or runner
    label; no repository secret or write token; exact-tree/cache/plan verification remains
    fail-closed. Prove check-name and caller/called-workflow behavior in canary before route
    use.
  - >
    Second cutover capability: route only same-repository trusted execution packs through
    that main-defined executor. Fork/untrusted PR jobs, ci-plan, contract-delta, ci-gate,
    fences, ci-authority and merge-on-green remain independently GitHub-hosted. Preserve
    current semantic evidence, exact-base causality, check identities and merge controller.
    Route-only rollback returns packs to hosted execution.
  - >
    After natural production observations, measure hosted minutes, queue pickup/completion,
    cancellation amplification, PC CPU/load/memory/swap/disk, independent render pickup and
    M1/M2 contention. Use those receipts to commission one further expensive trusted lane at
    a time until projected hosted use has meaningful headroom below 50,000/month.
  - >
    Do not recruit the M4 Pro or any M4 mini unless post-#6286, post-PC-cutover and post-M1
    telemetry still fails a quantified queue/resource/SLO gate. Return the final private
    compute acceptance packet to Sol, then stop before visibility mutation.

do_not_redo:
  - Do not fork, rebuild, supersede, mark ready, arm or merge PR #6286.
  - >
    Do not expose persistent home runners to PR-authored workflow code. The runner-group
    trust boundary remains restricted to exact main-defined workflows; repository lint is
    defense in depth, not the server-side admission authority.
  - >
    Do not move hosted control-plane or untrusted jobs merely to improve the projection.
    Do not remove semantic proof, exact-base healing, fences, ci-authority, merge-on-green,
    cancellation semantics or required check identities.
  - >
    Do not create a runner database, scheduler, queue, CI proof system, retry/lifecycle
    service, alternate policy file or side-band route declaration.
  - Do not assign generic macstudio to the M1; W4 may admit one capability-specific lane only.
  - Do not use the M4 fleet as a substitute for repair, cancellation control or measurement.
  - Do not mutate repository visibility from this program.

danger_areas:
  - >
    Runner-group workflow restrictions are load-bearing. A local workflow test cannot prove
    the current server-side selected-workflow set; require the organization-level receipt
    before production route acceptance.
  - >
    Same-repository reusable-workflow syntax using `./` selects the caller commit, not current
    main. The trusted executor must be referenced by full repository path at refs/heads/main
    (or a separately reviewed immutable SHA), and its actual check-name/permission semantics
    must be demonstrated before merge-controller reliance.
  - >
    Workflow run counts amplify candidate work: the sampled CI window had 100 distinct heads
    for only 11 associated PRs. Capacity planning on PR count alone will understate load;
    queue cancellation and exact-candidate identity must be part of production telemetry.
  - >
    The approximately 102,000-minute post-pack estimate is a raw rounded-job-minute model,
    not a promise. It excludes unknown organization-wide usage and any platform billing
    multiplier, and therefore establishes NOT_READY rather than a budget forecast.
---

# Private-repository compute readiness — COO acceptance packet

## Verdict

**NOT READY / FAIL-CLOSED.** The earlier content/authentication cutover preparation is
not a compute-capacity acceptance. At this packet, Macro is still PUBLIC; fresh main
materially changed #6286's canonical CI manifest before exact proof, so the unpublished
candidate was correctly withheld; PC Wave B/C has not proved even one accepted CI slot
after a WSL resolver failure and unsuccessful restart; M1 storage recovery is safely
partial and W4 is not admitted; and the best first-wave hosted-minute model remains about
twice the Enterprise Cloud allowance.

No production CI route and no visibility setting changed. M2 remains the existing
production safety net. M4 Pro and all three M4 minis remain outside the fleet.

## Capability ledger

| Capability | State | Acceptance boundary |
|---|---|---|
| Protected operating procedure | PROVEN_CURRENT | Skillpack 12117ca5… loaded from protected Mastermind master |
| #6286 planner containment | BUILT_NOT_PROVEN / HOLD | Remote 7fe2a560… unchanged; unpublished 22c8… withheld after current manifest drift; fresh same-carrier proof owed |
| PC isolated runner substrate | BUILT_NOT_PROVEN | Registrations/services observed; org group state unreadable |
| PC network/cache path | BROKEN / DARK_OR_DISCONNECTED | Native WSL relaunch, DNS/broker and exact-main cache proof owed |
| PC one-slot parity | NOT_BUILT as current receipt | Two exact trees, parity, contamination and negative-cache refusal owed |
| PC three CI + one render | NOT_BUILT as current receipt | Concurrent resource and reservation receipt owed |
| Terra non-secret disposable scratch | PROVEN for narrow role | Ownership enforcement remains admin-gated |
| M1 W2 listener soak | PROVEN | 12-hour three-listener diagnostic continuity; no full-work claim |
| M1 storage headroom | IN_PROGRESS / guard false | 72,218,204 KiB safely copied; source untouched; ~110.8 GiB free; >=200 GiB and exact parity owed |
| M1 W4 production lane | HELD | One capability-specific measured-safe route only; generic macstudio forbidden |
| Trusted CI production cutover | NOT_STARTED | #6286 acceptance and PC 3+1 acceptance are predecessors |
| Private hosted-minute readiness | NOT_READY | Natural post-cutover projection must show meaningful headroom below 50k |
| Repository visibility | PUBLIC / STOPPED | Chairman-only mutation after Sol accepts the final packet |

## Frozen architecture and wave law

The smallest trusted cutover is not “put ci.yml on the PC.” PR-authored workflow code
must never acquire a persistent home runner merely because the PR comes from the same
repository. A selected main-defined reusable executor owns the self-hosted job; the PR
workflow supplies bounded identities, and the executor re-derives and verifies the exact
tree and authoritative plan. Forks and every untrusted path stay hosted. The hosted
planner/gate/fences/authority/merge controller remain independent, so loss or compromise
of the PC execution plane cannot manufacture merge authority.

This is a frozen proposal, not an implementation claim. It becomes commissionable only
after #6286 and PC capacity are separately accepted. Every later cost wave must move one
independently useful trusted capability, carry a route-only rollback, and return natural
production plus resource/queue receipts before the next lane is selected.

## Native recovery action

At the Windows console, run:

```powershell
wsl.exe -d Ubuntu-24.04 --exec /bin/true
```

Opening the Ubuntu-24.04 app once is equivalent. The PC operator resumes only after that
native action and follows the fail-closed order recorded above.

## Stop state

Return this packet to Sol as a blocker/continuation packet. It is not permission to merge
#6286, change production routing, add M4 capacity, or flip repository visibility.
