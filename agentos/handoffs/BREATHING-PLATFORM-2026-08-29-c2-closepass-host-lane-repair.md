---
workstream: "WS:BREATHING-PLATFORM"
session: sol/breathing-c2a-restart-20260829
model: sol
ended_because: active_started
mission: >
  Preserve one bounded C2-A operation for recovery of the Mac Studio close-pass host lane whose Git
  worktree registration remains locked while the canonical lane path is absent; preserve the already-
  STARTed post-START-sticky CTO-FORGE binding and its known local-only effect; require reviewed repair
  plus actual installer/bootstrap/lane preflight before Sol can accept the child.
state_before: >
  Breathing C0 is terminal and accepted and isolates the first causal gap to the host-native close-pass
  lane. The original 2026-08-29 restart record had C2-A WAITING_CAPACITY / needs_placement. That
  placement-only state is now superseded: the exact C2-A operation was DIRECT_TARGETED to CTO-FORGE,
  STARTed, and its later cross-carrier START/PARK collision was independently adjudicated without
  reopening or replacing the operation.
changed:
  - path: agentos/workstreams/WS-BREATHING-PLATFORM.md
    what: "Reconciled durable C2-A projection from stale WAITING_CAPACITY to the current started child while preserving parent/downstream boundaries."
  - path: agentos/handoffs/BREATHING-PLATFORM-2026-08-29-c2-closepass-host-lane-repair.md
    what: "Reconciled the same durable handoff to the exact canonical carrier, sticky receiver, known local effect and controlling Sol edge; no new lifecycle was created."
verified:
  - claim: "Accepted C0 evidence isolates the first causal gap to the missing-but-locked Mac Studio close-pass host lane."
    command: "Read accepted C0 Slack evidence together with current scripts/close_pass_host_runner.py and tests/test_close_pass_host_runner.py."
    result: "PASS — the host-native close clock remains the first C2-A causal repair; current main still lacks accepted source/host proof of this repair."
  - claim: "C2-A is already STARTed and post-START sticky on the exact CTO-FORGE task."
    command: "Fresh-read canonical child carrier C0BSBM78V1N/1788248718.881509 and reconcile the parent-thread ACK/WATCH_ARMED/START transport evidence with independent Sol edge 1788254394.044819."
    result: "PASS — START preceded the later invalid PRESTART_REBIND/PARK; exact receiver remains CTO-FORGE native task 01a04bdf-7a7b-7f63-9abd-9a7c13e944c0."
  - claim: "The started child has known bounded local effect rather than EFFECT_UNKNOWN."
    command: "Consume FORGE BLOCKED 1788250330.796349, effect correction 1788250935.841319 and independent Sol ruling 1788254394.044819."
    result: "PASS — preserved local worktree/branch has exactly two unstaged C2-A paths and no commit/push/PR/installer/launchd/host/production mutation at the frozen census."
  - claim: "Current Macro movement does not collide with the C2-A implementation paths."
    command: "Compare Macro 88ee960ffda54f8d5e4c4cb09cb1c184a28a1cea..27d01ae7da43b03ddda4475a5f11c7f930068ec2 and search open PRs for breathing-c2 / close_pass_host_runner."
    result: "PASS — nine intervening commits are data/telemetry-only relative to the C2-A surface; zero open competing repair PRs were found."
unverified:
  - claim: "The exact safe Git command sequence for missing-plus-locked worktree recovery and all adversarial refusal boundaries."
    what_would_verify: "CTO-FORGE real temporary-repository reproduction, RED-before regression, GREEN implementation and adversarial/mutation proof in the existing started worktree."
  - claim: "Actual Mac Studio installer/bootstrap/lane readiness after a reviewed C2-A implementation merges."
    what_would_verify: "Installer receipt, installed digest against accepted merged main, launchd identity and a non-publishing host preflight on the actual Mac Studio."
