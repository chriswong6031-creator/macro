---
workstream: WS:AGENT-OS
session: sol/mas28-w0r-r028-reconciliation
model: sol
ended_because: complete
mission: >
  Reconcile the canonical W0 R028 contradiction before W1 resumes: preserve
  PER_TARGET semantics while making each finding carry its exact MAS target identity,
  restamp the canonical ruleset/architecture/template contract, and durably record the
  supersession without touching the held W1 implementation.
state_before: >
  Macro 6a1795192cc06c1ea8c9004a33b9e4bec62831c9 carried ruleset digest
  41d5634a6ca6d4bbd993e728b73d839260452b24c891e556c59da52a184a1859.
  R028 was PER_TARGET at fixed SNAPSHOT:LINEAR but evidence contained only
  issue_type, portfolio_mode, and target_role, so distinct identical-shaped targets
  collapsed under finding uniqueness. W1 PR #6328 was open, deliberately unarmed, and
  held for exact source-law reconciliation.
changed:
  - path: config/pr_linkage_rules.v1.json
    what: >
      Adds the existing `target` ATOM to R028 evidence_keys only and reserializes the
      manifest as exact canonical JSON with no final newline.
  - path: research/MASTERMIND_PR_LINKAGE_VALIDATOR_V1_ARCHITECTURE_FREEZE_2026-08-23.md
    what: >
      Updates the R028 rule table and normative prose to bind exact MAS-n target
      identity while preserving PER_TARGET, fixed location, 46 rules and 44 keys.
  - path: .github/pull_request_template.md
    what: >
      Restamps the default authoring surface to ruleset digest
      2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa
      and architecture SHA-256
      9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e.
  - path: .github/PULL_REQUEST_TEMPLATE/design_migration.md
    what: >
      Applies the identical marker restamp while preserving the design-migration gates.
  - path: agentos/decisions/DEC-MAS28-PR-LINKAGE-VALIDATOR-V1-REPORT-ONLY.md
    what: >
      Marks the earlier record superseded by the exact R028 reconciliation successor.
  - path: agentos/decisions/DEC-MAS28-R028-TARGET-IDENTITY-RECONCILIATION.md
    what: >
      Records the durable repair choice and carries forward every unrelated grammar,
      compatibility and report-only authority boundary.
  - path: agentos/discoveries/DSC-MAS28-R028-EVIDENCE-IDENTITY-COLLAPSE.md
    what: >
      Records the historical identity-collapse landmine, falsifier and W1 consequence.
  - path: agentos/workstreams/WS-AGENT-OS.md
    what: >
      Closes W0/W0B, records W0R as the W1 dependency, and points W1 #6328 at exact
      reconciled source law without starting Agent OS W4.
  - path: agentos/handoffs/AGENT-OS-2026-08-23-mas28-w0r-r028-reconciliation.md
    what: >
      Provides this cold-session boundary and downstream propagation receipt.
verified:
  - claim: The modifying carrier started from the fresh protected Macro default head.
    command: >
      git fetch origin; git rev-parse HEAD origin/main; git status --short --branch
    result: >
      Both refs were 6a1795192cc06c1ea8c9004a33b9e4bec62831c9 before edits;
      branch claude/mas28-w0r was clean in the commissioned sparse worktree.
  - claim: Current cross-repository protected heads and authoring surfaces were read.
    command: >
      git -C each repository fetch origin; git rev-parse origin/main or origin/master;
      git show the protected .github/pull_request_template.md blobs.
    result: >
      Macro 6a1795192cc06c1ea8c9004a33b9e4bec62831c9; Mastermind
      eb9910681a6db9f9675b25233c8865bb43325c32; Terminal
      4e50b5f9f8a31a860f3dd12e7d70aaca52be421f. Mastermind blob
      a258becc198a1305cfde86969e77e4c5e141fbc6 and Terminal blob
      b4c91ced8d07ff024f3fe3ee539cb9387e941a5e still carry the prior markers.
  - claim: W1 and template collision state was reconciled without adopting foreign bytes.
    command: >
      gh pr view 6328 and 6135; git status --short --branch in mas28-w1 and mas28-w1r;
      gh api repos/{owner}/{repo}/rulesets for all three repositories.
    result: >
      #6135 merged as 283a12b393ebec9f849aefc3764ed0725518a4d9; #6328 is open,
      unarmed and concluded-green except the known ci-authority/codex pilot negative;
      its principal carrier has foreign dirt while clean W1R matches remote head
      cbbfd81143d4121b6270190a7a80dcc237732dc7. No repository ruleset is installed.
  - claim: Exact canonical digests and prospective Macro template blobs are frozen.
    command: >
      shasum -a 256 config/pr_linkage_rules.v1.json architecture-file;
      git hash-object .github/pull_request_template.md design_migration.md;
      inspect the manifest final byte.
    result: >
      Ruleset 2e97ad7acd0aec77ef18dbd76a1b3f2bbf8b7d4585e938498615de1917aa71aa;
      architecture 9c57ad499fa34ee32f0ffeb9f2f5928f0515dba1609f984e5a20ce6576e7f75e;
      default template blob 4af0a1a3273ba4eefec99cad2441264705551835;
      design template blob ee4c7d1bf8d26d18218443c382e4e9cce2a8bd46; manifest final byte
      is `}` with no newline.
