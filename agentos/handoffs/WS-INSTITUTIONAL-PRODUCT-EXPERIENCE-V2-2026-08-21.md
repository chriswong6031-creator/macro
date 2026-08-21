---
workstream: "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2"
session: "claude/xpv2-sc-r3a-binding-pack (worktree archaeology-fixture-distribution-f6f63a)"
model: fable
ended_because: complete
mission: >
  Execute the XPV2-SC-R3A operator handoff: build the complete source-of-truth and
  capability substrate for the Sector Central (US) R3 reference — six archaeology
  sub-lanes (A–F), capability disposition ledger, producer binding matrix, frozen
  fixture with SHA-256 receipts, routing contract, access/hydration contract, R3
  design brief, attack tests — production impact none, stopping before any new
  Sector Central visual reference.
state_before: >
  Turn-3 R2 mockups existed as frozen BLOCK-verdict evidence
  (research/reference_integrity/mastermind-xpv2-turn3-r2/); no binding pack, no
  WS record, no fixture, no attack tests. The operator handoff arrived as a
  downloaded markdown file naming a workstream key that did not yet exist in agentos.
changed:
  - path: research/reference_integrity/mastermind-xpv2-sector-r3/
    what: >
      Entire R3A binding pack (PR #6122, merged f4305a4485f6): six lane dossiers
      under archaeology/, ADJUDICATIONS.md (A1–A10 frozen rulings),
      capability_disposition_ledger.md (92 rows: 90 RETAIN / 2 BLOCKED_DATA),
      producer_binding_matrix.md, fixture/ (18 receipts, byte-identical to source
      artifacts at commit 4c55fe433490), routing_contract.md,
      access_hydration_contract.md, R3_DESIGN_BRIEF.md, R3B_HANDOFF_DRAFT.md,
      README.md.
  - path: tests/test_xpv2_sector_r3_fixture.py
    what: >
      59-test attack/mutation suite over the frozen fixture and code constants
      (never live site//data/ — moving-data law A10), hardened through an opus
      adversarial review (4 BLOCKING + 6 SHOULD-FIX findings fixed with
      mutation-fire proofs).
  - path: .github/ci/legacy-jobs.yml
    what: >
      One step appended to the reference-integrity job (gate:code, unscoped, on
      the merge gate) running the suite; jinja2 added to its install line
      (required by importing split_actnow from scripts/build_sector_central.py).
verified:
  - claim: PR #6122 merged with green proof runs
    command: "gh pr view 6122 --json state,mergedAt,mergeCommit → MERGED 2026-08-20T20:16:40Z f4305a4485f6"
  - claim: suite green on merged bytes
    command: "python3 -m pytest tests/test_xpv2_sector_r3_fixture.py -q → 59 passed"
  - claim: fixture faithful, 18/18 receipts
    command: "python3 - <<sha-recompute over fixture/receipts.json vs git show 4c55fe433490:<source> → all_entries_verified=True, count=18"
  - claim: CI step reachable on every PR
    command: "python3 scripts/run_ci_pack.py --workflow .github/ci/legacy-jobs.yml --pack-index 0 --pack-count 1 --validate-only (reference-integrity selected); python3 scripts/audit_unrun_tests.py → exit 0"
unresolved:
  - "R3B not started (by design — the R3A stop condition forbids it); dispatch decision sits with the commissioning seat."
unverified:
  - "tests/test_si_workspace_shell.py actually pinning LEGACY_ANCHORS (routing_contract.md flags this GAP honestly)"
  - "anonymous HTTP fetchability of Explore/Confluence payloads (inferred from config/site_access.yml, no live curl)"
do_not_redo:
  - "Re-derive the six-lane archaeology — the dossiers are production-cited and adversarially reviewed; extend, don't re-census."
  - "Treat the R2 candidate HTML as source authority (authority precedence is frozen in the pack README)."
  - "Bind Moving to si_handoff.json — ADJUDICATIONS §A2 REFUTED that handoff premise; Moving binds five nightly artifacts, Money binds si_handoff."
  - "Repair the production seams recorded in A3/A6/A7 inside an XPV2 wave — they are filed as separate chips (Map reco tags under context disclaimer; Overview stale-guard fail-open was FIXED separately; #theme-* hashchange seam)."
danger_areas:
  - "fixture/ is FROZEN — any regeneration re-times receipts and breaks 59 tests; provenance metadata may be added, values/order never recomputed."
  - "The attack suite must never assert on live site//data/ (nightly rewrites them; merge gate must not ride moving data — A10)."
  - "The reference-integrity job's earlier steps are a hard gate; a red there darkens the XPV2 step (appended-step-dark shape, recorded as review NOTE N3)."
next_actions:
  - "Review and dispatch R3B_HANDOFF_DRAFT.md (marked DRAFT — DO NOT START) to a fresh design session; R3A's stop condition forbade starting it."
---

# Session handoff — XPV2-SC-R3A binding pack (2026-08-21)

Orchestration shape (worked well, keep): six census lanes fanned out to routed sonnet
scouts in parallel; Fable main loop adjudicated conflicts into ADJUDICATIONS.md; a sonnet
builder assembled deliverables from the frozen rulings; an opus reviewer attacked the pack
(PARTIAL verdict, 4 BLOCKING found, all fixed with mutation-fire proofs before merge).
Routed workers repeatedly stopped on status notes and needed explicit continue-to-packet
nudges — budget for that.

The pack is self-describing: start at
`research/reference_integrity/mastermind-xpv2-sector-r3/README.md`.