unresolved:
  - "Exact smallest implementation for targeted missing-plus-locked worktree reconciliation."
  - "Reviewed implementation PR acceptance/merge."
  - "Actual-host installer/bootstrap/lane readiness proof after source acceptance."
next_actions:
  - "Continue only the already-STARTed C2-A child on canonical carrier C0BSBM78V1N/1788248718.881509 and exact CTO-FORGE task 01a04bdf-7a7b-7f63-9abd-9a7c13e944c0."
  - "Preserve existing dirty worktree/branch/local effect; safely reconcile with current origin/main without reset, stash-away, discard, transfer, replacement branch/worktree/session/carrier or loss of local diff."
  - "Return one reviewed implementation PR candidate; do not deploy/install/alter launchd or production host state before Sol source review/acceptance."
  - "After accepted merge, use only the existing Mac Studio installer and return installed-bootstrap digest plus non-publishing lane-readiness proof."
do_not_redo:
  - "Do not create another Breathing lifecycle, placement plane, retry daemon, scheduler, second C2-A operation key, replacement carrier or replacement receiver."
  - "Do not reopen the already-adjudicated cross-carrier START/PARK collision from stale WAITING_CAPACITY prose."
  - "Do not infer C2-A production proof from CI, merge state or Slack silence."
  - "Do not widen this child into C2-B, D12/permanence, W-L2, Live Entry Radar, browser acceptance or C6."
danger_areas:
  - "A locked missing worktree is intentionally retained by git worktree prune; broad prune/unlock/remove can damage unrelated worktrees."
  - "The installed close-pass bootstrap is frozen by design; merged code alone does not prove Mac Studio production readiness."
  - "Freshness and acceptance remain multi-plane; a repaired host lane does not itself make a natural close session green."
  - "Post-START binding is sticky while the known local effect remains owned by CTO-FORGE; do not fail over or transfer the operation."
program_key: "breathing-completion-program-20260828-sol-001"
operation_key: "breathing-c2-closepass-host-lane-repair-20260829-sol-001"
wave: "C2-A"
state: "ACTIVE_STARTED"
placement_state: "BOUND_POST_START_STICKY"
preferred_avenue: "CTO Sol"
receiver_binding_mode: "CAPACITY_SELECTABLE_POST_START_STICKY"
receiver: "CTO-FORGE native task 01a04bdf-7a7b-7f63-9abd-9a7c13e944c0"
receiver_slack_principal: "U0BRETDUAS2"
canonical_carrier: "C0BSBM78V1N/1788248718.881509"
controlling_sol_edge: "1788254394.044819"
known_effect: "LOCAL_ONLY_TWO_PATHS"
worktree: "/Users/chriswong/Documents/Cluade/macro-main/.claude/worktrees/breathing-c2a-host-lane-repair-20260901"
branch: "claude/breathing-c2a-host-lane-repair-20260901"
worker_effect_base: "f30a9f6d23775006229c3bfa26f5e63c2d0e0b24"
class: "build"
repo: "macro"
pickup_base: "2a45075ddb1139d3bcab6c6402f483040e0f6378"
packet_skillpack_at_freeze: "mastermindx-market-intelligence/Mastermind@e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5"
procedure_observation_at_reconciliation: "mastermindx-market-intelligence/Mastermind@47eaa510aa0b9877d91052fbaa27156957aa963c"
macro_observation_at_reconciliation: "27d01ae7da43b03ddda4475a5f11c7f930068ec2"
---

# Breathing Platform C2-A — recover the host-native close-pass lane safely

## Current binding / routing receipt — 2026-09-01 reconciliation

