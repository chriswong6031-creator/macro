---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: codex/cs-v2-w2c-runtime
model: codex
ended_because: ci_handoff
mission: >
  Attribute the 80.3-minute W2 runtime falsifier, implement only the measured
  sustainable-runtime repair, bind it to exact tests and production-ledger
  replay, and stop in a draft HOLD-FOR-SOL PR without merging.
state_before: >
  W2A and W2B were proven live and natural run 32786919396 drained inherited
  LIVE debt from 337 to zero. W2 remained in progress because discovery was
  degraded and Capital Structure job 97654020902 crossed its 76.5-minute
  warning at 80.3 minutes. W3/W4 were held and daily dispatch forbidden.
changed:
  - path: engine/capital_structure/document_terms.py
    what: >
      Close exact manifest/content/parser dependency reuse, source-validate only
      dirty roots nightly, preserve whole-ledger --rebuild authority, and emit
      attributable reuse/read/validation counts.
  - path: scripts/compile_capital_structure_document_terms.py
    what: >
      Remove the duplicate post-compile historical retained-byte re-derivation;
      retain schema, manifest dependency, history, and atomic output checks.
  - path: tests/test_capital_structure_document_terms.py
    what: >
      Add hostile stale-evidence, new-evidence, parser-invalidation, no-read,
      full-rebuild semantic/byte-parity, and authority-reseal tests.
  - path: docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md
    what: Freeze exact dependency reuse and full-rebuild parity as source law.
  - path: research/CAPITAL_STRUCTURE_W2C_INCREMENTAL_DOCUMENT_TERMS_QUALIFICATION_2026-08-25.md
    what: Record three-run attribution, production replay, headroom, gates, and falsifiers.
  - path: agentos/decisions/DEC-CS-V2-W2C-EXACT-DEPENDENCY-INCREMENTAL-DOCUMENT-TERMS.md
    what: Record the chosen repair and rejected timeout/cap/cache alternatives.
  - path: agentos/discoveries/DSC-CS-V2-W2C-DOCUMENT-TERM-ESTATE-SCALING.md
    what: Make the historical-estate runtime mechanism durable across sessions.
  - path: agentos/workstreams/WS-CAPITAL-STRUCTURE-INTELLIGENCE-V2.md
    what: Record Sol's W2C/W2D reruling while keeping W2 in progress and W3/W4 held.
verified:
  - claim: Exact production no-op replay performs zero retained-source reads and preserves all rows.
    command: >
      /opt/homebrew/bin/python3.12 inline replay of origin/main
      data/capital_structure source ledger and document_term_observations through
      compile_document_term_records with a source reader that raises on any call
    result: >
      8,757 manifests, 3,505 observations, 670 eligible, zero processed, 670
      reused, zero source reads, zero parser invalidations, exact output equality,
      9.071 seconds.
  - claim: Incremental/full parity and hostile dependency invalidations pass.
    command: >
      /opt/homebrew/bin/python3.12 -m pytest -q
      tests/test_capital_structure_document_terms.py -k
      'incremental_compile or new_evidence_identity or parser_version_change_forces_one_root or disk_incremental_and_full_rebuild or lineage_validation_reuses or released_authority_policy or cold_tracked_source_export'
    result: 8 passed.
  - claim: The integrated W1/W2A/W2B Capital Structure invariant surface remains green.
    command: >
      /opt/homebrew/bin/python3.12 -m pytest -q over the 12 attributable
      source-identity, closed-bundle, compiler, event-spine, document-term,
      projection, daily, SEC-collector, health, source-manifest, and
      source-ledger test targets, excluding only the unchanged pre-existing
      Python.org CPython 3.12.2 spoof-probe parameter.
    result: 401 passed, 2 skipped, 3 deselected, 3 temporary-cleanup warnings.
  - claim: Append-only source/evidence fences remain green.
    command: >
      /opt/homebrew/bin/python3.12 -m pytest -q
      tests/test_append_only_assertions.py
      tests/test_append_only_base_fence.py
    result: 62 passed, 3 temporary-cleanup warnings.
  - claim: Agent OS records validate with no new schema or reference errors.
    command: /opt/homebrew/bin/python3.12 scripts/agentos.py validate
    result: 711 records, 0 errors, 33 pre-existing warnings.
  - claim: The intentional authority closure was control-first resealed while parser semantics stayed frozen.
    command: >
      Import neutralized exact origin/main and changed scratch exports under
      reviewed CPython 3.12.13; compute _semantic_closure for authority and parser entrypoints.
    result: >
      Control reproduced authority 426 / 52b07cec / a5f1ef92 and parser
      263 / 4939a46e / d4751527 exactly. Changed authority is
      432 / ce4537de / b08d50df; parser remains exactly unchanged.
unverified:
  - claim: The natural production job returns below 76.5 minutes with both W2C and W2D present.
    what_would_verify: >
      Sol accepts and merges exact W2C and W2D heads, then the first natural
      scheduled collector -> Capital Structure chain containing both completes.
unresolved:
  - "W2D discovery-clock/Latest-Filings implementation remains a separate held PR and may not merge before W2C adjudication."
  - "One local Python.org 3.12.2 spoof-probe assertion sees an unreleased installed runtime fingerprint; unchanged origin/main control fails identically, so W2C does not alter the runtime allowlist."
  - "W2 remains in progress; W3 and W4 are still held."
next_actions:
  - "Sol reviews the exact W2C PR head; do not merge without a new exact-head release."
  - "Complete W2D as one separate draft HOLD-FOR-SOL PR; do not merge it before W2C adjudication."
  - "After both accepted heads merge, observe only the first natural scheduled chain containing both."
do_not_redo:
  - "Reopen W2A/W2B capacity, spill, lane, pacing, carrier, warning, timeout, queue, store, projection, fence, or authority law."
  - "Add a document-term cache or second truth store; the canonical immutable ledger is the reuse surface."
  - "Reread/reparse unchanged retained roots after exact dependency admission; use --rebuild for the deliberate whole-ledger audit."
  - "Dispatch or rerun daily.yml, or start W3/W4."
danger_areas:
  - "A new manifest/evidence identity and a parser-version change must force source reads even if accession or visible values look unchanged."
  - "Full-rebuild parity is an authority gate; do not optimize --rebuild by removing its whole-ledger retained-byte audit."
  - "The 63 dirty roots were HISTORICAL spill, but this PR has no authority to cap or rewrite spill law."
prs: [6415]
decisions:
  - DEC:CS-V2-W2C-EXACT-DEPENDENCY-INCREMENTAL-DOCUMENT-TERMS
discoveries:
  - DSC:CS-V2-W2C-DOCUMENT-TERM-ESTATE-SCALING
---

W2C is built and locally qualified, not accepted, merged, or proven live. The
carrier must remain draft and held for Sol at one immutable exact head.
