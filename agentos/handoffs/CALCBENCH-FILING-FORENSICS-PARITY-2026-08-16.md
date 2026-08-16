---
workstream: "WS:CALCBENCH-FILING-FORENSICS-PARITY"
session: claude/calcbench-handoff-20260816
model: codex
ended_because: blocked
mission: >
  Explain whether the Calcbench-parity/attested-history work is the same product
  as Filing Forensics, record exactly what this continuation built and verified,
  name every remaining gate to full completion, and leave a cold-stranger handoff
  for the next session.
state_before: >
  Wave 0A's dedicated-reader code and repository reader-secret delivery were live.
  Wave 0B had two failed production seed runs and no artifacts, packet, or operator
  replay. PR #5381 made credential failures value-free and diagnosable; PR #5388
  shipped the independent four-artifact verifier. The protected writer Access Key
  ID had not changed since the exact invalid-key failure on 2026-08-11.
changed:
  - path: agentos/workstreams/WS-CALCBENCH-FILING-FORENSICS-PARITY.md
    what: >
      Created the canonical cross-session workstream, product relationship,
      Waves 0A-8, blocker, next action, landmines, and do-not-redo record.
  - path: agentos/handoffs/CALCBENCH-FILING-FORENSICS-PARITY-2026-08-16.md
    what: >
      Captured the Aug-16 live/repository evidence, work delivered in this
      continuation, missing parity work, and exact restart sequence.
prs: [5381, 5388]
verified:
  - claim: >
      Filing Forensics and the Calcbench-parity attested-history work are linked
      parts of one product family, not two competing customer products.
    command: >-
      git show origin/main:site/fundamental_forensics.js | grep -n -E 'ATTESTED_HISTORY_URL|/api/forensics/state|historyRequest'; grep -n -E 'api/forensics/state|api/forensics/v1/attested-history' app/forensics.py
    result: >
      The same Filing Forensics client selects /api/forensics/state for private
      current state and calls /api/forensics/v1/attested-history for its Run record
      source view; app/forensics.py owns both authenticated route families.
  - claim: >
      The production writer blocker was unchanged on 2026-08-16, so another seed
      dispatch with the same protected environment values would repeat the failure.
    command: >-
      gh api --paginate repos/mastermindx-market-intelligence/macro/environments/attested-history-seed/secrets --jq '.secrets[] | [.name,.updated_at] | @tsv'
    result: >
      R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID remained 2026-08-11T03:27:33Z and
      R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY remained 2026-08-11T03:27:39Z.
  - claim: >
      No successful seed or read-only operator replay occurred after the verifier
      shipped.
    command: >-
      gh run list --workflow attested-history-aapl-seed.yml --limit 12 --json databaseId,status,conclusion,createdAt,headSha; gh run list --workflow attested-history-operator.yml --limit 12 --json databaseId,status,conclusion,createdAt,headSha
    result: >
      Seed run 31534160304 was still the newest run and concluded failure; the
      operator workflow returned no runs. No four-artifact production bundle exists.
  - claim: >
      The four repository reader/address secret names exist at repository scope,
      but their presence is not functional storage proof.
    command: >-
      gh api --paginate repos/mastermindx-market-intelligence/macro/actions/secrets --jq '.secrets[] | select(.name|test("ATTESTED_HISTORY";"i")) | [.name,.updated_at] | @tsv'
    result: >
      Bucket, endpoint, read-only Access Key ID, and read-only secret names were all
      present; latest timestamps were 2026-08-11. Values were never read or printed.
  - claim: >
      The independent production-bundle verifier is merged on main and ready for a
      successful four-artifact seed bundle.
    command: >-
      git log -1 --format='%H %cI %s' -- scripts/verify_fundamental_forensics_attested_history_seed_bundle.py
    result: >
      706336e357f9aa6421dd177ab9eaf993f3c12988, PR #5388. It recomputes byte
      lengths and SHA-256s, binds Git/run/dependency-lock provenance, and rejects
      missing, extra, or semantically tampered artifacts.
  - claim: >
      The repository and live VPS were current at the handoff audit base.
    command: >-
      git rev-parse origin/main; curl -fsSL 'https://mastermind-x.com/api/health?proof=calcbench-handoff-20260816'
    result: >
      origin/main ba6a6665a971ff5d3697fa0a1e77d55f1f81d018; live commit and checkout
      both ba6a6665a97.
  - claim: >
      No canonical operator packet is tracked on main.
    command: >-
      git ls-files --error-unmatch config/fundamental_forensics/attested_history_operator.v1.json
    result: >
      Exit 1; packet absent, as required until a successful seed bundle is
      independently admitted.