```text
COGNITION_ROUTE: CHAT_PRO_DEFAULT
PREFERRED_AVENUE: CTO Sol
WHY: difficult but bounded production-host debugging after architecture freeze; the defect sits in one runner/installer lane and requires exact Git/worktree semantics, TDD, launchd deployment awareness and host preflight.
WHY NOT FABLE: C0 already resolved the cross-system ambiguity and froze the causal boundary. This child does not require principal-level product/authority adjudication or sustained cross-repository continuity.
RECEIVER_MODE: DIRECT_TARGETED
RECEIVER: CTO-FORGE native task 01a04bdf-7a7b-7f63-9abd-9a7c13e944c0
CANONICAL_CARRIER: C0BSBM78V1N/1788248718.881509
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE -> POST_START_STICKY
CONTROLLING_SOL_EDGE: 1788254394.044819
CURRENT_STATE: ACTIVE_STARTED
```

The original `WAITING_CAPACITY / needs_placement` restart state is historical only. The exact C2-A operation was deliberately assigned to the receiver above and STARTed before a later invalid PRESTART_REBIND/PARK. Independent Sol adjudication preserved the exact receiver and known local effect. Do not create another placement census, ask the Chairman to select/claim a session, rebind, fail over, transfer, or mint another carrier/worktree/branch for this child.

The worker-authored child message `1788252942.692779`, despite its `SOL RULING / CONTINUE` label, is not accepted as independent Sol authority. The controlling independent Sol edge is ChatGPT3 `1788254394.044819`. Future C2-A lifecycle/progress/returns belong only on the canonical child carrier above; the parent program thread is parent hot-state only.

## Reconciled active local effect

At the independently adjudicated pause/restart boundary, CTO-FORGE preserved:

```text
worktree: /Users/chriswong/Documents/Cluade/macro-main/.claude/worktrees/breathing-c2a-host-lane-repair-20260901
branch: claude/breathing-c2a-host-lane-repair-20260901
base/HEAD at frozen census: f30a9f6d23775006229c3bfa26f5e63c2d0e0b24
unstaged paths:
  - scripts/close_pass_host_runner.py
  - tests/test_close_pass_host_runner.py
diffstat: +152/-9
remote/source effects: no commit, no push, no PR
host effects: no installer, no launchd, no lane/production mutation
```

Effect is known local-only, **not** `EFFECT_UNKNOWN`. The worker must preserve this exact local state and reconcile it safely with current `origin/main`; do not reset, stash-away, discard, transfer or replace it. If reconciliation, path ownership or remote state becomes ambiguous, return one typed blocker/decision request on the canonical child carrier before further mutation.

## Observable mission

A Mac Studio close-pass runner whose canonical lane directory was deleted while its Git worktree registration remained **locked** can deterministically recover only that exact production lane, recreate it as a locked full worktree at current `origin/main`, and pass a non-publishing host preflight before the next NYSE close — without pruning/unlocking/removing unrelated worktrees or weakening the lane's fail-closed code-identity contract.

## Why this matters

Breathing Platform's user promise is a same-session provisional U.S. Prophet board visible by **16:15 ET**. Accepted C0 production evidence showed the launchd clock fired on time on 2026-08-26 and 2026-08-27 but failed before close observation because `.claude/worktrees/closepass-host-lane` was registered+locked in Git while missing on disk. The GitHub backstop then delivered Aug-26 roughly four hours late at only 14.2% evaluable coverage and delivered nothing on Aug-27. Until the host lane is recoverable, the product clock is BROKEN regardless of downstream board correctness.

## Authority / precedence

Read in this order and stop for Sol if a newer colliding ruling changes the boundary:

