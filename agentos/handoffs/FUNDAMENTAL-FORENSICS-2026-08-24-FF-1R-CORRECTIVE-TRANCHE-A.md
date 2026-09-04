---
workstream: WS:FUNDAMENTAL-FORENSICS
session: warp/warp-dd26b312f6b44ddd8c59acd6170cfe70
model: codex
ended_because: blocked
mission: >
  Execute exactly one Sol-released FF-1R corrective tranche-A production
  recovery against the frozen cursor-zero plan after #6318 landed, adjudicate
  its bounded receipt, and durably reconcile the organizational state without
  retrying, skipping an issuer, or starting a later tranche.
state_before: >
  PR #6318 had merged the immutable issuer-manifest transport repair as
  32cbd775e827653e88f8be6f8094d73e8c3014dc. Recovery plan
  e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4
  remained at cursor/completed 0, backlog 2,571 and null last-successful
  recovery receipt. ANGO remained the first selected issuer with its governed
  20,779-byte legacy manifest. No post-witness recovery had executed.
changed:
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: >
      Record #6318 as merged, replace the stale transport-repair landing action
      with the actual failed corrective tranche-A receipt, retain
      BUILT_NOT_PROVEN, and bind the no-retry/no-skip stop.
  - path: agentos/handoffs/FUNDAMENTAL-FORENSICS-2026-08-24-FF-1R-CORRECTIVE-TRANCHE-A.md
    what: >
      Preserve the release, pre-dispatch, workflow-history, production receipt,
      before/after object identities, budget, and stop-condition evidence for a
      cold successor and Sol review.
  - path: agentos/discoveries/DSC-FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT.md
    what: >
      Record the durable production fact that ANGO's merged prior/current
      filing evidence conflicts on acceptance_datetime after the manifest
      transport succeeds, and bind future work to source adjudication rather
      than normalization or retry.
