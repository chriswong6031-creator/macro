---
key: CALCBENCH-FILING-FORENSICS-PARITY
title: Calcbench parity inside Filing Forensics
objective: >
  Build clean-room Calcbench-equivalent financial-statement, filing, disclosure,
  point-in-time, query, export, and analyst workflows over lawfully sourced data,
  delivered through the existing Fundamental/Filing Forensics product family.
  Done means Waves 0A-8 are merged and live, production evidence is reversible to
  immutable SEC sources and receipts, analyst/API/Excel round trips agree, and the
  independent parity, temporal, security, UX, and operations closure audit passes.
status: blocked
program: fundamental-forensics
repos: [macro, terminal]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
blocked_by:
  - >
    Operator must replace the protected attested-history-seed environment secret
    R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID with the Cloudflare R2 S3 Access Key ID
    for the separate Object Read & Write writer role; update its paired secret too
    if a new writer token is generated. The value must never enter chat or git.
next_action: >
  Check whether R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID has an updated_at later than
  2026-08-11T03:27:33Z; if so, dispatch attested-history-aapl-seed.yml from main,
  approve the protected environment, and independently admit the four downloaded
  artifacts with verify_fundamental_forensics_attested_history_seed_bundle.py.
owns_paths:
  - app/forensics.py
  - collectors/fundamental_forensics_acquisition.py
  - collectors/fundamental_forensics_companyfacts.py
  - config/fundamental_forensics/
  - engine/fundamental_forensics/
  - scripts/build_fundamental_forensics.py
  - scripts/build_fundamental_forensics_disclosures.py
  - scripts/fundamental_forensics_disclosure_bundle.py
  - scripts/run_fundamental_forensics_attested_history.py
  - scripts/run_fundamental_forensics_wave2.py
  - scripts/seed_fundamental_forensics_attested_history.py
  - scripts/verify_fundamental_forensics_attested_history_seed_bundle.py
  - templates/fundamental_forensics.css
  - templates/fundamental_forensics.html.j2
  - templates/fundamental_forensics.js
  - tests/test_forensics_api.py
  - tests/test_fundamental_forensics_*.py
  - .github/workflows/attested-history-aapl-seed.yml
  - .github/workflows/attested-history-operator.yml
waves:
  - id: W0A
    title: Dedicated attested-history reader and credential delivery
    status: done
    next_action: >
      Preserve the dedicated store and fail-loud delivery boundary; functional
      storage proof remains part of W0B's cross-role control read.
  - id: W0B
    title: Bounded AAPL seed, independent bundle admission, packet activation, and zero-write replay
    status: in_progress
    depends_on: [W0A]
    next_action: >
      Wait for the protected writer Access Key ID timestamp to advance, then run
      the exact seed-to-verifier-to-packet-to-read-only-replay sequence in the
      latest handoff. Do not skip or reorder an admission gate.
  - id: W1
    title: First live v2 attested query-snapshot publication
    status: todo
    depends_on: [W0B]
    next_action: >
      After the zero-write replay passes, build the single-writer driver around
      the existing publisher library and prove pointer-last CAS publication.
  - id: W2
    title: Partitioned issuer corpus and frozen gold QA
    status: todo
    depends_on: [W1]
    next_action: >
      Run the governed 12-issuer slice, freeze review samples, and pass coverage,
      source-reversibility, disclosure-diff, and blinded QA gates before scaling.
  - id: W3
    title: Production bitemporal and as-reported query plane
    status: todo
    depends_on: [W2]
    next_action: >
      Wire the governed metric registry and immutable snapshots into authenticated
      original/latest/as-of, trace, bulk, peer, and disclosure query contracts.
  - id: W4
    title: Complete analyst cockpit and cross-company workflows
    status: todo
    depends_on: [W3]
    next_action: >
      Extend the existing Filing Forensics cockpit with as-reported statements,
      recent filings, multi-company, bulk, analytics, saved work, and alerts.
  - id: W5
    title: Specialist filing, dimensional, filer, and professional intelligence
    status: todo
    depends_on: [W2, W3]
    next_action: >
      Ship each specialist family as a separately governed dataset with coverage,
      schema, QA, source trace, and domain-review acceptance.
  - id: W6
    title: API, export, and Excel delivery
    status: todo
    depends_on: [W3, W4]
    next_action: >
      Implement tenant-bounded API/export jobs and Excel formulas over the same
      query contract, then prove value, vintage, and receipt round trips.
  - id: W7
    title: Context-only Neural Web and Prophet integration
    status: todo
    depends_on: [W2, W3]
    next_action: >
      Feed receipt-bearing point-in-time context and a leakage-safe outcome ledger
      without granting rank, size, gate, escalation, or trade-origination authority.
  - id: W8
    title: Independent full-parity closure audit
    status: todo
    depends_on: [W4, W5, W6, W7]
    next_action: >
      Audit the clean-room boundary, temporal laws, source completeness, security,
      UX, operations, and advertised parity ledger against live evidence.