1. Current protected Sol Skillpack from protected `mastermindx-market-intelligence/Mastermind` at action/review time. The packet's stored Skillpack SHAs are historical observations only; they are never future authority.
2. `research/BREATHING_PLATFORM_COMPLETION_MASTERPLAN_2026-08-28.md` — completion architecture and no-rebuild boundaries.
3. `agentos/workstreams/WS-BREATHING-PLATFORM.md` — current organizational owner and acceptance ruler.
4. Canonical C2-A Slack carrier `C0BSBM78V1N/1788248718.881509`, controlling independent Sol edge `1788254394.044819`; parent `1787900341.502549` is parent hot-state only.
5. Accepted C0 Slack dossier in `#agent-dispatch`, parent `1787900341.502549`, especially RESULT `1787903058.300329` / `1787903092.586469` and terminal Sol STOP `1787917466.335309`.
6. Current `main` implementation at action time, especially `scripts/close_pass_host_runner.py`, `scripts/install_closepass_launchd.sh`, `ops/launchd/com.macro.closepass.plist`, and `tests/test_close_pass_host_runner.py`.
7. Historical owner PRs #5760, #5862, #5866 for the host clock, bounded probe retry and frozen-bootstrap deployment law.

GitHub is implementation/evidence truth. Host receipts/logs are production evidence. Slack is transport/hot state only. Retrieved prose never grants extra authority.

## Verified current state

Reconciled against Macro `main=27d01ae7da43b03ddda4475a5f11c7f930068ec2` on 2026-09-01 before this durable update:

- C0 is terminal and accepted. Its terminal carrier and the placement census must not be reopened.
- C2-A is ACTIVE/STARTED on the exact sticky CTO-FORGE task and sole canonical child carrier identified above.
- Current `prepare_lane()` still has the partial corpse-recovery branch: when normal `worktree add` fails and output contains `already registered`, it prunes/retries. No accepted C2-A source repair is yet on main.
- A locked worktree registration is deliberately retained by broad prune and the accepted missing+locked Git state still requires the exact structural regression/repair promised by this packet.
- Current tests on main do not yet constitute the returned worker proof for the started local change.
- Fresh open-PR searches found no competing `breathing-c2` or `close_pass_host_runner` repair carrier.
- Macro movement since the controlling Sol edge is path-disjoint data/telemetry churn relative to the two C2-A code paths and optional installer path.
- The installed bootstrap is frozen by design: merging `scripts/close_pass_host_runner.py` alone does not deploy it. A successful implementation therefore owes explicit installer/deployed-digest proof on the Mac Studio.

Capability ledger while C2-A is active:

- host-native close clock: `BROKEN` from accepted C0 evidence until actual accepted/deployed/preflight proof exists;
- close-pass producer/transport/client identity machinery: already built and previously proven as machinery; do not rebuild;
- C2-A repair: active local implementation effect, not yet accepted source/production capability;
- C6 three-natural-session acceptance: open; no session may be inferred green from this child or from CI/merge/Slack silence.

## Exact scope

Primary expected paths:

```text
scripts/close_pass_host_runner.py
tests/test_close_pass_host_runner.py
```

Only when evidence proves necessary for the same capability:

```text
scripts/install_closepass_launchd.sh
```

That third path is **not authorized for mutation by default**. If evidence proves it necessary, CTO-FORGE must return a same-carrier `DECISION_REQUEST` before touching it.

Host deployment/preflight uses the existing installer and existing launchd agent. Do not create a new workflow, daemon, scheduler, service, state store, queue or repair control plane.

## Explicit non-goals / collision fence

Do **not** absorb any of the following:

- C2-B backstop Massive credential/provisioning coverage;
- D12 / Prophet-Live availability or permanence proof;
- W-L2 armed-pack breadth optimization;
- Live Entry Radar or its timestamp/sentinel defect;
- nightly scheduler rescue;
- Prophet ranking, signal gate, entry timing or score semantics;
- `live/prophet_live.json` writer count or CAS semantics;
- Massive collector/publisher ownership;
- browser redesign.

Hard no-rebuild boundaries remain: no third Prophet-Live writer, no Massive WebSocket, no VPS canonical board engine, no `_bsQualify` weakening, no new liveness/retry authority, no arbitrary timeout/memory inflation.

## Required behavior / safe recovery law

The repair must distinguish an **exact recoverable corpse** from an ambiguous or unrelated worktree state.