unverified:
  - claim: >
      The repository Object Read credential can mint a valid child and read from
      mastermind-attested-history-prod.
    what_would_verify: >
      A successful Wave 0B seed storage-control probe followed by the packet-bound
      attested-history-operator replay with zero writes and zero write attempts.
  - claim: >
      The protected writer pair is a valid Object Read & Write R2 S3 credential.
    what_would_verify: >
      An advanced environment-secret timestamp followed by writer-store admission
      and the bounded production seed completing successfully.
  - claim: >
      Any production v2 issuer snapshot/pointer exists.
    what_would_verify: >
      Wave 1 single-writer publication after W0B and a bounded authenticated read
      of the resulting latest/root/detail receipts.
  - claim: >
      Full Calcbench functional parity is complete.
    what_would_verify: >
      Waves 1-8 plus the independent clean-room, temporal, security, UX,
      operational, cross-surface, API, export, and Excel closure audit.
unresolved:
  - >
    Whether the operator changed only the Cloudflare reader permission server-side
    or also regenerated its S3 credential pair. GitHub timestamps show the reader
    secret values themselves were not replaced after 2026-08-11.
  - >
    The writer credential is the sole external input before W0B can reach R2; its
    Access Key ID must be corrected by the operator without exposing the value.
next_actions:
  - >
    Read AGENTS.md, CLAUDE.md, this workstream and handoff, the 2026-08-11 Wave 0B
    handoff, and the full-parity program; fetch fresh origin/main and work in a new
    .claude/worktrees worktree on a claude/ branch.
  - >
    Run the environment-secret metadata query in this handoff. If
    R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID is still timestamped
    2026-08-11T03:27:33Z, stop before dispatch and ask the operator to replace it
    with the writer token's R2 S3 Access Key ID. If a new writer token was minted,
    its paired secret must be updated in the same protected environment.
  - >
    After the timestamp advances, run: gh workflow run
    attested-history-aapl-seed.yml --ref main -f enable_aapl_seed=true. Approve the
    attested-history-seed environment under the standing operator authority and
    confirm the job actually enters in_progress.
  - >
    On success, download exactly attested-history-aapl-seed-<run_id>-<attempt> into
    a fresh directory and run: python3 -m
    scripts.verify_fundamental_forensics_attested_history_seed_bundle
    --artifact-dir <dir> --repo-root . --sha <full-run-head-sha> --run-id <id>
    --run-attempt <attempt>. Accept only status=verified,
    zero_write_preflight=true, and all_nonclaims_exact=true.
  - >
    Create the packet-activation PR from fresh main. Commit
    attested_history_operator_packet.json byte-for-byte as
    config/fundamental_forensics/attested_history_operator.v1.json; replace only
    the final absence assertion in the inert operator test with byte-exact,
    Git-provenance, workflow-binding, and tamper-rejection admission. Preserve all
    surrounding workflow-inertness assertions.
  - >
    After activation is merged/live, dispatch attested-history-operator.yml from
    main with enable_readonly_preflight=true. Accept only a packet-bound successful
    receipt proving zero writes and zero write attempts. Only then mark W0B done and
    start W1's single-writer publication driver.
  - >
    Continue Waves 1-8 strictly in dependency order from the workstream. Update the
    workstream only at durable wave boundaries and write a new dated handoff before
    any later session stops with unfinished work.
do_not_redo:
  - >
    Do not build another Filing Forensics UI to solve the credential blocker. The
    customer surface already exists and is linked to both API planes.
  - >
    Do not debug acquisition before writer-store passes. The seed pipeline was
    already proven end-to-end against a hermetic store with all four artifacts and
    the correct object layout.
  - >
    Do not infer credential success from GitHub secret names, masked *** values, a
    Cloudflare permission label, a green secret-delivery job, API health, or a 401.
  - >
    Do not use the shared research bucket or generic R2 fallback for attested
    history; the dedicated bucket and root prefix are part of the security model.
  - >
    Do not hand-edit the sealed packet, bypass the independent verifier, reorder the
    wave gates, or let Neural Web/Prophet rank, size, gate, escalate, or originate a
    trade from this evidence.
