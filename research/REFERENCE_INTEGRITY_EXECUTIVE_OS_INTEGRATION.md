# Reference Integrity Gate ↔ Executive OS — integration contract

**Status:** Contract only. No runtime integration ships with RIG V1, because no canonical
review-job dispatch/state mechanism exists on the merged main of either repo (census below).
The governance layer lands before runtime automation; this document is the exact contract a
future runtime must satisfy, so integration is a wiring exercise, not a design exercise.
**Companion:** `research/REFERENCE_INTEGRITY_GATE_V1.md` (the law being integrated).

---

## §1 Census verdict — why this is a contract and not an implementation

Inspected 2026-08-12 (Macro `origin/main`; Mastermind `master`):

1. **Mastermind `control_plane/` is validation/gating, not dispatch.** `packet_gate.py` /
   `decision_packet.py` gate trading-book DecisionPackets; `governance.py` is an append-only
   authority-change audit ledger (`governance.jsonl`: `flag_changed`, `doctrine_changed`);
   `run_ledger.py`/`run_events.py` bracket cron-job runs. Nothing implements
   artifact-ready states, reviewer-role dispatch, or verdict-gated transitions.
2. **The Executive OS strategic-state work is not on Mastermind `master`**
   (`config/strategic_state.yml`, `control_plane/strategic_state.py`, and the AGENTS/CLAUDE
   "Executive contract" exist only on unmerged branches/worktrees — verified by
   merge-base ancestry). Macro-side documents citing them are merged prose, not reachable
   runtime. An integration must not assume they are live.
3. **Even once merged, the strategic state forbids this coupling.** Its bootstrap contract
   §4 declares the state advisory/orientation-only: it may describe and label work, never
   decide whether work runs or grant authority — a dispatcher reading it becomes the
   prohibited second scheduler. RIG must not hang review dispatch off `strategic_state.yml`.
4. **The nearest structural analog is off-limits.** Metabolism's
   AGENDA→PROPOSE→ADJUDICATE→BUILD→AUDIT loop is dormant (`AUTONOMY_PAUSED=true`) and
   ABSORB-classified — Phase 0 census §6.2 forbids restarting or perpetuating it as a second
   work-dispatch system.
5. **Standing prohibitions bind any future runtime:** no second control plane (census §6.1),
   no new schedulers/queues/buses (§6.4), no auto-arming authority (§6.6),
   `duplicate_control_planes` (strategic-state standing constraint).

Conclusion: RIG V1 operates **session-driven** — a commissioning session dispatches the two
critics per the model-routing law, the design authority issues the verdict, CI enforces the
receipts. The committed artifact set IS the state store; there is deliberately no second one.

## §2 The state machine (already live as committed artifacts)

```
design_work
    ↓  (proposal committed; manifest status: draft)
artifact_ready
    ↓  (manifest status: in_review; frozen_sha pinned)
reference_integrity_review
    ├─ product_regression_critic   → reviews/product_regression.yml
    └─ visual_taste_critic         → reviews/visual_taste.yml
    ↓  (both receipts frozen, two-pass complete)
design_authority_verdict           → verdict.yml
    ↓
reference_approved                 → approval.yml; manifest status: approved
    ↓                                (else: revise | rejected)
migration_allowed                  (factory packets may now cite RIG-RECEIPT)
```

State field: `research/reference_integrity/<id>/manifest.yml: status`
(`draft | in_review | approved | revise | rejected | superseded`). Transitions are commits;
CI (`scripts/check_reference_integrity.py`) refuses illegal states (an `approved` without
receipts/verdict/complete artifact set cannot merge). A future runtime changes **who
performs** the transitions, never the store, the schema, or the gate.

## §3 Required events (future runtime)

Follow the existing governance-ledger event shape (`event_type, target, actor, reason,
before, after` appended to a ledger) — the Phase 0 census's own recommendation is adding
event types to `governance.jsonl`, not building a new store. Minimum event set:

| event_type | target | fired when | after |
|---|---|---|---|
| `reference_review_requested` | reference_id | manifest enters `in_review` with pinned `frozen_sha` | reviewer roles owed |
| `reference_review_receipt` | reference_id + role | a critic receipt lands (per pass: first_pass frozen / second_pass amended) | receipt path + verdict |
| `reference_verdict` | reference_id | design-authority verdict committed | verdict enum + unresolved-blocker count |
| `reference_approved` / `reference_rejected` / `reference_revise` | reference_id | terminal status commit | approval receipt path (approve only) |

## §4 Reviewer contract (inputs/outputs — identical for human, session, or runtime dispatch)

**Inputs, first pass (rationale-quarantined; the runtime MUST be able to withhold the
rationale):** user/business job · production-before artifact (baseline evidence paths) ·
proposed-after artifact (frozen files) · capability ledger + user-task matrix
(`baseline.yml`, `proposal.yml` minus any rationale fields). **Inputs, second pass:** the
designer rationale, constraints, data limitations. **Outputs:** one
`mastermind.rig_review.v1` receipt per role — verdict `PASS | PASS_WITH_CONDITIONS | BLOCK`,
findings with stable ids + severities, two-pass record with quarantine attestation.
**Role routing:** independent Opus `reviewer`-class seats (factory §1 red-team role;
capability-manifest seat labels are the natural home for naming these seats). Neither
reviewer may be the author; the runtime must carry distinct identities into the receipts.

## §5 Blocking conditions (the runtime must not be able to bypass)

Approval is illegal while any of: a blocker-severity critic finding lacks a verdict
resolution (`upheld_revise | resolved_by_change | overridden`+justification) · a
`critical: true` user task is `WORSE` unadjudicated · any capability disposition is missing
or malformed (incl. data-motivated `REMOVE`) · receipts' `artifact_sha` ≠ proposal
`frozen_sha` · reviewer identity collides with author. These are exactly checker rules
L1–L9 — the runtime inherits them by construction because CI runs on every commit path; a
runtime that "approves" without satisfying them produces an unmergeable commit, not an
approved reference.

## §6 CEO / design-authority verdict schema

`mastermind.rig_verdict.v1` (`verdict.yml`): the eight forced comparative answers (improved /
worsened / disappeared / harder / stronger-claims / intent-vs-convenience /
production-preferable / **strongest argument against**), per-blocker resolutions, overrides
citing finding ids (permanent record), verdict enum
`APPROVE_REFERENCE | APPROVE_WITH_CONDITIONS | REVISE | REJECT`, preserved strengths,
conditions. A future `submit_executive_packet`-style CEO write surface (census §5 item 10)
may **carry** this packet, but the packet schema is owned here and does not change shape in
transit.

## §7 Authority

The verdict-gates-state step cites `config/authority_map.yml`'s A0–A7 ladder when the
Executive contract merges: issuing `APPROVE_REFERENCE` is a design-authority act (factory §1
design-authority role; Fable main loop / CEO-designated authority), never a builder or critic
act, and never auto-armed. RIG mints no new authority concept and no second ladder.

## §8 Exact future integration points discovered (and the non-couplings)

**Couple here when live:** governance-ledger event append (§3) · capability-manifest seat
labels for the two critic roles (§4) · `submit_executive_packet` as verdict transport (§6) ·
authority-map citation (§7).
**Never couple:** `config/strategic_state.yml` (advisory-only by its own §4) · Metabolism's
ADJUDICATE loop (dormant, ABSORB-classified) · any new scheduler/queue/state store
(prohibited; the committed artifact set is the only store).

Nothing further ships until the Executive OS exposes the §3 ledger on a merged main; at that
point integration is: emit four event types at the existing transition commits.
