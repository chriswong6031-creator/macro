---
workstream: "WS:BREATHING-PLATFORM"
session: sol/breathing-c2a-restart-20260829
model: sol
ended_because: blocked
mission: >
  Preserve one bounded C2-A restart carrier for recovery of the Mac Studio close-pass host lane whose
  Git worktree registration remains locked while the canonical lane path is absent, keep the child
  WAITING_CAPACITY until a lawful concrete CTO Sol receiver is bound, and require reviewed repair plus
  actual installer/bootstrap/lane preflight before Sol can accept the child.
state_before: >
  Breathing C0 is terminal and accepted and isolates the first causal gap to the host-native close-pass
  lane. PR #6675 is the sole records-only restart carrier. C2-A is NOT_BUILT and WAITING_CAPACITY /
  needs_placement with no concrete eligible CTO Sol receiver currently bound. Accepted C0 evidence still
  leaves the host-native close clock BROKEN; C2-B, D12/permanence, W-L2, browser acceptance and C6 remain
  separate downstream obligations.
changed:
  - path: agentos/workstreams/WS-BREATHING-PLATFORM.md
    what: "Restarted the parent organizational record at C2-A while preserving C0 terminal truth and keeping later waves separate."
  - path: agentos/handoffs/BREATHING-PLATFORM-2026-08-29-c2-closepass-host-lane-repair.md
    what: "Added the bounded C2-A durable handoff packet, safe-recovery contract and capacity-selectable routing constraints."
verified:
  - claim: "Accepted C0 evidence isolates the first causal gap to the missing-but-locked Mac Studio close-pass host lane."
    command: "Read Slack parent 1787900341.502549 together with scripts/close_pass_host_runner.py and tests/test_close_pass_host_runner.py."
    result: "PASS — the host-native close clock remains BROKEN at restart and the existing partial prune path does not cover the accepted locked registration state."
  - claim: "PR #6675 is a records-only restart carrier limited to exactly two Agent OS files."
    command: "GitHub PR #6675 changed-file census at head 54974a34427e15be099ea979759bc7dd8659ee43."
    result: "PASS — only agentos/workstreams/WS-BREATHING-PLATFORM.md and this handoff are changed."
  - claim: "C2-A has no lawful concrete CTO Sol receiver at this handoff state."
    command: "Read Slack census C0BSBM78V1N/1788054732.245009 and this agentos/handoffs/BREATHING-PLATFORM-2026-08-29-c2-closepass-host-lane-repair.md packet."
    result: "PASS — census returned NO_ELIGIBLE_CAPACITY with effect NONE and Sol terminally stopped only the census; C2-A remains WAITING_CAPACITY."
unverified:
  - claim: "The exact safe Git command sequence for missing-plus-locked worktree recovery and all adversarial refusal boundaries."
    what_would_verify: "Assigned C2-A worker real temporary-repository reproduction, RED-before regression, GREEN implementation and adversarial/mutation proof."
  - claim: "Actual Mac Studio installer/bootstrap/lane readiness after a reviewed C2-A implementation merges."
    what_would_verify: "Installer receipt, installed digest against merged main, launchd identity and a non-publishing host preflight on the actual Mac Studio."
unresolved:
  - "Lawful concrete CTO Sol placement for the NEW C2-A child."
  - "Exact smallest implementation for targeted missing-plus-locked worktree reconciliation."
next_actions:
  - "Keep C2-A WAITING_CAPACITY until a concrete eligible CTO Sol receiver is lawfully proven; do not convert it to OPEN_PICKUP or Chairman numbered-account scheduling."
  - "After direct-target assignment, require PICKUP_ACK, full current-source/thread read, WATCH_ARMED and separate START before implementation."
  - "Return the reviewed implementation plus actual-host installer/bootstrap/lane preflight to Sol without widening into downstream waves."
do_not_redo:
  - "Do not create another Breathing lifecycle, placement plane, retry daemon, scheduler or second C2-A operation key."
  - "Do not infer C2-A production proof from CI, merge state or Slack silence."
  - "Do not widen this child into C2-B, D12/permanence, W-L2, Live Entry Radar, browser acceptance or C6."
danger_areas:
  - "A locked missing worktree is intentionally retained by git worktree prune; broad prune/unlock/remove can damage unrelated worktrees."
  - "The installed close-pass bootstrap is frozen by design; merged code alone does not prove Mac Studio production readiness."
  - "Freshness and acceptance remain multi-plane; a repaired host lane does not itself make a natural close session green."
