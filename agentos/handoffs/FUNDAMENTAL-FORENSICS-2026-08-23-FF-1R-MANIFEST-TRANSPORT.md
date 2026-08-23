---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff1r-manifest-transport-20260823
model: codex
ended_because: ci_handoff
mission: >
  Repair only the FF-1R immutable issuer-manifest transport boundary after the
  first bounded production recovery attempt failed closed before any issuer
  completed, while preserving compact pointers and all frozen recovery state.
state_before: >
  PR #6285 merged the bounded FF-1R engine as
  1e7d9f5030fd7c7c06fb03f022857510c5d0f9ed. Production run 32626273461 /
  run_382b4fbf26bb0fe3e298 selected 64 CIKs at cursor 0 but stopped at its
  first issuer: ANGO's valid 20,779-byte immutable manifest exceeded the
  16,384-byte compact-pointer read ceiling. It made one current Submissions
  request, zero historical Submissions or Company Facts requests, and
  completed no issuer. The run is a fail-closed witness, not a checkpoint.
changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: >
      Keep every compact pointer at 16 KiB; add a measured 128 KiB immutable
      issuer-manifest envelope shared by bounded recovery/incremental reads and
      canonical writes, with typed transport failures, stored identity-era
      compatibility, schema/source/key binding, and one-hop lineage checks.
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: >
      Add public recovery and incremental large-manifest proof, exact-ceiling
      and one-byte-over refusal, ANGO-sized legacy identity, compact-pointer,
      schema/UTF-8/source/key/lineage mutation, bounded writer race/readback,
      cursor-zero, and no-unbounded-read regressions.
  - path: agentos/discoveries/DSC-FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER.md
    what: >
      Record the measured immutable-manifest versus compact-pointer transport
      distinction exposed by the first production witness.
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: >
      Reconcile #6285, the rejected first recovery checkpoint, frozen cursor,
      active P1 repair, and the later-release requirement for a corrective
      tranche-A retry.
  - path: agentos/handoffs/FUNDAMENTAL-FORENSICS-2026-08-23-FF-1R-MANIFEST-TRANSPORT.md
    what: >
      Preserve the exact local, production read-only, scope, and no-dispatch
      receipts for review of PR #6318.
prs: [6285, 6318]
verified:
  - claim: >
      The production immutable-manifest distribution selects 128 KiB under
      Sol's mandated measured-ceiling rule.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17; paginate
      list_objects_v2 for fundamental_forensics/broad-sec/v1/issuers/ and
      select exact issuers/<CIK>/manifests/<sha>.json keys and listing sizes.
    result: >
      4,819 manifests; min 1,197; median 11,410; p90 19,385; p95 22,889;
      p99 33,305; max 43,665; 817 above 16 KiB; 51 above 32 KiB; zero above
      64, 128 or 256 KiB. The smallest power of two at least twice the maximum
      is 131,072 bytes (128 KiB).
  - claim: >
      ANGO evidence, the recovery plan/continuation, and latest-complete were
      unchanged after implementation; only bounded authenticated reads were
      performed.
    command: >
      ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17; use
      R2Store.get_bytes_strict_bounded_versioned for the ANGO issuer pointer,
      recovery continuation and latest-complete, and bounded reads for their
      immutable targets; hash exact bytes and decode receipts locally.
    result: >
      ANGO manifest remains 20,779 bytes with byte sha256
      9c0118c7f10e14eb42a3cd2f108e71938b91275fbeefed2f9f2f1eb691f6ae26,
      ID 6cf86c4b77fe25dbae9a82cece41dd0d8917ecd428cc6eda0d562859e8f1fa9d,
      68 relevant/68 cumulative accessions, null predecessor, and pointer
      sha256 24540172d3d60fd3d076ff431a438ab48e2941973251a17f976f6c2dbb217a51.
      Plan sha256 remains e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4
      with 2,595 rows / 2,571 CIKs, cursor 0, completed 0 and null
      last-successful receipt. latest-complete byte sha256 remains
      ce79636dd10dce4ca94a37a4991440b3096b4fa1fb72949511acdc0b5f4f7c97.
  - claim: >
      The complete owning and adjacent deterministic test batteries accept the
      bounded transport and reject hostile identity, lineage and storage cases.
    command: >
      python3 -m pytest -q tests/test_fundamental_forensics_broad_sec.py &&
      python3 -m pytest -q tests/test_edgar_forensics_collector.py
      tests/test_filing_forensics_broad_sec_lane.py
      tests/test_fundamental_forensics_edgar_index.py
    result: >
      Exit 0: 118 owning tests passed with one pre-existing sparse skip; 44
      adjacent collector/lane/index tests passed. Only non-blocking fixture and
      temporary-directory cleanup warnings were emitted.
  - claim: >
      AgentOS and textual diff validation pass and the final intended scope is
      five files with no schema, workflow or R2Store change.
    command: >
      python3 scripts/agentos.py validate && git diff --check && git diff
      --name-only e4562f8b7662f8e533f7353494fcf6f401dca149...HEAD
    result: >
      AgentOS exited 0 with 30 unrelated pre-existing warnings; diff check is
      clean. The exact five-file census is the runtime, owning test, Discovery,
      workstream and this handoff; GitHub exact-head proof remains to be
      collected on PR #6318.