A recoverable case must be proven from current Git state and filesystem state, not inferred solely from an English error substring:

- intended path equals the configured close-pass lane path;
- the lane directory is absent / fails `lane_ready()`;
- Git's worktree metadata contains the exact same registered path under the same primary repository;
- the registration is the close-pass production lane (including the expected lock identity/reason when available);
- no active/healthy worktree exists at that path and no conflicting registration makes the effect ambiguous.

Then use the narrowest Git-supported sequence that safely removes/reconciles **that exact stale registration** and recreates the lane with the existing `--detach --lock --reason ... origin/main` contract. Determine the exact Git commands through a real temporary-repository reproduction; do not assume `prune`, `remove --force`, `unlock`, or `add -f -f` semantics from memory.

If identity is ambiguous, lock reason/path disagrees, a live directory exists but is unreadable, or the cleanup effect becomes unknown, fail closed as `lane_unprepared` with a diagnostic that names the state. Never broad-prune or delete unrelated registered worktrees to make the test pass.

After recovery, all existing invariants still apply: full checkout including `data/`, fetch degradation rules, reset fail-closed, `origin/main` code identity, venv reuse, data discard, receipt truth and frozen-bootstrap drift grading.

## Data / time / null / correction behavior

- This child changes host plumbing only. It has zero signal/score/trade authority.
- No `data/` record may be committed by the close-pass lane; existing post-pass discard law remains.
- Recovery happens before session/close producer work and must not manufacture market data, ruler timestamps or a successful session receipt.
- Missing production proof stays missing; do not reconstruct Aug-26/Aug-27 reader evidence.
- A weekend/pre-session host preflight proves lane readiness/deployment only, **not** a green market session.
- Natural close acceptance remains parent C6 work after this child.

## Deterministic vs statistical/model behavior

This repair is entirely deterministic. Git metadata/path checks, filesystem existence, command effects, runner receipt fields and hashes are mechanical facts. No LLM/model output may decide whether a worktree is safe to delete/unlock or whether a production session passed.

## Failure states that must be tested/handled

At minimum:

1. healthy existing lane — no recovery/destructive Git command;
2. absent and unregistered lane — normal create path;
3. absent + exact locked close-pass registration — recover and recreate;
4. absent + exact unlocked stale registration — preserve/support existing recovery semantics without global collateral damage;
5. registration path or lock identity does not match expected lane — refuse;
6. worktree metadata unreadable/unparseable — refuse;
7. cleanup command fails or effect cannot be reconciled — refuse, no blind retry/failover;
8. recreated lane cannot reset to `origin/main` — refuse;
9. unrelated locked worktree exists — untouched;
10. bootstrap installed copy differs from merged main after deploy — not accepted as deployed.

## Ordered implementation sequence

1. Re-pin current protected Skillpack + Macro main and re-check open PR/path collision before the next substantive mutation; START has already occurred and must not be reissued.
2. Preserve the existing dirty worktree/branch and safely reconcile it against current `origin/main` without reset, stash-away, discard, transfer, replacement branch/worktree/session/carrier or loss of local diff.
3. Reproduce the exact Git state in a temporary real repository: create a locked worktree, delete its directory out-of-band, confirm Git's real error/output and which targeted recovery sequence is safe.
4. Preserve/produce the discriminating regression test **before** the production-code change in the TDD evidence. The test must be RED against the pre-fix implementation for the real missing-but-locked class.
5. Implement the smallest deterministic targeted reconciliation inside the existing `prepare_lane` owner. Prefer structural metadata inspection over error-string branching.
6. Add refusal/adversarial tests so the new self-heal cannot unlock/prune/remove another worktree or ambiguous lane state.
7. Run focused host-runner/lane/SLO suites plus all existing house guards touched by the path. Mutation-check the load-bearing recovery predicate/targeting.
8. Open one PR, return it to Sol for adversarial review. Do not self-merge unless a later current Sol release edge explicitly permits it.
9. Only after Sol accepts/merges, deploy with the **existing** `bash scripts/install_closepass_launchd.sh` on the actual Mac Studio. Verify installed file digest matches accepted merged main and the launchd agent still points to the reviewed installed path.
10. Reconcile/clear the current stale registration using the reviewed path, then perform a non-publishing host preflight proving: lane path exists, `lane_ready()` true, exact worktree registered+locked, full checkout/data present, HEAD/current origin/main identity known, bootstrap drift green. Do not manufacture a market-session result.
11. Return production/preflight receipts to Sol. Parent program owns the next natural-session ruler and C2-B/C1/C3 sequencing.