landmines:
  - >
    Filing Forensics is the product surface; Calcbench parity is the capability
    program behind and around it. Do not create a second filing product, parallel
    knowledge base, or third semantic query model.
  - >
    The current private-state API and the dedicated attested-history API are
    intentionally separate storage planes. The dedicated bucket is
    mastermind-attested-history-prod at bucket-root fundamental_forensics/; the
    similarly named shared research bucket is not an acceptable substitute.
  - >
    GitHub secret listings are paginated, masked workflow values prove nothing,
    and a healthy service only proves fail-closed startup. Trust exact secret
    timestamps plus the sanitized workflow stage error and live control reads.
  - >
    The repository Object Read token and protected-environment Object Read & Write
    writer token must be separate. Changing reader permissions cannot repair an
    invalid writer S3 Access Key ID.
  - >
    Neural Web and Prophet may consume context only. No plausible filing narrative
    or technically valid receipt promotes Forensics into ranking, sizing, gating,
    escalation, or trade authority.
do_not_redo:
  - >
    Do not debug SEC acquisition before writer-store admission. The AAPL seed
    pipeline already passed a hermetic end-to-end run with the correct object
    layout and four-artifact bundle.
  - >
    Do not rerun seed run 31534160304 unchanged. It failed before the first R2
    request because the protected writer parent Access Key ID was invalid, and its
    environment-secret timestamp was still unchanged on 2026-08-16.
  - >
    Do not hand-edit or semantically reconstruct the operator packet. Admit the
    exact downloaded bytes with the independent verifier, then commit them intact.
  - >
    Do not treat existing engine code, fixture tests, secret delivery, or an API
    401/503 as proof that a real issuer was seeded or a production v2 pointer exists.
artifacts:
  - research/CALCBENCH_FULL_PARITY_PROGRAM_AND_WAVE_2_BUILD_DOCKET_2026-08-01.md
  - research/CALCBENCH_PARITY_CLAUDE_CONTINUATION_HANDOFF_2026-08-06.md
  - research/CALCBENCH_PARITY_WAVE_0B_CONTINUATION_HANDOFF_2026-08-11.md
  - agentos/handoffs/CALCBENCH-FILING-FORENSICS-PARITY-2026-08-16.md
---

## Current product shape

Filing Forensics is the existing customer-facing product. Calcbench parity is
the program that deepens that product from a current-filing review workbench into
a source-preserving historical financial-data and analyst platform. The same page
already consumes the private current-state API and has a Run record view wired to
the attested-history receipt API. The latter has no admitted production issuer yet,
so the integration is real in code but incomplete in live data.

This workstream deliberately keeps the storage boundary separate while keeping the
product coherent: current private state remains one plane; immutable attested
history lives in its own bucket and API; both meet in Filing Forensics and later
analyst/Terminal surfaces through governed contracts.
