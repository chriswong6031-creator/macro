---
workstream: "WS:CROSS-REPO-CONTRACT-GOVERNANCE"
session: sol/crg-r0-recovery-20260829
model: sol
ended_because: complete
mission: >
  Recover the stalled CRG R0 release gate, make the accepted records-only architecture
  durable on Macro main, reconcile the false Agent OS awaiting-CI projection, and leave
  the exact principal-placement continuation recoverable without claiming worker execution.
state_before: >
  PR #6596 had exact-head green CI and a prior Sol PASS but remained Draft because the
  connected GitHub mark-ready mutation failed on a GraphQL response-schema defect. No
  Fable principal ACK/START/Worker claim existed. Agent OS still described R0 as awaiting_ci.
changed:
  - path: agentos/workstreams/WS-CROSS-REPO-CONTRACT-GOVERNANCE.md
    what: >
      Mark R0 complete at accepted merge 2a45075ddb1139d3bcab6c6402f483040e0f6378,
      preserve that R0 repaired zero production seams, and advance the exact next action to
      lawful Fable principal placement before CRG-NW-AUTHORITY-V1.
verified:
  - claim: "R0 exact carrier was accepted and merged."
    command: "GitHub PR #6596 exact-head release review + expected-head squash merge."
    result: >
      PASS — accepted head 3aa76becc43a4fab7599e5f8e377979f81622beb; fences/ci,
      contract-delta, both trusted executor packs and ci-gate green; merge SHA
      2a45075ddb1139d3bcab6c6402f483040e0f6378 is current Macro main immediately after merge.
  - claim: "The Draft-only administrative blocker was cleared without repository mutation."
    command: "Grok Secretary bounded UI child crg-r0-draft-ready-ui-unblock-20260829-sol-001 plus canonical GitHub reread."
    result: >
      PASS — one Ready-for-review transition only; canonical GitHub confirmed draft=false,
      merged=false and unchanged head before Sol merge. Grok child received terminal SOL ACCEPTED / STOP.
  - claim: "R0 architecture remained current enough to merge after the recovery delay."
    command: "Fresh three-repository source-law spot checks before release."
    result: >
      PASS — Macro engine/neuralweb/mastermind_context.py still states all five Portfolio
      authority booleans FALSE/context-only; current Portfolio brain/neural_web_context.py
      still defaults prompt context ON and decision mode to shrink while config/authority_map.yml
      describes MASTERMIND_NW_DECISION as default-off/dark. Terminal moved only through unrelated
      China OHLC ownership work since the R0 census pin. CRG-01 therefore remains genuinely BROKEN.
  - claim: "No CRG principal was already executing."
    command: "Slack exact-operation search for crg-fable-principal-20260828-sol-001."
    result: "PASS — no prior Slack carrier/ACK/START/RESULT found for the principal operation."
unverified:
  - claim: "A concrete eligible Fable receiver is currently available."
    what_would_verify: >
      Live provider/session placement evidence yielding one unambiguous eligible receiver,
      followed by deliberate lawful delivery and that receiver's ACK/readback; until then the
      principal operation is UNCLAIMED / WAITING_CAPACITY.
  - claim: "CRG-01 is repaired."
    what_would_verify: >
      A separately commissioned CRG-NW-AUTHORITY-V1 child, accepted code/contracts/conformance
      on exact heads, and required real producer-consumer proof. R0 merge proves none of this.
unresolved:
  - >-
    The canonical Executive worker route remains production_armed=false, so no Executive Job/Worker
    claim may be invented for CRG principal placement.
  - >-
    Live Fable placement is being reconciled separately; do not ask the Chairman to allocate a routine
    numbered account when no automated placement owner can currently do so.
  - >-
    CRG-02 imported Macro generation identity, CRG-03 reverse publication ownership, Prophet proof,
    Terminal washout authority, older Terminal formal contract gaps and the final production dossier
    remain open after CRG-01 in the bounded wave order.
next_actions:
  - >-
    Sol: complete live Fable placement reconciliation for crg-fable-principal-20260828-sol-001.
    If exactly one eligible concrete session is lawfully identified, deliberately deliver the existing
    principal handoff, require ACK/read/watch/START, and keep Slack delivery distinct from execution.
  - >-
    After actual principal claim, perform a fresh collision census and commission only
    CRG-NW-AUTHORITY-V1 as the first R1 implementation child.
  - >-
    Sol reviews every principal/child BLOCKED, DECISION_REQUEST and RESULT on the same lawful carrier
    and issues exactly one explicit CONTINUE/REPAIR/STOP edge; never leave the program idle after a return.
do_not_redo:
  - "Do not recreate R0, the semantic program, or the Agent OS workstream."
  - "Do not create a central Contract Governance runtime, gateway, queue, scheduler, registry or release gate."
  - "Do not rebuild portfolio/prophet_feed.py; its remaining problem is contract/proof, not absence."
  - "Do not treat Direct Terminal -> Portfolio as a missing feature; it remains REJECTED_BY_DESIGN."
  - "Do not call R0 merge production seam completion."
---

# CRG R0 closeout

Before this recovery, the accepted R0 carrier existed but was stuck behind a Draft-only GitHub UI gate,
and Agent OS could not truthfully say that the durable CRG execution home had landed. After this recovery,
R0 is durable on Macro main at `2a45075ddb1139d3bcab6c6402f483040e0f6378` and the organizational
continuation can move to actual principal placement. This is a records-only capability delta: it makes
CRG recoverable and governed across sessions, but repairs zero production seams.