unverified:
  - claim: The new Macro template-marker cutover is live and GitHub prepopulates it.
    what_would_verify: >
      Merge W0R, fetch exact origin/main, create one real disposable draft PR without an
      explicit body, prove both new markers and the six-line block, then close it and
      delete its remote branch.
  - claim: The exact new cutover receipt and immutable legacy cohort are recorded in Linear.
    what_would_verify: >
      After merge/proof, compute the canonical receipt from exact repository/default ref,
      merge SHA, both template blobs, first strict PR number, then-open legacy cohort and
      new ruleset digest; root coordinates the one exact MAS-28 comment. This W0R does not
      mutate Linear independently.
  - claim: W1 and the two downstream repository templates consume the new digest.
    what_would_verify: >
      Separate bounded W1/Mastermind/Terminal carriers merge from protected heads and
      their schemas, goldens, marker blobs and real draft proofs match this handoff.
unresolved:
  - "W1 PR #6328 must remain paused until W0R is on origin/main, then refresh rather than cherry-pick an unmerged law."
  - "W1 must rotate five old-digest pins (two observation-schema constants, one report-schema constant, the core frozen digest, and its digest golden), add target to the R028 contract/emitter/report schema, and add a hostile identical-shape two-target non-collapse test."
  - "Mastermind .github/pull_request_template.md plus tests/test_pr_linkage_authoring_template.py and Terminal .github/pull_request_template.md still name the prior contract/ruleset digests; propagate markers only, not a duplicate manifest or validator."
  - "The post-merge cutover receipt is necessarily external to the self-referential merge commit; root must coordinate the exact Linear comment after the proof PR is closed."
next_actions:
  - "After W0R merges, capture the exact Macro draft-prepopulation and cutover receipts, close/delete the proof carrier, and return them to root for one MAS-28 Linear comment."
  - "Then refresh W1 #6328 from the merged W0R law and require target in manifest schema, emitter, goldens and hostile two-target dedup tests before re-review."
  - "Update the Mastermind and Terminal template markers in separate repository-local PRs; do not copy the Macro manifest or create another truth store."
do_not_redo:
  - "Do not change R028 cardinality or location; exact `target` evidence is the canonical repair."
  - "Do not add a 45th evidence key, 47th rule, workflow, House-Law row, branch protection, merge gate, Linear mutation, control plane or second manifest."
  - "Do not touch or adopt the foreign W1 carrier dirt; W1 resumes only after W0R merges."
danger_areas:
  - "A new ruleset digest invalidates old marker receipts until each repository propagates the exact marker and records its own immutable cutover."
  - "Template blob SHA uses Git blob identity, while contract/ruleset markers use SHA-256 of exact file/canonical-manifest bytes; do not substitute one hash family for another."
  - "A fixed finding location cannot supply target identity; evidence must carry it before uniqueness reduction."
---

# Cold-session return point

Start from merged W0R, not from the held W1 branch. Verify the exact protected default head and
the root-coordinated cutover receipt, then reconcile W1's manifest schema/emitter/tests to require
`target` for R028. The rest of the V1 contract is frozen and remains REPORT_ONLY.
