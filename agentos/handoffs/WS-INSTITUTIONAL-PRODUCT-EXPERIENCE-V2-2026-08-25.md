---
workstream: "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2"
session: sol-continuation-replay-prevention-79ea20
model: fable
ended_because: complete
mission: >
  Records-only reconciliation of the XPV2 organizational layer to merged #6337
  (C2' of the Sol Continuation Delta ruling, 2026-08-25): recognize the completed
  R3B/R3B.1/R3B.2 cycle as completed, remove the stale executable next_action,
  protect settled work behind do_not_redo, and hold the five R3C-owned conditions
  non-executable. This handoff SUPERSEDES the 2026-08-21 handoff as the active
  continuation layer; the 08-21 file is preserved untouched as provenance.
state_before: >
  The workstream still recorded R3B.2 in_progress at pre-merge head 90ce21ac
  with a next_action telling Sol to resolve F1/F2 and issue the final verdict —
  all of which had already completed inside merged #6337
  (8b303a58e8c0b807ef34d1913c4cacf5bb346e2d, 2026-08-24T22:56:54-04:00,
  APPROVE_WITH_CONDITIONS). The latest handoff (2026-08-21) still instructed
  dispatching R3B_HANDOFF_DRAFT.md. This was the canonical continuation-replay
  incident: a fresh Sol following the organizational layer alone could lawfully
  resurrect completed work — even though part of that layer (#6388) had been
  correctly repaired only hours before the carrier completed.
changed:
  - path: agentos/workstreams/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2.md
    what: >
      status active→done; wave R3B.2 in_progress→done with merge/approval receipts
      (merge 8b303a58e8c0, final head f400e8b4df4d, verdict APPROVE_WITH_CONDITIONS,
      five R3C-owned conditions, MA2-001 refuted); stale F1/F2 next_action replaced
      with a non-executable hold that routes any successor wave through an explicit
      Chairman/Sol authorization; workstream-level do_not_redo added; body
      reconciled to merged truth (F2 lineage settled; #6336 closed unmerged).
  - path: agentos/handoffs/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2-2026-08-25.md
    what: this superseding handoff (the 2026-08-21 handoff is preserved, not edited).
verified:
  - claim: "#6337 is merged with the Sol APPROVE_WITH_CONDITIONS records"
    command: "git log -1 --format='%H %s %ci' 8b303a58e8c0b807ef34d1913c4cacf5bb346e2d && git merge-base --is-ancestor 8b303a58e8c0b807ef34d1913c4cacf5bb346e2d origin/main"
    result: "records(xpv2): Sol APPROVE_WITH_CONDITIONS for mastermind-xpv2-sector-r3b-2 (#6337), 2026-08-24 22:56:54 -0400; IS ancestor of origin/main"
  - claim: "verdict.yml + approval.yml exist in the merged r3b-2 pack"
    command: "git ls-tree -r --name-only 8b303a58e8c0 research/reference_integrity/mastermind-xpv2-sector-r3b-2/ | grep -E 'approval|verdict'"
    result: "approval.yml and verdict.yml present"
  - claim: "the pre-repair workstream state this record replaces was the stale one"
    command: "git show 4faf00a44510:agentos/workstreams/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2.md | grep -n 'in_progress\\|90ce21ac'"
    result: "R3B.2 in_progress at head 90ce21ac977209370b57b2ef1af7331cebb25861 — repaired by #6388, then made stale again by the #6337 merge"
  - claim: "Agent OS record set validates"
    command: "python3 scripts/agentos.py validate"
    result: "exit 0"
unverified: []
unresolved:
  - "The five carried conditions (R3C-HEATMAP-LEGIBILITY, R3C-AUTH-PREMIUM, R3C-TIME-MACHINE, R3C-VALIDATED-21D, R3C-NO-UNSUPPORTED-INVENTION) are R3C-owned and remain deliberately unexecuted; they become an acceptance floor only inside an explicitly authorized future R3C commission."
next_actions:
  - "None executable for XPV2. If the Chairman/Sol authorizes a successor wave, commission it fresh via COMMISSION_WAVE as CONTINUATION_DELTA against merged #6337 (pickup 8b303a58e8c0b807ef34d1913c4cacf5bb346e2d), reconciling this handoff's do_not_redo first."
do_not_redo:
  - "Do not redispatch R3B or R3B_HANDOFF_DRAFT.md — the R3B reference cycle completed as merge f5b0094614b688e8b66552e35ac65d23656fbc64 and was superseded by R3B.1/R3B.2."
  - "Do not redo R3B.1 — the successor correction completed as merge 780cbcf6d2d2c7b32b87a4674929e1732e5ad036 and its verdict lineage was finally ratified via the #6337 F2 ruling."
  - "Do not redo the #6388 workstream reconciliation (merge 4faf00a44510a41f968a272a6fae5d8acb7890be) — repaired-then-superseded state is repaired forward, never replayed."
  - "Do not redo F1/F2 — both closed inside merged #6337 (F1 top-level artifact_sha mirror; F2 branch-side R3B.1 verdict ratified)."
  - "Do not rerun the four final R3B.2 critics absent a named receipt-invalidating event — their receipts are durable under research/reference_integrity/mastermind-xpv2-sector-r3b-2/reviews/."
  - "Do not redo or re-litigate the #6337 approval/merge — Sol ruled APPROVE_WITH_CONDITIONS; merge 8b303a58e8c0b807ef34d1913c4cacf5bb346e2d is canonical."
  - "Do not start R3C or treat the five carried R3C-owned conditions as open executable work — R3C implementation is explicitly not authorized."
  - "Re-derive the six-lane archaeology — the dossiers are production-cited and adversarially reviewed; extend, don't re-census. (carried forward from 2026-08-21)"
  - "Treat the R2 candidate HTML as source authority (authority precedence is frozen in the pack README). (carried forward from 2026-08-21)"
  - "Bind Moving to si_handoff.json — ADJUDICATIONS §A2 REFUTED that handoff premise; Moving binds five nightly artifacts, Money binds si_handoff. (carried forward from 2026-08-21)"
  - "Repair the production seams recorded in A3/A6/A7 inside an XPV2 wave — they are filed as separate chips. (carried forward from 2026-08-21)"
danger_areas:
  - "The r3b-2 pack (fixture, receipts, reviews/, verdict.yml, approval.yml) is FROZEN merged evidence — any regeneration re-times receipts; provenance may be added, values never recomputed."
  - "The attack suite must never assert on live site//data/ (nightly rewrites them; merge gate must not ride moving data — A10)."
  - "The 2026-08-21 handoff and pre-#6337 record revisions are historical provenance: superseded, never rewritten or deleted — rewriting history to hide a stale record destroys the incident evidence the Continuation Delta corpus pins."
  - "RIG rule_l5 reads artifact_sha at TOP level only — nested under identity: reads '<missing>', green at in_review, red at approved (the F1 lesson)."
prs: [6337, 6388]
---

# Session handoff — XPV2 organizational closure onto merged #6337 (2026-08-25)

Cold-stranger summary: XPV2's declared objective is complete. #6337 merged with Sol's
APPROVE_WITH_CONDITIONS — reference law only. Nothing in this workstream is executable.
Five conditions exist and are R3C-owned; R3C is not authorized. Any future continuation
must be derived as a delta against merged #6337 after reconciling the do_not_redo list
above — never copied from any earlier commission, including the ones that built this
program. The 2026-08-21 handoff remains on disk as history; this file is the active
continuation layer.

This closure is itself the founding regression fixture of the Continuation Delta
program: the Mastermind Skillpack PR pins this exact stale-state shape RED forever
(tests/incident_replays/fixtures/2026-08-25-xpv2-continuation-replay/) and this
handoff's do_not_redo statements are statement-identical to that fixture's context
bundle.