danger_areas:
  - >
    Repository secret listing requires --paginate. Inspecting only page one already
    caused a false conclusion that the four reader secrets did not exist.
  - >
    Reader and writer roles are easy to confuse: repository READONLY secrets use a
    separate Object Read token; protected SEED secrets use Object Read & Write. The
    failed run rejected the writer Access Key ID before any R2 network request, so
    it did not test reader permission.
  - >
    The R2 endpoint validator requires the full HTTPS account endpoint with no
    bucket path or trailing slash; the access-key value must be the generated S3
    Access Key ID, not an API token value, token ID, or display name.
  - >
    A successful seed produces review artifacts, not canonical public state. The
    packet activation PR and separate zero-write replay are mandatory before W1.
  - >
    Code exists, production wiring exists, and real-data proof are three distinct
    states. Preserve those labels in every status update; this program previously
    called credentials bound when the deploy workflow had silently omitted them.
  - >
    The current Filing Forensics page is backed mainly by the broad current-state
    plane. The attested Run record route is wired, but no production v2 pointer is
    published; never describe the whole page as point-in-time historical yet.
---

## §0 State — what is true right now

This is one product family with two deliberately separate data planes. **Filing
Forensics** is the user-facing workbench. **Calcbench parity** is the clean-room
capability program adding deeper statements, filing history, bitemporal semantics,
source trace, comparisons, specialist datasets, API/export, and Excel delivery.
The same Filing Forensics JavaScript already reads the current private-state API
and the attested-history receipt API, so they are linked in code and presentation.
They are not yet linked by admitted production history: the sealed-history lane has
no successful seed, packet, replay, or v2 pointer.

The continuation delivered two production safeguards. PR #5381 made the failed
credential boundary diagnosable without printing values and made reader-secret
delivery fail loudly. PR #5388 added an independent verifier for the exact four-file
seed bundle. Both are merged; the verifier is waiting for a successful bundle.
As of 2026-08-16 the protected writer Access Key ID timestamp was unchanged, the
newest seed remained failed, and the operator workflow had never run.

## §1 What is left — in order

1. Correct the protected writer S3 Access Key ID without exposing it, then run the
   bounded AAPL seed.
2. Independently verify the four downloaded artifacts; accept no semantic rewrite,
   extra file, missing provenance, non-zero preflight write, or relaxed nonclaim.
3. Activate the exact sealed packet in git and pass the preserved inertness tests.
4. Run the packet-bound read-only replay and prove zero writes/attempts. This closes
   Wave 0B.
5. Publish the first live v2 snapshot through a single-writer driver and pointer-last
   CAS (Wave 1).
6. Build and grade the partitioned issuer corpus and frozen gold QA (Wave 2).
7. Put the bitemporal/as-reported/normalized query contracts behind production auth
   and bounded pagination (Wave 3).
8. Complete the analyst cockpit, recent filings, multi-company, bulk, analytics,
   alerts, specialist datasets, API/export, and Excel surfaces (Waves 4-6).
9. Add only receipt-bearing, point-in-time context to Neural Web/Prophet with an
   outcome ledger and no authority promotion (Wave 7).
10. Run the independent full-parity closure audit (Wave 8).

## §2 What will bite you

The permission change the operator showed was for the repository reader token. That
is the correct role—Object Read—but it cannot repair the separate protected writer
credential. The writer must remain Object Read & Write. Run `31534160304` failed at
`writer-store` with `R2 parent access key ID is invalid` before R2 was contacted, so
it proves neither reader success nor reader failure.

Do not collapse product linkage into storage linkage. Two buckets/contracts are a
security and provenance feature, not evidence of two products. Conversely, sharing
one page does not make the attested lane live: until seed → independent admission →
packet → zero-write replay → v2 publication completes, most user-visible data still
comes from the broad current-state plane.

## §3 What was decided and found

No new decision or discovery record was necessary. The canonical program registry,
existing parity dockets, merged code, Actions history, secret metadata, and live
health endpoint already resolve the product relationship and blocker. This session
created the missing workstream and handoff records so those facts are now reachable
through the Agent OS context compiler.

## §4 Not in scope — do not adopt

This handoff does not authorize copying Calcbench code, protected output, mappings,
branding, or UI geometry. It does not authorize a parallel filing database, a new
customer product competing with Filing Forensics, broad issuer ingestion before the
pilot gates, or Forensics-derived trading authority. It also does not close the
separate operator decisions already recorded in the older handoff: competitor
password rotation, historical paid-body git purge, and the three pinned HOLD rows.