prs: [6285, 6318]
verified:
  - claim: >
      Current main admitted the landed repair and preserved every Sol-pinned
      runtime, workflow and universe artifact before dispatch.
    command: >
      git fetch origin; git merge-base --is-ancestor
      32cbd775e827653e88f8be6f8094d73e8c3014dc origin/main; git rev-parse
      origin/main:engine/fundamental_forensics/broad_sec_store.py
      origin/main:.github/workflows/filing-forensics-broad-sec.yml
      origin/main:data/edgar/fundamentals.parquet
    result: >
      Dispatch main was 03471a74e47b76d5abbe66cb69bd3d85b7a940a7;
      release ancestry passed; blobs were respectively
      283285c73813dba7f3eb6c819ac10a2ec0bc5486,
      0cae6bc43a9484367319e5981abb73afe18e3ab8 and
      84f1808685c6739af73191da6950a7a6c538a564.
  - claim: >
      The only broad-SEC execution after failed witness 32626273461 and before
      this dispatch was a lawful serialized quiet incremental, not recovery.
    command: >
      gh run list --workflow filing-forensics-broad-sec.yml --limit 30 --json
      databaseId,event,headSha,status,conclusion,createdAt,updatedAt,url; gh run
      view 32688874242 --log
    result: >
      Scheduled run 32688874242 / run_2dfb3cc973b3f025b09e completed at
      2026-08-24T04:08:26Z with mode=incremental, status/reason=complete,
      failures=[], 2,627 unchanged index rows and zero affected issuers,
      Submissions or Company Facts. Wave-2 run 32686697441 had already
      completed; the shared filing-forensics-sec writers did not overlap.
  - claim: >
      Immediately before dispatch the frozen plan, cursor-zero continuation,
      selected tranche, ANGO, and current latest-complete were valid and no
      shared-group writer was queued or running.
    command: >
      On /opt/macro with authenticated Research R2 configuration, call
      load_universe, _load_continuation, _load_prior_context and
      _read_issuer_manifest; read compact heads with
      get_bytes_strict_bounded_versioned and immutable ANGO through the 128 KiB
      manifest envelope; query both GitHub workflows for non-completed runs.
    result: >
      Plan e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4
      bound recovery_from=2026-07-12T11:23:15Z, cutoff
      2026-08-23T04:03:38Z, 2,595 rows and 2,571 CIKs. Continuation pointer
      sha256 9eb12cdede278e1478b02102f4c3a04ce5f51f979d030b27e4d8040aa0d362f5
      bound object 6aeb7b149c7d926d7974ccef2555baebf36e447fa29dc77111b75af80afc00e5,
      cursor/completed 0, backlog 2,571 and null last-successful receipt.
      The 64-CIK cursor-zero slice had sha256
      476faee281df9d1a58098fe52ee9defa45c798aa0db7e67eef3394d7db77a2cc
      and began with 0001275187 / ANGO, exactly matching failed witness
      32626273461. Both writer queues were empty.
  - claim: >
      Exactly one new logical recovery operation was dispatched and it ran on
      the preflighted main identity.
    command: >
      gh workflow run filing-forensics-broad-sec.yml --ref main -f
      mode=recovery -f recovery_from=2026-07-12T11:23:15Z; gh run view
      32708350406 --json databaseId,event,headSha,status,conclusion,jobs,url;
      gh run view 32708350406 --log
    result: >
      Run 32708350406, job 97374223159, event workflow_dispatch, head
      03471a74e47b76d5abbe66cb69bd3d85b7a940a7. It started
      2026-08-24T08:50:41Z and concluded failure at 08:51:12Z because the
      fail-closed runtime receipt exited 1. No second dispatch exists in the
      dispatch window and no writer remained queued or running.
  - claim: >
      The #6318 transport defect disappeared, but corrective tranche A failed
      its acceptance contract before any safe recovery progress.
    command: >
      gh run view 32708350406 --log; bounded read of
      fundamental_forensics/broad-sec/v1/runs/run_56830b4a74bd82a33d19/receipt.json
      followed by exact SHA-256 and JSON binding checks.
    result: >
      Receipt run_56830b4a74bd82a33d19 is 4,930 bytes with sha256
      60d39e7e6ca96d8d570d2c9af88365e7e1ad643330f90023444178df7c3e0194.
      status=failed, reason_code=historical_submissions_conflict, failures has
      one ANGO row: accession 0001628280-26-048138 conflicts on
      acceptance_datetime. completed_this_run/total=0/0 and backlog=2,571.
      There is no 20,779 > 16,384 error, store_readback_failure, substituted
      source_binding_failure, E2BIG or exit 126.
  - claim: >
      The failed operation stayed within every bounded network envelope and
      made no unaffected-universe fanout.
    command: >
      Decode the exact R2 receipt and compare coverage/recovery fields with
      MAX_AFFECTED_ISSUERS, historical-request and byte, and Company Facts
      request and byte limits in broad_sec_store.py.
    result: >
      selected=64; current Submissions=1; historical Submissions=0 and 0 bytes;
      Company Facts=0 and 0 bytes; affected issuers=0; objects/manifests
      admitted=0. Only first selected CIK 0001275187 was requested before the
      typed failure stopped the loop.
  - claim: >
      Plan, continuation, ANGO and latest-complete remained exact across the
      failed operation while immutable failure evidence was retained.
    command: >
      Repeat the same bounded versioned Research R2 reads immediately after
      run 32708350406; compare byte hashes, ETags, referenced object identities,
      decoded cursor, and SHA-bound complete receipt.
    result: >
      Plan stayed e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4.
      Continuation pointer stayed byte/ETag identical at
      9eb12cdede278e1478b02102f4c3a04ce5f51f979d030b27e4d8040aa0d362f5 /
      7d1b180677064f5630f75cde58426e76 with cursor/completed 0, backlog 2,571
      and null last-successful receipt. ANGO pointer stayed
      24540172d3d60fd3d076ff431a438ab48e2941973251a17f976f6c2dbb217a51,
      manifest ID 6cf86c4b77fe25dbae9a82cece41dd0d8917ecd428cc6eda0d562859e8f1fa9d,
      20,779-byte body sha256
      9c0118c7f10e14eb42a3cd2f108e71938b91275fbeefed2f9f2f1eb691f6ae26,
      68 filings/accessions and null predecessor. latest-complete stayed
      byte/ETag identical at
      0c2b42015572dd5a7407eee7612121a55c0465c40ddb5cce3625c75429e72e2c /
      d6655c1d591bb8a44c2f3932c01d49fd, bound to complete incremental
      run_2dfb3cc973b3f025b09e and cutoff 2026-08-24T04:08:21Z. The immutable
      failed receipt/observations were published and latest-observation moved
      to run_56830b4a74bd82a33d19 with head sha256
      aa5e62fd7e576666e0393ef3b2adb9f475eeccf27cd8405693214f81112f1285.
