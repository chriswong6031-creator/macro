# Private Repository Cutover Acceptance Plan

**Goal:** Produce one evidence packet that makes the final visibility decision reversible,
bounded, and unsurprising. This plan does not change repository visibility.

**Authority:** Existing GitHub workflows/rulesets, runner policy, CI semantic proof, Agent
OS workstream, private-readiness issue/PR carriers, and Mastermind strategic state remain
the only authority and evidence planes. No duplicate readiness registry is created.
At execution time, #6351/P5 owns the CI route, queue, hosted-minute, and runner evidence;
#6432 owns private-consumer/access migration; the current runner-fleet workstream owns
host receipts. If those carriers are superseded, the packet names the exact successors
rather than silently taking ownership.

## Required gates before requesting the final visibility confirmation

1. **Trusted CI route accepted:** #6505 is merged at an exact current-main descendant and
   P4 has three natural ordinary-PR receipts with semantic parity, clean one-job teardown,
   root-cache isolation, and unchanged render capacity.
2. **Latency accepted:** a named natural-traffic corpus shows ordinary green PR
   final-push-to-gate p95 below 10 minutes and heavy PR p95 below 15–20 minutes, or the
   packet explicitly names the residual exception, its bounded operational impact, owner,
   expiry/reconsideration condition, and rollback. A residual exception is accepted only
   by Sol on the exact P5 carrier and remains subject to the final Chairman visibility
   decision; an open-ended modernization backlog is not a cutover veto.
3. **Queueing accepted:** simultaneous ordinary PR evidence demonstrates queue time and
   tail behavior for the accepted PC slot count. Nominal cores or a one-off three-pack
   canary do not satisfy this gate.
4. **Hosted-minutes accepted:** current usage, private-repository billing behavior, and a
   conservative monthly projection remain below the approved budget with explicit
   headroom. Hosted fallback and trust-plane jobs are included. The packet records the
   approved numeric ceiling and data source rather than inventing a threshold.
5. **Runner capacity accepted:** every admitted runner has exact GitHub identity/status/
   labels, service/PID/root binding, immutable helper hashes, cache permissions, resource
   guard, teardown, and contamination receipts. Render and merge-control routes remain
   independently healthy. The MacBook role is optional native validation, not a substitute
   for missing Linux/x86 capacity.
6. **Private consumers accepted:** every deployment, automation, app installation, bot,
   runner group, webhook, package/data consumer, cross-repo checkout, and human role that
   currently assumes public access has an authenticated private-access proof or an
   explicit rollback/exemption. Evidence from #6367 remains evidence only; use the current
   private-readiness carriers and issue ownership.
7. **Recovery accepted:** a documented rollback restores the prior visibility and repairs
   any access grant without changing CI/render routes. Required break-glass owners and
   native administrator surfaces are known; no credential is stored in the packet.
8. **No moving-head collision:** immediately before the decision, re-pin Macro
   `origin/main`, Mastermind protected procedure revision, rulesets, open private-readiness
   carriers, and all binding checks. A moving authority/workflow/policy head invalidates
   the packet until reconciled.

## Acceptance sequence

- [ ] Assemble the packet from existing receipts; do not rerun terminally accepted broad
  host censuses or M1 soak work.
- [ ] Run one focused consumer/access audit and one focused CI/queue/budget projection.
- [ ] Classify every item `PASS`, `EXPLICITLY_NOT_REQUIRED`, or `BLOCKED` with exact
  evidence. Unknown is blocked, not assumed pass.
- [ ] Obtain adversarial Sol review on the exact current-main packet.
- [ ] Present Chairman with one decision: `PRIVATE_CUTOVER_READY` plus exact rollback, or
  the smallest remaining blocker and its single owner.
- [ ] Only after a separate explicit Chairman confirmation, perform the visibility change
  in the native GitHub administrator surface. Do not bundle it with code merge or runner
  registration.
- [ ] Immediately verify GitHub visibility, authenticated clone/fetch, CI planner and
  executor admission, deployment/automation consumers, required checks, and rollback
  reachability. On any critical access failure, execute the documented visibility rollback
  and preserve diagnostics.

## Terminal verdicts

- `PRIVATE_CUTOVER_READY`: every gate above is exact-head accepted; visibility is still
  unchanged and awaits the one final explicit confirmation.
- `PRIVATE_CUTOVER_COMPLETE`: explicit confirmation was received, visibility changed, and
  the post-change access/CI/deployment verification passed.
- `PRIVATE_CUTOVER_ROLLED_BACK`: the change was attempted, a critical gate failed, and the
  documented prior visibility/access state was restored.
- `BLOCKED`: name the exact failed gate and the single authority or action required.