unverified:
  - claim: >
      PR #6318 final exact head passes semantic CI, contract-delta, all selected
      packs, ci-gate, fences, published fence contexts and active authority.
    what_would_verify: >
      Push this handoff as the final candidate head and require every active
      GitHub check to conclude green on that exact head; inspect raw contexts
      and logs without arming auto-merge.
  - claim: >
      Sol has released PR #6318 for merge or authorized any production
      recovery retry.
    what_would_verify: >
      A later explicit Sol ruling must release the exact reviewed subject head.
      No production release exists in this handoff.
decisions:
  - DEC:FF-1R-BOUNDED-JULY-RECOVERY
discoveries:
  - DSC:FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN
  - DSC:FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER
unresolved:
  - >
    Exact-head GitHub proof and Sol implementation review remain required
    before PR #6318 may leave HOLD-FOR-SOL.
  - >
    The frozen recovery plan remains at cursor 0. A later operation is a
    corrective retry of tranche A, not tranche B, and requires new Sol
    authorization after this repair lands.
  - >
    Previous-quarter weekly reconciliation remains SPEC_ONLY / NOT_BUILT and
    FF-2 remains FORBIDDEN / NOT_STARTED.
next_actions:
  - >
    Push the final handoff commit, collect exact-head PR #6318 semantic CI,
    contract, pack, fence, authority, mergeability and review-thread receipts,
    then stop at the ratified HOLD for Sol.
  - >
    After a later explicit Sol release only, land the exact reviewed head and
    verify merged-main ancestry; do not dispatch recovery in the repair wave.
do_not_redo:
  - >
    Do not widen POINTER_MAX_BYTES, change the global R2Store, rewrite ANGO or
    another immutable manifest, regenerate the frozen plan, delete/recreate
    continuation, or dynamically raise the manifest ceiling.
  - >
    Do not rerun 32626273461, dispatch a corrective tranche-A retry, call any
    operation tranche B, move latest-complete, or start prior-quarter/FF-2
    work without later explicit Sol authority.
danger_areas:
  - >
    Production manifests currently use the #5898 identity era while new #6285
    writes include component-set identity. Reader-only legacy compatibility is
    necessary for immutable evidence; new writers must never select it.
  - >
    A future manifest above 128 KiB is an architecture-review refusal, not a
    reason to skip the issuer, advance the cursor, truncate evidence, or grow
    the ceiling at runtime.
  - >
    The first failed run selected 64 CIKs but completed zero. Cursor 0, null
    last-successful receipt and unchanged latest-complete are load-bearing.
---

## 0. State

PR #6318 contains the bounded immutable issuer-manifest transport repair and
is intentionally draft / HOLD-FOR-SOL. FF-1R is not production-proven. The
first recovery operation remains a fail-closed cursor-zero witness, not a
checkpoint or a completed tranche.

## 1. What is left

Collect complete exact-head GitHub proof and stop for Sol's implementation
review. If Sol later releases the repair, land only that exact reviewed head
and verify ancestry. This wave may not dispatch production recovery.

## 2. What will bite you

The immutable legacy ANGO body cannot be re-identified under the newer
component-set formula or rewritten. The stored identity era must be selected
from the body fields: both component fields absent means legacy read
compatibility; both present means current identity; a mixed body fails closed.
Compact pointer bounds remain unchanged even though their immutable targets
use the larger measured envelope.

## 3. What was decided and found

DSC:FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER records the measured
transport-class distinction. DEC:FF-1R-BOUNDED-JULY-RECOVERY remains the
recovery architecture; this repair does not amend plan, selection, cursor or
production-dispatch authority.

## 4. Not in scope

No recovery dispatch/retry, continuation tranche, previous-quarter
reconciliation, FF-2, Wave-2, public product, Capital Structure, Prophet, CI
control plane, global R2 transport, schema, or workflow capability changed.