unverified:
  - claim: >
      Which evidence era owns the conflicting acceptance_datetime and what
      smallest lawful implementation change, if any, should reconcile it.
    what_would_verify: >
      A separately commissioned read-only source/manifest comparison and Sol
      architecture adjudication; this production packet authorizes no code fix.
  - claim: >
      Any successful FF-1R production progress or completion.
    what_would_verify: >
      A later explicitly authorized operation after the ANGO conflict is
      resolved, with failures=[], positive contiguous completion and an
      advanced SHA-bound continuation; no such authority exists here.
decisions:
  - DEC:FF-1R-BOUNDED-JULY-RECOVERY
discoveries:
  - DSC:FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN
  - DSC:FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER
  - DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT
unresolved:
  - >
    Sol must adjudicate ANGO accession 0001628280-26-048138's conflicting
    acceptance_datetime before any new recovery operation.
  - >
    FF-1R remains BUILT_NOT_PROVEN with no accepted production checkpoint;
    FF-1 remains partial.
  - >
    Previous-quarter weekly reconciliation remains SPEC_ONLY / NOT_BUILT and
    FF-2 remains FORBIDDEN / NOT_STARTED.
next_actions:
  - >
    Return run 32708350406 / run_56830b4a74bd82a33d19 and this records-only
    closeout to Sol; do not repair the conflict under this packet.
  - >
    If Sol later commissions conflict archaeology, preserve both source eras,
    accession identity and the frozen plan while establishing the exact
    acceptance_datetime disagreement before proposing any implementation.
do_not_redo:
  - >
    Do not rerun 32626273461 or 32708350406, dispatch another recovery from
    cursor 0, skip ANGO, advance the cursor, regenerate plan e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4,
    or call another operation tranche B.
  - >
    Do not rewrite ANGO, replace its legacy identity, grow the manifest
    envelope, weaken duplicate-filing conflict checks, or convert the conflict
    into source_binding_failure merely to manufacture recovery progress.
  - >
    Do not start unattended recovery, previous-quarter reconciliation, FF-2,
    or any implementation change from this records-only closeout.
danger_areas:
  - >
    A future ordinary incremental may lawfully advance latest-complete while
    the recovery plan remains frozen. Re-read both immediately before any
    later operation and distinguish incremental movement from recovery cursor
    movement.
  - >
    A failed recovery may publish immutable receipt/observation evidence and
    latest-observation without changing latest-complete or the continuation;
    do not infer progress from object presence.
  - >
    Cursor 0 means any duplicate recovery dispatch would repeat tranche A.
    The absence of a second queued or active dispatch is part of this receipt.
---

## 0. Production verdict

Corrective tranche A is **STOPPED / NOT ACCEPTED**. The immutable-manifest
transport repair is production-observed working for ANGO, but the run made zero
safe recovery progress and failed closed on a different source-consistency
invariant: accession `0001628280-26-048138` conflicts on
`acceptance_datetime`.

## 1. State that must survive

- `FF-1R = BUILT_NOT_PROVEN`; there is no accepted recovery checkpoint.
- Frozen plan: `e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4`.
- Continuation: cursor/completed `0`, backlog `2,571`, null last-successful
  recovery receipt.
- ANGO remains the exact governed legacy object; no successor was created.
- `latest-complete` remains the complete post-schedule incremental
  `run_2dfb3cc973b3f025b09e`, byte-identical across corrective tranche A.

## 2. Stop boundary

The one corrective dispatch authorized by Sol was consumed by run
`32708350406`. Its nonempty failures array, different reason code and zero safe
progress independently trigger the packet's stop condition. Preserve the
immutable failed receipt and latest-observation evidence. Do not retry, skip
ANGO, dispatch a later tranche, change code, start previous-quarter work, or
start FF-2.