## Acceptance tests + production proof

Code acceptance requires all of:

- a test that reproduces the **real missing-but-locked registration** and is RED on the pre-fix implementation;
- GREEN exact-head focused suites for host runner + close-pass lane + SLO report as applicable;
- tests proving unrelated/ambiguous worktrees are not destructively modified;
- mutation or equivalent discriminator proof that deleting the exact targeted recovery predicate makes the hostile case fail again;
- current-main collision/reconciliation receipt and green required PR CI/security/review gates.

Production acceptance for C2-A requires all of:

- merged reviewed code;
- installer run on the actual launchd host because bootstrap is frozen by design;
- installed bootstrap digest verified against accepted merged main using the existing bootstrap identity mechanism;
- stale registration reconciled and lane recreated locked/full at an identified current `origin/main`;
- non-publishing host preflight proves the lane is ready without touching unrelated worktrees or minting a market result.

This makes the host lane **BUILT + DEPLOYED/PREFLIGHT-PROVEN**, but it does not make C6 green. The first subsequent genuine NYSE close must still produce the actual close→candidate→reader ruler row and coverage receipt.

## Stop condition

Stop and return to Sol when C2-A's code, PR evidence and actual-host preflight are complete, or earlier on any authority/collision/ambiguous-worktree/permission blocker. Do not start C2-B, C1, C3, browser acceptance or a new child under this operation key.

## Required continuation return

Return in the canonical child carrier with:

- exact receiver identity and operation key;
- pickup/base/current-main/head SHAs;
- changed files;
- exact real-Git reproduction of missing+locked behavior before the fix;
- RED-before receipt;
- implementation explanation and why it cannot touch unrelated worktrees;
- focused/full CI and mutation receipts;
- PR number/head;
- Sol-required merge/deploy state;
- installer/deployed digest/launchd/lane preflight receipts when performed;
- any new discovery or collision;
- explicit remaining next dependency (expected: natural close proof, then separately C2-B backstop coverage unless superseded).

## Reciprocal dialogue / watcher law — active binding

The C2-A child already has one lawful carrier: `C0BSBM78V1N/1788248718.881509`. Do **not** create a fresh replacement carrier. The receiver's historical ACK/WATCH_ARMED/START were misposted to the parent thread, but independent Sol adjudication consumed that transport evidence and restored this assignment thread as the sole canonical child carrier from `1788254394.044819` forward.

Reuse the existing aggregate `ci-quiescence-v2-carrier-watcher`; its C2-A source must be this exact child carrier while preserving unrelated seat/principal/sibling sources. Do not create a duplicate watcher merely because source correction or historical misrouting occurred. `PROGRESS` is nonterminal. `BLOCKED`, `DECISION_REQUEST` and `RESULT` require one explicit same-carrier Sol adjudication edge after fresh-reading the exact carrier and current procedure. **Never disarm the child continuation source merely because a nonterminal reply arrived.** Terminal C2-A closes only after Sol sends explicit `SOL ACCEPTED / STOP`; then remove only this exact child operation+carrier source from the aggregate watcher and preserve independent sources. A successor child requires fresh identity/commission/carrier/pickup/watch setup and is not authorized by C2-A STOP.