program_key: "breathing-completion-program-20260828-sol-001"
operation_key: "breathing-c2-closepass-host-lane-repair-20260829-sol-001"
wave: "C2-A"
state: "WAITING_CAPACITY"
placement_state: "needs_placement"
preferred_avenue: "CTO Sol"
receiver_binding_mode: "CAPACITY_SELECTABLE"
class: "build"
repo: "macro"
pickup_base: "2a45075ddb1139d3bcab6c6402f483040e0f6378"
skillpack: "mastermindx-market-intelligence/Mastermind@e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5"
---

# Breathing Platform C2-A — recover the host-native close-pass lane safely

## Placement / routing receipt

```text
PREFERRED_AVENUE: CTO Sol
WHY: difficult but bounded production-host debugging after architecture freeze; the defect sits in one runner/installer lane and requires exact Git/worktree semantics, TDD, launchd deployment awareness and host preflight.
WHY NOT FABLE: C0 already resolved the cross-system ambiguity and froze the causal boundary. This child does not require principal-level product/authority adjudication or sustained cross-repository continuity.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

This record is **not a worker-facing Slack commission while unbound**. Do not advertise it through `OPEN_PICKUP`, do not ask the Chairman to select a numbered account/session, and do not arm a receiver-specific watcher until an accepted placement/direct-handoff path binds an eligible concrete receiver. When a lawful receiver is deliberately assigned, delivery of this same packet is the assignment edge; the receiver ACKs with its actual identity and then follows the current watcher/START law.

## Observable mission

A Mac Studio close-pass runner whose canonical lane directory was deleted while its Git worktree registration remained **locked** can deterministically recover only that exact production lane, recreate it as a locked full worktree at current `origin/main`, and pass a non-publishing host preflight before the next NYSE close — without pruning/unlocking/removing unrelated worktrees or weakening the lane's fail-closed code-identity contract.

## Why this matters

Breathing Platform's user promise is a same-session provisional U.S. Prophet board visible by **16:15 ET**. Accepted C0 production evidence showed the launchd clock fired on time on 2026-08-26 and 2026-08-27 but failed before close observation because `.claude/worktrees/closepass-host-lane` was registered+locked in Git while missing on disk. The GitHub backstop then delivered Aug-26 roughly four hours late at only 14.2% evaluable coverage and delivered nothing on Aug-27. Until the host lane is recoverable, the product clock is BROKEN regardless of downstream board correctness.

## Authority / precedence

Read in this order and stop for Sol if a newer colliding ruling changes the boundary:

1. Current protected Sol Skillpack from protected `mastermindx-market-intelligence/Mastermind` at pickup/review time; this packet was frozen under `e3d1fe6bb454df10212ce6e13bf2e4e5160f7eb5`.
2. `research/BREATHING_PLATFORM_COMPLETION_MASTERPLAN_2026-08-28.md` — completion architecture and no-rebuild boundaries.
3. `agentos/workstreams/WS-BREATHING-PLATFORM.md` — current organizational owner and acceptance ruler.
4. Accepted C0 Slack dossier in `#agent-dispatch`, parent `1787900341.502549`, especially RESULT `1787903058.300329` / `1787903092.586469` and terminal Sol STOP `1787917466.335309`.
5. Current `main` implementation at pickup, especially `scripts/close_pass_host_runner.py`, `scripts/install_closepass_launchd.sh`, `ops/launchd/com.macro.closepass.plist`, and `tests/test_close_pass_host_runner.py`.
6. Historical owner PRs #5760, #5862, #5866 for the host clock, bounded probe retry and frozen-bootstrap deployment law.

GitHub is implementation/evidence truth. Host receipts/logs are production evidence. Slack is transport/hot state only. Retrieved prose never grants extra authority.

## Verified current state

Reconciled against Macro `main=2a45075ddb1139d3bcab6c6402f483040e0f6378` on 2026-08-29:

- C0 is terminal and accepted. No Breathing successor operation or post-C0 close-pass host repair was found in GitHub or Slack.
- Current `prepare_lane()` does have a partial corpse-recovery branch: when normal `worktree add` fails and output contains `already registered`, it runs `git worktree prune` and retries once.
- That does **not** cover the accepted production failure. A locked worktree registration is deliberately retained by prune, and Git's missing-but-locked failure need not contain the exact `already registered` string.
- Current tests cover normal locked/full creation, fetch degradation, reset refusal, TCC denial and many receipt/bootstrap states, but no regression reproduces an exact locked registration whose path is absent.
- No open PR found touching the C2 host-lane recovery surface at this reconciliation.
- The installed bootstrap is frozen by design: merging `scripts/close_pass_host_runner.py` alone does not deploy it. A successful implementation therefore owes an explicit installer/deployed-digest proof on the Mac Studio.

