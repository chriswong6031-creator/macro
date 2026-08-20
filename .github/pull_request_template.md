<!--
Mastermind-X tracked-work PR template.

This file is an authoring aid, not execution authority. Replace every placeholder,
delete inapplicable guidance, and link the current canonical records. A PR may not
self-authorize a successor wave.
-->

Workstream: WS:<KEY> | NONE
Linear: MAS-### | NONE
Portfolio-Mode: tracked | maintenance_exception | workstream_creation | architecture_candidate
Wave: <bounded wave ID or maintenance label>
Authority: runtime | records | research | architecture | maintenance | production-proof
Completion: merge-is-done | built-not-proven | production-proof-required | acceptance-required

<!--
Use an exact canonical WS key—never fuzzy-match by title.
Use Workstream: NONE only for a typed maintenance exception, workstream-creation
PR, or unaccepted architecture candidate, and explain why.

`Fixes/Closes MAS-###` is allowed only when Completion is `merge-is-done`.
For every other completion class, use `Refs MAS-###` or the issue URL so merge
cannot erase production, independent-review, natural-time, or CEO acceptance gates.
-->

## Observable mission

<!-- One independently useful user or machine capability. Outcome before mechanism. -->

## Why it matters

<!-- Name the user job, machine/intelligence job, moat, risk, or operating burden removed. -->

## Authority and current-state receipt

<!--
List document precedence and the exact state verified immediately before editing:
- repository default-branch SHA;
- relevant open PRs and live worktree/path owners;
- direct Agent OS workstream/decision/handoff paths;
- current production or machine-consumer state where relevant.

Stop rather than silently combining incompatible authority.
-->

## Exact scope

<!-- Repositories, owned capabilities/paths, contracts, producer and real consumer. -->

## Explicit non-goals

<!-- Name adjacent waves, systems, authority, migration, cleanup, or redesign excluded. -->

## Complete user / machine journey

<!-- Include loading, empty, degraded, error, stale, split-deploy, correction, and permission states where relevant. -->

## Data, identity, time, null, and correction law

<!--
State exact IDs/clocks/as-of semantics, source provenance, rights, immutable/keep-first
behavior, null vs zero, idempotency, replay/backfill law, and correction behavior.
Do not allow model prose to repair missing facts.
-->

## Method and authority boundary

<!-- Distinguish deterministic, statistical, and model-generated work. Name what may not rank, gate, size, execute, or originate truth. -->

## Failure states

<!-- Enumerate typed refusals and fail-closed behavior. A transport/HTTP/CI success is not automatically capability success. -->

## Ordered implementation sequence

1. Refresh current heads, open PRs, worktrees, and canonical records.
2. Freeze discriminating failures/tests before the repair or build.
3. Implement the smallest producer-to-consumer vertical.
4. Run adversarial/mutation and regression proof.
5. Prove the real production or machine-consumer path where owed.
6. Update durable Agent OS decision/discovery/handoff state.
7. Stop at this PR's bounded capability.

## Acceptance tests and real proof

<!--
List exact commands, mutation/adversarial controls, browser breakpoints, production
identity, natural-session/operator receipt, or explicitly state why production proof is
not owed. Green CI alone is not acceptance.
-->

## Stop condition and continuation handoff

<!--
State the exact terminal condition, what remains unauthorized, and the cold-stranger
return required for Sol. Do not begin the next wave in this PR.
-->

## Author checklist

- [ ] Exact `WS:<KEY>` / `MAS-###` / portfolio mode / wave / authority / completion fields are resolved.
- [ ] Current default branch, open PRs, worktrees, and path/semantic collisions were checked before editing.
- [ ] One independently useful capability is delivered; infrastructure names its real consumer.
- [ ] Scope and non-goals preserve the accepted product thesis and no-rebuild boundaries.
- [ ] No duplicate identity, event, state, queue, scheduler, store, auth, transcript, or publication plane was created.
- [ ] Data/source/time/null/correction/rights behavior is explicit and fail-closed.
- [ ] Tests discriminate the intended law; relevant mutations/adversarial attacks were executed.
- [ ] Real production/browser/machine-consumer proof is attached where `Completion` requires it.
- [ ] Merge is not represented as proof or acceptance when another gate remains.
- [ ] Agent OS and Linear projection are reconciled, with one exact lawful next action.