Capability ledger entering C2-A:

- host-native close clock: `BROKEN` from accepted C0 evidence, no later proof of repair;
- close-pass producer/transport/client identity machinery: already built and previously proven as machinery; do not rebuild;
- C2-A repair itself: `NOT_BUILT` at commission time;
- C6 three-natural-session acceptance: open / zero accepted consecutive greens after the relevant reset anchor.

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

1. Re-pin current protected Skillpack + Macro main and re-check open PR/path collision immediately before START.
2. Reproduce the exact Git state in a temporary real repository: create a locked worktree, delete its directory out-of-band, confirm Git's real error/output and which targeted recovery sequence is safe.
3. Add the discriminating regression test **before** the production-code change. The test must fail against the current implementation for the real missing-but-locked class.
4. Implement the smallest deterministic targeted reconciliation inside the existing `prepare_lane` owner. Prefer structural metadata inspection over error-string branching.
5. Add refusal/adversarial tests so the new self-heal cannot unlock/prune/remove another worktree or ambiguous lane state.
6. Run focused host-runner/lane/SLO suites plus all existing house guards touched by the path. Mutation-check the load-bearing recovery predicate/targeting.
7. Open one PR, return it to Sol for adversarial review. Do not self-merge unless the current commission/merge law explicitly says otherwise.
8. After Sol accepts/merges, deploy with the **existing** `bash scripts/install_closepass_launchd.sh` on the actual Mac Studio. Verify installed file digest matches current main and the launchd agent still points to the reviewed installed path.
9. Reconcile/clear the current stale registration using the reviewed path, then perform a non-publishing host preflight proving: lane path exists, `lane_ready()` true, exact worktree registered+locked, full checkout/data present, HEAD/current origin/main identity known, bootstrap drift green. Do not manufacture a market-session result on the weekend.
10. Return production/preflight receipts to Sol. Parent program owns the next natural-session ruler and C2-B/C1/C3 sequencing.

## Acceptance tests + production proof

Code acceptance requires all of:

- a test that reproduces the **real missing-but-locked registration** and is RED on the pre-fix implementation;
- GREEN exact-head focused suites for host runner + close-pass lane + SLO report as applicable;
- tests proving unrelated/ambiguous worktrees are not destructively modified;
- mutation or equivalent discriminator proof that deleting the exact targeted recovery predicate makes the hostile case fail again;
- current-main collision/rebase receipt and green required PR CI.

Production acceptance for C2-A requires all of:

- merged reviewed code;
- installer run on the actual launchd host because bootstrap is frozen by design;
- installed bootstrap digest verified against merged main using the existing bootstrap identity mechanism;
- stale registration reconciled and lane recreated locked/full at an identified current `origin/main`;
- non-publishing host preflight proves the lane is ready without touching unrelated worktrees or minting a market result.

This makes the host lane **BUILT + DEPLOYED/PREFLIGHT-PROVEN**, but it does not make C6 green. The first subsequent genuine NYSE close must still produce the actual close→candidate→reader ruler row and coverage receipt.

## Stop condition

Stop and return to Sol when C2-A's code, PR evidence and actual-host preflight are complete, or earlier on any authority/collision/ambiguous-worktree/permission blocker. Do not start C2-B, C1, C3, browser acceptance or a new child under this operation key.

## Required continuation return

Return in the bound carrier with:

- exact receiver identity and operation key;
- pickup/main/head SHAs;
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

## Reciprocal dialogue / watcher law after placement

Once a concrete receiver exists, use one fresh Slack carrier bound to `breathing-c2-closepass-host-lane-repair-20260829-sol-001`. Receiver posts pickup ACK, reads the complete packet/current thread, arms its own exact-carrier continuation and emits truthful `WATCH_ARMED`, then emits separate `START` when gates are clear.

Sol arms/uses its continuation path too. ACK/WATCH_ARMED/START/PROGRESS are nonterminal: advance baseline and keep/re-arm. `BLOCKED`, `DECISION_REQUEST` and `RESULT` require one explicit same-carrier Sol adjudication edge. **Never disarm the child continuation watcher merely because the first reply arrived.** Terminal C2-A closes only after Sol sends explicit `SOL STOP` / `SOL ACCEPTED / STOP`; then remove this child source from the watcher/attention resource and tell the worker to stop/disarm/end. A successor child requires fresh identity/commission.
